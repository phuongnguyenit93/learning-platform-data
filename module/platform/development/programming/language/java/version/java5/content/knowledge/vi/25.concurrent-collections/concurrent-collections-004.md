# Phân biệt thao tác đơn nguyên tử với chuỗi thao tác ghép

Đổi một `HashMap` dùng chung thành `ConcurrentHashMap` giúp các lời gọi của bản đồ được thực hiện an toàn khi nhiều luồng truy cập. Nhưng một quy tắc như “nếu chưa có thì thêm”, “đọc rồi tăng” hoặc “kiểm tra còn chỗ rồi đăng ký” vẫn có thể sai nếu được viết bằng nhiều lời gọi tách rời.

Muốn chọn đúng cơ chế, cần xác định **toàn bộ quyết định nào phải diễn ra mà không bị một thao tác cạnh tranh chen vào làm sai điều kiện**. Phạm vi đó có thể lớn hơn một phương thức, và không thể đo bằng số dòng mã.

## 1. Nguyên tử, an toàn luồng và khả năng nhìn thấy

| Khái niệm | Câu hỏi cần trả lời |
|---|---|
| An toàn luồng (thread safety) | Cấu trúc hoặc đối tượng có giữ đúng hợp đồng khi bị truy cập đồng thời không? |
| Tính nguyên tử (atomicity) | Trong phạm vi được bảo đảm, việc kiểm tra/cập nhật có thể bị quan sát hoặc tác động như một thao tác dở dang không? |
| Khả năng nhìn thấy (visibility) | Phép đọc ở luồng khác có quan hệ bộ nhớ phù hợp với phép ghi cần quan sát không? |
| Thao tác ghép (compound action) | Có nhiều bước phụ thuộc nhau tạo thành một quyết định nghiệp vụ không? |

Tính nguyên tử là bảo đảm về phạm vi thao tác và tương tác đồng thời, không có nghĩa JVM chỉ dùng đúng một lệnh máy. Một API có thể thực hiện nhiều bước nội bộ nhưng vẫn công bố bảo đảm nguyên tử thích hợp.

