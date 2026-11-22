# Giới hạn của ảnh chụp dữ liệu chỉ đọc khi nguồn đang bị luồng khác sửa

*Chủ đề Java 10 — Thiết kế dữ liệu chỉ đọc. Bài học giải thích giới hạn của `List.copyOf`, `Set.copyOf`, `Map.copyOf` và các cách công bố dữ liệu cho nhiều luồng trong Java 17+ và các JDK hiện đại. Trọng tâm là tính nhất quán của snapshot, không phải một bài nhập môn tổng quát về concurrency.*

## 1. Kết luận cần nắm

`List.copyOf(source)`, `Set.copyOf(source)` và `Map.copyOf(source)` rất phù hợp để **xuất bản một collection không thể sửa**. Với đầu vào ổn định và hợp lệ, kết quả không phản ánh việc thêm, xóa hoặc thay các phần tử/entry sau đó của collection nguồn. Tuy nhiên:

> **Không thể suy ra “ảnh chụp nguyên tử tại một thời điểm” chỉ từ việc gọi `copyOf` trên một nguồn mutable đang bị luồng khác sửa.**

Đặc biệt:

- “Không thể sửa” (*unmodifiable*) có nghĩa người nhận không thể dùng các mutator của collection kết quả để thay đổi cấu trúc hoặc ánh xạ phần tử của nó.
- “Ảnh chụp ổn định” (*snapshot*) có nghĩa kết quả đã tạo thành công không phản ánh các thay đổi cấu trúc/thay phần tử của collection nguồn xảy ra **sau đó**.
- “Ảnh chụp nhất quán” (*consistent snapshot*) có nghĩa các phần dữ liệu trong kết quả tương ứng với một trạng thái hợp lệ được xác định theo mô hình đồng bộ của ứng dụng.
- “Ảnh chụp nguyên tử” (*atomic snapshot*) đòi hỏi thao tác lấy dữ liệu có một điểm hiệu lực logic được bảo đảm tương ứng; việc dùng một copy factory thông thường **không tự tạo ra** bảo đảm này khi writers đang sửa nguồn.
- “Công bố an toàn” (*safe publication*) là việc đưa tham chiếu của object đã khởi tạo hoàn chỉnh tới các luồng đọc thông qua cơ chế có bảo đảm bộ nhớ phù hợp, chẳng hạn `AtomicReference` hoặc trường `volatile`.

Bốn ý cuối **không đồng nghĩa**. Một collection có thể unmodifiable nhưng **đã chứa dữ liệu thiếu nhất quán do quá trình đọc nguồn xảy ra giữa nhiều lần sửa**. Sau khi copy xong, tính unmodifiable không thể sửa lại dữ liệu sai đã được quan sát.

## 2. Ví dụ tình huống rủi ro

Giả sử một dịch vụ lưu danh sách mã cấu hình:

~~~java
var source = new ArrayList<>(List.of("A", "B"));

// Luồng đọc:
var snapshot = List.copyOf(source);

// Luồng ghi, có thể chạy đồng thời:
source.add("C");
~~~

Nếu hai luồng chạy **không đồng bộ**, ta không được khẳng định snapshot chắc chắn là `[A, B]` hoặc `[A, B, C]` trong mọi trường hợp. Việc sao chép có thể đụng vào trạng thái đang bị thay đổi của một `ArrayList` không được thiết kế cho truy cập vừa đọc vừa ghi không đồng bộ.

Tùy collection, thời điểm và cách cài đặt, ứng dụng có thể thấy dữ liệu không nhất quán, ngoại lệ như `ConcurrentModificationException` hoặc các hành vi quan sát không đáng tin khác. **Không được viết test chỉ dựa vào hy vọng “chạy trùng thời điểm sẽ ném đúng một ngoại lệ”.**

Mấu chốt: `List.copyOf` là một API collection. Nó **không tự quản lý giao thức khóa cho mọi mutable collection được truyền vào**.

### Một diễn tiến có thể khiến kết quả khó hiểu

~~~text
Thời điểm      Luồng đọc                       Luồng ghi
T1             Bắt đầu copy source
T2             Quan sát một phần dữ liệu
T3                                              Thay đổi source
T4             Tiếp tục lấy dữ liệu còn lại
T5             Kết thúc hoặc thất bại
~~~

Đây là **sơ đồ rủi ro**, không phải lời cam kết về trình tự nội bộ của implementation. Trình biên dịch/JVM và lớp collection được phép có cách thực hiện khác nhau theo hợp đồng Java. Không phụ thuộc vào việc `copyOf` duyệt bằng iterator, `toArray` hay một kỹ thuật nội bộ cụ thể.

Nếu nghiệp vụ yêu cầu toàn bộ cấu hình phải đồng bộ với nhau, cần bảo đảm rằng quá trình **chụp dữ liệu được phối hợp với writers**.

## 3. `copyOf` bảo đảm điều gì — và không bảo đảm điều gì?

### 3.1. Khi nguồn không bị sửa đồng thời

~~~java
var source = new ArrayList<>(List.of("A", "B"));
var published = List.copyOf(source);
source.add("C");

// published vẫn chứa A và B.
~~~

Kết quả không phản ánh thay đổi cấu trúc `source.add("C")` xảy ra sau khi `copyOf` hoàn tất. Đây là một use case chuẩn.

Tương tự:

~~~java
var rawFlags = new HashSet<>(Set.of("READ"));
var immutableFlags = Set.copyOf(rawFlags);
rawFlags.add("WRITE");
// immutableFlags không tự thêm WRITE.
~~~

~~~java
var rawConfig = new HashMap<>(Map.of("min", 1));
var immutableConfig = Map.copyOf(rawConfig);
rawConfig.put("max", 10);
// immutableConfig không tự thêm max.
~~~

`List.copyOf`, `Set.copyOf`, `Map.copyOf` đều từ chối dữ liệu `null` không hợp lệ theo API tương ứng. Nhưng kiểm tra null **không phải một cơ chế đồng bộ**: nếu nguồn đang bị sửa đồng thời, việc phát sinh hoặc không phát sinh ngoại lệ null không chứng minh snapshot nguyên tử.

