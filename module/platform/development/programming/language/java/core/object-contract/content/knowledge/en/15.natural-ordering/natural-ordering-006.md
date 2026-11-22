# Khuyến nghị nhất quán giữa `compareTo() == 0` và `equals()`

## 1. Hiểu đúng hai khái niệm “bằng nhau”

Trong Java, một đối tượng có thể tham gia **hai cơ chế so sánh độc lập**:

- **`equals(Object)`** trả về `boolean` để xác định hai đối tượng có bằng nhau về mặt logic hay không. Đây là hợp đồng chung của `Object`; các collection như `HashSet` và `HashMap` dùng nó cùng `hashCode()` để nhận diện phần tử/khóa.
- **`compareTo(T)`** trả về `int` âm, 0 hoặc dương để xác định thứ tự tự nhiên của các đối tượng triển khai `Comparable<T>`. Các collection có thứ tự như `TreeSet` và `TreeMap` dùng phép so sánh này, hoặc một `Comparator` được cung cấp.

Hợp đồng `Comparable` **khuyến nghị mạnh** thứ tự tự nhiên nhất quán với `equals`, nghĩa là:

```java
x.compareTo(y) == 0   // nên tương đương với
x.equals(y)           // true
```

Đây là đoạn biểu thức minh họa, giả sử `x` và `y` cùng kiểu thích hợp và khác `null`.

Viết chính xác bằng logic:

```text
x.compareTo(y) == 0  ⇔  x.equals(y) == true
```

Dấu `⇔` có nghĩa **cả hai chiều đều đúng**:

1. Nếu `compareTo` trả 0 thì `equals` phải trả `true`.
2. Nếu `equals` trả `true` thì `compareTo` phải trả 0.

Điều này nói về **cặp đối tượng có giá trị so sánh**, không có nghĩa `compareTo` phải trả chính xác `-1` hoặc `1` khi chúng khác nhau. Giá trị âm/dương bất kỳ là hợp lệ.

**Mấu chốt:** Đây là **khuyến nghị**, không phải điều kiện bắt buộc để một lớp triển khai `Comparable`. Một số lớp chuẩn, nổi bật là `BigDecimal`, cố ý có thứ tự tự nhiên **không nhất quán** với `equals`; JavaDoc yêu cầu trường hợp này nên được ghi rõ để người sử dụng hiểu hậu quả.

## 2. Vì sao Java khuyến nghị sự nhất quán?

Giả sử một hệ thống định nghĩa hai sản phẩm có cùng mã `sku` là cùng một đối tượng logic. Nếu `equals` dùng `sku` nhưng `compareTo` lại chỉ so giá bán, ta có thể gặp hai tình huống:

- Hai sản phẩm khác mã nhưng cùng giá: `compareTo == 0` dù `equals == false`. Một `TreeSet` có thể bỏ sản phẩm thứ hai vì coi là trùng, trong khi `HashSet` giữ cả hai.
- Hai sản phẩm cùng mã nhưng giá khác: `equals == true` dù `compareTo != 0`. Một `HashSet` coi là trùng, nhưng `TreeSet` có thể giữ hai phần tử mà `equals` lại cho là bằng nhau.

Sự khác biệt này đặc biệt gây khó hiểu nếu cùng đối tượng được truyền lần lượt qua các API nhận `Set`, hoặc khi thay `HashMap` bằng `TreeMap` để sắp xếp khóa.

| Collection | Cơ chế nhận diện hai phần tử/khóa tương đương | Hệ quả khi tiêu chí khác nhau |
| --- | --- | --- |
| `HashSet` | `equals(Object)` và `hashCode()` | Gộp các phần tử bằng nhau theo `equals` |
| `HashMap` | `equals(Object)` và `hashCode()` của khóa | Cập nhật giá trị khi gặp khóa bằng nhau |
| `TreeSet` | `compareTo(T) == 0` hoặc `Comparator.compare(...) == 0` | Coi các phần tử có cùng thứ tự so sánh là một |
| `TreeMap` | `compareTo(T) == 0` hoặc `Comparator.compare(...) == 0` | Coi các khóa so sánh bằng 0 là một khóa |

`TreeSet` và `TreeMap` vẫn vận hành theo **thứ tự so sánh đã cung cấp**, kể cả khi không nhất quán với `equals`. Nhưng khi đó chúng không đáp ứng trọn vẹn ý nghĩa equality mà giao diện `Set`/`Map` thông thường mô tả. API gọi cần hiểu rõ quy tắc này.

