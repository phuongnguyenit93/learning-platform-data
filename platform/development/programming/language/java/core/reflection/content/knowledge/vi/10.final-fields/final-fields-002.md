# Điều kiện giới hạn khi Field.set gặp final trong Java Reflection

Một trường (field) có từ khóa **final** được thiết kế để chỉ nhận giá trị trong quá trình khởi tạo hợp lệ theo quy tắc Java. Khi dùng Reflection, bạn vẫn có thể lấy đối tượng java.lang.reflect.Field và đọc giá trị của trường. Tuy nhiên, **đọc được Field, thậm chí gọi thành công setAccessible(true), không đồng nghĩa Field.set có quyền sửa giá trị final**.

Trong Java 17, một số **instance final field** của class thông thường vẫn có thể bị sửa bằng deep reflection theo điều kiện rất chặt; nhưng **static final**, final trong **record** và final trong **hidden class** là các trường **non-modifiable**, không thể ghi bằng Field.set. Từ JDK 26, những lần sửa final field bằng deep reflection còn chịu chính sách cảnh báo/giới hạn mới, hướng đến cấm mặc định trong các bản Java tương lai.

Mục tiêu bài học: nhận biết trường hợp được phép hoặc bị chặn khi gọi Field.set, dự đoán exception, phân biệt quyền truy cập với quyền ghi, kiểm tra tác động của modules và chọn cách thiết kế an toàn thay cho sửa final sau khởi tạo.

## 1. final trong mã nguồn khác gì với Reflection?

Ví dụ:

~~~java
class Order {
    private final int id;

    Order(int id) {
        this.id = id;
    }

    int id() {
        return id;
    }
}
~~~

Mã Java thông thường không cho phép viết order.id = 100 sau constructor vì trường được khai báo final. Reflection có hai bước riêng:

1. Lấy metadata: Field field = Order.class.getDeclaredField("id").
2. Truy cập hoặc ghi: field.get(order), field.set(order, 100), có thể cần field.setAccessible(true).

**getDeclaredField** cho phép tìm field private đã khai báo trực tiếp trong lớp, nhưng bản thân nó không cấp quyền đọc/ghi. **setAccessible(true)** yêu cầu tắt các kiểm tra truy cập theo ngôn ngữ Java đối với Field đó, trong phạm vi quyền module cho phép. Nó **không loại bỏ các loại final bị Java đánh dấu là không thể ghi**.

Điều này phải tách thành ba câu hỏi:

- Có tìm đúng Field và đối tượng đích không?
- Caller có được phép thực hiện thao tác Reflection hay không?
- Field thuộc loại final có thể sửa trong runtime/phiên bản JDK đang chạy hay không?

Chỉ khi cả ba điều kiện đều phù hợp, Field.set mới có cơ hội hoàn thành. Việc sửa thành công không có nghĩa hành vi của chương trình sau đó luôn quan sát được giá trị mới.

## 2. Quy tắc Field.set đối với final trên Java 17

Theo API Java SE 17, để **ghi một final field bằng Field.set(Object, Object)**, các điều kiện sau phải đồng thời đúng:

1. **setAccessible(true) đã thành công trên chính Field này**.
2. Field là **instance field**, tức **không phải static**.
3. Lớp khai báo field **không phải hidden class**.
4. Lớp khai báo field **không phải record class**.
5. Object đích phù hợp, giá trị truyền vào có thể gán/chuyển đổi hợp lệ cho kiểu của field, và không có rào cản runtime bổ sung.

Khi thiếu một trong các điều kiện ghi final ở trên, Field.set có thể ném **IllegalAccessException**. Nếu quyền truy cập đã bị chặn ngay ở setAccessible(true), ngoại lệ thường gặp là **InaccessibleObjectException**. Nếu giá trị hoặc đối tượng không phù hợp, có thể gặp **IllegalArgumentException**; nếu truyền null cho instance field cần receiver, có thể gặp **NullPointerException**.

