# Ảnh hưởng của truy cập và cập nhật đến access-ordered LinkedHashMap

Trong Java 21, LinkedHashMap có thể duy trì encounter order theo thứ tự các entry được truy cập gần đây nhất. Chế độ này được gọi là access-order và được bật bằng constructor có tham số accessOrder = true. Mỗi lần một entry hiện có được truy cập bằng các phương thức phù hợp, entry đó được chuyển về cuối thứ tự; entry ở đầu là entry ít được truy cập gần đây nhất.

Hành vi này hữu ích khi xây dựng cache kiểu LRU (Least Recently Used): khi cần loại bỏ một entry vì vượt giới hạn dung lượng, entry ở đầu map là ứng viên ít được dùng gần đây nhất. Để sử dụng đúng, cần phân biệt thao tác nào tạo access, thao tác nào chỉ đọc hoặc duyệt, và cách cập nhật mapping làm thay đổi encounter order.

## 1. Bật chế độ access-order

LinkedHashMap có constructor nhận ba tham số: sức chứa ban đầu, load factor và cờ accessOrder.

~~~java
import java.util.LinkedHashMap;

LinkedHashMap<String, Integer> cache =
        new LinkedHashMap<>(16, 0.75f, true);
~~~

Tham số cuối quyết định cách duy trì encounter order:

| accessOrder | Cách duy trì thứ tự |
|---|---|
| false | Insertion-order: thứ tự chèn entry vào map |
| true | Access-order: thứ tự truy cập, từ ít được truy cập gần đây nhất đến được truy cập gần đây nhất |

Constructor không truyền accessOrder sử dụng insertion-order. Vì vậy, new LinkedHashMap<>() không tự tạo LRU map. Muốn có access-order, phải dùng constructor có tham số boolean và truyền true.

Trong access-order mode, có thể hình dung thứ tự như sau:

~~~text
eldest / ít được truy cập gần đây                 youngest / mới truy cập gần đây
             |                                                     |
             v                                                     v
           A=1  ->  B=2  ->  C=3  ->  D=4
~~~

Khi entry B được truy cập, nó được chuyển về cuối:

~~~text
Trước:  A=1  ->  B=2  ->  C=3  ->  D=4
Sau:    A=1  ->  C=3  ->  D=4  ->  B=2
~~~

Map không sắp xếp theo key hoặc value. Encounter order thể hiện mức độ gần đây của các lần truy cập.

## 2. Những thao tác nào tạo access?

Java 21 quy định rõ các phương thức tạo access đến entry trong LinkedHashMap access-order. Nếu entry tương ứng tồn tại sau khi phương thức hoàn tất, access sẽ đưa entry đó về cuối encounter order.

| Phương thức | Khi nào tạo access? |
|---|---|
| get(key) | Khi tìm thấy mapping cho key |
| getOrDefault(key, defaultValue) | Khi tìm thấy mapping cho key; key không tồn tại thì không có entry để chuyển |
| put(key, value) | Entry tương ứng tồn tại sau lời gọi; cập nhật mapping hiện có sẽ đưa entry về cuối |
| putIfAbsent(key, value) | Khi mapping tương ứng tồn tại sau lời gọi |
| compute(key, function) | Khi mapping tương ứng tồn tại sau lời gọi |
| computeIfAbsent(key, function) | Khi mapping tương ứng tồn tại sau lời gọi |
| computeIfPresent(key, function) | Khi mapping tương ứng tồn tại sau lời gọi |
| merge(key, value, function) | Khi mapping tương ứng tồn tại sau lời gọi |
| replace(...) | Chỉ khi value thực sự được thay thế thành công |
| putAll(map) | Tạo một access cho mỗi mapping được đưa vào, theo thứ tự iterator của entrySet() của map nguồn |

Với các phương thức tính toán như compute hoặc merge, nếu thao tác làm mapping bị xóa hoặc không tạo ra mapping, sẽ không có entry còn tồn tại để được chuyển về cuối. Quy tắc cốt lõi là entry phải tồn tại sau khi lời gọi kết thúc.

Các thao tác truy cập không thành công, chẳng hạn get với key không có trong map, không thay đổi encounter order. Ví dụ:

~~~java
LinkedHashMap<String, Integer> cache =
        new LinkedHashMap<>(16, 0.75f, true);
cache.put("A", 1);
cache.put("B", 2);
cache.put("C", 3);

cache.get("A");
System.out.println(cache.keySet()); // [B, C, A]

cache.get("missing");
System.out.println(cache.keySet()); // [B, C, A]
~~~

get("A") tìm thấy entry và chuyển nó về cuối. get("missing") không tìm thấy mapping, nên thứ tự không thay đổi.

## 3. Phân biệt access với các thao tác chỉ quan sát

