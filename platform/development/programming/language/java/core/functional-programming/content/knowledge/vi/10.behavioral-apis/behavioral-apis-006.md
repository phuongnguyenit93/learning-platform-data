# Map.computeIfAbsent(), compute() và merge(): truyền hành vi xử lý giá trị trong Java

## Mục tiêu học tập

Ba phương thức `Map.computeIfAbsent()`, `Map.compute()` và `Map.merge()` nhận **hàm dưới dạng đối số** để quyết định giá trị liên kết với một khóa. Chúng thay nhiều chuỗi thao tác như `containsKey` → `get` → `put` bằng một API biểu đạt trực tiếp quy tắc cập nhật. Tuy có cú pháp gần nhau, **thời điểm gọi lambda, giá trị đầu vào và cách xử lý `null` khác biệt quan trọng**.

Sau bài này, bạn có thể:

- Chọn đúng API khi cần khởi tạo theo nhu cầu, tính lại từ giá trị cũ hoặc cộng dồn/ghép một giá trị mới.
- Đọc chữ ký và xác định rõ function descriptor của `Function` và `BiFunction`.
- Dự đoán khi callback được gọi và khi nó **không** được gọi, kể cả khi khóa có giá trị `null`.
- Giải thích cách trả `null` để không thêm hoặc xóa mapping, đồng thời phân biệt **không có khóa** với **khóa đang trỏ đến null**.
- Xử lý đúng trường hợp lambda ném ngoại lệ, dữ liệu mutable và việc cập nhật đồng thời.
- Viết, chạy và kiểm tra một chương trình Java 17 có kết quả xác định.

## 1. Map nhận hành vi thay vì chỉ nhận giá trị

`Map<K,V>` là interface ánh xạ khóa kiểu `K` tới giá trị kiểu `V`. Trong `java.util.Map`, ba phương thức được khai báo theo ý tưởng sau:

```java
V computeIfAbsent(
        K key,
        Function<? super K, ? extends V> mappingFunction);

V compute(
        K key,
        BiFunction<? super K, ? super V, ? extends V> remappingFunction);

V merge(
        K key,
        V value,
        BiFunction<? super V, ? super V, ? extends V> remappingFunction);
```

Đây là **chữ ký rút gọn để học API**, không phải đoạn mã độc lập để đặt vào class. Các interface hàm thuộc `java.util.function`. Một giá trị `null` được sử dụng để biểu đạt một trạng thái đặc biệt theo hợp đồng từng phương thức; cách dùng `null` cũng phụ thuộc loại Map cụ thể.

Khác biệt cốt lõi:

| API | Lambda nhận gì? | Khi nào lambda được gọi? | Nếu lambda trả `null` |
| --- | --- | --- | --- |
| `computeIfAbsent(key, f)` | `key` | Khi khóa chưa có mapping **hoặc hiện ánh xạ tới `null`** | Không ghi giá trị mới; mapping `null` sẵn có có thể vẫn được giữ |
| `compute(key, f)` | `key`, `oldValue` | Cho khóa được yêu cầu, dù trước đó có giá trị hay không | Xóa mapping nếu đang có; nếu chưa có thì không thêm |
| `merge(key, value, f)` | `oldValue`, `value` | Chỉ khi khóa đang có **giá trị khác `null`** | Xóa mapping |

`merge` còn yêu cầu tham số `value` và `remappingFunction` **không được `null`**. Nó dùng trực tiếp `value` để tạo mapping khi trước đó không có giá trị khác `null`, vì vậy không gọi remapping function ở nhánh đó.

**Lưu ý quan trọng:** `Map` là interface. Một số triển khai cho phép khóa hoặc giá trị `null` như `HashMap`, `LinkedHashMap`; `ConcurrentHashMap` không cho phép cả khóa lẫn giá trị `null`. Đồng thời, các bảo đảm về đồng bộ và số lần thực thi hàm có thể khác nhau giữa các triển khai.

## 2. computeIfAbsent(): chỉ tạo giá trị khi cần

### 2.1. Cú pháp và luồng xử lý

```java
Map<String, Integer> cache = new HashMap<>();

Integer length = cache.computeIfAbsent(
        "Java",
        key -> key.length()
);
```

