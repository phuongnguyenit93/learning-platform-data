# Chiến lược phiên bản

Một hệ thống sử dụng Domain-Specific Language (DSL) thường có nhiều thành phần cùng tiến hóa: cú pháp và semantics của ngôn ngữ, API contract, schema dữ liệu, definition nghiệp vụ, compiler/runtime, plugin, package và dữ liệu đã lưu. Khi một thành phần thay đổi, producer và consumer có thể đang chạy các phiên bản khác nhau. Nếu không có chiến lược phiên bản, một thay đổi tưởng như nhỏ có thể làm parser từ chối source cũ, làm API client không đọc được response mới, khiến workflow đang chạy đổi semantics hoặc làm dữ liệu lịch sử không thể giải mã.

**Chiến lược phiên bản** (*versioning strategy*) là tập quy tắc xác định cách định danh, phát hành, tương thích, lựa chọn, lưu giữ, nâng cấp và ngừng hỗ trợ các phiên bản của một thành phần. Chiến lược tốt giúp hệ thống biết chính xác đang dùng version nào, thay đổi nào tương thích, khi nào cần migration, consumer nào bị ảnh hưởng và cách rollback hoặc tiếp tục xử lý dữ liệu cũ.

Ví dụ một ứng dụng tích hợp workflow DSL có thể có các version độc lập:

| Thành phần | Ví dụ version | Ý nghĩa |
|---|---|---|
| DSL language | 2.1 | Cú pháp và semantics được hỗ trợ. |
| Workflow definition | FulfillOrder@7 | Một định nghĩa nghiệp vụ cụ thể. |
| Engine runtime | 5.4.2 | Implementation thực thi DSL. |
| API contract | /v2 | Hợp đồng giao tiếp với client. |
| Data schema | Order@3 | Cấu trúc dữ liệu đơn hàng. |
| Plugin API | 4 | Extension contract mà plugin phải tương thích. |
| Package | commerce-rules 1.8.0 | Tập module và dependency được phát hành. |

Các version này có liên quan nhưng không nhất thiết tăng cùng nhau. Engine 5.4 có thể hỗ trợ DSL language 1.x và 2.x; workflow definition 7 có thể dùng Order schema 3; API v2 có thể vẫn trả một schema component được chia sẻ bởi nhiều endpoint.

## 1. Vì sao cần chiến lược phiên bản?

### Tiến hóa độc lập

Producer và consumer không phải lúc nào cũng deploy cùng thời điểm. API server có thể đã lên version mới trong khi client SDK cũ vẫn được sử dụng. Schema registry có thể chứa nhiều version để các service nâng cấp theo lịch riêng.

### Bảo toàn dữ liệu lịch sử

Event, workflow instance, document hoặc compiled artifact được tạo bởi version cũ có thể cần đọc lại nhiều năm sau. Nếu chỉ lưu tên definition mà không lưu version, runtime có thể diễn giải dữ liệu cũ bằng semantics mới.

### Kiểm soát breaking change

Đổi field type, bỏ keyword, thay precedence hoặc thay rule conflict policy có thể phá consumer. Versioning giúp xác định thay đổi nào cần major version mới, migration hoặc compatibility layer.

### Reproducibility

Khi một quyết định nghiệp vụ được tạo ra, tổ chức có thể cần biết engine, language, definition, plugin và schema version nào đã tạo kết quả. Version metadata giúp tái dựng hoặc audit.

### Rollback và incident response

Nếu version mới gây lỗi, cần biết có thể quay lại version trước không, dữ liệu đã ghi có tương thích không và instance đang chạy sẽ tiếp tục bằng version nào.

### Deprecation có kế hoạch

Versioning cho phép thông báo sớm, đo usage, hướng dẫn consumer chuyển đổi và ngừng hỗ trợ theo lịch thay vì xóa contract đột ngột.

## 2. Những loại version trong hệ sinh thái DSL

Không nên gom mọi thứ vào một con số version duy nhất.

### Language version

Language version xác định cú pháp, grammar, type rules và runtime semantics của DSL. Ví dụ version 2 bổ sung pattern matching hoặc thay đổi precedence của operator.

### Definition version

Definition version định danh một rule set, workflow, schema declaration hoặc query cụ thể. Hai definition có thể dùng cùng language version nhưng khác nội dung nghiệp vụ.

### Engine version

Engine version định danh implementation: parser, interpreter, compiler, scheduler, persistence adapter và API runtime. Một engine mới có thể hỗ trợ nhiều language version.

### API version

API version định danh contract giao tiếp qua HTTP/RPC. Nó có thể thay đổi độc lập với internal schema hoặc engine.

### Schema version

Schema version mô tả cấu trúc và semantics dữ liệu. Nó có thể được dùng bởi API, event, database, file hoặc message.

### Plugin/extension API version

Version này định nghĩa interface và lifecycle hook mà plugin phải tuân thủ. Engine có thể giữ plugin API ổn định qua nhiều engine release.

### Package/module version

Package version định danh artifact chứa DSL modules, function libraries, custom types hoặc definitions. Dependency resolution cần biết version chính xác của package.

### Runtime state version

Persisted execution state có thể có serialization format version riêng. Engine mới cần biết cách đọc, migrate hoặc từ chối state cũ.

### Configuration version

Cấu trúc config cũng tiến hóa. Version có thể xác định field, default và interpretation của configuration document.

## 3. Version identity và naming

Một version chỉ hữu ích khi identity của nó ổn định và không nhập nhằng.

### Namespace và name

Schema hoặc definition nên có namespace/domain để tránh trùng tên. Ví dụ:

~~~text
com.example.orders.FulfillOrder
com.example.billing.InvoiceApproval
com.example.identity.Customer
~~~

### Version gắn với identity

Có thể biểu diễn identity như:

~~~text
com.example.orders.FulfillOrder@7
com.example.schemas.Order@3
com.example.dsl.language@2.1
~~~

### Immutable identity

Một version đã publish nên được coi là bất biến. Nếu nội dung thay đổi, tạo version mới. Nếu sửa cùng version, consumer không thể biết artifact đang chạy có phải artifact đã kiểm thử hay không.

