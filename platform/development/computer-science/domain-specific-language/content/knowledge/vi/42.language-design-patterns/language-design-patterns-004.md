# Khai báo theo quy ước

## 1. Khai báo theo quy ước trong DSL là gì?

Một DSL (*Domain-Specific Language*) thường có nhiều declaration lặp lại cùng một hình dạng: tên service, endpoint, schema, field, rule, task, event, module hoặc handler. Nếu mỗi declaration đều phải ghi đầy đủ mọi metadata, cấu hình và liên kết, source sẽ dài và khó duy trì.

**Khai báo theo quy ước (*convention-based declaration*)** là cách thiết kế DSL cho phép compiler hoặc runtime suy ra một phần cấu hình từ các quy tắc đã được định nghĩa trước. Người viết chỉ khai báo phần khác biệt; những phần còn lại được xác định bằng convention.

Cách tiếp cận này thường được gọi là *convention over configuration*: ưu tiên các mặc định thống nhất để giảm cấu hình lặp lại, đồng thời vẫn cho phép override khi một trường hợp thực sự khác chuẩn.

Ví dụ, nếu tên schema và tên file tuân theo một quy tắc:

~~~text
schema Customer {
    id: UUID
    name: String
}
~~~

Compiler có thể suy ra:
- Schema có tên Customer.
- Resource key mặc định là customers nếu convention định nghĩa pluralization như vậy.
- File tương ứng có thể là Customer.dsl hoặc customer.schema theo file mapping đã cấu hình.
- Tên type được export là Customer nếu visibility mặc định cho phép.

Đây chỉ là ví dụ minh họa. Một DSL cụ thể phải công bố chính xác convention nào tồn tại và cách suy ra kết quả. Không được để mỗi compiler, plugin hoặc IDE tự đoán theo cách riêng.

Khai báo theo quy ước giúp:
- Giảm boilerplate.
- Làm source nhất quán giữa nhiều module.
- Tăng tốc tạo declaration phổ biến.
- Hỗ trợ code generation và discovery.
- Giảm lỗi do quên cấu hình mặc định.
- Giữ quy trình đơn giản cho trường hợp thông thường.

Tuy nhiên, convention chỉ có ích khi nó dễ hiểu, xác định, có thể kiểm tra và không tạo ra hành vi bất ngờ.

## 2. Convention over configuration

Convention over configuration là nguyên tắc thiết kế trong đó hệ thống chọn một hành vi mặc định theo quy tắc chung. Người dùng chỉ cần khai báo những gì khác với mặc định.

Ví dụ trong một DSL workflow:

~~~text
workflow OrderApproval {
    task ValidateOrder
    task ReserveInventory
    task NotifyCustomer
}
~~~

Nếu DSL có convention đặt tên, compiler có thể suy ra operation ID từ tên task, suy ra handler theo namespace hoặc gắn task vào nhóm mặc định.

Thay vì viết:

~~~text
workflow OrderApproval {
    task ValidateOrder {
        id: "validateOrder"
        handler: "handlers.ValidateOrder"
        retry: 0
        timeout: 30s
        enabled: true
    }
}
~~~

người dùng chỉ viết phần cần thay đổi:

~~~text
workflow OrderApproval {
    task ValidateOrder {
        timeout: 10s
    }
}
~~~

Các giá trị còn lại đến từ convention hoặc profile mặc định.

### 2.1. Mục tiêu của convention

Một convention tốt:
- Phù hợp với phần lớn trường hợp.
- Dựa trên thông tin đã có trong source hoặc project model.
- Có kết quả ổn định.
- Không phụ thuộc môi trường ngẫu nhiên.
- Dễ tra cứu trong tài liệu.
- Có thể bị override một cách rõ ràng.
- Có diagnostics khi không thể áp dụng.

### 2.2. Configuration vẫn cần thiết

Convention không loại bỏ configuration. Nó giảm cấu hình trùng lặp bằng cách cung cấp default.

Một hệ thống thường có ba lớp:

1. Convention: quy tắc mặc định của DSL hoặc framework.
2. Configuration: giá trị được project hoặc module chỉ định.
3. Explicit declaration: giá trị khai báo trực tiếp tại construct.

Thứ tự ưu tiên cần được đặc tả. Một mô hình phổ biến là explicit declaration thắng project configuration, project configuration thắng convention default, nhưng không phải DSL nào cũng chọn đúng thứ tự này.

### 2.3. Convention không phải phép đoán

