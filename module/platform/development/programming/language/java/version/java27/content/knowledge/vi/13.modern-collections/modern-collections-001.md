# Collection, List, Set, Queue, Deque và Map

## 1. Tổng quan Java Collections Framework

**Java Collections Framework (JCF)** là tập hợp các interface, lớp triển khai và thuật toán dùng để lưu trữ, duyệt và thao tác với nhóm đối tượng. Trong Java 27, những hợp đồng quan trọng nhất cho nhu cầu thường ngày gồm **Collection**, **List**, **Set**, **Queue**, **Deque** và **Map**.

Điểm cốt lõi là **chọn interface theo ý nghĩa dữ liệu**, sau đó mới chọn implementation theo cách truy cập, thứ tự và hiệu năng. Không phải dữ liệu nào “gồm nhiều phần tử” cũng nên lưu trong ArrayList.

- **List**: dãy phần tử theo vị trí; cho phép phần tử trùng lặp.
- **Set**: tập phần tử duy nhất theo quy tắc bằng nhau.
- **Queue**: hàng đợi xử lý phần tử theo chính sách cụ thể, thường nhưng không bắt buộc là FIFO.
- **Deque**: hàng đợi hai đầu; có thể hoạt động như FIFO queue hoặc LIFO stack.
- **Map**: ánh xạ khóa → giá trị; mỗi khóa xuất hiện tối đa một lần.
- **Collection**: hợp đồng chung cho phần lớn cấu trúc lưu phần tử, **không** bao gồm Map.

Sơ đồ đơn giản hóa quan hệ kế thừa interface:

~~~mermaid
flowchart TD
    I["Iterable<E>"] --> C["Collection<E>"]
    C --> SC["SequencedCollection<E>"]
    C --> S["Set<E>"]
    C --> Q["Queue<E>"]
    SC --> L["List<E>"]
    SC --> SS["SequencedSet<E>"]
    S --> SS
    Q --> D["Deque<E>"]
    SC --> D
    S --> SoS["SortedSet<E>"]
    SS --> SoS
    M["Map<K,V>"] --> SM["SequencedMap<K,V>"]
    SM --> SoM["SortedMap<K,V>"]
~~~

**SequencedCollection**, **SequencedSet** và **SequencedMap** đã được chuẩn hóa từ Java 21 (JEP 431), nên là API chính thức trong Java 27, không phải preview. Chúng giúp diễn đạt thứ tự duyệt và thao tác đầu/cuối một cách nhất quán. Các interface **SortedSet** và **SortedMap** cũng nằm trong nhánh sequenced tương ứng.

**Map không extends Collection** vì nó lưu cặp khóa/giá trị thay vì chỉ lưu các phần tử E. Tuy vậy, Map là một phần quan trọng của Collections Framework và cung cấp các view như **keySet()**, **values()** và **entrySet()**.

## 2. Interface là hợp đồng, implementation quyết định đặc tính

Cùng một interface có thể có nhiều cách triển khai khác nhau:

| Interface | Implementation thường dùng | Đặc tính nổi bật |
|---|---|---|
| **List** | **ArrayList** | Duyệt theo chỉ số; truy cập vị trí nhanh, phù hợp danh sách thông thường |
| **List**, **Deque** | **LinkedList** | Danh sách liên kết hai chiều; hỗ trợ thao tác hai đầu |
| **Set** | **HashSet** | Không bảo đảm thứ tự duyệt; tra cứu membership hiệu quả trong trường hợp điển hình |
| **SequencedSet** | **LinkedHashSet** | Giữ thứ tự encounter, thường là thứ tự thêm |
| **SortedSet** | **TreeSet** | Duyệt theo thứ tự tự nhiên hoặc Comparator |
| **Queue** | **PriorityQueue** | Lấy phần tử theo độ ưu tiên, không phải FIFO |
| **Deque** | **ArrayDeque** | Queue/stack hai đầu, không nhận null |
| **Map** | **HashMap** | Ánh xạ khóa/giá trị, không bảo đảm thứ tự |
| **SequencedMap** | **LinkedHashMap** | Map có thứ tự encounter và thao tác đầu/cuối |
| **SortedMap** | **TreeMap** | Map được sắp theo khóa |
| **Concurrent Map** | **ConcurrentHashMap** | Hỗ trợ truy cập đồng thời với các bảo đảm riêng |

Nên khai báo biến bằng interface phù hợp nhất khi code không phụ thuộc chi tiết triển khai:

~~~java
List<String> names = new ArrayList<>();
Set<String> codes = new HashSet<>();
Queue<String> pending = new ArrayDeque<>();
Deque<String> history = new ArrayDeque<>();
Map<String, Integer> stock = new HashMap<>();
~~~

Nếu nghiệp vụ yêu cầu thứ tự cụ thể, hãy biểu diễn nhu cầu đó bằng kiểu hoặc hợp đồng rõ ràng. Ví dụ, dùng **SequencedMap** và **LinkedHashMap** khi muốn xử lý mục đầu/cuối của một bảng ánh xạ có thứ tự, thay vì dựa vào thứ tự ngẫu nhiên của HashMap.

## 3. Collection: hợp đồng chung cho tập phần tử

**Collection<E>** mô tả một nhóm phần tử kiểu E. Những thao tác thường dùng:

| Phương thức | Ý nghĩa |
|---|---|
| **size()**, **isEmpty()** | Đếm phần tử, kiểm tra rỗng |
| **contains(value)** | Kiểm tra một phần tử có trong collection |
| **add(value)** | Thử thêm phần tử; là thao tác tùy chọn theo implementation |
| **remove(value)** | Xóa một phần tử bằng điều kiện bằng nhau |
| **addAll(other)** | Thêm các phần tử từ collection khác |
| **containsAll(other)** | Kiểm tra chứa toàn bộ phần tử của collection khác |
| **removeIf(predicate)** | Xóa phần tử thỏa điều kiện nếu hỗ trợ |
| **iterator()**, **forEach(...)** | Duyệt phần tử |
| **stream()** | Tạo stream để xử lý theo pipeline |
| **toArray(...)** | Xuất dữ liệu sang array |