Đây là đoạn minh họa cần import `java.util.Map`, `java.util.HashMap` và đặt trong phương thức hợp lệ. `Function<? super K, ? extends V>` có function descriptor tương đương `(K) -> V` trong ngữ cảnh Map đã biết kiểu. Với `Map<String,Integer>`, `key` có kiểu `String`, kết quả `int` từ `length()` được boxing sang `Integer`.

Các tình huống:

1. Nếu khóa **chưa có mapping**: gọi `mappingFunction.apply(key)`. Nếu trả giá trị khác null, lưu giá trị rồi trả về nó.
2. Nếu khóa **đã ánh xạ đến null** và Map cho phép `null`: cũng gọi mapping function; nếu trả khác null, thay giá trị null bằng giá trị mới.
3. Nếu khóa **đã có giá trị khác null**: trả giá trị cũ, **không gọi** mapping function.
4. Nếu mapping function trả `null`: không tạo mapping mới. Nếu trước đó khóa có mapping `null` thì mapping ấy không tự bị xóa chỉ bởi việc function trả null.

Điểm cuối cùng dễ nhầm. `computeIfAbsent` không có nghĩa “nếu không tìm thấy thì luôn thêm một phần tử”. Chỉ kết quả **khác null** mới được lưu thành giá trị mới.

### 2.2. Giá trị null và khóa không tồn tại

```java
Map<String, String> names = new HashMap<>();
names.put("Mai", null);

names.computeIfAbsent("Mai", key -> "Mai Anh");
System.out.println(names.get("Mai")); // Mai Anh

names.computeIfAbsent("Lan", key -> null);
System.out.println(names.containsKey("Lan")); // false
```

Ở đây Map ban đầu có khóa `"Mai"` nhưng giá trị `null`, nên callback cho `"Mai"` vẫn được gọi. Với `"Lan"` chưa tồn tại, callback trả null và không thêm khóa.

Nếu cần xác định chính xác một khóa có mặt hay không, `containsKey` có ý nghĩa khác `get(key) == null` khi Map cho phép giá trị null. `get` trả null trong cả hai trường hợp: khóa không có và khóa có mapping null.

### 2.3. Áp dụng: khởi tạo collection theo nhu cầu

```java
Map<String, List<String>> groups = new HashMap<>();

groups.computeIfAbsent("java", key -> new ArrayList<>())
      .add("Lan");
groups.computeIfAbsent("java", key -> new ArrayList<>())
      .add("Mai");
```

Đây là đoạn minh họa cần import `Map`, `List`, `HashMap` và `ArrayList`. Lần đầu với `"java"` tạo danh sách mới; lần tiếp theo dùng danh sách đã có. Kết quả dự kiến tại `groups.get("java")` là `[Lan, Mai]`.

Tuy nhiên danh sách ở đây là **mutable**. Nếu nhiều thread cùng thêm phần tử, tính an toàn của Map chưa bảo đảm tính an toàn khi thao tác `List.add`. Muốn xử lý đồng thời phải thiết kế đồng bộ cho cả cấu trúc giá trị, không chỉ Map.

## 3. compute(): quyết định giá trị mới từ khóa và giá trị cũ

`compute` nhận một `BiFunction<? super K, ? super V, ? extends V>`. Với `Map<String,Integer>`, lambda có thể viết:

```java
points.compute("Mai", (key, oldValue) -> {
    return oldValue == null ? 1 : oldValue + 1;
});
```

Đây là mã minh họa; `points` phải được khai báo kiểu `Map<String,Integer>` trước đó.

**Hợp đồng:**

- Callback nhận **khóa** làm tham số thứ nhất.
- Callback nhận **giá trị cũ** làm tham số thứ hai.
- Nếu chưa có mapping, hoặc mapping cũ là null, `oldValue` được truyền là null.
- Nếu callback trả giá trị **khác null**, Map liên kết khóa với giá trị đó và trả về giá trị mới.
- Nếu callback trả `null`, mapping được **xóa nếu có**, hoặc không thêm nếu trước đó không có.

Vì `oldValue == null` đại diện cho cả “khóa chưa tồn tại” lẫn “khóa có giá trị null”, nếu logic cần phân biệt hai trường hợp này thì chỉ nhìn vào `oldValue` là chưa đủ. Khi phải đọc trạng thái bên ngoài callback, hãy xét tính nhất quán và tính đồng thời thay vì giả định một phép kiểm tra `containsKey` tách rời được cập nhật nguyên tử.

