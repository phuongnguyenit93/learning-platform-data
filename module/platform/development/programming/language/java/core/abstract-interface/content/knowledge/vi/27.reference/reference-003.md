# Bảng quy tắc ưu tiên và xử lý xung đột phương thức trong Java

## Mục tiêu

Khi Java tìm một phương thức, có hai câu hỏi cần tách riêng: trình biên dịch chọn **chữ ký nào** trong các overload có thể gọi, và khi chương trình chạy thì **phần triển khai nào** được thực thi do kế thừa hoặc ghi đè. Với interface, còn cần xử lý các phương thức `default` được kế thừa từ nhiều interface.

Bài này tổng hợp quy tắc ưu tiên thường gặp, cách đọc lỗi biên dịch do xung đột và cách giải quyết rõ ràng trong Java 17+.

## 1. Phân biệt overload, override và default method

- **Overload (nạp chồng):** nhiều phương thức cùng tên nhưng khác danh sách tham số. Trình biên dịch chọn overload phù hợp dựa trên kiểu khai báo của biểu thức và các quy tắc chuyển đổi kiểu.
- **Override (ghi đè):** lớp con cung cấp cách triển khai cho phương thức instance có thể ghi đè được của lớp cha hoặc interface. Khi gọi qua một tham chiếu, triển khai được chọn theo kiểu thực tế của đối tượng tại thời gian chạy.
- **Default method:** phương thức instance có phần thân được khai báo trong interface bằng từ khóa `default`. Lớp triển khai có thể kế thừa phương thức này nếu không có quy tắc ưu tiên hoặc xung đột buộc lớp phải cung cấp triển khai khác.
- **Phương thức abstract:** khai báo hợp đồng mà không có phần thân. Một lớp cụ thể phải đáp ứng tất cả phương thức abstract còn thiếu; một lớp abstract có thể tiếp tục để lại chúng cho lớp con.

Các khái niệm này phối hợp với nhau nhưng không thay thế nhau. Java trước hết phải xác định lời gọi phù hợp theo kiểu và chữ ký ở thời điểm biên dịch; sau đó, với phương thức instance có tính đa hình, JVM gọi triển khai override thích hợp trên đối tượng thực tế.

## 2. Bảng quy tắc ưu tiên khi kế thừa phương thức

| Tình huống | Quy tắc | Cách xử lý |
|---|---|---|
| Lớp có phương thức instance phù hợp | Phương thức của lớp được ưu tiên so với default method của interface | Dùng phương thức lớp; override trong lớp nếu cần hành vi khác |
| Lớp cha có phương thức instance phù hợp | Phương thức kế thừa từ lớp cha thắng default method của interface | Không cần triển khai lại nếu phương thức lớp cha đáp ứng hợp đồng |
| Lớp cha khai báo phương thức abstract cùng chữ ký | Khai báo trong hệ thống lớp vẫn có hiệu lực; default của interface không tự thay thế hợp đồng abstract đó | Lớp cụ thể phải override và cung cấp thân phương thức |
| Interface con ghi đè default của interface cha | Default từ interface con cụ thể hơn được chọn | Kế thừa default của interface con hoặc override trong lớp |
| Hai interface không có quan hệ cha con cùng cung cấp default trùng chữ ký | Không có default nào tự động thắng interface còn lại | Lớp triển khai phải override và giải quyết xung đột |
| Nhiều interface chỉ khai báo cùng một phương thức abstract với kiểu trả về tương thích | Một triển khai phù hợp có thể đáp ứng tất cả hợp đồng đó | Cung cấp một phương thức công khai |
| Một default và một abstract cùng chữ ký từ hai interface độc lập | Lớp triển khai không tự động chọn default; compiler yêu cầu lớp giải quyết xung đột | Override bằng phương thức public tương thích; nếu phù hợp, gọi default qua `InterfaceName.super.method()` |
| Phương thức static của interface | Không được kế thừa và override như phương thức instance | Gọi bằng tên interface, ví dụ `SomeInterface.utility()` |

