# Thao tác đầu–cuối và view đảo thứ tự của LinkedHashMap từ Java 21

## 1. Bài toán: map đã có thứ tự, làm việc với hai đầu như thế nào?

`LinkedHashMap` giữ các cặp khóa–giá trị theo một thứ tự duyệt xác định. Với một danh sách công việc theo mã, ta có thể muốn xem công việc đầu tiên, lấy công việc cuối ra khỏi danh sách, đưa một mã đang có lên đầu hoặc hiển thị cùng dữ liệu theo chiều ngược lại.

Những yêu cầu đó khác với tra cứu `get(key)`. `get` tìm theo khóa, còn thao tác đầu–cuối tìm theo **vị trí trong thứ tự duyệt**. Khóa đầu tiên không nhất thiết nhỏ nhất, tên đầu tiên không nhất thiết đứng trước theo bảng chữ cái và giá trị cuối không nhất thiết lớn nhất.

Từ Java 21, `LinkedHashMap` triển khai `SequencedMap`. Nhờ đó, chương trình có API thống nhất để xem, thêm, đổi vị trí hoặc lấy ra mapping ở hai đầu và lấy một khung nhìn đảo thứ tự. Đây là API thư viện chuẩn, không cần bật `--enable-preview`. Các ví dụ trong bài cần JDK 21 trở lên; chúng không biên dịch với `--release 17`. Có thể đối chiếu thời điểm bổ sung tại [LinkedHashMap — Java 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/LinkedHashMap.html).

Ba khái niệm sẽ được dùng xuyên suốt:

- **Thứ tự duyệt (encounter order):** thứ tự nhìn thấy các entry khi duyệt map.
- **Đầu và cuối:** entry đứng đầu hoặc cuối trong thứ tự của đối tượng đang được gọi.
- **Khung nhìn đảo (`reversed` view):** một cách nhìn cùng map theo chiều ngược lại, có liên kết với dữ liệu gốc.

Hãy hình dung một map có thứ tự khóa A, B, C:

```text
map:          đầu → A → B → C ← cuối
map.reversed: đầu → C → B → A ← cuối
```

Chỉ việc tạo view đảo không di chuyển A, B hay C trong map gốc. Nó thay đổi chiều quan sát. Khi gọi một thao tác có ý nghĩa đầu–cuối trên view, ý nghĩa đó được tính theo chiều của view.

## 2. Nhận diện đúng các API mới

### 2.1. Các thao tác trên cả mapping

Mỗi mapping, còn gọi là một entry, gồm cả khóa và giá trị. Với map có kiểu khóa `K`, giá trị `V`, các phương thức chính là:

| Phương thức | Kiểu kết quả | Có thay đổi map không? | Ý nghĩa |
|---|---|---|---|
| `firstEntry()` | `Map.Entry<K,V>` hoặc `null` | Không loại/thêm entry | Xem mapping đầu |
| `lastEntry()` | `Map.Entry<K,V>` hoặc `null` | Không loại/thêm entry | Xem mapping cuối |
| `pollFirstEntry()` | `Map.Entry<K,V>` hoặc `null` | Có nếu map không rỗng | Lấy và loại mapping đầu |
| `pollLastEntry()` | `Map.Entry<K,V>` hoặc `null` | Có nếu map không rỗng | Lấy và loại mapping cuối |
| `putFirst(k, v)` | Giá trị cũ kiểu `V`, có thể `null` | Có thể thêm/cập nhật/đổi vị trí | Đặt mapping ở đầu |
| `putLast(k, v)` | Giá trị cũ kiểu `V`, có thể `null` | Có thể thêm/cập nhật/đổi vị trí | Đặt mapping ở cuối |
| `reversed()` | `SequencedMap<K,V>` | Tạo view, không tự đảo dữ liệu gốc | Nhìn map theo thứ tự ngược |

`LinkedHashMap` thông thường hỗ trợ các thao tác thay đổi trên đây. Khi viết mã nhận một `SequencedMap` bất kỳ, cần nhớ một số thao tác thay đổi là tùy chọn: một cách triển khai có thể không hỗ trợ việc đặt tùy ý mapping vào đầu/cuối. Tên interface không xóa bỏ các ràng buộc của đối tượng thực tế.

### 2.2. Các view có thứ tự

Ba phương thức bổ sung cho phép làm việc với riêng khóa, riêng giá trị hoặc toàn entry bằng kiểu có thao tác đầu–cuối:

| Phương thức | Kiểu trả về | Một phần tử của view là gì? |
|---|---|---|
| `sequencedKeySet()` | `SequencedSet<K>` | Một khóa |
| `sequencedValues()` | `SequencedCollection<V>` | Một giá trị |
| `sequencedEntrySet()` | `SequencedSet<Map.Entry<K,V>>` | Một entry |

`SequencedSet` kết hợp tính chất không trùng phần tử của `Set` với một thứ tự duyệt xác định. `SequencedCollection` chỉ mô tả tập hợp có thứ tự, không tự đặt điều kiện duy nhất. Vì nhiều khóa khác nhau có thể cùng giá trị, view giá trị của map là collection, không phải set.

Các view cũ `keySet()`, `values()`, `entrySet()` vẫn duyệt theo thứ tự của `LinkedHashMap`. Việc có API mới không làm chúng mất thứ tự. Điểm khác là kiểu trả về của các phương thức mới thể hiện được khả năng thao tác đầu–cuối trong mã nguồn.

### 2.3. Kiểu khai báo quyết định phương thức có thể gọi

Đoạn sau là mã minh họa đặt bên trong một phương thức, không phải một tệp Java độc lập:

```java
LinkedHashMap<String, Integer> linked = new LinkedHashMap<>();
Map<String, Integer> general = linked;
SequencedMap<String, Integer> ordered = linked;

ordered.firstEntry();
linked.putFirst("A", 1);
// general.firstEntry(); // Không biên dịch: Map không khai báo phương thức này.
```

`general` và `ordered` có thể trỏ tới cùng đối tượng. Tuy nhiên, trình biên dịch xét phương thức theo kiểu khai báo của biến. Nếu một API cần dùng thứ tự và hai đầu, nhận hoặc trả `SequencedMap` sẽ thể hiện yêu cầu rõ hơn so với chỉ dùng `Map`.

Không nên ép kiểu một `Map` bất kỳ thành `SequencedMap` để làm cho mã biên dịch. Chẳng hạn, một đối tượng `HashMap` không tự trở thành map có thứ tự khi bị ép kiểu. Cần biết đúng loại đối tượng hoặc thiết kế chữ ký API phù hợp.

## 3. Xem hai đầu và lấy hai đầu ra là hai hành động khác nhau

### 3.1. firstEntry và lastEntry chỉ quan sát

`firstEntry()` trả entry đầu hiện tại; `lastEntry()` trả entry cuối hiện tại. Chúng không lấy entry ra khỏi map. Trong chế độ thứ tự truy cập, hai phép quan sát này cũng không đóng vai trò một lần `get` để đưa entry thành mới được dùng.

Với thứ tự A, B, C, gọi `firstEntry()` rồi `lastEntry()` vẫn để thứ tự A, B, C và vẫn có ba entry. Khi chỉ cần xem mục sắp xử lý mà chưa muốn xóa, đây là nhóm thao tác phù hợp.

### 3.2. pollFirstEntry và pollLastEntry vừa lấy vừa loại

`pollFirstEntry()` trả entry đầu rồi loại mapping tương ứng. `pollLastEntry()` làm tương tự ở cuối. Nếu chỉ in kết quả của một lời gọi `poll`, map đã thay đổi dù không có thêm câu lệnh `remove`.

Ví dụ, với thứ tự A, B, C:

```text
firstEntry()     → trả A, map vẫn [A, B, C]
pollFirstEntry() → trả A, map còn [B, C]
pollLastEntry()  → trả C, map còn [B]
```

Đây là các thao tác theo mapping: không chỉ bỏ một giá trị ra khỏi một danh sách rời rạc. Sau khi poll A, tra cứu khóa A trên map sẽ không còn mapping đó.

