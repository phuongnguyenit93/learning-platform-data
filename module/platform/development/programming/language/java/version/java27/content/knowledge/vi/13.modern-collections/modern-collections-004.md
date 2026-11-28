# TreeSet, TreeMap, Comparable và Comparator trong Java 27

Trong **Java 27**, khi cần lưu một tập giá trị **không trùng nhau và luôn có thứ tự**, có thể dùng `TreeSet`. Khi cần ánh xạ **khóa → giá trị** và muốn duyệt khóa theo thứ tự, có thể dùng `TreeMap`. Cả hai đều dựa vào một quy tắc **so sánh thứ tự**, được cung cấp bởi:

- `Comparable<T>`: kiểu dữ liệu tự định nghĩa **thứ tự tự nhiên** (*natural ordering*).
- `Comparator<T>`: một đối tượng/hàm bên ngoài định nghĩa **thứ tự tùy chọn** (*custom ordering*).

Điều quan trọng là các cấu trúc này không chỉ dùng phép so sánh để hiển thị phần tử theo thứ tự. **Kết quả so sánh bằng `0` còn quyết định hai phần tử/khóa có bị coi là trùng nhau hay không.** Vì vậy, thiết kế thứ tự sai có thể khiến `TreeSet` bỏ qua một phần tử, hoặc `TreeMap` thay thế một giá trị dưới một khóa mà lập trình viên nghĩ là khác.

Bài học thuộc chương **Collections hiện đại**, chỉ sử dụng các API Java Collections Framework hiện hành và ổn định trong Java SE 27.

## 1. Bức tranh tổng quan

### 1.1. `TreeSet` là gì?

`TreeSet<E>` là một cách triển khai `NavigableSet<E>`, có các đặc điểm:

- Lưu **tập hợp phần tử không trùng theo quy tắc so sánh**.
- Duyệt theo **thứ tự tăng dần** của quy tắc so sánh, không phải thứ tự thêm vào.
- Hỗ trợ truy vấn gần nhất như phần tử nhỏ hơn/lớn hơn một mốc.
- Hỗ trợ lấy một **vùng giá trị** (*range view*), ví dụ các mã từ "B" đến trước "M".
- Các thao tác cơ bản `add`, `remove`, `contains` có chi phí được bảo đảm ở mức `O(log n)`.

```java
import java.util.TreeSet;

var numbers = new TreeSet<Integer>();
numbers.add(30);
numbers.add(10);
numbers.add(20);
numbers.add(10);

System.out.println(numbers); // [10, 20, 30]
```

Thêm số `10` lần thứ hai không làm tăng kích thước tập hợp; dữ liệu được duyệt theo thứ tự tăng, bất kể thứ tự `add`.

### 1.2. `TreeMap` là gì?

`TreeMap<K,V>` là một cách triển khai `NavigableMap<K,V>`, có các đặc điểm:

- Mỗi **khóa** ánh xạ đến một giá trị; khóa được tổ chức theo thứ tự so sánh.
- Khi duyệt `entrySet()` hoặc `keySet()`, các khóa xuất hiện theo thứ tự tăng.
- Hỗ trợ truy vấn khóa hoặc entry gần một mốc, lấy vùng khóa, duyệt ngược.
- Các thao tác cơ bản `containsKey`, `get`, `put`, `remove` có chi phí được bảo đảm ở mức `O(log n)`.
- Phần **giá trị** không cần triển khai `Comparable`; chỉ khóa cần có thứ tự phù hợp.

```java
import java.util.TreeMap;

var prices = new TreeMap<String, Integer>();
prices.put("orange", 25);
prices.put("apple", 15);
prices.put("banana", 20);

System.out.println(prices); // {apple=15, banana=20, orange=25}
```

Theo thứ tự tự nhiên của `String`, các khóa được sắp xếp theo thứ tự từ điển theo đơn vị UTF-16. Đây không tự động là cách sắp xếp ngôn ngữ tự nhiên phù hợp với mọi người dùng hoặc mọi locale.

### 1.3. Khác biệt nhanh so với các collection thông dụng

| Cấu trúc | Dữ liệu lưu trữ | Thứ tự duyệt | Thao tác tra cứu/thêm/xóa thông dụng |
| --- | --- | --- | --- |
| `HashSet` | Phần tử không trùng theo `equals`/`hashCode` | Không bảo đảm thứ tự | Trung bình gần `O(1)` khi phân phối băm phù hợp |
| `TreeSet` | Phần tử không trùng theo phép so sánh | **Tăng dần** theo thứ tự so sánh | `O(log n)` |
| `HashMap` | Khóa → giá trị, dựa vào `equals`/`hashCode` | Không bảo đảm thứ tự khóa | Trung bình gần `O(1)` khi băm phù hợp |
| `TreeMap` | Khóa → giá trị, dựa vào phép so sánh | **Tăng dần** theo thứ tự khóa | `O(log n)` |
| `LinkedHashMap` | Khóa → giá trị | Có thể duy trì thứ tự chèn/truy cập theo cấu hình | Thường gần `O(1)` cho thao tác cơ bản |

**Chỉ chọn cấu trúc cây khi thật sự cần thứ tự hoặc các phép truy vấn vùng/láng giềng.** Nếu chỉ cần tra cứu theo khóa không có thứ tự, `HashMap` thường phù hợp hơn.

## 2. Cơ chế xác định thứ tự: tự nhiên hoặc do `Comparator` cung cấp

Khi tạo một `TreeSet` hoặc `TreeMap`, có hai cách chính:

1. **Không đưa comparator vào constructor:** dùng *natural ordering* từ `Comparable.compareTo`.
2. **Đưa một `Comparator`:** sử dụng `Comparator.compare` để xác định thứ tự.

