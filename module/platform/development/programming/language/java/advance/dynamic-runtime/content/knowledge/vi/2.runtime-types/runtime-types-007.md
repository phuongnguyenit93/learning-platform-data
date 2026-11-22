# 2.7 Khám phá lớp cha, interface, nestmate và các lớp con được phép của sealed type

Khi có một đối tượng `Class<?>` ở thời điểm chạy, Java Reflection cho phép tìm hiểu các quan hệ kiểu đã được ghi trong metadata của lớp: lớp cha trực tiếp, những interface được khai báo trực tiếp, các lớp cùng *nest* và các kiểu được phép kế thừa/triển khai một `sealed` type. Bốn quan hệ này có ý nghĩa khác nhau; không nên dùng kết quả của API này để suy luận thay cho API khác.

Bài sử dụng **Java 17+** để bao quát cả nestmate (có từ Java 11) và sealed class/interface (chuẩn hóa trong Java 17).

## 1. Bản đồ các API cần biết

| Cần khám phá | API trên `Class<?>` | Kết quả và ý nghĩa |
| --- | --- | --- |
| Lớp cha trực tiếp | `getSuperclass()` | Một `Class<?>`, hoặc `null` nếu không có superclass theo API |
| Superclass có thông tin generic | `getGenericSuperclass()` | Một `Type`; có thể là `ParameterizedType` |
| Interface khai báo trực tiếp | `getInterfaces()` | Mảng `Class<?>[]`; không tự thu thập tất cả interface kế thừa gián tiếp |
| Interface trực tiếp có generic | `getGenericInterfaces()` | Mảng `Type[]` |
| Lớp chủ của nest | `getNestHost()` | `Class<?>` của nest host; có thể chính là lớp đang xét |
| Các thành viên cùng nest | `getNestMembers()` | Mảng `Class<?>[]` bao gồm nest host và các nestmate được ghi nhận |
| Hai kiểu có cùng nest? | `isNestmateOf(Class<?> other)` | `boolean` |
| Có phải sealed type? | `isSealed()` | `boolean` |
| Các lớp/interface con được phép trực tiếp | `getPermittedSubclasses()` | Mảng `Class<?>[]` nếu sealed, ngược lại `null` |

Tất cả thao tác trên phản ánh thông tin kiểu của JVM. Chúng **không** tự tạo đối tượng, và không có nghĩa là quét toàn bộ classpath để tìm mọi lớp con.

## 2. Khám phá lớp cha: `getSuperclass()`

Với `class Child extends Parent`, `Child.class.getSuperclass()` trả về `Parent.class`. Đây là **một cấp cha trực tiếp**. Muốn đi hết chuỗi superclass, lặp lại trên kết quả cho đến khi nhận `null`.

Các trường hợp dễ nhầm:

- `Object.class.getSuperclass() == null` vì `Object` là gốc của hệ phân cấp class.
- `SomeInterface.class.getSuperclass() == null`, dù một đối tượng triển khai interface vẫn thừa hưởng các phương thức từ `Object` thông qua lớp của nó.
- `int.class`, `void.class` cũng trả về `null`.
- Với một array class như `String[].class`, superclass là `Object.class`; array còn triển khai `Cloneable` và `java.io.Serializable`.
- Một `record` trực tiếp kế thừa `java.lang.Record`; một enum có superclass liên quan đến `java.lang.Enum`.

Ví dụ truy ngược (đây là **đoạn phương thức bổ sung**, đặt trong một class bất kỳ):

~~~java
static void printSuperclassChain(Class<?> type) {
    for (Class<?> current = type;
         current != null;
         current = current.getSuperclass()) {
        System.out.println(current.getName());
    }
}
~~~

Dùng `getSuperclass()` khi chỉ cần quan hệ class thực tế. Nếu khai báo là `class StringBox extends Box<String>` và cần biết đối số kiểu `String`, hãy dùng `getGenericSuperclass()` rồi xử lý `Type`/`ParameterizedType`. `getSuperclass()` chỉ trả về `Class` của `Box`, không giữ đối số generic trong kiểu trả về.

## 3. Khám phá interface: `getInterfaces()`

`getInterfaces()` trả về các interface được khai báo **trực tiếp** trong mệnh đề `implements` của class, hoặc các interface trong mệnh đề `extends` của một interface:

~~~java
interface Audible {}
interface Trainable extends Audible {}
class Parent implements Audible {}
class Child extends Parent implements Trainable {}
~~~

Kết quả:

- `Child.class.getInterfaces()` chỉ chứa `Trainable`, không có `Audible`.
- `Parent.class.getInterfaces()` chứa `Audible`.
- `Trainable.class.getInterfaces()` chứa `Audible`.

Tuy `Audible` không xuất hiện trong mảng interface trực tiếp của `Child`, `Audible.class.isAssignableFrom(Child.class)` vẫn là `true`. Quan hệ gán được tính xuyên qua superclass lẫn superinterface.

Muốn thu thập **toàn bộ interface liên quan**, phải duyệt cả interface cha và superclass, đồng thời loại trùng. Đoạn helper sau sử dụng `java.util.Set` và **không phải chương trình độc lập**:

~~~java
static void collectAllInterfaces(Class<?> type, java.util.Set<Class<?>> found) {
    if (type == null) return;

    for (Class<?> direct : type.getInterfaces()) {
        if (found.add(direct)) {
            collectAllInterfaces(direct, found);
        }
    }
    collectAllInterfaces(type.getSuperclass(), found);
}
~~~

Có thể gọi `collectAllInterfaces(Child.class, new java.util.LinkedHashSet<>())` để thu được cả `Trainable` và `Audible`. `Set` tránh lặp hoặc xử lý lại cùng một interface trong mô hình kim cương. Với generic, `getGenericInterfaces()` trả về `Type[]` để giữ phần khai báo như `Supplier<String>` thay vì chỉ lấy `Supplier.class`. Khi kiểm tra khả năng gán ở runtime, ưu tiên `isAssignableFrom` thay vì tự suy đoán từ tên interface.

## 4. Nestmate: quan hệ cùng nest, không phải kế thừa

Từ Java 11, JVM hỗ trợ **nest**: một nhóm class/interface cùng runtime package được class file xác định có chung *nest host*. Các thành viên này là **nestmate** và có quyền truy cập các thành viên `private` của nhau theo quy tắc truy cập JVM.

Ví dụ, trình biên dịch Java thường đặt class ngoài cùng `House` làm nest host và class lồng `House.Room` làm một nestmate. Khi đó:

- `House.Room.class.getNestHost()` trả về `House.class`.
- `House.class.getNestMembers()` chứa `House` và `House.Room`.
- `House.Room.class.isNestmateOf(House.class)` trả về `true`.
- `House.Room` có thể đọc một field `private` của `House` mà không phải sử dụng `setAccessible(true)`.

Một class không tham gia nest nhiều thành viên thường là nest host của chính nó. Quan hệ này đến từ metadata class file (`NestHost`/`NestMembers`), **không** được xác định bằng `extends` hoặc `implements`. Hai class cùng superclass không nhất thiết là nestmate; hai class cùng nest cũng không nhất thiết có quan hệ kế thừa.

Đừng nhầm các API:

| API | Trả lời câu hỏi |
| --- | --- |
| `getDeclaringClass()` | Class/interface nào *khai báo* một member class? (Có thể `null` đối với top-level/local class.) |
| `getEnclosingClass()` | Một class được khai báo trong phạm vi class nào? |
| `getNestHost()` | Ai là host của *nest* theo JVM? |
| `getNestMembers()` | Những kiểu nào được ghi nhận cùng nest? |

`getNestMembers()` không bảo đảm thứ tự các phần tử ngoài nest host và có thể chứa bản ghi trùng; đừng phụ thuộc vào thứ tự khi so sánh hoặc hiển thị. Những *hidden class* được thêm động vào nest cũng không nhất thiết xuất hiện trong mảng này.

## 5. Sealed type và `getPermittedSubclasses()`

`sealed` giới hạn **những kiểu nào được phép trực tiếp** kế thừa một sealed class hoặc mở rộng/triển khai một sealed interface. Trong Java 17:

~~~java
sealed interface Shape permits Circle, Square {}
final class Circle implements Shape {}
non-sealed class Square implements Shape {}
~~~

