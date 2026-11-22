# Kế thừa aspect khi mô hình ngôn ngữ cho phép trong Aspect/AOP

Trong lập trình hướng khía cạnh (**Aspect-Oriented Programming — AOP**), aspect đóng gói những mối quan tâm cắt ngang (*cross-cutting concerns*) bằng **pointcut**, **advice** và đôi khi có trạng thái hoặc thành phần hỗ trợ. Khi nhiều aspect làm những việc gần giống nhau — cùng ghi trace, cùng đo thời gian, cùng áp một quy tắc kiểm tra nhưng lên các nhóm join point khác nhau — việc sao chép toàn bộ pointcut và advice vào từng aspect dễ tạo lỗi bảo trì.

Một số **ngôn ngữ và mô hình AOP** cho phép **kế thừa aspect** (*aspect inheritance*), nhất là thông qua **abstract aspect** làm lớp cơ sở và những concrete aspect chuyên biệt hóa. Trong mô hình như vậy, phần cha có thể định nghĩa các hành vi dùng chung và những điểm mở rộng; phần con cung cấp pointcut hoặc phương thức hỗ trợ cụ thể.

Tuy nhiên, **không phải hệ AOP nào cũng cho phép kế thừa aspect**. Có công nghệ chỉ hỗ trợ interceptor qua proxy, có công nghệ dùng cấu hình hoặc annotation, có công nghệ hỗ trợ mã khai báo aspect riêng, và có những ràng buộc đặc biệt: class nào được phép làm cha, aspect nào được phép bị kế thừa, kiểu pointcut nào là abstract, cách advice được truyền xuống, cách instance được tạo và các quy tắc precedence.

Điểm then chốt của bài: **kế thừa dùng để tái sử dụng và chuyên biệt hóa một hợp đồng AOP rõ ràng, không phải cách tự động hoán đổi advice hoặc kết hợp mọi aspect thành một cây kế thừa**. Cần phân biệt **thừa kế hành vi**, **chọn join point**, **vòng đời instance** và **thứ tự nhiều aspect chạy tại cùng điểm**.

Bài tập trung vào **Aspect/AOP cơ bản và nâng cao nói chung**. Phần cú pháp AspectJ được chú thích như một ví dụ riêng cho ngôn ngữ có hỗ trợ; phần Java 17 chạy được bằng JDK thuần mô phỏng ý tưởng **abstract base policy + concrete specializations** qua chuỗi interceptor, không tuyên bố JDK proxy là một bộ aspect weaver đầy đủ.

## 1. Mục tiêu học tập

Sau bài, bạn có thể:

1. Giải thích vì sao người ta trừu tượng hóa những hành vi cắt ngang giống nhau thay vì sao chép nhiều aspect.
2. Phân biệt **abstract aspect**, **concrete aspect**, **abstract pointcut**, advice được định nghĩa ở cha và method hỗ trợ có thể override.
3. Hiểu kế thừa aspect **phụ thuộc khả năng của mô hình ngôn ngữ**; không coi mọi bộ AOP là một hệ kế thừa giống Java class.
4. Xác định những phần nên cố định ở cha và những phần nên để con chuyên biệt hóa: tập join point, định dạng nhãn, chính sách lỗi, lựa chọn trạng thái.
5. Phân biệt **kế thừa declaration** với **advice precedence** và quan hệ lồng nhau của around advice.
6. Đánh giá **kế thừa và chính sách tạo aspect instance** theo singleton/per-target/per-flow khi công nghệ hỗ trợ.
7. Nhận diện những giới hạn của `private`/`protected`, module/package, abstract contract, constructor và trạng thái mutable.
8. So sánh inheritance với **composition, delegation, helper service, named pointcut và reusable interceptor**.
9. Biên dịch, chạy và giải thích ví dụ Java 17 với một abstract interceptor cùng hai concrete specializations, giá trị trả về và ngoại lệ được bảo toàn.
10. Thiết kế kiểm thử tránh duplicate advice, pointcut chọn sai, proxy bypass, precedence không rõ và coupling giữa aspect cha–con.

## 2. Những khái niệm phải tách riêng

| Khái niệm | Vai trò | Ví dụ |
| --- | --- | --- |
| **Aspect definition** | Khai báo mối quan tâm cắt ngang | `TracingAspect` |
| **Abstract aspect** | Bản thiết kế chưa cụ thể hóa hoàn toàn, không dùng trực tiếp như concrete instance theo mô hình hỗ trợ | `BaseTracing` |
| **Concrete aspect** | Một aspect có đủ thông tin để được áp dụng/khởi tạo theo chính sách của công nghệ | `OrderTracing` |
| **Abstract pointcut** | Hợp đồng chọn join point còn chờ phần con cung cấp điều kiện | “Nhóm operation nào phải trace?” |
| **Concrete pointcut** | Điều kiện chọn join point thực tế | “Execution của `OrderService.place(..)`” |
| **Advice** | Hành vi before/after/around gắn với điểm phù hợp | Ghi start, ghi result, giữ exception |
| **Support method/field** | Phần code và state hỗ trợ advice | Formatter, counter |
| **Instantiation policy** | Quy định số aspect instance và phạm vi mỗi instance | Shared hoặc per-flow nếu hỗ trợ |
| **Advice precedence** | Thứ tự tương đối của nhiều advice/aspect tại một join point | Auth bao ngoài Trace |
| **Structural introduction** | Bổ sung member/quan hệ type nếu công nghệ hỗ trợ | Inter-type method |
| **Composition/delegation** | Dùng một đối tượng/cơ chế khác để chia sẻ hành vi | `AuditSink` hoặc `Policy` |

**Kế thừa aspect không đồng nghĩa việc target class được kế thừa**. Ví dụ `OrderTracing extends BaseTracing` mô tả quan hệ giữa **hai định nghĩa aspect**, chứ không làm `OrderService` kế thừa `BaseTracing`.

Và **kế thừa aspect không phải kế thừa giao diện API của đối tượng đích**. Một aspect áp dụng advice ở execution của `order.place()` không tự làm `Order` có thêm method hay field; khả năng sửa cấu trúc là một cơ chế khác.

## 3. Vì sao cần trừu tượng hóa aspect?

Giả sử có ba nghiệp vụ:

```text
OrderService.place()    -> cần tracing
InvoiceService.create() -> cần tracing
ShippingService.send()  -> cần tracing
```

Nếu mỗi aspect viết lại phần ghi trước/sau và xử lý lỗi, chúng dễ khác nhau vô ý:

- Nhóm A log thời gian cả nhánh throw, nhóm B chỉ log sau return.
- Nhóm C bắt `Exception` rồi trả fallback, gây thay đổi hợp đồng nghiệp vụ.
- Nhãn log của từng nhóm không nhất quán.
- Một aspect giữ đối số trong field singleton còn những aspect khác dùng biến cục bộ.
- Khi đổi phương thức đặt correlation ID hoặc che dữ liệu nhạy cảm, phải sửa nhiều nơi.
- Một nhóm retry nhầm khi logging thất bại.