```java
import java.util.Comparator;
import java.util.TreeSet;

TreeSet<Integer> ascending = new TreeSet<>();
TreeSet<Integer> descending =
        new TreeSet<>(Comparator.reverseOrder());

ascending.addAll(java.util.List.of(3, 1, 2));
descending.addAll(java.util.List.of(3, 1, 2));

System.out.println(ascending);  // [1, 2, 3]
System.out.println(descending); // [3, 2, 1]
```

Thứ tự so sánh ảnh hưởng đồng thời đến việc **duyệt dữ liệu, tìm láng giềng, xác định vùng, và xem hai khóa/phần tử có tương đương nhau hay không**.

Một comparator có thể đảo thứ tự mà không làm đổi tính duy nhất; nhưng comparator chỉ so sánh một thuộc tính có thể **gộp** những đối tượng mà ứng dụng muốn giữ riêng. Đây là một rủi ro thiết kế cần xem xét từ đầu.

## 3. `Comparable<T>` — thứ tự tự nhiên do chính lớp định nghĩa

Interface `java.lang.Comparable<T>` có một phương thức:

```java
int compareTo(T other);
```

Ý nghĩa kết quả:

| `a.compareTo(b)` | Diễn giải |
| --- | --- |
| Nhỏ hơn `0` | `a` đứng **trước** `b` |
| Bằng `0` | `a` và `b` **tương đương về thứ tự** |
| Lớn hơn `0` | `a` đứng **sau** `b` |

Không cần trả chính xác `-1`, `0` hoặc `1`. Hợp đồng quan tâm **dấu** của kết quả, không phải trị tuyệt đối.

### 3.1. Ví dụ: khóa bất biến có thứ tự theo hai trường

Giả sử mã sản phẩm được xác định bởi một nhóm hàng và một mã trong nhóm. Có thể biểu diễn bằng `record` bất biến:

```java
import java.util.Objects;

record ProductKey(String category, String code)
        implements Comparable<ProductKey> {

    ProductKey {
        Objects.requireNonNull(category, "category");
        Objects.requireNonNull(code, "code");
    }

    @Override
    public int compareTo(ProductKey other) {
        int byCategory = category.compareTo(other.category());
        if (byCategory != 0) {
            return byCategory;
        }
        return code.compareTo(other.code());
    }
}
```

Đây là thứ tự tăng theo `category`; khi cùng nhóm mới so tiếp `code`. Với hai record, `equals` được sinh từ **cả hai component**. `compareTo` cũng trả về `0` khi và chỉ khi cả hai component bằng nhau, nên thứ tự nhất quán với `equals`.

Sử dụng:

```java
var keys = new java.util.TreeSet<ProductKey>();
keys.add(new ProductKey("book", "B02"));
keys.add(new ProductKey("pen", "P01"));
keys.add(new ProductKey("book", "B01"));

for (ProductKey key : keys) {
    System.out.println(key.category() + "/" + key.code());
}
```

Kết quả:

```text
book/B01
book/B02
pen/P01
```

### 3.2. Hợp đồng `compareTo`

Một triển khai `Comparable` hợp lệ phải tuân thủ các tính chất quan trọng:

- **Đối xứng về dấu:** dấu của `x.compareTo(y)` phải đối nghịch dấu của `y.compareTo(x)`.
- **Bắc cầu:** nếu `x > y` và `y > z` thì `x > z` theo quy tắc đã chọn.
- **Các nhóm tương đương nhất quán:** nếu `x.compareTo(y) == 0` thì với mọi `z`, dấu của `x.compareTo(z)` phải bằng dấu của `y.compareTo(z)`.
- So sánh phải có ý nghĩa ổn định với trạng thái đang xét; không phụ thuộc tùy ý vào thời gian, số lần gọi hay biến toàn cục.

Tài liệu API **khuyến nghị mạnh** quan hệ `x.compareTo(y) == 0` đồng nhất với `x.equals(y)`, dù điều đó không phải yêu cầu tuyệt đối của `Comparable`. Nếu khác nhau, đặc biệt phải chú ý khi dùng `TreeSet` hoặc `TreeMap`.

**Không nên viết phép so sánh số nguyên bằng cách trừ**:

```java
// Dễ sai do tràn số:
// return this.priority - other.priority;
```

Hai số `int` ở hai cực trị có thể làm kết quả phép trừ bị tràn và đảo dấu. Hãy dùng:

```java
return Integer.compare(this.priority, other.priority);
```

Với `long` dùng `Long.compare`; với `double` dùng `Double.compare` khi muốn semantics phù hợp với lớp wrapper, bao gồm trường hợp `NaN` và số không có dấu.

### 3.3. Khi nào nên để lớp triển khai `Comparable`?

Nên dùng khi kiểu có một thứ tự **tự nhiên, ổn định và được mọi người đồng thuận** trong miền dữ liệu, ví dụ:

- Mã định danh có quy tắc thứ tự rõ ràng.
- Giá trị ngày/giờ từ các kiểu như `LocalDate`.
- Số nguyên, chuỗi có thứ tự tự nhiên như API định nghĩa.

Nếu ứng dụng cần nhiều thứ tự đều hợp lý — xếp theo tên, điểm, ngày tạo, mức ưu tiên — đừng cố nhồi mọi trường hợp vào một `compareTo`; dùng các `Comparator` riêng.

## 4. `Comparator<T>` — khai báo thứ tự bên ngoài kiểu dữ liệu

`java.util.Comparator<T>` là functional interface với phương thức chính:

```java
int compare(T first, T second);
```

Có thể tạo comparator bằng lambda, method reference hoặc các factory method tiện ích:

```java
import java.util.Comparator;

record Ticket(String id, int priority) {}

Comparator<Ticket> byPriority =
        Comparator.comparingInt(Ticket::priority);

Comparator<Ticket> byId =
        Comparator.comparing(Ticket::id);
```

Hàm `comparingInt` tránh boxing chỉ để lấy khóa so sánh kiểu `int`. Các phương thức hiện hành khác gồm `comparingLong`, `comparingDouble`, `comparing`, `thenComparing` và `reversed`.

