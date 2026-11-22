# Thứ tự lặp và các hành vi không được API cam kết

## 1. Vì sao hành vi “vẫn chạy như cũ” chưa chắc là tương thích?

Khi nâng cấp JDK, framework, thư viện hoặc thay đổi implementation, nhiều ứng dụng Java tiếp tục biên dịch và chạy mà không phát sinh exception, nhưng dữ liệu quan sát được lại khác trước. Một nguyên nhân phổ biến là mã ứng dụng dựa vào **thứ tự lặp**, **thứ tự xử lý** hoặc một chi tiết hành vi mà API chưa bao giờ cam kết.

Ví dụ, một ứng dụng đưa dữ liệu vào `HashMap` rồi lặp qua `map.keySet()` để tạo báo cáo. Trong nhiều lần chạy, các khóa có thể xuất hiện theo cùng một thứ tự. Nhóm phát triển dễ nhầm thứ tự đó là “mặc định Java”. Sau khi nâng JDK hoặc thay đổi số phần tử, báo cáo đảo thứ tự; kiểm thử snapshot bắt đầu thất bại hoặc người dùng thấy dữ liệu hiển thị không ổn định. Tuy nhiên, `HashMap` không bảo đảm iteration order, nên việc thứ tự thay đổi không nhất thiết là lỗi của JVM hay thư viện mới.

Tình huống tương tự xuất hiện khi:

- Dùng `HashSet` để sinh danh sách gửi qua API và kỳ vọng phần tử được sắp giống thứ tự thêm.
- Dùng `Map.of(...)`, `Set.of(...)` hoặc `Collectors.toSet()` rồi dựa vào thứ tự đang thấy.
- Đổi `stream()` sang `parallelStream()`, tiếp tục dùng `forEach` cho tác dụng phụ có thứ tự.
- Dùng kết quả `Files.list(...)` hoặc `Class.getDeclaredMethods()` và cho rằng nó phản ánh thứ tự file hoặc thứ tự khai báo trong source.
- Đọc dữ liệu SQL không có `ORDER BY` và coi thứ tự dòng trả về là ổn định.
- Dùng `PriorityQueue.iterator()` và kỳ vọng các phần tử được lặp theo độ ưu tiên.
- So sánh JSON/text serialization bằng chuỗi khi thứ tự key hoặc metadata không có hợp đồng xác định.

Mục tiêu của bài học là nhận diện các hành vi **được cam kết**, **không được cam kết** và **được quy định theo một điều kiện cụ thể**; từ đó thiết kế code và test sao cho kết quả không phụ thuộc vào chi tiết implementation tình cờ.

## 2. Ba lớp hợp đồng cần phân biệt

### 2.1. Hành vi được đặc tả bảo đảm

Một API có thể đưa ra cam kết rõ ràng về thứ tự hoặc tác dụng quan sát được. Ví dụ:

- `List` là collection có thứ tự, các phần tử có vị trí theo index.
- `LinkedHashMap` mặc định duy trì thứ tự chèn khi lặp, trong khi có thể cấu hình chế độ access-order.
- `TreeMap` lặp qua entry theo thứ tự khóa do natural ordering hoặc comparator xác định.
- Một ordered stream khi được thu về list bằng những operation giữ encounter order sẽ có thứ tự tương ứng.

Khi phụ thuộc vào những cam kết này, mã ứng dụng có căn cứ để yêu cầu implementation mới tiếp tục tuân thủ. Nếu behavior đổi trái đặc tả, đó có thể là regression của implementation hoặc do một điều kiện hợp đồng không còn thỏa mãn.

### 2.2. Hành vi không được đặc tả cam kết

“Không được bảo đảm” không có nghĩa mỗi lần chạy nhất thiết sẽ ngẫu nhiên. Một implementation có thể lặp qua các phần tử theo một thứ tự rất ổn định trong nhiều năm, nhưng vẫn được quyền thay đổi cấu trúc nội bộ, kích thước bảng, hash distribution hoặc chiến lược tối ưu hóa.

Ví dụ `HashMap` có thể tình cờ trả khóa theo thứ tự tăng dần với một tập `Integer` đơn giản trong một phiên bản JDK. Kết quả đó **không tạo thành hợp đồng**. Thay key, thay capacity, thêm phần tử hoặc đổi JDK có thể làm thứ tự khác đi.

Quy tắc thực hành: **Khi tài liệu API không hứa thứ tự, đừng suy diễn thứ tự từ một output mẫu.**

### 2.3. Hành vi chỉ được bảo đảm khi đáp ứng điều kiện

Một số API có hợp đồng có điều kiện:

- `Stream.findFirst()` trả phần tử đầu theo **encounter order nếu stream có encounter order**. Nếu nguồn unordered, khái niệm “đầu tiên” không cung cấp một lựa chọn có ý nghĩa ổn định.
- `Stream.forEachOrdered()` tuân thủ encounter order khi stream có order đó; nó không tự tạo ra order cho nguồn unordered.
- `Collections.sort(...)` hoặc `List.sort(...)` dựa trên comparator; kết quả có thể không đủ xác định nếu comparator không phân biệt hai đối tượng mà nghiệp vụ cần xếp thứ tự riêng.
- `LinkedHashMap` bảo đảm thứ tự theo cơ chế của nó, nhưng khi bật **access-order**, thao tác đọc có thể thay đổi thứ tự lặp.

Khi review migration, phải ghi rõ điều kiện nào tạo ra cam kết, không chỉ ghi “có thứ tự” hoặc “không có thứ tự”.

## 3. Một số khái niệm cần hiểu chính xác

**Iteration order** là thứ tự phần tử được trả về bởi `Iterator` hoặc vòng lặp `for-each`.

**Encounter order** trong Stream API là thứ tự mà pipeline nhận phần tử từ source và các intermediate operations, nếu source/pipeline có định nghĩa một thứ tự như vậy.

**Insertion order** là thứ tự các phần tử được thêm lần đầu, thường gặp ở `LinkedHashMap` và `LinkedHashSet` với cấu hình thông thường.

**Access order** là thứ tự được cập nhật theo các lần truy cập, có thể được cấu hình trong `LinkedHashMap`.

**Sorted order** là thứ tự do natural ordering hoặc `Comparator` xác định, như trong `TreeMap` hoặc `TreeSet`.

**Execution order** là thứ tự các thao tác, callback hoặc side effect thật sự diễn ra. Nó không phải lúc nào cũng trùng iteration order, đặc biệt trong môi trường đa luồng hoặc xử lý bất đồng bộ.

**Determinism** là tính xác định: cùng đầu vào và cùng điều kiện hợp đồng sẽ cho kết quả quan sát được giống nhau. Một thuật toán có thể xử lý bằng nhiều thứ tự nội bộ khác nhau nhưng vẫn tạo đầu ra xác định, hoặc ngược lại.

**Behavioral compatibility** là khả năng giữ nguyên những kết quả và tác dụng quan sát được mà consumer có quyền dựa vào. Binary compatibility chỉ cho thấy bytecode có thể liên kết, không bảo đảm hành vi thuộc nhóm này.

## 4. Bảng so sánh các collection Java thường gặp