| Loại field | Ví dụ | setAccessible(true) có thể cho đọc? | Field.set ghi final trên Java 17? |
| --- | --- | --- | --- |
| Instance final trong class thông thường | private final int id | Có, nếu quyền truy cập cho phép | **Có điều kiện**, với các hạn chế trên |
| Static final của class | private static final String NAME | Có, nếu quyền truy cập cho phép | **Không** |
| Static final trong interface | String NAME = "x" | Có theo visibility/quyền truy cập | **Không** |
| Instance final của record | record User(int id) | Có, nếu quyền truy cập cho phép | **Không** |
| Final field trong hidden class | field final của lớp tạo qua Lookup.defineHiddenClass | Có, nếu quyền truy cập cho phép | **Không** |
| Instance non-final thông thường | private int count | Có, nếu quyền truy cập cho phép | Có thể, theo quyền truy cập và quy tắc kiểu |

**Chú ý:** bảng này nói về thao tác **Field.set** của Java Reflection, không kết luận về tất cả cơ chế như Java bytecode, JNI, serialization internals hoặc API đặc biệt khác. Không dùng mẹo dựa vào Unsafe hoặc sửa cờ Modifier để lách các ràng buộc: những cách đó không phải hợp đồng API ổn định.

### Non-modifiable final field nghĩa là gì?

JDK 17 xác định ba nhóm **không thể ghi qua Field.set**:

- Mọi **static final** (trong class hoặc interface).
- Mọi **final field khai báo trong hidden class**.
- Mọi **final field khai báo trong record class**.

Với các nhóm này, setAccessible(true) nếu được cho phép chỉ giúp Reflection **đọc** field không public; nó **không chuyển** field thành writable.

Một record như record Customer(int id) tự có instance component field tương ứng private final. Dù có lấy được Field("id"), Field.set vẫn không được phép sửa nó.

## 3. Ví dụ Java 17+ có thể biên dịch và chạy

Lưu toàn bộ đoạn dưới đây vào **FinalFieldRulesDemo.java**. Ví dụ cố tình thử bốn trường hợp: sửa instance final thông thường, ghi static final, ghi final của record và truyền sai kiểu dữ liệu.

~~~java
import java.lang.reflect.Field;
import java.lang.reflect.Modifier;

public class FinalFieldRulesDemo {
    static final class Invoice {
        private final int id;

        Invoice(int id) {
            this.id = id;
        }
    }

    static final class Settings {
        private static final String VERSION = "v1";
    }

    record Receipt(int id) {}

    public static void main(String[] args) throws ReflectiveOperationException {
        Invoice invoice = new Invoice(1);
        Field instanceField = Invoice.class.getDeclaredField("id");
        System.out.println("instance final = "
                + Modifier.isFinal(instanceField.getModifiers()));
        instanceField.setAccessible(true);
        instanceField.set(invoice, 42);
        System.out.println("instance Field.get = " + instanceField.getInt(invoice));

        Field constantField = Settings.class.getDeclaredField("VERSION");
        constantField.setAccessible(true);
        try {
            constantField.set(null, "v2");
        } catch (IllegalAccessException ex) {
            System.out.println("static final = " + ex.getClass().getSimpleName());
        }

        Field recordField = Receipt.class.getDeclaredField("id");
        recordField.setAccessible(true);
        try {
            recordField.set(new Receipt(3), 9);
        } catch (IllegalAccessException ex) {
            System.out.println("record final = " + ex.getClass().getSimpleName());
        }

        try {
            instanceField.set(invoice, "text");
        } catch (IllegalArgumentException ex) {
            System.out.println("wrong value type = " + ex.getClass().getSimpleName());
        }
    }
}
~~~

Biên dịch/chạy bằng JDK 17–25, hoặc chạy bằng JDK 21 để tái lập đúng stdout sau đây:

~~~bash
javac --release 17 -encoding UTF-8 FinalFieldRulesDemo.java
java FinalFieldRulesDemo
~~~

Stdout được kiểm tra bằng cách biên dịch với **--release 17** và chạy trên JDK 21:

~~~text
instance final = true
instance Field.get = 42
static final = IllegalAccessException
record final = IllegalAccessException
wrong value type = IllegalArgumentException
~~~

Giải thích theo từng bước:

1. Modifier.isFinal(instanceField.getModifiers()) trả true: metadata xác nhận instance field id có modifier final.
2. instanceField.setAccessible(true) thành công vì ví dụ đang nằm trong cùng chương trình/module có quyền cần thiết. Trên JDK 21, Field.set(invoice, 42) ghi được vào **instance final của class thường**, Field.getInt trả 42.
3. Settings.VERSION là **static final**. Ngay cả sau setAccessible(true), Field.set(null, "v2") ném IllegalAccessException; đối số receiver null vốn hợp lệ với static field, nên lỗi nằm ở quyền ghi final.
4. Receipt.id là **record final**. setAccessible(true) không biến nó thành writable; Field.set ném IllegalAccessException.
5. Instance id có kiểu int. Truyền chuỗi "text" không thể unbox/widen thành int, nên Field.set ném IllegalArgumentException.

**Giới hạn của ví dụ:** chỉ kết luận Field.get quan sát 42 ngay sau thao tác thành công trên JDK được kiểm thử. Đừng coi đây là lời bảo đảm mọi đoạn code đã biên dịch, thread khác hoặc JVM/JIT khác đều nhìn thấy 42 qua getter hay truy cập trực tiếp. Trên JDK 26, lệnh sửa instance final trong ví dụ có thể phát **cảnh báo trên stderr** theo chính sách mới; phần stdout được ghi riêng để tránh nhầm lẫn.

## 4. setAccessible, trySetAccessible và quyền module

Trước khi gọi Field.set, kiểm tra lớp và module thực sự chứa field. Trong **Java Platform Module System (JPMS)**, các chỉ thị có vai trò khác nhau:

- **requires** tạo quan hệ module readability; nó không tự mở private member để Reflection.
- **exports package** cho phép dùng public API ở package đó từ các module đọc thư viện; nó không tự cho quyền truy cập private field.
- **opens package** hoặc **opens package to target.module** cho phép deep reflection trong phạm vi module được mở, gồm khả năng yêu cầu setAccessible(true) trên private field.

Ví dụ module chứa entity:

~~~java
module com.example.data {
    exports com.example.data.api;
    opens com.example.data.entity to com.example.json;
}
~~~

Module com.example.json có thể yêu cầu mở quyền truy cập reflective vào các field của com.example.data.entity. Nhưng nếu field thuộc loại **static final** hoặc **record final**, opens vẫn **không biến nó thành writable**. Nếu field là ordinary instance final, opens có thể thỏa điều kiện truy cập; còn các giới hạn final của Field.set và JDK vẫn áp dụng.

Ở một package không được mở cho caller module, ví dụ:

~~~java
Field field = someClass.getDeclaredField("value");
field.setAccessible(true); // có thể ném InaccessibleObjectException
~~~

Đây là **đoạn minh họa**; someClass phải là Class<?> đã xác định ở ngữ cảnh gọi, không phải chương trình độc lập.

Thay bằng:

~~~java
if (field.trySetAccessible()) {
    // Được phép yêu cầu bỏ qua kiểm tra access; chưa chắc ghi được nếu field final.
} else {
    // Module/package hoặc kiểm soát truy cập không cho phép.
}
~~~

trySetAccessible() thường trả false thay vì ném InaccessibleObjectException khi không thể bật accessibility (nhưng các exception an ninh đặc biệt vẫn có thể tồn tại). Thành công của trySetAccessible() **không đồng nghĩa Field.set chắc chắn thành công**. Cần tách lỗi ở giai đoạn mở quyền và lỗi ở giai đoạn ghi.

