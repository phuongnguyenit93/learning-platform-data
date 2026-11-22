# Xây dựng chỉ mục tra cứu từ danh sách đối tượng

> **Chương:** Thu thập thành Map  
> **Module:** JAVA_STREAM_API  
> **Trọng tâm:** Dùng pipeline `filter`, `map` và `collect` của Java Stream API để chuyển danh sách đối tượng thành các chỉ mục tra cứu theo ID, email, danh mục hoặc nhiều khóa. Hiểu cách chọn `toMap`, `groupingBy`, merge function, loại Map, tính bất biến và cách kiểm tra chỉ mục khi dữ liệu hoặc cách chạy pipeline thay đổi.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt danh sách dữ liệu gốc với **chỉ mục tra cứu** dưới dạng `Map<K, V>` hoặc `Map<K, List<V>>`.
2. Xây dựng chỉ mục theo khóa duy nhất bằng `Collectors.toMap`, xử lý khóa trùng có chủ đích.
3. Dùng `Collectors.groupingBy` cho quan hệ **một khóa – nhiều đối tượng**, hoặc `toMap` với merge function khi thích hợp.
4. Tạo chỉ mục theo nhiều tiêu chí, chỉ mục lồng nhau và khóa đã chuẩn hóa.
5. Chọn `HashMap`, `LinkedHashMap`, `TreeMap` hoặc `ConcurrentMap` dựa trên yêu cầu thực tế.
6. Kiểm soát khóa `null`, giá trị `null`, đối tượng mutable, bản sao bất biến và tính nhất quán khi danh sách gốc thay đổi.
7. Kiểm tra đúng số lượng bản ghi, thứ tự, chính sách trùng khóa và tính đúng khi chạy song song.
8. Biết khi nào nên xây Map trước để tra cứu nhiều lần và khi nào chỉ cần `findFirst` hoặc `anyMatch`.

Các ví dụ dùng **Java 17+**. `Collectors.toMap` và `groupingBy` có từ Java 8; `record` cần Java 16+, `Stream.toList()` có từ Java 16. Những đoạn mã rời được hiểu là phần thân của một phương thức có các `import` tương ứng; các ví dụ hoàn chỉnh có khai báo lớp riêng.

## 1. Chỉ mục tra cứu là gì?

Giả sử ứng dụng có danh sách khách hàng:

~~~java
import java.util.List;

record Customer(long id, String email, String city, boolean active) {}

List<Customer> customers = List.of(
        new Customer(101L, "an@example.vn", "Hà Nội", true),
        new Customer(102L, "binh@example.vn", "Hồ Chí Minh", true),
        new Customer(103L, "chi@example.vn", "Hà Nội", false),
        new Customer(104L, "dung@example.vn", "Hồ Chí Minh", true)
);
~~~

Muốn tìm khách hàng có ID `103`, một cách là duyệt danh sách:

~~~java
import java.util.Optional;

Optional<Customer> found = customers.stream()
        .filter(c -> c.id() == 103L)
        .findFirst();

System.out.println(found.map(Customer::email).orElse("Không có"));
// chi@example.vn
~~~

Mỗi lần tìm kiếm theo cách này có thể phải xem xét tới `n` phần tử, tức chi phí tuyến tính **O(n)** trong trường hợp xấu nhất. Nếu ứng dụng phải tra cứu cùng danh sách rất nhiều lần, có thể tạo chỉ mục:

~~~text
List<Customer>
    ├── Customer(id=101, email="an@example.vn",   city="Hà Nội")
    ├── Customer(id=102, email="binh@example.vn", city="Hồ Chí Minh")
    ├── Customer(id=103, email="chi@example.vn",  city="Hà Nội")
    └── Customer(id=104, email="dung@example.vn", city="Hồ Chí Minh")
                  │
                  │ collect(toMap(Customer::id, identity()))
                  ▼
Map<Long, Customer>
    101 ──> Customer(101, ...)
    102 ──> Customer(102, ...)
    103 ──> Customer(103, ...)
    104 ──> Customer(104, ...)

index.get(103L) ──> Customer(103, ...)
~~~

Với Map băm thông thường và khóa có `hashCode` phân bố tốt, tra cứu `get` **thường O(1) trung bình**. Tuy nhiên không có bảo đảm O(1) cho mọi tình huống. Xây chỉ mục có chi phí ban đầu, tốn thêm bộ nhớ và đặt ra yêu cầu đồng bộ khi dữ liệu gốc thay đổi.

**Chỉ mục trong bài này là cấu trúc dữ liệu trong bộ nhớ Java**. Nó khác với index của cơ sở dữ liệu: sau khi tạo Map, Java không tự động theo dõi mọi lần sửa danh sách nguồn.

## 2. Tạo chỉ mục một khóa duy nhất với toMap

`Collectors.toMap` có dạng cơ bản:

~~~java
static <T, K, U> Collector<T, ?, Map<K, U>> toMap(
        Function<? super T, ? extends K> keyMapper,
        Function<? super T, ? extends U> valueMapper
);
~~~

- `keyMapper` lấy khóa chỉ mục từ mỗi đối tượng.
- `valueMapper` chọn giá trị lưu trong Map.
- Mỗi khóa chỉ được ánh xạ tới một giá trị theo chính sách hiện tại; overload hai tham số **ném ngoại lệ khi có khóa trùng**.

### 2.1. Chỉ mục ID → đối tượng

~~~java
import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collectors;

Map<Long, Customer> byId = customers.stream()
        .collect(Collectors.toMap(
                Customer::id,
                Function.identity()
        ));

Customer customer = byId.get(103L);

System.out.println(customer.email()); // chi@example.vn
~~~

`Function.identity()` nghĩa là **giữ nguyên đối tượng đầu vào** làm giá trị. Map chứa tham chiếu tới đối tượng `Customer`; không phải cơ chế tạo bản sao sâu (*deep copy*).

Pipeline trên có cách đọc rõ ràng:

~~~text
customers.stream()
  └── collect(toMap(Customer::id, identity()))
          ├── khóa  : c.id()
          └── giá trị: chính c
                  ↓
          Map<Long, Customer>
~~~

`toMap` là collector được truyền vào thao tác kết thúc `collect`. Dữ liệu được duyệt khi gọi `collect`, sau đó có một Map tra cứu.

### 2.2. Chỉ lưu trường cần tra cứu

Nếu nghiệp vụ chỉ cần tìm email theo ID:

~~~java
Map<Long, String> emailById = customers.stream()
        .collect(Collectors.toMap(
                Customer::id,
                Customer::email
        ));

System.out.println(emailById.get(102L)); // binh@example.vn
~~~

Điều này có thể giảm lượng dữ liệu mà chỉ mục tham chiếu, nhưng sẽ mất khả năng truy cập các trường khác qua chỉ mục đó. Giá trị của `valueMapper` có thể là một đối tượng, một chuỗi, một số hoặc một DTO đã chuyển đổi.

