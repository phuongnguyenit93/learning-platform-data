# Giới hạn tham chiếu đến tham số kiểu khác trong Java Generics

## 1. Bài toán và mục tiêu

Trong Java, một tham số kiểu generic có thể bị giới hạn (*bounded type parameter*) bởi một lớp hoặc interface cụ thể, ví dụ `<T extends Number>`. Nhưng nhiều thuật toán cần diễn tả **quan hệ giữa hai hoặc nhiều tham số kiểu**, chứ không chỉ giới hạn từng tham số riêng rẽ:

```java
// Mảnh minh họa đặt trong một lớp Java.
static <Super, Sub extends Super> Super choose(
        boolean useSub, Super first, Sub second) {
    return useSub ? second : first;
}
```

Ở đây `Sub extends Super` nói rằng **kiểu đối số `Sub` phải là subtype của kiểu đối số `Super`**. Hai tên `Super` và `Sub` đều là tham số kiểu của cùng phương thức. Với `Super = Number`, `Sub = Integer`, compiler chứng minh rằng một `Integer` có thể dùng ở nơi yêu cầu `Number`. Nếu cố chọn `Super = String` và `Sub = Integer`, ràng buộc sẽ không hợp lệ.

Một ví dụ khác:

```java
static <T extends Comparable<? super T>> T maximum(
        java.util.Collection<? extends T> source) {
    // Triển khai đầy đủ ở phần sau.
    throw new UnsupportedOperationException();
}
```

`T` trong `Comparable<? super T>` được dùng **ngay trong giới hạn của chính `T`**. Đây là một ví dụ của giới hạn tự tham chiếu (*recursive/F-bound*), đồng thời kết hợp wildcard để cho phép một kiểu được so sánh theo giao diện do chính nó hoặc kiểu cha hỗ trợ.

Sau bài học, bạn cần có thể:

- Đọc và viết `<A, B extends A>`, `<T extends Comparable<T>>` và `<T extends Comparable<? super T>>`.
- Xác định chính xác **tham số nào là nguồn ràng buộc**, tham số nào bị giới hạn và quan hệ subtype cần chứng minh.
- Hiểu tham chiếu tới một tham số kiểu khác trong **lớp generic, phương thức generic, constructor generic và bound tự tham chiếu**.
- Phân biệt `extends` trong **khai báo type parameter** với wildcard `? extends ...`/`? super ...`.
- Biết khi nào type inference đủ thông tin, khi nào nên dùng type witness hoặc khai báo kiểu đích rõ ràng.
- Tránh nhầm quan hệ subtype với covariance của `List<T>` và tránh raw type/unchecked cast để lách lỗi giới hạn.

Bài viết dành cho Java **17+**, bao gồm các mảnh minh họa và một tệp `DependentBoundsDemo.java` hoàn chỉnh đã được biên dịch, chạy thử.

## 2. Cú pháp nền tảng: bound của một tham số kiểu

Giới hạn đơn giản thường viết:

```java
class NumericBox<T extends Number> {
    private final T value;

    NumericBox(T value) {
        this.value = value;
    }

    double asDouble() {
        return value.doubleValue();
    }
}
```

`T extends Number` nghĩa là đối số kiểu thực tế của `T` phải là `Number` hoặc subtype của `Number`. Vì vậy `NumericBox<Integer>` và `NumericBox<Double>` hợp lệ, còn `NumericBox<String>` không hợp lệ.

Dù `Number` là lớp hay giới hạn là một interface như `Comparable<T>`, Java đều dùng **từ khóa `extends`** trong danh sách khai báo type parameter. Không viết `<T implements Interface>`.

Một tham số kiểu có thể có **nhiều bound**:

```java
// Mảnh khai báo trong lớp hoặc phương thức Java.
static <T extends Number & Comparable<T>> boolean greater(T a, T b) {
    return a.compareTo(b) > 0;
}
```

Bound lớp (nếu có) phải đứng đầu, các interface đứng sau dấu `&`. Ví dụ `Integer` vừa là `Number` vừa thực hiện `Comparable<Integer>`, nên đáp ứng bound này. Không được ghép nhiều class bound: Java không hỗ trợ kế thừa nhiều lớp.

Khi bound tham chiếu đến **tham số kiểu khác** thay vì tên một class/interface cụ thể, nguyên tắc vẫn là kiểm tra quan hệ subtype ngay từ lúc biên dịch.

## 3. Hai tham số kiểu phụ thuộc nhau: `<Super, Sub extends Super>`

Ví dụ lớp generic:

```java
class Pair<Super, Sub extends Super> {
    private final Super first;
    private final Sub second;

    Pair(Super first, Sub second) {
        this.first = first;
        this.second = second;
    }

    Super first() {
        return first;
    }

    Sub second() {
        return second;
    }
}
```

`Pair<Number, Integer>` hợp lệ vì `Integer` là subtype của `Number`. `Pair<CharSequence, String>` hợp lệ vì `String` thực hiện `CharSequence`. Nhưng `Pair<String, Integer>` không hợp lệ vì `Integer` không phải subtype của `String`.

