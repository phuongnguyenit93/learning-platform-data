# Tính tái nhập của khóa đọc và khóa ghi

## 1. Tái nhập giải quyết vấn đề gì?

Một phương thức đã giữ khóa có thể gọi tiếp phương thức khác cũng cần khóa đó. **Tái nhập (reentrancy)** cho phép cùng luồng lấy lại khóa mà nó đang giữ, thay vì tự chờ chính mình. Ví dụ, thao tác cập nhật một bộ nhớ đệm gọi một hàm hỗ trợ cũng được bảo vệ bằng khóa ghi.

Cần phân biệt hai cấp độ: `ReadWriteLock` là giao diện cho một cặp khóa đọc/ghi; tính tái nhập phụ thuộc lớp triển khai. Bài này xét **`ReentrantReadWriteLock`** trong `java.util.concurrent.locks`, API vẫn được sử dụng trong Java hiện hành. Không suy rộng kết luận sang mọi khóa đọc/ghi. Xem [hợp đồng ReadWriteLock](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/locks/ReadWriteLock.html).

Khóa đọc cho phép nhiều luồng đọc cùng lúc; khóa ghi giữ quyền truy cập độc quyền. Tái nhập là quyền của **luồng đang giữ khóa**, không phải của mọi luồng chạy cùng phương thức hay dùng cùng đối tượng dữ liệu.

## 2. Những chiều lấy khóa nào được hỗ trợ?

Các tình huống dưới đây đều dùng **cùng một đối tượng `ReentrantReadWriteLock`** và cùng luồng thực hiện hai lần lấy khóa:

| Trạng thái hiện tại của luồng | Yêu cầu tiếp theo | Kết quả |
| --- | --- | --- |
| Đã giữ khóa đọc | Lấy thêm khóa đọc | Được: tái nhập đọc |
| Đã giữ khóa ghi | Lấy thêm khóa ghi | Được: tái nhập ghi |
| Đã giữ khóa ghi | Lấy khóa đọc | Được |
| Chỉ giữ khóa đọc | Lấy khóa ghi | Không hỗ trợ nâng cấp trực tiếp |

Chiều ghi → đọc hữu ích khi hàm cập nhật gọi hàm đọc đã có sẵn. Nó còn là cơ sở để hạ khóa: lấy khóa đọc khi vẫn giữ khóa ghi, sau đó nhả hết khóa ghi nhưng tiếp tục giữ khóa đọc. Ngược lại, chỉ giữ khóa đọc rồi gọi `writeLock().lock()` khiến luồng chờ mà không tự hoàn tất được khi vẫn giữ phần đọc đó. Xem [quy tắc tái nhập và hạ khóa](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/locks/ReentrantReadWriteLock.html).

## 3. Mỗi lần lấy thành công tạo thêm một lần phải nhả

### Khóa đọc

Cùng luồng có thể lấy khóa đọc nhiều lần. Mỗi lần thành công cần một `unlock()` tương ứng; nhả một lần không xóa các lần giữ còn lại. `getReadHoldCount()` cho biết số lần **luồng hiện tại** giữ khóa đọc; `getReadLockCount()` là tổng số lần giữ khóa đọc trên đối tượng khóa, không phải số luồng đọc phân biệt.

Khóa đọc không trao quyền sửa dữ liệu chung: hai luồng cùng giữ khóa đọc vẫn có thể chạy đồng thời. Việc phương thức lấy khóa đọc lần thứ hai không làm phần mã của nó thành độc quyền.

Nếu luồng không giữ khóa đọc mà gọi `readLock().unlock()`, nó nhận `IllegalMonitorStateException`. Tài liệu phương thức: [ReadLock](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/locks/ReentrantReadWriteLock.ReadLock.html).

### Khóa ghi

Khóa ghi theo dõi chủ sở hữu và số lần giữ. Khi chủ sở hữu lấy lại khóa ghi, số lần giữ tăng; mỗi lần nhả giảm một. Chỉ khi số lần giữ ghi trở về 0, quyền giữ ghi mới được giải phóng. Nếu luồng đó vẫn còn giữ khóa đọc, luồng khác vẫn chưa thể lấy khóa ghi.

`getWriteHoldCount()` trả số lần giữ ghi của luồng đang gọi; `isWriteLockedByCurrentThread()` trả lời luồng hiện tại có phải chủ sở hữu khóa ghi hay không. Các phép đo này hữu ích để minh họa hoặc chẩn đoán; không thay thế việc lấy khóa.

