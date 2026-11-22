# Tính linh hoạt

Trong thiết kế ngôn ngữ chuyên biệt miền (Domain-Specific Language, DSL), **tính linh hoạt (flexibility)** là khả năng cho phép người dùng biểu diễn nhiều trường hợp nghiệp vụ, thích ứng với thay đổi và mở rộng cách sử dụng mà không phải sửa toàn bộ nền tảng DSL. Một DSL linh hoạt có thể hỗ trợ cấu hình theo môi trường, extension, plugin, custom rule, type mới hoặc những biến thể của cùng một workflow. Tuy nhiên, càng mở rộng quyền tùy biến thì ngôn ngữ càng có nguy cơ khó học, khó kiểm tra, khó tối ưu và khó bảo đảm tính nhất quán.

Ví dụ, một DSL triển khai có thể cho phép khai báo service theo một cấu trúc chuẩn:

~~~text
service orderApi {
    replicas = 3
    port = 8080
}
~~~

Nếu mọi project đều phải dùng đúng cấu trúc này, DSL dễ học và dễ validate nhưng có thể không đáp ứng các trường hợp đặc biệt. Nếu DSL cho phép người dùng viết bất kỳ script nào để cấu hình service, khả năng biểu đạt tăng lên nhưng compiler khó phân tích, tooling khó hỗ trợ và việc thực thi có thể tạo rủi ro. Một thiết kế tốt tìm điểm cân bằng: cung cấp cấu trúc khai báo đủ mạnh cho phần lớn use case, có extension point được kiểm soát và chỉ mở escape hatch khi thật sự cần.

Tính linh hoạt không phải một thuộc tính đơn lẻ. Nó gồm linh hoạt về cú pháp, semantics, type system, configuration, composition, extension, runtime behavior, platform và lifecycle. Mỗi chiều có chi phí riêng. Thiết kế DSL cần xác định ai được tùy biến, tùy biến ở đâu, mức nào được hỗ trợ và những invariant nào phải luôn được giữ.

## 1. Tính linh hoạt trong DSL là gì?

Một DSL linh hoạt cho phép cùng một mô hình ngôn ngữ đáp ứng các nhu cầu khác nhau mà vẫn giữ được semantics có thể hiểu và kiểm tra.

### 1.1. Khả năng biểu đạt

Người dùng có thể mô tả nhiều trường hợp nghiệp vụ bằng những construct phù hợp. Ngôn ngữ quá hạn chế khiến họ phải dùng workaround hoặc rời khỏi DSL.

### 1.2. Khả năng tùy biến

Người dùng có thể thay đổi giá trị, policy, profile, template hoặc hành vi ở những điểm được thiết kế để cấu hình.

### 1.3. Khả năng mở rộng

Nhóm phát triển hoặc plugin author có thể thêm type, function, provider, rule hoặc backend mà không phải fork toàn bộ compiler.

### 1.4. Khả năng kết hợp

Các construct nhỏ có thể ghép thành module, workflow, rule set hoặc component lớn. Composition giúp DSL mở rộng bằng cách kết hợp những thành phần có sẵn.

### 1.5. Khả năng thích ứng

DSL có thể hỗ trợ nhiều environment, platform, version và tổ chức với các constraint khác nhau.

### 1.6. Giới hạn của linh hoạt

Một cấu hình tùy biến quá rộng có thể làm behavior khó dự đoán. Tính linh hoạt có giá trị khi người dùng vẫn hiểu được kết quả và công cụ vẫn kiểm tra được các invariant quan trọng.

## 2. Vì sao DSL cần tính linh hoạt?

Domain thực tế hiếm khi chỉ có một trường hợp chuẩn. DSL cần đáp ứng khác biệt giữa project mà không làm ngôn ngữ phình to không kiểm soát.

### 2.1. Khác biệt giữa các project

Hai project cùng dùng một DSL có thể khác số lượng service, quy tắc bảo mật, naming convention và deployment target.

### 2.2. Khác biệt giữa environment

Development có thể dùng mock service và ít replica; production cần secret, autoscaling và policy nghiêm ngặt. Profile giúp biểu diễn khác biệt mà không nhân bản toàn bộ source.

### 2.3. Tiến hóa nghiệp vụ

Rule và workflow có thể thay đổi theo tổ chức, sản phẩm hoặc regulation. Extension point cho phép thích ứng mà không sửa core language cho mọi thay đổi nhỏ.

### 2.4. Tích hợp hệ thống hiện có

Một DSL có thể cần kết nối với database, broker, cloud provider hoặc legacy API. Adapter và plugin giúp mở rộng integration.

### 2.5. Nhu cầu của người dùng khác nhau

Người mới có thể cần default và high-level construct; chuyên gia có thể cần control chi tiết. DSL có thể cung cấp nhiều mức trừu tượng trên cùng model.

### 2.6. Tránh fork

Nếu không có extension mechanism, mỗi nhóm có thể tạo một phiên bản DSL riêng. Điều này làm phân mảnh tooling, documentation và compatibility.

### 2.7. Đổi mới có kiểm soát

Một extension API ổn định cho phép thử nghiệm feature mới bên ngoài core và đưa vào ngôn ngữ khi đã chứng minh giá trị.

## 3. Các chiều của tính linh hoạt

Có thể phân tích flexibility theo những chiều khác nhau thay vì chỉ hỏi DSL có “mở” hay không.