```java
// Các câu lệnh có thể đặt trong một phương thức Java.
Pair<Number, Integer> numbers = new Pair<>(3.5, 7);
Number a = numbers.first();
Integer b = numbers.second();

Pair<CharSequence, String> names = new Pair<>("base", "child");
// Pair<String, Integer> wrong = new Pair<>("text", 1); // Lỗi bound.
```

**Phân tích từng vị trí:**

| Thành phần | Ý nghĩa |
| --- | --- |
| `Super` | Tham số kiểu độc lập, chưa có bound riêng ngoài `Object` mặc định. |
| `Sub extends Super` | `Sub` phải là subtype của `Super` được chọn ở cùng lần tham số hóa. |
| `Super first` | Trường chấp nhận giá trị theo hợp đồng của `Super`. |
| `Sub second` | Trường giữ kiểu cụ thể hơn theo hợp đồng `Sub`. |
| `Super first()` | Kết quả người gọi nhận là `Super`. |
| `Sub second()` | Kết quả người gọi nhận là `Sub`; không phải ép từ `Object`. |

Quan hệ `Sub extends Super` chỉ ràng buộc **kiểu**, không khẳng định hai đối tượng trong các trường `first` và `second` có cùng giá trị. Nó cũng không yêu cầu `Sub` là **subclass trực tiếp**: một subtype qua nhiều cấp, interface implementation, hoặc cùng kiểu được chọn cho cả hai tham số cũng hợp lệ nếu các bound đáp ứng.

### Tham số kiểu bằng chính kiểu kia vẫn hợp lệ

```java
Pair<String, String> same = new Pair<>("A", "B");
```

`String` là subtype của chính nó theo quan hệ subtype phản xạ; `extends` trong bound không bắt buộc phải là một lớp con *khác* lớp cha.

## 4. Bound phụ thuộc trong phương thức generic

Không cần tạo lớp generic mới để sử dụng quan hệ `Sub extends Super`. Một phương thức thường được khai báo bên trong lớp tiện ích có thể tự sở hữu hai tham số kiểu:

```java
final class Selection {
    private Selection() {}

    static <Super, Sub extends Super> Super choose(
            boolean chooseSub, Super normal, Sub specialized) {
        return chooseSub ? specialized : normal;
    }
}
```

Phương thức chỉ cần biết giá trị `specialized` có thể dùng an toàn như một `Super`. Ví dụ:

```java
Number result =
        Selection.<Number, Integer>choose(true, 1.5, 9); // 9
```

Hai type arguments `Number` và `Integer` nằm giữa `<...>` của lời gọi phương thức: `Selection.<Number, Integer>choose(...)`. Đây gọi là **explicit type witness**, hữu ích khi muốn nhìn rõ quan hệ. Trong nhiều lời gọi, compiler có thể suy luận kiểu và người lập trình chỉ viết `Selection.choose(...)`.

Lưu ý quan trọng: Java thường có nhiều cách chọn kiểu chung hợp lệ. Nếu không chỉ định type arguments, compiler có thể suy luận một kiểu cha/giao diện rộng hơn ý muốn dựa trên các đối số và ngữ cảnh. **Đừng tự mặc định compiler luôn chọn `Number`** chỉ vì người viết đang làm việc với số. Khi chữ ký phụ thuộc nhau hoặc lỗi suy luận khó hiểu, hãy đặt kiểu đích rõ ràng hay dùng type witness như trên.

### Bound giúp gì cho thân phương thức?

Với `<Super, Sub extends Super>`, compiler cho phép:

```java
static <Super, Sub extends Super> Super promote(Sub value) {
    Super upcast = value; // Hợp lệ: Sub extends Super.
    return upcast;
}
```

Ngược lại, chiều từ `Super` sang `Sub` không được bảo đảm:

```java
// Không hợp lệ:
// static <Super, Sub extends Super> Sub downcast(Super value) {
//     return value; // Super không nhất thiết là Sub.
// }
```

Đây chính là giá trị của bound: trình biên dịch cho phép chiều chuyển kiểu được chứng minh, từ chối chiều không có bảo đảm, không cần chờ `ClassCastException` lúc chạy.

## 5. Tham chiếu đến type parameter khai báo phía sau

Java cho phép một type parameter tham chiếu đến type parameter khác nằm **phía sau** trong cùng danh sách khai báo:

```java
class Forward<Sub extends Super, Super> {
    private final Sub value;

    Forward(Sub value) {
        this.value = value;
    }

    Super readAsSuper() {
        return value;
    }
}

// Forward<Integer, Number> f = new Forward<>(7);
// Number n = f.readAsSuper();
```

`Super` vẫn thuộc cùng danh sách type parameter của `Forward`, nên bound `Sub extends Super` hợp lệ. Tương tự, phương thức generic cũng có thể viết:

```java
static <Sub extends Super, Super> Super up(Sub value) {
    return value;
}
```

Cú pháp này **được Java hỗ trợ**, nhưng cách viết `<Super, Sub extends Super>` thường **dễ đọc hơn** vì khai báo kiểu cơ sở trước rồi mới khai báo kiểu phụ thuộc. Cách bố trí thuận mắt giúp người mới nhanh nhận ra chiều của ràng buộc.

