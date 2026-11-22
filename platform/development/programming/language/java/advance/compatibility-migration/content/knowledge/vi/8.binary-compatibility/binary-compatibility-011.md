# Thêm final, sealed hoặc thay đổi khả năng kế thừa

Trong nhóm **Tương thích nhị phân** của chủ đề **Java Advance Compatibility Migration**, thay đổi khả năng kế thừa là một trong những loại thay đổi API dễ bị đánh giá sai. Một lớp vẫn giữ nguyên tên, constructor và phương thức công khai, nhưng chỉ cần thêm **final** hoặc **sealed** cũng có thể khiến plugin hoặc lớp con đã biên dịch từ trước không còn nạp được khi thay JAR thư viện.

Vấn đề thường xuất hiện khi các thành phần có vòng đời phát hành độc lập: framework cung cấp lớp nền, tổ chức phát hành SDK, đối tác viết subclass, hoặc một module tạo proxy bằng công cụ runtime. Khi nâng thư viện, nhóm có thể biên dịch lại thư viện thành công và chạy unit test nội bộ, nhưng bytecode của consumer cũ vẫn đang chứa quan hệ **extends**, **implements** hoặc **override** đã bị phiên bản mới cấm.

Bài này phân tích chính xác tác động của **final**, **sealed**, **non-sealed**, tập **permits**, các thay đổi liên quan đến class/interface và phương pháp migration để giữ consumer cũ hoạt động.

## 1. Tương thích nhị phân và hợp đồng kế thừa

Tương thích nhị phân (binary compatibility) trả lời câu hỏi: chương trình đã biên dịch với phiên bản API cũ có thể tiếp tục liên kết và chạy với phiên bản API mới mà **không biên dịch lại chương trình đó** hay không?

Với một thư viện hỗ trợ kế thừa, hợp đồng không chỉ gồm các phương thức để gọi. Nó còn bao gồm:

- Lớp có được phép làm superclass không.
- Interface có cho phép class hoặc subinterface mới triển khai/mở rộng không.
- Phương thức instance có được override không.
- Constructor nào có thể được lớp con gọi qua **super(...)**.
- Lớp con có thể kế thừa thành viên nào và với quyền truy cập gì.
- Kiểu có bị giới hạn bởi **sealed** và **permits** hay không.
- Consumer hiện hữu có được xây dựng và triển khai độc lập với thư viện không.

Ví dụ, API phiên bản 1 cung cấp:

~~~java
package example.api;

public class BaseHandler {
    public String handle(String input) {
        return input;
    }
}
~~~

Một plugin bên ngoài đã biên dịch:

~~~java
package example.plugin;

import example.api.BaseHandler;

public class CustomHandler extends BaseHandler {
    @Override
    public String handle(String input) {
        return "custom:" + input;
    }
}
~~~

Bytecode của **CustomHandler** ghi nhận superclass là **example.api.BaseHandler** và có một phương thức override tương ứng. Nếu phiên bản 2 biến **BaseHandler** thành **final**, việc giữ nguyên chữ ký **handle(String)** không thể cứu quan hệ kế thừa đã bị cấm.

### 1.1. Ba khía cạnh cần kiểm tra riêng

| Khía cạnh | Câu hỏi | Cách xác minh |
|---|---|---|
| Source compatibility | Source subclass cũ có biên dịch được với thư viện mới không? | Biên dịch source consumer trên API mới |
| Binary compatibility | Class file subclass cũ có nạp và chạy cùng thư viện mới không? | Giữ nguyên bytecode consumer và thay đúng JAR thư viện |
| Behavioral compatibility | Override, dispatch động và hợp đồng mở rộng có còn hoạt động đúng không? | Test thực tế trên các subclass và plugin đại diện |

Một thay đổi có thể làm source không biên dịch được nhưng bytecode cũ vẫn liên kết được; trường hợp khác có thể gây lỗi runtime dù chỉ sửa một modifier. Vì vậy, không dùng kết quả build lại toàn bộ source để kết luận binary compatibility.

## 2. Các modifier quyết định khả năng kế thừa

Java có một số cơ chế kiểm soát quan hệ kế thừa. Chúng có ý nghĩa khác nhau và tạo ràng buộc khác nhau cho consumer.

| Khai báo | Khả năng kế thừa hoặc triển khai | Ý nghĩa khi nâng cấp |
|---|---|---|
| Class thường, không final/sealed | Có thể được subclass nếu constructor và quyền truy cập cho phép | Khả năng mở rộng là một phần hành vi API thực tế |
| **final class** | Không thể có subclass | Thêm final có thể làm hỏng subclass cũ |
| **sealed class** | Chỉ cho phép direct subclass có trong tập permitted | Thêm sealed có thể làm hỏng subclass cũ không được phép |
| **non-sealed class** | Mở lại khả năng có subclass, khi chính class đó là direct child của sealed type | Có thể tạo một điểm mở rộng nằm dưới sealed hierarchy |
| **sealed interface** | Chỉ cho phép class hoặc subinterface trực tiếp có trong tập permitted | Thêm sealed có thể làm hỏng implementation hoặc subinterface cũ |
| **non-sealed interface** | Mở lại khả năng được triển khai/mở rộng dưới sealed interface | Hữu ích để giữ một nhánh extension mở |
| **final instance method** | Không được override | Thêm final có thể làm hỏng class file subclass đã override |
| **final static method** | Không có overriding động; static method được xử lý bằng method hiding | Tác động binary khác với final instance method |

**final**, **sealed** và **non-sealed** là cơ chế ở các cấp khác nhau. Không thể dùng **final** cho interface. **non-sealed** cũng không phải modifier có thể thêm tùy ý vào mọi class/interface; nó chỉ hợp lệ khi kiểu có direct sealed supertype phù hợp.

