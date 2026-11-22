# Phương thức mới trong interface và xung đột với lớp đang triển khai

Interface là một phần quan trọng của hợp đồng API Java. Một thư viện có thể công bố interface để các ứng dụng khác triển khai; theo thời gian, thư viện cần bổ sung hành vi mới. Tuy nhiên, thêm một phương thức vào interface có thể ảnh hưởng đến các lớp đã triển khai interface đó, kể cả những lớp nằm trong dự án khác mà nhóm phát triển không kiểm soát.

Từ Java 8, interface có thể khai báo `default` method với phần thân mặc định. Nhờ vậy, thư viện có thể bổ sung một số hành vi mà không bắt buộc mọi lớp triển khai phải viết lại ngay. Cơ chế này giúp tiến hóa API, nhưng vẫn có thể tạo xung đột với phương thức sẵn có trong lớp, phương thức kế thừa từ superclass hoặc default method từ interface khác.

Để đánh giá thay đổi interface một cách an toàn, cần phân biệt phương thức abstract, default, static và private; hiểu quy tắc chọn phương thức khi có nhiều nguồn kế thừa; đồng thời kiểm tra cả source compatibility, binary compatibility và thay đổi hành vi lúc chạy.

## 1. Thêm phương thức vào interface có thể ảnh hưởng thế nào?

Giả sử thư viện ban đầu công bố:

```java
public interface PaymentGateway {
    Payment charge(Order order);
}
```

Một ứng dụng triển khai interface:

```java
public class BankPaymentGateway implements PaymentGateway {
    @Override
    public Payment charge(Order order) {
        // Gửi yêu cầu thanh toán tới ngân hàng.
        return Payment.approved(order);
    }
}
```

Sau một thời gian, thư viện muốn thêm khả năng hoàn tiền. Nếu chỉ thêm một phương thức abstract:

```java
public interface PaymentGateway {
    Payment charge(Order order);
    Payment refund(Payment payment);
}
```

`BankPaymentGateway` chưa có `refund`. Khi biên dịch lại mã nguồn, lớp cụ thể không còn đáp ứng đầy đủ hợp đồng interface và compiler báo lỗi nếu lớp không được khai báo `abstract` hoặc không triển khai phương thức mới.

Nếu thư viện thêm phương thức có thân mặc định:

```java
public interface PaymentGateway {
    Payment charge(Order order);

    default Payment refund(Payment payment) {
        throw new UnsupportedOperationException("Refund is not supported");
    }
}
```

Lớp triển khai cũ có thể tiếp tục biên dịch mà không phải bổ sung phương thức ngay. Khi không có phương thức phù hợp trong lớp hoặc interface cụ thể hơn, lời gọi `refund` sẽ dùng phần thân mặc định.

Tuy nhiên, ví dụ trên cũng cho thấy một vấn đề thiết kế: một lời gọi hoàn tiền có thể thất bại khi implementation không hỗ trợ. Default method chỉ cung cấp hành vi dự phòng; nó không thể tự tạo ra khả năng nghiệp vụ mà lớp triển khai không có.

## 2. Các loại phương thức trong interface

### 2.1. Abstract method

Abstract method chỉ khai báo chữ ký, không có thân phương thức:

```java
public interface Repository<T> {
    T findById(long id);
}
```

Lớp cụ thể triển khai interface phải cung cấp phần thân phù hợp, trừ khi phương thức được kế thừa từ superclass hoặc một implementation khác đáp ứng hợp đồng.

Thêm abstract method vào interface công khai làm tăng nghĩa vụ của các implementation khi biên dịch lại. Đây là thay đổi source-incompatible đối với các lớp cụ thể chưa triển khai phương thức mới.

### 2.2. Default method

Default method có từ Java 8. Nó khai báo bằng từ khóa `default` và phải có thân phương thức:

```java
public interface Identifiable {
    String id();

    default boolean hasId() {
        return id() != null && !id().isBlank();
    }
}
```

Lớp triển khai chỉ cần cung cấp `id()`. Nếu không override `hasId()`, lớp kế thừa hành vi mặc định. Default method có thể gọi abstract method của interface, nhờ đó hành vi chung dựa trên dữ liệu mà implementation cung cấp.

Default method thường được dùng để bổ sung tiện ích có thể suy ra từ hợp đồng hiện có. Nếu hành vi mới cần trạng thái riêng, truy cập database, giao tiếp mạng hoặc một quyết định nghiệp vụ mà interface không thể biết, hãy cân nhắc một API khác thay vì đặt một default method giả định.

### 2.3. Static method

Interface có thể khai báo static method từ Java 8:

```java
public interface Identifiers {
    static boolean isValid(String value) {
        return value != null && !value.isBlank();
    }
}
```

Static method được gọi qua tên interface:

```java
boolean valid = Identifiers.isValid("ORD-100");
```

Static method của interface không được kế thừa như instance method bởi lớp triển khai hoặc subinterface. Vì thế, thêm static method thường không tạo nghĩa vụ triển khai mới cho các lớp hiện có.

### 2.4. Private method

Từ Java 9, interface có thể có private instance method và private static method để chia sẻ logic giữa các default/static method:

```java
public interface AuditView {
    default String summary(String actor) {
        return normalize(actor) + " performed an action";
    }

    private String normalize(String actor) {
        return actor == null ? "unknown" : actor.trim();
    }
}
```

Private method chỉ dùng bên trong interface. Lớp triển khai không kế thừa và không thể override method này. Nó là chi tiết triển khai của interface, không phải một phương thức mới mà implementation phải cung cấp.

## 3. Source compatibility và binary compatibility

Khi tiến hóa interface công khai, cần phân biệt hai khái niệm:

- **Source compatibility:** mã nguồn cũ có biên dịch lại được với phiên bản interface mới hay không.
- **Binary compatibility:** class file đã biên dịch trước đó có tiếp tục liên kết và chạy với phiên bản interface mới hay không, trong các đường sử dụng đã tồn tại.

Hai khái niệm này không đồng nhất. Một class file có thể vẫn được JVM nạp, nhưng một lời gọi phương thức mới chưa có implementation có thể thất bại khi thực thi.

| Thay đổi interface | Khi biên dịch lại implementation cũ | Với class file đã biên dịch trước đó |
|---|---|---|
| Thêm abstract instance method | Lớp cụ thể thường phải triển khai thêm; nếu không sẽ lỗi compile. | Class file cũ có thể vẫn được nạp, nhưng lời gọi phương thức mới có thể ném `AbstractMethodError`. |
| Thêm default instance method | Thường vẫn biên dịch nếu không có xung đột chữ ký/kế thừa. | Thường tương thích nhị phân; có ngoại lệ khi xuất hiện xung đột default method. |
| Thêm static method | Không tạo nghĩa vụ triển khai cho lớp. | Không thay đổi tập instance method mà lớp phải cung cấp. |
| Thêm private method | Không tạo nghĩa vụ triển khai cho lớp. | Là chi tiết nội bộ của interface; không phải method được kế thừa. |

Vì vậy, default method là một công cụ quan trọng để tiến hóa interface, nhưng không phải bảo đảm tuyệt đối rằng mọi thay đổi đều tương thích. Phải xét các interface khác mà lớp triển khai, các superclass hiện có và chữ ký method trong toàn bộ hệ thống.

## 4. Quy tắc phân giải khi lớp có nhiều phương thức cùng chữ ký

Java có quy tắc xác định implementation được dùng khi một lớp nhận cùng một method signature từ nhiều nơi. Những quy tắc quan trọng nhất là:

1. Phương thức instance phù hợp được khai báo hoặc kế thừa từ class hierarchy được ưu tiên hơn default method của interface.
2. Trong các interface có quan hệ kế thừa, default method từ interface cụ thể hơn sẽ thắng method từ interface cha.
3. Nếu hai interface độc lập cùng cung cấp default method xung đột, lớp cụ thể phải override để giải quyết.
4. Nếu subinterface khai báo lại method dưới dạng abstract, nó có thể hủy default method được kế thừa; lớp cụ thể triển khai subinterface phải cung cấp implementation.

Các quy tắc này thường được tóm tắt bằng nguyên tắc: class thắng interface; interface cụ thể hơn thắng interface cha; hai default từ các interface độc lập cần được giải quyết rõ ràng.

## 5. Phương thức của class thắng default method

Giả sử interface cung cấp default method:

```java
public interface Printable {
    default String format() {
        return "formatted by Printable";
    }
}
```

Một superclass đã có phương thức cùng chữ ký:

```java
public class BaseDocument {
    public String format() {
        return "formatted by BaseDocument";
    }
}
```

Lớp con vừa kế thừa superclass vừa triển khai interface:

```java
public class Invoice extends BaseDocument implements Printable {
}
```

Khi gọi:

```java
Invoice invoice = new Invoice();
System.out.println(invoice.format());
```

kết quả là:

```text
formatted by BaseDocument
```

Phương thức kế thừa từ `BaseDocument` được ưu tiên. Default method của `Printable` không thay thế implementation từ class hierarchy.

### 5.1. Superclass có phương thức abstract

Quy tắc class thắng interface cũng cần chú ý khi superclass khai báo method abstract:

```java
public abstract class BaseTask {
    public abstract void execute();
}

public interface Executable {
    default void execute() {
        System.out.println("Default execution");
    }
}

public abstract class ScheduledTask extends BaseTask
        implements Executable {
}
```

`ScheduledTask` vẫn phải là abstract vì phương thức abstract được kế thừa từ `BaseTask` chi phối. Default method của interface không tự lấp vào vị trí abstract method của superclass. Một lớp con cụ thể phải triển khai `execute()`:

```java
public class DailyTask extends ScheduledTask {
    @Override
    public void execute() {
        System.out.println("Run daily task");
    }
}
```

### 5.2. Access modifier của phương thức hiện có

Method dùng để triển khai instance method của interface phải đáp ứng mức truy cập public. Nếu superclass có method cùng chữ ký nhưng chỉ là `protected` hoặc package-private, lớp con không thể dùng method đó để đáp ứng hợp đồng public của interface. Khi biên dịch lại, compiler có thể báo lỗi về quyền truy cập yếu hơn.

Tương tự, static method trong class không thể thay thế instance method mà interface yêu cầu. Khi thêm default method vào interface cũ, hãy kiểm tra cả method cùng tên và cùng tham số trong superclass, không chỉ các method được viết trực tiếp trong lớp triển khai.

## 6. Default method từ interface cụ thể hơn

Nếu một interface mở rộng interface khác và override default method, implementation từ interface con sẽ được ưu tiên:

```java
public interface Logger {
    default void log(String message) {
        System.out.println("LOG: " + message);
    }
}

public interface StructuredLogger extends Logger {
    @Override
    default void log(String message) {
        System.out.println("[structured] " + message);
    }
}

public class FileLogger implements Logger, StructuredLogger {
}
```

`StructuredLogger` là subinterface của `Logger`, nên default method của nó cụ thể hơn. `FileLogger` sử dụng implementation từ `StructuredLogger`:

```java
new FileLogger().log("Application started");
```

Kết quả:

```text
[structured] Application started
```

Không cần override trong `FileLogger` vì chỉ có một default method cụ thể nhất được kế thừa.

## 7. Xung đột giữa hai default method độc lập

Xung đột phổ biến nhất xảy ra khi một lớp triển khai hai interface độc lập, cả hai đều cung cấp default method cùng chữ ký:

```java
public interface JsonExporter {
    default String export() {
        return "JSON";
    }
}

public interface XmlExporter {
    default String export() {
        return "XML";
    }
}

public class ReportExporter implements JsonExporter, XmlExporter {
}
```

Lớp `ReportExporter` không thể tự động chọn một implementation. Khi biên dịch, Java báo lỗi vì hai default method cùng có thể được kế thừa và không interface nào cụ thể hơn interface còn lại.

### 7.1. Override để tự định nghĩa hành vi

Giải pháp rõ ràng nhất là override method trong lớp:

```java
public class ReportExporter implements JsonExporter, XmlExporter {
    @Override
    public String export() {
        return "CUSTOM REPORT";
    }
}
```

Implementation của lớp có độ ưu tiên cao hơn default method từ interface.

### 7.2. Chọn một default method bằng `InterfaceName.super`

Nếu muốn tái sử dụng một hoặc nhiều phần thân mặc định, có thể gọi trực tiếp:

```java
public class JsonReportExporter implements JsonExporter, XmlExporter {
    @Override
    public String export() {
        return JsonExporter.super.export();
    }
}
```

Hoặc kết hợp cả hai hành vi:

```java
public class CombinedReportExporter implements JsonExporter, XmlExporter {
    @Override
    public String export() {
        return JsonExporter.super.export()
                + " + " + XmlExporter.super.export();
    }
}
```

`InterfaceName.super.method()` là cú pháp gọi default method từ một direct superinterface phù hợp. Nó không phải cú pháp gọi static method và không thể dùng để gọi tùy ý một interface không phải superinterface trực tiếp.

## 8. Subinterface có thể hủy default method

Một subinterface có thể khai báo lại method của interface cha dưới dạng abstract:

```java
public interface DefaultCloseable {
    default void closeResource() {
        System.out.println("Default close");
    }
}

public interface ManagedResource extends DefaultCloseable {
    @Override
    void closeResource();
}
```

`ManagedResource` không cung cấp phần thân mặc định. Nó yêu cầu implementation cụ thể phải tự định nghĩa `closeResource()`:

```java
public class DatabaseResource implements ManagedResource {
    @Override
    public void closeResource() {
        System.out.println("Close database connection");
    }
}
```

Nếu lớp cụ thể không triển khai method này, compiler báo lỗi. Kỹ thuật này hữu ích khi một interface con muốn siết chặt hợp đồng mà interface cha đã cung cấp default behavior quá rộng.

## 9. Xung đột chữ ký method với lớp triển khai cũ

Khi thêm method vào interface công khai, rủi ro không chỉ đến từ default method khác. Một lớp cũ có thể đã khai báo method trùng tên và tham số vì mục đích riêng.

### 9.1. Method sẵn có vô tình trở thành implementation

Giả sử một lớp đã có:

```java
public class LegacyCache {
    public boolean isEmpty() {
        return size() == 0;
    }

    public int size() {
        return 0;
    }
}
```

Sau này interface được bổ sung:

```java
public interface CacheView {
    default boolean isEmpty() {
        return size() == 0;
    }

    int size();
}
```

Lớp triển khai cả hai:

```java
public class LegacyCache implements CacheView {
    public boolean isEmpty() {
        return size() == 0;
    }

    public int size() {
        return 0;
    }
}
```

Method public `isEmpty()` đã có trong class được chọn thay cho default method. Trường hợp này thường biên dịch được và không cần sửa lớp, nhưng hành vi của lời gọi qua interface sẽ theo method của class.

Điều này có thể gây bất ngờ nếu method cũ cùng chữ ký nhưng có ý nghĩa khác với method mới mà thư viện muốn cung cấp. Vì vậy, khi chọn tên default method mới, tác giả API cần cân nhắc các tên phổ biến mà implementation bên ngoài có thể đã sử dụng.

### 9.2. Trùng tên nhưng khác tham số là overload

