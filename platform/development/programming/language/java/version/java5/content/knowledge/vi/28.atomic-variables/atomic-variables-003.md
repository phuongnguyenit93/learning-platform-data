# AtomicReference và cập nhật tham chiếu

## 1. Cập nhật một ô tham chiếu dùng chung

Giả sử ứng dụng có một bản cấu hình hiện tại. Nhiều luồng đọc nó; một số luồng có thể tạo phiên bản mới rồi công bố thay thế.

`AtomicReference<V>` là một đối tượng giữ **một tham chiếu** kiểu V, cung cấp các thao tác đọc, thay thế và cập nhật có điều kiện theo cách nguyên tử.

```java
AtomicReference<Settings> current =
        new AtomicReference<>(initialSettings);
```

Đây là khai báo minh họa; Settings và initialSettings do ứng dụng định nghĩa. Lớp nằm trong `java.util.concurrent.atomic`.

Cần hiểu đúng vấn đề: phép gán tham chiếu Java thông thường vốn không bị đọc thành “nửa địa chỉ”. AtomicReference có giá trị ở **ngữ nghĩa truy cập bộ nhớ và các thao tác cập nhật phối hợp**, chẳng hạn so sánh rồi thay thế trong một thao tác nguyên tử.

Nó không biến toàn bộ đồ thị đối tượng mà tham chiếu trỏ tới thành dữ liệu tự động an toàn giữa các luồng.

## 2. Ba đối tượng cần phân biệt

```text
Các luồng cùng dùng
        |
        v
AtomicReference<Settings>     <- ô tham chiếu có API nguyên tử
        |
        v
Settings hiện tại            <- đối tượng được trỏ tới
        |
        v
Dữ liệu lồng bên trong       <- có thể bất biến hoặc thay đổi được
```

AtomicReference bảo vệ thao tác thay đổi **tham chiếu hiện tại**. Nếu Settings chứa một ArrayList mà các luồng tự sửa, danh sách ấy vẫn cần giao thức riêng hoặc phải được thiết kế bất biến.

Ví dụ sai về suy luận:

```java
AtomicReference<ArrayList<String>> names =
        new AtomicReference<>(new ArrayList<>());

names.get().add("An");
```

Đoạn trên không làm phép add trở thành nguyên tử hoặc an toàn chỉ vì đã gọi get trên AtomicReference. Các luồng vẫn có thể cùng sửa một ArrayList thường.

Không dùng AtomicReference như một “lớp vỏ thread-safe” chung cho mọi đối tượng.

## 3. Các thao tác nền tảng

| API | Ý nghĩa |
|---|---|
| `get()` | Đọc tham chiếu hiện tại |
| `set(next)` | Thay tham chiếu bằng next |
| `getAndSet(next)` | Thay tham chiếu và trả tham chiếu trước đó trong cùng thao tác |
| `compareAndSet(expected, next)` | Chỉ thay nếu tham chiếu hiện tại chính là expected |
| `updateAndGet(function)` | Cập nhật theo hàm và trả giá trị sau cập nhật |
| `getAndUpdate(function)` | Cập nhật theo hàm và trả giá trị trước cập nhật |

Constructor không đối số khởi tạo bằng null. Null là giá trị được phép đối với AtomicReference, khác với một số collection không chấp nhận null.

Ứng dụng vẫn cần quy định null nghĩa là gì: chưa khởi tạo, không có dữ liệu, đã đóng hay một trạng thái khác. Không để các hàm cập nhật vô tình giải tham chiếu null mà không có hợp đồng.

Chi tiết các thao tác nằm tại [AtomicReference API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/atomic/AtomicReference.html).

### Thay vô điều kiện khác cập nhật dựa trên giá trị cũ

`set` phù hợp khi muốn công bố phiên bản mới không phụ thuộc phiên bản hiện tại, theo quyền sở hữu và chính sách ứng dụng.