### 3.2. Câu khẳng định cần tránh

Không đúng:

> “Vì `copyOf` cho unmodifiable collection nên nó thread-safe và luôn phản ánh chính xác một thời điểm khi bất kỳ thread nào đang cập nhật source.”

Đúng hơn:

> “Sau khi được tạo thành công từ dữ liệu đã được bảo vệ phù hợp, bản copy là một cấu trúc collection không thể sửa. Muốn snapshot nhất quán khi nguồn mutable được chia sẻ giữa các luồng, phải phối hợp việc ghi và sao chép hoặc sử dụng mô hình trạng thái bất biến/công bố snapshot khác.”

Không phải mọi collection đang chạy đồng thời đều nguy hiểm theo cùng một cách: các implementation concurrent có hợp đồng khác nhau. Nhưng “thread-safe collection” cũng **chưa chắc** cung cấp snapshot giao dịch của nhiều phần tử hoặc nhiều cấu trúc dữ liệu.

### 3.3. Danh tính đối tượng không phải bảo đảm

Nếu nguồn đã là một unmodifiable collection phù hợp, `copyOf` **có thể tái sử dụng đối tượng nguồn** thay vì cấp phát một đối tượng mới. Do đó không được dùng `==` hay số lần tạo object để chứng minh có snapshot.

Kiểm tra giá trị, hành vi không sửa được và **cách snapshot được lấy trong điều kiện đồng thời** mới là điều quan trọng.

## 4. Phân biệt bốn dạng dữ liệu thường gặp

| Nguồn/đầu ra | Có thể sửa qua tham chiếu đã xuất bản? | Quan sát thay đổi nguồn về sau? | Có tự bảo đảm snapshot nguyên tử khi nguồn đang đổi? |
| --- | --- | --- | --- |
| `List.copyOf(source)` từ nguồn ổn định | Không | Không với sửa cấu trúc/thay phần tử | Không cần tranh chấp nếu nguồn thực sự ổn định |
| `List.copyOf(source)` trong lúc source bị sửa không đồng bộ | Kết quả tạo thành công không sửa được | Không với sửa cấu trúc sau khi hoàn tất | **Không được bảo đảm** |
| `Collections.unmodifiableList(source)` | Không qua view | **Có** vì đây là read-only view | **Không**; view không đóng băng nguồn |
| `Collections.synchronizedList(source)` | Có nếu dùng API wrapper | Có, vì wrapper chính là cách truy cập source | Có khóa cho từng operation theo hợp đồng wrapper; **không tự khóa cả một chuỗi nhiều thao tác** |
| `CopyOnWriteArrayList` | Có; các phương thức ghi tạo phiên bản backing mới | Có khi truy vấn list hiện tại; iterator cũ có snapshot riêng | Iterator có snapshot theo hợp đồng; không tự bảo đảm một giao dịch trải trên nhiều collection |
| `ConcurrentHashMap` | Có | Có | Iterator/view có thể quan sát cập nhật đồng thời theo chính sách *weakly consistent*; **không phải snapshot nguyên tử toàn map** |
| `AtomicReference<ImmutableState>` | Đổi tham chiếu toàn trạng thái qua API atomic | Reader mới có thể nhận phiên bản mới | Đọc một tham chiếu cho **toàn bộ immutable state đã chuẩn bị** có thể cho snapshot nhất quán của phiên bản đó, nếu lúc xây dựng trạng thái đã được bảo vệ đúng |

“Read-only” chỉ nói về khả năng sửa qua một giao diện; “snapshot nguyên tử” nói về **tính nhất quán tại ranh giới đọc nhiều giá trị**.

## 5. Cách 1 — Cùng một khóa cho mọi writer và thao tác snapshot

Đây là giải pháp dễ giải thích nếu trạng thái dùng một mutable `ArrayList`/`HashMap` được quản lý trong cùng một component.

~~~java
private static final Object LOCK = new Object();
private static final List<String> SHARED = new ArrayList<>();

static void addItem(String value) {
    synchronized (LOCK) {
        SHARED.add(value);
    }
}

static List<String> snapshot() {
    synchronized (LOCK) {
        return List.copyOf(SHARED);
    }
}
~~~

Đây là các thành viên minh họa cần đặt trong cùng một lớp, import `List` và `ArrayList`.

**Điều kiện để lời giải có tác dụng:** **tất cả** đường sửa nguồn (thêm, xóa, thay phần tử, clear, cập nhật một nhóm giá trị, v.v.) đều phải tuân thủ **đúng cùng một khóa**. Nếu có một writer sửa `SHARED` ngoài `synchronized(LOCK)`, ta đã làm mất bảo đảm cần có.

Khi thread đọc giữ `LOCK`, không writer nào cùng khóa được phép sửa nguồn trong lúc `List.copyOf` lấy dữ liệu. Snapshot thu được là một trạng thái **ổn định theo giao thức đồng bộ của component**.

### 5.1. Vì sao nên giữ thời gian trong critical section ngắn?

~~~java
List<String> stable;
synchronized (LOCK) {
    stable = List.copyOf(SHARED);
}
// Parse, format, gửi mạng hoặc xử lý dài ở NGOÀI lock nếu có thể.
process(stable);
~~~

Chỉ khóa việc cần lấy dữ liệu một cách nhất quán. Không giữ khóa trong thời gian gọi API mạng, xử lý chuỗi dài hoặc làm I/O không liên quan; nó sẽ chặn các writer chờ khóa. Bản copy có thể tốn thời gian `O(n)` cho một list lớn, nên đánh đổi giữa độ lớn dữ liệu và thời gian writer chờ phải được đánh giá.

**Không copy rồi mới khóa:**

~~~java
// Sai mục tiêu: việc đọc nguồn đã xảy ra trước khi bảo vệ bằng khóa.
var candidate = List.copyOf(SHARED);
synchronized (LOCK) {
    return candidate;
}
~~~

Khóa trong ví dụ này đến quá muộn. Nếu cần snapshot nhất quán, **thao tác lấy nội dung từ nguồn** phải được bảo vệ.

