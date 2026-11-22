# Xử lý phần tử null và kết quả ánh xạ null

Trong Java Stream API, `null` có thể xuất hiện ở **hai thời điểm khác nhau**: đã có sẵn trong nguồn dữ liệu hoặc được một hàm biến đổi tạo ra. Ví dụ, một danh sách khách hàng có thể chứa phần tử `null`; ngay cả khi từng khách hàng khác `null`, trường `email` mà `map(Customer::getEmail)` trả về vẫn có thể là `null`. Nếu không xác định rõ cách xử lý, pipeline dễ ném `NullPointerException`, tạo kết quả khó hiểu hoặc gây lỗi khi thu thập bằng collector.

Bài học thuộc chương **Lọc và biến đổi phần tử** của module **JAVA_STREAM_API**. Mục tiêu là sử dụng `filter`, `map`, `flatMap` và `collect` an toàn trong pipeline lazy; đồng thời hiểu khi nào có thể dùng `Optional`, `Stream.ofNullable`, cách xử lý dữ liệu thiếu trước khi grouping và những ảnh hưởng đến hiệu năng, trạng thái và xử lý song song.

## 1. Stream có tự loại bỏ null không?

**Không.** Một `Stream<T>` của kiểu tham chiếu có thể mang phần tử `null` nếu nguồn của nó cho phép. `map` cũng có thể tạo ra `null` và phần tử đó **tiếp tục đi xuống các bước sau**; `filter` chỉ loại phần tử khi predicate trả về `false`.

```java
import java.util.Arrays;
import java.util.List;
import java.util.Objects;
import java.util.stream.Collectors;

List<String> raw = Arrays.asList("An", null, "Bình");

List<String> cleaned = raw.stream()
        .filter(Objects::nonNull)
        .collect(Collectors.toList());

System.out.println(cleaned); // [An, Bình]
```

`Objects::nonNull` là method reference cho `Objects.nonNull(value)`: trả `true` nếu giá trị khác `null`. Nó là một `Predicate<T>` phù hợp với `filter`.

Chú ý **nguồn dữ liệu**: `Arrays.asList("An", null, "Bình")` chấp nhận phần tử null, còn các factory như `List.of("An", null)` (Java 9+) sẽ ném `NullPointerException` ngay lúc tạo danh sách. Đó là lỗi ở lúc tạo nguồn, trước khi pipeline có cơ hội lọc.

### 1.1. Null ở nguồn khác null từ map

| Vị trí xuất hiện | Ví dụ | Rủi ro |
|---|---|---|
| Phần tử nguồn là `null` | `customers` chứa một khách hàng `null` | Gọi `Customer::getEmail` trên phần tử đó sẽ lỗi |
| Trường bên trong đối tượng là `null` | Khách hàng tồn tại nhưng chưa khai báo email | `map(Customer::getEmail)` tạo phần tử `null` |
| Một hàm ánh xạ chủ động trả `null` | `map(code -> lookup.get(code))` khi không tìm thấy | Các bước tiếp theo có thể không chấp nhận null |
| Phần tử của danh sách lồng nhau là `null` | Một nhóm dữ liệu chứa phần tử trống | `flatMap` không tự loại null **bên trong** các Stream con |

Hai bước lọc thường dùng giải quyết **hai vấn đề riêng**:

```java
customers.stream()
        .filter(Objects::nonNull)    // bảo vệ đối tượng Customer
        .map(Customer::getEmail)     // có thể trả về String null
        .filter(Objects::nonNull);   // bảo vệ các bước làm việc với email
```

Đoạn minh họa giả định có kiểu `Customer` cùng getter `getEmail()`. Ví dụ hoàn chỉnh về kiểu này ở phần tiếp theo.

## 2. Đặt filter trước khi truy cập phần tử

Một sai sót thường gặp là kiểm tra null **sau khi đã gọi phương thức trên null**:

```java
List<String> values = Arrays.asList("  Java  ", null, "  Stream  ");

// SAI: gặp phần tử null ở map(String::trim) sẽ ném NPE.
values.stream()
        .map(String::trim)
        .filter(Objects::nonNull)
        .collect(Collectors.toList());
```

`filter` phải đứng **trước** thao tác có thể dereference phần tử:

```java
List<String> trimmed = values.stream()
        .filter(Objects::nonNull)
        .map(String::trim)
        .collect(Collectors.toList());

System.out.println(trimmed); // [Java, Stream]
```

Trong pipeline, các thao tác trung gian `filter` và `map` thường **lazy**: đoạn `map(String::trim)` không thực thi ngay khi được khai báo. Lỗi `NullPointerException` của phiên bản sai thường phát sinh **khi thao tác kết thúc** như `collect` bắt đầu duyệt dữ liệu. Vì thế, việc khởi tạo Stream thành công không có nghĩa mọi bước biến đổi đều an toàn.

### 2.1. Null và chuỗi rỗng là hai trường hợp khác nhau

Với dữ liệu người dùng, chuỗi `""` hoặc chuỗi chỉ chứa khoảng trắng không phải `null`. Sau khi loại null, có thể tiếp tục chuẩn hóa:

```java
List<String> source = Arrays.asList(
        null, "  an@example.com  ", "", "   ", "binh@example.com");

List<String> emails = source.stream()
        .filter(Objects::nonNull)
        .map(String::trim)
        .filter(email -> !email.isEmpty())
        .collect(Collectors.toList());

System.out.println(emails);
// [an@example.com, binh@example.com]
```

`Objects::nonNull` xử lý **thiếu tham chiếu**; `isEmpty` (hoặc `isBlank` từ Java 11) xử lý **chuỗi có nội dung rỗng**. Chỉ chọn thao tác nào phù hợp với quy tắc nghiệp vụ, ví dụ hệ thống có thể muốn giữ chuỗi rỗng để biểu thị người dùng chủ động xóa giá trị.

## 3. Map trả null: ba chính sách xử lý

Phương thức `Stream.map` biến mỗi phần tử đầu vào thành **đúng một phần tử đầu ra về mặt cấu trúc**, kể cả khi hàm ánh xạ trả `null`. Nó không ngầm chuyển null thành “không có kết quả”.

Giả sử `Customer::getEmail` có thể trả về null:

```java
Stream<String> mappedEmails = customers.stream()
        .filter(Objects::nonNull)
        .map(Customer::getEmail);
// mappedEmails vẫn có thể chứa các phần tử null.
```

Trước khi chọn API, hãy xác định ý nghĩa nghiệp vụ của giá trị thiếu.

### 3.1. Bỏ qua bản ghi không có giá trị

```java
List<String> availableEmails = customers.stream()
        .filter(Objects::nonNull)
        .map(Customer::getEmail)
        .filter(Objects::nonNull)
        .collect(Collectors.toList());
```

Đây là lựa chọn gọn khi mục đích chỉ là “lấy các email thực sự có” và không cần giữ số vị trí hay ánh xạ một-một với các khách hàng gốc.

### 3.2. Thay bằng giá trị mặc định

```java
List<String> displayEmails = customers.stream()
        .filter(Objects::nonNull)
        .map(Customer::getEmail)
        .map(email -> email == null ? "(chưa có email)" : email)
        .collect(Collectors.toList());
```

Cách này giữ **một kết quả cho mỗi khách hàng hợp lệ**. Chọn giá trị mặc định có ý nghĩa với ngữ cảnh; đừng dùng chuỗi hiển thị như `"(chưa có email)"` làm dữ liệu nghiệp vụ nếu hệ thống vẫn cần phân biệt thiếu giá trị với một email thật.

Nếu muốn thất bại sớm về mặt nghiệp vụ, có thể kiểm tra tường minh:

```java
List<String> requiredEmails = customers.stream()
        .filter(Objects::nonNull)
        .map(Customer::getEmail)
        .map(email -> Objects.requireNonNull(
                email, "Email là trường bắt buộc"))
        .collect(Collectors.toList());
```

Lỗi chỉ xảy ra nếu có email null **và** terminal operation duyệt đến nó.

### 3.3. Giữ null nguyên trạng khi thực sự cần

Đôi khi dữ liệu đầu ra cần giữ nguyên số lượng phần tử, kể cả vị trí thiếu:

```java
List<String> possiblyNullEmails = customers.stream()
        .filter(Objects::nonNull)
        .map(Customer::getEmail)
        .collect(Collectors.toCollection(java.util.ArrayList::new));
```

