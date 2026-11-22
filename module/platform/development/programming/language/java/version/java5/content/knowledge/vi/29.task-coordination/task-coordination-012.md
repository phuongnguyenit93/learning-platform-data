# Lựa chọn công cụ phối hợp theo quan hệ giữa các tác vụ

## 1. Vẽ quan hệ trước khi chọn lớp

Hai chương trình cùng có mười luồng có thể cần những công cụ hoàn toàn khác nhau:

- Một chương trình cần đợi mười phần việc kết thúc rồi tổng hợp.
- Một chương trình cần mười bên cùng qua từng vòng tính toán.
- Một chương trình có mười tác vụ nhưng chỉ cho ba tác vụ dùng tài nguyên cùng lúc.
- Một chương trình cần bên tạo dữ liệu giao công việc cho bên xử lý.

Số luồng không mô tả đủ bài toán. Hãy viết quan hệ phụ thuộc bằng câu cụ thể: **ai cần chờ ai, chờ sự kiện gì, có truyền dữ liệu không, và quan hệ đó lặp lại thế nào?**

Công cụ phối hợp không tự làm cho mọi dữ liệu dùng chung an toàn. Sau khi chọn điểm chờ, vẫn phải xác định ai sở hữu dữ liệu trước và sau điểm đó, xử lý lỗi ra sao và lúc nào thu hồi tài nguyên.

Bài tập trung vào các công cụ từ Java 5 vẫn còn dùng trong Java hiện đại; ví dụ chạy trên Java 17 trở lên. Một lựa chọn bổ sung ra đời sau được nhắc rõ khi nhu cầu vượt mô hình nhóm cố định.

## 2. Bản đồ lựa chọn

| Quan hệ cần diễn đạt | Công cụ nên xét trước | Điều nó không tự làm |
| --- | --- | --- |
| Một hoặc nhiều bên đợi đủ N tín hiệu của một đợt | `CountDownLatch` | Mang kết quả, báo lỗi tác vụ hoặc reset |
| Một nhóm cố định chờ nhau ở mỗi vòng | `CyclicBarrier` | Tự xử lý tác vụ bỏ cuộc trước khi tới rào |
| Tối đa K bên đồng thời được vào một khu vực tài nguyên | `Semaphore` | Tự quản lý danh tính tài nguyên hoặc giới hạn tốc độ theo giây |
| Hai bên gặp nhau và đổi dữ liệu cho nhau | `Exchanger` | Phát dữ liệu cho mọi bên hoặc giữ hàng đợi công việc |
| Bên tạo công việc giao cho bên xử lý | `BlockingQueue` | Tự định nghĩa đóng hàng đợi và kết thúc toàn hệ thống |
| Người gọi cần kết quả/lỗi của một phép tính bất đồng bộ | `Future` | Chia giai đoạn cho cả nhóm hoặc bảo đảm tác vụ dừng ngay khi hủy |
| Người gọi cần đợi một luồng cụ thể chấm dứt | `Thread.join` | Trả về kết quả có kiểu của tác vụ |
| Nhiều thao tác cần bảo vệ cùng một bất biến | Khóa hoặc thiết kế trạng thái nguyên tử | Thay thế quan hệ truyền công việc và quản lý vòng đời |

Bảng là điểm bắt đầu. Một quy trình có thể có nhiều quan hệ và dùng hơn một công cụ, nhưng mỗi công cụ cần một vai trò riêng.

## 3. Quan hệ một chiều: “chờ đủ sự kiện”

Ví dụ: tải ba phần cấu hình, sau đó mở dịch vụ.

```text
Tải A ── báo xong ─┐
Tải B ── báo xong ─┼──→ bên điều phối đi tiếp
Tải C ── báo xong ─┘
```

`CountDownLatch(3)` diễn đạt ba tín hiệu của một đợt. Bên báo dùng `countDown()`; bên đợi dùng `await()`. Các bên báo không buộc phải đợi nhau.

Một latch có số đếm một còn có thể làm cổng bắt đầu:

```text
Chuẩn bị dữ liệu → mở cổng → các tác vụ được phép bắt đầu
```

Hai vai trò đó có chiều phụ thuộc khác nhau. Nếu cần cả cổng bắt đầu và báo xong, đặt tên và tạo hai latch riêng.