### 4.1. Thêm tiêu chí phụ bằng `thenComparing`

Giả sử hai ticket có thể có cùng `priority` nhưng khác `id`. Nếu dùng `Comparator.comparingInt(Ticket::priority)` trong `TreeSet`, hai ticket cùng mức ưu tiên sẽ bị coi là trùng. Để giữ chúng riêng, thêm tiêu chí `id`:

```java
Comparator<Ticket> byPriorityThenId =
        Comparator.comparingInt(Ticket::priority)
                  .thenComparing(Ticket::id);
```

So sánh diễn ra theo thứ tự:

1. So `priority`.
2. Nếu bằng nhau, so `id`.
3. Chỉ trả về `0` nếu cả hai tiêu chí bằng nhau.

Với record `Ticket(String id, int priority)` và giả định `id` không `null`, comparator này nhất quán với `equals` do record sinh ra. Nếu `id` có thể `null`, cần định nghĩa chính sách so sánh `null` rõ ràng.

```java
var tickets = new java.util.TreeSet<>(byPriorityThenId);

tickets.add(new Ticket("T-02", 1));
tickets.add(new Ticket("T-01", 1));
tickets.add(new Ticket("T-03", 2));

for (Ticket ticket : tickets) {
    System.out.println(ticket.id());
}
```

Kết quả:

```text
T-01
T-02
T-03
```

### 4.2. Đảo thứ tự bằng `reversed()`

```java
Comparator<Ticket> highFirst = byPriorityThenId.reversed();
```

Cách này đảo **toàn bộ** thứ tự: ưu tiên cao trước, và ID cũng đảo trong cùng mức ưu tiên. Nếu chỉ muốn ưu tiên giảm dần nhưng ID vẫn tăng dần, hãy diễn đạt riêng:

```java
Comparator<Ticket> highPriorityThenId =
        Comparator.comparingInt(Ticket::priority)
                  .reversed()
                  .thenComparing(Ticket::id);
```

Thứ tự đặt `reversed()` và `thenComparing()` ảnh hưởng kết quả. Đừng xem chúng là hai thao tác hoán đổi tự do.

### 4.3. `nullsFirst` và `nullsLast`

Nếu miền dữ liệu **cố ý cho phép `null`**, có thể viết comparator biết xử lý `null`:

```java
Comparator<String> nullableNames =
        Comparator.nullsLast(Comparator.naturalOrder());

System.out.println(nullableNames.compare("Lan", null) < 0); // true
```

Với `TreeSet`/`TreeMap`, việc có chấp nhận khóa/phần tử `null` phụ thuộc comparator. Thứ tự tự nhiên thông thường **không chấp nhận `null`**. Trong nhiều hệ thống, một khóa không được `null` là thiết kế an toàn và dễ hiểu hơn; chỉ sử dụng hỗ trợ `null` nếu nghiệp vụ thật sự cần.

## 5. Phân biệt `compare(...) == 0` với `equals(...)`

Đây là điểm quan trọng nhất khi dùng cấu trúc sắp xếp.

`HashSet`/`HashMap` dựa vào quy tắc `equals`/`hashCode`. `TreeSet`/`TreeMap` dựa vào `compareTo` hoặc `Comparator.compare` để xác định các phần tử/khóa tương đương về thứ tự.

Xét hai chuỗi:

```java
String a = "java";
String b = "JAVA";

System.out.println(a.equals(b)); // false
System.out.println(
        String.CASE_INSENSITIVE_ORDER.compare(a, b) == 0
); // true
```

Nếu dùng comparator không phân biệt hoa/thường trong `TreeSet`:

```java
var names = new java.util.TreeSet<String>(
        String.CASE_INSENSITIVE_ORDER
);

System.out.println(names.add("java")); // true
System.out.println(names.add("JAVA")); // false
System.out.println(names.size());      // 1
```

Đối với cây, hai chuỗi **được coi là một phần tử**, vì kết quả so sánh là `0`. Đây có thể là ý đồ của nghiệp vụ muốn gộp tên không phân biệt hoa/thường; nhưng nếu muốn giữ cả hai chuỗi, comparator này không phù hợp.

Tương tự, với `TreeMap`:

```java
var scores = new java.util.TreeMap<String, Integer>(
        String.CASE_INSENSITIVE_ORDER
);

scores.put("java", 10);
scores.put("JAVA", 20);

System.out.println(scores.size());       // 1
System.out.println(scores.get("java"));   // 20
```

Lệnh `put` thứ hai **cập nhật giá trị** của khóa tương đương theo comparator thay vì thêm một khóa mới. Khóa được giữ trong cấu trúc không nhất thiết đổi thành chuỗi được đưa vào lần `put` thứ hai; không nên suy luận giá trị khóa hiển thị dựa trên lần ghi sau.

> **Hợp đồng:** Các tài liệu `TreeSet` và `TreeMap` yêu cầu quy tắc thứ tự phải nhất quán với `equals` **nếu muốn tuân thủ đầy đủ hợp đồng chung của `Set`/`Map`**. Khi comparator không nhất quán, hành vi so sánh theo cây vẫn được xác định, nhưng có thể trái với kỳ vọng về tính duy nhất dựa trên `equals`. Phải ghi rõ và chấp nhận chủ đích nếu sử dụng.

### 5.1. Khi muốn sắp xếp không phân biệt hoa/thường nhưng vẫn giữ hai khóa

Thêm tiêu chí phụ phân biệt chính tả chính xác:

```java
Comparator<String> ignoreCaseThenExact =
        String.CASE_INSENSITIVE_ORDER
                .thenComparing(Comparator.naturalOrder());

var set = new java.util.TreeSet<>(ignoreCaseThenExact);
set.add("java");
set.add("JAVA");

System.out.println(set.size()); // 2
```