Ở đây `ArrayList` là kiểu danh sách cụ thể hỗ trợ phần tử null. Việc **giữ null** là quyết định có chủ đích: nhiều API phía sau không cho phép null. Không nên mặc định rằng mọi collector hoặc mọi bộ sưu tập đều nhận giá trị null.

## 4. Stream.ofNullable: biến một giá trị có thể null thành 0 hoặc 1 phần tử

Từ **Java 9**, `Stream.ofNullable(value)` trả về:

- Stream chứa **một** phần tử nếu `value != null`;
- Stream **rỗng** nếu `value == null`.

```java
import java.util.stream.Stream;

System.out.println(Stream.ofNullable("Java").count());        // 1
System.out.println(Stream.ofNullable((String) null).count()); // 0
```

Phân biệt với `Stream.of((String) null)`: lời gọi này tạo một Stream có **một phần tử null**, không tạo Stream rỗng.

```java
long containsNull = Stream.of((String) null).count();      // 1
long skipsNull = Stream.ofNullable((String) null).count(); // 0
```

### 4.1. Bỏ kết quả null của map bằng flatMap

`flatMap` nhận mỗi phần tử rồi ghép các Stream con thành một Stream chung. Kết hợp nó với `Stream.ofNullable` để mỗi giá trị được ánh xạ thành **không hoặc một** phần tử:

```java
List<String> emails = customers.stream()
        .filter(Objects::nonNull)
        .flatMap(customer ->
                Stream.ofNullable(customer.getEmail()))
        .collect(Collectors.toList());
```

Tương đương về ý định với `map(Customer::getEmail).filter(Objects::nonNull)`:

```java
List<String> emails = customers.stream()
        .filter(Objects::nonNull)
        .map(Customer::getEmail)
        .filter(Objects::nonNull)
        .collect(Collectors.toList());
```

**Nên chọn cách nào?** Với một trường đơn giản, `map(...).filter(Objects::nonNull)` thường dễ đọc hơn. `Stream.ofNullable` đặc biệt hữu ích khi đang xây dựng pipeline `flatMap`, hoặc khi cần nối các giá trị tùy chọn với những nguồn có thể trả nhiều phần tử.

Lưu ý: `Stream.ofNullable` chỉ kiểm tra **đối số được truyền cho nó**. Nếu `customer` đang là null, biểu thức `customer.getEmail()` vẫn lỗi **trước khi** `ofNullable` được gọi; vì thế phải lọc đối tượng hoặc kiểm tra null ở lambda.

### 4.2. Danh sách lồng nhau có nhóm null

```java
List<List<String>> groups = Arrays.asList(
        Arrays.asList("A", null),
        null,
        Arrays.asList("B", "C"));

List<String> labels = groups.stream()
        .filter(Objects::nonNull)   // bỏ nhóm null
        .flatMap(List::stream)      // ghép phần tử trong từng nhóm
        .filter(Objects::nonNull)   // bỏ phần tử null ở bên trong nhóm
        .collect(Collectors.toList());

System.out.println(labels); // [A, B, C]
```

Lọc null ở **cấp danh sách con** không thay thế cho lọc null ở **cấp phần tử**. `flatMap` không loại null được phát ra từ các Stream con. Theo hợp đồng `flatMap`, nếu chính hàm mapper trả một **Stream null** thì nó được coi là Stream rỗng; tuy vậy, trả `Stream.empty()` tường minh thường giúp ý định rõ ràng hơn.

## 5. Optional và kết quả có thể vắng mặt

`Optional<T>` biểu thị một giá trị **có hoặc không**. Nó không chứa phần tử null: `Optional.ofNullable(null)` trả về `Optional.empty()`, trong khi `Optional.of(null)` ném `NullPointerException`.

```java
import java.util.Optional;

Optional<String> missing = Optional.ofNullable((String) null);
System.out.println(missing.isPresent()); // false
```

Nếu mapper trả về `Optional<String>`, `map` bình thường sẽ tạo `Stream<Optional<String>>`. Từ Java 9, `Optional.stream()` giúp chuyển mỗi Optional thành Stream 0 hoặc 1 phần tử:

```java
List<String> normalized = customers.stream()
        .filter(Objects::nonNull)
        .flatMap(customer -> Optional.ofNullable(customer.getEmail())
                .map(String::trim)
                .filter(email -> !email.isEmpty())
                .stream())
        .collect(Collectors.toList());
```

