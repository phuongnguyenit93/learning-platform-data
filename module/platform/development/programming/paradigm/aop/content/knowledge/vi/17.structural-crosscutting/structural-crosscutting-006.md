# Quan hệ giữa mở rộng cấu trúc, mixin và kế thừa trong AOP

> **Phạm vi:** Kiến thức lập trình hướng khía cạnh (Aspect-Oriented Programming — AOP) từ cơ bản đến nâng cao. Bài làm rõ ba khái niệm dễ bị gọi thay thế nhau: **mở rộng cấu trúc (structural extension / introduction)**, **mixin** và **kế thừa (inheritance)**; đồng thời phân biệt với composition, delegation, interface default methods và proxy. Khả năng thêm interface, method, field hoặc quan hệ cha vào lớp đã có phụ thuộc mô hình ngôn ngữ/công cụ AOP. Các ví dụ Java 17 minh họa nguyên lý và giới hạn, không phải cú pháp một bộ dệt AOP cụ thể.

## 1. Tại sao cần phân biệt ba khái niệm?

Một lớp nghiệp vụ ban đầu chỉ cung cấp các thao tác cốt lõi:

~~~text
Order
  - code
  + code()
  + calculateTotal()
~~~

Sau đó hệ thống muốn các Order có thể được gắn nhãn, ghi thông tin truy vết hoặc tham gia một hợp đồng mới. Có ít nhất ba hướng thiết kế:

1. **Kế thừa:** định nghĩa một kiểu con mở rộng kiểu cha đã có.
2. **Mixin:** tái sử dụng một nhóm hành vi giữa các kiểu khác nhau, thường không muốn ép chúng vào một nhánh phân cấp chung.
3. **Mở rộng cấu trúc bằng AOP:** dùng cơ chế introduction/inter-type declaration tương ứng để khai báo thêm thành viên hoặc quan hệ kiểu cho những lớp đích từ bên ngoài phần khai báo ban đầu.

Ba hướng có thể cho cảm giác giống nhau ở điểm cuối cùng: object có thêm một API hoặc hành vi. Nhưng **chúng khác nhau về nguồn khai báo, cơ chế áp dụng, danh tính kiểu, thứ tự phân giải method và vòng đời trạng thái**.

Câu hỏi thiết kế không phải “cách nào thêm được method?” mà là: *Ai sở hữu hợp đồng mới? Object gốc có thật sự trở thành thành viên của interface đó không? Hành vi được cài ở đâu? Điều gì xảy ra khi kế thừa và các extension xung đột?*

## 2. Ba định nghĩa cốt lõi

### 2.1. Kế thừa

**Inheritance** là quan hệ giữa kiểu con và kiểu cha được ngôn ngữ/hệ kiểu định nghĩa. Trong Java, một class có thể extends một class cha trực tiếp và có thể implements nhiều interface theo luật ngôn ngữ.

Kế thừa có thể đem lại:

- Hành vi được thừa hưởng từ superclass.
- Override method theo quy tắc dynamic dispatch.
- Khả năng dùng subtype ở nơi yêu cầu supertype khi hợp đồng phù hợp.
- Trạng thái instance từ superclass và quan hệ khởi tạo tương ứng.

Kế thừa không đồng nghĩa “mọi object sẽ tự nhận code mới khi ta khai báo một class con”. Một instance vốn thuộc class gốc không tự chuyển thành instance của class con mới.

### 2.2. Mixin

**Mixin** là ý tưởng tái sử dụng một phần chức năng giữa nhiều kiểu, chẳng hạn nhóm method gắn nhãn, kiểm toán hoặc định dạng, mà không nhất thiết mô tả một quan hệ “là một” của domain.

Mixin có nhiều cách hiện thực tùy ngôn ngữ:

- Trait hoặc module có method dùng lại.
- Interface cùng default methods khi khả năng ngôn ngữ cho phép.
- Delegate object cung cấp hành vi.
- Một đối tượng triển khai interface và chia sẻ logic bằng composition.
- Structural introduction kết hợp interface với một implementation/delegate trong hệ AOP có hỗ trợ.

**Mixin là mẫu tổ chức/tái sử dụng hành vi**, không mặc định là một cú pháp, cũng không mặc định tạo superclass mới.

### 2.3. Mở rộng cấu trúc trong AOP

**Structural extension** là việc thay đổi **cấu trúc nhìn thấy được của một kiểu hoặc đối tượng qua hệ thống can thiệp**, thay vì chỉ chạy advice trước/sau/bao quanh lời gọi.

Một cơ chế introduction có thể, tùy công cụ:

- Làm một lớp đích thực hiện thêm interface.
- Cung cấp một hoặc nhiều method được giới thiệu.
- Cung cấp trạng thái bổ sung hoặc delegate cho hành vi mới.
- Thêm quan hệ kiểu cha/con trong giới hạn được cơ chế hỗ trợ.
- Thay cách các công cụ compile/weave nhìn thấy các thành viên được bổ sung.

Không được mặc định rằng mọi engine AOP có đủ tất cả khả năng này. Một engine chỉ có runtime interception cũng có thể **không hỗ trợ structural changes**.

## 3. AOP hành vi và AOP cấu trúc khác nhau

**Behavioral advice** bổ sung hành vi tại join point:

~~~text
Caller -> Before/around/after advice -> Original method
~~~

Cấu trúc method và interface mà caller thấy có thể vẫn giữ nguyên. Ví dụ logging trước pay không có nghĩa đối tượng PaymentService tự implements Loggable.

**Structural introduction** hướng đến một thay đổi dạng:

~~~text
Before:
  class Order { code(); }

After introduction (conceptually):
  Order also supports interface Taggable
  + addTag(String)
  + tags()
~~~

Một advice có thể dùng trạng thái mới sau introduction, nhưng **advice và introduction không cùng một thao tác**. Advice tác động vào các điểm thực thi; introduction tác động vào mô hình cấu trúc/kiểu hoặc mặt ngoài đối tượng theo cơ chế.

## 4. Bảng so sánh ở mức kiến trúc

| Tiêu chí | Kế thừa | Mixin / trait | AOP structural extension |
|---|---|---|---|
| Mục đích chính | Quan hệ subtype và mở rộng kiểu | Tái sử dụng hành vi | Bổ sung cấu trúc ngoài phần khai báo target |
| Nơi khai báo | Class/interface ở mã nguồn | Trait/interface/delegate | Aspect hoặc quy tắc introduction |
| Target có cần biết tính năng? | Thường có trong khai báo subtype | Phụ thuộc cách áp dụng | Có thể giảm thay đổi trực tiếp target |
| Thay đổi hệ kiểu? | Có, theo ngôn ngữ | Có hoặc không | Có thể có, tùy weaving/proxy model |
| Bổ sung instance state? | Qua class/subclass | Tùy implementation | Phụ thuộc loại introduction |
| Method resolution | Luật ngôn ngữ | Luật trait/default/delegate | Luật công cụ kết hợp ngôn ngữ |
| Tranh chấp tên | Override/overload | Conflict resolution | Có thể fail weaving hoặc cần precedence/giải quyết |
| Vòng đời | Theo object class | Theo owner/delegate | Per-target/per-instance/per-proxy tùy mô hình |
| Công cụ thực thi | Compiler/runtime Java | Compiler/runtime của cách áp dụng | Weaver/interceptor/adapter tương ứng |