So sánh không phân biệt hoa/thường chỉ là tiêu chí đầu. Nếu hòa, dùng thứ tự tự nhiên của `String` để phân biệt chính xác. Vì vậy, hai chuỗi chỉ tương đương (kết quả `0`) khi chúng có cùng nội dung theo `String.equals`.

Nếu **nghiệp vụ yêu cầu** mã không phân biệt hoa/thường phải là *cùng một khóa*, một cách khác là chuẩn hóa khóa về dạng chuẩn có kiểm soát ngay từ đầu và dùng dạng chuẩn ở mọi nơi. Cần quy định rõ locale/Unicode của quá trình chuẩn hóa, thay vì mặc định `toLowerCase()` là đủ cho mọi ngôn ngữ.

### 5.2. Ngoại lệ nổi tiếng: `BigDecimal`

`BigDecimal.compareTo` và `BigDecimal.equals` có semantics khác nhau:

```java
import java.math.BigDecimal;

BigDecimal x = new BigDecimal("1.0");
BigDecimal y = new BigDecimal("1.00");

System.out.println(x.compareTo(y)); // 0
System.out.println(x.equals(y));    // false
```

Thứ tự tự nhiên của `BigDecimal` so sánh theo **giá trị số học**, còn `equals` còn xét *scale*. Vì vậy, hai đối tượng có thể bị `TreeSet<BigDecimal>` coi là trùng dù một `HashSet<BigDecimal>` có thể giữ cả hai.

Đây là ngoại lệ đã được **ghi rõ trong tài liệu API hiện hành**, không phải lỗi của cây. Hãy quyết định liệu miền dữ liệu muốn bình đẳng theo giá trị số học hay theo cả `scale`, rồi chọn cách lưu/chuẩn hóa phù hợp.

## 6. `TreeSet` — các thao tác tìm phần tử theo thứ tự

Vì `TreeSet` triển khai `NavigableSet`, ta có nhiều thao tác hơn `add`, `contains` và `remove`.

```java
import java.util.List;
import java.util.TreeSet;

var points = new TreeSet<>(List.of(10, 20, 30, 40));
```

| Phương thức | Ý nghĩa | Kết quả với ví dụ |
| --- | --- | --- |
| `first()` | Phần tử nhỏ nhất | `10` |
| `last()` | Phần tử lớn nhất | `40` |
| `lower(20)` | Phần tử lớn nhất **nhỏ hơn** 20 | `10` |
| `floor(20)` | Phần tử lớn nhất **nhỏ hơn hoặc bằng** 20 | `20` |
| `ceiling(25)` | Phần tử nhỏ nhất **lớn hơn hoặc bằng** 25 | `30` |
| `higher(20)` | Phần tử nhỏ nhất **lớn hơn** 20 | `30` |
| `pollFirst()` | Lấy và **xóa** phần tử nhỏ nhất | `10`; tập bị thay đổi |
| `pollLast()` | Lấy và **xóa** phần tử lớn nhất | `40`; tập bị thay đổi |

```java
System.out.println(points.lower(20));   // 10
System.out.println(points.floor(20));   // 20
System.out.println(points.ceiling(25)); // 30
System.out.println(points.higher(20));  // 30
```

Các phương thức `lower`, `floor`, `ceiling`, `higher` trả về `null` nếu không tìm thấy phần tử phù hợp. Ngược lại, `first()` và `last()` sẽ ném `NoSuchElementException` nếu tập hợp rỗng. `pollFirst()`/`pollLast()` trả về `null` nếu rỗng.

Với comparator cho phép lưu `null`, không nên mặc định `null` trả về từ các phương thức tìm láng giềng luôn biểu thị “không có phần tử”. Một thiết kế không chứa `null` giúp giao diện dễ sử dụng hơn.

### 6.1. Tập con và các ranh giới inclusive/exclusive

```java
var set = new TreeSet<>(List.of(10, 20, 30, 40, 50));

var range = set.subSet(20, true, 40, false);
System.out.println(range); // [20, 30]
```

Tham số `true`/`false` lần lượt quy định có **bao gồm** biên dưới và biên trên hay không. Ngoài `subSet` còn có:

- `headSet(to, inclusive)`: phần trước một giới hạn.
- `tailSet(from, inclusive)`: phần từ một giới hạn trở đi.
- `descendingSet()`: view theo thứ tự ngược.

```java
System.out.println(set.headSet(30, false)); // [10, 20]
System.out.println(set.tailSet(30, true));  // [30, 40, 50]
System.out.println(set.descendingSet());    // [50, 40, 30, 20, 10]
```

**Quan trọng:** `subSet`, `headSet`, `tailSet` và `descendingSet` là **view được hỗ trợ bởi collection gốc** (*backed view*), không mặc định là bản sao độc lập.

```java
var set = new TreeSet<>(List.of(10, 20, 30, 40));
var middle = set.subSet(10, true, 40, false);

middle.remove(20);

System.out.println(set);    // [10, 30, 40]
System.out.println(middle); // [10, 30]
```

Xóa trong view đã xóa phần tử khỏi tập gốc. Ngược lại, thay đổi tập gốc cũng phản ánh trong view theo giới hạn tương ứng. Thao tác thêm vào view một phần tử nằm ngoài khoảng cho phép sẽ ném `IllegalArgumentException`.

Nếu cần một collection riêng biệt, hãy chủ động sao chép:

```java
var independent = new TreeSet<>(middle);
```

Bản sao này không chia sẻ cấu trúc tập với `middle`, nhưng chỉ sao chép tham chiếu tới các phần tử; nếu phần tử mutable thì bản thân chúng vẫn là những đối tượng dùng chung.

### 6.2. Lưu ý với API `SequencedSet`

Kể từ Java 21, `TreeSet` cũng thuộc hệ API *sequenced collections*. Nó có thể lấy phần tử đầu/cuối theo thứ tự và tạo view đảo chiều. Tuy nhiên, **không thể chủ động đặt vị trí chèn** trong một cây có thứ tự so sánh: `TreeSet.addFirst(...)` và `TreeSet.addLast(...)` ném `UnsupportedOperationException`.