Việc cho phép forward reference không đồng nghĩa Java cho phép mọi kiểu bound vòng tròn. Một số tổ hợp bounds bất hợp lệ do luật vòng lặp hoặc do không thỏa điều kiện generic, và một số dạng F-bound hợp lệ được diễn giải ở mục 9. Hãy để compiler kiểm tra từng khai báo thay vì giả định mọi chu trình tham chiếu đều được cho phép.

## 6. Bound qua interface: một tham số kiểu dùng API do tham số khác mô tả

Một bound có thể sử dụng một interface generic mang tham số kiểu khác. Ví dụ:

```java
import java.util.function.Function;

final class Converter<Source, Target> {
    private final Function<? super Source, ? extends Target> function;

    Converter(Function<? super Source, ? extends Target> function) {
        this.function = function;
    }

    Target convert(Source value) {
        return function.apply(value);
    }
}
```

`Converter<Source, Target>` liên kết nguồn và đích bằng một generic functional interface, nhưng **chưa đặt bound subtype giữa hai tham số**. Đây là hợp đồng chuyển đổi, không phải `Target extends Source`. Hai loại quan hệ phải được phân biệt:

1. **Quan hệ subtype**: `<Parent, Child extends Parent>` khẳng định mọi giá trị `Child` có thể dùng như `Parent`.
2. **Quan hệ hàm biến đổi**: `Function<? super Source, ? extends Target>` khẳng định có một thao tác chuyển nguồn thành kết quả, dù `Source` và `Target` không có quan hệ kế thừa nào.

Nếu một kiểu cần hỗ trợ so sánh với một kiểu khác, bound có thể tham chiếu đến generic interface:

```java
// Mảnh chữ ký minh họa trong một lớp Java:
static <Other, T extends Comparable<Other>> int compare(
        T left, Other right) {
    return left.compareTo(right);
}
```

`T extends Comparable<Other>` bảo đảm `left.compareTo(right)` hợp lệ, do `left` có khả năng so sánh với `Other`. Không nhất thiết `T` phải cùng kiểu với `Other`. Khi chọn tham số, phải có implementation thật sự đáp ứng `Comparable<Other>`.

### Khác với sử dụng nhiều kiểu trong một phương thức

```java
static <A, B> String describe(A a, B b) {
    return String.valueOf(a) + "/" + String.valueOf(b);
}
```

Phương thức này chỉ khai báo hai tham số kiểu độc lập; **không có bound tham chiếu chéo**. Không phải mọi method dùng nhiều type parameters đều là phương thức có dependent bounds.

## 7. Recursive bound — tham số kiểu tự tham chiếu

Một kiểu giới hạn có thể đề cập đến chính tham số đang được khai báo:

```java
class OrderedBox<T extends Comparable<T>> {
    private final T value;

    OrderedBox(T value) {
        this.value = value;
    }

    boolean isLessThan(T other) {
        return value.compareTo(other) < 0;
    }
}
```

Ở đây `T` phải là một kiểu thực hiện `Comparable<T>`. Ví dụ `String implements Comparable<String>` và `Integer implements Comparable<Integer>`, nên `OrderedBox<String>` và `OrderedBox<Integer>` đáp ứng bound.

Mẫu `<T extends Comparable<T>>` còn được gọi là **F-bounded polymorphism** trong ngữ cảnh một kiểu được ràng buộc bởi một cấu trúc generic chứa chính nó. Một mục đích thường gặp là mô hình hóa khả năng "so sánh với cùng kiểu".

```java
OrderedBox<String> text = new OrderedBox<>("A");
boolean result = text.isLessThan("B"); // true.
```

Không nhầm bound này với cú pháp tự kế thừa trực tiếp:

```java
// Sai: một lớp không thể extends chính nó.
// class Loop extends Loop {}
```

Trong `T extends Comparable<T>`, `T` không tự extends chính mình theo nghĩa khai báo superclass; nó phải thực thi **một interface generic** mà đối số kiểu trỏ về chính `T`.

## 8. Tại sao `Comparable<? super T>` linh hoạt hơn `Comparable<T>`?

Xét quan hệ:

```java
class Animal implements Comparable<Animal> {
    private final String name;

    Animal(String name) {
        this.name = name;
    }

    @Override
    public int compareTo(Animal other) {
        return name.compareTo(other.name);
    }
}

class Dog extends Animal {
    Dog(String name) {
        super(name);
    }
}
```

`Dog` kế thừa việc so sánh của `Animal`. Vì `Animal implements Comparable<Animal>`, một `Dog` có thể được so sánh với các `Animal` khác — nhưng `Dog` **không tự nhiên trở thành `Comparable<Dog>`**. Generics Java không đồng biến: `Comparable<Animal>` và `Comparable<Dog>` là hai kiểu tham số hóa khác nhau.

Do đó, bound hẹp:

```java
// Có thể loại Dog trong ví dụ trên:
// static <T extends Comparable<T>> T max(Collection<T> items) { ... }
```

