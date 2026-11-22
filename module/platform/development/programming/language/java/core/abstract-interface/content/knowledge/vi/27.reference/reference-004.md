# Các hiểu lầm thường gặp về abstract class và interface trong Java, và cách kiểm chứng

Khi học Java, nhiều lỗi về thiết kế hướng đối tượng xuất phát từ những quy tắc được nhớ chưa đầy đủ: cho rằng lớp trừu tượng không có thân phương thức, interface chỉ chứa phương thức abstract, hoặc một lớp có thể tạo đối tượng trực tiếp từ bất kỳ kiểu tham chiếu nào. Cách học chắc chắn là phân biệt **quy tắc của ngôn ngữ**, **hành vi lúc chạy** và **quy ước thiết kế**, rồi kiểm chứng từng điều bằng compiler hoặc một chương trình nhỏ.

Bài này tập trung vào **abstract class**, **interface**, kế thừa, triển khai, phương thức **default**, phương thức **static** và đa hình.

## 1. Hiểu lầm: lớp abstract không thể có constructor hoặc phương thức đã triển khai

**Thực tế:** lớp abstract có thể có trường, constructor, phương thức cụ thể và phương thức abstract. Điều khiến lớp đó không thể được khởi tạo trực tiếp là khai báo abstract, không phải việc mọi phương thức đều thiếu thân.

Constructor của lớp abstract chạy khi một lớp con được khởi tạo. Nó thường thiết lập trạng thái chung và bảo đảm các bất biến của phần lớp cha. Phương thức cụ thể có thể chứa logic dùng chung, trong khi phương thức abstract để lớp con cung cấp phần khác biệt.

~~~java
abstract class BaseDocument {
    private final String title;

    protected BaseDocument(String title) {
        this.title = title;
    }

    public String title() {
        return title;
    }

    public abstract int pageCount();
}
~~~

Đây là đoạn minh họa, chưa phải chương trình độc lập. BaseDocument có constructor và phương thức cụ thể title(), đồng thời yêu cầu lớp con cung cấp pageCount().

Một lớp con cụ thể phải triển khai phương thức abstract còn thiếu:

~~~java
final class ShortDocument extends BaseDocument {
    ShortDocument(String title) {
        super(title);
    }

    @Override
    public int pageCount() {
        return 1;
    }
}
~~~

Nếu ShortDocument không triển khai pageCount(), lớp phải được khai báo abstract hoặc compiler sẽ báo lỗi. Annotation @Override giúp compiler xác nhận phương thức thực sự ghi đè hoặc triển khai một phương thức kế thừa.

## 2. Hiểu lầm: không thể khai báo biến có kiểu abstract class hoặc interface

**Thực tế:** không thể tạo đối tượng trực tiếp bằng new đối với interface hoặc lớp abstract, nhưng có thể khai báo biến, tham số, kiểu trả về và trường bằng các kiểu đó. Biến tham chiếu có thể trỏ tới một đối tượng của lớp cụ thể tương thích.

~~~java
// Không hợp lệ: không thể khởi tạo trực tiếp
// BaseDocument document = new BaseDocument("Draft");

// Hợp lệ nếu ShortDocument là lớp cụ thể:
BaseDocument document = new ShortDocument("Draft");
~~~

Dòng hợp lệ minh họa đa hình: kiểu khai báo của biến là BaseDocument, còn kiểu thực của đối tượng là ShortDocument. Khi gọi một phương thức instance được override, Java chọn phần triển khai dựa trên kiểu thực của đối tượng lúc chạy.

Không nên kết luận rằng một biến có kiểu interface chỉ có thể trỏ tới một interface. Interface là kiểu tham chiếu; đối tượng thực phải là instance của một lớp cụ thể triển khai interface đó.

## 3. Hiểu lầm: interface chỉ có các phương thức abstract

**Thực tế:** interface có thể khai báo các phương thức abstract, default, static và private (phương thức private trong interface có từ Java 9). Các dạng này phục vụ những mục đích khác nhau:

- Phương thức abstract mô tả hành vi mà lớp triển khai phải cung cấp.
- Phương thức default có thân, cung cấp hành vi mặc định có thể được lớp triển khai giữ nguyên hoặc override.
- Phương thức static thuộc về chính interface và được gọi bằng tên interface.
- Phương thức private hỗ trợ chia sẻ logic giữa các phương thức có thân bên trong interface; nó không phải hợp đồng mà lớp triển khai override.

Ví dụ:

~~~java
interface Auditable {
    String actor();

    default String auditLine() {
        return "actor=" + actor();
    }

    static String formatName() {
        return "audit";
    }

    private String normalize(String value) {
        return value.trim();
    }
}
~~~

Đoạn trên minh họa các dạng phương thức, nhưng normalize hiện chưa được gọi. Trong mã thật, phương thức private có thể được dùng bên trong một phương thức có thân, chẳng hạn default, để chia sẻ logic. Một phương thức private trong interface không được lớp triển khai gọi trực tiếp như một phần API và không thể override.

Các trường được khai báo trong interface cũng có quy tắc riêng: chúng ngầm định là public static final. Vì vậy interface thường không dùng để lưu trạng thái instance riêng cho từng đối tượng. Nếu mỗi đối tượng cần dữ liệu thay đổi, hãy đặt dữ liệu đó trong lớp triển khai hoặc lớp nền phù hợp.

## 4. Hiểu lầm: phương thức default luôn được dùng, không cần quan tâm xung đột

**Thực tế:** phương thức default cho phép interface bổ sung hành vi mặc định, nhưng Java có quy tắc giải quyết khi nhiều nguồn cung cấp phương thức cùng chữ ký.

1. Phương thức instance phù hợp được định nghĩa trong lớp thường được ưu tiên hơn phương thức default từ interface.
2. Nếu một interface con mở rộng interface cha và override phương thức default, phần định nghĩa ở interface con cụ thể hơn.
3. Nếu một lớp nhận hai phương thức default xung đột từ hai interface độc lập, lớp thường phải override phương thức để giải quyết xung đột.

Ví dụ sau **cố ý không biên dịch** vì CombinedLogger nhận hai phương thức default cùng chữ ký mà không chọn cách xử lý:

~~~java
interface ConsoleLog {
    default String channel() {
        return "console";
    }
}

interface FileLog {
    default String channel() {
        return "file";
    }
}

// Cố ý sai: không giải quyết xung đột channel()
class CombinedLogger implements ConsoleLog, FileLog {
}
~~~

Cách sửa là override rõ ràng:

~~~java
class CombinedLogger implements ConsoleLog, FileLog {
    @Override
    public String channel() {
        return ConsoleLog.super.channel() + "+" + FileLog.super.channel();
    }
}
~~~

Cú pháp ConsoleLog.super.channel() cho phép gọi phần triển khai mặc định cụ thể từ interface đó. Chỉ dùng nó khi thật sự muốn tái sử dụng logic mặc định tương ứng.

## 5. Hiểu lầm: phương thức static của interface được kế thừa như phương thức instance

**Thực tế:** phương thức static của interface được gọi bằng tên interface. Nó không được kế thừa như phương thức instance thông thường của lớp triển khai.

~~~java
interface Identifier {
    static String kind() {
        return "identifier";
    }
}

class UserId implements Identifier {
}
~~~

Cách gọi hợp lệ là Identifier.kind(). Cách gọi UserId.kind() hoặc new UserId().kind() không phải cách gọi hợp lệ cho phương thức static chỉ được khai báo trong interface Identifier. Hãy phân biệt rõ phương thức static với phương thức default: default được gọi trên đối tượng và có thể override; static được gọi trên kiểu khai báo và không tham gia dispatch đa hình instance.

## 6. Hiểu lầm: interface có thể triển khai interface bằng implements