Nếu phiên bản mới được tính từ giá trị đang có và nhiều luồng cùng cập nhật, tách get rồi set thường không đủ.

## 4. Vì sao get rồi set vẫn có thể mất cập nhật?

Giả sử state giữ bản chụp có processed bằng 0. Hai luồng cùng làm:

```java
Snapshot old = state.get();
Snapshot next = new Snapshot(
        old.version() + 1,
        old.processed() + 1);
state.set(next);
```

Đây là đoạn minh họa lỗi cập nhật nhiều bên ghi, với kiểu Snapshot của ứng dụng.

Một diễn biến có thể xảy ra:

```text
Luồng A đọc processed=0
Luồng B đọc processed=0
A công bố processed=1
B công bố processed=1
```

Hai lần xử lý nhưng giá trị cuối chỉ là 1. Từng get và set có ngữ nghĩa nguyên tử riêng; **cả chuỗi đọc-tính-ghi không tự trở thành một giao dịch nguyên tử**.

Dùng updateAndGet hoặc một vòng compareAndSet phù hợp nếu yêu cầu là giữ tất cả cập nhật dựa trên trạng thái cũ.

Ngược lại, nếu chính sách là bản cấu hình được người quản trị công bố sau thay thế hoàn toàn bản trước, set có thể là lựa chọn đúng. Phải phân biệt ý nghĩa nghiệp vụ trước khi chọn API.

## 5. compareAndSet dùng danh tính, không gọi equals

CAS là viết tắt thường dùng của compare-and-set: so sánh giá trị đang giữ với giá trị kỳ vọng rồi chỉ cập nhật nếu khớp.

Đối với AtomicReference, phép so sánh là `==` trên tham chiếu.

Hai đối tượng record hoặc String có cùng nội dung, equals trả true, vẫn có thể là hai tham chiếu khác nhau. Dùng một bản sao “giống giá trị” làm expected không bảo đảm CAS thành công.

Mẫu thường gặp:

```java
Snapshot observed = state.get();
Snapshot replacement = createNext(observed);

if (state.compareAndSet(observed, replacement)) {
    // Lan thay the nay da thanh cong.
}
```

`createNext` là logic của ứng dụng. Giữ chính tham chiếu đã đọc làm expected giúp kiểm tra rằng ô tham chiếu vẫn là giá trị mong đợi tại thời điểm CAS.

CAS trả false là kết quả bình thường khi giá trị hiện tại không khớp. Nó không đồng nghĩa đối tượng expected không hợp lệ hoặc có một ngoại lệ nội bộ.

### Giá trị trả về khác compareAndExchange

`compareAndSet` trả boolean. API `compareAndExchange` hiện hành trả giá trị thực tế quan sát được tại phép so sánh, gọi là witness value.

Không nhầm hai hợp đồng khi xử lý kết quả. Bài dùng compareAndSet để giữ mô hình đơn giản; chưa cần các biến thể ngữ nghĩa bộ nhớ yếu hơn.

## 6. Cập nhật bằng hàm và vòng thử lại

Với một Snapshot bất biến:

```java
Snapshot updated = state.updateAndGet(
        old -> new Snapshot(
                old.version() + 1,
                old.processed() + 1));
```

Nếu có tranh chấp, việc cập nhật có thể cần tính lại từ giá trị mới hơn. Hàm có thể được áp dụng nhiều lần dù chỉ một lần thay thế cuối cùng của lời gọi thành công.

Vì vậy, hàm cập nhật nên chỉ tạo giá trị mới từ đầu vào, không có tác động phụ bên ngoài.

### Không gửi thông báo trong hàm cập nhật

Ví dụ cần tránh:

```java
state.updateAndGet(old -> {
    sendNotification();
    return createNext(old);
});
```

Thông báo có thể được gửi lại nếu hàm được đánh giá lại khi tranh chấp. Ngay cả sửa đối tượng old bên trong cũng nguy hiểm: các luồng khác có thể đang đọc cùng đối tượng đó trước khi CAS thành công.

