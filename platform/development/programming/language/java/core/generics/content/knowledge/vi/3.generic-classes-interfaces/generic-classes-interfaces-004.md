# Khai báo giao diện generic và hợp đồng theo kiểu trong Java

**Generic interface** là giao diện khai báo một hoặc nhiều **tham số kiểu** ngay sau tên, ví dụ `interface Repository<ID, T>`. Interface này mô tả các thao tác có liên hệ kiểu: khóa định danh phải có kiểu `ID`, còn dữ liệu được lưu và trả về có kiểu `T`. Khi sử dụng `Repository<Long, User>`, trình biên dịch kiểm tra rằng phương thức lưu nhận `Long` và `User`, trong khi phương thức tìm kiếm trả về `Optional<User>`.

Giao diện generic đặc biệt hữu ích khi nhiều loại dữ liệu chia sẻ **cùng một hợp đồng**, còn kiểu đầu vào và đầu ra cần giữ nhất quán. Bài này tập trung vào cú pháp khai báo, triển khai bằng `implements`, kế thừa qua `extends`, các loại phương thức được phép khai báo, giới hạn kiểu và những lỗi phổ biến. Ví dụ hoàn chỉnh sử dụng Java 17 trở lên.

## 1. Tại sao cần interface generic?

Giả sử ứng dụng có kho người dùng được đánh ID bằng `Long`, kho sản phẩm được đánh mã bằng `String`. Nếu viết hai interface độc lập, các chữ ký dễ trùng lặp:

```java
interface UserStore {
    void save(Long id, User user);
    User findById(Long id);
}

interface ProductStore {
    void save(String code, Product product);
    Product findById(String code);
}
```

Các đoạn ngắn trong bài là **mã minh họa nằm trong một ngữ cảnh phù hợp**; `User` và `Product` ở trên là các kiểu nghiệp vụ giả định, không phải tệp Java hoàn chỉnh.

Ta có thể mô tả mối quan hệ chung bằng hai tham số kiểu:

```java
interface Repository<ID, T> {
    void save(ID id, T entity);
    java.util.Optional<T> findById(ID id);
}
```

`ID` là kiểu của khóa; `T` là kiểu thực thể. Sử dụng interface bằng cách truyền **đối số kiểu**:

```java
Repository<Long, User> users;
Repository<String, Product> products;
```

Trình biên dịch biết rằng `users.save` nhận `(Long, User)`, còn `products.save` nhận `(String, Product)`. Tên `ID` và `T` chỉ là tham số kiểu của Java, không phải hai biến dữ liệu hay các class được tạo ra ở runtime.

Một phiên bản không generic sẽ làm yếu hợp đồng:

```java
interface WeakRepository {
    void save(Object id, Object entity);
    Object findById(Object id);
}
```

Ở đây, caller phải tự ép kiểu giá trị tìm được và có thể lẫn kiểu khóa với kiểu dữ liệu. Generics giúp chuyển nhiều lỗi kiểu từ lúc chạy sang **lúc biên dịch**. Tuy nhiên, chúng không tự kiểm tra quy tắc nghiệp vụ như ID có tồn tại, entity đã hợp lệ hay người gọi có quyền xem dữ liệu.

## 2. Cú pháp khai báo và cách đọc hợp đồng

Dạng một tham số:

```java
interface Holder<T> {
    void set(T value);
    T get();
}
```

Dạng nhiều tham số:

```java
interface Dictionary<K, V> {
    void put(K key, V value);
    V get(K key);
}
```

| Thành phần | Ý nghĩa |
| --- | --- |
| `interface Holder<T>` | **Khai báo** tham số kiểu `T` trong phạm vi interface |
| `Holder<String>` | **Sử dụng** interface với đối số kiểu `String` |
| `interface Dictionary<K,V>` | Khai báo hai tham số kiểu, với vai trò khóa và giá trị |
| `Dictionary<Long,String>` | Ràng buộc `K = Long`, `V = String` cho tham chiếu cụ thể |
| `new MemoryDictionary<>()` | Toán tử diamond `<>` nhờ ngữ cảnh để suy luận các đối số kiểu của constructor |

