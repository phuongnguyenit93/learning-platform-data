# Map.equals() xét cùng các ánh xạ khóa, giá trị

## 1. Khi nào hai Map được coi là bằng nhau?

Trong Java, `Map<K, V>` biểu diễn tập hợp các **ánh xạ từ khóa tới giá trị** (key–value mappings). Hai `Map` được xem là bằng nhau khi chúng chứa **cùng những ánh xạ khóa–giá trị**, dù có thể được tạo từ các lớp triển khai khác nhau hoặc thêm dữ liệu theo thứ tự khác nhau.

Có thể diễn đạt hợp đồng của `Map.equals(Object)` theo quy tắc:

```text
m1.equals(m2) là true nếu:
  1. m2 cũng là một Map;
  2. m1 và m2 có cùng số lượng ánh xạ;
  3. với mỗi khóa trong m1, m2 chứa khóa tương đương
     và giá trị gắn với khóa đó cũng tương đương.
```

Theo đặc tả `Map`, cách định nghĩa chính thức liên hệ với tập các entry: hai map có `entrySet()` bằng nhau thì hai map bằng nhau. Một **entry** là cặp khóa–giá trị.

Ví dụ, hai map cùng chứa `"A" -> 10` và `"B" -> 20` là bằng nhau. Nếu một map đổi `"B" -> 21`, chúng không còn bằng nhau. Nếu có giá trị 20 nhưng gắn với một khóa khác, chúng cũng không bằng nhau.

**Mấu chốt:** `Map.equals()` so sánh **nội dung ánh xạ**, không so sánh hai tham chiếu có trỏ tới cùng một object hay không, không chỉ so danh sách khóa và cũng không chỉ so danh sách giá trị.

## 2. Phân biệt ba tình huống thường bị nhầm

| Tình huống | `Map.equals()` | Giải thích |
| --- | --- | --- |
| Cùng các khóa và cùng giá trị tương ứng, thứ tự thêm khác | `true` | Thứ tự thêm không thuộc tiêu chí equality của `Map` |
| Cùng tập khóa nhưng một giá trị khác | `false` | Đã khác một ánh xạ khóa → giá trị |
| Cùng tập giá trị nhưng giá trị gắn với khóa khác | `false` | Quan hệ ánh xạ khác nhau |
| Cùng cặp ánh xạ nhưng `HashMap` và `LinkedHashMap` | `true` | Khác implementation không làm đổi equality, nếu tuân thủ hợp đồng `Map` |
| Một map có thêm một entry | `false` | Số lượng ánh xạ khác |
| Hai biến tham chiếu tới cùng một map | `true` | Cùng object thì luôn bằng chính nó nếu hợp đồng `equals` được tuân thủ |

Các collection có thứ tự như `LinkedHashMap` có thể giữ thứ tự chèn khi duyệt, và `TreeMap` có thể duyệt theo thứ tự khóa. Nhưng **thứ tự duyệt không phải thành phần trực tiếp của hợp đồng `Map.equals()`**. Đừng dùng `map.toString()` hoặc kết quả duyệt entry làm tiêu chí equality của map.

## 3. Map.equals() phối hợp equals() của khóa và giá trị ra sao?

Một cách hiểu hữu ích: một ánh xạ `(key, value)` được coi là tương đương với `(otherKey, otherValue)` khi:

```java
Objects.equals(key, otherKey)
        && Objects.equals(value, otherValue)
```

Đây là **đoạn biểu thức minh họa**, không phải chương trình độc lập; cần `import java.util.Objects;`. `Objects.equals(a, b)` xử lý được `null`: cả hai cùng `null` thì bằng nhau; nếu chỉ một đối tượng `null`, kết quả là `false`; còn lại dùng `a.equals(b)`.

Khi khóa hoặc giá trị là kiểu do bạn tạo:

- Hai đối tượng khóa **khác instance** vẫn có thể đại diện cho cùng khóa logic nếu `equals(Object)` xác định chúng bằng nhau.
- Hai đối tượng giá trị **khác instance** vẫn có thể tương đương nếu `equals(Object)` của kiểu giá trị trả `true`.
- Nếu hai map có cùng khóa nhưng giá trị không bằng nhau, toàn bộ hai map không bằng nhau.
- `equals(Object)` và `hashCode()` của các kiểu dùng làm khóa phải tuân thủ hợp đồng Java; nếu không, map dựa trên băm có thể hoạt động sai kỳ vọng.

Lưu ý: hai cặp có **cùng giá trị nhưng khác khóa** không trở thành cùng ánh xạ. Map biểu diễn quan hệ “khóa này gắn với giá trị nào”, không phải một tập giá trị độc lập.

