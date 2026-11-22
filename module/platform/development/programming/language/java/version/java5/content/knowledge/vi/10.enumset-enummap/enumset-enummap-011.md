# Chia sẻ EnumSet, EnumMap giữa các luồng một cách an toàn

## 1. Chuyên dụng cho enum không đồng nghĩa an toàn luồng

`EnumSet` và `EnumMap` có biểu diễn chuyên dụng và kiểm tra kiểu tốt cho miền enum, nhưng bản thân chúng **không tự đồng bộ hóa**. Nếu nhiều luồng truy cập cùng một đối tượng và có luồng sửa, cần một giao thức truy cập phù hợp.

Không nên suy ra an toàn luồng từ những đặc điểm sau:

- Các phần tử hoặc khóa là hằng enum.
- Trường giữ collection được khai báo `final`.
- Iterator không ném `ConcurrentModificationException`.
- Một phương thức có tên như `putIfAbsent`, `merge` hoặc `computeIfAbsent`.

`final` có thể ngăn gán lại trường tham chiếu, nhưng không khóa những thao tác trên đối tượng mà trường đó dẫn tới. Iterator nhất quán yếu không bảo đảm một ảnh chụp nguyên tử hay quyền sửa đồng thời tùy ý.

Tài liệu [EnumSet](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/EnumSet.html) và [EnumMap](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/EnumMap.html) đều nêu yêu cầu đồng bộ hóa bên ngoài khi có truy cập cùng lúc với sửa đổi.

## 2. Cần bảo vệ cả thao tác và quan hệ dữ liệu

Một bộ đếm theo enum có thể chứa thao tác đọc-sửa-ghi:

```java
int oldCount = counts.getOrDefault(event, 0);
counts.put(event, oldCount + 1);
```

Nếu hai luồng cùng đọc 10 rồi cùng ghi 11, một cập nhật bị mất. Việc từng lời gọi nhìn ngắn hoặc wrapper `Integer` bất biến không làm cả chuỗi trở thành nguyên tử.

Cũng có thể có quan hệ giữa hai cấu trúc. Ví dụ một sự kiện đã được ghi nhận phải có mặt trong `active` và có số đếm dương trong `counts`. Nếu chỉ khóa từng collection riêng khi sửa hoặc đọc, người đọc có thể nhìn thấy trạng thái ở giữa hai cập nhật.

Trước khi chọn công cụ, cần xác định:

1. Luồng nào có quyền sửa?
2. Các lần đọc cần nhìn thấy dữ liệu mới ở mức nào?
3. Những thao tác nào phải là một khối không bị chen ngang?
4. Có quan hệ cần giữ nhất quán giữa nhiều collection không?
5. Kết quả đưa ra ngoài là dữ liệu sống hay một ảnh chụp độc lập?

An toàn luồng không chỉ là tránh ngoại lệ; nó còn gồm khả năng nhìn thấy cập nhật và tính đúng của các quan hệ dữ liệu.

## 3. Cách rõ ràng: một khóa riêng bao toàn bộ trạng thái liên quan

Một lớp đóng gói có thể giữ một đối tượng khóa riêng, rồi dùng cùng khóa đó cho mọi lần đọc/sửa của trạng thái được bảo vệ.

```java
private final Object monitor = new Object();
private final EnumSet<Event> active = EnumSet.noneOf(Event.class);
private final EnumMap<Event, Integer> counts = new EnumMap<>(Event.class);
```

Đây là đoạn trường trong lớp `SharedState` ở chương trình đầy đủ. Các thao tác công khai không trả collection đang sống ra ngoài; chúng thực hiện cập nhật hoặc tạo ảnh chụp trong vùng `synchronized (monitor)`.

Cùng một khóa giúp đạt hai mục tiêu: chỉ một luồng thực hiện vùng được bảo vệ tại một thời điểm, và những lần mở khóa/khóa phù hợp tạo quan hệ nhìn thấy dữ liệu theo mô hình bộ nhớ Java.

