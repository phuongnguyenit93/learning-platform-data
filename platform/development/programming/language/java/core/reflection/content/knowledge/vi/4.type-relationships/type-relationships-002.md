# Class.getInterfaces() — chỉ trả về các interface trực tiếp

## 1. Ý nghĩa và chữ “trực tiếp”

Trong Java Reflection, `Class<?>[] getInterfaces()` là phương thức của `java.lang.Class`, cho biết các **interface được khai báo trực tiếp** bởi kiểu đang xét. Phương thức trả về **mảng các đối tượng `Class<?>`** đại diện cho interface; nó không trả về đối tượng triển khai interface, không trả về tên dưới dạng `String`, và không tự duyệt toàn bộ cây kế thừa.

- Với **class**, đó là các interface xuất hiện trực tiếp trong mệnh đề `implements` của chính class.
- Với **interface**, đó là các superinterface xuất hiện trực tiếp trong mệnh đề `extends` của chính interface.
- Interface có được **gián tiếp** qua superclass hoặc qua một interface cha khác không tự động xuất hiện trong kết quả của kiểu đang xét.
- Kết quả là mảng rỗng `Class<?>[0]` nếu không có interface trực tiếp, chứ không phải `null`. Phần tử trong mảng đi theo thứ tự khai báo trong `implements` hoặc `extends`.

Ví dụ nhanh:

~~~java
interface A {}
interface B extends A {}
class Parent implements A {}
class Child extends Parent implements B {}
~~~

Ở đây:

| Biểu thức | Interface trả về trực tiếp | Điều quan trọng |
| --- | --- | --- |
| `A.class.getInterfaces()` | `[]` | `A` không `extends` interface nào. |
| `B.class.getInterfaces()` | `[A]` | `B extends A` trực tiếp. |
| `Parent.class.getInterfaces()` | `[A]` | `Parent implements A` trực tiếp. |
| `Child.class.getInterfaces()` | `[B]` | `Child` chỉ khai báo `implements B`; `A` vẫn là một quan hệ kiểu hợp lệ nhưng không nằm trong mảng trực tiếp của `Child`. |

Hãy tách hai câu hỏi: **“Kiểu này trực tiếp khai báo interface nào?”** dùng `getInterfaces()`; **“Kiểu này có thể được xem là một interface cụ thể hay không?”** dùng kiểm tra quan hệ kiểu như `SomeInterface.class.isAssignableFrom(Target.class)`.

## 2. Ví dụ chạy được với Java 17+

Lưu toàn bộ chương trình sau thành `DirectInterfacesDemo.java`:

~~~java
import java.io.Serializable;
import java.util.Arrays;
import java.util.function.Supplier;
import java.util.stream.Collectors;

interface Root {}
interface Middle extends Root {}
interface Marker {}

class Parent implements Serializable {}
class Child extends Parent implements Middle, Marker {}

class GenericSample implements Supplier<String> {
    @Override
    public String get() {
        return "ok";
    }
}

public class DirectInterfacesDemo {
    private static String directNames(Class<?> type) {
        return Arrays.stream(type.getInterfaces())
                .map(Class::getSimpleName)
                .collect(Collectors.joining(", ", "[", "]"));
    }

