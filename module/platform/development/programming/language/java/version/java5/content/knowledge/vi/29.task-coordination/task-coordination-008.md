# acquire, tryAcquire, release và cân bằng giấy phép

## 1. Giấy phép biểu diễn quyền sử dụng một phần sức chứa

Giả sử một dịch vụ chỉ cho phép tối đa ba tác vụ cùng truy cập một tài nguyên. Mỗi tác vụ cần nhận một **giấy phép (permit)** trước khi sử dụng, rồi trả lại khi việc sử dụng thật sự kết thúc.

`Semaphore` quản lý số giấy phép còn khả dụng. Giấy phép ở đây là số đếm logic, không phải đối tượng riêng được phát cho từng tác vụ.

```text
Sức chứa quy ước: 3

3 giấy phép rảnh
    ↓ acquire() thành công
2 giấy phép rảnh, 1 lượt sử dụng đang hoạt động
    ↓ release()
3 giấy phép rảnh
```

Ba thao tác cần phối hợp đúng là:

- `acquire`: nhận giấy phép, có thể chờ.
- `tryAcquire`: thử nhận, có thể không nhận được.
- `release`: thêm giấy phép trở lại.

Trong mô hình giới hạn cố định, nguyên tắc cốt lõi là: **chỉ trả số giấy phép đã nhận thành công, đúng một lần, tại thời điểm công việc được bảo vệ đã kết thúc**.

## 2. Chọn cách nhận giấy phép

| Lời gọi | Hành vi khi thiếu giấy phép | Dấu hiệu đã nhận |
| --- | --- | --- |
| `acquire()` | Chờ, có thể bị ngắt | Trở về bình thường |
| `acquire(n)` | Chờ đủ n giấy phép | Trở về bình thường |
| `tryAcquire()` | Không chờ | Trả `true` |
| `tryAcquire(n)` | Không chờ | Trả `true` |
| `tryAcquire(timeout, unit)` | Chờ tối đa theo thời hạn | Trả `true` |
| `tryAcquire(n, timeout, unit)` | Chờ đủ n theo thời hạn | Trả `true` |

`acquire` và phiên bản thử có thời hạn có thể ném `InterruptedException`. Khi phương thức bị ngắt trước khi nhận thành công, không được trả giấy phép như thể đã nhận. Thử không thành công trả `false` cũng không tạo nghĩa vụ `release`. Xem [hợp đồng nhận giấy phép của Semaphore](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Semaphore.html).

### Chờ không giới hạn

```java
// Mã minh họa trong phương thức có thể ném InterruptedException.
gate.acquire();
try {
    useResource();
} finally {
    gate.release();
}
```

Vị trí `acquire()` nằm **trước** `try` là có chủ ý: nếu lời gọi đó ném ngoại lệ, chương trình chưa đi vào vùng `try/finally` và không trả một giấy phép chưa nhận.

### Từ chối hoặc chuyển hướng ngay khi bận

```java
// Mã minh họa.
if (!gate.tryAcquire()) {
    rejectBusyRequest();
    return;
}

try {
    useResource();
} finally {
    gate.release();
}
```

Nếu trả `false`, cần chính sách rõ: từ chối yêu cầu, đưa vào hàng chờ khác hoặc thử ở thời điểm phù hợp. Không tiếp tục sử dụng tài nguyên mà bỏ qua thất bại.

### Chờ có thời hạn

```java
// Mã minh họa trong phương thức có thể ném InterruptedException.
if (!gate.tryAcquire(200, TimeUnit.MILLISECONDS)) {
    reportBusy();
    return;
}

try {
    useResource();
} finally {
    gate.release();
}
```

Thời hạn này giới hạn **thời gian chờ giấy phép**, không giới hạn thời gian `useResource()`. Nếu công việc cần thời hạn thực thi hoặc hủy, phải thiết kế phần đó riêng.

## 3. Cân bằng giấy phép là một bất biến của chương trình

Với bộ giới hạn khởi tạo N giấy phép không âm và mọi thao tác đều tuân thủ giao thức nhận/trả:

```text
giấy phép đang rảnh + giấy phép đã nhận nhưng chưa trả = N
```

Đây là bất biến do **chương trình duy trì**, không phải một giới hạn tối đa mà `Semaphore` tự nhớ.