Đừng nhầm “có thứ tự được duyệt” với “được phép chọn vị trí chèn như `List` hoặc một collection theo thứ tự chèn”. Thứ tự của `TreeSet` do comparator hoặc natural ordering quyết định.

## 7. `TreeMap` — ánh xạ có thứ tự khóa và các phép tìm lân cận

Tạo `TreeMap` theo thứ tự tự nhiên:

```java
import java.util.TreeMap;

var inventory = new TreeMap<Integer, String>();

inventory.put(100, "Bút");
inventory.put(300, "Sổ");
inventory.put(200, "Thước");

System.out.println(inventory);
// {100=Bút, 200=Thước, 300=Sổ}
```

Gọi `inventory.put(200, "Thước mới")` thay thế giá trị gắn với khóa `200`, không tăng số lượng entry.

Trong `TreeMap`, giá trị có thể cùng nhau hoặc khác nhau tùy ý; phép so sánh dùng cho **khóa**, không phải `String` giá trị trong ví dụ.

### 7.1. Truy vấn theo khóa và entry

| API | Kết quả hoặc ý nghĩa |
| --- | --- |
| `firstKey()` / `lastKey()` | Khóa đầu/cuối; ném `NoSuchElementException` nếu map rỗng |
| `firstEntry()` / `lastEntry()` | Entry có khóa đầu/cuối; trả về `null` nếu rỗng |
| `lowerKey(k)` / `higherKey(k)` | Khóa ngay trước/sau `k` theo thứ tự |
| `floorKey(k)` / `ceilingKey(k)` | Khóa gần nhất ≤ `k` / ≥ `k` |
| `lowerEntry(k)` / `higherEntry(k)` | Entry của khóa trước/sau |
| `floorEntry(k)` / `ceilingEntry(k)` | Entry gần nhất ≤ `k` / ≥ `k` |
| `pollFirstEntry()` / `pollLastEntry()` | Lấy và **xóa** entry đầu/cuối |
| `descendingMap()` | View duyệt map theo thứ tự khóa giảm dần |
| `navigableKeySet()` | View tập khóa có thể điều hướng |

```java
var map = new TreeMap<Integer, String>();
map.put(10, "basic");
map.put(20, "standard");
map.put(30, "premium");

System.out.println(map.floorKey(25));   // 20
System.out.println(map.ceilingKey(25)); // 30
System.out.println(map.lowerEntry(20)); // 10=basic
System.out.println(map.higherEntry(20)); // 30=premium
```

Khi chỉ cần khóa, dùng các biến thể `...Key`; khi cần cả khóa và giá trị, dùng `...Entry`. Một kết quả entry có thể là `null` khi không có ứng viên. Nếu map chứa giá trị `null`, đừng suy luận rằng `get(key) == null` chứng minh khóa không tồn tại: dùng `containsKey(key)` để kiểm tra.

### 7.2. `subMap`, `headMap`, `tailMap` và view trực tiếp

```java
var map = new TreeMap<Integer, String>();
map.put(10, "A");
map.put(20, "B");
map.put(30, "C");
map.put(40, "D");

var middle = map.subMap(10, true, 30, false);
System.out.println(middle); // {10=A, 20=B}

middle.put(20, "B2");
System.out.println(map.get(20)); // B2
```

`subMap(from, fromInclusive, to, toInclusive)` trả về view được hỗ trợ bởi map gốc. Tương tự `TreeSet`, thay đổi view tác động lên map gốc trong phạm vi được phép. `headMap` và `tailMap` cũng cung cấp view theo vùng.

- Với view, `put` khóa ngoài phạm vi sẽ ném `IllegalArgumentException`.
- Các biên được hiểu theo **thứ tự comparator hiện hành**, không nhất thiết theo giá trị số tăng nếu comparator đảo chiều.
- Nếu cần bản sao độc lập, tạo một `TreeMap` mới từ view. Hãy lưu ý constructor nhận `SortedMap` có thể giữ thứ tự comparator của nguồn; không cần tự giả định thứ tự luôn là natural.

```java
var copy = new TreeMap<>(middle);
```

### 7.3. Duyệt theo khóa, không dựa vào `entrySet()` của `HashMap`

```java
for (var entry : map.entrySet()) {
    System.out.println(entry.getKey() + " -> " + entry.getValue());
}
```

Với `TreeMap`, thứ tự đi qua entry là thứ tự các **khóa tăng dần** theo quy tắc so sánh. Nếu muốn duyệt ngược mà không thay đổi collection gốc:

```java
for (var entry : map.descendingMap().entrySet()) {
    System.out.println(entry.getKey() + " -> " + entry.getValue());
}
```

Không nên sắp xếp lại nhiều lần danh sách `entrySet()` nếu yêu cầu của ứng dụng là duy trì khả năng truy vấn có thứ tự thường xuyên. `TreeMap` đã thể hiện chính yêu cầu đó.

## 8. So sánh đúng để bảo vệ tính nhất quán

### 8.1. Quy tắc ba ngôi của `Comparator.compare`

Tương tự `Comparable`, comparator phải đáp ứng:

1. `sign(compare(x, y)) == -sign(compare(y, x))`.
2. Tính bắc cầu của quan hệ lớn hơn/nhỏ hơn.
3. Nếu `compare(x, y) == 0` thì `compare(x, z)` và `compare(y, z)` có cùng dấu với mọi `z`.
4. Xử lý đối số không hợp lệ nhất quán; nếu không chấp nhận `null`, nên để lỗi được phát hiện rõ.

Comparator không được tạo “vòng” như `A < B`, `B < C` nhưng lại `C < A`. Cây tìm kiếm theo thứ tự yêu cầu quan hệ thứ tự nhất quán.