Ví dụ:

~~~java
Collection<String> events = new ArrayList<>();

events.add("created");
events.add("paid");
events.add("created");

System.out.println(events.size());          // 3
System.out.println(events.contains("paid")); // true

events.removeIf("created"::equals);
System.out.println(events);                  // [paid]
~~~

Ở ví dụ này, đối tượng thật là ArrayList nên cho phép trùng lặp và có thứ tự. Nhưng **Collection** nói chung **không hứa** hai đặc tính đó; chỉ riêng implementation hoặc interface con mới định nghĩa chúng.

Các thao tác sửa đổi trong Collection có thể là **optional operations**. Một collection unmodifiable có quyền ném **UnsupportedOperationException** khi được yêu cầu sửa, kể cả với một số thao tác trông như không thay đổi nội dung. Không nên mặc định mọi Collection đều mutable.

## 4. Generics giúp giới hạn kiểu phần tử

Java collections thường dùng **generics** để kiểm tra kiểu tại thời điểm biên dịch:

~~~java
List<String> cities = new ArrayList<>();

cities.add("Ha Noi");
cities.add("Da Nang");
// cities.add(42); // Lỗi biên dịch: Integer không phải String

String first = cities.getFirst();
~~~

Generics giảm nhu cầu ép kiểu và làm rõ hợp đồng dữ liệu. Không nên sử dụng **raw List**, **raw Map** trong mã mới vì mất kiểm tra kiểu tĩnh và dễ dẫn đến ClassCastException ở nơi khác.

Sự bất biến của tham số generic (*invariance*) rất quan trọng:

~~~java
List<Integer> integers = new ArrayList<>();
// List<Number> numbers = integers; // Không hợp lệ
~~~

Nếu chỉ cần đọc như Number, có thể dùng wildcard **? extends Number**:

~~~java
static double sum(Collection<? extends Number> values) {
    double total = 0;
    for (Number value : values) {
        total += value.doubleValue();
    }
    return total;
}
~~~

Nếu API chủ yếu **ghi** các giá trị Integer vào đích, dùng **? super Integer** khi phù hợp:

~~~java
static void addDefaults(Collection<? super Integer> target) {
    target.add(10);
    target.add(20);
}
~~~

Quy tắc ghi nhớ thường dùng: **PECS — Producer Extends, Consumer Super**. Đây là hướng dẫn về khả năng đọc/ghi trong generic API, không phải quy tắc bắt buộc cho mọi biến collection.

## 5. List: thứ tự và vị trí có ý nghĩa

**List<E>** là dãy phần tử có thứ tự theo chỉ số, bắt đầu từ 0. Nó cho phép trùng lặp. Phần tử tại vị trí nào là một phần của ý nghĩa dữ liệu: bước trong quy trình, hàng trên bảng, lịch sử sự kiện, danh sách ưu tiên thủ công.

~~~java
List<String> phases = new ArrayList<>(List.of("design", "test"));

phases.add("deploy");
phases.add(1, "implement");

System.out.println(phases);
// [design, implement, test, deploy]

System.out.println(phases.get(1));      // implement
System.out.println(phases.indexOf("test")); // 2
~~~

Những API quan trọng:

- **get(index)**, **set(index, value)**: đọc/đổi phần tử theo vị trí.
- **add(index, value)**, **remove(index)**: thêm/xóa tại vị trí.
- **indexOf(value)**, **lastIndexOf(value)**: tìm vị trí theo quy tắc equals.
- **subList(from, to)**: view của một đoạn danh sách; giới hạn trên **to** là exclusive.
- **sort(comparator)** và **replaceAll(operator)**: cập nhật nội dung nếu List hỗ trợ sửa.
- **getFirst()**, **getLast()**, **addFirst()**, **addLast()**: API thống nhất từ Java 21 qua SequencedCollection.

~~~java
List<String> pipeline = new ArrayList<>(List.of("build", "test"));
pipeline.addFirst("checkout");
pipeline.addLast("release");

System.out.println(pipeline.getFirst()); // checkout
System.out.println(pipeline.getLast());  // release
System.out.println(pipeline.reversed()); // [release, test, build, checkout]
~~~

**ArrayList** thường là lựa chọn mặc định tốt cho List cần truy cập theo chỉ số. **LinkedList** có thể dùng như List lẫn Deque, nhưng với nhiều bài toán danh sách thông thường, cấu trúc dựa trên mảng của ArrayList đơn giản và có locality tốt hơn. Không nên chuyển sang LinkedList chỉ vì nghĩ rằng mọi thao tác thêm/xóa của nó luôn nhanh: tìm đúng vị trí bằng chỉ số vẫn cần duyệt các nút.

## 6. Set: tính duy nhất thay vì vị trí

**Set<E>** không chứa hai phần tử được coi là bằng nhau theo hợp đồng **equals**. Thêm phần tử đã có không làm tăng số lượng:

~~~java
Set<String> permissions = new HashSet<>();

permissions.add("READ");
permissions.add("WRITE");
boolean addedAgain = permissions.add("READ");

System.out.println(permissions.size()); // 2
System.out.println(addedAgain);         // false
~~~

Không được dựa vào thứ tự hiển thị của **HashSet**. Nếu cần duyệt theo thứ tự thêm, dùng **LinkedHashSet**; nếu cần sắp xếp theo Comparator, dùng **TreeSet**.

~~~java
Set<String> unordered = new HashSet<>(List.of("beta", "alpha", "gamma"));
Set<String> insertionOrdered =
    new LinkedHashSet<>(List.of("beta", "alpha", "gamma"));
Set<String> sorted = new TreeSet<>(List.of("beta", "alpha", "gamma"));