### 3.1. Cập nhật hoặc khởi tạo cùng một quy tắc

```java
Map<String, Integer> visits = new HashMap<>();

visits.compute("article-1",
        (key, old) -> old == null ? 1 : old + 1);
visits.compute("article-1",
        (key, old) -> old == null ? 1 : old + 1);

// visits.get("article-1") là 2.
```

`compute` gọi remapping function ở cả hai lượt. Việc kiểm tra `old == null` xử lý trường hợp ban đầu chưa có giá trị.

### 3.2. Xóa mapping bằng kết quả null

```java
Map<String, Integer> quota = new HashMap<>();
quota.put("Mai", 5);

quota.compute("Mai", (key, old) -> null);
System.out.println(quota.containsKey("Mai")); // false
```

Đây là quy ước có chủ đích của API, không phải một lỗi “bị mất dữ liệu”. Nếu `null` có ý nghĩa giá trị nghiệp vụ cần giữ, phải lựa chọn kiểu chứa dữ liệu hoặc cấu trúc Map phù hợp và không tùy tiện trả null từ callback.

**Chọn `compute` khi:** công thức cần cả `key` lẫn giá trị cũ; muốn dùng một điểm mở rộng xử lý mọi trạng thái; hoặc có thể muốn xóa mapping dựa trên điều kiện.

## 4. merge(): kết hợp một giá trị mới với giá trị đang có

`merge` hợp với cộng dồn số lượng, tổng hợp tiền, ghép chuỗi hoặc kết hợp kết quả theo khóa.

```java
Map<String, Integer> counts = new HashMap<>();

counts.merge("java", 1, Integer::sum);
counts.merge("java", 1, Integer::sum);
counts.merge("java", 1, Integer::sum);

// counts.get("java") là 3.
```

Với `Map<String,Integer>`, tham số `value` ở đây là `1`. Khi chưa có giá trị khác null, Map đưa `1` trực tiếp vào; ở các lượt sau, `Integer::sum` nhận giá trị cũ và giá trị `1` để cộng lại.

### 4.1. Tham số remapping function không có khóa

`merge(key, value, (oldValue, newValue) -> result)` có descriptor `(V,V) -> V`, **không có tham số `key` trong callback**.

Ví dụ:

```java
Map<String, String> messages = new HashMap<>();

messages.merge("errors", "E1", (oldText, incoming) ->
        oldText + "," + incoming);
messages.merge("errors", "E2", (oldText, incoming) ->
        oldText + "," + incoming);

// messages.get("errors") là "E1,E2".
```

Nếu quy tắc kết hợp cần đọc khóa để quyết định, `compute(key, (key, old) -> ...)` có thể phù hợp hơn. `merge` nhận sẵn giá trị mới như tham số phương thức nên trường hợp chưa có mapping không cần gọi callback để tạo giá trị đó.

### 4.2. Ba trường hợp của merge

| Trạng thái trước khi gọi | Hành vi của `merge(k, v, f)` |
| --- | --- |
| Không có khóa `k` | Liên kết `k -> v`; không gọi `f` |
| `k` đang ánh xạ đến null (với Map cho phép null) | Liên kết `k -> v`; không gọi `f` |
| `k` đang ánh xạ đến giá trị `old` khác null | Gọi `f.apply(old, v)`, lưu kết quả nếu khác null; nếu trả null thì xóa khóa |

`v` **không được null**, và `f` cũng không được null. Đáng chú ý, đối số `v` được Java đánh giá **trước khi gọi phương thức**. Vì vậy:

```java
// Minh họa: expensiveValue() là phương thức bên ngoài.
map.merge("key", expensiveValue(), (oldValue, incoming) ->
        combine(oldValue, incoming));
```

Dù remapping function bị bỏ qua vì khóa đang trống, `expensiveValue()` vẫn được tính để làm đối số `value`. Đó không phải lazy supplier. Nếu chỉ muốn tạo giá trị tốn kém khi thiếu khóa, `computeIfAbsent` hoặc một thiết kế khác có thể phù hợp hơn.

### 4.3. Xóa bằng null

```java
Map<String,Integer> counts = new HashMap<>();
counts.put("java", 5);

counts.merge("java", 1, (oldValue, incoming) -> null);
System.out.println(counts.containsKey("java")); // false
```

