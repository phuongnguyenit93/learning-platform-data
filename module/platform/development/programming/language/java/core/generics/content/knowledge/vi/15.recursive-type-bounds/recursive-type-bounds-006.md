# Giới hạn của kiểu tự tham chiếu: F-bounded generics không tự bảo đảm mọi lớp con

## 1. Vấn đề: kiểu trông giống “chính mình” nhưng không có bảo đảm tương ứng

Trong Java Generics, **kiểu tự tham chiếu** thường được mô hình hóa bằng một tham số kiểu có giới hạn đệ quy (*F-bounded type parameter*):

~~~java
abstract class Base<T extends Base<T>> {
    // API có thể sử dụng T cho tham số và kiểu trả về.
}
~~~

Đọc biểu thức `T extends Base<T>` là: **tham số kiểu được cung cấp cho T phải là một subtype của Base<T>**. Ràng buộc này cho phép compiler kiểm tra nhiều tương quan kiểu hữu ích, chẳng hạn một API chỉ chấp nhận đối tượng có tham số kiểu tương ứng.

Tuy nhiên, nó **không có nghĩa**: “mọi lớp `C extends Base<...>` đều bắt buộc phải truyền `C` làm tham số kiểu”.

Chẳng hạn, hai khai báo sau đều biên dịch:

~~~java
final class Correct extends Base<Correct> {}
final class Mismatch extends Base<Correct> {}
~~~

Lớp `Correct` thỏa `Correct extends Base<Correct>`. Vì thế `Correct` là đối số hợp lệ cho `T` của `Base<T>`, ngay cả khi **lớp trực tiếp mở rộng Base là Mismatch**.

Đây là giới hạn nền tảng: **Java kiểm tra cận của đối số kiểu T, không tự ràng buộc T bằng tên của chính lớp con đang khai báo**. Java không có một từ khóa generic tự động đại diện cho “kiểu runtime/chính xác của this” trong mọi lớp con.

## 2. F-bound thực sự kiểm tra điều gì?

Xét:

~~~java
abstract class Node<S extends Node<S>> {
    public abstract String id();
    public String connect(S next) {
        return id() + " -> " + next.id();
    }
}
~~~

Giới hạn `S extends Node<S>` áp đặt quan hệ lên **S**. Khi viết `class Alpha extends Node<Alpha>`, compiler kiểm tra `Alpha` có thỏa `Node<Alpha>` hay không.

Nhưng khi viết:

~~~java
final class Alpha extends Node<Alpha> {
    @Override
    public String id() { return "alpha"; }
}

final class Beta extends Node<Alpha> {
    @Override
    public String id() { return "beta"; }
}
~~~

compiler kiểm tra `Alpha` có phải subtype của `Node<Alpha>` hay không, và câu trả lời là có. Nó **không kiểm tra Beta là Alpha**. Beta vì vậy kế thừa `connect(Alpha next)`, chứ không kế thừa `connect(Beta next)`.

Mô tả quan hệ:

~~~text
Alpha extends Node<Alpha>  → hợp lệ
Beta  extends Node<Alpha>  → cũng hợp lệ

Node<S> có connect(S)
Beta nhận connect(Alpha), không nhận connect(Beta)
~~~

Nếu người thiết kế tưởng `connect(S)` luôn có nghĩa “chỉ kết nối hai đối tượng cùng lớp con”, API đã không bảo đảm đúng điều đó.

### Quy tắc hợp lệ và không hợp lệ

| Khai báo | Kết quả | Lý do |
| --- | --- | --- |
| `class A extends Root<A>` | Hợp lệ nếu A thỏa Root<A> | T = A đáp ứng cận đệ quy. |
| `class B extends Root<A>` | Vẫn có thể hợp lệ | Chỉ A cần thỏa Root<A>; B không nhất thiết là A. |
| `class C extends Root<String>` | Không hợp lệ đối với `Root<T extends Root<T>>` | String không phải subtype của Root<String>. |
| `class D extends Root<D>` | Hợp lệ nếu khai báo tạo quan hệ D extends Root<D> | Compiler có thể kiểm tra cận đệ quy qua chính lớp đang định nghĩa. |

