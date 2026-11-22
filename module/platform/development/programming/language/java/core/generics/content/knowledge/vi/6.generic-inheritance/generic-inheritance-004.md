# Quan hệ giữa lớp generic và giao diện generic trong Java

Trong Java, một **lớp generic** có thể `implements` một **giao diện generic**, hoặc `extends` một lớp generic khác. Khi kế thừa, lớp con phải **giữ nguyên**, **chuyển tiếp**, hoặc **cố định** các tham số kiểu theo cú pháp khai báo. Nhờ đó, hợp đồng kiểu của phương thức được duy trì từ interface đến implementation và đến nơi gọi.

Ví dụ, `Store<K,V>` định nghĩa khả năng lưu dữ liệu theo khóa. `MapStore<K,V> implements Store<K,V>` giữ hai tham số kiểu để tái sử dụng, còn `UserStore extends MapStore<Long,User>` cố định cặp kiểu khóa–giá trị cho một nghiệp vụ. Mỗi cách ảnh hưởng trực tiếp tới chữ ký phương thức mà trình biên dịch chấp nhận.

Sau bài học, bạn có thể giải thích quan hệ giữa `class` và `interface` generic, phân biệt kế thừa giữ tham số với chuyên biệt hóa, thực hiện đúng `@Override`, đọc chữ ký qua nhiều tầng kế thừa, nhận diện các lỗi về bất biến kiểu, type erasure và raw type. Các ví dụ hoàn chỉnh dùng Java 17 trở lên.

## 1. Ba quan hệ cần phân biệt

Trong Java, các khai báo sau biểu diễn ba quan hệ khác nhau:

```java
interface Reader<K, V> {
    V read(K key);
}

interface Store<K, V> extends Reader<K, V> {
    void put(K key, V value);
}

class MemoryStore<K, V> implements Store<K, V> {
    private final java.util.Map<K, V> map = new java.util.HashMap<>();

    @Override
    public void put(K key, V value) {
        map.put(key, value);
    }

    @Override
    public V read(K key) {
        return map.get(key);
    }
}
```

1. `Store<K,V> extends Reader<K,V>`: một **interface kế thừa interface** khác và bổ sung hợp đồng.
2. `MemoryStore<K,V> implements Store<K,V>`: một **class triển khai interface** và phải cung cấp các phương thức abstract bắt buộc.
3. `class Specialized extends MemoryStore<String,Integer>`: một **class kế thừa class** khác, có thể cố định các đối số kiểu của lớp cha.

Từ `extends` có hai cách dùng trong cấu trúc kế thừa: `class Child extends Parent` và `interface Sub extends Base`. `implements` là quan hệ class triển khai interface. Dấu `extends` trong `T extends Number` lại có vai trò **ràng buộc type parameter**; đây là một ngữ cảnh cú pháp khác.

**Các ký hiệu `K`, `V` trong khai báo không phải tên lớp hay biến runtime.** Chúng là tham số kiểu. Còn `Store<String,Integer>` là một **kiểu đã được tham số hóa** với các đối số `String` và `Integer`.

## 2. Interface generic xác định hợp đồng, class generic thực hiện hợp đồng

Một interface generic mô tả phương thức dưới dạng quan hệ kiểu:

```java
interface Repository<ID, ENTITY> {
    void save(ID id, ENTITY entity);
    java.util.Optional<ENTITY> findById(ID id);
}
```

Lớp triển khai có thể giữ nguyên hai type parameter:

```java
class MemoryRepository<ID, ENTITY>
        implements Repository<ID, ENTITY> {

    private final java.util.Map<ID, ENTITY> data =
            new java.util.HashMap<>();

    @Override
    public void save(ID id, ENTITY entity) {
        data.put(id, entity);
    }

    @Override
    public java.util.Optional<ENTITY> findById(ID id) {
        return java.util.Optional.ofNullable(data.get(id));
    }
}
```

`MemoryRepository<ID,ENTITY>` **khai báo lại hai tham số cùng vai trò ở chính class**, rồi **truyền chúng** vào `Repository<ID,ENTITY>`. Việc đặt tên `ID` và `ENTITY` giống interface cho dễ đọc, nhưng **đối số kiểu không buộc trùng tên**:

```java
class AlternateStore<K, V> implements Repository<K, V> {
    private final java.util.Map<K, V> data = new java.util.HashMap<>();

    @Override
    public void save(K key, V value) {
        data.put(key, value);
    }

    @Override
    public java.util.Optional<V> findById(K key) {
        return java.util.Optional.ofNullable(data.get(key));
    }
}
```

