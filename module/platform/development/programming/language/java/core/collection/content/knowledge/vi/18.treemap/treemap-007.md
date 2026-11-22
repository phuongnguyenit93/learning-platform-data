# TreeMap: descendingMap, navigableKeySet và view đảo thứ tự

## 1. Một tập mapping có thể được nhìn theo nhiều chiều

Giả sử chương trình giữ các phiên bản tài liệu theo số thứ tự 10, 20, 30. Ta muốn tra theo số, xem từ cũ đến mới ở một màn hình và xem từ mới đến cũ ở màn hình khác. Không nhất thiết phải tạo hai map rồi tự đồng bộ mỗi khi dữ liệu thay đổi.

`TreeMap` đã giữ khóa theo một thứ tự xác định. **Khung nhìn (view)** cho phép thao tác với cùng dữ liệu qua một hướng hoặc một phạm vi khác. Hai API chính trong bài là:

- `descendingMap()`: view của cả mapping theo thứ tự đảo.
- `navigableKeySet()`: view của các khóa, có các phép tìm khóa lân cận và làm việc với hai đầu.

Hai API liên quan giúp nối các cách nhìn là `descendingKeySet()` trên map và `descendingSet()` trên `NavigableSet`. Chúng không tạo một kho dữ liệu độc lập chỉ vì kết quả có kiểu map hoặc set.

Với map dùng thứ tự tự nhiên của số nguyên:

```text
Dữ liệu gốc:                   10=A, 20=B, 30=C
map duyệt khóa:                10 → 20 → 30
map.descendingMap duyệt khóa:  30 → 20 → 10
map.navigableKeySet:           10 → 20 → 30
map.descendingKeySet:          30 → 20 → 10
```

Điều cần hiểu không chỉ là đảo chiều dòng in. Khi thao tác qua view đảo, **đầu/cuối, trước/sau, khóa lân cận và cận phạm vi đều phải được đọc theo thứ tự của view**. Khi xóa qua view sửa được, mapping trong map gốc cũng bị xóa.

Các ví dụ trong bài dùng Java 17 trở lên, chỉ dựa trên các API điều hướng đã có của `TreeMap` và `NavigableMap`.

## 2. Nhận diện đúng kiểu kết quả

| Lời gọi | Kiểu kết quả | Dữ liệu nhìn thấy | Thứ tự |
|---|---|---|---|
| `map.descendingMap()` | `NavigableMap<K,V>` | Cả khóa và giá trị | Đảo so với map nhận lời gọi |
| `map.navigableKeySet()` | `NavigableSet<K>` | Chỉ khóa | Cùng thứ tự với map |
| `map.descendingKeySet()` | `NavigableSet<K>` | Chỉ khóa | Đảo so với map |
| `keys.descendingSet()` | `NavigableSet<K>` | Các phần tử của set/view khóa | Đảo so với set nhận lời gọi |

`NavigableMap` mở rộng khả năng của map có thứ tự: ngoài tra chính xác theo khóa, nó còn tìm khóa hoặc entry ngay trước/sau một mốc. `NavigableSet` làm các phép tương tự trên phần tử đơn lẻ, nên ở view khóa, kết quả là khóa chứ không phải entry.

`keySet()` của `TreeMap` vẫn được duyệt có thứ tự. Khác biệt hữu ích của `navigableKeySet()` là kiểu trả về công bố các phương thức như `lower`, `floor`, `ceiling`, `higher`, `pollFirst` và `descendingSet`.

Đoạn sau chỉ minh họa bên trong một phương thức, không phải tệp Java độc lập:

```java
TreeMap<Integer, String> map = new TreeMap<>();
NavigableMap<Integer, String> down = map.descendingMap();
NavigableSet<Integer> keys = map.navigableKeySet();
NavigableSet<Integer> downKeys = map.descendingKeySet();
```

Không khai báo `TreeMap<Integer,String> down = map.descendingMap()`: API trả về `NavigableMap`, không hứa rằng view là một đối tượng `TreeMap` độc lập. Dùng đúng interface vừa đủ giúp thể hiện khả năng thật của kết quả.

## 3. “Giảm dần” là đảo thứ tự đang có

### 3.1. Không cố định là số lớn đến số nhỏ

`TreeMap` có thể dùng thứ tự tự nhiên hoặc một comparator riêng. `descendingMap()` đảo **thứ tự của map hiện tại**, không áp đặt một quy tắc chung cho mọi kiểu khóa.

Nếu map gốc theo thứ tự số tăng dần, view đảo đi từ lớn xuống nhỏ. Nhưng nếu map gốc đã được tạo với comparator số giảm dần, view đảo của nó lại đi từ nhỏ lên lớn. Với khóa phức hợp, thứ tự đảo cũng dựa trên comparator của khóa đó.

Do đó, trong bài các phát biểu “khóa lớn nhất” và “khóa nhỏ nhất theo giá trị số” chỉ được áp dụng khi đã nêu rõ map gốc dùng thứ tự tự nhiên của số nguyên. Trong trường hợp tổng quát, hãy nói đầu/cuối hoặc trước/sau theo comparator.

Tài liệu [NavigableMap — Java 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/NavigableMap.html) mô tả view đảo có thứ tự ngược với map gốc. Đảo hai lần cho một view có ý nghĩa tương đương map ban đầu; không cần dùng danh tính đối tượng `==` để định nghĩa tính chất này.

### 3.2. Đảo chiều không thay mapping hoặc tạo nhóm khóa mới

View vẫn chứa cùng các cặp khóa–giá trị. `get(key)` không trả một giá trị khác chỉ vì đang dùng chiều đảo. Các nhóm khóa tương đương theo so sánh cũng không bị tách thành khóa mới: đảo thứ tự giữ nguyên quan hệ so sánh bằng 0.

`down.put(key, value)` thêm hoặc cập nhật mapping trong map gốc. Vị trí duyệt sau đó được quyết định bởi thứ tự khóa, không phải vị trí thực hiện lời gọi hay việc map được gọi là “down”. Không thể thêm một khóa số 25 vào đầu tùy ý của một TreeMap tự nhiên vốn có 10, 20, 30; khóa đó nằm giữa 20 và 30 trong chiều gốc.

`down.values()` và `down.entrySet()` duyệt theo thứ tự khóa của view đảo. Đó không phải việc sắp giá trị V theo một comparator mới.

## 4. View đảo được liên kết hai chiều với map gốc

### 4.1. Thay đổi ở một đường nhìn thấy ở đường còn lại