`Optional.map` cũng có tính chất đặc biệt: khi hàm ánh xạ trả null, kết quả là `Optional.empty()`. Đây là cách **Optional** xử lý null, không phải quy tắc của `Stream.map`.

Đối với phép biến đổi một trường đơn giản, `Optional` có thể thêm độ phức tạp không cần thiết. Nó phù hợp khi API đã trả Optional, khi có nhiều bước xử lý tùy chọn hoặc muốn biểu diễn rõ ràng kết quả có thể thiếu ở ranh giới phương thức.

### 5.1. findFirst/findAny không biểu diễn kết quả null

Một bẫy ít rõ ràng:

```java
// Có thể ném NPE: phần tử được chọn là null.
Stream.of((String) null).findFirst();

// An toàn: giá trị null được bỏ trước khi tìm.
Optional<String> first = Stream.of((String) null, "A")
        .filter(Objects::nonNull)
        .findFirst(); // Optional[A]
```

`findFirst` và `findAny` trả `Optional<T>`, vốn không chứa được null. Nếu phần tử được chọn là null, lời gọi có thể ném `NullPointerException`. Đừng suy luận rằng `Optional` tự bỏ mọi phần tử null trong một Stream đầu vào. Cần lọc hoặc chuẩn hóa trước thao tác kết thúc.

## 6. Ví dụ hoàn chỉnh: làm sạch email khách hàng

Chương trình dưới đây chạy trên **Java 9 trở lên** (do dùng `Stream.ofNullable`). Nó phân biệt khách hàng null, email null, chuỗi trắng và danh mục null; vừa tạo danh sách email chuẩn hóa vừa thống kê dữ liệu chưa hợp lệ. Các thao tác sử dụng dữ liệu bất biến trong quá trình duyệt.

```java
import java.util.Arrays;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class NullSafeStreamDemo {
    static final class Customer {
        private final String name;
        private final String email;
        private final String region;

        Customer(String name, String email, String region) {
            this.name = name;
            this.email = email;
            this.region = region;
        }

        String getName()   { return name; }
        String getEmail()  { return email; }
        String getRegion() { return region; }
    }

    public static void main(String[] args) {
        List<Customer> customers = Arrays.asList(
                new Customer("An", " AN@EXAMPLE.COM ", "Bắc"),
                null,
                new Customer("Bình", null, "Bắc"),
                new Customer("Chi", "   ", null),
                new Customer("Dũng", " dung@example.com ", "Nam")
        );

        // Bỏ khách hàng null trước khi gọi getter.
        // Bỏ tiếp email null trước khi trim/toLowerCase.
        List<String> normalizedEmails = customers.stream()
                .filter(Objects::nonNull)
                .map(Customer::getEmail)
                .filter(Objects::nonNull)
                .map(String::trim)
                .filter(email -> !email.isEmpty())
                .map(email -> email.toLowerCase(Locale.ROOT))
                .collect(Collectors.toList());

        System.out.println(normalizedEmails);
        // [an@example.com, dung@example.com]

        // Hai khách hàng thực sự tồn tại nhưng chưa có email hợp lệ.
        long missingEmailCount = customers.stream()
                .filter(Objects::nonNull)
                .filter(customer -> customer.getEmail() == null
                        || customer.getEmail().trim().isEmpty())
                .count();
        System.out.println(missingEmailCount); // 2

        // Lấy các vùng đã được cung cấp bằng Java 9+.
        List<String> regions = customers.stream()
                .filter(Objects::nonNull)
                .flatMap(customer -> Stream.ofNullable(customer.getRegion()))
                .collect(Collectors.toList());
        System.out.println(regions); // [Bắc, Bắc, Nam]

        // Cần lọc region null trước khi groupingBy.
        Map<String, Long> countsByRegion = customers.stream()
                .filter(Objects::nonNull)
                .filter(customer -> customer.getRegion() != null)
                .collect(Collectors.groupingBy(
                        Customer::getRegion,
                        Collectors.counting()));
        System.out.println(countsByRegion.get("Bắc")); // 2
        System.out.println(countsByRegion.get("Nam")); // 1

        Optional<String> firstValidEmail = customers.stream()
                .filter(Objects::nonNull)
                .flatMap(customer -> Stream.ofNullable(customer.getEmail()))
                .map(String::trim)
                .filter(email -> !email.isEmpty())
                .findFirst();

        System.out.println(firstValidEmail.orElse("(không có)"));
        // AN@EXAMPLE.COM
    }
}
```