không linh hoạt bằng:

```java
static <T extends Comparable<? super T>> T max(
        java.util.Collection<? extends T> items) {
    java.util.Iterator<? extends T> iterator = items.iterator();
    if (!iterator.hasNext()) {
        throw new java.util.NoSuchElementException("Empty collection");
    }

    T best = iterator.next();
    while (iterator.hasNext()) {
        T candidate = iterator.next();
        if (candidate.compareTo(best) > 0) {
            best = candidate;
        }
    }
    return best;
}
```

Phân tích:

- `T extends Comparable<? super T>`: kiểu `T` phải có khả năng so sánh với `T` **hoặc một kiểu cha của `T`**.
- `Collection<? extends T>`: danh sách nguồn chứa `T` hoặc subtype phù hợp của `T`, nên duyệt và đọc như `T` an toàn.
- `candidate.compareTo(best)`: được compiler kiểm tra bởi bound `Comparable<? super T>`.
- Giá trị trả về là `T`: giữ lại kiểu phần tử theo hợp đồng, không ép về `Object`.

```java
// Với List<Dog> và Dog extends Animal implements Comparable<Animal>:
List<Dog> dogs = List.of(new Dog("Bim"), new Dog("An"));
Dog selected = max(dogs); // Bim vì "Bim" > "An" theo String.compareTo.
```

Đây là ví dụ **giới hạn tham chiếu đến tham số kiểu trong wildcard của một bound**. Phần `? super T` nằm **bên trong đối số kiểu của interface `Comparable`**, không phải khai báo bound "lower bound" trực tiếp cho `T`.

Nếu không cần tự viết thuật toán, `Collections.max(...)` đã cung cấp phương thức chuẩn có hợp đồng tương tự và xử lý trường hợp empty collection bằng ngoại lệ thích hợp.

## 9. F-bound ở lớp cha: `N extends Node<N>`

Một mẫu nâng cao khác là **self-referential type parameter** dành cho API fluent hoặc cây đối tượng:

```java
abstract class Node<N extends Node<N>> {
    abstract N self();

    N touch() {
        return self();
    }
}

final class TaskNode extends Node<TaskNode> {
    @Override
    TaskNode self() {
        return this;
    }

    String finish() {
        return "done";
    }
}
```

`Node<N extends Node<N>>` nghĩa là kiểu `N` phải thuộc gia đình `Node<N>`. Lớp con chọn `N = TaskNode` vì `TaskNode extends Node<TaskNode>`:

```java
TaskNode node = new TaskNode();
String result = node.touch().finish(); // "done".
```

Nhờ bound, `touch()` trả `N` thay vì `Node<?>`, cho phép code sử dụng tiếp các phương thức của lớp cụ thể mà không cast.

**Giới hạn cần hiểu:** Mẫu này không tự chứng minh tại runtime rằng mọi subtype sẽ chọn chính nó làm type argument. Java cho phép một số cách kế thừa không đúng ý đồ của nhà thiết kế nếu không kiểm soát hierarchy. Khi cần nghiêm ngặt, dùng `final` cho concrete subclasses hoặc thiết kế interface/factory phù hợp, đồng thời cân nhắc tính phức tạp của self-bound.

### Bound tự tham chiếu của enum

Java khai báo khái niệm enum theo kiểu cơ sở `Enum<E extends Enum<E>>`. Một generic method làm việc với enum có thể dùng bound:

```java
static <E extends Enum<E>> String enumName(E value) {
    return value.name();
}
```

`E` vừa là kiểu của enum cụ thể vừa được tham chiếu lại trong `Enum<E>`. Ví dụ với `enum Status { NEW, DONE }`:

```java
// enumName(Status.DONE) trả "DONE".
```

Đây là ứng dụng phổ biến của F-bound trong thư viện chuẩn, không phải thủ thuật riêng của một dự án.

## 10. Bound của lớp, phương thức và constructor

Dependent bounds được khai báo trong **danh sách tham số kiểu phù hợp với từng phạm vi**.

### 10.1. Ở lớp generic

```java
class ParentChild<Parent, Child extends Parent> {
    private final Child child;

    ParentChild(Child child) {
        this.child = child;
    }

    Parent asParent() {
        return child;
    }

    Child child() {
        return child;
    }
}
```

`Parent` và `Child` thuộc phạm vi của lớp; các phương thức instance sử dụng chúng mà không cần khai báo lại `<Parent, Child>`.

### 10.2. Ở phương thức generic trong lớp thông thường

```java
class RelationalTools {
    static <Base, Derived extends Base> Base viewAsBase(Derived item) {
        return item;
    }
}
```

Hai tham số chỉ thuộc phương thức; một lớp không generic vẫn hoàn toàn được phép khai báo method này. Vì method `static` có tham số kiểu riêng, nó không phụ thuộc type argument của lớp bao quanh.

### 10.3. Ở constructor generic

```java
class Description {
    private final String text;

    <Base, Derived extends Base> Description(
            Base general, Derived specialized) {
        this.text = general + " -> " + specialized;
    }

    String text() {
        return text;
    }
}
```

