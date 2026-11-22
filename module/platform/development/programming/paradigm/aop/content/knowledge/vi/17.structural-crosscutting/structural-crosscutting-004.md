# Giới hạn truy cập và xung đột tên khi bổ sung thành phần trong Aspect/AOP

Trong lập trình hướng khía cạnh (**Aspect-Oriented Programming — AOP**), một số cơ chế ngoài advice trước/sau/quanh còn hỗ trợ **thay đổi cấu trúc kiểu** (*structural crosscutting*): bổ sung phương thức, trường dữ liệu, constructor, giao diện triển khai hoặc quan hệ kế thừa cho những lớp đã tồn tại. Trong các mô hình như AspectJ, khả năng này thường được mô tả bằng **inter-type declarations (ITD)** hoặc *introductions*. Một hướng khác là **mixin qua adapter/proxy**, chỉ đưa thêm khả năng khi đi qua đối tượng thích nghi, không nhất thiết sửa cấu trúc lớp đích.

Khả năng “bổ sung thành phần” rất mạnh, nhưng có những câu hỏi quan trọng:

1. Thành phần mới có **quyền truy cập** tới dữ liệu `private`, `protected`, package-private và public của lớp đích hay không?
2. Nếu lớp đã có phương thức/trường **cùng tên** hoặc nhiều aspect cùng bổ sung một thành phần, ai sở hữu tên đó?
3. Thêm một interface có method trùng chữ ký hoặc nhiều `default` methods thì compiler/weaver giải quyết thế nào?
4. Nếu class dùng generics, overload, inheritance, static members hoặc final modifiers, có lỗi **signature clash**, erasure hay thay nghĩa dispatch không?
5. Nếu lớp ở một module/package/class loader khác, cơ chế AOP có thật sự được phép **weave hoặc tiếp cận** thành phần cần dùng không?
6. Nếu không thể bổ sung an toàn, nên đổi tên, dùng interface hợp đồng, adapter, composition hay bỏ việc can thiệp cấu trúc?

**Nguyên tắc cốt lõi:** AOP không tự cấp “quyền truy cập mọi thứ” và cũng không bảo đảm hai khai báo trùng nhau được kết hợp theo thứ tự ưu tiên một cách an toàn. **Luật của Java, của bytecode, của ngôn ngữ AOP và của cơ chế weaver/proxy phải được xem riêng.**

Bài này nói về **Aspect/AOP nói chung, từ cơ bản tới nâng cao**, không gắn với một framework ứng dụng cụ thể. Những đoạn có cú pháp AspectJ được đánh dấu là **minh họa cho ngôn ngữ hỗ trợ ITD**, không phải cú pháp Java thông thường. Chương trình Java 17 chạy được ở phần thực hành minh họa **interface mixin qua proxy và xung đột phương thức**, đồng thời nêu rõ những điều mà proxy *không* thực hiện được.

## 1. Mục tiêu học tập

Sau bài, bạn có thể:

- Phân biệt thay đổi cấu trúc lớp bằng **inter-type declaration** với **advice** và với mixin qua **adapter/proxy**.
- Hiểu các mức visibility của Java: `public`, `protected`, **package-private**, `private`; tránh diễn giải quyền của ITD theo trực giác đơn giản.
- Nhận diện xung đột **cùng tên, cùng chữ ký, cùng field, overload, inheritance, default interface methods và generic erasure**.
- Nêu được vì sao **field hiding** không giống method overriding, và vì sao một member mới không tự thay thế member cũ.
- Kiểm tra `final`, `static`, bridge methods, constructor và những ràng buộc từ class/interface contract.
- Hiểu giới hạn của **JPMS module**, **reflection**, **class-loader identity**, phạm vi weaving và chế độ proxy.
- Thiết kế bổ sung thành phần có **tên ổn định, ownership rõ ràng và khả năng tương thích** với phiên bản thư viện thay đổi.
- Chạy ví dụ Java 17 có `default` method conflict, interface adapter qua JDK proxy và hai giao diện trùng chữ ký.
- Lập ma trận test để phát hiện xung đột tại **compile time, weaving time, class loading time và runtime**.

## 2. Nhắc lại: thay đổi hành vi khác thay đổi cấu trúc

Trong AOP, hai nhóm chức năng dễ bị trộn lẫn:

| Nhóm | Tác động điển hình | Ví dụ |
| --- | --- | --- |
| **Behavioral crosscutting** | Chọn join point rồi chạy advice | Trước khi gọi `pay()` thì kiểm tra quyền |
| **Structural crosscutting** | Bổ sung thành viên hoặc quan hệ kiểu nếu ngôn ngữ/công cụ hỗ trợ | Thêm `traceId()` cho `Order` |
| **Adapter/mixin proxy** | Đối tượng bọc biểu lộ thêm một interface hoặc hành vi | Proxy vừa là `OrderView` vừa là `Auditable` |
| **Composition thông thường** | Một object dùng object khác qua field/interface | `OrderAuditAdapter` chứa `Order` |
| **Inheritance thông thường** | Thay đổi hoặc mở rộng lớp con theo Java | `AuditedOrder extends Order` nếu được phép |

**Advice** không đồng nghĩa class thực sự có thêm method. Một around advice có thể thay hành vi khi gọi `save()`, nhưng không khiến compiler Java cho phép gọi `order.traceId()` nếu type của `order` không khai báo phương thức đó và chưa có cơ chế introduction hợp lệ.

**Proxy adapter** khác ITD thật: đối tượng proxy có thể triển khai interface mới, nhưng **target gốc** không vì thế được bổ sung field/method vào class file. Nếu một người giữ tham chiếu gốc, họ vẫn thấy API cũ. Nếu weaver sửa cấu trúc kiểu theo hợp đồng của ngôn ngữ AOP, API của artifact được weave có thể khác API trước weaving.

### 2.1. Ba cấp tác động cần kiểm chứng

- **Source-level visibility:** compiler đang biên dịch trên những khai báo nào, classpath/modulepath nào?
- **Bytecode/runtime structure:** class file nạp thực tế có field/method/interface mới không?
- **Call-site behavior:** caller có gọi qua proxy, adapter hay woven class mà mong đợi không?

