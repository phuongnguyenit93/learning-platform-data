# ConcurrentHashMap, concurrent collection và blocking queue

Trong Java 27, nhiều thread có thể cùng đọc và thay đổi trạng thái của ứng dụng. Khi các thread dùng chung một **Map**, **List**, **Set** hoặc hàng đợi, câu hỏi không chỉ là “cấu trúc nào chạy nhanh?” mà còn là **những thao tác nào an toàn, hành vi nào được bảo đảm và cách phối hợp tải giữa các thread**.

Java cung cấp các cấu trúc dữ liệu đồng thời trong **java.util.concurrent**, nổi bật là:

- **ConcurrentHashMap<K, V>**: map dành cho truy cập và cập nhật đồng thời, có những phép cập nhật nguyên tử theo khóa.
- **Concurrent collection**: các tập hợp với hợp đồng đồng thời chuyên biệt, như **CopyOnWriteArrayList**, **ConcurrentLinkedQueue** và **ConcurrentSkipListMap**.
- **BlockingQueue<E>**: hàng đợi có thể **chờ** khi chưa có phần tử hoặc không còn sức chứa, thường được dùng để nối producer và consumer.

Chọn đúng cấu trúc dữ liệu giúp giảm nhu cầu khóa thủ công, nhưng không tự động biến mọi chuỗi thao tác nghiệp vụ thành một giao dịch nguyên tử. Bài học trình bày các API ổn định, vẫn áp dụng trong Java 27; ví dụ sử dụng generics và các khả năng Java hiện đại, không dựa vào cơ chế legacy.

## 1. Vấn đề: collection thông thường không tự bảo đảm an toàn đồng thời

Ví dụ một bộ đếm dùng **HashMap**:

~~~java
import java.util.HashMap;
import java.util.Map;

Map<String, Integer> counts = new HashMap<>();

void record(String category) {
    counts.put(category, counts.getOrDefault(category, 0) + 1);
}
~~~

Nếu nhiều thread cùng gọi **record("email")**, có thể xảy ra trình tự:

~~~text
Thread A                  Thread B
--------                  --------
đọc email = 5
                          đọc email = 5
tính 5 + 1
                          tính 5 + 1
ghi email = 6
                          ghi email = 6

Kết quả: 6 thay vì 7.
~~~

Đây là **lost update**: một lần tăng bị mất vì thao tác đọc–tính–ghi không nguyên tử. Với **HashMap**, vấn đề còn rộng hơn: bản thân các thao tác thay đổi đồng thời không được hỗ trợ theo hợp đồng đồng bộ mà ứng dụng cần. Không thể chỉ đổi đoạn code thành nhiều lời gọi **get()** và **put()** rồi hy vọng chúng tự phối hợp đúng.

**Thread-safe collection** thường bảo vệ được những thao tác mà hợp đồng của nó xác định, nhưng **chuỗi nhiều lời gọi** chưa chắc nguyên tử. Cần phân biệt:

- **Atomicity (tính nguyên tử):** một thao tác hoặc tổ hợp thao tác được coi là không bị can thiệp theo phạm vi bảo đảm.
- **Visibility (khả năng nhìn thấy):** cập nhật của thread này được thread khác quan sát theo quan hệ đồng bộ phù hợp.
- **Ordering (thứ tự):** những ràng buộc thứ tự xảy ra trước/sau giữa các hành động.
- **Coordination (phối hợp):** khi nào producer chờ, khi nào consumer được đánh thức, khi nào dừng.

Các collection đồng thời giải quyết những nhu cầu khác nhau; không có một cấu trúc phù hợp cho mọi tình huống.

## 2. Các lựa chọn Map và collection phổ biến

| Nhu cầu | Lựa chọn đáng cân nhắc | Điểm cần nhớ |
|---|---|---|
| Map đọc/ghi từ nhiều thread | **ConcurrentHashMap** | Có thao tác atomic theo key; iteration không phải ảnh chụp nhất quán toàn Map |
| Map cần thứ tự theo key và truy cập đồng thời | **ConcurrentSkipListMap** | Sắp xếp theo thứ tự tự nhiên/comparator, chi phí khác HashMap |
| Set concurrent không cần sắp xếp | **ConcurrentHashMap.newKeySet()** | Các thao tác tập hợp dựa trên cơ chế của ConcurrentHashMap |
| Set concurrent cần thứ tự | **ConcurrentSkipListSet** | Có thứ tự và các thao tác điều hướng |
| List có nhiều lượt đọc, rất ít lượt sửa | **CopyOnWriteArrayList** | Mỗi lần sửa thường sao chép cấu trúc mảng; iterator là snapshot |
| Set có nhiều lượt đọc, rất ít lượt sửa | **CopyOnWriteArraySet** | Phù hợp tập dữ liệu tương đối nhỏ, ít cập nhật |
| Queue concurrent không chặn khi rỗng | **ConcurrentLinkedQueue** | **poll()** trả null khi rỗng, không tự chờ |
| Deque concurrent không chặn | **ConcurrentLinkedDeque** | Có thể thao tác hai đầu; không cung cấp chờ |
| Hàng đợi producer–consumer cần chờ | **BlockingQueue** | **put()/take()** có thể chặn; chọn capacity có chủ đích |
| List/Map thường được bọc một khóa chung | **Collections.synchronizedList/Map** | Iteration và tổ hợp thao tác có thể cần khóa ngoài |

Những cấu trúc này phục vụ các hợp đồng khác nhau. Chọn **ConcurrentHashMap** không phải để “thay thế mọi Map”; chọn **BlockingQueue** không phải vì mọi ứng dụng dùng nhiều thread đều cần hàng đợi.

## 3. ConcurrentHashMap: thao tác cơ bản

**ConcurrentHashMap<K, V>** triển khai **ConcurrentMap<K, V>** và hỗ trợ truy cập đồng thời mà không yêu cầu caller khóa cả Map cho mỗi lần gọi thông thường.

~~~java
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;

ConcurrentMap<String, String> status = new ConcurrentHashMap<>();

status.put("order-1", "NEW");
status.put("order-2", "PROCESSING");

System.out.println(status.get("order-1")); // NEW

status.remove("order-2");
System.out.println(status.containsKey("order-2")); // false
~~~

Với chương trình một thread, thao tác trông giống Map thông thường. Lợi ích xuất hiện khi nhiều thread truy cập cùng đối tượng Map.

### Không cho phép null key hoặc null value

ConcurrentHashMap không chấp nhận **null** làm khóa hoặc giá trị. Điều này có ý nghĩa quan trọng trong xử lý đồng thời:

~~~java
ConcurrentHashMap<String, Integer> values =
        new ConcurrentHashMap<>();

// values.put(null, 1);    // Ném NullPointerException.
// values.put("a", null);  // Ném NullPointerException.
~~~

**get(key)** trả null khi không có ánh xạ cho key đó. Vì null value bị cấm, kết quả null không nhập nhằng với trường hợp “key tồn tại nhưng value bằng null”.

Nếu nghiệp vụ cần biểu diễn một giá trị vắng mặt, hãy xác định mô hình thay thế phù hợp: loại bỏ key, dùng kiểu dữ liệu có trạng thái rõ ràng hoặc tổ chức riêng trạng thái nghiệp vụ.

