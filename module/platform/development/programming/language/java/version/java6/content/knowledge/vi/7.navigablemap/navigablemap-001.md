# NavigableMap: ánh xạ có thứ tự khóa và các truy vấn điều hướng

## 1. Khi tra đúng khóa là chưa đủ

Một `Map<K, V>` lưu quan hệ **khóa → giá trị**. Ví dụ:

```text
0   -> "base"
100 -> "standard"
500 -> "premium"
```

`get(100)` lấy giá trị gắn đúng khóa 100. Nhưng nếu người dùng nhập 320 và ta cần cấu hình bắt đầu có hiệu lực gần nhất mà không vượt 320, khóa cần tìm là 100. `get(320)` không tự làm việc đó.

`NavigableMap<K, V>` bổ sung các câu hỏi dựa trên thứ tự khóa: khóa ngay trước một mốc, khóa không vượt mốc, khóa đầu tiên đạt mốc hoặc khóa ngay sau mốc. Khi cần cả dữ liệu đi kèm, nó trả luôn cặp khóa–giá trị tương ứng.

Phân biệt các vai trò:

| Kiểu | Trọng tâm |
| --- | --- |
| `Map<K, V>` | Ánh xạ và tra đúng khóa |
| `SortedMap<K, V>` | Ánh xạ có thứ tự khóa, đầu/cuối và các góc nhìn khoảng |
| `NavigableMap<K, V>` | Bổ sung tìm hàng xóm, chọn đầu mốc có/không nhận bằng và chiều đảo |
| `TreeMap<K, V>` | Một cách cài đặt cụ thể dựa trên cây cân bằng |

Ta thường khai báo theo nhu cầu hành vi:

```java
// Đoạn minh họa, cần import java.util.NavigableMap và TreeMap.
NavigableMap<Integer, String> tiers = new TreeMap<>();
```

Nếu biến chỉ có kiểu `Map`, các phương thức như `floorEntry` không hiện diện trên kiểu đó, dù đối tượng thực tế là `TreeMap`.

Các ví dụ trong bài chạy bằng Java 17 trở lên và dùng API hiện hành.

## 2. Có thứ tự theo khóa nghĩa là gì?

### 2.1. Không phải thứ tự thêm hoặc thứ tự giá trị

Đưa các khóa vào lần lượt 500, 0, 100 vẫn cho thứ tự khóa tự nhiên:

```text
{0=base, 100=standard, 500=premium}
```

Thứ tự được quyết định bởi:

- Thứ tự tự nhiên của K, nếu không cung cấp comparator.
- Hoặc `Comparator<? super K>` được cấu hình khi tạo map.

Giá trị V không cần tự so sánh được và không tham gia quyết định vị trí. Thay `"standard"` bằng `"updated"` không chuyển khóa 100 sang vị trí khác. Hai khóa khác nhau cũng được phép cùng ánh xạ tới một giá trị.

Đây không phải cách “sắp xếp map theo value”. Nếu cần tìm giá trị nhỏ nhất hoặc xếp giá theo một thuộc tính trong V, phải có cấu trúc chỉ mục hoặc thuật toán phù hợp khác.

### 2.2. Tính duy nhất cũng theo phép so sánh khóa

Với `TreeMap`, các khóa có kết quả so sánh bằng 0 được xem là cùng một vị trí ánh xạ. `put` vào vị trí ấy thay giá trị trước đó, thay vì thêm một ánh xạ độc lập.

Thứ tự nên nhất quán với `equals` của khóa để tuân thủ hợp đồng chung của `Map`. Không dùng comparator chỉ theo một trường rồi giả định mọi đối tượng khác `equals` vẫn có khóa riêng. Đồng thời không sửa trường tham gia so sánh của một khóa đang nằm trong cây: cấu trúc không tự sắp xếp lại sau khi đối tượng bị đổi.

Những đặc điểm về thứ tự và quan hệ bằng của khóa được mô tả trong [TreeMap API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/TreeMap.html).