### Content hash

Ngoài version number, có thể lưu hash của artifact hoặc canonical content. Hash giúp phát hiện cùng version label nhưng nội dung khác nhau, và hỗ trợ reproducible build.

### Version label và artifact identity

Label như latest, stable hoặc current là alias thay đổi theo thời gian. Không nên dùng alias làm định danh lịch sử. Khi instance bắt đầu, resolve alias thành immutable version cụ thể rồi lưu lại.

### Version metadata

Một version record có thể gồm:
- Stable ID và version string.
- Artifact/content hash.
- Release timestamp.
- Owner và release channel.
- Language/runtime compatibility.
- Dependency versions.
- Changelog và migration notes.
- Lifecycle status.
- Signature/provenance.

## 4. Semantic Versioning

Semantic Versioning (SemVer) thường biểu diễn version dạng MAJOR.MINOR.PATCH:

~~~text
MAJOR.MINOR.PATCH
2.4.1
~~~

Quy ước phổ biến:
- **MAJOR:** thay đổi không tương thích với contract trước.
- **MINOR:** bổ sung chức năng tương thích ngược.
- **PATCH:** sửa lỗi tương thích, không chủ ý đổi contract.

### Ví dụ

Version 2.3.1 có thể được nâng lên 2.3.2 để sửa bug parser nhưng giữ grammar contract; 2.4.0 để thêm keyword hoặc API optional; 3.0.0 để bỏ syntax cũ hoặc thay semantics không tương thích.

### Pre-release

Có thể dùng suffix như alpha, beta hoặc rc:

~~~text
3.0.0-alpha.1
3.0.0-beta.2
3.0.0-rc.1
~~~

Pre-release báo artifact chưa phải stable release. Dependency resolver cần xử lý rõ việc version range có chấp nhận prerelease hay không.

### Build metadata

Build metadata có thể dùng để ghi build identifier:

~~~text
2.4.1+build.583
~~~

Theo SemVer, build metadata không quyết định precedence. Không dùng metadata này để biểu diễn thay đổi semantics.

### SemVer không tự chứng minh compatibility

Version 2.4.0 không tự động tương thích chỉ vì số MINOR tăng. Team phải có compatibility policy và kiểm thử. Một thay đổi tưởng là additive có thể phá consumer strict hoặc exhaustive enum switch.

### Version 0.x

Trong giai đoạn phát triển ban đầu, một số dự án dùng 0.x để báo API chưa ổn định. Cần công bố rõ policy vì tooling có thể diễn giải version 0 theo cách khác nhau.

## 5. Versioning theo từng thành phần

Mỗi lớp nên có quy tắc riêng dựa trên contract của nó.

| Thành phần | Đơn vị version | Thay đổi cần cân nhắc |
|---|---|---|
| Language grammar | Language major/minor | Keyword, production, precedence. |
| Language semantics | Language version | Evaluation order, null, overflow, truthiness. |
| Definition | Immutable revision | Nội dung rule/workflow cụ thể. |
| API | API major hoặc operation revision | Path, request, response, error. |
| Schema | Schema revision | Field, type, constraint, default. |
| Engine | Runtime release | Bug fix, performance, persistence. |
| Plugin API | Interface major/minor | Lifecycle hook và extension contract. |
| Persisted state | Serialization version | Field/state representation. |
| Config | Config schema version | Field, default, meaning. |

### Language syntax và semantics

Thêm một keyword có thể là MINOR nếu keyword mới không làm identifier hợp lệ cũ trở thành reserved. Nếu nó chiếm tên identifier cũ, thay đổi có thể breaking. Đổi precedence có thể thay nghĩa source hiện có dù grammar vẫn parse thành công.

### Definition revision

Một workflow definition thay đổi nội dung nghiệp vụ nên có revision riêng. Có thể dùng monotonically increasing revision hoặc content-addressed ID. Không nhất thiết áp SemVer cho mọi definition.

### Engine release

Engine version có thể tăng PATCH khi sửa lỗi runtime. Tuy nhiên, nếu bug fix thay đổi behavior mà người dùng đang dựa vào, release note phải nói rõ và có compatibility consideration.

## 6. Backward, forward và full compatibility

Compatibility mô tả khả năng các phiên bản khác nhau làm việc cùng nhau.

### Backward compatibility

Consumer hoặc runtime mới có thể đọc/tiếp nhận dữ liệu được tạo bởi version cũ.

Ví dụ engine mới vẫn parse workflow definition v1 và đọc persisted state v2.

### Forward compatibility

Consumer cũ có thể đọc dữ liệu do producer mới tạo, thường bằng cách bỏ qua field chưa biết hoặc giữ unknown enum value.

### Full compatibility

Cả chiều mới đọc cũ và cũ đọc mới đều hoạt động theo policy.

### Source compatibility

Source DSL cũ vẫn parse/type-check được bởi compiler mới.

### Binary/wire compatibility

Serialized payload cũ và mới vẫn có thể trao đổi theo protocol contract.

### Behavioral compatibility

Cùng một input và definition tạo cùng outcome/observable behavior. Đây là mức khó hơn cấu trúc vì implementation mới có thể giữ schema nhưng đổi evaluation semantics.

### Persistence compatibility

Engine mới có thể load state hoặc event được ghi bởi engine cũ.

### Plugin compatibility

Plugin build với một API version có thể load và hoạt động trong runtime version khác.

### Compatibility matrix

Với nhiều version, nên lập matrix rõ:

| Producer | Consumer | Kỳ vọng |
|---|---|---|
| API v1 | Client v1 | Được hỗ trợ trong thời gian migration. |
| API v2 | Client v1 | Chỉ hỗ trợ nếu có compatibility adapter. |
| Schema v3 | Consumer v2 | Kiểm tra forward compatibility policy. |
| Engine v5 | State v4 | Cần reader/migration tương thích. |
| Engine v6 | Plugin API v4 | Chỉ load nếu API range cho phép. |

## 7. Đánh giá breaking change

Một thay đổi có thể phá nhiều lớp contract cùng lúc.

