# ConcurrentSkipListMap, ConcurrentSkipListSet và truy vấn có thứ tự

## 1. Khi dữ liệu đồng thời còn cần một trật tự để tìm kiếm

Giả sử nhiều luồng cùng ghi nhận các sự kiện theo thời gian. Chương trình không chỉ hỏi “có sự kiện với khóa này không?” mà còn hỏi:

- Sự kiện gần nhất không muộn hơn một mốc là sự kiện nào?
- Khóa đầu tiên sau một mốc là gì?
- Những sự kiện nào nằm trong một khoảng?
- Có thể lấy và xóa mục đứng đầu mà nhiều luồng không cùng lấy một mục không?

Các câu hỏi này dùng **quan hệ thứ tự** giữa các khóa. Một bảng băm phù hợp với tra cứu theo khóa chính xác, nhưng không tự cung cấp ý nghĩa “khóa liền trước”, “khóa liền sau” hay “đoạn từ A đến B”.

`ConcurrentSkipListMap<K, V>` kết hợp map đồng thời với việc sắp xếp khóa. `ConcurrentSkipListSet<E>` giữ các phần tử duy nhất theo thứ tự và hỗ trợ các truy vấn tương tự mà không có phần giá trị riêng. Hai lớp phù hợp khi thứ tự là một phần của cách truy vấn, trong khi dữ liệu có nhiều luồng truy cập.

Cần tách ba ý ngay từ đầu:

1. **Thứ tự:** khóa hoặc phần tử nào được coi là đứng trước?
2. **Điều hướng:** cần mục liền trước, liền sau hay một khoảng?
3. **Tính đồng thời:** khi dữ liệu thay đổi, phép đọc và chuỗi thao tác của ứng dụng có ý nghĩa đến đâu?

Có thứ tự không đồng nghĩa đã có một bản chụp cố định. An toàn cho từng thao tác không tự biến nhiều truy vấn thành một giao dịch. Đây là hai ranh giới quan trọng nhất của bài.

Các chương trình trong bài độc lập, dùng Java 17 trở lên và không cần thư viện ngoài. Lưu đúng tên tệp trong từng mục, biên dịch rồi chạy ở thư mục chứa tệp. Những ví dụ giải thích ranh giới khoảng chạy tuần tự để kết quả rõ ràng. Ví dụ nhiều luồng chỉ in kết quả sau khi lấy xong các `Future`, tránh phụ thuộc vào thứ tự in ngẫu nhiên của các luồng.

## 2. Mô hình cấu trúc và các kiểu giao diện

### 2.1. Map được sắp theo khóa, Set được sắp theo phần tử

Với map, thứ tự xét trên `K`, không phải trên `V`. Thêm `(30, "A")`, `(10, "Z")` và `(20, "M")` vào map dùng thứ tự số tự nhiên sẽ cho thứ tự khóa 10, 20, 30. Các giá trị được duyệt theo khóa tương ứng, không tự sắp thành A, M, Z.

Với set, phần tử chính là dữ liệu dùng để so sánh. Nếu cần giữ nhiều công việc có cùng độ ưu tiên, phải xác định một thứ tự đầy đủ đủ để phân biệt chúng, thay vì chỉ so sánh độ ưu tiên.

Nếu không truyền comparator, hai lớp dùng thứ tự tự nhiên. Nếu truyền `Comparator` khi tạo, mọi khái niệm đầu, cuối, thấp hơn, cao hơn và giới hạn khoảng đều đi theo comparator đó.

### 2.2. Những khả năng được ghép lại

```text
Map
  → SortedMap: khóa có thứ tự
      → NavigableMap: tìm lân cận, lấy khoảng, đảo chiều
          → ConcurrentNavigableMap: các thao tác đồng thời
              → ConcurrentSkipListMap

Set
  → SortedSet: phần tử có thứ tự
      → NavigableSet: tìm lân cận, lấy khoảng, đảo chiều
          → ConcurrentSkipListSet
```

Sơ đồ trình bày quan hệ khả năng qua các giao diện; không phải mọi dòng đều là một lớp cha trực tiếp. `ConcurrentSkipListSet` được xây dựng dựa trên `ConcurrentSkipListMap`, nhưng người sử dụng vẫn làm việc qua các phép toán set.

`ConcurrentSkipListMap` cung cấp chi phí trung bình kỳ vọng O(log n) cho các thao tác cơ bản như `get`, `containsKey`, `put`, `remove`. `ConcurrentSkipListSet` có đặc tính tương ứng với `contains`, `add`, `remove`. Không diễn giải đặc tính này thành mọi truy vấn, mọi phép duyệt hay mọi tải thực tế đều mất cùng một thời gian. Xem [ConcurrentSkipListMap Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentSkipListMap.html) và [ConcurrentSkipListSet Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentSkipListSet.html).

Tên “skip list” gợi ý một cấu trúc tìm kiếm có các mức giúp bỏ qua những đoạn trong dữ liệu đã sắp. Khi viết mã ứng dụng, điều cần dựa vào là hợp đồng truy vấn và tính đồng thời của lớp, không phải chiều cao hay hình dạng nội bộ của một danh sách cụ thể.

### 2.3. Những điều kiện đầu vào

Khóa của map phải so sánh được với nhau theo quy tắc đã chọn; tương tự với phần tử set. Trộn các kiểu không có thứ tự chung hoặc cung cấp comparator không phù hợp có thể gây `ClassCastException`.

Map không cho phép khóa hoặc giá trị `null`; set không cho phép phần tử `null`. Vì vậy, khi một phép truy vấn lân cận trả `null`, đó là dấu hiệu không tìm thấy kết quả theo phép truy vấn, không phải một phần tử `null` đang được lưu.

Các trường tham gia so sánh nên ổn định trong suốt thời gian khóa hoặc phần tử nằm trong cấu trúc. Nếu đổi thời gian, độ ưu tiên hay mã dùng để so sánh ngay trên đối tượng đang được lưu, cấu trúc không tự dời nó đến đúng vị trí mới. Một đối tượng khóa bất biến giúp tránh lỗi này.

Comparator cũng không nên đọc một cấu hình thứ tự đang thay đổi hoặc dựa vào trạng thái dùng chung thiếu đồng bộ. Một phép so sánh có kết quả đổi tùy thời điểm sẽ làm các câu hỏi như “nằm giữa hai cận” mất ý nghĩa nhất quán.

## 3. Tìm khóa hoặc phần tử lân cận