Bảng này nói về phương thức instance và hợp đồng Java. Chữ ký phải tương thích, mức truy cập không được giảm khi override, và kiểu trả về phải đáp ứng quy tắc override của Java. Nếu hai khai báo cùng tên và tham số có kiểu trả về không tương thích, không thể khắc phục chỉ bằng cách chọn một default; thiết kế phải được thay đổi để các hợp đồng tương thích.

## 3. Quy tắc chọn overload khi biên dịch

Với các phương thức overload cùng tên, Java chọn phương thức áp dụng được theo các giai đoạn của lời gọi phương thức:

1. **Chuyển đổi invocation nghiêm ngặt:** xét các chuyển đổi như khớp kiểu và widening primitive/reference, chưa dùng boxing hoặc unboxing.
2. **Chuyển đổi invocation linh hoạt:** nếu giai đoạn trước không có phương thức phù hợp, xét thêm các chuyển đổi cho phép boxing/unboxing.
3. **Varargs:** nếu vẫn chưa tìm được phương thức phù hợp, xét các phương thức có tham số biến độ dài.

Java chọn phương thức phù hợp cụ thể nhất trong giai đoạn đầu tiên có ứng viên hợp lệ. Đây là lý do một overload nhận kiểu tham chiếu rộng hơn có thể được chọn trước một overload cần boxing, tùy kiểu đối số và chữ ký. Nếu không có phương thức phù hợp hoặc có nhiều lựa chọn không thể phân định là cụ thể nhất, lời gọi bị lỗi biên dịch.

Ví dụ, nếu có `print(Object)` và `print(String)`, lời gọi `print("hi")` chọn `print(String)` vì `String` cụ thể hơn `Object`. Nếu có `print(String)` và `print(Integer)`, lời gọi `print(null)` mơ hồ vì cả hai kiểu tham chiếu đều nhận được `null` và không kiểu nào cụ thể hơn kiểu còn lại. Có thể giải quyết bằng cách ép kiểu rõ ràng, chẳng hạn `print((String) null)`, nếu đúng với ý định.

Overload được chọn ở thời điểm biên dịch theo kiểu biểu thức. Override của phương thức instance sau đó được phân giải theo đối tượng thực tế. Vì vậy, biến tham chiếu có kiểu lớp cha vẫn có thể gọi triển khai override trong lớp con, nhưng không thể gọi một overload chỉ tồn tại ở lớp con nếu overload đó không khả dụng qua kiểu khai báo của biến.

## 4. Xử lý xung đột default giữa các interface

Giả sử hai interface độc lập đều định nghĩa `default String route()`. Một lớp triển khai cả hai sẽ không thể để trình biên dịch tự chọn một cách tùy ý. Lớp phải override `route()`. Bên trong phương thức override, có thể gọi trực tiếp default của một interface cha trực tiếp bằng cú pháp `InterfaceName.super.method()`.

Ví dụ:

~~~java
interface FastRoute {
    default String route() {
        return "fast";
    }
}

interface SafeRoute {
    default String route() {
        return "safe";
    }
}

class ChosenRoute implements FastRoute, SafeRoute {
    @Override
    public String route() {
        return FastRoute.super.route() + "+" + SafeRoute.super.route();
    }
}
~~~

`ChosenRoute` định nghĩa hành vi rõ ràng bằng cách kết hợp hai default. Nếu chỉ muốn dùng một trong hai, phần thân có thể trả về `FastRoute.super.route()` hoặc `SafeRoute.super.route()`. Việc gọi qua `InterfaceName.super` chỉ hợp lệ trong ngữ cảnh kế thừa interface thích hợp; tên interface được dùng phải là interface trực tiếp mà lớp triển khai.

Nếu interface con mở rộng interface cha và cung cấp default cùng chữ ký, default ở interface con là phương thức cụ thể hơn. Nếu interface con chủ động khai báo lại phương thức đó dưới dạng abstract, nó có thể loại bỏ default kế thừa khỏi hợp đồng của interface con; lớp cụ thể triển khai interface con phải cung cấp phần thân phương thức.

### Default và abstract từ hai interface khác nhau

Không được áp dụng quy tắc “default luôn đáp ứng abstract” cho hai interface **độc lập**. Trong ví dụ sau, `NameResolver` phải tự override `label()` dù `DefaultName` đã có thân phương thức:

~~~java
interface AbstractName {
    String label();
}

interface DefaultName {
    default String label() {
        return "default";
    }
}

class NameResolver implements AbstractName, DefaultName {
    @Override
    public String label() {
        return DefaultName.super.label();
    }
}
~~~

Nếu bỏ override khỏi `NameResolver`, mã sẽ không biên dịch vì không giải quyết được phương thức trùng chữ ký. Trường hợp khác là **interface con** cung cấp default để override một khai báo abstract kế thừa; khi đó lớp cụ thể có thể dùng default đó:

~~~java
interface BaseName {
    String label();
}

interface ChildName extends BaseName {
    @Override
    default String label() {
        return "child";
    }
}

class UsesChildName implements ChildName {
}
~~~

Phân biệt quan hệ kế thừa của các interface trước khi kết luận rằng một default method đã đáp ứng hợp đồng abstract.

## 5. Phương thức abstract trùng nhau và kiểu trả về

Hai interface có thể khai báo cùng một phương thức abstract. Nếu chữ ký và kiểu trả về tương thích, một phương thức public trong lớp có thể triển khai cả hai hợp đồng:

~~~java
interface HasCode {
    String code();
}

interface HasIdentifier {
    String code();
}

class RecordCode implements HasCode, HasIdentifier {
    @Override
    public String code() {
        return "C-17";
    }
}
~~~

Không cần viết hai phương thức chỉ vì có hai interface. Khi gọi qua biến kiểu `HasCode` hoặc `HasIdentifier`, cả hai lời gọi đều chạy cùng triển khai `RecordCode.code()`.

Kiểu trả về cần được xem xét cẩn thận. Với phương thức instance override, kiểu trả về nguyên thủy phải khớp; kiểu tham chiếu có thể dùng kiểu con tương thích theo quy tắc covariant return. Nếu hai interface đòi hỏi kiểu trả về không thể cùng đáp ứng, lớp không thể tạo ra một triển khai hợp lệ bằng cách khai báo hai phương thức chỉ khác kiểu trả về, vì kiểu trả về không tạo thành overload riêng.

## 6. Ví dụ hoàn chỉnh chạy bằng Java 17+

Ví dụ sau minh họa bốn quy tắc: phương thức lớp cha ưu tiên default của interface; default của interface con ưu tiên default từ cha; xung đột giữa hai default độc lập phải được giải quyết; và một triển khai có thể đáp ứng hai hợp đồng abstract. Cuối cùng, ví dụ overload/override cho thấy sự khác nhau giữa lựa chọn ở thời điểm biên dịch và gọi triển khai lúc chạy.

Lưu toàn bộ mã vào `Main.java`:

~~~java
interface Named {
    default String label() {
        return "interface";
    }
}

class BaseLabel {
    public String label() {
        return "class";
    }
}

class ClassWins extends BaseLabel implements Named {
}

interface GeneralMode {
    default String mode() {
        return "general";
    }
}

interface SpecificMode extends GeneralMode {
    @Override
    default String mode() {
        return "specific";
    }
}

class MostSpecificWins implements SpecificMode {
}

interface FastRoute {
    default String route() {
        return "fast";
    }
}

interface SafeRoute {
    default String route() {
        return "safe";
    }
}

class ChosenRoute implements FastRoute, SafeRoute {
    @Override
    public String route() {
        return FastRoute.super.route() + "+" + SafeRoute.super.route();
    }
}

interface HasCode {
    String code();
}

interface HasIdentifier {
    String code();
}

class RecordCode implements HasCode, HasIdentifier {
    @Override
    public String code() {
        return "C-17";
    }
}

class Formatter {
    String show(Object value) {
        return "Object";
    }

    String show(String value) {
        return "String";
    }
}

class CustomFormatter extends Formatter {
    @Override
    String show(String value) {
        return "CustomString";
    }
}

