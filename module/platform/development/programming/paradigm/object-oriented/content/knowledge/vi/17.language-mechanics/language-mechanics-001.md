# Java Generics: Kiểu tổng quát và lớp có tham số kiểu

> **Chủ đề:** OOP → Cơ chế ngôn ngữ → Kiểu tổng quát và lớp có tham số kiểu.  
> **Mục tiêu:** Tự khai báo và sử dụng lớp `Box<T>`, `Pair<K,V>` và lớp lưu trữ dữ liệu có tham số kiểu; hiểu generic type, type parameter, type argument, type inference, giới hạn kiểu, wildcard và type erasure; tránh các lỗi phổ biến khi thiết kế API Java.

## 1. Generics giải quyết vấn đề gì?

**Generics** (kiểu tổng quát) cho phép khai báo lớp, interface hoặc phương thức mà **một số kiểu dữ liệu được để thành tham số**, thay vì viết lại mã cho từng kiểu. Nhờ đó, trình biên dịch Java phát hiện nhiều thao tác sai kiểu ngay khi biên dịch.

Ví dụ trước thời kỳ dùng generic type an toàn:

~~~java
import java.util.ArrayList;
import java.util.List;

List raw = new ArrayList(); // raw type: không chỉ ra kiểu phần tử
raw.add("Java");
raw.add(123);              // Cả chuỗi lẫn số đều được chấp nhận

String name = (String) raw.get(1);
// Biên dịch được (có cảnh báo raw/unchecked) nhưng chạy sẽ
// gặp ClassCastException vì phần tử ở vị trí 1 là Integer.
~~~

Với generic type, hợp đồng kiểu trở nên rõ ràng:

~~~java
List<String> names = new ArrayList<>();
names.add("Java");
names.add("OOP");

// names.add(123); // LỖI BIÊN DỊCH: Integer không phải String.
String first = names.get(0); // Không phải ép kiểu thủ công.
~~~

**Điểm cốt lõi:** Generics tăng **type safety tại compile time**, làm rõ ý nghĩa API và giảm ép kiểu. Nó **không tạo ra một bản sao class riêng tại runtime cho mỗi tham số kiểu**: Java chủ yếu triển khai generics bằng cơ chế *type erasure* (xóa thông tin tham số kiểu trong bytecode ở nhiều vị trí), sẽ giải thích ở phần sau.

## 2. Đọc đúng cú pháp generic type

| Cú pháp | Ý nghĩa | Ví dụ |
|---|---|---|
| `class Box<T>` | Khai báo **lớp có một tham số kiểu** tên `T` | `Box<String>` |
| `interface Store<K,V>` | Interface có hai tham số kiểu | `Store<Long,User>` |
| `Box<String>` | Một **parameterized type**: kiểu cụ thể khi sử dụng `Box` với đối số kiểu `String` | `Box<String> x` |
| `T`, `K`, `V` | **Type parameters**, những tên tượng trưng trong khai báo | `T value` |
| `String`, `Long`, `User` | **Type arguments**, những kiểu được truyền khi dùng generic | `new Box<String>(...)` |
| `<>` | **Diamond operator**, trình biên dịch suy luận type arguments phù hợp | `new Box<>("Hi")` |
| `<T> T first(...)` | Phương thức generic khai báo tham số kiểu **riêng** | `static <T> T first(List<T> list)` |

Tên `T` không phải từ khóa của Java. Các tên quy ước thường gặp: `T` (Type), `E` (Element), `K` (Key), `V` (Value), `R` (Result), `S` (một kiểu khác). Có thể chọn tên rõ nghĩa hơn cho hệ thống phức tạp, ví dụ `ENTITY`, `ID`, nhưng chữ hoa ngắn giúp đọc các API Java phổ biến.

Phân biệt hai cách viết:

~~~java
class Holder<T> {
    T value; // T do class khai báo, dùng được ở instance member.

    Holder(T value) {
        this.value = value;
    }

    T get() {
        return value;
    }

    static <U> U identity(U x) {
        // U được khai báo bởi chính phương thức static này.
        return x;
    }
}
~~~

Một phương thức `static` **không** thể dùng `T` của class để khai báo field hoặc method signature phụ thuộc vào instance type parameter, vì thành viên static thuộc về class, không thuộc riêng `Holder<String>` hay `Holder<Integer>`. Nhưng phương thức static **có thể tự khai báo** `<U>` như `identity`.

