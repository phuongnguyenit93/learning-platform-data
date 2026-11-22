# Quy tắc `null` của `ConcurrentHashMap`

## 1. Quy tắc nền tảng: không lưu khóa hoặc giá trị `null`

`ConcurrentHashMap<K,V>` không cho phép khóa `null` và không cho phép giá trị ánh xạ là `null`. Đó là hợp đồng của lớp, không phải một tùy chọn có thể bật khi tạo map.

```java
ConcurrentHashMap<String, String> map = new ConcurrentHashMap<>();
map.put(null, "A");     // NullPointerException
map.put("key", null);   // NullPointerException
```

Đoạn trên minh họa hai thao tác lỗi riêng biệt; nếu chạy lần lượt mà không bắt ngoại lệ, chương trình dừng ở thao tác đầu và không tự chạy tiếp đến thao tác thứ hai.

Tuy nhiên, không được rút gọn thành “mọi chỗ xuất hiện `null` đều ném lỗi”. `null` có ba vai trò cần tách rõ:

| Vai trò | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Dữ liệu định lưu vào map | `put("key", null)` | Không hợp lệ |
| Kết quả tra cứu | `get("missing")` trả `null` | Không có ánh xạ ở lần tra cứu đó |
| Kết quả của hàm tính lại | `compute(key, (k, old) -> null)` | Có thể yêu cầu không lưu hoặc xóa ánh xạ, tùy phương thức |

Quy tắc khóa/giá trị và các hợp đồng phương thức đang dùng được mô tả tại [Java SE `ConcurrentHashMap`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html). Nội dung trong bài không cần API đã lỗi thời.

## 2. Vì sao “không tìm thấy” có thể được biểu diễn rõ bằng `null`?

Với `HashMap`, một khóa có thể được gắn với giá trị `null`, nên `get(key) == null` có thể là “không có khóa” hoặc “có khóa nhưng giá trị là null”. Với `ConcurrentHashMap`, trường hợp thứ hai không tồn tại trong dữ liệu được lưu.

Do đó, một lần `get(key)` trả `null` có ý nghĩa rõ: lần đọc đó không tìm thấy ánh xạ. Điều này đặc biệt hữu ích khi các luồng có thể đồng thời thêm và xóa khóa.

Nhưng “rõ nghĩa tại lần đọc” không có nghĩa “sẽ giữ nguyên đến bước kế tiếp”. Ví dụ:

```java
String value = map.get("job-1");
if (value == null) {
    map.put("job-1", "NEW");
}
```

Đoạn minh họa vẫn có khoảng đua: một luồng khác có thể thêm giá trị sau `get` và trước `put`, rồi bị ghi đè. Quy tắc không lưu `null` không làm cả chuỗi kiểm tra – hành động trở thành nguyên tử.

Nếu ý định là chỉ thêm khi chưa có, dùng:

```java
String previous = map.putIfAbsent("job-1", "NEW");
```

`previous == null` nghĩa là lời gọi đã thêm giá trị vì trước đó chưa có ánh xạ tại thao tác nguyên tử này. Nếu trả về giá trị khác `null`, đó là giá trị đang có mà thao tác không ghi đè. Dù vậy, một luồng khác vẫn có thể thay đổi map sau khi phương thức trở về.

## 3. Các đầu vào thường gây `NullPointerException`

Với một `ConcurrentHashMap<String, String>` hợp lệ, có thể nhớ theo nhóm:

| Lời gọi | Hành vi với `null` |
| --- | --- |
| `put(null, "A")` | Khóa không hợp lệ, ném `NullPointerException` |
| `put("k", null)` | Giá trị không hợp lệ, ném `NullPointerException` |
| `putIfAbsent("k", null)` | Giá trị không hợp lệ, kể cả khi khóa đã có |
| `get(null)` | Khóa tra cứu không hợp lệ |
| `containsKey(null)` | Khóa tra cứu không hợp lệ |
| `containsValue(null)` | Giá trị tìm kiếm không hợp lệ |
| `remove(null)` | Khóa không hợp lệ |
| `replace("k", null)` | Giá trị thay thế không hợp lệ |
| `merge("k", null, function)` | Giá trị đưa vào không hợp lệ; không phải yêu cầu xóa |
| `computeIfAbsent("k", null)` | Hàm tính bị thiếu, không hợp lệ |

