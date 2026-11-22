# Khai báo liên kiểu (inter-type declaration) trong mô hình AOP phù hợp

## 1. Khai báo liên kiểu là gì?

Trong **lập trình hướng khía cạnh (Aspect-Oriented Programming – AOP)**, một *aspect* mô-đun hóa những mối quan tâm cắt ngang nhiều thành phần. Ta thường biết AOP qua **pointcut** và **advice**: một pointcut lựa chọn các **join point**; advice thực hiện hành vi trước, sau hoặc bao quanh những điểm đó.

**Khai báo liên kiểu (inter-type declaration, ITD)** là một cơ chế khác: aspect có thể **mô tả phần mở rộng cấu trúc của những kiểu khác**. Khi mô hình/công cụ AOP hỗ trợ, một khai báo nằm trong aspect có thể trở thành thành viên hoặc quan hệ kiểu của một class/interface khác sau khi được xử lý bởi compiler hoặc weaver phù hợp.

Những thay đổi cấu trúc có thể gồm:

- Thêm **field** vào kiểu đích.
- Thêm **method** vào kiểu đích.
- Thêm **constructor** vào class đích, theo các ràng buộc công cụ.
- Khai báo kiểu đích **implements** thêm interface.
- Khai báo kiểu đích **extends** một superclass hợp lệ, nếu mô hình ngôn ngữ hỗ trợ và không vi phạm hệ thống kiểu.

**Không phải mọi hệ thống AOP đều có ITD.** Một engine chỉ hỗ trợ proxy/advice khi gọi method có thể **không thay đổi được cấu trúc Java class thực tế**. Vì vậy cụm “trong mô hình AOP phù hợp” có ý nghĩa quan trọng: phải xác minh công cụ có hỗ trợ **structural/static crosscutting**, hình thức weaving và giới hạn Java/runtime tương ứng.

Ví dụ trực giác:

```text
Trước khi có ITD:

Order
  + id()
  + submit()

Sau khi một công cụ hỗ trợ ITD xử lý thành công:

Order
  + id()
  + submit()
  + auditCount()          [introduced method]
  + auditMarks            [introduced field]
  implements Auditable    [introduced parent interface]
```

Đây là mô tả cấu trúc, **không có nghĩa mã `Order.java` gốc phải được sửa trực tiếp**, nhưng artifact dùng để biên dịch/nạp/chạy có thể phải được **woven** thành công.

## 2. Phân biệt ITD với advice: hai chiều cắt ngang

| Câu hỏi | Advice (dynamic crosscutting) | Inter-type declaration (structural/static crosscutting) |
| --- | --- | --- |
| Can thiệp vào cái gì? | Đường thực thi ở join point | Cấu trúc của kiểu đích |
| Thêm method mới vào API? | Không tự động | Có thể, nếu được hỗ trợ |
| Thêm field riêng cho mỗi instance? | Không tự động | Có thể với introduced instance field |
| Thêm quan hệ implements interface? | Không tự động | Có thể với declaration hỗ trợ |
| Thay đổi hành vi method hiện hữu? | Có thể qua before/after/around | Có thể gián tiếp do method/hierarchy mới, nhưng không cùng cơ chế |
| Phụ thuộc call path có qua proxy không? | Với proxy-based advice: thường có | Với ITD đã weave vào class: việc tồn tại thành viên không đòi caller đi qua proxy |
| Kiểm tra lúc nào? | Matching/dispatch ở compile/load/runtime tùy mô hình | Thường ràng buộc kiểu và cấu trúc ở compile/weave/load |
| Rủi ro chính | Lỗi thứ tự, bypass, exception, side effects | Xung đột chữ ký, hierarchy, binary compatibility, initialization, access |

**Advice không mặc nhiên là ITD.** Một around advice có thể trả giá trị khác hoặc thực hiện thêm logic nhưng **không biến đối tượng thành subtype của một interface mới** chỉ vì đã bọc method.

**ITD không mặc nhiên là advice.** Thêm method `auditCount()` không có nghĩa mọi lần gọi `submit()` sẽ tự tăng số đếm. Nếu cần tăng đếm khi một join point xảy ra, có thể kết hợp ITD với advice hoặc để logic cập nhật ở method phù hợp.

## 3. Khi nào nên cân nhắc ITD?

Một số use case hợp lý:

1. **Gắn vai trò (role) vào các type đã có:** nhiều class không có quan hệ cha-con nghiệp vụ nhưng đều có thể đóng vai trò `Auditable`, `Identifiable` hoặc `Observable`.
2. **Thêm hành vi chung có trạng thái per-instance:** ví dụ thêm số đếm audit cho một nhóm class khi hệ thống sở hữu được phạm vi weaving.
3. **Mở rộng một API legacy do mình quản lý** mà không muốn chèn cùng đoạn mã vào nhiều class.
4. **Xây một mixin/role có tính kiểu tĩnh:** consumer có thể thao tác qua interface được giới thiệu sau khi biên dịch phù hợp.
5. **Tách chức năng cắt ngang về một module:** ví dụ trạng thái quan sát, một interface hỗ trợ chẩn đoán, hoặc năng lực debug cho đối tượng được chọn.

Cần thận trọng với những ý tưởng:

- Thêm dữ liệu bí mật vào object ngoài mục đích ban đầu.
- Thay đổi parent class hàng loạt.
- Gắn `Serializable` nhưng chưa thiết kế invariant của object graph.
- Thêm overload giống API vendor có thể thay đổi overload resolution.
- Introduce method chỉ để tránh refactor một interface đáng lẽ do ứng dụng tự thiết kế.
- Dùng ITD để mở khóa class bị hệ thống kiểu Java cố tình hạn chế.

**Chọn ITD khi lợi ích về mô-đun hóa cấu trúc đủ lớn và có thể quản lý được build, weaving, compatibility và ownership.** Không dùng chỉ vì cú pháp ngắn.

## 4. Điều kiện tiên quyết: không phải engine nào cũng hỗ trợ

Trước khi sử dụng, hỏi:

- Công cụ AOP có cho **khai báo member ở kiểu khác** hay chỉ hỗ trợ interception?
- Có hỗ trợ thêm **field/method/constructor** hay chỉ thêm interface?
- Có hỗ trợ `declare parents ... implements` / `extends` không?
- Việc mở rộng được áp dụng ở **source compile-time**, **binary weaving**, **load-time** hay cách khác?
- Những consumer muốn gọi member mới cần được compile với artifact đã weave hay cần compile riêng theo hướng dẫn của engine?
- Compiler/IDE có hiểu cú pháp và symbol ITD không?
- Runtime class loader/module có cho định nghĩa và nạp class sau biến đổi không?
- Có những kiểu không hỗ trợ như `final`/`sealed`/record, JDK system classes, native types hay class của module bị khóa không?
- Có cách kiểm tra class thật sau weaving và rollback khi lỗi không?

Tài liệu và ví dụ dưới đây dùng **AspectJ** làm **một ngôn ngữ hỗ trợ ITD** để nhìn thấy cú pháp cụ thể. Các hệ thống AOP khác có thể dùng annotation, mixin metadata, compiler transform hoặc không có khả năng tương đương.

## 5. Khái niệm “kiểu đích” và “nơi khai báo”

Trong một khai báo như:

```java
public int Order.auditCount() {
    return 0;
}
```

đoạn này là **cú pháp inter-type method đặc thù AspectJ**, không phải khai báo method hợp lệ bên trong class Java bình thường.

Hai vai trò:

- **Declaring aspect:** module chứa khai báo, ví dụ `AuditFeature`.
- **Target type:** type nhận thành viên khi được weave, ví dụ `Order`.

Khi triển khai thành công, người dùng có thể nhìn thành viên ấy như năng lực của `Order` theo quy tắc access và compile visibility của công cụ. Tuy nhiên quyền truy cập của ITD không nhất thiết giống việc chèn thủ công một dòng `private` vào class đích; phải xem ngữ nghĩa visibility của ngôn ngữ ITD.

### 5.1. Receiver `this` bên trong introduced method

Theo ngữ nghĩa AspectJ, trong body của một **inter-type instance method**, `this` chỉ **đối tượng target type đang chạy method**, không phải instance của declaring aspect.

Ví dụ:

```java
public String Order.describe() {
    return "Order:" + this.id();
}
```

Đây là fragment ITD đặc thù AspectJ; `id()` được giả định là method phù hợp của `Order`. Nếu cần truy cập state của chính aspect, phải dùng cơ chế tham chiếu aspect phù hợp; không suy rằng `this` ở đây là aspect instance.

## 6. Giới thiệu một method mới

Inter-type method hữu ích khi muốn một role công khai có hành vi mới:

```java
public int Order.auditCount() {
    return 0;
}
```

Phát biểu: kiểu `Order` được bổ sung một method public trả `int`.

Nhưng production cần hiểu:

- Method có va chạm với method cùng chữ ký đã tồn tại không?
- Có ghi đè hoặc xung đột với method kế thừa không?
- Có thay đổi overload resolution khi method cùng tên tồn tại?
- Nếu method mới truy cập field introduced, field đã được khởi tạo đúng chưa?
- Contract của method mới là gì khi trạng thái target thay đổi?
- Method có được consumer nhìn thấy ở compile time không?

### 6.1. Khác với wrapper method

Một wrapper `OrderView.auditCount()` là method thuộc **wrapper**, không tự biến `Order` thành đối tượng có method đó. Nếu API yêu cầu object thật có thêm member, wrapper không thể được quảng bá là ITD.

### 6.2. Generic methods và overload

Một số ngôn ngữ ITD hỗ trợ generic introduced methods. Ví dụ tài liệu AspectJ mô tả cách thêm method generic vào một type theo cú pháp có tham số kiểu trước return type.

Khi đưa generic vào, cần kiểm tra:

- Type parameter bounds.
- Java erasure và bridge methods.
- Overload với method generic/covariant return có sẵn.
- Checked exceptions được khai báo.
- Source và binary compatibility.
- IDE/compiler nhận biết type signature đã weave.

Không suy rằng một method có tên khác là chắc chắn tránh xung đột nếu **erased signature** trùng.

## 7. Giới thiệu field: trạng thái thật của target hay state ở aspect?

Ví dụ cú pháp AspectJ:

```java
private int Order.auditMarks = 0;
```

Đây là **inter-type instance field** trong mô hình AspectJ: mỗi instance đích hỗ trợ phần state đã introduced. Nó **không phải** một biến singleton trên aspect.

So sánh:

```text
Aspect-wide counter:
  one count shared by aspect instance, tùy lifecycle của aspect

Introduced instance field:
  each Order instance has its own auditMarks state
```

Trường hợp nhiều object:

```text
Order A: auditMarks=1
Order B: auditMarks=3
Order C: auditMarks=0
```

Đây là ví dụ giá trị sau các lượt cập nhật độc lập, không phải output thực thi.

### 7.1. Access modifier của introduced field

Theo ngữ nghĩa AspectJ, `private` trên inter-type member có nghĩa **riêng với declaring aspect**, khác với việc trực tiếp chèn `private field` vào source của target.

- Code bên trong aspect có thể truy cập ITD private phù hợp.
- Code thông thường của target không đương nhiên có quyền nhìn member private-to-aspect.
- Introduced member public có thể trở thành một phần API được thấy rộng rãi.
- Visibility package/default gắn với package của aspect theo quy tắc công cụ, không mặc định là package của target.
- Theo tài liệu ngôn ngữ AspectJ liên quan, **không có protected inter-type member** cùng ngữ nghĩa với introduced public/private/default.

Cần đọc chính xác đặc tả access của compiler đang dùng; không đánh đồng với Java source member.

### 7.2. Khởi tạo field và side effects

Một inter-type field initializer có thể được chạy trong lifecycle tạo object. Theo ngữ nghĩa AspectJ đã công bố, initializer của introduced field chạy trước class-local initializers trong target.

Điều này có hậu quả:

- Field introduced có thể chưa nhìn thấy các giá trị target dự kiến.
- Initialization order phụ thuộc hierarchy và compilation/weaving.
- Không nên thực hiện I/O hoặc gọi method overridable một cách bừa bãi trong initializer.
- Không coi đưa thêm field vào object là một thay đổi không ảnh hưởng lifecycle.

Đặc biệt với **serialization**, object layout và state mới có thể thay đổi cách lưu/khôi phục; phải xem contract serialization cụ thể.

## 8. Giới thiệu constructor

Trong AspectJ có dạng khai báo ITD cho constructor:

```java
public Point.new(int x, int y) {
    this.x = x;
    this.y = y;
}
```

Đây là **mảnh minh họa tool-specific**, giả định `Point` cho phép các truy cập tương ứng và compiler chấp nhận các ràng buộc constructor; không phải code Java chạy trực tiếp bằng `javac`.

Tài liệu AspectJ mô tả introduced constructor làm type đích hỗ trợ thêm constructor, với một số giới hạn quan trọng:

- Không introduce constructor lên interface.
- Có thể xung đột với constructor được compiler tạo ngầm.
- **Inter-type constructor không thể gán giá trị cho `final` variable đã khai báo trong target type**, theo hạn chế của AspectJ.
- Vẫn phải tuân thủ constructor chain và các quy tắc khởi tạo được áp dụng.
- Constructor side effects/lifecycle không được bỏ qua.

### 8.1. Bẫy constructor mặc định

Một class Java không khai báo constructor có **implicit no-arg constructor** trong nhiều trường hợp. Thêm một ITD no-arg constructor không chắc là “thêm mới vì source không viết constructor nào”; nó có thể xung đột với constructor ngầm.

### 8.2. Không “vá” bất biến của class bằng constructor bất kỳ

Nếu target có final fields, validation bắt buộc hoặc yêu cầu factory riêng, một introduced constructor không tự bảo đảm các invariant ấy. Việc thêm constructor là **thay đổi public construction contract** và cần code review tương đương viết constructor trong class.

## 9. Giới thiệu quan hệ implements interface

Một trong những ứng dụng rõ nhất là **role introduction**.

Ví dụ AspectJ:

```java
declare parents: Order implements Auditable;
```

Ý nghĩa: loại `Order` được khai báo triển khai `Auditable` trong mô hình đã được weave. Tất nhiên, hợp đồng interface phải được thực hiện: method có sẵn trên target hoặc được đưa vào bằng ITD (theo quy tắc compiler).

Đây là thay đổi **quan hệ kiểu**, không chỉ thêm một object wrapper đang giữ `Order`.

### 9.1. Khác với Java dynamic proxy

JDK dynamic proxy có thể tạo một instance triển khai interface `Auditable` và giữ `Order` làm target, nhưng **class `Order` gốc không vì vậy implements Auditable**.

```text
ITD role:
  Order class (woven) implements Auditable
  order instanceof Auditable -> có thể true

Interface proxy:
  proxy implements Auditable
  order gốc instanceof Auditable -> không đổi
```

