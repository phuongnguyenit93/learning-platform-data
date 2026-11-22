# `canAccess` và đối tượng đích phù hợp trong Java Reflection

## 1. Vấn đề cần giải quyết

Khi dùng Reflection, lấy được một `Field`, `Method` hoặc `Constructor` **không có nghĩa là mã đang chạy được phép truy cập thành viên đó**. Bước tra cứu (`getDeclaredField`, `getDeclaredMethod`, `getDeclaredConstructor`) và bước kiểm tra quyền truy cập là hai việc khác nhau.

Từ Java 9, `AccessibleObject.canAccess(Object obj)` giúp kiểm tra **mã gọi hiện tại** có thể truy cập thành viên được phản chiếu hay không, trong ngữ cảnh **đối tượng đích phù hợp**. Ba nhóm đối tượng Reflection hỗ trợ phương thức này là:

- `Field`: trường dữ liệu, thuộc instance hoặc static;
- `Method`: phương thức, thuộc instance hoặc static;
- `Constructor`: hàm tạo, không có instance đích trước khi khởi tạo.

Điểm mấu chốt: đối số `obj` của `canAccess` là **đối tượng đích để xét quyền truy cập**, không phải giá trị trường, tham số phương thức, hoặc tên lớp. Với thành viên static và constructor, phải truyền `null`.

## 2. Chọn `obj` đúng với loại thành viên

| Đối tượng Reflection | Đối số `canAccess(obj)` hợp lệ | Ví dụ |
| --- | --- | --- |
| `Field` instance | Một đối tượng khác `null`, là instance của lớp khai báo trường hoặc lớp con | `field.canAccess(customer)` |
| `Method` instance | Một đối tượng khác `null`, là instance của lớp khai báo phương thức hoặc lớp con | `method.canAccess(customer)` |
| `Field` static | **`null`** | `field.canAccess(null)` |
| `Method` static | **`null`** | `method.canAccess(null)` |
| `Constructor` | **`null`** | `ctor.canAccess(null)` |

**Quan trọng:** đây là quy tắc riêng cho `canAccess`. Một số API gọi Reflection khác có thể có quy tắc cho tham số đối tượng đích khác (ví dụ `Field.get` có thể bỏ qua đối tượng truyền vào đối với trường static); không được suy ngược quy tắc ấy cho `canAccess`.

Một instance của **lớp con** vẫn có thể là đối tượng đích hợp lệ cho thành viên instance được khai báo ở lớp cha. Điều kiện kiểu đích hợp lệ chỉ là **điều kiện đầu vào**; chưa đủ để kết luận có quyền truy cập. Đặc biệt với `protected` qua các package, kiểu receiver còn có thể ảnh hưởng đến kết quả kiểm tra quyền theo quy tắc Java.

### Khi truyền sai đối tượng đích

`canAccess` **ném `IllegalArgumentException`**, thay vì trả `false`, nếu:

1. Thành viên là **instance field / instance method** nhưng `obj == null`;
2. Thành viên là instance field / method nhưng `obj` không phải instance của lớp khai báo (hoặc lớp con phù hợp);
3. Thành viên là **static field / static method / constructor** nhưng `obj != null`.

Vì vậy, cần phân biệt:

- `false` = đối số đích đã đúng dạng, nhưng mã gọi **không có quyền truy cập** theo trạng thái/quy tắc hiện tại;
- `IllegalArgumentException` = **đối tượng đích đưa vào `canAccess` không hợp lệ**. Đây không phải một kết quả kiểm tra quyền `false`.

## 3. `canAccess` kiểm tra quyền của ai?

`canAccess` trả lời câu hỏi: **caller hiện tại** có được phép truy cập thành viên được phản chiếu trên đối tượng đích này không?

Phép kiểm tra liên quan đến nhiều yếu tố:

- `public`, `protected`, package-private, `private` của thành viên và khả năng truy cập lớp khai báo;
- vị trí của mã gọi: lớp, package, quan hệ kế thừa;
- với ứng dụng dùng JPMS (Java Platform Module System): ranh giới module, package được `exports` hoặc `opens`, tùy loại quyền đang dùng;
- cờ tắt kiểm tra quyền Java language access control của chính đối tượng `Field`/`Method`/`Constructor` đó, được bật khi `trySetAccessible()` hoặc `setAccessible(true)` thành công;
- kiểu đối tượng đích, nhất là quy tắc receiver của thành viên `protected` trong một số trường hợp kế thừa khác package.

