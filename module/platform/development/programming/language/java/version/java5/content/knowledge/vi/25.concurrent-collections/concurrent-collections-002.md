# `ConcurrentHashMap` trong truy cập nhiều luồng

## 1. Bảo vệ bảng ánh xạ và bảo vệ nghiệp vụ là hai việc khác nhau

`ConcurrentHashMap<K,V>` lưu ánh xạ khóa – giá trị và cho phép nhiều luồng cùng đọc, thêm, thay thế hoặc xóa ánh xạ an toàn. Nó hữu ích cho bảng tra dùng chung, trạng thái theo mã định danh hoặc thống kê theo khóa.

Ví dụ, nhiều luồng nhận yêu cầu có thể cùng tăng số lượt truy cập của một đường dẫn. Dùng một `HashMap` được chia sẻ và sửa trực tiếp mà không có cơ chế đồng bộ phù hợp không đáp ứng yêu cầu này. Thay bằng `ConcurrentHashMap` bảo vệ các thao tác của bảng, nhưng vẫn phải chọn đúng thao tác cho việc tăng bộ đếm.

Ba phạm vi cần phân biệt:

```text
an toàn của từng thao tác map
        ↓ không tự suy ra
nguyên tử của chuỗi đọc – kiểm tra – ghi
        ↓ không tự suy ra
nhất quán của nghiệp vụ qua nhiều khóa hoặc nhiều đối tượng
```

Một thao tác nguyên tử được quan sát như một thao tác không bị chen vào ở giữa trong phạm vi mà hợp đồng của nó bảo đảm. Đừng mở rộng bảo đảm của một khóa thành một giao dịch trên cả hệ thống.

[Java SE `ConcurrentHashMap`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html) mô tả khả năng đọc đồng thời, cập nhật, quan hệ hiển thị bộ nhớ và giới hạn của các phép tổng hợp. Các ví dụ trong bài dùng API vẫn áp dụng trên Java hiện hành và chạy trên Java 17+.

## 2. Đọc và ghi cùng một khóa có ý nghĩa gì?

Đọc bằng `get(key)` thường không bị chặn bởi cập nhật. Một luồng đọc có thể quan sát trạng thái trước hoặc sau một cập nhật đang diễn ra; nó không phải chờ toàn bộ map ngừng thay đổi mới được truy cập.

Với một khóa, cập nhật có quan hệ xảy ra-trước (happens-before) với lần đọc trả về giá trị không `null` phản ánh cập nhật đó. Điều này giúp chia sẻ giá trị qua map một cách có quy tắc về bộ nhớ. Nó không có nghĩa mọi luồng nhìn thấy mọi khóa như một bức ảnh chụp chung tại cùng một thời điểm.

Ví dụ minh họa:

```java
ConcurrentHashMap<String, String> status = new ConcurrentHashMap<>();
status.put("job-1", "READY");
String current = status.get("job-1");
```

Nếu không có thay đổi khác xen vào, `current` là `"READY"`. Nếu luồng khác cập nhật hoặc xóa cùng khóa, kết quả đọc phụ thuộc thao tác nào đã có hiệu lực ở thời điểm đó. Không thêm kết luận “đã đọc rồi thì giá trị sẽ giữ nguyên cho đến khi tôi dùng xong”.

### Không nhận khóa hoặc giá trị `null`

`put(null, value)` và `put(key, null)` không hợp lệ. `get(key)` trả `null` biểu diễn chưa tìm thấy ánh xạ ở lần đọc đó; nó không bị nhập nhằng với một giá trị `null` đã lưu.

Không vì thế mà coi `null` từ lần đọc trước là một lời hứa rằng khóa vẫn vắng mặt ở bước tiếp theo. Nếu cần “chỉ thêm khi chưa có”, hãy dùng thao tác kết hợp sẵn có.

## 3. Vì sao `get` rồi `put` vẫn làm mất cập nhật?

Đoạn sau dùng map đồng thời nhưng phép tăng chưa nguyên tử:

```java
Integer old = counts.getOrDefault("hits", 0);
counts.put("hits", old + 1);
```

