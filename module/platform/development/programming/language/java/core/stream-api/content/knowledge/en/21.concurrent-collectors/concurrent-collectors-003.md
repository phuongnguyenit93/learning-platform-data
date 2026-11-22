# Tạo ConcurrentMap bằng Collectors.toConcurrentMap

## 1. Vì sao cần một Collector trả ConcurrentMap?

Trong **JAVA_STREAM_API**, ta thường bắt đầu từ nguồn dữ liệu, nối các bước `filter`, `map`, `flatMap`, rồi sử dụng terminal operation `collect` để thu kết quả. Khi muốn ánh xạ từng phần tử thành một cặp **khóa – giá trị** và có thể hợp nhất các phần tử trùng khóa, `Collectors.toMap` là công cụ quen thuộc. Tuy nhiên, đối với một số pipeline xử lý song song, ta muốn collector có khả năng **tích lũy đồng thời vào một ConcurrentMap**.

`Collectors.toConcurrentMap` là họ collector dành cho nhu cầu đó. Nó:

- Chuyển các phần tử `T` thành cặp khóa `K` và giá trị `U`.
- Thu kết quả thành một `ConcurrentMap<K, U>`.
- Có overload để lựa chọn **chính sách khi khóa trùng**.
- Có overload để lựa chọn **loại ConcurrentMap** bằng `mapFactory`.
- Là collector có đặc tính **`CONCURRENT` và `UNORDERED`**; có thể tận dụng xử lý song song khi đáp ứng các điều kiện của Collector API.

Ví dụ hệ thống nhập dòng đơn hàng. Nhiều dòng có thể cùng mã sản phẩm (`sku`), và ta chỉ cần biết **tổng số đơn vị theo từng SKU**:

~~~text
Stream<OrderLine>
    │
    ├─ ("BOOK", 2)
    ├─ ("PEN",  3)
    ├─ ("BOOK", 1)
    └─ ("PAD",  4)
    │
    ▼
toConcurrentMap(
    OrderLine::sku,
    OrderLine::quantity,
    Integer::sum
)
    │
    ▼
ConcurrentMap<String, Integer>
    ├─ "BOOK" → 3
    ├─ "PEN"  → 3
    └─ "PAD"  → 4

Thứ tự duyệt các khóa không được bảo đảm ở collector mặc định.
~~~

**Điểm cần hiểu:** `ConcurrentMap` là **kiểu dữ liệu kết quả** có giao thức thao tác đồng thời, còn `CONCURRENT` là **đặc tính của Collector**. Hai khái niệm liên quan nhưng không đồng nghĩa với việc mọi code bên ngoài pipeline hay mọi đối tượng đặt bên trong Map đều tự động thread-safe.

Bài thuộc chương **Thu thập đồng thời** của Java Stream API, dùng ví dụ Java 17+, kết hợp ngữ nghĩa lazy pipeline, nguồn có thể chia bằng Spliterator, hợp đồng của phép gộp, an toàn trạng thái và những giới hạn về hiệu năng.

## 2. Ba overload của toConcurrentMap

Các chữ ký khái niệm trong `java.util.stream.Collectors`:

~~~java
// 1. Khóa được yêu cầu không trùng.
static <T, K, U>
Collector<T, ?, ConcurrentMap<K, U>> toConcurrentMap(
    Function<? super T, ? extends K> keyMapper,
    Function<? super T, ? extends U> valueMapper
);

// 2. Có chính sách gộp khi khóa trùng.
static <T, K, U>
Collector<T, ?, ConcurrentMap<K, U>> toConcurrentMap(
    Function<? super T, ? extends K> keyMapper,
    Function<? super T, ? extends U> valueMapper,
    BinaryOperator<U> mergeFunction
);

// 3. Có chính sách gộp và factory tạo ConcurrentMap.
static <T, K, U, M extends ConcurrentMap<K, U>>
Collector<T, ?, M> toConcurrentMap(
    Function<? super T, ? extends K> keyMapper,
    Function<? super T, ? extends U> valueMapper,
    BinaryOperator<U> mergeFunction,
    Supplier<M> mapFactory
);
~~~

Bảng đối chiếu:

| Thành phần | Chức năng | Ví dụ |
| --- | --- | --- |
| `keyMapper` | Chuyển mỗi `T` thành khóa `K` | `Item::sku` |
| `valueMapper` | Chuyển mỗi `T` thành giá trị `U` | `Item::quantity` |
| `mergeFunction` | Hợp nhất hai giá trị `U` có cùng khóa | `Integer::sum` |
| `mapFactory` | Cung cấp một ConcurrentMap rỗng mới | `ConcurrentSkipListMap::new` |

Kết quả của cả ba overload đều là một **Collector**, không phải một Map được tạo ngay lúc gọi phương thức. Map được xây dựng khi terminal `collect(...)` thực thi.

**Đặc điểm then chốt:**

- Dạng **hai tham số** từ chối khóa trùng và ném `IllegalStateException` nếu phát sinh va chạm.
- Dạng **ba tham số** cho phép khóa trùng, áp dụng `mergeFunction`.
- Dạng **bốn tham số** còn cho phép chọn loại Map cụ thể, nhưng factory phải trả một loại **`ConcurrentMap`**, không phải `HashMap` hoặc `LinkedHashMap` thông thường.

`Collectors.toConcurrentMap` không cam kết chính xác lớp Map trả về nếu không truyền factory. Trong các JDK phổ biến, Map mặc định thường là `ConcurrentHashMap`; **không nên dựa vào lớp triển khai đó như hợp đồng API** nếu ứng dụng cần một lớp cụ thể.

## 3. Ví dụ 1: ánh xạ khóa duy nhất bằng overload hai tham số

Giả sử danh sách người dùng có mã định danh duy nhất, muốn lập bảng tra cứu từ mã tới tên:

~~~java
import java.util.List;
import java.util.concurrent.ConcurrentMap;
import java.util.stream.Collectors;

public class UsersToConcurrentMap {
    record User(String id, String name) {}

    public static void main(String[] args) {
        List<User> users = List.of(
            new User("U01", "An"),
            new User("U02", "Bình"),
            new User("U03", "Chi")
        );

        ConcurrentMap<String, String> nameById = users.parallelStream()
            .collect(Collectors.toConcurrentMap(
                User::id,
                User::name
            ));

        System.out.println(nameById.get("U01")); // An
        System.out.println(nameById.get("U03")); // Chi
        System.out.println(nameById.size());     // 3
    }
}
~~~