| Cấu trúc | Hợp đồng iteration/order | Lưu ý khi migration |
| --- | --- | --- |
| `ArrayList` | Duy trì thứ tự phần tử theo vị trí trong list | Index và thứ tự có ý nghĩa |
| `LinkedList` | Duy trì thứ tự phần tử của list | Không nhầm “có thứ tự” với “đã sort” |
| `HashSet` | Không bảo đảm iteration order | Không mặc định giữ thứ tự thêm |
| `LinkedHashSet` | Duy trì thứ tự chèn theo cơ chế của collection | Không tự sắp theo giá trị |
| `TreeSet` | Các phần tử được xếp theo natural ordering/comparator | Comparator còn quyết định phần tử nào được coi là trùng |
| `HashMap` | Không bảo đảm thứ tự key, entry hoặc value | Output có thể đổi khi cấu trúc hash thay đổi |
| `LinkedHashMap` | Mặc định insertion-order; có thể chọn access-order | Truy cập có thể đổi thứ tự nếu access-order bật |
| `TreeMap` | Các entry được duyệt theo thứ tự khóa | Comparator ảnh hưởng cả điều kiện đồng nhất khóa |
| `ConcurrentHashMap` | Không bảo đảm iteration order | Iterator weakly consistent, không tạo snapshot nguyên tử |
| `CopyOnWriteArrayList` | Có thứ tự list; iterator dùng snapshot của mảng tại thời điểm tạo | Không thấy các thay đổi sau khi iterator được tạo |
| `PriorityQueue` | `poll()` trả phần tử ưu tiên cao nhất theo comparator/natural order | `iterator()` không có thứ tự ưu tiên được bảo đảm |
| `List.of(...)` | Duy trì thứ tự phần tử truyền vào | List không chỉnh sửa được qua API mutation |
| `Set.of(...)` | Không bảo đảm iteration order | Không chấp nhận phần tử `null` hoặc trùng nhau |
| `Map.of(...)` | Không bảo đảm iteration order | Không chấp nhận key/value `null` hoặc key trùng |

Không nên nhìn một output và suy ra rằng mọi collection trong bảng hoạt động như nhau. Bảng này chỉ tóm tắt hợp đồng phổ biến; còn phải xem từng overload, wrapper và điều kiện cụ thể của API.

### 4.1. `HashMap` không phải `LinkedHashMap`

~~~java
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.Map;

Map<String, Integer> unordered = new HashMap<>();
unordered.put("third", 3);
unordered.put("first", 1);
unordered.put("second", 2);

for (String key : unordered.keySet()) {
    System.out.println(key);
}
// Không cam kết sẽ in theo thứ tự third, first, second.

Map<String, Integer> insertionOrdered = new LinkedHashMap<>();
insertionOrdered.put("third", 3);
insertionOrdered.put("first", 1);
insertionOrdered.put("second", 2);

for (String key : insertionOrdered.keySet()) {
    System.out.println(key);
}
// Theo thứ tự chèn: third, first, second.
~~~

Với `HashMap`, việc một phiên bản JDK đang cho ra thứ tự đẹp mắt không làm nó trở thành `LinkedHashMap`. Không nên viết test kỳ vọng một thứ tự cụ thể cho `HashMap.keySet()`, `entrySet()` hoặc `values()`.

### 4.2. `LinkedHashMap` có thể ở chế độ access-order

~~~java
import java.util.LinkedHashMap;
import java.util.Map;

Map<String, Integer> cache = new LinkedHashMap<>(
        16, 0.75f, true); // accessOrder = true

cache.put("a", 1);
cache.put("b", 2);
cache.put("c", 3);

cache.get("a");

System.out.println(cache.keySet()); // [b, c, a]
~~~

Trong chế độ access-order, việc truy cập một entry có thể làm nó chuyển về cuối thứ tự. Đây là cơ sở cho một số cache kiểu least-recently-used, nhưng có thể gây ngạc nhiên nếu consumer cho rằng map luôn giữ insertion-order. Đặc biệt, cần tránh sửa cấu trúc hoặc thay đổi order bất ngờ trong lúc iterator đang hoạt động.

### 4.3. `TreeMap` là sorted map, không phải insertion-ordered map

~~~java
import java.util.Map;
import java.util.TreeMap;

Map<String, Integer> byKey = new TreeMap<>();
byKey.put("z", 1);
byKey.put("a", 2);
byKey.put("m", 3);

System.out.println(byKey.keySet()); // [a, m, z]
~~~

Thứ tự đến từ natural ordering của key `String`, không phải thứ tự chèn. Nếu dùng comparator khác, thứ tự cũng khác. Việc thêm case-insensitive comparator hoặc cách normalize key có thể làm một số khóa trở nên tương đương theo comparator, gây thay đổi cả số lượng entry.

## 5. `HashMap` và `HashSet`: thứ tự có thể ổn định nhưng không phải hợp đồng

### 5.1. Tại sao không thể suy luận từ cách hash hiện tại?

`HashMap` tổ chức dữ liệu theo hash bucket và cơ chế quản lý nội bộ. Iteration order có thể chịu ảnh hưởng bởi hash code, capacity, resize, tập key, va chạm hash và implementation của JDK. Một vài tập key làm iteration order trông có quy luật, nhưng đó chỉ là kết quả của cấu trúc nội bộ.

Không viết những đoạn như:

~~~java
Map<Integer, String> map = new HashMap<>();
for (int i = 0; i < 10; i++) {
    map.put(i, "value-" + i);
}

// Sai nếu coi quan sát này là hợp đồng:
// "keySet() luôn trả 0, 1, 2, ..., 9"
~~~

Việc chạy thử nhiều lần và nhận cùng thứ tự chỉ chứng minh điều đã quan sát trong các lần thử, không chứng minh Java cam kết kết quả đó.

### 5.2. `HashSet` dựa trên cấu trúc hash, không giữ thứ tự chèn

~~~java
Set<String> tags = new HashSet<>();
tags.add("backend");
tags.add("mobile");
tags.add("security");

for (String tag : tags) {
    System.out.println(tag);
}
~~~

Không được coi thứ tự console là thứ tự nhập. Nếu yêu cầu là **lặp theo thứ tự thêm**, hãy dùng `LinkedHashSet`. Nếu yêu cầu là **sắp theo giá trị**, dùng `TreeSet` hoặc sort list theo comparator.

### 5.3. Không thể khôi phục “thứ tự chèn gốc” từ một map không có hợp đồng đó

Một lỗi migration phổ biến:

~~~java
Map<String, Integer> source = new HashMap<>();
// ... source đã được điền dữ liệu từ trước.

Map<String, Integer> copied = new LinkedHashMap<>(source);
~~~

`copied` sẽ duy trì **thứ tự mà nó nhận được khi lặp nguồn**, nhưng `source` không cam kết thứ tự đó. Việc copy sau cùng không biến một lịch sử chèn đã bị mất thành thông tin có thể khôi phục.

Nếu thứ tự gốc có ý nghĩa, phải dùng collection có order từ lúc thu thập dữ liệu hoặc lưu một trường order/sequence rõ ràng.

## 6. Collection bất biến cũng không đồng nghĩa có thứ tự

Từ Java 9, có thể tạo collection gọn bằng các factory:

~~~java
List<String> steps = List.of("validate", "charge", "notify");
Set<String> roles = Set.of("reader", "writer", "admin");
Map<String, Integer> priority = Map.of(
        "high", 1,
        "normal", 2,
        "low", 3);
~~~

Các điều cần phân biệt:

- `List.of(...)` duy trì thứ tự phần tử khi tạo list.
- `Set.of(...)` không cam kết iteration order.
- `Map.of(...)` không cam kết iteration order của entry/key/value.
- Những collection này không hỗ trợ thao tác thêm/xóa/sửa trực tiếp.
- `Set.of(...)` không cho phần tử trùng hoặc `null`; `Map.of(...)` không cho key trùng, key `null` hay value `null`.

Việc đổi:

~~~java
Map<String, Integer> result = new LinkedHashMap<>();
// ...
~~~

sang:

~~~java
Map<String, Integer> result = Map.of(
        "high", 1, "normal", 2, "low", 3);
~~~

