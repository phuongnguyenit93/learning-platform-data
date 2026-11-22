# Interface chuyên biệt hơn và phương thức được chọn trong Java

Khi một class implements nhiều interface, hoặc một interface con extends interface cha, có thể xuất hiện nhiều phương thức **cùng tên**. Java cần xác định phương thức nào được kế thừa, phương thức nào thực sự được gọi, và khi nào trình biên dịch buộc lập trình viên tự giải quyết xung đột. Những quy tắc này đặc biệt quan trọng với **default method** (từ Java 8), và vẫn áp dụng trong Java hiện đại.

Ba câu hỏi phải tách biệt:

1. **Kế thừa/ghi đè giữa các interface:** phương thức của interface chuyên biệt hơn (subinterface) đã override phương thức của superinterface chưa?
2. **Class hay interface cung cấp triển khai?** Nếu class có phương thức instance tương ứng, quy tắc ưu tiên phương thức của class được áp dụng; hai default methods không liên quan có thể xung đột.
3. **Chọn overload và dispatch:** khi tên phương thức có nhiều danh sách tham số, Java trước hết chọn *chữ ký thích hợp lúc biên dịch*, sau đó chọn *phần triển khai được gọi lúc chạy* nếu đó là phương thức instance có thể override.

Không nên gộp ba câu hỏi này thành một quy tắc mơ hồ như “Java luôn lấy method gần nhất”. Bài này trình bày cách suy luận, ví dụ đúng/sai, phương pháp thiết kế và một chương trình Java 17+ chạy độc lập.

## 1. Hiểu chính xác “interface chuyên biệt hơn”

Một interface là **subinterface** của interface khác khi nó trực tiếp hoặc gián tiếp `extends` interface đó. Ví dụ:

```java
interface Display {
    default String label() {
        return "Display";
    }
}

interface DetailedDisplay extends Display {
    @Override
    default String label() {
        return "Detailed";
    }
}
```

Đây là **đoạn định nghĩa minh họa**, không phải chương trình có `main`. `DetailedDisplay` chuyên biệt hơn `Display` vì `DetailedDisplay extends Display`. Method `DetailedDisplay.label()` **override** `Display.label()`, nên lời gọi thông qua đối tượng triển khai `DetailedDisplay` dùng hành vi chuyên biệt.

```java
class Card implements DetailedDisplay {}

Display view = new Card();
System.out.println(view.label()); // Detailed
```

Đây là **đoạn minh họa phụ thuộc vào hai interface phía trên**. Dù biến `view` mang kiểu khai báo `Display`, đối tượng thực tế là `Card`, triển khai `DetailedDisplay` nên phiên bản default bị override có hiệu lực.

**Điểm mấu chốt:** “chuyên biệt hơn” trong ngữ cảnh này là **quan hệ kế thừa kiểu**, không phải interface có nhiều phương thức hơn, tên dài hơn hoặc nằm phía sau trong danh sách `implements`.

## 2. Subinterface override default method: bản chuyên biệt được ưu tiên

Giả sử:

```java
interface RootPolicy {
    default String mode() {
        return "general";
    }
}

interface StrictPolicy extends RootPolicy {
    @Override
    default String mode() {
        return "strict";
    }
}

class Service implements RootPolicy, StrictPolicy {}
```

Đây là **định nghĩa minh họa**. Class `Service` cố tình liệt kê cả interface cha lẫn interface con; việc đó có thể thừa trong thiết kế API thật, nhưng cho thấy không có “bỏ phiếu” giữa hai default methods. `StrictPolicy.mode` override method của `RootPolicy`, nên chỉ hành vi `strict` có hiệu lực trên `Service`.

```java
Service service = new Service();
System.out.println(service.mode()); // strict

RootPolicy asRoot = service;
System.out.println(asRoot.mode());  // strict
```

Hai dòng đều in `strict`. **Cast sang kiểu interface cha không chọn lại body default của cha**: với một instance method có override, Java vẫn dùng triển khai phù hợp với đối tượng thực tế.

