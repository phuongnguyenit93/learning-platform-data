# Độ phức tạp, dung lượng và lựa chọn collection thực tế

Trong Java 27, chọn đúng collection không đơn giản là nhớ `ArrayList` nhanh hơn `LinkedList` hay `HashMap` tra cứu nhanh hơn `TreeMap`. Một lựa chọn tốt phải khớp **thao tác được thực hiện thường xuyên**, **quy mô dữ liệu**, **thứ tự cần bảo toàn**, **mức sử dụng bộ nhớ**, **khả năng thay đổi**, **mô hình truy cập đồng thời** và **hợp đồng của API**.

Bài thuộc chương **Collections hiện đại** của module **Java 27 và các kiến thức liên quan**. Nội dung tập trung vào API Java SE 27 còn hiện hành, bao gồm `SequencedCollection` / `SequencedMap`, các phương thức tạo map/set theo số phần tử dự kiến, collection bất biến về cấu trúc và các collection đồng thời. Không khuyến nghị những lớp lịch sử như `Vector`, `Stack` hoặc `Hashtable` làm lựa chọn mặc định cho mã mới.

## 1. Hiểu đúng độ phức tạp trước khi so sánh

### 1.1. Big-O mô tả sự tăng trưởng chi phí

Gọi `n` là số phần tử đang chứa và `k` là số phần tử được thêm, xóa hoặc sao chép trong một thao tác. Ký hiệu Big-O cho biết chi phí tăng như thế nào khi quy mô thay đổi, chứ không cho biết số mili giây chính xác.

| Ký hiệu | Diễn giải | Ví dụ thường gặp |
|---|---|---|
| `O(1)` | Chi phí không tăng theo `n` trong mô hình xét | Truy cập chỉ số trong `ArrayList`, `peek` của `PriorityQueue` |
| `O(log n)` | Tăng chậm theo số phần tử | Tra cứu key trong `TreeMap`, `TreeSet` |
| `O(n)` | Tăng tỷ lệ với số phần tử | `contains` trong list không có index chuyên dụng |
| `O(n log n)` | Thường gặp trong sắp xếp so sánh | Sắp xếp danh sách tổng quát theo comparator |
| `O(n²)` | Có thể phát sinh do lặp quét toàn bộ dữ liệu trong một vòng lặp lớn | Kiểm tra trùng bằng cách gọi `List.contains` cho từng phần tử đầu vào |

Hai thao tác có cùng Big-O vẫn có thể có tốc độ rất khác nhau do locality của bộ nhớ, cấp phát object, nhánh CPU, boxing, GC và chi phí của `equals`, `hashCode` hoặc `Comparator`.

### 1.2. Phân biệt worst-case, expected và amortized

Ba khái niệm dễ bị đánh đồng:

- **Worst-case**: giới hạn chi phí trong trường hợp bất lợi nhất của một thao tác.
- **Expected/average trong điều kiện giả định**: chi phí kỳ vọng nếu hàm băm phân bố hợp lý hoặc phân bố đầu vào đáp ứng giả định của cấu trúc.
- **Amortized**: một thao tác riêng lẻ có thể tốn kém, nhưng tổng chi phí của một chuỗi thao tác được chia đều.

Ví dụ `ArrayList.add(e)` vào cuối thường rẻ. Khi mảng bên trong đầy, một lần thêm có thể cần cấp phát mảng lớn hơn và sao chép các phần tử, tốn `O(n)`; xét cả chuỗi thêm liên tiếp, chi phí mỗi lần thêm là **`O(1)` amortized**, không phải bảo đảm worst-case `O(1)`.

Với `HashMap.get(k)` hoặc `put(k,v)`, cách nói phù hợp là **`O(1)` kỳ vọng khi hash phân bố tốt**, không phải `O(1)` bất kể dữ liệu và hàm băm. Collision, resize và chi phí xử lý key có thể ảnh hưởng đáng kể.

### 1.3. Phân biệt chi phí một thao tác và cả thuật toán

Nếu cần kiểm tra liệu mỗi phần tử của list A có xuất hiện trong list B:

~~~java
static <T> long countMatches(List<T> a, List<T> b) {
    return a.stream().filter(b::contains).count();
}
~~~

Nếu `b` là một `ArrayList` dài `m`, mỗi lần `contains` có thể quét `O(m)` phần tử. Với `a` có `n` phần tử, tổng chi phí có thể là `O(n × m)`.

Nếu nhu cầu chỉ là kiểm tra membership và dữ liệu cho phép dùng hash:

~~~java
static <T> long countMatchesFast(List<T> a, List<T> b) {
    Set<T> lookup = new HashSet<>(b);
    return a.stream().filter(lookup::contains).count();
}
~~~

Tạo set có chi phí kỳ vọng `O(m)`, rồi kiểm tra `n` phần tử có chi phí kỳ vọng `O(n)`. Tổng thể thường là `O(n + m)`. Đổi lại, cách thứ hai dùng thêm bộ nhớ `O(m)` và đòi hỏi `equals` / `hashCode` nhất quán.

**Đánh giá thuật toán tổng thể** quan trọng hơn việc chỉ nhìn tên một collection.

## 2. Bảng tra cứu nhanh các collection chủ yếu

Các giá trị dưới đây là đặc tính thông dụng hoặc cam kết của các triển khai được nhắc đến. Ký hiệu `*` biểu thị chi phí kỳ vọng/amortized hoặc phụ thuộc giả định, không phải worst-case tuyệt đối. Không tính chi phí của comparator, callback, đối tượng phần tử hoặc việc đồng bộ bên ngoài.

| Collection | Đọc/tìm kiếm | Thêm | Xóa | Thứ tự | Nhận xét |
|---|---|---|---|---|---|
| `ArrayList<E>` | `get(i) O(1)`; `contains O(n)` | Cuối `O(1)*`; tại đầu/giữa `O(n)` | Cuối `O(1)`; đầu/giữa `O(n)` | Theo chỉ số | Mặc định tốt cho list |
| `LinkedList<E>` | `get(i) O(n)`; `contains O(n)` | Hai đầu `O(1)` | Hai đầu `O(1)`; tìm phần tử `O(n)` | Theo vị trí node | Có overhead node và locality kém |
| `ArrayDeque<E>` | Peek hai đầu `O(1)*`; tìm phần tử `O(n)` | Hai đầu `O(1)*` | Hai đầu `O(1)*` | FIFO/LIFO do API quyết định | Phù hợp queue và stack đơn luồng |
| `HashSet<E>` | `contains O(1)*` | `O(1)*` | `O(1)*` | Không bảo đảm | Kiểm tra membership |
| `LinkedHashSet<E>` | `contains O(1)*` | `O(1)*` | `O(1)*` | Encounter order rõ ràng | Dedupe và giữ thứ tự |
| `TreeSet<E>` | `contains O(log n)` | `O(log n)` | `O(log n)` | Được sắp xếp | Tìm kiếm theo khoảng giá trị |
| `HashMap<K,V>` | `get O(1)*` | `put O(1)*` | `remove O(1)*` | Không bảo đảm | Lookup bằng key |
| `LinkedHashMap<K,V>` | `get O(1)*` | `put O(1)*` | `remove O(1)*` | Insertion/access order | Map có encounter order |
| `TreeMap<K,V>` | `get O(log n)` | `put O(log n)` | `remove O(log n)` | Theo key đã sắp xếp | `floorKey`, `ceilingKey`, range query |
| `PriorityQueue<E>` | `peek O(1)`; `contains O(n)` | `offer O(log n)` | `poll O(log n)` | Theo độ ưu tiên tại đầu | Không duyệt theo thứ tự ưu tiên |
| `EnumSet<E>` | Thao tác set thường rất hiệu quả | Rẻ với tập enum | Rẻ với tập enum | Theo thứ tự khai báo enum | Chỉ dành cho phần tử enum |
| `EnumMap<K,V>` | Thao tác map thường rất hiệu quả | Rẻ với key enum | Rẻ với key enum | Theo thứ tự khai báo enum | Chỉ dành cho key enum |

