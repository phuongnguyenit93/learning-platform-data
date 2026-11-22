# Thêm tham số kiểu mới ở lớp con khi kế thừa Generics trong Java

Một lớp con của generic class **có thể khai báo nhiều tham số kiểu hơn lớp cha**. Lớp con quyết định tham số kiểu nào được truyền cho lớp cha và tham số kiểu nào được dùng cho dữ liệu/hành vi bổ sung của chính nó. Chẳng hạn, nếu `Box<T>` chứa một giá trị `T`, lớp con `TaggedBox<T, M>` có thể kế thừa giá trị đó và thêm một dấu nhãn (metadata) thuộc kiểu `M`.

```java
class Box<T> {
    private final T value;

    Box(T value) {
        this.value = value;
    }

    T get() {
        return value;
    }
}

class TaggedBox<T, M> extends Box<T> {
    private final M marker;

    TaggedBox(T value, M marker) {
        super(value);
        this.marker = marker;
    }

    M marker() {
        return marker;
    }
}
```

Đây là **hai định nghĩa lớp minh họa**, chưa có phương thức `main`. Quan hệ cốt lõi nằm ở dòng `class TaggedBox<T, M> extends Box<T>`:

- `<T, M>` khai báo **hai type parameters của lớp con**. `T` là kiểu giá trị, `M` là kiểu nhãn do lớp con bổ sung.
- `extends Box<T>` truyền **chỉ `T`** cho type parameter của lớp cha. `Box<T>` không tự biết `M`.
- `super(value)` gọi constructor của lớp cha để thiết lập trạng thái `T`.
- `marker` và `marker()` là phần mở rộng gắn với type parameter `M` riêng của lớp con.
- `TaggedBox<String, Integer>` là subtype của `Box<String>` vì nó `extends Box<T>` với `T = String`; nó không phải subtype của `Box<Integer>`.

Thiết kế này rất hữu ích khi một subtype cần bổ sung thông tin như mã định danh, nhãn, kiểu đơn vị đo, kiểu trạng thái hoặc chính sách xử lý, trong khi vẫn dùng lại hợp đồng chung của lớp cha.

## 1. Cú pháp tổng quát: lớp con khai báo kiểu rồi ánh xạ lên lớp cha

Khuôn dạng thường gặp:

```java
class Parent<A> {
    // Thành viên dựa trên A
}

class Child<A, B> extends Parent<A> {
    // Có thể dùng A được kế thừa theo quan hệ với Parent<A>
    // và thêm trạng thái/hành vi dựa trên B
}
```

Ví dụ trên chỉ minh họa **cú pháp kế thừa**, chưa có chức năng của cặp `A`, `B`. Quan trọng là:

1. Danh sách `<A, B>` sau tên `Child` **khai báo** type parameters của `Child`.
2. Danh sách `<A>` sau `Parent` trong `extends Parent<A>` là **các type arguments** truyền cho lớp cha.
3. Trình biên dịch áp dụng ánh xạ đó để xác định kiểu của các thành viên `Parent` khi nhìn từ `Child`.
4. Tham số kiểu thêm ở lớp con `B` không bắt buộc phải có vai trò nào trong lớp cha; nó có thể chỉ phục vụ trường và method mới.

`extends` mô tả **quan hệ kế thừa lớp**, còn các dấu `<...>` mô tả **tham số hóa kiểu**. Không có quy tắc rằng lớp con phải chỉ dùng đúng số tham số kiểu của lớp cha, cũng không bắt buộc giữ nguyên tên hay thứ tự type parameter.

Một ví dụ có ánh xạ khác:

```java
class Parent<T> { }

class Child<K, V> extends Parent<V> { }
```

Lớp con này gửi **`V`** cho `T` của lớp cha, để `K` cho chức năng riêng của lớp con. Với `Child<String, Integer>`, supertype được tham số hóa là `Parent<Integer>`, **không phải `Parent<String>`**. Tên `K`, `V` chỉ là quy ước: quan hệ thực sự do `extends Parent<V>` quyết định.

## 2. Lớp con giữ kiểu cha và thêm kiểu mới

Giả sử lớp cha quản lý phần tử `T`; lớp con cần thêm metadata thuộc kiểu `M`:

```java
class Item<T> {
    private final T data;

    Item(T data) {
        this.data = data;
    }

    T data() {
        return data;
    }
}

class LabeledItem<T, M> extends Item<T> {
    private final M label;

    LabeledItem(T data, M label) {
        super(data);
        this.label = label;
    }

    M label() {
        return label;
    }
}
```