Một chương trình thành công khi dùng IDE plugin đặc biệt không bảo đảm chương trình **biên dịch bằng javac đơn thuần**, hay bản triển khai cuối cùng đã chứa những introduction.

## 3. Inter-type declarations và mixin thực chất làm gì?

Một ngôn ngữ AOP hỗ trợ ITD có thể cho phép khai báo bên ngoài class đích rằng class ấy có thêm thành viên hoặc quan hệ kiểu. Mô hình ý tưởng:

```text
Original class:
  Order { id(), total() }

Structural aspect / introduction:
  Order implements Auditable
  Order.auditTag()

Woven result (conceptually):
  Order { id(), total(), auditTag() }
  Order is assignable to Auditable
```

Đây là sơ đồ khái niệm. Cách tạo bytecode, quyền truy cập, tên bridge/synthetic method và thời điểm weave phụ thuộc công cụ.

Nếu thay bằng một proxy:

```text
Order target { id(), total() }
       |
       v
Adapter/Proxy implements OrderView, Auditable
       |
       +--> calls target.id(), target.total()
       +--> implements auditTag() itself
```

Target `Order` không nhất thiết implements `Auditable`. **Chỉ proxy** có thể mang interface mới; `order instanceof Auditable` vẫn có thể false trong khi `proxy instanceof Auditable` là true.

### 3.1. Không phải mọi bộ AOP cho phép structural introduction

Một số công cụ chỉ hỗ trợ **method execution interception** hoặc một tập join point giới hạn; không thể thêm field, constructor hay sửa class hierarchy. Có công cụ cho phép **declare parents**, có công cụ chỉ cho phép **thêm interface qua proxy**, và cũng có công cụ không hỗ trợ gì ngoài advice.

Trước khi thiết kế, phải tra cứu khả năng thực tế: **ngôn ngữ AOP**, thời điểm weaving, loại class đích, bytecode format, phiên bản JDK, giới hạn loader/module và những thành phần được weave.

## 4. Giới hạn truy cập trong Java

Bốn mức kiểm soát truy cập cho members thường gặp:

| Modifier | Cùng class khai báo | Cùng package | Lớp con khác package | Code khác package không kế thừa |
| --- | --- | --- | --- | --- |
| `public` | Có | Có | Có | Có, nếu class/package/module cũng cho truy cập |
| `protected` | Có | Có | Có theo các quy tắc subclass và qualifier của Java | Không |
| Không ghi modifier (**package-private**) | Có | Có theo runtime/compiler package phù hợp | Không chỉ vì là subclass khác package | Không |
| `private` | Có trong phạm vi quyền private/nestmate theo Java | Không chỉ vì cùng package | Không chỉ vì kế thừa | Không |

Đây là **tóm lược**: member public trong một class không thể truy cập từ chỗ mà **class khai báo không accessible**, và module mạnh có thể giới hạn việc liên kết class/package qua biên module. Với `protected` ở khác package, Java còn quy định **kiểu của expression dùng làm receiver** đối với instance members; không thể tóm thành “subclass ở đâu cũng gọi trên mọi instance”.

### 4.1. `private` không biến thành public vì có aspect

Nếu một lớp có:

```java
public class Account {
    private long balance;
    public long balance() { return balance; }
}
```

Một phần code ngoài lớp **không tự được phép** đọc `balance` chỉ vì nó nằm trong một aspect. Một ngôn ngữ AOP có **cơ chế được cấp quyền đặc biệt**, hoặc weaver có thể chèn những phương thức truy cập, có thể cung cấp khả năng riêng — nhưng đó là **hợp đồng mở rộng của ngôn ngữ/công cụ**, không phải luật của Java thông thường.

Ở mức thiết kế, ưu tiên **public hoặc package-facing API ổn định** phù hợp quyền hạn. Không đưa ITD vào chỉ để phá encapsulation của một lớp không sở hữu, nhất là khi chứa thông tin nhạy cảm.

### 4.2. `protected` có quy tắc receiver

Giả sử subclass ở package khác thừa hưởng method protected. Quyền truy cập có thể hợp lệ với `this` hoặc một receiver có kiểu subclass phù hợp, nhưng không mặc định hợp lệ với một biểu thức có kiểu base tùy ý. Code aspect/ITD có thể được biên dịch trong ngữ cảnh khác ngữ cảnh của subclass, nên không được suy quá mức từ tên modifier.

### 4.3. Package-private phụ thuộc ranh giới package/module và loader

Hai lớp có tên package chữ giống nhau không chắc có quyền package-private với nhau trong runtime nếu được nạp dưới **những class loader khác nhau**. Trên JVM, runtime package identity liên quan tới **tên package và defining class loader**, còn JPMS bổ sung những quy tắc về named modules và đóng gói.

Vì vậy một introduction/proxy vào lớp ở loader khác có thể thất bại do **inaccessible type**, kiểm tra liên kết hoặc quy tắc module, dù người viết thấy package name giống nhau.

### 4.4. Visibility của thành phần *được bổ sung*

Một ITD tạo method `public` có ý nghĩa API công khai của artifact đã weave, còn method `private`/package-private có phạm vi sử dụng hẹp theo semantics công cụ. Không mặc định một member private được “thêm vào target” sẽ dùng đúng những luật lexical của mã khai báo trực tiếp trong target; các compiler AOP có thể áp những quy tắc riêng về **ai sở hữu, ai thấy và body được biên dịch trong ngữ cảnh nào**.

## 5. `public` của interface là một hợp đồng không thể hạ cấp

Method abstract của interface trong Java thường là **public**. Nếu lớp hoặc ITD được dùng để đáp ứng interface:

```java
interface Identifiable {
    String id();
}
```

thì implementation tương ứng phải accessible công khai theo hợp đồng interface. Không thể triển khai bằng `private String id()` hay package-private method rồi kỳ vọng compiler coi đó là một implementation hợp lệ.

