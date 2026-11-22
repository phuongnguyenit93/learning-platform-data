# Đọc field instance bằng đối tượng đúng kiểu trong Java Reflection

## 1. Bài toán: một `Field` cần một object để đọc giá trị

Reflection cho phép lấy metadata của một field ngay cả khi chưa có object cụ thể:

```java
Field field = Person.class.getDeclaredField("name");
```

Nhưng **field instance thuộc trạng thái của từng object**. Để đọc giá trị, cần truyền một **đối tượng nhận (receiver)** phù hợp cho phương thức `Field.get(Object obj)`:

```java
Person person = new Person("Lan");
Object value = field.get(person);
```

Trong ví dụ minh họa này, `Person` phải là class có field `name`, constructor nhận `String`, và quyền truy cập phải hợp lệ. Đây là mảnh code giải thích cú pháp, không phải chương trình độc lập.

Có hai điều kiện riêng biệt: **(1) receiver phải thuộc đúng kiểu tương thích với class khai báo field; (2) code đang gọi phải có quyền truy cập field đó**. Nếu receiver sai kiểu, Java Reflection không thể lấy giá trị trường theo metadata đã chọn, dù field mang modifier `public`.

Câu hỏi cốt lõi của bài: `field.get(obj)` đòi `obj` phải có kiểu gì, và những khác biệt giữa class khai báo field, class runtime của object, field kế thừa và field cùng tên là gì?

## 2. Quy tắc chính xác của `Field.get(Object)`

Chữ ký API:

```java
public Object get(Object obj)
        throws IllegalArgumentException, IllegalAccessException
```

Khi `field` đại diện cho **instance field**:

- `obj` phải **khác `null`**.
- `obj` phải là instance của **class hoặc interface khai báo field**, hoặc một lớp con/lớp triển khai tương thích. Với field khai báo trong `Parent`, receiver `new Parent()` và `new Child()` khi `Child extends Parent` đều hợp lệ về kiểu.
- `Field.getDeclaringClass()` chỉ ra **kiểu khai báo field**. Đây là mốc cần đối chiếu với receiver, không phải class đã dùng để tìm kiếm một field một cách tình cờ.
- Khi receiver sai kiểu: `IllegalArgumentException`. Khi receiver `null` cho instance field: `NullPointerException`.
- Khi receiver đúng kiểu nhưng caller không có quyền đọc field trong chế độ kiểm tra truy cập hiện hành: `IllegalAccessException`.
- Khi đọc field kiểu nguyên thủy như `int`, `get` trả đối tượng wrapper, ví dụ `Integer`. Khi field kiểu tham chiếu chứa `null`, kết quả `get` cũng có thể là `null`: đừng nhầm **giá trị field null** với **receiver null**.

**Khác biệt với field static:** nếu field có modifier `static`, Java bỏ qua receiver truyền vào `Field.get` (có thể truyền `null`), vì giá trị thuộc class, không thuộc một object cụ thể. Bài này tập trung vào **instance field**.

Có thể dự đoán receiver đúng kiểu bằng biểu thức:

```java
Class<?> owner = field.getDeclaringClass();
boolean compatible = owner.isInstance(obj);
```

`Class.isInstance(null)` trả `false`, nên biểu thức kiểm tra an toàn cả khi receiver có thể null. Nó chỉ xác minh **khả năng tương thích kiểu**, không tự cấp quyền truy cập cho một field `private` hay một class/package bị giới hạn.

## 3. Ví dụ Java 17+ chạy độc lập: đúng kiểu, sai kiểu và `null`

Tạo file **`InstanceFieldReadDemo.java`**:

```java
import java.lang.reflect.Field;

public class InstanceFieldReadDemo {
    public static class Parent {
        public String label = "parent";
    }

    public static final class Child extends Parent {
        public String label = "child";
        public int count = 7;
    }

    public static void main(String[] args) throws ReflectiveOperationException {
        Parent parent = new Parent();
        Child child = new Child();

        Field parentLabel = Parent.class.getDeclaredField("label");
        Field childLabel = Child.class.getDeclaredField("label");
        Field count = Child.class.getDeclaredField("count");

        System.out.println("Parent.label from Parent: " + parentLabel.get(parent));
        System.out.println("Parent.label from Child: " + parentLabel.get(child));
        System.out.println("Child.label from Child: " + childLabel.get(child));

        System.out.println("Parent field accepts Child: "
                + parentLabel.getDeclaringClass().isInstance(child));
        System.out.println("Child field accepts Parent: "
                + childLabel.getDeclaringClass().isInstance(parent));

        Object countValue = count.get(child);
        System.out.println("Child.count: " + countValue);
        System.out.println("Count declared type: " + count.getType().getName());
        System.out.println("Count returned type: "
                + countValue.getClass().getSimpleName());

        try {
            childLabel.get(parent);
        } catch (IllegalArgumentException e) {
            System.out.println("Wrong receiver: IllegalArgumentException");
        }

        try {
            childLabel.get(null);
        } catch (NullPointerException e) {
            System.out.println("Null receiver: NullPointerException");
        }
    }
}
```

