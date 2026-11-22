# `Collectors.toMap()` với hàm tạo khóa và giá trị trong Java Stream

Trong Java Stream, `Collectors.toMap()` dùng để **thu thập** các phần tử thành một `Map<K,V>`. Điểm quan trọng nhất là hai hàm bạn cung cấp quyết định **mỗi phần tử nguồn trở thành khóa nào và giá trị nào**:

~~~java
Map<K, V> result = stream.collect(
        Collectors.toMap(keyMapper, valueMapper));
~~~

Ở đây, `keyMapper` nhận **một phần tử nguồn** và trả khóa `K`; `valueMapper` cũng nhận **một phần tử nguồn** và trả giá trị `V`. Mỗi phần tử được đưa qua hai hàm để tạo một cặp khóa–giá trị. Bộ thu thập hoàn thành khi terminal operation `collect(...)` chạy.

Chẳng hạn, từ `Stream<Employee>` có thể tạo `Map<Long,String>` bằng mã nhân viên làm khóa và tên nhân viên làm giá trị:

~~~java
Map<Long, String> nameById = employees.stream()
        .collect(Collectors.toMap(Employee::id, Employee::name));
~~~

Hai đoạn đầu là **minh họa trong phương thức** với các biến/kiểu đã khai báo. Những phần tiếp theo có chương trình Java 17+ đầy đủ để biên dịch và chạy.

**Ba quy tắc cần nhớ ngay:**

1. Overload hai hàm **không tự xử lý khóa trùng**: nếu hai phần tử tạo cùng khóa, collector ném `IllegalStateException`.
2. Không dùng `valueMapper` trả `null`: các overload `Collectors.toMap` chuẩn không chấp nhận giá trị map bằng null; có thể ném `NullPointerException`.
3. `toMap(keyMapper, valueMapper)` **không bảo đảm loại Map và thứ tự duyệt**. Nếu cần insertion order, sorted keys hoặc loại map cụ thể, chọn overload có `mapSupplier`.

## 1. Đọc chữ ký: hai hàm tạo khóa và giá trị

Overload cơ bản của `Collectors` có dạng:

~~~java
// Chữ ký API được rút gọn để học, không phải chương trình độc lập.
static <T, K, U> Collector<T, ?, Map<K, U>> toMap(
        Function<? super T, ? extends K> keyMapper,
        Function<? super T, ? extends U> valueMapper);
~~~

Đọc theo kiểu dữ liệu:

~~~text
Stream<T>
   keyMapper:   T → K
   valueMapper: T → U
   collect(toMap(...))
                ↓
             Map<K, U>
~~~

- `T`: kiểu **phần tử nguồn** đang đi qua pipeline.
- `K`: kiểu của **khóa** được tạo từ từng phần tử.
- `U`: kiểu của **giá trị** được tạo từ từng phần tử.
- `Function<T,R>`: functional interface nhận một `T`, trả một `R`.
- `Collectors.toMap(...)`: là một **Collector**; `stream.collect(...)` mới là terminal operation thực thi việc thu thập.

`keyMapper` và `valueMapper` có thể là lambda, method reference, hoặc biểu thức tạo dữ liệu mới. Không cần `K` và `U` cùng kiểu với `T`.

Ví dụ với `T = Employee`, `K = Long`, `U = String`:

~~~java
Collectors.toMap(Employee::id, Employee::name)
~~~

Nếu muốn giữ toàn bộ nhân viên làm giá trị, có thể dùng `Function.identity()`:

~~~java
Collectors.toMap(Employee::id, java.util.function.Function.identity())
~~~

Khi đó kiểu kết quả là `Map<Long,Employee>`. `Function.identity()` trả chính đối tượng đầu vào, **không sao chép đối tượng** và không tạo ra một clone.

## 2. Ví dụ độc lập: tạo khóa và giá trị khác kiểu nguồn