`K` tương ứng `ID`, còn `V` tương ứng `ENTITY`. **Tên type parameter không định danh quan hệ kế thừa**; sự tương thích xuất phát từ vị trí type argument và chữ ký phương thức.

Khi khai báo:

```java
Repository<Long, String> repo = new MemoryRepository<>();
repo.save(1L, "ready");
java.util.Optional<String> found = repo.findById(1L);
```

compiler xem `save` nhận `(Long,String)` và `findById` trả `Optional<String>`. `new MemoryRepository<>()` sử dụng **diamond operator** để suy luận type arguments từ ngữ cảnh; không phải raw type.

### Những phương thức nào cần cài đặt?

Một class **concrete** implements `Repository<ID,ENTITY>` phải triển khai tất cả abstract methods của hợp đồng, trừ khi đã được kế thừa từ superclass theo cách hợp lệ. `@Override` giúp compiler phát hiện chữ ký sai. Phương thức triển khai interface abstract phải có visibility `public`:

```java
@Override
public void save(ID id, ENTITY entity) { ... }
```

Bỏ `public`, đảo kiểu đầu vào hoặc đổi kiểu trả về không tương thích có thể khiến class **không triển khai đúng** phương thức bắt buộc. Nếu chưa cung cấp đủ phương thức abstract, class phải được khai báo `abstract`.

Generic interface chỉ quy định **loại dữ liệu** và những chữ ký/hành vi đã mô tả. Nó không tự tạo lưu trữ, không tự kiểm tra tính duy nhất ID, không tự xử lý giao dịch và không mặc nhiên thread-safe.

## 3. Lớp không generic cố định đối số kiểu của interface

Nếu implementation chỉ phục vụ một loại dữ liệu, nó có thể không khai báo `<...>`:

```java
interface Sink<T> {
    void accept(T value);
}

class StringSink implements Sink<String> {
    @Override
    public void accept(String value) {
        System.out.println(value);
    }
}
```

`StringSink` đã **chuyên biệt hóa** `T` thành `String`. Chữ ký bắt buộc là `accept(String)`. Không cần và không nên khai báo `class StringSink<T>` nếu nghiệp vụ của lớp chỉ dành cho chuỗi.

Điều tương tự với hai tham số kiểu:

```java
class UserRepository
        implements Repository<Long, User> {
    // Phải triển khai save(Long, User)
    // và findById(Long) trả Optional<User>.
}
```

`User` là kiểu nghiệp vụ minh họa; đoạn trên chỉ là **khai báo hình dạng** và sẽ cần thân phương thức thực tế để là một concrete class hợp lệ. Trong chương trình chạy hoàn chỉnh ở phần 6, `UserStore` được chuyên biệt hóa bằng cách kế thừa một implementation generic đã hoàn chỉnh.

### Cố định một phần, giữ một phần

Có thể cố định kiểu khóa nhưng giữ kiểu giá trị tùy chọn:

```java
class LongKeyRepository<T> implements Repository<Long, T> {
    private final java.util.Map<Long, T> data = new java.util.HashMap<>();

    @Override
    public void save(Long id, T item) {
        data.put(id, item);
    }

    @Override
    public java.util.Optional<T> findById(Long id) {
        return java.util.Optional.ofNullable(data.get(id));
    }
}
```

`LongKeyRepository<T>` vẫn generic theo `T`, nhưng **khóa luôn có kiểu `Long`**. Dùng `LongKeyRepository<Order>` hay `LongKeyRepository<User>` tùy đối tượng nghiệp vụ. `LongKeyRepository<String>` không yêu cầu lại kiểu khóa khi khởi tạo.

Phân biệt rõ **class generic hay không** với **kiểu cha/interface mà class chọn**: một class không có `<T>` vẫn có thể implements hoặc extends một generic type bằng đối số kiểu cụ thể.

## 4. Class generic kế thừa class generic bên cạnh `implements`

`implements Repository<K,V>` buộc một **class** thực hiện hợp đồng interface; `extends MemoryRepository<K,V>` lại **kế thừa class đã có implementation**. Hai quan hệ có thể kết hợp: lớp con tái sử dụng implementation của superclass, còn hợp đồng interface của superclass tiếp tục áp dụng sau phép thế type arguments.

Dùng `MemoryRepository<ID,ENTITY>` đã khai báo tại mục 2, ta có ba hình thức:

```java
class AuditedRepository<K,V> extends MemoryRepository<K,V> {}
class LongKeyRepository<V> extends MemoryRepository<Long,V> {}
class FixedCounts extends MemoryRepository<String,Integer> {}
```

