# size, isEmpty, contains và ý nghĩa giá trị trả về

Khi làm việc với collection, ba câu hỏi xuất hiện rất thường xuyên:

- Hiện có bao nhiêu phần tử?
- Có phần tử nào hay không?
- Có một giá trị cụ thể trong collection hay không?

Java cung cấp `size()`, `isEmpty()` và `contains(Object)` để trả lời ba câu hỏi đó. Tuy đều là thao tác truy vấn, chúng mang ý nghĩa khác nhau. Hiểu đúng giá trị trả về giúp tránh nhầm số phần tử với dung lượng, nhầm sự tồn tại với số lần xuất hiện, hoặc nhầm hai đối tượng có nội dung bằng nhau với cùng một tham chiếu.

Bài này trình bày hợp đồng chung trong Java Collections Framework và các điểm cần kiểm tra ở cách triển khai cụ thể. Ví dụ hoàn chỉnh dùng Java 17 trở lên.

## 1. Ba phương thức, ba loại thông tin

Các chữ ký trong `Collection<E>` là:

```java
int size();
boolean isEmpty();
boolean contains(Object o);
```

Đây là chữ ký API, không phải một chương trình Java độc lập.

| Phương thức | Câu hỏi được trả lời | Giá trị trả về |
| --- | --- | --- |
| `size()` | Có bao nhiêu phần tử đang thuộc collection? | Một số nguyên `int` |
| `isEmpty()` | Collection có rỗng không? | `true` nếu không có phần tử; ngược lại `false` |
| `contains(o)` | Có ít nhất một phần tử tương ứng với giá trị `o` không? | `true` nếu có; `false` nếu không, với đầu vào hợp lệ |

Một danh sách có 10 phần tử vẫn có thể trả `false` cho `contains("Java")`: số lượng không nói lên nội dung. Một danh sách chỉ có một phần tử `null` lại không rỗng: nó có một vị trí đã được chiếm bởi một phần tử hợp lệ của cách triển khai đó.

Các thao tác trên trả lời trạng thái của đối tượng được truy vấn. Chúng không tải dữ liệu từ cơ sở dữ liệu, không tự lọc phần tử theo điều kiện nghiệp vụ và không đếm những phần tử mà chương trình “dự định” thêm sau này. [Java 17: Collection](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collection.html)

## 2. size(): số phần tử hiện có

### 2.1. Size không phải capacity

Trong một `ArrayList`, dung lượng mảng bên trong và số phần tử hiện có là hai đại lượng khác nhau:

```java
List<String> names = new ArrayList<>(20);

System.out.println(names.size()); // 0
names.add("Lan");
System.out.println(names.size()); // 1
```

Đây là đoạn minh họa trong một phương thức, với import `java.util.List` và `java.util.ArrayList`.

Tham số `20` chuẩn bị dung lượng ban đầu. Nó không thêm 20 phần tử, cũng không tạo 20 phần tử `null` để người dùng truy cập. Ngay sau khi khởi tạo, `names.get(0)` vẫn không hợp lệ vì danh sách chưa có phần tử nào.

Không suy ra kích thước từ dung lượng đã dự kiến hoặc từ số ô của mảng nội bộ. Chỉ `size()` mô tả số phần tử thuộc danh sách theo API. [Java 17: ArrayList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html)

### 2.2. Phần tử trùng và null vẫn được tính theo cấu trúc

Với một danh sách cho phép giá trị trùng và `null`:

```java
List<String> names = new ArrayList<>();
names.add("Lan");
names.add("Lan");
names.add(null);

System.out.println(names.size()); // 3
```

Hai lần xuất hiện của `"Lan"` chiếm hai vị trí khác nhau. Phần tử `null` chiếm vị trí thứ ba. `size()` không tự loại trùng, bỏ qua `null` hoặc đếm số người duy nhất.

Nếu chuyển dữ liệu sang `HashSet`, cấu trúc tập chỉ giữ một đại diện cho mỗi giá trị theo quy tắc bằng nhau của nó:

```java
Set<String> unique = new HashSet<>(names);
System.out.println(unique.size()); // 2: "Lan" và null
```

Các đoạn này cần import các kiểu được dùng và đặt trong một phương thức. Kết quả khác nhau do nội dung thực tế của hai cấu trúc khác nhau; `size()` không mang hai ý nghĩa tùy tiện.

Nếu cần đếm số lần một giá trị xuất hiện, `size()` không phải câu trả lời. Chẳng hạn, danh sách `["Lan", "Lan", null]` có kích thước 3 nhưng `"Lan"` xuất hiện 2 lần. Có thể dùng vòng lặp hoặc thao tác đếm theo đúng phép so sánh cần thiết.

### 2.3. Size phản ánh thay đổi đã thực hiện

Sau khi xóa một lần xuất hiện khỏi danh sách:

```java
names.remove("Lan");
System.out.println(names.size());          // 2
System.out.println(names.contains("Lan")); // true
```

Danh sách vẫn còn một `"Lan"` và một `null`. Xóa một phần tử không đồng nghĩa xóa mọi phần tử bằng nó.

Sau `clear()`, nếu thao tác được cách triển khai hỗ trợ và thành công, collection không còn phần tử nên `size()` là 0.

### 2.4. Kiểu int có giới hạn

Hợp đồng `Collection.size()` trả `Integer.MAX_VALUE` nếu số phần tử vượt giới hạn biểu diễn đó. Vì vậy, không nên dùng API này như một bộ đếm `long` không giới hạn.