## 3. Bốn hướng tìm quanh một mốc

Giả sử map dùng khóa số tăng dần. Với mốc x, quy tắc là:

| Phía cần tìm | Điều kiện khóa k | Chỉ lấy khóa | Lấy cả khóa và giá trị |
| --- | --- | --- | --- |
| Ngay trước, không nhận bằng | k lớn nhất với `k < x` | `lowerKey(x)` | `lowerEntry(x)` |
| Phía trước, nhận bằng | k lớn nhất với `k <= x` | `floorKey(x)` | `floorEntry(x)` |
| Phía sau, nhận bằng | k nhỏ nhất với `k >= x` | `ceilingKey(x)` | `ceilingEntry(x)` |
| Ngay sau, không nhận bằng | k nhỏ nhất với `k > x` | `higherKey(x)` | `higherEntry(x)` |

Không có ứng viên thì phương thức trả `null`. Mốc không cần tồn tại trong map. Các phương thức này chỉ tìm, không xóa ánh xạ. Hợp đồng nằm trong [NavigableMap API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/NavigableMap.html).

Với khóa `[0, 100, 500]`:

| x | lowerKey | floorKey | ceilingKey | higherKey |
| --- | --- | --- | --- | --- |
| -1 | null | null | 0 | 0 |
| 0 | null | 0 | 0 | 100 |
| 100 | 0 | 100 | 100 | 500 |
| 320 | 100 | 100 | 500 | 500 |
| 500 | 100 | 500 | 500 | null |
| 600 | 500 | 500 | null | null |

Tại x = 100, `floor` và `ceiling` nhận chính mốc 100; `lower` và `higher` bỏ qua nó. Tại x = 320, không có khóa bằng mốc nên hai phương thức mỗi phía trả cùng khóa.

Các từ “trước”, “sau”, “nhỏ”, “lớn” luôn phải được hiểu theo comparator của map. Với thứ tự đảo, chúng không còn đồng nghĩa trực tiếp với nhỏ/lớn về giá trị số.

## 4. Chọn Key hay Entry?

### 4.1. Khi cần giá trị đi kèm, Entry diễn đạt trực tiếp hơn

Có thể lấy khóa rồi gọi `get`:

```java
// Đoạn minh họa, tiers có kiểu NavigableMap<Integer, String>.
Integer key = tiers.floorKey(320);
if (key != null) {
    String value = tiers.get(key);
    System.out.println(value);
}
```

Nhưng nếu mục tiêu là tìm cấu hình có hiệu lực, `floorEntry` diễn đạt đầy đủ hơn:

```java
// Đoạn minh họa.
Map.Entry<Integer, String> selected = tiers.floorEntry(320);
if (selected != null) {
    System.out.println(selected.getKey());
    System.out.println(selected.getValue());
}
```

Cách dùng Entry tránh một lần tra lại khóa và giữ rõ quan hệ khóa–giá trị được chọn trong lần gọi. Nó không biến toàn bộ nghiệp vụ nhiều bước thành một giao dịch hoặc khóa dữ liệu khỏi thay đổi đồng thời.

Nếu chỉ cần mốc để hiển thị hoặc tiếp tục một phép tính, dùng dạng Key là đủ.

### 4.2. Null entry khác với entry có value null

`TreeMap` cho phép value null. Vì vậy phải phân biệt:

```text
entry == null
    -> Không có ánh xạ thỏa điều kiện điều hướng.

entry != null và entry.getValue() == null
    -> Có ánh xạ; giá trị được lưu tại đó là null.
```

Trong khi đó, `get(key)` trả null có thể nghĩa là không có khóa hoặc có khóa với value null. Dùng `containsKey` khi cần phân biệt hai trường hợp ấy.

Với map khóa `Integer`, tránh gán thẳng một kết quả điều hướng có thể null vào `int`: quá trình tự mở hộp sẽ gây `NullPointerException`.