**Không phải cứ có khóa là dùng được `toMap` hai tham số**: cần xác nhận tính duy nhất của khóa trong nguồn và giá trị do mapper trả về phù hợp hợp đồng collector.

## 3. Khóa trùng: quyết định rõ chính sách trước khi collect

Hai bản ghi có cùng khóa có thể xuất hiện do dữ liệu lỗi, dữ liệu lịch sử, phiên bản mới hơn hoặc vì khóa được chọn vốn không duy nhất.

~~~java
import java.util.List;

List<Customer> duplicates = List.of(
        new Customer(101L, "an@example.vn", "Hà Nội", true),
        new Customer(101L, "an.new@example.vn", "Hà Nội", true)
);
~~~

Câu lệnh sau **không tạo ra một Map hợp lệ**:

~~~java
// Runtime: IllegalStateException do khóa 101 xuất hiện hai lần.
Map<Long, Customer> invalid = duplicates.stream()
        .collect(Collectors.toMap(
                Customer::id,
                java.util.function.Function.identity()
        ));
~~~

Đây là hành vi hữu ích khi **ID buộc phải duy nhất**. Không nên lặng lẽ bỏ bản ghi chỉ để làm chương trình chạy tiếp nếu vi phạm tính duy nhất là lỗi dữ liệu.

### 3.1. Báo lỗi trùng khóa có thông điệp nghiệp vụ

Overload ba tham số:

~~~java
import java.util.function.Function;
import java.util.stream.Collectors;

Map<Long, Customer> strictIndex = duplicates.stream()
        .collect(Collectors.toMap(
                Customer::id,
                Function.identity(),
                (previous, incoming) -> {
                    throw new IllegalStateException(
                            "Trùng ID khách hàng: " + previous.id()
                    );
                }
        ));
~~~

Ở đây, merge function quyết định cách xử lý khi hai giá trị có **cùng khóa**. Vì dữ liệu trùng bị coi là không hợp lệ, hàm cố ý ném ngoại lệ.

Trên Stream song song, thời điểm phát hiện và đối tượng nào được đưa vào merge có thể khác; thông báo lỗi **không nên phụ thuộc vào thứ tự xử lý** để diễn đạt nguyên nhân.

### 3.2. Giữ bản ghi đầu hoặc cuối khi nghiệp vụ cho phép

~~~java
Map<Long, Customer> keepFirst = duplicates.stream()
        .collect(Collectors.toMap(
                Customer::id,
                Function.identity(),
                (first, later) -> first
        ));

Map<Long, Customer> keepLast = duplicates.stream()
        .collect(Collectors.toMap(
                Customer::id,
                Function.identity(),
                (first, later) -> later
        ));
~~~

Với nguồn `List` có thứ tự và pipeline tuần tự, hai ví dụ cho hai chính sách rõ ràng. Nhưng **“bản ghi cuối cùng” không đồng nghĩa “bản ghi mới nhất”**: vị trí trong List không cho biết timestamp hoặc version nếu không có quy định dữ liệu đầu vào.

Nếu ý nghĩa là **chọn phiên bản mới nhất**, tốt hơn nên so sánh trường version/timestamp trực tiếp, với quy tắc xử lý khi hai bản ghi cùng phiên bản. Những phép chọn phụ thuộc thứ tự gặp phần tử không thích hợp để tùy tiện chuyển sang collector `UNORDERED` hoặc concurrent mà không xem lại hợp đồng.

### 3.3. Chọn bản ghi có revision lớn nhất với tie-break rõ ràng

~~~java
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.function.BinaryOperator;
import java.util.function.Function;
import java.util.stream.Collectors;

record Product(long id, int revision, String name) {}

List<Product> revisions = List.of(
        new Product(7L, 1, "Bút xanh"),
        new Product(7L, 3, "Bút xanh mới"),
        new Product(9L, 2, "Sổ tay")
);

// Quy tắc đã định: revision cao hơn được ưu tiên;
// nếu revision bằng nhau, tên lớn hơn theo String.compareTo được chọn.
Comparator<Product> priority =
        Comparator.comparingInt(Product::revision)
                  .thenComparing(Product::name);

BinaryOperator<Product> choosePreferred = BinaryOperator.maxBy(priority);

Map<Long, Product> latestById = revisions.parallelStream()
        .collect(Collectors.toMap(
                Product::id,
                Function.identity(),
                choosePreferred
        ));

System.out.println(latestById.get(7L).revision()); // 3
~~~

`maxBy` trên thứ tự so sánh nhất quán này giúp phép chọn không phụ thuộc việc ghép trái/phải khi các giá trị khác nhau đều phân biệt được bằng comparator. Vì `id` là khóa giống nhau trong một nhóm, `revision` và `name` xác định thứ tự ưu tiên cho dữ liệu trong ví dụ.

**Giới hạn nghiệp vụ:** Nếu hai bản ghi cùng ID và cùng revision nhưng khác nội dung, việc chọn theo tên chỉ đúng nếu đó **thật sự là quy tắc được chấp thuận**. Trong nhiều hệ thống, tốt hơn là báo xung đột version. Không nên tự đặt quy tắc ưu tiên chỉ để giải quyết lỗi dữ liệu.

## 4. Khóa không duy nhất: groupingBy tạo chỉ mục một – nhiều

Nếu muốn tra cứu **mọi khách hàng của một thành phố**, thành phố rõ ràng không phải khóa duy nhất. `toMap(Customer::city, identity())` hai tham số sẽ ném ngoại lệ khi gặp người thứ hai trong cùng thành phố.

Dùng `groupingBy`:

~~~java
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

Map<String, List<Customer>> byCity = customers.stream()
        .collect(Collectors.groupingBy(Customer::city));

System.out.println(byCity.get("Hà Nội").size()); // 2
System.out.println(byCity.get("Hồ Chí Minh").size()); // 2
~~~

Đây là chỉ mục **một khóa → nhiều phần tử**:

~~~text
"Hà Nội"        ──> [Customer(101), Customer(103)]
"Hồ Chí Minh"   ──> [Customer(102), Customer(104)]
~~~

Một số điểm cần lưu ý:

- `groupingBy` có thể cho một `Map<K, List<T>>`, giữ nhiều bản ghi trùng khóa phân loại.
- Map trả về **không có bảo đảm kiểu cài đặt, tính mutable hoặc thread-safety** trừ khi chọn overload và điều kiện cụ thể.
- `List` trong mỗi nhóm là kết quả thu thập, không nhất thiết là cấu trúc đồng bộ; đừng sửa chúng đồng thời mà không có cơ chế phù hợp.
- Khi dùng groupingBy chuẩn, **khóa phân loại phải khác null**; nếu classifier trả null, thao tác có thể ném `NullPointerException`.

### 4.1. Trả danh sách rỗng nếu không có khóa

~~~java
List<Customer> inDaNang = byCity.getOrDefault(
        "Đà Nẵng", List.of()
);

System.out.println(inDaNang.size()); // 0
~~~