- `AuditedRepository<K,V>` chuyển cả K và V lên superclass; bản thân class con vẫn generic.
- `LongKeyRepository<V>` cố định kiểu khóa Long và giữ V thay đổi được.
- `FixedCounts` cố định cả hai: `Repository<String,Integer>` là interface contract của nó qua superclass.

Không cần viết lại `implements Repository<...>` nếu quan hệ đã được superclass triển khai đúng; nếu thêm interface mới, class vẫn phải đáp ứng mọi method bắt buộc của interface đó. Constructor không được kế thừa và cần gọi `super(...)` phù hợp khi superclass yêu cầu. Các khai báo trên nhằm so sánh **extends class** với **implements interface**; chương trình ở mục 6 mới minh họa hành vi có lưu trữ và override thực tế.

## 5. Interface generic kế thừa interface generic

`interface` có thể `extends` **nhiều interface**:

```java
interface Reader<K, V> {
    V find(K key);
}

interface Writer<K, V> {
    void save(K key, V value);
}

interface ReadWrite<K, V> extends Reader<K, V>, Writer<K, V> {
}
```

`ReadWrite<String,Integer>` thừa hưởng cả `find(String)` trả `Integer` và `save(String,Integer)`. Dù `ReadWrite` không tự thêm method nào, nó kết hợp hai hợp đồng kiểu.

Tương tự class, interface con có thể cố định đối số kiểu của interface cha:

```java
interface StringReader extends Reader<Long, String> {
}
```

Đọc là: `StringReader` có `find(Long)` và trả `String`. Tên `StringReader` ở đây nhấn mạnh kiểu kết quả, không phải kiểu khóa.

Một interface cũng có thể sắp xếp lại type parameter một cách rõ ràng:

```java
interface Flipped<V, K> extends Reader<K, V> {
}
```

Nếu dùng `Flipped<String,Long>`, hợp đồng inherited là `Reader<Long,String>`. **Thứ tự khai báo type parameter có ý nghĩa**; compiler gắn theo vị trí, không theo tên biến.

### Kế thừa `default` methods

```java
interface Reader<K, V> {
    java.util.Optional<V> find(K key);

    default boolean contains(K key) {
        return find(key).isPresent();
    }
}
```

Class implements `Reader<String,Integer>` nhận được `contains(String)` nếu không override, miễn implementation cung cấp `find(String)`. `default` method dùng type parameter thuộc interface cha với cách chuyên biệt hóa đã chọn.

Nếu class nhận hai `default` methods cùng chữ ký từ hai interface không liên quan, Java có thể yêu cầu override để giải quyết xung đột. Việc generic hóa interface không tự xóa quy tắc giải quyết xung đột này.

## 6. Chương trình Java 17+ hoàn chỉnh: `extends` và `implements` cùng hoạt động

Tạo tệp **`Main.java`**. Ví dụ gồm interface chỉ đọc `Reader<K,V>`, interface đọc/ghi `Store<K,V>`, lớp triển khai generic `MapStore<K,V>`, lớp con cố định kiểu `UserStore` và lớp con giữ nguyên kiểu `CountingStore<K,V>`.

```java
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;

public class Main {
    record User(long id, String name) {}

    interface Reader<K, V> {
        Optional<V> find(K key);
    }

    interface Store<K, V> extends Reader<K, V> {
        void put(K key, V value);
    }

    static class MapStore<K, V> implements Store<K, V> {
        private final Map<K, V> data = new LinkedHashMap<>();

        @Override
        public void put(K key, V value) {
            data.put(
                    Objects.requireNonNull(key),
                    Objects.requireNonNull(value));
        }

        @Override
        public Optional<V> find(K key) {
            return Optional.ofNullable(data.get(key));
        }
    }

    static final class UserStore extends MapStore<Long, User> {
        void putUser(User user) {
            put(user.id(), user);
        }
    }

    static final class CountingStore<K, V> extends MapStore<K, V> {
        private int writes;

        @Override
        public void put(K key, V value) {
            super.put(key, value);
            writes++;
        }

        int writes() {
            return writes;
        }
    }

    public static void main(String[] args) {
        Store<String, Integer> stock = new MapStore<>();
        stock.put("SKU-01", 7);
        System.out.println("stock: "
                + stock.find("SKU-01").orElse(-1));

        UserStore users = new UserStore();
        users.putUser(new User(42L, "Lan"));
        System.out.println("user: "
                + users.find(42L).map(User::name).orElse("missing"));

        CountingStore<String, String> preferences =
                new CountingStore<>();
        preferences.put("theme", "dark");
        preferences.put("lang", "vi");
        System.out.println("writes: " + preferences.writes());
        System.out.println("theme: "
                + preferences.find("theme").orElse("-"));

        Reader<String, Integer> view = stock;
        System.out.println("reader: "
                + view.find("SKU-01").orElse(-1));

        // stock.put("SKU-01", "seven"); // Sai: V phải là Integer.
        // users.put("42", new User(42L, "Lan")); // Sai: K phải là Long.
    }
}
```

