# BigDecimal.hashCode và hệ quả trong HashSet hoặc HashMap

## 1. Vấn đề: hai số bằng nhau về giá trị vẫn có thể là hai khóa khác nhau

Với `BigDecimal`, điều quan trọng là phân biệt **so sánh giá trị số** với **so sánh biểu diễn**. Hai đối tượng `new BigDecimal("2.0")` và `new BigDecimal("2.00")` có cùng giá trị toán học. Nhưng chúng khác `scale` nên `equals()` trả `false`; `hashCode()` cũng xét `scale`.

Đây là nguyên nhân làm lập trình viên bất ngờ khi dùng `BigDecimal` làm phần tử của `HashSet` hoặc khóa của `HashMap`: thêm `2.0` rồi kiểm tra sự tồn tại bằng `2.00` có thể cho kết quả **không tìm thấy**, dù `compareTo()` báo hai giá trị bằng nhau.

```java
BigDecimal a = new BigDecimal("2.0");
BigDecimal b = new BigDecimal("2.00");

System.out.println(a.compareTo(b) == 0); // true
System.out.println(a.equals(b));          // false
System.out.println(a.hashCode() == b.hashCode()); // false với cặp giá trị này
```

Đoạn trên minh họa ba cách kiểm tra khác nhau, chưa phải chương trình Java độc lập. Phần ví dụ chạy đầy đủ sẽ cho thấy kết quả trong từng loại collection.

## 2. Vì sao BigDecimal giữ cả giá trị và scale?

Một `BigDecimal` về bản chất biểu diễn:

```text
giá trị = unscaledValue × 10^(-scale)

BigDecimal("2.0")  : unscaledValue = 20,  scale = 1
BigDecimal("2.00") : unscaledValue = 200, scale = 2
```

Hai cách biểu diễn cùng một số, nhưng giữ lại thông tin tỷ lệ thập phân ban đầu. Điều này hữu ích khi `scale` mang ý nghĩa về định dạng, độ chi tiết hoặc hợp đồng dữ liệu.

Ba phương thức có hợp đồng riêng:

| Phương thức | Điều được kiểm tra | `2.0` với `2.00` |
| --- | --- | --- |
| `a.compareTo(b)` | Thứ tự **theo giá trị số**; `0` nghĩa là ngang giá trị | `0` |
| `a.equals(b)` | Giá trị số **và scale** phải bằng nhau | `false` |
| `a.hashCode()` | Mã băm nhất quán với `equals()`, có xét scale | Hai mã băm khác nhau đối với cặp này |

Hợp đồng chung của Java quy định:

- Nếu `a.equals(b)` là `true` thì **bắt buộc** `a.hashCode() == b.hashCode()`.
- Nếu hai `hashCode()` bằng nhau thì **không thể kết luận** `equals()` bằng nhau: va chạm mã băm vẫn có thể xảy ra.
- Nếu `a.equals(b)` là `false`, mã băm **có thể** trùng hoặc khác nhau. Không nên kiểm tra tính bằng nhau bằng cách so sánh mã băm.
- `BigDecimal.compareTo()` có thứ tự **không nhất quán với equals**: `compareTo() == 0` không đảm bảo `equals() == true`.

Vì vậy, muốn hỏi “hai số có cùng giá trị toán học không?”, hãy dùng `compareTo() == 0`. Muốn hỏi “hai biểu diễn BigDecimal có đúng cùng scale và giá trị không?”, dùng `equals()`.

## 3. HashSet dùng equals và hashCode như thế nào?

`HashSet<BigDecimal>` sử dụng quy tắc tương đương của `equals()`, với `hashCode()` để tìm vị trí ứng viên. Nó không dùng `compareTo()` để quyết định phần tử đã tồn tại.

```java
Set<BigDecimal> values = new HashSet<>();
values.add(new BigDecimal("2.0"));
values.add(new BigDecimal("2.00"));

System.out.println(values.size()); // 2
System.out.println(values.contains(new BigDecimal("2.0")));   // true
System.out.println(values.contains(new BigDecimal("2.000"))); // false
```

Ở đây, cả `2.0` và `2.00` đều được thêm: chúng là **hai phần tử khác nhau theo equals**. Giá trị `2.000` là một cách biểu diễn thứ ba, nên `contains` không tìm thấy đối tượng tương đương theo `equals()`.

