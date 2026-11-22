# Thay đổi superclass, interface và quan hệ kế thừa

Trong Java, superclass và interface xác định một phần hợp đồng mà class công bố với code sử dụng nó. Một class có thể kế thừa phương thức và trạng thái từ superclass, triển khai một hoặc nhiều interface, hoặc nhận implementation mặc định từ interface cha. Khi thư viện thay đổi cấu trúc kế thừa, ảnh hưởng có thể lan tới các ứng dụng đã biên dịch, kể cả khi tên phương thức mà consumer gọi vẫn còn trong source.

Trong Java Compatibility Migration, thay đổi hierarchy cần được xem xét ở ít nhất ba mức:

- **Source compatibility:** source consumer có biên dịch lại được không? Các subclass và implementation có còn override/implement đúng hợp đồng không?
- **Binary compatibility:** bytecode đã biên dịch trước đây có còn nạp, xác minh và liên kết được với class/interface mới không?
- **Behavioral compatibility:** phương thức được dispatch có còn là implementation cũ không? Quan hệ subtype, lời gọi `super`, default method và hành vi kế thừa có thay đổi không?

Một thay đổi hierarchy có thể không làm hỏng mọi binary ngay khi class được nạp, nhưng vẫn gây lỗi khi một đường code cụ thể được thực thi. Vì vậy, chỉ kiểm tra compile hoặc startup là chưa đủ.

## 1. Mô hình kế thừa trong Java và JVM

### 1.1. Superclass và interface

Một class Java chỉ có một direct superclass (ngoại trừ `Object`, là gốc của hệ thống class thông thường), nhưng có thể triển khai nhiều interface:

```java
public class PremiumOrder extends Order implements Billable, Auditable {
    // Kế thừa từ Order và triển khai hai interface.
}
```

Quan hệ này tạo ra nhiều hợp đồng:

- `PremiumOrder` là subtype của `Order`, `Billable` và `Auditable`.
- Code nhận `Order` có thể nhận `PremiumOrder`.
- Code nhận `Billable` có thể nhận `PremiumOrder` và gọi các phương thức trong hợp đồng `Billable`.
- Các phương thức được kế thừa hoặc triển khai được chọn theo quy tắc method lookup và dynamic dispatch của JVM.

Một interface có thể mở rộng nhiều interface khác:

```java
public interface Billable extends Identifiable, Taxable {
    Receipt createReceipt();
}
```

Một thay đổi ở interface cha có thể ảnh hưởng tới tất cả interface con và class triển khai ở nhiều module khác nhau.

### 1.2. Quan hệ kế thừa được ghi trong class file

Class file chứa thông tin về superclass và các interface trực tiếp mà class triển khai. JVM dùng thông tin đó để xác minh type safety, kiểm tra khả năng gán kiểu, tìm method và thực hiện dispatch.

Khi biên dịch lời gọi phương thức, bytecode thường ghi một symbolic reference gồm owner type, tên method và descriptor. Lệnh gọi có thể là `invokevirtual`, `invokeinterface`, `invokespecial` hoặc `invokestatic`, tùy loại phương thức và cách gọi.

Ví dụ:

```java
Order order = new PremiumOrder();
order.calculateTotal();
```

Kiểu tĩnh `Order` tham gia vào quá trình biên dịch và xác định method reference được ghi trong bytecode; object thực tế `PremiumOrder` tham gia vào dynamic dispatch đối với phương thức instance có thể override.

Vì thế, thay đổi hierarchy có thể ảnh hưởng cả việc JVM có tìm thấy method được tham chiếu hay không và implementation nào được chọn khi chạy.

### 1.3. Phân biệt method resolution và method selection

Hai bước thường bị nhầm lẫn:

1. **Resolution:** JVM tìm method/field phù hợp với symbolic reference trong constant pool, dựa trên owner, tên, descriptor và quy tắc tìm kiếm trong hierarchy.
2. **Selection/dispatch:** với lời gọi instance có dynamic dispatch, JVM chọn implementation phù hợp với class thực tế của receiver.

Một method có thể tồn tại trong class con nhưng không giúp symbolic reference được resolve nếu bytecode đang tham chiếu owner là superclass không còn khai báo hoặc kế thừa method đó. Ngược lại, method reference có thể resolve thành công nhưng implementation được chọn đã thay đổi vì hierarchy hoặc override thay đổi.

