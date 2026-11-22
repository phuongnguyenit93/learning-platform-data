# Lập bảng quyết định chọn Java Collection và tự đánh giá qua tình huống

> **Mục tiêu:** Chọn collection từ yêu cầu thực tế; giải thích lựa chọn theo tính duy nhất, thứ tự, thao tác thường gặp, chi phí, `null`, mutability và đa luồng; sau đó tự đánh giá bằng tình huống và thang điểm.

## 1. Đặt đúng câu hỏi trước khi chọn lớp

Trong Java Collections Framework, `List`, `Set` và `Queue` thuộc nhánh `Collection`; `Deque` mở rộng `Queue`. `Map` lưu các cặp khóa–giá trị và **không kế thừa `Collection`**.

Khi nhận một bài toán lưu trữ, hãy lần lượt hỏi:

1. **Hình dạng dữ liệu?** Dãy, tập không trùng, tra cứu theo khóa, hàng đợi, ngăn xếp, hay hàng chờ ưu tiên?
2. **Trùng lặp?** Có cần giữ nhiều lần xuất hiện cùng một phần tử? Khóa trong map có bắt buộc duy nhất?
3. **Thứ tự?** Cần theo vị trí, thứ tự chèn, sắp xếp theo comparator, FIFO/LIFO hay độ ưu tiên?
4. **Thao tác chủ đạo?** `get(i)`, `contains`, `get(key)`, thêm/xóa ở hai đầu, truy vấn khoảng, xử lý job tiếp theo?
5. **Khối lượng và cập nhật?** Dữ liệu lớn hay nhỏ, đọc nhiều hay ghi nhiều, có giới hạn dung lượng hoặc cần bản không chỉnh sửa?
6. **Đồng thời và ràng buộc?** Nhiều luồng cùng sửa? Cần thao tác nguyên tử, chặn producer/consumer, dùng `null` hay enum?

Quy trình: **chọn interface theo hợp đồng dữ liệu → xác định thứ tự/trùng → xác định thao tác nóng → xem concurrency và dung lượng → chọn implementation → kiểm chứng giả định**. Không phải ứng dụng nào cũng chỉ cần một cấu trúc; có thể dùng map để tra khóa và queue để điều phối công việc.

## 2. Bảng quyết định: chọn theo yêu cầu, không theo thói quen

| Nhu cầu | Lớp thường chọn | Vì sao | Cảnh báo |
|---|---|---|---|
| Dãy có thứ tự, giữ trùng, truy cập index | `ArrayList<E>` | `get(i)` nhanh, append cuối hiệu quả | Chèn/xóa đầu hoặc giữa dịch phần tử |
| Dãy không cần thay đổi cấu trúc sau khi tạo | `List.of`, `List.copyOf` | Không cho `add/remove/set` | Không cho null; không deep-copy các đối tượng con |
| Phần tử duy nhất, không quan tâm thứ tự | `HashSet<E>` | `add/contains/remove` trung bình nhanh | Không hứa thứ tự duyệt |
| Phần tử duy nhất, giữ thứ tự xuất hiện đầu tiên | `LinkedHashSet<E>` | Set + insertion order | Không tự sắp theo giá trị |
| Phần tử duy nhất, luôn sắp xếp hoặc truy vấn khoảng | `TreeSet<E>` | Có `first/last/subSet` và thứ tự comparator | Thao tác khoảng `O(log n)`; comparator quyết định phần tử “trùng” |
| Tra cứu theo khóa duy nhất, không cần thứ tự | `HashMap<K,V>` | `get/put` trung bình `O(1)` | Không dựa vào thứ tự iteration |
| Map theo thứ tự chèn, hoặc truy cập gần đây | `LinkedHashMap<K,V>` | Cho thứ tự duyệt ổn định; hỗ trợ nền tảng LRU | LRU cần bật access-order và cài eviction |
| Map khóa sắp xếp, cần `subMap` | `TreeMap<K,V>` | Navigable, duyệt theo key | Không sắp theo value |
| FIFO hoặc LIFO một luồng | `ArrayDeque<E>` | Nhanh ở hai đầu, triển khai `Deque` | Không cho null, không thread-safe |
| Công việc lấy ra theo priority | `PriorityQueue<E>` | `offer/poll` khoảng `O(log n)` | Iterator không bảo đảm sorted; bằng priority không tự FIFO |
| Hàng đợi nhiều luồng, giới hạn dung lượng, cần chặn | `ArrayBlockingQueue<E>` | `put/take` đợi khi đầy/rỗng | Phải thiết kế hủy/đóng tác vụ để tránh chờ mãi |
| Hàng đợi concurrent không chặn, không giới hạn cố định | `ConcurrentLinkedQueue<E>` | FIFO không chặn | Không tự cung cấp backpressure |
| Map nhiều luồng ghi | `ConcurrentHashMap<K,V>` | `merge/compute/putIfAbsent` hỗ trợ cập nhật nguyên tử theo khóa | Không cho null; “đọc rồi ghi” riêng lẻ có thể race |
| Danh sách nhiều luồng đọc nhiều, hiếm sửa | `CopyOnWriteArrayList<E>` | Iterator theo snapshot | Mỗi lần sửa sao chép mảng |
| Tập giá trị của một enum | `EnumSet<E>` | Gọn, nhanh, duyệt theo thứ tự khai báo enum | Chỉ nhận enum, không nhận null |
| Map với khóa enum | `EnumMap<K,V>` | Gọn, nhanh, key theo thứ tự khai báo | Khóa phải đúng enum, không null |