### 5.2. Nếu dùng nhiều collection liên quan

Giả sử một cấu hình có `products` và `prices`, và chúng phải có phiên bản nhất quán.

~~~java
synchronized (LOCK) {
    var productsCopy = List.copyOf(products);
    var pricesCopy = Map.copyOf(prices);
    // Tạo một object snapshot chứa cả hai.
}
~~~

Nếu writer cập nhật `products` và `prices` cùng một khóa, reader có thể lấy **cả hai bản copy trong cùng critical section**. Ngược lại, copy `products` rồi nhả khóa, copy `prices` sau có thể thu được hai phiên bản không tương ứng nhau.

Với các nguồn nằm trong database hoặc các dịch vụ riêng biệt, một Java monitor không thể thay thế **transaction/consistent read** ở tầng lưu trữ. Chọn chiến lược consistency phù hợp với ranh giới của hệ thống.

## 6. Chương trình hoàn chỉnh Java 17+: snapshot với khóa, công bố mới và COW iterator

Chương trình sau được thiết kế để có **đầu ra xác định**, không tạo race ngẫu nhiên rồi xem nó có ném `ConcurrentModificationException` hay không. Nó minh họa:

1. `List.copyOf` khi được bảo vệ bằng chung một lock ở cả writer và reader.
2. `Collections.unmodifiableList` chỉ là view, nên phản ánh nguồn sau khi writer đổi.
3. `AtomicReference` công bố một tham chiếu tới unmodifiable snapshot mới.
4. Iterator của `CopyOnWriteArrayList` được tạo trước một lần thêm phần tử giữ snapshot tại thời điểm iterator được tạo.
5. `List.copyOf` là sao chép **nông** đối với các object phần tử.

~~~java
// File: ConcurrentReadOnlySnapshotDemo.java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicReference;

public class ConcurrentReadOnlySnapshotDemo {
    private static final Object LOCK = new Object();
    private static final ArrayList<String> SHARED =
            new ArrayList<>(List.of("A", "B"));

    static List<String> lockedSnapshot() {
        synchronized (LOCK) {
            return List.copyOf(SHARED);
        }
    }

    static void changeSource() {
        synchronized (LOCK) {
            SHARED.add("C");
        }
    }

    static final class MutableBox {
        String text;
        MutableBox(String text) {
            this.text = text;
        }
    }

    public static void main(String[] args) throws InterruptedException {
        var oldSnapshot = lockedSnapshot();
        var liveView = Collections.unmodifiableList(SHARED);

        var gate = new CountDownLatch(1);
        var writer = new Thread(() -> {
            try {
                gate.await();
            } catch (InterruptedException interrupted) {
                Thread.currentThread().interrupt();
                return;
            }
            changeSource();
        });
        writer.start();
        gate.countDown();
        writer.join();

        System.out.println("old snapshot = " + oldSnapshot);
        System.out.println("new snapshot = " + lockedSnapshot());
        System.out.println("read-only view = " + liveView);

        var published = new AtomicReference<>(
                List.copyOf(List.of("READ")));
        var heldSnapshot = published.get();
        published.updateAndGet(previous -> {
            var copy = new ArrayList<>(previous);
            copy.add("WRITE");
            return List.copyOf(copy);
        });

        System.out.println("held published = " + heldSnapshot);
        System.out.println("current published = " + published.get());

        var cow = new CopyOnWriteArrayList<>(List.of("X", "Y"));
        var iter = cow.iterator();
        cow.add("Z");
        var seen = new ArrayList<String>();
        iter.forEachRemaining(seen::add);
        System.out.println("COW iterator snapshot = " + seen);
        System.out.println("COW latest = " + cow);

        var box = new MutableBox("before");
        var shallow = List.copyOf(List.of(box));
        box.text = "after";
        System.out.println("shallow element = " + shallow.get(0).text);
    }
}
~~~

Chạy với JDK 17+:

~~~bash
javac --release 17 ConcurrentReadOnlySnapshotDemo.java
java ConcurrentReadOnlySnapshotDemo
~~~

Stdout đã kiểm chứng:

~~~text
old snapshot = [A, B]
new snapshot = [A, B, C]
read-only view = [A, B, C]
held published = [READ]
current published = [READ, WRITE]
COW iterator snapshot = [X, Y]
COW latest = [X, Y, Z]
shallow element = after
~~~

### Giải thích

- `oldSnapshot` được tạo trước khi writer thêm `C`; nó không thay đổi khi writer xong. Sau khi `writer.join()`, `lockedSnapshot()` lấy phiên bản mới là `[A, B, C]`.
- `CountDownLatch` điều phối thời điểm writer bắt đầu; `join` đảm bảo main chỉ in sau khi writer hoàn tất. **Tính nhất quán của snapshot do lock chung tạo ra**, không phải do `join` một mình.
- `liveView` được tạo từ `Collections.unmodifiableList(SHARED)` nhưng không phải copy: sau khi writer đổi nguồn và main đợi `join`, view hiển thị `C`.
- `published.get()` trả một tham chiếu tới danh sách không thể sửa `[READ]` ở thời điểm đó. `updateAndGet` tạo **một danh sách mới** `[READ, WRITE]`, rồi cập nhật tham chiếu; `heldSnapshot` vẫn chứa `[READ]`.
- Iterator `CopyOnWriteArrayList` được tạo khi list là `[X, Y]`. Sau `cow.add("Z")`, iterator cũ vẫn duyệt `[X, Y]`, nhưng truy cập list hiện tại thấy `[X, Y, Z]`.
- `MutableBox` cho thấy collection unmodifiable không đồng nghĩa các object thành phần immutable. Thay đổi field `box.text` ảnh hưởng giá trị đọc qua `shallow`.

Đây là chương trình minh họa **đúng mẫu phối hợp**; nó cố ý không thực hiện truy cập sai đồng bộ để tạo một lỗi chạy ngẫu nhiên.

## 7. Vì sao một read-only view không đủ bảo vệ dữ liệu đang đổi?

Một wrapper:

~~~java
var source = new ArrayList<>(List.of("A", "B"));
var readOnlyView = Collections.unmodifiableList(source);
~~~

