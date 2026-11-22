# Thu thập thành `Set` và hiểu ngữ nghĩa loại trùng

Trong Java Stream API, `collect` là terminal operation biến một pipeline khai báo thành kết quả cụ thể. Khi bài toán cần **các giá trị duy nhất**, `Set` là cấu trúc dữ liệu thường được chọn. Tuy nhiên, “duy nhất” phải được hiểu theo đúng hợp đồng so sánh của từng loại `Set`; thứ tự phần tử, khả năng chỉnh sửa và khả năng xử lý `null` cũng phụ thuộc cách thu thập.

Bài này thuộc chương **Thu thập thành Collection** của module **JAVA_STREAM_API**. Trọng tâm là `Collectors.toSet()`, `Collectors.toCollection(...)`, `Collectors.toUnmodifiableSet()`, quy tắc `equals`/`hashCode`, cách chọn `HashSet`, `LinkedHashSet` và `TreeSet`, cũng như khác biệt giữa `distinct()` và thu thập vào `Set`. Các ví dụ kết hợp `filter`, `map`, `collect`, `groupingBy` và stream song song; đồng thời chỉ ra giới hạn về trạng thái, tài nguyên và hiệu năng.

## 1. Thu thập thành `Set` bằng `Collectors.toSet()`

Giả sử danh sách đầu vào có các mã kỹ năng bị lặp:

```java
import java.util.List;
import java.util.Set;
import java.util.stream.Collectors;

List<String> skills = List.of("Java", "SQL", "Java", "Git", "SQL");

Set<String> unique = skills.stream()
        .collect(Collectors.toSet());

System.out.println(unique.size());                  // 3
System.out.println(unique.contains("Java"));        // true
System.out.println(unique.contains("SQL"));         // true
System.out.println(unique.contains("Git"));         // true
```

Đầu vào có năm phần tử nhưng `Set` kết quả chỉ còn ba giá trị khác nhau. **Không nên khẳng định thứ tự khi in `unique`**: `Collectors.toSet()` không bảo đảm kiểu triển khai hay thứ tự duyệt phần tử.

Pipeline có ba phần:

1. `skills.stream()` tạo nguồn từ danh sách, có encounter order theo vị trí phần tử.
2. Các intermediate operation tùy chọn như `filter` hoặc `map` mô tả việc lọc và chuyển đổi.
3. `collect(Collectors.toSet())` tiêu thụ stream, tích lũy vào một `Set` và loại các phần tử trùng theo quy tắc của `Set` được tạo.

Nếu cần kết hợp thao tác khác:

```java
Set<String> normalized = List.of(" Java ", "SQL", "Java", " Git ").stream()
        .map(String::trim)
        .map(String::toLowerCase)
        .collect(Collectors.toSet());

System.out.println(normalized.equals(Set.of("java", "sql", "git"))); // true
```

Đây là cách loại trùng **sau khi chuẩn hóa**. Nếu hai giá trị chỉ khác khoảng trắng hoặc chữ hoa thường nhưng ứng dụng muốn xem là cùng một mã, hãy chuẩn hóa trước khi thu thập.

### 1.1. `toSet()` bảo đảm điều gì, và không bảo đảm điều gì?

| Thuộc tính | Hợp đồng của `Collectors.toSet()` |
|---|---|
| Số phần tử | Mỗi giá trị tương đương theo quy tắc của `Set` xuất hiện tối đa một lần |
| Kiểu trả về | `Set<T>` |
| Kiểu triển khai cụ thể | **Không được bảo đảm**, không giả định luôn là `HashSet` |
| Thứ tự duyệt phần tử | **Không được bảo đảm**, dù nguồn là `List` có thứ tự |
| Khả năng chỉnh sửa kết quả | **Không được bảo đảm** bởi hợp đồng collector |
| Khả năng tuần tự hóa hoặc thread safety | **Không được bảo đảm** |
| Đặc tính collector | `UNORDERED`; không có cam kết giữ encounter order |

Nếu ứng dụng cần một kiểu `Set` cụ thể hoặc chính sách thứ tự cụ thể, chọn `Collectors.toCollection(supplier)` thay vì dựa vào một chi tiết triển khai của `toSet()`.

## 2. “Trùng” nghĩa là gì? `equals` và `hashCode`

Với các `Set` dựa trên hash như `HashSet` và `LinkedHashSet`, tính duy nhất dựa vào `equals` và `hashCode` của phần tử. Hai đối tượng có dữ liệu nhìn giống nhau chưa chắc được xem là bằng nhau.

```java
import java.util.List;
import java.util.Set;
import java.util.stream.Collectors;

Set<String> names = List.of("Java", "Java", "java").stream()
        .collect(Collectors.toSet());

System.out.println(names.size()); // 2
```

`String.equals` phân biệt chữ hoa và chữ thường: `"Java"` bằng `"Java"`, nhưng không bằng `"java"`. Thu thập vào `Set` **không tự động chuẩn hóa** dữ liệu.

### 2.1. `equals` và `hashCode` phải nhất quán

Với những phần tử dùng trong hash-based `Set`, hợp đồng quan trọng là:

- `equals` cần có tính phản xạ, đối xứng, bắc cầu và nhất quán khi trạng thái so sánh không thay đổi.
- Nếu `a.equals(b)` là `true` thì `a.hashCode() == b.hashCode()` phải đúng.
- Hai đối tượng có cùng `hashCode` **không nhất thiết** bằng nhau; hash collision được phép xảy ra.
- Nếu ghi đè `equals`, phải ghi đè `hashCode` tương ứng; nếu không, `HashSet` có thể không phát hiện trùng đúng cách.

Một `record` mặc định có `equals` và `hashCode` xét **tất cả thành phần**:

```java
record Employee(long id, String name) {}

Set<Employee> employees = List.of(
        new Employee(1, "An"),
        new Employee(1, "An"),
        new Employee(1, "An Nguyễn")
).stream().collect(Collectors.toSet());

System.out.println(employees.size()); // 2
```

Trong ví dụ, bản ghi thứ nhất và thứ hai bằng nhau vì mọi thành phần đều bằng nhau. Bản ghi thứ ba khác `name`, nên vẫn là phần tử riêng, mặc dù có cùng `id`.

**Quy tắc loại trùng là quy tắc miền dữ liệu**, không phải chỉ việc gọi `toSet()`. Muốn định nghĩa “hai nhân viên cùng mã id là một người”, ta phải biểu diễn hoặc triển khai tiêu chí đó một cách tường minh.

### 2.2. Tùy chỉnh ngữ nghĩa bằng đối tượng có khóa định danh

Ví dụ một kiểu dữ liệu chỉ xác định danh tính theo `id`:

```java
import java.util.Objects;

final class Customer {
    private final long id;
    private final String name;

    Customer(long id, String name) {
        this.id = id;
        this.name = name;
    }

    long id() { return id; }
    String name() { return name; }

    @Override
    public boolean equals(Object other) {
        if (this == other) return true;
        if (!(other instanceof Customer customer)) return false;
        return id == customer.id;
    }

    @Override
    public int hashCode() {
        return Long.hashCode(id);
    }

    @Override
    public String toString() {
        return "Customer[" + id + ", " + name + "]";
    }
}
```

Với kiểu này, `new Customer(1, "An")` và `new Customer(1, "An cập nhật")` được coi là bằng nhau theo `id`. Thu thập bằng `toSet()` sẽ không giữ cả hai. **Không được suy rằng bản ghi tên cũ hay mới luôn là bản ghi được giữ** từ một collector unordered, đặc biệt trong stream song song.

Trong thực tế, chỉ ghi đè `equals`/`hashCode` theo `id` nếu điều đó phù hợp với ý nghĩa danh tính của class ở mọi nơi. Nếu bài toán chỉ muốn đếm các `id` duy nhất, cách rõ ràng hơn là:

```java
Set<Long> ids = List.of(
        new Employee(1, "An"),
        new Employee(1, "An cập nhật"),
        new Employee(2, "Bình")
).stream()
 .map(Employee::id)
 .collect(Collectors.toSet());

System.out.println(ids.equals(Set.of(1L, 2L))); // true
```

### 2.3. Không thay đổi khóa hash khi phần tử đang ở trong `Set`

Nếu `equals` và `hashCode` sử dụng một thuộc tính mutable, việc sửa thuộc tính đó sau khi đưa phần tử vào `HashSet` có thể khiến `contains` hoặc `remove` hoạt động khó dự đoán, vì phần tử đã nằm trong bucket theo hash cũ. Ưu tiên khóa bất biến: `record`, trường `final` hoặc dữ liệu không bị thay đổi trong thời gian phần tử thuộc tập hợp.

## 3. Chọn `HashSet`, `LinkedHashSet` hay `TreeSet`

`Set` là giao diện. Cách tạo và quy tắc của cấu trúc cụ thể quyết định thứ tự và chiến lược nhận biết phần tử trùng:

| Loại `Set` | Quy tắc duy nhất | Thứ tự duyệt | Trường hợp điển hình |
|---|---|---|---|
| `HashSet` | `equals`/`hashCode` | Không bảo đảm | Tra cứu giá trị, kiểm tra thành viên |
| `LinkedHashSet` | `equals`/`hashCode` | Theo thứ tự thêm phần tử | Loại trùng nhưng cần giữ thứ tự gặp đầu tiên |
| `TreeSet` | So sánh theo `compareTo` hoặc `Comparator`; `compare(...) == 0` nghĩa là trùng | Theo thứ tự sắp xếp | Tập giá trị duy nhất có thứ tự tăng dần/quy tắc riêng |

`Collectors.toCollection` cho phép **chỉ định supplier tạo collection**:

```java
import java.util.HashSet;
import java.util.LinkedHashSet;
import java.util.TreeSet;
import java.util.Set;
import java.util.stream.Collectors;

List<Integer> source = List.of(4, 2, 4, 1, 3, 2);

HashSet<Integer> hash = source.stream()
        .collect(Collectors.toCollection(HashSet::new));

LinkedHashSet<Integer> insertion = source.stream()
        .collect(Collectors.toCollection(LinkedHashSet::new));

TreeSet<Integer> sorted = source.stream()
        .collect(Collectors.toCollection(TreeSet::new));

System.out.println(insertion); // [4, 2, 1, 3]
System.out.println(sorted);    // [1, 2, 3, 4]
System.out.println(hash.size()); // 4; không dựa vào thứ tự in
```