Để chẩn đoán:

~~~java
Class<?> owner = field.getDeclaringClass();
Module ownerModule = owner.getModule();
Module callerModule = YourCaller.class.getModule();
System.out.println(ownerModule.isOpen(owner.getPackageName(), callerModule));
~~~

Đây cũng là một đoạn minh họa; thay YourCaller bằng class thực hiện Reflection. **Module.isOpen** giúp kiểm tra ranh giới package, không quyết định riêng một field final có ghi được không. Với class và caller ở cùng module, các quy tắc truy cập có thể khác trường hợp hai named modules riêng biệt.

Tùy chọn **--add-opens source.module/package=target.module** có thể cấp quyền deep reflection lúc khởi chạy khi phù hợp, nhưng **không** cho phép ghi các field non-modifiable final. Và từ JDK 26, **--add-opens cũng không thay thế quyền final-field mutation bổ sung** được đề cập ở mục 7.

## 5. Phân biệt từng loại lỗi khi Field.set thất bại

| Hiện tượng | Điểm thất bại | Nguyên nhân thường gặp | Hướng giải quyết |
| --- | --- | --- | --- |
| NoSuchFieldException | getDeclaredField/getField | Sai tên hoặc tìm nhầm lớp; getDeclaredField không tìm field kế thừa | Chọn đúng declaring class/tên field |
| InaccessibleObjectException | setAccessible(true) | Package trong named module không opens cho caller | Xem module-info.java và quyền opens phù hợp |
| trySetAccessible() trả false | trySetAccessible() | Không thể bật suppression theo access/module rules | Dùng API public hoặc điều chỉnh quyền có chủ đích |
| IllegalAccessException | Field.set | Không đủ quyền ghi; hoặc final thuộc loại không được sửa | Kiểm tra final/static/record/hidden và accessible flag |
| IllegalArgumentException | Field.set | Receiver sai class hoặc kiểu giá trị không thể chuyển hợp lệ | Dùng đúng object và đúng kiểu field |
| NullPointerException | Field.set | Receiver null với instance field | Truyền instance thực |
| Cảnh báo final field mutation (JDK 26) | Lúc đột biến final được phát hiện | Deep reflective mutation chưa được cho phép rõ ràng | Di chuyển logic khởi tạo; khi bắt buộc thì xem JEP 500 |

**Ví dụ:** Field f có kiểu int có thể nhận Integer qua unboxing và một số chuyển đổi nguyên thủy *widening* được hỗ trợ. Nhưng không được chuyển tùy tiện từ String thành int, cũng không mặc định thực hiện narrowing conversion như long xuống int. Có thể dùng phương thức chuyên biệt Field.setInt(...) nếu phù hợp, nhưng **nó cũng không vượt qua hạn chế final**.

### Kiểm tra modifier và declaring class

Dùng mã phụ trợ sau khi đã có Field:

~~~java
int modifiers = field.getModifiers();
boolean isFinal = Modifier.isFinal(modifiers);
boolean isStatic = Modifier.isStatic(modifiers);
boolean inRecord = field.getDeclaringClass().isRecord();
boolean inHidden = field.getDeclaringClass().isHidden();
~~~

Đây là đoạn code minh họa, cần import java.lang.reflect.Field và java.lang.reflect.Modifier và biến field. Một quy tắc tự kiểm tra là: nếu isFinal và (isStatic hoặc inRecord hoặc inHidden), **đừng gọi Field.set để mong sửa field ấy**. Ngay cả khi các điều kiện trên đều false, vẫn phải xét quyền truy cập, phiên bản Java và rủi ro mutation của instance final.

## 6. Vì sao sửa instance final thành công vẫn nguy hiểm?