Quy tắc mở khóa trước các lần khóa sau trên cùng monitor thuộc [JLS §17.4.5](https://docs.oracle.com/javase/specs/jls/se25/html/jls-17.html#jls-17.4.5). Chỉ khóa bên ghi nhưng bên đọc truy cập trực tiếp không tuân theo cùng giao thức là không đủ.

### Không để tham chiếu đang sống thoát ra ngoài

Nếu một getter trả thẳng `active`, `counts`, `keySet()` hoặc một view thay đổi được, người gọi có thể vượt qua khóa của lớp. Khi đó lời hứa “mọi truy cập đi qua monitor” không còn đúng.

Muốn xử lý lâu hoặc gọi mã bên ngoài, thường nên tạo ảnh chụp dưới khóa rồi thả khóa trước khi xử lý ảnh chụp. Không giữ khóa trong lúc thực hiện tác vụ chậm không cần thiết hoặc gọi callback tùy ý có thể khóa ngược trở lại.

## 4. Ảnh chụp cần được sao chép và công bố đúng

`Collections.unmodifiableSet(active)` chỉ tạo một view không cho người nhận sửa qua view đó; nếu lớp vẫn sửa `active`, view vẫn dựa trên đối tượng đang sống. Nó chưa phải ảnh chụp độc lập.

Để tạo ảnh chụp ổn định:

1. Giữ khóa bảo vệ nguồn trong lúc đọc/sao chép.
2. Tạo các tập/map độc lập.
3. Nếu không muốn người nhận sửa ảnh chụp, bọc bản sao không cho sửa.
4. Không giữ một alias khác để tiếp tục sửa những bản sao đã công bố.
5. Bảo đảm các đối tượng giá trị có chính sách bất biến hoặc đồng bộ hóa phù hợp.

Với enum không có trạng thái sửa đổi và giá trị `Integer` trong ví dụ, các phần tử/giá trị không đưa thêm trạng thái sửa đổi được vào ảnh chụp. Nếu giá trị là `List`, sao chép `EnumMap` chỉ sao chép tham chiếu tới danh sách; cần xử lý sâu hơn theo mô hình dữ liệu.

Ảnh chụp của hai cấu trúc liên quan phải được lấy trong cùng vùng khóa nếu cần một trạng thái thống nhất. Hai bản sao được lấy riêng ở hai thời điểm có thể không thuộc cùng một lần quan sát.

## 5. Chương trình nhiều luồng chạy đầy đủ

Lưu thành `SharedEnumCollectionsDemo.java`. `Snapshot` là một record của Java 17 dùng để mang dữ liệu; constructor của nó tạo bản sao và bọc không cho sửa. Record tự nó không làm collection bất biến.

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.EnumMap;
import java.util.EnumSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class SharedEnumCollectionsDemo {
    enum Event {
        ALPHA, BETA
    }

    record Snapshot(Set<Event> active, Map<Event, Integer> counts) {
        Snapshot {
            EnumSet<Event> activeCopy = EnumSet.noneOf(Event.class);
            activeCopy.addAll(active);
            active = Collections.unmodifiableSet(activeCopy);

            EnumMap<Event, Integer> countsCopy = new EnumMap<>(Event.class);
            countsCopy.putAll(counts);
            counts = Collections.unmodifiableMap(countsCopy);
        }
    }

    static final class SharedState {
        private final Object monitor = new Object();
        private final EnumSet<Event> active = EnumSet.noneOf(Event.class);
        private final EnumMap<Event, Integer> counts = new EnumMap<>(Event.class);

        void mark(Event event) {
            synchronized (monitor) {
                counts.merge(event, 1, Integer::sum);
                active.add(event);
            }
        }

        Snapshot snapshot() {
            synchronized (monitor) {
                return new Snapshot(active, counts);
            }
        }
    }

    public static void main(String[] args) throws Exception {
        SharedState state = new SharedState();
        Snapshot initial = state.snapshot();

        ExecutorService pool = Executors.newFixedThreadPool(4);
        try {
            List<Future<?>> tasks = new ArrayList<>();
            for (int worker = 0; worker < 4; worker++) {
                Event event = worker % 2 == 0 ? Event.ALPHA : Event.BETA;
                tasks.add(pool.submit(() -> {
                    for (int i = 0; i < 1000; i++) {
                        state.mark(event);
                    }
                }));
            }
            for (Future<?> task : tasks) {
                task.get();
            }
        } finally {
            pool.shutdown();
        }

        Snapshot completed = state.snapshot();
        System.out.println("initial active=" + initial.active());
        System.out.println("initial counts=" + initial.counts());
        System.out.println("completed active=" + completed.active());
        System.out.println("completed counts=" + completed.counts());

        int total = completed.counts().values().stream()
                .mapToInt(Integer::intValue).sum();
        System.out.println("completed total=" + total);

        state.mark(Event.ALPHA);
        System.out.println("saved snapshot alpha="
                + completed.counts().get(Event.ALPHA));
        System.out.println("current alpha="
                + state.snapshot().counts().get(Event.ALPHA));

        try {
            completed.active().clear();
        } catch (UnsupportedOperationException expected) {
            System.out.println("snapshot mutation=rejected");
        }
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -Xlint:all -Werror SharedEnumCollectionsDemo.java
java SharedEnumCollectionsDemo
```

Stdout:

```text
initial active=[]
initial counts={}
completed active=[ALPHA, BETA]
completed counts={ALPHA=2000, BETA=2000}
completed total=4000
saved snapshot alpha=2000
current alpha=2001
snapshot mutation=rejected
```

Bốn tác vụ cùng cập nhật một `SharedState`; mỗi tác vụ ghi nhận 1000 lần. Hai tác vụ dùng `ALPHA`, hai tác vụ dùng `BETA`, nên sau khi chờ mọi `Future` hoàn tất, tổng xác định là 4000.

Trong `mark`, cập nhật số đếm và tập đang hoạt động dùng cùng monitor. `snapshot` cũng dùng monitor đó, nên không sao chép nguồn ở giữa hai bước cập nhật ấy. Constructor ảnh chụp được gọi trong vùng khóa, do đó mọi lượt đọc nguồn để sao chép vẫn được bảo vệ.

`initial` không đổi dù nhiều luồng đã cập nhật trạng thái. `completed` cũng không đổi sau một lần cập nhật mới; nó không phải view sống của state. Những wrapper không cho sửa bao các bản sao riêng và giữ thứ tự duyệt theo enum của các cấu trúc nền trong ví dụ.

Chương trình chờ kết quả tác vụ trước khi in; nó không dùng `Thread.sleep` để đoán rằng các luồng chắc đã xong. Kết quả đúng không phụ thuộc một thứ tự lịch chạy cụ thể giữa bốn tác vụ.

## 6. Synchronized wrapper: dùng đúng đối tượng khóa

Nếu chỉ cần chia sẻ một cấu trúc tương đối độc lập, có thể dùng wrapper chuẩn:

```java
Set<Event> active = Collections.synchronizedSet(EnumSet.noneOf(Event.class));
Map<Event, Integer> counts =
        Collections.synchronizedMap(new EnumMap<>(Event.class));
```

Các biến này đặt trong một phạm vi phù hợp và cần import `Set`, `Map`, `Collections` cùng các lớp enum collection. Mọi truy cập vào collection nền phải đi qua wrapper; đừng giữ một biến khác để sửa trực tiếp đối tượng nền.

### Duyệt phải giữ khóa của wrapper suốt lần duyệt

```java
synchronized (active) {
    for (Event event : active) {
        System.out.println(event);
    }
}

synchronized (counts) {
    for (Map.Entry<Event, Integer> entry : counts.entrySet()) {
        System.out.println(entry.getKey() + "=" + entry.getValue());
    }
}
```

Với map, khóa trên `counts`, không khóa tùy ý trên `counts.keySet()` hoặc `entrySet()`. Yêu cầu khóa cũng áp dụng khi duyệt qua iterator, spliterator hoặc stream theo hợp đồng wrapper.

Xem [Collections.synchronizedSet](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Collections.html#synchronizedSet(java.util.Set)) và [Collections.synchronizedMap](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Collections.html#synchronizedMap(java.util.Map)).

### Chuỗi thao tác cần một vùng bảo vệ chung

Nếu cần `get` rồi tính rồi `put`, giữ khóa của wrapper qua toàn bộ chuỗi. Chỉ vì từng lời gọi riêng được đồng bộ hóa không có nghĩa một chuỗi nhiều lời gọi đã tự trở thành một giao dịch.

Hai wrapper cho set và map thường có hai khóa riêng. Chúng không tự giữ quan hệ giữa hai cấu trúc như chương trình ở mục 5. Khi dữ liệu liên quan cần cập nhật/đọc cùng lúc, lớp đóng gói với một khóa chung thường làm hợp đồng rõ hơn.

Nếu dùng nhiều khóa, cần một thứ tự lấy khóa nhất quán để tránh các luồng chờ nhau theo vòng. Không thêm khóa một cách rời rạc ở từng nơi gọi rồi kỳ vọng mọi đoạn mã tự phối hợp.

## 7. Trường hợp đọc nhiều: công bố các phiên bản bất biến

Với dữ liệu cấu hình đọc nhiều và cập nhật ít, một cách khác là tạo một phiên bản độc lập rồi công bố tham chiếu tới phiên bản đó qua cơ chế có quan hệ bộ nhớ phù hợp, chẳng hạn `volatile` hoặc `AtomicReference`.

Điều kiện cốt lõi là **không tiếp tục sửa phiên bản đã công bố**. Việc ghi một tham chiếu vào `volatile` không biến các lệnh `put`/`add` sau đó trên chính đối tượng thành an toàn luồng.

Nếu chỉ có một bên ghi đã được quản lý, thay cả tham chiếu tới ảnh chụp có thể phù hợp. Nếu nhiều bên ghi đều đọc phiên bản cũ rồi tạo phiên bản mới, chỉ dùng phép gán có thể làm mất một cập nhật; cần khóa bên ghi hoặc cơ chế cập nhật nguyên tử phù hợp.

Ví dụ đoạn thành viên quản lý riêng một tập Event bằng `AtomicReference`, cần import tương ứng:

```java
private final AtomicReference<Set<Event>> current =
        new AtomicReference<>(
                Collections.unmodifiableSet(EnumSet.noneOf(Event.class)));

void enable(Event event) {
    current.updateAndGet(previous -> {
        EnumSet<Event> next = EnumSet.noneOf(Event.class);
        next.addAll(previous);
        next.add(event);
        return Collections.unmodifiableSet(next);
    });
}

Set<Event> enabledSnapshot() {
    return current.get();
}
```

Mỗi lần cập nhật tạo một tập mới, không sửa `previous`. `updateAndGet` có thể chạy lại hàm cập nhật khi có cạnh tranh, nên hàm đó không được chứa tác dụng phụ bên ngoài như gửi thông điệp hoặc tăng một bộ đếm khác.

Đối tượng `AtomicReference` bảo vệ việc công bố/cập nhật tham chiếu theo hợp đồng của nó, không tự khóa mọi nội dung bên trong. Nếu cần ảnh chụp set và map nhất quán với nhau, đặt cả hai vào cùng một giá trị ảnh chụp rồi cập nhật giá trị đó, thay vì dùng hai tham chiếu độc lập.

Xem [AtomicReference](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/atomic/AtomicReference.html). Sao chép mỗi lần có chi phí; không chọn mô hình này chỉ vì nó tránh khóa phía đọc.

## 8. Khi cần cấu trúc đồng thời khác

Có thể dùng enum làm khóa của một `ConcurrentHashMap` hoặc làm phần tử của tập được tạo bằng `ConcurrentHashMap.newKeySet()`. Đây là lựa chọn khác về hợp đồng cập nhật và hiệu năng, không phải một `EnumMap`/`EnumSet` tự trở nên đồng thời.

Những đánh đổi cần xem xét gồm thứ tự duyệt không còn là bảo đảm thứ tự enum như hai cấu trúc chuyên dụng, chính sách null và mức nhất quán của phép quan sát nhiều khóa.

Một cấu trúc hỗ trợ cập nhật an toàn từng khóa cũng không tự làm một nhóm cập nhật qua nhiều khóa hoặc nhiều collection trở thành một ảnh chụp/giao dịch thống nhất. Xem hợp đồng [ConcurrentHashMap](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html).

## 9. Các lỗi nên loại ngay trong thiết kế

| Cách làm | Vì sao chưa đủ? |
| --- | --- |
| Chỉ khai báo collection là final | Chỉ ngăn gán lại trường; nội dung vẫn có thể bị sửa |
| Chỉ khóa khi ghi | Bên đọc vẫn cần tuân theo giao thức nhìn thấy dữ liệu và tính nhất quán |
| Dùng unmodifiable view của nguồn đang sống | Người giữ nguồn vẫn sửa được; đây không phải bản sao độc lập |
| Dùng volatile cho tham chiếu rồi sửa đối tượng được tham chiếu | Volatile không khóa mọi thao tác bên trong collection |
| Dựa vào việc không có ConcurrentModificationException | Iterator của enum collection không dùng ngoại lệ ấy như một bảo đảm an toàn |
| Trả collection/view đang sống từ getter | Người gọi có thể vượt qua khóa và sửa trạng thái được bảo vệ |
| Sao chép map chứa danh sách rồi coi mọi giá trị đã được cô lập | Bản sao nông vẫn chia sẻ các đối tượng giá trị |

Kiểm thử nhiều luồng nên kiểm tra tổng, tính chất quan hệ giữa dữ liệu và chính sách ảnh chụp, không chỉ kiểm tra rằng chương trình không ném lỗi. Một lần chạy đúng không thay thế được việc chứng minh mọi đường truy cập đều tuân cùng giao thức đồng bộ hóa.

## 10. Tự kiểm tra

1. EnumSet/EnumMap có tự an toàn luồng vì các khóa/phần tử là enum không?
2. Vì sao getter trả một view không cho sửa của collection nền vẫn có thể không phải ảnh chụp ổn định?
3. Khi duyệt keySet của synchronizedMap, cần khóa trên map hay keySet?
4. Vì sao hai synchronized wrapper độc lập chưa đủ để giữ một quan hệ set-map?
5. AtomicReference có làm mọi lệnh sửa collection được nó giữ trở thành nguyên tử không?

Đáp án:

1. Không. Phải có giao thức truy cập khi các luồng chia sẻ với sửa đổi.
2. View còn dựa trên nguồn mà bên khác có thể sửa; cần sao chép và công bố đúng để có ảnh chụp độc lập.
3. Khóa trên wrapper map theo hợp đồng, giữ khóa trong toàn bộ lần duyệt.
4. Chúng có vùng đồng bộ riêng, không tự tạo một vùng nguyên tử bao dữ liệu của cả hai.
5. Không. Nó cung cấp thao tác trên tham chiếu; phiên bản đã công bố cần được quản lý theo mô hình bất biến hoặc đồng bộ hóa riêng.

Hãy chọn rõ một mô hình sở hữu và công bố dữ liệu: cục bộ một luồng, trạng thái chung dưới khóa, hoặc các phiên bản ảnh chụp không bị sửa sau khi công bố. Sau đó giữ mọi đường đọc, ghi và đưa dữ liệu ra ngoài tuân theo mô hình ấy.