Không đánh đồng ô “thay đổi hệ kiểu” giữa một **proxy implementing interface** và **class gốc thực sự được dệt để implements interface**.

## 5. Ví dụ trực giác: một tính năng gắn nhãn

Giả sử nhiều đối tượng domain cần thao tác:

~~~text
Taggable
  + addTag(tag)
  + tags()
~~~

Các đối tượng gồm Order, Invoice và Shipment; chúng không nhất thiết có một superclass domain chung ngoài Object.

Một giải pháp inheritance có thể tạo một lớp nền TaggedEntity, nhưng điều đó:

- Đưa tính năng gắn nhãn vào phân cấp class.
- Có thể bất tiện với một superclass đã được chọn.
- Tạo nguy cơ base class tích lũy quá nhiều mối quan tâm.
- Có thể buộc domain class phụ thuộc hạ tầng tagging.

Một giải pháp mixin/delegate có thể cho các class sử dụng chung TagState/TagService mà không cần cùng superclass.

Một giải pháp introduction trong AOP có thể khai báo ở ngoài rằng một nhóm lớp đích nay hỗ trợ Taggable, nếu cơ chế chọn lớp và bổ sung interface/member cho phép.

**Cùng API đầu ra không có nghĩa cùng quan hệ kiểu hoặc cùng vị trí lưu trạng thái.**

## 6. Hệ kiểu Java và single class inheritance

Java class chỉ có **một superclass trực tiếp**. Một class có thể implements nhiều interface, và các interface có thể mở rộng nhiều interface khác.

Điều này ảnh hưởng thiết kế mixin:

- Không thể cho một class Java extends đồng thời hai concrete base classes.
- Một interface default method có thể cung cấp hành vi chung nhưng không có instance field theo cách một class bình thường có.
- Nếu hành vi mixin cần state, phải xác định nơi state được lưu: trong class, delegate, external map hoặc cấu trúc do weaver tạo.
- Một công cụ structural AOP không nên được hiểu là “bỏ qua mọi luật hợp lệ của hệ kiểu Java”.

Nếu introduction muốn thêm quan hệ superclass, phải tuân theo **ràng buộc của class hierarchy và bytecode**. Không thể tùy ý ghép nhiều superclass class như một phép mixin vô điều kiện.

## 7. Interface và mixin không hoàn toàn đồng nghĩa

Một interface thể hiện một **hợp đồng kiểu**. Java interface có thể có abstract methods, default methods, static methods và private helper methods trong phạm vi luật ngôn ngữ.

Mixin là ý tưởng **chia sẻ implementation**. Một interface chỉ chứa abstract method tạo hợp đồng nhưng không cung cấp code dùng chung; một interface có default methods có thể đóng vai trò mixin-like.

Ví dụ khái niệm:

~~~java
interface Describable {
    String code();

    default String description() {
        return "code=" + code();
    }
}
~~~

Đây là mảnh Java hợp lệ nhưng không phải file runnable độc lập.

Một class implements Describable cần cung cấp code(); khi ấy có thể dùng default description(). Điều này là **mixin-like behavior bằng ngôn ngữ Java**, không cần structural weaver và cũng không tự giới thiệu interface cho các class vốn chưa implements nó.

## 8. Composition/delegation cũng có thể giống mixin

Một class có thể giữ delegate:

~~~text
Order
  has-a TagState
  addTag delegates to TagState.add
~~~

Ưu điểm:

- State owner rõ.
- Kiểm thử delegate độc lập.
- Không cần hierarchy phức tạp.
- Dễ chọn thread-safety/synchronization.
- Không phụ thuộc bytecode weaving để biết method tồn tại.

Nhược điểm có thể là phải viết forwarding methods, sửa target hoặc bọc target trong adapter.

Trong một số hệ AOP, một introduction có thể được hiện thực bằng **delegate**. Nhưng điều này phụ thuộc cơ chế; không được tuyên bố mọi introduction đều tương đương composition thủ công.

## 9. Kế thừa là subtype relation chứ không phải dán thêm method

Nếu class PriorityOrder extends Order, quan hệ:

~~~text
PriorityOrder is-an Order
~~~

có ý nghĩa với overload resolution, subtype checks và dynamic dispatch.

Một Taggable mixin được áp dụng cho Order có thể chỉ biểu thị:

~~~text
Order supports Taggable behavior
~~~

Không nhất thiết tạo ra quan hệ domain “TaggedOrder là một nhánh con của Order”. Một structural introduction có thể đưa ra interface membership, còn việc có superclass relation mới hay không phải dựa vào tính năng của công cụ.

**Mối quan hệ kiểu nên phản ánh ý nghĩa hợp đồng**, không chỉ tiện viết code.

## 10. Ví dụ Java 17 số 1: interface default, xung đột và kế thừa

Chương trình này trình bày ba quy tắc Java cụ thể:

1. Một class implements hai interface cung cấp default method cùng chữ ký phải giải quyết xung đột phù hợp.
2. Một subclass có thể override method đã được class cha giải quyết.
3. Method concrete được thừa hưởng từ superclass có ưu tiên trước default method interface tương ứng trong trường hợp minh họa.

Lưu file **InheritanceMixinDemo.java**:

~~~java
public class InheritanceMixinDemo {
    interface LeftLabel {
        default String label() {
            return "LEFT";
        }
    }

    interface RightLabel {
        default String label() {
            return "RIGHT";
        }
    }

    static class Combined implements LeftLabel, RightLabel {
        @Override
        public String label() {
            return LeftLabel.super.label()
                    + "+"
                    + RightLabel.super.label();
        }
    }

    static class Specialized extends Combined {
        @Override
        public String label() {
            return "SPECIAL(" + super.label() + ")";
        }
    }

    static class BaseRecord {
        public String label() {
            return "BASE";
        }
    }

    static class DerivedRecord extends BaseRecord
            implements LeftLabel {
        // BaseRecord.label() đã cung cấp implementation.
    }

    public static void main(String[] args) {
        Combined combined = new Combined();
        Specialized specialized = new Specialized();
        DerivedRecord derived = new DerivedRecord();

        System.out.println("[combined] " + combined.label());
        System.out.println("[specialized] " + specialized.label());
        System.out.println("[class-wins] " + derived.label());
        System.out.println("[as-interface] "
                + ((LeftLabel) combined).label());
    }
}
~~~