| Chiều | Câu hỏi thiết kế | Cơ chế thường dùng |
|---|---|---|
| Syntax | Người dùng có thể viết theo những dạng nào? | Grammar, aliases, macros |
| Semantics | Có thể tùy biến behavior đến đâu? | Rules, policies, functions |
| Types | Có thể mở rộng type system không? | Custom types, constraints |
| Configuration | Có thể thay đổi theo context nào? | Profiles, variables |
| Composition | Có thể ghép construct thế nào? | Modules, imports, templates |
| Extension | Có thể thêm capability mới không? | Plugins, providers |
| Runtime | Có thể chọn execution behavior nào? | Strategies, adapters |
| Platform | Có thể target nhiều môi trường không? | Backends, target profiles |
| Lifecycle | Có thể tiến hóa mà không phá consumer không? | Versioning, migration |

### 3.1. Syntax flexibility

Alias, shorthand, custom operator hoặc macro có thể làm cú pháp tiện hơn. Tuy nhiên, nhiều cách viết cho cùng một ý tưởng làm tài liệu và formatter phức tạp.

### 3.2. Semantic flexibility

Policy hoặc function cho phép thay đổi cách hệ thống xử lý. Đây là chiều mạnh nhưng cần type checking, determinism và security boundary.

### 3.3. Type flexibility

Custom type giúp mô hình hóa domain riêng. Nếu type system quá mở hoặc cho phép coercion tùy ý, lỗi có thể chỉ xuất hiện ở runtime.

### 3.4. Configuration flexibility

Variable, profile và override hỗ trợ nhiều environment. Cần quy định precedence và nguồn giá trị.

### 3.5. Extension flexibility

Plugin và provider cho phép thêm năng lực mà không thay core. Cần API compatibility và permission model.

### 3.6. Runtime flexibility

Có thể chọn retry strategy, concurrency policy hoặc transport. Những lựa chọn cần có default an toàn và contract rõ.

## 4. Đánh đổi giữa linh hoạt và đơn giản

Tăng số lựa chọn làm tăng khả năng đáp ứng nhưng cũng tăng chi phí học, cấu hình và vận hành.

### 4.1. Cognitive load

Người dùng phải hiểu nhiều option, precedence và tương tác. DSL có quá nhiều cách biểu đạt một việc khiến người dùng khó chọn.

### 4.2. Configuration surface

Mỗi option mới cần documentation, validation, default, test và compatibility policy. Nhiều option ít dùng có thể làm hệ thống khó bảo trì.

### 4.3. Predictability

Cấu hình càng động, behavior càng phụ thuộc context. Người dùng cần biết chính xác giá trị cuối cùng được resolve như thế nào.

### 4.4. Discoverability

Feature tùy biến cần được IDE, help và documentation khám phá. Extension không có metadata tốt có thể tồn tại nhưng người dùng không biết.

### 4.5. Debuggability

Khi behavior được tạo từ nhiều layer override, tìm nguồn giá trị cuối cùng khó hơn. Tool cần explain configuration và show effective model.

### 4.6. Learning curve

Một DSL có cấu trúc chuẩn giúp người mới bắt đầu nhanh. Escape hatch và extension có thể dành cho trường hợp nâng cao thay vì bắt mọi người học ngay.

### 4.7. Thiết kế progressive disclosure

Hiển thị lựa chọn phổ biến trước, cho phép mở rộng khi cần. Default và high-level construct xử lý phần lớn use case; advanced configuration chỉ xuất hiện ở nơi có nhu cầu thực.

## 5. Thiết kế DSL theo mức trừu tượng

Một cách tạo flexibility là cung cấp nhiều mức abstraction trên cùng semantics.

~~~mermaid
flowchart TD
    A[High-level DSL construct] --> B[Reusable domain component]
    B --> C[Typed intermediate model]
    C --> D[Platform adapter]
    D --> E[Target implementation]
    F[Advanced extension] --> C
~~~

### 5.1. High-level construct

Người dùng khai báo ý định nghiệp vụ thay vì chi tiết triển khai. Ví dụ khai báo service có health check thay vì tự viết toàn bộ probe resource.

### 5.2. Domain component

Component tái sử dụng gom nhiều khai báo liên quan. Người dùng có thể dùng component chuẩn hoặc tạo component riêng theo contract.

### 5.3. Intermediate representation

IR chuẩn hóa các construct khác nhau thành model thống nhất. Nhiều syntax hoặc frontend có thể cùng chuyển vào IR.

### 5.4. Platform adapter

Adapter ánh xạ IR sang nền tảng đích. Điều này cho phép DSL giữ semantics chung trong khi target có implementation khác nhau.

### 5.5. Advanced escape hatch

Khi abstraction không đủ, người dùng có thể dùng extension hoặc target-specific block có giới hạn. Cần xác định rõ phần nào không còn portable.

### 5.6. Abstraction leak

High-level construct có thể che chi tiết quan trọng như network policy hoặc transaction boundary. Documentation cần cho phép xem effective model và target output.

## 6. Flexibility trong cú pháp

Cú pháp linh hoạt có thể hỗ trợ alias, shorthand, nhiều style hoặc macro.

### 6.1. Alias

Alias giúp người dùng chuyển từ cú pháp cũ hoặc dùng tên phù hợp domain. Nhiều alias kéo dài làm tăng số dạng source mà parser phải hỗ trợ.

### 6.2. Shorthand

Shorthand rút gọn khai báo phổ biến. Cần bảo đảm semantics giống dạng đầy đủ và formatter có thể chuẩn hóa về một style.

### 6.3. Named arguments