không chỉ thay mutability. Nó có thể bỏ luôn bảo đảm về order. Consumer dùng `result.keySet()` để dựng UI sẽ không còn cơ sở dựa vào thứ tự được biểu diễn trong source.

### 6.1. `copyOf` và wrapper không tự “chuẩn hóa” thứ tự

`List.copyOf(collection)` tạo list không sửa được và bảo toàn thứ tự lặp của collection đầu vào tại thời điểm copy. Nếu nguồn là `HashSet`, list thu được chỉ phản ánh một iteration không được nguồn cam kết.

`Set.copyOf(...)` và `Map.copyOf(...)` không cung cấp hợp đồng duy trì insertion-order của nguồn. `Collections.unmodifiableMap(...)` có thể giữ cách lặp của map được bọc, nhưng chỉ ngăn thay đổi **qua wrapper**, không tự biến một `HashMap` thành ordered map và không ngăn thay đổi nếu code khác vẫn giữ reference đến map gốc.

Một collection unmodifiable không nhất thiết là snapshot bất biến của dữ liệu nguồn; cần xem API tạo collection là copy hay view.

## 7. `PriorityQueue`: độ ưu tiên không bằng thứ tự iterator

`PriorityQueue` được thiết kế để truy cập phần tử ở đầu queue theo natural ordering hoặc comparator. Nó không cam kết iterator sẽ duyệt toàn bộ phần tử theo thứ tự ưu tiên.

~~~java
import java.util.PriorityQueue;

PriorityQueue<Integer> queue = new PriorityQueue<>();
queue.add(30);
queue.add(10);
queue.add(20);

for (Integer value : queue) {
    System.out.println(value);
}
// Không cam kết in 10, 20, 30.
~~~

Nếu cần **tiêu thụ theo ưu tiên**, dùng `poll()`:

~~~java
while (!queue.isEmpty()) {
    System.out.println(queue.poll());
}
// Theo thứ tự ưu tiên của comparator/natural ordering.
~~~

Lưu ý `poll()` làm thay đổi queue. Nếu cần báo cáo không phá dữ liệu, copy queue rồi poll bản copy, hoặc chuyển phần tử sang list và sort:

~~~java
List<Integer> sorted = new ArrayList<>(queue);
sorted.sort(Integer::compareTo);
~~~

Nếu nhiều phần tử có cùng mức ưu tiên, một priority queue thông thường không cung cấp tie-breaker theo thứ tự chèn. Muốn thứ tự xác định, cần comparator bổ sung một khóa riêng như sequence number.

## 8. Stream API: encounter order và execution order

### 8.1. Nguồn stream quyết định nhiều điều

~~~java
List<String> list = List.of("c", "a", "b");
List<String> fromList = list.stream()
        .map(String::toUpperCase)
        .toList();
// [C, A, B] vì list có encounter order.

Set<String> set = new HashSet<>(list);
List<String> fromSet = set.stream()
        .map(String::toUpperCase)
        .toList();
// Không có cam kết là [C, A, B].
~~~

`Stream.toList()` (Java 16+) tạo list kết quả theo encounter order của stream **nếu stream có encounter order**. Nó không tự tạo thứ tự có ý nghĩa cho nguồn unordered. Ngoài ra, list trả về từ `Stream.toList()` không cho thao tác mutation; migration từ `collect(Collectors.toList())` có thể tác động tới consumer từng sửa list kết quả.

### 8.2. `forEach` và `forEachOrdered`

~~~java
List<Integer> numbers = List.of(1, 2, 3, 4, 5);

numbers.parallelStream()
        .forEach(System.out::println);
// Không bảo đảm thứ tự side effect theo 1, 2, 3, 4, 5.
~~~

Nếu cần side effects theo encounter order:

~~~java
numbers.parallelStream()
        .forEachOrdered(System.out::println);
// Tôn trọng encounter order của stream.
~~~

`forEachOrdered` không có nghĩa mọi action sẽ chạy trong cùng một thread hay hoàn toàn tuần tự như code ứng dụng tự viết. Nó bảo đảm thứ tự tương ứng theo contract của API; các giả định về thread identity, lock hoặc hiệu năng vẫn cần xem xét.

Khi side effect phải đúng thứ tự và không có lợi ích song song rõ ràng, pipeline tuần tự thường đơn giản hơn:

~~~java
numbers.stream().forEachOrdered(System.out::println);
~~~

### 8.3. `findFirst()`, `findAny()` và `unordered()`

~~~java
String first = names.stream().findFirst().orElseThrow();
String any = names.parallelStream().findAny().orElseThrow();
~~~

`findFirst()` có nghĩa đầu tiên theo encounter order khi order tồn tại; `findAny()` được phép chọn một phần tử bất kỳ nhằm tạo cơ hội tối ưu, đặc biệt trong stream song song. Đổi từ `findFirst()` sang `findAny()` có thể làm thay đổi kết quả, dù cả hai trả về `Optional<T>`.

`unordered()` là lời tuyên bố rằng pipeline không cần giữ yêu cầu encounter order. Không nên thêm `unordered()` chỉ để tăng hiệu năng nếu đầu ra phục vụ pagination, hiển thị hay sự kiện có thứ tự.

### 8.4. `sorted()` và tính ổn định

`Stream.sorted()` sắp xếp theo natural ordering; `sorted(comparator)` dùng comparator chỉ định. Với ordered stream, sort có tính ổn định; với unordered stream, không có cùng bảo đảm giữ thứ tự tương đối giữa những phần tử được xem là bằng nhau theo comparator.

Nếu hai đối tượng cùng `priority` nhưng cần thứ tự ổn định, thêm tie-breaker:

~~~java
Comparator<Task> order = Comparator
        .comparingInt(Task::priority)
        .thenComparing(Task::id);

List<Task> sorted = tasks.stream()
        .sorted(order)
        .toList();
~~~

Điều kiện là `id` phải có ý nghĩa ổn định và có khả năng phân biệt các task khi cần. Comparator cần thống nhất với mục tiêu nghiệp vụ; một comparator có nhiều phần tử được xem là bằng nhau chưa chắc tạo output xác định nếu nguồn không có thứ tự.

## 9. Collectors và cấu trúc dữ liệu kết quả

### 9.1. `Collectors.toSet()` không hứa giữ thứ tự

~~~java
Set<String> names = users.stream()
        .map(User::name)
        .collect(Collectors.toSet());
~~~

Không nên giả định set này giữ thứ tự user trong stream. Nếu cần collection có thứ tự chèn theo encounter order của nguồn, chỉ rõ supplier:

~~~java
Set<String> names = users.stream()
        .map(User::name)
        .collect(Collectors.toCollection(LinkedHashSet::new));
~~~

Nếu yêu cầu sort theo giá trị:

~~~java
Set<String> names = users.stream()
        .map(User::name)
        .collect(Collectors.toCollection(TreeSet::new));
~~~

Lưu ý comparator/natural ordering của `TreeSet` có thể ảnh hưởng tới việc các phần tử được coi là trùng. Nếu xử lý ngôn ngữ tự nhiên, comparator của `String` không tự tương đương cách sắp xếp theo locale của người dùng.

### 9.2. `Collectors.toMap()` không cam kết loại map hoặc thứ tự

~~~java
Map<String, User> byId = users.stream()
        .collect(Collectors.toMap(User::id, Function.identity()));
~~~

Không nên dựa vào thứ tự `byId.entrySet()`. Nếu cần thứ tự key theo lần xuất hiện đầu trong một **stream có encounter order**, có thể chỉ định map factory và merge function:

~~~java
Map<String, User> byId = users.stream()
        .collect(Collectors.toMap(
                User::id,
                Function.identity(),
                (first, duplicate) -> first,
                LinkedHashMap::new));
