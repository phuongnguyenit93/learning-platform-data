# Tái sử dụng mô hình

Trong một DSL (Domain-Specific Language), nhiều dự án hoặc module thường cần cùng một khái niệm: Money, Address, Customer, Workflow, Policy, Event, API Resource hoặc một nhóm quy tắc nghiệp vụ. Nếu mỗi nơi tự định nghĩa lại các cấu trúc này, hệ thống sẽ có nhiều phiên bản gần giống nhau, khó đồng bộ và dễ phát sinh lỗi tương thích. **Tái sử dụng mô hình (model reuse)** là cách tổ chức các model, type, schema, grammar và thành phần ngôn ngữ để nhiều DSL document hoặc module có thể dùng chung một định nghĩa có kiểm soát.

Tái sử dụng mô hình không chỉ là copy một đoạn khai báo. Nó bao gồm việc xác định ownership, module boundary, import/export, versioning, dependency, extension point và semantics khi nhiều model kết hợp. Một thiết kế tốt giúp người dùng tận dụng model có sẵn, giảm trùng lặp, duy trì một nguồn định nghĩa và vẫn cho phép domain cụ thể mở rộng mà không làm thay đổi contract dùng chung.

## 1. Tái sử dụng mô hình là gì?

Model là biểu diễn có cấu trúc của các khái niệm trong một domain. Tùy DSL, model có thể là:

- Entity và value object.
- Type, enum và function signature.
- Schema request/response hoặc event.
- Workflow, state machine và policy.
- Configuration profile.
- AST/metamodel và grammar fragment.
- Template hoặc code generation rule.
- Constraint, validation rule và reusable expression.

Tái sử dụng mô hình cho phép một định nghĩa được tham chiếu hoặc mở rộng ở nhiều nơi thay vì sao chép.

Ví dụ module dùng chung:

~~~text
module common.money {
    type CurrencyCode
    type Money {
        amount: Decimal
        currency: CurrencyCode
    }
}
~~~

Module bán hàng có thể sử dụng:

~~~text
module sales.order {
    import common.money.Money

    entity Order {
        total: Money
    }
}
~~~

Module hóa đơn cũng dùng cùng type Money. Cả hai module tham chiếu một định nghĩa chung nên semantics về amount và currency được quản lý tại một nơi.

### 1.1. Reuse khác copy-paste

Copy-paste tạo bản sao độc lập. Nếu model gốc thay đổi, mọi bản sao phải được cập nhật riêng. Reuse tạo dependency hoặc composition đến định nghĩa dùng chung, giúp thay đổi có thể được quản lý theo version và compatibility policy.

### 1.2. Reuse khác inheritance

Inheritance là một cơ chế tái sử dụng và chuyên biệt hóa model, nhưng không phải cách duy nhất. Composition, import, delegation, generic types và schema references cũng có thể hỗ trợ reuse.

### 1.3. Reuse phải giữ ownership rõ

Một module cần có owner chịu trách nhiệm cho model public. Nếu nhiều module cùng sửa một định nghĩa không có quy tắc, reuse có thể trở thành nguồn xung đột.

## 2. Vì sao cần tái sử dụng mô hình?

Tái sử dụng model đem lại lợi ích ở nhiều tầng:

- Giảm định nghĩa trùng lặp.
- Thống nhất semantics và validation.
- Chia sẻ schema giữa API, event và runtime.
- Giảm số lượng model phải kiểm thử.
- Giúp các team tích hợp theo contract chung.
- Hỗ trợ generated code và documentation nhất quán.
- Dễ quản lý version và migration.
- Tăng khả năng khám phá các domain concepts có sẵn.

### 2.1. Tránh model drift

Nếu hai module tự định nghĩa Money riêng, một module có thể dùng Decimal, module khác dùng Float; một nơi cho phép âm, nơi khác không. Dù cùng tên, semantics có thể khác nhau. Shared model giảm khả năng drift này.

### 2.2. Tăng tính nhất quán

Một reusable type có thể chứa cùng constraints, formatting và serialization rules. Các consumer dùng nó sẽ có behavior nhất quán hơn.

### 2.3. Giảm chi phí bảo trì

Sửa validation hoặc documentation của một model dùng chung có thể cải thiện nhiều module. Tuy nhiên, thay đổi model public cũng có phạm vi ảnh hưởng lớn hơn, nên cần versioning và review chặt.