### 3.1. Bốn quan hệ cần nhớ

Với mục tiêu `x`, các phép điều hướng tìm kết quả gần nhất thỏa một quan hệ, chứ không yêu cầu `x` đang tồn tại:

| Ý muốn | Map chỉ lấy khóa | Map lấy cặp khóa và giá trị | Set lấy phần tử |
|---|---|---|---|
| Lớn nhất nhưng nhỏ hơn x | `lowerKey(x)` | `lowerEntry(x)` | `lower(x)` |
| Lớn nhất nhưng không lớn hơn x | `floorKey(x)` | `floorEntry(x)` | `floor(x)` |
| Nhỏ nhất nhưng không nhỏ hơn x | `ceilingKey(x)` | `ceilingEntry(x)` | `ceiling(x)` |
| Nhỏ nhất nhưng lớn hơn x | `higherKey(x)` | `higherEntry(x)` | `higher(x)` |

Nhỏ hơn và lớn hơn đều được hiểu theo thứ tự của cấu trúc. `lower` và `higher` loại trừ mục tiêu; `floor` và `ceiling` cho phép bằng mục tiêu. Không có ứng viên thì kết quả là `null`. Xem [các phép điều hướng của NavigableMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/NavigableMap.html) và [NavigableSet](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/NavigableSet.html).

Với các khóa 10, 20, 30, mục tiêu 25 không tồn tại nhưng `floorKey(25)` vẫn là 20 và `ceilingKey(25)` vẫn là 30. Với mục tiêu 20, `lowerKey(20)` là 10 còn `floorKey(20)` là 20. Đó là khác biệt giữa truy vấn loại trừ và bao gồm mốc.

### 3.2. Chương trình với map và đối tượng Entry

Tệp `OrderedMapQueriesDemo.java`:

```java
import java.util.concurrent.ConcurrentSkipListMap;

public class OrderedMapQueriesDemo {
    public static void main(String[] args) {
        var values = new ConcurrentSkipListMap<Integer, String>();
        values.put(30, "thirty");
        values.put(10, "ten");
        values.put(20, "twenty");

        System.out.println("keys=" + values.keySet());
        System.out.println("lower20=" + values.lowerKey(20));
        System.out.println("floor20=" + values.floorKey(20));
        System.out.println("ceiling25=" + values.ceilingKey(25));
        System.out.println("higher30=" + values.higherKey(30));
        System.out.println("floorEntry25=" + values.floorEntry(25));
        System.out.println("first=" + values.firstEntry());
        System.out.println("last=" + values.lastEntry());

        var observed = values.floorEntry(25);
        values.put(20, "TWENTY");
        System.out.println("observedValue=" + observed.getValue());
        System.out.println("currentValue=" + values.get(20));
        try {
            observed.setValue("changed");
        } catch (UnsupportedOperationException ex) {
            System.out.println("entryWrite=" + ex.getClass().getSimpleName());
        }

        var empty = new ConcurrentSkipListMap<Integer, String>();
        System.out.println("emptyFirstEntry=" + empty.firstEntry());
        try {
            empty.firstKey();
        } catch (java.util.NoSuchElementException ex) {
            System.out.println("emptyFirstKey=" + ex.getClass().getSimpleName());
        }
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 OrderedMapQueriesDemo.java
java OrderedMapQueriesDemo
```

Stdout:

```text
keys=[10, 20, 30]
lower20=10
floor20=20
ceiling25=30
higher30=null
floorEntry25=20=twenty
first=10=ten
last=30=thirty
observedValue=twenty
currentValue=TWENTY
entryWrite=UnsupportedOperationException
emptyFirstEntry=null
emptyFirstKey=NoSuchElementException
```

Chương trình thêm khóa theo thứ tự 30, 10, 20 nhưng duyệt ra 10, 20, 30. Điều đó cho thấy thứ tự chèn không phải thứ tự sử dụng cho các truy vấn.

`floorEntry(25)` lấy cả khóa 20 và giá trị của nó trong một kết quả. Nếu cần khóa lẫn giá trị, dùng dạng trả về entry giúp tránh tự ghép hai phép đọc như `floorKey` rồi `get`, giữa chúng có thể có cập nhật khác.

Đối tượng `observed` được lấy khi giá trị là `"twenty"`. Sau khi map được thay thành `"TWENTY"`, entry đã lấy vẫn chứa giá trị trước đó. Nó không phải một tay cầm tự cập nhật theo map.

Phép `setValue` trên entry này không được hỗ trợ. Muốn cập nhật map, dùng phép cập nhật của map với điều kiện phù hợp. Cũng cần phân biệt bản ghi liên kết và bản sao sâu: nếu giá trị là một đối tượng có thể thay đổi, entry giữ tham chiếu đó, không tự sao chép toàn bộ dữ liệu bên trong.

### 3.3. Trường hợp rỗng và hai dạng đọc đầu/cuối

Khi map rỗng, `firstEntry()` và `lastEntry()` trả `null`, còn `firstKey()` và `lastKey()` ném `NoSuchElementException`. Với set, `first()` và `last()` cũng cần xử lý trường hợp rỗng; các phép `pollFirst()`, `pollLast()` trả `null` khi không có phần tử.

Không viết “kiểm tra không rỗng rồi lấy khóa đầu” như thể hai lời gọi liền nhau tạo một ranh giới chung. Một luồng khác có thể xóa hết dữ liệu giữa hai lời gọi. Chọn API có thể biểu diễn trực tiếp tình huống không có kết quả, hoặc xử lý ngoại lệ đúng với thiết kế.

Đối với chương trình trên, map `empty` không có luồng khác truy cập nên kết quả rỗng hoàn toàn ổn định. Trong mã có nhiều luồng, kết quả của mỗi lần đọc chỉ nên được dùng với phạm vi bảo đảm của chính lần đọc đó.

## 4. Lấy khoảng: cận có được bao gồm hay không?

### 4.1. Biểu diễn khoảng rõ ràng

Với thứ tự số tăng dần, ký hiệu `[a, b)` nghĩa là lấy các khóa từ a trở lên nhưng nhỏ hơn b. Hai dấu ngoặc thể hiện khác biệt quan trọng: cận trái được bao gồm, cận phải bị loại.

Các lời gọi có cờ boolean giúp nói thẳng điều đó:

```java
// Mã minh họa trong một phương thức, chưa phải chương trình độc lập.
var window = map.subMap(20, true, 40, false); // [20, 40)
var before = map.headMap(40, false);         // nhỏ hơn 40
var from = map.tailMap(20, true);            // từ 20 trở lên
```

`subSet`, `headSet`, `tailSet` của set có cách dùng tương ứng.

Các dạng ngắn kế thừa ý nghĩa của giao diện có thứ tự:

| Lời gọi | Ý nghĩa theo thứ tự hiện tại |
|---|---|
| `subMap(a, b)` hoặc `subSet(a, b)` | Bao gồm a, loại b |
| `headMap(b)` hoặc `headSet(b)` | Loại b |
| `tailMap(a)` hoặc `tailSet(a)` | Bao gồm a |

Đừng đoán mọi dạng ngắn đều bao gồm hoặc đều loại cận. Khi đọc mã nghiệp vụ liên quan mốc thời gian, viết cờ rõ ràng thường giúp xem xét dễ hơn.

Nếu hai cận bằng nhau, dạng `[a, a)` rỗng. Dạng bao gồm cả hai cận có thể chứa khóa so sánh bằng a nếu khóa ấy tồn tại. Nếu cận đầu đứng sau cận cuối theo thứ tự đang dùng, lời gọi lấy khoảng không hợp lệ.

### 4.2. Khoảng trả về là view được nối với dữ liệu gốc