`Description` không phải generic class, nhưng constructor **tự khai báo** `<Base, Derived extends Base>`. Quan hệ subtype được kiểm tra ở mỗi lời gọi constructor. Một constructor trong `class Holder<T>` có thể kết hợp `T` của lớp với tham số kiểu mới:

```java
class Holder<T> {
    private final T value;

    <S extends T> Holder(S source) {
        this.value = source;
    }

    T get() {
        return value;
    }
}

// Holder<Number> h = new Holder<>(7); // S có thể được suy luận là Integer.
```

Ở đây `T` thuộc **lớp** `Holder<T>`; `S` thuộc **constructor**, bị bound bởi `T`. Không cần khai báo lại `<T>` cho constructor: điều đó sẽ tạo một tên trùng che khuất `T` lớp.

Hãy chú ý constructor generic cần type parameter list đặt trước tên constructor, không có kiểu trả về.

## 11. Suy luận kiểu và quan hệ bất biến của generic containers

Khi nhiều tham số phụ thuộc nhau, compiler giải một tập ràng buộc tại mỗi lời gọi. Có thể viết:

```java
// Lớp có static <Base, Item extends Base> List<Base> widen(...):
List<Number> values =
        DependentBoundsDemo.<Number, Integer>widen(List.of(1, 2));
```

Ở đây caller chỉ rõ `Base = Number` và `Item = Integer`; compiler xác minh `Integer extends Number` rồi trả `List<Number>`.

Trong khi đó, phép gán sau là **sai**:

```java
List<Integer> ints = List.of(1, 2);
// List<Number> nums = ints; // Sai: List<Integer> không phải List<Number>.
```

Quan hệ `Integer extends Number` không làm `List<Integer> extends List<Number>`. Nếu Java cho phép, người dùng `List<Number>` có thể đưa `Double` vào một đối tượng vốn hứa chỉ chứa `Integer`.

### Dùng wildcard khi nguồn chỉ sản xuất dữ liệu

```java
static <Base, Item extends Base> List<Base> widen(
        java.util.Collection<? extends Item> items) {
    java.util.List<Base> result = new java.util.ArrayList<>();
    result.addAll(items);
    return result;
}
```

`Collection<? extends Item>` bảo đảm các phần tử có thể đọc như `Item`; `Item extends Base` tiếp tục cho phép đưa từng phần tử vào `List<Base>`. Đây là cách phối hợp **dependent type bound** và **upper-bounded wildcard** mà không ép kiểu không kiểm tra được.

Bound ở `<Base, Item extends Base>` tạo quan hệ giữa **các type parameters**; wildcard `? extends Item` ở tham số phương thức tạo điều kiện cho **một giá trị collection cụ thể** được truyền vào. Cả hai cùng dùng từ khóa `extends` nhưng phạm vi và tác dụng khác nhau.

### Type witness và khả năng suy luận

Một lời gọi như `widen(List.of(1, 2))` có thể được compiler suy luận tùy ngữ cảnh; đôi khi kiểu `Base` được chọn thành kiểu rộng hoặc khác dự đoán. Để bảo vệ hợp đồng dễ đọc, đặt kiểu vế trái rõ hoặc dùng type witness `ClassName.<Number,Integer>method(...)`. Không nên dựa vào raw `List` hay cast unchecked để cố ép compiler chọn kết quả.

## 12. Thứ tự bound và những cú pháp không hợp lệ

Bảng so sánh các cách viết:

| Khai báo | Trạng thái | Ý nghĩa |
| --- | --- | --- |
| `<A, B extends A>` | Hợp lệ | `B` là subtype của `A`. |
| `<B extends A, A>` | Hợp lệ | Tham chiếu forward đến `A` được khai báo trong cùng danh sách. |
| `<T extends Comparable<T>>` | Hợp lệ | `T` hỗ trợ so sánh với chính `T`. |
| `<T extends Comparable<? super T>>` | Hợp lệ | `T` hỗ trợ so sánh với `T` hoặc một supertype. |
| `<E extends Enum<E>>` | Hợp lệ | Recursive bound thông dụng của enum. |
| `<A, B super A>` | Không hợp lệ | Khai báo type parameter không dùng `super` như wildcard. |
| `<A, B implements A>` | Không hợp lệ | Bound dùng `extends`, không dùng `implements`. |
| `<T extends Number & Comparable<T>>` | Hợp lệ | Bound lớp rồi đến bound interface. |
| `<T extends Comparable<T> & Number>` | Không hợp lệ | Nếu bound lớp là `Number`, nó phải đứng trước interface. |
| `<T extends String>` | Cú pháp hợp lệ nhưng không có type argument reference hợp lệ | `String` là final; không thể tạo subtype mới ngoài chính `String`. Dùng `T = String` vẫn hợp lệ. |

**Lưu ý về hàng cuối:** `<T extends String>` là một khai báo hợp lệ về mặt generic bounds (dù rất ít hữu ích), vì `T` vẫn có thể được gán là chính `String`. Không được diễn giải `extends` bắt buộc strict subtype; `String` thỏa bound `String` của chính nó.