Không phải mọi thao tác đọc đều làm thay đổi access-order. Những phương thức không được quy định là tạo access sẽ không chuyển entry về cuối.

Ví dụ, các thao tác sau không tạo access:

- containsKey(key) và containsValue(value).
- Duyệt keySet(), values() hoặc entrySet().
- Lấy iterator hoặc spliterator từ các collection view.
- Duyệt map bằng forEach.
- Các thao tác trên collection view không truy cập entry theo nghĩa access-order của map.

Ví dụ:

~~~java
LinkedHashMap<String, Integer> cache =
        new LinkedHashMap<>(16, 0.75f, true);
cache.put("A", 1);
cache.put("B", 2);
cache.put("C", 3);

cache.containsKey("A");
cache.containsValue(2);
cache.keySet().contains("A");

System.out.println(cache.keySet()); // [A, B, C]
~~~

Các lệnh kiểm tra trên không làm A chuyển về cuối. Nếu chương trình cần cập nhật độ gần đây khi kiểm tra key, phải gọi một thao tác tạo access phù hợp, chẳng hạn get(key).

Không nên nhầm containsKey(key) với get(key): cả hai đều có thể xác định một key có tồn tại, nhưng chỉ get tạo access cho entry tìm thấy.

## 4. Cập nhật value và vị trí entry

Trong access-order mode, cập nhật một mapping có thể làm thay đổi vị trí entry ngay cả khi key không đổi.

~~~java
LinkedHashMap<String, Integer> cache =
        new LinkedHashMap<>(16, 0.75f, true);
cache.put("A", 1);
cache.put("B", 2);
cache.put("C", 3);

cache.put("A", 10);

System.out.println(cache); // {B=2, C=3, A=10}
~~~

put("A", 10) thay value của mapping A và tạo access đến entry đó. Kết quả là A chuyển về cuối. Map vẫn chỉ có một mapping cho key A.

Các phương thức replace có quy tắc cụ thể: chỉ một lần thay value thành công mới tạo access. Nếu key không tồn tại hoặc điều kiện so khớp old value không đúng, thứ tự không đổi.

~~~java
cache.replace("B", 20);       // thay value và đưa B về cuối
cache.replace("C", 999, 30);  // không thay nếu value hiện tại không phải 999
~~~

Lệnh đầu cập nhật mapping B nếu có và làm B thành entry được truy cập gần đây nhất. Lệnh thứ hai chỉ tạo access nếu mapping C có value cũ bằng 999 và được thay bằng 30; nếu điều kiện không đúng thì không có access.

### putIfAbsent và các phương thức compute

Các phương thức cập nhật có điều kiện cũng tham gia quy tắc access-order. Khi entry tương ứng tồn tại sau khi lời gọi hoàn tất, nó được xem là đã truy cập.

~~~java
LinkedHashMap<String, Integer> cache =
        new LinkedHashMap<>(16, 0.75f, true);
cache.put("A", 1);
cache.put("B", 2);
cache.put("C", 3);

cache.putIfAbsent("A", 100);
System.out.println(cache.keySet()); // [B, C, A]

cache.computeIfPresent("B", (key, value) -> value + 10);
System.out.println(cache.keySet()); // [C, A, B]
~~~

putIfAbsent không thay value của A vì key đã có mapping, nhưng entry đó vẫn được truy cập và chuyển về cuối. computeIfPresent cập nhật B và cũng chuyển B về cuối.

Nếu hàm tính toán trả về null theo quy tắc của Map và mapping bị loại bỏ hoặc không được tạo, không có entry tương ứng để chuyển về cuối. Cần xem kết quả cuối của thao tác, không chỉ nhìn tên phương thức.

## 5. putAll tạo access theo thứ tự map nguồn

putAll(source) tạo access cho từng mapping được đưa vào map đích. Thứ tự các access theo thứ tự mà iterator entrySet() của map nguồn cung cấp.

~~~java
LinkedHashMap<String, Integer> cache =
        new LinkedHashMap<>(16, 0.75f, true);
cache.put("A", 1);
cache.put("B", 2);
cache.put("C", 3);

LinkedHashMap<String, Integer> updates = new LinkedHashMap<>();
updates.put("A", 10);
updates.put("B", 20);

cache.putAll(updates);

System.out.println(cache); // {C=3, A=10, B=20}
~~~

Map nguồn là LinkedHashMap insertion-order nên putAll xử lý A rồi B. Mỗi mapping được truy cập khi đưa vào map đích, khiến thứ tự cuối cùng là C, A, B.

Nếu map nguồn không có encounter order được đảm bảo, không nên dựa vào một thứ tự cụ thể của các access được tạo bởi putAll.

## 6. Những thao tác không phải access nhưng vẫn có thể thay đổi vị trí