Ngược lại, một dòng như `counter++` vẫn gồm đọc, tính và ghi. Khai báo `counter` là `volatile` không làm phép tăng đó thành cập nhật nguyên tử. Hợp đồng mô hình bộ nhớ và các quan hệ đồng bộ hóa được quy định tại [JLS, chương 17](https://docs.oracle.com/javase/specs/jls/se25/html/jls-17.html).

**Một thao tác đúng không làm cả chuỗi đúng.** Ví dụ `ConcurrentMap.putIfAbsent` gộp điều kiện “chưa có” với việc thêm; hai lời gọi riêng `containsKey` và `put` không có cùng bảo đảm. Xem [ConcurrentMap](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ConcurrentMap.html).

## 2. Ba dạng thao tác ghép thường gặp

### 2.1. Đọc–sửa–ghi

```java
// Minh họa lỗi: counter là ConcurrentMap<String, Integer> dùng chung.
int oldValue = counter.getOrDefault("value", 0);
counter.put("value", oldValue + 1);
```

Mỗi lần `get` và `put` có thể đúng hợp đồng, nhưng hai luồng cùng đọc 0 rồi cùng ghi 1 làm mất một lần tăng. Lỗi nằm ở việc giá trị đã đọc không còn là căn cứ độc quyền cho lần ghi sau.

### 2.2. Kiểm tra rồi hành động

```java
// Minh họa lỗi: members là CopyOnWriteArrayList<String>.
if (!members.contains("alice")) {
    members.add("alice");
}
```

`CopyOnWriteArrayList` cho phép phần tử trùng. Hai luồng đều có thể kiểm tra khi chưa có, rồi mỗi luồng thêm một lần. Nếu mục tiêu là giữ dạng danh sách nhưng thêm khi vắng mặt, lớp này có `addIfAbsent`; xem [CopyOnWriteArrayList.addIfAbsent](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/CopyOnWriteArrayList.html#addIfAbsent(E)). Nếu bản chất dữ liệu là tập hợp không trùng, một tập hợp đồng thời thường biểu đạt mục tiêu rõ hơn.

### 2.3. Kiểm tra một trạng thái rồi dùng trạng thái đó

```java
// Minh họa lỗi: queue là BlockingQueue<Job>.
if (!queue.isEmpty()) {
    Job next = queue.take();
    process(next);
}
```

Giữa `isEmpty()` và `take()`, một bên tiêu thụ khác có thể đã lấy phần tử cuối. Lời gọi `take()` vẫn có thể chờ dù kiểm tra trước đó thấy không rỗng.

Nếu cần thử lấy ngay, dùng `poll()` và xử lý kết quả `null`. Nếu cần chờ công việc, gọi `take()` theo chính sách chờ/ngắt đã định, không dựa vào một phép kiểm tra cũ để dự đoán nó sẽ không chờ.

Các đoạn trên chỉ minh họa từng mẫu lỗi và giả định đã có biến, kiểu và hàm được mô tả; chúng không phải chương trình độc lập.

## 3. Thí nghiệm tái hiện mất cập nhật có kiểm soát

Chạy một đoạn lỗi rồi “thấy kết quả đúng” không chứng minh nó an toàn: lịch chạy có thể tình cờ tránh khoảng xen kẽ nguy hiểm. Chương trình dưới dùng `CyclicBarrier` để buộc cả hai luồng đọc xong trước khi một luồng được ghi.

Lưu thành `CompoundOperationDemo.java`:

```java
import java.util.Set;
import java.util.concurrent.BrokenBarrierException;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.CyclicBarrier;
import java.util.concurrent.atomic.AtomicInteger;

public class CompoundOperationDemo {
    static void runTwo(Runnable action) throws InterruptedException {
        Thread first = new Thread(action, "first");
        Thread second = new Thread(action, "second");
        first.start();
        second.start();
        first.join();
        second.join();
    }

    public static void main(String[] args) throws InterruptedException {
        ConcurrentMap<String, Integer> counter = new ConcurrentHashMap<>();
        counter.put("value", 0);
        CyclicBarrier bothHaveRead = new CyclicBarrier(2);

        Runnable separateReadAndWrite = () -> {
            int previous = counter.get("value");
            try {
                bothHaveRead.await();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                return;
            } catch (BrokenBarrierException e) {
                throw new IllegalStateException(e);
            }
            counter.put("value", previous + 1);
        };

        runTwo(separateReadAndWrite);
        System.out.println("get then put: " + counter.get("value"));

        counter.put("value", 0);
        runTwo(() -> counter.merge("value", 1, Integer::sum));
        System.out.println("atomic merge: " + counter.get("value"));

        Set<String> registered = ConcurrentHashMap.newKeySet();
        AtomicInteger successfulRegistrations = new AtomicInteger();
        runTwo(() -> {
            if (registered.add("same-user")) {
                successfulRegistrations.incrementAndGet();
            }
        });
        System.out.println("successful registrations: "
                + successfulRegistrations.get());
        System.out.println("registered users: " + registered.size());
    }
}
```

Biên dịch và chạy với Java 17 trở lên:

```shell
javac -encoding UTF-8 --release 17 CompoundOperationDemo.java
java CompoundOperationDemo
```

Stdout trong lượt chạy bình thường, không có ngắt từ tác nhân bên ngoài:

```text
get then put: 1
atomic merge: 2
successful registrations: 1
registered users: 1
```

### Vì sao dòng đầu chắc chắn là 1?

Giá trị khởi tạo là 0. Mỗi luồng phải gọi `get` trước khi tới rào đồng bộ. Không luồng nào được chạy tiếp tới `put` cho tới khi cả hai đã đọc. Bởi vậy, cả hai biến cục bộ `previous` đều là 0, rồi cả hai ghi 1.

Rào đồng bộ chỉ dùng để dựng một lịch chạy dễ kiểm chứng. Nó không bao trùm toàn bộ chuỗi đọc–sửa–ghi thành một vùng độc quyền. Không dùng `sleep` để hi vọng tạo ra lịch xen kẽ này.

### Vì sao merge là 2?

`ConcurrentHashMap` bảo đảm cập nhật của mỗi lần `merge` theo hợp đồng nguyên tử của nó. Hai lần tăng trên cùng khóa được phân xử sao cho không cùng ghi đè từ một giá trị cũ như đoạn tách rời. Sau khi chờ cả hai luồng kết thúc bằng `join`, tổng là 2.

### Vì sao đăng ký thành công đúng một lần?

`registered.add("same-user")` thực hiện quyết định thêm vào tập hợp đồng thời và trả kết quả cho chính lần gọi đó. Một luồng nhận `true`, luồng còn lại nhận `false`; không cần `contains` trước. `AtomicInteger` chỉ đếm số lời gọi thành công, giúp quan sát kết quả mà không tự tạo thêm một bộ đếm không an toàn.

Đây là lỗi tranh chấp ở mức logic (race condition) dù các truy cập vào bản đồ được thực hiện bằng API an toàn luồng. Không nên gọi mọi lỗi như vậy là tranh chấp dữ liệu (data race) theo nghĩa chặt của JMM: vẫn có thể mất cập nhật vì ghép sai các thao tác đã được đồng bộ hóa bên trong.

## 4. Ưu tiên API bao trùm cả quyết định

| Quy tắc cần thực hiện | Cách ghép dễ sai | Cách biểu đạt phù hợp |
|---|---|---|
| Thêm nếu khóa chưa có | `containsKey` rồi `put` | `ConcurrentMap.putIfAbsent` |
| Tăng giá trị trên một khóa | `get` rồi `put` | `merge` hoặc `compute` có hợp đồng phù hợp |
| Xóa nếu giá trị chưa đổi | `get`, so sánh rồi `remove(key)` | `remove(key, expected)` |
| Thay nếu giá trị chưa đổi | `get`, so sánh rồi `put` | `replace(key, expected, next)` |
| Nhận phần tử nếu đang có | `isEmpty` rồi lấy | `poll()` và xử lý kết quả |
| Giữ tập hợp không trùng | `contains` rồi `add` | Dùng `add` trên một tập hợp đồng thời và đọc kết quả |
| Thêm vào danh sách nếu vắng mặt | `contains` rồi `add` | `CopyOnWriteArrayList.addIfAbsent` khi phù hợp tải đọc/ghi |

Không chỉ thay tên phương thức một cách máy móc. Hãy kiểm tra kiểu triển khai, giá trị trả về và ý nghĩa khi điều kiện thất bại. Ví dụ `replace` có điều kiện trả `false` thường có nghĩa dữ liệu đã đổi, không phải ngoại lệ hệ thống.

API cũng chỉ bao trùm đúng phạm vi được công bố. Một `compute` trên khóa A rồi một `compute` trên khóa B không tự tạo giao dịch cho hai khóa.

## 5. Khi phải khóa cả chuỗi thao tác

Nếu không có API phù hợp cho toàn bộ bất biến, có thể cần một vùng đồng bộ hóa bên ngoài. Ví dụ giữ quy tắc thêm không trùng trên một danh sách được bọc đồng bộ:

```java
List<String> names = Collections.synchronizedList(new ArrayList<>());

// Đoạn sử dụng trong phạm vi chia sẻ cùng biến names.
synchronized (names) {
    if (!names.contains("alice")) {
        names.add("alice");
    }
}
```

Đây là đoạn minh họa cần import `List`, `Collections`, `ArrayList`. Khóa được giữ qua cả kiểm tra và thêm. Những đường thực hiện cùng quy tắc phải tuân thủ cùng giao thức; mọi truy cập vào danh sách nền phải đi qua wrapper thay vì giữ tham chiếu khác rồi sửa trực tiếp. Việc duyệt wrapper cũng có yêu cầu khóa riêng được tài liệu mô tả tại [Collections.synchronizedList](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Collections.html#synchronizedList(java.util.List)).

Với `ConcurrentHashMap`, `synchronized(map)` không tự liên kết với cơ chế đồng bộ hóa nội bộ của nó. Nếu một nơi lấy monitor này còn nơi khác chỉ gọi `map.put` bình thường, lời gọi `put` kia không vì thế phải chờ monitor bên ngoài. Một khóa ngoài chỉ bảo vệ bất biến khi tất cả bên có khả năng phá bất biến cùng phối hợp.

Đối với trạng thái chung giữa nhiều collection, khóa phải bao trùm toàn bộ trạng thái liên quan hoặc thiết kế lại cách biểu diễn. Ví dụ “mỗi người chỉ nằm trong một trong hai nhóm” không được bảo vệ chỉ bằng việc mỗi nhóm riêng là tập hợp đồng thời.

Giữ vùng khóa gọn; không thực hiện I/O kéo dài hoặc chờ một bên khác cần chính khóa đó để tiến triển. Nếu phải giữ nhiều khóa, cần thứ tự lấy khóa nhất quán để tránh nguy cơ bế tắc.

## 6. Một lời gọi không phải lúc nào cũng nguyên tử toàn bộ

Đừng nhìn hình thức “một method call” rồi suy ra toàn bộ hiệu ứng không thể bị quan sát từng phần.

- Thao tác hàng loạt như `putAll`, `clear` hoặc `replaceAll` trên một collection đồng thời có thể cho phép bên đọc quan sát những trạng thái trung gian theo hợp đồng lớp cụ thể; không coi đó là giao dịch toàn collection.
- Một lần duyệt an toàn không nhất thiết là ảnh chụp nhất quán của mọi phần tử. Kiểu duyệt yếu nhất quán và ảnh chụp có ý nghĩa khác nhau.
- `computeIfAbsent(key, k -> new ArrayList<>()).add(value)` gồm thao tác trên bản đồ và một thao tác khác trên danh sách. Danh sách không tự an toàn đồng thời chỉ vì được lấy từ bản đồ.
- Hàm callback có thể có quy tắc gọi lại khác nhau giữa các triển khai `ConcurrentMap`. Không đặt tác dụng phụ cần “đúng một lần” vào callback chỉ dựa vào tên phương thức.

Tương tự, hai trường trong cùng đối tượng có thể tạo thành một bất biến dù mỗi trường riêng có kiểu nguyên tử. Ví dụ `used` và `free` cần cùng mô tả một sức chứa: hai lần cập nhật hai biến độc lập có thể để bên đọc thấy trạng thái chưa đồng bộ giữa chúng. Có thể dùng khóa chung hoặc gom thành một giá trị bất biến được thay cùng nhau, tùy thiết kế.

## 7. Kiểm tra giới hạn sức chứa là một bất biến riêng

Đoạn sau không giới hạn an toàn số người đăng ký:

```java
// Minh họa lỗi dù registered là một tập hợp đồng thời.
if (registered.size() < limit) {
    registered.add(userId);
}
```

Hai luồng có thể cùng thấy còn một chỗ rồi cùng thêm hai người khác nhau. Dùng `add` nguyên tử chỉ giữ tính không trùng của từng phần tử, không giữ được tổng số lượng dưới giới hạn.

Nếu cần giới hạn, phải có cơ chế phân bổ chỗ đi cùng việc đăng ký, và xử lý cả trường hợp thêm trùng, thất bại hoặc hủy. Một semaphore có thể đại diện hạn mức trong một thiết kế đầy đủ, nhưng không chỉ thêm lệnh lấy giấy phép mà bỏ qua việc hoàn trả đúng lúc. Quy tắc nghiệp vụ quyết định phạm vi phải phối hợp.

## 8. Cách rà soát một đoạn mã dùng collection đồng thời

Thực hiện lần lượt:

1. Viết bất biến cần giữ bằng lời: không trùng, không mất lần tăng, không vượt sức chứa, hay chuyển trạng thái có điều kiện.
2. Đánh dấu lần đọc tạo ra căn cứ cho lần ghi. Nếu có khoảng trống giữa chúng, xét luồng khác có thể đổi dữ liệu gì trong khoảng đó.
3. Tìm API gộp đúng cả điều kiện và cập nhật, rồi dùng kết quả của chính API để quyết định bước tiếp theo.
4. Nếu bất biến trải qua nhiều khóa hoặc nhiều đối tượng, thiết kế phạm vi khóa/giao dịch hoặc cách gom trạng thái phù hợp.
5. Kiểm tra tất cả đường đọc/ghi có tuân thủ giao thức và các giá trị bên trong có thực sự an toàn hay không.
6. Dựng lịch xen kẽ có kiểm soát để kiểm chứng tình huống nguy hiểm; đừng chỉ chạy lặp rồi dựa vào may rủi.

Ngay cả một lần “đánh dấu đã xử lý” nguyên tử trong tập hợp cũng không tự bảo đảm thao tác bên ngoài thành công. Nếu tiến trình dừng sau đánh dấu nhưng trước khi gửi thông báo, trạng thái đăng ký và tác động bên ngoài vẫn lệch nhau. Tính nguyên tử trong bộ nhớ không thay thế giao thức xử lý lỗi và lưu trữ bền vững.

## 9. Tự kiểm tra

1. Một dòng `map.put(k, map.get(k) + 1)` có phải phép tăng nguyên tử không? — Không; số dòng không quyết định phạm vi nguyên tử.
2. `volatile` có sửa được chuỗi kiểm tra rồi thêm vào collection không? — Không.
3. Tập hợp đồng thời có tự bảo đảm quy tắc `size < limit` rồi thêm không? — Không; đó là một bất biến rộng hơn.
4. Vì sao thí nghiệm dùng rào đồng bộ? — Để buộc cả hai lần đọc xảy ra trước mọi lần ghi, tái hiện chắc chắn lịch gây mất cập nhật.
5. Khi nào khóa ngoài có ích? — Khi nó bao trùm toàn bộ thao tác cần phối hợp và mọi bên liên quan đều tuân thủ cùng giao thức.