Luồng kiểm tra có thể hiểu như sau:

```text
add(BigDecimal("2.0"))
  → tính hashCode theo biểu diễn của 2.0
  → lưu phần tử

add(BigDecimal("2.00"))
  → tính hashCode theo biểu diễn của 2.00
  → không có phần tử equals(...) == true
  → thêm phần tử mới

contains(BigDecimal("2.000"))
  → tìm ứng viên bằng hashCode
  → cần ứng viên equals(...) == true
  → không có → false
```

Đây là mô tả ở mức hợp đồng của collection; cách triển khai bucket, bảng băm hoặc xử lý collision có thể thay đổi. **HashSet không sai và BigDecimal không sai**: ứng dụng phải xác định mình muốn duy nhất theo *giá trị* hay theo *biểu diễn*.

## 4. HashMap dùng BigDecimal làm khóa: put và get dễ gây nhầm

`HashMap<BigDecimal, V>` xác định khóa bằng `hashCode()` và `equals()`. Nếu lần ghi và lần đọc tạo `BigDecimal` từ các chuỗi có scale khác nhau, `get` có thể trả `null`.

```java
Map<BigDecimal, String> map = new HashMap<>();
map.put(new BigDecimal("2.0"), "dữ liệu A");
map.put(new BigDecimal("2.00"), "dữ liệu B");

System.out.println(map.size()); // 2
System.out.println(map.get(new BigDecimal("2.0")));   // dữ liệu A
System.out.println(map.get(new BigDecimal("2.000"))); // null
```

Cả hai lần `put` tạo hai entry riêng; lần `get` thứ hai không khớp biểu diễn nào. `null` có thể nghĩa là thiếu khóa **hoặc** có khóa ánh xạ tới giá trị `null`; dùng `containsKey` khi cần phân biệt hai tình huống.

Vấn đề tương tự xuất hiện ở cache, dữ liệu tổng hợp, thuật toán đếm tần suất, gom nhóm theo giá, hoặc so khớp ID dạng số thập phân:

- Dữ liệu nhập vào là `"2.0"` nhưng truy vấn là `"2.00"`.
- Dữ liệu lấy từ JSON, database hay phép tính trung gian có scale khác nhau.
- Nhóm `Map<BigDecimal, List<Item>>` bị tách thành nhiều nhóm tuy các khóa ngang giá trị.

Đừng đổi sang `double` hay lấy `intValue()` chỉ để tránh trường hợp này: có thể mất độ chính xác hoặc phần thập phân và tạo ra một quy tắc khóa sai.

## 5. Chương trình Java 17+ chứng minh HashSet, HashMap và TreeSet, TreeMap

Lưu tệp `BigDecimalCollectionsDemo.java`:

```java
import java.math.BigDecimal;
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;
import java.util.TreeMap;
import java.util.TreeSet;

public class BigDecimalCollectionsDemo {
    public static void main(String[] args) {
        BigDecimal a = new BigDecimal("2.0");
        BigDecimal b = new BigDecimal("2.00");
        BigDecimal lookup = new BigDecimal("2.000");

        System.out.println("compareTo == 0: " + (a.compareTo(b) == 0));
        System.out.println("equals: " + a.equals(b));
        System.out.println("hashCode equal: "
                + (a.hashCode() == b.hashCode()));

        Set<BigDecimal> hashSet = new HashSet<>();
        hashSet.add(a);
        hashSet.add(b);
        System.out.println("HashSet size: " + hashSet.size());
        System.out.println("HashSet contains 2.000: "
                + hashSet.contains(lookup));

        Map<BigDecimal, String> hashMap = new HashMap<>();
        hashMap.put(a, "first");
        hashMap.put(b, "second");
        System.out.println("HashMap size: " + hashMap.size());
        System.out.println("HashMap get 2.0: " + hashMap.get(a));
        System.out.println("HashMap get 2.000: " + hashMap.get(lookup));

        Set<BigDecimal> treeSet = new TreeSet<>();
        treeSet.add(a);
        treeSet.add(b);
        System.out.println("TreeSet size: " + treeSet.size());
        System.out.println("TreeSet contains 2.000: "
                + treeSet.contains(lookup));

        Map<BigDecimal, String> treeMap = new TreeMap<>();
        treeMap.put(a, "first");
        treeMap.put(b, "second");
        System.out.println("TreeMap size: " + treeMap.size());
        System.out.println("TreeMap get 2.000: " + treeMap.get(lookup));
    }
}
```