## 2. Thay đổi superclass

Thay superclass là thay đổi cấu trúc có phạm vi ảnh hưởng rộng. Nó tác động tới quan hệ subtype, các method được kế thừa, constructor chain, protected access, `super` call và method dispatch.

### 2.1. Đổi superclass sang một lớp không liên quan

Phiên bản thư viện cũ:

```java
public class Order extends BaseEntity {
    public String getId() {
        return super.getId();
    }
}
```

Consumer có thể dùng:

```java
BaseEntity entity = new Order();
```

Nếu phiên bản mới đổi thành:

```java
public class Order extends Object {
    public String getId() {
        return "generated";
    }
}
```

thì `Order` không còn là subtype của `BaseEntity`. Source consumer có phép gán `BaseEntity entity = new Order()` sẽ không biên dịch lại. Binary cũ có thể gặp lỗi xác minh hoặc lỗi khi ép kiểu/liên kết các thao tác dựa trên quan hệ cũ, tùy bytecode và đường thực thi.

Ngay cả khi lớp mới tự khai báo một method có cùng tên với method trước đây được kế thừa, điều đó không khôi phục toàn bộ hợp đồng của superclass cũ. Các method khác, field, constructor, protected member, annotation và semantics của `BaseEntity` vẫn có thể bị mất.

### 2.2. Đổi sang một subclass của superclass cũ

Giả sử `Order` trước đây kế thừa `BaseEntity`, sau đó chuyển sang `AuditedEntity`, trong đó `AuditedEntity extends BaseEntity`:

```java
public class BaseEntity {
    public String getId() { return "id"; }
}

public class AuditedEntity extends BaseEntity {
    public Instant getCreatedAt() { return Instant.now(); }
}

public class Order extends AuditedEntity {
}
```

Về quan hệ subtype, `Order` vẫn là `BaseEntity` vì `AuditedEntity` kế thừa `BaseEntity`. Một số source consumer tiếp tục biên dịch mà không cần sửa. Tuy nhiên, đây vẫn là thay đổi hierarchy cần đánh giá:

- Constructor chain mới có thể gọi constructor khác và thay đổi trạng thái khởi tạo.
- `AuditedEntity` có thể override method mà `Order` trước đây kế thừa trực tiếp.
- Method mới được thêm vào superclass trung gian có thể làm thay đổi overload/override trong subclass.
- Field và method có cùng tên trong hierarchy có thể thay đổi việc truy cập hoặc che khuất (*hiding*).
- Serialization, reflection và framework introspection có thể quan sát hierarchy khác trước.

Giữ quan hệ subtype không đồng nghĩa giữ toàn bộ behavioral compatibility.

### 2.3. Thay đổi constructor của superclass

Constructor không được kế thừa. Constructor của subclass phải gọi một constructor hợp lệ của superclass, tường minh hoặc ngầm định.

Nếu superclass trước đây có constructor không tham số:

```java
public class BaseEntity {
    public BaseEntity() { }
}
```

thì subclass có thể không khai báo constructor và compiler tự chèn lời gọi `super()`.

Nếu phiên bản mới bỏ constructor không tham số:

```java
public class BaseEntity {
    public BaseEntity(String tenantId) { }
}
```

source subclass không có constructor tường minh sẽ không biên dịch lại vì lời gọi `super()` mặc định không còn hợp lệ. Những subclass đã biên dịch trước đây cũng cần được xem xét: khi superclass mới không còn constructor descriptor mà bytecode subclass gọi, khởi tạo subclass có thể thất bại với `NoSuchMethodError` trong quá trình gọi constructor.

Khi thay constructor của superclass, cần kiểm tra tất cả subclass nội bộ và consumer bên ngoài có thể kế thừa class đó.

### 2.4. Thay đổi `protected` và package access trong hierarchy

Subclass có thể truy cập protected member theo quy tắc Java. Di chuyển một method hoặc field sang superclass khác, đổi package hoặc thay đổi visibility có thể làm source consumer mất quyền truy cập.

Ví dụ:

```java
package com.example.base;

public class BaseEntity {
    protected String tenantId;
}
```

Subclass ở package khác có thể truy cập member protected theo quy tắc dành cho subclass. Nếu member chuyển sang một class không còn nằm trong hierarchy hoặc bị giảm visibility, subclass có thể không biên dịch và bytecode cũ có thể gặp lỗi truy cập khi thực thi.