Một **base abstraction** có thể chịu trách nhiệm cho bất biến chung:

```text
on selected join point:
    begin observation
    try:
        result = proceed()
        record normal result
        return result
    catch original error:
        record failure
        rethrow original error
    finally:
        release local observation state
```

Các concrete aspects chỉ xác định **những join point nào thuộc phạm vi** hoặc **nhãn/policy nào phù hợp**. Như vậy tránh nhân bản khung điều khiển vốn khó bảo trì.

### 3.1. Trừu tượng hóa không phải gom mọi chính sách vào một cha

Một base aspect làm cả xác thực, cache, retry, transaction và audit có thể trở thành một “siêu aspect” với nhiều flag tùy chỉnh. Khi đó các concrete aspects bị kéo vào những phụ thuộc và thứ tự phức tạp, thậm chí một subclass vô tình vô hiệu kiểm tra bắt buộc.

Chỉ gom các phần thực sự có **bất biến và lifecycle chung**. Những mối quan tâm khác nhau nên được **kết hợp qua composition/precedence/coordinator** khi cần, thay vì cố ép vào cùng một cây kế thừa.

## 4. Mô hình abstract aspect và concrete aspect

Trong mô hình ngôn ngữ hỗ trợ kiểu này:

```text
AbstractObservationAspect
    |
    +-- shared advice: before/around/after
    +-- helper: normalizeName(), safeRecord()
    +-- abstract pointcut: observedOperations()
    |
    +-- OrderObservationAspect
    |     +-- observedOperations = OrderService.place(..)
    |
    +-- InvoiceObservationAspect
          +-- observedOperations = InvoiceService.create(..)
```

Phần cha định nghĩa “**quan sát hoạt động đã được chọn như thế nào**”. Phần con định nghĩa “**hoạt động nào được chọn**”. Phải kiểm tra ngữ nghĩa của công cụ để biết advice được kế thừa/buộc vào concrete pointcut theo cách nào.

### 4.1. Vì sao abstract aspect không nên áp dụng độc lập?

Abstract aspect có thể còn **abstract pointcut chưa được định nghĩa** hoặc contract chưa được đáp ứng. Nếu runtime tự xem nó là một concrete aspect bên cạnh mọi subclass, lời gọi có thể bị ghi lặp. Trong mô hình abstract-aspect inheritance phù hợp, chỉ các định nghĩa **concrete hợp lệ** mới được áp dụng như những aspect hoàn chỉnh theo instantiation policy.

Không suy rằng một abstract aspect không thể chứa advice: nó có thể có advice **đã viết sẵn** nhưng phải có concrete context để áp dụng.

### 4.2. Pointcut là hợp đồng chuyên biệt hóa

Một abstract pointcut tương tự một “hook” để concrete aspect cung cấp phạm vi join point. Điều khác với abstract Java method là **pointcut mô tả một tập sự kiện trong chương trình**, không chỉ trả một giá trị bằng một lời gọi hàm thông thường.

Nếu con định nghĩa một pointcut **quá rộng**, advice chung ở cha có thể chạy tại hàng nghìn điểm và gây đệ quy khi nó ghi log qua một method cũng được chọn. Nếu định nghĩa **quá hẹp**, những điểm cần bảo vệ có thể không khớp.

### 4.3. Concrete aspect phải đáp ứng những gì?

Tùy mô hình, phần con có thể phải:

- Cung cấp tất cả abstract pointcuts còn thiếu;
- Cài những abstract helper methods được cha yêu cầu;
- Đáp ứng quy tắc truy cập `public`/`protected`/package/private;
- Tuân thủ hạn chế về superclass và instantiation policy;
- Không tạo member signatures xung đột;
- Cung cấp một pointcut hợp lệ trong những join point được weaver hỗ trợ;
- Được đưa vào phạm vi biên dịch/weaving và đóng gói đúng.

Không được coi một khai báo aspect “extends” thành công ở source là bằng chứng mọi advice đã được áp dụng đúng trong artifact runtime.

## 5. Ví dụ cú pháp AspectJ: abstract pointcut và inherited advice

Dưới đây là **minh họa thuộc ngôn ngữ AspectJ**; đây không phải code `javac` thường biên dịch được. Giả định dự án có lớp `demo.OrderService` chứa phương thức `place(..)`, lớp `demo.InvoiceService` chứa `create(..)` và dùng compiler/weaver phù hợp.

```java
// File: BaseObservation.aj
package demo;

public abstract aspect BaseObservation {
    protected abstract pointcut selected();

    before(): selected() {
        System.out.println("OBSERVE before");
    }

    after() returning: selected() {
        System.out.println("OBSERVE returned");
    }

    after() throwing(Throwable error): selected() {
        System.out.println("OBSERVE failed "
                + error.getClass().getSimpleName());
    }
}
```

Hai concrete specializations:

```java
// File: OrderObservation.aj
package demo;

public aspect OrderObservation extends BaseObservation {
    protected pointcut selected():
        execution(* demo.OrderService.place(..));
}
```

```java
// File: InvoiceObservation.aj
package demo;

public aspect InvoiceObservation extends BaseObservation {
    protected pointcut selected():
        execution(* demo.InvoiceService.create(..));
}
```

**Ý nghĩa:**

1. `BaseObservation` là **abstract aspect** chứa advice và khai báo `selected()` chưa được giải nghĩa cụ thể.
2. `OrderObservation` và `InvoiceObservation` cung cấp pointcut ở các join point khác nhau.
3. Khung trước/sau/nhánh lỗi được định nghĩa **một lần**.
4. Vì pointcut của hai con chọn nhóm phương thức khác nhau, một lời gọi `OrderService.place(..)` thường chỉ khớp phần specialization tương ứng; nếu các pointcut **chồng lên nhau**, có thể có nhiều advice từ nhiều concrete aspects cùng chạy.
5. `after returning` chỉ biểu thị **method returned normally**; không được suy “nghiệp vụ đã commit” chỉ từ việc không có exception.

**Lưu ý ngữ pháp:** Đây là các tệp `.aj`; `pointcut`, `before`, `after`, `returning` và `execution(* ...)` thuộc cú pháp AspectJ, không phải từ khóa AOP chung hoặc code Java tiêu chuẩn. Cần kiểm tra chính xác quy tắc visibility và override abstract pointcut theo phiên bản toolchain dùng thật.

### 5.1. Một root có thể được chọn bởi hai concrete aspects

Nếu `OrderObservation` chọn `execution(* OrderService.*(..))` còn `InvoiceObservation` lại chọn một pattern chung bao gồm `OrderService.place(..)`, cùng join point có thể có hai bộ advice cùng chạy.

Kế thừa từ cùng abstract base **không tự loại các điểm giao nhau**. Công cụ có thể tạo instance cho từng concrete aspect và áp từng advice; phải xem **phạm vi pointcut và precedence**, không nghĩ rằng “chỉ chạy lớp con gần nhất”.