### 2.4. Tăng khả năng tương tác

Shared model tạo ngôn ngữ chung giữa bounded contexts hoặc service teams. Cần cẩn trọng để không ép mọi domain dùng cùng một abstraction khi semantics thực sự khác nhau.

## 3. Các cấp độ reuse

Có thể tái sử dụng ở nhiều mức:

| Cấp độ | Thành phần dùng lại | Ví dụ |
|---|---|---|
| Syntax | Grammar fragments, parser rules | QualifiedName, expression syntax |
| Metamodel | EClass, EAttribute, EReference | Common model package |
| Type system | Primitive/domain types | Money, Instant, Identifier |
| Schema | Request, response, event | Address, ErrorEnvelope |
| Domain model | Entity, value object, policy | Customer, OrderStatus |
| Behavior | Function, rule, workflow step | RetryPolicy, validation function |
| Template | Code generation templates | Common DTO mapping |
| Documentation | Reusable concept/reference page | Pagination guide |
| Test assets | Fixture, assertion helper | Shared parser test corpus |

### 3.1. Syntax reuse

Grammar fragment dùng chung giúp nhiều DSL có cùng cú pháp identifier, literal hoặc expression. Tuy nhiên, syntax reuse cần tránh coupling quá chặt giữa grammar của các domain khác nhau.

### 3.2. Metamodel reuse

Nhiều language module có thể tham chiếu cùng Ecore package hoặc metamodel. Cần quản lý namespace URI, package version và class identity ổn định.

### 3.3. Type/schema reuse

Một type như Money hoặc Address có thể được dùng trong nhiều operation, event và entity. Schema reuse cần quy định nullability, serialization và compatibility.

### 3.4. Behavioral reuse

Một function hoặc rule có thể dùng lại qua library/module. Cần xác định purity, side effects, authorization và runtime dependencies.

## 4. Module và package boundary

Model reuse thường được tổ chức qua module hoặc package. Module là đơn vị đặt tên, version, export và dependency.

Ví dụ:

~~~text
workspace/
├── common/
│   ├── identifiers.dsl
│   ├── money.dsl
│   └── address.dsl
├── sales/
│   └── order.dsl
└── billing/
    └── invoice.dsl
~~~

### 4.1. Cohesion

Các model trong một module nên có quan hệ domain rõ ràng. Module chứa mọi thứ dùng chung có thể trở thành package khổng lồ khó version và review.

### 4.2. Coupling

Consumer chỉ nên phụ thuộc vào public model cần thiết. Import cả module lớn làm tăng coupling và khiến thay đổi nội bộ ảnh hưởng nhiều nơi.

### 4.3. Public và internal models

Module có thể phân biệt export/public declarations với internal implementation details. Public model cần compatibility policy; internal model có thể thay đổi tự do hơn trong giới hạn module.

### 4.4. Bounded contexts

Trong domain-driven design, cùng một khái niệm có thể có nghĩa khác nhau giữa các bounded context. Không nên ép Sales.Order và Shipping.Order dùng chung một model nếu lifecycle, invariants và ownership khác nhau. Có thể chia sẻ primitive hoặc identifier nhưng giữ domain model riêng.

### 4.5. Shared kernel

Một shared kernel là tập model nhỏ được nhiều domain cùng sở hữu và thay đổi có phối hợp. Nó cần governance rõ vì thay đổi ảnh hưởng đồng thời nhiều nhóm.

## 5. Import, export và namespace

DSL cần cú pháp để một module sử dụng model của module khác.

Ví dụ:

~~~text
module sales.order

import common.money.Money
import common.address.Address

entity Order {
    total: Money
    shippingAddress: Address
}
~~~

### 5.1. Explicit imports

Import tường minh giúp người đọc thấy dependency và tránh đưa quá nhiều tên vào scope.

### 5.2. Wildcard imports

Wildcard import tiện khi module có nhiều type, nhưng có thể gây name collision và làm khó tìm nguồn symbol. Nên giới hạn hoặc hỗ trợ tooling hiển thị origin.

### 5.3. Aliases

Alias giúp tránh xung đột:

~~~text
import crm.Customer as CRMCustomer
import billing.Customer as BillingCustomer
~~~

Alias là tên cục bộ; symbol identity vẫn trỏ đến declaration gốc.

