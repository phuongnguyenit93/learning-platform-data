# Hệ quả khi dùng BigDecimal trong TreeSet hoặc TreeMap

## 1. Vấn đề: cùng giá trị số học nhưng không cùng cách biểu diễn

Trong Java, `BigDecimal` có hai cách xem xét sự bằng nhau:

- `compareTo(BigDecimal)` so sánh **giá trị số học**. Nếu hai số bằng nhau về giá trị, `compareTo()` trả `0`, dù khác `scale`.
- `equals(Object)` yêu cầu **cùng giá trị số học và cùng scale**. Vì thế, `new BigDecimal("2.0").equals(new BigDecimal("2.00"))` là `false`.

Ví dụ ngắn:

```java
BigDecimal a = new BigDecimal("2.0");  // unscaled=20, scale=1
BigDecimal b = new BigDecimal("2.00"); // unscaled=200, scale=2

System.out.println(a.compareTo(b) == 0); // true
System.out.println(a.equals(b));         // false
```

Trong tài liệu Java, hai đối tượng như `a` và `b` thuộc cùng một *cohort*: bằng nhau về giá trị số học, nhưng có biểu diễn thập phân khác nhau. Thứ tự tự nhiên của `BigDecimal` (*natural ordering*) được xác định qua `compareTo()` và **không nhất quán với `equals()`** (*inconsistent with equals*).

Sự khác biệt này tác động trực tiếp khi dùng `BigDecimal` làm **phần tử của `TreeSet`** hoặc **khóa của `TreeMap`**. Hai cấu trúc này dựa vào **thứ tự so sánh**, chứ không dựa vào `equals()` để xác định hai phần tử/khóa được xem như cùng một.

## 2. TreeSet: một phần tử có thể bị coi là trùng dù equals là false

`TreeSet` sắp xếp phần tử theo thứ tự tự nhiên, hoặc theo `Comparator` truyền khi khởi tạo. Nếu không truyền comparator, với `BigDecimal` nó dùng `compareTo()`.

Các thao tác như `add()`, `contains()`, `remove()` dựa vào kết quả so sánh. Khi `compareTo() == 0`, `TreeSet` coi hai đối tượng tương đương để quyết định một phần tử đã tồn tại, bất kể `equals()` có thể trả `false`.

```java
TreeSet<BigDecimal> values = new TreeSet<>();
boolean first = values.add(new BigDecimal("2.0"));  // true
boolean second = values.add(new BigDecimal("2.00")); // false

System.out.println(values.size());                   // 1
System.out.println(values.contains(new BigDecimal("2.000"))); // true
```

Điều gì diễn ra?

1. Phần tử `2.0` được thêm vào vì tập ban đầu rỗng.
2. `2.00` so sánh bằng `2.0` theo `compareTo() == 0`, nên lần `add` thứ hai trả `false` và không tăng kích thước.
3. Lời gọi `contains(new BigDecimal("2.000"))` trả `true`, dù `"2.000"` không `equals()` với phần tử `"2.0"` đang lưu.
4. Với `remove(new BigDecimal("2.000"))`, `TreeSet` có thể xóa phần tử `"2.0"` vì chúng bằng nhau theo cách so sánh của tập.

**Hệ quả thực tế:** nếu người lập trình mong `TreeSet<BigDecimal>` lưu cả `2.0` lẫn `2.00` như hai biểu diễn riêng, việc mất phần tử là hành vi *được định nghĩa bởi comparator*, không phải lỗi ngẫu nhiên của Java.

Theo hợp đồng chung của `Set`, tính duy nhất được mô tả bằng `equals()`. Vì `TreeSet` với thứ tự tự nhiên `BigDecimal` lại xác định trùng nhau bằng `compareTo()`, thứ tự này **không nhất quán với hợp đồng `Set`**; tài liệu Java cảnh báo rõ trường hợp đó. Các thao tác của `TreeSet` vẫn hoạt động theo quy tắc sắp xếp đã chọn.

## 3. TreeMap: hai khóa khác equals có thể trỏ tới cùng một entry

Với `TreeMap<BigDecimal, V>` dùng thứ tự tự nhiên, nếu hai khóa so sánh bằng nhau (`compareTo() == 0`), `TreeMap` xem chúng là **một khóa logic**.

