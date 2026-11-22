# await, countDown và quan hệ bộ nhớ của latch

## 1. Latch vừa phối hợp thời điểm vừa công bố dữ liệu

`CountDownLatch` là chốt đếm dùng một lần. Nó giúp một hoặc nhiều luồng chờ cho đến khi một số sự kiện đã được báo hoàn tất.

Hai thao tác chính là:

- `countDown()`: báo một sự kiện đã đạt tới mốc đã quy ước.
- `await()`: chờ đến khi đủ số lần báo đó.

Ngoài việc chờ, latch còn thiết lập quan hệ bộ nhớ giữa phía báo và phía đợi. Nhờ vậy, dữ liệu được tạo **trước khi báo** có thể được phía đợi sử dụng an toàn **sau khi chờ thành công**, nếu toàn bộ giao thức truy cập dữ liệu cũng đúng.

Ví dụ điển hình: chia phép tính thành hai tác vụ, mỗi tác vụ ghi một phần kết quả, rồi luồng tổng hợp đợi cả hai phần trước khi cộng.

API này được giới thiệu từ Java 5 và vẫn còn phù hợp trong Java hiện đại. Những ví dụ dưới đây chạy trên Java 17 trở lên và không dựa vào ngủ một khoảng thời gian để đoán tác vụ đã xong.

## 2. Vòng đời của bộ đếm

```java
CountDownLatch done = new CountDownLatch(2);
```

Diễn biến thông thường:

```text
count = 2
    countDown()
count = 1
    countDown()
count = 0  → mở chốt
```

Mỗi lần `countDown()` khi bộ đếm còn dương làm nó giảm một. Lời gọi khiến bộ đếm về không mở chốt cho tất cả các luồng đang đợi. Chúng trở lại trạng thái có thể được lập lịch; không có cam kết mọi luồng sẽ chạy ngay lập tức hay theo thứ tự gọi `await`.

Một số tính chất cần phân biệt:

- `countDown()` không chờ các bên khác giảm tiếp bộ đếm.
- Latch đếm **lần báo**, không đăng ký danh tính luồng. Một luồng có thể báo nhiều lần nếu mã cho phép.
- Sau khi về không, các lần giảm tiếp không có tác dụng.
- Chốt không đóng lại và không có thao tác reset.
- Khởi tạo bằng không tạo chốt đã mở; số âm bị từ chối bằng `IllegalArgumentException`.

Vì latch không tự biết công việc nào tương ứng mỗi lần giảm, ứng dụng phải quy định rõ “mỗi tín hiệu nghĩa là gì” và tránh báo thiếu hoặc báo hai lần.

## 3. Ba kết quả cần phân biệt khi chờ

### await() thành công

```java
done.await();
usePublishedResults();
```

Đây là mã minh họa trong một phương thức có thể ném `InterruptedException`; `usePublishedResults` đại diện cho bước xử lý kết quả của ứng dụng.

Nếu `await()` trở về bình thường, chốt đã mở. Nếu chốt mở trước khi bắt đầu chờ, phương thức cũng có thể trở về ngay; không cần phía đợi phải “đợi sẵn” để nhận tín hiệu.

Không có tín hiệu bị mất theo kiểu một thông báo thoáng qua: trạng thái về không được giữ lại.

### await có giới hạn thời gian

```java
boolean completed = done.await(2, TimeUnit.SECONDS);
if (!completed) {
    throw new IllegalStateException("Tasks did not finish in time");
}
usePublishedResults();
```

Cần import `java.util.concurrent.TimeUnit`. Kết quả `true` cho biết chốt đã mở; `false` cho biết lần chờ hết thời gian trước khi quan sát được việc mở chốt.

Khi trả `false`, không được tiếp tục dùng toàn bộ kết quả như thể mọi tác vụ đã báo xong. Một số tác vụ có thể đã hoàn tất và một số khác chưa; giao thức công bố “tất cả phần” chưa được xác nhận.

Hết thời gian chờ không tự hủy tác vụ và không tự giảm bộ đếm. Nếu cần hủy, phải có cơ chế riêng, chẳng hạn giữ `Future` và thực hiện chính sách hủy phù hợp.

### Chờ bị ngắt

`await` có thể ném `InterruptedException`. Đây là đường kết thúc riêng, không phải chờ thành công và cũng không phải kết quả `false` của thời gian chờ.