Dùng JDK 17 trở lên, trong thư mục chứa tệp:

```bash
javac -encoding UTF-8 Main.java
java Main
```

Kết quả stdout:

```text
stock: 7
user: Lan
writes: 2
theme: dark
reader: 7
```

**Giải thích từng quan hệ:**

1. `Store<K,V> extends Reader<K,V>`: `find(K)` là hợp đồng được kế thừa từ interface cha; `put(K,V)` do interface con bổ sung.
2. `MapStore<K,V> implements Store<K,V>`: class generic giữ hai tham số kiểu để cài đặt hợp đồng đọc và ghi bằng `Map<K,V>`. Các `@Override` có chữ ký tương thích với hợp đồng interface.
3. `UserStore extends MapStore<Long,User>`: class không generic cố định cặp kiểu cha. `put` được thừa hưởng với hợp đồng `(Long,User)`, `find` trả `Optional<User>`, nên method `putUser(User)` có thể gọi `put(user.id(),user)` an toàn kiểu.
4. `CountingStore<K,V> extends MapStore<K,V>`: class con vẫn generic, override `put(K,V)` và gọi `super.put(...)`. Chỉ sau lời gọi lưu thành công, bộ đếm `writes` được tăng.
5. `Store<String,Integer> stock = new MapStore<>()`: biến được khai báo theo **interface**, đối tượng được tạo bằng implementation. Caller phụ thuộc hợp đồng `Store`, không cần biết class dùng `LinkedHashMap` ở bên trong.
6. `Reader<String,Integer> view = stock`: interface `Store<String,Integer>` **là subtype** của `Reader<String,Integer>` vì quan hệ `extends`; biến `view` chỉ có thể gọi những method thấy được trên `Reader`.
7. Hai dòng comment lỗi cố ý minh họa compiler sẽ ngăn sai kiểu khi lời gọi đi qua các tham chiếu có type arguments rõ ràng.

Phương thức `find` dùng `Optional` để biểu thị khóa có thể chưa tồn tại. Đây là **quyết định thiết kế API**; generics không tự chọn `Optional`. Ví dụ lưu trong bộ nhớ và không thread-safe, không đại diện cho transaction, persistence hay phân quyền truy cập dữ liệu.

## 7. Đọc kiểu hiệu lực qua nhiều tầng kế thừa

Xem chuỗi sau:

```java
interface Source<T> {
    T read();
}

abstract class AbstractSource<T> implements Source<T> {
}

class TextSource extends AbstractSource<String> {
    @Override
    public String read() {
        return "hello";
    }
}
```

Mối quan hệ kiểu theo từng tầng:

```text
Source<T>
    ↑ implements
AbstractSource<T>
    ↑ extends (T = String)
TextSource
```

Khi xem `TextSource` như `Source<String>`, phương thức `read()` trả `String`. `AbstractSource<T>` được khai báo `abstract` vì chưa cài đặt `read()`, nhưng vẫn hợp lệ khi triển khai interface generic mà chưa cung cấp hết phương thức ở lớp trung gian.

**Không phải mọi lớp trong chuỗi đều cần generic.** Lớp trung gian có thể giữ `T`, còn lớp cuối có thể cố định `T = String` để biểu diễn nghiệp vụ.

Nếu một lớp cha generic có constructor nhận `T`, lớp con phải gọi `super(...)` với giá trị phù hợp sau khi đã chọn type arguments. Việc kế thừa generic không tự tạo constructor trong lớp con.

### Truyền tham số kiểu qua superclass và interface

```java
interface Identifiable<ID> {
    ID id();
}

abstract class Entity<ID> implements Identifiable<ID> {
}

final class UserEntity extends Entity<Long> {
    private final Long id;

    UserEntity(Long id) {
        this.id = id;
    }

    @Override
    public Long id() {
        return id;
    }
}
```

`UserEntity` cố định `ID = Long` qua superclass `Entity<Long>`, nên cũng đáp ứng `Identifiable<Long>`. Lúc sử dụng:

```java
Identifiable<Long> entity = new UserEntity(5L);
Long id = entity.id();
```

Không cần và không được tự giả định `UserEntity` triển khai `Identifiable<String>` chỉ vì `Long` hoặc `String` đều là `Object`.

## 8. Kiểm tra chữ ký phương thức override sau khi chuyên biệt hóa

Giả sử:

```java
interface Formatter<T> {
    String format(T value);
}
```

Một class cố định `T = Integer` phải triển khai chữ ký tương ứng:

```java
class IntegerFormatter implements Formatter<Integer> {
    @Override
    public String format(Integer value) {
        return "value=" + value;
    }
}
```

Phương thức `format(Integer)` chính là implementation của hợp đồng `Formatter<Integer>`. Dòng sau **không thay thế** hợp đồng ấy:

```java
// Ví dụ sai khi thay phương thức bắt buộc:
// public String format(String value) { return value; }
```

Dù tên method vẫn là `format`, tham số `String` không đúng. Nếu lớp concrete không có method đúng chữ ký, compiler sẽ yêu cầu triển khai method hoặc khai báo lớp `abstract`.

### Tương thích kiểu trả về

Java cho phép **covariant return type** đối với các kiểu trả về tham chiếu thích hợp. Ví dụ interface khai báo `Number read()`, implementation có thể trả `Integer`. Nhưng generic container mặc định **bất biến**, nên không suy ra rằng method khai báo trả `List<Number>` có thể override bằng `List<Integer>`.

`@Override` bảo vệ người viết khỏi việc vô tình tạo method khác chữ ký khi định triển khai interface hay override method của superclass. Nó không thay thế unit test cho logic nghiệp vụ.

### Bridge methods do type erasure

```java
interface Processor<T> {
    T process(T value);
}

class StringProcessor implements Processor<String> {
    @Override
    public String process(String value) {
        return value.strip();
    }
}
```

Ở cấp mã nguồn, implementation viết `process(String)`. Java biên dịch generics chủ yếu theo cơ chế **type erasure**, nên compiler có thể sinh một **bridge method tổng hợp** để duy trì dispatch đa hình khi chữ ký đã xóa kiểu khác nhau. Bạn không cần và không nên tự viết bridge method; hãy khai báo đúng generic signature và để compiler xử lý chi tiết bytecode.

## 9. Giới hạn của tính thay thế: `extends` lớp khác với subtype giữa generic types

Giả sử:

```java
class Animal {}
class Dog extends Animal {}
```

Mặc dù `Dog extends Animal`, hai kiểu sau **không có quan hệ subtype trực tiếp**:

```java
java.util.List<Dog> dogs = new java.util.ArrayList<>();

// Không biên dịch:
// java.util.List<Animal> animals = dogs;
```

Nếu gán được, caller qua `List<Animal>` có thể thêm `Animal` không phải `Dog` vào danh sách thực chất chỉ dành cho `Dog`.

Quy tắc tương tự với các interface do bạn tự khai báo:

```java
// Trong ngữ cảnh có Store<Long,Dog> dogs:
Store<Long, Dog> dogStore = null;

// Không biên dịch:
// Store<Long, Animal> animalStore = dogStore;
```

**Cần phân biệt:**

- `Store<K,V> extends Reader<K,V>` xác lập quan hệ subtype **giữa hai khai báo interface** với cùng cách tham số hóa tương ứng.
- `Store<Long,Dog>` và `Store<Long,Animal>` là hai cách tham số hóa **cùng một generic interface**, vốn mặc định bất biến theo đối số kiểu.

Vì `Store<Long,Dog>` là subtype của `Reader<Long,Dog>`, phép gán `Reader<Long,Dog> view = dogStore` hợp lệ. Nhưng không thể nhảy sang `Store<Long,Animal>` chỉ nhờ `Dog extends Animal`.

### Sử dụng wildcard đúng nhu cầu

Nếu một API **chỉ đọc** các giá trị thuộc họ `Animal`, có thể biểu diễn:

```java
Reader<Long, ? extends Animal> readOnly = dogStore;
```

Vì `Reader` không có thao tác ghi, kiểu wildcard `? extends Animal` cho phép sử dụng kết quả đọc như giá trị tương thích với `Animal` sau khi xử lý `Optional`. Nếu API cho phép ghi, wildcard cần được chọn cẩn thận theo hướng dữ liệu; `? extends Animal` không cho phép ghi một `Animal` tùy ý vào một `Store<Long, ? extends Animal>`.