Tạo file `BasicToMapDemo.java`:

~~~java
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

public class BasicToMapDemo {
    record Employee(long id, String name, int score) {}

    public static void main(String[] args) {
        List<Employee> employees = List.of(
                new Employee(3, "Chi", 90),
                new Employee(1, "An", 80),
                new Employee(2, "Bình", 85));

        Map<Long, String> nameById = employees.stream()
                .collect(Collectors.toMap(
                        Employee::id,
                        Employee::name));

        Map<Long, Integer> doubledScoreById = employees.stream()
                .collect(Collectors.toMap(
                        e -> e.id(),
                        e -> e.score() * 2));

        System.out.println("nameById[2]=" + nameById.get(2L));
        System.out.println("size=" + nameById.size());
        System.out.println("doubleScore[1]=" + doubledScoreById.get(1L));
    }
}
~~~

~~~bash
javac --release 17 BasicToMapDemo.java
java BasicToMapDemo
~~~

Kết quả:

~~~text
nameById[2]=Bình
size=3
doubleScore[1]=160
~~~

Giải thích:

1. `employees.stream()` trả `Stream<Employee>`.
2. `Employee::id` lấy `long`, được boxing thành `Long` vì khóa generic của `Map` là kiểu tham chiếu.
3. `Employee::name` trả `String`, nên kết quả đầu là `Map<Long,String>`.
4. `e -> e.score() * 2` trả `int`, được boxing thành `Integer`, nên kết quả thứ hai là `Map<Long,Integer>`.
5. Đọc kết quả qua `get(2L)` và `get(1L)`, thay vì in toàn bộ `Map`, để **không phụ thuộc thứ tự duyệt** của Map do overload hai hàm tạo ra.

Lưu ý `2L` là `Long`; `map.get(2)` boxing `int` thành `Integer`, khác `Long` và thường cho `null` dù đã có khóa `2L`.

## 3. Khóa trùng: vì sao overload hai hàm ném lỗi?

`Map` chỉ có thể có **một giá trị gắn với mỗi khóa**. Nếu hai phần tử nguồn cho ra cùng khóa, overload `toMap(keyMapper,valueMapper)` không thể tự đoán nên chọn giá trị nào.

Ví dụ hai nhân viên cùng có `department = "IT"`:

~~~java
// Minh họa: giả định Employee có phương thức department().
employees.stream()
        .collect(Collectors.toMap(
                Employee::department,
                Employee::name));
~~~

Nếu có ít nhất hai employee với khóa `"IT"`, phép thu thập này ném `IllegalStateException` do khóa trùng. **Ngay cả khi hai giá trị bằng nhau**, overload cơ bản cũng không xem đó là lý do được phép ghi trùng.

Khóa trùng được xác định theo cơ chế tương đương khóa của loại Map được tạo (thường là `equals`/`hashCode`; với `TreeMap`, theo comparator của cây). Không chỉ dựa vào việc cùng một tham chiếu object.

Tạo file `DuplicateKeyToMapDemo.java`:

~~~java
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

public class DuplicateKeyToMapDemo {
    public static void main(String[] args) {
        List<String> names = List.of("Anna", "Adam", "Bình");

        try {
            names.stream().collect(Collectors.toMap(
                    s -> s.substring(0, 1),
                    s -> s));
        } catch (IllegalStateException ex) {
            System.out.println("duplicate=" + ex.getClass().getSimpleName());
        }

        Map<String, String> firstByInitial = names.stream()
                .collect(Collectors.toMap(
                        s -> s.substring(0, 1),
                        s -> s,
                        (first, later) -> first));

        System.out.println("A=" + firstByInitial.get("A"));
        System.out.println("B=" + firstByInitial.get("B"));
    }
}
~~~

~~~bash
javac --release 17 DuplicateKeyToMapDemo.java
java DuplicateKeyToMapDemo
~~~

Kết quả:

~~~text
duplicate=IllegalStateException
A=Anna
B=Bình
~~~

Trong ví dụ, Anna và Adam đều tạo khóa `"A"`; overload hai hàm ném ngoại lệ, còn overload có **merge function** chủ động giữ giá trị đã có khi gặp khóa trùng.

Không dựa vào **nội dung chính xác của thông báo ngoại lệ** để xử lý nghiệp vụ vì thông báo có thể khác nhau giữa phiên bản Java; kiểu ngoại lệ và nguyên nhân trùng khóa mới là nội dung cần kiểm tra.

## 4. Overload ba hàm: chủ động xử lý khóa trùng

Khi khóa trùng là điều **hợp lệ theo nghiệp vụ**, chọn:

~~~java
// Chữ ký API rút gọn; không phải chương trình độc lập.
static <T, K, U> Collector<T, ?, Map<K, U>> toMap(
        Function<? super T, ? extends K> keyMapper,
        Function<? super T, ? extends U> valueMapper,
        BinaryOperator<U> mergeFunction);
~~~

`mergeFunction` nhận **hai giá trị `U` của cùng một khóa**, không nhận hai phần tử `T` của stream và cũng không nhận trực tiếp khóa `K`.

Các chiến lược phổ biến:

| Tình huống | `mergeFunction` | Ý nghĩa |
| --- | --- | --- |
| Giữ giá trị đang có | `(oldValue, newValue) -> oldValue` | Bỏ qua giá trị mới khi khóa trùng. |
| Lấy giá trị mới | `(oldValue, newValue) -> newValue` | Giá trị mới thay giá trị trước. |
| Cộng số lượng | `Integer::sum` | Tổng hợp các giá trị có cùng khóa. |
| Giữ mức cao hơn | `Integer::max` | Chọn giá trị lớn nhất theo cùng khóa. |
| Ghép chuỗi | `(a, b) -> a + ", " + b` | Gộp các giá trị thành chuỗi, cần xác định thứ tự. |

Một minh họa hoàn chỉnh để cộng số lượng theo mã hàng. Tạo file `MergeQuantitiesDemo.java`:

~~~java
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.stream.Collectors;

public class MergeQuantitiesDemo {
    record Line(String sku, int quantity) {}

    public static void main(String[] args) {
        List<Line> lines = List.of(
                new Line("B", 4),
                new Line("A", 2),
                new Line("B", 3),
                new Line("A", 5));

        Map<String, Integer> totals = lines.stream()
                .collect(Collectors.toMap(
                        Line::sku,
                        Line::quantity,
                        Integer::sum,
                        TreeMap::new));

        System.out.println(totals);
    }
}
~~~

~~~bash
javac --release 17 MergeQuantitiesDemo.java
java MergeQuantitiesDemo
~~~

Kết quả:

~~~text
{A=7, B=7}
~~~

Ở đây `Line::sku` tạo khóa `String`; `Line::quantity` tạo giá trị `Integer` do boxing từ `int`; `Integer::sum` xử lý số lượng khi khóa trùng. `TreeMap::new` giúp kết quả duyệt khóa theo thứ tự tự nhiên, nên stdout có thứ tự `A`, `B`.

**Quan trọng khi chạy song song:** merge function nên **associative**, stateless và không can thiệp nguồn. Ví dụ phép cộng là phù hợp; logic phụ thuộc trạng thái bên ngoài hoặc thứ tự callback có thể cho kết quả khó dự đoán. Với “giữ giá trị đầu/cuối”, phải định nghĩa “đầu/cuối” theo encounter order và cân nhắc việc stream có thứ tự hay không; không mặc định nó mang nghĩa bản ghi mới nhất theo timestamp.

## 5. Overload bốn hàm: kiểm soát loại Map

Nếu ứng dụng cần Map cụ thể, dùng overload:

~~~java
// Chữ ký API rút gọn để học.
static <T, K, U, M extends Map<K, U>> Collector<T, ?, M> toMap(
        Function<? super T, ? extends K> keyMapper,
        Function<? super T, ? extends U> valueMapper,
        BinaryOperator<U> mergeFunction,
        Supplier<M> mapSupplier);
~~~

Các thành phần:

1. `keyMapper`: `T -> K`.
2. `valueMapper`: `T -> U`.
3. `mergeFunction`: `(U,U) -> U`, áp dụng khi hai khóa được Map xem là trùng.
4. `mapSupplier`: `() -> M`, tạo Map đích (và các Map trung gian cần thiết).

Chọn supplier theo yêu cầu:

| Map | Ví dụ supplier | Đặc tính đáng chú ý |
| --- | --- | --- |
| `HashMap` | `HashMap::new` | Không bảo đảm thứ tự duyệt. |
| `LinkedHashMap` | `LinkedHashMap::new` | Duyệt theo **thứ tự chèn** theo cấu hình mặc định. |
| `TreeMap` | `TreeMap::new` | Duyệt khóa theo **thứ tự comparator/natural order**, yêu cầu khóa so sánh phù hợp. |

Tạo file `MapSupplierDemo.java`:

~~~java
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.stream.Collectors;

public class MapSupplierDemo {
    record Item(String code, int price) {}

    public static void main(String[] args) {
        List<Item> items = List.of(
                new Item("C", 30),
                new Item("A", 10),
                new Item("B", 20));

        Map<String, Integer> insertionOrder = items.stream()
                .collect(Collectors.toMap(
                        Item::code,
                        Item::price,
                        (existing, incoming) -> existing,
                        LinkedHashMap::new));

        Map<String, Integer> sortedKeys = items.stream()
                .collect(Collectors.toMap(
                        Item::code,
                        Item::price,
                        (existing, incoming) -> existing,
                        TreeMap::new));

        System.out.println("insertion=" + insertionOrder);
        System.out.println("sorted=" + sortedKeys);
    }
}
~~~

~~~bash
javac --release 17 MapSupplierDemo.java
java MapSupplierDemo
~~~

Kết quả với nguồn `List` có thứ tự và pipeline tuần tự trên:

~~~text
insertion={C=30, A=10, B=20}
sorted={A=10, B=20, C=30}
~~~

`LinkedHashMap` duy trì insertion order; `TreeMap` duyệt theo thứ tự khóa. Tuy nhiên, điều này **không** tạo bảo đảm rằng mọi parallel/unordered stream đều có thứ tự chèn tương ứng với một yêu cầu nghiệp vụ. Nếu đầu ra cần thứ tự chính xác, hãy đảm bảo encounter order từ nguồn và quy tắc sắp xếp/thu thập rõ ràng, hoặc sắp xếp sau khi thu thập.

## 6. Xử lý giá trị `null`: đừng coi là tự động được bỏ qua

Một lỗi hay gặp là `valueMapper` trả `null`:

~~~java
// Đoạn mô tả rủi ro:
Collectors.toMap(Product::sku, Product::description)
~~~

Nếu `description()` trả `null`, collector `toMap` có thể ném `NullPointerException`. Với implementation JDK thông dụng và hợp đồng thu thập chuẩn, bạn nên **tránh đưa giá trị null vào toMap** ở tất cả overload.

Chọn rõ một trong các chính sách sau:

**A. Từ chối giá trị thiếu:** validate phần tử hoặc dùng `Objects.requireNonNull` kèm thông báo trước khi đưa vào Map.

~~~java
// Đoạn minh họa trong ngữ cảnh có Product.
Collectors.toMap(
        Product::sku,
        p -> java.util.Objects.requireNonNull(
                p.description(), "Missing description: " + p.sku()))
~~~

**B. Dùng giá trị mặc định phù hợp nghiệp vụ:**

