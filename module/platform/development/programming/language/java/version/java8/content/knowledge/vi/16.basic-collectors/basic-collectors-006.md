# Merge function khi nhiều phần tử có cùng khóa

## 1. Vấn đề: nhiều phần tử tạo ra cùng một khóa

Khi biến một `Stream<T>` thành `Map<K,V>`, mỗi phần tử nguồn được ánh xạ thành một cặp **khóa** và **giá trị**. Dữ liệu thực tế thường có khóa lặp lại: nhiều dòng hóa đơn cùng mã sản phẩm (SKU), nhiều sự kiện cùng người dùng, hoặc nhiều bản ghi cùng mã nhóm. Khi đó, chương trình phải quyết định **gộp giá trị nào và bằng quy tắc nào**.

Ví dụ ba dòng bán hàng:

| SKU | Số lượng | Kết quả mong muốn |
| --- | ---: | --- |
| JAVA | 2 | |
| SQL | 1 | |
| JAVA | 3 | `{JAVA=5, SQL=1}` |

Trong Java Stream, cách viết sau **không cộng tự động** số lượng của những dòng cùng khóa:

```java
Map<String, Integer> quantityBySku = sales.stream()
    .collect(Collectors.toMap(Sale::sku, Sale::quantity));
```

Nếu hai phần tử ánh xạ tới cùng khóa, dạng `toMap(keyMapper, valueMapper)` **ném `IllegalStateException`** khi thu thập. Trong ví dụ này, hai phần tử có khóa `"JAVA"`. Đây là hành vi đúng theo hợp đồng API, nhằm tránh tự ý mất dữ liệu khi có khóa trùng.

> Những đoạn code ngắn trong bài sử dụng lớp `Sale` và danh sách `sales` được khai báo đầy đủ ở mục 5. Chúng minh họa ý tưởng; chương trình ở mục 5 có thể biên dịch và chạy độc lập.

## 2. `Collectors.toMap` có merge function

Dạng phổ biến để xử lý trùng khóa:

```java
Collectors.toMap(keyMapper, valueMapper, mergeFunction)
```

Khai báo kiểu tổng quát của Java:

```java
<T, K, U> Collector<T, ?, Map<K, U>> toMap(
    Function<? super T, ? extends K> keyMapper,
    Function<? super T, ? extends U> valueMapper,
    BinaryOperator<U> mergeFunction
)
```

- **`keyMapper`**: trích khóa `K` của từng phần tử nguồn, ví dụ `Sale::sku`.
- **`valueMapper`**: trích giá trị `U` cần lưu/gộp, ví dụ `Sale::quantity`.
- **`mergeFunction`**: nhận **hai giá trị cùng khóa** và trả lại một giá trị hợp nhất cùng kiểu `U`, ví dụ `Integer::sum`. Nó **không** nhận khóa `K`.

Cách đọc biểu thức:

```java
Map<String, Integer> quantityBySku = sales.stream()
    .collect(Collectors.toMap(
        Sale::sku,             // khóa: mã sản phẩm
        Sale::quantity,        // giá trị: số lượng của dòng này
        Integer::sum          // gặp cùng khóa: cộng hai số lượng
    ));
```

Với một khóa mới, `toMap` ghi giá trị do `valueMapper` tạo ra. Khi gặp cùng khóa, nó gọi `mergeFunction` để gộp giá trị đã có với giá trị mới, rồi lưu kết quả cho khóa đó. Quy tắc gộp áp dụng lặp lại nếu khóa xuất hiện lần thứ ba, thứ tư, v.v.

Một cách diễn giải đơn giản:

```text
JAVA -> 2
SQL  -> 1
JAVA -> 3   => merge(2, 3) = 5

Kết quả: JAVA -> 5, SQL -> 1
```

Giả sử `(existing, incoming) -> existing + incoming`. Hai tham số là **giá trị** tương ứng của các bản ghi/nhóm đã được gom; trong pipeline song song, `incoming` có thể là kết quả của một nhóm con chứ không nhất thiết là phần tử kế tiếp theo thứ tự danh sách. Không nên viết quy tắc phụ thuộc vào số lần hoặc thứ tự gọi merge function.

### 2.1. Dạng bốn tham số: chọn loại `Map`

```java
Map<String, Integer> quantityBySku = sales.stream()
    .collect(Collectors.toMap(
        Sale::sku,
        Sale::quantity,
        Integer::sum,
        TreeMap::new
    ));
```

