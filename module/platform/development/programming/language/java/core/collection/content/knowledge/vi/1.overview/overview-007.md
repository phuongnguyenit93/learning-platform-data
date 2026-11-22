# Các tiêu chí chọn cấu trúc: trùng lặp, null, truy cập và đồng thời

Chọn collection là chọn **quy tắc dữ liệu và cách chương trình làm việc với dữ liệu**. Hai lớp cùng có phương thức `add` hoặc `get` có thể khác hẳn nhau về việc giữ phần tử trùng, chấp nhận `null`, thứ tự duyệt và tính an toàn khi nhiều luồng cùng truy cập.

Ví dụ, ba yêu cầu sau đều nói đến “danh sách mã đơn hàng” nhưng cần ba cách nhìn khác nhau:

- Nhật ký ghi nhận mỗi lần đơn hàng được xử lý cần giữ cả những lần lặp.
- Tập mã đơn hàng đã xử lý cần nhận biết mã đã có mà không lưu lặp.
- Bảng tra cứu trạng thái cần tìm một đơn hàng bằng mã, nên quan hệ khóa–giá trị mới là trọng tâm.

Bài này thuộc phần tổng quan Java Collections Framework, sử dụng API có trong Java 17. Mục tiêu là biết đặt câu hỏi đúng trước khi chọn `ArrayList`, `HashSet`, `HashMap`, `ArrayDeque` hoặc một cấu trúc đồng thời.

## 1. Bắt đầu bằng hợp đồng dữ liệu

Trước khi xét tốc độ, hãy viết ngắn gọn yêu cầu theo bốn trục:

| Trục quyết định | Câu hỏi cần trả lời | Hệ quả khi chọn sai |
| --- | --- | --- |
| Trùng lặp | Hai phần tử hoặc hai khóa như thế nào được xem là cùng một giá trị? Có giữ mọi lần xuất hiện không? | Mất dữ liệu hoặc giữ dữ liệu đáng lẽ phải loại trùng |
| `null` | `null` có ý nghĩa hợp lệ không? Có cần phân biệt “không có” với “có nhưng chưa biết giá trị” không? | Ngoại lệ khi chạy hoặc diễn giải sai trạng thái |
| Truy cập | Thường lấy theo chỉ số, theo khóa, kiểm tra tồn tại, lấy đầu/cuối hay truy vấn theo thứ tự? | Phải tìm kiếm hoặc dịch chuyển dữ liệu nhiều lần |
| Đồng thời | Ai được đọc, ai được ghi, và những bước nào phải diễn ra nguyên tử? | Mất cập nhật, đọc trạng thái không nhất quán hoặc lỗi duyệt |

Sau bốn câu hỏi đó, bổ sung thứ tự cần giữ, khả năng sửa đổi, kích thước dự kiến và chi phí bộ nhớ. Đây là các điều kiện giúp chọn lớp cụ thể trong cùng một nhóm.

`Collection` không bảo đảm rằng mọi cách triển khai đều chấp nhận cùng loại phần tử hoặc cùng cơ chế đồng bộ. Một biến khai báo là `Collection<String>` cũng không đủ để suy ra có được thêm `null` hay sửa nội dung hay không. Cần đọc hợp đồng của cách triển khai hoặc phương thức tạo ra đối tượng. [Java 17: Collection](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collection.html)

## 2. Trùng lặp: giữ mọi lần xuất hiện hay chỉ giữ một đại diện?

### 2.1. List, Set và Map giải quyết những nhu cầu khác nhau

| Kiểu dữ liệu cần biểu diễn | Lựa chọn thường gặp | Ý nghĩa của phần tử trùng |
| --- | --- | --- |
| Chuỗi phần tử có vị trí | `List<E>` | Có thể giữ nhiều phần tử bằng nhau |
| Tập các giá trị duy nhất | `Set<E>` | Không thêm một phần tử được xem là đã có |
| Quan hệ tra cứu theo khóa | `Map<K,V>` | Khóa duy nhất; nhiều khóa có thể cùng một giá trị |
| Công việc chờ xử lý theo quy tắc lấy ra | `Queue<E>` hoặc `Deque<E>` | Tùy cách triển khai, thường có thể giữ phần tử trùng |

Ví dụ minh họa trong một phương thức:

```java
List<String> events = new ArrayList<>(List.of("B", "A", "B"));
Set<String> unique = new LinkedHashSet<>(events);

System.out.println(events); // [B, A, B]
System.out.println(unique); // [B, A]
```

`LinkedHashSet` ở đây vừa loại trùng vừa giữ thứ tự chèn. Nếu chỉ cần kiểm tra tồn tại mà không yêu cầu thứ tự duyệt, `HashSet` là một lựa chọn khác. Không dựa vào thứ tự tình cờ quan sát được khi in `HashSet`. [Java 17: LinkedHashSet](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedHashSet.html)

