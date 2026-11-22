# Kiểm tra tính kết hợp và ảnh hưởng của thứ tự trong hàm merge

Khi thu thập một Stream thành `Map<K, V>` bằng `Collectors.toMap`, hai phần tử đầu vào có thể tạo ra **cùng khóa**. Lúc đó, hàm `merge` quyết định sẽ giữ, thay thế hay kết hợp hai giá trị. Một hàm merge cho kết quả có vẻ đúng khi chạy tuần tự vẫn có thể cho kết quả khác nếu Stream được chia thành nhiều phần rồi gộp song song. Để thiết kế đúng, cần phân biệt **tính kết hợp nhóm** (*associativity*), **tính giao hoán** (*commutativity*) và **thứ tự gặp phần tử** (*encounter order*).

Bài thuộc chương **Thu thập thành Map** của module **JAVA_STREAM_API**. Nội dung nối tiếp cách lập trình khai báo với pipeline lazy, `filter`, `map`, `reduce`, `collect` và các collector như `groupingBy`. Việc hiểu hàm merge cũng giúp viết collector tùy chỉnh, đánh giá xử lý song song dựa vào `Spliterator` và nhận diện giới hạn về trạng thái, hiệu năng, tài nguyên và độ chính xác.

## 1. Khi nào toMap gọi hàm merge?

Trong Java 8+, overload phổ biến của `Collectors.toMap` có dạng:

```java
static <T, K, U> Collector<T, ?, Map<K, U>> toMap(
        Function<? super T, ? extends K> keyMapper,
        Function<? super T, ? extends U> valueMapper,
        BinaryOperator<U> mergeFunction)
```

Các tham số có ý nghĩa:

| Tham số | Công việc | Ví dụ |
|---|---|---|
| `keyMapper` | Lấy khóa từ từng phần tử đầu vào | `Order::getCustomerId` |
| `valueMapper` | Lấy giá trị để đưa vào Map | `Order::getAmount` |
| `mergeFunction` | Kết hợp **giá trị cũ** và **giá trị mới** nếu hai phần tử có khóa trùng | `BigDecimal::add` |

`mergeFunction` có kiểu `BinaryOperator<U>`: nhận hai giá trị kiểu `U`, trả lại một giá trị kiểu `U`. Với trường hợp thông thường, hãy hiểu nó theo công thức:

```text
Map đang có:  K -> oldValue
Phần tử mới:  K -> newValue
                     |
                     v
K -> mergeFunction(oldValue, newValue)
```

Nếu khóa chưa có, giá trị được đưa vào Map mà không cần gộp với một giá trị cũ. Nếu hai phần tử có khóa khác nhau, mergeFunction cũng không cần được gọi cho cặp đó.

### 1.1. Không cung cấp mergeFunction khi có khóa trùng

Overload `toMap(keyMapper, valueMapper)` mặc định **ném `IllegalStateException` khi có khóa trùng**.

```java
import java.util.Arrays;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

List<String> words = Arrays.asList("an", "anh", "bình");

// Sai nếu yêu cầu cho phép nhiều từ có cùng chữ cái đầu.
// Hai từ "an" và "anh" đều tạo khóa "a".
Map<String, String> byFirstLetter = words.stream()
        .collect(Collectors.toMap(
                word -> word.substring(0, 1),
                word -> word));
// IllegalStateException khi gặp khóa "a" trùng.
```

Nếu dữ liệu thực sự yêu cầu mỗi khóa là duy nhất, lỗi này hữu ích vì phát hiện dữ liệu vi phạm quy tắc. Nếu **trùng khóa là hợp lệ**, cần xác định rõ chính sách merge:

```java
Map<String, String> firstWordByLetter = words.stream()
        .collect(Collectors.toMap(
                word -> word.substring(0, 1),
                word -> word,
                (oldValue, newValue) -> oldValue));

System.out.println(firstWordByLetter.get("a")); // an
```

Trong ví dụ tuần tự này, khi gặp "anh" sau "an", merge giữ giá trị cũ "an". Đây là một chính sách hợp lệ, nhưng có **phụ thuộc thứ tự đầu vào**.

## 2. Tính kết hợp nhóm là yêu cầu cốt lõi của phép gộp

Một phép gộp `f(a, b)` có tính **kết hợp nhóm** khi:

\[
f(f(a,b),c)=f(a,f(b,c))
\]

Nói đơn giản: **cùng một dãy giá trị, thay đổi cách đặt ngoặc khi gộp không làm đổi kết quả**. Đây là yêu cầu thiết yếu để việc kết hợp các kết quả từng phần của collector mang cùng ý nghĩa với xử lý tuần tự. Với Stream song song, thư viện có quyền gom phần tử theo nhiều nhánh, rồi gọi combiner để nhập các Map từng nhánh.