Các ví dụ chính không dùng khóa null. `TreeMap` theo thứ tự tự nhiên không chấp nhận khóa null; chính sách của comparator tùy chỉnh hoặc cách cài đặt khác cần được xét riêng.

### 4.3. Entry điều hướng là ảnh chụp ánh xạ

Entry nhận từ `floorEntry`, `ceilingEntry`, `lowerEntry`, `higherEntry`, `firstEntry` hoặc `lastEntry` biểu diễn ánh xạ tại thời điểm gọi. Trên `TreeMap`, chúng không hỗ trợ `setValue`; muốn cập nhật map, dùng thao tác map phù hợp như `put`.

Ví dụ:

```text
Lấy floorEntry(320) -> 100=standard
Sau đó put(100, "updated")

Entry đã lấy       -> vẫn 100=standard
Ánh xạ hiện tại    -> 100=updated
```

Đây là ảnh chụp **nông** của cặp tham chiếu. Nếu V là một đối tượng mutable, việc sửa chính đối tượng ấy vẫn có thể quan sát được qua tham chiếu đã lấy. Nó không phải bản sao sâu của toàn bộ dữ liệu.

Không suy ra mọi `Map.Entry` trong Java có cùng khả năng sửa đổi. Entry nhận qua các API khác, chẳng hạn iterator của một cách cài đặt map cụ thể, có thể có hợp đồng khác.

## 5. Đầu, cuối và thao tác lấy rồi xóa

| Mục đích | Phương thức | Khi map rỗng |
| --- | --- | --- |
| Xem ánh xạ đầu | `firstEntry()` | `null` |
| Xem ánh xạ cuối | `lastEntry()` | `null` |
| Lấy khóa đầu | `firstKey()` | Ném `NoSuchElementException` |
| Lấy khóa cuối | `lastKey()` | Ném `NoSuchElementException` |
| Lấy và xóa ánh xạ đầu | `pollFirstEntry()` | `null` |
| Lấy và xóa ánh xạ cuối | `pollLastEntry()` | `null` |

“Đầu” và “cuối” theo thứ tự hiện tại. Trên map khóa tự nhiên tăng dần, đầu có khóa nhỏ nhất và cuối có khóa lớn nhất.

Đừng thay `lastEntry` bằng `pollLastEntry` chỉ để đọc phần tử cuối: `poll` làm thay đổi dữ liệu. Các thao tác xóa còn phụ thuộc map hoặc góc nhìn có cho sửa hay không.

## 6. Các góc nhìn liên quan đến thứ tự

### 6.1. Bộ khóa có khả năng điều hướng

`navigableKeySet()` trả `NavigableSet<K>` là góc nhìn các khóa. Nó hữu ích khi chỉ cần điều hướng giữa các mốc, không cần V.

`descendingKeySet()` cho thứ tự khóa đảo; `descendingMap()` cho cả ánh xạ theo thứ tự đảo.

Đây là góc nhìn liên kết. Xóa một khóa qua bộ khóa có hỗ trợ xóa sẽ xóa ánh xạ tương ứng khỏi map. Không thể thêm khóa qua bộ khóa để tự tạo một V chưa được xác định; hãy thêm ánh xạ bằng `put`.

### 6.2. Khoảng có đầu nhận hoặc loại

Với khóa tăng dần:

```java
// Đoạn minh họa.
NavigableMap<Integer, String> window =
        tiers.subMap(100, true, 500, false);
```

Góc nhìn chỉ nhận các khóa thuộc `[100, 500)`. Hai boolean quyết định có nhận từng đầu mốc hay không.

- Thay một ánh xạ qua window ảnh hưởng map gốc.
- Thêm khóa nằm ngoài khoảng qua window bị từ chối.
- Truy vấn điều hướng trên window chỉ xét khóa thuộc khoảng ấy.

Nếu map gốc có khóa 500 nhưng window loại 500, `window.ceilingKey(300)` có thể trả null dù `tiers.ceilingKey(300)` trả 500.