System.out.println(insertionOrdered); // [beta, alpha, gamma]
System.out.println(sorted);           // [alpha, beta, gamma]
~~~

Hai Set chứa cùng các phần tử được xem là bằng nhau mà không cần cùng thứ tự duyệt. Tuy nhiên, với **TreeSet**, quan hệ duy nhất dựa trên kết quả so sánh của Comparator hoặc thứ tự tự nhiên. Nên bảo đảm Comparator phù hợp với equals khi cần tuân thủ đầy đủ hợp đồng Set trong các ngữ cảnh thay thế implementation.

**Khi nào dùng Set?** Kiểm tra membership, loại phần tử trùng, quản lý quyền, danh sách mã định danh duy nhất. Nếu thứ tự và số lần xuất hiện có ý nghĩa, List mới là mô hình đúng.

## 7. Queue: hợp đồng hàng đợi

**Queue<E>** dành cho các phần tử đang chờ được xử lý. Chính sách chọn phần tử có thể là FIFO, độ ưu tiên hoặc một chính sách khác do implementation quy định.

Các cặp phương thức cần phân biệt:

| Mục đích | Báo lỗi bằng ngoại lệ | Trả giá trị đặc biệt |
|---|---|---|
| Thêm phần tử | **add(e)** | **offer(e)** |
| Lấy và xóa phần tử đầu | **remove()** | **poll()** |
| Xem nhưng không xóa phần tử đầu | **element()** | **peek()** |

Với hàng đợi giới hạn dung lượng, **offer(e)** có thể trả **false** khi không nhận thêm phần tử; **add(e)** có thể ném **IllegalStateException**. Khi hàng đợi rỗng, **poll()/peek()** trả **null**, còn **remove()/element()** ném **NoSuchElementException**.

~~~java
Queue<String> jobs = new ArrayDeque<>();

jobs.offer("job-1");
jobs.offer("job-2");

System.out.println(jobs.peek()); // job-1, chưa xóa
System.out.println(jobs.poll()); // job-1, đã xóa
System.out.println(jobs.poll()); // job-2
System.out.println(jobs.poll()); // null
~~~

Ví dụ trên hoạt động FIFO vì **ArrayDeque** duy trì thứ tự thêm vào cuối và lấy từ đầu. Không phải Queue nào cũng FIFO: **PriorityQueue** chọn phần tử theo thứ tự ưu tiên.

~~~java
Queue<Integer> priorities = new PriorityQueue<>();

priorities.offer(30);
priorities.offer(10);
priorities.offer(20);

System.out.println(priorities.poll()); // 10
System.out.println(priorities.poll()); // 20
System.out.println(priorities.poll()); // 30
~~~

**PriorityQueue không cam kết iterator duyệt theo thứ tự ưu tiên.** Muốn xử lý có thứ tự, hãy lấy lần lượt bằng **poll()** hoặc dùng một cấu trúc sorted phù hợp với mục đích.

## 8. Deque: thao tác ở cả hai đầu

**Deque<E>** (double-ended queue) hỗ trợ thêm, đọc và xóa ở đầu lẫn cuối. Nó có thể biểu diễn:

- **FIFO queue**: **addLast/offerLast** và **removeFirst/pollFirst**.
- **LIFO stack**: **push** và **pop**, hoặc **addFirst** và **removeFirst**.
- **Hàng đợi hai đầu**: thêm và xóa ở cả hai phía theo luật nghiệp vụ.

~~~java
Deque<String> queue = new ArrayDeque<>();

queue.addLast("A");
queue.addLast("B");
queue.addFirst("URGENT");

System.out.println(queue.removeFirst()); // URGENT
System.out.println(queue.removeFirst()); // A
System.out.println(queue.removeFirst()); // B
~~~

Dùng Deque như stack:

~~~java
Deque<String> actions = new ArrayDeque<>();

actions.push("open");
actions.push("edit");

System.out.println(actions.pop());  // edit
System.out.println(actions.peek()); // open
~~~

Trong Java hiện đại, **ArrayDeque** là lựa chọn phù hợp cho phần lớn stack/queue đơn luồng. Không nên lựa chọn lớp **Stack** cũ để xây dựng stack mới khi Deque cung cấp hợp đồng rõ hơn và phù hợp với cách thiết kế collection hiện tại.

**ArrayDeque không chấp nhận null**. Quy ước này rất quan trọng vì nhiều thao tác Deque trả null để biểu thị trạng thái rỗng. Khi đọc giá trị, dùng **pollFirst()** nếu rỗng là trường hợp bình thường, hoặc **removeFirst()** nếu rỗng là vi phạm bất biến.

## 9. Map: ánh xạ khóa sang giá trị

**Map<K,V>** lưu các cặp key/value. Mỗi khóa chỉ xuất hiện một lần; việc gọi **put** với khóa đã tồn tại sẽ thay giá trị cũ.

~~~java
Map<String, Integer> inventory = new HashMap<>();

inventory.put("PEN", 10);
inventory.put("BOOK", 5);
inventory.put("PEN", 12);

System.out.println(inventory.size());      // 2
System.out.println(inventory.get("PEN"));   // 12
System.out.println(inventory.get("MISSING")); // null
~~~

Các API thường dùng:

| Phương thức | Ý nghĩa |
|---|---|
| **put(key, value)** | Thêm hoặc thay ánh xạ |
| **get(key)** | Lấy giá trị; có thể trả null |
| **containsKey(key)** | Kiểm tra sự tồn tại của khóa |
| **getOrDefault(key, fallback)** | Lấy giá trị hoặc dự phòng khi không có ánh xạ |
| **putIfAbsent(key, value)** | Thêm khi chưa có ánh xạ phù hợp |
| **computeIfAbsent(key, fn)** | Tính giá trị khi khóa chưa có giá trị không null |
| **merge(key, value, fn)** | Thêm hoặc kết hợp với giá trị cũ |
| **remove(key)** | Xóa ánh xạ |
| **keySet()**, **values()**, **entrySet()** | Xem khóa, giá trị, cặp ánh xạ |