Lưu ý: `ArrayDeque` sử dụng mảng có thể tăng dung lượng nên nhiều thao tác ở hai đầu được mô tả chính xác hơn là *amortized constant time*. `LinkedList` có `O(1)` ở hai đầu, nhưng nếu phải đi tìm vị trí trước thì tổng chi phí vẫn có thể là `O(n)`.

Bảng không thay thế tài liệu API và benchmark theo workload. Ví dụ, một key có `hashCode` hoặc comparator tốn kém sẽ thay đổi chi phí thực tế.

## 3. ArrayList: lựa chọn List mặc định trong nhiều workload

### 3.1. Mảng động, truy cập ngẫu nhiên nhanh

`ArrayList` duy trì một mảng nội bộ có thể mở rộng, thích hợp khi:

- Đọc phần tử qua `get(index)` thường xuyên.
- Duyệt tuần tự nhiều phần tử.
- Thêm phần tử chủ yếu ở cuối.
- Cần dữ liệu liên tiếp theo thứ tự nhưng không yêu cầu thêm/xóa liên tục ở đầu.

~~~java
List<String> names = new ArrayList<>();
names.add("An");
names.add("Bình");
names.add("Chi");

System.out.println(names.get(1)); // Bình
~~~

`get(i)` và `set(i,e)` có chi phí `O(1)`. Duyệt toàn bộ list có chi phí `O(n)`, song thường tận dụng locality tốt hơn danh sách liên kết.

### 3.2. Insert/remove giữa list phải dịch chuyển phần tử

~~~java
List<Integer> numbers = new ArrayList<>(List.of(10, 20, 30));
numbers.add(0, 5);       // chèn đầu: dịch chuyển phần tử
numbers.remove(1);       // xóa giữa: dịch chuyển phần tử còn lại
~~~

Những thao tác như `add(0, e)`, `remove(0)` hay `add(i, e)` có thể tốn `O(n)` vì phải dịch chuyển nhiều tham chiếu trong mảng.

Nếu ứng dụng lặp lại thao tác lấy khỏi đầu liên tục, không nên tự làm queue bằng `ArrayList.remove(0)`: xử lý `n` phần tử như vậy có thể tốn tổng `O(n²)`. Dùng `ArrayDeque` và `pollFirst()` phù hợp hơn.

### 3.3. Khi nào LinkedList có lợi?

`LinkedList` là doubly linked list. Nó có thể thêm/xóa ở hai đầu với chi phí `O(1)` và cũng có thể sửa node thông qua iterator ở vị trí đã tìm được mà không dịch chuyển các phần tử còn lại.

Tuy nhiên, `get(i)` cần duyệt node, thường tốn `O(n)`. Mỗi phần tử có node và các tham chiếu liên kết, làm tăng overhead bộ nhớ và ảnh hưởng locality.

Với Java hiện đại, **đừng chọn LinkedList chỉ vì thường xuyên thêm/xóa** nếu các thao tác đó không diễn ra tại một vị trí đã được xác định. Hãy cân nhắc `ArrayList` cho list truy cập chỉ số và `ArrayDeque` cho queue/deque. `LinkedList` chỉ nên chọn khi cấu trúc liên kết thật sự phù hợp với cách truy cập và phép đo thực tế.

## 4. Size khác capacity: tác động đến hiệu năng và bộ nhớ

### 4.1. Size là số phần tử; capacity là chỗ dự trữ

Với `ArrayList`:

- `size()` là số phần tử có trong list.
- **Capacity** là kích thước mảng nội bộ để giữ các phần tử.
- Capacity luôn ít nhất bằng size và có thể lớn hơn size để giảm số lần cấp phát lại.

~~~java
ArrayList<Integer> values = new ArrayList<>(10_000);
System.out.println(values.size()); // 0
~~~

Tạo list có initial capacity `10_000` **không** tạo ra 10.000 phần tử. Nó chỉ chuẩn bị chỗ chứa; các phần tử vẫn phải được thêm bằng `add` hoặc các thao tác tương tự.

Điều này rất quan trọng khi dự trù bộ nhớ: 10.000 list rỗng nhưng đặt capacity quá lớn có thể tiêu tốn bộ nhớ đáng kể.

### 4.2. Đặt capacity khi biết trước quy mô

~~~java
int expectedCount = 50_000;

ArrayList<String> items = new ArrayList<>(expectedCount);

for (int i = 0; i < expectedCount; i++) {
    items.add("item-" + i);
}
~~~

Khi biết trước số lượng gần đúng, initial capacity hợp lý có thể giảm việc cấp phát và sao chép mảng. Nếu list đã tạo, có thể gọi `ensureCapacity(minCapacity)` trước khi thêm nhiều phần tử.

~~~java
ArrayList<String> items = new ArrayList<>();
items.ensureCapacity(30_000);
~~~

Ngược lại, đặt capacity lớn hơn nhu cầu thực tế quá nhiều sẽ tăng mức chiếm dụng bộ nhớ. Java API **không cam kết hệ số tăng mảng cụ thể**; không nên viết logic dựa vào giả định nội bộ như “luôn tăng đúng 1,5 lần”.

### 4.3. Giảm capacity có phải luôn tốt?

`ArrayList.trimToSize()` yêu cầu giảm capacity về size hiện tại. Điều này có thể hữu ích sau khi hoàn tất việc dựng một list lớn, ít thay đổi và sẽ tồn tại lâu.

~~~java
ArrayList<String> items = new ArrayList<>(100_000);
items.add("one");
items.add("two");

items.trimToSize();
~~~

Nhưng việc thu nhỏ có thể cần sao chép mảng, và nếu tiếp tục thêm phần tử, mảng lại phải mở rộng. Vì vậy **không** gọi `trimToSize` sau mỗi lần xóa một phần tử.

`clear()` xóa phần tử về mặt logic nhưng không phải lời hứa sẽ thu nhỏ capacity về mức tối thiểu. Nếu cần giải phóng bộ nhớ của vùng backing array lớn, có thể bỏ tham chiếu đến collection không còn dùng và tạo collection mới với quy mô phù hợp; GC chỉ thu hồi khi các object không còn reachable.