**Sealed classes và interfaces** trở thành tính năng chính thức từ Java 17. Nếu hệ thống vẫn phải chạy trên JDK cũ không hỗ trợ class file của release này, việc thêm sealed có thể kéo theo thay đổi yêu cầu runtime, ngoài vấn đề tương thích của consumer.

## 3. Thêm final vào một class đang có subclass

### 3.1. Thay đổi nhìn từ source

Phiên bản 1:

~~~java
package example.api;

public class Engine {
    public String run() {
        return "running";
    }
}
~~~

Plugin đã phát hành:

~~~java
package example.plugin;

import example.api.Engine;

public class FastEngine extends Engine {
    @Override
    public String run() {
        return "fast";
    }
}
~~~

Phiên bản 2 chỉ sửa modifier:

~~~java
package example.api;

public final class Engine {
    public String run() {
        return "running";
    }
}
~~~

Nếu biên dịch lại **FastEngine** với phiên bản 2, **javac** báo lỗi vì không thể kế thừa class final. Nhưng tình huống migration quan trọng hơn là **FastEngine.class** đã được biên dịch trước đó và không được build lại.

Theo Java Language Specification, khi JVM nạp class file của subclass cũ với superclass mới đã chuyển thành final, JVM ném **IncompatibleClassChangeError** vì quan hệ kế thừa không còn hợp lệ. Lỗi có thể chỉ xuất hiện khi plugin được nạp, không nhất thiết ở thời điểm ứng dụng khởi động.

### 3.2. Vì sao giữ nguyên method không đủ?

Trong class file, quan hệ superclass được lưu riêng với tham chiếu đến method. Runtime phải kiểm tra tính hợp lệ của quan hệ kế thừa khi nạp/liên kết class. Dù **Engine.run()** còn nguyên descriptor, **FastEngine** vẫn cố mở rộng một class đã bị final.

~~~text
Biên dịch ban đầu:
    FastEngine.class  ----extends----> Engine v1 (open)
                                           |
                                           v
                                        Hợp lệ

Thay JAR, giữ nguyên FastEngine.class:
    FastEngine.class  ----extends----> Engine v2 (final)
                                           |
                                           v
                             IncompatibleClassChangeError
~~~

Kết luận thực hành: **Thêm final vào public/protected base class được người khác kế thừa là thay đổi phá vỡ tương thích nhị phân**, kể cả khi không xóa bất kỳ method nào.

### 3.3. Trường hợp ít rủi ro hơn

Nếu class vốn chỉ dùng nội bộ, không có subclass ngoài phạm vi kiểm soát và mọi consumer có thể được build hoặc kiểm chứng đầy đủ, thêm final có thể là lựa chọn thiết kế hợp lý.

Tuy nhiên, chỉ nhìn source trong repository để nói “không có subclass” có thể bỏ sót:

- Plugin phát hành độc lập.
- Thư viện của đối tác hoặc các module không nằm trong cùng repository.
- Framework tạo subclass/proxy bằng bytecode lúc runtime.
- Consumer dùng reflection hoặc tên class từ cấu hình.
- Binary được xây dựng từ các phiên bản cũ hơn mà repository không còn chứa.

Cần kiểm kê cả dependency và artifact runtime, không chỉ tìm từ khóa **extends** trong source hiện tại.

## 4. Thêm final vào một instance method

Thêm **final** vào một class và thêm **final** vào method là hai thay đổi khác nhau.

### 4.1. Method từng cho phép override

Phiên bản 1:

~~~java
package example.api;

public class Formatter {
    public String format(String value) {
        return value;
    }
}
~~~

Consumer cũ:

~~~java
package example.plugin;

import example.api.Formatter;

public class HtmlFormatter extends Formatter {
    @Override
    public String format(String value) {
        return "<p>" + value + "</p>";
    }
}
~~~

Phiên bản 2:

~~~java
package example.api;

public class Formatter {
    public final String format(String value) {
        return value;
    }
}
~~~

Mã nguồn **HtmlFormatter** không biên dịch lại được với phiên bản 2. Quan trọng hơn, JVM khi nạp class file cũ có phương thức override bị cấm có thể ném **IncompatibleClassChangeError**. Đây là tình huống được mô tả trong JLS §13.4.17.

Nhóm thư viện có thể nghĩ rằng việc thêm final giúp tối ưu hoặc ngăn subclass thay đổi hành vi. Nhưng khi API đã được phát hành và consumer đang override nó, modifier này thay đổi hợp đồng mở rộng.

### 4.2. Final đối với static method

Một static method không tham gia overriding đa hình như instance method. Java dùng cơ chế method hiding cho static method. Vì vậy, theo quy tắc binary compatibility của JLS, thêm **final** vào static method không tạo cùng loại lỗi nhị phân như thêm final vào instance method từng bị override.

Tuy nhiên, source của subclass có method static trùng tên/chữ ký có thể không còn biên dịch được trong một số trường hợp. Đây là ví dụ tại sao **source compatibility** cần được kiểm tra tách khỏi binary compatibility.

### 4.3. Đừng nhầm với final field

**final field** chủ yếu liên quan đến khả năng gán giá trị, không trực tiếp quyết định quan hệ kế thừa. Với một **public static final** primitive/String được khởi tạo bằng biểu thức hằng, compiler còn có thể nhúng giá trị vào bytecode consumer. Rủi ro của loại field này thuộc hợp đồng dữ liệu/hằng số, khác với lỗi khi class hoặc method bị final.

Bài này tập trung vào **final class** và **final method** vì chúng ảnh hưởng trực tiếp đến inheritance và overriding.