```java
TreeMap<BigDecimal, String> prices = new TreeMap<>();

prices.put(new BigDecimal("2.0"), "first");
prices.put(new BigDecimal("2.00"), "second");

System.out.println(prices.size());                      // 1
System.out.println(prices.get(new BigDecimal("2.000"))); // second
```

Ở lần `put` đầu, map tạo một entry. Lần `put` thứ hai tìm thấy khóa tương đương theo comparator, nên **giá trị của entry cũ bị thay bằng `"second"`**; nó không tạo entry mới. Khóa được lưu trong ví dụ vẫn là đối tượng `2.0` đã chèn đầu tiên. Có thể quan sát qua `firstKey()` hoặc duyệt `keySet()`; việc thay giá trị không đồng nghĩa thay đối tượng khóa đang lưu.

Các thao tác tìm kiếm như `get()`, `containsKey()`, `remove()` cũng dựa trên thứ tự so sánh. Một khóa mới với giá trị `2.000` có thể truy cập hoặc xóa entry đã tạo bằng `2.0`.

Điều này đặc biệt đáng lưu ý nếu khóa `BigDecimal` đại diện cho giá trị có **scale mang ý nghĩa nghiệp vụ** (ví dụ độ chính xác đo lường hoặc định dạng số thập phân cần phân biệt). Trong trường hợp đó, hai khóa có thể bị gộp bất ngờ, gây ghi đè dữ liệu.

## 4. Chương trình Java 17 chạy được: đối chiếu TreeSet, TreeMap, HashSet, HashMap

Tạo tệp **`BigDecimalSortedCollectionsDemo.java`**:

```java
import java.math.BigDecimal;
import java.util.Comparator;
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;
import java.util.TreeMap;
import java.util.TreeSet;

public class BigDecimalSortedCollectionsDemo {
    public static void main(String[] args) {
        BigDecimal a = new BigDecimal("2.0");
        BigDecimal b = new BigDecimal("2.00");
        BigDecimal probe = new BigDecimal("2.000");

        System.out.println("equals=" + a.equals(b));
        System.out.println("compareToZero=" + (a.compareTo(b) == 0));
        System.out.println("scales=" + a.scale() + "," + b.scale());

        Set<BigDecimal> treeSet = new TreeSet<>();
        System.out.println("treeAddA=" + treeSet.add(a));
        System.out.println("treeAddB=" + treeSet.add(b));
        System.out.println("treeSize=" + treeSet.size());
        System.out.println("treeContainsProbe=" + treeSet.contains(probe));
        System.out.println("treeStored=" + treeSet.iterator().next());

        Map<BigDecimal, String> treeMap = new TreeMap<>();
        System.out.println("mapPutA=" + treeMap.put(a, "first"));
        System.out.println("mapPutB=" + treeMap.put(b, "second"));
        System.out.println("mapSize=" + treeMap.size());
        System.out.println("mapGetProbe=" + treeMap.get(probe));
        System.out.println("mapStoredKey=" + treeMap.keySet().iterator().next());

        Set<BigDecimal> hashSet = new HashSet<>();
        hashSet.add(a);
        hashSet.add(b);
        Map<BigDecimal, String> hashMap = new HashMap<>();
        hashMap.put(a, "first");
        hashMap.put(b, "second");
        System.out.println("hashSetSize=" + hashSet.size());
        System.out.println("hashMapSize=" + hashMap.size());
        System.out.println("hashMapGetProbe=" + hashMap.get(probe));

        Comparator<BigDecimal> byValueThenScale = (left, right) -> {
            int result = left.compareTo(right);
            return result != 0 ? result
                    : Integer.compare(left.scale(), right.scale());
        };
        Set<BigDecimal> strictTreeSet = new TreeSet<>(byValueThenScale);
        strictTreeSet.add(a);
        strictTreeSet.add(b);
        System.out.println("strictTreeSize=" + strictTreeSet.size());
        System.out.println("strictContainsProbe=" + strictTreeSet.contains(probe));

        Set<BigDecimal> normalizedSet = new TreeSet<>();
        normalizedSet.add(a.stripTrailingZeros());
        normalizedSet.add(b.stripTrailingZeros());
        System.out.println("normalizedSize=" + normalizedSet.size());
        System.out.println("normalizedValue=" + normalizedSet.iterator().next());
    }
}
```

