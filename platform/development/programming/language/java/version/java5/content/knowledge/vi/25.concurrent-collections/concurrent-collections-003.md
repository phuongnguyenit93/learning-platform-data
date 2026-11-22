# putIfAbsent, replace và remove có điều kiện

## 1. Vấn đề: kiểm tra rồi thay đổi là hai thời điểm khác nhau

Một collection an toàn cho nhiều luồng bảo vệ từng thao tác theo hợp đồng của nó. Điều đó không tự làm cho một chuỗi thao tác của ứng dụng trở thành nguyên tử. Nếu một luồng kiểm tra map rồi quyết định thêm, thay hoặc xóa, luồng khác có thể thay đổi dữ liệu giữa hai bước.

Ví dụ trong một bảng trạng thái công việc, hai luồng cùng thấy chưa có `job-1`. Nếu cả hai đều dùng `put` sau bước kiểm tra, bên đến sau có thể ghi đè trạng thái do bên trước vừa tạo. Tương tự, một luồng dọn dẹp có thể xóa nhầm phiên bản mới nếu chỉ nhớ rằng trước đó khóa tồn tại.

`ConcurrentMap<K,V>` cung cấp các thao tác kết hợp điều kiện và thay đổi: `putIfAbsent`, các dạng `replace`, và `remove(key, expectedValue)`. Chúng giúp diễn đạt quy tắc “chỉ thay đổi nếu trạng thái hiện tại vẫn thỏa điều kiện” trong một thao tác nguyên tử.

Bài dùng `ConcurrentHashMap` để minh họa. Đây là các API vẫn áp dụng trong Java hiện đại; ví dụ chạy được với Java 17 trở lên.

## 2. Phân biệt các chữ ký và giá trị trả về

Trong bảng dưới, `ConcurrentHashMap` không cho phép khóa hoặc giá trị `null`, nên kết quả `null` không lẫn với một giá trị `null` hợp lệ đang được lưu.

| Phương thức | Điều kiện thay đổi | Nếu thay đổi thành công | Nếu không thỏa điều kiện |
| --- | --- | --- | --- |
| `V putIfAbsent(K key, V value)` | Chưa có ánh xạ cho khóa | Thêm `value`, trả `null` | Giữ nguyên, trả giá trị đang có tại lần kiểm tra nguyên tử |
| `V replace(K key, V value)` | Khóa đang có ánh xạ | Thay bằng `value`, trả giá trị trước đó | Không thêm khóa mới, trả `null` |
| `boolean replace(K key, V expected, V update)` | Khóa đang ánh xạ tới giá trị bằng `expected` | Thay bằng `update`, trả `true` | Giữ nguyên, trả `false` |
| `boolean remove(Object key, Object expected)` | Khóa đang ánh xạ tới giá trị bằng `expected` | Xóa ánh xạ, trả `true` | Giữ nguyên, trả `false` |

“Có điều kiện” không đồng nghĩa mọi phương thức đều trả `boolean`. `putIfAbsent` và `replace(key, value)` trả về giá trị cũ, còn hai dạng đối chiếu giá trị mong đợi trả về cờ thành công.

Thành công ở đây nói về thao tác map đó. Nó không cam kết dữ liệu vẫn y nguyên sau khi phương thức trả về: một luồng khác có thể cập nhật tiếp ngay lập tức. Hợp đồng nguyên tử của các thao tác được quy định trong [ConcurrentMap — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ConcurrentMap.html).

## 3. putIfAbsent: tạo ánh xạ nếu chưa có

Đoạn kiểm tra rồi thêm sau đây không gộp thành một thao tác nguyên tử chỉ nhờ dùng `ConcurrentHashMap`:

```java
// Đoạn minh họa có tranh chấp; states là ConcurrentMap<String, String>.
if (!states.containsKey("job-1")) {
    states.put("job-1", "PENDING");
}
```

Lịch chạy có thể là: luồng A kiểm tra và thấy chưa có; luồng B cũng thấy chưa có rồi thêm trạng thái của nó; luồng A tiếp tục `put` và ghi đè. Mỗi lời gọi riêng vẫn an toàn, nhưng quy tắc “chỉ tạo khi chưa có” của ứng dụng đã không được giữ.

Viết trực tiếp bằng thao tác kết hợp:

```java
// Đoạn minh họa trong phương thức.
String previous = states.putIfAbsent("job-1", "PENDING");
if (previous == null) {
    System.out.println("This call created the mapping");
} else {
    System.out.println("Already present: " + previous);
}
```