Đừng nhầm **tham số `value`** null với **kết quả callback** null: tham số `value = null` là không hợp lệ; kết quả remapping function null có nghĩa xóa mapping khi callback được gọi.

## 5. Bảng quyết định: dùng API nào?

| Nhu cầu nghiệp vụ | API phù hợp | Vì sao |
| --- | --- | --- |
| Lấy dữ liệu trong cache, chỉ tải khi chưa có giá trị | `computeIfAbsent` | Chỉ gọi hàm khởi tạo khi cần |
| Khởi tạo danh sách và thêm phần tử cho một khóa | `computeIfAbsent` | Tạo collection khi thiếu rồi thao tác trên collection được trả về |
| Thay đổi một giá trị dựa trên cả khóa và giá trị cũ | `compute` | Callback nhận `key` và `oldValue` |
| Đặt/xóa mapping theo quy tắc có thể trả null | `compute` | Callback được gọi với trạng thái hiện có |
| Cộng bộ đếm theo khóa | `merge(k,1,Integer::sum)` | Nhánh chưa có khóa dùng trực tiếp `1` |
| Gộp giá trị mới từ bên ngoài vào bản đã có | `merge` | Callback nhận hai giá trị cũ và mới |
| Chỉ cần đọc giá trị đã có | `get` hoặc `getOrDefault` | Không cần đưa callback cập nhật vào Map |
| Cập nhật giá trị cố định không cần tính lại | `put` hoặc `replace` tùy điều kiện | Hợp đồng đơn giản hơn |

Không có một phương thức “tốt nhất” cho mọi trường hợp. Hãy chọn theo **thời điểm cần callback**, các đối số thực sự cần và ý nghĩa của `null`.

## 6. Chương trình Java 17 hoàn chỉnh

Đây là ví dụ chạy đầy đủ, dùng `LinkedHashMap` để kết quả hiển thị có thứ tự ổn định, đồng thời minh họa `ConcurrentHashMap.merge` khi cộng dồn.

Tạo file **`MapCallbacksDemo.java`**:

```java
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;

public class MapCallbacksDemo {
    public static void main(String[] args) {
        Map<String, Integer> scores = new LinkedHashMap<>();
        scores.put("Mai", null);

        AtomicInteger loads = new AtomicInteger();
        int first = scores.computeIfAbsent("Mai", key -> {
            loads.incrementAndGet();
            return 10;
        });
        int second = scores.computeIfAbsent("Mai", key -> {
            loads.incrementAndGet();
            return 99;
        });
        System.out.println("computeIfAbsent: " + first + ", " + second
                + ", loads=" + loads.get());
        System.out.println("Map: " + scores);

        Integer updated = scores.compute("Mai",
                (key, old) -> old == null ? 0 : old + 5);
        System.out.println("compute: " + updated);

        Integer merged = scores.merge("Mai", 7, Integer::sum);
        System.out.println("merge existing: " + merged);

        Integer newValue = scores.merge("Lan", 3, Integer::sum);
        System.out.println("merge new: " + newValue + ", map=" + scores);

        scores.compute("Lan", (key, old) -> null);
        System.out.println("after compute null: " + scores);

        scores.merge("Mai", 1, (oldValue, incoming) -> null);
        System.out.println("after merge null: " + scores);

        Integer absent = scores.computeIfAbsent("Unknown", key -> null);
        System.out.println("absent null: " + absent
                + ", contains=" + scores.containsKey("Unknown"));

        scores.put("Nullable", null);
        scores.computeIfAbsent("Nullable", key -> null);
        System.out.println("existing null mapping: "
                + scores.containsKey("Nullable") + "/" + scores.get("Nullable"));

        ConcurrentHashMap<String, Integer> counts = new ConcurrentHashMap<>();
        for (int i = 0; i < 3; i++) {
            counts.merge("clicks", 1, Integer::sum);
        }
        System.out.println("counts: " + counts);
    }
}
```

Biên dịch bằng JDK 17 trở lên:

```bash
javac MapCallbacksDemo.java
java MapCallbacksDemo
```

**Stdout chính xác:**

```text
computeIfAbsent: 10, 10, loads=1
Map: {Mai=10}
compute: 15
merge existing: 22
merge new: 3, map={Mai=22, Lan=3}
after compute null: {Mai=22}
after merge null: {}
absent null: null, contains=false
existing null mapping: true/null
counts: {clicks=3}
```