`Map.get` trả `null` nếu không tìm thấy khóa (trong các Map có thể chứa null, `get` còn có thể trả null vì giá trị là null). Với chỉ mục chỉ chứa giá trị không null, `getOrDefault` rõ ràng khi muốn trả một danh sách rỗng.

### 4.2. Chỉ lưu thông tin cần dùng theo từng nhóm

Ví dụ thành phố → danh sách email:

~~~java
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

Map<String, List<String>> emailsByCity = customers.stream()
        .collect(Collectors.groupingBy(
                Customer::city,
                Collectors.mapping(
                        Customer::email,
                        Collectors.toList()
                )
        ));

System.out.println(emailsByCity.get("Hà Nội"));
// [an@example.vn, chi@example.vn]
~~~

`Collectors.mapping` là downstream collector: nó biến từng `Customer` thành `String` rồi thu thập trong nhóm tương ứng.

Nếu chỉ cần **số lượng khách hàng theo thành phố**, không cần tạo các list:

~~~java
Map<String, Long> countByCity = customers.stream()
        .collect(Collectors.groupingBy(
                Customer::city,
                Collectors.counting()
        ));

System.out.println(countByCity.get("Hà Nội")); // 2
~~~

Lựa chọn kiểu giá trị `V` của chỉ mục là quyết định thiết kế: lưu toàn bộ đối tượng, lưu một trường, lưu danh sách hoặc lưu giá trị tổng hợp.

## 5. Nhiều chỉ mục trên cùng một tập dữ liệu

Một ứng dụng có thể cần ba đường tra cứu:

- Theo ID: `Map<Long, Customer>`.
- Theo email: `Map<String, Customer>`.
- Theo thành phố: `Map<String, List<Customer>>`.

~~~java
import java.util.List;
import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collectors;

List<Customer> snapshot = List.copyOf(customers);

Map<Long, Customer> idIndex = snapshot.stream()
        .collect(Collectors.toMap(
                Customer::id, Function.identity()
        ));

Map<String, Customer> emailIndex = snapshot.stream()
        .collect(Collectors.toMap(
                Customer::email, Function.identity()
        ));

Map<String, List<Customer>> cityIndex = snapshot.stream()
        .collect(Collectors.groupingBy(Customer::city));
~~~

`List.copyOf` cho danh sách có cấu trúc không thể thay đổi và từ chối phần tử null; ở đây `Customer` là record chứa các kiểu nguyên thủy và `String` nên các trường đang dùng cũng ổn định. Với record chứa field mutable, bản sao này **không** sao chép sâu từng object.

**Quan trọng:** Ba Map được tạo từ cùng một snapshot, nhưng vẫn là **ba chỉ mục độc lập**. Khi có bản ghi mới, sửa email hoặc chuyển thành phố, các Map **không tự cập nhật**.

### 5.1. Cùng một đối tượng có thể xuất hiện trong nhiều Map

Các Map ở trên thường cùng tham chiếu đến những đối tượng `Customer` trong snapshot. Chỉ mục không nhất thiết tạo bản sao đối tượng; việc tạo thêm chỉ mục chủ yếu tăng chi phí cho cấu trúc khóa, bucket, entry và danh sách nhóm.

Nếu đối tượng là mutable, thay đổi field của đối tượng có thể làm giá trị mà Map trả về thay đổi nhưng **khóa Map cũ vẫn giữ nguyên**, dẫn đến chỉ mục email/thành phố không nhất quán. Ví dụ:

~~~text
Chỉ mục tạo lúc đầu:
   emailIndex["old@example.vn"] -> Customer(email="old@example.vn")

Sau khi sửa field email của Customer:
   emailIndex["old@example.vn"] -> Customer(email="new@example.vn")

   emailIndex["new@example.vn"] -> null   (chưa rebuild)
~~~

Đó là lý do nên ưu tiên mô hình dữ liệu bất biến cho snapshot và có chiến lược cập nhật chỉ mục rõ ràng.

## 6. Chuẩn hóa khóa để tránh tra cứu hụt

Email hoặc mã đối tác có thể được nhập với khoảng trắng và cách viết hoa khác nhau. Nếu yêu cầu nghiệp vụ cho phép so khớp không phân biệt hoa/thường, nên chuẩn hóa **cả lúc lập chỉ mục lẫn lúc tra cứu**.

~~~java
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collectors;

static String normalizedEmail(String raw) {
    return raw.strip().toLowerCase(Locale.ROOT);
}
~~~

Đặt `normalizedEmail` trong một lớp tiện ích hoặc phương thức static của lớp đang chạy. Cách dùng:

~~~java
Map<String, Customer> byNormalizedEmail = customers.stream()
        .collect(Collectors.toMap(
                customer -> normalizedEmail(customer.email()),
                Function.identity()
        ));

Customer found = byNormalizedEmail.get(
        normalizedEmail("  AN@EXAMPLE.VN ")
);

System.out.println(found.id()); // 101
~~~

Dùng `Locale.ROOT` giúp phép chuyển chữ thường nhất quán theo locale chung, tránh phụ thuộc locale máy chạy.

**Chuẩn hóa làm thay đổi quan hệ trùng khóa.** Ví dụ `"AN@EXAMPLE.VN"` và `"an@example.vn"` có thể về cùng một khóa; `toMap` hai tham số sẽ phát hiện trùng. Cần chính sách dữ liệu khi điều đó xảy ra.

Đối với địa chỉ email thực tế, quy tắc phân biệt hoa/thường của local part, Unicode, IDN và cách chuẩn hóa hợp lệ có thể phức tạp. Đoạn trên chỉ là **quy ước tìm kiếm của ứng dụng minh họa**; không nên áp nó thành quy tắc xác thực/định danh email toàn cầu.

Với mã hàng hoặc số giấy tờ, cũng cần cân nhắc việc bỏ ký tự, bỏ số 0 đầu hoặc đổi định dạng có thể làm **hai giá trị khác nhau bị nhập thành một khóa**. Chuẩn hóa chỉ đúng khi nó phù hợp định nghĩa khóa nghiệp vụ.

## 7. Chọn loại Map và kiểm soát thứ tự

Overload mặc định của `Collectors.toMap` và `groupingBy` không bảo đảm kiểu Map kết quả. Nếu cần đặc tính cụ thể, dùng overload có `mapFactory`.

### 7.1. HashMap cho tra cứu thông thường

~~~java
import java.util.HashMap;
import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collectors;

Map<Long, Customer> index = customers.stream()
        .collect(Collectors.toMap(
                Customer::id,
                Function.identity(),
                (a, b) -> {
                    throw new IllegalStateException("Duplicate ID " + a.id());
                },
                HashMap::new
        ));
~~~

`HashMap` cho tra cứu theo băm với hiệu năng trung bình tốt nếu thiết kế `equals`/`hashCode` của khóa phù hợp; nó **không cam kết thứ tự duyệt**.