### Map an toàn không đồng nghĩa value cũng an toàn

~~~java
ConcurrentHashMap<String, java.util.ArrayList<String>> groups =
        new ConcurrentHashMap<>();

groups.put("team", new java.util.ArrayList<>());

// Hai thread cùng groups.get("team").add(...)
// vẫn có thể gặp vấn đề vì ArrayList không tự thread-safe.
~~~

ConcurrentHashMap bảo vệ **cấu trúc Map và các thao tác Map** theo hợp đồng của nó; nó không tự làm cho đối tượng value có thể thay đổi trạng thái trở nên thread-safe. Nên chọn value bất biến, atomic value hoặc cấu trúc concurrent phù hợp với nhu cầu của từng key.

## 4. Atomic update: tránh get() rồi put() khi cập nhật cùng key

Đoạn mã sau **không đủ an toàn** để tăng bộ đếm khi nhiều thread cùng cập nhật:

~~~java
// KHÔNG nguyên tử dù counts là ConcurrentHashMap:
int current = counts.getOrDefault("email", 0);
counts.put("email", current + 1);
~~~

Hai lời gọi Map riêng lẻ không tạo thành một giao dịch đọc–sửa–ghi.

ConcurrentMap cung cấp những thao tác hợp thành có ngữ nghĩa rõ hơn:

| Method | Mục tiêu |
|---|---|
| **putIfAbsent(key, value)** | Chỉ thêm ánh xạ khi key chưa có value |
| **replace(key, oldValue, newValue)** | Thay nếu value đang bằng giá trị kỳ vọng |
| **remove(key, value)** | Xóa nếu value hiện tại khớp |
| **computeIfAbsent(key, function)** | Tính value nếu chưa có |
| **computeIfPresent(key, function)** | Tính lại khi đã có ánh xạ |
| **compute(key, function)** | Tính lại dựa vào key và value hiện tại (có thể null nếu vắng mặt) |
| **merge(key, value, function)** | Kết hợp value đã có với value được cung cấp |

### Dùng merge() để đếm

~~~java
import java.util.concurrent.ConcurrentHashMap;

ConcurrentHashMap<String, Integer> counts =
        new ConcurrentHashMap<>();

static void record(
        ConcurrentHashMap<String, Integer> counts,
        String category) {
    counts.merge(category, 1, Integer::sum);
}
~~~

**merge(category, 1, Integer::sum)** có nghĩa:

- Nếu chưa có key, dùng giá trị khởi đầu **1**.
- Nếu đã có, kết hợp value cũ với **1** qua **Integer.sum(...)**.
- Bản cập nhật của key được phối hợp nguyên tử theo hợp đồng của ConcurrentHashMap.

Ví dụ:

~~~java
record(counts, "email");
record(counts, "email");
record(counts, "audit");

System.out.println(counts.get("email")); // 2
System.out.println(counts.get("audit")); // 1
~~~

Nếu dùng nhiều thread, **merge** tránh lost update mà ví dụ **get() + put()** mắc phải.

**Lưu ý:** **Integer** vẫn có giới hạn số nguyên và phép cộng có thể tràn nếu bộ đếm tăng quá lớn. Khi miền giá trị yêu cầu, cân nhắc **Long**, **AtomicLong** hoặc **LongAdder**.

### putIfAbsent() cho khởi tạo một lần theo key

~~~java
ConcurrentHashMap<String, String> routes =
        new ConcurrentHashMap<>();

String previous = routes.putIfAbsent("health", "/health");

System.out.println(previous); // null nếu thêm thành công lần đầu
~~~

Điểm mạnh là việc kiểm tra và thêm được thực hiện như **một thao tác Map**, không phải **containsKey()** rồi **put()** rời rạc.

### replace(key, expected, updated)

~~~java
routes.put("health", "/health");

boolean changed = routes.replace(
        "health", "/health", "/healthz");

System.out.println(changed);             // true
System.out.println(routes.get("health")); // /healthz
~~~

Đây là cách thể hiện cập nhật có điều kiện giống cơ chế *compare-and-set* ở phạm vi một ánh xạ Map, không phải giao dịch trên nhiều key.

## 5. computeIfAbsent() và cách tạo value dùng chung

Một nhu cầu phổ biến là tạo value lần đầu cho mỗi key rồi chia sẻ giữa các thread. Ví dụ tạo bộ đếm cho từng category:

~~~java
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.LongAdder;

ConcurrentHashMap<String, LongAdder> counts =
        new ConcurrentHashMap<>();

void record(String category) {
    counts.computeIfAbsent(
            category,
            ignored -> new LongAdder()
    ).increment();
}
~~~

**computeIfAbsent()** bảo đảm việc thiết lập ánh xạ mới cho key theo cơ chế nguyên tử của Map. **LongAdder.increment()** là thao tác đồng thời phù hợp để nhiều thread tăng bộ đếm mà không cần cập nhật lại chính ánh xạ Map cho mỗi lần tăng.

Khi **computeIfAbsent()** thấy value đã tồn tại, nó trả về value đó mà không cần tạo value mới. Nếu hàm mapping trả **null**, Map không thiết lập ánh xạ cho key.

### Không thực hiện việc chặn lâu trong mapping function

Một lỗi thiết kế:

~~~java
// Không nên dùng computeIfAbsent cho công việc mạng chặn lâu:
cache.computeIfAbsent(
        key,
        ignored -> fetchFromRemoteService()
);
~~~

Nếu **fetchFromRemoteService()** chậm, việc thực thi mapping function có thể làm những cập nhật khác bị ảnh hưởng, tùy cấu trúc nội bộ và tình trạng tranh chấp. Với ConcurrentHashMap, hãy giữ hàm remapping **ngắn, rõ ràng và không có các tương tác nguy hiểm**.

Quan trọng:

- **Không tự cập nhật lại cùng Map bên trong mapping/remapping function.** Một số kiểu đệ quy có thể bị phát hiện và ném **IllegalStateException**; những kiểu phụ thuộc vòng cũng dễ gây khó hiểu hoặc bế tắc.
- **Không đặt tác dụng phụ không thể lặp lại một cách an toàn** vào hàm remapping nếu không hiểu rõ hợp đồng được sử dụng.
- **Không coi việc khởi tạo value là transaction cho mọi công việc bên ngoài** như gửi HTTP hoặc ghi database.
- Nếu cần cache kết quả bất đồng bộ hoặc deduplicate tác vụ I/O nặng, hãy thiết kế riêng một lớp quản lý lifecycle và lỗi, thay vì dùng Map như khóa cho toàn bộ quá trình.

Các thao tác **compute/merge** là công cụ mạnh cho **một key**; để duy trì bất biến trải qua **nhiều key**, cần một thiết kế đồng bộ hoặc mô hình dữ liệu khác.

## 6. LongAdder, AtomicLong và bộ đếm đồng thời

**AtomicLong** và **LongAdder** đều là công cụ hữu ích, nhưng có sự khác biệt.

~~~java
import java.util.concurrent.atomic.AtomicLong;
import java.util.concurrent.atomic.LongAdder;

AtomicLong exactCounter = new AtomicLong();
exactCounter.incrementAndGet();

