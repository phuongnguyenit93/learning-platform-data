# Thứ tự List và giới hạn bảo đảm thứ tự của Set, Map

## 1. Thứ tự là một phần của hợp đồng kiểu dữ liệu

Các collection trong Java không có cùng một cam kết về thứ tự lặp qua phần tử.

- **List** biểu diễn một dãy có thứ tự. Mỗi phần tử có vị trí, truy cập được bằng chỉ số và có thể xuất hiện nhiều lần.
- **Set** biểu diễn tập hợp phần tử không trùng lặp. Interface `Set` không cam kết một thứ tự lặp chung cho mọi implementation.
- **Map** ánh xạ key sang value. Interface `Map` không cam kết thứ tự lặp chung cho các key, value hoặc entry; thứ tự phụ thuộc implementation cụ thể.

Cần phân biệt ba khái niệm:

1. **Encounter order:** thứ tự mà iterator hoặc thao tác duyệt collection đưa phần tử ra.
2. **Insertion order:** thứ tự các phần tử hoặc key được thêm lần đầu.
3. **Sorted order:** thứ tự được xác định bởi thứ tự tự nhiên hoặc một `Comparator`.

Một collection có thể giữ thứ tự thêm vào, sắp xếp theo comparator hoặc không đưa ra bất kỳ bảo đảm thứ tự nào. Không suy luận thứ tự chỉ từ kết quả một lần chạy.

## 2. List: luôn có thứ tự theo vị trí

Hợp đồng của `List` xác định một dãy có thứ tự. Phần tử được truy cập bằng chỉ số từ 0 đến `size() - 1`; các thao tác thêm, xóa hoặc sắp xếp có thể làm thay đổi vị trí. List cho phép phần tử trùng lặp.

```java
List<String> colors = List.of("red", "blue", "red");

System.out.println(colors.get(0));
System.out.println(colors);
```

Kết quả:

```text
red
[red, blue, red]
```

`List.of` được bổ sung từ Java 9. Nó tạo list không sửa được, giữ nguyên thứ tự đối số truyền vào và cho phép phần tử trùng lặp; nó từ chối `null`. Tính không sửa được không làm mất thứ tự của List.

Các implementation phổ biến:

- `ArrayList` giữ thứ tự theo chỉ số và thường phù hợp khi cần truy cập ngẫu nhiên nhanh.
- `LinkedList` cũng giữ thứ tự theo vị trí, nhưng truy cập theo chỉ số phải đi qua các node.
- `List.of` và `List.copyOf` tạo list không sửa được, giữ thứ tự phần tử theo nguồn hoặc đối số.

Khi cần sắp xếp, dùng `List.sort(comparator)` hoặc `Collections.sort(list, comparator)`. Phép sort của List là ổn định: các phần tử được comparator xem là bằng nhau giữ nguyên thứ tự tương đối trước khi sắp xếp. Việc gọi sort chủ động thay đổi thứ tự của list có thể sửa được.

## 3. Set: interface không bảo đảm thứ tự chung

`Set` không cho phép hai phần tử bằng nhau theo quy tắc `equals` của Set cùng tồn tại. Tuy nhiên, interface này không quy định thứ tự lặp chung. Muốn có thứ tự cụ thể, phải chọn implementation có hợp đồng phù hợp.

### HashSet: không có thứ tự lặp được bảo đảm

`HashSet` dùng bảng băm để lưu phần tử. Nó không bảo đảm thứ tự lặp; thứ tự có thể thay đổi khi cấu trúc bảng thay đổi, khi thêm/xóa phần tử hoặc giữa các lần chạy. Một kết quả có vẻ ổn định trong thử nghiệm không phải cam kết API.

Dùng `HashSet` khi cần tập hợp không trùng lặp và không phụ thuộc thứ tự. Không viết test hoặc logic nghiệp vụ giả định phần tử đầu tiên của iterator là một giá trị cố định.

### LinkedHashSet: giữ thứ tự thêm vào

