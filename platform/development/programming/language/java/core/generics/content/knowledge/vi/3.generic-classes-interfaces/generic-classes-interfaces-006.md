# Triển khai giao diện bằng tham số kiểu của lớp trong Java Generics

## 1. Mục tiêu

Java cho phép **generic class** truyền các tham số kiểu do chính lớp khai báo vào **generic interface** mà nó triển khai. Cơ chế này kết nối hợp đồng của interface với cách dùng lớp ở từng kiểu cụ thể: khi một class được dùng như Implementation<String>, compiler biết nó cũng thực hiện Interface<String> nếu lớp khai báo đúng mối quan hệ.

Ví dụ nền tảng:

~~~java
interface Store<T> {
    void save(T value);
    T load();
}

class MemoryStore<E> implements Store<E> {
    private E item;

    @Override
    public void save(E value) {
        item = value;
    }

    @Override
    public E load() {
        return item;
    }
}
~~~

Trong **MemoryStore<E>**, E là *type parameter* được lớp khai báo. Trong **implements Store<E>**, E là *type argument* lấy từ tham số kiểu của lớp để điền vào vị trí T của Store<T>. Hai vị trí này dùng cùng một tên E nhưng đảm nhận vai trò cú pháp khác nhau. **implements không tạo thêm tham số kiểu mới**.

Sau bài này, bạn cần giải thích và vận dụng được cách chuyển tiếp một hoặc nhiều tham số kiểu qua implements, viết @Override đúng chữ ký, triển khai interface bằng kiểu cố định hoặc kiểu hỗn hợp, giữ quan hệ generic qua extends, xử lý bounds và tránh raw type, wildcard không hợp lệ cùng xung đột do type erasure.

## 2. Mẫu cú pháp và phạm vi của tham số kiểu

Cú pháp thường gặp:

~~~java
interface Contract<T> {
    T process(T input);
}

class GenericImplementation<U> implements Contract<U> {
    @Override
    public U process(U input) {
        return input;
    }
}
~~~

Diễn giải theo thứ tự:

1. **interface Contract<T>** khai báo một type parameter T của interface, dùng nó cho tham số input và kết quả.
2. **class GenericImplementation<U>** khai báo một type parameter U mới, thuộc phạm vi lớp triển khai.
3. **implements Contract<U>** áp dụng U cho vị trí tham số kiểu T mà Contract khai báo. Mỗi trường hợp sử dụng GenericImplementation<String> đồng thời thỏa Contract<String>.
4. **public U process(U input)** triển khai hợp đồng phương thức sau phép thay thế type argument; cả đầu vào lẫn đầu ra vẫn giữ cùng U.
5. **@Override** buộc compiler kiểm tra rằng phương thức thật sự override một phương thức của supertype; nếu sai tên, tham số hoặc quan hệ kiểu, lỗi được phát hiện khi biên dịch.

Không có yêu cầu tên tham số kiểu ở class và interface phải giống nhau: **Store<T>** và **MemoryStore<E>** sử dụng hai tên khác nhau nhưng được kết nối ở **Store<E>**. Bạn cũng có thể dùng **class MemoryStore<T> implements Store<T>** nếu thấy dễ đọc hơn.

Một cách biểu đạt tổng quát:

~~~text
interface InterfaceName<P> { ... }

class ClassName<Q> implements InterfaceName<Q> {
    // Các method được triển khai theo Q.
}
~~~

Dấu **<Q>** sau ClassName là *nơi khai báo*; dấu **<Q>** sau InterfaceName là *nơi sử dụng*. Với nhiều kiểu:

~~~text
class ClassName<K, V> implements InterfaceName<K, V> { ... }
~~~

Dấu phẩy tách các type parameters độc lập. Từng type argument trong implements phải hợp lệ với vị trí và bounds tương ứng của interface.

## 3. Ví dụ chạy độc lập: truyền tham số kiểu của lớp vào interface

Lưu vào **GenericImplementationDemo.java**:

~~~java
public class GenericImplementationDemo {
    interface Store<T> {
        void save(T value);
        T load();
    }

    static final class MemoryStore<E> implements Store<E> {
        private E item;

        @Override
        public void save(E value) {
            item = value;
        }

        @Override
        public E load() {
            return item;
        }
    }

    interface Converter<I, O> {
        O convert(I input);
    }

    static final class LabelConverter<T>
            implements Converter<T, String> {
        @Override
        public String convert(T input) {
            return "value=" + input;
        }
    }

    public static void main(String[] args) {
        Store<String> words = new MemoryStore<>();
        words.save("Java");
        System.out.println(words.load());

        Store<Integer> score = new MemoryStore<>();
        score.save(42);
        System.out.println(score.load());

        Converter<Integer, String> converter = new LabelConverter<>();
        System.out.println(converter.convert(score.load()));
    }
}
~~~

Biên dịch và chạy với JDK 17+:

~~~bash
javac -encoding UTF-8 GenericImplementationDemo.java
java GenericImplementationDemo
~~~

Stdout:

~~~text
Java
42
value=42
~~~

Các kết luận rút ra:

- **MemoryStore<E> implements Store<E>** gắn E trong class với T trong interface; khi được dùng qua Store<String>, phương thức save nhận String, load trả String.
- **new MemoryStore<>()** dùng diamond operator để suy luận type argument từ ngữ cảnh. Diamond không tạo một type parameter mới.
- **Converter<I, O>** khai báo hai kiểu độc lập: kiểu đầu vào I và kiểu đầu ra O.
- **LabelConverter<T> implements Converter<T, String>** chỉ chuyển tiếp T vào tham số kiểu đầu tiên; type argument thứ hai được cố định là String.
- **Converter<Integer, String>** vì vậy nhận Integer và trả String. Phép nối chuỗi trong convert tạo chính xác "value=42" ở lần gọi cuối.

Các nested interface/class trong chương trình giúp một tệp duy nhất biên dịch độc lập. Khi xây dựng dự án lớn, chúng có thể được đưa ra các file riêng mà cú pháp implements vẫn như vậy.

## 4. Chuyển tiếp `T` giữ được quan hệ kiểu giữa class và interface

Khi viết `class MemorySource<E> implements Source<E>`, `E` được khai báo **một lần bởi class** rồi truyền vào hợp đồng interface. Chẳng hạn:

~~~java
interface Source<T> { T read(); }

class MemorySource<E> implements Source<E> {
    private final E value;
    MemorySource(E value) { this.value = value; }
    @Override public E read() { return value; }
}
~~~

Trong một method, `Source<String> source = new MemorySource<>("hello");` cho phép `String text = source.read();` mà không cần cast. Nếu chỉ khai báo `Object read()`, compiler không thể hứa kết quả là `String`.

Khác biệt quan trọng của **lớp triển khai generic** là cùng class có thể duy trì hợp đồng `Source<String>`, `Source<Integer>` và các type arguments khác tại từng nơi sử dụng. Việc chuyển tiếp `E` qua `implements` giúp chữ ký override được kiểm tra từ đầu vào tới đầu ra, nhưng không tạo các runtime classes riêng cho từng `E`.

## 5. Đối chiếu: cố định kiểu hay chuyển tiếp type parameter?

Không phải mọi implementation của generic interface đều phải generic. Hai cú pháp sau có phạm vi tái sử dụng khác nhau:

~~~java
interface Reader<T> { T read(); }

class TextReader implements Reader<String> {
    @Override public String read() { return "text"; }
}

class MemoryReader<E> implements Reader<E> {
    private final E item;
    MemoryReader(E item) { this.item = item; }
    @Override public E read() { return item; }
}
~~~

| Cách triển khai | Ý nghĩa |
|---|---|
| `TextReader implements Reader<String>` | Lớp chuyên xử lý `String`; không có type parameter riêng |
| `MemoryReader<E> implements Reader<E>` | Lớp mang `E` và chuyển `E` vào interface; cùng khai báo dùng được với nhiều kiểu |

Khi lớp có nghiệp vụ cố định vào một concrete type, chọn chuyên biệt. Khi logic giống nhau cho nhiều kiểu và cần giữ quan hệ `E` xuyên suốt, chọn lớp generic. Trọng tâm các mục kế tiếp là **chuyển tiếp một phần/nhiều type parameters qua các tầng hợp đồng**, không phải lặp lại việc triển khai kiểu cố định.

## 6. Triển khai interface nhiều tham số kiểu

Xét một hợp đồng nhận khóa K và trả dữ liệu V:

~~~java
interface Lookup<K, V> {
    V find(K key);
}
~~~

Một lớp triển khai có thể chuyển tiếp cả K và V:

~~~java
class MapLookup<K, V> implements Lookup<K, V> {
    private final java.util.Map<K, V> map;

    MapLookup(java.util.Map<K, V> map) {
        this.map = map;
    }

    @Override
    public V find(K key) {
        return map.get(key);
    }
}
~~~

Ở class MapLookup, K và V được khai báo riêng và dùng làm type arguments của Lookup. Khi dùng MapLookup<String, Integer>, hợp đồng được áp dụng thành **Integer find(String key)**.

Ví dụ sử dụng:

~~~java
// Minh họa trong một phương thức:
java.util.Map<String, Integer> data =
        java.util.Map.of("spring", 21);
Lookup<String, Integer> lookup = new MapLookup<>(data);
Integer value = lookup.find("spring");
~~~

Cần giữ **đúng thứ tự đối số kiểu**: Lookup<K, V> có K cho key và V cho value. Nếu viết **implements Lookup<V, K>**, chữ ký cần implement sẽ thành **K find(V key)**, tức thay đổi hợp đồng.

### Chuyển tiếp một phần và cố định một phần

~~~java
class StringKeyLookup<V> implements Lookup<String, V> {
    private final java.util.Map<String, V> map;

    StringKeyLookup(java.util.Map<String, V> map) {
        this.map = map;
    }

    @Override
    public V find(String key) {
        return map.get(key);
    }
}
~~~

Class này chỉ khai báo V, cố định kiểu khóa thành String. **StringKeyLookup<Integer>** triển khai Lookup<String, Integer>; **StringKeyLookup<Long>** triển khai Lookup<String, Long>.

Theo chiều ngược lại cũng được:

~~~java
class BooleanLookup<K> implements Lookup<K, Boolean> {
    @Override
    public Boolean find(K key) {
        return key != null;
    }
}
~~~

**BooleanLookup<K>** giữ khóa linh hoạt và kết quả cố định Boolean. Số type parameters khai báo trên class không bắt buộc bằng số type parameters của interface; chỉ cần các type arguments trong mệnh đề implements đầy đủ, tương thích và phù hợp với method contracts.

## 7. Triển khai nhiều interface cùng lúc

Java cho phép một class triển khai nhiều superinterfaces, mỗi interface có thể dùng type variables riêng của class.

~~~java
interface Identified<ID> {
    ID id();
}

interface Valued<V> {
    V value();
}

class Entry<K, V> implements Identified<K>, Valued<V> {
    private final K key;
    private final V data;

    Entry(K key, V data) {
        this.key = key;
        this.data = data;
    }

    @Override
    public K id() {
        return key;
    }

    @Override
    public V value() {
        return data;
    }
}
~~~

**Entry<K, V>** truyền K vào Identified và V vào Valued. Một thể hiện **Entry<Long, String>** có cả hợp đồng Identified<Long> và Valued<String>.

Một type variable cũng có thể được chia sẻ giữa nhiều interface:

~~~java
interface Input<T> {
    void accept(T value);
}

interface Output<T> {
    T produce();
}

class Channel<T> implements Input<T>, Output<T> {
    private T current;

    @Override
    public void accept(T value) {
        current = value;
    }

    @Override
    public T produce() {
        return current;
    }
}
~~~

Với Channel<String>, cả accept và produce dùng String. Việc dùng cùng T mô tả quan hệ kiểu đầu vào và đầu ra của một channel.

Cú pháp class nhiều interface là **implements I<T>, J<T>**, phân cách bằng dấu phẩy. Nếu class còn extends một superclass, thứ tự là **extends Base<...> implements I<...>, J<...>**.

## 8. Quy tắc override phương thức generic interface

Interface có thể có method thông thường sử dụng type variable của interface:

~~~java
interface Transformer<I, O> {
    O transform(I input);
}

class FunctionTransformer<I, O> implements Transformer<I, O> {
    private final java.util.function.Function<? super I, ? extends O> function;

    FunctionTransformer(
            java.util.function.Function<? super I, ? extends O> function) {
        this.function = function;
    }

    @Override
    public O transform(I input) {
        return function.apply(input);
    }
}
~~~

Method triển khai phải phù hợp với chữ ký **O transform(I input)** sau phép áp dụng các type arguments. Quan trọng:

- Phương thức interface là public, vì vậy implementation cần **public**; giảm visibility xuống package-private sẽ không hợp lệ.
- @Override giúp phát hiện method không thực sự override vì sai tên, sai tham số, sai chữ ký hoặc quan hệ kiểu.
- Kiểu trả về phải tương thích; Java có hỗ trợ covariant return với các reference types khi đáp ứng luật override.
- Không được mở rộng checked exceptions vượt quá hợp đồng phương thức của interface.
- Khi method cần dùng I, O được khai báo trên class, không cần tự khai báo **<I, O>** ngay trước kiểu trả về của method.

Ví dụ lỗi:

~~~java
// Cố ý sai, không biên dịch:
interface Holder<T> {
    T read();
}

// class Wrong<T> implements Holder<T> {
//     T read() { return null; }
// }
~~~

Trong Wrong, read() thiếu public. Cách sửa là **public T read()**. Nếu method khác hẳn về kiểu tham số hoặc trả về, compiler sẽ thông báo thiếu phương thức bắt buộc hay xung đột tên.

### Phân biệt type parameter của class với generic method

~~~java
interface Copier {
    <U> U copy(U input);
}

class IdentityCopier implements Copier {
    @Override
    public <U> U copy(U input) {
        return input;
    }
}
~~~

Trong ví dụ này **Copier** không generic; chính method **copy** khai báo type parameter U. Đó là lý do implementation phải giữ chữ ký generic method tương thích.

Ngược lại:

~~~java
interface Consumer<T> {
    void accept(T item);
}

class ConsumerImpl<T> implements Consumer<T> {
    @Override
    public void accept(T item) {
        System.out.println(item);
    }
}
~~~

Method accept sử dụng T **đã được class khai báo**. Viết **public <U> void accept(U item)** sẽ khai báo một generic method khác, không thực hiện hợp đồng accept(T) mà class đang có nghĩa vụ triển khai. Phân biệt nguồn gốc của từng type variable khi đọc chữ ký.

## 9. Kế thừa generic interface rồi triển khai

Một interface có thể extends một interface generic và tiếp tục chuyển type variable của chính nó:

~~~java
interface Identified<ID> {
    ID id();
}

interface Labeled<ID> extends Identified<ID> {
    String label();
}
~~~

Labeled<ID> kế thừa Identified<ID>. Class triển khai **Labeled<K>** cần thực hiện cả id() trả K và label() trả String, trừ khi một implementation hợp lệ đã được kế thừa từ superclass.

~~~java
class LabeledItem<K> implements Labeled<K> {
    private final K key;
    private final String text;