### 3.3. Map rỗng trả null cho cả bốn phương thức

Cả `firstEntry`, `lastEntry`, `pollFirstEntry`, `pollLastEntry` đều trả `null` khi map rỗng. Không được gọi ngay `map.firstEntry().getKey()` nếu chưa biết có entry. Có thể lưu kết quả vào biến, kiểm tra khác `null`, rồi mới đọc khóa và giá trị.

Việc map cho phép giá trị `null` không làm kết quả entry trở nên nhập nhằng theo cách của `get`. Một map chứa mapping `A → null` có `firstEntry()` khác `null`; chỉ `entry.getValue()` là `null`. Tương tự, nếu khóa cũng là `null`, entry vẫn tồn tại.

## 4. putFirst và putLast: vừa cập nhật vừa định vị

### 4.1. Khóa chưa có: thêm vào đầu hoặc cuối

`putFirst(k, v)` thêm mapping mới vào đầu thứ tự. `putLast(k, v)` thêm mapping mới vào cuối. Nếu không có mapping cũ cho khóa, giá trị trả về là `null`.

Không có chỉ số số nguyên nào được truyền vào. Đây không phải `List.add(index, element)` và cũng không có thao tác chèn trực tiếp vào vị trí thứ 5. Khi gọi `get(0)` trên một map có khóa số nguyên, số 0 vẫn là khóa cần tìm, không phải chỉ số của entry đầu.

### 4.2. Khóa đã có: giữ một mapping, đổi giá trị và chuyển vị trí

Nếu khóa đã tồn tại, `putFirst` hoặc `putLast` cập nhật giá trị của mapping đó và chuyển nó đến đầu/cuối nếu cần. Chúng không tạo một bản sao của khóa ở vị trí mới. Map vẫn tuân theo quy tắc một khóa tương ứng nhiều nhất một mapping.

Giá trị trả về là **giá trị cũ**, không phải entry mới, không phải vị trí và cũng không phải cờ cho biết có di chuyển hay không. Nếu giá trị cũ là `null`, kết quả `null` không đủ để phân biệt với trường hợp khóa trước đó chưa có. Khi cần biết sự tồn tại trước thao tác, hãy kiểm tra theo hợp đồng phù hợp trước khi cập nhật.

### 4.3. Khác với put thông thường trong chế độ thứ tự chèn

Ở một `LinkedHashMap` mặc định, `put` khóa đã có chỉ thay giá trị, giữ vị trí của khóa. `putFirst` và `putLast` thể hiện yêu cầu vị trí rõ ràng nên vẫn có thể thay đổi vị trí đó.

| Trạng thái ban đầu `[A, B, C]` | Thứ tự sau thao tác |
|---|---|
| `put("B", newValue)` trên map theo thứ tự chèn | `[A, B, C]` |
| `putFirst("B", newValue)` | `[B, A, C]` |
| `putLast("B", newValue)` | `[A, C, B]` |

Bảng trên xét ba lần thử độc lập, cùng điểm xuất phát. Không đọc nó thành ba thao tác nối tiếp nhau. Chế độ thứ tự truy cập sẽ được xét riêng vì `put` thông thường trong chế độ đó còn có ý nghĩa làm mới truy cập.

## 5. Chương trình 1: thêm, chuyển vị trí, xem và poll

Lưu chương trình đầy đủ vào `LinkedHashMapEndsDemo.java`. Map được tạo bằng constructor mặc định nên dùng thứ tự chèn. Ví dụ dùng tên khóa để dễ quan sát vị trí; không có bước sắp xếp theo tên.

```java
import java.util.LinkedHashMap;

public class LinkedHashMapEndsDemo {
    public static void main(String[] args) {
        LinkedHashMap<String, Integer> map = new LinkedHashMap<>();
        map.put("beta", 2);
        map.put("delta", 4);

        System.out.println("putFirstNew=" + map.putFirst("alpha", 1));
        System.out.println("putLastNew=" + map.putLast("omega", 9));
        System.out.println("afterNew=" + map);

        System.out.println("putFirstExisting=" + map.putFirst("delta", 40));
        System.out.println("afterMoveFirst=" + map);
        System.out.println("putLastExisting=" + map.putLast("alpha", 10));
        System.out.println("afterMoveLast=" + map);

        map.put("beta", 20);
        System.out.println("afterPlainPut=" + map);
        System.out.println("first=" + map.firstEntry());
        System.out.println("last=" + map.lastEntry());
        System.out.println("beforePollSize=" + map.size());

        System.out.println("pollFirst=" + map.pollFirstEntry());
        System.out.println("pollLast=" + map.pollLastEntry());
        System.out.println("remaining=" + map);
        System.out.println("size=" + map.size());
    }
}
```

Biên dịch và chạy bằng JDK 21 trở lên:

```shell
javac --release 21 -encoding UTF-8 LinkedHashMapEndsDemo.java
java LinkedHashMapEndsDemo
```

Stdout:

```text
putFirstNew=null
putLastNew=null
afterNew={alpha=1, beta=2, delta=4, omega=9}
putFirstExisting=4
afterMoveFirst={delta=40, alpha=1, beta=2, omega=9}
putLastExisting=1
afterMoveLast={delta=40, beta=2, omega=9, alpha=10}
afterPlainPut={delta=40, beta=20, omega=9, alpha=10}
first=delta=40
last=alpha=10
beforePollSize=4
pollFirst=delta=40
pollLast=alpha=10
remaining={beta=20, omega=9}
size=2
```

### 5.1. Theo dõi thứ tự thay vì chỉ nhìn giá trị

Ban đầu có beta, delta. Thêm alpha ở đầu và omega ở cuối tạo thứ tự `[alpha, beta, delta, omega]`. Hai lần thêm khóa mới trả về `null`.

`putFirst("delta", 40)` trả giá trị cũ `4`, thay thành `40` và kéo delta lên đầu. Sau đó `putLast("alpha", 10)` trả `1`, thay thành `10` và đưa alpha xuống cuối. Số entry vẫn bốn vì đây là hai khóa đã có.

Lần `put("beta", 20)` chỉ cập nhật beta tại chỗ. Vì map này theo thứ tự chèn, kết quả vẫn có thứ tự `[delta, beta, omega, alpha]`.

`first=delta=40` và `last=alpha=10` là cách in một entry dưới dạng `khóa=giá trị`; các dòng đó không có nghĩa phương thức trả về một chuỗi có hai dấu bằng. Kiểu kết quả thật là `Map.Entry<String, Integer>`.

### 5.2. Poll để lấy và loại

Hai lời gọi xem đầu/cuối không đổi `beforePollSize=4`. Sau `pollFirstEntry`, delta bị loại. Sau `pollLastEntry`, alpha bị loại. Map còn beta và omega, có kích thước hai.

Quan sát này cũng giải thích vì sao không được dùng `poll` chỉ để xem “công việc tiếp theo là gì” nếu vẫn muốn giữ công việc đó. Chọn `firstEntry` hoặc `lastEntry` khi ý định chỉ là đọc.

## 6. Chương trình 2: entry trả về là snapshot, không phải cửa cập nhật map

### 6.1. Bản chụp của mapping tại thời điểm gọi

Bốn phương thức trả entry trực tiếp trên `SequencedMap` — `firstEntry`, `lastEntry`, `pollFirstEntry`, `pollLastEntry` — trả một **bản chụp (snapshot)** của mapping tại thời điểm gọi. Chúng không hỗ trợ `setValue` để thay giá trị trong map. Hợp đồng này được mô tả tại [SequencedMap — Java 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/SequencedMap.html).

Không nên suy ra rằng hễ một giá trị có kiểu `Map.Entry` thì đều sửa được map qua `setValue`. Cách lấy entry quyết định hợp đồng kết nối với map. Đặc biệt, entry snapshot khác với entry đang được cung cấp trong một lượt duyệt `entrySet()`.

Chương trình sau lưu một snapshot, cập nhật map, thử `setValue` trên snapshot và kiểm tra trường hợp khóa/giá trị `null`. Lưu vào `LinkedHashMapEntrySnapshotDemo.java`.