Tham số thứ tư `mapFactory` tạo `Map` đích. Ví dụ `TreeMap::new` cho kết quả sắp theo thứ tự khóa tự nhiên; `LinkedHashMap::new` hữu ích nếu muốn giữ thứ tự chèn các khóa khi thu thập tuần tự từ một nguồn có thứ tự. Khi không truyền `mapFactory`, đừng dựa vào kiểu `Map` cụ thể, tính sửa được hay thứ tự duyệt của kết quả.

**Chọn loại `Map` theo yêu cầu nghiệp vụ:** một `TreeMap` dùng bộ so sánh để xác định khóa tương đương; một `HashMap` thường dùng `equals/hashCode`. Hai khóa hiển thị khác nhau vẫn có thể bị xem là trùng nếu phép so sánh khóa xem chúng tương đương.

## 3. Chọn chiến lược gộp phù hợp

Merge function là **quy tắc nghiệp vụ**. Phần khó không nằm ở cú pháp lambda mà ở việc chọn đúng ý nghĩa cho nhiều bản ghi cùng khóa.

| Yêu cầu khi trùng khóa | Merge function | Ý nghĩa |
| --- | --- | --- |
| Cộng số lượng | `Integer::sum` hoặc `Long::sum` | Tổng số lượng thuộc cùng mã. |
| Cộng tiền chính xác | `BigDecimal::add` | Tổng số tiền thuộc cùng mã, nếu `valueMapper` trả `BigDecimal`. |
| Lấy số lớn nhất | `Integer::max` hoặc `BigDecimal::max` | Giá trị lớn nhất của nhóm. |
| Lấy số nhỏ nhất | `Integer::min` hoặc `BigDecimal::min` | Giá trị nhỏ nhất của nhóm. |
| Giữ giá trị gộp bên trái | `(left, right) -> left` | Chọn bên trái theo cách các nhóm được kết hợp. |
| Chọn giá trị bên phải | `(left, right) -> right` | Chọn bên phải theo cách các nhóm được kết hợp. |
| Coi trùng khóa là lỗi nghiệp vụ | Lambda ném exception có thông báo rõ | Không âm thầm gộp bản ghi vốn phải duy nhất. |

### 3.1. Cộng số lượng và doanh thu

```java
Map<String, Integer> units = sales.stream()
    .collect(Collectors.toMap(
        Sale::sku, Sale::quantity, Integer::sum
    ));

Map<String, BigDecimal> revenue = sales.stream()
    .collect(Collectors.toMap(
        Sale::sku, Sale::revenue, BigDecimal::add
    ));
```

Nếu có nhiều dòng JAVA, tổng số lượng là tổng các `quantity`; doanh thu là tổng `quantity × unitPrice` của **từng dòng**, chứ không phải lấy tổng số lượng nhân với đơn giá tùy chọn khi giá có thể thay đổi giữa các dòng. `BigDecimal` phù hợp cho các phép cộng tiền tệ thập phân; khởi tạo nó từ chuỗi thay vì một `double` có sai số biểu diễn.

### 3.2. Giữ một bản ghi hay chọn bản ghi tốt nhất

```java
Map<String, Sale> chooseLeft = sales.stream()
    .collect(Collectors.toMap(
        Sale::sku, Function.identity(), (left, right) -> left
    ));

Map<String, Sale> chooseRight = sales.stream()
    .collect(Collectors.toMap(
        Sale::sku, Function.identity(), (left, right) -> right
    ));
```

`Function.identity()` giữ nguyên bản ghi đầu vào làm giá trị `Map`. Trong pipeline tuần tự có encounter order xác định, hai lambda trên thể hiện lựa chọn bên trái/bên phải trong quá trình gộp. **Không dùng “bên phải” như định nghĩa của “bản ghi mới nhất”** nếu dữ liệu chưa có chính sách thứ tự thời gian hoặc mã phiên bản: bản ghi được duyệt sau chưa chắc được tạo sau.

Nếu yêu cầu là chọn giá trị lớn nhất, biểu đạt trực tiếp bằng phép toán có ý nghĩa:

```java
Map<String, BigDecimal> maxPrice = sales.stream()
    .collect(Collectors.toMap(
        Sale::sku, Sale::unitPrice, BigDecimal::max
    ));
```

