# Ranh giới giữa sử dụng công cụ có sẵn và tự xây bộ đồng bộ

## 1. Bắt đầu từ quy tắc cần bảo đảm

Một bộ đồng bộ (synchronizer) phối hợp các luồng theo một giao thức: ai được đi tiếp, ai phải chờ, điều kiện nào kết thúc chờ, và dữ liệu được nhìn thấy giữa các luồng như thế nào. Khi gặp yêu cầu đa luồng, câu hỏi đầu tiên là **quy tắc nào cần được bảo đảm**, rồi mới chọn lớp hoặc cơ chế.

Ví dụ “chỉ một người sửa số dư”, “tối đa bốn tác vụ đang gọi dịch vụ ngoài” và “chờ ba bước khởi tạo hoàn tất” đều có việc chờ, nhưng là ba giao thức khác nhau. Một khóa bảo vệ thao tác cập nhật; một bộ giấy phép giới hạn mức đồng thời; một cổng đếm chờ các sự kiện hoàn tất. Chọn theo việc “có nhiều luồng” sẽ dễ dùng sai công cụ.

`AQS` và `LockSupport` giúp hiểu cách công cụ đồng bộ được xây dựng. Biết chúng không có nghĩa mọi bài toán nên bắt đầu bằng cách viết một khóa mới. Một lớp nghiệp vụ có tên riêng vẫn có thể dùng các công cụ thư viện bên trong và cung cấp đúng hợp đồng mà ứng dụng cần.

Bài học tập trung vào những lựa chọn còn áp dụng trên Java hiện hành; ví dụ dùng Java 17 trở lên. Không dựa vào cơ chế điều khiển luồng cũ hoặc mẹo tối ưu theo một phiên bản JDK đã qua.

## 2. Ba mức thiết kế cần phân biệt

| Mức | Công việc chính | Ví dụ |
| --- | --- | --- |
| Sử dụng trực tiếp | Áp đúng hợp đồng của công cụ đã có | Dùng `CountDownLatch` chờ khởi tạo |
| Kết hợp và đóng gói | Dùng công cụ đã có, thêm quy tắc nghiệp vụ và API dễ dùng | Lớp giới hạn số tác vụ đang chạy dùng `Semaphore` |
| Xây bộ đồng bộ mới | Tự định nghĩa giao thức cấp/nhả quyền và tiến trình chờ | Lớp `Sync` kế thừa AQS cho một giao thức chưa có công cụ phù hợp |

Ranh giới nằm ở **trách nhiệm về giao thức đồng bộ**, không nằm ở tên lớp. Viết `UploadGate` bọc một `Semaphore` là đóng gói. Tự giữ trạng thái nguyên tử, hàng đợi người chờ, ngắt và đánh thức là xây công cụ đồng bộ, dù toàn bộ mã chỉ vài chục dòng.

Ưu tiên mức ít trách nhiệm hơn khi nó đã đáp ứng đúng yêu cầu. Đây là một quyết định kỹ thuật: giảm số tình huống cạnh tranh mà nhóm phải tự chứng minh và bảo trì.

## 3. Viết đặc tả trước khi chọn công cụ

Một đặc tả ngắn nên trả lời được các câu hỏi sau:

1. **Bất biến:** điều gì không được sai dù các luồng xen kẽ thế nào? Ví dụ số tác vụ đã nhận quyền và chưa trả quyền không vượt bốn.
2. **Đơn vị quyền:** quyền thuộc một luồng, một tác vụ, một đối tượng tài nguyên hay một giai đoạn công việc?
3. **Vòng đời:** dùng một lần hay tái sử dụng; có đóng, đặt lại, thay đổi giới hạn hay chuyển thế hệ không?
4. **Chờ:** chờ vô hạn, chờ có thời hạn hay từ chối ngay; bị ngắt thì xử lý thế nào?
5. **Dữ liệu:** thao tác nào công bố dữ liệu; thao tác nào nhận quyền đọc dữ liệu đã công bố?
6. **Tiến trình:** trong các giả thiết hợp lệ, ai có trách nhiệm nhả quyền hoặc tạo sự kiện để người chờ tiếp tục?
7. **Phạm vi:** các luồng dùng cùng một đối tượng trong cùng JVM, hay yêu cầu phải có hiệu lực trên nhiều tiến trình/máy?

