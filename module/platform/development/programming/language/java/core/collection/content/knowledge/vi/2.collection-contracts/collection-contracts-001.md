# Khai báo theo giao diện và lựa chọn lớp cài đặt

## 1. Hai quyết định trong một dòng khai báo

Khi cần quản lý nhiều phần tử, ta phải trả lời hai câu hỏi khác nhau:

1. **Cấu trúc này cần cung cấp khả năng gì?** Danh sách có vị trí, tập không trùng, hàng đợi hay ánh xạ khóa–giá trị?
2. **Đối tượng nào sẽ thực hiện các khả năng đó?** Dùng mảng động, bảng băm, cây có thứ tự hay cấu trúc hai đầu?

Trong Java Collections Framework, giao diện (interface) giúp diễn đạt câu thứ nhất; lớp cài đặt (implementation class) là một phần quan trọng của câu thứ hai.

```java
List<String> names = new ArrayList<>();
```

Đọc dòng này theo ba phần:

- `List<String>`: biến `names` được khai báo là một danh sách các `String`.
- `new ArrayList<>()`: tạo đối tượng có lớp thực tế là `ArrayList`.
- `=`: lưu tham chiếu tới đối tượng đó vào biến; không tạo thêm một đối tượng `List`.

`List` là giao diện nên không thể viết `new List<>()`. Đối tượng vẫn là `ArrayList` sau khi gán vào biến kiểu `List`.

Mục tiêu của cách khai báo này là để phần mã sử dụng phụ thuộc vào **hợp đồng cần thiết**, đồng thời giữ việc chọn cách lưu trữ tại nơi khởi tạo. Nó giúp thay đổi có kiểm soát; không làm mọi lớp cài đặt trở nên tương đương.

Các ví dụ sử dụng API có trong Java 17. Trước khi thực hành, cần biết biến tham chiếu, phương thức, generics cơ bản và vòng lặp `for-each`.

## 2. Kiểu khai báo và lớp thực tế có vai trò gì?

### 2.1. Kiểu khai báo quyết định API có thể gọi trực tiếp

Hai biến sau cùng trỏ tới một đối tượng:

```java
// Đoạn minh họa đặt trong một phương thức; cần import java.util.*.
ArrayList<String> storage = new ArrayList<>();
List<String> names = storage;

names.add("Lan");
storage.ensureCapacity(100);

System.out.println(names.size()); // 1
```

`add` thuộc hợp đồng `List` nên có thể gọi qua `names`. `ensureCapacity` là thao tác riêng của `ArrayList`, không nằm trong API `List` của Java 17. Vì vậy, `names.ensureCapacity(100)` không biên dịch, dù đối tượng thực tế là `ArrayList`.

Hai tham chiếu dùng chung đối tượng. Thay đổi thông qua một tham chiếu có thể được quan sát qua tham chiếu còn lại. Khai báo theo giao diện không sao chép dữ liệu và không tạo một lớp bọc.

Kiểu tham chiếu và giá trị đối tượng mà biến có thể giữ được quy định trong [JLS: Reference Types and Values](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.3.1) và [Variables of Reference Type](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.12.2).

### 2.2. Đối tượng thực tế cung cấp phần cài đặt khi chạy

```java
// Đoạn minh họa đặt trong một phương thức; cần import java.util.*.
List<String> tasks = new ArrayList<>();
tasks.add("code");

tasks = new LinkedList<>(tasks);
tasks.add("test");
```

Ban đầu `tasks` tham chiếu một `ArrayList`. Sau phép gán thứ hai, nó tham chiếu một `LinkedList` mới, được khởi tạo từ các phần tử của danh sách cũ.

Các lời gọi phương thức thể hiện thông thường như `tasks.add(...)` được phân phối tới phần cài đặt thích hợp của đối tượng khi chạy. Chữ ký có thể gọi vẫn phải hợp lệ với kiểu khai báo tại thời điểm biên dịch. Đây là mối liên hệ giữa đa hình (polymorphism), giao diện và lớp cài đặt; xem [JLS: Method Invocation Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.12).

Lưu ý: phép gán trong ví dụ **tạo bản sao cấu trúc mới**, không biến đối tượng `ArrayList` cũ thành `LinkedList`. Nếu có biến khác giữ danh sách cũ, biến đó tiếp tục nhìn thấy danh sách cũ. Các phần tử vẫn là những tham chiếu được sao chép, không được nhân bản sâu.