ngăn được:

~~~java
// readOnlyView.add("C");    // UnsupportedOperationException
// readOnlyView.remove("A"); // UnsupportedOperationException
~~~

Nhưng **không ngăn**:

~~~java
source.add("C");
// readOnlyView giờ quan sát danh sách có C.
~~~

Trong môi trường nhiều luồng, việc chỉ giao wrapper không thể sửa cho consumer **không tự đồng bộ** quá trình một writer sửa backing list và một reader duyệt wrapper. Nếu backing list là `ArrayList` mutable thường, vẫn cần có giao thức đồng bộ khi truy cập đồng thời.

Một wrapper unmodifiable là **hợp đồng cấm sửa qua interface này**, không phải bản sao, không phải mutex và không phải isolation.

Nếu muốn tạo một bản sao ổn định, có thể dùng:

~~~java
List<String> snapshot;
synchronized (LOCK) {
    snapshot = List.copyOf(source);
}
~~~

với điều kiện **mọi writer** cũng khóa `LOCK`. Không nên giữ tham chiếu mutable tới source để tạo đường bypass ngoài giao thức.

## 8. `Collections.synchronizedList`: đồng bộ từng lời gọi chưa đủ cho mọi thao tác phức hợp

Có thể dùng:

~~~java
List<String> shared =
        Collections.synchronizedList(new ArrayList<>());
~~~

Wrapper này cung cấp đồng bộ cho các phương thức của list thông qua monitor theo hợp đồng. Tuy vậy, khi thao tác cần duyệt một chuỗi phần tử hoặc giữ nhiều thao tác thuộc cùng một giao dịch logic, cần **đồng bộ bên ngoài theo cùng monitor**:

~~~java
List<String> snapshot;
synchronized (shared) {
    snapshot = List.copyOf(shared);
}
~~~

Khi writer chỉ sửa thông qua `shared.add(...)`, `shared.remove(...)`, ... hoặc cùng khóa `synchronized(shared)`, thì việc lấy toàn bộ snapshot trong critical section được bảo vệ.

Nếu bạn vẫn giữ biến tham chiếu tới `ArrayList` nền và viết trực tiếp qua nó, không qua wrapper/khóa chung, cơ chế đồng bộ của `synchronizedList` **bị bypass**.

### Duyệt list cũng phải bảo vệ theo hợp đồng

Với `Collections.synchronizedList`, khi dùng iterator, stream hoặc spliterator, tài liệu API yêu cầu có đồng bộ thủ công khi duyệt:

~~~java
synchronized (shared) {
    for (var item : shared) {
        process(item);
    }
}
~~~

Mã minh họa giả định `process` có sẵn. Đối với xử lý dài, có thể **copy dưới khóa** rồi lặp trên bản copy ở ngoài khóa:

~~~java
List<String> stable;
synchronized (shared) {
    stable = List.copyOf(shared);
}
for (var item : stable) {
    process(item);
}
~~~

Điểm lợi: writer không bị chặn suốt cả thời gian `process`. Điểm đổi lại: reader xử lý **một phiên bản cũ** nếu writer cập nhật sau khi copy, và copy tốn thời gian/bộ nhớ. Đây là sự lựa chọn về mô hình dữ liệu, không phải lỗi của collection.

## 9. `ConcurrentHashMap` và các collection concurrent: thread-safe không luôn đồng nghĩa atomic snapshot

`ConcurrentHashMap` hỗ trợ truy cập và cập nhật đồng thời, nhưng iterator/spliterator của những view như `keySet()` được mô tả là **weakly consistent**: chúng có thể phản ánh một số thay đổi xảy ra trong khi duyệt và không cung cấp snapshot giao dịch của toàn bộ map.

~~~java
var current = new ConcurrentHashMap<String, Integer>();
current.put("A", 1);
current.put("B", 2);

var keys = current.keySet(); // View trên map đang thay đổi.
var copiedKeys = Set.copyOf(keys);
~~~

Đây là đoạn minh họa với import `ConcurrentHashMap`, `Set`. Nếu writers thay đổi map trong lúc copy, **không được khẳng định** `copiedKeys` đại diện chính xác cho một phiên bản nguyên tử của toàn map.

Sau khi kết quả `copiedKeys` được tạo thành công, nó không thể sửa và không tự thêm/xóa phần tử theo các cập nhật **xảy ra sau** ở map. Nhưng trạng thái **đã được thu thập trước lúc copy kết thúc** vẫn phụ thuộc vào chính sách quan sát của nguồn.

Tương tự, `Map.copyOf(concurrentMap)` cho kết quả unmodifiable nếu thành công, nhưng không trở thành một giao dịch đọc nguyên tử chỉ nhờ tên `copyOf`.

### Ví dụ tình huống hai giá trị liên quan

Một map lưu `"used"` và `"limit"`. Writers cập nhật cả hai theo một quy tắc. Nếu reader sao chép trong khi writers đang thực hiện các cập nhật riêng lẻ, reader có thể nhìn thấy một cặp giá trị không tương ứng với **một trạng thái nghiệp vụ hoàn chỉnh**, dù từng phép `put` riêng đã thread-safe.

Nếu cần **hai giá trị cập nhật đồng thời như một đơn vị**, có thể lưu chúng trong một object immutable và thay thế cả object qua một tham chiếu atomic, hoặc dùng lock/transaction có chung phạm vi. `ConcurrentHashMap` không tự biến chuỗi nhiều cập nhật thành một giao dịch.

### Không dùng sự vắng mặt của `ConcurrentModificationException` làm bằng chứng

Một iterator concurrent có thể được thiết kế **không fail-fast**; điều đó không có nghĩa nó đã đọc một ảnh chụp nhất quán. Ngược lại, iterator của một collection thường đôi lúc có thể không phát hiện sửa đổi đồng thời; điều đó cũng không chứng minh thao tác an toàn.

**Đúng hợp đồng consistency quan trọng hơn việc có/không thấy exception trong một lần chạy.**

## 10. `CopyOnWriteArrayList`: snapshot iterator, phù hợp workload đọc nhiều/ghi ít

