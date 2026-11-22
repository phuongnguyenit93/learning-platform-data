# descendingMap và navigableKeySet trong NavigableMap

## 1. Cùng dữ liệu, nhiều cách quan sát

Một `NavigableMap<K, V>` có thể cần phục vụ hai cách sử dụng:

- Duyệt đầy đủ khóa–giá trị theo chiều ngược.
- Chỉ tra cứu và xử lý các khóa, nhưng vẫn cần khả năng điều hướng.

`descendingMap()` và `navigableKeySet()` đáp ứng hai nhu cầu đó bằng **khung nhìn** (view). Khung nhìn cho phép thao tác trên cùng dữ liệu nền qua một giao diện hoặc thứ tự khác; nó không tự tạo bản sao độc lập.

Với map `{10=A, 20=B, 30=C}` theo thứ tự tự nhiên:

```java
// map la NavigableMap<Integer, String>.
NavigableMap<Integer, String> descending = map.descendingMap();
NavigableSet<Integer> keys = map.navigableKeySet();
```

`descending` quan sát ánh xạ theo thứ tự `30, 20, 10`, còn `keys` quan sát các khóa theo thứ tự `10, 20, 30`. Các API này vẫn thuộc Java hiện hành; xem [NavigableMap](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/NavigableMap.html).

## 2. descendingMap đảo toàn bộ ý nghĩa thứ tự

`descendingMap()` trả về `NavigableMap<K, V>`, giữ các ánh xạ nhưng đảo thứ tự khóa so với map đang gọi. Nó không sắp theo giá trị `V`.

Tác động không chỉ là in ngược các dòng:

| Trên map tự nhiên có khóa [10, 20, 30] | Trên khung nhìn ngược |
| --- | --- |
| `firstKey()` là 10 | `firstKey()` là 30 |
| `lastKey()` là 30 | `lastKey()` là 10 |
| `lowerKey(20)` là 10 | `lowerKey(20)` là 30 |
| `higherKey(20)` là 30 | `higherKey(20)` là 10 |
| `floorKey(25)` là 20 | `floorKey(25)` là 30 |
| `ceilingKey(25)` là 30 | `ceilingKey(25)` là 20 |

Các quan hệ được xét theo comparator của khung nhìn đang dùng. “Nhỏ hơn” theo thứ tự đảo có thể là một số lớn hơn theo số học. Hợp đồng `descendingMap` quy định đảo cả hướng và quan hệ điều hướng; xem [NavigableMap.descendingMap](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/NavigableMap.html).

Nếu map gốc vốn dùng comparator đảo, `descendingMap()` lại đảo thứ tự ấy. Không mặc định “descending” luôn có nghĩa số lớn đứng trước; nó là chiều ngược của **thứ tự nguồn**.

Gọi hai lần `map.descendingMap().descendingMap()` tạo một khung nhìn tương đương về thứ tự và dữ liệu với map ban đầu. Không dựa vào so sánh tham chiếu `==` để kiểm tra sự tương đương này.

## 3. navigableKeySet là tập khóa có điều hướng

`navigableKeySet()` trả về `NavigableSet<K>`. Ngoài duyệt khóa, nơi gọi có thể dùng:

- `lower/floor/ceiling/higher` để tìm khóa quanh một mốc.
- `first/last` để xem hai đầu.
- `subSet/headSet/tailSet` để lấy phạm vi khóa.
- `descendingSet` hoặc iterator ngược để đổi chiều duyệt.

Ví dụ với khóa `[10, 25, 30, 40]`, `keys.floor(27)` là 25, `keys.ceiling(27)` là 30. Các thao tác này làm việc trên khóa; chúng không trả giá trị ánh xạ. Xem [NavigableSet](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/NavigableSet.html).