Trong `Holder<String>`, trình biên dịch xem `get()` là phương thức trả `String`; trong `Holder<Integer>`, phương thức ấy trả `Integer`. Không cần ép `Object` một cách thủ công khi gọi qua tham chiếu có kiểu đầy đủ.

Các tên thông dụng là `T` (type), `E` (element), `K` (key), `V` (value). Nếu bài toán có nhiều kiểu, một tên diễn tả rõ vai trò như `ID` cũng hợp lệ. Không dùng tên có ý nghĩa nhập nhằng khiến caller khó suy luận hợp đồng.

**Cần nhớ:** tham số generic Java thông thường là kiểu tham chiếu. `Repository<long, User>` không hợp lệ; dùng `Repository<Long, User>`. Boxing/unboxing có thể xảy ra khi truyền số primitive tới vị trí nhận wrapper.

## 3. Chương trình Java 17+ hoàn chỉnh

Chương trình sau minh họa cùng một interface cho kho người dùng (`Long` → `User`) và kho tồn kho (`String` → `Integer`). Hợp đồng đọc được tách khỏi hợp đồng ghi; phương thức `exists` là phương thức `default`. Giao diện `Converter<I,O>` minh họa một phương thức generic riêng bên trong interface generic.

Lưu đúng tên tệp **`Main.java`**:

```java
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;

public class Main {
    record User(long id, String name) {}

    interface ReadRepository<ID, T> {
        Optional<T> findById(ID id);

        default boolean exists(ID id) {
            return findById(id).isPresent();
        }
    }

    interface Repository<ID, T> extends ReadRepository<ID, T> {
        void save(ID id, T entity);
    }

    static final class InMemoryRepository<ID, T>
            implements Repository<ID, T> {
        private final Map<ID, T> entries = new LinkedHashMap<>();

        @Override
        public void save(ID id, T entity) {
            entries.put(
                    Objects.requireNonNull(id, "id"),
                    Objects.requireNonNull(entity, "entity"));
        }

        @Override
        public Optional<T> findById(ID id) {
            return Optional.ofNullable(entries.get(id));
        }
    }

    @FunctionalInterface
    interface Converter<I, O> {
        O convert(I input);

        default <R> Converter<I, R> andThen(
                Converter<? super O, ? extends R> next) {
            Objects.requireNonNull(next, "next");
            return input -> next.convert(convert(input));
        }
    }

    public static void main(String[] args) {
        Repository<Long, User> users = new InMemoryRepository<>();
        users.save(101L, new User(101L, "Lan"));

        System.out.println("user: "
                + users.findById(101L)
                        .map(User::name)
                        .orElse("not found"));
        System.out.println("exists 999: " + users.exists(999L));

        Repository<String, Integer> stock = new InMemoryRepository<>();
        stock.save("SKU-01", 7);
        System.out.println("stock: "
                + stock.findById("SKU-01").orElse(-1));

        Converter<String, Integer> count = String::length;
        Converter<String, String> label =
                count.andThen(n -> "length=" + n);

        System.out.println("length: " + count.convert("Java"));
        System.out.println("label: " + label.convert("Java"));

        // users.save("101", new User(101L, "Lan"));
        // Sai kiểu ID: Repository<Long,User> yêu cầu Long.
    }
}
```

Chạy với JDK 17 trở lên:

```bash
javac -encoding UTF-8 Main.java
java Main
```

Stdout:

```text
user: Lan
exists 999: false
stock: 7
length: 4
label: length=4
```

### Tại sao chương trình này kiểm tra được hợp đồng kiểu?