Với stream nguồn `List` có thứ tự, `LinkedHashSet` lưu thứ tự thêm **lần đầu**. `TreeSet` đưa phần tử vào thứ tự tự nhiên của `Integer`. `HashSet` không có hợp đồng thứ tự dù việc in trên một JDK có thể trông ổn định.

### 3.1. Vì sao `Collectors.toCollection(LinkedHashSet::new)` khác `Collectors.toSet()`?

```java
List<String> events = List.of("open", "save", "open", "close", "save");

Set<String> firstSeenOrder = events.stream()
        .collect(Collectors.toCollection(LinkedHashSet::new));

System.out.println(firstSeenOrder); // [open, save, close]
```

Đây là lựa chọn khi nghiệp vụ cần “các sự kiện duy nhất theo thứ tự xuất hiện lần đầu”. `Collectors.toSet()` chỉ bảo đảm tính duy nhất theo `Set`; nó là collector `UNORDERED`, không giữ lời hứa về thứ tự xuất hiện.

Với stream đã bị bỏ encounter order bằng `unordered()` hoặc nguồn vốn không có thứ tự như `HashSet`, `LinkedHashSet` vẫn có thứ tự chèn, nhưng không tự **khôi phục** một encounter order mà nguồn không cung cấp. Nếu muốn thứ tự toàn phần được xác định bởi giá trị, hãy sắp xếp hoặc dùng `TreeSet` với comparator phù hợp.

### 3.2. `TreeSet` có một khái niệm “trùng” khác

`TreeSet` dùng kết quả so sánh để quyết định phần tử tương đương. Chẳng hạn, bộ so sánh không phân biệt hoa thường:

```java
import java.util.TreeSet;
import java.util.stream.Collectors;

TreeSet<String> tokens = Stream.of("Java", "JAVA", "sql", "SQL")
        .collect(Collectors.toCollection(
                () -> new TreeSet<>(String.CASE_INSENSITIVE_ORDER)
        ));

System.out.println(tokens.size()); // 2
```

Hai chuỗi `"Java"` và `"JAVA"` khác nhau theo `String.equals`, nhưng comparator trả `0`, nên `TreeSet` coi chúng là một nhóm tương đương. Phần tử đại diện được giữ phụ thuộc vào phần tử được thêm trước; không diễn giải kết quả là “chọn dạng chữ chuẩn nhất”. Nếu cần dạng chuẩn, dùng `map(String::toLowerCase)` hoặc quy tắc chuẩn hóa rõ ràng trước khi thu thập.

Với sorted set, comparator hoặc natural ordering **nên nhất quán với `equals`** nếu muốn thực hiện đầy đủ hợp đồng chung của `Set`. Dùng comparator không nhất quán có thể hợp lệ cho một nhu cầu sắp xếp cụ thể nhưng gây bất ngờ khi so sánh, trao đổi hoặc xử lý các loại `Set` khác nhau.

Một ví dụ kinh điển:

```java
import java.math.BigDecimal;
import java.util.TreeSet;

BigDecimal a = new BigDecimal("1.0");
BigDecimal b = new BigDecimal("1.00");

System.out.println(a.equals(b));    // false
System.out.println(a.compareTo(b)); // 0

Set<BigDecimal> hashBased = Stream.of(a, b)
        .collect(Collectors.toCollection(HashSet::new));
Set<BigDecimal> treeBased = Stream.of(a, b)
        .collect(Collectors.toCollection(TreeSet::new));

System.out.println(hashBased.size()); // 2
System.out.println(treeBased.size()); // 1
```

Đây là lý do phải xác định đúng **tiêu chí trùng** trước khi chọn loại `Set`.

## 4. `distinct()` và `collect(toSet())` có giống nhau không?

Cả hai đều liên quan loại trùng, nhưng ở **hai giai đoạn khác nhau**:

| Đặc điểm | `distinct()` | `collect(Collectors.toSet())` |
|---|---|---|
| Loại thao tác | Intermediate, stateful | Terminal |
| Kiểu dữ liệu sau thao tác | Vẫn là `Stream<T>` | Thành `Set<T>` |
| Tiếp tục `map`, `filter` được không? | Có | Không, stream đã tiêu thụ |
| Tiêu chí trùng | `Object.equals` | Theo loại `Set` mà collector dùng; với hash-based set là `equals`/`hashCode` |
| Thứ tự với nguồn có encounter order | Giữ phần tử xuất hiện **đầu tiên** | Không bảo đảm thứ tự |
| Bối cảnh dùng | Loại trùng giữa pipeline trước các bước tiếp theo | Thu được tập kết quả duy nhất ở cuối pipeline |

Ví dụ:

```java
List<String> labels = List.of("A", "B", "A", "C", "B");

List<String> orderedUnique = labels.stream()
        .distinct()
        .toList();
System.out.println(orderedUnique); // [A, B, C]

Set<String> uniqueSet = labels.stream()
        .collect(Collectors.toSet());
System.out.println(uniqueSet.size()); // 3; thứ tự không được bảo đảm
```

Khi stream **có encounter order**, `distinct()` giữ phần tử xuất hiện đầu tiên trong nhóm bằng nhau. Nếu cần đưa kết quả cuối vào `Set` mà vẫn giữ thứ tự lần đầu:

```java
LinkedHashSet<String> orderedSet = labels.stream()
        .collect(Collectors.toCollection(LinkedHashSet::new));
System.out.println(orderedSet); // [A, B, C]
```

Không bắt buộc thêm `distinct()` trước `toCollection(LinkedHashSet::new)`: bản thân `LinkedHashSet` đã loại trùng. Tuy nhiên, `distinct()` hữu ích nếu phải loại trùng **trước một thao tác trung gian tiếp theo** hoặc cần danh sách kết quả giữ thứ tự.

### 4.1. `sorted()` trước `toSet()` không bảo đảm thứ tự của `Set`

```java
Set<Integer> result = List.of(4, 1, 3, 2).stream()
        .sorted()
        .collect(Collectors.toSet());

System.out.println(result.size()); // 4
// Không khẳng định kết quả duyệt có thứ tự [1, 2, 3, 4].
```

Nếu cần một `Set` có thứ tự tăng dần, dùng:

```java
TreeSet<Integer> sortedUnique = List.of(4, 1, 3, 2).stream()
        .collect(Collectors.toCollection(TreeSet::new));
System.out.println(sortedUnique); // [1, 2, 3, 4]
```

Nếu cần danh sách có thứ tự tăng dần và không trùng, dùng `stream().distinct().sorted().toList()`. Lựa chọn cấu trúc kết quả theo cách bên gọi sẽ sử dụng dữ liệu.

## 5. Bản ghi nào được giữ khi trùng khóa?

Một câu hỏi thực tế là: “Nếu hai object bằng nhau theo `equals` nhưng chứa thông tin khác nhau, bản nào được giữ?” Với `Collectors.toSet()`, thứ tự và phần tử đại diện không được cam kết. Bản ghi được giữ có thể phụ thuộc collector, cách chia dữ liệu hoặc thứ tự xử lý.

Đối với nguồn có encounter order và yêu cầu lấy bản ghi **xuất hiện đầu tiên theo tiêu chí `equals`**, có thể dùng `distinct()` rồi thu vào `List`:

```java
List<Customer> customers = List.of(
        new Customer(1, "An cũ"),
        new Customer(1, "An mới"),
        new Customer(2, "Bình")
);

List<Customer> firstByEquality = customers.stream()
        .distinct()
        .toList();

System.out.println(firstByEquality);
// [Customer[1, An cũ], Customer[2, Bình]]
```

Trong ví dụ, `Customer` ở mục 2.2 có `equals` theo `id`; với `List.stream()` có thứ tự, `distinct()` giữ đại diện đầu tiên. **Đừng thay bằng `unordered().distinct()`** nếu tiêu chí “đầu tiên” quan trọng.

Nếu tiêu chí trùng chỉ là một trường nhưng class `equals` xét tất cả trường, `distinct()` không thể tự suy ra “trùng theo id”. Có thể sử dụng `toMap` với merge function rõ ràng:

```java
import java.util.LinkedHashMap;
import java.util.Map;

List<Employee> source = List.of(
        new Employee(1, "An cũ"),
        new Employee(1, "An mới"),
        new Employee(2, "Bình")
);

Map<Long, Employee> firstById = source.stream()
        .collect(Collectors.toMap(
                Employee::id,
                employee -> employee,
                (first, ignored) -> first,
                LinkedHashMap::new
        ));

System.out.println(firstById.get(1L)); // Employee[id=1, name=An cũ]
```

Ví dụ dùng nguồn có thứ tự; merge function `(first, ignored) -> first` nêu chính sách chọn giá trị theo thứ tự gặp phần tử. `LinkedHashMap` cung cấp thứ tự chèn của khóa trong kết quả. Nếu nghiệp vụ cần **bản ghi mới nhất theo thời gian**, hãy định nghĩa trường thời gian và quy tắc so sánh rõ ràng; không suy từ việc đối tượng “đến sau” trong một nguồn không có thứ tự.

## 6. Kết quả có thể chỉnh sửa hay không?

Một số API tạo `Set` bất biến hoặc không cho phép chỉnh sửa; đây là yêu cầu độc lập với chuyện loại trùng.

| Cách tạo | Hợp đồng quan trọng | Phiên bản Java |
|---|---|---|
| `Collectors.toSet()` | Không bảo đảm tính có thể sửa/kiểu cụ thể | Java 8+ |
| `Collectors.toCollection(HashSet::new)` | Kết quả là `HashSet` mutable | Java 8+ |
| `Collectors.toCollection(LinkedHashSet::new)` | Kết quả là `LinkedHashSet` mutable | Java 8+ |
| `Collectors.toUnmodifiableSet()` | Kết quả không thể sửa; không chấp nhận `null` | Java 10+ |
| `Set.copyOf(collection)` | Bản sao không thể sửa; không chấp nhận `null` | Java 10+ |
| `Set.of(elements...)` | Không thể sửa; `null` và phần tử trùng gây lỗi | Java 9+ |