### 5.4. Re-export

Một module có thể export lại type từ dependency để cung cấp facade API. Cần ghi rõ origin và tránh vô tình biến dependency implementation thành public contract.

### 5.5. Qualified names

Qualified name như common.money.Money giúp định danh ổn định. Naming convention cần nhất quán và tránh phụ thuộc file path nếu file có thể đổi vị trí.

### 5.6. Name collision

Nếu hai module export cùng tên, resolver cần quy tắc rõ: yêu cầu qualified name, alias hoặc báo ambiguity. Không nên chọn ngẫu nhiên theo thứ tự dependency.

## 6. Composition thay cho inheritance

Composition kết hợp các model bằng cách chứa hoặc tham chiếu thành phần khác.

Ví dụ:

~~~text
type ContactInfo {
    email: EmailAddress
    phone: PhoneNumber?
}

entity Customer {
    id: CustomerId
    contact: ContactInfo
}
~~~

### 6.1. Ưu điểm của composition

- Giữ các model thành phần độc lập.
- Có thể dùng một value object ở nhiều entity.
- Tránh hierarchy sâu.
- Giảm ràng buộc giữa các domain.
- Dễ mở rộng bằng cách thêm component.

### 6.2. Composition và containment

Containment nghĩa là một model sở hữu object con. Reference nghĩa là liên kết đến object khác có identity độc lập. DSL cần phân biệt hai trường hợp vì serialization và lifecycle khác nhau.

### 6.3. Optional components

Một component có thể optional. Cần phân biệt không có component, component rỗng và component có giá trị null.

### 6.4. Composition conflicts

Nếu hai component có field trùng tên hoặc constraints xung đột, DSL cần quy tắc resolution hoặc yêu cầu namespace riêng.

## 7. Inheritance và model specialization

Inheritance cho phép model con kế thừa thuộc tính và behavior từ model cha.

Ví dụ:

~~~text
entity Person {
    id: PersonId
    name: String
}

entity Employee extends Person {
    employeeNumber: String
    department: Department
}
~~~

### 7.1. Khi nào inheritance phù hợp?

Dùng inheritance khi model con thực sự là một dạng của model cha và có thể thay thế nó trong mọi context mà contract cho phép.

### 7.2. Liskov substitution

Nếu DSL hỗ trợ subtype, consumer dùng base type không nên bị phá khi nhận subtype. Constraints của subtype không nên làm vô hiệu các assumption hợp lệ của base contract.

### 7.3. Multiple inheritance

Multiple inheritance có thể tạo diamond problem khi hai parent định nghĩa cùng field hoặc behavior. Cần quy định precedence, conflict resolution hoặc hạn chế chỉ cho phép single inheritance.

### 7.4. Abstract model

Base model có thể abstract và không được instantiate trực tiếp. Tài liệu và validator cần chỉ rõ điều kiện.

### 7.5. Inherited constraints

Constraint của parent thường áp dụng cho child. Child có thể bổ sung constraint; việc nới lỏng hoặc thay thế constraint cần semantics rõ để không phá substitutability.

### 7.6. Không lạm dụng inheritance

Nếu quan hệ chỉ là “có một” hoặc chia sẻ vài field, composition thường đơn giản và linh hoạt hơn. Hierarchy sâu làm khó hiểu model và migration.

## 8. Generic types và reusable templates

Generic cho phép định nghĩa model tổng quát với tham số kiểu.

Ví dụ:

~~~text
type Page<T> {
    items: T[]
    nextCursor: String?
}

type Result<T, E> {
    value: T?
    error: E?
}
~~~

Consumer có thể dùng Page<Order>, Page<Customer> hoặc Result<Invoice, ApiError>.

### 8.1. Type parameters

Generic parameter cần có scope và identity riêng. Không nên trộn generic parameter với type có cùng tên trong module ngoài.

### 8.2. Constraints

Có thể giới hạn type parameter:

~~~text
type Repository<T where T extends Entity> {
    findById(id: T.Id): T?
}
~~~

Constraint cho biết operations nào hợp lệ trên T.

### 8.3. Variance

Nếu DSL hỗ trợ generic subtyping, cần xác định covariance, contravariance hoặc invariance. Ví dụ List<Dog> có được dùng ở nơi cần List<Animal> hay không phụ thuộc variance contract.