Ngoài tính đúng đắn, sự nhất quán còn giúp mã dễ đọc: “hai khóa trùng nhau” có cùng nghĩa dù dữ liệu đang nằm trong map theo băm, map theo thứ tự hay được so sánh trực tiếp.

## 3. Ví dụ sai: compareTo chỉ xét mức ưu tiên, equals xét toàn bộ record

Tạo tệp `InconsistentComparisonDemo.java`:

```java
import java.util.HashSet;
import java.util.Set;
import java.util.TreeSet;

public class InconsistentComparisonDemo {
    record Event(String code, int priority)
            implements Comparable<Event> {

        @Override
        public int compareTo(Event other) {
            return Integer.compare(priority, other.priority);
        }
    }

    public static void main(String[] args) {
        Event a = new Event("E-1", 5);
        Event b = new Event("E-2", 5);

        System.out.println(a.equals(b));
        System.out.println(a.compareTo(b) == 0);

        Set<Event> hashSet = new HashSet<>();
        hashSet.add(a);
        hashSet.add(b);
        System.out.println(hashSet.size());

        Set<Event> treeSet = new TreeSet<>();
        treeSet.add(a);
        treeSet.add(b);
        System.out.println(treeSet.size());
        System.out.println(treeSet.contains(b));
    }
}
```

Chạy với JDK 17 trở lên:

```bash
javac InconsistentComparisonDemo.java
java InconsistentComparisonDemo
```

Kết quả:

```text
false
true
2
1
true
```

Diễn giải:

1. Record `Event` tự sinh `equals(Object)` theo **cả `code` và `priority`**. `a` và `b` khác mã nên `equals` là `false`.
2. `compareTo` chỉ so `priority`. Hai sự kiện đều ưu tiên 5 nên `compareTo == 0`.
3. `HashSet` giữ **2 phần tử** theo equality của record.
4. `TreeSet` chỉ giữ **1 phần tử**, vì thứ tự tự nhiên coi hai sự kiện bằng nhau. `contains(b)` vẫn trả `true` theo tiêu chí của cây, dù đối tượng `b` chưa được thêm thành một phần tử riêng.

`TreeSet.contains(b)` ở đây không chứng minh `a.equals(b)`. Nó chỉ chứng minh cây có phần tử tương đương với `b` theo cách so sánh đang sử dụng.

**Vấn đề thiết kế:** Nếu yêu cầu nghiệp vụ là một sự kiện phân biệt bởi cả mã và mức ưu tiên, `compareTo` thiếu tiêu chí phá hòa (`code`). Nếu mục đích thực sự là gộp sự kiện cùng mức ưu tiên, hãy chủ động diễn đạt quy tắc đó trong cấu trúc dữ liệu hoặc `Comparator`, thay vì giả định equality thông thường đã đổi theo.

## 4. Thiết kế đúng: cùng định nghĩa về “trùng” trong equals và compareTo

Ví dụ dưới đây mô hình hóa một mã sản phẩm `sku` duy nhất. Giá hiển thị chỉ là thuộc tính mô tả, **không quyết định danh tính**. Vì thế, cả `equals` và `compareTo` đều dựa trên `sku`.

Tạo tệp `ConsistentComparisonDemo.java`:

```java
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.TreeMap;
import java.util.TreeSet;

public class ConsistentComparisonDemo {
    static final class Product implements Comparable<Product> {
        private final String sku;
        private final int displayPrice;

        Product(String sku, int displayPrice) {
            this.sku = Objects.requireNonNull(sku);
            this.displayPrice = displayPrice;
        }

        @Override
        public int compareTo(Product other) {
            return sku.compareTo(other.sku);
        }

        @Override
        public boolean equals(Object obj) {
            return obj instanceof Product other
                    && sku.equals(other.sku);
        }

        @Override
        public int hashCode() {
            return sku.hashCode();
        }
    }

    public static void main(String[] args) {
        Product a = new Product("A-01", 100);
        Product sameSku = new Product("A-01", 200);
        Product b = new Product("B-01", 100);

        System.out.println(a == sameSku);
        System.out.println(a.equals(sameSku));
        System.out.println(a.compareTo(sameSku) == 0);
        System.out.println(a.equals(b));
        System.out.println(a.compareTo(b) < 0);

        Set<Product> hashSet = new HashSet<>();
        hashSet.add(a);
        hashSet.add(sameSku);
        hashSet.add(b);
        System.out.println(hashSet.size());

        Set<Product> treeSet = new TreeSet<>();
        treeSet.add(a);
        treeSet.add(sameSku);
        treeSet.add(b);
        System.out.println(treeSet.size());

        Map<Product, String> hashMap = new HashMap<>();
        hashMap.put(a, "first");
        hashMap.put(sameSku, "updated");
        System.out.println(hashMap.size());
        System.out.println(hashMap.get(a));

        Map<Product, String> treeMap = new TreeMap<>();
        treeMap.put(a, "first");
        treeMap.put(sameSku, "updated");
        System.out.println(treeMap.size());
        System.out.println(treeMap.get(a));
    }
}
```

