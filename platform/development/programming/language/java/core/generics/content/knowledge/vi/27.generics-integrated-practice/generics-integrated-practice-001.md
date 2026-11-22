# Xây dựng `Box<T>`, `Pair<K,V>` và giao diện lưu trữ generic trong Java 17+

Bài thực hành này xây dựng một mô hình nhỏ nhưng hoàn chỉnh gồm **`Box<T>`**, **`Pair<K,V>`** và **giao diện `Storage<K,V>`** cùng một implementation lưu trong bộ nhớ. Mục tiêu không chỉ là “thêm dấu `<T>` để code biên dịch”, mà còn thiết kế **quan hệ kiểu chính xác, bất biến dữ liệu, hợp đồng thao tác, ranh giới trách nhiệm và kiểm thử** để có thể mở rộng thành API thực tế.

Sau bài thực hành, bạn có thể:

- Tạo một lớp/record generic mang **một** type parameter `T`, với static generic factory và generic instance method.
- Tạo `Pair<K,V>` gồm **hai** type parameters độc lập, dùng được cho cặp khóa–giá trị.
- Khai báo **generic interface `Storage<K,V>`**, nơi `K` là kiểu khóa và `V` là kiểu giá trị; triển khai nó bằng `LinkedHashMap<K,V>`.
- Chọn `Optional<V>` để biểu thị **không tìm thấy**, phân biệt với giá trị `null`.
- Giữ dữ liệu nội bộ `private`, không phát tán mutable backing map, và cung cấp danh sách snapshot không sửa được về **cấu trúc**.
- Áp dụng `K/V/T/R`, method type parameter, `? extends`/`? super`, type inference và cách thiết kế API không cần raw/unchecked casts.
- Viết chương trình Java 17+ chạy độc lập, có đầu ra kiểm chứng được; phân biệt rõ hợp đồng compile-time với những điều vẫn phải kiểm tra ở runtime.

## 1. Đề bài và sơ đồ thiết kế

Giả sử cần quản lý các giá trị có khóa; ví dụ danh sách người dùng theo mã số hoặc điểm số theo tên. Ta muốn một hệ thống có ba thành phần:

```text
Box<T>
  ├── value(): T
  ├── of(U): Box<U>                 (static generic factory)
  └── map(Function<T,R>): Box<R>   (chuyển kiểu giá trị)

Pair<K,V>
  ├── key(): K
  └── value(): V

Storage<K,V>                        (hợp đồng không gắn với công nghệ lưu)
  ├── put(K, V)
  ├── find(K): Optional<V>
  ├── remove(K): Optional<V>
  ├── containsKey(K): boolean
  ├── size(): int
  ├── snapshot(): List<Pair<K,V>>
  └── isEmpty(): boolean           (default method)

InMemoryStorage<K,V> implements Storage<K,V>
  └── private LinkedHashMap<K,V>   (chi tiết triển khai)
```

Một ứng dụng có thể chọn:

```java
Storage<Integer, Box<String>> users = new InMemoryStorage<>();
Storage<String, Integer> scores = new InMemoryStorage<>();
```

Hai biến dùng **cùng một interface** nhưng gắn kiểu khác nhau. Với biến `users`, compiler biết khóa là `Integer` và giá trị là `Box<String>`; với biến `scores`, khóa là `String` và giá trị là `Integer`.

**Không đánh đồng generic storage với database:** phiên bản này chỉ lưu tạm trong RAM, không tự lưu file/SQL, không bảo đảm giao dịch, không bảo đảm đa luồng và không làm deep copy các object được lưu. Những tính năng đó cần thiết kế/hợp đồng riêng.

## 2. Chọn type parameters có ý nghĩa

Bộ ba tên thường gặp:

| Tên | Ý nghĩa trong bài | Quan hệ kiểu |
| --- | --- | --- |
| `T` | Kiểu một giá trị trong `Box<T>` | `Box<String>` giữ `String`, `Box<Integer>` giữ `Integer` |
| `K` | Kiểu khóa trong `Pair<K,V>` và `Storage<K,V>` | Đầu vào cho `put/find/remove/containsKey` |
| `V` | Kiểu giá trị trong `Pair<K,V>` và `Storage<K,V>` | Đầu vào của `put`, kiểu phần tử trong `Optional<V>` |
| `U` | Kiểu riêng của static factory `Box.of` | Không nhầm với `T` của class |
| `R` | Kiểu kết quả mới khi `Box<T>.map` | Liên kết kết quả callback với `Box<R>` |

Tên `K` và `V` **không buộc hai loại runtime class khác nhau**. `Storage<String,String>` vẫn hợp lệ. Tương tự, `Box<Integer>` và `Box<String>` thường dùng cùng một runtime class `Box` do **type erasure**, dù compiler kiểm tra chúng như các kiểu tham số hóa khác nhau.

Một design tốt chọn type parameter để biểu diễn **quan hệ dữ liệu mà compiler có thể bảo vệ**. Nếu thay toàn bộ bằng `Object`, caller sẽ phải cast và dễ gặp `ClassCastException` muộn hơn.

## 3. Xây dựng `Box<T>`: một wrapper generic bất biến ở cấp container

Trong Java 17, `record` giúp biểu diễn một cấu trúc chỉ giữ một giá trị:

```java
import java.util.Objects;
import java.util.function.Function;

record Box<T>(T value) {
    Box {
        Objects.requireNonNull(value, "value");
    }

    static <U> Box<U> of(U value) {
        return new Box<>(value);
    }

    <R> Box<R> map(Function<? super T, ? extends R> mapper) {
        return Box.of(Objects.requireNonNull(mapper, "mapper")
                             .apply(value));
    }
}
```

Đây là **snippet độc lập về khai báo**; chương trình chạy đầy đủ nằm ở mục 10 với các khai báo lồng bên trong một class chứa `main`.

### Vì sao dùng `record Box<T>`?