**Mặc định có điều kiện:** `ArrayList` cho dãy, `HashSet` cho tập, `HashMap` cho ánh xạ, `ArrayDeque` cho FIFO/LIFO. Hãy chuyển sang lớp khác khi *yêu cầu cụ thể* khiến nó cần thiết.

`LinkedList` không phải cách tăng tốc mặc định cho `List`. `get(i)` mất `O(n)` để đi qua các nút, bộ nhớ mỗi nút lớn hơn; chèn/xóa tại nút đã tìm được có thể `O(1)` nhưng tìm nút thường vẫn `O(n)`. Với stack/queue thông thường, `ArrayDeque` thường phù hợp hơn lớp `Stack` cũ.

## 3. Bảng chi phí và các điều kiện đi kèm

`n` là số phần tử; độ phức tạp đối với hash giả định hàm băm hợp lý và phân bố bình thường. Một thao tác `O(1)` trung bình vẫn có chi phí resize, va chạm, cấp phát và ảnh hưởng bộ nhớ.

| Cấu trúc | Tìm/truy cập | Thêm | Xóa | Ngữ nghĩa thứ tự |
|---|---|---|---|---|
| `ArrayList` | `get(i): O(1)`, `contains: O(n)` | Cuối `O(1)` amortized; giữa `O(n)` | Đầu/giữa `O(n)` | Theo vị trí |
| `HashSet` / `HashMap` | `contains/get: O(1)` trung bình | `O(1)` trung bình | `O(1)` trung bình | Không cam kết |
| `LinkedHashSet` / `LinkedHashMap` | `O(1)` trung bình | `O(1)` trung bình | `O(1)` trung bình | Theo chèn; map có thể theo truy cập |
| `TreeSet` / `TreeMap` | `O(log n)` | `O(log n)` | `O(log n)` | Theo comparator/key |
| `ArrayDeque` | Tìm phần tử `O(n)` | Hai đầu `O(1)` amortized | Hai đầu `O(1)` amortized | Theo deque |
| `PriorityQueue` | `peek: O(1)`, `contains: O(n)` | `offer: O(log n)` | `poll: O(log n)` | Khi lấy đầu theo comparator |

Các lỗi hợp đồng cần kiểm tra:

- `HashSet`/`HashMap` phụ thuộc `equals` và `hashCode`: nếu `a.equals(b)` thì hai đối tượng phải có hash code bằng nhau. Không đổi trường tham gia hash của phần tử/khóa đã lưu.
- `TreeSet`/`TreeMap` coi hai phần tử/khóa tương đương nếu comparator trả về `0`. Comparator chỉ so điểm có thể làm mất học viên có cùng điểm. Để đúng hợp đồng Set/Map về equality, nên nhất quán comparator với `equals`.
- `ArrayList`, `HashMap`, `HashSet` cho phép null (HashMap một khóa null và nhiều value null). `ArrayDeque`, `PriorityQueue`, `ConcurrentHashMap` và `List.of/Set.of/Map.of` không cho null. `TreeSet/TreeMap` thứ tự tự nhiên không dùng null; comparator tùy chỉnh có thể xác định thứ tự cho null.
- `List.copyOf` tạo danh sách không chỉnh sửa cấu trúc, không sao chép sâu các phần tử mutable. `Collections.unmodifiableList(original)` tạo view: nếu list gốc đổi, view có thể phản ánh thay đổi.
- `HashSet` đôi khi duyệt có vẻ ổn định nhưng API không cam kết. `LinkedHashSet` giữ insertion order; `TreeSet` sắp theo comparator.
- `PriorityQueue` chỉ đảm bảo **lấy ra bằng `poll`** theo ưu tiên; lặp với iterator không ra thứ tự ưu tiên. Cùng priority cần comparator có tiêu chí phụ như số thứ tự.
- Iterator fail-fast không phải công cụ đồng bộ hay bảo đảm phát hiện mọi race. Collection concurrent có thể dùng weakly consistent iterator; `CopyOnWriteArrayList` dùng snapshot iterator. Kiểm tra semantics trước khi chọn.

## 4. Tự lập bảng quyết định cho một chức năng

Mỗi hàng gắn với **một yêu cầu đo được**, thay vì chỉ ghi tên lớp:

| Câu hỏi | Dữ kiện ví dụ | Ứng viên | Quyết định |
|---|---|---|---|
| Giữ cả lần xuất hiện trùng và xem mục thứ i? | Lịch sử thao tác | `List` / `Set` | `ArrayList` |
| Loại trùng nhưng giữ lần đầu xuất hiện? | Thẻ bài viết | `HashSet` / `LinkedHashSet` | `LinkedHashSet` |
| Tra cứu theo mã hàng nghìn lần? | Mã SKU → sản phẩm | `ArrayList` / `HashMap` | `HashMap` |
| Truy vấn thời gian từ A tới B? | Các mốc được sắp | `HashSet` / `TreeSet` | `TreeSet` hoặc `TreeMap` |
| Lấy job đến trước trước? | FIFO đơn luồng | `ArrayDeque` / `PriorityQueue` | `ArrayDeque` |
| Mỗi lúc chỉ được 500 việc chờ, nhiều luồng? | Producer/consumer | `ConcurrentLinkedQueue` / `ArrayBlockingQueue` | `ArrayBlockingQueue<>(500)` |
| Lấy việc quan trọng nhất trước? | Ticket có priority | `ArrayDeque` / `PriorityQueue` | `PriorityQueue` + tie-break |
| Nhiều luồng tăng bộ đếm theo khóa? | Đếm page view | `HashMap` / `ConcurrentHashMap` | `ConcurrentHashMap` + `merge` |

Quyết định nên trình bày dạng: “Tôi dùng **X** vì cần **tính chất Y** và chủ yếu gọi **phép Z**; tôi chấp nhận **giới hạn W**”. Với dữ liệu lớn hoặc độ trễ quan trọng, thêm benchmark cho đường chạy thật. Đừng tối ưu chỉ theo Big-O.

## 5. Java 17: một bài toán, nhiều collection đúng mục đích

Dưới đây là chương trình đầy đủ. Tên file là `CollectionChoiceDemo.java`.

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
import java.util.Queue;
import java.util.Set;
import java.util.TreeSet;

public class CollectionChoiceDemo {
    record Job(String name, int priority, long sequence) {}

    public static void main(String[] args) {
        List<String> history = new ArrayList<>();
        history.add("đọc");
        history.add("viết");
        history.add("đọc");

        Set<String> unique = new LinkedHashSet<>(history);
        Map<String, Integer> counts = new LinkedHashMap<>();
        for (String action : history) {
            counts.merge(action, 1, Integer::sum);
        }

        Deque<String> fifo = new ArrayDeque<>();
        fifo.addLast("A");
        fifo.addLast("B");

        Set<Integer> scores = new TreeSet<>(List.of(7, 9, 8, 7));

        Queue<Job> jobs = new PriorityQueue<>(
            Comparator.comparingInt(Job::priority)
                .reversed()
                .thenComparingLong(Job::sequence)
        );
        jobs.offer(new Job("normal", 2, 0));
        jobs.offer(new Job("urgent", 5, 1));
        jobs.offer(new Job("urgent2", 5, 2));

        System.out.println("Lịch sử: " + history);
        System.out.println("Duy nhất: " + unique);
        System.out.println("Số lần: " + counts);
        System.out.println("FIFO: " + fifo.removeFirst() + " -> " + fifo.removeFirst());
        System.out.println("Điểm tăng dần: " + scores);
        System.out.println("Ưu tiên: "
            + jobs.remove().name() + ", "
            + jobs.remove().name() + ", "
            + jobs.remove().name());
    }
}
~~~