Nếu cần “bản ghi có thời gian cập nhật mới nhất”, hãy lưu timestamp trong giá trị và so sánh timestamp khi merge. Cần quy định thêm cách xử lý hai bản ghi cùng timestamp (ví dụ so theo ID duy nhất) để kết quả không mơ hồ; `(a, b) -> b` đơn thuần không giải quyết yêu cầu đó.

### 3.3. Khi trùng khóa phải được báo lỗi

Nếu SKU bắt buộc duy nhất trong đầu vào, việc cộng hoặc ghi đè sẽ che giấu sai lệch dữ liệu. Dùng dạng `toMap` không có merge function để phát hiện `IllegalStateException`, hoặc xây dựng cơ chế kiểm tra có thể báo **chính xác SKU trùng** trước khi lưu. Merge function chỉ nhận hai **giá trị**, nên không mặc nhiên biết khóa gây xung đột.

## 4. Trùng khóa được xác định như thế nào?

### 4.1. Khóa từ `keyMapper` mới quyết định xung đột

Giả sử đầu vào có `"java"`, `"JAVA"` và `" Java "`. Nếu nghiệp vụ coi đây là cùng SKU, hãy chuẩn hóa ở `keyMapper` một cách **có chủ đích**:

```java
Map<String, Integer> units = sales.stream()
    .collect(Collectors.toMap(
        sale -> sale.sku().trim().toUpperCase(Locale.ROOT),
        Sale::quantity,
        Integer::sum
    ));
```

`Locale.ROOT` hữu ích cho chuẩn hóa mã nhận dạng độc lập với ngôn ngữ hiển thị. Chỉ chuẩn hóa khi nghiệp vụ thật sự coi khác biệt chữ hoa/thường/khoảng trắng là không có ý nghĩa; có hệ thống coi mã `"a"` khác mã `"A"`. Validate mã rỗng hoặc không hợp lệ trước khi tổng hợp.

Với `HashMap`, hai khóa bằng nhau theo `equals` (và có `hashCode` phù hợp) sẽ đụng nhau. Với `TreeMap`, sự tương đương phụ thuộc vào comparator/natural ordering. Không nên lấy chuỗi hiển thị làm bằng chứng rằng hai đối tượng khóa là khác nhau.

### 4.2. Phải định nghĩa chính sách dữ liệu `null`

`Map.merge` yêu cầu **giá trị mới khác `null`**. Vì `Collectors.toMap` có merge function dùng quy tắc `Map.merge`, đừng để `valueMapper` trả `null` và mong giá trị được bỏ qua tự động; nó có thể gây `NullPointerException`. Khả năng chấp nhận khóa `null` phụ thuộc loại `Map` và collector; `TreeMap` với thứ tự tự nhiên và `ConcurrentHashMap` không chấp nhận khóa `null`. Tốt nhất validate, loại hoặc thay thế giá trị thiếu theo quy tắc nghiệp vụ **trước** `collect`.

Merge function trả `null` cũng **không có nghĩa là “giữ nguyên”**: theo hợp đồng `Map.merge`, nó có thể xóa mapping của khóa đang gộp. Nếu muốn bỏ qua giá trị mới, trả lại `existing` (giá trị khác `null`), không trả `null`.

## 5. Chương trình đầy đủ: xử lý nhiều dòng bán hàng cùng SKU

Ví dụ minh họa bốn lựa chọn có ý nghĩa khác nhau: báo lỗi trùng khóa, cộng số lượng, cộng doanh thu và chọn đơn giá lớn nhất. Đồng thời so sánh `Collectors.toMap` với `Map.merge` khi cập nhật bản đồ trực tiếp. Chương trình dùng **Java 8 APIs và cú pháp tương thích Java 8**, chạy được trên JDK 17+.

Tạo tệp **MergeFunctionDemo.java**:

```java
import java.math.BigDecimal;
import java.util.Arrays;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.stream.Collectors;

public class MergeFunctionDemo {
    static final class Sale {
        private final String sku;
        private final int quantity;
        private final BigDecimal unitPrice;

        Sale(String sku, int quantity, String unitPrice) {
            this.sku = sku;
            this.quantity = quantity;
            this.unitPrice = new BigDecimal(unitPrice);
        }

        String sku() { return sku; }
        int quantity() { return quantity; }
        BigDecimal unitPrice() { return unitPrice; }

        BigDecimal revenue() {
            return unitPrice.multiply(BigDecimal.valueOf(quantity));
        }
    }

    public static void main(String[] args) {
        List<Sale> sales = Arrays.asList(
            new Sale("JAVA", 2, "120.00"),
            new Sale("SQL", 1, "90.00"),
            new Sale("JAVA", 3, "120.00"),
            new Sale("API", 2, "50.00"),
            new Sale("JAVA", 1, "130.00")
        );

        try {
            sales.stream().collect(Collectors.toMap(
                Sale::sku, Sale::quantity
            ));
        } catch (IllegalStateException duplicateKey) {
            System.out.println("Khong co merge: loi trung khoa");
        }

        Map<String, Integer> quantityBySku = sales.stream()
            .collect(Collectors.toMap(
                Sale::sku,
                Sale::quantity,
                Integer::sum,
                TreeMap::new
            ));

        Map<String, BigDecimal> revenueBySku = sales.stream()
            .collect(Collectors.toMap(
                Sale::sku,
                Sale::revenue,
                BigDecimal::add,
                TreeMap::new
            ));

        Map<String, BigDecimal> maxPriceBySku = sales.stream()
            .collect(Collectors.toMap(
                Sale::sku,
                Sale::unitPrice,
                BigDecimal::max,
                TreeMap::new
            ));

        Map<String, Long> countBySku = sales.stream()
            .collect(Collectors.groupingBy(
                Sale::sku,
                TreeMap::new,
                Collectors.counting()
            ));

        Map<String, Integer> quantityByMerge = new TreeMap<>();
        for (Sale sale : sales) {
            quantityByMerge.merge(sale.sku(), sale.quantity(), Integer::sum);
        }

        System.out.println("So luong theo SKU: " + quantityBySku);
        System.out.println("Doanh thu theo SKU: " + revenueBySku);
        System.out.println("Gia lon nhat theo SKU: " + maxPriceBySku);
        System.out.println("So dong theo SKU: " + countBySku);
        System.out.println("Map.merge: " + quantityByMerge);
    }
}
```

Biên dịch và chạy trong thư mục chứa tệp:

```bash
javac -encoding UTF-8 MergeFunctionDemo.java
java MergeFunctionDemo
```

**Stdout chính xác:**

```text
Khong co merge: loi trung khoa
So luong theo SKU: {API=2, JAVA=6, SQL=1}
Doanh thu theo SKU: {API=100.00, JAVA=730.00, SQL=90.00}
Gia lon nhat theo SKU: {API=50.00, JAVA=130.00, SQL=90.00}
So dong theo SKU: {API=1, JAVA=3, SQL=1}
Map.merge: {API=2, JAVA=6, SQL=1}
```

Phân tích:

1. **Không có merge function:** SKU `JAVA` xuất hiện ba lần nên `toMap` hai tham số phát sinh `IllegalStateException`. Chương trình bắt exception để minh họa, không in nội dung thông báo vì thông báo có thể thay đổi theo phiên bản JDK.
2. **Cộng số lượng:** `JAVA` có `2 + 3 + 1 = 6`; `SQL=1`, `API=2`.
3. **Cộng doanh thu:** `JAVA = 2 × 120.00 + 3 × 120.00 + 1 × 130.00 = 730.00`. Đây là lý do dùng `Sale::revenue` thay vì gộp giá rồi mới tính.
4. **Lấy giá lớn nhất:** ba đơn giá `JAVA` là `120.00`, `120.00` và `130.00` nên kết quả `130.00`.
5. **Đếm dòng:** `groupingBy(..., counting())` cho biết mỗi SKU có bao nhiêu dòng; nó trả `Long`, khác với tổng `quantity`.
6. **Kết quả dễ kiểm chứng:** `TreeMap::new` làm khóa in theo thứ tự `API`, `JAVA`, `SQL`; kết quả không phụ thuộc thứ tự duyệt của `HashMap`.
7. **`Map.merge`:** vòng lặp thay đổi một `Map` hiện có, còn `Collectors.toMap` xây `Map` từ stream; với phép gộp `Integer::sum`, cả hai cho cùng tổng số lượng.

## 6. Chọn `toMap`, `groupingBy` hay `Map.merge`