Biên dịch và chạy:

```bash
javac BigDecimalCollectionsDemo.java
java BigDecimalCollectionsDemo
```

Stdout:

```text
compareTo == 0: true
equals: false
hashCode equal: false
HashSet size: 2
HashSet contains 2.000: false
HashMap size: 2
HashMap get 2.0: first
HashMap get 2.000: null
TreeSet size: 1
TreeSet contains 2.000: true
TreeMap size: 1
TreeMap get 2.000: second
```

Chương trình không in trực tiếp toàn bộ collection vì thứ tự duyệt của `HashSet` và `HashMap` không phải thứ tự được đảm bảo.

Điểm đáng chú ý: `TreeSet` và `TreeMap` mặc định dùng thứ tự tự nhiên qua `compareTo()`, nên xem `2.0`, `2.00`, `2.000` là cùng một vị trí theo thứ tự. `TreeMap.put(b, "second")` cập nhật giá trị của entry đã có vì so sánh khóa trả `0`; `get(lookup)` tìm được `"second"`.

## 6. Vì sao TreeSet và TreeMap có kết quả khác?

Các collection hash và sorted dùng quy tắc xác định khóa khác nhau:

| Collection | Quy tắc mặc định để coi là cùng phần tử/khóa | `2.0` và `2.00` |
| --- | --- | --- |
| `HashSet<BigDecimal>` | `hashCode` + `equals` | Hai phần tử |
| `HashMap<BigDecimal, V>` | `hashCode` + `equals` | Hai khóa |
| `TreeSet<BigDecimal>` | `compareTo` trả `0` | Một phần tử |
| `TreeMap<BigDecimal, V>` | `compareTo` trả `0` | Một khóa; put sau cập nhật giá trị |
| `TreeSet/TreeMap` có `Comparator` riêng | Comparator trả `0` | Phụ thuộc comparator |

`TreeSet` và `TreeMap` có hành vi sắp xếp nhất quán với `compareTo()`, nhưng vì thứ tự tự nhiên của `BigDecimal` **không nhất quán với equals**, các sorted collection sử dụng nó sẽ không hoàn toàn tuân theo hợp đồng tổng quát dựa trên `equals` của `Set`/`Map`. Hành vi của sorted collection vẫn được xác định theo comparator.

Hệ quả thực tế: chuyển code từ `HashMap` sang `TreeMap` có thể thay đổi cả **số lượng khóa** và **quy tắc ghi đè**, không chỉ thay đổi thứ tự duyệt. Hãy chọn collection dựa trên yêu cầu nghiệp vụ, rồi đảm bảo mọi phần của ứng dụng sử dụng cùng một định nghĩa về tính duy nhất.

Không có `Comparator` nào được truyền vào `HashMap` hoặc `HashSet` để đổi hành vi `equals` của khóa. Nếu dùng hash collection mà muốn các scale khác nhau vẫn là một khóa, cần chuẩn hóa khóa hoặc thiết kế kiểu khóa riêng.

## 7. Ba chính sách khóa ứng với ba yêu cầu dữ liệu

**Giữ scale:** dùng `BigDecimal` nguyên dạng làm khóa hash nếu `2.0` và `2.00` cần phân biệt. Điều này sử dụng đúng hợp đồng `equals/hashCode` hiện có.

**Cùng số học thì cùng khóa:** chuẩn hóa giá trị trước khi `put`, `get`, `containsKey` và `remove`, kể cả khi tải lại từ storage:

```java
static BigDecimal numericKey(BigDecimal input) {
    return java.util.Objects.requireNonNull(input).stripTrailingZeros();
}
```

```java
Map<BigDecimal, String> map = new HashMap<>();
map.put(numericKey(new BigDecimal("2.00")), "two");
String result = map.get(numericKey(new BigDecimal("2.000"))); // "two"
```

Đây là các đoạn đặt trong một class/method với import `BigDecimal`, `Map`, `HashMap`. `stripTrailingZeros` giữ nguyên số nhưng có thể làm scale âm (`1000.0 → 1E+3`) và đưa mọi zero về scale 0. Việc nhiều khóa khác representation trở thành một khóa chuẩn buộc ứng dụng có chính sách xử lý dữ liệu trùng (giữ, từ chối, ghi đè, gộp). Lưu văn bản/scale gốc ở trường riêng nếu cần audit.

