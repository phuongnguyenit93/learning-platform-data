# Thao tác riêng lẻ nguyên tử và chuỗi nhiều bước chưa tự nguyên tử

## 1. Concurrent bảo vệ điều gì?

`ConcurrentSkipListMap` và `ConcurrentSkipListSet` cho phép nhiều luồng thao tác an toàn trên cấu trúc có thứ tự. Tuy nhiên, điều đó không có nghĩa mọi đoạn mã dùng chúng đều là một đơn vị không thể bị xen vào.

Cần phân biệt:

- **Thao tác có hợp đồng nguyên tử:** một điều kiện và cập nhật cụ thể được cấu trúc thực hiện như một thao tác logic.
- **Chuỗi nhiều lời gọi do ứng dụng ghép lại:** giữa các lời gọi, luồng khác có thể thay đổi dữ liệu.
- **Bất biến nghiệp vụ:** điều kiện phải đúng trên một hoặc nhiều khóa, có thể cần cơ chế phối hợp riêng.

“Nguyên tử” không nhất thiết là một lệnh CPU. Từ phía các bên cùng thao tác, một cập nhật được bảo đảm nguyên tử có hiệu ứng như diễn ra tại một điểm trong khoảng gọi và trả về, dù cách cài đặt có nhiều bước hoặc thử lại bên trong.

Cũng không được hiểu rằng mọi phương thức có một tên gọi đều nguyên tử: các thao tác hàng loạt như putAll hoặc clear có hợp đồng khác. Bài này tập trung vào cách chọn đúng ranh giới thao tác với API hiện hành, bằng ví dụ Java 17 trở lên.

## 2. Lỗi kiểm tra rồi thực hiện

### 2.1. Từng lời gọi đúng, cả ý định vẫn sai

Giả sử muốn chỉ một worker tạo một ánh xạ:

```java
// Mẫu minh họa lỗi khi nhiều luồng cùng chạy.
if (!map.containsKey(key)) {
    map.put(key, value);
    markAsCreator();
}
```

Một lịch xen kẽ hợp lệ:

| Bước | Worker A | Worker B |
| --- | --- | --- |
| 1 | containsKey trả false | |
| 2 | | containsKey trả false |
| 3 | put giá trị của A | |
| 4 | | put giá trị của B |
| 5 | Tự ghi nhận mình là người tạo | |
| 6 | | Cũng tự ghi nhận mình là người tạo |

Map vẫn có đúng một ánh xạ ở khóa ấy. Cấu trúc không bị hỏng. Nhưng hai worker đều tin mình vừa tạo mới, và giá trị của một bên có thể đã ghi đè bên kia.

Đây là lỗi **kiểm tra rồi thực hiện** (check-then-act). Không thể sửa chỉ bằng việc đổi map thông thường sang map đồng thời rồi giữ nguyên chuỗi.

### 2.2. Gộp ý định bằng putIfAbsent

```java
// Đoạn minh họa với ConcurrentSkipListMap không cho value null.
String previous = map.putIfAbsent(key, value);
if (previous == null) {
    markAsCreator();
}
```

`putIfAbsent` kiểm tra hiện diện và đặt giá trị như một thao tác kết hợp nguyên tử. Vì ConcurrentSkipListMap không chứa value null, previous null phân biệt được trường hợp lần gọi này vừa đặt ánh xạ.

Hợp đồng các phép kết hợp được mô tả trong [ConcurrentMap API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ConcurrentMap.html).

Lưu ý: biểu thức tạo value đã có thể được tính trước khi gọi putIfAbsent. Hai luồng có thể cùng tạo hai đối tượng tạm dù chỉ một value được lưu. Nếu việc tạo value có tác động bên ngoài, đừng nhầm “một ánh xạ được đặt” với “bước chuẩn bị chỉ chạy đúng một lần”.

## 3. Lỗi đọc rồi ghi làm mất cập nhật

Một bộ đếm đang là 0. Hai worker cùng tăng:

```java
// Mẫu minh họa lỗi.
int previous = counts.get("x");
counts.put("x", previous + 1);
```

Lịch chạy:

```text
A đọc 0
B đọc 0
A ghi 1
B ghi 1
Kết quả cuối: 1, trong khi có hai lần tăng.
```

Mỗi get và put được thực hiện an toàn trên map đồng thời. Phép tính “giá trị mới dựa trên giá trị cũ hiện tại” chưa được bảo vệ như một đơn vị.

Một cách diễn đạt đúng cho ví dụ:

```java
// Đoạn minh họa.
counts.merge("x", 1, Integer::sum);
```

Khi chưa có khóa, đặt 1; khi đã có, dùng cơ chế cập nhật của map để kết hợp giá trị hiện tại với 1. Với hai lần tăng hợp lệ trên dữ liệu ví dụ, kết quả là 2.

Số học vẫn có hợp đồng riêng. Integer có thể tràn nếu bộ đếm vượt miền int; tính nguyên tử không tự biến int thành số nguyên không giới hạn hoặc phát hiện mọi lỗi nghiệp vụ.

### 3.1. Hàm tính có thể được thử lại

Không suy ra hàm của `compute`, `computeIfAbsent`, `computeIfPresent` hoặc `merge` trên ConcurrentSkipListMap chỉ chạy đúng một lần. Lớp không bảo đảm việc áp dụng hàm tính chỉ xảy ra một lần nguyên tử.

Vì vậy hàm nên tính giá trị mới từ đầu vào, không chứa tác động bên ngoài cần đúng một lần. Ví dụ, dùng hàm cộng là phù hợp; gửi thông báo hoặc thu phí ngay trong hàm tính là một vấn đề khác với cập nhật ánh xạ.

Phải phân biệt **một cập nhật được chấp nhận vào map** và **số lần gọi hàm để tính ứng viên cập nhật**. Hợp đồng chi tiết thuộc từng phương thức trong [ConcurrentSkipListMap API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ConcurrentSkipListMap.html).

## 4. Các phép có điều kiện trên một khóa

| Ý định | API thường phù hợp | Điều kiện được kết hợp |
| --- | --- | --- |
| Tạo nếu chưa có | putIfAbsent(k, v) | Hiện diện + đặt |
| Thay khi khóa vẫn tồn tại | replace(k, next) | Hiện diện + thay |
| Thay khi value vẫn bằng expected | replace(k, expected, next) | So value + thay |
| Xóa khi value vẫn bằng expected | remove(k, expected) | So value + xóa |
| Kết hợp value hiện tại với đầu vào mới | merge(k, v, function) | Tính/cập nhật theo hợp đồng |
| Lấy và xóa một đầu có thứ tự | pollFirstEntry/pollLastEntry | Chọn một đầu + lấy/xóa |

### 4.1. Không xóa nhầm giá trị mới bằng quan sát cũ

Giả sử reader lấy entry `10=old`. Sau đó writer đổi ánh xạ thành `10=new`.

Nếu reader gọi `remove(10)`, nó có thể xóa ánh xạ mới. Nếu ý định là “chỉ xóa nếu vẫn là giá trị tôi đã nhìn thấy”, dùng:

```java
// Đoạn minh họa.
boolean removed = map.remove(saved.getKey(), saved.getValue());
```

Với trạng thái `10=new`, expected là old nên thao tác trả false và giữ new.

Điều kiện dùng quan hệ bằng của value, không yêu cầu cùng danh tính đối tượng. Nó cũng không ghi lại lịch sử: nếu value đã đổi rồi quay về một giá trị bằng expected, phép kiểm tra hiện tại vẫn có thể thành công. Khi nghiệp vụ cần nhận biết mọi lần thay đổi, phải có phiên bản hoặc giao thức khác.

### 4.2. Điều kiện tại khóa không đồng nghĩa điều kiện trên thứ tự toàn cục