### 6.1. `Collectors.toUnmodifiableSet()`

```java
Set<String> permissions = Stream.of("READ", "WRITE", "READ")
        .collect(Collectors.toUnmodifiableSet());

System.out.println(permissions.size()); // 2

// permissions.add("DELETE"); // Ném UnsupportedOperationException khi chạy.
```

Đừng nhầm `toUnmodifiableSet()` với `toSet()`: API thứ nhất **cam kết không thể chỉnh sửa**, API thứ hai không cam kết điều đó. `toUnmodifiableSet()` cũng là một collector unordered và khi các phần tử bằng nhau được đưa vào, nó không cam kết giữ đối tượng đại diện nào trong số các phần tử bằng nhau.

```java
// Có thể ném NullPointerException vì kết quả không cho phép null:
// Set<String> invalid = Stream.of("A", null)
//         .collect(Collectors.toUnmodifiableSet());
```

Nếu cần loại `null`, làm rõ ngay trong pipeline:

```java
import java.util.Objects;

Set<String> safe = Stream.of("A", null, "B", "A")
        .filter(Objects::nonNull)
        .collect(Collectors.toUnmodifiableSet());

System.out.println(safe.equals(Set.of("A", "B"))); // true
```

### 6.2. `Set.of` khác `Set.copyOf`

```java
Set<String> fixed = Set.of("A", "B");
Set<String> copy = Set.copyOf(List.of("A", "B", "A"));

System.out.println(fixed.size()); // 2
System.out.println(copy.size());  // 2

// Set.of("A", "A"); // IllegalArgumentException: trùng phần tử.
```

`Set.of` **từ chối phần tử trùng**, trong khi `Set.copyOf` **loại trùng** từ collection đầu vào. Với các đối tượng khác nhau nhưng `equals` trả `true`, `Set.copyOf` không cam kết giữ đại diện cụ thể nào. Cả hai loại tập không cho chỉnh sửa và không chấp nhận `null`.

### 6.3. Vừa giữ thứ tự thêm vừa không cho chỉnh sửa

Nếu cần một `Set` kết quả duyệt theo thứ tự đầu tiên và không cho bên gọi sửa, có thể xây dựng một `LinkedHashSet` mới rồi trả về bản bọc không thể chỉnh sửa:

```java
import java.util.Collections;
import java.util.LinkedHashSet;

Set<String> orderedReadOnly = List.of("B", "A", "B", "C").stream()
        .collect(Collectors.collectingAndThen(
                Collectors.toCollection(LinkedHashSet::new),
                Collections::unmodifiableSet
        ));

System.out.println(orderedReadOnly); // [B, A, C]
// orderedReadOnly.add("D"); // UnsupportedOperationException.
```

Ở đây collector tạo một `LinkedHashSet` mới không bị bên ngoài giữ tham chiếu, rồi trả về wrapper không cho chỉnh sửa. **Đây không phải deep immutability**: nếu các phần tử là object mutable, nội dung bên trong chúng vẫn có thể thay đổi; vì vậy nên thu thập dữ liệu bất biến khi phù hợp.

## 7. Xử lý `null` trước khi thu thập

`null` không phải giá trị nghiệp vụ hợp lệ trong nhiều hệ thống. Đừng phụ thuộc vào việc `Collectors.toSet()` hiện tại có thể đang tạo `HashSet` chấp nhận `null`: API không cam kết kiểu kết quả. `Collectors.toUnmodifiableSet()` từ chối `null`; `TreeSet` với natural ordering cũng không thể so sánh `null` theo cách thông thường.

```java
Set<String> labels = Stream.of("Java", null, "SQL", "Java")
        .filter(Objects::nonNull)
        .collect(Collectors.toSet());

System.out.println(labels.equals(Set.of("Java", "SQL"))); // true
```

Nếu `null` có ý nghĩa riêng (ví dụ “chưa phân loại”), nên chuyển thành một nhãn/giá trị miền dữ liệu rõ ràng:

```java
Set<String> categories = Stream.of("A", null, "B")
        .map(value -> value == null ? "UNCLASSIFIED" : value)
        .collect(Collectors.toSet());

System.out.println(categories.contains("UNCLASSIFIED")); // true
```

Quyết định này thuộc về yêu cầu nghiệp vụ: **bỏ `null`** và **thay `null` bằng một giá trị có nghĩa** là hai hành vi khác nhau.

## 8. Thu thập thành `Set` khi stream chạy song song

```java
Set<Integer> unique = List.of(1, 2, 2, 3, 1, 4)
        .parallelStream()
        .collect(Collectors.toSet());

System.out.println(unique.equals(Set.of(1, 2, 3, 4))); // true
```