Nếu `StrictPolicy` **không khai báo lại** `mode` mà chỉ kế thừa nó, class vẫn nhận **một declaration được kế thừa** từ `RootPolicy`, chứ không tự động có hai phiên bản xung đột.

### Kế thừa hình thoi không đồng nghĩa xung đột

```java
interface Top {
    default String id() { return "top"; }
}

interface LeftPath extends Top {}
interface RightPath extends Top {}

class Diamond implements LeftPath, RightPath {}
```

Đây là đoạn minh họa. `Diamond` có hai *đường kế thừa* đến cùng khai báo `Top.id`, nhưng vẫn chỉ có một default implementation chung. `new Diamond().id()` trả `"top"`. **Hai đường dẫn đến cùng một declaration không phải hai default methods độc lập.**

Nếu một nhánh chuyên biệt, ví dụ `LeftPath`, override `id()` còn nhánh kia chỉ kế thừa `Top.id()`, method override tại nhánh chuyên biệt có thể loại phương thức cha bị override khỏi tập ứng viên kế thừa. Điều kiện là quan hệ override thực sự tồn tại theo chữ ký; không suy từ thứ tự liệt kê interface.

## 3. “Class wins”: phương thức của class ưu tiên default method của interface

Khi một superclass cung cấp **phương thức instance cụ thể, public và tương thích** với phương thức default của interface, hành vi từ class được ưu tiên:

```java
class BaseService {
    public String label() {
        return "class";
    }
}

interface HasLabel {
    default String label() {
        return "interface";
    }
}

class FinalService extends BaseService implements HasLabel {}
```

Đoạn minh họa trên hợp lệ. `new FinalService().label()` trả `"class"`, không phải `"interface"`. Class không cần override chỉ để viết lại cùng một method đã kế thừa.

**Phân biệt với mục 2:** mặc dù một subinterface có thể chuyên biệt hơn superinterface, quan hệ **class–interface** vẫn có ưu tiên riêng. Khi xác định method được gọi, không thể chỉ nhìn vào phần `implements` mà bỏ qua các instance methods đã khai báo hoặc kế thừa từ class.

Hai ghi nhớ khi áp dụng:

- Nếu class **tự override** method một cách phù hợp, bản override của class cũng được chọn và sẽ là điểm dispatch cho các lời gọi instance.
- Một method không `public` từ superclass không tự động thỏa hợp đồng `public` của interface; trình biên dịch vẫn kiểm tra khả năng truy cập và điều kiện override. Không áp dụng “class wins” mà bỏ qua visibility hoặc chữ ký.

## 4. Hai interface ngang hàng có default method giống nhau: phải giải quyết

Khi hai interface **không có quan hệ subinterface phù hợp** cùng cung cấp default methods có chữ ký trùng hoặc *override-equivalent*, Java không tự lựa chọn ngẫu nhiên:

```java
interface Alpha {
    default String label() { return "A"; }
}

interface Beta {
    default String label() { return "B"; }
}

// SAI: nếu không override label(), compiler báo xung đột.
// class InvalidService implements Alpha, Beta {}
```

Đây là ví dụ minh họa; dòng class sai đã comment. Trình biên dịch không dùng thứ tự `implements Alpha, Beta` để quyết định gọi `Alpha` hay `Beta`, kể cả cả hai tình cờ có body giống nhau.

**Cách sửa đúng** là class tự override và lựa chọn rõ ràng:

```java
class CombinedService implements Alpha, Beta {
    @Override
    public String label() {
        return Alpha.super.label() + "/" + Beta.super.label();
    }
}
```

Đoạn minh họa cần `Alpha` và `Beta` đã khai báo ở trên; `new CombinedService().label()` trả `"A/B"`. Cú pháp `Alpha.super.label()` chỉ định default implementation từ **direct superinterface** hợp lệ trong ngữ cảnh class. Đây **không** phải lời gọi động theo kiểu biến như `((Alpha) this).label()`; cast không giải quyết xung đột default hoặc cưỡng chế gọi body của cha.

Có thể định nghĩa hoàn toàn mới:

```java
class PreferredService implements Alpha, Beta {
    @Override
    public String label() {
        return "custom";
    }
}
```

Đây cũng là minh họa hợp lệ. Quan trọng là người viết code xác nhận lựa chọn và chịu trách nhiệm về hợp đồng của cả hai interface.

## 5. Một default method và một abstract method không liên quan

Có tình huống tinh vi hơn: một interface yêu cầu abstract method, interface khác cung cấp default method **cùng chữ ký**, nhưng hai interface không có quan hệ override với nhau:

```java
interface RequiredLabel {
    String label();
}

interface DefaultLabel {
    default String label() {
        return "default";
    }
}

// SAI: hai hợp đồng ngang hàng không tự động khớp ý nghĩa.
// interface Ambiguous extends RequiredLabel, DefaultLabel {}
```

Đây là ví dụ lỗi được comment. Trong một interface con kế thừa đồng thời hai declaration *override-equivalent*, một abstract và một default, JLS yêu cầu xác định rõ việc override thay vì tự nhận default là đúng hợp đồng abstract.

Một cách giải quyết ở interface con:

```java
interface ResolvedLabel extends RequiredLabel, DefaultLabel {
    @Override
    default String label() {
        return DefaultLabel.super.label();
    }
}
```

Đây là định nghĩa minh họa hợp lệ: `ResolvedLabel` chủ động override method và chọn hành vi của `DefaultLabel`. Với một **class** implement các interface ngang hàng này, có thể viết một override cụ thể phù hợp:

```java
class ResolvedLabelClass implements RequiredLabel, DefaultLabel {
    @Override
    public String label() {
        return DefaultLabel.super.label();
    }
}
```

Class cũng có thể tự tạo hành vi thay vì ủy quyền cho một default method. **Kết luận:** “có một default thì method abstract ở interface còn lại sẽ được tự động đáp ứng” là một giả định nguy hiểm. Hãy kiểm tra quan hệ override và giải quyết chủ động.

## 6. Interface con có thể làm default method trở lại abstract

Subinterface không nhất thiết giữ cách triển khai mặc định của superinterface. Nó có thể **khai báo lại** một default method thành abstract để yêu cầu class triển khai:

```java
interface OptionalLabel {
    default String label() {
        return "basic";
    }
}

interface ExplicitLabel extends OptionalLabel {
    @Override
    String label(); // trở lại abstract
}

class ExplicitCard implements ExplicitLabel {
    @Override
    public String label() {
        return "explicit";
    }
}
```

Đây là định nghĩa minh họa. `new ExplicitCard().label()` trả `"explicit"`. Nếu bỏ override ở class không abstract này, trình biên dịch báo lỗi vì `ExplicitLabel` đã yêu cầu cung cấp phần triển khai.

Khả năng này hữu ích khi **interface chuyên biệt muốn một hợp đồng chặt hơn**: superinterface có phương án chung, còn subinterface không chấp nhận phương án chung đó và buộc implementor quyết định.

Chú ý: dù khai báo lại abstract, **đây vẫn là override** của cùng signature trong hệ phân cấp, không tự động tạo một overload mới. Nếu interface có thêm các phương thức trừu tượng khác, việc nó có còn là functional interface hay không được quyết định bởi tập abstract methods theo quy tắc SAM, chứ không chỉ đếm số khai báo.

## 7. Interface con chỉ override đúng chữ ký, không “nuốt” các overload khác

**Overriding** và **overloading** là hai quan hệ khác nhau:

- *Override:* phương thức ở kiểu con ghi đè một declaration phù hợp theo quan hệ chữ ký (*subsignature*), kiểu trả về tương thích và các ràng buộc liên quan.
- *Overload:* nhiều phương thức có cùng tên nhưng **danh sách tham số khác nhau**. Chúng là các phương thức khác nhau, có thể cùng tồn tại.

Ví dụ:

```java
interface Formatter {
    default String render(Object value) {
        return "Object";
    }

    default String render(String value) {
        return "String";
    }
}

interface DetailedFormatter extends Formatter {
    @Override
    default String render(String value) {
        return "Detailed String";
    }
}
```