Các ví dụ thường gặp:

- Xóa field hoặc keyword đang được sử dụng.
- Đổi type, nullability hoặc unit của field.
- Thêm required field không có default tương thích.
- Đổi enum code hoặc discriminator.
- Thu hẹp numeric range.
- Thay precedence hoặc associativity của operator.
- Đổi evaluation order hoặc short-circuit behavior.
- Thay đổi default value.
- Đổi rule priority/conflict resolution.
- Đổi lifecycle state hoặc terminal semantics.
- Thay đổi persisted state format không có reader/migration.
- Xóa plugin hook hoặc đổi method signature.
- Đổi API status/error shape mà client phụ thuộc.

### Syntactic breaking change

Source cũ không parse được hoặc parse theo cấu trúc khác.

### Semantic breaking change

Source vẫn parse nhưng cho kết quả khác. Đây là loại nguy hiểm vì compile có thể thành công nhưng business behavior đổi.

### Operational breaking change

Behavior runtime như timeout, retry, queue hoặc transaction boundary đổi khiến hệ thống vận hành khác.

### Security breaking change

Authorization, field visibility hoặc secret handling đổi. Có thể là thay đổi cần thiết nhưng phải được công bố và kiểm tra consumer.

### Consumer inventory

Trước khi phát hành breaking change, cần biết ai đang dùng field, keyword, endpoint hoặc plugin API. Không có usage data thì đánh giá impact chỉ là phỏng đoán.

## 8. Versioning cho DSL language

Language version nên xác định cả grammar và semantics.

Ví dụ một source có thể khai báo:

~~~text
languageVersion "2.1";

workflow FulfillOrder {
    ...
}
~~~

Hoặc version được chỉ định trong manifest/project config.

### Explicit language version

Source hoặc project pin language version giúp parser biết grammar/semantics cần áp dụng. Điều này tăng reproducibility.

### Default language version

Nếu source không khai báo version, compiler có thể dùng version mặc định. Default thay đổi theo compiler release có thể làm cùng source parse khác nhau; cần policy migration rõ.

### Feature flags

Một số ngôn ngữ dùng feature flag để bật syntax mới trước khi tăng major version. Feature flag cần được pin vào compilation context và lưu cùng artifact.

### Deprecation

Keyword/function cũ có thể tiếp tục hoạt động nhưng phát warning. Warning cần chỉ rõ replacement, version dự kiến removal và cách xử lý.

### Language compatibility mode

Compiler mới có thể hỗ trợ compatibility mode cho source cũ. Compatibility mode cần được kiểm thử như một language profile, không nên là tập workaround không được quản lý.

### Syntax và semantics version tách biệt

Có thể grammar version không đổi nhưng built-in function semantics đổi do runtime. Nếu điều đó ảnh hưởng kết quả, cần version semantics hoặc pin runtime/library version.

## 9. Versioning API

API versioning giúp server và client phát triển độc lập.

### URI path versioning

Ví dụ:

~~~text
GET /api/v1/orders/123
GET /api/v2/orders/123
~~~

Ưu điểm là dễ nhìn và routing rõ. Nhược điểm là version xuất hiện trong resource path và có thể tạo nhiều endpoint song song.

### Header versioning

Client gửi version trong header:

~~~http
Accept: application/vnd.example.orders-v2+json
~~~

Ưu điểm là URI có thể giữ ổn định. Nhược điểm là khó nhìn trong browser và cache/proxy cần xử lý Vary header phù hợp.

### Query parameter

Ví dụ:

~~~text
GET /orders/123?api-version=2026-01
~~~

Cách này dễ thử nhưng cần cẩn thận với cache key và canonical URL.

### Content negotiation

Server chọn representation theo Accept header hoặc media type. Có thể hỗ trợ nhiều schema representation trên cùng resource.

### Version per endpoint hay whole API

Một số API version toàn bộ contract theo major version; một số version độc lập theo operation/resource. Version per operation linh hoạt hơn nhưng tăng độ phức tạp documentation và client.

### Response version metadata

Response có thể chứa API version hoặc schema version đã được sử dụng. Điều này giúp client/log xác định contract thực tế.

### Error contract

Error response cũng cần versioning. Client nên dựa vào stable error code thay vì parse message text.

## 10. Versioning schema dữ liệu

Schema có thể tiến hóa độc lập với API hoặc engine.

### Immutable schema revision

Khi publish schema revision, nội dung nên bất biến. Schema mới tham chiếu version cũ hoặc tạo dependency snapshot.

### Additive change

Thêm field optional thường dễ tương thích nếu consumer bỏ qua unknown field và producer cũ không cần gửi field đó.

### Field rename

Rename trực tiếp có thể giống xóa field cũ và thêm field mới đối với consumer. Có thể dùng alias hoặc migration mapping.

### Field split/merge

Tách fullName thành givenName/familyName hoặc gộp address fields cần transform dữ liệu. Không phải lúc nào cũng có thể chuyển đổi không mất thông tin.

### Type change

Đổi Integer thành Decimal hoặc String thành enum có thể cần adapter và migration. Cần kiểm tra dữ liệu cũ có biểu diễn được trong type mới không.

### Null/default evolution

Đổi field từ optional sang required hoặc nullable sang non-nullable có thể phá consumer. Default cũng có thể thay đổi semantics của dữ liệu cũ.

### Schema registry

Registry lưu schema ID, version, compatibility mode, references, owner và lifecycle. Producer có thể phải đăng ký schema và vượt qua compatibility check trước publish.

## 11. Versioning event và message

Event thường được lưu lâu và có nhiều consumer. Versioning cần bảo toàn khả năng đọc lịch sử.

### Event envelope

Một envelope có thể chứa:

~~~json
{
  "eventId": "evt-2048",
  "eventType": "OrderPlaced",
  "schemaVersion": "3",
  "occurredAt": "2026-11-15T04:00:00Z",
  "producer": "orders-service",
  "payload": {
    "orderId": "ORD-1001"
  }
}
~~~

### Event immutable

Không sửa event đã publish. Khi meaning thay đổi, phát event version mới hoặc event mới; historical record vẫn giữ contract lúc phát.