Biên dịch và chạy với JDK 17+:

~~~bash
javac -encoding UTF-8 CollectionChoiceDemo.java
java CollectionChoiceDemo
~~~

Đầu ra chính xác:

~~~text
Lịch sử: [đọc, viết, đọc]
Duy nhất: [đọc, viết]
Số lần: {đọc=2, viết=1}
FIFO: A -> B
Điểm tăng dần: [7, 8, 9]
Ưu tiên: urgent, urgent2, normal
~~~

**Giải thích:** `ArrayList` giữ hai lần “đọc” trong lịch sử; `LinkedHashSet` khử trùng và giữ thứ tự gặp; `LinkedHashMap` cộng số lần và giữ thứ tự thêm khóa. `ArrayDeque` xử lý FIFO ở hai đầu; `TreeSet` khử trùng đồng thời sắp điểm; `PriorityQueue` lấy độ ưu tiên lớn trước. Hai job priority 5 được xếp bằng `sequence`; nếu comparator chỉ so priority thì không thể giả định job đến trước luôn lấy trước.

## 6. 12 tình huống tự đánh giá

**Cách làm:** Trước khi đọc đáp án mục 7, viết cho mỗi câu (a) interface/lớp, (b) tính chất quyết định, (c) một rủi ro hoặc giả định cần xác minh. Nhiều lời giải có thể đúng nếu giữ đủ hợp đồng.

1. **Nhật ký thao tác:** Giữ thứ tự thực hiện và nhiều lần lặp; giao diện cần lấy thao tác thứ i.
2. **Hashtag:** Loại trùng, hiển thị theo thứ tự xuất hiện lần đầu, không sắp alphabet.
3. **Kho sản phẩm:** Từ SKU tra sản phẩm nhanh; không yêu cầu thứ tự hiển thị; mỗi SKU một sản phẩm.
4. **Mốc lịch:** Sắp tăng theo thời gian và tìm các mốc trong khoảng từ A đến B.
5. **Undo:** Lấy thao tác mới nhất ra trước; chỉ một luồng, không cần tìm theo chỉ số.
6. **Xử lý ảnh:** Producer và consumer chạy khác luồng; tối đa 1000 tác vụ chờ; producer cần đợi khi đầy.
7. **Ticket hỗ trợ:** Priority cao xử lý trước, cùng priority theo thứ tự đến; không cần duyệt toàn hàng chờ theo thứ tự.
8. **Đếm lượt xem:** Nhiều luồng tăng bộ đếm cho cùng khóa; không được làm mất increment.
9. **Danh sách listener:** Nhiều luồng duyệt liên tục, rất ít ghi; mỗi lần duyệt muốn snapshot ổn định.
10. **Quyền người dùng:** Chỉ có các hằng enum `ADMIN/EDITOR/VIEWER`; một người có tập vai trò không trùng.
11. **Bảng top điểm:** Nhiều học viên có cùng điểm; hiển thị điểm giảm dần và giữ đủ học viên.
12. **Cache LRU:** Tra theo key; chỉ một luồng; khi vượt 100 mục thì bỏ mục lâu nhất **không được truy cập** (không phải mục được thêm cũ nhất).

Nếu tình huống chưa quy định null, mutation, kích thước hoặc concurrency, hãy ghi giả định. Không chấm một lớp là “sai” chỉ vì khác đáp án mẫu khi nó đáp ứng mọi ràng buộc.

## 7. Đáp án tham khảo và lý do