Java cho phép một số ngoại lệ reflective phục vụ công cụ tái dựng đối tượng hoặc deserialization, nhưng **final không được thiết kế như biến cấu hình có thể sửa tùy thời điểm**. JDK 17 mô tả việc sửa final bằng Reflection chỉ có ý nghĩa trong các kịch bản reconstruction/deserialization phù hợp, trước khi đối tượng được các thành phần khác sử dụng.

### Giá trị có thể không được mọi code quan sát như nhau

Xét ví dụ mang tính giải thích (không dự đoán stdout):

~~~java
class Flags {
    final int mode = 1;

    int mode() {
        return mode;
    }
}
~~~

Compiler và JIT có thể tận dụng tính bất biến của final; một lệnh gọi getter hoặc mã đã tối ưu hóa có thể tiếp tục sử dụng giá trị cũ dù Reflection đã sửa ô nhớ. Đặc biệt với **compile-time constants** là final primitive/String khởi tạo bằng biểu thức hằng, Java có thể thay thế tham chiếu bằng hằng ngay từ bytecode của consumer.

Vì vậy:

- Không dùng Field.get ngay sau khi set như bằng chứng thay đổi sẽ phản ánh ổn định ở tất cả code.
- Không xây dựng tính đúng đắn nghiệp vụ dựa trên sửa một final đã công bố cho thread khác.
- Không dùng Reflection để đổi static final constant rồi trông chờ toàn bộ chương trình nhìn thấy thay đổi; Field.set thậm chí từ chối ghi loại này.
- Sửa final sau khởi tạo phá vỡ giả định tối ưu hóa, bất biến và có thể làm suy yếu các bảo đảm về an toàn công bố đối tượng.

### Vấn đề thread và Java Memory Model

Quy tắc final field của Java Memory Model có ý nghĩa đặc biệt tại lúc hoàn tất khởi tạo đối tượng qua constructor. Các bảo đảm đó không phải giấy phép cho một thread sửa final tùy ý rồi chờ mọi thread khác thấy giá trị mới. Field.set thành công là một thao tác reflective, **không phải giao thức đồng bộ hóa** thay thế happens-before, volatile hoặc synchronized.

Nếu dữ liệu thật sự cần thay đổi theo thời gian, hãy thiết kế nó bằng field thông thường kết hợp cơ chế đồng bộ thích hợp; nếu cần giữ dữ liệu bất biến, hãy tạo instance mới bằng constructor hoặc factory method. Đừng xem final thành một kiểu mutable field ẩn.

## 7. Lưu ý mới từ JDK 26: JEP 500 – Prepare to Make Final Mean Final

Quy tắc ở mục 2 mô tả khả năng của **Java SE 17**. Cần phân biệt nó với một thay đổi khi chạy trên JDK hiện đại.

Từ **JDK 26**, JEP 500 bổ sung cơ chế phát hiện việc **mutate final instance fields thông qua deep reflection**. Theo chế độ mặc định ở JDK 26, lần mutation bất hợp lệ bởi một module có thể tiếp tục chạy nhưng phát **cảnh báo**. Mục tiêu được JDK công bố là một bản phát hành sau sẽ chuyển mặc định sang **từ chối thao tác**, trừ khi ứng dụng cấp quyền tường minh cho module thực hiện mutation.

Các tham số liên quan:

- **--enable-final-field-mutation=ALL-UNNAMED**: cho phép code trong unnamed module (ứng dụng trên classpath) thực hiện kiểu mutation này khi các điều kiện truy cập khác cũng thỏa mãn.
- **--enable-final-field-mutation=module.one,module.two**: cấp cho các named module được chỉ định thực hiện final-field mutation theo chính sách JDK 26.
- **--illegal-final-field-mutation=warn**: cho phép nhưng cảnh báo, là chế độ mặc định của JDK 26 đối với mutation chưa được cấp quyền.
- **--illegal-final-field-mutation=debug**: cảnh báo kèm stack trace, hữu ích để tìm library đang sửa final.
- **--illegal-final-field-mutation=deny**: từ chối mutation không được cấp phép và dẫn đến IllegalAccessException.
- **--illegal-final-field-mutation=allow**: cho phép mà không cảnh báo, chỉ nên coi là biện pháp chuyển tiếp.