    LabeledItem(K key, String text) {
        this.key = key;
        this.text = text;
    }

    @Override
    public K id() {
        return key;
    }

    @Override
    public String label() {
        return text;
    }
}
~~~

Chỉ cần **implements Labeled<K>**; không bắt buộc lặp thêm **implements Identified<K>**, vì đó đã là superinterface của Labeled<K>.

Một interface con có thể khai báo nhiều tham số hơn interface cha:

~~~java
interface KeyValue<K, V> extends Identified<K> {
    V value();
}
~~~

K được truyền tiếp lên Identified; V dùng ở method mới. Class muốn triển khai KeyValue<K, V> phải có cả **K id()** và **V value()**. Đây là cách chuyển tiếp type variables xuyên qua nhiều tầng quan hệ kế thừa.

## 10. Kết hợp extends class với implements interface

Một generic subclass có thể chuyển tiếp cùng type variable tới superclass và interface:

~~~java
interface Printable<T> {
    String render(T input);
}

class Container<T> {
    private final T value;

    Container(T value) {
        this.value = value;
    }

    T get() {
        return value;
    }
}

class PrintableContainer<U> extends Container<U>
        implements Printable<U> {

    PrintableContainer(U value) {
        super(value);
    }

    @Override
    public String render(U input) {
        return "[" + input + "]";
    }
}
~~~

Class **PrintableContainer<U>** vừa extends Container<U> vừa implements Printable<U>. U là type parameter do subclass khai báo; hai supertype đều nhận U làm type argument. Việc kế thừa không làm mất quan hệ kiểu giữa các thành viên, nếu các type arguments được truyền đúng.

Subclass không generic có thể cố định type argument:

~~~java
class TextContainer extends PrintableContainer<String> {
    TextContainer(String text) {
        super(text);
    }
}
~~~

TextContainer kế thừa việc triển khai Printable<String> thông qua PrintableContainer<String>. Không cần viết lại implements nếu superclass đã thực hiện interface.

Ngoài ra, subclass có thể tiếp tục khai báo type parameter và chuyển tiếp:

~~~java
class CustomContainer<X> extends PrintableContainer<X> {
    CustomContainer(X value) {
        super(value);
    }
}
~~~

Trong một hệ thống kế thừa lớn, hãy lần theo type arguments qua từng extends/implements để biết chính xác method contract mà object cuối cùng đáp ứng.

## 11. Bounds khi interface yêu cầu một kiểu có ràng buộc

Nếu generic interface có type parameter với bound, class triển khai dùng type variable cũng phải bảo đảm bound đó.

~~~java
interface NumericView<N extends Number> {
    N value();
    double asDouble();
}

class NumericBox<T extends Number> implements NumericView<T> {
    private final T number;

    NumericBox(T number) {
        this.number = number;
    }

    @Override
    public T value() {
        return number;
    }

    @Override
    public double asDouble() {
        return number.doubleValue();
    }
}
~~~

**NumericBox<T extends Number>** bảo đảm T đáp ứng Number; do đó **implements NumericView<T>** hợp lệ. Nếu viết **class NumericBox<T> implements NumericView<T>**, compiler không thể chứng minh mọi T đều là Number.

Với interface cần Comparable:

~~~java
interface OrderedValue<T extends Comparable<T>> {
    T get();
}

class OrderedBox<T extends Comparable<T>>
        implements OrderedValue<T> {
    private final T value;

    OrderedBox(T value) {
        this.value = value;
    }

    @Override
    public T get() {
        return value;
    }
}
~~~

Nếu type parameter cần nhiều bounds, dùng **&**:

~~~java
class NumberOrder<T extends Number & Comparable<T>>
        implements Comparable<NumberOrder<T>> {

    private final T number;

    NumberOrder(T number) {
        this.number = number;
    }

    @Override
    public int compareTo(NumberOrder<T> other) {
        return number.compareTo(other.number);
    }
}
~~~

Ở đây **Comparable<NumberOrder<T>>** có type argument là **toàn bộ kiểu tham số hóa NumberOrder<T>**; vì vậy chữ ký override là **compareTo(NumberOrder<T> other)**, không phải compareTo(T). Bound trên T giúp phần thân có thể gọi number.compareTo(other.number).

Dù Number là class và Comparable là interface, khai báo type parameter vẫn dùng **extends**. Nếu có class bound, nó đứng trước interface bounds, phân tách bằng **&**.

## 12. Ví dụ chạy: kế thừa interface generic, nhiều kiểu và một subclass cố định

Lưu thành **GenericHierarchyDemo.java**:

~~~java
public class GenericHierarchyDemo {
    interface Identified<ID> {
        ID id();
    }

    interface Labeled<ID> extends Identified<ID> {
        String label();
    }

    static class Item<K, V> implements Labeled<K> {
        private final K key;
        private final V value;
        private final String label;

        Item(K key, V value, String label) {
            this.key = key;
            this.value = value;
            this.label = label;
        }

        @Override
        public K id() {
            return key;
        }

        @Override
        public String label() {
            return label;
        }

        V value() {
            return value;
        }
    }

