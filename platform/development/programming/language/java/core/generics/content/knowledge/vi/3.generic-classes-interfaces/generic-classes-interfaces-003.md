# Thiết kế lớp nhiều tham số kiểu với `Pair<K, V>` trong Java Generics

Một lớp generic không bị giới hạn ở một tham số kiểu `T`. Khi một đối tượng cần lưu hoặc phối hợp **hai giá trị có thể thuộc hai kiểu khác nhau**, ta có thể khai báo `class Pair<K, V>`. Ký hiệu `K` thường gợi *key* (khóa), `V` gợi *value* (giá trị). Hai kiểu được lựa chọn độc lập khi sử dụng lớp; từ đó trình biên dịch kiểm tra kiểu của từng thành phần mà không cần ép kiểu thủ công.

Bài học này đi từ cú pháp `<K, V>`, cách thiết kế lớp `Pair`, khởi tạo và suy luận kiểu, đến factory method, thao tác biến đổi, tính bất biến, hợp đồng `equals()/hashCode()` và quyết định khi nào nên dùng một kiểu cặp tổng quát.

## 1. Vì sao cần hai tham số kiểu?

Một hộp `Box<T>` chứa một giá trị thuộc kiểu `T`; còn một cặp `Pair<K, V>` mô tả **hai vị trí có vai trò và kiểu tách biệt**:

```java
class Pair<K, V> {
    private final K key;
    private final V value;

    Pair(K key, V value) {
        this.key = key;
        this.value = value;
    }

    K key() {
        return key;
    }

    V value() {
        return value;
    }
}
```

Đây là **một định nghĩa lớp minh họa** (chưa có `main`). Trong phần khai báo:

- `<K, V>` khai báo **hai tham số kiểu** thuộc lớp `Pair`, có thể xuất hiện ở trường, constructor và phương thức instance của lớp.
- `K key` biểu thị thành phần đầu mang kiểu `K`; `V value` biểu thị thành phần sau mang kiểu `V`.
- Khi viết `Pair<String, Integer>`, ta thay `K = String` và `V = Integer`; vì vậy `key()` có kiểu tĩnh `String`, còn `value()` có kiểu tĩnh `Integer`.
- Với `Pair<Long, Long>`, hai đối số kiểu giống nhau cũng hợp lệ. Có **hai tham số kiểu** không có nghĩa hai kiểu bắt buộc phải khác nhau.
- Tên `K` và `V` là quy ước. Nếu cặp chỉ biểu diễn “trái/phải” mà không có vai trò khóa–giá trị, `Pair<L, R>` hoặc tên có nghĩa rõ hơn có thể phù hợp.

Nếu dùng `Pair<Object, Object>` để lưu tùy ý, người đọc phải cast khi muốn dùng phương thức đặc thù của từng kiểu; sai kiểu có thể chỉ lộ ra lúc chạy. Nếu dùng `Pair<String, Integer>`, trình biên dịch đã biết kiểu của từng thành phần và phát hiện nhiều lỗi trước khi thực thi.

## 2. Cú pháp khai báo và sử dụng `Pair<K, V>`

Với ví dụ `Pair` ở trên, cú pháp khởi tạo gồm kiểu thực tế cho cả hai tham số:

```java
Pair<String, Integer> age = new Pair<>("Ada", 36);
Pair<Integer, String> code = new Pair<>(404, "Not Found");
Pair<String, String> labels = new Pair<>("vi", "Xin chào");
```

Các dòng trên cần đặt trong một phương thức hoặc vùng khai báo hợp lệ có thể nhìn thấy lớp `Pair`. Đây là **ba lần dùng cùng một định nghĩa lớp**, không tạo ba lớp nguồn khác nhau.