Hai method chỉ cùng tên chưa chắc xung đột. Ví dụ:

```java
public interface MessageSource {
    default String getMessage(String key) {
        return key;
    }
}

public class CustomMessageSource implements MessageSource {
    public String getMessage(String key, String locale) {
        return key + "@" + locale;
    }
}
```

`getMessage(String)` và `getMessage(String, String)` có danh sách tham số khác nhau nên là hai overload. Method trong lớp không override default method.

Trong Java, method signature được xác định chủ yếu bởi tên và kiểu tham số sau khi áp dụng quy tắc generic/erasure; kiểu trả về không được dùng để phân biệt overload. Khi có method cùng signature, kiểu trả về phải tương thích theo quy tắc override và return-type-substitutability.

### 9.3. Khác kiểu trả về

Giả sử interface mới thêm:

```java
public interface Versioned {
    default Number version() {
        return 1;
    }
}
```

Một lớp cũ có thể đã có method `public String version()`. Khi lớp đó triển khai interface, hai method có cùng tên và không có tham số nhưng kiểu trả về không tương thích. Java không cho phép dùng return type để tạo hai method overload cùng chữ ký; việc biên dịch có thể thất bại.

Nếu return type của method trong lớp là kiểu con hợp lệ của return type trong interface, đó có thể là covariant return và method của lớp có thể override method interface. Ví dụ `Integer` là kiểu con của `Number`.

### 9.4. Generic erasure và name clash

Generic type được xóa về erasure khi tạo bytecode. Hai chữ ký trông khác nhau trong mã nguồn có thể trở thành cùng chữ ký sau erasure, gây name clash hoặc lỗi override.

Ví dụ, hai interface độc lập khai báo:

```java
import java.util.List;

public interface StringBatch {
    default void process(List<String> values) {
    }
}

public interface IntegerBatch {
    default void process(List<Integer> values) {
    }
}
```

Sau type erasure, cả hai đều có dạng `process(List)`. Một lớp triển khai cả hai có thể gặp name clash hoặc xung đột kế thừa. Không thể giải quyết bằng cách chỉ viết hai method khác nhau theo generic argument vì ở bytecode, kiểu tham số đã bị xóa.

Khi thiết kế interface có generic method, hãy kiểm tra cả erasure và các interface mà implementation có thể kết hợp.

## 10. Xung đột với checked exception

Method override phải tuân theo quy tắc checked exception của method được override. Nếu interface mới thêm default method không khai báo checked exception nhưng class đã có method cùng signature khai báo một checked exception rộng hơn, source recompilation có thể thất bại.

Ví dụ:

```java
import java.io.IOException;

public interface ResourceView {
    default String describe() {
        return "resource";
    }
}

public class LegacyResource implements ResourceView {
    public String describe() throws IOException {
        return "legacy resource";
    }
}
```

Method của lớp không thể override method interface bằng cách bổ sung checked exception `IOException` mà interface không cho phép. Cần đổi chữ ký, đổi tên method mới hoặc thiết kế API sao cho không tạo xung đột với implementation cũ.

Unchecked exception như `RuntimeException` không bị ràng buộc theo quy tắc checked exception này, nhưng vẫn cần tài liệu hóa hành vi để tránh thay đổi hợp đồng bất ngờ.

## 11. Xung đột khi thêm default vào hai interface đã được triển khai chung

Một trường hợp quan trọng trong binary compatibility xuất hiện khi một class đã triển khai hai interface độc lập, và sau đó cả hai interface được nâng cấp để thêm default method cùng signature.

Giả sử phiên bản cũ:

```java
public interface Readable {
    String read();
}

public interface Writable {
    void write(String value);
}

public class LegacyDevice implements Readable, Writable {
    @Override
    public String read() {
        return "data";
    }

    @Override
    public void write(String value) {
    }
}
```

