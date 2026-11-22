# Chính sách phần tử null và giới hạn kiểu của từng cài đặt

## 1. Một giá trị có thể đúng kiểu nhưng vẫn không được chấp nhận

Xét hai collection cùng giữ chuỗi:

```java
// Đoạn minh họa trong một phương thức; cần import java.util.*.
List<String> names = new ArrayList<>();
Deque<String> jobs = new ArrayDeque<>();

names.add(null); // Được phép.
// jobs.add(null); // Biên dịch được, nhưng ném NullPointerException khi chạy.
```

Cả hai lời gọi đều hợp lệ về kiểu ở thời điểm biên dịch. Khác biệt là hợp đồng của đối tượng thực tế: `ArrayList` cho phép phần tử `null`, còn `ArrayDeque` không cho phép.

Khi làm việc với collection, có ba lớp câu hỏi:

1. **Kiểu khai báo cho phép truyền gì?** Ví dụ `List<String>` không cho thêm `Integer` bằng lời gọi có kiểm tra kiểu thông thường.
2. **Cài đặt chấp nhận giá trị nào?** Ví dụ `null` có thể bị cấm.
3. **Cấu trúc cần điều kiện bổ sung gì?** Ví dụ các phần tử phải so sánh được với nhau để lưu trong cây có thứ tự.

Chính sách `null` và giới hạn kiểu thuộc **hợp đồng của cài đặt hoặc factory/wrapper**, không chỉ thuộc tên giao diện `List`, `Set` hay `Map`.

Bài sử dụng API có trong Java 17. Mục tiêu là biết nơi nào kiểm tra trước khi thay cấu trúc dữ liệu, chẩn đoán ngoại lệ đúng nguyên nhân và thiết kế đầu vào rõ ràng.

## 2. Phân biệt ba vị trí xuất hiện null

### 2.1. Biến collection là null

```java
// Đoạn minh họa trong một phương thức; cần import java.util.List.
List<String> names = null;
// names.add("A"); // NullPointerException vì không có đối tượng collection.
```

Chưa có một collection nào để xét chính sách phần tử. Lỗi xuất hiện vì gọi phương thức qua tham chiếu `null`.

### 2.2. Collection tồn tại và chứa phần tử null

```java
// Đoạn minh họa trong một phương thức; cần import java.util.*.
List<String> names = new ArrayList<>();
names.add(null);

System.out.println(names.size()); // 1
System.out.println(names.get(0)); // null
```

Danh sách không rỗng. Nó có một phần tử với giá trị `null`.

`null` không phải chuỗi `"null"`, không phải chuỗi rỗng `""` và cũng không phải “không có phần tử” trong cấu trúc này.

### 2.3. Phần tử tồn tại nhưng một trường bên trong là null

Một `List<Person>` có thể chứa một đối tượng `Person` khác `null` nhưng trường `name` của người đó là `null`. Collection thông thường không tự kiểm tra mọi thuộc tính của phần tử.

Tương tự, việc cấm phần tử `null` không bảo đảm phần tử thỏa mãn quy tắc nghiệp vụ như tên không rỗng, giá không âm hoặc dữ liệu đầy đủ. Đó là trách nhiệm của kiểu dữ liệu và lớp xử lý đầu vào.

## 3. Hợp đồng chung về giá trị không hợp lệ

Collections Framework cho phép cài đặt giới hạn phần tử, chẳng hạn cấm `null` hoặc chỉ nhận những giá trị có khả năng so sánh phù hợp.

Khi chèn phần tử không hợp lệ, các ngoại lệ thường gặp là:

| Ngoại lệ | Ý nghĩa cần xem xét |
| --- | --- |
| `NullPointerException` | Cài đặt không nhận `null` hoặc thao tác bên trong không xử lý được `null` |
| `ClassCastException` | Phần tử/khóa không tương thích với yêu cầu kiểu hoặc phép so sánh |
| `IllegalArgumentException` | Một thuộc tính của phần tử/đối số không đáp ứng ràng buộc được công bố |
| `UnsupportedOperationException` | Thao tác sửa không được hỗ trợ, dù giá trị có thể đúng kiểu và khác `null` |

Với truy vấn như `contains` hoặc thao tác xóa theo đối tượng, hợp đồng tổng quát có thể cho phép trả `false` hoặc ném ngoại lệ đối với phần tử không phù hợp. Không suy diễn rằng “cấm thêm `null`” đồng nghĩa mọi `contains(null)` đều có một hành vi giống nhau.