Đây là đoạn minh họa giả định `counts` là `ConcurrentHashMap<String, Integer>` dùng chung. Có thể xảy ra thứ tự:

| Thời điểm | Luồng A | Luồng B |
| --- | --- | --- |
| 1 | Đọc được 10 | |
| 2 | | Đọc được 10 |
| 3 | Ghi 11 | |
| 4 | | Ghi 11 |

Hai lần tăng nhưng kết quả chỉ tăng từ 10 lên 11. Từng `get` và `put` đều an toàn; chuỗi thao tác của ứng dụng không có bảo đảm tương ứng.

Tương tự, kiểm tra `containsKey` rồi `put`, hoặc đọc giá trị rồi `remove(key)`, đều có khoảng đua giữa kiểm tra và hành động.

Lựa chọn thường dùng:

| Ý định | Thao tác phù hợp |
| --- | --- |
| Chỉ gắn giá trị nếu chưa có khóa | `putIfAbsent(key, value)` |
| Chỉ xóa nếu giá trị hiện tại khớp giá trị dự kiến | `remove(key, expectedValue)` |
| Chỉ thay nếu giá trị hiện tại khớp giá trị cũ | `replace(key, oldValue, newValue)` |
| Tạo giá trị khi chưa có | `computeIfAbsent(key, mappingFunction)` |
| Tính lại giá trị theo khóa và giá trị hiện tại | `compute(key, remappingFunction)` |
| Gộp một giá trị mới vào giá trị hiện có | `merge(key, value, remappingFunction)` |

Các thao tác có điều kiện như `putIfAbsent`, `remove(key, value)` và `replace(key, old, new)` có bảo đảm nguyên tử trong [hợp đồng `ConcurrentMap`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ConcurrentMap.html). Luôn kiểm tra giá trị trả về để biết điều kiện có khớp hay không.

## 4. Dùng `merge` cho phép tăng theo khóa

Với bộ đếm số nguyên đơn giản:

```java
counts.merge("hits", 1, Integer::sum);
```

Nếu chưa có `"hits"`, map gắn giá trị 1. Nếu đã có, hàm gộp cộng giá trị cũ với 1 rồi cập nhật trong thao tác nguyên tử của `ConcurrentHashMap` đối với khóa đó.

Không cần vòng `get` – cộng – `put`. Trong ví dụ với tổng nhỏ, `Integer` là đủ; với hệ thống đếm lớn cần chọn kiểu và chính sách tràn số phù hợp. Map đồng thời không tự phát hiện hoặc ngăn tràn số của phép cộng.

Các hàm `compute` và `merge` cần ngắn, đơn giản. Một số cập nhật khác có thể phải đợi khi hàm đang tính. Không dùng chúng như chỗ tùy tiện để gọi mạng chậm, chờ tài nguyên khác hoặc cập nhật đệ quy chính map đó.

Hàm trả `null` có ý nghĩa riêng: với `compute`, hoặc nhánh gộp của `merge`, nó có thể yêu cầu xóa ánh xạ. `null` không trở thành một giá trị được lưu. Vì vậy phải đọc đúng hợp đồng từng phương thức trước khi dùng `null` làm kết quả hàm.

## 5. Ví dụ chạy được: bốn luồng cùng tăng một khóa