`LinkedHashSet` duy trì thứ tự lặp theo thứ tự phần tử được thêm lần đầu. Khi thêm lại một phần tử đã có, phần tử đó không chuyển đến cuối. Nếu xóa phần tử rồi thêm lại, nó được thêm ở vị trí cuối của thứ tự mới.

```java
Set<String> names = new LinkedHashSet<>();
names.add("blue");
names.add("red");
names.add("blue");
names.add("green");

System.out.println(names);
```

Kết quả:

```text
[blue, red, green]
```

Dùng `LinkedHashSet` khi cần loại bỏ trùng lặp nhưng vẫn muốn duyệt theo thứ tự chèn.

### TreeSet: giữ thứ tự sắp xếp

`TreeSet` duy trì phần tử theo thứ tự tự nhiên hoặc theo `Comparator` được cung cấp. Iterator duyệt theo thứ tự tăng dần của quy tắc đó.

```java
Set<String> names = new TreeSet<>(
        List.of("blue", "red", "green")
);

System.out.println(names);
```

Kết quả:

```text
[blue, green, red]
```

Với `TreeSet`, kết quả `compare(a, b) == 0` được xem là hai phần tử trùng nhau theo thứ tự của set, kể cả khi `a.equals(b)` không trả về `true`. Comparator nên nhất quán với `equals` nếu muốn tuân thủ đầy đủ hợp đồng tổng quát của Set.

### Các Set factory và implementation khác

- `Set.of` (Java 9) tạo set không sửa được, từ chối `null` và phần tử trùng lặp. Thứ tự lặp của set tạo bởi factory method không được bảo đảm.
- `Set.copyOf` (Java 10) tạo set không sửa được; không nên dựa vào thứ tự lặp của kết quả.
- `EnumSet` duyệt phần tử theo thứ tự khai báo của các hằng enum, không theo thứ tự thêm vào.

## 4. Map: thứ tự phụ thuộc implementation

`Map` không phải là một List các cặp key-value. Interface `Map` không cam kết thứ tự lặp chung. Thứ tự quan sát được qua `keySet()`, `values()` và `entrySet()` đi theo quy tắc lặp của map cụ thể.

### HashMap: không có thứ tự key được bảo đảm

`HashMap` không cam kết thứ tự lặp của key hoặc entry. Không dựa vào thứ tự hiện ra khi in map, kể cả khi dữ liệu nhỏ hoặc thứ tự có vẻ không đổi qua vài lần chạy.

Dùng `HashMap` khi cần tra cứu theo key và không cần thứ tự duyệt cụ thể.

### LinkedHashMap: thứ tự chèn hoặc thứ tự truy cập

Mặc định, `LinkedHashMap` giữ thứ tự key được chèn lần đầu. Cập nhật value của key đã tồn tại không làm key đó chuyển vị trí.

Constructor có tham số `accessOrder = true` chuyển map sang chế độ thứ tự truy cập. Những lần truy cập phù hợp, chẳng hạn `get`, đưa entry được truy cập về cuối thứ tự. Chế độ này hữu ích khi xây dựng cache kiểu least-recently-used (LRU).

```java
Map<String, Integer> cache =
        new LinkedHashMap<>(16, 0.75f, true);

cache.put("A", 1);
cache.put("B", 2);
cache.put("C", 3);

cache.get("A");

System.out.println(cache.keySet());
```

Kết quả:

```text
[B, C, A]
```

Entry A được truy cập sau B và C nên chuyển về cuối. Nếu chỉ cần thứ tự chèn, dùng constructor mặc định của `LinkedHashMap`.

### TreeMap: sắp xếp theo key

`TreeMap` duy trì các key theo thứ tự tự nhiên hoặc `Comparator`. Các view `keySet()` và `entrySet()` duyệt theo thứ tự key đó.

```java
Map<String, Integer> scores = new TreeMap<>();
scores.put("third", 3);
scores.put("first", 1);
scores.put("second", 2);

System.out.println(scores);
```

Kết quả:

```text
{first=1, second=2, third=3}
```

Tương tự `TreeSet`, comparator trả về 0 cho hai key khiến TreeMap xem chúng là cùng một vị trí key. Comparator không nhất quán với `equals` có thể khiến hành vi của map khác kỳ vọng thông thường của hợp đồng `Map`.