- `Repository<Long,User>` nghĩa là `save` yêu cầu một `Long` và một `User`; `findById` trả `Optional<User>`. Dòng truyền `"101"` (kiểu `String`) bị để comment vì **không biên dịch** nếu bật lên.
- `Repository<String,Integer>` dùng **cùng định nghĩa** `Repository<ID,T>` và **cùng class triển khai** `InMemoryRepository<ID,T>`, nhưng đối số kiểu khác; `findById("SKU-01")` trả `Optional<Integer>`.
- `InMemoryRepository<ID,T>` giữ hai tham số kiểu khi `implements Repository<ID,T>`; nó lưu dữ liệu trong `Map<ID,T>` và dùng `@Override` để trình biên dịch kiểm tra rằng chữ ký thực thi đúng interface.
- `ReadRepository<ID,T>` định nghĩa API đọc; `Repository<ID,T>` kế thừa qua `extends`. Phương thức `default exists(ID)` hoạt động theo đúng kiểu ID của repository đã tham số hóa.
- `Converter<I,O>` giữ quan hệ kiểu đầu vào và kiểu đầu ra. `count` có kiểu `Converter<String,Integer>`; `count.andThen(...)` tạo `Converter<String,String>` bằng một bước biến đổi kết quả từ `Integer` sang `String`.

`InMemoryRepository` chỉ là ví dụ chạy trong bộ nhớ, không đại diện cho repository truy cập database, không tự bảo đảm transaction hoặc an toàn đa luồng. Quy tắc không cho lưu khóa và entity `null` đến từ `Objects.requireNonNull` trong **implementation**, không phải do cú pháp `<ID,T>`.

## 4. Hai kiểu triển khai interface generic

### 4.1. Lớp triển khai vẫn giữ tham số kiểu

```java
interface Store<K, V> {
    void put(K key, V value);
    V get(K key);
}

class MemoryStore<K, V> implements Store<K, V> {
    private final java.util.Map<K, V> data =
            new java.util.HashMap<>();

    @Override
    public void put(K key, V value) {
        data.put(key, value);
    }

    @Override
    public V get(K key) {
        return data.get(key);
    }
}
```

`MemoryStore<K,V>` tiếp tục là class generic. Ta có thể dùng `Store<String,Integer>` hay `Store<Long,User>` mà không phải thay cấu trúc class. Chữ ký của `put` và `get` phải phù hợp với đúng `K`, `V` đã khai báo.

### 4.2. Lớp triển khai cố định kiểu cụ thể

```java
class StringIntStore implements Store<String, Integer> {
    private final java.util.Map<String, Integer> data =
            new java.util.HashMap<>();

    @Override
    public void put(String key, Integer value) {
        data.put(key, value);
    }

    @Override
    public Integer get(String key) {
        return data.get(key);
    }
}
```

`StringIntStore` không có `<K,V>` trên tên class; nó chọn cố định `String` và `Integer` lúc khai báo `implements Store<String,Integer>`. Vì thế, implementation phải cung cấp các method tương ứng:

- `public void put(String, Integer)`
- `public Integer get(String)`

Không thể lặng lẽ thay `put(String,Integer)` bằng `put(String,String)` rồi coi là đã triển khai phương thức bắt buộc; class sẽ không còn đáp ứng hợp đồng.

**Đặc điểm chung:** phương thức của interface được khai báo abstract là `public` (trừ những trường hợp đặc biệt của các loại phương thức khác), nên method override trong class phải là `public`. `@Override` giúp phát hiện sai tên, sai tham số và các lỗi làm cho method không còn thực sự override.

Nếu class chỉ thực hiện một phần hợp đồng abstract, class đó phải được khai báo `abstract` để class con có thể bổ sung implementation.

## 5. Interface generic kế thừa interface khác

Một interface có thể **kế thừa** một hoặc nhiều interface, qua `extends`, đồng thời giữ hoặc cố định các đối số kiểu.

**Giữ nguyên kiểu giữa các tầng:**

```java
interface Reader<ID, T> {
    java.util.Optional<T> find(ID id);
}

interface Writer<ID, T> {
    void save(ID id, T item);
}

interface ReadWriteStore<ID, T>
        extends Reader<ID, T>, Writer<ID, T> {
}
```