### 7.2. LinkedHashMap khi cần thứ tự chèn

~~~java
import java.util.LinkedHashMap;

Map<Long, Customer> indexInEncounterOrder = customers.stream()
        .collect(Collectors.toMap(
                Customer::id,
                Function.identity(),
                (a, b) -> a,
                LinkedHashMap::new
        ));

System.out.println(indexInEncounterOrder.keySet());
// [101, 102, 103, 104] với nguồn List và pipeline tuần tự này
~~~

`LinkedHashMap` mặc định giữ thứ tự chèn. Ví dụ dùng **Stream tuần tự có thứ tự** để diễn đạt thứ tự chèn theo danh sách. Nếu hợp đồng yêu cầu thứ tự kết quả nghiêm ngặt trong mọi phương thức sử dụng, hãy thiết kế và kiểm tra riêng khi chuyển sang xử lý song song; đừng suy ra thứ tự từ `HashMap`.

### 7.3. TreeMap khi cần thứ tự khóa

~~~java
import java.util.TreeMap;

TreeMap<Long, Customer> sortedIndex = customers.stream()
        .collect(Collectors.toMap(
                Customer::id,
                Function.identity(),
                (a, b) -> a,
                TreeMap::new
        ));

System.out.println(sortedIndex.firstKey()); // 101
~~~

`TreeMap` duyệt theo **thứ tự của khóa** (natural order hoặc comparator), thường có chi phí tra cứu/chèn **O(log n)**. Comparator phải được thiết kế thận trọng: nếu coi hai khóa khác nhau là bằng nhau theo `compare(a,b) == 0`, TreeMap sẽ xử lý chúng như một khóa duy nhất.

### 7.4. Map theo yêu cầu nghiệp vụ

| Nhu cầu | Lựa chọn điển hình | Điều cần kiểm tra |
|---|---|---|
| Tra cứu ID, không cần thứ tự | `HashMap` | `equals`/`hashCode` và khóa ổn định |
| Duyệt kết quả theo thứ tự chèn | `LinkedHashMap` | Nguồn, pipeline và chính sách trùng khóa |
| Cần range query/sắp thứ tự khóa | `TreeMap` | Comparator, hiệu năng và ý nghĩa thứ tự |
| Tích lũy đồng thời theo khóa | `ConcurrentHashMap` hoặc collector concurrent chuẩn | Thread-safety, khả năng trùng khóa, thứ tự không được bảo đảm |
| Không cho sửa cấu trúc chỉ mục sau khi tạo | `toUnmodifiableMap` hoặc `Map.copyOf` | Null, duplicate, bất biến nông |

Không có loại Map nào mặc định đúng cho mọi bài toán. Chọn cấu trúc theo **đường truy cập và ràng buộc của người dùng**, rồi kiểm tra dữ liệu.

## 8. Chỉ mục lồng nhau: thành phố → ID → khách hàng

Khi cần tra cứu theo cả thành phố lẫn ID:

~~~java
import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collectors;

Map<String, Map<Long, Customer>> byCityThenId = customers.stream()
        .collect(Collectors.groupingBy(
                Customer::city,
                Collectors.toMap(
                        Customer::id,
                        Function.identity()
                )
        ));

Customer result = byCityThenId
        .getOrDefault("Hà Nội", Map.of())
        .get(103L);

System.out.println(result.email()); // chi@example.vn
~~~

Đây là chỉ mục hai cấp:

~~~text
"Hà Nội"
    ├── 101 -> Customer(101)
    └── 103 -> Customer(103)

"Hồ Chí Minh"
    ├── 102 -> Customer(102)
    └── 104 -> Customer(104)
~~~

Chỉ mục hai cấp hữu ích khi:

- Ứng dụng thường **lọc trước theo thành phố** rồi tìm ID trong nhóm.
- ID chỉ cần duy nhất **bên trong mỗi nhóm** (nếu miền dữ liệu cho phép).
- Cần lưu cấu trúc nhóm phục vụ truy cập nhiều lần.

Nếu ID đã duy nhất toàn hệ thống, tra cứu theo `idIndex.get(id)` có thể đơn giản hơn. Khi ID **không** duy nhất theo toàn hệ thống, định nghĩa rõ khóa ghép như `(tenantId, id)` hay chỉ mục lồng nhau để tránh ghi đè ngẫu nhiên.

### 8.1. Dùng record làm khóa ghép

~~~java
import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collectors;

record CityCustomerKey(String city, long id) {}

Map<CityCustomerKey, Customer> byCityAndId = customers.stream()
        .collect(Collectors.toMap(
                c -> new CityCustomerKey(c.city(), c.id()),
                Function.identity()
        ));

Customer found = byCityAndId.get(
        new CityCustomerKey("Hà Nội", 103L)
);

System.out.println(found.email()); // chi@example.vn
~~~

`record` tự sinh `equals` và `hashCode` dựa trên các component, phù hợp để tạo khóa **giá trị**. Các thành phần khóa vẫn cần bất biến về hành vi: với ví dụ này, `String` và `long` đáp ứng tốt.

## 9. Chỉ mục bất biến và vòng đời dữ liệu

Nếu Map được xây một lần để các thành phần khác **chỉ đọc**, trả chỉ mục không thể thay đổi cấu trúc giúp giảm nhầm lẫn về quyền cập nhật.

### 9.1. toUnmodifiableMap (Java 10+)

~~~java
import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collectors;

Map<Long, Customer> immutableById = customers.stream()
        .collect(Collectors.toUnmodifiableMap(
                Customer::id,
                Function.identity()
        ));

// immutableById.put(105L, anotherCustomer);
// Ném UnsupportedOperationException nếu gọi.
~~~

`toUnmodifiableMap` không chấp nhận khóa hoặc giá trị null và cũng ném ngoại lệ khi khóa trùng nếu dùng overload hai tham số.

### 9.2. Map.copyOf là bản sao cấu trúc nông

~~~java
import java.util.Map;

Map<Long, Customer> readOnlyIndex = Map.copyOf(byId);
~~~

`Map.copyOf` trả về Map không cho thay đổi cấu trúc. Nó **không tự sao chép sâu** các object làm giá trị: nếu đối tượng đích mutable, nó vẫn có thể bị thay đổi qua tham chiếu khác. `Map.copyOf` cũng không chấp nhận khóa hoặc giá trị null; thứ tự duyệt của kết quả không được bảo đảm.

So sánh ba cách:

| API | Có cho sửa Map trả về? | Có tự sao chép sâu các giá trị? |
|---|---|---|
| `Collectors.toMap` | Không có bảo đảm bất biến; thường dùng Map mutable | Không |
| `Collectors.toUnmodifiableMap` | Không | Không |
| `Map.copyOf(existingMap)` | Không | Không |

`Collections.unmodifiableMap(existing)` cũng tạo một **view** không cho sửa qua chính view đó; nếu `existing` vẫn bị sửa từ nơi khác, view có thể phản ánh thay đổi. Cách này khác với việc tạo snapshot Map theo giá trị.

