# So sánh chính xác lớp và kiểm tra khả năng là kiểu con trong Java

## 1. Hai câu hỏi khác nhau về kiểu đối tượng

Trong Java, **lớp thực tế** (*runtime class*) của một đối tượng là lớp của đối tượng được tạo tại thời điểm chạy, không nhất thiết là kiểu khai báo của biến đang tham chiếu đến nó. Phân biệt hai yêu cầu thường gặp:

1. **Chính xác lớp này?** Đối tượng có đúng lớp runtime `SomeClass`, không chấp nhận lớp con? Dùng `obj.getClass() == SomeClass.class` sau khi bảo đảm `obj != null`.
2. **Là một đối tượng thuộc kiểu này hoặc kiểu con?** Đối tượng có thể được coi là một `SomeClass` theo quan hệ kế thừa/triển khai interface? Dùng `obj instanceof SomeClass`.

Ví dụ:

```java
class Animal {}
class Dog extends Animal {}
class Poodle extends Dog {}

Animal pet = new Poodle();

System.out.println(pet instanceof Animal);       // true
System.out.println(pet instanceof Dog);          // true
System.out.println(pet.getClass() == Animal.class); // false
System.out.println(pet.getClass() == Poodle.class); // true
```

Đây là **đoạn minh họa các khai báo/lệnh**; chương trình có thể biên dịch/chạy độc lập được cung cấp ở mục 5. Biến `pet` được khai báo là `Animal` nhưng đối tượng thực tế là `Poodle`. Vì vậy cùng một tham chiếu có thể thỏa kiểm tra “là một `Animal`” trong khi không có lớp runtime đúng bằng `Animal.class`.

| Biểu thức | Câu hỏi | `new Poodle()` trong hệ `Animal → Dog → Poodle` |
| --- | --- | --- |
| `obj instanceof Animal` | Đối tượng có tương thích với `Animal`? | `true` |
| `obj instanceof Dog` | Đối tượng có tương thích với `Dog`? | `true` |
| `obj instanceof Poodle` | Đối tượng có tương thích với `Poodle`? | `true` |
| `obj.getClass() == Animal.class` | Lớp runtime có đúng `Animal`? | `false` |
| `obj.getClass() == Poodle.class` | Lớp runtime có đúng `Poodle`? | `true` |
| `Animal.class.isInstance(obj)` | Kiểm tra runtime tương tự `instanceof Animal`? | `true` |
| `Animal.class.isAssignableFrom(Poodle.class)` | Có thể gán đối tượng kiểu `Poodle` vào tham chiếu `Animal`? | `true` |

Đây là hai **chính sách về kiểu** khác nhau, không phải hai cú pháp tương đương có thể tùy ý thay thế.

## 2. `getClass() == SomeClass.class`: so sánh lớp chính xác

Mỗi đối tượng Java thừa hưởng phương thức `public final Class<?> getClass()` từ `Object`. Nó trả về một đối tượng `Class` biểu diễn **kiểu runtime**. Để kiểm tra chính xác lớp:

```java
if (obj != null && obj.getClass() == Animal.class) {
    // Chỉ đối tượng có lớp thực tế đúng Animal.
}
```

Đây là **đoạn lệnh nằm trong phương thức đã có biến `obj`**. Kiểm tra `obj != null` rất quan trọng: `obj.getClass()` ném `NullPointerException` khi `obj == null`. So với đó, `null instanceof Animal` luôn là `false` (với vế trái là tham chiếu null).

### Vì sao dùng `==` giữa các đối tượng `Class`?

Trong cùng một lớp được nạp, đối tượng `Class` đại diện cho kiểu runtime là duy nhất, nên so bằng `==` là thích hợp để kiểm tra **cùng một lớp runtime**. Không cần so tên lớp bằng chuỗi:

```java
obj.getClass().getName().equals("com.example.Animal")
```

Đoạn trên là **cách so tên mang tính minh họa**, không phải cách kiểm tra lớp chính xác được khuyến nghị. Hai lớp do hai class loader khác nhau nạp có thể có cùng tên nhị phân nhưng vẫn là hai kiểu runtime khác nhau. `getClass() == Animal.class` phản ánh đúng sự phân biệt này.

### Khi nào kiểm tra chính xác hữu ích?