| Mục tiêu | API phù hợp | Lý do |
| --- | --- | --- |
| Mỗi khóa gộp thành một giá trị bằng phép cộng/max/min | `Collectors.toMap(key, value, merge)` | Gọn và thể hiện rõ phép gộp. |
| Muốn chủ động loại `Map`, thứ tự khóa | `Collectors.toMap(key, value, merge, mapFactory)` | `TreeMap` hoặc `LinkedHashMap` khi có yêu cầu rõ. |
| Muốn giữ **toàn bộ** các dòng cùng khóa | `Collectors.groupingBy(key)` | Trả `Map<K,List<T>>`, không phải tự ghép các danh sách. |
| Muốn đếm theo khóa | `Collectors.groupingBy(key, counting())` | Diễn đạt rõ đây là số phần tử, không phải tổng giá trị. |
| Muốn vừa nhóm vừa tổng hợp bằng downstream collector | `groupingBy(key, summingInt/mapping/reducing/...)` | Dễ mở rộng sang nhiều kiểu tổng hợp. |
| Đã có một `Map` và nhận thêm dữ liệu từng dòng | `map.merge(key, value, remappingFunction)` | Cập nhật trực tiếp cấu trúc có sẵn. |

Ví dụ cần **giữ tất cả** những dòng cùng SKU để người dùng mở lịch sử đơn hàng:

```java
Map<String, List<Sale>> salesBySku = sales.stream()
    .collect(Collectors.groupingBy(Sale::sku));
```

Không cần lạm dụng `toMap` với merge function tạo nhiều `ArrayList`, ghép rồi đột biến các danh sách đó. `groupingBy` đã thực hiện đúng nhiệm vụ nhóm các phần tử.

Một collector khác nếu chỉ muốn đếm:

```java
Map<String, Long> countBySku = sales.stream()
    .collect(Collectors.groupingBy(
        Sale::sku,
        Collectors.counting()
    ));
```

Nếu yêu cầu là một số đếm mỗi SKU, biểu thức này rõ hơn việc tự ép mọi phép toán vào `toMap`.

**`Map.merge` là API liên quan nhưng khác vai trò:** đối tượng `Map` đã tồn tại, rồi `merge` thêm hoặc gộp giá trị theo khóa. Phương thức này **thay đổi `Map`**. Khi dùng một `HashMap` bình thường, không cho nhiều luồng cùng ghi vào nó mà thiếu đồng bộ. Nếu remapping function trả `null`, mapping có thể bị xóa. Không sửa chính `Map` đang được xử lý từ bên trong remapping function.

## 7. Tính đúng đắn của merge function

### 7.1. Quy tắc gộp nên có tính kết hợp

Khi stream có thể chạy song song, các phần tử có thể được gộp trong từng nhóm con trước khi ghép nhóm. Để kết quả tổng hợp có nghĩa ổn định, phép gộp cần **kết hợp được** (associative):

```text
merge(merge(a, b), c) = merge(a, merge(b, c))
```

Ví dụ `Integer::sum`, `BigDecimal::add`, `Integer::max` phù hợp với ý nghĩa toán học tương ứng. Ngược lại:

```java
(a, b) -> (a + b) / 2
```

không phải cách tính **trung bình của cả nhóm**: kết quả bị ảnh hưởng bởi cách nhóm các phần tử và không phản ánh trọng số số lượng. Nếu cần trung bình theo khóa, dùng `groupingBy(key, averagingInt(...))` hoặc thống kê `sum/count` với chính sách số học phù hợp.

**Tính kết hợp không đồng nghĩa tính giao hoán**. Đối với phép cộng và cực đại, đổi thứ tự toán hạng không làm thay đổi ý nghĩa; còn chính sách chọn bên trái/bên phải phụ thuộc vào cách hợp nhất các nhóm. Đừng dựa vào thứ tự merge function khi dùng unordered/concurrent pipeline, và đừng dùng lựa chọn bên trái/bên phải để giả định thứ tự nghiệp vụ khi không có thông tin thời gian.

### 7.2. Tránh tác dụng phụ, tràn số và làm tròn sai