Với `ReadWriteStore<Long, User>`, `find` nhận `Long` trả `Optional<User>`, còn `save` nhận `Long,User`. Mối quan hệ kiểu được truyền xuyên qua từng interface, không cần viết lại tất cả phương thức.

**Cố định đối số kiểu ở interface con:**

```java
interface IdLookup<T> {
    T find(long id);
}

interface UserLookup extends IdLookup<User> {
}
```

`UserLookup` không còn tham số kiểu; nó chọn `T = User`. Lớp implements `UserLookup` phải thực hiện `User find(long id)` khi không có implementation thích hợp được kế thừa.

**Bổ sung hành vi mặc định sau khi chuyên biệt hóa:**

```java
interface Sender<T> {
    void send(T message);
}

interface TextSender extends Sender<String> {
    default void sendUpperCase(String value) {
        send(value.toUpperCase(java.util.Locale.ROOT));
    }
}
```

`TextSender` kế thừa hợp đồng `send(String)` và bổ sung một thao tác cụ thể cho chuỗi. Nó không tự định nghĩa đích gửi; lớp triển khai `TextSender` vẫn phải cung cấp `send(String)`.

Interface có thể kế thừa nhiều interface khi chữ ký tương thích. Nếu hai interface cung cấp các phương thức `default` xung đột, lớp triển khai thường phải override để giải quyết rõ ràng. Không thể tùy tiện thừa hưởng hai cách tham số hóa khác nhau của cùng một generic interface, như `Comparable<String>` và `Comparable<Integer>`, vì có thể xung đột do type erasure.

## 6. Phân biệt type parameter của interface và của method

### 6.1. `T` khai báo trên interface

```java
interface Box<T> {
    void set(T value);
    T get();
}
```

Một instance được xem qua `Box<String>` sử dụng `T = String` ở cả hai method; `Box<Integer>` sử dụng `T = Integer`. `T` thuộc **toàn bộ hợp đồng instance**.

### 6.2. Method tự khai báo `<R>`

```java
interface Mapper<T> {
    <R> R map(
            T source,
            java.util.function.Function<? super T, ? extends R> function);
}
```

`T` được chọn khi sử dụng `Mapper<T>`. Ngược lại, `R` có thể khác giữa các lời gọi của `map`. Dấu `<R>` **phải nằm trước kiểu trả về** `R`; nó là phần khai báo một method generic riêng.

Nếu chỉ cần một thuật toán generic ở đúng một method và không cần giữ cùng `T` xuyên các method, có thể khai báo method-level generic trong một interface không generic:

```java
interface Identity {
    <R> R same(R value);
}
```

Tránh đặt tên phương thức trùng tên tham số kiểu của interface nếu việc đó che khuất ý nghĩa của một tham số kiểu khác; chẳng hạn thêm một `<T>` mới ở cấp method trong `interface Box<T>` sẽ tạo một `T` riêng, dễ làm người đọc hiểu nhầm.

### 6.3. Method `default` dùng kiểu của interface

```java
interface Matcher<T> {
    boolean matches(T value);

    default boolean rejects(T value) {
        return !matches(value);
    }
}
```

`default` có thân phương thức, được lớp triển khai kế thừa hoặc override khi cần. `rejects` vẫn nhận đúng `T`. Đây là cách chia sẻ hành vi mặc định mà không buộc mọi implementation sao chép cùng một đoạn logic.

Trong `Main.java`, `ReadRepository<ID,T>` có `default boolean exists(ID id)` gọi `findById(ID)`. Type parameter không thay đổi giữa hai lời gọi, và implementation không phải viết lại `exists`.

### 6.4. Method `static` tự khai báo type parameter khi cần

Method static của generic interface không thể sử dụng trực tiếp tham số kiểu `T` thuộc instance interface:

```java
interface Factory<T> {
    T create();

    static <R> Factory<R> of(
            java.util.function.Supplier<? extends R> source) {
        java.util.Objects.requireNonNull(source);
        return source::get;
    }
}
```

