# ConcurrentMap và các thao tác cập nhật nguyên tử

Một bản đồ dùng chung có thể bị nhiều luồng kiểm tra và cập nhật cùng lúc: đăng ký một tên chưa tồn tại, tăng bộ đếm, thay trạng thái nếu nó vẫn còn là trạng thái đã đọc. Vấn đề thường không nằm ở một lệnh `get` hay `put`, mà ở **khoảng hở giữa các lệnh**.

`ConcurrentMap<K, V>` mở rộng `Map<K, V>` với các bảo đảm phục vụ truy cập đồng thời, đặc biệt là những thao tác điều kiện nguyên tử. Trong bài, kiểu khai báo là `ConcurrentMap` và triển khai cụ thể là `ConcurrentHashMap`; các ví dụ dùng API hiện hành, chạy với Java 17 trở lên.

## 1. Vì sao get rồi put vẫn mất cập nhật?

Giả sử `counts` đã là một bản đồ an toàn luồng. Đoạn sau vẫn không phải phép tăng nguyên tử:

```java
// Minh họa lỗi đọc–sửa–ghi; counts là bản đồ dùng chung.
int oldValue = counts.getOrDefault("completed", 0);
counts.put("completed", oldValue + 1);
```

Hai luồng có thể xen kẽ:

```text
Giá trị ban đầu: 10
Luồng A đọc 10
Luồng B đọc 10
Luồng A ghi 11
Luồng B ghi 11
Kết quả: 11, dù có hai lần tăng.
```

Mỗi phương thức có thể an toàn khi gọi đồng thời, nhưng ghép nhiều phương thức không tự tạo một hành động không thể bị xen kẽ. Cách biểu đạt đúng mục tiêu tăng trên một khóa là:

```java
counts.merge("completed", 1, Integer::sum);
```

Nếu chưa có khóa, dùng giá trị 1; nếu đã có, cộng giá trị cũ với 1 bằng cơ chế cập nhật của bản đồ. Quy tắc về thao tác điều kiện nằm trong [ConcurrentMap](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ConcurrentMap.html).

## 2. Các thao tác điều kiện cơ bản

Bảng dưới áp dụng cho ví dụ dùng `ConcurrentHashMap`, nơi không cho phép khóa hay giá trị `null`:

| Phương thức | Điều kiện cập nhật | Giá trị trả về |
|---|---|---|
| `putIfAbsent(k, v)` | Chỉ thêm nếu chưa có ánh xạ cho k | Giá trị cũ; `null` nếu lần gọi thêm mới thành công |
| `remove(k, expected)` | Chỉ xóa nếu giá trị hiện tại bằng expected | `true` nếu xóa thành công |
| `replace(k, expected, newValue)` | Chỉ thay nếu giá trị hiện tại bằng expected | `true` nếu thay thành công |
| `replace(k, newValue)` | Chỉ thay nếu khóa đang có ánh xạ | Giá trị cũ; `null` nếu khóa vắng mặt |

Điều kiện kiểm tra và tác động lên ánh xạ được thực hiện như một thao tác nguyên tử. Không viết lại thành `containsKey` → `get` → `put` hoặc `remove` nếu mục tiêu là giữ điều kiện đúng ngay lúc cập nhật.

Ví dụ suy luận:

```java
// Đoạn minh họa trong phạm vi có ConcurrentMap<String, String> states.
states.putIfAbsent("job-42", "NEW");
boolean started = states.replace("job-42", "NEW", "RUNNING");
```

`started` là `true` nghĩa là **lần gọi này** đã chuyển trạng thái theo điều kiện. Nếu luồng khác đã đổi giá trị trước, lần gọi trả `false`; ứng dụng quyết định đọc lại, từ chối hay thử lại theo nghiệp vụ.

Việc so khớp giá trị dùng ý nghĩa bằng nhau qua `equals`, không phải mặc nhiên so sánh định danh đối tượng bằng `==`. Nếu trạng thái có thể đi từ A sang B rồi trở lại A, phép thay với expected A vẫn có thể thành công. Nó không phát hiện lịch sử thay đổi ở giữa. Khi lịch sử quan trọng, cần đưa phiên bản vào trạng thái được so sánh.

### putIfAbsent không trì hoãn việc tạo đối tượng

Trong lời gọi `cache.putIfAbsent(key, createValue())`, Java tính `createValue()` trước khi gọi phương thức. Vì vậy, dù khóa đã có, việc tạo ứng viên vẫn xảy ra. `computeIfAbsent` phù hợp hơn khi cần tính giá trị chỉ trong trường hợp thiếu, nhưng phải hiểu hợp đồng callback ở phần sau.