Nếu nhiều luồng cùng tranh thêm một khóa đang vắng, không có luồng nào xóa khóa trong quá trình đó, chỉ một lời gọi thành công trong việc tạo ánh xạ. Các lời gọi còn lại thấy giá trị đã có. Đây là nền tảng cho một bảng nhận quyền xử lý trong cùng tiến trình, nhưng chưa phải một giao dịch bảo đảm tác động nghiệp vụ chỉ diễn ra đúng một lần.

Giá trị đối số đã được tính trước khi gọi phương thức. Ví dụ `putIfAbsent(key, createValue())` vẫn gọi `createValue()` ngay cả khi khóa đã có. Nhiều luồng có thể cùng tạo ứng viên, dù chỉ một ứng viên được lưu. Nếu việc tạo tốn kém hoặc có tác động bên ngoài, không suy rằng `putIfAbsent` đã khiến việc tạo chỉ chạy một lần. `computeIfAbsent` là API khác cần đọc hợp đồng riêng khi nhu cầu là tính giá trị theo khóa.

## 4. Hai dạng replace giải quyết hai quy tắc khác nhau

### replace(key, update): chỉ thay khi khóa tồn tại

Dạng hai đối số phù hợp khi không muốn tạo một khóa mới. Nó không kiểm tra rằng giá trị hiện tại còn bằng giá trị mà luồng đã đọc trước đó.

Ví dụ `states.replace("job-1", "RUNNING")` thay giá trị nếu `job-1` đang có ánh xạ và trả về giá trị cũ. Nếu luồng khác vừa đổi từ `PENDING` sang `CANCELLED`, lời gọi này vẫn có thể thay `CANCELLED` thành `RUNNING` vì điều kiện duy nhất là khóa tồn tại. Nếu nghiệp vụ chỉ cho phép chuyển từ `PENDING`, dạng này chưa đủ.

### replace(key, expected, update): chỉ thay đúng trạng thái mong đợi

```java
// Đoạn minh họa trong phương thức.
boolean started = states.replace("job-1", "PENDING", "RUNNING");
if (!started) {
    System.out.println("Job is absent or no longer pending");
}
```

Việc kiểm tra giá trị hiện tại và việc thay được gộp nguyên tử. Nếu giá trị đã khác `PENDING`, lời gọi không ghi đè. `false` không nhất thiết là lỗi hệ thống; nó thường có nghĩa dữ liệu đã thay đổi hoặc khóa không còn tồn tại, nên bên gọi cần đọc lại hoặc dừng theo quy tắc nghiệp vụ.

Không thực hiện tác động bên ngoài trước rồi mới dùng `replace` để quyết định mình có quyền thực hiện hay không. Nếu hai luồng đều gọi dịch vụ thanh toán trước khi tranh chuyển trạng thái, tính nguyên tử của map không thu hồi được lần thanh toán thừa. Việc nhận quyền và tác động ngoài tiến trình cần giao thức phù hợp.

## 5. remove(key, expected): không xóa nhầm dữ liệu mới

Giả sử một tác vụ dọn dẹp đã đọc `session -> token-A`. Trong lúc nó xử lý, một tác vụ khác đổi ánh xạ thành `session -> token-B`.

```text
T1: đọc session -> token-A
T2: đổi session -> token-B
T1: remove(session)             -> có thể xóa nhầm token-B

T1: remove(session, token-A)    -> false, giữ lại token-B
```

`remove(key)` chỉ dựa vào khóa và trả giá trị bị xóa. `remove(key, expected)` đối chiếu cả giá trị hiện tại và trả cờ thành công. Dạng có điều kiện hữu ích khi xóa một đăng ký, một giá trị cache hoặc một quyền xử lý mà luồng hiện tại đã quan sát, trong khi khóa đó có thể được thay bằng dữ liệu mới.

Điều kiện vẫn chỉ là so sánh giá trị, không tự kiểm tra toàn bộ lịch sử của khóa. Cần lưu ý cách định nghĩa `equals` và phiên bản dữ liệu.

## 6. Điều kiện dùng sự bằng nhau, không phải luôn dùng `==`

`replace(key, expected, update)` và `remove(key, expected)` so sánh giá trị theo quy tắc bằng nhau của đối tượng. Hai đối tượng khác địa chỉ nhưng `equals` trả `true` vẫn có thể thỏa điều kiện. Không mặc định đó là phép so sánh cùng một tham chiếu như `==`.

Điều này hữu ích với giá trị bất biến như `String` hoặc `record`: có thể mô tả trạng thái mong đợi bằng dữ liệu. Nhưng nó cũng có nghĩa một giá trị đã rời đi rồi quay lại bằng giá trị cũ vẫn có thể được xem là trùng.