Record tự cung cấp constructor theo component, accessor `value()`, `equals`, `hashCode`, `toString` theo component. Ta bổ sung compact canonical constructor để **cấm `null`** vì hợp đồng Box ở ví dụ là “luôn có một giá trị”.

```java
Box<String> name = Box.of("Java");
String text = name.value(); // "Java"
```

Khi dùng record, tham chiếu tới component field được cố định sau khi tạo (không có setter). Nhưng “record bất biến” ở đây có nghĩa **bất biến về các component references**: nếu `T` là một `ArrayList` mutable, nội dung list đó vẫn có thể thay đổi từ alias khác. Record không deep-copy object thành phần.

### Static factory có `<U>` riêng

```java
static <U> Box<U> of(U value)
```

`U` được khai báo bởi **chính method `of`**, không phải `T` của record `Box<T>`. Đây là cách đúng vì static method không thể tham chiếu trực tiếp type variable `T` của lớp trong static context.

Caller có thể dùng type inference:

```java
Box<String> words = Box.of("hello");
Box<Integer> count = Box.of(42);
```

Hoặc type witness tường minh khi cần:

```java
Box<String> words = Box.<String>of("hello");
```

Không cần và không nên dùng raw `Box`.

## 4. `Box<T>.map`: method generic có kiểu kết quả mới

Một wrapper thường hữu ích hơn nếu có thể biến đổi giá trị bên trong:

```java
<R> Box<R> map(Function<? super T, ? extends R> mapper)
```

Khi `T = String`, một callback `String::length` cho kết quả `Integer`, vì vậy:

```java
Box<String> text = Box.of("Binh");
Box<Integer> length = text.map(String::length);
System.out.println(length.value()); // 4
```

Cần phân biệt:

- `T` thuộc record `Box<T>`, tức kiểu input của callback tại instance hiện tại.
- `R` thuộc method `map`, tức kiểu output được method suy luận.
- `Function<? super T, ? extends R>` diễn đạt callback có thể **tiêu thụ một giá trị T** và **sản xuất một giá trị tương thích R**.

`map` **không sửa `Box<T>` ban đầu**; nó tạo một `Box<R>` mới. Với implementation đang dùng, mapper không được `null`, và kết quả mapper cũng không được `null` vì `Box.of` gọi constructor cấm null.

Nếu muốn hỗ trợ “có hoặc không có giá trị”, nên thiết kế một wrapper có semantics khác, hoặc dùng `Optional<T>`. Không nên âm thầm đổi Box hiện tại sang nullable rồi vẫn viết Javadoc “luôn có giá trị”.

### Đọc đúng `? super T` và `? extends R`

`? super T` là quan hệ **consumer** của callback: một hàm nhận `Object` cũng có thể nhận `String`. `? extends R` là quan hệ **producer**: một hàm trả `Integer` có thể được dùng trong ngữ cảnh cần `Number`.

Những wildcard này không ảnh hưởng đến runtime class của `Box`; chúng giúp compile-time API linh hoạt hơn mà không cần unchecked casts.

## 5. Xây dựng `Pair<K,V>`: hai thành phần độc lập

Một pair gắn khóa với giá trị:

```java
import java.util.Objects;

record Pair<K,V>(K key, V value) {
    Pair {
        Objects.requireNonNull(key, "key");
        Objects.requireNonNull(value, "value");
    }
}
```

Caller:

```java
Pair<Integer, String> ticket = new Pair<>(7, "READY");
Integer id = ticket.key();
String status = ticket.value();
```

Dùng `K` cho key và `V` cho value giúp mã đọc được ngay, đồng thời giữ quan hệ kiểu:

```java
// KHÔNG BIÊN DỊCH:
// Pair<Integer, String> wrong = new Pair<>("seven", 7);
```

Record tự cung cấp `equals`, `hashCode`, `toString` theo các component. Ví dụ:

```text
Pair[key=7, value=READY]
```

**Khác biệt quan trọng:** `Pair<K,V>` là **data carrier**, không phải bản thân storage. Một Pair có thể giữ một cặp bất kỳ; nó không cài đặt việc tìm kiếm, cập nhật hay đảm bảo tính duy nhất của khóa. Những quy tắc này thuộc giao diện `Storage` và implementation.

### Tại sao constructor cấm null?

Bài thực hành chủ động chọn key/value **non-null**, vì `Storage.find` sẽ trả `Optional<V>`: null không được dùng như “một giá trị đã lưu nhưng null”. Điều này khiến việc phân biệt *absent* và *present* rõ ràng.

Đây là lựa chọn hợp đồng của API, **không phải Java Generics mặc định cấm null**. Một kiểu `Pair<String,Integer>` khác hoàn toàn có thể cho phép null nếu tác giả thiết kế điều đó.

## 6. Thiết kế interface `Storage<K,V>`: lập hợp đồng trước implementation

Định nghĩa:

```java
import java.util.List;
import java.util.Optional;

interface Storage<K,V> {
    void put(K key, V value);
    Optional<V> find(K key);
    Optional<V> remove(K key);
    boolean containsKey(K key);
    int size();
    List<Pair<K,V>> snapshot();

    default boolean isEmpty() {
        return size() == 0;
    }
}
```

Đây là generic interface với hai type parameters do **interface** khai báo. `Storage<Integer, Box<String>>` làm cho mọi method sử dụng `K`, `V` tương ứng tại compile time.

| Thành viên | Kiểu đầu vào/kết quả | Hợp đồng chọn cho bài |
| --- | --- | --- |
| `put(K,V)` | Nhận đúng K, V | Thêm hoặc ghi đè giá trị theo key; từ chối null |
| `find(K)` | `Optional<V>` | Có key: trả giá trị; không có: `Optional.empty()` |
| `remove(K)` | `Optional<V>` | Xóa key, trả giá trị cũ nếu có |
| `containsKey(K)` | `boolean` | Cho biết key đang được lưu |
| `size()` | `int` | Đếm số **key phân biệt** đang có |
| `snapshot()` | `List<Pair<K,V>>` | Trả ảnh chụp cấu trúc danh sách entry không cho sửa |
| `isEmpty()` | `boolean` | Default method dựa vào `size()==0` |