Các thay đổi package-private còn nhạy hơn: quyền truy cập phụ thuộc package, không chỉ quan hệ kế thừa. Cần xem cả module/package boundary khi di chuyển class.

### 2.5. Thêm method vào superclass có thể đổi dispatch

Một superclass mới có thể thêm method trùng tên và signature với method mà subclass trước đây tự khai báo. Method đó có thể trở thành override thực sự sau khi source được biên dịch lại.

Phiên bản cũ:

```java
public class BaseTask {
}

public class CustomTask extends BaseTask {
    public void execute() {
        System.out.println("custom");
    }
}
```

Phiên bản mới của superclass:

```java
public class BaseTask {
    public void execute() {
        System.out.println("base");
    }
}
```

Khi biên dịch lại `CustomTask`, method `execute()` của nó override method superclass. Nếu code cũ gọi `super.execute()` sau khi được sửa hoặc thêm annotation `@Override`, hành vi sẽ khác với code trước đây vốn không có method đó trong lớp cha.

Đặc biệt, thêm method vào superclass có thể làm thay đổi dispatch của subclass mà không cần thay đổi call site. Nếu subclass được biên dịch lại, method cùng signature có thể trở thành override; nếu binary cũ được giữ nguyên, việc resolution và dispatch cần được đánh giá trên class file thực tế cùng hierarchy mới.

## 3. Thay đổi interface được triển khai

Class có thể triển khai nhiều interface. Thay đổi danh sách interface làm thay đổi tập kiểu mà class có thể được gán tới và các method contract mà class cần đáp ứng.

### 3.1. Thêm interface

Giả sử class ban đầu:

```java
public class CsvExporter {
    public byte[] export() { return new byte[0]; }
}
```

Phiên bản mới khai báo thêm interface:

```java
public interface Exportable {
    byte[] export();
}

public class CsvExporter implements Exportable {
    @Override
    public byte[] export() { return new byte[0]; }
}
```

Thêm interface có thể mở rộng khả năng sử dụng của class, nhưng cần xem xét các trường hợp:

- Interface chỉ khai báo abstract method và class đã có method tương ứng: class có thể đáp ứng contract mà không cần thêm implementation mới.
- Interface có abstract method mà class chưa triển khai: source build có thể thất bại nếu class cụ thể không đáp ứng interface; nếu class file được tạo hoặc phát hành theo cách không đầy đủ, lời gọi method có thể ném `AbstractMethodError`.
- Interface có default method: method đó có thể tham gia vào method selection và thay đổi implementation được gọi.
- Interface có default method xung đột với default method khác trong hierarchy: có thể phát sinh compile-time conflict hoặc lỗi linkage khi class/interface không cung cấp override giải quyết xung đột.
- Interface có cùng method signature với method đã có nhưng semantics khác: class có thể được xem là triển khai contract mới dù implementation cũ không đáp ứng kỳ vọng mới.

Thêm interface không chỉ là thêm một dòng `implements`; đó là công bố thêm một contract cho mọi consumer.

### 3.2. Xóa interface

Nếu class bỏ một interface khỏi danh sách `implements`, các source consumer gán class đó vào kiểu interface sẽ không còn biên dịch:

```java
Exportable exporter = new CsvExporter();
```

Các binary đã biên dịch có thể vẫn nạp class, nhưng khi thực thi thao tác ép kiểu, truyền đối số hoặc gọi `invokeinterface` dựa trên interface đã bị loại bỏ, có thể gặp `ClassCastException` hoặc `IncompatibleClassChangeError` tùy thao tác và trạng thái class được nạp.

Nếu interface bị xóa hoàn toàn khỏi thư viện, binary tham chiếu trực tiếp tới interface có thể gặp `NoClassDefFoundError` khi JVM cần resolve kiểu đó.

### 3.3. Đổi interface cha của interface

Interface có thể mở rộng nhiều interface:

```java
public interface SecureRepository extends Repository, Auditable {
}
```

Nếu phiên bản mới bỏ `Repository` khỏi danh sách superinterface, code gán `SecureRepository` vào `Repository` sẽ không còn hợp lệ khi biên dịch lại. Các binary dựa trên quan hệ subtype cũ cũng cần được kiểm tra khi cast, method resolution hoặc gọi qua interface.