Nếu cờ bỏ qua kiểm tra quyền đang được bật thành công, `canAccess` trả `true` khi `obj` hợp lệ. Nếu cờ chưa bật, nó xét quyền của caller theo cơ chế kiểm soát truy cập Java (Reflection có điều chỉnh riêng về module readability theo Javadoc).

**Không nên coi `canAccess` là đặc điểm cố định của riêng một `Field` hay `Method`.** Khi gọi nó từ các lớp khác nhau, kết quả có thể khác, vì caller thay đổi. Chuyển một `Method` qua helper rồi gọi `canAccess` trong helper cũng khiến ngữ cảnh kiểm tra gắn với helper, không tự chuyển quyền của caller ban đầu.

## 4. Ví dụ Java 17+ chạy độc lập

Lưu thành file `CanAccessDemo.java`. Hai lớp `CanAccessDemo` và `AccessTarget` là **hai lớp top-level khác nhau** trong cùng file và cùng package mặc định; nhờ đó ví dụ về `private` không bị ảnh hưởng bởi quan hệ nestmate của các lớp lồng nhau.

~~~java
import java.lang.reflect.Constructor;
import java.lang.reflect.Field;
import java.lang.reflect.Method;

public class CanAccessDemo {
    public static void main(String[] args) throws Exception {
        AccessTarget target = new AccessTarget();

        Field publicField =
                AccessTarget.class.getDeclaredField("count");
        Field privateField =
                AccessTarget.class.getDeclaredField("secret");
        Field staticField =
                AccessTarget.class.getDeclaredField("total");
        Method instanceMethod =
                AccessTarget.class.getDeclaredMethod("ping");
        Method staticMethod =
                AccessTarget.class.getDeclaredMethod("reset");
        Constructor<AccessTarget> constructor =
                AccessTarget.class.getDeclaredConstructor();

        // Instance member: truyền instance đích hợp lệ.
        System.out.println("public field: " + publicField.canAccess(target));
        System.out.println("instance method: " + instanceMethod.canAccess(target));

        // Static member và constructor: truyền null.
        System.out.println("static field: " + staticField.canAccess(null));
        System.out.println("static method: " + staticMethod.canAccess(null));
        System.out.println("constructor: " + constructor.canAccess(null));

        // Đích hợp lệ nhưng private: caller không có quyền mặc định.
        System.out.println("private before: " + privateField.canAccess(target));

        try {
            publicField.canAccess(null);
        } catch (IllegalArgumentException e) {
            System.out.println("instance + null: IllegalArgumentException");
        }

        try {
            publicField.canAccess(new Object());
        } catch (IllegalArgumentException e) {
            System.out.println("instance + wrong type: IllegalArgumentException");
        }

        try {
            staticField.canAccess(target);
        } catch (IllegalArgumentException e) {
            System.out.println("static + non-null: IllegalArgumentException");
        }

        try {
            constructor.canAccess(target);
        } catch (IllegalArgumentException e) {
            System.out.println("constructor + non-null: IllegalArgumentException");
        }

        // Hai lớp cùng unnamed module: có thể bật quyền trong ví dụ này.
        boolean enabled = privateField.trySetAccessible();
        System.out.println("opened private: " + enabled);
        System.out.println("private after: " + privateField.canAccess(target));

        if (privateField.canAccess(target)) {
            System.out.println("secret value: " + privateField.get(target));
        }
    }
}

class AccessTarget {
    public int count = 3;
    private String secret = "demo";
    public static int total = 9;

    public AccessTarget() { }

    public void ping() { }

    public static void reset() { }
}
~~~

Chạy:

~~~bash
javac CanAccessDemo.java
java CanAccessDemo
~~~

Kết quả trên JDK 17+ khi hai lớp được chạy trong cùng unnamed module (như lệnh trên):

~~~text
public field: true
instance method: true
static field: true
static method: true
constructor: true
private before: false
instance + null: IllegalArgumentException
instance + wrong type: IllegalArgumentException
static + non-null: IllegalArgumentException
constructor + non-null: IllegalArgumentException
opened private: true
private after: true
secret value: demo
~~~

**Giải thích:**