### 5.2. Advice inheritance không phải Java method overriding

Một khai báo `before(): selected() { ... }` không phải một Java method tên `before` để subclass dùng `@Override` rồi thay thân tùy ý. Ngôn ngữ AOP có quy tắc riêng về advice declaration, inheritance và precedence.

Nếu muốn phần con thay đổi hành vi có kiểm soát, thiết kế **method hook rõ ràng** hoặc inject một policy/delegate, thay vì giả định có thể override trực tiếp bất kỳ advice nào như overriding method.

## 6. Kế thừa và giới hạn của ngôn ngữ

Không có một luật kế thừa aspect áp dụng cho mọi công nghệ AOP:

| Câu hỏi | Cần xác minh |
| --- | --- |
| Có hỗ trợ `abstract aspect` không? | Một số ngôn ngữ có, nhiều proxy frameworks không có khai báo này |
| Aspect con được extends loại nào? | Abstract aspect, class thông thường hoặc interface tùy quy tắc |
| Concrete aspect có cho subclass tiếp không? | Có mô hình hạn chế việc mở rộng concrete aspect |
| Advice từ cha có kế thừa không? | Ngữ nghĩa khai báo và phạm vi concrete aspect |
| Pointcut abstract phải được con định nghĩa thế nào? | Tên, signature, modifier, tham số binding |
| Abstract helper Java methods có được dùng không? | Nếu ngôn ngữ hỗ trợ thành phần Java trong aspect |
| State/instantiation policy có được kế thừa không? | Theo mô hình và các ràng buộc riêng |
| Có nhiều base aspects không? | Java-class-like inheritance có thể chỉ có một superclass |
| Private method/field của cha truy cập được không? | Visibility và đặc quyền riêng của ngôn ngữ |
| Có xung đột tên giữa cha/con không? | Overload, overriding, hiding, ITD collision |
| Có cần weave subclass và target riêng? | Toolchain và giới hạn join point |
| Abstract aspect có được đóng gói thành library không? | Binary compatibility và weaver support |

Trong một mô hình như AspectJ, nên đọc **các hạn chế riêng của aspect inheritance** thay vì áp đặt hoàn toàn quy tắc subclass của class Java thường. Ví dụ, không được mặc định mọi concrete aspect được phép có concrete aspect subclass; tính hợp lệ phải xem chính sách ngôn ngữ.

### 6.1. Không nhầm nhiều interface với nhiều superclass

Java hỗ trợ một lớp kế thừa một superclass trực tiếp nhưng có thể triển khai nhiều interfaces. Điều này **không có nghĩa** một aspect có thể extends nhiều base aspects để “nhận mọi advice”. Nhiều mối quan tâm dùng chung nên có thể được **ghép các aspect riêng**, dùng helper/delegate hoặc chiến lược composition.

### 6.2. Kế thừa class thông thường không đồng nghĩa aspect hợp lệ

Một AOP language có thể cho phép aspect kế thừa những lớp hỗ trợ nhất định, nhưng không tự biến mọi `class BaseLogger` thành base aspect mang pointcut/advice. Cần biết **metadata/cú pháp** nào đưa một type vào mô hình aspect.

Tương tự, việc một Java class `extends` một helper không bảo đảm pointcut của helper tồn tại hoặc được kích hoạt.

## 7. Template method và các điểm mở rộng an toàn

Mẫu thiết kế **Template Method** là một cách tư duy hiệu quả:

```text
Base aspect:
    chọn pointcut theo contract
    bắt đầu quan sát
    invoke business exactly once
    ghi kết quả hoặc lỗi
    dọn state trong finally

Concrete aspect:
    cung cấp tập join point
    cung cấp nhãn/context hợp lệ
    có thể định nghĩa chính sách trình bày
```

**Bất biến nên khóa ở base:** advice quan sát không nuốt lỗi của target, không gọi `proceed` lặp nếu không có chủ đích, không rò state ra ngoài scope và không tự ghi dữ liệu nhạy cảm.

**Điểm mở rộng nên đủ nhỏ:** lựa chọn pointcut, nhãn, cách lấy metadata không nhạy cảm, định dạng kết quả quan sát. Nếu một subclass cần thay đổi hoàn toàn semantics retry hoặc transaction, đó có thể là **một aspect khác**, không nên gắn vào cùng base chỉ vì tên “logging”.

### 7.1. Hook được gọi từ advice phải có hợp đồng lỗi

Giả sử base advice gọi một method `formatLabel()` do con override. Nếu con ném lỗi, lỗi này xảy ra **trong advice**, có thể khiến target không chạy hoặc che kết quả target.

Một base class có thể cung cấp vùng bảo vệ với chính sách cụ thể cho **lỗi quan sát tùy chọn**, nhưng không nên bắt mọi `Throwable` quanh toàn bộ `proceed` rồi biến cả lỗi nghiệp vụ thành “logger offline”.

### 7.2. Không lấy state per-request làm field singleton

Nếu base aspect có field mutable `currentRequestId` và concrete aspect được dùng chung nhiều thread, người gọi A/B có thể ghi đè nhau. Dù field được kế thừa đúng cú pháp, **vòng đời và thread safety** vẫn phải đúng.

Với dữ liệu chỉ thuộc một invocation, dùng biến cục bộ. Nếu phải chia sẻ nhiều join points trong dynamic flow, dùng mô hình state/scope phù hợp (per-flow nếu công nghệ hỗ trợ, hoặc context rõ ràng). Kế thừa không tự cấp state độc lập cho mỗi request.

## 8. Đặt tên pointcut, member và khả năng tương thích

Trong một hệ có nhiều lớp aspect:

```text
BaseObservation
  |
  +-- FinanceObservation
  +-- WarehouseObservation
  +-- UserObservation
```

Tên `selected()`, `onSuccess()`, `counter` có thể được kế thừa hoặc che/override theo semantics của ngôn ngữ. Nếu một subclass khai báo lại một thành phần cùng tên nhưng sai signature, kết quả có thể là **một declaration mới** chứ không phải override như dự tính.

### 8.1. Tách namespace và ownership

- Định nghĩa một contract rõ cho abstract pointcut và các tham số binding.
- Đặt tên helper method nêu rõ ý nghĩa thay vì `handle`, `run` quá chung.
- Dùng `protected` cho hook thật sự dành cho subclass nếu ngôn ngữ hỗ trợ; giữ helper nội bộ là private khi thích hợp.
- Cố định các API không muốn con đổi theo khả năng của ngôn ngữ, tránh vô tình phá invariants.
- Không để nhiều concrete aspects cùng giới thiệu method/field cùng signature vào một target nếu công cụ không có quy tắc an toàn rõ.
- Kiểm tra tên method của target sau khi thư viện nâng cấp: một pointcut wildcard hoặc introduction có thể chọn/xung đột thành phần mới.