Xem [Collection API: restrictions on elements](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collection.html). Khi lớp cụ thể có bảo đảm mạnh hơn, hãy dùng bảo đảm đó.

## 4. Bảng chính sách null của các collection thông dụng

Bảng sau mô tả việc **lưu phần tử**, không phải mọi truy vấn với đối số `null`.

| Cài đặt hoặc cách tạo | Nhận phần tử `null`? | Ghi chú |
| --- | --- | --- |
| `ArrayList` | Có | Có thể có nhiều vị trí `null` |
| `LinkedList` | Có | Dùng làm hàng đợi vẫn cần tránh nhập nhằng với kết quả `poll` |
| `HashSet` | Có | Tối đa một phần tử `null` |
| `LinkedHashSet` | Có | Tối đa một `null`, giữ thứ tự chèn |
| `TreeSet` với thứ tự tự nhiên | Không | `null` không so sánh được theo thứ tự tự nhiên |
| `TreeSet` với comparator | Tùy comparator | Có thể dùng comparator có chính sách `null` rõ ràng |
| `ArrayDeque` | Không | `add/offer` phần tử `null` bị từ chối |
| `PriorityQueue` | Không | Comparator chấp nhận `null` không bỏ được lệnh cấm này |
| `EnumSet` | Không | Phần tử phải thuộc đúng loại enum và khác `null` |
| `Arrays.asList(...)` | Có thể chứa `null` | Danh sách cố định kích thước, được chống lưng bởi mảng |
| `List.of`, `List.copyOf` | Không | Factory từ chối nguồn có phần tử `null` |
| `Set.of`, `Set.copyOf` | Không | Ngoài quy tắc `null` còn có quy tắc riêng về trùng |
| `Collections.unmodifiableList(backing)` | Có thể chứa `null` từ nguồn | Wrapper ngăn sửa, không làm sạch nội dung nguồn |

Nguồn cho các nhóm cài đặt:

- [ArrayList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html), [LinkedList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedList.html).
- [HashSet](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashSet.html), [TreeSet](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeSet.html).
- [ArrayDeque](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayDeque.html), [PriorityQueue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/PriorityQueue.html).
- [EnumSet](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/EnumSet.html), [List factories](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#unmodifiable), [Set factories](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Set.html#unmodifiable).

Không biến bảng thành quy tắc theo tên họ: “mọi list đều nhận `null`” và “mọi cấu trúc có comparator đều nhận `null`” đều không đúng.

## 5. Map phải xét riêng khóa và giá trị

`Map` không kế thừa `Collection`, nhưng nằm trong cùng framework và thường được chọn cùng các cấu trúc collection. Với map, có hai vị trí cần kiểm tra độc lập.

| Cài đặt hoặc factory | Khóa `null` | Giá trị `null` |
| --- | --- | --- |
| `HashMap` | Cho phép một khóa `null` | Cho phép |
| `LinkedHashMap` | Cho phép một khóa `null` | Cho phép |
| `TreeMap` thứ tự tự nhiên | Không cho phép | Cho phép |
| `TreeMap` có comparator | Tùy comparator | Cho phép |
| `EnumMap` | Không cho phép | Cho phép |
| `ConcurrentHashMap` | Không cho phép | Không cho phép |
| `Map.of`, `Map.ofEntries`, `Map.copyOf` | Không cho phép | Không cho phép |

Tài liệu tương ứng: [HashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashMap.html), [TreeMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeMap.html), [EnumMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/EnumMap.html), [ConcurrentHashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html), [Map factories](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html#unmodifiable).

### 5.1. get trả null có thể mang hai ý nghĩa

```java
// Đoạn minh họa trong một phương thức; cần import java.util.*.
Map<String, Integer> scores = new HashMap<>();
scores.put("pending", null);

System.out.println(scores.get("unknown"));       // null
System.out.println(scores.get("pending"));       // null
System.out.println(scores.containsKey("unknown")); // false
System.out.println(scores.containsKey("pending")); // true
```

Với map cho phép giá trị `null`:

- Không có khóa.
- Có khóa nhưng ánh xạ tới `null`.

Cả hai đều có thể làm `get` trả `null`. Nếu cần phân biệt trong mã một luồng này, kiểm tra sự tồn tại của khóa theo hợp đồng.

Không coi chuỗi `get` rồi `containsKey` là một giao dịch nguyên tử khi map có thể bị luồng khác sửa. Đồng thời là yêu cầu thiết kế riêng.

### 5.2. Vì sao phải kiểm tra khi đổi cài đặt?

Đổi `HashMap` thành `ConcurrentHashMap` có thể làm đầu vào từng được chấp nhận trở thành lỗi. Không chỉ có đặc tính nhiều luồng thay đổi; chính sách khóa/giá trị `null` cũng thay đổi.

Đổi `HashMap` thành `TreeMap` còn thêm yêu cầu về khả năng so sánh khóa. Kiểu khai báo `Map<K, V>` không xóa các khác biệt này.

## 6. null và giá trị báo “không có”

`Queue.poll` hoặc `Deque.poll` có thể dùng `null` để báo cấu trúc rỗng. Nếu một cài đặt còn cho phép lưu phần tử `null`, cùng một kết quả trở nên dễ hiểu nhầm.

```java
// Đoạn minh họa trong một phương thức; cần import java.util.*.
Queue<String> queue = new LinkedList<>();
queue.add(null);

System.out.println(queue.size()); // 1
System.out.println(queue.poll()); // null: vừa lấy phần tử null.
System.out.println(queue.size()); // 0
System.out.println(queue.poll()); // null: không có phần tử để lấy.
```

`LinkedList` cho lưu `null`, nhưng đó không phải lý do tốt để dùng `null` làm công việc thật trong hàng đợi. Chọn dữ liệu biểu diễn công việc rõ ràng hoặc quy định phần tử phải khác `null`.

Với `ArrayDeque`, chính sách cấm `null` làm kết quả `poll` khác `null` phân biệt rõ hơn với hàng đợi rỗng. Không mở rộng lập luận này thành quy tắc “mọi Queue đều cấm `null`”, vì ví dụ `LinkedList` cho thấy điều ngược lại.

Cũng không biến chuỗi `isEmpty` rồi `poll` thành cách kiểm tra an toàn nhiều luồng một cách tự động.

## 7. Cấu trúc có thứ tự: đúng kiểu khai báo chưa đủ

### 7.1. Thứ tự tự nhiên yêu cầu so sánh được

`TreeSet<E>` và khóa của `TreeMap<K, V>` cần được sắp theo thứ tự tự nhiên hoặc comparator. Với thứ tự tự nhiên, các phần tử/khóa phải có khả năng so sánh phù hợp với nhau.

```java
// Đoạn minh họa trong một phương thức; cần import java.util.*.
Set<Number> numbers = new TreeSet<>();
numbers.add(1);
// numbers.add(2.5); // ClassCastException: Integer và Double không có
                    // thứ tự tự nhiên so sánh chéo phù hợp trong cấu trúc này.
```

`Integer` và `Double` đều là `Number` nên được phép truyền vào API theo kiểu khai báo. Nhưng “cùng là Number” không tạo ra một thứ tự tự nhiên chung cho mọi loại số.

Nếu yêu cầu nghiệp vụ thật sự là sắp các dạng giá trị khác nhau, phải thiết kế comparator có thứ tự nhất quán trên toàn miền dữ liệu. Không chữa lỗi bằng raw type hoặc ép kiểu mù.

### 7.2. Comparator có thể định nghĩa vị trí của null

```java
// Đoạn minh họa trong một phương thức; cần import java.util.*.
Comparator<String> nullFirst =
        Comparator.nullsFirst(Comparator.naturalOrder());

NavigableSet<String> sorted = new TreeSet<>(nullFirst);
sorted.add("B");
sorted.add(null);
sorted.add("A");

System.out.println(sorted); // [null, A, B]
```

Comparator này xếp `null` trước các chuỗi khác `null`; chuỗi khác `null` được so theo thứ tự tự nhiên. Có thể dùng `nullsLast` nếu yêu cầu ngược lại. [Comparator.nullsFirst](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Comparator.html#nullsFirst(java.util.Comparator))

Comparator phải xử lý được các giá trị mà cấu trúc dự kiến nhận và phải tuân thủ hợp đồng so sánh. Không chỉ thêm một nhánh `null` rồi bỏ qua tính nhất quán còn lại.

Quan trọng: một comparator chấp nhận `null` chỉ có tác dụng nếu **bản thân cài đặt cho phép**. `PriorityQueue` vẫn cấm `null` ngay cả khi truyền comparator có chính sách này.

### 7.3. So sánh được và “bằng nhau” cần nhất quán

Trong `TreeSet`, kết quả so sánh bằng `0` được dùng để coi phần tử là cùng vị trí theo cấu trúc. Nếu comparator chỉ so độ dài chuỗi, `"An"` và `"Bo"` có thể bị coi là trùng dù `equals` khác nhau.

Đây là vấn đề khác với `null` nhưng thuộc cùng câu hỏi: “cài đặt yêu cầu gì ở phần tử?”. Đối với `Set`, thứ tự cần nhất quán với `equals` để giữ đúng hợp đồng chung của tập. Đối với map có thứ tự, phép so sánh khóa cũng cần được thiết kế phù hợp.

## 8. Generics kiểm tra gì và không kiểm tra gì?

### 8.1. Kiểm tra kiểu tại thời điểm biên dịch

```java
// Đoạn minh họa trong một phương thức; cần import java.util.*.
List<String> words = new ArrayList<>();
words.add("hello");
// words.add(123); // Không biên dịch.
words.add(null);  // Kiểu tham chiếu cho phép null; ArrayList cũng chấp nhận.
```

Đối số kiểu generic là kiểu tham chiếu, không phải kiểu nguyên thủy. Vì vậy, dùng `List<Integer>`, không dùng `List<int>`. Tuy nhiên, `Integer` có thể là `null`; khi unboxing sang `int`, giá trị `null` sẽ gây `NullPointerException`.

Kiểu `String` không mã hóa một bảo đảm “khác `null`” trong hệ thống kiểu Java thông thường. Nếu API cần điều kiện đó, phải công bố và kiểm tra phù hợp.

### 8.2. Danh sách kiểu con không tự thành danh sách kiểu cha

```java
// Đoạn minh họa trong một phương thức; cần import java.util.*.
List<Integer> integers = List.of(1, 2, 3);
// List<Number> numbers = integers; // Không biên dịch.

List<Number> numbers = new ArrayList<>();
numbers.addAll(integers);
numbers.add(2.5);

System.out.println(numbers); // [1, 2, 3, 2.5]
```

Nếu cho gán trực tiếp `List<Integer>` sang `List<Number>`, mã khác có thể thêm `Double` vào cùng danh sách vốn được kỳ vọng chỉ chứa `Integer`. Tính bất biến của tham số kiểu generic ngăn sai lệch đó.

`addAll` có chữ ký nhận nguồn `Collection<? extends E>` nên có thể sao chép các `Integer` vào đích chứa `Number`. Bản sao và phép gán tham chiếu là hai việc khác nhau.

### 8.3. Type erasure không tạo hàng rào kiểm tra phần tử ở mọi lần thêm

Với phần lớn generics Java, đối số kiểu bị xóa khỏi biểu diễn kiểu khi chạy. `new ArrayList<String>()` không giữ một hàng rào `String.class` riêng để tự kiểm tra mọi lời gọi raw vào `add`.

Nếu dùng raw type hoặc unchecked cast, có thể làm dữ liệu sai kiểu lọt vào rồi lỗi xuất hiện khi đọc. Không có mâu thuẫn với generics: mã đã đi qua ranh giới bỏ kiểm tra kiểu.

Các quy tắc về parameterized type, raw type, type erasure và heap pollution được mô tả trong [JLS Chapter 4](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html), đặc biệt các mục 4.5, 4.6, 4.8 và 4.12.2.

## 9. Mã raw và checked collection

### 9.1. Lỗi có thể xuất hiện muộn tại chỗ đọc

```java
// Minh họa cố ý không an toàn; đặt trong một phương thức.
// Cần import java.util.*; trình biên dịch cảnh báo raw/unchecked.
List<String> words = new ArrayList<>();
List raw = words;
raw.add(123);

// String first = words.get(0); // ClassCastException khi chuyển kết quả sang String.
```

`ArrayList` không tự biết nó đang được mong đợi chứa `String` qua tham chiếu khác. Cảnh báo unchecked phải được xem là tín hiệu rủi ro, không phải phiền phức cần tắt đại trà.

### 9.2. Wrapper checked kiểm tra ngay tại ranh giới chèn

```java
// Minh họa khi phải tương tác mã cũ dùng raw type.
// Cần import java.util.*; raw.add là lời gọi cố ý không an toàn.
List<String> checked =
        Collections.checkedList(new ArrayList<>(), String.class);
List raw = checked;

// raw.add(123); // ClassCastException ngay khi chèn qua wrapper.
checked.add("A");
checked.add(null); // Được: backing ArrayList cho phép null.
```

`checkedList` cung cấp view kiểm tra kiểu lúc chạy:

- Kiểm tra dữ liệu đi qua các thao tác chèn/thay thế của view.
- Không tự cấm `null` nếu collection nguồn cho phép.
- Không tự sửa dữ liệu sai kiểu đã tồn tại trong nguồn.
- Không ngăn việc một tham chiếu khác chèn trực tiếp vào nguồn, bỏ qua wrapper.
- Không kiểm tra sâu tham số kiểu lồng nhau như “mọi List bên trong đều chứa String”.

Nó hữu ích khi buộc phải đi qua mã legacy, nhưng không thay thế thiết kế generic đúng và kiểm tra đầu vào nghiệp vụ. Xem [Collections.checkedList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#checkedList(java.util.List,java.lang.Class)).

## 10. Factory, wrapper và thao tác sao chép

### 10.1. Cùng là List nhưng chính sách khác nhau

```java
// Đoạn minh họa trong một phương thức; cần import java.util.*.
List<String> nullable = new ArrayList<>();
nullable.add(null);

List<String> view = Collections.unmodifiableList(nullable);
System.out.println(view); // [null]

// List<String> snapshot = List.copyOf(nullable);
// Dòng trên ném NullPointerException vì nguồn chứa null.
```

“Không cho sửa” và “không cho `null`” là hai chính sách độc lập. Wrapper không cho sửa có thể quan sát dữ liệu `null` từ nguồn, trong khi `List.copyOf` từ chối phần tử đó khi tạo kết quả.

`Set.of` không nhận phần tử trùng trong các đối số được truyền; `Set.copyOf` có thể hợp nhất các phần tử bằng nhau của nguồn thành tập. Không suy diễn mọi quy tắc của factory `of` sang factory `copyOf` chỉ vì chúng cùng tạo kết quả không cho sửa.

### 10.2. Chú ý lời gọi được đánh giá từ trong ra ngoài

```java
// Minh họa một biểu thức sẽ ném NullPointerException.
// Cần import java.util.*.
// List<String> values = new ArrayList<>(List.of("A", (String) null));
```

`List.of` thất bại trước khi constructor `ArrayList` nhận dữ liệu. Điều này không chứng minh `ArrayList` cấm `null`.

Nếu thật sự cần tạo danh sách sửa được có `null`, dùng nguồn phù hợp:

```java
// Đoạn minh họa trong một phương thức; cần import java.util.*.
List<String> values =
        new ArrayList<>(Arrays.asList("A", null));
System.out.println(values); // [A, null]
```

### 10.3. null của mảng varargs khác phần tử null

```java
// Đoạn minh họa trong một phương thức; cần import java.util.*.
List<String> oneNull = Arrays.asList((String) null);
System.out.println(oneNull.size()); // 1

// Arrays.asList((String[]) null); // NullPointerException: mảng nguồn là null.
```

Ép kiểu trong ví dụ làm ý định rõ ràng: truyền một phần tử `String` là `null`, hoặc truyền cả mảng là `null`. Xem [Arrays.asList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Arrays.html#asList(T...)).

## 11. contains, remove và nguy cơ suy diễn từ truy vấn

`contains(Object)` và `remove(Object)` nhận `Object`, nên việc truyền đối số khác tham số kiểu không nhất thiết bị chặn lúc biên dịch.

```java
// Đoạn minh họa trong một phương thức; cần import java.util.*.
Collection<String> words = new ArrayList<>(List.of("one"));

System.out.println(words.contains(123)); // false trong ví dụ ArrayList này.
System.out.println(words.remove(123));   // false.
```

Một cấu trúc có thứ tự có thể cần so sánh đối số truy vấn với phần tử, dẫn tới `ClassCastException` với kiểu không phù hợp. Tương tự, truy vấn `null` trên cài đặt cấm `null` có thể bị từ chối theo hợp đồng.

Các kết luận nên tránh:

- “`contains(null)` trả `false` nên collection chắc chắn cho thêm `null`.”
- “Mọi phương thức nhận `Object` đều an toàn với mọi đối tượng.”
- “Thử thành công trên collection rỗng đủ chứng minh dữ liệu hợp lệ.”
- “Thêm một phần tử không so sánh được chưa lỗi thì thêm các phần tử tiếp theo cũng được.”

Cần đọc quy tắc theo từng thao tác. Một phép so sánh có thể chỉ xảy ra khi cấu trúc đã có dữ liệu, và các lớp có thể chủ động kiểm tra sớm hơn.

## 12. Thiết kế chính sách tại ranh giới ứng dụng

Nếu nghiệp vụ không chấp nhận phần tử `null`, hãy quyết định rõ từ đầu thay vì phụ thuộc tình cờ vào collection được dùng.

```java
// Minh họa phương thức trong một lớp; cần import java.util.*.
static List<String> validatedNames(Collection<String> source) {
    Objects.requireNonNull(source, "source");

    List<String> result = new ArrayList<>(source.size());
    for (String name : source) {
        result.add(Objects.requireNonNull(name, "name"));
    }
    return List.copyOf(result);
}
```

Phương thức này:

1. Từ chối collection nguồn `null`.
2. Từ chối từng phần tử `null` trong lúc dựng kết quả riêng.
3. Không thêm/xóa phần tử của nguồn.
4. Trả một danh sách không cho sửa, không nhận `null`.

Nó chưa kiểm tra tên rỗng hoặc chỉ gồm khoảng trắng. Nếu nghiệp vụ yêu cầu, bổ sung kiểm tra với thông báo thích hợp.

Đừng âm thầm loại `null` nếu vị trí hoặc số lượng phần tử mang ý nghĩa, chẳng hạn danh sách điểm theo thứ tự môn học. “Bỏ phần tử không hợp lệ” và “từ chối đầu vào” là hai chính sách khác nhau.

Với trường có ý nghĩa “chưa có giá trị”, có thể chọn một kiểu dữ liệu hoặc trạng thái tường minh thay vì nhét `null` vào cấu trúc mà các thao tác khác khó phân biệt. Không cần bọc mọi phần tử vào `Optional` theo một khuôn chung; lựa chọn phải phục vụ mô hình dữ liệu.

## 13. Chương trình hoàn chỉnh

Lưu thành `NullAndTypePolicyDemo.java`. Phần legacy cố ý dùng raw type để quan sát thời điểm lỗi; không nên sao chép cách đó vào mã ứng dụng bình thường.

```java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collection;
import java.util.Collections;
import java.util.Comparator;
import java.util.Deque;
import java.util.HashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.NavigableSet;
import java.util.Set;
import java.util.TreeSet;
import java.util.concurrent.ConcurrentHashMap;

public final class NullAndTypePolicyDemo {
    private static void showRejection(String label, Runnable action) {
        try {
            action.run();
            System.out.println(label + ": accepted");
        } catch (NullPointerException ex) {
            System.out.println(label + ": NullPointerException");
        } catch (ClassCastException ex) {
            System.out.println(label + ": ClassCastException");
        }
    }

    @SuppressWarnings({"rawtypes", "unchecked"})
    private static void putThroughLegacyCode(List target, Object value) {
        target.add(value);
    }

    public static void main(String[] args) {
        List<String> nullable = new ArrayList<>();
        nullable.add(null);
        nullable.add("A");
        nullable.add(null);
        System.out.println("List: " + nullable);

        Set<String> unique = new LinkedHashSet<>(nullable);
        System.out.println("Set: " + unique);

        Deque<String> deque = new ArrayDeque<>();
        showRejection("Deque add null", () -> deque.add(null));
        System.out.println("Empty deque poll: " + deque.poll());

        NavigableSet<String> natural = new TreeSet<>();
        showRejection("Natural TreeSet add null", () -> natural.add(null));

        Comparator<String> nullFirst =
                Comparator.nullsFirst(Comparator.naturalOrder());
        NavigableSet<String> sorted = new TreeSet<>(nullFirst);
        sorted.add("B");
        sorted.add(null);
        sorted.add("A");
        System.out.println("Null-friendly TreeSet: " + sorted);

        Map<String, Integer> map = new HashMap<>();
        map.put(null, 7);
        map.put("missingValue", null);
        System.out.println("Null key value: " + map.get(null));
        System.out.println("Absent value: " + map.get("absent"));
        System.out.println("Present null value: " + map.get("missingValue"));
        System.out.println("Contains absent: " + map.containsKey("absent"));
        System.out.println("Contains missingValue: "
                + map.containsKey("missingValue"));

        Map<String, Integer> concurrent = new ConcurrentHashMap<>();
        showRejection("ConcurrentHashMap null key",
                () -> concurrent.put(null, 1));
        showRejection("ConcurrentHashMap null value",
                () -> concurrent.put("A", null));

        showRejection("List.of null", () -> List.of("A", (String) null));
        showRejection("List.copyOf nullable", () -> List.copyOf(nullable));

        List<String> fixed = Arrays.asList("A", null);
        System.out.println("Arrays.asList: " + fixed);
        List<String> view = Collections.unmodifiableList(nullable);
        System.out.println("Unmodifiable view contains null: "
                + view.contains(null));

        List<String> unsafe = new ArrayList<>();
        putThroughLegacyCode(unsafe, 123);
        showRejection("Read polluted List<String>", () -> {
            String value = unsafe.get(0);
            System.out.println(value);
        });

        List<String> checked =
                Collections.checkedList(new ArrayList<>(), String.class);
        showRejection("Checked legacy insert",
                () -> putThroughLegacyCode(checked, 123));
        checked.add(null);
        System.out.println("Checked allows backing null: " + checked);

        Collection<Integer> integers = List.of(1, 2, 3);
        List<Number> numbers = new ArrayList<>();
        numbers.addAll(integers);
        numbers.add(2.5);
        System.out.println("Numbers: " + numbers);
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 NullAndTypePolicyDemo.java
java NullAndTypePolicyDemo
```

Mã đã được kiểm tra bằng `--release 17` trên một JDK mới hơn. `@SuppressWarnings` chỉ đặt tại hàm legacy minh họa để tập trung output; nó không sửa tính không an toàn của raw type.

Stdout:

```text
List: [null, A, null]
Set: [null, A]
Deque add null: NullPointerException
Empty deque poll: null
Natural TreeSet add null: NullPointerException
Null-friendly TreeSet: [null, A, B]
Null key value: 7
Absent value: null
Present null value: null
Contains absent: false
Contains missingValue: true
ConcurrentHashMap null key: NullPointerException
ConcurrentHashMap null value: NullPointerException
List.of null: NullPointerException
List.copyOf nullable: NullPointerException
Arrays.asList: [A, null]
Unmodifiable view contains null: true
Read polluted List<String>: ClassCastException
Checked legacy insert: ClassCastException
Checked allows backing null: [null]
Numbers: [1, 2, 3, 2.5]
```

### Những gì ví dụ chứng minh

- `ArrayList` giữ được hai vị trí `null`; `LinkedHashSet` chỉ giữ một phần tử `null`.
- `ArrayDeque` cấm `null`; `poll` trên đối tượng rỗng trả `null`.
- `TreeSet` thứ tự tự nhiên cấm `null`; comparator được chọn có thể tạo thứ tự `null, A, B`.
- `HashMap` chấp nhận khóa và giá trị `null`. `get` không tự phân biệt khóa vắng với khóa ánh xạ tới `null`.
- `ConcurrentHashMap` từ chối cả hai loại `null`.
- `List.of` và `List.copyOf` từ chối nguồn có phần tử `null`.
- `Arrays.asList` giữ được `null`; wrapper không cho sửa không tự xóa `null` khỏi nguồn.
- Chèn sai kiểu qua raw `ArrayList` có thể chỉ lộ khi đọc thành `String`. Qua checked wrapper, lỗi bị phát hiện khi chèn.
- Chép các `Integer` vào `List<Number>` qua `addAll` hợp lệ; gán trực tiếp `List<Integer>` sang `List<Number>` là một chuyện khác.

Hàm `showRejection` chỉ dùng để quan sát ngoại lệ dự kiến. Nó không chứng minh rằng mọi nguồn đầu vào của ứng dụng đã được kiểm tra.

## 14. Lỗi phổ biến và cách kiểm tra

| Cách hiểu sai | Vì sao sai | Cách xử lý |
| --- | --- | --- |
| `List<String>` chắc chắn không có `null` | Generic không biểu đạt tính khác `null` | Công bố và kiểm tra điều kiện đầu vào |
| Mọi `List` đều nhận `null` | Factory như `List.of` cấm | Xem nguồn tạo đối tượng |
| Mọi `TreeSet` cấm `null` | Comparator có thể định nghĩa thứ tự cho `null` | Kiểm tra comparator và hợp đồng lớp |
| Comparator nhận `null` thì mọi collection nhận `null` | `PriorityQueue` có lệnh cấm riêng | Kiểm tra cả comparator lẫn cài đặt |
| `Map.get` trả `null` nghĩa là không có khóa | Có thể là giá trị `null` đã lưu | Dùng hợp đồng phân biệt phù hợp |
| Chuyển `HashMap` sang concurrent map không đổi đầu vào | `ConcurrentHashMap` cấm khóa/giá trị `null` | Kiểm tra chính sách trước khi thay |
| `List.of` lỗi trong constructor `ArrayList` nghĩa là `ArrayList` cấm `null` | Biểu thức nguồn đã lỗi trước | Xem thứ tự đánh giá biểu thức |
| Cùng là `Number` thì sắp tự nhiên được | Các loại số không tự so sánh chéo theo một thứ tự chung | Chọn kiểu dữ liệu/comparator phù hợp |
| Checked wrapper làm sạch toàn bộ nguồn | Nó bảo vệ thao tác đi qua wrapper | Kiểm tra nguồn và không giữ đường chèn bỏ qua |
| Bỏ cảnh báo unchecked là xử lý được vấn đề | Dữ liệu sai kiểu vẫn có thể lọt vào | Giảm raw type và kiểm soát ranh giới legacy |
| Không cho sửa đồng nghĩa không có `null` | Đây là hai đặc tính độc lập | Tài liệu hóa từng đặc tính |

## 15. Tự kiểm tra và thực hành

### Câu hỏi

1. `List<String> x = null;` khác `List<String> x = new ArrayList<>(); x.add(null);` thế nào?
2. Vì sao lời gọi `new ArrayDeque<String>().add(null)` biên dịch nhưng thất bại lúc chạy?
3. `HashSet` chứa tối đa bao nhiêu phần tử `null`?
4. Cần gì để `TreeSet<String>` nhận `null` một cách có chủ đích?
5. Comparator nhận `null` có đủ để `PriorityQueue` nhận `null` không?
6. Vì sao `get` trên `HashMap` có thể trả `null` dù khóa tồn tại?
7. `List<Number>` có thể giữ `Integer` và `Double`, vậy `TreeSet<Number>` thứ tự tự nhiên có tự hỗ trợ cả hai không?
8. Checked wrapper kiểm tra ở thời điểm nào và có tự cấm `null` không?
9. Vì sao `Arrays.asList((String) null)` khác `Arrays.asList((String[]) null)`?
10. Khi đổi cài đặt, ngoài kiểu generic cần kiểm tra những ràng buộc nào?

### Bài tập

- Tạo bảng thử riêng cho `add(null)`, `contains(null)` và `remove(null)`; phân biệt điều tài liệu bảo đảm với kết quả quan sát của cài đặt đang chạy.
- Dùng `TreeSet` với `nullsFirst` rồi đổi thành `nullsLast`; dự đoán thứ tự trước khi chạy.
- Tạo `HashMap` có khóa `"pending"` ánh xạ tới `null` và đối chiếu với khóa không tồn tại.
- Sửa một đoạn dùng raw type để không còn cảnh báo unchecked.
- Bọc ranh giới legacy bằng `Collections.checkedList` và kiểm chứng kiểu sai bị từ chối ngay lúc chèn.
- Viết hàm kiểm tra nguồn không có `null` trước khi chuyển sang collection có chính sách nghiêm ngặt hơn.
- Thử chuyển dữ liệu chứa `null` từ `ArrayList` sang `List.copyOf`; giải thích lỗi và chọn chính sách xử lý đúng nghiệp vụ thay vì loại bỏ dữ liệu âm thầm.

### Gợi ý đối chiếu

1. Trường hợp đầu không có đối tượng; trường hợp sau có danh sách chứa một phần tử `null`.
2. Kiểu tham chiếu cho phép truyền `null` nhưng lớp cài đặt từ chối giá trị đó.
3. Một.
4. Comparator phù hợp xử lý `null` và tuân thủ hợp đồng so sánh.
5. Không; cài đặt có quy tắc cấm riêng.
6. Map có thể chứa giá trị `null` cho khóa đó.
7. Không; cùng kiểu cha không tạo khả năng so sánh tự nhiên chéo.
8. Kiểm tra lúc dữ liệu được chèn qua view; `null` tùy backing collection.
9. Một trường hợp truyền một phần tử `null`, trường hợp kia truyền mảng nguồn `null`.
10. Chính sách `null`, khả năng so sánh, bằng nhau, loại phần tử/khóa, giới hạn giá trị và hành vi từng thao tác.