Với `TreeMap` sửa được thông thường, các thao tác trên `descendingMap()` tác động đến cùng dữ liệu:

| Thao tác | Ảnh hưởng đến map gốc |
|---|---|
| `down.put(k, v)` | Thêm hoặc cập nhật mapping k |
| `down.remove(k)` | Loại mapping k nếu có |
| `down.clear()` khi down là view đảo toàn map | Xóa toàn bộ mapping của map gốc |
| `down.pollFirstEntry()` | Loại entry đầu view, tức cuối gốc |
| `down.pollLastEntry()` | Loại entry cuối view, tức đầu gốc |

Ngược lại, thêm hoặc loại mapping qua map gốc lập tức được phản ánh khi quan sát view. Không có thao tác “làm mới view” riêng phải gọi sau mỗi put.

### 4.2. Xem hai đầu và lấy ra là hai việc khác nhau

`firstKey()`/`lastKey()` chỉ xem khóa đầu/cuối, không loại mapping. `firstEntry()`/`lastEntry()` xem cả mapping ở hai đầu. Các phương thức có `poll` vừa lấy kết quả vừa loại mapping.

Trong map gốc có khóa `[10, 20, 30]`, view đảo là `[30, 20, 10]`. `down.firstKey()` là 30; `down.pollFirstEntry()` lấy entry 30 và khiến map gốc không còn khóa 30. Nếu chỉ muốn hiển thị mục đầu tiên, dùng phép xem để tránh xóa ngoài ý định.

## 5. Chương trình 1: thao tác qua hai chiều

Lưu chương trình đầy đủ vào `TreeMapDescendingViewDemo.java`. Map gốc dùng thứ tự tự nhiên của `Integer`.

```java
import java.util.NavigableMap;
import java.util.TreeMap;

public class TreeMapDescendingViewDemo {
    public static void main(String[] args) {
        TreeMap<Integer, String> map = new TreeMap<>();
        map.put(10, "A");
        map.put(20, "B");
        map.put(30, "C");
        NavigableMap<Integer, String> down = map.descendingMap();
        System.out.println("original=" + map);
        System.out.println("descending=" + down);
        System.out.println("descendingEnds=" + down.firstKey() + "," + down.lastKey());
        down.put(25, "X");
        down.remove(10);
        map.put(5, "D");
        System.out.println("sharedOriginal=" + map);
        System.out.println("sharedDescending=" + down);
        System.out.println("lookup20=" + down.get(20));
        System.out.println("descendingPollFirst=" + down.pollFirstEntry());
        System.out.println("descendingPollLast=" + down.pollLastEntry());
        System.out.println("remainingOriginal=" + map);
        System.out.println("remainingDescending=" + down);
        System.out.println("twiceDescending=" + down.descendingMap().navigableKeySet());
        System.out.println("equalMappings=" + map.equals(down));
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 TreeMapDescendingViewDemo.java
java TreeMapDescendingViewDemo
```

Stdout:

```text
original={10=A, 20=B, 30=C}
descending={30=C, 20=B, 10=A}
descendingEnds=30,10
sharedOriginal={5=D, 20=B, 25=X, 30=C}
sharedDescending={30=C, 25=X, 20=B, 5=D}
lookup20=B
descendingPollFirst=30=C
descendingPollLast=5=D
remainingOriginal={20=B, 25=X}
remainingDescending={25=X, 20=B}
twiceDescending=[20, 25]
equalMappings=true
```

### 5.1. Thêm theo vị trí sắp thứ tự, không theo thời điểm chèn

Ban đầu gốc là `{10=A, 20=B, 30=C}`, view là `{30=C, 20=B, 10=A}`. Gọi `down.put(25, "X")` thêm 25 vào vị trí phù hợp trong cùng cây. `down.remove(10)` loại 10 khỏi gốc. Gọi `map.put(5, "D")` thêm 5 qua gốc và view cũng nhìn thấy nó.

Vì vậy gốc trở thành `[5, 20, 25, 30]`, view trở thành `[30, 25, 20, 5]`. `lookup20=B` xác nhận tra theo khóa không bị đổi ý nghĩa giá trị.

### 5.2. Poll trên view đảo lấy đầu nào của gốc?

`descendingPollFirst=30=C` loại khóa lớn nhất theo thứ tự tự nhiên đang xét. Sau đó `descendingPollLast=5=D` loại khóa nhỏ nhất. Map gốc còn `[20, 25]`, view còn `[25, 20]`.

`twiceDescending=[20, 25]` quay về cùng chiều gốc. `equalMappings=true` không có nghĩa hai chiều duyệt giống nhau: phép bằng nhau của map xét các mapping, không xét thứ tự duyệt. Khi cần kiểm tra thứ tự, hãy quan sát một danh sách khóa theo thứ tự, không chỉ dùng `Map.equals`.

## 6. Các phép tìm lân cận đổi nghĩa theo chiều

### 6.1. Ý nghĩa của lower, floor, ceiling, higher

Các phép điều hướng dùng thứ tự của **đối tượng nhận lời gọi**:

| Trên map | Trên view khóa | Ý nghĩa theo thứ tự của đối tượng |
|---|---|---|
| `lowerKey(x)` | `lower(x)` | Khóa gần nhất ở trước x, không nhận khóa tương đương x |
| `floorKey(x)` | `floor(x)` | Khóa gần nhất ở trước hoặc tương đương x |
| `ceilingKey(x)` | `ceiling(x)` | Khóa gần nhất ở sau hoặc tương đương x |
| `higherKey(x)` | `higher(x)` | Khóa gần nhất ở sau x, không nhận khóa tương đương x |

“Gần nhất” ở đây là gần theo thứ tự, không phải tối thiểu hóa một khoảng cách số học bất kỳ. Với khóa không phải số, không cần có khái niệm trừ hai khóa để tính khoảng cách.

Với gốc tự nhiên có `[10, 20, 30, 40]`, mốc 25 cho:

| Phép tìm | Gốc tăng dần | View giảm dần |
|---|---|---|
| lower | 20 | 30 |
| floor | 20 | 30 |
| ceiling | 30 | 20 |
| higher | 30 | 20 |

Trong chiều giảm, 30 đứng trước 25, còn 20 đứng sau 25. Vì thế `down.lowerKey(25)` trả 30 dù 30 lớn hơn 25 về giá trị số.

### 6.2. Cặp phép tương ứng giữa gốc và đảo

Với `down = map.descendingMap()`, có thể đối chiếu:

```text
down.lowerKey(x)   ↔ map.higherKey(x)
down.floorKey(x)   ↔ map.ceilingKey(x)
down.ceilingKey(x) ↔ map.floorKey(x)
down.higherKey(x)  ↔ map.lowerKey(x)
```

Các phép trả entry tương ứng cũng đổi chiều theo cách đó. `floor` và `ceiling` vẫn bao gồm trường hợp khóa tương đương x; `lower` và `higher` vẫn loại trường hợp bằng. Không đổi cờ “có nhận bằng” chỉ vì đổi hướng.

## 7. Chương trình 2: điều hướng và cận phạm vi trong chiều đảo

Lưu vào `TreeMapDescendingNavigationDemo.java`. Các truy vấn gồm mốc có thật, mốc nằm giữa và mốc nằm ngoài tập khóa.

```java
import java.util.List;
import java.util.NavigableMap;
import java.util.TreeMap;

public class TreeMapDescendingNavigationDemo {
    private static void show(String label, NavigableMap<Integer, String> map, int key) {
        System.out.println(label + "(" + key + "): lower=" + map.lowerKey(key)
                + ", floor=" + map.floorKey(key)
                + ", ceiling=" + map.ceilingKey(key)
                + ", higher=" + map.higherKey(key));
    }

    public static void main(String[] args) {
        TreeMap<Integer, String> map = new TreeMap<>();
        for (int key : List.of(10, 20, 30, 40)) {
            map.put(key, "v" + key);
        }
        NavigableMap<Integer, String> down = map.descendingMap();
        for (int query : List.of(25, 20, 5, 45)) {
            show("original", map, query);
            show("descending", down, query);
        }
        System.out.println("descendingRange="
                + down.subMap(40, true, 20, false).navigableKeySet());
        System.out.println("descendingHead=" + down.headMap(30, false).navigableKeySet());
        System.out.println("descendingTail=" + down.tailMap(30, true).navigableKeySet());
        try {
            down.subMap(10, true, 40, true);
            throw new AssertionError("Expected IllegalArgumentException");
        } catch (IllegalArgumentException expected) {
            System.out.println("wrongBoundOrder=IllegalArgumentException");
        }
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 TreeMapDescendingNavigationDemo.java
java TreeMapDescendingNavigationDemo
```

Stdout:

```text
original(25): lower=20, floor=20, ceiling=30, higher=30
descending(25): lower=30, floor=30, ceiling=20, higher=20
original(20): lower=10, floor=20, ceiling=20, higher=30
descending(20): lower=30, floor=20, ceiling=20, higher=10
original(5): lower=null, floor=null, ceiling=10, higher=10
descending(5): lower=10, floor=10, ceiling=null, higher=null
original(45): lower=40, floor=40, ceiling=null, higher=null
descending(45): lower=null, floor=null, ceiling=40, higher=40
descendingRange=[40, 30]
descendingHead=[40]
descendingTail=[30, 20, 10]
wrongBoundOrder=IllegalArgumentException
```

### 7.1. Có khóa bằng mốc và không có kết quả

Tại mốc 20, cả floor và ceiling đều có thể trả 20. Lower/higher phải tìm một khóa khác: ở gốc là 10/30, còn ở chiều đảo là 30/10.

Mốc 5 và 45 cho thấy `null` khi không có ứng viên theo hướng cần tìm. Ví dụ ở chiều giảm, 5 nằm sau mọi khóa đang có, nên không có khóa ceiling/higher của 5; lower/floor là 10. Kết quả không có ứng viên không làm map thay đổi.

### 7.2. from và to cũng theo comparator của view

`down.subMap(40, true, 20, false)` lấy từ 40 đến trước 20 theo chiều giảm, nên có `[40, 30]`. Cờ `true` nhận 40; cờ `false` loại 20.

`down.headMap(30, false)` lấy phần đứng trước 30 trong chiều giảm, tức `[40]`. `down.tailMap(30, true)` lấy từ 30 về sau, tức `[30, 20, 10]`.

`down.subMap(10, true, 40, true)` sai thứ tự cận vì 10 đứng sau 40 trong comparator của view. Nó ném `IllegalArgumentException`. Không dùng quy tắc “số nhỏ viết trước” để đặt cận cho mọi view.

### 7.3. Khi chuyển một phạm vi sang chiều đảo

Nếu muốn cùng tập khóa thuộc `(20, 40]` của gốc tự nhiên, ta có thể nhìn bằng gốc `subMap(20, false, 40, true)` hoặc view đảo `subMap(40, true, 20, false)`. Hai cách chứa cùng mapping nhưng duyệt ngược nhau.

Khi đổi cận đầu/cuối, cần mang theo đúng cờ bao gồm của từng **giá trị cận**: cận 40 vẫn được nhận, cận 20 vẫn bị loại. Chỉ đảo hai số mà giữ cờ theo vị trí cũ có thể tạo ra một tập khóa khác.

## 8. navigableKeySet: view khóa có khả năng điều hướng

### 8.1. Ba đường nhìn khóa theo chiều đảo

Với map có khóa 10, 20, 30, các lời gọi sau cho cùng thứ tự khóa đảo:

```java
// Minh họa bên trong một phương thức đã có biến map.
map.descendingKeySet();
map.navigableKeySet().descendingSet();
map.descendingMap().navigableKeySet();
```

Chúng đều nhìn khóa theo chiều 30, 20, 10 và đều liên quan đến cùng map. Không nên dùng việc chúng có phải cùng đối tượng `==` hay không để quyết định xem thay đổi có truyền qua map gốc hay không. Hợp đồng view mới là điều cần dựa vào.

`downKeys.first()` nhìn phần tử đầu theo comparator của downKeys, nên trong ví dụ số tự nhiên đó là 30. Các phương thức `lower/floor/ceiling/higher` của set cũng dùng chiều của chính set, giống quy tắc đã thấy trên map.

### 8.2. Xóa khóa từ view là xóa cả mapping

View khóa không chỉ là một tập số độc lập. Trên view khóa của `TreeMap`, các thao tác loại phần tử được hỗ trợ:

| Thao tác trên view khóa | Ảnh hưởng |
|---|---|
| `remove(k)` | Loại mapping của k nếu có trong view |
| `pollFirst()` | Lấy khóa đầu và loại mapping tương ứng |
| `pollLast()` | Lấy khóa cuối và loại mapping tương ứng |
| `iterator.remove()` sau `next()` hợp lệ | Loại mapping của khóa iterator vừa trả |
| `clear()` | Loại toàn bộ mapping mà view khóa đang nhìn thấy |