Các tác động phụ phải được tổ chức riêng theo yêu cầu. Đặt một hành động sau CAS thành công chỉ giải quyết việc không làm nó trong nhánh CAS thất bại; nó không tự cung cấp giao dịch bền vững giữa cập nhật bộ nhớ và gửi ra hệ thống ngoài.

### Vòng CAS viết tường minh

```java
for (;;) {
    Snapshot old = state.get();
    Snapshot next = createNext(old);

    if (state.compareAndSet(old, next)) {
        return next;
    }
}
```

Đây là phương thức minh họa với createNext do ứng dụng cung cấp. Nếu thất bại, phải đọc lại và tính từ giá trị phù hợp, không giữ mãi một expected đã lỗi thời rồi thử lại vô hạn.

Vòng retry có thể tốn CPU và cấp phát nhiều đối tượng khi tranh chấp cao. Không suy luận “không viết lock” đồng nghĩa mọi luồng hoàn tất trong thời gian cố định.

## 7. Chương trình Java 17+: danh tính và cập nhật nhiều luồng

Ví dụ dùng record chứa hai trường nguyên thủy, nên các bản chụp không có dữ liệu bên trong có thể bị sửa.

Lưu thành **`AtomicReferenceDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

public class AtomicReferenceDemo {
    record Snapshot(long version, long processed) {}

    public static void main(String[] args) throws Exception {
        Snapshot initial = new Snapshot(0, 0);
        AtomicReference<Snapshot> state =
                new AtomicReference<>(initial);

        Snapshot equalCopy = new Snapshot(0, 0);

        System.out.println(
                "equal values: " + initial.equals(equalCopy));
        System.out.println(
                "CAS equal copy: "
                + state.compareAndSet(
                        equalCopy, new Snapshot(99, 99)));
        System.out.println(
                "CAS observed: "
                + state.compareAndSet(initial, new Snapshot(1, 0)));

        ExecutorService pool = Executors.newFixedThreadPool(4);
        CountDownLatch start = new CountDownLatch(1);
        List<Future<?>> tasks = new ArrayList<>();

        try {
            for (int worker = 0; worker < 4; worker++) {
                tasks.add(pool.submit(() -> {
                    start.await();
                    for (int i = 0; i < 1000; i++) {
                        state.updateAndGet(old -> new Snapshot(
                                old.version() + 1,
                                old.processed() + 1));
                    }
                    return null;
                }));
            }

            start.countDown();

            for (Future<?> task : tasks) {
                task.get(5, TimeUnit.SECONDS);
            }

            Snapshot completed = state.get();
            System.out.println(
                    "processed: " + completed.processed());
            System.out.println(
                    "version: " + completed.version());

            Snapshot previous = state.getAndSet(
                    new Snapshot(completed.version() + 1, 0));

            System.out.println(
                    "before reset: " + previous.processed());
            System.out.println(
                    "after reset: " + state.get().processed());
        } finally {
            start.countDown();
            pool.shutdown();
            try {
                if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                    pool.shutdownNow();
                    if (!pool.awaitTermination(
                            5, TimeUnit.SECONDS)) {
                        throw new IllegalStateException(
                                "Executor did not terminate");
                    }
                }
            } catch (InterruptedException e) {
                pool.shutdownNow();
                Thread.currentThread().interrupt();
                throw e;
            }
        }
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 AtomicReferenceDemo.java
java AtomicReferenceDemo
```

Stdout chính xác:

```text
equal values: true
CAS equal copy: false
CAS observed: true
processed: 4000
version: 4001
before reset: 4000
after reset: 0
```

### Đọc kết quả

Hai record đầu có cùng giá trị nhưng khác đối tượng; CAS với equalCopy thất bại. CAS với chính initial đang được giữ thành công, đưa version lên 1 nhưng processed vẫn bằng 0.