### 4.4. Phân biệt chi phí object phần tử với chi phí backing array

~~~java
List<Integer> boxed = new ArrayList<>();
boxed.add(1000); // boxing int thành Integer
~~~

`ArrayList<Integer>` lưu **tham chiếu** đến `Integer` chứ không lưu trực tiếp các byte của primitive `int` như một `int[]`. Ngoài backing array, có thể phát sinh bộ nhớ cho các wrapper object và chi phí GC. Không nên đưa ra số byte cố định cho mỗi phần tử vì phụ thuộc JVM, cấu hình, kích thước tham chiếu và chiến lược tối ưu runtime.

Nếu khối dữ liệu thật sự là các primitive cố định, một `int[]` hoặc `long[]` có thể tiết kiệm bộ nhớ hơn. Nhưng mảng primitive không cung cấp toàn bộ tiện ích của `List`, nên phải cân nhắc giao diện API và chi phí thao tác.

## 5. HashMap, HashSet: lookup kỳ vọng nhanh và bài toán dung lượng

### 5.1. HashMap và HashSet phục vụ hai mục đích khác nhau

- `HashMap<K,V>` ánh xạ từ key sang value.
- `HashSet<E>` lưu các phần tử duy nhất, thích hợp với kiểm tra membership và loại bỏ trùng.

~~~java
Map<String, Integer> frequency = new HashMap<>();
frequency.merge("java", 1, Integer::sum);
frequency.merge("java", 1, Integer::sum);

System.out.println(frequency.get("java")); // 2

Set<String> seen = new HashSet<>();
System.out.println(seen.add("A")); // true
System.out.println(seen.add("A")); // false
~~~

Khi hàm băm phân bố hợp lý và cấu trúc có dung lượng thích hợp, các thao tác lookup/chèn/xóa thường đạt `O(1)` kỳ vọng.

### 5.2. Collision và hợp đồng equals/hashCode

Hai object không bằng nhau vẫn có thể trả về cùng `hashCode()`. Đây là **hash collision**, không phải lỗi của Java. Hash-based collections phải xử lý các key cùng hash.

Điều bắt buộc đối với các key dùng trong `HashMap` và phần tử của `HashSet`:

- Nếu `a.equals(b)` là `true`, hai object phải có cùng `hashCode()`.
- Các field tham gia `equals` / `hashCode` nên ổn định trong thời gian object còn được dùng làm key hoặc phần tử set.
- Không dựa vào thứ tự duyệt của `HashMap` / `HashSet` vì API không bảo đảm thứ tự đó.

Một key mutable có thể gây lỗi khó phát hiện:

~~~java
record UserKey(String country, long id) {
}

Map<UserKey, String> users = new HashMap<>();
UserKey key = new UserKey("VN", 42L);
users.put(key, "An");
~~~

Record với component bất biến như `String` và primitive giúp tạo key ổn định. Nếu thay bằng object mutable và sửa nội dung mà `equals`/`hashCode` phụ thuộc vào, tra cứu có thể không còn hoạt động đúng.

### 5.3. Initial capacity và load factor của HashMap

`HashMap` sử dụng dung lượng các bucket và hệ số tải (**load factor**). Giá trị load factor mặc định là `0.75`, một cân bằng phổ biến giữa bộ nhớ và chi phí tra cứu. Khi vượt một ngưỡng liên quan đến capacity và load factor, map có thể phải mở rộng và phân phối lại phần tử.

Điểm cần nhớ:

- `map.size()` là số cặp key-value, không phải số bucket.
- Initial capacity là số bucket ban đầu theo cách triển khai map, **không** đồng nghĩa “số phần tử có thể thêm chính xác mà không resize”.
- Đặt capacity quá nhỏ khiến resize xảy ra nhiều lần khi thêm nhiều key.
- Đặt capacity quá lớn lãng phí bộ nhớ và có thể làm chi phí duyệt tăng.
- Chọn load factor rất thấp có thể làm map thưa và tốn bộ nhớ; quá cao có thể làm lookup kém hiệu quả.

### 5.4. Java 27: ưu tiên newHashMap(expectedMappings)

Java cung cấp `HashMap.newHashMap(int numMappings)` để tạo map phù hợp với số mapping **dự kiến**, giúp người đọc không phải tự tính capacity từ load factor.

~~~java
int expectedDistinctKeys = 25_000;

HashMap<String, Long> counts =
        HashMap.newHashMap(expectedDistinctKeys);

counts.merge("login", 1L, Long::sum);
counts.merge("purchase", 1L, Long::sum);
~~~

`newHashMap` không tạo trước 25.000 mapping; nó chuẩn bị dung lượng thích hợp để thường không phải resize khi thêm đủ số mapping dự kiến với load factor mặc định. Với set có API tương tự:

~~~java
HashSet<String> uniqueIds = HashSet.newHashSet(10_000);
~~~

`HashMap.newHashMap` và `HashSet.newHashSet` đã là API chuẩn từ Java 19 và vẫn dùng được trong Java 27. Khi số phần tử dự kiến chưa rõ, constructor mặc định vẫn là lựa chọn hợp lý.

### 5.5. Duyệt HashMap cũng chịu ảnh hưởng capacity

Tài liệu `HashMap` chỉ rõ duyệt các collection view có chi phí phụ thuộc **capacity cộng với size**, không chỉ số entry hiện có. Vì vậy, một map có ít phần tử nhưng capacity quá lớn có thể duyệt kém hiệu quả.

`LinkedHashMap` duy trì thêm cấu trúc liên kết theo encounter order; việc duyệt thông thường tỷ lệ với **size** mà không phụ thuộc capacity theo cách tương tự. Đổi lại, nó có overhead bộ nhớ để giữ thứ tự.

## 6. HashMap, LinkedHashMap và TreeMap: chọn theo yêu cầu thứ tự

### 6.1. Khi không cần thứ tự

~~~java
Map<String, Integer> stock = new HashMap<>();
stock.put("banana", 10);
stock.put("apple", 20);
~~~

`HashMap` phù hợp khi mục tiêu chính là tra cứu key và **không** có yêu cầu rõ về thứ tự. Việc thấy thứ tự duyệt có vẻ cố định trong vài lần chạy không làm nó trở thành contract.

### 6.2. Khi phải giữ insertion order

~~~java
Map<String, Integer> stock = new LinkedHashMap<>();
stock.put("banana", 10);
stock.put("apple", 20);
stock.put("orange", 5);

System.out.println(stock.keySet()); // [banana, apple, orange]
~~~

`LinkedHashMap` mặc định duy trì **insertion order**. Việc đặt lại value cho key đã tồn tại không mặc nhiên biến entry thành phần tử mới được chèn ở cuối theo chế độ insertion-order.

Nếu cần giữ thứ tự xuất hiện đầu tiên khi loại bỏ trùng, dùng `LinkedHashSet`:

~~~java
List<String> input = List.of("A", "B", "A", "C", "B");
Set<String> orderedUnique = new LinkedHashSet<>(input);

