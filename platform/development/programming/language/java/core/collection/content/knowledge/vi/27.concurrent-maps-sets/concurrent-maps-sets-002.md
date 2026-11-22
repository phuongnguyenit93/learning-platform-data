# ConcurrentHashMap: truy cập đồng thời và chính sách không nhận null

## 1. ConcurrentHashMap giải quyết vấn đề gì?

Một ứng dụng có thể có nhiều luồng cùng đăng ký phiên làm việc, lưu trạng thái hoặc cập nhật số lượt truy cập. Nếu tất cả cùng dùng một map, cấu trúc chứa phải phối hợp được các lần đọc và thay đổi. Dùng một biến `HashMap` chung mà không có giao thức đồng bộ là chưa đủ.

`ConcurrentHashMap<K, V>` là một map dựa trên bảng băm, được thiết kế cho **truy cập đồng thời (concurrent access)**. Nó cung cấp thao tác an toàn đa luồng và các phép cập nhật có điều kiện phù hợp với bối cảnh nhiều bên cùng sử dụng.

Có hai cam kết cần học cùng nhau:

- Các thao tác của map có chính sách đồng bộ và phạm vi nguyên tử được tài liệu quy định.
- Map **không chứa khóa null và không chứa giá trị null**. Vì vậy, kết quả null từ `get` có một ý nghĩa rõ ràng: lần đọc đó không tìm được ánh xạ cho khóa.

Điều này giúp thiết kế thuật toán, nhưng không tự biến mọi quy trình thành một giao dịch. Nó cũng không làm đối tượng giá trị bất biến hay tự quyết định thế nào là “không có dữ liệu” trong nghiệp vụ.

Bài này tập trung vào cách đọc đúng những cam kết đó, áp dụng các thao tác cơ bản và mô hình hóa trạng thái vắng dữ liệu. Các ví dụ tương thích Java 17 trở lên.

### 1.1. Những từ cần phân biệt

| Khái niệm | Ý nghĩa trong bài |
| --- | --- |
| Ánh xạ (mapping) | Quan hệ một khóa với một giá trị đang được map lưu |
| An toàn đa luồng | Đối tượng giữ đúng hợp đồng khi nhiều luồng sử dụng theo cách được quy định |
| Tính nguyên tử | Một thao tác có phạm vi bảo vệ không bị tách thành các bước để bên khác xen vào theo cách phá điều kiện của thao tác |
| Quan hệ happens-before | Quy tắc của mô hình bộ nhớ giúp xác định thứ tự và việc nhìn thấy dữ liệu giữa các luồng |
| Vắng khóa | Không có ánh xạ đang được lần thao tác đó quan sát |
| Giá trị null | Tham chiếu không trỏ tới đối tượng; không phải một giá trị được phép lưu trong `ConcurrentHashMap` |
| Giá trị không tìm thấy trong nghiệp vụ | Một trạng thái của ứng dụng cần được biểu diễn rõ, chẳng hạn đã tra cứu nhưng không có người dùng |

Một map có thể an toàn ở mức ánh xạ nhưng quy trình gồm nhiều ánh xạ vẫn sai. Cũng có thể map không chứa null, trong khi một phương thức hợp lệ của nó vẫn trả về null để báo kết quả.

## 2. Mô hình truy cập đồng thời của ConcurrentHashMap

### 2.1. Khác với đặt một khóa chung quanh mọi thao tác

`ConcurrentHashMap` hỗ trợ đọc đồng thời và mức đồng thời cao cho cập nhật. Các thao tác truy xuất như `get` không dùng khóa theo cách khóa toàn bộ bảng; chúng có thể chồng lấp với cập nhật. Lớp không cung cấp cơ chế khóa toàn bảng để chặn mọi truy cập. [ConcurrentHashMap Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html)

Vì vậy, không nên hình dung nó đơn giản là `HashMap` với một `synchronized` bao mọi phương thức. Bên đọc không cần tự khóa map chỉ để thực hiện một lần `get` theo hợp đồng của lớp.

Điều này cũng không có nghĩa mọi cập nhật luôn chạy hoàn toàn độc lập hoặc không bao giờ phải chờ. Các thao tác tranh chấp cùng dữ liệu và các hàm tính có thể cần phối hợp. Tốc độ còn phụ thuộc số khóa, phân bố băm, tỷ lệ đọc/ghi và công việc trong từng thao tác.

**Không nên gọi cả lớp là “hoàn toàn lock-free”.** Đó là một tuyên bố mạnh hơn mức cần thiết để sử dụng API và không mô tả đúng mọi đường cập nhật.

Trong Java 17, không dùng mô hình “luôn có 16 segment cố định” như một hợp đồng API. Tham số constructor `concurrencyLevel` là gợi ý định cỡ, không phải số luồng tối đa được phép dùng map. Cần tách cam kết công khai khỏi chi tiết triển khai có thể thay đổi.

### 2.2. Phạm vi nguyên tử thường là một thao tác hoặc một khóa

Một lần `put` an toàn không làm hai lần gọi của người dùng tự gộp lại. Đoạn sau là **mã minh họa có lỗi khi nhiều luồng cùng tăng**, với `counts` đã có số nguyên tại khóa `"requests"`:

```java
int previous = counts.get("requests");
counts.put("requests", previous + 1);
```

Hai luồng có thể cùng đọc 10 rồi cùng ghi 11. Không có lần `put` nào ghi “nửa giá trị”, nhưng một lần tăng đã bị mất vì hai giá trị mới được tính từ cùng một số cũ.

Đối với bộ đếm nhỏ trong bài, có thể diễn đạt một lần tăng bằng:

```java
counts.merge("requests", 1, Integer::sum);
```

Đây là đoạn minh họa, giả sử `counts` là `ConcurrentHashMap<String, Integer>`. Khi khóa vắng, số 1 được thêm; khi đã có, phép gộp tính số mới. Không dùng cả đoạn sai và đoạn sửa cho cùng một lần tăng.