Ví dụ đếm số lần xuất hiện:

~~~java
Map<String, Integer> counts = new HashMap<>();

for (String word : List.of("java", "sql", "java", "java")) {
    counts.merge(word, 1, Integer::sum);
}

System.out.println(counts.get("java")); // 3
~~~

Khi cần phân biệt khóa **không tồn tại** với khóa **đã tồn tại nhưng giá trị null**, dùng **containsKey**. **get(key) == null** không đủ để phân biệt hai trường hợp trên ở những implementation cho phép null như HashMap.

**Map không có thứ tự duyệt chung.** HashMap không bảo đảm thứ tự; LinkedHashMap có encounter order; TreeMap sắp theo khóa. Nếu thứ tự là một phần của hợp đồng đầu ra, hãy chọn implementation phù hợp ngay từ đầu.

## 10. Duyệt Map đúng cách

Duyệt cặp key/value qua **entrySet()** thường là cách tự nhiên nhất:

~~~java
Map<String, Integer> stock = new LinkedHashMap<>();
stock.put("PEN", 10);
stock.put("BOOK", 5);

for (Map.Entry<String, Integer> entry : stock.entrySet()) {
    System.out.println(entry.getKey() + "=" + entry.getValue());
}
~~~

Hoặc dùng **forEach**:

~~~java
stock.forEach((sku, quantity) ->
    System.out.println(sku + ": " + quantity)
);
~~~

Các collection trả về từ **keySet()**, **values()** và **entrySet()** thông thường là **view** của Map gốc. Xóa phần tử qua một số view được hỗ trợ sẽ tác động đến Map. Tuy nhiên, không phải view nào cũng cho phép mọi thao tác thêm/sửa, và việc thay đổi Map trong lúc duyệt có thể gây hành vi không được hỗ trợ.

Nếu cần danh sách khóa độc lập tại thời điểm hiện tại, tạo bản sao rõ ràng:

~~~java
List<String> snapshotKeys = List.copyOf(stock.keySet());
~~~

Lưu ý: **List.copyOf** giữ encounter order của đầu vào Collection khi tạo danh sách, nhưng chỉ có thứ tự có ý nghĩa nếu collection nguồn có thứ tự xác định. **HashMap.keySet()** không tự trở thành một danh sách có thứ tự ổn định chỉ vì được sao chép.

## 11. Sequenced Collections: API đầu/cuối và đảo chiều

Từ Java 21, **SequencedCollection<E>** bổ sung hợp đồng cho một collection có **encounter order** được xác định. Các thao tác bao gồm **getFirst**, **getLast**, **addFirst**, **addLast**, **removeFirst**, **removeLast** và **reversed**. Các thao tác sửa là tùy chọn, nên có thể ném **UnsupportedOperationException** ở collection không cho sửa đổi.

**SequencedSet<E>** kết hợp tính duy nhất của Set với thứ tự encounter. **SequencedMap<K,V>** bổ sung các thao tác liên quan đến entry đầu/cuối và view đảo chiều cho Map.

~~~java
SequencedSet<String> stages = new LinkedHashSet<>();

stages.add("compile");
stages.add("test");
stages.add("deploy");

System.out.println(stages.getFirst()); // compile
System.out.println(stages.getLast());  // deploy
System.out.println(stages.reversed()); // [deploy, test, compile]
~~~

Với LinkedHashSet, **addFirst** hoặc **addLast** có thể đặt lại vị trí encounter của một phần tử đã có mà không làm Set chứa bản sao trùng lặp:

~~~java
stages.addFirst("deploy");
System.out.println(stages); // [deploy, compile, test]
~~~

Với Map có thứ tự:

~~~java
SequencedMap<String, Integer> ranking = new LinkedHashMap<>();

ranking.put("alice", 10);
ranking.put("bob", 8);
ranking.put("carol", 6);

System.out.println(ranking.firstEntry()); // alice=10
System.out.println(ranking.lastEntry());  // carol=6

ranking.putFirst("carol", 12);
System.out.println(ranking.sequencedKeySet());
// [carol, alice, bob]
~~~

**reversed() trả về view đảo thứ tự, không phải bản sao độc lập.** Việc thay đổi qua view, nếu được hỗ trợ, có thể ghi ngược vào collection gốc. Không dùng reversed view như một snapshot bất biến. Nếu cần một bản sao theo thứ tự đảo ở một thời điểm, tạo collection mới từ view và lựa chọn chính sách mutability rõ ràng.

Lưu ý thêm: thứ tự **encounter** không nhất thiết là thứ tự **sort**. LinkedHashSet duy trì thứ tự chèn hoặc được sắp lại tường minh; TreeSet duy trì thứ tự theo Comparator.

## 12. SortedSet và SortedMap: thứ tự do Comparator quyết định

**TreeSet** và **TreeMap** duy trì một thứ tự có cấu trúc dựa trên thứ tự tự nhiên hoặc Comparator.

~~~java
NavigableSet<Integer> scores = new TreeSet<>();

scores.add(80);
scores.add(65);
scores.add(95);

System.out.println(scores.first());   // 65
System.out.println(scores.last());    // 95
System.out.println(scores.ceiling(81)); // 95
~~~

Với khóa của Map:

~~~java
NavigableMap<String, Integer> ranks =
    new TreeMap<>(Comparator.reverseOrder());

ranks.put("alpha", 1);
ranks.put("beta", 2);

System.out.println(ranks.firstKey()); // beta
~~~

Các cấu trúc sorted đặc biệt hữu ích khi cần tìm phần tử gần nhất, truy vấn khoảng giá trị hoặc xuất dữ liệu có thứ tự. Đổi lại, những phép tìm kiếm/cập nhật thông thường có chi phí bậc **O(log n)**, khác với chi phí trung bình gần **O(1)** của các hash-based collections khi các giả định về hash hợp lệ.