## 5. Sealed class: giới hạn tập direct subclass

Một **sealed class** xác định chính xác các kiểu được phép trực tiếp kế thừa nó.

Ví dụ với Java 17 trở lên:

~~~java
package example.model;

public sealed abstract class Payment
        permits CardPayment, CashPayment {
}

public final class CardPayment extends Payment {
}

public non-sealed class CashPayment extends Payment {
}
~~~

Trong ví dụ:

- **Payment** chỉ cho phép **CardPayment** và **CashPayment** là direct subclass.
- **CardPayment** được đánh dấu **final**, vì nhánh này không được mở rộng.
- **CashPayment** được đánh dấu **non-sealed**, mở lại khả năng có subclass dưới nhánh CashPayment.

Một permitted direct subclass của sealed class phải chọn trạng thái kế thừa phù hợp: **final**, **sealed** hoặc **non-sealed**. Nếu chọn **sealed**, nó phải tiếp tục xác định các direct subclass được phép của chính mình.

### 5.1. Sealed interface

Interface cũng có thể sealed:

~~~java
package example.event;

public sealed interface Event
        permits CreatedEvent, CancelledEvent {
}

public record CreatedEvent(String id) implements Event {
}

public final class CancelledEvent implements Event {
}
~~~

**CreatedEvent** là record; record là final theo ngữ nghĩa Java và có thể là permitted implementation. Interface **Event** không cho phép các implementation khác tự ý tham gia làm direct child.

### 5.2. Ranh giới package và module

Java yêu cầu permitted direct subclass/subinterface nằm trong phạm vi cho phép:

- Với **named module**, permitted direct subclass phải thuộc **cùng module** với sealed parent.
- Với **unnamed module**, các permitted direct subclass phải thuộc **cùng package** với sealed parent.

Quy tắc này quan trọng với thư viện công khai: nếu trước đây consumer bên ngoài package/module có thể kế thừa class, việc thêm sealed không chỉ yêu cầu cập nhật danh sách **permits**; nó còn có thể khiến vị trí của consumer không còn hợp lệ theo quy tắc ngôn ngữ.

Không nên đề xuất “chỉ thêm tên mọi plugin bên ngoài vào permits” khi các plugin nằm ở package khác trong unnamed module hoặc ở named module khác. Cần thiết kế lại extension point phù hợp.

### 5.3. Permits chỉ kiểm soát direct subclass

~~~text
                 sealed Payment
                 /            \
                /              \
       final CardPayment     non-sealed CashPayment
                                    |
                                    v
                              LegacyCashPayment
                                    |
                                    v
                               MoreCashPayment
~~~

**Payment** chỉ cần cho phép **CardPayment** và **CashPayment** trực tiếp. Vì **CashPayment** là non-sealed, các subclass gián tiếp dưới nó có thể tiếp tục mở rộng theo quy tắc Java thông thường.

Đây là một phương án để giữ vùng extension mở: khóa tập nhánh cấp cao nhưng cho phép consumer tùy biến qua một nhánh **non-sealed** được thiết kế có chủ ý.

## 6. Thêm sealed vào class hoặc interface đã phát hành

### 6.1. Thêm sealed vào class trước đây mở

Phiên bản 1:

~~~java
package example.api;

public abstract class Job {
    public abstract void execute();
}
~~~

Plugin bên ngoài đã biên dịch:

~~~java
package example.plugin;

import example.api.Job;

public class CleanupJob extends Job {
    @Override
    public void execute() {
        System.out.println("cleanup");
    }
}
~~~

Phiên bản 2 có thể chuyển **Job** thành sealed và giới hạn direct subclasses:

~~~java
package example.api;

public sealed abstract class Job permits BuiltInJob {
    public abstract void execute();
}

final class BuiltInJob extends Job {
    @Override
    public void execute() {
        System.out.println("built-in");
    }
}
~~~

**CleanupJob.class** cũ vẫn tham chiếu đến **Job** làm superclass, nhưng nó không nằm trong tập direct subclass được cho phép. Khi JVM nạp class cũ, **IncompatibleClassChangeError** xảy ra.

Việc source của Job vẫn có method **execute()** không thay đổi kết luận. Quan hệ kế thừa đã trở thành một phần điều kiện liên kết.

### 6.2. Nếu subclass cũ được liệt kê trong permits?

Một subclass cũ **đã biên dịch** có thể tiếp tục liên kết nếu nó là permitted direct subclass hợp lệ và các điều kiện binary khác được đáp ứng. Nhưng source của subclass khi **biên dịch lại** phải tuân thủ quy tắc mới của sealed hierarchy, như khai báo **final**, **sealed** hoặc **non-sealed**.

Đừng đánh đồng hai việc:

- Bytecode cũ được JVM chấp nhận vì danh sách permitted phù hợp.
- Source cũ tiếp tục compile được mà không cần cập nhật modifier.

Việc thêm sealed cũng cần kiểm tra xem consumer cũ có thể được liệt kê hợp lệ theo ranh giới package/module không.

### 6.3. Thêm sealed vào interface

Một interface trước đây mở có thể được nhiều class hoặc subinterface độc lập triển khai:

~~~java
package example.spi;

public interface Plugin {
    void start();
}
~~~

Nếu phiên bản mới chuyển thành:

~~~java
package example.spi;

public sealed interface Plugin permits BuiltInPlugin {
    void start();
}
~~~

thì các plugin cũ **implements Plugin** nhưng không nằm trong tập permitted có thể gặp **IncompatibleClassChangeError** khi được nạp. Quy tắc này áp dụng cho cả direct implementation bằng class và direct subinterface.

Với SPI hoặc SDK công khai, thêm sealed thường là thay đổi lớn vì extension point có thể được sử dụng bởi các consumer mà đội phát hành thư viện không kiểm soát.