Một view là một cách nhìn có giới hạn trên cùng dữ liệu, không phải bản sao. Cập nhật trong khoảng qua map gốc có thể xuất hiện trong view; thay đổi qua view tác động trở lại map gốc. Chèn một khóa ngoài giới hạn view gây `IllegalArgumentException`. View của `ConcurrentNavigableMap` tiếp tục hỗ trợ các phép điều hướng đồng thời. Xem [hợp đồng lấy khoảng của ConcurrentNavigableMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentNavigableMap.html#subMap(K,boolean,K,boolean)).

Tệp `RangeViewsDemo.java`:

```java
import java.util.concurrent.ConcurrentSkipListMap;

public class RangeViewsDemo {
    public static void main(String[] args) {
        var root = new ConcurrentSkipListMap<Integer, String>();
        for (int key : new int[] {10, 20, 30, 40, 50}) {
            root.put(key, "v" + key);
        }

        var window = root.subMap(20, true, 40, false);
        System.out.println("initialWindow=" + window.keySet());
        window.put(25, "v25");
        window.remove(30);
        root.put(35, "v35");
        System.out.println("rootAfterChanges=" + root.keySet());
        System.out.println("liveWindow=" + window.keySet());

        try {
            window.put(40, "outside");
        } catch (IllegalArgumentException ex) {
            System.out.println("outsideWrite=" + ex.getClass().getSimpleName());
        }
        System.out.println("root40=" + root.get(40));
        System.out.println("head40Default=" + root.headMap(40).keySet());
        System.out.println("tail40Default=" + root.tailMap(40).keySet());

        var descending = window.descendingMap();
        System.out.println("descending=" + descending.keySet());
        System.out.println("descendingLower25=" + descending.lowerKey(25));
        System.out.println("descendingHigher25=" + descending.higherKey(25));
        System.out.println("descendingRange=" +
                descending.subMap(35, true, 20, false).keySet());

        window.clear();
        System.out.println("rootAfterWindowClear=" + root.keySet());
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 RangeViewsDemo.java
java RangeViewsDemo
```

Stdout:

```text
initialWindow=[20, 30]
rootAfterChanges=[10, 20, 25, 35, 40, 50]
liveWindow=[20, 25, 35]
outsideWrite=IllegalArgumentException
root40=v40
head40Default=[10, 20, 25, 35]
tail40Default=[40, 50]
descending=[35, 25, 20]
descendingLower25=35
descendingHigher25=20
descendingRange=[35, 25]
rootAfterWindowClear=[10, 40, 50]
```

Theo dõi các bước trước khi đảo chiều:

1. `window` ban đầu có 20 và 30; 40 ở ngoài vì cận phải bị loại.
2. Thêm 25 qua view làm map gốc có 25.
3. Xóa 30 qua view làm map gốc mất 30.
4. Thêm 35 qua map gốc làm view nhìn thấy 35.
5. Chèn 40 qua view bị từ chối; giá trị 40 ở map gốc vẫn là `v40`.
6. `window.clear()` cuối chương trình xóa các mục trong khoảng khỏi map gốc.

Thí nghiệm này chạy tuần tự. Nó minh họa quan hệ giữa view và dữ liệu nền mà không trộn thêm biến động từ luồng khác.

### 4.3. Quyền truy cập qua view có phạm vi dữ liệu nhưng vẫn có tác động thật

Truyền một submap cho hàm khác không chỉ truyền danh sách kết quả. Hàm nhận có thể thay đổi những mục mà view cho phép. Ví dụ, gọi `clear` trên view làm mất dữ liệu thật trong khoảng.

Nếu bên nhận chỉ được đọc, cần một hợp đồng hoặc lớp bao giới hạn thao tác phù hợp. Một lớp bao chỉ đọc trên view vẫn có thể phản ánh thay đổi từ nguồn gốc; nó không tự trở thành bản chụp.

Một view lồng bên trong view khác cũng phải tuân thủ cận của view bên ngoài. Không dùng `subMap` trên một khoảng nhỏ để cố mở rộng trở lại ngoài phạm vi đó.

Giữ một view trong bộ nhớ cũng giữ liên hệ với cấu trúc nền. Nếu chỉ muốn giữ một nhóm kết quả ngắn hạn, hãy cân nhắc sao chép dữ liệu cần dùng và xác định mức nhất quán của việc sao chép.

## 5. Đảo chiều làm đổi cả ý nghĩa điều hướng

`descendingMap()` và `descendingSet()` cung cấp view theo thứ tự đảo ngược. Đây không chỉ là cách in cùng một danh sách từ cuối về đầu; các quan hệ so sánh của view cũng bị đảo.

Trong `RangeViewsDemo`, các khóa tăng dần của window là 20, 25, 35. View đảo chiều duyệt 35, 25, 20:

```text
Thứ tự tăng:  20 → 25 → 35
Thứ tự đảo:   35 → 25 → 20

Trong view đảo:
lowerKey(25)  = 35
higherKey(25) = 20
```

Số 35 lớn hơn 25 theo số học, nhưng đứng trước 25 trong thứ tự đảo. Vì vậy nó là kết quả của `lowerKey(25)` trên view ấy.

Tương tự, khoảng của view đảo phải viết theo thứ tự đảo:

```java
// Mã minh họa trong một phương thức, chưa phải chương trình độc lập.
var part = descending.subMap(35, true, 20, false);
```

Kết quả của ví dụ là 35, 25. Viết ngược hai cận chỉ vì quen thứ tự số tăng có thể gây lỗi khoảng không hợp lệ.

Để đọc đúng một lời gọi điều hướng:

1. Xác định đang gọi trên map gốc hay view nào.
2. Xác định comparator hoặc chiều duyệt của view đó.
3. Diễn giải “trước”, “sau”, “bao gồm cận” theo chính thứ tự ấy.

Đảo chiều hai lần đưa cách nhìn trở lại thứ tự ban đầu. Thay đổi qua view đảo vẫn tác động vào dữ liệu nền trong phạm vi của nó.

Trong các lớp này, tài liệu API cho biết duyệt theo chiều tăng thuận lợi hơn chiều giảm. Nếu ứng dụng dùng cả hai chiều, hãy chọn thứ tự khóa chính theo cách truy vấn thường xuyên và đo trên tải thật; không suy ra một tỷ lệ chênh lệch cố định từ một ví dụ nhỏ.

## 6. Set có thứ tự: tính duy nhất do quy tắc so sánh quyết định

### 6.1. Khi so sánh bằng 0 nhưng equals không bằng nhau

Một comparator không chỉ quyết định cách trình bày. Với cấu trúc có thứ tự, kết quả so sánh bằng 0 còn quyết định hai khóa hoặc phần tử có cùng vị trí nhận diện trong cấu trúc hay không.

Giả sử mỗi công việc có `priority` và `id`. Hai công việc cùng độ ưu tiên nhưng khác mã vẫn là hai công việc. Nếu comparator chỉ nhìn `priority`, set sẽ coi chúng tương đương theo thứ tự và không giữ cả hai.

Để tuân thủ hợp đồng thông thường của `Set` và `Map`, thứ tự phải nhất quán với `equals` trên miền dữ liệu được dùng. Một comparator làm hai đối tượng khác nhau theo `equals` so sánh bằng 0 có thể khiến kết quả nhìn rất khó hiểu. Xem [yêu cầu nhất quán với equals của Comparator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Comparator.html).

### 6.2. Chương trình với Set, view và khóa phụ

Tệp `OrderedSetDemo.java`:

```java
import java.util.Comparator;
import java.util.List;
import java.util.concurrent.ConcurrentSkipListSet;

public class OrderedSetDemo {
    record Job(int priority, String id) {}

    public static void main(String[] args) {
        var numbers = new ConcurrentSkipListSet<Integer>(List.of(40, 10, 30, 20));
        System.out.println("numbers=" + numbers);
        System.out.println("lower20=" + numbers.lower(20));
        System.out.println("floor25=" + numbers.floor(25));
        System.out.println("ceiling25=" + numbers.ceiling(25));
        System.out.println("higher20=" + numbers.higher(20));

        var window = numbers.subSet(20, true, 40, false);
        System.out.println("window=" + window);
        window.remove(30);
        System.out.println("afterViewRemove=" + numbers);
        System.out.println("polled=" + numbers.pollFirst());
        System.out.println("remaining=" + numbers);

        Job first = new Job(5, "A");
        Job second = new Job(5, "B");
        var priorityOnly = new ConcurrentSkipListSet<Job>(
                Comparator.comparingInt(Job::priority));
        System.out.println("jobsEqual=" + first.equals(second));
        System.out.println("firstAdded=" + priorityOnly.add(first));
        System.out.println("secondAdded=" + priorityOnly.add(second));
        System.out.println("priorityOnlyContainsB=" + priorityOnly.contains(second));
        System.out.println("priorityOnlySize=" + priorityOnly.size());

        Comparator<Job> fullOrder = Comparator.comparingInt(Job::priority)
                .thenComparing(Job::id);
        var complete = new ConcurrentSkipListSet<Job>(fullOrder);
        complete.add(first);
        complete.add(second);
        System.out.println("fullOrderIds=" +
                complete.stream().map(Job::id).toList());

        var empty = new ConcurrentSkipListSet<Integer>();
        System.out.println("emptyPoll=" + empty.pollFirst());
        try {
            empty.first();
        } catch (java.util.NoSuchElementException ex) {
            System.out.println("emptyFirst=" + ex.getClass().getSimpleName());
        }
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 OrderedSetDemo.java
java OrderedSetDemo
```

Stdout:

```text
numbers=[10, 20, 30, 40]
lower20=10
floor25=20
ceiling25=30
higher20=30
window=[20, 30]
afterViewRemove=[10, 20, 40]
polled=10
remaining=[20, 40]
jobsEqual=false
firstAdded=true
secondAdded=false
priorityOnlyContainsB=true
priorityOnlySize=1
fullOrderIds=[A, B]
emptyPoll=null
emptyFirst=NoSuchElementException
```

Nửa đầu cho thấy API của set song song với API khóa của map: tìm lân cận, lấy khoảng, xóa qua view rồi lấy và xóa phần tử đầu.

Nửa sau cố ý dùng một comparator không đủ thông tin:

- `first.equals(second)` là `false`, vì hai record có mã A và B khác nhau.
- Lần thêm thứ hai trả `false`, vì comparator chỉ thấy độ ưu tiên 5 ở cả hai.
- `contains(second)` trả `true`, dù phần tử thực sự được giữ là công việc A.
- Kích thước set chỉ là 1.

Điều này không phải một cuộc đua giữa các luồng. Nó xuất phát từ mô hình nhận diện do comparator áp đặt.

Comparator `fullOrder` so sánh độ ưu tiên trước rồi đến mã. Với record hai trường này và dữ liệu trong ví dụ, quy tắc đó phân biệt đúng hai công việc và nhất quán với `equals`.

### 6.3. Áp dụng cùng suy nghĩ cho Map

Nếu khóa map là `Job` và comparator chỉ so sánh `priority`, hai khóa cùng độ ưu tiên cũng tranh cùng vị trí khóa theo thứ tự. Gọi `put` bằng khóa thứ hai có thể thay giá trị của liên kết đã có thay vì tạo thêm một liên kết độc lập.

Nếu nghiệp vụ muốn không phân biệt hoa thường hoặc muốn nhóm nhiều biểu diễn thành một danh tính chung, nên định nghĩa danh tính dữ liệu rõ ràng, chẳng hạn chuẩn hóa mã trước khi làm khóa. Đừng để một comparator phục vụ hiển thị vô tình quyết định mất dữ liệu.

Thêm khóa phụ cũng phải phù hợp với mô hình. Chỉ thêm một trường tùy ý để “không bị mất phần tử” có thể khiến thứ tự không nhất quán với `equals` ở chiều ngược lại. Hãy xác định những trường nào thật sự tạo nên danh tính và dùng một quy tắc nhất quán.

### 6.4. Tránh các comparator không ổn định

Không viết so sánh số bằng cách lấy hiệu rồi ép kiểu nếu miền số có thể tràn. Dùng `Integer.compare`, `Long.compare`, `Comparator.comparingInt`, `comparingLong` giúp diễn đạt ý định rõ hơn.

Cũng không nên dùng “thời điểm hiện tại”, trạng thái tải hoặc một bảng ưu tiên đang bị sửa để thay đổi thứ tự của phần tử đã nằm trong set. Nếu độ ưu tiên cần đổi, hãy có quy trình loại bỏ và thêm lại với dữ liệu mới, đồng thời xác định cách phối hợp khi nhiều luồng thực hiện quy trình đó.

Tính an toàn của cấu trúc không tự biến một comparator sai thành một thứ tự hợp lệ.

## 7. Điều đồng thời bảo đảm và những gì ứng dụng vẫn phải giải quyết

### 7.1. Duyệt được trong lúc cập nhật không đồng nghĩa có bản chụp

Iterator của các cấu trúc này có tính nhất quán yếu (weakly consistent). Nó có thể tiếp tục duyệt khi có thao tác đồng thời và không dùng `ConcurrentModificationException` để thông báo các thay đổi đó. Các cập nhật trong lúc duyệt có thể được phản ánh, nhưng không nên yêu cầu mọi cập nhật đều xuất hiện theo một ảnh chụp chung. Xem [quy tắc duyệt của java.util.concurrent](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/package-summary.html#ConcurrentCollections).

Có hai câu hỏi độc lập:

- Các kết quả được duyệt có theo thứ tự khóa không?
- Các kết quả có cùng thuộc một trạng thái dữ liệu tại một thời điểm duy nhất không?

Một phép duyệt có thể giữ trật tự của các khóa mà vẫn đi qua dữ liệu đang thay đổi. Việc danh sách kết quả trông đã sắp không chứng minh đó là một bản chụp nhất quán.

Vì vậy, không đưa một danh sách stdout cố định cho thí nghiệm vừa duyệt vừa chèn/xóa tự do rồi tuyên bố mọi lần chạy phải giống nhau. Nếu cần kết quả cố định để kiểm chứng logic khoảng, phải ổn định dữ liệu hoặc dùng điểm phối hợp rõ ràng như các ví dụ tuần tự trong bài.

### 7.2. View có thứ tự không tạo giao dịch theo khoảng

Giả sử ứng dụng lấy `subMap`, tính tổng các giá trị rồi xóa khoảng. Trong lúc đó, luồng khác có thể thêm, sửa hoặc xóa mục. Không có căn cứ coi “tính tổng rồi xóa” là một hành động nguyên tử.

Các thao tác xử lý nhiều mục như `putAll`, `clear` hay duyệt `forEach` không nên được xem là cùng một lần chuyển trạng thái cho tất cả mục. Tương tự, `size()` và kết quả duyệt ở một thời điểm khác không tạo một cặp số liệu đồng bộ.

Tài liệu `ConcurrentSkipListSet` còn nhắc rằng `size()` không phải thao tác thời gian hằng số và số đếm có thể không phản ánh một trạng thái ổn định khi bị sửa đồng thời. Không dùng số đếm vừa đọc làm chỗ giữ trước khả năng cho một thao tác sau.

Nếu nghiệp vụ đòi hỏi một báo cáo đúng tại cùng một mốc, cần thêm cơ chế: các bên cùng tuân thủ một khóa ngoài, dữ liệu được công bố theo phiên bản bất biến, hoặc nguồn có khả năng tạo bản chụp/giao dịch phù hợp. Chỉ bên đọc tự khóa một đối tượng trong khi bên ghi không tham gia thì không tạo được ranh giới đó.

### 7.3. Hai lời gọi đúng riêng lẻ vẫn có khoảng trống giữa chúng

Đoạn minh họa sau có vấn đề khi nhiều bên cùng lấy việc:

```java
// Mã minh họa SAI, chưa phải chương trình độc lập.
Integer key = pending.firstKey();
String value = pending.remove(key);
process(value);
```

Sau khi một bên đọc được khóa, bên khác có thể đã lấy mất mục đó. Bên đầu không còn chắc nhận được giá trị nào, và trường hợp map rỗng cũng phải xử lý.

Nếu đúng nhu cầu là lấy và xóa mục đầu, dùng phép biểu diễn trực tiếp hành động đó là `pollFirstEntry()`. Nếu chỉ muốn đọc, dùng `firstEntry()` rồi chấp nhận rằng kết quả đọc không phải việc đặt chỗ độc quyền.

Tương tự, muốn chỉ thêm khi chưa có khóa thì dùng `putIfAbsent`, không tự ghép `containsKey` rồi `put`. Muốn xóa hoặc thay đúng giá trị đã quan sát thì cân nhắc dạng có giá trị mong đợi như `remove(key, oldValue)` hoặc `replace(key, oldValue, newValue)`.

Một phép cập nhật có điều kiện cũng chỉ xử lý điều kiện nó được giao. Nó không tự xác nhận rằng mục vừa đọc là ứng viên tốt nhất trên toàn bộ khoảng nếu các khóa khác đồng thời thay đổi.

### 7.4. Không suy rộng số lần gọi callback giữa các lớp

Với `ConcurrentSkipListMap`, tài liệu `computeIfAbsent`, `computeIfPresent`, `compute` không cam kết hàm tính toán chỉ được thực hiện một lần một cách nguyên tử theo giả định thường bị gán cho mọi map đồng thời. Khi tranh chấp, cần tránh đặt tác động bên ngoài chỉ được phép xảy ra một lần vào hàm tính toán. Xem [hợp đồng computeIfAbsent của ConcurrentSkipListMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentSkipListMap.html#computeIfAbsent(K,java.util.function.Function)).

Ví dụ suy luận: map cuối cùng chỉ giữ một kết quả không chứng minh dịch vụ ngoài chỉ được gọi một lần để tạo kết quả đó. Nếu cần phối hợp việc tải, phải thiết kế vòng đời công việc rõ ràng thay vì dựa vào tên phương thức giống nhau giữa các lớp.

## 8. Nhiều luồng cùng lấy mục đầu

### 8.1. Chương trình dùng pollFirstEntry

Ví dụ này nạp 40 mục trước, rồi cho bốn luồng cùng lấy và xóa mục đầu. Trong giai đoạn lấy mục không có bên thêm lại hoặc thay dữ liệu.

Tệp `ConcurrentDrainDemo.java`:

```java
import java.util.ArrayList;
import java.util.HashSet;
import java.util.Map;
import java.util.concurrent.ConcurrentLinkedQueue;
import java.util.concurrent.ConcurrentSkipListMap;
import java.util.concurrent.CyclicBarrier;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class ConcurrentDrainDemo {
    public static void main(String[] args) throws Exception {
        var pending = new ConcurrentSkipListMap<Integer, String>();
        for (int id = 1; id <= 40; id++) {
            pending.put(id, "job-" + id);
        }

        var removedIds = new ConcurrentLinkedQueue<Integer>();
        var start = new CyclicBarrier(4);
        var pool = Executors.newFixedThreadPool(4);
        var futures = new ArrayList<Future<Void>>();

        try {
            for (int i = 0; i < 4; i++) {
                futures.add(pool.submit(() -> {
                    start.await(10, TimeUnit.SECONDS);
                    Map.Entry<Integer, String> entry;
                    while ((entry = pending.pollFirstEntry()) != null) {
                        removedIds.add(entry.getKey());
                    }
                    return null;
                }));
            }
            for (Future<Void> future : futures) {
                future.get(10, TimeUnit.SECONDS);
            }
            var unique = new HashSet<>(removedIds);
            System.out.println("removedCount=" + removedIds.size());
            System.out.println("uniqueCount=" + unique.size());
            System.out.println("remainingCount=" + pending.size());
            System.out.println("coversAllIds=" +
                    (unique.size() == 40 && unique.contains(1) && unique.contains(40)));
        } finally {
            pool.shutdownNow();
        }
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 ConcurrentDrainDemo.java
java ConcurrentDrainDemo
```

Stdout:

```text
removedCount=40
uniqueCount=40
remainingCount=0
coversAllIds=true
```

`pollFirstEntry()` vừa trả kết quả vừa loại liên kết tương ứng. Mỗi luồng đưa mã đã lấy vào một hàng đợi đồng thời để luồng chính kiểm tra sau khi các tác vụ hoàn tất.

Kết quả được chọn để ổn định theo ý nghĩa thí nghiệm:

- Có 40 lần nhận được mục.
- Có 40 mã khác nhau.
- Map không còn mục.
- Tất cả mã có thể có đều đến từ miền 1 đến 40 đã nạp ban đầu.

Chương trình không in “luồng 1 lấy những mã nào” vì việc phân chia phụ thuộc lịch thực thi. Nó cũng không buộc một luồng phải lấy được phần công việc bằng với luồng khác.

### 8.2. Lấy trước và hoàn thành trước là hai sự kiện khác nhau

Ngay cả khi mỗi lần lấy chọn mục đầu, thứ tự bắt đầu xử lý hoặc hoàn tất vẫn có thể khác:

```text
Luồng A lấy mục 1 → xử lý lâu
Luồng B lấy mục 2 → xử lý nhanh → hoàn tất trước
Luồng A hoàn tất sau
```

Nếu nghiệp vụ đòi hỏi hoàn tất nghiêm ngặt theo thứ tự, cần một cơ chế điều phối khác hoặc bước ghi nhận kết quả theo thứ tự. Cấu trúc dữ liệu chỉ quyết định phần lấy mục mà nó quản lý.

Cũng không thể suy ra xử lý bên ngoài “đúng một lần” từ việc mục bị xóa một lần. Nếu một luồng lấy mục rồi chương trình dừng trước khi xử lý xong, map đã mất mục đó. Nếu cần phục hồi, xác nhận hoàn tất hay độ bền sau khi tiến trình dừng, phải thiết kế trạng thái và lưu trữ phù hợp.

### 8.3. Rỗng tại thời điểm lấy chưa có nghĩa nguồn việc đã kết thúc

Trong thí nghiệm, không có bên sản xuất thêm mục nên thấy `null` là điều kiện kết thúc hợp lệ cho mỗi luồng.

Nếu một bên khác có thể chèn việc sau đó, `null` chỉ cho biết lần lấy hiện tại không nhận được mục. Vòng lặp phải có cơ chế nhận thông báo, chờ hoặc điều kiện kết thúc riêng. Không dùng vòng quay liên tục chỉ để hỏi map có phần tử mới hay chưa.

Nếu mục tiêu chính là một hàng đợi ưu tiên có thao tác chờ khi chưa có việc, hãy xem một cấu trúc hàng đợi phù hợp như `PriorityBlockingQueue`. Nó có thao tác lấy có chờ, nhưng iterator không bảo đảm duyệt theo thứ tự ưu tiên và nó không cung cấp cùng bộ truy vấn khoảng của map. Xem [PriorityBlockingQueue Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/PriorityBlockingQueue.html).

## 9. Thiết kế chỉ mục thời gian bằng khóa ghép

### 9.1. Vì sao timestamp riêng lẻ chưa đủ?

Nếu hai sự kiện có cùng mốc thời gian và map chỉ dùng thời gian làm khóa, lần ghi sau có thể thay giá trị trước. Một map không tự trở thành cấu trúc chứa nhiều giá trị cho cùng khóa.

Có thể chọn khóa ghép:

```text
EventKey = (time, sequence)

So sánh time trước
Nếu time bằng nhau → so sánh sequence
```

Trong ví dụ, `time` là số mili giây trên một trục thời gian giả lập chung; `sequence` dương và phân biệt các sự kiện cần giữ trong cùng mốc. Quy tắc dương cũng cho phép dùng số 0 làm cận trước mọi sự kiện của một mốc.

Tệp `EventWindowDemo.java`:

```java
import java.util.Comparator;
import java.util.concurrent.ConcurrentSkipListMap;

public class EventWindowDemo {
    record EventKey(long time, long sequence) {}

    public static void main(String[] args) {
        Comparator<EventKey> order = Comparator.comparingLong(EventKey::time)
                .thenComparingLong(EventKey::sequence);
        var events = new ConcurrentSkipListMap<EventKey, String>(order);

        events.put(new EventKey(900, 1), "before");
        events.put(new EventKey(1000, 2), "A");
        events.put(new EventKey(1000, 3), "B");
        events.put(new EventKey(1500, 4), "C");
        events.put(new EventKey(2000, 5), "at-end");

        // Domain rule: stored sequence numbers are strictly positive.
        EventKey from = new EventKey(1000, 0);
        EventKey to = new EventKey(2000, 0);
        var window = events.subMap(from, true, to, false);

        System.out.println("windowValues=" + window.values());
        var afterLastInGroup = new EventKey(1000, Long.MAX_VALUE);
        System.out.println("lastAtOrBefore1000=" +
                events.floorEntry(afterLastInGroup).getValue());

        events.put(new EventKey(1200, 6), "D");
        System.out.println("liveWindowValues=" + window.values());

        var copy = new ConcurrentSkipListMap<EventKey, String>(window);
        events.put(new EventKey(1300, 7), "E");
        System.out.println("copyValues=" + copy.values());
        System.out.println("rootWindowValues=" + window.values());

        events.headMap(from, false).clear();
        System.out.println("firstRemaining=" + events.firstEntry().getValue());
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 EventWindowDemo.java
java EventWindowDemo
```

Stdout:

```text
windowValues=[A, B, C]
lastAtOrBefore1000=B
liveWindowValues=[A, B, D, C]
copyValues=[A, B, D, C]
rootWindowValues=[A, B, D, E, C]
firstRemaining=A
```

### 9.2. Diễn giải khoảng theo toàn bộ khóa

Hai cận là `(1000, 0)` và `(2000, 0)`. Vì mọi sequence được lưu đều dương:

- Mọi sự kiện ở thời gian 1000 đứng sau cận trái, nên A và B được lấy.
- Sự kiện C ở thời gian 1500 nằm bên trong.
- Sự kiện ở thời gian 2000 với sequence 5 đứng sau cận phải và bị loại.
- Khoảng thực hiện ý nghĩa thời gian `[1000, 2000)`.

Đây là kết quả của mô hình dữ liệu đã đặt ra. Nếu ứng dụng cho phép sequence âm hoặc dùng một quy tắc khóa khác, cận 0 không còn đúng. Không sao chép “giá trị đặc biệt làm cận” sang một miền dữ liệu khác mà bỏ điều kiện đi kèm.

Muốn tìm mục cuối không muộn hơn 1000, chương trình dùng mục tiêu `(1000, Long.MAX_VALUE)` cho `floorEntry`. Kết quả là B, phần tử cuối trong nhóm thời gian 1000 theo thứ tự khóa. Ứng dụng thật phải xử lý trường hợp không có mục phù hợp trước khi gọi `getValue()`; chương trình biết chắc dữ liệu đã nạp có kết quả đó.

### 9.3. Một view sống và một bản sao độc lập

`window` được tạo trước khi thêm D ở 1200. Sau khi thêm, view duyệt A, B, D, C. Nó tiếp tục nối với dữ liệu gốc.

Biến `copy` được tạo từ window rồi sau đó map gốc mới thêm E. Bản sao không có E, còn view gốc có E. Trong chương trình tuần tự này, điểm sao chép nằm giữa hai câu lệnh rõ ràng nên kết quả dễ đối chiếu.

Nếu có luồng ghi trong lúc tạo bản sao, việc tạo một cấu trúc độc lập không tự đảm bảo nó là ảnh chụp nguyên tử của nguồn tại đúng một thời điểm. Có hai thuộc tính riêng:

- Sau khi tạo xong, các thay đổi cấu trúc của map gốc không tự phản ánh vào bản sao.
- Quá trình thu thập dữ liệu để sao chép có mức nhất quán nào khi nguồn đang thay đổi?

Ngoài ra, sao chép map vẫn là sao chép các tham chiếu khóa và giá trị. Dùng các record khóa bất biến và giá trị chuỗi trong ví dụ giúp giữ phần này đơn giản.

### 9.4. Xóa dữ liệu cũ cần thêm quy tắc về thời gian đến

Lệnh `events.headMap(from, false).clear()` xóa những khóa đứng trước `(1000, 0)`. Trong dữ liệu của ví dụ, mục `before` bị xóa và mục đầu còn lại là A.

Nếu có sự kiện đến trễ với thời gian nhỏ hơn 1000 được chèn sau khi dọn, dữ liệu cũ lại có thể xuất hiện. Một lần dọn khoảng không tạo ra quy tắc cấm ghi vào khoảng đó.

Ứng dụng cần xác định có nhận sự kiện trễ không, mốc dọn dựa vào thời gian sự kiện hay thời gian nhận, và bên ghi phải kiểm tra điều kiện nào. Các quyết định ấy thuộc mô hình lưu trữ và xử lý sự kiện, không được map tự suy ra.

### 9.5. Khóa ghép cũng ảnh hưởng đến phân trang

Nếu dùng kết quả cuối trang làm mốc cho trang tiếp theo, dùng đầy đủ khóa ghép và cận loại trừ giúp tránh nhầm những sự kiện có cùng thời gian.

Đó mới là quy tắc tiếp tục theo thứ tự. Nó chưa tạo ảnh chụp cho tất cả trang: các sự kiện mới được thêm trước mốc đã đi qua có thể không xuất hiện ở những trang sau, và các mục bị xóa sẽ thay đổi kết quả.

Nếu yêu cầu phân trang trên một tập dữ liệu cố định, phải gắn với phiên bản hoặc nguồn ảnh chụp. Đừng dùng thứ tự tăng dần để hứa mức nhất quán mà hệ thống chưa cung cấp.

## 10. Chọn cấu trúc và kiểm tra cách sử dụng

### 10.1. Chọn theo câu hỏi phải trả lời

| Nhu cầu chính | Hướng cân nhắc |
|---|---|
| Tra cứu khóa chính xác, không cần lân cận hay khoảng | Một map đồng thời dựa trên băm có thể phù hợp |
| Tra cứu khóa, lân cận và khoảng, nhiều luồng cùng cập nhật | `ConcurrentSkipListMap` |
| Giữ tập phần tử duy nhất theo một thứ tự, cần lân cận hoặc khoảng | `ConcurrentSkipListSet` |
| Chỉ có một luồng hoặc mọi truy cập đã được phối hợp bên ngoài | Có thể không cần lớp đồng thời |
| Lấy việc theo ưu tiên và chờ khi chưa có việc | Xem cấu trúc hàng đợi với thao tác chờ |
| Cần nhiều mục thay đổi như một giao dịch | Cần thêm cơ chế ở mức ứng dụng hoặc nguồn lưu trữ |

Bảng không khẳng định một lớp luôn nhanh hơn lớp khác. Số lượng mục, chi phí comparator, tỷ lệ đọc/ghi, chiều duyệt và kích thước khoảng đều ảnh hưởng đến lựa chọn.

### 10.2. Những chi phí thường bị bỏ qua

Một comparator dài, đọc nhiều trường hoặc cấp phát dữ liệu tạm có thể làm truy vấn đắt dù cấu trúc có đặc tính tìm kiếm tốt. Nên chuẩn hóa khóa một lần khi phù hợp thay vì lặp lại công việc nặng trong từng phép so sánh.

Lấy một view không có nghĩa đã xử lý xong toàn bộ khoảng. Muốn đọc, tổng hợp, xuất hoặc xóa nhiều mục vẫn có công việc theo số mục liên quan. Không lấy đặc tính O(log n) của một thao tác cơ bản để gán cho việc in toàn bộ dữ liệu.

`containsValue` cũng không phải truy vấn có chỉ mục theo giá trị. Nếu ứng dụng thường hỏi theo một trường trong V, cần xem có nên đưa trường đó vào khóa hoặc có một chỉ mục khác; duy trì nhiều chỉ mục lại tạo yêu cầu nhất quán riêng.

Không xem skip list là một danh sách có vị trí số. Nó không tự cung cấp phép lấy “phần tử thứ 10.000” với một cam kết chi phí như truy cập mảng. Nếu thứ hạng theo số là yêu cầu cốt lõi, cần một thiết kế thích hợp cho thứ hạng.

## 11. Thực hành và tự kiểm tra

### Bài 1: chọn phép điều hướng

Với khóa 10, 20, 30, 40, hãy tìm:

1. Khóa gần nhất trước 20 nhưng không lấy chính 20.
2. Khóa gần nhất không nhỏ hơn 25.
3. Khóa gần nhất không lớn hơn 20.
4. Khóa sau 40.

Hướng giải thích: lần lượt dùng `lowerKey(20)`, `ceilingKey(25)`, `floorKey(20)`, `higherKey(40)`. Kết quả là 10, 30, 20 và `null`. Sau đó tự làm lại trên `descendingMap` bằng cách diễn giải theo thứ tự của view.

### Bài 2: cận khoảng và tác động của view

Tạo map có khóa 10, 20, 30, 40, 50 rồi lấy `subMap(20, true, 40, false)`.

- Vì sao khóa 40 không nằm trong kết quả?
- Nếu thêm 25 qua view, map gốc có thay đổi không?
- Nếu map gốc thêm 35 sau khi tạo view, view có cần được tạo lại không?
- Nếu gọi `clear` qua view, những khóa nào còn lại?

Trong điều kiện không có cập nhật khác, kết quả sau khi thêm 25, thêm 35 và xóa view là 10, 40, 50. Cần giải thích bằng ranh giới khoảng và quan hệ dùng chung dữ liệu, không dựa vào thứ tự chèn.

### Bài 3: comparator và dữ liệu bị gộp

Một set chứa đơn hàng; comparator chỉ so sánh ngày đặt. Hai đơn hàng khác mã có cùng ngày.

Hãy giải thích vì sao lần thêm sau có thể trả `false`, dù `equals` của hai đơn hàng là `false`. Sau đó thiết kế danh tính và comparator đủ thông tin để giữ cả hai mà nhất quán với `equals`.

Đừng chỉ thêm một trường tăng ngẫu nhiên vào comparator. Hãy xác định trường đó có thuộc danh tính đối tượng hay không và có ổn định khi dữ liệu nằm trong cấu trúc không.

### Bài 4: tổng tiền trong một khoảng

Một luồng duyệt submap để cộng số tiền; luồng khác vẫn cập nhật giá trị và thêm mục.

Vì sao kết quả vẫn có thể không phải tổng ở một thời điểm duy nhất dù không có `ConcurrentModificationException`? Nếu báo cáo bắt buộc là một ảnh chụp tại cùng mốc, các bên phải tham gia cơ chế nào?

Hướng giải thích: tính an toàn khi duyệt và tính nhất quán của một báo cáo nhiều mục là hai yêu cầu riêng. Cần khóa phối hợp, phiên bản bất biến hoặc nguồn giao dịch phù hợp với mức chính xác được yêu cầu.

### Bài 5: lấy việc và hoàn tất việc

Dùng `pollFirstEntry` để nhiều luồng cùng nhận việc. Một việc nhỏ được lấy sau nhưng hoàn tất trước việc lớn được lấy trước.

Điều này có mâu thuẫn với thứ tự của map không? Nếu tiến trình dừng sau khi xóa một mục nhưng trước khi xử lý xong, dữ liệu có tự quay lại map không?

Hướng giải thích: thứ tự lấy, thứ tự hoàn tất và khả năng phục hồi là ba vấn đề khác nhau. Phép lấy/xóa nguyên tử không tự cung cấp thứ tự hoàn tất hay độ bền của quy trình.

### Các câu hỏi cần trả lời trong mã thật

1. Thứ tự nằm trên khóa hay trên phần tử nào?
2. Comparator có nhất quán, ổn định và phù hợp với `equals` không?
3. Cận trái và cận phải có được bao gồm không?
4. Phép điều hướng đang gọi trên chiều tăng hay view đảo?
5. Kết quả đang là view, một entry đã quan sát hay bản sao độc lập?
6. Có cần một ảnh chụp chung cho nhiều mục hoặc nhiều trang không?
7. Có chuỗi “đọc rồi ghi” nào phải thay bằng một thao tác có điều kiện hoặc một cơ chế phối hợp không?
8. Phần tử và giá trị bên trong có tự được chia sẻ an toàn, hay chỉ cấu trúc ngoài là đồng thời?

Khi trả lời được các câu hỏi này, người học có thể dùng thứ tự để diễn đạt đúng truy vấn, đồng thời giữ rõ giới hạn của kết quả trong một hệ thống đang thay đổi.