System.out.println(orderedUnique); // [A, B, C]
~~~

### 6.3. Khi phải sắp xếp theo key và tìm range

~~~java
NavigableMap<Integer, String> priceBands = new TreeMap<>();
priceBands.put(100, "basic");
priceBands.put(300, "plus");
priceBands.put(500, "premium");

System.out.println(priceBands.floorKey(350));   // 300
System.out.println(priceBands.ceilingKey(350)); // 500
~~~

`TreeMap` dùng thứ tự tự nhiên của key hoặc `Comparator` do caller cung cấp. Nó hỗ trợ các thao tác như `firstEntry`, `lastEntry`, `lowerKey`, `floorKey`, `ceilingKey`, `higherKey` và `subMap` với chi phí dựa trên cây được sắp xếp.

Các thao tác `get`, `put`, `remove` và `containsKey` có chi phí `O(log n)` được API bảo đảm. `TreeSet` áp dụng ý tưởng tương tự cho tập phần tử.

### 6.4. Comparator quyết định cách key được xem là trùng

Với `TreeMap` / `TreeSet`, hai key được xem là cùng vị trí nếu comparator trả về `0`. Điều này có thể khác `equals`.

~~~java
Set<String> names =
        new TreeSet<>(String.CASE_INSENSITIVE_ORDER);

names.add("Java");
names.add("java");

System.out.println(names.size()); // 1
~~~

Comparator nên nhất quán với `equals` nếu muốn giữ đầy đủ hợp đồng thông thường của `Set` / `Map`. Nếu cố ý dùng so sánh không nhất quán, phải công bố và hiểu rõ ý nghĩa “trùng” khác đi.

**Không dùng TreeMap chỉ vì muốn có iteration order ổn định**: nếu mong muốn là thứ tự chèn, `LinkedHashMap` thường phù hợp hơn và không phải trả chi phí sắp xếp key.

## 7. SequencedCollection và SequencedMap trong Java hiện hành

### 7.1. Truy cập hai đầu thống nhất

Từ Java 21, các interface `SequencedCollection`, `SequencedSet` và `SequencedMap` cung cấp contract về encounter order và thao tác ở hai đầu. Chúng tiếp tục có trong Java 27.

~~~java
SequencedCollection<String> tasks = new ArrayList<>();

tasks.addFirst("urgent");
tasks.addLast("routine");

System.out.println(tasks.getFirst()); // urgent
System.out.println(tasks.getLast());  // routine
~~~

Chi phí phụ thuộc **implementation**, không chỉ interface: `addFirst` trên `ArrayList` có thể phải dịch chuyển `O(n)` phần tử, còn thêm ở đầu `ArrayDeque` thường `O(1)` amortized.

### 7.2. reversed() là một view theo thứ tự ngược

~~~java
List<String> names = new ArrayList<>(List.of("A", "B", "C"));
List<String> reversed = names.reversed();

System.out.println(reversed); // [C, B, A]

names.add("D");
System.out.println(reversed.getFirst()); // D
~~~

`reversed()` trả một **view** có encounter order ngược, không phải mặc định sao chép tất cả phần tử. Thay đổi hợp lệ trên backing collection có thể phản ánh lên view, và chiều ngược lại cũng có thể ảnh hưởng collection gốc tùy thao tác được hỗ trợ.

Khi cần một snapshot độc lập:

~~~java
List<String> snapshot = List.copyOf(names.reversed());
~~~

`snapshot` không cho sửa cấu trúc bằng các thao tác mutator. Bản sao là **shallow** đối với object phần tử, không biến object mutable bên trong thành immutable.

### 7.3. LinkedHashMap có API cho thứ tự có chủ đích

~~~java
SequencedMap<String, Integer> stages = new LinkedHashMap<>();

stages.putLast("build", 1);
stages.putLast("test", 2);
stages.putFirst("validate", 0);

System.out.println(stages.firstEntry().getKey()); // validate
System.out.println(stages.lastEntry().getKey());  // test
~~~

`putFirst` / `putLast` thể hiện rõ mục đích đặt entry ở hai đầu encounter order. Với `HashMap`, thứ tự này không phải contract; với `TreeMap`, vị trí lại gắn với comparator và các thao tác thay đổi vị trí tùy ý có thể không được hỗ trợ.

## 8. Queue, Deque và PriorityQueue: khác nhau ở thứ tự lấy ra

### 8.1. FIFO: dùng ArrayDeque cho queue đơn luồng

~~~java
Deque<String> queue = new ArrayDeque<>();

queue.offerLast("task-A");
queue.offerLast("task-B");

System.out.println(queue.pollFirst()); // task-A
System.out.println(queue.pollFirst()); // task-B
System.out.println(queue.pollFirst()); // null (rỗng)
~~~

`ArrayDeque` phù hợp với queue có hai đầu hoặc stack, hoạt động với mảng tăng dung lượng khi cần. Nó **không chấp nhận null** và **không an toàn luồng** nếu nhiều thread chỉnh sửa đồng thời mà không có đồng bộ thích hợp.

Các cặp API tiện dùng:

| Mục đích | Thêm | Đọc | Lấy và xóa |
|---|---|---|---|
| FIFO queue | `offerLast(e)` | `peekFirst()` | `pollFirst()` |
| LIFO stack | `push(e)` | `peek()` | `pop()` |
| Hai đầu | `offerFirst/offerLast` | `peekFirst/peekLast` | `pollFirst/pollLast` |

`poll` trả `null` khi rỗng, còn một số phương thức như `remove` / `pop` có thể ném exception nếu không có phần tử. Tùy ý nghĩa nghiệp vụ mà chọn dạng API phù hợp.

### 8.2. PriorityQueue không phải danh sách đã sắp xếp

~~~java
PriorityQueue<Integer> priorities = new PriorityQueue<>();
priorities.offer(20);
priorities.offer(5);
priorities.offer(10);

System.out.println(priorities.peek()); // 5
System.out.println(priorities.poll()); // 5
System.out.println(priorities.poll()); // 10
~~~

`PriorityQueue` giữ phần tử có độ ưu tiên cao nhất theo thứ tự **nhỏ nhất trước** với comparator mặc định/natural order. Có thể đảo thứ tự bằng comparator. `offer` / `poll` thường `O(log n)`, `peek` `O(1)`, còn `contains(Object)` và `remove(Object)` `O(n)`.

**Duyệt PriorityQueue bằng iterator không bảo đảm thứ tự ưu tiên**. Nếu cần xuất từng phần tử theo thứ tự, phải liên tục `poll` (làm rỗng queue) hoặc tạo bản sao trước khi lấy.

### 8.3. Bài toán top-K bằng min-heap

Khi cần giữ **k phần tử có điểm cao nhất** từ luồng `n` phần tử, không cần sắp xếp toàn bộ dữ liệu. Dùng min-heap có tối đa `k` phần tử:

~~~java
record Score(String name, int points) {
}