Ở phiên bản sau, cả hai interface cùng được thêm:

```java
public interface Readable {
    String read();

    default void reset() {
        System.out.println("Reset reader");
    }
}

public interface Writable {
    void write(String value);

    default void reset() {
        System.out.println("Reset writer");
    }
}
```

Class file `LegacyDevice` đã biên dịch trước đó có thể vẫn được JVM nạp với các interface mới, nhưng nếu gọi `reset()` mà không có implementation cụ thể trong class, JVM có thể phát hiện hai maximally-specific default method và ném `IncompatibleClassChangeError`. Khi biên dịch lại source, compiler báo xung đột và yêu cầu lớp override `reset()`.

Đây là lý do việc thêm default method thường binary-compatible nhưng vẫn có ngoại lệ quan trọng. Trước khi phát hành interface mới, hãy xem xét các tổ hợp interface mà implementation có thể cùng triển khai, đặc biệt với các thư viện API công khai.

## 12. Thứ tự ưu tiên khi giải quyết method

Bảng sau tóm tắt cách Java xử lý các tình huống thường gặp:

| Tình huống | Kết quả |
|---|---|
| Class có public instance method cùng signature với default method | Method của class được dùng. |
| Superclass có concrete instance method cùng signature | Method kế thừa từ superclass thắng default method. |
| Superclass có abstract method cùng signature | Lớp con cụ thể vẫn phải triển khai abstract method. |
| Subinterface override default method của interface cha | Default method của subinterface cụ thể hơn được kế thừa. |
| Hai interface độc lập có default method cùng signature | Lớp phải override để chọn hoặc kết hợp hành vi. |
| Subinterface redeclare method dưới dạng abstract | Default method cha bị hủy trong hợp đồng của subinterface; class cụ thể phải triển khai. |
| Method trùng tên nhưng khác danh sách tham số | Thường là overload, không phải override. |
| Method cùng signature nhưng return type không tương thích | Lỗi compile hoặc xung đột kiểu; return type không tạo overload riêng. |

## 13. Cách xử lý xung đột khi nâng cấp thư viện

Khi thư viện thêm method vào interface, nên thực hiện các bước sau:

1. **Kiểm kê implementation.** Tìm tất cả lớp trong repository triển khai interface và xác định các implementation bên ngoài nếu có.
2. **Tìm chữ ký trùng.** Kiểm tra class hierarchy, method cùng tên/tham số, return type, checked exception, generic erasure và modifier.
3. **Xác định loại method mới.** Chọn abstract, default, static hoặc private theo hợp đồng thực sự cần công bố.
4. **Đánh giá hành vi mặc định.** Default method phải có kết quả hợp lý cho implementation cũ. Tránh trả về giá trị giả hoặc thực hiện side effect mà implementation không mong đợi.
5. **Kiểm tra các interface kết hợp.** Một implementation có thể triển khai nhiều interface từ các thư viện khác nhau; hãy tìm khả năng hai default method trùng signature.
6. **Biên dịch lại client.** Build các module và dự án phụ thuộc với phiên bản interface mới để phát hiện source conflict.
7. **Kiểm thử binary compatibility.** Dùng class file cũ với interface mới trong một test runtime riêng, đặc biệt nếu thư viện cam kết không yêu cầu client biên dịch lại.
8. **Kiểm thử hành vi.** Xác nhận lời gọi qua interface reference, class reference và superclass reference đều đi tới implementation đúng.
9. **Công bố migration note.** Nêu rõ method mới, default behavior, xung đột có thể gặp và cách override.

Không nên chỉ kiểm tra repository của chính thư viện. Một interface public có thể được triển khai bởi plugin, ứng dụng khách hàng hoặc module không nằm trong quyền kiểm soát của tác giả thư viện.

## 14. Thiết kế interface để dễ tiến hóa

### 14.1. Ưu tiên default method có thể suy ra từ hợp đồng hiện tại