## 3. Ví dụ Java 17 hoàn chỉnh: lớp Box, Pair và Repository tổng quát

Ví dụ sau chạy độc lập bằng JDK 17+, không cần Spring hay thư viện ngoài. Nó minh họa ba cấp độ sử dụng:

1. `Box<T>` lưu một giá trị với kiểu cụ thể được quyết định ở nơi sử dụng.
2. `Pair<K,V>` có **hai** tham số kiểu độc lập.
3. `InMemoryRepository<ID,T>` tái sử dụng cùng một implementation lưu dữ liệu cho nhiều loại entity và ID, nhưng vẫn ràng buộc kiểu đúng.

Tạo tệp **`GenericsDemo.java`**:

~~~java
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.function.Function;

// Generic class: T đại diện cho kiểu dữ liệu được chứa.
final class Box<T> {
    private T value;

    Box(T value) {
        this.value = Objects.requireNonNull(value, "value");
    }

    T get() {
        return value;
    }

    void set(T next) {
        value = Objects.requireNonNull(next, "next");
    }

    // Generic method: R là tham số kiểu MỚI của phương thức.
    // Có thể biến Box<String> thành Box<Integer>, v.v.
    <R> Box<R> map(Function<? super T, ? extends R> mapper) {
        Objects.requireNonNull(mapper, "mapper");
        return new Box<>(
                Objects.requireNonNull(mapper.apply(value), "mapped value"));
    }
}

// Generic record: các thành phần độc lập về kiểu.
record Pair<K, V>(K key, V value) {}

// Entity ví dụ, record bất biến.
record User(String id, String name) {}

// Repository in-memory phục vụ demo, không phải kho dữ liệu bền vững.
final class InMemoryRepository<ID, T> {
    private final Function<T, ID> idOf;
    private final Map<ID, T> data = new HashMap<>();

    InMemoryRepository(Function<T, ID> idOf) {
        this.idOf = Objects.requireNonNull(idOf, "idOf");
    }

    void save(T item) {
        Objects.requireNonNull(item, "item");
        ID id = Objects.requireNonNull(idOf.apply(item), "id");
        data.put(id, item);
    }

    Optional<T> findById(ID id) {
        Objects.requireNonNull(id, "id");
        return Optional.ofNullable(data.get(id));
    }
}

public class GenericsDemo {
    public static void main(String[] args) {
        Box<String> language = new Box<>("Java"); // Diamond: suy luận T
        Box<Integer> counter = new Box<>(42);

        System.out.println("Box<String>: " + language.get());
        System.out.println("Box<Integer>: " + counter.get());

        // R = Integer vì String::length trả về int, được boxing.
        Box<Integer> length = language.map(String::length);
        System.out.println("Độ dài: " + length.get());

        Pair<String, Long> invoice = new Pair<>("HD-01", 180_000L);
        System.out.println(
                "Hóa đơn: " + invoice.key() + " = " + invoice.value());

        InMemoryRepository<String, User> users =
                new InMemoryRepository<>(User::id);
        users.save(new User("U-01", "Lan"));

        System.out.println(
                "Người dùng: " + users.findById("U-01").orElseThrow().name());
    }
}
~~~

Chạy:

~~~bash
javac GenericsDemo.java
java GenericsDemo
~~~

Kết quả dự kiến:

~~~text
Box<String>: Java
Box<Integer>: 42
Độ dài: 4
Hóa đơn: HD-01 = 180000
Người dùng: Lan
~~~

### Đọc luồng kiểu

- Với `Box<String> language`, mọi chỗ sử dụng `T` trong thành viên instance của `Box<T>` được **trình biên dịch xem là `String`**. `language.set(123)` sẽ không biên dịch.
- Với `Box<Integer> counter`, `counter.get()` có kiểu trả về `Integer` tại compile time.
- `<R> Box<R> map(...)` cho phép biến một loại dữ liệu sang một loại khác: `Box<String>` thành `Box<Integer>`. Tham số kiểu `R` là của method, độc lập với `T` của class.
- `Pair<K,V>` chỉ thể hiện cấu trúc hai giá trị có thể khác kiểu. Khi sử dụng `Pair<String,Long>`, `key()` trả `String`, `value()` trả `Long`.
- `InMemoryRepository<ID,T>` giữ nhất quán **kiểu khóa** và **kiểu entity**. Trong ví dụ, `findById` nhận `String` và trả `Optional<User>`; không cần ép kiểu từ `Object`.
- `User::id` là method reference dùng làm hàm trích khóa `Function<User,String>`. Repository không cần biết field `id` được lưu như thế nào trong từng loại entity.