- Trong định nghĩa bình đẳng theo **kiểu giá trị**, nếu một đối tượng của lớp con không được phép bằng đối tượng lớp cha dù các trường chung trùng nhau.
- Khi phân nhánh xử lý yêu cầu **đúng lớp hiện tại**, không chấp nhận bất kỳ subtype nào.
- Khi kiểm tra bất biến của một mô hình mà loại giá trị phải chính xác, ví dụ một số cách so sánh dữ liệu không có chính sách tương đương xuyên kiểu.

**Giới hạn:** kiểm tra bằng `getClass` loại trừ toàn bộ subclass, kể cả subclass không bổ sung trạng thái. Nếu hệ thống dùng proxy sinh lớp con ở runtime hoặc framework dựa trên subclass, kiểm tra kiểu chính xác có thể không phù hợp với yêu cầu nghiệp vụ. Không nên áp dụng cơ học chỉ vì thấy `instanceof` “quá rộng”.

## 3. `instanceof`: kiểm tra tương thích với kiểu đích

Toán tử `instanceof` trả về `true` nếu một tham chiếu không null trỏ tới đối tượng có thể chuyển đổi kiểm tra kiểu (*casting conversion*) thích hợp sang kiểu đích theo luật Java. Với lớp và interface thường gặp, điều đó bao gồm **đúng lớp** và **kiểu con**; với interface, nó bao gồm đối tượng thuộc lớp triển khai interface.

```java
Object value = "hello";
System.out.println(value instanceof String);       // true
System.out.println(value instanceof CharSequence); // true
System.out.println(value instanceof Object);       // true
```

Đây là **đoạn minh họa chạy trong phương thức**; `String` thực hiện `CharSequence` và cũng là `Object`. Cách kiểm tra này phù hợp khi mã cần sử dụng một **khả năng được biểu diễn bởi kiểu cha hoặc interface**, mà không cần biết lớp triển khai cụ thể.

Từ Java 16 trở đi, `instanceof` hỗ trợ **pattern matching**:

```java
if (value instanceof String text) {
    System.out.println(text.length());
}
```

Đây là **đoạn lệnh nằm trong phương thức đã có biến `value`**. Biến mẫu `text` chỉ khả dụng khi việc kiểm tra phù hợp với phạm vi đã được trình biên dịch xác định; Java thực hiện kiểm tra rồi cung cấp biến kiểu `String` không cần ép kiểu tường minh.

Tuy nhiên, **một kiểm tra `instanceof` không chứng minh tất cả đối tượng thuộc lớp cha có thể ép thành lớp con**. `obj instanceof Dog` đúng thì mới được dùng như `Dog`, còn việc `obj instanceof Animal` đúng không chứng minh nó là `Dog`.

### Liên hệ với `Class.isInstance` và `Class.isAssignableFrom`

Khi kiểu đích được biết trước ở thời điểm viết mã, `instanceof Animal` là cách trực tiếp nhất. Khi kiểu đích nằm trong một biến `Class<?>` (ví dụ được truyền từ cấu hình hoặc một API reflection), có thể dùng:

```java
Class<?> target = Animal.class;
boolean supported = target.isInstance(obj);
```

Đây là **đoạn lệnh trong phương thức**; `Class.isInstance(obj)` nhận một **đối tượng hoặc null** và trả về boolean. Nó không yêu cầu gọi phương thức trên `obj`, vì vậy `target.isInstance(null)` là `false` thay vì ném `NullPointerException`.

Với `Class.isAssignableFrom(otherClass)`, hai bên đều là **đối tượng `Class`**:

```java
boolean animalFromDog = Animal.class.isAssignableFrom(Dog.class); // true
boolean dogFromAnimal = Dog.class.isAssignableFrom(Animal.class); // false
```

Đây là **đoạn lệnh minh họa** dùng khai báo `Animal` và `Dog` ở trên. Chiều của phép kiểm tra rất quan trọng: `A.class.isAssignableFrom(B.class)` hỏi liệu một giá trị kiểu `B` có thể được gán vào nơi cần `A` hay không, không phải chiều ngược lại. Nó hữu ích trong reflection, generic container và framework, khi ta cần kiểm tra tương thích kiểu **trước khi có instance**.

## 4. Hệ quả đặc biệt với hợp đồng `equals()`

Trong module **object-contract**, khác biệt giữa `getClass` và `instanceof` đặc biệt quan trọng ở **`Object.equals(Object)`**. Một phương thức `equals` hợp lệ phải có tính phản xạ, đối xứng, bắc cầu, nhất quán và trả về `false` khi so với `null`.

### 4.1. Dùng `instanceof` có thể khiến lớp cha chấp nhận lớp con