- **Thứ tự quan trọng:** `Pair<String, Integer>` khác `Pair<Integer, String>`. Đổi chỗ đối số kiểu đồng nghĩa đổi vai trò của các phương thức trả về.
- **Diamond operator `<>`:** tại `new Pair<>("Ada", 36)`, trình biên dịch suy luận `K`, `V` dựa vào kiểu đích và biểu thức đối số. Có thể viết đầy đủ `new Pair<String, Integer>("Ada", 36)` nhưng thường dài dòng.
- **Wrapper cho primitive:** `Integer` là kiểu tham chiếu, phù hợp với type argument. `36` là literal `int` và được boxing thành `Integer` khi cần. `Pair<String, int>` không hợp lệ trong Java 17.
- **Hai kiểu có quan hệ độc lập:** khai báo `Pair<String, Integer>` không nói rằng `String` phải kế thừa `Integer` hoặc ngược lại.
- **Dùng đúng kiểu trả về:** `String name = age.key(); Integer years = age.value();` hợp lệ; `String years = age.value();` không biên dịch.

Java generics thông thường dùng **type erasure**, nên `Pair<String, Integer>` và `Pair<Integer, String>` có cùng lớp `Pair` tại runtime; bộ tham số kiểu chủ yếu phục vụ kiểm tra kiểu ở compile time. Đừng dùng `instanceof Pair<String, Integer>` để thử kiểu cụ thể, vì phép thử kiểu tham số hóa đó không hợp lệ.

## 3. Bản thiết kế khuyến nghị: bất biến và API nhỏ

Một `Pair` có thể được viết theo kiểu mutable với setter, nhưng khi nó biểu diễn một giá trị kết hợp, thiết kế **immutable** thường dễ dự đoán và dễ dùng làm kết quả hoặc khóa:

1. `final class` ngăn lớp con thay đổi hợp đồng bằng override.
2. Các trường `private final` không cho gán lại tham chiếu sau khi xây dựng.
3. Không công khai setter.
4. Constructor thiết lập đầy đủ cả hai thành phần.
5. Accessor `key()`, `value()` trả đúng kiểu generic đã khai báo.
6. `equals` và `hashCode` so sánh hai thành phần theo giá trị và nhất quán với nhau.
7. `toString` giúp debug và log; tránh phụ thuộc vào format chuỗi như giao thức trao đổi dữ liệu lâu dài.

**Bất biến ở đây là bất biến nông (shallow immutability).** Nếu `V` là một `ArrayList<String>` có thể sửa, việc `Pair` giữ trường `final` không ngăn người gọi sửa nội dung danh sách đó. Nếu API cần bất biến sâu hơn, hãy giới hạn kiểu thành phần, tạo bản sao phòng vệ hoặc dùng đối tượng thành phần immutable phù hợp.

Cho phép `null` hay không là **quyết định thiết kế**, không phải quy tắc của `Pair<K, V>`. `new Pair<>(null, 3)` có thể hợp lệ nếu constructor không kiểm tra. Nếu nghiệp vụ yêu cầu cả hai thành phần không-null, dùng `Objects.requireNonNull(key, "key")` và `Objects.requireNonNull(value, "value")` trong constructor; mô tả rõ hợp đồng đó trong API.

## 4. Ví dụ Java 17 chạy độc lập: `Pair<K, V>` đầy đủ

Lưu toàn bộ chương trình sau vào tệp **`PairDemo.java`** (Java 17+):