Không được kết luận kết quả của `instanceof` chỉ từ “đã cài AOP”; phải biết class nào đã weave, object nào đang dùng và loader nào định nghĩa type.

### 9.2. Vai trò của interface trong hợp đồng

Nên ưu tiên một interface **có nghĩa nghiệp vụ** và method rõ:

```java
public interface Auditable {
    void markAudited();
    int auditCount();
}
```

Đây là source Java hợp lệ khi lưu trong `Auditable.java`. ITD có thể làm type đích thỏa hợp đồng đó. Đừng thêm một marker interface rỗng chỉ để dễ cast mà không có ngữ nghĩa thực tiễn.

## 10. Giới thiệu quan hệ extends class

Một số ngôn ngữ ITD, như AspectJ, có dạng:

```java
declare parents: SomeType extends NewBaseType;
```

Đây là **cú pháp đặc thù ngôn ngữ AOP**, không phải một câu lệnh Java hợp lệ trong thân class thông thường.

Thay đổi superclass thường rủi ro hơn thêm interface vì Java class đã có chuỗi kế thừa và constructor/behavior phụ thuộc superclass.

Cần xác minh:

- Target và base class có tương thích hệ thống kiểu không?
- Target có là `final`/record/sealed hierarchy bị giới hạn không?
- Có làm mất/chồng chéo contract của superclass hiện hữu không?
- Constructor chain còn hợp lệ không?
- Có xung đột field/method inherited, overload hoặc override không?
- Serialization, equals/hashCode và lifecycle có phụ thuộc superclass cũ không?
- Classloader, module boundary và binary references có chấp nhận hierarchy sau weaving không?

**Không nên coi `declare parents ... extends` là thao tác thay superclass tùy ý, không điều kiện.** Một compiler/weaver nghiêm túc phải kiểm tra nhiều ràng buộc.

## 11. Ví dụ ITD hoàn chỉnh bằng AspectJ (không phải Java thuần)

Phần này cho thấy một cách **đúng bản chất structural crosscutting**: class `Order` không tự khai báo `Auditable`, nhưng aspect bổ sung field, methods và quan hệ implements.

**Tệp `Order.java`:**

```java
public class Order {
    private final String id;

    public Order(String id) {
        this.id = id;
    }

    public String id() {
        return id;
    }
}
```

**Tệp `Auditable.java`:**

```java
public interface Auditable {
    void markAudited();
    int auditCount();
}
```

**Tệp `AuditIntroduction.aj` – cú pháp AspectJ:**

```java
public aspect AuditIntroduction {
    declare parents: Order implements Auditable;

    private int Order.auditMarks = 0;

    public void Order.markAudited() {
        auditMarks++;
    }

    public int Order.auditCount() {
        return auditMarks;
    }
}
```

**Tệp `Demo.java`:**

```java
public class Demo {
    public static void main(String[] args) {
        Order order = new Order("A-1");
        Auditable audit = (Auditable) order;

        System.out.println("id:" + order.id());
        System.out.println("start:" + audit.auditCount());

        audit.markAudited();
        audit.markAudited();

        System.out.println("after:" + audit.auditCount());
        System.out.println("same:" + (order == audit));
    }
}
```

### 11.1. Điều cần thấy

- `Order` trong source không viết `implements Auditable`.
- `AuditIntroduction` khai báo quan hệ implements.
- Aspect đưa `auditMarks` thành state được gắn với mỗi `Order` instance.
- Aspect đưa hai method đúng contract của `Auditable` vào target.
- `Demo` ép chính instance `order` sang `Auditable`; không tạo một wrapper khác.
- `same:true` minh họa reference qua interface và reference qua class đều chỉ tới cùng object.

### 11.2. Công cụ biên dịch bắt buộc

Không thể biên dịch `AuditIntroduction.aj` bằng `javac` thuần. Cần một bản **AspectJ compiler/weaver hỗ trợ source/target Java 17** cùng runtime phù hợp và phải đưa các class liên quan vào phạm vi compile/weave.

Ví dụ **lệnh tham khảo**, phụ thuộc phiên bản công cụ:

```bash
ajc -17 -d out Order.java Auditable.java AuditIntroduction.aj Demo.java
java -cp "out:<duong-dan-aspectjrt.jar>" Demo
```

Lệnh thứ hai minh họa classpath trên hệ điều hành dùng dấu `:`. Với Windows, dùng dấu `;` giữa các entry. Đường dẫn đến `aspectjrt.jar` phải thay bằng đường dẫn thật của phiên bản công cụ đang cài. Nếu dùng build tool, cấu hình nguồn Java và weave class theo tài liệu chính thức của toolchain.

**Không coi câu lệnh trên là lệnh độc lập có thể chạy trên máy chỉ cài JDK**. Phải có `ajc` và AspectJ runtime thích hợp. Tên flag/source level cần được xác minh với phiên bản compiler thực tế; các bản compiler cũ có thể không hỗ trợ Java 17.

Khi toolchain và weaving đúng, **đầu ra logic mong đợi**:

```text
id:A-1
start:0
after:2
same:true
```

Đây là kết quả theo ngữ nghĩa của chương trình minh họa, không phải chứng cứ rằng mọi phiên bản AspectJ/build configuration đã được chạy và kiểm thử ở đây.

### 11.3. Tại sao đây là ITD thay vì advice?

Ví dụ không có `before`, `after` hay `around`. Nó thực hiện **thay đổi cấu trúc**:

1. Một quan hệ implements mới.
2. Một instance field mới.
3. Hai instance methods mới.

Không có quy tắc tăng counter tự động khi `Order.id()` được gọi. Chỉ `markAudited()` chủ động tăng counter. Muốn tự tăng tại một join point, cần logic advice phù hợp hoặc sửa method body được chọn.

## 12. Java 17 standalone: phân biệt adapter/proxy với thay đổi type thật

Vì một bài học Java cần thấy chương trình chạy ngay cả khi không có compiler AOP, ví dụ sau dùng **Java 17 thuần** để so sánh:

- **Adapter** triển khai interface và **giữ target khác**.
- **Subclass được viết rõ trong Java source** có quan hệ subtype với target.
- ITD nếu có sẽ bổ sung khả năng vào type gốc theo mô hình weaving riêng; chương trình Java dưới đây **không thực hiện ITD**.

Tạo file `StructureVsWrapperDemo.java`:

```java
public class StructureVsWrapperDemo {
    interface Auditable {
        void markAudited();
        int auditCount();
    }

    static class Order {
        private final String id;

        Order(String id) {
            this.id = id;
        }

        String id() {
            return id;
        }
    }

    static final class OrderAdapter implements Auditable {
        private final Order target;
        private int marks;

        OrderAdapter(Order target) {
            this.target = target;
        }

        @Override
        public void markAudited() {
            marks++;
        }

        @Override
        public int auditCount() {
            return marks;
        }

        Order target() {
            return target;
        }
    }

    static final class ExtendedOrder extends Order
            implements Auditable {
        private int marks;

        ExtendedOrder(String id) {
            super(id);
        }

        @Override
        public void markAudited() {
            marks++;
        }

        @Override
        public int auditCount() {
            return marks;
        }
    }

    public static void main(String[] args) {
        Order raw = new Order("A-1");
        OrderAdapter adapter = new OrderAdapter(raw);

        System.out.println("raw:type:" + raw.getClass().getSimpleName());
        System.out.println("raw:auditable:" + (raw instanceof Auditable));
        System.out.println("adapter:type:"
                + adapter.getClass().getSimpleName());
        System.out.println("adapter:same-target:"
                + (adapter.target() == raw));

        adapter.markAudited();
        System.out.println("adapter:count:" + adapter.auditCount());
        System.out.println("raw:still:"
                + (raw instanceof Auditable));

        Order extended = new ExtendedOrder("B-2");
        System.out.println("extended:type:"
                + extended.getClass().getSimpleName());
        System.out.println("extended:auditable:"
                + (extended instanceof Auditable));

        Auditable role = (Auditable) extended;
        role.markAudited();
        role.markAudited();
        System.out.println("extended:count:" + role.auditCount());
        System.out.println("extended:same-reference:"
                + (extended == role));
    }
}
```