Biên dịch/chạy bằng JDK 17:

~~~bash
javac InheritanceMixinDemo.java
java InheritanceMixinDemo
~~~

**Stdout chính xác:**

~~~text
[combined] LEFT+RIGHT
[specialized] SPECIAL(LEFT+RIGHT)
[class-wins] BASE
[as-interface] LEFT+RIGHT
~~~

### 10.1. Combined phải giải quyết xung đột

LeftLabel và RightLabel đều cung cấp label(). Combined override rõ ràng và gọi hai default implementations qua InterfaceName.super.

Nếu Combined không có một quy tắc override phù hợp, compiler Java sẽ báo xung đột default methods. Không có chuyện JVM tùy ý chọn interface xuất hiện đầu tiên trong implements list.

### 10.2. Specialized minh họa kế thừa và dynamic dispatch

Specialized extends Combined và override label. Khi gọi trên đối tượng Specialized, implementation override được thực thi.

Đây là luật Java thông thường, không phải weaving hoặc introduction. Việc có mixin-like behavior từ interface không xóa quy tắc subclass dispatch.

### 10.3. BaseRecord minh họa ưu tiên class implementation

DerivedRecord extends BaseRecord và implements LeftLabel. BaseRecord đã cung cấp label concrete; do đó trong tình huống này method của class được dùng thay vì default label của interface.

Không suy rằng mọi engine introduction có thể dễ dàng áp dụng một default method để ghi đè method sẵn có của class. Muốn chặn/thay hành vi method đang tồn tại là một chủ đề **behavioral advice/override/dispatch** khác với bổ sung cấu trúc, và có các quy tắc xung đột riêng.

### 10.4. Gọi qua interface không thay implementation động

Khi cast combined thành LeftLabel và gọi label(), method override ở Combined vẫn được dùng. Hợp đồng interface quyết định cách sử dụng về mặt kiểu; dispatch tới implementation hợp lệ tại runtime.

## 11. Đây chưa phải structural AOP

InheritanceMixinDemo chỉ dùng những tính năng sẵn có trong source Java. Các class **tự khai báo** implements/extends; không có aspect nào bổ sung interface cho một class đã định nghĩa.

Điều quan trọng là dùng ví dụ để hiểu **luật kiểu và giải quyết xung đột** mà một implementation AOP có thể phải tương thích, không coi Java default methods là một ngôn ngữ introduction chung.

Muốn quan sát hiệu ứng thêm interface ở ngoài target source, cần phân biệt **adapter/proxy** với **weaving thực sự thay đổi định nghĩa class**.

## 12. Introduction có thể có nhiều cấp độ

Một số kiểu mở rộng cấu trúc về mặt khái niệm:

### 12.1. Interface introduction

Công cụ khiến lớp đích được nhìn nhận là thực hiện một interface mới. Khi có hỗ trợ đầy đủ, code được biên dịch trong môi trường biết introduction có thể gọi các method của interface theo hợp đồng.

### 12.2. Method introduction

Một method mới được bổ sung vào mô hình cấu trúc của lớp đích. Việc compiler, class loader và reflection có nhìn thấy nó ra sao phụ thuộc cách weaving.

### 12.3. Field/state introduction

Một trạng thái mới được tổ chức để phục vụ hành vi bổ sung. Nó có thể gắn từng instance, một aspect instance, một delegate hoặc một vùng lưu bên ngoài.

### 12.4. Parent-type introduction

Một số hệ AOP có khả năng thay hoặc khai báo thêm quan hệ kiểu cha trong giới hạn nhất định. Phải xem tính hợp lệ trong hierarchy; không coi đây là một cách tùy ý vượt luật single class inheritance.

### 12.5. Delegate-backed introduction

Một mặt ngoài mới được ghép từ target và delegate. Đôi khi caller chỉ tương tác qua một wrapper/proxy; khi đó target gốc có thể **không bị thay cấu trúc thật**.

Bốn/five cấp độ này không mặc nhiên cùng được một engine hỗ trợ.

## 13. Mixin trong AOP thường là hợp đồng cộng implementation

Một thiết kế điển hình ở mức khái niệm:

~~~text
Target: Order
Interface: Taggable
Implementation source: TagMixinDelegate

Introduction policy:
  target types matching criterion
  expose Taggable
  delegate Taggable methods to a suitable state holder
~~~

Mục tiêu là tái sử dụng implementation Taggable cho nhiều target types mà không chép method vào từng class source.

Điểm cần chốt:

- Ai tạo delegate?
- Mỗi target một delegate hay nhiều target dùng chung?
- Ai hủy hoặc thu hồi state?
- Một target có được nhiều proxy đại diện không?
- Phương thức introduced có dispatch tới target hay delegate?
- Quan hệ interface có nhìn thấy từ object gốc, proxy hay class đã weave?
- Khi nhiều introductions trùng method signature, lỗi/precedence xử lý ra sao?

Nếu không làm rõ, một “mixin” có thể vô tình trộn trạng thái giữa các đối tượng hoặc gây memory leak.

## 14. Proxy không tự biến đổi class đích

Trong Java, Dynamic Proxy có thể tạo một object mới triển khai một tập interface xác định và chuyển lời gọi tới InvocationHandler.

Ví dụ:

~~~text
Original object: Order
Proxy object:    OrderView + Taggable
                     |
                     +-- OrderView calls delegate to Order
                     +-- Taggable calls use extra state
~~~

Ở đây **proxy** có thể implements Taggable, nhưng **Order gốc không tự implements Taggable**.

Điều đó khác với một loại class-level structural weaving thực sự khiến target class được nhận diện là implement interface mới.

Một runtime interceptor có thể dùng proxy làm “mặt ngoài đã mở rộng”, nhưng phải mô tả đúng giới hạn. Casting original Order thành Taggable có thể không hợp lệ; casting proxy thì có thể hợp lệ.

## 15. Ví dụ Java 17 số 2: proxy đưa thêm interface, nhưng không weave object gốc

Ví dụ này dùng Java Dynamic Proxy để **mô phỏng một mặt ngoài bổ sung hành vi Taggable**. Đây không phải một implementation structural AOP tự động.

Mỗi proxy có một LinkedHashSet riêng lưu tags. Hai proxy cùng ủy quyền tới một Order gốc vẫn có state tags khác nhau. Điều này minh họa vì sao **per-proxy state** không nên bị lẫn với **per-target state**.

Lưu file **ProxyMixinDemo.java**:

~~~java
import java.lang.reflect.InvocationHandler;
import java.lang.reflect.Proxy;
import java.util.LinkedHashSet;
import java.util.Set;