Giả sử lớp `Point` có `x` và `y`, còn `ColoredPoint extends Point` thêm trường `color`. Nếu `Point.equals` dùng:

```java
if (!(other instanceof Point p)) return false;
return x == p.x && y == p.y;
```

Đây là **phần thân minh họa** của `equals` trong lớp `Point`. Phương thức của lớp cha chấp nhận cả `ColoredPoint` vì lớp con cũng là một `Point`. Nhưng nếu `ColoredPoint.equals` kiểm tra thêm màu và không chấp nhận `Point` thuần, có thể xảy ra:

```text
point.equals(coloredPoint)  -> true
coloredPoint.equals(point)  -> false
```

Khi hai phía trả khác nhau, **tính đối xứng bị phá vỡ**. Lỗi không do bản thân `instanceof` sai, mà do **hai lớp định nghĩa quan hệ bằng nhau không tương thích**. Chỉ đổi `instanceof` trong một phương thức mà không kiểm tra toàn hệ phân cấp chưa đủ bảo đảm hợp đồng.

### 4.2. Dùng `getClass` để thống nhất chính sách “chỉ cùng lớp”

Nếu đối tượng của hai lớp runtime khác nhau **không bao giờ nên bằng nhau**, `Point.equals` có thể kiểm tra:

```java
@Override
public boolean equals(Object other) {
    if (this == other) return true;
    if (other == null || getClass() != other.getClass()) return false;
    Point that = (Point) other;
    return x == that.x && y == that.y;
}
```

Đây là **phương thức thuộc lớp `Point`**, giả sử các trường `x`, `y` đã khai báo; không phải chương trình độc lập. Khi một `Point` thuần so với một `ColoredPoint`, kiểm tra lớp runtime không khớp ở cả hai hướng và hai phương thức có thể cùng trả `false`.

Ở phía lớp con, cần xây dựng `equals` và `hashCode` tương thích với phần dữ liệu kế thừa lẫn phần dữ liệu mới. Ví dụ tại mục 5 thể hiện đầy đủ, có thể chạy được.

**Lưu ý quan trọng:** `getClass` trong lớp cha không tự khiến mọi override `equals` ở lớp con tuân thủ hợp đồng. Một lớp con có thể viết mã sai, hoặc dùng quan hệ bằng nhau không đối xứng trong phần triển khai của nó. `getClass` chỉ giúp thiết lập chính sách chính xác về kiểu khi các lớp đều tuân thủ.

### 4.3. Dùng `instanceof` vẫn có thể đúng khi mô hình phù hợp

Với một **lớp `final`** không có lớp con, kiểm tra `other instanceof FinalValue` và kiểm tra lớp chính xác thường dẫn đến cùng miền đối tượng hợp lệ. Một hệ phân cấp cũng có thể dùng `instanceof` nếu **mọi lớp liên quan chia sẻ một định nghĩa bình đẳng ổn định**, không có lớp con âm thầm bổ sung tiêu chí khiến quan hệ bị lệch.

Nếu thật sự cần một số lớp con được phép bằng lớp cha, có thể dùng thiết kế hợp tác như `canEqual` hoặc một mô hình danh tính chung; vẫn phải kiểm tra cả đối xứng, bắc cầu, `hashCode` và các giá trị biên. `getClass` không phải “nâng cấp” mặc định của `instanceof` trong mọi bài toán.

## 5. Chương trình Java 17+ đầy đủ: so kiểu và kiểm chứng `equals`

Lưu chương trình sau thành **`RuntimeClassDemo.java`**. Phần đầu minh họa kiểu runtime với ba lớp kế thừa. Phần sau dùng `getClass` trong `Point.equals` và triển khai `ColoredPoint` để kiểm tra bình đẳng giữa cha/con theo cả hai chiều.