Giải thích:

1. `users.parallelStream()` yêu cầu pipeline có thể xử lý song song.
2. `keyMapper` là `User::id`, trả khóa `String`.
3. `valueMapper` là `User::name`, trả giá trị `String`.
4. `collect` tạo `ConcurrentMap<String, String>`.

Đây là trường hợp thích hợp cho overload hai tham số **khi mã định danh thật sự duy nhất**.

### Nếu khóa bị trùng thì sao?

~~~java
import java.util.List;
import java.util.stream.Collectors;

record User(String id, String name) {}

List<User> duplicates = List.of(
    new User("U01", "An"),
    new User("U01", "An phiên bản khác")
);

// Ném IllegalStateException vì hai phần tử có cùng khóa "U01":
duplicates.stream().collect(
    Collectors.toConcurrentMap(User::id, User::name)
);
~~~

Không có cơ chế mặc định “lấy giá trị cuối cùng”. Lỗi khóa trùng là hành vi được thiết kế để tránh việc mất dữ liệu ngoài ý muốn.

Nếu khóa trùng là dữ liệu **không hợp lệ**, hãy giữ overload hai tham số và xử lý ngoại lệ theo chính sách nhập dữ liệu. Nếu khóa trùng là **bình thường**, phải chọn một `mergeFunction` tường minh.

## 4. Ví dụ 2: hợp nhất các dòng trùng khóa bằng mergeFunction

Một SKU có thể xuất hiện ở nhiều đơn hàng. Mục tiêu là tổng số lượng theo SKU, không phải một bản ghi đại diện bất kỳ.

~~~java
import java.util.List;
import java.util.concurrent.ConcurrentMap;
import java.util.stream.Collectors;

public class SumUnitsBySku {
    record OrderLine(String orderId, String sku, long quantity) {}

    public static void main(String[] args) {
        List<OrderLine> lines = List.of(
            new OrderLine("O1", "BOOK", 2L),
            new OrderLine("O2", "PEN",  3L),
            new OrderLine("O3", "BOOK", 1L),
            new OrderLine("O4", "PAD",  4L)
        );

        ConcurrentMap<String, Long> unitsBySku = lines.parallelStream()
            .collect(Collectors.toConcurrentMap(
                OrderLine::sku,
                OrderLine::quantity,
                Long::sum
            ));

        System.out.println(unitsBySku.get("BOOK")); // 3
        System.out.println(unitsBySku.get("PEN"));  // 3
        System.out.println(unitsBySku.get("PAD"));  // 4
        System.out.println(unitsBySku.size());      // 3
    }
}
~~~

`Long::sum` nhận hai giá trị của **cùng khóa** rồi cộng chúng. Có thể hình dung:

~~~text
BOOK -> 2
BOOK -> 1

merge(2, 1) -> 3

PEN -> 3
PAD -> 4
~~~

Trong parallel stream, hai giá trị cùng khóa có thể đến từ những nhánh xử lý khác nhau; **không được giả định thứ tự gọi `mergeFunction`**. Với phép cộng số nguyên không cần xác định “giá trị nào đến trước”, kết quả ổn định theo ngữ nghĩa số học Java nếu miền đầu vào phù hợp.

**Giới hạn:** `Long::sum` có thể tràn `long`. Nếu kết quả phải là tổng toán học không tràn, hãy xác định miền giá trị hoặc dùng kiểu số phù hợp (ví dụ `BigInteger`); không coi `ConcurrentMap` là cơ chế tự phát hiện overflow.

### 4.1. Tổng BigDecimal cho dữ liệu tiền tệ

Khi số tiền cần chính xác ở miền thập phân và mọi giá trị cùng đơn vị tiền tệ, `BigDecimal::add` là một merge function thường hợp lý:

~~~java
import java.math.BigDecimal;
import java.util.List;
import java.util.concurrent.ConcurrentMap;
import java.util.stream.Collectors;

public class RevenueBySku {
    record Sale(String sku, BigDecimal amount) {}

    public static void main(String[] args) {
        List<Sale> sales = List.of(
            new Sale("BOOK", new BigDecimal("19.90")),
            new Sale("PEN",  new BigDecimal("5.25")),
            new Sale("BOOK", new BigDecimal("10.10"))
        );

        ConcurrentMap<String, BigDecimal> revenue = sales.parallelStream()
            .collect(Collectors.toConcurrentMap(
                Sale::sku,
                Sale::amount,
                BigDecimal::add
            ));

        System.out.println(revenue.get("BOOK")); // 30.00
        System.out.println(revenue.get("PEN"));  // 5.25
    }
}
~~~

`BigDecimal.add` không làm tròn khi không truyền `MathContext`. Dù vậy, một báo cáo tài chính vẫn cần chính sách về tiền tệ, scale, tỷ giá và trường hợp giá trị null; phép cộng không tự biết hai khoản tiền có cùng đơn vị hay không.

## 5. Merge function phải thỏa những tính chất nào?

`mergeFunction` là phần rất dễ viết sai khi xử lý đồng thời. Nó phải **không can thiệp nguồn**, không dựa vào mutable shared state, và phù hợp với việc các phần tử được kết hợp theo những cách khác nhau.

### 5.1. Tính kết hợp

Với các giá trị `a`, `b` và `c`:

~~~text
merge(merge(a, b), c) = merge(a, merge(b, c))
~~~

Nếu điều kiện trên không đúng, cách ghép các nhánh khác nhau có thể cho kết quả khác nhau.

Ví dụ **không nên dùng phép trừ** để tổng hợp:

~~~java
// Không phù hợp cho phép tổng hợp song song cần kết quả ổn định:
ConcurrentMap<String, Integer> result = rows.parallelStream()
    .collect(Collectors.toConcurrentMap(
        Row::key,
        Row::value,
        (left, right) -> left - right
    ));
~~~

Trong snippet, `Row` và `rows` là model và danh sách do ứng dụng cung cấp. Phép trừ không có tính kết hợp: `(10 - 3) - 2` khác `10 - (3 - 2)`.

