# Khi nào nên sửa thiết kế kiểu trực tiếp thay vì mở rộng bằng aspect

## 1. Câu hỏi kiến trúc đằng sau một phép mở rộng kiểu

Trong **Aspect-Oriented Programming (AOP)**, advice có thể can thiệp vào những join point đã có. Một số mô hình AOP nâng cao còn hỗ trợ **structural crosscutting**: đưa vào method, field, interface hoặc một capability bổ sung bằng introduction, mixin, proxy, code generation hoặc source/bytecode weaving, tùy công cụ.

Khả năng ấy hữu ích khi một mối quan tâm xuyên suốt phải xuất hiện tại nhiều kiểu. Nhưng “công cụ có thể bổ sung” **không tự có nghĩa đó là lựa chọn thiết kế tốt**. Nếu bản thân một kiểu nghiệp vụ thiếu method hoặc invariant thiết yếu, việc dùng aspect để “vá” API có thể che một thiết kế kiểu chưa đầy đủ, gây lỗi compile/runtime khó phát hiện và làm tăng phụ thuộc vào toolchain.

Ví dụ: `Invoice` luôn phải có `invoiceId`, `status` và quy tắc chuyển trạng thái hợp lệ. Nếu API được công bố không cho biết những dữ liệu ấy, dùng một aspect giới thiệu `getStatus()` hoặc external map `Invoice → status` có thể tạo hai nơi giữ sự thật. Khi status là **bất biến nghiệp vụ cốt lõi**, thường nên sửa **mô hình/kiểu** một cách tường minh.

Ngược lại, nếu cần gắn `traceId` cho nhiều operations khác nhau để theo dõi request mà không thay đổi contract của từng domain type, một aspect quan sát hoặc một scoped context có thể hợp lý hơn.

### Nguyên tắc quyết định

> **Nếu một khả năng là bản chất của đối tượng, thuộc hợp đồng mà mọi client hợp lệ phải biết, hoặc bảo vệ invariant của domain, ưu tiên sửa trực tiếp type/API/implementation. Nếu khả năng chủ yếu là mối quan tâm xuyên suốt, không đổi semantic contract của type, có phạm vi áp dụng và lifecycle rõ, AOP có thể là một giải pháp thích hợp.**

Đây là **heuristic kiến trúc**, không phải luật tuyệt đối. Với code của bên thứ ba, một legacy binary không thể sửa, hoặc hàng trăm kiểu có chung một capability do công cụ weaving hỗ trợ tốt, introduction có thể là sự đánh đổi đúng. Cần đánh giá theo **hợp đồng**, **chi phí**, **mức độ kiểm soát mã nguồn**, **toolchain**, **khả năng kiểm thử** và **vòng đời dữ liệu**.

### Sau bài học, bạn sẽ

1. Phân biệt **sửa trực tiếp class/interface**, **composition/decorator**, **AOP advice** và **structural introduction**.
2. Nhận diện **domain invariant, identity, lifecycle** và operations thuộc bản chất một type.
3. Biết khi nào nên thêm field/method/interface trực tiếp thay vì cất state vào proxy/aspect.
4. Hiểu sự khác nhau giữa kiểu được thấy ở **source/compiler**, **proxy runtime** và **class được weave**.
5. Đánh giá trade-off về LSP, API discoverability, binary compatibility, source compatibility, serialization và migration.
6. Phân tích Java constraints: `final`, `record`, sealed hierarchies, constructors, visibility và generic erasure.
7. Thiết kế phần mở rộng khi không thể sửa source: interface adapter, wrapper, external associations hoặc tool-specific introductions.
8. Tránh việc dùng aspect để **che lỗi thiết kế**, **vượt quyền**, **nhân side effects** hoặc lưu state sai scope.
9. Chạy một ví dụ Java 17 đối chiếu **class trực tiếp implements capability** với **proxy thêm interface**, và giải thích stdout.
10. Áp dụng ma trận quyết định, bài tập và checklist review cho một hệ thống thực.

**Phạm vi:** Kiến thức Aspect/AOP cơ bản và nâng cao **nói chung**. Không đồng nhất cú pháp, tính năng hoặc precedence của một engine với tất cả công cụ AOP.

## 2. Bốn cách giải một yêu cầu “thêm khả năng cho đối tượng”

Giả sử hệ thống có `Document` với `read()` và `save()`. Yêu cầu mới: mỗi document có `revisionId()`, đồng thời mọi lần `save()` cần được đo latency.

Có bốn hướng thiết kế chính:

| Cách | Điều thay đổi | Điểm mạnh | Rủi ro/giới hạn |
| --- | --- | --- | --- |
| **Sửa class/interface trực tiếp** | API và implementation của loại đối tượng. | Type contract rõ với compiler/IDE; dễ bảo vệ invariant. | Cần sở hữu source, versioning/migration. |
| **Composition/decorator** | Tạo wrapper implement abstraction tương ứng. | Tường minh, dễ test, không cần weaving engine. | Caller phải dùng wrapper; khác identity/type gốc. |
| **Advice tại join point** | Hành vi quanh các operations đã có. | Hợp cho logging, tracing, metrics, policy crosscutting. | Không mặc định thêm member vào type; call path có thể bypass. |
| **Structural introduction/mixin** | Bổ sung interface/method/state ở mức engine hỗ trợ. | Có thể áp dụng capability thống nhất cho nhiều types. | Cú pháp/toolchain/type view, conflicts và lifecycle phức tạp. |

Không nhất thiết chọn **chỉ một**. Một thiết kế thường hiệu quả là:
- `revisionId` là **dữ liệu cốt lõi** → sửa domain type hoặc một interface typed.
- `save()` latency metric là **cross-cutting observation** → dùng advice hoặc instrumentation thích hợp.
- Một compatibility adapter cho đối tác không sửa được → wrapper hoặc introduction khi cần.

### 2.1. “Mở rộng bằng aspect” có nhiều nghĩa

Một cơ chế chỉ có before/after/around advice **không đồng nghĩa có structural introductions**. Một JDK dynamic proxy có thể tạo object implements interface bổ sung, nhưng **không sửa class target**. Một generated subclass có members mới chỉ thay subtype, không thay base declaration. Một weaver có thể thay class artifact khi hỗ trợ, nhưng vẫn chịu Java/JVM/build constraints.

Trước khi ra quyết định, phải trả lời: **công cụ đang thêm gì, vào object/class nào, ở compile time hay runtime?**

### 2.2. “Sửa thiết kế kiểu trực tiếp” không chỉ là thêm một getter

Có thể cần:
- Định nghĩa một interface nghiệp vụ chính xác hơn.
- Tách một class có nhiều trách nhiệm.
- Đưa state/invariant về đúng aggregate owner.
- Dùng value object thay chuỗi/số rời rạc.
- Tạo constructor/factory bảo đảm trạng thái hợp lệ.
- Chỉnh generic bounds, error model hoặc lifecycle API.
- Tái cấu trúc inheritance thành composition.
- Công bố sealed subtypes/variant states rõ ràng.

Nếu vấn đề là domain model thiếu ranh giới, thêm method bằng weaving vẫn chưa sửa **mô hình khái niệm**.

## 3. Dấu hiệu mạnh cho việc sửa type trực tiếp

### 3.1. Thuộc tính là một phần của danh tính nghiệp vụ

Một `Customer` cần `customerId`, một `Payment` cần `paymentId`, một `Order` cần `orderId`. Nếu hệ thống chỉ hợp lệ khi mỗi instance đều có định danh đó, nó thường nên là **field hoặc value object trong domain contract**, không phải dữ liệu được gắn tạm khi một advice chạy.

Vì sao?
- Constructor/factory có thể kiểm tra ID ngay.
- Compiler và tests nhìn thấy ID requirement.
- Serialization/database mapping có thể được thiết kế thống nhất.
- Mọi call path (bao gồm direct target) đều thấy cùng nguồn sự thật.
- Không phụ thuộc proxy instance và registry riêng để tra ID.

Một correlation ID cho telemetry thì khác: nó mô tả **lượt xử lý**, không nhất thiết thuộc identity bền vững của từng domain entity.

### 3.2. Method mới diễn đạt operation nghiệp vụ chính