Một lỗi hay gặp là code của class đã có `String id()` package-private, sau đó aspect “giới thiệu” `implements Identifiable`. Có một method **trùng tên và tham số** nhưng thiếu visibility không làm interface tự được thực hiện hợp lệ. Phải có một implementation đúng signature/access, theo khả năng mà công nghệ cho phép.

## 6. Xung đột tên: phân loại chính xác

Tên giống nhau chưa đủ kết luận lỗi. Cần xem:

1. Thành phần là **field, method, constructor, nested type hay interface**?
2. Cùng tên trong **cùng lớp** hay được thừa hưởng từ superclass/interface?
3. Với method: cùng **parameter types** sau erasure không, return types có tương thích không?
4. Thành phần **instance** hay **static**?
5. Accessibility và override/hide có hợp lệ không?
6. Member đã có trong class gốc hay do **nhiều aspect khác nhau** giới thiệu?
7. Việc biên dịch/weaving có tạo **synthetic hoặc bridge methods** không?
8. Có nhiều **default methods** với cùng chữ ký không?
9. Có artifact/thư viện phiên bản mới thêm member trùng với introduction cũ không?

| Tình huống | Rủi ro | Hướng xử lý |
| --- | --- | --- |
| Hai ITD cùng bổ sung `auditTag()` vào một target | Tranh chấp cùng signature | Chọn một owner, đổi API, bỏ một introduction |
| Class gốc đã có `auditTag()` | Thay đổi/đè/hide không như dự kiến hoặc bị từ chối | Tôn trọng thành phần gốc và kiểm tra luật precedence/collision |
| ITD thêm `id(String)`, lớp có `id()` | Có thể chỉ là overload hợp lệ | Đánh giá ambiguity và binary compatibility |
| Hai method khác generic type argument nhưng cùng erasure | Name clash | Đổi tên/thiết kế type-safe API khác |
| Two interfaces có `default label()` | Không có default duy nhất | Class phải resolve rõ theo luật Java |
| Field cùng tên ở lớp cha/con | Field hiding, không dynamic dispatch | Dùng accessor có hợp đồng thay vì dựa field name |
| Một interface cần method public, class chỉ có method package-private | Không đáp ứng contract | Bổ sung public implementation hợp lệ |
| Static và instance method cùng signature | Không thể xem static hiding như instance overriding | Đổi thiết kế/tên |
| `final` method bị cố override | Không hợp lệ | Chuyển sang composition hoặc API khác |
| Proxy thêm interface duplicate signature | Handler có thể không phân biệt view bằng Method | Thiết lập một behavior thống nhất |

**Cấu hình thứ tự aspect không phải cách “giải quyết” mọi trùng member.** Thứ tự advice/precedence về hành vi **khác** quy tắc xung đột declarations ở type system.

## 7. Method signature, overload và xung đột do erasure

Trong Java, hai method có thể overload hợp lệ khi **danh sách kiểu tham số** khác nhau. Nhưng chỉ khác **return type** thì không tạo overload hợp lệ:

```java
// CỐ Ý KHÔNG BIÊN DỊCH: không được overload chỉ theo return type.
int size() { return 1; }
String size() { return "one"; }
```

Đây là hai phương thức giả định đặt trong cùng lớp. Một ITD thêm method cùng tên/tham số nhưng return type khác vào class đã có member cũng có thể không hợp lệ hoặc tạo collision theo quy tắc công cụ; không được mặc định “compiler chọn theo ngữ cảnh trả về”.

### 7.1. Generic erasure gây name clash

Đoạn dưới đây **cố ý không biên dịch**:

```java
import java.util.List;

class ErasureClash {
    void inspect(List<String> values) {}
    void inspect(List<Integer> values) {}
}
```

Sau *type erasure*, cả hai có parameter type `List`, nên không thể tạo hai overload chỉ dựa vào type argument `String` và `Integer`. Nếu một aspect thêm method `inspect(List<Integer>)` vào một class đã có `inspect(List<String>)`, cần tính cả **erasure và các phương thức bridge/synthetic có thể được sinh**, không chỉ nhìn source generic signature.

### 7.2. Covariant return và override

Một override có thể thu hẹp **reference return type** theo luật covariant return:

```java
class Base {
    Number value() { return 1; }
}
class Child extends Base {
    @Override Integer value() { return 2; }
}
```

Đây là snippet Java minh họa. Không được thay đổi return type tùy ý: ví dụ `String` không phải subtype của `Number`. Khi compiler tạo **bridge method**, bytecode có thể có member bổ sung để giữ compatibility. Một weaver/ITD phải xử lý xung đột ở cấp bytecode và type system, không chỉ ở hình thức chữ ký nguồn.

### 7.3. Varargs và arrays

Trong Java, `String...` là cú pháp khai báo tham số varargs dựa trên `String[]`. Nếu method đã có `log(String[])`, không thể giới thiệu một method `log(String...)` vào cùng class rồi coi đó là một overload khác. Nhiều biểu diễn nhìn khác nhau ở source vẫn có **cùng descriptor**.

## 8. Field hiding không phải method overriding

Field resolution trong Java khác virtual method dispatch. Ví dụ:

```java
class Parent {
    public String label = "parent";
    public String label() { return "parent-method"; }
}
class Child extends Parent {
    public String label = "child";
    @Override public String label() { return "child-method"; }
}
```

Đây là snippet minh họa. Nếu `Parent p = new Child()`, biểu thức `p.label` tham chiếu field của `Parent` theo **kiểu compile-time của expression**, còn `p.label()` gọi method override của `Child` bằng dispatch động.

Do đó, khi ITD thêm **field cùng tên với field được thừa hưởng**, không nên coi nó như “override state”. Nó có thể **hide** một field và tạo hai vùng dữ liệu khác nhau trên một object. Điều này dễ làm advice đọc một giá trị trong khi code nghiệp vụ đọc giá trị khác.

### 8.1. Tên field và method có thể trùng

Java cho phép field và method có cùng tên trong một class ở những dạng hợp lệ, vì ngữ cảnh cú pháp truy cập khác nhau (`obj.value` và `obj.value()`). Nhưng điều đó **không có nghĩa thiết kế API dễ hiểu**; một ITD thêm method trùng tên field có thể làm người đọc khó xác định mục đích.