Biên dịch/chạy chỉ với JDK 17:

```bash
javac StructureVsWrapperDemo.java
java StructureVsWrapperDemo
```

**Stdout xác định:**

```text
raw:type:Order
raw:auditable:false
adapter:type:OrderAdapter
adapter:same-target:true
adapter:count:1
raw:still:false
extended:type:ExtendedOrder
extended:auditable:true
extended:count:2
extended:same-reference:true
```

### 12.1. Ý nghĩa của `raw:still:false`

Tạo `new OrderAdapter(raw)` **không sửa type `Order`** và không làm biến `raw` triển khai interface. Chỉ adapter triển khai interface và giữ tham chiếu tới `raw`.

Đây là khác biệt quan trọng giữa **wrapper/delegation** và **structural introduction**.

### 12.2. Ý nghĩa của `extended:auditable:true`

`ExtendedOrder` được Java source khai báo `implements Auditable`, nên nó là subtype. Tuy nhiên `Order` gốc vẫn không trở thành Auditable.

Một ITD thành công có thể khiến chính `Order` thỏa interface sau weaving, không cần đổi source `Order.java`.

### 12.3. Không nên dùng ví dụ Java thuần để “chứng minh” hành vi của một ITD engine

Java thuần không có cú pháp `public void Order.markAudited()`. Chương trình so sánh **cơ chế thay thế tương tự** về sử dụng object/type, nhưng không thực hiện biến đổi class file. Để kiểm ITD thật, phải xây, weave và chạy ví dụ ở phần trước bằng công cụ tương ứng.

## 13. Vai trò chung trên nhiều class qua interface

Giả sử ba kiểu `Point`, `Line` và `Shape` cần có năng lực `HasLabel` nhưng không chia sẻ superclass thích hợp.

Một số ngôn ngữ ITD cho phép:

1. Khai báo một interface dùng làm role.
2. Khai báo nhiều target type implements interface.
3. Đưa field/method dùng chung vào interface role theo cơ chế ITD của công cụ.

Trong AspectJ, tài liệu minh họa kiểu marker interface được introduced vào nhiều target, sau đó introduce field/method trên interface ấy:

```java
aspect LabelFeature {
    private interface HasLabel {}

    declare parents: (Point || Line || Shape)
        implements HasLabel;

    private String HasLabel.label;

    public String HasLabel.getLabel() {
        return label;
    }
}
```

Đây là **mảnh AspectJ minh họa**, giả định các target types tồn tại; không phải một ứng dụng hoàn chỉnh chạy với `javac`.

Ý nghĩa: mô-đun một role thành **một phần mở rộng dùng chung**, thay vì lặp khai báo field và method cho từng type.

### 13.1. Đừng nhầm với interface field của Java thuần

Trong Java thuần, field khai báo trong interface có quy tắc cố định của ngôn ngữ (`public static final`). Mô hình inter-type member của AspectJ có thể cho phép khai báo **instance field liên quan đến interface role** như một phần khả năng structural weaving.

Đây là tính năng **ngôn ngữ AOP riêng**, không phải bằng chứng rằng Java source interface thuần có thể chứa mutable instance fields.

### 13.2. Tránh pattern target quá rộng

Một type pattern chọn hàng trăm class có thể:

- Gắn thêm role cho những type không thực sự phù hợp.
- Tạo xung đột method/field ở class con.
- Khiến một bản nâng cấp thư viện phát sinh lỗi weave.
- Tác động serialization hoặc reflection trên diện rộng.
- Thay đổi biểu hiện API mà đội sở hữu class không được thông báo.

Ưu tiên target type pattern nhỏ, có review và test compile/weave regression.

## 14. ITD và mô hình kế thừa Java

Java có những ràng buộc cơ bản:

- Một class chỉ có **một superclass** trực tiếp theo hệ thống kế thừa class Java.
- Một class có thể implement nhiều interface hợp lệ.
- `final class` không thể bị subclass trực tiếp bằng cơ chế Java thường.
- Sealed classes/interfaces giới hạn những subtype được phép.
- Records là class với ràng buộc cấu trúc riêng, ngầm final và không cho tự thêm instance field thông thường.
- Một số loại kiểu/binary có giới hạn đặc biệt theo VM, module, compiler hoặc Java language version.

ITD không phải “đặc quyền bỏ qua mọi ràng buộc Java”. Một engine phù hợp phải tôn trọng type safety và những quy tắc VM, hoặc công bố chính xác giới hạn biến đổi hỗ trợ.

### 14.1. Sealed types và permits

Nếu một sealed interface chỉ permit một số implementation, việc introduce nó làm parent cho một class ngoài tập permitted có thể không hợp lệ. Cần kiểm tra **trạng thái hierarchy sau weave** và sự tương thích với ngữ nghĩa của Java version đang dùng.

Không giả định ITD có thể tự thêm type vào sealed hierarchy mà không cần compiler và module coherence.

### 14.2. Record và giá trị bất biến

Một record Java có component fields và các quy tắc construction, equality, serialization riêng. Thêm arbitrary mutable instance field bằng ITD có thể vi phạm giới hạn class-file/ngôn ngữ hoặc không được tool hỗ trợ. Khi cần giữ metadata ngoài record, một **external association map**, event log hoặc wrapper có thể phù hợp hơn, nhưng lại có ownership/GC semantics riêng.

### 14.3. Enum, native và JDK types

Các kiểu đặc biệt hoặc class do hệ thống nạp có thể không thuộc phạm vi weaving. Không suy rằng bất kỳ binary nào cũng biến đổi được chỉ vì có bytecode trên disk. Class loader bootstrap, package/module integrity và ràng buộc JVM có thể ngăn hoặc giới hạn thao tác.

## 15. Khả năng truy cập và quyền sở hữu module

Một introduced method công khai có thể thay đổi API consumer nhìn thấy. Nhưng cần phân biệt:

- Visibility theo ngôn ngữ ITD.
- Java visibility/access flags sau weaving.
- Package chứa aspect và package chứa target.
- Module export/open, access qua reflection.
- Classloader defining type.
- Quyền truy cập field/method private/protected của target.

Trong AspectJ, một aspect **privileged** có khả năng truy cập member không public của type khác theo cơ chế công cụ. Đây là lựa chọn có rủi ro bảo trì và quyền truy cập lớn, không phải yêu cầu bắt buộc cho mọi ITD.

### 15.1. Tránh yêu cầu privileged khi có API công khai đủ dùng

Nếu introduced method chỉ cần gọi `target.id()` public, đừng phụ thuộc private field nội bộ của target khi không cần. Library upgrade có thể đổi field layout nhưng vẫn giữ public API; phụ thuộc vào private details khiến weaving dễ vỡ.

### 15.2. Không tự nhận định JPMS luôn cho phép

Trong Java Platform Module System, `exports` và `opens` kiểm soát khả năng truy cập/reflective access theo module. Việc weaving hoặc định nghĩa class có thể có yêu cầu riêng. Cần thử với **module graph, class loader và packaging giống production**.