Java 21 bổ sung putFirst và putLast qua SequencedMap. LinkedHashMap triển khai các phương thức này để đặt mapping tại vị trí được yêu cầu, kể cả khi map đang ở access-order mode.

~~~java
import java.util.LinkedHashMap;
import java.util.SequencedMap;

SequencedMap<String, Integer> cache =
        new LinkedHashMap<>(16, 0.75f, true);
cache.put("A", 1);
cache.put("B", 2);
cache.put("C", 3);

cache.putFirst("C", 30);
System.out.println(cache.keySet()); // [C, A, B]

cache.putLast("A", 10);
System.out.println(cache.keySet()); // [C, B, A]
~~~

putFirst và putLast định vị mapping rõ ràng ở đầu hoặc cuối. Chúng không phải thao tác truy cập thông thường để chuyển entry về cuối theo access-order; vị trí được yêu cầu bởi chính phương thức quyết định vị trí sau lời gọi. Một lần get hoặc một access operation khác về sau vẫn có thể đưa entry đó về cuối.

Các phương thức đầu-cuối này hữu ích khi cần điều chỉnh thứ tự một cách chủ động. Chúng khác với put(key, value), vốn trong access-order mode tạo access đến mapping và đưa nó về cuối nếu mapping tồn tại sau lời gọi.

## 7. Xây dựng LRU cache đơn giản

Một LRU cache loại bỏ entry ít được truy cập gần đây nhất khi vượt quá dung lượng. LinkedHashMap access-order cung cấp thứ tự cần thiết: entry ở đầu là eldest và entry ở cuối là youngest.

Có thể override removeEldestEntry để loại bỏ entry đầu sau khi thêm mapping mới:

~~~java
import java.util.LinkedHashMap;
import java.util.Map;

class LruCache<K, V> extends LinkedHashMap<K, V> {
    private final int capacity;

    LruCache(int capacity) {
        super(16, 0.75f, true);
        if (capacity < 0) {
            throw new IllegalArgumentException("capacity must be non-negative");
        }
        this.capacity = capacity;
    }

    @Override
    protected boolean removeEldestEntry(Map.Entry<K, V> eldest) {
        return size() > capacity;
    }
}
~~~

Sử dụng cache:

~~~java
LruCache<String, Integer> cache = new LruCache<>(3);
cache.put("A", 1);
cache.put("B", 2);
cache.put("C", 3);

cache.get("A");
cache.put("D", 4);

System.out.println(cache.keySet()); // [C, A, D]
~~~

Diễn biến:

1. Sau ba lần put, thứ tự là A, B, C.
2. get("A") đưa A về cuối: B, C, A.
3. put("D", 4) thêm D ở cuối. Kích thước thành bốn, vượt giới hạn ba.
4. removeEldestEntry trả true, nên entry đầu B bị loại bỏ. Thứ tự còn lại là C, A, D.

removeEldestEntry được gọi sau khi put hoặc putAll thêm mapping mới. Việc đọc entry bằng get chỉ cập nhật thứ tự, không tự gọi chính sách loại bỏ. Đây là ví dụ cache đơn giản cho một luồng hoặc môi trường đã có cơ chế đồng bộ thích hợp; bản thân LinkedHashMap không thread-safe.

## 8. Ảnh hưởng đến iterator và fail-fast behavior

Trong access-order mode, thao tác truy cập làm thay đổi encounter order là structural modification. Vì thế, một thao tác get có thể làm iterator đang hoạt động trở nên không hợp lệ, dù số lượng mapping không đổi.

Ví dụ không nên dùng:

~~~java
for (String key : cache.keySet()) {
    Integer value = cache.get(key); // có thể thay đổi access order
    System.out.println(key + "=" + value);
}
~~~

Nếu get(key) chuyển entry khỏi vị trí hiện tại, cấu trúc thứ tự bị thay đổi trong khi iterator đang duyệt. Iterator fail-fast có thể ném ConcurrentModificationException. Đây là hành vi phát hiện lỗi best-effort, không phải cơ chế đồng bộ hoặc bảo đảm phát hiện mọi sửa đổi.

Nếu chỉ cần đọc key và value trong lúc duyệt, hãy dùng entry nhận được từ iterator thay vì gọi get trên cùng map:

~~~java
for (Map.Entry<String, Integer> entry : cache.entrySet()) {
    System.out.println(entry.getKey() + "=" + entry.getValue());
}
~~~

Thao tác duyệt entrySet() không tạo access cho backing map. Nếu cần truy cập một key để cập nhật độ gần đây, thực hiện get ngoài vòng duyệt hoặc thiết kế luồng xử lý để không sửa encounter order trong lúc iterator đang hoạt động.

## 9. Access-order và insertion-order khác nhau thế nào?