## 7. Thay đổi danh sách permits qua các phiên bản

Không chỉ thao tác thêm sealed mới quan trọng. Thay đổi tập permitted của một sealed type cũng có hệ quả khác nhau.

| Thay đổi | Hệ quả nhị phân với binary cũ | Lưu ý ngoài binary |
|---|---|---|
| Mở class thông thường thành **sealed** | Có thể lỗi với direct subclass cũ không được phép | Phải tuân thủ package/module và modifier của subclass |
| Mở interface thông thường thành **sealed** | Có thể lỗi với implementation/subinterface cũ không được phép | Đặc biệt rủi ro với SPI công khai |
| Thêm một permitted direct subclass | Theo JLS, không phá vỡ khả năng liên kết binary cũ | Có thể ảnh hưởng exhaustive switch và tính đầy đủ của xử lý |
| Xóa một permitted direct subclass | Binary cũ của subclass bị xóa quyền có thể gặp **IncompatibleClassChangeError** | Cần kế hoạch thay thế/di chuyển consumer |
| **sealed** thành **non-sealed** | Thường giữ binary compatibility | Mở rộng lại cây kế thừa; xem xét rủi ro hành vi |
| **final** thành **sealed** | Không làm hỏng binary cũ chỉ vì thay modifier | Thêm khả năng có subclass mới |
| **final** thành class mở | Thường không phá vỡ binary, nếu không vi phạm ràng buộc sealed parent | Mở rộng hợp đồng extension, cần thiết kế hỗ trợ |

### 7.1. Thêm permitted subtype và exhaustive switch

Ví dụ Java 21 với pattern matching for switch:

~~~java
sealed interface Response permits Success, Failure {}

record Success(String value) implements Response {}

record Failure(String message) implements Response {}

static String describe(Response response) {
    return switch (response) {
        case Success s -> s.value();
        case Failure f -> f.message();
    };
}
~~~

Tại thời điểm biên dịch, compiler thấy các subtype được cho phép và xác định switch đã exhaustive.

Nếu phiên bản mới mở rộng hierarchy bằng subtype thứ ba và chương trình cũ vẫn giữ bytecode của switch, việc **thêm** subtype thường được coi là binary compatible theo JLS: class file cũ vẫn có thể liên kết.

Tuy nhiên, khi switch cũ thực tế nhận instance của subtype mới không được bao phủ, tại runtime có thể phát sinh **MatchException**. Đây là rủi ro tương thích hành vi/migration dù không phải phá vỡ binary linkage của sealed type.

Do đó, khi mở rộng **permits**, ngoài kiểm tra binary API hãy tìm các switch expression/pattern switch phụ thuộc tính exhaustive, và chạy compatibility test với kiểu mới.

### 7.2. Xóa permitted subtype

Khi một subclass từng được phép bị loại khỏi **permits**, class file cũ của chính subclass đó có thể không nạp được. Đây không chỉ là cảnh báo compiler; JVM thực hiện kiểm tra cấu trúc kế thừa khi liên kết.

Trước khi bỏ subtype, cần biết:

- Có consumer đang tạo instance của subtype không?
- Có dữ liệu serialized chứa tên subtype không?
- Có ServiceLoader, reflection hoặc DI container nạp subtype không?
- Có consumer được biên dịch độc lập không?
- Có thể hỗ trợ subtype thêm một chu kỳ phát hành không?

Nếu không thể kiểm soát consumer, một major release có hướng dẫn di chuyển và thời hạn hỗ trợ là lựa chọn rõ ràng hơn.

## 8. Non-sealed như một điểm mở rộng có kiểm soát

Sealed hierarchy không nhất thiết phải khóa mọi cấp. Có thể giới hạn các nhóm kiểu cấp cao nhưng dành một nhánh **non-sealed** cho bên thứ ba mở rộng.

~~~java
package example.api;

public sealed interface Message
        permits SystemMessage, ExternalMessage {
}

public record SystemMessage(String text) implements Message {
}

public non-sealed interface ExternalMessage extends Message {
}
~~~

Consumer bên ngoài có thể triển khai **ExternalMessage**:

~~~java
package partner.plugin;

import example.api.ExternalMessage;

public final class PartnerMessage implements ExternalMessage {
}
~~~

Lợi ích:

- Tập direct subtype của **Message** vẫn được kiểm soát.
- API công khai dành một extension point rõ ràng.
- Bên thứ ba không cần được liệt kê trực tiếp trong **Message.permits**.
- Các module có thể được nâng cấp độc lập qua nhánh **ExternalMessage**.

Tuy nhiên, **non-sealed** không tự bảo đảm mọi thay đổi sau này an toàn. Nếu sau một thời gian thư viện chuyển **ExternalMessage** thành sealed hoặc final, nó vẫn có thể làm hỏng plugin đã phát hành. Nhánh mở nên được xem là một hợp đồng hỗ trợ lâu dài.

### 8.1. Non-sealed chỉ hợp lệ trong sealed hierarchy

Không thể tùy ý viết:

~~~java
public non-sealed class Utility {
}
~~~

nếu Utility không có sealed direct superclass hoặc sealed direct superinterface. Compiler sẽ từ chối. Vì vậy, khi bỏ **final** trong một sealed hierarchy, phải chọn modifier và quan hệ kế thừa hợp lệ; không chỉ xóa từ khóa rồi giả định source còn compile.

## 9. Thay đổi superclass, interface và constructor

**final** và **sealed** là biểu hiện rõ nhất của rủi ro inheritance, nhưng các thay đổi khác cũng có thể phá vỡ consumer cũ.

### 9.1. Đổi superclass hoặc bỏ interface