### Upcasting

Consumer có thể chuyển event cũ sang internal model mới khi đọc. Upcaster cần deterministic và được version hóa.

### Downcasting

Nếu cần gửi data về consumer cũ, adapter có thể chuyển representation mới sang cũ. Cần xác định field không thể biểu diễn và policy khi mất dữ liệu.

### Event type versioning

Có thể dùng một event type với schema version, hoặc tạo tên event version riêng. Lựa chọn phải nhất quán và hỗ trợ registry/consumer routing.

### Replay

Khi replay event history, cần pin event schema và semantics của projection. Nếu projection code mới thay đổi kết quả, đó là rebuild projection mới chứ không phải event history đã thay đổi.

### Unknown fields/enums

Consumer cần policy rõ: ignore, preserve hoặc reject. Với event forwarding, preserve unknown field có thể tránh mất dữ liệu.

## 12. Versioning workflow và rule definition

Definition nghiệp vụ có lifecycle riêng và thường cần revision immutable.

### Revision number

Một workflow có thể được lưu như:

~~~text
FulfillOrder@5
FulfillOrder@6
FulfillOrder@7
~~~

Revision 7 có thể là bản mới cho instance bắt đầu sau thời điểm publish. Instance cũ tiếp tục revision đã pin.

### Active revision

Registry có thể đánh dấu revision active cho execution mới. Alias active/latest phải resolve thành revision cụ thể khi start.

### Pinning per instance

Process instance lưu:
- Definition ID/revision.
- Language version.
- Engine/runtime version.
- Package/plugin versions.
- Input schema version.
- Config/feature profile nếu ảnh hưởng semantics.

### Rule package

Rule set có thể được publish như package có version. Decision request cần lưu package revision đã tạo decision nếu audit/replay quan trọng.

### Version dependency

Workflow có thể gọi subprocess hoặc import rule package. Dependency cần được pin hoặc resolve theo policy rõ. Dùng latest động có thể làm execution không reproducible.

### In-flight execution

Khi definition mới được publish, instance đang chạy có thể tiếp tục version cũ, được migrate hoặc bị drain. Chính sách phải được định nghĩa theo loại workflow.

## 13. Versioning engine và runtime

Engine version là version của implementation, không phải version của definition.

### Runtime release

Engine release có thể chứa parser fix, performance optimization, new evaluator, scheduler change hoặc persistence adapter update.

### Supported language versions

Mỗi engine release nên công bố language versions được hỗ trợ và các feature profile tương ứng.

### Runtime compatibility

Một compiled artifact có thể phụ thuộc compiler version/IR version. Runtime cần xác thực artifact compatibility trước khi load.

### Persisted state reader

Engine mới cần đọc state cũ hoặc chạy migration. Nếu không hỗ trợ, phải fail sớm với diagnostic rõ thay vì load một phần rồi crash khi resume.

### Plugin API compatibility

Plugin cần khai báo version/range tương thích. Engine startup có thể kiểm tra plugin descriptor trước khi initialize.

### Rolling deployment

Trong lúc rollout, hai engine version có thể chạy đồng thời. Queue message, state và schema phải tương thích trong thời gian overlap.

### Runtime bug fix

Bug fix có thể thay đổi behavior của chương trình từng phụ thuộc vào bug cũ. Release note cần phân biệt intended correction và compatibility impact.

## 14. Dependency versioning và package management

DSL modules thường import function library, custom type, plugin hoặc schema package.

### Exact pinning

Pin chính xác version giúp build và execution tái lập:

~~~text
dependency "commerce-types" version "3.2.1";
dependency "tax-functions" version "1.7.0";
~~~

### Version range

Range như 3.x có thể linh hoạt nhưng kết quả resolution thay đổi theo thời điểm nếu dependency mới được publish. Build cần lockfile hoặc resolved dependency manifest.

### Lockfile

Lockfile ghi exact artifact/version/hash đã resolve. Nó giúp môi trường developer, CI và production dùng cùng dependency graph.

### Transitive dependency

Package A phụ thuộc B; package B phụ thuộc C. Resolver cần phát hiện conflict nếu A yêu cầu C v1 còn B yêu cầu C v2 và runtime không hỗ trợ cả hai.

### Dependency graph

Graph cần được resolve deterministically. Cần policy về nearest version, highest compatible version hoặc conflict failure.

### Reproducible build

Build artifact nên ghi compiler, plugin, library, grammar và dependency hashes. Nếu package registry thay đổi nội dung dưới cùng version, hash verification sẽ phát hiện.

### Supply chain

Chỉ resolve artifact từ registry được tin cậy, xác minh signature/provenance khi cần và có quy trình thu hồi dependency có lỗ hổng.

## 15. Version range và compatibility policy

Version range mô tả tập version được chấp nhận, nhưng cú pháp và semantics khác nhau giữa package manager.

Ví dụ minh họa:

~~~text
>= 2.3.0 and < 3.0.0
^2.3.0
~2.3.0
~~~

### Caret range

Trong nhiều hệ sinh thái, caret cho phép update tương thích theo SemVer. Cần hiểu chính xác behavior với version 0.x và prerelease của package manager đang dùng.

### Tilde range

Thường giới hạn update trong một minor line, nhưng behavior phụ thuộc tool.

### Exact version

Exact pin phù hợp cho runtime production hoặc build reproducible, đổi lại cần quy trình update chủ động.

### Compatibility declaration

Package có thể khai báo:
- Supported engine range.
- Supported language range.
- Plugin API range.
- Schema dependency range.
- Runtime state format range.

### Resolver behavior

Khi không có version thỏa range, resolver nên fail rõ và chỉ ra dependency conflict. Không âm thầm chọn version gần nhất nếu điều đó có thể đổi semantics.

### Locking resolved graph

Sau resolution, lưu lockfile hoặc deployment manifest để môi trường khác không resolve lại theo registry state mới.

## 16. Migration strategy

Migration chuyển source, schema, persisted state hoặc dependency từ version cũ sang version mới.

### Source migration