```java
import java.util.Objects;

public class RuntimeClassDemo {
    static class Animal {}
    static class Dog extends Animal {}
    static final class Poodle extends Dog {}

    static class Point {
        private final int x, y;

        Point(int x, int y) {
            this.x = x;
            this.y = y;
        }

        @Override
        public boolean equals(Object other) {
            if (this == other) return true;
            if (other == null || getClass() != other.getClass()) {
                return false;
            }
            Point that = (Point) other;
            return x == that.x && y == that.y;
        }

        @Override
        public int hashCode() {
            return Objects.hash(x, y);
        }
    }

    static final class ColoredPoint extends Point {
        private final String color;

        ColoredPoint(int x, int y, String color) {
            super(x, y);
            this.color = Objects.requireNonNull(color);
        }

        @Override
        public boolean equals(Object other) {
            if (this == other) return true;
            if (!super.equals(other)) return false;
            ColoredPoint that = (ColoredPoint) other;
            return color.equals(that.color);
        }

        @Override
        public int hashCode() {
            return 31 * super.hashCode() + color.hashCode();
        }
    }

    public static void main(String[] args) {
        Object poodle = new Poodle();
        System.out.println("instanceof Animal = "
                + (poodle instanceof Animal));
        System.out.println("instanceof Dog = "
                + (poodle instanceof Dog));
        System.out.println("exact Animal class = "
                + (poodle.getClass() == Animal.class));
        System.out.println("exact Poodle class = "
                + (poodle.getClass() == Poodle.class));
        System.out.println("Animal isInstance = "
                + Animal.class.isInstance(poodle));
        System.out.println("Animal assignable from Poodle = "
                + Animal.class.isAssignableFrom(Poodle.class));
        System.out.println("Poodle assignable from Animal = "
                + Poodle.class.isAssignableFrom(Animal.class));
        Object missing = null;
        System.out.println("null instanceof Animal = "
                + (missing instanceof Animal));

        Point base = new Point(2, 3);
        ColoredPoint red = new ColoredPoint(2, 3, "red");
        ColoredPoint copy = new ColoredPoint(2, 3, "red");
        System.out.println("base.equals(red) = " + base.equals(red));
        System.out.println("red.equals(base) = " + red.equals(base));
        System.out.println("red.equals(copy) = " + red.equals(copy));
        System.out.println("equal colored hash = "
                + (red.hashCode() == copy.hashCode()));
    }
}
```

Chạy trong thư mục chứa tệp bằng JDK 17 trở lên:

```bash
javac RuntimeClassDemo.java
java RuntimeClassDemo
```

Kết quả:

```text
instanceof Animal = true
instanceof Dog = true
exact Animal class = false
exact Poodle class = true
Animal isInstance = true
Animal assignable from Poodle = true
Poodle assignable from Animal = false
null instanceof Animal = false
base.equals(red) = false
red.equals(base) = false
red.equals(copy) = true
equal colored hash = true
```

**Giải thích đầu ra:**

1. Đối tượng `Poodle` cũng là `Dog` và `Animal`, nên hai kiểm tra `instanceof` đầu tiên đều đúng. Nhưng lớp runtime của đối tượng là **`Poodle`**, không phải `Animal`.
2. `Animal.class.isInstance(poodle)` cũng `true`: đây là cách kiểm tra ở runtime khi thông tin kiểu nằm trong một đối tượng `Class`. `isAssignableFrom` cho biết hướng kế thừa `Poodle → Animal` là hướng gán hợp lệ; hướng `Animal → Poodle` thì không.
3. Một tham chiếu `null` cho kết quả `false` khi dùng `instanceof`. Nếu dùng `missing.getClass()` mà không kiểm tra null sẽ ném `NullPointerException`.
4. `base.equals(red)` là `false` vì lớp runtime `Point` khác `ColoredPoint`. Chiều ngược lại cũng `false`, vì `super.equals(other)` phát hiện lớp khác.
5. Hai `ColoredPoint` độc lập nhưng có cùng tọa độ và màu trả `true`. Cả hai tạo hash theo phần điểm kế thừa và màu nên các đối tượng bằng nhau cũng có cùng hash.

Không nên suy rộng rằng bất kỳ hai đối tượng cùng lớp nào cũng bằng nhau. `getClass` chỉ giải quyết câu hỏi **kiểu có tương thích theo chính sách đang chọn không**, còn nội dung thuộc tính vẫn phải so đúng trong `equals`.

## 6. Khi nào nên dùng loại kiểm tra nào?