Vì đầu vào là `List` có thứ tự và pipeline ở chế độ tuần tự, thứ tự email trong ví dụ được giữ như lúc xuất hiện trong danh sách sau lọc. Thứ tự hiển thị khi duyệt các khóa của `Map` từ `groupingBy` không được bảo đảm; ví dụ dùng `get` theo khóa để không phụ thuộc thứ tự đó.

## 7. Null trong các terminal operation và collector

Không phải mọi điểm kết thúc pipeline đều có cùng hợp đồng về null. Nên xử lý null **trước khi** chuyển dữ liệu cho các API có yêu cầu chặt chẽ.

| API/bước xử lý | Điều cần lưu ý |
|---|---|
| `collect(Collectors.toList())` | Trả về một `List` nhưng không cam kết kiểu, khả năng sửa đổi hoặc các thuộc tính khác; nên lọc null nếu downstream không chấp nhận |
| `collect(Collectors.toCollection(ArrayList::new))` | Chỉ định `ArrayList`; có thể chủ động giữ phần tử null |
| `collect(Collectors.toUnmodifiableList())` (Java 10+) | Ném `NullPointerException` nếu giá trị thu thập là null |
| `collect(Collectors.toMap(keyMapper, valueMapper))` | Giá trị map được tạo ra không được null; cần lọc/chuẩn hóa trước; khóa cũng nên có hợp đồng không null rõ ràng |
| `collect(Collectors.groupingBy(classifier))` | Classifier trả null sẽ gây `NullPointerException`; lọc hoặc thay nhãn nhóm trước |
| `findFirst()` / `findAny()` | Phần tử được chọn là null có thể gây `NullPointerException` |
| `mapToInt(Integer::intValue)` | Gặp phần tử null sẽ lỗi khi unboxing; lọc trước khi chuyển sang primitive stream |
| `sorted()` | Thứ tự tự nhiên thường không xử lý null; nếu cần xếp null, dùng Comparator phù hợp |

### 7.1. toMap: lọc thiếu khóa/giá trị trước khi thu thập

```java
// Giả định Customer::getName() là khóa, getEmail() là giá trị.
Map<String, String> byName = customers.stream()
        .filter(Objects::nonNull)
        .filter(customer -> customer.getName() != null)
        .filter(customer -> customer.getEmail() != null)
        .collect(Collectors.toMap(
                Customer::getName,
                Customer::getEmail));
```

Đoạn trên còn đòi hỏi **khóa không trùng nhau**; nếu có tên trùng nhau, overload `toMap` hai tham số sẽ ném `IllegalStateException`. Có thể cung cấp hàm gộp khi trùng khóa, nhưng xử lý trùng khóa là một yêu cầu khác với xử lý null.

### 7.2. groupingBy: quyết định chính sách cho nhóm thiếu khóa

```java
Map<String, Long> counts = customers.stream()
        .filter(Objects::nonNull)
        .collect(Collectors.groupingBy(
                customer -> customer.getRegion() == null
                        ? "CHƯA_XÁC_ĐỊNH"
                        : customer.getRegion(),
                Collectors.counting()));
```

Cách này **giữ khách hàng thiếu vùng** vào một nhóm riêng. Nếu quy tắc nghiệp vụ yêu cầu bỏ khách hàng đó, dùng `filter(customer -> customer.getRegion() != null)` trước `groupingBy` thay vì đặt nhãn mặc định.

### 7.3. sorted: cần phân biệt đối tượng null và khóa null

```java
import java.util.Comparator;

// Cho phép chính phần tử String là null, đặt null cuối cùng.
List<String> ordered = Arrays.asList("B", null, "A").stream()
        .sorted(Comparator.nullsLast(Comparator.naturalOrder()))
        .collect(Collectors.toList());
// [A, B, null]

// Với Customer khác null nhưng tên có thể null:
Comparator<Customer> byNullableName = Comparator.comparing(
        Customer::getName,
        Comparator.nullsLast(String.CASE_INSENSITIVE_ORDER));
```