Named arguments giúp cấu hình dễ đọc khi có nhiều tham số. Chúng hỗ trợ thêm parameter mà ít ảnh hưởng call site hơn positional-only syntax.

### 6.4. Optional block

Block tùy chọn giảm boilerplate nhưng default phải rõ. Người dùng cần biết khi không khai báo thì engine chọn behavior nào.

### 6.5. Macro

Macro có thể tạo syntax hoặc AST từ một construct cấp cao. Macro mạnh nhưng làm source-to-source mapping và debugging khó hơn.

### 6.6. Custom operator

Operator tùy biến có thể làm biểu thức ngắn nhưng precedence và readability khó kiểm soát. Nên giới hạn số operator và định nghĩa rõ associativity.

### 6.7. Syntax extension policy

Nếu cho plugin thêm grammar, cần quản lý ambiguity, namespace, parser compatibility và tooling. Một syntax extension không được làm parser các file hiện có đổi cách diễn giải.

## 7. Flexibility trong semantics và rule

Semantics linh hoạt cho phép domain thay đổi policy mà không sửa compiler core.

### 7.1. Declarative rules

Người dùng khai báo điều kiện và kết quả. Engine chịu trách nhiệm đánh giá theo semantics đã công bố.

### 7.2. Policy object

Policy gom các lựa chọn như retry, authorization hoặc routing thành object có type. Consumer có thể dùng policy chuẩn hoặc khai báo policy riêng.

### 7.3. Strategy pattern

Một field có thể chọn strategy implementation qua identifier đã đăng ký. DSL cần xác minh strategy tồn tại và tương thích với context.

### 7.4. Rule priority

Rule có thể được sắp theo priority hoặc hit policy. Precedence cần tường minh để thay đổi rule không tạo behavior khó đoán.

### 7.5. Pure expression

Biểu thức thuần dễ cache, kiểm thử và tái lập. Cho phép side effect trong mọi expression làm semantics khó hiểu và giảm khả năng tối ưu.

### 7.6. Custom function

Function extension có thể mở rộng domain operations. Cần signature, return type, error semantics, resource budget và permission rõ.

### 7.7. Policy composition

Có thể kết hợp policy theo AND, OR, override hoặc fallback. DSL cần quy định cách xử lý conflict và thứ tự đánh giá.

## 8. Flexibility trong type system

Type system có thể hỗ trợ domain-specific types và user-defined structures.

### 8.1. Custom scalar type

Người dùng có thể tạo type như EmailAddress, CustomerId hoặc Money. Type mới có validation và semantics riêng.

### 8.2. Record type

Record cho phép mô hình hóa cấu trúc dữ liệu domain. Field có type, nullability, default và constraint.

### 8.3. Enum extension

Một số DSL cho phép enum mở rộng bởi plugin. Cần cân nhắc consumer có thể xử lý giá trị mới hay không.

### 8.4. Generic types

Generic giúp tái sử dụng component với nhiều type. Inference và constraint cần đủ rõ để diagnostic dễ hiểu.

### 8.5. Refinement types

Refinement type bổ sung predicate lên type cơ sở, ví dụ PositiveInteger. Nó tăng độ chính xác nhưng cần kiểm soát chi phí validation.

### 8.6. Type coercion

Coercion tiện lợi nhưng có thể che lỗi. Chỉ cho phép conversion an toàn và không mơ hồ; conversion có mất dữ liệu nên cần tường minh.

### 8.7. Dynamic type

Dynamic type tăng flexibility nhưng làm lỗi chuyển sang runtime và giảm khả năng phân tích tĩnh. Nên giới hạn ở boundary hoặc use case có lý do.

### 8.8. Type extension compatibility

Thêm type hoặc đổi constraint có thể ảnh hưởng serialized model và generated code. Type schema cần versioning.

## 9. Configuration và profile flexibility

Configuration cho phép một model được triển khai trong nhiều context.

### 9.1. Variables

Variable đặt tên cho giá trị có thể thay đổi theo project hoặc environment. Type và default giúp giảm lỗi.

### 9.2. Profiles

Profile gom các cấu hình theo mục đích như development, test, staging và production.

~~~text
profile development {
    replicas = 1
    logging.level = DEBUG
}

profile production {
    replicas = 4
    logging.level = WARN
}
~~~

### 9.3. Override

Một layer có thể override giá trị từ layer khác. Cần quy định precedence giữa defaults, project, profile, command line và environment.

### 9.4. Inheritance

Profile có thể kế thừa profile chung. Cần xác định merge behavior cho scalar, list và map.

### 9.5. Conditional configuration

Có thể bật block theo feature flag hoặc target. Điều kiện cần được kiểm tra và ghi vào resolved configuration.

### 9.6. Secret reference

Configuration có thể tham chiếu secret store thay vì chứa credential trực tiếp. Điều này tăng flexibility nhưng cần permission và runtime resolution policy.

### 9.7. Effective configuration

Tool nên hiển thị giá trị cuối cùng cùng nguồn override. Nếu không, người dùng khó biết tại sao production nhận một giá trị khác file gốc.

### 9.8. Configuration explosion

Quá nhiều profile và override tạo ra nhiều tổ hợp khó test. Giới hạn combination và cung cấp profile chuẩn giúp giảm rủi ro.

## 10. Composition, module và reuse

Composition cho phép mở rộng behavior bằng cách kết hợp component nhỏ.

### 10.1. Module

Module gom type, rule, service hoặc task thành đơn vị có interface rõ. Module có thể được import và tái sử dụng.

### 10.2. Component template

Template tạo component từ parameter. Parameter cần có type và default để template không sinh cấu hình thiếu.