Ví dụ trạng thái biến đổi `PENDING -> RUNNING -> PENDING`. Một luồng đã đọc `PENDING` từ đầu dùng `replace(key, "PENDING", "RUNNING")` sau đó vẫn có thể thành công. Phương thức không biết giữa hai thời điểm đã có một vòng thay đổi. Hiện tượng giá trị A đổi sang B rồi trở lại A thường được gọi là ABA.

Nếu nghiệp vụ cần nhận diện đúng phiên bản, có thể lưu trạng thái cùng một số phiên bản không tái sử dụng trong phạm vi cần phân biệt:

```java
// Đoạn mô hình dữ liệu minh họa.
record State(String status, long version) {}

// statesWithVersion là ConcurrentMap<String, State> trong phương thức hiện tại.
State observed = statesWithVersion.get("job-1");
if (observed != null && observed.status().equals("PENDING")) {
    State update = new State("RUNNING", observed.version() + 1);
    boolean changed = statesWithVersion.replace("job-1", observed, update);
}
```

`record` so sánh cả `status` và `version`, nên cùng trạng thái nhưng phiên bản khác không bị xem như một giá trị mong đợi cũ. Cách này chỉ đúng nếu mọi đường cập nhật đều tuân theo quy tắc phiên bản và không xóa/tạo lại bằng một phiên bản cũ. Nó không tự giải quyết lỗi tràn số hay phối hợp trạng thái giữa nhiều tiến trình.

Giữ giá trị bất biến cũng giúp tránh trường hợp luồng khác thay đổi trực tiếp các trường của một đối tượng đang lưu, làm điều kiện so sánh khó hiểu. Map đồng thời bảo vệ quan hệ khóa–giá trị; nó không tự biến mọi đối tượng giá trị thành đối tượng an toàn cho nhiều luồng.

## 7. Chương trình chạy đầy đủ

Lưu vào `ConditionalMapDemo.java`. Phần đầu kiểm tra từng giá trị trả về; phần sau cho hai luồng cùng tranh tạo một khóa. Chương trình chỉ in tổng số lời gọi tạo thành công, không khẳng định luồng có tên nào phải thắng.

```java
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicInteger;

public class ConditionalMapDemo {
    private static void check(boolean condition) {
        if (!condition) {
            throw new AssertionError("Unexpected map result");
        }
    }

    public static void main(String[] args) throws InterruptedException {
        ConcurrentMap<String, String> states = new ConcurrentHashMap<>();

        String first = states.putIfAbsent("job-1", "PENDING");
        check(first == null);
        System.out.println("first putIfAbsent: " + first);

        String second = states.putIfAbsent("job-1", "OTHER");
        check("PENDING".equals(second));
        System.out.println("second putIfAbsent: " + second);

        check(states.replace("missing", "RUNNING") == null);
        System.out.println("replace missing: null");

        String previous = states.replace("job-1", "RUNNING");
        check("PENDING".equals(previous));
        System.out.println("replace previous: " + previous);

        boolean staleReplace =
                states.replace("job-1", "PENDING", "DONE");
        check(!staleReplace);
        System.out.println("replace with stale expected: " + staleReplace);

        boolean changed = states.replace("job-1", "RUNNING", "DONE");
        check(changed);
        System.out.println("replace with current expected: " + changed);

        boolean staleRemove = states.remove("job-1", "RUNNING");
        check(!staleRemove);
        System.out.println("remove with stale expected: " + staleRemove);

        boolean removed = states.remove("job-1", "DONE");
        check(removed);
        System.out.println("remove with current expected: " + removed);

        CountDownLatch start = new CountDownLatch(1);
        AtomicInteger winners = new AtomicInteger();

        Runnable claim = () -> {
            try {
                start.await();
                if (states.putIfAbsent("job-2", "CLAIMED") == null) {
                    winners.incrementAndGet();
                }
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        };

        Thread one = new Thread(claim, "one");
        Thread two = new Thread(claim, "two");
        one.start();
        two.start();
        start.countDown();
        one.join();
        two.join();

        check(winners.get() == 1);
        check("CLAIMED".equals(states.get("job-2")));
        System.out.println("concurrent claim winners: " + winners.get());
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 ConditionalMapDemo.java
java ConditionalMapDemo
```

Stdout:

```text
first putIfAbsent: null
second putIfAbsent: PENDING
replace missing: null
replace previous: PENDING
replace with stale expected: false
replace with current expected: true
remove with stale expected: false
remove with current expected: true
concurrent claim winners: 1
```

