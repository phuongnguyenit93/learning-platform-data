# Tính an toàn của đối tượng phần tử bên trong collection

## 1. Collection giữ tham chiếu, không bọc mọi thao tác của phần tử

Một collection đồng thời có thể bảo vệ việc thêm, tìm, lấy hoặc xóa phần tử theo hợp đồng của nó. Điều đó không tự biến mọi đối tượng được lưu bên trong thành đối tượng an toàn khi nhiều luồng cùng sửa.

Ví dụ:

```java
ConcurrentHashMap<String, Counter> counters = new ConcurrentHashMap<>();
counters.put("hits", new Counter());
counters.get("hits").increment();
```

Đây là đoạn minh họa, giả định `Counter` là lớp ứng dụng đã được khai báo. Ba việc khác nhau đang diễn ra:

1. Map lưu một ánh xạ từ `"hits"` đến tham chiếu `Counter`.
2. `get` lấy tham chiếu đó theo cơ chế an toàn của map.
3. `increment` chạy trên chính đối tượng `Counter`, theo cách mà lớp `Counter` được viết.

Nếu `increment` chỉ là `value++` trên một trường thông thường, map không tự thêm khóa hay phép toán nguyên tử cho lệnh đó. Hai luồng có thể lấy cùng một tham chiếu an toàn rồi cùng sửa đối tượng không an toàn.

Cần luôn xét ít nhất hai lớp:

```text
collection: ai được thêm, tìm, thay hoặc xóa tham chiếu?
                         ↓
phần tử: ai được đọc/sửa trạng thái bên trong tham chiếu đó?
```

Khi giá trị là một collection khác, chẳng hạn `ConcurrentHashMap<String, ArrayList<String>>`, nguyên tắc này tiếp tục áp dụng xuống từng lớp, không dừng ở container ngoài cùng.

## 2. Công bố an toàn có bảo đảm, nhưng có ranh giới thời gian

Các collection trong `java.util.concurrent` có bảo đảm về hiển thị bộ nhớ. Theo [Memory Consistency Properties của `java.util.concurrent`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/package-summary.html), hành động trong một luồng trước khi đưa đối tượng vào collection đồng thời có quan hệ xảy ra-trước (happens-before) với hành động sau khi một luồng khác truy cập hoặc lấy đối tượng đó từ collection.

Có thể hình dung:

```text
luồng A: khởi tạo phần tử → đưa vào collection
                                      ↓ bảo đảm trao đổi qua collection
luồng B:                      lấy được phần tử → đọc dữ liệu đã chuẩn bị
```

Đây là cơ sở để chuẩn bị một thông điệp rồi gửi qua hàng đợi hoặc đưa một đối tượng đã khởi tạo vào map dùng chung.

Nhưng nếu luồng A tiếp tục sửa đối tượng **sau** khi đã đưa vào collection, bảo đảm của lần đưa trước không tự bao phủ các lần sửa tương lai:

```text
luồng A: đưa phần tử vào collection → sửa trường x
luồng B: lấy phần tử từ collection  → đọc trường x
```

Muốn đọc và sửa `x` đúng khi hai phía có thể chạy đồng thời, cần quy tắc bổ sung: bất biến, quyền sở hữu độc quyền, `volatile`, phép toán nguyên tử hoặc khóa phù hợp với yêu cầu. Chọn đúng cơ chế theo loại thao tác, không chỉ theo mong muốn “thấy được dữ liệu mới”.

Không phải mọi `Collection` đều có bảo đảm đồng thời này. Một `ArrayList` thông thường bị chia sẻ và sửa không đồng bộ không được nâng cấp chỉ vì biến khai báo bằng kiểu `List`.

## 3. Lỗi mất cập nhật vẫn xảy ra ở bên trong phần tử

Giả sử phần tử có trường:

```java
class Counter {
    int value;
}
```

Hai luồng đều muốn tăng `value` một lần. Nếu mỗi luồng đọc 0 rồi ghi lại 1, kết quả cuối là 1 thay vì 2. Collection vẫn có thể chứa đúng một `Counter` và không hề bị hỏng cấu trúc; lỗi nằm ở thao tác trên đối tượng dùng chung.

Một tình huống tương tự với giá trị danh sách:

```java
ConcurrentHashMap<String, List<String>> groups = new ConcurrentHashMap<>();
groups.computeIfAbsent("team", key -> new ArrayList<>()).add("member");
```

Đoạn minh họa cần các import Java phù hợp. `computeIfAbsent` bảo vệ việc quản lý ánh xạ của map. Sau khi nó trả danh sách, `.add` là thao tác của `ArrayList`. Hai luồng thêm vào cùng danh sách không được map tự điều phối.