    public static void main(String[] args) {
        System.out.println("Child: " + directNames(Child.class));
        System.out.println("Parent: " + directNames(Parent.class));
        System.out.println("Middle: " + directNames(Middle.class));
        System.out.println("Root: " + directNames(Root.class));
        System.out.println("String[]: " + directNames(String[].class));
        System.out.println("int: " + directNames(int.class));

        System.out.println("Root assignable from Child: "
                + Root.class.isAssignableFrom(Child.class));
        System.out.println("Serializable assignable from Child: "
                + Serializable.class.isAssignableFrom(Child.class));

        System.out.println("Generic direct: "
                + GenericSample.class.getInterfaces()[0].getTypeName());
        System.out.println("Generic signature: "
                + GenericSample.class.getGenericInterfaces()[0].getTypeName());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac DirectInterfacesDemo.java
java DirectInterfacesDemo
~~~

Kết quả chuẩn:

~~~text
Child: [Middle, Marker]
Parent: [Serializable]
Middle: [Root]
Root: []
String[]: [Cloneable, Serializable]
int: []
Root assignable from Child: true
Serializable assignable from Child: true
Generic direct: java.util.function.Supplier
Generic signature: java.util.function.Supplier<java.lang.String>
~~~

Phân tích từng điểm:

1. `Child` **trực tiếp** `implements Middle, Marker`, nên `getInterfaces()` trả `Middle` trước `Marker`, đúng thứ tự khai báo. `Root` không nằm trong mảng này dù `Middle extends Root`.
2. `Serializable` thuộc mệnh đề `implements` của `Parent`, nên `Parent.class.getInterfaces()` có `Serializable` còn `Child.class.getInterfaces()` không có. Tuy vậy, một `Child` cũng là `Serializable` nhờ kế thừa `Parent`.
3. `Middle` là một **interface**, nên kết quả `[Root]` đến từ `extends Root`. `Root` không extends interface nào nên kết quả rỗng.
4. Các kiểu mảng và kiểu nguyên thủy có quy tắc riêng, xem phần tiếp theo.
5. `isAssignableFrom` trả `true` cho cả quan hệ gián tiếp qua superinterface hoặc superclass; do đó khác mục đích `getInterfaces()`.
6. `Supplier<String>` được trả về dưới dạng `Class` thô `Supplier` khi gọi `getInterfaces()`; thông tin `<String>` chỉ thấy ở `getGenericInterfaces()`.

## 3. Các trường hợp đặc biệt

| Kiểu của `Class` | Kết quả `getInterfaces()` |
| --- | --- |
| Class khai báo `implements I, J` | `[I, J]` theo thứ tự khai báo. |
| Class không khai báo `implements` | Mảng rỗng, kể cả khi superclass triển khai interface. |
| Interface khai báo `extends I, J` | `[I, J]` theo thứ tự khai báo. |
| Interface không khai báo `extends` | Mảng rỗng. |
| Kiểu mảng, chẳng hạn `String[]` hoặc `int[]` | `[Cloneable, java.io.Serializable]`, đúng thứ tự này, dù không có mã nguồn `implements`. |
| Primitive như `int`, `boolean` hoặc `void.class` | Mảng rỗng. |

Đặc biệt, `String[].class.getInterfaces()` không tìm các interface do `String` triển khai; nó phản ánh các interface của **chính kiểu mảng**. Tương tự, `int.class.getInterfaces()` rỗng nhưng `int[].class.getInterfaces()` có hai phần tử.

## 4. Phân biệt với các API liên quan

| API | Câu hỏi mà API trả lời |
| --- | --- |
| `type.getInterfaces()` | Interface nào được class trực tiếp triển khai hoặc được interface trực tiếp mở rộng? |
| `type.getGenericInterfaces()` | Các interface trực tiếp ấy được khai báo với tham số kiểu generic nào, nếu có? Trả về `Type[]`, không phải `Class<?>[]`. |
| `type.getSuperclass()` | Superclass trực tiếp của class là gì? Không dùng để liệt kê interface. |
| `I.class.isAssignableFrom(type)` | Biến kiểu `I` có thể nhận đối tượng thuộc `type` hay không, xét cả quan hệ kế thừa và triển khai gián tiếp? |
| `I.class.isInstance(object)` | Đối tượng thực tế có tương thích với interface `I` không? |

Hai phương thức `isAssignableFrom` và `isInstance` phù hợp hơn khi muốn **kiểm tra khả năng gán kiểu**. Ví dụ `Root.class.isAssignableFrom(Child.class)` là `true` dù `Root` không nằm trong `Child.class.getInterfaces()`. Với `isInstance`, truyền một object; với `isAssignableFrom`, truyền một đối tượng `Class<?>`.

`getGenericInterfaces()` vẫn chỉ liệt kê interface **trực tiếp**, nhưng giữ mô tả generic: trong ví dụ, kết quả chứa `java.util.function.Supplier<java.lang.String>`. Không ép mọi phần tử của `Type[]` sang `ParameterizedType` vì một interface có thể xuất hiện dưới dạng `Class` thô; trước khi ép kiểu phải kiểm tra `instanceof`.

## 5. Khi cần biết toàn bộ interface tổ tiên

Nếu cần liệt kê các interface có được qua nhiều cấp, `getInterfaces()` chỉ là bước khởi đầu. Với `Child` trong ví dụ, thuật toán phải đọc các interface trực tiếp của `Child`, đi tiếp qua `getInterfaces()` của từng interface đã tìm thấy, xét cả `Parent` qua `getSuperclass()`, và ghi nhận mỗi `Class<?>` đúng một lần trong `Set<Class<?>>` để tránh trùng khi nhiều nhánh hội tụ.

Ví dụ, `Child` có hai interface trực tiếp `[Middle, Marker]`, `Middle extends Root`, còn `Parent implements Serializable`. Nếu duyệt sâu từng nhánh interface trước khi chuyển sang nhánh kế tiếp và cuối cùng mới đi lên superclass, thứ tự kết quả là `[Middle, Root, Marker, Serializable]`. Đây là thứ tự do **thuật toán tự chọn**, không phải danh sách mà một lần gọi `Child.class.getInterfaces()` trả về.

Khi chỉ cần trả lời đúng/sai cho một interface, `Root.class.isAssignableFrom(Child.class)` rõ ràng và đơn giản hơn. Chỉ cần tự duyệt đồ thị khi phải thu thập toàn bộ interface; lúc đó nên dùng danh tính `Class<?>` làm khóa khử trùng lặp, xác định rõ thứ tự duyệt và quyết định có tính chính interface đầu vào hay chỉ tổ tiên. Những lựa chọn thuật toán và tình huống đồ thị hình thoi được triển khai chi tiết trong bài “Duyệt đồ thị interface và tránh lặp”.

## 6. Lỗi phổ biến và cách tự kiểm tra

- **Nhầm trực tiếp với toàn bộ cây kế thừa:** `Child.class.getInterfaces().length == 0` không chứng minh `Child` không triển khai interface nào; class cha có thể đã triển khai chúng.
- **Bỏ sót superinterface:** class `implements Middle` không khiến `Root` xuất hiện trực tiếp trong mảng của class, dù `Middle extends Root`.
- **Áp dụng máy móc cho array:** mọi kiểu mảng đều trả về `Cloneable` và `Serializable` trong thứ tự quy định.
- **Đòi thông tin generic từ `Class<?>[]`:** dùng `getGenericInterfaces()` khi phải đọc `Supplier<String>` hay `Comparable<T>` từ khai báo trực tiếp.
- **Truy cập `getInterfaces()[0]` khi chưa kiểm tra:** mảng có thể rỗng; kiểm tra `length` trước để tránh `ArrayIndexOutOfBoundsException`.
- **Nhầm kết quả với instance:** `getInterfaces()` trả metadata về *kiểu*, không tạo instance, không gọi phương thức interface.

Tự kiểm tra với `class D extends Parent {}` trong ví dụ: `D.class.getInterfaces()` phải là `[]`, nhưng `Serializable.class.isAssignableFrom(D.class)` phải là `true`. Giải thích được cả hai kết quả nghĩa là đã nắm đúng ý nghĩa của **“trực tiếp”**.

**Tài liệu tham khảo:** [Java SE 17 API — java.lang.Class](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html), phần `getInterfaces()`, `getGenericInterfaces()` và `isAssignableFrom()`.