**Phạm vi của ví dụ:** `InMemoryRepository` chỉ minh họa type safety và khả năng tái sử dụng; nó chưa cung cấp transaction, lưu trữ bền vững, xử lý truy cập đa luồng hoặc kiểm soát trùng khóa. Không nên dùng trực tiếp như repository production trong ứng dụng nhiều luồng.

## 4. Lớp có nhiều tham số kiểu và đặt ràng buộc ở đâu

Một class tổng quát có thể định nghĩa nhiều tham số kiểu:

~~~java
interface Repository<ID, ENTITY> {
    void save(ENTITY entity);
    Optional<ENTITY> findById(ID id);
}
~~~

Ví dụ các kiểu sử dụng khác nhau:

~~~java
Repository<Long, Product> products;
Repository<String, Customer> customers;
~~~

`Product` và `Customer` ở đây là các kiểu nghiệp vụ minh họa, cần được định nghĩa trong dự án. Mỗi cách kết hợp tạo một **parameterized type ở phía mã nguồn**: không phải một class bytecode riêng cho từng tổ hợp.

Nên dùng bao nhiêu tham số kiểu? Chỉ thêm tham số khi **client cần kiểm soát và kiểm tra kiểu tương ứng**. Nếu một generic class có năm, sáu tham số làm chữ ký khó đọc, cân nhắc chia vai trò, dùng type alias ở lớp trừu tượng riêng (Java không có cú pháp type alias tổng quát như một số ngôn ngữ khác) hoặc gói nhiều thuộc tính vào một domain type.

### 4.1. Khi thuật toán cần giới hạn `T`

Một `Box<T>` chỉ lưu/trả dữ liệu thì không cần biết `T` hỗ trợ những hành vi nào. Ngược lại, muốn gọi `doubleValue()` phải ghi `<T extends Number>`; muốn `compareTo` thì dùng bound như sau:

~~~java
static <T extends Comparable<? super T>> T greater(T a, T b) {
    return a.compareTo(b) >= 0 ? a : b;
}
~~~

`extends` trong khai báo generic chấp nhận **cả class và interface**. Nhiều bound dùng `&` (class nếu có phải đầu tiên): `<T extends Number & Comparable<? super T>>`. Java không có cú pháp `<T super Number>`; lower-bound chỉ có ở wildcard `? super Number`.

Bound bảo đảm API khả dụng tại compile time, **không** xác minh giá trị nghiệp vụ, null hay quan hệ thứ tự hợp lệ. Bài **Ràng buộc tham số kiểu** phát triển riêng `NumberBox`, `Comparable<? super T>`, intersection/recursive bounds, phép thử và các giới hạn erasure.

### 4.2. Generic method khác generic class

Không cần cả class tổng quát khi chỉ có **một phương thức** làm việc với nhiều kiểu:

~~~java
import java.util.List;
import java.util.NoSuchElementException;

final class Lists {
    private Lists() {}

    // <T> xuất hiện TRƯỚC kiểu trả về T.
    static <T> T first(List<T> items) {
        if (items.isEmpty()) {
            throw new NoSuchElementException("empty list");
        }
        return items.get(0);
    }
}

// Trong method khác:
String title = Lists.first(List.of("Java", "OOP"));
Integer number = Lists.first(List.of(10, 20));
~~~

Cả hai lời gọi dùng **cùng một phương thức**; trình biên dịch suy luận `T = String` hoặc `T = Integer` dựa vào đối số và ngữ cảnh. Có thể chỉ rõ đối số kiểu:

~~~java
String title = Lists.<String>first(List.of("Java", "OOP"));
~~~

Cách viết tường minh ít cần thiết khi type inference đã đủ. Nếu trong dự án đã có biến `title` từ đoạn trước, hãy đặt ví dụ này trong method riêng để tránh khai báo trùng biến cục bộ.

## 5. Type inference: trình biên dịch suy luận được bao nhiêu?

Java hỗ trợ suy luận đối số kiểu trong nhiều trường hợp:

~~~java
Box<String> box = new Box<>("Hello");  // Diamond operator
var another = new Box<>("World");      // Suy ra Box<String> trong JDK 10+
Pair<String, Integer> pair = new Pair<>("SKU-7", 3);
~~~

**Suy luận không phải dynamic typing**: `var another` vẫn có một kiểu tĩnh xác định tại compile time, là `Box<String>`. Gọi `another.set(100)` vẫn là lỗi biên dịch.

Một tình huống cần cẩn trọng khi constructor generic tự suy luận kiểu theo biểu thức khởi tạo và không có target type:

~~~java
var emptyStrings = new java.util.ArrayList<String>();
emptyStrings.add("A");

// var unknown = new java.util.ArrayList<>();
// Nếu không có thông tin ràng buộc, phần tử thường được suy ra
// kiểu Object; không thể tự kỳ vọng là String.
~~~

Khi API yêu cầu rõ kiểu phần tử, hãy khai báo `List<String> names = new ArrayList<>();` hoặc dùng constructor có type arguments tường minh. Đọc generic signature của method trước khi “sửa” bằng cast.

## 6. Invariance: vì sao Box<Integer> không phải Box<Number>?

`Integer extends Number` là quan hệ subtype hợp lệ. Nhưng với generic type thông thường, Java **không tự suy ra** `Box<Integer> extends Box<Number>`. Tương tự, `List<Integer>` không phải subtype của `List<Number>`.

~~~java
Box<Integer> ints = new Box<>(10);

// Box<Number> numbers = ints; // KHÔNG biên dịch.
~~~

Nếu điều này được phép, client có thể đưa `Double` vào hộp được tạo để chỉ chứa `Integer`:

~~~java
// Giả sử giả định sai: Box<Number> numbers = ints;
numbers.set(3.14);             // 3.14 là Double hợp lệ cho Number
Integer x = ints.get();        // Nhưng ints lẽ ra chỉ chứa Integer!
~~~

Vì vậy, với các generic type như `Box<T>` và `List<T>`, type arguments mặc định **invariant**. Đừng giải quyết lỗi bằng raw type hoặc ép kiểu không kiểm tra. Hãy xem API có cần wildcard hay một abstraction khác không.

So sánh với array: Java array có **covariance**, nhưng có thể phát hiện lỗi ghi kiểu ở runtime:

~~~java
Number[] nums = new Integer[1];
nums[0] = 3.14; // ArrayStoreException lúc chạy.
~~~

Generic invariance tránh một nhóm lỗi kiểu ngay ở compile time. Đây là một khác biệt quan trọng khi chuyển API array sang generic collection.

## 7. Wildcard để nhận nhiều kiểu collection an toàn

Generic thông thường **bất biến**: `List<Integer>` không gán cho `List<Number>`. Wildcard diễn đạt nơi sử dụng cần **đọc** hoặc **ghi** giá trị mà vẫn giữ kiểm tra kiểu:

| Chữ ký | Lời hứa của compiler | Phép thêm phần tử |
| --- | --- | --- |
| `List<?>` | Đọc được dưới `Object` | Chỉ `null` hợp lệ về kiểu |
| `List<? extends Number>` | Đọc được dưới `Number` | Không thêm `Integer`/`Double` tùy ý |
| `List<? super Integer>` | Thêm `Integer` an toàn; đọc dưới `Object` | Được thêm `Integer` |
| `List<Number>` | Đọc/ghi theo kiểu `Number` chính xác | Được thêm subtype của `Number` |

~~~java
static double sum(List<? extends Number> source) {
    double total = 0;
    for (Number n : source) total += n.doubleValue();
    return total;
}

static <T> void copyAll(
        List<? extends T> source, List<? super T> destination) {
    for (T item : source) destination.add(item);
}
~~~

`sum(List.of(1, 2, 3))` biên dịch dù nguồn là `List<Integer>`; `copyAll` có thể đưa dữ liệu từ `List<Integer>` vào `List<Number>`. **PECS** (Producer Extends, Consumer Super) mô tả vai trò nguồn/đích trong phương thức, không làm collection immutable. Những collection `List.of` vẫn từ chối `add` tại runtime dù chữ ký cho phép.

Wildcard khác `<T>`: đặt tên `T` khi cần ràng buộc các vị trí input/output cùng kiểu. Bài **Quan hệ kiểu của các cấu trúc tổng quát** là nơi dạy chính invariance, wildcard capture, PECS và generic inheritance với bảng compile/error và test đầy đủ.