### 8.4. Type inference

Generic arguments có thể được suy ra từ context. Documentation và diagnostics cần cho biết khi nào inference thành công và cách chỉ định type tường minh nếu mơ hồ.

### 8.5. Template instantiation

Generator có thể tạo code riêng cho từng type argument hoặc dùng generic target language. Cần kiểm tra output size, caching và naming collisions.

## 9. Reusable functions, rules và behaviors

Ngoài data model, DSL có thể tái sử dụng function, validator hoặc policy.

Ví dụ:

~~~text
library common.validation {
    function isNonBlank(value: String): Boolean {
        return trim(value) != ""
    }

    rule validEmail(email: EmailAddress) {
        require matches(email, EMAIL_PATTERN)
    }
}
~~~

### 9.1. Pure functions

Pure function không có side effects và cùng input tạo cùng output. Chúng dễ reuse, cache và test.

### 9.2. Stateful behavior

Behavior có state hoặc side effects cần khai báo dependency và lifecycle. Không nên dùng library function như thể pure nếu nó gọi network hoặc cập nhật database.

### 9.3. Rule composition

Nhiều rule có thể kết hợp bằng all/any/not hoặc import. Cần xác định short-circuit behavior và thứ tự evaluation nếu rule có thể tạo diagnostic.

### 9.4. Policy reuse

Policy như requireMfa hoặc restrictExport có thể được tái sử dụng, nhưng cần context parameters và versioning. Policy security-critical không nên bị consumer override tùy ý.

### 9.5. Runtime dependencies

Reusable behavior có thể phụ thuộc service hoặc capability. Module metadata nên khai báo dependency để compiler và deployment tool kiểm tra.

## 10. Reuse grammar và parser components

Một số DSL chia sẻ cú pháp cơ bản như qualified name, literal, annotation hoặc expression.

### 10.1. Grammar composition

Parser rule có thể được import hoặc extend từ grammar module dùng chung. Cần bảo đảm rule name và terminal rules không xung đột.

### 10.2. Terminal rules

Các terminal như identifier, integer và string có thể dùng chung. Thay đổi identifier rules có thể ảnh hưởng mọi DSL consumer, vì vậy cần versioning.

### 10.3. Expression grammar

Expression grammar có precedence và associativity phức tạp. Reuse expression fragment cần giữ cùng semantics và diagnostics.

### 10.4. Extension points

Một grammar base có thể cung cấp extension points để domain DSL bổ sung keyword hoặc statement. Cần giới hạn extension để không tạo ambiguity.

### 10.5. Parser compatibility

Nếu grammar base thay đổi, parser của các DSL con cần regenerate và chạy compatibility tests. Không nên cập nhật grammar fragment mà không kiểm tra downstream language modules.

## 11. Reuse metamodel và Ecore

Trong framework modeling, metamodel có thể được chia thành package độc lập và tham chiếu qua EReference.

Ví dụ khái niệm:

~~~text
common.ecore
├── Identifier
├── Money
└── Address

sales.ecore
└── Order
    ├── id: Identifier
    ├── total: Money
    └── shippingAddress: Address
~~~

### 11.1. Namespace URI

EPackage thường có namespace URI. URI và classifier identity cần ổn định để resource đã serialize có thể load đúng.

### 11.2. EReference

Cross-package EReference liên kết classifier giữa các package. Cần xác định containment, proxy resolution và resource loading.

### 11.3. Package versioning

Thay đổi EClass, EAttribute hoặc multiplicity có thể làm dữ liệu XMI cũ không tương thích. Metamodel version và migration strategy cần được quản lý.

### 11.4. Generated model code

Nếu Ecore sinh Java classes, consumer cần dùng đúng generated package version. Không sửa generated class trực tiếp; thay đổi source metamodel rồi regenerate.

### 11.5. ResourceSet và package registry

Runtime cần đăng ký các package được dùng và resolve resource đúng. Test nhiều module nên kiểm tra package registry, URI mapping và proxy resolution.

## 12. Reusable schemas cho API và event

Một type có thể được chia sẻ giữa request, response và event schema.

Ví dụ:

~~~text
schema Address {
    line1: String
    city: String
    postalCode: String?
}

operation createCustomer {
    request {
        name: String
        address: Address
    }
}