### 8.2. Tránh comparator phụ thuộc trạng thái có thể thay đổi

Đây là một anti-pattern:

```java
// Không nên làm: thứ tự thay đổi theo thời gian hiện tại.
// Comparator<Task> byDeadlineDistance =
//         Comparator.comparingLong(t ->
//                 Math.abs(t.deadlineMillis() - System.currentTimeMillis()));
```

Nếu comparator thay đổi kết quả khi dữ liệu trong collection không đổi, cấu trúc cây có thể không còn phù hợp với thứ tự đã sử dụng khi chèn. Tương tự, khi một trường của đối tượng đang nằm trong `TreeSet` hoặc đang làm khóa trong `TreeMap` bị sửa, thứ tự nội bộ có thể bị phá vỡ.

Cách an toàn:

- Ưu tiên **khóa bất biến**: `String`, `Integer`, `LocalDate`, `record` có thành phần bất biến.
- Nếu giá trị phụ thuộc vào thời gian, tính và lưu một **khóa so sánh ổn định** tại thời điểm tạo; khi thay đổi thứ tự nghiệp vụ, xóa và chèn lại với khóa mới hoặc xây dựng lại cây.
- Không để comparator gọi API gây tác dụng phụ hoặc trả kết quả không ổn định.

### 8.3. Không dùng trừ số; chú ý số thực và `null`

Sai tiềm ẩn:

```java
// Comparator<Integer> unsafe = (a, b) -> a - b;
```

Đúng hơn:

```java
Comparator<Integer> numeric = Integer::compare;
```

Với giá trị có thể `null`, chọn `Comparator.nullsFirst(...)` hoặc `nullsLast(...)` theo yêu cầu nghiệp vụ. Với số thực, xác định rõ cách xử lý `NaN` và `-0.0`/`+0.0`; dùng `Double.compare` thay vì tự viết `a < b ? -1 : a > b ? 1 : 0` khi cần thứ tự giống `Double`.

### 8.4. Tránh quan hệ thứ tự không nhất quán với `equals`

Một `record` có ba component có thể có `equals` so cả ba component. Nếu comparator chỉ so một component, hai đối tượng khác nhau theo `equals` có thể bị coi là một phần tử trong `TreeSet`.

Nếu mục đích là giữ **mọi record khác nhau**, thêm tiêu chí phụ cho đủ những trường định danh. Nếu mục đích là gộp theo nhóm, hãy xác định một cấu trúc dữ liệu khác phù hợp: ví dụ `TreeMap<GroupKey, List<Record>>` để giữ nhiều bản ghi trong cùng nhóm, thay vì dựa vào hiện tượng mất phần tử của `TreeSet`.

## 9. Lỗi với khóa/phần tử có thể thay đổi

Giả sử một đối tượng `Employee` có trường `rank` mutable và comparator sắp theo `rank`:

```java
final class Employee {
    final String id;
    int rank;

    Employee(String id, int rank) {
        this.id = id;
        this.rank = rank;
    }
}
```

Nếu đối tượng đang ở trong `TreeSet<Employee>` mà `rank` thay đổi, cây **không tự sắp xếp lại**. Các thao tác `contains`, `remove` hoặc duyệt theo thứ tự có thể cho kết quả bất ngờ. Đây là vấn đề thiết kế, không phải nghĩa vụ của collection phải phát hiện và di chuyển node sau khi trường thay đổi.

Một giải pháp là **tách dữ liệu và khóa thứ tự**:

```java
record EmployeeRank(int rank, String employeeId)
        implements Comparable<EmployeeRank> {

    @Override
    public int compareTo(EmployeeRank other) {
        int byRank = Integer.compare(rank, other.rank());
        return byRank != 0
                ? byRank
                : employeeId.compareTo(other.employeeId());
    }
}
```

`EmployeeRank` là record bất biến nếu các component là `int` và `String`, nên giá trị so sánh không tự thay đổi. Khi nhân viên đổi hạng, hãy xóa **khóa cũ** và thêm **khóa mới** vào cây.

## 10. `null`, lỗi kiểu và các ngoại lệ thường gặp

| Tình huống | Kết quả cần hiểu |
| --- | --- |
| Thêm `null` vào `TreeSet` dùng natural ordering | Bị từ chối với `NullPointerException` |
| Đặt khóa `null` vào `TreeMap` dùng natural ordering | Bị từ chối với `NullPointerException` |
| Dùng comparator chấp nhận `null` | Có thể cho phép `null` làm phần tử hoặc khóa; cần xử lý hệ quả của các API trả `null` |
| Thêm đối tượng không so sánh được với những phần tử/khóa hiện có | Có thể ném `ClassCastException` |
| Gọi `first()` / `last()` trên `TreeSet` rỗng | `NoSuchElementException` |
| Gọi `firstKey()` / `lastKey()` trên `TreeMap` rỗng | `NoSuchElementException` |
| Dùng view để chèn phần tử/khóa ngoài khoảng | `IllegalArgumentException` |
| Gọi `addFirst` / `addLast` trên `TreeSet` | `UnsupportedOperationException` vì không hỗ trợ chèn theo vị trí |

Không nên dựa vào collection để “tự sửa” dữ liệu sai kiểu hoặc trùng khóa. Dùng generics để mô tả kiểu dữ liệu rõ ràng; xác minh và chuẩn hóa đầu vào trước khi chèn.

**Lưu ý về `null` trong map:** `TreeMap` có thể cho phép **giá trị** `null`, khác với điều kiện của **khóa**. Nếu dùng `get(key)` và nhận `null`, điều đó có thể là khóa không tồn tại *hoặc* khóa ánh xạ tới giá trị `null`.

## 11. Độ phức tạp, bộ nhớ và chọn collection đúng việc

`TreeMap` trong Java SE là cấu trúc cây tìm kiếm cân bằng kiểu **red-black tree**; `TreeSet` được triển khai dựa trên `TreeMap`. Nhờ tính cân bằng, các thao tác cơ bản có chi phí theo logarit số phần tử.