Có thể đổi keyword, syntax, import path hoặc expression structure. Tool migration nên tạo source mới có thể review và lưu mapping từ vị trí cũ sang vị trí mới.

### Data migration

Chuyển record/schema cũ sang cấu trúc mới. Cần xử lý null, default, invalid historical data và data loss.

### Runtime state migration

Chuyển process instance đang chạy sang state format hoặc definition mới. Cần mapping current step, variables, pending timer, task và compensation state.

### Dependency migration

Thay package/plugin version, cập nhật lockfile và kiểm tra transitive compatibility.

### Expand and contract

Một chiến lược database/API phổ biến:
1. Thêm cấu trúc mới trong khi giữ cấu trúc cũ.
2. Deploy producer có thể ghi cả hai representation hoặc dual-read.
3. Chuyển consumer sang cấu trúc mới.
4. Backfill dữ liệu lịch sử.
5. Ngừng ghi cấu trúc cũ.
6. Xóa cấu trúc cũ trong release sau.

### Migration idempotency

Chạy migration hai lần không được làm hỏng dữ liệu hoặc tạo duplicate. Dùng migration ID, checkpoint và transactional batch.

### Migration validation

Sau migration, kiểm tra record count, invariant, checksum hoặc sample semantic comparison. Cần có report record lỗi và cách retry.

### Rollback

Rollback code không nhất thiết rollback dữ liệu. Với migration một chiều, có thể cần forward-fix hoặc compatibility reader thay vì reverse migration.

## 17. Versioning và deployment strategy

Cách deploy quyết định nhiều version có thể cùng tồn tại bao lâu.

### Big-bang upgrade

Tất cả producer/consumer được nâng cùng lúc. Dễ hiểu nhưng thường khó trong hệ thống lớn và có downtime risk.

### Rolling upgrade

Thay từng instance dần. Trong thời gian chuyển tiếp, old/new version cùng chạy; contract phải hỗ trợ overlap.

### Blue-green deployment

Dựng environment mới, kiểm tra readiness, chuyển traffic rồi drain environment cũ. Cần kiểm soát message ownership và active execution.

### Canary release

Chuyển một tỷ lệ nhỏ traffic hoặc tenant sang version mới. So sánh error rate, latency và business outcome trước khi mở rộng.

### Shadow execution

Chạy version mới trên bản sao input để so sánh output, không phát side effect thật. Hữu ích với rule engine và decision DSL.

### Feature flag

Bật feature mới theo tenant hoặc cohort. Flag cần được version hóa/pin nếu nó ảnh hưởng semantics của execution lâu dài.

### Rollback window

Giữ artifact, schema và runtime state compatibility đủ lâu để rollback. Không xóa version cũ ngay khi deployment mới thành công.

## 18. Deprecation và end-of-life

Deprecation là thông báo một feature/version sẽ bị ngừng hỗ trợ trong tương lai.

### Deprecation lifecycle

Có thể dùng các trạng thái:
- Active.
- Deprecated.
- Sunset scheduled.
- Read-only/maintenance.
- Retired.

### Deprecation metadata

Một field/function/keyword có thể ghi:
- Version được deprecated.
- Replacement.
- Planned removal version/date.
- Migration guide.
- Owner/contact.

### Warning

Compiler hoặc validator có thể cảnh báo khi source dùng deprecated syntax. Warning nên có code ổn định để CI có thể cấu hình policy.

### Usage telemetry

Đếm consumer hoặc definition còn dùng feature cũ giúp quyết định thời điểm sunset. Telemetry phải tôn trọng privacy và access policy.

### Sunset notice

Thông báo cần nêu ngày ngừng hỗ trợ, ảnh hưởng, replacement và cách kiểm tra usage.

### Retention

Một version retired khỏi việc tạo execution mới vẫn có thể cần giữ để đọc historical data hoặc audit.

### Long-lived consumer

Không giả định mọi consumer nâng cấp ngay. Có thể cần adapter, compatibility endpoint hoặc hỗ trợ extended maintenance cho nhóm có lịch deploy chậm.

## 19. Reproducibility, audit và provenance

Versioning có giá trị khi có thể tái dựng chính xác môi trường đã tạo ra kết quả.

Một execution record có thể lưu:

~~~json
{
  "executionId": "exec-2048",
  "definition": {
    "id": "FulfillOrder",
    "revision": "7",
    "contentHash": "sha256:..."
  },
  "languageVersion": "2.1",
  "engineVersion": "5.4.2",
  "schemaVersions": {
    "Order": "3",
    "Customer": "2"
  },
  "dependencies": {
    "commerce-types": "3.2.1",
    "tax-functions": "1.7.0"
  }
}
~~~

### Artifact immutability

Lưu artifact hoặc content hash. Version label đơn thuần không đủ nếu registry cho phép overwrite.

### Environment fingerprint

Ghi configuration fingerprint, plugin versions, feature flags và relevant runtime options. Không đưa secret vào fingerprint record.

### Replay

Replay cần cùng definition, language semantics, dependency, input và deterministic environment. Nếu có external side effect, replay nên dùng simulation/fake service hoặc read-only mode.

### Auditability

Decision log có thể lưu engine/definition/schema version để giải thích vì sao một kết quả được tạo tại thời điểm đó.

### Provenance

Ghi source repository, commit, build pipeline, signer và publish actor. Điều này giúp xác định artifact đến từ đâu.

## 20. Versioning cho database và persisted execution state

Database schema và workflow state có yêu cầu riêng.

### Database migration version

Migration tool thường lưu migration ID đã áp dụng. Migration phải có thứ tự rõ và được review.

### State serialization version

Một workflow instance có thể lưu JSON/bytes của variables, step position và timer. Envelope cần state format version để engine biết cách decode.

### Reader/writer compatibility

Có thể triển khai reader mới trước, sau đó writer mới. Trong rolling upgrade, old reader có thể gặp state mới nếu writer rollout trước; thứ tự deploy phải được thiết kế.

### Lazy migration

Có thể migrate record khi được đọc hoặc resume. Cách này giảm migration batch lớn nhưng làm runtime path phức tạp và cần theo dõi số record còn cũ.