## 4. Ví dụ Java 17+: cùng nội dung dù khác implementation và thứ tự

Tạo tệp `MapEqualityDemo.java`:

```java
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.TreeMap;

public class MapEqualityDemo {
    public static void main(String[] args) {
        Map<String, Integer> first = new HashMap<>();
        first.put("A", 10);
        first.put("B", 20);

        Map<String, Integer> second = new LinkedHashMap<>();
        second.put("B", 20);
        second.put("A", 10);

        Map<String, Integer> third = new TreeMap<>();
        third.put("B", 20);
        third.put("A", 10);

        System.out.println(first.equals(second));
        System.out.println(second.equals(first));
        System.out.println(first.equals(third));
        System.out.println(first.hashCode() == second.hashCode());

        second.put("B", 21);
        System.out.println(first.equals(second));

        second.put("B", 20);
        second.remove("A");
        System.out.println(first.equals(second));

        Map<String, Integer> withNull = new HashMap<>();
        withNull.put("missing", null);
        System.out.println(withNull.get("missing") == null);
        System.out.println(withNull.containsKey("missing"));
        System.out.println(withNull.equals(Map.of()));
    }
}
```

Biên dịch và chạy:

```bash
javac MapEqualityDemo.java
java MapEqualityDemo
```

Kết quả:

```text
true
true
true
true
false
false
true
true
false
```

Giải thích:

1. `first`, `second` và `third` đều có `A -> 10`, `B -> 20`. Dù lớp triển khai và thứ tự thêm khác nhau, `equals` vẫn trả `true` giữa chúng.
2. Hai map bằng nhau phải có cùng `hashCode()`. Vì vậy phép so sánh mã băm trả `true`. Chiều ngược lại không đúng: cùng hash chưa chứng minh hai map bằng nhau.
3. Đổi `B` từ 20 thành 21 làm một entry khác đi, nên `first.equals(second)` thành `false`.
4. Khôi phục giá trị `B` rồi xóa entry `A` khiến map còn một entry; kích thước khác nhau nên vẫn `false`.
5. `withNull.get("missing") == null` là `true`, nhưng `containsKey("missing")` cũng là `true`: map có entry `"missing" -> null`. Map rỗng `Map.of()` không bằng map chứa một entry này.

Ví dụ dùng `HashMap`, `LinkedHashMap`, `TreeMap` với khóa `String` theo thứ tự tự nhiên. Một `TreeMap` dùng comparator **không nhất quán với `equals` của khóa** có thể phá các kỳ vọng equality khi so sánh chéo các implementation; xem phần lưu ý phía dưới.

## 5. Nếu khóa và giá trị đều là đối tượng tự định nghĩa

Java record có thể biểu diễn một kiểu giá trị bất biến đơn giản và tự cung cấp `equals(Object)` cùng `hashCode()` theo các thành phần record.

Tạo tệp `MapObjectValueDemo.java`:

```java
import java.util.HashMap;
import java.util.Map;

public class MapObjectValueDemo {
    record ProductId(String code) {}
    record PriceTag(int amount, String currency) {}

    public static void main(String[] args) {
        ProductId keyOne = new ProductId("P-001");
        ProductId keyTwo = new ProductId("P-001");

        PriceTag priceOne = new PriceTag(120, "VND");
        PriceTag priceTwo = new PriceTag(120, "VND");

        System.out.println(keyOne == keyTwo);
        System.out.println(keyOne.equals(keyTwo));
        System.out.println(priceOne.equals(priceTwo));

        Map<ProductId, PriceTag> left = new HashMap<>();
        left.put(keyOne, priceOne);

        Map<ProductId, PriceTag> right = new HashMap<>();
        right.put(keyTwo, priceTwo);

        System.out.println(left.equals(right));

        right.put(keyTwo, new PriceTag(130, "VND"));
        System.out.println(left.equals(right));

        right.clear();
        right.put(new ProductId("P-002"), priceOne);
        System.out.println(left.equals(right));
    }
}
```

Chạy trên JDK 17+:

```bash
javac MapObjectValueDemo.java
java MapObjectValueDemo
```

Stdout:

```text
false
true
true
true
false
false
```

`keyOne` và `keyTwo` là hai object khác tham chiếu (dòng đầu `false`) nhưng cùng `code`, nên bình đẳng theo giá trị (`true`). `priceOne` và `priceTwo` tương tự. Vì hai map chứa cùng ánh xạ logic `P-001 -> (120, VND)`, `left.equals(right)` là `true`.

Đổi giá trị tương ứng thành 130 khiến hai map khác nhau. Tiếp theo, dù lại dùng giá trị `priceOne`, thay khóa bằng `P-002` vẫn làm hai map khác nhau. Qua đó thấy rõ điều kiện equality gồm **cả khóa và giá trị gắn với khóa đó**.