Tên bổ sung nên mô tả **hợp đồng** và tránh những thành phần có sẵn, không tận dụng mọi khe hở pháp lý của cú pháp.

### 8.2. Static hiding và giới hạn của `final`

Một static method không được override theo nghĩa dispatch động của instance method; nó có cơ chế **hiding** riêng. Một method `final` không được override trong Java thông thường. Một class `final` không được subclass, dù một adapter hoặc proxy giao diện có thể được xây bên cạnh nó.

Với ITD/weaving, khả năng thay đổi cấu trúc hoặc thêm method mới cho class final **phụ thuộc công cụ**; không từ đó suy ra được phép override method final hoặc vi phạm ràng buộc bytecode. Khi gặp final/binary library, luôn xác minh khả năng hỗ trợ thay vì phỏng đoán.

## 9. Nhiều interface và `default` method collision

Java cho phép interface khai báo `default` methods. Nếu một class triển khai **hai interface độc lập có cùng default signature**, Java không thể chọn ngầm một nhánh. Class cần cung cấp override giải quyết.

Ví dụ:

```java
interface Left {
    default String label() { return "left"; }
}
interface Right {
    default String label() { return "right"; }
}
final class Combined implements Left, Right {
    @Override public String label() {
        return Left.super.label() + "+" + Right.super.label();
    }
}
```

Đoạn này có thể biên dịch khi đặt trong đúng file/class hoặc các top-level package-private classes hợp lệ. Phương thức override biểu thị quyết định **tường minh của chủ class**. Một introduction làm class implements thêm interface có default method có thể khiến **xung đột mới** xuất hiện, dù class không đổi source.

### 9.1. Quy tắc cần nhớ

- **Class method hợp lệ** thường có ưu tiên hơn interface default tương ứng theo luật Java.
- Hai default từ những interface không có quan hệ ưu tiên có thể bắt buộc class resolve bằng override.
- Một abstract method của interface khác có thể ảnh hưởng quy tắc kế thừa và lỗi compile nếu class chưa đáp ứng hợp đồng.
- Khi introduction thêm nhiều interface, phải kiểm tra **toàn bộ tập members được kế thừa**, không chỉ những method của interface mới được thêm.
- Nếu interface thay đổi từ phiên bản thư viện A sang B và bổ sung default method mới, source trước đây hợp lệ có thể gặp conflict hoặc thay đổi dispatch khi rebuild.

Không giải quyết default collision chỉ bằng “aspect nào chạy trước”, vì đây là vấn đề **type/interface contract**, không phải thứ tự chạy advice.

## 10. Cú pháp structural introduction đặc thù của AspectJ

Ví dụ chỉ minh họa **cú pháp AspectJ**, không phải Java tiêu chuẩn; cần compiler/weaver hiểu ngôn ngữ này và lớp/interface đích tương ứng:

```java
// File: TagIntroduction.aj (minh họa ngôn ngữ AspectJ)
// Giả sử demo.Order đã tồn tại, và demo.TraceTag là interface
// có phương thức: String traceTag();

public aspect TagIntroduction {
    declare parents: demo.Order implements demo.TraceTag;

    public String demo.Order.traceTag() {
        return "tagged";
    }
}
```

Ý tưởng: phần `declare parents` bổ sung quan hệ implements interface cho target, còn **inter-type method** cung cấp implementation của `traceTag()` ở class được áp dụng theo khả năng của công cụ.

Đây là mã **không chạy độc lập** với `javac`; muốn thực thi cần các lớp đích, interface tương ứng và đúng toolchain AspectJ. Không nên lấy ví dụ này làm bằng chứng mọi weaver hay proxy đều có quyền thay đổi quan hệ implements của class.

### 10.1. Ví dụ về xung đột *không dùng để biên dịch*

Giả sử hai aspect cùng muốn giới thiệu một method có cùng signature:

```java
// Hai declarations MÔ TẢ XUNG ĐỘT (không ghép để biên dịch).
public String demo.Order.traceTag() { return "A"; }
public String demo.Order.traceTag() { return "B"; }
```

Không thể thiết kế API chỉ dựa vào kỳ vọng “weaver sẽ chọn B vì chạy sau”. Công nghệ có thể báo conflict, có quy tắc precedence hạn chế hoặc hạn chế introduction dựa vào class hierarchy. Phải dựa trên tài liệu và kiểm thử **toolchain/version** cụ thể, rồi sửa thiết kế để **một chủ sở hữu** chịu trách nhiệm mỗi member.

### 10.2. Private inter-type state

Một ITD có thể giới thiệu state riêng trong những mô hình hỗ trợ. Nhưng field đó được **khai báo ở đâu**, ai có thể đọc, compiler có phát sinh helper method/field synthetic nào và object lifetime thế nào đều cần xác minh theo luật AspectJ/weaver thực tế.

Một field `private` được giới thiệu không có nghĩa mọi đoạn source Java của target được phép truy cập nó như một field viết trực tiếp trong target. Ngược lại, một aspect đặc quyền trong công nghệ hỗ trợ có thể có quyền đặc biệt, nhưng không nên biến cơ chế ấy thành **phụ thuộc ngầm vào internals** của thư viện không thuộc quyền sở hữu.

## 11. JPMS, reflection và class-loader boundaries

Từ Java 9, **Java Platform Module System (JPMS)** bổ sung các ranh giới đóng gói. Một module có thể **exports** package để code module khác truy cập public types, trong khi **opens** cho một số dạng reflection truy cập member không public. Hai khái niệm có mục đích và tác dụng khác nhau.

Một chương trình dùng reflection có thể thử:

```java
field.setAccessible(true);
```

Nhưng trong môi trường module mạnh, thao tác đó có thể thất bại, chẳng hạn với `InaccessibleObjectException`, nếu package/module không cho phép deep reflection phù hợp. Cũng không có luật rằng thêm một tùy chọn mở package sẽ tự giải quyết mọi xung đột ITD hoặc cấp quyền cho mọi hình thức bytecode rewriting.

### 11.1. Kiểm tra phân biệt `exports` và `opens`

