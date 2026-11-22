# `getClass()` là `final` và không thể ghi đè trong Java

## 1. Mục tiêu bài học

Trong Java, mọi đối tượng đều kế thừa phương thức `getClass()` từ `java.lang.Object`. Khi gọi phương thức này trên một tham chiếu **khác `null`**, Java trả về đối tượng `Class<?>` đại diện cho **lớp thực tế lúc chạy** (runtime class) của chính đối tượng ấy.

Bài học tập trung vào hai sự thật gắn liền nhau:

1. `Object.getClass()` là phương thức **`final`**, vì vậy mọi lớp con, kể cả lớp tự định nghĩa, record hay enum, **không được override nó**.
2. Kết quả `getClass()` phản ánh **kiểu thực của đối tượng**, có thể khác kiểu biến tham chiếu được khai báo trong mã nguồn.

Nắm rõ chúng giúp bạn dùng đúng thông tin kiểu trong Java, phân biệt so kiểu chính xác với so theo quan hệ kế thừa, và tránh thiết kế sai các phương thức `equals()`.

## 2. Khai báo của `Object.getClass()`

Trong `java.lang.Object`, chữ ký phương thức có dạng:

```java
public final native Class<?> getClass();
```

Đây là **khai báo minh họa chữ ký từ JDK**, không phải đoạn mã bạn có thể tự thêm vào một lớp để chạy độc lập. Ý nghĩa từng phần:

- **`public`:** có thể gọi trên bất kỳ đối tượng nào mà bạn có tham chiếu hợp lệ.
- **`final`:** lớp kế thừa không thể ghi đè phương thức cùng chữ ký. Quy tắc được trình biên dịch Java kiểm tra.
- **`native`:** phần hiện thực được cung cấp qua cơ chế mức thấp của JVM/runtime, thay vì một thân phương thức Java trong khai báo trên.
- **`Class<?>`:** kiểu kết quả biểu diễn metadata của một lớp/kiểu runtime; nó không phải chuỗi tên lớp. Có thể dùng các API phản chiếu (reflection) như `getName()`, `getSuperclass()`, `isInterface()`, `isAssignableFrom()`.

Đối với một đối tượng tồn tại trong JVM, lớp thực tế của nó đã được xác định khi đối tượng được tạo ra. Việc gán đối tượng đó sang một biến có kiểu cha hoặc interface không thay đổi lớp thực tế ấy, nên `getClass()` vẫn trả metadata của kiểu runtime ban đầu.

**Điểm cần phân biệt:** `getClass()` là phương thức **`final`**, nhưng điều đó không có nghĩa mọi lớp chứa phương thức ấy đều là `final`. Ví dụ, `Animal` có thể không `final` và vẫn được kế thừa, mặc dù phương thức `getClass()` kế thừa từ `Object` luôn không thể bị ghi đè.

## 3. Kiểu khai báo và lớp thực tế khác nhau ra sao?

Ví dụ:

```java
class Animal {}
class Dog extends Animal {}

Animal pet = new Dog();
```

`pet` có **kiểu khai báo** `Animal`. Nhưng đối tượng được tạo bởi `new Dog()` có **runtime class** là `Dog`.

Vì vậy:

```java
pet.getClass() == Dog.class;    // true
pet.getClass() == Animal.class; // false
pet instanceof Animal;          // true
pet instanceof Dog;             // true
```

Đây là các biểu thức minh họa dựa trên biến `pet` khai báo phía trên. Hãy hiểu hai kiểm tra khác nhau:

- `pet.getClass() == Dog.class` hỏi: “Đối tượng này thuộc **chính xác** lớp `Dog` ở runtime không?”
- `pet instanceof Animal` hỏi: “Đối tượng này có tương thích với kiểu `Animal`, bao gồm lớp con không?”

Phương thức `getClass()` không bị “che” bởi kiểu biến `Animal`. Việc gọi trên một biến kiểu cha vẫn cho metadata của lớp thực tế, kể cả khi lớp con không hề định nghĩa lại `getClass()`.

### `SomeType.class` khác `obj.getClass()` thế nào?

`Dog.class` là **class literal**: lấy `Class` của kiểu được nêu trực tiếp trong mã; không cần tạo một thể hiện của `Dog`.