`CopyOnWriteArrayList` áp dụng chiến lược tạo backing array mới khi có các thao tác sửa cấu trúc/phần tử. Iterator của nó có **snapshot cố định của array tại thời điểm iterator được tạo** và không phản ánh các thay đổi về sau.

~~~java
var cow = new CopyOnWriteArrayList<>(List.of("A", "B"));
var iterator = cow.iterator();

cow.add("C");

// iterator vẫn duyệt A, B.
// cow hiện tại chứa A, B, C.
~~~

Đây là một **bảo đảm cụ thể của iterator `CopyOnWriteArrayList`**, không phải bảo đảm chung cho mọi iterator của mọi collection.

Hệ quả:

- Đọc/duyệt lặp đi lặp lại trong khi ghi hiếm xảy ra có thể thuận lợi.
- Mỗi lần ghi có chi phí copy backing array, nên dữ liệu lớn và cập nhật liên tục có thể tốn CPU/bộ nhớ.
- Iterator snapshot không hỗ trợ `remove`/`set`/`add`.
- Những phiên bản iterator được tạo ở thời điểm khác nhau có thể thấy dữ liệu khác nhau; muốn một lần xử lý nhất quán, dùng **một iterator/snapshot được chốt** trong phạm vi xử lý đó.
- Snapshot iterator không bảo đảm các **đối tượng phần tử mutable** không bị thay đổi, và không tạo atomic snapshot của một tập hợp gồm nhiều nguồn dữ liệu khác nhau.

Khi yêu cầu là một danh sách không thể sửa gửi ra khỏi component, có thể vẫn dùng `List.copyOf` theo một **ràng buộc trạng thái rõ**. Không cần thay mọi `ArrayList` thành `CopyOnWriteArrayList`: hãy đo mức độ đọc/ghi và yêu cầu consistency trước.

## 11. Cách 2 — Xây dựng trạng thái immutable rồi công bố một tham chiếu mới

Thay vì chia sẻ một collection mutable cho mọi thread, một mô hình khác là:

1. Chuẩn bị một object trạng thái mới.
2. Trong object đó, tạo unmodifiable copy cho các collection.
3. Chỉ sau khi hoàn tất, **công bố một tham chiếu** tới trạng thái mới bằng một cơ chế an toàn.
4. Reader đọc tham chiếu **một lần** rồi dùng trạng thái đó suốt một hoạt động.

Ví dụ một cấu hình:

~~~java
record AppSnapshot(
        long revision,
        List<String> productCodes,
        Map<String, Integer> limits
) {
    AppSnapshot {
        productCodes = List.copyOf(productCodes);
        limits = Map.copyOf(limits);
    }
}
~~~

Đây là đoạn minh họa Java 17+, cần import `java.util.List` và `java.util.Map`. Compact constructor của `record` tạo unmodifiable copy từ các tham số. **Điều kiện**: hai tham số phải đại diện cho dữ liệu **nhất quán ngay lúc xây dựng**; nếu chúng được lấy từ hai mutable collection đang đổi không có khóa, bản thân constructor không thể giải quyết việc chụp hai nguồn nguyên tử.

Giả sử `AppSnapshot` đã xây dựng đúng:

~~~java
var published = new AtomicReference<>(
    new AppSnapshot(1, List.of("A"), Map.of("max", 10))
);

// Khi chuẩn bị xong phiên bản mới:
var newer = new AppSnapshot(
    2, List.of("A", "B"), Map.of("max", 20));

published.set(newer);

// Trong một request:
var snapshot = published.get();
var revision = snapshot.revision();
var products = snapshot.productCodes();
var limit = snapshot.limits().get("max");
~~~

Lợi ích: reader dùng một object `snapshot` đã chốt, thay vì gọi `published.get()` lại giữa các dòng có thể dẫn tới trộn `revision` từ phiên bản cũ với `limits` từ phiên bản mới.

**Không làm như sau khi cần tính nhất quán liên trường:**

~~~java
var revision = published.get().revision();
var products = published.get().productCodes();
var limits = published.get().limits();
~~~

Mỗi lần `get()` có thể thấy tham chiếu phiên bản khác, vì một writer có thể công bố snapshot mới giữa các lần đọc.

### 11.1. `AtomicReference.updateAndGet` và thao tác cập nhật

`AtomicReference.updateAndGet` có thể dùng để tạo trạng thái kế tiếp bằng hàm chuyển đổi:

~~~java
published.updateAndGet(previous -> {
    var newProducts = new ArrayList<>(previous.productCodes());
    newProducts.add("C");
    return new AppSnapshot(
        previous.revision() + 1,
        newProducts,
        previous.limits()
    );
});
~~~

Hàm cập nhật nên **không có tác dụng phụ ngoài**: khi có tranh chấp giữa nhiều writers, `updateAndGet` có thể phải gọi lại hàm để thử CAS lần nữa. Không gửi email, ghi DB hay trừ tiền ngay bên trong lambda cập nhật chỉ vì nghĩ nó chỉ chạy một lần.

Nếu một thay đổi phải đồng bộ với database, queue, cache khác hoặc transaction ngoài bộ nhớ, `AtomicReference` chỉ giải quyết phần **tham chiếu trong tiến trình Java**, không giải quyết giao dịch phân tán.

### 11.2. `volatile` cũng có thể công bố tham chiếu mới

Nếu chiến lược cập nhật đủ đơn giản, một trường:

~~~java
private volatile AppSnapshot currentSnapshot;
~~~

có thể được dùng để công bố một tham chiếu trạng thái mới và cho reader nhận giá trị đúng theo các quy tắc visibility của Java Memory Model. Nhưng bản thân `volatile` **không** biến nhiều thao tác đọc-sửa-ghi thành một giao dịch không mất cập nhật. Nếu có nhiều writers tính `next = f(current)`, dùng cơ chế lock hoặc CAS thích hợp.