Cách đơn giản là cho phương thức gọi truyền ngoại lệ lên. Nếu ở ranh giới không thể truyền ngoại lệ đã kiểm tra, có thể khôi phục trạng thái ngắt rồi dừng đường xử lý phụ thuộc kết quả:

```java
// Đoạn mã bên trong một phương thức trả về void.
try {
    done.await();
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    return;
}
usePublishedResults();
```

Khi ném ngoại lệ ngắt, thao tác chờ xóa cờ ngắt của luồng. Việc khôi phục cho phép tầng gọi phía trên nhận biết yêu cầu ngắt. Đừng nuốt ngoại lệ rồi tiếp tục xử lý như thể chốt đã mở.

## 4. Quan hệ happens-before thực sự bảo đảm điều gì?

Happens-before là quan hệ thứ tự trong mô hình bộ nhớ Java. Nó giúp lập luận rằng một thao tác ghi phải được nhìn thấy bởi thao tác đọc nằm sau điểm đồng bộ thích hợp; không phải chỉ dựa vào việc “trên đồng hồ có vẻ đã chạy trước”.

Đối với latch, có thể hình dung:

```text
Luồng tạo kết quả                     Luồng sử dụng
ghi dữ liệu
    ↓ theo thứ tự chương trình
countDown()  ── quan hệ đồng bộ ──→  await() thành công
                                         ↓
                                     đọc dữ liệu
```

Hợp đồng này áp dụng cho các hành động trước những lần giảm bộ đếm đóng góp vào việc mở chốt, và các hành động sau lần `await` tương ứng trở về thành công.

Khi có nhiều tác vụ, tác vụ A giảm từ `2` xuống `1` vẫn đóng góp quan hệ công bố; không chỉ dữ liệu của tác vụ cuối cùng giảm từ `1` xuống `0` mới được nhìn thấy.

Điều này giải thích vì sao một mẫu “mỗi tác vụ ghi một ô riêng, rồi giảm latch; phía tổng hợp đợi latch rồi đọc các ô” không cần biến mỗi ô thành một biến volatile.

Nhưng latch không tự làm mọi thao tác trong các tác vụ an toàn. Nếu hai tác vụ cùng thực hiện `sum++` trên một biến thường, chúng vẫn có thể ghi đè kết quả của nhau trước khi báo xong. Chờ sau cùng không khôi phục những lần tăng đã bị mất.

Phải phân biệt:

- **Công bố kết quả đã tạo:** latch có thể cung cấp quan hệ cần thiết.
- **Phối hợp các tác vụ cùng sửa dữ liệu:** cần phân vùng dữ liệu, khóa, biến nguyên tử hoặc cơ chế khác phù hợp.

## 5. Ví dụ chạy được: công bố hai phần kết quả

Lưu thành `LatchMemoryDemo.java`:

```java
import java.util.concurrent.CountDownLatch;

public class LatchMemoryDemo {
    private static Thread worker(
            int index,
            int input,
            int[] results,
            RuntimeException[] failures,
            CountDownLatch done) {
        return new Thread(() -> {
            try {
                results[index] = Math.multiplyExact(input, input);
            } catch (RuntimeException e) {
                failures[index] = e;
            } finally {
                done.countDown();
            }
        });
    }

    public static void main(String[] args) throws InterruptedException {
        int[] results = new int[2];
        RuntimeException[] failures = new RuntimeException[2];
        CountDownLatch done = new CountDownLatch(2);

        Thread first = worker(0, 3, results, failures, done);
        Thread second = worker(1, 4, results, failures, done);
        first.start();
        second.start();

        done.await();

        for (RuntimeException failure : failures) {
            if (failure != null) {
                throw new IllegalStateException("Worker failed", failure);
            }
        }

        System.out.println("first=" + results[0]);
        System.out.println("second=" + results[1]);
        System.out.println("total=" + (results[0] + results[1]));
        System.out.println("count=" + done.getCount());
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```shell
javac --release 17 LatchMemoryDemo.java
java LatchMemoryDemo
```

Stdout:

```text
first=9
second=16
total=25
count=0
```

Lập luận về tính đúng:

1. Mỗi tác vụ ghi một phần tử riêng của mảng `results`; không có hai phép ghi đồng thời vào cùng phần tử.
2. Nếu phép tính ném `RuntimeException`, lỗi được lưu ở ô riêng trước khi báo hoàn tất.
3. Cả ghi kết quả lẫn ghi lỗi đều xảy ra trước `countDown()` của tác vụ tương ứng.
4. Luồng chính chỉ đọc mảng sau `done.await()` thành công.
5. Các quan hệ bộ nhớ của latch công bố những ghi đó cho luồng chính.

Không có `join()` trước khi đọc kết quả: ví dụ chủ ý dùng latch làm điểm phối hợp và công bố dữ liệu. Latch bảo đảm mốc trước `countDown` đã xảy ra, không phải toàn bộ luồng đã kết thúc. Nếu cần chờ cả phần việc sau mốc đó hoặc cần bảo đảm luồng kết thúc, phải chọn mốc khác hoặc dùng `join`.

Ví dụ chỉ thu nhận `RuntimeException` để làm rõ đường lỗi thông thường; nó không phải khuôn quản lý mọi lỗi nghiêm trọng của JVM.

Dòng in `getCount()` dùng để minh họa trạng thái sau khi đã chờ thành công. Nó không phải cơ chế thay thế cho `await`.

## 6. Vị trí countDown là ranh giới công bố

Xét đoạn sai:

```java
// SAI nếu phía đợi cần results[index] sau await.
done.countDown();
results[index] = computeResult();
```

Phía đợi có thể đi qua `await()` ngay sau tín hiệu cuối cùng, trong khi kết quả chưa được ghi. Bảo đảm bộ nhớ của latch không kéo một phép ghi ở sau `countDown` trở thành dữ liệu đã công bố trước đó.

Đặt lại đúng thứ tự:

```java
results[index] = computeResult();
done.countDown();
```

Nếu báo hoàn tất phải luôn xảy ra khi tác vụ kết thúc một lần thử, dùng `finally` và một kênh kết quả/lỗi như ví dụ trên. Đây là quyết định về nghĩa của tín hiệu:

- Tín hiệu “đã kết thúc lần thử” có thể xuất hiện cả khi thành công lẫn thất bại.
- Tín hiệu “đã khởi tạo thành công” không nên được hiểu như vậy nếu chỉ đơn giản giảm latch trong mọi trường hợp.

Latch không mang giá trị kết quả và không truyền ngoại lệ tự động. Nếu một tác vụ thất bại nhưng vẫn báo, người đợi cần xem dữ liệu lỗi trước khi coi toàn bộ công việc thành công.

Ngược lại, nếu chỉ giảm latch ở đường thành công mà không có chính sách thất bại, một ngoại lệ có thể khiến người đợi chờ mãi.

Đối với tác vụ chưa từng chạy do bị từ chối nộp hoặc bị hủy trước khi bắt đầu, khối `finally` bên trong tác vụ cũng không chạy. Người tổ chức công việc phải xử lý trường hợp đó; không thể chỉ thêm `finally` rồi mặc định đủ mọi tín hiệu.

## 7. Hai kiểu chốt thường gặp và chiều công bố

### Chốt báo xong

```text
Tác vụ: ghi kết quả → countDown(done)
Điều phối: await(done) → đọc kết quả
```

Số đếm thường bằng số phần việc cần báo. Phía đợi nhận dữ liệu được các tác vụ công bố trước tín hiệu.

### Chốt cho phép bắt đầu

```text
Điều phối: chuẩn bị dữ liệu → countDown(start)
Tác vụ: await(start) → dùng dữ liệu đã chuẩn bị
```

`start` thường bắt đầu bằng `1`. Chiều công bố đi từ luồng điều phối sang các tác vụ qua chốt này.

Nếu cần cả “bắt đầu” và “hoàn tất”, dùng hai latch với vai trò khác nhau. Một chốt đã mở không thể dùng lại làm chốt cho giai đoạn tiếp theo.

Cũng đừng suy luận rằng hai tác vụ cùng đi qua một start latch sẽ tự có thứ tự nhìn thấy dữ liệu chúng ghi **sau** lúc đi qua chốt. Chúng được mở cổng, nhưng vẫn chạy đồng thời; dữ liệu chung sau đó cần giao thức riêng.

## 8. Những nhầm lẫn và tình huống chờ mãi

### Đếm nhầm số sự kiện

Khởi tạo bằng `3` nhưng chỉ có hai đường gọi `countDown` thì chốt không mở. Khởi tạo quá nhỏ hoặc giảm hai lần có thể mở chốt trước khi đủ kết quả.

Hãy gắn mỗi tín hiệu với một sự kiện xác định, thay vì chỉ nhìn số lượng luồng trong chương trình.

### Chờ trong khi giữ tài nguyên mà bên báo cần

```text
Luồng A giữ khóa L rồi await(done)
Luồng B cần khóa L để hoàn tất và countDown(done)
```

B không hoàn tất được vì thiếu khóa; A không nhả khóa vì đang chờ B. `await` trên latch không tự nhả các monitor hoặc khóa khác mà luồng đang giữ.

Một tình huống tương tự là nhóm luồng cố định bị chiếm hết bởi những tác vụ đang đợi, trong khi các tác vụ cần giảm latch vẫn nằm trong hàng chờ của chính nhóm đó.

### Dùng ngủ thay chờ

`Thread.sleep` không chứng minh tác vụ đã hoàn tất và không thiết lập quan hệ đồng bộ bộ nhớ cần thiết. Ngủ lâu hơn chỉ thay đổi xác suất quan sát lỗi, không sửa giao thức.

### Dùng getCount làm giao thức chờ

`getCount` thích hợp cho quan sát/chẩn đoán. Không viết vòng quay đọc bộ đếm để tự thay thế `await`; dùng API chờ có hợp đồng hoàn tất, ngắt và thời gian chờ rõ ràng.

### Hiểu tín hiệu là thành công nghiệp vụ

Bộ đếm về không chỉ chứng minh đủ tín hiệu theo những gì mã đã gọi. Nó không chứng minh thanh toán thành công, dữ liệu hợp lệ hoặc mọi tác vụ không có ngoại lệ. Những điều kiện đó phải được biểu diễn trong kết quả riêng.

## 9. Ranh giới của bảo đảm bộ nhớ

Một latch đã mở không tiếp tục là kênh công bố cho mọi thay đổi tương lai.

Ví dụ: tác vụ báo xong, sau đó tiếp tục sửa cùng đối tượng; phía đợi đọc đối tượng sau khi qua chốt. Những sửa đổi sau tín hiệu không được bảo vệ chỉ nhờ lần báo trước. Nếu hai bên tiếp tục truy cập đồng thời, cần cơ chế mới cho giai đoạn đó.

Tương tự, latch khởi tạo bằng không không tạo ra tín hiệu công bố từ một tác vụ chưa thực hiện `countDown`. Gọi giảm thêm trên chốt đã bằng không không được dùng như thông điệp cho một thế hệ dữ liệu mới.

Happens-before cũng không có nghĩa mọi dữ liệu trong chương trình tự trở thành một ảnh chụp nguyên tử. Ví dụ dùng latch an toàn vì mỗi tác vụ sở hữu một ô kết quả đến mốc công bố và không sửa tiếp ô đó sau mốc. Khi quyền sở hữu hoặc vòng đời thay đổi, phải phân tích lại các lần truy cập.

## 10. Tự kiểm tra

1. Tác vụ ghi kết quả sau `countDown`; phía đợi có được bảo đảm thấy kết quả đó sau `await` không?
2. `await(timeout)` trả `false` có tự hủy tác vụ không?
3. Hai tác vụ cùng `sum++` rồi báo latch; việc chờ có sửa được mất cập nhật không?
4. Khi `countDown` nằm trong `finally`, bộ đếm về không có chứng minh mọi tác vụ thành công không?
5. Có thể dùng lại latch đã mở cho một đợt tính toán mới không?
6. Có cần phía đợi gọi `await` trước lần giảm cuối cùng để không mất tín hiệu không?

Đáp án:

1. Không; thứ tự công bố đang bị đảo.
2. Không; phải có chính sách hủy riêng.
3. Không; cần bảo vệ phép cập nhật dùng chung từ đầu.
4. Không; còn phải đọc kết quả hoặc lỗi.
5. Không; tạo latch mới hoặc chọn công cụ dành cho nhiều giai đoạn.
6. Không; trạng thái mở được giữ lại.

Khi dùng latch, hãy xác định chính xác dữ liệu nào được ghi trước tín hiệu, ai được đọc sau khi chờ thành công, và điều gì xảy ra khi một tác vụ không thể gửi tín hiệu.

## Tài liệu đối chiếu

- [CountDownLatch — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/CountDownLatch.html): vòng đời, thao tác chờ và hiệu ứng nhất quán bộ nhớ.
- [Java Language Specification 17.4.5 — Happens-before Order](https://docs.oracle.com/javase/specs/jls/se25/html/jls-17.html#jls-17.4.5): cơ sở để lập luận về hiển thị dữ liệu giữa các luồng.