## 3. compute và merge: chọn theo mục đích

Trong ngữ cảnh không lưu giá trị `null`:

| Phương thức | Khi nào hàm tính được dùng? | Ý nghĩa kết quả `null` từ hàm |
|---|---|---|
| `computeIfAbsent(k, f)` | Khi khóa thiếu | Không thiết lập ánh xạ mới |
| `computeIfPresent(k, f)` | Khi khóa đang có giá trị | Xóa ánh xạ đang được cập nhật |
| `compute(k, f)` | Tính với giá trị hiện tại, hoặc `null` nếu thiếu | Không giữ ánh xạ cho khóa |
| `merge(k, incoming, f)` | Khi đã có giá trị; nếu thiếu thì dùng incoming | Xóa ánh xạ |

Với `compute`, hàm nhận `(key, currentValue)`. Với `merge`, hàm ghép nhận `(oldValue, incomingValue)`, không nhận khóa. Giá trị `incoming` của `merge` phải khác `null`.

Ví dụ minh họa lựa chọn:

```java
// scores là ConcurrentMap<String, Integer> dùng ConcurrentHashMap.
scores.computeIfAbsent("bonus", key -> 10);
scores.computeIfPresent("bonus", (key, old) -> old + 5);
scores.merge("bonus", 2, Integer::sum);
scores.compute("bonus", (key, old) -> null); // Xóa ánh xạ.
```

Không nhầm `return null` trong hàm tính với việc lưu giá trị `null`. Trong `ConcurrentHashMap`, `null` không được lưu làm khóa hay giá trị; tại các API tính toán, nó là tín hiệu điều khiển kết quả cập nhật.

Không suy rộng quy tắc cấm `null` của lớp này thành một khẳng định cho mọi triển khai `ConcurrentMap`. Giao diện cho phép triển khai công bố chính sách riêng, và những triển khai hỗ trợ `null` phải đáp ứng lại hợp đồng của các phương thức mặc định liên quan. [Hợp đồng Map và các hạn chế giá trị](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Map.html).

## 4. Chương trình chạy đầy đủ

Lưu thành `ConcurrentMapDemo.java`:

```java
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;

public class ConcurrentMapDemo {
    public static void main(String[] args) throws InterruptedException {
        ConcurrentMap<String, Integer> scores = new ConcurrentHashMap<>();

        System.out.println("first insert previous: "
                + scores.putIfAbsent("alice", 1));
        System.out.println("second insert previous: "
                + scores.putIfAbsent("alice", 99));
        System.out.println("replace expected 1: "
                + scores.replace("alice", 1, 2));
        System.out.println("replace stale 1: "
                + scores.replace("alice", 1, 3));
        System.out.println("remove stale 1: "
                + scores.remove("alice", 1));
        System.out.println("alice: " + scores.get("alice"));

        System.out.println("initial bonus: "
                + scores.computeIfAbsent("bonus", key -> 10));
        System.out.println("updated bonus: "
                + scores.computeIfPresent("bonus", (key, value) -> value + 5));
        System.out.println("merged bonus: "
                + scores.merge("bonus", 2, Integer::sum));
        scores.compute("bonus", (key, value) -> null);
        System.out.println("bonus present: " + scores.containsKey("bonus"));

        ConcurrentMap<String, Integer> counts = new ConcurrentHashMap<>();
        Runnable increment = () -> {
            for (int i = 0; i < 1_000; i++) {
                counts.merge("completed", 1, Integer::sum);
            }
        };

        Thread first = new Thread(increment, "first");
        Thread second = new Thread(increment, "second");
        first.start();
        second.start();
        first.join();
        second.join();

        System.out.println("completed: " + counts.get("completed"));
        System.out.println("remove current 2: " + scores.remove("alice", 2));
        System.out.println("alice present: " + scores.containsKey("alice"));
    }
}
```

Biên dịch và chạy:

```shell
javac -encoding UTF-8 --release 17 ConcurrentMapDemo.java
java ConcurrentMapDemo
```

Stdout:

```text
first insert previous: null
second insert previous: 1
replace expected 1: true
replace stale 1: false
remove stale 1: false
alice: 2
initial bonus: 10
updated bonus: 15
merged bonus: 17
bonus present: false
completed: 2000
remove current 2: true
alice present: false
```

Những điểm cần rút ra:

- Lần thêm thứ hai không ghi đè 1 bằng 99, mà trả giá trị đã tồn tại.
- Sau khi 1 được thay bằng 2, các thao tác kỳ vọng giá trị cũ 1 thất bại. Chúng không xóa hoặc ghi đè một cập nhật mới hơn.
- Các hàm tính thay đổi `bonus` theo chuỗi 10 → 15 → 17, rồi xóa ánh xạ bằng kết quả `null`.
- Hai luồng thực hiện tổng cộng 2.000 lần `merge` trên cùng khóa. Các phép cộng không bị mất bởi lỗi đọc–sửa–ghi. `join()` bảo đảm chương trình đợi cả hai luồng hoàn tất trước khi in tổng cuối.

Giá trị 2.000 là kết quả cho miền dữ liệu nhỏ của ví dụ. Tính nguyên tử không ngăn số nguyên tràn khi bộ đếm thật vượt miền `Integer`; cần chọn kiểu số và chính sách tràn phù hợp.

## 5. Phân biệt hợp đồng giao diện và lớp triển khai

Đây là điểm quan trọng khi viết hàm nhận tham số kiểu `ConcurrentMap`.

### Với ConcurrentMap nói chung

Một số phương thức mặc định như `compute`, `computeIfPresent`, `merge` và `replaceAll` dùng cơ chế thử cập nhật theo điều kiện rồi thử lại nếu gặp cạnh tranh. Hàm tính có thể được gọi nhiều lần cho cùng khóa trong quá trình này.

Với cách mặc định của `computeIfAbsent`, nhiều luồng có thể cùng thấy khóa thiếu và cùng tạo ứng viên trước khi `putIfAbsent` phân xử. Chỉ một ứng viên được thiết lập ở bước phân xử tương ứng, nhưng chi phí tạo và tác dụng phụ của các ứng viên khác vẫn có thể đã xảy ra. Đừng từ kiểu `ConcurrentMap` suy ra hàm khởi tạo chỉ chạy đúng một lần trong toàn hệ thống.

### Với ConcurrentHashMap