Các khai báo ở bảng là **các trường hợp riêng**, giả định tồn tại kiểu `Root<T extends Root<T>>`. Không được dán tất cả như một chương trình Java vì một số khai báo được cố ý viết để minh họa lỗi.

## 3. Ví dụ chạy được: một lớp con “khai” kiểu của lớp con khác

Lưu chương trình hoàn chỉnh dưới tên **SelfTypeLimitDemo.java**:

~~~java
abstract class Fluent<S extends Fluent<S>> {
    private final String name;

    protected Fluent(String name) {
        this.name = name;
    }

    public String name() {
        return name;
    }

    public String pairWith(S other) {
        return name + " + " + other.name();
    }

    @SuppressWarnings("unchecked")
    public S uncheckedSelf() {
        return (S) this;
    }
}

final class Correct extends Fluent<Correct> {
    Correct(String name) {
        super(name);
    }
}

// Hợp lệ, dù Mismatch không phải là Correct!
final class Mismatch extends Fluent<Correct> {
    Mismatch(String name) {
        super(name);
    }
}

class Parent extends Fluent<Parent> {
    Parent(String name) {
        super(name);
    }
}

// Một lớp con tiếp theo tự động giữ tham số kiểu Parent.
final class Child extends Parent {
    Child(String name) {
        super(name);
    }
}

public class SelfTypeLimitDemo {
    public static void main(String[] args) {
        Correct expected = new Correct("correct");
        Mismatch actual = new Mismatch("mismatch");

        // Mismatch có phương thức pairWith(Correct).
        System.out.println(actual.pairWith(expected));

        Parent parent = new Parent("parent");
        Child child = new Child("child");

        // Child kế thừa pairWith(Parent), không phải pairWith(Child).
        System.out.println(child.pairWith(parent));

        try {
            // Compiler tin kiểu trả về khai báo là Correct.
            Correct wrong = actual.uncheckedSelf();
            System.out.println(wrong.name());
        } catch (ClassCastException error) {
            System.out.println("unchecked self -> ClassCastException");
        }
    }
}
~~~

Biên dịch và chạy trên Java 17 trở lên:

~~~bash
javac SelfTypeLimitDemo.java
java SelfTypeLimitDemo
~~~

Kết quả:

~~~text
mismatch + correct
child + parent
unchecked self -> ClassCastException
~~~

**Phân tích từng kết quả:**

1. `actual` là Mismatch, nhưng tham số kiểu của `Fluent` mà Mismatch sử dụng là Correct. Vì vậy phương thức `pairWith` yêu cầu một **Correct**. Lời gọi hợp lệ và in `mismatch + correct`.
2. `Child` kế thừa `Parent extends Fluent<Parent>`, nên phương thức kế thừa `pairWith` yêu cầu **Parent**. Lời gọi với đối tượng `Parent` hợp lệ dù receiver là `Child`. Điều này cho thấy quan hệ generic không tự chuyển từ Parent thành Child ở mỗi cấp kế thừa.
3. `uncheckedSelf()` dùng `(S) this`, nhưng `this` của `Mismatch` thực sự là Mismatch, không phải Correct. Phép ép kiểu không được kiểm chứng hoàn chỉnh tại vị trí lớp generic. Khi lời gọi được sử dụng như một `Correct`, kiểm tra kiểu runtime được áp dụng tại ranh giới sử dụng kết quả và ném `ClassCastException`.

**Lưu ý:** `@SuppressWarnings("unchecked")` chỉ ẩn cảnh báo compiler; nó không bảo đảm phép ép kiểu là đúng. Trong ví dụ, phép ép nằm trong generic class chủ ý để cho thấy thiết kế thiếu an toàn; không nên đưa nguyên mẫu `uncheckedSelf()` vào thư viện dùng thực tế mà không có bất biến kiểu được bảo đảm.

## 4. Vì sao phép ép `(S) this` nguy hiểm?