Chọn latch khi điều cần biểu diễn chính là mốc sự kiện. Nếu người gọi chủ yếu muốn “lấy kết quả của từng phép tính và nhận lỗi của nó”, `Future` thường trực tiếp hơn việc tự tạo mảng kết quả, mảng lỗi và một latch.

Latch không kiểm tra danh tính người báo. Báo hai lần hoặc đặt số đếm quá nhỏ có thể mở chốt sớm. Nếu một tác vụ không bao giờ được chạy thì `finally` bên trong nó cũng không thể gửi tín hiệu; phía tổ chức công việc phải xử lý trường hợp bị từ chối hoặc bị hủy trước khi bắt đầu.

## 4. Quan hệ ngang hàng theo vòng: “không ai sang bước sau một mình”

Ví dụ: mỗi bên cập nhật một vùng của mô phỏng, nhưng vòng tiếp theo cần mọi vùng của vòng hiện tại đã sẵn sàng.

```text
A: tính vòng 1 ─┐             A: tính vòng 2 ─┐
B: tính vòng 1 ─┼─ qua rào ─→ B: tính vòng 2 ─┼─ qua rào
C: tính vòng 1 ─┘             C: tính vòng 2 ─┘
```

`CyclicBarrier` phù hợp với nhóm có số bên cố định. Mỗi bên đến mốc bằng `await()`; đủ bên thì lượt hoàn tất. Barrier action có thể tổng hợp dữ liệu tại ranh giới trước khi các bên đi tiếp.

Dùng latch cho mỗi vòng cũng có thể xây dựng được một giao thức, nhưng phải quản lý latch mới, việc chuyển lượt và đối tượng nào thuộc lượt nào. Nếu mô hình đã là “nhóm chờ nhau lặp lại”, barrier thể hiện ý định rõ hơn.

Cần chính sách lỗi cho cả nhóm: ngắt hoặc hết hạn tại một lời gọi barrier có thể phá lượt và làm các bên khác nhận `BrokenBarrierException`. Một tác vụ lỗi trước khi tới rào lại không được barrier tự phát hiện.

Nếu số bên cần đăng ký hoặc rời nhóm theo thời gian, nhóm cố định không còn mô tả tốt bài toán. Có thể xét `Phaser`, được thêm từ Java 7 và vẫn dùng trong Java hiện đại. Nó cần một giao thức đăng ký/rời nhóm riêng; không nên đưa vào chỉ vì tên có vẻ linh hoạt hơn.

## 5. Quan hệ sức chứa: “được vào nếu còn suất”

Ví dụ: có nhiều tác vụ nhưng chỉ cho hai tác vụ đồng thời sử dụng một bộ xử lý bên ngoài.

```text
Nhiều tác vụ → lấy giấy phép → tối đa 2 tác vụ dùng tài nguyên
                              ↓
                         trả giấy phép
```

`Semaphore(2)` diễn đạt sức chứa. Những tác vụ đang dùng tài nguyên không phải đợi nhau tại một mốc chung; chúng hoàn tất độc lập rồi trả giấy phép.

Không dùng barrier hai bên thay semaphore hai suất. Barrier đợi một nhóm đủ bên gặp nhau; semaphore cho phép từng bên vào khi có suất. Nếu chỉ còn một tác vụ, semaphore vẫn cho nó chạy khi có giấy phép, còn barrier hai bên có thể đợi mãi.

Semaphore chỉ quản lý số lượng giấy phép. Nếu có một danh sách kết nối hoặc thiết bị thực, ứng dụng còn phải lấy/trả đúng đối tượng trong danh sách đó an toàn. Giấy phép không tự chọn tài nguyên.

Một semaphore cũng không phải bộ giới hạn tốc độ theo thời gian: giới hạn “tối đa hai lời gọi đang chạy” khác “không quá hai lời gọi mỗi giây”. Nếu lời gọi kết thúc rất nhanh, số lần mỗi giây vẫn có thể rất lớn.

Khi thứ tự chờ quan trọng, xét chế độ fair và kiểm tra mọi đường lấy giấy phép. `tryAcquire()` không có thời gian chờ cho phép chen ngang cả khi semaphore bật fair.