Comparator trong TreeSet/TreeMap quyết định khi nào hai khóa/phần tử được xem là trùng nhau theo thứ tự so sánh (**compare(a,b) == 0**). Nếu Comparator không nhất quán với equals, hành vi vẫn tuân theo thứ tự đã chọn nhưng có thể gây bất ngờ khi sử dụng chúng như Set/Map theo hợp đồng equals thông thường.

## 13. Chọn implementation theo hiệu năng thực tế

Bảng dưới đây mô tả đặc tính **điển hình**, không phải cam kết tuyệt đối cho mọi phân bố dữ liệu, kích thước hoặc môi trường chạy.

| Implementation | Truy cập/tìm kiếm | Thêm/xóa | Khi phù hợp |
|---|---|---|---|
| **ArrayList** | get(index) O(1) | Thêm cuối amortized O(1); chèn/xóa giữa O(n) | Danh sách chủ yếu duyệt và đọc theo chỉ số |
| **LinkedList** | get(index) O(n) | Thao tác đầu/cuối O(1) | Cần List + Deque trong một cấu trúc, có lý do rõ ràng |
| **ArrayDeque** | Không hỗ trợ get(index) | Thêm/xóa hai đầu amortized O(1) | Stack hoặc FIFO queue đơn luồng |
| **HashSet** | contains trung bình gần O(1) | add/remove trung bình gần O(1) | Tập phần tử duy nhất, không cần thứ tự |
| **LinkedHashSet** | Tương tự hash-based Set | Thêm/xóa thông thường gần O(1) | Tập duy nhất có encounter order |
| **TreeSet** | contains O(log n) | add/remove O(log n) | Tập có thứ tự và truy vấn khoảng |
| **HashMap** | get/containsKey trung bình gần O(1) | put/remove trung bình gần O(1) | Tra cứu khóa, không cần thứ tự |
| **LinkedHashMap** | Tương tự hash-based Map | put/remove thông thường gần O(1) | Map cần thứ tự encounter |
| **TreeMap** | get O(log n) | put/remove O(log n) | Map cần sắp xếp theo khóa |
| **PriorityQueue** | peek O(1) | offer/poll O(log n) | Xử lý theo độ ưu tiên |

**Không suy ra lựa chọn tối ưu chỉ từ Big-O.** Bộ nhớ, locality, số phần tử, cách duyệt, tần suất cập nhật và chi phí của **hashCode/equals/Comparator** đều quan trọng. Ví dụ, ArrayList thường đơn giản và nhanh trong nhiều bài toán mà LinkedList có vẻ hấp dẫn trên lý thuyết.

Nếu biết trước số phần tử dự kiến lớn, có thể chọn capacity phù hợp cho một số cấu trúc như **new ArrayList<>(expectedSize)** hoặc **HashMap.newHashMap(expectedMappings)** (API có từ Java 19). Capacity là gợi ý phân bổ, không phải giới hạn cứng số phần tử.

## 14. Mutable, unmodifiable và immutable không giống nhau

Một vấn đề thường gặp trong thiết kế API là phân biệt **không cho sửa collection** với **dữ liệu hoàn toàn bất biến**.

~~~java
List<String> fixed = List.of("A", "B");
// fixed.add("C"); // UnsupportedOperationException
~~~

Các factory **List.of**, **Set.of** và **Map.of** trả về collection/map unmodifiable. Chúng không cho phép null. **Set.of** từ chối phần tử trùng khi tạo; **Map.of** từ chối khóa trùng. Thứ tự duyệt của **Set.of** và **Map.of** không được cam kết.

~~~java
List<String> source = new ArrayList<>(List.of("A", "B"));

List<String> snapshot = List.copyOf(source);
List<String> liveView = Collections.unmodifiableList(source);

source.add("C");

System.out.println(snapshot); // [A, B]
System.out.println(liveView); // [A, B, C]
~~~

**List.copyOf** cho một danh sách unmodifiable không phản ánh các thay đổi cấu trúc sau đó của nguồn. **Collections.unmodifiableList** là một **view** không cho sửa qua nó, nhưng vẫn có thể phản ánh thay đổi từ danh sách nền.

Các collection unmodifiable vẫn có thể chứa **đối tượng mutable**:

~~~java
record Ticket(String id, List<String> notes) {}

List<String> mutableNotes = new ArrayList<>();
List<Ticket> tickets = List.of(new Ticket("T1", mutableNotes));

mutableNotes.add("updated");

System.out.println(tickets.getFirst().notes()); // [updated]
~~~

Để đạt tính bất biến sâu hơn, cần kiểm soát cả các phần tử/thành phần lồng nhau, thường qua record constructor kiểm tra và tạo bản sao phù hợp. **List.copyOf** chỉ sao chụp cấu trúc bên ngoài, không clone các phần tử.

## 15. Bảo đảm thứ tự, equality và hashCode

Một collection có thể **có thứ tự** hoặc **không cam kết thứ tự**. Đặc tính này ảnh hưởng đến việc serialize JSON, ghi log, tính checksum, làm test snapshot và giao tiếp với dịch vụ khác.

- **List** so sánh bằng nhau theo **thứ tự và phần tử tại từng vị trí**.
- **Set** so sánh dựa trên **tập phần tử**, không dựa trên thứ tự duyệt.
- **Map** so sánh dựa trên **các ánh xạ khóa/giá trị**, không dựa trên thứ tự duyệt.
- **HashSet/HashMap** không hứa thứ tự ổn định qua các lần chạy hoặc thay đổi cấu trúc.
- **LinkedHashSet/LinkedHashMap** có encounter order; TreeSet/TreeMap có thứ tự sort.

Nếu dùng object làm phần tử trong HashSet hoặc khóa trong HashMap, **equals** và **hashCode** phải tuân thủ hợp đồng nhất quán. Không nên sửa các field tham gia tính equals/hashCode khi object vẫn đang nằm trong hash-based Set/Map.