~~~

Nếu muốn sắp theo key, có thể dùng `TreeMap::new` thay cho `LinkedHashMap::new`, miễn là key và comparator phù hợp.

### 9.3. `groupingBy` và thứ tự nhóm

~~~java
Map<String, List<Order>> groups = orders.stream()
        .collect(Collectors.groupingBy(Order::status));
~~~

Thứ tự các key của map nhóm không được suy ra từ thứ tự đơn hàng hoặc thứ tự enum status. Nếu muốn duy trì thứ tự các nhóm theo lần gặp đầu tiên trong một stream tuần tự có encounter order:

~~~java
Map<String, List<Order>> groups = orders.stream()
        .collect(Collectors.groupingBy(
                Order::status,
                LinkedHashMap::new,
                Collectors.toList()));
~~~

Nếu muốn báo cáo theo thứ tự nghiệp vụ `NEW` → `PAID` → `SHIPPED`, cách rõ nhất là biểu diễn thứ tự đó bằng danh sách quy định hoặc một comparator, không suy ra từ thứ tự group xuất hiện trong dữ liệu nguồn.

### 9.4. `Collectors.toList()` và tính mutability

Không nên giả định implementation cụ thể hoặc khả năng chỉnh sửa của list trả về từ `Collectors.toList()` trong mọi phiên bản/triển khai. Nếu cần list có thể chỉnh sửa, có thể chỉ định:

~~~java
List<String> mutable = stream.collect(
        Collectors.toCollection(ArrayList::new));
~~~

Nếu cần kết quả không chỉnh sửa được, nêu rõ ý định bằng API phù hợp, chẳng hạn `Stream.toList()` trên JDK hỗ trợ hoặc `Collectors.toUnmodifiableList()` khi điều kiện phần tử cho phép. Mutability và ordering là hai chiều hợp đồng độc lập.

## 10. Thread concurrency: iterator không phải snapshot có thứ tự

### 10.1. Fail-fast không phải một cơ chế đồng bộ

Iterator của một số collection như `ArrayList` và `HashMap` có cơ chế phát hiện sửa đổi cấu trúc không đúng cách và có thể ném `ConcurrentModificationException`. Tuy nhiên, cơ chế fail-fast mang tính **best effort**, không phải bảo đảm phát hiện mọi race condition.

~~~java
List<String> values = new ArrayList<>(List.of("a", "b", "c"));
for (String value : values) {
    if (value.equals("b")) {
        values.remove(value); // Không phải cách chỉnh sửa an toàn của vòng lặp.
    }
}
~~~

Trong vòng lặp cần xóa phần tử, có thể dùng `Iterator.remove()` khi iterator hỗ trợ, hoặc dùng API như `removeIf(...)` theo hợp đồng collection. Khi nhiều thread cùng sửa, cần concurrency strategy đúng, không lấy việc không thấy exception làm bằng chứng an toàn.

### 10.2. `ConcurrentHashMap` có weakly consistent iterator

`ConcurrentHashMap` cho phép nhiều thao tác đồng thời; iterator có thể quan sát một số thay đổi diễn ra khi đang lặp, nhưng không cung cấp một snapshot nguyên tử của toàn bộ map và không bảo đảm thứ tự.

~~~java
ConcurrentHashMap<String, Integer> counters = new ConcurrentHashMap<>();
counters.put("a", 1);
counters.put("b", 2);

for (Map.Entry<String, Integer> entry : counters.entrySet()) {
    System.out.println(entry);
}
~~~

Code này không nên dùng để tạo một báo cáo yêu cầu cả **snapshot nhất quán** lẫn **thứ tự ổn định**. Nếu nghiệp vụ cần hai thuộc tính đó, phải có cơ chế snapshot/locking/versioning phù hợp, sau đó sắp theo một khóa xác định.

### 10.3. `CopyOnWriteArrayList` có snapshot iterator

Với `CopyOnWriteArrayList`, iterator duyệt ảnh chụp mảng tại thời điểm tạo iterator, nên không tự phản ánh các phần tử thêm sau đó:

~~~java
CopyOnWriteArrayList<String> values =
        new CopyOnWriteArrayList<>(List.of("a", "b"));

Iterator<String> iterator = values.iterator();
values.add("c");

while (iterator.hasNext()) {
    System.out.println(iterator.next());
}
// Iterator này chỉ thấy a và b.
~~~

Snapshot iterator khác với weakly consistent iterator. Hai collection có thể đều tránh lỗi fail-fast trong tình huống trên nhưng có contract khác về phần tử được nhìn thấy.

### 10.4. Thứ tự completion không phải thứ tự submission

~~~java
List<CompletableFuture<Result>> futures = submitTasks();
~~~

Các task có thể hoàn thành theo thứ tự khác thứ tự tạo. Nếu đưa kết quả vào shared collection ngay khi hoàn thành, output có thể phản ánh completion order. Nếu cần kết quả theo input order, hãy lưu một index/sequence gắn với task và sắp lại hoặc thu theo thứ tự index đã được thiết kế.

Không nên dùng thời điểm thread được scheduler chạy làm một thứ tự nghiệp vụ mặc định. Scheduler, CPU, GC và I/O có thể thay đổi thứ tự completion mà không vi phạm API.

## 11. API liên quan file system: `Files.list` và `DirectoryStream`

Không nên giả định file được trả về theo tên, ngày sửa hay thứ tự trên disk:

~~~java
try (Stream<Path> paths = Files.list(directory)) {
    paths.forEach(System.out::println);
}
// Không cam kết theo tên file.
~~~

Nếu muốn tên file tăng dần:

~~~java
try (Stream<Path> paths = Files.list(directory)) {
    List<Path> sorted = paths
            .sorted(Comparator.comparing(
                    path -> path.getFileName().toString()))
            .toList();

    sorted.forEach(System.out::println);
}
~~~

`Files.list` trả stream gắn với resource hệ thống nên cần đóng bằng try-with-resources. Thứ tự duyệt từ file system không phải hợp đồng nghiệp vụ.

`Files.walk` có quy tắc duyệt cây theo độ sâu, nhưng không có nghĩa các entry trong cùng một directory được sắp theo tên. Nếu cần danh sách toàn cục có thứ tự xác định, phải xác định comparator và thu/sort theo yêu cầu. Khi có symlink hoặc cây thư mục thay đổi trong lúc duyệt, còn phải kiểm tra semantics và giới hạn của traversal.

Nếu tiêu chí là “file mới nhất”, không nên chỉ lấy `findFirst()` từ `Files.list`. Cần đọc metadata thời gian theo API phù hợp, xử lý trường hợp trùng timestamp và quy định tie-breaker; nếu file có thể thay đổi trong lúc scan, cần xem xét tính nhất quán.

## 12. Reflection và thứ tự thành viên class

Các API reflection như:

~~~java
Method[] methods = MyType.class.getDeclaredMethods();
Field[] fields = MyType.class.getDeclaredFields();
~~~

không cam kết trả mảng theo thứ tự khai báo trong source. Một framework lấy phương thức đầu tiên, hoặc serialize fields theo thứ tự reflection trả về, có thể tạo behavior phụ thuộc vào implementation JDK/compiler.

Nếu cần một thứ tự có ý nghĩa, phải quy định nó:

~~~java
Method[] methods = MyType.class.getDeclaredMethods();

Arrays.sort(methods,
        Comparator.comparing(Method::getName)
                .thenComparing(method -> Arrays.toString(
                        method.getParameterTypes())));
~~~

Đây chỉ là một comparator minh họa. Với overloaded methods, bridge/synthetic members, return type và type name, cần chọn khóa phân biệt phù hợp với mục tiêu. Nếu thứ tự là hợp đồng nghiệp vụ, một annotation `@Order`, danh sách cấu hình hoặc metadata rõ ràng thường tốt hơn suy ra từ tên reflection.