### 8.2. Overload và pointcut binding

Một abstract pointcut có thể cần binding đối số, ví dụ một `orderId`, nhưng concrete pointcut chọn những phương thức có signature khác nhau. Khi đó contract binding có thể không phù hợp:

```text
Base requires: selected(String id)
Child A chooses: work(String)
Child B chooses: work(int)
```

Nếu `Child B` không thể cung cấp một `String` theo semantics của pointcut language, không thể chỉ đổi tên tham số rồi coi là đúng. Cần **hợp đồng type rõ** hoặc dùng một abstraction trung gian cho metadata quan sát.

### 8.3. Generics và erasure

Một helper Java method trong aspect có thể chịu những luật Java về erasure: `process(List<String>)` và `process(List<Integer>)` không phải hai overload hợp lệ trong cùng class sau erasure. Khi mở rộng base helper, phải tính cả bridge methods, covariant return và visibility.

Đừng biến một xung đột Java type system thành “thứ tự aspect” — advice precedence không giải quyết duplicate method declarations.

## 9. Vòng đời instance không tự được suy từ cây kế thừa

Một điểm dễ sai: thấy `OrderObservation extends BaseObservation` rồi nghĩ runtime tạo:

```text
one BaseObservation instance + one OrderObservation instance
```

Không thể suy vậy. Trong mô hình kế thừa OO, instance subclass thường **chứa phần state được kế thừa từ base**, không nhất thiết có một object base riêng như sibling aspect. Abstract aspect thường không được áp dụng như một concrete aspect độc lập.

Với **hai concrete subclasses** `OrderObservation` và `InvoiceObservation`, chúng có thể có **những aspect instances riêng** theo instantiation policy của từng concrete aspect. Tuy nhiên phạm vi và số lượng object còn phụ thuộc công nghệ AOP.

### 9.1. Shared state trong field của base

Nếu base định nghĩa `protected long counter`, mỗi concrete aspect instance có một field state thuộc instance đó theo semantics OO phù hợp. Nhưng nếu base dùng `static long counter`, dữ liệu static có thể được chia sẻ trong phạm vi class/loader, không trở thành per-subclass counter tự động.

Với nhiều thread, counter mutable không đồng bộ có thể mất cập nhật. Dùng cấu trúc concurrency đúng khi dữ liệu là aggregate toàn cục; dùng biến invocation-local khi đó là dữ liệu một lời gọi.

### 9.2. Per-control-flow và nested roots

Một số mô hình AOP hỗ trợ instantiation theo dynamic control flow (những khái niệm như `percflow`). Khi abstract/concrete aspects có điều kiện flow, phải xác minh:

- Chính sách instantiation được khai báo trên type nào;
- Có được con kế thừa/đổi chính sách ấy không;
- Mỗi root tạo những activation/instances nào;
- Nếu root lồng nhau, state dùng instance của root nào;
- Khi root ném lỗi, binding được dỡ lúc nào;
- Có async task khác thread tham gia flow không hay cần propagation riêng.

Không tự đồng nhất “inherit aspect” với “inherit dynamic call stack”. Kế thừa là **quan hệ type**, còn cflow là **quan hệ lời gọi runtime**.

### 9.3. Khởi tạo và cleanup

Một constructor hoặc field initializer trên base có thể chạy khi tạo concrete aspect instance theo những quy tắc cụ thể, nhưng không dùng điều đó làm chứng cứ rằng mọi target invocation có một instance mới.

Tài nguyên được base tạo ra như file, socket, listener hoặc cache cần **owner, cleanup và lifecycle**. Một concrete aspect bị tắt/weaver không áp dụng không nhất thiết kích hoạt destructor hay hoàn nguyên những đăng ký đã tạo.

## 10. Kế thừa advice khác precedence giữa nhiều aspect

Giả sử có hai concrete aspects:

```text
SecurityAspect     -> guards execution of transfer
TracingAspect      -> observes execution of transfer
```

Quan hệ `TracingAspect extends BaseObservation` **không quyết định** Security sẽ bao ngoài hay nằm trong Trace. Khi cùng một join point có nhiều advice, precedence/order là hợp đồng riêng.

Trong mô hình quanh:

```text
Security(Trace(Target))
```

Security có thể từ chối trước khi Trace chạy. Còn:

```text
Trace(Security(Target))
```

Trace có thể quan sát cả lần bị từ chối. Hai cấu trúc có mục tiêu khác nhau, và kế thừa abstract tracing base **không thay đổi** mục tiêu ấy.

### 10.1. Before/after đảo chiều theo around nesting

Nếu A bao ngoài B:

```text
A.before
  B.before
    Target
  B.after
A.after
```

Muốn “A chạy trước B” phải làm rõ là **before** hay **after**. Đừng dùng sự tồn tại của `extends` như một phép topological sort cho toàn bộ advice.

### 10.2. Advice ở cha và con chồng điểm

Một concrete subclass có thể bổ sung **advice riêng**, bên cạnh advice được thừa kế theo công nghệ. Nếu cả hai chọn cùng join point, có thể xảy ra nhiều đoạn xử lý. Không suy rằng advice của subclass **override** advice trong base chỉ vì dùng pointcut giống nhau.

Muốn hành vi chắc chắn, test số lần advice/target được gọi và thứ tự, hoặc gộp bất biến trong một **template/hook có hợp đồng**.

## 11. Ví dụ Java 17 chạy được: abstract policy và hai concrete subclasses

Chương trình sau mô phỏng **tái sử dụng một khung interception qua kế thừa**:

- `AbstractTraceAspect` định nghĩa **template** cho before, return, throw và finally, đồng thời **bảo toàn đúng một lần gọi `proceed`**.
- Hai subclass `AllOperationsAspect` và `PriorityOperationsAspect` chuyên biệt hóa **điều kiện chọn** và **nhãn**.
- `ServicePort` là giao diện nghiệp vụ; `WorkService` là target thật.
- `Proxy` và chain chỉ chặn lời gọi đi **qua proxy**, không bổ sung một aspect language riêng hoặc bytecode weaving.
- Những lần gọi bắt đầu bằng `vip-` được cả hai aspects chọn, do đó **hai lớp observation chạy lồng nhau**, không phải “subclass ghi đè advice cha”.
- Khi target ném `IllegalArgumentException`, cả advice quan sát thích hợp đều truyền lại ngoại lệ gốc.

Đây là **mô hình áp dụng template-method reuse**, không tuyên bố một abstract Java class chính là abstract aspect của mọi ngôn ngữ AOP.

Tạo file `AspectInheritanceDemo.java`:

```java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;
import java.util.List;

public class AspectInheritanceDemo {
    interface ServicePort {
        String process(String name);
    }

    static final class WorkService implements ServicePort {
        @Override
        public String process(String name) {
            System.out.println("TARGET " + name);
            if ("bad".equals(name)) {
                throw new IllegalArgumentException("invalid");
            }
            return "done:" + name;
        }
    }

    @FunctionalInterface
    interface Proceeding {
        Object proceed() throws Throwable;
    }

    static abstract class AbstractTraceAspect {
        protected abstract boolean select(Method method, Object[] args);
        protected abstract String label();

        // Template is final: subclasses cannot silently omit proceed.
        public final Object around(
                Method method, Object[] args, Proceeding next)
                throws Throwable {
            if (!select(method, args)) {
                return next.proceed();
            }

            String operation = (String) args[0];
            System.out.println(label() + " before " + operation);
            try {
                Object result = next.proceed();
                System.out.println(label() + " return " + result);
                return result;
            } catch (Throwable error) {
                System.out.println(label() + " throw "
                        + error.getClass().getSimpleName());
                throw error;
            } finally {
                System.out.println(label() + " finally");
            }
        }
    }

    static final class AllOperationsAspect extends AbstractTraceAspect {
        @Override
        protected boolean select(Method method, Object[] args) {
            return method.getName().equals("process")
                    && method.getParameterCount() == 1;
        }

        @Override
        protected String label() {
            return "ALL";
        }
    }

    static final class PriorityOperationsAspect
            extends AbstractTraceAspect {
        @Override
        protected boolean select(Method method, Object[] args) {
            return method.getName().equals("process")
                    && args[0] instanceof String name
                    && name.startsWith("vip-");
        }

        @Override
        protected String label() {
            return "VIP";
        }
    }

    static Object callTarget(
            Method method, Object target, Object[] args)
            throws Throwable {
        try {
            return method.invoke(target, args);
        } catch (InvocationTargetException wrapped) {
            throw wrapped.getCause();
        }
    }

    static Object invokeAt(
            int position,
            List<AbstractTraceAspect> aspects,
            Method method,
            Object[] args,
            Object target) throws Throwable {
        if (position == aspects.size()) {
            return callTarget(method, target, args);
        }

        AbstractTraceAspect aspect = aspects.get(position);
        return aspect.around(method, args,
                () -> invokeAt(position + 1, aspects,
                        method, args, target));
    }

    static ServicePort wrap(ServicePort target,
                            List<AbstractTraceAspect> aspects) {
        return (ServicePort) Proxy.newProxyInstance(
                ServicePort.class.getClassLoader(),
                new Class<?>[] { ServicePort.class },
                (proxy, method, args) ->
                        invokeAt(0, aspects, method, args, target));
    }

    public static void main(String[] args) {
        ServicePort proxy = wrap(
                new WorkService(),
                List.of(new AllOperationsAspect(),
                        new PriorityOperationsAspect()));

        System.out.println("CALL " + proxy.process("ordinary"));
        System.out.println("CALL " + proxy.process("vip-1"));
        try {
            proxy.process("bad");
        } catch (IllegalArgumentException error) {
            System.out.println("CALLER " + error.getMessage());
        }
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac -encoding UTF-8 AspectInheritanceDemo.java
java AspectInheritanceDemo
```

**Stdout dự kiến chính xác:**

```text
ALL before ordinary
TARGET ordinary
ALL return done:ordinary
ALL finally
CALL done:ordinary
ALL before vip-1
VIP before vip-1
TARGET vip-1
VIP return done:vip-1
VIP finally
ALL return done:vip-1
ALL finally
CALL done:vip-1
ALL before bad
TARGET bad
ALL throw IllegalArgumentException
ALL finally
CALLER invalid
```

### 11.1. Vì sao `ordinary` chỉ chạy ALL?

`AllOperationsAspect.select` chọn mọi lời gọi `process` đúng dạng, còn `PriorityOperationsAspect.select` chỉ chọn tên bắt đầu `"vip-"`. Vì `ordinary` không phải `vip-`, VIP bỏ qua việc ghi log và gọi tiếp đúng một lần. Target chạy và trả `done:ordinary`; ALL ghi return rồi finally.

### 11.2. Vì sao `vip-1` có hai lớp observation?

Cả ALL và VIP đều chọn cùng join point. Chúng **không phải** quan hệ “ALL là instance cha của VIP”; chúng là **hai concrete interceptor instances** cùng kế thừa template `AbstractTraceAspect`.

Chuỗi đặt ALL ngoài VIP: `ALL(VIP(Target))`. Thứ tự vì vậy là ALL before, VIP before, target, VIP return/finally, ALL return/finally. Nếu đảo danh sách, thứ tự log khác nhưng hai chính sách vẫn có thể độc lập về code.

### 11.3. Vì sao ngoại lệ gốc được bảo toàn?

`WorkService.process("bad")` ném `IllegalArgumentException("invalid")`. Phần `callTarget` bóc `InvocationTargetException` của reflection, rồi `AbstractTraceAspect` ghi loại lỗi và **ném lại chính lỗi đó**. Vì VIP không chọn `bad`, chỉ ALL ghi lỗi, và caller bắt đúng `IllegalArgumentException`.

Trong ví dụ, `label()` và `System.out.println` không ném lỗi ở những đường đã xét. Với observer thực tế, lỗi từ formatter/exporter cần được xử lý riêng theo hợp đồng, không catch rộng quanh `next.proceed()` rồi bỏ luôn lỗi của nghiệp vụ.

### 11.4. Vì sao template `final` có ích?

`around` được đánh dấu `final`, nên hai subclass không thể âm thầm viết một bản điều khiển riêng làm mất `finally`, nuốt lỗi target hoặc gọi tiếp nhiều lần. Phần chúng thay đổi chỉ là **`select` và `label`**.

Đây là một **quy tắc thiết kế cho ví dụ Java**. Không suy từ nó rằng mọi ngôn ngữ AOP hỗ trợ `final advice` với cú pháp tương tự.

### 11.5. Giới hạn cần hiểu rõ

- Đây là Java thuần với **JDK dynamic proxy và chain tự viết**, không phải native aspect inheritance/weaving.
- JDK proxy chỉ áp trên lời gọi đi qua giao diện; gọi trực tiếp `new WorkService().process(...)` bypass toàn bộ logic.
- `select` của ALL đơn giản và không kiểm tra sâu kiểu tham số; với API nhiều overload cần đối chiếu đầy đủ signature/declaring type.
- Ví dụ không có field state mutable per-call; do đó tránh vấn đề ghi đè state khi proxy dùng đồng thời.
- Trong mô hình thực, có thể có nhiều loại advice, join point và instantiation policy khác mà ví dụ này không mô phỏng.
- `@Override` ở subclass override **Java helper hooks**, không override advice declaration của một AOP language.
- Nếu handler áp chung cho `Object` methods như `equals`/`hashCode`, cần hợp đồng riêng; demo chỉ gọi `process`.
- Nếu `select` hoặc `label` của subclass lỗi, target có thể không được gọi hoặc bị đổi kết quả; cần review contract.

## 12. So sánh inheritance, composition và delegation