### 10.3. Inheritance và composition

Inheritance chia sẻ behavior qua base definition nhưng có thể tạo coupling sâu. Composition ghép component độc lập thường dễ kiểm soát hơn.

### 10.4. Extension of component

Component có thể cung cấp hook hoặc slot để consumer thêm behavior. Hook cần có lifecycle và ordering rõ.

### 10.5. Reuse boundary

Không phải mọi khác biệt đều nên trở thành parameter. Nếu hai component có semantics khác đáng kể, tạo component riêng có thể dễ hiểu hơn một abstraction có quá nhiều option.

### 10.6. Dependency management

Reusable module cần version, dependency constraint và compatibility policy. Module flexible nhưng phụ thuộc nhiều plugin không tương thích sẽ khó sử dụng.

### 10.7. Encapsulation

Module nên ẩn implementation và công bố interface cần thiết. Expose mọi internal detail khiến consumer phụ thuộc vào cấu trúc khó thay đổi.

## 11. Plugin và extension points

Plugin là cơ chế phổ biến để thêm khả năng mà không sửa core DSL.

### 11.1. Extension point

Extension point xác định nơi plugin có thể tham gia, ví dụ parser phase, type provider, code generator, deployment backend hoặc validation rule.

### 11.2. Plugin contract

Contract mô tả API, version, lifecycle, input/output, exception behavior và capability được phép.

### 11.3. Plugin registry

Registry ánh xạ extension ID sang implementation. DSL tham chiếu ID thay vì class name hoặc arbitrary code.

### 11.4. Version compatibility

Plugin cần khai báo host API range. Loader kiểm tra compatibility trước khi khởi tạo.

### 11.5. Plugin ordering

Nếu nhiều plugin cùng tham gia phase, thứ tự phải được định nghĩa hoặc yêu cầu plugin khai báo dependency/priority.

### 11.6. Plugin isolation

Plugin có thể chạy trong process riêng hoặc sandbox với quyền giới hạn. Không nên mặc định plugin được tin cậy chỉ vì cài qua registry.

### 11.7. Plugin discovery

IDE và CLI cần có metadata để hiển thị extension được cài, capability, version và documentation.

### 11.8. Plugin lifecycle

Install, enable, disable, upgrade và removal cần được quản lý. Một project nên pin plugin version nếu behavior phụ thuộc vào plugin đó.

## 12. Custom backend và platform portability

Một DSL có thể target nhiều nền tảng bằng cách tách domain model khỏi code emission.

### 12.1. Backend interface

Backend nhận IR và sinh artifact cho target. Interface cần xác định capability và limitation.

### 12.2. Capability detection

Không phải target nào cũng hỗ trợ mọi feature. Compiler có thể kiểm tra capability trước khi generation.

### 12.3. Portable core

Phần DSL portable nên biểu diễn semantics chung. Target-specific block cần được đánh dấu rõ để người dùng biết project bị ràng buộc vào platform nào.

### 12.4. Backend-specific extension

Một backend có thể cung cấp option riêng. Namespace và type cần tránh làm option target-specific lọt sang backend khác.

### 12.5. Capability fallback

Nếu target không hỗ trợ feature, engine có thể báo error, dùng fallback đã định nghĩa hoặc yêu cầu người dùng chọn target khác. Không tự hạ cấp semantics một cách âm thầm.

### 12.6. Cross-target testing

Cùng một DSL model cần được test trên từng backend được hỗ trợ. Output khác nhau có thể hợp lệ nếu behavior theo contract tương đương.

### 12.7. Portability report

Tool có thể báo construct nào portable, construct nào target-specific và construct nào cần thay thế khi chuyển platform.

## 13. Escape hatch và quyền tùy biến cấp thấp

Escape hatch cho phép người dùng truy cập khả năng mà abstraction DSL chưa biểu diễn.

### 13.1. Khi nào cần escape hatch?

Có thể cần khi platform có feature mới, integration đặc biệt hoặc trường hợp hiếm chưa được đưa vào core language.

### 13.2. Raw target block

Một DSL có thể cho phép nhúng đoạn cấu hình hoặc code của target. Cần chỉ rõ phần đó không được DSL type-check đầy đủ hoặc không portable.

### 13.3. Opaque payload

Có thể giữ payload dạng opaque để chuyển tiếp đến target system. Tuy nhiên, validation và security vẫn phải được thực hiện ở boundary phù hợp.

### 13.4. Scope limitation

Escape hatch nên giới hạn trong một block, resource hoặc task. Không mở toàn bộ runtime nếu chỉ cần một cấu hình cụ thể.

### 13.5. Validation boundary

DSL cần xác định phần nào được validate và phần nào do target tool chịu trách nhiệm. Error mapping nên chỉ rõ nguồn lỗi.

### 13.6. Portability cost

Escape hatch thường gắn project với target cụ thể. Tool nên hiển thị portability warning và hỗ trợ inventory các block này.

### 13.7. Migration path

Nếu escape hatch được dùng rộng rãi, có thể là tín hiệu core DSL thiếu abstraction. Theo dõi usage để quyết định có nên đưa capability thành feature chuẩn.

## 14. Flexibility và type safety

Tùy biến không nên làm mất các bảo đảm mà DSL có thể cung cấp.

### 14.1. Typed configuration

Dùng schema và type để giới hạn giá trị hợp lệ. IDE có thể completion và diagnostic trước runtime.

### 14.2. Typed extension API

Plugin nhận object có type rõ thay vì map string tùy ý. Contract typed giúp compiler và host kiểm tra tương thích.