static List<Score> topK(List<Score> input, int k) {
    if (k < 0) {
        throw new IllegalArgumentException("k must be >= 0");
    }

    PriorityQueue<Score> heap = new PriorityQueue<>(
            Comparator.comparingInt(Score::points)
    );

    for (Score score : input) {
        if (heap.size() < k) {
            heap.offer(score);
        } else if (!heap.isEmpty()
                && score.points() > heap.peek().points()) {
            heap.poll();
            heap.offer(score);
        }
    }

    List<Score> result = new ArrayList<>(heap);
    result.sort(Comparator.comparingInt(Score::points).reversed());
    return result;
}
~~~

Với `k > 0`, chi phí thời gian xấp xỉ `O(n log k + k log k)` và bộ nhớ phụ `O(k)`, không tính dữ liệu input. Khi `k == 0`, hàm trả danh sách rỗng và bỏ qua thao tác heap; cách cài đặt có thể cải tiến thêm đường đi này nếu đo thấy cần.

Nếu cần kết quả ổn định khi các điểm bằng nhau, comparator nên bổ sung tiêu chí phụ (chẳng hạn `name` hoặc mã định danh). Không dựa vào thứ tự tình cờ của heap.

## 9. EnumSet, EnumMap và lựa chọn chuyên dụng

### 9.1. EnumSet cho một tập giá trị enum

~~~java
enum Permission {
    READ, WRITE, DELETE
}

EnumSet<Permission> permissions =
        EnumSet.of(Permission.READ, Permission.WRITE);

System.out.println(permissions.contains(Permission.WRITE)); // true
~~~

`EnumSet` được thiết kế riêng cho enum và có biểu diễn compact, thường rất hiệu quả cho tập flags. Thứ tự duyệt theo **thứ tự khai báo hằng enum**.

~~~java
EnumSet<Permission> none = EnumSet.noneOf(Permission.class);
EnumSet<Permission> all = EnumSet.allOf(Permission.class);
~~~

Không dùng `HashSet<String>` nếu mô hình thực sự có một tập enum cố định, trừ khi cần tính mở rộng khác với enum.

### 9.2. EnumMap khi key là enum

~~~java
EnumMap<Permission, String> labels =
        new EnumMap<>(Permission.class);

labels.put(Permission.READ, "Xem");
labels.put(Permission.WRITE, "Sửa");

System.out.println(labels.get(Permission.READ)); // Xem
~~~

`EnumMap` được tối ưu cho tập key enum cố định và duyệt theo thứ tự khai báo enum. Nó cho phép value `null` nếu cần, nhưng không cho key `null`.

Trường hợp này khác `Map.of`, vốn không cho key hoặc value null.

### 9.3. Collection khác chỉ nên dùng khi hợp đồng cần

Một số loại đặc biệt:

- `IdentityHashMap` so sánh key bằng identity (`==`) thay vì `equals`. Hữu ích cho thuật toán theo dõi danh tính object, **không** thay thế `HashMap` chung.
- `WeakHashMap` lưu key bằng weak reference, hữu ích trong một số cấu trúc gắn metadata phụ với object. GC có thể làm entry biến mất; **không** coi đây là cache TTL hoặc cache có giới hạn dung lượng đáng tin cậy.
- `ConcurrentSkipListMap` và `ConcurrentSkipListSet` phù hợp khi cần thứ tự sorted và truy cập đồng thời.
- `Collections.newSetFromMap(...)` có các trường hợp chuyên biệt, nhưng thường `HashSet`, `LinkedHashSet` hoặc `ConcurrentHashMap.newKeySet()` dễ dùng hơn cho bài toán phổ biến.

## 10. Unmodifiable, snapshot và view: không đồng nghĩa

### 10.1. Factory collections bất khả sửa cấu trúc

~~~java
List<String> roles = List.of("reader", "writer");
Set<String> unique = Set.of("A", "B");
Map<String, Integer> weights = Map.of("low", 1, "high", 2);
~~~

Các collection trả về từ `List.of`, `Set.of` và `Map.of` là **unmodifiable**: gọi `add`, `remove` hoặc `put` sẽ không được hỗ trợ. Các factory này cũng **không chấp nhận null**; `Set.of` không chấp nhận phần tử trùng, `Map.of` không chấp nhận key trùng.

Thứ tự duyệt của `Set.of` và `Map.of` **không được bảo đảm**. Nếu thứ tự là contract, cần chọn một collection có encounter order xác định.

### 10.2. List.copyOf và Collections.unmodifiableList khác nhau

~~~java
List<String> original = new ArrayList<>(List.of("A"));

List<String> snapshot = List.copyOf(original);
List<String> readOnlyView = Collections.unmodifiableList(original);

original.add("B");

System.out.println(snapshot);     // [A]
System.out.println(readOnlyView); // [A, B]
~~~

- `List.copyOf` tạo một list unmodifiable chứa những phần tử tại thời điểm gọi; nếu nguồn đã là loại unmodifiable phù hợp, implementation có thể tái sử dụng. Không bảo đảm sao chép sâu các phần tử.
- `Collections.unmodifiableList` tạo một **view** không cho sửa qua view, nhưng các thay đổi qua backing list vẫn có thể xuất hiện trên view.

Nếu dữ liệu cần không bị tác động bởi thay đổi về **cấu trúc** của nguồn, `List.copyOf` là lựa chọn rõ ý định hơn.

### 10.3. Stream.toList và các API gần giống

`Stream.toList()` trả về một list unmodifiable và không cam kết implementation cụ thể. `Collectors.toList()` **không bảo đảm** type, tính có thể sửa, khả năng serialization hay thread safety của list nhận được; không nên dựa vào implementation mà một JDK cụ thể đang trả về.

~~~java
List<String> names = Stream.of("An", "Bình")
        .map(String::toUpperCase)
        .toList();
~~~

Cần chú ý import `java.util.stream.Stream`. Nếu muốn collection mutable có chủ ý, dùng collector phù hợp hoặc tạo `new ArrayList<>(...)`.

### 10.4. Không dùng subList làm snapshot

~~~java
List<String> source =
        new ArrayList<>(List.of("A", "B", "C", "D"));

List<String> view = source.subList(1, 3); // [B, C]
List<String> copy = List.copyOf(view);
~~~

`subList` là view gắn với backing list, nên các thay đổi cấu trúc bên ngoài phạm vi view có thể khiến hành vi không còn được xác định theo hợp đồng. `copy` biểu thị một snapshot unmodifiable về cấu trúc.

## 11. Truy cập đồng thời: chọn collection theo kiểu cạnh tranh

### 11.1. Collection thông thường không tự an toàn luồng

`ArrayList`, `HashMap`, `LinkedHashMap` và `ArrayDeque` không tự đồng bộ các thao tác khi nhiều thread truy cập và có sửa đổi. Không được suy luận rằng `get` hoặc `put` đơn lẻ “trông có vẻ an toàn” nghĩa là toàn bộ workflow an toàn.

Nếu chia sẻ mutable collection giữa nhiều thread, cần thiết kế đồng bộ thích hợp hoặc dùng collection đồng thời có contract tương ứng.

### 11.2. ConcurrentHashMap cho map truy cập đồng thời