Nếu view khóa đến từ toàn map, clear làm rỗng map. Nếu nó đến từ một map phạm vi, clear chỉ loại các mapping đang thuộc phạm vi đó. Tính chất liên kết vẫn có hiệu lực qua nhiều lớp view.

Tài liệu [TreeMap — Java 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeMap.html) nêu rõ view khóa liên kết với map và hỗ trợ loại phần tử. Truyền một view khóa cho nơi khác có thể trao cho nơi đó khả năng xóa mapping, dù kiểu dữ liệu họ nhận chỉ là một set.

### 8.3. Không thể thêm khóa qua add

`keys.add(k)` và `keys.addAll(...)` không được hỗ trợ trên view khóa của map; chúng ném `UnsupportedOperationException`. Một khóa riêng lẻ không cung cấp giá trị V cho mapping mới. Muốn thêm mapping, hãy dùng `put` trên map với cả khóa và giá trị.

Vì vậy, “map sửa được” không đồng nghĩa “mọi phương thức sửa của mọi view đều chạy được”. View khóa cho phép loại mapping nhưng không cho thêm mapping bằng `add`. `NavigableSet` chỉ là kiểu API; khả năng thao tác cụ thể còn phụ thuộc cách triển khai và nguồn tạo view.

### 8.4. Phân biệt rỗng với không có ứng viên

| Lời gọi trên kiểu đang xét | Khi rỗng hoặc không có kết quả |
|---|---|
| `keys.first()` / `keys.last()` | Ném `NoSuchElementException` nếu set rỗng |
| `keys.pollFirst()` / `keys.pollLast()` | Trả `null` nếu set rỗng |
| `keys.lower/floor/ceiling/higher(x)` | Trả `null` nếu không có ứng viên |
| `map.firstKey()` / `map.lastKey()` | Ném `NoSuchElementException` nếu map rỗng |
| `map.firstEntry()` / `map.lastEntry()` | Trả entry `null` nếu map rỗng |
| `map.pollFirstEntry()` / `map.pollLastEntry()` | Trả entry `null` nếu map rỗng |

Đừng áp dụng quy tắc rỗng của một phương thức sang một phương thức khác chỉ vì chúng cùng nói đến đầu/cuối. Hợp đồng `NavigableSet` được mô tả tại [NavigableSet — Java 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/NavigableSet.html).

## 9. Chương trình 3: view khóa, iterator và trường hợp null

Lưu chương trình đầy đủ vào `TreeMapNavigableKeysDemo.java`. Các ngoại lệ được bắt có chủ đích để in ra hành vi cần quan sát.

```java
import java.util.Comparator;
import java.util.Iterator;
import java.util.Map;
import java.util.NavigableSet;
import java.util.NoSuchElementException;
import java.util.TreeMap;

public class TreeMapNavigableKeysDemo {
    public static void main(String[] args) {
        TreeMap<Integer, String> map = new TreeMap<>();
        map.put(10, "A");
        map.put(20, "B");
        map.put(30, "C");
        NavigableSet<Integer> keys = map.navigableKeySet();
        NavigableSet<Integer> downKeys = map.descendingKeySet();
        System.out.println("keys=" + keys);
        System.out.println("descendingKeys=" + downKeys);
        System.out.println("descendingSet=" + keys.descendingSet());
        System.out.println("keysFromDescendingMap="
                + map.descendingMap().navigableKeySet());
        System.out.println("descendingEnds=" + downKeys.first() + "," + downKeys.last());
        System.out.println("lower25=" + keys.lower(25) + "," + downKeys.lower(25));
        try {
            keys.add(15);
            throw new AssertionError("Expected UnsupportedOperationException");
        } catch (UnsupportedOperationException expected) {
            System.out.println("addKey=UnsupportedOperationException");
        }
        System.out.println("descendingPollFirst=" + downKeys.pollFirst());
        System.out.println("remove10=" + keys.remove(10));
        System.out.println("afterKeyRemovals=" + map);
        map.put(25, "X");
        System.out.println("sameKeyViews=" + keys + "," + downKeys);
        Iterator<Integer> iterator = downKeys.iterator();
        System.out.println("iteratorNext=" + iterator.next());
        iterator.remove();
        System.out.println("afterIteratorRemove=" + map);
        keys.clear();
        System.out.println("emptyMap=" + map.isEmpty());
        System.out.println("emptyPoll=" + keys.pollFirst());
        try {
            keys.first();
            throw new AssertionError("Expected NoSuchElementException");
        } catch (NoSuchElementException expected) {
            System.out.println("emptyFirst=NoSuchElementException");
        }
        TreeMap<Integer, String> nullable =
                new TreeMap<>(Comparator.nullsFirst(Comparator.naturalOrder()));
        nullable.put(null, "nil");
        nullable.put(10, "ten");
        System.out.println("nullableFirst=" + nullable.navigableKeySet().first());
        System.out.println("nullablePolledKey=" + nullable.navigableKeySet().pollFirst());
        System.out.println("nullableSizeAfterPoll=" + nullable.size());
        nullable.put(null, "nil-again");
        Map.Entry<Integer, String> entry = nullable.descendingMap().pollLastEntry();
        System.out.println("nullablePolledEntry=" + entry);
        System.out.println("nullableEntryExists=" + (entry != null));
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 TreeMapNavigableKeysDemo.java
java TreeMapNavigableKeysDemo
```

Stdout:

```text
keys=[10, 20, 30]
descendingKeys=[30, 20, 10]
descendingSet=[30, 20, 10]
keysFromDescendingMap=[30, 20, 10]
descendingEnds=30,10
lower25=20,30
addKey=UnsupportedOperationException
descendingPollFirst=30
remove10=true
afterKeyRemovals={20=B}
sameKeyViews=[20, 25],[25, 20]
iteratorNext=25
afterIteratorRemove={20=B}
emptyMap=true
emptyPoll=null
emptyFirst=NoSuchElementException
nullableFirst=null
nullablePolledKey=null
nullableSizeAfterPoll=1
nullablePolledEntry=null=nil-again
nullableEntryExists=true
```

### 9.1. Các đường đảo cùng nhìn thấy một thứ tự

Ba dòng `descendingKeys`, `descendingSet`, `keysFromDescendingMap` đều là `[30, 20, 10]`. Trong khi đó `keys` là `[10, 20, 30]`. `lower25=20,30` ghi kết quả trên view cùng chiều và view đảo: hướng điều hướng thay đổi theo chiều của view.

