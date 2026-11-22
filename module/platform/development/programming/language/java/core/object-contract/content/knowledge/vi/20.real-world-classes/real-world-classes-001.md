# `getClass()` trả về đối tượng `Class` của lớp thực tế

## 1. Khái niệm: lớp thực tế là lớp của đối tượng tại runtime

Trong Java, biến kiểu tham chiếu có **kiểu khai báo** (static/compile-time type), còn đối tượng mà biến trỏ tới có **lớp thực tế khi chạy** (runtime class). Hai thông tin này có thể khác nhau vì tính đa hình và phép gán hướng lên (upcasting).

Phương thức `getClass()` được khai báo trong `java.lang.Object`:

```java
public final native Class<?> getClass();
```

Đây là **chữ ký API**, không phải một phương thức cần tự viết lại. Khi gọi `object.getClass()` trên đối tượng khác `null`, kết quả là đối tượng `java.lang.Class` đại diện cho **lớp runtime chính xác** của đối tượng đó.

Ví dụ ý tưởng:

```java
Animal animal = new Dog();
Class<?> runtimeType = animal.getClass();
```

Nếu `Dog extends Animal`, biến `animal` có kiểu khai báo là `Animal` nhưng đối tượng được tạo là `Dog`. Vì vậy `animal.getClass() == Dog.class` là `true`, còn `animal.getClass() == Animal.class` là `false`. Việc gán đối tượng vào biến kiểu cha **không biến đối tượng Dog thành Animal**.

Các điều cần nhớ:

- `getClass()` là phương thức của **đối tượng**, không phải một cách hỏi trình biên dịch biến đang khai báo kiểu gì.
- Phương thức `getClass()` là `final`: lớp con **không được ghi đè** để nói dối về lớp runtime.
- Kết quả có kiểu `Class<?>` (một đối tượng metadata), **không phải một đối tượng mới của lớp được phản ánh**.
- So sánh `getClass()` với một class literal như `Dog.class` là cách kiểm tra **đúng lớp thực tế**.
- Không thể gọi `null.getClass()`: tham chiếu `null` không đại diện cho đối tượng nên sẽ phát sinh `NullPointerException`.

Bài này tập trung vào nghĩa của `Object.getClass()`, cách đối chiếu với `instanceof` và hệ quả đối với hợp đồng bằng nhau của đối tượng Java.

## 2. Kiểu khai báo khác lớp thực tế thế nào?

Giả sử có quan hệ:

```text
          Animal
          /    \
        Dog    Cat

Biến Animal animal = new Dog()
        |
        v
  Đối tượng Dog ở runtime
```

Một biến kiểu `Animal` có thể tham chiếu tới một `Animal`, một `Dog` hoặc một `Cat` nếu các lớp và điều kiện truy cập cho phép. Kiểu khai báo quyết định **những thành viên có thể gọi trực tiếp trong mã nguồn**, còn lớp runtime quyết định **đối tượng đang tồn tại thực sự thuộc lớp nào** và cách dispatch các phương thức instance có thể ghi đè.

So sánh:

| Biểu thức | Trả lời câu hỏi | Ví dụ với `Animal animal = new Dog()` |
| --- | --- | --- |
| `animal.getClass()` | Đối tượng hiện tại thuộc chính xác lớp runtime nào? | `Dog.class` |
| `animal.getClass() == Dog.class` | Có đúng lớp `Dog` không? | `true` |
| `animal.getClass() == Animal.class` | Có đúng lớp `Animal` không? | `false` |
| `animal instanceof Animal` | Có thể xem đối tượng như một `Animal` không? | `true` |
| `animal instanceof Dog` | Có thể xem đối tượng như một `Dog` không? | `true` |
| `Dog.class.isInstance(animal)` | Kiểm tra quan hệ instance động bằng đối tượng `Class` | `true` |
| `animal.getClass().getSuperclass()` | Lớp cha trực tiếp của lớp runtime là gì? | `Animal.class` |

**Lưu ý:** `getClass()` không tự thực hiện ép kiểu. Biết rằng đối tượng có runtime class là `Dog` không làm biến `animal` tự chuyển kiểu khai báo thành `Dog`. Khi thực sự cần truy cập API riêng của `Dog`, dùng kiểm tra kiểu thích hợp hoặc pattern matching:

```java
if (animal instanceof Dog dog) {
    // dog có kiểu Dog trong phạm vi được phép.
}
```

Đây là đoạn minh họa và cần đặt trong một ngữ cảnh có `Animal`/`Dog` được khai báo. Java 17 hỗ trợ pattern matching cho `instanceof` như trên.

## 3. Một đối tượng `Class` đại diện điều gì?

`java.lang.Class` là kiểu chứa thông tin về một lớp, interface, array class hoặc kiểu đặc biệt được Java biểu diễn bằng class object. `Object.getClass()` trả về metadata của lớp thực tế của một **instance**. Từ `Class<?>`, ta có thể đọc những thông tin phù hợp:

| API | Ý nghĩa |
| --- | --- |
| `getName()` | Tên nhị phân của lớp thông thường; cú pháp riêng cho một số kiểu, ví dụ mảng. |
| `getSimpleName()` | Tên đơn giản phục vụ trình bày; có thể là chuỗi rỗng với một số lớp ẩn danh. |
| `getCanonicalName()` | Tên canonical khi tồn tại; có thể trả về `null`, chẳng hạn một số lớp cục bộ hoặc ẩn danh. |
| `getSuperclass()` | `Class` của lớp cha trực tiếp, hoặc `null` trong các trường hợp không có lớp cha phù hợp. |
| `getInterfaces()` | Mảng `Class<?>` của các interface trực tiếp mà kiểu khai báo thực hiện/kế thừa theo quy tắc API. |
| `isInterface()` | `true` nếu `Class` đại diện cho interface. |
| `isArray()` | `true` nếu kiểu được phản ánh là một array class. |
| `getComponentType()` | Với một array class, trả `Class` của kiểu phần tử; không phải array class thì trả `null`. |
| `isAssignableFrom(otherClass)` | Kiểm tra khả năng gán kiểu tham chiếu từ `otherClass` sang kiểu đại diện bởi `Class` hiện tại. |
| `isInstance(value)` | Kiểm tra động liệu giá trị có là instance của lớp/interface được phản ánh hay không. |

Ví dụ:

```java
Class<?> type = "hello".getClass();

System.out.println(type.getSimpleName());  // String
System.out.println(type == String.class);   // true
System.out.println(type.isInterface());     // false
```

Đoạn trên chỉ minh họa trong một phương thức, không phải một chương trình độc lập. Phần lớn thao tác này thuộc nhóm **reflection** (phản chiếu metadata). Nhưng hiểu `getClass()` không yêu cầu phải tạo đối tượng bằng reflection hoặc thao tác với private field.

### `getClass()` không tạo mới một `Class` cho mỗi lần gọi

Đối với **cùng một lớp đã được định nghĩa trong cùng phạm vi định danh runtime**, các lần gọi `getClass()` trên các instance của lớp đó tham chiếu tới cùng đối tượng `Class`. Vì vậy kiểm tra:

```java
new String("a").getClass() == new String("b").getClass()
```

trả về `true`, mặc dù hai `String` được tạo bằng hai biểu thức `new` là hai đối tượng khác nhau. Đối tượng `Class` đại diện **kiểu**, còn hai chuỗi đại diện **instance**.

Phép so sánh `==` giữa hai biến `Class<?>` là phù hợp để hỏi chúng có biểu diễn **cùng một runtime class** không. Đừng suy từ `==` trên `Class` sang `==` trên các instance của lớp ấy.

## 4. Lớp cha, interface và đa hình

Đối tượng có thể thỏa nhiều quan hệ kiểu, nhưng `getClass()` vẫn trả về **một lớp runtime chính xác**.

Giả sử:

```java
interface Pet {}
class Animal {}
final class Dog extends Animal implements Pet {}
```

Khi `Object value = new Dog()`:

- `value.getClass() == Dog.class` đúng.
- `value.getClass() == Animal.class` sai dù `Dog` kế thừa `Animal`.
- `value.getClass() == Pet.class` sai dù `Dog` triển khai `Pet`; `Pet.class` phản ánh interface, không phải lớp thực tế của instance.
- `value instanceof Animal` và `value instanceof Pet` đều đúng.
- `Animal.class.isInstance(value)` và `Pet.class.isInstance(value)` đều đúng.

