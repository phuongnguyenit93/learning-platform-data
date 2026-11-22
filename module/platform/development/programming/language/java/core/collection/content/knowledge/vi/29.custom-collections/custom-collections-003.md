# AbstractQueue và AbstractMap

## 1. Lớp khung cung cấp hành vi, cài đặt con cung cấp nền dữ liệu

Khi viết collection tùy chỉnh, phần khó không chỉ nằm ở chỗ lưu phần tử. Bên gọi còn trông đợi nhiều phương thức có quan hệ nhất quán: thêm, xóa, duyệt, xem nội dung, chuyển thành mảng, so sánh và thao tác qua các view.

Các lớp cài đặt khung (skeletal implementation) giảm công việc lặp bằng cách xây nhiều phương thức từ một số thao tác nền. `AbstractQueue` và `AbstractMap` là hai ví dụ:

- `AbstractQueue` xây một số thao tác Queue trên `offer`, `poll`, `peek`.
- `AbstractMap` xây nhiều thao tác Map trên cách nhìn các cặp khóa–giá trị qua `entrySet()`.

Chúng không chọn sẵn mọi thứ: thứ tự lấy phần tử, giới hạn dung lượng, cấu trúc chứa khóa, khả năng sửa hay chi phí tra cứu vẫn cần được quyết định.

Mô hình chung:

```text
Hợp đồng giao diện
    ↓
Lớp khung: triển khai các phương thức dựa trên thao tác nền
    ↓
Lớp con: giữ dữ liệu và thực hiện đúng các thao tác nền
```

Một phương thức nền sai có thể làm nhiều phương thức kế thừa cùng sai. Ngược lại, khi nền đúng và phù hợp, lớp con có thể tái sử dụng khá nhiều hành vi mà không tự viết lại.

Bài dùng Java 17 trở lên. Ba chương trình độc lập lần lượt minh họa một queue FIFO có giới hạn, một map nhỏ có thể sửa và một map không cho sửa. Chúng tái sử dụng cấu trúc chứa có sẵn để tập trung vào quan hệ giữa các phương thức của lớp khung; không đề xuất thay các collection chuẩn bằng các lớp minh họa này trong mọi ứng dụng.

## 2. Vị trí trong hệ thống kiểu và trách nhiệm của lớp con

| Khía cạnh | AbstractQueue | AbstractMap |
|---|---|---|
| Giao diện chính | `Queue<E>` | `Map<K, V>` |
| Lớp cha trực tiếp | `AbstractCollection<E>` | `Object` |
| Trọng tâm của nền cài đặt | Thêm thử, lấy đầu, xem đầu, duyệt và đếm | Set-view của các liên kết khóa–giá trị |
| Dữ liệu lưu ở đâu? | Do lớp con chọn | Do lớp con chọn |
| Có tự cung cấp tính đồng thời? | Không | Không |
| Có tự chọn thứ tự? | Không | Không |
| Có thể kế thừa trực tiếp để tạo đối tượng? | Cần lớp con cụ thể | Cần lớp con cụ thể |

`Map` thuộc Java Collections Framework nhưng không phải giao diện con của `Collection`. Các tập khóa, tập entry và collection giá trị của map mới là các view collection.

Cũng không nên đồng nhất `AbstractQueue` với `BlockingQueue`. Kế thừa nó không tự tạo các phương thức `put`, `take` hay thao tác chờ có timeout.

Hai lớp khung cung cấp thuật toán mặc định chứ không tự làm dữ liệu của lớp con an toàn khi nhiều luồng truy cập. Các ví dụ có thể sửa trong bài được thiết kế cho cách dùng một luồng hoặc cách phối hợp bên ngoài đã được xác định.

## 3. AbstractQueue: từ giá trị báo thất bại đến ngoại lệ

### 3.1. Năm phương thức nền cần cung cấp

Một lớp con cụ thể tối thiểu cần thực hiện:

| Phương thức | Hợp đồng cần giữ |
|---|---|
| `offer(e)` | Thử thêm; thành công trả `true`, chưa thể thêm do giới hạn phù hợp thì trả `false`; không nhận `null` |
| `poll()` | Lấy và xóa đầu queue; rỗng trả `null` |
| `peek()` | Xem đầu queue mà không xóa; rỗng trả `null` |
| `size()` | Số phần tử hiện có theo hợp đồng của cài đặt |
| `iterator()` | Duyệt đúng dữ liệu theo thứ tự đã công bố |

`AbstractQueue` dùng kết quả `false` hoặc `null` để tạo các phiên bản báo ngoại lệ. Vì vậy, nó phù hợp với queue không lưu phần tử `null`. Xem [hợp đồng nền của AbstractQueue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/AbstractQueue.html).

Chính lớp con xác định “đầu queue” là phần tử nào. FIFO, ưu tiên hoặc LIFO có thể có quy tắc khác nhau. Không suy ra mọi queue kế thừa khung này đều FIFO.

`offer` trả `false` cho tình huống không thêm được theo chính sách thông thường, chẳng hạn đầy. Điều đó không yêu cầu chuyển mọi lỗi đầu vào thành `false`; giá trị không hợp lệ vẫn có thể phải báo ngoại lệ theo hợp đồng.

### 3.2. Quan hệ giữa các cặp phương thức

| Phương thức kế thừa | Thao tác nền được dùng | Khi thao tác chưa thành công |
|---|---|---|
| `add(e)` | `offer(e)` | `offer` trả `false` thì báo `IllegalStateException` |
| `remove()` | `poll()` | `poll` trả `null` thì báo `NoSuchElementException` |
| `element()` | `peek()` | `peek` trả `null` thì báo `NoSuchElementException` |

Đây là hai cách biểu đạt cùng nhu cầu Queue với chính sách thất bại khác nhau. Xem [các cặp phương thức của Queue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Queue.html).