Biên dịch và chạy:

```bash
javac BigDecimalSortedCollectionsDemo.java
java BigDecimalSortedCollectionsDemo
```

Kết quả (đã chạy thực tế với biên dịch `javac --release 17`):

```text
equals=false
compareToZero=true
scales=1,2
treeAddA=true
treeAddB=false
treeSize=1
treeContainsProbe=true
treeStored=2.0
mapPutA=null
mapPutB=first
mapSize=1
mapGetProbe=second
mapStoredKey=2.0
hashSetSize=2
hashMapSize=2
hashMapGetProbe=null
strictTreeSize=2
strictContainsProbe=false
normalizedSize=1
normalizedValue=2
```

Các điểm cần đọc kỹ trong output:

- `treeAddB=false`: `TreeSet` bỏ qua phần tử thứ hai vì so sánh số học bằng nhau.
- `treeContainsProbe=true`: phần tử truy vấn `2.000` được coi là có trong tập dù khác scale với phần tử lưu `2.0`.
- `mapPutB=first`: `Map.put` trả giá trị cũ, chứng tỏ lần chèn thứ hai cập nhật một entry có sẵn; `mapGetProbe=second` cho biết giá trị mới.
- `mapStoredKey=2.0`: entry hiện có vẫn mang khóa của lần chèn đầu tiên trong tình huống này.
- `hashSetSize=2` và `hashMapSize=2`: cấu trúc băm coi `a` và `b` khác nhau vì dựa vào `equals()` và `hashCode()`.
- `strictTreeSize=2`: một comparator được thiết kế để phân biệt scale đã giữ cả hai đối tượng.
- `normalizedSize=1`: chủ động chuẩn hóa dữ liệu khiến hai biểu diễn cùng giá trị trở thành một dạng để lưu.

## 5. So sánh ý nghĩa “trùng nhau” trong các collection

| Cấu trúc | Quy tắc xác định trùng phần tử/khóa | `2.0` với `2.00` theo mặc định |
| --- | --- | --- |
| `HashSet<BigDecimal>` | `equals()` và `hashCode()` | Hai phần tử riêng (size 2) |
| `HashMap<BigDecimal, V>` | `equals()` và `hashCode()` | Hai khóa riêng (size 2) |
| `TreeSet<BigDecimal>` | `compareTo() == 0` theo thứ tự tự nhiên | Một phần tử (size 1) |
| `TreeMap<BigDecimal, V>` | `compareTo() == 0` theo thứ tự tự nhiên | Một khóa (size 1), giá trị sau ghi đè |
| `TreeSet/TreeMap` với `Comparator` tùy chỉnh | `comparator.compare(a, b) == 0` | Tùy comparator |

Với `HashSet`/`HashMap`, `hashCode()` của `BigDecimal` phản ánh giá trị không scale và scale. Vì vậy `2.0` và `2.00` có thể có mã băm khác nhau; điều cốt yếu vẫn là `equals()` trả `false`. Không được suy từ việc hai số có cùng giá trị số học rằng chúng sẽ là cùng khóa trong `HashMap`.

Với `TreeSet`/`TreeMap`, **các phương thức `equals()` của đối tượng khóa/phần tử không phải tiêu chí duy nhất** để xác định tương đương. Cấu trúc sắp xếp dùng kết quả so sánh làm tiêu chí định danh trong thao tác tìm kiếm.

## 6. Cách chọn thiết kế đúng theo yêu cầu dữ liệu

### Trường hợp A — Hai biểu diễn cùng số phải được xem là một giá trị

Ví dụ nghiệp vụ chỉ quan tâm `2`, `2.0` và `2.00` như **cùng một giá trị số học**.

Dùng `TreeSet`/`TreeMap` theo thứ tự tự nhiên **có thể chủ đích phù hợp** nếu bạn chấp nhận rằng khóa/phần tử được định danh theo `compareTo() == 0` và hiểu hạn chế về tính nhất quán với `equals()`. Cần ghi rõ quy tắc này trong API để tránh nhầm với `HashSet`/`HashMap`.