**Thực tế:** lớp dùng implements để triển khai interface. Một interface mở rộng một hoặc nhiều interface khác bằng extends. Một lớp chỉ có thể extends một lớp trực tiếp, nhưng có thể implements nhiều interface.

~~~java
interface HasId {
    String id();
}

interface HasLabel extends HasId {
    String label();
}

abstract class EntityBase {
    public abstract String type();
}

final class UserEntity extends EntityBase implements HasLabel {
    @Override
    public String id() {
        return "u-17";
    }

    @Override
    public String label() {
        return "User";
    }

    @Override
    public String type() {
        return "account";
    }
}
~~~

HasLabel kế thừa hợp đồng id() từ HasId, nên UserEntity phải triển khai cả id() và label(). Ngoài ra, UserEntity còn triển khai type() được kế thừa từ lớp abstract EntityBase. Vì thế, khi kiểm tra một lớp concrete, hãy xét toàn bộ phương thức abstract còn lại từ cả lớp cha lẫn các interface.

## 7. Ví dụ hoàn chỉnh: kiểm chứng bằng compiler và lúc chạy

Ví dụ dưới đây cho thấy lớp abstract có constructor và phương thức cụ thể; lớp con hoàn thiện phương thức abstract; kiểu tham chiếu là interface; phương thức default có thể bị override; phương thức static của interface được gọi bằng tên interface.

Lưu toàn bộ mã vào tệp **AbstractInterfaceChecks.java**:

~~~java
interface Describable {
    String describe();

    default String source() {
        return "interface default";
    }

    static String contract() {
        return "Describable";
    }
}

abstract class BaseReport implements Describable {
    private final String title;

    protected BaseReport(String title) {
        this.title = title;
        System.out.println("BaseReport constructor: " + title);
    }

    @Override
    public String describe() {
        return "Report: " + title;
    }

    protected abstract int itemCount();

    public final int itemCountForDisplay() {
        return itemCount();
    }
}

final class SalesReport extends BaseReport {
    SalesReport(String title) {
        super(title);
    }

    @Override
    public String source() {
        return "SalesReport override";
    }

    @Override
    protected int itemCount() {
        return 3;
    }
}