### 5.2. Tính giao hoán giúp kết quả không phụ thuộc thứ tự

Vì `toConcurrentMap` là collector **UNORDERED**, thứ tự hai giá trị được đưa vào merge không nhất thiết theo encounter order. Nếu yêu cầu cùng một kết quả **bất kể lịch chạy**, nên chọn phép gộp còn có tính giao hoán:

~~~text
merge(a, b) = merge(b, a)
~~~

Ví dụ phù hợp về ý định:

| Phép gộp | Kết hợp? | Giao hoán? | Nhận xét |
| --- | --- | --- | --- |
| `Long::sum` | Có theo ngữ nghĩa cộng `long` của Java | Có | Lưu ý tràn số nếu cần miền toán học không tràn |
| `BigDecimal::add` không `MathContext` | Có về giá trị số | Có về giá trị số | Scale có thể ảnh hưởng `equals` hoặc hiển thị |
| `Integer::max` | Có | Có | Lấy giá trị lớn nhất |
| Nối chuỗi `left + right` | Có theo thứ tự chuỗi | **Không** | Thứ tự kết quả không xác định khi unordered |
| `(a,b) -> b` | Có | **Không** | “Giá trị cuối” phụ thuộc lịch thực thi |
| Phép trừ | **Không** | Không | Không phù hợp cho reduction cần ổn định |

**Lưu ý BigDecimal:** Về mặt *giá trị số*, phép cộng không làm tròn có tính kết hợp và giao hoán. Nhưng `BigDecimal.equals` còn xét `scale`; nếu nghiệp vụ quan tâm biểu diễn/scale chính xác, hãy chuẩn hóa dữ liệu hoặc chọn chính sách rõ ràng thay vì chỉ suy từ giá trị toán học.

### 5.3. Không có nghĩa là phải luôn giao hoán

Collector API đặt trọng tâm vào việc tích lũy và kết hợp đúng hợp đồng. `toConcurrentMap` không bảo đảm thứ tự; nếu phép gộp nhạy với thứ tự, chương trình vẫn có thể chạy, nhưng kết quả có thể không còn **xác định theo encounter order**. Khi yêu cầu “giữ bản ghi đầu tiên” hoặc “ghép văn bản đúng trình tự nguồn”, hãy chọn collector có hợp đồng thứ tự phù hợp hoặc xác định thứ tự bằng khóa nghiệp vụ, chứ không kỳ vọng `toConcurrentMap` giữ thứ tự.

## 6. Phân biệt “bản ghi mới nhất” với “đến cuối cùng”

Một lỗi hay gặp là dùng:

~~~java
// Không bảo đảm chọn bản ghi mới nhất theo nghiệp vụ:
(left, right) -> right
~~~

Trên parallel stream, `right` chỉ là đối số thứ hai của **một lần gộp**, không nhất thiết là phần tử có thời gian lớn nhất hoặc vị trí muộn nhất trong nguồn.

Đúng hơn là chọn bản ghi bằng **trường phiên bản/thời gian**, với quy tắc phá hòa đủ rõ:

~~~java
import java.util.Comparator;
import java.util.List;
import java.util.concurrent.ConcurrentMap;
import java.util.function.BinaryOperator;
import java.util.stream.Collectors;

public class LatestEvents {
    record Event(String key, long version, String payload) {}

    public static void main(String[] args) {
        List<Event> events = List.of(
            new Event("BOOK", 10, "old"),
            new Event("PEN",  12, "blue"),
            new Event("BOOK", 15, "new"),
            new Event("BOOK", 12, "middle")
        );

        Comparator<Event> byVersionThenPayload =
            Comparator.comparingLong(Event::version)
                .thenComparing(Event::payload);

        ConcurrentMap<String, Event> latest = events.parallelStream()
            .collect(Collectors.toConcurrentMap(
                Event::key,
                event -> event,
                BinaryOperator.maxBy(byVersionThenPayload)
            ));

        System.out.println(latest.get("BOOK").payload()); // new
        System.out.println(latest.get("BOOK").version()); // 15
    }
}
~~~

Với quy tắc so sánh này, mọi Event trùng khóa được chọn theo **version lớn nhất**, rồi tới `payload` để phá hòa. Nếu có hai Event có cùng version và payload nhưng khác những thuộc tính nghiệp vụ khác, phải xác định thêm tiêu chí nếu việc chọn đại diện cụ thể là quan trọng.

Đây là một nguyên tắc thiết kế chung: **thứ tự xử lý trên thread không phải thứ tự nghiệp vụ**. Khi cần “mới nhất”, phải lưu timestamp/sequence/version đủ tin cậy và đưa phép so sánh đó vào thuật toán.

## 7. Chọn loại ConcurrentMap bằng mapFactory

Nếu cần một kiểu Map cụ thể, dùng overload bốn tham số:

~~~java
toConcurrentMap(
    keyMapper,
    valueMapper,
    mergeFunction,
    mapFactory
)
~~~

`mapFactory` là `Supplier<M>` với `M extends ConcurrentMap<K,U>`. Nó phải cung cấp một container phù hợp, thông thường là **một Map mới và rỗng** cho mỗi lần thu thập.

### 7.1. ConcurrentSkipListMap: sắp xếp theo khóa

`ConcurrentSkipListMap` vừa hỗ trợ thao tác đồng thời vừa duyệt khóa theo thứ tự so sánh:

~~~java
import java.util.List;
import java.util.concurrent.ConcurrentSkipListMap;
import java.util.stream.Collectors;

public class SortedConcurrentMap {
    record Item(String sku, long quantity) {}

    public static void main(String[] args) {
        List<Item> items = List.of(
            new Item("PEN", 2),
            new Item("BOOK", 3),
            new Item("PAD", 1),
            new Item("BOOK", 1)
        );

        ConcurrentSkipListMap<String, Long> units = items.parallelStream()
            .collect(Collectors.toConcurrentMap(
                Item::sku,
                Item::quantity,
                Long::sum,
                ConcurrentSkipListMap::new
            ));

        System.out.println(units.keySet()); // [BOOK, PAD, PEN]
        System.out.println(units.get("BOOK")); // 4
    }
}
~~~