Không cần tự override cả sáu phương thức chỉ để giữ quan hệ mặc định này. Nhưng nếu override một phương thức, phải giữ sự nhất quán với các phương thức còn lại.

Ví dụ, nếu `peek` trả phần tử B mà `poll` lại lấy A trong một trạng thái không thay đổi, bên gọi không còn có một ý nghĩa “đầu queue” nhất quán.

### 3.3. clear và addAll cũng dựa vào nền đã chọn

`clear()` mặc định gọi `poll()` lặp đến khi nhận `null`. Nếu cài `poll` chỉ xem mà không xóa, thao tác dọn có thể không tiến triển. Nếu `poll` ném lỗi khi rỗng thay vì trả `null`, đường dọn cũng không còn đúng với nền mà lớp khung yêu cầu.

`addAll` mặc định thêm từng phần tử theo đường `add`. Nếu một lần thêm ném lỗi, các phần tử trước đó có thể đã vào queue. Nó không phải một giao dịch tự hoàn tác tất cả.

```text
addAll([C, D, E])
    → add(C) → offer(C) → thành công
    → add(D) → offer(D) → thành công
    → add(E) → offer(E) → không còn chỗ → ngoại lệ

C và D có thể vẫn nằm trong queue.
```

Khả năng sửa qua iterator cũng quan trọng. `remove(Object)` là thao tác khác với `remove()`: phiên bản có đối tượng tìm phần tử phù hợp và có thể dựa vào iterator để xóa.

Nếu iterator không hỗ trợ xóa, không được mặc định mọi phép xóa kế thừa đều sẽ làm được. Cần công bố và kiểm tra đúng những thao tác được hỗ trợ.

## 4. Chương trình Queue: năm phương thức nền, nhiều hành vi kế thừa

Tệp `QueueSkeletonDemo.java`:

```java
import java.util.AbstractQueue;
import java.util.ArrayDeque;
import java.util.Iterator;
import java.util.List;
import java.util.Objects;

public class QueueSkeletonDemo {
    static final class BoundedFifo<E> extends AbstractQueue<E> {
        private final int capacity;
        private final ArrayDeque<E> elements = new ArrayDeque<>();

        BoundedFifo(int capacity) {
            if (capacity <= 0) {
                throw new IllegalArgumentException("capacity must be positive");
            }
            this.capacity = capacity;
        }

        @Override
        public boolean offer(E element) {
            Objects.requireNonNull(element, "element");
            if (elements.size() == capacity) {
                return false;
            }
            return elements.offerLast(element);
        }

        @Override
        public E poll() {
            return elements.pollFirst();
        }

        @Override
        public E peek() {
            return elements.peekFirst();
        }

        @Override
        public int size() {
            return elements.size();
        }

        @Override
        public Iterator<E> iterator() {
            return elements.iterator();
        }
    }

    public static void main(String[] args) {
        var queue = new BoundedFifo<String>(2);
        System.out.println("offerA=" + queue.offer("A"));
        System.out.println("offerB=" + queue.offer("B"));
        System.out.println("peek=" + queue.peek());
        System.out.println("offerC=" + queue.offer("C"));
        try {
            queue.add("C");
        } catch (IllegalStateException ex) {
            System.out.println("fullAdd=" + ex.getClass().getSimpleName());
        }

        System.out.println("removeHead=" + queue.remove());
        System.out.println("removeB=" + queue.remove("B"));
        try {
            queue.addAll(List.of("C", "D", "E"));
        } catch (IllegalStateException ex) {
            System.out.println("bulkFailure=" + ex.getClass().getSimpleName());
        }
        System.out.println("afterBulk=" + queue);
        queue.clear();
        System.out.println("emptyPoll=" + queue.poll());
        try {
            queue.element();
        } catch (java.util.NoSuchElementException ex) {
            System.out.println("emptyElement=" + ex.getClass().getSimpleName());
        }

        queue.addAll(List.of("X", "Y"));
        Iterator<String> iterator = queue.iterator();
        System.out.println("iteratorNext=" + iterator.next());
        iterator.remove();
        System.out.println("afterIteratorRemove=" + queue);
        try {
            queue.offer(null);
        } catch (NullPointerException ex) {
            System.out.println("nullOffer=" + ex.getClass().getSimpleName());
        }
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 QueueSkeletonDemo.java
java QueueSkeletonDemo
```

Stdout:

```text
offerA=true
offerB=true
peek=A
offerC=false
fullAdd=IllegalStateException
removeHead=A
removeB=true
bulkFailure=IllegalStateException
afterBulk=[C, D]
emptyPoll=null
emptyElement=NoSuchElementException
iteratorNext=X
afterIteratorRemove=[Y]
nullOffer=NullPointerException
```

### 4.1. Biểu diễn và điều kiện của ví dụ

`BoundedFifo` chứa dữ liệu trong một `ArrayDeque` riêng, thêm cuối và lấy đầu. Dung lượng là giới hạn số phần tử do lớp bọc quản lý, không phải một lời hứa mảng bên trong chỉ có đúng chừng đó ô.

`offer` kiểm tra `null` trước khi xét đầy. Khi đủ chỗ nó thêm cuối; khi đã đạt giới hạn nó trả `false`. Các đường thêm hợp lệ đi qua phương thức này.

`poll` và `peek` cùng dùng đầu deque nhưng một bên xóa, một bên chỉ đọc. Iterator được lấy từ chính dữ liệu nền nên duyệt cùng nội dung và hỗ trợ xóa phần tử đã duyệt.

Không trả iterator của một bản sao nếu muốn phép xóa qua iterator tác động vào queue gốc.

### 4.2. Các kết quả thể hiện đường gọi nào?

A và B được nhận; C chưa vào được nên `offer` trả `false`. Khi gọi `add("C")`, chính lớp khung chuyển thất bại đó thành ngoại lệ.