Hai lớp này là **định nghĩa minh họa thay thế**, không đặt trùng tên với các lớp cùng tên trong một package nếu đã có. Khi dùng trong một method:

```java
LabeledItem<String, Integer> item =
        new LabeledItem<>("book", 101);

String value = item.data();
Integer label = item.label();
```

Nhờ `extends Item<T>`, kiểu trả về của phương thức kế thừa `data()` là `String` tại `LabeledItem<String, Integer>`, không phải `Object`. Còn `label()` có kiểu `Integer` nhờ tham số kiểu mới `M`.

Nếu bạn viết `LabeledItem<String, Integer>` rồi truyền một `Boolean` vào vị trí `M`, compiler có thể báo lỗi ngay. Bạn cũng không cần cast một nhãn `Integer` về đúng kiểu sau khi đọc.

Điều kiện tiên quyết: các type arguments truyền cho class/interface cha phải đáp ứng **mọi upper bound** trong khai báo của cha. Ví dụ nếu cha là `class Parent<T extends Number>`, lớp con không thể đơn giản viết `class Child<T, M> extends Parent<T>` với `T` hoàn toàn không bound; phải bảo đảm `T` thỏa `Number`.

## 3. Lớp con có thể cố định kiểu cha nhưng vẫn thêm kiểu riêng

Không phải tham số kiểu của lớp con nào cũng cần chuyển cho lớp cha. Ví dụ:

```java
class Base<T> {
    private final T value;

    Base(T value) {
        this.value = value;
    }

    T get() {
        return value;
    }
}

class TextMetadata<M> extends Base<String> {
    private final M metadata;

    TextMetadata(String text, M metadata) {
        super(text);
        this.metadata = metadata;
    }

    M metadata() {
        return metadata;
    }
}
```

Đây là **hai lớp minh họa độc lập**. `TextMetadata<M>` có đúng một type parameter `M` của nó, nhưng kế thừa `Base<String>` với **type argument cố định `String`**, không gửi `M` lên cha.

Khi gọi:

```java
TextMetadata<Long> entry = new TextMetadata<>("hello", 99L);

String text = entry.get();
Long meta = entry.metadata();
```

`get()` luôn trả về `String` cho mọi `TextMetadata<M>`, còn `metadata()` thay đổi kiểu theo `M`. Bởi vậy:

- `TextMetadata<Long>` là subtype của `Base<String>`.
- `TextMetadata<Boolean>` cũng là subtype của `Base<String>`.
- `TextMetadata<Long>` không tự nhiên trở thành subtype của `Base<Long>`.

Đây là cách thiết kế tốt khi subtype đại diện cho **một loại chuyên biệt của phần dữ liệu cha**, nhưng phần dữ liệu bổ sung vẫn cần tổng quát.

## 4. Ví dụ Java 17 chạy độc lập: ba cách thêm tham số kiểu ở lớp con

Lưu toàn bộ chương trình sau thành **`ExtraSubclassTypeParameterDemo.java`**:

```java
import java.util.List;
import java.util.Objects;
import java.util.function.Function;

public class ExtraSubclassTypeParameterDemo {
    static class Box<T> {
        private final T value;

        protected Box(T value) {
            this.value = value;
        }

        public T get() {
            return value;
        }

        public String describe() {
            return "Box(" + value + ")";
        }
    }

    static final class TaggedBox<T, M> extends Box<T> {
        private final M marker;

        private TaggedBox(T value, M marker) {
            super(value);
            this.marker = marker;
        }

        static <V, L> TaggedBox<V, L> of(V value, L marker) {
            return new TaggedBox<>(value, marker);
        }

        public M marker() {
            return marker;
        }

        @Override
        public String describe() {
            return "Tagged(" + get() + ", " + marker + ")";
        }

        public <U> TaggedBox<U, M> mapValue(
                Function<? super T, ? extends U> mapper) {
            Objects.requireNonNull(mapper, "mapper");
            return TaggedBox.of(mapper.apply(get()), marker);
        }
    }

    static final class TextTagged<M> extends Box<String> {
        private final M metadata;

        TextTagged(String text, M metadata) {
            super(text);
            this.metadata = metadata;
        }

        M metadata() {
            return metadata;
        }
    }

    interface Identifiable<ID> {
        ID id();
    }

    static final class Identified<T, ID>
            extends Box<T> implements Identifiable<ID> {
        private final ID id;

        Identified(T value, ID id) {
            super(value);
            this.id = id;
        }

        @Override
        public ID id() {
            return id;
        }
    }

    static final class NumericTagged<N extends Number, M>
            extends Box<N> {
        private final M marker;

        NumericTagged(N value, M marker) {
            super(value);
            this.marker = marker;
        }

        double twice() {
            return get().doubleValue() * 2;
        }

        M marker() {
            return marker;
        }
    }

    public static void main(String[] args) {
        TaggedBox<String, Integer> tagged = TaggedBox.of("Java", 7);
        System.out.println("tagged: " + tagged.describe());
        System.out.println("types: " + tagged.get().toUpperCase()
                + "/" + (tagged.marker() + 1));

        Box<String> parentView = tagged;
        System.out.println("upcast: " + parentView.get());
        System.out.println("dispatch: " + parentView.describe());

        TaggedBox<Integer, Integer> mapped =
                tagged.mapValue(String::length);
        System.out.println("mapped: " + mapped.describe());

        TextTagged<Long> fixed = new TextTagged<>("Hi", 99L);
        System.out.println("fixed: " + fixed.get()
                + "/" + fixed.metadata());

        Identified<List<Integer>, String> identified =
                new Identified<>(List.of(2, 4, 6), "batch-1");
        System.out.println("identified: " + identified.id()
                + "=" + identified.get());

        Identifiable<String> interfaceView = identified;
        System.out.println("interface: " + interfaceView.id());

        NumericTagged<Integer, String> numeric =
                new NumericTagged<>(8, "units");
        System.out.println("numeric: " + numeric.twice()
                + "/" + numeric.marker());

        List<Box<String>> boxes = List.of(tagged, fixed);
        System.out.println("boxes: " + boxes.size());
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```bash
javac ExtraSubclassTypeParameterDemo.java
java ExtraSubclassTypeParameterDemo
```

Stdout theo đúng thứ tự:

```text
tagged: Tagged(Java, 7)
types: JAVA/8
upcast: Java
dispatch: Tagged(Java, 7)
mapped: Tagged(4, 7)
fixed: Hi/99
identified: batch-1=[2, 4, 6]
interface: batch-1
numeric: 16.0/units
boxes: 2
```

### Phân tích ví dụ

**Trường hợp A — `TaggedBox<T, M> extends Box<T>`.** Lớp con giữ nguyên kiểu giá trị từ cha qua `T`, rồi bổ sung nhãn `M`. Khi `T = String`, `get()` trả `String`; khi `M = Integer`, `marker()` trả `Integer`. Biểu thức `tagged.marker() + 1` hợp lệ nhờ unboxing wrapper.

**Trường hợp B — upcasting giữ đúng kiểu cha.** `Box<String> parentView = tagged;` hợp lệ vì `TaggedBox<String, Integer>` kế thừa `Box<String>`. Qua `parentView`, compiler vẫn biết `get()` trả `String`, nhưng không cho gọi trực tiếp `marker()`, vì phương thức đó không được khai báo trên `Box<String>`. Lời gọi `parentView.describe()` vẫn thực hiện **dynamic dispatch** tới override của `TaggedBox`, nên kết quả là `Tagged(Java, 7)`.

**Trường hợp C — generic method riêng trong generic subclass.** `mapValue` khai báo `<U>` thuộc **method**, độc lập với `T` và `M` thuộc **lớp**. Nó biến giá trị từ kiểu `T` sang `U` nhưng giữ nhãn `M`. Vì vậy `TaggedBox<String, Integer>` biến thành `TaggedBox<Integer, Integer>` khi ánh xạ `String::length`. Wildcard `Function<? super T, ? extends U>` cho phép function tiêu thụ kiểu rộng hơn `T` và tạo kết quả thuộc subtype thích hợp của `U`.

**Trường hợp D — `TextTagged<M> extends Box<String>`.** Kiểu dữ liệu của lớp cha được **cố định** là `String`; `M` chỉ dành cho metadata của subclass. `TextTagged<Long>` vẫn là một `Box<String>`, không phải `Box<Long>`.

**Trường hợp E — `Identified<T, ID> extends Box<T> implements Identifiable<ID>`.** Lớp con chuyển `T` cho superclass và `ID` cho interface. Một subclass có thể mở rộng **một class** và thực thi **nhiều interface**; các type arguments ở mỗi quan hệ được kiểm tra theo khai báo tương ứng. Ở đây `Identified<List<Integer>, String>` lưu danh sách số nguyên và mã định danh chuỗi; qua `Identifiable<String>`, method `id()` vẫn trả `String`.

**Trường hợp F — `NumericTagged<N extends Number, M>`.** Subclass áp đặt bound `N extends Number` để dùng `doubleValue()`. Bound `Number` cũng bảo đảm `N` thích hợp làm type argument của `Box<N>`. `NumericTagged<Integer, String>` hợp lệ, nhưng `NumericTagged<String, Integer>` sẽ không biên dịch.

**Trường hợp G — collection của kiểu cha.** `List<Box<String>> boxes = List.of(tagged, fixed);` hợp lệ vì **cả hai đối tượng** có supertype `Box<String>` và ngữ cảnh đích phù hợp. Điều này không đồng nghĩa có thể trực tiếp gán cả một `List<TaggedBox<String, Integer>>` sang `List<Box<String>>`: Java generic collection vẫn **invariant**, như phần dưới.

## 5. Ánh xạ type parameter giữa cha và con không nhất thiết cùng tên

Trình biên dịch không dựa vào tên `T`, `U`, `K`, `V` để nối kiểu cha–con. Nó dựa vào **type argument biểu thức trong mệnh đề `extends`**.

```java
class Parent<P> {
    P get() {
        return null;
    }
}