~~~java
ConcurrentHashMap<String, LongAdder> counts =
        new ConcurrentHashMap<>();

counts.computeIfAbsent("request", key -> new LongAdder())
        .increment();

long current = counts.get("request").sum();
~~~

Ví dụ cần import `java.util.concurrent.ConcurrentHashMap` và `java.util.concurrent.atomic.LongAdder`. `computeIfAbsent` giúp tránh mẫu kiểm tra-rồi-ghi tách rời không an toàn khi nhiều thread cùng tạo value.

`ConcurrentHashMap` không chấp nhận `null` làm key hoặc value. Các phép đọc dưới thay đổi đồng thời không tạo một snapshot giao dịch toàn cục; iterator là loại **weakly consistent**, không có ý nghĩa là tất cả thao tác trên nhiều entry tự động atomic.

Với nhu cầu đếm rất nhiều key, cần cân nhắc overhead của `LongAdder` cho mỗi entry và đặc tính của dữ liệu thực tế.

### 11.3. CopyOnWriteArrayList: nhiều đọc, ít ghi

`CopyOnWriteArrayList` thích hợp khi collection được đọc hoặc duyệt thường xuyên nhưng cập nhật hiếm, ví dụ một danh sách listener tương đối nhỏ.

~~~java
CopyOnWriteArrayList<Runnable> listeners =
        new CopyOnWriteArrayList<>();

listeners.add(() -> System.out.println("changed"));

for (Runnable listener : listeners) {
    listener.run();
}
~~~

Khi ghi, implementation tạo bản sao mảng liên quan, nên cập nhật có chi phí tốn kém theo số phần tử. Iterator đọc từ **snapshot** tạo tại thời điểm iterator được tạo, vì vậy không phản ánh những thay đổi sau đó trong chính lượt duyệt.

Nếu list liên tục được cập nhật số lượng lớn, `CopyOnWriteArrayList` thường không phù hợp.

### 11.4. Queue giữa các thread và backpressure

Nếu producer và consumer chạy ở các thread khác nhau, cân nhắc collection trong `java.util.concurrent`:

| Collection | Đặc trưng | Trường hợp phù hợp |
|---|---|---|
| `ConcurrentLinkedQueue` | Queue không chặn, đồng thời | Giao việc không cần bounded capacity ở mức queue |
| `ArrayBlockingQueue` | Bounded blocking queue | Giới hạn số job đợi, áp dụng backpressure |
| `LinkedBlockingQueue` | Blocking queue, có thể giới hạn capacity | Cần blocking semantics và lựa chọn về dung lượng |
| `PriorityBlockingQueue` | Queue đồng thời có thứ tự ưu tiên | Cần lấy job ưu tiên nhưng không tự giới hạn dung lượng |
| `ConcurrentHashMap.newKeySet()` | Set đồng thời | Membership/dedup trong nhiều thread |

Không tự động chọn queue không giới hạn cho luồng công việc có producer có thể tạo dữ liệu nhanh hơn consumer xử lý. Nếu không có cơ chế giới hạn hoặc loại bỏ bớt job, backlog có thể tăng đến mức gây áp lực bộ nhớ.

### 11.5. Không dựa vào size() để điều phối đồng thời

`ConcurrentLinkedQueue.size()` có thể phải duyệt dữ liệu `O(n)` và kết quả có thể đã thay đổi ngay sau khi đo vì thread khác tiếp tục thao tác. Tương tự, `size()` trên nhiều collection concurrent không phải một giao dịch đọc snapshot nhất quán toàn bộ trạng thái.

Nếu cần điều phối capacity hay backpressure, hãy dùng contract của bounded `BlockingQueue` và phương thức `offer` / `put` / `poll` / `take` phù hợp, thay vì kiểm tra `size() < limit` rồi thêm như hai bước tách rời.

## 12. Bộ nhớ, GC và “chi phí ẩn” cần tính

### 12.1. Per-element overhead

Các cấu trúc có node hoặc entry object thường có overhead mỗi phần tử cao hơn mảng tham chiếu liên tiếp. Không nên tự giả định byte-per-element cố định vì runtime có thể dùng các cách tổ chức object khác nhau.

- `ArrayList` có backing array chứa tham chiếu.
- `LinkedList` có các node và liên kết hai chiều.
- `HashMap` cần cấu trúc bucket và entry/node để lưu key-value.
- `LinkedHashMap` cần thêm thông tin liên kết để bảo toàn thứ tự.
- `TreeMap` / `TreeSet` dùng cấu trúc cây có node và liên kết.
- `EnumSet` / `EnumMap` thường có biểu diễn gọn nhờ số lượng giá trị enum xác định.

Với số lượng phần tử rất lớn, chênh lệch nhỏ trên mỗi entry có thể trở thành lượng bộ nhớ đáng kể và làm tăng công việc của GC.

### 12.2. Số lượng phần tử sống và số lượng phần tử cấp phát

Hai workload có cùng số phần tử cuối cùng vẫn có thể tạo số lượng object tạm thời khác nhau.

Ví dụ, liên tục tạo `new HashSet<>(items)` trong từng request có thể dễ viết nhưng tạo nhiều cấu trúc tạm và làm tăng áp lực GC. Có thể cân nhắc tái sử dụng khi hợp đồng lifecycle cho phép, nhưng không nên dùng chung mutable state thiếu đồng bộ chỉ để tiết kiệm cấp phát.

Phân biệt:

- **Live set size**: số object còn reachable.
- **Allocation rate**: tốc độ cấp phát trong thời gian chạy.
- **Peak memory**: mức bộ nhớ cao nhất tại lúc tải lớn.
- **GC pauses / CPU**: ảnh hưởng của quản lý bộ nhớ.

### 12.3. Chọn capacity dựa trên peak và vòng đời

Đặt capacity quá sát peak có thể giảm resize nhưng tăng mức chiếm dụng khi tải bình thường thấp. Ngược lại, để capacity nhỏ rồi mở rộng liên tục có thể tạo chi phí cấp phát và sao chép.

Khi chọn kích thước nên biết:

1. Quy mô thường gặp và trường hợp lớn nhất có thể.
2. Collection sống trong một request hay nhiều giờ.
3. Có cần snapshot/cache nhiều bản song song hay không.
4. Tốc độ thêm/xóa theo thời gian.
5. Collection có giới hạn logic về số phần tử không.

Với dữ liệu tăng không giới hạn, việc chọn một cấu trúc có lookup tốt không thay thế được yêu cầu **đặt giới hạn dung lượng**, TTL, eviction hoặc xử lý backpressure ở cấp kiến trúc.

## 13. Ví dụ thực tế: chọn collection theo workload

### 13.1. Loại trùng nhưng bảo toàn thứ tự xuất hiện

~~~java
static List<String> uniqueInOrder(List<String> input) {
    return List.copyOf(new LinkedHashSet<>(input));
}
~~~

Lựa chọn `LinkedHashSet` thể hiện hai yêu cầu: uniqueness và insertion order. Chi phí dựng thường `O(n)` kỳ vọng và bộ nhớ thêm `O(n)`. `List.copyOf` tạo đầu ra unmodifiable, nhưng phần tử bên trong nếu là object mutable vẫn có thể thay đổi.