Record không tự biến các thành phần mutable được chứa bên trong thành bất biến sâu. Ví dụ `record DataKey(List<String> parts) {}` vẫn giữ tham chiếu tới danh sách có thể thay đổi. Khi dùng record làm khóa, cần bảo đảm trạng thái tham gia `equals/hashCode` ổn định khi đang nằm trong map.

## 6. Map.hashCode() cũng dựa trên các entry

Theo hợp đồng `Map.hashCode()`, mã băm của map bằng **tổng các mã băm của entry** trong `entrySet()`. Mã băm của một `Map.Entry` theo hợp đồng là:

```text
entryHash = hashCode(key) XOR hashCode(value)
            (null được tính là 0)

mapHash = tổng entryHash của tất cả entry
```

Điều này giải thích vì sao hai map bằng nhau phải có cùng hash **mà không phụ thuộc thứ tự duyệt entry**: phép cộng không phụ thuộc thứ tự. Tuy vậy, hai map khác nhau vẫn có thể trùng hash do collision; tuyệt đối không dùng `map1.hashCode() == map2.hashCode()` thay cho `map1.equals(map2)`.

Có thể kiểm chứng hợp đồng trên một map đơn giản:

```java
Map<String, Integer> m = Map.of("A", 10, "B", 20);
int sumOfEntries = m.entrySet().stream()
        .mapToInt(Map.Entry::hashCode)
        .sum();
boolean sameHash = m.hashCode() == sumOfEntries;
```

Đây là **đoạn mã minh họa**, cần `import java.util.Map;`. `sameHash` phải là `true` với một implementation tuân thủ hợp đồng `Map`.

Mã băm của một map không phải ID duy nhất, chữ ký số hay giá trị bền vững để lưu vào hệ thống khác. Nếu khóa hoặc giá trị mutable thay đổi những trường tham gia equality, mã băm map cũng có thể thay đổi.

## 7. Null, map rỗng và sự khác biệt giữa “không có khóa” và “có khóa ánh xạ tới null”

Ba map sau không bằng nhau:

```text
{}                   (không có entry)
{"x" -> null}        (một entry có value null)
{null -> "x"}        (một entry có key null)
```

`HashMap` cho phép tối đa một khóa `null` và có thể có nhiều khóa khác nhau mang giá trị `null`. `Map.of(...)` và `Map.ofEntries(...)` không cho phép khóa hay giá trị `null`; nhiều implementation khác cũng có chính sách riêng.

- `get(key) == null` **không phân biệt** một khóa không tồn tại và một khóa đang ánh xạ đến `null`.
- `containsKey(key)` trả lời khóa có tồn tại hay không.
- Hai map chỉ bằng nhau khi tình trạng **tồn tại khóa** và **giá trị đi kèm** tương ứng. Một entry `"x" -> null` phải được so với entry có cùng khóa và cũng có giá trị `null`.

Khi cần xử lý `null`, dựa vào hợp đồng của implementation cụ thể trước khi gọi `put(null, value)` hoặc `put(key, null)`. Đừng suy rằng mọi `Map` đều hỗ trợ null chỉ vì `HashMap` hỗ trợ.

## 8. Map khác List và Set về điều kiện equality

Mỗi collection có hợp đồng equality riêng:

| Kiểu | Điều kiện bằng nhau chính | Thứ tự có quan trọng? |
| --- | --- | --- |
| `List` | Cùng độ dài, các phần tử cùng vị trí tương đương | **Có** |
| `Set` | Cùng các phần tử logic | Thông thường **không** |
| `Map` | Cùng các ánh xạ khóa–giá trị | **Không** theo hợp đồng Map |

Ví dụ, `List.of("A", "B")` không bằng `List.of("B", "A")`. Nhưng một map chứa `A -> 1` rồi `B -> 2` vẫn bằng map tạo `B -> 2` rồi `A -> 1`.

Đồng thời, map **không chỉ là tập khóa**: hai map có cùng keySet nhưng các value khác nhau thì không bằng nhau. Nó cũng không chỉ là một tập value: nếu đổi hai giá trị giữa hai khóa thì các ánh xạ đã thay đổi.

## 9. Những ngoại lệ và tình huống cần cẩn trọng

### Comparator không nhất quán với equals

`TreeMap` dùng comparator hoặc natural ordering để xác định hai khóa được xem là cùng vị trí trong cấu trúc cây. Nếu comparator trả 0 cho hai khóa mà `equals` lại trả `false`, map có thể coi chúng là cùng khóa trong thao tác `put/get` nhưng các map dùng equality thông thường lại phân biệt chúng.