`ConcurrentSkipListMap` được sắp theo **khóa**. Điều đó không có nghĩa collector lưu các bản ghi theo encounter order hay gọi `mergeFunction` theo thứ tự nguồn. Hai thuộc tính khác nhau:

- **Thứ tự duyệt khóa:** do Map triển khai cung cấp.
- **Thứ tự giá trị được gộp:** collector UNORDERED không cam kết theo thứ tự nguồn.

Nếu comparator coi hai khóa khác nhau là tương đương (so sánh trả 0), Map có thể xem chúng là cùng một khóa; cần quy định comparator phù hợp với định nghĩa khóa nghiệp vụ.

### 7.2. ConcurrentHashMap: lựa chọn khi không cần sắp khóa

~~~java
import java.util.concurrent.ConcurrentHashMap;

ConcurrentHashMap<String, Long> units = items.parallelStream()
    .collect(Collectors.toConcurrentMap(
        Item::sku,
        Item::quantity,
        Long::sum,
        ConcurrentHashMap::new
    ));
~~~

Đoạn trên giả định `Item` và `items` từ ví dụ trước. Dùng `ConcurrentHashMap::new` nếu yêu cầu cụ thể là loại Map này. `ConcurrentHashMap` không bảo đảm thứ tự duyệt khóa.

### 7.3. Không dùng một HashMap thông thường làm factory

~~~java
// Không khớp ràng buộc kiểu M extends ConcurrentMap<K, U>:
// Collectors.toConcurrentMap(
//     Item::sku, Item::quantity, Long::sum, HashMap::new
// );
~~~

`HashMap` và `LinkedHashMap` không triển khai `ConcurrentMap`. Nếu yêu cầu là Map giữ thứ tự chèn và không cần collector concurrent, hãy xem `Collectors.toMap(..., LinkedHashMap::new)` thay vì cố ép factory cho `toConcurrentMap`.

## 8. CONCURRENT và UNORDERED: đặc tính của collector

`Collector.Characteristics` mô tả cách một collector có thể được sử dụng. `Collectors.toConcurrentMap` là collector **concurrent** và **unordered**.

- `CONCURRENT` cho phép framework gọi accumulator đồng thời từ nhiều thread **trên cùng một kết quả container**, theo hợp đồng.
- `UNORDERED` thông báo việc tích lũy không cần giữ thứ tự nguồn.
- Kết quả collector dạng này có thể được dùng trực tiếp làm Map mà không cần biến đổi kiểu cuối phức tạp; tuy nhiên không nên xây logic dựa vào danh tính Map hay thứ tự thực thi callback.

### 8.1. Kiểm tra collector characteristics

~~~java
import java.util.List;
import java.util.concurrent.ConcurrentMap;
import java.util.stream.Collector;
import java.util.stream.Collectors;

record Item(String sku, long quantity) {}

Collector<Item, ?, ConcurrentMap<String, Long>> collector =
    Collectors.toConcurrentMap(
        Item::sku,
        Item::quantity,
        Long::sum
    );

System.out.println(
    collector.characteristics().contains(
        Collector.Characteristics.CONCURRENT
    )
); // true

System.out.println(
    collector.characteristics().contains(
        Collector.Characteristics.UNORDERED
    )
); // true
~~~

Có `CONCURRENT` **không** nghĩa là terminal `collect` chạy song song khi nguồn Stream đang tuần tự. Một Stream tuần tự vẫn có thể dùng `toConcurrentMap`; chỉ là kết quả có giao diện ConcurrentMap và collector có khả năng tích lũy đồng thời nếu hệ thống sử dụng theo cách phù hợp.

### 8.2. Parallel stream làm việc thế nào?

Với collector concurrent, unordered, một triển khai parallel stream có thể cho các nhánh **tích lũy trực tiếp vào một container đồng thời** thay vì bắt buộc tạo nhiều Map riêng rồi hợp nhất theo encounter order. API cho phép chiến lược phù hợp, nhưng không cam kết số thread, số lần gộp, thời điểm gọi hàm hoặc mức tăng tốc cụ thể.

~~~text
            Các nhánh xử lý Stream song song
                │         │         │
                ▼         ▼         ▼
           accumulator accumulator accumulator
                │         │         │
                └─────────┼─────────┘
                          ▼
                    ConcurrentMap

             (Sơ đồ khái niệm; không phải lịch thread bắt buộc)
~~~

Với nguồn có thứ tự như `List`, collector `UNORDERED` vẫn được phép không quan tâm encounter order. Do đó nó không phù hợp khi giá trị cuối phụ thuộc việc các bản ghi đến trước/sau.

## 9. Chính sách null: phải kiểm soát cả khóa lẫn giá trị

Một `ConcurrentMap` phổ biến như `ConcurrentHashMap` **không chấp nhận khóa `null` hoặc giá trị `null`**. `ConcurrentSkipListMap` cũng không chấp nhận giá trị null và không chấp nhận khóa null trong cách dùng thông thường.

Vì vậy, khi dùng `toConcurrentMap`:

- Không cho `keyMapper` trả null.
- Không cho `valueMapper` trả null.
- Không trả null từ `mergeFunction` để “đại diện cho giá trị vắng mặt” mà không hiểu rõ ngữ nghĩa `Map.merge`.
- Chọn chính sách nghiệp vụ trước: **lọc**, **chuẩn hóa thành giá trị hợp lệ**, hoặc **báo lỗi**.

Ví dụ làm sạch dữ liệu trước khi collect:

~~~java
import java.util.Arrays;
import java.util.List;
import java.util.Objects;
import java.util.concurrent.ConcurrentMap;
import java.util.stream.Collectors;

public class NullSafeConcurrentMap {
    record Product(String sku, String name) {}

    public static void main(String[] args) {
        List<Product> raw = Arrays.asList(
            new Product("P01", "Bút"),
            new Product(null, "Chưa có mã"),
            new Product("P02", null)
        );

        ConcurrentMap<String, String> names = raw.parallelStream()
            .filter(p -> p.sku() != null && p.name() != null)
            .collect(Collectors.toConcurrentMap(
                Product::sku,
                Product::name
            ));

        System.out.println(names.size()); // 1
        System.out.println(names.get("P01")); // Bút
    }
}
~~~