Chạy:

```bash
javac ConsistentComparisonDemo.java
java ConsistentComparisonDemo
```

Stdout:

```text
false
true
true
false
true
2
2
1
updated
1
updated
```

Giải thích:

- `a` và `sameSku` khác tham chiếu (`== false`) nhưng có cùng `sku`; vì vậy `equals == true` và `compareTo == 0`.
- `a` và `b` khác mã; `equals == false`, còn `compareTo` cho đúng thứ tự từ điển của mã (`"A-01"` trước `"B-01"`).
- Cả `HashSet` lẫn `TreeSet` có đúng **2 sản phẩm logic**.
- Cả `HashMap` lẫn `TreeMap` đều chỉ có **1 khóa logic** sau khi cập nhật mã `A-01`; `get(a)` trả `"updated"`.

Ở đây `displayPrice` không tham gia equality và thứ tự tự nhiên, nên hai sản phẩm cùng SKU nhưng giá hiển thị khác vẫn biểu thị cùng đối tượng nghiệp vụ. **Đây là quyết định có chủ ý của ví dụ**, không phải quy tắc rằng mọi kiểu `Product` đều nên bỏ qua giá.

`Product` là `final`, `sku` là `final` và `String` bất biến; điều này giúp duy trì tính nhất quán khi khóa/phần tử đang nằm trong collection. Với kiểu có kế thừa hoặc thuộc tính mutable, cần kiểm tra thêm hợp đồng bình đẳng của toàn hierarchy và nguy cơ thay đổi khóa.

## 5. Sửa ví dụ Event bằng tiêu chí phá hòa

Với record `Event(String code, int priority)`, `equals` được tạo dựa vào **cả hai thành phần**. Có thể làm natural ordering nhất quán bằng cách so mức ưu tiên trước rồi dùng mã để phân biệt những sự kiện có cùng ưu tiên:

```java
@Override
public int compareTo(Event other) {
    int byPriority = Integer.compare(priority, other.priority);
    if (byPriority != 0) {
        return byPriority;
    }
    return code.compareTo(other.code);
}
```

Đây là **đoạn mã đặt bên trong record `Event` ở ví dụ trước**, giả sử `code` không phải `null`. Với các chuỗi hợp lệ, phép so sánh chỉ trả 0 khi **`priority` bằng nhau và `code` bằng nhau**, phù hợp với `equals` được sinh tự động.

Nếu thứ tự chỉ là nhu cầu tạm thời của một màn hình hay báo cáo, không cần thay đổi natural ordering của kiểu. Thay vào đó, dùng `Comparator` tại nơi tạo collection. Cần nhớ comparator đó sẽ quyết định ý nghĩa trùng khóa/phần tử của `TreeSet`/`TreeMap` sử dụng nó.

Ví dụ comparator so cả hai tiêu chí:

```java
Comparator<Event> byPriorityThenCode =
        Comparator.comparingInt(Event::priority)
                .thenComparing(Event::code);
```

Đoạn này cũng là **mã minh họa**, cần `import java.util.Comparator;` và record `Event` có accessor `priority()`, `code()`. Nếu `code` có thể là `null`, phải quy định cách xử lý `null` (ví dụ `Comparator.nullsFirst`).

## 6. Ba hợp đồng riêng phải cùng đúng

Một lớp định nghĩa cả equality và natural ordering nên đáp ứng **ba lớp cam kết**:

### Hợp đồng equals(Object)

`equals` phải phản xạ, đối xứng, bắc cầu, nhất quán khi dữ liệu liên quan không đổi, và `x.equals(null) == false` với `x` khác `null`.