Ví dụ về nhiều bound phụ thuộc:

```java
// Đây là chữ ký minh họa.
static <T extends Number & Comparable<T>, U extends T>
        T chooseNumber(T general, U specific) {
    return specific;
}
```

`T` trước hết phải là một subtype của `Number` và thực hiện `Comparable<T>`; tiếp đó `U` phải là subtype của `T`. Mỗi bound thêm một điều kiện, nhưng không thay đổi ý nghĩa `U extends T`.

Nếu compiler báo lỗi `type argument is not within bounds`, hãy kiểm tra đối số kiểu của từng tham số theo thứ tự. Ví dụ `Pair<String,Integer>` thất bại vì `Integer` không nằm trong miền mà bound `Sub extends Super` cho phép khi `Super = String`.

## 13. Hạn chế: raw type, type erasure, static context

Giới hạn kiểu được kiểm tra lúc biên dịch. Java generics chủ yếu dùng **type erasure**, nên runtime thường không giữ một lớp riêng cho mỗi cách tham số hóa `Pair<Number,Integer>` hoặc `Pair<CharSequence,String>`.

```java
// Những kiểu chung không thể trực tiếp được tạo hay kiểm tra ở runtime:
// T value = new T();            // Sai với T là type parameter.
// Class<T> clazz = T.class;     // Sai.
// if (object instanceof Pair<Number, Integer>) { } // Sai: tham số không reifiable.
```

Có thể kiểm tra `object instanceof Pair<?, ?>` nếu cần xác nhận dạng lớp, nhưng phép kiểm tra ấy không chứng minh các đối số kiểu cụ thể hay kiểu dữ liệu thực trong từng trường. Khi tiếp nhận dữ liệu từ nguồn ngoài, vẫn phải xác thực các giá trị nếu rủi ro dữ liệu sai kiểu là có thật.

### Raw type có thể phá lời hứa của bound

```java
Pair<Number, Integer> correct = new Pair<>(1.5, 4);
// Pair raw = correct; // Dạng raw làm mất thông tin về hai type arguments.
```

Đừng dùng `Pair` raw rồi cast về `Pair<String,Integer>` để vượt qua giới hạn compiler. Raw type và unchecked conversion có thể tạo **heap pollution**, dẫn đến `ClassCastException` tại nơi đọc giá trị sau này. Bound không phải cơ chế kiểm tra dữ liệu runtime thay thế cho validation.

### Static member không mượn được type parameter của lớp

```java
class Container<Base, Item extends Base> {
    // static Item last; // Không hợp lệ: Item thuộc lớp, không thuộc static member.

    static <X, Y extends X> X promote(Y value) {
        return value;
    }
}
```

`Base`/`Item` là tham số kiểu của `Container`, nên dùng trong instance fields/methods. Một static generic method phải **tự khai báo `<X,Y extends X>`**; hai tham số mới độc lập với tham số kiểu của lớp.

## 14. Chương trình Java 17+ hoàn chỉnh, đã kiểm thử

Tạo tệp **`DependentBoundsDemo.java`** đúng nội dung dưới đây. Mã minh họa:

- Bound giữa hai type parameters trên lớp `Pair<Super, Sub extends Super>`.
- Lớp con cố định type arguments `NumberPair extends Pair<Number,Integer>`.
- Phương thức generic `choose` và `widen` dùng `Sub extends Super`.
- Giới hạn tự tham chiếu `Comparable<? super T>` qua lớp `Dog extends Animal implements Comparable<Animal>`.
- F-bound `E extends Enum<E>` và `N extends Self<N>`.

```java
import java.util.*;

public class DependentBoundsDemo {
    static class Animal implements Comparable<Animal> {
        private final String name;

        Animal(String name) { this.name = name; }
        String name() { return name; }

        @Override
        public int compareTo(Animal other) {
            return name.compareTo(other.name);
        }
    }

    static final class Dog extends Animal {
        Dog(String name) { super(name); }
    }

    static class Pair<Super, Sub extends Super> {
        private final Super first;
        private final Sub second;

        Pair(Super first, Sub second) {
            this.first = first;
            this.second = second;
        }

        Super first() { return first; }
        Sub second() { return second; }
    }

    static final class NumberPair extends Pair<Number, Integer> {
        NumberPair(Number first, Integer second) {
            super(first, second);
        }
    }

    static <Super, Sub extends Super> Super choose(
            boolean useSub, Super first, Sub second) {
        return useSub ? second : first;
    }

    static <T extends Comparable<? super T>> T max(
            Collection<? extends T> source) {
        Iterator<? extends T> iterator = source.iterator();
        if (!iterator.hasNext()) {
            throw new NoSuchElementException("empty");
        }

        T best = iterator.next();
        while (iterator.hasNext()) {
            T value = iterator.next();
            if (value.compareTo(best) > 0) {
                best = value;
            }
        }
        return best;
    }

    static <E extends Enum<E>> String enumName(E value) {
        return value.name();
    }

    enum Status { NEW, DONE }

    static abstract class Self<N extends Self<N>> {
        abstract N self();

        N fluent() {
            return self();
        }
    }

    static final class Task extends Self<Task> {
        @Override
        Task self() { return this; }

        String finish() { return "done"; }
    }

    static <Base, Item extends Base> List<Base> widen(
            Collection<? extends Item> items) {
        List<Base> result = new ArrayList<>();
        result.addAll(items);
        return result;
    }

    public static void main(String[] args) {
        Pair<Number, Integer> pair = new Pair<>(3.5, 7);
        System.out.println("pair: " + pair.first() + " / " + pair.second());

        System.out.println("choice: " +
                DependentBoundsDemo.<Number, Integer>choose(true, 1.5, 9));

        List<Dog> dogs = List.of(new Dog("Bim"), new Dog("An"));
        System.out.println("max dog: " + max(dogs).name());

        System.out.println("enum: " + enumName(Status.DONE));
        System.out.println("self: " + new Task().fluent().finish());

        List<Number> numbers =
                DependentBoundsDemo.<Number, Integer>widen(List.of(2, 4));
        System.out.println("widen: " + numbers);

        NumberPair np = new NumberPair(1.2, 3);
        System.out.println("fixed: " + np.second());
    }
}
```