Một ví dụ chạy trên classpath đơn giản có thể không đủ chứng minh nó chạy trong named module, plugin loader hay môi trường có signed JAR.

## 16. Va chạm chữ ký và xung đột member

Các tình huống dễ xảy ra:

1. Target đã có một method đúng tên/parameter types mà aspect muốn introduce.
2. Hai aspect cùng introduce method/field công khai có thể nhìn thấy vào cùng type.
3. Một superclass hoặc interface đã có method khiến introduced method gây ambiguous inheritance.
4. Method mới ảnh hưởng overload resolution hoặc generic type erasure.
5. Một field công khai cùng tên tạo mơ hồ khi code truy cập.
6. Target thay đổi trong phiên bản mới, vô tình thêm method/field trùng ITD cũ.

### 16.1. Không coi compile conflict là lỗi nhỏ để bỏ qua

Trong Java, một call site có thể được overload resolution quyết định ở compile time. Thêm overload có thể làm mã nguồn cũ **không còn biên dịch** hoặc chọn method khác sau khi biên dịch lại, ngay cả khi binary cũ vẫn còn chạy.

Vì vậy introduced public members là một **thay đổi API thật** và cần quản lý tương thích.

### 16.2. Tương tác giữa nhiều ITD

Theo đặc tả AspectJ, một số xung đột giữa inter-type members có thể được giải quyết theo quy tắc inheritance hoặc precedence của declaring aspects. Tuy nhiên không nên dựa vào precedence mơ hồ để hợp thức hóa hai declaration cùng chủ đích khác nhau.

Cần:

- Chỉ định một owner cho capability.
- Đánh giá thứ tự/precedence khi thật sự có ý nghĩa.
- Kiểm tra build error/warning.
- Thử full compile/weave với tất cả aspect bật.
- Có test cho lựa chọn overload và dispatch kỳ vọng.

**Precedence của advice** và **xử lý xung đột ITD** là hai mảng ngữ nghĩa liên quan nhưng không thể chỉ dựa trên một câu “aspect A chạy trước aspect B” để hiểu.

## 17. Constructor, initialization và invariant

Một introduced field có default value, nhưng method target có thể quan sát object trong constructor khi state chưa hoàn tất. ITD đặt thêm logic vào initialization chain nên cần kiểm tra:

- Thứ tự field initializer.
- Superclass constructor có gọi method overridable không.
- Target có công bố `this` trước khi hoàn tất init không.
- Introduced method được gọi ở giai đoạn nào.
- Field introduced có thread-safe nếu object được chia sẻ không.
- Có cần idempotent setup hay teardown không.

Một invariant ví dụ:

```text
auditCount >= 0
owner != null before public business operation
```

Nếu introduced field được cập nhật bằng `++` đồng thời trên nhiều thread, **không tự thread-safe**. Java type checking không chứng minh atomicity của phép cập nhật.

### 17.1. Đếm số lần bằng `int++` không phù hợp concurrency nghiêm ngặt

`auditMarks++` trong ví dụ đơn luồng là chủ ý đơn giản. Với counter concurrent cần xem atomic operations/synchronization hoặc chọn mô hình thread confinement.

Không mặc định inter-type instance field “mỗi object có state riêng” đồng nghĩa “state luôn nhất quán trong mọi luồng”.

## 18. Bảo toàn API khi mở rộng cấu trúc

Từ góc nhìn consumer, một thay đổi ITD có thể được xem như:

- Thêm method vào concrete type.
- Thêm interface được triển khai.
- Thêm constructor công khai.
- Thêm field quan sát được qua reflection.
- Thay đổi superclass hoặc inherited methods.

Những thay đổi ấy có thể ảnh hưởng:

- Source compatibility khi biên dịch lại.
- Binary compatibility nếu artifact woven và consumer compile với cấu trúc không đồng bộ.
- Reflection và các thư viện dựa runtime class metadata.
- Serialization/deserialization.
- Dependency injection/lookup theo interface.
- Logging/JSON mapping dựa trên getter.
- Method handles, caches theo class hoặc constructor discovery.

### 18.1. “Thêm method” có thể là breaking change

Dù Java thường chấp nhận thêm method, trong hệ thống có nhiều overload, interface inheritance hoặc reflective mapper, một introduced method mới có thể làm call resolution/serialization thay đổi. Đánh giá bằng compiler và integration tests, không chỉ nhìn diff mã gốc.

### 18.2. Có bản weave nhưng consumer dùng bản chưa weave

Hai module có thể cùng tham chiếu tên `Order` nhưng khác artifact:

```text
Module A compiled against woven Order
Module B loads original unwoven Order
```

Có nguy cơ linkage/typing/runtime error hoặc thiếu method theo ngữ cảnh. Phải bảo đảm **artifact/loader version consistency** và test packaging cuối cùng, đặc biệt khi dùng incremental build, multi-module, shaded JAR hoặc plugin architecture.

## 19. ITD khi biên dịch, weaving và thời điểm nạp class

Các mô hình triển khai có thể khác nhau:

### 19.1. Compile-time weaving

Compiler thấy source target, aspect và khai báo ITD; nó có thể đưa cấu trúc được khai báo vào binary cuối.

Ưu điểm:

- Dễ báo lỗi type conflict khi build.
- Consumer source có thể kiểm kiểu với model đã kết hợp khi build đúng.
- Có thể inspect artifact trước deployment.

Rủi ro:

- Build config phải đưa đủ nguồn và compiler phù hợp.
- Multi-module cần quy định dependency và thứ tự compile/weave.
- IDE không được tích hợp có thể hiểu sai method introduced.

### 19.2. Binary weaving/post-compile weaving

Class files đã được compile trước có thể được một weaver biến đổi thêm.

Cần xác minh:

- Có được chỉnh sửa artifact đó không?
- Class file version có hỗ trợ không?
- Consumer compile dựa trên API nào?
- Digital signature/JAR integrity có bị ảnh hưởng không?
- Metadata, debug symbols hoặc tool instrumentation khác có xung đột không?

### 19.3. Load-time weaving

Class được xử lý lúc nạp theo cấu hình weaver/loader.

Các vấn đề:

- Class đã nạp từ trước có được biến đổi kịp không?
- Parent-first/child-first loader chọn bản nào?
- Module access và bytecode verification có hợp lệ không?
- Instrumentation khác có đua nhau biến đổi class không?
- Nếu consumer đã compile với ITD nhưng runtime không weave class, có lỗi linkage không?

**Không tự cho rằng mọi biến đổi cấu trúc đều có thể áp dụng bằng retransformation sau khi class đã nạp.** Java instrumentation/redefinition APIs có những giới hạn riêng về thay đổi schema (method/field/hierarchy); công cụ phải thực hiện đúng phạm vi được VM hỗ trợ.

## 20. So sánh với mixin, decorator, composition và extension method

| Kỹ thuật | Method xuất hiện trên target class thật? | Thay đổi instanceof của target? | Cần chú ý |
| --- | --- | --- | --- |
| ITD được weave thành công | Có thể có | Có thể khi introduce interface | Compiler/weaver và compatibility |
| Java interface default method | Chỉ khi type triển khai interface theo Java type rules | Chỉ khi type implements interface | Không tự thêm interface vào một type cũ |
| Java subclass viết thủ công | Trên subclass; target superclass gốc không đổi | Instance của subclass có các subtype hợp lệ | Constructor/final/hierarchy |
| Adapter/decorator | Trên adapter/decorator | Target gốc không đổi | Reference và identity khác |
| JDK dynamic proxy | Trên proxy implements interface | Target gốc không đổi | Lời gọi phải qua proxy |
| Mixin library/runtime | Tùy công cụ | Tùy công cụ | Không mặc định là bytecode ITD |
| Static utility method | Không | Không | Caller gọi qua utility/facade |
| Bytecode advice weaving | Không tự thêm member chỉ vì advice chạy | Không tự thay interface | Dynamic vs structural crosscutting |