Nhả khóa ghi từ luồng khác, hoặc nhả quá số lần đã lấy, gây `IllegalMonitorStateException`. Xem [WriteLock](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/locks/ReentrantReadWriteLock.WriteLock.html).

## 4. Chương trình quan sát các trường hợp

Ví dụ sau chạy tuần tự trên luồng `main` để kết quả đếm không phụ thuộc lịch chạy. Hai phương thức lồng nhau mô phỏng hàm bên ngoài gọi hàm hỗ trợ; dùng cùng khóa xuyên suốt. Chương trình kiểm tra chiều đọc → ghi bằng `tryLock()` để tránh tự treo.

Lưu toàn bộ mã vào `ReentrancyDemo.java`, dùng JDK 17 trở lên:

```java
import java.util.concurrent.locks.ReentrantReadWriteLock;

public class ReentrancyDemo {
    private static final ReentrantReadWriteLock RW =
            new ReentrantReadWriteLock();
    private static int value = 10;

    private static void trace(String label) {
        System.out.println(label + ": read=" + RW.getReadHoldCount()
                + ", write=" + RW.getWriteHoldCount());
    }

    private static void readInner() {
        RW.readLock().lock();
        try {
            trace("read inner");
        } finally {
            RW.readLock().unlock();
        }
    }

    private static void nestedRead() {
        RW.readLock().lock();
        try {
            trace("read outer");
            readInner();
            trace("read outer after inner");
        } finally {
            RW.readLock().unlock();
        }
    }

    private static void writeInner() {
        RW.writeLock().lock();
        try {
            value++;
            trace("write inner");
        } finally {
            RW.writeLock().unlock();
        }
    }

    private static void nestedWrite() {
        RW.writeLock().lock();
        try {
            trace("write outer");
            writeInner();
            trace("write outer after inner");
        } finally {
            RW.writeLock().unlock();
        }
    }

    private static void writerReads() {
        RW.writeLock().lock();
        try {
            RW.readLock().lock();
            try {
                trace("writer also reads");
                System.out.println("value=" + value);
            } finally {
                RW.readLock().unlock();
            }
        } finally {
            RW.writeLock().unlock();
        }
    }

    private static void downgrade() {
        RW.writeLock().lock();
        try {
            value++;
            RW.readLock().lock();
        } finally {
            RW.writeLock().unlock();
        }
        try {
            trace("after downgrade");
            System.out.println("value=" + value);
        } finally {
            RW.readLock().unlock();
        }
    }

    private static void attemptUpgrade() {
        RW.readLock().lock();
        try {
            boolean acquired = RW.writeLock().tryLock();
            try {
                System.out.println("read to write acquired=" + acquired);
            } finally {
                if (acquired) {
                    RW.writeLock().unlock();
                }
            }
        } finally {
            RW.readLock().unlock();
        }
    }

    public static void main(String[] args) {
        nestedRead();
        nestedWrite();
        writerReads();
        downgrade();
        attemptUpgrade();
        trace("end");
    }
}
```

Biên dịch và chạy:

```shell
javac ReentrancyDemo.java
java ReentrancyDemo
```

Stdout:

```text
read outer: read=1, write=0
read inner: read=2, write=0
read outer after inner: read=1, write=0
write outer: read=0, write=1
write inner: read=0, write=2
write outer after inner: read=0, write=1
writer also reads: read=1, write=1
value=11
after downgrade: read=1, write=0
value=12
read to write acquired=false
end: read=0, write=0
```

Các dòng `inner` cho thấy số lần giữ tăng từ 1 lên 2. Khi hàm hỗ trợ kết thúc, `finally` của nó chỉ đưa số lần giữ về 1; hàm bên ngoài vẫn có khóa. Dòng `writer also reads` cho thấy hai bộ đếm có thể đồng thời khác 0. Sau `downgrade`, quyền ghi đã hết nhưng quyền đọc còn; giá trị 12 được đọc dưới khóa đọc. Dòng cuối kiểm tra ví dụ không để sót lần giữ khóa nào.

Đây là phép thử cơ chế của một luồng, không phải phép đo hiệu năng hay chứng minh thứ tự phục vụ giữa nhiều luồng.

## 5. Vì sao không nâng trực tiếp từ đọc lên ghi?

Giả sử T1 chỉ giữ khóa đọc rồi gọi `writeLock().lock()`. Khóa ghi cần không còn phần đọc đang giữ. Nhưng T1 chỉ có thể chạy tới `readLock().unlock()` sau khi lời gọi lấy khóa ghi trả về: T1 tự chặn đường giải phóng phần đọc của mình. Kể cả không có luồng đọc thứ hai, `ReentrantReadWriteLock` cũng không thực hiện phép chuyển đó.