**Đừng nhầm:**
- `volatile List<String> current` không làm list bên trong trở thành thread-safe nếu writer vẫn gọi `current.add(...)`.
- `AtomicReference<List<String>>` không tự làm list bên trong immutable; phải **công bố list đã được chốt** và không mutate nó sau đó.
- Một tham chiếu atomic chỉ cho atomicity ở mức tham chiếu đó; không thay thế cơ chế cập nhật nhất quán các hệ thống ngoài tiến trình.

## 12. Tính bất biến nông: snapshot list ổn định nhưng phần tử có thể đổi

Giả sử:

~~~java
var item = new StringBuilder("A");
var snapshot = List.copyOf(List.of(item));
item.append("B");

System.out.println(snapshot.get(0)); // AB
~~~

`snapshot` không thể gọi `add`/`remove`, nhưng phần tử `StringBuilder` là một object mutable được giữ dưới dạng **cùng tham chiếu**. Việc sửa nội dung `item` tác động tới giá trị quan sát qua snapshot.

Trong ứng dụng đa luồng, nếu trường bên trong `item` còn bị sửa không đồng bộ, người đọc có thể gặp **data race ở cấp phần tử** dù danh sách bao ngoài không thể sửa.

Với snapshot cần nhất quán sâu, ưu tiên:

- `String`, enum và các value object bất biến thích hợp.
- Record có thành phần bất biến; nếu record chứa collection mutable, tạo defensive copy trong constructor.
- Sao chép có chủ đích các đối tượng phần tử mutable trước khi xuất bản, dưới cùng chiến lược đồng bộ với nguồn.
- Không trả lại một tham chiếu mutable vốn đang được writer tiếp tục sửa.

Cũng lưu ý `Set.copyOf` với phần tử mutable tham gia `equals`/`hashCode` có thể dẫn đến lỗi lookup nếu hash thay đổi về sau. `Map.copyOf` không bảo đảm value object bất biến. Tính “unmodifiable” chỉ đề cập cấu trúc collection, không bao trùm toàn bộ object graph.

## 13. Tính nhất quán có nhiều cấp độ

Không phải mọi chương trình đều cần snapshot atomic. Hãy phân loại yêu cầu trước khi chọn cách thực hiện.

| Yêu cầu | Ví dụ | Cơ chế thường phù hợp |
| --- | --- | --- |
| Chỉ ngăn caller sửa cấu trúc | Trả mã loại sản phẩm từ dữ liệu đã chuẩn bị ổn định | `List.copyOf`/`Set.copyOf`/`Map.copyOf` |
| Chấp nhận nhìn thấy updates theo thời gian | Read-only view phục vụ quan sát trạng thái | View có hợp đồng và synchronization phù hợp |
| Snapshot của **một** collection mutable được nhiều writer quản lý | Danh sách tham số của component | Cùng lock khi writer sửa và reader copy |
| Duyệt list không bị thay đổi bởi writer sau khi iterator được tạo | Listener registry đọc nhiều/ghi ít | `CopyOnWriteArrayList` hoặc unmodifiable snapshot đã công bố |
| Nhiều dữ liệu phải thuộc cùng phiên bản | Config gồm feature flags + quotas | Capture dưới cùng lock/transaction, lưu immutable aggregate |
| Cập nhật phiên bản trạng thái cho nhiều readers | Runtime config / policy đã được kiểm chứng | `AtomicReference<ImmutableState>` hoặc `volatile` cho công bố |
| Dữ liệu đến từ DB và đòi tính nhất quán giao dịch | Bảng đơn hàng + tồn kho | Database transaction/consistent read, không chỉ Java collection lock |

Chiến lược tốt nhất phụ thuộc workload. Một khóa rõ ràng thường dễ kiểm toán hơn nhiều trick concurrency. `CopyOnWriteArrayList` hợp lý ở danh sách nhỏ, đọc nhiều/ghi hiếm; không hợp lý khi hàng nghìn thao tác ghi mỗi giây trên list lớn. Atomic immutable-state thường giúp readers ít tranh chấp hơn nhưng đổi lại writers phải tạo trạng thái mới và quản lý việc công bố, versioning, invalidation.

## 14. Những lỗi và ngộ nhận phổ biến

| Ngộ nhận | Điều cần hiểu |
| --- | --- |
| “`List.copyOf` luôn chụp một thời điểm nguyên tử dù nguồn đang đổi.” | Không có bảo đảm tổng quát ấy; phải bảo vệ nguồn/capture. |
| “Không có `ConcurrentModificationException` thì snapshot nhất quán.” | Sai. Fail-fast chỉ là cơ chế phát hiện best-effort ở nhiều collection, không phải bằng chứng consistency. |
| “Có `ConcurrentModificationException` thì `copyOf` chắc chắn không thread-safe.” | Ngoại lệ phản ánh việc truy cập không phù hợp hợp đồng; không phải mọi collection concurrent có cùng cách hoạt động. |
| “Unmodifiable view là snapshot.” | `Collections.unmodifiableList` vẫn nhìn thấy backing list thay đổi. |
| “`Collections.synchronizedList` tự khóa mọi vòng for/iterator từ bên ngoài.” | Khi duyệt phải đồng bộ theo hợp đồng wrapper; thao tác nhiều bước cần khóa chung. |
| “`ConcurrentHashMap` cho một ảnh chụp nguyên tử của toàn map.” | Không mặc định; iterator/view weakly consistent. |
| “`CopyOnWriteArrayList` iterator thấy luôn thay đổi mới nhất.” | Iterator cố định snapshot ở thời điểm tạo; cần iterator mới để thấy bản cập nhật sau. |
| “`AtomicReference` làm từng phần tử list thread-safe.” | Nó công bố/thay tham chiếu; list và các phần tử cần đúng hợp đồng riêng. |
| “Đọc `AtomicReference.get()` nhiều lần vẫn luôn là một phiên bản.” | Không; writer có thể cập nhật giữa các lần get. |
| “Giữ khóa khi in/đọc mạng cũng được vì dữ liệu cần nhất quán.” | Thường nên copy ngắn dưới khóa rồi xử lý ngoài khóa để tránh chặn writers. |
| “`copyOf` tạo deep copy.” | Không; phần tử mutable vẫn chia sẻ tham chiếu. |
| “`join()` thay thế synchronization cho mọi lần snapshot.” | `join` chỉ chờ thread hoàn tất và thiết lập quan hệ bộ nhớ tương ứng; không bảo vệ các thao tác đang diễn ra đồng thời với writer khác. |
| “Một snapshot cũ tự động biết trạng thái mới.” | Không; muốn dữ liệu mới phải chụp/publish phiên bản mới. |
| “Record luôn bất biến sâu.” | Không; record chứa mutable components vẫn có thể bị thay đổi nếu không defensive copy. |