### Tại sao interface không tự chọn `HashMap`?

Một interface nên mô tả **khả năng mà client sử dụng**, còn chi tiết lưu trong RAM, database hay file thuộc implementation. Nếu code nghiệp vụ giữ biến:

```java
Storage<String, Integer> scores = new InMemoryStorage<>();
```

thì về sau có thể đổi sang implementation khác, miễn nó tuân thủ **cùng hợp đồng**. Tuy nhiên, generic type safety không tự bảo đảm hai implementation có cùng order, atomicity hay concurrency semantics; các yêu cầu đó cần ghi trong tài liệu công khai.

### Vì sao `Optional<V>`?

`Optional<V>` diễn đạt một kết quả **có thể vắng mặt** mà không phải dùng `null` làm tín hiệu mơ hồ:

```java
Optional<Integer> maybeScore = scores.find("An");
int score = maybeScore.orElse(0);
```

Để semantics này rõ, bài chọn **cấm lưu giá trị null**. Nếu thiết kế cho phép `null` như giá trị hợp lệ, `Optional.ofNullable(data.get(key))` không thể phân biệt “khóa tồn tại với null” và “khóa không tồn tại”. Khi đó phải thiết kế kiểu kết quả khác, hoặc thêm chính sách định nghĩa rõ.

## 7. Triển khai `InMemoryStorage<K,V>` bằng `LinkedHashMap`

Một implementation ban đầu:

```java
import java.util.*;

final class InMemoryStorage<K,V> implements Storage<K,V> {
    private final Map<K,V> data = new LinkedHashMap<>();

    @Override
    public void put(K key, V value) {
        data.put(
                Objects.requireNonNull(key, "key"),
                Objects.requireNonNull(value, "value"));
    }

    @Override
    public Optional<V> find(K key) {
        return Optional.ofNullable(
                data.get(Objects.requireNonNull(key, "key")));
    }

    @Override
    public Optional<V> remove(K key) {
        return Optional.ofNullable(
                data.remove(Objects.requireNonNull(key, "key")));
    }

    @Override
    public boolean containsKey(K key) {
        return data.containsKey(
                Objects.requireNonNull(key, "key"));
    }

    @Override
    public int size() {
        return data.size();
    }

    @Override
    public List<Pair<K,V>> snapshot() {
        List<Pair<K,V>> entries = new ArrayList<>();

        for (Map.Entry<K,V> entry : data.entrySet()) {
            entries.add(
                    new Pair<>(entry.getKey(), entry.getValue()));
        }

        return List.copyOf(entries);
    }
}
```

**Cách hoạt động:**

- `Map<K,V>` giữ quan hệ kiểu giống interface; các `put` không cần cast.
- `LinkedHashMap` mặc định giữ **thứ tự chèn của các key** khi duyệt `entrySet()`. Cập nhật giá trị của key đã có không biến nó thành key mới trong insertion-order mode.
- `private final Map<K,V> data` không cho caller giữ trực tiếp một biến tới backing map qua public API. `final` không làm map bất biến; nó chỉ cố định **tham chiếu field** sau khi khởi tạo.
- `put` gọi `Objects.requireNonNull` cho cả key/value để thực thi chính sách non-null ở runtime.
- `Optional.ofNullable(data.get(key))` trả empty khi không thấy key; vì value null bị cấm, hành vi không bị nhập nhằng trong điều kiện invariant còn đúng.
- `remove` lấy giá trị cũ rồi xóa; nếu không thấy key thì empty.
- `snapshot()` duyệt entry hiện tại, xây **các `Pair<K,V>` mới**, rồi dùng `List.copyOf` để caller không `add/remove/set` trên danh sách kết quả.

### Invariant cần duy trì

Bất biến của implementation:

1. **Mọi key/value được lưu đều non-null**, do các đường ghi công khai được kiểm soát.
2. `data` không bị công khai dưới dạng mutable alias.
3. Mỗi key xuất hiện tối đa một lần, theo semantics của `Map`/key equality và hash.
4. `size()` bằng số entry hiện tại của map.
5. `find/remove` dùng một quy tắc “không tìm thấy” nhất quán.
6. `snapshot()` không phụ thuộc vào các thay đổi cấu trúc sau khi đã tạo.
7. Class này **chưa tuyên bố thread-safe**; thao tác đồng thời không được tự động bảo đảm.

Những invariant này thuộc logic chương trình bên cạnh kiểm tra generic type arguments ở compile time. Nếu code cố tình dùng **raw `Storage`**, unchecked casts hay reflection để phá chúng, một `Map<K,V>` bị ô nhiễm vẫn có thể gây lỗi muộn — Java Generics không ngăn mọi hành vi phá hệ thống kiểu.

## 8. Invariance: `Storage<Integer,String>` không phải `Storage<Number,Object>`

Java Generics **bất biến** (*invariant*) theo type arguments. Ví dụ:

```java
Storage<Integer, String> typed = new InMemoryStorage<>();

// KHÔNG BIÊN DỊCH:
// Storage<Number, Object> wider = typed;
```

Điều này không mâu thuẫn với `Integer extends Number` và `String extends Object`. Nếu được gán như vậy, caller có thể dùng `wider.put(3.14, new Object())` và làm hỏng lời hứa `Storage<Integer,String>`.

Tương tự:

```java
Storage<Integer, Box<String>> users = new InMemoryStorage<>();

// KHÔNG BIÊN DỊCH:
// users.put("101", Box.of("An")); // key phải là Integer
// users.put(101, Box.of(42));     // value phải là Box<String>
```

**Đó là lợi ích của generic API**: compiler loại nhiều thao tác sai trước khi chạy.

Đừng sửa bằng cast raw hoặc `(Storage)`: thao tác đó làm mất kiểm tra type arguments, dẫn tới heap pollution và lỗi xuất hiện xa vị trí vi phạm.

