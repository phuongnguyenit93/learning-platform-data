# `Class.getSuperclass()`: lớp cha trực tiếp và các trường hợp trả về `null`

## 1. Ý nghĩa của `getSuperclass()`

Trong Java Reflection, đối tượng `Class<?>` mô tả một kiểu tại runtime. Gọi `type.getSuperclass()` để lấy đối tượng `Class` đại diện cho **lớp cha trực tiếp** được xác định qua quan hệ `extends`. Ví dụ, nếu `class Dog extends Animal` thì `Dog.class.getSuperclass() == Animal.class`. Phương thức không tự duyệt toàn bộ chuỗi tổ tiên và không liệt kê các interface.

Khai báo phương thức trong `java.lang.Class<T>`:

```java
public Class<? super T> getSuperclass()
```

Khi làm việc với `Class<?>`, có thể gán kết quả cho `Class<?> parent`. Giá trị `null` là **kết quả hợp lệ theo hợp đồng API**, không phải bằng chứng Reflection gặp lỗi hoặc ném ngoại lệ.

Java phân biệt superclass với superinterface: class chỉ có tối đa một superclass trực tiếp, có thể triển khai nhiều interface; interface có thể mở rộng nhiều interface nhưng không có superclass theo `getSuperclass()`.

## 2. Chính xác khi nào trả `null`?

| Kiểu được hỏi | Kết quả | Giải thích |
| --- | --- | --- |
| `Object.class` | `null` | `java.lang.Object` là gốc chuỗi kế thừa của các class thông thường, không có lớp cha. |
| Mọi interface, chẳng hạn `Runnable.class` | `null` | Ngay cả khi interface có `extends` interface khác, quan hệ đó được tra bằng `getInterfaces()`. |
| Mọi primitive: `boolean`, `byte`, `short`, `char`, `int`, `long`, `float`, `double` (ví dụ `int.class`) | `null` | Primitive không phải class kế thừa từ `Object`. |
| `void.class` hoặc `Void.TYPE` | `null` | `void` biểu thị không có giá trị trả về; không có superclass. |

Một annotation type khai báo bằng `@interface` cũng là interface, nên `MyAnnotation.class.getSuperclass()` bằng `null`. Kể cả khi interface kế thừa nhiều interface, kết quả vẫn `null`.

**Các trường hợp dễ nhầm:**

- `int.class.getSuperclass() == null`, trong khi `Integer.class.getSuperclass() == Number.class`. Primitive và wrapper là các kiểu khác nhau.
- `void.class.getSuperclass() == null`, nhưng `Void.class.getSuperclass() == Object.class`. `java.lang.Void` là một class tham chiếu khác với `void`.
- `String[].class.getSuperclass() == Object.class`, `int[].class.getSuperclass() == Object.class`. Mảng là kiểu tham chiếu; **mọi array class đều có superclass phản chiếu là `Object`**, bất kể kiểu phần tử hay số chiều.
- Class bình thường không khai báo `extends` có superclass là `Object` (ngoại trừ chính `Object`); enum có superclass `Enum`, còn record có superclass `Record`.

## 3. Ví dụ Java 17 hoàn chỉnh

Tạo tệp `SuperclassDemo.java` với nội dung:

```java
public class SuperclassDemo {
    interface Named extends Runnable {}

    static class Parent {}

    static class Child extends Parent implements Named {
        @Override
        public void run() {}
    }

    enum Status { READY }

    record Point(int x, int y) {}

    private static void show(Class<?> type) {
        Class<?> parent = type.getSuperclass();
        System.out.println(type.getSimpleName() + " -> "
                + (parent == null ? "null" : parent.getSimpleName()));
    }

    public static void main(String[] args) {
        show(Object.class);
        show(Named.class);
        show(int.class);
        show(void.class);
        show(String[].class);
        show(String[][].class);
        show(Parent.class);
        show(Child.class);
        show(Status.class);
        show(Point.class);

        System.out.println("Named extends -> "
                + Named.class.getInterfaces()[0].getSimpleName());
        System.out.println("Child implements -> "
                + Child.class.getInterfaces()[0].getSimpleName());
        System.out.println("Void.class -> "
                + Void.class.getSuperclass().getSimpleName());
    }
}
```

Biên dịch/chạy với JDK 17 trở lên:

```bash
javac SuperclassDemo.java
java SuperclassDemo
```

Kết quả:

```text
Object -> null
Named -> null
int -> null
void -> null
String[] -> Object
String[][] -> Object
Parent -> Object
Child -> Parent
Status -> Enum
Point -> Record
Named extends -> Runnable
Child implements -> Named
Void.class -> Object
```

**Đọc kết quả:**

- `Named` vẫn có superinterface `Runnable`, nhưng `getSuperclass()` bằng `null`; `getInterfaces()` cho biết interface mà `Named` mở rộng trực tiếp.
- `Child` vừa `extends Parent` vừa `implements Named`. `getSuperclass()` trả `Parent`, trong khi `getInterfaces()` trả interface khai báo trực tiếp là `Named`.
- `Parent` mặc định kế thừa `Object`. `Status` kế thừa `Enum`, `Point` kế thừa `Record`; cả hai vẫn có superclass.
- `String[]` và `String[][]` đều trả `Object`, không trả class biểu diễn kiểu phần tử. `Void.class` là class tham chiếu nên trả `Object`.