Thêm superinterface có thể đưa thêm abstract/default method vào hợp đồng. Đặc biệt, default method từ nhiều interface cha có thể tạo xung đột và yêu cầu interface con hoặc class triển khai override tường minh.

## 4. Thay đổi abstract method và default method trong interface

Java 8 bổ sung default method cho interface. Điều này giúp thư viện bổ sung hành vi mà không bắt buộc mọi implementation phải được sửa ngay, nhưng không loại bỏ mọi rủi ro compatibility.

### 4.1. Thêm abstract method

Interface cũ:

```java
public interface PaymentGateway {
    PaymentResult pay(PaymentRequest request);
}
```

Consumer có implementation:

```java
public class LegacyGateway implements PaymentGateway {
    @Override
    public PaymentResult pay(PaymentRequest request) {
        return PaymentResult.success();
    }
}
```

Interface mới thêm abstract method:

```java
public interface PaymentGateway {
    PaymentResult pay(PaymentRequest request);
    void refund(RefundRequest request);
}
```

Khi biên dịch lại `LegacyGateway`, compiler báo class chưa triển khai `refund`. Binary `LegacyGateway` đã biên dịch trước đó có thể vẫn được nạp, nhưng nếu code gọi `refund` trên instance đó, JVM không tìm được implementation và có thể ném `AbstractMethodError`.

Đây là rủi ro quan trọng với plugin API và SPI: implementation có thể nằm trong repository hoặc sản phẩm của bên thứ ba mà nhóm phát triển thư viện không kiểm soát.

### 4.2. Thêm default method

Có thể bổ sung default method để cung cấp hành vi mặc định:

```java
public interface PaymentGateway {
    PaymentResult pay(PaymentRequest request);

    default void refund(RefundRequest request) {
        throw new UnsupportedOperationException("Refund is not supported");
    }
}
```

Implementation cũ không cần thêm method để source compile lại. Tuy nhiên, default method chỉ duy trì compatibility ở mức cấu trúc; hành vi mặc định có thể không phù hợp với mọi implementation. Nếu caller bắt đầu gọi `refund`, implementation cũ có thể ném exception.

Một default method mới cũng có thể xung đột với method cùng signature từ interface khác hoặc với method trong superclass. Quy tắc ưu tiên giữa class method, interface default method và interface cha cần được xét khi biên dịch và chạy.

### 4.3. Xung đột default method

Hai interface không liên quan cùng khai báo default method có cùng signature:

```java
interface JsonExport {
    default String format() { return "json"; }
}

interface XmlExport {
    default String format() { return "xml"; }
}
```

Class triển khai cả hai phải giải quyết xung đột:

```java
class ReportExporter implements JsonExport, XmlExport {
    @Override
    public String format() {
        return JsonExport.super.format();
    }
}
```

Nếu một interface mới được thêm vào hierarchy và mang theo default method trùng signature, class hoặc interface con có thể phải thêm override. Việc thay đổi interface cha cũng có thể khiến một default method trước đây được chọn trở nên không còn duy nhất.

### 4.4. Ưu tiên class method

Trong xung đột giữa một method cụ thể trong class hierarchy và một default method từ interface, class method được ưu tiên. Điều này có thể làm thay đổi hành vi khi một method mới được thêm vào superclass, hoặc khi interface mới đưa default method vào hierarchy.

Với thư viện nền tảng, không nên dựa vào suy đoán từ tên method. Hãy biên dịch consumer đại diện và kiểm tra dispatch trên class file thực tế.

## 5. Thay đổi class thành interface hoặc interface thành class

Thay đổi bản chất một type từ class sang interface hoặc ngược lại là thay đổi mạnh. Bytecode lưu loại symbolic reference và các lệnh gọi tương ứng; khi loại type thay đổi, JVM có thể phát hiện mismatch.

Ví dụ, consumer đã biên dịch dựa trên class `Repository` có thể dùng `new Repository()` hoặc `extends Repository`. Nếu thư viện đổi `Repository` thành interface, source consumer không còn hợp lệ. Binary cũ có thể gặp `IncompatibleClassChangeError` khi JVM phát hiện class/interface kind không khớp với bytecode.

