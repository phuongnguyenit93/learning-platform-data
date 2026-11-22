# Lấy kiểu thực tế của đối tượng bằng `Object.getClass()`

## 1. Mục tiêu

Sau bài học, bạn có thể:

- Gọi `getClass()` để xác định **lớp thực tế ở thời điểm chạy** của một đối tượng.
- Phân biệt lớp thực tế với kiểu khai báo của biến tham chiếu, đặc biệt khi dùng kế thừa và interface.
- Đọc một số thông tin cơ bản từ đối tượng `Class<?>` được trả về và so sánh chính xác các kiểu.
- Xử lý đúng trường hợp `null`, kiểu nguyên thủy, mảng, generic và các lớp được tạo động.

Phạm vi của bài là cách lấy **kiểu runtime từ một đối tượng đã có**. Các thao tác phản chiếu sâu như gọi constructor, truy cập field private hay gọi method bằng reflection là các chủ đề riêng.

## 2. `getClass()` là gì?

Mọi đối tượng Java đều kế thừa phương thức `public final Class<?> getClass()` từ `java.lang.Object`. Khi gọi `obj.getClass()`, JVM trả về đối tượng `java.lang.Class` đại diện cho **lớp thực tế đã tạo ra `obj`**, không đơn thuần là kiểu ghi trước tên biến.

Ví dụ:

```java
Object value = "Xin chào";
Class<?> actualType = value.getClass();

System.out.println(actualType == String.class); // true
```

- Kiểu khai báo của biến `value` là `Object`.
- Đối tượng mà `value` trỏ tới là một `String`.
- Kết quả `getClass()` là đối tượng `Class` của `java.lang.String`.

`Class<?>` không phải là chính đối tượng `value`, mà là đối tượng mô tả lớp của nó. Có thể dùng kết quả để hỏi tên lớp, lớp cha, interface, annotation và nhiều metadata khác. Phương thức `getClass()` là `final`, nên lớp con không thể override để giả mạo kết quả.

**Quy tắc cốt lõi:** với biến tham chiếu không `null`, `x.getClass()` mô tả lớp của **đối tượng hiện được tham chiếu**, bất kể biến `x` được khai báo rộng đến đâu.

## 3. Ví dụ Java 17+ có thể biên dịch và chạy

Tạo tệp `GetClassDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;

public class GetClassDemo {
    static class Animal {
    }

    static final class Dog extends Animal {
    }

    public static void main(String[] args) {
        Animal pet = new Dog();
        Class<?> actualType = pet.getClass();

        System.out.println(actualType.getName());
        System.out.println(actualType.getSimpleName());
        System.out.println(actualType == Animal.class);
        System.out.println(actualType == Dog.class);
        System.out.println(actualType.getSuperclass() == Animal.class);

        List<String> names = new ArrayList<>();
        System.out.println(names.getClass().getName());
        System.out.println(names.getClass() == ArrayList.class);
    }
}
```

Biên dịch và chạy trong thư mục chứa tệp:

```bash
javac GetClassDemo.java
java GetClassDemo
```

Kết quả chuẩn:

```text
GetClassDemo$Dog
Dog
false
true
true
java.util.ArrayList
true
```

Giải thích:

1. `Animal pet = new Dog()`: kiểu khai báo của `pet` là `Animal` nhưng đối tượng được tạo bằng `new Dog()`.
2. `pet.getClass()` trả về `Class` đại diện cho `Dog`, do đó so sánh với `Animal.class` cho `false` và với `Dog.class` cho `true`.
3. `getSuperclass()` cho biết `Class` của lớp cha trực tiếp, vì vậy `Dog` có superclass là `Animal`.
4. `getName()` in `GetClassDemo$Dog` vì `Dog` là lớp thành viên tĩnh nằm trong `GetClassDemo`; ký tự `$` thuộc tên nhị phân của lớp lồng nhau. `getSimpleName()` chỉ in `Dog`.
5. `names` được khai báo là `List<String>` nhưng được tạo bởi `new ArrayList<>()`; lớp runtime của nó là `java.util.ArrayList`.

Đoạn chương trình không phụ thuộc Spring hay thư viện bên ngoài; sử dụng JDK là đủ.

## 4. Kiểu khai báo và lớp runtime khác nhau như thế nào?

Xét hai khái niệm:

| Khái niệm | Câu hỏi trả lời | Ví dụ |
| --- | --- | --- |
| Kiểu khai báo (compile-time type) | Trình biên dịch cho phép gọi những thành viên nào qua biến này? | `Animal` của biến `pet` |
| Lớp thực tế (runtime class) | Đối tượng cụ thể được JVM tạo từ lớp nào? | `Dog` do `new Dog()` |
| Đối tượng `Class` | Metadata đại diện cho lớp runtime đó | `pet.getClass()` là `Dog.class` |

Một biến được gán lại có thể trỏ tới đối tượng thuộc lớp khác mà vẫn phù hợp với kiểu khai báo:

```java
Object item = "Java";
System.out.println(item.getClass() == String.class); // true

item = Integer.valueOf(42);
System.out.println(item.getClass() == Integer.class); // true
```