Đây không phải bản sao độc lập; thay đổi map gốc trong phạm vi cũng xuất hiện ở window. `headMap` và `tailMap` tạo góc nhìn một phía tương tự.

### 6.3. Thứ tự đảo cũng đảo hướng điều hướng

Nếu khóa hiện có là `[0, 100, 200, 500]`, góc nhìn đảo có thứ tự `[500, 200, 100, 0]`.

Trên góc nhìn đó, `lowerKey(100)` trả 200: 200 đứng trước 100 theo thứ tự đảo. Khi tạo khoảng trên map đảo, hai đầu cũng phải hợp lệ theo comparator đảo, không theo thứ tự số tăng mặc định.

## 7. Chương trình hoàn chỉnh

Lưu thành **NavigableMapOverview.java**. Phần `pollLastEntry` cố ý chạy trên bản sao để quan sát thao tác lấy/xóa mà không làm mất ánh xạ trong biến tiers dùng để đối chiếu.

```java
import java.util.Map;
import java.util.NavigableMap;
import java.util.TreeMap;

public class NavigableMapOverview {
    static void printKeys(NavigableMap<Integer, String> map, int target) {
        System.out.printf("%d | %s | %s | %s | %s%n",
                target, map.lowerKey(target), map.floorKey(target),
                map.ceilingKey(target), map.higherKey(target));
    }

    public static void main(String[] args) {
        NavigableMap<Integer, String> tiers = new TreeMap<>();
        tiers.put(500, "premium");
        tiers.put(0, "base");
        tiers.put(100, "standard");
        System.out.println("Map: " + tiers);
        System.out.println("Keys: " + tiers.navigableKeySet());
        System.out.println("x | lower | floor | ceiling | higher");
        for (int target : new int[]{-1, 0, 100, 320, 500, 600}) {
            printKeys(tiers, target);
        }

        Map.Entry<Integer, String> selected = tiers.floorEntry(320);
        if (selected == null) throw new AssertionError("Missing base tier");
        System.out.println("Tier for 320: " + selected);
        tiers.put(100, "updated");
        System.out.println("Saved entry: " + selected);
        System.out.println("Current mapping: " + tiers.get(100));
        try {
            selected.setValue("illegal");
        } catch (UnsupportedOperationException ex) {
            System.out.println("Navigation entry cannot setValue");
        }

        NavigableMap<Integer, String> window =
                tiers.subMap(100, true, 500, false);
        System.out.println("Window: " + window);
        window.put(200, "extra");
        System.out.println("Base after view.put: " + tiers);
        System.out.println("Window ceilingKey(300): " + window.ceilingKey(300));
        System.out.println("Base ceilingKey(300): " + tiers.ceilingKey(300));
        System.out.println("Descending: " + tiers.descendingMap());
        System.out.println("Descending lowerKey(100): " +
                tiers.descendingMap().lowerKey(100));

        NavigableMap<Integer, String> copy = new TreeMap<>(tiers);
        System.out.println("Polled last from copy: " + copy.pollLastEntry());
        System.out.println("Copy after poll: " + copy);
        System.out.println("Base still has 500: " + tiers.containsKey(500));

        NavigableMap<Integer, String> nullableValues = new TreeMap<>();
        nullableValues.put(10, null);
        Map.Entry<Integer, String> nullableEntry =
                nullableValues.floorEntry(10);
        System.out.println("Entry exists: " + (nullableEntry != null));
        System.out.println("Entry value: " + nullableEntry.getValue());
        System.out.println("get missing: " + nullableValues.get(99));
        System.out.println("get present null: " + nullableValues.get(10));

        NavigableMap<Integer, String> empty = new TreeMap<>();
        System.out.println("Empty firstEntry: " + empty.firstEntry());
        System.out.println("Empty floorKey: " + empty.floorKey(10));
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac -encoding UTF-8 NavigableMapOverview.java
java NavigableMapOverview
```