event CustomerCreated {
    customerId: CustomerId
    address: Address
}
~~~

### 12.1. Shared schema ownership

Schema dùng chung cần owner và version. Thay đổi một field có thể ảnh hưởng nhiều API/event consumers.

### 12.2. Read/write models

API có thể dùng command model để nhận input và read model để trả output. Không nhất thiết dùng một entity model cho cả hai nếu semantics khác nhau.

### 12.3. Schema references

Generated OpenAPI/AsyncAPI có thể dùng component references để tái sử dụng schema. Cần kiểm tra reference không bị dangling và không tạo vòng lặp không hỗ trợ.

### 12.4. Event payload compatibility

Event đã phát có thể được lưu lâu. Shared schema cần compatibility rules để consumer cũ vẫn đọc được event cũ.

### 12.5. Serialization

Cùng model có thể được serialize theo JSON, XML hoặc binary format. Cần xác định naming, nullability, default và unknown field handling cho từng format.

## 13. Model libraries và package management

Khi model được chia sẻ giữa nhiều repository, cần cách phân phối và version dependency.

### 13.1. Package identity

Mỗi package nên có tên duy nhất, owner, version, source repository và metadata. Không nên chỉ định danh package bằng file path local.

### 13.2. Semantic versioning

Có thể dùng MAJOR.MINOR.PATCH:

- MAJOR: thay đổi không tương thích.
- MINOR: thêm model hoặc capability tương thích.
- PATCH: sửa lỗi không phá contract.

Đối với model DSL, xóa field, đổi type, thu hẹp enum hoặc thay constraint có thể là breaking change.

### 13.3. Version ranges

Consumer có thể khai báo version chính xác hoặc range. Range quá rộng làm build không tái lập; range quá hẹp làm cập nhật khó. Cần lockfile hoặc dependency resolution report.

### 13.4. Dependency lock

Lockfile ghi phiên bản package đã resolve để local và CI dùng cùng model. Khi cập nhật dependency, cần review diff và chạy compatibility tests.

### 13.5. Private registries

Model nội bộ có thể được phân phối qua registry riêng. Access token và package signing cần được quản lý an toàn.

### 13.6. Reproducible resolution

Cùng manifest và registry state cần resolve cùng dependency set. Tránh dependency dynamic version không được khóa trong release build.

## 14. Dependency graph và chu trình

Các model module tạo thành dependency graph.

~~~text
common.types
    ^       ^
    |       |
sales.order billing.invoice
    ^       ^
    |       |
fulfillment shipping
~~~

### 14.1. Directed dependencies

Nếu module A import B, A phụ thuộc vào B. Dependency graph giúp xác định build order, impact analysis và package closure.

### 14.2. Circular dependencies

A import B và B import A có thể gây khó khăn cho loading, versioning và compilation. Nên tách shared abstraction vào module thứ ba hoặc dùng interface boundary.

### 14.3. Dependency inversion

Module domain không nên phụ thuộc trực tiếp vào implementation detail của infrastructure. Có thể định nghĩa contract ở module ổn định rồi adapter triển khai.

### 14.4. Transitive dependencies

Nếu A dùng B và B dùng C, cần quyết định A có thể thấy C hay phải import trực tiếp. Explicit dependency giúp ownership và compatibility rõ hơn.

### 14.5. Dependency minimization

Import package lớn chỉ để dùng một type nhỏ làm tăng coupling. Có thể tách package core types nhỏ, nhưng không nên chia module quá vụn làm khó quản lý.

## 15. Conflict resolution và diamond dependencies

Khi nhiều module cung cấp cùng tên hoặc cùng version của một model, compiler cần quy tắc rõ.

### 15.1. Name collision

Hai package có thể export type Customer. Consumer cần qualified import hoặc alias.

### 15.2. Diamond dependency

Module A và B cùng phụ thuộc package C nhưng yêu cầu version khác nhau. Package manager cần resolve một version tương thích hoặc báo conflict.

### 15.3. Multiple definitions

Nếu hai model cùng qualified name được load từ hai artifact khác nhau, không nên chọn một cách âm thầm. Compiler cần báo duplicate identity hoặc yêu cầu dependency resolution rõ ràng.

### 15.4. Override policy

Một số DSL cho phép module override default model hoặc configuration. Cần phân biệt override có chủ đích với duplicate declaration.