Một cách hiện thực API fluent thường thấy:

~~~java
abstract class Chain<S extends Chain<S>> {
    @SuppressWarnings("unchecked")
    public S step() {
        // Cập nhật trạng thái.
        return (S) this;
    }
}
~~~

Ý định là cho phép:

~~~java
final class GoodChain extends Chain<GoodChain> {}
GoodChain result = new GoodChain().step();
~~~

Trong trường hợp `GoodChain`, quan hệ giữa lớp thực tế và tham số `S` đúng như ý định.

Nhưng Java vẫn cho phép:

~~~java
final class WrongChain extends Chain<GoodChain> {}
~~~

Đối số `GoodChain` vẫn đáp ứng `S extends Chain<S>`. Lời gọi:

~~~java
GoodChain wrong = new WrongChain().step();
~~~

biên dịch nhưng có thể ném `ClassCastException` khi kết quả được dùng như `GoodChain`.

### Vai trò của type erasure

Generic trong Java chủ yếu được triển khai qua **type erasure**. Tham số kiểu `S` có cận trên là `Chain<S>` sẽ bị xóa về kiểu cận tương ứng khi sinh bytecode. Do đó phép ép `(S) this` bên trong lớp generic không thể tự xác minh rằng đối tượng hiện tại thuộc đúng lớp cụ thể mà caller gắn cho `S`.

Compiler có thể chèn `checkcast` tại nơi kết quả generic được sử dụng với kiểu cụ thể. Vì thế lỗi thường xuất hiện **ở chỗ nhận kết quả**, không nhất thiết tại lệnh `return (S) this`.

Không nên suy ra rằng type erasure làm mọi generic đều không an toàn. Suy luận và kiểm tra generics ở thời điểm biên dịch vẫn rất có giá trị. Điểm thiếu an toàn ở đây phát sinh từ một **unchecked cast cộng với giả định không được F-bound bảo đảm**.

### Không phải mọi phương thức dùng S đều nguy hiểm

Phương thức nhận tham số `S` như `pairWith(S)` có thể hoàn toàn hợp lệ về kiểu; chỉ là ý nghĩa “S luôn trùng lớp runtime của this” không được bảo đảm. Rủi ro ném `ClassCastException` trở nên rõ nhất khi thân generic tự ép `this` thành `S` hoặc trả `this` bằng một đường ép kiểu không kiểm tra được.

## 5. Ngay cả khai báo đúng kiểu tự tham chiếu cũng có thể mất bảo đảm ở lớp cháu

Xét:

~~~java
class Parent extends Chain<Parent> {}
class Child extends Parent {}
~~~

Giả sử `Chain<S>` có phương thức:

~~~java
public S step() {
    // ...
    return (S) this; // cần hiểu rủi ro unchecked cast.
}
~~~

Với `Child`, phương thức được kế thừa vẫn có kiểu trả về compile-time **Parent**, không tự biến thành Child. Java không suy luận lại tham số generic mà Parent đã truyền cho Chain.

Vì thế:

~~~java
Child child = new Child();
Parent p = child.step(); // Hợp lệ.
// Child c = child.step(); // Không biên dịch: step() trả Parent.
~~~

Nếu thiết kế một DSL/fluent API cần giữ nguyên kiểu lớp lá qua mọi bước, **cho phép kế thừa sâu sau khi đã cố định S** có thể làm API mất độ chính xác. Khai báo một lớp `Parent extends Chain<Parent>` rồi để các lớp khác `extends Parent` không còn bảo đảm kiểu trả về của chain là lớp con cuối cùng.

Ngay cả khi `Parent` có những phương thức ghi đè để trả về Parent theo cơ chế covariant return, Java cũng **không tự ghi đè lại** phương thức cho Child. Muốn Child nhận kiểu trả về Child, cần thiết kế API và thứ bậc kế thừa phù hợp hoặc khai báo/ghi đè rõ ràng ở cấp Child.

## 6. F-bound bảo đảm được gì và không bảo đảm được gì?