Kết quả chuẩn:

```text
Map: {0=base, 100=standard, 500=premium}
Keys: [0, 100, 500]
x | lower | floor | ceiling | higher
-1 | null | null | 0 | 0
0 | null | 0 | 0 | 100
100 | 0 | 100 | 100 | 500
320 | 100 | 100 | 500 | 500
500 | 100 | 500 | 500 | null
600 | 500 | 500 | null | null
Tier for 320: 100=standard
Saved entry: 100=standard
Current mapping: updated
Navigation entry cannot setValue
Window: {100=updated}
Base after view.put: {0=base, 100=updated, 200=extra, 500=premium}
Window ceilingKey(300): null
Base ceilingKey(300): 500
Descending: {500=premium, 200=extra, 100=updated, 0=base}
Descending lowerKey(100): 200
Polled last from copy: 500=premium
Copy after poll: {0=base, 100=updated, 200=extra}
Base still has 500: true
Entry exists: true
Entry value: null
get missing: null
get present null: null
Empty firstEntry: null
Empty floorKey: null
```

Dòng `Saved entry` đối chiếu với `Current mapping` cho thấy ảnh chụp entry khác góc nhìn map liên kết. Dòng `Base after view.put` cho thấy window sửa được dữ liệu gốc. Hai cơ chế này không nên bị nhầm lẫn chỉ vì đều trả về một đối tượng Java.

## 8. Ứng dụng và giới hạn của phép tìm theo khóa

### 8.1. Cấu hình bắt đầu có hiệu lực từ một mốc

Nếu cấu hình tại khóa k có hiệu lực từ k cho đến trước mốc kế tiếp, dùng `floorEntry(x)`. Tại đúng mốc 100, cấu hình của 100 phải được chọn; `lowerEntry(100)` sẽ lấy sai mốc trước.

Phải xác định hành vi khi x nhỏ hơn mọi mốc: có cấu hình mặc định, từ chối yêu cầu hay báo thiếu dữ liệu. Không mặc định rằng lúc nào cũng có một khóa 0 nếu miền dữ liệu còn cho giá trị âm.

### 8.2. Chọn mức tối thiểu đáp ứng yêu cầu

Nếu khóa là dung lượng, còn V là cấu hình gói dịch vụ, `ceilingEntry(requested)` chọn dung lượng nhỏ nhất vẫn đủ đáp ứng. Nếu không có ứng viên thì trả null; cần xử lý trường hợp hết mức hỗ trợ.

### 8.3. Điều hướng qua các phiên bản hoặc mốc

`higherEntry(currentKey)` lấy phiên bản có khóa tiếp theo, còn `lowerEntry(currentKey)` lấy phiên bản trước. Không dùng `ceilingEntry` nếu yêu cầu phải đi tiếp qua mốc hiện tại; nó có thể trả lại chính mốc đang đứng.

Các hàm điều hướng không giữ vị trí duyệt. Gọi lặp với cùng mốc trên cùng dữ liệu không đổi sẽ tiếp tục trả cùng kết quả.

### 8.4. Không tự suy ra khoảng cách hoặc ngữ nghĩa khoảng

“Gần nhất” trong hợp đồng là ứng viên sát mốc ở một phía theo thứ tự, không phải ứng viên có khoảng cách số học nhỏ nhất. Muốn gần nhất theo khoảng cách, phải lấy cả hai phía và áp dụng quy tắc riêng.

Tương tự, nếu khóa là thời điểm bắt đầu còn V chứa cả thời điểm kết thúc của một lịch hẹn, `floorEntry(time)` chỉ tìm lịch có mốc bắt đầu phù hợp gần nhất. Nó không tự chứng minh lịch đó còn hiệu lực hoặc giải quyết các khoảng chồng lấn. Phải kiểm tra thêm thông tin trong V hoặc dùng mô hình chỉ mục khác.