~~~java
record UserId(String value) {}

Map<UserId, String> users = new HashMap<>();
users.put(new UserId("u-1"), "Lan");

System.out.println(users.get(new UserId("u-1"))); // Lan
~~~

Record phù hợp làm key khi các component tham gia equality có giá trị ổn định. Nhưng record chứa một List mutable vẫn có thể gây rủi ro nếu thành phần đó bị sửa sau khi record được dùng làm khóa. Record không tự bảo đảm bất biến sâu.

## 16. Null và kết quả trả về đặc biệt

Chính sách null **không giống nhau** ở các implementation.

| Cấu trúc | Null |
|---|---|
| **ArrayList** | Có thể chứa null |
| **HashSet** | Có thể chứa một null |
| **HashMap** | Có thể có một null key và nhiều null value |
| **ArrayDeque** | Không cho phép null |
| **PriorityQueue** | Không cho phép null |
| **ConcurrentHashMap** | Không cho phép null key hoặc null value |
| **List.of / Set.of / Map.of** | Không cho phép null |
| **TreeSet / TreeMap** | Phụ thuộc quy tắc so sánh, Comparator và implementation; không nên giả định hỗ trợ null |

Khi dùng Queue, **poll()** trả null nếu rỗng; do đó không chèn null như một phần tử dữ liệu vào cấu trúc hàng đợi không cho phép null. Với Map cho phép null, **get() == null** có thể là “không có khóa” hoặc “khóa có giá trị null”; kiểm tra thêm **containsKey** nếu cần phân biệt.

Để biểu diễn “có hoặc không có kết quả”, có thể dùng Optional ở ranh giới phương thức trả về nếu phù hợp. Không cần bọc mọi phần tử collection vào Optional chỉ để thay thế một hợp đồng null chưa rõ ràng.

## 17. Duyệt, xóa khi duyệt và collection views

Duyệt qua enhanced for:

~~~java
List<String> words =
    new ArrayList<>(List.of("alpha", "beta", "gamma"));

for (String word : words) {
    System.out.println(word);
}
~~~

Nếu cần xóa theo điều kiện, **removeIf** thường rõ ràng:

~~~java
words.removeIf(word -> word.startsWith("b"));
System.out.println(words); // [alpha, gamma]
~~~

Hoặc dùng iterator và chính **iterator.remove()** khi implementation hỗ trợ:

~~~java
Iterator<String> it = words.iterator();

while (it.hasNext()) {
    if (it.next().equals("gamma")) {
        it.remove();
    }
}
~~~

Không nên sửa cấu trúc một ArrayList bằng **list.remove(...)** trong lúc đang duyệt bằng enhanced for. Nhiều iterator được gọi là **fail-fast** và có thể ném ConcurrentModificationException khi phát hiện sửa đổi không hợp lệ. Đây là cơ chế phát hiện lỗi ở mức best-effort, **không phải** cơ chế bảo đảm an toàn đa luồng.

Với view như **subList**, **reversed** hoặc **Map.keySet()**, hãy đọc tài liệu của từng loại để biết sửa đổi nào được phép và có lan truyền sang nguồn không. Khi cần một snapshot độc lập, dùng copy factory phù hợp.

## 18. Stream và Collection bổ sung cho nhau

**Collection** lưu trữ và quản lý phần tử; **Stream** mô tả một pipeline xử lý dữ liệu từ nguồn. Stream không phải một collection và không được thiết kế để tái sử dụng sau terminal operation.

~~~java
List<String> names = List.of("An", "Binh", "Anh", "Lan");

List<String> selected = names.stream()
    .filter(name -> name.startsWith("A"))
    .map(String::toUpperCase)
    .toList();

System.out.println(selected); // [AN, ANH]
~~~

**Stream.toList()** trả về một List unmodifiable. Nếu cần danh sách mutable để tiếp tục thêm/xóa, hãy tạo bản sao:

~~~java
List<String> editable = new ArrayList<>(selected);
editable.add("ANNA");
~~~

Chuyển sang Set:

~~~java
Set<String> unique = names.stream()
    .map(String::toLowerCase)
    .collect(java.util.stream.Collectors.toSet());
~~~

Không phụ thuộc vào thứ tự duyệt của Set do **Collectors.toSet()** tạo ra. Nếu thứ tự là một phần hợp đồng, hãy chỉ rõ collection đích:

~~~java
Set<String> orderedUnique = names.stream()
    .collect(java.util.stream.Collectors.toCollection(LinkedHashSet::new));
~~~

Với Map, phép collect có thể gặp khóa trùng. Khi sử dụng **Collectors.toMap**, cần xác định chính sách xử lý duplicate keys (chẳng hạn merger function) để tránh lỗi bất ngờ.

## 19. Collections và đa luồng

**ArrayList**, **HashMap**, **HashSet**, **ArrayDeque** và các implementation thông thường **không tự an toàn** cho truy cập sửa đổi đồng thời từ nhiều thread. **final** trên biến tham chiếu cũng không làm collection trở nên thread-safe.

Nếu cần chia sẻ dữ liệu, lựa chọn tùy mô hình sử dụng:

- **Immutable/unmodifiable snapshot**: phù hợp cho dữ liệu cấu hình hoặc danh sách không đổi giữa nhiều thread, với điều kiện các phần tử được chia sẻ an toàn.
- **ConcurrentHashMap**: phù hợp cho truy cập/cập nhật map đồng thời; không chấp nhận null.
- **BlockingQueue** như **LinkedBlockingQueue** hoặc **ArrayBlockingQueue**: phù hợp giao tiếp producer/consumer có khả năng chờ khi rỗng hoặc đầy.
- **ConcurrentLinkedQueue**: queue không khóa cho kịch bản nhiều thread phù hợp.
- **Collections.synchronizedList(...)**: wrapper đồng bộ cho một số thao tác, nhưng vẫn cần khóa ngoài phù hợp khi duyệt theo hợp đồng của wrapper.