## 9. Helper method generic: làm việc với mọi storage có K và V tương ứng

Có thể viết một method dùng lại cho tất cả storage:

```java
static <K,V> void printAll(Storage<K,V> storage) {
    for (Pair<K,V> pair : storage.snapshot()) {
        System.out.println(pair.key() + " => " + pair.value());
    }
}
```

Khi gọi:

```java
Storage<String,Integer> scores = new InMemoryStorage<>();
scores.put("An", 9);
printAll(scores);
```

compiler suy luận `K=String` và `V=Integer`. Method generic này **không cần hiểu riêng** `Integer` hay `String`; nó chỉ dựa vào những thao tác mà interface bảo đảm.

Với `Box<String>` làm value, `pair.value()` có kiểu `Box<String>` ở compile time. In trực tiếp record sẽ dùng `toString()` theo record component, nhưng print format là **lựa chọn của helper**, không nằm trong hợp đồng lưu trữ.

### Khi nào dùng wildcard?

Nếu helper chỉ đọc entry để in mà không cần liên hệ giữa các vị trí tham số/return, ta cũng có thể viết một biến thể dùng wildcard:

```java
static void showUnknown(Storage<?,?> storage) {
    for (Pair<?,?> pair : storage.snapshot()) {
        System.out.println(pair.key() + " => " + pair.value());
    }
}
```

Ở đây ta chấp nhận một storage có kiểu khóa/giá trị chưa biết và chỉ **đọc**; việc gọi `storage.put` qua `Storage<?,?>` với key/value cụ thể không an toàn do compiler không biết các wildcard captures.

Nếu method cần nối kiểu của storage nguồn và đích, hãy dùng named type parameters và wildcard có chủ đích, thay vì `Object` ở mọi nơi.

## 10. Chương trình Java 17+ hoàn chỉnh

Lưu tệp **`GenericStorageDemo.java`**. Toàn bộ chương trình chỉ dùng Java standard library, **không cần dependency**:

```java
import java.util.*;
import java.util.function.Function;

public class GenericStorageDemo {
    record Box<T>(T value) {
        Box {
            Objects.requireNonNull(value, "value");
        }

        static <U> Box<U> of(U value) {
            return new Box<>(value);
        }

        <R> Box<R> map(Function<? super T, ? extends R> mapper) {
            return Box.of(
                    Objects.requireNonNull(mapper, "mapper")
                            .apply(value));
        }
    }

    record Pair<K,V>(K key, V value) {
        Pair {
            Objects.requireNonNull(key, "key");
            Objects.requireNonNull(value, "value");
        }
    }

    interface Storage<K,V> {
        void put(K key, V value);
        Optional<V> find(K key);
        Optional<V> remove(K key);
        boolean containsKey(K key);
        int size();
        List<Pair<K,V>> snapshot();

        default boolean isEmpty() {
            return size() == 0;
        }
    }

    static final class InMemoryStorage<K,V>
            implements Storage<K,V> {
        private final Map<K,V> data = new LinkedHashMap<>();

        @Override
        public void put(K key, V value) {
            data.put(
                    Objects.requireNonNull(key, "key"),
                    Objects.requireNonNull(value, "value"));
        }

        @Override
        public Optional<V> find(K key) {
            return Optional.ofNullable(
                    data.get(Objects.requireNonNull(key, "key")));
        }

        @Override
        public Optional<V> remove(K key) {
            return Optional.ofNullable(
                    data.remove(Objects.requireNonNull(key, "key")));
        }

        @Override
        public boolean containsKey(K key) {
            return data.containsKey(
                    Objects.requireNonNull(key, "key"));
        }

        @Override
        public int size() {
            return data.size();
        }

        @Override
        public List<Pair<K,V>> snapshot() {
            List<Pair<K,V>> result = new ArrayList<>();

            for (Map.Entry<K,V> entry : data.entrySet()) {
                result.add(
                        new Pair<>(entry.getKey(), entry.getValue()));
            }

            return List.copyOf(result);
        }
    }

    static <K,V> void printAll(Storage<K,V> storage) {
        for (Pair<K,V> pair : storage.snapshot()) {
            System.out.println(pair.key()
                    + " => " + pair.value());
        }
    }

    static void expectFailure(String title, Runnable operation) {
        try {
            operation.run();
            System.out.println(title + ": unexpected success");
        } catch (NullPointerException
                 | UnsupportedOperationException ex) {
            System.out.println(title + ": "
                    + ex.getClass().getSimpleName());
        }
    }

    public static void main(String[] args) {
        Storage<Integer, Box<String>> users = new InMemoryStorage<>();

        System.out.println("Initially empty: " + users.isEmpty());

        users.put(101, Box.of("An"));
        users.put(102, Box.of("Binh"));

        System.out.println("User 101: "
                + users.find(101)
                       .map(Box::value)
                       .orElse("missing"));

        System.out.println("User 999: "
                + users.find(999)
                       .map(Box::value)
                       .orElse("missing"));

        System.out.println("Mapped length: "
                + users.find(102).orElseThrow()
                       .map(String::length).value());

        Pair<Integer,String> ticket = new Pair<>(7, "READY");
        System.out.println("Pair: " + ticket);

        List<Pair<Integer, Box<String>>> before = users.snapshot();

        users.put(103, Box.of("Chi"));

        System.out.println("Snapshot count: " + before.size());
        System.out.println("Storage count: " + users.size());

        System.out.println("Remove 101: "
                + users.remove(101)
                       .map(Box::value).orElse("missing"));

        System.out.println("Contains 101: " + users.containsKey(101));

        System.out.println("Remaining entries:");
        printAll(users);

        expectFailure("Null value",
                () -> users.put(999, null));
        expectFailure("Null key",
                () -> users.find(null));
        expectFailure("Snapshot mutation",
                () -> before.add(new Pair<>(9, Box.of("X"))));

        Storage<String,Integer> scores = new InMemoryStorage<>();
        scores.put("An", 9);
        System.out.println("Score: "
                + scores.find("An").orElseThrow());
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 GenericStorageDemo.java
java GenericStorageDemo
```