Nếu `Customer` cũng có thể null, phải thêm một lớp xử lý null bên ngoài, ví dụ `Comparator.nullsLast(byNullableName)`; chỉ dùng comparator cho khóa tên không bảo vệ việc gọi getter trên một Customer null.

### 7.4. Unboxing không tự thay null bằng 0

```java
List<Integer> input = Arrays.asList(1, null, 3);

int sum = input.stream()
        .filter(Objects::nonNull)
        .mapToInt(Integer::intValue)
        .sum();

System.out.println(sum); // 4
```

Không nên viết `mapToInt(Integer::intValue)` trực tiếp nếu đầu vào có thể null. Null không có một đại diện ngầm định trong `IntStream`; nếu muốn coi null như `0`, hãy chọn chính sách đó một cách tường minh, ví dụ `mapToInt(value -> value == null ? 0 : value)`.

## 8. Thứ tự, tính lazy và xử lý song song

Pipeline chứa `filter(Objects::nonNull)` và `map` thường được xử lý **theo nhu cầu** của thao tác kết thúc. Điều này giúp bỏ qua đối tượng null mà không tạo danh sách trung gian, nhưng cũng có ba hệ quả:

1. **Giữ nguyên dữ liệu gốc**: `filter` tạo một chuỗi phần tử được nhìn qua Stream; nó không tự xóa phần tử null khỏi `List` nguồn.
2. **Không đoán số lần gọi mapper từ tác dụng phụ**: với thao tác ngắn mạch như `findFirst` và các tối ưu có thể bỏ qua thao tác trung gian, việc ghi log, tăng biến đếm hoặc sửa dữ liệu trong `map` không phải cách đáng tin để theo dõi số phần tử.
3. **Hàm xử lý nên không có trạng thái dùng chung**: các lambda dựa vào biến mutable hoặc thay đổi nguồn trong lúc duyệt dễ gây lỗi, nhất là khi bật `parallel()`.

```java
// Khai báo một pipeline an toàn khi chỉ cần các tên không null.
List<String> names = customers.parallelStream()
        .filter(Objects::nonNull)
        .map(Customer::getName)
        .filter(Objects::nonNull)
        .collect(Collectors.toList());
```

Ví dụ chỉ đọc dữ liệu và không chia sẻ bộ tích lũy mutable bên ngoài; collector điều phối việc thu thập. Tuy nhiên, `parallelStream()` không mặc nhiên nhanh hơn trên danh sách nhỏ, vì còn chi phí chia công việc và gộp kết quả. Với nguồn có encounter order như `List`, `filter` và `map` không tự đảo thứ tự, nhưng `parallelStream().forEach(...)` không bảo đảm thứ tự **thực thi hành động**.

Không dùng `peek` để “xử lý null” bằng cách sửa đối tượng tại chỗ. `peek` là thao tác quan sát và vẫn lazy; nó không thay thế cho lọc hay ánh xạ có quy tắc rõ ràng.

## 9. Những lỗi thường gặp

| Cách viết dễ sai | Vì sao sai hoặc dễ gây hiểu nhầm | Hướng xử lý |
|---|---|---|
| `stream.map(String::trim).filter(Objects::nonNull)` | `trim` đã dereference null trước khi lọc | Đặt `filter(Objects::nonNull)` trước `map` |
| `customers.map(Customer::getEmail)` khi có Customer null | Gọi getter trên tham chiếu null | Lọc đối tượng null trước |
| Nghĩ `map` trả null sẽ tự biến mất | `Stream.map` giữ một phần tử null | Lọc sau `map` hoặc dùng `flatMap(Stream::ofNullable)` |
| `Stream.of((String) null)` với mong muốn có Stream rỗng | Đây là Stream một phần tử null | Dùng `Stream.ofNullable` (Java 9+) |
| `findFirst` trên Stream có null đứng đầu | Không biểu diễn được null bằng `Optional` | Lọc null trước khi tìm |
| `groupingBy` với classifier có thể null | Classifier null gây lỗi | Chọn bỏ bản ghi hay gán khóa nhóm mặc định |
| `toMap` với value mapper trả null | Thu thập có thể ném `NullPointerException` | Lọc hoặc chuẩn hóa giá trị |
| `mapToInt(Integer::intValue)` với phần tử null | Unboxing null gây lỗi | Lọc null hoặc áp dụng quy tắc mặc định tường minh |
| Dùng `List.of` với null để tạo dữ liệu thử | Factory không cho phần tử null | Dùng `Arrays.asList` khi cố tình kiểm thử null |
| Lọc null mà không xét yêu cầu nghiệp vụ | Có thể làm mất bản ghi cần báo lỗi hoặc giữ vị trí | Chọn rõ: bỏ qua, thay mặc định, giữ hay từ chối |