~~~java
Collectors.toMap(
        Product::sku,
        p -> p.description() == null ? "(unknown)" : p.description())
~~~

**C. Bỏ bản ghi không có giá trị:** thêm `filter` trước `collect` nếu nghiệp vụ cho phép.

~~~java
products.stream()
        .filter(p -> p.description() != null)
        .collect(Collectors.toMap(Product::sku, Product::description))
~~~

Các đoạn trên là **minh họa**, giả sử `Product` và `products` đã khai báo, và `sku` duy nhất. Lựa chọn B vẫn phải xử lý khóa trùng nếu có; lựa chọn C thay đổi **tập dữ liệu** và không đồng nghĩa với “giữ entry có value null”.

Ví dụ chạy đầy đủ, file `NullValueToMapDemo.java`:

~~~java
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.stream.Collectors;

public class NullValueToMapDemo {
    record Product(String sku, String description) {}

    public static void main(String[] args) {
        List<Product> products = List.of(
                new Product("A", "Bút"),
                new Product("B", null));

        try {
            products.stream().collect(Collectors.toMap(
                    Product::sku,
                    Product::description));
        } catch (NullPointerException ex) {
            System.out.println("null value=NullPointerException");
        }

        Map<String, String> fallback = products.stream()
                .collect(Collectors.toMap(
                        Product::sku,
                        p -> p.description() == null
                                ? "(unknown)" : p.description(),
                        (first, second) -> first,
                        TreeMap::new));

        System.out.println("fallback=" + fallback);
    }
}
~~~

~~~bash
javac --release 17 NullValueToMapDemo.java
java NullValueToMapDemo
~~~

Kết quả:

~~~text
null value=NullPointerException
fallback={A=Bút, B=(unknown)}
~~~

**Khóa null:** overload `toMap` cũng không nên được dùng với giả định sẽ chấp nhận key null. Một số implementation/loại Map có thể chấp nhận null key, nhưng không có bảo đảm chung cho mọi overload và supplier; `TreeMap` theo natural order thông thường không cho null key. Hãy đặt hợp đồng khóa không null, lọc/từ chối key null hoặc thiết kế quy tắc ánh xạ khóa rõ ràng.

## 7. Khóa trùng có thể xuất hiện dù dữ liệu nhìn khác nhau

Không chỉ hai phần tử “giống hệt” mới có thể tạo khóa trùng. Điều này xảy ra khi:

- `String::toLowerCase` biến `"ABC"` và `"abc"` về cùng khóa (với cách chuẩn hóa thống nhất).
- Lấy `emailDomain`: nhiều địa chỉ thuộc cùng miền.
- Lấy năm từ timestamp: nhiều sự kiện có cùng năm.
- Lấy ký tự đầu của tên: nhiều người bắt đầu bằng cùng chữ.
- Dùng `TreeMap` với comparator không phân biệt chữ hoa/chữ thường: hai khóa khác nhau theo `String.equals` vẫn có thể được comparator xem tương đương.

Vì vậy, trước khi chọn overload hai hàm, phải biết `keyMapper` **tạo khóa duy nhất** theo quy tắc Map sẽ dùng. Nếu không, phải chọn giữa `mergeFunction`, `groupingBy` hoặc thay đổi kiểu khóa.

Đặc biệt nếu nhiều phần tử cần giữ **toàn bộ giá trị** trên cùng một khóa, `groupingBy` thường trực tiếp hơn `toMap`:

~~~java
// Minh họa: nhiều Employee có cùng department.
Map<String, List<Employee>> grouped = employees.stream()
        .collect(Collectors.groupingBy(Employee::department));
~~~

Ở đây kiểu giá trị là `List<Employee>`, nên không làm mất các phần tử khi trùng khóa. Cần lưu ý `groupingBy` cũng thường không chấp nhận khóa phân nhóm null; validate dữ liệu hoặc ánh xạ sang khóa mặc định tường minh.