LongAdder highThroughputCounter = new LongAdder();
highThroughputCounter.increment();

System.out.println(exactCounter.get());      // 1
System.out.println(highThroughputCounter.sum()); // 1
~~~

| Tiêu chí | AtomicLong | LongAdder |
|---|---|---|
| Mục tiêu | Giá trị nguyên tử đơn lẻ | Bộ đếm có nhiều cập nhật đồng thời |
| Tăng | **incrementAndGet()**, **getAndIncrement()** | **increment()**, **add(long)** |
| Đọc | **get()** đọc giá trị nguyên tử tại một thời điểm | **sum()** cộng các thành phần hiện tại |
| Tính chất snapshot khi cập nhật đồng thời | Đọc một biến nguyên tử | **sum()** không phải snapshot nguyên tử trước các cập nhật đồng thời |
| Dùng cho ID tăng tuần tự | Có thể phù hợp với **getAndIncrement()** | Không phù hợp khi cần ID/sequence duy nhất từ mỗi lần tăng |

**LongAdder.sum()** là lựa chọn tốt cho thống kê hoặc số liệu đo lường có thể chấp nhận rằng việc đọc trong lúc cập nhật không phải một thời điểm nguyên tử duy nhất. Khi các thread cập nhật đã hoàn tất và được **join()** đúng cách, đọc tổng sẽ phản ánh những cập nhật đó.

Ví dụ bộ đếm theo khóa:

~~~java
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.LongAdder;

ConcurrentHashMap<String, LongAdder> totals =
        new ConcurrentHashMap<>();

String category = "downloads";

totals.computeIfAbsent(
        category, ignored -> new LongAdder()
).increment();
~~~

Không cần đồng bộ thêm chỉ để cùng lúc tăng **LongAdder** đang được chia sẻ hợp lệ.

## 7. Iterator và view của ConcurrentHashMap

Các collection view như **keySet()**, **values()**, **entrySet()** cho phép duyệt dữ liệu của ConcurrentHashMap.

~~~java
ConcurrentHashMap<String, Integer> scores =
        new ConcurrentHashMap<>();

scores.put("A", 10);
scores.put("B", 20);

for (var entry : scores.entrySet()) {
    System.out.println(
            entry.getKey() + "=" + entry.getValue());
}
~~~

Khi những thread khác đồng thời sửa Map, iterator của ConcurrentHashMap có tính chất **weakly consistent**: nó có thể phản ánh một số cập nhật xảy ra trong lúc duyệt, không cung cấp snapshot nguyên tử toàn Map, và không dùng cơ chế fail-fast kiểu thông thường để báo **ConcurrentModificationException** chỉ vì có cập nhật đồng thời.

### Đừng dựa vào thứ tự duyệt

ConcurrentHashMap **không bảo đảm thứ tự theo insertion hoặc theo key**. Nếu cần thứ tự theo khóa, xem **ConcurrentSkipListMap**; nếu cần snapshot có thứ tự nhất quán tại một thời điểm nghiệp vụ, có thể phải tạo bản sao trong ranh giới đồng bộ phù hợp.

### size() không phải điều kiện phối hợp

~~~java
if (!scores.isEmpty()) {
    // Không có nghĩa một key cụ thể chắc chắn còn ở đây.
}
~~~

Khi Map đang thay đổi, **size()**, **isEmpty()** hoặc **containsValue()** có thể không đại diện cho một trạng thái ổn định phù hợp để ra quyết định cần tính nguyên tử trên nhiều bước.

Nếu cần một thống kê kích thước quy mô lớn, ConcurrentHashMap cung cấp **mappingCount()** trả về **long**, nhưng kết quả vẫn có thể là ước lượng khi cập nhật đồng thời. Không nên dùng nó như cơ chế khóa hoặc đồng bộ.

### Có thể chụp snapshot không?

~~~java
Map<String, Integer> copy = Map.copyOf(scores);
~~~

Kết quả là một Map không sửa được theo API của nó, nhưng việc sao chép từ một nguồn đang cập nhật đồng thời **không tự đảm bảo một snapshot nguyên tử tại cùng một thời điểm**. Nếu toàn bộ dữ liệu phải tương ứng một version nghiệp vụ, cần cơ chế phiên bản hóa hoặc đồng bộ ở cấp ứng dụng.

## 8. Tập hợp Set và thao tác bulk của ConcurrentHashMap

### Tạo concurrent Set

~~~java
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;

Set<String> processedIds = ConcurrentHashMap.newKeySet();

processedIds.add("task-1");
processedIds.add("task-2");

boolean firstTime = processedIds.add("task-1");

System.out.println(firstTime); // false
~~~

**newKeySet()** cung cấp một Set concurrent, hữu ích để lưu các ID đã được đánh dấu. Phương thức **add()** trả true khi Set thay đổi do phần tử chưa có.

Nếu mục tiêu là **chỉ một thread giành quyền đánh dấu một key**, có thể dùng:

~~~java
if (processedIds.add(taskId)) {
    // Thread này là thread đầu tiên thêm taskId thành công.
}
~~~

Tuy vậy, **đánh dấu đã xử lý** và **thực sự hoàn tất tác vụ** là hai trạng thái khác nhau. Nếu công việc thất bại sau khi thêm key, cần thiết kế trạng thái retry hoặc hoàn tác phù hợp.

### Bulk operations

ConcurrentHashMap còn có các method như:

- **forEach(...)** để áp dụng hành động lên các ánh xạ.
- **search(...)** để tìm kết quả thích hợp.
- **reduce(...)** để tổng hợp dữ liệu.

Một số overload chấp nhận **parallelismThreshold** để cho phép xử lý song song khi quy mô đạt ngưỡng.

Ví dụ duyệt tuần tự theo cấu hình ngưỡng:

~~~java
ConcurrentHashMap<String, Integer> values =
        new ConcurrentHashMap<>();

values.put("one", 1);
values.put("two", 2);

values.forEach(
        Long.MAX_VALUE,
        (key, value) -> System.out.println(key + "=" + value)
);
~~~

Ngưỡng lớn như **Long.MAX_VALUE** dùng khi không muốn chia công việc xử lý song song. Đây không phải là API snapshot hay transaction: nếu Map thay đổi đồng thời, kết quả quan sát vẫn tuân theo hợp đồng yếu nhất quán.

Trong bulk operation song song, tránh phụ thuộc vào thứ tự, tránh side effect không an toàn và bảo đảm thao tác tổng hợp phù hợp với cách thực thi song song.

## 9. Concurrent collection: những biến thể ngoài ConcurrentHashMap

**java.util.concurrent** có các collection và queue với mục tiêu khác nhau. Điều quan trọng là hiểu **chiến lược đồng thời**, không chỉ nhớ tên lớp.

### CopyOnWriteArrayList: tối ưu cho đọc nhiều, ghi ít

~~~java
import java.util.Iterator;
import java.util.concurrent.CopyOnWriteArrayList;

CopyOnWriteArrayList<String> listeners =
        new CopyOnWriteArrayList<>();

listeners.add("A");
listeners.add("B");

Iterator<String> iterator = listeners.iterator();

listeners.add("C");

while (iterator.hasNext()) {
    System.out.println(iterator.next());
}
~~~

Kết quả:

~~~text
A
B
~~~

Iterator ở đây dựa trên snapshot của mảng tại thời điểm tạo iterator. Thao tác thêm **"C"** sau đó không xuất hiện trong lần duyệt này.

Đặc điểm:

- Đọc và duyệt rất thuận tiện khi thay đổi xảy ra ít.
- Các thao tác sửa cấu trúc thường phải sao chép mảng, nên chi phí tăng theo kích thước danh sách.
- Iterator là snapshot và **không hỗ trợ thao tác remove() của iterator**.
- Snapshot của mảng chỉ sao chép **tham chiếu**; đối tượng phần tử có thể thay đổi trạng thái vẫn cần hợp đồng an toàn riêng.

**CopyOnWriteArraySet** có đặc tính tương tự cho Set, phù hợp với danh sách nhỏ các listener, callback hoặc registry ít thay đổi.

### Khi nào không nên dùng CopyOnWriteArrayList?

Nếu nhiều thread liên tục **add()**, **remove()** hoặc thay đổi danh sách lớn, chi phí sao chép trên các cập nhật có thể vượt xa lợi ích của việc duyệt snapshot. Hãy đo bằng workload thực tế.

## 10. ConcurrentLinkedQueue và ConcurrentLinkedDeque

**ConcurrentLinkedQueue<E>** là queue concurrent kiểu FIFO không chặn, phù hợp với trường hợp caller muốn thêm hoặc lấy phần tử **mà không cần chờ**.

~~~java
import java.util.concurrent.ConcurrentLinkedQueue;

ConcurrentLinkedQueue<String> events =
        new ConcurrentLinkedQueue<>();

events.offer("created");
events.offer("modified");

System.out.println(events.poll()); // created
System.out.println(events.poll()); // modified
System.out.println(events.poll()); // null
~~~

Điểm quan trọng:

- **offer(e)** thêm phần tử nếu hợp lệ, không chờ còn sức chứa theo cơ chế bounded queue.
- **poll()** trả về phần tử hoặc **null** khi không có phần tử tại thời điểm gọi.
- Queue không chấp nhận phần tử **null**, nhờ đó null có thể biểu diễn “không có kết quả” khi poll.
- Iterator có đặc tính weakly consistent, không phải snapshot cố định của toàn queue.

**ConcurrentLinkedDeque<E>** cho phép thao tác ở cả hai đầu, ví dụ **offerFirst()**, **offerLast()**, **pollFirst()**, **pollLast()**.

~~~java
import java.util.concurrent.ConcurrentLinkedDeque;

ConcurrentLinkedDeque<String> deque =
        new ConcurrentLinkedDeque<>();

deque.offerFirst("priority");
deque.offerLast("normal");

System.out.println(deque.pollFirst()); // priority
System.out.println(deque.pollLast());  // normal
~~~

Một concurrent queue không chặn **không tự cung cấp cơ chế backpressure dựa trên sức chứa giới hạn**. Nếu producer nhanh hơn consumer trong thời gian dài, lượng dữ liệu tồn đọng có thể tăng và gây áp lực bộ nhớ. Khi cần chờ và giới hạn số phần tử, hãy xem BlockingQueue.

## 11. ConcurrentSkipListMap và ConcurrentSkipListSet

Nếu ứng dụng vừa cần truy cập đồng thời vừa cần **thứ tự đã xác định của key**, có thể dùng **ConcurrentSkipListMap**:

~~~java
import java.util.concurrent.ConcurrentSkipListMap;

ConcurrentSkipListMap<Integer, String> tasks =
        new ConcurrentSkipListMap<>();

tasks.put(20, "medium");
tasks.put(10, "high");
tasks.put(30, "low");

System.out.println(tasks.firstKey()); // 10
System.out.println(tasks.lastKey());  // 30

tasks.forEach((priority, task) ->
        System.out.println(priority + ": " + task));
~~~

Kết quả duyệt theo key:

~~~text
10: high
20: medium
30: low
~~~

**ConcurrentSkipListMap** là một **ConcurrentNavigableMap**, hỗ trợ các thao tác điều hướng như **firstEntry()**, **higherKey()**, **subMap()** theo hợp đồng tương ứng.

**ConcurrentSkipListSet** cung cấp Set có thứ tự dựa trên cùng hướng thiết kế.

Lựa chọn này thường có chi phí khác ConcurrentHashMap vì phải duy trì quan hệ thứ tự. Đừng chọn chỉ vì muốn thấy thứ tự duyệt “đẹp hơn” nếu bài toán không cần truy cập có thứ tự.

## 12. Collections.synchronizedMap/List khác concurrent collection chuyên biệt

Java cũng có các wrapper như:

~~~java
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

List<String> names =
        Collections.synchronizedList(new ArrayList<>());

Map<String, Integer> counts =
        Collections.synchronizedMap(new HashMap<>());
~~~

Các wrapper này đồng bộ các lời gọi truy cập thích hợp theo khóa của wrapper. Tuy nhiên, **iteration hoặc tổ hợp nhiều lời gọi** vẫn có thể cần caller giữ cùng khóa trong suốt đoạn thao tác.

Ví dụ duyệt một synchronized list:

~~~java
synchronized (names) {
    for (String name : names) {
        System.out.println(name);
    }
}
~~~

Nếu không đồng bộ đúng khi duyệt, cập nhật đồng thời có thể gây hành vi không mong muốn hoặc ngoại lệ ở iterator tùy trường hợp.

So sánh:

| Đặc điểm | synchronizedMap wrapper | ConcurrentHashMap |
|---|---|---|
| Cơ chế truy cập | Thông thường đồng bộ trên một khóa của wrapper | Cơ chế concurrent chuyên biệt |
| Duyệt khi có cập nhật đồng thời | Thường cần đồng bộ bên ngoài | Iterator weakly consistent |
| null key/value | Tùy Map nền, ví dụ HashMap cho phép null | Không cho phép |
| Atomic operation | Phụ thuộc hợp đồng wrapper và cách dùng khóa chung | Có những thao tác atomic theo key |
| Tổ hợp nghiệp vụ nhiều bước | Có thể cần giữ khóa trong toàn bộ tổ hợp | Không tự trở thành transaction nhiều key |

Một wrapper synchronized vẫn có giá trị khi ứng dụng cần một cơ chế khóa đơn giản và có thể giữ cùng khóa cho cả bất biến nghiệp vụ. Không nên tự suy diễn rằng thay nó bằng ConcurrentHashMap sẽ giữ nguyên mọi tính chất đồng bộ của một khối nhiều thao tác.

## 13. BlockingQueue là gì?

**BlockingQueue<E>** là interface thuộc **java.util.concurrent** mở rộng **Queue<E>**, bổ sung các thao tác có thể **chờ**:

- **put(e)**: chờ nếu queue chưa thể nhận thêm phần tử.
- **take()**: chờ nếu queue chưa có phần tử.
- **offer(e, timeout, unit)**: chờ tối đa khoảng thời gian chỉ định để thêm phần tử.
- **poll(timeout, unit)**: chờ tối đa khoảng thời gian chỉ định để lấy phần tử.

Ví dụ:

~~~java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;

BlockingQueue<String> queue = new ArrayBlockingQueue<>(2);