Chiều ngược lại cũng vậy: nếu một interface trở thành class, code dùng `implements`, interface method invocation hoặc multiple inheritance contract có thể không còn hợp lệ.

Thông thường, thay đổi kiểu type này nên được xem là breaking change và thực hiện trong major version, kèm API mới hoặc adapter type để hỗ trợ giai đoạn chuyển tiếp.

## 6. Thay đổi final, abstract và khả năng kế thừa

### 6.1. Thêm `final` vào class

Nếu một class trước đây có thể được subclass hóa nhưng phiên bản mới thêm `final`, source subclass không còn biên dịch. Binary subclass cũ có thể gặp `VerifyError` khi JVM xác minh rằng nó kế thừa từ class final.

Đây là thay đổi có ảnh hưởng trực tiếp tới framework và thư viện dựa trên subclass/proxy như ORM, mocking, AOP hoặc dependency injection.

### 6.2. Thêm `abstract` hoặc abstract method

Thay một class cụ thể thành abstract khiến source consumer không thể khởi tạo trực tiếp class đó. Binary cũ thực hiện `new` trên class nay abstract có thể gặp `InstantiationError`.

Thêm abstract method vào một superclass có thể khiến subclass cụ thể cũ không có implementation. Khi method được gọi trên instance của subclass đó, có thể gặp `AbstractMethodError`. Khi source subclass được biên dịch lại, compiler sẽ yêu cầu implement method hoặc chuyển subclass thành abstract.

### 6.3. Thay đổi visibility và sealed hierarchy

Giảm visibility của class hoặc member có thể làm source consumer mất quyền truy cập và binary có thể gặp `IllegalAccessError`. Tăng visibility thường ít hạn chế hơn nhưng vẫn có thể thay đổi API được nhìn thấy và overload resolution.

Java 17 hỗ trợ sealed classes/interfaces như một tính năng chuẩn. Nếu một type được chuyển sang `sealed` với danh sách `permits`, các subclass/implementation bên ngoài không nằm trong danh sách được phép sẽ không thể biên dịch hoặc xác minh theo hierarchy mới. Thay đổi này cần được đánh giá như thay đổi chính sách mở rộng API.

## 7. Method resolution, `super` và lỗi linkage thường gặp

### 7.1. `NoSuchMethodError`

Lỗi này xảy ra khi bytecode tham chiếu method theo owner/name/descriptor nhưng JVM không tìm thấy method phù hợp khi resolve. Một số nguyên nhân liên quan tới hierarchy:

- Method bị xóa khỏi class và không còn được kế thừa từ superclass/interface.
- Method được di chuyển sang subclass trong khi symbolic reference vẫn trỏ tới superclass.
- Descriptor thay đổi do tham số hoặc return type thay đổi.
- Superclass hoặc interface mới không còn cung cấp method mà consumer đã biên dịch dựa vào.

Ví dụ, binary cũ gọi `BaseTask.execute()`. Nếu phiên bản mới xóa method khỏi `BaseTask` và chỉ khai báo nó ở `CustomTask`, symbolic reference owner `BaseTask` không được resolve bằng cách tìm xuống các subclass. JVM không tìm method trong mọi class con của owner.

### 7.2. `AbstractMethodError`

Lỗi này có thể xảy ra khi một method được resolve nhưng object thực tế không có implementation cụ thể để thực thi. Tình huống điển hình là thêm abstract method vào interface hoặc superclass mà implementation/subclass cũ chưa cung cấp.

### 7.3. `IncompatibleClassChangeError`

Đây là nhóm lỗi linkage khi cấu trúc class/interface hoặc loại member mà bytecode kỳ vọng không còn khớp với runtime. Ví dụ có thể gồm thay class thành interface, interface thành class, hoặc xung đột method/default method trong một số trường hợp resolution.

### 7.4. `VerifyError`

JVM verifier kiểm tra bytecode có tuân thủ type safety và quy tắc class hierarchy hay không. Thay đổi superclass, final/abstract hoặc quan hệ assignability có thể làm bytecode consumer cũ không còn hợp lệ theo hierarchy mới và dẫn đến `VerifyError`.

### 7.5. `ClassCastException`

Nếu class không còn implement interface hoặc kế thừa superclass mà consumer kỳ vọng, một phép `checkcast` có thể thất bại lúc chạy. Code cũ có thể đã biên dịch và class vẫn nạp được, nhưng object runtime không còn là instance của type được cast.