**Scale cố định:** nếu miền dữ liệu thật sự yêu cầu hai chữ số và không được mất dữ liệu, dùng `setScale(2, RoundingMode.UNNECESSARY)`. Giá trị không thể biểu diễn chính xác gây `ArithmeticException`. Nếu cho phép rounding, cần mode và quy tắc xử lý khóa bị gộp rõ ràng; hai giá trị số học khác nhau có thể thành một giá trị sau làm tròn. Bài **Chính sách chuẩn hóa scale trước khi lưu hoặc so sánh** xử lý riêng DB, JSON, precision, scale âm và các ranh giới đó.

## 8. Cố định chính sách trong kiểu khóa bất biến

```java
public record NumericDecimalKey(BigDecimal value) {
    public NumericDecimalKey {
        value = java.util.Objects.requireNonNull(value)
                .stripTrailingZeros();
    }
}
```

Đây là `record` độc lập trong Java 17, cần import `java.math.BigDecimal`. `equals` và `hashCode` sinh tự động từ thành phần **đã chuẩn hóa**. Khi cần giữ nguyên chuỗi hoặc scale đầu vào, lưu chúng riêng; canonical key chỉ phục vụ danh tính theo giá trị số.
## 9. Các góc cạnh và lỗi thường gặp

**1. So sánh bằng compareTo nhưng tra cứu bằng HashMap.** Nếu code kiểm tra trước bằng `compareTo() == 0`, sau đó truy vấn bằng `map.get(otherBigDecimal)`, hai bước đang dùng hai định nghĩa bằng nhau khác nhau. Kiểm tra số học không đảm bảo lookup bằng hash thành công.

**2. Chỉ so hashCode để quyết định trùng.** Hash collision có thể xảy ra. Luôn theo hợp đồng `equals()`, hoặc chuẩn hóa rồi để collection thực hiện việc so sánh.

**3. Dùng `stripTrailingZeros()` trên một khóa nhưng không trên khóa truy vấn.** Dễ dẫn đến cache miss hoặc bản ghi không tìm thấy. Chuẩn hóa nhất quán ở mọi thao tác, bao gồm ghi, đọc, xóa và khôi phục trạng thái.

**4. Nhầm scale âm sau chuẩn hóa là lỗi.** `1000.0.stripTrailingZeros()` tạo `1E+3`, scale `-3`. Số vẫn chính xác. Nếu nơi nhận cấm dạng này, phải xử lý định dạng/scale ở ranh giới xuất dữ liệu theo hợp đồng riêng.

**5. Gộp dữ liệu vô tình sau khi chuẩn hóa.** Ví dụ ban đầu `2.0` và `2.00` là hai khóa khác nhau. Sau chuẩn hóa, chúng trùng nhau. Khi dùng `Collectors.toMap`, trùng khóa mà không có hàm gộp có thể làm collector ném `IllegalStateException`. Trong vòng lặp với `HashMap.put`, giá trị sau sẽ ghi đè giá trị trước. Cần chọn chính sách rõ ràng.

**6. Dùng phép làm tròn để tạo khóa dù định danh yêu cầu đúng giá trị.** Rounding có thể đồng nhất hai số vốn khác nhau về số học. `stripTrailingZeros()` chỉ bỏ số 0 dư nên giữ nguyên giá trị; `setScale(..., HALF_UP)` có thể thay đổi giá trị.

**7. Tạo BigDecimal từ literal double.** `new BigDecimal(0.1)` thể hiện chính xác giá trị nhị phân gần đúng của `double`, không phải thập phân đúng bằng `0.1`. Khi yêu cầu decimal nhập chính xác, dùng `new BigDecimal("0.1")`; nếu nguồn đã là `double`, `BigDecimal.valueOf(double)` thường phù hợp hơn constructor nhận `double`, nhưng không phục hồi sai số đã phát sinh trước đó.