### 14.3. Validation at boundary

Giá trị dynamic cần được validate khi đi vào typed core. Sau khi xác thực, các bước tiếp theo có thể dựa vào invariant đã thiết lập.

### 14.4. Avoid unsafe coercion

Không tự chuyển mọi chuỗi thành số, path hoặc identifier. Conversion cần được khai báo và báo lỗi nếu mất thông tin.

### 14.5. Typed escape hatch

Ngay cả raw block cũng có thể có schema envelope, allowed target và capability rõ để giới hạn phạm vi.

### 14.6. Static versus runtime checks

Static checking phát hiện lỗi trước execution; runtime check cần cho dữ liệu động. DSL nên chỉ rõ guarantee nào đến từ mỗi tầng.

### 14.7. Soundness trade-off

Nếu cho phép dynamic behavior, compiler có thể không chứng minh được mọi property. Cần báo rõ phần nào được kiểm tra và phần nào chỉ được xác nhận lúc runtime.

## 15. Flexibility và hiệu năng

Cấu hình và extension động có thể làm tăng chi phí parse, resolve, compile và runtime.

### 15.1. Dynamic dispatch

Plugin hoặc strategy được chọn runtime có thể tăng overhead và làm khó tối ưu. Nếu choice có thể biết lúc compile, resolve sớm có thể hiệu quả hơn.

### 15.2. Reflection

Reflection giúp mở rộng nhưng giảm khả năng static analysis và có thể tăng chi phí runtime. Dùng reflection ở boundary cần thiết thay vì trong hot path.

### 15.3. Configuration resolution

Nhiều layer override và inheritance làm tăng chi phí resolve. Có thể compile effective configuration thành immutable snapshot để reuse.

### 15.4. Plugin loading

Load nhiều plugin có thể làm startup chậm. Lazy loading hoặc capability-based loading giúp chỉ nạp extension cần thiết.

### 15.5. Cacheability

Pure expression và immutable model dễ cache. Dynamic function phụ thuộc environment hoặc network có thể làm cache không an toàn.

### 15.6. Optimization boundary

Compiler có thể tối ưu phần typed/known trong khi giữ dynamic boundary riêng. Cần tránh làm optimization thay đổi behavior của extension.

### 15.7. Performance budget

Cho phép custom function nhưng giới hạn thời gian, memory và call count. Extension cần có performance contract.

## 16. Flexibility và bảo mật

Khả năng tùy biến thường mở rộng bề mặt tấn công.

### 16.1. Arbitrary code execution

Cho người dùng nhúng script tổng quát có thể cấp quyền quá rộng. Ưu tiên declarative construct hoặc expression language giới hạn.

### 16.2. Capability model

Cấp quyền theo capability cụ thể như đọc source, ghi output hoặc gọi provider. Không cho mọi plugin quyền của host process.

### 16.3. Plugin trust

Xác minh nguồn, signature, version và permission manifest. Cần process isolation khi plugin không cùng trust domain.

### 16.4. Secret access

Extension chỉ nhận secret mà nó cần và được phép dùng. Không đưa secret vào global context có thể truy cập từ mọi function.

### 16.5. Network access

Custom provider hoặc function có thể gọi network. Dùng allowlist endpoint, timeout, response limit và audit.

### 16.6. Configuration injection

Raw config có thể tạo command, path hoặc query nguy hiểm. Validate và encode theo sink.

### 16.7. Tenant isolation

Extension do tenant cấu hình không được truy cập dữ liệu hoặc resource của tenant khác. Tenant context phải được xác minh tại runtime.

### 16.8. Secure defaults

Khi người dùng không cấu hình, chọn default có quyền tối thiểu và behavior an toàn. Không mở rộng quyền để làm feature “tự hoạt động” một cách tiện lợi.

## 17. Flexibility và khả năng bảo trì

Một DSL linh hoạt vẫn cần có cấu trúc để codebase và ecosystem có thể phát triển.

### 17.1. API surface

Mỗi extension point là một contract cần versioning và support. Không mở quá nhiều hook trước khi có use case thực tế.

### 17.2. Deprecation cost

Cấu hình linh hoạt có thể tạo nhiều legacy variants. Cần deprecation policy và migration support cho từng API public.

### 17.3. Documentation burden

Mỗi option, plugin và interaction cần tài liệu. Nếu không thể giải thích behavior ngắn gọn, abstraction có thể quá phức tạp.

### 17.4. Test matrix

Nhiều feature flag, profile và plugin tạo ra tổ hợp cấu hình lớn. Cần xác định supported combinations thay vì tuyên bố mọi tổ hợp đều hoạt động.

### 17.5. Debugging

Cần giải thích effective config, plugin order, selected backend và source of each value.

### 17.6. Ownership

Mỗi extension API cần owner chịu trách nhiệm compatibility và review. API không có owner dễ trở thành surface không được quản lý.

### 17.7. Observability

Log và metrics cần cho biết extension nào đã chạy, version nào được chọn và capability nào được dùng mà không lộ dữ liệu nhạy cảm.

## 18. Precedence và conflict giữa các lớp cấu hình

Khi DSL có defaults, profile, environment và CLI override, phải xác định giá trị nào thắng.

### 18.1. Precedence order

Một policy có thể dùng thứ tự: built-in default, module default, project config, environment profile, command-line override. Thứ tự cụ thể cần được công bố.

### 18.2. Explicit override

Override nên thể hiện rõ nguồn và giá trị cũ. Một số trường nhạy cảm có thể không cho override ở scope thấp hơn.