Lệnh `keys.add(15)` bị từ chối. Sau đó `downKeys.pollFirst()` lấy 30 ra và loại mapping 30=C. `keys.remove(10)` loại mapping 10=A. Map gốc chỉ còn 20=B.

### 9.2. Một view đã tạo vẫn phản ánh thay đổi mới

Khi thêm 25=X qua map gốc, chính các biến view cũ nhìn thấy `[20, 25]` và `[25, 20]`. Chúng không giữ riêng ba khóa tại thời điểm khởi tạo.

Iterator được tạo từ `downKeys` trả 25 trước. Gọi `iterator.remove()` đúng sau lần `next()` đó loại 25 khỏi map; gốc còn 20=B. Đây là đường xóa được iterator hỗ trợ, không phải một lệnh `map.remove` bên ngoài iterator đang hoạt động.

`keys.clear()` sau đó làm map rỗng. `pollFirst()` trả `null`, còn `first()` ném `NoSuchElementException`, đúng hai hợp đồng khác nhau.

### 9.3. Khóa null làm kết quả chỉ trả khóa có thể nhập nhằng

Map `nullable` dùng comparator cho phép khóa `null` và đặt nó đầu thứ tự gốc. Khi map đang có null và 10, `first()` trả khóa `null` hợp lệ. `pollFirst()` cũng trả `null`, nhưng lần này nó **đã loại một mapping**, được chứng minh bằng `nullableSizeAfterPoll=1`.

Do đó không thể luôn suy ra “poll trả null nghĩa là trước đó rỗng” nếu chính cấu trúc cho phép phần tử null. Quy tắc thông thường chỉ không nhập nhằng khi miền khóa không có null.

Ví dụ cuối chuyển sang `pollLastEntry()` trên view đảo. Entry có khóa null nằm cuối chiều đảo, nên được lấy ra. Dòng `nullablePolledEntry=null=nil-again` mô tả một đối tượng entry có thật chứa khóa null, và `nullableEntryExists=true` xác nhận đối tượng kết quả không phải null.

Khi cần phân biệt “không có mapping” với “có mapping mang khóa null”, API trả cả entry thường giúp thể hiện rõ hơn API chỉ trả khóa. Nó không yêu cầu giá trị bên trong entry phải khác null.

## 10. View phạm vi vẫn dùng chung dữ liệu

### 10.1. Phạm vi là điều kiện cận, không phải danh sách khóa được chụp lại

`down.subMap(40, true, 20, false)` không chụp riêng các khóa đang có lúc gọi. Nó xác định một cửa nhìn chứa các khóa trong phạm vi đã chọn, theo comparator đảo. Khi map gốc được thêm khóa mới nằm trong phạm vi, khóa đó xuất hiện trong view.

Ngược lại, khóa nằm ngoài phạm vi không xuất hiện dù vẫn tồn tại trong map gốc. Lệnh ghi một khóa ngoài phạm vi qua view sẽ bị từ chối bằng `IllegalArgumentException`; việc map gốc có khả năng chứa khóa đó không nới cận của view.

Loại entry đang đúng cận không làm cận thay đổi. Sau khi mapping 40 bị xóa, view vẫn có cận 40 và vẫn có thể nhìn thấy khóa 35 được thêm về sau. Không hiểu cận phạm vi như “khóa lớn nhất đang còn trong view”.

### 10.2. clear qua phạm vi chỉ xóa phần đang nhìn thấy

Giả sử gốc có 10, 20, 25, 30, 35, còn view phạm vi nhìn 35, 30, 25. `range.clear()` loại đúng các mapping 25, 30, 35 khỏi gốc. Các khóa 10 và 20 còn lại vì nằm ngoài phạm vi, trong đó 20 bị loại bởi cờ cận không bao gồm.

Việc xóa qua phạm vi và qua view đảo không cần chạy thêm một vòng xóa trên map gốc. Nhưng cũng vì vậy, không được coi range như một bản sao có thể dọn bỏ tự do mà không ảnh hưởng chủ sở hữu map.

## 11. Chương trình 4: bản sao, kiểu constructor và phạm vi sống

Lưu vào `TreeMapViewCopyRangeDemo.java`. Ví dụ tạo cả view liên kết lẫn các cấu trúc sao chép để quan sát sự khác nhau sau khi thay đổi.

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.NavigableMap;
import java.util.TreeMap;