```java
import java.util.List;
import java.util.Objects;
import java.util.function.Function;

public class PairDemo {
    public static final class Pair<K, V> {
        private final K key;
        private final V value;

        private Pair(K key, V value) {
            this.key = key;
            this.value = value;
        }

        public static <K, V> Pair<K, V> of(K key, V value) {
            return new Pair<>(key, value);
        }

        public K key() {
            return key;
        }

        public V value() {
            return value;
        }

        public Pair<V, K> swapped() {
            return Pair.of(value, key);
        }

        public <NEW_VALUE> Pair<K, NEW_VALUE> mapValue(
                Function<? super V, ? extends NEW_VALUE> mapper) {
            Objects.requireNonNull(mapper, "mapper");
            return Pair.of(key, mapper.apply(value));
        }

        @Override
        public boolean equals(Object object) {
            if (this == object) {
                return true;
            }
            if (!(object instanceof Pair<?, ?> other)) {
                return false;
            }
            return Objects.equals(key, other.key)
                    && Objects.equals(value, other.value);
        }

        @Override
        public int hashCode() {
            return Objects.hash(key, value);
        }

        @Override
        public String toString() {
            return "(" + key + ", " + value + ")";
        }
    }

    public static void main(String[] args) {
        Pair<String, Integer> person = Pair.of("Ada", 36);
        Pair<Integer, String> reversed = person.swapped();
        Pair<String, String> ageText =
                person.mapValue(age -> age + " years");
        Pair<String, Integer> same = Pair.of("Ada", 36);
        Pair<String, Integer> different = Pair.of("Ada", 37);
        Pair<String, List<Integer>> scores =
                Pair.of("scores", List.of(2, 4, 6));

        System.out.println("person: " + person);
        System.out.println("key upper: " + person.key().toUpperCase());
        System.out.println("next age: " + (person.value() + 1));
        System.out.println("swapped: " + reversed);
        System.out.println("mapped: " + ageText);
        System.out.println("equal: " + person.equals(same));
        System.out.println("different: " + person.equals(different));
        System.out.println("nested: " + scores);
        System.out.println("same type: " + Pair.of(1, 2));
    }
}
```

Biên dịch và chạy trong thư mục chứa tệp:

```bash
javac PairDemo.java
java PairDemo
```

**Stdout dự kiến:**

```text
person: (Ada, 36)
key upper: ADA
next age: 37
swapped: (36, Ada)
mapped: (Ada, 36 years)
equal: true
different: false
nested: (scores, [2, 4, 6])
same type: (1, 2)
```

Giải thích kết quả theo từng cơ chế:

- `Pair.of("Ada", 36)` là **generic static factory method**. Trình biên dịch suy luận `K = String`, `V = Integer` (boxing `36` khi cần). Giá trị nhận được có kiểu `Pair<String, Integer>`.
- `person.key().toUpperCase()` hợp lệ vì `key()` có kiểu `String`. `person.value() + 1` unbox `Integer` thành `int` để cộng ra `37`.
- `swapped()` có kiểu trả về `Pair<V, K>`, tức `Pair<Integer, String>` trong trường hợp này. **Hoán đổi giá trị đi cùng hoán đổi vị trí tham số kiểu**; giữ `Pair<K, V>` ở kiểu trả về sẽ sai.
- `mapValue(...)` giữ nguyên `K` nhưng cho phép đổi `V` sang một kiểu mới `NEW_VALUE`. Lambda biến `36` thành `"36 years"`, nên kết quả là `Pair<String, String>`.
- `equals` kiểm tra nội dung cả hai thành phần, vì thế `person` bằng `same` nhưng khác `different`. `hashCode` nhất quán với `equals`; chương trình không in giá trị hash cụ thể vì không cần phụ thuộc cách biểu diễn đó.
- `Pair<String, List<Integer>>` minh họa **kiểu generic lồng nhau**: `K` là `String`, `V` là `List<Integer>`. Chương trình dùng `List.of(...)` vốn trả một danh sách không cho thay đổi phần tử bằng các lệnh sửa; nhưng bản thân kiểu `Pair` không đòi `V` phải là list immutable.
- `Pair.of(1, 2)` hợp lệ khi `K` và `V` cùng được suy luận là `Integer`. Hai vị trí vẫn độc lập về vai trò dù trùng kiểu.

Đoạn `if (!(object instanceof Pair<?, ?> other))` dùng *pattern matching for instanceof* có trong Java 17. `Pair<?, ?>` chỉ kiểm tra đối tượng thuộc `Pair` mà không giả định đối số kiểu runtime cụ thể. Việc so sánh từng thành phần bằng `Objects.equals` phù hợp khi thành phần có thể `null` và tránh ép kiểu không an toàn.

## 5. Static factory và giới hạn kiểu của thành viên `static`

Một factory như `Pair.of(...)` giúp khởi tạo gọn hơn mà vẫn giữ được kiểu ở cả hai vị trí. Chữ ký:

```java
public static <K, V> Pair<K, V> of(K key, V value) {
    return new Pair<>(key, value);
}
```

Đây là phương thức **trong lớp `Pair<K, V>`** của ví dụ đầy đủ, không phải một hàm Java tự do.

Cặp `<K, V>` sau `static` **khai báo hai tham số kiểu riêng của phương thức**. Nó không sử dụng trực tiếp `K`, `V` của instance `Pair<K, V>`, vì static method thuộc về lớp chứ không thuộc một đối tượng được tham số hóa. Việc phương thức đặt tên giống tham số lớp được phép; phạm vi khai báo là khác nhau. Nếu muốn tránh nhầm khi đọc, có thể khai báo factory là `static <A, B> Pair<A, B> of(A a, B b)`; ý nghĩa không đổi.

Mẫu sai về phạm vi (không biên dịch khi đặt trong `class Pair<K, V>`):

```java
// static Pair<K, V> create(K key, V value) { ... }
// Sai vì static không được dùng trực tiếp type parameters của lớp.
```

Mẫu đúng có phần khai báo type parameter của phương thức: `static <K, V> Pair<K, V> create(K key, V value)`.

Cú pháp gọi có thể viết tường minh bằng type witness `Pair.<String, Integer>of("Ada", 36)`, nhưng trong phần lớn tình huống `Pair.of("Ada", 36)` đã đủ để trình biên dịch suy luận. Một lưu ý quan trọng: **type inference phụ thuộc ngữ cảnh**. Nếu dùng `var pair = Pair.of("Ada", 36)`, kiểu được suy luận theo các biểu thức đối số; nếu cần hợp đồng rộng hơn (ví dụ `Pair<CharSequence, Number>`), hãy khai báo kiểu đích tường minh hoặc gọi factory với type witness phù hợp. Không phải mọi tình huống compiler đều tự đoán đúng dụng ý API.

## 6. Thao tác hai thành phần mà vẫn bảo toàn kiểu

Lợi ích lớn của nhiều tham số kiểu là **phương thức có thể thay đổi một thành phần mà giữ nguyên thành phần khác**:

| Phương thức | Kiểu trả về | Ý nghĩa |
|---|---|---|
| `K key()` | `K` | Đọc thành phần thứ nhất đúng kiểu |
| `V value()` | `V` | Đọc thành phần thứ hai đúng kiểu |
| `Pair<V, K> swapped()` | `Pair<V, K>` | Hoán đổi hai thành phần và hai tham số kiểu |
| `<R> Pair<K, R> mapValue(Function<? super V, ? extends R> f)` | `Pair<K, R>` | Giữ `K`, biến đổi riêng `V` |
| `<R> Pair<R, V> mapKey(Function<? super K, ? extends R> f)` | `Pair<R, V>` | Giữ `V`, biến đổi riêng `K` |

`mapKey` là **gợi ý thiết kế tương tự**, không nằm trong chương trình `PairDemo`. Nếu bổ sung vào thân lớp `Pair`, có thể cài đặt:

```java
public <NEW_KEY> Pair<NEW_KEY, V> mapKey(
        Function<? super K, ? extends NEW_KEY> mapper) {
    Objects.requireNonNull(mapper, "mapper");
    return Pair.of(mapper.apply(key), value);
}
```

Đoạn trên dùng `Function` và `Objects` đã import trong ví dụ đầy đủ, và **cần nằm bên trong lớp `Pair<K, V>`**. Với `Pair<String, Integer> p`, lời gọi `p.mapKey(String::length)` có kiểu `Pair<Integer, Integer>`.

Tại sao `Function<? super V, ? extends R>` thay vì chỉ `Function<V, R>`? Wildcard giúp chấp nhận rộng hơn: phép biến đổi có thể tiêu thụ một **supertype của `V`** và tạo một **subtype của `R`**. Mẫu “đầu vào `? super`, đầu ra `? extends`” hữu ích cho API nhận function. Nếu mới học, có thể bắt đầu bằng `Function<V, R>` rồi mở rộng khi đã hiểu PECS.