**Standard output**:

```text
Initially empty: true
User 101: An
User 999: missing
Mapped length: 4
Pair: Pair[key=7, value=READY]
Snapshot count: 2
Storage count: 3
Remove 101: An
Contains 101: false
Remaining entries:
102 => Box[value=Binh]
103 => Box[value=Chi]
Null value: NullPointerException
Null key: NullPointerException
Snapshot mutation: UnsupportedOperationException
Score: 9
```

Các dòng cần hiểu rõ:

1. Trước khi `put`, `size()==0`, nên default `isEmpty()` trả `true`.
2. `find(101)` tìm thấy `Box<String>`; `Optional.map(Box::value)` lấy chuỗi `"An"`.
3. `find(999)` trả `Optional.empty()`, nên `orElse("missing")`.
4. `Box<String>.map(String::length)` trả `Box<Integer>` có giá trị 4, không sửa Box ban đầu.
5. Pair record có `toString()` được sinh từ hai component.
6. `before` chứa hai entry ở thời điểm `snapshot()`; thêm key 103 sau đó làm `size()` của storage thành 3, nhưng `before.size()` vẫn là 2.
7. `remove(101)` trả giá trị cũ; `containsKey(101)` sau đó là `false`.
8. `LinkedHashMap` duy trì insertion order cho các key còn lại: 102 rồi 103.
9. Hai thao tác null bị chặn bằng `Objects.requireNonNull`; sửa danh sách snapshot gây `UnsupportedOperationException`.
10. Cùng implementation `InMemoryStorage<K,V>` dùng được cho `Storage<String,Integer>` mà không cast.

Hàm `expectFailure` chỉ để demo các exception đã dự kiến; trong bài kiểm thử chuyên nghiệp nên dùng assertion chính xác rằng **đúng exception** được ném và thất bại nếu thao tác **không ném exception**, thay vì chỉ in `unexpected success`.

## 11. Quy tắc null, empty và lỗi: ghi rõ trong tài liệu

Không có quy tắc mặc định của Java Generics rằng `T`, `K` hay `V` phải non-null. Đó là **hợp đồng được chọn** cho các class trong bài.

Với `Box<T>`:

- `new Box<>(null)` hoặc `Box.of(null)` bị constructor từ chối bằng `NullPointerException`.
- `box.map(null)` cũng bị từ chối.
- `box.map(...)` nếu mapper trả null, `Box.of` từ chối kết quả null.
- `Box<T>` không có khái niệm empty; dùng `Optional<T>` nếu cần biểu thị “không có giá trị”.

Với `Pair<K,V>`:

- Key và value đều phải non-null.
- Các component có thể **cùng runtime class**; không bắt buộc khác nhau.
- Pair không tự thực thi quy tắc unique key, sorting hay persistence.

Với `Storage<K,V>`:

- `put` nhận key và value non-null; nếu key đã tồn tại thì cập nhật giá trị.
- `find`/ `remove` trả `Optional.empty()` nếu không tồn tại.
- `find(null)`, `remove(null)`, `containsKey(null)`, `put(null,...) ` đều không hợp lệ theo implementation.
- `snapshot()` trả các cặp đang có tại thời điểm tạo danh sách mới; client không thêm/xóa phần tử vào kết quả được.
- Storage không bảo đảm deep clone value object và không tự thread-safe.

**Nên ghi hợp đồng bằng Javadoc**, không để người dùng phải suy luận từ `Optional` hay từ tên `InMemoryStorage`.

## 12. Javadoc cho một interface generic: tài liệu hóa cả kiểu và hành vi

Một interface public có thể khai báo:

```java
/**
 * Stores non-null values under non-null keys.
 *
 * @param <K> key type, using its equals/hashCode semantics
 * @param <V> stored value type
 */
interface Storage<K,V> {
    /**
     * Inserts or replaces a value associated with a key.
     *
     * @param key non-null key
     * @param value non-null value
     * @throws NullPointerException if key or value is null
     */
    void put(K key, V value);

    /**
     * Looks up a value without removing it.
     *
     * @param key non-null key
     * @return present value, or empty if the key is absent
     * @throws NullPointerException if key is null
     */
    Optional<V> find(K key);

    // Other operations follow the same contract.
}
```

Đây là **đoạn khai báo độc lập minh họa Javadoc**; chương trình runnable ở mục 10 có phiên bản đầy đủ của interface. Với public API, bổ sung Javadoc cho `remove`, `size`, `containsKey`, `snapshot`, thứ tự và concurrency policy.

Lưu ý cú pháp:

- `@param <K>`, `@param <V>` mô tả **type parameters** của interface.
- `@param key`, `@param value` mô tả **tham số giá trị** của method.
- `@return` giải thích ý nghĩa empty/present.
- `@throws` nói về trường hợp lỗi theo hợp đồng.

Tài liệu không thể thay thế việc **thực thi** hợp đồng. Nếu Javadoc nói cấm null, implementation phải kiểm tra hoặc dùng cấu trúc dữ liệu áp đặt cùng chính sách một cách nhất quán.

## 13. Tại sao dùng `Map<K,V>` thay `Object[]` ở implementation đầu tiên?

Một cài đặt `Object[]` hoặc raw `Map` có thể cần unchecked casts và chứng minh bất biến phức tạp. Trong bài này, `LinkedHashMap<K,V>` đã có typed API đủ dùng:

```java
private final Map<K,V> data = new LinkedHashMap<>();
```

Compiler bảo vệ khi gọi:

```java
data.put(key, value);
V stored = data.get(key);
```

Không cần `@SuppressWarnings("unchecked")`, không cần tự tạo generic array và không cần `(V)` ở getter.