`Map` không kế thừa `Collection`: nó biểu diễn ánh xạ. Khi gọi `put` với một khóa đã có, ánh xạ hiện tại của khóa được thay giá trị, chứ không tạo thêm một khóa giống hệt.

```java
Map<String, Integer> quantities = new HashMap<>();
quantities.put("BOOK", 2);
Integer previous = quantities.put("BOOK", 5);

System.out.println(previous);             // 2
System.out.println(quantities.get("BOOK")); // 5
System.out.println(quantities.size());    // 1
```

Nếu yêu cầu là “mỗi khách hàng có nhiều đơn hàng”, có thể dùng `Map<CustomerId, List<Order>>`; nếu chỉ dùng `Map<CustomerId, Order>`, các lần ghi cùng khóa sẽ thay thế nhau. Cấu trúc phải diễn đạt đúng quan hệ một–nhiều. [Java 17: Map](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html)

### 2.2. Phải định nghĩa “bằng nhau” trước khi loại trùng

Đối với `HashSet` và khóa của `HashMap`, thiết kế `equals` và `hashCode` phải nhất quán:

- Nếu hai đối tượng bằng nhau theo `equals`, chúng phải có cùng `hashCode`.
- Hai đối tượng có cùng mã băm chưa chắc bằng nhau; va chạm mã băm không đồng nghĩa dữ liệu trùng.
- Không thay đổi các trường tham gia tính `equals`/`hashCode` khi đối tượng đang được dùng làm khóa hoặc phần tử trong tập băm.

Chẳng hạn, một đối tượng khách hàng được tìm theo mã khách hàng nhưng sau khi thêm vào `HashSet` lại bị đổi mã có thể không còn được tìm ở vị trí mà cấu trúc đã lưu. Dùng khóa bất biến hoặc tạo một khóa giá trị riêng thường dễ kiểm soát hơn.

`String` và những kiểu giá trị bất biến thích hợp thường giúp giảm rủi ro này. Với lớp tự viết, cần quyết định rõ “cùng mã” hay “mọi trường đều giống nhau” mới là bằng nhau. Một `record` tự sinh phép so sánh theo các thành phần của nó; điều đó chỉ đúng nhu cầu khi chính các thành phần ấy tạo nên danh tính giá trị. [Java 17: HashSet](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashSet.html)

### 2.3. Cây có thứ tự nhận biết trùng bằng phép so sánh

`TreeSet` và khóa của `TreeMap` dùng thứ tự tự nhiên hoặc `Comparator`. Hai phần tử/khóa có kết quả so sánh bằng `0` được xử lý như cùng một vị trí trong cấu trúc.

Giả sử hai sản phẩm có mã khác nhau nhưng cùng tên “Pen”. Nếu comparator chỉ xét tên, `TreeSet` chỉ giữ một phần tử dù `equals` của hai sản phẩm là `false`.

```java
Comparator<Product> byName =
        Comparator.comparing(Product::name);

// Nếu muốn phân biệt sản phẩm cùng tên:
Comparator<Product> byNameThenId =
        Comparator.comparing(Product::name)
                  .thenComparing(Product::id);
```

Đây là đoạn minh họa; kiểu `Product` được định nghĩa trong chương trình hoàn chỉnh ở cuối bài. Chỉ dùng tên để loại trùng nếu “một tên là một giá trị duy nhất” thực sự là yêu cầu. Nếu muốn collection tuân thủ đầy đủ hợp đồng `Set`/`Map` dựa trên `equals`, thứ tự so sánh cần nhất quán với `equals`. Cũng không sửa trường dùng để sắp thứ tự khi đối tượng đang nằm trong cây. [Java 17: TreeSet](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeSet.html), [TreeMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeMap.html)

Một điểm khác: `Set.of("A", "A")` báo `IllegalArgumentException`; phương thức này không âm thầm giữ một bản như cách thêm lặp vào `HashSet`. Không suy diễn hành vi của phương thức tạo từ hành vi của `add`. [Java 17: Set](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Set.html)

## 3. Null: lựa chọn mô hình dữ liệu, không phải chi tiết phụ

### 3.1. Chính sách null phụ thuộc lớp cụ thể

Bảng sau mô tả các lựa chọn phổ biến trong Java 17, không phải quy tắc cho mọi lớp cùng triển khai một interface.