## 15. Cách kiểm thử concurrency đáng tin hơn

Các race condition thường phụ thuộc thời gian, scheduler và phần cứng. Test chạy 1.000 lần rồi không thấy lỗi **không phải bằng chứng** rằng thiếu synchronized vẫn an toàn.

Một test tốt cần kiểm tra các **bảo đảm đã thiết kế** thay vì hy vọng tạo lỗi ngẫu nhiên:

1. **Bảo toàn phiên bản cũ:** tạo snapshot trước một thay đổi được điều phối, sau đó xác nhận snapshot cũ không chứa phần tử được thêm.
2. **Bản mới sau cập nhật:** dùng `CountDownLatch` hoặc `Thread.join` để xác nhận writer hoàn tất, rồi chụp bằng cùng lock và kiểm tra dữ liệu mới.
3. **Atomic publication:** reader nhận một object immutable-state duy nhất; xác nhận các trường thuộc một revision được công bố cùng nhau.
4. **Mutator bị chặn:** kiểm tra `UnsupportedOperationException` khi gọi `add`/`remove` trên kết quả `copyOf`.
5. **Đầu vào xấu:** xác nhận null collection/null elements bị từ chối theo hợp đồng.
6. **Không khóa quá lâu:** đo độ trễ tạo snapshot trên workload thực để kiểm tra ảnh hưởng lên writer.
7. **Phân tích nhiều writers:** xác nhận không mất update do thao tác read-modify-write không nguyên tử. Với `AtomicReference.updateAndGet`, hàm chuyển đổi phải an toàn khi được gọi lại.
8. **Dữ liệu nhiều phần:** test invariant giữa các trường, ví dụ `revision` và nội dung cấu hình, hoặc giới hạn không nhỏ hơn mức đã dùng.

`CountDownLatch`, `CyclicBarrier` hay `Phaser` giúp lập lịch kiểm thử có kiểm soát, nhưng **không tự sửa** một thuật toán thiếu đồng bộ. Chúng chỉ làm thứ tự sự kiện trong test rõ hơn. Khi cần phân tích sâu, có thể dùng công cụ chuyên biệt để phát hiện data race/stress test, nhưng vẫn phải bắt đầu từ hợp đồng và tính đúng.

## 16. Bài tập thực hành có đáp án

### Câu 1 — Bản copy trước khi thay đổi nguồn

~~~java
var source = new ArrayList<>(List.of("A", "B"));
var old = List.copyOf(source);
source.add("C");
~~~

**Hỏi:** `old` có chứa `C` không?

**Đáp án:** Không. Ở đây thao tác thay đổi nguồn được thực hiện **sau khi** `copyOf` hoàn tất, nên `old` vẫn là `[A, B]`.

### Câu 2 — Gọi copy trong lúc writer đang sửa

Có một `ArrayList` được hai thread dùng chung, writer gọi `add` liên tục còn reader gọi `List.copyOf` không có cơ chế đồng bộ.

**Đáp án:** Không được giả định snapshot nhất quán, và không được giả định luôn có `ConcurrentModificationException`. Phải thiết kế lock chung, snapshot ổn định hoặc chuyển sang mô hình công bố immutable state.

### Câu 3 — Wrapper read-only

~~~java
var base = new ArrayList<>(List.of(1, 2));
var view = Collections.unmodifiableList(base);
base.add(3);
~~~

**Hỏi:** `view` có thể thấy `3` không?

**Đáp án:** Có. Wrapper không phải snapshot; nó quan sát backing list. Trong ví dụ tuần tự này `view` có thể hiển thị `[1, 2, 3]`. Với truy cập đồng thời, cần bảo vệ cách đọc view cho phù hợp.

### Câu 4 — Lock nào có ý nghĩa?

~~~java
var copy = List.copyOf(shared);
synchronized (LOCK) {
    publish(copy);
}
~~~

**Hỏi:** Đoạn trên bảo vệ quá trình lấy snapshot chưa?

**Đáp án:** Chưa. `copyOf` chạy **trước** lock. Muốn đồng bộ capture, phải giữ cùng lock trong lúc copy và mọi writer phải dùng lock đó.

### Câu 5 — Nhiều tham chiếu tới version khác nhau

~~~java
var revision = published.get().revision();
var flags = published.get().flags();
~~~

**Hỏi:** Hai giá trị luôn thuộc cùng một phiên bản không?

**Đáp án:** Không. Writer có thể gọi `published.set(next)` giữa hai lần `get()`. Đọc `var snapshot = published.get();` **một lần**, rồi đọc `snapshot.revision()` và `snapshot.flags()`.

### Câu 6 — CopyOnWrite iterator

~~~java
var cow = new CopyOnWriteArrayList<>(List.of("A", "B"));
var it = cow.iterator();
cow.add("C");
~~~

**Hỏi:** `it` sẽ duyệt thêm `C` không?

**Đáp án:** Không. Iterator thuộc `CopyOnWriteArrayList` là snapshot iterator, nó phản ánh trạng thái ở thời điểm tạo. Iterator mới hoặc truy vấn list hiện tại có thể thấy `C`.

### Câu 7 — ConcurrentHashMap

Một ứng dụng dùng `ConcurrentHashMap` và gọi `Map.copyOf(map)` trong lúc luồng khác cập nhật nhiều key. Có nên gọi kết quả “ảnh chụp transaction nhất quán” không?

**Đáp án:** Không. Collection concurrent bảo đảm những thuộc tính thread-safety riêng của nó, nhưng không tự tạo giao dịch nhiều key. Nếu cần phiên bản đồng nhất, dùng atomic immutable aggregate, một giao thức phối hợp hoặc một nguồn có transactional snapshot semantics.