Đây là giới hạn hợp đồng, không khẳng định một collection cụ thể có thể thực sự chứa số phần tử lớn như vậy trong bộ nhớ. Với những bài toán dữ liệu cực lớn, cần xem cả cấu trúc lưu trữ và API đếm thực tế. [Java 17: Collection.size](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collection.html#size())

## 3. isEmpty(): có phần tử hay không?

### 3.1. Giá trị boolean diễn đạt trực tiếp ý định

`isEmpty()` trả:

- `true`: collection không có phần tử.
- `false`: collection có ít nhất một phần tử.

Trong trạng thái ổn định, `collection.isEmpty()` và `collection.size() == 0` cho cùng câu trả lời. Khi chỉ cần biết có dữ liệu hay không, `isEmpty()` diễn đạt ý định trực tiếp hơn:

```java
if (orders.isEmpty()) {
    System.out.println("Chưa có đơn hàng");
}
```

Đây là đoạn minh họa; `orders` là một collection đã được khởi tạo. Không cần tính toàn bộ số lượng chỉ để kiểm tra rỗng.

Tuy nhiên, không kết luận rằng `isEmpty()` luôn có chi phí hằng số cho mọi lớp, hoặc luôn nhanh hơn `size()` trong mọi trường hợp. Interface quy định ý nghĩa; chi phí phụ thuộc cách triển khai.

### 3.2. Rỗng khác với null

Ba trạng thái sau khác nhau:

```java
List<String> missing = null;
List<String> empty = new ArrayList<>();

List<String> oneNull = new ArrayList<>();
oneNull.add(null);
```

| Biến | Có đối tượng danh sách không? | Kích thước |
| --- | --- | --- |
| `missing` | Không | Không thể gọi `size()` hay `isEmpty()` |
| `empty` | Có | 0 |
| `oneNull` | Có | 1 |

Gọi `missing.isEmpty()` ném `NullPointerException`: chưa có đối tượng để nhận lời gọi. Trong khi đó, `oneNull.isEmpty()` là `false`.

Nếu một API quy định luôn trả collection, nên trả collection rỗng khi không có kết quả. Người gọi khi đó có thể dùng `isEmpty()` mà không phải đoán `null` có nghĩa gì.

Nếu đang tích hợp với API có thể trả `null`, cần xử lý theo hợp đồng cụ thể:

```java
if (items == null || items.isEmpty()) {
    System.out.println("Không có danh sách để xử lý");
}
```

Đây là đoạn minh họa cho trường hợp nghiệp vụ chủ động xem hai trạng thái tương đương. Không tự gộp `null` và rỗng nếu chúng biểu thị hai trạng thái khác nhau, chẳng hạn “chưa tải” và “đã tải nhưng không có kết quả”.

## 4. contains(): hỏi sự tồn tại, không hỏi vị trí hoặc số lượng

### 4.1. True nghĩa là có ít nhất một phần tử phù hợp

Với danh sách `["Lan", "Lan", null]`:

| Lời gọi | Kết quả |
| --- | --- |
| `contains("Lan")` | `true` |
| `contains("Minh")` | `false` |
| `contains(null)` | `true`, vì `ArrayList` này chứa `null` |

Kết quả `true` không cho biết:

- Có bao nhiêu phần tử bằng giá trị đang tìm.
- Phần tử nằm ở chỉ số nào.
- Phần tử được thêm lúc nào.
- Đối tượng được lưu có phải chính tham chiếu truyền vào không.

Muốn biết vị trí trong `List`, cần API như `indexOf`. Muốn lấy đối tượng phù hợp, cần tìm và trả đối tượng ấy. Muốn đếm, cần thao tác đếm.

Không dùng `contains` rồi tiếp tục tìm lại cùng phần tử nếu có thể thực hiện việc tìm và lấy kết quả trong một lượt; điều đó vừa tránh lặp công việc, vừa giúp mục đích của mã rõ hơn.

### 4.2. Bình đẳng giá trị khác với cùng tham chiếu

Một mô hình đọc hợp đồng chung của `contains(o)` là: có tồn tại phần tử `e` sao cho `Objects.equals(o, e)` đúng hay không.

Với chuỗi:

```java
List<String> names = new ArrayList<>();
names.add("Lan");

String query = new String("Lan");
System.out.println(names.contains(query)); // true
```

Dù `query` là một đối tượng mới, `String.equals` so nội dung, nên `contains` vẫn trả `true`.

Đối với lớp tự định nghĩa, kết quả phụ thuộc quy tắc bằng nhau của lớp đó. Một lớp không ghi đè `equals` thường vẫn dùng bình đẳng tham chiếu từ `Object`. Hai đối tượng có trường trông giống nhau không tự nhiên trở thành bằng nhau.

Cũng không nên hiểu mô tả hợp đồng là yêu cầu mọi lớp phải gọi `equals` trên mọi phần tử. Một cấu trúc băm có thể dùng mã băm để loại bớt ứng viên trước. Ý nghĩa kết quả và thuật toán thực thi là hai điều cần phân biệt.

### 4.3. Contains nhận Object nên truy vấn khác kiểu có thể biên dịch

Chữ ký là `contains(Object o)`, không phải `contains(E o)`. Vì vậy:

```java
List<Integer> numbers = List.of(1, 2, 3);

System.out.println(numbers.contains(1));   // true
System.out.println(numbers.contains(1L));  // false
```

`1` được boxing thành `Integer`; `1L` được boxing thành `Long`. `Integer.equals` không coi một `Long` là bằng nó chỉ vì cùng giá trị số học.

Đây không phải phép tìm “số 1 bất kể kiểu”. Nếu dữ liệu có nhiều kiểu số, hãy chuẩn hóa kiểu hoặc viết điều kiện so sánh rõ ràng trước khi dùng cấu trúc.

Không suy ra rằng truy vấn sai kiểu luôn trả `false`. Một số collection có thể ném `ClassCastException` khi đối tượng không tương thích với cách so sánh hoặc kiểu phần tử được hỗ trợ.

### 4.4. HashSet cần equals và hashCode nhất quán

Khi tìm trong `HashSet`, mã băm hỗ trợ xác định vùng ứng viên và phép so sánh bằng nhau xác nhận giá trị phù hợp.

Hai nguyên tắc thiết yếu:

1. Nếu `a.equals(b)` là `true`, `a.hashCode()` và `b.hashCode()` phải bằng nhau.
2. Không sửa các trường dùng cho `equals`/`hashCode` khi đối tượng đang là phần tử trong tập băm.

Nếu một lớp vi phạm hợp đồng hoặc khóa thay đổi sau khi thêm, có thể xuất hiện tình huống phần tử vẫn thấy khi duyệt nhưng `contains` không tìm được như mong đợi. Khi chẩn đoán, cần kiểm tra mô hình bình đẳng của đối tượng, không chỉ nghi ngờ collection.

Cùng mã băm không bảo đảm bằng nhau: các giá trị khác nhau có thể va chạm mã băm và vẫn cùng tồn tại. [Java 17: HashSet](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashSet.html)

### 4.5. TreeSet dùng thứ tự so sánh để tìm phần tử

`TreeSet` dùng thứ tự tự nhiên hoặc comparator. Trong cấu trúc này, hai phần tử có kết quả so sánh bằng 0 được xử lý là tương đương để tìm và loại trùng.

Một ví dụ dễ quan sát là `BigDecimal`:

```java
BigDecimal first = new BigDecimal("1.0");
BigDecimal query = new BigDecimal("1.00");

System.out.println(first.equals(query));    // false
System.out.println(first.compareTo(query)); // 0
```

`equals` của `BigDecimal` xét cả giá trị và scale; `compareTo` so theo giá trị số. Do đó:

```java
List<BigDecimal> list = List.of(first);
Set<BigDecimal> tree = new TreeSet<>();
tree.add(first);

System.out.println(list.contains(query)); // false
System.out.println(tree.contains(query)); // true
```

Các đoạn minh họa này cần import `BigDecimal`, `List`, `Set` và `TreeSet`.

Điểm cần học không phải “`contains` không đáng tin”, mà là phải biết quy tắc bình đẳng của dữ liệu và cấu trúc. Với tập cây, thứ tự nhất quán với `equals` là điều kiện để hành vi tuân thủ đầy đủ hợp đồng chung của `Set`. Đừng chọn comparator chỉ vì đẹp khi sắp mà không xét việc nó đồng thời quyết định tính duy nhất. [Java 17: TreeSet](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeSet.html), [BigDecimal](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html)

### 4.6. Contains null không luôn trả false khi collection không hỗ trợ null

Một collection không cho phép `null` có thể ném `NullPointerException` khi gọi `contains(null)`, hoặc trả `false` trong những trường hợp được hợp đồng cho phép.

Vì vậy, không dùng một phép thử chung kiểu “cứ hỏi `contains(null)` rồi xem” để thay thế việc biết hợp đồng đầu vào. Ví dụ `ArrayList` trong bài cho phép `null`, nhưng không nên mang kỳ vọng ấy áp dụng cho mọi collection khác.

Các ngoại lệ này không biến `false` thành giá trị biểu thị lỗi. `false` nghĩa là không tìm thấy theo hợp đồng; ngoại lệ nghĩa là yêu cầu không thể được xử lý hợp lệ trong tình huống đó.

## 5. Với Map, phải nói rõ đang tìm khóa hay giá trị

`Map<K,V>` không kế thừa `Collection<E>`, nhưng cũng có `size()` và `isEmpty()`:

- `size()` đếm số ánh xạ khóa–giá trị.
- `isEmpty()` hỏi có ánh xạ nào không.
- `containsKey(key)` hỏi khóa có tồn tại không.
- `containsValue(value)` hỏi có ít nhất một ánh xạ đến giá trị đó không.

```java
Map<String, String> notes = new HashMap<>();
notes.put("A", null);

System.out.println(notes.size());              // 1
System.out.println(notes.isEmpty());           // false
System.out.println(notes.containsKey("A"));    // true
System.out.println(notes.containsValue(null)); // true
```

Đoạn minh họa dùng `HashMap`, vốn cho phép giá trị `null`. Một ánh xạ đến `null` vẫn là một ánh xạ.

Không viết `map.get(key) != null` như cách kiểm tra tồn tại tổng quát khi map cho phép giá trị `null`: khóa có thể đã tồn tại và đang ánh xạ đến `null`.

`containsKey` và `containsValue` cũng không nhất thiết có cùng chi phí. Map được tổ chức để tra cứu theo khóa thường không có chỉ mục tương đương theo giá trị. Hãy dùng đúng câu hỏi thay vì coi hai phương thức là hoán đổi được. [Java 17: Map](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html)

## 6. Hợp đồng chung không cam kết mọi truy vấn đều nhanh như nhau

| Cấu trúc | `size()` thường gặp | `contains()` thường gặp |
| --- | --- | --- |
| `ArrayList` | Lấy số lượng đang quản lý | Duyệt tìm, tuyến tính trong trường hợp tổng quát |
| `LinkedList` | Lấy số lượng đang quản lý | Duyệt các nút để tìm |
| `HashSet` | Lấy số lượng đang quản lý | Trung bình thuận lợi khi mã băm phân bố tốt |
| `TreeSet` | Lấy số lượng đang quản lý | Theo đường tìm trong cây, chi phí logarit |
| `ConcurrentLinkedQueue` | Phải duyệt để đếm | Phải tìm theo dữ liệu của hàng đợi |

Bảng nhằm chỉ ra sự khác nhau về đường thực thi. Chi phí `equals`, comparator, mã băm và truy cập bộ nhớ còn ảnh hưởng thời gian thực tế.

`AbstractCollection` cung cấp cách triển khai `isEmpty()` dựa trên `size() == 0` và `contains` dựa trên duyệt. Lớp cụ thể có thể ghi đè. Không dùng cách triển khai mặc định để suy ra mọi collection đều có cùng hiệu năng. [Java 17: AbstractCollection](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/AbstractCollection.html)

Ví dụ, với một danh sách lớn, gọi `contains` lặp lại cho từng phần tử đầu vào có thể tạo tổng chi phí lớn. Nếu bài toán chủ yếu là kiểm tra thành viên và không cần giữ lần lặp, một tập được xây dựng một lần có thể phù hợp hơn. Trước khi chuyển, phải xác nhận quy tắc bằng nhau và yêu cầu giữ thứ tự.

## 7. Truy vấn không tự bảo vệ chuỗi thao tác đồng thời

### 7.1. Kết quả đúng lúc kiểm tra chưa chắc còn đúng lúc sử dụng

Đoạn minh họa sau có khoảng trống giữa hai thao tác:

```java
if (!queue.isEmpty()) {
    String job = queue.poll();
    // Luồng khác có thể đã lấy phần tử cuối trước poll().
}
```

Nếu `queue` được nhiều luồng tiêu thụ, nó có thể rỗng sau lần kiểm tra. Với queue không cho phép phần tử `null`, thường có thể gọi thao tác lấy trước rồi xử lý kết quả:

```java
String job = queue.poll();
if (job != null) {
    process(job);
}
```

Đây là mã minh họa luồng xử lý, không phải chương trình độc lập: `queue` và `process` được ứng dụng cung cấp. Muốn chờ khi rỗng, có thể cần API như `take()` của `BlockingQueue`, thay vì tự kiểm tra liên tục.

Tương tự, `if (!list.contains(x)) list.add(x)` không tự bảo đảm không trùng khi hai luồng cùng chạy. Phải dùng một thao tác đáp ứng yêu cầu nguyên tử hoặc một vùng đồng bộ bao trùm cả quy trình.

### 7.2. Size có thể không phải ảnh chụp toàn hệ thống

Tài liệu `ConcurrentLinkedQueue` nêu rằng `size()` phải duyệt và có thể không chính xác nếu hàng đợi đổi trong lúc đếm. Không dùng kết quả này để tự áp đặt một giới hạn sức chứa có tính nguyên tử:

```java
// Không đủ để bảo đảm queue không vượt 100 phần tử khi có ghi đồng thời.
if (queue.size() < 100) {
    queue.offer(job);
}
```

Nếu cần giới hạn số công việc chờ, chọn một queue có sức chứa và cơ chế thêm phù hợp với yêu cầu đó.

Các phương thức truy vấn cũng không làm một `ArrayList` hoặc `HashSet` thông thường an toàn khi luồng khác đang sửa mà không có cơ chế phối hợp. Không gọi `size()` như một cách “đồng bộ ngầm” hoặc bảo đảm nhìn thấy mọi thay đổi. [Java 17: ConcurrentLinkedQueue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentLinkedQueue.html)

## 8. Chương trình Java 17 hoàn chỉnh

Lưu mã sau vào `CollectionQueriesDemo.java`:

```java
import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeSet;

public class CollectionQueriesDemo {
    public static void main(String[] args) {
        List<String> names = new ArrayList<>(20);
        System.out.println("initial size = " + names.size());
        System.out.println("initial empty = " + names.isEmpty());

        names.add("Lan");
        names.add("Lan");
        names.add(null);
        System.out.println("list size = " + names.size());
        System.out.println("list empty = " + names.isEmpty());
        System.out.println("contains Lan = " + names.contains(new String("Lan")));
        System.out.println("contains null = " + names.contains(null));
        System.out.println("contains Minh = " + names.contains("Minh"));

        Set<String> unique = new HashSet<>(names);
        System.out.println("set size = " + unique.size());

        names.remove("Lan");
        System.out.println("after one removal size = " + names.size());
        System.out.println("after one removal contains Lan = " + names.contains("Lan"));

        List<Integer> numbers = List.of(1, 2, 3);
        System.out.println("contains Integer 1 = " + numbers.contains(1));
        System.out.println("contains Long 1 = " + numbers.contains(1L));

        BigDecimal first = new BigDecimal("1.0");
        BigDecimal query = new BigDecimal("1.00");
        List<BigDecimal> prices = List.of(first);
        Set<BigDecimal> sortedPrices = new TreeSet<>();
        sortedPrices.add(first);
        System.out.println("decimal equals = " + first.equals(query));
        System.out.println("decimal comparison = " + first.compareTo(query));
        System.out.println("price list contains = " + prices.contains(query));
        System.out.println("price tree contains = " + sortedPrices.contains(query));

        Map<String, String> notes = new HashMap<>();
        notes.put("A", null);
        System.out.println("map size = " + notes.size());
        System.out.println("map empty = " + notes.isEmpty());
        System.out.println("map contains key A = " + notes.containsKey("A"));
        System.out.println("map contains value null = " + notes.containsValue(null));

        names.clear();
        System.out.println("cleared size = " + names.size());
        System.out.println("cleared empty = " + names.isEmpty());
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 CollectionQueriesDemo.java
java CollectionQueriesDemo
```

Stdout:

```text
initial size = 0
initial empty = true
list size = 3
list empty = false
contains Lan = true
contains null = true
contains Minh = false
set size = 2
after one removal size = 2
after one removal contains Lan = true
contains Integer 1 = true
contains Long 1 = false
decimal equals = false
decimal comparison = 0
price list contains = false
price tree contains = true
map size = 1
map empty = false
map contains key A = true
map contains value null = true
cleared size = 0
cleared empty = true
```

Các nhóm kết quả minh chứng từng điểm:

1. Dung lượng ban đầu 20 không tạo phần tử, nên ban đầu kích thước bằng 0 và rỗng.
2. Hai chuỗi giống nhau cùng một `null` làm danh sách có 3 phần tử, nhưng tập băm có 2 giá trị.
3. Một đối tượng `String` mới vẫn được tìm thấy theo nội dung.
4. Xóa một lần `"Lan"` làm kích thước giảm nhưng không loại mọi lần xuất hiện.
5. `Integer(1)` không bằng `Long(1)` theo phép `equals` của các lớp bao tương ứng.
6. `BigDecimal` cho thấy sự khác biệt giữa `equals` và thứ tự tự nhiên khi tìm trong tập cây.
7. Một ánh xạ có giá trị `null` vẫn làm map không rỗng.
8. Sau khi xóa hết phần tử, `size()` và `isEmpty()` phản ánh trạng thái rỗng.

Chương trình không in thứ tự phần tử của `HashSet`, nên kết quả không phụ thuộc thứ tự duyệt mà lớp đó không bảo đảm.

## 9. Lỗi thường gặp và cách kiểm tra

| Hiểu nhầm | Điều thực tế cần nhớ |
| --- | --- |
| `new ArrayList<>(100)` có kích thước 100 | Chỉ chuẩn bị dung lượng; kích thước ban đầu là 0 |
| `isEmpty()` kiểm tra được biến có `null` không | Gọi phương thức trên tham chiếu `null` gây lỗi |
| Có một phần tử `null` thì danh sách rỗng | Nó vẫn có một phần tử |
| `contains` trả số lần xuất hiện hoặc vị trí | Nó chỉ trả thông tin có/không |
| Hai đối tượng khác tham chiếu không thể được tìm thấy bằng `contains` | Quy tắc bình đẳng giá trị có thể coi chúng bằng nhau |
| `contains(1L)` phải tìm được số `Integer` 1 | Kiểu số bao và quy tắc `equals` vẫn có ý nghĩa |
| Mọi collection xử lý `contains(null)` giống nhau | Phải kiểm tra chính sách của lớp |
| `contains` luôn duyệt toàn bộ và gọi `equals` | Cấu trúc có thể dùng băm hoặc thứ tự so sánh |
| Một kết quả `false` chứng minh không ai thêm phần tử ngay sau đó | Truy vấn không khóa trạng thái cho những thao tác tiếp theo |
| `size()` của mọi collection là O(1) | Một số cấu trúc phải duyệt để đếm |

Khi một phép truy vấn cho kết quả bất ngờ, kiểm tra lần lượt: collection thực sự đang chứa gì, kiểu của đối tượng truy vấn, quy tắc `equals`/`hashCode` hoặc comparator, chính sách `null`, rồi mới xét việc có luồng khác đang sửa dữ liệu hay không.

## 10. Tự luyện

1. Một `ArrayList<String>` chứa `"A"`, `"A"`, `null`. `size()`, `isEmpty()` và `contains("A")` trả gì?  
   **Đáp án:** 3, `false`, `true`.

2. Xóa đúng một lần xuất hiện của `"A"` khỏi danh sách đó. `contains("A")` còn đúng không?  
   **Đáp án:** còn, vì vẫn có một phần tử `"A"`.

3. Một `HashMap<String, String>` có khóa `"x"` ánh xạ đến `null`. Map có rỗng không?  
   **Đáp án:** không. Map có một ánh xạ; `containsKey("x")` là `true`.

4. Vì sao `List.of(1, 2).contains(1L)` trả `false`?  
   **Đáp án:** phần tử là `Integer`, còn truy vấn là `Long`; cùng giá trị số không làm chúng bằng nhau theo `equals`.

5. Vì sao không nên dùng `queue.size() < limit` rồi `offer` để bảo đảm sức chứa trong hệ thống nhiều luồng?  
   **Đáp án:** việc kiểm tra và thêm là hai thao tác tách biệt; trạng thái có thể đổi giữa chúng. Cần cấu trúc hoặc cơ chế đáp ứng giới hạn một cách nguyên tử.

Ba phương thức này giúp diễn đạt ba ý định riêng: đếm, kiểm tra rỗng và kiểm tra thành viên. Mỗi lần dùng, hãy xác định chính xác câu hỏi cần trả lời và phạm vi mà kết quả còn có ý nghĩa.