Bảng tập trung vào các lời gọi cụ thể, không tuyên bố mọi tham số của mọi phương thức đều xử lý `null` giống nhau.

### Hai trường hợp dễ kết luận sai

**`getOrDefault("missing", null)` có thể trả `null`.** Giá trị mặc định chỉ là kết quả trả về khi chưa tìm thấy khóa; nó không được chèn vào map. Vì vậy việc dùng mặc định `null` ở đây không vi phạm quy tắc lưu trữ.

**`remove("k", null)` trả `false` khi khóa hợp lệ.** Đây là phương thức xóa có điều kiện: chỉ xóa nếu giá trị hiện tại khớp giá trị dự kiến. Vì không có ánh xạ mang giá trị `null` trong `ConcurrentHashMap`, điều kiện đó không khớp. Không dùng nó để xóa một khóa bất kể giá trị; nếu đó là ý định, dùng `remove("k")`.

Hai overload `remove(key)` và `remove(key, expectedValue)` có ý nghĩa khác nhau. Cũng không suy rộng hành vi của `ConcurrentHashMap` sang mọi triển khai `Map` chỉ vì cùng tên phương thức.

## 4. `null` trong `compute`: tín hiệu điều khiển, không phải dữ liệu được lưu

### `computeIfAbsent`: không tạo ánh xạ nếu hàm trả `null`

```java
String result = map.computeIfAbsent("unknown", key -> null);
```

Nếu khóa đang vắng mặt, hàm được dùng để thử tính giá trị. Kết quả `null` khiến map không lưu ánh xạ mới; `result` là `null`. Lần gọi tương lai có thể tính lại vì khóa vẫn chưa có.

Nếu khóa đã có giá trị, hàm không được dùng để thay giá trị đó. Không hiểu việc hàm có thể trả `null` là cách xóa một giá trị đang tồn tại qua `computeIfAbsent`.

### `computeIfPresent`: hàm trả `null` thì xóa ánh xạ đang có

```java
map.computeIfPresent("active", (key, oldValue) -> null);
```

Nếu `"active"` đang có giá trị, hàm được gọi và `null` yêu cầu gỡ ánh xạ. Nếu không có khóa, hàm không cần chạy và map không tạo giá trị mới.

### `compute`: nhận `null` cho giá trị cũ khi chưa có khóa

```java
map.compute("attempts", (key, oldValue) ->
        oldValue == null ? "first" : "again");
```

Ở đây `oldValue == null` là đầu vào hợp lệ của hàm để biểu diễn chưa có ánh xạ. Nó không chứng minh map đã lưu một giá trị `null`.

Nếu hàm `compute` trả `null`, ánh xạ đang có bị gỡ; nếu vốn chưa có, khóa tiếp tục vắng mặt. Map không tạo một mục mới với giá trị `null`.

Phần cập nhật theo khóa của các phương thức này là nguyên tử theo hợp đồng `ConcurrentHashMap`, nhưng hàm phải ngắn và không sửa chính map trong lúc tính. Không dùng tác dụng phụ bên ngoài rồi mặc định chúng cũng được đưa vào cùng một giao dịch.

## 5. `merge`: phân biệt giá trị đầu vào và kết quả hàm gộp

Với lời gọi:

```java
map.merge("state", "NEW", (oldValue, incomingValue) -> null);
```

Có hai tình huống khác nhau:

- Nếu chưa có `"state"`, map gắn trực tiếp giá trị `"NEW"`. Hàm gộp không cần chạy.
- Nếu đã có giá trị, hàm gộp chạy; kết quả `null` yêu cầu xóa ánh xạ đó.

Trong cả hai tình huống, không có giá trị `null` nào được lưu. Ngược lại, lời gọi dưới đây không phải cách xóa:

```java
map.merge("state", null, (oldValue, incomingValue) -> "X");
```

Đây là mã minh họa lỗi: giá trị đầu vào của `merge` phải khác `null`, nên lời gọi ném `NullPointerException`. Không nhầm “hàm được phép trả null” với “mọi đối số null đều được phép”.

Tương tự, `replaceAll` không dùng kết quả `null` làm giao thức xóa từng ánh xạ như `compute`. Nếu hàm thay thế tạo giá trị `null`, đó là lỗi với `ConcurrentHashMap`; cũng không được mặc định mọi cập nhật trước đó sẽ được hoàn tác như một giao dịch.