Một subclass đã biên dịch có thể dựa vào việc một kiểu vẫn là subtype của một class/interface cụ thể. Nếu thư viện thay đổi hierarchy và loại bỏ supertype mà binary cũ dùng trong các lời gọi hoặc phép chuyển kiểu, lỗi liên kết hoặc **VerifyError** có thể xuất hiện.

Không nên kết luận “không ai gọi trực tiếp superclass” chỉ từ source. Quan hệ kiểu còn được dùng trong bytecode để xác minh type safety và dispatch phương thức.

### 9.2. Thu hẹp constructor

Lớp con gọi constructor của superclass qua **super(...)**. Nếu constructor công khai hoặc protected trong phiên bản cũ bị xóa, đổi descriptor hoặc thu hẹp quyền truy cập trong phiên bản mới, subclass cũ có thể gặp **NoSuchMethodError** hoặc **IllegalAccessError** khi liên kết lời gọi constructor.

Ví dụ:

~~~java
public class Base {
    protected Base(String configuration) {
    }
}
~~~

Consumer cũ:

~~~java
public class CustomBase extends Base {
    public CustomBase() {
        super("custom");
    }
}
~~~

Nếu v2 chỉ còn **Base(int)**, bytecode cũ vẫn tham chiếu đến constructor nhận String và có thể không liên kết được. Đây là vấn đề độc lập với việc class có final hay sealed.

### 9.3. Thêm abstract hoặc thay đổi method override

Thay một concrete method thành abstract hoặc thêm abstract member vào contract của lớp/interface có thể làm consumer cũ thiếu implementation khi một đường gọi thực tế được sử dụng. Lỗi có thể là **AbstractMethodError**.

Thêm default method vào interface thường không trực tiếp phá vỡ khả năng liên kết cũ, nhưng có thể tạo xung đột khi nhiều interface cung cấp default method cùng chữ ký. Khi chạy một đường gọi xung đột, **IncompatibleClassChangeError** có thể xuất hiện.

Đó là lý do đánh giá khả năng kế thừa cần xem toàn bộ hierarchy và method resolution, không chỉ tìm modifier final/sealed.

## 10. Rủi ro với framework, proxy và mã được tạo ở runtime

Một framework có thể tạo lớp con mà source repository không chứa. Ví dụ:

- Spring AOP dùng class-based proxy.
- ORM hoặc thư viện lazy loading tạo proxy bằng subclass.
- Byte Buddy, CGLIB hoặc công cụ instrumentation sinh bytecode.
- Plugin framework nạp class theo tên từ cấu hình.
- Serialization/deserialization framework cần instantiate hoặc phân giải subtype.
- ServiceLoader tìm implementation ở runtime.

Nếu một class trở thành **final**, cơ chế cần subclass class đó có thể không còn hoạt động. Nếu một method trở thành **final**, class-based proxy thường không thể override method đó để chèn logic interception. Nếu một interface trở thành **sealed**, một generated class muốn trực tiếp implement interface có thể bị từ chối nếu không phải permitted subtype hợp lệ.

Đây là nhóm rủi ro cần integration test, vì unit test gọi class trực tiếp có thể vẫn thành công.

### 10.1. Không phải mọi proxy đều dùng subclass

Java có interface-based proxy và class-based proxy với ràng buộc khác nhau. Nếu một framework dùng proxy dựa trên interface thông thường, việc class implementation thành final không nhất thiết ngăn proxy interface hoạt động. Ngược lại, nếu interface itself bị sealed, generated implementation cần được xem xét theo quy tắc permits.

Vì vậy, cần xác nhận cơ chế proxy thực tế của từng framework và cấu hình của dự án. Không áp dụng một kết luận chung cho mọi proxy.

### 10.2. Kiểm thử theo cơ chế extension

| Cơ chế | Tình huống cần test |
|---|---|
| Subclass source | Consumer có extends trực tiếp |
| Interface implementation | Consumer có implements trực tiếp |
| Reflection | Nạp class bằng tên, gọi constructor, kiểm tra modifier |
| ServiceLoader | Provider cũ có thể được phát hiện và nạp |
| Class-based proxy | Framework có tạo subclass của class mới final/sealed không |
| Method interception | Method mới final có chặn interception không |
| Serialization | Dữ liệu cũ có tham chiếu subtype bị bỏ khỏi permits không |
| Pattern switch | Switch exhaustive cũ có xử lý subtype mới không |

Một rủi ro được coi là xử lý xong khi có bằng chứng trên đúng cơ chế lỗi, không chỉ khi compile lại source thành công.

## 11. Thực hành: chạy subclass cũ với class đã final

Ví dụ sau cho thấy cách kiểm tra binary compatibility đúng nghĩa. Ta sẽ biên dịch plugin một lần với thư viện v1 rồi giữ nguyên file class của plugin khi thay thư viện v2.

### Bước 1: Tạo thư viện v1

File **v1/example/api/Engine.java**:

~~~java
package example.api;

public class Engine {
    public String run() {
        return "Engine v1";
    }
}
~~~

Tạo JAR:

~~~bash
javac -d out-v1 v1/example/api/Engine.java
jar --create --file engine-v1.jar -C out-v1 .
~~~

### Bước 2: Tạo plugin và client

File **consumer/example/plugin/CustomEngine.java**:

~~~java
package example.plugin;

import example.api.Engine;

public class CustomEngine extends Engine {
    @Override
    public String run() {
        return "Plugin";
    }
}
~~~

File **consumer/example/app/Main.java**:

~~~java
package example.app;

import example.plugin.CustomEngine;

public class Main {
    public static void main(String[] args) {
        System.out.println(new CustomEngine().run());
    }
}
~~~