Hai biểu thức `item.getClass()` lần lượt trả về hai `Class` khác nhau vì đối tượng được tham chiếu đã thay đổi.

Điều này đặc biệt hữu ích khi nhận giá trị dưới kiểu cha như `Object`, một interface như `List`, hay một lớp cơ sở. Tuy nhiên, **không nên ép thiết kế hướng đối tượng thành chuỗi kiểm tra kiểu** nếu có thể dùng đa hình hoặc interface để thực hiện hành vi.

## 5. Làm việc với `Class<?>` được trả về

Các phương thức thông dụng:

| Biểu thức | Ý nghĩa | Ví dụ với đối tượng `new ArrayList<>()` |
| --- | --- | --- |
| `obj.getClass()` | Lấy đối tượng `Class` của lớp runtime | `ArrayList.class` |
| `obj.getClass().getName()` | Tên nhị phân, thường có package | `java.util.ArrayList` |
| `obj.getClass().getSimpleName()` | Tên ngắn của lớp | `ArrayList` |
| `obj.getClass().getCanonicalName()` | Tên chuẩn nếu kiểu có tên chuẩn | `java.util.ArrayList` |
| `obj.getClass().getSuperclass()` | `Class` của lớp cha trực tiếp, nếu có | `AbstractList.class` |
| `obj.getClass().getInterfaces()` | Danh sách interface được lớp khai báo triển khai trực tiếp | Phụ thuộc khai báo lớp |

Lưu ý về tên: `getSimpleName()` có thể trả chuỗi rỗng cho lớp vô danh; `getCanonicalName()` có thể trả `null` cho lớp vô danh hoặc lớp cục bộ. Không giả định các phương thức tên luôn cho kết quả có thể dùng làm định danh duy nhất. Tên của lớp được tạo động, chẳng hạn proxy, không phải API ổn định để ghi cứng.

Khi chưa cần ràng buộc kiểu cụ thể, khai báo biến như sau:

```java
Class<?> type = someObject.getClass();
```

Dấu `?` nghĩa là chưa biết chính xác kiểu được mô tả, giúp tránh ép kiểu `Class` không an toàn. Lớp runtime không phụ thuộc vào việc biến tham chiếu được khai báo với generic nào.

## 6. So sánh đúng lớp hay chấp nhận cả lớp con?

Có ba phép kiểm tra dễ bị nhầm:

| Cách kiểm tra | Ý nghĩa |
| --- | --- |
| `obj.getClass() == Dog.class` | Đúng **chính xác** lớp runtime là `Dog` |
| `obj instanceof Animal` | Đối tượng tương thích với `Animal`, kể cả lớp con |
| `Animal.class.isAssignableFrom(obj.getClass())` | Lớp runtime có thể gán cho biến kiểu `Animal` |

Ví dụ minh họa bên trong một phương thức có biến `pet` được khai báo `Animal pet = new Dog();`:

```java
System.out.println(pet.getClass() == Animal.class);                 // false
System.out.println(pet instanceof Animal);                         // true
System.out.println(Animal.class.isAssignableFrom(pet.getClass())); // true
```

Ở đây `Dog` **không phải chính xác** `Animal` nhưng **là một kiểu con** của `Animal`. Nếu nghiệp vụ cần hỗ trợ tất cả lớp con hoặc đối tượng thực thi interface, `instanceof` hoặc `Class.isInstance(...)` thường diễn đạt đúng ý hơn phép so sánh `getClass() == ...`.

Trong cùng ngữ cảnh nạp lớp, có thể so sánh các đối tượng `Class` bằng `==` để kiểm tra danh tính lớp. Đừng dùng riêng `getName().equals(...)` làm bằng chứng hai lớp là một: hai class loader khác nhau có thể nạp các lớp có cùng tên nhị phân nhưng không cùng danh tính runtime.

## 7. Các trường hợp cần lưu ý

### 7.1. Tham chiếu `null`

`getClass()` là phương thức của **đối tượng**. Khi biến bằng `null` thì không có đối tượng để lấy lớp:

```java
Object value = null;
// value.getClass(); // Ném NullPointerException tại runtime.

if (value != null) {
    System.out.println(value.getClass().getName());
} else {
    System.out.println("Không có đối tượng");
}
```

Đoạn trên là một **mảnh code đặt trong phương thức**, và nhánh `else` in `Không có đối tượng`. Đừng gọi `value.getClass()` trước khi kiểm tra `null` nếu đầu vào có thể vắng mặt. Dùng `instanceof` với `null` sẽ cho `false` thay vì ném `NullPointerException`.

### 7.2. Kiểu nguyên thủy, boxing và mảng

Các giá trị nguyên thủy như `int`, `boolean`, `double` không phải đối tượng nên không gọi được `getClass()` trực tiếp. Có thể dùng literal kiểu (`int.class`) hoặc boxing thành đối tượng:

```java
int count = 3;
// count.getClass(); // Lỗi biên dịch: int không phải reference type.

Object boxed = count; // Autoboxing sang Integer.
System.out.println(boxed.getClass() == Integer.class); // true
System.out.println(int.class.getName());                // int

Object numbers = new int[] {1, 2, 3};
System.out.println(numbers.getClass().isArray());                    // true
System.out.println(numbers.getClass().getComponentType() == int.class); // true
```

Mảng trong Java **là đối tượng**, kể cả mảng phần tử nguyên thủy. `numbers.getClass()` biểu diễn kiểu mảng `int[]`; `getComponentType()` trả về `int.class`. Đối với mảng, `getName()` sử dụng tên nhị phân đặc biệt, chẳng hạn `[I` cho `int[]`; khi cần trình bày dễ đọc, cân nhắc `getTypeName()`.

### 7.3. Generic và type erasure

`getClass()` mô tả lớp runtime, **không tái tạo type argument** của từng biến generic:

```java
List<String> words = new ArrayList<>();
List<Integer> counts = new ArrayList<>();

System.out.println(words.getClass() == counts.getClass()); // true
```

Cả hai đối tượng là `ArrayList`. Không thể dùng `words.getClass()` để kết luận danh sách mang `String` hay `Integer`. Java có thể lưu một số thông tin generic ở **khai báo** (ví dụ signature của field hoặc superclass) để reflection đọc bằng các API riêng, nhưng đó không phải thông tin về type argument của hai đối tượng `ArrayList` này.

### 7.4. Proxy và các lớp được tạo động

Trong framework hoặc môi trường có proxy, `getClass()` có thể trả về **lớp proxy được tạo tại runtime** thay vì lớp nghiệp vụ mà bạn mong đợi. Đừng so sánh cứng tên lớp được tạo động hoặc cho rằng `getClass()` luôn trùng với kiểu interface của đối tượng. Nếu mục tiêu là kiểm tra đối tượng đáp ứng hợp đồng nào, dùng `instanceof` hoặc `Class.isInstance(...)` sẽ phù hợp hơn.

## 8. Dùng khi nào trong thực tế?

Các tình huống hợp lý gồm ghi nhận loại đối tượng phục vụ chẩn đoán, phân loại chính xác các loại giá trị đã biết, truy xuất metadata phục vụ reflection hoặc kiểm tra nguyên nhân vì sao một biến kiểu interface đang chứa một implementation cụ thể.

Ví dụ đoạn code sau nằm **bên trong một phương thức**:

```java
Object payload = "hello";
Class<?> type = payload.getClass();

if (type == String.class) {
    System.out.println("Đúng lớp String");
}
System.out.println("Runtime type: " + type.getName());
```

Output:

```text
Đúng lớp String
Runtime type: java.lang.String
```

Trong logic nghiệp vụ thông thường, ưu tiên đa hình, interface hoặc pattern matching `instanceof` thay vì dùng `getClass()` và downcast liên tục. Sử dụng phép so sánh `==` với `Class` khi yêu cầu thật sự là **khớp đúng một implementation**.

## 9. Lỗi thường gặp và cách tránh

1. **Nhầm kiểu khai báo với lớp runtime:** `Animal pet = new Dog()` không làm `pet.getClass()` trở thành `Animal.class`.
2. **Gọi trên `null`:** kiểm tra tham chiếu trước khi gọi, nếu `null` là trường hợp hợp lệ.
3. **Dùng so sánh chính xác trong bài toán cần đa hình:** `getClass() == Base.class` loại bỏ tất cả subclass; cân nhắc `instanceof`.
4. **Cho rằng runtime class chứa type argument generic:** `new ArrayList<String>()` và `new ArrayList<Integer>()` có cùng lớp runtime.
5. **Gọi `getClass()` trên primitive:** dùng `int.class` hoặc boxing khi thật sự cần `Class` của wrapper.
6. **Dựa vào tên class để quyết định danh tính:** tên có thể chứa `$`, ký hiệu mảng hoặc tên lớp được framework sinh ra; danh tính lớp còn phụ thuộc class loader.
7. **Lấy tên hiển thị làm khóa dữ liệu bền vững:** `getSimpleName()` không đủ duy nhất và có thể rỗng với lớp vô danh.

## 10. Tự kiểm tra

- Với `Number number = Integer.valueOf(7);`, `number.getClass() == Number.class` là `false`; `number.getClass() == Integer.class` là `true`.
- Với `Object x = new String[2];`, `x.getClass().isArray()` là `true` và `x.getClass().getComponentType() == String.class` là `true`.
- Với `Object x = null;`, biểu thức `x.getClass()` ném `NullPointerException`; không có “lớp của null”.
- Với hai biến `List<String>` và `List<Integer>` đều trỏ tới `new ArrayList<>()`, `getClass()` trả cùng đối tượng `Class` khi chúng được nạp từ cùng lớp runtime.

**Điểm cần nhớ:** `getClass()` trả về `Class` của **đối tượng thực sự đang tồn tại**, còn kiểu khai báo của biến quyết định khả năng kiểm tra kiểu lúc biên dịch. Hãy chọn so sánh chính xác `Class` hay kiểm tra quan hệ kiểu tùy yêu cầu.