Ví dụ minh họa **chỉ dùng với Java 26+**, giả sử ứng dụng ở classpath thật sự phải thực hiện mutation sau khi đã xét quyền truy cập:

~~~bash
java --enable-final-field-mutation=ALL-UNNAMED FinalFieldRulesDemo
~~~

Hoặc chủ động kiểm thử ứng dụng theo chính sách nghiêm ngặt của JDK 26:

~~~bash
java --illegal-final-field-mutation=deny FinalFieldRulesDemo
~~~

Nếu thực hiện lệnh deny không kèm quyền --enable-final-field-mutation phù hợp, ví dụ ở mục 3 có thể thất bại sớm tại instanceField.set(invoice, 42) với IllegalAccessException, nên **không dùng stdout JDK 21 làm dự đoán cho lần chạy đó**.

**Hai lớp điều kiện độc lập:** module sở hữu field vẫn phải mở package thích hợp cho caller qua opens/--add-opens (hoặc trường hợp truy cập được phép khác); đồng thời JDK 26 có thể đòi cấp phép mutation cho module caller. --enable-final-field-mutation không tự mở package, và **không biến static final/record final/hidden-class final thành writable**.

Chính sách này giúp các thư viện serialization/DI dần bỏ phụ thuộc vào việc sửa final đã tồn tại. Nếu bảo trì dự án chạy nhiều JDK, hãy thử bản mới, xem stderr và nâng phiên bản library trước khi cân nhắc bất kỳ tùy chọn cấp quyền nào.

## 8. Cách thiết kế thay thế Reflection để giữ final đúng nghĩa

### Đặt dữ liệu tại thời điểm khởi tạo

~~~java
public record UserProfile(String name, int level) {
    public UserProfile withLevel(int nextLevel) {
        return new UserProfile(name, nextLevel);
    }
}
~~~

Đây là class record độc lập có thể dùng trong dự án; khi cần thay đổi level, tạo một UserProfile mới thay vì Field.set lên field của record.

### Constructor, factory, builder

Nếu đối tượng cần các giá trị bắt buộc, truyền chúng qua constructor/factory/builder. Các framework có thể hỗ trợ **constructor-based binding** hoặc **record canonical constructor** thay vì ghi từng private final field sau khi tạo instance. Khi framework cần truy cập non-public constructor ở module khác, vẫn có thể cần opens, nhưng không nhất thiết cần mutation final sau constructor.

### Khi dữ liệu thực sự mutable

Dùng một field non-final với setter có kiểm soát, hoặc tạo object mới khi trạng thái thay đổi. Đối với ứng dụng đa luồng, chọn volatile, AtomicReference, synchronized hay immutable snapshot theo yêu cầu nhất quán thực tế. Đừng né final bằng Reflection để đổi trạng thái âm thầm.

### Với static constants

Muốn đổi cấu hình runtime, dùng nguồn cấu hình hoặc đối tượng cấu hình mutable có cơ chế cập nhật rõ ràng. Không dựa vào chỉnh static final primitive/String, đặc biệt các compile-time constants có khả năng bị inline vào nơi sử dụng.

## 9. Quy trình chẩn đoán từng bước