### 15.5. Deterministic resolution

Kết quả resolve không nên phụ thuộc thứ tự file hoặc thứ tự scan filesystem. Resolution cần deterministic để build tái lập.

## 16. Extension và customization

Model dùng chung đôi khi cần mở rộng cho domain cụ thể mà không sửa package gốc.

### 16.1. Extension fields

Có thể dùng extension model hoặc metadata:

~~~text
extend Customer with SalesCustomerInfo {
    salesRegion: Region
}
~~~

Cần xác định extension được lưu trong model gốc hay sidecar model, và cách serialize.

### 16.2. Annotation

Annotation có thể bổ sung metadata như display label, validation hint hoặc generation option mà không thay đổi core structure.

### 16.3. Decorator pattern

Một model wrapper có thể bổ sung behavior hoặc metadata cho model gốc. Tooling cần hiển thị đúng origin và tránh nhầm wrapper với identity gốc.

### 16.4. Extension compatibility

Extension có thể bị phá khi base model đổi. API cần quy định extension points ổn định và test các extension consumer.

### 16.5. Không sửa trực tiếp shared model

Nếu một domain cần semantics khác, nên tạo specialization hoặc adapter thay vì sửa model dùng chung theo nhu cầu cục bộ.

## 17. Model transformations và mapping

Các domain có thể dùng model riêng và chuyển đổi qua adapter hoặc mapping.

Ví dụ:

~~~text
CRM.Customer
      |
      v
CustomerMapping
      |
      v
Sales.CustomerProfile
~~~

### 17.1. Anti-corruption layer

Một mapping layer bảo vệ domain khỏi semantics của model bên ngoài. Điều này hữu ích khi tích hợp hệ thống cũ hoặc package third-party.

### 17.2. Explicit mapping

Mapping nên nêu field nguồn, field đích, conversion và behavior khi thiếu dữ liệu. Tránh mapping ngầm dựa trên tên field nếu có thể gây nhầm.

### 17.3. Lossy transformations

Nếu target model không biểu diễn đầy đủ source model, cần ghi rõ dữ liệu bị bỏ hoặc chuyển thành extension metadata. Không nên coi mapping là lossless nếu không đúng.

### 17.4. Mapping validation

Có thể kiểm tra mọi required target field được cấp giá trị, enum được map đầy đủ và conversion không mất precision.

### 17.5. Round-trip mapping

Nếu yêu cầu chuyển qua lại, test source→target→source có bảo toàn thông tin không. Không phải mọi mapping đều round-trip được.

## 18. Versioning và evolution của shared models

Shared model có nhiều consumer nên thay đổi cần có kế hoạch.

### 18.1. Additive changes

Thêm optional field thường ít rủi ro hơn xóa hoặc đổi kiểu field. Tuy nhiên, consumer có strict schema validation có thể từ chối field mới; cần kiểm tra compatibility thực tế.

### 18.2. Rename

Rename có thể cần alias tạm thời, deprecated field hoặc migration tool cập nhật references. Không nên đổi tên mà không cung cấp đường chuyển.

### 18.3. Type changes

Đổi String sang Identifier hoặc Integer sang Decimal cần conversion rule, validation và data migration.

### 18.4. Constraint changes

Tăng minimum length, thu hẹp enum hoặc thêm required constraint có thể khiến dữ liệu cũ không hợp lệ dù schema shape không đổi.

### 18.5. Deprecation lifecycle

Model/field có thể đi qua supported, deprecated, migration available và removed. Diagnostic cần chỉ ra replacement và version loại bỏ.

### 18.6. Compatibility matrix

Với compiler, runtime và model package độc lập version, cần công bố tổ hợp được hỗ trợ. Package manager có thể kiểm tra compatibility trước khi build.

## 19. Tài liệu hóa reusable models

Model dùng chung cần tài liệu giải thích ownership, semantics và cách sử dụng.

Một trang model reference nên gồm:

- Tên và qualified name.
- Package/module và owner.
- Mục đích domain.
- Fields, types, requiredness và constraints.
- Invariants và lifecycle.
- Examples.
- Serialization behavior.
- Dependencies.
- Version và compatibility.
- Deprecated members và migration path.

### 19.1. Example-driven docs

Ví dụ sử dụng model trong nhiều context giúp consumer hiểu model được dùng như thế nào và giới hạn ở đâu.