### Hợp đồng hashCode()

Nếu `x.equals(y)` là `true`, thì `x.hashCode() == y.hashCode()` bắt buộc là `true`. Khóa trong `HashMap` hoặc phần tử trong `HashSet` nên có dữ liệu tham gia bình đẳng **ổn định trong thời gian được lưu**.

`compareTo` **không thay thế** `hashCode`. Hai object có `compareTo == 0` nhưng `equals == false` không có nghĩa chúng bắt buộc cùng mã băm. Quy tắc hash xuất phát từ `equals`.

### Hợp đồng compareTo(T)

Phép so sánh tự nhiên phải có thứ tự nhất quán: kết quả theo chiều đối ngược nhau phải có dấu ngược, quan hệ lớn hơn phải bắc cầu, và khi `x.compareTo(y) == 0` thì `x` với `y` phải được so như nhau khi đứng trước một đối tượng thứ ba thích hợp. Nói cách khác, comparator không được tạo ra thứ tự mâu thuẫn.

**Nhất quán giữa compareTo và equals là khuyến nghị bổ sung**, không thay thế các điều kiện nội tại của hai phương thức. Một lớp có thể có `compareTo` bắc cầu nhưng vẫn không nhất quán với `equals`, như ví dụ `Event`.

## 7. Ngoại lệ có chủ đích: BigDecimal

`BigDecimal` là ví dụ Java chuẩn được tài liệu ghi rõ: hai số có thể bằng nhau theo giá trị số học nhưng khác **scale**.

```java
BigDecimal x = new BigDecimal("2.0");
BigDecimal y = new BigDecimal("2.00");

System.out.println(x.compareTo(y) == 0); // true
System.out.println(x.equals(y));         // false
```

Đây là đoạn minh họa cần `import java.math.BigDecimal;`. `compareTo` coi hai số bằng nhau về số học; `equals` còn yêu cầu cùng scale. Kết quả là `HashSet<BigDecimal>` có thể giữ `2.0` và `2.00` làm hai phần tử, trong khi `TreeSet<BigDecimal>` với natural ordering chỉ giữ một.

Điều đó **không làm BigDecimal trở thành một kiểu Java sai**: nó cố ý thể hiện hai khái niệm bình đẳng khác nhau. Nhưng người dùng API phải xác định rõ “trùng” nghĩa là cùng giá trị số học hay cùng giá trị và scale, đặc biệt trước khi dùng làm khóa hoặc phần tử set.

Nếu nghiệp vụ muốn gộp tất cả dạng biểu diễn của cùng một số decimal, có thể chuẩn hóa có chủ đích bằng `stripTrailingZeros()` ở cả bước thêm lẫn tra cứu; nhớ rằng phương thức này có thể cho scale âm hoặc dạng ký pháp khoa học. Nếu nghiệp vụ cần scale cố định (ví dụ hai chữ số thập phân), có thể `setScale(2, roundingMode)` theo quy tắc làm tròn rõ ràng. Không áp dụng việc chuẩn hóa tùy tiện khi scale mang ý nghĩa nghiệp vụ.

## 8. Những lỗi cài đặt thường gặp

| Lỗi | Hệ quả | Cách sửa |
| --- | --- | --- |
| `compareTo` chỉ so một trường trong khi `equals` so nhiều trường | Các phần tử khác nhau theo `equals` có thể bị TreeSet gộp | Thêm tiêu chí phá hòa phù hợp hoặc định nghĩa lại equality theo nghiệp vụ |
| `compareTo` so nhiều trường trong khi `equals` chỉ so một trường | TreeSet có thể giữ hai phần tử mà `equals` coi là bằng nhau | Thống nhất định nghĩa trùng nhau |
| Dùng `return a - b;` để so `int` | Tràn số có thể làm đảo thứ tự, phá quy tắc so sánh | Dùng `Integer.compare(a, b)` |
| Mặc định `compareTo` luôn trả `-1`, `0`, `1` | Kiểm tra sai điều kiện, ví dụ `compareTo(x) == 1` | Chỉ kiểm tra âm / 0 / dương |
| Ghi đè `equals` nhưng quên `hashCode` | HashSet/HashMap không nhận diện đúng đối tượng bằng nhau | Ghi đè cả hai bằng cùng những thành phần |
| Đưa khóa mutable vào collection rồi đổi trường so sánh | Tra cứu trong HashMap hoặc thứ tự của TreeSet/TreeMap có thể hỏng | Ưu tiên kiểu bất biến; xóa trước, cập nhật rồi thêm lại khi cần |
| Gọi `compareTo(null)` và trông chờ kết quả so với `null` | `Comparable` thông thường không coi `null` là giá trị so sánh hợp lệ | Xử lý `null` riêng hoặc dùng comparator có chính sách null |
| Dùng `Comparator` theo cột hiển thị rồi tưởng TreeSet vẫn phân biệt phần tử theo `equals` | TreeSet gộp khi comparator trả 0 | Dùng tiêu chí phá hòa hoặc một cấu trúc cho phép phần tử trùng khóa sắp xếp |