**Đừng gọi mọi kiểu “thêm hành vi” là ITD.** Nếu dữ liệu được giữ trong `WeakHashMap<Object,State>` bên ngoài target, đó là **association bên ngoài**, không nhất thiết là introduced instance field.

### 20.1. Khi adapter tốt hơn ITD

- Ứng dụng không sở hữu JAR vendor.
- Không thể kiểm soát full compile/weave pipeline.
- Không muốn thay đổi public type structure.
- Chỉ cần thêm role ở một ranh giới API do mình sở hữu.
- Cần dễ gỡ tính năng khi nâng cấp thư viện.
- Muốn hỗ trợ những class bị hạn chế hierarchy.

### 20.2. Khi ITD có giá trị khác biệt

- Các consumer thực sự cần **static type relationship** được introduced.
- Nhiều target types chia sẻ cùng role nhưng không tiện sửa source.
- Cần state per-instance được liên kết trực tiếp với target trong phạm vi công cụ cho phép.
- Build/test/package có thể kiểm soát và xác minh weaving xuyên các module liên quan.

## 21. ITD và aspect lifetime là hai chuyện khác nhau

Một aspect có thể có lifecycle theo singleton, per-object, per-control-flow hoặc mô hình khác tùy engine. Nhưng introduced instance field có ý nghĩa **trạng thái trên target**, không phải mặc định là field trên aspect instance.

Ví dụ:

```text
One aspect instance
  |
  +-- Order A has introduced auditMarks=1
  +-- Order B has introduced auditMarks=3
```

Đừng suy rằng singleton aspect làm tất cả Order cùng một counter. Ngược lại, nếu aspect giữ `static counter` hoặc mutable field của chính aspect thì có thể **chia sẻ** theo lifecycle ấy.

Kiểm thử phải tách:

- State riêng từng target.
- State riêng mỗi aspect instance.
- State static/shared.
- State theo thread/invocation.
- State được lưu ở external registry.

Các mô hình state khác nhau làm ra kết quả concurrency và serialization khác nhau.

## 22. ITD và việc gọi method từ mã đã biên dịch

Một method được introduced có thể được gọi:

- Từ source được compile cùng toolchain hỗ trợ ITD.
- Qua interface introduced sau weaving.
- Qua reflection sau khi class được load đã có member.
- Từ code đã compile trước với một API phù hợp khi runtime giữ đúng class contract.

Không chắc source được compile hoàn toàn bằng `javac` thuần **trước khi** có ITD sẽ biết member mới trong symbol table.

Một tình huống điển hình:

```text
Compile consumer against original Order:
    order.auditCount()  // compiler Java thuần không thấy method

Compile/weave consumer and Order under ITD-aware toolchain:
    method có thể trở thành symbol hợp lệ
```

**Source visibility và runtime classfile visibility là hai pha khác nhau**; phải chỉ rõ compiler nào và artifact nào được consumer dùng. Không chỉ nói “woven class có method nên mọi source Java ở mọi module sẽ tự compile”.

## 23. Xung đột với private method và encapsulation

ITD cần tôn trọng mô hình access. AspectJ còn cung cấp cơ chế privileged aspect, nhưng đó là khả năng quyền cao và có thể tạo coupling với nội bộ target.

Giới hạn thiết kế:

- Không truy cập field private vendor chỉ để tiết kiệm một getter nếu không bắt buộc.
- Không introduce public method tiết lộ state nhạy cảm.
- Không tạo method cùng chữ ký nhưng contract khác với API target.
- Không thay invariants mà đội sở hữu target không biết.
- Không tạo một role làm tăng quyền thao tác vượt security model.
- Không coi `private` của ITD có cùng phạm vi với Java private trong target.

Đây không chỉ là bài toán cú pháp: ITD có thể thay **bề mặt API của class** và do đó cả trust boundary.

## 24. Serialization và persistence

Một introduced field có thể khiến trạng thái bổ sung tồn tại trên object. Nhưng từ đó không thể tự suy rằng:

- Java serialization sẽ lưu đúng field theo phiên bản cũ.
- Thêm interface `Serializable` là đủ để object hợp lệ cho serialization.
- Khôi phục object bỏ qua constructor luôn khởi tạo introduced field như ý.
- ORM hoặc JSON mapper sẽ nhìn field/method theo cách bạn mong đợi.
- Schema persistence tự động cập nhật.
- Version cũ/phiên bản mới của woven binary trao đổi dữ liệu an toàn.

Cần quy định:

1. State introduced có cần bền vững không?
2. Nếu không, có thể coi nó là transient/derived không?
3. Migration khi version thêm/bớt member sẽ như thế nào?
4. Giữ invariant ra sao khi deserialization?
5. Contract của equals/hashCode/toString có phụ thuộc state mới không?
6. Có phản ánh field qua reflection/introspection ngoài chủ đích không?

**ITD thay đổi cấu trúc, không tự quản lý migration.**

## 25. Nhiều aspect cùng mở rộng một type

Một codebase có thể có:

```text
TraceFeature -> Order.traceId
AuditFeature -> Order.auditMarks
CacheFeature -> Order.cacheStatus
```

Nếu mỗi tính năng độc lập và tên/contract rõ, modularity có thể cải thiện. Nhưng nếu:

- Hai aspect introduce cùng public method.
- Một method của feature A dựa vào field private của feature B.
- Parent interface tạo phương thức inherited xung đột.
- Một update thêm method mới vào target và đụng ITD.
- Một feature bị disable nhưng consumer vẫn compile với API introduced.

thì hệ thống có thể lỗi compile/weave hoặc chạy không tương thích.

### 25.1. Thiết kế trách nhiệm sở hữu

Nên có tài liệu:

- Aspect owner.
- Target type pattern cụ thể.
- Introduced member signature và visibility.
- Hợp đồng method/field, initialization.
- Các feature/aspect phụ thuộc.
- Tương thích khi tắt tính năng.
- Điều kiện build/weave cần bật đồng thời.

Không đặt toàn bộ tính đúng đắn vào **thứ tự aspect ngẫu nhiên**.

### 25.2. Thay đổi API qua một feature toggle

Tắt một before advice có thể chỉ đổi hành vi runtime, nhưng tắt một ITD có thể khiến **member hoặc interface biến mất khỏi class**. Đây là thay đổi type schema lớn hơn.

Vì vậy ITD không thích hợp cho một feature flag biến động per-request nếu consumer phụ thuộc static type introduced. Hãy xem nó như một phần cấu hình artifact/deployment nhất quán.

## 26. Kiểm thử ITD ở ba lớp

### 26.1. Compile/weave tests

Kiểm thử rằng:

- Aspect và target compile/weave thành công.
- Interface role được introduced.
- Method/field/constructor được tạo với signature mong đợi.
- Không có xung đột inheritance/erasure/visibility.
- Công cụ báo đúng lỗi với một declaration cố ý không hợp lệ.
- Build thực tế dùng đúng compiler/weaver version.

### 26.2. Runtime behavior tests

Kiểm thử:

- `instanceof`/cast theo role introduced.
- Method introduced chạy đúng và giữ invariant.
- Hai target instances có state introduced độc lập.
- Exception propagation và side effect đúng contract.
- Concurrency phù hợp; không mất update khi dùng chung object.
- Class loader cuối cùng thực sự nạp **woven binary**.
- Reflection chỉ thấy những member intended.
- Constructor mới khởi tạo state đúng nếu có dùng.

### 26.3. Regression/integration tests

Kiểm thử:

- Khởi động ứng dụng/module production-like.
- Consumer compile với exposed APIs.
- Class/module version giữa producer và consumer nhất quán.
- Serialized data cũ còn tương thích nếu được yêu cầu.
- Không xung đột với các aspect khác.
- Không có đổi behavior ngoài dự kiến ở overload/equals/hashCode.
- Tắt/bỏ ITD dẫn tới failure rõ thay vì lỗi ngầm muộn.
- Thư viện vendor nâng cấp không làm type pattern chọn nhầm đối tượng.

## 27. Ma trận kiểm thử nên có

| Ca | Điều muốn chứng minh |
| --- | --- |
| Chưa áp dụng weaving | Source target nguyên bản không có member mới |
| Đã weave thành công | Type đúng hỗ trợ member/interface mới |
| Cast vào interface introduced | Thành công đúng phạm vi |
| Cast ở type không được chọn | Không tự trở thành role |
| Gọi method introduced | Kết quả/side effect đúng |
| Hai instances | Field introduced không lẫn state |
| Constructor introduced | Chuỗi khởi tạo/invariant phù hợp |
| Existing method conflict | Compiler/weaver báo lỗi hoặc xử lý đúng đặc tả |
| Generic erasure clash | Không phát sinh signature trùng ngoài chủ đích |
| Existing superclass/interface | Không phá luật type hierarchy |
| Final/sealed/record | Giới hạn được công cụ kiểm đúng |
| Module/classloader | Artifact nạp đúng ở runtime |
| Consumer biên dịch bằng compiler khác | Không giả định thấy symbol ITD nếu không có metadata đúng |
| Serialization | Versioning và state persistence theo hợp đồng |
| Concurrent updates | Không mất state do race |
| Multi-aspect ITDs | Không xung đột public member/precedence |
| Bỏ một ITD | Consumer được báo breaking change rõ |
| Build sạch vs incremental | Cùng cấu trúc class cuối |
| Binary weaving trên thư viện ngoài | Có quyền và kiểm tra integrity |
| Reflection mapping | Không lộ/thêm property ngoài ý muốn |

### 27.1. Kiểm tra giới hạn bằng negative tests

Một bộ test chỉ chứng minh ITD hoạt động trên class dễ nhất không đủ. Nên có các ca **không được introduce** vào type ngoài scope, không được bỏ qua conflict, và phải thất bại rõ nếu loader không nạp woven binary.

### 27.2. Source vs binary verification

Một số tool có thể hiển thị cấu trúc introduced khác nhau trong decompiler/reflection nhưng ngữ nghĩa vẫn được công cụ bảo đảm. Khi cần xác minh ở mức bytecode, kiểm tra class artifact được đóng gói và chạy thật. Không dựa vào mã Java nguồn chưa weave như bằng chứng cuối.

## 28. Khi nào không nên dùng ITD?

Không nên mặc định dùng ITD nếu:

- Chỉ cần ghi log trước/sau method: **advice** có thể phù hợp hơn.
- Chỉ cần gắn thêm hành vi ở biên API do mình sở hữu: **adapter/decorator** có thể đơn giản hơn.
- Không kiểm soát compiler/weaver hoặc deployment artifacts.
- Target là class không thể cấu trúc lại an toàn theo Java type rules.
- Một SDK vendor thay đổi liên tục và không có hợp đồng binary ổn định.
- Cần bật/tắt capability từng request nhưng client đã compile phụ thuộc interface introduced.
- Có rủi ro serialization, ORM mapping hoặc module access lớn hơn lợi ích.
- ITD chỉ che giấu một vấn đề thiết kế trách nhiệm/ownership đáng lẽ cần refactor.
- Giải pháp phải dễ hiểu bởi các đội chỉ dùng Java compiler và reflection thông thường.

**Giải pháp ít xâm lấn hơn thường đáng ưu tiên**, trừ khi vai trò và type structure bổ sung là một nhu cầu thực sự.

## 29. Các hiểu nhầm thường gặp

**“AOP chỉ có before/after/around.”** Không phải mọi mô hình. Một số ngôn ngữ AOP còn hỗ trợ structural crosscutting, gồm ITD.

**“Một around advice có thể làm target implements interface mới.”** Không tự động. Advice không đồng nghĩa thay type schema.

**“JDK proxy triển khai Auditable nghĩa Order gốc cũng implements Auditable.”** Sai. Proxy và target là những đối tượng/kiểu khác nhau.

**“ITD là sửa source code trực tiếp.”** Không nhất thiết. Công cụ có thể weave class từ source/binary mà không sửa file nguồn.

**“ITD dùng được với mọi engine AOP.”** Sai. Phải có ngôn ngữ/compiler/weaver hỗ trợ.

**“Introduced field là field singleton của aspect.”** Không khi nó được khai báo là instance field trên target.

**“`private` trong inter-type member có nghĩa đúng như private field viết trong target source.”** Không thể suy như vậy; theo AspectJ nó private đối với declaring aspect.

**“Introduced constructor có thể tùy tiện gán final field của target.”** Không với giới hạn được AspectJ công bố.

**“Không viết constructor trong source nghĩa không có constructor để xung đột.”** Sai. Java có quy tắc implicit constructor.

**“Declare parents extends bỏ qua mọi luật kế thừa Java.”** Không. Type hierarchy vẫn phải hợp lệ.

**“Introduce interface là cách bỏ qua sealed permits.”** Không được giả định; cần thỏa quy tắc type/JVM và tool support.

**“ITD chỉ thay đổi behavior, không thay compatibility.”** Sai. Public method/interface/constructor mới là thay đổi cấu trúc API.

**“Dùng compiler AOP một lần là mọi module tự nhìn thấy ITD.”** Không. Các consumer, classloaders và runtime artifacts phải nhất quán.

**“Thêm field là an toàn cho serialization/ORM.”** Không. Có thể đổi layout, reflection, schema và migration.

**“Có role mới nghĩa mọi instance đang chạy đều được biến đổi ngay.”** Không thể mặc định, nhất là class đã load và giới hạn redefinition.

**“Mọi introduced member có thể được xác minh chỉ qua test return value.”** Không. Cần type, reflection, binary, initialization và integration tests.

## 30. Bài tập thực hành

### Bài 1 — Advice hay ITD?

Yêu cầu: trước mỗi lần gọi `Order.submit()`, ghi thời gian bắt đầu. Có nhất thiết cần ITD không?

**Đáp án:** Không. Nếu chỉ quan sát thời điểm chạy, before/around advice thường trực tiếp hơn. Chỉ cân nhắc ITD nếu cần cấu trúc/state mới có ý nghĩa trên type.

### Bài 2 — Role cho class legacy

`Order` không implements `Auditable`; consumer muốn nhận chính instance Order dưới interface Auditable trong artifact woven. Cơ chế nào phù hợp?

**Đáp án:** ITD `declare parents ... implements` cùng method implementations có thể phù hợp nếu engine hỗ trợ và class/weaving hợp lệ. Adapter chỉ làm wrapper implements interface, không đổi type Order.

### Bài 3 — Trạng thái nhiều instance