class Child<A, B> extends Parent<B> {
    private A extra;
}
```

Đây là **lớp minh họa**, không dùng `null` làm giá trị hợp đồng sản phẩm; phần thân chỉ để biểu diễn kiểu trả về. `Child<String, Integer>` kế thừa `Parent<Integer>` và `get()` trả kiểu `Integer`, còn `extra` là `String`.

Có thể dùng kiểu tổng hợp làm type argument của cha:

```java
class Parent<T> { }

class Aggregated<A, B> extends Parent<java.util.List<A>> {
    private final B metadata;

    Aggregated(B metadata) {
        this.metadata = metadata;
    }
}
```

Với `Aggregated<String, Long>`, supertype của nó là `Parent<List<String>>`. Như vậy subclass **không nhất thiết** phải truyền trực tiếp một type parameter trần; nó có thể truyền một parameterized type được tạo từ tham số kiểu của lớp con. Tuy nhiên, mọi kiểu trong khai báo phải hợp lệ và thỏa bounds của cha.

**Nhận biết đúng phạm vi:** ký hiệu trong `class Child<A,B>` do lớp con khai báo; `Parent<B>` sử dụng ký hiệu `B` ấy làm type argument. `Parent` không “nhận thêm” type parameter `A`; chính subtype mới là nơi sở hữu thông tin thêm.

## 6. Thêm một kiểu mới để thực thi generic interface

Mẫu kế thừa tổng quát còn xuất hiện khi lớp con triển khai interface:

```java
interface HasKey<K> {
    K key();
}

class ValueHolder<T> {
    private final T value;

    ValueHolder(T value) {
        this.value = value;
    }

    T get() {
        return value;
    }
}

class KeyedHolder<T, K> extends ValueHolder<T>
        implements HasKey<K> {
    private final K key;

    KeyedHolder(T value, K key) {
        super(value);
        this.key = key;
    }

    @Override
    public K key() {
        return key;
    }
}
```

Đây là **ba khai báo minh họa**, không cần kết hợp với lớp `Box` ở chương trình chạy đầy đủ. Khi dùng `KeyedHolder<String, Long>`:

- Quan hệ superclass: `ValueHolder<String>`, cho nên `get()` trả `String`.
- Quan hệ interface: `HasKey<Long>`, cho nên `key()` trả `Long`.
- `T` và `K` đều được khai báo trên lớp con, rồi truyền vào **hai hợp đồng khác nhau**.

Có thể gán một đối tượng `KeyedHolder<String, Long>` cho biến kiểu `ValueHolder<String>` hoặc `HasKey<Long>`. Nhưng qua biến kiểu interface, chỉ nhìn thấy các method do interface khai báo.

Nếu interface tự kế thừa generic interface khác, cũng có thể **khai báo thêm type parameter**:

```java
interface Reader<T> {
    T read();
}

interface AuditedReader<T, AUDIT> extends Reader<T> {
    AUDIT audit();
}
```

`AuditedReader<String, Integer>` là subtype của `Reader<String>`, đồng thời có `audit()` trả `Integer`. Đây là **kế thừa interface**, không phải class inheritance; cú pháp vẫn sử dụng ánh xạ type parameter tương tự.

## 7. Type bounds khi lớp con thêm tham số kiểu

Nếu superclass có bound:

```java
class NumericBox<N extends Number> {
    private final N number;

    NumericBox(N number) {
        this.number = number;
    }

    double value() {
        return number.doubleValue();
    }
}
```

thì subclass chuyển một type parameter của mình lên cha phải khai báo bound tương thích:

```java
class Measured<N extends Number, UNIT> extends NumericBox<N> {
    private final UNIT unit;