| Cần làm | Yêu cầu cần xem |
| --- | --- |
| Code module khác gọi public API | Exports, khả năng đọc module, accessibility |
| Reflection đến nonpublic member | Opens/deep-reflection permission nếu áp dụng |
| Bổ sung member bằng weaving | Công cụ hỗ trợ module/class loading và cấu trúc bytecode |
| Proxy triển khai interface nonpublic | Giới hạn về package/module và interface list của JDK Proxy |
| Nạp class cùng tên từ hai loader | Runtime type identity và cast/linkage |
| Hot reload thư viện | Cache/proxy/weaver có giữ class loader cũ hay không |

**Hai `Class` object có binary name giống nhau nhưng thuộc defining class loader khác nhau có thể là hai runtime types khác nhau.** Một method signature trên object của loader A không tự đáp ứng interface có tên giống hệt từ loader B.

### 11.2. Không dùng `setAccessible` như một thiết kế mặc định

Reflection mở quyền riêng tư có thể gây lỗi module, khó bảo trì và làm yếu encapsulation. Nếu muốn thêm một hành vi đọc trạng thái, ưu tiên **API công khai tối thiểu** hoặc phối hợp giữa các module qua interface ổn định. Chỉ dùng quyền truy cập đặc biệt khi có lý do và hợp đồng hỗ trợ rõ.

## 12. Java 17 runnable: mixin proxy và va chạm phương thức

Chương trình sau không dùng AOP compiler. Nó minh họa ba tình huống:

1. **Hai default methods trùng chữ ký** được giải bằng override tường minh.
2. **JDK dynamic proxy** bổ sung một interface quan sát cho **đối tượng proxy**, nhưng không sửa class target gốc.
3. **Hai interface khai báo cùng method signature** trên một proxy: handler không thể biết lời gọi được thực hiện qua kiểu tham chiếu nào chỉ từ `Method.getDeclaringClass()`; JDK Proxy dùng một `Method` tương ứng interface ưu tiên theo danh sách trong tình huống trùng method.

Đặt toàn bộ trong file `StructuralMixinDemo.java`:

```java
import java.lang.reflect.Proxy;

public class StructuralMixinDemo {
    public interface Named {
        String name();
    }

    public interface AuditTag {
        String auditTag();
    }

    public static final class Order implements Named {
        private final String id;

        public Order(String id) {
            this.id = id;
        }

        @Override
        public String name() {
            return "order-" + id;
        }
    }

    public interface Left {
        default String label() {
            return "left";
        }
    }

    public interface Right {
        default String label() {
            return "right";
        }
    }

    public static final class Combined implements Left, Right {
        @Override
        public String label() {
            return Left.super.label() + "+" + Right.super.label();
        }
    }

    public interface FirstCode {
        String code();
    }

    public interface SecondCode {
        String code();
    }

    static Object adapt(Order target) {
        return Proxy.newProxyInstance(
                StructuralMixinDemo.class.getClassLoader(),
                new Class<?>[] { Named.class, AuditTag.class },
                (proxy, method, args) -> {
                    if (method.getName().equals("name")
                            && method.getParameterCount() == 0) {
                        return target.name();
                    }
                    if (method.getName().equals("auditTag")
                            && method.getParameterCount() == 0) {
                        return "audit:" + target.name();
                    }
                    if (method.getName().equals("toString")
                            && method.getParameterCount() == 0) {
                        return "AugmentedOrder";
                    }
                    throw new UnsupportedOperationException(
                            method.getName());
                });
    }

    static Object duplicateMethods() {
        return Proxy.newProxyInstance(
                StructuralMixinDemo.class.getClassLoader(),
                new Class<?>[] { FirstCode.class, SecondCode.class },
                (proxy, method, args) ->
                        method.getDeclaringClass().getSimpleName());
    }

    public static void main(String[] args) {
        Order target = new Order("7");
        Object adapted = adapt(target);

        System.out.println("DOMAIN " + target.name());
        System.out.println("MIXIN_NAME " + ((Named) adapted).name());
        System.out.println("MIXIN_TAG " + ((AuditTag) adapted).auditTag());
        System.out.println("TARGET_TAG "
                + AuditTag.class.isInstance(target));
        System.out.println("PROXY_TAG " + (adapted instanceof AuditTag));
        System.out.println("DEFAULT " + new Combined().label());

        Object duplicate = duplicateMethods();
        System.out.println("DUP_FIRST "
                + ((FirstCode) duplicate).code());
        System.out.println("DUP_SECOND "
                + ((SecondCode) duplicate).code());
    }
}
```

Biên dịch và chạy bằng Java 17 trở lên:

```bash
javac -encoding UTF-8 StructuralMixinDemo.java
java StructuralMixinDemo
```

Stdout dự kiến chính xác:

```text
DOMAIN order-7
MIXIN_NAME order-7
MIXIN_TAG audit:order-7
TARGET_TAG false
PROXY_TAG true
DEFAULT left+right
DUP_FIRST FirstCode
DUP_SECOND FirstCode
```

### 12.1. Vì sao target vẫn không có `AuditTag`?

`adapt(target)` tạo ra một **đối tượng proxy khác** triển khai `Named` và `AuditTag`. Invocation handler chuyển `name()` về target và tự cung cấp `auditTag()`. Vì class `Order` gốc **không implements AuditTag**, dòng `TARGET_TAG false` đúng; riêng object proxy mới in `PROXY_TAG true`.

**Không được kết luận AOP qua proxy đã “thêm method vào class Order”.** Nó tạo một view/adapter khác. Người giữ target gốc vẫn không gọi được `target.auditTag()` ở Java compile time.

### 12.2. Vì sao `Combined` cần override?

`Left` và `Right` đều cung cấp `default String label()`. Class `Combined` không thể im lặng dùng một trong hai. Nó override và lựa chọn kết hợp `Left.super.label()` với `Right.super.label()`, tạo `left+right`.

Một introduction thêm interface có default method vào class đang có interface khác phải tính các xung đột tương tự.

### 12.3. Vì sao hai kiểu tham chiếu đều nhận `FirstCode`?