Kế thừa hữu ích khi cần một contract **“là một phiên bản chuyên biệt của cùng hành vi chung”**. Composition phù hợp khi nhiều chính sách **khác bản chất** cần hoạt động cùng nhau.

| Cách tái sử dụng | Điểm mạnh | Cạm bẫy |
| --- | --- | --- |
| **Abstract aspect + concrete aspects** | Chia sẻ advice/hook, specialization pointcut | Phụ thuộc mạnh vào base và quy tắc inheritance của tool |
| **Named pointcut definitions** | Tái sử dụng tập join point | Không tự chia sẻ body advice hoặc lifecycle |
| **Helper service** | Dùng chung formatter/metric sink/validation logic | Vẫn phải quản lý lỗi và DI/ownership |
| **Composition of aspects** | Mối quan tâm độc lập, precedence minh bạch | Nhiều advice có thể chồng nhau |
| **Delegation to policy object** | Thay thuật toán qua interface, ít coupling với type hierarchy | Cần chọn và truyền đúng policy |
| **Interceptor/decorator chain** | Hành vi và thứ tự thấy rõ trong code/config | Phụ thuộc phạm vi interception (ví dụ proxy) |
| **Copy/paste nhiều aspects** | Ban đầu đơn giản | Dễ phân kỳ semantics khi sửa |
| **Structural introduction** | Bổ sung API/type khi được hỗ trợ | Có thể gây xung đột member, binary/API compatibility |

### 12.1. Khi nên ưu tiên abstract aspect

- Nhiều use cases chia sẻ **một khung advice với cùng luật return/throw/cleanup**.
- Khác biệt chính là **pointcut, nhãn hoặc phương thức hỗ trợ nhỏ**.
- Ngôn ngữ AOP và toolchain có **hợp đồng kế thừa rõ, được kiểm thử**.
- Bản base có thể ổn định lâu dài mà không buộc con cập nhật liên tục.
- Concrete aspects có thể được kiểm thử riêng và không tự tạo chồng pointcut nguy hiểm.

### 12.2. Khi nên ưu tiên composition

- Một aspect cần audit, một aspect cần retry, một aspect cần transaction, khác nhau về semantics.
- Hai chính sách phải bật/tắt và phiên bản hóa độc lập.
- Cần làm rõ precedence hơn là quan hệ type.
- Cần hỗ trợ công nghệ AOP không có native abstract aspect inheritance.
- Có nhiều biến thể tổ hợp; một cây subclass sẽ phát triển thành vô số lớp.
- Một phần logic nên có thể dùng trong nghiệp vụ không có AOP, qua interface/helper.

Kế thừa không phải mục tiêu; **bảo toàn hợp đồng và giảm trùng lặp có ý nghĩa** mới là mục tiêu.

## 13. Thiết kế abstract pointcut tốt

Một abstract pointcut nên có tên phản ánh **hợp đồng ngữ nghĩa**, ví dụ `businessOperations()` thay vì `anyMethod()`.

### 13.1. Định nghĩa tập chọn và tập loại trừ

Nếu base có advice ghi telemetry, nên xác định:

- Những execution/call join points nào được phép chọn?
- Code của logger/exporter có bị pointcut chọn ngược làm advice tái nhập không?
- Có chọn getter/setter vô hại hoặc hot path không?
- Có chọn overload/implementation mới không?
- Có cần thêm điều kiện type/annotation/argument binding không?
- Có đang chọn constructor, field access, internal call mà công nghệ không hỗ trợ không?

Một concrete aspect định nghĩa `selected(): execution(* *(..))` theo wildcard quá rộng có thể vô tình áp advice lên cả logger, tăng overhead hoặc stack overflow vì recursive tracing.

### 13.2. Sử dụng điều kiện phủ định có chủ đích

Một số pointcut languages cho phép `&&`, `||`, `!` hoặc named pointcuts. Có thể mô tả ý tưởng:

```text
selectedBusinessOperations()
  AND NOT insideTelemetryInfrastructure()
```

Đây là **giả mã**, không phải Java chuẩn. Đừng dùng bộ lọc phủ định mơ hồ dựa vào tên lớp tình cờ; cần test khi package refactor hoặc thêm lớp mới.

### 13.3. Kiểm tra điểm giao nhau giữa các concrete subclasses

Nếu một base có ba concrete subclasses, kiểm thử cả các **giao nhau của pointcut sets**:

```text
ObservedByOrder ∩ ObservedByInvoice
ObservedByOrder ∩ ObservedByGeneral
ObservedByInvoice ∩ ObservedByGeneral
```

Một điểm nằm trong hai tập có thể nhận advice hai lần từ hai concrete aspects theo mô hình công cụ. Nếu điều đó có chủ đích, cần tài liệu về thứ tự và dữ liệu. Nếu không, thu hẹp pointcuts hoặc chuyển thành một aspect với policy rõ.

## 14. Thư viện aspect dùng chung và module hóa

Một nhóm có thể phát hành **abstract aspect base** như thư viện, còn ứng dụng cung cấp concrete specializations. Điều này tạo khả năng tái sử dụng giữa nhiều module, nhưng thêm trách nhiệm về **phiên bản hóa**:

- Nếu base thêm một abstract pointcut mới, các concrete aspects cũ có thể trở nên không hợp lệ khi biên dịch lại.
- Nếu base đổi visibility/signature của hook, subclass cũ có thể không còn override hợp lệ.
- Nếu base đổi advice type từ before sang around, semantics return/exception/timing có thể thay đổi.
- Nếu base đổi phạm vi pointcut từ hẹp sang rộng, những điểm mới có thể bị instrument ngoài ý định.
- Nếu base đổi state từ local sang field singleton, concurrency/retention có thể xuất hiện.
- Nếu base đưa một declaration mới cùng tên member ở subclass, có thể xuất hiện conflict.
- Nếu artifact chỉ chứa base hoặc chỉ chứa concrete declaration thiếu dependency, weaving có thể thất bại hoặc advice không được áp.

Cần **compatibility matrix** giữa base version, concrete specializations và AOP compiler/weaver version; không xem “cùng major Java version” là đủ.

### 14.1. JPMS và class loader

Khi base aspect/concrete aspect/target nằm ở module hoặc class loader khác nhau, phải đánh giá ranh giới truy cập, exports/opens, reflection và khả năng weaving ở môi trường thật.

Một class có tên giống nhau trong hai loaders không tự là cùng runtime type. Một concrete aspect được biên dịch với một bản interface nhưng target runtime dùng bản khác có thể gặp `ClassCastException`, `NoSuchMethodError` hoặc lỗi liên kết tùy tình huống.

### 14.2. Không biến base thành kho giữ request

Một base aspect chia sẻ field mutable để giữ `lastArgs`, `currentUser`, `target` hoặc payload lớn có thể vô tình giữ object sau invocation. Nếu concrete aspects dùng các instance sống dài, vấn đề tồn tại ở **mọi subclass**.

