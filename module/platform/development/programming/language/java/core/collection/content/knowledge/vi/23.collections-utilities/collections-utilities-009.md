# asLifoQueue, newSetFromMap và điều kiện của cấu trúc nền

Một cấu trúc dữ liệu đôi khi đã có đúng cách lưu trữ cần dùng, nhưng giao diện phía gọi lại khác. Một thuật toán nhận `Queue` có thể cần lấy phần tử mới nhất trước; một bài toán nhận `Set` có thể cần so thành viên theo định danh đối tượng hoặc dùng khóa yếu.

`Collections.asLifoQueue` và `Collections.newSetFromMap` tạo những giao diện thích nghi dựa trên cấu trúc nền. Chúng không đọc toàn bộ dữ liệu rồi tạo một bản sao độc lập. Hành vi của kết quả phụ thuộc cách chuyển thao tác và hợp đồng của deque/map được truyền vào.

Bài này dùng Java 17. Trước khi chạy mã, cần biết `Queue`, `Deque`, `Map`, `Set` và tham chiếu. Hai trọng tâm là vị trí thêm/lấy của LIFO và điều kiện sở hữu map khi tạo set.

## 1. Hai bộ thích nghi giải quyết hai bài toán khác nhau

| Phương thức | Đầu vào | Kết quả | Mục tiêu |
| --- | --- | --- | --- |
| `Collections.asLifoQueue(deque)` | `Deque<T>` | `Queue<T>` | Dùng các thao tác queue nhưng lấy phần tử theo LIFO |
| `Collections.newSetFromMap(map)` | `Map<E, Boolean>` | `Set<E>` | Dùng khóa map làm nơi lưu thành viên của set |

LIFO là “vào sau, ra trước” (last in, first out). Nếu thêm A, rồi B, rồi C qua giao diện LIFO, phần tử được lấy trước là C.

Set từ map dùng khóa để đại diện thành viên. Kiểu giá trị `Boolean` là phần phục vụ biểu diễn của bộ thích nghi; người dùng làm việc với `Set<E>` thay vì tự quản lý các cặp khóa–giá trị.

Điểm chung là có **cấu trúc nền đang được dùng thật**. Không có lời hứa tự làm bất biến phần tử, thay chính sách `null` hoặc thêm khả năng đồng thời cho một cấu trúc vốn không có.

Điểm khác quan trọng: deque của `asLifoQueue` **không bắt buộc rỗng**. Map của `newSetFromMap` **bắt buộc rỗng lúc tạo**, và sau đó không nên được truy cập trực tiếp nữa.

## 2. Vì sao một `Queue` có thể có thứ tự LIFO?

`Queue` mô tả các thao tác thêm, lấy và xem phần tử đầu sẽ được xử lý. Nó không buộc mọi cách thực hiện đều là FIFO. Hàng đợi ưu tiên và hàng đợi LIFO là các ví dụ có thứ tự khác. [Hợp đồng Queue, Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Queue.html).

Nếu chỉ truyền một `ArrayDeque` trực tiếp dưới kiểu `Queue`, các thao tác queue thông thường thêm ở cuối và lấy ở đầu, tạo FIFO. Ép kiểu giao diện không thay vị trí thêm.

`asLifoQueue` đổi cách ánh xạ thao tác: thêm qua queue vào **đầu deque**, và lấy cũng ở **đầu deque**. Đó là lý do phần tử vừa thêm được lấy trước.

~~~text
offer(A): đầu [A] cuối
offer(B): đầu [B, A] cuối
offer(C): đầu [C, B, A] cuối
poll():   trả C, còn [B, A]
~~~

Không có bước đảo toàn deque mỗi lần thêm. Quan hệ LIFO đến từ việc dùng cùng một đầu cho thêm và lấy.

### Chuyển đúng từng nhóm thao tác

| Thao tác trên queue thích nghi | Thao tác theo đầu deque | Ý nghĩa khi không có phần tử/chỗ trống |
| --- | --- | --- |
| `add(e)` | `addFirst(e)`, tương ứng push | Thất bại thêm do đầy: ngoại lệ |
| `offer(e)` | `offerFirst(e)` | Có thể trả `false` nếu đầy |
| `remove()` | `removeFirst()`, tương ứng pop | Rỗng: `NoSuchElementException` |
| `poll()` | `pollFirst()` | Rỗng: `null` |
| `element()` | `getFirst()` | Rỗng: `NoSuchElementException` |
| `peek()` | `peekFirst()` | Rỗng: `null` |

Các phương thức queue có hai nhóm xử lý thất bại. Chọn nhóm theo hợp đồng mong muốn; đừng gọi `remove()` khi thật sự muốn thăm dò không có dữ liệu bằng `poll()`.