`pet.getClass()` là **truy vấn runtime** trên đối tượng cụ thể đang được tham chiếu. Nếu một ngày biến `pet` giữ `new Cat()` thay vì `new Dog()`, kết quả có thể là `Cat.class`.

Cả hai trả về đối tượng `Class` đại diện cho kiểu tương ứng. Trong cùng phạm vi kiểu đã được JVM nạp, nhiều thể hiện của cùng một lớp chia sẻ đối tượng `Class`:

```java
new Dog().getClass() == new Dog().getClass(); // true
```

Hai thể hiện `Dog` ở biểu thức này **không phải cùng một đối tượng Dog**; chúng chỉ có cùng lớp thực tế. Vì thế `a.getClass() == b.getClass()` không đồng nghĩa với `a == b` hoặc `a.equals(b)`.

## 4. Vì sao không được override `getClass()`?

Nếu một lớp có thể giả mạo metadata kiểu runtime thông qua override, kết quả của `getClass()` sẽ không còn là nguồn thông tin đáng tin cậy về lớp thực sự mà JVM đang quản lý. Java vì vậy khóa phương thức tại `Object` bằng `final`.

Ví dụ **cố ý sai, sẽ không biên dịch**:

```java
class FakeType {
    @Override
    public Class<?> getClass() {
        return String.class;
    }
}
```

Lỗi biên dịch về bản chất là: `getClass()` không thể override phương thức `final` trong `Object`. Bỏ `@Override` cũng không giúp: chữ ký vẫn trùng với phương thức `final` được kế thừa.

Tương tự, ta không thể override `getClass()` trong:

- Một lớp con bình thường, kể cả lớp con sâu nhiều cấp.
- Một record: record kế thừa `Object` (thông qua `java.lang.Record`) và vẫn chịu ràng buộc `final` của `getClass()`.
- Một enum: enum kế thừa `java.lang.Enum` rồi đến `Object`.
- Một lớp vô danh hoặc thân lớp riêng của hằng enum.

Nếu chỉ muốn cung cấp **nhãn loại nghiệp vụ**, hãy đặt một phương thức **khác tên**, ví dụ `kind()`, `typeCode()`, `displayType()`; không cố thay đổi `Object.getClass()`.

## 5. Ví dụ Java 17+ hoàn chỉnh

Tạo tệp **`GetClassFinalDemo.java`**:

```java
import java.util.ArrayList;

public class GetClassFinalDemo {

    static class Animal {}

    static class Dog extends Animal {}

    record Point(int x, int y) {}

    enum Mode {
        SIMPLE,
        CUSTOM {
            @Override
            String label() {
                return "custom";
            }
        };

        String label() {
            return "simple";
        }
    }

    static boolean sameRuntimeClass(Object left, Object right) {
        return left != null
                && right != null
                && left.getClass() == right.getClass();
    }

    public static void main(String[] args) {
        Animal animal = new Animal();
        Animal dogAsAnimal = new Dog();
        Object anonymous = new Animal() {};
        Object point = new Point(1, 2);

        System.out.println("declared Animal, runtime Dog: "
                + (dogAsAnimal.getClass() == Dog.class));
        System.out.println("dog instanceof Animal: "
                + (dogAsAnimal instanceof Animal));
        System.out.println("Animal vs Dog same class: "
                + (animal.getClass() == dogAsAnimal.getClass()));
        System.out.println("two Dog instances same Class: "
                + (new Dog().getClass() == dogAsAnimal.getClass()));
        System.out.println("same runtime class Dog vs Animal: "
                + sameRuntimeClass(dogAsAnimal, animal));
        System.out.println("record runtime class: "
                + (point.getClass() == Point.class));

        System.out.println("anonymous exactly Animal: "
                + (anonymous.getClass() == Animal.class));
        System.out.println("anonymous superclass Animal: "
                + (anonymous.getClass().getSuperclass()
                        == Animal.class));
        System.out.println("anonymous canonical name null: "
                + (anonymous.getClass().getCanonicalName() == null));

        System.out.println("enum constant class is Mode: "
                + (Mode.CUSTOM.getClass() == Mode.class));
        System.out.println("enum declaring class is Mode: "
                + (Mode.CUSTOM.getDeclaringClass() == Mode.class));

        Object strings = new ArrayList<String>();
        Object numbers = new ArrayList<Integer>();
        System.out.println("erased generic class same: "
                + (strings.getClass() == numbers.getClass()));

        Object missing = null;
        System.out.println("missing == null: " + (missing == null));
        try {
            missing.getClass();
        } catch (NullPointerException ex) {
            System.out.println("missing.getClass() throws NPE");
        }
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac GetClassFinalDemo.java
java GetClassFinalDemo
```