Tương tự, không nên dùng thứ tự `getDeclaredConstructors()` hoặc `getMethods()` để quyết định “constructor/method ưu tiên” nếu API không cung cấp contract đó.

### 12.1. Metadata và code generation

Các công cụ như ORM, serializer, mapper hoặc DI container có thể khám phá thành viên qua reflection. Khi nâng phiên bản JDK/framework, thứ tự được phát hiện có thể khác. Nếu code generator phụ thuộc thứ tự đó để tạo schema, request signature hoặc source, output có thể đổi mặc dù source model không đổi.

Giải pháp là công bố thứ tự qua một cấu trúc ổn định: property order annotation được framework hỗ trợ, schema thứ tự rõ ràng hoặc comparator xác định. Không sửa bằng cách hy vọng “reflection ở JDK cũ luôn trả theo source order”.

## 13. Dữ liệu database: không có `ORDER BY` thì không có thứ tự hàng được hứa hẹn

Một ứng dụng Java có thể đọc kết quả từ JDBC/JPA/Hibernate:

~~~sql
SELECT id, created_at, total
FROM orders;
~~~

Không có `ORDER BY`, SQL không bảo đảm thứ tự bản ghi, bất kể index hoặc execution plan hiện tại. Sau khi nâng driver, database, ORM hoặc thêm index, tập kết quả có thể giữ nguyên nhưng thứ tự khác.

Nếu API cần đơn hàng mới nhất trước:

~~~sql
SELECT id, created_at, total
FROM orders
ORDER BY created_at DESC, id ASC;
~~~

`id` là tie-breaker để phân biệt các bản ghi có cùng `created_at`, với điều kiện `id` là khóa ổn định và unique theo dữ liệu.

### 13.1. Pagination cần thứ tự xác định

Query kiểu:

~~~sql
SELECT id, created_at
FROM orders
LIMIT 20 OFFSET 20;
~~~

không đủ để định nghĩa trang thứ hai nếu không có order. Hậu quả có thể là bản ghi xuất hiện lại hoặc biến mất giữa các lần phân trang.

Ngay cả khi thêm `ORDER BY`, dữ liệu được thêm/xóa đồng thời giữa request vẫn có thể làm offset pagination trượt. Khi cần tính nhất quán mạnh hơn, xem xét snapshot transaction, cursor/keyset pagination hoặc contract phân trang tương ứng.

Khi chuyển ORM/framework, nên kiểm tra query thực tế, không chỉ method name. Việc repository trước đây “tình cờ trả theo ID” có thể là kết quả của execution plan chứ không phải cam kết.

## 14. JSON, serialization và kết quả dạng text

### 14.1. JSON array có thứ tự, JSON object không nên dùng thứ tự key làm nghiệp vụ

Ví dụ:

~~~json
{
  "items": ["A", "B", "C"],
  "metadata": {
    "name": "report",
    "version": 2
  }
}
~~~

Thứ tự phần tử trong array `items` có ý nghĩa khi protocol định nghĩa. Với các member của JSON object `metadata`, consumer không nên giả định order là thông tin nghiệp vụ chỉ vì serializer cũ ghi `name` trước `version`.

Một thư viện serialize `Map` có thể xuất field theo iteration order của map. Nếu map là `HashMap`, JSON text thu được có thể khác sau migration dù dữ liệu có cùng key/value.

Điều này đặc biệt ảnh hưởng khi:

- Lưu snapshot hoặc golden file dạng chuỗi thô.
- Hash nguyên JSON string làm cache key.
- Ký số trên byte representation không có bước canonicalization.
- Sinh diff hoặc cấu hình từ map không có order.

Nếu cần representation xác định, hãy dùng một canonical serialization được quy định rõ, hoặc sắp field trước khi sinh text theo schema. Không chỉ thay map thành `TreeMap` rồi cho rằng mọi kiểu dữ liệu lồng nhau, số thực, Unicode và null được chuẩn hóa đầy đủ.

### 14.2. `toString()` thường không phải giao thức lưu trữ

`Map.toString()` và nhiều `toString()` khác chủ yếu hỗ trợ debug. Nếu ứng dụng phân tích string đó để phục hồi dữ liệu, nó đang phụ thuộc vào cách trình bày có thể thay đổi.

Ví dụ không nên dùng làm định dạng dữ liệu bền vững:

~~~java
String saved = someMap.toString();
~~~

Thay vào đó, định nghĩa schema và serializer/deserializer công khai. Nếu dùng format cho log, không nên yêu cầu parser downstream phân tích chính xác thứ tự của những field vốn không có hợp đồng.

### 14.3. Reflection-based serializer

Nếu serializer tự duyệt `getDeclaredFields()` rồi ghi field theo iteration order, output có thể khác khi compiler hoặc runtime thay đổi. Quy định thứ tự field ở schema/annotation hoặc dùng encoder có canonical output khi thật sự cần định dạng xác định.

## 15. Thứ tự chuỗi, locale, timezone và các mặc định phụ thuộc môi trường

Một hành vi khác dễ bị nhầm là “mặc định Java sẽ giống nhau trên mọi nơi”. Một số API phụ thuộc cấu hình môi trường hoặc ngữ cảnh mà code không chỉ định rõ:

- `Locale.getDefault()` có thể ảnh hưởng format, case mapping và collator.
- `ZoneId.systemDefault()` có thể ảnh hưởng hiển thị thời gian.
- Charset mặc định của một số API/hệ thống cần xem xét theo phiên bản JDK và cấu hình runtime.
- Thứ tự file system, cấu hình hệ điều hành và native providers có thể khác giữa máy.

Với việc sắp xếp chuỗi cho người dùng, `String.compareTo` so sánh theo natural ordering của Java, không tự là cách sắp xếp chữ cái đúng theo mọi ngôn ngữ. Có thể dùng `Collator` khi nghiệp vụ yêu cầu quy tắc theo locale:

~~~java
Collator collator = Collator.getInstance(
        Locale.forLanguageTag("vi-VN"));

List<String> names = new ArrayList<>(inputNames);
names.sort(collator);
~~~

Comparator theo locale có thể xem hai chuỗi tương đương ở một mức so sánh. Nếu cần kết quả tuyệt đối xác định cho các trường hợp bằng nhau, thêm tie-breaker và quy định cách xử lý normalization/case.

Không mặc định rằng “đã gọi `sorted()`” là đủ cho mọi trường hợp. Cần biết sort theo quy tắc nào, locale gì, cách xử lý null và tie-breaker ra sao.

### 15.1. Quy tắc chọn khóa sort

Một comparator ổn định thường cần:

1. Trường nghiệp vụ chính, ví dụ `priority` hoặc `createdAt`.
2. Quy tắc xử lý `null` cho mỗi trường nếu có.
3. Tie-breaker ổn định, ví dụ ID unique.
4. Thứ tự tăng/giảm được công bố.
5. Chú ý comparator phù hợp với yêu cầu của `TreeMap`/`TreeSet` khi dùng nó để xác định key uniqueness.

Ví dụ:

~~~java
Comparator<Order> ordering =
        Comparator.comparing(
                Order::createdAt,
                Comparator.nullsLast(Comparator.reverseOrder()))
            .thenComparing(Order::id);

List<Order> result = orders.stream()
        .sorted(ordering)
        .toList();
~~~

Ở đây kết quả phụ thuộc vào hợp đồng `Order.id()` và `Order.createdAt()`. Nếu `id` có thể `null`, comparator cần quy tắc null riêng; nếu ID không unique, hãy bổ sung khóa phân biệt hoặc chấp nhận thứ tự những phần tử tương đương không có ý nghĩa.