## 10. Null, dữ liệu lỗi và hợp đồng khóa

Một chỉ mục tốt phải xác định rõ liệu các trường định danh có được phép null, rỗng, sai định dạng hay không.

Ví dụ yêu cầu tất cả email đều có giá trị:

~~~java
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.function.Function;
import java.util.stream.Collectors;

Map<String, Customer> safeEmailIndex = customers.stream()
        .collect(Collectors.toMap(
                c -> Objects.requireNonNull(
                        c.email(), "Email không được null, id=" + c.id()
                ),
                Function.identity()
        ));
~~~

Nếu nghiệp vụ cho phép email `null`, thường **không** nên dùng null như một khóa duy nhất gom nhiều người. Có thể chọn lọc những người có email:

~~~java
Map<String, Customer> knownEmails = customers.stream()
        .filter(c -> c.email() != null)
        .collect(Collectors.toMap(
                Customer::email,
                Function.identity()
        ));
~~~

Kết quả này **không bao gồm** khách hàng thiếu email. Nếu cần báo lỗi dữ liệu thiếu, hãy kiểm tra đầu vào và trả thông tin lỗi theo chính sách nghiệp vụ.

**Lưu ý về null:**

- `Collectors.toUnmodifiableMap` và `Map.copyOf` từ chối null.
- Với `Collectors.toMap`, không nên dựa vào khả năng dùng giá trị null; các JDK thông dụng ném `NullPointerException` khi value mapper trả null và hợp đồng không hứa hỗ trợ null.
- `Collectors.groupingBy` yêu cầu classifier cho khóa không null trong cách dùng chuẩn; muốn nhóm “không rõ thành phố”, hãy tạo một khóa đại diện rõ ràng, ví dụ `"CHƯA_XÁC_ĐỊNH"`, nếu giá trị này không xung đột với khóa thật.
- Dùng `Objects.requireNonNull` để chặn dữ liệu sai tại biên xử lý, kèm thông tin nhận diện bản ghi.

~~~java
Map<String, List<Customer>> byKnownCity = customers.stream()
        .collect(Collectors.groupingBy(
                c -> c.city() == null ? "CHƯA_XÁC_ĐỊNH" : c.city()
        ));
~~~

Với hệ thống có dữ liệu phức tạp, mô hình `Optional` hoặc một kiểu khóa đại diện trạng thái thiếu thông tin có thể rõ nghĩa hơn chuỗi sentinel.

## 11. Khóa phải ổn định: equals, hashCode và đối tượng mutable

`HashMap` sử dụng `hashCode` và `equals` của khóa để định vị entry. Nếu **trạng thái dùng để tính hashCode/equals thay đổi sau khi chèn**, lookup có thể thất bại dù vẫn đang dùng đúng tham chiếu object.

~~~java
import java.util.HashMap;
import java.util.Map;

final class MutableKey {
    String code;

    MutableKey(String code) {
        this.code = code;
    }

    @Override public boolean equals(Object other) {
        return other instanceof MutableKey k
                && java.util.Objects.equals(code, k.code);
    }

    @Override public int hashCode() {
        return java.util.Objects.hashCode(code);
    }
}

MutableKey key = new MutableKey("A");
Map<MutableKey, String> index = new HashMap<>();
index.put(key, "Sản phẩm A");

key.code = "B"; // Làm thay đổi hashCode của khóa đã được chèn.

// Có thể không tìm được kết quả mong muốn:
System.out.println(index.get(new MutableKey("B")));
~~~

Trong ví dụ, việc sửa `code` phá vỡ giả định khóa được giữ ổn định ở vị trí bucket đã chèn. Không dựa vào kết quả của `get` sau khi đã sửa khóa như một hợp đồng tin cậy.

Giải pháp:

- Dùng `String`, `Long` hoặc một `record` gồm các trường bất biến làm khóa.
- Không dùng một entity mutable làm khóa nếu các field tham gia `equals`/`hashCode` có thể thay đổi.
- Khi khóa nghiệp vụ thay đổi, **xóa entry cũ và thêm entry mới** bằng một quy trình cập nhật được kiểm soát, hoặc xây lại snapshot chỉ mục.
- Với `TreeMap`, cũng cần giữ ổn định những trường ảnh hưởng comparator.

**Phân biệt:** Sửa giá trị `Customer` của một entry không nhất thiết phá hỏng bảng băm nếu **khóa Long** không thay đổi. Nhưng việc sửa email hoặc thành phố trong `Customer` có thể làm **chỉ mục phụ** tương ứng bị lỗi thời.

## 12. Xây lại chỉ mục khi dữ liệu thay đổi

Chỉ mục trong bộ nhớ nên có vòng đời rõ ràng:

1. Nhận hoặc tải **snapshot** dữ liệu đầu vào đã được kiểm tra.
2. Tạo các Map cần thiết trên snapshot đó.
3. Công bố các Map cho bên đọc khi chúng đã xây xong.
4. Khi dữ liệu nguồn cập nhật, quyết định **xây lại toàn bộ** hoặc cập nhật từng entry theo một giao thức nhất quán.

Ví dụ xây lại immutable index từ danh sách mới:

~~~java
import java.util.List;
import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collectors;

static Map<Long, Customer> buildIdIndex(List<Customer> source) {
    return source.stream()
            .collect(Collectors.toUnmodifiableMap(
                    Customer::id,
                    Function.identity()
            ));
}
~~~

Khi danh sách nguồn có thể thay đổi do thread khác ghi, **không** chạy stream trên một collection mutable đang bị sửa đồng thời nếu collection không hỗ trợ. Nên chụp snapshot nhất quán dưới cơ chế đồng bộ phù hợp hoặc lấy snapshot bất biến từ tầng dữ liệu.

### 12.1. Nhiều chỉ mục phải nhất quán với nhau

Giả sử cần cập nhật email cho khách hàng `101`. Nếu hệ thống vừa thay email trong `byId` vừa chưa cập nhật `byEmail`, một yêu cầu đọc giữa chừng có thể thấy hai phiên bản dữ liệu.

Một giải pháp là xây **một bundle chỉ mục bất biến** rồi thay toàn bộ tham chiếu tới bundle:

~~~java
import java.util.List;
import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collectors;

record CustomerIndexes(
        Map<Long, Customer> byId,
        Map<String, Customer> byEmail
) {}

static CustomerIndexes buildIndexes(List<Customer> snapshot) {
    Map<Long, Customer> byId = snapshot.stream()
            .collect(Collectors.toUnmodifiableMap(
                    Customer::id, Function.identity()
            ));

    Map<String, Customer> byEmail = snapshot.stream()
            .collect(Collectors.toUnmodifiableMap(
                    Customer::email, Function.identity()
            ));

    return new CustomerIndexes(byId, byEmail);
}
~~~