### 7.6. `NoClassDefFoundError`

Nếu superclass hoặc interface bị xóa khỏi artifact runtime, class phụ thuộc có thể không nạp được khi JVM cần resolve hierarchy. Đây là lỗi thiếu class ở runtime, khác với việc class vẫn tồn tại nhưng không còn quan hệ kế thừa như trước.

## 8. Ảnh hưởng tới framework và cơ chế tạo class động

Thay đổi hierarchy có thể ảnh hưởng mạnh tới framework vì nhiều framework quan sát hoặc tạo class dựa trên quan hệ kế thừa.

### 8.1. Proxy và AOP

Một số proxy được tạo bằng cách subclass class mục tiêu. Nếu class chuyển thành `final`, constructor không còn truy cập được hoặc method không thể override, proxy generation có thể thất bại. Framework dùng interface-based proxy có thể ít phụ thuộc vào class hierarchy cụ thể hơn, nhưng contract interface vẫn phải ổn định.

### 8.2. ORM và entity inheritance

ORM có thể dùng superclass cho mapped fields, identifier, lifecycle callback hoặc inheritance mapping. Thay superclass, visibility của constructor hoặc quan hệ entity có thể làm thay đổi mapping và schema behavior.

### 8.3. Mocking và bytecode instrumentation

Mocking library có thể subclass class mục tiêu hoặc instrument bytecode. Thêm `final`, sealed hierarchy hoặc thay đổi method visibility có thể làm mock không tạo được hoặc hành vi test khác production.

### 8.4. Serialization

Với Java serialization, thay đổi superclass và trạng thái được kế thừa có thể ảnh hưởng dữ liệu serialized. `serialVersionUID` mặc định được tính từ một số đặc điểm của class; thay đổi class declaration hoặc hierarchy có thể làm giá trị mặc định thay đổi. Khi class Serializable thay đổi, cần xem xét explicit `serialVersionUID`, `serialPersistentFields`, custom `readObject`/`writeObject` và dữ liệu được lưu từ phiên bản trước.

Không nên giả định giữ nguyên field trong class con là đủ để giữ serialization compatibility nếu superclass hoặc serializable hierarchy đã thay đổi.

## 9. Thiết kế thay đổi hierarchy an toàn hơn

### 9.1. Giữ superclass cũ làm adapter

Nếu cần chuyển implementation sang hierarchy mới, có thể giữ type cũ và delegate sang thành phần mới:

```java
public class LegacyOrder extends BaseEntity {
    private final OrderModel delegate;

    public LegacyOrder(OrderModel delegate) {
        this.delegate = delegate;
    }

    @Override
    public String getId() {
        return delegate.id();
    }
}
```

Adapter chỉ phù hợp khi có thể duy trì semantics và invariants của type cũ. Nếu superclass cũ cung cấp nhiều trạng thái hoặc protected extension points, cần xác định rõ những phần nào được adapter hỗ trợ.

### 9.2. Thêm interface trước, chuyển consumer sau

Một lộ trình thường dùng là:

1. Định nghĩa interface mới thể hiện contract cần công bố.
2. Cho class hiện tại implement interface và phát hành phiên bản tương thích.
3. Chuyển consumer sang phụ thuộc interface thay vì concrete class.
4. Tạo implementation mới theo interface.
5. Giữ implementation/type cũ trong giai đoạn chuyển tiếp.
6. Loại bỏ type cũ ở major release sau khi consumer đã chuyển.

Cách này giảm phụ thuộc vào superclass cụ thể và hỗ trợ thay thế implementation độc lập hơn.

### 9.3. Dùng composition khi không cần kế thừa

Kế thừa tạo quan hệ subtype và chia sẻ contract. Nếu chỉ cần tái sử dụng code, composition thường ít ràng buộc hơn:

```java
public class OrderService {
    private final TaxCalculator taxCalculator;

    public OrderService(TaxCalculator taxCalculator) {
        this.taxCalculator = taxCalculator;
    }

    public Money total(Order order) {
        return taxCalculator.calculate(order);
    }
}
```

Thay implementation của `TaxCalculator` không nhất thiết làm thay đổi hierarchy của `OrderService`. Tuy nhiên, composition cũng có contract riêng; cần quản lý interface/dependency injection như mọi API khác.