Giả sử ba đơn có cùng mã sản phẩm `P01` và số lượng `2, 3, 4`. Hàm merge là phép cộng:

```java
import java.util.Arrays;
import java.util.Map;
import java.util.stream.Collectors;

Map<String, Integer> quantityBySku =
        Arrays.asList(2, 3, 4).stream()
                .collect(Collectors.toMap(
                        quantity -> "P01",
                        quantity -> quantity,
                        Integer::sum));

System.out.println(quantityBySku.get("P01")); // 9
```

Với phép cộng, kết quả `(2 + 3) + 4` và `2 + (3 + 4)` đều bằng `9`. Vì vậy, việc phân nhóm không thay đổi ý nghĩa của tổng (với lưu ý riêng về miền số, tràn số và phép toán dấu phẩy động).

### 2.1. Phép merge không kết hợp nhóm: trung bình từng cặp

Đây là lỗi phổ biến khi muốn “lấy giá trị trung bình theo khóa”:

```java
// SAI khi dùng làm trung bình chung cho nhiều phần tử trùng khóa.
Map<String, Double> wrongAverage =
        Arrays.asList(10, 20, 40).stream()
                .collect(Collectors.toMap(
                        value -> "P01",
                        value -> value.doubleValue(),
                        (a, b) -> (a + b) / 2.0));

System.out.println(wrongAverage.get("P01")); // 27.5 ở thứ tự này.
```

Xét hai cách đặt ngoặc:

```text
f(f(10, 20), 40) = f(15, 40) = 27.5
f(10, f(20, 40)) = f(10, 30) = 20.0
Trung bình đúng: (10 + 20 + 40) / 3 = 23.333...
```

Không những không kết hợp nhóm, cách này còn **không tính đúng trung bình tổng thể**, kể cả nếu chạy tuần tự. Nếu chia Stream thành các phần khác nhau, kết quả merge còn có thể thay đổi.

**Cách đúng** là giữ **tổng và số lượng phần tử** trong trạng thái tích lũy, rồi chia một lần sau khi gộp. Có thể dùng `groupingBy(..., averagingInt(...))` hoặc collector lưu cặp `(sum, count)`; không thể tính trung bình có trọng số chính xác chỉ bằng cách gộp các giá trị trung bình của nhóm mà không giữ kích thước nhóm.

```java
import java.util.Map;
import java.util.stream.Collectors;

Map<String, Double> correctAverage =
        Arrays.asList(10, 20, 40).parallelStream()
                .collect(Collectors.groupingBy(
                        value -> "P01",
                        Collectors.averagingInt(Integer::intValue)));

System.out.println(correctAverage.get("P01"));
// 23.333333333333332 (biểu diễn double gần đúng).
```

### 2.2. Phép trừ cũng không kết hợp nhóm

```java
java.util.function.BinaryOperator<Integer> subtraction =
        (a, b) -> a - b;

System.out.println(subtraction.apply(
        subtraction.apply(20, 5), 3)); // 12
System.out.println(subtraction.apply(
        20, subtraction.apply(5, 3))); // 18
```

Tránh dùng phép trừ hoặc chia làm mergeFunction cho một phép tổng hợp mà cần kết quả độc lập với cách phân hoạch. Nếu nghiệp vụ thực sự yêu cầu cập nhật tuần tự theo từng sự kiện, cần mô tả rõ thứ tự và trạng thái, thay vì ngầm dùng một phép gộp không kết hợp nhóm.

## 3. Kết hợp nhóm khác giao hoán: có thể đúng nhưng phụ thuộc thứ tự

Phép gộp có tính **giao hoán** khi `f(a,b) = f(b,a)`. Tính giao hoán và tính kết hợp nhóm là **hai thuộc tính khác nhau**.

| Hàm merge | Kết hợp nhóm? | Giao hoán? | Hệ quả |
|---|---|---|---|
| `Integer::sum` | Có theo phép cộng `int` của Java | Có | Kết quả không phụ thuộc hoán vị, nhưng có thể tràn `int` |
| `BigDecimal::add` | Có với giá trị thập phân chính xác thông thường | Có về giá trị số | Hợp lý cho cộng tiền nếu không dùng giá trị null |
| `(oldValue, newValue) -> oldValue` | Có | Không | Giữ phần tử gặp đầu tiên theo một thứ tự xác định |
| `(oldValue, newValue) -> newValue` | Có | Không | Giữ phần tử gặp cuối cùng theo một thứ tự xác định |
| `(a, b) -> a + "|" + b` | Có | Không | Ghép chuỗi có thứ tự; đảo phần tử sẽ đảo thứ tự chuỗi |
| `(a, b) -> (a + b) / 2.0` | Không | Có về mặt biểu thức, trừ các giá trị đặc biệt | Kết quả thay đổi theo cách phân nhóm |
| `(a, b) -> a - b` | Không | Không | Dễ lệch kết quả ở pipeline song song |