1. Trường `count` và phương thức `ping` là public, mã `CanAccessDemo` ở cùng package với `AccessTarget`, và `target` là instance hợp lệ: `canAccess(target)` trả `true`.
2. `total` và `reset` là static; constructor không có instance đích: phải dùng `canAccess(null)`.
3. `secret` là `private` của **một lớp top-level khác**. Caller `CanAccessDemo` không được truy cập mặc định, nên kết quả `false` dù `target` đúng kiểu.
4. Bốn lời gọi trong khối `try` cố tình vi phạm quy tắc của tham số `obj`. Mỗi lời gọi phát sinh `IllegalArgumentException` trước khi đưa ra kết luận có quyền hay không.
5. `trySetAccessible()` thành công trong ví dụ cùng unnamed module; trạng thái cờ cho phép bỏ qua kiểm tra truy cập ngôn ngữ, nên `canAccess(target)` đổi thành `true` và `Field.get(target)` đọc được trường private. Điều đó **không bảo đảm thành công với mọi module hoặc mọi thành viên**.

## 5. Dùng `canAccess` cùng `trySetAccessible` như thế nào?

`canAccess(obj)` là **phép kiểm tra**; nó không tự thay đổi quyền truy cập. `trySetAccessible()` là **yêu cầu bật cờ bỏ qua kiểm tra truy cập** nếu được phép:

~~~java
// Minh họa trong ngữ cảnh đã có:
// Field field = ...; Object receiver = ...; receiver đúng kiểu.
if (!field.canAccess(receiver)) {
    if (!field.trySetAccessible()) {
        throw new IllegalAccessException("Không thể bật quyền Reflection");
    }
}
Object value = field.get(receiver);
~~~

Đây là đoạn code **minh họa trong phương thức có xử lý/khai báo checked exception**; nó không phải chương trình độc lập. Chỉ thực hiện yêu cầu mở quyền đối với thành viên mà ứng dụng được phép và thật sự cần truy cập.

- `canAccess` không mở quyền; `false` không đồng nghĩa với `trySetAccessible` chắc chắn sẽ thành công.
- `trySetAccessible` trả `true` nếu bật được cờ; trả `false` khi không thể bật do giới hạn truy cập thông thường, chẳng hạn package của module khác không mở thích hợp cho caller. Nó vẫn có thể ném `SecurityException` trong môi trường áp dụng Security Manager.
- `setAccessible(true)` có mục tiêu tương tự, nhưng có thể ném `InaccessibleObjectException` nếu không thể bật cờ do hạn chế đóng gói module.
- `isAccessible()` đã deprecated từ Java 9. Tên của nó dễ gây hiểu nhầm: nó chỉ phản ánh cờ bỏ qua kiểm tra quyền, **không** trả lời đầy đủ caller có quyền truy cập hay không. Dùng `canAccess` cho câu hỏi kiểm tra quyền hiện tại.
- `canAccess` trả `true` không có nghĩa thao tác kế tiếp chắc chắn thành công vì còn các điều kiện khác: đối số của `Method.invoke`, kiểu dữ liệu khi `Field.set`, trạng thái `final`, ngoại lệ từ phương thức đích và các yếu tố runtime khác.

### Các trạng thái dễ nhầm lẫn

| Trường hợp | Kết quả thường thấy | Lý do |
| --- | --- | --- |
| Public instance field, receiver đúng kiểu, lớp/package truy cập được | `true` | Caller có quyền thông thường. |
| Private instance field của lớp top-level khác, receiver đúng kiểu | `false` | Receiver hợp lệ nhưng quyền bị hạn chế. |
| Instance field, receiver `null` | `IllegalArgumentException` | Sai loại đối tượng đích. |
| Instance method, receiver không thuộc lớp khai báo hoặc lớp con | `IllegalArgumentException` | Sai loại đối tượng đích. |
| Static method, receiver là một object | `IllegalArgumentException` | Static đòi `null`. |
| Constructor, receiver là object | `IllegalArgumentException` | Constructor đòi `null`. |
| Private field, đã `trySetAccessible()` thành công, receiver đúng kiểu | `true` | Đã bật cờ bỏ qua kiểm tra truy cập. |

## 6. Bẫy trong code thực tế

### Nhầm đối số của `canAccess` với đối số của `invoke`

Với instance method:

~~~java
Method m = String.class.getMethod("substring", int.class);
String receiver = "reflection";

System.out.println(m.canAccess(receiver)); // true
System.out.println(m.invoke(receiver, 3));  // lection
~~~

`canAccess(receiver)` nhận **receiver**, không nhận `3`. `invoke(receiver, 3)` nhận receiver **và** đối số truyền cho `substring`. Nếu gọi `m.canAccess(3)`, đây là `Integer` chứ không phải `String`, nên ném `IllegalArgumentException`. Đoạn code trên minh họa cần đặt trong hàm có xử lý/khai báo ngoại lệ checked.