Lớp này ghi đè các phương thức tính toán và công bố bảo đảm mạnh hơn: lời gọi `compute` được thực hiện nguyên tử, hàm được gọi một lần cho mỗi lời gọi; `computeIfAbsent` không gọi hàm khi đã có giá trị, và tính toán khi cần được phối hợp nguyên tử. Xem [ConcurrentHashMap.computeIfAbsent và compute](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html#computeIfAbsent(K,java.util.function.Function)).

Điều đó vẫn không có nghĩa “mỗi khóa chỉ tạo đúng một lần suốt đời”: khóa có thể bị xóa, hàm có thể trả `null`, hoặc một lời gọi sau được thực hiện sau khi lần trước thất bại. Nó cũng không phải bảo đảm một tác động bên ngoài được thực hiện đúng một lần qua các lần chạy lại của ứng dụng.

Vì vậy, hàm tính nên ngắn, tập trung vào giá trị trả về và tránh tác dụng phụ như gửi email, gọi thanh toán hoặc tăng một bộ đếm phụ bên ngoài. Không sửa chính bản đồ đó từ bên trong hàm tính; với `ConcurrentHashMap`, điều này vi phạm ràng buộc tính toán và một số cập nhật đệ quy có thể bị phát hiện bằng `IllegalStateException`.

Tác vụ tải dữ liệu qua mạng kéo dài trong `computeIfAbsent` có thể giữ các cập nhật liên quan phải chờ. Khi cần tải bất đồng bộ hoặc chia sẻ một lần tải, nên thiết kế cơ chế lưu trạng thái đang tải hoặc đối tượng kết quả tương lai với chính sách lỗi và loại bỏ rõ ràng; không coi một callback dài là giải pháp miễn phí.

## 6. Nguyên tử trên ánh xạ không bảo vệ mọi thứ bên trong

Đoạn minh họa sau không làm `ArrayList` trở thành an toàn khi nhiều luồng cùng thêm:

```java
// groups là ConcurrentMap<String, List<String>>.
groups.computeIfAbsent("team", key -> new ArrayList<>()).add("alice");
```

Bước nhận hoặc thiết lập danh sách có bảo đảm của bản đồ. Lệnh `add` diễn ra trên đối tượng danh sách sau đó và chịu hợp đồng riêng của nó.

Các lựa chọn gồm dùng cấu trúc giá trị hỗ trợ truy cập đồng thời, đồng bộ hóa giá trị theo một giao thức chung, hoặc thay bằng giá trị bất biến mới qua một thao tác tính toán. Nếu dùng cách cuối, không sửa danh sách cũ ngay trong callback rồi coi đó là cập nhật bất biến.

Ngoài ra, luồng khác có thể xóa hoặc thay ánh xạ sau khi ta nhận danh sách nhưng trước khi thêm. Việc thêm vẫn có thể tác động lên đối tượng cũ đã rời bản đồ. Nếu yêu cầu là “thêm vào nhóm đang hiện hành”, cần thiết kế cả vòng đời của giá trị, không chỉ an toàn của từng lệnh.

Tương tự, khi callback ném ngoại lệ, bảo đảm không thiết lập kết quả ánh xạ mới không tự hoàn tác những thay đổi mà callback đã gây ra cho một đối tượng có thể thay đổi hoặc cho hệ thống bên ngoài.

Khóa cũng nên có `equals` và `hashCode` ổn định trong thời gian nằm trong bản đồ. An toàn luồng của collection không sửa được một khóa có trạng thái nhận diện bị đổi tùy ý.

## 7. Một khóa không phải giao dịch nhiều khóa

Giả sử muốn trừ một đơn vị của A rồi cộng cho B:

```java
balances.compute("A", (key, value) -> value - 1);
balances.compute("B", (key, value) -> value + 1);
```

Đây chỉ là phân tích hai lời gọi trong một ứng dụng đã bảo đảm khóa có giá trị. Mỗi cập nhật trên khóa có thể nguyên tử, nhưng một luồng khác vẫn có thể quan sát trạng thái giữa hai bước; bước thứ hai cũng có thể không hoàn thành.

Muốn giữ một bất biến chung giữa nhiều khóa, cần một giao thức chung như khóa ngoài mà **mọi bên đọc/ghi liên quan đều tuân thủ**, gom trạng thái vào một giá trị bất biến để thay cùng nhau, hoặc dùng cơ chế giao dịch phù hợp. Chỉ thêm `synchronized(map)` quanh hai lời gọi ở một nơi không ngăn các nơi khác tiếp tục gọi trực tiếp vào `ConcurrentHashMap` mà không lấy khóa đó.

`replaceAll`, `putAll` hoặc `clear` cũng không mặc nhiên là một giao dịch đồng thời trên toàn bản đồ. Không dùng `size()` rồi thêm như cơ chế giới hạn số phần tử: nhiều luồng có thể cùng vượt qua phép kiểm tra.

## 8. Chọn API theo câu hỏi nghiệp vụ

| Câu hỏi | Thao tác phù hợp |
|---|---|
| Chỉ đăng ký nếu tên chưa có | `putIfAbsent` |
| Chỉ hủy nếu giá trị vẫn là phiên bản tôi biết | `remove(key, expected)` |
| Chỉ chuyển trạng thái nếu vẫn còn trạng thái mong đợi | `replace(key, expected, next)` |
| Tạo giá trị khi thiếu | `computeIfAbsent` |
| Chỉ biến đổi giá trị đang có | `computeIfPresent` |
| Tính lại theo trạng thái có/không có | `compute` |
| Cộng hoặc ghép thêm một giá trị đầu vào | `merge` |

Các phương thức có bảo đảm cụ thể phụ thuộc đối tượng triển khai thật, không phụ thuộc việc biến được khai báo bằng tên `Map` hay `ConcurrentMap`. Khai báo `ConcurrentMap` giúp chữ ký hàm thể hiện yêu cầu về truy cập đồng thời; thay một `HashMap` thông thường vào thiết kế không giữ được bảo đảm chỉ vì nó cũng có các phương thức cùng tên.

## 9. Tự kiểm tra

1. `get` và `put` đều an toàn luồng thì ghép thành tăng một đơn vị có an toàn không? — Không; dùng thao tác cập nhật phù hợp như `merge`.
2. `replace(key, old, next)` trả `false` có nhất thiết là lỗi hệ thống không? — Không; có thể điều kiện đã lỗi thời do cạnh tranh.
3. `compute` trả `null` từ callback có lưu `null` vào `ConcurrentHashMap` không? — Không; ánh xạ bị xóa hoặc vẫn không tồn tại.
4. `computeIfAbsent` có làm danh sách nhận được an toàn khi nhiều luồng gọi `add` không? — Không.
5. Hai lần `compute` trên hai khóa có tạo giao dịch chuyển trạng thái chung không? — Không; phải thiết kế thêm phạm vi đồng bộ hoặc giao dịch.