queue.put("A");
queue.put("B");

// queue.put("C") sẽ chờ cho tới khi có chỗ trống,
// nếu không bị gián đoạn.

System.out.println(queue.take()); // A
System.out.println(queue.take()); // B
~~~

Các lời gọi **put()** và **take()** có thể ném **InterruptedException**; đoạn mã cần nằm trong một method khai báo hoặc xử lý ngoại lệ đó.

### BlockingQueue không cho phép null

Không thêm **null** vào BlockingQueue. Giá trị **null** được dành cho kết quả của các phương thức như **poll()** khi không lấy được phần tử, thay vì biểu diễn một item hợp lệ.

BlockingQueue cũng **không có method close() chuẩn**. Việc dừng các consumer phải được thiết kế ở cấp ứng dụng, ví dụ thông qua tín hiệu hủy, interruption hoặc một loại thông điệp kết thúc riêng.

## 14. Bốn nhóm phương thức của BlockingQueue

BlockingQueue có nhiều thao tác gần nhau về chức năng nhưng khác về **cách phản ứng khi queue đầy hoặc rỗng**:

| Mục tiêu | Ném exception ngay nếu không thể | Trả giá trị đặc biệt ngay | Chờ vô thời hạn | Chờ có giới hạn |
|---|---|---|---|---|
| Thêm phần tử | **add(e)** | **offer(e)** trả false | **put(e)** | **offer(e, time, unit)** |
| Lấy và loại phần tử | **remove()** | **poll()** trả null | **take()** | **poll(time, unit)** |
| Xem đầu queue | **element()** | **peek()** trả null | Không có | Không có |

Lưu ý:

- Cột “ném exception” biểu diễn tình huống không thể thực hiện do queue đầy/rỗng; những lỗi đối số khác vẫn có thể xảy ra ở các phương thức khác.
- **put/take** là thao tác có thể chờ và nhận **InterruptedException**.
- **offer(timeout)** trả false nếu hết thời gian mà chưa thêm được; **poll(timeout)** trả null nếu hết thời gian mà chưa lấy được.
- **remove()** không tham số ném **NoSuchElementException** nếu queue rỗng; **add(e)** trên queue giới hạn có thể ném **IllegalStateException** nếu không còn khả năng chứa.
- **peek()** xem đầu queue mà không loại bỏ phần tử.

Ví dụ giới hạn chờ:

~~~java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.TimeUnit;

BlockingQueue<String> queue = new ArrayBlockingQueue<>(1);
queue.put("first");

boolean accepted = queue.offer(
        "second", 100, TimeUnit.MILLISECONDS);

System.out.println(accepted); // false nếu không có consumer lấy phần tử
~~~

Kết quả phụ thuộc vào có thread khác tiêu thụ phần tử trong khoảng chờ hay không. Ví dụ minh họa hành vi timeout của một queue không có consumer đồng thời.

## 15. Những triển khai BlockingQueue phổ biến

| Triển khai | Sức chứa | Thứ tự/đặc tính | Phù hợp |
|---|---|---|---|
| **ArrayBlockingQueue** | Cố định, khai báo khi tạo | FIFO; có lựa chọn fairness khi tạo | Pipeline cần giới hạn backlog rõ ràng |
| **LinkedBlockingQueue** | Có thể khai báo giới hạn; constructor mặc định có capacity rất lớn | FIFO | Hàng đợi đa producer/consumer cần linh hoạt |
| **PriorityBlockingQueue** | Không có giới hạn sức chứa hữu hạn do constructor capacity đặt ra | Theo priority qua Comparable/Comparator | Lấy công việc theo độ ưu tiên, không phải FIFO |
| **DelayQueue** | Không giới hạn thông thường | Phần tử chỉ được lấy khi độ trễ đã hết; cần **Delayed** | Công việc được phép chạy sau thời điểm trì hoãn |
| **SynchronousQueue** | Không lưu phần tử, capacity bằng 0 | Producer giao trực tiếp cho consumer đang chờ | Chuyển giao trực tiếp, không có backlog |
| **LinkedTransferQueue** | Không giới hạn thông thường | FIFO; hỗ trợ **transfer()** chờ consumer nhận | Giao tiếp cần chuyển giao trực tiếp trong một số thao tác |
| **LinkedBlockingDeque** | Có thể giới hạn capacity | Hai đầu queue; triển khai **BlockingDeque** | Chèn/lấy ở đầu hoặc cuối có thể chờ |

### ArrayBlockingQueue: kiểm soát tải bằng capacity

~~~java
BlockingQueue<String> tasks = new ArrayBlockingQueue<>(100);
~~~

Tối đa 100 phần tử có thể chờ trong queue theo capacity khai báo. Khi queue đầy, **put()** chờ cho tới khi có consumer lấy phần tử.

Constructor có tham số **fair** có thể điều chỉnh chính sách phục vụ các thread đang chờ; fairness có thể giảm throughput trong một số workload. Đừng bật chỉ vì nghĩ rằng “fair” tự bảo đảm thứ tự nghiệp vụ của tất cả tác vụ.

### LinkedBlockingQueue: chú ý constructor không giới hạn tường minh

~~~java
import java.util.concurrent.LinkedBlockingQueue;

BlockingQueue<String> bounded =
        new LinkedBlockingQueue<>(1000);
~~~

Đối với **new LinkedBlockingQueue<>()** không chỉ định capacity, giới hạn mặc định là **Integer.MAX_VALUE**. Trong thực tế, queue có thể tăng backlog tới khi gây áp lực bộ nhớ trước khi chạm giới hạn lý thuyết. Với hệ thống có producer không kiểm soát, nên chọn capacity có chủ đích.

### PriorityBlockingQueue và DelayQueue

Các queue này có cơ chế lấy phần tử đặc biệt. **PriorityBlockingQueue** không bảo đảm lấy theo thứ tự đưa vào khi mức ưu tiên giống nhau; **DelayQueue** chỉ trả các phần tử đã hết thời gian delay theo hợp đồng **Delayed**.

Một queue có ưu tiên **không tự giới hạn lượng công việc đang chờ**. Nếu cần cả priority và giới hạn tải, có thể phải thiết kế thêm cơ chế kiểm soát ở cấp ứng dụng.

### SynchronousQueue: không phải queue lưu việc

~~~java
import java.util.concurrent.SynchronousQueue;

SynchronousQueue<String> handoff = new SynchronousQueue<>();
~~~

Queue này không chứa phần tử tồn đọng: mỗi lần thêm thành công cần được ghép với một lần nhận tương ứng. **put()** có thể chờ consumer nhận; **take()** có thể chờ producer cung cấp.

SynchronousQueue đặc biệt hữu ích khi cần một điểm **handoff**, không phải một vùng đệm chứa các công việc đang chờ.

## 16. Backpressure: producer nhanh hơn consumer

Một tình huống quen thuộc:

~~~text
Producer tạo 1.000 task/giây
             |
             v
        Hàng đợi
             |
             v
Consumer xử lý 100 task/giây
~~~

Nếu hàng đợi không có giới hạn hữu hiệu, số task tồn đọng có thể tăng theo thời gian. Nếu queue bị giới hạn capacity, producer phải **chờ, từ chối hoặc điều tiết** khi không còn chỗ.