Một default method tốt thường dùng các method đã tồn tại để tạo tiện ích mới:

```java
public interface CollectionView<E> {
    int size();
    E get(int index);

    default boolean isEmpty() {
        return size() == 0;
    }
}
```

`isEmpty()` có thể được tính từ `size()`, không cần trạng thái mới. Đây là kiểu mở rộng tương đối an toàn.

### 14.2. Tránh tên method quá chung chung

Các tên như `close`, `reset`, `size`, `name`, `value`, `get`, `process` có khả năng đã xuất hiện trong class của người dùng. Khi thêm default method, hãy xem xét mức độ phổ biến của tên và khả năng xung đột.

Tên method phản ánh rõ vai trò domain thường giảm nguy cơ trùng và làm API dễ đọc hơn. Tuy nhiên, tên dài không tự bảo đảm an toàn; vẫn cần kiểm tra chữ ký và kiểu trả về.

### 14.3. Không dùng default method để giả lập capability không có thật

Một default method kiểu:

```java
default void deleteAll() {
    throw new UnsupportedOperationException();
}
```

có thể giúp giữ source compatibility, nhưng caller có thể hiểu nhầm rằng mọi implementation đều hỗ trợ xóa. Nếu capability là tùy chọn, hãy biểu diễn rõ bằng interface riêng, capability query hoặc API trả về kết quả thể hiện khả năng hỗ trợ.

### 14.4. Giữ ổn định ngữ nghĩa

Một default method có thể được override, nhưng người dùng thường dựa vào hành vi được tài liệu hóa. Tránh thay đổi hành vi mặc định giữa các bản phát hành nếu không có lý do rõ ràng. Nếu default method gọi abstract method khác, hãy xác định rõ yêu cầu đối với kết quả trả về, exception và side effect của method đó.

## 15. Kiểm thử tiến hóa interface

Một bộ kiểm thử tốt nên bao gồm các trường hợp:

| Trường hợp | Mục tiêu |
|---|---|
| Implementation cũ không override default method | Xác nhận default behavior hoạt động. |
| Implementation có method cùng signature | Xác nhận class method được chọn và ngữ nghĩa không bị thay đổi ngoài dự kiến. |
| Superclass có method cùng signature | Xác nhận class hierarchy được ưu tiên. |
| Hai interface có default method xung đột | Xác nhận compiler yêu cầu override và lớp xử lý đúng. |
| Subinterface cung cấp default cụ thể hơn | Xác nhận method cụ thể nhất được dùng. |
| Subinterface redeclare abstract | Xác nhận implementation cụ thể phải cung cấp method. |
| Return type, checked exception hoặc generic erasure không tương thích | Xác nhận lỗi được phát hiện ở compile time. |
| Binary cũ với interface mới | Phát hiện `AbstractMethodError` hoặc `IncompatibleClassChangeError` trong trường hợp có thể xảy ra. |

### 15.1. Test implementation kế thừa default

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;

class IdentifiableTest {
    @Test
    void usesDefaultHasIdImplementation() {
        Identifiable value = () -> "ID-100";

        assertEquals(true, value.hasId());
    }
}
```

Ví dụ dùng lambda vì `Identifiable` có một abstract method. Default method không làm interface mất tính functional.

### 15.2. Test class override default

```java
interface Greeting {
    default String message() {
        return "hello";
    }
}

class VietnameseGreeting implements Greeting {
    @Override
    public String message() {
        return "xin chao";
    }
}
```

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;

class GreetingTest {
    @Test
    void classImplementationWins() {
        Greeting greeting = new VietnameseGreeting();
        assertEquals("xin chao", greeting.message());
    }
}
```

### 15.3. Test conflict ở compile time

Một xung đột giữa hai default method là lỗi biên dịch. Có thể giữ một fixture source riêng để xác nhận API mới thực sự yêu cầu client giải quyết xung đột:

```java
interface A {
    default void run() {
    }
}

interface B {
    default void run() {
    }
}

class Conflict implements A, B {
    // javac báo lỗi: phải override run().
}
```

Sau đó thêm implementation rõ ràng:

```java
class Resolved implements A, B {
    @Override
    public void run() {
        A.super.run();
    }
}
```

## 16. Tóm tắt quyết định khi thêm method

| Nhu cầu | Hướng thiết kế thường phù hợp |
|---|---|
| Bắt buộc mọi implementation cung cấp hành vi mới | Thêm abstract method trong một thay đổi có kế hoạch migration rõ ràng. |
| Có thể cung cấp hành vi chung từ API hiện tại | Thêm default method có ngữ nghĩa an toàn. |
| Hàm tiện ích không cần instance | Thêm static method và gọi qua tên interface. |
| Logic dùng chung nội bộ giữa các method trong interface | Dùng private method từ Java 9. |
| Capability chỉ một số implementation có | Cân nhắc interface capability riêng hoặc API biểu diễn khả năng hỗ trợ. |
| Cần thay đổi hợp đồng không tương thích | Tạo interface/version mới hoặc tổ chức migration theo major release. |

## 17. Checklist trước khi phát hành interface mới

- [ ] Đã xác định interface nào được công bố cho client bên ngoài.
- [ ] Đã kiểm kê các class triển khai interface và superclass liên quan.
- [ ] Đã tìm method trùng tên và tham số trong class hierarchy.
- [ ] Đã kiểm tra return type, checked exception và generic erasure.
- [ ] Đã kiểm tra các interface độc lập mà implementation có thể cùng triển khai.
- [ ] Đã chọn đúng loại abstract/default/static/private method.
- [ ] Default behavior có ý nghĩa rõ ràng và không giả định capability không tồn tại.
- [ ] Đã biên dịch lại các client đại diện với interface mới.
- [ ] Đã kiểm thử binary cũ với thư viện mới nếu cần duy trì binary compatibility.
- [ ] Đã kiểm thử đường gọi qua interface reference và class reference.
- [ ] Đã ghi rõ hành vi mới và hướng xử lý xung đột trong release note.

## Tài liệu tham khảo

- [JLS 9 — Interfaces](https://docs.oracle.com/javase/specs/jls/se21/html/jls-9.html): quy tắc khai báo, kế thừa và default method của interface.
- [JLS 8.4.8 — Inheritance, Overriding, and Hiding](https://docs.oracle.com/javase/specs/jls/se21/html/jls-8.html#jls-8.4.8): quy tắc override và kế thừa method trong class.
- [JLS 13 — Binary Compatibility](https://docs.oracle.com/javase/specs/jls/se21/html/jls-13.html): tác động tương thích nhị phân của thay đổi API.
- [JLS 15.12 — Method Invocation Expressions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.12): quy tắc chọn method khi gọi.
- [JEP 126 — Lambda Expressions & Virtual Extension Methods](https://openjdk.org/jeps/126): bối cảnh bổ sung virtual extension/default methods trong Java 8.
- [Java 8 Default Methods Tutorial](https://docs.oracle.com/javase/tutorial/java/IandI/defaultmethods.html): ví dụ default method và xung đột kế thừa.

## Kết luận

Thêm phương thức vào interface là một thay đổi hợp đồng cần xem xét cả lớp triển khai cũ và các interface khác trong hệ thống. Abstract method tạo nghĩa vụ triển khai mới; default method giúp mở rộng API với hành vi sẵn có nhưng có thể xung đột với class method hoặc default method khác; static và private method không tạo nghĩa vụ instance cho lớp triển khai. Nắm vững thứ tự ưu tiên class/interface, xử lý rõ xung đột bằng override và `InterfaceName.super`, đồng thời kiểm thử cả source lẫn binary compatibility sẽ giúp API Java tiến hóa an toàn hơn.