Ở `of`, `<R>` là tham số kiểu **của phương thức static**, còn `T` thuộc hợp đồng `Factory<T>` khi sử dụng một factory instance. `Factory.of(() -> "ready")` có thể suy luận kiểu `Factory<String>`.

Đoạn giả định sau là lỗi:

```java
// Sai: T chỉ được khai báo trên Factory<T>.
// static T createDefault() { ... }
```

Gọi static method bằng tên interface (`Factory.of(...)`), không gọi như một instance method được kế thừa qua object implementing interface.

## 7. Functional interface vẫn có thể generic

Functional interface có một phương thức abstract chức năng, là target type cho lambda hoặc method reference.

```java
@FunctionalInterface
interface Converter<I, O> {
    O convert(I input);
}
```

Các đối số kiểu đảm bảo lambda được kiểm tra đúng chữ ký:

```java
Converter<String, Integer> count = String::length;
Integer size = count.convert("Java");
```

`String::length` phù hợp vì nhận chuỗi và trả `int` (autobox thành `Integer`). Nếu viết:

```java
// Không biên dịch:
// Converter<String, Integer> wrong = text -> text.toUpperCase();
```

thì kết quả lambda là `String` trong khi `O = Integer`, nên trình biên dịch từ chối.

`@FunctionalInterface` vẫn cho phép `default` và `static` methods, vì các phương thức này không được tính như những abstract method bổ sung trong hợp đồng SAM (single abstract method). Ví dụ `Converter<I,O>` trong chương trình `Main.java` vừa có abstract `convert`, vừa có default `andThen`.

**Kết hợp các converter:** phần chữ ký

```java
default <R> Converter<I, R> andThen(
        Converter<? super O, ? extends R> next)
```

cho phép kết nối đầu ra kiểu `O` của bước thứ nhất với đầu vào mà bước thứ hai chấp nhận, rồi trả về converter kiểu `I -> R`. `? super O`/`? extends R` là wildcard diễn đạt khả năng nhận input và tạo output tương thích; chúng giúp API linh hoạt hơn mà vẫn được kiểm tra kiểu.

## 8. Ràng buộc kiểu bằng `extends`

Không phải lúc nào mọi kiểu `T` đều phù hợp. Nếu implementation cần gọi một method cụ thể trên entity, generic interface có thể khai báo **bound**:

```java
interface Identified<ID> {
    ID id();
}

interface EntityStore<ID, T extends Identified<ID>> {
    void save(T entity);
    java.util.Optional<T> findById(ID id);
}
```

`T extends Identified<ID>` bảo đảm kiểu thực thể có method `id()` trả đúng loại ID. Một record có thể đáp ứng ràng buộc:

```java
record Ticket(Long id, String title) implements Identified<Long> {}

class TicketStore implements EntityStore<Long, Ticket> {
    private final java.util.Map<Long, Ticket> values =
            new java.util.HashMap<>();

    @Override
    public void save(Ticket ticket) {
        values.put(ticket.id(), ticket);
    }

    @Override
    public java.util.Optional<Ticket> findById(Long id) {
        return java.util.Optional.ofNullable(values.get(id));
    }
}
```

Nếu một kiểu chỉ implements `Identified<String>`, nó không được chọn làm `T` trong `EntityStore<Long,T>` trừ khi cũng thỏa mãn bound thích hợp. Bound làm hợp đồng **mạnh hơn**: không chỉ “ID có kiểu `Long`”, mà thực thể phải có khả năng cung cấp ID theo cùng kiểu.

Có thể khai báo nhiều bound khi thực sự cần, ví dụ `T extends Identified<ID> & java.io.Serializable`; nếu danh sách có class bound, class phải xuất hiện đầu tiên rồi mới đến interface bound.

**Không thêm bound để làm mã trông phức tạp hơn.** Nếu method không sử dụng khả năng được bound cung cấp, cân nhắc giữ hợp đồng đơn giản.