## 8. Erasure: compiler biết `T`, runtime không có class riêng cho từng đối số kiểu

Với Java generics, compiler kiểm tra `List<String>` và `List<Integer>` theo type argument, nhưng hai `ArrayList` vẫn là cùng một runtime class:

~~~java
var texts = new java.util.ArrayList<String>();
var ints = new java.util.ArrayList<Integer>();
System.out.println(texts.getClass() == ints.getClass()); // true
~~~

Sau **type erasure**, `T` không bound thường được thay bằng `Object`; nếu có bound thì thường bị erase thành bound trái nhất, ví dụ `T extends Number` thành `Number`. Compiler có thể thêm cast/bridge methods để giữ hành vi đã kiểm tra.

| Không hợp lệ trực tiếp | Lý do |
|---|---|
| `new T()`, `T.class`, `new T[10]` | Runtime không biết kiểu cụ thể của `T` |
| `obj instanceof List<String>` | `List<String>` không phải kiểu reifiable để kiểm tra type argument |
| `static T shared` trong `class Box<T>` | Thành viên static không thuộc một biến thể `Box<String>` riêng |
| Overload `f(List<String>)` và `f(List<Integer>)` | Hai chữ ký trùng nhau sau erasure |
| `class CustomError<T> extends Exception` | Subclass của `Throwable` không được generic |

Khi cần tạo `T`, truyền `Supplier<? extends T>`; khi cần kiểm tra class lúc chạy, truyền `Class<T>` và dùng `isInstance/cast`. Reflection có thể nhìn thấy **generic signature trong khai báo**, nhưng không biến `ArrayList<String>` thành runtime class khác `ArrayList<Integer>`.

Raw type và unchecked cast ở mục kế tiếp có thể phá tính an toàn compiler đã bảo đảm.

## 9. Raw type, unchecked warning và heap pollution

**Raw type** bỏ toàn bộ type arguments: `List` thay vì `List<String>`, `Box` thay vì `Box<User>`. Nó thường tồn tại vì mã Java cũ hoặc API không generic; dùng raw type trong code mới làm mất nhiều kiểm tra kiểu quan trọng.

~~~java
import java.util.ArrayList;
import java.util.List;

List<String> names = new ArrayList<>();
List raw = names;        // Cùng object, nhìn qua kiểu raw.
raw.add(123);           // Cảnh báo unchecked nhưng có thể biên dịch.
String name = names.get(1);
// ClassCastException khi đọc: Integer đã được thêm ở chỉ số 1.
~~~

Hiện tượng biến/collection được khai báo với parameterized type nhưng thực tế chứa giá trị không tương thích gọi là **heap pollution**. Khi Java báo `unchecked assignment`, `unchecked call` hoặc `unchecked cast`, đừng chỉ tắt cảnh báo. Hãy lần theo boundary với raw type và chuyển đổi về kiểu có kiểm chứng.

Nếu phải giao tiếp với API legacy trả `List<?>`, có thể đọc từng phần tử, dùng `instanceof String` để kiểm tra rồi chép sang `List<String>` mới; đó là kiểm tra runtime có ý nghĩa. Một cast `(List<String>) raw` đơn thuần không xác minh được từng phần tử.

Sự khác biệt này rất quan trọng trong API công khai: **type safety nhờ generics chỉ có thể đáng tin khi không vô tình vượt qua ranh giới bằng unchecked cast hoặc raw type**.

## 10. Thiết kế generic class: nên tổng quát đến đâu?

Generics có giá trị khi nhiều kiểu dữ liệu chia sẻ cùng **cấu trúc và quy tắc xử lý**, trong khi type argument làm rõ các mối quan hệ cần thiết. Không nên tổng quát hóa mọi domain class chỉ vì có thể viết `<T>`.

### Trường hợp phù hợp

- `Box<T>`, `Optional<T>`: đóng gói một giá trị hoặc khả năng không có giá trị.
- `Pair<K,V>`, `Map<K,V>`: liên hệ nhiều giá trị có kiểu rõ ràng.
- `Repository<ID,ENTITY>`: quan hệ kiểu khóa/entity lặp lại nhiều nơi.
- `Result<T>`: đóng gói kết quả thành công với kiểu dữ liệu xác định, kèm trạng thái lỗi có hợp đồng rõ.
- Bộ xử lý tập hợp hoặc thuật toán không phụ thuộc kiểu cụ thể, trừ các khả năng được yêu cầu trong bound.