### Câu 8 — Snapshot nông

~~~java
var box = new StringBuilder("A");
var snapshot = List.copyOf(List.of(box));
box.append("B");
~~~

**Hỏi:** Giá trị phần tử qua `snapshot.get(0)` có thay đổi không?

**Đáp án:** Có; nó vẫn trỏ tới object `StringBuilder` đã đổi thành `AB`. `copyOf` không tạo deep copy.

### Câu 9 — Synchronized wrapper

~~~java
var shared = Collections.synchronizedList(
    new ArrayList<>(List.of("A", "B"))
);
~~~

**Hỏi:** Khi một chuỗi duyệt hoặc snapshot phải thấy danh sách ổn định, nên làm gì?

**Đáp án:** Bao việc duyệt/copy trong `synchronized(shared)` và bảo đảm writer chỉ thao tác qua wrapper hoặc theo cùng monitor. Đừng mutate một tham chiếu `ArrayList` nền còn bị lộ ra ngoài wrapper.

### Câu 10 — Khi nào không cần snapshot nhất quán tuyệt đối?

Một bộ thống kê phục vụ biểu đồ gần thời gian thực chấp nhận thấy vài bản cập nhật chậm hơn. Dữ liệu không dùng cho kế toán, quota hay phân quyền.

**Đáp án:** Tùy hợp đồng, có thể chọn cấu trúc concurrent và kết quả weakly consistent để giảm contention. Nhưng phải **ghi rõ tính nhất quán được chấp nhận**, tránh tuyên bố đó là transaction snapshot. Với quota, phân quyền và dữ liệu có invariant chặt, thường cần ràng buộc nghiêm hơn.

## 17. Checklist áp dụng trong code review

- [ ] **Nguồn có thể bị thay đổi đồng thời?** Liệt kê mọi writer, kể cả đường sửa qua alias, sublist, iterator và field của object phần tử.
- [ ] **Có snapshot consistency requirement không?** Xác định rõ phiên bản cần quan sát hoặc mức độ sai lệch cho phép.
- [ ] **Lock dùng thống nhất chưa?** Nếu dùng monitor, tất cả writer và reader có tuân thủ cùng lock trong toàn bộ thao tác không?
- [ ] **Nhiều collection liên quan?** Có capture dưới một giao thức đồng bộ hoặc transaction chung không?
- [ ] **Nguồn là concurrent collection?** Đã đọc đúng chính sách iterator/consistency, không tự xem nó là atomic snapshot chưa?
- [ ] **Có dùng `Collections.unmodifiable*`?** Hiểu đó là view, không phải snapshot chưa?
- [ ] **Dữ liệu có được công bố an toàn?** Dùng `AtomicReference`, `volatile` hoặc các cơ chế happens-before phù hợp chưa?
- [ ] **Reader lấy một revision duy nhất?** Đọc tham chiếu một lần cho toàn thao tác hay liên tục gọi get?
- [ ] **Phần tử có mutable không?** Có cần deep copy/immutable values và đồng bộ riêng không?
- [ ] **Có kiểm thử các ca cạnh tranh theo lịch rõ?** Tránh test phụ thuộc ngoại lệ ngẫu nhiên.
- [ ] **Có đánh giá chi phí snapshot?** Tính thời gian copy, bộ nhớ, mức contention và tần suất cập nhật.
- [ ] **Có phân biệt bản copy cũ với trạng thái hiện tại?** Nếu cần dữ liệu mới, có cơ chế công bố/tái tạo snapshot chưa?

## 18. Tài liệu Java chính thức còn phù hợp

- [Java SE API — `List.copyOf` và Unmodifiable Lists](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/List.html): bảo đảm của danh sách unmodifiable, snapshot cấu trúc, cấm null và giới hạn về phần tử mutable.
- [Java SE API — `Set.copyOf`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Set.html): tương tự với các phần tử unique của set.
- [Java SE API — `Map.copyOf`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Map.html): ảnh hưởng của map nguồn và unmodifiable map kết quả.
- [Java SE API — `Collections.synchronizedList` và `unmodifiableList`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Collections.html): wrapper đồng bộ, yêu cầu khóa khi duyệt, và read-only view.
- [Java SE API — `ArrayList`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/ArrayList.html): không được đồng bộ sẵn; iterator fail-fast không phải bảo đảm correctness.
- [Java SE API — `ConcurrentHashMap`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html): chính sách duyệt weakly consistent và truy cập đồng thời.
- [Java SE API — `CopyOnWriteArrayList`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/CopyOnWriteArrayList.html): snapshot iterator và đặc điểm copy-on-write.
- [Java SE API — `AtomicReference`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/atomic/AtomicReference.html): công bố và thay tham chiếu atomic, `updateAndGet`.
- [Java SE API — `CountDownLatch`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/CountDownLatch.html): điều phối luồng trong kiểm thử.
- [Java Language Specification, `17 — Threads and Locks](https://docs.oracle.com/javase/specs/jls/se25/html/jls-17.html): Java Memory Model, happens-before và đồng bộ trong chương trình nhiều luồng.
- [JEP 269 — Convenience Factory Methods for Collections](https://openjdk.org/jeps/269): bối cảnh các unmodifiable factory hiện đại; `copyOf` được bổ sung ở Java 10 và tiếp tục dùng trong JDK hiện tại.

**Ghi nhớ:** `copyOf` là công cụ tốt để xây một **collection không thể sửa** từ dữ liệu đã hợp lệ, nhưng **không thay thế việc đồng bộ khi chụp một nguồn đang bị sửa**. Muốn snapshot nhất quán, bảo vệ thao tác đọc nguồn bằng đúng giao thức các writer sử dụng, hoặc xây dựng trạng thái bất biến và công bố một tham chiếu phiên bản hoàn chỉnh. Với dữ liệu quan trọng, hãy kiểm tra cả tính nguyên tử của **quá trình capture**, tính an toàn của **quá trình publication**, và giới hạn **bất biến nông** của các phần tử.