## 16. Java 21 `SequencedCollection`: thể hiện order rõ hơn

Java 21 bổ sung họ API sequenced collections, gồm `SequencedCollection`, `SequencedSet` và `SequencedMap`, cho các cấu trúc có encounter order được định nghĩa rõ. Các API như `getFirst()`, `getLast()`, `reversed()` và các thao tác sequenced phù hợp giúp chương trình thể hiện ý định dùng thứ tự.

Ví dụ trên JDK 21+:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.SequencedCollection;

SequencedCollection<String> workflow =
        new ArrayList<>(List.of("validate", "charge", "notify"));

System.out.println(workflow.getFirst()); // validate
System.out.println(workflow.getLast());  // notify
System.out.println(workflow.reversed()); // view theo thứ tự ngược
~~~

Điểm quan trọng:

- Việc dùng API sequenced thể hiện contract về encounter order rõ hơn so với khai báo một `Collection` chung nếu order thực sự quan trọng.
- Không phải mọi collection đều có thứ tự; `HashSet`/`HashMap` không tự được biến thành ordered structures chỉ vì nâng JDK.
- `reversed()` biểu diễn view với encounter order đảo ngược; cần phân biệt view và snapshot nếu collection có thể bị thay đổi.
- Nếu target runtime là JDK thấp hơn 21, không thể dùng trực tiếp API mới mà không đổi mức Java hỗ trợ.

Khi tiến hóa API public, đổi kiểu trả về từ `Collection<T>` sang `SequencedCollection<T>` cần đánh giá source/binary compatibility. Dù ý định “giữ order” rõ hơn, việc thay descriptor vẫn có thể ảnh hưởng bytecode consumer đã biên dịch.

## 17. Khi nào cần sắp xếp, khi nào cần giữ nguyên?

Không phải yêu cầu nào cũng cần `sort()`. Cần phân loại mục đích:

| Nhu cầu | Lựa chọn phù hợp | Tránh |
| --- | --- | --- |
| Giữ thứ tự thêm | `ArrayList`, `LinkedHashSet`, `LinkedHashMap` | `HashSet`/`HashMap` |
| Sắp theo key/giá trị | `TreeMap`, `TreeSet`, `List.sort`, `Stream.sorted` | Tin vào thứ tự hash |
| Ưu tiên phần tử tiếp theo | `PriorityQueue.poll` | Dùng iterator của priority queue để yêu cầu sorted output |
| Duy trì thứ tự bước workflow | `List` hoặc model có sequence | Biểu diễn workflow bằng `Set` unordered |
| Xuất báo cáo xác định | Comparator có tie-breaker, schema rõ | Serialize `HashMap` theo thứ tự tình cờ |
| Trả tập kết quả không có order | `Set` với hợp đồng “unordered” rõ | Ghi snapshot test khóa chặt thứ tự không hứa |
| Xử lý song song không cần order | `parallelStream`/`unordered` khi đúng contract | Vẫn dùng `findFirst()`/side effect có order vô thức |
| Xử lý song song nhưng output phải có order | Giữ encounter order hoặc gom theo index rồi reorder | Lấy thứ tự completion làm thứ tự input |

Việc thay `HashMap` bằng `TreeMap` không phải lúc nào cũng “sửa lỗi order” vô hại: comparator có thể xem hai key khác nhau theo `equals` là tương đương, làm mất dữ liệu. Hãy chọn cấu trúc theo cả hợp đồng khóa, hiệu năng và semantics.

## 18. Thiết kế kiểm thử không phụ thuộc vào thứ tự tình cờ

### 18.1. Kiểm tra đúng hợp đồng của kết quả

Nếu API trả **tập phần tử**, test nên so sánh theo tập:

~~~java
Set<String> expected = Set.of("reader", "writer");
Set<String> actual = permissionService.roles();

assertEquals(expected, actual);
~~~

Nếu API trả **list có thứ tự được hứa**, test nên kiểm tra thứ tự:

~~~java
List<String> expected =
        List.of("validate", "charge", "notify");

assertEquals(expected, workflowService.steps());
~~~

Không chuyển mọi test sang so sánh `Set` để dễ pass. Nếu thứ tự là hợp đồng, bỏ kiểm tra order sẽ che regression. Ngược lại, không khóa cứng thứ tự `HashSet` trong snapshot nếu API không hứa order.

### 18.2. Test property thay vì chỉ test một output

Có thể kiểm tra những tính chất như:

- Đầu ra chứa đúng phần tử/kết quả, không dư hoặc thiếu.
- Với API ordered, từng cặp phần tử liên tiếp tuân thủ comparator.
- Với pagination, không có bản ghi lặp trong một snapshot đã định nghĩa.
- Với grouping, các phần tử thuộc đúng nhóm, bất kể thứ tự key của map nếu order không phải hợp đồng.
- Với side effect, thứ tự callback được kiểm tra nếu API hứa order; nếu không hứa, chỉ kiểm tra điều kiện nghiệp vụ thật.

Ví dụ kiểm tra list có thứ tự theo comparator:

~~~java
for (int index = 1; index < actualOrders.size(); index++) {
    Order previous = actualOrders.get(index - 1);
    Order current = actualOrders.get(index);
    assertTrue(ordering.compare(previous, current) <= 0);
}
~~~

Test cần fixture có phần tử trùng khóa sort chính, nhiều size/capacity và dữ liệu biên. Nếu chỉ có hai phần tử hoặc tất cả key unique theo trường đầu tiên, test có thể không phát hiện thiếu tie-breaker.

### 18.3. Test trên nhiều JDK không đủ để “chứng minh được bảo đảm”

Chạy cùng một test trên JDK 17 và JDK 21 hữu ích để phát hiện regression, nhưng nếu một hành vi không được API cam kết thì việc nó giống nhau trên hai JDK **không tạo ra cam kết**.

Test nên dựa trên đặc tả. Nếu cần output ổn định, hãy tạo determinism trong code bằng collection/ordering explicit, không dựa vào việc môi trường test vô tình cho một kết quả lặp lại.

## 19. Kỹ thuật điều tra khi migration làm đổi thứ tự

### 19.1. Truy theo nguồn và từng phép biến đổi

Khi nhận báo cáo “Java mới đảo thứ tự”, đặt các câu hỏi:

1. Kết quả được tạo từ `List`, `Set`, `Map`, `Stream`, SQL hay file system?
2. Nguồn có contract ordering không? Nếu có, contract là gì?
3. Có bước `collect(toSet())`, `toMap`, `groupingBy`, `Map.copyOf` hoặc chuyển sang `HashMap`/`HashSet` không?
4. Có chuyển từ sequential sang parallel stream, hoặc từ `forEachOrdered` sang `forEach` không?
5. Có comparator/tie-breaker và null handling không?
6. Có code sinh JSON/log từ map hoặc reflection không?
7. Consumer đang yêu cầu thứ tự hay chỉ so sánh text snapshot?
8. Có thay đổi data volume, key distribution, DB query planner hay index không?

Thay vì sửa từ cuối bằng một `sort()` không rõ tiêu chí, hãy xác định **điểm đầu tiên nơi contract về thứ tự bị mất**. Nếu yêu cầu là insertion-order, phải giữ order ngay từ đầu; sort alphabetically ở cuối không tái tạo được order đó.

### 19.2. Mẫu sơ đồ tìm nguyên nhân