Nói cách khác, **“chính xác cùng lớp”** và **“thuộc kiểu hoặc kiểu con”** là hai quan hệ khác nhau. Trong code nghiệp vụ, chọn phép kiểm tra tương ứng với yêu cầu:

- Nếu cho phép mọi đối tượng triển khai một giao diện, dùng `instanceof` hoặc `Class.isInstance`.
- Nếu muốn biết đúng lớp runtime, dùng `getClass() == ExpectedType.class`.
- Nếu cần phương thức có polymorphism, đa số trường hợp chỉ cần gọi phương thức đã khai báo ở interface/lớp cha; không cần hỏi `getClass()` ở từng nhánh.

Lạm dụng `getClass()` rồi viết chuỗi `if/else` cho mọi lớp con có thể làm giảm giá trị của đa hình. Chỉ kiểm tra lớp thực tế khi **lớp cụ thể thực sự là một phần của quy tắc**.

## 5. Chương trình Java 17+ độc lập

Chương trình sau bao quát lớp cha/con, interface, upcast, class literal, record, mảng và `null`. Phần in ra sử dụng `getSimpleName()` và các kết quả boolean ổn định để không phụ thuộc tên package khi chạy.

Lưu trong tệp `RuntimeClassDemo.java`:

```java
public class RuntimeClassDemo {
    interface Pet {}

    static class Animal {}

    static final class Dog extends Animal implements Pet {}

    static final class Cat extends Animal {}

    record Point(int x, int y) {}

    public static void main(String[] args) {
        Animal animal = new Dog();
        Object upcast = animal;

        System.out.println("declared Animal, runtime: "
                + animal.getClass().getSimpleName());
        System.out.println("upcast keeps runtime Class: "
                + (upcast.getClass() == animal.getClass()));
        System.out.println("exactly Dog: "
                + (animal.getClass() == Dog.class));
        System.out.println("exactly Animal: "
                + (animal.getClass() == Animal.class));
        System.out.println("instanceof Animal: "
                + (animal instanceof Animal));
        System.out.println("instanceof Dog: "
                + (animal instanceof Dog));
        System.out.println("implements Pet: "
                + Pet.class.isInstance(animal));
        System.out.println("superclass: "
                + animal.getClass().getSuperclass().getSimpleName());

        Object otherAnimal = new Cat();
        System.out.println("another runtime class: "
                + otherAnimal.getClass().getSimpleName());
        System.out.println("Cat vs Dog Class: "
                + (otherAnimal.getClass() == animal.getClass()));

        Object point = new Point(3, 4);
        System.out.println("record runtime: "
                + point.getClass().getSimpleName());

        int[] numbers = {1, 2};
        System.out.println("int[] exact class: "
                + (numbers.getClass() == int[].class));
        System.out.println("array component is int: "
                + (numbers.getClass().getComponentType() == int.class));
        System.out.println("array Class isArray: "
                + numbers.getClass().isArray());

        Object strings = new String[2];
        System.out.println("String[] vs Object[] exact: "
                + (strings.getClass() == Object[].class));
        System.out.println("String[] is Object[] instance: "
                + (strings instanceof Object[]));

        System.out.println("same Dog Class object: "
                + (new Dog().getClass() == animal.getClass()));
        System.out.println("Class of runtime metadata: "
                + animal.getClass().getClass().getSimpleName());

        Object missing = null;
        try {
            missing.getClass();
        } catch (NullPointerException exception) {
            System.out.println("null getClass: NullPointerException");
        }
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac -encoding UTF-8 RuntimeClassDemo.java
java RuntimeClassDemo
```

Đầu ra:

```text
declared Animal, runtime: Dog
upcast keeps runtime Class: true
exactly Dog: true
exactly Animal: false
instanceof Animal: true
instanceof Dog: true
implements Pet: true
superclass: Animal
another runtime class: Cat
Cat vs Dog Class: false
record runtime: Point
int[] exact class: true
array component is int: true
array Class isArray: true
String[] vs Object[] exact: false
String[] is Object[] instance: true
same Dog Class object: true
Class of runtime metadata: Class
null getClass: NullPointerException
```

### Phân tích các nhóm kết quả