Đoạn trên chọn chính sách **bỏ bản ghi không đầy đủ**. Nếu dữ liệu thiếu phải được ghi nhận hoặc báo lỗi, cần trả một kiểu kết quả có trạng thái lỗi, thu thập báo cáo sai lệch hoặc ném exception. Không được xem việc bỏ qua dữ liệu là mặc định hợp lý trong mọi nghiệp vụ.

### 9.1. Vì sao mergeFunction trả null là nguy hiểm?

Các implementation phổ biến dựa vào ngữ nghĩa `Map.merge`: nếu remapping function trả `null`, ánh xạ khóa có thể bị **xóa** khỏi Map. Do đó:

~~~java
// Không dùng null như một kết quả tổng hợp hợp lệ:
(left, right) -> null
~~~

Đoạn này không có nghĩa “giữ khóa nhưng giá trị rỗng”. Khi gộp nhiều dòng cùng khóa, nó có thể khiến kết quả bị xóa, rồi một dòng đến sau tạo lại khóa, làm kết quả khó dự đoán. Hãy dùng một value object chứa trạng thái hoặc một chính sách gộp tường minh, không dựa vào null.

## 10. An toàn luồng: Map an toàn không đồng nghĩa callback an toàn

`ConcurrentMap` cung cấp các thao tác đồng thời ở cấp Map. Nhưng nếu `keyMapper`, `valueMapper` hay `mergeFunction` truy cập hoặc sửa dữ liệu mutable dùng chung, chúng vẫn có thể gây race condition hoặc cho kết quả không xác định.

### 10.1. Ví dụ sai: bộ đếm dùng chung trong mapper

~~~java
import java.util.concurrent.atomic.AtomicInteger;
import java.util.stream.IntStream;
import java.util.stream.Collectors;

// Chống chỉ định nếu muốn thứ tự khóa theo thứ tự input.
AtomicInteger counter = new AtomicInteger();

var result = IntStream.range(0, 1000)
    .parallel()
    .boxed()
    .collect(Collectors.toConcurrentMap(
        n -> "K" + counter.getAndIncrement(),
        n -> n
    ));
~~~

`AtomicInteger` giúp thao tác tăng là nguyên tử, nhưng **số thứ tự gắn vào mỗi phần tử phụ thuộc lịch xử lý**. Nếu muốn các khóa `K0`, `K1` ... tương ứng với chỉ số nguồn, dùng trực tiếp `n -> "K" + n`. Đây là lỗi về **ngữ nghĩa nghiệp vụ**, ngay cả khi không có data race ở phép tăng.

### 10.2. Ví dụ sai: merge bằng cách sửa một ArrayList được chia sẻ

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Collectors;

record Row(String key, String value) {}

List<Row> rows = List.of(
    new Row("A", "x"),
    new Row("A", "y")
);

// Không nên dùng mutable list như một giá trị có thể bị
// đọc/ghi đồng thời bên ngoài pipeline mà không có đồng bộ phù hợp.
var map = rows.parallelStream().collect(
    Collectors.toConcurrentMap(
        Row::key,
        row -> new ArrayList<>(List.of(row.value())),
        (left, right) -> {
            left.addAll(right); // Gộp kiểu mutation: khó dùng an toàn ngoài phạm vi collector.
            return left;
        }
    )
);
~~~

Việc thao tác vào List có thể được thực hiện dưới cơ chế đồng bộ theo khóa của ConcurrentMap triển khai, nhưng **các List kết quả không tự thread-safe** khi có tác vụ khác truy cập/sửa đồng thời. Hơn nữa, mutation trong merge làm tăng độ phức tạp của chứng minh tính kết hợp và khả năng tái sử dụng reducer. Nếu mục tiêu là **gom một danh sách bản ghi theo khóa**, dùng `groupingByConcurrent` với downstream được quản lý bởi collector sẽ diễn đạt rõ hơn.

~~~java
import java.util.concurrent.ConcurrentMap;
import java.util.stream.Collectors;

ConcurrentMap<String, List<Row>> grouped = rows.parallelStream()
    .collect(Collectors.groupingByConcurrent(
        Row::key,
        Collectors.toList()
    ));
~~~

**Chú ý:** Giá trị `List<Row>` bên trong `ConcurrentMap` không được bảo đảm là một danh sách an toàn cho các sửa đổi đồng thời tùy ý **sau** khi collect. `groupingByConcurrent` quản lý việc tích lũy theo hợp đồng Collector trong giai đoạn thu thập; nó không biến tất cả các giá trị lồng nhau thành collection concurrent.

### 10.3. Nên làm gì với mergeFunction?

- Ưu tiên hàm **thuần**, không can thiệp nguồn và không giữ trạng thái mutable bên ngoài.
- Đảm bảo **kết hợp được**, và nếu cần kết quả ổn định không phụ thuộc thứ tự thì chọn phép **giao hoán** hoặc quy tắc chọn đại diện xác định.
- Không dùng merge function để gửi email, ghi log nghiệp vụ bắt buộc, gọi dịch vụ ngoài hoặc sửa một Map khác.
- Với phép tính có chi phí lớn, cân nhắc mức độ tranh chấp tại các khóa nóng và kiểm thử thực tế.

## 11. So sánh toMap, toConcurrentMap và groupingByConcurrent

Ba collector này có điểm chung là trả một Map, nhưng giải quyết ba nhu cầu khác nhau.

| Tiêu chí | `toMap` | `toConcurrentMap` | `groupingByConcurrent` |
| --- | --- | --- | --- |
| Dạng đầu ra | `Map<K,U>` | `ConcurrentMap<K,U>` | `ConcurrentMap<K,D>` |
| Collector có `CONCURRENT`? | Không | Có | Có |
| Collector `UNORDERED`? | Không mặc định | Có | Có |
| Khóa trùng | Lỗi hoặc dùng merge function | Lỗi hoặc dùng merge function | Nhiều phần tử được đưa vào **cùng nhóm** |
| Giá trị nhóm | Một `U` sau ánh xạ/gộp | Một `U` sau ánh xạ/gộp | Kết quả của downstream collector |
| Tùy chọn Map | `mapFactory`, cần `Map` | `mapFactory`, cần `ConcurrentMap` | `mapFactory`, cần `ConcurrentMap` |
| Cần giữ ngữ nghĩa encounter order | Có thể cân nhắc `toMap` cùng Map/merge phù hợp | Không | Không |