Bốn worker thực hiện tổng cộng 4000 lần cập nhật thành công. Mỗi lần tạo Snapshot mới với cả hai trường, nên processed tăng tới 4000 và version tăng thêm 4000 tới 4001.

Số lần hàm lambda được đánh giá nội bộ có thể nhiều hơn số cập nhật thành công; ví dụ không in hoặc đếm tác động phụ trong lambda để tránh nhầm điều này.

Main chờ mọi worker hoàn tất rồi mới reset, nên không còn cuộc đua với phần reset trong thí nghiệm. `getAndSet` trả bản chụp trước reset đồng thời công bố bản mới có processed bằng 0.

Main khai báo throws Exception để tập trung vào hành vi nguyên tử. Các lời chờ có thời hạn giúp phát hiện thiếu tiến triển; ứng dụng thật cần xử lý lỗi và ngắt theo quyền sở hữu công việc.

## 8. Công bố một bản chụp nhất quán

Giả sử cấu hình có endpoint và retryLimit phải đi cùng nhau. Đặt chúng trong một đối tượng bất biến rồi thay một tham chiếu giúp bên đọc lấy **một phiên bản**:

```java
Settings snapshot = current.get();
use(snapshot.endpoint(), snapshot.retryLimit());
```

Đây là mã minh họa. Đọc tham chiếu một lần rồi dùng các trường của cùng snapshot tránh vô tình trộn hai phiên bản.

Cách có thể không đúng với yêu cầu nhất quán:

```java
use(current.get().endpoint(), current.get().retryLimit());
```

Một bên ghi có thể công bố phiên bản mới giữa hai lần get, làm hai trường thuộc hai Settings khác nhau.

### Record không tự làm mọi thành phần bất biến sâu

Record có trường List chỉ làm tham chiếu thành phần không bị gán lại theo cách thông thường. Nội dung List vẫn có thể thay đổi nếu giữ một danh sách có thể thay đổi.

Có thể dùng List.copyOf khi tạo snapshot nếu hợp đồng phù hợp, nhưng các phần tử cũng phải được xét: sao chép danh sách không sao chép sâu mọi đối tượng bên trong.

Thiết kế bản chụp phải bảo đảm những dữ liệu bên đọc sử dụng không bị bên ghi sửa trực tiếp sau khi công bố.

## 9. Ngữ nghĩa bộ nhớ: get/set mặc định và giới hạn

`get` và `set` của AtomicReference dùng ngữ nghĩa truy cập volatile theo hợp đồng. Việc công bố đối tượng đã được xây dựng đúng trước set, và đọc nó qua get theo quan hệ tương ứng, hỗ trợ việc thấy dữ liệu đã công bố.

Điều này không bảo vệ các thay đổi không đồng bộ xảy ra **sau đó** trên cùng đối tượng có thể thay đổi.

Cũng không làm hai AtomicReference khác nhau trở thành một giao dịch chung. Nếu hai tham chiếu phải thay đồng thời theo một bất biến, có thể đặt trạng thái liên quan trong cùng một snapshot hoặc dùng giao thức đồng bộ phù hợp.

Các lớp atomic chủ yếu cung cấp thao tác trên từng biến; xem [tổng quan java.util.concurrent.atomic](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/atomic/package-summary.html).

API hiện hành có các biến thể plain, opaque, acquire hoặc release phục vụ những giao thức bộ nhớ chuyên biệt. Không tự thay get/set trong ví dụ bằng một biến thể yếu hơn chỉ vì tên nghe nhẹ hoặc nhanh; phải chứng minh quan hệ bộ nhớ cần thiết.

## 10. CAS không nhớ toàn bộ lịch sử: điểm cần biết về ABA

Giả sử một luồng đọc tham chiếu A, rồi bị tạm dừng. Trong lúc đó luồng khác thay:

```text
A -> B -> A
```

Nếu tham chiếu hiện tại trở lại **chính đối tượng A cũ**, CAS kiểm tra expected=A có thể thành công. Nó chỉ thấy giá trị hiện tại khớp, không tự biết đã có hai lần thay đổi ở giữa.