### 6.1. Phân tích từng bước

1. `scores.put("Mai", null)` tạo một mapping có khóa `"Mai"` nhưng chưa có giá trị thực tế. `LinkedHashMap` chấp nhận giá trị null.
2. `computeIfAbsent("Mai", ...)` thấy giá trị là null, gọi function, tăng `loads` lên `1` rồi ghi `10`. Lần gọi thứ hai thấy `10` nên **không gọi** function; `loads` vẫn bằng `1`. Cả `first` và `second` bằng `10`.
3. `compute("Mai", ...)` nhận `key = "Mai"` và `old = 10`, trả `15`; Map lưu `15`.
4. `merge("Mai", 7, Integer::sum)` nhận giá trị cũ `15` và giá trị mới `7`, trả `22`.
5. `merge("Lan", 3, Integer::sum)` không có giá trị cũ, nên lưu trực tiếp `3` mà không gọi `Integer::sum`. `LinkedHashMap` giữ thứ tự chèn `Mai` rồi `Lan`.
6. `compute("Lan", ..., null)` trả null, làm mất mapping `Lan`.
7. `merge("Mai", 1, (old,incoming) -> null)` chạy callback vì `Mai` đang có `22`; kết quả null xóa mapping `Mai`, Map rỗng.
8. `computeIfAbsent("Unknown", key -> null)` không thêm mapping mới. `containsKey("Unknown")` là `false`.
9. Map được chèn `Nullable -> null`. Callback tiếp tục trả null nên **mapping null sẵn có vẫn tồn tại**. Vì thế dòng cuối có `true/null`.
10. `ConcurrentHashMap` với khóa `"clicks"` được cộng ba lần bằng `merge` và ra `3`. Ví dụ chạy tuần tự; chưa chứng minh chương trình xử lý toàn bộ các vấn đề đồng thời nếu các giá trị phức tạp hay callback có tác dụng phụ.

Chương trình đã dùng kiểu dữ liệu và API có trong Java 17, có tên file trùng `public class`, không phụ thuộc mạng hay dữ liệu ngoài. Để hiển thị dấu tiếng Việt trong chú thích và các bài tập đi kèm, môi trường terminal nên sử dụng UTF-8; output ví dụ chính dùng ký tự ASCII và có thể đối chiếu trực tiếp.

## 7. Khi callback ném ngoại lệ hoặc tạo tác dụng phụ

Cả ba API đều nhận lambda có thể gây lỗi runtime. Nếu callback ném **unchecked exception**, phép gọi phương thức có thể kết thúc bằng ngoại lệ và không có giá trị trả về bình thường. Với các triển khai thông thường và hợp đồng API, mapping liên quan đến thao tác thất bại không được cập nhật thành kết quả mới. Tuy nhiên, nếu callback tự sửa các object bên ngoài, **những tác dụng phụ đó không tự được hoàn tác**.

Ví dụ:

```java
// Minh họa: cache là Map<String,Integer> đã khai báo.
cache.compute("key", (key, old) -> {
    auditLog.add("attempt " + key); // tác dụng phụ bên ngoài Map
    throw new IllegalStateException("failed");
});
```

Đoạn này không độc lập: cần khai báo `cache` và `auditLog`. Nếu exception xảy ra, dòng thêm vào `auditLog` đã chạy. Không nên xem compute là một transaction tự rollback tất cả thay đổi bên ngoài.

Một lỗi khác: functional interface chuẩn `Function.apply` và `BiFunction.apply` **không khai báo checked exception** như `IOException` hoặc `SQLException`. Nếu lambda gọi API có checked exception, phải xử lý nó bên trong, chuyển thành unchecked theo chính sách nghiệp vụ hoặc tách I/O ra khỏi callback. Khai báo `throws IOException` ở phương thức gọi bên ngoài không tự mở rộng hợp đồng của `Function`.

### 7.1. Tránh thay đổi cùng Map ngay trong callback

Mã như:

```java
// KHÔNG nên làm: thay đổi chính Map từ bên trong remapping callback.
map.compute("k", (key, old) -> {
    map.put("other", 123);
    return 456;
});
```