Biên dịch consumer bằng JAR v1:

~~~bash
javac -cp engine-v1.jar -d consumer-out consumer/example/plugin/CustomEngine.java consumer/example/app/Main.java
~~~

Tại đây **consumer-out** chứa bytecode cũ. Không biên dịch lại các file đó ở bước sau.

Chạy baseline:

~~~bash
# Windows
java -cp "engine-v1.jar;consumer-out" example.app.Main

# Linux/macOS
java -cp "engine-v1.jar:consumer-out" example.app.Main
~~~

Kết quả:

~~~text
Plugin
~~~

### Bước 3: Thay Engine bằng phiên bản final

File **v2/example/api/Engine.java**:

~~~java
package example.api;

public final class Engine {
    public String run() {
        return "Engine v2";
    }
}
~~~

Tạo JAR v2:

~~~bash
javac -d out-v2 v2/example/api/Engine.java
jar --create --file engine-v2.jar -C out-v2 .
~~~

### Bước 4: Chạy consumer cũ mà không biên dịch lại

~~~bash
# Windows
java -cp "engine-v2.jar;consumer-out" example.app.Main

# Linux/macOS
java -cp "engine-v2.jar:consumer-out" example.app.Main
~~~

JVM phải nạp **CustomEngine.class** đã được biên dịch với Engine v1. Nhưng **Engine v2** là final. Kết quả mong đợi là **IncompatibleClassChangeError** thông báo một class đang cố kế thừa class final.

Điểm cần ghi nhận: thư viện v2 tự biên dịch thành công, vẫn có method **run()**, và nếu viết một ứng dụng chỉ tạo **new Engine()** thì có thể chạy bình thường. Lỗi chỉ xuất hiện khi consumer cũ có quan hệ extends được nạp.

### Bước 5: Quan sát class file

Dùng **javap**:

~~~bash
javap -classpath engine-v1.jar -v example.api.Engine
javap -classpath engine-v2.jar -v example.api.Engine
javap -classpath consumer-out -v example.plugin.CustomEngine
~~~

Trong class file, class **final** có cờ **ACC_FINAL**. Class file của CustomEngine vẫn khai báo superclass là Engine. Khi thay JAR, tổ hợp class file mới không thỏa điều kiện inheritance.

Ví dụ này giúp phân biệt lỗi nhị phân với lỗi compile. Không gọi lại **javac** cho consumer trong bước kiểm thử tương thích nhị phân.

## 12. Thực hành với sealed và permits

Một phép thử tương tự có thể minh họa sealed. Để giữ ví dụ phù hợp quy tắc package trong unnamed module, thư viện sealed mới và các direct subclass được phép nằm cùng package **example.model**.

Phiên bản 1:

~~~java
package example.model;

public interface Operation {
    String name();
}
~~~

Một implementation cũ đã biên dịch:

~~~java
package example.external;

import example.model.Operation;

public class UnknownOperation implements Operation {
    @Override
    public String name() {
        return "unknown";
    }
}
~~~

Phiên bản 2 của interface:

~~~java
package example.model;

public sealed interface Operation permits KnownOperation {
    String name();
}

final class KnownOperation implements Operation {
    @Override
    public String name() {
        return "known";
    }
}
~~~

Khi runtime dùng **Operation v2** và nạp binary cũ **UnknownOperation**, implementation đó không phải permitted direct subtype. JVM có thể ném **IncompatibleClassChangeError**.

Cách sửa không thể chỉ thêm **UnknownOperation** vào permits nếu implementation thực tế nằm ở package khác trong unnamed module. Cần thay đổi thiết kế, chẳng hạn:

- Tiếp tục giữ Operation là interface mở ở phiên bản cần tương thích.
- Tạo sealed hierarchy mới dành cho các kiểu tích hợp nội bộ, còn Operation cũ giữ nguyên.
- Tạo nhánh extension **non-sealed** trong hierarchy mới để cho phép consumer bên ngoài triển khai.
- Phát hành major version và yêu cầu consumer cập nhật nếu quyết định khóa extension point là chủ đích.

## 13. Chiến lược migration giảm phá vỡ

### 13.1. Giữ API mở trong thời gian chuyển tiếp

Nếu public base class đã được consumer subclass, một cách an toàn là giữ class cũ không final trong chu kỳ chuyển tiếp, đồng thời đưa ra API mới có thiết kế hạn chế hơn.

Ví dụ:

~~~java
package example.api;

@Deprecated(since = "2.0")
public class LegacyProcessor {
    public String process(String text) {
        return text;
    }
}

public final class NewProcessor {
    public String process(String text) {
        return text;
    }
}
~~~

Các consumer cũ vẫn có thể kế thừa **LegacyProcessor**. Consumer mới dùng **NewProcessor** nếu không cần inheritance. Sau khi có kế hoạch di chuyển, thư viện có thể quyết định khi nào loại bỏ API cũ.

Đánh dấu deprecated không tự phá vỡ binary compatibility. Nó cung cấp tín hiệu chuyển đổi trước khi bỏ hợp đồng.

### 13.2. Dùng composition thay cho inheritance

Nếu mục tiêu của final là ngăn subclass sửa logic nội bộ, có thể giữ contract mở cũ nhưng chuyển phần thực thi sang đối tượng được đóng gói.

~~~java
public final class ProcessingCore {
    public String execute(String input) {
        return input.trim();
    }
}

@Deprecated
public class LegacyProcessor {
    private final ProcessingCore core = new ProcessingCore();

    public String process(String input) {
        return core.execute(input);
    }
}
~~~

**LegacyProcessor** vẫn mở cho consumer cũ, còn **ProcessingCore** dùng final vì không được thiết kế làm extension point. Nhóm có thể dần hướng consumer sang composition mà không đột ngột cấm subclass hiện có.