## 9. Chi phí và truy cập đồng thời

`TreeMap` dựa trên cây đỏ–đen. `get`, `put`, `remove` và `containsKey` có thời gian O(log n). Các truy vấn điều hướng cũng tìm dọc chiều cao cây, nên có chi phí O(log n) lần so sánh; tổng chi phí còn phụ thuộc comparator.

Nếu chỉ cần tra đúng khóa và không cần quan hệ thứ tự, hãy cân nhắc đặc tính của một cấu trúc như `HashMap`. Không có lợi ích khi chọn cây chỉ để kỳ vọng tra khóa trung bình hằng số.

Để duyệt mọi ánh xạ, dùng iterator/for-each trên `entrySet` theo thứ tự mong muốn thay vì liên tục gọi `higherEntry` cho từng khóa. Tìm lại n lần có thể tốn O(n log n), trong khi duyệt toàn bộ cây theo iterator có thời gian O(n).

`NavigableMap` là giao diện, không ép mọi cách cài đặt cùng hiệu năng hoặc chính sách đồng thời. `TreeMap` không tự đồng bộ truy cập nhiều luồng. Chuỗi “tìm ứng viên, kiểm tra, cập nhật” không tự nguyên tử; ảnh chụp entry cũng không khóa ánh xạ đó cho bên gọi. Khi có truy cập đồng thời, cần cơ chế sở hữu hoặc đồng bộ phù hợp với cả nghiệp vụ.

## 10. Lỗi thường gặp và thực hành

| Lỗi | Cách sửa |
| --- | --- |
| Nghĩ map sắp theo value | Đọc comparator của khóa |
| Dùng `get` để tìm mốc gần nhất | Chọn phương thức điều hướng theo phía và nhận bằng |
| Dùng `higher` thay `ceiling` | Thử đầu vào bằng đúng một khóa hiện có |
| Tự mở hộp kết quả null | Giữ kiểu đối tượng, kiểm tra trước |
| Nhầm value null với không có ánh xạ | Kiểm tra entry hoặc `containsKey` phù hợp |
| Gọi `setValue` trên entry điều hướng | Cập nhật qua map, tuân thủ hợp đồng cụ thể |
| Dùng `poll` chỉ để xem | Dùng `firstEntry` hoặc `lastEntry` |
| Coi subMap là bản sao | Nhận diện quan hệ liên kết và giới hạn khóa |
| Dùng comparator chỉ theo một phần định danh | Xác định lại ý nghĩa khóa duy nhất |
| Coi entry được chọn là tài nguyên đã đặt chỗ | Thiết kế đồng bộ cho cả thao tác nghiệp vụ |

Bài tập tự kiểm chứng:

1. Với `{10=A, 30=B, 50=C}`, dự đoán bốn truy vấn Key cho mốc 30 và 40. Tại 30 phải nhận `10, 30, 30, 50`; tại 40 nhận `30, 30, 50, 50`.
2. Chọn `floorEntry(40)`, rồi thay giá trị tại khóa 30. Xác minh entry đã chọn và giá trị hiện tại có thể khác nhau.
3. Tạo `subMap(10, true, 50, false)`. Giải thích vì sao truy vấn `ceilingKey(40)` trên góc nhìn trả null dù tập gốc có khóa 50.
4. Thêm một khóa có value null, rồi phân biệt “entry tồn tại với value null” và “không có entry”. Không gọi `getValue` khi entry là null.
5. Dùng một bản sao map để thử `pollFirstEntry` cho đến khi rỗng. Xác minh mỗi lần lấy làm số ánh xạ giảm một và lần gọi cuối trả null.

Khi chọn một truy vấn điều hướng, hãy xác định rõ thứ tự khóa, phía cần tìm, có nhận bằng không, cần chỉ khóa hay cả giá trị, và hành vi khi không có ánh xạ. Đó là nền tảng để dùng `NavigableMap` đúng với dữ liệu nghiệp vụ.