**Kiểu khai báo và upcast:** biến `animal` có kiểu `Animal`, nhưng được gán một instance `Dog`. Chuyển tiếp thành `Object upcast` không đổi đối tượng, do đó `upcast.getClass()` và `animal.getClass()` vẫn là cùng `Dog.class`.

**`getClass` so với `instanceof`:** kiểm tra `animal.getClass() == Animal.class` sai do đối tượng không thuộc *chính xác* lớp `Animal`. Nhưng `animal instanceof Animal` đúng do `Dog` là lớp con. Giao diện `Pet` không thay đổi runtime class là `Dog`, dù `Pet.class.isInstance(animal)` đúng.

**Hai lớp con khác nhau:** `otherAnimal` được tạo là `Cat` nên `getClass().getSimpleName()` là `Cat`; dù cả `Cat` và `Dog` đều là `Animal`, hai đối tượng `Class` cụ thể khác nhau.

**Record:** `Point` cũng là một kiểu tham chiếu có `getClass()`, giống class thông thường. Trong trường hợp này `point.getClass() == Point.class` cũng sẽ đúng. Cơ chế `getClass` không khác biệt chỉ vì cú pháp khai báo là `record`.

**Mảng:** `int[]` và `String[]` đều là đối tượng có array class riêng. `int[].class` phản ánh loại mảng `int[]`, còn `int.class` phản ánh kiểu thành phần nguyên thủy `int`. `String[]` không có **lớp chính xác** là `Object[]`, nhưng có thể dùng ở vị trí `Object[]` bởi quy tắc kiểu của mảng tham chiếu Java. Phân biệt khả năng gán với chính xác cùng lớp.

**`Class` object:** hai `Dog` riêng biệt vẫn trả về cùng đối tượng `Class` của `Dog`. Lời gọi thêm `animal.getClass().getClass()` hỏi lớp của **chính đối tượng metadata `Class`**, nên tên đơn giản in ra là `Class`, không phải `Dog`.

**`null`:** `missing.getClass()` ném `NullPointerException` bởi `missing` không trỏ đến đối tượng nào. Đoạn `try/catch` giúp chương trình tiếp tục, không biến `null` thành một lớp runtime.

## 6. `getClass()` với mảng và kiểu nguyên thủy

### Mảng cũng có lớp runtime

Các biểu thức như:

```java
String[] texts = new String[3];
int[][] grid = new int[2][4];

Class<?> textArrayClass = texts.getClass();
Class<?> gridClass = grid.getClass();
```

cho biết hai đối tượng là các array class khác nhau. `textArrayClass.isArray()` và `gridClass.isArray()` đều đúng. `gridClass.getComponentType()` trả `int[].class` vì phần tử trực tiếp của `int[][]` là một `int[]`, không phải `int`.

Với `Object[] mixed = new String[2]`, biến `mixed` khai báo là `Object[]` nhưng runtime class của mảng vẫn là `String[].class`. Điều này giải thích tại sao Java vẫn kiểm tra loại phần tử thực tế của mảng và có thể ném `ArrayStoreException` nếu cố lưu đối tượng không phù hợp vào một mảng tham chiếu được nhìn qua kiểu rộng hơn:

```java
Object[] mixed = new String[1];
mixed[0] = Integer.valueOf(42); // ArrayStoreException khi chạy.
```

Đây là đoạn minh họa không nên chạy mà không bắt ngoại lệ. Trường hợp này cho thấy **runtime type của array là dữ liệu thật**, chứ không bị thay thế bởi kiểu của biến đang giữ mảng.

### Kiểu nguyên thủy không thể gọi phương thức

`int`, `boolean`, `double` là các kiểu nguyên thủy; một giá trị `int` không phải tham chiếu tới instance nên không có cú pháp hợp lệ `number.getClass()` với `number` là primitive.

Nhưng Java vẫn có **class literal** cho kiểu nguyên thủy:

```java
Class<?> primitive = int.class;
Class<?> wrapper = Integer.class;

System.out.println(primitive.isPrimitive()); // true
System.out.println(wrapper.isPrimitive());   // false
```

Đây là đoạn dùng trong một phương thức. Nếu cần một đối tượng bọc giá trị `int`, `Integer.valueOf(5).getClass()` sẽ trả `Integer.class`, không phải `int.class`. Class literal `int.class` là metadata của kiểu nguyên thủy chứ không phải kết quả gọi phương thức trên một giá trị primitive.