Vì vậy, khi đánh giá tính đúng, hãy lần theo tham chiếu đến nơi thực sự có thay đổi. Dừng ở tên `ConcurrentHashMap` chưa đủ để kết luận.

## 4. Ví dụ Java 17+: map an toàn, phần tử chưa an toàn

Lưu thành `ElementSafetyDemo.java`. Chương trình cố ý đặt hai luồng vào cùng một thứ tự đọc – ghi để thấy lỗi mất cập nhật, thay vì chạy một vòng đua rồi đoán một con số có thể thay đổi giữa các lần chạy.

```java
import java.util.concurrent.Callable;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CyclicBarrier;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class ElementSafetyDemo {
    static final class MutableCounter {
        int value;
    }

    private static void runPair(ExecutorService pool, Callable<Void> action)
            throws Exception {
        Future<Void> first = pool.submit(action);
        Future<Void> second = pool.submit(action);
        try {
            first.get(5, TimeUnit.SECONDS);
            second.get(5, TimeUnit.SECONDS);
        } finally {
            first.cancel(true);
            second.cancel(true);
        }
    }

    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newFixedThreadPool(2);
        ConcurrentHashMap<String, MutableCounter> unsafeValues =
                new ConcurrentHashMap<>();
        unsafeValues.put("hits", new MutableCounter());
        ConcurrentHashMap<String, AtomicInteger> safeValues =
                new ConcurrentHashMap<>();
        safeValues.put("hits", new AtomicInteger());

        try {
            CyclicBarrier bothRead = new CyclicBarrier(2);
            runPair(pool, () -> {
                MutableCounter counter = unsafeValues.get("hits");
                int observed = counter.value;
                bothRead.await(5, TimeUnit.SECONDS);
                counter.value = observed + 1;
                return null;
            });
            System.out.println("plain field after two increments: "
                    + unsafeValues.get("hits").value);

            runPair(pool, () -> {
                safeValues.get("hits").incrementAndGet();
                return null;
            });
            System.out.println("atomic field after two increments: "
                    + safeValues.get("hits").get());
        } finally {
            pool.shutdownNow();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("workers did not terminate");
            }
        }
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 ElementSafetyDemo.java
java ElementSafetyDemo
```

Stdout khi các tác vụ hoàn tất trong thời hạn minh họa:

```text
plain field after two increments: 1
atomic field after two increments: 2
```

Vì sao dòng đầu có giá trị xác định trong ví dụ này?

1. Cả hai luồng đọc trường trước khi tới `bothRead.await`.
2. Không luồng nào được vượt qua điểm hẹn trước khi cả hai đã đến, nên cả hai đều đã đọc giá trị ban đầu là 0 trước các lần ghi.
3. Mỗi luồng ghi lại `0 + 1`, nên hai lần tăng theo ý định chỉ để lại giá trị 1.
4. Luồng chính chờ kết quả của cả hai tác vụ bằng `Future.get()` trước khi in.

Điểm hẹn chỉ giúp tái hiện một cách xen kẽ có lỗi; nó không biến chuỗi đọc – ghi thành phép tăng nguyên tử. Phần mã ghi trường thông thường là minh họa lỗi, không phải mẫu nên dùng trong ứng dụng.

Ở phần sau, `AtomicInteger.incrementAndGet()` cung cấp phép tăng nguyên tử của chính giá trị đó, như mô tả trong [Java SE `AtomicInteger`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/atomic/AtomicInteger.html). Cả hai map đều an toàn ở cấp cấu trúc; kết quả khác nhau vì phần tử có cơ chế khác nhau.

## 5. Bốn cách thiết kế trạng thái phần tử

### Cách 1: dùng phần tử bất biến

Nếu phần tử không thay đổi sau khi tạo và không giữ trạng thái có thể sửa bị lộ ra ngoài, nhiều luồng có thể đọc nó mà không phải phối hợp các lần ghi vào chính đối tượng đó.

```java
record UserView(String id, String displayName) {}
```

Với các trường `String` trong ví dụ này, không có danh sách hoặc mảng có thể sửa bị chia sẻ qua record. Khi muốn đổi tên, tạo `UserView` mới rồi cập nhật tham chiếu theo cơ chế phù hợp.

Không dùng từ khóa `final` hoặc `record` như bằng chứng tự động về bất biến sâu. `final List<Item>` chỉ làm tham chiếu không bị gán lại; danh sách hoặc `Item` bên trong vẫn có thể sửa nếu thiết kế cho phép.

Ví dụ sao chép danh sách để chặn thay đổi cấu trúc từ bên ngoài:

```java
record Batch(java.util.List<String> names) {
    Batch {
        names = java.util.List.copyOf(names);
    }
}
```

`List.copyOf` tạo danh sách không cho thêm, xóa hoặc thay phần tử. Nhưng nếu phần tử là một đối tượng có thể sửa, nó không tự sao chép sâu đối tượng ấy. [Hợp đồng `List` về các danh sách không thể sửa](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/List.html) nêu rõ dữ liệu có thể trông như thay đổi nếu chính các phần tử có thể sửa.

### Cách 2: bản thân phần tử có cơ chế đồng thời

`AtomicInteger` phù hợp cho phép tăng một giá trị đơn. Một lớp tự quản lý khóa cũng có thể bảo vệ một nhóm trường:

```java
final class SafeCounter {
    private int value;

    synchronized void increment() {
        value++;
    }

    synchronized int get() {
        return value;
    }
}
```

Đọc và ghi đều lấy cùng monitor của đối tượng. Trường được giữ riêng để bên khác không sửa trực tiếp và bỏ qua giao thức.

Nếu cần bảo vệ quan hệ giữa nhiều trường, phải dùng một thao tác chung cho cả quan hệ đó. Hai trường `AtomicInteger` độc lập không tự làm việc cập nhật cả hai thành một giao dịch. Tương tự, kiểm tra `counter.get() < limit` rồi tăng bằng một lời gọi khác vẫn có khoảng đua; cần một hành động kiểm tra – cập nhật đúng yêu cầu.

### Cách 3: thay cả giá trị bằng một phiên bản mới

Có thể giữ các giá trị bất biến rồi cập nhật qua phương thức nguyên tử theo khóa của map:

```java
record Stock(int available, int reserved) {}
ConcurrentHashMap<String, Stock> stocks = new ConcurrentHashMap<>();
stocks.put("book", new Stock(10, 0));
stocks.computeIfPresent("book", (key, old) ->
        old.available() > 0
                ? new Stock(old.available() - 1, old.reserved() + 1)
                : old);
```

Đây là đoạn minh họa để đặt trong chương trình Java thích hợp. Hai số được giữ trong cùng một đối tượng bất biến; người đọc lấy một `Stock` rồi đọc hai trường từ chính phiên bản đó. Hàm tính tạo phiên bản mới thay vì sửa phiên bản mà người đọc khác đang giữ.

Mọi nơi cập nhật vẫn phải tuân theo quy tắc nghiệp vụ; một `put` tùy tiện có thể ghi đè trạng thái. Bảo đảm theo một khóa cũng chưa bao phủ chuyển dữ liệu qua nhiều khóa hoặc tài nguyên bên ngoài.

### Cách 4: chuyển quyền sở hữu qua hàng đợi

Một đối tượng có thể được sửa an toàn mà không cần nhiều khóa nếu tại mỗi giai đoạn chỉ một bên được quyền sửa nó.

```text
bên sản xuất chuẩn bị đối tượng
        ↓ đưa vào hàng đợi
bên sản xuất ngừng sử dụng để sửa
        ↓ bên tiêu thụ lấy được
bên tiêu thụ trở thành bên chịu trách nhiệm sửa tiếp
```

Đây là giao thức của ứng dụng. Hàng đợi chỉ chuyển tham chiếu, không buộc bên sản xuất quên tham chiếu đã giữ. Nếu bên sản xuất tiếp tục sửa, hoặc đưa cùng một đối tượng vào hàng nhiều lần cho nhiều bên tiêu thụ, quyền sở hữu độc quyền có thể không còn.

Khi gửi tiếp sang giai đoạn khác, phải xác định rõ lúc nào bên hiện tại ngừng sửa. Nếu cần nhiều bên cùng đọc đồng thời, ưu tiên trạng thái bất biến hoặc bản sao phù hợp thay vì một đối tượng đang bị sửa không kiểm soát.

## 6. Những cách sửa chưa đủ

| Cách làm | Vì sao chưa giải quyết toàn bộ vấn đề |
| --- | --- |
| Đổi trường thành `volatile int` rồi giữ `value++` | `volatile` hỗ trợ hiển thị bộ nhớ nhưng phép đọc – cộng – ghi vẫn không thành một phép tăng nguyên tử |
| Giữ `final Counter counter` | Tham chiếu cố định, trạng thái bên trong `counter` vẫn có thể sửa |
| Bọc đối tượng trong record nhưng chứa danh sách có thể sửa | Record không tự sao chép hoặc đóng băng toàn bộ đối tượng con |
| Gọi lại `map.get(key)` trước mỗi lần sửa | Lấy tham chiếu an toàn không tự đồng bộ các trường của phần tử |
| `synchronized (collection)` ở một chỗ | Chỉ điều phối các bên cũng lấy đúng khóa ấy; người sửa trực tiếp phần tử có thể không tham gia |
| Tạo một đối tượng khóa mới trong mỗi lần gọi | Các lần gọi không tranh chấp cùng khóa nên không loại trừ nhau |
| Ngủ một khoảng trước khi đọc | Thời gian chờ không tạo giao thức đúng về bộ nhớ hoặc nguyên tử |