| Hành vi | Insertion-order (false) | Access-order (true) |
|---|---|---|
| Entry mới được thêm | Xuất hiện cuối | Xuất hiện cuối |
| get(key) thành công | Không đổi vị trí | Chuyển entry về cuối |
| put với key đã có | Cập nhật value, giữ vị trí chèn | Cập nhật value và tạo access, chuyển về cuối |
| containsKey(key) | Không đổi vị trí | Không đổi vị trí |
| Duyệt collection view | Không đổi vị trí | Không đổi vị trí |
| replace thành công | Giữ vị trí chèn | Tạo access và chuyển về cuối |
| putFirst / putLast | Đặt vị trí theo yêu cầu | Đặt vị trí theo yêu cầu |

Với insertion-order, việc cập nhật value của mapping hiện có không làm thay đổi thứ tự chèn. Với access-order, các access operation được quy định sẽ thay đổi vị trí của entry. Vì vậy, hai chế độ phục vụ các mục đích khác nhau: insertion-order phù hợp khi cần giữ trình tự thêm dữ liệu; access-order phù hợp khi cần theo dõi mức độ gần đây của lần sử dụng.

## 10. Giới hạn và lưu ý khi thiết kế cache

**Không thread-safe.** LinkedHashMap không hỗ trợ truy cập và sửa đổi đồng thời một cách an toàn. Khi nhiều luồng dùng chung cache, cần đồng bộ hóa tất cả thao tác có thể ảnh hưởng đến map, bao gồm cả get trong access-order mode vì thao tác này có thể thay đổi thứ tự.

**Đừng duyệt và truy cập lại cùng map.** Gọi get trong lúc duyệt có thể thay đổi encounter order và làm iterator ném ConcurrentModificationException. Dùng Map.Entry từ iterator khi chỉ cần đọc dữ liệu.

**Chính sách dung lượng cần rõ ràng.** removeEldestEntry trong ví dụ loại bỏ entry khi số mapping vượt capacity. Ứng dụng thực tế có thể cần thêm thời gian hết hạn, giới hạn bộ nhớ, tải lại dữ liệu hoặc thống kê hit/miss; access-order chỉ giải quyết thứ tự gần đây, không cung cấp toàn bộ chính sách cache.

**Không phải mọi thao tác đọc đều là access.** containsKey, containsValue và các collection view không cập nhật độ gần đây. Nếu logic cache cần tính một thao tác kiểm tra là lần sử dụng, hãy thực hiện một access operation thích hợp.

**Không nhầm putFirst/putLast với access.** Hai phương thức này định vị mapping tường minh. Sau đó, một access operation thông thường có thể tiếp tục thay đổi vị trí của entry.

**Cẩn trọng với null.** LinkedHashMap cho phép null key và null value. get(key) trả về null có thể có nghĩa là không có mapping hoặc mapping hiện tại có value null; dùng containsKey(key) khi cần phân biệt. Lệnh get với key có mapping value null vẫn là access vì entry tồn tại.

## 11. Quy trình kiểm tra hành vi access-order

Khi kiểm tra một LinkedHashMap dùng access-order, hãy thực hiện các bước sau:

1. Tạo map bằng constructor new LinkedHashMap<>(initialCapacity, loadFactor, true).
2. Thêm một số mapping và ghi nhận encounter order ban đầu.
3. Gọi get với key tồn tại, sau đó kiểm tra key đó chuyển về cuối.
4. Gọi get với key không tồn tại và xác nhận thứ tự không đổi.
5. Thử containsKey và duyệt collection view để xác nhận các thao tác này không tạo access.
6. Thử put, putIfAbsent, compute, merge và replace thành công để quan sát quy tắc chuyển entry.
7. Thử putFirst và putLast để phân biệt định vị tường minh với access.
8. Nếu dùng LRU cache, thêm entry vượt giới hạn và xác nhận entry ở đầu bị loại bỏ.
9. Tránh gọi access operation làm thay đổi thứ tự trong khi iterator đang hoạt động.

## Kết luận

LinkedHashMap access-order sắp encounter order từ entry ít được truy cập gần đây nhất đến entry được truy cập gần đây nhất. Các phương thức như get, put, compute, merge và replace thành công có thể đưa entry về cuối; containsKey và thao tác duyệt view thì không. Hiểu rõ quy tắc này giúp xây dựng LRU cache, tránh thay đổi thứ tự ngoài ý muốn và tránh lỗi iterator khi truy cập map trong lúc duyệt.

## Tài liệu tham khảo

- [Java SE 21 API — LinkedHashMap](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/LinkedHashMap.html)
- [Java SE 21 API — SequencedMap](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/SequencedMap.html)
- [Java SE 21 API — Map](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Map.html)
- [JEP 431 — Sequenced Collections](https://openjdk.org/jeps/431)