Compiler không nên suy luận tùy ý từ tên hoặc cấu trúc gần giống. Nếu convention không cho kết quả duy nhất, compiler phải báo ambiguity hoặc yêu cầu khai báo tường minh.

Ví dụ, một class tên User có thể tương ứng với bảng users, endpoint /users, topic user-events hoặc workflow UserLifecycle. Không nên suy ra tất cả những resource đó chỉ từ tên class nếu DSL không định nghĩa rõ mapping.

## 3. Những loại convention thường gặp

Convention có thể áp dụng ở nhiều lớp của DSL.

| Loại convention | Ví dụ | Kết quả suy ra |
|---|---|---|
| Naming | CustomerProfile | Identifier hoặc operation ID |
| File layout | models/Customer.dsl | Module hoặc namespace |
| Declaration shape | Field có tên id | Primary key mặc định |
| Type mapping | String | Kiểu dữ liệu lưu trữ |
| Resource mapping | Customer | Resource path hoặc table |
| Handler binding | CreateOrder | Handler theo naming pattern |
| Visibility | Declaration trong module public | Export mặc định |
| Lifecycle | Task không khai báo retry | Retry policy mặc định |
| Serialization | Object schema | JSON field mapping |
| Validation | Field có type Email | Validator mặc định |
| Documentation | Declaration có doc comment | Mô tả được sinh tự động |
| Dependency | Import theo namespace | Module resolution |
| Testing | File có hậu tố Test | Test discovery |
| Deployment | Module trong thư mục functions | Deployment unit |

Không phải tất cả convention đều nên được bật. Một DSL cấu hình hạ tầng có thể ưu tiên explicit declarations vì hậu quả của suy luận sai rất lớn. Một DSL dành cho CRUD hoặc workflow đơn giản có thể hưởng lợi nhiều từ naming và structure conventions.

## 4. Naming conventions

Naming convention chuẩn hóa cách tạo tên từ declaration.

### 4.1. Identifier convention

Một DSL có thể chọn camelCase cho field và operation, PascalCase cho type, kebab-case cho file hoặc snake_case cho database column.

Ví dụ:

~~~text
type CustomerProfile {
    firstName: String
    lastName: String
}

operation createCustomerProfile
~~~

Convention có thể suy ra tên wire field hoặc database column, nhưng cần ghi rõ conversion algorithm.

### 4.2. Singular và plural

Resource thường có tên singular trong model và plural trong collection route:

~~~text
resource Customer {
    collectionPath: "/customers"
    itemPath: "/customers/{customerId}"
}
~~~

Nếu muốn suy ra collectionPath từ Customer, DSL cần quy tắc pluralization. Các từ bất quy tắc như Person, Child hoặc Category khiến pluralization đơn giản có thể sai.

Nên cho phép override:

~~~text
resource Person {
    collectionPath: "/people"
}
~~~

### 4.3. Prefix và suffix

Convention có thể thêm hậu tố hoặc tiền tố:
- CreateOrderHandler.
- OrderRepository.
- CustomerSchema.
- PaymentValidator.
- OrderEvents.

Cần xác định suffix là một phần tên logic hay chỉ là cách discovery implementation.

### 4.4. Case sensitivity

Tài liệu phải nêu tên có phân biệt chữ hoa/chữ thường hay không. Một hệ thống có thể dùng case-sensitive identifiers trong DSL nhưng case-insensitive path trên một platform khác; mapping cần được quy định.

### 4.5. Collision

Hai tên khác nhau có thể biến thành cùng một tên sau normalization. Ví dụ firstName và first_name có thể cùng map về first_name.

Compiler nên phát hiện collision sau khi áp dụng convention, không chỉ kiểm tra tên source ban đầu.

### 4.6. Reserved names

Convention có thể tạo tên mặc định như id, createdAt, updatedAt hoặc default. Nếu tên đó đã được dùng, cần quy tắc precedence hoặc diagnostic rõ ràng.

## 5. File layout và module discovery conventions

Một DSL có thể suy ra module từ vị trí file trong project.

Ví dụ cấu trúc:

~~~text
project/
  dsl/
    models/
      Customer.dsl
      Order.dsl
    workflows/
      OrderApproval.dsl
    services/
      PaymentService.dsl
~~~

Convention có thể ánh xạ:
- Thư mục models thành namespace models.
- Thư mục workflows thành namespace workflows.
- Tên file thành module name.
- File có hậu tố .test.dsl thành test module.
- File trong migrations thành migration artifact.

### 5.1. Root directory

Cần xác định root nào được dùng để tính đường dẫn tương đối. Không nên để cùng một file có module identity khác nhau tùy current working directory.