Khởi tạo `new Semaphore(3)` không khiến `release()` tự chặn khi số giấy phép đã lên 3. Trả thừa có thể làm số đếm vượt 3, khiến nhiều tác vụ hơn dự kiến được đi vào.

Hai dạng lỗi đối xứng:

| Lỗi | Hậu quả có thể xảy ra |
| --- | --- |
| Quên trả giấy phép | Sức chứa khả dụng giảm dần; tác vụ chờ lâu hoặc không thể đi tiếp |
| Trả thừa hoặc trả lặp | Sức chứa logic tăng sai; giới hạn đồng thời bị phá vỡ |

Nếu có cơ chế cố ý tăng/giảm sức chứa hoặc dùng semaphore để truyền tín hiệu, giao thức kế toán sẽ khác. Không lấy quy tắc của bộ giới hạn cố định áp đặt lên mọi cách sử dụng semaphore. Bài này tập trung vào giới hạn số lượt sử dụng đồng thời.

## 4. Lỗi đặt finally bao quanh cả acquire

Đoạn sau sai với mục tiêu trả đúng giấy phép đã nhận:

```java
// Ví dụ sai: acquire có thể ném InterruptedException.
try {
    gate.acquire();
    useResource();
} finally {
    gate.release();
}
```

Nếu luồng đang đợi bị ngắt, `acquire()` ném ngoại lệ. `finally` vẫn chạy và thêm giấy phép dù luồng chưa hề nhận được giấy phép nào.

Có hai cách tổ chức đúng.

**Cách thứ nhất:** chỉ vào `try` sau khi nhận thành công:

```java
gate.acquire();
try {
    useResource();
} finally {
    gate.release();
}
```

**Cách thứ hai:** nếu cấu trúc buộc phải đặt việc nhận bên trong `try`, theo dõi trạng thái nhận:

```java
boolean acquired = false;
try {
    gate.acquire();
    acquired = true;
    useResource();
} finally {
    if (acquired) {
        gate.release();
    }
}
```

Không dùng `availablePermits() > 0` để suy ra mình đã nhận giấy phép. Giá trị rảnh toàn cục không cho biết trách nhiệm trả của tác vụ hiện tại.

## 5. Ví dụ chạy đầy đủ: thất bại không làm rò rỉ hoặc phát thừa giấy phép

Chương trình dưới đây có sức chứa 2 và không có luồng khác nhận hoặc trả giấy phép. Nó cố ý giữ cả 2 giấy phép để quan sát `tryAcquire` thất bại. Sau đó trả một giấy phép, dùng lại giấy phép đó trong một tác vụ phát sinh lỗi và kiểm tra số đếm cuối cùng.

Tệp `PermitBalanceDemo.java`, chạy trên JDK 17 trở lên:

```java
import java.util.concurrent.Semaphore;
import java.util.concurrent.TimeUnit;

public class PermitBalanceDemo {
    public static void main(String[] args) throws InterruptedException {
        Semaphore gate = new Semaphore(2);
        int held = 0;

        try {
            gate.acquire(2);
            held += 2;
            System.out.println("afterAcquireTwo=" + gate.availablePermits());
            System.out.println("immediate=" + gate.tryAcquire());
            System.out.println("timed="
                    + gate.tryAcquire(30, TimeUnit.MILLISECONDS));

            gate.release();
            held--;

            try {
                gate.acquire();
                try {
                    throw new IllegalStateException("simulated task failure");
                } finally {
                    gate.release();
                }
            } catch (IllegalStateException expected) {
                System.out.println("task=" + expected.getMessage());
            }
            System.out.println("afterTask=" + gate.availablePermits());
        } finally {
            if (held > 0) {
                gate.release(held);
            }
        }

        System.out.println("atEnd=" + gate.availablePermits());
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 PermitBalanceDemo.java
java PermitBalanceDemo
```

Kết quả:

```text
afterAcquireTwo=0
immediate=false
timed=false
task=simulated task failure
afterTask=1
atEnd=2
```

Diễn biến kế toán:

| Bước | Giấy phép rảnh | Giấy phép do phần ngoài giữ |
| --- | --- | --- |
| Ban đầu | 2 | 0 |
| Nhận 2 | 0 | 2 |
| Hai lần thử không thành công | 0 | 2 |
| Phần ngoài trả 1 | 1 | 1 |
| Tác vụ lồng bên trong nhận 1 | 0 | 1 |
| Tác vụ lỗi nhưng finally trả 1 | 1 | 1 |
| Finally ngoài trả phần còn giữ | 2 | 0 |

Biến `held` chỉ ghi nhận số giấy phép phần ngoài đang có trách nhiệm trả. Phần lồng bên trong tự nhận/trả theo cặp riêng.

Ví dụ dùng một luồng để thứ tự số đếm xác định. Khi có nhiều luồng, `availablePermits()` có thể thay đổi ngay sau khi đọc, nên không dùng các giá trị quan sát đó để thay cho thao tác nhận nguyên tử.

## 6. Nhận nhiều giấy phép phải trả đúng số lượng

Nếu một công việc cần n đơn vị sức chứa:

```java
// Mã minh họa; permitsNeeded là số dương đã được kiểm tra.
gate.acquire(permitsNeeded);
try {
    useSeveralUnits(permitsNeeded);
} finally {
    gate.release(permitsNeeded);
}
```

`acquire(n)` chỉ trở về thành công khi nhận đủ n, không trả kết quả “đã nhận một phần”. Thử n giấy phép thất bại cũng không có phần nhận thành công để phải hoàn trả.

Đừng thay bằng việc nhận từng giấy phép nếu thuật toán không xử lý được tình trạng giữ một phần rồi chờ phần còn lại:

```text
Semaphore có 2 giấy phép
T1 nhận 1, cần thêm 1
T2 nhận 1, cần thêm 1
→ cả hai cùng giữ một phần và chờ nhau trả
```

Nhận cả nhóm bằng `acquire(2)` tránh tình huống giữ một phần đó trên cùng semaphore. Tuy nhiên, nếu yêu cầu n lớn hơn sức chứa cố định mà không có bên nào tăng thêm, yêu cầu không thể được đáp ứng. Cần kiểm tra yêu cầu theo miền bài toán trước khi chờ.

Nhận nhiều giấy phép cũng không tự giải quyết deadlock giữa nhiều semaphore hoặc tài nguyên khác. Khi phải nhận nhiều tài nguyên, cần quy tắc thứ tự hoặc giao thức hoàn trả riêng.

## 7. Semaphore không quản lý quyền sở hữu như khóa

`Semaphore` không nhớ “luồng nào đang sở hữu giấy phép số mấy”. Một luồng khác có thể gọi `release()`. Điều này hữu ích cho mô hình một bên nhận quyền và một bên khác báo công việc kết thúc, nhưng cũng khiến trả sai khó bị phát hiện tự động.

Ngược lại, `ReentrantLock` có khái niệm luồng sở hữu và hỗ trợ nhận lại khóa theo luồng đó; xem [ReentrantLock](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/locks/ReentrantLock.html).

Không suy luận rằng:

- Cùng luồng đã nhận một giấy phép thì lần nhận tiếp theo sẽ tự được cho qua.
- Luồng gọi `release()` sai sẽ luôn bị báo lỗi quyền sở hữu.
- Semaphore một giấy phép tự có mọi đặc điểm của một khóa tái nhập.

Với semaphore một giấy phép, một luồng nhận rồi tiếp tục `acquire()` trước khi trả có thể tự chặn chính mình.

Giấy phép cũng không thay thế danh tính tài nguyên. Nếu giới hạn một nhóm kết nối, vẫn cần cách chọn kết nối rảnh, đánh dấu kết nối đang dùng và trả đúng kết nối. Việc chỉ giới hạn số lượt đồng thời không tự bảo vệ cấu trúc quản lý nhóm tài nguyên.

## 8. Thời điểm trả phải theo vòng đời công việc thật

Với công việc đồng bộ, `finally` sau lời gọi thường đúng:

```java
gate.acquire();
try {
    performSynchronousOperation();
} finally {
    gate.release();
}
```

Với công việc bất đồng bộ, việc khởi động rồi trả giấy phép ngay có thể mở lại sức chứa khi công việc thật vẫn đang chạy:

```java
// Ví dụ sai nếu mục tiêu là giới hạn số công việc nền đang chạy.
gate.acquire();
try {
    startBackgroundOperation();
} finally {
    gate.release(); // Chỉ chờ lời gọi khởi động trở về.
}
```