## 10. Bài tập vận dụng

### Bài 1: Lọc và chuẩn hóa mã

Đầu vào:

```java
List<String> codes = Arrays.asList(null, " ab1 ", "", "  ", "CD2");
```

Yêu cầu: bỏ null và chuỗi trắng, chuyển thành chữ in hoa. Một đáp án Java 8:

```java
List<String> result = codes.stream()
        .filter(Objects::nonNull)
        .map(String::trim)
        .filter(code -> !code.isEmpty())
        .map(code -> code.toUpperCase(Locale.ROOT))
        .collect(Collectors.toList());
// [AB1, CD2]
```

### Bài 2: Chọn giá trị từ một hàm lookup có thể trả null

Giả sử `Map<String, Integer> prices` chứa giá theo mã và `codes` có những mã không tìm thấy. Hãy tạo danh sách các giá tồn tại:

```java
Map<String, Integer> prices = new java.util.HashMap<>();
prices.put("A", 10);
prices.put("B", 20);

List<String> lookupCodes = Arrays.asList("A", "Z", null, "B");

List<Integer> existingPrices = lookupCodes.stream()
        .filter(Objects::nonNull)
        .map(prices::get)            // Z -> null
        .filter(Objects::nonNull)
        .collect(Collectors.toList());
// [10, 20]
```

### Bài 3: Nhận biết vị trí lọc đúng

Với `Arrays.asList(null, "  A  ")`, vì sao `map(String::trim).filter(Objects::nonNull)` không an toàn? Đáp án: vì `String::trim` được gọi trên null khi terminal operation duyệt phần tử đầu; cần đưa `filter(Objects::nonNull)` lên trước.

### Bài 4: Giữ số lượng kết quả

Nguồn `Arrays.asList("A", null, "C")` cần cho ra `["A", "CHƯA_CÓ", "C"]`. Có nên dùng `filter(Objects::nonNull)`? Không, vì như vậy mất vị trí thứ hai. Dùng:

```java
List<String> labels = Arrays.asList("A", null, "C").stream()
        .map(value -> value == null ? "CHƯA_CÓ" : value)
        .collect(Collectors.toList());
// [A, CHƯA_CÓ, C]
```

### Bài 5: Thiết kế nhóm cho dữ liệu thiếu

Nếu `Customer::getRegion` trả null, `groupingBy(Customer::getRegion)` có phù hợp không? Không; phải chọn một chính sách: bỏ các khách hàng thiếu vùng trước khi grouping, hoặc ánh xạ null sang một khóa nhóm như `"CHƯA_XÁC_ĐỊNH"` để thống kê riêng. Việc lựa chọn phụ thuộc yêu cầu báo cáo.

## 11. Nguyên tắc chọn cách xử lý

Khi thiết kế pipeline, hãy hỏi lần lượt: **phần tử nguồn có thể null không**, **hàm ánh xạ có thể trả null không**, và **kết quả thiếu mang ý nghĩa nghiệp vụ gì**. Lọc bằng `Objects::nonNull` trước mọi thao tác dereference, rồi kiểm tra đầu ra của `map` nếu mapper có thể trả null. Dùng `Stream.ofNullable` hoặc `Optional.stream` khi muốn biểu diễn việc một giá trị tùy chọn tạo **0 hoặc 1 phần tử**. Trước `findFirst`, unboxing, `groupingBy`, `toMap` hoặc collector không chấp nhận null, hãy chuẩn hóa dữ liệu theo hợp đồng của API đích. Cách này giúp pipeline Stream vừa khai báo rõ ý định, vừa tránh lỗi bị trì hoãn đến lúc terminal operation thực thi.