### Interface không phải runtime class chính xác của đối tượng triển khai

`Runnable.class`, `Comparable.class` và các class literal giao diện khác đều là đối tượng `Class` hợp lệ. Nhưng với một đối tượng triển khai `Runnable`, `getClass()` cho biết **lớp thực thi cụ thể**, không trả chính `Runnable.class`. Muốn kiểm tra đối tượng có triển khai interface hay không, dùng `instanceof Runnable` hoặc `Runnable.class.isInstance(value)`.

## 7. `getClass()` trong thiết kế `equals(Object)`: so sánh lớp chính xác

Một ứng dụng quan trọng trong chủ đề hợp đồng đối tượng là chọn **miền các kiểu được phép bằng nhau**.

Giả sử lớp giá trị chỉ muốn bằng đối tượng **đúng lớp runtime**. Có thể kiểm tra:

```java
if (other == null || getClass() != other.getClass()) {
    return false;
}
```

Đây là đoạn bên trong một triển khai `equals(Object)`. Kiểm tra trên `other` sau khi xác nhận nó không `null` để tránh NPE. Sau điều kiện này, hai đối tượng có cùng lớp runtime và có thể tiếp tục so các trường ý nghĩa.

### Ví dụ về `equals` dùng kiểm tra lớp chính xác

```java
import java.util.Objects;

final class Coordinate {
    private final int x;
    private final int y;

    Coordinate(int x, int y) {
        this.x = x;
        this.y = y;
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) {
            return true;
        }
        if (other == null || getClass() != other.getClass()) {
            return false;
        }
        Coordinate that = (Coordinate) other;
        return x == that.x && y == that.y;
    }

    @Override
    public int hashCode() {
        return Objects.hash(x, y);
    }
}
```

Đây là một lớp hỗ trợ hợp lệ trong cùng package/tệp Java (không phải chương trình có `main`). `Coordinate` là `final` nên không có lớp con; kiểm tra `getClass` thể hiện cách yêu cầu đúng kiểu. `equals` xác nhận hai tọa độ bằng nhau theo `x` và `y`, còn `hashCode` dùng cùng dữ liệu để đáp ứng hợp đồng hash. Cặp `getClass` và `hashCode` không thay thế nhau: câu hỏi “đúng lớp không?” và “giá trị các trường bằng nhau không?” đều cần được trả lời.

### Khi nào `getClass()` khác `instanceof` trong `equals`?

- `getClass() == other.getClass()`: chỉ cho phép **chính xác cùng lớp runtime**. Một instance lớp cha không bao giờ bằng instance lớp con nếu khác lớp runtime, dù các trường chung trùng nhau.
- `other instanceof Base`: cho phép đối tượng thuộc lớp `Base` hoặc lớp con của nó vượt qua kiểm tra kiểu. Đây có thể là lựa chọn đúng nếu quy tắc bằng nhau thực sự được định nghĩa thống nhất cho toàn thứ bậc.
- Một lớp cha cho phép bằng lớp con, nhưng lớp con chỉ cho bằng chính nó, có thể gây **vi phạm tính đối xứng** (`a.equals(b)` khác `b.equals(a)`). Nếu các lớp thêm tiêu chí so sánh, còn có nguy cơ phá bắc cầu.

Vì vậy **không có quy tắc “mọi `equals` đều phải dùng `getClass`”**. Hãy thiết kế quan hệ bằng nhau trước; dùng `getClass` hoặc `instanceof` theo chính sách type-equivalence của domain. `final` value class hoặc record (khi phù hợp) giúp tránh một số xung đột kế thừa, nhưng không tự xử lý mọi component mutable hoặc so sánh sai.

Đặc biệt, dùng `getClass()` trong `equals` không nhất thiết phù hợp với mô hình có proxy/subclass sinh bởi framework: đối tượng proxy có thể có runtime class khác lớp entity gốc. Đừng áp nguyên tắc này máy móc lên các entity của ORM; cần tuân theo chiến lược danh tính và proxy của framework đang dùng.

## 8. Tại sao tên lớp chưa chắc là danh tính lớp?