| Thao tác | `TreeSet` / `TreeMap` | Ghi chú |
| --- | --- | --- |
| Thêm, xóa, tìm một khóa/phần tử | `O(log n)` | Bảo đảm cho các thao tác cơ bản do API mô tả |
| Tìm láng giềng như `floor`/`ceiling` | Đi theo thứ tự cây | Tận dụng khả năng điều hướng |
| Duyệt toàn bộ theo thứ tự | `O(n)` cho việc duyệt các phần tử/entry | Không cần gọi `sort` mỗi lần |
| Bộ nhớ bổ sung | `O(n)` cho cấu trúc lưu dữ liệu | Có chi phí node và liên kết cây |
| Tra cứu băm trung bình | `HashSet`/`HashMap` thường gần `O(1)` | Không có thứ tự sắp xếp |

Tuy cây giúp dữ liệu luôn có thứ tự, nó không tự làm mọi việc “nhanh hơn” một hash-based collection. Với bảng tra cứu ID thông thường, ưu tiên `HashMap` khi thứ tự khóa không cần thiết.

**Khi dùng cây:** Bài toán cần tìm bản ghi gần ngưỡng, chọn khoảng thời gian, duyệt theo thứ tự ưu tiên, hoặc duy trì danh sách có thứ tự trong khi dữ liệu liên tục được thêm/xóa.

**Khi không cần cây:** Chỉ kiểm tra membership, đếm số phần tử duy nhất, hoặc tra cứu khóa chính không quan tâm thứ tự. Khi đó các collection băm có thể phù hợp hơn.

## 12. Đồng thời: `TreeSet` và `TreeMap` không tự đồng bộ

Hai lớp này không cung cấp bảo đảm thread-safe cho việc cập nhật đồng thời mà không có cơ chế điều phối thích hợp.

Nếu nhiều luồng cùng truy cập một `TreeSet`/`TreeMap` và có ít nhất một luồng sửa, cần chiến lược đồng bộ hóa phù hợp (ví dụ bảo vệ toàn bộ quy trình bằng lock, hoặc dùng collection đồng thời được thiết kế riêng).

Một số lựa chọn hiện hành khi cần **concurrent sorted/navigable collections**:

- `ConcurrentSkipListSet`: tập có thứ tự và hỗ trợ thao tác đồng thời.
- `ConcurrentSkipListMap`: map có thứ tự hỗ trợ thao tác đồng thời.

Những lớp đó có semantics về iterator, snapshot, tính nhất quán và giới hạn `null` riêng; không thể hoán đổi chúng với `TreeSet`/`TreeMap` mà không đọc hợp đồng của từng lớp.

Iterator của `TreeSet`/`TreeMap` có cơ chế *fail-fast* mang tính **best effort** khi bị thay đổi cấu trúc ngoài iterator; **không** được dùng việc ném `ConcurrentModificationException` như một biện pháp đồng bộ hóa hoặc bảo đảm tính đúng đắn.

## 13. Chương trình Java 27 hoàn chỉnh

Ví dụ dưới đây cho thấy một `TreeSet` của ticket với thứ tự do comparator xác định, cùng một `TreeMap` hỗ trợ tra cứu theo khoảng và lấy láng giềng.

Tạo file `SortedCollectionsDemo.java`:

```java
import java.util.Comparator;
import java.util.NavigableMap;
import java.util.NavigableSet;
import java.util.TreeMap;
import java.util.TreeSet;

public class SortedCollectionsDemo {

    record Ticket(String id, int priority) {}

    public static void main(String[] args) {
        Comparator<Ticket> order =
                Comparator.comparingInt(Ticket::priority)
                          .thenComparing(Ticket::id);

        NavigableSet<Ticket> queue = new TreeSet<>(order);
        queue.add(new Ticket("T-02", 1));
        queue.add(new Ticket("T-01", 1));
        queue.add(new Ticket("T-03", 2));
        queue.add(new Ticket("T-01", 1));

        System.out.println("Tickets:");
        for (Ticket ticket : queue) {
            System.out.println(ticket.id() + ": " + ticket.priority());
        }

        NavigableMap<Integer, String> levels = new TreeMap<>();
        levels.put(10, "basic");
        levels.put(20, "standard");
        levels.put(30, "premium");

        System.out.println("Keys: " + levels.navigableKeySet());
        System.out.println("Floor 25: " + levels.floorKey(25));
        System.out.println("Ceiling 25: " + levels.ceilingKey(25));
        System.out.println("Range: " + levels.subMap(10, true, 30, false));

        var descending = levels.descendingMap();
        System.out.println("Descending keys: " + descending.navigableKeySet());
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 SortedCollectionsDemo.java
java SortedCollectionsDemo
```

Kết quả:

```text
Tickets:
T-01: 1
T-02: 1
T-03: 2
Keys: [10, 20, 30]
Floor 25: 20
Ceiling 25: 30
Range: {10=basic, 20=standard}
Descending keys: [30, 20, 10]
```

Giải thích:

1. `Comparator.comparingInt(...).thenComparing(...)` chọn ticket theo mức ưu tiên tăng dần; nếu trùng mức ưu tiên, dùng ID để xác định thứ tự.
2. Ticket `T-01` được thêm hai lần nhưng không làm tăng số lượng phần tử vì comparator trả về `0` khi so với ticket đã có cùng ID và priority.
3. `TreeMap` tổ chức các mức `10`, `20`, `30` theo natural ordering của `Integer`.
4. `floorKey(25)` tìm mức gần nhất **không vượt quá** `25`, còn `ceilingKey(25)` tìm mức gần nhất **không nhỏ hơn** `25`.
5. `subMap(10, true, 30, false)` cho view của các mức từ `10` đến trước `30`.
6. `descendingMap()` cho view thứ tự ngược, không tạo một bản sao độc lập và không sửa dữ liệu gốc.