## 6. Ví dụ Java 17+ kiểm chứng các vai trò của `null`

Lưu thành `ConcurrentNullDemo.java`. Ví dụ chạy một luồng để quan sát đúng hợp đồng `null` mà không phụ thuộc thứ tự lập lịch. Quy tắc này vẫn áp dụng khi map được dùng bởi nhiều luồng.

```java
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;

public class ConcurrentNullDemo {
    private static void expectNpe(String label, Runnable action) {
        try {
            action.run();
            throw new AssertionError("Expected NullPointerException: " + label);
        } catch (NullPointerException ex) {
            System.out.println(label + ": NullPointerException");
        }
    }

    public static void main(String[] args) {
        ConcurrentHashMap<String, String> map = new ConcurrentHashMap<>();
        expectNpe("null key", () -> map.put(null, "A"));
        expectNpe("null value", () -> map.put("k", null));
        expectNpe("merge null input", () ->
                map.merge("k", null, (old, incoming) -> incoming));

        System.out.println("missing: " + map.get("missing"));
        System.out.println("null fallback: " + map.getOrDefault("missing", null));
        map.computeIfAbsent("none", key -> null);
        System.out.println("none stored: " + map.containsKey("none"));

        map.put("state", "READY");
        map.computeIfPresent("state", (key, old) -> null);
        System.out.println("state after compute: " + map.containsKey("state"));

        map.put("merged", "A");
        map.merge("merged", "B", (old, incoming) -> null);
        System.out.println("merged stored: " + map.containsKey("merged"));
        map.merge("fresh", "A", (old, incoming) -> null);
        System.out.println("fresh: " + map.get("fresh"));

        map.put("keep", "VALUE");
        System.out.println("remove expected null: " + map.remove("keep", null));
        System.out.println("keep: " + map.get("keep"));

        Map<String, String> source = Map.of("u1", "Lan");
        ConcurrentHashMap<String, Optional<String>> cache = new ConcurrentHashMap<>();
        System.out.println("uncached u2: " + cache.get("u2"));
        Optional<String> result = cache.computeIfAbsent("u2", key ->
                Optional.ofNullable(source.get(key)));
        System.out.println("cached u2: " + cache.containsKey("u2"));
        System.out.println("u2 has value: " + result.isPresent());
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 ConcurrentNullDemo.java
java ConcurrentNullDemo
```

Stdout:

```text
null key: NullPointerException
null value: NullPointerException
merge null input: NullPointerException
missing: null
null fallback: null
none stored: false
state after compute: false
merged stored: false
fresh: A
remove expected null: false
keep: VALUE
uncached u2: null
cached u2: true
u2 has value: false
```

`expectNpe` chỉ bắt ngoại lệ dự kiến trong các phép thử đầu vào của ví dụ, rồi in tên ngoại lệ. Nó không phải khuyến nghị bắt mọi `NullPointerException` trong ứng dụng để tiếp tục chạy bất kể lỗi lập trình.

Các dòng `fresh: A` và `merged stored: false` cho thấy cùng một hàm gộp trả `null` có tác động khác nhau tùy việc hàm có được gọi hay không. Các dòng cuối phân biệt khóa chưa được lưu với một kết quả “đã tra cứu nhưng không có dữ liệu”.

## 7. Biểu diễn “đã tra cứu nhưng không có kết quả” bằng dữ liệu rõ nghĩa

Nếu một hàm nạp dữ liệu trả `null`, việc đưa trực tiếp kết quả đó vào `computeIfAbsent` không ghi nhớ lần tìm không thấy. Mỗi lần gọi sau có thể tiếp tục tìm lại.

Khi cần ghi nhớ cả kết quả không tìm thấy, có thể chọn một kiểu giá trị khác `null`. Ví dụ trong chương trình dùng `Optional<String>`:

| Trạng thái ở lớp lưu tạm | Giá trị quan sát |
| --- | --- |
| Chưa có bản ghi cho khóa | `cache.get(key)` trả `null` |
| Đã tra cứu và không có kết quả | Ánh xạ chứa `Optional.empty()` |
| Đã tra cứu và có kết quả | Ánh xạ chứa `Optional` có giá trị |