| Cấu trúc hoặc cách tạo | Phần tử / khóa `null` | Giá trị `null` của Map |
| --- | --- | --- |
| `ArrayList`, `LinkedList` | Cho phép phần tử `null` | Không áp dụng |
| `HashSet`, `LinkedHashSet` | Cho phép một phần tử `null` | Không áp dụng |
| `HashMap`, `LinkedHashMap` | Cho phép một khóa `null` | Cho phép |
| `TreeSet` | Thứ tự tự nhiên không cho; comparator có thể hỗ trợ | Không áp dụng |
| `TreeMap` | Thứ tự tự nhiên không cho khóa `null`; comparator có thể hỗ trợ | Cho phép |
| `ArrayDeque`, `PriorityQueue` | Không cho phần tử `null` | Không áp dụng |
| `ConcurrentHashMap` | Không cho khóa `null` | Không cho |
| `CopyOnWriteArrayList` | Cho phép phần tử `null` | Không áp dụng |
| `List.of`, `Set.of`, `Map.of` | Không cho phần tử/khóa `null` | `Map.of` không cho |

Các hợp đồng tương ứng được mô tả tại [ArrayList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html), [LinkedList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedList.html), [HashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashMap.html), [ArrayDeque](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayDeque.html) và [PriorityQueue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/PriorityQueue.html).

Không phải cứ dùng cây là tuyệt đối không được có `null`. Ví dụ minh họa sau đặt quy tắc so sánh `null` rõ ràng:

```java
Set<String> names =
        new TreeSet<>(Comparator.nullsFirst(Comparator.naturalOrder()));
names.add("Lan");
names.add(null);
System.out.println(names); // [null, Lan]
```

Tuy vậy, “có thể hỗ trợ” không đồng nghĩa “nên cho phép”. Nếu `null` không có ý nghĩa nghiệp vụ, hãy chặn từ đầu. Việc đổi lớp sau này cũng dễ hơn khi mô hình dữ liệu không phụ thuộc vào một ngoại lệ riêng của lớp hiện tại.

### 3.2. Get trả null chưa đủ để biết khóa có tồn tại

Trong một `HashMap` cho phép giá trị `null`, hai trạng thái khác nhau có thể cho cùng kết quả:

```java
Map<String, String> notes = new HashMap<>();
notes.put("A", null);

System.out.println(notes.get("A"));         // null: khóa có, giá trị null
System.out.println(notes.get("B"));         // null: không có khóa
System.out.println(notes.containsKey("A")); // true
System.out.println(notes.containsKey("B")); // false
```

Nếu cần phân biệt, dùng `containsKey` hoặc thiết kế một kiểu giá trị diễn đạt trạng thái rõ hơn. `getOrDefault("A", "unknown")` vẫn trả `null` vì khóa `A` thực sự có ánh xạ; giá trị mặc định chỉ dùng khi không có ánh xạ.

Với dữ liệu được sửa đồng thời, hai lệnh `containsKey` rồi `get` cũng không tự tạo một ảnh chụp nguyên tử: dữ liệu có thể đổi giữa hai lệnh. Cần xem xét điều kiện đồng thời riêng, không chỉ giải quyết sự nhập nhằng của `null`.

### 3.3. Queue thường dùng null để báo không có phần tử

`poll()` có thể trả `null` khi hàng đợi rỗng. Nếu cho phép đưa `null` vào dữ liệu, kết quả đó khó phân biệt với một phần tử thật.

`ArrayDeque` không nhận `null`, nên kết quả `poll()` dễ diễn giải hơn. `LinkedList` cho phép `null`, kể cả khi được sử dụng qua `Queue`; khả năng này là một lý do cần tự đặt chính sách dữ liệu chặt hơn.

Đối với `BlockingQueue`, `null` không được chấp nhận. Nếu cần báo kết thúc công việc, dùng một thông điệp kết thúc có kiểu hoặc quy ước riêng; không dùng `null` làm phần tử đánh dấu. [Java 17: BlockingQueue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/BlockingQueue.html)

### 3.4. Chuyển sang bản không sửa được có thể thay đổi điều kiện đầu vào

`List.of` và `List.copyOf` tạo danh sách không sửa được và từ chối `null`. Không thể mặc định rằng một `ArrayList` đang có `null` sẽ luôn chuyển được bằng `List.copyOf`.

Ngược lại, `Collections.unmodifiableList` tạo một lớp nhìn không cho sửa qua chính nó; nếu danh sách gốc thay đổi thì lớp nhìn phản ánh thay đổi. Nó cũng không làm các đối tượng phần tử trở nên bất biến.

Hãy phân biệt ba yêu cầu: không cho sửa qua một tham chiếu, không thay đổi cấu trúc dữ liệu, và không thay đổi trạng thái phần tử. [Java 17: List](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html), [Collection: view và khả năng sửa đổi](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collection.html)

## 4. Truy cập: tối ưu thao tác thật sự diễn ra