## 3. Chọn giao diện theo ý nghĩa dữ liệu

Không phải cứ chọn giao diện ở cao nhất trong cây kế thừa là tốt. Hãy chọn giao diện đủ diễn đạt các thao tác và ý nghĩa mà phần mã đang cần.

| Nhu cầu | Giao diện phù hợp | Điều cần diễn đạt |
| --- | --- | --- |
| Chỉ cần duyệt từng phần tử | `Iterable<E>` | Không đòi hỏi chỉ số hay kiểm tra kích thước |
| Cần nhóm phần tử và thao tác chung như `size`, `contains` | `Collection<E>` | Chưa cam kết danh sách hay tập |
| Cần vị trí, chỉ số và có thể giữ phần tử trùng | `List<E>` | Thứ tự của chuỗi phần tử |
| Cần tính không trùng | `Set<E>` | Tập hợp theo quy tắc bằng nhau |
| Cần tập được sắp xếp | `SortedSet<E>` | Thứ tự tự nhiên hoặc `Comparator` |
| Cần tìm phần tử gần một mốc, như `ceiling` hoặc `floor` | `NavigableSet<E>` | Khả năng điều hướng trên tập có thứ tự |
| Cần đưa vào/lấy ra theo chính sách hàng đợi | `Queue<E>` | Thao tác trên đầu hàng đợi |
| Cần thao tác cả hai đầu, FIFO hoặc LIFO | `Deque<E>` | Ý định sử dụng hai đầu |
| Cần tra giá trị theo khóa | `Map<K, V>` | Mỗi khóa ánh xạ tối đa một giá trị |
| Cần ánh xạ được sắp theo khóa | `SortedMap<K, V>` | Thứ tự của khóa |
| Cần điều hướng theo khóa | `NavigableMap<K, V>` | Ví dụ tìm khóa nhỏ nhất không dưới một mốc |

`Map` thuộc Collections Framework nhưng **không kế thừa `Collection`**. Nó quản lý ánh xạ, thay vì chỉ một nhóm phần tử. Các view như `keySet()`, `values()` và `entrySet()` mới cung cấp cách nhìn dạng collection. Xem [Map API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html).

Ví dụ, nếu thuật toán gọi `get(i)` thì tham số `Collection<String>` không đủ. Ngược lại, một phương thức chỉ duyệt và tính tổng không nhất thiết phải yêu cầu `ArrayList<String>`.

```java
// Đoạn minh họa phương thức; cần import java.util.Collection.
static int totalLength(Collection<String> values) {
    int total = 0;
    for (String value : values) {
        total += value.length();
    }
    return total;
}
```

Hợp đồng bổ sung của phương thức này là `values` và từng phần tử đều khác `null`. Kiểu `Collection<String>` tự nó chưa diễn đạt điều kiện đó.

Cách phân nhóm và các thao tác chung được mô tả trong [Collection API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collection.html). Ngữ nghĩa chuỗi có vị trí được mô tả trong [List API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html); tính không trùng được mô tả trong [Set API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Set.html).

## 4. Chọn lớp cài đặt theo yêu cầu cụ thể

Sau khi chọn giao diện, xét hành vi cần thiết rồi mới cân nhắc chi phí.