### 5.2. Directory-to-namespace mapping

Có thể biến path segments thành namespace segments:

~~~text
dsl/models/customer/Address.dsl
    -> models.customer.Address
~~~

Cần quy định:
- Segment có được phép chứa dấu gạch ngang không.
- Cách normalize Unicode.
- Cách xử lý chữ hoa/thường.
- Thư mục ẩn.
- Symlink.
- File trùng tên trên filesystem case-insensitive.

### 5.3. Discovery boundaries

Module discovery cần có giới hạn root. Không được tự động quét toàn bộ filesystem hoặc theo symlink ra ngoài project nếu policy không cho phép.

### 5.4. Explicit module declaration

Một file có thể khai báo module name tường minh:

~~~text
module commerce.orders
~~~

Khi module declaration khác path-derived name, DSL cần quy tắc rõ: từ chối, cho phép alias hoặc dùng explicit name làm authoritative identity.

### 5.5. Stable identity

Không nên dùng vị trí file làm identity duy nhất nếu file có thể được di chuyển. Có thể dùng module ID ổn định và giữ file path như một thuộc tính discovery.

## 6. Declaration shape conventions

Convention có thể suy ra metadata từ cấu trúc declaration.

Ví dụ:

~~~text
entity Customer {
    id: UUID
    name: String
    email: Email
}
~~~

Một DSL có thể định nghĩa rằng:
- Field id là identifier mặc định.
- Field có type Email được validate theo email format.
- Field có annotation required là bắt buộc.
- Field không có visibility modifier dùng visibility mặc định.
- Field có type collection được serialize thành array.

Các quy tắc này cần được công bố riêng. Không nên để người dùng suy ra từ tên hoặc type mà không có documentation.

### 6.1. Conventional primary key

Một convention có thể coi field tên id là primary key:

~~~text
entity Product {
    id: UUID
    name: String
}
~~~

Nếu entity có productId thay vì id, có thể cho phép chỉ định:

~~~text
entity Product {
    @key
    productId: UUID
    name: String
}
~~~

Cần nói rõ có hỗ trợ composite key hay không và convention xử lý nhiều field được đánh dấu key thế nào.

### 6.2. Timestamps

Một convention có thể nhận diện createdAt và updatedAt là lifecycle fields. Cần xác định ai tạo giá trị, timezone, precision và liệu user có được phép ghi trực tiếp hay không.

### 6.3. Soft delete

Không nên tự động suy ra field deletedAt hoặc isDeleted chỉ từ tên. Soft delete ảnh hưởng query, uniqueness, retention và audit nên thường cần annotation hoặc policy explicit.

### 6.4. Type-based conventions

Type Email có thể mặc định dùng email validator; type Money có thể mang currency semantics; type URL có thể dùng URI parser. Những mapping này phải là một phần của type contract.

## 7. Convention cho handler và dependency binding

Một DSL có thể tự tìm implementation dựa trên tên operation hoặc declaration.

Ví dụ:

~~~text
operation CreateOrder {
    input: CreateOrderRequest
    output: Order
}
~~~

Nếu convention quy định handler theo tên:

~~~text
CreateOrder -> handlers.CreateOrderHandler
~~~

thì compiler hoặc runtime có thể resolve implementation mà không cần khai báo đường dẫn handler trong mỗi operation.

### 7.1. Handler discovery

Cần định nghĩa:
- Namespace được tìm.
- Naming transformation.
- Visibility.
- Overload behavior.
- Module dependency.
- Version compatibility.
- Cách xử lý không tìm thấy handler.

### 7.2. Ambiguous binding

Nếu có hai implementation cùng phù hợp, compiler không nên chọn theo thứ tự filesystem hoặc classpath không ổn định. Cần báo ambiguity và yêu cầu explicit binding.

### 7.3. Explicit binding override

Có thể cho phép:

~~~text
operation CreateOrder {
    handler: commerce.handlers.CustomCreateOrder
}
~~~

Explicit binding cần được ưu tiên theo quy tắc đã công bố và phải được type-check với operation signature.

### 7.4. Dependency injection

Convention có thể map parameter type tới service registration. Cần phân biệt:
- Dependency được inject.
- Dependency được tự khởi tạo.
- Dependency là singleton, scoped hay transient.
- Lifetime của dependency.
- Disposal behavior.

Không nên tạo dependency tùy ý chỉ vì tìm được class cùng tên.

### 7.5. Runtime discovery và build-time binding