Cần chuyển trách nhiệm trả đến mốc kết thúc thật sự, chẳng hạn cơ chế hoàn tất của tác vụ nền. Khi làm vậy phải xử lý đầy đủ:

1. Khởi động thất bại trước khi có tác vụ nền: bên khởi động vẫn chịu trách nhiệm trả.
2. Khởi động thành công: trách nhiệm trả được bàn giao rõ ràng cho đường hoàn tất.
3. Thành công, lỗi hoặc hủy đều dẫn đến đúng một lần trả.
4. Thông báo hủy không bị nhầm là tài nguyên đã ngừng sử dụng nếu công việc thực tế vẫn chạy.

Một cặp `acquire/release` nhìn cân bằng về số lần gọi chưa đủ nếu thời điểm trả làm giới hạn đồng thời mất ý nghĩa.

## 9. Ngắt, công bằng và quan sát trạng thái

### Ngắt lúc chờ

Nếu không chuyển tiếp `InterruptedException`, có thể xử lý theo mẫu:

```java
// Mã minh họa trong phương thức không khai báo InterruptedException.
try {
    gate.acquire();
} catch (InterruptedException interrupted) {
    Thread.currentThread().interrupt();
    return;
}

try {
    useResource();
} finally {
    gate.release();
}
```

Khi nhận thành công rồi công việc bị lỗi hoặc bị ngắt trong lúc chạy, trách nhiệm trả vẫn tồn tại và nên được thực hiện trong `finally`.

`acquireUninterruptibly()` là một API khác với chính sách chờ khác; không dùng nó chỉ để tránh phải xử lý ngoại lệ nếu hệ thống cần hủy tác vụ đang chờ.

### Công bằng không làm phép thử tức thời thành hàng chờ

Có thể tạo `new Semaphore(n, true)` để bật chính sách công bằng cho việc cấp giấy phép theo quy tắc của API. Tuy nhiên, các phiên bản `tryAcquire` không có thời hạn có thể nhận giấy phép đang rảnh mà không tuân thủ chính sách công bằng đó. Xem [chính sách fairness của Semaphore](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Semaphore.html).

Do đó vòng `while (!gate.tryAcquire()) { }` vừa tiêu tốn CPU vừa không phải cách thay thế an toàn cho việc chờ có chính sách công bằng. Khi muốn chờ, dùng API chờ phù hợp.

### Số giấy phép rảnh là ảnh chụp, không phải đặt chỗ

```java
// Ví dụ sai trong môi trường đồng thời.
if (gate.availablePermits() > 0) {
    useResource();
}
```

Một luồng khác có thể nhận giấy phép ngay sau phép kiểm tra; mã trên còn chưa nhận giấy phép nào. `tryAcquire()` mới kết hợp kiểm tra và nhận theo thao tác đồng bộ của semaphore.

Quan hệ bộ nhớ từ các hành động trước `release` đến hành động sau việc nhận thành công ở luồng khác hỗ trợ công bố dữ liệu theo giao thức. Nó không tự biến mọi dữ liệu đang được nhiều luồng thao tác thành an toàn; đặc biệt semaphore N giấy phép vẫn cho phép N bên chạy cùng lúc.

## 10. Tự kiểm tra việc cân bằng

Với mỗi đường đi của một công việc, hãy xác định:

- Đã nhận thành công chưa, và nhận bao nhiêu?
- Phần nào hiện có trách nhiệm trả?
- Lỗi trước khi nhận và lỗi sau khi nhận có đi vào các nhánh khác nhau không?
- Timeout hoặc `tryAcquire=false` có bị trả nhầm không?
- Hủy tác vụ có gây trả hai lần hoặc không trả lần nào không?
- Tại thời điểm trả, công việc còn sử dụng tài nguyên không?

Bài tập: đặt `release()` vào nhánh `tryAcquire()` trả `false` của ví dụ. Số đếm sẽ tăng dù không có giấy phép vừa được nhận. Đây là lỗi phát thừa, không phải cách “khôi phục” sau một lần thử thất bại.

Nguyên tắc cuối cùng cần duy trì là **nhận thành công tạo ra trách nhiệm trả; thất bại khi nhận không tạo ra trách nhiệm đó**.