### 19.2. Ownership metadata

Có thể ghi owner team, contact hoặc repository. Khi model có vấn đề, người dùng biết nơi gửi issue.

### 19.3. Generated reference

Documentation generator có thể tạo bảng fields và type references từ metamodel. Prose vẫn cần giải thích semantics không thể suy ra từ cấu trúc.

### 19.4. Discoverability

IDE completion, hover, symbol search và catalog giúp người dùng tìm model hiện có trước khi tạo một model mới.

## 20. Testing cho model reuse

Reuse làm tăng phạm vi ảnh hưởng, nên test cần bao phủ cả model gốc và consumer.

Các nhóm test:

1. Model package parse và validate độc lập.
2. Import/export và qualified name resolution.
3. Shared type được dùng ở nhiều module.
4. Inheritance và composition.
5. Generic constraints và variance nếu có.
6. Dependency resolution và version conflicts.
7. Cycle detection.
8. Extension compatibility.
9. Schema serialization/deserialization.
10. Model migration giữa version.
11. Mapping và lossless/lossy transformations.
12. Generated code compilation.
13. Documentation examples.
14. Incremental build và cache invalidation.

### 20.1. Consumer contract tests

Một shared package nên có test consumer đại diện để xác nhận public model đủ dùng và không phụ thuộc internal details.

### 20.2. Compatibility tests

Chạy consumer fixtures cũ với package mới để phát hiện breaking changes. Có thể dùng schema diff hoặc compiler diagnostics.

### 20.3. Dependency graph tests

Kiểm tra không có circular dependency, version conflict hoặc transitive dependency ngoài policy.

### 20.4. Serialization tests

Lưu model bằng version cũ rồi load bằng version mới để xác nhận migration/upcasting. Kiểm tra cả unknown fields và optional fields.

### 20.5. Performance tests

Một shared model graph lớn có thể làm loading và linking chậm. Benchmark resource count, resolution time và memory khi cần.

## 21. Security và trust boundary

Model package có thể chứa metadata, code generation templates hoặc plugin. Không nên xem mọi dependency là đáng tin chỉ vì nó được import.

Các biện pháp:

- Chỉ dùng registry/source được phê duyệt.
- Pin version và verify checksum/signature.
- Review generator/template code có khả năng thực thi.
- Giới hạn quyền plugin và extension.
- Không nhúng secret vào model package.
- Kiểm soát external schema references.
- Validate package metadata và dependency graph.
- Theo dõi vulnerability và license của dependency.
- Audit thay đổi public model quan trọng.

### 21.1. Untrusted model definitions

Parser nên xử lý model source như dữ liệu. Nếu DSL có macro/plugin, execution cần sandbox và quyền rõ ràng.

### 21.2. Supply chain

Shared model package có thể ảnh hưởng nhiều sản phẩm. Signing, provenance và immutable releases giúp xác định nguồn và nội dung package.

### 21.3. Data exposure

Một model dùng chung có thể vô tình đưa field nhạy cảm vào API hoặc log. Schema classification và serialization policy cần được áp dụng tại boundary.

## 22. Ví dụ tổng hợp: shared model cho nhiều domain

Một workspace có ba module:

~~~text
common.identity
common.money
sales.orders
billing.invoices
~~~

Shared identity:

~~~text
module common.identity {
    type CustomerId = Identifier
    type Address {
        line1: String
        city: String
        postalCode: String?
    }
}
~~~

Shared money:

~~~text
module common.money {
    type CurrencyCode
    type Money {
        amount: Decimal
        currency: CurrencyCode
    }
}
~~~

Sales:

~~~text
module sales.orders {
    import common.identity.CustomerId
    import common.identity.Address
    import common.money.Money

    entity Order {
        id: OrderId
        customerId: CustomerId
        shippingAddress: Address
        total: Money
    }
}
~~~

Billing:

~~~text
module billing.invoices {
    import common.identity.CustomerId
    import common.money.Money

    entity Invoice {
        customerId: CustomerId
        amountDue: Money
    }
}
~~~

### 22.1. Lợi ích

Sales và Billing dùng cùng định nghĩa CustomerId và Money. Validation, serialization và documentation có thể được quản lý tập trung.

### 22.2. Ranh giới domain