Thiết kế tốt đặt dữ liệu theo invocation trong local variables, chỉ giữ aggregate state ở mức instance khi thật sự cần và có thread safety.

## 15. Xung đột override, visibility và pointcut contract

Một lớp con chỉ thật sự override một Java method nếu signature và luật Java phù hợp. Tương tự, một concrete aspect chỉ thật sự đáp ứng abstract pointcut nếu **tên, tham số/binding, modifier và loại declaration** đúng luật của ngôn ngữ AOP đó.

Sai lầm thường gặp:

- Con khai báo `selected(String)` khi cha đòi `selected()`: đây có thể là declaration khác, không đáp ứng hook.
- Con làm hẹp visibility của hook mà contract yêu cầu `protected` hoặc `public`.
- Một helper method `static` được tưởng là override instance method.
- Dùng return type không tương thích ở overridden helper method.
- Thay tên tham số/kiểu binding không khớp pointcut thực tế.
- Mong một advice do con khai báo “thay thế” inherited advice mà không kiểm tra semantics.
- Trộn member introduction vào cùng target làm collision.
- Tưởng `private` field của base tự có thể bị con truy cập trực tiếp.

**Mẹo thiết kế:** đặt `@Override` trên Java helper hooks nơi ngôn ngữ hỗ trợ và dùng compile-time validation cho abstract pointcut contracts. Đối với pointcut/advice language, dùng cú pháp của công cụ và test đúng artifact.

## 16. Kế thừa không tự giải quyết lỗi luồng điều khiển

Một around advice ở base có thể gọi `proceed`; các concrete aspects có thể kế thừa bản đó. Điều không nên làm là nghĩ chỉ cần “base chạy trước con” để bảo đảm an toàn.

### 16.1. Short-circuit

Nếu một aspect bên ngoài không gọi `proceed` mà trả cache hit, phần advice ở các aspect bên trong có thể không chạy. Kế thừa từ cùng base không ngăn điều đó.

Nếu bắt buộc có authorization trước mọi truy cập, cần đặt chính sách ở **ranh giới đáng tin**; không dựa vào việc các aspect cùng kế thừa `BasePolicy`.

### 16.2. Retry và số lần chạy

Nếu một around advice của subclass retry bằng cách gọi `proceed` nhiều lần, target có thể chạy nhiều lần. Một base trace dùng `before`/after có thể đếm **attempt** hoặc **logical request** tùy thứ tự nesting. Kế thừa không tự chuẩn hóa đơn vị đo.

### 16.3. Lỗi observer so với lỗi target

Nếu base phục vụ observer tùy chọn, nó nên cô lập **lỗi do chính observer** theo hợp đồng; không nuốt các ngoại lệ gốc từ target. Nếu concrete subclass thay formatter và formatter throw, base phải quyết định có chặn invocation không.

Nếu base phục vụ policy bắt buộc như authorization, fail-open mặc định sẽ nguy hiểm. Vì vậy một base “universal around” cho cả telemetry và guard là trừu tượng quá rộng.

## 17. Ma trận kiểm thử kế thừa aspect

| Kịch bản | Cần chứng minh |
| --- | --- |
| Một concrete subclass định nghĩa pointcut hợp lệ | Advice kế thừa chạy tại các join point mong đợi |
| Join point ngoài pointcut subclass | Không chạy inherited advice của subclass đó |
| Abstract aspect chưa được cụ thể hóa | Không được áp dụng như concrete policy độc lập sai ý định |
| Hai subclasses có pointcuts tách biệt | Không có sự kiện thừa hoặc trùng |
| Hai subclasses có pointcuts giao nhau | Số advice/instance và order rõ |
| Concrete subclass thiếu abstract pointcut | Build phát hiện contract chưa được đáp ứng |
| Helper hook override hợp lệ | Gọi đúng implementation của con |
| Hook signature/visibility sai | Compile/build phát hiện thay vì âm thầm tạo hàm khác |
| Target return bình thường | Advice giữ đúng result |
| Target throw | Advice giữ nguyên exception/cause theo hợp đồng |
| Observer helper throw | Chính sách xử lý lỗi riêng, không nuốt target |
| Pointcut chọn overload khác | Không match ngoài ý định |
| Recursive/self-invocation | Không tạo advice loop/bypass trái thiết kế |
| Aspect state dùng đa luồng | Không lẫn dữ liệu invocation |
| Per-target/per-flow instantiation nếu hỗ trợ | Số instance và scope được xác minh |
| Precedence với aspect khác | Before/after/around order đúng |
| Proxy target gốc được gọi trực tiếp | Phát hiện đường bypass |
| Module/class loader khác | Access/linking theo hợp đồng |
| Build woven và deployment artifact | Chính artifact cuối có advice cần thiết |
| Thư viện base nâng phiên bản | Concrete specializations còn tương thích |
| Thêm một concrete aspect mới | Không làm thay semantics các subclass cũ |

### 17.1. Property tests hữu ích

Với aspect thuần quan sát, những bất biến nên kiểm tra:

- Mỗi invocation target chạy **đúng số lần** mà hợp đồng định nghĩa.
- Return/exception của target không bị thay chỉ vì logging.
- Các join point không chọn **không** sinh log.
- Không có context/ThreadLocal/registration bị giữ sau return/throw.
- Khi hai concrete aspects cùng áp, mỗi aspect được ghi theo ý định và thứ tự đã công bố.
- Dữ liệu người dùng không bị giữ trong singleton base.

### 17.2. Không chỉ test output của phần con

Một concrete aspect có thể “hoạt động” trong unit test nhưng inherited advice không thực sự được woven trong ứng dụng do build/runtime nạp lớp khác. Phải kiểm tra **độ phủ của weaver và artifact triển khai**, không chỉ đối tượng Java được khởi tạo trong unit test.

## 18. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Coi mọi AOP có aspect inheritance | API/cú pháp không tồn tại | Xác minh capability của công nghệ |
| Coi abstract aspect là một concrete singleton tự chạy | Advice chạy thừa hoặc dự đoán sai instance | Hiểu instantiation policy thực tế |
| Nhầm abstract pointcut với abstract Java method | Contract binding không hợp lệ | Áp đúng cú pháp/ngữ nghĩa AOP |
| Nghĩ con override advice bằng cách khai báo advice mới | Advice chồng nhau và số lượt chạy sai | Dùng hook được hỗ trợ, test precedence |
| Dùng `extends` để giải quyết order của nhiều aspects | Bảo mật/timing/audit sai | Quy định precedence riêng |
| Base chọn mọi phương thức rồi con không lọc | Đệ quy và overhead lớn | Abstract pointcut hẹp, test phạm vi |
| Kế thừa field `currentRequest` trong shared aspect | Race và giữ request lâu | Local/context scope phù hợp |
| Static counter được coi là per-subclass | Dữ liệu bị dùng chung ngoài ý muốn | Instance state rõ hoặc key riêng |
| Đổi signature hook không kiểm tra con | Compile/build break | Semantic versioning, contract tests |
| Để nhiều concrete subclasses chọn cùng effect | Logging/audit trùng | Kiểm tra pointcut intersections |
| Coi kế thừa abstract base là mixin vào target | Caller không có API mới | Tách structural introduction khỏi inheritance |
| Dùng proxy rồi nghĩ target đã được weave | Lời gọi trực tiếp bypass | Kiểm tra đúng đối tượng và artifact |
| Chia sẻ một base giữa guard và observer | Chính sách lỗi xung đột | Tách mối quan tâm theo bất biến |
| Không test phần throw/cleanup | Rò scope hoặc che lỗi gốc | Test return, throw, timeout/cancel khi phù hợp |
| Không tính version của AOP compiler | Nguồn chạy khác nhau giữa môi trường | Chốt toolchain và test end-to-end |