## 9. Hợp đồng kiểu không đồng nghĩa với hợp đồng hành vi

`Repository<ID,T>` giúp trả lời:

- `save` phải nhận kiểu khóa và entity nào?
- `findById` trả kiểu dữ liệu nào?
- Lớp triển khai có override đúng các method không?

Nhưng interface **không tự quyết định**:

- `save` ghi đè entity cũ hay từ chối trùng ID;
- `findById` trả `Optional.empty()` khi không có dữ liệu hay phát sinh lỗi hạ tầng;
- có cho phép khóa hoặc giá trị `null` không;
- dữ liệu có được ghi bền vững, có transaction hoặc được bảo vệ trước truy cập đồng thời không;
- quyền đọc và quyền ghi của người dùng được áp dụng thế nào;
- ID được truyền vào có khớp thuộc tính ID bên trong entity không.

Tác giả API phải mô tả và thực thi các quy tắc ấy trong contract/documentation, validation và implementation. Generic interface là **hợp đồng kiểu được trình biên dịch hiểu**, còn semantics nghiệp vụ cần cam kết riêng.

Từ góc nhìn thiết kế, nên dùng tham chiếu kiểu interface khi caller chỉ cần hợp đồng đó:

```java
Repository<Long, User> users = new InMemoryRepository<>();
```

Tác dụng là dễ thay implementation phù hợp mà caller không phụ thuộc trực tiếp vào cấu trúc `Map` nội bộ. Tuy vậy, việc có nhiều interface chỉ mang tính hình thức mà không nêu được một hợp đồng chung thường làm dự án khó đọc hơn.

## 10. Invariance và wildcard khi làm việc qua interface

Generics trong Java **bất biến** theo mặc định. Giả sử `Manager extends Employee`:

```java
Repository<Long, Manager> managers = null;
// Repository<Long, Employee> employees = managers; // Không biên dịch.
```

Lý do: nếu phép gán hợp lệ, caller qua tham chiếu `Repository<Long,Employee>` có thể lưu một `Employee` không phải `Manager` vào kho vốn chỉ chứa `Manager`.

Nếu chỉ đọc, có thể cần một kiểu biến linh hoạt hơn:

```java
ReadRepository<Long, ? extends Employee> readOnly = null;
```

Một `ReadRepository<Long,Manager>` phù hợp để gán cho kiểu đọc rộng hơn ấy, vì biến `readOnly` chỉ biết kết quả là một subtype chưa xác định của `Employee`. Kết quả `findById` có quan hệ với `Optional<? extends Employee>`, nhưng không thể tùy tiện gán thành `Optional<Employee>` do tính bất biến của `Optional`.

Khi thiết kế API, `? extends T` thường hữu ích tại nơi **sản xuất/đọc** `T`; `? super T` thường hữu ích khi **tiêu thụ/ghi** `T`. Quy tắc này định hướng cách dùng, không thay thế việc kiểm tra chữ ký thực tế của từng method.

Raw type làm mất nhiều khả năng kiểm tra:

```java
Repository raw = new InMemoryRepository();
```

Dùng `raw.save(...)` có thể biên dịch cùng cảnh báo `unchecked`, mở đường cho sai kiểu ở runtime. Ưu tiên `Repository<Long,User>` hoặc khai báo có type parameter thích hợp. `Repository<?,?>` tốt hơn raw type khi chỉ muốn giữ một tham chiếu với kiểu không biết trước, nhưng vì chưa biết các kiểu đối số nên không thể tùy ý gọi `save` với giá trị bất kỳ.

## 11. Type erasure và hạn chế ở runtime

Java triển khai generics chủ yếu bằng **type erasure**. Trình biên dịch kiểm tra ràng buộc lúc compile, sau đó phần lớn thông tin đối số kiểu không còn ở object runtime. `InMemoryRepository<Long,User>` và `InMemoryRepository<String,Integer>` đều dùng cùng một class runtime `InMemoryRepository`, chứ không tạo một class JVM mới cho từng cặp kiểu.