public class ProxyMixinDemo {
    interface OrderView {
        String code();
    }

    interface Taggable {
        void addTag(String tag);
        String tags();
    }

    static final class Order implements OrderView {
        private final String code;

        Order(String code) {
            this.code = code;
        }

        @Override
        public String code() {
            return code;
        }
    }

    static Object introduce(OrderView target) {
        Set<String> tags = new LinkedHashSet<>();

        InvocationHandler handler = (proxy, method, args) -> {
            Class<?> owner = method.getDeclaringClass();

            if (owner == Taggable.class) {
                if (method.getName().equals("addTag")) {
                    tags.add((String) args[0]);
                    return null;
                }
                if (method.getName().equals("tags")) {
                    return String.join(",", tags);
                }
            }

            if (owner == OrderView.class
                    && method.getName().equals("code")) {
                return target.code();
            }

            if (owner == Object.class) {
                return switch (method.getName()) {
                    case "toString" ->
                            "TaggedView(" + target.code() + ")";
                    case "hashCode" ->
                            System.identityHashCode(proxy);
                    case "equals" -> proxy == args[0];
                    default ->
                            throw new UnsupportedOperationException(
                                    method.toString());
                };
            }

            throw new UnsupportedOperationException(method.toString());
        };

        return Proxy.newProxyInstance(
                OrderView.class.getClassLoader(),
                new Class<?>[] {OrderView.class, Taggable.class},
                handler);
    }

    public static void main(String[] args) {
        Order original = new Order("ORD-7");
        Object proxyOne = introduce(original);
        Object proxyTwo = introduce(original);

        System.out.println("[original] taggable="
                + (((Object) original) instanceof Taggable));
        System.out.println("[proxy] taggable="
                + (proxyOne instanceof Taggable));
        System.out.println("[proxy] sameObject="
                + (proxyOne == proxyTwo));

        Taggable one = (Taggable) proxyOne;
        Taggable two = (Taggable) proxyTwo;
        one.addTag("hot");
        one.addTag("hot");
        one.addTag("review");

        System.out.println("[proxy-one] code="
                + ((OrderView) proxyOne).code());
        System.out.println("[proxy-one] tags=" + one.tags());
        System.out.println("[proxy-two] empty="
                + two.tags().isEmpty());
        System.out.println("[original] code=" + original.code());
    }
}
~~~

Biên dịch và chạy bằng JDK 17:

~~~bash
javac ProxyMixinDemo.java
java ProxyMixinDemo
~~~

**Stdout chính xác:**

~~~text
[original] taggable=false
[proxy] taggable=true
[proxy] sameObject=false
[proxy-one] code=ORD-7
[proxy-one] tags=hot,review
[proxy-two] empty=true
[original] code=ORD-7
~~~

### 15.1. Tại sao original không Taggable?

Order chỉ khai báo implements OrderView. Nó là một class Java được biên dịch bình thường và không hề được một weaver thay đổi. Interface Taggable xuất hiện **trên proxy object** do Proxy.newProxyInstance tạo.

### 15.2. Tại sao proxy Taggable?

newProxyInstance nhận hai interface: OrderView và Taggable. Proxy class tại runtime implements cả hai nên proxyOne instanceof Taggable đúng.

Điều này chỉ cho phép cast **proxy object**, không cung cấp một phép cast mới cho **original object**.

### 15.3. Tại sao proxyOne và proxyTwo có tags khác nhau?

Mỗi lần gọi introduce tạo một LinkedHashSet mới bên trong InvocationHandler closure. Hai proxies cùng trỏ tới target code ORD-7, nhưng state của Taggable nằm **per-proxy**, không nằm trong Order.

Nếu yêu cầu thực tế là tags gắn lâu dài với **target**, thiết kế per-proxy ở đây không đáp ứng: truy cập qua proxy khác không thấy tags đã lưu. Cần xác định key ownership và state lifetime ở cấp target.

### 15.4. Tại sao hot chỉ xuất hiện một lần?

LinkedHashSet giữ phần tử không trùng và theo thứ tự chèn. Sau khi addTag("hot") hai lần và "review" một lần, chuỗi nối là hot,review.

Đây là thuộc tính cấu trúc dữ liệu được dùng trong demo, không phải quy tắc tự có của một mixin.

### 15.5. Hạn chế cố ý của ví dụ

- Không có code weaving, inter-type compiler hay pointcut selection.
- Không thay đổi class Order gốc.
- Dynamic Proxy chỉ dựng mặt ngoài dựa trên interface.
- Object methods được xử lý bằng identity semantics của proxy trong demo, không phải quy tắc equality cho mọi application.
- LinkedHashSet trong handler chưa đồng bộ hóa, không an toàn nếu cùng proxy bị nhiều thread sửa đồng thời.
- Handler triển khai method name rõ cho ví dụ, không phải adapter phổ dụng cho mọi overloaded method.
- Không mô tả toàn bộ cơ chế checked exceptions của reflection/proxy; nếu handler dùng Method.invoke phải xử lý InvocationTargetException và hợp đồng throws thích hợp.

**Bài học:** proxy có thể cho trải nghiệm “object hỗ trợ thêm interface”, nhưng phải biết **object nào được mở rộng** và **state gắn với gì**.

## 16. Structural weaving thực sự khác proxy bọc

Giả sử một công cụ AOP có inter-type declarations thực sự được weave vào một class:

~~~text
Source declares Order only.
Weaver transforms type model / bytecode.
Resulting Order class can expose added interface/members
within the supported configuration.
~~~

Khi ấy có thể có sự khác biệt so với proxy:

- Code tương thích có thể xem **instance của Order class** là interface mới.
- Method introduction có thể được nhìn thấy trong class metadata hoặc reflection theo cách weaving.
- Không cần caller luôn cầm một proxy wrapper riêng.
- Semantics về lifecycle và field storage phụ thuộc những gì weaver đã bổ sung.

Nhưng không được nói mọi kỹ thuật weaving đều hoạt động như trên ở mọi phase. **Compile-time, post-compile và load-time weaving** có điểm thời gian, khả năng ảnh hưởng tới caller đã biên dịch, instrumentation scope và class loading khác nhau.

## 17. Thời điểm weaving ảnh hưởng khả năng nhìn thấy API

Có thể phân biệt ba nhóm khái niệm:

1. **Compile-time weaving:** mã nguồn và quy tắc aspect được kết hợp trong quá trình build thích hợp.
2. **Post-compile/binary weaving:** class artifacts đã biên dịch được biến đổi trước khi được sử dụng theo cơ chế.
3. **Load-time weaving:** class được biến đổi khi nạp, trước khi JVM định nghĩa class tương ứng nếu cơ chế hỗ trợ.

