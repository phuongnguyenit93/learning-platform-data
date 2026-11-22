# Các biến thể truy vấn trả về key trong NavigableMap

## 1. Khi chỉ cần biết khóa nào phù hợp

`NavigableMap<K, V>` lưu ánh xạ khóa–giá trị theo một thứ tự của **khóa**. Ngoài việc tìm một mục gồm cả khóa và giá trị, nó cung cấp các phương thức chỉ trả về khóa phù hợp với mốc truy vấn:

```java
K lowerKey(K key);
K floorKey(K key);
K ceilingKey(K key);
K higherKey(K key);
```

Đây là chữ ký minh họa API. Kiểu trả về là `K`, không phải `V`, cũng không phải `Map.Entry<K, V>`.

Ví dụ một bảng phân hạng có khóa là điểm tối thiểu, giá trị là tên hạng. Nếu chỉ cần biết mức điểm nào đã đạt để đánh dấu trên giao diện, `floorKey(score)` cho kết quả trực tiếp. Nếu cần cả tên hạng, có thể chọn truy vấn trả về entry để thể hiện đúng nhu cầu.

Các biến thể trả khóa vẫn thuộc API hiện hành; xem [NavigableMap](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/NavigableMap.html).

## 2. Bốn quan hệ cần phân biệt

Với thứ tự tự nhiên của khóa số nguyên:

| Phương thức | Tìm khóa k | Khi không có khóa phù hợp |
| --- | --- | --- |
| `lowerKey(x)` | Khóa lớn nhất thỏa `k < x` | `null` |
| `floorKey(x)` | Khóa lớn nhất thỏa `k <= x` | `null` |
| `ceilingKey(x)` | Khóa nhỏ nhất thỏa `k >= x` | `null` |
| `higherKey(x)` | Khóa nhỏ nhất thỏa `k > x` | `null` |

`floor/ceiling` cho phép bằng mốc; `lower/higher` loại trường hợp bằng. Cả bốn đều quan sát dữ liệu, không lấy khóa ra khỏi map và không thay đổi ánh xạ. Hợp đồng từng phương thức nằm trong [NavigableMap: các truy vấn trả khóa](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/NavigableMap.html).

Giả sử các khóa là `[0, 50, 100, 200]`:

- Với mốc 135 chưa có trong map: `lowerKey` và `floorKey` đều là 100; `ceilingKey` và `higherKey` đều là 200.
- Với mốc 100 đã có: `lowerKey` là 50, `floorKey` là 100, `ceilingKey` là 100 và `higherKey` là 200.

Mốc truy vấn không bắt buộc phải là một khóa hiện có. Nó chỉ cần hợp lệ đối với quy tắc so sánh của map.

## 3. Chọn theo ý định của chương trình

### Mức đã đạt: floorKey

Nếu mỗi khóa là **điểm tối thiểu để vào hạng**, `floorKey(score)` tìm ngưỡng cao nhất không vượt điểm hiện có.

Với 135 điểm, ngưỡng là 100. `ceilingKey(135)` lại tìm 200, có thể là mục tiêu chưa đạt; dùng nhầm phương thức sẽ xếp hạng sai.

### Mốc tiếp theo: higherKey hoặc ceilingKey

Nếu “tiếp theo” phải khác và cao hơn mốc đang xét, dùng `higherKey`. Nếu “từ mốc này trở đi” cho phép chính mốc đó, dùng `ceilingKey`.

Ví dụ tại khóa 100:

- Mốc không thấp hơn 100: `ceilingKey(100)` là 100.
- Mốc cao hơn 100: `higherKey(100)` là 200.

### Mốc trước đó: lowerKey hoặc floorKey

Tương tự, “trước mốc” là quan hệ nghiêm ngặt; “không sau mốc” cho phép bằng. Với thời gian hoặc phiên bản được sắp xếp, chọn sai dấu bằng là một lỗi biên có thể không lộ ra nếu chỉ kiểm thử mốc nằm giữa hai khóa.

`ceilingKey` không có nghĩa “khóa gần nhất theo khoảng cách”. Nó chỉ tìm về một phía. Nếu thật sự cần khoảng cách nhỏ nhất, phải xét cả hai phía cùng quy tắc khi bằng khoảng cách.

## 4. Ví dụ đầy đủ chạy trên Java 17+