### 13.2. Gom thống kê số lần xuất hiện

~~~java
static Map<String, Long> frequencies(List<String> words) {
    Map<String, Long> counts = HashMap.newHashMap(words.size());

    for (String word : words) {
        counts.merge(word, 1L, Long::sum);
    }

    return counts;
}
~~~

`HashMap.newHashMap(words.size())` sử dụng một upper bound thô cho số key khác nhau. Nếu phần lớn từ trùng, mức dự trữ này có thể quá cao. Nếu biết số key phân biệt dự kiến, hãy dùng ước lượng đó thay vì tổng số từ.

Nếu cần kết quả iteration theo thứ tự gặp lần đầu, sử dụng `LinkedHashMap`; nếu cần theo alphabet, sắp xếp key hoặc dùng `TreeMap`.

### 13.3. Tìm một key gần nhất theo thứ tự

~~~java
NavigableMap<Integer, String> thresholds = new TreeMap<>();

thresholds.put(10, "low");
thresholds.put(50, "medium");
thresholds.put(100, "high");

Map.Entry<Integer, String> floor = thresholds.floorEntry(75);
System.out.println(floor.getValue()); // medium
~~~

`TreeMap` giúp tìm predecessor/successor và range query. `HashMap` không cung cấp các phép tìm kiếm theo thứ tự key với đặc tính tương tự.

### 13.4. Queue công việc một thread

~~~java
Deque<String> jobs = new ArrayDeque<>();

jobs.offerLast("compile");
jobs.offerLast("test");

while (!jobs.isEmpty()) {
    System.out.println(jobs.pollFirst());
}
~~~

Dùng `ArrayDeque` cho FIFO, không dùng `ArrayList.remove(0)`. Với nhiều thread sản xuất/tiêu thụ và cần giới hạn backlog, cân nhắc `ArrayBlockingQueue` hoặc loại `BlockingQueue` phù hợp.

### 13.5. Cache LRU nhỏ bằng LinkedHashMap

`LinkedHashMap` có chế độ **access-order** và hook `removeEldestEntry`, phù hợp cho ví dụ cache **giới hạn số entry** trong một thread:

~~~java
final class LruMap<K, V> extends LinkedHashMap<K, V> {
    private final int maxEntries;

    LruMap(int maxEntries) {
        super(16, 0.75f, true); // true = access-order

        if (maxEntries <= 0) {
            throw new IllegalArgumentException("maxEntries must be positive");
        }

        this.maxEntries = maxEntries;
    }

    @Override
    protected boolean removeEldestEntry(Map.Entry<K, V> eldest) {
        return size() > maxEntries;
    }
}
~~~

~~~java
LruMap<String, String> cache = new LruMap<>(2);

cache.put("A", "alpha");
cache.put("B", "beta");
cache.get("A");              // A trở thành entry mới được truy cập
cache.put("C", "gamma");  // B là entry ít được truy cập gần đây nhất

System.out.println(cache.containsKey("A")); // true
System.out.println(cache.containsKey("B")); // false
~~~

Đây là minh họa cơ chế LRU theo **số entry**, không có TTL, không có giới hạn dung lượng theo byte, không an toàn luồng và không tích hợp chính sách xử lý miss/eviction phức tạp. `removeEldestEntry` được kiểm tra khi chèn mapping mới; nó không tự chạy theo thời gian. Với cache lớn hoặc nhiều thread, cần đánh giá một giải pháp cache chuyên dụng có contract rõ ràng.

## 14. Bảng quyết định nhanh

| Nhu cầu thực tế | Lựa chọn thường nên thử đầu tiên | Lý do |
|---|---|---|
| List đọc theo index, thêm chủ yếu cuối | `ArrayList` | `get O(1)`, locality tốt, thêm cuối amortized |
| FIFO/LIFO hai đầu, một thread | `ArrayDeque` | Thao tác hai đầu amortized `O(1)` |
| Membership/loại trùng, không cần thứ tự | `HashSet` | Lookup kỳ vọng `O(1)` |
| Dedupe nhưng giữ encounter order | `LinkedHashSet` | Uniqueness và insertion order |
| Tập có thứ tự sắp xếp, truy vấn range | `TreeSet` | `O(log n)` và phép tìm láng giềng |
| Map tra cứu key, không cần thứ tự | `HashMap` | Lookup kỳ vọng `O(1)` |
| Map giữ insertion order | `LinkedHashMap` | Thứ tự duyệt xác định |
| Map access-order/LRU đơn giản | `LinkedHashMap` access-order | Có chính sách duyệt theo lần truy cập |
| Map sorted/range by key | `TreeMap` | `O(log n)` và navigable APIs |
| Lấy phần tử ưu tiên nhất từng lần | `PriorityQueue` | Heap với `peek O(1)`, `poll O(log n)` |
| Set/map với khóa enum | `EnumSet` / `EnumMap` | Cấu trúc chuyên dụng gọn và hiệu quả |
| Không cần sửa cấu trúc | `List.of` / `Set.of` / `Map.of` / `copyOf` | Hợp đồng unmodifiable rõ ràng |
| Map có cập nhật đồng thời | `ConcurrentHashMap` | Concurrency contract phù hợp |
| List nhiều đọc, cực ít ghi, có concurrent readers | `CopyOnWriteArrayList` | Snapshot iterator, đổi lại ghi đắt |
| Nhiều producer/consumer có giới hạn backlog | `ArrayBlockingQueue` | Bounded blocking và backpressure |

**Quy tắc thực dụng:** bắt đầu bằng cấu trúc đơn giản nhất đáp ứng hợp đồng, sau đó đo trên kích thước và cách truy cập thật. Không thay collection chỉ vì một bảng Big-O cho thấy khả năng tốt hơn trong một thao tác ít khi xảy ra.

## 15. Kiểm thử và benchmark lựa chọn collection

### 15.1. Đo đúng thao tác cần tối ưu

Một benchmark hữu ích phải mô phỏng:

- Số phần tử nhỏ, trung bình và lớn đúng như production.
- Phân phối key thực tế, tỷ lệ key trùng, tỷ lệ lookup hit/miss.
- Thứ tự thao tác: chỉ đọc, chỉ ghi hay xen kẽ.
- Có yêu cầu giữ thứ tự / sorted / uniqueness hay không.
- Chi phí tạo collection, nạp dữ liệu, sử dụng và giải phóng.
- Mức đồng thời, mức cạnh tranh trên key, throughput và tail latency.

Không chỉ đo `get` trong vòng lặp nhỏ nếu ứng dụng thực tế chi phần lớn thời gian ở `put`, tạo key hoặc serialize kết quả.

### 15.2. Tránh benchmark ngây thơ bằng nanoTime một lần

JIT, warm-up, dead-code elimination, GC, CPU frequency scaling và phân bố dữ liệu khiến kết quả của một phép đo duy nhất dễ sai.