Build-time binding giúp phát hiện lỗi sớm và tạo artifact xác định. Runtime discovery linh hoạt hơn nhưng có thể thất bại khi deploy hoặc làm kết quả phụ thuộc classpath. Tài liệu cần nói rõ DSL dùng cách nào.

## 8. Convention cho API và resource mapping

Một DSL API có thể suy ra route, method hoặc schema mapping từ resource declaration.

Ví dụ:

~~~text
resource Customer {
    fields {
        id: UUID
        name: String
    }
}
~~~

Một CRUD convention có thể tạo:
- GET /customers.
- GET /customers/{id}.
- POST /customers.
- PATCH /customers/{id}.
- DELETE /customers/{id}.

Tuy nhiên, không phải mọi resource đều nên có đủ CRUD operations. Việc sinh endpoint cần xét authorization, lifecycle, validation và domain rules.

### 8.1. Opt-in resource generation

Có thể yêu cầu resource khai báo một profile:

~~~text
resource Customer {
    api: crud
}
~~~

Profile xác định operation nào được tạo. Đây là explicit opt-in dù chi tiết route vẫn theo convention.

### 8.2. Method inference

Một số action names có thể map thành method:
- list/read -> GET.
- create -> POST.
- replace -> PUT.
- update -> PATCH.
- delete -> DELETE.

Không nên suy ra method chỉ từ tên nếu operation có semantics khác. Ví dụ action recalculate có thể chỉ đọc, có thể tạo side effect hoặc có thể chạy job.

### 8.3. Route parameter convention

Field id có thể map thành path parameter. Cần định nghĩa type, encoding, route collision và behavior khi ID không tồn tại.

### 8.4. Request/response schema convention

Có thể dùng CreateCustomerRequest cho request body và Customer cho response. Nếu có nhiều representation, cần explicit schema selection.

### 8.5. Security defaults

Không nên tự động mở endpoint public vì declaration không ghi security. Một convention an toàn thường yêu cầu authentication mặc định, rồi cho phép public access qua explicit policy có review.

## 9. Convention cho validation và serialization

Convention có thể gắn validator hoặc serializer mặc định theo type và field metadata.

Ví dụ:

~~~text
schema Registration {
    email: Email
    age: Integer
    displayName: String
}
~~~

Type Email có thể kiểm tra format; Integer có thể kiểm tra type; field displayName có thể dùng length limits theo profile.

### 9.1. Type-to-validator mapping

Cần nêu validator nào được gắn cho từng type:
- Email.
- URL.
- UUID.
- Date.
- Duration.
- Money.
- CountryCode.

Validator phải có semantics xác định và versioned. Một validator đổi behavior có thể làm input cũ bị từ chối.

### 9.2. Required fields

Một số DSL coi field non-null là required; một số DSL phân biệt required và nullable. Không nên suy ra required chỉ từ type nếu language semantics không quy định.

### 9.3. Naming-based validation

Không nên tự gắn validator nhạy cảm chỉ vì field tên password, email hoặc phone nếu không có type/annotation đáng tin. Tên có thể gây false positive và không thể thay thế data classification.

### 9.4. Serialization naming

Convention có thể chuyển field name:
- camelCase sang snake_case.
- PascalCase sang camelCase.
- DSL name sang JSON property.

Cần xác định mapping được áp dụng ở wire format, database schema hay cả hai. Explicit rename cần có precedence rõ ràng.

### 9.5. Null, absent và default

Serialization phải phân biệt:
- Field không xuất hiện.
- Field xuất hiện với null.
- Field xuất hiện với default.
- Field bị omit khi serialize.

Các trạng thái này có thể mang semantics khác nhau đối với PATCH và schema evolution.

## 10. Convention cho workflow, rules và event

Trong workflow DSL, convention có thể giảm metadata lặp lại cho task, transition và event handler.

### 10.1. Task defaults

Task có thể nhận timeout, retry, queue hoặc owner mặc định từ workflow profile.

~~~text
workflow OrderFlow {
    defaults {
        timeout: 30s
        retry: 2
    }

    task ValidateOrder
    task ReserveStock {
        retry: 0
    }
}
~~~

Task ReserveStock override retry default. DSL cần giải thích default được kế thừa và merge như thế nào.

### 10.2. Transition naming

Tên transition có thể được suy ra từ source/target state:

~~~text
transition Pending -> Approved
~~~

Compiler có thể tạo ID như Pending_to_Approved. Nếu có nhiều transition cùng cặp state nhưng trigger khác nhau, cần thêm explicit ID.