Một lựa chọn khác là **chuẩn hóa khóa trước khi lưu và khi truy vấn**, đặc biệt khi muốn cấu trúc băm và cấu trúc sắp xếp thống nhất về tính duy nhất:

```java
static BigDecimal numericKey(BigDecimal value) {
    return value.stripTrailingZeros();
}

// Ví dụ trong một phương thức:
Set<BigDecimal> keys = new HashSet<>();
keys.add(numericKey(new BigDecimal("2.0")));
keys.add(numericKey(new BigDecimal("2.00")));
// keys.size() == 1

boolean found = keys.contains(numericKey(new BigDecimal("2.000")));
// found == true
```

Phương thức `numericKey` là **đoạn minh họa**, phải đặt trong một lớp Java. Quy tắc chuẩn hóa phải áp dụng **nhất quán ở cả ghi và đọc**. `stripTrailingZeros()` có thể trả số dạng khoa học với scale âm (ví dụ `600.0` thành `6E+2`), và số 0 được chuẩn hóa về `BigDecimal.ZERO`. Nếu scale có ý nghĩa, cách chuẩn hóa này không đáp ứng yêu cầu.

### Trường hợp B — Hai biểu diễn khác scale phải là hai phần tử/khóa riêng

Ví dụ yêu cầu phân biệt `2.0` (scale 1) và `2.00` (scale 2). Với collection không cần sắp xếp, `HashSet`/`HashMap` đã tuân theo `equals()` của `BigDecimal`.

Nếu vẫn cần thứ tự sắp xếp, cung cấp comparator: **so sánh giá trị trước, so sánh scale khi giá trị số học bằng nhau**.

```java
Comparator<BigDecimal> byValueThenScale = (left, right) -> {
    int result = left.compareTo(right);
    return result != 0 ? result
            : Integer.compare(left.scale(), right.scale());
};

TreeSet<BigDecimal> distinctScales = new TreeSet<>(byValueThenScale);
distinctScales.add(new BigDecimal("2.0"));
distinctScales.add(new BigDecimal("2.00"));
// distinctScales.size() == 2

TreeMap<BigDecimal, String> details = new TreeMap<>(byValueThenScale);
details.put(new BigDecimal("2.0"), "scale 1");
details.put(new BigDecimal("2.00"), "scale 2");
// details.size() == 2
```

Vì sao comparator này nhất quán với `equals()` của `BigDecimal`? Nếu hai giá trị có cùng giá trị số học **và cùng scale**, phần unscaled của chúng cũng giống nhau, nên `equals()` trả `true`. Do đó comparator trả 0 đúng trong trường hợp `equals()` trả `true`. Comparator vẫn thỏa tính phản đối xứng, bắc cầu và thứ tự nhất quán.

Tuy nhiên, comparator này sẽ cho phép hai số cùng giá trị nhưng khác scale tồn tại cùng lúc. Nếu ứng dụng cần tính duy nhất **theo giá trị số học**, hãy chọn quy tắc của trường hợp A; đừng áp dụng comparator này chỉ vì muốn “khắc phục” cảnh báo.

### Trường hợp C — Có nhiều thuộc tính tạo nên danh tính nghiệp vụ

Nếu một bản ghi có cả số tiền, mã tiền tệ, mức độ chính xác, thời điểm và mã định danh, thì việc chọn `BigDecimal` làm khóa duy nhất có thể đánh mất ngữ nghĩa. Cần tạo khóa nghiệp vụ rõ ràng, ví dụ một record chứa mã tiền tệ và giá trị tiền đã được quy đổi về đơn vị nhỏ nhất theo một quy tắc được định nghĩa trước:

```java
record MoneyKey(String currencyCode, long minorUnits) {}
```

Đây là ví dụ về **kiểu khóa**; việc quy đổi `BigDecimal` sang `minorUnits` phải kiểm tra scale, làm tròn, phạm vi `long` và quy tắc đơn vị tiền tệ riêng. Khi cần giá trị lớn, có thể dùng `BigInteger` thay `long`. Không quy đổi bằng `double` rồi ép kiểu vì có thể mất chính xác.