### 4.1. Chọn theo đường truy cập chính

| Nhu cầu chính | Lựa chọn khởi đầu | Điều cần kiểm tra thêm |
| --- | --- | --- |
| Lấy theo chỉ số, nối cuối và duyệt tuần tự | `ArrayList` | Có chèn/xóa nhiều ở giữa không? |
| Kiểm tra thành viên, không cần thứ tự | `HashSet` | `equals`/`hashCode` đúng chưa? |
| Loại trùng nhưng giữ thứ tự chèn | `LinkedHashSet` | Có cần sắp theo giá trị thay vì thứ tự chèn không? |
| Tra cứu theo khóa | `HashMap` | Có cần thứ tự hoặc truy vấn khoảng khóa không? |
| Duyệt khóa theo thứ tự, tìm lân cận/khoảng | `TreeMap` | Comparator có phản ánh đúng ý nghĩa khóa không? |
| Tập có thứ tự và tìm lân cận | `TreeSet` | Tiêu chí duy nhất có nhất quán với so sánh không? |
| Thêm/lấy hai đầu; ngăn xếp hoặc hàng đợi thường | `ArrayDeque` | Có nhiều luồng hoặc cần chờ dữ liệu không? |
| Lấy phần tử ưu tiên cao nhất theo quy tắc | `PriorityQueue` | Có thật sự cần duyệt toàn bộ theo thứ tự không? |

Một interface thể hiện mục đích sẽ giúp mã gọi dễ đọc:

```java
List<String> labels = new ArrayList<>();
Set<String> processedIds = new HashSet<>();
Map<String, Integer> countsById = new HashMap<>();
Deque<String> pendingJobs = new ArrayDeque<>();
```

Đây là đoạn khai báo minh họa; cần import các kiểu tương ứng. Khai báo interface không làm mọi lớp thay thế được cho nhau về `null`, thứ tự, hiệu năng hay đồng thời. Khi cần thao tác `floorKey` hoặc `ceilingKey`, `NavigableMap` mới diễn tả đủ khả năng cần dùng.

### 4.2. Hiểu độ phức tạp cùng giả định

Với `n` là số phần tử, các đặc điểm thường dùng để so sánh là:

| Cấu trúc | Thao tác | Đặc điểm chi phí |
| --- | --- | --- |
| `ArrayList` | `get(index)`, `set(index, value)` | Thời gian hằng số |
| `ArrayList` | Thêm cuối | Hằng số khấu hao; một lần mở rộng có thể phải sao chép |
| `ArrayList` | Chèn/xóa ở giữa, tìm theo giá trị | Tuyến tính trong trường hợp tổng quát |
| `LinkedList` | `get(index)` | Phải đi qua các nút, tuyến tính trong trường hợp tổng quát |
| `LinkedList` | Thêm/xóa đầu hoặc cuối | Thời gian hằng số |
| `HashMap`, `HashSet` | Tra cứu, thêm cơ bản | Thường hằng số khi mã băm phân bố tốt |
| `TreeMap`, `TreeSet` | Tra cứu, thêm, xóa cơ bản | Theo logarit của số phần tử |
| `ArrayDeque` | Thêm/lấy hai đầu | Phần lớn thao tác có chi phí hằng số khấu hao |
| `PriorityQueue` | Thêm hoặc lấy đầu ưu tiên | Theo logarit; xem đầu là hằng số |

Các bảo đảm và giới hạn cụ thể nằm trong tài liệu [ArrayList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html), [LinkedList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedList.html), [HashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashMap.html), [TreeMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeMap.html) và [PriorityQueue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/PriorityQueue.html).

“Hằng số khấu hao” mô tả chi phí trung bình theo một chuỗi thao tác, không cam kết từng lần gọi đều tốn thời gian như nhau. Đồng thời, ký hiệu độ phức tạp không tính hết bộ nhớ, chi phí cấp phát, độ cục bộ dữ liệu và nội dung của phép so sánh.

Đừng chọn `LinkedList` chỉ vì nghĩ “chèn giữa nhanh”: trước hết phải tìm đến vị trí. Thêm ngay tại vị trí mà `ListIterator` đã đứng khác với gọi thêm theo chỉ số khi còn phải duyệt đến đó.

Một vòng lặp `for (int i = 0; i < list.size(); i++) list.get(i)` phù hợp khác nhau tùy lớp. Với danh sách liên kết, các lần truy cập theo chỉ số có thể khiến toàn vòng lặp thành bậc hai. Nếu chỉ cần duyệt, dùng vòng `for-each` hoặc iterator.

### 4.3. Thứ tự chèn, thứ tự sắp và thứ tự ưu tiên khác nhau