Nếu `Account.transferTo(...)` có quy tắc số dư, idempotency và atomicity, việc “giới thiệu” method bằng aspect có thể che logic quan trọng và chuyển trách nhiệm ra khỏi aggregate/service có quyền kiểm soát invariant.

Nếu method là operation chính mà mọi caller cần hiểu, nên đưa nó vào **public API** phù hợp rồi có implementation/test rõ. Advice có thể bổ trợ tracing, metrics hay policy xung quanh operation ấy, không thay thế domain method.

### 3.3. Invariant cần đúng ở mọi đường truy cập

Ví dụ một `InventoryItem` phải luôn thỏa `reserved <= available`. Nếu chỉ interceptor trên proxy mới bảo vệ điều kiện này, một direct target call hoặc self-invocation không đi qua proxy có thể phá invariant.

Khi invariant là **bắt buộc** cho mọi thay đổi state, đặt validation/update vào đúng owner/trusted boundary. Một aspect có thể quan sát hoặc thực thi thêm policy, nhưng không nên là nơi duy nhất duy trì sự thật nội tại của đối tượng nếu interception coverage chưa được chứng minh.

### 3.4. Compiler phải bảo đảm khả năng sử dụng

Một API mới cần mọi consumer thấy `Auditable.auditId()` và được compiler kiểm tra. Nếu source của type có thể sửa, việc implements interface rõ ràng thường giảm rủi ro hơn phụ thuộc một quá trình weave/generation mà IDE/test và production có thể dùng artifact khác nhau.

Nếu chỉ proxy runtime implements `Auditable`, biến gốc `Document d` không tự có `auditId()`; caller phải cast hoặc được trả typed adapter. **Compile-time visibility** là một yêu cầu kiến trúc thực, không chỉ sự tiện lợi của IDE.

### 3.5. State có lifecycle/phụ thuộc phức tạp

Một introduced field giữ database resource, listener, mutable buffer hoặc task controller cần khởi tạo và dọn đúng thời điểm. Constructor, factory, `close()`, owner và invariants có thể được thể hiện rõ hơn khi state thuộc class/component được định nghĩa tường minh.

Nếu aspect state lives ở registry global `Map<Target,State>`, registry có thể giữ target lâu hơn dự kiến. Nếu state ở handler, hai wrappers cùng target có thể có hai states, dẫn tới phân tán nguồn sự thật.

## 4. Dấu hiệu cho phép ưu tiên aspect

Một aspect phù hợp khi các điều kiện sau phần lớn đúng:
- Concern áp cho **nhiều kiểu hoặc nhiều join points** theo một quy tắc rõ ràng.
- Concern chủ yếu là **cross-cutting observation** hoặc một policy được công bố.
- Nó không biến đổi invariant cốt lõi hay đòi thêm thuộc tính bắt buộc trong domain schema.
- Interception mechanism bao phủ đúng các paths cần xử lý.
- Behavior có thể kiểm thử độc lập và kiểm tra integration với target.
- State chủ yếu immutable/shared an toàn hoặc local mỗi invocation.
- Không phụ thuộc vào một interface được introduced nhưng compiler/consumer không biết.
- Có chính sách rõ khi advice throw, skip, retry, short-circuit hoặc async.
- Build/deploy pipeline cho introduction/weaving được kiểm soát nếu sử dụng.
- Lợi ích giảm duplication lớn hơn coupling với framework/toolchain.

Các ví dụ điển hình:
- Đo thời gian của nhiều operations.
- Thêm correlation ID vào logs trong scope đã xác thực.
- Thu thập per-attempt và per-logical metrics.
- Audit invocation theo policy được công bố.
- Truyền một concern orthogonal qua nhiều components, khi API domain không nên mang các tham số chỉ phục vụ instrumentation.
- Giới thiệu một **capability hẹp** cho nhiều đối tượng legacy khi không thể sửa source và runtime/toolchain được kiểm soát.

### 4.1. Aspect không nhất thiết phải “vô hình”

Authorization, retry hay fallback có thể **đổi hành vi** một cách hợp lệ nếu API/architecture đã công bố policies tương ứng. Nhưng nếu policy bắt buộc, nó cần được bảo vệ ở boundary đáng tin và test các đường bypass, không chỉ giả định mọi lời gọi qua proxy.

### 4.2. Có thể có sự phân công hợp lý

~~~text
Domain type:
  business identity
  invariants
  state transitions
  primary APIs

Cross-cutting aspect:
  tracing
  metrics
  optional structured audit
  consistent policy at verified boundaries

Infrastructure adapter:
  protocol conversion
  serialization
  external dependency mapping
~~~

Sơ đồ là gợi ý phân chia trách nhiệm, không phải tuyên bố một kiến trúc duy nhất cho mọi ứng dụng.

## 5. “Bản chất của đối tượng” và “bản chất của một lần sử dụng”

Hai tình huống dễ nhầm:

**Tình huống A — Mỗi hóa đơn có số định danh phát hành:** Đây là dữ liệu của **invoice entity**. Nếu ID thay đổi khi tạo proxy khác, có thể là lỗi. Nó nên nằm trong hợp đồng type hoặc một owner bền vững.

**Tình huống B — Mỗi request thao tác hóa đơn có trace ID:** Đây là dữ liệu của **invocation/logical operation**. Một invoice có thể bị đọc bởi nhiều requests song song với trace IDs khác nhau. Lưu `currentTraceId` trong invoice field hay aspect per-target field là sai scope.

| Câu hỏi | Thuộc về type/domain | Thuộc về invocation/context |
| --- | --- | --- |
| Hai requests trên cùng object cần cùng giá trị? | Thường có, tùy property. | Thường không. |
| Giá trị cần serialize/persist lâu dài? | Có thể có. | Thường không. |
| Constructor/factory phải validate? | Thường có. | Root context entry thường validate. |
| Có liên quan nghiệp vụ khi không có AOP? | Có. | Có thể chỉ phục vụ observability. |
| Có cần đọc trên direct-target calls? | Thường có. | Phụ thuộc instrumentation coverage. |
| Có thể do nhiều threads cập nhật đồng thời? | Cần domain synchronization. | Cần per-call/task isolation. |

Đôi lúc **một audit ID bền vững** thuộc entity, còn **trace ID của lần audit** thuộc flow. Đặt tên rõ để tránh đưa một concern xuyên suốt thành field nghiệp vụ hoặc ngược lại.

## 6. Interface introduction không tự sửa một API thiếu hợp đồng

Giả sử type chỉ có:

~~~java
interface Reader {
    String read(String key);
}
~~~

Đến một ngày mọi caller **bắt buộc** cần owner ID của dữ liệu để thực thi quyền. Nếu chỉ dùng một proxy thêm `Owned.ownerId()`, thì:
- Target gốc vẫn không có contract `Owned`.
- Caller giữ target có thể bỏ qua proxy.
- Hai proxies có thể trả owner IDs khác nhau nếu handler sở hữu state.
- Compiler không bảo đảm mọi `Reader` đều có owner ID.
- Một code path dùng plain `Reader` không nhận được type guarantee.
- Owner ID từ untrusted input trong handler có thể bị spoof.

Nếu quyền sở hữu là **đặc tính bắt buộc của mọi Reader trong domain**, hãy cân nhắc định nghĩa:
- `OwnedReader extends Reader`, có `ownerId()`.
- Một `record OwnerId(...)`/value object validated.
- Factory chỉ trả loại đảm bảo owner.
- An explicit authorized operation boundary.
- Domain tests không phụ thuộc interception.

Một aspect có thể cung cấp tracing/audit cho `OwnedReader` nhưng không nên là nguồn duy nhất của thuộc tính domain bắt buộc.

### 6.1. Khi nào introduction interface lại hợp lý?

Một integration tới thư viện bên thứ ba có rất nhiều objects, và app chỉ cần gắn một **capability phụ** để instrumentation, không thể sửa source. Nếu proxy hoặc weaver có hợp đồng rõ và mọi consumer được cung cấp đúng typed objects, introduction có thể giảm boilerplate.

Ví dụ một `TraceTagged` marker dùng để nhận diện wrapper tại instrumentation boundary có thể phù hợp; nhưng đừng dùng marker đó thay authorization hoặc dữ liệu nghiệp vụ cần tồn tại trên target thật.

### 6.2. Không gọi proxy interface introduction là “target đã implements”