### Eager migration

Migrate toàn bộ dữ liệu trước khi switch runtime. Dễ vận hành sau khi hoàn tất nhưng có thể tốn thời gian và cần downtime/dual-write strategy.

### Mixed-version state

Nếu nhiều engine version cùng xử lý partition, cần bảo đảm không có writer tạo state mà reader khác không hiểu.

### Checkpoint migration

Nếu execution có checkpoint, migration cần cập nhật checkpoint và event sequence nhất quán để recovery không replay sai.

## 21. Compatibility testing

Compatibility không nên chỉ được suy luận từ version number.

### Schema compatibility check

So schema mới với schema đã publish theo backward/forward/full policy.

### Source compatibility test

Parse/type-check corpus DSL cũ bằng compiler mới. Lưu AST/semantic snapshot để phát hiện thay đổi ngoài dự kiến.

### Behavioral regression

Chạy definition và input đại diện qua runtime cũ và mới, so outcome/event trace theo policy.

### Plugin compatibility

Load plugin cũ trong runtime mới và chạy lifecycle/extension tests.

### Persisted state compatibility

Tạo state bằng engine cũ, đọc/resume bằng engine mới. Kiểm tra state và side effect không bị mất/lặp.

### Consumer-driven contract test

Consumer mô tả assumptions về API/schema; producer chạy test để xác nhận contract vẫn đáp ứng.

### Compatibility matrix automation

CI có thể kiểm tra các cặp producer/consumer version được hỗ trợ. Matrix cần giới hạn ở các combination thực sự có thể triển khai cùng nhau.

### Negative compatibility tests

Xác nhận engine từ chối rõ ràng version không hỗ trợ, plugin không tương thích hoặc state không thể migrate; không được parse một phần rồi chạy sai.

## 22. Version resolution trong DSL project

Một project DSL có thể cần lock language, module và runtime version.

Ví dụ manifest minh họa:

~~~yaml
project:
  name: order-platform
  languageVersion: "2.1"
  engineRange: ">=5.4.0 <6.0.0"

dependencies:
  commerce-types: "3.2.1"
  tax-functions: "1.7.0"

definitions:
  FulfillOrder:
    revision: "7"
    schema:
      Order: "3"
~~~

### Resolution phase

Resolver đọc manifest, tìm artifact, kiểm tra range, giải dependency graph và tạo lockfile.

### Lockfile

Lockfile ghi version chính xác, hash và source registry. Developer và CI dùng cùng lockfile để tránh resolution drift.

### Language/runtime compatibility

Manifest có thể pin language version và engine range. Engine phải kiểm tra combination đó được hỗ trợ trước khi start.

### Environment override

Không nên để production tự động dùng latest package nếu project yêu cầu reproducibility. Override phải có explicit release/deployment change.

### Multiple environments

Dev/staging/prod có thể dùng cùng definition revision nhưng config khác nhau. Nếu config ảnh hưởng semantics, cần ghi config version/fingerprint vào execution metadata.

## 23. Versioning và semantic change trong DSL

Không phải mọi thay đổi grammar đều là thay đổi semantics, và ngược lại.

### Keyword addition

Thêm keyword mới có thể xung đột identifier cũ. Contextual keyword hoặc language version có thể giảm breaking impact.

### Operator precedence

Thay precedence làm AST thay đổi dù source vẫn hợp lệ. Có thể yêu cầu language version mới hoặc cảnh báo migration.

### Default behavior

Đổi default timeout, null handling hoặc retry policy có thể đổi behavior của source không khai báo option. Default cần được xem như contract.

### Built-in function

Đổi implementation hoặc return type của built-in function có thể phá source. Library version hoặc language version cần pin.

### Numeric semantics

Overflow, rounding, division precision và comparison semantics phải ổn định hoặc được version hóa.

### Null/truthiness semantics

Thay cách xử lý null, missing hoặc truthiness có thể ảnh hưởng hàng loạt rule/condition. Đây là semantic breaking change.

### Evaluation order

Thay thứ tự evaluation có thể đổi side effect. Không nên xem đây là optimization vô hại.

### Runtime default library

Engine có thể load built-in library mới theo engine release. Nếu kết quả cần reproducible, dependency version cần pin riêng.

## 24. Versioning API và schema trong quá trình migration

Một thay đổi thường đi qua nhiều bước.

Ví dụ đổi response field total từ number sang Money object:

~~~json
{
  "total": {
    "amount": "125.50",
    "currency": "USD"
  }
}
~~~

Có thể triển khai:
1. Thêm field mới totalMoney trong response cũ.
2. Giữ total cũ trong thời gian chuyển tiếp.
3. Cập nhật client mới để ưu tiên totalMoney.
4. Theo dõi usage của total cũ.
5. Công bố sunset.
6. Tạo API major version mới hoặc bỏ field cũ theo policy.

### Dual field

Dual field dễ migrate nhưng có thể gây mismatch. Cần xác định field nào authoritative và có kiểm tra hai field tương đương không.

### Adapter layer

Server có thể chuyển internal model mới sang response cũ cho client legacy. Adapter cần test và có ngày sunset.

### Consumer migration order

Nếu producer phát field mới trước khi consumer hiểu nó, consumer strict có thể fail. Nếu consumer deploy trước, nó cần fallback khi producer chưa gửi field mới.

### Contract ownership

Producer chịu trách nhiệm phát hành schema/API; consumer chịu trách nhiệm nâng cấp client. Cần thống nhất timeline và xác nhận readiness trước khi remove old contract.

## 25. Versioning và security

Versioning cũng ảnh hưởng security posture.

### Vulnerable dependency

Một package version có lỗ hổng cần được thay thế. Version pinning không có nghĩa giữ mãi version cũ; cần security update process.

### Revocation

Registry có thể đánh dấu artifact bị thu hồi do compromised hoặc lỗi nghiêm trọng. Runtime cần policy chặn load version mới hoặc tiếp tục instance đã chạy.

### Signature verification

Verify signature/provenance trước khi load plugin hoặc executable artifact. Hash chỉ kiểm tra integrity nếu expected hash đến từ nguồn tin cậy.