**Kết quả chuẩn:**

```text
declared Animal, runtime Dog: true
dog instanceof Animal: true
Animal vs Dog same class: false
two Dog instances same Class: true
same runtime class Dog vs Animal: false
record runtime class: true
anonymous exactly Animal: false
anonymous superclass Animal: true
anonymous canonical name null: true
enum constant class is Mode: false
enum declaring class is Mode: true
erased generic class same: true
missing == null: true
missing.getClass() throws NPE
```

**Giải thích các nhóm kết quả:**

1. `dogAsAnimal` có kiểu khai báo `Animal` nhưng là `new Dog()`, do đó `getClass() == Dog.class` là `true`. `instanceof Animal` cũng là `true` do quan hệ kế thừa.
2. `animal` và `dogAsAnimal` có lớp runtime khác nhau, nên phép so hai đối tượng `Class` là `false`. Hai thể hiện `Dog` độc lập lại có **cùng lớp** và chia sẻ metadata `Class`.
3. `sameRuntimeClass` so chính xác hai lớp và chủ động kiểm tra null ở cả hai phía. Hai đối tượng được tạo khác lớp cho kết quả `false`.
4. `Point` là record, nhưng record vẫn là một kiểu runtime cụ thể. `point.getClass()` trả `Point.class`.
5. `new Animal() {}` tạo **lớp con vô danh** của `Animal`. Đối tượng đó là `Animal` theo `instanceof`, nhưng lớp thực tế **không phải chính** `Animal.class`. `getSuperclass()` cho biết lớp cha trực tiếp là `Animal`, còn lớp vô danh không có tên canonical nên `getCanonicalName() == null`.
6. `Mode.CUSTOM` có **constant-specific class body**, do đó runtime class của hằng này có thể là một lớp con của enum `Mode`, khác `Mode.class`. `getDeclaringClass()` của hằng vẫn trả lớp enum khai báo, tức `Mode.class`.
7. Hai `ArrayList` với đối số kiểu `String` và `Integer` có cùng lớp runtime `ArrayList` sau khi type erasure. `getClass()` của thể hiện không cho phép suy ra đầy đủ generic type argument.
8. Gọi phương thức trên tham chiếu `null` ném `NullPointerException`; kiểm tra `missing == null` được phép và không gọi phương thức.

## 6. `getClass()`, `instanceof`, `Class.isInstance`: chọn đúng câu hỏi

| Cách kiểm tra | Ý nghĩa | Kết quả với `new Dog()` khi so `Animal` |
| --- | --- | --- |
| `obj.getClass() == Animal.class` | Lớp runtime **chính xác** là `Animal` | `false` |
| `obj instanceof Animal` | Đối tượng là `Animal` hoặc subtype | `true` |
| `Animal.class.isInstance(obj)` | Kiểm tra runtime xem đối tượng có thể dùng như `Animal` không | `true` |
| `Animal.class.isAssignableFrom(obj.getClass())` | Xem lớp `Animal` có thể nhận một giá trị của lớp runtime bên phải không | `true` nếu `obj` khác null |
| `obj == other` | Hai tham chiếu trỏ cùng đối tượng hay không | Không suy ra được chỉ từ tên lớp |

`instanceof` và `Class.isInstance` được thiết kế cho bài toán **tương thích kiểu**, chẳng hạn một nhánh xử lý áp dụng cho mọi lớp triển khai interface. `getClass() == SomeClass.class` dành cho bài toán cần đúng **lớp cụ thể**, không chấp nhận subtype.

Ví dụ với interface:

```java
interface Payable {}
final class Invoice implements Payable {}

Object value = new Invoice();

boolean isPayable = value instanceof Payable;          // true
boolean runtimeInvoice = value.getClass() == Invoice.class; // true
```