Lưu tệp `NavigableMapKeyQueries.java`:

```java
import java.util.NavigableMap;
import java.util.NoSuchElementException;
import java.util.TreeMap;

public class NavigableMapKeyQueries {
    private static void printNeighbors(NavigableMap<Integer, String> map,
                                       int query) {
        System.out.println(query
                + " -> lower=" + map.lowerKey(query)
                + ", floor=" + map.floorKey(query)
                + ", ceiling=" + map.ceilingKey(query)
                + ", higher=" + map.higherKey(query));
    }

    private static void showEmptyEndpoint(NavigableMap<Integer, String> map,
                                          boolean first) {
        String name = first ? "firstKey" : "lastKey";
        try {
            Integer key = first ? map.firstKey() : map.lastKey();
            System.out.println("empty " + name + "=" + key);
        } catch (NoSuchElementException expected) {
            System.out.println("empty " + name + "=NoSuchElementException");
        }
    }

    public static void main(String[] args) {
        NavigableMap<Integer, String> levels = new TreeMap<>();
        levels.put(0, "basic");
        levels.put(50, "bronze");
        levels.put(100, "silver");
        levels.put(200, "gold");

        System.out.println("keys=" + levels.navigableKeySet());
        for (int query : new int[] {-5, 0, 35, 50, 135, 200, 250}) {
            printNeighbors(levels, query);
        }

        Integer reached = levels.floorKey(135);
        if (reached != null) {
            System.out.println("reached key=" + reached);
            System.out.println("reached value=" + levels.get(reached));
        }
        System.out.println("firstKey=" + levels.firstKey());
        System.out.println("lastKey=" + levels.lastKey());
        System.out.println("size after queries=" + levels.size());

        NavigableMap<Integer, String> descending = levels.descendingMap();
        System.out.println("descending keys=" + descending.navigableKeySet());
        printNeighbors(descending, 135);
        printNeighbors(descending, 100);

        NavigableMap<Integer, String> middle =
                levels.subMap(50, true, 200, false);
        System.out.println("middle keys=" + middle.navigableKeySet());
        System.out.println("middle floorKey(40)=" + middle.floorKey(40));
        System.out.println("middle ceilingKey(150)=" + middle.ceilingKey(150));

        NavigableMap<Integer, String> nullableValues = new TreeMap<>();
        nullableValues.put(10, null);
        Integer found = nullableValues.floorKey(10);
        System.out.println("null-value key=" + found);
        System.out.println("null-value value=" + nullableValues.get(found));
        System.out.println("null-value containsKey="
                + nullableValues.containsKey(found));

        NavigableMap<Integer, String> empty = new TreeMap<>();
        System.out.println("empty floorKey=" + empty.floorKey(10));
        System.out.println("empty ceilingKey=" + empty.ceilingKey(10));
        showEmptyEndpoint(empty, true);
        showEmptyEndpoint(empty, false);
    }
}
```

Biên dịch và chạy với JDK 17 hoặc mới hơn:

```shell
javac -encoding UTF-8 NavigableMapKeyQueries.java
java NavigableMapKeyQueries
```

Kết quả chính xác:

```text
keys=[0, 50, 100, 200]
-5 -> lower=null, floor=null, ceiling=0, higher=0
0 -> lower=null, floor=0, ceiling=0, higher=50
35 -> lower=0, floor=0, ceiling=50, higher=50
50 -> lower=0, floor=50, ceiling=50, higher=100
135 -> lower=100, floor=100, ceiling=200, higher=200
200 -> lower=100, floor=200, ceiling=200, higher=null
250 -> lower=200, floor=200, ceiling=null, higher=null
reached key=100
reached value=silver
firstKey=0
lastKey=200
size after queries=4
descending keys=[200, 100, 50, 0]
135 -> lower=200, floor=200, ceiling=100, higher=100
100 -> lower=200, floor=100, ceiling=100, higher=50
middle keys=[50, 100]
middle floorKey(40)=null
middle ceilingKey(150)=null
null-value key=10
null-value value=null
null-value containsKey=true
empty floorKey=null
empty ceilingKey=null
empty firstKey=NoSuchElementException
empty lastKey=NoSuchElementException
```

### Những điểm nên kiểm tra trong output

Số lượng ánh xạ sau mọi truy vấn vẫn là 4. Các phương thức trả khóa không xóa dữ liệu.