### Security policy version

Authorization policy hoặc schema redaction policy có thể có version riêng. Audit record cần biết policy nào được áp dụng.

### Historical replay

Replay không nên tái kích hoạt secret hoặc side effect theo quyền hiện tại một cách vô kiểm soát. Dùng replay mode với capability hạn chế.

### End-of-life và patch support

Một version cũ có thể không còn nhận feature nhưng vẫn cần security patch trong maintenance window. Công bố support policy rõ.

## 26. SemVer và các mô hình version khác

SemVer không phải lựa chọn duy nhất.

| Mô hình | Đặc điểm | Phù hợp |
|---|---|---|
| Semantic versioning | MAJOR.MINOR.PATCH theo compatibility intent. | Library, runtime và package. |
| Date-based version | Dựa trên ngày/tháng phát hành. | API hoặc service release theo lịch. |
| Monotonic revision | Số tăng dần theo definition change. | Workflow/rule revision. |
| Content-addressed | Identity từ hash nội dung. | Immutable artifact, build cache. |
| Calendar versioning | Năm/tháng hoặc năm/tháng/ngày. | Product release train. |
| Schema ID registry | ID do registry cấp, version metadata đi kèm. | Event/schema serialization. |

### Date-based version

Ví dụ 2026-11 hoặc 2026.11.15. Cần quy định timezone/cutoff và không suy ra compatibility chỉ từ ngày mới hơn.

### Monotonic revision

Revision 8 lớn hơn revision 7 nhưng không cho biết mức độ tương thích. Cần release notes và compatibility metadata.

### Content-addressed identity

Hash xác định nội dung bất biến. Nhưng hash không diễn tả thứ tự, compatibility hay ý nghĩa nghiệp vụ; thường kết hợp version label.

### Kết hợp mô hình

Một definition có thể có revision 7 và content hash; engine có SemVer; API dùng major version; schema registry cấp schema ID. Đây là điều bình thường nếu mỗi loại identity có vai trò rõ.

## 27. Quy trình phát hành version mới

Một release process nên kiểm tra cả artifact và consumer impact.

1. Xác định thay đổi và loại version bị ảnh hưởng.
2. Phân loại additive, compatible, breaking, semantic hoặc operational change.
3. Cập nhật schema/language/API version theo policy.
4. Tạo migration guide và deprecation notice nếu cần.
5. Chạy parser/semantic regression corpus.
6. Chạy schema/API compatibility checks.
7. Kiểm tra plugin/dependency compatibility.
8. Tạo immutable artifact và content hash.
9. Publish lên registry/package repository.
10. Deploy theo canary/rolling/blue-green policy.
11. Theo dõi error, latency, business outcome và consumer usage.
12. Mở rộng rollout hoặc rollback theo điều kiện đã định.
13. Ghi release metadata và support lifecycle.

### Release notes

Release note cần nêu:
- Added features.
- Changed behavior.
- Deprecated features.
- Removed features.
- Migration steps.
- Compatibility matrix.
- Known limitations.
- Security fixes.

### Release approval

Breaking change có thể cần review từ owner, consumer team, security và data governance tùy contract.

### Release channel

Có thể có stable, preview, beta hoặc LTS. Consumer cần biết channel nào được dùng trong production.

## 28. Java: biểu diễn version và compatibility metadata

Một model đơn giản có thể tách version của các thành phần:

~~~java
public record RuntimeCompatibility(
    String engineVersion,
    String languageVersion,
    String pluginApiVersion,
    String stateFormatVersion
) {}

public record DefinitionReference(
    String definitionId,
    String revision,
    String contentHash,
    String languageVersion
) {}

public record ExecutionMetadata(
    String executionId,
    DefinitionReference definition,
    RuntimeCompatibility runtime,
    Map<String, String> schemaVersions,
    Map<String, String> dependencyVersions
) {}
~~~

Model này giúp lưu version metadata cùng execution. Trong implementation thực tế, nên dùng type chuyên biệt cho version thay vì String tự do để parse, compare và validate range an toàn hơn.

### Version value object

Một Version value object có thể parse major/minor/patch, prerelease và build metadata. Không nên so sánh version bằng lexical string; ví dụ 2.10.0 lớn hơn 2.9.0 dù string sorting có thể cho kết quả ngược.

### Compatibility service

Một service có thể kiểm tra runtime hỗ trợ language version, plugin API range và state format version trước khi load.

~~~java
CompatibilityResult check(
        EngineCapabilities engine,
        ProjectManifest manifest) {
    // Resolve supported ranges and report incompatibilities.
    throw new UnsupportedOperationException("Illustrative API");
}
~~~

### Explicit failure

Nếu version không tương thích, trả diagnostic gồm component, requested version, supported range và remediation. Không tự động hạ version mà không thông báo.

## 29. Observability cho version adoption

Versioning cần dữ liệu để biết consumer đã chuyển đổi đến đâu.

### Version usage metrics

Theo dõi:
- Active execution theo definition revision.
- Request count theo API version.
- Event consumer theo schema version.
- Plugin version đang load.
- Persisted state còn ở format cũ.
- Deprecated keyword/function usage.
- Migration success/failure.

### Consumer inventory

Catalog ghi service, team, environment và version dependency. Nó giúp xác định ai cần được thông báo trước sunset.

### Migration progress

Dashboard có thể hiển thị số record đã migrate, số record còn cũ, error count và throughput.

### Sunset readiness

Chỉ remove old version khi usage đã về mức cho phép, consumer owner xác nhận và fallback policy sẵn sàng.

### Avoid sensitive labels

Metric label không nên chứa arbitrary tenant ID hoặc user data nếu cardinality cao hoặc có thể tiết lộ thông tin. Dùng aggregation và controlled dimensions.

## 30. Những lỗi thường gặp trong chiến lược phiên bản

**Dùng một version number cho mọi thứ.** Language, engine, schema và definition có lifecycle khác nhau. Tách version identity.

**Dùng latest cho execution lịch sử.** Kết quả replay có thể đổi theo definition mới. Pin immutable revision lúc execution start.