**F-bound bảo đảm tại compile time:**

- Tham số `S` phải thỏa cận khai báo, ví dụ `S extends Base<S>`.
- Bên trong `Base<S>`, có thể sử dụng các API mà compiler biết `S` kế thừa từ Base<S>.
- Những lời gọi phương thức nhận `S` được kiểm tra theo tham số generic đã chọn.
- Lớp viết `extends Base<Unrelated>` bị từ chối nếu `Unrelated` không đáp ứng giới hạn đệ quy.

**F-bound không tự bảo đảm:**

- Mọi lớp `C` đều bắt buộc khai báo `extends Base<C>`.
- `S` chính là lớp runtime của `this`.
- `S` là lớp con cụ thể sâu nhất trong cả cây kế thừa.
- `(S) this` luôn an toàn ở runtime.
- Một phương thức trả về `S` nhất thiết trả về **chính đối tượng this**; nó có thể trả một đối tượng khác có kiểu S.
- Một lớp thư viện có thể chặn tất cả cách mở rộng không tuân thủ quy ước chỉ bằng giới hạn generic.

**Phân biệt quan hệ subtype với sự bằng nhau về kiểu:** `S extends Base<S>` đặt yêu cầu `S` là subtype của `Base<S>`. Nó không là biểu thức kiểu `S == RuntimeClassOf(this)`.

## 7. Những biện pháp thiết kế API thực tế

### 7.1. Tách hành vi thật sự cần T khỏi lời hứa “this là T”

Nếu API chỉ cần so sánh hay nối một `S` đã biết, hãy dùng giới hạn như bình thường:

~~~java
abstract class Relation<S extends Relation<S>> {
    public abstract int compareTo(S other);
}
~~~

Chữ ký trên buộc đối số `compareTo` theo `S` mà lớp con đã chọn. Đừng tự diễn giải nó thành “hai đối tượng luôn cùng lớp runtime”.

Nếu toàn bộ yêu cầu chỉ là phương thức trả lại đối tượng hiện tại để chain, hãy cân nhắc trả về kiểu cơ sở hoặc một interface chung, thay vì ép `this` thành tham số kiểu có khả năng bị chọn sai.

### 7.2. Cho lớp lá hiện thực self() bằng kiểu cụ thể

Một mẫu thay thế giúp tránh phép ép `(S) this` trong base:

~~~java
abstract class FluentSafe<S extends FluentSafe<S>> {
    protected abstract S self();

    public S touch() {
        // Thực hiện thao tác.
        return self();
    }
}

final class SafeBuilder extends FluentSafe<SafeBuilder> {
    @Override
    protected SafeBuilder self() {
        return this;
    }
}
~~~

Ở `SafeBuilder`, `return this` được compiler kiểm tra bằng kiểu cụ thể `SafeBuilder`; không cần unchecked cast tại `FluentSafe`.

**Nhưng vẫn là hợp đồng thiết kế:** một lớp khác vẫn có thể chọn `FluentSafe<SafeBuilder>` và triển khai `self()` bằng cách trả một `SafeBuilder` mới. Compiler sẽ kiểm tra kiểu trả về là SafeBuilder, nhưng không kiểm chứng rằng nó là đúng đối tượng nhận lời gọi. Mẫu abstract self giải quyết **vấn đề unchecked cast tại lớp generic**, chứ không tạo ra một từ khóa “this type” mới.

### 7.3. Khóa thứ bậc khi cần bất biến chặt

Nếu thư viện sở hữu mọi lớp con, Java 17+ có thể dùng **sealed class** để giới hạn tập lớp được phép kế thừa, kết hợp những lớp lá **final**:

~~~java
sealed abstract class Restricted<S extends Restricted<S>>
        permits OnlyAllowed {
}

final class OnlyAllowed extends Restricted<OnlyAllowed> {
}
~~~

Trong ví dụ trên, chỉ `OnlyAllowed` được phép trực tiếp kế thừa `Restricted` theo khai báo `permits`; `OnlyAllowed` lại là final. Nhờ vậy ta có tập lớp con được đóng và có thể kiểm tra thủ công quan hệ tự tham chiếu của từng lớp được cho phép.