Không cần viết một luận văn cho mỗi khóa. Nhưng câu “chờ cho đến khi xong” chưa đủ: nếu tác vụ thất bại hoặc bị hủy, ai báo xong; có cần truyền lỗi; có được chờ lại lần sau không? Khi đặc tả còn mơ hồ, viết AQS sẽ biến sự mơ hồ đó thành lỗi khó quan sát.

## 4. Bản đồ nhu cầu và công cụ thư viện

| Nhu cầu | Điểm bắt đầu phù hợp | Câu hỏi cần xác minh |
| --- | --- | --- |
| Bảo vệ nhiều thao tác trên trạng thái dùng chung | `synchronized` hoặc `ReentrantLock` | Có cần lấy khóa có thời hạn, có thể ngắt, hoặc nhiều điều kiện chờ không? |
| Giới hạn số hoạt động cùng diễn ra | `Semaphore` | Mỗi hoạt động lấy/trả bao nhiêu giấy phép, và giữ trong bao lâu? |
| Chờ N sự kiện hoàn tất, một lần | `CountDownLatch` | Đếm sự kiện nào, đường lỗi có báo hoàn tất không? |
| Nhiều bên gặp nhau theo từng vòng | `CyclicBarrier` hoặc `Phaser` | Số bên có cố định không, khi một bên lỗi thì các bên khác xử lý ra sao? |
| Truyền công việc giữa bên tạo và bên xử lý | `BlockingQueue` thích hợp | Có giới hạn dung lượng và chính sách khi đầy không? |
| Nhận kết quả hoặc lỗi của một tác vụ | `Future` hoặc `CompletableFuture` theo cách dùng | Có thật sự cần chặn luồng, hay có thể nối bước xử lý? |
| Cập nhật nguyên tử một giá trị đơn | Các lớp nguyên tử phù hợp | Bất biến có thật sự chỉ nằm trong một giá trị không? |

Đây là bản đồ khởi đầu, không phải phép thay thế tùy ý giữa các lớp. Gói `java.util.concurrent` cung cấp các nhóm công cụ với hợp đồng khác nhau về công việc, hàng đợi, sự kiện và đồng bộ. [Tổng quan java.util.concurrent](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/package-summary.html)

Ví dụ `CountDownLatch` không đặt lại số đếm sau khi về không; dùng nó cho nhiều vòng cần một thiết kế khác. Một `Semaphore(1)` không tự có quy tắc chủ sở hữu như một khóa. Trường `volatile` giúp quan sát trạng thái nhưng không tự biến chuỗi kiểm tra–tính–ghi thành thao tác nguyên tử. [Vòng đời CountDownLatch](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/CountDownLatch.html), [Giấy phép và sở hữu trong Semaphore](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/Semaphore.html)

`synchronized` vẫn là lựa chọn hiện hành cho bảo vệ vùng cập nhật phù hợp. Chọn `ReentrantLock` khi hợp đồng cần tính năng của nó, không vì cho rằng cú pháp ngắn hơn/cũ hơn đồng nghĩa đã lỗi thời. Tương tự, cơ chế đọc nhiều–ghi ít chỉ đáng cân nhắc sau khi hiểu dữ liệu và mức cạnh tranh; tên công cụ không chứng minh nó nhanh hơn trong tải thực tế.

## 5. Minh chứng: lớp nghiệp vụ dùng Semaphore

Yêu cầu cụ thể: một đối tượng cổng cho phép tối đa `limit` lời gọi **đồng bộ** chạy phần công việc của mình cùng lúc. Bên gọi có thể chờ một khoảng để lấy quyền; hết thời gian thì công việc không được chạy. Nếu công việc ném ngoại lệ, quyền vẫn phải được trả. Nếu bị ngắt khi chờ, truyền `InterruptedException` ra ngoài và không trả giấy phép mà mình chưa lấy.