Quy tắc thường được gọi là “producer extends, consumer super” (PECS) là gợi ý về chiều đọc/ghi, không phải cơ chế tự biến generic types thành covariant.

## 10. Ràng buộc type parameter trong kế thừa

Khi một interface cần đảm bảo thực thể có ID đúng kiểu, có thể khai báo bound:

```java
interface HasId<ID> {
    ID id();
}

interface EntityRepository<ID, E extends HasId<ID>> {
    void save(E entity);
    java.util.Optional<E> find(ID id);
}
```

`E extends HasId<ID>` yêu cầu kiểu entity phải cung cấp method `id()` trả đúng loại `ID`. Nếu class giữ nguyên cả hai type parameters, nó cũng phải thỏa bound:

```java
class InMemoryEntityRepository<ID, E extends HasId<ID>>
        implements EntityRepository<ID, E> {

    private final java.util.Map<ID, E> data =
            new java.util.HashMap<>();

    @Override
    public void save(E entity) {
        data.put(entity.id(), entity);
    }

    @Override
    public java.util.Optional<E> find(ID id) {
        return java.util.Optional.ofNullable(data.get(id));
    }
}
```

Nếu viết `class Broken<ID,E> implements EntityRepository<ID,E>`, compiler từ chối vì `E` chưa được ràng buộc để chắc chắn là subtype phù hợp của `HasId<ID>`. Cách sửa là truyền một kiểu cụ thể đúng bound hoặc lặp lại bound thích hợp ở khai báo class con.

**Một lớp không được tự nới rộng bound của type parameter cha** theo cách làm mất hợp đồng của cha. Khi subclass tiếp tục generic, hãy đảm bảo type arguments được truyền lên superclass hoặc interface đều thỏa tất cả bound cần thiết.

### Có thể thêm ràng buộc ở lớp con

Giả sử `Box<T>` cho phép mọi reference type, lớp con có thể hạn chế hơn:

```java
class NumberBox<N extends Number> extends Box<N> {
    NumberBox(N value) {
        super(value);
    }

    double asDouble() {
        return get().doubleValue();
    }
}
```

`NumberBox<Integer>` hợp lệ, `NumberBox<String>` bị từ chối. Lớp con chọn một tập đối số kiểu hẹp hơn nhưng vẫn thỏa yêu cầu tổng quát của `Box<N>`.

## 11. Type erasure và xung đột kế thừa

Java dùng **type erasure**: trong bytecode, type variables được xóa về upper bound (hoặc `Object` nếu không có bound), và compiler chèn cast/bridge methods khi cần. Một instance `MapStore<String,Integer>` không phải runtime class riêng so với `MapStore<Long,User>`; cả hai cùng có runtime class `MapStore` trong chương trình.

Các cú pháp sau không hợp lệ:

```java
// Không được kiểm tra chính xác cả type argument:
// if (obj instanceof Store<String, Integer>) { ... }

// Không có class literal cho kiểu tham số hóa:
// Store<String, Integer>.class
```

Có thể dùng `obj instanceof Store<?, ?>` để kiểm tra đối tượng thuộc một cách tham số hóa **không biết rõ type arguments**. Nó không kiểm chứng kiểu khóa và giá trị bên trong.

### Một generic interface không được kế thừa với hai type arguments khác nhau

Đoạn dưới **cố ý sai**, bởi một class không được thừa hưởng đồng thời hai cách tham số hóa không tương thích của cùng interface:

```java
interface Processor<T> {
    T process(T input);
}

interface StringProcessor extends Processor<String> {
}

interface IntegerProcessor extends Processor<Integer> {
}

// Không biên dịch:
// class Mixed implements StringProcessor, IntegerProcessor { ... }
```

`StringProcessor` đòi `Processor<String>`; `IntegerProcessor` đòi `Processor<Integer>`. Sau type erasure, JVM không thể coi `Mixed` như đã triển khai cùng một generic interface theo hai cách không tương thích. Không thể giải quyết bằng việc thêm hai overload `process(String)` và `process(Integer)` rồi tuyên bố cả hai interface đã được kế thừa hợp lệ.

### Phương thức có cùng erasure

Trong cùng một type, hai overload `void handle(List<String>)` và `void handle(List<Integer>)` có cùng dạng tham số `List` sau erasure, nên xung đột. Đây là lý do không nên dựa vào type arguments để phân biệt overload khi chữ ký runtime giống nhau.

## 12. Raw type, unchecked warnings và nguy cơ mất hợp đồng

Khi một class implements/extends generic type nhưng **bỏ type arguments**, Java có thể xử lý như raw type vì tương thích với mã cũ:

```java
// Không khuyến nghị:
class LegacyStore extends java.util.HashMap {
}
```

`HashMap` có hai type parameters, nhưng raw `HashMap` không còn hợp đồng khóa/giá trị cụ thể cho nhiều thao tác. Khi gọi các method generic qua raw reference, cảnh báo `unchecked` có thể xuất hiện; dữ liệu sai có thể chỉ phát hiện khi lấy ra và cast.

Cùng vấn đề với:

```java
java.util.Map<String, Integer> typed = new java.util.HashMap<>();
java.util.Map raw = typed;
raw.put("count", "not an integer"); // Cảnh báo unchecked.
```

Sau đó đọc `Integer count = typed.get("count");` có thể ném `ClassCastException` ở runtime. Chương trình học nên dùng đầy đủ đối số kiểu (`Map<String,Integer>`), hạn chế raw ở vùng tích hợp legacy và kiểm tra dữ liệu thay vì tắt warnings tùy tiện.

**`new HashMap<>()` không phải raw type.** Diamond nhờ compiler suy luận type arguments; khác với `new HashMap()`.

## 13. Các lỗi phổ biến và cách sửa

**Lỗi 1 — quên truyền type parameter của class con lên cha:** `class Child<T> extends Parent` là raw inheritance nếu `Parent` generic. Dùng `extends Parent<T>` khi cần giữ cùng quan hệ kiểu, hoặc `extends Parent<String>` khi cần cố định.

**Lỗi 2 — tự dùng `T` nhưng chưa khai báo `T`:**

```java
// Sai:
// class Child extends Box<T> { }

// Đúng khi giữ T:
class Child<T> extends Box<T> {
    Child(T value) { super(value); }
}
```

**Lỗi 3 — implementation sai chữ ký sau chuyên biệt hóa:** với `implements Formatter<Integer>`, method phải nhận `Integer` theo hợp đồng, không nhận `String`. Dùng `@Override` và để compiler kiểm tra.

**Lỗi 4 — dùng tên type parameters như thể chúng phải giống cha:** `class Child<A,B> implements Store<A,B>` vẫn hợp lệ dù interface khai báo `Store<K,V>`. Quan trọng là **quan hệ theo vị trí và bound**, không phải tên.

**Lỗi 5 — hiểu `extends` generic là tự cho phép hiệp biến:** `Dog extends Animal` không kéo theo `Store<Long,Dog> extends Store<Long,Animal>`. Cần wildcard hoặc mô hình API phù hợp khi chỉ đọc/ghi ở mức trừu tượng.

**Lỗi 6 — thừa hưởng một interface với hai cách tham số hóa:** ví dụ đồng thời `Processor<String>` và `Processor<Integer>` trên cùng một class không hợp lệ. Tách vai trò hoặc dùng interface khác.

**Lỗi 7 — override trả kiểu không tương thích:** `Optional<Dog>` không phải subtype của `Optional<Animal>`; quy tắc covariant return không hợp thức hóa những generic wrappers bất biến.

**Lỗi 8 — bỏ bound khi subclass generic:** nếu interface cha đòi `E extends HasId<ID>`, lớp con giữ `E` cũng cần đảm bảo bound ấy.

**Lỗi 9 — nhầm type erasure với việc compiler không kiểm tra:** thông tin generic chủ yếu kiểm tra ở compile time, nhưng raw/cast không kiểm chứng vẫn có thể phá vỡ hợp đồng. Không dựa vào `instanceof Store<String,Integer>` để kiểm tra toàn bộ kiểu.

**Lỗi 10 — quên hợp đồng hành vi:** kế thừa chữ ký không tự đảm bảo dữ liệu luôn bền vững, bất biến, an toàn đa luồng hay đã được phân quyền. Implementation và tài liệu phải xác định các cam kết đó.

## 14. Khi nào nên giữ generic và khi nào nên chuyên biệt hóa?

Chọn **lớp generic implements generic interface** khi nhiều kiểu dữ liệu cần một thuật toán, ví dụ `MapStore<K,V>` cung cấp thao tác lưu theo khóa cho nhiều cặp kiểu.

Chọn **lớp con generic extends lớp generic** khi cần thêm hành vi chung mà vẫn giữ cùng type arguments, như `CountingStore<K,V> extends MapStore<K,V>`.

Chọn **lớp không generic cố định type arguments** khi nghiệp vụ cần một hợp đồng rõ ràng, ví dụ `UserStore extends MapStore<Long,User>` hoặc `IntegerFormatter implements Formatter<Integer>`.