    static class StringItem extends Item<String, Integer> {
        StringItem(String id, Integer value) {
            super(id, value, "fixed");
        }
    }

    public static void main(String[] args) {
        Labeled<String> a = new Item<>("A-1", 7, "item");
        System.out.println(a.id() + " / " + a.label());

        Item<Long, String> b = new Item<>(42L, "done", "task");
        System.out.println(b.id() + " -> " + b.value());

        StringItem c = new StringItem("S", 9);
        System.out.println(c.id() + ":" + c.value());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 GenericHierarchyDemo.java
java GenericHierarchyDemo
~~~

Stdout:

~~~text
A-1 / item
42 -> done
S:9
~~~

Ở chương trình này:

1. **Labeled<ID> extends Identified<ID>** chuyển tiếp ID từ interface con lên interface cha.
2. **Item<K, V> implements Labeled<K>** chỉ truyền K cho interface; V là type parameter bổ sung dùng cho payload.
3. **Labeled<String> a** chỉ phơi bày các method do Labeled<String> và Identified<String> bảo đảm. Vì vậy a.id() trả String, a.label() trả String; còn method riêng value() của Item không thuộc API của biến a.
4. **Item<Long, String>** áp dụng K = Long và V = String; chỉ K tham gia hợp đồng Labeled<K>.
5. **StringItem extends Item<String, Integer>** cố định type arguments, đồng thời kế thừa implementation của Labeled<String>.

## 13. Tính bất biến khi sử dụng interface generic

Nếu class implements Service<T>, việc dùng Class<String> tạo ra quan hệ với Service<String>. Tuy nhiên, Java không xem **Service<String>** tự động là subtype của **Service<Object>**, dù String là subtype của Object.

~~~java
interface Service<T> {
    T result();
}

class ServiceImpl<T> implements Service<T> {
    private final T value;

    ServiceImpl(T value) {
        this.value = value;
    }

    @Override
    public T result() {
        return value;
    }
}
~~~

Các phép gán đúng:

~~~java
// Minh họa trong phương thức:
Service<String> text = new ServiceImpl<>("ok");
String a = text.result();

Service<Integer> count = new ServiceImpl<>(123);
Integer b = count.result();
~~~

Phép gán sau sai:

~~~java
// Cố ý sai, không biên dịch:
// Service<Object> everything = new ServiceImpl<String>("ok");
~~~

**Service<String>** không là subtype của Service<Object>. Đây là tính **invariance** của generic type arguments. Nếu chỉ cần đọc Number từ một service đang giữ một subtype của Number, dùng wildcard ở nơi khai báo tham chiếu:

~~~java
Service<? extends Number> numeric = new ServiceImpl<>(10);
Number n = numeric.result();
~~~

Đây là cách dùng wildcard **tại nơi sử dụng kiểu**. Nó khác với mệnh đề implements trong khai báo class.

## 14. Vì sao không viết implements Interface<?>?

Mã sau không hợp lệ:

~~~java
interface Receiver<T> {
    void accept(T input);
}

// Cố ý sai:
// class UnknownReceiver implements Receiver<?> {
//     public void accept(Object input) {}
// }
~~~

Dấu **?** là wildcard type argument phù hợp ở nhiều vị trí **sử dụng** parameterized type; không được dùng làm type argument trực tiếp trong phần khai báo superinterface **implements Receiver<?>**. Một class phải chỉ ra hợp đồng nó sẽ triển khai thông qua type arguments thích hợp.

Nếu muốn class linh hoạt:

~~~java
class GenericReceiver<T> implements Receiver<T> {
    @Override
    public void accept(T input) {
        System.out.println(input);
    }
}
~~~

Nếu muốn class chỉ nhận Object:

~~~java
class AnyObjectReceiver implements Receiver<Object> {
    @Override
    public void accept(Object input) {
        System.out.println(input);
    }
}
~~~

**Receiver<T>** và **Receiver<Object>** không thể tùy tiện thay thế nhau: T có thể là String, Integer hoặc một reference type khác. **Receiver<?>** có thể là kiểu biến ở nơi sử dụng khi bạn chưa biết type argument, nhưng không đồng nghĩa với Receiver<Object>.

## 15. Không thể triển khai hai chuyên biệt khác nhau của cùng generic interface

Ví dụ:

~~~java
interface Action<T> {
    void run(T value);
}

interface TextAction extends Action<String> {}
interface CountAction extends Action<Integer> {}

// Cố ý sai, không biên dịch:
// class Impossible implements TextAction, CountAction {}
~~~

Một class không thể đồng thời kế thừa Action<String> và Action<Integer> từ hai đường superinterfaces như trên. Generic interface đã bị chuyên biệt theo hai type arguments khác nhau; Java cấm xung đột hợp đồng kiểu này. Đây không chỉ là vấn đề thiếu method, mà là một giới hạn của hệ thống kiểu generic và erasure.

Có thể sử dụng **composition** để một class điều phối hai trách nhiệm khác nhau:

~~~java
class ActionCoordinator {
    private final Action<String> text;
    private final Action<Integer> count;

    ActionCoordinator(Action<String> text, Action<Integer> count) {
        this.text = text;
        this.count = count;
    }

    void text(String value) {
        text.run(value);
    }

    void count(Integer value) {
        count.run(value);
    }
}
~~~

ActionCoordinator giữ hai dependency có kiểu rõ ràng mà không phải cùng implements Action hai lần. Nếu hai vai trò thực sự tách biệt, thiết kế hai interface khác nhau cũng có thể phù hợp.

## 16. Raw type, erasure và bridge method

Một mệnh đề implements có thể dùng *raw type* của generic interface trong mã cũ:

~~~java
interface DataHolder<T> {
    void set(T value);
    T get();
}

// Raw type: chỉ minh họa tương thích mã cũ.
class RawHolder implements DataHolder {
    private Object data;

    @Override
    public void set(Object value) {
        data = value;
    }

    @Override
    public Object get() {
        return data;
    }
}
~~~

**implements DataHolder** bỏ type argument, dẫn đến việc sử dụng các chữ ký sau erasure như Object khi type variable không bound. Raw type làm mất nhiều kiểm tra an toàn kiểu, có thể tạo cảnh báo *unchecked* khi chuyển giữa raw và parameterized reference.

Trong code mới, nên viết rõ một trong hai ý định:

- **class Holder<T> implements DataHolder<T>**: class generic giữ cùng type variable.
- **class ObjectHolder implements DataHolder<Object>**: triển khai chuyên biệt cho Object.

Một hạn chế runtime liên quan là **type erasure**: generic type variables thường được erase thành cận trên (Object nếu không có cận). Nếu class triển khai interface bằng kiểu cụ thể và override một method, compiler có thể tạo **bridge method** để duy trì dispatch đúng sau erasure.

~~~java
interface Provider<T> {
    T supply();
}

class TextProvider implements Provider<String> {
    @Override
    public String supply() {
        return "Java";
    }
}
~~~

TextProvider viết method supply() trả String. Compiler có thể sinh bridge method có chữ ký erased trả Object để đáp ứng cơ chế JVM. Lập trình viên không tự viết bridge này; ở Java source, tham chiếu **Provider<String>** vẫn trả String với kiểm tra kiểu biên dịch.

Điều đó không có nghĩa cứ gọi **getClass()** sẽ biết type arguments của một object generic: thông tin generic có thể xuất hiện trong metadata của khai báo, nhưng đối số kiểu gắn với biến/tham chiếu runtime bất kỳ không thể luôn khôi phục được từ runtime class.

## 17. Default method và static method trong generic interface

Generic interface có thể định nghĩa default method sử dụng type parameter của interface:

~~~java
interface Mapper<T> {
    T map(T value);

    default java.util.List<T> mapAll(java.util.List<T> source) {
        java.util.List<T> output = new java.util.ArrayList<>();
        for (T value : source) {
            output.add(map(value));
        }
        return output;
    }

    static <U> U identity(U input) {
        return input;
    }
}

class EchoMapper<T> implements Mapper<T> {
    @Override
    public T map(T value) {
        return value;
    }
}
~~~

EchoMapper<T> cung cấp implementation của map(T), đồng thời kế thừa default method mapAll(List<T>). Với EchoMapper<String>, mapAll nhận List<String> và trả List<String>.

**Mapper.identity** là một static generic method tự khai báo U. Nó không dùng T của interface vì static method không gắn với một instance Mapper<String>. Có thể gọi **Mapper.identity("hello")** hoặc **Mapper.<String>identity("hello")**.

Nếu nhiều superinterfaces mang các default methods xung đột, class triển khai có thể phải tự override để giải quyết theo luật Java. Cơ chế type argument không loại bỏ những quy tắc xung đột của default method.

## 18. Ví dụ chạy độc lập: nhiều superinterfaces và bound

Lưu vào **GenericContractsDemo.java**:

~~~java
public class GenericContractsDemo {
    interface Named<T> {
        T value();
    }

    interface TextView {
        String render();
    }

    interface Formatter<T> {
        String format(T input);

        default String formatNonNull(T input) {
            return input == null ? "(missing)" : format(input);
        }
    }

    static final class Ranked<T extends Number & Comparable<T>>
            implements Named<T>, TextView, Comparable<Ranked<T>> {

        private final T rank;

        Ranked(T rank) {
            this.rank = rank;
        }

        @Override
        public T value() {
            return rank;
        }

        @Override
        public String render() {
            return "rank=" + rank.doubleValue();
        }

        @Override
        public int compareTo(Ranked<T> other) {
            return rank.compareTo(other.rank);
        }
    }

    static final class SimpleFormatter<T> implements Formatter<T> {
        @Override
        public String format(T input) {
            return "[" + input + "]";
        }
    }

    public static void main(String[] args) {
        Ranked<Integer> low = new Ranked<>(3);
        Ranked<Integer> high = new Ranked<>(8);

        System.out.println(low.compareTo(high) < 0);
        System.out.println(low.render());
        System.out.println(high.value());

        Formatter<String> format = new SimpleFormatter<>();
        System.out.println(format.formatNonNull("Java"));
        System.out.println(format.formatNonNull(null));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 GenericContractsDemo.java
java GenericContractsDemo
~~~

Stdout:

~~~text
true
rank=3.0
8
[Java]
(missing)
~~~

Chương trình minh họa:

- **Ranked<T>** truyền T vào Named<T>, nhưng implements TextView là interface không generic.
- **Comparable<Ranked<T>>** nhận cả kiểu Ranked<T> làm type argument; compareTo nhận một Ranked<T> khác.
- Bound **T extends Number & Comparable<T>** cho phép vừa gọi doubleValue() vừa so sánh hai giá trị T.
- **SimpleFormatter<T> implements Formatter<T>** có method format(T), còn default method formatNonNull(T) đến từ interface.
- Trong nhánh null, formatNonNull trả "(missing)" mà không gọi format.

## 19. Các lỗi biên dịch phổ biến và cách sửa

**1. Không khai báo T của class**

~~~java
interface Source<T> {
    T get();
}

// Sai vì T chưa tồn tại trong scope:
// class BrokenSource implements Source<T> {}
~~~

Sửa thành **class FixedSource<T> implements Source<T>** và triển khai get(), hoặc dùng **Source<String>** với kiểu cố định.

**2. Đảo thứ tự type arguments**

~~~java
interface PairService<K, V> {
    V get(K key);
}

// Cố ý sai nếu method viết theo K -> V:
// class Wrong<K, V> implements PairService<V, K> {
//     public V get(K key) { return null; }
// }
~~~

Với **PairService<V, K>**, hợp đồng thật là **K get(V key)**; muốn giữ V get(K key) phải dùng **implements PairService<K, V>**.

**3. Sai visibility của method override**

~~~java
interface Writer<T> {
    void write(T value);
}

// Sai:
// class WriterImpl<T> implements Writer<T> {
//     void write(T value) {}
// }
~~~

Method trong interface là public. Phần triển khai phải là **public void write(T value)** và nên dùng @Override.

**4. Đổi T thành Object tùy tiện**

~~~java
interface Returner<T> {
    T run();
}

// Sai:
// class ReturnerImpl<T> implements Returner<T> {
//     public Object run() { return new Object(); }
// }
~~~

Object không bảo đảm là T. Cần triển khai **public T run()** hoặc cố định type argument thành Object nếu API thực sự muốn như vậy.

**5. Dùng interface có bound nhưng class không đáp ứng**

~~~java
interface NumberView<T extends Number> {
    T get();
}

// Sai:
// class AnyView<T> implements NumberView<T> {}
~~~

Sửa thành **class NumberViewImpl<T extends Number> implements NumberView<T>** và triển khai get().

**6. Dùng wildcard trong implements**

**implements Receiver<?>** không hợp lệ; hãy sử dụng **implements Receiver<T>** khi class có khai báo T hoặc **implements Receiver<Object>** cho implementation cố định.

**7. Triển khai cùng interface với hai type arguments khác nhau**

**implements Action<String>, Action<Integer>** không hợp lệ. Cần thay đổi thiết kế để mỗi class không kế thừa cùng generic interface theo hai chuyên biệt khác nhau.

**8. Dùng raw type để bỏ type arguments**

**implements Holder** với Holder generic làm mất quan hệ kiểu. Chọn **Holder<T>** hoặc một chuyên biệt cụ thể và rà soát cảnh báo unchecked.

**9. Giả định type parameters của class được dùng trong static method**

~~~java
class Util<T> {
    // static T echo(T value) { return value; } // Sai.
    static <U> U echo(U value) {
        return value;
    }
}
~~~

Static method tự khai báo U. T của class không thuộc phần static theo cách dùng trên.

**10. Tưởng T extends Object cho phép cast tùy ý**

Ngay cả khi T không bound có cận Object, **Service<String>** không phải Service<Object>. Không ép kiểu vòng qua Object để bỏ qua generic type checking; hãy xem lại hợp đồng và cân nhắc wildcard ở vị trí sử dụng.

## 20. Khi nào nên thiết kế class implements interface generic?

Các trường hợp điển hình:

| Tình huống | Thiết kế gợi ý | Lý do |
| --- | --- | --- |
| Một bộ nhớ chứa bất kỳ kiểu E | MemoryStore<E> implements Store<E> | Giữ hợp đồng E xuyên suốt |
| Lookup với khóa và giá trị độc lập | MapLookup<K, V> implements Lookup<K, V> | Bảo toàn hai quan hệ kiểu |
| Khóa luôn String, giá trị biến đổi | StringKeyLookup<V> implements Lookup<String, V> | Chỉ linh hoạt vị trí cần thiết |
| Chuyển bất kỳ T thành chuỗi | LabelConverter<T> implements Converter<T, String> | Đầu ra cố định String |
| Chỉ đọc chuỗi từ nguồn cố định | TextReader implements Reader<String> | Không cần generic class |
| Cần cùng T giữa hai interface | Channel<T> implements Input<T>, Output<T> | Kết nối hợp đồng đọc/ghi |
| Nhiều hành vi độc lập cho cùng đối tượng | Entity<K,V> implements Identified<K>, Valued<V> | Mỗi interface nhận type argument đúng vai trò |

Một quy trình thiết kế có ích:

1. Bắt đầu từ hợp đồng interface và xác định từng type parameter biểu thị kiểu gì.
2. Quyết định type arguments nào cần linh hoạt qua class và type arguments nào nên cố định.
3. Đặt đúng danh sách **<...>** ngay sau tên class và viết đủ đối số trong implements.
4. Từ interface, thay type parameters bằng type arguments tương ứng để suy ra chính xác chữ ký cần @Override.
5. Kiểm tra bounds, visibility, return types và các superinterfaces thừa kế.
6. Thử khai báo một biến có kiểu interface được tham số hóa và gán một implementation thích hợp. Compiler sẽ phát hiện khi mối quan hệ kiểu không khớp.
7. Xử lý null, exceptions và trạng thái mutable theo contract riêng; generics không bảo đảm các thuộc tính runtime đó.

Ví dụ **Lookup<K, V>** dùng Map.get có thể trả null nếu không thấy khóa. Việc triển khai đúng Lookup<K,V> bảo đảm kiểu trả về V về mặt tĩnh nhưng không tự cam kết giá trị khác null; API nên mô tả rõ điều đó.

## 21. Câu hỏi ôn tập

**Câu 1.** Trong **class DataSource<U> implements Source<U>**, vị trí nào khai báo U và vị trí nào sử dụng U làm type argument?

**Đáp án:** DataSource<U> khai báo type parameter U của class; Source<U> trong implements dùng U đã khai báo làm type argument cho Source.

**Câu 2.** Có cần cùng tên type parameter giữa interface và class không?

**Đáp án:** Không. Interface<A> và Implementation<T> có thể liên kết bằng implements Interface<T>.

**Câu 3.** Nếu interface **Mapper<I, O>** có method **O map(I value)** và class **MapperImpl<T> implements Mapper<T, String>**, chữ ký method triển khai là gì?

**Đáp án:** **public String map(T value)**.

**Câu 4.** Tại sao **class Bad implements Source<T>** sai khi class chưa khai báo T?

**Đáp án:** T không nằm trong phạm vi của Bad. Cần khai báo **class Bad<T>** hoặc chọn một type argument cụ thể.

**Câu 5.** Nếu interface **Bounded<N extends Number>**, có thể viết **class Holder<T> implements Bounded<T>** không?

**Đáp án:** Không, nếu T không có bound tương thích. Cần ví dụ **class Holder<T extends Number> implements Bounded<T>** và các method bắt buộc.

**Câu 6.** Với **class Entry<K,V> implements Identified<K>, Valued<V>**, interface nào dùng K và interface nào dùng V?

**Đáp án:** Identified nhận K, Valued nhận V. Entry<Long, String> thực hiện Identified<Long> và Valued<String>.

**Câu 7.** Một class implements **Labeled<T>** với **Labeled<T> extends Identified<T>** có phải implement id() không?

**Đáp án:** Có nếu id() còn abstract và chưa được cung cấp bởi superclass; vì Labeled<T> kế thừa hợp đồng của Identified<T>.

**Câu 8.** **Service<String>** có tự động gán cho **Service<Object>** được không?

**Đáp án:** Không. Generic types Java mặc định invariant; dùng wildcard ở nơi sử dụng nếu mô hình đọc/ghi cho phép.

**Câu 9.** Tại sao **implements Receiver<?>** không hợp lệ?

**Đáp án:** Wildcard không thể là type argument trực tiếp của superinterface được khai báo trong implements. Dùng Receiver<T> với T do class khai báo hoặc Receiver<ConcreteType>.

**Câu 10.** Có thể triển khai Action<String> và Action<Integer> đồng thời trong một class không?

**Đáp án:** Không, vì cùng generic interface Action bị kế thừa với hai type arguments khác nhau; có thể dùng composition cho hai trách nhiệm.

**Câu 11.** Với **class Ranked<T> implements Comparable<Ranked<T>>**, kiểu tham số compareTo là T hay Ranked<T>?

**Đáp án:** Ranked<T>. Type argument của Comparable là cả kiểu Ranked<T>, nên method nhận đối tượng Ranked<T> khác.

**Câu 12.** Vì sao một implementation cụ thể của Reader<String> có thể có bridge method trong bytecode?

**Đáp án:** Compiler có thể sinh bridge để duy trì dispatch/phù hợp chữ ký sau type erasure; developer chỉ cần viết @Override đúng trong Java source.

## 22. Tổng kết

**class Implementation<T> implements Interface<T>** là cú pháp chuẩn để class dùng chính tham số kiểu của mình nhằm thực hiện một generic interface. Nó tạo một ràng buộc kiểu rõ ràng giữa class và contract, giúp caller sử dụng Implementation<String> như Interface<String> và được kiểm tra kiểu khi biên dịch.

Khi interface có nhiều tham số kiểu, class có thể chuyển tiếp tất cả, chuyển tiếp một phần hoặc kết hợp type variables với type arguments cụ thể. Cần theo dõi các type arguments qua từng tầng extends/implements, triển khai method với @Override đúng chữ ký, đáp ứng bounds và tránh raw type, wildcard trong superinterface cùng xung đột kế thừa các chuyên biệt khác nhau.
