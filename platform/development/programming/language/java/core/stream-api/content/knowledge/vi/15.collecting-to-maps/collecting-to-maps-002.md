# Xử lý khóa trùng bằng hàm merge

Khi chuyển một `Stream<T>` thành `Map<K,V>`, không phải lúc nào mỗi phần tử cũng tạo ra một khóa duy nhất. Danh sách giao dịch có nhiều giao dịch của cùng khách hàng, các dòng log có cùng mã lỗi, hoặc dữ liệu nhập từ nhiều nguồn có thể chứa cùng mã sản phẩm. Khi đó, câu hỏi quan trọng không chỉ là **dùng khóa gì**, mà còn là **hai giá trị có cùng khóa phải được kết hợp như thế nào**.

Bài học thuộc chương **Thu thập thành Map** của module `JAVA_STREAM_API`. Ta sẽ học cách dùng `Collectors.toMap` với `mergeFunction`, lựa chọn giữa giữ giá trị đầu, giữ giá trị sau, cộng dồn, chọn bản ghi theo tiêu chí hoặc báo lỗi; đồng thời xét rõ các hợp đồng về trạng thái, tính kết hợp khi xử lý song song, `null`, thứ tự khóa và chi phí hiệu năng. Chủ đề này nối tiếp tư duy pipeline lazy gồm `filter`, `map`, `collect` và những tình huống phải lựa chọn `groupingBy` hoặc `toConcurrentMap`.

> Các biến thể `Collectors.toMap` và `Collectors.toConcurrentMap` được trình bày ở đây có từ **Java 8**. Các ví dụ chủ yếu dùng `Arrays.asList` và `Collectors` để có thể áp dụng cho dự án Java 8.

## 1. Vì sao khóa trùng là một vấn đề?

Giả sử có các dòng số lượng theo mã hàng:

```text
("P01", 3)
("P02", 5)
("P01", 7)
```

Nếu mỗi dòng trở thành một mục trong Map, ta sẽ gặp hai giá trị cho cùng khóa `"P01"`. Nhưng Map chỉ lưu **một giá trị ứng với một khóa tại một thời điểm**.

Tùy nghiệp vụ, kết quả đúng có thể là:

- `P01 → 3`: giữ bản ghi đầu tiên;
- `P01 → 7`: giữ bản ghi sau;
- `P01 → 10`: cộng số lượng;
- `P01 → [3, 7]`: giữ toàn bộ giá trị, lúc này `groupingBy` thường phù hợp hơn;
- Báo lỗi: khóa `P01` xuất hiện lặp ngoài dự kiến.

Không có chiến lược mặc định nào đúng cho mọi bài toán. **Quy tắc xử lý khóa trùng là một phần của yêu cầu nghiệp vụ** và cần được thể hiện trong code thay vì dựa vào kết quả tình cờ của Map.

## 2. toMap hai tham số: chỉ phù hợp khi khóa không trùng

Phương thức thường gặp:

```java
Collectors.toMap(keyMapper, valueMapper)
```

Trong đó `keyMapper` lấy khóa từ một phần tử, còn `valueMapper` lấy giá trị. Ví dụ mỗi chuỗi tên sản phẩm là duy nhất:

```java
import java.util.Arrays;
import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collectors;

Map<String, Integer> lengths = Arrays.asList(
        "Java", "Stream", "API"
).stream().collect(
        Collectors.toMap(
                Function.identity(),
                String::length
        )
);

System.out.println(lengths.get("Stream")); // 6
```

Nhưng khi `keyMapper` tạo khóa trùng, overload hai tham số **ném `IllegalStateException`**, chứ không tự động chọn giá trị đầu hay cuối:

```java
// Chạy sẽ ném IllegalStateException do "java" xuất hiện hai lần.
Map<String, Integer> invalid = Arrays.asList(
        "java", "JAVA"
).stream().collect(
        Collectors.toMap(
                word -> word.toLowerCase(java.util.Locale.ROOT),
                String::length
        )
);
```

Điều kiện trùng thông thường của `HashMap` dựa vào `equals` và `hashCode` của khóa, nhưng **cách xác định hai khóa có tương đương hay không còn phụ thuộc loại Map được sử dụng**. Ví dụ `TreeMap` xem hai khóa là tương đương nếu comparator cho kết quả bằng 0. Vì thế, quy tắc chuẩn hóa khóa và Map supplier là hai yếu tố cần cân nhắc.