Một thay đổi structural có thể ảnh hưởng **kiểu nhìn thấy lúc compile** của caller. Nếu caller đã biên dịch mà không biết method introduced, nó không tự có source-level type checking và lời gọi trực tiếp tới method đó.

Ngược lại, bytecode được weave đúng thời điểm có thể cung cấp runtime interface membership, nhưng bản thân điều ấy chưa làm **source code cũ tự xuất hiện lời gọi method mới**.

Cần phân biệt **API visibility khi biên dịch**, **cấu trúc runtime đã nạp**, và **cơ chế truy cập thông qua proxy/adapter**.

## 18. Binary compatibility và class loading

Structural change có thể tương tác với:

- Các class đã được JVM nạp.
- Multiple class loaders có các bản định nghĩa class khác nhau.
- Module boundaries và access rules.
- Method descriptors/erasure.
- Những caller đã biên dịch với phiên bản cũ.
- Serialization contracts hoặc reflection metadata.
- Interface method dispatch và default-method rules.

Không tự cho rằng sau khi một class đã được JVM định nghĩa, hệ thống có thể tùy ý thêm method/interface cho class ấy ở mọi thời điểm. Các API redefine/retransform class trong JVM có **những giới hạn cụ thể**; cấu trúc có thể cần được quyết định trước khi class được định nghĩa.

Vì vậy structural AOP thường nhạy hơn advice thuần quan sát đối với build/deployment/class-loading environment.

## 19. Khả năng casting phải gắn với danh tính object

Ba tình huống:

~~~text
1) Subclass object:
   new PriorityOrder() instanceof Order  -> true

2) Proxy implements Taggable:
   proxy instanceof Taggable             -> true
   underlying original may not be Taggable

3) Woven target type implements Taggable:
   actual woven instance may be Taggable
   depending on weaving model and load scope
~~~

Không thể chỉ từ một log “introduced Taggable” mà kết luận **mọi reference tới object gốc** đều cast được thành Taggable. Phải biết nó chỉ là proxy mặt ngoài hay thay đổi class runtime thật.

Điều này quan trọng khi một phần code dùng proxy còn code khác giữ reference trực tiếp tới target.

## 20. Identity và equality khi dùng mixin/proxy

Với inheritance, một object instance có danh tính của chính nó. Với wrapper/proxy, có ít nhất **hai object**: original và proxy.

Nếu hai proxies cùng đại diện một target:

~~~text
proxyOne != proxyTwo (identity)
proxyOne delegates to target X
proxyTwo delegates to target X
~~~

Định nghĩa equals/hashCode của proxy có thể:

- Dựa trên identity của proxy.
- Dựa trên identity của target.
- Dựa trên business key của target.
- Dựa trên một contract riêng.

Mỗi lựa chọn có tác động tới Set/Map caching, context storage và mixin state. Không tự dùng equals của target làm khóa lưu state nếu hai target **equals bằng nhau về nghiệp vụ nhưng là hai object khác** mà state cần tách.

Nếu state nên gắn mỗi target instance, **object identity** và lifetime/GC cần được thiết kế rõ.

## 21. State ownership: per-instance, per-target, per-proxy, per-type

Một mixin có thể cần trạng thái:

| Mô hình state | Ý nghĩa | Rủi ro |
|---|---|---|
| **Per-target instance** | Mỗi target object một state | Cần lifecycle gắn target/GC |
| **Per-proxy** | Mỗi proxy view một state | Hai proxies của một target khác state |
| **Per-aspect singleton** | Shared state toàn scope | Nhiều target/request trộn dữ liệu |
| **Per-type** | Shared state theo class/type | Không chứa dữ liệu riêng instance |
| **Per-invocation** | State tạm cho một lời gọi | Không giữ lâu hơn lời gọi |
| **External keyed store** | State nằm trong map/delegate ngoài | Key/equality, retention, concurrency |

Không được đặt requestId hiện tại vào mixin instance sống lâu qua nhiều request chỉ vì nó gắn với một target. **Per-target không phải per-request**.

Một introduction tạo field trên target có thể có lifetime theo target; một delegate per-proxy có lifetime theo proxy. Chúng không hoán đổi được khi thiết kế dữ liệu.

## 22. Giữ state bên ngoài có thể gây memory leak

Nếu dùng một static map:

~~~text
Map<Target, MixinState>
~~~

và giữ strong references, target objects có thể không được thu hồi dù ứng dụng không còn dùng.

Một weak-key map có thể giảm retention trong một số thiết kế, nhưng cần hiểu semantics của equals/hashCode và việc **value không được giữ đường tham chiếu ngược tới key** nếu mục tiêu là GC. Ngoài ra weak references có thể bị thu hồi ở thời điểm không dự đoán trước.

Một identity map cho phép phân biệt object identity nhưng nếu nó giữ strong key vẫn có thể tạo leak. Không có một loại map nào tự giải quyết mọi yêu cầu identity, lifecycle và concurrency.

Nếu dùng field thực sự trong woven object, state thường có lifetime theo object. Nếu dùng proxy, state có thể theo proxy. **Hãy xác định nơi state thật sự nằm trước khi chọn cleanup.**

## 23. Concurrency của mixin state

Một mixin có thể được áp dụng lên shared target nhiều thread cùng gọi. Nếu introduced field hoặc delegate chứa HashMap, ArrayList hoặc LinkedHashSet mutable, không thể mặc định thread safe.

Ví dụ ProxyMixinDemo sử dụng LinkedHashSet không được synchronized. Dùng an toàn trong một demo tuần tự, không chứng minh rằng addTag đồng thời là an toàn.

Các lựa chọn gồm:

- Immutable value replacement với cơ chế publish phù hợp.
- Thread-safe collection nếu semantics đúng.
- Synchronization/lock có phạm vi hẹp.
- Atomic state khi thao tác đủ đơn giản.
- Per-invocation state nếu không cần chia sẻ.
- Ownership theo thread hoặc actor model phù hợp.

Không dùng synchronized mù quáng nếu cross-cutting code có thể re-enter target hoặc gọi advice khác, vì dễ tạo lock ordering/deadlock problem.

## 24. Method lookup, overriding và conflict resolution

Nếu một method được bổ sung trùng tên với method có sẵn, không đủ để biết “ai thắng” chỉ bằng tên.

Phải kiểm tra:

1. Chữ ký đầy đủ (name và parameter types, method descriptor khi xét bytecode).
2. Visibility/access của cả hai khai báo.
3. Static hay instance method.
4. Return-type covariance hợp lệ hay không.
5. Method abstract/default/concrete.
6. Superclass/interface precedence.
7. Phạm vi generic và type erasure.
8. Bridge methods do compiler tạo.
9. Rules về conflict của công cụ structural AOP.
10. Có method final hoặc ràng buộc khác không thể thay thế.