Với JDK dynamic proxy, chỉ object proxy implements các interfaces cấu hình. Target gốc không tự thay định nghĩa class và không xuất hiện field mới chỉ nhờ handler. Nếu một weaver thực sự thay class artifact, behavior/reflective visibility có thể khác; phải xác minh engine và build pipeline ấy.

## 7. Trường hợp bổ sung field: đừng tạo hai nguồn sự thật

Một tình huống nguy hiểm:

~~~text
Order.class:
    status = SHIPPED

Aspect Registry:
    Map<Order,Status> shadowStatus
    shadowStatus[order] = PAID
~~~

Ai sở hữu status? Một caller đọc `order.status` thấy SHIPPED, một introduced getter trả PAID. Không có cách diễn giải nhất quán nếu không định nghĩa rõ một hệ là authoritative và cơ chế đồng bộ được bảo đảm.

### 7.1. Field nên ở nơi invariant được thực thi

Nếu status điều khiển `ship()`, `cancel()`, `refund()`, logic transition thường nên nằm trong domain owner, không bị chia giữa field gốc và registry external chỉ để aspect có thể “thêm thuộc tính”.

### 7.2. Khi external association có thể phù hợp

Một external association `Target → MetricsBucket` có thể hợp lý khi:
- Metrics chỉ là metadata phụ.
- Không ảnh hưởng business methods.
- Mapping đúng identity và bounded lifecycle.
- Owner remove entries khi target hết hạn.
- Không giữ strong keys/values khiến target bị giữ vô hạn.
- Concurrent updates được xử lý.

Đây là **observability state**, không phải một field domain mới bắt buộc.

### 7.3. Per-proxy state khác per-target state

Hai wrappers bọc cùng một target có thể có hai fields riêng. Nếu yêu cầu “mọi references tới target có một thuộc tính thống nhất”, state nằm trong handler **không tự đáp ứng**. Sửa type trực tiếp có thể giúp thống nhất owner nếu source được kiểm soát; nếu không, cần canonical adapter hoặc registry identity có cleanup và documented semantics.

## 8. Thay method trực tiếp khi logic cần được đọc và bảo trì như domain code

Một method bổ sung mang tính nghiệp vụ đáng kể có:
- Input validation.
- Transaction boundaries.
- State transition.
- Error types.
- Idempotency guarantees.
- Side effects trên hệ ngoài.
- Compensating action hoặc undo behavior.
- Persistence/schema contract.

Việc triển khai nó bằng introduction/weaving có thể hữu ích về kỹ thuật, nhưng tăng độ khó:
- Người đọc source `Account` không thấy `transfer()`.
- Refactoring IDE chưa chắc hiểu ITD.
- Unit test trên target chưa weave khác integration runtime.
- Build phải theo toolchain tương ứng.
- Method name/signature có thể conflict khi domain thêm member sau này.
- Lỗi linkage xuất hiện nếu client/runtime artifacts lệch.

Khi domain source nằm trong quyền kiểm soát và khả năng cần lâu dài, thường nên đưa method vào class/service đúng trách nhiệm, có API docs và tests. Aspect ở ngoài đo performance/audit theo hợp đồng.

### 8.1. Một method chỉ là tiện ích thuần?

Nếu method mới là helper pure để format ID, hãy cân nhắc:
- Utility function.
- Value object method.
- Interface default method.
- Extension qua composition/adapter.

Structural AOP có thể là quá nhiều hạ tầng cho một helper đơn giản.

### 8.2. Một method cross-cutting nhưng yêu cầu data source là domain?

Ví dụ `validatedCopy()` áp cho nhiều value objects. Nếu invariant của từng type khác nhau, một aspect cố “giới thiệu” generic validation có thể thiếu thông tin. Có thể tốt hơn là một `Validatable` typed contract với implementation rõ trên mỗi type, hoặc một service validator được đăng ký tường minh. AOP chỉ hợp lý nếu crosscutting logic thật sự uniform.

## 9. LSP và khả năng thay thế: việc thêm member vẫn cần đúng hành vi

**Liskov Substitution Principle (LSP)** nhắc rằng thay implementation/đối tượng tại một abstraction boundary không được làm client tuân thủ hợp đồng trở nên sai.

Nếu proxy implements `PaymentPort` và một interface phụ:
- `PaymentPort.charge()` vẫn phải giữ result, exception và side-effect semantics.
- Không được tự retry non-idempotent operations ngoài contract.
- Không được biến failure thành `false`/0 giả thành công.
- `equals`, `hashCode`, identity và `getClass()` có thể khác target; nếu caller được quyền phụ thuộc, proxy không là thay thế hoàn toàn.
- `synchronized(proxy)` và `synchronized(target)` là hai monitors khác khi đó là hai objects.
- Async result/stream resource lifecycle phải giữ đúng lời hứa.

### 9.1. Compatibility theo abstraction khác “hoàn toàn giống”

Một proxy có thể thay target hợp lệ khi caller chỉ dùng interface, nhưng thất bại khi caller cast sang concrete target class. Một weaver giữ target identity có thể thay lỗi/return nếu advice có mutation. Không đồng nhất **type assignability** với **behavioral substitutability**.

### 9.2. Xác định semantic ownership

Nếu một property quyết định postcondition, ai chịu trách nhiệm bảo đảm đúng?
- Target/domain owner.
- Adapter có contract rõ.
- Một external service giữ authoritative state.
- AOP introduction được kiểm chứng.

Đừng để hai thành phần cùng tuyên bố authoritative mà không có consistency contract.

## 10. Ràng buộc của Java type system và JVM

### 10.1. Final classes/methods

`final class` không thể bị subclass theo Java bình thường, còn `final method` không thể bị override ở subclass. Nhưng một final class có thể được **bọc bằng interface proxy hoặc decorator** nếu có abstraction thích hợp. Không suy rằng final cấm mọi hình thức AOP.

### 10.2. Records

Java record là một class có cấu trúc data carrier được khai báo và implicitly final. Nó rất phù hợp cho **value objects bất biến** mang state cốt lõi với invariant ở compact constructor. Một proxy subclass record không phải hướng hợp lệ theo luật Java thông thường.

Nếu muốn record có thêm business property bền vững, thường nên sửa **record components/schema** và migration cần thiết, thay vì giữ một shadow field của aspect. Cũng phải cân nhắc compatibility: thay record components ảnh hưởng constructors, accessors, equality, serialization.

### 10.3. Sealed hierarchies

Một sealed interface/class kiểm soát các permitted subtypes. Không thể giả định runtime-generated proxy được phép implement/seal-hierarchy type mới bất kỳ. Nếu cần mở rộng domain variants, sửa permits/subtype design trực tiếp là lựa chọn rõ khi nắm source.

### 10.4. Constructors và initialization

Bổ sung field cần một thời điểm initialization. Với type trực tiếp, constructor/factory/initializer có thể bảo đảm invariant. Với weaving/introduction, cần hiểu cơ chế khi instance được tạo, lazy vs eager, và việc constructor target có thực sự được can thiệp hay không. Một interface proxy được dựng **sau khi target tồn tại** không đưa field của handler vào constructor target.

### 10.5. Generics/erasure

Hai methods `process(List<String>)` và `process(List<Integer>)` trong cùng Java class có cùng erasure và không thể coexist như overload thông thường. Một introduction có thể gây name clash dù source aspect và target nhìn khác nhau. Nên để compiler/type system kiểm soát sớm bằng API rõ, hoặc test toolchain biến đổi chính xác.

### 10.6. Classloading và binary artifacts

Java runtime type identity gồm class name và defining loader. Class source chưa weave và binary đã weave là những API views khác nhau; client compile với artifact đã weave nhưng production nạp class chưa weave có thể gặp linkage failure.

Không mặc định runtime agent có thể thêm method/field/interface tùy ý vào **class đã load**: structural class redefinition bị giới hạn. Cần kiểm tra giai đoạn compile/load và JVM tool support. Nếu source có thể sửa trực tiếp, build consistency thường dễ quản lý hơn.

## 11. Một ví dụ Java 17: một capability bắt buộc nên nằm trong API chính thức

Tưởng tượng ví điện tử có:
- `Wallet.credit(amount)`: tăng số dư đúng amount khi amount hợp lệ.
- `Wallet.balance()`: đọc số dư.
- `Auditable.auditId()`: cho biết định danh audit bền vững.