Đây là định nghĩa minh họa. `DetailedFormatter` **chỉ override** `render(String)`; nó vẫn kế thừa `render(Object)`. Không phải vì interface con có `render` mà toàn bộ các overload cùng tên đều biến mất.

Trong code:

```java
class Printer implements DetailedFormatter {}

Printer printer = new Printer();
String text = "Java";
Object obj = text;

System.out.println(printer.render(text)); // Detailed String
System.out.println(printer.render(obj));  // Object
```

Đây là đoạn minh họa phụ thuộc vào định nghĩa trên. Java chọn giữa `render(String)` và `render(Object)` dựa trên **kiểu tại thời điểm biên dịch của đối số**. Biến `obj` chứa một `String` thật, nhưng **kiểu khai báo là `Object`**, nên overload `render(Object)` được chọn ở bước compile-time.

## 8. Một lời gọi Java gồm hai bước: overload resolution và overriding dispatch

Khi gặp `object.method(argument)`, hãy suy luận theo thứ tự:

1. **Thời điểm biên dịch:** tìm các method có tên phù hợp và có thể truy cập; xác định những phương thức áp dụng được cho loại đối số, số lượng tham số, generic type inference, boxing/unboxing hoặc varargs nếu có. Từ đó chọn *most-specific applicable method* theo quy tắc overload resolution.
2. **Thời điểm chạy:** nếu phương thức được chọn là một instance method có thể override, JVM sử dụng triển khai thích hợp cho **kiểu thực tế của đối tượng nhận**. Default method thuộc interface có thể là implementation được kế thừa nếu không có override class hoặc phương thức chuyên biệt hơn.

Hai nghĩa của từ **“specific”** không đồng nhất:

| Ngữ cảnh | “Specific” nghĩa là gì? | Điều quyết định |
| --- | --- | --- |
| Chọn default giữa interface cha và interface con | Quan hệ kế thừa/override giữa các interface | Subinterface chuyên biệt hơn |
| Chọn overload `show(Object)` vs `show(String)` | Phương thức áp dụng được và cụ thể hơn theo kiểu tham số | Kiểu tĩnh của biểu thức đối số, quy tắc overload |
| Chọn body của instance method đã override | Triển khai tương ứng với đối tượng runtime | Dynamic method dispatch |
| Xung đột default của interface ngang hàng | Không có lựa chọn an toàn mặc định | Override tường minh |

### Ví dụ chọn overload theo kiểu tĩnh

```java
static String describe(Object value) { return "Object"; }
static String describe(CharSequence value) { return "CharSequence"; }
static String describe(String value) { return "String"; }

// Khi đặt bên trong một phương thức của class:
String s = "Java";
CharSequence cs = s;
Object o = s;

System.out.println(describe(s));  // String
System.out.println(describe(cs)); // CharSequence
System.out.println(describe(o));  // Object
```

Đây là đoạn minh họa có các method static và câu lệnh cần được đặt trong class/phương thức hợp lệ. **Cùng một object `"Java"`** nhưng ba kiểu tĩnh của tham số khác nhau dẫn tới **ba overload được chọn khác nhau**. Việc runtime object là `String` không khiến `describe(o)` tự chọn overload `describe(String)`.

### Ví dụ overriding dispatch

```java
interface Greeting {
    default String message() { return "hello"; }
}

interface WarmGreeting extends Greeting {
    @Override
    default String message() { return "hello again"; }
}

class Greeter implements WarmGreeting {}

Greeting g = new Greeter();
System.out.println(g.message()); // hello again
```

Đây là minh họa. Compiler đã xác định `Greeting.message()` là method tương ứng với lời gọi, nhưng body thực hiện là implementation được override trong `WarmGreeting`.

### null và overload có thể gây nhập nhằng

```java
static String pick(String value)  { return "string"; }
static String pick(Integer value) { return "integer"; }

// SAI: pick(null) nhập nhằng giữa hai overload không liên quan.
// ĐÚNG: cast nếu thực sự cần chỉ định overload.
String selected = pick((String) null);
```