| Nhu cầu điển hình | Khai báo minh họa | Điểm cần lưu ý |
| --- | --- | --- |
| Danh sách có chỉ số, đọc và thêm cuối thường xuyên | `List<String> x = new ArrayList<>();` | Mảng động; phù hợp nhiều trường hợp danh sách thông thường |
| Có lý do cần cấu trúc danh sách liên kết | `List<String> x = new LinkedList<>();` | Truy cập theo chỉ số phải duyệt liên kết |
| Kiểm tra thuộc tập, không cần cam kết thứ tự duyệt | `Set<String> x = new HashSet<>();` | Phụ thuộc `equals`/`hashCode` |
| Loại trùng và giữ thứ tự thêm | `Set<String> x = new LinkedHashSet<>();` | Không phải sắp xếp theo giá trị |
| Tập có thứ tự và cần tìm quanh một mốc | `NavigableSet<Integer> x = new TreeSet<>();` | Dựa vào thứ tự tự nhiên hoặc `Comparator` |
| FIFO một luồng | `Queue<String> x = new ArrayDeque<>();` | `offer` vào cuối, `poll` từ đầu trong cách sử dụng này |
| Ngăn xếp hoặc thao tác hai đầu một luồng | `Deque<String> x = new ArrayDeque<>();` | Dùng `push/pop` cho LIFO hoặc API hai đầu |
| Lấy phần tử ưu tiên trước | `Queue<Integer> x = new PriorityQueue<>();` | Đầu hàng đợi theo độ ưu tiên, không phải thứ tự thêm |
| Tra cứu theo khóa, không yêu cầu thứ tự duyệt | `Map<String, Integer> x = new HashMap<>();` | Không cam kết thứ tự khóa |
| Ánh xạ giữ thứ tự thêm theo cấu hình mặc định | `Map<String, Integer> x = new LinkedHashMap<>();` | Lớp còn có cấu hình access-order riêng |
| Ánh xạ theo thứ tự khóa và có điều hướng | `NavigableMap<Integer, String> x = new TreeMap<>();` | Thứ tự khóa phụ thuộc phép so sánh |

Đây là bảng chọn ban đầu, không thay thế việc đọc hợp đồng của API đang dùng.

- `HashSet` không cam kết thứ tự duyệt. “Không cam kết” không có nghĩa là mỗi lần duyệt đều ngẫu nhiên. Việc một lần chạy trông có vẻ đã sắp xếp không tạo thành bảo đảm. [HashSet API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashSet.html)
- `LinkedHashSet` giữ thứ tự chèn; thêm lại phần tử đã có không đưa nó tới cuối. [LinkedHashSet API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedHashSet.html)
- `TreeSet` dùng phép so sánh để xác định vị trí và coi hai phần tử có kết quả so sánh bằng `0` là cùng một phần tử theo cấu trúc cây. Phép so sánh cần nhất quán với `equals` để đáp ứng hợp đồng chung của `Set`. [TreeSet API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeSet.html)
- `PriorityQueue` không bảo đảm iterator duyệt theo thứ tự ưu tiên. Khi muốn lấy theo ưu tiên, dùng thao tác lấy đầu hàng đợi theo hợp đồng. [PriorityQueue API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/PriorityQueue.html)
- `ArrayDeque` không nhận `null` và không tự đồng bộ hóa cho truy cập nhiều luồng. [ArrayDeque API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayDeque.html)

Với `HashMap`, `LinkedHashMap` và `TreeMap`, tham khảo lần lượt [tra cứu theo bảng băm](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashMap.html), [thứ tự chèn hoặc thứ tự truy cập](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedHashMap.html), và [ánh xạ theo cây có thứ tự](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeMap.html).

## 5. Không đổi lớp cài đặt chỉ vì cùng biên dịch

Xét yêu cầu: “loại mã bị trùng nhưng giữ thứ tự xuất hiện đầu tiên”.

```java
// Đoạn minh họa đặt trong một phương thức; cần import java.util.*.
Set<String> codes =
        new LinkedHashSet<>(List.of("B", "A", "B"));
System.out.println(codes); // [B, A]
```

Đổi `LinkedHashSet` thành `HashSet` vẫn đúng về kiểu, nhưng không còn bảo đảm thứ tự đầu ra. Đổi sang `TreeSet` với thứ tự tự nhiên sẽ tạo `[A, B]` đối với dữ liệu này, khác yêu cầu giữ thứ tự xuất hiện.

Vì vậy, khả năng thay thế cần được đánh giá theo ít nhất các chiều sau:

| Chiều kiểm tra | Câu hỏi trước khi thay |
| --- | --- |
| Phần tử trùng | Nghiệp vụ có cần giữ các lần xuất hiện không? |
| Thứ tự | Theo vị trí, theo lần thêm, theo phép so sánh hay không yêu cầu? |
| `null` | Có được thêm khóa, giá trị hoặc phần tử `null` không? |
| Sửa dữ liệu | Có cần `add`, `remove`, `set` hay cập nhật entry không? |
| Đồng thời | Có nhiều luồng cùng truy cập và sửa không? |
| Quan hệ bằng nhau | Dựa trên `equals/hashCode` hay comparator? |
| Chi phí | Thuật toán chủ yếu duyệt, tra cứu, thêm cuối hay truy cập ngẫu nhiên? |
| Sở hữu dữ liệu | Đây là dữ liệu riêng, bản sao hay view của dữ liệu khác? |