### 18.3. Merge semantics

Scalar thường replace; map có thể merge theo key; list có thể replace hoặc append. Mỗi kiểu cần semantics riêng.

### 18.4. Conflict detection

Nếu hai layer cùng đặt một giá trị nhưng không có precedence rõ, engine có thể báo conflict thay vì chọn ngẫu nhiên.

### 18.5. Explain effective value

Tool có thể trả lời “giá trị này đến từ đâu?” bằng cách hiển thị layer, file và dòng tạo override cuối cùng.

### 18.6. Immutable resolved model

Sau khi resolve, tạo model bất biến cho build/deploy. Không để extension thay đổi cấu hình giữa lúc các task đang dùng.

### 18.7. Secret precedence

Credential cần policy riêng. Không cho một file project không tin cậy override secret source hoặc identity đã được cấp bởi platform.

## 19. Standard extension và custom extension

Không phải mọi khả năng đều nên nằm trong core DSL.

### 19.1. Core feature

Đưa vào core khi semantics phổ biến, ổn định và cần được hỗ trợ nhất quán bởi tooling.

### 19.2. Standard library

Một thư viện chuẩn cung cấp reusable type, function và component nhưng có thể version độc lập với grammar core.

### 19.3. Official plugin

Plugin chính thức mở rộng khả năng theo contract được kiểm soát. Nó có thể phát hành độc lập nhưng cần compatibility matrix.

### 19.4. Third-party plugin

Plugin bên ngoài tăng ecosystem flexibility nhưng cần trust, review, signing, permissions và support expectations.

### 19.5. Local extension

Project có thể có function hoặc component nội bộ. Cần namespace và boundary để tránh xung đột khi module được chia sẻ.

### 19.6. Extension promotion

Nếu một extension được dùng rộng rãi, có thể xem xét đưa vào standard library hoặc core. Cần đánh giá semantics, compatibility và support cost.

### 19.7. Extension retirement

Plugin hoặc custom API cũng cần deprecation plan. Ecosystem không thể ổn định nếu extension cũ không có lifecycle.

## 20. Flexibility và khả năng tương thích

Càng nhiều cách mở rộng thì càng cần contract versioning rõ.

### 20.1. Language compatibility

Thêm syntax hoặc đổi precedence có thể ảnh hưởng source cũ. Version gate bảo đảm file được diễn giải theo language version đã chọn.

### 20.2. Plugin API compatibility

Host và plugin cần khai báo API range. Loader phải từ chối tổ hợp không tương thích với diagnostic rõ.

### 20.3. IR compatibility

Nhiều backend dùng chung IR. IR schema cần version để backend cũ không hiểu sai model mới.

### 20.4. Serialized model

Nếu DSL lưu compiled model hoặc cache, type và field extension cần schema migration.

### 20.5. Target compatibility

Custom backend có thể hỗ trợ feature subset. Capability negotiation giúp phát hiện trước khi generate.

### 20.6. Backward and forward compatibility

Nêu rõ consumer mới đọc config cũ được không và consumer cũ có bỏ qua field mới được không. Không mặc định cả hai chiều đều tương thích.

### 20.7. Compatibility testing

Test các version combination được công bố và từ chối tổ hợp nằm ngoài support matrix.

## 21. Thiết kế default và convention

Default tốt giúp DSL dễ dùng mà vẫn cho phép điều chỉnh.

### 21.1. Convention over configuration

Cung cấp quy tắc mặc định cho trường hợp phổ biến. Người dùng chỉ cần override khi có yêu cầu khác.

### 21.2. Safe default

Default nên ưu tiên security, predictability và resource limits. Ví dụ không mở network hoặc quyền admin chỉ vì không có config.

### 21.3. Visible default

Tool nên có khả năng hiển thị effective default. Default ẩn có thể gây ngạc nhiên khi nâng version.

### 21.4. Versioned default

Thay đổi default có thể làm behavior đổi dù source không thay. Cần versioning, release note hoặc explicit opt-in.

### 21.5. Override guard

Một số default quan trọng có thể không được override ở project scope. Policy enforcement cần được thực hiện tại compiler hoặc runtime.

### 21.6. Avoid magic behavior

Không tự suy luận quá nhiều từ tên file, environment hoặc convention không được công bố. Convention cần có tài liệu và diagnostic.

## 22. Đánh giá trade-off bằng decision framework

Trước khi thêm một cơ chế linh hoạt, có thể đánh giá theo một số câu hỏi.

| Tiêu chí | Câu hỏi |
|---|---|
| Frequency | Bao nhiêu use case thực sự cần tùy biến này? |
| Stability | Semantics có đủ ổn định để trở thành public API? |
| Safety | Có thể giới hạn quyền và validate không? |
| Tooling | IDE, formatter, analyzer có thể hỗ trợ không? |
| Portability | Có làm project phụ thuộc một platform không? |
| Performance | Có ảnh hưởng parse, compile hoặc runtime không? |
| Compatibility | Có thể version và migrate không? |
| Ownership | Ai duy trì và hỗ trợ extension? |
| Complexity | Người dùng phải học bao nhiêu khái niệm mới? |
| Alternatives | Có thể giải quyết bằng composition hoặc configuration hiện có? |

### 22.1. Bắt đầu từ use case

Không thêm extension point chỉ vì nó có vẻ tổng quát. Xác định use case, consumer và constraint trước.

### 22.2. Chọn cơ chế nhỏ nhất