**Cần phân biệt rõ:** sealed class giới hạn **lớp nào được kế thừa**; nó không tự cấm một lớp được phép ghi sai tham số generic. Người thiết kế vẫn phải rà soát `extends Restricted<...>` của từng lớp trong `permits`. Trong cấu trúc phức tạp có lớp con `sealed` hoặc `non-sealed` trung gian, cần kiểm soát tiếp các cấp kế thừa.

### 7.4. Factory, constructor và khả năng kế thừa

Giới hạn constructor, cung cấp factory trả kiểu cụ thể và chọn final cho lớp lá có thể giảm khả năng tạo các biến thể ngoài ý định. Tuy nhiên, một lớp cơ sở trừu tượng có constructor protected và có thể được mở rộng vẫn có khả năng nhận các lớp con chọn tham số kiểu khác với chính chúng. Không nên tuyên bố factory hoặc một lớp lá final đơn lẻ đủ để buộc **mọi** lớp con của một base mở rộng là đúng kiểu.

### 7.5. Sử dụng hợp đồng interface khi không cần self-type chính xác

Nếu các thao tác dùng được ở cấp trừu tượng, một interface không có tham số “self” có thể đơn giản và rõ hơn. Ví dụ:

~~~java
interface Named {
    String name();
}
~~~

Khi phương thức chỉ cần trả String hoặc so sánh hai Named, thêm F-bound có thể tạo độ phức tạp mà không mang lại bảo đảm thiết yếu. Chỉ dùng F-bound nếu mối quan hệ generic mà nó **thực sự kiểm tra** có giá trị với API.

## 8. Trường hợp có quy tắc ngôn ngữ bổ sung

Một số API trong Java chuẩn dùng recursive bound, nổi tiếng là:

~~~java
class Example<E extends Enum<E>> {
}
~~~

Nhưng không nên suy diễn rằng cứ dùng mẫu `T extends Base<T>` là sẽ có tất cả đặc tính của enum. **Enum trong Java chịu quy tắc ngôn ngữ riêng về khai báo enum, kế thừa và khả năng mở rộng**. Những giới hạn bổ sung ấy không phát sinh tự động từ cú pháp F-bound của một lớp thông thường.

Tương tự, khi gặp chữ ký `Comparable<T>`, hãy đọc ý nghĩa kiểu ở ngay hợp đồng của phương thức. Một lớp triển khai `Comparable<Other>` hoàn toàn có thể so sánh với Other nếu hợp đồng cho phép; `Comparable<T>` không có nghĩa bắt buộc T là tên của lớp đang triển khai. Nếu API đòi hai giá trị cùng đúng loại, phải xác định và kiểm tra bất biến bằng thiết kế cụ thể.

## 9. Những lỗi dễ gặp khi review generic API

### Lỗi 1: Nhìn thấy `T extends Base<T>` rồi kết luận “T chính là this”

~~~java
class Wrong extends Base<Right> {
}
~~~

Nếu Right đáp ứng `Right extends Base<Right>`, khai báo Wrong có thể hợp lệ. Hãy kiểm tra **đối số generic thực tế** của mỗi lớp con, không chỉ tên tham số kiểu ở lớp cơ sở.

### Lỗi 2: Che hết unchecked warning

~~~java
@SuppressWarnings("unchecked")
T self() {
    return (T) this;
}
~~~

Suppress warning chỉ phù hợp khi nhà phát triển đã chứng minh bằng kiến trúc rằng cast là an toàn. Nếu base là điểm mở rộng công khai, người dùng có thể khai báo lớp con “lệch” và phá giả định đó. Cần có thiết kế đóng hoặc tránh cast.

### Lỗi 3: Final một lớp lá rồi nghĩ cây đã an toàn

~~~java
final class Good extends Base<Good> {
}
class Other extends Base<Good> {
}
~~~