Đoạn này minh họa hai câu hỏi khác nhau, không phải một chương trình có `main`. Phần lớn mã ứng dụng tận dụng **đa hình** nên nên xử lý qua interface hoặc `instanceof` thay vì rẽ nhánh liên tục theo tên lớp. Chỉ chọn kiểm tra lớp chính xác khi đó thật sự là một yêu cầu của nghiệp vụ hoặc API.

## 7. Liên hệ với `equals()`: vì sao có người dùng `getClass()`?

Khi tự viết quan hệ bằng nhau theo giá trị, có hai chiến lược phổ biến để kiểm tra đối tượng bên phải:

**Chiến lược kiểm tra lớp chính xác:**

```java
@Override
public boolean equals(Object other) {
    if (this == other) return true;
    if (other == null || getClass() != other.getClass()) return false;
    PointValue that = (PointValue) other;
    return x == that.x && y == that.y;
}
```

Đây là **thân phương thức minh họa** của một lớp `PointValue` có hai trường `int x`, `int y`; cần định nghĩa `hashCode()` phù hợp để thành một lớp value hoàn chỉnh. Điều kiện `getClass() != other.getClass()` loại mọi subtype khỏi quan hệ bằng nhau. Trong một kiểu có thể bị kế thừa, điều này đôi khi là quyết định có chủ đích để tránh các tình huống phức tạp về đối xứng/bắc cầu của `equals`.

**Chiến lược kiểm tra loại tương thích:**

```java
if (!(other instanceof PointValue value)) {
    return false;
}
```

Cách dùng `instanceof` có thể chấp nhận subtype. Điều này hợp lý khi tất cả subtype được phép tham gia **cùng một quan hệ bằng nhau** và các quy tắc thật sự giữ được hợp đồng `equals`. Nhưng nếu subtype bổ sung các trường tham gia equality, triển khai sơ suất có thể phá đối xứng hoặc bắc cầu.

**Không có một quy tắc “luôn phải dùng `getClass`” cho mọi lớp**. Phụ thuộc vào mô hình dữ liệu và hợp đồng equality:

- Với value class `final` hoặc record, không có subclass ứng dụng; `instanceof` và kiểm tra lớp chính xác thường tương đương cho các thể hiện cùng kiểu được xét.
- Với phân cấp kế thừa có mở rộng dữ liệu, cần thiết kế quan hệ bằng nhau rất cẩn thận; có thể giới hạn đúng lớp bằng `getClass()` hoặc ưu tiên composition/value object `final`.
- Đừng nhầm việc `getClass()` là `final` với việc `equals()` luôn so lớp chính xác. `Object.equals()` mặc định so **danh tính**; nhiều lớp tự override `equals()` theo ngữ nghĩa riêng. `getClass()` không tự được gọi bởi mọi triển khai `equals`.

### Trường hợp proxy hoặc lớp sinh động

Một đối tượng proxy/subclass do framework tạo có thể có lớp runtime khác với lớp domain mà chương trình nghĩ tới. Nếu dùng `getClass() == Domain.class` cứng nhắc, đối tượng ấy có thể bị từ chối dù nó vẫn tương thích với `Domain` theo `instanceof`. Trong các framework, cần đọc hợp đồng proxy và equality tương ứng; không tự giả định một thực thể proxy và thực thể gốc phải bằng nhau.

## 8. Các tình huống đặc biệt thường gặp

### 8.1. Lớp vô danh và lớp lồng

`getClass()` không trả “lớp cha gần nhất” mà trả chính lớp runtime, kể cả khi tên lớp được trình biên dịch sinh ra. Lớp vô danh có thể không có canonical name; không dựa vào `getSimpleName()` hoặc một tên có dấu `$` để xác định loại nghiệp vụ.

`getSuperclass()` là API khác: nó trả superclass trực tiếp của một `Class` (hoặc null cho một số loại như interface, primitive hoặc `Object.class`). Nó không thay thế `getClass()`.

### 8.2. Enum có constant-specific class body

Nếu enum định nghĩa phương thức riêng cho từng hằng bằng thân lớp, một hằng có thể có runtime class khác lớp enum khai báo. Muốn lấy **kiểu enum gốc**, dùng `someEnum.getDeclaringClass()`. Muốn kiểm tra đúng **hằng** nào, dùng `==` với hằng tương ứng.

Không giả định rằng mọi `enumConstant.getClass() == MyEnum.class` đều đúng khi enum có constant-specific class body.