Biên dịch và chạy từ thư mục chứa file:

```bash
javac --release 17 InstanceFieldReadDemo.java
java InstanceFieldReadDemo
```

Kết quả stdout:

```text
Parent.label from Parent: parent
Parent.label from Child: parent
Child.label from Child: child
Parent field accepts Child: true
Child field accepts Parent: false
Child.count: 7
Count declared type: int
Count returned type: Integer
Wrong receiver: IllegalArgumentException
Null receiver: NullPointerException
```

**Vì sao chương trình cho kết quả trên?**

1. `parentLabel` khai báo tại `Parent` nên đọc được từ một `Parent` hoặc `Child`. Một object `Child` **vẫn chứa trạng thái instance của phần `Parent` được kế thừa**.
2. `Child` tự khai báo `label` cùng tên: đó là **field hiding**. Hai đối tượng `Field` đại diện cho **hai khai báo khác nhau**. `parentLabel.get(child)` vẫn đọc `Parent.label` và trả `parent`; `childLabel.get(child)` đọc `Child.label` và trả `child`.
3. `childLabel` khai báo tại `Child`, nên receiver `parent` không hợp lệ: một instance `Parent` chưa chắc là `Child`. Java phát sinh `IllegalArgumentException`.
4. `childLabel.get(null)` không có object chứa trạng thái instance nên phát sinh `NullPointerException`.
5. `count` khai báo là `int`; `Field.get` trả `Integer` sau boxing. `count.getType()` vẫn là `int.class`, còn kiểu runtime của kết quả là `Integer.class`.

Ví dụ cố ý dùng các field `public` trong những nested class `public` để làm nổi bật **kiểm tra kiểu receiver** mà không lẫn thêm lỗi quyền truy cập.

## 4. Hiểu đúng quan hệ lớp khai báo và kiểu runtime

Giả sử:

```java
class Animal {
    public int age = 3;
}

class Dog extends Animal {
    public String breed = "Shiba";
}
```

Đây là **mảnh code độc lập về khai báo kiểu**; để chạy thử, đặt hai class vào file phù hợp với quy tắc tên file Java, hoặc dùng chúng trong một chương trình có `main`.

Với:

```java
Field ageField = Animal.class.getDeclaredField("age");
Field breedField = Dog.class.getDeclaredField("breed");

Dog dog = new Dog();
Animal animal = new Animal();

Object a = ageField.get(dog);     // Hợp lệ: Dog là Animal
Object b = ageField.get(animal);  // Hợp lệ: Animal là Animal
Object c = breedField.get(dog);   // Hợp lệ: Dog có field breed
// breedField.get(animal);        // IllegalArgumentException
```

Các câu lệnh nằm trong một phương thức khai báo `throws ReflectiveOperationException` hoặc có xử lý các exception phù hợp.

Đừng đảo chiều quan hệ:

- **Field khai báo ở superclass + object subclass:** hợp lệ về kiểu.
- **Field khai báo ở subclass + object superclass:** không hợp lệ, trừ khi object được truyền thực sự là instance của subclass.
- **Field khai báo ở lớp A + object không liên quan B:** không hợp lệ.
- **Field khai báo ở A + biến tham chiếu có static type `Object` nhưng chứa instance của A:** vẫn hợp lệ, vì `Field.get` kiểm tra **object runtime**, không bị giới hạn bởi kiểu khai báo của biến Java.

Ví dụ:

```java
Object receiver = new Dog();
Object value = Animal.class.getDeclaredField("age").get(receiver);
```

Receiver hợp lệ vì object runtime là `Dog`. Việc biến `receiver` có static type `Object` không khiến `Field.get` ném `IllegalArgumentException`.

Có thể nhớ bằng biểu thức:

```java
field.getDeclaringClass().isInstance(receiver)
```