### 10.3. Event handler discovery

Tên handler có thể được map từ event name theo convention. Nhưng event version, payload schema và delivery semantics vẫn cần được khai báo hoặc resolve tường minh.

### 10.4. Retry và idempotency

Không nên suy ra retry count lớn cho mọi task. Retry side effect có thể tạo duplicate action nếu handler không idempotent. Convention cần profile an toàn và cho phép override theo task.

### 10.5. Transaction boundary

Transaction không nên được suy ra chỉ từ việc nhiều task nằm trong cùng block. Cần một rule explicit về transaction scope hoặc một convention rất rõ gắn với operation type.

## 11. Convention resolution và precedence

Khi nhiều nguồn cùng cung cấp giá trị, DSL cần xác định nguồn nào thắng.

Một precedence model có thể là:

~~~text
Platform policy
      |
      v
Project configuration
      |
      v
Module configuration
      |
      v
Declaration-level setting
      |
      v
Convention default
~~~

Đây là ví dụ về thứ tự ưu tiên; một số policy platform không thể bị override bởi source.

### 11.1. Resolution stages

Một pipeline có thể:
1. Parse declaration.
2. Resolve module identity.
3. Apply naming conventions.
4. Load project/module configuration.
5. Merge explicit declaration values.
6. Validate final model.
7. Generate effective declaration model.

Nên có một representation trung gian chứa cả giá trị gốc và giá trị hiệu lực.

### 11.2. Default versus inherited value

Default là giá trị dùng khi không có giá trị khác. Inherited value được kế thừa từ parent scope. Hai khái niệm này khác nhau khi parent đổi.

Ví dụ một task không khai báo timeout có thể:
- Dùng convention default 30s.
- Kế thừa timeout của workflow.
- Dùng platform default.

Tài liệu cần nêu thứ tự và cách biểu diễn việc không khai báo.

### 11.3. Merge semantics

Với scalar, override thường thay thế giá trị. Với list, map hoặc nested object, có thể:
- Replace toàn bộ.
- Merge theo key.
- Append.
- Deduplicate.
- Reject conflict.

Không nên để merge behavior phụ thuộc implementation detail.

### 11.4. Null và reset

Cần phân biệt field bị bỏ qua với explicit null hoặc reset-to-default. Ví dụ null có thể là giá trị hợp lệ, trong khi từ khóa reset có thể yêu cầu bỏ override và quay lại convention.

### 11.5. Explain effective configuration

Tooling nên hiển thị:
- Giá trị hiệu lực.
- Giá trị source nếu có.
- Nguồn cung cấp.
- Quy tắc convention đã áp dụng.
- Override nào thắng.
- Version của convention profile.

Điều này giúp debug vì sao runtime nhận một giá trị khác với source trực tiếp.

## 12. Determinism và khả năng dự đoán

Convention cần deterministic: cùng source, configuration, language version và environment inputs phải tạo cùng effective model.

### 12.1. Không phụ thuộc filesystem order

Nếu discovery tìm nhiều file, không nên chọn implementation đầu tiên theo thứ tự directory listing. Filesystem enumeration có thể khác giữa platform.

### 12.2. Không phụ thuộc current directory

Module resolution cần dựa trên project root hoặc configured roots, không dựa trên thư mục mà process tình cờ được khởi chạy.

### 12.3. Không phụ thuộc thời gian hiện tại

Convention không nên tự chọn behavior dựa vào giờ hiện tại hoặc ngày build trừ khi time là input explicit và được version/record.

### 12.4. Không phụ thuộc môi trường ngầm

Environment variable, locale, operating system và classpath có thể ảnh hưởng resolution. Cần khai báo những inputs này hoặc cố định chúng trong build/runtime profile.

### 12.5. Stable generated names

Tên được sinh tự động cần ổn định khi declaration không đổi. Không dùng random ID hoặc absolute path nếu chúng làm diff thay đổi giữa máy developer và CI.

### 12.6. Reproducible builds

Build artifact cần lưu:
- DSL version.
- Convention profile/version.
- Project config hash.
- Dependency versions.
- Compiler version.
- Relevant environment inputs.

Nhờ vậy có thể tái lập effective declarations và truy nguyên thay đổi.

## 13. Ambiguity, conflict và diagnostics

Convention resolution có thể thất bại nếu có nhiều candidate hoặc dữ liệu thiếu.

### 13.1. Ambiguous discovery

Ví dụ hai handler cùng thỏa naming convention:

~~~text
handlers.CreateOrder
plugins.CreateOrder
~~~