### 8.3. Kiểu nguyên thủy và mảng

Primitive không phải đối tượng để gọi instance method:

```java
int number = 42;
// number.getClass(); // Sai: int là kiểu nguyên thủy, không có getClass().
Class<?> primitiveType = int.class;
Class<?> boxedType = Integer.valueOf(number).getClass();
```

Đoạn trên là minh họa khai báo biến. `primitiveType` biểu diễn kiểu nguyên thủy `int`; `boxedType` biểu diễn lớp `Integer`. Chúng không bằng nhau.

Mảng là đối tượng, nên `new String[0].getClass() == String[].class` là `true`. Đừng suy ra mảng là `String.class`: lớp của `String[]` khác lớp của từng phần tử `String`.

### 8.4. Generic type erasure

Với:

```java
Object first = new java.util.ArrayList<String>();
Object second = new java.util.ArrayList<Integer>();

boolean sameClass = first.getClass() == second.getClass(); // true
```

`getClass()` không đưa ra tham số kiểu generic `String` hoặc `Integer` của từng lần khởi tạo khi thông tin ấy đã bị xóa bởi type erasure. API reflection về generic declarations có thể đọc cấu trúc generic trong **khai báo lớp/trường/phương thức** khi metadata tồn tại, nhưng không biến mỗi đối tượng `ArrayList<T>` thành một lớp runtime khác nhau cho từng `T`.

### 8.5. Lớp nạp bởi các class loader khác nhau

Tên đầy đủ giống nhau không phải lúc nào cũng có nghĩa đó là **cùng một kiểu runtime**. Java tính danh tính lớp theo định danh lớp và class loader xác định lớp đó. Khi cùng tên lớp được nạp độc lập bởi những bộ nạp khác nhau, hai đối tượng `Class` có thể khác nhau. So `Class<?>` bằng `==` phản ánh đúng danh tính runtime; so các chuỗi từ `getName()` có thể chỉ nói chúng **cùng tên**, không chứng minh cùng lớp.

Trong ứng dụng thông thường, điều này ít xuất hiện; trong plugin system, app server, hot deployment hoặc môi trường module phức tạp, đây là nguyên nhân quan trọng của lỗi tương thích kiểu.

## 9. `getClass()` và reflection

Một khi đã có đối tượng `Class<?>`, có thể xem thông tin cấu trúc mà không làm thay đổi bản chất của đối tượng:

```java
Object value = "hello";
Class<?> type = value.getClass();

String binaryName = type.getName();       // "java.lang.String"
String simpleName = type.getSimpleName(); // "String"
boolean isString = type == String.class;  // true
```

Đây là đoạn Java minh họa có thể đặt trong `main`. Reflection còn có các phương thức để truy vấn constructor, field, method hoặc annotation theo quy tắc truy cập của Java. `getClass()` tự nó **không** tự động đọc hết trường dữ liệu, không thay đổi khả năng truy cập thành viên và không biến một đối tượng thành một thể hiện của lớp khác.

Khi cần tạo đối tượng kiểu đã biết ngay tại thời điểm biên dịch, hãy ưu tiên `SomeClass.class`. Khi nhận một `Object` bất kỳ và phải biết kiểu runtime, dùng `getClass()` sau khi đã xử lý khả năng null.

## 10. Lỗi phổ biến và cách tránh