Đây là ví dụ minh họa. `String` và `Integer` không có quan hệ subtype trực tiếp, nên không có một overload áp dụng được nào chuyên biệt hơn cái kia cho đối số `null`. Một cast rõ ràng hoặc API có tên khác giúp loại bỏ nhập nhằng. Không dùng quy tắc “interface nào chuyên biệt hơn” để suy ra kết quả overload trong tình huống này.

## 9. Class thắng default không đồng nghĩa static method tham gia cạnh tranh

Phương thức `static` trong interface không phải default method instance, và không được kế thừa như phương thức default. Ví dụ:

```java
interface Factory {
    static String id() {
        return "factory";
    }

    default String display() {
        return "display";
    }
}

interface DetailedFactory extends Factory {}

// ĐÚNG:
String key = Factory.id();

// SAI: DetailedFactory.id() (không được kế thừa static method).
// SAI: new SomeImplementation().id() (không gọi static interface method qua instance).
```

Đây là đoạn minh họa; các câu lệnh phải đặt trong ngữ cảnh hợp lệ. `Factory.id()` được truy cập thông qua tên interface khai báo nó. `DetailedFactory` kế thừa default method `display`, nhưng không tự động có static method `id`. Đừng nhầm **method hiding** của class static method với **override** của instance/default method.

Tương tự, **private methods của interface**, có từ Java 9, là helper nội bộ dùng trong thân interface; chúng không được kế thừa hoặc override như public default methods. Đừng đưa chúng vào cuộc phân giải một lời gọi public từ class triển khai.

## 10. Chữ ký, kiểu trả về và generics cũng phải hợp lệ

Hai phương thức **cùng tên** chưa đủ để trở thành override. Java kiểm tra chữ ký theo tham số, *subsignature* đối với phương thức generic và các điều kiện hợp lệ như return-type substitutability.

### Covariant return type

```java
interface Metric {
    Number value();
}

interface IntegerMetric extends Metric {
    @Override
    Integer value();
}

class CountMetric implements IntegerMetric {
    @Override
    public Integer value() {
        return 42;
    }
}
```

Đây là định nghĩa minh họa. `Integer` là subtype của `Number`, nên kiểu trả về **covariant** hợp lệ. `new CountMetric().value()` trả `Integer.valueOf(42)`. Một class hoặc interface không được tùy ý đổi kiểu trả về thành kiểu không tương thích khi override cùng chữ ký.

### Chỉ đổi kiểu trả về không tạo overload hợp lệ

```java
// SAI: cùng tên, cùng tham số, chỉ khác return type.
// interface Broken {
//     String read();
//     Integer read();
// }
```

Đây là minh họa về lỗi compile-time. Overload dựa trên **danh sách tham số**, không phân biệt chỉ theo kiểu trả về.

### Generic erasure có thể gây name clash

```java
// SAI: hai method có cùng erasure List sau khi xóa tham số kiểu.
// interface Broken {
//     void handle(java.util.List<String> names);
//     void handle(java.util.List<Integer> ids);
// }
```

Đây là ví dụ minh họa. Java generic sử dụng type erasure; hai overload khác nhau chỉ bởi type argument như `List<String>` và `List<Integer>` không thể tồn tại với cùng chữ ký đã xóa. Khi thiết kế API có nhiều interface generic, xem xét cả erasure và return type trước khi giả định các phương thức sẽ kế thừa/override “tự nhiên”.

## 11. Chương trình Java 17+ hoàn chỉnh

Chương trình sau minh họa tất cả tình huống chính trong một file: subinterface override default, gọi qua interface cha, **class wins**, hai default methods ngang hàng được giải quyết tường minh, subinterface biến default thành abstract, và overload resolution dựa trên kiểu tĩnh.

Lưu thành **InterfaceSpecificityDemo.java**:

```java
public class InterfaceSpecificityDemo {

    interface Label {
        default String label() {
            return "root";
        }
    }

    interface DetailedLabel extends Label {
        @Override
        default String label() {
            return "specific";
        }
    }

    static final class DetailedService
            implements Label, DetailedLabel {
    }

    static class ParentService {
        public String label() {
            return "class";
        }
    }

    interface HasLabel {
        default String label() {
            return "interface";
        }
    }

    static final class ClassPreferred
            extends ParentService implements HasLabel {
    }

    interface Left {
        default String action() {
            return "L";
        }
    }

    interface Right {
        default String action() {
            return "R";
        }
    }

    static final class Resolved implements Left, Right {
        @Override
        public String action() {
            return Left.super.action() + "/" + Right.super.action();
        }
    }

    interface Header {
        default String title() {
            return "header";
        }
    }

    interface StrictHeader extends Header {
        @Override
        String title(); // re-abstract default method
    }

    static final class StrictService implements StrictHeader {
        @Override
        public String title() {
            return "required";
        }
    }

    static String choose(Object value) {
        return "Object";
    }

    static String choose(CharSequence value) {
        return "CharSequence";
    }

    static String choose(String value) {
        return "String";
    }

    public static void main(String[] args) {
        DetailedService detailed = new DetailedService();
        Label asParent = detailed;

        System.out.println("direct: " + detailed.label());
        System.out.println("via parent: " + asParent.label());
        System.out.println("class wins: " +
                new ClassPreferred().label());
        System.out.println("conflict resolved: " +
                new Resolved().action());
        System.out.println("reabstracted: " +
                new StrictService().title());

        String text = "Java";
        CharSequence sequence = text;
        Object object = text;

        System.out.println("overload String: " + choose(text));
        System.out.println("overload CharSequence: " +
                choose(sequence));
        System.out.println("overload Object: " + choose(object));
    }
}
```

Biên dịch/chạy với JDK 17 trở lên:

```bash
javac InterfaceSpecificityDemo.java
java InterfaceSpecificityDemo
```

**Kết quả chuẩn:**

```text
direct: specific
via parent: specific
class wins: class
conflict resolved: L/R
reabstracted: required
overload String: String
overload CharSequence: CharSequence
overload Object: Object
```

**Giải thích:**

1. `DetailedLabel extends Label` và override `label`, nên `DetailedService` dùng `specific`, kể cả khi biến tham chiếu được khai báo là `Label`.
2. `ClassPreferred` kế thừa `ParentService.label`; phương thức class có hiệu lực thay vì default method của `HasLabel`.
3. `Resolved` nhận hai default methods từ `Left` và `Right` ngang hàng, vì vậy **phải override**; nó chỉ định cả hai qua `Left.super.action()`/`Right.super.action()`.
4. `StrictHeader` biến default `Header.title` trở lại abstract, buộc `StrictService` cung cấp triển khai, do đó in `required`.
5. Ba lời gọi `choose` nhận cùng object `String` nhưng biến tham số mang ba kiểu tĩnh khác nhau: `String`, `CharSequence` và `Object`. Đó là **overloading**, không phải lựa chọn default method theo interface chuyên biệt hơn.

## 12. Lỗi phổ biến và cách giải quyết

| Lỗi nhận định hoặc cách viết | Vấn đề | Cách xử lý |
| --- | --- | --- |
| “Interface xuất hiện sau `implements` sẽ thắng” | Thứ tự liệt kê không giải quyết conflict | Kiểm tra quan hệ extends/override; override tường minh nếu độc lập |
| “Cast sang interface cha để gọi body default cha” | Dynamic dispatch vẫn chọn override thực tế | Thiết kế method ủy quyền rõ ràng; dùng `Interface.super` trong ngữ cảnh hợp lệ |
| “Hai default methods giống body thì Java chấp nhận” | Xung đột là về declarations, không phải so sánh body | Viết override |
| “Default method sẽ tự đáp ứng abstract method từ interface ngang hàng” | Java không giả định hợp đồng hai interface tương thích | Chọn hành vi bằng overriding declaration |
| “Method của class bị default method interface ghi đè” | Trái quy tắc ưu tiên class | Xem instance method của class/superclass |
| “Subinterface override `format(String)` thì mất `format(Object)`” | Override theo signature, không theo tên | Kiểm tra từng overload |
| “Runtime object là `String` nên luôn chọn `f(String)`” | Overload resolution chọn bằng kiểu tĩnh | Đọc kiểu khai báo đối số và applicability |
| “Interface static method được kế thừa như default” | Static interface method không kế thừa như default | Gọi bằng tên interface khai báo |
| “Chỉ khác return type là hai overload” | Java không phân biệt overload chỉ theo return type | Đổi danh sách tham số hoặc tên method |
| “Hai overload `List<String>` và `List<Integer>` hợp lệ” | Erasure gây name clash | Thiết kế API có tên khác hoặc mô hình kiểu khác |