Ví dụ kiểm tra hai phép merge chọn giá trị:

```java
import java.util.function.BinaryOperator;

BinaryOperator<String> keepFirst = (oldValue, newValue) -> oldValue;
BinaryOperator<String> keepLast  = (oldValue, newValue) -> newValue;

System.out.println(keepFirst.apply(
        keepFirst.apply("A", "B"), "C")); // A
System.out.println(keepFirst.apply(
        "A", keepFirst.apply("B", "C"))); // A

System.out.println(keepLast.apply(
        keepLast.apply("A", "B"), "C"));  // C
System.out.println(keepLast.apply(
        "A", keepLast.apply("B", "C")));  // C

System.out.println(keepFirst.apply("A", "B")); // A
System.out.println(keepFirst.apply("B", "A")); // B
```

**Kết luận về first/last wins:** cả hai toán tử có tính kết hợp nhóm. Chúng **không cần giao hoán** để hợp lệ với việc gộp những phân đoạn theo encounter order. Nhưng nếu không còn một encounter order được xác định, chúng **không thể cam kết** giá trị nghiệp vụ nào là “đầu” hoặc “cuối”.

## 4. Encounter order ảnh hưởng đến kết quả merge thế nào?

**Encounter order** là thứ tự các phần tử do nguồn và pipeline quy định. `List.stream()` có encounter order theo vị trí trong danh sách. `HashSet.stream()` không có thứ tự gặp phần tử được bảo đảm. `unordered()` có thể loại bỏ ràng buộc thứ tự; điều này có thể tạo thêm tự do xử lý cho thư viện.

Giả sử có các bản ghi cập nhật cùng mã `P01` theo thứ tự:

```text
Sự kiện 1: P01 -> "nháp"
Sự kiện 2: P01 -> "đã duyệt"
Sự kiện 3: P01 -> "đã giao"
```

Khi thu thập **tuần tự trên List theo đúng thứ tự trên**:

```java
import java.util.Arrays;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

List<String> statuses = Arrays.asList(
        "nháp", "đã duyệt", "đã giao");

Map<String, String> first = statuses.stream()
        .collect(Collectors.toMap(
                status -> "P01",
                status -> status,
                (oldValue, newValue) -> oldValue));

Map<String, String> last = statuses.stream()
        .collect(Collectors.toMap(
                status -> "P01",
                status -> status,
                (oldValue, newValue) -> newValue));

System.out.println(first.get("P01")); // nháp
System.out.println(last.get("P01"));  // đã giao
```

Kết quả thay đổi nếu **đảo thứ tự đầu vào**. Điều đó không có nghĩa mergeFunction sai về tính kết hợp; nó có nghĩa **ngữ nghĩa của phép chọn phụ thuộc vào thứ tự**, tương tự “chọn bản ghi đầu tiên/ cuối cùng”.

Với một Stream **có thứ tự** và collector phù hợp, việc gộp các phân đoạn vẫn phải tôn trọng ngữ nghĩa thứ tự của collector; nhưng không nên xem thứ tự các **lời gọi** mergeFunction là giao diện lập trình ổn định để ghi log hay cập nhật biến ngoài. Khi chuyển sang một nguồn không có thứ tự, dùng `unordered()` hoặc dùng collector concurrent/unordered, không dựa vào keepFirst/keepLast để xác định “bản ghi mới nhất” theo nghiệp vụ.

### 4.1. Thứ tự các entry trong Map là vấn đề riêng

`Collectors.toMap(...)` mặc định **không cam kết** loại Map cụ thể hay thứ tự duyệt `entrySet()`. Việc một giá trị được chọn theo quy tắc merge không đồng nghĩa các khóa Map sẽ được in theo thứ tự xuất hiện.

Nếu cần một chính sách về **thứ tự khóa trong kết quả**, dùng overload bốn tham số:

```java
Map<String, String> byInsertionOrder = statuses.stream()
        .collect(Collectors.toMap(
                status -> status.substring(0, 1),
                status -> status,
                (oldValue, newValue) -> oldValue,
                java.util.LinkedHashMap::new));
```