## 7. Những hệ quả dễ bị bỏ qua khi triển khai

**Gộp dữ liệu và mất record:** chương trình thống kê đưa `2.0` và `2.00` vào `TreeMap<BigDecimal, Result>` có thể chỉ còn một entry. Nếu mỗi chuỗi đầu vào là một phép đo riêng cần lưu, khóa cần bổ sung danh tính khác hoặc đổi comparator.

**Đọc được bằng khóa chưa từng lưu:** truy vấn `treeMap.get(new BigDecimal("2.000"))` có thể trả dữ liệu của khóa `2.0`. Điều này thuận tiện cho tra cứu theo số học, nhưng nguy hiểm khi người dùng tưởng scale là một phần của định danh.

**Ghi đè ngoài ý muốn:** các lời gọi `put`, `putIfAbsent`, `computeIfAbsent`, `merge` có thể xem các khóa `BigDecimal` khác scale là một khóa. Tùy phương thức, kết quả là giữ giá trị trước, cập nhật hoặc gộp dữ liệu. Kiểm tra logic nghiệp vụ thay vì coi mỗi đối tượng mới là một khóa mới.

**Kết quả khác giữa hai loại collection:** dữ liệu đưa vào `HashSet` có thể có 2 phần tử, chuyển sang `TreeSet` mặc định chỉ còn 1. Việc chuyển đổi kiểu collection có thể thay đổi chính sách trùng lặp, không chỉ khả năng sắp xếp.

**Tác động tới `contains` và `remove`:** với `TreeSet`, một đối tượng tìm kiếm khác scale vẫn có thể tìm được hoặc xóa đối tượng đang lưu. Điều này quan trọng với code dùng kiểm tra quyền, điều kiện tồn tại hay thao tác xóa dựa theo khóa được dựng lại từ chuỗi đầu vào.

**Vấn đề giữ định dạng:** khi `TreeMap.put` cập nhật value cho khóa có `compareTo() == 0`, entry ban đầu vẫn có thể hiển thị scale của khóa chèn trước. Không dựa vào `keySet().iterator().next().toString()` để suy ra cách người dùng nhập dữ liệu mới nhất. Nếu cần lưu nguyên văn số đầu vào, lưu nó thành trường dữ liệu riêng.

## 8. Lỗi thường gặp và cách phòng tránh

1. **Cho rằng `compareTo() == 0` đồng nghĩa `equals() == true`.** Với `BigDecimal` điều này sai khi scale khác. Hãy xác định bạn cần so sánh số học hay so sánh cả biểu diễn.
2. **Tin rằng `TreeSet` gọi `equals()` khi thêm phần tử.** Nó dựa trên thứ tự, nên hai đối tượng `equals=false` vẫn có thể bị coi là trùng.
3. **Dùng `TreeMap` làm bảng lưu bản ghi khác nhau nhưng chỉ lấy giá trị thập phân làm khóa.** Những khóa cùng giá trị số học sẽ gộp entry. Bổ sung mã định danh hoặc comparator phù hợp.
4. **Chuyển `HashMap` sang `TreeMap` để có sắp xếp mà không kiểm tra chính sách trùng lặp.** Kích thước có thể thay đổi. Hãy test bộ dữ liệu có `2.0`, `2.00` và `2.000`.
5. **Dùng comparator dựa trên `toString()` khi muốn so sánh BigDecimal số học.** Thứ tự từ điển của chuỗi không tương đương thứ tự số học và còn phụ thuộc dạng biểu diễn (ví dụ `"10"` và `"2"`). Dùng `compareTo()` và, khi cần, thêm scale làm tiêu chí phụ.
6. **Chuẩn hóa bằng `stripTrailingZeros()` mà không xét hậu quả.** Số 0 và scale âm là trường hợp quan trọng; chuẩn hóa có thể xóa thông tin số chữ số thập phân ban đầu. Quy định cách lưu định dạng nguyên gốc riêng nếu cần.
7. **Tạo `BigDecimal` từ `double` rồi khó hiểu kết quả.** `new BigDecimal(0.1)` phản ánh giá trị nhị phân gần 0.1 của `double`. Với dữ liệu thập phân đầu vào, thường nên khởi tạo từ chuỗi `new BigDecimal("0.1")`, hoặc cân nhắc `BigDecimal.valueOf(0.1)`.
8. **Bỏ qua ràng buộc nhất quán của comparator.** Comparator cho `TreeSet`/`TreeMap` phải bảo đảm thứ tự hợp lệ (chẳng hạn phản đối xứng và bắc cầu); muốn tuân thủ đầy đủ hợp đồng `Set`/`Map`, điều kiện `compare(a,b) == 0` cũng cần tương đương `a.equals(b)`.