Bảng đang nói `remove()` **không đối số**. `remove(value)` là thao tác tìm và xóa một phần tử phù hợp, không đồng nghĩa pop phần tử đầu. [Các thao tác hai đầu của Deque, Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Deque.html).

## 3. `asLifoQueue` là view sống trên deque

### Không tạo một ngăn xếp độc lập

Mã minh họa trong một phương thức:

~~~java
Deque<String> storage = new ArrayDeque<>();
Queue<String> pending = Collections.asLifoQueue(storage);

pending.add("A");
pending.add("B");
~~~

Cả hai giao diện đều dùng cùng dữ liệu. Duyệt deque từ đầu tới cuối sẽ thấy B, A. Lấy qua queue cũng lấy từ cấu trúc ấy.

Deque có thể đã có phần tử trước khi tạo view. Factory không tự đảo những phần tử hiện có để đoán lịch sử thêm của chúng. Nó cung cấp quy tắc cho những thao tác qua view kể từ lúc dùng.

Ví dụ deque đang là `[old-first, old-last]`, thêm `"new"` qua queue cho `[new, old-first, old-last]`. Phần tử new được ưu tiên lấy vì được đặt ở đầu, còn quan hệ của hai phần tử cũ không bị đảo.

### Giữ cả hai tham chiếu thì phải kiểm soát hai đường truy cập

Sửa trực tiếp deque sẽ được nhìn thấy qua queue. Đó là bằng chứng về cùng nơi lưu trữ, nhưng trong mã ứng dụng phải tránh vô tình trộn các quy tắc thêm ở đầu/cuối.

Nếu một thành phần thêm qua `deque.addLast` còn thành phần khác thêm qua queue LIFO, câu chuyện “vào sau ra trước” chỉ có nghĩa theo các thao tác đã được quy định. Không thể bỏ qua đường thêm ở cuối rồi hứa một thứ tự toàn cục khác.

Một cách đóng gói đơn giản khi chỉ muốn công bố LIFO là không để lộ deque:

~~~java
Queue<String> pending =
        Collections.asLifoQueue(new ArrayDeque<String>());
~~~

Người gọi chỉ có giao diện queue đã thích nghi. Nếu toàn bộ mã đã dùng `Deque` trực tiếp và muốn push/pop, dùng chính `Deque` thường đủ; không cần thêm một bộ thích nghi chỉ để viết tên hàm khác.

### Duyệt không có nghĩa là lấy phần tử ra

Iterator của view dùng thứ tự duyệt deque từ đầu tới cuối. Với dữ liệu đã thêm A, B, C qua LIFO, một bản `new ArrayList<>(queue)` biểu diễn C, B, A mà không tự pop các phần tử.

Ngược lại, lặp `poll` là thao tác lấy ra thật. Phải phân biệt việc đọc để hiển thị với việc tiêu thụ công việc.

## 4. `addAll` và giới hạn của cấu trúc nền

### Thêm cả nhóm đảo thứ tự nhóm ở đầu