Đặc tả này khớp với việc lấy/trả giấy phép của `Semaphore`. Ta cần lớp bao để đóng gói đúng cặp thao tác, chưa cần trạng thái hay hàng đợi mới.

Lưu thành `ExistingToolBoundaryDemo.java`:

```java
import java.util.Objects;
import java.util.concurrent.Semaphore;
import java.util.concurrent.TimeUnit;

public class ExistingToolBoundaryDemo {
    static final class ConcurrencyGate {
        private final Semaphore permits;

        ConcurrencyGate(int limit) {
            if (limit <= 0) {
                throw new IllegalArgumentException("limit must be positive");
            }
            permits = new Semaphore(limit);
        }

        boolean tryRun(long timeout, TimeUnit unit, Runnable action)
                throws InterruptedException {
            Objects.requireNonNull(unit, "unit");
            Objects.requireNonNull(action, "action");
            if (!permits.tryAcquire(timeout, unit)) {
                return false;
            }
            try {
                action.run();
                return true;
            } finally {
                permits.release();
            }
        }
    }

    public static void main(String[] args) throws InterruptedException {
        ConcurrencyGate gate = new ConcurrencyGate(1);
        int[] executions = {0};

        try {
            gate.tryRun(0, TimeUnit.NANOSECONDS, () -> {
                try {
                    boolean nested = gate.tryRun(
                            0, TimeUnit.NANOSECONDS, () -> executions[0]++);
                    System.out.println("nested=" + nested);
                } catch (InterruptedException exception) {
                    Thread.currentThread().interrupt();
                    throw new IllegalStateException(exception);
                }
                throw new IllegalStateException("demo failure");
            });
        } catch (IllegalStateException expected) {
            System.out.println("actionFailure=propagated");
        }

        boolean afterFailure = gate.tryRun(
                0, TimeUnit.NANOSECONDS, () -> executions[0]++);
        System.out.println("afterFailure=" + afterFailure);
        System.out.println("executions=" + executions[0]);

        Thread.currentThread().interrupt();
        try {
            gate.tryRun(0, TimeUnit.NANOSECONDS, () -> executions[0]++);
        } catch (InterruptedException expected) {
            System.out.println("interrupt=propagated");
        }
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```shell
javac ExistingToolBoundaryDemo.java
java ExistingToolBoundaryDemo
```

Stdout:

```text
nested=false
actionFailure=propagated
afterFailure=true
executions=1
interrupt=propagated
```

### Vì sao dùng phép gọi lồng trong ví dụ?

Cổng có một giấy phép. Công việc bên ngoài đang giữ giấy phép rồi thử nhận thêm quyền với thời gian chờ `0`. Lần gọi lồng trả `false`, nên công việc bên trong không chạy. Ví dụ cố ý kiểm tra tình trạng hết quyền mà không phụ thuộc tốc độ bộ lập lịch hoặc các lệnh `sleep`.

Đây không phải khóa tái nhập: một công việc đang chạy không được tự nhận lại giấy phép chỉ vì dùng cùng luồng. Nếu đổi lần gọi lồng thành chờ vô hạn khi giới hạn là một, nó có thể tự đợi giấy phép đang do chính mình giữ. Hợp đồng cần làm rõ cách sử dụng đó trước khi đưa API cho ứng dụng.

### Vì sao sau lỗi vẫn chạy được?

Phần `action.run()` nằm trong `try/finally` **sau khi** lấy giấy phép thành công. Vì thế ngoại lệ từ công việc truyền ra ngoài nhưng giấy phép vẫn được trả. Lần gọi sau in `afterFailure=true`, và đúng một công việc tăng `executions` đã chạy.

Nếu `tryAcquire` trả `false` hoặc ném `InterruptedException`, chương trình chưa vào khối `try/finally` trả quyền. Nhờ vậy không có lần `release` thừa do một yêu cầu chưa được cấp quyền. Các quy tắc chờ/ngắt cụ thể được cung cấp bởi `Semaphore`; lớp bao dùng chúng thay vì tự dựng hàng chờ. [Các thao tác lấy giấy phép Semaphore](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/Semaphore.html)

`executions` trong chương trình chỉ được thay đổi trên luồng chính. Nó giúp quan sát những công việc nào đã chạy, không phải mẫu bộ đếm an toàn cho nhiều luồng. Khi dùng cổng với giới hạn lớn hơn một và dữ liệu dùng chung, dữ liệu ấy vẫn cần cơ chế bảo vệ riêng phù hợp.

## 6. Công cụ thư viện không thay thế đặc tả nghiệp vụ

Lớp bao trên còn có những ranh giới rõ ràng:

- **Giới hạn đồng thời, không giới hạn số lần mỗi giây.** Một công việc hoàn tất nhanh trả giấy phép ngay; cùng một giấy phép có thể phục vụ nhiều công việc trong một giây. Yêu cầu tốc độ theo thời gian cần thuật toán giới hạn tốc độ riêng hoặc công cụ thích hợp.
- **Thời hạn lấy quyền, không phải thời hạn chạy công việc.** Đối số `timeout` chỉ được chuyển cho thao tác chờ giấy phép. Sau khi nhận quyền, `action.run()` có thể chạy lâu hơn khoảng đó. Cần chính sách khác nếu muốn quản lý thời hạn của bản thân công việc.
- **Vòng đời đồng bộ.** Nếu action chỉ khởi động một thao tác bất đồng bộ rồi trở về ngay, giấy phép được trả trước khi thao tác ấy thực sự xong. Muốn giới hạn thao tác bất đồng bộ, phải giữ quyền đến lúc kết quả hoàn tất, xử lý cả lỗi và hủy, và tránh trả hai lần.
- **Một đối tượng dùng chung.** Nếu mỗi yêu cầu tự tạo `new ConcurrencyGate(4)`, các yêu cầu không chia sẻ cùng giới hạn. Các tiến trình/JVM khác nhau cũng không chia sẻ giấy phép của đối tượng Java này.
- **Không tự bảo vệ mọi trạng thái bên trong công việc.** Cho phép bốn hoạt động cùng chạy có nghĩa vẫn có thể có bốn luồng cùng sửa một cấu trúc dữ liệu. Giới hạn dung lượng và bảo vệ tính nhất quán là hai yêu cầu khác nhau.

Các thiếu sót ở mức nghiệp vụ này thường được sửa bằng vòng đời và cách kết hợp công cụ. Chúng không tự trở thành lý do phải bỏ `Semaphore` để viết AQS. Ví dụ đổi “cấp quyền cho lời gọi đồng bộ” thành “cấp quyền đến lúc một kết quả bất đồng bộ hoàn tất” trước hết đòi hỏi API và cơ chế trả quyền đúng vòng đời.

## 7. Khi nào đủ lý do cân nhắc bộ đồng bộ mới?

Có thể cân nhắc khi đã đặc tả một giao thức cụ thể, đã kiểm tra công cụ sẵn có và cách kết hợp đơn giản, nhưng vẫn có khoảng trống về ngữ nghĩa hoặc một giới hạn đã được đo. Ví dụ giả định: mỗi yêu cầu có trọng số, tài nguyên có nhiều giai đoạn đóng/mở, và một quy tắc cấp quyền nguyên tử đặc biệt mà việc ghép rời nhiều công cụ không giữ được bất biến. Phải chỉ ra chính xác khoảng trống ấy, không chỉ gọi nó là “nghiệp vụ đặc biệt”.

Trước khi xây mới, cần có:

1. Bảng trạng thái hợp lệ và các phép chuyển.
2. Điểm mà một yêu cầu được coi là đã nhận quyền.
3. Quy tắc nhả, hủy, hết thời gian, đóng và tái sử dụng nếu có.
4. Quan hệ đồng bộ bảo đảm dữ liệu nhìn thấy đúng giữa các bên.
5. Lập luận vì sao người chờ không bị bỏ quên trong các tình huống cạnh tranh hợp lệ.
6. Kế hoạch kiểm chứng và người chịu trách nhiệm bảo trì.

“Tự viết sẽ nhanh hơn”, “đã học CAS” hoặc “chỉ có vài dòng park/unpark” chưa phải bằng chứng. Nếu mục tiêu là học, có thể xây bản thực nghiệm với phạm vi rõ ràng và so sánh hành vi. Nếu mục tiêu là dùng trong sản phẩm, trách nhiệm bao gồm cả những trường hợp không xuất hiện trong một lần chạy thuận lợi.

## 8. Chọn AQS hay trực tiếp dùng LockSupport?

**AQS** phù hợp với nhiều bộ đồng bộ có thể diễn đạt việc lấy/nhả bằng một trạng thái `int`, ở chế độ độc quyền, chia sẻ hoặc kết hợp phù hợp. Lớp con cung cấp quy tắc qua các hook; khung AQS đảm nhiệm phần xếp hàng và các đường chờ. Nếu cần trạng thái rộng hơn, thư viện có biến thể `AbstractQueuedLongSynchronizer`; cần đánh giá mô hình trước khi tự hạ xuống tầng thấp hơn. [Phạm vi và cách mở rộng AQS](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/locks/AbstractQueuedSynchronizer.html)

**LockSupport** là thao tác tạm chờ/đánh thức theo luồng. Khi dùng trực tiếp, người viết phải phối hợp trạng thái có đồng bộ, đăng ký người chờ, kiểm tra lại điều kiện, xử lý ngắt và thời hạn. Một giấy phép không cộng dồn và park có thể tự trở về; những điểm này là một phần giao thức phải xử lý. [Phạm vi LockSupport](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/locks/LockSupport.html)

Không coi hai lựa chọn này là hai kiểu viết tương đương. AQS giúp tái sử dụng một phần giao thức; dùng `LockSupport` trực tiếp nghĩa là tự chịu thêm trách nhiệm. Khi bài toán nằm ngoài mô hình AQS, trước tiên giải thích phần nào nằm ngoài và vì sao các công cụ khác chưa đáp ứng, rồi mới chọn tầng triển khai.

Cũng không cần đọc tên trường riêng rồi sao chép mã hàng đợi của một JDK cũ. Hợp đồng mở rộng công khai và đặc tả giao thức là cơ sở duy trì tương thích; chi tiết triển khai có thể thay đổi giữa các phiên bản.

## 9. Bằng chứng cần mạnh đến đâu?

Tách bốn câu hỏi khi đánh giá:

| Câu hỏi | Ví dụ bằng chứng phù hợp |
| --- | --- |
| API có đúng với đặc tả không? | Kiểm thử thành công, thất bại, tham số sai, lỗi công việc và vòng đời |
| Có giữ bất biến khi cạnh tranh không? | Phân tích điểm cấp quyền, các cách xen kẽ và kiểm thử đồng thời có điều phối |
| Có tiếp tục tiến lên được không? | Các trường hợp nhả/hủy/hết thời hạn đúng lúc người khác bắt đầu chờ; giới hạn thời gian phát hiện treo |
| Có đạt mục tiêu hiệu năng không? | Đo tải đại diện, mức cạnh tranh, độ trễ, thông lượng, CPU và bộ nhớ |

Đừng dùng `sleep(100)` như bằng chứng một luồng chắc chắn đã đến đúng vị trí. Có thể dùng latch/barrier trong phép thử để điều phối các mốc đã định nghĩa, đồng thời hiểu chúng có thể tạo quan hệ đồng bộ và ảnh hưởng cách đo. Không đưa công cụ đo vào giữa đoạn cần đo rồi coi kết quả vẫn đại diện nguyên vẹn cho sản phẩm.

`jcstress` của OpenJDK hỗ trợ các phép kiểm tra cạnh tranh và hành vi bộ nhớ; `JMH` hỗ trợ xây và chạy benchmark trên JVM. Chúng phục vụ những câu hỏi khác nhau. Một bộ đồng bộ sai không trở thành đúng vì benchmark nhanh; chạy stress không thấy lỗi cũng không chứng minh mọi cách xen kẽ đều đúng. [OpenJDK jcstress](https://github.com/openjdk/jcstress), [OpenJDK JMH](https://github.com/openjdk/jmh)

Đối chiếu với phương án thư viện trong cùng điều kiện: số luồng, thời gian giữ quyền, tỉ lệ chờ, kiểu công việc, JDK và phần cứng. Một kết quả ít cạnh tranh không đủ dự đoán tình trạng nhiều người chờ; thông lượng cao hơn cũng có thể đi kèm độ trễ chờ tệ hơn. Chỉ nhận mục tiêu hiệu năng mà dữ liệu thực tế đã hỗ trợ.

## 10. Những tình huống dễ chọn sai tầng

| Tình huống | Hướng xử lý ban đầu |
| --- | --- |
| Cần chờ tải cấu hình một lần | Xem xét latch hoặc kết quả tác vụ; đừng tự viết hàng chờ |
| Đang dùng khóa nhưng số liệu bị sai | Kiểm tra mọi đường đọc/ghi có dùng cùng khóa, vùng bảo vệ và vòng đời |
| Đang dùng semaphore nhưng giấy phép tăng vô lý | Kiểm tra release thừa, đường bị ngắt và action bất đồng bộ trả quyền sớm |
| Chương trình treo khi tải cao | Xác định người giữ quyền, thứ tự khóa, tác vụ có chặn nhau và ai phải nhả; chưa kết luận cần khóa mới |
| Cần công bằng | Đọc đúng hợp đồng của công cụ và từng biến thể API; không đồng nhất FIFO với thứ tự CPU chạy |
| Cần khóa giữa nhiều máy | Chọn một cơ chế phối hợp liên tiến trình/phân tán phù hợp; AQS trong một JVM không cung cấp phạm vi đó |
| Chỉ thiếu tên API theo nghiệp vụ | Viết lớp bao nhỏ, giữ kín công cụ đồng bộ bên trong |

Kiểm tra lỗi sử dụng trước khi thay nền tảng. Một lỗi do chờ cùng tài nguyên mà chính mình đang giữ có thể vẫn tồn tại sau khi đổi từ `ReentrantLock` sang một khóa AQS tự viết.

## 11. Thực hành ra quyết định

**Tình huống A:** khởi động ba bước rồi cho phép xử lý yêu cầu. Có phải tự xây cổng AQS không? Trước hết xác định cần đếm hoàn tất hay truyền kết quả/lỗi. Nếu chỉ chờ ba tín hiệu một lần, latch có thể khớp; nếu cần kết quả và lỗi, xem mô hình tác vụ. Đường thất bại phải được đặc tả, không để người chờ vô hạn vì thiếu tín hiệu.

**Tình huống B:** tối đa mười lượt tải lên cùng lúc, nhưng tác vụ trả về một kết quả bất đồng bộ. Lớp bao semaphore đồng bộ trong bài chưa đủ: quyền phải theo toàn bộ vòng đời tải lên. Đây là thay đổi cách quản lý quyền, chưa chứng minh cần tự viết cơ chế xếp hàng.

**Tình huống C:** muốn “tự viết khóa để học”. Hợp lý trong thực nghiệm: ghi rõ có tái nhập không, có công bằng/ngắt/thời hạn/Condition không; kiểm tra lỗi và giới hạn. Không gọi nó là thay thế hoàn chỉnh cho khóa thư viện chỉ vì chương trình mẫu tăng bộ đếm đúng.

**Tình huống D:** một thuật toán có phép cấp tài nguyên nguyên tử mà các công cụ đã khảo sát không diễn đạt được. Viết bất biến và bảng chuyển trước; thử mô hình hóa bằng công cụ hiện có; nếu vẫn có khoảng trống, thiết kế bộ đồng bộ mới cùng kế hoạch kiểm chứng. Việc chọn AQS hay LockSupport là bước triển khai sau quyết định đó.