Một nguyên tắc thực tế: **natural ordering nên đại diện cho thứ tự ổn định và có ý nghĩa lâu dài của kiểu**, còn những kiểu sắp xếp theo yêu cầu màn hình (theo giá, ngày, mức ưu tiên) nên được biểu diễn bằng comparator riêng. Tuy nhiên, ngay cả comparator riêng cũng phải được xem xét nếu dùng nó làm cơ chế nhận diện khóa trong sorted set/map.

## 9. Checklist thiết kế và kiểm thử

1. **Viết trước định nghĩa bình đẳng:** hai object nào thực sự là một giá trị logic? Chọn trường tham gia `equals` và `hashCode`.
2. **Chọn thứ tự tự nhiên:** tiêu chí nào tạo được thứ tự đầy đủ, bắc cầu và ổn định? Phải phá hòa đủ để `compareTo == 0` biểu thị đúng một giá trị logic nếu muốn nhất quán với `equals`.
3. **Dùng helper so sánh đúng:** `Integer.compare`, `Long.compare`, `String.compareTo`, `Comparator.comparing(...).thenComparing(...)` thay vì phép trừ dễ tràn số.
4. **Kiểm thử cả hai chiều:** với các object khác nhau `a`, `b`, xác minh `(a.compareTo(b) == 0) == a.equals(b)` và `b.compareTo(a)` có dấu ngược khi cần.
5. **Kiểm thử ba phần tử:** nếu `a < b` và `b < c` thì `a < c`; các giá trị so sánh 0 không làm thay đổi kết quả khi so với phần tử thứ ba.
6. **Kiểm thử Set/Map thực tế:** đưa các đối tượng bằng nhau và khác nhau vào `HashSet`/ `TreeSet`, dùng làm khóa `HashMap`/`TreeMap`, so kích thước và kết quả `contains/get`.
7. **Kiểm tra null, kế thừa, mutable state:** xác định rõ tiền điều kiện so sánh và tránh thay đổi trường quyết định thứ tự khi object nằm trong sorted collection.
8. **Nếu cố ý không nhất quán, ghi tài liệu rõ:** giải thích tiêu chí `compareTo`, tiêu chí `equals`, và ảnh hưởng đến sorted set/map; người dùng phải chọn collection phù hợp.

**Tự kiểm tra:**

- Nếu `a.compareTo(b) == 0` nhưng `a.equals(b) == false`, natural ordering có nhất quán với equals không? **Không.**
- Nếu một `TreeSet` chỉ lưu một phần tử trong khi `HashSet` lưu hai phần tử cùng cặp object, nguyên nhân thường là gì? **Hai tiêu chí “trùng” khác nhau giữa so thứ tự và equality.**
- Nhất quán giữa `compareTo` và `equals` có bắt buộc với mọi lớp `Comparable` không? **Không, nhưng được khuyến nghị mạnh; khi không nhất quán cần tài liệu hóa.**
- Khi dùng `Comparator` để sort theo điểm số, nếu nhiều người cùng điểm nhưng phải giữ tất cả, cần làm gì? **Thêm một tiêu chí phá hòa hoặc dùng cấu trúc dữ liệu thích hợp, thay vì dùng TreeSet chỉ so điểm.**

**Ghi nhớ:** Nên định nghĩa `compareTo(a, b) == 0` đúng khi `a.equals(b)` là `true`, để mọi collection hiểu thống nhất ý nghĩa “cùng phần tử/khóa”. Trường hợp cố ý khác như `BigDecimal` là hợp lệ, nhưng phải hiểu và tài liệu hóa hành vi khi dùng cấu trúc dữ liệu có thứ tự.