- Giữ merge function **không có side effect**: không tăng biến toàn cục, không ghi log để dựa vào số lần gọi và không sửa dữ liệu nguồn đang được duyệt.
- `Integer::sum` có thể tràn `int` nếu tổng lớn. Nếu nghiệp vụ cần phát hiện tràn, cân nhắc `Math.addExact` hoặc thiết kế miền giá trị `long`/`BigInteger` phù hợp.
- Với số tiền, chọn `BigDecimal` và quy tắc làm tròn được định nghĩa bởi nghiệp vụ; nếu vừa cộng vừa chia để tính bình quân, cần quyết định `scale`/`RoundingMode`.
- Merge function nên trả kết quả **khác `null`**, không tự thay đổi `Map` đang nhận dữ liệu, và không phụ thuộc thứ tự thực thi.
- Nếu phần tử đầu vào có thể chứa mã trống, số lượng âm bất thường hoặc giá thiếu, cần **validate theo miền nghiệp vụ** trước khi tổng hợp; merge function không thể tự sửa mọi lỗi của dữ liệu đầu vào.

### 7.3. Song song không tự động nhanh hơn

Collector từ `Collectors.toMap` không phải concurrent collector. Trên parallel stream, phần kết hợp phải hợp nhất khóa giữa các `Map` tạm, có thể tốn chi phí. Khi thứ tự không cần thiết và phép gộp thực sự phù hợp với xử lý đồng thời, `Collectors.toConcurrentMap` có các dạng nhận merge function và trả `ConcurrentMap`. Nhưng kết quả của concurrent collector có thể không có encounter order, khóa/giá trị `null` không được hỗ trợ bởi `ConcurrentHashMap` và phép gộp vẫn phải an toàn theo hợp đồng. Dùng song song khi dữ liệu và phép đo hiệu năng chứng minh lợi ích; ưu tiên bản tuần tự dễ kiểm chứng trước.

## 8. Những lỗi dễ mắc và cách tự kiểm tra

1. **Quên merge function:** `toMap(key, value)` có thể ném `IllegalStateException` khi khóa lặp lại. Cần chọn chính sách gộp hoặc xác nhận dữ liệu phải duy nhất.
2. **Dùng `(old, next) -> next` để suy ra “mới nhất”:** thứ tự xử lý khác thời điểm phát sinh; phải so timestamp/version nếu đó là yêu cầu.
3. **Cộng sai cấp độ:** tổng tiền theo SKU phải cộng thành tiền **từng dòng** nếu đơn giá thay đổi, không lấy một đơn giá rồi nhân tổng số lượng.
4. **Tin vào thứ tự mặc định của `Map`:** chỉ dùng `TreeMap`/`LinkedHashMap` với hợp đồng phù hợp khi cần thứ tự ổn định.
5. **Để `valueMapper` trả `null`:** không xem đó là cách bỏ qua dữ liệu; kiểm tra/loại bỏ dữ liệu thiếu theo chính sách trước `toMap`.
6. **Trả `null` từ merge function:** `Map.merge` có thể xóa mapping.
7. **Gộp bằng phép không kết hợp được:** kết quả có thể khác khi chạy song song hoặc khi cách phân nhóm thay đổi.
8. **Dùng `toMap` để giữ nhiều phần tử:** nếu cần `Map<K,List<T>>`, bắt đầu từ `groupingBy`.
9. **Phụ thuộc side effect:** không chia sẻ danh sách hoặc biến đếm có thể thay đổi giữa các lambda.

Tự kiểm tra nhanh:

- Dòng `("A", 2)`, `("B", 3)`, `("A", 4)` qua `toMap(code, quantity, Integer::sum)` cho gì? **Đáp án:** `A → 6, B → 3` (thứ tự khóa tùy loại `Map`).
- Nếu thay `Integer::sum` bằng `Integer::max`, giá trị `A` là bao nhiêu? **Đáp án:** `4`.
- Nếu muốn cả hai dòng thuộc `A` để hiển thị chi tiết, nên dùng gì? **Đáp án:** `groupingBy(code)` để có `Map<K,List<T>>`.
- Nếu có hai bản ghi cùng SKU nhưng khác thời điểm cập nhật, `(left,right)->right` có luôn chọn bản mới nhất không? **Đáp án:** không; phải định nghĩa thứ tự thời gian/tie-break và so sánh theo đó.

## 9. Tham khảo API chính thức

Những cơ chế trên thuộc Stream/Collections API vẫn đang được dùng trên các phiên bản JDK hiện hành:

- [`Collectors.toMap`, `groupingBy`, `toConcurrentMap` — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Collectors.html).
- [`Map.merge` — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Map.html).
- [`Stream` — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Stream.html).