Ở Java, overriding một method đã có khác với **thêm method mới**. Một introduction không thể tự được coi là quyền override mọi method final hoặc ghi đè default resolution tùy ý.

## 25. Hai mixin đưa ra cùng một member

Giả sử có hai mixin:

~~~text
TagMixin:
    label()

AuditMixin:
    label()
~~~

Nếu cả hai được áp dụng cho cùng target và cùng signature, hệ thống có thể gặp xung đột.

Các cách xử lý **phụ thuộc ngôn ngữ/công cụ**:

- Báo lỗi compile/weave.
- Yêu cầu khai báo override/alias rõ.
- Định nghĩa precedence tường minh.
- Đổi API thành hai tên/namespace không trùng.
- Dùng delegate composition và forwarding có chủ đích.

Không giả định “aspect khai báo sau luôn thắng” hoặc “mixin gần target hơn luôn thắng”. Nếu thứ tự ảnh hưởng correctness, phải có bảo đảm thực tế và kiểm thử.

Một cách thiết kế tốt là **tránh làm mờ ownership**: hai trách nhiệm khác nhau nên có hai interface/method names rõ, thay vì tranh một method chung không mang ngữ nghĩa cụ thể.

## 26. Overload khác override

Hai method cùng tên nhưng khác tham số là **overload**. Một method trong subtype có cùng chữ ký phù hợp và ràng buộc return/access là **override**.

Mixin giới thiệu:

~~~text
label()
label(Locale)
~~~

có thể tạo overload. Nhưng thêm label() cùng signature với method có sẵn có thể là conflict hoặc một cơ chế override tùy luật.

AOP advice chọn method call bằng pointcut cũng có thể bị nhầm giữa các overload nếu biểu thức chọn chỉ dùng tên. Khi làm structural introduction, cần kiểm tra **hợp đồng chữ ký và type resolution**, không chỉ tên hiển thị trên log.

## 27. Generics và type erasure

Java generics có **type erasure**; nhiều thông tin tham số kiểu không tồn tại như các method descriptors runtime khác nhau.

Nếu introduction/mixin cố tạo các method chỉ khác nhau về generic type arguments nhưng bị erase thành cùng descriptor, có thể gặp name clash.

Ví dụ khái niệm:

~~~text
process(List<String>)
process(List<Integer>)
~~~

Hai chữ ký này không thể là hai overload Java hợp lệ chỉ dựa trên generic argument vì cùng erasure List.

Cần chú ý compiler-generated bridge methods trong các quan hệ override tổng quát. Một công cụ weaving xử lý bytecode phải nhất quán với những quy tắc này; không được hứa thêm mọi generic method tùy ý mà không xét collision.

## 28. Kế thừa và substitution

Một subtype hợp lệ về kiểu chưa chắc giữ đúng mọi giả định về **hành vi**. Thiết kế nên tôn trọng khả năng thay thế: nơi mong đợi supertype không nên bị phá invariants bởi subtype hoặc introduced behavior.

Ví dụ một introduction thêm Taggable cho Order chỉ nên thể hiện **một hợp đồng mà Order thật sự đáp ứng**. Nếu addTag được cho phép nhưng tags luôn trả dữ liệu từ proxy khác không đồng nhất, có thể vi phạm kỳ vọng của client.

Hợp đồng hành vi gồm:

- Điều kiện trước/sau.
- Bất biến của object.
- Ngữ nghĩa exceptions.
- State consistency.
- Thread safety.
- Equality/identity.
- Persistence/serialization nếu có.
- Khả năng dùng qua các reference khác nhau.

Structural typing nhìn có vẻ đúng chưa bảo đảm behavior đúng.

## 29. Mixin không phải đa kế thừa class

Một ngôn ngữ có thể hỗ trợ traits, modules hoặc multiple inheritance với các quy tắc linearization và conflict resolution riêng. Java class inheritance không có đa kế thừa class.

Interface default methods đem lại một dạng tái sử dụng code, nhưng:

- Không kế thừa multiple concrete class state.
- Có quy tắc xung đột default methods rõ ràng.
- Không tự giới thiệu interface vào target chưa khai báo.
- Không tự giải quyết state ownership.
- Không thay thế composition cho mọi nhu cầu.

Vì vậy gọi mixin là “đa kế thừa” chỉ chính xác khi nói về một mô hình ngôn ngữ cụ thể có semantics phù hợp; không phải một định nghĩa phổ quát.

## 30. AOP structural introduction và open classes

**Open class** là ý tưởng cho phép bổ sung phần khai báo hoặc hành vi của class từ ngoài module class ban đầu theo một cách có tổ chức.

Structural introduction trong AOP có thể được xem như một dạng hỗ trợ open classes trong những mô hình cho phép thêm members hoặc parent types.

Nhưng “open classes” là một khái niệm thiết kế rộng. Không phải một runtime monkey-patching system bất kỳ cũng có type checking hoặc weaving semantics giống structural AOP.

Điểm cần xét:

- Extension được giải quyết ở compile time hay runtime?
- Có thể nhìn thấy từ những module khác không?
- Có một định nghĩa class thống nhất hay nhiều wrapper views?
- Konflikt method được phát hiện lúc nào?
- Metadata reflection có phản ánh không?
- Binary compatibility được đảm bảo ở mức nào?

## 31. Thiết kế introduction tránh phụ thuộc quá nhiều vào target

Một structural aspect có thể phải chọn nhiều classes:

~~~text
Apply Taggable to:
  Order
  Invoice
  Shipment
~~~

Mục tiêu tái sử dụng là rõ, nhưng nếu selection quá rộng:

- Một class vốn đã implements Taggable có thể bị conflict.
- Một class mới vô tình nhận API không phù hợp domain.
- Một method introduced vô tình trùng tên với method mới của target sau refactor.
- Một version library mới thay hierarchy làm weaving không còn hợp lệ.
- Một target từ module khác không nằm trong phạm vi weave.

Nên chọn **tiêu chí áp dụng có ý nghĩa** và có test âm: class nào chắc chắn **không được nhận extension**.

## 32. Khi nào chọn kế thừa?

Kế thừa phù hợp khi:

- Có quan hệ subtype thực sự, rõ hợp đồng.
- Chúng ta kiểm soát source hierarchy.
- Một shared base class không cản trở nhu cầu mở rộng khác.
- Các invariants của superclass và subclass tương thích.
- Việc thiết kế mở rộng không làm lớp nền trở thành “god object”.

Không nên dùng kế thừa chỉ để gom logging, metrics, tagging và audit vào một base class nếu chúng không cùng bản chất domain.

Nếu một tính năng là optional/cross-cutting, composition hoặc mixin có thể biểu đạt tốt hơn. Nếu cần bổ sung cấu trúc vào code không muốn hoặc không thể sửa, structural AOP có thể phù hợp **khi công cụ và deployment có hỗ trợ chắc chắn**.