Có nguy cơ phá giả định của thuật toán cập nhật. Java documentation yêu cầu callback không sửa chính Map trong lúc tính mapping. Với các Map không đồng thời, một số triển khai có thể phát hiện và ném `ConcurrentModificationException`; với các Map đồng thời, hành vi có thể bị ngăn chặn hoặc gây lỗi cập nhật đệ quy. Đừng viết logic phụ thuộc việc thao tác này “tình cờ vẫn chạy” ở một phiên bản runtime.

Nếu cần cập nhật nhiều khóa theo quy tắc nhất quán, hãy thiết kế một thao tác phối hợp riêng có đồng bộ/giao dịch theo loại dữ liệu và môi trường sử dụng. `compute` chỉ diễn đạt phép tính một mapping theo khóa, không biến cả Map thành transaction đa khóa.

### 7.2. Callback nên ngắn và ít tác dụng phụ

Callback gọn như `Integer::sum` dễ suy luận. Callback ghi log, gửi email hoặc gọi REST có thể bị gọi ở thời điểm khác dự kiến; trong môi trường concurrent có thể phải xử lý thử lại hoặc gặp tương tác giữa thread. Hãy tách phép tính thuần và tác vụ I/O khi có thể.

## 8. Concurrency: Map thường khác ConcurrentHashMap

**Đừng giả định** `Map.computeIfAbsent`, `Map.compute` hoặc `Map.merge` có bảo đảm nguyên tử giống nhau trên mọi implementation.

### 8.1. HashMap/LinkedHashMap

`HashMap` và `LinkedHashMap` không cung cấp an toàn cập nhật đồng thời chỉ vì được gọi qua `compute`. Nếu nhiều thread cùng thao tác, cần đồng bộ phù hợp hoặc một triển khai concurrent; những chuỗi thao tác `get` → `put` càng dễ gây mất cập nhật.

Chẳng hạn, hai thread cùng đọc `0` rồi cùng ghi `1` có thể làm mất một lượt tăng. Đưa logic vào `compute` trên Map không thread-safe không tự sửa được vấn đề.

### 8.2. ConcurrentHashMap

`ConcurrentHashMap` triển khai các phương thức cập nhật này với bảo đảm nguyên tử cho thao tác mapping theo khóa theo hợp đồng riêng của nó. Với `computeIfAbsent`, quá trình xác định/thiết lập mapping theo khóa được thực hiện nguyên tử; các cập nhật khác có thể bị chặn trong lúc computation đang chạy. Với `compute` và `merge`, việc cập nhật cụ thể cũng được đồng bộ theo hợp đồng của Map concurrent.

`ConcurrentHashMap` **không cho `null` làm khóa hoặc giá trị**. Vì thế không thể thử `put("Mai", null)` trên nó như ví dụ `LinkedHashMap`. Kết quả null của mapping function thường mang nghĩa không thiết lập mapping (hoặc xóa mapping khi method quy định), không phải lưu giá trị null.

```java
java.util.concurrent.ConcurrentHashMap<String, Integer> counts =
        new java.util.concurrent.ConcurrentHashMap<>();

counts.merge("views", 1, Integer::sum);
counts.merge("views", 1, Integer::sum);
System.out.println(counts.get("views")); // 2
```

Đây là đoạn minh họa hợp lệ đặt trong phương thức. Nếu nhiều thread tăng cùng khóa, `merge` của `ConcurrentHashMap` thích hợp hơn vòng lặp đọc rồi ghi không đồng bộ.

**Các điểm cần cẩn thận:**

- Computation trong callback nên **ngắn và đơn giản**; không giữ thao tác cập nhật lâu khi có nhiều thread tranh chấp.
- Không cập nhật lại chính Map đó từ callback đang tính mapping. Với `ConcurrentHashMap`, các cập nhật đệ quy có thể phát sinh `IllegalStateException` nếu phát hiện được.
- Không ngầm coi callback là một cơ chế thực thi I/O đúng một lần trong toàn bộ vòng đời ứng dụng: xóa mapping, lỗi hoặc các lần gọi tiếp theo có thể khiến computation được thực hiện lại.
- Tính nguyên tử của mapping trong `ConcurrentHashMap` không khiến **object giá trị mutable** (như `ArrayList` được lưu trong Map) tự thread-safe.

Nếu hệ thống cần tổng hợp nhiều số đếm với tần suất cực cao, có thể xem `LongAdder` kết hợp với `computeIfAbsent` cho từng khóa, nhưng vẫn phải hiểu vòng đời giá trị và cách đọc nhất quán số đếm.