Compiler cần báo hai candidate và yêu cầu explicit binding. Không nên chọn theo thứ tự import.

### 13.2. Convention collision

Hai declaration có thể tạo cùng route, operation ID, table name hoặc generated symbol. Collision cần được phát hiện sau normalization.

### 13.3. Missing convention target

Nếu convention yêu cầu handler nhưng không tìm thấy, diagnostic nên nói rõ:
- Operation nào thiếu binding.
- Namespace đã tìm.
- Naming pattern đã dùng.
- Cách khai báo explicit binding.

### 13.4. Unsupported shape

Một declaration có thể gần giống convention nhưng thiếu field hoặc có type không tương thích. Compiler nên giải thích vì sao nó không được nhận diện thay vì âm thầm bỏ qua.

### 13.5. Diagnostic severity

Có thể dùng:
- Error: model không thể resolve hoặc tạo hành vi không xác định.
- Warning: convention hoạt động nhưng có rủi ro hoặc sắp deprecated.
- Info: compiler đã áp dụng default.
- Hint: có thể rút gọn declaration bằng convention.

### 13.6. Explainability

Diagnostic nên chỉ ra source location và nguồn convention. Một lệnh hoặc panel explain có thể trình bày resolution trace từ declaration đến effective value.

## 14. Explicit override và escape hatch

Convention không thể bao phủ mọi trường hợp. DSL cần cách override rõ ràng.

Ví dụ:

~~~text
resource Customer {
    path: "/people"
    table: "crm_person"
}
~~~

Explicit values thay thế các giá trị suy ra theo quy tắc precedence.

### 14.1. Override từng field

Cho phép override một field mà giữ các convention khác. Đây thường là lựa chọn ít gây bất ngờ hơn việc tắt toàn bộ convention.

### 14.2. Disable convention

Có thể cho phép disable một convention cụ thể:

~~~text
resource LegacyRecord {
    conventions: none
}
~~~

Nếu hỗ trợ, cần nói rõ convention nào bị tắt: naming, route generation, schema mapping hay tất cả.

### 14.3. Custom mapping

Có thể khai báo mapping function hoặc annotation có type. Tránh cho phép arbitrary script chạy trong compile phase chỉ để biến đổi tên.

### 14.4. Explicitness cho sensitive behavior

Các hành vi ảnh hưởng security, data retention, public exposure, payment hoặc deletion thường nên yêu cầu khai báo rõ hoặc opt-in. Convention an toàn có thể chọn deny/disabled làm default.

### 14.5. Override validation

Explicit override vẫn phải được validate. Ví dụ handler path phải resolve được và signature phải tương thích với operation.

## 15. Convention profiles và cấu hình theo project

Một project có thể chọn profile để áp dụng một nhóm convention.

Ví dụ:

~~~text
conventionProfile "standard-api" {
    naming: camelCase
    routeStyle: plural-kebab-case
    defaultAuthentication: required
    requestValidation: strict
}
~~~

### 15.1. Built-in profiles

Có thể cung cấp:
- Minimal.
- Standard.
- Strict.
- Legacy compatibility.
- Framework-specific.

Mỗi profile cần mô tả chính xác các rule và default đi kèm.

### 15.2. Custom profiles

Project có thể tạo profile riêng. Nên có schema và version thay vì một tập cấu hình không kiểm soát.

### 15.3. Profile inheritance

Profile có thể kế thừa profile khác, nhưng cần phát hiện cycle và quy tắc merge rõ ràng.

### 15.4. Profile selection

Profile được chọn ở project hoặc module scope. Cần xác định có được override ở từng declaration hay không.

### 15.5. Environment-specific profile

Development và production có thể cần khác nhau về logging, timeout hoặc external endpoints. Nhưng không nên để source semantics thay đổi âm thầm theo môi trường.

Tách compile-time convention profile khỏi runtime deployment config giúp build reproducible hơn.

## 16. Convention và schema evolution

Khi convention thay đổi, cùng source có thể tạo effective model khác.

Ví dụ pluralization rule đổi từ suffix đơn giản sang dictionary-based. Resource Customer có thể vẫn map như cũ, nhưng resource Person có thể đổi từ /persons sang /people.

### 16.1. Version convention

Convention profile nên có version. Build record cần lưu version đã dùng.

### 16.2. Breaking convention changes

Các thay đổi có thể breaking:
- Đổi naming transformation.
- Đổi route generation.
- Đổi serialization field names.
- Đổi handler discovery precedence.
- Đổi default visibility.
- Đổi default security.
- Đổi type mapping.
- Đổi merge semantics.