Ví dụ cập nhật counter an toàn bằng ConcurrentHashMap:

~~~java
java.util.concurrent.ConcurrentMap<String, Integer> counts =
    new java.util.concurrent.ConcurrentHashMap<>();

counts.merge("request", 1, Integer::sum);
counts.merge("request", 1, Integer::sum);

System.out.println(counts.get("request")); // 2
~~~

Các phương thức **merge**, **compute** trên ConcurrentHashMap có tính nguyên tử ở cấp thao tác theo hợp đồng của implementation. Điều này không tự làm một chuỗi nhiều thao tác trên nhiều key trở thành transaction.

Nếu dùng Map thường, chuỗi **get + put** không tự nguyên tử. Ngay cả khi từng phép đọc/ghi trông đơn giản, nhiều thread có thể gây mất cập nhật. Hãy xác định rõ mức đồng bộ cần thiết thay vì thay ngẫu nhiên ArrayList bằng một collection đồng thời mà chưa xét hợp đồng truy cập.

## 20. Ví dụ hoàn chỉnh: xử lý sản phẩm, hàng đợi và thống kê

Ví dụ sau kết hợp nhiều interface trong một tác vụ nhỏ. Lưu vào tệp **ModernCollectionsDemo.java** để chạy với JDK 27.

~~~java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.Deque;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.PriorityQueue;
import java.util.SequencedMap;
import java.util.SequencedSet;

public class ModernCollectionsDemo {
    record Job(String id, int priority) {}