Viết `Set<String>` không truyền đạt đầy đủ yêu cầu giữ thứ tự chèn. Nếu thứ tự đó là một phần API, cần ghi rõ trong tài liệu và kiểm thử bằng kết quả có thể quan sát. Đừng dựa vào việc người đọc nhìn thấy `new LinkedHashSet<>()` ở một nơi xa.

## 6. Hợp đồng giao diện không bảo đảm mọi thao tác đều thành công

### 6.1. Có phương thức không có nghĩa đối tượng cho sửa

```java
// Đoạn minh họa đặt trong một phương thức; cần import java.util.List.
List<String> fixed = List.of("A", "B");
// fixed.add("C"); // Biên dịch được, nhưng khi chạy sẽ ném UnsupportedOperationException.
```

`List.of` tạo danh sách không cho sửa qua các thao tác thay đổi của `List` và không nhận phần tử `null`. `List<String>` không phải kiểu “chỉ đọc”: API vẫn có `add`. Giới hạn đến từ đối tượng được trả về. Không dựa vào tên lớp nội bộ của kết quả `List.of`.

Ba trường hợp dễ nhầm:

| Cách tạo | Thêm/xóa phần tử | Thay phần tử bằng `set` | Quan hệ với nguồn |
| --- | --- | --- | --- |
| `new ArrayList<>(source)` | Được | Được | Bản sao nông của các phần tử |
| `Arrays.asList(array)` | Không thay kích thước | Được | View được chống lưng bởi mảng |
| `Collections.unmodifiableList(source)` | Không cho sửa qua view | Không | Thay đổi ở nguồn có thể xuất hiện qua view |
| `List.copyOf(source)` | Không | Không | Không phản ánh thay đổi cấu trúc của collection nguồn |

`List.copyOf` không nhất thiết tạo đối tượng mới nếu nguồn đã phù hợp; không dùng nó để yêu cầu một danh tính đối tượng khác. Các bản sao trên không tự nhân bản sâu các phần tử. Một phần tử có trạng thái thay đổi vẫn có thể bị sửa thông qua tham chiếu khác.