| Tình huống | Lựa chọn phù hợp | Lý do |
| --- | --- | --- |
| Xử lý mọi đối tượng triển khai một interface | `instanceof InterfaceType` | Chấp nhận các implementation khác nhau |
| Nhận một đối tượng thuộc lớp cơ sở hoặc bất kỳ lớp con | `instanceof BaseType` | Hỗ trợ đa hình |
| Chỉ xử lý đúng lớp runtime `FinalMessage` hoặc `ExactEvent` | `getClass() == ExactEvent.class` | Không nhận lớp con |
| Lớp giá trị muốn `equals` chỉ có thể `true` giữa cùng lớp runtime | `getClass()` trong `equals` cùng kiểm tra thuộc tính | Xác lập chính sách bình đẳng chính xác về kiểu |
| Kiểu được chọn động bằng `Class<?> target` | `target.isInstance(obj)` | Kiểm tra tương thích với instance khi kiểu là dữ liệu runtime |
| Cần xác định liệu hai kiểu có thể gán theo một hướng | `Target.class.isAssignableFrom(Source.class)` | Là câu hỏi về **kiểu**, không cần instance |
| Cần ép kiểu an toàn và khai báo biến mới | `obj instanceof Target t` | Vừa kiểm tra vừa ràng buộc biến pattern trong phạm vi phù hợp |
| Đối tượng do framework tạo proxy kế thừa runtime | Cần thiết kế chính sách domain trước | `getClass` sẽ thấy lớp proxy thay vì luôn thấy lớp mô hình gốc |

### Hai điểm dễ sai với reflection

- `A.class.isAssignableFrom(B.class)` hướng từ **kiểu đích** `A` tới **kiểu nguồn** `B`. Viết đảo sẽ trả kết quả khác; trong quan hệ cha/con, chỉ một hướng có thể gán an toàn.
- `Class.isInstance` không phải `getClass()==...`. `Animal.class.isInstance(new Poodle())` là `true` dù hai đối tượng `Class` `Animal.class` và `Poodle.class` không đồng nhất.

Một biến kiểu `Object` có thể trỏ tới đối tượng mang kiểu runtime bất kỳ. Vì vậy muốn biết đối tượng **hỗ trợ hành vi** nào, thường dùng interface và `instanceof`/đa hình; muốn ràng buộc chính xác **danh tính lớp runtime**, dùng `getClass` hoặc so đối tượng `Class`.

## 7. Trường hợp biên và giới hạn của hai phương pháp

### 7.1. `null`

`obj instanceof SomeType` là `false` nếu `obj == null`. `SomeType.class.isInstance(null)` cũng trả `false`. Trong khi đó `obj.getClass()` ném `NullPointerException`; phép kiểm tra lớp chính xác cần đi sau điều kiện null. Khi viết `equals`, thường bắt đầu bằng:

```java
if (this == other) return true;
if (other == null || getClass() != other.getClass()) return false;
```

Đây là **đoạn logic trong phương thức `equals`**, không phải chương trình độc lập. Nó vừa xử lý so cùng tham chiếu, vừa tránh gọi `getClass` trên đối tượng null.

### 7.2. Interface, abstract class và kiểu đa hình

Một đối tượng triển khai interface `Runnable` có thể thỏa `obj instanceof Runnable`. Nhưng `obj.getClass() == Runnable.class` luôn sai đối với một instance thông thường, vì interface không phải một lớp có thể tạo đối tượng trực tiếp. Tương tự, một instance lớp con có thể thỏa `obj instanceof AbstractBase`, trong khi lớp runtime không thể bằng đúng lớp abstract không thể khởi tạo.

Điều này làm rõ khác biệt: **“thuộc một kiểu” không có nghĩa “lớp runtime trùng chính xác kiểu ấy”**.

### 7.3. Mảng

Mảng `String[]` thỏa `instanceof Object[]` vì các phần tử đều là tham chiếu, nhưng lớp runtime của nó không bằng `Object[].class`; nó bằng `String[].class`. Mảng `int[]` lại **không** là `Object[]` vì phần tử là kiểu nguyên thủy; tuy vậy chính mảng `int[]` vẫn là một `Object`. Các loại mảng khác nhau có lớp runtime khác nhau, và có thể phân biệt bằng `getClass` khi thực sự cần chính xác kiểu mảng.

### 7.4. Proxy và lớp sinh động

Một số framework tạo proxy bằng cách tạo subclass của lớp miền. Khi đó `getClass() == DomainType.class` có thể là `false` dù proxy được thiết kế để đóng vai một `DomainType` trong ứng dụng. Ngược lại, `proxy instanceof DomainType` có thể là `true` trong trường hợp proxy kế thừa `DomainType`.

**Không phải proxy nào cũng là subclass của lớp miền**: proxy dựa trên interface có quan hệ kiểu theo interface thay vì chắc chắn kế thừa lớp cụ thể. Các ORM và framework còn có chính sách riêng về identity, lazy loading và `equals`. Hãy xác định quy tắc identity ở mức miền hoặc theo hướng dẫn framework thay vì tự động chọn `getClass` hay `instanceof` từ một ví dụ đơn giản.