Về kiểu trả về, `Map.keySet()` cung cấp `Set<K>`; `navigableKeySet()` cung cấp trực tiếp `NavigableSet<K>`. Khi cần điều hướng, dùng API có kiểu phù hợp thay vì ép kiểu tập khóa. Xem [Map.keySet](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Map.html#keySet()).

### Các cách lấy khóa theo chiều ngược

Ba cách sau có cùng ý nghĩa về các khóa và chiều duyệt:

```java
map.descendingKeySet();
map.descendingMap().navigableKeySet();
map.navigableKeySet().descendingSet();
```

Chúng đều là khung nhìn trên dữ liệu nguồn. Sự tương đương về hành vi không yêu cầu các đối tượng trả về phải là cùng một tham chiếu.

## 4. Khả năng sửa của hai loại khung nhìn khác nhau

Với một `TreeMap` có thể sửa:

| Thao tác | Tác động |
| --- | --- |
| `descending.put(k, v)` | Thêm/cập nhật ánh xạ trong map gốc |
| `descending.remove(k)` | Xóa ánh xạ ở map gốc |
| `keys.remove(k)` | Xóa cả ánh xạ của khóa k trong map gốc |
| `keys.clear()` | Xóa các ánh xạ thuộc tập khóa đang nhìn thấy |
| `keys.add(k)` | Không được hỗ trợ |
| `keys.addAll(...)` | Không được hỗ trợ |

Tập khóa không có đủ thông tin về giá trị `V` để thực hiện một phép thêm ánh xạ thông thường. Vì vậy muốn thêm khóa và giá trị, hãy dùng `put` trên map.

Một tập khóa không hỗ trợ thêm vẫn có thể hỗ trợ xóa. Đừng suy ra rằng `keys.add` bị từ chối thì `keys.remove` hoặc `clear` không làm thay đổi dữ liệu. Hợp đồng này được ghi rõ tại [TreeMap.navigableKeySet](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/TreeMap.html).

Bảng đang nói về khung nhìn của `TreeMap` có thể sửa trong ví dụ. Nếu nguồn là map hoặc bộ bao chỉ đọc, các phép sửa còn bị giới hạn bởi hợp đồng của nguồn.

## 5. Ví dụ đầy đủ chạy trên Java 17+

Tệp `NavigableMapViewsDemo.java`:

```java
import java.util.NavigableMap;
import java.util.NavigableSet;
import java.util.TreeMap;
import java.util.TreeSet;

public class NavigableMapViewsDemo {
    public static void main(String[] args) {
        NavigableMap<Integer, String> base = new TreeMap<>();
        base.put(10, "A");
        base.put(20, "B");
        base.put(30, "C");

        NavigableMap<Integer, String> descending = base.descendingMap();
        NavigableSet<Integer> keys = base.navigableKeySet();

        System.out.println("base=" + base);
        System.out.println("descending=" + descending);
        System.out.println("descending first/last="
                + descending.firstKey() + "/" + descending.lastKey());
        System.out.println("descending lowerKey(20)=" + descending.lowerKey(20));
        System.out.println("descending floorKey(25)=" + descending.floorKey(25));
        System.out.println("descending ceilingKey(25)="
                + descending.ceilingKey(25));
        System.out.println("descending higherKey(20)="
                + descending.higherKey(20));

        descending.put(40, "D");
        System.out.println("base after descending put=" + base);
        System.out.println("keys after descending put=" + keys);

        System.out.println("key remove(20)=" + keys.remove(20));
        System.out.println("base after key removal=" + base);
        base.put(25, "X");
        System.out.println("keys after base put=" + keys);
        System.out.println("keys floor(27)=" + keys.floor(27));
        System.out.println("keys ceiling(27)=" + keys.ceiling(27));
        System.out.println("descendingKeySet=" + base.descendingKeySet());
        System.out.println("descending navigableKeySet="
                + descending.navigableKeySet());

        NavigableMap<Integer, String> mapCopy = new TreeMap<>(descending);
        NavigableSet<Integer> keyCopy = new TreeSet<>(keys);

        try {
            keys.add(50);
            throw new AssertionError("keys.add should fail");
        } catch (UnsupportedOperationException expected) {
            System.out.println("keys.add=UnsupportedOperationException");
        }

        NavigableSet<Integer> tail = keys.tailSet(25, true);
        System.out.println("tail pollFirst=" + tail.pollFirst());
        System.out.println("base after poll=" + base);

        keys.subSet(10, true, 40, false).clear();
        System.out.println("base after range clear=" + base);
        System.out.println("descending after range clear=" + descending);
        System.out.println("mapCopy=" + mapCopy);
        System.out.println("keyCopy=" + keyCopy);
        System.out.println("double descending keys="
                + descending.descendingMap().navigableKeySet());
    }
}
```

Biên dịch và chạy với JDK 17 hoặc mới hơn:

```shell
javac -encoding UTF-8 NavigableMapViewsDemo.java
java NavigableMapViewsDemo
```

Kết quả chính xác:

```text
base={10=A, 20=B, 30=C}
descending={30=C, 20=B, 10=A}
descending first/last=30/10
descending lowerKey(20)=30
descending floorKey(25)=30
descending ceilingKey(25)=20
descending higherKey(20)=10
base after descending put={10=A, 20=B, 30=C, 40=D}
keys after descending put=[10, 20, 30, 40]
key remove(20)=true
base after key removal={10=A, 30=C, 40=D}
keys after base put=[10, 25, 30, 40]
keys floor(27)=25
keys ceiling(27)=30
descendingKeySet=[40, 30, 25, 10]
descending navigableKeySet=[40, 30, 25, 10]
keys.add=UnsupportedOperationException
tail pollFirst=25
base after poll={10=A, 30=C, 40=D}
base after range clear={40=D}
descending after range clear={40=D}
mapCopy={40=D, 30=C, 25=X, 10=A}
keyCopy=[10, 25, 30, 40]
double descending keys=[40]
```

## 6. Theo dõi quan hệ dùng chung dữ liệu

### Thêm qua descendingMap

`descending.put(40, "D")` làm map gốc có thêm `40=D`. Tập khóa được lấy **từ trước** cũng tự quan sát thấy 40 vì nó nhìn vào cùng map.

Không cần gọi lại `navigableKeySet()` mỗi lần map thay đổi để có một tập kết quả mới. Điều đó cũng có nghĩa tập khóa cũ không phải ảnh chụp dữ liệu tại thời điểm tạo.

### Xóa qua tập khóa

`keys.remove(20)` khiến ánh xạ `20=B` biến mất khỏi map gốc và khung nhìn ngược. Việc xóa không chỉ ẩn 20 khỏi một tập tạm.

Sau đó `base.put(25, "X")` làm tập khóa thấy 25. Chiều cập nhật từ map đến tập khóa và từ tập khóa về map đều được thể hiện trong cùng chương trình.

### Lấy và xóa đầu của một phạm vi khóa

`keys.tailSet(25, true)` là khung nhìn các khóa không nhỏ hơn 25 trong thứ tự tự nhiên. `pollFirst()` trên nó trả 25 và xóa ánh xạ `25=X` khỏi map gốc.

Đây là tác động sửa dữ liệu. Nếu chỉ muốn xem khóa đầu của khoảng, dùng thao tác đọc thích hợp thay vì `pollFirst`.

### clear trên khoảng chỉ xóa phần đang nhìn thấy

Sau phép poll, khóa còn lại là `[10, 30, 40]`. Lời gọi:

```java
keys.subSet(10, true, 40, false).clear();
```

xóa 10 và 30, giữ lại 40 vì biên trên bị loại. Khi đó cả `base` và `descending` chỉ còn `40=D`.

Nếu gọi `keys.clear()` trên tập khóa đầy đủ thì toàn bộ map bị xóa. Phải xác định rõ tập khóa đang dùng là toàn bộ dữ liệu hay một khoảng bị giới hạn.

## 7. Bản sao độc lập và việc giữ comparator

Trước các phép xóa cuối, chương trình tạo:

```java
NavigableMap<Integer, String> mapCopy = new TreeMap<>(descending);
NavigableSet<Integer> keyCopy = new TreeSet<>(keys);
```

Hai biến mới không còn là khung nhìn của `base`. Sau khi map gốc chỉ còn 40:

- `mapCopy` vẫn giữ `{40=D, 30=C, 25=X, 10=A}`.
- `keyCopy` vẫn giữ `[10, 25, 30, 40]`.

Constructor `TreeMap` nhận `SortedMap` giữ comparator của nguồn, nên bản sao từ `descending` tiếp tục có thứ tự ngược. Xem [constructor TreeMap](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/TreeMap.html).

Kiểu nguồn được chọn ở thời điểm biên dịch có ý nghĩa khi chọn overload. Nếu chỉ giữ nguồn qua biến kiểu `Map`, `new TreeMap<>(source)` chọn constructor nhận `Map` và dùng thứ tự tự nhiên, thay vì mặc định giữ comparator. Khi muốn bảo toàn thứ tự, hãy thể hiện yêu cầu đó rõ trong kiểu dữ liệu hoặc constructor.

Bản sao cấu trúc không phải bản sao sâu. Nếu khóa hoặc giá trị là đối tượng có thể thay đổi, các tham chiếu bên trong có thể vẫn được dùng chung. Trong ví dụ, khóa `Integer` và giá trị `String` là các đối tượng bất biến.

Nếu chỉ cần một danh sách để hiển thị theo thứ tự hiện tại, có thể sao chép tập khóa vào `ArrayList`. Nếu cần tiếp tục tra cứu hàng xóm trên bản sao, `TreeSet` là một lựa chọn phù hợp hơn.

## 8. Duyệt và sửa dữ liệu qua các khung nhìn

Việc một khung nhìn đang hoạt động phản ánh dữ liệu nguồn không đồng nghĩa mọi iterator đều được phép tiếp tục khi nguồn bị sửa.

Không viết:

```java
// Minh hoa cach sua khong phu hop trong khi for-each dang duyet.
for (Integer key : base.navigableKeySet()) {
    base.remove(key);
}
```

Với `TreeMap`, sửa cấu trúc theo cách đó có thể làm iterator phát sinh `ConcurrentModificationException`. Không dựa vào ngoại lệ này như một cơ chế đồng bộ hoặc một bảo đảm rằng mọi lỗi sửa đồng thời đều được phát hiện. Xem [hợp đồng iterator và đồng bộ TreeMap](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/TreeMap.html).

Nếu mục tiêu là xóa có điều kiện trong một chương trình đơn luồng, có thể dùng iterator và chính `iterator.remove()`:

```java
// base la TreeMap/NavigableMap co ho tro xoa.
java.util.Iterator<Integer> iterator = base.navigableKeySet().iterator();
while (iterator.hasNext()) {
    Integer key = iterator.next();
    if (key < 20) {
        iterator.remove();
    }
}
```

Đoạn trên minh họa việc dùng iterator đúng quyền xóa, không phải một chương trình độc lập. Nếu đã biết rõ một khoảng cần xóa, thao tác `subSet(...).clear()` thường diễn đạt yêu cầu ngắn gọn hơn.

Khung nhìn không bổ sung an toàn luồng cho `TreeMap`. Nếu có truy cập đồng thời và sửa dữ liệu, cần thiết kế giao thức truy cập phù hợp; không khóa riêng map gốc và khung nhìn bằng hai khóa không liên quan.

## 9. Lỗi thường gặp và cách chọn API

- **Coi descendingMap là bản sao:** xóa qua nó làm mất dữ liệu ở map gốc. Tạo `TreeMap` mới nếu cần chỉnh một bản độc lập.
- **Coi navigableKeySet là TreeSet tự do:** `add` bị từ chối; xóa lại tác động đến map.
- **Hiểu lower/higher theo số học sau khi đảo:** viết thứ tự khóa ra trước rồi suy luận theo comparator.
- **Coi thứ tự khóa là thứ tự giá trị:** `descendingMap` không xếp các giá trị theo tên, điểm hay trường khác.
- **Trả tập khóa ra ngoài mà quên quyền xóa:** nơi nhận có thể xóa ánh xạ của nơi sở hữu map. Cần chọn rõ giữa khung nhìn có thể sửa, khung nhìn chỉ đọc hoặc bản sao.
- **Dùng so sánh Set.equals để chứng minh cùng thứ tự:** phép bằng của set không kiểm tra thứ tự duyệt. Nếu thứ tự quan trọng trong kiểm thử, thu dãy khóa vào danh sách rồi so sánh.

Khi cần cả khóa lẫn giá trị theo chiều ngược, duyệt `map.descendingMap().entrySet()`. Khi chỉ cần khóa và điều hướng quanh mốc, dùng `navigableKeySet()`. Khi chỉ cần khóa theo chiều ngược, `descendingKeySet()` thể hiện trực tiếp ý định.

## 10. Thực hành

1. Đổi map gốc sang comparator đảo rồi dự đoán thứ tự của `descendingMap`. Kiểm tra cả `firstKey/lastKey` và `lowerKey/higherKey`.
2. Lấy một khung nhìn khóa, thêm ánh xạ qua map rồi xóa qua tập khóa. Sau mỗi thao tác, đối chiếu cả map gốc, map ngược và tập khóa.
3. Gọi `clear()` trên một khoảng khóa và xác nhận các ánh xạ ngoài khoảng còn nguyên.
4. Sao chép map ngược bằng constructor nhận `SortedMap`, sau đó sửa nguồn. Kiểm tra bản sao không đổi và vẫn duyệt theo thứ tự ngược.
5. Viết kiểm thử xác nhận `keys.add` ném đúng `UnsupportedOperationException`, còn `keys.remove` xóa đúng ánh xạ. Không kết luận “không sửa được” chỉ từ một phép thêm thất bại.