## 19. Bài tập vận dụng có đáp án

### Bài 1 — Abstract pointcut để làm gì?

Bạn có năm concrete tracing aspects có cùng logic ghi trước/sau nhưng chọn năm nhóm method execution khác nhau. Nên lặp lại advice ở cả năm?

**Đáp án:** Nếu ngôn ngữ cho phép, có thể đặt **advice chung** trong abstract aspect và để mỗi concrete aspect cung cấp abstract pointcut tương ứng. Nếu công nghệ không hỗ trợ, tái sử dụng helper/interceptor qua composition hoặc delegation.

### Bài 2 — Abstract aspect có tự áp toàn ứng dụng?

Một abstract base chỉ khai báo `selected()` chưa định nghĩa. Có nên coi nó là một aspect độc lập chạy advice với mọi điểm?

**Đáp án:** Không. Đó là một hợp đồng còn thiếu concrete specialization. Cách instantiation tùy công cụ nhưng không nên giả định runtime tạo một concrete instance từ abstract definition.

### Bài 3 — Hai con chọn cùng method

Hai concrete aspects cùng kế thừa `BaseObservation` và cả hai chọn `OrderService.place(..)`. Advice sẽ chỉ chạy một lần vì chung base?

**Đáp án:** Không thể kết luận vậy. Có thể có hai concrete aspects cùng áp lên join point. Cần kiểm tra số instance, số advice và precedence; nếu trùng không có chủ đích, sửa pointcut hoặc hợp nhất chính sách.

### Bài 4 — Advice override

Một con định nghĩa `before()` mới trong khai báo aspect để “đè” `before()` của cha. Có phải Java overriding không?

**Đáp án:** Không. Advice declarations có cú pháp/ngữ nghĩa riêng, không phải Java method cùng tên được override bằng `@Override`. Muốn một điểm thay đổi, dùng abstract pointcut hoặc method hook/strategy được ngôn ngữ cho phép.

### Bài 5 — Shared field

Base aspect có `String currentUser`; hai concrete aspects dùng cùng logic trong các thread. Có an toàn cho dữ liệu theo từng lời gọi không?

**Đáp án:** Không mặc định. Field thuộc aspect instances với lifetime cụ thể, không phải per-invocation. Có thể race/retention, đặc biệt với shared instances; dùng context ngắn hạn hoặc biến local.

### Bài 6 — Sự khác nhau với precedence

`TraceAspect extends AbstractTrace`, còn `AuthAspect` là aspect riêng. Kế thừa có bảo đảm Trace chạy sau Auth?

**Đáp án:** Không. Order giữa Trace và Auth là vấn đề **precedence/chain nesting** riêng, phải được cấu hình và kiểm thử.

### Bài 7 — Pointcut quá rộng

Con định nghĩa `selected()` để chọn cả logger được advice gọi. Nguy cơ gì?

**Đáp án:** Advice có thể tự kích hoạt lại qua logger, tạo recursion, log storm hoặc quá tải. Thu hẹp join point và loại phần hạ tầng quan sát một cách có chủ đích.

### Bài 8 — Java 17 demo

Vì sao `vip-1` in hai cặp before/return/finally, còn `ordinary` chỉ in một?

**Đáp án:** Cả `AllOperationsAspect` và `PriorityOperationsAspect` chọn `vip-1`, nhưng chỉ ALL chọn `ordinary`. Hai concrete objects chia sẻ template qua kế thừa chứ không “override advice”.

### Bài 9 — Proxy bypass

Khi gọi trực tiếp `new WorkService().process("vip-1")` thay vì qua proxy trong demo, có được hai lớp logging không?

**Đáp án:** Không. Trong demo, chain nằm trong JDK proxy. Target gốc không được weave; caller đi ngoài proxy không kích hoạt logic interceptor.

### Bài 10 — Abstract hook được sửa ở base

Phiên bản mới của base thêm một abstract method/hook bắt buộc. Điều gì cần làm với các concrete aspects cũ?

**Đáp án:** Kiểm tra compatibility và bổ sung implementation theo contract. Đây có thể là thay đổi làm hỏng source/binary compatibility và cần kiểm thử build/weaving ở tất cả module sử dụng.

### Bài 11 — Khi nào bỏ inheritance?

Một abstract aspect chứa nhiều nhánh cấu hình `isAudit`, `isSecurity`, `isCache` và các subclasses liên tục phải override cleanup lẫn retry semantics. Nên tiếp tục thêm hooks?

**Đáp án:** Nên xem lại trừu tượng. Các chính sách có bất biến/lifecycle khác nhau nên tách thành các aspects độc lập và phối hợp qua precedence/coordinator hoặc dùng composition, thay vì cố giữ một base quá rộng.

## 20. Ghi nhớ

- **Kế thừa aspect chỉ áp dụng khi mô hình ngôn ngữ/công cụ hỗ trợ.** Không mặc định mọi AOP có `abstract aspect`, `extends` hay inherited advice.
- **Abstract aspect** giúp chia sẻ logic; **concrete aspect** cung cấp pointcut/hook cụ thể theo contract.
- **Abstract pointcut là hợp đồng lựa chọn join point**, không phải một Java abstract method thông thường.
- **Advice inheritance không có nghĩa Java method overriding**; lớp con có advice mới có thể làm phát sinh thêm hành vi, cần test.
- **Kế thừa không quyết định precedence**, không tự tạo per-request instance và không thay thế pointcut coverage.
- Giữ phần bất biến về **return/throw/cleanup** ở base; để subclasses chuyên biệt hóa những gì thực sự cần thay đổi.
- State mutable của base vẫn chịu **lifetime và concurrency** của concrete instance; không lưu request trong shared field.
- Khi việc tái sử dụng không phù hợp type hierarchy, dùng **composition, delegation, helper service hoặc reusable interceptor chain**.
- Kiểm thử trên **công cụ và artifact thực**, gồm pointcuts chồng nhau, ngoại lệ, instance scope, module access, proxy bypass và nâng phiên bản thư viện.