**Sửa artifact đã publish.** Cùng version label có nội dung khác nhau làm mất reproducibility. Publish version mới và lưu hash.

**Cho rằng MINOR luôn an toàn.** Consumer strict hoặc semantics hidden có thể bị phá. Chạy compatibility test với behavior thật.

**Chỉ version syntax mà không version semantics.** Source vẫn parse nhưng output đổi. Ghi rõ language/runtime semantics và default behavior.

**Không lưu dependency lock.** Build hôm nay và ngày mai resolve package khác nhau. Lưu lockfile/resolved manifest.

**Không có migration plan.** Consumer không biết cách chuyển field, state hoặc source. Phát hành migration guide và adapter.

**Rollback binary nhưng không rollback data.** Runtime mới có thể đã ghi state/schema mà version cũ không đọc được. Thiết kế reader/writer compatibility trước deploy.

**Xóa version cũ quá sớm.** Historical event hoặc long-running workflow vẫn cần artifact cũ. Retain theo dependency và audit policy.

**Không theo dõi consumer usage.** Team không biết ai còn dùng contract deprecated. Duy trì inventory và telemetry.

**Version range quá rộng.** Resolver có thể chọn dependency chưa được kiểm thử. Pin bằng lockfile và compatibility matrix.

**Dùng string comparison cho version.** Thứ tự version có thể sai. Parse thành structured value và compare theo precedence rules.

**Không phân biệt API version và schema version.** Một schema có thể được chia sẻ ở nhiều endpoint. Quản lý contract theo đúng boundary.

**Không kiểm tra plugin compatibility lúc startup.** Lỗi xuất hiện khi feature được gọi lần đầu. Validate extension graph trước khi engine ready.

## 31. Quy trình xây dựng chiến lược phiên bản

Một quy trình thực tế có thể gồm:

1. **Lập inventory:** liệt kê language, definition, engine, API, schema, plugin, package, config và state format.
2. **Xác định identity:** namespace, immutable version, content hash và owner.
3. **Chọn version model:** SemVer, revision, date-based hoặc content-addressed theo từng loại.
4. **Định nghĩa compatibility:** backward, forward, full, source, behavioral, wire và persistence.
5. **Phân loại change:** additive, breaking, semantic, operational và security.
6. **Pin dependency:** exact version hoặc range có lockfile và resolved graph.
7. **Thiết kế migration:** source, schema, API, workflow instance và persisted state.
8. **Thiết kế deprecation:** warning, replacement, sunset date và support window.
9. **Tự động hóa checks:** schema compatibility, parser corpus, plugin matrix và state migration.
10. **Lập deployment plan:** rolling, canary, blue-green, shadow hoặc coordinated release.
11. **Ghi provenance:** engine/runtime, artifact hash, dependencies và configuration fingerprint.
12. **Theo dõi adoption:** consumer inventory, usage metrics và migration dashboard.
13. **Giữ rollback path:** artifact cũ, data compatibility và recovery plan.
14. **Retire có kiểm soát:** chỉ ngừng version khi usage và retention policy cho phép.

## 32. Checklist trước khi phát hành version

Trước khi publish một language, API, schema, definition hoặc engine version, cần xác nhận:

- Version thuộc đúng component và có identity ổn định không?
- Artifact đã publish có immutable và có content hash không?
- Language/engine/schema/plugin compatibility range có được khai báo không?
- Thay đổi đã được phân loại về source, behavioral, wire và persistence impact chưa?
- Consumer inventory có đầy đủ không?
- Compatibility checks đã chạy trên version được hỗ trợ chưa?
- Definition và execution có pin exact version không?
- Dependency graph có lockfile/resolved manifest không?
- Migration có idempotent, checkpoint và validation không?
- Historical event/state còn đọc được không?
- API/schema deprecation có replacement và sunset plan không?
- Release notes có mô tả breaking/semantic change không?
- Canary/shadow/rollback strategy có rõ không?
- Security patch và artifact provenance được kiểm tra chưa?
- Version usage metrics và migration progress có thể quan sát không?
- Old artifact được giữ đủ lâu cho replay, audit và long-running instance không?

## 33. Kết quả cần có sau khi thiết kế chiến lược phiên bản

Một chiến lược versioning hoàn chỉnh cho hệ sinh thái DSL thường cung cấp:

- **Version inventory:** language, definition, engine, API, schema, plugin, package, config và state format.
- **Identity model:** namespace, immutable revision, SemVer/date/revision policy và content hash.
- **Compatibility policy:** backward, forward, full, source, behavioral, wire và persistence compatibility.
- **Change classification:** additive, breaking, semantic, operational và security changes.
- **Dependency resolution:** version ranges, lockfile, registry, transitive dependency và deterministic resolution.
- **Pinning model:** exact definition/schema/runtime/dependency version cho execution và build.
- **Migration strategy:** source, API, schema, database, event và in-flight state migration.
- **Deprecation lifecycle:** warning, replacement, sunset, support window và retirement.
- **Deployment strategy:** rolling, blue-green, canary, shadow execution và rollback.
- **Reproducibility/provenance:** artifact hash, engine build, dependency versions và config fingerprint.
- **Compatibility automation:** schema/API checks, parser regression, plugin matrix và state reader tests.
- **Adoption observability:** consumer inventory, version usage, migration progress và sunset readiness.

Chiến lược phiên bản giúp DSL và ứng dụng tiến hóa mà vẫn giữ được khả năng tương tác và tái lập. Cần tách version của language, definition, engine, API, schema, plugin và persisted state vì mỗi thành phần có contract riêng. Một version đã publish nên bất biến, dependency nên được resolve có lock, execution cần pin revision cụ thể và compatibility phải được kiểm chứng bằng test thay vì suy ra từ số MAJOR/MINOR/PATCH. Khi migration, deprecation, deployment overlap, rollback và retention được thiết kế cùng nhau, hệ thống có thể nâng cấp từng phần, tiếp tục xử lý dữ liệu lịch sử và kiểm soát thay đổi semantics mà không làm consumer bất ngờ.