## 6. Quan hệ trao đổi từng cặp và quan hệ dòng công việc

### Hai bên đổi cho nhau: Exchanger

Ví dụ một bên có bộ đệm đã ghi đầy, bên kia có bộ đệm đã xử lý xong. Mỗi bên muốn giao bộ đệm mình có và nhận bộ đệm từ đối tác.

```text
Bên A mang X ──┐       ┌── A nhận Y
               ├─ đổi ┤
Bên B mang Y ──┘       └── B nhận X
```

`Exchanger<V>` diễn đạt cuộc gặp và trao đổi hai chiều. Hai bên có thể lặp việc trao đổi ở nhiều lần gọi.

Nó không tự gán danh tính đối tác trong một nhóm đông. Nếu nhiều luồng cùng dùng một exchanger, không mặc định A luôn ghép đúng B. Nếu chỉ có một bên tiếp tục trao đổi, bên đó có thể phải đợi đối tác không bao giờ đến.

Sau khi giao một bộ đệm khả biến cho bên kia, bên gửi không nên tiếp tục sửa nó khi chưa nhận lại quyền sử dụng theo giao thức. Trao đổi tham chiếu không tạo bản sao dữ liệu.

### Một hoặc nhiều bên tạo công việc: BlockingQueue

Nếu quan hệ là “tạo các đơn vị công việc rồi cho bên khác lấy xử lý”, hàng đợi thường rõ hơn:

```text
Bên tạo → [công việc chờ] → bên xử lý
```

`BlockingQueue` có thể chờ khi lấy từ hàng rỗng hoặc khi thêm vào hàng có giới hạn đã đầy. Hàng đợi có sức chứa giới hạn tạo áp lực ngược (backpressure): bên tạo không thể tùy ý tích lũy vô hạn công việc.

Một `put` thành công không chứng minh phần việc đã được bên nhận xử lý xong. Nó chỉ xác nhận bước giao vào hàng đợi theo hợp đồng thao tác. Nếu cần đợi kết quả của từng đơn vị, bổ sung cơ chế phản hồi phù hợp.

`BlockingQueue` không có quy tắc đóng chung cho mọi triển khai. Ứng dụng phải chọn cách dừng, chẳng hạn tín hiệu kết thúc hoặc hủy hợp tác; nếu dùng tín hiệu cuối với nhiều bên xử lý, cần tính đủ cách mỗi bên nhận được yêu cầu dừng.

## 7. Quan hệ kết quả và vòng đời: Future, join

`Future<V>` thể hiện kết quả của một phép tính bất đồng bộ. Người gọi có thể chờ bằng `get()`, lấy giá trị, nhận `ExecutionException` khi tác vụ thất bại hoặc nhận trạng thái hủy thích hợp.

Đây là lựa chọn tự nhiên cho bài toán “tách ba phép tính rồi cần ba kết quả”. Không cần tự coi mỗi kết quả là một tín hiệu latch nếu công cụ thực thi đã cung cấp future.

Đặt giới hạn thời gian cho `get` chỉ giới hạn thời gian đợi của lời gọi đó. Nó không tự hủy tác vụ. `cancel(true)` cũng chỉ yêu cầu cơ chế hủy với khả năng ngắt phù hợp, không phải bảo đảm cưỡng bức dừng mọi loại công việc.

`Thread.join()` dành cho việc chờ một luồng cụ thể kết thúc. Một luồng có thể chạy nhiều công việc; kết thúc một công việc trong nhóm thực thi không đồng nghĩa luồng phục vụ công việc đó cũng chấm dứt. Vì vậy không dùng join lên luồng của nhóm thực thi như cách thay cho future của từng tác vụ.

Với nhu cầu xử lý kết quả theo thứ tự hoàn tất, có thể xét công cụ chuyên cho thu nhận hoàn tất, thay vì bắt buộc chờ từng future theo thứ tự nộp. Đó là lựa chọn về cách thu nhận kết quả, khác với việc giới hạn số tác vụ được dùng một tài nguyên.

## 8. Ví dụ chạy được: cổng bắt đầu, giới hạn tài nguyên và mốc tổng hợp

Quy trình sau có ba quan hệ riêng:

1. Ba tác vụ chỉ được làm việc sau khi bên điều phối mở cổng.
2. Trong đoạn dùng tài nguyên, tối đa hai tác vụ được vào.
3. Bên điều phối đợi đủ ba tín hiệu kết thúc rồi kiểm tra lỗi và tổng hợp.

Lưu thành `CoordinationChoiceDemo.java`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Semaphore;

public class CoordinationChoiceDemo {
    public static void main(String[] args) throws InterruptedException {
        int taskCount = 3;
        CountDownLatch start = new CountDownLatch(1);
        CountDownLatch finished = new CountDownLatch(taskCount);
        Semaphore resourceSlots = new Semaphore(2, true);
        int[] results = new int[taskCount];
        Exception[] failures = new Exception[taskCount];

        for (int i = 0; i < taskCount; i++) {
            int index = i;
            Thread task = new Thread(() -> {
                try {
                    start.await();
                    resourceSlots.acquire();
                    try {
                        results[index] = (index + 1) * 10;
                    } finally {
                        resourceSlots.release();
                    }
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                    failures[index] = e;
                } catch (RuntimeException e) {
                    failures[index] = e;
                } finally {
                    finished.countDown();
                }
            });
            task.start();
        }

        start.countDown();
        finished.await();

        for (Exception failure : failures) {
            if (failure != null) {
                throw new IllegalStateException("A task failed", failure);
            }
        }

        int total = 0;
        for (int result : results) {
            total += result;
        }

        System.out.println("tasks=" + taskCount);
        System.out.println("total=" + total);
        System.out.println("availableSlots="
                + resourceSlots.availablePermits());
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```shell
javac --release 17 CoordinationChoiceDemo.java
java CoordinationChoiceDemo
```

Stdout khi các tác vụ chạy bình thường:

```text
tasks=3
total=60
availableSlots=2
```

Những điểm cần đọc đúng:

- `start` không tổng hợp kết quả; nó chỉ cho phép các tác vụ bắt đầu.
- `resourceSlots` không đợi đủ ba tác vụ; nó chỉ giới hạn đoạn giữa acquire và release.
- `finished` không mang kết quả hoặc lỗi; hai mảng là kênh riêng.
- Mỗi tác vụ chỉ ghi phần tử mang chỉ số của mình. Luồng chính đọc sau lần await thành công của `finished`.
- `release` chỉ chạy sau khi acquire thành công. Một ngắt trong lúc lấy giấy phép không tạo ra giấy phép thừa.
- Tín hiệu trong finally có nghĩa “đã kết thúc lần thử”, vì vậy phải kiểm tra mảng lỗi.

Các phép tính rất ngắn nên một lần chạy có thể không thực sự dùng đồng thời đủ hai suất. Ví dụ minh họa cấu trúc giới hạn, không khẳng định đo được mức đồng thời cực đại.

Đây là ví dụ học cách ghép vai trò. Nếu yêu cầu thực tế chỉ là chạy ba phép tính rồi lấy giá trị/lỗi, dùng `ExecutorService` và future thường gọn hơn cách tổ chức thủ công này. Trong ứng dụng còn cần quản lý lỗi khởi chạy, ngắt bên điều phối và vòng đời các tác vụ đang chạy.

## 9. Điểm phối hợp cũng là ranh giới dữ liệu

Việc “một luồng có vẻ đã chạy trước” không thay thế quan hệ công bố bộ nhớ. Mỗi công cụ có hợp đồng tương ứng với quan hệ nó biểu diễn.

Ví dụ:

- Kết quả ghi trước tín hiệu latch được công bố cho bên đi qua await thành công tương ứng.
- Rào thành công phối hợp dữ liệu giữa các bên ở ranh giới lượt, bao gồm action nếu có.
- Một cuộc exchange thành công công bố dữ liệu trước trao đổi cho phía đối tác sau trao đổi.
- Dữ liệu được đặt vào hàng đợi có quan hệ công bố với bên truy cập/lấy phần tử theo hợp đồng.
- Future cho phép bên gọi quan sát kết quả của phép tính qua get.

Đừng mở rộng những bảo đảm đó thành “mọi thay đổi sau này đều an toàn”. Nếu bên tạo tiếp tục sửa một đối tượng sau khi giao nó, có thể xuất hiện truy cập đồng thời mới. Phải quy định đối tượng là bất biến, chuyển quyền sử dụng, hoặc có đồng bộ riêng.

Một latch ở cuối cũng không sửa được việc hai tác vụ đã cùng tăng một biến thường sai cách trước đó. Điều phối mốc và bảo vệ phép cập nhật là hai nhu cầu có liên hệ nhưng khác nhau.

## 10. Lỗi và hủy là một phần của quan hệ phụ thuộc

Trước khi triển khai, hãy hỏi: “nếu một bên không bao giờ tới mốc thì những bên đang đợi sẽ ra sao?”.

| Công cụ | Điểm cần có chính sách riêng |
| --- | --- |
| Latch | Thiếu tín hiệu có thể chờ mãi; đủ tín hiệu không tự chứng minh thành công |
| Barrier | Một lượt có thể bị broken; phải dừng hoặc phục hồi nhóm có điều phối |
| Semaphore | Không trả giấy phép làm giảm sức chứa; trả thừa làm sai giới hạn |
| Exchanger | Đối tác mất hoặc dừng khiến bên còn lại thiếu người ghép |
| Hàng đợi | Bên tạo/bên nhận dừng phải có giao thức kết thúc và xử lý việc còn lại |
| Future | Hết thời gian chờ, lỗi và hủy là các kết quả khác nhau |

Ngoài số bên, còn phải bảo đảm tài nguyên thực thi đủ cho quan hệ chờ. Một nhóm luồng cố định có thể bị chiếm hết bởi các tác vụ đang đợi những tác vụ chưa được chạy trong chính nhóm đó.

Không giữ một khóa cần thiết cho bên khác trong lúc chờ. Không dùng `Thread.sleep` thay cho việc chứng minh một sự kiện đã xảy ra. Không bỏ qua ngắt rồi tiếp tục sử dụng dữ liệu chưa được xác nhận là sẵn sàng.

Nếu công việc liên quan cơ sở dữ liệu hoặc dịch vụ ngoài, các công cụ phối hợp trong JVM không tự tạo giao dịch hay hoàn tác tác dụng phụ bên ngoài.

## 11. Tự luyện lựa chọn

1. Năm tác vụ tính các phần độc lập, người gọi cần giá trị và lỗi của từng phần.
2. Bốn tác vụ mô phỏng cần cùng hoàn tất mỗi vòng trước khi bắt đầu vòng mới.
3. Có một trăm tác vụ nhưng chỉ cho năm tác vụ gọi hệ thống ngoài đồng thời.
4. Hai luồng liên tục đổi bộ đệm đầy và rỗng.
5. Nhiều bên tạo việc cho một nhóm xử lý, cần giới hạn số việc chưa nhận.
6. Một đợt khởi tạo gồm ba sự kiện khác nhau, nhiều người dùng cùng chờ mốc sẵn sàng.

Gợi ý:

1. Future từ cơ chế thực thi tác vụ.
2. CyclicBarrier nếu nhóm cố định; xét Phaser nếu số bên cần thay đổi theo giao thức.
3. Semaphore với vòng đời lấy/trả giấy phép rõ ràng.
4. Exchanger với quy tắc sở hữu bộ đệm.
5. BlockingQueue có giới hạn và giao thức kết thúc.
6. CountDownLatch cùng kênh trạng thái khởi tạo/lỗi.

Chọn công cụ bằng cách mô tả mối quan hệ, rồi kiểm tra dữ liệu, lỗi và vòng đời. Khi mỗi điểm chờ có một ý nghĩa rõ ràng, việc phối hợp trở nên dễ kiểm chứng hơn nhiều so với ghép các lệnh chờ chỉ để đạt thứ tự mong muốn trong một lần chạy.

## Tài liệu đối chiếu

- [CountDownLatch](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/CountDownLatch.html), [CyclicBarrier](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/CyclicBarrier.html), [Semaphore](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/Semaphore.html) — các mô hình mốc, lượt và sức chứa.
- [Exchanger](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/Exchanger.html), [BlockingQueue](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/BlockingQueue.html), [Future](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/Future.html) — trao đổi, truyền việc và kết quả.
- [Phaser](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/Phaser.html) — lựa chọn bổ sung khi số bên tham gia cần thay đổi.