public class Main {
    public static void main(String[] args) {
        System.out.println(new ClassWins().label());
        System.out.println(new MostSpecificWins().mode());
        System.out.println(new ChosenRoute().route());

        RecordCode record = new RecordCode();
        HasCode codeView = record;
        HasIdentifier idView = record;
        System.out.println(codeView.code());
        System.out.println(idView.code());

        Formatter formatter = new CustomFormatter();
        System.out.println(formatter.show("hello"));
        System.out.println(formatter.show((Object) "hello"));
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~text
javac Main.java
java Main
~~~

Đầu ra chuẩn chính xác:

~~~text
class
specific
fast+safe
C-17
C-17
CustomString
Object
~~~

Giải thích kết quả:

1. `ClassWins.label()` kế thừa phương thức public từ `BaseLabel`; phương thức đó được ưu tiên so với default `Named.label()`.
2. `MostSpecificWins.mode()` dùng default `SpecificMode.mode()`, vì interface này mở rộng và ghi đè default của `GeneralMode`.
3. `ChosenRoute.route()` giải quyết xung đột bằng cách gọi tường minh cả hai default.
4. `RecordCode.code()` đáp ứng hai interface có cùng hợp đồng abstract, nên hai biến interface đều in `C-17`.
5. Với `formatter.show("hello")`, kiểu đối số là `String`, nên trình biên dịch chọn overload `show(String)`. Đối tượng thực tế là `CustomFormatter`, vì vậy triển khai override in `CustomString`.
6. Với `formatter.show((Object) "hello")`, kiểu biểu thức đối số là `Object`, nên overload `show(Object)` được chọn. `CustomFormatter` không override overload này, do đó phương thức kế thừa in `Object`.

## 7. Các trường hợp dễ nhầm

- **Nghĩ rằng interface nào được liệt kê trước trong `implements` sẽ thắng:** thứ tự liệt kê không quyết định cách chọn default. Xung đột giữa các default độc lập phải được giải quyết bằng override.
- **Nghĩ rằng mọi phương thức cùng tên đều là overload:** overload yêu cầu danh sách tham số khác nhau. Override thay thế triển khai của một phương thức kế thừa có chữ ký tương thích.
- **Nghĩ rằng kiểu thực tế của đối tượng quyết định overload:** kiểu thực tế quyết định triển khai override; overload được chọn dựa trên kiểu biểu thức và các phương thức có thể truy cập tại thời điểm biên dịch.
- **Quên default ở interface con:** default cụ thể hơn trong interface con thắng default kế thừa từ interface cha.
- **Cho rằng default luôn thay thế phương thức abstract của lớp cha:** một khai báo abstract được kế thừa từ lớp cha vẫn có thể buộc lớp cụ thể phải triển khai phương thức đó.
- **Cố dùng kiểu trả về để tạo overload:** các phương thức chỉ khác kiểu trả về không tạo thành overload hợp lệ.
- **Gọi static method qua đối tượng như thể đó là dispatch đa hình:** static method của interface cần được gọi qua tên interface và không tham gia cơ chế override instance.

## 8. Quy trình chẩn đoán khi gặp lỗi biên dịch

1. Xác định lời gọi đang vướng overload, override, default inheritance hay hợp đồng abstract.
2. Ghi lại kiểu khai báo của biến nhận lời gọi và kiểu của từng đối số; dùng chúng để kiểm tra overload có thể áp dụng.
3. Kiểm tra lớp cha trước, rồi xem các interface có cung cấp default cùng chữ ký hay không.
4. Với nhiều default, kiểm tra quan hệ cha con giữa các interface. Nếu các default cạnh tranh đến từ những interface độc lập, override và chọn hành vi mong muốn.
5. Kiểm tra mức truy cập, kiểu trả về, tham số và checked exception của phương thức override.
6. Biên dịch lại và chạy ví dụ tối thiểu để xác nhận kết quả. Khi cần, ép kiểu đối số tường minh để phân biệt overload nào đang được chọn.

## Ghi nhớ

Overload được phân giải ở thời điểm biên dịch; override được chọn theo đối tượng thực tế khi chạy. Trong kế thừa, phương thức instance từ hệ thống lớp được ưu tiên so với default của interface; default ở interface con thắng default từ cha; các default độc lập có cùng chữ ký cần được lớp triển khai giải quyết rõ ràng. Những hợp đồng abstract trùng nhau có thể dùng chung một triển khai nếu chữ ký và kiểu trả về tương thích.