### EnumMap và các factory method

- `EnumMap` duyệt key theo thứ tự khai báo của các hằng enum.
- `Map.of` và `Map.ofEntries` (Java 9) tạo map không sửa được. Thứ tự lặp không được bảo đảm.
- `Map.copyOf` (Java 10) tạo map không sửa được; thứ tự lặp của kết quả cũng không được bảo đảm.

Không dùng `Map.of`, `Map.ofEntries` hoặc `Map.copyOf` khi logic cần thứ tự chèn hay thứ tự sắp xếp. Hãy chọn `LinkedHashMap` hoặc `TreeMap` theo yêu cầu.

## 5. Ví dụ tổng hợp có kết quả xác định

Chương trình sau minh họa List, các Set và các Map có thứ tự cụ thể. Với `HashSet`, ví dụ chỉ kiểm tra số lượng và khả năng chứa phần tử; nó không in thứ tự iterator vì thứ tự đó không được bảo đảm.

```java
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeMap;
import java.util.TreeSet;

public class CollectionOrderDemo {
    public static void main(String[] args) {
        List<String> list = List.of("red", "blue", "red");
        System.out.println("List = " + list);

        Set<String> hashSet = new HashSet<>(list);
        System.out.println("HashSet size = " + hashSet.size());
        System.out.println("HashSet contains blue = "
                + hashSet.contains("blue"));

        Set<String> insertionOrder = new LinkedHashSet<>();
        insertionOrder.add("blue");
        insertionOrder.add("red");
        insertionOrder.add("blue");
        insertionOrder.add("green");
        System.out.println("LinkedHashSet = " + insertionOrder);

        Set<String> sortedSet = new TreeSet<>(insertionOrder);
        System.out.println("TreeSet = " + sortedSet);

        Map<String, Integer> insertionMap = new LinkedHashMap<>();
        insertionMap.put("third", 3);
        insertionMap.put("first", 1);
        insertionMap.put("second", 2);
        System.out.println("LinkedHashMap = " + insertionMap);

        Map<String, Integer> sortedMap = new TreeMap<>(insertionMap);
        System.out.println("TreeMap = " + sortedMap);

        Map<String, Integer> accessOrder =
                new LinkedHashMap<>(16, 0.75f, true);
        accessOrder.put("A", 1);
        accessOrder.put("B", 2);
        accessOrder.put("C", 3);
        accessOrder.get("A");
        System.out.println("Access-order keys = "
                + accessOrder.keySet());
    }
}
```

Lưu mã nguồn trong `CollectionOrderDemo.java`, sau đó biên dịch và chạy với Java 17 trở lên:

```bash
javac --release 17 -Xlint:all CollectionOrderDemo.java
java CollectionOrderDemo
```

Kết quả:

```text
List = [red, blue, red]
HashSet size = 2
HashSet contains blue = true
LinkedHashSet = [blue, red, green]
TreeSet = [blue, green, red]
LinkedHashMap = {third=3, first=1, second=2}
TreeMap = {first=1, second=2, third=3}
Access-order keys = [B, C, A]
```

## 6. Sequenced Collections từ Java 21

Từ Java 21, Java bổ sung các interface `SequencedCollection`, `SequencedSet` và `SequencedMap` để mô tả collection có thứ tự gặp phần tử rõ ràng và cung cấp thao tác ở hai đầu.

Các interface này bổ sung những thao tác như:

- `getFirst()` và `getLast()` để đọc phần tử đầu/cuối.
- `addFirst(...)` và `addLast(...)` ở các kiểu hỗ trợ thay đổi.
- `reversed()` để lấy view theo chiều ngược của thứ tự gặp phần tử.

`List` là một `SequencedCollection`; `SequencedSet` mô tả Set có encounter order; `SequencedMap` mô tả Map có thứ tự và các view tương ứng. `LinkedHashSet` và `LinkedHashMap` triển khai các interface sequenced này trong Java 21 trở lên.