| Nhận định hoặc cách làm | Vấn đề | Cách đúng |
| --- | --- | --- |
| “Biến `Animal` luôn trả `Animal.class`.” | Sai nếu nó trỏ tới `Dog` hoặc lớp con khác. | `getClass()` trả lớp thực tế của đối tượng. |
| “Override `getClass()` để hiển thị loại riêng.” | Phương thức của `Object` là `final`; không biên dịch. | Định nghĩa `kind()` hoặc phương thức tên khác. |
| “`getClass() == Base.class` kiểm tra cả lớp con.” | Nó chỉ nhận **đúng lớp Base**. | Dùng `instanceof Base` nếu muốn nhận subtype. |
| “Hai đối tượng có cùng `getClass()` thì `equals()` bằng nhau.” | Cùng kiểu không chứng minh bằng nhau về danh tính hay giá trị. | Dùng hợp đồng `equals` hoặc `==` theo mục đích. |
| “Có thể gọi `value.getClass()` khi `value` là null.” | Ném `NullPointerException`. | Kiểm tra null trước hoặc dùng `instanceof` khi phù hợp. |
| “So `getClass().getName()` luôn đủ xác định lớp.” | Có thể cùng tên nhưng khác class loader. | So `Class` theo danh tính khi thực sự cần exact runtime class. |
| “`getClass()` phân biệt được `List<String>` và `List<Integer>`.” | Generic args thường bị xóa trong runtime instance type. | Đưa thông tin kiểu vào API/`Class<T>` hoặc type token khi cần. |
| “Mọi hằng enum có `getClass() == MyEnum.class`.” | Constant-specific class body có runtime subclass. | Dùng `getDeclaringClass()` cho kiểu enum khai báo. |
| “`getClass()` final làm mọi lớp con thành final.” | Ràng buộc final chỉ áp dụng phương thức đó. | Phân biệt `final` method với `final` class. |
| “`getClass()` và `getSuperclass()` tương đương.” | Một cái là lớp runtime đối tượng, một cái hỏi lớp cha của metadata `Class`. | Chọn API theo câu hỏi cần trả lời. |

## 11. Checklist lựa chọn nhanh

1. **Muốn biết chính xác lớp của một đối tượng?** Kiểm tra nó khác `null`, sau đó dùng `obj.getClass()`.
2. **Muốn đối tượng có tương thích một interface/lớp cha?** Dùng `instanceof` hoặc `Class.isInstance`.
3. **Muốn metadata của kiểu đã biết khi biên dịch?** Dùng `Type.class`; không cần tạo một đối tượng chỉ để gọi `getClass()`.
4. **Muốn so hai lớp runtime chính xác?** Dùng `a.getClass() == b.getClass()` sau khi xử lý null.
5. **Muốn kiểm tra hai đối tượng giống nhau về dữ liệu?** Dùng quan hệ `equals()` của lớp đã định nghĩa, không suy ra từ `getClass()`.
6. **Muốn kiểu enum khai báo dù hằng có thân lớp riêng?** Dùng `enumValue.getDeclaringClass()`.
7. **Muốn tạo loại nghiệp vụ do người dùng định nghĩa?** Tạo API tên khác; `Object.getClass()` không thể override.

## 12. Tự kiểm tra

**Câu 1.** `Animal x = new Dog();`. `x.getClass() == Animal.class` là `true` hay `false`?

**Đáp án:** `false`, vì runtime class là `Dog`. `x instanceof Animal` vẫn là `true`.

**Câu 2.** Có thể khai báo `public Class<?> getClass()` trong lớp riêng để “thay kết quả” của `Object.getClass()` không?

**Đáp án:** Không. `Object.getClass()` là `final`; phương thức cùng chữ ký không được override.

**Câu 3.** Hai đối tượng khác nhau của `Dog` có cùng `getClass()` không? Có chắc chắn `equals()` bằng nhau không?

**Đáp án:** Chúng có cùng `Class` runtime. `equals()` còn phụ thuộc quy tắc của lớp; không thể suy từ cùng kiểu.

**Câu 4.** Vì sao `new Animal() {}` không có `getClass() == Animal.class`?

**Đáp án:** Đó là một lớp con vô danh thực sự; runtime class là lớp con ấy.

**Câu 5.** Tại sao `getClass()` của hai `ArrayList<String>` và `ArrayList<Integer>` giống nhau?

**Đáp án:** Cả hai là thể hiện runtime của `ArrayList`; thông tin generic type argument không tạo lớp runtime tách biệt sau type erasure.

**Câu 6.** Khi cần kiểm tra một giá trị thuộc subtype của `Base`, dùng `obj.getClass() == Base.class` hay `obj instanceof Base`?

**Đáp án:** `obj instanceof Base`. Cách kiểm tra lớp bằng nhau chính xác sẽ loại subtype.

**Ghi nhớ:** `Object.getClass()` là **`public final native`**, luôn trả metadata của **lớp runtime thực tế** đối với một đối tượng khác null. Không lớp nào được override nó. Hãy dùng `getClass()` khi cần exact type, `instanceof` khi cần quan hệ kiểu, và `equals()` khi cần so ngữ nghĩa giá trị.