Nếu audit ID thật sự là **một phần hợp đồng của ví**, ta muốn compiler biết implementation phải cung cấp nó. Có thể định nghĩa `AuditedWallet extends Wallet, Auditable` và yêu cầu các factories/API trả loại ấy.

Một cách khác là bọc một `Wallet` bằng proxy implements thêm `Auditable`. Proxy đó có audit ID, nhưng target gốc không có capability ấy. Điều này hợp lý cho metadata của wrapper; không tương đương với bổ sung identity bền vững cho mọi object ví.

### 11.1. Thiết kế trực tiếp: type diễn đạt lời hứa

~~~text
AuditedWallet extends Wallet, Auditable
          |
          +-- DirectWallet implements AuditedWallet

Caller nhận AuditedWallet
   -> compiler biết balance(), credit(), auditId()
   -> constructor bảo đảm auditId hợp lệ
   -> mọi phương thức trong DirectWallet nhìn cùng state
~~~

### 11.2. Thiết kế proxy: capability chỉ tồn tại trên wrapper

~~~text
PlainWallet implements Wallet
           ^
           | delegates
Proxy implements Wallet, Auditable
           + auditId từ handler
           + credit/balance chuyển tiếp vào PlainWallet

Caller giữ PlainWallet gốc: không có Auditable.
Caller giữ proxy: có Auditable.
~~~

Cả hai mô hình có thể hữu ích, nhưng cần mô tả đúng ai sở hữu contract.

## 12. Java 17 runnable: sửa kiểu trực tiếp so với thêm interface bằng proxy

Chương trình dưới đây mô phỏng hai cách. Nó không dùng một weaver và **không sửa class target bằng AOP**; JDK dynamic proxy chỉ giới thiệu giao diện phụ **trên proxy object**.

Tạo file **`DirectTypeVsAspectDemo.java`**:

~~~java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Proxy;

public class DirectTypeVsAspectDemo {
    interface Wallet {
        int credit(int amount);
        int balance();
    }

    interface Auditable {
        String auditId();
    }

    interface AuditedWallet extends Wallet, Auditable { }

    static final class DirectWallet implements AuditedWallet {
        private final String auditId;
        private int balance = 10;

        DirectWallet(String auditId) {
            if (auditId == null || auditId.isBlank()) {
                throw new IllegalArgumentException("audit ID required");
            }
            this.auditId = auditId;
        }

        @Override
        public int credit(int amount) {
            if (amount < 0) {
                throw new IllegalArgumentException("negative amount");
            }
            balance += amount;
            return balance;
        }

        @Override
        public int balance() {
            return balance;
        }

        @Override
        public String auditId() {
            return auditId;
        }
    }

    static final class PlainWallet implements Wallet {
        private int balance = 10;

        @Override
        public int credit(int amount) {
            if (amount < 0) {
                throw new IllegalArgumentException("negative amount");
            }
            balance += amount;
            return balance;
        }

        @Override
        public int balance() {
            return balance;
        }
    }

    static Wallet addAuditInterface(Wallet target, String id) {
        return (Wallet) Proxy.newProxyInstance(
                Wallet.class.getClassLoader(),
                new Class<?>[] { Wallet.class, Auditable.class },
                (proxy, method, arguments) -> {
                    if (method.getDeclaringClass() == Object.class) {
                        return switch (method.getName()) {
                            case "equals" -> proxy == arguments[0];
                            case "hashCode" -> System.identityHashCode(proxy);
                            case "toString" -> "AuditedWalletProxy";
                            default -> throw new UnsupportedOperationException(
                                    method.getName());
                        };
                    }
                    if (method.getDeclaringClass() == Auditable.class) {
                        return id;
                    }
                    try {
                        return method.invoke(target, arguments);
                    } catch (InvocationTargetException wrapped) {
                        throw wrapped.getCause();
                    }
                }
        );
    }

    static void client(Wallet wallet) {
        System.out.println("CLIENT credit=" + wallet.credit(5));
        System.out.println("CLIENT balance=" + wallet.balance());
    }