Đó là cách dùng queue để triển khai **backpressure**: tốc độ tạo công việc bị ràng buộc bởi năng lực tiếp nhận hoặc xử lý ở hạ nguồn.

### Ba chiến lược phổ biến

1. **Chờ:** dùng **put()** khi producer được phép block, thích hợp cho một pipeline đã xác định rõ khả năng dừng.
2. **Chờ có timeout:** dùng **offer(e, timeout, unit)**, sau đó trả lỗi hoặc retry theo chính sách có giới hạn.
3. **Không chờ:** dùng **offer(e)** và xử lý false, ví dụ từ chối yêu cầu hoặc ghi nhận trạng thái cần xử lý lại.

~~~java
import java.util.concurrent.TimeUnit;

boolean accepted = queue.offer(
        task, 250, TimeUnit.MILLISECONDS);

if (!accepted) {
    // Queue đang quá tải theo chính sách timeout;
    // trả phản hồi hoặc đưa vào cơ chế retry có giới hạn.
}
~~~

Không nên **lặng lẽ bỏ task** khi **offer()** trả false nếu ứng dụng có hợp đồng không được mất dữ liệu. Cần một cách giải quyết rõ ràng: retry có giới hạn, lưu bền vững, báo lỗi cho caller hoặc chuyển tải sang nơi khác.

### remainingCapacity() không khóa chỗ trống

~~~java
if (queue.remainingCapacity() > 0) {
    // Không có bảo đảm thread khác sẽ không lấy chỗ trước khi put/offer.
}
~~~

Dùng **offer()** hoặc **put()** trực tiếp thay vì kiểm tra rồi hành động với giả định hai bước là nguyên tử.

## 17. Mẫu producer–consumer với BlockingQueue

Mỗi producer tạo công việc và đưa vào queue. Một hoặc nhiều consumer lấy công việc để xử lý:

~~~text
 Producer A ----\
                 \
 Producer B ------> BlockingQueue (capacity N)
                 /             |
 Producer C ----/              v
                          Consumer 1
                          Consumer 2
~~~

Các lợi ích:

- Producer và consumer không phải gọi nhau trực tiếp.
- Số lượng công việc đang chờ được kiểm soát nếu queue có capacity.
- Consumer có thể **take()** để chờ mà không phải tự viết busy loop.
- Nhiều thread có thể truy cập queue mà không cần khóa riêng cho thao tác queue thông thường.

Tuy vậy, cần có **giao thức dừng** và **chính sách khi xử lý task thất bại**. Chỉ đặt task vào queue không bảo đảm task sẽ được xử lý thành công; nếu tiến trình bị dừng hoặc consumer ném lỗi, công việc có thể chưa hoàn thành.

## 18. Ví dụ hoàn chỉnh: hai consumer, queue giới hạn và ConcurrentHashMap

Ví dụ sau dùng API ổn định trên Java 27:

- **ArrayBlockingQueue** có capacity 3 để giới hạn số task chờ.
- Hai **virtual thread** thực thi vai trò consumer.
- **ConcurrentHashMap<String, LongAdder>** đếm số task đã xử lý theo category.
- Một thông điệp **Stop** riêng, không dùng null làm “poison pill”.
- Sau khi consumer đã **join()**, chương trình in kết quả cuối cùng có thể xác định được.

Lưu vào **WorkQueueDemo.java**:

~~~java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.LongAdder;

public final class WorkQueueDemo {
    private WorkQueueDemo() {}

    private sealed interface Message permits Job, Stop {}

    private record Job(String category) implements Message {}

    private enum Stop implements Message {
        INSTANCE
    }

    private static void consume(
            BlockingQueue<Message> queue,
            ConcurrentHashMap<String, LongAdder> totals) {

        try {
            while (true) {
                Message message = queue.take();

                if (message == Stop.INSTANCE) {
                    return;
                }

                Job job = (Job) message;

                totals.computeIfAbsent(
                        job.category(),
                        ignored -> new LongAdder()
                ).increment();
            }
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
        }
    }

    public static void main(String[] args)
            throws InterruptedException {

        BlockingQueue<Message> queue = new ArrayBlockingQueue<>(3);

        ConcurrentHashMap<String, LongAdder> totals =
                new ConcurrentHashMap<>();

        Thread first = Thread.ofVirtual()
                .name("consumer-1")
                .start(() -> consume(queue, totals));

        Thread second = Thread.ofVirtual()
                .name("consumer-2")
                .start(() -> consume(queue, totals));

        String[] jobs = {
                "email", "audit", "email",
                "report", "audit", "email"
        };

        for (String category : jobs) {
            queue.put(new Job(category));
        }

        // Có hai consumer => gửi hai tín hiệu kết thúc.
        queue.put(Stop.INSTANCE);
        queue.put(Stop.INSTANCE);

        first.join();
        second.join();

        System.out.println("email=" + totals.get("email").sum());
        System.out.println("audit=" + totals.get("audit").sum());
        System.out.println("report=" + totals.get("report").sum());
    }
}
~~~

Kết quả:

~~~text
email=3
audit=2
report=1
~~~

**Giải thích cơ chế:**

1. Producer ở **main()** gọi **put()**. Nếu queue đầy, main chờ cho tới khi consumer lấy bớt task.
2. Hai consumer gọi **take()** để nhận Message. Queue phân phối mỗi phần tử được lấy cho **một consumer**, không phát bản sao cho cả hai.
3. **Job** và **Stop** là các biến thể riêng của một sealed interface, tránh dùng chuỗi đặc biệt có thể đụng với dữ liệu nghiệp vụ.
4. Consumer gặp **Stop.INSTANCE** thì thoát vòng lặp. Có hai consumer nên producer gửi **hai phần tử Stop**.
5. **computeIfAbsent()** bảo đảm mỗi category có một LongAdder dùng chung; **increment()** hỗ trợ tăng đồng thời.
6. **join()** chờ cả hai consumer kết thúc. Chỉ sau đó **sum()** mới được dùng để in kết quả cuối mà không còn cập nhật song song từ các consumer.
7. Virtual thread là cơ chế thread hiện hành của Java, phù hợp với nhiều tác vụ chờ I/O; **nó không thay đổi tính an toàn của collection**. Ví dụ này dùng virtual thread chỉ để thể hiện khả năng sử dụng với BlockingQueue.

Ví dụ cố ý đơn giản: các task chỉ tăng bộ đếm, không có I/O thực hoặc lỗi nghiệp vụ. Nếu thread **main** bị interrupt giữa lúc gửi task và các tín hiệu Stop, ứng dụng thật cần cơ chế hủy/đóng có kiểm soát để tránh để consumer chờ mãi. Với task thực tế, cũng phải xác định retry, dead-letter, thứ tự xử lý và khả năng mất việc khi tiến trình dừng.

## 19. Dừng consumer: interruption, cờ dừng và poison pill

**BlockingQueue không có close() chuẩn**. Một consumer đang **take()** có thể chờ vô thời hạn nếu không còn producer và không có cơ chế dừng.

### Cách 1: dùng interruption

~~~java
Thread consumer = Thread.ofVirtual().start(() -> {
    try {
        while (true) {
            String work = queue.take();
            System.out.println("Work: " + work);
        }
    } catch (InterruptedException exception) {
        Thread.currentThread().interrupt();
    }
});