- `ArrayList` giữ thứ tự vị trí của danh sách.
- `LinkedHashSet` giữ thứ tự chèn.
- `TreeSet` sắp theo thứ tự tự nhiên hoặc comparator.
- `PriorityQueue` bảo đảm phần tử ở đầu theo thứ tự ưu tiên; iterator không bảo đảm duyệt toàn bộ theo thứ tự sắp.

Vì vậy, in `PriorityQueue` không phải bằng chứng rằng cả hàng đợi đã được sắp thành danh sách. Khi cần lấy theo mức ưu tiên, gọi `poll` liên tiếp; việc này đồng thời làm mất phần tử khỏi hàng đợi. Nếu chỉ muốn xuất báo cáo có thứ tự và giữ dữ liệu gốc, cần tạo bản sao hoặc sắp một danh sách riêng.

## 5. Đồng thời: an toàn từng phương thức chưa đủ cho quy trình

### 5.1. Xác định có thật sự chia sẻ dữ liệu không

Một collection chỉ dùng trong một luồng thường không cần cấu trúc đồng thời. Đây là lựa chọn đơn giản khi có thể giữ quyền sở hữu dữ liệu trong một tác vụ.

Nếu nhiều luồng chỉ đọc sau khi dữ liệu đã được tạo hoàn tất, không còn sửa và được công bố an toàn qua cơ chế đồng bộ phù hợp, một cấu trúc thông thường có thể được chia sẻ. Nhưng `final` trên biến tham chiếu không cấm sửa collection; “không thấy lệnh ghi ở đây” cũng không chứng minh không có bên khác giữ tham chiếu và sửa.

Khi có ghi đồng thời, lựa chọn cơ chế phải dựa trên **bất biến cần giữ**. Ví dụ “mỗi lần tăng phải được tính” khác với “có thể đọc một tổng quan gần thời điểm hiện tại”.

### 5.2. Ba hướng bảo vệ phổ biến

| Hướng | Phù hợp khi | Điều phải tự kiểm soát |
| --- | --- | --- |
| Giữ dữ liệu riêng theo luồng hoặc chia sẻ bản không đổi | Có thể tránh chia sẻ dữ liệu đang sửa | Công bố an toàn, tham chiếu đến phần tử có thể sửa |
| Dùng cùng một khóa bên ngoài hoặc synchronized wrapper | Muốn bảo vệ cả chuỗi thao tác bằng một khóa | Mọi bên truy cập cùng giao thức khóa, kể cả lúc duyệt |
| Dùng lớp trong `java.util.concurrent` | Nhiều luồng cần truy cập trực tiếp với hợp đồng phù hợp | Nguyên tử của từng API, cách duyệt và bất biến nhiều bước |

`Collections.synchronizedList` tạo wrapper được đồng bộ hóa. Khi dùng iterator, stream hoặc spliterator, cần tự đồng bộ trên wrapper trong suốt quá trình duyệt. Không giữ một tham chiếu tới danh sách gốc rồi bỏ qua wrapper.

```java
List<String> shared =
        Collections.synchronizedList(new ArrayList<>());

synchronized (shared) {
    if (!shared.contains("A")) {
        shared.add("A");
    }
}

synchronized (shared) {
    for (String value : shared) {
        System.out.println(value);
    }
}
```

Đây là đoạn minh họa trong một phương thức. Cùng một khóa bao trùm cả kiểm tra và thêm. Nếu nhiều nơi tự viết `contains` rồi `add` ngoài khóa chung, hai luồng vẫn có thể cùng quan sát “chưa có” và thêm lặp.

Với `synchronizedMap`, khi duyệt `keySet` hoặc `entrySet`, đồng bộ trên wrapper của map, không trên đối tượng view. [Java 17: Collections, synchronized wrappers](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html)

### 5.3. Chọn lớp đồng thời theo đúng cách sử dụng

| Nhu cầu | Lớp hoặc nhóm thường phù hợp | Đánh đổi chính |
| --- | --- | --- |
| Tra cứu/cập nhật theo khóa giữa nhiều luồng | `ConcurrentHashMap` | Không nhận `null`; không tạo giao dịch cho nhiều khóa |
| Map đồng thời có thứ tự khóa | `ConcurrentSkipListMap` | Chi phí và hợp đồng khác map băm |
| Danh sách đọc/duyệt rất nhiều, sửa ít | `CopyOnWriteArrayList` | Sao chép mảng khi sửa; iterator giữ ảnh chụp |
| Tập đồng thời không cần thứ tự | `ConcurrentHashMap.newKeySet()` | Theo đặc tính của tập dựa trên concurrent map |
| Trao đổi công việc giữa bên sản xuất và tiêu thụ | `BlockingQueue`, như `ArrayBlockingQueue` | Phải chọn dung lượng và cách xử lý đầy/rỗng |
| Hàng đợi đồng thời không cần chặn chờ | `ConcurrentLinkedQueue` | Không tự giới hạn tải như một hàng đợi có sức chứa cố định |