## 9. Các tình huống biên cần nhớ

### 9.1. Map chứa khóa với giá trị null

Với `HashMap`:

```java
Map<String,Integer> map = new HashMap<>();
map.put("k", null);
```

- `map.get("k")` là null nhưng `map.containsKey("k")` là true.
- `computeIfAbsent("k", key -> 7)` thay null bằng `7`.
- `compute("k", (key, old) -> old == null ? 5 : old + 1)` nhận `old = null`, có thể ghi `5` nếu gọi ở trạng thái chưa có giá trị.
- `merge("k", 2, Integer::sum)` ghi `2` mà không gọi `Integer::sum` nếu giá trị trước đó là null.

Các dòng trên là các **trường hợp riêng để phân tích**; không phải một chuỗi thao tác liên tiếp trên cùng Map nếu muốn mỗi dòng đều bắt đầu từ `k -> null`.

### 9.2. Callback trả null

| Lời gọi | Với khóa chưa có | Với khóa có giá trị khác null |
| --- | --- | --- |
| `computeIfAbsent(k, key -> null)` | Không thêm | Không gọi lambda, trả giá trị cũ |
| `compute(k, (key, old) -> null)` | Không thêm | Xóa mapping |
| `merge(k, v, (old, incoming) -> null)` với `v != null` | Thêm `v`, callback không chạy | Xóa mapping |

Bảng này không thay thế việc xét tình huống “khóa đang map tới null”; ở trạng thái đó `computeIfAbsent` gọi hàm, `compute` nhận old=null và `merge` dùng trực tiếp v.

### 9.3. Lambda có thông tin khác nhau

`computeIfAbsent` nhận `key` nhưng không nhận old value; `compute` nhận cả key và old; `merge` chỉ nhận hai giá trị old/incoming (không có key trực tiếp). Nếu chọn sai API, bạn có thể phải capture state bên ngoài không cần thiết, làm mã khó kiểm thử.

### 9.4. Khi cần tạo giá trị mới từ dữ liệu đắt đỏ

`computeIfAbsent("key", k -> load(k))` là một cách chỉ gọi `load` khi chưa có giá trị. `merge("key", load("key"), combiner)` sẽ **gọi `load` để tính tham số** trước khi vào `merge`, kể cả nếu giá trị cũ đã có. Hãy cân nhắc cả chi phí và số lần gọi; đừng giả định mọi API nhận lambda đều lazy.

## 10. Những lỗi thường gặp và cách phòng tránh

1. **Nhầm “absent” với “không có khóa”.** `computeIfAbsent` coi giá trị hiện tại null là trường hợp cần tính lại; `containsKey` mới phân biệt khóa có mặt nếu Map cho phép giá trị null.
2. **Dùng `computeIfAbsent` mà muốn luôn cập nhật.** Khi giá trị khác null đã tồn tại, callback sẽ không chạy. Dùng `compute` hoặc `merge` theo yêu cầu.
3. **Dùng `compute` mà quên oldValue có thể null.** Khi khóa chưa có hoặc trỏ tới null, `oldValue` là null; `oldValue + 1` sẽ gây unboxing NPE.
4. **Nhầm thứ tự tham số của merge.** Callback của `merge` nhận `(oldValue, incoming)`, **không phải `(key, oldValue)`**.
5. **Truyền giá trị null cho `merge`.** API yêu cầu tham số `value` khác null, không dùng null để ra lệnh xóa. Muốn xóa có điều kiện, callback có thể trả null khi nó được gọi.
6. **Tưởng `null` luôn có cùng nghĩa.** Trong `computeIfAbsent`, null nghĩa không thiết lập giá trị mới; trong `compute` và nhánh remapping của `merge`, null có thể xóa mapping.
7. **Tưởng Map default methods luôn atomic.** Không có bảo đảm chung đó trên Map thường; phải chọn implementation và đồng bộ đúng.
8. **Gây tác dụng phụ lên cùng Map bên trong callback.** Dễ gây lỗi reentrancy hoặc kết quả không xác định theo triển khai; tránh thao tác này.
9. **Ẩn I/O chậm hoặc không idempotent trong callback.** Có thể gây trì hoãn, lỗi, tranh chấp, và cần quy tắc retry riêng.
10. **Quên mutable value.** `Map<String,List<Item>>` dùng `computeIfAbsent` không làm `List` thread-safe.
11. **Cho rằng callback có thể ném checked exception tùy ý.** `Function`/`BiFunction` không khai báo checked exception; cần bắt/xử lý đúng hợp đồng.
12. **Chọn `merge` cho mọi cập nhật.** Khi logic thực sự phụ thuộc khóa, `compute` thường thể hiện mục đích tốt hơn.