### 16.3. Migration report

Tooling có thể so sánh effective model trước và sau khi nâng convention version:
- Generated name changed.
- Route changed.
- Handler binding changed.
- Schema changed.
- Default policy changed.
- Declaration became ambiguous.

### 16.4. Pinning

Project có thể pin convention profile version để tránh thay đổi ngoài ý muốn khi compiler được nâng cấp.

### 16.5. Deprecation

Một convention cũ có thể được deprecated với warning, migration guide và thời điểm loại bỏ rõ ràng.

## 17. Convention trong IDE và developer tooling

IDE cần làm rõ phần nào do người dùng viết và phần nào do convention sinh ra.

### 17.1. Completion

Autocomplete có thể gợi ý declaration tối thiểu và hiển thị default values. Gợi ý phải dựa trên language version và profile hiện tại.

### 17.2. Go to definition

Khi một handler hoặc schema được resolve theo convention, Go to Definition cần mở đúng target và cho biết nó được tìm thấy theo quy tắc nào.

### 17.3. Find usages

Generated symbol cần liên kết ngược về declaration gốc. Nếu không, người dùng khó tìm nơi tạo route, operation ID hoặc handler binding.

### 17.4. Hover và effective value

Hover có thể hiển thị:
- Effective value.
- Convention source.
- Explicit override.
- Inherited configuration.
- Profile version.

### 17.5. Refactoring

Rename declaration có thể làm thay đổi generated names. IDE cần preview các symbol/route/table bị ảnh hưởng trước khi áp dụng.

### 17.6. Quick fixes

Tooling có thể:
- Thêm explicit override.
- Resolve ambiguous binding.
- Tắt convention cho một field.
- Rename declaration để tránh collision.
- Chuyển generated value thành explicit value.

## 18. Testing convention resolution

Convention là logic của compiler nên cần được kiểm tra độc lập.

### 18.1. Unit tests

Kiểm tra từng rule:
- Naming transformation.
- File-to-module mapping.
- Type-to-validator mapping.
- Handler discovery.
- Default value.
- Merge behavior.
- Explicit override.

### 18.2. Precedence tests

Tạo test khi nhiều nguồn cùng khai báo một field và xác nhận nguồn thắng theo specification.

### 18.3. Ambiguity tests

Test:
- Hai handler cùng tên.
- Hai route normalize về cùng path.
- Hai declaration tạo cùng generated symbol.
- Import resolution có nhiều candidate.

### 18.4. Determinism tests

Chạy cùng project với:
- Thứ tự file khác nhau.
- Operating system khác nhau.
- Current directory khác nhau.
- Cache bật/tắt.
- Build sạch và incremental.

Effective model cần giống nhau khi inputs được đặc tả là tương đương.

### 18.5. Golden tests

Lưu effective model hoặc generated artifact làm golden output. Khi convention thay đổi, diff cho thấy chính xác generated values nào bị đổi.

### 18.6. Migration tests

Kiểm tra project cũ khi nâng convention profile và xác nhận migration report phản ánh breaking changes.

## 19. Performance và caching

Convention resolution có thể cần quét module, resolve symbol và tạo generated declarations.

### 19.1. Avoid repeated discovery

Không nên scan toàn project cho mỗi declaration. Có thể tạo index theo namespace, type hoặc naming pattern.

### 19.2. Incremental resolution

Khi một handler được thêm hoặc đổi tên, chỉ những operation phụ thuộc vào convention đó cần resolve lại nếu dependency graph cho phép.

### 19.3. Cache invalidation

Cache key cần bao gồm:
- Source/module identity.
- Convention profile version.
- Project config.
- Dependency graph version.
- Compiler version.
- Relevant environment inputs.

### 19.4. Discovery boundaries

Giới hạn số module và thư mục được scan. Không để convention discovery vô tình trở thành filesystem search không giới hạn.

### 19.5. Explain trace cost

Resolution trace rất hữu ích khi debug nhưng không nhất thiết phải được materialize đầy đủ cho mọi build production. Có thể bật chi tiết theo diagnostic hoặc debug mode.

## 20. Security và trust boundaries

Convention có thể tự động phát hiện implementation hoặc tạo operation. Điều đó làm cho discovery trở thành một phần của security boundary.

### 20.1. Không tự động expose declaration

Một declaration được tìm thấy không đồng nghĩa nó được phép public. Visibility và API exposure cần policy rõ.

### 20.2. Không tự động cấp permission