`asLifoQueue` thực hiện `addAll` bằng một chuỗi lời gọi `addFirst` trên deque, theo các phần tử được đọc từ đầu vào. [API asLifoQueue, Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#asLifoQueue(java.util.Deque)).

Với queue đang rỗng:

~~~java
pending.addAll(List.of("A", "B", "C"));
~~~

Sau đó thứ tự đầu tới cuối là `[C, B, A]`. Nếu queue đã có dữ liệu, nhóm ấy nằm phía trước dữ liệu cũ theo cùng quy tắc.

Đừng đánh đồng thao tác này với `deque.addAll` thông thường thêm ở đuôi. Một lần gọi có cùng tên nhưng đối tượng nhận khác có thể dùng chính sách đặt vị trí khác.

### Bounded deque giữ giới hạn của nó

Dùng deque giới hạn hai phần tử:

~~~java
Queue<String> pending =
        Collections.asLifoQueue(new LinkedBlockingDeque<String>(2));
~~~

Thêm A rồi B bằng `offer` thành công. `offer("C")` trả `false` khi đầy; `add("C")` ném `IllegalStateException` trong tình huống ấy.

Bộ thích nghi không cấp phát vùng bổ sung để né giới hạn và cũng không tự đợi cho có chỗ. Kiểu kết quả `Queue` không cung cấp các thao tác chặn như `put` hoặc `take` dù cấu trúc nền có một giao diện chặn riêng.

`LinkedBlockingDeque` có thể có giới hạn dung lượng, còn `ArrayDeque` không có giới hạn cố định kiểu đó và tự tăng khi cần. Chính sách này đến từ loại deque được chọn. [LinkedBlockingDeque](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/LinkedBlockingDeque.html), [ArrayDeque](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayDeque.html).

### Bulk operation không tự là một giao dịch

Nếu queue giới hạn hai phần tử đang rỗng rồi `addAll(A, B, C)`, hai lần thêm đầu có thể hoàn thành trước khi lần thứ ba thất bại. Ví dụ chạy bên dưới xác nhận trạng thái còn B, A sau ngoại lệ.

Không suy từ “một lời gọi Java” thành “hoặc thêm hết, hoặc không thay gì”. Nếu nghiệp vụ cần cả nhóm được chấp nhận như một đơn vị, phải thiết kế cơ chế khác phù hợp.

### Chính sách `null` không bị xóa bỏ

`ArrayDeque` không cho phần tử `null` nên queue LIFO dựa trên nó cũng từ chối `null`. Một deque khác có thể có chính sách khác, nhưng `null` làm kết quả thăm dò rỗng của `poll`/`peek` dễ nhập nhằng.

Nên dùng phần tử có ý nghĩa rõ với giao thức queue đang chọn. Không coi view là cách hợp thức hóa một phần tử mà cấu trúc nền không nhận.

## 5. `newSetFromMap`: map trống được giao cho set quản lý

Chữ ký:

~~~java
public static <E> Set<E> newSetFromMap(Map<E, Boolean> map)
~~~

Đây là khai báo API để đọc kiểu, không phải phần cài đặt cần chép vào chương trình.

Các khóa map đại diện thành viên set. Thao tác `set.add(e)` được thực hiện thông qua thao tác ghi trên map; các thao tác thành viên/xóa/duyệt đi theo map hoặc góc nhìn khóa của nó.

### Map phải thực sự không có ánh xạ

Một map có khóa `"already"` với giá trị `Boolean.FALSE` vẫn là **map không rỗng**. False không có nghĩa “khóa không tồn tại”. Truyền map ấy vào factory ném `IllegalArgumentException`.

Factory không nhận một map đang có dữ liệu để “chuyển hết khóa sang set”. Nếu chỉ cần một bản tập khóa của map hiện hữu, đó là nhu cầu khác, thường liên quan tới `keySet` hoặc sao chép các khóa theo hợp đồng cần thiết.

### Sau khi tạo, không truy cập trực tiếp map nền

Tài liệu yêu cầu map rỗng lúc gọi và khuyến cáo không truy cập map trực tiếp sau khi factory trả về. Cách dùng đúng và dễ duy trì là tạo map ngay trong lời gọi và không giữ tham chiếu ngoài:

~~~java
Set<Object> visited = Collections.newSetFromMap(
        new IdentityHashMap<Object, Boolean>());
~~~

Mọi thao tác thành viên thực hiện qua `visited`. Không giữ một alias của map, một `keySet` cũ hoặc một view có thể thay dữ liệu ở đường khác.

Điều này khác ví dụ quan sát deque qua hai giao diện ở phần LIFO. Với set từ map, **không dùng đọc/ghi trực tiếp map nền sau tạo để làm thí nghiệm**; chương trình dưới đây chỉ thao tác trên set khi đã tạo thành công.

Quy tắc sở hữu ngăn việc bên ngoài tự đặt một giá trị `Boolean` khác hoặc sửa ánh xạ, làm hỏng những giả định mà thao tác set dựa vào. [API newSetFromMap, Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#newSetFromMap(java.util.Map)).

### Rỗng là điều kiện tạo, không bảo đảm mọi thao tác đều hỗ trợ

Một map rỗng nhưng không sửa được có thể đáp ứng việc kiểm tra rỗng. Set thích nghi từ nó vẫn không thể `add` nếu map không hỗ trợ ghi.

Đừng dùng việc factory tạo xong làm bằng chứng rằng map nền hỗ trợ tất cả thao tác mong muốn. Khi ứng dụng cần thêm/xóa thành viên, hãy chọn một map có quyền cập nhật phù hợp ngay từ đầu.

## 6. Các đặc tính set thừa hưởng từ map

### Thứ tự duyệt

Với `LinkedHashMap` theo thứ tự chèn, set thích nghi duyệt theo thứ tự khóa được chèn. Thêm lại một thành viên đã có không tạo một vị trí mới; xóa rồi thêm lại đưa nó vào cuối thứ tự chèn.

Ví dụ này hữu ích để kiểm chứng cơ chế, nhưng nhu cầu set thường theo thứ tự chèn đã có `LinkedHashSet` diễn đạt trực tiếp. Không cần dùng factory cho mọi map vốn đã có một kiểu set tương ứng quen thuộc. [LinkedHashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedHashMap.html), [LinkedHashSet](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedHashSet.html).

Không hứa thứ tự chèn cho một set dựa trên `HashMap`, `IdentityHashMap` hoặc `ConcurrentHashMap` chỉ vì code có các lần add theo một thứ tự cụ thể.

### Định danh tham chiếu

`IdentityHashMap` xem hai khóa là cùng nhau khi chúng là cùng tham chiếu, tức `==`. Vì vậy hai `new String("item")` khác nhau có thể cùng là hai thành viên trong set dù `equals` của chúng trả `true`.

Một đối tượng mới khác tham chiếu nhưng bằng nội dung không tự tìm thấy thành viên cũ. Quy tắc này có ích khi theo dõi chính các nút đối tượng đã thăm, không muốn gộp hai nút chỉ vì chúng bằng nhau về dữ liệu. [IdentityHashMap, Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/IdentityHashMap.html).

Đây là ngữ nghĩa chuyên biệt. Không dùng một set theo định danh như tập giá trị thông thường rồi kỳ vọng mọi phép so sánh set, phép tập hợp hoặc tiện ích kết hợp với một set dựa trên `equals` đều có ý nghĩa thông thường.

Trong thí nghiệm, dùng `new String` để bảo đảm có các tham chiếu khác nhau. Hai string literal giống nhau không là một cách kiểm tra thích hợp vì chúng có thể được dùng chung.

### Khóa yếu

Có thể tạo set dựa trên `WeakHashMap`:

~~~java
Set<Object> tracked = Collections.newSetFromMap(
        new WeakHashMap<Object, Boolean>());
~~~

Đây là mảnh mã minh họa cần import `Set`, `Collections` và `WeakHashMap`. Nó không tạo một tập giữ mạnh mọi đối tượng thành viên.

Khi không còn tham chiếu mạnh phù hợp tới một khóa, việc dọn rác có thể làm thành viên biến mất. Không dùng set khóa yếu làm sổ lưu bắt buộc phải giữ mọi mục cho tới khi gọi remove.

Không viết stdout khẳng định “gọi `System.gc()` xong size chắc chắn bằng 0”. Thời điểm thu gom và việc giữ khóa còn sống không do một dòng yêu cầu GC quyết định. Chương trình chính không dùng một kết quả GC để làm bằng chứng cố định. [WeakHashMap, Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/WeakHashMap.html).

### Đồng thời và chính sách `null`

Set dựa trên `ConcurrentHashMap` thừa hưởng khả năng thao tác đồng thời của map, bao gồm việc không nhận khóa `null`. Set không tự thêm khóa ngoài hay biến các thao tác nhiều bước thành một giao dịch.

Đối với nhu cầu set đồng thời thông thường, `ConcurrentHashMap.newKeySet()` là API trực tiếp có sẵn trong Java 17:

~~~java
Set<String> active = ConcurrentHashMap.newKeySet();
~~~

`newSetFromMap` vẫn hữu ích để hiểu và dùng các map nền phù hợp khác. Chọn API thể hiện rõ mục đích, không dùng một lớp thích nghi chỉ để tăng số lớp. [ConcurrentHashMap và newKeySet](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html#newKeySet()).

Một set theo map thông thường nhận `null` có thể nhận `null`; một map không nhận khóa `null` sẽ truyền giới hạn ấy sang set. Giao diện `Set<E>` không tự xác định chung một chính sách `null` cho mọi cách tạo.

## 7. Chương trình hoàn chỉnh

Lưu toàn bộ mã vào **`BackedAdaptersDemo.java`**. Các map dùng tạo set thành công đều được tạo trực tiếp trong factory, không được giữ alias để đọc hoặc sửa sau đó.

Map không rỗng được tạo riêng chỉ để kiểm tra trường hợp bị từ chối. Các ví dụ set đồng thời chạy trong một luồng nhằm kiểm tra thao tác thêm/trùng/`null`; bảo đảm đồng thời đến từ hợp đồng lớp nền, không được suy ra chỉ từ một lần chạy đơn luồng.

~~~java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Deque;
import java.util.HashMap;
import java.util.IdentityHashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.NoSuchElementException;
import java.util.Queue;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.LinkedBlockingDeque;

public class BackedAdaptersDemo {
    private static void rejects(
            String label,
            Class<? extends RuntimeException> expected,
            Runnable action) {
        try {
            action.run();
            throw new AssertionError(label + " unexpectedly succeeded");
        } catch (RuntimeException ex) {
            if (!expected.isInstance(ex)) {
                throw new AssertionError(label + " wrong exception", ex);
            }
            System.out.println(label + "=" + ex.getClass().getSimpleName());
        }
    }

    public static void main(String[] args) {
        Deque<String> backing = new ArrayDeque<>();
        Queue<String> lifo = Collections.asLifoQueue(backing);
        lifo.offer("A");
        lifo.offer("B");
        lifo.add("C");
        System.out.println("lifo.view=" + new ArrayList<>(lifo));
        System.out.println("lifo.backing=" + new ArrayList<>(backing));
        System.out.println("lifo.peek=" + lifo.peek());
        System.out.println("lifo.remove=" + lifo.remove());
        System.out.println("lifo.poll=" + lifo.poll());
        System.out.println("lifo.element=" + lifo.element());
        System.out.println("lifo.lastPoll=" + lifo.poll());
        System.out.println("lifo.emptyPoll=" + lifo.poll());
        System.out.println("lifo.emptyPeek=" + lifo.peek());
        rejects("lifo.emptyRemove", NoSuchElementException.class,
                lifo::remove);
        rejects("lifo.null", NullPointerException.class,
                () -> lifo.offer(null));

        Deque<String> existing =
                new ArrayDeque<>(List.of("old-first", "old-last"));
        Queue<String> adapted = Collections.asLifoQueue(existing);
        System.out.println("existing.before=" + new ArrayList<>(adapted));
        adapted.add("new");
        System.out.println("existing.afterAdd=" + new ArrayList<>(adapted));
        System.out.println("existing.removeLast=" + existing.removeLast());
        System.out.println("existing.afterBackingEdit="
                + new ArrayList<>(adapted));

        Queue<String> bulk = Collections.asLifoQueue(new ArrayDeque<>());
        bulk.addAll(List.of("A", "B", "C"));
        System.out.println("bulk.view=" + new ArrayList<>(bulk));

        Queue<String> bounded =
                Collections.asLifoQueue(new LinkedBlockingDeque<>(2));
        System.out.println("bounded.offers="
                + bounded.offer("A") + "/"
                + bounded.offer("B") + "/"
                + bounded.offer("C"));
        System.out.println("bounded.peek=" + bounded.peek());
        rejects("bounded.addFull", IllegalStateException.class,
                () -> bounded.add("C"));
        System.out.println("bounded.polls="
                + bounded.poll() + "/" + bounded.poll());

        Queue<String> partial =
                Collections.asLifoQueue(new LinkedBlockingDeque<>(2));
        rejects("partial.addAll", IllegalStateException.class,
                () -> partial.addAll(List.of("A", "B", "C")));
        System.out.println("partial.afterFailure=" + new ArrayList<>(partial));

        Set<String> ordered = Collections.newSetFromMap(
                new LinkedHashMap<String, Boolean>());
        System.out.println("ordered.firstAdd=" + ordered.add("beta"));
        ordered.add("alpha");
        System.out.println("ordered.equalAdd="
                + ordered.add(new String("beta")));
        System.out.println("ordered.values=" + new ArrayList<>(ordered));
        ordered.remove("beta");
        ordered.add("beta");
        System.out.println("ordered.reinserted=" + new ArrayList<>(ordered));
        ordered.add(null);
        System.out.println("ordered.null=" + ordered.contains(null));

        String first = new String("item");
        String second = new String("item");
        Set<String> identity = Collections.newSetFromMap(
                new IdentityHashMap<String, Boolean>());
        System.out.println("identity.equalValues=" + first.equals(second));
        System.out.println("identity.adds="
                + identity.add(first) + "/" + identity.add(second));
        System.out.println("identity.size=" + identity.size());
        System.out.println("identity.containsSame=" + identity.contains(first));
        System.out.println("identity.containsEqualOther="
                + identity.contains(new String("item")));
        System.out.println("identity.removeSame=" + identity.remove(first));
        System.out.println("identity.afterRemove.size=" + identity.size());

        Map<String, Boolean> nonempty = new HashMap<>();
        nonempty.put("already", Boolean.FALSE);
        rejects("nonempty.map", IllegalArgumentException.class,
                () -> Collections.newSetFromMap(nonempty));
        Set<String> readonlyBacking = Collections.newSetFromMap(
                Collections.<String, Boolean>emptyMap());
        rejects("readonly.mapAdd", UnsupportedOperationException.class,
                () -> readonlyBacking.add("x"));

        Set<String> concurrent = Collections.newSetFromMap(
                new ConcurrentHashMap<String, Boolean>());
        System.out.println("concurrent.adds="
                + concurrent.add("job") + "/" + concurrent.add("job"));
        System.out.println("concurrent.size=" + concurrent.size());
        rejects("concurrent.null", NullPointerException.class,
                () -> concurrent.add(null));
    }
}
~~~

Biên dịch và chạy từ thư mục chứa tệp:

~~~shell
javac --release 17 -encoding UTF-8 BackedAdaptersDemo.java
java BackedAdaptersDemo
~~~

Cần JDK 17 trở lên để dùng lệnh biên dịch này. Mã đã được biên dịch với `--release 17` và chạy trên OpenJDK 24.0.2, thoát thành công. Stdout chính xác:

~~~text
lifo.view=[C, B, A]
lifo.backing=[C, B, A]
lifo.peek=C
lifo.remove=C
lifo.poll=B
lifo.element=A
lifo.lastPoll=A
lifo.emptyPoll=null
lifo.emptyPeek=null
lifo.emptyRemove=NoSuchElementException
lifo.null=NullPointerException
existing.before=[old-first, old-last]
existing.afterAdd=[new, old-first, old-last]
existing.removeLast=old-last
existing.afterBackingEdit=[new, old-first]
bulk.view=[C, B, A]
bounded.offers=true/true/false
bounded.peek=B
bounded.addFull=IllegalStateException
bounded.polls=B/A
partial.addAll=IllegalStateException
partial.afterFailure=[B, A]
ordered.firstAdd=true
ordered.equalAdd=false
ordered.values=[beta, alpha]
ordered.reinserted=[alpha, beta]
ordered.null=true
identity.equalValues=true
identity.adds=true/true
identity.size=2
identity.containsSame=true
identity.containsEqualOther=false
identity.removeSame=true
identity.afterRemove.size=1
nonempty.map=IllegalArgumentException
readonly.mapAdd=UnsupportedOperationException
concurrent.adds=true/false
concurrent.size=1
concurrent.null=NullPointerException
~~~

### Giải thích các nhóm kết quả

**`lifo`:** thêm A, B, C cho thứ tự đầu tới cuối C, B, A trên cả view và deque. Peek không lấy ra; remove/poll lấy từ đầu. Element nhìn thấy A còn lại. Hai phép thăm dò rỗng trả `null`, còn remove rỗng ném `NoSuchElementException`.

**`lifo.null`:** deque nền `ArrayDeque` từ chối `null`; view không thay chính sách đó.

**`existing`:** deque không rỗng vẫn được thích nghi. Factory không đảo hai phần tử cũ; add new đặt new lên đầu. Xóa cuối trực tiếp trên deque được nhìn thấy qua view, chứng minh dữ liệu dùng chung. Đây là thí nghiệm quan hệ view, không là khuyến nghị để nhiều thành phần trộn tùy ý các đường sửa.

**`bulk`:** addAll A, B, C trở thành các lần addFirst nên thứ tự C, B, A.

**`bounded`:** hai offer đầu thành công, lần ba trả false khi hết chỗ. Add khi đầy ném lỗi. Lấy phần tử vẫn theo B rồi A, không theo thứ tự offer FIFO.

**`partial`:** một lời gọi addAll có thể đã thêm hai phần tử trước khi thất bại. Dữ liệu B, A còn lại sau ngoại lệ, không có tự phục hồi về rỗng.

**`ordered`:** thêm beta lần đầu thay đổi set; thêm một chuỗi mới bằng beta không thay đổi thành viên theo equals. Thứ tự ban đầu beta, alpha; xóa rồi thêm beta cho alpha, beta. Map nền đã được giao riêng cho set và không bị truy cập sau tạo.

**`identity`:** hai chuỗi bằng nội dung nhưng khác tham chiếu đều được thêm. Tìm đúng tham chiếu thành công, tìm một chuỗi mới bằng nội dung thất bại. Xóa đúng tham chiếu chỉ xóa một trong hai thành viên.

**`nonempty.map`:** một khóa gắn Boolean.FALSE vẫn làm map không rỗng và bị từ chối. Giá trị false không được hiểu là “không phải thành viên” để vượt điều kiện đầu vào.

**`readonly.mapAdd`:** map rỗng không sửa được không cung cấp khả năng thêm cho set. Kiểm tra rỗng chưa đủ để kết luận mọi quyền sửa.

**`concurrent`:** thêm cùng chuỗi lần thứ hai không làm thay đổi set. Khóa null bị từ chối theo chính sách ConcurrentHashMap. Không in thứ tự của set nền này vì nó không hứa thứ tự chèn.

## 8. Cách dùng trong thiết kế chương trình

### Một thuật toán nhận Queue cần quy tắc lấy khác nhau

Nếu thuật toán chỉ gọi offer/poll và chấp nhận chính sách thứ tự do phía gọi chọn, có thể cấp một queue FIFO hoặc view LIFO của deque.

Ví dụ xử lý công việc chờ có thể dùng FIFO để ưu tiên việc cũ hoặc LIFO cho một quy trình duyệt theo chiều sâu. Nhưng sự thay thế chỉ hợp lệ khi hợp đồng thuật toán không ngầm yêu cầu FIFO cho tính đúng.

Tên giao diện `Queue` không thay thế tài liệu về thứ tự. Khi thứ tự quyết định hành vi, hãy ghi rõ queue được cấp có chính sách nào.

### Theo dõi đối tượng đã thăm theo định danh

Khi duyệt một đồ thị đối tượng, hai nút có thể bằng dữ liệu nhưng vẫn là hai đối tượng khác nhau cần xử lý. Set theo định danh đáp ứng cách nhận diện ấy.

Nếu nghiệp vụ là tập mã hoặc tập giá trị, dùng equals thông thường thường phù hợp hơn. Không chọn định danh chỉ vì nó tránh gọi equals; thay quan hệ bình đẳng là thay ý nghĩa dữ liệu.

### Danh sách theo dõi không giữ sống đối tượng

Set khóa yếu có thể phù hợp khi chỉ muốn theo dõi đối tượng mà không tự trở thành lý do giữ nó tồn tại. Cần chấp nhận việc thành viên biến mất theo vòng đời tham chiếu.

Nếu dữ liệu phải tồn tại chắc chắn, chọn cấu trúc giữ mạnh với vòng đời xóa rõ ràng. Khóa yếu không là một cách giới hạn size chính xác hoặc bộ nhớ đệm có lịch hết hạn xác định.

### Thành viên được chia sẻ giữa nhiều luồng

Set từ map đồng thời có thể phù hợp cho thao tác thành viên đơn lẻ. Tuy vậy, `contains` rồi `add` là hai bước; cần cân nhắc dùng kết quả của chính `add` nếu câu hỏi là “lần này có thêm thành viên mới không?”.

Các nhóm thao tác, việc duyệt toàn bộ, trạng thái size hoặc cập nhật dữ liệu ngoài set vẫn cần hợp đồng nhất quán riêng. Không hứa một snapshot chỉ vì thao tác nền là an toàn đồng thời.

Với queue thích nghi trên một deque đồng thời, thao tác được chuyển cho deque có chính sách của nó. View không tự thêm một giao thức nguyên tử cho addAll, cho vòng lặp tiêu thụ hoặc cho trạng thái của các phần tử đang được xử lý.

## 9. Những điều cần kiểm tra ở cấu trúc nền

Đối với LIFO queue, trước tiên xác định cách thêm/lấy, chính sách đầy/rỗng và null. Sau đó quyết định có giữ lộ deque ra ngoài không. Nếu có, mọi đường sửa phải được đưa vào cách giải thích thứ tự của hệ thống.

Đối với set từ map, kiểm tra map rỗng, hỗ trợ các cập nhật cần dùng và được chuyển quyền sử dụng riêng. Sau đó xác định quan hệ bình đẳng khóa, thứ tự duyệt, quyền giữ sống khóa và chính sách đồng thời.

Không thể kiểm tra các đặc tính ấy bằng mỗi kiểu khai báo `Queue<T>` hay `Set<E>`. Phải biết cách tạo và hợp đồng của lớp nền.

Về chi phí, adapter chuyển các thao tác xuống nền nên chi phí phụ thuộc thao tác tương ứng của nền. addAll là chuỗi thao tác thành phần, không phải phép gộp không có chi phí. Đặc tính thứ tự hay đồng thời của nền không tự biến các phần tử thành dữ liệu bất biến sâu.

Nếu có kiểu trực tiếp như `LinkedHashSet`, `HashSet` hoặc `ConcurrentHashMap.newKeySet()` đáp ứng đúng mục tiêu, lựa chọn trực tiếp giúp người đọc nhận diện ý định nhanh hơn. Điểm mạnh của các factory ở bài này là thích nghi một cấu trúc nền có ngữ nghĩa cần thiết, không phải thay mọi collection tiêu chuẩn bằng lớp bọc.

## 10. Thực hành có đáp án

### Bài 1 — Queue không tự đồng nghĩa FIFO

Một deque rỗng được thích nghi bằng `asLifoQueue`. Gọi add A, add B, add C rồi gọi poll ba lần.

**Câu hỏi:** Thứ tự trả là gì? Nếu chỉ giữ ArrayDeque dưới kiểu Queue mà không dùng factory, cách thêm thông thường khác ở đâu?

**Đáp án:** View LIFO trả C, B, A vì add và poll cùng dùng đầu deque. Queue thông thường của deque thêm ở cuối và lấy ở đầu nên tạo FIFO. Thay kiểu biến không tự thay thao tác nền như adapter làm.

### Bài 2 — Deque đã có dữ liệu

Deque từ đầu tới cuối là `[old1, old2]`. Tạo view LIFO rồi gọi `offer("new")`.

**Câu hỏi:** Có phải factory yêu cầu rỗng hoặc tự đảo thành old2, old1 không? Thứ tự hiện tại là gì?

**Đáp án:** Không. Deque không bắt buộc rỗng; dữ liệu cũ không tự đảo. Sau offer là `[new, old1, old2]`. Quy tắc đặt vào đầu áp dụng cho thao tác qua view, không suy lịch sử tạo các phần tử cũ.

### Bài 3 — Thêm cả nhóm khi đầy

Một view dựa trên deque dung lượng 2 đang rỗng. Gọi addAll với A, B, C.

**Câu hỏi:** Có thể giả định ngoại lệ đồng nghĩa không có phần tử nào được thêm không?

**Đáp án:** Không. addAll thực hiện chuỗi addFirst; hai phần tử đầu có thể đã được thêm trước lỗi ở phần tử thứ ba. Với thí nghiệm trong bài, trạng thái sau lỗi là B, A. Nếu cần chấp nhận cả nhóm như một đơn vị, phải thiết kế giao thức khác.

### Bài 4 — Map có giá trị false

~~~java
Map<String, Boolean> map = new HashMap<>();
map.put("x", Boolean.FALSE);
~~~

**Câu hỏi:** Có thể truyền map ấy cho newSetFromMap vì “x chưa active” không?

**Đáp án:** Không. Map có một ánh xạ nên không rỗng; factory ném IllegalArgumentException. Điều kiện là không có ánh xạ, không phải mọi giá trị đều false. Nếu cần tập khóa từ dữ liệu map hiện hữu, phải dùng một cách khác đúng mục tiêu.

### Bài 5 — Giữ map để debug sau tạo

Một thành phần tạo map rỗng, truyền vào newSetFromMap, rồi vẫn giữ map để gọi put/get hoặc đọc keySet ở một chỗ khác.

**Câu hỏi:** Cách sở hữu này có phù hợp hợp đồng không? Cách tạo nào giảm rủi ro?

**Đáp án:** Không phù hợp khuyến cáo của API: không truy cập trực tiếp map sau khi tạo set. Tạo map ngay trong lời gọi factory và chỉ giữ Set kết quả; mọi thao tác và quan sát cần đi qua set. Không giữ một view của map để tạo đường truy cập gián tiếp khác.

### Bài 6 — Hai chuỗi bằng nhau trong set định danh

Hai biến được tạo bằng hai lời gọi `new String("x")` riêng, rồi thêm vào set dựa trên IdentityHashMap.

**Câu hỏi:** Size có thể là 2 không? contains với một new String("x") thứ ba có tìm thấy không?

**Đáp án:** Size là 2 trong tình huống này vì hai tham chiếu khác nhau. Chuỗi thứ ba không phải một trong các tham chiếu đang lưu nên không tìm thấy. Đây là ngữ nghĩa định danh có chủ đích, khác tập giá trị dùng String.equals.

### Bài 7 — Map rỗng nhưng không ghi được

Map rỗng không sửa được được truyền cho factory, sau đó gọi set.add("x").

**Câu hỏi:** Việc tạo set thành công đã chứng minh add được hỗ trợ chưa?

**Đáp án:** Chưa. Factory kiểm tra rỗng không biến map thành map sửa được; add phải ghi xuống map và có thể ném UnsupportedOperationException như ví dụ. Chọn map nền có quyền sửa cần dùng ngay từ đầu.

### Bài 8 — Khóa yếu và đồng thời

Một set dùng WeakHashMap; set khác dùng ConcurrentHashMap.

**Câu hỏi:** Có được hứa set khóa yếu chỉ mất phần tử khi gọi remove không? Có được hứa set đồng thời nhận null và mọi nhóm addAll là nguyên tử không?

**Đáp án:** Không. Thành viên khóa yếu có thể biến mất khi khóa không còn được giữ mạnh phù hợp và được thu gom. ConcurrentHashMap từ chối null và các bảo đảm thao tác đơn lẻ không tự gộp nhiều bước thành một giao dịch. Chọn cấu trúc nền là chọn cả những chính sách ấy, không chỉ chọn một cách lưu trữ bên trong.

Hai adapter này chỉ hữu ích khi hợp đồng nền được đưa vào hợp đồng sử dụng. Với asLifoQueue, điều cốt lõi là cùng đầu thêm/lấy và view dùng chung deque. Với newSetFromMap, điều cốt lõi là map rỗng, sở hữu riêng và các đặc tính khóa được kế thừa vào set.