Giả sử reader gọi `floorEntry(12)` và nhận khóa 10. Sau đó một luồng thêm khóa 11. Lúc này khóa 10 vẫn có thể mang cùng value cũ, nhưng đã không còn là floor của 12.

Một lần replace/remove có expectedValue tại khóa 10 không kiểm tra lại việc khóa 10 còn là ứng viên floor. Đây là hai điều kiện khác nhau:

```text
Ánh xạ tại khóa 10 vẫn có value cũ?
Khóa 10 vẫn là ứng viên đúng theo toàn bộ thứ tự hiện tại?
```

Nếu phải chọn và cập nhật theo một bất biến thứ tự như vậy, cần thiết kế ranh giới phối hợp đúng với cả điều kiện chọn.

### 4.3. Set cũng có kết quả để dùng trực tiếp

Với ConcurrentSkipListSet, tránh `contains(x)` rồi `add(x)` chỉ để biết ai thêm mới. Dùng ngay boolean từ add:

```java
// Đoạn minh họa.
if (set.add(id)) {
    // Lần gọi này đã thêm được id.
}
```

Điều này không biến một tác động bên ngoài trong thân if thành phần của phép thêm. Nếu tác động ấy thất bại, phần tử đã thêm không tự quay lại trạng thái trước. Hợp đồng của set được nêu trong [ConcurrentSkipListSet API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ConcurrentSkipListSet.html).

## 5. Bất biến nhiều khóa cần cơ chế khác

### 5.1. Giới hạn dung lượng là điều kiện trên cả tập dữ liệu

Yêu cầu: map chỉ được có tối đa một chỗ đặt.

```java
// Mẫu minh họa lỗi khi nhiều luồng cùng đặt các khóa khác nhau.
if (reservations.size() < 1) {
    reservations.put(id, "reserved");
}
```

Hai luồng có thể cùng thấy size bằng 0, rồi thêm hai khóa khác nhau. Map cuối có size 2.

Ngay cả một size hoàn toàn chính xác ở thời điểm đọc cũng không giải quyết được khoảng trống giữa kiểm tra và thêm. `putIfAbsent` tại từng id cũng chưa đủ: hai id khác nhau đều có thể được đặt thành công, trong khi bất biến là giới hạn tổng.

### 5.2. Phối hợp toàn bộ điều kiện và cập nhật

Trong ví dụ nhỏ, dùng một khóa ứng dụng chung:

```java
// Đoạn minh họa: mọi bên sửa reservations phải tuân thủ gate này.
synchronized (gate) {
    if (reservations.size() < 1) {
        reservations.put(id, "reserved");
    }
}
```

Phạm vi cần bảo vệ là cả lần kiểm tra và lần ghi. Nếu chỉ bọc mỗi put, cuộc đua vẫn còn vì hai luồng có thể đã kiểm tra trước đó.

Mọi đường cập nhật liên quan đến bất biến phải tham gia cùng giao thức. ConcurrentSkipListMap không tự tuân thủ gate mà ứng dụng tạo; một writer bỏ qua gate vẫn có thể phá giới hạn.

Nếu reader cần quan sát nhiều khóa như một trạng thái nhất quán, reader ấy cũng phải tham gia cách phối hợp phù hợp. Chỉ khóa writer không tự làm mọi chuỗi đọc bên ngoài trở thành snapshot.

Với bài toán khác, có thể chọn một luồng sở hữu dữ liệu, một bộ điều phối tài nguyên hoặc mô hình trạng thái bất biến được công bố theo phiên bản. Không cần dùng cùng một chiến lược cho mọi trường hợp, nhưng phải chỉ rõ thành phần nào bảo vệ bất biến.

### 5.3. Cẩn thận khóa và chờ

Không giữ gate rồi chờ một barrier mà luồng còn lại cũng phải lấy gate mới đến được barrier; cách đó có thể gây bế tắc.