## 14. Bảng lỗi thường gặp và hướng sửa

| Cách viết/giả định | Vấn đề | Cách phù hợp |
| --- | --- | --- |
| Cho `Comparator.comparingInt(Ticket::priority)` vào `TreeSet<Ticket>` | Các ticket cùng priority bị coi là trùng | Thêm `thenComparing(Ticket::id)` nếu ID xác định đối tượng riêng |
| Viết `(a, b) -> a - b` | Có thể tràn số và đảo thứ tự | Dùng `Integer.compare` |
| Mặc định `compare(a,b)==0` luôn có nghĩa `a.equals(b)` | Không đúng với comparator tùy ý và một số kiểu chuẩn | Xác định hợp đồng bình đẳng, document khi không nhất quán |
| Sửa trường dùng để so sánh khi phần tử đang trong cây | Cây không tự tổ chức lại | Dùng khóa bất biến; xóa và chèn lại |
| Coi `subSet`/`subMap` là snapshot | Thay đổi view ảnh hưởng cấu trúc gốc | Chủ động tạo collection mới khi cần bản sao |
| Coi thứ tự `TreeSet` là thứ tự chèn | Cây duyệt theo quy tắc so sánh | Dùng cấu trúc theo thứ tự chèn nếu đó mới là yêu cầu |
| Coi `HashMap` và `TreeMap` có cùng chi phí cơ bản | Một bên băm, một bên cây cân bằng | Chọn theo yêu cầu ordering và tra cứu |
| Thêm `null` với natural ordering | Không so sánh được `null` | Dùng khóa không `null`; comparator nullable chỉ khi cần |
| Dùng `TreeSet.addFirst` để ưu tiên chèn | Không hỗ trợ định vị theo ý muốn | Chọn thứ tự comparator hoặc cấu trúc khác |
| Đọc `TreeMap.get(k)==null` là “không có khóa” | Có thể tồn tại khóa ánh xạ tới `null` | Dùng `containsKey` khi cần phân biệt |
| Dựa vào fail-fast iterator để an toàn đa luồng | Fail-fast chỉ best effort | Thiết kế đồng bộ hóa hoặc concurrent sorted collection |
| Cho rằng `String` tự nhiên sắp theo quy tắc tiếng Việt | Natural order không tự áp dụng locale | Dùng chiến lược collation phù hợp khi mục tiêu là hiển thị theo ngôn ngữ, đồng thời cân nhắc hệ quả về tính nhất quán với `equals` |

## 15. Checklist thiết kế cho bài toán thực tế

Trước khi dùng `TreeSet` hoặc `TreeMap`, hãy tự trả lời:

1. **Có thật sự cần dữ liệu được duy trì theo thứ tự?** Nếu không, hash-based collection thường đơn giản và hiệu quả hơn.
2. **Thứ tự tự nhiên có ý nghĩa không?** Nếu có, dùng `Comparable`; nếu cần nhiều thứ tự, dùng `Comparator`.
3. **Tiêu chí nào xác định trùng lặp?** Nhớ rằng cây dùng kết quả so sánh `0`, không chỉ `equals`.
4. **Có cần tiêu chí phụ để phân biệt phần tử/khóa?** Cân nhắc `thenComparing` cho các thuộc tính định danh còn thiếu.
5. **So sánh có nhất quán, bắc cầu và ổn định không?** Tránh trừ số, thời gian hiện tại và tác dụng phụ.
6. **Phần tử/khóa có mutable không?** Giữ các thành phần so sánh bất biến trong thời gian nằm trong cây.
7. **Có cần tìm láng giềng hoặc vùng giá trị không?** Dùng `lower`, `floor`, `ceiling`, `higher` và các range view.
8. **View có bị thay đổi ngoài ý muốn không?** `subSet`/`subMap` và view đảo chiều được hỗ trợ bởi collection gốc.
9. **Có dữ liệu `null` hoặc không so sánh được không?** Định nghĩa hợp đồng đầu vào rõ ràng.
10. **Có truy cập đồng thời không?** Chọn cơ chế đồng bộ hoặc `ConcurrentSkipListSet`/`ConcurrentSkipListMap` khi phù hợp.

**Ghi nhớ:** `Comparable` cho kiểu một thứ tự tự nhiên; `Comparator` cho collection một quy tắc thứ tự; `TreeSet` dùng quy tắc đó để vừa **sắp xếp** vừa **loại trùng**; `TreeMap` dùng quy tắc đó để vừa **sắp xếp khóa** vừa **xác định khóa tương đương**.

## 16. Tài liệu chính thức của Java SE 27

- [`TreeSet<E>` — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/TreeSet.html): ordering, hợp đồng `Set`, độ phức tạp, phương thức điều hướng và range views.
- [`TreeMap<K,V>` — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/TreeMap.html): red-black tree, cách so sánh khóa, thời gian `O(log n)` và các thao tác map.
- [`Comparable<T>` — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/Comparable.html): natural ordering và các yêu cầu đối với `compareTo`.
- [`Comparator<T>` — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/Comparator.html): `compare`, `comparing`, `thenComparing`, `reversed`, `nullsFirst`/`nullsLast`.
- [`NavigableSet<E>` — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/NavigableSet.html): `lower`, `floor`, `ceiling`, `higher`, `subSet` và `descendingSet`.
- [`NavigableMap<K,V>` — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/NavigableMap.html): tra cứu láng giềng, các view có thứ tự và `subMap`.
- [`BigDecimal` — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/math/BigDecimal.html): khác biệt được ghi nhận giữa `compareTo` và `equals`.
- [`ConcurrentSkipListSet` — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/ConcurrentSkipListSet.html) và [`ConcurrentSkipListMap`](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/ConcurrentSkipListMap.html): lựa chọn hiện đại khi cần collection có thứ tự hỗ trợ thao tác đồng thời.