Trong ví dụ **tuần tự**, `LinkedHashMap` giữ thứ tự chèn các khóa khác nhau. `TreeMap::new` phù hợp khi muốn sắp xếp khóa theo thứ tự tự nhiên hoặc comparator được cấu hình. **Map supplier chỉ quyết định cách lưu/duyệt khóa**; nó không tự làm mergeFunction trở nên kết hợp nhóm hay xác định “mới nhất” của những bản ghi có cùng khóa.

## 5. Khi cần một kết quả bất biến theo thứ tự: chọn bằng quy tắc so sánh

Trong dữ liệu giao dịch, “bản ghi mới nhất” thường nên được định nghĩa bằng **thời gian hoặc số phiên bản**, chứ không phải vị trí vô tình trong một Stream. Với hai sự kiện có cùng khóa, có thể chọn sự kiện có phiên bản lớn hơn; nếu bằng phiên bản, dùng khóa phụ duy nhất để phá hòa.

```java
import java.util.Comparator;
import java.util.function.BinaryOperator;

Comparator<Event> byVersionThenId =
        Comparator.comparingLong(Event::getVersion)
                .thenComparing(Event::getEventId);

BinaryOperator<Event> chooseLatest =
        BinaryOperator.maxBy(byVersionThenId);
```

Đoạn này giả định tồn tại kiểu `Event` với `getVersion()` và `getEventId()` không null, cùng comparator tạo thứ tự nhất quán. `maxBy` gộp hai sự kiện bằng cách chọn sự kiện lớn hơn theo comparator; nếu khóa phụ giúp xác định **duy nhất** cực đại, việc hoán vị nguồn cũng không đổi sự kiện được chọn.

Nếu chỉ so phiên bản mà nhiều bản ghi có cùng phiên bản, kết quả có thể còn phụ thuộc việc phá hòa. Khi đó, việc bổ sung `eventId` (hoặc quy tắc nghiệp vụ khác) giúp xác định rõ một bản ghi thắng cuộc. Việc chọn “phiên bản lớn nhất” không tương đương “bản ghi xuất hiện cuối cùng”.

## 6. Ví dụ Java 8 hoàn chỉnh: cộng tổng và chọn bản ghi theo khóa

Ví dụ sau mô tả các dòng bán hàng. Một mã hàng có thể xuất hiện nhiều lần với số tiền, mức ưu tiên và thời điểm cập nhật khác nhau. Chúng ta tính **tổng tiền theo mã** và chọn **bản ghi có mức ưu tiên cao nhất, sau đó có thời điểm mới nhất**, đều bằng mergeFunction phù hợp.

```java
import java.math.BigDecimal;
import java.util.Arrays;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.function.BinaryOperator;
import java.util.function.Function;
import java.util.stream.Collectors;

public class MapMergeContractsDemo {
    static final class Sale {
        private final String sku;
        private final String ticket;
        private final BigDecimal amount;
        private final int priority;
        private final long receivedAt;

        Sale(String sku, String ticket, String amount,
                int priority, long receivedAt) {
            this.sku = sku;
            this.ticket = ticket;
            this.amount = new BigDecimal(amount);
            this.priority = priority;
            this.receivedAt = receivedAt;
        }

        String getSku() {
            return sku;
        }

        String getTicket() {
            return ticket;
        }

        BigDecimal getAmount() {
            return amount;
        }

        int getPriority() {
            return priority;
        }

        long getReceivedAt() {
            return receivedAt;
        }
    }

    public static void main(String[] args) {
        List<Sale> sales = Arrays.asList(
                new Sale("P01", "A-old",  "12.50", 1, 100),
                new Sale("P02", "B-only", "7.25",  3, 150),
                new Sale("P01", "A-new",  "2.75",  4, 130),
                new Sale("P01", "A-mid",  "10.00", 4, 120)
        );

        // BigDecimal.add: cộng tiền chính xác theo giá trị thập phân.
        Map<String, BigDecimal> totalBySku = sales.parallelStream()
                .collect(Collectors.toMap(
                        Sale::getSku,
                        Sale::getAmount,
                        BigDecimal::add));

        System.out.println(totalBySku.get("P01")); // 25.25
        System.out.println(totalBySku.get("P02")); // 7.25

        // Phá hòa bằng thời gian, rồi ticket để có cực đại xác định.
        Comparator<Sale> byPriorityTimeTicket =
                Comparator.comparingInt(Sale::getPriority)
                        .thenComparingLong(Sale::getReceivedAt)
                        .thenComparing(Sale::getTicket);

        Map<String, Sale> chosenBySku = sales.parallelStream()
                .collect(Collectors.toMap(
                        Sale::getSku,
                        Function.identity(),
                        BinaryOperator.maxBy(byPriorityTimeTicket)));

        System.out.println(chosenBySku.get("P01").getTicket());
        // A-new (cùng priority=4 nhưng receivedAt=130 lớn hơn 120)

        // Chính sách theo thứ tự đầu vào được thể hiện rõ khi chạy tuần tự.
        Map<String, String> firstBySku = sales.stream()
                .collect(Collectors.toMap(
                        Sale::getSku,
                        Sale::getTicket,
                        (oldValue, newValue) -> oldValue,
                        LinkedHashMap::new));

        Map<String, String> lastBySku = sales.stream()
                .collect(Collectors.toMap(
                        Sale::getSku,
                        Sale::getTicket,
                        (oldValue, newValue) -> newValue,
                        LinkedHashMap::new));

        System.out.println(firstBySku.get("P01")); // A-old
        System.out.println(lastBySku.get("P01"));  // A-mid
        System.out.println(firstBySku.keySet());   // [P01, P02]
    }
}
```