Nếu cả T1 và T2 cùng giữ đọc rồi cùng chờ ghi, mỗi luồng còn giữ một phần đọc khiến bên kia không thể ghi. Bật chế độ công bằng không tạo ra khả năng nâng cấp. Thay `lock()` bằng một vòng lặp `tryLock()` trong lúc vẫn giữ đọc cũng không sửa được thiết kế.

Khi đọc thấy cần cập nhật, cách xử lý là:

1. Kết thúc phạm vi đọc và nhả **mọi lần giữ đọc của luồng hiện tại**.
2. Lấy khóa ghi.
3. Kiểm tra lại điều kiện cần cập nhật vì luồng khác có thể đã thay đổi dữ liệu trong khoảng chuyển tiếp.
4. Chỉ cập nhật nếu điều kiện vẫn đúng; nhả khóa ghi trong `finally`.

Ví dụ minh họa bên trong một lớp có các trường `rw`, `loaded`, `data` và hàm `load()`; đây không phải chương trình độc lập:

```java
rw.readLock().lock();
try {
    if (loaded) {
        return data;
    }
} finally {
    rw.readLock().unlock();
}

rw.writeLock().lock();
try {
    if (!loaded) { // Kiểm tra lại sau khi đã lấy quyền ghi.
        data = load();
        loaded = true;
    }
    return data;
} finally {
    rw.writeLock().unlock();
}
```

Đoạn minh họa giả định trước khi gọi, luồng không giữ khóa đọc nào khác trên `rw`; `data` là giá trị bất biến có thể trả về an toàn. Nếu một hàm bên ngoài vẫn giữ đọc, việc nhả riêng lần đọc trong đoạn này chưa đủ. Đây là lý do cần biết hợp đồng khóa của cả chuỗi gọi, không chỉ nhìn một phương thức.

## 6. Quy tắc thực hành và lỗi dễ gặp

- Đặt `lock()` ngay trước `try`; nhả trong `finally`. Với `tryLock()`, chỉ nhả khi kết quả là `true`. Mỗi phạm vi nên chịu trách nhiệm cho đúng lần lấy khóa của nó. Xem [mẫu sử dụng Lock](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/locks/Lock.html).
- Không dùng một vòng `while` để nhả toàn bộ số lần giữ của luồng: hàm con có thể vô tình phá quyền bảo vệ dữ liệu mà hàm cha vẫn cần.
- Khi hạ khóa, phải lấy đọc **trước khi** nhả lần ghi cuối cùng. Nhả ghi rồi mới lấy đọc để lại khoảng trống cho người ghi khác chen vào. Nếu đang giữ ghi hai lần, nhả một lần vẫn chưa hoàn tất hạ khóa.
- Tái nhập không chuyển quyền sở hữu sang luồng khác. Giao việc sang `ExecutorService` không khiến tác vụ nhận được khóa của luồng giao việc. Nếu luồng cha giữ ghi rồi chờ tác vụ cần cùng khóa, chương trình có thể mắc kẹt.
- Không tạo `new ReentrantReadWriteLock()` trong từng phương thức để bảo vệ cùng dữ liệu: các đối tượng khóa khác nhau không phối hợp với nhau.
- Khóa tái nhập không loại bỏ mọi bế tắc. Hai khóa khác nhau bị lấy theo thứ tự đảo nhau vẫn có thể gây bế tắc.
- Không giữ khóa qua lời gọi chậm hoặc hàm gọi ngược không kiểm soát chỉ vì lấy lại khóa được. Hãy giữ phạm vi bảo vệ ngắn, rõ quyền đọc/ghi.

## 7. Tự kiểm tra

1. Hàm A lấy khóa ghi rồi gọi B, B lấy cùng khóa ghi và nhả một lần. Khi B trở về, A còn giữ khóa không? **Có**, lần giữ của A vẫn còn.
2. Một luồng giữ đọc hai lần, nhả một lần rồi muốn lấy ghi. Đã đủ điều kiện chưa? **Chưa**, luồng vẫn còn một lần giữ đọc và không thể nâng cấp trực tiếp.
3. Luồng giữ ghi, lấy đọc rồi nhả hết ghi. Có được sửa dữ liệu chung tiếp không? **Không**, lúc này nó chỉ giữ đọc.
4. Vì sao phải kiểm tra lại dữ liệu khi nhả đọc rồi lấy ghi? **Vì có khoảng chuyển tiếp cho luồng khác cập nhật dữ liệu.**