~~~mermaid
flowchart TD
    A[Thứ tự đầu ra thay đổi] --> B{API có cam kết order?}
    B -->|Có| C[Kiểm tra source, comparator, transforms]
    B -->|Không| D[Xác định consumer có thật sự cần order]
    C --> E{Điểm nào làm mất order?}
    E --> F[Sửa ở đúng điểm chuyển đổi]
    D --> G{Có yêu cầu nghiệp vụ về order?}
    G -->|Có| H[Thiết kế order rõ bằng collection hoặc sort]
    G -->|Không| I[Sửa test hoặc consumer để không phụ thuộc order]
    F --> J[Contract tests và rollout]
    H --> J
    I --> J
~~~

Sơ đồ không thay việc phân tích từng API; nó giúp phân biệt lỗi implementation thật với trường hợp ứng dụng đang dựa vào hành vi chưa từng được cam kết.

### 19.3. Nhật ký phân tích tối thiểu

Một báo cáo nên ghi:

~~~text
Observed behavior:
  report keys changed from [A, B, C] to [B, C, A]
Baseline:
  JDK 17 + framework vOld
Target:
  JDK 21 + framework vNew
Data source:
  HashMap<String, ReportEntry>
API contract:
  HashMap iteration order unspecified
Consumer assumption:
  CSV writer used map.entrySet() as output order
Decision:
  Define CSV sorting by reportOrder ASC, id ASC
Evidence:
  contract test on sorted output, integration test with duplicate reportOrder
~~~

Kết luận đúng không phải “HashMap mới bị lỗi”; kết luận là CSV writer thiếu một bước sắp xếp theo hợp đồng nghiệp vụ. Nếu khách hàng thực sự yêu cầu “theo thứ tự nhập”, giải pháp phải giữ insertion-order từ lúc ghi dữ liệu thay vì tự đặt một sort mới.

## 20. Tương thích hành vi và phát hành thư viện

Khi thư viện thay implementation nhưng giữ public signatures, cần xem có hành vi nào đang được bên dùng coi là ổn định:

- Giá trị trả về có cùng tập phần tử không?
- Có thứ tự nào được hứa trong Javadoc hay API contract không?
- Thứ tự có ảnh hưởng việc tính hash/cache key, signature hoặc serialization không?
- Các tác dụng phụ xảy ra theo cùng thứ tự và số lần cần thiết không?
- Có thay đổi từ eager sang lazy hoặc sequential sang concurrent không?
- Có chuyển result sang wrapper unmodifiable/snapshot không?
- Có xuất hiện default locale/timezone/platform dependence mới không?

Nếu order được cam kết, việc đổi từ một ordered collection sang unordered collection mà không sort lại là thay đổi behavior cần được xem như regression/breaking change. Nếu order **không** được cam kết, dự án vẫn nên công bố khác biệt có khả năng ảnh hưởng consumer trong migration guide, nhất là khi hệ sinh thái có nhiều client lâu năm.

### 20.1. Khi API thật sự cần order, thể hiện trong hợp đồng

Ví dụ API:

~~~java
/**
 * Returns a snapshot of all matching orders sorted by
 * createdAt descending, then orderId ascending.
 * Never returns null.
 */
List<Order> findOrders(String customerId);
~~~

Javadoc cho biết rõ tiêu chí và tie-breaker. Consumer có thể dùng thứ tự một cách hợp pháp, test có thể bảo vệ đúng yêu cầu. Nếu API chỉ trả tập không thứ tự, cũng nên ghi rõ:

~~~java
/**
 * Returns the matching roles. Iteration order is unspecified.
 */
Set<String> rolesFor(String userId);
~~~

Đối với API đã có consumer, việc thay đổi contract phải được xem xét source/binary/behavioral compatibility. Ví dụ đổi kiểu trả về từ `Set<T>` sang `List<T>` để hứa order có thể đổi method descriptor, ảnh hưởng client đã biên dịch. Thêm method mới như `rolesInDisplayOrder()` và giữ method cũ có thể là lộ trình ít rủi ro hơn.

### 20.2. Không biến chi tiết implementation thành lời hứa không cần thiết

Nếu nghiệp vụ không cần thứ tự, đừng hứa “insertion-order” chỉ vì một bản hiện dùng `LinkedHashMap`. Việc công bố quá nhiều chi tiết có thể hạn chế khả năng tối ưu trong tương lai.

Hợp đồng tốt phải đủ mạnh cho consumer làm đúng công việc, nhưng không khóa implementation vào những đặc điểm không cần thiết.

## 21. Quy trình migration để tránh phụ thuộc hành vi không được cam kết

### Bước 1: Khảo sát điểm phát sinh output

Lập danh sách API xuất collection, stream, file listing, reflection metadata, query result, serialized text và event. Xác định các đường code consumer phụ thuộc thứ tự bằng cách chọn phần tử đầu/cuối, dùng index hoặc so sánh text.

### Bước 2: Đọc contract của từng API

Đối chiếu Javadoc, đặc tả Java và hợp đồng của framework/dependency. Phân loại thành:

- Order được bảo đảm.
- Order có điều kiện (nguồn ordered, comparator, access-order).
- Order không được bảo đảm.
- Hành vi khác không được bảo đảm, ví dụ snapshot, timing, mutability hoặc execution thread.

### Bước 3: Chọn quy tắc nghiệp vụ riêng

Nếu cần insertion order, dùng cấu trúc giữ thứ tự từ nguồn. Nếu cần sort, định nghĩa comparator và tie-breaker. Nếu cần snapshot, tạo snapshot có cách đồng bộ phù hợp. Nếu không cần order, loại bỏ những giả định trong consumer và test.

### Bước 4: Tách thay đổi implementation khỏi thay đổi hợp đồng

Không gộp đổi JDK/framework, đổi collection, đổi serialization và đổi tiêu chí sort trong cùng một thay đổi lớn khi có thể tách. Điều này giúp xác định nguyên nhân nếu behavior khác.

### Bước 5: Test cả behavior và migration

Chạy test theo hợp đồng đã viết, có dữ liệu trùng khóa chính, số phần tử đủ lớn để phát sinh resize, trường hợp null và concurrent updates nếu liên quan. Test trên runtime mục tiêu, nhưng không dùng việc output giống nhau để thay thế cam kết API.

### Bước 6: Công bố và triển khai

Release note phải mô tả thay đổi behavior thực sự có ý nghĩa, không chỉ ghi “upgrade Java”. Nếu kết quả JSON/CSV/protocol trước đây dựa vào thứ tự không được hứa nhưng consumer thực tế đã phụ thuộc, cần migration plan, phối hợp downstream và hỗ trợ chuyển tiếp khi cần.

### Bước 7: Theo dõi sau phát hành

Quan sát số lỗi xử lý message, checksum/signature mismatch, CSV diff, lỗi pagination, báo cáo không ổn định và exception liên quan dữ liệu/collection. Khi có dấu hiệu regression, điều tra từ source và contract thay vì mặc định JVM mới sai.

## 22. Những sai lầm thường gặp

**“Chạy một nghìn lần đều cùng order, vậy Java bảo đảm order.”** Sai. Tính ổn định quan sát được không thay thế Javadoc hoặc đặc tả API.

**“HashMap luôn sắp theo hashCode tăng dần.”** Sai. Không có hợp đồng đó; không nên xây thuật toán trên cấu trúc bucket nội bộ.

**“Map.of viết key theo thứ tự nào thì iterator trả đúng thứ tự đó.”** Sai. `Map.of` không hứa iteration order.

**“Copy HashMap sang LinkedHashMap sẽ lấy lại thứ tự chèn.”** Sai. Bạn chỉ sao chép thứ tự lặp của nguồn vào thời điểm copy.

**“PriorityQueue là sorted collection, nên iterator đã sorted.”** Sai. `poll()` và `iterator()` có hợp đồng khác nhau.