public class TreeMapViewCopyRangeDemo {
    public static void main(String[] args) {
        TreeMap<Integer, String> map = new TreeMap<>();
        map.put(10, "A");
        map.put(20, "B");
        map.put(30, "C");
        map.put(40, "D");
        NavigableMap<Integer, String> down = map.descendingMap();
        TreeMap<Integer, String> descendingCopy = new TreeMap<>(down);
        Map<Integer, String> generalMap = down;
        TreeMap<Integer, String> naturalCopy = new TreeMap<>(generalMap);
        List<Integer> keySnapshot = new ArrayList<>(down.navigableKeySet());
        System.out.println("descendingCopyKeys=" + descendingCopy.keySet());
        System.out.println("naturalCopyKeys=" + naturalCopy.keySet());
        System.out.println("keySnapshot=" + keySnapshot);
        NavigableMap<Integer, String> range = down.subMap(40, true, 20, false);
        System.out.println("initialRange=" + range);
        range.put(30, "C2");
        range.remove(40);
        map.put(35, "new");
        range.put(25, "X");
        System.out.println("sharedRange=" + range);
        System.out.println("sharedOriginal=" + map);
        try {
            range.put(10, "outside");
            throw new AssertionError("Expected IllegalArgumentException");
        } catch (IllegalArgumentException expected) {
            System.out.println("outsideRangePut=IllegalArgumentException");
        }
        System.out.println("unchanged10=" + map.get(10));
        range.clear();
        System.out.println("afterRangeClear=" + map);
        System.out.println("sameDescendingView=" + down);
        System.out.println("independentDescendingCopy=" + descendingCopy);
        System.out.println("independentNaturalCopy=" + naturalCopy);
        System.out.println("independentKeySnapshot=" + keySnapshot);
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 TreeMapViewCopyRangeDemo.java
java TreeMapViewCopyRangeDemo
```

Stdout:

```text
descendingCopyKeys=[40, 30, 20, 10]
naturalCopyKeys=[10, 20, 30, 40]
keySnapshot=[40, 30, 20, 10]
initialRange={40=D, 30=C}
sharedRange={35=new, 30=C2, 25=X}
sharedOriginal={10=A, 20=B, 25=X, 30=C2, 35=new}
outsideRangePut=IllegalArgumentException
unchanged10=A
afterRangeClear={10=A, 20=B}
sameDescendingView={20=B, 10=A}
independentDescendingCopy={40=D, 30=C, 20=B, 10=A}
independentNaturalCopy={10=A, 20=B, 30=C, 40=D}
independentKeySnapshot=[40, 30, 20, 10]
```

### 11.1. Cùng đối tượng đầu vào, hai constructor có hợp đồng thứ tự khác

`down` được khai báo là `NavigableMap`, vốn cũng là `SortedMap`. Vì vậy `new TreeMap<>(down)` chọn constructor nhận `SortedMap` và giữ cùng quy tắc thứ tự của down. `descendingCopyKeys` là `[40, 30, 20, 10]`.

`generalMap` trỏ đến chính view đó nhưng được khai báo là `Map`. Lời gọi `new TreeMap<>(generalMap)` chọn constructor nhận `Map`, tạo TreeMap theo **thứ tự tự nhiên**. Kết quả `naturalCopyKeys` là `[10, 20, 30, 40]`.

Lựa chọn overload của constructor diễn ra theo kiểu mà trình biên dịch nhìn thấy tại lời gọi, không tự đổi sang overload SortedMap chỉ vì đối tượng thực tế lúc chạy có khả năng đó. Đây là lý do một thay đổi nhỏ về kiểu biến hoặc chữ ký hàm có thể làm cách sao chép thứ tự thay đổi.

Các hợp đồng constructor này được mô tả trong [TreeMap — Constructor Details](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeMap.html). Với khóa chỉ so được bằng comparator riêng mà không có thứ tự tự nhiên, chọn nhầm constructor nhận Map còn có thể gây lỗi, không chỉ đổi chiều.

### 11.2. Danh sách khóa là một bản chụp cấu trúc riêng

`new ArrayList<>(down.navigableKeySet())` tạo danh sách mới theo thứ tự duyệt của view tại thời điểm tạo: `[40, 30, 20, 10]`. Thêm hoặc xóa khóa trong map sau đó không tự cập nhật danh sách này.

Danh sách chỉ giữ khóa, không giữ các mapping. Hai bản sao TreeMap giữ cả mapping, nhưng được sắp theo comparator riêng đã chọn khi tạo. Vì vậy, “chụp dữ liệu theo chiều đảo” có thể là một danh sách khóa hoặc một map mới; cần chọn đúng kiểu kết quả mà công việc tiếp theo cần.

### 11.3. Ghi qua range và ghi qua gốc đều được phản ánh

`range` ban đầu có `{40=D, 30=C}`. Sau các thao tác:

- `range.put(30, "C2")` cập nhật 30 trong map gốc.
- `range.remove(40)` loại 40 trong map gốc.
- `map.put(35, "new")` làm 35 xuất hiện trong range vì nằm giữa các cận.
- `range.put(25, "X")` thêm 25 vào gốc và vào range.

Range lúc này là `{35=new, 30=C2, 25=X}`. Cận vẫn là từ 40 có nhận đến 20 không nhận. Lời gọi `range.put(10, "outside")` bị từ chối, và `unchanged10=A` xác nhận mapping 10 của gốc không bị thay giá trị.

Sau `range.clear()`, gốc còn `{10=A, 20=B}`, view đảo còn `{20=B, 10=A}`. Hai bản sao TreeMap và danh sách khóa vẫn giữ dữ liệu lúc được tạo. Chúng độc lập về cấu trúc với gốc, trong khi down và range tiếp tục theo dõi dữ liệu hiện tại.

### 11.4. Sao chép nông không phải sao chép sâu

Các constructor copy và ArrayList ở đây tạo cấu trúc chứa mới, nhưng không nhân bản sâu từng đối tượng khóa hoặc giá trị. Ví dụ dùng `Integer` và `String`, nên không có thao tác sửa đối tượng giá trị tại chỗ làm kết quả khó quan sát.

Nếu giá trị là một đối tượng có thể thay đổi, map gốc và bản sao có thể cùng giữ tham chiếu đến nó. Sửa đối tượng đó qua một tham chiếu vẫn có thể được quan sát ở cả hai. Tương tự, phải giữ ổn định các thành phần khóa mà comparator dùng; sao chép một map không làm khóa có thể thay đổi tự trở nên an toàn.

Bản sao cũng không mặc nhiên chỉ đọc. Tính độc lập về cấu trúc, quyền sửa cấu trúc và việc chia sẻ tham chiếu đối tượng là ba câu hỏi riêng.

## 12. Duyệt an toàn và chọn đúng quyền thay đổi

### 12.1. Duyệt ngược không bắt buộc sao chép

Nếu chỉ cần đi qua các khóa theo chiều ngược, có thể dùng `descendingKeySet()` trong vòng lặp hoặc lấy `map.navigableKeySet().descendingIterator()`. `descendingIterator()` có hiệu ứng duyệt theo chiều của `descendingSet().iterator()`.

Nếu cần cả khóa lẫn giá trị, duyệt `map.descendingMap().entrySet()` sẽ đọc được cả hai từ entry. Không nhất thiết tạo danh sách khóa đảo rồi tra lại từng khóa chỉ để lấy giá trị, trừ khi bản sao danh sách phục vụ một mục đích riêng.

Đoạn sau minh họa một lượt duyệt đọc, đặt trong phương thức đã có `map`, không phải chương trình độc lập:

```java
for (Map.Entry<Integer, String> entry : map.descendingMap().entrySet()) {
    System.out.println(entry.getKey() + ":" + entry.getValue());
}
```

Lượt duyệt này không tự loại mapping. Nếu muốn lấy dần và loại các mapping theo chiều đảo trong một luồng, có thể gọi `pollFirstEntry()` trên view và kiểm tra đối tượng entry trả về. Cần xác định rõ việc lấy ra trước khi xử lý có phù hợp với trường hợp xử lý thất bại hay không; bản thân TreeMap không cung cấp giao dịch cho công việc phía sau.

### 12.2. Thay đổi qua một view cũng ảnh hưởng iterator ở view khác

Map gốc, view đảo và các view khóa không có ba bản dữ liệu tách biệt. Nếu đang duyệt một view rồi thêm/xóa mapping qua một đường khác, iterator có thể bị ảnh hưởng bởi thay đổi cấu trúc của cùng map.

`TreeMap` có iterator fail-fast, có thể báo `ConcurrentModificationException` khi phát hiện kiểu thay đổi đó. Đây là cơ chế phát hiện lỗi theo nỗ lực, không phải một bảo đảm phối hợp truy cập và cũng không phải cơ chế chỉ dành cho nhiều luồng. Một luồng tự sửa map ngoài iterator của nó vẫn có thể gặp vấn đề.

Khi cần xóa khóa đang duyệt, dùng `iterator.remove()` theo đúng vòng đời `next`/`remove`, như chương trình 3. Không viết một vòng for-each trên downKeys rồi tự gọi `map.remove(key)` và cho rằng đổi biến nhận lời gọi đã tách việc xóa khỏi cấu trúc đang duyệt.

Nếu cần tạo một kế hoạch thay đổi rồi mới áp dụng, có thể thu thập các khóa vào một danh sách riêng trước. Điều đó tách cấu trúc duyệt danh sách khỏi cấu trúc map; nó không tự làm cả quy trình trở thành nguyên tử khi có luồng khác cùng thay đổi dữ liệu.

### 12.3. View không tạo quyền chỉ đọc hoặc khả năng đồng thời

`descendingMap()` tự nó không biến map thành chỉ đọc. `navigableKeySet()` cũng không phải một bản công bố khóa vô hại nếu bên nhận được phép gọi `remove` hoặc `clear`. Khi thiết kế API trả dữ liệu, cần chọn rõ có muốn cho phép bên nhận thay đổi nguồn qua kết quả hay không.

Một lớp bọc chỉ đọc thích hợp có thể ngăn thay đổi qua chính lớp bọc, nhưng khái niệm chỉ đọc vẫn khác với bản chụp độc lập: thay đổi từ chủ sở hữu map gốc có thể tiếp tục được nhìn thấy qua các view. Khi cần dữ liệu tách biệt về cấu trúc, phải tạo cấu trúc mới như ví dụ copy.

`TreeMap` không tự đồng bộ cho truy cập đồng thời; các view của nó cũng không thêm sự đồng bộ. Một chuỗi `firstKey()` rồi `remove(key)` gồm hai thao tác riêng, không được suy ra rằng dữ liệu không thể thay đổi xen giữa khi nhiều luồng cùng dùng. Mọi đường truy cập qua gốc và qua view phải tuân theo cùng một thiết kế phối hợp nếu có yêu cầu đồng thời.

## 13. Kiểm tra theo quan hệ giữa các view

### 13.1. Những điều nên đối chiếu

Một phép kiểm tra chỉ nhìn chuỗi in giảm dần sẽ bỏ sót phần quan trọng của view. Nên kiểm tra cả dữ liệu liên kết và ngữ nghĩa theo chiều:

1. Lấy view, sau đó thêm qua gốc: view có nhìn thấy mapping mới ở đúng vị trí không?
2. Xóa qua view khóa: mapping trong gốc có bị loại không?
3. Poll đầu view đảo: có loại cuối gốc không?
4. Với một mốc ở giữa, lower/floor/ceiling/higher có đổi cặp đúng theo chiều không?
5. Với mốc trùng khóa, floor/ceiling có giữ tính bao gồm còn lower/higher vẫn loại bằng không?
6. View phạm vi có nhận đúng cận và từ chối ghi ngoài cận không?
7. Bản sao có giữ đúng comparator mong muốn và độc lập với thay đổi cấu trúc của gốc không?

Kiểm tra thứ tự bằng một danh sách khóa theo thứ tự duyệt, chẳng hạn `new ArrayList<>(view.navigableKeySet())`. Phép bằng nhau của map hoặc set không kiểm tra thứ tự, nên hai view đi ngược chiều vẫn có thể bằng nhau về mapping hoặc tập khóa.

### 13.2. Trường hợp biên có giá trị học tập

- Map rỗng: tách rõ phương thức trả null và phương thức ném ngoại lệ.
- Map một mapping: đầu và cuối cùng là một khóa; poll một đầu làm đầu kia cũng biến mất.
- Map đã dùng comparator giảm dần: descendingMap phải đảo về chiều tăng của số trong trường hợp đó.
- Cận phạm vi không trùng khóa đang có: cận vẫn là mốc so sánh, không cần được chèn vào map.
- Mapping đúng cận bị xóa: phạm vi vẫn giữ cận đã định, không thu hẹp theo tập khóa hiện tại.
- Khóa null nếu comparator cho phép: phân biệt entry null với entry có khóa null.

Nếu from và to tương đương theo comparator, một phạm vi nhận cả hai đầu có thể chứa nhóm khóa tại mốc đó; nếu loại một đầu thì không chứa mốc. Khi làm việc với comparator riêng, cần xét quan hệ so sánh thay vì chỉ dựa vào hình thức biểu diễn khóa.

### 13.3. Chi phí của view và bản sao khác nhau

Việc lấy view không đòi hỏi sao chép tất cả mapping thành một map dữ liệu độc lập. Các thao tác qua view vẫn làm việc trên cấu trúc được liên kết, với chiều và cận của view.

Tuy nhiên, đừng suy ra mọi thao tác trên view đều có chi phí hằng số. Duyệt k phần tử và tạo danh sách k khóa phải xử lý k phần tử; các phép tìm trên TreeMap vẫn dựa vào cấu trúc cây và phép so sánh khóa. Các view phạm vi cũng có công việc kiểm tra cận và thao tác trên phần dữ liệu được nhìn thấy.

Chọn view khi cần nhìn dữ liệu hiện tại theo chiều hoặc phạm vi khác. Chọn bản sao khi cần cấu trúc độc lập và chấp nhận chi phí tạo dữ liệu chứa mới. Đây là quyết định về quan hệ dữ liệu trước khi là quyết định tối ưu tốc độ.

## 14. Lỗi thường gặp

| Nhầm lẫn | Hệ quả | Cách xử lý |
|---|---|---|
| descendingMap tạo một TreeMap riêng | Sửa view làm thay đổi gốc ngoài ý định | Đọc đúng quan hệ view liên kết |
| Tạo view đảo làm map gốc đổi chiều duyệt | Dự đoán sai kết quả từ biến gốc | Giữ riêng chiều của từng đối tượng nhận lời gọi |
| descending luôn là số lớn đến số nhỏ | Sai khi gốc đã có comparator đảo | Đảo thứ tự đang có, không mặc định giá trị số |
| lower luôn trả số nhỏ hơn | Sai trên view giảm dần | Đọc theo comparator của view |
| Viết cận subMap số nhỏ trước ở mọi chiều | IllegalArgumentException hoặc sai phạm vi | Đặt from/to theo thứ tự view |
| Đổi cận nhưng quên đổi vị trí cờ bao gồm | Nhận nhầm một đầu, bỏ nhầm đầu khác | Gắn cờ với giá trị cận tương ứng |
| navigableKeySet là tập khóa độc lập | Remove/clear làm mất mapping nguồn | Tạo collection mới nếu cần bản sao |
| Map sửa được nên keys.add cũng được | UnsupportedOperationException | Thêm mapping bằng put cả khóa và giá trị |
| Poll chỉ xem đầu/cuối | Dữ liệu bị loại | Dùng first/last để xem |
| First của set rỗng trả null | Bỏ sót NoSuchElementException | Theo hợp đồng riêng của phương thức |
| Poll khóa trả null luôn nghĩa là rỗng | Sai khi có khóa null hợp lệ | Dùng entry hoặc hợp đồng khóa không null khi cần phân biệt |
| Mọi constructor TreeMap copy đều giữ comparator | Bản sao đổi thứ tự hoặc không so được khóa | Phân biệt overload Map và SortedMap |
| Map.equals hoặc Set.equals chứng minh thứ tự giống nhau | Kiểm tra không phát hiện đảo chiều | So sánh một danh sách theo thứ tự |

## 15. Tự kiểm tra

### Câu hỏi

1. Gốc tự nhiên có `[10, 20, 30]`; sau khi tạo down, gốc có tự chuyển thành `[30, 20, 10]` không?
2. Xóa khóa 20 qua `down.navigableKeySet()` có ảnh hưởng map gốc không?
3. `down.pollFirstEntry()` lấy đầu hay cuối gốc?
4. Với gốc `[10, 20, 30, 40]`, `down.lowerKey(25)` và `down.ceilingKey(25)` là gì?
5. Vì sao `down.subMap(10, true, 40, true)` không hợp lệ khi down dùng thứ tự số giảm dần?
6. `map.descendingKeySet()` và `map.navigableKeySet().descendingSet()` có cần là cùng đối tượng để cùng nhìn dữ liệu không?
7. Có thể thêm khóa vào map bằng `navigableKeySet().add(key)` không?
8. Tạo `ArrayList` từ view khóa có tiếp tục nhìn thấy các khóa thêm về sau không?
9. Khi đầu vào được khai báo NavigableMap, constructor TreeMap copy nào được chọn? Nếu khai báo Map thì sao?
10. Một poll khóa trả null có đủ để suy ra trước đó không có mapping trong mọi TreeMap không?

### Đáp án

1. Không; gốc giữ chiều cũ, down nhìn ngược.
2. Có; view khóa liên kết nên mapping 20 bị loại khỏi gốc.
3. Cuối gốc, vì đó là đầu view đảo.
4. Lần lượt là 30 và 20, theo chiều của down.
5. 10 đứng sau 40 trong comparator giảm dần; cận from/to bị đảo so với thứ tự yêu cầu.
6. Không; quan hệ được bảo đảm bởi hợp đồng view, không dựa vào danh tính đối tượng.
7. Không; view khóa không hỗ trợ add/addAll, cần put mapping trên map.
8. Không; đó là danh sách mới chứa các khóa tại lúc tạo, dù bản thân các đối tượng khóa có thể vẫn được chia sẻ tham chiếu.
9. NavigableMap cũng là SortedMap nên chọn overload SortedMap và giữ thứ tự; kiểu Map chọn overload Map, dùng thứ tự tự nhiên.
10. Không; nếu comparator cho phép khóa null, poll có thể vừa loại một mapping mang khóa null.

## 16. Thực hành với kết quả đối chiếu

### Bài 1: xóa qua view đảo

Tạo gốc tự nhiên có 1=A, 2=B, 3=C và lấy down. Thêm 4=D qua gốc, rồi gọi `down.navigableKeySet().pollFirst()`. Trước khi chạy, dự đoán khóa được lấy và thứ tự cả hai chiều.

Kết quả đối chiếu: poll trả 4 và loại 4=D; gốc còn `[1, 2, 3]`, down còn `[3, 2, 1]`. Nếu dự đoán 1 thì đã đọc đầu view như đầu gốc.

### Bài 2: cận có bao gồm theo chiều đảo

Với gốc có 10, 20, 30, 40, lấy `down.subMap(40, false, 20, true)`. Liệt kê khóa đang nhìn và viết một phạm vi trên gốc chứa cùng mapping.

Kết quả đối chiếu: down nhìn `[30, 20]`; gốc tương ứng là `subMap(20, true, 40, false)` với thứ tự `[20, 30]`. Cờ true vẫn đi cùng cận 20 và cờ false vẫn đi cùng cận 40.

### Bài 3: view không chụp riêng tập khóa ban đầu

Tạo range đảo từ 40 có nhận đến 20 không nhận khi gốc chỉ có 10, 20, 30, 40. Xóa mapping 40, rồi thêm 35 qua gốc. Giải thích vì sao range nhìn thấy 35 dù khóa đó chưa tồn tại lúc tạo range.

Kết quả đối chiếu: range nhìn `[35, 30]`. Phạm vi được xác định bởi cận, không bởi bản sao danh sách các khóa lúc khởi tạo.

### Bài 4: kiểm tra bản sao và kiểu khai báo

Tạo down, một TreeMap copy từ biến NavigableMap và một TreeMap copy từ biến Map trỏ cùng down. Sau đó sửa gốc. Đối chiếu thứ tự ban đầu của hai bản sao và việc chúng có tự cập nhật hay không.

Kết quả đối chiếu: bản sao từ NavigableMap giữ chiều của down; bản sao từ Map dùng thứ tự tự nhiên. Cả hai không tự cập nhật cấu trúc theo gốc. Muốn xác nhận thứ tự, so danh sách khóa, không chỉ so Map.equals.

## 17. Môi trường chạy và tài liệu

Bốn chương trình trong bài độc lập, dùng cú pháp và API tương thích Java 17. Chúng đã được biên dịch bằng `javac --release 17 -encoding UTF-8` và chạy trên JDK 24.0.2; stdout đã được đối chiếu từ các lần chạy đó. Mỗi lớp public được lưu trong tệp trùng tên, không cần thư viện ngoài.

- [TreeMap — Java 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeMap.html): view đảo, view khóa, constructor sao chép và phạm vi liên kết.
- [NavigableMap — Java 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/NavigableMap.html): quan hệ điều hướng, descendingMap và cận phạm vi.
- [NavigableSet — Java 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/NavigableSet.html): tìm lân cận, hai đầu, view đảo và iterator.
- [SortedMap — Java 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/SortedMap.html): thứ tự của map và các collection view tương ứng.