### Nhầm `null` ở constructor với chưa được phép tạo instance

`constructor.canAccess(null)` chỉ kiểm tra quyền đối với constructor. `null` là giá trị bắt buộc của tham số kiểm tra, **không phải tham số truyền vào constructor**. Khi muốn tạo instance, dùng `constructor.newInstance(args...)` với các tham số thật và xử lý ngoại lệ thích hợp.

### Bỏ qua kiểm tra kiểu trước khi kiểm tra quyền

Nếu viết tiện ích chung để gọi Reflection, trước hết xác định có phải static hay constructor không, rồi kiểm tra receiver:

~~~java
// Mã phác họa áp dụng khi đã có AccessibleObject member.
if (member instanceof Constructor<?>) {
    // canAccess(null)
} else if (member instanceof Field field) {
    // Modifier.isStatic(field.getModifiers()) ? null : receiver
} else if (member instanceof Method method) {
    // Modifier.isStatic(method.getModifiers()) ? null : receiver
}
~~~

Đoạn trên là mô tả logic, không phải hàm hoàn chỉnh. Với instance member, cần kiểm tra `receiver != null` và `declaringClass.isInstance(receiver)` trước khi gọi `canAccess(receiver)`, để lỗi dữ liệu đích được báo rõ ràng. `Class.isInstance` phù hợp với instance lớp con, thay vì chỉ so sánh chính xác `receiver.getClass() == declaringClass`.

### Hiểu sai module và `public`

Một phương thức `public` không tự động truy cập được từ mọi module nếu lớp hoặc package khai báo không được xuất phù hợp. Ngược lại, có thể lấy metadata bằng `getDeclaredMethod` nhưng chưa có quyền `invoke`. Khi ứng dụng ở các named module khác nhau, `exports` liên quan đến quyền sử dụng API công khai; `opens` liên quan đến khả năng thực hiện deep reflection. Quyền mở bằng `trySetAccessible` không được xem như một cách vượt mọi ranh giới module.

## 7. Checklist quyết định `canAccess` theo từng bước

1. **Xác định loại thành viên:** `Field`, `Method` hay `Constructor`.
2. **Xác định static hay instance:** `Modifier.isStatic(member.getModifiers())` áp dụng cho field/method.
3. **Chọn receiver:** static/constructor → `null`; instance → object thuộc lớp khai báo hoặc lớp con.
4. **Gọi `canAccess(receiver)`:** xử lý riêng trường hợp sai receiver gây `IllegalArgumentException`.
5. **Nếu trả `false`:** xem quyền lớp/package/module và chính sách ứng dụng; chỉ cân nhắc `trySetAccessible()` khi cần và được phép.
6. **Thực thi Reflection:** `Field.get/set`, `Method.invoke` hoặc `Constructor.newInstance`; tiếp tục xử lý các lỗi đặc thù của thao tác.

### Tự kiểm tra

- Có một `Field` private thuộc instance; truyền một instance đúng lớp vào `canAccess` nhưng chưa mở quyền. Kết quả là gì? **Thường là `false` nếu caller không có quyền**, không phải `IllegalArgumentException`.
- Có một `Method` static public; gọi `canAccess(new Object())` thì sao? **`IllegalArgumentException`**, vì static phải truyền `null`.
- Có `Field` instance khai báo trong `Base`, đối tượng thực tế là `Derived extends Base`. Receiver hợp lệ không? **Có**; sau đó mới xét quyền truy cập của caller.
- `trySetAccessible()` trả `false` thì có nên gọi `get` trên private field như thể đã mở quyền? **Không**; cần xử lý thiếu quyền hoặc thay đổi thiết kế/API.

**Kết luận:** `canAccess(obj)` cần **đúng đối tượng đích trước**, rồi mới đánh giá **quyền của caller**. `false` biểu thị không được phép truy cập với đối tượng hợp lệ; đối tượng sai loại gây `IllegalArgumentException`. Static member và constructor phải truyền `null`.

### Tài liệu chính thức

- [JDK 17 — AccessibleObject.canAccess(Object)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AccessibleObject.html#canAccess(java.lang.Object))
- [JDK 17 — AccessibleObject.trySetAccessible()](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AccessibleObject.html#trySetAccessible())
- [JDK 17 — java.lang.reflect.Modifier](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Modifier.html)
- [Java Language Specification §6.6 — Access Control](https://docs.oracle.com/javase/specs/jls/se17/html/jls-6.html#jls-6.6)