// Ở vị trí điều khiển dừng:
consumer.interrupt();
~~~

Lời gọi **take()** đang chờ có thể bị đánh thức bằng **InterruptedException**. Khi một method quyết định không ném tiếp ngoại lệ, thường nên khôi phục trạng thái interrupt bằng **Thread.currentThread().interrupt()**, sau đó kết thúc hoặc chuyển yêu cầu hủy lên tầng trên.

Không dùng vòng lặp:

~~~java
// Sai về mặt thiết kế hủy:
// while (true) {
//     try {
//         process(queue.take());
//     } catch (InterruptedException ignored) {
//         // Bỏ qua hủy và tiếp tục chờ mãi.
//     }
// }
~~~

Nếu cố ý tiếp tục xử lý sau khi bị interrupt, cần có chính sách rõ ràng; việc nuốt tín hiệu hủy không chủ đích khiến chương trình khó dừng.

### Cách 2: poison pill hoặc thông điệp kết thúc

Ví dụ **WorkQueueDemo** dùng **Stop.INSTANCE**. Với nhiều consumer, phải gửi đủ tín hiệu hoặc có giao thức kết thúc khác để từng consumer biết lúc nào dừng.

Những điểm cần cân nhắc:

- Gửi thông điệp kết thúc **sau** khi mọi producer liên quan đã hoàn tất gửi task cần xử lý.
- Không được lẫn tín hiệu kết thúc với dữ liệu hợp lệ.
- Nếu một consumer có thể chết vì lỗi không kiểm soát, việc gửi đủ poison pill không tự bảo đảm các consumer còn lại dừng.
- Với queue giới hạn, việc gửi poison pill cũng có thể chờ nếu queue đầy; đường shutdown phải được thiết kế để tránh deadlock.
- Nếu nhiều producer hoạt động, một producer gửi Stop quá sớm có thể khiến consumer thoát khi producer khác vẫn còn task.

### Cách 3: poll(timeout) với tín hiệu dừng

~~~java
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

AtomicBoolean running = new AtomicBoolean(true);

while (running.get()) {
    String work = queue.poll(200, TimeUnit.MILLISECONDS);

    if (work != null) {
        process(work);
    }
}
~~~

Mẫu này giả định **queue** và method **process(...)** đã tồn tại, đồng thời vòng lặp được đặt trong một method xử lý hoặc khai báo **InterruptedException**. Khi một thread khác đặt **running.set(false)**, consumer có thể nhận ra trong một lần thức dậy sau đó.

**AtomicBoolean** giúp chia sẻ tín hiệu dừng an toàn giữa các thread, nhưng vòng lặp này không bảo đảm tự động xử lý hết các task còn trong queue trước khi thoát. Phải xác định mục tiêu: dừng ngay hay drain hết backlog.

## 20. Memory consistency và nguyên tắc nhìn thấy dữ liệu

Hợp đồng của các cấu trúc đồng thời không chỉ nói về việc tránh ngoại lệ mà còn liên quan tới **Java Memory Model**.

Ví dụ, **BlockingQueue** cung cấp quan hệ memory consistency quan trọng: những hành động trong thread producer xảy ra **trước khi đưa một đối tượng vào BlockingQueue** được bảo đảm xảy ra-trước (*happens-before*) những hành động sau khi thread khác **truy cập hoặc loại bỏ đối tượng đó** từ queue, theo hợp đồng API.

Nhờ vậy, cách giao việc sau là một mô hình trao đổi an toàn khi dùng đúng:

~~~java
record Task(String text) {}

BlockingQueue<Task> queue = new ArrayBlockingQueue<>(10);

// Producer:
queue.put(new Task("ready"));

// Consumer:
Task task = queue.take();
System.out.println(task.text());
~~~

Nhưng quy tắc đó **không biến một Task có field mutable không được đồng bộ trở thành an toàn cho mọi lần sửa sau khi đã đưa vào queue**. Cách thiết kế đơn giản là tạo một đối tượng bất biến và không tiếp tục thay đổi trạng thái của nó sau khi công bố.

Với **ConcurrentHashMap**, các quy tắc đồng bộ của nó đảm bảo rằng khi một thread đọc được một giá trị được đưa vào Map theo đường đi phù hợp, trạng thái công bố của value có quan hệ happens-before cần thiết với việc đọc đó. Tuy nhiên, việc cập nhật các field mutable bên trong value sau đó vẫn phải được bảo vệ theo hợp đồng của chính value.

### Thread.join() để chờ hoàn thành

~~~java
Thread worker = Thread.ofVirtual().start(() -> {
    // Ghi dữ liệu cần công bố.
});

worker.join();

// Sau khi join thành công, hành động của worker
// xảy ra-trước những hành động tiếp theo của thread này.
~~~

Khi cần đọc kết quả cuối cùng của tác vụ, **join()** hoặc cơ chế đồng bộ hoàn tất tương ứng giúp thiết lập thứ tự và khả năng nhìn thấy cần thiết.

Không dùng **Thread.sleep(...)** như một cách “đợi cho chắc” thay thế đồng bộ: một khoảng ngủ cố định không chứng minh thread khác đã hoàn thành.

## 21. Kiểm thử collection đồng thời

Lỗi race condition thường không lộ ra khi chỉ chạy một thread hoặc thêm một vài lần **sleep()**. Có thể dùng **CountDownLatch** để phối hợp các thread bắt đầu công việc và kiểm tra kết quả.

Ví dụ độc lập **ConcurrentCounterTest.java**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CountDownLatch;

public class ConcurrentCounterTest {
    public static void main(String[] args)
            throws InterruptedException {

        int workers = 4;
        int incrementsPerWorker = 1_000;

        ConcurrentHashMap<String, Integer> counts =
                new ConcurrentHashMap<>();

        CountDownLatch ready = new CountDownLatch(workers);
        CountDownLatch start = new CountDownLatch(1);

        List<Thread> threads = new ArrayList<>();

        for (int i = 0; i < workers; i++) {
            Thread worker = Thread.ofPlatform().start(() -> {
                ready.countDown();

                try {
                    start.await();

                    for (int j = 0; j < incrementsPerWorker; j++) {
                        counts.merge("event", 1, Integer::sum);
                    }
                } catch (InterruptedException exception) {
                    Thread.currentThread().interrupt();
                }
            });

            threads.add(worker);
        }

        ready.await();
        start.countDown();

        for (Thread worker : threads) {
            worker.join();
        }

        int actual = counts.getOrDefault("event", 0);
        int expected = workers * incrementsPerWorker;

        System.out.println("expected=" + expected);
        System.out.println("actual=" + actual);
    }
}
~~~

Kết quả nếu không có interrupt ngoài ý muốn:

~~~text
expected=4000
actual=4000
~~~

**CountDownLatch** làm các worker chờ cùng một tín hiệu bắt đầu, giúp tăng khả năng cạnh tranh đồng thời; nó không bảo đảm tất cả thread thực hiện từng bước chính xác cùng một thời điểm.