### 9.4. Quản lý default method cẩn thận

Khi thêm default method vào interface công khai:

- Kiểm tra các interface cha và interface khác có cùng signature.
- Kiểm tra superclass của implementation có method tương ứng hay không.
- Xác định hành vi mặc định có an toàn cho mọi implementation cũ không.
- Nếu không có hành vi mặc định đúng, cân nhắc interface mới hoặc adapter thay vì thêm method rồi ném `UnsupportedOperationException` một cách bất ngờ.
- Test consumer/plugin đã biên dịch với phiên bản interface cũ.

## 10. Quy trình kiểm tra binary compatibility cho hierarchy

### Bước 1: Lưu baseline API và artifact

Giữ lại JAR cũ, class file, public API report, dependency graph và các consumer đại diện. Ghi nhận class nào là extensible, interface nào là SPI và các subclass/implementation nằm ngoài repository.

### Bước 2: Lập bản đồ hierarchy

Thu thập:

- Direct superclass và superinterface của từng type.
- Subclass và interface implementation trong source nội bộ.
- Class được framework proxy hoặc generate.
- API protected/public được consumer override hoặc gọi qua `super`.
- Default method, bridge method và covariant return.

Với artifact đã biên dịch, `javap -v` có thể hiển thị superclass, interface, method descriptor và bridge flag.

### Bước 3: So sánh hierarchy trước/sau

Ghi nhận class/interface được thêm, xóa, đổi loại, di chuyển package, thay superclass hoặc thay danh sách interface. So sánh method/constructor được khai báo và được kế thừa.

### Bước 4: Build lại source consumer

Compile tất cả module nội bộ và các implementation đại diện. Đặc biệt kiểm tra subclass, SPI provider, plugin và test dùng mock/proxy.

### Bước 5: Chạy binary cũ với thư viện mới

Nếu sản phẩm cần binary compatibility, giữ nguyên consumer đã biên dịch bằng thư viện cũ rồi chạy nó với artifact thư viện mới. Kiểm tra startup, class loading và các call path thực tế; không biên dịch lại consumer trong phép thử này vì làm vậy sẽ che mất lỗi binary.

### Bước 6: Kiểm tra linkage và dispatch

Theo dõi các lỗi:

- `NoSuchMethodError`, `AbstractMethodError`.
- `IncompatibleClassChangeError`, `VerifyError`.
- `IllegalAccessError`, `NoClassDefFoundError`.
- `ClassCastException` ở cast hoặc framework proxy.

Thêm test để xác nhận method implementation được gọi, đặc biệt với default method, `super` call, subclass và interface reference.

### Bước 7: Kiểm tra serialization và framework integration

Nếu hierarchy tham gia serialization, ORM, proxy, AOP hoặc instrumentation, kiểm tra dữ liệu và hành vi được tạo bằng phiên bản cũ. Chạy test trên runtime và dependency version giống môi trường triển khai.

### Bước 8: Công bố migration path

Nếu thay đổi không thể duy trì tương thích, công bố rõ breaking change, type thay thế, ví dụ chuyển đổi, phiên bản loại bỏ và hướng dẫn cho implementor/consumer bên ngoài.

## 11. Công cụ hỗ trợ

### 11.1. `javap`

Xem cấu trúc class file:

```bash
javap -classpath old-library.jar -v com.example.Order
javap -classpath new-library.jar -v com.example.Order
```

Quan sát:

- `super_class` và `interfaces`.
- Method descriptor và generic signature.
- Access flags như `ACC_FINAL`, `ACC_ABSTRACT`, `ACC_BRIDGE`.
- Constructor và method được khai báo.

### 11.2. japicmp và Revapi

Các công cụ như japicmp hoặc Revapi có thể so sánh public API giữa hai phiên bản artifact, phát hiện type/member bị xóa, visibility thay đổi và nhiều dạng binary/source compatibility issue. Cần cấu hình đúng artifact, filter và policy. Tool không thể thay thế test cho reflection, framework-generated class hoặc hành vi runtime.

### 11.3. Dependency và runtime test

Khi kiểm tra consumer, dùng đúng dependency graph mà ứng dụng sẽ resolve ở production. Hai phiên bản của cùng một library trong classpath có thể làm kết quả test khác nhau; classloader riêng của application server/plugin container cũng cần được xét nếu hệ thống sử dụng.