`ConcurrentSkipListMap` phù hợp khi cần cả đồng thời và truy cập theo thứ tự; nó không nhận khóa hoặc giá trị `null`. [Java 17: ConcurrentSkipListMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentSkipListMap.html)

Hàng đợi có dung lượng hữu hạn giúp giới hạn số công việc đang chờ. Chọn `put` để chờ, `offer` để thử hoặc `offer` có thời hạn tùy luồng xử lý. Một queue đồng thời không có giới hạn dung lượng không tự bảo vệ ứng dụng trước tốc độ sản xuất công việc lớn hơn tốc độ tiêu thụ.

### 5.4. Thao tác ghép cần API nguyên tử phù hợp

Đoạn sau **sai khi có nhiều luồng tăng cùng khóa**, kể cả `counts` là `ConcurrentHashMap`:

```java
Integer oldValue = counts.get("requests");
counts.put("requests", oldValue == null ? 1 : oldValue + 1);
```

Hai luồng có thể cùng đọc `10` rồi cùng ghi `11`, làm mất một lần tăng. Dùng một thao tác cập nhật nguyên tử theo khóa:

```java
counts.merge("requests", 1, Integer::sum);
```

Tương tự, cân nhắc `putIfAbsent`, `compute`, `computeIfAbsent` hoặc các phương thức thay thế có điều kiện thay vì tự ghép đọc–kiểm tra–ghi.

Hàm tính toán nên ngắn, tránh tác vụ chặn lâu và không sửa lại chính map trong quá trình tính. Nguyên tử theo một khóa không bảo vệ bất biến nhiều khóa: chuyển tiền giữa hai số dư cần thiết kế đồng bộ hoặc giao dịch riêng.

Một `ConcurrentHashMap<String, ArrayList<String>>` chỉ bảo vệ cấu trúc map. Việc hai luồng cùng gọi `add` trên cùng `ArrayList` lấy từ map vẫn không được map tự bảo vệ. Cần chọn giá trị bất biến, cấu trúc giá trị đồng thời hoặc cơ chế khóa phù hợp. [Java 17: ConcurrentHashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html)

### 5.5. Duyệt collection có nhiều hợp đồng khác nhau

- Iterator fail-fast của nhiều collection thông thường có thể báo `ConcurrentModificationException` khi phát hiện sửa cấu trúc không hợp lệ. Đây là cơ chế phát hiện lỗi theo khả năng, không phải bảo đảm đồng bộ và không phải cách làm chương trình an toàn.
- Iterator của `ConcurrentHashMap` là weakly consistent: có thể phản ánh một phần thay đổi diễn ra trong lúc duyệt, không cam kết ảnh chụp nguyên tử của toàn map.
- Iterator của `CopyOnWriteArrayList` dùng mảng tại lúc iterator được tạo. Những thay đổi sau đó không xuất hiện trong iterator ấy. Chi phí là việc sửa phải sao chép, và iterator có thể giữ mảng cũ còn sống.

Không gọi chung mọi cách duyệt không ném `ConcurrentModificationException` là “fail-safe” rồi suy ra cùng một ý nghĩa.

Ảnh chụp của `CopyOnWriteArrayList` cũng chỉ là ảnh chụp các tham chiếu phần tử. Nếu một đối tượng phần tử bị sửa trạng thái, danh sách không tự tạo bản sao sâu hoặc bảo vệ trạng thái đó. [Java 17: CopyOnWriteArrayList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CopyOnWriteArrayList.html)

## 6. Chương trình hoàn chỉnh: quan sát các tiêu chí

Lưu toàn bộ chương trình sau vào `CollectionCriteriaDemo.java`. Chương trình sử dụng `record`, collection thông thường và các lớp đồng thời có trong Java 17.

