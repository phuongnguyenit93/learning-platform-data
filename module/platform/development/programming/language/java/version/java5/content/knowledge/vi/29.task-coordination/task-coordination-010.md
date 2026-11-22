# Exchanger và trao đổi dữ liệu giữa hai tác vụ

## 1. Mô hình gặp nhau để đổi dữ liệu

Giả sử một tác vụ tạo dữ liệu vào bộ đệm, còn tác vụ khác xử lý dữ liệu đó. Sau một lượt:

- Bên tạo có bộ đệm đầy và cần một bộ đệm rỗng.
- Bên xử lý có bộ đệm rỗng và cần bộ đệm đầy.

Đây là nhu cầu **trao đổi hai chiều tại một điểm gặp**, thay vì chỉ gửi dữ liệu theo một chiều.

`Exchanger<V>` thuộc `java.util.concurrent` cho phép hai luồng gặp nhau, mỗi bên đưa một giá trị và nhận giá trị của bên còn lại:

```text
Trước khi gặp:
Tác vụ A giữ X
Tác vụ B giữ Y

Trao đổi thành công:
A đưa X ──────────→ B nhận X
A nhận Y ←────────── B đưa Y
```

Bên đến trước chờ đối tác; khi hai bên ghép được với nhau, mỗi bên nhận dữ liệu do đối tác cung cấp. Xem [hợp đồng Exchanger](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Exchanger.html).

Lớp này vẫn được hỗ trợ trên JDK hiện đại. Điểm quan trọng của nó là **ghép cặp và bàn giao**, không phải tạo thêm luồng hoặc tự tổ chức vòng đời tác vụ.

## 2. Đưa một giá trị, nhận một giá trị khác

Hai dạng lời gọi thường dùng:

```java
V received = exchanger.exchange(offered);
V receivedWithTimeout =
        exchanger.exchange(offered, 1, TimeUnit.SECONDS);
```

Đoạn trên chỉ minh họa chữ ký sử dụng; `V` là kiểu dữ liệu của exchanger.

| Tình huống | Kết quả |
| --- | --- |
| Đã có đối tác đang chờ | Hai bên trao đổi và nhận giá trị của nhau |
| Chưa có đối tác | Chờ ở điểm trao đổi |
| Đang chờ bị ngắt | Có thể ném `InterruptedException` |
| Bản có thời hạn chờ hết thời gian | Ném `TimeoutException` |

Không nhầm `exchange` với một hàm sửa đối tượng được đưa vào. **Giá trị trả về** mới là giá trị nhận từ đối tác. Với bộ đệm có thể tái sử dụng, cách viết thường là:

```java
buffer = exchanger.exchange(buffer);
```

Gọi rồi bỏ qua giá trị trả về sẽ không cập nhật biến `buffer` thành bộ đệm mới nhận.

Exchanger trao đổi giá trị tham chiếu, không sao chép sâu nội dung và không tự gọi `clear()` hoặc biến đổi dữ liệu.

## 3. Vì sao mô hình hai bộ đệm hữu ích?

Gọi X và Y là hai đối tượng bộ đệm khác nhau:

```text
Lượt 1:
Bên tạo:    điền X → đổi X lấy Y
Bên xử lý:         đổi Y lấy X → xử lý X → làm rỗng X

Lượt 2:
Bên tạo:    điền Y → đổi Y lấy X
Bên xử lý:         đổi X lấy Y → xử lý Y → làm rỗng Y
```

Trong lúc bên xử lý đọc X, bên tạo có thể điền Y. Đến lần trao đổi tiếp theo, bên tạo chờ nếu bên xử lý chưa xong và ngược lại.

Điểm lợi là hai đối tượng được dùng luân phiên. Chương trình có thể giảm việc tạo bộ đệm mới theo từng lượt, nhưng hiệu quả thực tế còn phụ thuộc kích thước dữ liệu, thời gian tính và mức cân bằng giữa hai bên.

Không phải mọi bài toán tạo/xử lý dữ liệu đều hợp với nhịp gặp nhau này. Nếu bên tạo cần đi trước nhiều phần dữ liệu hoặc có nhiều bên xử lý độc lập, một hàng đợi có dung lượng phù hợp có thể diễn đạt bài toán tốt hơn.

## 4. Ví dụ đầy đủ: đổi bộ đệm đầy lấy bộ đệm rỗng

Chương trình có hai tác vụ và hai `ArrayList<Integer>` được tạo riêng:

- Bên tạo điền hai số vào bộ đệm.
- Hai bên trao đổi bộ đệm.
- Bên xử lý tính tổng rồi làm rỗng bộ đệm vừa nhận.
- Hai bên lặp lại đúng hai lượt.