```java
import java.util.LinkedHashMap;
import java.util.Map;

public class LinkedHashMapEntrySnapshotDemo {
    public static void main(String[] args) {
        LinkedHashMap<String, String> map = new LinkedHashMap<>();
        System.out.println("emptyFirst=" + map.firstEntry());
        System.out.println("emptyLast=" + map.lastEntry());
        System.out.println("emptyPollFirst=" + map.pollFirstEntry());
        System.out.println("emptyPollLast=" + map.pollLastEntry());

        map.put(null, null);
        Map.Entry<String, String> snapshot = map.firstEntry();
        System.out.println("snapshot=" + snapshot);
        System.out.println("entryExists=" + (snapshot != null));
        System.out.println("keyIsNull=" + (snapshot.getKey() == null));
        System.out.println("valueIsNull=" + (snapshot.getValue() == null));

        map.put(null, "updated");
        System.out.println("currentFirst=" + map.firstEntry());
        System.out.println("oldSnapshot=" + snapshot);
        try {
            snapshot.setValue("changed");
            throw new AssertionError("Expected UnsupportedOperationException");
        } catch (UnsupportedOperationException expected) {
            System.out.println("setValue=UnsupportedOperationException");
        }

        Map.Entry<String, String> removed = map.pollFirstEntry();
        System.out.println("removed=" + removed);
        System.out.println("emptyAfterPoll=" + map.isEmpty());
        System.out.println("removedValue=" + removed.getValue());
    }
}
```

Biên dịch và chạy bằng JDK 21 trở lên:

```shell
javac --release 21 -encoding UTF-8 LinkedHashMapEntrySnapshotDemo.java
java LinkedHashMapEntrySnapshotDemo
```

Stdout:

```text
emptyFirst=null
emptyLast=null
emptyPollFirst=null
emptyPollLast=null
snapshot=null=null
entryExists=true
keyIsNull=true
valueIsNull=true
currentFirst=null=updated
oldSnapshot=null=null
setValue=UnsupportedOperationException
removed=null=updated
emptyAfterPoll=true
removedValue=updated
```

### 6.2. Đừng nhầm entry null với khóa hoặc giá trị null

Bốn dòng đầu đều in `null` vì map đang rỗng. Sau `map.put(null, null)`, `snapshot` là một entry có thật, được in là `null=null`. Vì thế:

- `snapshot != null` là `true`.
- `snapshot.getKey() == null` là `true`.
- `snapshot.getValue() == null` cũng là `true`.

Đây là ba phép kiểm tra khác nhau. Với API trả toàn entry, một mapping có giá trị `null` vẫn phân biệt được với việc không có mapping ở đầu map.

Sau khi cập nhật khóa `null` thành giá trị `updated`, entry hiện tại là `null=updated`, còn snapshot cũ vẫn là `null=null`. Nó không phải một biến tự đồng bộ với mọi lần thay giá trị của map.

### 6.3. setValue và tính độc lập của bản chụp

Lời gọi `snapshot.setValue("changed")` ném `UnsupportedOperationException`. Muốn cập nhật mapping cần gọi API của map theo ý nghĩa mong muốn: giữ vị trí theo chế độ của `put`, đặt lên đầu bằng `putFirst`, hoặc đặt xuống cuối bằng `putLast`.

Sau `pollFirstEntry`, map rỗng nhưng đối tượng `removed` vẫn cho đọc được `updated`. Đó là kết quả mô tả mapping vừa bị lấy ra, không phải một entry đang còn thuộc map.

Snapshot không đồng nghĩa với sao chép sâu mọi đối tượng. Nếu khóa hoặc giá trị là đối tượng có thể thay đổi, bản chụp vẫn có thể chứa tham chiếu đến chính đối tượng đó. Ví dụ ở đây dùng `String`, nên thao tác `map.put` thay tham chiếu giá trị bằng chuỗi khác; snapshot vẫn giữ tham chiếu cũ. Không dùng kết luận này để khẳng định một giá trị có thể thay đổi đã được nhân bản.

### 6.4. Không đánh đồng mọi cách lấy entry

Ba trường hợp cần tách biệt:

| Cách lấy entry | Điều cần biết |
|---|---|
| `map.firstEntry()` hoặc ba phương thức entry đầu–cuối còn lại | Snapshot, không hỗ trợ sửa map qua `setValue` |
| Entry trong khi duyệt `map.entrySet()` hoặc `sequencedEntrySet()` | Có kết nối với mapping theo hợp đồng duyệt; `LinkedHashMap` cho phép cập nhật giá trị qua `setValue` trong phạm vi phù hợp |
| `map.sequencedEntrySet().getFirst()` | Không lấy bảo đảm snapshot hay khả năng `setValue` của `firstEntry()` áp sang cách này; `SequencedMap` không quy định chung khả năng kết nối của entry lấy theo cách đó |

Trong bài, ví dụ view chỉ đọc và in entry lấy bằng `getFirst`; không dựa vào giả định rằng `setValue` của entry đó phải hoạt động giống một loại entry khác.

## 7. reversed(): đảo chiều nhìn, cùng một dữ liệu

### 7.1. Đầu của view là cuối của map gốc

Đặt tên `reverse = map.reversed()` chỉ tạo thêm một cách thao tác trên dữ liệu đang có. Với `LinkedHashMap`, các thay đổi được phép qua view được truyền vào map gốc; thay đổi map gốc cũng xuất hiện trên view. Đây là đặc tính view liên kết, không phải hành vi của một bản sao.

Mối quan hệ giữa các thao tác có vị trí là:

| Gọi trên `reverse` | Vị trí tương ứng trong `map` gốc |
|---|---|
| `reverse.firstEntry()` | Xem cuối map gốc |
| `reverse.lastEntry()` | Xem đầu map gốc |
| `reverse.pollFirstEntry()` | Lấy và loại cuối map gốc |
| `reverse.pollLastEntry()` | Lấy và loại đầu map gốc |
| `reverse.putFirst(k, v)` | Đặt mapping ở cuối map gốc |
| `reverse.putLast(k, v)` | Đặt mapping ở đầu map gốc |

Nếu khóa đã tồn tại thì phép đặt vẫn cập nhật giá trị và đổi vị trí tương ứng, không tạo một entry thứ hai. Từ “đầu” và “cuối” luôn phải gắn với chiều của đối tượng nhận lời gọi.

### 7.2. Tạo view không đảo lại cấu trúc gốc

Giả sử map gốc là `[A, B, C]`. Sau khi lấy view đảo, map gốc vẫn duyệt `[A, B, C]`; view duyệt `[C, B, A]`. Cả hai nhìn thấy cùng ba mapping. Không có giai đoạn map gốc bị thay thành `[C, B, A]` chỉ vì đã gọi `reversed()`.

Điều này phù hợp khi muốn hiển thị cùng một tập dữ liệu theo hai chiều hoặc lấy từ đầu/cuối tương ứng mà không xây một map chứa bản sao. Nhưng trả view cho nơi khác cũng có nghĩa là trao một đường thao tác liên quan đến map gốc. `reverse.clear()` trên một view sửa được sẽ xóa dữ liệu của map gốc.

### 7.3. put thông thường trên view không đồng nghĩa putLast của view

Đây là một điểm dễ suy luận sai: vì đang nhìn theo chiều đảo, người đọc có thể nghĩ mọi `reverse.put(k, v)` với khóa mới sẽ thêm vào cuối view. Với view của `LinkedHashMap`, `put` thông thường được thực hiện theo hành vi của map gốc. Trong map theo thứ tự chèn, khóa mới được thêm cuối **map gốc**, nên xuất hiện đầu **view đảo**.