1. **Tìm đúng Field.** Dùng getDeclaredField(name) trên class khai báo, không giả định nó duyệt superclasses. Với field kế thừa, tìm trên declaring class.
2. **Kiểm tra loại field.** Modifier.isFinal(), Modifier.isStatic(), getDeclaringClass().isRecord(), isHidden(). Nếu final và là static/record/hidden: xem như không thể ghi qua Field.set.
3. **Kiểm tra access.** Ai thực hiện Reflection? Package chứa field có được opens đúng module caller không? Nếu dùng setAccessible(true), lỗi tại đây thường khác lỗi tại Field.set.
4. **Kiểm tra receiver và value.** Instance field cần object thuộc class phù hợp; primitive cần kiểu chuyển đổi được; static field không cần receiver.
5. **Kiểm tra JDK đang chạy.** Khả năng Java 17 khác chính sách mutation JDK 26. Đọc warning/stack trace và thử cấu hình kiểm tra phù hợp khi bảo trì.
6. **Đánh giá tính đúng đắn sau mutation.** Nếu field là final, không dùng kết quả Field.get đơn lẻ để kết luận getter/consumer khác sẽ thấy giá trị mới; ưu tiên sửa kiến trúc đối tượng.

Một quy trình chẩn đoán tốt phân biệt rõ **metadata được tra cứu**, **quyền mở access**, **quyền ghi loại field**, **kiểu dữ liệu**, và **ngữ nghĩa bất biến**. Điều này thường chỉ ra lỗi nằm ở đâu mà không cần mở rộng quyền toàn bộ module.

## 10. Tự kiểm tra

**Câu 1.** private static final int LIMIT = 10; thuộc class thường, field.setAccessible(true) thành công. Field.setInt(null, 20) có thành công không?

**Đáp án:** Không. Đây là static final, thuộc nhóm non-modifiable trên Java 17; setter chuyên biệt không vượt qua giới hạn final.

**Câu 2.** private final int age của class thường, Field.setAccessible(true) thành công; receiver hợp lệ, kiểu truyền phù hợp. Field.set có thể chạy được trên Java 17 không?

**Đáp án:** Có điều kiện. Đây là instance final không thuộc record/hidden class. Tuy nhiên việc sửa sau khi đối tượng được công bố không được bảo đảm quan sát đồng nhất, và JDK 26 còn có chính sách cảnh báo/giới hạn mới.

**Câu 3.** record Book(String title) có field title. Nếu gọi setAccessible(true) được rồi thì Field.set(book, "new") có hợp lệ không?

**Đáp án:** Không. Instance final do record khai báo thuộc nhóm non-modifiable.

**Câu 4.** Một module exports package chứa class nhưng không opens cho module framework muốn ghi private final field. Lỗi có thể xuất hiện từ bước nào?

**Đáp án:** Từ setAccessible(true) vì không có opens (có thể ném InaccessibleObjectException). Thêm exports không thay thế opens; ngay cả khi opens được cấp, vẫn phải kiểm tra loại final và chính sách JDK.

**Câu 5.** Trên JDK 26, mở package với --add-opens liệu đủ để tránh warning final field mutation?

**Đáp án:** Không nhất thiết. Quyền deep reflection và quyền **mutate final** được xét riêng; nếu thật sự cần, phải hiểu --enable-final-field-mutation và --illegal-final-field-mutation.

**Ghi nhớ:** Reflection có thể **đọc** các final field trong phạm vi quyền phù hợp; **Field.set chỉ từng cho phép sửa một số instance final của class thông thường với điều kiện chặt chẽ**. Static final, record final và hidden-class final không thể ghi bằng Field.set. Trên JDK 26+, kiểm tra thêm chính sách final-field mutation và ưu tiên khởi tạo bất biến đúng bằng constructor/factory.

### Tài liệu tham khảo

- Java SE 17, java.lang.reflect.Field – Field.set: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Field.html#set(java.lang.Object,java.lang.Object)
- Java SE 17, AccessibleObject – setAccessible và các final field non-modifiable: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AccessibleObject.html#setAccessible(boolean)
- Java SE 17, Class – isRecord/isHidden: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html
- Java Language Specification §17.5 – final Field Semantics: https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html#jls-17.5
- JEP 500 – Prepare to Make Final Mean Final: https://openjdk.org/jeps/500
- Oracle JDK 26 Migration Guide – Preparing for final Field Mutation Restrictions: https://docs.oracle.com/en/java/javase/26/migrate/preparing-final-field-mutation-restrictions.html