```java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.HashSet;
import java.util.Iterator;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeSet;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CopyOnWriteArrayList;

public class CollectionCriteriaDemo {
    record Product(String id, String name) {}

    public static void main(String[] args) throws InterruptedException {
        List<String> events = new ArrayList<>(List.of("B", "A", "B"));
        System.out.println("list = " + events);
        System.out.println("unique by insertion = " + new LinkedHashSet<>(events));
        System.out.println("unique sorted = " + new TreeSet<>(events));

        Product p1 = new Product("P1", "Pen");
        Product p2 = new Product("P2", "Pen");
        Set<Product> byEquals = new HashSet<>(List.of(p1, p2));
        Set<Product> byName = new TreeSet<>(Comparator.comparing(Product::name));
        byName.add(p1);
        byName.add(p2);
        System.out.println("hash size = " + byEquals.size());
        System.out.println("tree by name size = " + byName.size());

        Map<String, String> notes = new HashMap<>();
        notes.put("A", null);
        System.out.println("get(A) = " + notes.get("A"));
        System.out.println("get(B) = " + notes.get("B"));
        System.out.println("contains A/B = "
                + notes.containsKey("A") + "/" + notes.containsKey("B"));

        ArrayDeque<String> queue = new ArrayDeque<>();
        System.out.println("poll empty = " + queue.poll());
        try {
            queue.add(null);
        } catch (NullPointerException expected) {
            System.out.println("ArrayDeque rejects null");
        }

        ConcurrentHashMap<String, Integer> counts = new ConcurrentHashMap<>();
        List<Thread> workers = new ArrayList<>();
        for (int i = 0; i < 4; i++) {
            Thread worker = new Thread(() -> {
                for (int j = 0; j < 1_000; j++) {
                    counts.merge("requests", 1, Integer::sum);
                }
            });
            workers.add(worker);
            worker.start();
        }
        for (Thread worker : workers) {
            worker.join();
        }
        System.out.println("requests = " + counts.get("requests"));

        CopyOnWriteArrayList<String> listeners =
                new CopyOnWriteArrayList<>(List.of("A", "B"));
        Iterator<String> beforeChange = listeners.iterator();
        listeners.add("C");
        List<String> snapshot = new ArrayList<>();
        beforeChange.forEachRemaining(snapshot::add);
        System.out.println("iterator snapshot = " + snapshot);
        System.out.println("current list = " + listeners);
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 CollectionCriteriaDemo.java
java CollectionCriteriaDemo
```

Kết quả chuẩn:

```text
list = [B, A, B]
unique by insertion = [B, A]
unique sorted = [A, B]
hash size = 2
tree by name size = 1
get(A) = null
get(B) = null
contains A/B = true/false
poll empty = null
ArrayDeque rejects null
requests = 4000
iterator snapshot = [A, B]
current list = [A, B, C]
```

Cách đọc kết quả:

1. `List` giữ ba lần xuất hiện; `LinkedHashSet` chỉ giữ hai giá trị theo thứ tự chèn, còn `TreeSet` sắp theo chuỗi.
2. Hai `Product` khác mã nên khác nhau theo `equals` do record sinh ra. Comparator chỉ xét tên lại cho kết quả bằng `0`, khiến tập cây giữ một sản phẩm.
3. `get` của map trả `null` cho cả khóa có ánh xạ `null` lẫn khóa vắng; `containsKey` phân biệt hai trạng thái.
4. `poll` hàng đợi rỗng trả `null`, nhưng không thể đưa `null` vào `ArrayDeque`.
5. Bốn luồng cùng tăng một khóa bằng `merge`. Mỗi luồng tăng 1.000 lần; `join` chờ tất cả hoàn tất trước khi đọc nên tổng là 4.000.
6. Iterator của danh sách copy-on-write được tạo trước khi thêm `C`, nên vẫn chỉ duyệt `A` và `B`.

Ví dụ không in trực tiếp thứ tự của `HashSet` hoặc `ConcurrentHashMap`, nên output không phụ thuộc thứ tự duyệt mà các lớp đó không cam kết. Không dùng ví dụ “thường chạy đúng” của cập nhật có tranh chấp để chứng minh an toàn đồng thời.

## 7. Quy trình áp dụng vào bài toán thực tế

Giả sử cần tiếp nhận mã công việc, tránh xử lý trùng và chuyển cho các luồng xử lý:

1. **Xác định ý nghĩa trùng:** cùng mã công việc là một việc hay một lần thử mới? Nếu một công việc được chạy lại hợp lệ, có thể cần định danh lần thử.
2. **Đặt chính sách null:** từ chối mã `null` ngay lúc nhận, vì nó không đại diện cho công việc hợp lệ.
3. **Chọn đường truy cập:** cần kiểm tra mã đã có và lấy công việc theo thứ tự, nên một collection đơn lẻ chưa chắc thể hiện đủ cả hai.
4. **Xác định nguyên tử:** “đánh dấu đã nhận” và “đưa vào hàng đợi” là hai thay đổi. Một concurrent set cộng với concurrent queue không tự tạo giao dịch giữa chúng.
5. **Xem giới hạn hệ thống:** nhiều tiến trình hoặc nhiều máy cần cơ chế phối hợp bền vững; collection trong một JVM không bảo đảm loại trùng toàn hệ thống.
6. **Chọn chiến lược lỗi:** nếu tiến trình dừng sau đánh dấu nhưng trước xếp hàng, phải có cơ chế khôi phục thay vì làm mất công việc.