`Class.getName()`, `getSimpleName()` và `getCanonicalName()` chủ yếu cung cấp **tên và mô tả**. Nhưng định danh class ở runtime không chỉ do chuỗi tên quyết định: trong hệ thống có nhiều class loader, hai lớp với **cùng tên nhị phân** được định nghĩa bởi **hai class loader khác nhau** có thể là hai lớp khác nhau theo JVM.

Hệ quả:

- Không thay `first.getClass() == second.getClass()` bằng `first.getClass().getName().equals(second.getClass().getName())` khi cần kiểm tra **cùng lớp runtime chính xác**.
- `getClass().getSimpleName()` là chuỗi có ích để ghi log/hiển thị nhưng không phải khóa danh tính duy nhất.
- Các lớp lồng thường có tên nhị phân chứa dấu `$` (ví dụ `RuntimeClassDemo$Dog`). Lớp ẩn danh hoặc lớp cục bộ có quy tắc tên khác, và `getSimpleName()` có thể rỗng.
- Proxy được framework sinh động có thể có tên lớp bất ngờ dù đối tượng vẫn triển khai interface/kế thừa kiểu gốc.
- Nếu cần làm việc với metadata thực sự, giữ đối tượng `Class<?>` và dùng API của nó thay vì tự phân tích chuỗi tên bằng thủ thuật cắt ký tự.

Chỉ cần biết giới hạn trên để tránh nhầm lẫn. Việc tự tạo class loader, định nghĩa lớp động hoặc khám phá toàn bộ reflection là chủ đề sâu hơn, không cần cho cách dùng `getClass()` thông thường.

## 9. `getClass()`, `Class.isInstance`, `isAssignableFrom` và `instanceof`

Các công cụ sau dễ bị nhầm tên nhưng trả lời những câu hỏi khác nhau:

| Biểu thức | Cách hiểu |
| --- | --- |
| `obj.getClass() == Target.class` | Instance có **chính xác** lớp `Target` không? |
| `obj instanceof Target` | Instance có thuộc `Target` hoặc kiểu con/kiểu triển khai phù hợp không? |
| `Target.class.isInstance(obj)` | Biến thể động của kiểm tra instance dựa trên `Class` của đích. |
| `Target.class.isAssignableFrom(actualClass)` | Có thể gán một tham chiếu kiểu `actualClass` vào biến kiểu `Target` không? |
| `obj.getClass().getSuperclass() == Parent.class` | Lớp cha trực tiếp của lớp runtime có đúng là `Parent` không? |

Hai cách kiểm tra có thể khác nhau:

```java
// Giả sử Dog extends Animal và Object obj = new Dog();
boolean exact = obj.getClass() == Animal.class; // false
boolean assignable = Animal.class.isInstance(obj); // true
boolean classRelation =
        Animal.class.isAssignableFrom(obj.getClass()); // true
```

Đoạn minh họa đặt trong phương thức có các kiểu `Animal`/`Dog`. Với mục tiêu xử lý mọi loại `Animal`, kiểm tra theo kiểu kế thừa thường phù hợp; với mục tiêu chặn mọi lớp con khác, phép kiểm tra `getClass` mới thể hiện chính sách.

Chú ý hướng của `isAssignableFrom`: `Parent.class.isAssignableFrom(Child.class)` thường là đúng khi `Child extends Parent`, còn đảo chiều không nhất thiết đúng.

## 10. Lỗi thường gặp và cách sửa