**Đọc kết quả:**

- Tổng cho `P01` là `12.50 + 2.75 + 10.00 = 25.25`; phép cộng thập phân không phụ thuộc thứ tự ghi nhận của các bản ghi trong ví dụ.
- Bản ghi thắng theo **priority và receivedAt** là `A-new`; kết quả này khác `A-mid`, vốn là bản ghi cuối trong danh sách.
- `keepFirst` và `keepLast` cho hai cách lựa chọn hợp lệ về thứ tự, nhưng không thể thay thế tiêu chí “mới nhất theo thời điểm” nếu danh sách có thể bị đảo hoặc ghép từ các nguồn khác nhau.
- `LinkedHashMap` khiến thứ tự khóa của hai Map ở ví dụ tuần tự là `[P01, P02]`. Điều đó là chính sách **thứ tự duyệt Map**, khác với chính sách **merge giá trị cho cùng khóa**.

Để tính tổng tiền, nên chọn `BigDecimal` hoặc đơn vị tiền nhỏ nhất với miền giá trị an toàn. Phép cộng `int`/`long` có thể tràn; phép cộng `double` có sai số làm tròn và có thể cho kết quả bit khác nhau theo thứ tự gộp dù trên toán học thực phép cộng có tính kết hợp nhóm.

## 7. Tự kiểm tra associativity và thứ tự bằng các biểu thức nhỏ

Trước khi đưa mergeFunction vào pipeline, nên kiểm tra ít nhất các giá trị `a`, `b`, `c` và so sánh **hai cách nhóm phép gộp**.

### 7.1. Một hàm đúng về kết hợp nhóm nhưng vẫn nhạy thứ tự

```java
import java.util.function.BinaryOperator;

BinaryOperator<String> concatenate =
        (left, right) -> left + "|" + right;

String groupLeft = concatenate.apply(
        concatenate.apply("A", "B"), "C");
String groupRight = concatenate.apply(
        "A", concatenate.apply("B", "C"));
String reversed = concatenate.apply("B", "A");

System.out.println(groupLeft);  // A|B|C
System.out.println(groupRight); // A|B|C
System.out.println(reversed);   // B|A
```

Hàm nối chuỗi có **tính kết hợp nhóm**, nên chia đoạn `["A", "B", "C"]` thành các nhánh rồi gộp theo cùng thứ tự vẫn cho cùng kết quả. Nhưng nó không giao hoán: đảo thứ tự phần tử sẽ đổi chuỗi. Nếu thực sự muốn một tập hợp giá trị không phụ thuộc thứ tự, có thể thu thập vào `Set` hoặc sắp xếp các giá trị trước khi nối, tùy yêu cầu nghiệp vụ.

### 7.2. Một hàm sai về kết hợp nhóm

```java
BinaryOperator<Double> pairAverage = (a, b) -> (a + b) / 2.0;

double leftGrouped =
        pairAverage.apply(pairAverage.apply(10.0, 20.0), 40.0);
double rightGrouped =
        pairAverage.apply(10.0, pairAverage.apply(20.0, 40.0));

System.out.println(leftGrouped);  // 27.5
System.out.println(rightGrouped); // 20.0
```

Nếu hai cách nhóm cho kết quả khác nhau trên dữ liệu đầu vào có ý nghĩa, mergeFunction không đáp ứng yêu cầu của phép tổng hợp có thể chia nhánh.

### 7.3. Thử trên dữ liệu trùng khóa

Một bộ tình huống nhỏ nên bao gồm:

1. **Nguồn rỗng**: `collect(toMap(...))` trả Map rỗng; mergeFunction không có dữ liệu để gọi.
2. **Một giá trị cho mỗi khóa**: không có va chạm khóa, chỉ kiểm tra keyMapper/valueMapper.
3. **Hai hoặc ba giá trị trùng khóa**: kiểm tra rõ quy tắc old/new và tính kết hợp nhóm.
4. **Khóa đan xen** (ví dụ `P01, P02, P01, P02`): kiểm tra mỗi khóa được tổng hợp độc lập.
5. **Đảo thứ tự đầu vào**: xác nhận trường hợp nào được phép đổi kết quả và trường hợp nào phải giữ nguyên.
6. **Tuần tự và song song**: so kết quả theo giá trị của Map, không chỉ nhìn thứ tự in `entrySet`; nếu có sai khác, kiểm tra phép gộp và dữ liệu trước khi quy kết cho môi trường.

Thử nghiệm trên vài mẫu chỉ giúp phát hiện lỗi, **không chứng minh** một phép toán có tính kết hợp nhóm với mọi dữ liệu. Khi có thể, lập luận bằng các tính chất toán học và quy tắc nghiệp vụ.

## 8. toConcurrentMap và xử lý song song: khi nào thứ tự không còn phù hợp?

`Collectors.toConcurrentMap` tạo một collector concurrent, unordered. Khi các phần tử có cùng khóa được tích lũy đồng thời, thứ tự chúng được gộp có thể phụ thuộc lịch thực thi. **Không nên dùng phép chọn “giữ cũ” hoặc “giữ mới” để ngầm xác định bản ghi theo thời gian** trong collector kiểu này.

```java
import java.math.BigDecimal;
import java.util.concurrent.ConcurrentMap;
import java.util.stream.Collectors;

ConcurrentMap<String, BigDecimal> totals = sales.parallelStream()
        .collect(Collectors.toConcurrentMap(
                Sale::getSku,
                Sale::getAmount,
                BigDecimal::add));
```

Đoạn minh họa trên dùng danh sách `sales` và kiểu `Sale` ở ví dụ hoàn chỉnh. `BigDecimal::add` phù hợp về ngữ nghĩa tổng tiền, nên có thể dùng trong cả `toMap` và `toConcurrentMap` nếu dữ liệu đầu vào hợp lệ. Ngược lại, chính sách “first wins” chỉ có ý nghĩa khi **định nghĩa được first**, còn `toConcurrentMap` không cung cấp thứ tự gặp phần tử để diễn giải “first” theo danh sách ban đầu.

| Tình huống | Lựa chọn |
|---|---|
| Mọi lần gộp phải cho cùng tổng hoặc cùng cực đại xác định | Hàm merge kết hợp nhóm; nếu thứ tự không được bảo đảm, nên chọn thêm quy tắc không phụ thuộc hoán vị |
| Muốn giá trị đầu tiên/cuối cùng theo List có thứ tự | Nêu rõ encounter order; dùng `toMap` trên pipeline có thứ tự, tránh loại bỏ ràng buộc thứ tự |
| Muốn tối ưu thu thập song song không cần thứ tự | Cân nhắc `toConcurrentMap` với phép gộp an toàn khi chạy đồng thời |
| Cần nhóm mọi giá trị theo khóa thay vì chọn một giá trị | `groupingBy` hoặc `groupingByConcurrent` với downstream collector phù hợp |
| Cần hiển thị khóa Map theo thứ tự | Chọn `LinkedHashMap` hoặc `TreeMap` đúng yêu cầu, không phụ thuộc Map mặc định |

**Lưu ý về hiệu năng:** `toMap` trên parallel stream có thể phải gộp các Map trung gian, làm phát sinh chi phí. `toConcurrentMap` có thể tránh một số chi phí gộp bằng cập nhật concurrent, nhưng không mặc định nhanh hơn trong mọi tình huống: nhiều giá trị cùng một khóa có thể gây tranh chấp. Chỉ thay đổi khi thực sự không cần thứ tự và đã đo với tập dữ liệu tương ứng.

## 9. Những trường hợp đặc biệt của Map.merge

Collectors dùng cơ chế gộp các giá trị theo khóa. Do đó, cần hiểu thêm các giới hạn:

### 9.1. Giá trị null và kết quả merge null

`Map.merge(key, value, remappingFunction)` không nhận một `value` đầu vào null. Vì vậy, nếu `valueMapper` của `toMap` trả null, collector thường ném `NullPointerException` thay vì coi null là “không có giá trị”. Hãy lọc hoặc chuẩn hóa dữ liệu trước khi thu thập.