**Quy tắc thiết kế:** chọn collection generic chuẩn nếu nó diễn đạt đúng dữ liệu và không gây hạn chế nghiệp vụ không cần thiết. Chỉ tự viết low-level storage trên `Object[]` khi thật sự có lý do về bộ nhớ, thuật toán hoặc layout, và lúc đó phải duy trì invariant của mọi đường ghi/đọc cùng phạm vi cast thật hẹp.

Type erasure vẫn tồn tại: nếu caller cố tình dùng `Storage raw` hoặc reflection, họ có thể bypass một phần compile-time guarantees. Đó không phải lý do để bỏ generics trong API bình thường.

## 14. `Pair<K,V>` với `Map.Entry<K,V>`: nên chọn gì?

Java đã có `Map.Entry<K,V>` và `Map.entry(key,value)` để biểu diễn các entry đơn giản. Vậy có cần `Pair<K,V>` riêng?

**Dùng `Pair<K,V>` hợp lý khi:**

- Bài toán cần một data carrier **độc lập với khái niệm Map**.
- Bạn muốn đặt tên component rõ `key`/`value` hoặc `first`/`second`.
- Muốn một record bất biến về các component references, `equals/hashCode/toString` theo record.
- Muốn mở rộng domain behavior phù hợp và tài liệu hóa điều kiện key/value.

**Dùng `Map.Entry<K,V>` hợp lý khi:**

- Đang làm việc trực tiếp với API của `Map`.
- Không cần một abstraction Pair độc lập.
- Có thể dùng `Map.entry(k,v)` cho một cặp có hợp đồng phù hợp (factory này không nhận null).

**Không được đánh đồng `Map.Entry` lấy từ `map.entrySet()` với một immutable snapshot.** Entry từ view của map có thể phản ánh live data và các điều kiện về `setValue`/mutation phụ thuộc implementation; nếu trả chúng ra ngoài, cần đọc hợp đồng cụ thể. Trong ví dụ, ta tạo các `Pair` mới rồi `List.copyOf` để tránh đưa trực tiếp một live `entrySet()` cho caller.

## 15. Snapshot chỉ bất biến về cấu trúc; object graph có thể mutable

Trả `List.copyOf(entries)` bảo vệ danh sách output khỏi `add`, `remove`, `set`; danh sách cũng không tự thay đổi khi storage thêm/xóa entry sau đó.

Nhưng xét một value mutable:

```java
Storage<Integer, List<String>> store = new InMemoryStorage<>();
List<String> original = new ArrayList<>(List.of("a"));
store.put(1, original);

List<Pair<Integer,List<String>>> snapshot = store.snapshot();
original.add("b");

System.out.println(snapshot.get(0).value()); // [a, b]
```

Code trên cho thấy **snapshot cấu trúc không phải deep copy**. Record `Pair` giữ tham chiếu tới cùng `List<String>`; nội dung list ấy vẫn thay đổi qua `original`.

Nếu mục tiêu của ứng dụng đòi một snapshot sâu:

- Có thể yêu cầu `V` là kiểu immutable theo hợp đồng (nhưng Java generic bound không thể diễn tả “mọi đối tượng của V đều immutable” theo cách tổng quát).
- Có thể nhận copier `Function<? super V,? extends V>` hoặc serializer để tạo bản sao thích hợp, tùy domain.
- Có thể chuyển dữ liệu vào immutable domain records/DTO đã kiểm soát các trường mutable.
- Phải xử lý cả concurrency và tính nhất quán khi đọc nguồn.

Một API không nên hứa “fully immutable snapshot” chỉ vì nó trả `List<Pair<K,V>>` được tạo bằng `List.copyOf`.

## 16. PECS khi muốn sao chép giữa hai storage tương thích

Trong ví dụ chính, `Storage<K,V>` giữ quan hệ kiểu chặt. Với thao tác **chỉ đọc từ nguồn và ghi vào đích**, có thể dùng variance tại vị trí sử dụng:

```java
static <K,V> int copyEntries(
        Storage<K, ? extends V> source,
        Storage<K, ? super V> destination) {
    int count = 0;

    for (Pair<K, ? extends V> pair : source.snapshot()) {
        destination.put(pair.key(), pair.value());
        count++;
    }

    return count;
}
```

Đây là **snippet cho method helper** với `Storage` và `Pair` đã định nghĩa. Quan hệ theo PECS:

- `source` sản xuất giá trị đọc như `V` hoặc subtype của `V`, nên dùng `? extends V`.
- `destination` tiêu thụ giá trị `V`, nên dùng `? super V`.
- `K` được giữ như cùng một type parameter để key từ source có thể truyền sang destination đúng kiểu.

Ví dụ hợp lý:

```java
Storage<String,Integer> small = new InMemoryStorage<>();
Storage<String,Number> wide = new InMemoryStorage<>();
small.put("a", 3);

int copied = copyEntries(small, wide);
```

Lời gọi hợp lệ vì `Integer` là subtype của `Number`. Nhưng **`Storage<String,Integer>` vẫn không phải subtype trực tiếp của `Storage<String,Number>`**. Chính wildcard trong **chữ ký helper** cho phép những đối số cùng tham gia một operation.

Một chú ý nghiệp vụ: `copyEntries` duyệt snapshot nguồn và ghi đè nếu key đã có ở đích. Giá trị trả về `count` ở đây là số entry đã xử lý thành công, **không phải số key mới thực sự thêm**. Nếu destination có cùng key hoặc đang dùng cùng instance với source, cần làm rõ semantics/side effects.

## 17. So sánh `Storage<K,V>` với `Storage<K,Box<V>>`

Bạn có hai kiểu thiết kế khả thi:

```java
Storage<Integer,String> direct = new InMemoryStorage<>();
Storage<Integer,Box<String>> wrapped = new InMemoryStorage<>();
```

Trong `direct`, giá trị là chuỗi. Trong `wrapped`, giá trị là **một wrapper có khả năng map và có invariant non-null**.

Không có lựa chọn nào luôn đúng:

- **Chọn `Storage<K,V>` trực tiếp** nếu abstraction Box không thêm ý nghĩa domain, chỉ khiến caller viết thêm `.value()`.
- **Chọn `Storage<K,Box<V>>`** nếu domain thực sự cần một lớp wrapper: provenance, validation, trạng thái đã chuẩn hóa, hoặc các phép biến đổi có hợp đồng riêng.
- Với `Optional<V>`, không nên tự động tạo `Box<Optional<V>>` trừ khi các tầng wrapper có ý nghĩa khác nhau rõ ràng; quá nhiều wrapper làm API khó hiểu.

Bài thực hành dùng `Storage<Integer,Box<String>>` để minh họa composition của generic types; trong code production, cần đánh giá xem Box có tạo giá trị thiết kế thực sự hay không.

## 18. Kiểm thử các trường hợp biên

Bên cạnh chương trình chạy, một bộ kiểm thử chuyên nghiệp nên kiểm tra:

| Tình huống | Kết quả mong đợi theo hợp đồng |
| --- | --- |
| `new InMemoryStorage<>()` | `isEmpty()==true`, `size()==0` |
| `put(k,v)` lần đầu | `size` tăng một, `find(k)` trả `v` |
| `put(k,v2)` với key đã có | `size` không tăng, `find(k)` trả `v2` |
| `find(missing)` | `Optional.empty()` |
| `remove(existing)` | Trả giá trị cũ, key biến mất |
| `remove(missing)` | `Optional.empty()`, không đổi size |
| `containsKey(existing)` | `true` |
| `null` key ở put/find/remove/containsKey | `NullPointerException` |
| `null` value ở put | `NullPointerException` |
| `Box.of(null)`, `new Pair<>(null,v)` | `NullPointerException` |
| `Box.map` với mapper phù hợp | Tạo `Box<R>` mới, không sửa Box cũ |
| `Box.map` với mapper `null`/trả `null` | `NullPointerException` |
| Snapshot trước/sau mutation | Snapshot trước giữ số entry và key/value references tại thời điểm tạo |
| `snapshot().add(...)` | `UnsupportedOperationException` |
| Giá trị mutable bị sửa qua alias | Snapshot có thể thấy trạng thái mới của chính value object |
| `Storage<K,V>` sai K hoặc V | Lời gọi typed bị compiler từ chối |
| Hai type arguments `K`, `V` giống nhau | Vẫn hợp lệ |
| Thao tác trên nhiều thread | Không có bảo đảm thread-safety từ implementation mẫu |

Đối với JUnit 5, bạn có thể dùng `assertThrows(NullPointerException.class, () -> storage.put(1,null))` và `assertEquals(...)`; nhưng JUnit là dependency ngoài JDK, không cần để chạy chương trình ở mục 10.

### Kiểm thử kiểu compile-time

Một fixture cố ý sai có thể chứa:

```java
// KHÔNG BIÊN DỊCH, chỉ để kiểm chứng compiler:
Storage<Integer,String> text = new InMemoryStorage<>();
text.put("not an Integer", "A");
text.put(1, 123);
```

Nếu API của bạn vô tình chuyển `put(K,V)` thành `put(Object,Object)`, những lời gọi này có thể không còn bị compiler chặn — dấu hiệu **hợp đồng kiểu đã yếu đi** dù functional tests với dữ liệu đúng vẫn pass.

## 19. Sai lầm thường gặp khi tự xây generic API

**Sai lầm 1 — Dùng raw `Storage`:**

```java
Storage raw = new InMemoryStorage();
raw.put("key", 3);
```

Code có thể biên dịch với raw/unchecked warnings nhưng mất quan hệ kiểu K/V. Dùng `Storage<String,Integer>` nếu đó là contract bạn muốn.

**Sai lầm 2 — Tưởng `Pair<K,V>` đòi K khác V:** không. `Pair<String,String>` hoàn toàn hợp lệ.

**Sai lầm 3 — Tưởng `Box<T>` có thể khai báo `static T cache`:** không. Static context không được dùng type variable của class theo cách đó; static factory phải có type parameter riêng, như `static <U> Box<U> of(U)`.

**Sai lầm 4 — Tạo `new T[n]` để lưu generic:** không hợp lệ với type variable non-reifiable. Dùng các collection generic chuẩn khi đủ nhu cầu.

**Sai lầm 5 — Nhầm `Storage<Integer,Box<String>>` với `Storage<Integer,String>`:** value types khác nhau; không thể tự động ép Box ra String ở compile time. Muốn chuyển dữ liệu, viết một phép mapping rõ ràng.

**Sai lầm 6 — Gọi `find` và giả định luôn có value:** `Optional<V>` có thể empty. Dùng `orElse`, `ifPresent`, `map` hoặc `orElseThrow` với chính sách lỗi rõ.

**Sai lầm 7 — Dùng null làm tín hiệu missing trong implementation vốn cho phép null value:** làm `Optional.ofNullable(data.get(k))` không phân biệt missing/present-null. Chọn invariant non-null hoặc kiểu kết quả khác.

**Sai lầm 8 — Công khai backing map:** caller có thể sửa state ngoài các method bảo vệ invariant. Trong bài, map là `private`, snapshot được xây riêng.

**Sai lầm 9 — Tưởng `final Map<K,V>` nghĩa map immutable:** `final` chỉ áp dụng tới tham chiếu field; nội dung map vẫn mutable.

**Sai lầm 10 — Tưởng `List.copyOf` deep-copy mọi element:** không. Các object được Pair/Box tham chiếu vẫn có thể mutable.

**Sai lầm 11 — Tưởng interface luôn quy định thứ tự:** thứ tự insertion là lựa chọn của `LinkedHashMap` ở implementation này. Nếu tất cả implementations phải bảo đảm cùng thứ tự, phải đưa vào **hợp đồng interface** và test.

**Sai lầm 12 — Tưởng thread-safe vì có generics:** generic typing không bảo đảm đồng bộ/visibility. Chọn concurrent implementation hoặc quản lý synchronization nếu cần.