    Measured(N number, UNIT unit) {
        super(number);
        this.unit = unit;
    }

    UNIT unit() {
        return unit;
    }
}
```

Đây là hai lớp minh họa hợp lệ đặt trong cùng bối cảnh thích hợp. `Measured<Integer, String>` hợp lệ; `Measured<String, String>` không hợp lệ vì `String` không phải subtype của `Number`.

Cách viết sai:

```java
// class WrongMeasured<N, UNIT> extends NumericBox<N> { }
// Không biên dịch: N không được ràng buộc là subtype của Number.
```

Lớp con cũng có thể đặt bound lên **tham số kiểu mới** nếu cần, ví dụ `<T, M extends Comparable<M>>`, với điều kiện các bound và kiểu được sử dụng phù hợp. Không cần áp bound chỉ để thêm tham số: `M` tự do là hợp lệ nếu API không cần thao tác chuyên biệt trên `M`.

### Nhiều bounds và ràng buộc kết hợp

Một type parameter có thể có multiple bounds như `<X extends Number & Comparable<X>>`. Khi có bound là class, nó phải đứng trước interface bound, sau đó các interface phân cách bằng `&`. Không viết `<X super Number>` để khai báo lower bound; `? super X` là wildcard tại vị trí sử dụng một generic type.

Tham số kiểu lớp con có thể liên hệ nhau theo bound, nhưng việc thêm quá nhiều ràng buộc khiến chữ ký khó hiểu. Hãy đặt bound để phản ánh những thao tác thực sự cần thiết, chứ không chỉ để tăng độ phức tạp.

## 8. Kiểm tra subtype đúng với từng type argument

`TaggedBox<String,Integer> extends Box<String>`, nên một đối tượng TaggedBox ấy có thể được dùng ở nơi nhận `Box<String>`; type argument **M=Integer** chỉ phục vụ phần metadata của lớp con.

```java
TaggedBox<String, Integer> tagged = TaggedBox.of("x", 1);
Box<String> base = tagged;
// Box<Object> tooWide = tagged; // Không hợp lệ.
List<? extends Box<String>> view = List.of(tagged);
```

**Phân biệt hai tầng bất biến:** `Box<String>` không là `Box<Object>`; tương tự `List<TaggedBox<String,Integer>>` không tự là `List<Box<String>>`. Nếu chỉ đọc phần tử, bounded wildcard như `List<? extends Box<String>>` giúp biểu diễn đúng quan hệ; nó không cho quyền ghi thêm một Box tùy ý. Đây là giới hạn của **type arguments tại nơi sử dụng**, không phủ nhận việc bản thân TaggedBox kế thừa Box<String>.

## 9. Những giới hạn của Java khi thiết kế subclass generic

### 9.1. Java chỉ hỗ trợ một superclass

Một class Java chỉ có thể `extends` **một** class, nhưng có thể `implements` nhiều interface. Vì vậy muốn tích hợp nhiều hợp đồng kiểu, hãy chọn một superclass rồi thêm các interface generic hoặc ưu tiên composition khi phù hợp. Thêm type parameter mới không biến Java thành ngôn ngữ có multiple class inheritance.

### 9.2. Không kế thừa hai cách tham số hóa của cùng interface

Một subtype không thể đồng thời kế thừa `Holder<String>` và `Holder<Integer>` của cùng khai báo `Holder<T>`, kể cả khi các đường kế thừa đi qua interface trung gian. Đây là quy tắc nhất quán superinterface của Java, **không chỉ** là xung đột overload do erasure; interface rỗng `Marker<T>` cũng chịu hạn chế ấy.

Nếu một lớp cần vừa giữ giá trị T vừa cung cấp ID, hai **interface khác nhau** như `ValueSource<T>` và `Identifiable<ID>` (đã dùng ở mục 4/6) diễn đạt vai trò rõ hơn. Nếu cần hai instantiations của **cùng** interface, tạo hai đối tượng và phối hợp bằng composition thay vì bắt một lớp kế thừa cả hai.

### 9.3. Raw type làm mất kiểm tra kiểu

Viết `extends Base` thay vì `extends Base<String>` khi `Base` là generic class có thể dẫn tới sử dụng **raw type** và mất bảo đảm kiểu. Không nên bỏ `<...>` chỉ để compiler chấp nhận mã cũ. Trong phần lớn chương trình hiện đại, lớp con cần **truyền type argument phù hợp** cho generic superclass.

Ví dụ:

```java
// Tránh: class RawChild<X> extends Box { ... }
// Ưu tiên: class TypedChild<X> extends Box<X> { ... }
```

Hai dòng là **phác thảo cú pháp**, không phải định nghĩa lớp hoàn chỉnh. Raw type có thể gây unchecked warnings, cast do compiler thêm vào, và nguy cơ `ClassCastException` ở runtime.

### 9.4. Type erasure và việc không thể kiểm tra tham số kiểu cụ thể tại runtime

`TaggedBox<String, Integer>` và `TaggedBox<Integer, String>` đều là các cách tham số hóa của cùng lớp `TaggedBox`, không phải hai class runtime riêng.

Ví dụ hợp lệ:

```java
if (obj instanceof TaggedBox<?, ?>) {
    System.out.println("some tagged box");
}
```

Đây là đoạn minh họa cần có biến `obj` thuộc kiểu phù hợp và nằm trong method. Không viết `obj instanceof TaggedBox<String, Integer>` như thể JVM có thể kiểm tra mọi type argument đã bị xóa. Kết quả `instanceof TaggedBox<?, ?>` xác nhận loại raw class một cách an toàn cho pattern chung, **không xác nhận** `T = String` và `M = Integer`.

Lưu ý: dùng `@Override` trên method override thực sự giúp compiler kiểm tra chữ ký. Với generic inheritance, bridge method có thể được compiler tạo sau erasure để duy trì overriding; không nên tự viết bridge method hoặc dựa vào sự tồn tại của nó như một API công khai.

## 10. Tham số kiểu của subclass và tham số kiểu của method độc lập

Trong `TaggedBox<T, M>`, bạn có thể khai báo một generic method riêng:

```java
public <U> TaggedBox<U, M> mapValue(
        Function<? super T, ? extends U> mapper) {
    return TaggedBox.of(mapper.apply(get()), marker);
}
```

Đây là **trích đoạn method** từ ví dụ `TaggedBox<T,M>`; cần có `Function`, truy cập `get()`, trường `marker` và factory `of` thích hợp trong class chứa method.

Ba phạm vi kiểu khác nhau:

- `T`: class type parameter được truyền cho superclass `Box<T>`.
- `M`: class type parameter bổ sung của subclass, giữ nguyên trong kết quả.
- `U`: **method type parameter mới** mô tả kiểu của giá trị sau biến đổi.

Lời gọi `TaggedBox<String, Integer>.mapValue(String::length)` không phải đổi `T` của object đang tồn tại. Nó **tạo một `TaggedBox<Integer, Integer>` mới** trong ví dụ, còn object cũ vẫn chứa `String`. Đây là lợi ích của thiết kế bất biến: phép biến đổi trả về object mới với quan hệ type parameters được thể hiện tường minh.

Một static factory thuộc `TaggedBox<T, M>` phải tự khai báo type parameters của **method**, vì static context không dùng trực tiếp tham số kiểu của class. Ví dụ:

```java
static <V, L> TaggedBox<V, L> of(V value, L marker) {
    return new TaggedBox<>(value, marker);
}
```

Chữ `V`, `L` được chọn để nhấn mạnh chúng thuộc riêng factory; chúng không “mượn” `T`, `M` của một instance. Có thể đặt tên factory là `<T, M>` theo quy tắc shadowing, nhưng làm vậy dễ gây hiểu nhầm trong bài học về phạm vi kiểu.

## 11. Những lỗi phổ biến khi thêm type parameter ở lớp con

**Lỗi 1 — Nhầm số type parameter của cha và con.** Nếu cha là `Box<T>`, con vẫn có thể là `TaggedBox<T, M>`. Tuy nhiên, mệnh đề `extends Box<T>` phải truyền **đúng một** type argument phù hợp cho `Box`; không viết `extends Box<T, M>` nếu `Box` chỉ khai báo một tham số kiểu.

**Lỗi 2 — Quên chuyển type parameter cho lớp cha.** `extends Box` dùng raw type; `extends Box<T>` giữ an toàn kiểu và quan hệ kiểu trả về của các method kế thừa.

**Lỗi 3 — Tưởng `M` tự động nằm trong superclass.** `TaggedBox<T, M> extends Box<T>` không làm `Box<T>` biết `M`. Muốn sử dụng `M` qua một biến có kiểu `Box<T>`, cần thiết kế thêm API ở lớp cha, một interface khác hoặc kiểm tra/cast an toàn khi có lý do chính đáng.

**Lỗi 4 — Không gọi constructor cha phù hợp.** Nếu `Box<T>` chỉ có constructor `Box(T value)`, constructor lớp con phải gọi `super(value)` làm thao tác đầu tiên hoặc dùng constructor delegation hợp lệ. Không có constructor mặc định `Box()` để compiler tự gọi.

**Lỗi 5 — Truyền sai type parameter cho cha.** `Child<A,B> extends Parent<B>` nghĩa là kiểu cha là `Parent<B>`. Nếu chủ ý giữ kiểu `A` mà lại viết `Parent<B>`, các method kế thừa sẽ có kiểu sai với hợp đồng mong muốn.

**Lỗi 6 — Quên bound khi cha có bound.** `Base<N extends Number>` không chấp nhận một `N` tự do hoàn toàn từ lớp con; khai báo `<N extends Number, M>` hoặc dùng một type argument thỏa ràng buộc.

**Lỗi 7 — Nhầm quan hệ subtype với variance.** `TaggedBox<String, Integer>` là subtype của `Box<String>`, nhưng không của `Box<Object>` hay `TaggedBox<Object, Integer>`. Cần wildcard phù hợp nếu API chỉ muốn đọc ở kiểu rộng.

**Lỗi 8 — Nghĩ một lớp con với `<T, M>` luôn phải dùng `T` làm kiểu cha.** Không bắt buộc. `class Child<T, M> extends Parent<M>` và `class Child<M> extends Parent<String>` có thể là thiết kế hợp lệ; phải chọn ánh xạ theo ý nghĩa dữ liệu.

**Lỗi 9 — Nhầm tham số kiểu class và method.** `<U> TaggedBox<U, M> mapValue(...)` khai báo `U` thuộc method; `U` không thay đổi kiểu của một object `TaggedBox<T, M>` đã có.

**Lỗi 10 — Cố dùng `T` hoặc `M` của class trong static factory mà không khai báo riêng.** Phương thức static phải có type parameters mới như `static <V,L> TaggedBox<V,L> of(...)`.

**Lỗi 11 — Sử dụng raw type rồi cast tùy tiện.** Nếu bắt buộc tương tác với mã Java cũ, cô lập raw type và validate dữ liệu tại ranh giới; đừng dùng cast không kiểm tra làm giải pháp kế thừa tổng quát.

**Lỗi 12 — Giả định `final` làm các trường kiểu `T` và `M` bất biến sâu.** `private final T value` chỉ ngăn gán lại tham chiếu. Nếu `T` hoặc `M` trỏ đến list mutable, trạng thái bên trong list vẫn có thể thay đổi.

**Lỗi 13 — Viết nhiều nhánh kế thừa cùng một generic interface với type argument xung đột.** Java không chấp nhận kế thừa cùng interface đó đồng thời dưới hai phép tham số hóa khác nhau trong một hệ phân cấp. Cần sửa mô hình hoặc sử dụng interface với nhiều tham số kiểu.

## 12. Cách quyết định có nên thêm type parameter ở lớp con

Khi thiết kế API, hãy kiểm tra bốn câu hỏi:

1. **Dữ liệu mới có một kiểu độc lập, ổn định trong suốt vòng đời object không?** Ví dụ `TaggedBox<T, M>` cần giữ type của nhãn, nên `M` có giá trị.
2. **Lớp cha đã mô tả phần nào?** Nếu cha chỉ quản lý `T`, subclass chỉ nên bổ sung thứ không thuộc hợp đồng đó; đừng thay đổi ý nghĩa `T` bất ngờ.
3. **Quan hệ `extends Parent<...>` có bảo toàn đúng kiểu kế thừa không?** Việc điền `T`, `M`, `List<T>` hay kiểu cố định cần theo ý nghĩa nghiệp vụ, không theo tên ký hiệu.
4. **Có cần inheritance không?** Nếu type mới chỉ là một thành phần dữ liệu kết hợp nhưng không thật sự là một subtype của cha, composition có thể đơn giản hơn.

Ví dụ thay thế bằng composition nếu không có quan hệ “is-a” thực sự:

```java
final class Annotated<T, M> {
    private final T value;
    private final M metadata;