Introduced field `private int Order.marks`, tạo hai Order và gọi `mark()` hai lần trên object thứ nhất. Object thứ hai có mặc định count bằng 2 không?

**Đáp án:** Không; introduced **instance field** gắn với từng object theo ngữ nghĩa target state. Các lần cập nhật object thứ nhất không mặc định cập nhật object thứ hai.

### Bài 4 — Xung đột method

Sau khi triển khai ITD `Order.auditCount()`, tác giả Order thêm method cùng chữ ký vào version kế tiếp. Điều gì cần làm?

**Đáp án:** Kiểm tra compiler/weaver conflict, quyết định ownership/cấu trúc mới và cập nhật contract; không tùy tiện mặc định hai method cùng tồn tại hay một method luôn thắng.

### Bài 5 — Class final

`FinalOrder` là final nhưng có public API cho phép viết adapter. Có nhất thiết biến nó thành subclass để thêm role?

**Đáp án:** Không thể subclass final bằng Java thông thường. Adapter là lựa chọn tách biệt; ITD thích hợp đến đâu phụ thuộc loại introduction và giới hạn công cụ, không được đoán rằng final có thể bị bỏ qua.

### Bài 6 — Constructor ngầm

Target source không khai báo constructor. Một ITD muốn introduce no-arg constructor. Có chắc không conflict?

**Đáp án:** Không. Java có implicit default constructor khi điều kiện phù hợp; cần kiểm tra chữ ký và rules của compiler AOP.

### Bài 7 — Java 17 thuần

Vì sao lệnh `javac Order.java AuditIntroduction.aj` không hợp lệ trong ví dụ ITD?

**Đáp án:** `.aj` chứa cú pháp AspectJ, không phải Java source thuần. Cần compiler/weaver hỗ trợ và đúng build configuration.

### Bài 8 — Runtime không weave

Consumer compile thành công với introduced method nhưng runtime nạp `Order.class` nguyên gốc. Hậu quả có thể là gì?

**Đáp án:** Runtime type/member thiếu so với contract lúc compile; có thể có linkage hoặc cast/method resolution error tùy call path. Phải kiểm artifact và loader đúng.

### Bài 9 — Bảo mật

Một introduced public method trả nội dung token private của target. “Chỉ thêm method” có vô hại không?

**Đáp án:** Không. Nó mở rộng API và có thể làm lộ dữ liệu. Phải đánh giá security/ownership/trust boundary.

### Bài 10 — Concurrent counter

Introduced field `int marks` tăng bằng `marks++` trên cùng Order từ nhiều thread. Có chắc số cuối bằng tổng lượt gọi?

**Đáp án:** Không. `++` không bảo đảm atomic update giữa nhiều thread; phải dùng cơ chế đồng bộ/atomic phù hợp nếu contract đòi đếm chính xác.

## 31. Checklist đánh giá trước khi áp dụng ITD

- [ ] Mục tiêu thực sự cần **thay đổi cấu trúc type**, không chỉ can thiệp method invocation.
- [ ] Công cụ đang dùng hỗ trợ đúng kiểu ITD yêu cầu.
- [ ] Đã phân biệt cú pháp tool-specific với Java 17 thuần.
- [ ] Biết declaring aspect và target type, type patterns đủ hẹp.
- [ ] Đã chỉ rõ fields/methods/constructors/parents cần giới thiệu.
- [ ] Đã kiểm type/signature, erasure, overload và inheritance conflicts.
- [ ] Đã kiểm visibility của inter-type member theo ngữ nghĩa công cụ.
- [ ] Không tiết lộ private state qua introduced public API.
- [ ] Đã đánh giá initializer order, constructor chain và invariant.
- [ ] Không tự tin rằng ITD constructor có thể gán final fields target.
- [ ] Đã kiểm final/sealed/record/enum và hierarchy constraints.
- [ ] Đã kiểm source/binary/load-time weaving support.
- [ ] Consumer modules compile với model type đã introduced.
- [ ] Runtime load đúng woven binary; loader/module cấu hình khớp.
- [ ] Không giả định structural redefinition áp được lên class đã load.
- [ ] Có kế hoạch ownership/compatibility khi library upgrade.
- [ ] Có chính sách với nhiều aspects cùng introduce members.
- [ ] Giới hạn reflection, serialization/ORM schema và persistence migration đã được xem xét.
- [ ] Đã kiểm thread safety của introduced mutable state.
- [ ] Có positive/negative compile-time tests và runtime tests.
- [ ] Đã thử với deployment/package/profiles gần production.
- [ ] Đã ghi rõ contract và breaking changes khi thêm/bỏ role.
- [ ] Có phương án rollback/alternative adapter nếu weaving thất bại.
- [ ] Không tự coi proxy/decorator là ITD thật.
- [ ] Đã tham khảo tài liệu chính thức đúng phiên bản compiler đang dùng.

## 32. Tài liệu đối chiếu

Các nguồn sau mô tả **ngữ nghĩa của AspectJ, một công cụ AOP có ITD**. Chúng không làm ITD trở thành tính năng phổ quát của mọi cơ chế AOP:

- [Eclipse AspectJ – Inter-type declarations](https://eclipse.dev/aspectj/doc/released/progguide/language-interType.html): các loại member, `this`, visibility và role introduction.
- [Eclipse AspectJ – Static crosscutting](https://eclipse.dev/aspectj/doc/released/progguide/semantics-declare.html): grammar và quy tắc method/field/constructor/parent declarations, conflicts, initialization, access modifiers.
- [Eclipse AspectJ – Quick reference](https://eclipse.dev/aspectj/doc/latest/progguide/quickreference.html): cú pháp ITD và `declare parents`.
- [Eclipse AspectJ – Roles and views](https://eclipse.dev/aspectj/doc/released/progguide/examples-basic.html): ví dụ role introduction qua các class có sẵn.
- [Java SE 17 – Proxy](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Proxy.html): để đối chiếu dynamic proxy **không thay type của target**.
- [Java Language Specification 17](https://docs.oracle.com/javase/specs/jls/se17/html/index.html): quy tắc kiểu, inheritance, constructor, final và sealed types.

Muốn dùng một compiler/version cụ thể, kiểm tra tài liệu phát hành, hỗ trợ bytecode Java tương ứng và thử compile/weave trên đúng classpath/module path thực tế.

## 33. Kết luận

**Inter-type declaration là cách mô-đun hóa một thay đổi về cấu trúc của kiểu, không chỉ chèn thêm lệnh trước/sau lời gọi.** Khi được compiler/weaver hỗ trợ, aspect có thể giới thiệu fields, methods, constructors và quan hệ implements/extends theo quy tắc ngôn ngữ, giúp những type hiện hữu nhận thêm vai trò hoặc năng lực rõ ràng.

Giá trị lớn nhất là **structural crosscutting có chủ đích**. Nhưng hệ quả đi kèm là trách nhiệm lớn hơn với **type safety, constructor/invariant, hierarchy, visibility, source/binary compatibility, serialization và deployment**.

Hãy xác minh ba điều trước khi áp dụng: **có thực sự cần mở rộng type hay chỉ cần advice/adapter; công cụ AOP có hỗ trợ ITD theo đúng ngữ nghĩa mong muốn không; và toàn bộ consumer–compiler–woven artifact–runtime có nhất quán không**. Một ITD tốt phải vừa tiện mô-đun hóa vừa có thể kiểm chứng được, thay vì đưa một cấu trúc mới vào hệ thống mà không có contract hoặc đường nâng cấp an toàn.