| Câu | Collection phù hợp | Giải thích / điều cần tránh |
|---|---|---|
| 1 | `List<Action>` bằng `ArrayList<>` | Giữ thứ tự và trùng; `get(i)` nhanh. `Set` sẽ xóa lịch sử lặp. |
| 2 | `LinkedHashSet<String>` | Không trùng và vẫn giữ thứ tự xuất hiện đầu tiên. `HashSet` không cam kết thứ tự. |
| 3 | `HashMap<String, Product>` | Tra theo khóa trung bình `O(1)`; key phải giữ `equals/hashCode` ổn định. |
| 4 | `TreeSet<Instant>` hoặc `TreeMap<Instant, List<Event>>` | Sorted và có API range. Nếu trùng mốc thời gian, phải giữ nhiều event thay vì ghi đè. |
| 5 | `Deque<Action>` bằng `ArrayDeque<>` | `push/pop` là LIFO; tránh dùng `Stack` cũ làm mặc định. |
| 6 | `BlockingQueue<Task>` bằng `ArrayBlockingQueue<>(1000)` | `put` đợi nếu đầy, `take` đợi nếu rỗng. Có kế hoạch kết thúc, hủy và xử lý interrupt. |
| 7 | `PriorityQueue<Ticket>` | Comparator priority giảm dần rồi sequence tăng dần. Không dùng iterator để hiện kết quả sorted. |
| 8 | `ConcurrentHashMap<Key, Long>` với `merge(key, 1L, Long::sum)` | Increment an toàn theo khóa; `put(k, get(k) + 1)` làm hai bước dễ race. Với contention lớn có thể cân nhắc `LongAdder`. |
| 9 | `CopyOnWriteArrayList<Listener>` | Snapshot iterator thích hợp với nhiều lần duyệt và ít cập nhật; ghi nhiều sẽ tốn sao chép. |
| 10 | `EnumSet<Role>` | Biểu diễn nhỏ gọn, nhanh và chỉ chứa hằng enum; không nhận null. |
| 11 | `List<Student>` được `sort` theo điểm giảm dần; hoặc `TreeMap<Integer, List<Student>>` dùng reverse order | Giữ mọi học viên cùng điểm. `TreeMap<Integer, Student>` sẽ ghi đè key điểm trùng. |
| 12 | `LinkedHashMap<K,V>` access-order, override `removeEldestEntry` | Truy cập gần nhất phải đổi vị trí; dùng map đơn luồng hoặc có đồng bộ hóa thích hợp. |

Ví dụ Java 17 độc lập minh họa câu 12 (giới hạn 2 cho dễ xem; đổi thành 100 khi áp dụng đề):

~~~java
import java.util.LinkedHashMap;
import java.util.Map;

public class LruExample {
    public static void main(String[] args) {
        Map<String, Integer> cache = new LinkedHashMap<>(16, 0.75f, true) {
            @Override
            protected boolean removeEldestEntry(Map.Entry<String, Integer> eldest) {
                return size() > 2;
            }
        };
        cache.put("A", 1);
        cache.put("B", 2);
        cache.get("A");
        cache.put("C", 3);
        System.out.println(cache);
    }
}
~~~

Chạy `javac -encoding UTF-8 LruExample.java` rồi `java LruExample` cho `{A=1, C=3}`. “B” bị loại vì “A” được truy cập sau. `LinkedHashMap` access-order có thể cập nhật thứ tự ngay trong `get`, nên không tùy tiện chia sẻ nó giữa nhiều luồng mà không có cơ chế đồng bộ.

## 8. Thang điểm và phiếu tự chấm

Mỗi tình huống **tối đa 2 điểm**, tổng **24**:

- **1 điểm chọn đúng:** lớp/interface thỏa toàn bộ yêu cầu nêu rõ. Chấp nhận giải pháp khác đáp án nếu có lập luận đúng; chọn loại mất trùng, mất thứ tự, mất cập nhật hoặc sai concurrency là 0 điểm phần này.
- **1 điểm giải thích:** nói rõ một đặc tính cốt lõi *và* một rủi ro/điều kiện (ví dụ hash contract, comparator, capacity, atomicity, snapshot, thứ tự). Chỉ trả lời tên lớp không đủ điểm giải thích.

| Tổng /24 | Mức nắm vững | Bài tập tiếp theo |
|---|---|---|
| 21–24 | Quyết định và lý do vững | Thử dữ liệu lớn và nhiều luồng, so đo thực tế |
| 17–20 | Phần lớn đúng | Giải thích lại các rủi ro ở câu sai |
| 12–16 | Biết họ collection nhưng còn nhầm hợp đồng | Ôn thứ tự vs sắp xếp, Set/Map/Queue |
| 0–11 | Chưa chọn theo yêu cầu | Làm lại sáu câu hỏi mục 1 trước mỗi tình huống |