    Annotated(T value, M metadata) {
        this.value = value;
        this.metadata = metadata;
    }

    T value() {
        return value;
    }

    M metadata() {
        return metadata;
    }
}
```

Đây là **một lớp minh họa**, không kế thừa `Box<T>`; nó gộp hai thành phần dưới một kiểu thay vì tạo subtype. Nếu người dùng API không cần thay `Annotated<T, M>` vào chỗ `Box<T>`, đây có thể là lựa chọn dễ duy trì hơn.

## 13. Câu hỏi tự kiểm tra có đáp án

**Câu 1.** `class Child<T, M> extends Parent<T>` khai báo bao nhiêu type parameters ở lớp con?  
**Đáp án:** Hai: `T` và `M`. Chỉ `T` được truyền làm type argument cho `Parent<T>`.

**Câu 2.** Với `Child<String, Integer> extends Parent<T>`, supertype được tham số hóa là gì?  
**Đáp án:** `Parent<String>` nếu khai báo cụ thể là `class Child<T,M> extends Parent<T>`.

**Câu 3.** `class Child<K,V> extends Parent<V>` và `Child<String,Long>` thì `Parent` có kiểu gì?  
**Đáp án:** `Parent<Long>`. Ánh xạ do `extends Parent<V>` xác định.

**Câu 4.** `TextTagged<Long> extends Box<String>` có trở thành `Box<Long>` không?  
**Đáp án:** Không. Lớp cha được cố định ở `String`; `Long` chỉ là type argument của metadata lớp con.

**Câu 5.** `TaggedBox<String,Integer>` có gán được cho `Box<String>` không?  
**Đáp án:** Có, do kế thừa; nhưng nó không tự gán được cho `Box<Object>`.

**Câu 6.** Nếu `Box<T>` có constructor `Box(T value)` và không có no-arg constructor, constructor của subclass nên làm gì?  
**Đáp án:** Gọi `super(value)` hoặc constructor delegation phù hợp để khởi tạo phần cha.

**Câu 7.** `class Measured<N,UNIT> extends NumericBox<N>` có hợp lệ nếu `NumericBox<N extends Number>` không?  
**Đáp án:** Không. Cần ràng buộc `N extends Number` ở lớp con hoặc truyền một type argument đã thỏa bound.

**Câu 8.** Có thể vừa `extends Box<T>` vừa `implements Identifiable<ID>` không?  
**Đáp án:** Có. Class chỉ có một superclass, nhưng có thể thực thi interface generic với type argument độc lập.

**Câu 9.** `<U> TaggedBox<U,M> mapValue(...)` thuộc phạm vi kiểu nào?  
**Đáp án:** `U` thuộc method, `T` và `M` thuộc class. Kết quả có thể mang kiểu giá trị mới `U` và giữ metadata kiểu `M`.

**Câu 10.** `List<TaggedBox<String,Integer>>` có phải subtype của `List<Box<String>>` không?  
**Đáp án:** Không. Nếu chỉ đọc, cân nhắc `List<? extends Box<String>>`.

**Câu 11.** Vì sao không dùng `instanceof TaggedBox<String,Integer>` để xác minh hai type arguments?  
**Đáp án:** Do type erasure; phép kiểm tra kiểu tham số hóa cụ thể đó không hợp lệ ở runtime Java thông thường.

**Câu 12.** Khi nào nên tạo `Annotated<T,M>` bằng composition thay vì `TaggedBox<T,M> extends Box<T>`?  
**Đáp án:** Khi dữ liệu chỉ cần kết hợp hai thành phần mà không cần hợp đồng subtype “is-a Box”; composition giúp tránh ràng buộc kế thừa không cần thiết.

**Câu 13.** Type parameter mới `M` có bắt buộc khác kiểu `T` không?  
**Đáp án:** Không. `TaggedBox<String,String>` vẫn hợp lệ; đây là hai vai trò kiểu độc lập, không yêu cầu hai lớp khác nhau.

**Câu 14.** Nếu lớp con có `static <V,L> TaggedBox<V,L> of(V value,L tag)`, `V` và `L` có phải `T` và `M` của instance class không?  
**Đáp án:** Không; chúng được khai báo riêng ở method static và dùng để suy luận kiểu của object `TaggedBox<V,L>` được tạo.

**Câu 15.** Nếu `Box<String> parentView` trỏ đến một `TaggedBox<String,Integer>`, `parentView.describe()` gọi bản nào?  
**Đáp án:** Nếu `describe()` là phương thức instance được override, Java dùng dynamic dispatch tới bản override của `TaggedBox`; còn static type `Box<String>` quyết định những method nào được gọi trực tiếp.

**Tổng kết:** lớp con generic **được quyền thêm tham số kiểu mới** mà không sửa số tham số kiểu của cha. Điều quan trọng là khai báo `<...>` trên lớp con, ánh xạ rõ các kiểu trong `extends Parent<...>` và `implements Interface<...>`, giữ đúng bounds, constructor, quan hệ subtype và giới hạn invariance. Nếu quan hệ kế thừa thực sự có ý nghĩa, thiết kế này cho phép mở rộng dữ liệu/hành vi mà vẫn bảo toàn khả năng kiểm tra kiểu ở compile time.