```java
import java.util.LinkedHashSet;
import java.util.SequencedSet;

public class SequencedCollectionsDemo {
    public static void main(String[] args) {
        SequencedSet<String> names = new LinkedHashSet<>();
        names.addFirst("Ada");
        names.addLast("Grace");
        names.addLast("Linus");

        System.out.println(names.getFirst());
        System.out.println(names.getLast());
        System.out.println(names.reversed());
    }
}
```

Biên dịch với Java 21 trở lên:

```bash
javac --release 21 -Xlint:all SequencedCollectionsDemo.java
java SequencedCollectionsDemo
```

Kết quả:

```text
Ada
Linus
[Linus, Grace, Ada]
```

Sequenced Collections chuẩn hóa cách thao tác với đầu, cuối và view đảo thứ tự. Chúng không làm cho mọi Set hoặc Map bất kỳ tự nhiên có thứ tự; implementation vẫn phải cung cấp encounter order để triển khai hợp đồng sequenced.

## 7. Thứ tự trong Stream và khi nào cần kiểm soát nó

Stream có thể mang encounter order từ nguồn dữ liệu. Stream tạo từ List thông thường có encounter order theo thứ tự List. Stream từ một nguồn không bảo đảm thứ tự, chẳng hạn HashSet, không tự tạo ra một thứ tự ổn định.

Với stream có encounter order, `forEachOrdered` yêu cầu xử lý theo thứ tự đó, kể cả khi pipeline chạy song song. `forEach` không cam kết giữ thứ tự encounter trong xử lý song song. Nếu thứ tự là yêu cầu nghiệp vụ, hãy chọn nguồn và terminal operation phù hợp thay vì dựa vào lịch chạy thread.

Nếu cần thứ tự cụ thể cho kết quả, có thể sắp xếp rõ ràng bằng `sorted()` hoặc `sorted(comparator)`. Sắp xếp stream tạo thứ tự cho các phần tử đi qua bước đó; nó không thay đổi collection nguồn.

## 8. Chọn implementation theo yêu cầu

| Yêu cầu | Kiểu phù hợp | Bảo đảm |
|---|---|---|
| Dãy theo chỉ số, cho phép trùng lặp | `List` / `ArrayList` | Thứ tự vị trí |
| Không trùng lặp, không cần thứ tự | `HashSet` | Không bảo đảm thứ tự lặp |
| Không trùng lặp, giữ thứ tự thêm | `LinkedHashSet` | Thứ tự chèn |
| Không trùng lặp, cần sắp xếp | `TreeSet` | Thứ tự tự nhiên/comparator |
| Tra cứu key, không cần thứ tự | `HashMap` | Không bảo đảm thứ tự lặp |
| Map giữ thứ tự thêm | `LinkedHashMap` | Thứ tự chèn |
| Map giữ thứ tự truy cập | `LinkedHashMap` với `accessOrder=true` | Thứ tự truy cập |
| Map sắp xếp theo key | `TreeMap` | Thứ tự key |
| Key/phần tử là enum | `EnumMap` / `EnumSet` | Thứ tự khai báo enum |

## 9. Checklist khi review mã nguồn

1. Logic có thực sự phụ thuộc vào thứ tự duyệt không, hay chỉ cần membership/tra cứu?
2. Nếu cần thứ tự, hợp đồng của interface hay implementation cụ thể bảo đảm điều đó?
3. Có đang vô tình dựa vào thứ tự hiện tại của HashSet hoặc HashMap không?
4. Yêu cầu là thứ tự chèn, thứ tự truy cập hay thứ tự sắp xếp?
5. Với TreeSet/TreeMap, comparator có nhất quán với `equals` và có thứ tự tổng hợp lệ không?
6. Factory method `Set.of` hoặc `Map.of` có bị dùng ở nơi cần thứ tự không?
7. Stream có encounter order không và có cần `forEachOrdered` hoặc `sorted` không?
8. Nếu dùng Sequenced Collections, môi trường chạy có Java 21 trở lên không?

Hãy dựa vào hợp đồng của interface và implementation đang dùng. List có thứ tự theo vị trí; Set và Map chỉ có thứ tự cụ thể khi implementation hoặc API được chọn cam kết điều đó.