### Quy trình gỡ một lỗi xung đột interface

1. Ghi lại **chữ ký đầy đủ** của phương thức: tên, tham số, generic type/erasure, return type, visibility.
2. Vẽ quan hệ kiểu: interface nào **extends** interface nào; class **extends** superclass nào và **implements** interface nào.
3. Với cùng signature, kiểm tra liệu subinterface **đã override** method của superinterface hay không.
4. Tìm method instance tương ứng trong class/superclass; nếu có, kiểm tra hợp đồng truy cập và ưu tiên class.
5. Nếu có hai declaration default ngang hàng (hoặc default–abstract không liên quan), bổ sung override chủ động và quyết định hành vi.
6. Nếu có nhiều **tham số** khác nhau, giải quyết overload bằng kiểu tĩnh tại call site, đừng nhầm với conflict default.
7. Biên dịch thử bằng một ví dụ tối giản; bổ sung test trường hợp biến tham chiếu kiểu cha, kiểu con, nhiều overload và `null` khi cần.

## 13. Ứng dụng trong thiết kế API hiện đại

### Mở rộng interface công khai bằng default method

Default methods giúp thêm hành vi dùng chung mà không bắt mọi class implement ngay, nhưng cũng có thể phát sinh xung đột khi một class hiện thực nhiều interface. Trước khi thêm default method cho một thư viện, cần kiểm tra tên/chữ ký tương ứng trong các interface khác mà consumer của thư viện thường dùng.

Một cách giảm rủi ro là đặt **tên có nghĩa nghiệp vụ** thay vì những tên quá chung như `process()`, `handle()`. Dù có thể giải quyết conflict bằng overriding, API dễ hiểu hơn khi người dùng không phải biết nhiều quy tắc chọn method cho thao tác thông thường.

### Đặt phương thức override ở nơi biểu đạt quyết định

Khi hai interface đại diện cho hai chính sách khác nhau, đừng chỉ định một interface thắng vì nó “đứng gần” trong source code. Hãy viết override trong class triển khai hoặc interface tổng hợp để giải thích lý do chọn, và test contract của cả hai. Một helper `default` có thể được gọi bằng `InterfaceName.super.method()` khi ngữ cảnh cho phép; đây là lựa chọn **tường minh**, không phải dispatch ngẫu nhiên.

### Functional interface có default methods

Một interface vẫn có thể là functional interface khi chỉ có **một abstract method chức năng** dù còn có nhiều default methods. Subinterface override default method để chuyên biệt hóa hành vi phụ trợ **không tự làm mất khả năng dùng lambda**, miễn các điều kiện SAM vẫn đúng:

```java
@FunctionalInterface
interface Rule {
    boolean test(String input);

    default String description() {
        return "general rule";
    }
}

@FunctionalInterface
interface NamedRule extends Rule {
    @Override
    default String description() {
        return "named rule";
    }
}

NamedRule rule = value -> value != null && !value.isEmpty();
System.out.println(rule.description()); // named rule
```

Đây là **đoạn minh họa**, yêu cầu đặt interface và câu lệnh ở vị trí hợp lệ trong tệp. Việc `NamedRule` chuyên biệt hóa `description` là hợp lệ; phương thức chức năng vẫn là `test`. Nếu subinterface thêm một abstract method độc lập, nó có thể không còn functional, nên `@FunctionalInterface` giúp trình biên dịch kiểm tra ý định.

## 14. Bài tập có đáp án định hướng