Nếu hệ thống có nhiều thread đọc/ghi, việc công bố bundle mới cần cơ chế visibility/thread-safety thích hợp (ví dụ một `volatile` reference hoặc `AtomicReference<CustomerIndexes>`). Mỗi yêu cầu đọc nên chụp **một** reference bundle và dùng xuyên suốt yêu cầu đó. Điều này tránh việc đọc từng Map từ hai phiên bản khác nhau.

Không nên xem một vài Map mutable là “đã đồng bộ” chỉ vì từng Map dùng cấu trúc concurrent: **tính nhất quán giữa các chỉ mục** là một yêu cầu cao hơn thread-safety của từng thao tác Map.

## 13. Tạo chỉ mục bằng Collector song song

`parallelStream` có thể chia nguồn, tạo Map trung gian rồi ghép kết quả. Hợp đồng merge function trở nên đặc biệt quan trọng khi có khóa trùng.

~~~java
import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collectors;

Map<Long, Customer> parallelById = customers.parallelStream()
        .collect(Collectors.toMap(
                Customer::id,
                Function.identity()
        ));

System.out.println(parallelById.get(101L).email()); // an@example.vn
~~~

Với ID duy nhất và dữ liệu không thay đổi trong lúc chạy, đây là cách sử dụng đúng. Nhưng **parallel không bảo đảm nhanh hơn** với một danh sách nhỏ: chi phí phân chia và ghép Map trung gian có thể lớn hơn thời gian dựng Map tuần tự.

### 13.1. toConcurrentMap

~~~java
import java.util.concurrent.ConcurrentMap;
import java.util.function.Function;
import java.util.stream.Collectors;

ConcurrentMap<Long, Customer> concurrentById = customers.parallelStream()
        .collect(Collectors.toConcurrentMap(
                Customer::id,
                Function.identity()
        ));
~~~

`toConcurrentMap` tạo một collector concurrent/unordered theo hợp đồng của overload tương ứng. Dùng khi không cần encounter order và tình huống thực sự hưởng lợi từ thu thập đồng thời. **ConcurrentMap không cam kết thứ tự duyệt theo thứ tự đầu vào**.

Nếu có khóa trùng, phải chỉ định chính sách merge phù hợp, tương tự `toMap`:

~~~java
ConcurrentMap<Long, Product> latestConcurrent = revisions.parallelStream()
        .collect(Collectors.toConcurrentMap(
                Product::id,
                Function.identity(),
                choosePreferred
        ));
~~~

Trong ví dụ này, `choosePreferred` là phép chọn đã khai báo ở mục 3, dựa trên thứ tự ưu tiên rõ ràng; không cần giả định thứ tự thread quyết định bản ghi nào thắng.

### 13.2. groupingByConcurrent

~~~java
import java.util.List;
import java.util.concurrent.ConcurrentMap;
import java.util.stream.Collectors;

ConcurrentMap<String, List<Customer>> concurrentByCity =
        customers.parallelStream()
                .collect(Collectors.groupingByConcurrent(Customer::city));

System.out.println(concurrentByCity.get("Hà Nội").size()); // 2
~~~

Collector này cho phép nhóm đồng thời và **không bảo đảm thứ tự encounter order của các phần tử trong nhóm**. `ConcurrentMap` có thể là thread-safe đối với các thao tác Map, nhưng **các List giá trị không được bảo đảm an toàn cho sửa đổi đồng thời sau khi thu thập**. Nếu cần thứ tự ổn định trong mỗi nhóm, có thể chọn `groupingBy` phù hợp trên nguồn có thứ tự, hoặc sắp xếp kết quả bằng khóa sắp xếp nghiệp vụ.

### 13.3. Merge function cần hợp đồng phù hợp

Khi có nhiều kết quả trung gian cho cùng khóa, merge function nên bảo đảm dữ liệu không mất và cho kết quả đúng theo yêu cầu:

- **Cộng số nguyên chính xác:** dùng `BigInteger::add` hoặc kiểu số đủ lớn.
- **Gộp theo version:** dùng phép chọn có thứ tự ưu tiên xác định đầy đủ.
- **Gộp nhiều giá trị:** thường dùng `groupingBy`; không tự sửa một `ArrayList` chia sẻ trong parallel stream.
- **Giữ first/last:** phải xác định “first/last” theo encounter order hay theo một trường nghiệp vụ; không để thứ tự thread làm tiêu chí ngoài ý muốn.

Muốn kiểm chứng, đối chiếu Map tuần tự, Map song song và oracle độc lập, gồm trường hợp duplicate, nguồn rỗng và nhiều thứ tự dữ liệu. Với `Map<K, V>`, `Map.equals` so ánh xạ theo nội dung, không phụ thuộc thứ tự duyệt Map.

## 14. Kiểm chứng chỉ mục bằng oracle và bất biến

Đối với chỉ mục **ID duy nhất**, các bất biến cơ bản:

1. Số entry bằng số đối tượng nguồn (nếu ID thật sự duy nhất).
2. Với mỗi đối tượng nguồn `c`, `index.get(c.id())` là đối tượng có dữ liệu tương đương `c`.
3. Không tồn tại khóa ngoài nguồn.
4. Chính sách khóa trùng được kiểm tra bằng một bộ dữ liệu cố tình trùng.
5. Kết quả truy vấn của index khớp kết quả tra cứu trực tiếp từ danh sách.
6. Khi xây trên snapshot mới, chỉ mục phản ánh đúng snapshot mới.

Ví dụ helper kiểm tra:

~~~java
import java.util.List;
import java.util.Map;
import java.util.Objects;

static void verifyIdIndex(
        List<Customer> source,
        Map<Long, Customer> index) {

    if (index.size() != source.size()) {
        throw new AssertionError(
                "Số khóa không khớp số khách hàng"
        );
    }

    for (Customer expected : source) {
        Customer actual = index.get(expected.id());
        if (!Objects.equals(expected, actual)) {
            throw new AssertionError(
                    "Sai lookup cho ID " + expected.id()
            );
        }
    }
}
~~~

Hàm này giả định `Customer` là record có `equals` theo nội dung. Nếu `Customer` là class mutable không có `equals` theo dữ liệu, phải thiết kế comparator/kiểm tra từng trường hoặc so một DTO bất biến chuẩn hóa.

**Bổ sung phép thử khóa trùng** là bắt buộc nếu tính duy nhất đến từ dữ liệu bên ngoài; helper trên chỉ phát hiện sự không nhất quán với tập nguồn đã được xem là hợp lệ.

### 14.1. Kiểm tra nhóm mà không mất/nhân đôi bản ghi

~~~java
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

Map<String, List<Customer>> groups = customers.stream()
        .collect(Collectors.groupingBy(Customer::city));

long totalMembers = groups.values().stream()
        .mapToLong(List::size)
        .sum();

if (totalMembers != customers.size()) {
    throw new AssertionError("Nhóm bị mất hoặc nhân đôi khách hàng");
}
~~~