Không thể viết điều kiện sau để kiểm tra đầy đủ ID và entity:

```java
// Không biên dịch:
// if (value instanceof Repository<Long, User>) { ... }
```

Cú pháp `value instanceof Repository<?, ?>` có thể kiểm tra đối tượng thuộc loại interface đó, nhưng **không xác minh** tham số thực sự là `Long` và `User`.

Nếu code nhận dữ liệu từ JSON, reflection, raw collection hoặc thư viện cũ, generic type không thay thế validation và kiểm tra kiểu ở ranh giới. Các thư viện JSON có thể cung cấp type reference hoặc schema cho kiểu tham số hóa; API cụ thể phụ thuộc thư viện.

### Bridge methods

Khi lớp triển khai một method generic bằng kiểu cụ thể, compiler đôi khi tạo **bridge method tổng hợp** để giữ đúng cơ chế đa hình sau erasure:

```java
interface Processor<T> {
    T process(T value);
}

class StringProcessor implements Processor<String> {
    @Override
    public String process(String value) {
        return value.trim();
    }
}
```

Bạn chỉ cần triển khai `process(String)`; không tự viết bridge method. Kiến thức này giải thích tại sao khi xem bytecode hoặc Reflection có thể thấy method tổng hợp ngoài method đã khai báo.

### Hai overload chỉ khác đối số kiểu có thể trùng chữ ký

```java
// Không biên dịch:
// interface Bad {
//     void handle(java.util.List<String> names);
//     void handle(java.util.List<Integer> numbers);
// }
```

Sau erasure, cả hai có tham số `List`; Java không thể phân biệt hai overload đó chỉ bằng đối số generic. Cách xử lý là đổi tên method theo ý nghĩa, thiết kế một method generic thích hợp hoặc dùng hai loại tham số thật sự khác nhau.

Một class cũng không thể tùy tiện thực hiện cùng một generic interface ở hai kiểu đối số khác nhau khi dẫn đến xung đột erasure, ví dụ vừa `Comparable<String>` vừa `Comparable<Integer>`.

## 12. Lỗi khai báo và triển khai thường gặp

**Lỗi 1 — dùng `T` khi chưa khai báo:**

```java
// Sai vì T chưa có trong phạm vi:
// interface Broken { T get(); }

// Đúng:
interface Holder<T> {
    T get();
}
```

**Lỗi 2 — quên cố định hoặc chuyển tiếp đối số kiểu trên `implements`:**

```java
// Đúng khi class cũng generic:
class GenericHolder<T> implements Holder<T> {
    private T value;

    @Override
    public T get() {
        return value;
    }
}
```

Với class không generic, phải chọn kiểu cụ thể, ví dụ `implements Holder<String>`. Chỉ viết raw `implements Holder` đánh mất type information và thường gây cảnh báo/khó kiểm tra.

**Lỗi 3 — implementation sai method signature hoặc giảm visibility:** nếu `implements Holder<String>`, phương thức `get()` cần trả `String` hoặc một kiểu trả về tương thích theo quy tắc override, và phải công khai `public`. Không được đổi thành method `private`, cũng không được coi một overload nhận đối số khác là phương thức override đúng.

**Lỗi 4 — đặt type parameter nhầm cấp:** `<R>` trên method cho phép nhiều kiểu kết quả ở nhiều lời gọi; `<T>` trên interface ràng buộc nhiều method theo cùng kiểu. Chọn cấp khai báo đúng quan hệ.

**Lỗi 5 — dùng static method như instance method:** `static` trong interface phải gọi qua tên interface khai báo; type parameter instance của interface không thể tự xuất hiện trong static signature.

**Lỗi 6 — kiểm tra generic type bằng `instanceof` cụ thể:** do erasure, `instanceof Repository<Long,User>` không hợp lệ. Dùng `Repository<?,?>` để kiểm tra dạng interface ở runtime, rồi validate dữ liệu thực nếu cần.