**“Nếu dùng parallelStream, `forEach` vẫn theo thứ tự list.”** Sai. Cần phân biệt encounter order và execution order; dùng `forEachOrdered` khi contract yêu cầu.

**“Đã gọi `sorted()` nên mọi phần tử bằng nhau có thứ tự xác định.”** Chưa chắc. Cần xem encounter order, tính ổn định và tie-breaker của comparator.

**“Files.list đã theo tên trên máy Linux của tôi.”** Đó không phải cam kết của `Files.list`; hãy sort rõ nếu cần.

**“Reflection trả method theo thứ tự khai báo.”** Không có cam kết như vậy cho các API reflection liệt kê thành viên phổ biến.

**“ResultSet luôn theo primary key vì bảng có index.”** SQL không hứa row order nếu không có `ORDER BY`.

**“JSON object key order là một phần dữ liệu nghiệp vụ.”** Không nên coi đó là hợp đồng chung; nếu ký số hoặc hash, cần canonicalization phù hợp.

**“Thêm `TreeMap` là luôn an toàn.”** Comparator có thể thay đổi khái niệm key equality và vô tình làm mất entry.

**“ConcurrentHashMap iterator thấy dữ liệu đầy đủ của một thời điểm.”** Iterator weakly consistent không phải atomic snapshot.

**“Đã test trên hai phiên bản JDK nên order đó được bảo đảm.”** Test chứng minh những gì xảy ra trong lần thử, không tạo hợp đồng mới cho API.

## 23. Checklist cho thay đổi có liên quan thứ tự và behavior mặc định

- [ ] Đã xác định thứ tự nào là yêu cầu nghiệp vụ thực sự.
- [ ] Đã đọc contract của nguồn dữ liệu và container/collection dùng để lặp.
- [ ] Không dựa vào `HashMap`/`HashSet`/`Map.of`/`Set.of` khi cần insertion/sorted order.
- [ ] Nếu dùng `LinkedHashMap` đã biết rõ insertion-order hay access-order.
- [ ] Nếu dùng `TreeMap`/`TreeSet` đã xem comparator có làm hai khóa hợp lệ bị coi là trùng không.
- [ ] Nếu dùng `PriorityQueue` không lấy iteration order làm thứ tự ưu tiên.
- [ ] Nếu dùng Stream đã xác định encounter order và phân biệt `forEach` với `forEachOrdered`.
- [ ] Nếu thu về Set/Map đã chỉ định collection factory khi cần order.
- [ ] Nếu sort đã có comparator, null policy và tie-breaker phù hợp.
- [ ] Nếu dùng concurrent collection đã xác định snapshot/weak consistency và concurrency policy.
- [ ] Nếu dùng `Files.list`/reflection/SQL đã sắp rõ khi output cần deterministic.
- [ ] Nếu serialize JSON/CSV đã quy định order thực sự cần thiết và canonicalization khi ký/hash.
- [ ] Nếu dùng locale/timezone/charset đã cấu hình những mặc định có ảnh hưởng nghiệp vụ.
- [ ] Test kiểm tra đúng contract, không khóa thứ tự tình cờ.
- [ ] Consumer inventory đã bao gồm các downstream dựa vào thứ tự output.
- [ ] Release notes phân biệt behavior được hứa và behavior vốn unspecified nhưng đã thay đổi.
- [ ] Rollout có giám sát lỗi pagination, serialization, signature và kết quả nghiệp vụ.

## 24. Tình huống tổng hợp: nâng JDK và thay framework tạo báo cáo

Giả sử một service nhận đơn hàng từ database, gom theo trạng thái rồi xuất CSV. Trước migration:

~~~java
Map<String, List<Order>> grouped = orders.stream()
        .collect(Collectors.groupingBy(Order::status));

for (Map.Entry<String, List<Order>> group : grouped.entrySet()) {
    writeCsvSection(group.getKey(), group.getValue());
}
~~~

Nhóm từng thấy các phần `NEW`, `PAID`, `SHIPPED` xuất đúng thứ tự đó. Sau khi nâng JDK/framework, báo cáo chuyển thành `PAID`, `SHIPPED`, `NEW`. Mã không lỗi compile và dữ liệu vẫn đủ.

### 24.1. Phân tích nguyên nhân

`groupingBy` tạo map nhưng không hứa iteration order của các nhóm. Nếu nguồn `orders` lại lấy từ SQL không có `ORDER BY`, còn thêm một tầng thứ tự không được bảo đảm. Do đó, output cũ là một behavior tình cờ.

### 24.2. Thiết kế lại contract

Nếu nghiệp vụ muốn thứ tự trạng thái cố định, biểu diễn trực tiếp thứ tự đó:

~~~java
List<String> sectionOrder =
        List.of("NEW", "PAID", "SHIPPED");

Map<String, List<Order>> grouped = orders.stream()
        .collect(Collectors.groupingBy(Order::status));

for (String status : sectionOrder) {
    List<Order> group = grouped.getOrDefault(status, List.of());
    writeCsvSection(status, group);
}
~~~

Nếu trong mỗi nhóm cần đơn hàng theo thời gian tạo rồi ID:

~~~java
Comparator<Order> orderWithinSection =
        Comparator.comparing(Order::createdAt)
                .thenComparing(Order::id);

for (String status : sectionOrder) {
    List<Order> sortedGroup = grouped.getOrDefault(
                    status, List.of())
            .stream()
            .sorted(orderWithinSection)
            .toList();
    writeCsvSection(status, sortedGroup);
}
~~~

Kết quả không còn phụ thuộc thứ tự iteration của map hoặc SQL. Nếu có trạng thái mới chưa nằm trong `sectionOrder`, cần hợp đồng xử lý: từ chối, đưa vào mục “khác” hay bổ sung cấu hình. Không được âm thầm bỏ dữ liệu ngoài các trạng thái đã biết.

### 24.3. Kiểm thử sau chuyển đổi

Test cần cố ý đảo input order, tạo nhiều đơn có cùng `createdAt` và xác minh:

- Các section xuất theo danh sách `sectionOrder`.
- Mỗi section chứa đúng đơn hàng thuộc trạng thái.
- Đơn trong section sắp theo `createdAt` rồi `id`.
- Trạng thái ngoài danh sách có đường xử lý được quy định.
- CSV không phụ thuộc thứ tự do `HashMap` hoặc database trả về.

Bài học của tình huống này: migration đã **lộ ra một giả định không được API cam kết**. Hướng sửa đúng là đưa thứ tự thành hợp đồng rõ ràng, không tìm cách tái tạo ngẫu nhiên iteration order cũ.

## 25. Kết luận

Thứ tự lặp là một ví dụ điển hình cho ranh giới giữa **hành vi được bảo đảm** và **hành vi tình cờ của implementation**. `List`, `LinkedHashMap` hoặc `TreeMap` có các contract riêng về order; `HashMap`, `HashSet`, `Map.of`, `Set.of` và nhiều API khác không hứa điều tương tự. Stream còn phân biệt encounter order với thứ tự thực thi; concurrency, file system, reflection, database và serialization bổ sung những nguồn không xác định khác.

Trong Java Advance Compatibility Migration, đừng coi mọi thay đổi output là lỗi của JDK mới, nhưng cũng đừng mặc định rằng “không được cam kết” thì không ảnh hưởng người dùng. Hãy tìm nơi consumer đang dựa vào order hoặc behavior ngầm, quyết định yêu cầu nghiệp vụ thật sự, rồi thể hiện nó bằng collection, comparator, schema, query hoặc API contract rõ ràng. Kiểm thử dựa trên hợp đồng thay vì một output tình cờ; khi đó việc nâng phiên bản sẽ ít phụ thuộc vào chi tiết không thuộc quyền kiểm soát của ứng dụng.
