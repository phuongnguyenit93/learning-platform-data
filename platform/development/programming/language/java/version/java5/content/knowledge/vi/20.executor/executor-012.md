# Quyền sở hữu và trách nhiệm đóng vòng đời ExecutorService

## 1. Câu hỏi đầu tiên: ai có quyền quyết định dừng?

Một bộ thực thi có thể được nhiều dịch vụ dùng chung. Dịch vụ tạo báo cáo gửi xong tác vụ rồi gọi `shutdown()`; ngay sau đó dịch vụ lập chỉ mục gửi việc và bị từ chối. Từng phương thức có vẻ đã “dọn tài nguyên”, nhưng toàn ứng dụng bị lỗi vì quyền đóng đặt sai nơi.

**Bên sở hữu** là thành phần chịu trách nhiệm cho vòng đời tài nguyên: khởi tạo hoặc tiếp nhận quyền quản lý, xác định lúc ngừng sử dụng, yêu cầu dừng và xác nhận kết quả.

**Bên mượn** được sử dụng tài nguyên trong một phạm vi đã thỏa thuận. Nó không tự kết thúc vòng đời tài nguyên dùng chung.

Cần phân biệt ba phạm vi:

- Một **tác vụ** kết thúc khi công việc đó thành công, thất bại hoặc bị hủy.
- Một **yêu cầu** có thể hoàn thành trong khi ứng dụng tiếp tục dùng cùng bộ thực thi.
- Một **bộ thực thi** chỉ kết thúc khi toàn bộ vòng đời của nó được bên sở hữu đóng lại.

Quyền gửi công việc không tự kéo theo quyền đóng bộ thực thi. Bài này tập trung vào quyết định sở hữu và thứ tự dọn tài nguyên; các ví dụ chính dùng Java 17+, phần `try-with-resources` cho `ExecutorService` dùng Java 21+.

## 2. Quyền sở hữu là hợp đồng của thiết kế

| Cách nhận bộ thực thi | Cách hiểu nên thể hiện trong hợp đồng |
| --- | --- |
| Hàm tạo bên trong một đối tượng một bộ thực thi riêng | Đối tượng thường sở hữu và phải có cơ chế kết thúc |
| Hàm nhận bộ thực thi dùng chung qua tham số | Thường là mượn; hàm không đóng |
| Container tạo và quản lý vòng đời | Container sở hữu; thành phần sử dụng tuân theo vòng đời đó |
| Factory chuyển giao một bộ thực thi mới cho bên gọi | Bên gọi nhận trách nhiệm đóng |
| Truyền một instance có sẵn với thỏa thuận chuyển quyền | Bên nhận trở thành chủ sở hữu theo hợp đồng tường minh |

“Bên tạo thì bên đó đóng” là quy tắc khởi đầu tốt, nhưng có trường hợp **chuyển giao quyền sở hữu**. Vì vậy không chỉ nhìn vị trí lệnh `new`; cần biết tài nguyên được trao cho ai và còn ai tiếp tục sử dụng.

Một hợp đồng đủ rõ nên trả lời:

1. Ai được gửi công việc và trong khoảng thời gian nào?
2. Ai ngừng việc tiếp nhận?
3. Công việc đã nhận được chờ hoàn tất hay hủy?
4. Ai theo dõi lỗi và kết quả?
5. Ai xác nhận bộ thực thi đã kết thúc?

Không cần cho mọi lớp đều có phương thức `close()`. Nếu một lớp chỉ mượn bộ thực thi, việc thêm `close()` rồi đóng tài nguyên mượn có thể làm người dùng hiểu sai phạm vi quyền hạn.

## 3. Ví dụ Java 17: hai bên mượn, một bên sở hữu

Chương trình dưới đây tạo một bộ thực thi ở điểm ghép ứng dụng, truyền nó cho hai khách sử dụng rồi đóng ở cuối phạm vi ứng dụng. Mỗi khách chỉ gửi việc và trả `Future`.

Tệp **ExecutorOwnershipDemo.java**:

```java
import java.util.Objects;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class ExecutorOwnershipDemo {
    static final class TaskClient {
        private final String role;
        private final ExecutorService borrowedExecutor;

        // Bo thuc thi duoc muon; ben goi giu quyen quan ly vong doi.
        TaskClient(String role, ExecutorService borrowedExecutor) {
            this.role = Objects.requireNonNull(role);
            this.borrowedExecutor = Objects.requireNonNull(borrowedExecutor);
        }

        Future<String> process(int id) {
            return borrowedExecutor.submit(() -> role + "-" + id);
        }
    }

    private static boolean stopOwnedExecutor(ExecutorService executor) {
        executor.shutdown();
        try {
            if (executor.awaitTermination(5, TimeUnit.SECONDS)) {
                return true;
            }
            executor.shutdownNow();
            return executor.awaitTermination(5, TimeUnit.SECONDS);
        } catch (InterruptedException ex) {
            executor.shutdownNow();
            Thread.currentThread().interrupt();
            return false;
        }
    }

    public static void main(String[] args) throws Exception {
        ExecutorService ownedExecutor = Executors.newFixedThreadPool(2);

        try {
            TaskClient reports = new TaskClient("report", ownedExecutor);
            TaskClient indexing = new TaskClient("index", ownedExecutor);

            System.out.println(reports.process(7).get());
            System.out.println("shutdownAfterReport=" + ownedExecutor.isShutdown());
            System.out.println(indexing.process(8).get());
        } finally {
            boolean terminated = stopOwnedExecutor(ownedExecutor);
            System.out.println("ownerObservedTermination=" + terminated);
            if (!terminated) {
                System.err.println("Executor termination was not confirmed");
            }
        }
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 ExecutorOwnershipDemo.java
java ExecutorOwnershipDemo
```

Stdout khi thực thi hoàn tất bình thường:

```text
report-7
shutdownAfterReport=false
index-8
ownerObservedTermination=true
```

Sau khi xử lý báo cáo, bộ thực thi vẫn tiếp nhận công việc lập chỉ mục. Điều đó minh họa một yêu cầu kết thúc không kéo theo tài nguyên dùng chung kết thúc.

`TaskClient` giữ tham chiếu riêng nhưng không cung cấp thao tác đóng. Tên `borrowedExecutor` và chú thích hợp đồng làm rõ ý định; hệ thống kiểu của Java không tự chứng minh quyền sở hữu này. Người viết lớp vẫn có trách nhiệm không gọi `shutdown()` trên tài nguyên mượn.

Phương thức dừng có hai lượt chờ. Trả `true` nghĩa đã quan sát kết thúc; trả `false` nghĩa chưa xác nhận, bao gồm trường hợp luồng điều phối bị ngắt. Cờ ngắt được khôi phục để tầng trên còn nhận biết tín hiệu. Không đổi `false` thành thông báo “đã dừng thành công”.

Các tác vụ trong ví dụ rất ngắn và đã được lấy kết quả trước khi đóng. Nếu ứng dụng hủy khi còn nhiều tác vụ chờ, bên sở hữu cần thêm chính sách cho các công việc đó.

## 4. Quyền đóng gồm cả trách nhiệm xử lý phần việc còn lại

Các API dừng giải quyết những phần khác nhau:

| API | Bên sở hữu có thể kết luận gì? |
| --- | --- |
| `shutdown()` | Đã yêu cầu ngừng nhận mới; việc đã nhận vẫn được phép tiếp tục |
| `shutdownNow()` | Đã yêu cầu dừng mạnh hơn và nhận danh sách công việc chưa bắt đầu |
| `awaitTermination(...)` trả `true` | Bộ thực thi đã kết thúc |
| `isShutdown()` trả `true` | Quá trình dừng đã được khởi động; chưa chứng minh kết thúc |

`shutdown()` và `shutdownNow()` đều không tự chờ mọi tác vụ dừng. Yêu cầu ngắt cũng không cưỡng ép một tác vụ bỏ qua tín hiệu phải kết thúc. [Tài liệu ExecutorService trên Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html)

Quyết định đóng cần gắn với chính sách công việc:

- **Đã hoàn tất:** quan sát kết quả, ghi nhận thành công hoặc lỗi.
- **Đang chạy:** cho hoàn tất trong ngân sách, hoặc yêu cầu hủy có hợp tác.
- **Chưa bắt đầu:** hủy, báo không được xử lý hoặc chuyển sang nơi tiếp nhận khác theo hợp đồng.
- **Đã tạo tác dụng phụ:** xác định có cần dọn dữ liệu tạm hay hỗ trợ chạy lại an toàn.

Danh sách trả về từ `shutdownNow()` không phải giấy xác nhận mọi `Future` tương ứng đã chuyển sang trạng thái hủy. Mã quản lý công việc nên giữ các handle cần thiết và hoàn tất/hủy chúng theo chính sách; không để bên gọi chờ vô hạn một việc sẽ không được chạy.

Đóng bộ thực thi cũng không tự hoàn tác hóa đơn đã ghi, tệp đã tạo hay yêu cầu đã gửi ra ngoài. Khả năng chạy lại an toàn thuộc về thiết kế tác vụ.

## 5. Thứ tự dừng phải theo quan hệ phụ thuộc

Giả sử các tác vụ dùng kết nối cơ sở dữ liệu:

```text
Nguồn gửi công việc
    -> bộ thực thi
        -> tác vụ
            -> tài nguyên cơ sở dữ liệu
```

Một thứ tự dừng thường hợp lý:

1. Ngừng hoặc điều phối các nguồn tạo công việc mới.
2. Ngừng bộ thực thi tiếp nhận thêm.
3. Chờ hoặc hủy công việc đã nhận và xác nhận kết quả dừng.
4. Đóng tài nguyên mà các tác vụ sử dụng.

Đóng cơ sở dữ liệu ở bước đầu có thể làm tác vụ đang xử lý thất bại giữa chừng. Ngược lại, giữ nguồn gửi hoạt động trong khi bộ thực thi đã dừng sẽ tạo yêu cầu bị từ chối. Cần xác định cách phản hồi các yêu cầu đến đúng lúc chuyển trạng thái.

Nếu lượt chờ hết hạn và vẫn còn tác vụ chạy, không được giả định đã an toàn để đóng mọi tài nguyên phụ thuộc. Bên sở hữu phải áp dụng chính sách vận hành rõ ràng: báo lỗi dừng, tiếp tục chờ có giới hạn khác hoặc chấp nhận việc chấm dứt tiến trình theo cơ chế triển khai. Không có một chuỗi API nào thay thế được quyết định này.

### Không để tác vụ tự chờ bộ thực thi của chính nó

Một tác vụ gọi `awaitTermination` hoặc `close()` trên bộ thực thi đang chạy chính nó có thể chờ sự kết thúc của bản thân. Điểm điều phối đóng nên nằm ngoài nhóm công việc đang được chờ.

Nếu một tác vụ phát hiện cần dừng hệ thống, nó có thể báo tín hiệu cho bên sở hữu. Bên sở hữu thực hiện quy trình dừng từ phạm vi điều phối thích hợp.

## 6. Java 19+: AutoCloseable diễn đạt một phạm vi sở hữu

Từ Java 19, `ExecutorService` triển khai `AutoCloseable`, nên Java 21+ cho phép dùng trực tiếp trong `try-with-resources`.