Cách viết phương thức phải làm đúng điều được thể hiện bởi kiểu trả về. Ví dụ sau là **lỗi thiết kế**:

```java
// Trong class Pair<K, V>:
// Pair<K, V> swapped() { return Pair.of(value, key); }
// Sai về nguyên tắc tổng quát: Pair.of(value, key) có cặp vai trò V, K.
```

Có thể tình cờ chấp nhận khi `K` và `V` giống nhau, nhưng khai báo `Pair<K, V>` không đúng cho mọi cách tham số hóa. Chữ ký chính xác là `Pair<V, K> swapped()`.

## 7. Kiểm tra `equals`, `hashCode`, `toString` cho Pair

Khi hai đối tượng `Pair` dùng như các **giá trị**, phép so sánh thường cần quan tâm đến **cả key và value**. Ví dụ `Pair.of("A", 1)` nên bằng một `Pair.of("A", 1)` khác nếu chúng có cùng ngữ nghĩa giá trị.

- `equals(Object)` kiểm tra đối tượng cùng loại cặp và dùng `Objects.equals` trên từng thành phần. `Objects.equals(x,y)` cho kết quả hợp lý nếu một hay cả hai thành phần `null`, đồng thời dựa vào `equals` của từng thành phần.
- `hashCode()` phải thỏa: nếu `a.equals(b)` thì `a.hashCode() == b.hashCode()`. `Objects.hash(key, value)` là một cách cài đặt; không nhất thiết mọi hash khác nhau đều chỉ ra đối tượng khác nhau.
- `toString()` nên biểu diễn dễ đọc hai phần tử; `(Ada, 36)` trong ví dụ là **format tự chọn**, không phải quy tắc bắt buộc của Java.

**Không nên chỉ kiểm tra `key` trong `equals`** nếu cặp được mô tả là hai thành phần có giá trị: khi đó `Pair.of("A", 1)` và `Pair.of("A", 2)` sẽ bị coi như bằng nhau dù khác nội dung. Trường hợp miền nghiệp vụ chỉ định danh bằng một trường nên dùng lớp/record domain có hợp đồng equality được đặt tên rõ ràng.

Nếu thành phần là mảng (ví dụ `Pair<String, int[]>`), `Objects.equals` với mảng sử dụng ngữ nghĩa `equals` của mảng (không so sánh từng phần tử như `Arrays.equals`). Nếu cần **deep equality** hoặc so sánh mảng theo nội dung, phải thiết kế riêng cho loại giá trị đó. Vì thế một generic Pair không thể tự biết mọi quy tắc so sánh đặc thù miền dữ liệu.

Mẫu immutable giúp giữ `hashCode` ổn định hơn khi thành phần cũng immutable. Nếu `V` là một danh sách mutable hoặc đối tượng có `equals/hashCode` thay đổi theo trạng thái, việc dùng `Pair` làm khóa `HashMap` vẫn có thể gây lỗi tra cứu sau khi sửa thành phần. `final` trên trường không giải quyết tính mutable bên trong.

## 8. Giới hạn generic: bất biến kiểu và wildcard

Java không cho suy ra `Pair<CharSequence, Number>` từ `Pair<String, Integer>` dù `String` thực hiện `CharSequence` và `Integer` là subtype của `Number`.

Ví dụ **không biên dịch**:

```java
Pair<String, Integer> exact = Pair.of("A", 1);
// Pair<CharSequence, Number> wider = exact; // Không hợp lệ.
```

Ở đây `Pair` là class có hai tham số kiểu **invariant**. Giải pháp phụ thuộc việc muốn làm với cặp:

```java
static void show(
        Pair<? extends CharSequence, ? extends Number> pair) {
    System.out.println(pair.key() + " = " + pair.value());
}
```