Tệp `ExchangerBufferDemo.java`, chạy trên JDK 17 trở lên:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.Exchanger;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class ExchangerBufferDemo {
    public static void main(String[] args)
            throws InterruptedException, ExecutionException {
        Exchanger<List<Integer>> handoff = new Exchanger<>();
        ExecutorService pool = Executors.newFixedThreadPool(2);

        try {
            Future<Void> producer = pool.submit(() -> {
                List<Integer> buffer = new ArrayList<>();
                for (int round = 1; round <= 2; round++) {
                    buffer.add(round * 10);
                    buffer.add(round * 10 + 1);
                    buffer = handoff.exchange(buffer, 5, TimeUnit.SECONDS);
                }
                return null;
            });

            Future<List<Integer>> consumer = pool.submit(() -> {
                List<Integer> buffer = new ArrayList<>();
                List<Integer> sums = new ArrayList<>();
                for (int round = 1; round <= 2; round++) {
                    buffer = handoff.exchange(buffer, 5, TimeUnit.SECONDS);
                    int sum = 0;
                    for (int value : buffer) {
                        sum += value;
                    }
                    sums.add(sum);
                    buffer.clear();
                }
                return sums;
            });

            producer.get();
            List<Integer> sums = consumer.get();
            System.out.println("round1=" + sums.get(0));
            System.out.println("round2=" + sums.get(1));
            System.out.println("total=" + (sums.get(0) + sums.get(1)));
        } finally {
            pool.shutdownNow();
        }
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 ExchangerBufferDemo.java
java ExchangerBufferDemo
```

Kết quả khi hai lượt trao đổi hoàn tất trong thời hạn:

```text
round1=21
round2=41
total=62
```

Lượt 1 đưa các số 10 và 11 nên tổng là 21. Lượt 2 đưa 20 và 21 nên tổng là 41.

Nhóm thực thi có hai luồng để cả hai tác vụ có khả năng đến điểm trao đổi. Mỗi bên tự tạo bộ đệm ban đầu nên không có việc chúng cùng bắt đầu với một `ArrayList`.

Biến `sums` chỉ thuộc bên xử lý cho đến khi tác vụ đó hoàn tất. Luồng chính lấy danh sách kết quả qua `Future.get()`, rồi in theo thứ tự lượt; thứ tự lập lịch không làm đảo các dòng kết quả.

Các ngoại lệ trong tác vụ, gồm timeout và ngắt khi trao đổi, được chuyển tới `Future`. `main` nhận lỗi qua `ExecutionException`, còn `finally` yêu cầu nhóm thực thi dừng. Đây là chương trình minh họa hữu hạn; tác vụ dài trong hệ thống thực tế cần thêm chính sách dừng và quản lý tài nguyên.

## 5. Giao thức sở hữu dữ liệu mới là điều bảo vệ bộ đệm

Dùng `Exchanger` không tự biến `ArrayList` thành một cấu trúc có thể sửa đồng thời tùy ý. Ví dụ an toàn nhờ giao thức:

1. Trước khi trao đổi, mỗi bên chỉ sửa bộ đệm mình đang giữ.
2. Khi đã đưa bộ đệm vào một lần trao đổi, không có luồng phụ sửa nó trong lúc chờ.
3. Sau trao đổi thành công, bên gửi ngừng sử dụng bộ đệm đã bàn giao.
4. Bên nhận trở thành bên sử dụng độc quyền cho đến lần bàn giao tiếp.
5. Bên xử lý làm rỗng bộ đệm trước khi đưa nó trở lại.

Một lỗi thường gặp là giữ thêm bí danh của bộ đệm đã gửi:

```java
// Ví dụ sai nếu tiếp tục sửa sent sau trao đổi.
List<Integer> sent = buffer;
buffer = exchanger.exchange(buffer);
sent.clear();
```

`sent` vẫn trỏ đến bộ đệm vừa giao cho đối tác. Gọi `clear()` qua bí danh đó có thể phá dữ liệu mà bên kia đang đọc.

Tương tự, nếu hai bên cùng đưa **chính một đối tượng dùng chung** vào exchanger, việc trao đổi không tạo ra hai vùng dữ liệu độc lập. Cần xác lập quyền sử dụng từ trước, không chỉ thêm một lời gọi đồng bộ.

Quyền sử dụng độc quyền ở đây là quy ước của thiết kế, không phải quyền sở hữu được Java kiểm tra ở mức kiểu.

## 6. Dữ liệu ghi trước trao đổi được công bố thế nào?

Với một cặp trao đổi thành công, hành động trước `exchange()` ở mỗi bên có quan hệ **xảy ra trước (happens-before)** với hành động sau lần `exchange()` tương ứng trở về ở bên đối tác. Xem phần Memory consistency effects của [Exchanger](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Exchanger.html).

```text
Bên tạo điền bộ đệm X
    ↓
Bên tạo exchange(X)
    ↓ happens-before
Bên xử lý exchange(Y) nhận X
    ↓
Bên xử lý đọc nội dung X
```

Quan hệ theo chiều ngược lại cũng quan trọng: bên xử lý làm rỗng bộ đệm trước khi đưa nó vào lượt đổi tiếp theo; bên tạo nhận được bộ đệm đã làm rỗng sau lượt trao đổi thành công.

Đó là lý do ví dụ có thể bàn giao dữ liệu mà không cần đồng bộ hóa riêng từng lần `add()` hoặc `clear()`, miễn là giữ đúng quyền sử dụng một bên tại một thời điểm.

Nhưng bảo đảm công bố không bao phủ những lần sửa diễn ra **sau khi đã giao dữ liệu** mà bên gửi vẫn cố thực hiện. Exchanger tạo ranh giới bàn giao; nó không khóa đối tượng mãi sau ranh giới đó.

## 7. Timeout và ngắt không phải là dữ liệu phản hồi

Phiên bản có thời hạn hữu ích khi đối tác có thể không đến:

```java
// Mã minh họa trong phương thức xử lý InterruptedException.
try {
    buffer = exchanger.exchange(buffer, 500, TimeUnit.MILLISECONDS);
    processReceivedBuffer(buffer);
} catch (TimeoutException timeout) {
    reportMissingPartner();
}
```

Nếu có timeout, lời gọi không trả về một bộ đệm đối tác để xử lý. Không được tiếp tục như thể `buffer` đã được thay bằng dữ liệu mới. Phép gán chỉ xảy ra nếu lời gọi trả về bình thường.

Thời hạn là thời gian chờ ghép đối tác, không phải thời hạn để đối tác xử lý xong dữ liệu. Một lần trao đổi thành công cũng chưa chứng minh bên nhận đã đọc hoặc ghi dữ liệu xuống hệ thống bên ngoài.

Khi bắt `InterruptedException` tại chỗ mà không chuyển tiếp, thông thường cần khôi phục cờ ngắt rồi kết thúc nhánh công việc:

```java
// Mã minh họa trong một tác vụ Runnable.
try {
    buffer = exchanger.exchange(buffer);
} catch (InterruptedException interrupted) {
    Thread.currentThread().interrupt();
    return;
}
```

Không bắt lỗi rồi lập tức lặp lại vô hạn nếu đối tác đã chết hoặc đã dừng. Việc thử lại cần gắn với chính sách phiên làm việc, số lượt và trách nhiệm tài nguyên còn giữ.

Exchanger không có trạng thái “broken” chung giống một barrier hỏng, cũng không có `close()` để tự báo cho bên còn lại rằng đối tác đã dừng. Khi một bên lỗi, bên kia có thể vẫn đang tính hoặc sẽ chờ ở lượt sau. Cần timeout, ngắt hoặc tín hiệu kết thúc ở cấp ứng dụng.

## 8. Giữ hai bên cùng hiểu một lượt trao đổi

Exchanger không biết lượt thứ nhất nghĩa là “bộ đệm dữ liệu” và lượt thứ hai nghĩa là “xác nhận”. Nó chỉ ghép các lời gọi tương thích đang gặp nhau trên cùng đối tượng exchanger.

Trong giao thức hai bên cố định, cần thống nhất:

- Cùng số lượt, hoặc cùng một quy tắc kết thúc.
- Mỗi lượt đưa loại dữ liệu nào.
- Khi lỗi, có thử lại lượt đó hay dừng toàn bộ phiên.
- Bộ đệm nào đang được phép sửa.
- Mốc nào biểu diễn dữ liệu đã nhận và mốc nào biểu diễn xử lý đã xong.

Nếu cần truyền danh tính lượt, có thể bọc dữ liệu trong một kiểu thông điệp chứa số thứ tự, loại thông điệp và nội dung. Exchanger không tự kiểm tra các trường này; bên nhận phải xác minh theo giao thức.

Cũng không dùng `null` hoặc một giá trị đặc biệt làm tín hiệu kết thúc mà không định nghĩa rõ bên kia sẽ phản ứng thế nào. Với dữ liệu nghiệp vụ có thể trùng giá trị đó, nên có kiểu thông điệp phân biệt dữ liệu với lệnh dừng.

## 9. Nhiều hơn hai luồng không tạo thành một cuộc trao đổi nhóm

Một `Exchanger` có thể được nhiều luồng gọi, nhưng mỗi lần trao đổi thành công vẫn là **một cặp**. Không có bảo đảm “A luôn gặp B” chỉ vì hai luồng được đặt tên như vậy.

Nếu A, B và C cùng dùng một exchanger, A có thể ghép với B còn C tiếp tục chờ. Với bốn bên, chúng có thể ghép thành hai cặp; đó không phải rào đồng bộ chờ cả bốn.

Nếu giao thức chỉ cho phép hai tác vụ cụ thể gặp nhau, hãy cấp đối tượng exchanger riêng cho cặp đó hoặc thiết kế định tuyến ở lớp trên. Không dùng kiểu generic để thay cho việc định tuyến: `Exchanger<Message>` vẫn không biết thông điệp nào dành cho ai.

Exchanger cũng không cung cấp hợp đồng thứ tự công bằng để suy ra lịch ghép cặp cố định theo thứ tự gọi.

## 10. Những vòng chờ cần tránh

### Nhóm thực thi không đủ khả năng chạy cả hai bên

```text
Nhóm thực thi chỉ có 1 luồng
Tác vụ A đang chạy → exchange() chờ B
Tác vụ B đang nằm trong hàng đợi của cùng nhóm
→ B không có chỗ để chạy
```

Không giải quyết bằng cách tăng thời gian chờ. Cần thiết kế đủ tài nguyên thực thi hoặc chuyển sang mô hình không buộc hai bên chiếm chỗ đồng thời tại điểm gặp.

### Giữ khóa mà đối tác cần

Nếu A giữ một khóa rồi chờ exchanger, còn B cần khóa đó để chuẩn bị dữ liệu trước khi exchange, hai bên bị phụ thuộc vòng. Không giữ tài nguyên như vậy qua điểm chờ trừ khi đã chứng minh giao thức không thể tạo chu kỳ.

### Dùng một tác vụ gọi hai lần liên tiếp để “tự trao đổi”

```java
// Ví dụ sai: lời gọi đầu đã chờ, nên chưa đi đến lời gọi thứ hai.
exchanger.exchange(first);
exchanger.exchange(second);
```

Cần có một bên khác thực sự đến trong thời gian chờ. Exchanger không lưu giá trị đầu vào như một hàng đợi để cùng luồng lấy lại ở lời gọi sau.

## 11. Khi nào chọn công cụ khác?

| Nhu cầu | Công cụ đáng xem xét |
| --- | --- |
| Hai tác vụ đổi dữ liệu qua lại tại các điểm gặp | `Exchanger` |
| Một bên giao, bên kia nhận, không cần giá trị trả ngược | `SynchronousQueue` |
| Cần giữ một số phần dữ liệu chờ xử lý | Hàng đợi chặn có dung lượng phù hợp |
| Một nhóm cố định chờ nhau ở cuối nhiều chặng | `CyclicBarrier` |
| Chờ một số tín hiệu hoàn tất, không bàn giao giá trị từng cặp | `CountDownLatch` |

`SynchronousQueue` không có dung lượng lưu trữ nội bộ; đưa dữ liệu phải gặp thao tác nhận tương ứng. Xem [SynchronousQueue](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/SynchronousQueue.html).

Các triển khai `BlockingQueue` có thể có dung lượng để tách nhịp bên tạo và bên xử lý; lựa chọn dung lượng ảnh hưởng lượng dữ liệu chờ và áp lực lên bên tạo. Xem [BlockingQueue](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/BlockingQueue.html).

## 12. Bài tập tự kiểm tra

1. Tăng cả hai vòng lặp lên ba lượt rồi bỏ `buffer.clear()` ở bên xử lý. Ở lượt thứ ba, bên tạo dùng lại bộ đệm từng chứa dữ liệu lượt thứ nhất; dữ liệu cũ còn lại có thể bị cộng chung với dữ liệu mới. Hãy sửa cả phần in kết quả để quan sát lượt thứ ba.
2. Cho bên tạo chạy ba lượt nhưng bên xử lý chỉ chạy hai. Lượt trao đổi thứ ba của bên tạo sẽ không có đối tác; với bản có thời hạn, nó sẽ báo timeout.
3. Đổi nhóm thực thi thành một luồng. Điểm chờ nào ngăn đối tác được chạy? Chính lời gọi `exchange()` của tác vụ được chạy trước.
4. Sau khi trao đổi thành công, bên tạo có được giữ một bí danh rồi sửa bộ đệm vừa gửi không? Không nếu giao thức đã bàn giao quyền sử dụng cho bên xử lý.

Mô hình cần nhớ là **mỗi bên đưa một dữ liệu, nhận dữ liệu đối tác và chuyển quyền sử dụng rõ ràng tại một lần ghép cặp thành công**.