    public static void main(String[] args) {
        AuditedWallet direct = new DirectWallet("D-7");
        PlainWallet target = new PlainWallet();
        Wallet proxy = addAuditInterface(target, "P-8");

        System.out.println("DIRECT auditable=" + (direct instanceof Auditable));
        System.out.println("PROXY auditable=" + (proxy instanceof Auditable));
        System.out.println("TARGET auditable=" + (target instanceof Auditable));
        System.out.println("PROXY sameTarget=" + (proxy == target));
        System.out.println("PROXY concrete=" + (proxy instanceof PlainWallet));

        System.out.println("DIRECT id=" + direct.auditId());
        System.out.println("PROXY id=" + ((Auditable) proxy).auditId());
        client(direct);
        client(proxy);

        System.out.println("DIRECT finalBalance=" + direct.balance());
        System.out.println("TARGET finalBalance=" + target.balance());

        try {
            direct.credit(-1);
        } catch (IllegalArgumentException ex) {
            System.out.println("DIRECT error=" + ex.getMessage());
        }
        try {
            proxy.credit(-1);
        } catch (IllegalArgumentException ex) {
            System.out.println("PROXY error=" + ex.getMessage());
        }

        try {
            new DirectWallet("");
        } catch (IllegalArgumentException ex) {
            System.out.println("DIRECT invariant=" + ex.getMessage());
        }

        System.out.println("DIRECT classImplements="
                + Auditable.class.isAssignableFrom(DirectWallet.class));
        System.out.println("TARGET classImplements="
                + Auditable.class.isAssignableFrom(PlainWallet.class));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac DirectTypeVsAspectDemo.java
java DirectTypeVsAspectDemo
~~~

**Stdout kỳ vọng:**

~~~text
DIRECT auditable=true
PROXY auditable=true
TARGET auditable=false
PROXY sameTarget=false
PROXY concrete=false
DIRECT id=D-7
PROXY id=P-8
CLIENT credit=15
CLIENT balance=15
CLIENT credit=15
CLIENT balance=15
DIRECT finalBalance=15
TARGET finalBalance=15
DIRECT error=negative amount
PROXY error=negative amount
DIRECT invariant=audit ID required
DIRECT classImplements=true
TARGET classImplements=false
~~~

### 12.1. Điều quan trọng nhất của thiết kế trực tiếp

`DirectWallet` **implements `AuditedWallet`**. Compiler đòi implementation cho `auditId()`, `credit()`, `balance()`; constructor reject ID trống. Một caller chỉ nhận `AuditedWallet` có thể dựa vào capability ấy theo type contract.

Không có hidden registry nào giữ audit ID riêng. Mọi lời gọi trên object trực tiếp đều có thể đọc property `auditId` do class định nghĩa, không phụ thuộc caller đã bọc proxy hay chưa.

### 12.2. Điều quan trọng nhất của proxy

`proxy instanceof Auditable` đúng, nhưng `target instanceof Auditable` sai. `proxy` và `target` khác references; runtime proxy cũng không phải `PlainWallet`. Audit ID `P-8` nằm trong closure của handler, không nằm trong field của `PlainWallet`.

Nếu một module khác giữ `target` gốc, nó không thể ép target sang `Auditable` như một hợp đồng. Đây là lý do interface introduction qua wrapper không thể **tự thay thế** việc sửa type khi domain yêu cầu mọi target có ID.

### 12.3. Tại sao cùng kết quả credit chưa chứng minh cùng design?

Cả `client(direct)` và `client(proxy)` in `credit=15, balance=15`; interface `Wallet` được thực hiện đúng ở các lời gọi đã test. Nhưng design khác ở:
- Compile-time type guarantee.
- Constructor invariant của audit ID.
- Reflection trên target class.
- Object identity/concrete assignability.
- Quyền sở hữu audit state.
- Khả năng caller đi vòng qua proxy.

**Behavioral substitutability trong `Wallet` không đồng nghĩa structural equivalence của `AuditedWallet`.**

### 12.4. Vì sao lỗi `credit(-1)` vẫn đúng?

Target/direct implementations ném `IllegalArgumentException`. Handler proxy gọi `Method.invoke`, catch `InvocationTargetException` và rethrow cause; caller nhìn thấy đúng loại lỗi và message `negative amount`.

Một proxy muốn được coi là compatible phải giữ **return type + semantics + error contract** của operations gốc, không chỉ thêm interface phụ.

### 12.5. Vì sao reflection cuối chương trình quan trọng?

`Auditable.class.isAssignableFrom(DirectWallet.class)` là true vì direct class implements interface. `Auditable.class.isAssignableFrom(PlainWallet.class)` là false vì class gốc không thay đổi.

Một proxy cũng là runtime class có khả năng implements `Auditable`, nhưng đó là class generated **khác**. Nếu tool weaving thực sự thay target artifact, reflection trên transformed target có thể khác; demo này không kiểm điều đó.

### 12.6. Giới hạn có chủ đích

- Demo tuần tự; `balance` mutable không thread-safe khi concurrent calls.
- Handler được viết cho two non-overlapping interfaces; signature clashes cần handling khác.
- Audit ID của proxy chỉ là immutable closure, không phải policy xác thực.
- Proxy không chặn internal method calls của `PlainWallet` nếu target tự gọi chính nó.
- Không có persistence/serialization, transaction hoặc class bytecode weaving.
- Không khẳng định một interface proxy có thể implement arbitrary sealed interface; ở đây interfaces thông thường.
- Không dùng `AuditedWallet` làm kiểu của proxy vì proxy được tạo implements `Wallet,Auditable` chứ không implements `AuditedWallet` trực tiếp. Hai interfaces có đủ methods về mặt cấu trúc **không** tự có nghĩa object implement subinterface `AuditedWallet` theo nominal typing của Java. Nếu muốn proxy `instanceof AuditedWallet`, phải khai interface ấy trong danh sách proxy và xử lý methods tương ứng.

**Bài học từ code:** Nếu invariant “mọi ví được cấp phát đều có audit ID” là quan trọng, thiết kế **factory trả `AuditedWallet`** là một ràng buộc chặt hơn việc “có thể bọc bất kỳ `Wallet` nào và cast khi cần”.

## 13. Chỗ nào là vấn đề của type, chỗ nào là của aspect?

Một cách phân chia các yêu cầu cụ thể:

| Yêu cầu | Lựa chọn ban đầu | Lý do |
| --- | --- | --- |
| Mỗi `Invoice` phải có `invoiceId` không null. | Sửa type/constructor/schema. | Invariant nội tại. |
| Mỗi `Order` có `cancel()` với state transitions. | Sửa domain method/service. | Business operation cần ownership. |
| Mọi method public đều có duration metric. | Aspect/instrumentation. | Concern quan sát xuyên nhiều types. |
| Ghi trace ID theo từng HTTP request. | Scoped context + instrumentation. | Per-operation, không phải per-entity state. |
| Bổ sung `Auditable` cho 100 third-party objects. | Adapter/proxy hoặc ITD nếu tool phù hợp. | Source không thể sửa; capability phụ. |
| Khóa cache theo tenant và data type. | Explicit cache policy/adapter, aspect khi verified. | Cần trusted scope và semantics dữ liệu. |
| Một field `balance` phải nhất quán với ledger. | Domain aggregate/state owner. | Không tạo shadow state trong aspect. |
| Chặn truy cập khi chưa xác thực. | Trusted security boundary, có thể hỗ trợ bằng advice. | Policy bắt buộc, không được bypass. |
| Enforce unique order numbers trên storage. | DB/domain consistency mechanism. | Aspect interception không tự đảm bảo transaction/concurrency. |
| Ghi audit sau commit thành công. | Transaction event/outbox/audit boundary rõ. | After method return không luôn bằng after commit. |
| Mọi entity cần value equality. | Sửa value type/equality design. | Identity semantics cốt lõi. |
| Tự động thêm helper `debugLabel()`. | Utility/default method/decorator, cân nhắc aspect nếu rất rộng. | Đừng over-engineer. |

**Lưu ý:** Những lựa chọn này là điểm bắt đầu; điều kiện domain, legacy constraints và tool support có thể thay đổi kết luận. Quan trọng là diễn đạt **vì sao**.

## 14. Tính phát hiện của API và trải nghiệm phát triển

Một method xuất hiện trực tiếp trong class/interface được Java compiler, IDE, static analyzer, documentation generator và test doubles nhìn thấy theo các conventions thông thường.

Một method introduced bằng AOP có thể vẫn được tooling hỗ trợ tốt nếu engine có compiler integration, nhưng sẽ đòi:
- Plugin/processor/weaver được chạy đúng phiên bản.
- Generated source hoặc class artifact cùng build.
- Source-to-binary mapping.
- Annotation metadata và scopes nhất quán.
- Dependency locking và upgrade policy.
- Hướng dẫn debug stack traces/transformed code.

### 14.1. Điều gì xảy ra với người mới đọc code?

Nếu người đọc thấy `invoice.approve()` trong source, tìm class `Invoice` nhưng không thấy method và không biết weaving config, chi phí hiểu code tăng. Nếu operation quan trọng, đưa nó vào API trực tiếp có thể tăng khả năng bảo trì đáng kể.

### 14.2. Hidden coupling

Một aspect introduce `getTenant()` cho nhiều classes có thể tạo một mối phụ thuộc ngầm: những callers tưởng type có capability tự nhiên nhưng chỉ đúng khi module AOP đã được kích hoạt. Khi chạy unit test target **không weave**, code có thể không compile hoặc throw.

Nếu capability là thật sự bắt buộc, tài liệu hóa hợp đồng dependency và cân nhắc sửa type/adapter thay vì tạo hidden type requirement.

### 14.3. “Giảm boilerplate” không phải mục tiêu cao nhất

Loại bỏ 20 getters được copy có ích, nhưng nếu khiến build khó reproduce và tests chậm, lợi ích có thể không đủ. Ngược lại, một code-generation/toolchain được kiểm soát với structural introductions cho hàng nghìn types có thể đem lại lợi ích lớn. Đánh giá chi phí vòng đời, không chỉ dòng mã giảm.

## 15. Khi không sửa được source: thứ tự ưu tiên các phương án

Không có quyền sửa class không đồng nghĩa AOP luôn là giải pháp duy nhất.

### 15.1. Adapter typed, composition trước

Nếu third-party `ExternalRecord` không có `auditId()`, tạo:

~~~java
interface AuditedRecord {
    String auditId();
    ExternalRecord source();
}
~~~

Rồi có implementation adapter giữ reference tới target và ID được cấp hợp lệ. Caller nhận đúng `AuditedRecord`, không cần tưởng target class đã bị thay. Đây là API typed, reflection rõ và đơn vị ownership được công bố.

### 15.2. Mixin/introduction khi coverage lớn

Nếu hàng trăm types phải có cùng capability và công cụ hỗ trợ introduction chuẩn, có thể cân nhắc mixin:
- Tool có hỗ trợ generated implementation cho method mới?
- State instance hay shared?
- Những concrete types nào được chọn?
- Runtime/classloaders nào chịu phép biến đổi?
- Reflection/serialization/compatibility có cần nhìn introduced member?
- Conflict khi một target version mới tự thêm method trùng?
- Consumer compile-time view có nhận được type?
- Có thể rollback mà không phá client binary?

Nếu các câu trả lời có được chứng cứ tốt, AOP introduction có thể là lựa chọn đúng.

### 15.3. External registry khi metadata không phải domain state

Một map ID → metrics / weak association có thể hỗ trợ tracing/correlation khi không nên thay domain model. Nhưng tránh giữ target objects qua strong references trong registry sống dài. Bảo đảm eviction/cleanup, thread safety, cardinality budget và tenant isolation.

### 15.4. Bytecode weaving khi không có lựa chọn khác

Weaving có thể phù hợp cho một structural concern quan trọng mà source không thể sửa, nhưng cần:
- Kiểm soát compile/load stages và classloaders.
- Tests với artifact đã weave thật.
- Chiến lược versioning khi target library nâng cấp.
- Failure mode khi transformation không được áp dụng.
- Đánh giá security, legal/supportability và toolchain ownership.

Không sử dụng weaving chỉ để tránh một wrapper tường minh nếu wrapper đã đáp ứng API.

## 16. Source, binary và behavioral compatibility khi sửa trực tiếp

“Sửa type trực tiếp” không phải lựa chọn luôn không rủi ro. Một thay đổi class/interface phải được thiết kế versioning.

### 16.1. Source compatibility

Thêm abstract method vào interface có thể buộc các implementers đang có phải viết method mới khi compile lại. Thay generic bounds hoặc overloads có thể tạo ambiguity. Thêm constructor required parameter làm code cũ không compile.

Những điều này không luôn xấu: compiler báo nơi code phải thay có thể giúp **phát hiện sớm** những consumer chưa tuân hợp đồng mới, tốt hơn lỗi xuất hiện muộn do một introduction ẩn.

### 16.2. Binary compatibility

Không phải mọi source-compatible change đều binary-compatible và ngược lại. Ví dụ thay method/field descriptor, return type, interface hierarchy, constructor hoặc class artifact có thể ảnh hưởng linkage. Phải áp dụng luật Java binary compatibility cụ thể và test binaries từ version cũ.

Với weaving, cần test đặc biệt trường hợp client compile với class có introduced method nhưng runtime nạp class **chưa weave**: có thể lỗi như `NoSuchMethodError`. Không giả định compile success bảo đảm deployment đúng.

### 16.3. Behavioral compatibility

Ngay cả khi compile/link:
- Result có đúng domain meaning?
- `null` và `Optional.empty()` có phân biệt?
- Exceptions có đúng type/cause?
- Side effects có xảy ra đúng số lần?
- Identity, equality, hashCode và resource ownership có đúng?
- Async completion, cancellation và streams có giữ contract?
- New fields có initialized đúng?

Một introduced member và một method sửa trực tiếp **đều** cần behavioral tests.

### 16.4. Migration plan

Khi thay schema/model:
1. Thêm API hoặc value object mới.
2. Thiết kế backfill/default cho dữ liệu cũ.
3. Update persistence/schema và serializers.
4. Sửa callers theo staged rollout.
5. Thêm contract tests cho version cũ/mới.
6. Deprecate API cũ khi đã có migration path.
7. Rollback được nếu deployment không đồng bộ.

Nếu introduction từng che một thuộc tính thiếu, migration còn cần **lấy state từ proxy/registry** đưa về domain authoritative store, xác định conflicts và dữ liệu có thể bị mất khi wrapper hết vòng đời.

## 17. Serialization, reflection và đồng nhất dữ liệu

### 17.1. Khi field được thêm vào model

Các cơ chế serialization khác nhau có thể đọc fields/getters/annotations. Thêm field trực tiếp có thể đổi JSON/schema/Java serialization; không được tự suy mọi serializers sẽ tự tương thích. Nhưng việc thay đổi được **thể hiện trong source và migration** giúp consumer nhận biết sớm hơn.

### 17.2. Khi field chỉ nằm trong proxy handler

`target.getClass().getDeclaredFields()` không thấy field của handler. ORM/serializer đọc target có thể không lưu property mới. Nếu property cần persistence, một accessor trên wrapper chưa đủ nếu persistence layer tiếp tục lưu target gốc.

### 17.3. Reflection trên generated vs transformed type

Một interface proxy và target có runtime classes khác nhau. Source/bytecode weaving có thể tạo artifact chứa members mới, nên reflection trên target đã weave có thể thấy. Cần kiểm **đối tượng nào** và **artifact nào**, không chỉ tên interface.

### 17.4. Equality và identity

Nếu domain entity là value object có equality dựa trên ID, một proxy object riêng có thể có equality/hashCode không tương thích. Nếu map key thay target bằng proxy, behavior có thể đổi. Khi identity thuộc domain contract, hãy thiết kế trực tiếp hoặc giữ canonical adapter rõ, không cố giả lập reference equality bằng `equals()`: toán tử `==` không thể thay đổi cho hai objects riêng.

## 18. Các trường hợp nên tránh “dùng aspect làm sửa thiết kế”

### 18.1. Dùng advice để vá một null invariant

Nếu `User.email` được hứa non-null, đừng chờ advice tại `sendMail` rồi thay null bằng `"unknown"` để tiếp tục. Hãy validate ở constructor/factory/domain boundary và sửa dữ liệu sai. Advice chỉ là điểm instrumentation hoặc policy phụ.

### 18.2. Tự phát sinh field status bên ngoài aggregate

Đặt `WorkflowState` trong singleton aspect map không biến state thành đúng source of truth của domain. Hai object wrappers hoặc một direct target caller có thể quan sát khác nhau.

### 18.3. Dùng pointcut để bù việc thiếu interface chính thức

Nếu mọi consumer cần `Closeable` semantics, hãy đưa `close()`/ownership contract vào abstraction hoặc adapter. Một advice “đóng resource cuối method” có thể đóng sai nếu method trả stream/future cần resource sau khi return.

### 18.4. Dùng around advice để “thêm transaction” khi boundary bị phân mảnh

Có thể áp transaction-like policy ở crosscutting boundary, nhưng transaction semantics phụ thuộc resource manager, propagation, commit/rollback và async lifecycle. Nếu core invariant về atomic state không tồn tại ở layer đáng tin, chỉ bổ sung around advice quanh một method không chứng minh transaction đúng.

### 18.5. Tự “sửa lỗi” bằng fallback giá trị mặc định

Method trả `int`, aspect bắt mọi exception rồi `return 0`; code vẫn đúng primitive type nhưng có thể biến storage error thành “đếm thành công bằng 0”. Sửa error model/typed result hoặc chính sách fallback công khai thay vì che lỗi.

### 18.6. Cho aspect retry một command không idempotent

Một command gửi tiền có thể commit trước timeout; retry có thể nhân side effects dù caller cuối nhận `OK`. Phải sửa operation contract/idempotency hoặc tạo trusted retry boundary, không coi retry chỉ là option của aspect.

### 18.7. Gắn property per-request vào per-target aspect state

Một target singleton nhận nhiều requests song song; `aspect.currentTraceId` mutable field có thể bị overwrite. Nếu concern là request, sử dụng per-invocation/task context đúng scope; không sửa domain type để chứa trace ID hiện hành.

### 18.8. Chỉ kiểm thử proxy, bỏ qua direct calls và self-invocation

Một interceptor ở proxy có thể không thấy `this.internalMethod()`. Nếu validation/security invariant buộc chạy ở mọi internal path, sửa domain/trusted boundary thay vì tin mọi join point qua handler.

## 19. Quy trình ra quyết định có thể áp dụng ngay

### Bước 1 — Xác định capability có phải domain contract không

Viết một câu:

> “Mọi instance của type X phải ___, kể cả khi không có instrumentation hay proxy.”

Nếu điền được một invariant không tùy chọn, nghiêng về **sửa trực tiếp type, API hoặc domain owner**.

### Bước 2 — Xác định khách hàng sử dụng capability

Ai cần dùng?
- Compiler của các modules khác?
- Serializer/ORM?
- External APIs?
- Những clients chỉ giữ interface?
- Reflection/annotations?
- Một logger hoặc profiler?
- Một security boundary?

Nếu nhiều consumers chính thức cần contract, explicit interface thường hữu ích hơn hidden introduction.

### Bước 3 — Hỏi ai sở hữu dữ liệu và lifecycle

Capability có state nào?
- Persistent domain field?
- Per-target transient metadata?
- Per-proxy handler state?
- Per-invocation timestamp?
- Shared metrics counter?
- External resource?

Sở hữu sai state có thể nguy hiểm hơn việc viết thêm vài dòng code trong domain type.

### Bước 4 — Kiểm tra quyền sửa source và ràng buộc kỹ thuật

- Có thể sửa source class/interface không?
- Type thuộc vendor/legacy binary?
- Class là `final`/`record`/sealed?
- Tool hỗ trợ structural introduction đến mức nào?
- Compiler/runtime cùng thấy introduced API?
- Có nhiều classloaders, AOT/native hoặc hot reload?

Không đưa ra quyết định AOP khi chưa biết những điều kiện này.

### Bước 5 — Xác định mức độ thay đổi hành vi

- Chỉ quan sát?
- Có thêm method gọi từ caller?
- Có thay result/exception?
- Có short-circuit/caching?
- Có retry làm target chạy nhiều lần?
- Có effects lên concurrency, resource lifetime hoặc transaction?

Nếu thay đổi semantics domain, yêu cầu contract explicit và tests ở owner phù hợp.

### Bước 6 — So sánh chi phí vòng đời

Ước lượng/định tính:
- Dòng code boilerplate giảm.
- Toolchain/deployment complexity tăng.
- Debuggability/IDE support.
- Performance overhead.
- Test matrix.
- Risk khi nâng version library.
- Số types/join points chịu tác động.
- Rollback compatibility.

### Bước 7 — Chọn phương án đơn giản nhất giữ hợp đồng

Một thứ tự cân nhắc hữu ích, **không phải luật bắt buộc**:

1. **Sửa trực tiếp type/domain boundary** nếu đây là contract cốt lõi và có source.
2. **Composition/adapter** nếu không sửa source hoặc muốn cô lập integration.
3. **Advice** cho concern crosscutting trên join points đã tồn tại.
4. **Structural introduction/weaving** nếu thực sự cần capability áp đồng loạt vào nhiều types và toolchain hỗ trợ nhất quán.

Chọn theo nguyên nhân, không theo “công cụ hiện đang tiện”.

## 20. Scorecard để review một quyết định kiến trúc

Mỗi tiêu chí trả lời Có/Không hoặc Mức độ và kèm bằng chứng:

| Tiêu chí | Nghiêng sửa trực tiếp | Nghiêng aspect/introduction |
| --- | --- | --- |
| Thuộc tính là bất biến domain? | Có. | Không/metadata phụ. |
| Compiler phải bảo đảm mọi instance có capability? | Có. | Không, chỉ scoped wrapper. |
| Cần persistence/serialization chính thức? | Có. | Chỉ telemetry tạm. |
| Nhiều consumers cần gọi member trực tiếp? | Có. | Chỉ instrumentation module. |
| Thực hiện invariant tại mọi call path? | Có. | Verified interception đủ. |
| Source target do nhóm sở hữu? | Có. | Không, third-party. |
| Concern áp hàng trăm unrelated types? | Có thể, nhưng cần cân nhắc. | Có thể rất phù hợp. |
| Có state nhiều bước, transaction, lifecycle phức tạp? | Ưu tiên owner tường minh. | Chỉ nếu tool/owner có contract rõ. |
| Phụ thuộc toolchain weaving làm tăng rủi ro? | Ưu tiên source/API. | Chỉ dùng khi lợi ích đủ lớn. |
| Behavior chỉ quan sát và ít state? | Không bắt buộc sửa type. | Rất phù hợp. |
| Capability dễ biểu diễn bằng typed adapter? | Adapter có thể tốt hơn. | Introduction không bắt buộc. |
| Nhiều proxy cùng target phải dùng cùng state? | Domain/shared authoritative owner. | Per-target association nếu kiểm soát tốt. |

### 20.1. Không cộng điểm máy móc

Một invariant security “không được bypass” có thể quan trọng hơn mười mục hiệu năng hay boilerplate. Scorecard là công cụ thảo luận, không phải hàm số tự động chọn framework.

### 20.2. Ví dụ quyết định

“Thêm `Currency currency()` cho mọi money value” — đây có thể là tính chất cốt lõi của **Money** và liên quan phép tính. Nên sửa value object/API thay vì đem currency vào aspect state.

“Gắn trace baggage đã sanitize cho những method calls trong workflow” — metadata per-flow, áp rộng, thường không nên sửa mọi domain type; dùng context/instrumentation phù hợp.

“Gắn `Tagged` cho objects của library không thể sửa trong debug environment” — typed decorator/proxy hoặc introduction là lựa chọn thực tế, miễn tài liệu nói rõ wrapper mới sở hữu tag.

## 21. Ma trận kiểm thử trước khi quyết định và sau khi triển khai

### 21.1. Nếu sửa type trực tiếp

- Constructor/factory reject invalid state.
- Every implementation của interface đáp ứng contract.
- State transition invariant đúng trên success/error.
- Compile-time tests cho consumer API.
- Legacy data migration/serialization compatibility.
- Multithreaded use đúng theo thread-safety contract.
- Value equality/hashCode/identity semantics rõ.
- APIs async/lazy result vẫn giữ ownership.
- Rollback/deprecation plan và versioning.

### 21.2. Nếu dùng adapter/proxy/introduction

- `proxy instanceof IntroducedInterface` đúng khi được công bố.
- `target instanceof IntroducedInterface` đúng hoặc sai **theo cơ chế thực**, không suy đoán.
- Original operations giữ result/error/side effects.
- Introduced operations có implementation và initialization.
- Two proxies one target: state per-proxy/per-target đúng requirement.
- Direct target call có chính sách hợp lệ nếu bypass proxy.
- Self-invocation có được interceptor bao phủ không?
- Reflection `getClass()/getDeclaredMethods()` đúng artifact.
- Source compiler thấy các introduced methods khi cần.
- Runtime classloader nạp đúng transformed binary.
- Conflicts, overloads, generics erasure và sealed/final restrictions được test.
- Serialization schema và resource cleanup hợp lệ.
- Concurrent state không race; shutdown/async completion đúng.
- Security policy không phụ thuộc interface marker chưa xác thực.

### 21.3. Nếu dùng advice cho concern crosscutting

- Pointcut thực sự chọn đúng occurrences.
- Advice order được khai báo và xác minh.
- Short-circuit có bỏ qua policy bắt buộc không?
- Return/exception transparency hoặc transformation được công bố.
- Logging/metrics failure không che target failure nếu best-effort.
- `ThreadLocal` restore/remove ở success/error.
- Retry budget/idempotency/timeout đúng.
- Async stage completion được quan sát tại đúng thời điểm.
- Context/registry không giữ args/results/targets vô hạn.
- Performance overhead và p99 được đo dưới tải.

### 21.4. Golden-path test không đủ

Một proxy có thể pass `credit(5)` mà fail `credit(-1)`; một adapter có thể đúng với một instance nhưng sai khi hai wrappers bọc cùng target; một Weaver có thể hoạt động trong IDE và thiếu ở production. Các negative paths chính là bằng chứng của architectural correctness.

## 22. Những hiểu lầm phổ biến

**“Công cụ hỗ trợ introduction thì luôn nên dùng thay sửa class.”** Không. Khả năng kỹ thuật không thay thế quyết định về domain contract.

**“Sửa class trực tiếp là trái tinh thần AOP.”** Không. AOP bổ sung khả năng tổ chức cross-cutting concerns, không có mục tiêu thay mọi domain/API design.

**“Một interface proxy thêm capability nghĩa là target gốc đã implements.”** Không với JDK delegating proxy.

**“Per-proxy field là per-target field.”** Không nếu hai wrappers cùng target giữ hai states độc lập.

**“Sửa source lúc nào cũng dễ, không cần migration.”** Không. API/schema/versioning có thể gây breaking changes.

**“Method introduced không xuất hiện trong class source nhưng tất cả compilers đều nhìn thấy.”** Không. Tùy compiler/weaver/build artifact.

**“Một method mới có thể overload chỉ bằng return type khác.”** Không trong Java source thông thường.

**“Final class cấm mọi proxy và mọi AOP.”** Không. Final cấm subclass theo Java, không cấm bọc qua interface hay các cách instrumentation hợp lệ.

**“Aspect là nơi thích hợp để giữ trạng thái domain vì nó dùng chung nhiều lớp.”** Không nếu nó tạo nguồn sự thật thứ hai hoặc sai lifecycle.

**“Có `instanceof Auditable` là caller được phép audit/reset.”** Không. Type capability không thay thế authorization.

**“Log đầy đủ nghĩa là đã thực thi audit nghiệp vụ bền vững.”** Không. Logging/transaction commit/audit persistence là những events khác nhau.

**“Chỉ cần priority advice là mọi direct call cũng được kiểm soát.”** Không. Ordering không sửa proxy bypass.

**“Một proxy có cùng API sẽ có cùng identity/equality/class.”** Không mặc định.

**“Return type hợp lệ chứng minh postcondition.”** Không; result và side effects phải đúng.

**“Retry chỉ làm code chịu lỗi tốt hơn.”** Có thể lặp side effects; cần domain idempotency.

**“Chi phí introduction chỉ là CPU runtime.”** Còn build, security, migration, classloader, debugging, testing và vận hành.

**“Đưa traceId vào mọi domain entity là rõ ràng hơn scoped context.”** Không nếu traceId thuộc invocation, không phải entity.

**“Tách mọi thứ sang aspect làm type nhỏ hơn nên tốt hơn.”** Type nhỏ vì thiếu invariant có thể là **thiết kế kém rõ**, không phải clean design.

## 23. Bài tập vận dụng kèm lời giải

### Bài 1 — Order status

Mọi `Order` phải giữ trạng thái đã commit và kiểm quy tắc `NEW → PAID → SHIPPED`. Nên dùng field trong aspect hay domain type?

**Đáp án:** Nghiêng sửa domain state machine/type trực tiếp hoặc owner authoritative, vì status là invariant nghiệp vụ. Advice có thể quan sát transitions.

### Bài 2 — Trace ID

Một request đọc hàng chục domain objects; cần gắn trace ID vào logs của mỗi call. Nên thêm `traceId` vào mọi entity?

**Đáp án:** Không mặc định. Trace ID thuộc logical operation; dùng scoped context và instrumentation được propagate/cleanup đúng.

### Bài 3 — Library không sửa được

Một `Reader` từ third-party cần capability `Tagged` chỉ cho diagnostic tools. Có thể dùng cách nào?

**Đáp án:** Typed adapter/JDK interface proxy implements `Tagged`, hoặc introduction nếu tool phù hợp. Công bố tag thuộc wrapper hay target association.

### Bài 4 — Hai wrappers một target

P1 và P2 cùng bọc target T; mỗi handler có field `auditId`. P1 trả A, P2 trả B. Nếu auditId phải là định danh bền vững của T thì sai ở đâu?

**Đáp án:** State owner sai scope. Cần một nguồn authoritative theo T hoặc đưa vào domain API, không per-proxy.

### Bài 5 — Compiler guarantee

Một method `getCurrency()` được add chỉ bằng runtime proxy nhưng mọi consumer có biến type `Money` cần gọi nó. Điều gì thiếu?

**Đáp án:** Compile-time type contract; cần sửa Money interface/value object hoặc trả một typed adapter được công bố.

### Bài 6 — Retry charge

Aspect tự retry `charge()` sau timeout, attempt đầu có thể đã commit. Caller cuối nhận `OK`. Có an toàn chỉ vì result đúng type?

**Đáp án:** Không. Cần idempotency/transaction policy, vì side effects có thể nhân đôi.

### Bài 7 — Record

Muốn mọi `Money` record có `currency` bắt buộc. Có nên giữ currency trong external map của aspect?

**Đáp án:** Nếu currency thuộc giá trị tiền, nghiêng sửa record components/schema và migration, giữ invariant tại constructor/factory.

### Bài 8 — Sealed interface

Một sealed hierarchy chỉ cho phép hai implementations. Có thể tự tạo runtime proxy implement interface ấy mà không cần xét permitted subtypes?

**Đáp án:** Không. Java sealed type rules áp dụng; cần xem thiết kế hierarchy và runtime/tool capability.

### Bài 9 — Reflection

Proxy có `auditId()`, nhưng `target.getClass().getDeclaredMethods()` không thấy method đó. Là lỗi introduction?

**Đáp án:** Không nếu mục tiêu là interface introduction trên proxy. Nó sẽ là lỗi expectation nếu tài liệu từng hứa field/method được weave vào target class.

### Bài 10 — Một helper nhỏ

Chỉ một class cần method `displayName()` thuần túy. Có nên cài structural weaving pipeline?

**Đáp án:** Thường không. Method trực tiếp, utility hoặc decorator có thể đơn giản và dễ bảo trì hơn.

### Bài 11 — Auth policy

Một proxy mới có `resetState()` public và hiện mọi caller có proxy có thể gọi. Cần gì?

**Đáp án:** Authorization/validation ở trusted boundary, negative tests; một interface marker không phải permission.

### Bài 12 — Compiler thấy method nhưng runtime không có

Client compile với artifact đã weave, deployment lại nạp binary chưa weave. Có thể xuất hiện vấn đề gì?

**Đáp án:** Lỗi linkage/cast/behavior tùy call site, chẳng hạn `NoSuchMethodError`. Đồng bộ artifact/toolchain và test production bundle.

### Bài 13 — Async stream

Một introduced method trả `Stream<Row>`. Advice đóng resource ở `finally` khi method return. Có thể sai vì sao?

**Đáp án:** Stream có thể lazy, caller chưa tiêu thụ; resource ownership cần sống tới khi stream/caller đóng theo contract.

### Bài 14 — State đồng thời

Một introduced field `int accesses` tăng bằng `++` trên target singleton được 100 threads gọi. Per-target có bảo đảm đúng không?

**Đáp án:** Không; cùng target vẫn shared giữa threads. Dùng atomic/synchronization phù hợp.

### Bài 15 — Source sửa được nhưng nhiều lớp

Có 200 domain classes đều cần `toAuditLabel()`. Nên mặc định dùng introduction?

**Đáp án:** Chưa đủ dữ liệu. Nếu label chỉ phụ trợ và uniform, mixin/introduction/utility có thể phù hợp; nếu mỗi type có semantics khác và công bố API, interface typed với implementations hoặc adapter có thể rõ hơn. Đánh giá toolchain và test cost.

## 24. Checklist cuối trước khi quyết định

1. **Hợp đồng:** Capability mới có phải bản chất của type/domain không?
2. **Invariant:** Có bắt buộc đúng với mọi target, kể cả direct calls?
3. **Identity:** Property thuộc target, wrapper hay invocation?
4. **State owner:** Có một nguồn sự thật duy nhất không?
5. **Compiler:** Consumer có cần nhìn API mới lúc compile không?
6. **Source control:** Có quyền sửa class/interface target không?
7. **Scope:** Concern áp cho vài types hay hàng trăm join points?
8. **Tool support:** Engine có method/field/interface introduction thực hay chỉ advice?
9. **Mechanism:** Proxy, decorator, generated subclass hay woven target artifact?
10. **Class constraints:** `final`, record, sealed, constructors, modules?
11. **Conflict:** Existing methods/fields, generics erasure, default methods?
12. **API:** Có phương án interface/adapter/value object đơn giản hơn?
13. **Contracts:** Return/error/side effects có giữ đúng?
14. **Security:** Trusted boundary và authorization có bị bypass?
15. **Concurrency:** Shared/per-target state có thread-safe, visibility đúng?
16. **Async:** Task completion/streams/resource lifecycle rõ?
17. **Persistence:** State mới có cần lưu, backfill và schema migration?
18. **Reflection:** Consumer/tool có nhìn đúng class và annotations không?
19. **Binary:** Client runtime nạp đúng transformed artifact không?
20. **Build:** Toolchain ổn định, version locked, debug được?
21. **Tests:** Có contract tests cho direct target, wrapper, woven và negative paths?
22. **Observability:** Metrics/trace IDs đặt đúng scope chưa?
23. **Performance:** Contention, allocation, memory retention, p99?
24. **Maintenance:** Người đọc source có tìm thấy behavior quan trọng không?
25. **Rollback:** Có thể rollback mà không phá client phụ thuộc introduced member?

## Kết luận

**Khi một khả năng là hợp đồng cốt lõi của domain, cần được compiler xác nhận, bảo vệ invariant ở mọi đường gọi, hoặc có state/persistence/lifecycle quan trọng, ưu tiên sửa trực tiếp type, interface, value object hoặc owner nghiệp vụ.** Cách này biến yêu cầu thành điều kiện tường minh mà caller, IDE và tests đều nhìn thấy, thay vì một dependency ẩn vào cấu hình aspect.

**Khi yêu cầu là cross-cutting concern, áp rộng cho nhiều loại, không làm biến dạng semantics cốt lõi và interception coverage đã được xác minh, AOP có thể giảm duplication và tách instrumentation rất tốt.** Với thư viện không thể sửa, adapter/proxy/introduction là lựa chọn thực dụng, miễn nói rõ capability nằm trên wrapper hay class đã weave, state thuộc ai, clients thấy API ở giai đoạn nào và có cơ chế cleanup/compatibility phù hợp.

Đừng đánh đồng **“có thể thêm bằng aspect”** với **“nên thêm bằng aspect”**. Một kiến trúc tốt đặt **hợp đồng nghiệp vụ tại nơi dễ nhìn và kiểm chứng nhất**, rồi dùng Aspect/AOP để bổ sung những mối quan tâm thật sự xuyên suốt — thay vì che đi một mô hình kiểu cần được sửa.