public class AbstractInterfaceChecks {
    public static void main(String[] args) {
        Describable value = new SalesReport("Q3");

        System.out.println(value.describe());
        System.out.println(value.source());
        System.out.println(Describable.contract());
        System.out.println(value instanceof Describable);
        System.out.println(((BaseReport) value).itemCountForDisplay());
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~text
javac AbstractInterfaceChecks.java
java AbstractInterfaceChecks
~~~

Kết quả stdout chính xác:

~~~text
BaseReport constructor: Q3
Report: Q3
SalesReport override
Describable
true
3
~~~

Cách đọc kết quả:

- Dòng đầu xác nhận constructor của lớp abstract chạy khi tạo SalesReport.
- describe() dùng phần triển khai chung trong BaseReport, dù biến value có kiểu Describable.
- source() gọi phần override của SalesReport, thay cho thân default trong interface.
- Describable.contract() được gọi qua tên interface vì đó là phương thức static.
- instanceof trả về true vì đối tượng thực là SalesReport, triển khai Describable thông qua lớp cha.
- itemCountForDisplay() là phương thức cụ thể công khai gọi phương thức abstract itemCount() đã được SalesReport hoàn thiện.

## 8. Cách kiểm chứng từng hiểu lầm

Không cần chỉ tin vào lời giải thích. Hãy thiết kế một phép thử nhỏ cho mỗi quy tắc:

| Điều cần kiểm tra | Phép thử | Kết quả mong đợi |
|---|---|---|
| Có thể khởi tạo trực tiếp lớp abstract? | Thử khởi tạo BaseReport trong mã minh họa | Compiler từ chối vì lớp abstract |
| Concrete class có thể thiếu phương thức abstract? | Bỏ itemCount() khỏi SalesReport mà vẫn để lớp concrete | Compiler báo chưa triển khai phương thức abstract |
| Phương thức default có thể bị override? | Gọi source() trước và sau khi thêm override | Kết quả chuyển từ interface default sang SalesReport override |
| Phương thức static interface gọi thế nào? | Gọi Describable.contract() | Trả về Describable |
| Kiểu tham chiếu có quyết định implementation của phương thức instance? | Giữ Describable value, đổi lớp thực sang lớp khác override describe() | Lời gọi dùng implementation của đối tượng thực |
| Hai default method cùng chữ ký có tự chọn một cái? | Triển khai hai interface có cùng default mà không override | Compiler báo xung đột |

Các thử nghiệm cố ý gây lỗi nên được thực hiện riêng từng trường hợp, vì một lỗi biên dịch có thể ngăn những phần còn lại được kiểm tra. Sau mỗi thay đổi, biên dịch lại và đọc thông báo mới.

## 9. Quy trình đọc lỗi và xác minh trong dự án

1. Đọc thông báo compiler và xác định file, dòng, lớp cùng phương thức liên quan.
2. Tìm khai báo gốc trong interface hoặc lớp cha, rồi so sánh chữ ký và mức truy cập.
3. Kiểm tra lớp có phải abstract hay concrete. Lớp concrete phải hoàn thiện mọi phương thức abstract còn thiếu.
4. Thêm @Override cho các phương thức dự định ghi đè để compiler bắt lỗi tên hoặc tham số sai.
5. Kiểm tra xung đột giữa các phương thức default, khác biệt giữa static và instance, và các quy tắc truy cập.
6. Chạy lại lệnh build chuẩn của dự án. Nếu dự án nhiều module, hãy dùng build tool để bảo đảm classpath và source path đúng; một lỗi thiếu dependency không đồng nghĩa với lỗi thiết kế interface.

Không xóa @Override chỉ để làm mất một thông báo lỗi. Annotation giúp phát hiện lỗi hợp đồng; xóa nó có thể che khuất ý định sai mà không sửa nguyên nhân.

## 10. Các hiểu lầm cần tránh

- **“Abstract class không có logic.”** Sai: lớp abstract có thể cung cấp trạng thái, constructor và logic dùng chung.
- **“Không thể dùng abstract class làm kiểu biến.”** Sai: có thể dùng nó làm kiểu tham chiếu, chỉ không thể khởi tạo trực tiếp.
- **“Interface chỉ có phương thức abstract.”** Sai: interface hiện đại có thể có default, static và private method.
- **“Default method không thể bị override.”** Sai: lớp triển khai có thể cung cấp cách thực hiện riêng.
- **“Static method interface là phương thức instance được kế thừa.”** Sai: gọi bằng tên interface, không qua dispatch đa hình instance.
- **“Một lớp triển khai một interface con chỉ cần triển khai các phương thức khai báo ngay trong interface con.”** Sai: hợp đồng có thể được kế thừa từ interface cha và lớp abstract.
- **“Compiler chỉ kiểm tra cú pháp.”** Sai: compiler còn kiểm tra kiểu, hợp đồng phương thức, phạm vi truy cập và nhiều quy tắc ngôn ngữ khác.

## 11. Cách ghi nhớ

Abstract class phù hợp để chia sẻ trạng thái và hành vi giữa các lớp có quan hệ kế thừa; interface mô tả hợp đồng mà nhiều kiểu có thể đáp ứng. Cả hai đều hỗ trợ đa hình, nhưng có quy tắc khác nhau về constructor, trạng thái, phương thức mặc định và cách kết hợp kiểu.

Khi gặp một khẳng định về Java, hãy chuyển nó thành một câu hỏi có thể kiểm chứng: mã này có biên dịch không, phương thức nào được gọi lúc chạy, hoặc giá trị nào được in ra? Một ví dụ nhỏ, một dự đoán trước khi chạy và kết quả thực tế là cách tốt để phân biệt quy tắc ngôn ngữ với suy đoán.