Chọn **interface con chuyên biệt hóa** khi muốn đặt tên cho một vai trò API xác định, ví dụ `interface UserReader extends Reader<Long,User>`; điều này vẫn là interface, chưa có implementation.

Không nên lạm dụng tạo lớp kế thừa chỉ để đổi tên; cân nhắc composition khi các thành phần chỉ cần cộng tác thay vì quan hệ **is-a**. Generic inheritance hữu ích nhất khi lớp con thực sự **là một phiên bản** của kiểu cha và tuân thủ hợp đồng mà client mong đợi.

| Tình huống | Mẫu khai báo |
| --- | --- |
| Interface con giữ kiểu | `interface Store<K,V> extends Reader<K,V>` |
| Class generic triển khai interface | `class MapStore<K,V> implements Store<K,V>` |
| Class con vẫn generic | `class CountingStore<K,V> extends MapStore<K,V>` |
| Class con cố định kiểu | `class UserStore extends MapStore<Long,User>` |
| Class generic cố định một type argument | `class LongKeyStore<T> implements Repository<Long,T>` |
| Interface con cố định kiểu | `interface UserReader extends Reader<Long,User>` |
| Class trung gian chưa triển khai đủ | `abstract class AbstractSource<T> implements Source<T>` |

## 15. Bài tập tự kiểm tra

**Câu 1.** Với `interface Sink<T> { void accept(T x); }`, chữ ký đúng khi `class Logger implements Sink<String>` là gì?

**Đáp án:** `public void accept(String x)`. Type parameter `T` đã được cố định thành `String`, và method override phải có visibility thích hợp.

**Câu 2.** `class Child<T> extends Box<T>` khác `class Child extends Box<String>` ở đâu?

**Đáp án:** Dạng đầu giữ lớp con generic và chuyển `T` lên lớp cha; dạng sau tạo class con không generic và cố định kiểu `String` cho superclass.

**Câu 3.** Vì sao `Store<String,Integer>` có thể gán cho `Reader<String,Integer>`?

**Đáp án:** Vì khai báo `Store<K,V> extends Reader<K,V>` xác lập quan hệ subtype giữa hai interface sau khi áp dụng cùng cặp type arguments. Client có thể xem store như reader và chỉ gọi API đọc.

**Câu 4.** Nếu `Dog extends Animal`, có thể gán `Store<Long,Dog>` cho biến `Store<Long,Animal>` không?

**Đáp án:** Không. Generic types bất biến theo type arguments; nếu gán được, caller có thể lưu một `Animal` không phải `Dog` vào store dành cho `Dog`.

**Câu 5.** Vì sao `class Broken<ID,E> implements EntityRepository<ID,E>` không hợp lệ khi `E` của interface bị bound bởi `HasId<ID>`?

**Đáp án:** Type parameter `E` trên `Broken` chưa có bound phù hợp nên compiler không thể bảo đảm nó thỏa `E extends HasId<ID>`. Phải khai báo bound tương ứng hoặc dùng một kiểu cụ thể đáp ứng hợp đồng.

**Câu 6.** Có thể một class vừa implements `Processor<String>` vừa implements `Processor<Integer>` thông qua hai interface con khác nhau không?

**Đáp án:** Không, nếu hai đường kế thừa dẫn tới cùng một generic interface với hai cách tham số hóa không tương thích. Java từ chối do xung đột kiểu và erasure.

**Câu 7.** Đổi `MapStore<K,V>` thành `MapStore` raw để tránh viết type arguments có lợi cho an toàn kiểu không?

**Đáp án:** Không. Raw type loại bỏ phần lớn kiểm tra type arguments ở các thao tác và có thể dẫn đến cảnh báo `unchecked` hoặc `ClassCastException` khi runtime.

## Kết luận

Quan hệ giữa **lớp generic** và **giao diện generic** được thiết lập qua `implements` và `extends`. Interface định nghĩa hợp đồng kiểu; class có thể giữ tham số (`MapStore<K,V>`), cố định một phần (`LongKeyRepository<T>`) hoặc cố định toàn bộ (`UserStore extends MapStore<Long,User>`), miễn các chữ ký và bound được thực hiện đúng. Kế thừa giữa các khai báo type không làm các cách tham số hóa khác nhau tự có quan hệ subtype: generics Java vẫn bất biến theo mặc định. Dùng `@Override`, kiểm tra bound và tránh raw type giúp giữ đúng hợp đồng từ thiết kế đến caller, trong khi những yêu cầu nghiệp vụ và runtime phải được kiểm chứng riêng.