**Bài 1 — interface con và interface cha.** Cho `A` có `default String name(){return "A";}` và `B extends A` override trả `"B"`. Class `C implements B`. Với `A x = new C();`, `x.name()` trả gì? **Đáp án:** `"B"` vì `B.name` override `A.name` và dynamic dispatch dùng implementation của đối tượng.

**Bài 2 — hai đường đến một declaration.** `Root` khai báo `default ping`, `Left extends Root`, `Right extends Root`, class `Both implements Left,Right`. Có cần override không? **Đáp án:** không, nếu hai nhánh chỉ kế thừa cùng declaration `Root.ping`.

**Bài 3 — hai default độc lập.** `Left` và `Right` riêng biệt đều khai báo `default ping()`. Class implements cả hai nhưng không override. Có biên dịch không? **Đáp án:** không. Viết một override có thể gọi `Left.super.ping()` hoặc `Right.super.ping()` trong class khi điều kiện gọi hợp lệ.

**Bài 4 — class wins.** `Parent` có `public String id(){return "P";}`, interface `Named` có `default String id(){return "I";}`, class `Child extends Parent implements Named`. Kết quả? **Đáp án:** `"P"`.

**Bài 5 — phân biệt overload.** Có `show(Object)` và `show(String)`. Biến `Object x = "hello";`; `show(x)` gọi method nào? **Đáp án:** `show(Object)` vì overload được chọn bằng kiểu tĩnh `Object`. Gán vào `String s` sẽ chọn `show(String)`.

**Bài 6 — re-abstract.** `Base` có default `String label()`, `Strict extends Base` khai báo `String label();` không body. Class implements `Strict` phải làm gì? **Đáp án:** định nghĩa triển khai `public String label()` phù hợp hoặc là abstract class.

**Bài 7 — generic erasure.** Có thể viết cùng lúc hai method `accept(List<String>)` và `accept(List<Integer>)` trong một interface không? **Đáp án:** không; erasure khiến hai chữ ký trùng nhau. Đổi tên hoặc thiết kế lại hợp đồng.

## 15. Ghi nhớ nhanh

- **Interface con override method của cha** ⇒ method chuyên biệt hơn có hiệu lực; cast sang cha không ép gọi body cha.
- **Superclass/class có instance method tương ứng** ⇒ triển khai class được ưu tiên hơn default method interface, với các điều kiện override và visibility hợp lệ.
- **Hai default methods độc lập cùng chữ ký** ⇒ không tự chọn; override tường minh.
- **Default + abstract từ các interface không liên quan** ⇒ đừng giả định tự tương thích; khai báo override để khẳng định lựa chọn.
- **Đường kế thừa hình thoi tới cùng một method** ⇒ không tự tạo conflict.
- **Overload chọn lúc biên dịch; override dispatch lúc chạy** ⇒ cần biết kiểu tĩnh của tham số và kiểu thực tế của receiver.
- **Static/private interface methods** không tham gia lựa chọn default như public instance methods.
- Các quy tắc nêu trên được định nghĩa bởi JLS và vẫn áp dụng với Java 17+ cùng các JDK hiện đại.

### Tài liệu chuẩn

- [JLS `9.4.1 — Interface Method Inheritance and Overriding](https://docs.oracle.com/javase/specs/jls/se25/html/jls-9.html#jls-9.4.1)
- [JLS `9.4.1.3 — Inheriting Methods with Override-Equivalent Signatures](https://docs.oracle.com/javase/specs/jls/se25/html/jls-9.html#jls-9.4.1.3)
- [JLS `8.4.8 — Inheritance, Overriding, and Hiding](https://docs.oracle.com/javase/specs/jls/se25/html/jls-8.html#jls-8.4.8)
- [JLS `15.12 — Method Invocation Expressions and Overload Resolution](https://docs.oracle.com/javase/specs/jls/se25/html/jls-15.html#jls-15.12)
- [JLS `9.8 — Functional Interfaces](https://docs.oracle.com/javase/specs/jls/se25/html/jls-9.html#jls-9.8)