Hai interface `FirstCode` và `SecondCode` đều khai báo `String code()`. Proxy thực thi một implementation cho signature trùng nhau; khi handler nhận `Method`, nó không có thông tin “caller đã cast sang SecondCode rồi gọi”. Trong JDK Proxy, `Method` cho signature duplicate được lấy theo quy tắc về **interface xuất hiện trước** trong danh sách interface của proxy.

Bởi `FirstCode.class` đứng trước `SecondCode.class`, handler trả `"FirstCode"` cho cả hai lượt. Đây là lý do **không dùng `getDeclaringClass()` để quyết định quyền/nghĩa khác nhau cho hai view có cùng signature trên một proxy**.

### 12.4. Hạn chế và an toàn của ví dụ

- Proxy ở đây chỉ hỗ trợ hai methods `name()` và `auditTag()` cùng `toString()` ở handler; mọi method khác (chẳng hạn `equals`, `hashCode`) cố ý chưa có chính sách xử lý. **Không dùng làm adapter sản xuất chưa hoàn thiện**.
- Vì mọi interface được chọn là public, ví dụ không cần xử lý đặc thù về interface package-private từ nhiều package/module.
- Ví dụ không có ITD, không thay bytecode và không mở quyền truy cập `private` của target; `id` chỉ được sử dụng nội bộ qua `name()`.
- Không có field được bổ sung vào `Order`; nếu cần trạng thái per-proxy, handler/coordinator phải quản lý vòng đời, đồng thời và cleanup của state ấy.
- Nếu hai interface có cùng tên/parameters nhưng return type không tương thích, JDK Proxy có ràng buộc tạo proxy và có thể báo lỗi; chương trình minh họa dùng cùng `String` để có kết quả xác định.
- Caller phải thật sự dùng **proxy instance**, không dùng target gốc, thì phần bổ sung mới có mặt.

## 13. Kiểm soát tên và khả năng tương thích khi nâng cấp

Giả sử thư viện `Order` ở phiên bản 1 chưa có `auditTag()`. Một aspect giới thiệu method đó thành công. Ở phiên bản 2, tác giả thư viện **tự thêm** `auditTag()` với cùng signature hoặc nghĩa khác. Giờ xuất hiện nguy cơ xung đột source, bytecode hoặc ngữ nghĩa.

Để tránh:

1. Ưu tiên bổ sung những **interface có owner riêng** và tên method đặc trưng, chẳng hạn `AuditTraceView.traceTag()`, thay vì thêm những tên phổ biến như `getId`, `status`, `save`.
2. Công bố **API contract**: ai sở hữu, có thể sửa tên/kiểu không, bảo đảm về return/throw và thread-safety.
3. Kiểm tra **collision với cả class hierarchy**, kể cả members được kế thừa.
4. Kiểm tra **generics erasure, overload, bridge methods** và static/instance.
5. Có **binary compatibility test** với các artifact được weave, không chỉ unit test trên source.
6. Đánh giá kết quả khi thư viện nâng cấp: member mới ở target có trùng với introduction không?
7. Không phát tán một “public synthetic feature” vô tình trở thành API mà các module khác phụ thuộc nếu chưa cam kết duy trì.
8. Khi cần không làm thay đổi API target, ưu tiên **composition hoặc adapter**.

### 13.1. Binary compatibility không bằng source compatibility

Một class đã weave có thêm method và interface có thể thay đổi kết quả reflection, dispatch và kiểm tra `instanceof`. Caller đã biên dịch với API được giới thiệu có thể cần artifact **được weave phù hợp** lúc chạy. Nếu runtime nạp bản chưa weave, có thể gặp `NoSuchMethodError`, `ClassCastException` hoặc lỗi linking khác, tùy hình thức dùng.

Không đánh giá bằng một lệnh `javac` chạy trên lớp chưa weave rồi suy rằng introduction vô dụng. Ngược lại, không dùng một bản woven artifact làm bằng chứng mọi môi trường classpath/modulepath đều nhìn thấy cùng API.

## 14. Kế thừa, constructor và hạn chế của cấu trúc đích

Một introduction có thể nhắm class hoặc interface theo mô hình công cụ, nhưng những trường hợp sau cần thận trọng:

- Target là **final class**: không thể subclass thông thường, nhưng một weaver có thể có khả năng thêm một số members mà không subclass; phải xác nhận cụ thể.
- Target có **final method**: không được override theo Java như method thông thường; nếu cần đổi hành vi, advice khác override.
- Target có constructor bắt buộc bất biến: thêm field mới không đồng nghĩa field được gán đúng cho mọi đường khởi tạo/deserialization.
- Target dùng reflection/serialization: field bổ sung có thể ảnh hưởng quan sát cấu trúc, chiến lược serialize hoặc layout.
- Target là record/sealed class: JVM và Java có ràng buộc đặc biệt về state, inheritance và permitted subclasses; không suy một ITD tùy ý được phép phá các ràng buộc ấy.
- Target interface có private/default/static members: mỗi loại có luật thừa kế/truy cập khác nhau.
- Target được nạp trước khi cơ chế weaving tương ứng áp dụng: khả năng thêm thành phần có thể bị giới hạn bởi **thời điểm load/redefine/retransform**.

### 14.1. Trạng thái bổ sung phải có vòng đời

Nếu aspect giới thiệu một field mới cho mỗi target, phải hỏi:

- Field khởi tạo lúc nào và mặc định có ý nghĩa không?
- Object target có thể được tạo bằng reflection, deserialization, factory hoặc bytecode instrumentation không?
- Nhiều thread có thể ghi field được giới thiệu không?
- Field giữ request/context sống quá lâu không?
- Nếu target được clone hoặc serialize, giá trị field mới phải được xử lý ra sao?
- Có phương thức cleanup/close phù hợp không?

ITD không tự làm field mới **thread-safe** và cũng không tự giải phóng tài nguyên ngoài heap.

## 15. Xung đột khi nhiều aspect cùng mở rộng một kiểu

Một codebase có thể có hai module AOP khác nhau:

```text
AuditAspect  -> introduces Order.trace()
MetricAspect -> introduces Order.trace()
```