## 4. Đi qua nhiều cấp superclass

Vì mỗi lần gọi chỉ trả **lớp cha gần nhất**, cần lặp đến `null` để đi hết chuỗi. Đặt đoạn sau trong `main()` của chương trình phía trên:

```java
Class<?> current = Child.class;
while (current != null) {
    System.out.println(current.getSimpleName());
    current = current.getSuperclass();
}
```

Kết quả:

```text
Child
Parent
Object
```

Vòng lặp in kiểu đầu vào, rồi từng lớp cha; sau `Object`, `getSuperclass()` là `null` và vòng lặp dừng. Nếu bắt đầu bằng interface hoặc primitive, vòng lặp chỉ in chính kiểu đó. Cần nhớ vòng lặp này **không đi theo các nhánh interface**.

Khi bài toán là kiểm tra quan hệ **có thể gán kiểu**, `Base.class.isAssignableFrom(Candidate.class)` thường phù hợp hơn tự duyệt superclass. Ví dụ, `Named.class.isAssignableFrom(Child.class)` là `true` dù `Named` không nằm trong chuỗi superclass của `Child`. Chiều hỏi ở đây là: một giá trị kiểu `Candidate` có thể gán cho biến kiểu `Base` không?

## 5. Phân biệt các API liên quan

| Câu hỏi | API | Ý nghĩa |
| --- | --- | --- |
| Lớp cha trực tiếp? | `getSuperclass()` | Trả `Class` hoặc `null` theo hợp đồng ở mục 2. |
| Lớp cha và thông tin generic trong khai báo? | `getGenericSuperclass()` | Trả `Type`, có thể là `ParameterizedType`. |
| Interface được triển khai/mở rộng trực tiếp? | `getInterfaces()` | Trả mảng `Class<?>[]`; có thể là mảng rỗng. |
| Interface trực tiếp cùng đối số generic? | `getGenericInterfaces()` | Trả `Type[]`, không tự duyệt tổ tiên. |
| Kiểm tra nhóm kiểu? | `isInterface()`, `isPrimitive()`, `isArray()` | Phân loại kiểu trước khi xử lý kết quả `null`. |
| Kiểu thành phần của mảng? | `getComponentType()` | Ví dụ: `String[][].class.getComponentType() == String[].class`. |
| Có thể gán kiểu, bao gồm interface? | `isAssignableFrom(...)` | Kiểm tra quan hệ thay vì chỉ lấy superclass gần nhất. |

Do cơ chế xóa kiểu generic (*type erasure*), `getSuperclass()` trả `Class` cho lớp cha thô. Nếu khai báo `class TextBox extends Box<String>`, thì `TextBox.class.getSuperclass() == Box.class`; muốn đọc phần `<String>` trong khai báo phải dùng `getGenericSuperclass()`. Thông tin đó cũng không có nghĩa có thể khôi phục mọi đối số generic của đối tượng bất kỳ tại runtime.

Một class có thể kế thừa interface thông qua class cha; `getInterfaces()` trên chính class đó chỉ đưa ra interface trực tiếp mà class khai báo. Nếu cần lập danh sách mọi interface tổ tiên, phải tiếp tục đọc `getInterfaces()` ở các interface, đồng thời đi qua các superclass liên quan.

## 6. Lỗi thường gặp

**Không kiểm tra `null` trước khi gọi tiếp.** Dòng `type.getSuperclass().getName()` có thể ném `NullPointerException` với `Object.class`, interface, primitive hoặc `void.class`. Cách an toàn:

```java
Class<?> parent = type.getSuperclass();
String name = parent == null ? "(không có superclass)" : parent.getName();
```

**Hiểu `null` là “kiểu không có quan hệ kế thừa nào”.** Interface vẫn có thể `extends` interface khác; `getSuperclass()` không phản ánh nhánh đó. Dùng `getInterfaces()` để đọc trực tiếp, hoặc duyệt đệ quy khi muốn đủ tất cả superinterface.

**Cho rằng array hoặc wrapper cũng phải trả `null`.** Array có superclass là `Object`. `Integer` là class nên có superclass `Number`. Kết quả của primitive khác kết quả của lớp bao tương ứng.

**Nhầm `void.class` với `Void.class`.** `void.class` trả `null`; `Void.class` trả `Object.class`. Tên gần giống không đồng nghĩa hai `Class` giống nhau.

**Dùng `getSuperclass()` để hỏi class có triển khai interface hay không.** API này không đi qua `implements`; hãy dùng `isAssignableFrom` theo đúng chiều hoặc duyệt các interface nếu cần giải thích đường quan hệ.

Quy tắc cần nhớ: **`Object`, interface, primitive và `void` cho `null`; array cho `Object.class`; class, enum và record trả superclass trực tiếp tương ứng.**