Ví dụ này cho thấy tiêu chí đồng thời phải xét ở cấp quy trình. Chọn đúng lớp là nền tảng; bảo toàn bất biến nghiệp vụ còn cần thiết kế phối hợp giữa các bước.

Trước khi tối ưu, có thể viết một bảng yêu cầu nhỏ cho từng dữ liệu: có trùng không, có `null` không, thứ tự gì, thao tác nào thường xuyên, ai được sửa và điều gì phải nguyên tử. Sau đó mới đo trên kích thước và kiểu truy cập đại diện cho thực tế.

## 8. Lỗi thường gặp cần tự kiểm tra

| Lỗi | Vì sao sai | Cách sửa |
| --- | --- | --- |
| Chọn `Set` chỉ để “đỡ trùng” nhưng chưa định nghĩa bằng nhau | Có thể giữ hoặc loại sai dữ liệu | Thiết kế `equals`/`hashCode` hoặc comparator theo yêu cầu |
| Coi khóa trùng trong Map là một mục mới | `put` thay ánh xạ hiện có | Chọn giá trị dạng danh sách/tập nếu quan hệ là một–nhiều |
| Coi mọi `List` đều nhận `null` và sửa được | Interface không quy định mọi đối tượng giống nhau | Kiểm tra lớp hoặc phương thức tạo |
| Dùng `get(key) == null` để kết luận khóa không tồn tại | Có thể là ánh xạ đến `null` | Dùng hợp đồng dữ liệu rõ hoặc kiểm tra sự tồn tại phù hợp |
| Chọn `LinkedList` vì “chèn giữa O(1)” | Có thể vẫn phải tìm vị trí O(n) | Tính cả chi phí xác định vị trí |
| Trông chờ thứ tự `HashMap` hoặc thứ tự iterator của `PriorityQueue` | Không có bảo đảm thứ tự cần dùng | Chọn cấu trúc có hợp đồng thứ tự hoặc tạo bản sắp riêng |
| Coi `ConcurrentHashMap` làm mọi chuỗi thao tác nguyên tử | Đọc rồi ghi vẫn có khoảng xen kẽ | Dùng API nguyên tử hoặc cơ chế phối hợp thích hợp |
| Coi collection an toàn thì đối tượng phần tử cũng an toàn | Collection thường chỉ quản lý tham chiếu | Thiết kế trạng thái phần tử và cơ chế sửa riêng |
| Bắt `ConcurrentModificationException` để thử lại như cơ chế đồng bộ | Fail-fast chỉ hỗ trợ phát hiện lỗi | Sửa quyền sở hữu dữ liệu hoặc giao thức đồng bộ |
| Dùng copy-on-write khi ghi liên tục trên danh sách lớn | Sao chép gây chi phí thời gian và bộ nhớ | Chỉ chọn khi mô hình đọc nhiều, sửa ít phù hợp |

## 9. Tự luyện

1. Cần loại mã khách hàng trùng nhưng giữ thứ tự người dùng nhập. Vì sao `LinkedHashSet` phù hợp hơn `TreeSet`?  
   **Gợi ý:** yêu cầu giữ thứ tự chèn, không phải sắp theo giá trị.

2. Hai sản phẩm khác mã nhưng cùng giá bán được thêm vào `TreeSet` có comparator chỉ xét giá. Tập giữ bao nhiêu phần tử?  
   **Gợi ý:** phép so sánh bằng `0` làm chúng tương đương đối với tập cây. Muốn giữ cả hai, phải thêm tiêu chí phân biệt phù hợp.

3. Một `HashMap` chứa khóa `A` với giá trị `null`. `getOrDefault("A", "unknown")` trả gì?  
   **Đáp án:** `null`, vì có ánh xạ cho khóa `A`.

4. Thay `merge` trong ví dụ bằng `get` rồi `put`. Có được kỳ vọng luôn thấy 4.000 không?  
   **Đáp án:** không. Hai luồng có thể cùng tính từ một giá trị cũ và làm mất cập nhật.

5. Cần chuyển công việc giữa nhiều luồng, giới hạn tối đa 100 công việc chờ và cho bên nhận chờ khi rỗng. Bắt đầu đánh giá cấu trúc nào?  
   **Gợi ý:** một `BlockingQueue` có dung lượng hữu hạn, như `ArrayBlockingQueue`; sau đó quyết định hành vi khi đầy, ngắt chờ và dừng hệ thống.

Khi trả lời, luôn giải thích cả quy tắc dữ liệu lẫn cách truy cập. Tên lớp chỉ có ý nghĩa khi gắn với các điều kiện đó.