Nếu hai chức năng muốn nghĩa khác nhau nhưng dùng cùng signature, việc chúng nằm ở hai file không làm xung đột biến mất. Một bản build có thể thất bại, một cơ chế có thể yêu cầu precedence, hoặc một số tổ hợp không được phép; **không có quy tắc chung “aspect mới nhất thắng”**.

Cách giải hợp lý:

1. Tìm **hợp đồng thực tế** cả hai thành phần muốn cung cấp.
2. Nếu cùng một khả năng, hợp nhất **một interface/owner**, không tạo hai thực thể tranh chấp.
3. Nếu là hai khả năng khác nhau, **đặt tên khác** phù hợp ngữ cảnh (ví dụ `auditTraceId` và `metricSeriesId`).
4. Nếu một khả năng cần tái sử dụng kết quả của khả năng kia, chuyển sang **API phối hợp tường minh**.
5. Nếu không sở hữu target hoặc thư viện thay đổi nhiều, dùng **adapter/composition** để tránh chiếm namespace của target.
6. Kiểm thử kết quả trên artifact thực sau weaving và khi cả hai aspect cùng bật.

Việc đặt tên có prefix/suffix ngẫu nhiên để tránh lỗi compiler không giải quyết **semantic collision** nếu cùng một method name thật sự cần hai loại hành vi trái nhau.

## 16. Checklist trước khi bổ sung member bằng AOP

| Câu hỏi | Cần xác nhận |
| --- | --- |
| Công cụ có hỗ trợ **structural introduction** không? | ITD, declare parents, interface introduction hay chỉ proxy adapter |
| Target class có nằm trong phạm vi được xử lý? | Build, weaver, loader, module, package, artifact |
| Có member trùng ở target hoặc superclass không? | Field/method signatures, static, return types |
| Có nhiều aspect cùng mở rộng target không? | Conflict/owner/precedence nếu có |
| Có interface default trùng method không? | Java multiple-inheritance resolution |
| Member có thỏa visibility và interface contract không? | Public/protected/package/private, accessible types |
| Có generic erasure/bridge clash không? | Erased signatures và binary descriptors |
| Có final, sealed, record, constructor constraint không? | Ràng buộc class/bytecode được hỗ trợ |
| Có module/classloader boundary không? | Exports/opens, defining loader, runtime package |
| Caller dùng đúng object/artifact không? | Proxy vs original target; woven vs unwoven class |
| Có đường bypass hoặc khác compiler không? | Direct target call, self-invocation, build cache |
| Member mới có giữ state/resource không? | Thread-safety, lifetime, cleanup, serialization |
| Nâng cấp thư viện thì sao? | API collisions và binary compatibility |
| Có phương án ít can thiệp hơn không? | Public API, adapter, decorator, composition |

## 17. Kiểm thử ở những giai đoạn khác nhau

| Thời điểm | Ví dụ lỗi cần bắt |
| --- | --- |
| **Compile source** | Method duplicate, generic erasure, thiếu public implementation |
| **Aspect compilation** | ITD conflict hoặc target name/signature sai |
| **Weaving** | Không thể sửa class structure, incompatibility, thiếu class |
| **Class loading/linking** | Loader mismatch, module access, VerifyError/LinkageError |
| **Runtime calling** | `ClassCastException`, method không tồn tại, proxy view không đúng |
| **Reflection** | `getDeclaredMethods` khác mong đợi giữa woven/unwoven |
| **Concurrency** | Field bổ sung bị ghi đồng thời, race và retention |
| **Serialization** | State được bổ sung không khớp policy phiên bản |
| **Library upgrade** | API gốc mới chiếm tên introduction |
| **Regression** | Hai aspect cùng khai báo member, thứ tự/coverage thay đổi |

### 17.1. Test thuận và test nghịch

Không chỉ kiểm tra “gọi method mới được”. Cần kiểm tra:

- Không có **hai definitions** không tương thích trong artifact.
- Caller qua interface mới nhìn đúng implementation/return/throw.
- Caller giữ target gốc trong mô hình proxy **không giả nhận** API mới.
- Một method `private` trong target vẫn giữ đúng ranh giới truy cập đã thiết kế.
- Xung đột `default` được resolve tường minh.
- Phiên bản thư viện mới có hoặc không có member trùng được phát hiện sớm.
- Module khác/class loader khác không được cấp quyền “tình cờ”.
- Một lời gọi tại nhánh exception không giữ state/resource ngoài vòng đời.
- Nếu thay đổi cấu trúc là tính năng bắt buộc, bản triển khai **chưa weave** bị phát hiện thay vì âm thầm chạy thiếu tính năng.

### 17.2. Verify artifact cuối

Một bản build có thể biên dịch thành công nhưng chương trình thực tế nạp artifact khác (ví dụ class gốc chưa weave). Khi đó các test chạy trong IDE có thể pass nhưng deployment lỗi ở `instanceof` hoặc gọi method được giới thiệu.

Hãy kiểm tra đúng **artifact runtime**, classpath/modulepath, phiên bản JVM và thứ tự class loader. Nếu cần, kiểm tra public API qua reflection **một cách có kiểm soát** và chạy end-to-end tests trên chính artifact dự kiến triển khai.