### 7.5. Lớp con mới có thể phá hợp đồng `equals`

Ngay cả khi lớp cha dùng `getClass` đúng, một lớp con triển khai `equals` không đối xứng hoặc quên `hashCode` vẫn có thể làm hỏng hợp đồng. Trong mô hình giá trị, dùng `final class` hoặc `record` (mặc định final) thường giảm rủi ro do subclass thay đổi tiêu chí bình đẳng. Nếu cần kế thừa, phải kiểm tra toàn bộ quan hệ giữa các lớp thực tế có thể xuất hiện.

## 8. Lỗi phổ biến và cách tự kiểm tra

| Lỗi | Nguyên nhân | Cách sửa |
| --- | --- | --- |
| Tưởng `obj instanceof Base` chỉ nhận đúng `Base` | Không tính đến subtype | Dùng `getClass() == Base.class` khi muốn lớp runtime chính xác |
| Tưởng `obj.getClass() == Base.class` chấp nhận lớp con | `Class` bình đẳng chính xác, không theo kế thừa | Dùng `instanceof Base` hoặc `Base.class.isInstance(obj)` |
| Gọi `getClass()` trên null | Dereference null | Kiểm tra `obj != null` trước |
| Đảo chiều `isAssignableFrom` | Nhầm lớp nguồn và lớp đích | Nhớ `Target.class.isAssignableFrom(Source.class)` |
| Lớp cha dùng `instanceof` nhưng lớp con thêm tiêu chí bình đẳng riêng | `equals` có thể không đối xứng hoặc không bắc cầu | Thiết kế thống nhất quan hệ equality xuyên phân cấp |
| Thay `instanceof` bằng `getClass` khắp nơi không xét domain | Loại trừ mọi subclass/proxy | Xác định cần tương thích kiểu hay cần lớp chính xác |
| So tên lớp bằng chuỗi thay vì đối tượng `Class` | Class loader có thể tạo kiểu khác cùng tên | So `Class` trực tiếp nếu cần kiểm tra type identity |
| Kiểm tra `instanceof` rồi vẫn ép kiểu sai | Kiểm tra một kiểu nhưng ép sang một kiểu con khác | Dùng pattern variable đúng kiểu đã kiểm tra |
| Chỉ kiểm tra kiểu trong `equals`, quên giá trị và `hashCode` | Hợp đồng bình đẳng không hoàn chỉnh | So các thuộc tính quyết định equality, sinh hash tương thích |

### Câu hỏi tự kiểm tra

**1.** `Animal pet = new Poodle();`. `pet.getClass() == Animal.class` có đúng không? Còn `pet instanceof Animal`?

Kết quả lần lượt là `false` và `true`. Kiểu khai báo của biến không thay đổi lớp runtime của đối tượng.

**2.** `Class<?> target = Animal.class`. Dùng `target.isInstance(new Poodle())` có khác ý nghĩa với `new Poodle().getClass() == Animal.class` không?

Có. Biểu thức đầu kiểm tra quan hệ tương thích kiểu và cho `true`; biểu thức sau kiểm tra chính xác lớp runtime và cho `false`.

**3.** Trong hệ `Point`, `ColoredPoint` có thêm màu quyết định identity. Nếu lớp cha dùng `instanceof Point` để coi lớp con bằng mình theo tọa độ, còn lớp con từ chối lớp cha, tính chất nào bị vi phạm?

Tính **đối xứng** của `equals`. Hai chiều cho hai kết quả khác nhau. Một giải pháp là chính sách lớp runtime chính xác ở cả hai phía, miễn là nó phù hợp miền nghiệp vụ.

**4.** `Runnable.class.isAssignableFrom(MyTask.class)` đúng có nghĩa là gì?

Nếu `MyTask` triển khai `Runnable`, thì một đối tượng `MyTask` có thể được dùng ở nơi cần `Runnable`. Nó không khẳng định lớp runtime của đối tượng bằng chính xác `Runnable.class`.

**Ghi nhớ:** `instanceof` trả lời “đối tượng **có thể được coi là** kiểu này không?”, còn `getClass() == SomeType.class` trả lời “đối tượng có **chính xác lớp runtime** này không?”. Với `equals` và các hợp đồng đối tượng, lựa chọn phụ thuộc cách ứng dụng định nghĩa bình đẳng xuyên hệ phân cấp; sau kiểm tra kiểu vẫn phải so giá trị và bảo đảm `hashCode` tương thích.