### 13.3. Duy trì protected hook hợp lệ

Nếu framework cần cho phép tùy biến, hãy xác định rõ method nào là extension point:

~~~java
public class TaskRunner {
    public final void runTask() {
        beforeRun();
        executeCore();
        afterRun();
    }

    protected void beforeRun() {
    }

    protected void afterRun() {
    }

    private void executeCore() {
        System.out.println("core");
    }
}
~~~

Mẫu này phù hợp **khi thiết kế API mới**: một phương thức orchestration final giữ invariant, các protected hook vẫn override được.

Nhưng nếu **runTask()** trước đây cho phép subclass override và có consumer cũ đang làm như vậy, đổi thẳng nó thành final vẫn có thể phá vỡ binary compatibility. Cần triển khai migration theo giai đoạn, giữ method cũ hoặc tạo API mới thay vì cho rằng mẫu thiết kế đẹp hơn sẽ làm thay đổi cũ an toàn.

### 13.4. Thêm sealed hierarchy song song

Thay vì biến một interface SPI đang mở thành sealed:

~~~java
public interface Plugin {
    void execute();
}
~~~

có thể giữ **Plugin** cho consumer cũ, đồng thời thêm một hierarchy sealed riêng cho những kiểu hệ thống được kiểm soát:

~~~java
public sealed interface BuiltInAction
        permits ReadAction, WriteAction {
}

public record ReadAction(String path) implements BuiltInAction {
}

public record WriteAction(String path, String data) implements BuiltInAction {
}
~~~

Các kiểu built-in có phạm vi rõ ràng, trong khi Plugin tiếp tục là điểm mở rộng bên ngoài. Đây là cách tách nhu cầu exhaustive modeling khỏi yêu cầu hỗ trợ plugin công khai.

### 13.5. Phiên bản hóa có chủ đích

Nếu sản phẩm quyết định phải khóa inheritance:

1. Công bố thay đổi sắp tới.
2. Đánh dấu API cũ deprecated.
3. Cung cấp adapter hoặc API mới để consumer chuyển đổi.
4. Kiểm kê subclass/implementation thực tế.
5. Tạo compatibility test với artifact cũ.
6. Xác định thời hạn hỗ trợ và major release có breaking change.
7. Cập nhật migration guide và release notes.
8. Chỉ thay hợp đồng khi đã chấp nhận rõ ảnh hưởng lên consumer.

**Semantic Versioning** có thể giúp giao tiếp mức độ thay đổi, nhưng nhãn major/minor không tự bảo đảm JVM sẽ liên kết. Bằng chứng test trên artifact cụ thể vẫn cần thiết.

## 14. Kiểm thử tương thích nhị phân và khả năng mở rộng

### 14.1. Quy trình kiểm thử

1. **Chốt baseline:** lưu JAR/API v1, commit, checksum và JDK dùng để biên dịch.
2. **Lưu consumer cũ:** lấy binary plugin/subclass/implementation đã phát hành.
3. **Xác định thay đổi:** so sánh final, sealed, non-sealed, permits, method modifiers, constructor và hierarchy.
4. **Build thư viện mới:** tạo JAR v2 từ source mới.
5. **Chạy binary cũ:** giữ nguyên các class file consumer, chỉ thay thư viện v1 bằng v2 trên classpath/module path.
6. **Kiểm tra nạp class:** kích hoạt các plugin, ServiceLoader, proxy và subclass quan trọng.
7. **Kiểm tra hành vi:** chạy đường gọi override, hook và pattern switch liên quan.
8. **Lưu bằng chứng:** ghi JDK, JAR checksum, classpath, lệnh chạy và log lỗi.
9. **Đánh giá rủi ro còn lại:** consumer nào không có binary đại diện cần ghi rõ.

Với thư viện Java 17+, có thể dùng **javap** để xem modifier và danh sách permitted subclasses:

~~~bash
javap -classpath api-v2.jar -v -p example.api.SomeType
~~~

Các tín hiệu có thể thấy:

- **ACC_FINAL** với class hoặc method final.
- Thuộc tính **PermittedSubclasses** với sealed type.
- **super_class** và **interfaces** của class file consumer cũ.
- Method descriptor và access flags để đối chiếu.

Công cụ so sánh API như Revapi hoặc japicmp có thể hỗ trợ nhận diện thay đổi. Tuy nhiên, báo cáo API không thay thế việc chạy chính artifact cũ, đặc biệt khi có plugin, generated proxy và runtime-only dependencies.

### 14.2. Ma trận test đề xuất

| Trường hợp | Source cũ + API mới | Binary cũ + API mới | Ý nghĩa |
|---|---|---|---|
| Class v1 mở, v2 final; consumer extends | Compile fail | Có thể ICCE khi nạp subclass | Breaking inheritance |
| Instance method v1 mở, v2 final; consumer override | Compile fail | Có thể ICCE khi nạp class | Breaking override |
| Static method v1 mở, v2 final | Có thể bị hạn chế source hiding | Thường không phá vỡ binary theo JLS | Source và binary khác nhau |
| Class v1 mở, v2 sealed; consumer không permitted | Compile fail | ICCE khi nạp subclass | Breaking permits |
| Sealed v1, v2 thêm subtype | Consumer cũ thường compile được nếu không phụ thuộc exhaustive source | Binary cũ vẫn có thể liên kết | Cần test exhaustive switch/hành vi |
| Sealed v1, v2 bỏ một permitted subtype | Consumer cũ có thể compile fail | ICCE khi nạp subtype cũ | Breaking permits |
| Final v1, v2 bỏ final hợp lệ | Thường có thêm khả năng mở rộng | Binary cũ vẫn có thể liên kết | Nói chung an toàn nhị phân |
| Concrete method v1 thành abstract | Có thể compile fail tùy class | Có thể AbstractMethodError khi gọi | Breaking implementation contract |