Handler được bind theo convention không tự động có quyền đọc database, gọi network hoặc truy cập tenant khác.

### 20.3. Trusted roots

Module discovery cần giới hạn trong trusted project roots và xử lý symlink/path traversal an toàn.

### 20.4. Plugin discovery

Không tự động load plugin chỉ vì tên file hoặc class phù hợp convention. Cần registry, trust verification và permission policy.

### 20.5. Secret và environment configuration

Không đưa secret vào generated defaults hoặc documentation. Environment-specific configuration cần secret management và access control phù hợp.

### 20.6. Supply chain

Nếu convention tìm implementation qua dependency packages, cần pin version, verify integrity và tránh resolve dependency không tin cậy ngoài ý muốn.

## 21. Những sai lầm thường gặp

1. **Convention không được tài liệu hóa:** người dùng không biết compiler đã suy ra gì.
2. **Suy luận dựa trên tên quá rộng:** một tên bị dùng để tạo nhiều behavior không liên quan.
3. **Không có explicit override:** trường hợp ngoại lệ phải hack cấu trúc source.
4. **Precedence không rõ:** không biết default, project config hay declaration thắng.
5. **Chọn candidate theo thứ tự filesystem:** build không deterministic.
6. **Không phát hiện collision sau normalization:** hai declaration tạo cùng generated symbol.
7. **Tự động mở public endpoint:** discovery vô tình mở rộng attack surface.
8. **Convention có side effect:** compile phase gọi network hoặc thay đổi trạng thái.
9. **Không version convention:** nâng compiler làm behavior đổi ngoài dự kiến.
10. **Không giải thích effective value:** debug phải đọc implementation.
11. **Quét filesystem không giới hạn:** compile chậm và có thể vượt trust boundary.
12. **Không kiểm tra handler signature:** binding tìm thấy nhưng runtime thất bại.
13. **Merge collection không rõ:** list/map bị replace hoặc append ngoài dự kiến.
14. **Dùng tên field để suy ra security:** field password không tự động được bảo vệ.
15. **Cache thiếu profile version:** build dùng kết quả resolve cũ.
16. **Không có migration report:** generated route hoặc schema đổi mà không được nhận biết.

## 22. Quy trình thiết kế convention cho DSL

Một quy trình thực tế:

1. **Xác định boilerplate lặp lại:** tìm declaration phổ biến mà người dùng thường phải viết cùng cấu trúc.
2. **Chọn convention có giá trị cao:** ưu tiên quy tắc dễ hiểu và có ít trường hợp ngoại lệ.
3. **Định nghĩa input của convention:** tên, path, type, scope hoặc profile nào được dùng.
4. **Viết rule transformation chính xác:** quy định case, pluralization, normalization và collision.
5. **Xác định precedence:** platform, project, module, declaration và default.
6. **Thiết kế explicit override:** hỗ trợ override field và disable convention có kiểm soát.
7. **Bảo đảm determinism:** không dựa vào filesystem order, current directory hoặc environment ngầm.
8. **Định nghĩa diagnostics:** ambiguity, missing target, collision và unsupported shape.
9. **Version convention profile:** ghi version vào build/execution metadata.
10. **Tích hợp IDE:** effective values, Go to Definition, completion và preview refactor.
11. **Kiểm thử:** precedence, collision, ambiguity, deterministic build và migration.
12. **Đánh giá security:** discovery roots, plugin trust, exposure và permissions.
13. **Đo performance:** indexing, incremental resolution và cache invalidation.
14. **Tài liệu hóa:** ví dụ default, override, behavior không được suy ra và cách explain.
15. **Triển khai dần:** bật convention theo profile hoặc opt-in, quan sát diagnostics và migration impact.

## 23. Kết luận

Khai báo theo quy ước giúp DSL ngắn gọn bằng cách suy ra các giá trị phổ biến từ naming, file layout, declaration shape, type hoặc project profile. Nó giảm boilerplate và tạo tính nhất quán, nhưng chỉ đáng tin khi quy tắc được đặc tả rõ, có precedence ổn định, deterministic và có cách override.

Compiler cần phân biệt giá trị explicit, inherited và convention-derived; phát hiện ambiguity/collision; hiển thị effective configuration; và gắn kết quả với version của convention profile. Các hành vi nhạy cảm như public exposure, authorization, plugin loading và side effects cần policy tường minh. Khi convention có diagnostics, tooling, tests và migration support, người viết DSL có thể dùng mặc định thuận tiện mà vẫn hiểu chính xác chương trình sẽ được resolve như thế nào.