Đây là **phương thức minh họa**, cần đặt trong class nhìn thấy `Pair`. Tham số dạng `Pair<? extends CharSequence, ? extends Number>` có thể nhận `Pair<String, Integer>` và đọc qua giao diện kiểu rộng hơn. Trong ví dụ `Pair` bất biến, không có setter; với một Pair mutable, wildcard sẽ còn quyết định những giá trị nào có thể ghi an toàn.

**Không nhầm `Pair<?, ?>` với `Pair<Object, Object>`.** `Pair<?, ?>` chấp nhận một cặp có hai đối số kiểu chưa biết, phù hợp để quan sát như `Object`. `Pair<Object, Object>` là cặp có hai đối số kiểu cụ thể `Object`; hai khai báo không có cùng quan hệ gán.

Bound có thể đặt cho từng tham số khi một loại cặp đặc thù cần ràng buộc, chẳng hạn:

```java
class ScoredPair<K, V extends Number> {
    private final K key;
    private final V score;

    ScoredPair(K key, V score) {
        this.key = key;
        this.score = score;
    }

    double scoreAsDouble() {
        return score.doubleValue();
    }
}
```

Đây là **lớp minh họa riêng**, không nằm trong `PairDemo`. Bound `V extends Number` cho phép truy cập `doubleValue()` và ngăn type argument không thỏa `Number`. Không nên thêm bound chỉ vì tên tham số kiểu là `V`: một `Pair<K, V>` tổng quát có thể cần chứa bất kỳ reference type nào.

## 9. Khi nào dùng Pair, Map.Entry hoặc record?

`Pair<K, V>` phù hợp khi **hai giá trị thật sự được truyền/nhận cùng nhau** nhưng chưa cần thêm hợp đồng nghiệp vụ riêng. Tuy vậy, nó là một cấu trúc tổng quát nên tên `key`/`value` đôi khi làm lu mờ ý nghĩa thực tế, chẳng hạn tọa độ, khoảng thời gian hay thông tin của người dùng.

| Nhu cầu | Lựa chọn có thể phù hợp | Lưu ý |
|---|---|---|
| Cặp giá trị generic nhỏ cần API riêng | `Pair<K, V>` | Dễ kiểm soát hợp đồng bất biến, null, equals và biến đổi |
| Cặp gắn với một entry của map | `Map.Entry<K, V>` | Có ngữ nghĩa khóa–giá trị; `Map.entry(k,v)` tạo entry bất biến và **không chấp nhận null** |
| Chỉ lưu hai thành phần có tên cụ thể trong miền dữ liệu | `record Range(int start, int end)` hoặc record domain | Tên trường `start/end` có nghĩa hơn `key/value` |
| Cặp generic rất đơn giản trên Java 17+ | `record Pair<K, V>(K key, V value)` | Compiler sinh constructor, accessor, `equals`, `hashCode`, `toString`; record là bất biến nông |
| Nhiều trường và quy tắc nghiệp vụ | Lớp/record domain cụ thể | Đặt tên thuộc tính và validation theo đúng nghiệp vụ |

**Record generic** cho phép triển khai ngắn hơn. Ví dụ sau là **một tệp riêng** `Pair.java` và là phương án thay thế cho class `Pair<K, V>` trước đó:

```java
public record Pair<K, V>(K key, V value) {
    public static <K, V> Pair<K, V> of(K key, V value) {
        return new Pair<>(key, value);
    }

    public Pair<V, K> swapped() {
        return new Pair<>(value, key);
    }
}
```

`record` tự sinh accessor `key()`, `value()` và các phương thức giá trị dựa trên thành phần record. Với `Pair.of("A", 1)`, `toString()` do record sinh ra có định dạng kiểu `Pair[key=A, value=1]` (khác với `"(A, 1)"` của `PairDemo`). Không coi hai kiểu `Pair` này có định dạng xuất giống nhau khi thay đổi cách cài đặt.

Dù dùng class hay record, nếu cặp có ý nghĩa đặc thù và nhiều điều kiện bất biến, chẳng hạn `start <= end`, một `Range` với tên thành phần và kiểm tra dữ liệu cụ thể thường truyền đạt hợp đồng tốt hơn `Pair<Integer, Integer>`.