## 33. Khi nào chọn mixin/delegation?

Mixin/delegation phù hợp khi:

- Hành vi được tái sử dụng ở nhiều domain types.
- Không muốn đưa các types vào một concrete superclass chung.
- Có thể định nghĩa một interface rõ.
- State được lưu ở delegate hoặc owner hợp lý.
- Conflict resolution và thread safety dễ kiểm soát.
- Không cần thay bytecode hay runtime type model của class đích.

Một adapter/proxy có thể là giải pháp khi caller được phép nhận một wrapper object mới. Cần tài liệu hóa rằng **caller phải dùng wrapper**, và direct target reference có thể không có interface mở rộng.

## 34. Khi nào chọn structural extension bằng AOP?

Nên cân nhắc khi:

- Nhiều target classes cần cùng một hợp đồng ngoài concern cốt lõi.
- Source target không nên bị sửa hoặc nằm ở một module có khả năng mở rộng được kiểm soát.
- Mô hình AOP có **structural introductions được định nghĩa rõ**.
- Build/deployment có thể đảm bảo weaving đúng classes.
- Caller cần kiểu mới theo ngữ nghĩa thực, không chỉ intercept behavior.
- Các conflicts, constructor/lifetime/state và class loading đã được đánh giá.
- Có integration tests về cast, reflection, dispatch và concurrency.

Không nên dùng structural AOP chỉ vì muốn log một method: **behavioral advice** thường đúng mục tiêu và đơn giản hơn.

## 35. Thử nghiệm phải kiểm tra lớp nào thật sự được thay

Các ca test có giá trị:

| Ca | Kỳ vọng |
|---|---|
| Class đích được chọn | Nhận đúng extension theo mô hình |
| Class không được chọn | Không vô tình nhận interface/member |
| Proxy được gắn interface | Proxy cast được |
| Original target sau proxy wrapping | Không mặc định cast được |
| Woven class thật | Kiểm tra runtime interface membership khi được hỗ trợ |
| Target đã có method cùng chữ ký | Conflict/precedence đúng đặc tả |
| Hai mixin trùng member | Không có thứ tự ngầm nguy hiểm |
| Subclass override | Dispatch theo hợp đồng |
| Superclass method và interface default | Luật ngôn ngữ được giữ |
| Nhiều proxy cho cùng target | State ownership đúng |
| Hai targets equals nhưng khác identity | Không trộn state |
| Nhiều threads dùng shared target | Không race mixin state |
| Generic erasure collision | Không tạo class không hợp lệ |
| Reflection lookup | Chỉ khẳng định những method runtime thực có |
| Caller đã compile trước weaving | API visibility được xác nhận |
| Module/class loader boundary | Không nhầm hai lớp cùng tên khác loader |
| GC/release | Không giữ target qua static map ngoài ý định |
| Exception từ delegate | Không che lỗi gốc hoặc phá API |

Một unit test của delegate chưa đủ chứng minh structural weaving đã áp dụng lên đúng class ở môi trường chạy thật.

## 36. Lỗi phổ biến và cách sửa

**Lỗi 1 — Đồng nhất mixin với kế thừa.** Mixin là tổ chức tái sử dụng hành vi; kế thừa có subtype semantics cụ thể. Chọn đúng theo hợp đồng.

**Lỗi 2 — Cho rằng proxy đã sửa class gốc.** Proxy là object khác; phải phân biệt reference gốc và proxy.

**Lỗi 3 — Coi interface default method là state-bearing mixin.** Interface không có instance fields tùy ý; phải thiết kế state owner.

**Lỗi 4 — Đặt state của mọi target vào singleton aspect field.** Nhiều object có thể trộn trạng thái.

**Lỗi 5 — Sử dụng map strong-key lưu per-target state mãi.** Có thể giữ target sống lâu gây memory leak.

**Lỗi 6 — Mỗi proxy tự có state nhưng ứng dụng kỳ vọng per-target.** Hai wrapper nhìn thấy dữ liệu không nhất quán. Quy định scope rõ.

**Lỗi 7 — Bỏ qua thread safety.** Introduced field/delegate vẫn chịu concurrency như field thông thường.

**Lỗi 8 — Hai introductions trùng tên và dựa vào order ngẫu nhiên.** Dùng naming/override/precedence được bảo đảm hoặc báo conflict.

**Lỗi 9 — Cho rằng mọi AOP engine hỗ trợ thêm method/field.** Phải kiểm tra đúng join point và introduction capabilities.

**Lỗi 10 — Nhầm advice với introduction.** Chặn lời gọi không tạo thành viên kiểu mới.

**Lỗi 11 — Coi một cast thành công ở proxy chứng minh target cast được.** Test cả hai reference.

**Lỗi 12 — Không tính generic erasure và bridge methods.** Dễ gây collision/dispatch khác mong đợi.

**Lỗi 13 — Đổi hierarchy nhưng không xét binary compatibility.** Caller và class loader có thể dùng version khác.

**Lỗi 14 — Tạo mixin làm sai subtype invariants.** Interface membership về kiểu không đảm bảo behavior của contract.

**Lỗi 15 — Không kiểm thử negative selection.** Lớp ngoài phạm vi vẫn có thể bị mở rộng không mong muốn.

## 37. Quy trình phân tích một mở rộng cấu trúc

1. Xác định **hợp đồng mới** cần cung cấp.
2. Xác định yêu cầu là **behavioral advice** hay **structural API change**.
3. Xem kế thừa có phản ánh quan hệ domain thật không.
4. Xem mixin/delegate có thể tái sử dụng hành vi mà không sửa target không.
5. Nếu dùng AOP introduction, xác minh công cụ hỗ trợ interface/method/field/parent ở mức nào.
6. Xác định **object nhận interface**: target thật, woven instance hay proxy view.
7. Xác định **state owner**: per-instance, per-target, per-proxy hay per-type.
8. Xác định thứ tự method lookup, override và các conflicts.
9. Kiểm tra Java inheritance, generic erasure và access constraints.
10. Kiểm tra compile-time API visibility so với runtime structure.
11. Kiểm tra class loading, module boundaries và build/deployment.
12. Định nghĩa thread safety và release/GC policy.
13. Kiểm thử cast, reflection, delegate behavior và negative target selection.
14. Đo overhead và ảnh hưởng debug/stack traces.
15. Ghi tài liệu về điều kiện extension hoạt động và nơi không hoạt động.

Không bắt đầu bằng việc tìm một cú pháp “thêm interface nhanh nhất” khi chưa biết **kiểu và state có ý nghĩa gì ở runtime**.

## 38. Bài tập tự kiểm tra

### Câu 1. Mixin và superclass