### 11.1. Khi chỉ cần một giá trị tổng hợp theo khóa

~~~java
ConcurrentMap<String, Long> units = lines.parallelStream()
    .collect(Collectors.toConcurrentMap(
        OrderLine::sku,
        OrderLine::quantity,
        Long::sum
    ));
~~~

`toConcurrentMap` rõ ràng khi mỗi khóa ánh xạ tới **một giá trị cuối**, được tạo bằng phép merge có ý nghĩa.

### 11.2. Khi cần danh sách đầy đủ theo mỗi khóa

~~~java
ConcurrentMap<String, List<OrderLine>> linesBySku =
    lines.parallelStream().collect(
        Collectors.groupingByConcurrent(OrderLine::sku)
    );
~~~

`groupingByConcurrent` tự quản lý việc tích lũy nhiều phần tử vào mỗi nhóm. Lưu ý `groupingByConcurrent` không cam kết thứ tự encounter order trong danh sách nhóm.

### 11.3. Khi cần giữ thứ tự gặp đầu tiên hoặc Map có thứ tự chèn

Nếu yêu cầu đầu ra là Map duyệt khóa theo lần xuất hiện đầu tiên trong nguồn, `toConcurrentMap` không phải lựa chọn chính xác. Dùng collector ordered và factory thích hợp:

~~~java
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.stream.Collectors;

Map<String, Long> ordered = lines.stream()
    .collect(Collectors.toMap(
        OrderLine::sku,
        OrderLine::quantity,
        Long::sum,
        LinkedHashMap::new
    ));
~~~

`LinkedHashMap` lưu thứ tự chèn của khóa, thích hợp cho pipeline tuần tự có encounter order. Nó **không phải ConcurrentMap**. Nếu chỉ cần thứ tự **sắp theo khóa**, có thể dùng `ConcurrentSkipListMap` với `toConcurrentMap` như ở mục 7.

## 12. Kết hợp toConcurrentMap với collector nhiều tầng

Ta cũng có thể sử dụng `toConcurrentMap` làm **downstream** của một collector nhóm. Đây là cách xây một báo cáo phân cấp gồm Map khu vực, bên trong là Map SKU và tổng số lượng.

~~~java
import java.util.List;
import java.util.concurrent.ConcurrentMap;
import java.util.stream.Collectors;

public class NestedConcurrentReport {
    record OrderLine(String region, String sku, int quantity) {}

    public static void main(String[] args) {
        List<OrderLine> lines = List.of(
            new OrderLine("Nam", "BOOK", 2),
            new OrderLine("Nam", "BOOK", 1),
            new OrderLine("Nam", "PEN",  1),
            new OrderLine("Bắc", "PEN",  4)
        );

        ConcurrentMap<String, ConcurrentMap<String, Integer>> report =
            lines.parallelStream().collect(
                Collectors.groupingByConcurrent(
                    OrderLine::region,
                    Collectors.toConcurrentMap(
                        OrderLine::sku,
                        OrderLine::quantity,
                        Integer::sum
                    )
                )
            );

        System.out.println(report.get("Nam").get("BOOK")); // 3
        System.out.println(report.get("Nam").get("PEN"));  // 1
        System.out.println(report.get("Bắc").get("PEN"));  // 4
    }
}
~~~

Có hai mức khóa:

- `region` là khóa của `ConcurrentMap` bên ngoài.
- `sku` là khóa của `ConcurrentMap` bên trong.
- `Integer::sum` hợp nhất số lượng của những dòng cùng region và SKU.

Kiểu dữ liệu trả về là `ConcurrentMap<String, ConcurrentMap<String, Integer>>`. Cấu trúc này hữu ích khi hệ thống cần tra cứu nhanh hai cấp, nhưng cũng có chi phí tạo Map và đối tượng; nếu chỉ cần một báo cáo nhỏ chạy một lần, `groupingBy` tuần tự hoặc một record khóa tổng hợp có thể đơn giản hơn.

## 13. Null, khóa nóng, hiệu năng và giới hạn tài nguyên

### 13.1. Khóa nóng làm giảm mức song song hữu ích

Giả sử hàng triệu bản ghi đều thuộc một SKU `"BOOK"`. Dù nhiều thread đọc nguồn cùng lúc, các cập nhật lên **một khóa** phải được phối hợp để tránh mất dữ liệu.

~~~text
Nhiều nhánh parallel ─────► cùng key "BOOK"
                                │
                                ▼
                      Cập nhật/merge có phối hợp
                                │
                                ▼
                          Một giá trị cuối
~~~

Vì vậy, tính concurrent của collector không đảm bảo mọi tác vụ merge có thể mở rộng tuyến tính theo số lõi. Khi số nhóm rất ít và phân bố lệch, contention có thể trở thành nút thắt.

### 13.2. Số nhóm lớn tiêu tốn bộ nhớ

Mỗi khóa phân biệt tạo một entry trong Map. Nếu khóa được tạo bằng dữ liệu gần như duy nhất, ví dụ UUID cho mỗi bản ghi, `toConcurrentMap` có thể tạo một Map rất lớn, dù không có khóa nào cần merge. `ConcurrentMap` không phải kho lưu trữ vô hạn; cần tính đến giới hạn RAM, áp lực GC và chiến lược xử lý dữ liệu theo lô nếu đầu ra lớn.

### 13.3. Đừng đo hiệu năng bằng một lần chạy

Để so sánh `toMap` và `toConcurrentMap`:

1. Dùng cùng dữ liệu và cùng yêu cầu đầu ra, không chuyển từ “giữ thứ tự” sang “bất kỳ thứ tự” mà không ghi nhận.
2. Kiểm tra kết quả đúng trước bằng `Map.equals` hoặc các bất biến nghiệp vụ.
3. Đo tuần tự và song song, nhiều lần và trong điều kiện đủ ổn định.
4. Thay đổi kích thước nguồn, số khóa phân biệt, mức độ trùng khóa và chi phí mapper.
5. Đo thời gian, cấp phát/GC và mức sử dụng CPU khi cần.

