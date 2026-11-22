# Kiểu thành viên được thay thế thế nào qua các mức kế thừa trong Java Generics

## 1. Vấn đề cốt lõi

Khi một lớp generic được kế thừa, **tham số kiểu của lớp cha** có thể được điền bằng một kiểu cụ thể, bằng tham số kiểu của lớp con, hoặc bằng một kiểu tham số hóa phức tạp hơn. Trình biên dịch Java dùng quan hệ **extends** / **implements** để xác định kiểu tĩnh của những thành viên kế thừa tại mỗi mức.

Ví dụ đơn giản:

~~~java
class Parent<T> {
    protected T value;

    T get() {
        return value;
    }

    void set(T value) {
        this.value = value;
    }
}

class Child extends Parent<String> {}
~~~

Trong ngữ cảnh **Child**, các thành viên kế thừa được nhìn như:

- Field **value** có kiểu tĩnh **String** ở các biểu thức truy cập hợp lệ.
- Method **get()** có kiểu trả về **String**.
- Method **set(String value)** nhận String, không phải một Object tùy ý.

Đây là sự **thế đối số kiểu** (*type substitution*) theo khai báo **Child extends Parent<String>**. Parent<T> không phải được sao chép thành một class mới Parent<String> ở runtime; Java thực hiện việc kiểm tra và suy luận quan hệ kiểu khi biên dịch.

Bài học sẽ làm rõ:

1. Cách thay T bằng đối số kiểu ở một cấp kế thừa.
2. Cách kết hợp các phép thay thế khi đi qua **nhiều cấp**.
3. Vì sao một thành viên kế thừa có thể là **List<String>**, **Map<String, Integer>** thay vì chỉ String hay Integer.
4. Ảnh hưởng tới field, getter/setter, override, overloaded method và generic method riêng.
5. Kế thừa một phần tham số kiểu, đổi tên, đổi thứ tự tham số, giới hạn bound và triển khai interface.
6. Giới hạn của raw type, invariance, erasure, bridge method và cách đọc API cho đúng.

Tất cả chương trình hoàn chỉnh dưới đây dùng Java 17 trở lên. Các đoạn ghi “minh họa lỗi” không được biên dịch như chương trình chạy.

## 2. Phân biệt khai báo type parameter và sử dụng type argument

Trong đoạn:

~~~java
class Parent<T> {}
class Middle<U> extends Parent<U> {}
class Leaf extends Middle<String> {}
~~~

Ta có ba vị trí với ba ý nghĩa:

- **<T>** ngay sau Parent: Parent khai báo type parameter **T**.
- **<U>** ngay sau Middle: Middle khai báo type parameter **U** của riêng mình.
- **Parent<U>** trong **extends Parent<U>**: Middle dùng U làm **type argument** để lấp vào vị trí T của Parent.
- **Middle<String>** trong extends của Leaf: Leaf dùng **String** làm type argument để lấp vào U.

Khi đi từ Leaf lên Parent, ta thực hiện hai bước:

~~~text
Leaf extends Middle<String>
Middle<U> extends Parent<U>

Ở Leaf:
  U := String
  T := U := String

Suy ra Leaf kế thừa Parent<String>.
~~~

Việc T và U khác tên không ảnh hưởng kết quả. Tên type variable được khai báo ở từng cấp, còn điều quan trọng là **vị trí** và biểu thức type argument trong mệnh đề extends.

Đừng đọc **extends Parent<U>** như “Parent tự khai báo U” hoặc “U đổi tên thành T vĩnh viễn”. Đó chỉ là một quan hệ giữa hai khai báo generic. Parent vẫn có một type parameter riêng là T; Middle chọn một cách biểu diễn T thông qua U.

## 3. Thế kiểu ở một cấp: field và method thường

Xét:

~~~java
class Box<T> {
    protected T item;

    Box(T item) {
        this.item = item;
    }

    T get() {
        return item;
    }

    void replace(T value) {
        item = value;
    }
}

class StringBox extends Box<String> {
    StringBox(String value) {
        super(value);
    }

    void printUppercase() {
        System.out.println(get().toUpperCase());
    }
}
~~~

Khi compiler kiểm tra **StringBox**, nó biết Box được dùng với **T = String**. Vì thế get() trả String và có thể gọi **toUpperCase()** mà không cast. **replace(T)** được nhìn qua StringBox như method nhận String.

Constructor của Box cũng dùng T. Tại **super(value)** của StringBox, compiler kiểm tra tham số constructor theo kiểu String; tuy nhiên **constructor không được kế thừa**, nên StringBox phải tự khai báo constructor hoặc dựa vào một constructor khác hợp lệ.

Mã nguồn Box<T> chỉ được khai báo một lần. Java không cần tạo một phiên bản source riêng của Box cho từng kiểu. Khi tham chiếu qua **Box<String>**, phương thức get vẫn được kiểm tra có kiểu trả về String.

Không phải mọi thành viên được “thay” như nhau:

| Thành viên khai báo trong Box<T> | Nhìn từ StringBox kế thừa Box<String> |
| --- | --- |
| Field instance **T item** | Giá trị field có kiểu tĩnh String |
| Method instance **T get()** | Kiểu trả về String |
| Method instance **void replace(T)** | Tham số là String |
| Method **List<T> all()** | Kiểu trả về List<String> |
| Method **Map<String,T> map()** | Kiểu trả về Map<String,String> |
| Generic method **<R> R convert(Function<T,R>)** | T được thế thành String, R vẫn là type parameter của từng lời gọi method |
| Static method **static <U> U echo(U)** | U độc lập, không chịu tác động của T = String |