## 11. Bài tập tự luyện

1. Với `Map<String,Integer> map = new HashMap<>()`, hãy dự đoán `computeIfAbsent("a", k -> 5)` chạy callback mấy lần nếu gọi liên tiếp hai lần mà không sửa Map.
2. Giả sử `map.put("a", null)` trên `HashMap`. Khi gọi `computeIfAbsent("a", k -> 7)`, callback có được gọi không? Kết quả `containsKey("a")` và `get("a")` thế nào?
3. Cho `map.put("b", 2)`, gọi `compute("b", (k,old) -> old * 3)`. Giá trị mới của `"b"` là gì? Nếu callback trả null thì sao?
4. Viết một biểu thức `merge` tăng số lần truy cập cho khóa `"home"` lên 1, bắt đầu khi Map chưa có khóa.
5. Trong `merge("k", 10, (oldValue, incoming) -> oldValue - incoming)`, giá trị nào là old và giá trị nào là incoming? Callback có chạy khi `"k"` đang ánh xạ null không?
6. Vì sao `merge("k", expensive(), f)` vẫn gọi `expensive()` trước khi biết Map có giá trị cũ hay chưa?
7. Nếu dùng `ConcurrentHashMap<String, List<String>>` rồi `computeIfAbsent` trả `ArrayList`, việc nhiều thread cùng `add` có tự an toàn không?
8. Một callback `compute` tự gọi `map.put` lên cùng Map. Vì sao nên tránh, đặc biệt khi triển khai có hỗ trợ concurrent?
9. Với `Map<String,Integer>` có thể chứa null, phân biệt `get("x") == null` và `containsKey("x") == false`.
10. Cho callback `merge` trả null khi tổng vượt ngưỡng. Hãy giải thích trạng thái mới của khóa nếu trước đó đã có giá trị khác null, rồi so với khi khóa chưa tồn tại.

**Gợi ý đáp án:** (1) Một lần, nếu lần đầu trả `5`; lần hai đọc giá trị đã có. (2) Có, vì giá trị cũ null; kết quả `true` và `7`. (3) `6`; trả null thì xóa mapping. (4) `map.merge("home", 1, Integer::sum)`. (5) `oldValue` là giá trị Map hiện có, `incoming` là `10`; khi giá trị Map null, callback không chạy, Map nhận trực tiếp `10`. (6) Java đánh giá đối số trước khi gọi phương thức. (7) Không; cấu trúc List cần cơ chế đồng bộ riêng. (8) Xung đột quá trình remapping và có thể bị phát hiện/lỗi. (9) `get==null` bao gồm cả khóa thiếu hoặc có giá trị null; `containsKey==false` xác nhận không có khóa. (10) Trả null ở nhánh remapping xóa mapping; với khóa chưa tồn tại, `merge` thêm giá trị đầu vào và không gọi callback.

## Kết luận

`Map.computeIfAbsent()`, `Map.compute()` và `Map.merge()` là những ví dụ rõ ràng của việc **API Java nhận hành vi bằng functional interface**. Sự khác biệt quyết định nằm ở **đầu vào của callback, điều kiện gọi callback và ý nghĩa của kết quả null**:

- **`computeIfAbsent`:** khởi tạo khi chưa có giá trị khác null.
- **`compute`:** tính lại từ khóa và giá trị cũ cho mọi trường hợp.
- **`merge`:** kết hợp giá trị có sẵn với giá trị mới, hoặc dùng trực tiếp giá trị mới khi chưa có giá trị khác null.

Muốn áp dụng an toàn trong ứng dụng thực tế, hãy xác định loại Map, tính đồng thời, tác dụng phụ, xử lý ngoại lệ và tính mutable của giá trị trước khi chọn API. Cách viết lambda ngắn không thay thế được việc hiểu đúng hợp đồng cập nhật.