## 10. Cách thiết kế một API Pair dễ dùng

Trước khi đưa `Pair<K, V>` vào một thư viện, nên quyết định nhất quán các điểm sau:

1. **Vai trò:** `K` và `V` có thực sự là key/value không? Nếu là left/right, cân nhắc `Pair<L, R>`; nếu là thuộc tính domain, cân nhắc kiểu domain.
2. **Bất biến:** có cho cập nhật thành phần sau khi tạo không? Với value object, `private final` và không có setter thường phù hợp.
3. **Null:** chấp nhận `null` ở từng vị trí hay ném lỗi sớm bằng `Objects.requireNonNull`? Ghi rõ trong tài liệu API.
4. **Factory và constructor:** `Pair.of` giúp suy luận kiểu gọn; constructor private ngăn khởi tạo ngoài factory. Nếu muốn hỗ trợ `new Pair<>(...)` từ code người gọi, constructor phải có mức truy cập phù hợp.
5. **Equality:** hai thành phần cùng tham gia `equals/hashCode` hay còn có quy tắc domain? Tránh cài đặt nửa vời.
6. **Tính mutable của thành phần:** `final` không làm sâu các object bên trong; ghi rõ giới hạn hoặc dùng bản sao phòng vệ khi cần.
7. **Phép biến đổi:** nếu cho `swapped`, `mapKey`, `mapValue`, kiểu trả về phải biểu đạt chính xác vai trò kiểu trước/sau biến đổi.
8. **Type inference:** để người dùng thường gọi được `Pair.of("A", 1)`; dùng type witness hoặc kiểu đích tường minh ở trường hợp cần mở rộng kiểu.
9. **Không lạm dụng:** khi có ba, bốn thuộc tính hoặc cần các quy tắc nghiệp vụ, một class/record được đặt tên theo domain thường dễ bảo trì hơn các `Pair` lồng nhau.

Một lưu ý riêng về thiết kế thư viện: Java không cung cấp một lớp `Pair<K, V>` đa dụng trực tiếp trong `java.lang`. Tự xây class nhỏ khi có nhu cầu rõ ràng, hoặc dùng kiểu đã có của thư viện đang dùng. Tránh đưa thêm dependency chỉ để lấy một kiểu cặp đơn giản nếu nó không tạo giá trị khác.

## 11. Lỗi phổ biến

**Lỗi 1 — Dùng một type parameter cho cả hai vị trí khi muốn hai kiểu độc lập.**

```java
class SameTypePair<T> {
    T first;
    T second;
}
```

Lớp này buộc hai trường được nhìn qua cùng một `T` ở mỗi cách tham số hóa. Nếu nghiệp vụ muốn một chuỗi và một số với kiểu rõ ràng, `Pair<K, V>` diễn đạt tốt hơn. Một `SameTypePair<Object>` có thể giữ hai object khác kiểu nhưng làm mất thông tin kiểu cụ thể của từng trường.

**Lỗi 2 — Dùng primitive trong type argument:** `Pair<String, int>` không hợp lệ; dùng `Pair<String, Integer>`. Java tự boxing `int` khi cần trong ngữ cảnh khởi tạo hợp lệ.

**Lỗi 3 — Đổi thứ tự `K, V` khi khai báo kết quả:** `Pair<Integer, String>` không gán được sang `Pair<String, Integer>` chỉ vì đều là Pair. Đặc biệt kiểm tra chữ ký các phương thức như `swapped()`.

**Lỗi 4 — Cho rằng `Pair<String, Integer>` là subtype của `Pair<Object, Object>`.** Generic type invariant; dùng wildcard hoặc một kiểu API được thiết kế cho thao tác cần thiết.

**Lỗi 5 — Cố truy cập `K`, `V` của lớp từ static method mà không khai báo riêng.** Static factory phải tự viết `static <K, V> ...` (hoặc tên type parameter riêng khác).

**Lỗi 6 — Viết `equals` chỉ so key hoặc dùng `==` cho wrapper/string.** Nếu cần value equality, so từng thành phần bằng `Objects.equals` và viết `hashCode` nhất quán.