Một field **private** cũng có type được xác lập trong định nghĩa class cha, nhưng lớp con không được phép truy cập trực tiếp field ấy vì luật truy cập Java. Quan hệ thay kiểu và **quyền truy cập** là hai vấn đề khác nhau.

## 4. Nhiều mức kế thừa: phép thế kiểu được hợp thành

Đây là trường hợp thường gây khó hiểu:

~~~java
import java.util.List;

class Base<T> {
    protected final T data;

    Base(T data) {
        this.data = data;
    }

    T get() {
        return data;
    }
}

class Middle<U> extends Base<List<U>> {
    Middle(List<U> items) {
        super(items);
    }

    U first() {
        return get().get(0);
    }
}

class Final extends Middle<String> {
    Final(List<String> names) {
        super(names);
    }
}
~~~

Có ba cấp:

~~~text
Base<T>           : T
    ^
    | T := List<U>
Middle<U>         : U
    ^
    | U := String
Final             : không khai báo type parameter mới
~~~

Bước 1: **Middle<U> extends Base<List<U>>**. T của Base không phải U, mà là **List<U>**. Trong Middle, **get() trả List<U>**, và **data** mang kiểu List<U>.

Bước 2: **Final extends Middle<String>**. Ở Final, U của Middle được điền thành String.

Bước 3: Thế tiếp U vào biểu thức **List<U>**: kết quả **List<String>**. Vì thế Final có quan hệ kế thừa với **Base<List<String>>**, không phải Base<String>.

Bảng theo dõi:

| Thành viên | Trong Base<T> | Nhìn qua Middle<U> | Nhìn qua Final |
| --- | --- | --- | --- |
| **data** | T | List<U> | List<String> |
| **get()** | T | List<U> | List<String> |
| **first()** | Chưa có | U | String |
| **Middle(List<U>)** | Không thuộc Base | Constructor nhận List<U> | Constructor của Final gọi super với List<String> |

**Lưu ý:** Bảng mô tả kiểu tĩnh và hợp đồng source code. Đây không phải việc JVM thay type parameters trong field và method của một bản class runtime mới cho Final.

## 5. Ví dụ chạy độc lập: ba cấp, kiểu phần tử lồng nhau

Lưu thành **MultiLevelTypesDemo.java**:

~~~java
import java.util.List;

public class MultiLevelTypesDemo {
    static class Base<T> {
        private final T data;

        Base(T data) {
            this.data = data;
        }

        T get() {
            return data;
        }

        void show(T value) {
            System.out.println(value);
        }
    }

    static class Middle<U> extends Base<List<U>> {
        Middle(List<U> data) {
            super(data);
        }

        U first() {
            return get().get(0);
        }
    }

    static final class Final extends Middle<String> {
        Final(List<String> data) {
            super(data);
        }

        String upperFirst() {
            return first().toUpperCase();
        }
    }