Lưu thành `ConcurrentMapDemo.java`. Mỗi luồng tăng 1.000 lần; chỉ in kết quả sau khi đã nhận kết quả hoàn tất của mọi tác vụ.

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class ConcurrentMapDemo {
    public static void main(String[] args) throws Exception {
        ConcurrentHashMap<String, Integer> counts = new ConcurrentHashMap<>();
        int workers = 4;
        int repetitions = 1_000;
        CountDownLatch start = new CountDownLatch(1);
        ExecutorService pool = Executors.newFixedThreadPool(workers);
        List<Future<Void>> futures = new ArrayList<>();

        try {
            for (int i = 0; i < workers; i++) {
                futures.add(pool.submit(() -> {
                    start.await();
                    for (int n = 0; n < repetitions; n++) {
                        counts.merge("hits", 1, Integer::sum);
                    }
                    return null;
                }));
            }
            start.countDown();
            for (Future<Void> future : futures) {
                future.get(10, TimeUnit.SECONDS);
            }
        } finally {
            start.countDown();
            for (Future<Void> future : futures) {
                future.cancel(true);
            }
            pool.shutdownNow();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("workers did not terminate");
            }
        }

        System.out.println("hits: " + counts.get("hits"));
        System.out.println("replace expected: "
                + counts.replace("hits", 4_000, 0));
        System.out.println("hits after replace: " + counts.get("hits"));
        System.out.println("remove wrong value: " + counts.remove("hits", 1));
        System.out.println("remove expected value: " + counts.remove("hits", 0));
        System.out.println("contains hits: " + counts.containsKey("hits"));
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 ConcurrentMapDemo.java
java ConcurrentMapDemo
```

Stdout khi các tác vụ hoàn tất trong thời hạn của ví dụ:

```text
hits: 4000
replace expected: true
hits after replace: 0
remove wrong value: false
remove expected value: true
contains hits: false
```

Điểm quan sát:

1. `merge` bảo vệ toàn bộ phép cập nhật theo khóa, nên không bị mất các lần tăng như chuỗi `get` rồi `put`.
2. `Future.get()` xác nhận tác vụ hoàn tất thành công; không dùng `sleep` để đoán rằng các luồng đã xong. Thời hạn 10 giây ở đây áp dụng cho mỗi lần `get`, không phải một thời hạn tổng cho cả hệ thống.
3. Sau khi các luồng cập nhật đã xong, `replace` có điều kiện thấy đúng 4.000 và thay bằng 0.
4. `remove("hits", 1)` không xóa giá trị 0; `remove("hits", 0)` mới xóa. Kết quả kiểm tra và xóa thuộc cùng một thao tác.
5. Các số liệu in ở cuối không có luồng khác cập nhật xen vào, nên stdout có thứ tự và giá trị xác định. Việc in nguyên map nhiều khóa không được dùng để khẳng định thứ tự duyệt.

`CountDownLatch` chỉ mở cổng bắt đầu, không biến bốn luồng thành chạy đúng đồng thời trên phần cứng. Tính đúng của phép đếm không phụ thuộc chúng có bắt đầu ở cùng một nanosecond hay không.

## 6. `computeIfAbsent`: tạo theo nhu cầu, không phải cam kết chạy một lần mãi mãi

Ví dụ minh họa tạo một giá trị khi khóa chưa có:

```java
String label = labels.computeIfAbsent("vi", key -> "Tiếng Việt");
```

Giả định `labels` là `ConcurrentHashMap<String, String>`. Nếu đã có giá trị cho `"vi"`, hàm không cần được gọi. Nếu chưa có, hàm tính giá trị để gắn vào map.

Với chính `ConcurrentHashMap`, việc tính và gắn được thực hiện nguyên tử; không được suy rộng cùng số lần gọi hàm sang mọi lớp chỉ vì chúng cũng có phương thức mang tên `computeIfAbsent`.

Cũng không suy ra hàm chỉ được gọi một lần trong toàn bộ vòng đời ứng dụng:

- Nếu hàm trả `null`, không có ánh xạ mới được lưu, nên lần gọi sau có thể tính lại.
- Nếu hàm ném ngoại lệ, việc khởi tạo không thành công; lần sau có thể thử lại.
- Nếu ánh xạ bị xóa, một lần gọi tương lai có thể tạo lại.

Không dùng tác dụng phụ bên ngoài như gửi tiền, gửi thông điệp hoặc ghi dữ liệu không thể lặp lại rồi mặc định map đã bảo đảm chỉ thực hiện một lần. Tính nguyên tử của ánh xạ không biến hoạt động bên ngoài thành cùng một giao dịch.

Hàm tính không được sửa chính map trong quá trình tính. Một số cập nhật đệ quy có thể bị phát hiện và báo `IllegalStateException`; không xem khả năng phát hiện đó là lý do để viết hàm có vòng phụ thuộc.

## 7. Map an toàn không làm mọi đối tượng giá trị trở nên an toàn

Đoạn sau vẫn có vấn đề nếu nhiều luồng thêm vào cùng danh sách:

```java
ConcurrentHashMap<String, List<String>> groups = new ConcurrentHashMap<>();
groups.computeIfAbsent("team", key -> new ArrayList<>()).add("member");
```

`computeIfAbsent` giúp quản lý ánh xạ `"team" → danh sách`. Lời gọi `.add` diễn ra sau khi lấy được tham chiếu và là thao tác của `ArrayList`, không thuộc phần bảo vệ của map. Nhiều luồng sửa cùng danh sách không tự được đồng bộ.

Cần chọn mô hình theo yêu cầu: giá trị có cơ chế đồng thời riêng, giá trị bất biến được thay bằng một đối tượng mới, hoặc một cơ chế khóa mà mọi bên truy cập cùng tuân theo.

Ví dụ dùng giá trị bất biến với `compute`:

```java
record State(int version, String status) {}
ConcurrentHashMap<String, State> states = new ConcurrentHashMap<>();
states.put("job-1", new State(1, "NEW"));
states.computeIfPresent("job-1", (key, old) ->
        new State(old.version() + 1, "READY"));
```

Đây là đoạn để đặt trong ngữ cảnh Java thích hợp. `State` chỉ giữ `int` và `String`, nên việc thay cả giá trị không chia sẻ một trường danh sách có thể sửa. Với một record chứa đối tượng có thể sửa, record không tự làm đối tượng con đó bất biến.

Bảo đảm hiển thị bộ nhớ khi đưa đối tượng vào map chỉ bao phủ theo quan hệ đã được thiết lập; các thay đổi không đồng bộ vào trường của đối tượng **sau đó** vẫn cần cơ chế riêng.

## 8. Bộ đếm bằng `LongAdder`: phân biệt thống kê với điều kiện nghiệp vụ

Khi nhiều luồng cùng cập nhật thống kê theo khóa, có thể dùng giá trị `LongAdder`:

```java
ConcurrentHashMap<String, LongAdder> frequencies = new ConcurrentHashMap<>();
frequencies.computeIfAbsent("/home", key -> new LongAdder()).increment();
```

Đoạn minh họa cần import `java.util.concurrent.atomic.LongAdder`. Map quản lý việc tìm hoặc tạo bộ đếm; `LongAdder` tự hỗ trợ các cập nhật đồng thời bên trong nó. Khác với ví dụ `ArrayList`, bản thân giá trị có cơ chế phù hợp cho phép cộng nhiều luồng.

Tuy nhiên, `sum()` không phải ảnh chụp nguyên tử khi vẫn còn cập nhật đồng thời. [Tài liệu `LongAdder`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/atomic/LongAdder.html) định hướng kiểu này cho thống kê khi có tranh chấp, không phải mọi quyết định đồng bộ yêu cầu một giá trị chính xác tại thời điểm kiểm tra.

Đừng viết “nếu tổng còn dưới hạn thì tăng” bằng hai bước `sum` rồi `increment` và cho rằng đã kiểm soát hạn mức nguyên tử. Với nghiệp vụ cần kiểm tra và tăng như một hành động, phải chọn cơ chế đáp ứng chính điều kiện đó.

Mẫu trên cũng cần chính sách vòng đời ánh xạ. Nếu một luồng lấy được bộ đếm rồi luồng khác xóa hoặc thay ánh xạ trước khi lần tăng diễn ra, lần tăng có thể tác động vào bộ đếm đã không còn nằm trong map. Nếu cần thống kê xuyên suốt lần xóa hoặc thay, hãy quản lý quá trình đó rõ ràng; tính an toàn của từng đối tượng chưa giải quyết sự phối hợp giữa chúng.

## 9. Duyệt map không phải ảnh chụp bất biến

Iterator của `ConcurrentHashMap` có tính nhất quán yếu (weakly consistent): có thể duyệt trong khi các luồng khác thay đổi map, không dùng `ConcurrentModificationException` để báo mọi thay đổi đồng thời. Nó có thể phản ánh các ánh xạ được quan sát ở những thời điểm khác nhau.

Hệ quả khi thiết kế:

- Có thể dùng để quan sát hoặc tổng hợp khi chấp nhận dữ liệu đang biến động.
- Không bảo đảm mọi phần tử nhìn thấy đều tồn tại đồng thời trong một trạng thái chung.
- Không dựa vào thứ tự duyệt vì map không bảo đảm sắp xếp khóa hoặc thứ tự thêm.
- Không chia sẻ một iterator cho nhiều luồng rồi mặc định iterator đó an toàn theo cùng cách với map.

`size()`, `isEmpty()` và các kết quả tổng hợp cũng có thể chỉ phản ánh trạng thái chuyển tiếp khi đang có cập nhật. Không dùng `if (map.size() < limit) map.put(...)` làm một hạn mức toàn cục có bảo đảm.

Sao chép sang map mới trong lúc dữ liệu vẫn thay đổi tạo ra một bản sao đã thu thập, nhưng không tự chứng minh đó là ảnh chụp nguyên tử tại một thời điểm. Nếu báo cáo hoặc nghiệp vụ đòi hỏi ảnh chụp nhất quán, cần cơ chế riêng như ngừng cập nhật trong lúc chụp hoặc quản lý trạng thái theo phiên bản.

## 10. Nhiều khóa, khóa ngoài và giới hạn tài nguyên

Hai lời gọi `compute` trên hai tài khoản không tự trở thành một giao dịch chuyển tiền. Luồng khác có thể quan sát trạng thái nằm giữa hai lần cập nhật. Muốn bảo toàn ràng buộc nhiều khóa, cần thiết kế khóa chung, giao dịch hoặc gom trạng thái liên quan vào một đơn vị cập nhật phù hợp.

Đặt `synchronized (map)` quanh một đoạn mã chỉ loại trừ các luồng cũng lấy đúng monitor đó. Những luồng gọi `get`, `put`, `merge` bình thường không tự tham gia quy tắc khóa ngoài của ứng dụng. Không xem đó là cách khóa toàn bảng theo cơ chế nội bộ của `ConcurrentHashMap`.

Ngoài ra:

- Khóa cần có `equals` và `hashCode` ổn định khi được dùng trong map. Sửa trường tham gia tính khóa có thể làm việc tra cứu không còn đúng kỳ vọng.
- Phân bố băm kém hoặc nhiều cập nhật dồn vào một khóa có thể tạo tranh chấp; dùng map đồng thời không loại bỏ mọi điểm nghẽn.
- `initialCapacity` là thông tin để xác định kích thước ban đầu, không phải số ánh xạ tối đa. Map có thể tăng và vẫn cần ngân sách bộ nhớ.
- Map dùng làm bộ nhớ đệm không tự có hết hạn, loại bỏ theo dung lượng hoặc lưu bền. Các yêu cầu đó cần được thiết kế riêng.

Không cần giả định một cấu trúc khóa nội bộ cố định để viết chương trình đúng. Hãy dựa vào hợp đồng API, đo hiệu năng với tải đại diện và giữ rõ ranh giới thao tác nguyên tử.

## 11. Tự kiểm tra

1. Vì sao thay `HashMap` bằng `ConcurrentHashMap` chưa sửa được `get` rồi `put(old + 1)`?
2. `computeIfAbsent` trả `null` có lưu một giá trị `null` trong map không?
3. Vì sao một `ArrayList` lấy từ map vẫn có thể có lỗi khi nhiều luồng gọi `add`?
4. Iterator không ném `ConcurrentModificationException` có đồng nghĩa với ảnh chụp nhất quán không?
5. Vì sao `merge` trên khóa A rồi `merge` trên khóa B chưa tạo một giao dịch hai khóa?

Gợi ý: (1) Đọc và ghi vẫn là hai thao tác tách rời. (2) Không lưu ánh xạ mới. (3) Map chỉ bảo vệ ánh xạ, không tự đồng bộ bên trong giá trị. (4) Không, quá trình duyệt có thể phản ánh các thời điểm khác nhau. (5) Bảo đảm nguyên tử của từng lời gọi không gộp cả chuỗi thành một thao tác duy nhất.