Đây là một bất biến cần thiết, nhưng **chưa đủ**: một bản ghi có thể bị gán nhầm nhóm dù tổng số vẫn bằng nhau. Hãy kiểm tra thêm mọi đối tượng trong mỗi list thực sự có `city` tương ứng với khóa và số lần xuất hiện khớp nguồn.

### 14.2. So với phép tìm trực tiếp

~~~java
import java.util.Objects;
import java.util.Optional;

long targetId = 102L;

Optional<Customer> fromList = customers.stream()
        .filter(c -> c.id() == targetId)
        .findFirst();

Optional<Customer> fromIndex =
        Optional.ofNullable(byId.get(targetId));

if (!Objects.equals(fromList, fromIndex)) {
    throw new AssertionError("Chỉ mục không khớp nguồn");
}
~~~

Chỉ mục giúp tối ưu các lần tìm kiếm sau khi đã xây xong; phép tìm trực tiếp vẫn có ích làm oracle trên bộ dữ liệu kiểm tra nhỏ. Nếu nguồn cho phép ID trùng, hai đường tra cứu phải dùng **cùng chính sách chọn** thì phép so sánh mới có ý nghĩa.

## 15. Khi nào Map có lợi hơn quét Stream mỗi lần?

Giả sử có `n` khách hàng và cần thực hiện `q` lượt tra cứu ID.

| Cách làm | Công việc điển hình | Đánh đổi |
|---|---|---|
| Mỗi lần gọi `stream().filter(...).findFirst()` | Có thể O(n) cho mỗi lượt, tổng tới O(qn) | Không tốn cấu trúc chỉ mục; luôn đọc nguồn tại thời điểm truy vấn |
| Xây `HashMap` một lần rồi `get` | Xây thường O(n), mỗi `get` trung bình O(1) | Tốn O(n) bộ nhớ bổ sung và công bảo trì chỉ mục |
| Xây `TreeMap` | Xây khoảng O(n log n), tra cứu O(log n) | Hỗ trợ thứ tự/range query theo khóa |
| `groupingBy` theo khóa không duy nhất | Duyệt nguồn để nhóm, lưu các list theo khóa | Hữu ích cho truy vấn theo nhóm; tốn bộ nhớ tham chiếu |
| Cập nhật từng bản ghi vào Map đã có | Có thể tránh xây lại toàn bộ | Phải bảo đảm đồng bộ nhiều chỉ mục và chính sách khóa |

Đây là mô hình chi phí định tính: hiệu năng thực tế phụ thuộc phân bố khóa, triển khai Map, GC, lượng dữ liệu, tần suất cập nhật và cache locality. Đừng bật `parallelStream` chỉ vì đang xây một chỉ mục; trước tiên hãy kiểm tra tính đúng và đo với dữ liệu thật.

**Khi chỉ tìm đúng một lần**, cách quét `findFirst` thường đủ rõ và có thể rẻ hơn tổng chi phí dựng Map. **Khi cần hàng nghìn lượt tra cứu trên cùng snapshot**, chỉ mục Map thường đáng cân nhắc.

## 16. Các lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Chọn email/thành phố làm khóa duy nhất khi dữ liệu có trùng | `toMap` ném `IllegalStateException` | Xác định uniqueness; dùng merge có chính sách hoặc `groupingBy` |
| Merge bằng `(old, next) -> next` mà không biết thứ tự dữ liệu | “Bản ghi thắng” không phản ánh phiên bản đúng | Dùng version/timestamp và tie-break rõ ràng |
| Chuẩn hóa khóa chỉ lúc lập chỉ mục | `get` trả null dù dữ liệu có | Cùng hàm chuẩn hóa cho cả ghi và đọc |
| Giá trị `null` trong `toMap` | Có thể ném `NullPointerException` | Kiểm tra/chuẩn hóa dữ liệu trước |
| Sửa object dùng làm khóa HashMap | Lookup không còn đáng tin cậy | Khóa bất biến, stable `equals`/`hashCode` |
| Sửa Customer sau khi tạo index theo email | Map phụ giữ khóa email cũ | Rebuild hoặc cập nhật đồng bộ |
| Coi `toUnmodifiableMap` là deep copy | Giá trị mutable vẫn có thể đổi | DTO bất biến hoặc defensive copy sâu theo nhu cầu |
| Dựa vào thứ tự duyệt của `HashMap` | Kết quả hiển thị thiếu ổn định | `LinkedHashMap` tuần tự hoặc sắp xếp theo khóa |
| `groupingByConcurrent` rồi sửa các List từ nhiều thread | Race condition | Không sửa List chia sẻ; chọn cấu trúc/phương thức đồng bộ phù hợp |
| Cùng một Stream thực hiện hai terminal operation | `IllegalStateException` | Tạo Stream mới từ snapshot có thể duyệt lại |
| Quên xử lý khóa không tồn tại | `NullPointerException` khi gọi method trên kết quả `get` | `Optional.ofNullable`, `getOrDefault` hoặc kiểm tra null |
| Chỉ so số entry trong index | Có thể vẫn gán sai khóa | Kiểm tra từng cặp khóa/giá trị và oracle |

## 17. Ví dụ hoàn chỉnh: tạo hai chỉ mục và kiểm tra

Chương trình độc lập dưới đây tạo chỉ mục duy nhất theo ID, chỉ mục nhiều giá trị theo thành phố, rồi kiểm tra kết quả đầu ra. Các đối tượng `Customer` được mô hình hóa bằng `record` bất biến theo các trường đang sử dụng.

~~~java
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.function.Function;
import java.util.stream.Collectors;

public class CustomerIndexDemo {

    record Customer(long id, String email, String city, boolean active) {}

    record Indexes(
            Map<Long, Customer> byId,
            Map<String, List<Customer>> byCity
    ) {}

    static Indexes build(List<Customer> source) {
        List<Customer> snapshot = List.copyOf(source);

        Map<Long, Customer> byId = snapshot.stream()
                .collect(Collectors.toUnmodifiableMap(
                        Customer::id,
                        Function.identity()
                ));

        Map<String, List<Customer>> grouped = snapshot.stream()
                .collect(Collectors.groupingBy(
                        Customer::city,
                        Collectors.collectingAndThen(
                                Collectors.toList(),
                                List::copyOf
                        )
                ));

        // Tạo một Map snapshot không cho sửa cấu trúc.
        Map<String, List<Customer>> byCity = Map.copyOf(grouped);

        return new Indexes(byId, byCity);
    }

    static void check(List<Customer> source, Indexes indexes) {
        if (indexes.byId().size() != source.size()) {
            throw new AssertionError("ID phải duy nhất");
        }

        for (Customer customer : source) {
            if (!Objects.equals(
                    customer,
                    indexes.byId().get(customer.id()))) {
                throw new AssertionError(
                        "Tra cứu sai cho ID " + customer.id()
                );
            }
        }

        long groupedCount = indexes.byCity().values().stream()
                .mapToLong(List::size)
                .sum();

        if (groupedCount != source.size()) {
            throw new AssertionError("Sai số khách hàng theo nhóm");
        }
    }