Nếu việc trùng khóa là lỗi dữ liệu, overload hai tham số là một lựa chọn hữu ích: nó giúp phát hiện vi phạm thay vì âm thầm mất dữ liệu.

## 3. toMap ba tham số: chỉ định mergeFunction

Cú pháp giải quyết khóa trùng:

```java
Collectors.toMap(
        keyMapper,
        valueMapper,
        mergeFunction
)
```

Ở mức kiểu dữ liệu, `mergeFunction` là một `BinaryOperator<U>`: nhận **hai giá trị cùng kiểu U** cho cùng một khóa và trả về **một giá trị U** sau khi gộp.

```text
                Phần tử T
                   |
          +--------+--------+
          |                 |
    keyMapper(T)      valueMapper(T)
          |                 |
       khóa K             giá trị U
          |                 |
          +--------+--------+
                   |
               Map<K,U>
                   |
        nếu K đã có giá trị
                   |
       mergeFunction(oldU, newU)
                   |
             U sau khi gộp
```

Ví dụ đếm số lần mỗi từ xuất hiện, không cần đưa các từ vào danh sách trung gian:

```java
import java.util.Arrays;
import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collectors;

Map<String, Long> counts = Arrays.asList(
        "java", "stream", "java", "api", "stream", "java"
).stream().collect(
        Collectors.toMap(
                Function.identity(), // key: chính từ đang xét
                word -> 1L,          // mỗi lần xuất hiện có giá trị 1
                Long::sum            // cộng khi trùng khóa
        )
);

System.out.println(counts.get("java"));   // 3
System.out.println(counts.get("stream")); // 2
System.out.println(counts.get("api"));    // 1
```

Ở mỗi lần gặp `"java"`, Map cần giữ một giá trị tổng hợp; `Long::sum` gộp phần hiện có với phần mới. Khi chạy song song, hai giá trị đưa vào merge có thể là **hai kết quả tổng hợp từ hai nhánh**, không nhất thiết một bên là giá trị trực tiếp của một phần tử nguồn.

Đây là chi tiết rất quan trọng: hàm merge phải gộp được **các kết quả từng phần**, chứ không được chỉ đúng khi một đầu vào là “dòng dữ liệu mới nhất”.

## 4. Ba chính sách xử lý trùng phổ biến

Ta dùng dữ liệu có khác biệt chữ hoa/chữ thường:

```java
import java.util.Arrays;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collectors;

List<String> users = Arrays.asList(
        "Alice@EXAMPLE.COM",
        "bob@example.com",
        "alice@example.com"
);
```

### 4.1. Giữ giá trị đầu tiên

```java
Map<String, String> firstByEmail = users.stream()
        .collect(Collectors.toMap(
                email -> email.toLowerCase(Locale.ROOT),
                Function.identity(),
                (existing, incoming) -> existing
        ));

System.out.println(firstByEmail.get("alice@example.com"));
// Alice@EXAMPLE.COM
```

`(existing, incoming) -> existing` giữ giá trị đã có khi xử lý theo thứ tự. Trong ví dụ này, pipeline **tuần tự** đọc một `List` có encounter order, nên bản ghi đầu cho khóa chuẩn hóa được giữ lại.

### 4.2. Giữ giá trị đến sau

```java
Map<String, String> lastByEmail = users.stream()
        .collect(Collectors.toMap(
                email -> email.toLowerCase(Locale.ROOT),
                Function.identity(),
                (existing, incoming) -> incoming
        ));

System.out.println(lastByEmail.get("alice@example.com"));
// alice@example.com
```

`(existing, incoming) -> incoming` thay giá trị cũ bằng giá trị mới. Đây có thể là quy tắc hợp lệ nếu danh sách đã được **sắp xếp theo thời gian tăng dần** và bản ghi xuất hiện sau phải ghi đè bản ghi trước.

**Không nên mặc định “existing là bản ghi sớm nhất” hoặc “incoming là bản ghi mới nhất” khi nguồn unordered hoặc dùng concurrent collector**. Nếu thời gian của bản ghi thực sự quan trọng, hãy so sánh trường thời gian một cách tường minh; làm như vậy giúp logic ít phụ thuộc vào thứ tự duyệt.

### 4.3. Báo lỗi với thông điệp nghiệp vụ