**Lỗi 7 — Tin rằng `final` làm thành phần mutable trở nên bất biến.** `Pair<String, List<Integer>>` có thể chứa một list mutable; người giữ tham chiếu tới list vẫn có thể sửa nó.

**Lỗi 8 — Quên kiểm tra null trong hàm biến đổi.** Nếu `mapper == null`, lời gọi `mapper.apply` ném `NullPointerException`; `Objects.requireNonNull(mapper, "mapper")` làm hợp đồng rõ ràng. Nếu `value` là null, mapper cũng phải xử lý null hoặc API cần cấm null ngay khi tạo.

**Lỗi 9 — Dùng Pair thay lớp domain có nghĩa.** `Pair<Integer, Integer>` không cho người đọc biết đâu là ngày bắt đầu, đâu là ngày kết thúc; kiểu `DateRange` hoặc `Range` thường biểu đạt và kiểm tra dữ liệu tốt hơn.

**Lỗi 10 — Nghĩ type parameter tồn tại nguyên vẹn tại runtime.** Kiểm tra `pair instanceof Pair<?, ?>` hợp lệ nhưng không xác minh từng type argument; không dùng raw Pair và unchecked cast để né kiểm tra biên dịch.

## 12. Bài tập tự kiểm tra có đáp án

1. **`Pair<String, Integer>` có mấy type parameter và mấy type argument?** Định nghĩa `Pair<K, V>` khai báo hai type parameter `K`, `V`; tại cách dùng có hai type argument `String`, `Integer`.
2. **`Pair<Integer, Integer>` có hợp lệ không?** Có. Hai tham số kiểu độc lập không bắt buộc khác kiểu.
3. **`Pair<String, Integer> p = Pair.of("A", 4);` có cần cast khi gọi `p.value()` không?** Không. Compiler biết kiểu trả về `Integer`; gán vào `int` sẽ unbox.
4. **Nếu `p` là `Pair<String, Integer>`, `p.swapped()` thuộc kiểu nào?** `Pair<Integer, String>`. Đảo cả vị trí và quan hệ kiểu.
5. **Tại sao factory viết `static <K, V> Pair<K, V> of(...)`?** Vì static method cần khai báo type parameter riêng, không dùng trực tiếp type parameter ở mức instance của lớp.
6. **`Pair<String, Integer>` có gán cho biến `Pair<CharSequence, Number>` được không?** Không, vì generics invariant; khi chỉ cần đọc có thể nhận bằng `Pair<? extends CharSequence, ? extends Number>`.
7. **`Pair.of("x", 1).equals(Pair.of("x", 1))` trả gì với triển khai ở trên?** `true`, vì cả hai thành phần tương ứng bằng nhau theo `Objects.equals`.
8. **`new Pair<>(...)` có gọi được ngoài class `Pair` trong chương trình đầy đủ không?** Không vì constructor private; dùng `Pair.of(...)`.
9. **`record Pair<K, V>(K key, V value)` có tự động làm `List` bên trong immutable không?** Không; record bất biến nông, các đối tượng thành phần có thể vẫn mutable.
10. **Khi dữ liệu là giá trị “tọa độ x và y”, dùng `Pair<Double, Double>` hay `Point(double x, double y)`?** Cả hai có thể lưu dữ liệu, nhưng `Point` được đặt tên đúng domain, rõ ý nghĩa thành phần và có chỗ diễn đạt validation/hành vi tốt hơn.

Ghi nhớ: **`Pair<K, V>` là một lớp generic duy nhất có hai “ô kiểu” độc lập**. Thiết kế tốt là đặt đúng vai trò `K`/`V`, trả đúng kiểu ở từng accessor, giữ quan hệ kiểu khi hoán đổi hoặc biến đổi, và bảo đảm hợp đồng giá trị rõ ràng. Generics giúp compiler giữ an toàn kiểu; thiết kế API quyết định cặp đó có ý nghĩa và có dễ dùng hay không.