Không có một ngưỡng cố định mà “vượt n phần tử thì toConcurrentMap luôn nhanh”. Hiệu quả phụ thuộc `Spliterator`, các bước trước collect, hàm băm và so sánh khóa, phân bố dữ liệu, merge function và tài nguyên máy.

### 13.4. Nguồn I/O và side effect vẫn cần quản lý riêng

Nếu nguồn Stream được xây từ `Files.lines` hoặc socket, cần quản lý tài nguyên qua `try-with-resources`; `collect` không tự đóng mọi nguồn gắn với tài nguyên. Parallel stream có thể thực hiện callback trên nhiều thread, nên các lời gọi HTTP hay ghi DB trong mapper cần thiết kế retry/timeout/backpressure và tính idempotent, không dựa đơn thuần vào `toConcurrentMap`.

## 14. Kiểm thử: kết quả không phụ thuộc lịch chạy

Một kiểm thử tốt không so sánh chuỗi in ra từ `ConcurrentMap.toString()` vì thứ tự duyệt mặc định không được cam kết. Hãy so sánh nội dung khóa và giá trị.

Ví dụ độc lập sau xác minh tổng 10 nhóm, mỗi nhóm có 1.000 phần tử từ dải 0 đến 9.999:

~~~java
import java.util.concurrent.ConcurrentMap;
import java.util.stream.Collectors;
import java.util.stream.IntStream;

public class ConcurrentMapChecks {
    static ConcurrentMap<Integer, Long> countByRemainder(
        boolean parallel
    ) {
        IntStream stream = IntStream.range(0, 10_000);
        stream = parallel ? stream.parallel() : stream.sequential();

        return stream.boxed().collect(Collectors.toConcurrentMap(
            number -> number % 10,
            number -> 1L,
            Long::sum
        ));
    }

    public static void main(String[] args) {
        ConcurrentMap<Integer, Long> serial =
            countByRemainder(false);

        ConcurrentMap<Integer, Long> parallel =
            countByRemainder(true);

        if (!serial.equals(parallel)) {
            throw new AssertionError("Hai chế độ cho kết quả khác nhau");
        }

        if (parallel.size() != 10) {
            throw new AssertionError("Thiếu hoặc thừa nhóm");
        }

        for (int key = 0; key < 10; key++) {
            if (parallel.get(key) != 1000L) {
                throw new AssertionError("Sai số đếm của nhóm " + key);
            }
        }

        System.out.println("PASS");
    }
}
~~~

Kiểm tra này chứng minh đúng với **bộ dữ liệu thử**, không tự chứng minh mọi merge function có tính kết hợp hay mọi workload đều nhanh. Nên bổ sung test trường hợp:

- Stream rỗng: kết quả Map rỗng.
- Một khóa duy nhất xuất hiện nhiều lần.
- Nhiều khóa phân biệt, phân bố đều và phân bố lệch.
- Khóa trùng trong overload hai tham số: có lỗi đúng kỳ vọng.
- Null ở key/value: bị xử lý theo chính sách.
- Trường hợp tràn số, tie của comparator và phiên bản bản ghi.
- Nhiều lần chạy tuần tự/song song để phát hiện sự phụ thuộc vào lịch xử lý.

## 15. Những lỗi thường gặp

### Lỗi 1: dùng overload hai tham số khi khóa có thể trùng

~~~java
// Có thể ném IllegalStateException:
lines.parallelStream().collect(
    Collectors.toConcurrentMap(
        OrderLine::sku,
        OrderLine::quantity
    )
);
~~~

Nếu mục tiêu là tổng số lượng, phải thêm `Long::sum`; nếu khóa đáng lẽ duy nhất, giữ cách viết và coi trùng khóa là dữ liệu lỗi.

### Lỗi 2: dùng (left, right) -> right để chọn “dòng cuối”

~~~java
// Không đáng tin nếu muốn dòng có timestamp/version mới nhất:
(left, right) -> right
~~~

Vì collector unordered, thứ tự merge không cam kết theo nguồn. Chọn bằng comparator theo trường nghiệp vụ như `version` hoặc `timestamp`.

### Lỗi 3: dùng HashMap::new làm factory

~~~java
// Không biên dịch do yêu cầu M extends ConcurrentMap<K,U>:
// toConcurrentMap(keyMapper, valueMapper, mergeFn, HashMap::new)
~~~

Chọn `ConcurrentHashMap::new` hoặc `ConcurrentSkipListMap::new` nếu cần một loại ConcurrentMap cụ thể.

### Lỗi 4: coi giá trị List bên trong Map là thread-safe

~~~java
// ConcurrentMap<String, List<String>> không làm từng List<String>
// trở thành collection an toàn cho sửa đổi đồng thời.
~~~

Dùng collector phù hợp để gom list, chỉ công bố dữ liệu sau khi collect hoàn tất, và có chính sách đồng bộ nếu tiếp tục sửa các List sau đó.

### Lỗi 5: bỏ qua null

~~~java
// Không để keyMapper/valueMapper trả null khi thu vào
// các ConcurrentMap phổ biến như ConcurrentHashMap.
~~~

Phải lọc hoặc chuyển null thành trạng thái hợp lệ trước terminal. Nếu null là lỗi nghiệp vụ, báo lỗi thay vì âm thầm bỏ dữ liệu.

### Lỗi 6: merge function có tác dụng phụ

~~~java
// Sai ý tưởng: cập nhật biến dùng chung hoặc gửi request trong merge.
// merge có thể chạy trên nhiều thread và theo thứ tự không dự đoán.
~~~

Hãy viết hàm hợp nhất thuần; thực hiện side effect sau khi thu thập và xác nhận kết quả.

### Lỗi 7: nghĩ collector concurrent tự bật parallel

~~~java
// Stream vẫn tuần tự, dù collector có CONCURRENT:
var serial = lines.stream().collect(
    Collectors.toConcurrentMap(
        OrderLine::sku,
        OrderLine::quantity,
        Long::sum
    )
);
~~~

Chế độ xử lý do `stream()`, `parallelStream()`, `parallel()` và `sequential()` quyết định. Tính concurrent của collector chỉ mô tả khả năng tích lũy, không tự đổi mode.

### Lỗi 8: mặc định ConcurrentMap là không sửa đổi được