`CountDownLatch` mở cho cả hai luồng bắt đầu thử; nó không bắt buộc chúng chạy đúng cùng một thời điểm. Dù thứ tự lập lịch nào, không có bên xóa `job-2` nên chỉ một lần `putIfAbsent` có thể tạo ánh xạ mới. `join()` đợi cả hai lời gọi kết thúc trước khi kiểm tra kết quả.

Hai luồng dùng cùng chuỗi `CLAIMED` trong ví dụ để chỉ kiểm tra cơ chế tạo một lần. Nếu xây hệ thống nhận quyền thật, giá trị cần biểu diễn đúng danh tính/lần nhận quyền để việc cập nhật hoặc giải phóng có điều kiện không nhầm giữa các lượt.

## 8. Phạm vi bảo đảm và các lỗi cần tránh

### Chọn đúng triển khai đồng thời

Các tên phương thức này cũng xuất hiện trên `Map` trong Java hiện đại, nhưng không được suy rằng gọi chúng trên mọi `Map` đều có cùng bảo đảm nguyên tử khi nhiều luồng cùng sử dụng. Đặc biệt, đổi `ConcurrentHashMap` thành `HashMap` không giữ nguyên hợp đồng đồng thời. Cần dựa vào triển khai và hợp đồng của [Map — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Map.html) cùng `ConcurrentMap`.

`ConcurrentHashMap` cấm cả khóa `null` lẫn giá trị `null`. Vì vậy, trong bài, `putIfAbsent` trả `null` là tín hiệu lời gọi đã tạo ánh xạ; `replace(key, value)` trả `null` nghĩa khóa không có tại lần thao tác. Không suy rộng cách diễn giải này cho một triển khai khác cho phép giá trị `null`; phải xem hợp đồng của nó. Xem [ConcurrentHashMap — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html).

### Nguyên tử từng thao tác không phải giao dịch nhiều thao tác

`replace(k1, ...)` thành công rồi `replace(k2, ...)` thất bại không tự hoàn tác lần thay đầu. Nếu quy tắc nghiệp vụ ràng buộc nhiều khóa, cần mô hình dữ liệu hoặc cơ chế phối hợp phù hợp, không chỉ ghép nhiều phương thức nguyên tử.

Tương tự, `replace(key, map.get(key) + 1)` không bảo đảm một phép tăng nguyên tử. Bước đọc và lần thay hai đối số tách rời; hai luồng có thể cùng tính một kết quả rồi làm mất một lần tăng. Có thể dùng một phép cập nhật theo giá trị mong đợi với chiến lược đọc lại/thử lại, hoặc một API tính toán nguyên tử phù hợp. Không thử lại tác động bên ngoài tùy ý vì có thể thực hiện trùng.

`true` hay một giá trị cũ trả về chỉ là bằng chứng của lần cập nhật map. Nó không phải xác nhận dữ liệu đã lưu bền vững, không phải khóa phân tán, và không tự bảo đảm nghiệp vụ sẽ hoàn tất nếu luồng lỗi ngay sau khi nhận quyền.

## 9. Chọn nhanh theo ý định

| Ý định | Phương thức |
| --- | --- |
| Tạo nếu chưa có, nếu có thì lấy lại giá trị hiện hành | `putIfAbsent(key, candidate)` |
| Chỉ thay khóa đang tồn tại, không cần đối chiếu giá trị cũ | `replace(key, update)` |
| Chỉ chuyển từ đúng trạng thái/phiên bản đã mong đợi | `replace(key, expected, update)` |
| Chỉ xóa nếu ánh xạ vẫn bằng giá trị mình đã quan sát | `remove(key, expected)` |

## 10. Tự kiểm tra

1. `putIfAbsent` trên `ConcurrentHashMap` trả `null` có nghĩa đã thất bại không? Không; trong trường hợp này nó cho biết chưa có ánh xạ và lời gọi đã thêm thành công.
2. `replace(key, update)` có tạo khóa nếu khóa chưa có không? Không.
3. `replace(key, expected, update)` trả `false` có ghi `update` vào map không? Không.
4. Một giá trị mới đã thay thế giá trị cũ. Muốn dọn dẹp mà không xóa nhầm giá trị mới, nên dùng dạng nào? `remove(key, expectedOldValue)`.
5. Giá trị A đổi sang B rồi trở lại A có bị phát hiện chỉ bằng đối chiếu A không? Không; cần phiên bản hoặc cơ chế khác nếu lịch sử thay đổi quan trọng.
6. Map đồng thời có làm mọi trường bên trong một giá trị mutable tự an toàn không? Không; cần thiết kế giá trị và việc truy cập riêng.