Nhưng biểu thức này không kiểm tra field có phải `static` và không thay thế việc xác thực quyền truy cập. Muốn tránh nhập nhằng, xử lý hai điều kiện đó riêng.

## 5. Đọc đúng field khi có kế thừa và trùng tên

### 5.1. `getDeclaredField` cố định class khai báo

`Parent.class.getDeclaredField("label")` trả field được khai báo **ngay trong `Parent`**. Tương tự, `Child.class.getDeclaredField("label")` trả field khai báo **ngay trong `Child`**; hai field có cùng tên nhưng khác declaring class.

Đây là lý do **đối tượng `Field` quyết định ô dữ liệu nào được đọc**, còn receiver quyết định **đọc ô dữ liệu đó trên instance nào**. Field không tự đổi thành khai báo gần subclass nhất chỉ vì truyền instance subclass vào `get`.

### 5.2. `getField` có thể tìm field public được kế thừa

`Child.class.getField("name")` có thể tìm field `public` kế thừa từ superclass nếu `Child` không khai báo field public cùng tên che khuất theo quy tắc Reflection. Tuy nhiên, khi xử lý field hiding, nên lấy chính xác theo class cần xét bằng `getDeclaredField` và kiểm tra `getDeclaringClass()`.

Để tìm field có tên cho trước trên **chuỗi superclass**, có thể duyệt lớp từ con lên cha và lấy khai báo đầu tiên tìm thấy:

```java
static Field findNearestDeclaredField(Class<?> start, String fieldName)
        throws NoSuchFieldException {
    for (Class<?> current = start;
         current != null;
         current = current.getSuperclass()) {
        try {
            return current.getDeclaredField(fieldName);
        } catch (NoSuchFieldException ignored) {
            // Lớp này không khai báo field đó; thử lớp cha.
        }
    }
    throw new NoSuchFieldException(fieldName);
}
```

Đây là **phương thức minh họa** (đặt trong class tiện ích và import `java.lang.reflect.Field`), không phải file hoàn chỉnh. Nó tìm **khai báo gần subclass nhất**, không tự kiểm tra đó là instance hay static field, không tự bảo đảm field đọc được về access. Nếu cần field cụ thể ở superclass, chọn `Parent.class.getDeclaredField("...")` ngay từ đầu.

### 5.3. Field hiding khác method overriding

Method có thể override và thực hiện dynamic dispatch. Với field, Java **không có override field** theo nghĩa dispatch động như method. Khi hai class có field cùng tên, việc truy cập qua `Field` được xác định bởi **khai báo mà `Field` đại diện**, bất kể kiểu runtime của receiver là subclass.

Vì vậy, đừng áp dụng trực giác “object là Child thì mọi field tên `label` phải lấy từ Child” cho Reflection. Hãy kiểm tra `Field.getDeclaringClass()`.

## 6. Hàm hỗ trợ đọc instance field an toàn hơn

Nếu viết mapper hoặc công cụ chẩn đoán, có thể tạo helper bắt buộc receiver tương thích ngay từ đầu, tránh gọi nhầm field static hoặc đọc từ object khác loại.

Đặt phương thức sau trong một class đã import `java.lang.reflect.Field`, `java.lang.reflect.Modifier` và `java.util.Objects`:

```java
static Object readInstanceField(Field field, Object receiver)
        throws IllegalAccessException {
    Objects.requireNonNull(field, "field");

    if (Modifier.isStatic(field.getModifiers())) {
        throw new IllegalArgumentException("Expected an instance field");
    }

    Class<?> owner = field.getDeclaringClass();
    if (!owner.isInstance(receiver)) {
        throw new IllegalArgumentException(
                "Receiver must be an instance of " + owner.getName()
        );
    }

    return field.get(receiver);
}
```

Ý nghĩa:

- `Objects.requireNonNull(field)` phát hiện sớm lỗi không có metadata field.
- `Modifier.isStatic(...)` kiểm tra đối tượng `Field` đại diện cho **instance field** đúng phạm vi helper.
- `owner.isInstance(receiver)` nhận cả instance của owner và subclass tương thích; với `null` trả `false`.
- Khi receiver hợp lệ, `field.get(receiver)` vẫn có thể ném `IllegalAccessException` nếu field không accessible. Helper **không tự bypass access control**, và đây là chủ ý thiết kế.

Helper cố tình chuyển cả null receiver và sai kiểu thành thông báo `IllegalArgumentException` của chính helper. Đó là **hợp đồng helper tự đặt ra**; nếu gọi API gốc `Field.get(null)` đối với instance field thì Java ném `NullPointerException` theo hợp đồng chính thức.