Khi mốc đúng 50 hoặc 200, hai phương thức cho phép bằng trả về chính mốc ấy. Khi mốc là 35 hoặc 135, cặp kết quả cùng phía trùng nhau vì không có khóa bằng mốc.

Ở hai phía ngoài dữ liệu, chỉ phía còn tồn tại khóa mới có kết quả. Ví dụ mốc -5 không có khóa thấp hơn, nhưng có khóa không nhỏ hơn là 0.

## 5. firstKey và lastKey: hai đầu không cần mốc truy vấn

`NavigableMap` còn kế thừa `firstKey()` và `lastKey()` từ `SortedMap`:

- `firstKey()`: khóa đầu tiên theo thứ tự map.
- `lastKey()`: khóa cuối cùng theo thứ tự map.
- Cả hai ném `NoSuchElementException` khi map rỗng.

Chúng không nhận đối số. Đừng suy từ quy tắc của `floorKey` rằng mọi truy vấn trả khóa đều báo rỗng bằng `null`. Xem [SortedMap.firstKey/lastKey](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/SortedMap.html).

Trong ví dụ thứ tự tự nhiên, hai đầu là 0 và 200. Với thứ tự đảo, hai đầu đổi theo thứ tự map. Chúng cũng chỉ đọc dữ liệu.

Nếu cần lấy và xóa ánh xạ đầu/cuối, API tương ứng trả entry là `pollFirstEntry()` hoặc `pollLastEntry()`. Không có phương thức `pollFirstKey()` trên giao diện `NavigableMap`.

## 6. Trả khóa khác với trả giá trị hoặc entry

Xét ánh xạ:

```text
100 -> silver
```

`floorKey(135)` trả 100. Sau đó `get(100)` mới trả `"silver"`.

Khi cần cả khóa và giá trị, một truy vấn entry có thể rõ ràng hơn. Ví dụ minh họa, giả sử `levels` là `NavigableMap<Integer, String>`:

```java
java.util.Map.Entry<Integer, String> entry = levels.floorEntry(135);
if (entry != null) {
    Integer threshold = entry.getKey();
    String levelName = entry.getValue();
    // Su dung ca nguong va ten hang.
}
```

Entry trả về từ các truy vấn điều hướng mô tả ánh xạ tại thời điểm lời gọi; nó không phải cách tự động theo dõi mọi thay đổi về sau. Tài liệu `NavigableMap` mô tả các entry này là ảnh chụp ánh xạ và không hỗ trợ sửa map qua `setValue`. Xem [hợp đồng entry của NavigableMap](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/NavigableMap.html).

Không cần ép mọi truy vấn về entry nếu chỉ dùng khóa. Hãy chọn dạng trả về phù hợp với dữ liệu mà nơi gọi thực sự cần.

## 7. Phân biệt hai kiểu null

### Không có khóa phù hợp

Với map không có khóa null, `floorKey(-5)` trả null nghĩa là không có khóa thỏa quan hệ tìm kiếm.

Cần kiểm tra trước khi tự động mở hộp:

```java
// levels la NavigableMap<Integer, String>.
Integer key = levels.floorKey(-5);
if (key != null) {
    int threshold = key;
    // Dung threshold.
}
```

Viết `int key = levels.floorKey(-5);` có thể ném `NullPointerException` do mở hộp null.

### Có khóa nhưng giá trị ánh xạ là null

Trong chương trình, map `nullableValues` chứa `10 -> null`. `floorKey(10)` vẫn trả 10 vì khóa có tồn tại; `get(10)` trả null vì đó là giá trị đã lưu.