Trong chương trình dưới đây, hai luồng chờ nhau **trước khi vào synchronized**, sau đó lần lượt kiểm tra và đặt trong vùng bảo vệ. Barrier chỉ phục vụ thí nghiệm lịch chạy, không phải một phần yêu cầu nghiệp vụ dung lượng.

## 6. Chương trình hoàn chỉnh tạo được cuộc đua có kiểm soát

Chương trình dùng hai worker và `CyclicBarrier(2)` để ép cả hai đọc/kiểm tra trước khi thực hiện bước ghi của các mẫu sai. Nhờ đó, lỗi mất cập nhật và vượt dung lượng không phụ thuộc việc chạy thử có “may mắn” gặp lịch xen kẽ hay không.

Các mẫu đúng dùng API kết hợp hoặc khóa chung. Main chỉ in sau khi đã `Future.get()` cả hai tác vụ liên quan.

Lưu thành **AtomicStepsDemo.java**:

```java
import java.util.concurrent.ConcurrentSkipListMap;
import java.util.concurrent.CyclicBarrier;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.atomic.AtomicInteger;

public class AtomicStepsDemo {
    @FunctionalInterface
    interface Worker {
        void run(int id) throws Exception;
    }

    static void runTwo(ExecutorService pool, Worker worker) throws Exception {
        Future<Void> first = pool.submit(() -> {
            worker.run(1);
            return null;
        });
        Future<Void> second = pool.submit(() -> {
            worker.run(2);
            return null;
        });
        first.get();
        second.get();
    }

    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newFixedThreadPool(2);
        try {
            var badCreate = new ConcurrentSkipListMap<Integer, String>();
            var badOwners = new AtomicInteger();
            var bothChecked = new CyclicBarrier(2);
            runTwo(pool, id -> {
                boolean missing = !badCreate.containsKey(7);
                bothChecked.await();
                if (missing) {
                    badCreate.put(7, "worker-" + id);
                    badOwners.incrementAndGet();
                }
            });
            System.out.println("Check-then-put owners/size: " +
                    badOwners.get() + "/" + badCreate.size());

            var goodCreate = new ConcurrentSkipListMap<Integer, String>();
            var goodOwners = new AtomicInteger();
            var startCreate = new CyclicBarrier(2);
            runTwo(pool, id -> {
                startCreate.await();
                if (goodCreate.putIfAbsent(7, "worker-" + id) == null) {
                    goodOwners.incrementAndGet();
                }
            });
            System.out.println("PutIfAbsent owners/size: " +
                    goodOwners.get() + "/" + goodCreate.size());

            var badCount = new ConcurrentSkipListMap<String, Integer>();
            badCount.put("x", 0);
            var bothRead = new CyclicBarrier(2);
            runTwo(pool, id -> {
                int previous = badCount.get("x");
                bothRead.await();
                badCount.put("x", previous + 1);
            });
            System.out.println("Get-then-put count: " + badCount.get("x"));

            var goodCount = new ConcurrentSkipListMap<String, Integer>();
            goodCount.put("x", 0);
            var startIncrement = new CyclicBarrier(2);
            runTwo(pool, id -> {
                startIncrement.await();
                goodCount.merge("x", 1, Integer::sum);
            });
            System.out.println("Merge count: " + goodCount.get("x"));

            var badCapacity = new ConcurrentSkipListMap<Integer, String>();
            var bothHaveRoom = new CyclicBarrier(2);
            runTwo(pool, id -> {
                boolean hasRoom = badCapacity.size() < 1;
                bothHaveRoom.await();
                if (hasRoom) badCapacity.put(id, "reserved");
            });
            System.out.println("Uncoordinated capacity: " + badCapacity.size());

            var goodCapacity = new ConcurrentSkipListMap<Integer, String>();
            Object gate = new Object();
            var startReserve = new CyclicBarrier(2);
            runTwo(pool, id -> {
                startReserve.await();
                synchronized (gate) {
                    if (goodCapacity.size() < 1) {
                        goodCapacity.put(id, "reserved");
                    }
                }
            });
            System.out.println("Coordinated capacity: " + goodCapacity.size());

            var versions = new ConcurrentSkipListMap<Integer, String>();
            versions.put(10, "old");
            var saved = versions.floorEntry(12);
            versions.put(10, "new");
            System.out.println("Remove stale value: " +
                    versions.remove(saved.getKey(), saved.getValue()));
            System.out.println("Current value: " + versions.get(10));
        } finally {
            pool.shutdownNow();
        }
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```bash
javac -encoding UTF-8 AtomicStepsDemo.java
java AtomicStepsDemo
```

Kết quả chuẩn:

```text
Check-then-put owners/size: 2/1
PutIfAbsent owners/size: 1/1
Get-then-put count: 1
Merge count: 2
Uncoordinated capacity: 2
Coordinated capacity: 1
Remove stale value: false
Current value: new
```

### 6.1. Đọc các kết quả theo ý định

- `2/1`: map chỉ giữ một ánh xạ, nhưng hai worker đều đã chạy nhánh tự nhận tạo mới.
- `1/1`: kết quả putIfAbsent cho phép đúng một worker nhận lần đặt thành công.
- `1` so với `2`: get rồi put làm mất một lần tăng; merge giữ đúng hai lần tăng.
- Dung lượng 2 so với 1: bảo vệ một khóa không thay thế bảo vệ điều kiện tổng.
- Remove false và value new: phép xóa có điều kiện không xóa giá trị đã bị thay.

Chương trình không in worker nào thắng vì danh tính ấy không được lịch chạy bảo đảm. Nó chỉ in những kết quả logic mà từng thí nghiệm đã kiểm soát.

AtomicInteger trong thí nghiệm dùng để đếm có bao nhiêu worker đã đi vào nhánh; bản thân biến đếm không tạo ra hoặc sửa lỗi kiểm tra rồi put.

## 7. Một lời gọi không nhất thiết là một giao dịch toàn bộ

Các thao tác hàng loạt có thể gồm nhiều cập nhật bên trong. Ví dụ, `putAll` vào một map đang được đọc có thể bị quan sát một phần. `clear` không phải lời hứa đóng băng mọi reader rồi thay toàn bộ trạng thái trong một bước.

Tương tự:

- Iterator skip list là nhất quán yếu, không phải một lần đọc nguyên tử của toàn bộ map.
- Góc nhìn khoảng vẫn liên kết với dữ liệu gốc.
- Một entry điều hướng là ảnh chụp của ánh xạ, không phải quyền khóa ánh xạ.
- `equals`, `toArray` hoặc một lượt tổng hợp không mặc nhiên là snapshot nhất quán của dữ liệu đang đổi.

Đừng đếm số dấu chấm gọi hàm để suy ra phạm vi nguyên tử. Hãy đọc hợp đồng phương thức và xác định bất biến mà ứng dụng đang yêu cầu.

## 8. Cấu trúc đồng thời không bảo vệ mọi value mutable

Giả sử value là một đối tượng có hai trường cần thay cùng nhau. Đặt đối tượng đó vào concurrent map không tự làm chuỗi sửa hai trường nguyên tử.

Các lựa chọn thường gặp:

- Tạo một value bất biến mới rồi thay ánh xạ bằng thao tác phù hợp.
- Đồng bộ việc sử dụng value theo cơ chế riêng.
- Dùng kiểu value có hợp đồng đồng thời cần thiết.
- Chuyển quyền sở hữu cập nhật cho một luồng.

Khóa dùng cho map cũng phải được phối hợp với nơi sửa value nếu bất biến trải qua cả hai. Có một cấu trúc đồng thời ở bên ngoài không loại bỏ quan hệ chia sẻ đối tượng bên trong.

Tính hiển thị bộ nhớ cũng khác tính nguyên tử: việc một luồng thấy được dữ liệu đã công bố không ngăn một luồng khác xen vào giữa hai bước nghiệp vụ.

## 9. Cách phân tích trước khi viết mã

Với mỗi yêu cầu, hãy trả lời theo thứ tự:

1. **Bất biến là gì?** Ví dụ “chỉ tạo một lần”, “mỗi lần tăng phải được tính”, “tổng không vượt giới hạn”.
2. **Nó nằm trên một khóa hay nhiều khóa?** Điều kiện có phụ thuộc thứ tự hoặc một value ngoài map không?
3. **Có API kết hợp đúng ý định không?** Dùng kết quả putIfAbsent/add/replace/remove thay vì kiểm tra rồi hành động.
4. **Có hàm tính được thử lại không?** Giữ hàm tính không có tác dụng phụ cần đúng một lần.
5. **Nếu không có API phù hợp, ai điều phối toàn bộ chuỗi?** Xác định khóa chung, chủ sở hữu hoặc mô hình phiên bản.
6. **Kết quả sẽ được kiểm chứng thế nào?** Dùng lịch có kiểm soát và kiểm tra bất biến, không chỉ chạy nhiều lần rồi hy vọng.

Không giữ thêm khóa tổng thể một cách máy móc cho mọi get/put. Khóa bổ sung chỉ có ý nghĩa khi nó bảo vệ một bất biến lớn hơn phạm vi thao tác mà cấu trúc đã cung cấp, và mọi bên liên quan tuân thủ nó.

## 10. Lỗi thường gặp và bài tập

| Lỗi | Cách sửa |
| --- | --- |
| Concurrent nên contains rồi put là đủ | Dùng putIfAbsent |
| Get/put đều an toàn nên phép tăng cũng an toàn | Dùng cập nhật kết hợp đúng ý định |
| PutIfAbsent giữ được giới hạn tổng giữa nhiều khóa | Bảo vệ điều kiện tổng bằng giao thức riêng |
| Replace expected kiểm tra cả lịch sử thay đổi | Nó chỉ kiểm tra điều kiện hiện tại; cần version nếu yêu cầu lịch sử |
| Remove theo khóa sau khi đọc entry cũ | Dùng remove có expected khi cần giữ value mới |
| Compute/merge chạy hàm đúng một lần | Hiểu khả năng thử lại và tách tác động bên ngoài |
| Một phương thức bulk tương đương giao dịch | Đọc hợp đồng nguyên tử cụ thể |
| Khóa riêng một phía là đủ | Mọi đường liên quan phải cùng tham gia |
| Dùng barrier bên trong vùng khóa độc quyền | Có thể tạo bế tắc khi bên kia không vào được |

Bài tập:

1. Giữ nguyên hai worker trong mẫu sai tạo mới, giải thích vì sao map size vẫn là 1 dù badOwners là 2.
2. Dùng ba worker và barrier ba bên cho get rồi put. Nếu mọi worker đọc 0 trước khi ghi, kết quả cuối vẫn có thể là 1; chuyển sang merge phải cho 3.
3. Thử replace với expected đúng và sai. Xác nhận boolean phản ánh điều kiện tại khóa, không phải nhận định khóa có còn là floor của một mốc.
4. Với giới hạn hai chỗ và ba worker, thiết kế lịch khiến cả ba cùng thấy còn chỗ. Nêu phạm vi phải bảo vệ để kết quả không vượt 2.
5. Cố ý cho một writer bỏ qua gate trong một bản thử riêng và giải thích vì sao khóa của các writer còn lại chưa đủ bảo vệ bất biến.
6. Cho value là một record bất biến chứa hai trường cần thay cùng nhau. Đề xuất cách tạo và thay value mới, rồi chỉ rõ điều kiện expected hoặc version cần kiểm tra.

Một cấu trúc đồng thời cung cấp những thao tác có hợp đồng cụ thể. Tính đúng đắn của chuỗi nghiệp vụ phụ thuộc việc ranh giới nguyên tử ấy có trùng với điều kiện ứng dụng cần bảo vệ hay không.