    public static void main(String[] args) {
        // List: co thu tu, cho phep trung lap
        List<String> products =
            new ArrayList<>(List.of("PEN", "BOOK", "PEN"));

        products.addLast("RULER");
        System.out.println("Products: " + products);
        System.out.println("Last product: " + products.getLast());

        // SequencedSet: duyet theo encounter order, loai trung
        SequencedSet<String> unique = new LinkedHashSet<>(products);
        System.out.println("Unique products: " + unique);
        System.out.println("Reverse unique: " + unique.reversed());

        // Deque: FIFO pending queue
        Deque<String> pending = new ArrayDeque<>(unique);
        System.out.println("Next: " + pending.pollFirst());
        System.out.println("Remaining: " + pending);

        // SequencedMap: dem so lan xuat hien va giu thu tu khoa
        SequencedMap<String, Integer> quantities = new LinkedHashMap<>();
        for (String product : products) {
            quantities.merge(product, 1, Integer::sum);
        }
        System.out.println("Quantities: " + quantities);
        System.out.println("First entry: " + quantities.firstEntry());

        // PriorityQueue: lay cong viec co priority cao nhat truoc
        PriorityQueue<Job> jobs = new PriorityQueue<>(
            Comparator.comparingInt(Job::priority).reversed()
        );
        jobs.offer(new Job("prepare-shipment", 20));
        jobs.offer(new Job("security-check", 90));
        jobs.offer(new Job("notify-customer", 10));

        while (!jobs.isEmpty()) {
            System.out.println("Run: " + jobs.poll().id());
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac ModernCollectionsDemo.java
java ModernCollectionsDemo
~~~

Kết quả có thể dự đoán vì những nơi cần thứ tự đã chọn cấu trúc có encounter order hoặc Comparator rõ ràng:

~~~text
Products: [PEN, BOOK, PEN, RULER]
Last product: RULER
Unique products: [PEN, BOOK, RULER]
Reverse unique: [RULER, BOOK, PEN]
Next: PEN
Remaining: [BOOK, RULER]
Quantities: {PEN=2, BOOK=1, RULER=1}
First entry: PEN=2
Run: security-check
Run: prepare-shipment
Run: notify-customer
~~~

**Giải thích lựa chọn:**

1. List giữ nguyên dữ liệu đầu vào, bao gồm sản phẩm PEN xuất hiện hai lần.
2. LinkedHashSet loại trùng mà vẫn duy trì thứ tự xuất hiện đầu tiên.
3. ArrayDeque cung cấp hàng đợi FIFO không cần truy cập theo chỉ số.
4. LinkedHashMap ghi số lần xuất hiện nhưng vẫn giữ thứ tự lần đầu thêm key.
5. PriorityQueue lấy công việc có số priority cao hơn trước nhờ Comparator đảo.

Nếu chỉ dùng HashSet và HashMap, kết quả thứ tự duyệt không còn được bảo đảm. Đây là khác biệt thiết kế quan trọng khi viết test hoặc tạo đầu ra machine-readable.

## 21. Các lỗi phổ biến

| Hiện tượng | Nguyên nhân | Hướng xử lý |
|---|---|---|
| Kết quả HashSet/HashMap đổi thứ tự | Hash-based collection không bảo đảm encounter order | Dùng LinkedHashSet/LinkedHashMap hoặc sorted variant |
| Set mất phần tử trùng | Set biểu diễn tính duy nhất | Dùng List nếu số lần xuất hiện có ý nghĩa |
| Lấy phần tử khỏi Queue ra sai thứ tự | PriorityQueue không FIFO | Chọn ArrayDeque nếu cần FIFO |
| **poll()** trả null | Queue rỗng | Xử lý trạng thái rỗng hoặc dùng remove() khi rỗng là lỗi |
| **getFirst()** ném NoSuchElementException | Sequenced collection rỗng | Kiểm tra isEmpty() hoặc dùng API trả null nếu có |
| **UnsupportedOperationException** khi add | Collection unmodifiable | Tạo ArrayList/HashSet/HashMap mutable nếu cần sửa |
| **ConcurrentModificationException** khi duyệt | Sửa cấu trúc trực tiếp trong khi iterator hoạt động | Dùng removeIf/Iterator.remove hoặc quy tắc đồng bộ phù hợp |
| HashMap tìm không thấy key sau khi sửa object | Key mutable làm thay đổi equals/hashCode | Dùng key bất biến |
| **get() == null** không phân biệt trạng thái | Map cho phép null value | Dùng containsKey hoặc thay chính sách dữ liệu |
| **Collectors.toMap** lỗi key trùng | Thiếu merge policy | Cung cấp merger function rõ ràng |
| Dùng reversed view như bản sao | reversed() là view | Tạo bản sao khi cần snapshot |
| Dùng ArrayList như stack xóa đầu liên tục | remove(0) làm dịch phần tử | Dùng ArrayDeque |
| Race condition khi sửa HashMap | Map thường không an toàn cho nhiều thread | Dùng ConcurrentHashMap hoặc đồng bộ phù hợp |

## 22. Bài tập thực hành

**Bài tập 1 — Chọn đúng cấu trúc:** Nhận một danh sách các mã sản phẩm có thể trùng. Tạo ba kết quả: List giữ nguyên tất cả, Set chỉ giữ giá trị duy nhất và danh sách duy nhất vẫn giữ thứ tự xuất hiện. Giải thích implementation được chọn.

**Bài tập 2 — FIFO và ưu tiên:** Mô phỏng hàng đợi 10 công việc bằng ArrayDeque, sau đó mô phỏng lại bằng PriorityQueue sử dụng record Job(id, priority). So sánh thứ tự lấy công việc bằng poll().

**Bài tập 3 — Map và thống kê:** Đếm số lượt truy cập theo URL. Dùng **merge** để cộng dồn, **entrySet** để xuất báo cáo và **containsKey** để phân biệt khóa chưa xuất hiện.

**Bài tập 4 — Sequenced Collections:** Tạo LinkedHashSet gồm năm trạng thái. Dùng getFirst, getLast, addFirst và reversed, sau đó kiểm tra rằng đảo chiều là view chứ không phải snapshot.

**Bài tập 5 — An toàn dữ liệu:** So sánh List.copyOf(source) và Collections.unmodifiableList(source) khi sửa source. Sau đó đặt một phần tử mutable trong List.copyOf và mô tả giới hạn của tính bất biến.

**Bài tập 6 — Concurrent Map:** Dùng nhiều thread tăng cùng một bộ đếm theo khóa; so sánh cách cập nhật bằng **get + put** trên HashMap với **merge** của ConcurrentHashMap. Đừng dựa vào kết quả chạy may mắn của chương trình có data race để kết luận rằng nó an toàn.

## 23. Checklist chọn collection trong Java 27

- [ ] Xác định dữ liệu cần **thứ tự**, **tính duy nhất**, **FIFO/LIFO**, **độ ưu tiên** hay **tra cứu theo khóa**.
- [ ] Khai báo interface phù hợp; tránh phụ thuộc implementation khi không cần.
- [ ] Ưu tiên ArrayList cho danh sách thông thường và ArrayDeque cho queue/stack đơn luồng.
- [ ] Dùng HashSet/HashMap chỉ khi không yêu cầu thứ tự duyệt.
- [ ] Dùng LinkedHashSet/LinkedHashMap hoặc Sequenced API khi encounter order quan trọng.
- [ ] Dùng TreeSet/TreeMap nếu cần sắp xếp hoặc truy vấn khoảng.
- [ ] Không coi PriorityQueue là FIFO hoặc iterator có thứ tự ưu tiên.
- [ ] Chọn rõ chính sách null, trùng lặp, khả năng sửa đổi và các trường hợp rỗng.
- [ ] Phân biệt unmodifiable view với snapshot, và shallow copy với immutable object graph.
- [ ] Thiết kế equals/hashCode ổn định cho phần tử Set và khóa Map.
- [ ] Tránh sửa collection sai cách khi đang duyệt.
- [ ] Chọn concurrent collection khi truy cập đồng thời thực sự cần thiết.
- [ ] Đánh giá bộ nhớ và chi phí thao tác thực tế, không chỉ Big-O trên giấy.
- [ ] Kiểm thử tập rỗng, phần tử trùng, null, thứ tự duyệt, snapshot/view và truy cập đa luồng khi liên quan.

**Kết luận:** Trong Java 27, một hệ thống collection tốt được thiết kế từ **hợp đồng dữ liệu**, không chỉ từ tên lớp. List giữ thứ tự và sự trùng lặp; Set bảo vệ tính duy nhất; Queue/Deque định nghĩa cách lấy công việc; Map xử lý ánh xạ khóa/giá trị. Các interface **SequencedCollection**, **SequencedSet** và **SequencedMap** bổ sung API thống nhất cho thứ tự encounter, trong khi các triển khai cụ thể quyết định chi phí, tính mutable và bảo đảm đồng thời. Chọn đúng ngay từ đầu giúp mã rõ ràng, dự đoán được và dễ bảo trì.

## Tài liệu tham khảo

- [Java SE 27 — Collections Framework overview](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/doc-files/coll-overview.html): khái niệm và cấu trúc tổng quát.
- [Java SE 27 — Collection](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/Collection.html): phương thức cơ bản và các optional operations.
- [Java SE 27 — List](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/List.html): danh sách theo vị trí và SequencedCollection methods.
- [Java SE 27 — Set](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/Set.html): hợp đồng tính duy nhất.
- [Java SE 27 — Queue](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/Queue.html): offer/add, poll/remove, peek/element.
- [Java SE 27 — Deque](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/Deque.html): hàng đợi hai đầu.
- [Java SE 27 — Map](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/Map.html): ánh xạ key/value.
- [Java SE 27 — SequencedCollection](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/SequencedCollection.html), [SequencedSet](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/SequencedSet.html), [SequencedMap](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/SequencedMap.html): encounter order, thao tác đầu/cuối và reversed views.
- [JEP 431 — Sequenced Collections](https://openjdk.org/jeps/431): động cơ thiết kế và phạm vi chuẩn hóa từ Java 21.