Ở đây, **merge()** cập nhật nguyên tử theo key. Sau khi **join()** hoàn tất, giá trị được kiểm tra đã nhận các cập nhật của các worker không bị gián đoạn. Nếu viết cùng thử nghiệm bằng **get() + put()**, có thể quan sát lost update, nhưng race có xuất hiện trong một lần chạy cụ thể hay không vẫn phụ thuộc lịch thực thi.

### Điều gì cần kiểm thử thêm?

- Cùng key bị nhiều thread cập nhật.
- Nhiều key được cập nhật đồng thời.
- Producer nhanh hơn consumer và queue đầy.
- Consumer chờ trên queue rỗng.
- Timeout khi dùng **offer/poll**.
- Interrupt khi thread đang chờ.
- Dừng hệ thống khi còn task tồn đọng.
- Lỗi trong task, retry và khả năng xử lý trùng.
- Không giả định thứ tự ngoài những bảo đảm thực tế của cấu trúc.

Kiểm thử đồng thời nên hướng vào **bất biến và hợp đồng**, không phải đúng thứ tự dòng log của các thread.

## 22. Những lỗi thiết kế thường gặp

| Lỗi | Vấn đề | Cách cải thiện |
|---|---|---|
| Dùng **HashMap** để nhiều thread cùng ghi | Không có hợp đồng cập nhật concurrent phù hợp | Chọn ConcurrentHashMap hoặc đồng bộ trên ranh giới phù hợp |
| Dùng **get() + put()** để tăng counter | Lost update vì hai lời gọi không nguyên tử | Dùng **merge/compute** hoặc **LongAdder** |
| Cho rằng value trong ConcurrentHashMap tự thread-safe | Chỉ Map được bảo đảm theo hợp đồng Map | Dùng value bất biến/atomic/concurrent |
| Đưa **null** vào ConcurrentHashMap hoặc BlockingQueue | Cả hai không chấp nhận null | Thiết kế trạng thái vắng mặt rõ ràng |
| Dùng **size()** làm cơ chế phối hợp chính xác | Kích thước có thể thay đổi ngay hoặc là ước lượng | Dùng atomic operation, latch hoặc giao thức nghiệp vụ |
| Cho rằng iterator của ConcurrentHashMap là snapshot | Iterator weakly consistent | Nếu cần ảnh chụp nhất quán, thiết kế cơ chế riêng |
| Dùng CopyOnWriteArrayList khi ghi liên tục | Chi phí copy khi sửa | Chọn cấu trúc hợp workload |
| Dùng ConcurrentLinkedQueue nhưng mong **take()** | Queue không chặn không có take | Dùng BlockingQueue nếu cần chờ |
| Dùng queue không giới hạn với producer nhanh | Backlog có thể lớn dẫn tới thiếu bộ nhớ | Chọn bounded queue và backpressure |
| Bỏ qua kết quả false của **offer()** | Task có thể bị mất không thông báo | Xử lý từ chối, retry hoặc lưu bền vững |
| Kiểm tra **remainingCapacity()** rồi thêm | Race giữa kiểm tra và hành động | Gọi **offer/put** trực tiếp |
| Bắt **InterruptedException** rồi bỏ qua | Hệ thống khó shutdown | Tôn trọng hủy; restore interrupt hoặc propagate |
| Cho rằng BlockingQueue có **close()** | API không có close chuẩn | Thiết kế shutdown protocol |
| Gửi một poison pill cho nhiều consumer | Một số consumer vẫn chờ | Gửi đủ tín hiệu hoặc dùng cơ chế dừng khác |
| Gửi Stop khi producer khác vẫn làm việc | Consumer có thể thoát sớm | Xác định rõ điều kiện kết thúc của mọi producer |
| Dùng **Thread.sleep()** để chờ kết quả | Không chứng minh task đã xong | Dùng **join()**, Future hoặc đồng bộ hoàn tất |
| Dùng virtual threads để “sửa” race condition | Loại thread không thay đổi hợp đồng của dữ liệu dùng chung | Dùng đúng cấu trúc và giao thức đồng bộ |
| Dùng remapping function cho I/O chặn lâu | Có thể ảnh hưởng throughput và gây phụ thuộc vòng | Tách tính toán nhanh khỏi I/O, thiết kế cache async riêng |

## 23. Checklist chọn cấu trúc dữ liệu

Trước khi đưa collection vào mã đồng thời, hãy trả lời:

1. Có **bao nhiêu thread** cùng truy cập và chúng chủ yếu đọc hay ghi?
2. Có cần **Map theo key**, **Set**, **List có thứ tự**, **Deque** hay **hàng đợi giao việc**?
3. Những thao tác phải nguyên tử là **từng lời gọi**, **một key**, hay **nhiều bước trên nhiều key**?
4. Value có thể thay đổi trạng thái không? Nếu có, cơ chế bảo vệ bên trong value là gì?
5. Có cần **snapshot nhất quán**, hay iterator weakly consistent đã đủ?
6. Có yêu cầu **thứ tự theo key**, **thứ tự ưu tiên** hoặc **FIFO** không?
7. Producer có thể tạo dữ liệu nhanh hơn consumer trong thời gian dài không?
8. Nếu queue đầy, cần **block**, **timeout**, **reject** hay **retry**?
9. Nếu consumer chờ mãi hoặc thread bị interrupt, ứng dụng dừng bằng cách nào?
10. Nếu có nhiều consumer, cơ chế gửi tín hiệu kết thúc có đủ và đúng thời điểm không?
11. Công việc trong queue có thể thất bại hoặc cần retry không? Xử lý trùng và mất việc thế nào?
12. Có đang dùng **size()/isEmpty()/remainingCapacity()** làm điều kiện phối hợp không an toàn không?
13. Có cần dữ liệu sống sót sau khi tiến trình dừng không? Nếu có, collection trong bộ nhớ không thay thế cơ chế lưu bền vững.
14. Có kiểm thử race, timeout, interrupt, shutdown và overloading/backpressure theo workload thật không?

## Kết luận

**ConcurrentHashMap** phù hợp cho Map được nhiều thread truy cập và cập nhật, đặc biệt khi các thao tác **putIfAbsent**, **compute** hoặc **merge** thể hiện đúng tính nguyên tử cần thiết theo key. **LongAdder** là lựa chọn thường gặp cho bộ đếm có nhiều lượt cập nhật; **CopyOnWriteArrayList**, **ConcurrentLinkedQueue** và **ConcurrentSkipListMap** phục vụ những kiểu truy cập khác nhau.

**BlockingQueue** giải quyết một vấn đề khác: phối hợp producer–consumer bằng thao tác chờ, timeout và có thể cả giới hạn capacity để tạo backpressure. Queue tự bảo vệ thao tác truy cập theo hợp đồng của nó, nhưng không tự xử lý việc shutdown, retry, mất task hay đảm bảo giao dịch nghiệp vụ.

Khi viết Java 27, hãy lựa chọn theo **mức nguyên tử cần thiết, quy tắc visibility, tần suất đọc/ghi, sức chứa và giao thức vòng đời công việc**. Dùng một collection concurrent đúng chỗ thường đơn giản hơn khóa thủ công, nhưng độ đúng đắn cuối cùng luôn phụ thuộc vào hợp đồng **của toàn bộ thao tác nghiệp vụ**, không chỉ tên lớp dữ liệu.