`remove()` lấy A theo `poll`. `remove("B")` tìm B qua đường thao tác collection và xóa khỏi dữ liệu nền.

Sau khi queue đã rỗng, thêm C, D, E theo lô chỉ nhận được C và D. Ngoại lệ ở E không xóa ngược C, D. Kết quả `afterBulk=[C, D]` là một phần kiến thức cần quan sát, không phải lỗi của chương trình kiểm chứng.

`clear` làm dữ liệu rỗng qua đường lấy. Lần `poll` sau trả `null`, còn `element` báo ngoại lệ vì không có đầu queue.

Cuối cùng, iterator lấy X rồi xóa X, nên queue chỉ còn Y. Điều này kiểm chứng khả năng sửa của iterator có ảnh hưởng đến các phương thức kế thừa.

### 4.3. Những gì lớp khung chưa tự tạo

Ví dụ không có thao tác chờ, đồng bộ nhiều luồng hay chính sách ưu tiên. Nếu cần một queue có các khả năng đó, phải chọn cài đặt phù hợp hoặc thiết kế thêm cơ chế riêng.

Queue cũng không tự có quy tắc so sánh theo thứ tự phần tử giống `List`. Với lớp ví dụ không override `equals`/`hashCode`, không dùng hai queue cùng nội dung để suy ra chúng bằng nhau theo giá trị.

Hợp đồng Queue và cài đặt khung không phải lời hứa rằng mọi phép của một collection khác sẽ có cùng ngữ nghĩa.


## 5. AbstractMap: entrySet là nền cài đặt, không chỉ là kết quả để in

### 5.1. Phương thức trừu tượng trung tâm

`AbstractMap<K, V>` yêu cầu lớp con cung cấp `entrySet()`, trả về một `Set<Map.Entry<K, V>>` nhìn vào các liên kết của map. Từ đó, lớp khung cung cấp nhiều thao tác đọc và các view liên quan.

`put` mặc định không được hỗ trợ. Muốn hỗ trợ thêm hoặc thay liên kết, lớp con phải cung cấp đường `put` phù hợp. Muốn dùng các đường xóa mặc định, iterator của entry-set cần hỗ trợ xóa theo khả năng đã công bố. Xem [AbstractMap Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/AbstractMap.html).

Điểm cần chú ý là `entrySet` trả về **view của map**, không phải một báo cáo chụp dữ liệu không liên hệ với nguồn. Một map có thể sửa mà trả ra một tập entry sao chép rời rạc sẽ không giữ được quan hệ view mà bên gọi được quyền dựa vào.

### 5.2. Những phương thức nào được xây từ entrySet?

| Phương thức hoặc nhóm | Nền mặc định cần xem xét |
|---|---|
| `size()` | Kích thước của entry-set |
| `isEmpty()` | Kết quả kích thước |
| `get(key)`, `containsKey(key)` | Duyệt các entry để tìm khóa |
| `containsValue(value)` | Duyệt các entry để tìm giá trị |
| `remove(key)` | Tìm entry rồi xóa qua iterator |
| `clear()` | Gọi `entrySet().clear()` |
| `putAll(map)` | Gọi `put` cho các liên kết nguồn |
| `keySet()`, `values()` | Các view dựa trên liên kết và iterator của map |
| `equals`, `hashCode`, `toString` | Nội dung các liên kết |

Bảng mô tả cài đặt mặc định của lớp khung. Một lớp con có thể override để dùng biểu diễn hiệu quả hơn, nhưng phải giữ nghĩa hợp đồng.

Đặc biệt, kế thừa `AbstractMap` không tự tạo một bảng băm. `get` mặc định duyệt entry-set; nếu cần tra cứu có chỉ mục, phải cung cấp biểu diễn và đường tra cứu tương ứng.

### 5.3. Entry-set phải giữ nghĩa của một Set các liên kết

Một entry gồm khóa và giá trị. Khi so một entry với entry khác, không chỉ xét khóa rồi bỏ qua giá trị.

Ví dụ, nếu map đang có `a → 20`:

- Xóa `"a"` qua `keySet` xét khóa.
- Xóa entry `("a", 999)` qua `entrySet` không được coi là khớp chỉ vì cùng khóa.
- Xóa entry `("a", 20)` qua `entrySet` có thể xóa đúng liên kết nếu phép xóa được hỗ trợ.

Map không được có hai liên kết độc lập cho cùng một khóa theo quy tắc nhận diện khóa đã công bố. Nguồn lưu entry là một list cũng phải tự giữ điều kiện ấy, vì `AbstractSet` không tự loại trùng giúp mọi biểu diễn bên dưới.

`entrySet` không phải cửa thêm cặp mới thay cho `put`. Phương thức thêm vào entry-set không được mở tùy ý chỉ vì kiểu trả về là `Set`; các khả năng của view phải đúng với hợp đồng Map.

### 5.4. get trả null chưa xác định khóa có tồn tại hay không

Nếu map cho phép giá trị `null`, hai trạng thái khác nhau đều có thể làm `get(k)` trả `null`:

```text
Không có liên kết cho k.
Có liên kết k → null.
```

Trong cách dùng tuần tự, `containsKey` giúp phân biệt. Trong cách dùng nhiều luồng, hai lần đọc riêng không tự trở thành một thao tác nguyên tử.

Khi tự viết `put`, không dùng riêng `get(key) == null` để kết luận chắc chắn khóa chưa tồn tại rồi thêm một entry nữa. Với giá trị null được phép, cách đó có thể tạo hai entry cho cùng khóa.

## 6. Chương trình Map: một view thật nối với dữ liệu nền

Tệp `MapSkeletonDemo.java`:

```java
import java.util.AbstractMap;
import java.util.AbstractSet;
import java.util.ArrayList;
import java.util.Iterator;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

public class MapSkeletonDemo {
    static final class TinyMap<K, V> extends AbstractMap<K, V> {
        private final List<Entry<K, V>> entries = new ArrayList<>();
        private final Set<Entry<K, V>> entryView = new AbstractSet<>() {
            @Override
            public Iterator<Entry<K, V>> iterator() {
                return entries.iterator();
            }

            @Override
            public int size() {
                return entries.size();
            }

            @Override
            public void clear() {
                entries.clear();
            }
        };

        @Override
        public Set<Entry<K, V>> entrySet() {
            return entryView;
        }

        @Override
        public V put(K key, V value) {
            for (Entry<K, V> entry : entries) {
                if (Objects.equals(entry.getKey(), key)) {
                    return entry.setValue(value);
                }
            }
            entries.add(new SimpleEntry<>(key, value));
            return null;
        }
    }

    public static void main(String[] args) {
        var map = new TinyMap<String, Integer>();
        System.out.println("firstPut=" + map.put("a", 1));
        System.out.println("replaceA=" + map.put("a", 2));
        map.put("b", null);
        System.out.println("size=" + map.size());
        System.out.println("getB=" + map.get("b"));
        System.out.println("hasB=" + map.containsKey("b"));
        System.out.println("hasMissing=" + map.containsKey("missing"));

        Set<String> keys = map.keySet();
        var values = map.values();
        map.put("c", 3);
        System.out.println("liveKeys=" + keys);
        System.out.println("liveValues=" + values);

        Iterator<Map.Entry<String, Integer>> iterator = map.entrySet().iterator();
        Map.Entry<String, Integer> first = iterator.next();
        System.out.println("oldEntryValue=" + first.setValue(20));
        System.out.println("mapAfterEntryWrite=" + map);
        System.out.println("removeNullValue=" + values.remove(null));
        System.out.println("removeKeyC=" + keys.remove("c"));

        Map<String, Integer> reference = Map.of("a", 20);
        System.out.println("equalsForward=" + map.equals(reference));
        System.out.println("equalsBackward=" + reference.equals(map));
        System.out.println("sameHash=" +
                (map.hashCode() == reference.hashCode()));

        System.out.println("removeWrongEntry=" +
                map.entrySet().remove(new AbstractMap.SimpleImmutableEntry<>("a", 999)));
        System.out.println("removeExactEntry=" +
                map.entrySet().remove(new AbstractMap.SimpleImmutableEntry<>("a", 20)));
        System.out.println("emptyAfterEntryRemove=" + map.isEmpty());
        map.put(null, 7);
        System.out.println("nullKeyValue=" + map.get(null));
        map.clear();
        System.out.println("sizeAfterClear=" + map.size());
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 MapSkeletonDemo.java
java MapSkeletonDemo
```

Stdout:

```text
firstPut=null
replaceA=1
size=2
getB=null
hasB=true
hasMissing=false
liveKeys=[a, b, c]
liveValues=[2, null, 3]
oldEntryValue=2
mapAfterEntryWrite={a=20, b=null, c=3}
removeNullValue=true
removeKeyC=true
equalsForward=true
equalsBackward=true
sameHash=true
removeWrongEntry=false
removeExactEntry=true
emptyAfterEntryRemove=true
nullKeyValue=7
sizeAfterClear=0
```

### 6.1. Lớp con đã cài điều gì?

`TinyMap` giữ các entry trong một list riêng. Đây là biểu diễn nhỏ để nhìn rõ cơ chế, không phải bảng băm tối ưu.

`entryView` là một `AbstractSet`:

- `size` đọc từ list dữ liệu thật.
- Iterator duyệt chính list ấy và hỗ trợ `remove`.
- `clear` gọi trực tiếp `entries.clear()`.
- Thêm entry trực tiếp không được mở; lớp không override `add` của set-view.

`put` tìm khóa bằng `Objects.equals`. Nếu thấy khóa, nó thay giá trị của entry hiện có và trả giá trị cũ. Nếu chưa thấy, nó thêm một `SimpleEntry` mới.

Vì chỉ có `put` tạo liên kết mới và nó đã kiểm tra khóa, biểu diễn giữ được điều kiện không có hai liên kết cho cùng khóa. `SimpleEntry` cung cấp phần so sánh entry theo cả khóa và giá trị.

Lớp không tự override `get`, `containsKey`, `keySet`, `values`, `equals` hay `hashCode`. Các kết quả ở stdout đi qua nhiều đường mặc định của khung.

### 6.2. Cập nhật một khóa không làm tăng số liên kết

Lần đầu đặt `a → 1` trả `null`; đặt lại `a → 2` trả 1. Sau khi thêm `b → null`, kích thước là 2.

Khóa b có mặt dù `get("b")` trả `null`. `containsKey("b")` là `true`, còn khóa `"missing"` không có.

Ví dụ cũng kiểm tra khóa `null`, vì cài đặt này chủ ý cho phép nó và dùng phép so sánh phù hợp. Một cài đặt khác có thể không cho phép null, nhưng phải đưa ra chính sách và thực hiện nhất quán.

### 6.3. keySet và values là view đang nối với map

`keys` và `values` được lấy trước khi thêm c. Chúng vẫn phản ánh c khi được duyệt sau lần thêm, chứng tỏ đây không phải hai bản sao độc lập.

Xóa giá trị `null` qua `values.remove(null)` làm mất cả liên kết tương ứng, không chỉ đổi giá trị của nó sang một giá trị khác. Xóa c qua `keys.remove("c")` cũng làm mất liên kết c.

`values()` là collection, không phải set: nhiều khóa khác nhau có thể cùng trỏ đến các giá trị bằng nhau. Phép xóa một giá trị phù hợp không có nghĩa mọi liên kết có cùng giá trị đều tự bị xóa.