Nếu muốn gom về số lượng, có thể dùng `groupingBy(..., counting())` cho `Map<K,Long>`. Nếu muốn gộp thành một tổng, `toMap(keyMapper, valueMapper, Integer::sum)` cũng phù hợp.

## 8. Khi nào dùng `toMap`, `groupingBy`, `toUnmodifiableMap`?

| Mục tiêu | API thích hợp | Lưu ý |
| --- | --- | --- |
| Mỗi phần tử có khóa duy nhất, lấy một giá trị | `toMap(keyMapper, valueMapper)` | Khóa trùng làm thất bại. |
| Khóa trùng hợp lệ, cần gộp thành một giá trị | `toMap(keyMapper, valueMapper, mergeFunction)` | Merge phải có ngữ nghĩa rõ. |
| Cần loại Map cụ thể | `toMap(keyMapper, valueMapper, mergeFunction, mapSupplier)` | Có thể chọn `LinkedHashMap`, `TreeMap`... |
| Một khóa chứa nhiều bản ghi | `groupingBy(classifier)` | Trả `Map<K,List<T>>` theo mặc định. |
| Cần Map không hỗ trợ thay đổi sau khi thu | `toUnmodifiableMap(keyMapper, valueMapper)` | Java 10+; khóa/giá trị null không hợp lệ; khóa trùng vẫn thất bại nếu không có merge. |

`Collectors.toUnmodifiableMap` có overload cho merge function, nhưng nó **không** có overload `mapSupplier` như `toMap`. Map kết quả không hỗ trợ cập nhật qua API; cũng không nên dựa vào thứ tự lặp hay implementation class nếu không được tài liệu bảo đảm.

Overload `toMap` không có supplier **không bảo đảm** tính mutable, thread-safety, loại Map hoặc serializability của kết quả. Nếu cần một cấu trúc rõ ràng cho API công khai, hãy chọn overload có supplier hoặc sao chép sang cấu trúc đã định nghĩa chính xác, và kiểm tra yêu cầu immutability riêng.

## 9. Method reference và lambda: chọn đúng kiểu ở từng bước

Một pipeline có thể làm biến đổi kiểu **trước khi** gọi `toMap`:

~~~text
List<Employee>
  .stream()                              → Stream<Employee>
  .filter(e -> e.active())               → Stream<Employee>
  .map(Employee::name)                   → Stream<String>
  .collect(toMap(String::length,
                 String::toUpperCase))   → Map<Integer, String>
~~~

Sau `map(Employee::name)`, phần tử đầu vào của cả hai mapper trong `toMap` là **`String`**, không còn là `Employee`. Việc chọn `String::length` làm khóa có khả năng trùng nếu hai tên cùng độ dài — cần merge function hoặc thay khóa.

Một mẫu giữ đối tượng gốc làm value:

~~~java
// Giả sử employees: List<Employee>, id duy nhất và không null.
Map<Long, Employee> byId = employees.stream()
        .collect(Collectors.toMap(
                Employee::id,
                java.util.function.Function.identity()));
~~~

`Function.identity()` là cách viết rõ “giá trị chính là phần tử nguồn”. Dù map chứa các tham chiếu đến đối tượng gốc, không có deep copy: nếu đối tượng mutable bị thay đổi sau khi thu, giá trị mà map trỏ đến cũng phản ánh thay đổi đó.

Nếu khóa được tạo từ thuộc tính **mutable**, thay đổi thuộc tính sau khi chèn không tự cập nhật map key. Với khóa mutable được dùng trực tiếp và `equals/hashCode` thay đổi, lookup có thể bị hỏng. Ưu tiên khóa bất biến như ID, `String` hoặc value object immutable.

## 10. Chọn `Map` với khóa được chuẩn hóa

Nếu nghiệp vụ cần gom mã sản phẩm không phân biệt chữ hoa/thường, nên quy định phép chuẩn hóa và xử lý va chạm.