### Trường hợp không nên ép generic

Giả sử domain thực sự chỉ có `BankAccount` với quy tắc nghiệp vụ số tài khoản, trạng thái và số dư. Đổi nó thành `BankAccount<TBalance,TState,TId>` mà không có nhu cầu dùng nhiều kiểu khác nhau có thể làm API khó đọc và che mất khái niệm nghiệp vụ. Hãy ưu tiên những type có ý nghĩa trong domain, rồi dùng generics ở các abstraction thật sự tái sử dụng.

### Một vài quy tắc thiết kế

1. **Lộ đúng type parameter cần thiết** trong API công khai: một method trả `Object` buộc client cast sẽ làm giảm lợi ích của `<T>`.
2. **Ưu tiên collection interface** cho tham số nếu không cần khả năng riêng của `ArrayList`, `HashSet`, v.v.
3. **Giới hạn bound vừa đủ**; đừng ép `T extends SomeBaseClass` chỉ vì code hiện dùng class đó nếu interface nhỏ hơn đã đáp ứng thuật toán.
4. **Ghi rõ null policy**. `Box<T>` trong demo chủ động từ chối null; trong Java generics, `T` tự thân **không bảo đảm non-null**.
5. **Giữ thông tin kiểu nhất quán** giữa method/constructor: `Repository<ID,T>.findById(ID)` phải trả `Optional<T>`, tránh `Object`/unchecked cast.
6. **Kiểm thử kiểu sai ở compile time** và hành vi đúng ở runtime; đừng chỉ chứng minh rằng class có thể chứa một giá trị.
7. **Không nhầm generic type với đa hình kế thừa**. `List<Integer>` không kế thừa `List<Number>`; wildcard diễn đạt các ràng buộc linh hoạt khi cần.

## 11. Kiểm thử generic class và contract của nó

Kiểm thử generics có hai tầng bổ sung nhau:

- **Compile-time type safety:** Ví dụ `Box<String> box; box.set(1);` phải bị trình biên dịch từ chối. Đây là tính chất của hệ thống kiểu, không phải một exception runtime cần bắt bằng JUnit.
- **Runtime behavior:** Dù generic signature đúng, class vẫn có thể sai logic (trả nhầm giá trị, thay đổi trạng thái, nhận null trái hợp đồng).

Ví dụ JUnit Jupiter 5 cho `Box<T>` và `InMemoryRepository<ID,T>` ở phần 3, đặt tệp `GenericsDemoTest.java` trong source set kiểm thử cùng package:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.NoSuchElementException;
import org.junit.jupiter.api.Test;

class GenericsDemoTest {
    @Test
    void boxPreservesTheDeclaredValueType() {
        Box<String> language = new Box<>("Java");
        assertEquals("Java", language.get());

        language.set("Spring");
        assertEquals("Spring", language.get());

        Box<Integer> length = language.map(String::length);
        assertEquals(6, length.get());
    }

    @Test
    void repositoryUsesConsistentIdAndEntityTypes() {
        InMemoryRepository<String, User> users =
                new InMemoryRepository<>(User::id);

        users.save(new User("U-9", "Mai"));

        assertEquals("Mai",
                users.findById("U-9").orElseThrow().name());
        assertTrue(users.findById("U-unknown").isEmpty());

        assertThrows(NoSuchElementException.class,
                () -> users.findById("U-unknown").orElseThrow());
    }

    @Test
    void boxedNullIsRejectedByThisImplementation() {
        assertThrows(NullPointerException.class,
                () -> new Box<String>(null));
    }
}
~~~

Đoạn test yêu cầu dependency `org.junit.jupiter:junit-jupiter` và JUnit runner tương thích. Các test ở đây xác minh logic và null contract của implementation cụ thể; **không cần** tạo test runtime cho từng đối số kiểu `T` nếu thuật toán là một và trình biên dịch đã kiểm tra quan hệ kiểu.

Đối với thư viện generic phức tạp, nên có test với nhiều nhóm type khác nhau, ví dụ `String`, `Integer`, record/domain object, và các ràng buộc nâng cao để phát hiện những giả định bất hợp lý trong thuật toán.

## 12. Những câu hỏi thường gặp