## 9. Checklist ra quyết định

Trước khi đặt `BigDecimal` vào `TreeSet` hoặc làm khóa `TreeMap`, tự trả lời:

1. “Trùng” nghĩa là **cùng giá trị số học** hay **cùng giá trị và scale**?
2. Ứng dụng có cần giữ nguyên các số 0 tận cùng, nguyên văn đầu vào hoặc đơn vị đo không?
3. Có cần sắp xếp không? Nếu không, `HashSet`/`HashMap` có thể phù hợp hơn khi dùng định nghĩa `equals()`.
4. Có cần một comparator nhất quán với `equals()`, chẳng hạn so sánh số học rồi so sánh scale?
5. Nếu chuẩn hóa, mọi đường ghi, tìm kiếm, cập nhật và xóa đã áp dụng cùng quy tắc chưa?
6. Các trường hợp `0.0`/`0.00`, `2.0`/`2.00`, scale âm và giá trị âm đã được kiểm tra chưa?

## 10. Tự kiểm tra

**Câu 1.** `TreeSet<BigDecimal>` lần lượt nhận `"1.0"`, `"1.00"`, `"2.0"`. Kích thước là bao nhiêu?  
**Đáp án:** 2, vì hai biểu diễn giá trị 1 so sánh bằng nhau qua `compareTo()`.

**Câu 2.** `TreeMap<BigDecimal, String>` lưu `"1.0" -> "A"` rồi `"1.00" -> "B"`. Truy vấn khóa `"1.000"` trả gì?  
**Đáp án:** `"B"`. Mọi khóa đó bằng nhau theo thứ tự tự nhiên, và `put` thứ hai thay value của entry đầu.

**Câu 3.** Với cùng hai giá trị `"1.0"`, `"1.00"`, `HashSet` có bao nhiêu phần tử?  
**Đáp án:** 2 vì `equals()` phân biệt scale.

**Câu 4.** Nếu ứng dụng cần cả hai scale trong một `TreeSet`, nên làm gì?  
**Đáp án:** truyền comparator so sánh theo giá trị số học, sau đó theo scale để tránh `compare()==0` khi `equals()==false`.

**Câu 5.** Dùng `stripTrailingZeros()` có luôn bảo toàn định dạng đầu vào không?  
**Đáp án:** không; `600.0` có thể trở thành `6E+2` và mất scale/chuỗi thể hiện ban đầu.

## 11. Ghi nhớ

- `BigDecimal.compareTo()` so sánh **số học**; `BigDecimal.equals()` so sánh **số học và scale**.
- `TreeSet` và `TreeMap` quyết định trùng nhau dựa trên **`compareTo()` hoặc `Comparator.compare()` bằng 0**, nên `2.0` và `2.00` bị gộp mặc định.
- `HashSet` và `HashMap` dùng `equals()`/`hashCode()` nên hai biểu diễn trên là hai phần tử/khóa riêng.
- Giải pháp đúng phụ thuộc ý nghĩa của khóa: **nhất quán số học** có thể chuẩn hóa; **phân biệt scale** có thể dùng comparator so sánh số học rồi scale; **định danh nghiệp vụ phức tạp** cần một kiểu khóa rõ ràng.

Tài liệu chính thức (Java SE 17):
- [`BigDecimal` — so sánh, equals, hashCode, stripTrailingZeros](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html)
- [`Comparable` — natural ordering và consistency with equals](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Comparable.html)
- [`TreeSet`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeSet.html)
- [`TreeMap`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeMap.html)
- [`Comparator`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Comparator.html)