Order và Shipment cần gắn nhãn nhưng thuộc hai hierarchy khác nhau. Có bắt buộc đưa chúng vào cùng một superclass TaggableBase không?

**Đáp án:** không. Có thể dùng interface + delegation, default methods khi đủ, hoặc structural introduction nếu cơ chế hỗ trợ.

### Câu 2. Proxy và cast

Một proxy implements Taggable, target gốc không. Có thể cast target gốc thành Taggable chỉ vì proxy của nó cast được không?

**Đáp án:** không. Proxy và target là hai object với type membership có thể khác nhau.

### Câu 3. Hai default methods

Hai interfaces cung cấp cùng default label(). Một class implements cả hai có thể dựa vào thứ tự implements để chọn method không?

**Đáp án:** không. Cần tuân thủ luật giải quyết conflict, ví dụ override rõ như chương trình đầu.

### Câu 4. Superclass và interface

BaseRecord có label concrete, DerivedRecord extends BaseRecord implements LeftLabel có label default. Method nào được dùng trong ví dụ?

**Đáp án:** method từ BaseRecord.

### Câu 5. Hai proxies, cùng target

ProxyOne và ProxyTwo được tạo từ một Order nhưng mỗi handler có state riêng. Tags thêm vào ProxyOne có tự xuất hiện ở ProxyTwo không?

**Đáp án:** không trong chương trình minh họa. State được cấp phát per-proxy.

### Câu 6. Per-target và per-request

Một target service sống lâu phục vụ nhiều requests. Có nên lưu currentRequestId vào introduced field per-target và xem đó là request scope không?

**Đáp án:** không. Per-target lifetime có thể dài hơn request, gây nhầm dữ liệu và concurrency issues.

### Câu 7. Advice và introduction

Một advice log trước calculateTotal. Order có tự trở thành Loggable interface không?

**Đáp án:** không. Behavioral advice không mặc định thay đổi cấu trúc kiểu.

### Câu 8. Generic overload

Có thể thêm hai overload process(List<String>) và process(List<Integer>) chỉ dựa vào generic arguments trong Java không?

**Đáp án:** không, vì type erasure khiến chữ ký xung đột.

### Câu 9. Field introduction và GC

Một static map có strong keys là target objects và chứa state mixin. Rủi ro là gì?

**Đáp án:** map có thể giữ targets sống lâu hơn dự kiến và gây memory retention.

### Câu 10. Class loading

Một app đã load class trước khi bộ biến đổi có cơ hội thêm interface. Có thể tự giả định mọi object đã tạo sẽ nhận interface mới không?

**Đáp án:** không. Cần xem weaving phase và giới hạn JVM/class redefinition.

### Câu 11. Thêm method có sẵn

Một introduction khai báo method cùng chữ ký với method của target. Có chắc introduction sẽ override theo ý tác giả không?

**Đáp án:** không. Có thể conflict hoặc áp dụng một precedence/dispatch riêng tùy công cụ; phải kiểm chứng đặc tả.

### Câu 12. Chọn kỹ thuật

Cần gắn logging vào mọi lời gọi pay nhưng không thay public API. Có nhất thiết dùng structural introduction không?

**Đáp án:** không. Behavioral advice thường phù hợp hơn.

### Câu 13. Trait và đa kế thừa

Có thể gọi mọi mixin trong Java là multiple concrete class inheritance không?

**Đáp án:** không. Java không hỗ trợ một class extends hai concrete superclasses; mixin-like behavior qua interfaces/delegates có semantics khác.

### Câu 14. Runtime type identity

Hai class cùng tên được nạp bởi hai class loaders khác nhau có mặc định là cùng Java runtime type không?

**Đáp án:** không. Class loader identity là một phần của runtime type identity; weaving/casting cần đúng loader scope.

### Câu 15. Interface contract

Một target được introduce Taggable nhưng implementation addTag và tags không nhất quán. Thành công về instanceof có đủ xác nhận thiết kế đúng không?

**Đáp án:** không. Hợp đồng hành vi, state consistency và khả năng thay thế vẫn phải được kiểm thử.

## 39. Checklist cuối cùng

- [ ] Phân biệt rõ inheritance, mixin, introduction và delegation.
- [ ] Biết object nào thật sự mang interface mới.
- [ ] Không nhầm proxy surface với class-level weaving.
- [ ] Có hợp đồng kiểu và hành vi xác định.
- [ ] Kiểm tra giới hạn một superclass trực tiếp của Java class.
- [ ] Có quy tắc giải quyết trùng method/field.
- [ ] Xác định state lifetime per-target/per-proxy/per-instance.
- [ ] Không dùng singleton state cho dữ liệu riêng target hoặc request.
- [ ] Đã xem xét concurrency và GC retention.
- [ ] Đã xét binary compatibility và load-time scope.
- [ ] Không giả định mọi công cụ hỗ trợ mọi introduction.
- [ ] Có test dương/âm về target selection.
- [ ] Có test casting trên target và proxy khi thích hợp.
- [ ] Có test default-method conflicts, overriding và generics erasure.
- [ ] Có integration test với build/runtime thật.
- [ ] Tài liệu hóa điều kiện và giới hạn để người dùng API không hiểu nhầm.

## 40. Tổng kết

**Kế thừa** diễn đạt quan hệ subtype và tái sử dụng theo hệ phân cấp. **Mixin** diễn đạt tái sử dụng một nhóm hành vi, có thể hiện thực bằng default methods, delegation, traits hoặc các cơ chế ngôn ngữ khác. **Mở rộng cấu trúc trong AOP** dùng một cơ chế introduction tương ứng để đưa interface, member hoặc quan hệ kiểu mới vào mô hình của những lớp đích, nếu công cụ hỗ trợ.

Những phân biệt phải nhớ:

- **Thêm advice không đồng nghĩa thêm API cấu trúc.**
- **Proxy implementing interface không làm class gốc tự implements interface.**
- **Mixin không mặc định là multiple concrete class inheritance.**
- **Java default methods có quy tắc conflict/dispatch rõ, không do thứ tự ghi tùy ý.**
- **State ownership quyết định dữ liệu được chia sẻ per-target hay per-proxy.**
- **Class loading/weaving phase quyết định khả năng hiện diện của structural members.**
- **Casting, reflection, method resolution, generics và binary compatibility phải được kiểm chứng theo runtime thật.**
- **Một cấu trúc hợp lệ về kiểu vẫn phải bảo toàn hợp đồng hành vi và thread safety.**

**Câu hỏi thiết kế quyết định:** *Chúng ta muốn một quan hệ subtype thật, một nhóm hành vi có thể tái sử dụng hay một API mới được đưa vào những lớp sẵn có từ bên ngoài — và caller đang tương tác với original object, proxy view hay một class đã được weave?*