Các view khóa và giá trị hỗ trợ các đường xóa phù hợp khi map hỗ trợ, nhưng không cung cấp `add` như một cách tạo liên kết thiếu thông tin. Chỉ một khóa chưa đủ xác định giá trị, và chỉ một giá trị chưa đủ xác định khóa.

Quan hệ giữa map và các view là một phần của [hợp đồng Map](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html#entrySet()), không phải tiện ích phụ chỉ phục vụ in dữ liệu.

### 6.4. Entry.setValue là một đường cập nhật riêng

Trong ví dụ, entry đầu được lấy qua iterator, rồi `setValue(20)` đổi trực tiếp giá trị mà map đang dùng. Nó trả giá trị cũ là 2.

Một entry có thể hỗ trợ hoặc không hỗ trợ sửa giá trị. Nếu cài đặt hỗ trợ thì phải giữ đúng quan hệ với map trong phạm vi sử dụng entry hợp lệ. Đừng hứa một entry đã lấy sẽ luôn giữ liên hệ sau mọi lần map thay đổi hay sau khi entry bị loại. Xem [hợp đồng Map.Entry](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.Entry.html).

Vì ví dụ lưu chính các `SimpleEntry` trong list, thao tác thay giá trị tác động vào liên kết thật. Nếu trả entry sao chép rời mà vẫn cho `setValue`, người gọi có thể sửa bản sao mà map không đổi, trái với điều họ trông đợi ở entry của view hỗ trợ sửa.

Khả năng `put`, khả năng xóa và khả năng sửa qua entry cần được quyết định riêng. Một cài đặt không bắt buộc phải hỗ trợ mọi phép tùy chọn chỉ vì hỗ trợ một phép khác, nhưng không được để các đường API đưa ra những lời hứa mâu thuẫn.

### 6.5. Xóa một entry cần khớp cả khóa và giá trị

Khi map còn `a → 20`, xóa entry `a → 999` trả `false`; xóa entry `a → 20` trả `true`.

Đường này dùng khả năng iterator của entry-set có thể xóa phần tử trong list nền. Nếu iterator chỉ duyệt một bản sao hoặc không hỗ trợ xóa, không thể coi các đường xóa mặc định đã hoạt động đầy đủ.

Đối chiếu `equals` theo cả hai chiều với `Map.of("a", 20)` cùng hash bằng nhau kiểm chứng một phần nghĩa Map được kế thừa. Không cần hai đối tượng thuộc cùng lớp cài đặt mới có thể bằng nhau theo nội dung.

### 6.6. Chi phí của biểu diễn vẫn thuộc trách nhiệm lớp con

Với list entry trong ví dụ, tìm khóa và thêm/thay một khóa phải xét lần lượt nhiều liên kết. `get` mặc định cũng tìm như vậy. Không có chỉ mục băm được tạo tự động.

`entryView.clear` được override để gọi đường dọn của list trực tiếp. Nếu chỉ dựa vào xóa từng mục bằng iterator trên một list phải dồn phần tử, có thể phát sinh nhiều công việc lặp không cần thiết.

Đây là một điểm mở rộng có mục đích: giữ nguyên nghĩa view nhưng thay đường thực hiện cho phù hợp biểu diễn. Tối ưu hợp lệ phải bắt đầu từ việc xác định phương thức nào đang gọi phương thức nào, thay vì override ngẫu nhiên nhiều phương thức cùng một lúc.


## 7. Map không cho sửa: phải kiểm soát cả entry và view

### 7.1. Chỉ không override put chưa đóng mọi đường thay đổi

`AbstractMap.put` mặc định ném `UnsupportedOperationException`. Điều đó chưa đủ để kết luận map chỉ đọc nếu entry-set của lớp con vẫn cho xóa hoặc các entry vẫn cho đổi giá trị.

Các đường cần xem gồm:

```text
map.put(...)
map.remove(...)
map.clear()
map.entrySet().iterator().remove()
entry.setValue(...)
map.keySet().remove(...)
map.values().remove(...)
```

Nếu muốn không cho thay đổi, nguồn entry phải có các giới hạn phù hợp trên tất cả đường đã phơi bày.

Một `Set<Map.Entry<K,V>>` không cho thêm/xóa phần tử chưa chắc ngăn được `setValue` của những đối tượng entry bên trong. Giống một list không cho sửa vẫn có thể chứa đối tượng con thay đổi được, lớp bao của set không tự làm mọi entry bất biến.

### 7.2. Chương trình đóng cả đường sửa entry

Tệp `ReadOnlyMapSkeletonDemo.java`:

```java
import java.util.AbstractMap;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Set;

public class ReadOnlyMapSkeletonDemo {
    static final class FrozenMap<K, V> extends AbstractMap<K, V> {
        private final Map<K, V> frozen;

        FrozenMap(Map<? extends K, ? extends V> source) {
            frozen = Collections.unmodifiableMap(new LinkedHashMap<>(source));
        }

        @Override
        public Set<Entry<K, V>> entrySet() {
            return frozen.entrySet();
        }
    }

    public static void main(String[] args) {
        var source = new LinkedHashMap<String, Integer>();
        source.put("x", 1);
        var frozen = new FrozenMap<>(source);
        source.put("y", 2);
        System.out.println("frozen=" + frozen);
        System.out.println("hasSourceAddition=" + frozen.containsKey("y"));

        try {
            frozen.put("z", 3);
        } catch (UnsupportedOperationException ex) {
            System.out.println("put=" + ex.getClass().getSimpleName());
        }
        try {
            frozen.entrySet().iterator().next().setValue(9);
        } catch (UnsupportedOperationException ex) {
            System.out.println("entryWrite=" + ex.getClass().getSimpleName());
        }
        try {
            frozen.keySet().remove("x");
        } catch (UnsupportedOperationException ex) {
            System.out.println("keyRemove=" + ex.getClass().getSimpleName());
        }
        System.out.println("unchanged=" + frozen);
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 ReadOnlyMapSkeletonDemo.java
java ReadOnlyMapSkeletonDemo
```

Stdout:

```text
frozen={x=1}
hasSourceAddition=false
put=UnsupportedOperationException
entryWrite=UnsupportedOperationException
keyRemove=UnsupportedOperationException
unchanged={x=1}
```

Constructor tạo một `LinkedHashMap` riêng từ nguồn rồi bọc bằng `Collections.unmodifiableMap`. `entrySet` được trả từ map đã được bọc đúng cách, nên các entry nhìn qua đó cũng không cung cấp đường sửa giá trị vào dữ liệu nền. Xem [unmodifiableMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#unmodifiableMap(java.util.Map)).

Lớp con chỉ cài `entrySet`; các phép đọc còn lại đi qua khung. `put` mặc định bị từ chối, `setValue` trên entry bị từ chối và xóa khóa x qua view cũng bị từ chối.

Nguồn bên ngoài thêm y sau khi tạo đối tượng không làm map riêng xuất hiện y. Điều này đến từ bước sao chép, không chỉ từ việc bọc không cho sửa.

Ví dụ phục vụ học cách nối một entry-set an toàn vào khung. Nếu chỉ cần một map không cho sửa trong ứng dụng, có thể dùng trực tiếp công cụ có sẵn; không phải lúc nào cũng cần thêm một lớp kế thừa.

### 7.3. Sao chép cấu trúc chưa là sao chép sâu

Bước tạo map mới vẫn giữ các tham chiếu khóa và giá trị. Nếu các đối tượng đó có thể thay đổi, chúng không tự bị đóng băng.

Đặc biệt, khóa phải giữ quy tắc nhận diện phù hợp trong thời gian được dùng làm khóa. Việc chỉ đọc qua một tham chiếu map không sửa được một đối tượng khóa mà nơi khác tiếp tục thay đổi.

Ví dụ dùng khóa chuỗi và giá trị số nguyên để tránh trộn thêm vấn đề dữ liệu con khi quan sát các đường ghi.

### 7.4. Đừng dựa vào entry sau mọi thay đổi của nguồn

Một entry của map có quy tắc sử dụng gắn với view và việc duyệt. Nếu cần một bản ghi độc lập, phải tạo bản sao entry phù hợp; đừng giữ entry rồi mặc định nó luôn là một tay cầm cập nhật hợp lệ sau mọi thao tác cấu trúc.

Cũng không được trả bản sao rời khi API đang hứa một view có thể sửa xuyên về nguồn. Cần chọn đúng giữa “entry độc lập để đọc” và “entry của view map” rồi giữ nhất quán.

## 8. Những lỗi nền làm nhiều phương thức cùng hỏng

### 8.1. Vòng gọi giữa size và entrySet.size

Một map có thể biên dịch được nhưng không thể tính kích thước nếu hai phía gọi lại nhau:

```text
map.size()
    → entrySet().size()
        → map.size()
            → entrySet().size()
                → tiếp tục không có thao tác đọc dữ liệu thật
```

Đó là một vòng đệ quy, không phải hai cách tái sử dụng hợp lệ.

Trong `TinyMap`, `entryView.size` gọi trực tiếp `entries.size`. Đây là điểm chạm dữ liệu thật, giúp đường gọi kết thúc.

Một lỗi cùng nhóm là viết iterator của entry-set bằng cách duyệt `keySet()` của chính map, trong khi `keySet()` mặc định lại xây trên iterator entry-set. Cần vẽ đồ thị phụ thuộc trước khi nối các view qua nhau.

### 8.2. Trả snapshot thay cho live view của một map có thể sửa

Nếu mỗi `entrySet` chỉ trả một tập entry sao chép không nối với nguồn, một view đã lấy trước đó có thể không phản ánh lần thêm/xóa sau. Nếu cho phép xóa qua tập đó, việc xóa cũng chỉ làm đổi bản sao.

Không bắt buộc các lời gọi phải trả cùng danh tính đối tượng view trong mọi cài đặt. Điều cần giữ là quan hệ dữ liệu và khả năng thao tác mà hợp đồng đã hứa.

Trong `TinyMap`, một `entryView` được giữ ổn định và đọc trực tiếp list nền. Trong map chỉ đọc, view trỏ đến map riêng không cho sửa. Cả hai đều tránh một bản sao rời không phù hợp với nghĩa của view.

### 8.3. Lẫn peek với poll hoặc dùng null như dữ liệu hợp lệ của nền Queue

Nếu `peek` xóa phần tử, một lần xem có thể làm mất dữ liệu trước khi người dùng gọi lấy. Nếu `poll` không xóa, `remove` và `clear` không thể giữ nghĩa đúng.

Nếu queue chứa `null`, lớp khung không còn phân biệt kết quả `poll` trả null vì rỗng hay vì một phần tử thật. Đó là lý do yêu cầu không nhận null phải được thực hiện ở đường thêm.

Không trả một phần tử tùy ý để tránh giá trị null khi rỗng. Giá trị báo thất bại phải đúng theo hợp đồng.

### 8.4. Map trùng khóa do chỉ nhìn giá trị

Map cho phép null cần phân biệt “không có khóa” và “có khóa với giá trị null”. Đường `put` chỉ dựa vào kết quả `get` có thể thêm trùng liên kết nếu xử lý sai trường hợp này.

Ví dụ `TinyMap` tìm chính khóa trong các entry. Khi tìm thấy nó thay giá trị, không tạo thêm một entry chỉ vì giá trị cũ là null.

Tương tự, xóa một entry qua view phải xét đúng cả khóa và giá trị. So sánh theo khóa đơn thuần là nghĩa của một phép khác.

### 8.5. Khả năng sửa bị công bố không đồng nhất

Một map có thể hỗ trợ `put` nhưng không hỗ trợ sửa qua entry, hoặc có các phép tùy chọn khác bị từ chối. Điều quan trọng là công bố và giữ đúng mỗi khả năng.

Nếu chỉ cài `put` rồi mặc định `remove` cũng làm được, có thể gặp `UnsupportedOperationException` khi iterator entry-set không hỗ trợ xóa.

Nếu một queue cho phép `poll` nhưng iterator không xóa được, `clear` mặc định vẫn có đường qua `poll`; `remove(Object)` lại là đường khác. Không suy từ một phép xóa thành công sang mọi phép xóa đều được hỗ trợ.

Với các phép không làm thay đổi gì, chẳng hạn xóa khóa không có, cách báo ngoại lệ còn phụ thuộc hợp đồng và đường cài đặt cụ thể. Đừng viết một quy tắc kiểm tra quá rộng rằng mọi lời gọi có tên giống cập nhật đều bắt buộc ném lỗi trong mọi trạng thái.

## 9. Chi phí, phương thức mặc định và tính đồng thời

### 9.1. Tái sử dụng thuật toán không tự có cùng chi phí với HashMap

Trong `TinyMap`, `get` và `containsKey` mặc định phải duyệt list entry. `put` của ví dụ cũng tìm tuyến tính.

Nếu thêm rất nhiều khóa mới bằng `putAll`, mỗi lần `put` có thể tìm trên một map đang lớn dần. Việc lớp khung đã viết vòng lặp không làm tổng công việc ấy tự trở thành tuyến tính.

Các phép so sánh map cũng cần xét chi phí tra cứu của bên được đối chiếu. Một thao tác có vẻ chỉ duyệt một lần vẫn có thể gọi những phép đắt bên trong.

Nên đọc phần mô tả cài đặt của những phương thức được kế thừa, rồi override các điểm cần thiết khi biểu diễn mới có cách làm tốt hơn. Có thể đối chiếu [đường gọi của AbstractMap trong OpenJDK 17](https://raw.githubusercontent.com/openjdk/jdk17u/master/src/java.base/share/classes/java/util/AbstractMap.java).

### 9.2. Nền iterator quyết định nhiều chi phí xóa

Iterator xóa trực tiếp trong một cấu trúc liên kết có thể có đặc tính khác iterator xóa trong một mảng phải dồn phần tử. Khi một phương thức mặc định lặp lại phép xóa, khác biệt đó có thể được nhân lên.

Đó là lý do `entryView.clear` trong ví dụ gọi `entries.clear` thay vì chủ động đi qua từng entry để xóa. Nó giữ đúng kết quả nhưng sử dụng đường dọn phù hợp với nguồn.

Với queue, `clear` mặc định dùng `poll`. Nếu biểu diễn có một cách dọn toàn bộ hiệu quả hơn và giữ đúng yêu cầu, lớp con có thể override. Không tối ưu bằng cách bỏ qua việc giải phóng tham chiếu hoặc làm các view trở nên sai.

### 9.3. Phương thức mặc định của giao diện vẫn là một phần của bề mặt sử dụng

Một lớp Map không chỉ được gọi qua các phương thức xuất hiện trong thân `AbstractMap`. Giao diện còn có những phương thức như `compute`, `merge`, `replaceAll` hoặc các phép cập nhật có điều kiện.

Ví dụ, một đường mặc định có thể cần `put`, `remove` hoặc `Entry.setValue`. Nếu khả năng nền không được hỗ trợ, phương thức tổng hợp cũng có thể không thực hiện được trong trường hợp cần thay đổi.

Không dùng việc lớp đã biên dịch để suy ra mọi phương thức giao diện đều đã được kiểm tra trên biểu diễn mới. Cần đọc hợp đồng và chọn những hành vi thật sự sẽ cung cấp cho bên dùng.

### 9.4. Lớp khung không cung cấp hợp đồng ConcurrentMap hoặc BlockingQueue

Một `get` rồi `put` trong `TinyMap` không tự trở thành một hành động nguyên tử. Các phương thức mặc định thông thường cũng không tự có bảo đảm đồng thời chỉ vì tên trông giống phương thức ở một lớp concurrent.

Tương tự, điều kiện “còn dung lượng” rồi thêm trong `BoundedFifo.offer` là logic cho cách dùng đã công bố. Gọi nó tự do từ nhiều luồng trên `ArrayDeque` riêng chưa được đồng bộ không phải một queue đồng thời hợp lệ.

Nếu cần hỗ trợ nhiều luồng, phải có một thiết kế riêng cho trạng thái, thao tác tổ hợp, iterator và vòng đời. Không thể thêm một vài `synchronized` rời rạc rồi bỏ qua các view hoặc các phương thức kế thừa còn lại.

## 10. Cách kiểm chứng một lớp con của hai khung

### 10.1. Với Queue

Một bộ kiểm tra có ý nghĩa nên bao phủ:

- Khi rỗng: `poll`/`peek` trả null và `remove`/`element` báo đúng ngoại lệ.
- Khi còn chỗ: `offer` và `add` đưa phần tử vào đúng thứ tự.
- Khi đầy nếu có giới hạn: `offer` báo false, `add` báo lỗi phù hợp.
- Null được từ chối đúng ở các đường thêm.
- `poll` thật sự xóa, `peek` thật sự không xóa.
- Iterator có đúng nội dung và khả năng sửa đã công bố.
- `clear`, `remove(Object)` và `addAll` đi qua các đường hợp lệ.
- Trạng thái sau khi thao tác theo lô thất bại được hiểu đúng.

Ví dụ trong bài đã chạy các đường tiêu biểu để người học đối chiếu. Nếu viết cài đặt mới, có thể so chuỗi thao tác với một mô hình tham chiếu có cùng chính sách giới hạn và thứ tự, thay vì chỉ kiểm tra các trường nội bộ.

### 10.2. Với Map

Cần bao phủ ít nhất:

- Thêm khóa mới và thay khóa đã có.
- Giá trị trả về của `put` và `remove`.
- Chính sách null cho khóa và giá trị.
- Không có hai liên kết cho cùng một khóa.
- `get`, `containsKey`, `containsValue`, `size` nhất quán.
- View đã lấy vẫn nhìn đúng nguồn sau các thao tác hợp lệ.
- Xóa qua key-set, values hoặc entry-set đúng với khả năng đã công bố.
- Entry có hoặc không có `setValue` theo đúng chính sách.
- `equals` đối xứng với map tham chiếu và hash tương ứng.
- `clear` và các phép theo lô không tạo trạng thái ngoài hợp đồng.

Không chỉ kiểm tra `put` và `get` rồi bỏ qua view: các view là nền của chính lớp khung nên lỗi ở đó có thể lan sang nhiều phương thức.

### 10.3. Điều ví dụ đã và chưa chứng minh

Ba chương trình trong bài đã được biên dịch và chạy với Java 17. Stdout thể hiện các nhánh chức năng cụ thể, bao gồm trạng thái sau lỗi có chủ ý và khả năng sửa xuyên qua view.

Các ví dụ không đo tốc độ, số byte bộ nhớ hay chứng minh một thuật toán đồng thời. Chúng cũng không thay thế việc kiểm tra sâu hơn nếu cấu trúc được mở rộng sang dữ liệu lớn, khả năng sửa mới hoặc nhiều luồng.

Giữ bằng chứng gắn với điều đã thực sự kiểm tra giúp quyết định lúc nào có thể tái sử dụng phương thức nền và lúc nào phải thiết kế lại.

## 11. Thực hành

### Bài 1: vẽ đường gọi trước khi override

Với queue ví dụ, hãy vẽ đường gọi cho:

1. `add("A")`.
2. `remove()`.
3. `element()`.
4. `clear()`.
5. `remove("A")`.

Vì sao mục 2 và mục 5 không nhất thiết có cùng đường thực hiện? Nếu bỏ khả năng `iterator.remove`, phép nào vẫn còn làm được và phép nào phải xem lại?

Hướng giải thích: `remove()` dựa vào `poll`, còn `remove(Object)` là thao tác tìm phần tử phù hợp. Các khả năng sửa phải được xét riêng.

### Bài 2: thêm theo lô khi chỉ còn hai chỗ

Queue đang rỗng, dung lượng 2. Gọi `addAll` với ba phần tử không null.

Hãy dự đoán ngoại lệ và trạng thái dữ liệu sau đó theo cài đặt mặc định của `AbstractQueue`. Nếu nghiệp vụ yêu cầu cả lô cùng vào hoặc không phần tử nào vào, cần thiết kế ranh giới nào thay vì giả định lớp khung sẽ hoàn tác?

Không sửa bằng cách âm thầm bỏ phần tử cuối mà báo thành công.

### Bài 3: sửa vòng đệ quy kích thước

Một lớp con giữ dữ liệu trong list `records`. `map.size()` dùng mặc định, nhưng `entrySet().size()` lại gọi `map.size()`.

Hãy chỉ ra vì sao không có điểm kết thúc. Thao tác nào cần chạm trực tiếp `records.size()`? Vì sao chỉ đổi tên một trong hai phương thức không giải quyết quan hệ gọi?

Hướng giải thích: cần một thao tác nền đọc trạng thái thật, không phải hai lớp view chỉ gọi lại nhau.

### Bài 4: map chỉ đọc bị sửa qua entry

Một lớp không override `put`, nhưng trả `Collections.unmodifiableSet` của một set chứa các `SimpleEntry` có thể sửa.

Nếu lấy một entry rồi gọi `setValue`, việc set không cho thêm/xóa có đủ chặn thay đổi giá trị không? Hãy đối chiếu với cách `FrozenMap` trong bài lấy entry-set từ map đã được bọc đúng cách.

Hướng giải thích: phải bảo vệ cả thành phần entry, không chỉ tư cách thành viên trong set.

### Bài 5: giá trị null và nhận diện khóa

Map có liên kết `b → null`. Một cài đặt `put` mới quyết định “nếu get(b) bằng null thì thêm entry mới”.

Vì sao đường đó có thể làm hỏng điều kiện khóa duy nhất? Cần tìm sự tồn tại theo khóa thế nào? Nếu cấm null thay vì hỗ trợ, cần thực hiện chính sách ở những đường nào?

Hướng giải thích: giá trị thiếu và khóa thiếu là hai khái niệm khác nhau khi map nhận null.

### Các câu hỏi cần trả lời trước khi công bố lớp con

1. Những thao tác nào là nền và chúng đọc dữ liệu thật ở đâu?
2. Những phương thức kế thừa nào gọi các thao tác đó?
3. Có vòng gọi qua view nào không?
4. Null, thứ tự và giá trị báo thất bại có nhất quán không?
5. Iterator và entry mở những đường sửa nào?
6. View nối với dữ liệu nguồn hay là bản sao theo hợp đồng nào?
7. Chi phí của phương thức mặc định có phù hợp với biểu diễn không?
8. Khả năng đồng thời và các thao tác tùy chọn đã được phát biểu đúng chưa?

Dùng `AbstractQueue` và `AbstractMap` hiệu quả là hiểu đồ thị gọi và giữ đúng nền cài đặt. Khi phần nền nhất quán, lớp khung giảm được nhiều mã lặp; khi phần nền sai, lỗi có thể xuất hiện ở những phương thức mà lớp con không tự viết.