Muốn chỉ rõ vị trí trong view, hãy dùng `reverse.putFirst` hoặc `reverse.putLast`. Không tự gán ý nghĩa “thêm cuối view” cho `put` chỉ vì một loại collection khác có cách thêm phần tử như vậy. Mã nguồn [LinkedHashMap trong OpenJDK 21](https://raw.githubusercontent.com/openjdk/jdk21u/master/src/java.base/share/classes/java/util/LinkedHashMap.java) cho thấy view chuyển tiếp `put` đến map gốc, còn `putFirst` và `putLast` đổi đầu tương ứng.

Ở chế độ thứ tự chèn, cập nhật khóa đã có qua `reverse.put` vẫn không tự di chuyển khóa đó. Ở chế độ thứ tự truy cập, thao tác này còn tạo truy cập theo chính sách của map gốc. Phần sau sẽ xét trường hợp thứ tự truy cập bằng một chương trình riêng.

## 8. Chương trình 3: sửa hai chiều và tạo bản sao độc lập

Lưu chương trình đầy đủ vào `LinkedHashMapReversedDemo.java`. `reverse` là view; `copy` là một map mới được tạo từ thứ tự đang quan sát qua view.

```java
import java.util.LinkedHashMap;
import java.util.SequencedMap;

public class LinkedHashMapReversedDemo {
    public static void main(String[] args) {
        LinkedHashMap<String, Integer> map = new LinkedHashMap<>();
        map.put("A", 1);
        map.put("B", 2);
        map.put("C", 3);
        SequencedMap<String, Integer> reverse = map.reversed();
        LinkedHashMap<String, Integer> copy = new LinkedHashMap<>(reverse);

        System.out.println("original=" + map);
        System.out.println("reverse=" + reverse);
        System.out.println("reverseFirst=" + reverse.firstEntry());
        System.out.println("reverseLast=" + reverse.lastEntry());

        reverse.putFirst("X", 24);
        System.out.println("afterReversePutFirst=" + map);
        reverse.putLast("Y", 25);
        System.out.println("afterReversePutLast=" + map);
        reverse.put("Z", 26);
        System.out.println("afterReversePlainPut=" + map);
        System.out.println("reverseNow=" + reverse);

        reverse.put("B", 20);
        reverse.remove("A");
        map.putLast("W", 23);
        System.out.println("sharedOriginal=" + map);
        System.out.println("sharedReverse=" + reverse);

        System.out.println("reversePollFirst=" + reverse.pollFirstEntry());
        System.out.println("reversePollLast=" + reverse.pollLastEntry());
        System.out.println("remainingOriginal=" + map);
        System.out.println("remainingReverse=" + reverse);
        System.out.println("twiceReversedOrder=" + reverse.reversed().keySet());
        System.out.println("equalMappings=" + map.equals(reverse));
        System.out.println("independentCopy=" + copy);
    }
}
```

Biên dịch và chạy bằng JDK 21 trở lên:

```shell
javac --release 21 -encoding UTF-8 LinkedHashMapReversedDemo.java
java LinkedHashMapReversedDemo
```

Stdout:

```text
original={A=1, B=2, C=3}
reverse={C=3, B=2, A=1}
reverseFirst=C=3
reverseLast=A=1
afterReversePutFirst={A=1, B=2, C=3, X=24}
afterReversePutLast={Y=25, A=1, B=2, C=3, X=24}
afterReversePlainPut={Y=25, A=1, B=2, C=3, X=24, Z=26}
reverseNow={Z=26, X=24, C=3, B=2, A=1, Y=25}
sharedOriginal={Y=25, B=20, C=3, X=24, Z=26, W=23}
sharedReverse={W=23, Z=26, X=24, C=3, B=20, Y=25}
reversePollFirst=W=23
reversePollLast=Y=25
remainingOriginal={B=20, C=3, X=24, Z=26}
remainingReverse={Z=26, X=24, C=3, B=20}
twiceReversedOrder=[B, C, X, Z]
equalMappings=true
independentCopy={C=3, B=2, A=1}
```

### 8.1. Ba đối tượng, hai kiểu quan hệ dữ liệu

Ngay sau khi tạo:

```text
map:     {A=1, B=2, C=3}
reverse: {C=3, B=2, A=1}   ← nhìn cùng dữ liệu theo chiều ngược
copy:    {C=3, B=2, A=1}   ← map mới, lấy thứ tự đó lúc tạo
```

`reverse` và `copy` có thể được in giống nhau ở thời điểm đầu, nhưng hành vi sau đó khác nhau. Cách tạo mới quyết định tính độc lập, không phải hình thức dòng in.

`new LinkedHashMap<>(reverse)` duyệt các mapping của view đảo và đưa chúng vào một map theo thứ tự chèn mới. Các thay đổi cấu trúc hay thay tham chiếu giá trị trong map gốc sau đó không tự cập nhật map mới. Đây vẫn là bản sao nông: các đối tượng khóa/giá trị có thể được dùng chung nếu chúng có thể thay đổi.

### 8.2. Đặt đầu và cuối qua view

Ba thao tác đầu cho các kết quả đáng chú ý:

| Thao tác | Thứ tự map gốc sau thao tác | Điều đã xảy ra |
|---|---|---|
| `reverse.putFirst("X", 24)` | `[A, B, C, X]` | X đứng đầu view, tức cuối gốc |
| `reverse.putLast("Y", 25)` | `[Y, A, B, C, X]` | Y đứng cuối view, tức đầu gốc |
| `reverse.put("Z", 26)` | `[Y, A, B, C, X, Z]` | `put` thông thường thêm cuối gốc |

Vì vậy `reverseNow` in thứ tự `[Z, X, C, B, A, Y]`. Không cần đảo thủ công một danh sách khóa sau mỗi thay đổi; view lấy thứ tự ngược từ cùng dữ liệu đang được cập nhật.

### 8.3. Cập nhật giá trị và loại entry đều truyền qua

`reverse.put("B", 20)` đổi mapping B của map gốc thành B=20. `reverse.remove("A")` loại mapping A của map gốc. `map.putLast("W", 23)` thêm W vào cuối gốc và lập tức làm W đứng đầu view.

`reverse.pollFirstEntry()` sau đó lấy W ra, vì W đang đầu view. `reverse.pollLastEntry()` lấy Y ra, vì Y đang cuối view. Map gốc còn `[B, C, X, Z]`, view còn `[Z, X, C, B]`.

Đây là cùng một tập mapping được quan sát hai chiều, không phải hai map cần đồng bộ bằng mã riêng. Nếu chương trình có nhiều biến giữ các view, phải nhớ rằng một lần loại mapping ở bất cứ đường nào cũng tác động đến các đường nhìn còn lại.

### 8.4. Đảo hai lần và phép bằng nhau

`reverse.reversed()` cho thứ tự trở lại như map gốc. Ví dụ kiểm tra thứ tự `[B, C, X, Z]`, không dùng so sánh danh tính đối tượng bằng `==` để định nghĩa ý nghĩa đảo hai lần cho mọi cách triển khai `SequencedMap`.

`map.equals(reverse)` in `true` dù thứ tự duyệt ngược nhau. Hợp đồng bằng nhau của map kiểm tra các mapping, không kiểm tra thứ tự duyệt. Nếu cần kiểm tra thứ tự, hãy lấy một danh sách khóa theo thứ tự hiện tại để so sánh; không dùng `Map.equals` như bằng chứng hai chiều duyệt giống nhau.

`independentCopy={C=3, B=2, A=1}` vẫn giữ dữ liệu và thứ tự tại thời điểm bản sao được tạo. B ở bản sao vẫn là 2, A vẫn có, còn X/Y/Z/W chưa từng được đưa vào bản sao. Điều này phân biệt rất rõ **view theo dõi hiện tại** với **bản sao tại một thời điểm**.

## 9. Các sequenced view của khóa, giá trị và entry

### 9.1. Đầu–cuối của từng view cùng bám theo thứ tự map

Với map `{A=7, B=7, C=9}`:

| View | Thứ tự phần tử | Phần tử đầu | Phần tử cuối |
|---|---|---|---|
| `sequencedKeySet()` | `[A, B, C]` | A | C |
| `sequencedValues()` | `[7, 7, 9]` | 7 ứng với A | 9 ứng với C |
| `sequencedEntrySet()` | `[A=7, B=7, C=9]` | A=7 | C=9 |

Mỗi view hỗ trợ `getFirst`, `getLast` để xem phần tử theo thứ tự của view. Chúng không phải tên khác của `Map.firstEntry`: kiểu phần tử trả về phụ thuộc view. `keys.getFirst()` trả khóa, `values.getFirst()` trả giá trị, còn `entries.getFirst()` trả entry.

Gọi `reversed()` trên một view đảo thứ tự riêng cách nhìn đó. Chẳng hạn, `map.sequencedKeySet().reversed()` cho thứ tự khóa giống `map.reversed().sequencedKeySet()`. Cả hai vẫn liên quan đến cùng map; không nên coi một đường gọi dài hơn là đã tạo được bản sao độc lập.

### 9.2. Xóa từ view là xóa mapping trong map

Các view này của `LinkedHashMap` hỗ trợ loại phần tử. `keys.removeFirst()` loại khóa đầu và mapping của nó; `values.removeLast()` loại giá trị cuối cùng với mapping đang giữ giá trị đó; `entries.removeFirst()` loại entry đầu.

Giá trị có thể trùng nhau nên vị trí rất quan trọng. Với A=7, B=7, C=9, `values.removeFirst()` trả 7 và loại mapping A=7, không loại tất cả mapping có giá trị 7. B=7 vẫn có. Sau đó các view khóa và entry cũng tự phản ánh việc A đã rời map.

### 9.3. Không hỗ trợ thêm qua view không có nghĩa map chỉ đọc

Map sửa được không đồng nghĩa mọi thao tác thêm của mọi collection view đều được hỗ trợ. Trên các sequenced view của `LinkedHashMap`, việc thêm phần tử bằng `addFirst`, `addLast` không được hỗ trợ và ném `UnsupportedOperationException`.

Với view khóa hoặc giá trị, thêm một phần đơn lẻ còn không mô tả đầy đủ cặp khóa–giá trị cần tạo. Ngay cả view entry đã có cả hai thành phần, API view này cũng không cung cấp thao tác thêm đó. Muốn thêm hoặc định vị mapping, dùng `putFirst`/`putLast` trên map.

Vì vậy, không đọc tên `SequencedSet` hoặc `SequencedCollection` như lời hứa rằng tất cả phương thức thay đổi của interface đều thực hiện được trên mọi view. Khả năng đọc, xóa và thêm cần được kiểm tra riêng.

### 9.4. View rỗng ném ngoại lệ ở get/remove hai đầu

Đối với các collection view sửa được trong bài:

| Tình huống rỗng | Kết quả |
|---|---|
| `map.firstEntry()` hoặc `map.lastEntry()` | `null` |
| `map.pollFirstEntry()` hoặc `map.pollLastEntry()` | `null` |
| `keys.getFirst()` hoặc `keys.getLast()` | `NoSuchElementException` |
| `keys.removeFirst()` hoặc `keys.removeLast()` | `NoSuchElementException` |
| `values.getFirst/getLast/removeFirst/removeLast` | Cùng quy tắc ngoại lệ khi rỗng |

Quy tắc của collection được mô tả tại [SequencedCollection — Java 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/SequencedCollection.html). Đừng dùng `keys.getFirst() == null` làm cách kiểm tra view rỗng: nếu view rỗng, lời gọi đã ném ngoại lệ; nếu khóa đầu hợp lệ là `null`, kết quả có thể là `null` dù map không rỗng.

## 10. Chương trình 4: khả năng thay đổi và lỗi rỗng của view

Lưu vào `LinkedHashMapSequencedViewsDemo.java`. Các ngoại lệ trong ví dụ được bắt có chủ đích và in tên để đối chiếu hợp đồng, không phải bỏ qua một lỗi bất ngờ.

```java
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.NoSuchElementException;
import java.util.SequencedCollection;
import java.util.SequencedSet;

public class LinkedHashMapSequencedViewsDemo {
    private static void unsupported(String label, Runnable operation) {
        try {
            operation.run();
            throw new AssertionError("Expected UnsupportedOperationException");
        } catch (UnsupportedOperationException expected) {
            System.out.println(label + "=UnsupportedOperationException");
        }
    }

    private static void missing(String label, Runnable operation) {
        try {
            operation.run();
            throw new AssertionError("Expected NoSuchElementException");
        } catch (NoSuchElementException expected) {
            System.out.println(label + "=NoSuchElementException");
        }
    }

    public static void main(String[] args) {
        LinkedHashMap<String, Integer> map = new LinkedHashMap<>();
        map.put("A", 7);
        map.put("B", 7);
        map.put("C", 9);

        SequencedSet<String> keys = map.sequencedKeySet();
        SequencedCollection<Integer> values = map.sequencedValues();
        SequencedSet<Map.Entry<String, Integer>> entries =
                map.sequencedEntrySet();

        System.out.println("keyEnds=" + keys.getFirst() + "," + keys.getLast());
        System.out.println("valueEnds=" + values.getFirst() + "," + values.getLast());
        System.out.println("firstEntryFromView=" + entries.getFirst());
        System.out.println("reversedKeys=" + keys.reversed());
        System.out.println("reversedValues=" + values.reversed());

        unsupported("keyAddFirst", () -> keys.addFirst("X"));
        unsupported("valueAddLast", () -> values.addLast(99));
        unsupported("entryAddFirst",
                () -> entries.addFirst(Map.entry("X", 99)));

        System.out.println("removedFirstValue=" + values.removeFirst());
        System.out.println("afterValueRemoval=" + map);
        System.out.println("removedReverseFirstKey="
                + keys.reversed().removeFirst());
        System.out.println("afterReverseKeyRemoval=" + map);
        System.out.println("removedLastEntry=" + entries.removeLast());
        System.out.println("empty=" + map.isEmpty());

        missing("emptyKeyGetFirst", () -> keys.getFirst());
        missing("emptyKeyRemoveLast", () -> keys.removeLast());
        missing("emptyValueGetLast", () -> values.getLast());
        System.out.println("emptyMapFirst=" + map.firstEntry());

        map.put("D", 4);
        System.out.println("sameKeyViewAfterPut=" + keys);
        System.out.println("sameValueViewAfterPut=" + values);
    }
}
```

Biên dịch và chạy bằng JDK 21 trở lên:

```shell
javac --release 21 -encoding UTF-8 LinkedHashMapSequencedViewsDemo.java
java LinkedHashMapSequencedViewsDemo
```

Stdout:

```text
keyEnds=A,C
valueEnds=7,9
firstEntryFromView=A=7
reversedKeys=[C, B, A]
reversedValues=[9, 7, 7]
keyAddFirst=UnsupportedOperationException
valueAddLast=UnsupportedOperationException
entryAddFirst=UnsupportedOperationException
removedFirstValue=7
afterValueRemoval={B=7, C=9}
removedReverseFirstKey=C
afterReverseKeyRemoval={B=7}
removedLastEntry=B=7
empty=true
emptyKeyGetFirst=NoSuchElementException
emptyKeyRemoveLast=NoSuchElementException
emptyValueGetLast=NoSuchElementException
emptyMapFirst=null
sameKeyViewAfterPut=[D]
sameValueViewAfterPut=[4]
```

### 10.1. Xóa theo đúng vị trí của view

Ba lần xóa chạy nối tiếp:

1. `values.removeFirst()` trả 7 và loại A, nên map còn `{B=7, C=9}`.
2. `keys.reversed().removeFirst()` trả C vì C đang đầu view khóa đảo, nên map còn `{B=7}`.
3. `entries.removeLast()` trả B=7 và loại mapping cuối cùng, nên map rỗng.

Một giá trị trùng nhau vẫn gắn với những mapping riêng. Việc xóa giá trị đầu không có nghĩa xóa toàn bộ dữ liệu cùng giá trị. Việc xóa đầu view đảo không có nghĩa xóa đầu map gốc.

### 10.2. View vẫn sống sau khi map từng rỗng

Sau ba lần xóa, các biến `keys`, `values`, `entries` không biến thành những collection vĩnh viễn rỗng. Chúng vẫn là view của map. Khi thêm D=4 vào map gốc, chính các biến view cũ in `[D]` và `[4]`.

Đây là lý do không nên lưu một view rồi gọi nó là “dữ liệu tại thời điểm tạo”. Nếu cần một danh sách khóa độc lập cho một phép tính sau đó, hãy tạo một collection mới từ view theo đúng chiều mong muốn. Nếu cần cả mapping và thứ tự riêng, dùng map mới như `copy` trong ví dụ trước.

Các lệnh thêm bị từ chối không thay đổi map. Các lệnh đọc/xóa trên view rỗng báo `NoSuchElementException`; trong khi `emptyMapFirst=null` xác nhận API trả entry của map có quy tắc rỗng khác.

## 11. Kết hợp với chế độ thứ tự truy cập

### 11.1. Chiều của view và chính sách truy cập là hai vấn đề riêng

`LinkedHashMap` mặc định dùng thứ tự chèn. Constructor ba đối số với `true` dùng thứ tự truy cập:

```java
// Minh họa cấu hình bên trong một phương thức.
LinkedHashMap<String, Integer> map =
        new LinkedHashMap<>(16, 0.75f, true);
```

Trong map gốc theo thứ tự truy cập, một `get` tìm thấy khóa đưa entry đó về cuối. View đảo nhìn cùng sự thay đổi theo chiều ngược, nên entry được truy cập xuất hiện ở **đầu view đảo**.

Không được suy luận rằng gọi `reverse.get(key)` sẽ đổi chính sách để đưa entry về cuối view. Lời gọi vẫn tạo truy cập trên map gốc. Độ mới của entry thuộc cùng một map, không có một lịch sử truy cập độc lập chỉ dành cho view.

Ngược lại, các thao tác đặt vị trí rõ ràng như `putFirst`/`putLast` thực hiện vị trí được yêu cầu; chúng không đồng thời tạo thêm một lần truy cập để kéo entry về cuối map gốc. Nếu `putFirst` luôn lập tức bị một lần làm mới truy cập kéo xuống cuối, nó đã không thể thực hiện ý nghĩa đặt đầu của mình.

`firstEntry` và `lastEntry` chỉ xem hai đầu, không làm mới vị trí. Các phép quan sát qua collection view cũng không tự biến thành truy cập `get`. Việc đọc tên phương thức cụ thể quan trọng hơn việc gọi chung mọi thao tác này là “đọc dữ liệu”.

### 11.2. Chương trình 5: đối chiếu từng lần đổi vị trí

Lưu vào `LinkedHashMapAccessOrderEndsDemo.java`. Chương trình in song song thứ tự gốc và đảo sau mỗi bước để tránh nhầm phía đầu/cuối.

```java
import java.util.LinkedHashMap;
import java.util.SequencedMap;

public class LinkedHashMapAccessOrderEndsDemo {
    private static void show(String label,
            LinkedHashMap<String, Integer> map,
            SequencedMap<String, Integer> reverse) {
        System.out.println(label + ": original=" + map.keySet()
                + ", reverse=" + reverse.keySet());
    }

    public static void main(String[] args) {
        LinkedHashMap<String, Integer> map =
                new LinkedHashMap<>(16, 0.75f, true);
        map.put("A", 1);
        map.put("B", 2);
        map.put("C", 3);
        SequencedMap<String, Integer> reverse = map.reversed();

        System.out.println("first=" + map.firstEntry());
        System.out.println("last=" + map.lastEntry());
        show("afterInspect", map, reverse);

        System.out.println("reverseGetA=" + reverse.get("A"));
        show("afterReverseGet", map, reverse);
        System.out.println("reverseContainsB=" + reverse.containsKey("B"));
        show("afterContains", map, reverse);

        map.putFirst("C", 30);
        show("afterExplicitFirst", map, reverse);
        System.out.println("getC=" + map.get("C"));
        show("afterGetC", map, reverse);

        reverse.putLast("A", 10);
        show("afterReverseExplicitLast", map, reverse);
        System.out.println("reverseGetB=" + reverse.get("B"));
        show("afterReverseGetB", map, reverse);
    }
}
```

Biên dịch và chạy bằng JDK 21 trở lên:

```shell
javac --release 21 -encoding UTF-8 LinkedHashMapAccessOrderEndsDemo.java
java LinkedHashMapAccessOrderEndsDemo
```

Stdout:

```text
first=A=1
last=C=3
afterInspect: original=[A, B, C], reverse=[C, B, A]
reverseGetA=1
afterReverseGet: original=[B, C, A], reverse=[A, C, B]
reverseContainsB=true
afterContains: original=[B, C, A], reverse=[A, C, B]
afterExplicitFirst: original=[C, B, A], reverse=[A, B, C]
getC=30
afterGetC: original=[B, A, C], reverse=[C, A, B]
afterReverseExplicitLast: original=[A, B, C], reverse=[C, B, A]
reverseGetB=2
afterReverseGetB: original=[A, C, B], reverse=[B, C, A]
```

### 11.3. Giải thích kết quả

Hai phép xem ban đầu trả A=1 và C=3 nhưng `afterInspect` vẫn là `[A, B, C]`. Chúng không làm mới A hay C.

`reverse.get("A")` tìm thấy A. Map gốc thành `[B, C, A]`; view thành `[A, C, B]`. A mới được truy cập nằm cuối gốc và đầu đảo. `reverse.containsKey("B")` trả `true` nhưng không đổi thứ tự, nên B vẫn đầu gốc.

`map.putFirst("C", 30)` đặt C lên đầu gốc và cập nhật giá trị thành 30. Kết quả là `[C, B, A]`, không phải một kết quả có C ở cuối do bị làm mới truy cập ngầm. Ngay sau đó, `map.get("C")` mới là một lần truy cập thực sự và chuyển C xuống cuối, tạo `[B, A, C]`.

`reverse.putLast("A", 10)` đặt A ở cuối view, tương ứng đầu map gốc. Gốc thành `[A, B, C]`, đảo thành `[C, B, A]`. Lần `reverse.get("B")` cuối cùng lại tạo truy cập, đưa B xuống cuối gốc `[A, C, B]` và lên đầu view `[B, C, A]`.

Bảng sau ghi lại sự khác nhau ở cùng một map theo thứ tự truy cập:

| Loại thao tác | Có chủ đích làm mới truy cập không? | Cách hiểu vị trí |
|---|---|---|
| `get` tìm thấy khóa, kể cả qua view đảo | Có | Cuối gốc, đầu view đảo |
| `containsKey` | Không | Không tự đổi vị trí |
| `firstEntry`/`lastEntry` | Không | Chỉ quan sát hai đầu hiện tại |
| `putFirst`/`putLast` | Đặt vị trí rõ ràng | Theo đầu/cuối của đối tượng nhận lời gọi |
| Duyệt các view để đọc phần tử | Không tự tạo truy cập | Theo chiều của view đang duyệt |

### 11.4. Hệ quả khi map đang được dùng làm LRU

Trong một map theo thứ tự truy cập chỉ chịu các thao tác truy cập thông thường, đầu gốc thể hiện entry ít được dùng gần đây nhất. Nhưng `putFirst` cho phép chương trình chủ động chuyển một entry lên đầu. Sau thao tác đặt vị trí đó, không nên còn diễn giải thứ tự như một lịch sử chỉ được quyết định bởi các lần sử dụng.

Nếu một lớp cache muốn giữ chính sách LRU tự động nhất quán, nó cần quyết định có cho bên ngoài gọi các thao tác định vị hay không. Việc có API mới không có nghĩa nên để mọi người gọi tùy ý mà vẫn tuyên bố cache chỉ dựa trên lịch sử truy cập.

Ở chiều đảo, `pollFirstEntry()` lấy entry cuối gốc. Trong thứ tự truy cập thông thường, đó là phía mới nhất, không phải entry cũ nhất. Nếu muốn lấy entry cũ nhất từ view đảo, vị trí tương ứng là cuối view. Trước khi viết logic loại bỏ dựa vào đầu/cuối, phải xác định rõ đang cầm map gốc hay view đảo và liệu thứ tự đã được định vị thủ công hay chưa.

## 12. Chọn thao tác theo ý định sử dụng

### 12.1. Khi cần xem, lấy ra, định vị hoặc sao chép

| Ý định | Cách thể hiện phù hợp trên LinkedHashMap |
|---|---|
| Xem mapping đầu nhưng vẫn giữ nó | `firstEntry()` |
| Lấy mapping cuối khỏi map | `pollLastEntry()` |
| Đưa một khóa lên đầu, đồng thời đặt giá trị mong muốn | `putFirst(key, value)` |
| Đưa một khóa xuống cuối | `putLast(key, value)` |
| Duyệt cùng dữ liệu theo chiều ngược | `reversed()` |
| Lấy khóa đầu và chấp nhận lỗi khi không có phần tử | `sequencedKeySet().getFirst()` |
| Xóa mapping cuối bằng view khóa | `sequencedKeySet().removeLast()` |
| Giữ một map riêng theo thứ tự đảo tại thời điểm tạo | `new LinkedHashMap<>(map.reversed())` |

Đây là lựa chọn theo ngữ nghĩa, không phải các cách viết hoàn toàn thay thế cho nhau. Một view không phải một bản sao; poll không phải một phép xem; snapshot entry không phải một cửa sửa trực tiếp mapping.

### 12.2. Lấy dần các mapping theo một chiều

Nếu cần lấy hết các mapping theo thứ tự hiện tại để xử lý trong một luồng, có thể dùng poll thay vì tự lấy iterator rồi xóa bên ngoài iterator. Đoạn dưới minh họa bên trong một phương thức đã có `map`; nó không phải chương trình độc lập:

```java
Map.Entry<String, Integer> next;
while ((next = map.pollFirstEntry()) != null) {
    System.out.println(next.getKey() + ":" + next.getValue());
}
```

Vòng lặp này **làm rỗng map** nếu chạy hết bình thường. Nó kiểm tra đối tượng entry có tồn tại, không dùng giá trị của entry để quyết định dừng, nên một mapping có giá trị `null` không tự làm vòng lặp kết thúc sớm.

Nếu chỉ muốn duyệt mà giữ dữ liệu, hãy dùng `forEach` hoặc duyệt `entrySet()` theo chiều mong muốn. Nếu muốn lấy từ chiều ngược và loại dần, có thể dùng `pollLastEntry()` trên gốc hoặc `pollFirstEntry()` trên view đảo; cả hai đều làm thay đổi cùng map.

Việc poll trước rồi mới xử lý cũng đặt ra một quyết định ở cấp ứng dụng: nếu xử lý thất bại, mapping đã rời map. Không suy ra đây là một hàng đợi công việc có giao dịch, cơ chế thử lại hoặc lưu bền chỉ vì có API lấy ở hai đầu.

### 12.3. Giữ dữ liệu riêng cần tạo cấu trúc mới

`reversed()` tự nó không tạo quyền chỉ đọc và cũng không cách ly thay đổi. Nếu trả view cho mã gọi bên ngoài, hãy xem đó như một đường liên quan đến map gốc. Khi yêu cầu là một ảnh dữ liệu độc lập về cấu trúc, tạo collection/map mới theo thứ tự cần giữ.

Bản sao mới vẫn có thể sửa được. Tính độc lập về cấu trúc khác với tính bất biến của đối tượng, và sao chép nông khác với sao chép sâu. Trong ví dụ dùng `String`/`Integer`, các giá trị không thể bị sửa tại chỗ; với đối tượng nghiệp vụ có thể thay đổi, hợp đồng chia sẻ tham chiếu cần được xác định riêng.

Không dùng `Map.copyOf` chỉ dựa vào mong muốn “giữ chính xác chiều đảo”: thứ tự duyệt của map do phương thức này tạo không được quy định, theo [Map — Java 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Map.html#unmodifiable). Việc cần thứ tự cụ thể phải được thể hiện bằng một kiểu/cách tạo có hợp đồng thứ tự phù hợp. Trong phạm vi bài này, constructor `LinkedHashMap` từ view đảo đã cho thấy rõ thứ tự được giữ khi tạo bản sao.

## 13. Các điểm cần kiểm tra khi đưa vào mã thực tế

### 13.1. Duyệt và đổi vị trí

Di chuyển entry bằng `putFirst`/`putLast`, thêm hoặc xóa entry có thể làm thay đổi cấu trúc thứ tự mà iterator đang dựa vào. Đổi qua view đảo vẫn là đổi cùng map; không có một iterator độc lập được bảo vệ chỉ vì nó được tạo từ chiều khác.

Đặc biệt ở chế độ thứ tự truy cập, gọi `get` trong khi đang duyệt chính map cũng có thể đổi thứ tự. Muốn chỉ đọc khóa và giá trị trong một lượt duyệt, lấy từ entry đang duyệt thay vì lấy khóa rồi lại gọi `get` để tra lại.

Iterator fail-fast có thể báo `ConcurrentModificationException` khi phát hiện thay đổi không phù hợp, kể cả trong một luồng. Cơ chế đó hoạt động theo nỗ lực phát hiện lỗi, không phải bảo đảm để chương trình dựa vào làm cơ chế phối hợp. Đừng viết logic đúng/sai dựa trên giả định mọi thay đổi đều chắc chắn gây ngoại lệ.

Nếu cần thay đổi nhiều vị trí theo một danh sách quyết định, có thể thu thập khóa vào một collection riêng trước rồi thực hiện các thay đổi sau lượt duyệt. Cần xác định trước rằng những thay đổi đó có chủ đích làm đổi thứ tự; có bản sao danh sách khóa chỉ tách cấu trúc duyệt khỏi map, không vô hiệu hóa hiệu ứng của các lệnh gọi sau đó.

### 13.2. Nhiều luồng không được bảo vệ bởi view

`LinkedHashMap` không tự đồng bộ. View đảo cũng không biến nó thành map an toàn cho truy cập đồng thời. Map gốc, view đảo và các collection view cùng nhìn vào trạng thái liên quan, nên khi cần phối hợp nhiều luồng phải xét mọi đường truy cập đó.

`firstEntry()` rồi `pollFirstEntry()` là hai lời gọi riêng. Nếu trạng thái có thể thay đổi xen giữa, không được giả định entry đã xem chắc chắn chính là entry sẽ lấy ra. Muốn một bước “lấy ra” trong mô hình một luồng của bài, dùng trực tiếp poll và xử lý kết quả của chính lời gọi đó; yêu cầu nguyên tử giữa nhiều luồng cần thiết kế khác.

Ở map theo thứ tự truy cập, một lần `get` có thể đổi liên kết thứ tự, nên không thể coi mọi lệnh đọc là không thay đổi trạng thái. Các ví dụ được chạy tuần tự trong một luồng và không đưa ra bảo đảm đồng thời.

### 13.3. Phiên bản biên dịch và phiên bản chạy

Để dùng các API trong bài, cần thư viện Java 21 trở lên ở lúc biên dịch và môi trường chạy tương ứng. Cài JDK mới nhưng cấu hình dự án vẫn `--release 17` thì API `SequencedMap` và các thao tác mới của `LinkedHashMap` không nằm trong tập API được phép dùng.

Ngược lại, không thể biên dịch ví dụ cho Java 21 rồi chạy lớp đã tạo trên một JVM Java 17. Cần kiểm tra cả cấu hình JDK của IDE, trình biên dịch và môi trường mà lệnh `java` thực sự sử dụng. Đây là thay đổi API theo phiên bản, không phải lỗi cú pháp có thể sửa bằng cách thêm import.

Các chương trình dùng constructor `LinkedHashMap` thông thường, không dùng tính năng ngôn ngữ preview hay thư viện ngoài. `--release 21` trong lệnh biên dịch nêu rõ mức API/bytecode cần cho bài.

## 14. Lỗi thường gặp

| Nhầm lẫn | Hệ quả | Cách sửa |
|---|---|---|
| Đầu/cuối là khóa nhỏ nhất/lớn nhất | Đọc sai entry khi map không sắp theo khóa | Theo dõi đúng thứ tự duyệt |
| Gọi poll chỉ để xem | Mapping biến mất ngoài ý định | Dùng `firstEntry`/`lastEntry` để quan sát |
| Gọi `.getKey()` ngay trên `firstEntry()` | Có thể `NullPointerException` khi map rỗng | Kiểm tra entry khác `null` |
| `putFirst` khóa cũ tạo bản sao khóa | Dự đoán sai kích thước | Hiểu là cập nhật và định vị cùng mapping |
| `put` khóa cũ luôn chuyển cuối | Sai trên map theo thứ tự chèn | Phân biệt chế độ và thao tác định vị |
| `firstEntry().setValue(...)` cập nhật map | `UnsupportedOperationException` | Cập nhật qua API map phù hợp |
| `reversed()` đảo map gốc tại chỗ | Cho rằng thứ tự của mọi biến đều bị đảo | Tách chiều nhìn khỏi dữ liệu gốc |
| `reversed()` tạo một map độc lập | Sửa view làm đổi map gốc | Tạo cấu trúc mới khi cần độc lập |
| `reverse.put(...)` thêm cuối view | Sai vị trí với LinkedHashMap | Dùng thao tác vị trí rõ ràng khi đó là yêu cầu |
| Xóa đầu view đảo tức xóa đầu gốc | Loại nhầm entry | Đầu đảo tương ứng cuối gốc |
| View sửa được thì `addFirst` cũng chạy được | `UnsupportedOperationException` | Thêm cả mapping qua map |
| `getFirst` của view rỗng trả `null` | Bỏ sót `NoSuchElementException` | Theo đúng hợp đồng rỗng của từng API |
| Map bằng view đảo thì thứ tự giống nhau | Kiểm tra thứ tự không phát hiện lỗi | So sánh danh sách theo thứ tự mong muốn |

## 15. Tự kiểm tra và thực hành

### 15.1. Câu hỏi

1. Với thứ tự gốc `[A, B, C]`, `map.reversed().firstEntry()` nhìn thấy entry nào?
2. `firstEntry` và `pollFirstEntry` khác nhau ở tác động nào?
3. Vì sao entry `A=null` khác với kết quả entry `null`?
4. `putFirst("B", value)` trên map đã có A, B, C làm kích thước tăng không?
5. Sau `reverse.putLast("D", 4)` với D là khóa mới, D nằm đầu hay cuối map gốc?
6. Sửa giá trị bằng `setValue` trên entry lấy từ `firstEntry` có được không?
7. `map.sequencedKeySet().removeLast()` có chỉ sửa một tập khóa rời khỏi map không?
8. Vì sao `sequencedValues()` không trả `SequencedSet`?
9. Một `reverse.get("A")` thành công trên map theo thứ tự truy cập làm A nằm phía nào của gốc và của view?
10. Vì sao `map.equals(map.reversed())` có thể đúng dù chiều duyệt khác nhau?

### 15.2. Đáp án ngắn

1. C; đầu view đảo chính là cuối gốc.
2. `firstEntry` chỉ xem; `pollFirstEntry` lấy entry và loại mapping. Cả hai trả `null` nếu map rỗng.
3. `A=null` là một entry có thật chứa giá trị `null`; entry trả về `null` nghĩa là không có entry ở đầu vì map rỗng.
4. Không. Nó cập nhật và chuyển mapping B lên đầu, thứ tự thành `[B, A, C]`.
5. Đầu map gốc, vì cuối view tương ứng đầu gốc.
6. Không; snapshot đầu–cuối trong bài không hỗ trợ `setValue`. Hãy dùng thao tác cập nhật của map.
7. Không. View liên kết nên mapping của khóa cuối bị loại khỏi map gốc.
8. Vì nhiều khóa khác nhau được phép cùng ánh xạ đến một giá trị; view giá trị có thể chứa phần tử trùng.
9. Cuối gốc và đầu view đảo. Lời gọi tạo truy cập trên cùng map gốc.
10. Phép bằng nhau của map kiểm tra tập mapping, không kiểm tra thứ tự duyệt.

### 15.3. Bài thực hành 1: chuyển vị trí không tạo trùng khóa

Tạo map theo thứ tự chèn A=1, B=2, C=3. Chạy nối tiếp `putFirst("B", 20)`, `putLast("A", 10)`. Trước khi chạy, dự đoán giá trị cũ của mỗi lời gọi, thứ tự cuối và kích thước.

Kết quả đối chiếu: hai giá trị trả về lần lượt là 2 và 1; map cuối là `{B=20, C=3, A=10}`, kích thước ba. Nếu có bốn hoặc năm entry trong dự đoán, đã nhầm map với danh sách có thể giữ nhiều bản của cùng khóa.

### 15.4. Bài thực hành 2: xác định đúng chiều trước khi xóa

Từ map gốc A=1, B=2, C=3, tạo `reverse`. Chạy `reverse.putFirst("D", 4)` rồi `reverse.pollLastEntry()`. Ghi lại đồng thời thứ tự gốc và đảo sau mỗi bước.

Kết quả đối chiếu: sau đặt D, gốc `[A, B, C, D]`, đảo `[D, C, B, A]`. Poll cuối view lấy A=1, gốc còn `[B, C, D]`, đảo còn `[D, C, B]`. Nếu kết quả lấy D thì đã dùng nhầm chiều đầu/cuối.

### 15.5. Bài thực hành 3: chứng minh view và bản sao khác nhau

Tạo view đảo và một `new LinkedHashMap<>(view)` từ cùng map ba entry. Sau đó đổi giá trị của B và thêm một khóa mới qua map gốc. In cả gốc, view và bản sao.

Tiêu chí đối chiếu: view nhìn thấy giá trị B mới và khóa mới theo chiều đảo hiện tại; bản sao giữ các mapping và thứ tự tại lúc tạo. Sau đó xóa một mapping qua view và xác nhận nó biến mất khỏi gốc nhưng không tự biến mất khỏi bản sao.

### 15.6. Bài thực hành 4: không trộn hợp đồng rỗng

Trên một map rỗng, đối chiếu `firstEntry()` với `sequencedKeySet().getFirst()`. Tiếp theo thêm mapping có khóa `null`, giá trị `null` rồi gọi lại.

Kết quả đối chiếu: lúc rỗng, API map trả entry `null`, còn API view ném `NoSuchElementException`. Khi đã có mapping, `firstEntry()` là entry khác `null`, còn `getFirst()` của view khóa trả khóa `null` hợp lệ. Không thể kiểm tra rỗng của mọi API bằng cùng một phép so sánh kết quả với `null`.

## 16. Môi trường và tài liệu đối chiếu

Năm chương trình độc lập trong bài đã được biên dịch bằng `javac --release 21 -encoding UTF-8` và chạy trên JDK 24.0.2; stdout đã được đối chiếu từ các lần chạy đó. `--release 21` kiểm tra khả năng dùng API Java 21 lúc biên dịch; thông tin môi trường chạy nêu rõ JDK thực sự đã dùng. Mỗi tệp có một lớp `public` trùng tên tệp, không phụ thuộc ví dụ ở tệp khác.

- [LinkedHashMap — Java 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/LinkedHashMap.html): chế độ thứ tự, phương thức định vị và quan hệ giữa map với view đảo.
- [SequencedMap — Java 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/SequencedMap.html): nhóm thao tác mapping hai đầu, snapshot entry và hợp đồng thứ tự.
- [SequencedCollection — Java 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/SequencedCollection.html): `getFirst/getLast`, `removeFirst/removeLast` và trường hợp rỗng.
- [SequencedSet — Java 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/SequencedSet.html): tập hợp có thứ tự duyệt và view đảo.
- [LinkedHashMap — mã nguồn OpenJDK 21](https://raw.githubusercontent.com/openjdk/jdk21u/master/src/java.base/share/classes/java/util/LinkedHashMap.java): đối chiếu cách view chuyển tiếp các thao tác và đổi đầu/cuối.