Tương tự, “nếu chưa có thì đăng ký” nên dùng `putIfAbsent` thay cho `containsKey` rồi `put`. `ConcurrentMap` quy định các phép có điều kiện như `putIfAbsent`, `remove(key, expected)`, `replace(key, expected, replacement)` thực hiện kiểm tra và thay đổi theo một thao tác nguyên tử. [ConcurrentMap Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentMap.html)

### 2.3. Dùng kết quả trả về của chính thao tác có điều kiện

Ví dụ minh họa không độc lập:

```java
String previous = owners.putIfAbsent("slot", "north");
boolean registered = previous == null;
```

Với `owners` là `ConcurrentHashMap<String, String>`:

- `previous == null`: lần gọi đã thêm giá trị vì không có ánh xạ trước đó.
- `previous != null`: đã có người đăng ký; giá trị đó được trả về và không bị lần gọi này thay thế.

Kết quả này đáng dùng để quyết định nhánh thành công/thất bại hơn việc kiểm tra trước bằng `containsKey`. Một luồng khác vẫn có thể xóa hoặc thay đăng ký **sau** khi thao tác đã hoàn tất; thành công không phải quyền sở hữu vĩnh viễn.

Với `remove(key, expectedValue)` và `replace(key, expectedValue, newValue)`, “giá trị còn khớp” được xét theo quy tắc bằng nhau, không tự mang ý nghĩa số phiên bản. Nếu ứng dụng cần phân biệt hai thế hệ dữ liệu có cùng nội dung, hãy biểu diễn phiên bản trong dữ liệu/giao thức.

### 2.4. Kiểu khai báo không đổi đối tượng thực tế

Có thể viết:

```java
ConcurrentMap<String, Integer> counts = new ConcurrentHashMap<>();
```

Đây là khai báo minh họa, cần import tương ứng. Nó thể hiện yêu cầu sử dụng một map có cam kết concurrent. Nếu khai báo biến là `Map` nhưng đối tượng vẫn là `ConcurrentHashMap`, Java vẫn gọi các phương thức ghi đè của đối tượng thực tế.

Tuy nhiên, một API nhận `Map` bất kỳ không thể mặc định mọi đối tượng truyền vào đều an toàn khi chia sẻ. Kiểu `Map` không tự cấp bảo đảm đồng bộ cho mọi lớp triển khai; các phương thức mặc định cũng không tự mang cùng chính sách nguyên tử. [Map Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html)

## 3. Chương trình: đăng ký và cộng dồn từ hai tác vụ

### 3.1. Quy tắc của ví dụ

Hai tác vụ `north` và `south` cùng đăng ký khóa `"slot"`. Chính sách là chỉ một bên được đăng ký khi khóa chưa có.

Sau đó mỗi tác vụ ghi nhận 1.000 yêu cầu. Mỗi nhóm bốn yêu cầu có một lần kiểm tra, nên mỗi tác vụ đóng góp 250 vào bộ đếm `"checks"`.

Chương trình không yêu cầu bên nào thắng đăng ký vì điều đó tùy lịch chạy. Nó kiểm tra **có đúng một bên thắng** và các bộ đếm cuối không mất cập nhật.

Lưu thành **`ConcurrentRegistrationDemo.java`**:

```java
import java.util.TreeMap;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class ConcurrentRegistrationDemo {
    private static final int REQUESTS = 1_000;

    public static void main(String[] args) throws Exception {
        ConcurrentHashMap<String, String> owners = new ConcurrentHashMap<>();
        ConcurrentHashMap<String, Integer> counts = new ConcurrentHashMap<>();
        CountDownLatch start = new CountDownLatch(1);
        ExecutorService pool = Executors.newFixedThreadPool(2);
        try {
            Future<Boolean> north = pool.submit(() ->
                    registerAndCount(owners, counts, start, "north"));
            Future<Boolean> south = pool.submit(() ->
                    registerAndCount(owners, counts, start, "south"));
            start.countDown();

            boolean a = north.get(10, TimeUnit.SECONDS);
            boolean b = south.get(10, TimeUnit.SECONDS);
            int successful = (a ? 1 : 0) + (b ? 1 : 0);
            require(successful == 1, "exactly one registration must win");
            require(counts.get("requests") == 2 * REQUESTS, "request count");
            require(counts.get("checks") == 2 * (REQUESTS / 4), "check count");

            String owner = owners.get("slot");
            require("north".equals(owner) || "south".equals(owner), "owner");
            require(!owners.replace("slot", "unknown", "approved"),
                    "wrong expected owner must fail");
            boolean replaced = owners.replace("slot", owner, "approved");
            boolean removed = owners.remove("slot", "approved");
            require(replaced && removed && owners.isEmpty(), "conditional update");

            System.out.println("successful registrations = " + successful);
            System.out.println("counts = " + new TreeMap<>(counts));
            System.out.println("conditional replace = " + replaced);
            System.out.println("conditional remove = " + removed);
        } finally {
            pool.shutdownNow();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("pool did not terminate");
            }
        }
    }

    private static boolean registerAndCount(
            ConcurrentHashMap<String, String> owners,
            ConcurrentHashMap<String, Integer> counts,
            CountDownLatch start,
            String candidate) throws InterruptedException {
        if (!start.await(5, TimeUnit.SECONDS)) {
            throw new IllegalStateException("start timed out");
        }
        boolean won = owners.putIfAbsent("slot", candidate) == null;
        for (int i = 0; i < REQUESTS; i++) {
            counts.merge("requests", 1, Integer::sum);
            if (i % 4 == 0) {
                counts.merge("checks", 1, Integer::sum);
            }
        }
        return won;
    }

    private static void require(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 -Xlint:all ConcurrentRegistrationDemo.java
java ConcurrentRegistrationDemo
```

Stdout khi chương trình chạy thành công:

```text
successful registrations = 1
counts = {checks=500, requests=2000}
conditional replace = true
conditional remove = true
```

### 3.2. Vì sao các kết quả này có thể kiểm tra chính xác?

`putIfAbsent` trả null cho đúng một lần đăng ký khi khóa ban đầu vắng và không có bên xóa trong giai đoạn đăng ký. Hai tác vụ đều đọc kết quả của chính lần gọi của mình.