Nếu dùng helper trong hệ thống nhận dữ liệu từ bên ngoài, hãy xác định rõ chính sách exception và quyền truy cập thay vì tự động mở toàn bộ field.

## 7. Receiver đúng kiểu nhưng vẫn có thể bị `IllegalAccessException`

Ví dụ:

```java
public class Account {
    private String token = "secret";
}
```

Phần minh họa cần đặt trong ngữ cảnh phù hợp để biên dịch (top-level public class nằm trong `Account.java`). Code bên ngoài class có thể tìm metadata:

```java
Field tokenField = Account.class.getDeclaredField("token");
Account account = new Account();
Object value = tokenField.get(account); // Có thể ném IllegalAccessException
```

Ở đây `account` đúng kiểu, nhưng `token` là `private`. Nếu code gọi Reflection không có quyền truy cập private member, `get` bị chặn bằng `IllegalAccessException`. Nguyên nhân **khác hẳn** `IllegalArgumentException` khi receiver sai kiểu.

Cách xử lý nên ưu tiên **public getter hoặc API do lớp cung cấp** nếu bạn kiểm soát code nguồn. Chỉ dùng deep reflection khi bài toán thực sự yêu cầu và quyền truy cập cho phép. `trySetAccessible()` có thể trả `false`; `setAccessible(true)` có thể bị chặn, đặc biệt khi class nằm trong package của named module không được `opens` phù hợp. Không giả định mọi private field đều đọc được chỉ vì đã tìm thấy `Field`.

Phân biệt:

| Trường hợp | Receiver đúng kiểu? | Quyền truy cập? | Kết quả |
| --- | --- | --- | --- |
| Field `public` của public class, truy cập hợp lệ | Có | Có | Trả giá trị |
| Field `public` của `Parent`, receiver `Child extends Parent` | Có | Có | Trả phần trạng thái `Parent` trên object `Child` |
| Field của `Child`, receiver chỉ là `Parent` | Không | Không quyết định được kết quả thành công | `IllegalArgumentException` |
| Instance field, receiver là `null` | Không | Không quyết định được kết quả thành công | `NullPointerException` |
| Private field, receiver đúng kiểu nhưng caller không có quyền | Có | Không | `IllegalAccessException` |
| Static field | Receiver bị bỏ qua | Vẫn phải hợp lệ | Có thể truyền `null` |

Ở các trường hợp kết hợp nhiều lỗi, cần phân tích điều kiện của API và access control; bảng tập trung vào nguyên nhân nổi bật được tách riêng.

## 8. Đọc field primitive và kiểu tham chiếu

`Field.get(Object)` luôn trả về `Object` nên giá trị primitive được **boxing** tự động:

```java
Field countField = Child.class.getDeclaredField("count");
Object boxed = countField.get(child);   // Integer(7)
int count = (Integer) boxed;            // Unboxing
```

Đây là mảnh code tham chiếu `Child` và biến `child` trong chương trình ở mục 3.

Khi đã biết chính xác kiểu field, API còn có các phương thức đọc theo kiểu nguyên thủy, ví dụ `getInt(receiver)`, `getLong(receiver)`, `getBoolean(receiver)`. Chúng tránh trả về wrapper trong chữ ký gọi và áp dụng quy tắc chuyển đổi primitive thích hợp. **Không gọi `getInt` trên field tham chiếu `Integer` rồi mặc nhiên kỳ vọng được unboxing**, vì các phương thức chuyên biệt này không phải công cụ chuyển đổi kiểu tùy ý.

Với field kiểu tham chiếu:

```java
String text = (String) field.get(receiver);
```

ép kiểu `String` chỉ hợp lệ khi giá trị thực sự là `String` hoặc `null`; nếu giá trị thuộc class khác, code ép kiểu có thể ném `ClassCastException`. Có thể kiểm tra `field.getType()` để biết **kiểu khai báo của field**, nhưng type parameter generic yêu cầu thêm `getGenericType()` nếu cần phân tích chữ ký generic. Không nên dùng `getClass()` ngay trên kết quả mà chưa kiểm tra `null`.

## 9. Lỗi phổ biến khi đọc field instance