`Shape.class.isSealed()` trả về `true`. `Shape.class.getPermittedSubclasses()` trả về các `Class` đại diện cho `Circle` và `Square`. Danh sách này nói về **quyền trở thành subtype trực tiếp**, không phải danh sách mọi đối tượng đang tồn tại hay mọi subtype ở mọi cấp.

Một kiểu trực tiếp mở rộng/triển khai sealed type phải khai báo trạng thái phù hợp: `final` (ngăn kế thừa tiếp), `sealed` (tiếp tục giới hạn nhánh con), hoặc `non-sealed` (mở lại khả năng kế thừa; chỉ hợp lệ ở nhánh trực tiếp của sealed type). Ví dụ, `Square` là `non-sealed` nên các subtype tiếp theo có thể xuất hiện; `Shape.getPermittedSubclasses()` vẫn chỉ liệt kê `Square` ở cấp trực tiếp.

Phân biệt hai kết quả:

- `getPermittedSubclasses() == null`: kiểu đang xét **không phải sealed** (kể cả `final`, interface thông thường, array và kiểu nguyên thủy).
- `getPermittedSubclasses().length == 0`: kiểu đang xét **là sealed** nhưng mảng kiểu con được trả về rỗng; API có thể không trả được một số permitted subtype không tải/kiểm chứng được.

Thứ tự kết quả không được bảo đảm. Nếu cần xem nhiều cấp sealed, tiếp tục duyệt những permitted subtype mà `isSealed()` là `true`. Một nhánh `non-sealed` không có danh sách đóng mọi lớp con qua API này.

## 6. Ví dụ Java 17 chạy hoàn chỉnh

Lưu **toàn bộ** mã sau vào file `TypeDiscoveryDemo.java`. Các class/interface không có `public` phía dưới cùng file thuộc cùng package mặc định và hợp lệ trong Java.

~~~java
import java.util.Arrays;
import java.util.stream.Collectors;

public class TypeDiscoveryDemo {
    private static String names(Class<?>[] types) {
        if (types == null) return "null";
        return Arrays.stream(types)
                .map(Class::getSimpleName)
                .sorted()
                .collect(Collectors.joining(", ", "[", "]"));
    }

    public static void main(String[] args) {
        System.out.println("Child.superclass = " + Child.class.getSuperclass().getSimpleName());
        System.out.println("Child.interfaces = " + names(Child.class.getInterfaces()));
        System.out.println("Parent.interfaces = " + names(Parent.class.getInterfaces()));
        System.out.println("Trainable.superinterfaces = " + names(Trainable.class.getInterfaces()));
        System.out.println("Object.superclass = " + Object.class.getSuperclass());

        System.out.println("Room.nestHost = " + House.Room.class.getNestHost().getSimpleName());
        System.out.println("House.nestMembers = " + names(House.class.getNestMembers()));
        System.out.println("Room.isNestmateOf(House) = " + House.Room.class.isNestmateOf(House.class));
        System.out.println("Room.readPrivate = " + new House.Room().readPrivate(new House()));

        System.out.println("Shape.isSealed = " + Shape.class.isSealed());
        System.out.println("Shape.permits = " + names(Shape.class.getPermittedSubclasses()));
        System.out.println("Square.isSealed = " + Square.class.isSealed());
        System.out.println("Square.permits = " + names(Square.class.getPermittedSubclasses()));
    }
}

interface Audible {}
interface Trainable extends Audible {}
class Parent implements Audible {}
class Child extends Parent implements Trainable {}

class House {
    private final String secret = "private-ok";

    static class Room {
        String readPrivate(House h) {
            return h.secret;
        }
    }
}

sealed interface Shape permits Circle, Square {}
final class Circle implements Shape {}
non-sealed class Square implements Shape {}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac --release 17 TypeDiscoveryDemo.java
java TypeDiscoveryDemo
~~~

Stdout:

~~~text
Child.superclass = Parent
Child.interfaces = [Trainable]
Parent.interfaces = [Audible]
Trainable.superinterfaces = [Audible]
Object.superclass = null
Room.nestHost = House
House.nestMembers = [House, Room]
Room.isNestmateOf(House) = true
Room.readPrivate = private-ok
Shape.isSealed = true
Shape.permits = [Circle, Square]
Square.isSealed = false
Square.permits = null
~~~