Xem hợp đồng [List factories và copyOf](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection)), [Arrays.asList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Arrays.html#asList(T...)) và [Collections.unmodifiableList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#unmodifiableList(java.util.List)).

### 6.2. Khai báo theo giao diện không tạo an toàn nhiều luồng

`List<String> x = new ArrayList<>();` không an toàn hơn về đồng thời so với khai báo biến bằng `ArrayList<String>`. Nếu nhiều luồng cùng sửa, phải chọn cơ chế đồng bộ hoặc cấu trúc concurrent phù hợp với toàn bộ chuỗi thao tác.

Ngay cả khi từng thao tác được bảo vệ, chuỗi “kiểm tra rồi cập nhật” vẫn có thể cần một bảo đảm nguyên tử riêng. Bài này không thay thế việc thiết kế đồng thời.

### 6.3. `final` không làm collection bất biến

```java
// Đoạn minh họa đặt trong một phương thức; cần import java.util.*.
final List<String> names = new ArrayList<>();
names.add("Lan"); // Hợp lệ: sửa đối tượng, không gán lại biến.
// names = new LinkedList<>(); // Không biên dịch: gán lại biến final.
```

Cần tách ba việc: gán lại tham chiếu, thay đổi cấu trúc collection và thay đổi trạng thái phần tử.

## 7. Cân nhắc chi phí mà không phá hợp đồng

`ArrayList` có `get/set` theo chỉ số với chi phí hằng số; thêm cuối có chi phí hằng số phân bổ (amortized), dù một lần thêm cụ thể có thể cần mở rộng mảng. Thêm hoặc xóa giữa danh sách thường cần dịch chuyển phần tử. Xem [ArrayList API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html).

`LinkedList` cần đi qua liên kết khi truy cập theo chỉ số. Chèn/xóa tại vị trí mà iterator đã xác định khác với việc phải tìm vị trí trước. Vì vậy, kết luận “thêm/xóa nhiều thì luôn chọn LinkedList” bỏ qua chi phí tìm vị trí, cấp phát nút và đặc điểm truy cập bộ nhớ. [LinkedList API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedList.html)

Ví dụ thuật toán sau làm lộ giả định rằng truy cập theo chỉ số đủ rẻ:

```java
// Đoạn minh họa phương thức; cần import java.util.List.
static int totalByIndex(List<String> values) {
    int total = 0;
    for (int i = 0; i < values.size(); i++) {
        total += values.get(i).length();
    }
    return total;
}
```

Với `LinkedList`, nhiều lần `get(i)` có thể khiến tổng chi phí duyệt tăng tới bậc hai theo số phần tử. Nếu chỉ cần đi qua từng phần tử, cách `for-each` ở `totalLength` phù hợp hơn và không áp đặt truy cập ngẫu nhiên.

Khi thật sự cần đặc tính hiệu năng, hãy:

1. Xác định số lượng dữ liệu và tần suất thao tác.
2. Chọn cấu trúc đáp ứng đúng hành vi trước.
3. Đo trên dữ liệu và môi trường đại diện nếu đây là điểm nghẽn.
4. Giữ rõ giả định hiệu năng trong thuật toán hoặc hợp đồng.

Giao diện làm giảm phụ thuộc vào tên lớp; nó không xóa khác biệt về độ phức tạp.

## 8. Áp dụng ở tham số, giá trị trả về và trường dữ liệu

### 8.1. Tham số: yêu cầu đúng năng lực cần dùng

Nếu chỉ duyệt, nhận `Iterable<String>` là một lựa chọn. Nếu cần `size` hoặc `contains`, `Collection<String>` có thể phù hợp. Nếu cần vị trí, nhận `List<String>`. Nếu cần tính duy nhất, `Set<String>` diễn đạt ý định rõ hơn.

Nếu phương thức sửa collection của người gọi, phải nói rõ điều đó:

```java
// Đoạn minh họa phương thức; cần import java.util.List.
// Yêu cầu danh sách hỗ trợ add; phương thức sửa trực tiếp đối số.
static void appendReviewTask(List<String> tasks) {
    tasks.add("review");
}
```

Nhận `List` không có nghĩa là phương thức có thể an toàn gọi `add` trên mọi đối tượng `List`. Đối số `List.of(...)` không đáp ứng tiền điều kiện “hỗ trợ thêm phần tử”.

### 8.2. Trả về: cam kết hành vi mà người gọi cần

```java
// Đoạn minh họa phương thức; cần import java.util.*.
// Trả danh sách mới, sửa được; không sửa collection nguồn.
static List<String> copyTasks(Collection<String> source) {
    return new ArrayList<>(source);
}
```

`List` giữ thông tin về chuỗi và vị trí, trong khi `ArrayList` được giữ như quyết định cài đặt. Cần tài liệu hóa rằng kết quả sửa được và là bản sao nông.

Nếu API cần kết quả không cho sửa, có thể chọn `List.copyOf(source)`, đồng thời nêu giới hạn `null`. Nếu muốn trả view sống cùng dữ liệu nguồn, đó lại là hợp đồng khác và cần nói rõ.

Không trả trực tiếp collection nội bộ chỉ vì kiểu trả về là giao diện. Người gọi vẫn có thể gọi các thao tác sửa mà đối tượng hỗ trợ.

### 8.3. Trường dữ liệu: giữ ý định ổn định

```java
// Đoạn minh họa khai báo trường trong một lớp; cần import java.util.*.
private final Map<String, Integer> counts = new HashMap<>();
```

Ở đây lớp sở hữu ánh xạ và giữ quyết định chọn `HashMap` bên trong. Khi thay lớp cài đặt, vẫn phải kiểm tra thứ tự duyệt, `null`, tính đồng thời và những hành vi mà phần còn lại của lớp đang dựa vào.

## 9. Khi nào nên dùng kiểu lớp cụ thể?

Khai báo bằng lớp cụ thể hợp lý khi mã thật sự cần khả năng riêng của lớp đó.

```java
// Đoạn minh họa đặt trong một phương thức; cần import java.util.ArrayList.
ArrayList<String> buffer = new ArrayList<>();
buffer.ensureCapacity(1_000);
buffer.add("A");
```

Có thể giới hạn phụ thuộc này trong bước xây dựng, rồi chuyển tham chiếu cho mã chỉ cần giao diện:

```java
// Đoạn minh họa đặt trong một phương thức; cần import java.util.*.
ArrayList<String> buffer = new ArrayList<>();
buffer.ensureCapacity(1_000);
List<String> result = buffer;
```

Ngược lại, không cần ép về lớp chỉ để lấy một API đã có ở giao diện thích hợp. Nếu cần `ceiling`, khai báo `NavigableSet`; nếu cần `addFirst` trên Java 17, xem liệu ý định đúng có phải `Deque`.

Tránh lấy `List` rồi ép mù về `ArrayList`. Phương thức có thể nhận một `LinkedList` hoặc một danh sách không cho sửa, khiến phép ép thất bại với `ClassCastException`. Việc phải liên tục ép kiểu thường là dấu hiệu giao diện đang chọn chưa diễn đạt đúng nhu cầu.

### `var` vẫn suy luận ra một kiểu cụ thể

```java
// Đoạn minh họa đặt trong một phương thức; cần import java.util.*.
var first = new ArrayList<String>(); // Kiểu suy luận là ArrayList<String>.
List<String> second = new ArrayList<>();
```

`var` không tự nâng kiểu suy luận thành `List`. Nó là suy luận kiểu tĩnh cho biến cục bộ, không biến Java thành ngôn ngữ có kiểu động. Khi mục tiêu là thể hiện ranh giới `List` ngay ở dòng khai báo, viết tường minh giúp truyền đạt điều đó. [Local Variable Type Inference](https://docs.oracle.com/en/java/javase/17/language/local-variable-type-inference.html)

Generics cũng phải tương thích: `List<String>` không phải kiểu con của `List<Object>`. Dấu `<>` ở vế tạo đối tượng là cơ chế suy luận đối số kiểu, không bỏ kiểm tra kiểu. Chủ đề wildcard có thể giúp thiết kế tham số linh hoạt hơn, nhưng không cần dùng raw type để giải quyết vấn đề này.

## 10. Chương trình hoàn chỉnh

Lưu đúng tên `CollectionChoiceDemo.java`. Chương trình dùng các phần tử khác `null` và không có xử lý đồng thời.

```java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Collection;
import java.util.Deque;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.LinkedList;
import java.util.List;
import java.util.Map;
import java.util.NavigableSet;
import java.util.Queue;
import java.util.Set;
import java.util.TreeSet;

public final class CollectionChoiceDemo {
    static void appendReviewTask(List<String> tasks) {
        tasks.add("review");
    }

    static int totalLength(Collection<String> values) {
        int total = 0;
        for (String value : values) {
            total += value.length();
        }
        return total;
    }

    static List<String> copyTasks(Collection<String> source) {
        return new ArrayList<>(source);
    }

    public static void main(String[] args) {
        List<String> arrayTasks =
                new ArrayList<>(List.of("code", "test"));
        List<String> linkedTasks =
                new LinkedList<>(List.of("code", "test"));

        appendReviewTask(arrayTasks);
        appendReviewTask(linkedTasks);
        System.out.println("ArrayList: " + arrayTasks);
        System.out.println("LinkedList: " + linkedTasks);
        System.out.println("Total length: " + totalLength(arrayTasks));

        Set<String> uniqueInOrder =
                new LinkedHashSet<>(List.of("b", "a", "b"));
        System.out.println("Unique in order: " + uniqueInOrder);

        NavigableSet<Integer> scores =
                new TreeSet<>(List.of(30, 10, 20));
        System.out.println("Sorted: " + scores);
        System.out.println("At least 15: " + scores.ceiling(15));

        Queue<String> jobs = new ArrayDeque<>();
        jobs.offer("first");
        jobs.offer("second");
        System.out.println("Queue: " + jobs.poll() + ", " + jobs.poll());

        Deque<String> history = new ArrayDeque<>();
        history.push("open");
        history.push("edit");
        System.out.println("Stack: " + history.pop() + ", " + history.pop());

        Map<String, Integer> counts = new LinkedHashMap<>();
        counts.put("code", 1);
        counts.put("test", 2);
        counts.put("code", 3);
        System.out.println("Counts: " + counts);

        List<String> snapshot = List.copyOf(arrayTasks);
        arrayTasks.add("deploy");
        System.out.println("Snapshot: " + snapshot);
        System.out.println("Original: " + arrayTasks);
        try {
            snapshot.add("extra");
        } catch (UnsupportedOperationException ex) {
            System.out.println("Snapshot add: unsupported");
        }

        List<String> editableCopy = copyTasks(snapshot);
        editableCopy.add("extra");
        System.out.println("Editable copy: " + editableCopy);
    }
}
```

Biên dịch và chạy từ thư mục chứa tệp:

```shell
javac --release 17 -encoding UTF-8 CollectionChoiceDemo.java
java CollectionChoiceDemo
```

Cần JDK có `javac`; `--release 17` yêu cầu trình biên dịch kiểm tra mã và API theo nền Java 17. Chương trình đã được kiểm tra bằng lệnh này trên một JDK mới hơn.

Stdout:

```text
ArrayList: [code, test, review]
LinkedList: [code, test, review]
Total length: 14
Unique in order: [b, a]
Sorted: [10, 20, 30]
At least 15: 20
Queue: first, second
Stack: edit, open
Counts: {code=3, test=2}
Snapshot: [code, test, review]
Original: [code, test, review, deploy]
Snapshot add: unsupported
Editable copy: [code, test, review, extra]
```

Các kết quả cần giải thích được:

- `appendReviewTask` làm việc với hai lớp cùng đáp ứng yêu cầu danh sách sửa được; nó không cần nhận `ArrayList`.
- Tổng độ dài là `4 + 4 + 6 = 14`.
- `LinkedHashSet` giữ lần xuất hiện đầu tiên của `b` rồi `a`, loại lần `b` bị trùng.
- `TreeSet` sắp `10, 20, 30`; `ceiling(15)` trả `20`.
- `ArrayDeque` được nhìn qua `Queue` để dùng FIFO; cũng lớp đó được nhìn qua `Deque` để dùng LIFO.
- `LinkedHashMap` ở chế độ mặc định giữ thứ tự chèn khóa. Cập nhật `code` thành `3` không tạo khóa thứ hai và không chuyển khóa đó xuống cuối.
- `snapshot` không nhận phần tử `deploy` thêm sau vào danh sách nguồn; gọi `add` trên nó bị từ chối.
- `copyTasks` tạo danh sách mới sửa được, nên `editableCopy` thêm được `extra`.

Không có output nào dựa vào thứ tự duyệt không được cam kết của `HashSet` hay `HashMap`.

## 11. Lỗi thường gặp và cách sửa

| Cách làm | Vì sao có vấn đề | Cách xử lý |
| --- | --- | --- |
| Dùng `ArrayList` ở mọi tham số | Ép người gọi dùng một lớp dù thuật toán không cần | Chọn `List`, `Collection` hoặc `Iterable` theo yêu cầu |
| Dùng `Collection` cho cả chỗ cần `get(index)` | Làm mất API cần thiết | Dùng `List` nếu vị trí là một phần hợp đồng |
| Đổi `LinkedHashSet` sang `HashSet` vì cùng là `Set` | Làm mất bảo đảm thứ tự | Kiểm tra yêu cầu quan sát được trước khi thay |
| Coi mọi `Queue` đều FIFO | `PriorityQueue` dùng chính sách khác | Chọn và ghi rõ chính sách của lớp cài đặt |
| Gọi `add` trên kết quả `List.of` | Thao tác thay đổi không được hỗ trợ | Tạo bản sao sửa được nếu cần cập nhật |
| Dùng `final` để bảo đảm dữ liệu bất biến | Chỉ ngăn gán lại biến | Thiết kế quyền sửa collection và phần tử riêng |
| Ép mọi `List` về `ArrayList` | Đối tượng thực tế có thể là lớp khác | Dùng API giao diện hoặc thể hiện yêu cầu cụ thể |
| Chọn `LinkedList` chỉ vì “xóa nhanh” | Chưa tính chi phí tìm vị trí và thuật toán | Xem toàn bộ mẫu thao tác và đo khi cần |
| Trả collection nội bộ bằng kiểu `List` rồi coi là an toàn | Người gọi vẫn có thể sửa đối tượng | Chọn copy/view và tài liệu hóa quyền sở hữu |
| Cho rằng khai báo bằng interface tạo thread safety | Kiểu tham chiếu không cung cấp đồng bộ | Chọn chính sách đồng thời phù hợp |

## 12. Quy trình lựa chọn để áp dụng vào bài toán mới

1. **Viết yêu cầu dữ liệu:** có trùng không, cần thứ tự nào, có tra theo khóa không?
2. **Liệt kê thao tác:** duyệt, truy cập chỉ số, tìm thành viên, lấy hai đầu, tìm quanh mốc?
3. **Chọn giao diện:** đủ thao tác và đủ ý nghĩa, không kéo theo lớp cụ thể nếu không cần.
4. **Chọn lớp cài đặt:** xét cấu trúc lưu trữ, thứ tự, `null` và giới hạn của từng lớp.
5. **Xác định quyền sửa và sở hữu:** sửa nguồn, tạo bản sao hay trả view?
6. **Xét đồng thời và chi phí:** dựa trên cách dùng thực tế.
7. **Kiểm thử hợp đồng:** bảo đảm đầu ra, thứ tự và ngoại lệ vẫn đúng nếu thay lớp.

Ví dụ: “lưu mã sản phẩm duy nhất theo thứ tự nhập” dẫn tới `Set` ở ranh giới sử dụng, `LinkedHashSet` khi tạo đối tượng, cùng tài liệu và kiểm thử cho thứ tự nhập. “Tìm mức giá nhỏ nhất không thấp hơn ngân sách” dẫn tới `NavigableSet` và một cài đặt có thứ tự như `TreeSet`.

## 13. Tự kiểm tra và thực hành

### Câu hỏi

1. Với `List<String> x = new ArrayList<>();`, kiểu khai báo và lớp thực tế là gì?
2. Vì sao `x.ensureCapacity(100)` không biên dịch trên Java 17?
3. Một hàm chỉ tính tổng độ dài chuỗi có cần nhận `ArrayList<String>` không?
4. Thay `LinkedHashSet` bằng `TreeSet` có giữ thứ tự nhập không?
5. Vì sao `List<String> x = List.of("A");` vẫn không cho `add`?
6. Vì sao `final List<String>` vẫn có thể thay đổi nội dung?
7. Đổi `ArrayList` sang `LinkedList` có bảo đảm một thuật toán theo chỉ số giữ nguyên hiệu năng không?
8. API trả `List` cần nói thêm điều gì về quyền sửa và quan hệ với nguồn?

### Bài tập

- Thay `arrayTasks` trong chương trình bằng `LinkedList` mà không sửa `appendReviewTask`. Giải thích phần hành vi nào vẫn giữ.
- Dùng cùng dữ liệu `"B", "A", "B"` để tạo `HashSet`, `LinkedHashSet` và `TreeSet`. Chỉ khẳng định thứ tự trong những trường hợp có hợp đồng bảo đảm.
- Viết hàm trả danh sách mã không trùng theo thứ tự đầu tiên. Chọn kiểu trả về để biểu đạt kết quả có vị trí, tài liệu hóa tính duy nhất và quyền sửa.
- Sửa `copyTasks` thành trả kết quả không cho sửa bằng `List.copyOf`; đổi tên và tài liệu phương thức cho đúng hợp đồng mới.
- Viết kiểm tra rằng thêm vào bản sao sửa được không làm thay đổi cấu trúc collection nguồn.

### Gợi ý đối chiếu

1. `List<String>` là kiểu khai báo, `ArrayList` là lớp thực tế.
2. `ensureCapacity` không thuộc API `List` của nền Java 17.
3. Không; `Collection<String>` hoặc `Iterable<String>` có thể đủ tùy thao tác và hợp đồng.
4. Không; `TreeSet` sắp theo phép so sánh, không theo lần nhập.
5. Đối tượng không hỗ trợ thao tác sửa, dù chữ ký tồn tại trên giao diện.
6. `final` chỉ cố định tham chiếu.
7. Không; nhiều lần truy cập chỉ số có thể làm thay đổi đáng kể chi phí.
8. Có cho sửa không, có phải bản sao/view không, thay đổi nguồn có phản ánh vào kết quả không, và có giới hạn phần tử nào cần biết không.