Nếu một profile giải quyết được khác biệt, không cần thêm plugin. Nếu một function thuần đủ, không cần nhúng script tổng quát.

### 22.3. Ước lượng support cost

Tính chi phí documentation, test, compatibility, security review và deprecation trong suốt lifecycle.

### 22.4. Thử nghiệm trước khi chuẩn hóa

Có thể thử capability trong plugin hoặc experimental API. Khi semantics đã ổn định và có nhu cầu rộng, mới promote.

### 22.5. Ghi quyết định

Architecture decision record có thể lưu lý do chọn mức flexibility và trade-off được chấp nhận.

## 23. Kiểm thử tính linh hoạt

Flexibility cần được kiểm thử trên các cấu hình và extension được hỗ trợ.

### 23.1. Configuration matrix

Test profile, override, default và environment combinations được công bố.

### 23.2. Extension contract tests

Mỗi plugin cần test interface, lifecycle, error behavior và compatibility.

### 23.3. Negative tests

Thử extension không tồn tại, version không tương thích, capability bị từ chối và config conflict.

### 23.4. Type safety tests

Kiểm tra custom type, coercion, generic constraint và dynamic boundary.

### 23.5. Determinism tests

Cùng model và cấu hình phải tạo effective model và output ổn định.

### 23.6. Portability tests

Chạy cùng DSL trên các backend được hỗ trợ và kiểm tra construct target-specific được báo đúng.

### 23.7. Security tests

Kiểm tra plugin sandbox, secret access, network policy, path boundary và tenant isolation.

### 23.8. Performance tests

Đo chi phí khi bật extension, nhiều profile hoặc dynamic resolution. Kiểm tra giới hạn resource.

### 23.9. Compatibility tests

Test source và plugin ở version range được hỗ trợ, cùng migration khi API extension thay đổi.

### 23.10. Usability tests

Quan sát người dùng tìm option, hiểu precedence và debug effective configuration. Flexibility không hữu ích nếu không thể khám phá hoặc giải thích.

## 24. Ví dụ tổng hợp: thiết kế DSL triển khai linh hoạt

Giả sử DSL cần hỗ trợ nhiều cloud provider và environment.

### 24.1. Core service model

~~~text
service checkout {
    replicas = 3
    healthProbe {
        path = "/health"
        interval = 10 seconds
    }
}
~~~

Core model mô tả ý định chung mà không chứa resource-specific detail.

### 24.2. Environment profile

~~~text
profile development {
    replicas = 1
    observability = "verbose"
}

profile production {
    replicas = 5
    observability = "standard"
}
~~~

Profile cho phép điều chỉnh theo environment.

### 24.3. Provider selection

~~~text
target cloud {
    provider = "providerA"
    region = "asia-southeast1"
}
~~~

Provider được chọn từ registry đã cài và được xác minh compatibility.

### 24.4. Provider extension

Provider adapter chuyển core service model sang resource của cloud. Adapter công bố capability như autoscaling, ingress và managed identity.

### 24.5. Escape hatch

Nếu cần một resource đặc biệt chưa được core model hỗ trợ, người dùng có thể khai báo target-specific block. Tool đánh dấu phần này không portable.

### 24.6. Validation

Compiler xác minh provider hỗ trợ feature đã chọn, region hợp lệ, replica trong quota và extension có quyền cần thiết.

### 24.7. Explain plan

Tool hiển thị effective profile, provider, resource được tạo và nguồn của mỗi giá trị. Người dùng có thể kiểm tra trước khi apply.

### 24.8. Portability report

Khi đổi provider, tool liệt kê construct portable và target-specific. Những phần không thể ánh xạ được cần diagnostic thay vì tự bỏ qua.

## 25. Những sai lầm thường gặp

### 25.1. Coi nhiều option là flexibility tốt

Nhiều option có thể chỉ tăng cognitive load. Chỉ thêm lựa chọn khi có use case và semantics rõ.

### 25.2. Mở arbitrary code quá sớm

Script tổng quát làm giảm khả năng phân tích tĩnh, cache và security. Ưu tiên declarative extension và function allowlist.

### 25.3. Không có precedence

Nhiều layer override mà không có thứ tự rõ tạo behavior khó dự đoán. Cần effective config và source-of-value explanation.

### 25.4. Expose internal implementation

Cho consumer truy cập mọi internal detail khiến API khó thay đổi. Chỉ công bố extension point có contract và owner.

### 25.5. Extension không có lifecycle

Plugin API không version hoặc deprecation policy sẽ gây gánh nặng lâu dài.

### 25.6. Không kiểm soát target-specific behavior

Raw block có thể làm project không portable. Cần đánh dấu và report rõ.

### 25.7. Default không an toàn

Giá trị mặc định tiện lợi có thể mở quyền hoặc resource quá rộng. Chọn safe default và cho phép override có kiểm soát.

### 25.8. Dynamic behavior không được test

Configuration và plugin combination tạo nhiều trường hợp. Xác định supported matrix và kiểm thử các tổ hợp quan trọng.

### 25.9. Không có explainability

Người dùng không biết giá trị cuối đến từ đâu hoặc plugin nào đã can thiệp. Cung cấp resolved model và trace.

### 25.10. Over-abstraction

Một abstraction có quá nhiều parameter có thể khó hiểu hơn các component riêng. Tách abstraction khi semantics thực sự khác.

### 25.11. Không tính chi phí support

Mỗi extension point cần documentation, testing, compatibility và incident support. Đánh giá lifecycle cost trước khi mở rộng.

### 25.12. Không có fallback rõ