**Phiếu tự đánh giá để tự điền:**

| Câu | Lớp đã chọn | Tính chất quyết định | Rủi ro/giả định | Điểm /2 |
|---|---|---|---|---|
| 1, 2, 3, 4 | Ghi riêng từng câu | Trùng/thứ tự/key/range | Equality, comparator | ... |
| 5, 6, 7, 8 | Ghi riêng từng câu | LIFO/bounded blocking/priority/concurrent | Null, đóng queue, tie-break, atomicity | ... |
| 9, 10, 11, 12 | Ghi riêng từng câu | Snapshot/enum/giữ trùng điểm/LRU | Chi phí ghi, key trùng, đồng bộ | ... |

Khi sai một câu, viết lại theo mẫu: “Tôi cần ___ vì yêu cầu ___; tôi không chọn ___ vì sẽ vi phạm ___”. Sau đó **đổi một điều kiện** trong đề: nếu danh sách cần sắp xếp thay vì insertion order thì chọn gì? Nếu thêm nhiều luồng thì cấu trúc/đồng bộ thay thế ra sao? Nếu consumer chậm thì có giới hạn queue không? Đây là cách kiểm tra mình hiểu cơ chế, thay vì học thuộc đáp án.

## 9. Các lỗi phổ biến khi áp dụng

1. **Nhầm insertion order và sorted order:** `LinkedHashSet` giữ thứ tự chèn, `TreeSet` sắp theo comparator; `PriorityQueue` chỉ lấy đầu theo ưu tiên.
2. **Dùng `HashSet`/`HashMap` rồi dựa vào thứ tự duyệt “trông có vẻ ổn định”:** API không cam kết.
3. **Đưa khóa mutable vào hash collection và sửa trường tham gia hash:** lần `get/contains` sau có thể thất bại.
4. **Dùng comparator chỉ so một thuộc tính khi các đối tượng vẫn cần cùng tồn tại:** `TreeSet` có thể bỏ phần tử; `TreeMap` có thể ghi đè value.
5. **Nhìn `map.get(key) == null` rồi kết luận khóa vắng:** Với `HashMap`, key có thể tồn tại nhưng value null; cần `containsKey` nếu phân biệt hai trường hợp.
6. **Nghĩ `Collections.synchronizedList` biến cả chuỗi thao tác thành nguyên tử:** `contains` rồi `add`, hoặc iteration, có thể cần đồng bộ xung quanh toàn bộ đoạn.
7. **Dùng `HashMap` cho tăng đếm cạnh tranh vì test đơn luồng vẫn đúng:** thao tác đọc–sửa–ghi không nguyên tử; dùng API cập nhật atomic thích hợp.
8. **Dùng `CopyOnWriteArrayList` cho workload ghi liên tục:** mỗi lần ghi sao chép mảng, thường tốn kém.
9. **Dùng `PriorityQueue` như một danh sách được sắp có thể duyệt trực tiếp:** iterator không hứa thứ tự; hãy poll một bản sao hoặc sort một list.
10. **Nhầm unmodifiable với immutable sâu:** không thêm/xóa được từ `List.copyOf`, nhưng đối tượng mutable bên trong vẫn có thể thay đổi.

## 10. Checklist cuối cho mỗi quyết định

- [ ] Đã xác định giữ trùng, key lookup, index, thứ tự chèn, sắp xếp, FIFO/LIFO hay priority?
- [ ] Đã nêu phép truy cập thường gặp và Big-O của **phép đó**, không chỉ của lớp?
- [ ] Đã kiểm tra `equals/hashCode`, `Comparator`, null, khóa mutable và các giá trị trùng?
- [ ] Đã phân biệt thread-safe, thao tác nguyên tử và queue có backpressure?
- [ ] Đã kiểm tra chi phí ghi, bộ nhớ và yêu cầu giữ snapshot?
- [ ] Đã khai báo biến bằng interface phù hợp (`List`/`Set`/`Map`/`Queue`/`Deque`) khi có thể và kiểm tra ví dụ nhỏ?

Một quyết định tốt luôn gắn **yêu cầu → cấu trúc → lý do → giới hạn**. Bảng quyết định và điểm tự chấm giúp bạn giải thích lựa chọn, kể cả khi cần đổi implementation vì yêu cầu mới.