`Good` final ngăn các lớp khác `extends Good`, nhưng không tự ngăn `Other extends Base<Good>`. Muốn hạn chế tất cả lớp con của Base phải có chiến lược kiểm soát trực tiếp tại Base, ví dụ sealed hierarchy, và kiểm tra toàn bộ lớp được phép.

### Lỗi 4: Để lớp cháu kế thừa kiểu self của lớp cha

~~~java
class Parent extends Base<Parent> {
}
class Child extends Parent {
}
~~~

Child vẫn mang quan hệ generic của Parent. Một hàm trong Base trả về T vì thế trả Parent ở compile time khi được gọi qua Child. Cần dự liệu trước chiều sâu kế thừa.

### Lỗi 5: Dùng raw type hoặc unchecked cast để né ràng buộc

Raw type có thể bỏ qua một phần kiểm tra generics, còn unchecked cast có thể tạo lỗi chạy. Khi thiết kế bị vướng giới hạn self-type, hãy xem lại hợp đồng API hoặc cấu trúc kế thừa. Đừng dùng ép kiểu chỉ để che bất nhất.

## 10. Bài tập suy luận

**Câu 1.** Vì sao `class Odd extends Base<Good>` có thể hợp lệ dù Odd không phải Good?

**Đáp án:** Compiler kiểm tra đối số `Good` có đáp ứng `Good extends Base<Good>` hay không. Ràng buộc ấy không đòi Odd bằng Good.

**Câu 2.** Với `class Child extends Parent` và `class Parent extends Base<Parent>`, kiểu trả về của phương thức `T next()` kế thừa từ Base khi gọi trên Child là gì?

**Đáp án:** Parent, vì `T` được cố định là Parent ở khai báo `Parent extends Base<Parent>`; kế thừa sâu hơn không tự tái chuyên biệt hóa T.

**Câu 3.** Tại sao `return (T) this` trong lớp cơ sở generic có thể gặp ClassCastException ở nơi gọi?

**Đáp án:** Compiler không bảo đảm runtime class của this đúng bằng T được lớp con khai báo. Cast chưa kiểm tra được đầy đủ ở mức generic do type erasure; khi kết quả được dùng như kiểu cụ thể, kiểm tra runtime có thể thất bại.

**Câu 4.** Một base sealed có tự bảo đảm lớp được phép kế thừa sẽ chọn đúng self-type không?

**Đáp án:** Không. Sealed giới hạn danh sách lớp con; generic bound vẫn kiểm tra cận của tham số kiểu, không so nó với lớp con. Phải kiểm tra các khai báo permitted subclasses và kiểm soát kế thừa ở mọi cấp.

**Câu 5.** Mẫu abstract `S self()` giúp gì và không giải quyết điều gì?

**Đáp án:** Nó có thể đưa việc trả self về lớp cụ thể, để compiler kiểm tra `return this` mà không cần cast trong base. Nhưng một lớp con vẫn có thể chọn S là lớp khác và trả về một đối tượng S khác; sự đồng nhất với this cần được bảo đảm bằng thiết kế hoặc hợp đồng riêng.

## 11. Kết luận kỹ thuật

F-bounded generics là công cụ diễn đạt quan hệ `T extends Base<T>` ở **thời điểm biên dịch**. Nó hữu ích cho phương thức có tham số và kết quả dựa trên T, nhưng **không phải cơ chế self-type được cưỡng chế tuyệt đối**. Một lớp có thể kế thừa `Base<Other>` nếu Other thỏa cận; một lớp cháu có thể kế thừa tham số kiểu đã cố định của lớp cha; và `(T) this` có thể không an toàn.

Khi cần các bất biến mạnh hơn, hãy chọn biện pháp tương ứng: tránh unchecked cast, yêu cầu lớp cụ thể hiện thực self, giới hạn thứ bậc bằng final/sealed và rà soát từng lớp được phép, hoặc đơn giản hóa API để dùng kiểu interface chung. Đánh giá tính an toàn dựa vào **những điều compiler thực sự kiểm chứng**, không dựa vào tên `Self` hay `T`.