**8. Cho rằng BigDecimal tự thay đổi sau khi làm khóa.** `BigDecimal` là kiểu **immutable**, vì thế bản thân đối tượng khóa không bị chỉnh scale hay giá trị tại chỗ. Tuy nhiên, một đối tượng wrapper chứa trường có thể thay đổi và tự triển khai `equals/hashCode` dựa trên trường đó có thể làm hỏng hành vi hash collection khi trường bị sửa sau `put`. Ưu tiên khóa bất biến.

**9. Lẫn dữ liệu lưu trữ với biểu diễn hiển thị.** Số `2.00` có thể cần hiện đúng hai chữ số cho người dùng, nhưng chính sách cache chỉ quan tâm giá trị `2`. Giữ các quy tắc này ở những bước riêng: nhận dạng khóa, kiểm tra hợp lệ và định dạng.

## 10. Chọn hướng nào trong thực tế?

| Yêu cầu | Cách xử lý | Cần kiểm tra thêm |
| --- | --- | --- |
| Scale là một phần của danh tính | Dùng `BigDecimal` trực tiếp trong `HashMap/HashSet` | Nhà cung cấp dữ liệu có giữ scale ổn định không? |
| Mọi biểu diễn ngang giá trị là một khóa | Dùng `stripTrailingZeros()` nhất quán hoặc kiểu khóa chuẩn hóa | Xử lý entry trùng sau chuẩn hóa và serialization |
| Khóa phải có số chữ số thập phân cố định | `setScale(fixedScale, UNNECESSARY)` | Giá trị nào phải bị từ chối khi không exact? |
| Cần thứ tự tăng/giảm theo giá trị số | `TreeMap/TreeSet` mặc định dùng `compareTo()` | Có chấp nhận việc các scale khác nhau bị xem là một khóa? |
| Cần lưu số đơn vị nhỏ nhất bằng số nguyên | Đổi chính xác sang `BigInteger`/`long` nếu phạm vi cho phép | Đơn vị, overflow và phép đổi exact |

Một `TreeMap` có thể đáp ứng tự nhiên nhu cầu sắp xếp và gom các scale khác nhau, nhưng không thể xem đây là một phép thay thế trong suốt cho `HashMap`: hành vi nhận dạng khóa cũng thay đổi.

## 11. Câu hỏi tự kiểm tra

1. `new BigDecimal("0.0").equals(BigDecimal.ZERO)` trả gì? **False**: scale 1 khác scale 0, dù `compareTo(BigDecimal.ZERO) == 0`.
2. Thêm `new BigDecimal("3.0")` và `new BigDecimal("3.00")` vào `HashSet` có bao nhiêu phần tử? **Hai**: `equals()` phân biệt scale.
3. Thêm cùng hai giá trị vào `TreeSet` mặc định có bao nhiêu phần tử? **Một**: `compareTo()` coi hai số bằng nhau.
4. Vì sao hai đối tượng khác nhau có cùng `hashCode` chưa chắc là cùng khóa `HashMap`? **Vì** collection còn cần `equals()` để phân biệt các khóa có mã băm trùng.
5. Nên dùng `setScale(2, HALF_UP)` hay `stripTrailingZeros()` để tạo khóa theo đúng giá trị số? **`stripTrailingZeros()`**: nó không làm thay đổi giá trị số; `HALF_UP` có thể gộp các giá trị khác nhau.
6. Phải chuẩn hóa ở những bước nào để lookup nhất quán? **Mọi ranh giới tạo khóa**, đặc biệt `put`, `get`, `containsKey`, `remove`, và khi đọc lại từ dữ liệu đã lưu.

## 12. Kết luận

`BigDecimal.compareTo()` so sánh **giá trị số**, còn `BigDecimal.equals()` và `hashCode()` xét cả **giá trị số lẫn scale**. Vì vậy, `HashSet` và `HashMap` có thể giữ `2.0` và `2.00` thành hai phần tử/khóa riêng, trong khi `TreeSet` và `TreeMap` mặc định xem chúng là một theo `compareTo()`.

Điều quyết định là **định nghĩa tính duy nhất của ứng dụng**. Nếu biểu diễn quan trọng, dùng BigDecimal trực tiếp; nếu chỉ giá trị số quan trọng, chuẩn hóa chính xác và nhất quán; nếu domain cần scale cố định, kiểm tra và từ chối dữ liệu không đáp ứng trước khi tạo khóa. Luôn có chính sách xử lý trùng khi chuyển đổi từ nhiều biểu diễn sang một khóa chung.