## 18. Sai lầm phổ biến

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Coi ITD là tính năng mặc định của mọi AOP | Viết mã không được công cụ hỗ trợ | Xác minh khả năng toolchain |
| Nghĩ aspect đọc mọi private field | Vi phạm encapsulation hoặc compile/access fail | Dùng API/hợp đồng hoặc quyền đặc biệt khi được hỗ trợ |
| Nhầm `protected` với “mọi subclass gọi được trên mọi object” | Illegal access | Áp đúng luật subclass/receiver |
| Cùng package name là đủ package-private | Classloader/runtime package mismatch | Kiểm tra loader và module |
| ITD thêm method trùng method gốc | Collision/đổi hành vi | Một owner, rename, adapter |
| Chỉ khác return type mà gọi là overload | Compile conflict | Đổi params hoặc tên theo contract |
| `List<String>` vs `List<Integer>` coi là overload | Generic erasure clash | Thiết kế interface/type-safe API khác |
| Coi field hiding như override | Đọc hai state khác nhau | Dùng accessor rõ |
| Trộn static method với instance override | Dispatch sai | Tách chiến lược, đổi tên |
| Hai default methods cùng chữ ký không resolve | Compile conflict | Override tường minh |
| Đoán Proxy handler biết interface của caller | Sai với duplicate method | Quy định một behavior thống nhất |
| Nghĩ proxy đã sửa target class | `instanceof`/method call gốc thất bại | Dùng đúng proxy hoặc woven artifact |
| Dựa vào `setAccessible(true)` trong mọi module | Có thể InaccessibleObjectException | Exports/opens theo hợp đồng hoặc API công khai |
| Không test khi nâng cấp thư viện | New member collision/binary break | Compatibility matrix |
| Không kiểm tra bytecode đã weave | Runtime không có member | Artifact-level validation |
| Thêm field giữ request lâu dài | Memory retention/race | Scoped state, owner/cleanup |

## 19. Bài tập vận dụng có đáp án

### Bài 1 — Hai aspect trùng tên

AuditAspect và TraceAspect đều giới thiệu `Order.traceId()` với những ý nghĩa khác nhau. Có thể để cả hai rồi dùng advice precedence chọn phiên bản không?

**Đáp án:** Không được mặc định. Đây là **structural member collision**, không chỉ vấn đề thứ tự advice. Nên xác định owner hoặc tách thành những hợp đồng/names rõ ràng.

### Bài 2 — Package-private và module

Một ITD được biên dịch ở package chữ giống target, nhưng code nạp từ class loader khác. Có thể tự cho rằng field package-private truy cập được không?

**Đáp án:** Không. Runtime package và module/class-loader identity phải được xem cụ thể; tên package dạng chuỗi giống nhau không đủ bảo đảm quyền.

### Bài 3 — Generic erasure

Target đã có `inspect(List<String>)`. Aspect muốn thêm `inspect(List<Integer>)`. Vì sao rủi ro?

**Đáp án:** Cùng erasure `inspect(List)`, không phải hai overload hợp lệ dựa trên generic type arguments. Đổi tên hoặc xây một API khác.

### Bài 4 — Return type

Một class đã có `int count()`; aspect bổ sung `String count()`. Compiler có chọn method theo nơi gán kết quả không?

**Đáp án:** Không. Java không overload chỉ theo return type. Bổ sung cần tên/chữ ký hợp lệ theo type system và toolchain.

### Bài 5 — Default methods

Class implements cả `Left` và `Right`, mỗi interface có `default label()`. Làm sao giải quyết?

**Đáp án:** Cung cấp override `label()` rõ, có thể gọi `Left.super.label()` và `Right.super.label()` theo điều kiện Java cho phép.

### Bài 6 — Proxy và target

Từ chương trình runnable, tại sao `AuditTag.class.isInstance(target)` là false nhưng proxy trả true?

**Đáp án:** Proxy là **một object khác** triển khai giao diện bổ sung; nó không mutate class `Order` gốc.

### Bài 7 — Duplicate proxy methods

Vì sao `((SecondCode) duplicate).code()` vẫn in `FirstCode`?

**Đáp án:** Hai interfaces có signature giống nhau và proxy implementation không biết caller cast view nào. `Method` handler nhận được gắn với interface đầu tiên theo quy tắc JDK Proxy đối với duplicate methods.

### Bài 8 — Public interface contract

Một interface yêu cầu `public String id()`; class có method cùng chữ ký nhưng package-private. Chỉ declare implements interface đã đủ chưa?

**Đáp án:** Chưa. Implementation phải đáp ứng visibility và contract; cần một phương thức public hợp lệ theo khả năng công cụ.

### Bài 9 — Field vs method

Khi subclass có field cùng tên superclass, tại sao `Parent p = new Child(); p.label` và `p.label()` có thể khác?

**Đáp án:** Field access liên kết theo kiểu compile-time của expression, còn instance method override dùng dynamic dispatch.

### Bài 10 — Artifact

Code dùng method được ITD thêm chạy khi build bằng AOP compiler, nhưng gặp lỗi khi deployment. Nguyên nhân cần kiểm tra trước?

**Đáp án:** Bản triển khai có nạp **woven class đúng** không, classpath/modulepath/class loader có trộn woven và unwoven hay không, và runtime API thật có method/implements interface như dự kiến không.

### Bài 11 — Private field

Một aspect muốn đọc dữ liệu nhạy cảm từ `private` field của target. Có nên coi đó là quyền mặc định của AOP?

**Đáp án:** Không. Phải xem cơ chế access cụ thể và trách nhiệm bảo mật; thường nên cung cấp API tối thiểu được chủ lớp cho phép thay vì phá encapsulation.

## 20. Ghi nhớ

- **Structural introduction khác advice**: thêm method/field/interface không giống chạy trước/sau một join point.
- **ITD/weaving khác proxy mixin**: proxy thường chỉ làm object bọc mang thêm interface, không sửa class target gốc.
- Quyền truy cập `public/protected/package-private/private` còn chịu luật **class accessibility, modules, loaders và compiler AOP**; aspect không tự là ngoại lệ cho mọi giới hạn.
- **Xung đột tên** phải xét member kind, method signature, static/instance, inheritance, generic erasure và default interface methods; không thể giải tất cả bằng advice precedence.
- **Field hiding không phải overriding**, **return type khác không tạo overload**, và **default method conflict** cần giải quyết tường minh.
- Interface introduction phải thỏa **public method contract**; private state được giới thiệu không tự trở thành public API.
- **JPMS exports khác opens**; reflection hoặc weaving chỉ hoạt động khi quyền/toolchain hỗ trợ, không dựa vào tên package giống nhau.
- Tên introduction phải có owner rõ và chịu được **library upgrade**; ưu tiên adapter/composition khi không cần đổi bytecode của target.
- Kiểm thử trên **artifact đã weave hoặc proxy đúng** với các đường lỗi, modules, loader, collision và runtime behavior, không chỉ happy path.