`Optional.empty()` là một đối tượng hợp lệ, không phải giá trị ánh xạ `null`. [Java SE `Optional`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Optional.html) cung cấp `ofNullable` để chuyển một kết quả có thể là `null` thành kiểu biểu diễn có hoặc không có giá trị.

Đây là một lựa chọn mô hình hóa, không có nghĩa mọi map đều nên dùng `Optional`. Nếu cần phân biệt thêm trạng thái đang nạp, không tìm thấy, lỗi tạm thời hoặc đã hết hạn, một kiểu kết quả riêng có thể rõ ràng hơn.

Phải quyết định vòng đời kết quả không tìm thấy: nguồn dữ liệu có thể bổ sung giá trị sau đó. Lưu `Optional.empty()` mãi mãi sẽ giữ một kết luận cũ. `ConcurrentHashMap` không tự cung cấp thời hạn hết hạn hoặc giới hạn dung lượng cho cơ chế này.

Không đổi lỗi kết nối hoặc lỗi truy vấn thành “không tìm thấy” rồi lưu như một kết quả bình thường. Không tìm thấy là một kết quả nghiệp vụ; lỗi là đường xử lý khác.

Hàm nạp trong ví dụ chỉ đọc một map cục bộ, rất ngắn. Nếu nguồn thật là dịch vụ mạng chậm, cần thiết kế cách nạp và quản lý việc chờ riêng, thay vì mặc định đặt mọi I/O vào trong hàm tính của map.

## 8. Kiểm tra đầu vào tại ranh giới và tránh thay nghĩa dữ liệu

Nếu khóa hoặc giá trị là bắt buộc, nên kiểm tra tại ranh giới lớp ứng dụng và báo lỗi gắn với tên tham số:

```java
static void store(ConcurrentHashMap<String, String> map,
                  String userId, String displayName) {
    java.util.Objects.requireNonNull(userId, "userId");
    java.util.Objects.requireNonNull(displayName, "displayName");
    map.put(userId, displayName);
}
```

Đây là phương thức minh họa để đặt trong một lớp Java. Kiểm tra không làm dữ liệu `null` trở nên hợp lệ; nó làm lỗi xuất hiện rõ hơn ở ranh giới trách nhiệm.

Nếu nghiệp vụ thật sự cho phép thiếu dữ liệu, hãy biểu diễn trạng thái đó theo thiết kế. Đừng tự thay mọi khóa `null` bằng chuỗi rỗng hoặc mọi giá trị `null` bằng `"N/A"`: các giá trị đó có thể là dữ liệu hợp lệ và gây trùng nghĩa.

Khi nạp hàng loạt từ một nguồn cho phép `null`, cần xác định cách xử lý trước khi đưa vào map. Không gọi `putAll` rồi mặc định nó bỏ qua các mục `null` hoặc hoàn tác mọi mục đã thêm nếu gặp lỗi ở giữa. Việc sao chép nhiều ánh xạ không tự tạo một giao dịch trên cả map.

## 9. Tự kiểm tra

1. `get("missing")` trả `null` có chứng minh `ConcurrentHashMap` đang lưu một giá trị `null` không?
2. Vì sao `getOrDefault("missing", null)` không giống `put("missing", null)`?
3. `computeIfAbsent` trả `null` có ghi nhớ rằng đã tìm không thấy không?
4. `merge("k", "A", (old, incoming) -> null)` sẽ làm gì khi `k` chưa có, và khi `k` đã có?
5. `remove("k", null)` có nghĩa là xóa khóa bất kể giá trị không?
6. Vì sao một kết quả không tìm thấy được lưu bằng `Optional.empty()` vẫn cần chính sách làm mới?

Gợi ý: (1) Không, lần đọc đó không có ánh xạ. (2) Giá trị mặc định chỉ trả về cho bên gọi, không được lưu. (3) Không tạo ánh xạ mới, nên lần sau có thể tìm lại. (4) Chưa có thì gắn `"A"`; đã có thì hàm gộp trả `null` và xóa. (5) Không, đây là điều kiện so khớp không thể khớp với giá trị đang lưu hợp lệ. (6) Dữ liệu ở nguồn có thể thay đổi, còn map không tự hết hạn kết luận cũ.