Khi target không hỗ trợ feature, engine không nên âm thầm bỏ qua. Báo error hoặc dùng fallback được định nghĩa.

## 26. Nguyên tắc thiết kế tính linh hoạt cho DSL

Một DSL tốt cho phép thích ứng mà vẫn duy trì khả năng dự đoán, kiểm tra và bảo trì.

### 26.1. Bắt đầu từ domain invariant

Xác định điều gì luôn phải đúng và điều gì có thể tùy biến. Invariant không nên bị phá bởi extension.

### 26.2. Ưu tiên cấu trúc khai báo

Dùng typed configuration, rule, profile và component trước khi mở arbitrary script.

### 26.3. Phân tầng abstraction

Cung cấp high-level construct cho use case phổ biến, advanced option cho trường hợp đặc biệt và escape hatch có giới hạn.

### 26.4. Extension point có contract

Định nghĩa ID, type, lifecycle, version compatibility, permission và error behavior.

### 26.5. Default an toàn và hiển thị được

Người dùng nên biết giá trị mặc định và nguồn override. Default cần ổn định theo language version.

### 26.6. Type safety tại boundary

Custom hoặc dynamic input phải được validate trước khi đi vào typed core.

### 26.7. Kiểm soát side effect

Expression thuần dễ kiểm tra; task có side effect cần khai báo capability, dependency và retry semantics.

### 26.8. Explainability

Cung cấp effective configuration, selected plugin/backend, source location và resolution trace.

### 26.9. Quản lý compatibility

Version hóa syntax, IR, plugin API và serialized model. Có deprecation/migration policy cho extension public.

### 26.10. Bảo mật theo least privilege

Giới hạn filesystem, network, secret và resource cho từng extension. Không cấp quyền host mặc định.

### 26.11. Test supported combinations

Kiểm thử profile, target, plugin, version và security boundary. Không hứa mọi tổ hợp nếu chưa xác nhận.

### 26.12. Theo dõi usage và support cost

Dùng feedback và metrics phù hợp để biết extension nào có giá trị, extension nào tạo nợ bảo trì.

### 26.13. Giữ core nhỏ

Chỉ đưa capability phổ biến và ổn định vào core. Phần đặc thù có thể nằm trong standard library hoặc plugin.

### 26.14. Có đường tiến hóa

Experimental, stable, deprecated và removed cần lifecycle rõ để DSL có thể đổi mà không phá consumer bất ngờ.

## 27. Thuật ngữ cần nhớ

| Thuật ngữ | Ý nghĩa |
|---|---|
| Flexibility | Khả năng thích ứng và tùy biến DSL trong các use case khác nhau |
| Expressiveness | Khả năng biểu đạt ý tưởng miền bằng construct của ngôn ngữ |
| Extensibility | Khả năng bổ sung capability hoặc behavior mới |
| Customization | Điều chỉnh cấu hình hoặc behavior cho một context |
| Abstraction | Che chi tiết triển khai và biểu diễn ý định ở mức cao hơn |
| Composition | Ghép component nhỏ thành model lớn |
| Extension Point | Vị trí được thiết kế để plugin hoặc user bổ sung behavior |
| Plugin | Thành phần mở rộng DSL hoặc toolchain |
| Provider | Adapter triển khai capability trên một nền tảng |
| Escape Hatch | Cơ chế truy cập khả năng cấp thấp ngoài abstraction chuẩn |
| Intermediate Representation | Model trung gian dùng giữa frontend và backend |
| Capability | Tập khả năng mà target hoặc extension hỗ trợ |
| Profile | Nhóm cấu hình cho một environment hoặc use case |
| Override | Thay giá trị được kế thừa hoặc mặc định |
| Precedence | Thứ tự ưu tiên giữa các nguồn cấu hình |
| Effective Configuration | Cấu hình cuối cùng sau khi resolve defaults và overrides |
| Type Safety | Bảo đảm thao tác phù hợp với kiểu dữ liệu |
| Dynamic Dispatch | Chọn implementation tại runtime |
| Portability | Khả năng chuyển model giữa các target |
| Abstraction Leak | Chi tiết cấp thấp bị lộ qua abstraction |
| Safe Default | Giá trị mặc định giới hạn rủi ro và behavior ngoài ý muốn |
| Compatibility Matrix | Bảng các tổ hợp version được hỗ trợ |
| Contract Testing | Kiểm tra extension hoặc consumer tuân thủ interface đã cam kết |
| Configuration Explosion | Số tổ hợp cấu hình tăng đến mức khó kiểm soát |
| Progressive Disclosure | Chỉ hiển thị lựa chọn nâng cao khi người dùng cần |
| Semantic Invariant | Điều kiện ngữ nghĩa luôn phải được giữ |
| Extension Lifecycle | Vòng đời phát triển, version, deprecation và removal của extension |
| Portability Report | Báo cáo construct portable và target-specific |

Tính linh hoạt giúp DSL thích ứng với nhiều project, environment và nền tảng, nhưng mọi lựa chọn mở rộng đều có chi phí về độ phức tạp, type safety, hiệu năng, bảo mật, tooling và compatibility. Thiết kế tốt bắt đầu từ invariant của domain, cung cấp abstraction và cấu hình có kiểu cho use case phổ biến, mở extension point có contract và giới hạn escape hatch cho trường hợp đặc biệt. Khi default an toàn, precedence rõ, effective model có thể giải thích, extension được version hóa và các tổ hợp được kiểm thử, DSL có thể linh hoạt mà vẫn giữ được tính dự đoán và khả năng bảo trì.