Tạo file `NormalizeKeyDemo.java`:

~~~java
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Locale;
import java.util.stream.Collectors;

public class NormalizeKeyDemo {
    record Product(String sku, int stock) {}

    public static void main(String[] args) {
        List<Product> products = List.of(
                new Product("ABC", 3),
                new Product("abc", 4),
                new Product("XYZ", 2));

        Map<String, Integer> stockBySku = products.stream()
                .collect(Collectors.toMap(
                        p -> p.sku().toLowerCase(Locale.ROOT),
                        Product::stock,
                        Integer::sum,
                        LinkedHashMap::new));

        System.out.println(stockBySku);
    }
}
~~~

~~~bash
javac --release 17 NormalizeKeyDemo.java
java NormalizeKeyDemo
~~~

Kết quả với nguồn tuần tự có thứ tự:

~~~text
{abc=7, xyz=2}
~~~

Dùng `Locale.ROOT` để tránh việc chuẩn hóa chữ hoa/thường phụ thuộc locale mặc định của môi trường. Tùy miền dữ liệu, phép chuẩn hóa có thể cần bước khác như trim, Unicode normalization, quy tắc ID riêng; không áp dụng `toLowerCase` tùy tiện cho khóa có tính phân biệt hoa/thường theo hợp đồng.

Điều quan trọng là **chính sách merge**: `Integer::sum` cộng tồn kho từ hai mã được chuẩn hóa về cùng khóa. Nếu không muốn gộp, hãy validate khóa duy nhất và để lỗi xuất hiện, thay vì âm thầm chọn một bản ghi.

## 11. Thu thập trên stream rỗng và trong môi trường song song

Khi nguồn thực sự rỗng, `collect(toMap(...))` trả một **Map rỗng** theo collector hợp lệ. Không có phần tử để gọi `keyMapper`, `valueMapper` hoặc `mergeFunction`. Supplier có thể được dùng để tạo container kết quả.

Ví dụ minh họa:

~~~java
// Trong phương thức đã import các class tương ứng.
Map<String, Integer> result = java.util.stream.Stream.<String>empty()
        .collect(java.util.stream.Collectors.toMap(
                s -> s,
                String::length));
System.out.println(result.isEmpty()); // true
~~~

Với **parallel stream**, collector có thể tạo nhiều map trung gian rồi gộp. Vì vậy:

- Không dựa vào số lần hay thứ tự gọi mapper/merge để thực hiện side effect.
- Mapper và merge nên **stateless**, non-interfering; merge cần đặc tính kết hợp phù hợp để tránh kết quả phụ thuộc cách nhóm.
- Không giả định `Map` đầu ra của `toMap` thông thường là concurrent map hay có thể được nhiều thread sửa an toàn. Kết quả cuối là Map; thread-safety phụ thuộc implementation và cách dùng sau đó.
- Nếu thực sự cần collector concurrent, tìm hiểu `Collectors.toConcurrentMap` cùng các ràng buộc liên quan, thay vì gọi `parallel()` và nghĩ loại Map tự động đổi.
- Với yêu cầu về insertion order, tie-breaking hoặc “giữ bản ghi đầu tiên”, hãy xác định encounter order và kiểm thử với dữ liệu thực, đặc biệt khi nguồn ban đầu không có thứ tự.

## 12. Lỗi thường gặp và dấu hiệu nhận biết