Đó là vấn đề ABA trong những thuật toán cần biết trạng thái chưa trải qua chuyển đổi trung gian.

Không phải mọi ứng dụng cấu hình đều bị lỗi vì tình huống ấy. Phải xét việc thuật toán có phụ thuộc lịch sử hay chỉ cần so giá trị hiện tại.

Một cách thiết kế có thể là mỗi chuyển đổi công bố một đối tượng bao bất biến mới kèm phiên bản, với giao thức không đưa đối tượng bao cũ trở lại. Một lựa chọn chuyên biệt là AtomicStampedReference ghép tham chiếu và stamp để kiểm tra cùng nhau. Stamp vẫn cần quy tắc cập nhật và xử lý phạm vi; không chỉ thêm một số rồi cho rằng mọi thuật toán tự đúng.

Ví dụ của bài luôn tạo Snapshot mới cho cập nhật và không cài lại đối tượng bao cũ trong các worker. Trường version làm lịch sử dễ quan sát, không phải một lời khẳng định mọi kiểu tái sử dụng đối tượng đều an toàn.

## 11. Khi nào dùng và khi nào nên chọn cách khác?

| Nhu cầu | Hướng cân nhắc |
|---|---|
| Bên đọc lấy cấu hình bất biến hiện tại, bên ghi thay cả bản | AtomicReference hoặc volatile reference tùy nhu cầu cập nhật |
| Nhiều bên ghi tính bản mới từ bản cũ | `updateAndGet` hoặc CAS với hàm không có tác động phụ |
| Chỉ tăng một số | AtomicInteger/AtomicLong thường diễn đạt rõ hơn |
| Nhiều cấu trúc có thể thay đổi cần cập nhật theo một bất biến | Khóa hoặc thiết kế trạng thái tổng hợp thích hợp |
| Cần chờ điều kiện, phối hợp nhiều bước dài | Giao thức khóa/điều kiện hoặc cơ chế điều phối khác |
| Tranh chấp cao và snapshot lớn | Đo retry, cấp phát, thu gom rác và độ trễ trước khi chọn |

Volatile reference có thể đủ khi chỉ cần công bố bản mới và không có phép cập nhật dựa trên trạng thái cũ cần so sánh nguyên tử. AtomicReference hữu ích khi cần các thao tác phối hợp bổ sung.

Không chọn vì mục tiêu bỏ mọi từ khóa synchronized hoặc Lock khỏi mã. Một vòng CAS phức tạp hơn có thể khó chứng minh và chẩn đoán hơn một vùng khóa ngắn có trách nhiệm rõ.

## 12. Tự kiểm tra

1. AtomicReference<ArrayList<T>> có làm mọi thao tác add trên danh sách an toàn không?
2. CAS dùng equals hay danh tính tham chiếu?
3. Vì sao get rồi set có thể mất cập nhật dù từng phương thức là nguyên tử?
4. Hàm updateAndGet có chắc được gọi đúng một lần cho mỗi lời gọi API không?
5. Vì sao nên lấy snapshot một lần trước khi đọc nhiều trường liên quan?
6. Hai AtomicReference riêng có tự cập nhật thành một giao dịch chung không?
7. CAS thành công có tự chứng minh tham chiếu chưa từng đổi rồi quay lại đối tượng cũ không?

**Gợi ý:** (1) Không. (2) Danh tính theo ==. (3) Chuỗi đọc-tính-ghi có thể xen kẽ. (4) Không; có thể được đánh giá lại khi tranh chấp. (5) Để dùng cùng một phiên bản dữ liệu. (6) Không. (7) Không; phải xét ABA nếu lịch sử có ý nghĩa.

AtomicReference phù hợp khi thiết kế rõ **ô tham chiếu cần cập nhật, trạng thái bất biến được công bố và điều kiện để một thay thế được chấp nhận**.