```java
Map<String, String> strict = users.stream()
        .collect(Collectors.toMap(
                email -> email.toLowerCase(Locale.ROOT),
                Function.identity(),
                (existing, incoming) -> {
                    throw new IllegalArgumentException(
                            "Trùng email: " + existing + " / " + incoming
                    );
                }
        ));
```

Đoạn mã trên **cố ý ném ngoại lệ** vì danh sách có khóa trùng. Dùng cách này khi một khóa xuất hiện nhiều lần biểu thị lỗi nhập liệu phải dừng xử lý.

Nếu chỉ cần lỗi mặc định, `toMap(keyMapper, valueMapper)` đã đủ. Hàm ném ngoại lệ tùy chỉnh hữu ích khi cần thông báo có thêm ngữ cảnh về hai giá trị xung đột.

## 5. Cộng dồn giá trị bằng mergeFunction

Một ví dụ nghiệp vụ thường gặp là cộng số lượng hoặc doanh thu theo khóa. Tạo lớp bất biến đơn giản, tương thích Java 8:

```java
import java.math.BigDecimal;

final class Payment {
    private final String customerId;
    private final BigDecimal amount;

    Payment(String customerId, String amount) {
        this.customerId = customerId;
        this.amount = new BigDecimal(amount);
    }

    String customerId() {
        return customerId;
    }

    BigDecimal amount() {
        return amount;
    }
}
```

Thu thập doanh thu theo khách hàng:

```java
import java.math.BigDecimal;
import java.util.Arrays;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

List<Payment> payments = Arrays.asList(
        new Payment("C01", "12.50"),
        new Payment("C02", "8.00"),
        new Payment("C01", "7.25")
);

Map<String, BigDecimal> revenue = payments.stream()
        .collect(Collectors.toMap(
                Payment::customerId,
                Payment::amount,
                BigDecimal::add
        ));

System.out.println(revenue.get("C01")); // 19.75
System.out.println(revenue.get("C02")); // 8.00
```

Ở đây, `BigDecimal::add` tạo **giá trị BigDecimal mới** mà không sửa đối tượng cũ. Phép gộp cộng thỏa yêu cầu nghiệp vụ, hoạt động với cả hai giá trị đơn lẻ lẫn tổng cục bộ.

Một biến thể đếm số lượng theo mã bằng `Integer::sum` cũng khả thi, nhưng cần để ý **tràn số**. Với dữ liệu lớn, giá trị kiểu `long` thường có miền chứa rộng hơn `int`; khi tổng có thể vượt `long`, cần chính sách khác như `BigInteger` hay phát hiện tràn.

### Vì sao không dùng (a, b) -> a - b?

```java
// Không dùng cách này để tổng hợp kết quả theo khóa có thể chạy parallel:
(existing, incoming) -> existing - incoming
```

Phép trừ **không có tính kết hợp**: `(10 - 3) - 2` khác `10 - (3 - 2)`. Với parallel stream, các nhánh có thể được gộp theo nhóm khác nhau, làm kết quả phụ thuộc kế hoạch thực thi. Cũng không dùng mergeFunction có tác dụng phụ lên biến ngoài, trừ khi có mô hình đồng bộ và nghiệp vụ rõ ràng; thông thường hãy thiết kế hàm thuần, không phụ thuộc trạng thái bên ngoài.

## 6. Chọn bản ghi ưu tiên theo quy tắc, không theo vị trí

Nếu khóa trùng là tình huống hợp lệ nhưng ta cần giữ bản ghi theo **thời điểm cập nhật**, hãy đưa tiêu chí đó vào mergeFunction. Dưới đây là một lớp sự kiện đơn giản:

```java
import java.time.Instant;

final class ProductUpdate {
    private final String productId;
    private final Instant updatedAt;
    private final String revisionId;

    ProductUpdate(String productId, String time, String revisionId) {
        this.productId = productId;
        this.updatedAt = Instant.parse(time);
        this.revisionId = revisionId;
    }

    String productId() { return productId; }
    Instant updatedAt() { return updatedAt; }
    String revisionId() { return revisionId; }
}
```

Chọn bản ghi mới nhất, với `revisionId` dùng làm khóa phụ để phân xử khi trùng thời điểm:

```java
import java.util.Arrays;
import java.util.Comparator;
import java.util.Map;
import java.util.function.BinaryOperator;
import java.util.function.Function;
import java.util.stream.Collectors;

Comparator<ProductUpdate> priority = Comparator
        .comparing(ProductUpdate::updatedAt)
        .thenComparing(ProductUpdate::revisionId);

BinaryOperator<ProductUpdate> chooseLatest =
        BinaryOperator.maxBy(priority);

Map<String, ProductUpdate> latest = Arrays.asList(
        new ProductUpdate("P01", "2026-01-01T00:00:00Z", "a"),
        new ProductUpdate("P01", "2026-01-02T00:00:00Z", "b"),
        new ProductUpdate("P02", "2026-01-01T00:00:00Z", "c")
).stream().collect(
        Collectors.toMap(
                ProductUpdate::productId,
                Function.identity(),
                chooseLatest
        )
);

System.out.println(latest.get("P01").revisionId()); // b
```

Hàm `maxBy` luôn chọn kết quả có độ ưu tiên cao hơn, không phụ thuộc việc sự kiện đó đi trước hay sau trong nguồn. Nếu comparator không tạo được thứ tự ưu tiên **duy nhất** giữa các bản ghi khác nhau, việc chọn bản ghi khi hòa điểm vẫn có thể phụ thuộc cách gộp. Khi kết quả cần quyết định hoàn toàn, nên bổ sung khóa phụ ổn định và duy nhất hoặc quy định rõ chính sách xử lý hòa.

**Khác biệt với giữ bản ghi cuối:** một nguồn có thể không được sắp theo thời gian, đặc biệt khi ghép từ nhiều tệp hoặc truy vấn song song. Quy tắc dựa trên thuộc tính dữ liệu thường đáng tin cậy hơn việc giả định thứ tự đến.

## 7. toMap bốn tham số: lựa chọn loại Map

Ngoài `keyMapper`, `valueMapper`, `mergeFunction`, có thể truyền thêm `mapFactory`:

```java
Collectors.toMap(
        keyMapper,
        valueMapper,
        mergeFunction,
        mapFactory
)
```

Supplier này quyết định **loại Map được tạo để tích lũy**. Ví dụ cần Map có thứ tự thêm khóa để in báo cáo theo thứ tự gặp đầu tiên trong một pipeline tuần tự:

```java
import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.stream.Collectors;

Map<String, Integer> quantities = Arrays.asList(
        "P02:2", "P01:3", "P02:5", "P03:1"
).stream().collect(
        Collectors.toMap(
                row -> row.substring(0, row.indexOf(':')),
                row -> Integer.parseInt(
                        row.substring(row.indexOf(':') + 1)
                ),
                Integer::sum,
                LinkedHashMap::new
        )
);

System.out.println(quantities); // {P02=7, P01=3, P03=1}
```

`LinkedHashMap` mặc định duy trì thứ tự chèn khóa. Ở nguồn tuần tự có thứ tự, khóa `P02` xuất hiện đầu, sau đó `P01` và `P03`; cập nhật `P02` không làm khóa này chuyển xuống cuối trong chế độ insertion-order mặc định.

Một số lựa chọn khác:

| Factory | Đặc tính cần quan tâm | Khi dùng |
| --- | --- | --- |
| `HashMap::new` | Không cam kết thứ tự duyệt | Chỉ cần ánh xạ khóa–giá trị |
| `LinkedHashMap::new` | Thứ tự chèn khóa | Cần trình bày theo thứ tự gặp ở pipeline tuần tự |
| `TreeMap::new` | Sắp xếp theo natural order của khóa | Cần duyệt khóa theo thứ tự |
| `() -> new TreeMap<>(comparator)` | Comparator quyết định cả thứ tự và tính tương đương của khóa | Cần chuẩn hóa/so sánh khóa theo quy tắc riêng |

Với `TreeMap`, **hai khóa có comparator trả 0 sẽ được coi là một khóa** ngay cả khi `equals` của chúng không giống nhau. Chính sách merge phải tính đến đặc điểm này, chẳng hạn khi dùng `String.CASE_INSENSITIVE_ORDER`.

Đừng suy luận mặc định rằng `Collectors.toMap(...)` trả `HashMap` hoặc có thứ tự lặp lại cố định: API không cam kết kiểu Map, mutability, serializability hay thread-safety của kết quả khi không chỉ rõ factory.

## 8. Song song: mergeFunction cần kết hợp được

Với `parallelStream()`, các phần tử có thể được chia thành nhiều nhóm. Mỗi nhóm tạo một Map trung gian, sau đó framework kết hợp các Map. Vì vậy mergeFunction có thể nhận:

- Hai giá trị đến từ hai phần tử khác nhau trong cùng một nhánh;
- Hoặc **hai giá trị đã được tổng hợp** từ hai Map trung gian.

Để kết quả ổn định về ngữ nghĩa khi thay đổi cách nhóm, phép merge nên có **tính kết hợp**:

```text
merge(merge(a, b), c) = merge(a, merge(b, c))
```

Các quy tắc như `Long::sum`, `BigDecimal::add`, hoặc chọn tối đa theo comparator ổn định là những ví dụ phù hợp. Đối với `double`, cộng số thực có sai số làm tròn nên kết quả giữa các cách nhóm có thể khác chút ít; hãy cân nhắc yêu cầu chính xác.

`(first, second) -> first` và `(first, second) -> second` là các phép chọn có tính kết hợp về mặt toán học, nhưng **không giao hoán**. Chúng chọn theo vị trí tương đối trong phép gộp, nên không thích hợp nếu nghiệp vụ muốn “đầu tiên theo thời gian” mà Stream đã mất encounter order.

```java
Map<String, Long> parallelCounts = Arrays.asList(
        "A", "B", "A", "A", "B"
).parallelStream().collect(
        Collectors.toMap(
                Function.identity(),
                key -> 1L,
                Long::sum
        )
);

System.out.println(parallelCounts.get("A")); // 3
System.out.println(parallelCounts.get("B")); // 2
```

Đoạn này không phụ thuộc thứ tự vì tổng số lần xuất hiện là một phép gộp phù hợp. Tuy nhiên, **parallel không tự động nhanh hơn**: kết hợp Map có chi phí tạo bộ chứa, duyệt các khóa để gộp, hash và phân bổ công việc. Khi nguồn nhỏ hoặc quá nhiều khóa khác nhau, chi phí phối hợp có thể lớn hơn lợi ích.

Một lưu ý nữa: `toMap` thông thường **không phải concurrent collector**. Điều đó không có nghĩa không chạy được trên parallel stream. Java vẫn có thể tích lũy thành nhiều Map riêng rồi gộp qua combiner; không nên tự sửa một `HashMap` dùng chung từ `forEach` để thay cho việc này.

## 9. toConcurrentMap khác gì?

Khi nghiệp vụ không cần giữ encounter order và việc gom khóa có thể hưởng lợi từ cập nhật đồng thời, `Collectors.toConcurrentMap` có các overload tương tự:

```java
Collectors.toConcurrentMap(keyMapper, valueMapper, mergeFunction)
```

Ví dụ:

```java
import java.util.Arrays;
import java.util.concurrent.ConcurrentMap;
import java.util.function.Function;
import java.util.stream.Collectors;

ConcurrentMap<String, Long> counts = Arrays.asList(
        "warn", "info", "warn", "error"
).parallelStream().collect(
        Collectors.toConcurrentMap(
                Function.identity(),
                code -> 1L,
                Long::sum
        )
);

System.out.println(counts.get("warn")); // 2
```

`toConcurrentMap` là một **concurrent, unordered collector**: nó cho phép tích lũy theo chiến lược đồng thời, không cam kết thứ tự gặp phần tử cho kết quả. Điều này phù hợp với cộng đếm, nhưng không phù hợp với việc giữ “bản ghi đến trước” bằng `(a,b) -> a` nếu thứ tự ấy mang ý nghĩa nghiệp vụ.

Đối với yêu cầu phức tạp hơn, có overload nhận thêm `mapFactory` cho một `ConcurrentMap` phù hợp, nhưng vẫn cần tuân thủ hợp đồng mergeFunction và không giả định kết quả luôn nhanh hơn `toMap`. `ConcurrentMap` bảo vệ những thao tác được quy định là đồng thời của Map; điều đó không tự động làm cho mọi object mutable lưu bên trong Map an toàn khi sửa ở nhiều luồng.

## 10. Giá trị null và merge trả null: hai tình huống khác nhau

`null` thường gây lỗi khó phát hiện khi gom Map. Cần phân biệt:

1. **`valueMapper` trả `null`:** nhiều cách thu thập chuẩn, bao gồm `toMap`, không chấp nhận giá trị `null` và có thể ném `NullPointerException`. Không nên dựa vào một implementation cụ thể để cho phép giá trị này.
2. **`mergeFunction` trả `null`:** với cách xử lý theo `Map.merge`, `null` biểu thị **loại bỏ ánh xạ cho khóa đang trùng**, không phải “giữ giá trị null trong Map”. Đây là một chính sách xóa, không phải chính sách chọn giá trị.
3. **`keyMapper` trả `null`:** khả năng chấp nhận phụ thuộc kiểu Map và Collector; đặc biệt `ConcurrentHashMap` không chấp nhận khóa null. Để dễ di chuyển giữa các implementation, nên chuẩn hóa hoặc loại bản ghi không có khóa trước khi thu thập.

Ví dụ minh họa trường hợp hàm merge trả null:

```java
import java.util.Arrays;
import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collectors;

Map<String, String> cancelled = Arrays.asList(
        "A", "B", "A"
).stream().collect(
        Collectors.toMap(
                Function.identity(),
                Function.identity(),
                (previous, incoming) -> null
        )
);

System.out.println(cancelled.containsKey("A")); // false
System.out.println(cancelled.get("B"));          // B
```

Khi hai bản ghi `"A"` đụng khóa, hàm merge trả null nên ánh xạ `A` bị xóa trong Map tích lũy. Nếu có thêm một `"A"` xuất hiện sau nữa, khóa có thể được **thêm lại**; vì vậy hành vi này **không phải** là cách đáng tin cậy để “loại tất cả khóa có hơn một lần xuất hiện”, đặc biệt khi chia nhánh song song.

**Khuyến nghị:** tránh dùng `null` trong mergeFunction như một mẹo làm sạch dữ liệu. Nếu cần phát hiện khóa trùng hoặc loại toàn bộ khóa có số lần xuất hiện lớn hơn 1, hãy đếm số lần xuất hiện trước và lọc theo số đếm, hoặc dùng collector có trạng thái trung gian biểu diễn đủ thông tin.

Ví dụ loại khóa xuất hiện hơn một lần một cách rõ nghĩa:

```java
Map<String, Long> frequencies = Arrays.asList(
        "A", "B", "A", "C"
).stream().collect(
        Collectors.groupingBy(
                Function.identity(),
                Collectors.counting()
        )
);

Map<String, Long> onlyUnique = frequencies.entrySet().stream()
        .filter(entry -> entry.getValue() == 1L)
        .collect(Collectors.toMap(
                Map.Entry::getKey,
                Map.Entry::getValue
        ));

System.out.println(onlyUnique.containsKey("A")); // false
System.out.println(onlyUnique.get("B"));          // 1
```

## 11. Khi nào nên dùng groupingBy thay vì toMap?

Nếu **mỗi khóa cần giữ nhiều phần tử**, `groupingBy` thường diễn đạt tự nhiên hơn `toMap` với một mergeFunction phải tự quản lý danh sách mutable.

| Yêu cầu | API phù hợp | Lý do |
| --- | --- | --- |
| Mỗi khóa có một giá trị; khóa phải duy nhất | `toMap(keyMapper, valueMapper)` | Trùng khóa làm lỗi |
| Mỗi khóa giữ giá trị đầu hoặc cuối theo quy tắc rõ | `toMap(..., (a,b) -> a/b)` | Xử lý xung đột tường minh |
| Mỗi khóa cộng tổng số lượng/tiền | `toMap(..., Long::sum)` hoặc `groupingBy(..., summingLong(...))` | Không cần giữ danh sách |
| Mỗi khóa giữ toàn bộ bản ghi | `groupingBy(classifier)` | Kết quả `Map<K,List<T>>` |
| Mỗi khóa cần count, average, min/max | `groupingBy(..., downstreamCollector)` | Có các collector thống kê có sẵn |
| Cần concurrent và không cần order | `toConcurrentMap` / `groupingByConcurrent` | Hỗ trợ tích lũy concurrent theo hợp đồng |

Ví dụ nhóm tất cả đơn hàng theo mã khách hàng:

```java
Map<String, List<Payment>> byCustomer = payments.stream()
        .collect(Collectors.groupingBy(Payment::customerId));

System.out.println(byCustomer.get("C01").size()); // 2
```

Dùng `toMap` chỉ để tạo một `List` mới cho mỗi phần tử rồi nối các danh sách khiến code phức tạp và dễ nhầm trạng thái mutable, nhất là khi parallel. `groupingBy` thực hiện đúng nhiệm vụ này trực tiếp.

Nếu chỉ cần **tổng tiền** theo khách hàng, `groupingBy` cũng có thể dùng downstream `Collectors.reducing`:

```java
Map<String, BigDecimal> totals = payments.stream()
        .collect(Collectors.groupingBy(
                Payment::customerId,
                Collectors.reducing(
                        BigDecimal.ZERO,
                        Payment::amount,
                        BigDecimal::add
                )
        ));

System.out.println(totals.get("C01")); // 19.75
```

So với `toMap(Payment::customerId, Payment::amount, BigDecimal::add)`, cách này có vẻ dài hơn cho một phép cộng đơn giản, nhưng cấu trúc downstream phát huy tác dụng khi cần thống kê hoặc tổ hợp collector phức tạp.

## 12. Quy tắc lựa chọn mergeFunction đáng tin cậy

Trước khi viết hàm gộp, hãy xác định:

1. **Khóa được chuẩn hóa như thế nào?** Có bỏ khoảng trắng, đổi chữ thường hay dùng composite key không? Chuẩn hóa không đúng có thể gom nhầm các bản ghi khác nhau.
2. **Trùng khóa là lỗi hay điều được phép?** Nếu là lỗi, dùng overload hai tham số hoặc ném ngoại lệ tường minh.
3. **Kết quả cho một khóa cần biểu diễn gì?** Một bản ghi ưu tiên, tổng số, hay danh sách? Câu trả lời quyết định `toMap` hay `groupingBy`.
4. **Phép merge có tính kết hợp và không có tác dụng phụ không?** Đặc biệt quan trọng nếu pipeline chạy parallel.
5. **Quy tắc có phụ thuộc thứ tự đầu vào không?** Nếu có, xác định encounter order và cân nhắc việc chọn theo thuộc tính như timestamp.
6. **Có thể xuất hiện `null` không?** Xác định chính sách xử lý trước `collect`; đừng dùng null ngầm làm giá trị mặc định.
7. **Có cần thứ tự duyệt Map không?** Nếu có, chọn factory và nguồn phù hợp; không suy ra thứ tự từ `Map` mặc định.
8. **Kích thước dữ liệu và tỷ lệ khóa trùng là bao nhiêu?** Map có thể giữ nhiều khóa trong bộ nhớ; parallel/concurrent có chi phí khác nhau.

### Bảng lỗi thường gặp

| Mẫu sai hoặc giả định | Rủi ro | Hướng sửa |
| --- | --- | --- |
| `toMap(key, value)` trên dữ liệu có khóa trùng | `IllegalStateException` | Thêm mergeFunction phù hợp |
| `(a,b) -> b` nhưng cần giá trị mới nhất theo thời gian | “Sau” trong gộp chưa chắc là timestamp mới nhất | So sánh `updatedAt` trực tiếp |
| `(a,b) -> a-b` khi chạy parallel | Không có tính kết hợp | Dùng phép gộp có hợp đồng hợp lệ |
| `valueMapper` trả null | Có thể ném `NullPointerException` | Lọc, chuẩn hóa hoặc biểu diễn giá trị vắng mặt |
| Merge trả null để xóa trùng lặp vĩnh viễn | Khóa có thể xuất hiện lại | Đếm tần suất rồi lọc theo số đếm |
| Suy luận kiểu hoặc thứ tự Map mặc định | JDK không cam kết | Truyền `mapFactory` khi thật sự cần |
| Tự sửa `HashMap` ngoài pipeline qua `parallelStream().forEach` | Tranh chấp trạng thái | Dùng `collect` với Collector phù hợp |
| `toConcurrentMap` để giữ “lần đầu tiên” | Collector unordered | Chọn chính sách dựa trên khóa ưu tiên |
| Gộp các `List` mutable bằng mergeFunction tùy ý | Dễ sai/khó quản lý trạng thái khi parallel | Dùng `groupingBy` |
| Cứ bật parallel là nhanh hơn | Tạo/gộp Map và phối hợp luồng có chi phí | Đo đạc trên dữ liệu thực |

## 13. Ví dụ tổng hợp: doanh thu theo mã hàng và xử lý bản ghi trùng

Giả sử các giao dịch bán hàng có mã sản phẩm và số lượng. Yêu cầu: cộng số lượng mỗi mã, nhưng bỏ những dòng có số lượng không dương. Ta có thể dùng Map thu thập trực tiếp:

```java
import java.util.Arrays;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

final class Sale {
    private final String productId;
    private final long quantity;

    Sale(String productId, long quantity) {
        this.productId = productId;
        this.quantity = quantity;
    }

    String productId() { return productId; }
    long quantity() { return quantity; }
}

List<Sale> sales = Arrays.asList(
        new Sale("P01", 3),
        new Sale("P02", 2),
        new Sale("P01", 4),
        new Sale("P03", -1),
        new Sale("P02", 5)
);

Map<String, Long> sold = sales.stream()
        .filter(sale -> sale.quantity() > 0)
        .collect(Collectors.toMap(
                Sale::productId,
                Sale::quantity,
                Long::sum
        ));

System.out.println(sold.get("P01"));             // 7
System.out.println(sold.get("P02"));             // 7
System.out.println(sold.containsKey("P03"));     // false
```

Ở đây:

- `filter` làm rõ chính sách **loại số lượng không dương** trước khi tổng hợp;
- `keyMapper` phân nhóm theo mã sản phẩm;
- `valueMapper` lấy số lượng của từng giao dịch;
- `Long::sum` gộp đúng cả giá trị đơn lẻ lẫn kết quả tổng một nhánh;
- `collect` là terminal operation, kích hoạt pipeline và trả Map.

Nếu doanh nghiệp cần **ghi nhận số giao dịch bị loại** để kiểm toán, chỉ sử dụng `filter` như trên có thể làm mất thông tin; hãy bổ sung đường xử lý lỗi hoặc một Collector báo cáo đầy đủ. Nếu `long` có thể tràn, cân nhắc `Math.addExact` để phát hiện tràn, hoặc dùng `BigInteger` theo yêu cầu số học.

## 14. Câu hỏi tự kiểm tra

1. Điều gì xảy ra khi `toMap(keyMapper, valueMapper)` gặp hai phần tử có khóa giống nhau? **`IllegalStateException`**, vì chưa chỉ định chiến lược giải quyết xung đột.
2. Tham số thứ ba của `toMap` nhận gì? **Hai giá trị U** có cùng khóa và trả về **một U** sau khi gộp.
3. `(existing, incoming) -> existing` nghĩa là gì khi duyệt tuần tự một `List` có thứ tự? **Giữ giá trị được lưu trước** cho khóa đó.
4. Vì sao không nên dùng `(a,b) -> b` để chọn sự kiện mới nhất nếu dữ liệu không có thứ tự thời gian? **Vì** vị trí khi gộp không phản ánh timestamp.
5. Để tính số lượng theo khóa khi chạy parallel, `Long::sum` phù hợp hơn phép trừ vì sao? **Vì** phép cộng có tính kết hợp trong miền số nguyên phù hợp.
6. `toMap` hai tham số có mặc định trả về `LinkedHashMap` không? **Không**, loại Map không được cam kết.
7. Làm sao tạo Map giữ thứ tự chèn khóa cho pipeline tuần tự? **Dùng overload bốn tham số với `LinkedHashMap::new`**.
8. Nếu mergeFunction trả `null` trong `Map.merge` thì điều gì xảy ra? **Ánh xạ khóa đang xung đột bị xóa**.
9. Nếu mỗi khóa cần giữ nhiều bản ghi, nên chọn `groupingBy` hay tự ghép `List` trong `toMap`? **Thường chọn `groupingBy`**.
10. `toConcurrentMap` có bảo đảm thứ tự đầu tiên trong nguồn không? **Không**, đây là concurrent, unordered collector.
11. Hai khóa được `TreeMap` coi là trùng theo tiêu chí gì? **Comparator trả 0** (hoặc natural ordering khi không có comparator).
12. Để chọn một bản ghi theo ưu tiên không phụ thuộc encounter order, nên làm gì? **Dùng comparator với khóa phụ ổn định và một mergeFunction chọn bản ghi ưu tiên**.

**Nguyên tắc áp dụng:** Khi thu thập thành Map, hãy quyết định **ý nghĩa của khóa trùng trước khi viết `collect`**. Dùng `toMap` không có mergeFunction để phát hiện xung đột bất hợp lệ; dùng mergeFunction thuần, kết hợp được để cộng dồn hoặc chọn giá trị theo quy tắc rõ; dùng `groupingBy` nếu cần giữ nhiều phần tử trong một nhóm. Đừng nhầm thứ tự gộp với thời gian nghiệp vụ, và chỉ dùng concurrent hoặc parallel sau khi đã xác minh tính đúng đắn và hiệu năng.