Khi một cơ chế giải quyết được một lớp yêu cầu, hãy ghi rõ lớp đó. Ví dụ một cờ dừng `volatile` có thể phù hợp cho việc công bố một trạng thái đơn giản, nhưng không tự bảo vệ toàn bộ quan hệ giữa nhiều trường của công việc.

## 7. Vòng đời phần tử cũng là một phần của tính đúng

Nếu luồng A lấy một phần tử từ map, sau đó luồng B xóa hoặc thay ánh xạ, A vẫn có thể giữ và sửa đối tượng cũ. Xóa ánh xạ không thu hồi mọi tham chiếu đã được phát ra.

Ví dụ một bộ đếm nguyên tử có thể hoàn toàn an toàn bên trong, nhưng một lần tăng xảy ra trên bộ đếm đã bị thay khỏi map. Người đọc map mới không thấy lần tăng đó. Đây là lỗi phối hợp vòng đời, không phải lỗi của `AtomicInteger`.

Tương tự, gỡ một bên nhận sự kiện khỏi danh sách không tự hủy callback đã bắt đầu hoặc nằm trong một phiên bản danh sách đang được duyệt. Nếu nghiệp vụ yêu cầu ngừng tuyệt đối sau khi gỡ, cần quy tắc phối hợp với những bên đã giữ tham chiếu.

Với khóa của map hoặc phần tử của tập hợp dựa trên băm, còn phải giữ ổn định các trường tham gia `equals`/`hashCode` trong lúc nó được dùng làm khóa. Sửa những trường đó có thể khiến tra cứu không còn tìm đúng đối tượng theo kỳ vọng, dù cấu trúc collection vẫn an toàn khi có nhiều luồng.

## 8. Ảnh chụp collection không đồng nghĩa ảnh chụp trạng thái mọi phần tử

Một iterator có thể giữ ổn định tập tham chiếu theo hợp đồng snapshot, nhưng các đối tượng được tham chiếu vẫn có thể bị sửa. Bản sao nông sang collection mới cũng giữ chung phần tử.

Nếu cần báo cáo nhất quán của nhiều trường, nhiều phần tử hoặc nhiều khóa, hãy xác định chính xác phạm vi ảnh chụp. Lựa chọn có thể là sao chép dữ liệu dưới khóa phù hợp, lưu toàn bộ trạng thái liên quan dưới dạng bất biến, hoặc dùng phiên bản/giao dịch ở lớp quản lý.

Không tự cho rằng “không ném `ConcurrentModificationException`” hoặc “đã sao chép sang list mới” chứng minh toàn bộ số liệu tồn tại đồng thời trong một trạng thái chung. An toàn khi duyệt cấu trúc và tính nhất quán nghiệp vụ là hai yêu cầu riêng.

## 9. Câu hỏi cần trả lời khi thiết kế

Với mỗi loại phần tử được chia sẻ, hãy xác định:

1. Phần tử có bất biến thật sự không, gồm cả đối tượng con và dữ liệu lộ ra qua getter?
2. Những luồng nào có thể giữ cùng tham chiếu, kể cả sau khi nó bị xóa khỏi collection?
3. Cơ chế nào bảo đảm nhìn thấy thay đổi, và cơ chế nào bảo đảm kiểm tra – cập nhật nguyên tử?
4. Có quan hệ giữa nhiều trường hoặc nhiều đối tượng cần được giữ đúng cùng nhau không?
5. Khi chuyển qua hàng đợi, bên cũ đã ngừng sửa hay vẫn giữ quyền sửa?
6. Khi thay hoặc xóa ánh xạ, xử lý thế nào với các thao tác đang dùng phiên bản cũ?

Tự kiểm tra: đặt `ArrayList` vào `ConcurrentHashMap` có làm `ArrayList.add` an toàn khi nhiều luồng cùng chạy không? Đặt một đối tượng có trường `volatile` vào hàng đợi có làm mọi phương thức của nó nguyên tử không? Tạo record chứa mảng có làm nội dung mảng bất biến không?

Cả ba câu đều cần trả lời “không tự động”. Phải nhìn vào thao tác thực tế, quyền sửa và cơ chế phối hợp của chính đối tượng phần tử.