**Q1. `List<String>` có phải class riêng kế thừa `List`?**  
Không. `List<String>` là **parameterized type** từ generic interface `List<E>`. Nó chỉ định type argument ở compile time; không có một bản copy runtime class riêng theo từng `String`.

**Q2. Vì sao `Box<int>` không dùng được nhưng `Box<Integer>` được?**  
Generic type arguments trong Java phải là reference types. Boxing/unboxing cho phép chuyển đổi giữa `int` và `Integer` trong nhiều biểu thức, nhưng không biến primitive thành type argument hợp lệ.

**Q3. Một lớp có tham số kiểu bắt buộc phải là abstract class hoặc interface?**  
Không. `class Box<T>` có thể là concrete class như ví dụ. `record Pair<K,V>` và `interface Repository<ID,T>` cũng được phép có tham số kiểu.

**Q4. Generics có giúp thay thế kế thừa/đa hình không?**  
Không hoàn toàn. Kế thừa/interface polymorphism mô tả **hợp đồng hành vi**, trong khi generics mô tả **quan hệ giữa các kiểu ở API** và tái sử dụng thuật toán/cấu trúc cho nhiều type arguments. Chúng có thể kết hợp.

**Q5. `T extends Number` có cho phép mọi class tự định nghĩa phép toán `+` không?**  
Không. Java không định nghĩa toán tử cộng generic cho `Number`. Để thao tác số chính xác, cần giao diện tính toán riêng, strategy hoặc API cụ thể phù hợp; `doubleValue()` có thể mất độ chính xác.

**Q6. Khi nào dùng `<?>` thay `<T>`?**  
Khi không cần đặt tên và liên hệ kiểu giữa nhiều vị trí, dùng wildcard sẽ biểu đạt API gọn hơn. Khi cần cùng một type parameter xuất hiện trong cả input/output, `<T>` thường có ý nghĩa hơn.

## 13. Bài tập thực hành: viết Cache<K,V> an toàn kiểu

Hãy cài đặt một lớp:

~~~java
public final class Cache<K, V> {
    // TODO:
    // 1. private final Map<K, V> entries;
    // 2. public void put(K key, V value);
    // 3. public Optional<V> get(K key);
    // 4. public boolean containsKey(K key);
    // 5. public int size();
}
~~~

Yêu cầu:

1. Từ chối key null và value null theo chính sách bạn chọn, ghi rõ bằng JavaDoc.
2. Tạo `Cache<String,User>`, lưu `User("U-01", "Lan")` và đọc lại đúng kiểu `Optional<User>`.
3. Tạo `Cache<Long,String>` bằng cùng class, với ID kiểu `Long`.
4. Thử `cache.put(123L, user)` khi cache là `Cache<String,User>` để tự quan sát lỗi biên dịch.
5. Nếu muốn copy dữ liệu giữa các collection, viết helper `<T> void copyAll(List<? extends T>, List<? super T>)` và giải thích PECS.
6. Thử đặt một field `static V lastValue` trong `Cache<K,V>` rồi giải thích vì sao Java từ chối.
7. Nếu cần cache có TTL, đa luồng và eviction, hãy xác định **những yêu cầu runtime bổ sung** thay vì giả định generic signature giải quyết được.

### Tự kiểm tra sau bài học

- `<T>` được khai báo ở đâu? Khác biệt giữa `class Box<T>` và `static <T> T identity(T value)`?
- Vì sao `List<Integer>` không gán trực tiếp cho `List<Number>` dù `Integer extends Number`?
- Khi cần đọc số từ nhiều subtype, `List<? extends Number>` có lợi gì?
- Vì sao không thể dùng `new T()` trong generic class, và `Supplier<? extends T>` giải quyết vấn đề như thế nào?
- Raw type và unchecked cast có thể làm chương trình gặp lỗi gì ở runtime?
- Type erasure ảnh hưởng thế nào tới `instanceof`, overload method và việc tạo array generic?

**Ghi nhớ:** Generics giúp viết **một cấu trúc hoặc thuật toán có thể sử dụng với nhiều kiểu mà vẫn kiểm tra được quan hệ kiểu tại compile time**. Khi thiết kế lớp có tham số kiểu, hãy nghĩ tới hợp đồng API, tính bất biến/biến thiên, wildcard phù hợp và ranh giới type erasure, thay vì chỉ thêm ký hiệu `<T>`.