`Collectors.toSet()` có thể sử dụng với `parallelStream()`. Stream framework xử lý việc tạo container tích lũy cục bộ và kết hợp các phần kết quả theo hợp đồng collector. Điều đó **không có nghĩa `Set` trả về là thread-safe**, và cũng không có nghĩa nên chia sẻ một `HashSet` bên ngoài với nhiều thread.

### 8.1. Sai lầm: dùng `forEach` để tự thêm vào `HashSet` chung

```java
import java.util.HashSet;

Set<Integer> target = new HashSet<>();

// Không an toàn:
// List.of(1, 2, 3, 4).parallelStream().forEach(target::add);
```

`HashSet` không bảo đảm thao tác thêm từ nhiều thread đồng thời là an toàn. Dữ liệu có thể bị race, thiếu phần tử hoặc trạng thái nội bộ bị ảnh hưởng. Dùng `collect(Collectors.toSet())` để framework quản lý quá trình tích lũy.

### 8.2. `UNORDERED` không đồng nghĩa `CONCURRENT`

Hai khái niệm khác nhau:

- **`UNORDERED`**: collector không cam kết thứ tự phần tử trong kết quả.
- **`CONCURRENT`**: collector cho phép nhiều thread đồng thời tích lũy vào cùng container kết quả trong các điều kiện do hợp đồng collector quy định.

`Collectors.toSet()` là collector `UNORDERED`; không có cam kết là collector `CONCURRENT`. Việc `parallelStream().collect(toSet())` chạy hợp lệ không cho phép tự ý gọi `add` trên một `HashSet` chung từ nhiều thread.

Nếu bắt buộc có cấu trúc dữ liệu đồng thời với nhiều luồng bên ngoài tự cập nhật, cần thiết kế riêng cơ chế đồng bộ hoặc cấu trúc thread-safe phù hợp. Đối với một pipeline thu thập kết quả đơn thuần, collector thường là lựa chọn đơn giản và ít lỗi hơn.

### 8.3. Giữ thứ tự khi song song có thể tăng chi phí

Với `LinkedHashSet` hoặc `distinct()` trên stream có thứ tự, duy trì thứ tự gặp đầu tiên có thể tốn chi phí phối hợp khi chạy song song. Nếu nghiệp vụ không yêu cầu thứ tự, `toSet()` cho phép framework có thêm lựa chọn thực thi. **Không mặc định collector unordered luôn nhanh hơn**: kết quả đo phụ thuộc dữ liệu, va chạm hash, kích thước tập, số thread và chi phí tạo/kết hợp các container.

## 9. Kết hợp `groupingBy` với `toSet()`

Một ứng dụng phổ biến là nhóm dữ liệu rồi lấy các giá trị duy nhất trong từng nhóm. Ví dụ mỗi nhóm học có nhiều đăng ký môn học, trong đó có thể trùng:

```java
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;

record Enrollment(String group, String course) {}

List<Enrollment> registrations = List.of(
        new Enrollment("A", "Java"),
        new Enrollment("A", "SQL"),
        new Enrollment("A", "Java"),
        new Enrollment("B", "Git"),
        new Enrollment("B", "SQL")
);

Map<String, Set<String>> coursesByGroup = registrations.stream()
        .collect(Collectors.groupingBy(
                Enrollment::group,
                Collectors.mapping(
                        Enrollment::course,
                        Collectors.toSet()
                )
        ));

System.out.println(coursesByGroup.get("A").equals(Set.of("Java", "SQL")));
// true
System.out.println(coursesByGroup.get("B").equals(Set.of("Git", "SQL")));
// true
```

`groupingBy` quyết định khóa nhóm, `mapping` lấy trường `course`, còn `toSet()` loại trùng **bên trong từng nhóm**. `Map` được tạo bởi overload `groupingBy` mặc định cũng không cam kết thứ tự duyệt khóa.

Nếu phải giữ thứ tự đăng ký đầu tiên của từng môn trong nhóm, có thể thay downstream collector bằng:

```java
Map<String, LinkedHashSet<String>> orderedCoursesByGroup =
        registrations.stream().collect(Collectors.groupingBy(
                Enrollment::group,
                Collectors.mapping(
                        Enrollment::course,
                        Collectors.toCollection(LinkedHashSet::new)
                )
        ));

System.out.println(orderedCoursesByGroup.get("A")); // [Java, SQL]
```

Nguồn `registrations` là `List` có encounter order. Nếu còn yêu cầu thứ tự các khóa nhóm, cần chỉ định `mapFactory` của `groupingBy`, ví dụ `LinkedHashMap::new`; việc chọn downstream `LinkedHashSet` chỉ áp dụng cho **giá trị trong nhóm**.

## 10. Giới hạn hiệu năng, bộ nhớ và vòng đời

Việc thu thập thành `Set` cần lưu những giá trị duy nhất trong bộ nhớ. Với nguồn hữu hạn có `n` phần tử và `u` phần tử duy nhất:

- Với hash-based `Set`, thời gian thêm phần tử trung bình thường gần `O(n)` tổng cộng khi phân bố hash tốt; trường hợp xấu, va chạm hash và chi phí `equals` có thể làm chậm đáng kể.
- `TreeSet` thường tốn khoảng `O(n log u)` để thêm `n` phần tử, đổi lại có thứ tự so sánh.
- Bộ nhớ cho kết quả phụ thuộc khoảng `u` phần tử cùng cấu trúc dữ liệu, không chỉ số lượng `n`. Trong xử lý song song có thể tồn tại thêm các container và bộ đệm trung gian.
- `toSet()` không tự đóng tài nguyên của nguồn và không phải terminal operation ngắn mạch: nó cần duyệt nguồn hữu hạn đến khi hết.

Với stream vô hạn, không gọi `collect(toSet())` trực tiếp vì terminal operation có thể không kết thúc, ngay cả nếu phần tử được sinh lặp đi lặp lại:

```java
// Không chạy:
// Set<Integer> forever = Stream.generate(() -> 1)
//         .collect(Collectors.toSet());

Set<Integer> sample = Stream.generate(() -> 1)
        .limit(100)
        .collect(Collectors.toSet());

System.out.println(sample.equals(Set.of(1))); // true
```

Với nguồn gắn tài nguyên, ví dụ `Files.lines(path)`, dùng `try-with-resources`:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