```java
Map<String, String> byCode = sales.stream()
        .filter(sale -> sale.getTicket() != null)
        .collect(Collectors.toMap(
                Sale::getSku,
                Sale::getTicket,
                (oldValue, newValue) -> newValue));
```

Nếu chính **mergeFunction trả null**, `Map.merge` có ngữ nghĩa **xóa ánh xạ cho khóa đó**. Ví dụ, gặp hai giá trị trùng khóa có thể xóa khóa, rồi một phần tử sau đó lại thêm khóa mới. Đây là logic khác với “bỏ qua giá trị không hợp lệ”, và rất dễ khiến kết quả phụ thuộc cách chia/gộp Stream. Nếu mục đích là bỏ bản ghi không hợp lệ, dùng `filter` trước `collect`.

Đối với khóa null, các implementation Map có hợp đồng khác nhau. Không dựa vào hành vi null key vô tình quan sát được từ một loại Map mặc định; đặc biệt, `ConcurrentHashMap` và `TreeMap` với thứ tự tự nhiên không chấp nhận khóa null. Tốt nhất chuẩn hóa hoặc loại khóa null theo hợp đồng nghiệp vụ trước khi collect.

### 9.2. Side effect trong mergeFunction

`mergeFunction` có thể được gọi nhiều lần và có thể được gọi khi collector kết hợp kết quả từ các nhánh. Không nên dùng nó để tăng một biến đếm ngoài, gửi giao dịch, gọi API ngoài hoặc sửa dữ liệu nguồn:

```java
// Không nên để một biến mutable chung bị thay đổi trong mergeFunction,
// nhất là khi pipeline chạy song song.
// (oldValue, newValue) -> {
//     externalCounter++;
//     return oldValue + newValue;
// }

// Nên biểu diễn phép gộp thuần:
java.util.function.BinaryOperator<Integer> add = Integer::sum;
```

Không nên dùng tác dụng phụ trong mergeFunction để đếm bản ghi: các lời gọi có thể diễn ra ở những giai đoạn gộp khác nhau và trên những worker khác nhau; nếu phép gộp xóa khóa bằng cách trả null, việc suy số bản ghi từ số lần gọi còn dễ sai hơn. Nếu muốn **đếm số bản ghi theo khóa**, dùng `groupingBy(..., counting())` hoặc merge trực tiếp số đếm `1` cho từng phần tử.

```java
Map<String, Long> countBySku = sales.parallelStream()
        .collect(Collectors.toMap(
                Sale::getSku,
                sale -> 1L,
                Long::sum));

System.out.println(countBySku.get("P01")); // 3
```

### 9.3. Độ chính xác của số thực và tràn số

Phép cộng `double` không kết hợp nhóm **theo bit** vì sai số làm tròn. Ví dụ `(1e16 + -1e16) + 1` có thể khác `1e16 + (-1e16 + 1)`. Khi kết quả phải ổn định và chính xác theo tiền tệ, dùng `BigDecimal` cho giá trị thập phân hoặc số nguyên theo đơn vị nhỏ nhất với giới hạn phù hợp. Phép cộng số nguyên là kết hợp nhóm theo ngữ nghĩa tràn kiểu Java, nhưng số tổng có thể không còn đúng theo giá trị toán học mong muốn; không xem việc không đổi theo thứ tự là đảm bảo không tràn.

## 10. Những lỗi dễ mắc và cách xử lý

| Cách làm dễ sai | Hậu quả | Hướng xử lý |
|---|---|---|
| `toMap(key, value)` khi có khóa trùng | `IllegalStateException` | Khẳng định khóa phải duy nhất hoặc cung cấp mergeFunction |
| `(a, b) -> (a + b) / 2` để tính trung bình | Không kết hợp nhóm, trung bình sai | Gộp tổng và số lượng; dùng `averaging...` |
| `(a, b) -> a - b` | Phụ thuộc cách phân hoạch và thứ tự | Thiết kế lại phép tổng hợp có tính kết hợp nhóm |
| Dùng keepFirst/keepLast sau `unordered()` | Bản ghi được giữ có thể không xác định theo nghiệp vụ | Quy định thứ tự hoặc chọn theo version/time và phá hòa |
| Dùng `toConcurrentMap` để tìm “bản ghi cuối” | Thứ tự worker không phải thứ tự sự kiện | Chọn cực đại theo timestamp/version với tie-breaker |
| Tin thứ tự duyệt `HashMap` là thứ tự đầu vào | Đầu ra có thể đổi thứ tự | Dùng `LinkedHashMap`/`TreeMap` đúng mục đích |
| `valueMapper` trả null | Lỗi khi thu thập | Lọc hoặc chuẩn hóa trước |
| Merge trả null để “bỏ qua” | Có thể xóa khóa và làm kết quả bất ngờ | Dùng `filter` cho chính sách bỏ qua |
| Merge làm thay đổi biến chung | Data race, side effect khó dự đoán | Viết hàm thuần; thu thập count/tổng thành giá trị |
| Dùng `int`/`double` cho tiền tệ nhạy độ chính xác | Tràn hoặc sai số | Dùng `BigDecimal` hay miền số được kiểm soát |