Kết quả là một ConcurrentMap có thể hỗ trợ `put`, `remove`, `compute`, `merge`. Nó **không phải** một snapshot bất biến. Nếu API chỉ nên trả view không sửa đổi được, hãy xác định cách tạo bản sao công bố:

~~~java
import java.util.Map;

// Đã hoàn tất collect, không có thread khác tiếp tục sửa values:
Map<String, Long> snapshot = Map.copyOf(units);
~~~

`Map.copyOf` trả Map không sửa đổi được và cấm null ở khóa/giá trị, nhưng **không** cam kết giữ thứ tự duyệt khóa của `ConcurrentSkipListMap`. Các value object mutable đặt trong Map vẫn có thể thay đổi; muốn snapshot bất biến sâu phải sao chép/chuẩn hóa cả các đối tượng con.

## 16. Cách lựa chọn nhanh

| Yêu cầu | Lựa chọn gợi ý | Lý do |
| --- | --- | --- |
| Chuyển các bản ghi có key duy nhất thành lookup Map | `toConcurrentMap(key, value)` nếu cần ConcurrentMap | Lỗi khi key trùng |
| Cộng số lượng theo SKU trên parallel stream | `toConcurrentMap(key, value, Long::sum)` | Merge kết hợp, không phụ thuộc thứ tự |
| Chọn bản ghi mới nhất theo version | `toConcurrentMap(key, event, maxBy(comparator))` | Quy tắc xác định theo khóa nghiệp vụ |
| Cần Map sắp theo khóa và hỗ trợ đồng thời | `toConcurrentMap(..., ConcurrentSkipListMap::new)` | Có thứ tự so sánh khóa |
| Cần Map theo thứ tự chèn | `toMap(..., LinkedHashMap::new)` | Không phải concurrent collector |
| Cần nhiều bản ghi trong mỗi nhóm | `groupingByConcurrent(key)` | Downstream tích lũy nhóm |
| Cần tổng hoặc thống kê theo nhóm và không có yêu cầu ConcurrentMap | `groupingBy(key, summingX(...))` | Có thể gọn hơn cho báo cáo tuần tự |
| Có key/value null | Lọc, chuẩn hóa hoặc báo lỗi trước collect | Tránh kết quả sai và NPE |
| Chỉ cần tập giá trị bất biến sau tính toán | Thu thập rồi `Map.copyOf` nếu phù hợp | Tách trạng thái xử lý với API công bố |
| Dữ liệu lớn, nhiều khóa nóng | Benchmark và xem xét phân bố | Contention có thể giới hạn tốc độ |

## 17. Câu hỏi tự kiểm tra

1. **`Collectors.toConcurrentMap` trả về ngay một ConcurrentMap hay một Collector?** Trả một Collector; Map được tạo khi terminal `collect` thực thi.
2. **Overload hai tham số làm gì khi hai phần tử cùng khóa?** Ném `IllegalStateException`.
3. **Khi nào cần overload ba tham số?** Khi có thể trùng khóa và muốn quy định cách hợp nhất các giá trị.
4. **Tham số thứ tư dùng để làm gì?** `mapFactory` chọn một triển khai `ConcurrentMap` cụ thể.
5. **Có thể dùng `LinkedHashMap::new` làm factory không?** Không; Map đó không triển khai `ConcurrentMap`.
6. **Hai Collector characteristics quan trọng của `toConcurrentMap` là gì?** `CONCURRENT` và `UNORDERED`.
7. **`UNORDERED` có bảo đảm thứ tự khóa lộn xộn/ngẫu nhiên không?** Không; nó chỉ bỏ ràng buộc encounter order.
8. **`ConcurrentSkipListMap` sắp thứ tự gì?** Thứ tự **khóa** theo comparator/natural ordering, không phải thứ tự xử lý các bản ghi.
9. **Vì sao `(a,b) -> b` không đại diện chính xác cho “bản ghi mới nhất”?** Merge có thể xảy ra theo lịch thread và cách chia nguồn; cần so sánh trường version/timestamp.
10. **`ConcurrentMap<String,List<T>>` có khiến List bên trong an toàn khi nhiều thread cùng sửa không?** Không.
11. **Nếu keyMapper trả null, nên xử lý thế nào?** Lọc, thay khóa bằng trạng thái hợp lệ hoặc báo lỗi trước khi collect.
12. **Có thể cho mergeFunction trả null để giữ khóa nhưng giá trị thiếu không?** Không. Ngữ nghĩa `Map.merge` có thể xóa ánh xạ.
13. **Collector concurrent có tự biến `stream()` thành parallel stream không?** Không; chế độ do Stream quyết định.
14. **Tại sao `Long::sum` thường phù hợp hơn nối chuỗi khi merge trong unordered collector?** Phép cộng không phụ thuộc thứ tự, còn nối chuỗi thay đổi kết quả nếu đảo thứ tự.
15. **Khi nào dùng `groupingByConcurrent` thay vì `toConcurrentMap`?** Khi mỗi khóa cần tích lũy một nhóm/danh sách hoặc downstream collector riêng.
16. **Có thể so sánh hai kết quả ConcurrentMap bằng `Map.equals` không?** Có, khi mục tiêu là cùng tập cặp khóa–giá trị và giá trị có `equals` phù hợp; không so sánh thứ tự in.
17. **Nếu một SKU chiếm phần lớn dữ liệu thì điều gì có thể xảy ra?** Các cập nhật cùng khóa tạo contention và giảm lợi ích của xử lý song song.
18. **Tại sao Map trả về không tự là bất biến?** `ConcurrentMap` hỗ trợ mutation; nếu cần snapshot công bố, tạo bản sao hoặc view phù hợp sau collect.

**Ghi nhớ:** `Collectors.toConcurrentMap` tạo một **ConcurrentMap** từ các phần tử của Stream, với tùy chọn phát hiện khóa trùng, hợp nhất giá trị và chọn loại ConcurrentMap cụ thể. Collector này có đặc tính **CONCURRENT** và **UNORDERED**, nên không dùng encounter order làm quy tắc chọn “giá trị đầu/cuối”. Hãy thiết kế `mergeFunction` kết hợp được và không phụ thuộc trạng thái dùng chung, kiểm soát null, dùng đúng mapFactory, rồi đánh giá phân bố khóa và hiệu năng thực tế trước khi chọn thu thập song song.