    public static void main(String[] args) {
        Final child = new Final(List.of("java", "spring"));

        List<String> names = child.get();
        String first = child.first();
        Base<List<String>> parent = child;

        System.out.println(names);
        System.out.println(first);
        System.out.println(child.upperFirst());
        parent.show(List.of("typed"));
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 MultiLevelTypesDemo.java
java MultiLevelTypesDemo
~~~

Stdout chính xác:

~~~text
[java, spring]
java
JAVA
[typed]
~~~

Phân tích:

- **child.get()** trả List<String>, vì T của Base được thay bằng List<U>, rồi U được thay bằng String.
- **child.first()** trả String, vì first được khai báo trả U trong Middle<U>.
- **child.upperFirst()** gọi toUpperCase được vì compiler biết first() là String.
- **Base<List<String>> parent = child** hợp lệ: Final là subtype của Base<List<String>> qua hai tầng extends.
- **parent.show(List.of("typed"))** hợp lệ vì show(T) tại biến parent là show(List<String>).
- Biểu thức **Base<String> wrong = child** sẽ không biên dịch; Final không phải một Base<String>.

Đoạn demo dùng các lớp lồng static để gói chương trình trong một file. Từng class Base<T>, Middle<U>, Final vẫn có quan hệ kế thừa generic bình thường; static ở đây chỉ giải quyết quan hệ với lớp chương trình bao ngoài.

## 6. Cách tính phép thế kiểu một cách có hệ thống

Với chuỗi:

~~~java
class Root<A> {}
class Middle<B> extends Root<java.util.List<B>> {}
class Lower<C> extends Middle<java.util.Set<C>> {}
class Bottom extends Lower<String> {}
~~~

Hãy đi từ dưới lên và thế lần lượt:

~~~text
Bottom -> Lower<String>:
    C := String

Lower<C> -> Middle<Set<C>>:
    B := Set<C>
    sau C := String, B := Set<String>

Middle<B> -> Root<List<B>>:
    A := List<B>
    sau B := Set<String>, A := List<Set<String>>

Kết quả:
    Bottom là subtype của Root<List<Set<String>>>.
~~~

Phép thế diễn ra trên **biểu thức kiểu hoàn chỉnh**. Nếu type parameter nằm sâu trong List, Map hoặc Set, ta thay nó ở vị trí tương ứng rồi giữ nguyên phần vỏ kiểu.

Một cách ghi tổng quát:

~~~text
Root<A>
  Middle<B> extends Root<F(B)>
  Lower<C> extends Middle<G(C)>
  Bottom extends Lower<X>

Tại Bottom: A := F(G(X)).
~~~

F và G ở đây chỉ là ký hiệu mô tả “biểu thức kiểu” (ví dụ F(B) = List<B>, G(C) = Set<C>), **không phải cú pháp khai báo type constructor tổng quát trong Java**.

Với nhiều type parameters, hãy lập bảng riêng cho từng tên để tránh nhầm lẫn và ưu tiên đi theo mệnh đề extends thực tế thay vì đoán theo tên lớp.

## 7. Nhiều tham số kiểu và thay đổi thứ tự

Xét một lớp cha nhận hai tham số kiểu:

~~~java
class Pair<A, B> {
    A left;
    B right;

    Pair(A left, B right) {
        this.left = left;
        this.right = right;
    }

    A left() { return left; }
    B right() { return right; }
}

class Flipped<X, Y> extends Pair<Y, X> {
    Flipped(Y left, X right) {
        super(left, right);
    }
}

class Concrete extends Flipped<Integer, String> {
    Concrete(String left, Integer right) {
        super(left, right);
    }
}
~~~

Đọc chậm từng bước:

1. Flipped<X,Y> extends Pair<Y,X>: **A = Y**, **B = X**.
2. Concrete extends Flipped<Integer,String>: **X = Integer**, **Y = String**.
3. Ghép hai bước: **A = String**, **B = Integer**.
4. Concrete vì thế có quan hệ subtype với **Pair<String,Integer>**.

Khi đọc thành viên kế thừa qua Concrete:

- **left()** trả String.
- **right()** trả Integer.
- **left** là String, **right** là Integer (tùy quyền truy cập).
- Constructor Concrete nhận String trước, Integer sau do chính chữ ký đã khai báo; nó không tự kế thừa constructor của Pair.

Không được suy ra rằng Concrete là Pair<Integer,String> chỉ vì Concrete kế thừa Flipped<Integer,String>. **Mệnh đề extends Pair<Y,X> đã đảo hai vị trí**.

Một lớp con cũng có thể **giữ linh hoạt một tham số và cố định tham số kia**:

~~~java
class KeyValue<K, V> {
    K key;
    V value;
}

class StringKeyValue<V> extends KeyValue<String, V> {}
class LongStringValue extends StringKeyValue<String> {}
~~~

Ở StringKeyValue<V>: K = String, V còn tự do. Ở LongStringValue: V = String, suy ra cả K và V của KeyValue đều là String. Tên LongStringValue chỉ là tên ví dụ; việc tham số hóa thực tế phải được suy từ extends, **không phải từ tên class**.

## 8. Ví dụ chạy: hai tham số kiểu qua lớp trung gian

Lưu thành **PermutationDemo.java**:

~~~java
public class PermutationDemo {
    static class Pair<A, B> {
        private final A left;
        private final B right;

        Pair(A left, B right) {
            this.left = left;
            this.right = right;
        }

        A left() { return left; }
        B right() { return right; }
    }

    static class Swapped<X, Y> extends Pair<Y, X> {
        Swapped(Y left, X right) {
            super(left, right);
        }
    }

    static final class Fixed extends Swapped<Integer, String> {
        Fixed(String name, Integer score) {
            super(name, score);
        }
    }

    public static void main(String[] args) {
        Fixed item = new Fixed("Alice", 91);
        Pair<String, Integer> parent = item;

        String name = parent.left();
        Integer score = parent.right();

        System.out.println(name);
        System.out.println(score);
        System.out.println(parent.left() + ":" + parent.right());
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 PermutationDemo.java
java PermutationDemo
~~~

Stdout:

~~~text
Alice
91
Alice:91
~~~

**Fixed extends Swapped<Integer,String>**, còn Swapped<X,Y> extends Pair<Y,X>. Do đó A = String, B = Integer. Phép gán **Pair<String,Integer> parent = item** được kiểm tra tại thời gian biên dịch và không cần ép kiểu.

## 9. Phương thức nhận tham số kiểu của cha cũng được thay thế

Giả sử lớp cha không chỉ trả T mà còn nhận T:

~~~java
class Repository<T> {
    private T current;

    void save(T item) {
        current = item;
    }

    T load() {
        return current;
    }
}

class TextRepository extends Repository<String> {}
~~~

Trong ngữ cảnh TextRepository:

~~~java
TextRepository repo = new TextRepository();
repo.save("ok");
String value = repo.load();
~~~

Compiler xem **save** nhận String, **load** trả String. Nếu viết **repo.save(123)**, code sai kiểu tại compile time.

Với lớp trung gian:

~~~java
class ListRepository<E> extends Repository<java.util.List<E>> {}
class NameRepository extends ListRepository<String> {}
~~~

Tại NameRepository, **save** nhận List<String> và **load** trả List<String>. Nó không nhận trực tiếp String vì T của Repository được điền bằng **toàn bộ List<E>**.

Cần phân biệt **kiểu tham số phương thức** với **giá trị runtime**. Nếu save chấp nhận một List<String>, list đó vẫn có thể mutable hoặc chứa null tùy implementation. Generic substitution không tự tạo invariant “list không rỗng”, “không null” hay “bất biến”.

## 10. Override: chữ ký inherited phải được nhìn sau phép thế

Khi lớp con override một method, Java kiểm tra hợp đồng dựa trên kiểu của generic superclass sau khi áp dụng type arguments.

~~~java
abstract class Provider<T> {
    abstract T provide();
}

class StringProvider extends Provider<String> {
    @Override
    String provide() {
        return "ready";
    }
}
~~~

Provider<T>.provide() có kiểu trả T. Với StringProvider extends Provider<String>, method cần triển khai trả String hoặc một return type tương thích theo luật override.

Một ví dụ đa tầng:

~~~java
abstract class Base<T> {
    abstract T create();
}

abstract class Middle<U> extends Base<java.util.List<U>> {}

class Final extends Middle<String> {
    @Override
    java.util.List<String> create() {
        return java.util.List.of("ok");
    }
}
~~~

Final phải trả **List<String>**, vì T của Base được thế thành List<U>, U thành String. Nếu viết **String create()**, method không override đúng hợp đồng và không thể dùng để triển khai abstract method.

### Covariant return type

Khi method của superclass sau phép thế trả một reference type rộng, override có thể trả subtype phù hợp:

~~~java
abstract class NumberProvider<T extends Number> {
    abstract T get();
}

class IntegerProvider extends NumberProvider<Number> {
    @Override
    Integer get() {
        return 10;
    }
}
~~~

Ở IntegerProvider, T của NumberProvider được chọn là Number; **Integer** là subtype của Number nên kiểu trả về Integer là covariant và hợp lệ.

Nhưng **List<Integer>** không là subtype của **List<Number>**, do generic invariance. Vì vậy không thể chỉ dựa vào quan hệ Integer extends Number để đổi kiểu trả về **List<Number>** thành **List<Integer>** khi override.

### Mức truy cập và checked exceptions

Lớp con không được giảm access level của một method được override. Nếu method trong interface là public, implementation phải public. Với method của class, mức truy cập và checked exceptions cũng phải tuân theo luật Java thông thường. Generic substitution chỉ thay type variables trong chữ ký; nó không bỏ qua các luật override khác.

## 11. Phân biệt override với overload và field hiding

Hai phương thức trùng tên chưa chắc override nhau.

~~~java
class Base<T> {
    void set(T value) {
        System.out.println("base");
    }
}

class TextChild extends Base<String> {
    void set(Integer value) {
        System.out.println("integer");
    }
}
~~~

Trong TextChild có **set(String)** được kế thừa qua Base<String> và **set(Integer)** do TextChild khai báo. Đây là **overloading**: hai signatures nhận kiểu khác nhau.

Nếu TextChild muốn override method nhận String, viết:

~~~java
class TextChild extends Base<String> {
    @Override
    void set(String value) {
        System.out.println("string");
    }
}
~~~

Dùng @Override giúp compiler kiểm tra chủ định. Trong các trường hợp có type erasure và name clash, một overload tưởng hợp lệ còn có thể dẫn đến lỗi nếu hai declarations có cùng erasure; không nên chỉ dựa vào tên biến hoặc cảm giác “khác generic type arguments” để đoán.

**Field hiding** lại là chuyện khác. Nếu lớp con khai báo field cùng tên với field ở cha, Java có thể có **hai field khác nhau** và phép truy cập field được giải quyết theo kiểu tĩnh của biểu thức, không dùng dynamic dispatch như instance method. Generic substitution không biến field hiding thành overriding.

Ví dụ:

~~~java
class Parent<T> {
    T value;
}

class Child extends Parent<String> {
    Integer value;
}
~~~

Child có field value kiểu Integer riêng, còn **((Parent<String>) child).value** truy cập field của Parent có kiểu String. Thiết kế field hiding thường gây nhầm, nên ưu tiên tên khác hoặc đóng gói bằng getter/setter.

## 12. Generic method của lớp cha có scope riêng

Một phương thức có thể tự khai báo type parameter **R**, độc lập với T của class:

~~~java
import java.util.function.Function;

class Box<T> {
    private final T item;

    Box(T item) {
        this.item = item;
    }

    <R> R map(Function<? super T, ? extends R> mapper) {
        return mapper.apply(item);
    }
}

class StringBox extends Box<String> {
    StringBox(String value) {
        super(value);
    }
}
~~~

Ở StringBox, compiler thay T thành String trong method đã kế thừa. Tuy nhiên **R không bị thế thành String**; R vẫn do **mỗi lời gọi map** xác định.

Qua StringBox, chữ ký logic của map là:

~~~text
<R> R map(Function<? super String, ? extends R> mapper)
~~~

Ví dụ:

~~~java
// Minh họa trong một phương thức:
StringBox box = new StringBox("Java");
Integer length = box.map(String::length);
String upper = box.map(String::toUpperCase);
~~~

Lần đầu R được suy luận Integer; lần sau R là String. Đây là điểm phân biệt:

- **T** thuộc class Box<T>, nên khi StringBox extends Box<String>, T đã được xác định.
- **R** thuộc generic method map, nên mỗi lời gọi vẫn tự chọn R.

Một generic method của lớp cha như **<X> X identity(X input)** không liên quan T và vẫn giữ nguyên khả năng chấp nhận nhiều X qua mọi lớp con. Type arguments của class không “thay tất cả dấu <...> xuất hiện trong class cha”.

## 13. Ví dụ chạy: method-level type parameter vẫn độc lập

Lưu thành **InheritedGenericMethodDemo.java**:

~~~java
import java.util.function.Function;

public class InheritedGenericMethodDemo {
    static class Box<T> {
        private final T item;

        Box(T item) {
            this.item = item;
        }

        <R> R map(Function<? super T, ? extends R> mapper) {
            return mapper.apply(item);
        }

        T value() {
            return item;
        }
    }

    static class WordBox extends Box<String> {
        WordBox(String word) {
            super(word);
        }
    }

    public static void main(String[] args) {
        WordBox box = new WordBox("Java");

        Integer length = box.map(String::length);
        String uppercase = box.map(String::toUpperCase);
        String original = box.value();

        System.out.println(length);
        System.out.println(uppercase);
        System.out.println(original);
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 InheritedGenericMethodDemo.java
java InheritedGenericMethodDemo
~~~

Stdout:

~~~text
4
JAVA
Java
~~~

Quan hệ kiểu: từ WordBox extends Box<String>, T được thế bằng String trong **value()** và phần đầu vào Function của **map**. R vẫn độc lập, có thể là Integer hoặc String tùy mapper. Cả ba biến được gán trực tiếp, không cần cast.

## 14. Interface generic qua nhiều cấp extends/implements

Không chỉ các lớp cha mới tham gia phép thế. Generic interface cũng có thể được tham số hóa xuyên nhiều tầng.

~~~java
interface Source<T> {
    T fetch();
}

interface SequenceSource<E> extends Source<java.util.List<E>> {}

abstract class AbstractSequence<U> implements SequenceSource<U> {}

class StringSequence extends AbstractSequence<String> {
    @Override
    public java.util.List<String> fetch() {
        return java.util.List.of("a", "b");
    }
}
~~~

Lần theo đường đi:

~~~text
StringSequence
  extends AbstractSequence<String>
  implements SequenceSource<String>
  extends Source<List<String>>
~~~

Method fetch được khai báo trong Source<T> trả T. Ở StringSequence, kết quả trở thành **List<String>**. Việc implementation nằm trong class cuối cùng không làm thay đổi hợp đồng của interface đã kế thừa.

Thay thế qua interface với nhiều type parameters có thể phức tạp hơn:

~~~java
interface Transformer<I, O> {
    O apply(I input);
}

interface TextTransformer<T> extends Transformer<T, String> {}

class NumberFormatter implements TextTransformer<Integer> {
    @Override
    public String apply(Integer input) {
        return "n=" + input;
    }
}
~~~

Ở NumberFormatter, T của TextTransformer được thế bằng Integer. Interface cha trở thành Transformer<Integer,String>; vì vậy method apply nhận Integer và trả String.

Nơi gọi có thể dùng:

~~~java
Transformer<Integer, String> converter = new NumberFormatter();
String text = converter.apply(5);
~~~

Không cast vì quan hệ subtype và method signature đã được compiler kiểm tra.

## 15. Tính bất biến: subtype class không đồng nghĩa subtype type arguments

Xét:

~~~java
class Holder<T> {}
class NumberHolder extends Holder<Integer> {}
~~~

Vì NumberHolder extends Holder<Integer>, các phép gán sau đúng:

~~~java
NumberHolder direct = new NumberHolder();
Holder<Integer> asIntegerHolder = direct;
Holder<? extends Number> asNumberReader = direct;
~~~

Nhưng:

~~~java
// Cố ý sai:
// Holder<Number> asNumberHolder = direct;
~~~

**Holder<Integer> không phải subtype của Holder<Number>**. Dù Integer extends Number, type arguments của những generic classes như Holder mặc định **invariant**.

Một trường hợp nhiều cấp:

~~~java
class Root<T> {}
class Mid<U> extends Root<java.util.List<U>> {}
class Leaf extends Mid<Integer> {}
~~~

Leaf là subtype của **Root<List<Integer>>**, không phải **Root<List<Number>>** hay **Root<Collection<Integer>>** chỉ nhờ quan hệ subtype giữa kiểu bên trong.

Nếu API cần linh hoạt ở *nơi sử dụng*, có thể dùng bounded wildcard, ví dụ **Root<? extends List<? extends Number>>** phù hợp với một Root<List<Integer>> ở nhiều tình huống. Tuy nhiên, khi đọc/ghi qua các wildcard, quyền thao tác có thể bị giới hạn. Không nên thay biểu thức extends thực tế bằng supertype rộng rồi giả định mọi phép ghi vẫn hợp lệ.

## 16. Bounds vẫn phải thỏa qua mỗi cấp

Một generic superclass có thể giới hạn type parameter:

~~~java
class NumericBox<T extends Number> {
    protected final T value;

    NumericBox(T value) {
        this.value = value;
    }

    double amount() {
        return value.doubleValue();
    }
}
~~~

Subclass generic phải cung cấp một type argument chắc chắn là subtype của Number:

~~~java
class NumericMiddle<U extends Number> extends NumericBox<U> {
    NumericMiddle(U value) {
        super(value);
    }
}

class IntegerBox extends NumericMiddle<Integer> {
    IntegerBox(Integer value) {
        super(value);
    }
}
~~~

Nếu viết **class Invalid<U> extends NumericBox<U>**, compiler báo lỗi vì U không bound không được bảo đảm là Number. Bound của class cha được kiểm tra tại điểm sử dụng type argument trong extends.

Đôi khi type argument là một kiểu cụ thể luôn đáp ứng bound, nên lớp con không cần khai báo cùng bound:

~~~java
class FixedNumeric<X> extends NumericBox<Integer> {
    FixedNumeric(Integer value) {
        super(value);
    }
}
~~~

Ở FixedNumeric<X>, X độc lập và không tham gia extends; việc X không có bound không ảnh hưởng NumericBox<Integer>. Tuy nhiên khai báo X không được dùng ở đâu sẽ gây rối thiết kế nếu không có mục đích thật.

### Bound liên quan nhiều type parameters

~~~java
class OrderedPair<T extends Comparable<? super T>> {
    T left;
    T right;
}

class TextPair extends OrderedPair<String> {}
~~~

String đáp ứng bound Comparable<? super String>, nên TextPair hợp lệ. Khi mở rộng class generic có các bound phức tạp, hãy kiểm tra **toàn bộ type argument** thay vì chỉ nhìn tên T: các dạng Number, Comparable<? super T>, InterfaceA & InterfaceB có thể giới hạn những cách thay hợp lệ.

Bounds không loại trừ null. Nếu NumericBox<Integer> giữ null, **amount()** có thể ném NullPointerException. Đây là vấn đề giá trị runtime, không phải sai phép thế kiểu.

## 17. Static members không mang type parameter của instance

Type parameter của class cha gắn với phần khai báo generic nhưng không được dùng như một kiểu ở static context của chính class đó.

~~~java
class Base<T> {
    static int instanceCount;

    // static T last; // Không hợp lệ.
    static <U> U echo(U value) {
        return value;
    }
}

class Child extends Base<String> {}
~~~

**Base<String>** và **Base<Integer>** không có hai phiên bản static state riêng. Child kế thừa quan hệ từ Base<String>, nhưng một static field của Base vẫn thuộc Base chung, không được thay kiểu T theo mỗi subtype.

Phương thức **static <U> U echo(U value)** khai báo U riêng của method. Khi gọi **Base.echo("x")** hoặc **Child.echo(1)**, U được suy luận độc lập từ argument, không bị khóa thành String chỉ vì Child extends Base<String>.

Static methods bị **hiding**, không phải overriding động như instance methods. Không nên dùng việc tham số hóa superclass để suy đoán một static method được chuyên biệt theo T.

## 18. Constructor, private member và phần nào thực sự được kế thừa

Mô hình “mọi thứ thuộc cha đều bị thay kiểu” là không chính xác. Khi phân tích generics, cần kết hợp luật kế thừa thông thường:

- **Constructor không được kế thừa**. Lớp con khai báo constructor của mình và dùng super(...) phù hợp.
- Field/method private của superclass không tự trở thành các thành viên truy cập trực tiếp trong subclass. Chúng vẫn tồn tại trong class cha và có thể được gọi gián tiếp qua API public/protected phù hợp.
- Một method không truy cập được vì access modifier sẽ không trở nên truy cập được chỉ nhờ type argument được xác định.
- Instance method được override có dynamic dispatch; field access không có dynamic dispatch giống method.
- Static fields/methods thuộc class, không thuộc một cách tham số hóa riêng T.

Ví dụ:

~~~java
class Base<T> {
    private final T secret;

    Base(T secret) {
        this.secret = secret;
    }

    public T reveal() {
        return secret;
    }
}

class Child extends Base<String> {
    Child(String text) {
        super(text);
    }

    String readSecret() {
        // return secret; // Không hợp lệ: private trong Base.
        return reveal();  // Hợp lệ: inherited public method trả String.
    }
}
~~~

Đúng là phép thế cho biết **secret** trong Base<String> mang kiểu String và **reveal()** trả String. Nhưng Child không được đọc field secret trực tiếp. Đó là giới hạn access control, không liên quan đến sai type substitution.

## 19. Type erasure và bridge method: sự khác nhau giữa nguồn và bytecode

Ở Java source, khi viết:

~~~java
class Base<T> {
    T value() { return null; }
}

class StringBase extends Base<String> {
    @Override
    String value() { return "ok"; }
}
~~~

Compiler hiểu StringBase override method trả String của Base<String>. Nhưng **type erasure** thường thay type variable T không bound bằng Object trong chữ ký bytecode của Base.

Để giữ khả năng dispatch của JVM và hợp đồng override sau erasure, compiler có thể tạo một **bridge method** ở StringBase, đại ý có chữ ký trả Object rồi ủy quyền tới method trả String. Bridge method được tạo tự động; người viết Java không nên tự khai báo method trùng chữ ký bị erase.

Điều này giải thích hai điều cùng đúng:

1. Ở Java source, **String s = new StringBase().value()** hợp lệ mà không có cast thủ công.
2. Runtime **không tạo một class Base<String> riêng** với method value() thực sự trả String ở mọi vị trí bytecode.

Nếu trường hợp có bridge method, bạn có thể quan sát bằng công cụ **javap -c -p** trên file class đã biên dịch. Tên/chữ ký bridge cụ thể là chi tiết triển khai, không nên dựa vào để viết logic ứng dụng.

### Một cảnh báo về overload và erasure

Hai method như **void accept(List<String>)** và **void accept(List<Integer>)** không thể cùng tồn tại như hai overload riêng trong một class vì chúng có cùng erasure. Kế thừa generic nhiều cấp cũng có thể dẫn đến **name clash** khi một subclass khai báo method tưởng như khác kiểu nhưng sau erasure xung đột với inherited member.

Không dùng raw type hay ép kiểu unchecked để “sửa” một name clash. Hãy xác định rõ contract cần override, điều chỉnh signatures phù hợp hoặc chọn tên method khác khi đó thực sự là hai thao tác khác nghĩa.

## 20. Raw type làm mất độ chính xác của phép thế

Với:

~~~java
class Base<T> {
    T get() { return null; }
}

class Good extends Base<String> {}
class Legacy extends Base {}
~~~

Good kế thừa Base<String>, nên **Good.get()** được nhìn từ source là String. Legacy mở rộng **raw Base**; thông tin type argument đã bị bỏ, nên get() thường được nhìn qua chữ ký đã erase là Object.

~~~java
Good good = new Good();
String text = good.get();

Legacy legacy = new Legacy();
Object rawValue = legacy.get();
~~~

Khi cast rawValue sang String, bạn tự chịu rủi ro runtime. Raw inheritance thường có từ code Java cũ trước generics hoặc những API chưa được cập nhật. Trong code mới, nên dùng type arguments đầy đủ.

**Raw type không tương đương wildcard**. Ví dụ Base<?> vẫn là parameterized type với kiểu thành phần chưa xác định, và compiler áp đặt kiểm tra an toàn kiểu; Base raw bỏ qua nhiều kiểm tra. Nếu không biết đối số kiểu, hãy cân nhắc wildcard ở vị trí tham chiếu thích hợp, nhưng mệnh đề extends của một class cần một supertype hợp lệ theo luật Java, không dùng wildcard trực tiếp như **extends Base<?>**.

## 21. Type inference trong chuỗi generic inheritance

Compiler có thể suy luận type arguments của constructors và methods nhờ ngữ cảnh, nhưng **không tự biến một lớp con thành subtype của mọi cách tham số hóa có vẻ tương thích**.

~~~java
class Parent<T> {
    Parent(T value) {}
}

class Child<U> extends Parent<java.util.List<U>> {
    Child(java.util.List<U> values) {
        super(values);
    }
}
~~~

Caller có thể viết:

~~~java
Child<String> child = new Child<>(java.util.List.of("x", "y"));
Parent<java.util.List<String>> parent = child;
~~~

Diamond ở **new Child<>(...)** suy luận U = String từ tham số constructor và kiểu đích. Sau đó quan hệ extends cho biết T của Parent bằng List<U>, tức List<String>.

Nếu dùng **var child = new Child<>(List.of("x"))** trong ngữ cảnh đủ rõ, compiler vẫn suy luận từ constructor argument và không mất type safety chỉ vì var. Tuy nhiên type inference không thay đổi khai báo extends và không chữa được việc truyền sai type arguments.

Cần phân biệt **type inference tại nơi gọi** với **type substitution khi kế thừa**:

- Inference chọn type arguments phù hợp cho một generic constructor/method theo ngữ cảnh.
- Substitution áp dụng các type arguments đã chọn qua những mệnh đề extends/implements để xác định member types của supertypes.

Hai bước cùng tham gia kiểm tra kiểu, nhưng không phải cùng một cơ chế.

## 22. Sai lầm hay gặp

### Lỗi 1: Thấy Child extends Middle<String> rồi cho rằng Base<T> có T = String

Nếu **Middle<U> extends Base<List<U>>**, T phải là List<String>, không phải String. Luôn thế qua đầy đủ từng mệnh đề extends.

### Lỗi 2: Đổi tên type parameter rồi cho rằng kiểu khác đi

~~~java
class Base<T> {}
class Mid<U> extends Base<U> {}
~~~

Tên T và U khác nhau nhưng quan hệ là T := U. Đổi tên chỉ ảnh hưởng cách đọc source; không có chuyển đổi giá trị runtime nào diễn ra.

### Lỗi 3: Nghĩ rằng List<Integer> là List<Number>

Generic types thông thường invariant. Một lớp extends Base<List<Integer>> không đồng thời extends Base<List<Number>> chỉ vì Integer extends Number.

### Lỗi 4: Override với kiểu sai sau phép thế

~~~java
abstract class Base<T> {
    abstract T read();
}

class Wrong extends Base<String> {
    // String mới là kiểu cần trả:
    // @Override Integer read() { return 1; } // Sai.
    @Override String read() { return "ok"; }
}
~~~

Kiểu trả Integer không tương thích với String mà hợp đồng Base<String> yêu cầu.

### Lỗi 5: Cố dùng một tham số generic method như thể đã được class thay

Với **<R> R map(Function<T,R>)**, chỉ T bị thế qua class inheritance; R là một type parameter khác thuộc method. Phần R vẫn được caller xác định.

### Lỗi 6: Dùng constructor của superclass như constructor được kế thừa

Constructor không được kế thừa. Dù superclass khai báo Base(T), subclass vẫn cần constructor đúng và gọi **super(...)** thích hợp khi cần.

### Lỗi 7: Dùng private field từ subclass

Thế kiểu chỉ xác định kiểu tĩnh. Nó không vượt qua private access; gọi getter hợp lệ hoặc chỉnh API theo thiết kế đóng gói.

### Lỗi 8: Dùng raw Base thay cho Base<String>

Raw type xóa nhiều thông tin generic ở source và đưa kết quả quay lại Object/erasure. Dùng một parameterized supertype đầy đủ nếu biết kiểu.

### Lỗi 9: Trông đợi generic static field phân chia theo T

Static fields không thuộc riêng mỗi type argument. Một Base<Integer> và Base<String> không có static fields được chuyên biệt tự động theo T.

### Lỗi 10: Nhầm field hiding với method override

Method instance có thể override và dispatch động; field cùng tên ở lớp con che field lớp cha nhưng không override. Kiểu tĩnh của expression quyết định field nào được truy cập.

### Lỗi 11: Cho rằng mọi member đều được kế thừa trực tiếp

Constructors và private members không thuộc cùng tập inherited accessible members như public/protected methods. Luật kế thừa và access modifiers vẫn áp dụng ngoài generics.

### Lỗi 12: Dùng cast không kiểm tra để giả mạo supertype

Một **Base<List<Integer>>** không thể được xem an toàn thành **Base<List<String>>** chỉ vì cùng class Base sau erasure. Cast không đúng có thể dẫn tới ClassCastException khi đọc dữ liệu. Hãy sửa type relationships thay vì che lỗi.

## 23. Phương pháp đọc một hierarchy thực tế

Khi gặp một chuỗi kế thừa chưa quen, làm theo trình tự:

1. **Tìm generic declaration gốc.** Ghi tên type parameters của class hoặc interface có member đang quan tâm, ví dụ Base<T> với T get().
2. **Đọc mệnh đề extends/implements tại cấp ngay dưới.** Ghi chính xác type argument đi vào từng vị trí, kể cả List<U>, Map<K,V> hay một parameterized type lồng sâu.
3. **Lặp ở các cấp tiếp theo.** Thay type variables bên trong biểu thức kiểu đã ghi bằng type arguments của cấp dưới.
4. **Không bỏ mất các lớp bọc generic.** Nếu T = List<U>, sau khi U = String thì T = List<String>, không phải String.
5. **Xác định member được kế thừa hay override.** Kiểm tra private, static, constructors và access levels; đừng tưởng mọi thành viên đều dispatch giống nhau.
6. **Nếu method có <R>, ghi riêng R.** Các type parameters của method có scope và inference riêng.
7. **Kiểm tra bounds và invariance.** Một mệnh đề extends phải thỏa bound; List<Integer> không tự đổi thành List<Number>.
8. **Kiểm tra output bằng kiểu tham chiếu hợp lệ.** Thử khai báo Base<CorrectType> parent = child để compiler xác nhận kết quả suy luận.
9. **Xem erasure khi thật cần.** Nếu gặp name clash hoặc bridge method, nhớ source type checking và bytecode erasure là hai lớp khác nhau.
10. **Ưu tiên type arguments tường minh trong tài liệu.** Một bảng thế kiểu thường dễ hiểu hơn một chuỗi type declarations dài không được chú giải.

Ví dụ bài toán:

~~~java
class Root<T> {
    T read() { return null; }
}

class Level1<A> extends Root<java.util.Map<String, A>> {}

class Level2<B> extends Level1<java.util.List<B>> {}

class Final extends Level2<Integer> {}
~~~

Bảng:

| Cấp | Kiểu tham số được điền |
| --- | --- |
| Level2<Integer> | B = Integer |
| Level1<List<B>> | A = List<Integer> |
| Root<Map<String,A>> | T = Map<String,List<Integer>> |

Suy ra **Final.read()** có kiểu tĩnh **Map<String,List<Integer>>**. Không có bất kỳ phép cast hay chuyển đổi dữ liệu nào trong quá trình thế này.

## 24. Câu hỏi tự kiểm tra

**Câu 1.** Base<T> khai báo T get(); Middle<U> extends Base<List<U>>; Leaf extends Middle<String>. Kiểu get() ở Leaf là gì?

**Đáp án:** List<String>. Thế T = List<U>, tiếp theo U = String.

**Câu 2.** Vì sao **Leaf** ở câu trên không tự là Base<String>?

**Đáp án:** Mệnh đề extends trung gian đã đặt List<U> vào T của Base; cuối cùng T phải là List<String>, không phải String.

**Câu 3.** Pair<A,B>, Swapped<X,Y> extends Pair<Y,X>, Fixed extends Swapped<Integer,String>: left() và right() trả kiểu gì?

**Đáp án:** left() trả String, right() trả Integer; vì A = Y = String, B = X = Integer.

**Câu 4.** Với Repository<T>.save(T), lớp NameRepo extends Repository<List<String>> nhận tham số gì ở save?

**Đáp án:** List<String>, không phải String. Phép thế áp dụng toàn bộ biểu thức kiểu của T.

**Câu 5.** Generic method của cha **<R> R map(Function<T,R>)** được dùng từ subclass extends Base<String>. Có phải R thành String không?

**Đáp án:** Không. Chỉ T được cố định thành String; R vẫn do generic method và từng lời gọi quyết định.

**Câu 6.** Lớp con extends Provider<Number> có được override Number get() bằng Integer get() không?

**Đáp án:** Có, nếu các điều kiện override khác cũng thỏa: Integer là subtype của Number và return type covariant hợp lệ.

**Câu 7.** Tại sao không được override method trả List<Number> bằng method trả List<Integer> chỉ vì Integer extends Number?

**Đáp án:** List<Integer> không là subtype của List<Number> do invariance.

**Câu 8.** Constructor của Base<T> được tự động kế thừa bởi Child extends Base<String> không?

**Đáp án:** Không. Child phải có constructor phù hợp và gọi super(...) khi cần theo luật khởi tạo của Java.

**Câu 9.** Static method <U> U echo(U x) trong Base<T> có bị cố định thành U = String khi gọi qua Child extends Base<String> không?

**Đáp án:** Không. U là type parameter riêng của static method; T của Base không dùng trong static context theo cách đó.

**Câu 10.** Raw subclass **class Legacy extends Base** có giữ kết quả T get() được chuyên biệt thành String không?

**Đáp án:** Không. Raw type bỏ type arguments; với T không bound, kiểu sau erasure thường là Object, và an toàn kiểu giảm.

**Câu 11.** Nếu nhiều cấp extends/implements dẫn tới interface Source<List<Integer>>, một tham chiếu Source<List<Number>> có tự gán từ đối tượng đó không?

**Đáp án:** Không, vì List<Integer> và List<Number> là parameterized types khác nhau và generic invariance áp dụng qua các cấp.

**Câu 12.** Khi compiler sinh bridge method cho một override generic, có nghĩa Java tạo một runtime class Base<String> mới không?

**Đáp án:** Không. Bridge hỗ trợ dispatch sau erasure; nó không tạo một bản runtime class riêng cho từng type argument.

## 25. Ghi nhớ cốt lõi

Để biết kiểu của thành viên kế thừa, **không đoán từ tên lớp con**. Hãy đi theo đúng từng mệnh đề extends/implements, thay type arguments ở mỗi cấp và ghép các phép thế theo thứ tự. Nếu **Middle<U> extends Base<List<U>>** và **Final extends Middle<String>**, thì **Base<T>** được nhìn qua Final với **T = List<String>**; vì vậy field T, method T get() và method nhận T đều dùng List<String> trong những ngữ cảnh hợp lệ.

Những type parameters của generic method có scope riêng, static members không gắn với mỗi T, constructors không được kế thừa, private members không tự truy cập được, và erasure không xóa khả năng kiểm tra kiểu tại source code. Tách biệt rõ **phép thế kiểu**, **luật kế thừa/override** và **biểu diễn bytecode** là chìa khóa đọc đúng những hierarchy generic nhiều tầng.