Sales.Order và Billing.Invoice vẫn là model riêng vì chúng có lifecycle và invariants khác nhau. Reuse chỉ áp dụng cho khái niệm thực sự chung.

### 22.3. Thay đổi shared model

Nếu Money thêm currency precision rule, cả hai consumer cần chạy compatibility tests. Nếu thay đổi là breaking, có thể phát common.money v2 và cho consumer nâng cấp theo lịch riêng.

## 23. Những lỗi thiết kế thường gặp

| Sai lầm | Hậu quả | Cách khắc phục |
|---|---|---|
| Copy model vào nhiều module | Model drift và duplicate fixes | Dùng shared package có owner |
| Tạo một common module khổng lồ | Coupling và release blast radius lớn | Chia theo domain cohesion |
| Reuse model khác semantics | Consumer hiểu sai invariants | Giữ bounded context riêng |
| Dùng inheritance cho mọi reuse | Hierarchy sâu và khó thay đổi | Ưu tiên composition khi phù hợp |
| Wildcard import quá rộng | Name collision và khó trace origin | Explicit import/alias |
| Không version shared package | Consumer build không tái lập | Semantic version và lockfile |
| Cho phép circular imports | Loading/build khó xác định | Tách abstraction và kiểm tra graph |
| Không xử lý diamond conflicts | Resolve type phụ thuộc thứ tự | Deterministic dependency resolution |
| Override model gốc tùy tiện | Consumer khác bị thay đổi behavior | Extension point và ownership |
| Không test serialization compatibility | Dữ liệu cũ không load được | Versioned schema tests |
| Chỉ test model riêng lẻ | Consumer integration bị hỏng | Consumer contract tests |
| Export internal details | Public API khó thay đổi | Public/internal visibility |

## 24. Nguyên tắc thiết kế tái sử dụng mô hình

Khi xây dựng model reuse cho DSL, có thể áp dụng các nguyên tắc sau:

1. **Chia sẻ khái niệm thực sự chung.** Không ép các bounded contexts dùng chung model chỉ vì tên giống nhau.
2. **Đặt module boundary theo domain cohesion.** Package nên có trách nhiệm và owner rõ.
3. **Dùng import/export tường minh.** Qualified names và aliases giúp resolution dễ hiểu.
4. **Ưu tiên composition cho quan hệ has-a.** Dùng inheritance khi subtype có thể thay thế base contract.
5. **Hỗ trợ generic có kiểm soát.** Type constraints và variance cần semantics rõ.
6. **Giữ public model nhỏ và ổn định.** Không export implementation details.
7. **Quản lý dependency graph.** Phát hiện cycle, conflict và dependency thừa.
8. **Version hóa package.** Pin dependency và công bố compatibility.
9. **Có extension points.** Cho phép domain specialization mà không sửa shared source.
10. **Dùng mapping khi domain khác nhau.** Anti-corruption layer bảo vệ semantics.
11. **Kiểm tra serialization và migration.** Model reuse thường tồn tại lâu hơn một release.
12. **Test cả consumer.** Public model cần được kiểm tra qua các module sử dụng.
13. **Tài liệu hóa ownership và semantics.** Người dùng biết nên import gì và ai quản lý.
14. **Bảo vệ supply chain.** Verify nguồn package, signature và quyền plugin.
15. **Theo dõi phạm vi ảnh hưởng.** Thay đổi shared model cần impact analysis.

## 25. Kết luận

Tái sử dụng mô hình giúp nhiều module DSL dùng chung type, schema, entity, behavior và metamodel mà không phải tạo bản sao độc lập. Reuse có thể được thực hiện qua import/export, composition, inheritance, generic types, library functions, grammar fragments và package dependencies. Mỗi cách có semantics và trade-off riêng.

Một thiết kế bền vững cần module boundary hợp lý, ownership rõ, dependency graph không chu trình, resolution deterministic, versioning và compatibility policy. Với shared model public, cần kiểm tra consumer, serialization, migration và generated output trước khi phát hành thay đổi. Khi các domain có semantics khác nhau, mapping hoặc adapter thường an toàn hơn việc ép chúng vào một model chung.

Khi model reuse được quản lý như một contract có version và test, DSL giảm trùng lặp, tăng tính nhất quán và cho phép các nhóm phát triển độc lập trên nền tảng khái niệm dùng chung.