Khi thật sự cần microbenchmark, nên dùng công cụ thích hợp như **JMH (Java Microbenchmark Harness)** với warm-up, nhiều lần đo và cấu hình đầu vào có ý nghĩa. JMH là công cụ benchmark riêng, không phải một collection của `java.util`.

Nếu mục tiêu là chọn cấu trúc cho hệ thống, thêm benchmark toàn luồng (end-to-end), quan sát allocation rate, GC và latency ở tải thực tế. Một cấu trúc nhanh trong microbenchmark không chắc giảm độ trễ toàn ứng dụng.

### 15.3. Dùng kết quả đo để quyết định, không suy đoán số liệu

Không có mốc tuyệt đối kiểu “trên 10.000 phần tử phải dùng TreeMap” hay “LinkedList nhanh hơn ArrayList sau N lần insert”. Điểm hòa vốn phụ thuộc workload, JVM, máy chủ và kiểu phần tử.

Chỉ đưa ra con số throughput, byte-per-element hoặc ngưỡng chuyển cấu trúc khi có kết quả đo tái lập được với điều kiện thử nghiệm được ghi rõ.

## 16. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| `O(1)` nghĩa là luôn mất cùng số nanosecond | Big-O không mô tả latency tuyệt đối; cache, GC, collision và hash vẫn ảnh hưởng |
| `HashMap` có `get` luôn worst-case `O(1)` | Thường là `O(1)` kỳ vọng khi hash phân bố tốt; không là bảo đảm mọi trường hợp |
| `ArrayList.add` luôn `O(1)` worst-case | Thêm cuối `O(1)` amortized; resize đôi khi cần sao chép nhiều phần tử |
| `new ArrayList<>(10_000)` chứa 10.000 phần tử | Constructor chỉ chuẩn bị capacity; `size()` ban đầu bằng 0 |
| `clear()` luôn thu nhỏ mảng của ArrayList | `clear` thay đổi phần tử logic, không cam kết co capacity |
| `LinkedList` luôn nhanh hơn khi insert/remove | Tìm vị trí thường `O(n)`; node overhead và locality cũng quan trọng |
| `ArrayDeque` chấp nhận `null` | `ArrayDeque` cấm null |
| `PriorityQueue` duyệt theo thứ tự ưu tiên | Chỉ đầu queue được bảo đảm có ưu tiên thích hợp; iterator không sắp xếp |
| `HashMap` sẽ duyệt theo thứ tự từng thêm | Thứ tự không được bảo đảm; dùng `LinkedHashMap` nếu cần |
| `TreeMap` dùng `equals` để xác định key trùng | Nó dùng comparator/natural ordering; compare bằng 0 quyết định key tương đương |
| `reversed()` luôn sao chép collection | Các API sequenced thường trả reverse-order view |
| `Collections.unmodifiableList` là snapshot | Nó là view; backing list thay đổi có thể hiện ra |
| `List.of` cho phép null | Factory unmodifiable này không cho null |
| `ConcurrentHashMap` làm nhiều lệnh ghép thành transaction | Phải dùng các atomic APIs phù hợp; không có transaction tổng thể mặc định |
| `CopyOnWriteArrayList` phù hợp list ghi liên tục | Nó tối ưu cho trường hợp nhiều đọc, ít ghi |
| Chọn capacity càng lớn càng tốt | Có thể lãng phí bộ nhớ, tăng iteration cost và áp lực GC |

## 17. Câu hỏi tự kiểm tra

1. Khác nhau giữa `O(1)` expected và `O(1)` amortized là gì?
2. Vì sao thêm một phần tử vào cuối `ArrayList` đôi khi tốn `O(n)`?
3. Nếu biết trước có khoảng 50.000 phần tử, việc đặt initial capacity giúp ích thế nào? Tác hại khi dự trữ quá mức là gì?
4. Vì sao dùng `List.contains` lặp lại cho danh sách lớn có thể tệ hơn dựng một `HashSet`?
5. Nêu khác biệt của `HashMap`, `LinkedHashMap` và `TreeMap` khi yêu cầu về encounter order thay đổi.
6. Khi nào `TreeSet` phù hợp hơn `HashSet`?
7. Vì sao `ArrayDeque` phù hợp hơn `ArrayList.remove(0)` cho FIFO?
8. Tại sao `PriorityQueue` không thể được dùng như một list đã sắp xếp chỉ bằng cách duyệt iterator?
9. `HashMap.newHashMap(10_000)` tạo ra 10.000 entry ngay lúc gọi hay không?
10. Vì sao `List.copyOf` khác `Collections.unmodifiableList`?
11. Khi nào `CopyOnWriteArrayList` đáng cân nhắc, và chi phí phải trả là gì?
12. Vì sao `ConcurrentLinkedQueue.size()` không nên dùng làm cơ chế thực thi bounded backpressure?
13. Một dữ liệu cache có thể tăng vô hạn cần xử lý gì ngoài việc chọn `HashMap`?
14. Nếu collection phải chứa enum, vì sao cần cân nhắc `EnumSet` hoặc `EnumMap`?
15. Các thông số workload nào cần được kiểm soát khi so sánh performance hai collection?

## 18. Nguồn chính thức Java SE 27

- [Java SE 27 API — Collection](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/Collection.html): contract chung cho collection và các thao tác tùy chọn.
- [Java SE 27 API — List và SequencedCollection](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/List.html): thao tác theo chỉ số, `getFirst` / `getLast` và `reversed`.
- [Java SE 27 API — ArrayList](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/ArrayList.html): chi phí amortized, capacity và `ensureCapacity` / `trimToSize`.
- [Java SE 27 API — LinkedList](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/LinkedList.html): doubly linked list và các thao tác `Deque`.
- [Java SE 27 API — ArrayDeque](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/ArrayDeque.html): deque dùng mảng tăng dung lượng, null và amortized cost.
- [Java SE 27 API — HashMap](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/HashMap.html): load factor, capacity, iteration và `newHashMap`.
- [Java SE 27 API — HashSet](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/HashSet.html): uniqueness và `newHashSet`.
- [Java SE 27 API — LinkedHashMap](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/LinkedHashMap.html): insertion-order, access-order và `removeEldestEntry`.
- [Java SE 27 API — TreeMap](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/TreeMap.html): guaranteed logarithmic-time operations và `NavigableMap`.
- [Java SE 27 API — PriorityQueue](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/PriorityQueue.html): chi phí của `offer`, `poll`, `peek` và giới hạn iterator.
- [Java SE 27 API — EnumSet và EnumMap](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/EnumSet.html): các collection chuyên dụng cho enum.
- [Java SE 27 API — SequencedMap](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/SequencedMap.html): `putFirst`, `putLast` và views theo encounter order.
- [Java SE 27 API — ConcurrentHashMap](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html): thao tác đồng thời và các điều kiện nguyên tử.
- [Java SE 27 API — CopyOnWriteArrayList](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/CopyOnWriteArrayList.html): snapshot iteration, đọc nhiều/ghi ít.
- [Java SE 27 API — java.util.concurrent](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/package-summary.html): các concurrency collections và blocking queues.