`close()` bắt đầu dừng có trật tự và chờ bộ thực thi kết thúc. Nó không có tham số timeout. Nếu luồng đóng bị ngắt, nó yêu cầu dừng như `shutdownNow()`, tiếp tục chờ rồi khôi phục cờ ngắt trước khi trả về. Vì vậy, khối đóng có thể chờ lâu nếu tác vụ không chịu kết thúc. [Tài liệu ExecutorService.close](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ExecutorService.html#close())

Cú pháp tự đóng không tự quyết định ai là chủ sở hữu. Đặt một bộ thực thi dùng chung được truyền vào trong `try-with-resources` của một yêu cầu vẫn là lỗi thiết kế nếu yêu cầu đó không có quyền đóng.

`AutoCloseable` chỉ cung cấp giao thức `close()`; hợp đồng của từng loại tài nguyên mới xác định đóng sẽ làm gì. Nó không tự có nghĩa “đóng ngay”, “chờ tối đa vài giây” hoặc “không ảnh hưởng những bên khác”. [Tài liệu AutoCloseable](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/AutoCloseable.html)

### Ví dụ: đóng bộ thực thi trước tài nguyên mà tác vụ sử dụng

Tệp **ResourceOrderDemo.java**, chạy trên JDK 21+:

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class ResourceOrderDemo {
    static final class MemoryStore implements AutoCloseable {
        private volatile boolean closed;

        String read() {
            if (closed) {
                throw new IllegalStateException("Store is closed");
            }
            return "payload";
        }

        @Override
        public void close() {
            closed = true;
            System.out.println("store=closed");
        }
    }

    public static void main(String[] args) throws Exception {
        Future<String> result;

        try (MemoryStore store = new MemoryStore();
             ExecutorService executor = Executors.newSingleThreadExecutor()) {
            result = executor.submit(store::read);
            System.out.println("scope=leaving");
        }

        System.out.println("result=" + result.get());
        System.out.println("allResources=closed");
    }
}
```

Chạy:

```shell
javac --release 21 ResourceOrderDemo.java
java ResourceOrderDemo
```

Stdout:

```text
scope=leaving
store=closed
result=payload
allResources=closed
```

Các tài nguyên được đóng theo thứ tự ngược với khai báo: `executor` trước, `store` sau. Lệnh đóng bộ thực thi chờ tác vụ hoàn tất, nên tác vụ không phải đọc một store đã đóng. `Future.get()` sau khối vẫn quan sát kết quả hoặc lỗi đã được lưu; nó không cần store còn mở.

`MemoryStore` là tài nguyên giả lập để thấy thứ tự, không phải triển khai cơ sở dữ liệu. Khi áp dụng thực tế, cần xác minh tài nguyên phụ thuộc có hợp đồng đóng và dùng đồng thời phù hợp.

Nếu khai báo bộ thực thi trước store, thứ tự đóng bị đảo và có nguy cơ đóng store khi công việc vẫn chạy. Khi khối thân hoặc thao tác đóng ném lỗi, cơ chế `try-with-resources` vẫn thực hiện quy tắc dọn tài nguyên và có thể lưu lỗi đóng bổ sung trong danh sách suppressed exceptions. [JLS: try-with-resources](https://docs.oracle.com/javase/specs/jls/se25/html/jls-14.html#jls-14.20.3)

## 7. Thu hẹp quyền trong API

Nếu một thành phần chỉ cần gửi `Runnable`, có thể nhận giao diện `Executor` thay vì toàn bộ `ExecutorService`. Bề mặt API lúc đó không cung cấp phương thức đóng hay chờ kết thúc.

Nếu cần trả `Future`, một lựa chọn là cung cấp giao diện nghiệp vụ như `submitReport`, để quyền quản lý bộ thực thi ở thành phần sở hữu. Không nhất thiết phát tán tham chiếu bộ thực thi khắp hệ thống chỉ vì nhiều nơi cần gửi một loại công việc.

Đây là cách thể hiện ranh giới bằng thiết kế API, không phải cơ chế bảo vệ tuyệt đối. Không ép kiểu tài nguyên mượn chỉ để truy cập `shutdown()`; không dựa vào việc “vẫn gọi được phương thức” làm bằng chứng có quyền gọi.

Tránh constructor với tham số boolean mơ hồ như `closeExecutor` nếu người dùng khó xác định ý nghĩa. Nếu thư viện hỗ trợ cả hai chế độ, nên có cách tạo rõ như “tạo riêng và sở hữu” hoặc “dùng bộ thực thi bên ngoài”, kèm hợp đồng đóng.

## 8. Những lỗi sở hữu thường gặp

| Lỗi | Hậu quả | Cách sửa ở mức thiết kế |
| --- | --- | --- |
| Mỗi yêu cầu đóng bộ thực thi dùng chung | Yêu cầu sau bị từ chối | Đóng ở cuối vòng đời thành phần sở hữu |
| Tạo bộ thực thi mới trong mỗi lần gọi rồi quên đóng | Tích tụ luồng và tài nguyên | Dùng phạm vi riêng có dọn dẹp hoặc chia sẻ theo vòng đời |
| Nhiều bên đều nghĩ bên khác sẽ đóng | Không ai thực sự dọn tài nguyên | Ghi rõ một bên chịu trách nhiệm cuối cùng |
| Nhiều bên cùng tự đóng theo lịch riêng | Dừng ngoài dự kiến, lỗi khó truy vết | Một đầu mối quản lý, các bên khác báo tín hiệu |
| Đóng tài nguyên dữ liệu trước khi tác vụ kết thúc | Công việc đang chạy lỗi giữa chừng | Theo thứ tự phụ thuộc |
| Dừng từ một tác vụ rồi chờ chính bộ thực thi đó | Kẹt hoặc chờ vô ích | Đưa việc điều phối ra bên ngoài |

Gọi `shutdown()` nhiều lần không tạo thêm tác dụng dừng, nhưng tính chất đó không làm một thiết kế nhiều chủ sở hữu trở nên đúng. Vấn đề lớn hơn là ai quyết định **thời điểm** gọi.

Cũng không dùng thu gom rác hoặc cờ daemon thay cho quản lý vòng đời. Một chương trình cần biết lúc nào công việc không còn chạy và tài nguyên được giải phóng theo hợp đồng; việc một đối tượng không còn được mã nghiệp vụ giữ tham chiếu chưa chứng minh điều đó.

## 9. Kiểm chứng hợp đồng đóng

Một bài kiểm chứng có ý nghĩa nên đánh giá hành vi:

- Sau khi một bên mượn hoàn thành công việc, bên mượn khác vẫn gửi được.
- Khi bên sở hữu bắt đầu dừng, yêu cầu đến muộn nhận phản hồi đúng hợp đồng.
- Công việc đã nhận được hoàn tất hoặc hủy đúng chính sách.
- Sau quy trình dừng thành công, bộ thực thi thực sự đã terminated.
- Tài nguyên phụ thuộc chỉ được đóng tại mốc thích hợp.

Dùng chốt hoặc `Future` để tạo các mốc kiểm chứng; không suy luận “ngủ 100 ms chắc đã dừng”. Kiểm tra lỗi tác vụ riêng với kiểm tra kết thúc bộ thực thi: terminated không chứng minh mọi tác vụ thành công.

Khi đọc một lớp có trường `ExecutorService`, hãy tìm câu trả lời cho hai câu hỏi: **lớp này sở hữu hay mượn**, và **ai chịu trách nhiệm khi còn công việc vào lúc đóng**. Nếu chưa trả lời được, hợp đồng vòng đời vẫn còn thiếu dù mã đã biên dịch.