1. **Quên hai mapper dùng cùng kiểu phần tử nguồn**: sau `map`, `toMap` không còn nhận kiểu trước đó.
2. **Giả định mọi khóa là duy nhất**: dữ liệu thực tạo trùng và overload hai hàm ném `IllegalStateException`.
3. **Đánh đồng trùng khóa với trùng giá trị**: nhiều khóa có thể có cùng value hoàn toàn hợp lệ; **cùng khóa** mới là vấn đề.
4. **Dùng `valueMapper` nullable**: gặp `NullPointerException`. Chọn rõ bỏ qua, mặc định hay fail-fast.
5. **Dựa vào việc `HashMap` chấp nhận null key**: hợp đồng của collector và supplier không cho phép suy rộng cho mọi map; nên validate key.
6. **Tưởng `toMap` luôn sắp xếp**: overload hai/ba hàm không bảo đảm thứ tự lặp hay loại Map.
7. **Tưởng `mergeFunction` nhận khóa và giá trị mới**: nó nhận hai **giá trị cũ/mới** cho cùng khóa.
8. **Dùng `(a,b) -> a` khi cần lưu mọi bản ghi**: mất thông tin; `groupingBy` thường phù hợp hơn.
9. **Dùng `toMap` làm phép cộng mà quên merge**: một khóa xuất hiện nhiều lần gây lỗi thay vì cộng.
10. **Dùng mapper/merge có side effect**: kết quả có thể thay đổi theo cách thực thi, đặc biệt với parallel.
11. **Dùng khóa mutable**: thay đổi `equals/hashCode` hoặc thuộc tính khóa có thể khiến lookup không đúng.
12. **Nhầm `toMap` với `Map.of`**: `Map.of` tạo Map trực tiếp từ các cặp cố định và không chấp nhận null/trùng key; `toMap` là một collector dành cho Stream.
13. **Nhầm Map kết quả có thể sửa theo hợp đồng**: `Collectors.toMap` cơ bản không bảo đảm mutability, nên không thiết kế dựa vào đặc điểm của implementation hiện tại.
14. **Tưởng `TreeMap` dùng `equals/hashCode` như `HashMap`**: TreeMap dựa vào comparator/natural order để quyết định khóa tương đương.
15. **Bỏ qua `Map.get` khác kiểu khóa**: `Map<Long,V>` phải lookup `Long` (ví dụ `1L`), không phải `Integer` (`1`).
16. **Dùng stream một lần cho nhiều `collect`**: terminal operation tiêu thụ stream; cần tạo stream mới từ nguồn có thể đọc lại.

## 13. Checklist thiết kế `toMap()`

Trước khi viết collector, xác nhận:

- **Nguồn `T`** là kiểu gì ngay trước `collect`?
- **Khóa `K`** được tạo từ đâu, có bất biến, không null và duy nhất hay không?
- **Giá trị `U`** là thuộc tính, dữ liệu biến đổi hay cả phần tử qua `Function.identity()`?
- Nếu có hai phần tử cùng khóa, phải **báo lỗi**, giữ một giá trị, cộng dồn, chọn min/max hay **giữ tất cả** qua `groupingBy`?
- Có quy tắc rõ ràng cho **giá trị null** và **khóa null** chưa?
- Cần `HashMap`, `LinkedHashMap`, `TreeMap`, hoặc một Map không hỗ trợ chỉnh sửa không?
- Thứ tự kết quả có được yêu cầu không? Nếu có, thứ tự dựa trên encounter order hay comparator của khóa?
- Có chạy parallel stream hay mapper/merge tốn chi phí, chứa side effect, truy cập trạng thái mutable không?
- Test đã bao gồm **stream rỗng**, **khóa trùng**, **giá trị null**, **khóa null**, **khóa khác kiểu khi lookup**, và **thứ tự Map** chưa?

**Ghi nhớ:** `Collectors.toMap(keyMapper, valueMapper)` là cách diễn đạt **mỗi phần tử `T` trở thành một cặp `K → U`**. Nó không tự xử lý khóa trùng, không phải công cụ cho phép value null, và không mặc nhiên bảo đảm thứ tự Map. Khi cần merge hoặc loại Map cụ thể, hãy chọn overload ba/bốn hàm, mô tả rõ ngữ nghĩa của merge và bảo toàn tính đúng trên nguồn dữ liệu thực.