| Lỗi | Vì sao sai | Hướng đúng |
| --- | --- | --- |
| Nghĩ `obj.getClass()` trả kiểu khai báo của biến | Upcast chỉ thay cách nhìn của trình biên dịch, không thay đối tượng. | Dùng `getClass` để đọc lớp runtime; xem khai báo biến để biết static type. |
| So `getClass() == Parent.class` rồi cho rằng mọi lớp con cũng khớp | `==` giữa các đối tượng `Class` yêu cầu chính xác một lớp. | Dùng `instanceof Parent` hoặc `Parent.class.isInstance(obj)` nếu cần nhận lớp con. |
| Gọi `getClass()` trên `null` | `null` không có instance để dispatch phương thức. | Kiểm tra `obj != null` trước khi gọi; dùng `obj instanceof Type` nếu phù hợp vì `null instanceof Type` trả `false`. |
| Tìm cách ghi đè `getClass()` ở lớp con | `Object.getClass` là `final`. | Không override; dùng một phương thức domain riêng nếu muốn nhãn/loại nghiệp vụ tùy biến. |
| Lấy `getSimpleName()` làm định danh class duy nhất | Nhiều lớp ở package/loader khác nhau có thể trùng tên đơn giản. | Giữ `Class<?>` khi cần đúng lớp runtime; tên chỉ dùng để hiển thị. |
| Dùng `getClass()` trong mọi `equals` mà không xét domain | Có thể từ chối proxy/lớp con vốn cần bằng nhau theo quy tắc nghiệp vụ. | Quy định miền kiểu của equality trước khi chọn `getClass` hay `instanceof`. |
| So hash code của hai đối tượng `Class` thay vì so chính các `Class` | Hai hash giống nhau không bảo đảm cùng lớp. | So `Class` trực tiếp bằng `==` hoặc `equals`. |
| Nghĩ mảng chỉ có kiểu `Object` tại runtime | Mỗi loại array có runtime class riêng. | Dùng `getClass().isArray()`/`getComponentType()` hoặc class literal của mảng. |
| Nghĩ `int.class` là đối tượng `Integer` hay kết quả của `intValue.getClass()` | Primitive không có phương thức instance; wrapper là một lớp khác. | Phân biệt `int.class`, `Integer.class` và boxing. |
| Dùng chuỗi tên của lớp để dispatch mọi loại hành vi | Dễ hỏng khi đổi tên, thay class loader hoặc gặp proxy. | Ưu tiên interface, polymorphism, hoặc `Class`/`instanceof` khi cần phân nhánh thật sự. |

## 11. Checklist tự kiểm tra

Để chắc chắn hiểu `getClass()`, thử trả lời rồi chạy các tình huống:

1. Với `Object obj = new String("a")`, `obj.getClass()` là `String.class` hay `Object.class`? **`String.class`**.
2. Với `Animal animal = new Dog()`, vì sao `animal.getClass() == Animal.class` sai nhưng `animal instanceof Animal` đúng? **Một phép so chính xác lớp; phép còn lại xét quan hệ subtype**.
3. Hai đối tượng `new Dog()` khác nhau có cùng đối tượng `Class` không? **Có, nếu được tạo từ cùng lớp runtime đã định nghĩa**.
4. `getClass()` có thể trả trực tiếp interface `Pet.class` trên một instance `Dog implements Pet` không? **Không**, nó trả lớp runtime cụ thể `Dog.class`.
5. `new int[3].getClass() == int[].class` có đúng không? **Có**.
6. `int.class.isPrimitive()` khác `Integer.class.isPrimitive()` thế nào? **Lần lượt là `true` và `false`**.
7. `getClass()` có an toàn cho `null` không? **Không**, nó gây `NullPointerException`.
8. Trong `equals`, có khi nào kiểm tra exact class làm thay đổi chính sách bằng nhau giữa cha và con? **Có**, nên phải định nghĩa policy trước.
9. Nếu hai đối tượng trả cùng `getClass().getSimpleName()`, chắc chắn chúng có cùng `Class`? **Không**, tên ngắn không phải định danh duy nhất.
10. Nếu muốn chấp nhận bất kỳ implementer nào của một interface, `getClass()==Interface.class` hay `instanceof Interface` phù hợp? **`instanceof Interface`**.

## 12. Ghi nhớ

`Object.getClass()` trả về **đối tượng `Class` của lớp thực tế tại runtime**, bất kể kiểu khai báo của biến hay việc đối tượng được upcast qua bao nhiêu lớp/giao diện. Phương thức là `final` và yêu cầu tham chiếu khác `null`. Dùng `getClass() == SomeType.class` để kiểm tra **đúng lớp**, dùng `instanceof` hoặc `Class.isInstance` khi cần quan hệ **lớp con hoặc triển khai interface**. Mảng và record đều có lớp runtime; primitive có class literal nhưng không gọi `getClass` được. Khi dùng `getClass` trong `equals` hay reflection, phải hiểu chính sách danh tính kiểu và giới hạn của tên lớp, thay vì nhầm lẫn giữa metadata, quan hệ kế thừa và giá trị của đối tượng.