## 12. Bảng tổng hợp thay đổi hierarchy và rủi ro

| Thay đổi | Source consumer | Binary/runtime risk thường gặp |
|---|---|---|
| Đổi superclass sang type không liên quan | Mất subtype, inherited member hoặc protected access | `VerifyError`, `NoSuchMethodError`, `ClassCastException` hoặc thay đổi dispatch |
| Đổi superclass sang subclass của superclass cũ | Có thể vẫn biên dịch nhưng constructor/override thay đổi | Constructor chain, method selection, serialization và behavior thay đổi |
| Bỏ constructor superclass cũ | Subclass không có `super()` hợp lệ sẽ lỗi compile | `NoSuchMethodError` khi gọi constructor descriptor không còn tồn tại |
| Thêm method vào superclass | Có thể tạo override hoặc name conflict | Dispatch/behavior thay đổi; source recompilation có thể chọn method mới |
| Thêm interface abstract method | Implementation có thể phải bổ sung method | `AbstractMethodError` khi gọi method trên implementation cũ |
| Thêm default method | Thường không bắt buộc sửa implementation nhưng có thể xung đột | Dispatch thay đổi hoặc conflict khi resolve |
| Xóa interface khỏi class | Mất khả năng gán/cast sang interface | `ClassCastException`, `IncompatibleClassChangeError` khi invokeinterface |
| Xóa interface type khỏi runtime | Source không resolve type | `NoClassDefFoundError` khi JVM cần nạp type |
| Class đổi thành interface hoặc ngược lại | `extends`/`implements` và khởi tạo không còn hợp lệ | `IncompatibleClassChangeError` |
| Thêm `final` vào class | Subclass không biên dịch | `VerifyError` với subclass binary cũ |
| Thêm `abstract` hoặc abstract method | Không thể khởi tạo hoặc phải implement | `InstantiationError` hoặc `AbstractMethodError` |
| Thay sealed permits list | Subclass ngoài danh sách không được phép | Compile/verification failure với hierarchy không còn hợp lệ |

Các lỗi trong bảng là những rủi ro điển hình, không phải kết quả bắt buộc cho mọi trường hợp. Kết quả cụ thể phụ thuộc class file, symbolic reference, runtime classpath/module path và đường code được thực thi.

## 13. Checklist trước khi phát hành thay đổi hierarchy

- [ ] Đã ghi nhận superclass và superinterface trước/sau thay đổi.
- [ ] Đã kiểm tra quan hệ subtype mà consumer đang dựa vào.
- [ ] Đã tìm subclass, implementation, plugin và SPI provider.
- [ ] Đã kiểm tra constructor chain và constructor descriptor của superclass.
- [ ] Đã rà soát method được kế thừa, override, `super` call và protected access.
- [ ] Đã đánh giá abstract method và default method mới, gồm cả xung đột interface.
- [ ] Đã kiểm tra class/interface kind, `final`, `abstract` và sealed permits.
- [ ] Đã so sánh descriptor, bridge method và class file bằng `javap` hoặc công cụ API compatibility.
- [ ] Đã biên dịch lại source consumer.
- [ ] Đã chạy binary consumer cũ với thư viện mới nếu yêu cầu binary compatibility.
- [ ] Đã kiểm thử dispatch, cast, reflection, proxy, ORM và serialization khi có liên quan.
- [ ] Đã công bố adapter, deprecation hoặc migration guide cho breaking change.

## 14. Kết luận

Superclass, interface và quan hệ kế thừa là một phần của hợp đồng runtime trong Java. Thay đổi chúng có thể làm đổi quan hệ subtype, constructor chain, method resolution, dynamic dispatch, default method selection và khả năng tạo proxy/implementation. Một số thay đổi khiến source không biên dịch; một số khác vẫn cho phép class được nạp nhưng chỉ lỗi khi một method, cast hoặc đường code cụ thể được sử dụng.

Khi migration thư viện hoặc JDK, hãy so sánh hierarchy và descriptor của artifact trước/sau, biên dịch lại consumer, chạy binary cũ nếu cần hỗ trợ binary compatibility và kiểm thử hành vi của framework phụ thuộc kế thừa. Nếu phải thay đổi contract, dùng interface/adapter hoặc một lộ trình major release rõ ràng để consumer có thể chuyển đổi có kiểm soát.