Hàm `names` chỉ định dạng tên đơn giản, sắp xếp để đầu ra dễ kiểm tra và xử lý `null`. Trong công cụ thật, dùng `getName()`/`getTypeName()` khi cần tên đầy đủ: hai class ở hai package khác nhau có thể có cùng `getSimpleName()`. Cũng cần nhớ rằng cùng một tên nhị phân được nạp bởi những class loader khác nhau có thể đại diện cho những `Class` khác nhau.

Đọc các dòng quan trọng:

1. `Child.superclass` là `Parent`, còn `Child.interfaces` chỉ là `Trainable` vì API không tự lấy interface từ superclass.
2. `House.nestMembers` bao gồm host; `Room.readPrivate` chứng minh nestmate cho phép truy cập private hợp lệ do trình biên dịch/JVM xử lý.
3. `Shape.permits` có đúng các **con trực tiếp được phép**; `Square.permits = null` vì `Square` là `non-sealed`.

## 7. Cách chọn API khi ứng dụng

- **Kiểm tra class có kế thừa một class nền hay không:** dùng `Base.class.isAssignableFrom(candidate)` cho kết quả kiểm tra quan hệ xuyên cấp. Dùng `getSuperclass()` khi cần vẽ hoặc phân tích từng mắt xích của cây lớp cha.
- **Kiểm tra hợp đồng interface/plugin:** dùng `SomeContract.class.isAssignableFrom(candidate)` để xét quan hệ triển khai; dùng `getInterfaces()` và duyệt đệ quy khi cần trình bày interface nào được khai báo ở từng cấp.
- **Phân tích class lồng và private access:** dùng `getNestHost()`, `getNestMembers()`, `isNestmateOf()`; đừng dùng `getDeclaredClasses()` thay thế vì nó mô tả các khai báo member class, không tương đương metadata nest.
- **Phân tích mô hình miền đóng:** với một sealed class/interface, gọi `isSealed()` trước; sau đó dùng `getPermittedSubclasses()` để xác định danh sách nhánh con hợp lệ trực tiếp. Khi kiểm tra một đối tượng thực tế, vẫn phải kiểm tra kiểu runtime của đối tượng và quan hệ gán tương ứng.

## 8. Lỗi thường gặp và cách tránh

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| `getSuperclass() == null` nghĩa là không liên quan đến bất kỳ kiểu nào | Interface, `Object`, primitive, `void` đều có thể trả `null` theo quy tắc API |
| `getInterfaces()` liệt kê mọi interface, kể cả qua superclass | Nó chỉ liệt kê interface **trực tiếp** của kiểu đang xét; muốn toàn bộ phải duyệt thêm |
| Class lồng và nestmate là hai từ đồng nghĩa | Class lồng là quan hệ khai báo; nestmate là quan hệ truy cập dựa vào metadata JVM |
| Hai kiểu cùng parent sẽ có thể truy cập `private` của nhau | Quyền `private` giữa nestmate phụ thuộc vào nest, không phụ thuộc vào cùng superclass |
| `getPermittedSubclasses() == null` là không có subclass | `null` chỉ nói rằng kiểu **không sealed**; không thể suy ra có hay không các subclass |
| Danh sách `permits` là mọi subtype có thể tồn tại ở mọi cấp | Nó chỉ chứa những **subtype trực tiếp được phép**; nhánh `non-sealed` còn có thể mở rộng |
| Thứ tự mảng Reflection luôn cố định | Không dựa vào thứ tự của `getNestMembers()` hay `getPermittedSubclasses()`; sắp xếp nếu cần hiển thị ổn định |
| `getSimpleName()` đủ làm định danh duy nhất | Cần xem tên đầy đủ, module/package và class loader trong hệ thống động |

**Tự kiểm tra:** Với một `class B extends A implements I`, hãy dự đoán `B.class.getSuperclass()` và `B.class.getInterfaces()`. Nếu `A` cũng implements `J`, `J` có tự xuất hiện trong `B.getInterfaces()` không? Với một sealed interface có nhánh `non-sealed`, tại sao `getPermittedSubclasses()` chỉ thấy nhánh trực tiếp mà không thể liệt kê mọi hậu duệ?

Tài liệu chuẩn: [Java SE 17 — `java.lang.Class`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html).