`merge` giữ việc cập nhật theo khóa bên trong thao tác gộp. Mỗi tác vụ đóng góp đủ 1.000 lần cho `requests` và 250 lần cho `checks`. Các con số nhỏ nên không gặp tràn `int`.

Luồng chính chỉ đọc và in kết quả sau khi đã nhận kết quả của cả hai tác vụ. `TreeMap` dùng để trình bày khóa có thứ tự, giúp stdout cố định. Không có lời khẳng định rằng thứ tự duyệt của `ConcurrentHashMap` là thứ tự đã in.

Các lần `replace`/`remove` cuối chương trình chạy sau giai đoạn hai tác vụ, minh chứng điều kiện giá trị cũ: một giá trị kỳ vọng sai không được thay, giá trị đúng được thay rồi xóa.

Chương trình không đo hiệu năng và không chứng minh “hai khóa luôn được cập nhật cùng lúc”. Nó kiểm tra những điều kiện logic cần cho ví dụ. Thời hạn chờ chỉ để báo lỗi khi không thể hoàn tất; `finally` dừng nhóm luồng thay vì để tiến trình bị giữ lại.

## 4. Vì sao phải hiểu chính sách không nhận null?

### 4.1. Hợp đồng lưu trữ và ý nghĩa của `get`

`HashMap` cho phép khóa null và giá trị null. Vì vậy, trong một `HashMap`, `get(key) == null` có thể là không có khóa hoặc có khóa nhưng giá trị null. `containsKey` phân biệt được hai trạng thái nếu dữ liệu được truy cập trong bối cảnh ổn định/được phối hợp phù hợp. [HashMap Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashMap.html#get(java.lang.Object))

`ConcurrentHashMap` không lưu hai loại null đó. Với khóa hợp lệ, null từ `get` không phải một giá trị null đang nằm trong map.

Trong môi trường đồng thời, tự ghép `get` với `containsKey` để suy luận một trạng thái duy nhất còn có khoảng thời gian giữa hai lần gọi. Bên khác có thể thêm/xóa ánh xạ ở giữa. Không lưu null giúp lần `get` có tín hiệu vắng ánh xạ không mơ hồ do giá trị null.

Đây là cách giải thích ý nghĩa của **chính sách giá trị**. Nó không chứng minh rằng mọi cấu trúc an toàn đa luồng về mặt lý thuyết đều bắt buộc cấm khóa null. Cả khóa lẫn giá trị null bị cấm ở đây vì đó là hợp đồng cụ thể của `ConcurrentHashMap`.

### 4.2. Vắng ở lần đọc này không có nghĩa vắng mãi

Xét đoạn minh họa:

```java
Integer value = counts.get("job");
if (value == null) {
    System.out.println("Lan doc nay khong tim thay anh xa");
}
```

Luồng khác có thể thêm `"job"` ngay sau lần đọc. Ngược lại, nếu `value` khác null, luồng khác có thể xóa ánh xạ trước lúc bạn xử lý xong.

Do đó, `get` cung cấp kết quả của một lần truy xuất, không giữ chỗ và không khóa vòng đời của khóa. Nếu bước tiếp theo phải phụ thuộc vào việc ánh xạ còn nguyên, cần một thao tác có điều kiện hay giao thức lớn hơn.

Cũng cần phân biệt null trả về với khóa null truyền vào:

```java
counts.get("missing"); // Co the tra ve null.
counts.get(null);      // Nem NullPointerException.
```

Đây là đoạn minh họa, giả sử `counts` là `ConcurrentHashMap` và khóa `"missing"` chưa tồn tại. Hai dòng kiểm tra hai điều khác nhau: thiếu ánh xạ và đối số khóa không hợp lệ.

### 4.3. Chính sách “không lưu null” không có nghĩa “mọi null đều lỗi”

| Trường hợp | Ý nghĩa trong `ConcurrentHashMap` |
| --- | --- |
| `put(null, value)` | Khóa null không hợp lệ |
| `put(key, null)` | Giá trị lưu null không hợp lệ |
| `get(null)` | Khóa tra cứu null không hợp lệ |
| `get(nonNullKey)` trả null | Lần đọc không tìm được ánh xạ |
| `getOrDefault(key, null)` khi khóa vắng | Trả giá trị mặc định null, không lưu nó |
| Hàm `computeIfAbsent` trả null | Không tạo ánh xạ |
| Hàm `compute` trả null | Xóa ánh xạ đang có hoặc giữ trạng thái vắng |
| Hàm gộp của `merge` trả null | Xóa ánh xạ đang được gộp |

Điểm chung cần nhận ra: **null làm dữ liệu được lưu** và **null làm tín hiệu điều khiển/kết quả trả về** không có cùng vai trò.

Đặc biệt, đối số giá trị truyền trực tiếp cho `merge(key, value, function)` phải khác null. Nó không phải cùng trường hợp với việc `function` trả null để yêu cầu xóa.

Đọc phần `Throws`, `Returns` và hợp đồng hàm tính của từng overload. Không thay việc đọc hợp đồng bằng một luật nhớ quá rộng như “cứ truyền hoặc nhận null là sai”. [ConcurrentHashMap — getOrDefault và các phương thức tính](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html#getOrDefault(java.lang.Object,V))

## 5. Chương trình kiểm tra null và mô hình hóa kết quả vắng

### 5.1. Phân biệt dữ liệu null với tín hiệu không tạo/xóa

Chương trình dưới đây chạy trong một luồng để kiểm tra chính sách API rõ ràng. Nó không dùng ngoại lệ như cách xử lý thường xuyên cho dữ liệu đầu vào; các lệnh cố ý sai được đặt trong hàm kiểm tra để quan sát loại lỗi.

Lưu thành **`ConcurrentNullPolicyDemo.java`**:

```java
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;

public class ConcurrentNullPolicyDemo {
    public static void main(String[] args) {
        ConcurrentHashMap<String, Integer> map = new ConcurrentHashMap<>();

        System.out.println("get missing = " + map.get("missing"));
        System.out.println("getOrDefault missing, null = "
                + map.getOrDefault("missing", null));

        expectNullPointer("put(null, 1)", () -> map.put(null, 1));
        expectNullPointer("put(k, null)", () -> map.put("k", null));
        expectNullPointer("get(null)", () -> map.get(null));
        expectNullPointer("containsValue(null)", () -> map.containsValue(null));
        expectNullPointer("merge(k, null, sum)",
                () -> map.merge("k", null, Integer::sum));
        System.out.println("remove(missing, null) = " + map.remove("missing", null));

        int[] attempts = {0};
        Integer first = map.computeIfAbsent("absent", key -> {
            attempts[0]++;
            return null;
        });
        Integer second = map.computeIfAbsent("absent", key -> {
            attempts[0]++;
            return null;
        });
        require(first == null && second == null, "no value must be created");
        require(!map.containsKey("absent"), "null must not be stored");
        System.out.println("null-producing attempts = " + attempts[0]);
        System.out.println("absent stored = " + map.containsKey("absent"));

        map.put("count", 3);
        Integer computed = map.compute("count", (key, value) -> null);
        require(computed == null && !map.containsKey("count"), "compute removal");
        System.out.println("after compute-null, present = "
                + map.containsKey("count"));

        map.put("count", 3);
        Integer merged = map.merge("count", 1, (oldValue, added) -> null);
        require(merged == null && !map.containsKey("count"), "merge removal");
        System.out.println("after merge-null, present = "
                + map.containsKey("count"));

        Integer fresh = map.merge("fresh", 5, (oldValue, added) -> {
            throw new AssertionError("absent key must use the supplied value");
        });
        require(fresh == 5, "fresh merge");
        System.out.println("merge into absent key = " + fresh);

        ConcurrentHashMap<String, Optional<String>> cache = new ConcurrentHashMap<>();
        cache.put("known-missing", Optional.empty());
        cache.put("known-present", Optional.of("Lan"));
        System.out.println("unloaded cache entry = " + cache.get("unloaded"));
        System.out.println("known missing = " + cache.get("known-missing").isEmpty());
        System.out.println("known present = "
                + cache.get("known-present").orElseThrow());
    }

    private static void expectNullPointer(String label, Runnable action) {
        try {
            action.run();
            throw new AssertionError("expected NullPointerException: " + label);
        } catch (NullPointerException ex) {
            System.out.println(label + " -> " + ex.getClass().getSimpleName());
        }
    }

    private static void require(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }
}
```

Lệnh chạy:

```shell
javac --release 17 -encoding UTF-8 -Xlint:all ConcurrentNullPolicyDemo.java
java ConcurrentNullPolicyDemo
```

Stdout khi chạy thành công:

```text
get missing = null
getOrDefault missing, null = null
put(null, 1) -> NullPointerException
put(k, null) -> NullPointerException
get(null) -> NullPointerException
containsValue(null) -> NullPointerException
merge(k, null, sum) -> NullPointerException
remove(missing, null) = false
null-producing attempts = 2
absent stored = false
after compute-null, present = false
after merge-null, present = false
merge into absent key = 5
unloaded cache entry = null
known missing = true
known present = Lan
```

Các dòng đầu cho thấy một map không lưu null vẫn có thể trả null khi tra khóa vắng. Các lệnh `put`/`get` với khóa không hợp lệ và những giá trị lưu null được kiểm tra riêng.

`remove("missing", null)` trả false theo hợp đồng overload có điều kiện này: không có ánh xạ nào mang giá trị null để xóa. Trường hợp đó không cho phép đưa giá trị null vào map. Đối số khóa null vẫn không hợp lệ. [ConcurrentHashMap — remove(key, value)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html#remove(java.lang.Object,java.lang.Object))

Hai lần `computeIfAbsent` với hàm trả null tạo hai lần tính, vì không có kết quả nào được lưu sau lần đầu. Mảng `attempts` chỉ là bộ đếm cục bộ của ví dụ một luồng; không dùng cách tăng phần tử mảng này như bộ đếm dùng chung giữa nhiều luồng.

Hai dòng `after ... present = false` cho thấy null của hàm tính được hiểu là xóa, không phải lưu một ánh xạ null. Lần `merge` trên khóa vắng dùng trực tiếp giá trị 5; hàm gộp không được gọi ở nhánh đó.

### 5.2. `computeIfAbsent` không ghi nhớ một lần không tìm thấy nếu trả null

Giả sử bộ nhớ đệm cần lưu kết quả tra cứu. Nếu hàm tính trả null khi không có dữ liệu, khóa vẫn vắng; lần gọi sau có thể phải tra lại.

Riêng trên `ConcurrentHashMap`, `computeIfAbsent` thực hiện cả lần gọi nguyên tử và chỉ gọi hàm khi cần tính giá trị cho khóa vắng theo hợp đồng của nó. Nhưng đó không phải cam kết “chỉ gọi một lần trong suốt đời khóa”: null, ngoại lệ hoặc việc xóa ánh xạ có thể khiến lần gọi sau phải tính lại. [ConcurrentHashMap — computeIfAbsent](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html#computeIfAbsent(K,java.util.function.Function))

Phân biệt “chưa có kết quả trong bộ nhớ đệm” với “đã tra cứu, biết chắc không có kết quả” là quyết định dữ liệu của ứng dụng. Dùng null cho cả hai trong một map cấm null sẽ không thể giữ được sự khác biệt đó.

### 5.3. Một lựa chọn tường minh: `Optional<V>`

Trong chương trình trên, giá trị của cache là `Optional<String>`, bản thân đối tượng `Optional` luôn khác null khi được lưu:

| Kết quả `cache.get(key)` | Ý nghĩa do ví dụ quy định |
| --- | --- |
| null | Chưa có bản ghi kết quả trong cache |
| `Optional.empty()` | Đã ghi nhận không tìm thấy |
| `Optional.of("Lan")` | Đã có kết quả `"Lan"` |

`Optional` là đối tượng biểu diễn có hoặc không có giá trị khác null. Một `Optional.empty()` là đối tượng hợp lệ, không phải giá trị null bị cấm của map. [Optional Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Optional.html)

Đoạn xử lý minh họa, không độc lập, có thể dùng một kết quả đọc cục bộ:

```java
Optional<String> result = cache.get("user-7");
if (result == null) {
    System.out.println("Chua co ket qua trong cache");
} else if (result.isEmpty()) {
    System.out.println("Da tra cuu va khong tim thay");
} else {
    System.out.println("Tim thay: " + result.orElseThrow());
}
```

Đọc một lần vào `result` tránh tự ghép nhiều lần `get` rồi giả định chúng cùng một trạng thái. Dù vậy, kết quả vẫn có thể trở nên cũ ngay sau đó nếu các bên khác cập nhật cache.

`Optional` chỉ là một lựa chọn khi cần ba trạng thái như trong bảng. Nếu ứng dụng có thêm đang tải, lỗi, hết hạn, đang làm mới hoặc phiên bản dữ liệu, một kiểu kết quả riêng có tên trạng thái và dữ liệu đi kèm có thể rõ hơn.

Không nên dùng tùy tiện chuỗi rỗng, số âm hoặc một đối tượng đặc biệt mà người gọi có thể nhầm với dữ liệu thật. Nếu chọn đối tượng đánh dấu, cần thiết kế kiểu và quy tắc xử lý để nó không rò rỉ thành giá trị nghiệp vụ.

Kết quả “không tìm thấy” cũng có thể cần hết hạn hoặc bị xóa khi nguồn thay đổi. Lưu `Optional.empty()` chỉ giải quyết biểu diễn trạng thái, không tự cung cấp chính sách làm mới hay giới hạn bộ nhớ.

### 5.4. Hàm tính cần ngắn và quản lý tác dụng phụ cẩn thận

Các hàm của `compute`/`computeIfAbsent`/`merge` nên chỉ tính kết quả cần thiết và trả về. Không sửa lại chính map đang tính và không tùy tiện gọi lồng các thao tác có thể chờ nhau. Một số bên cập nhật khác có thể phải chờ trong lúc tính.

Tính nguyên tử của ánh xạ không khiến việc gọi dịch vụ ngoài, ghi một hệ thống khác hoặc gửi thông báo tự hoàn tác nếu hàm thất bại. Nếu nghiệp vụ cần phối hợp map với các tác dụng phụ đó, cần một giao thức riêng.

Cũng không chuyển bảo đảm số lần gọi hàm của một lớp cụ thể sang mọi `ConcurrentMap`. Một số phương thức mặc định có thể thử lại khi cạnh tranh, nên hàm tính có thể được gọi nhiều lần. [ConcurrentMap — compute và merge](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentMap.html#compute(K,java.util.function.BiFunction))

## 6. Truy cập không khóa ngoài vẫn có quy tắc nhìn thấy dữ liệu

### 6.1. Công bố đối tượng qua map

Một luồng thường tạo một đối tượng, điền dữ liệu rồi đặt nó vào map. Luồng khác lấy được đối tượng qua map và đọc dữ liệu đã khởi tạo.

`ConcurrentMap` quy định các hành động trước khi đặt đối tượng vào map xảy ra-trước các hành động sau khi luồng khác truy cập hoặc lấy đối tượng đó theo hợp đồng. Với `ConcurrentHashMap`, một truy xuất khác null có quan hệ với cập nhật ánh xạ tương ứng. Điều này giải thích vì sao `get` không cần một monitor ngoài do người dùng thêm vào mới có thể đọc đối tượng đã công bố đúng cách. [ConcurrentMap — Memory consistency effects](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentMap.html)

Quan hệ happens-before là quy tắc của mô hình bộ nhớ, không phải lời hứa về số mili giây để luồng được CPU chạy. Nó cũng không có nghĩa lần `get` nào cũng chắc chắn tìm thấy đối tượng nếu bên ghi chưa đặt vào.

Bản thân tham chiếu map cần được chia sẻ qua cơ chế khởi tạo/công bố phù hợp. Trong các ví dụ, map được tạo trước khi gửi tác vụ vào executor, không bị phát tán khi còn đang khởi tạo.

### 6.2. Chương trình công bố và chia sẻ tham chiếu

Lưu thành **`PublishedMappingDemo.java`**:

```java
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class PublishedMappingDemo {
    public static void main(String[] args) throws Exception {
        ConcurrentHashMap<String, Payload> map = new ConcurrentHashMap<>();
        CountDownLatch start = new CountDownLatch(1);
        ExecutorService pool = Executors.newFixedThreadPool(2);
        try {
            Future<?> producer = pool.submit(() -> {
                await(start);
                Payload payload = new Payload("Lan", 42);
                map.put("task", payload);
                return null;
            });

            Future<Payload> consumer = pool.submit(() -> {
                await(start);
                long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(5);
                Payload payload;
                while ((payload = map.get("task")) == null) {
                    if (Thread.currentThread().isInterrupted()) {
                        throw new InterruptedException("consumer interrupted");
                    }
                    if (System.nanoTime() - deadline >= 0) {
                        throw new IllegalStateException("publication timed out");
                    }
                    Thread.onSpinWait();
                }
                require("Lan".equals(payload.owner) && payload.amount == 42,
                        "state initialized before publication");
                return payload;
            });

            start.countDown();
            Payload received = consumer.get(10, TimeUnit.SECONDS);
            producer.get(10, TimeUnit.SECONDS);
            require(map.get("task") == received, "stored reference identity");

            System.out.println("published = " + received);
            System.out.println("same stored object = " + (map.get("task") == received));
            received.amount = 43;
            System.out.println("field after local change = " + map.get("task").amount);

            map.put("task", new Payload("Minh", 7));
            received.amount = 99;
            System.out.println("old reference after replacement = " + received.amount);
            System.out.println("current value after replacement = " + map.get("task"));
        } finally {
            pool.shutdownNow();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("pool did not terminate");
            }
        }
    }

    private static void await(CountDownLatch latch) throws InterruptedException {
        if (!latch.await(5, TimeUnit.SECONDS)) {
            throw new IllegalStateException("start timed out");
        }
    }

    private static void require(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    private static final class Payload {
        private String owner;
        private int amount;

        private Payload(String owner, int amount) {
            this.owner = owner;
            this.amount = amount;
        }

        @Override
        public String toString() {
            return owner + ":" + amount;
        }
    }
}
```

Lệnh chạy:

```shell
javac --release 17 -encoding UTF-8 -Xlint:all PublishedMappingDemo.java
java PublishedMappingDemo
```

Stdout khi chạy thành công:

```text
published = Lan:42
same stored object = true
field after local change = 43
old reference after replacement = 99
current value after replacement = Minh:7
```

Hai trường của `Payload` cố ý không khai báo final. Tác vụ tạo điền `owner` và `amount` trước `put`. Tác vụ nhận liên tục `get` cho tới khi lấy được tham chiếu rồi kiểm tra dữ liệu ngay trong tác vụ đó.

Cổng `start` chỉ phối hợp lúc hai tác vụ bắt đầu. Việc tạo và ghi trường xảy ra sau khi tác vụ tạo đi qua cổng; không có một latch báo “đã ghi xong” riêng để bên nhận dựa vào sau đó. Đường công bố đối tượng đang được minh họa là ánh xạ trong map.

Vòng chờ chủ động có thời hạn chỉ phục vụ thí nghiệm nhỏ này. Trong ứng dụng cần chờ một công việc hay kết quả, nên dùng một cơ chế chờ đúng với yêu cầu như `Future` hoặc hàng đợi phù hợp, thay vì sao chép vòng lặp quay này vào đường xử lý thông thường.

Bài chạy minh chứng cách sử dụng. Bảo đảm nhìn thấy dữ liệu đến từ hợp đồng đồng bộ của API và mô hình bộ nhớ, không phải từ việc một lần chạy cụ thể tình cờ in đúng số 42.

### 6.3. Công bố an toàn không làm giá trị bất biến

Sau khi cả hai tác vụ hoàn tất, luồng chính giữ tham chiếu `received`. Dòng `same stored object = true` chứng minh map trả chính đối tượng đã lưu, không phải một bản sao sâu.

Thay `received.amount` thành 43 làm đối tượng đang được map trỏ tới cũng có số 43. Phần này được thực hiện tuần tự trong luồng chính, để minh họa danh tính tham chiếu.

Sau đó map trỏ sang một `Payload` mới. Luồng chính sửa đối tượng cũ thành 99, nhưng giá trị hiện tại trong map vẫn là `Minh:7`. Thay ánh xạ không vô hiệu hóa mọi tham chiếu cũ đã được phát ra ngoài.

Nếu nhiều luồng cùng sửa `Payload.amount` về sau, chúng vẫn cần cơ chế riêng để bảo vệ trường và điều kiện liên quan. Map bảo vệ ánh xạ; nó không tự bọc mọi phương thức/trường của đối tượng giá trị trong một khóa.

Một lỗi thường gặp là tạo `ConcurrentHashMap<String, List<String>>`, dùng `computeIfAbsent` để lấy `ArrayList`, rồi cho nhiều luồng cùng `add` vào list đó. Phép lấy/tạo ánh xạ không tự biến `ArrayList` bên trong thành collection concurrent.

Hướng thiết kế có thể là giá trị bất biến và thay cả phiên bản, giá trị có đồng bộ riêng, hoặc lớp bao giữ toàn bộ trạng thái dưới một giao thức. Lựa chọn phụ thuộc việc thêm/xóa/thay ánh xạ phải phối hợp với sửa phần tử như thế nào.

## 7. Những giới hạn cần giữ đúng khi đọc hợp đồng

### 7.1. Một khóa an toàn không phải nhiều khóa cùng một giao dịch

Giả sử phải giảm số chỗ ở khóa A và tăng số chỗ ở khóa B. Hai lần `compute` có thể đều an toàn theo từng khóa, nhưng một người đọc giữa hai lần vẫn có thể thấy trạng thái mới của A và trạng thái cũ của B.

Muốn giữ một điều kiện liên quan nhiều khóa, cần một giao thức bao đủ phạm vi: cùng khóa cho mọi đường đọc/ghi liên quan, hoặc gom trạng thái thành một giá trị bất biến và thay theo phiên bản phù hợp.

Tùy tiện viết `synchronized (map)` quanh một đoạn không làm luồng khác chỉ gọi `map.put` tự lấy monitor đó. Khóa ngoài chỉ phối hợp các bên có tham gia cùng giao thức. Nếu cần kiểu khóa này, nên đóng gói map để không có đường truy cập đi vòng.

### 7.2. Số lượng và phép duyệt không mặc định là bản chụp toàn cục

Khi các luồng đang cập nhật, `size`, `isEmpty`, `containsValue` phản ánh trạng thái tạm thời. Chúng có thể hữu ích để theo dõi, nhưng không nên dùng như quyền giữ chỗ cho một hành động tiếp theo.

Iterator của các khung nhìn của `ConcurrentHashMap` là nhất quán yếu: có thể duyệt cùng với cập nhật, không dùng `ConcurrentModificationException` để báo thay đổi theo kiểu iterator thông thường, nhưng không chốt toàn bộ map tại một thời điểm.

Các phép hàng loạt như `putAll` và `clear` cũng không cung cấp một lần chuyển toàn map mà mọi người đọc đồng thời chỉ thấy hoàn toàn trước hoặc hoàn toàn sau. [ConcurrentHashMap — các thao tác tổng hợp](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html)

Vì thế, `new HashMap<>(liveConcurrentMap)` có thể tạo một bản độc lập về cấu trúc sau khi sao chép, nhưng không tự chứng minh mọi dữ liệu được lấy cùng phiên bản. Sắp xếp bản sao chỉ đổi thứ tự hiển thị; nó không sửa mức nhất quán của quá trình lấy dữ liệu.

Nếu đã biết không còn bên ghi trong giai đoạn đọc, như sau khi chờ các tác vụ kết thúc trong chương trình đầu, việc kiểm tra số lượng và trạng thái cuối có cơ sở khác. Hãy nêu điều kiện đó thay vì áp dụng kết luận cho giai đoạn cập nhật đang diễn ra.

### 7.3. Không nhận null không phải kiểm tra sâu toàn bộ đối tượng

Đoạn minh họa sau có thể đặt trong `main`, với import `ConcurrentHashMap`:

```java
record Profile(String nickname) {}

ConcurrentHashMap<String, Profile> profiles = new ConcurrentHashMap<>();
profiles.put("user-7", new Profile(null));

System.out.println(profiles.get("user-7").nickname() == null); // true
```

Khóa `"user-7"` khác null. Giá trị là một đối tượng `Profile` khác null. Trường `nickname` bên trong nó có thể là null nếu chính kiểu `Profile` cho phép.

Do đó, quy tắc của map không thay thế kiểm tra dữ liệu nghiệp vụ. Nếu biệt danh bắt buộc có, kiểu dữ liệu hoặc biên tiếp nhận dữ liệu cần kiểm tra yêu cầu đó.

Tương tự, map không tự kiểm tra mọi thành phần bên trong một khóa đối tượng. Một khóa cần có `equals`/`hashCode` đúng và ổn định trong thời gian dùng làm khóa. Làm thay đổi các trường ảnh hưởng đến phép bằng nhau/băm vẫn có thể khiến chương trình tra cứu sai theo hợp đồng của map; concurrency không xóa quy tắc nền tảng đó. [Map Java 17 — yêu cầu với khóa thay đổi](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html)

### 7.4. Giá trị mặc định trả về không phải giá trị đã lưu

Đoạn minh họa:

```java
ConcurrentHashMap<String, Integer> counts = new ConcurrentHashMap<>();
int missingCount = counts.getOrDefault("unknown", 0);
boolean stored = counts.containsKey("unknown");
```

Trong bối cảnh không có bên khác cập nhật, `missingCount` bằng 0 nhưng `stored` vẫn false. `getOrDefault` chỉ trả kết quả thay thế cho lần đọc, không tạo một bộ đếm tại khóa đó.

Cũng không dùng `getOrDefault(key, 0)` rồi `put(key, old + 1)` để thay cho `merge`. Dù tránh được lỗi unboxing null, hai lần gọi vẫn có khoảng trống làm mất cập nhật.

Những vấn đề này độc lập: một đoạn mã có thể xử lý null đúng nhưng đồng bộ sai, hoặc chọn thao tác đồng bộ đúng nhưng mô hình hóa trạng thái vắng dữ liệu sai.

## 8. Áp dụng và chuyển từ HashMap sang ConcurrentHashMap

### 8.1. Chọn theo quyền sở hữu và cách truy cập

| Bối cảnh | Cách tiếp cận có thể phù hợp | Điều phải giữ rõ |
| --- | --- | --- |
| Map chỉ do một luồng sở hữu | `HashMap` hoặc cấu trúc thường phù hợp | Không chia sẻ ngoài quyền sở hữu đó |
| Nhiều luồng đọc/ghi ánh xạ theo khóa, chấp nhận chính sách không null | `ConcurrentHashMap` | Dùng thao tác gộp đúng; quản lý trạng thái phần tử |
| Cần một khóa chung cho toàn bộ chuỗi trên map | Lớp bao có khóa riêng hoặc synchronized map theo giao thức | Mọi đường đọc/ghi phải cùng tuân thủ |
| Cần thứ tự khóa | Chọn cấu trúc có hợp đồng thứ tự phù hợp | `ConcurrentHashMap` không có thứ tự khóa được cam kết |
| Cần một bản ghi “đã tra nhưng không có” | Giá trị tường minh như `Optional.empty()` hoặc kiểu kết quả | Chính sách hết hạn, xóa và làm mới thuộc ứng dụng |
| Cần nhất quán nhiều đối tượng/toàn bộ dữ liệu | Giao thức phiên bản/khóa/giao dịch thích hợp | Một collection concurrent riêng lẻ không tự cung cấp tất cả |

Một `Collections.synchronizedMap(new HashMap<>())` là một phản ví dụ hữu ích cho cách nhớ sai “map an toàn đa luồng luôn cấm null”: cấu trúc nền `HashMap` của ví dụ vẫn hỗ trợ khóa và giá trị null. Đối tượng bọc cung cấp cơ chế đồng bộ, không biến hợp đồng thành của `ConcurrentHashMap`.

Nhưng việc đó không có nghĩa chỉ đổi sang synchronized map là xử lý xong mọi chuỗi thao tác. Tài liệu yêu cầu truy cập cấu trúc nền qua đối tượng bọc và giữ khóa phù hợp khi duyệt các khung nhìn. [Collections — synchronizedMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#synchronizedMap(java.util.Map))

### 8.2. Rà soát ý nghĩa null trước khi thay kiểu

Đổi `new HashMap<>()` thành `new ConcurrentHashMap<>()` có thể làm lộ giả định cũ. Hãy xác định từng trường hợp null đang có nghĩa gì:

- Không tìm thấy khóa: không cần một ánh xạ null.
- Chưa nạp dữ liệu: có thể biểu diễn bằng trạng thái vắng, nếu phù hợp.
- Đã nạp nhưng không có kết quả: cần một giá trị tường minh nếu muốn ghi nhớ.
- Dữ liệu đầu vào không hợp lệ: báo lỗi ở biên nhận dữ liệu theo hợp đồng ứng dụng.
- Yêu cầu xóa: gọi `remove` hoặc dùng null theo ngữ nghĩa được phương thức tính quy định.
- Lỗi nguồn dữ liệu: không tự đồng nhất với “không có kết quả” nếu hai trạng thái cần xử lý khác nhau.

Không bắt `NullPointerException` rồi im lặng bỏ qua để xem như việc ghi đã thành công. Cũng không đổi null thành chuỗi rỗng nếu chuỗi rỗng vốn là một dữ liệu hợp lệ mà ứng dụng cần phân biệt.

Khi chuyển dữ liệu hàng loạt từ map cũ, kiểm tra/chuẩn hóa chính sách null trước khi đưa vào map mới. Một lệnh nhập thất bại không nên được tự hiểu là toàn bộ trạng thái đã được hoàn tác. Nếu yêu cầu là nhập tất cả hoặc không nhập gì, cần thiết kế phạm vi kiểm tra và công bố tương ứng.

### 8.3. Rà soát chuỗi thao tác sau khi thay cấu trúc chứa

Sau khi xử lý dữ liệu null, tìm các mẫu như:

- `containsKey` rồi `put`.
- `get` rồi `put` giá trị được tính từ số cũ.
- `get` rồi so sánh rồi `remove`.
- `size` rồi quyết định có được thêm.
- Lấy một đối tượng giá trị rồi sửa trường/danh sách bên trong.

Với từng mẫu, viết rõ điều kiện cần giữ. Chọn `putIfAbsent`, `merge`, `compute`, xóa/thay có điều kiện hoặc giao thức lớn hơn theo đúng điều kiện đó.

Nếu nhiều khóa được dùng để diễn tả một trạng thái chung, không chỉ rà từng dòng gọi API. Cần xét cả người đọc báo cáo, đường xóa/reset, thời điểm hết hạn và những tham chiếu giá trị đã thoát ra ngoài.

Tham số định cỡ ban đầu cũng không phải giới hạn số phần tử hay giới hạn số luồng. Nó không thay thế việc giới hạn kích thước bộ nhớ đệm; `ConcurrentHashMap` không tự có TTL hay tự loại bỏ bản ghi theo chính sách cache.

## 9. Luyện tập để tự kiểm tra

### Bài 1 — Null khi đọc có phải map đang lưu null?

Một `ConcurrentHashMap<String, Integer>` trả null cho `get("x")`.

**Câu hỏi:** Có thể kết luận map chứa `"x" -> null` không? Có thể kết luận một luồng khác không được thêm `"x"` ngay sau đó không?

**Đối chiếu:** Không có ánh xạ null trong loại map này. Null biểu thị lần đọc không tìm thấy ánh xạ. Nó không giữ khóa vắng cho các hành động tương lai; luồng khác có thể thêm ngay sau lần đọc.

### Bài 2 — Trả null trong hàm tính

Một lần `computeIfAbsent("user-7", function)` trả null vì `function` không tìm thấy người dùng. Lần gọi tiếp theo vẫn cần tra cứu.

**Câu hỏi:** Vì sao lần đầu không được ghi nhớ? Nếu muốn giữ kết quả không tìm thấy, có thể biểu diễn như thế nào?

**Đối chiếu:** Hàm trả null không tạo ánh xạ. Có thể dùng một giá trị khác null biểu diễn đã tra mà không có, chẳng hạn `Optional.empty()` hoặc một kiểu kết quả riêng, kèm quy tắc hết hạn/làm mới phù hợp.

### Bài 3 — Giá trị mặc định và bộ đếm

Một lập trình viên sửa:

```java
Integer oldValue = counts.get("requests");
counts.put("requests", oldValue + 1);
```

thành:

```java
int oldValue = counts.getOrDefault("requests", 0);
counts.put("requests", oldValue + 1);
```

Hai đoạn là mã minh họa, không phải chương trình độc lập.

**Câu hỏi:** Bản sau đã giải quyết những gì và còn thiếu gì?

**Đối chiếu:** Nó có giá trị mặc định để tránh unboxing null khi khóa vắng. Nó chưa gộp đọc–sửa–ghi thành thao tác nguyên tử nên vẫn có thể mất cập nhật. Với yêu cầu đếm trong bài, dùng `merge` trên `ConcurrentHashMap` phù hợp hơn.

### Bài 4 — Null bên trong một đối tượng

Một map lưu `new Profile(null)` tại khóa khác null, và constructor `Profile` không cấm trường null.

**Câu hỏi:** Điều này có vi phạm chính sách không nhận null của map không? Nó có chắc chắn hợp lệ về nghiệp vụ không?

**Đối chiếu:** Tham chiếu giá trị là một đối tượng khác null nên không vi phạm riêng quy tắc lưu trữ đó. Tính hợp lệ của trường thuộc hợp đồng kiểu dữ liệu/ứng dụng; map không tự kiểm tra sâu.

### Bài 5 — Đối tượng được công bố rồi tiếp tục thay đổi

Luồng A tạo `Payload`, đặt vào map rồi về sau ghi các trường thường của nó. Luồng B gọi `get` và đọc các trường.

**Câu hỏi:** Có thể lấy bảo đảm công bố ban đầu làm bằng chứng mọi thay đổi trường về sau đều được phối hợp đúng không?

**Đối chiếu:** Không. Công bố dữ liệu đã khởi tạo trước khi đặt vào map và đồng bộ các lần sửa tương lai là hai yêu cầu khác nhau. Cần trạng thái bất biến hoặc một cơ chế bảo vệ phần tử đủ cho những lần sửa/đọc đó.

### Bài 6 — Hai lần cập nhật an toàn có thành một lần chuyển trạng thái không?

Ứng dụng dùng hai lần `compute`, một lần giảm số chỗ A, một lần tăng số chỗ B. Bên đọc cộng hai khóa bằng hai lần `get`.

**Câu hỏi:** Vì sao vẫn có thể đọc một tổng trung gian?

**Đối chiếu:** Các ranh giới nguyên tử riêng không tự nối thành một giao dịch nhiều khóa. Cần phối hợp cả phép chuyển và phép đọc theo điều kiện bất biến mà ứng dụng yêu cầu.

## 10. Tài liệu đối chiếu hợp đồng

Các chương trình trong bài minh họa cách dùng API; khi thay phiên bản hoặc lớp triển khai, kiểm tra đúng tài liệu của đối tượng thực tế:

- [ConcurrentHashMap Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html): truy cập đồng thời, chính sách null, hàm tính và giới hạn thao tác tổng hợp.
- [ConcurrentMap Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentMap.html): thao tác có điều kiện và quan hệ công bố dữ liệu.
- [Map Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html): hợp đồng ánh xạ, khóa và các phương thức mặc định.
- [HashMap Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashMap.html): đối chiếu ý nghĩa null và yêu cầu đồng bộ ngoài.
- [Optional Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Optional.html): biểu diễn có/không có giá trị khác null.
- [Collections Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html): cơ chế đối tượng bọc đồng bộ.