Biên dịch và chạy trên JDK 17+:

```bash
javac --release 17 -Xlint:all DependentBoundsDemo.java
java DependentBoundsDemo
```

**Stdout chính xác** (đã chạy với javac tương thích `--release 17`, không có cảnh báo từ `-Xlint:all`):

```text
pair: 3.5 / 7
choice: 9
max dog: Bim
enum: DONE
self: done
widen: [2, 4]
fixed: 3
```

Diễn giải kết quả:

1. `Pair<Number,Integer>` lưu `3.5` như `Number` và `7` như `Integer`, do bound `Integer extends Number`.
2. Type witness `<Number,Integer>` cho `choose` thể hiện rõ quan hệ, hàm trả nhánh thứ hai là `9` dưới kiểu kết quả `Number`.
3. `Dog` kế thừa `Comparable<Animal>` qua `Animal`; bound `Comparable<? super Dog>` phù hợp, nên `max(dogs)` trả một `Dog`. `"Bim"` lớn hơn `"An"` theo `String.compareTo`.
4. `Status.DONE` là giá trị enum thỏa `E extends Enum<E>`; `enumName` trả tên hằng `DONE`.
5. `Task extends Self<Task>` nên `fluent()` có kiểu `Task`; lời gọi nối tiếp `finish()` thành công.
6. `widen` sao chép nguồn `Integer` thành `List<Number>` mới. Nó không cố ép một `List<Integer>` hiện có thành `List<Number>`.
7. `NumberPair` kế thừa lớp generic bằng đối số kiểu cố định và getter `second()` trả `Integer`.

## 15. Các lỗi thường gặp và cách sửa

| Biểu hiện | Giải thích | Cách xử lý |
| --- | --- | --- |
| `Pair<String,Integer>` báo vi phạm bound | `Integer` không phải subtype của `String` | Chọn type arguments thực sự có quan hệ subtype. |
| `<Super, Sub super Super>` không biên dịch | Bound khai báo type parameter không dùng `super` | Viết `<Super, Sub extends Super>`. |
| `<T implements Comparable<T>>` không biên dịch | Bound của type parameter dùng `extends` ngay cả cho interface | Viết `<T extends Comparable<T>>`. |
| `List<Integer>` không gán cho `List<Number>` | Generic type arguments là invariant | Dùng `List<? extends Number>` để đọc, hoặc copy sang list đích phù hợp. |
| `<T extends Comparable<T>>` từ chối một số subtype | Kiểu con có thể chỉ thực hiện `Comparable<Supertype>` | Cân nhắc `<T extends Comparable<? super T>>`. |
| `static Sub method(...)` bên trong `class Pair<Super,Sub>` lỗi | Static member không tham chiếu type parameter lớp | Khai báo type parameters mới trên static method. |
| Cố `new T()` từ generic method | Erasure không cung cấp constructor của `T` | Nhận `Supplier<? extends T>`/factory. |
| Dùng raw `Pair` để bỏ cảnh báo | Xóa kiểm tra generic thay vì giải đúng ràng buộc | Giữ kiểu tham số hóa; kiểm tra dữ liệu legacy ở boundary. |
| Giả định `Sub extends Super` bắt buộc là subclass trực tiếp | Subtype có thể theo nhiều cấp hoặc cùng kiểu | Dựa vào quan hệ subtype mà compiler kiểm tra. |
| Đọc `Comparable<? super T>` thành “T có super bound” | `super` thuộc wildcard bên trong `Comparable` | Phân tách từng lớp cú pháp: bound `extends Comparable<...>` và wildcard `? super T`. |
| Bound vòng tròn tùy ý dẫn đến lỗi | Không phải mọi chu trình phụ thuộc đều hợp lệ | Dùng mẫu F-bound đã hiểu rõ, tránh thiết kế type hierarchy quá phức tạp. |
| Compiler suy luận kiểu đích khác dự định | Nhiều cách gán type arguments thỏa bounds | Đặt type đích rõ hoặc explicit type witness. |