**Lỗi 7 — lạm dụng kiểu `Object` hoặc cast unchecked:** caller mất bảo đảm kiểu, lỗi có thể chuyển từ compile time sang runtime. Tránh ép `(T)` chỉ để làm API trông generic khi không có căn cứ bảo đảm.

**Lỗi 8 — coi interface có thể khởi tạo trực tiếp:** không thể viết `new Repository<Long,User>()` nếu không có thân anonymous class triển khai đủ method. Cần instance của một class implements interface hoặc một cách tạo instance hợp lệ khác.

**Lỗi 9 — bỏ qua hành vi mặc định và quy tắc null:** method `default` có logic cụ thể và cần được đánh giá theo semantics của implementation. `Optional<T>` cũng không tự khiến mọi thao tác `save` hợp lệ: null, quyền truy cập hoặc uniqueness là kiểm tra khác.

## 13. Kiểm tra kiến thức

**Câu 1.** Với `Repository<String, Integer> stock`, `save` và `findById` có kiểu như thế nào?

**Đáp án:** `save(String, Integer)`; `findById(String)` trả `Optional<Integer>`. Kiểu này được suy ra ngay từ hai type arguments của biến `stock`.

**Câu 2.** Vì sao `class X<T> implements Holder<T>` hợp lệ nhưng `class X implements Holder<T>` không hợp lệ nếu `T` không tồn tại trong phạm vi?

**Đáp án:** `X<T>` khai báo `T` ở cấp class; còn `class X` không khai báo type parameter và không có nguồn nào khác cung cấp `T`. Phải giữ `<T>` ở class hoặc thay `T` bằng kiểu cụ thể.

**Câu 3.** Interface có thể vừa `@FunctionalInterface` vừa có phương thức `default` không?

**Đáp án:** Có. Functional interface cần thỏa quy tắc một abstract method chức năng; default và static methods không tính như abstract method bổ sung. Trong ví dụ, `Converter<I,O>` có `convert` abstract và `andThen` default.

**Câu 4.** `Repository<Long,Manager>` có gán thẳng cho `Repository<Long,Employee>` nếu `Manager` kế thừa `Employee` không?

**Đáp án:** Không, vì generics mặc định bất biến. Phép gán sẽ cho phép bên nhận ghi `Employee` không phải `Manager` vào repository dành cho `Manager`.

**Câu 5.** Tại sao `EntityStore<ID,T extends Identified<ID>>` mạnh hơn `Repository<ID,T>`?

**Đáp án:** Bound đòi hỏi `T` có khả năng cung cấp ID cùng kiểu `ID`, nên implementation có thể gọi `entity.id()` và nhận về ID đúng kiểu. `Repository<ID,T>` không tự ràng buộc thực thể có method như vậy.

**Câu 6.** Interface generic có thể xác nhận mọi đối số kiểu lúc runtime bằng `instanceof` không?

**Đáp án:** Không. Java generics chủ yếu dùng type erasure; có thể kiểm tra `Repository<?,?>`, nhưng không thể kiểm tra `Repository<Long,User>` bằng `instanceof` thông thường. Dữ liệu từ bên ngoài vẫn cần validation theo schema/hợp đồng thích hợp.

## Kết luận

Giao diện generic cho phép mô tả hợp đồng **theo quan hệ kiểu**, ví dụ `Repository<ID,T>`, thay vì buộc mọi phương thức nhận và trả `Object`. Khi một class `implements` interface hoặc một interface `extends` interface khác, các tham số kiểu có thể được **giữ nguyên, chuyên biệt hóa hoặc ràng buộc thêm**. Điều này hỗ trợ tái sử dụng implementation, phát hiện sai kiểu sớm và thay thế implementation qua một API ổn định. Khi thiết kế, hãy tách bạch type parameter ở cấp interface và method, tận dụng `default`/`static` đúng mục đích và viết rõ những cam kết nghiệp vụ mà hệ thống generic của Java không tự bảo đảm.