**Sai lầm 13 — Dùng unchecked cast để nối `Storage<K,V>` với `Storage<K,? super V>`:** thường có thể viết helper PECS typed; cast không phải lối tắt an toàn.

**Sai lầm 14 — Không nêu semantics khi `put` ghi đè:** với Map, cùng key thay giá trị cũ; người dùng API cần biết đó là update hay lỗi trùng khóa.

**Sai lầm 15 — Làm Box mutable khi không cần:** nếu chỉ cần một giá trị chuyển qua các bước, Box record immutable về component reference thường dễ kiểm soát hơn một class có `set(T)`.

## 20. Bài tập mở rộng có hướng dẫn

### Bài A — Thêm `putIfAbsent`

Mở rộng `Storage<K,V>`:

```java
Optional<V> putIfAbsent(K key, V value);
```

Chọn và tài liệu hóa hợp đồng: nếu key chưa tồn tại thì thêm và trả empty; nếu tồn tại thì giữ nguyên và trả value cũ. Dùng API `Map.putIfAbsent` sau khi kiểm tra null, đồng thời xác nhận implementation không cho lưu null. Kiểm thử size không đổi khi key đã tồn tại.

### Bài B — Tạo `Storage<K,V>` dạng đọc

Nếu nhiều caller chỉ đọc, tách interface:

```java
interface ReadOnlyStorage<K,V> {
    Optional<V> find(K key);
    boolean containsKey(K key);
    int size();
    List<Pair<K,V>> snapshot();
}
```

Sau đó cho `Storage<K,V>` mở rộng `ReadOnlyStorage<K,V>`. Phương pháp *interface segregation* giúp ngăn code chỉ cần đọc phụ thuộc vào `put/remove`.

**Lưu ý:** interface read-only không tự bảo đảm backing storage immutable — mã giữ writable alias vẫn có thể cập nhật dữ liệu. Đây là phân quyền ở **mặt API**, không nhất thiết là snapshot bất biến.

### Bài C — Thêm `mapValues`

Thiết kế một helper:

```java
static <K,V,R> Storage<K,R> mapValues(
        Storage<K,V> source,
        Function<? super V, ? extends R> mapper)
```

Phương thức nên tạo **storage mới**, giữ key `K`, chuyển value `V` thành `R`. Kiểm tra mapper khác null, kết quả mapper non-null theo contract của `Storage`, và xác định thứ tự/side effects khi mapper ném exception.

### Bài D — Kiểm tra behavior của snapshot

Tạo snapshot khi có hai entry, thêm một entry mới vào storage, xác minh snapshot trước vẫn chứa hai entry. Sau đó thử value là mutable list để nhận thấy snapshot không deep-copy. Tài liệu hóa hai tầng **bất biến cấu trúc** và **bất biến trạng thái object bên trong**.

### Bài E — Đổi implementation sang persistence

Thử định nghĩa `FileStorage<K,V>` hoặc `DatabaseStorage<K,V>` vẫn implements `Storage<K,V>`. Đừng giả định method `put` luôn rẻ, nguyên tử hoặc không lỗi I/O. Cần bổ sung exception strategy, serialization/codec cho K/V, transactions và concurrency policy trong hợp đồng.

## 21. Checklist đánh giá bài thực hành

Trước khi dùng bộ class này trong một module lớn hơn, hãy tự kiểm tra:

1. **Cả ba abstraction có đúng phạm vi?** Box giữ một giá trị; Pair mang hai component; Storage định nghĩa hành vi lưu.
2. **Tên type parameter nhất quán?** `T`, `K`, `V`, `R`, `U` có đúng vai trò không?
3. **Static generic factory được khai báo đúng?** `static <U> Box<U> of(U)`, không dùng `T` của class trong static context.
4. **API typed không có raw casts không cần thiết?** `Map<K,V>`, `Pair<K,V>`, `List<Pair<K,V>>` rõ ràng.
5. **Null policy rõ chưa?** Không lẫn missing với present-null.
6. **Update/remove semantics rõ chưa?** Cùng key ghi đè; remove trả giá trị trước khi xóa.
7. **Snapshot là copy hay view?** Trong bài là copy cấu trúc, không deep copy.
8. **Thứ tự entry có được yêu cầu không?** Nếu cần như một bảo đảm public API, hãy ghi vào interface contract.
9. **Tính đa hình đã được thử chưa?** Cùng interface dùng `Integer/Box<String>` và `String/Integer`.
10. **Có unit tests cho các trường hợp biên không?** Empty, duplicate key, null, wrong generic types, snapshot mutation, nullable mapper result.
11. **Có cần concurrency/persistence không?** Nếu có, thiết kế thêm ngoài generic interface mẫu.
12. **Có tách domain policy khỏi storage logic không?** Đừng ép một policy về người dùng vào `Storage<K,V>` nếu nó chỉ đúng cho một business entity.

## 22. Tổng kết

`Box<T>`, `Pair<K,V>` và `Storage<K,V>` minh họa ba cấp độ dùng Java Generics: **đóng gói một kiểu**, **liên hệ hai kiểu**, và **xây dựng một hợp đồng hành vi độc lập với implementation**. `Box<T>` cho thấy static generic factory và generic `map`; `Pair<K,V>` cho thấy hai component có loại khác nhau; `Storage<K,V>` dùng cùng type parameters xuyên suốt `put`, `find`, `remove`, `snapshot`, còn `InMemoryStorage` hiện thực thông qua `LinkedHashMap<K,V>` không cần unchecked casts.

Điểm cần nhớ không chỉ là syntax `<T>`, `<K,V>`: một API generic tốt phải **giữ mối quan hệ kiểu đúng ở compile time**, **nói rõ điều kiện runtime** (null, missing, update, order, mutation, ownership), **che giấu backing data** và **kiểm thử các ranh giới**. Khi những điều đó nhất quán, các abstraction có thể được dùng lại và mở rộng mà không buộc caller phụ thuộc vào raw types hoặc cast không kiểm tra.