### Quy trình debug lời gọi có dependent bounds

1. Xác định danh sách khai báo type parameters: nằm sau tên lớp, trước tên phương thức/constructor, hay bên trong một interface generic?
2. Vẽ quan hệ `Sub <: Super` cho `Sub extends Super`, và xác định kiểu cụ thể mà caller muốn truyền.
3. Với `T extends Comparable<? super T>`, kiểm tra kiểu `T` thực hiện `Comparable` của chính nó hay của một supertype.
4. Nếu có collection, tách **quan hệ type parameter** khỏi **quan hệ tham số hóa collection**: `List<Integer>` khác `List<Number>`.
5. Nếu inference khó hiểu, thêm type witness tại lời gọi hoặc khai báo kiểu kết quả tường minh; đọc compiler diagnostic thay vì che lỗi bằng cast.
6. Với code legacy/raw, xác thực dữ liệu trước khi chuyển vào API generic để không phát tán heap pollution.

## 16. Bài tập thực hành

**Bài 1 — Bound hai tham số kiểu.** Viết `class Holder<Base, Child extends Base>` với `Child get()` và `Base asBase()`. Tạo `Holder<Number,Integer>`, thử `Holder<CharSequence,String>` và phân tích vì sao `Holder<String,Integer>` thất bại.

**Bài 2 — Forward reference.** Viết một class `Forward<A extends B,B>` và phương thức `static <A extends B,B> B promote(A input)`. Biên dịch Java 17 và giải thích tại sao việc `B` xuất hiện phía sau vẫn được chấp nhận. Sau đó đổi thứ tự thành `<B,A extends B>` để tăng khả năng đọc.

**Bài 3 — Recursive bound.** Viết `static <T extends Comparable<? super T>> T min(Collection<? extends T> values)`, xử lý collection rỗng rõ ràng. Kiểm tra với `List<Integer>`, `List<String>` và subclass của một lớp cha thực hiện `Comparable<Cha>`.

**Bài 4 — Enum F-bound.** Viết `static <E extends Enum<E>> boolean sameName(E a, E b)` so sánh `a.name()` và `b.name()`. Giải thích rằng `E` buộc hai tham số có cùng kiểu enum tại chữ ký (caller không truyền hai enum khác nhau theo cách thông thường với một `E` duy nhất).

**Bài 5 — Self-bound.** Viết `abstract class Fluent<S extends Fluent<S>>` có phương thức `S configure()` dựa vào `S self()`; tạo concrete class `Query extends Fluent<Query>`. Kiểm tra `new Query().configure().execute()` khi `execute()` thuộc `Query`.

**Bài 6 — Invariance và copy.** Tạo `List<Integer> input = List.of(1,2,3)`. Chứng minh không gán trực tiếp vào `List<Number>`; dùng phương thức `widen` với `<Number,Integer>` để nhận một list số kiểu rộng hơn. Hãy thử thêm `Double` vào kết quả và giải thích vì sao điều này không thay đổi nguồn ban đầu.

**Bài 7 — Thiết kế API.** Một hệ thống có `class Animal` và `class Dog extends Animal`. Bạn cần hàm nhận nguồn `Collection<Dog>` và xuất `List<Animal>`. So sánh chữ ký dùng hai type parameters `<Base,Derived extends Base>` với chữ ký chỉ dùng `Collection<? extends Animal>`. Khi nào bound phụ thuộc thực sự đem lại lợi ích, khi nào chỉ thêm phức tạp?

## 17. Tổng kết

**Giới hạn tham chiếu đến tham số kiểu khác** cho phép diễn tả quan hệ mà Java có thể chứng minh ở thời điểm biên dịch:

- `<A, B extends A>`: `B` là subtype hợp lệ của `A`; dùng trong class, generic method hoặc constructor.
- `<T extends Comparable<T>>`: `T` được so sánh với chính kiểu `T` theo giao diện.
- `<T extends Comparable<? super T>>`: phiên bản linh hoạt hơn khi một kiểu thừa hưởng khả năng so sánh với supertype.
- `<E extends Enum<E>>`, `<N extends Node<N>>`: các **F-bounds** tự tham chiếu, hữu ích cho enum và self-typed APIs.
- Dependent bound và wildcard liên quan nhưng không giống nhau; Java generics mặc định **invariant**, nên `List<Derived>` không tự là `List<Base>`.
- Type inference, erasure và static context không xóa bỏ nghĩa của bound: hãy dùng kiểu khai báo chính xác và để compiler bảo vệ quan hệ subtype.

Khi gặp chữ ký generic khó đọc, xác định từng tham số, từng bound và hướng dữ liệu đi qua API. Câu hỏi quan trọng nhất là **“Giá trị thuộc type parameter này có thể được dùng một cách an toàn ở vị trí yêu cầu type parameter kia hay không?”**. Nếu biểu diễn được câu trả lời bằng bound như `Sub extends Super` hoặc `T extends Comparable<? super T>`, bạn đang tận dụng generics đúng mục đích: **tái sử dụng thuật toán mà vẫn giữ an toàn kiểu**.