static Set<String> readUniqueLines(Path path) throws IOException {
    try (Stream<String> lines = Files.lines(path)) {
        return lines
                .map(String::trim)
                .filter(s -> !s.isEmpty())
                .collect(Collectors.toSet());
    }
}
```

Sau một terminal operation `collect`, không được tiêu thụ lại cùng đối tượng `Stream`; muốn thu thập kiểu khác, tạo stream mới từ nguồn có thể đọc lại. Không dùng `peek` hay accumulator có side effect để thay thế việc thu thập: code tích lũy vào `Set` có cơ chế rõ ràng hơn và tránh thay đổi trạng thái bên ngoài trong pipeline.

## 11. Chương trình tổng hợp có thể chạy (Java 17+)

Ví dụ độc lập dưới đây minh họa `toSet`, `toCollection`, `toUnmodifiableSet`, phân biệt các kiểu `Set` và loại trùng theo khóa:

```java
import java.util.HashSet;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.TreeSet;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class CollectToSetDemo {
    record Employee(long id, String name) {}
    record Enrollment(String group, String course) {}

    public static void main(String[] args) {
        List<String> input = List.of("Java", "SQL", "Java", "Git", "SQL");

        Set<String> anyOrder = input.stream().collect(Collectors.toSet());
        System.out.println(anyOrder.equals(Set.of("Java", "SQL", "Git"))); // true

        LinkedHashSet<String> insertion = input.stream()
                .collect(Collectors.toCollection(LinkedHashSet::new));
        System.out.println(insertion); // [Java, SQL, Git]

        TreeSet<String> sorted = input.stream()
                .collect(Collectors.toCollection(TreeSet::new));
        System.out.println(sorted); // [Git, Java, SQL]

        Set<String> readOnly = Stream.of("A", null, "A", "B")
                .filter(Objects::nonNull)
                .collect(Collectors.toUnmodifiableSet());
        System.out.println(readOnly.equals(Set.of("A", "B"))); // true

        List<Employee> employees = List.of(
                new Employee(1, "An"),
                new Employee(1, "An cập nhật"),
                new Employee(2, "Bình")
        );
        Set<Long> ids = employees.stream()
                .map(Employee::id)
                .collect(Collectors.toSet());
        System.out.println(ids.equals(Set.of(1L, 2L))); // true

        List<Enrollment> registrations = List.of(
                new Enrollment("A", "Java"),
                new Enrollment("A", "Java"),
                new Enrollment("A", "SQL"),
                new Enrollment("B", "Git")
        );
        Map<String, Set<String>> groups = registrations.stream()
                .collect(Collectors.groupingBy(
                        Enrollment::group,
                        Collectors.mapping(
                                Enrollment::course,
                                Collectors.toSet()
                        )
                ));
        System.out.println(groups.get("A").equals(Set.of("Java", "SQL")));
        // true

        Set<Integer> parallel = List.of(3, 1, 2, 3, 1).parallelStream()
                .collect(Collectors.toSet());
        System.out.println(parallel.equals(Set.of(1, 2, 3))); // true

        // Không suy ra thứ tự duyệt từ toSet(), kể cả khi nguồn là List.
    }
}
```

Chương trình không dựa vào thứ tự in của `HashSet` hoặc của kết quả `toSet()`; những kiểm tra ở đó sử dụng `Set.equals`, vì phép bằng nhau giữa các set phản ánh chính xác nội dung phần tử mà ứng dụng quan tâm.

## 12. Những lỗi thường gặp

| Cách hiểu hoặc đoạn mã | Vì sao có vấn đề? | Cách phù hợp |
|---|---|---|
| Gọi `toSet()` rồi mong giữ thứ tự `List` | Collector là `UNORDERED` | Dùng `toCollection(LinkedHashSet::new)` |
| Gọi `sorted().collect(toSet())` rồi mong set đã sắp | `Set` kết quả không cam kết thứ tự duyệt | Dùng `toCollection(TreeSet::new)` hoặc `distinct().sorted().toList()` |
| Hai object có cùng `id` phải tự động bị loại trùng | `equals` có thể xét các trường khác | Xác định danh tính theo id hoặc `map` sang id |
| Ghi đè `equals` nhưng quên `hashCode` | Vi phạm hợp đồng hash-based collection | Cài đặt nhất quán cả hai hoặc dùng `record` phù hợp |
| Tưởng `TreeSet` luôn loại trùng theo `equals` | `TreeSet` dựa vào comparator hoặc `compareTo` | Đánh giá `compare(...) == 0` và tính nhất quán với `equals` |
| Mong `Collectors.toSet()` luôn trả `HashSet` mutable | API không cam kết kiểu/khả năng chỉnh sửa | Dùng `toCollection(HashSet::new)` khi cần cụ thể |
| Dùng `toUnmodifiableSet()` với `null` | Collector từ chối `null` | `filter(Objects::nonNull)` hoặc định chính sách thay thế |
| Nghĩ `Set.of("A", "A")` sẽ loại trùng | Factory này ném `IllegalArgumentException` | Dùng `Set.copyOf` hoặc collector nếu muốn loại trùng |
| `parallelStream().forEach(sharedSet::add)` | `HashSet` dùng chung không an toàn luồng | Dùng `parallelStream().collect(toSet())` |
| Cho rằng `UNORDERED` nghĩa là `CONCURRENT` | Đây là hai đặc tính collector khác nhau | Đọc chính xác `Collector.Characteristics` |
| Thu thập nguồn vô hạn trực tiếp thành set | `collect` đợi nguồn hoàn tất | Giới hạn hữu hạn trước `collect` |
| Dùng `distinct()` trước `toSet()` ở mọi pipeline | Có thể tạo bước loại trùng dư thừa | Chỉ dùng khi cần loại trùng giữa pipeline hoặc cần chọn đại diện theo thứ tự |

## 13. Tự kiểm tra

1. **`List.of("a", "b", "a").stream().collect(Collectors.toSet()).size()` trả gì?** Trả `2`.
2. **`Collectors.toSet()` có cam kết tạo `HashSet` mutable không?** Không, kiểu triển khai và khả năng chỉnh sửa không được cam kết.
3. **Làm sao loại trùng nhưng giữ thứ tự xuất hiện đầu tiên của nguồn `List`?** `collect(Collectors.toCollection(LinkedHashSet::new))` hoặc `distinct().toList()` nếu cần `List`.
4. **Làm sao tạo set gồm các số tăng dần?** `collect(Collectors.toCollection(TreeSet::new))` khi phần tử có thứ tự tự nhiên phù hợp.
5. **Hai record `Employee(1, "An")` và `Employee(1, "An mới")` có bị loại trùng mặc định không?** Không, vì `record.equals` xét tất cả thành phần.
6. **Tại sao `BigDecimal("1.0")` và `BigDecimal("1.00")` có thể bị `TreeSet` xem là trùng nhưng `HashSet` xem là khác?** `compareTo` trả `0`, còn `equals` phân biệt scale.
7. **`Collectors.toUnmodifiableSet()` khác gì `Collectors.toSet()`?** Loại đầu cam kết không chỉnh sửa và từ chối `null`; loại sau không cam kết tính có thể sửa hoặc kiểu cụ thể.
8. **`Set.of("A", "A")` trả set một phần tử không?** Không. Nó ném `IllegalArgumentException`.
9. **`parallelStream().collect(Collectors.toSet())` có yêu cầu `HashSet` là thread-safe không?** Không. Framework quản lý các container/tổng hợp; set trả về không tự nhiên trở thành thread-safe.
10. **Muốn các môn duy nhất trong mỗi nhóm, dùng các collector nào?** `groupingBy` với `mapping` và `toSet`.
11. **`Stream.generate(() -> 1).collect(Collectors.toSet())` có kết thúc vì chỉ có một giá trị duy nhất không?** Không. Collector vẫn chờ nguồn kết thúc; cần giới hạn hoặc nguồn hữu hạn.
12. **Nếu cần bản ghi đầu tiên theo `equals` từ nguồn có thứ tự, nên dùng gì?** `distinct().toList()` hoặc `distinct()` rồi thu vào một cấu trúc giữ encounter order.

**Ghi nhớ:** Thu thập thành `Set` là chọn **quy tắc duy nhất**, **cấu trúc kết quả** và **hợp đồng thứ tự**. `Collectors.toSet()` phù hợp khi chỉ cần một tập phần tử khác nhau; `toCollection(LinkedHashSet::new)` khi cần giữ thứ tự gặp đầu tiên; `toCollection(TreeSet::new)` khi cần duyệt theo thứ tự so sánh; `toUnmodifiableSet()` khi cần kết quả không thể sửa. Trước khi loại trùng đối tượng, luôn kiểm tra `equals`/`hashCode` hoặc comparator đang định nghĩa “cùng một phần tử” theo nghĩa nào.