    public static void main(String[] args) {
        List<Customer> customers = List.of(
                new Customer(101L, "an@example.vn", "Hà Nội", true),
                new Customer(102L, "binh@example.vn", "Hồ Chí Minh", true),
                new Customer(103L, "chi@example.vn", "Hà Nội", false)
        );

        Indexes indexes = build(customers);
        check(customers, indexes);

        System.out.println(indexes.byId().get(102L).email());
        // binh@example.vn

        System.out.println(indexes.byCity().get("Hà Nội").size());
        // 2

        System.out.println("INDEX_OK");
    }
}
~~~

Ở đây, `collectingAndThen(toList(), List::copyOf)` tạo list nhóm không thể thay đổi cấu trúc. `Map.copyOf` tạo Map nhóm không cho thêm/bớt entry, phù hợp với mục đích snapshot chỉ đọc.

**Giới hạn cần hiểu:** Đây là kiểm tra cơ bản minh họa, chưa kiểm tra từng membership của nhóm theo thành phố. Với dữ liệu thực, cần bổ sung kiểm tra khóa email, khóa trùng, các ca null, số lượng lớn và quy tắc cập nhật từ nguồn. Nếu dùng kiểu đối tượng mutable trong giá trị Map, bản sao của Map không tự bảo vệ trạng thái bên trong.

## 18. Bài tập tự kiểm tra (có đáp án)

### Bài 1. Tạo chỉ mục ID

**Đề:** Cho `List<Product> products`, trong đó `record Product(long id, String name) {}` và ID duy nhất. Xây dựng `Map<Long, Product>` để tra cứu sản phẩm theo ID.

**Đáp án:**

~~~java
Map<Long, Product> byId = products.stream()
        .collect(Collectors.toMap(
                Product::id,
                Function.identity()
        ));
~~~

`Function.identity()` giữ đối tượng làm giá trị. Nếu nguồn có ID trùng, collector hai tham số ném `IllegalStateException`.

### Bài 2. Một thành phố có nhiều khách hàng

**Đề:** Nếu có hai khách hàng ở `"Hà Nội"`, có dùng `toMap(Customer::city, identity())` được không?

**Đáp án:** Không dùng overload hai tham số cho quan hệ này vì khóa trùng. Chọn `groupingBy(Customer::city)` để tạo `Map<String, List<Customer>>`.

### Bài 3. Trùng khóa do chuẩn hóa

**Đề:** `" AN@EXAMPLE.VN "` và `"an@example.vn"` sau chuẩn hóa trở thành cùng khóa. Điều gì xảy ra với `toMap` hai tham số?

**Đáp án:** Nó phát hiện khóa trùng và ném `IllegalStateException`. Cần xem hai bản ghi có thật sự cùng định danh theo quy ước nghiệp vụ không và quyết định báo lỗi, gộp hay chọn bản ghi theo tiêu chí rõ ràng.

### Bài 4. Chọn theo revision

**Đề:** Hai bản ghi cùng ID có revision 3 và 5. Cách chọn nào an toàn về mặt ý nghĩa hơn `(old, next) -> next`?

**Đáp án:** Chọn bản ghi revision cao hơn bằng comparator hoặc merge function có quy tắc rõ ràng. Nếu revision bằng nhau nhưng dữ liệu mâu thuẫn, cần chính sách tie-break hoặc báo lỗi; đừng lấy thứ tự thực thi thread làm chính sách.

### Bài 5. Kiểm tra khóa thiếu

**Đề:** `byId.get(999L)` có thể trả gì? Làm sao không bị `NullPointerException`?

**Đáp án:** Khi không có ID này, nó trả `null`. Dùng điều kiện kiểm tra, `Optional.ofNullable(byId.get(999L))` hoặc một giá trị mặc định phù hợp.

### Bài 6. Chỉ mục không tự cập nhật

**Đề:** Sau khi tạo `emailIndex`, email của khách hàng thay đổi từ `a@example.vn` sang `b@example.vn`. Gọi `emailIndex.get("b@example.vn")` có tự tìm thấy người đó không?

**Đáp án:** Không. Map không tự cập nhật khóa. Cần xây lại chỉ mục hoặc thực hiện cập nhật khóa bằng quy trình nhất quán, và bảo đảm các chỉ mục liên quan cùng dùng phiên bản dữ liệu phù hợp.

### Bài 7. Thứ tự

**Đề:** Ứng dụng phải hiển thị các ID theo thứ tự xuất hiện trong List. Nên dùng Map nào?

**Đáp án:** Có thể dùng `LinkedHashMap` qua overload `toMap(..., LinkedHashMap::new)` với Stream tuần tự có encounter order. Nếu cần thứ tự ID tăng dần, dùng `TreeMap` hoặc sắp xếp rõ ràng.

### Bài 8. Bất biến của nhóm

**Đề:** Tổng kích thước các List trong `Map<String, List<Customer>> byCity` có bằng số khách hàng nguồn không?

**Đáp án:** Nếu mỗi khách hàng được phân vào đúng một nhóm và không bị lọc/bị nhân đôi, **có**. Cần kiểm tra thêm từng khách hàng có nằm đúng thành phố để tránh PASS giả khi bản ghi bị gán sai nhóm.

### Bài 9. Nguồn có khóa null

**Đề:** Nếu `Customer.city() == null`, có nên gọi trực tiếp `groupingBy(Customer::city)` không?

**Đáp án:** Không. Nên xác nhận dữ liệu hoặc ánh xạ null thành một khóa biểu diễn trạng thái thiếu thông tin theo quy tắc ứng dụng. `groupingBy` không nhận classifier trả null trong cách dùng thông thường.

### Bài 10. Khi nào không cần Map?

**Đề:** Có 10 khách hàng và chương trình chỉ tìm một ID đúng một lần. Có nên xây `Map<Long, Customer>` không?

**Đáp án:** Không bắt buộc. `stream().filter(c -> c.id() == target).findFirst()` đơn giản và có thể đủ nhanh. Xây chỉ mục thường có lợi khi cùng tập dữ liệu phải phục vụ **nhiều** lượt lookup hoặc các thao tác truy cập theo khóa.

---

**Ghi nhớ:** Xây chỉ mục từ danh sách bằng Java Stream API là việc xác định rõ **khóa nào duy nhất, khóa nào lặp, cần lưu giá trị gì và Map được dùng trong bao lâu**. Dùng `toMap` cho lookup theo khóa duy nhất với chính sách trùng rõ ràng, `groupingBy` cho một khóa có nhiều đối tượng, và `mapFactory` khi cần cấu trúc Map cụ thể. Chuẩn hóa khóa nhất quán, giữ khóa ổn định, xử lý null, xem Map như snapshot cần bảo trì, và kiểm chứng chỉ mục bằng dữ liệu nguồn cùng các ca biên trước khi tối ưu hoặc chuyển sang song song.