Do đó, `get(key) == null` không luôn chứng minh khóa vắng mặt nếu map cho phép giá trị null. `containsKey` có thể phân biệt trong một trạng thái truy cập được kiểm soát. Xem [Map.get](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Map.html#get(java.lang.Object)).

Trong thiết kế cho phép khóa null qua một comparator thích hợp, kết quả trả khóa null còn có thể nhập nhằng với không tìm thấy. Để giữ ý nghĩa “null là không có kết quả” đơn giản, các ví dụ dùng khóa không null và `TreeMap` theo thứ tự tự nhiên.

Không áp dụng khả năng chứa giá trị null của `TreeMap` cho mọi triển khai khác của `NavigableMap`; phải xét hợp đồng lớp cụ thể.

## 8. Thứ tự đảo và phạm vi làm đổi kết quả

### Truy vấn trên descendingMap

Khung nhìn ngược của ví dụ có thứ tự khóa:

```text
200, 100, 50, 0
```

Với mốc 135:

- `floorKey(135)` trả 200.
- `ceilingKey(135)` trả 100.

Đây không phải lỗi: các quan hệ được xét theo comparator của map đang được gọi. Với mốc 100, `lowerKey(100)` là 200, còn `higherKey(100)` là 50.

Nếu mã nghiệp vụ cần “ngưỡng số học cao nhất đã đạt”, hãy bảo đảm map dùng thứ tự phù hợp. Không chuyển sang khung nhìn đảo rồi giữ nguyên cách diễn giải số học của tên phương thức. Xem [NavigableMap.descendingMap](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/NavigableMap.html).

### Truy vấn trên subMap

Trong chương trình:

```java
NavigableMap<Integer, String> middle =
        levels.subMap(50, true, 200, false);
```

Khung nhìn chỉ có khóa `[50, 100]`. Vì vậy:

- `middle.floorKey(40)` trả null; khóa 0 của map gốc nằm ngoài khung nhìn.
- `middle.ceilingKey(150)` trả null; khóa 200 bị loại bởi biên trên.

Truy vấn không tự vượt phạm vi để lấy khóa ở map gốc. Kết quả null ở một khung nhìn không chứng minh map gốc không có hàng xóm phù hợp.

## 9. Lưu ý khi dùng trong mã thực tế

### Khóa phải so sánh được

`TreeMap` sắp theo thứ tự tự nhiên hoặc comparator đã cấu hình. Mốc truy vấn cần hợp lệ với quy tắc ấy; các kiểu không so sánh được hoặc null không được hỗ trợ có thể gây ngoại lệ. Comparator cũng phải được thiết kế nhất quán với `equals` để tuân thủ đầy đủ hợp đồng map. Xem [TreeMap](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/TreeMap.html).

### Trả khóa không phải giữ chỗ hoặc khóa dữ liệu

Sau `K key = map.floorKey(x)`, map không cam kết khóa đó tiếp tục tồn tại mãi. Nếu có thay đổi xen giữa, lần `get(key)` về sau có thể đọc giá trị mới hoặc không còn ánh xạ.

`TreeMap` không tự đồng bộ. Mã nhiều luồng cần một giao thức truy cập phù hợp; việc thay truy vấn khóa bằng truy vấn entry cũng không biến `TreeMap` thành cấu trúc an toàn luồng.

### Không dùng truy vấn hàng xóm thay mọi cách duyệt

Các phương thức điều hướng diễn đạt việc định vị một khóa quanh mốc. Khi muốn duyệt toàn bộ khóa, thường dùng vòng lặp trên `navigableKeySet()` hoặc một khung nhìn khoảng sẽ rõ hơn việc liên tục gọi `higherKey`.

Tương tự, tìm khóa đúng bằng đầu vào là nhu cầu của `containsKey` hoặc `get`; `floorKey` tìm được một khóa không có nghĩa đầu vào đã tồn tại trong map.

## 10. Kiểm thử và thực hành

Bộ kiểm thử cần có mốc đúng bằng khóa, nằm giữa hai khóa, thấp hơn tất cả, cao hơn tất cả và map rỗng. Với thứ tự riêng hoặc khung nhìn bị giới hạn, phải có ca kiểm tra riêng cho chúng.

1. Với khóa `[10, 30, 60]`, tính bốn kết quả cho mốc 30 và 31 trước khi chạy.
2. Tạo map có khóa 30 ánh xạ tới null. Giải thích vì sao `floorKey(31)` vẫn có kết quả dù `get` trả null.
3. Lấy `subMap(10, false, 60, false)`, truy vấn `lowerKey(30)` và `higherKey(30)`. Đối chiếu với map gốc.
4. Viết hàm chọn ngưỡng theo yêu cầu “đã đạt”, sau đó đổi yêu cầu thành “mục tiêu cao hơn kế tiếp”. Giữ ca kiểm thử đúng bằng mốc để phát hiện dùng sai dấu bằng.
5. Với một `descendingMap`, viết ra thứ tự khóa trước rồi dự đoán kết quả. Giải thích bằng comparator, không chỉ bằng độ lớn số học.