Ví dụ comparator không phân biệt chữ hoa/thường có thể xem `"A"` và `"a"` tương đương về thứ tự, trong khi `String.equals` phân biệt chúng. JavaDoc của `TreeMap` yêu cầu thứ tự phải **nhất quán với equals** nếu muốn tuân thủ đúng hợp đồng `Map` khi so sánh giữa các implementation.

Một `TreeMap<BigDecimal, ...>` dùng thứ tự tự nhiên cũng cần cân nhắc tương tự, vì `new BigDecimal("2.0").compareTo(new BigDecimal("2.00")) == 0`, trong khi `equals` trả `false`.

### IdentityHashMap không dùng equality thông thường

`IdentityHashMap` chủ ý xem hai khóa bằng nhau khi **cùng tham chiếu (`==`)** thay vì `equals`. Đây là implementation đặc biệt mà tài liệu Java nói rõ là **không tuân thủ hợp đồng chung của `Map` về equality theo đối tượng**. Vì vậy không nên dùng nó như một lựa chọn thay thế trực tiếp cho `HashMap` nếu mã gọi dựa vào `Map.equals()` theo giá trị.

### Giá trị mutable và key mutable

Hai map hiện tại có thể bằng nhau nhưng về sau trở thành không bằng nhau nếu một đối tượng value bên trong bị sửa làm `equals` thay đổi. Nếu đối tượng key bị sửa làm `hashCode` hoặc `equals` thay đổi sau khi đã thêm vào `HashMap`, việc tra cứu và `Map.equals()` cũng có thể không còn đáng tin cậy theo ý định ban đầu.

Đặc biệt, tránh **đưa chính map làm khóa hoặc giá trị của nó theo một cấu trúc tự tham chiếu** rồi trông chờ các phương thức `equals/hashCode/toString` xử lý an toàn; một số phép toán có thể không còn được định nghĩa tốt với cấu trúc đệ quy này.

## 10. Cách áp dụng trong code và kiểm thử

1. **Định nghĩa bình đẳng của khóa:** nếu hai key được coi là cùng thực thể logic, cài `equals(Object)` và `hashCode()` tương thích. Cân nhắc dùng record hoặc kiểu bất biến cho khóa.
2. **Định nghĩa bình đẳng của giá trị:** kiểm tra xem `equals` của value có phản ánh đúng điều kiện nghiệp vụ hay không. Ví dụ `BigDecimal.equals` phân biệt scale; `List.equals` phân biệt thứ tự.
3. **Kiểm thử khác thứ tự chèn:** tạo `HashMap` và `LinkedHashMap` với cùng mapping theo thứ tự ngược nhau; chúng vẫn phải bằng nhau.
4. **Kiểm thử thay đổi một thành phần:** đổi value của một key hoặc thay key, xác minh `Map.equals` trở thành `false`.
5. **Kiểm thử null và thiếu khóa:** phân biệt map có `"x" -> null` với map rỗng; dùng `containsKey` khi cần.
6. **Kiểm tra hash:** hai map bằng nhau phải có cùng `hashCode`; không dùng hash bằng nhau để suy ra map bằng nhau.
7. **Kiểm tra collection có comparator đặc biệt:** tránh giả định comparator trả 0 có nghĩa `equals` của khóa cũng trả `true`.
8. **Không so bằng chuỗi hiển thị:** thay vì so `map.toString()`, hãy dùng `map.equals(other)` khi mục đích là cùng nội dung ánh xạ.
9. **Giữ trạng thái ổn định khi so sánh:** không thay đổi map hoặc object khóa/giá trị đồng thời trong lúc thao tác equality; các collection thông thường không tự thread-safe.

**Tự kiểm tra:**

- Hai map có `A -> 1`, `B -> 2` nhưng thứ tự chèn ngược nhau có bằng nhau không? **Có.**
- Hai map có cùng `keySet()` nhưng một map chứa `B -> 3` thay vì `B -> 2` có bằng nhau không? **Không.**
- Hai map có cùng danh sách giá trị nhưng ánh xạ sang khóa khác nhau có bằng nhau không? **Không.**
- Một map chứa entry `A -> null` có bằng map rỗng không? **Không.**
- Hai map bằng nhau có bắt buộc `hashCode()` bằng nhau không? **Có.**

**Ghi nhớ:** `Map.equals(Object)` biểu thị **sự tương đương của toàn bộ các ánh xạ khóa–giá trị**. Cùng số entry, cùng khóa logic và giá trị tương ứng bằng nhau mới làm hai map bằng nhau; thứ tự chèn, thứ tự duyệt và lớp triển khai thông thường không quyết định kết quả.