**ICCE** là viết tắt của **IncompatibleClassChangeError**. Bảng diễn đạt theo cơ chế lỗi điển hình; thời điểm lỗi xuất hiện phụ thuộc class nào được nạp và đường code nào được thực thi.

### 14.3. Các consumer cần đưa vào test

- Subclass được build trong cùng repository.
- Plugin được phát hành riêng.
- Implementation của interface/SPI công khai.
- Framework extension hoặc interceptor.
- Proxy runtime do ORM/AOP tạo.
- Consumer dùng reflection, ServiceLoader hoặc class name từ cấu hình.
- Consumer chứa switch exhaustive trên sealed hierarchy.
- Batch chạy theo lịch mà test bình thường ít kích hoạt.

Nếu chỉ có test của thư viện v2 mà không có test consumer cũ, chưa đủ bằng chứng cho binary compatibility.

## 15. Rủi ro trong hệ thống module và class loader

Sealed hierarchy có các quy tắc package/module, còn việc load class phụ thuộc classpath, module path và class loader thực tế. Những yếu tố này cần được ghi nhận trong migration.

Ví dụ:

- Một plugin chạy trong named module khác có thể không hợp lệ làm permitted direct subtype của sealed API.
- Framework dùng class loader riêng có thể nạp bản thư viện không phải bản nhóm dự kiến.
- Có nhiều JAR cùng chứa một class nhưng khác modifier hoặc permits.
- Shadowed dependency khiến API tại runtime khác API được dùng khi compile.
- Một plugin chỉ được nạp khi thực hiện tác vụ đặc biệt, nên lỗi xuất hiện muộn.

Khi điều tra, hãy xác nhận artifact nào đã được JVM nạp, version/checksum của nó và đường dẫn thực tế. Đừng kết luận chỉ dựa trên dependency khai báo trong build file.

Các lựa chọn như mở module cho reflection hoặc thêm command-line flags không thể biến một subclass không được phép thành hợp lệ dưới sealed hierarchy. **Permits** là ràng buộc ngôn ngữ và JVM; nó không phải lỗi cấu hình reflection có thể bỏ qua bằng một cờ runtime tùy ý.

## 16. Checklist đánh giá trước khi thay đổi final/sealed

### Xác định API và consumer

- [ ] Đã chốt artifact baseline của thư viện.
- [ ] Đã kiểm kê class/interface được phát hành như extension point.
- [ ] Đã tìm subclass hoặc implementation trong repository.
- [ ] Đã xem xét plugin, SDK consumer và module bên ngoài.
- [ ] Đã kiểm tra proxy, ServiceLoader và reflection.
- [ ] Đã ghi phiên bản JDK và cách nạp class thực tế.

### Đánh giá modifier

- [ ] Class mới final có subclass cũ không?
- [ ] Instance method mới final có consumer đang override không?
- [ ] Sealed class/interface mới có loại direct child cũ không?
- [ ] Mọi permitted direct subtype có nằm đúng package/module không?
- [ ] Các child của sealed type có modifier final/sealed/non-sealed hợp lệ khi biên dịch lại không?
- [ ] Có nhánh non-sealed phù hợp nếu cần hỗ trợ extension bên ngoài không?
- [ ] Có loại bỏ một permitted subtype đã phát hành không?
- [ ] Có thêm subtype khiến switch exhaustive cũ cần kiểm tra không?

### Kiểm thử và phát hành

- [ ] Đã so sánh API binary và classfile flags.
- [ ] Đã chạy consumer class file cũ với JAR mới, không biên dịch lại consumer.
- [ ] Đã kiểm thử đường nạp plugin và proxy runtime.
- [ ] Đã kiểm thử method override, constructor và hierarchy.
- [ ] Đã kiểm thử exhaustive switch nếu tập permitted mở rộng.
- [ ] Đã ghi lại lỗi và bằng chứng test.
- [ ] Đã có kế hoạch migration/adapter/deprecation nếu breaking.
- [ ] Đã xác định rollback và trách nhiệm hỗ trợ consumer.

## 17. Tài liệu đặc tả để đối chiếu

Các quy tắc về tương thích nhị phân được mô tả trong **Java Language Specification, Chapter 13: Binary Compatibility**:

- **§13.4.2:** sealed, non-sealed và final classes.
- **§13.4.17:** final methods.
- **§13.4.4:** thay đổi superclasses và superinterfaces.
- **§13.5.2:** sealed và non-sealed interfaces.
- **§13.5.7:** thay đổi method của interface, gồm default methods.

Tham khảo trực tiếp tài liệu chuẩn cho Java 17 trở lên: https://docs.oracle.com/javase/specs/jls/se17/html/jls-13.html

Khi đánh giá một migration cụ thể, hãy đọc đặc tả của release tương ứng với compiler và runtime mục tiêu. Nếu dự án dùng Java mới hơn và cần biết quy tắc chi tiết của một tính năng mới, kiểm tra chương liên quan trong JLS của chính release đó.

---

**Điểm cần nhớ:** Khả năng được subclass, implement hoặc override là một phần của hợp đồng API. Thêm **final** hay **sealed** có thể thay đổi hợp đồng đó ngay cả khi tên và descriptor của các method vẫn nguyên vẹn. Để migration an toàn, hãy kiểm tra các binary consumer đã biên dịch từ trước, đánh giá tập **permits** và extension point, rồi đưa ra lộ trình chuyển đổi hoặc API thay thế trước khi khóa cây kế thừa.