| Sai lầm | Triệu chứng | Cách sửa |
| --- | --- | --- |
| `field.get(null)` với instance field | `NullPointerException` | Truyền instance thật, khác `null` |
| Truyền object không thuộc declaring class hoặc subclass | `IllegalArgumentException` | Kiểm tra `field.getDeclaringClass().isInstance(receiver)` |
| Dùng `Field` của `Child` để đọc trên một `Parent` thuần túy | `IllegalArgumentException` | Lấy `Field` từ class phù hợp hoặc dùng receiver `Child` |
| Ngỡ field của superclass sẽ tự chuyển thành field cùng tên của subclass | Đọc nhầm giá trị khi field hiding | Kiểm tra `getDeclaringClass()`; chọn đúng khai báo |
| Receiver đúng nhưng field private không accessible | `IllegalAccessException` | Ưu tiên public API; kiểm tra module và quyền truy cập |
| Gọi `getDeclaredField` trên subclass cho field chỉ khai báo ở superclass | `NoSuchFieldException` | Tìm ở declaring class hoặc duyệt superclass |
| Ép trực tiếp `Object` từ field int sang `String` | `ClassCastException` | Dùng wrapper tương ứng, `getInt` hoặc kiểm tra kiểu |
| Dùng `field.getType().isInstance(receiver)` để kiểm tra receiver | Kết quả sai mục tiêu vì `getType()` là **kiểu giá trị** của field | Dùng `getDeclaringClass().isInstance(receiver)` |
| Quên phân biệt `static` và instance | Truyền receiver không cần thiết hoặc dùng helper sai mục đích | Dùng `Modifier.isStatic(field.getModifiers())` |

### Phân biệt ba kiểu trong cùng thao tác

Đọc biểu thức:

```java
Field field = Parent.class.getDeclaredField("label");
Object receiver = new Child();
Object value = field.get(receiver);
```

- `field.getDeclaringClass() == Parent.class`: **kiểu khai báo field**.
- `receiver.getClass() == Child.class`: **kiểu runtime của object đang chứa giá trị**.
- `field.getType() == String.class`: **kiểu khai báo của giá trị field**.

Để xác thực object truyền vào `get`, so **declaring class với runtime receiver**, không so `field.getType()` với receiver. `getType()` hữu ích khi kiểm tra hoặc chuyển đổi **giá trị trả về**, không phải khi xác định owner của field.

## 10. Câu hỏi tự kiểm tra

1. Với `Base` và `Derived extends Base`, nếu `age` được khai báo trong `Base` thì `Base.class.getDeclaredField("age").get(new Derived())` có hợp lệ về kiểu không?
2. Nếu `Derived` có thêm field `score`, điều gì xảy ra khi gọi `Derived.class.getDeclaredField("score").get(new Base())`?
3. `field.getDeclaringClass()` khác `field.getType()` như thế nào?
4. `field.get(null)` với instance field gây exception gì? Nếu field là `static` thì receiver được xử lý ra sao?
5. Tại sao đọc một private field có thể thất bại ngay cả khi `owner.isInstance(receiver)` trả `true`?
6. Hai class cha/con cùng khai báo field tên `label`: đối tượng `Field` thu từ class cha sẽ đọc field nào khi receiver là object con?

**Đáp án ngắn:** (1) hợp lệ; (2) `IllegalArgumentException`; (3) một bên là class khai báo field, bên kia là kiểu giá trị của field; (4) `NullPointerException` đối với instance, receiver bị bỏ qua đối với static; (5) vì còn kiểm tra quyền truy cập; (6) khai báo `label` của class cha.

## 11. Ghi nhớ khi áp dụng

Đối với **instance field**, thao tác đọc đúng là:

```java
if (field.getDeclaringClass().isInstance(receiver)) {
    Object value = field.get(receiver);
    // Sử dụng value theo kiểu khai báo phù hợp.
}
```

Đây là mảnh code đặt trong phương thức có xử lý `IllegalAccessException`, áp dụng riêng cho instance field. Nó thể hiện đúng quy tắc tương thích receiver, nhưng chương trình thực tế còn phải xử lý receiver không hợp lệ, quyền truy cập và giá trị `null`.

Ba câu hỏi nên trả lời trước mọi lệnh đọc bằng Reflection: **field được khai báo ở đâu? receiver thực sự là object thuộc kiểu nào? caller có quyền truy cập không?** Trả lời đúng ba câu hỏi này giúp phân biệt rõ lỗi kiểu, lỗi `null` và lỗi access, đồng thời tránh đọc nhầm field khi có kế thừa hoặc field hiding.

Tài liệu API tham khảo: [Java SE `Field.get(Object)`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Field.html#get(java.lang.Object)).