## 11. Bài tập tự kiểm tra có đáp án

### Bài 1. Kiểm tra phép merge giữ cũ

```java
java.util.function.BinaryOperator<String> f = (a, b) -> a;
```

Hãy so `f(f("A", "B"), "C")` và `f("A", f("B", "C"))`. Sau đó đảo đầu vào `"A"` và `"B"`.

**Đáp án:** Hai cách đặt ngoặc đều trả `"A"`, nên toán tử kết hợp nhóm; `f("A", "B")` trả `"A"` còn `f("B", "A")` trả `"B"`, nên không giao hoán.

### Bài 2. Trung bình từng cặp

Cho các giá trị `10, 20, 40` cùng khóa. Dùng merge `(a, b) -> (a + b) / 2` có tính đúng trung bình không?

**Đáp án:** Không. Nếu nhóm trái trước cho `27.5`, nhóm phải trước cho `20.0`; trung bình đúng là khoảng `23.333...`. Giữ `sum` và `count` hoặc dùng downstream `averagingInt`.

### Bài 3. Bản ghi cuối và bản ghi mới nhất

Ba sự kiện cùng mã `P01` có các timestamp lần lượt `100, 130, 120`. Nếu chọn bằng `(oldValue, newValue) -> newValue` trên Stream tuần tự theo thứ tự này, kết quả là timestamp nào? Nếu cần mới nhất thì làm gì?

**Đáp án:** Keep-last chọn `120` vì nó xuất hiện cuối. Muốn timestamp mới nhất là `130`, dùng phép chọn cực đại theo timestamp (và tie-breaker nếu có thể hòa).

### Bài 4. Thứ tự khóa Map và thứ tự merge

`Collectors.toMap(..., LinkedHashMap::new)` có tự làm mergeFunction không kết hợp nhóm trở nên đúng trên parallel stream không?

**Đáp án:** Không. `LinkedHashMap` chỉ cung cấp một chính sách thứ tự chèn khóa. Tính kết hợp của các giá trị được gộp là yêu cầu độc lập.

### Bài 5. Có thể sử dụng merge không giao hoán trong toMap?

**Đáp án:** Có, khi phép gộp có tính kết hợp nhóm và nghiệp vụ có thứ tự cần được giữ. Ví dụ `(a, b) -> a + "|" + b` có tính kết hợp nhóm nhưng không giao hoán. Khi không có encounter order, kết quả ghép chuỗi có thể đổi thứ tự.

### Bài 6. Tổng số lượng theo khóa

Cho các dòng có mã `A, B, A, A`. Dùng `toMap` để đếm số phần tử theo mã, có thể dùng hàm merge nào?

```java
Map<String, Long> counts = codes.stream()
        .collect(Collectors.toMap(
                code -> code,
                code -> 1L,
                Long::sum));
// A -> 3, B -> 1
```

Đoạn minh họa giả định `codes` là `List<String>` chứa `"A", "B", "A", "A"` không null. Vì phép cộng số đếm kết hợp nhóm và giao hoán, kết quả không phụ thuộc thứ tự mã.

## 12. Nguyên tắc thiết kế một mergeFunction đúng

Trước khi dùng `Collectors.toMap` hoặc `toConcurrentMap` trên dữ liệu có khóa trùng, hãy xác định: **khóa có thể trùng vì sao**, **kết quả mong muốn là tổng, chọn phần tử hay giữ toàn bộ**, **phép merge có tính kết hợp nhóm không**, **thứ tự đầu vào có làm thay đổi ý nghĩa kết quả không**, và **Map đầu ra có cần thứ tự khóa riêng không**. Với phép gộp phụ thuộc thứ tự, hãy xác lập encounter order và tránh làm mất ràng buộc ấy; với phép gộp cần độc lập thứ tự, thiết kế thêm quy tắc chọn xác định hoặc phép tổng hợp có tính giao hoán phù hợp. Kiểm tra dữ liệu rỗng, khóa trùng, đảo thứ tự, xử lý song song và giới hạn về số học để bảo đảm kết quả cuối thực sự đúng với nghiệp vụ.
