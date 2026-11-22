# Thiết kế bảng tra cứu và ảnh chụp cấu hình bằng `Map.copyOf`

> **Phạm vi:** `Map.copyOf(Map)` được bổ sung trong Java 10 và vẫn là API chuẩn trên các JDK hiện đại. Bài hướng dẫn thiết kế **bảng tra cứu chỉ đọc** (*read-only lookup table*) và **snapshot cấu hình** không cho sửa, đồng thời phân biệt với `HashMap` mutable và `Collections.unmodifiableMap` dạng live view. Chỉ dùng kiến thức, API và cách thiết kế còn áp dụng hiện nay; không cần cài bản Java 10 đã cũ.

## 1. Mục tiêu học tập

Sau bài, bạn có thể:

1. Giải thích chính xác hợp đồng của `Map.copyOf`: snapshot các entry tại thời điểm tạo, kết quả không cho sửa, không nhận khóa hoặc giá trị `null`.
2. Chọn `Map.of`, `Map.ofEntries`, `Map.copyOf`, `HashMap` hoặc `Collections.unmodifiableMap` theo nguồn dữ liệu, khả năng cập nhật và quyền sở hữu.
3. Thiết kế bảng tra cứu từ dữ liệu đầu vào với các bước **validate → build mutable → publish unmodifiable**, thay vì để bên gọi sửa trực tiếp dữ liệu nội bộ.
4. Dùng ảnh chụp cấu hình để độc lập với các thay đổi sau đó của `Map` nguồn; phân biệt **snapshot cấu trúc** với **sao chép sâu** của các đối tượng key/value.
5. Thiết kế mô hình cập nhật cấu hình theo phiên bản với `AtomicReference<Map<K,V>>` khi có nhiều luồng đọc; hiểu giới hạn của `Map.copyOf` đối với thread safety.
6. Xử lý đúng duplicate keys, thứ tự duyệt, `null`, lookup thiếu khóa, chi phí copy và kiểm thử mà không dựa vào chi tiết implementation.
7. Biên dịch, chạy và giải thích output của một chương trình Java độc lập.

## 2. Vì sao `Map.copyOf` phù hợp cho bảng tra cứu và snapshot?

Bảng tra cứu thường là ánh xạ **khóa → giá trị**: mã trạng thái → HTTP code, tên cấu hình → giá trị, mã sản phẩm → mức thuế, tên tính năng → cờ bật/tắt. Khi hoàn thành việc xây dựng, nhiều bảng như vậy chỉ cần đọc. Nếu caller có thể `put` hoặc `remove` trực tiếp, việc đọc ở nơi khác có thể nhận dữ liệu không còn đúng hợp đồng.

Xem ví dụ ngắn (đoạn mã nằm **bên trong một phương thức**):

```java
var working = new java.util.HashMap<String, Integer>();
working.put("timeoutMs", 500);
working.put("retries", 2);

var published = java.util.Map.copyOf(working);

working.put("retries", 9);
System.out.println(working.get("retries")); // 9
System.out.println(published.get("retries")); // 2
```

`published` là bản chụp không cho sửa của các entry trong `working`. Thay đổi cấu trúc hay phép gán value ở `working` **sau** khi copy không làm thay đổi map được công bố.

**Tuy nhiên,** ví dụ trên chỉ an toàn như một snapshot giá trị ổn định vì cả khóa (`String`) lẫn value (`Integer`) đều bất biến. Nếu value là đối tượng mutable, `Map.copyOf` vẫn giữ tham chiếu đến đối tượng đó; xem phần 9.

Đừng gọi `Map.copyOf` là cách “khóa” chính đối tượng `working`. Nó tạo ra **một map kết quả không cho sửa**; `working.put(...)` vẫn thực hiện bình thường.

## 3. Hợp đồng của API Java 10

Chữ ký khái quát trong `java.util.Map`:

```java
static <K, V> Map<K, V> copyOf(
        Map<? extends K, ? extends V> map)
```

- **Đầu vào:** một `Map` đã có; không phải danh sách các cặp key/value rời.
- **Đầu ra:** `Map<K,V>` chứa cùng các ánh xạ key/value như nguồn vào thời điểm tạo, không cho phép thêm, xóa hoặc cập nhật entry qua API map.
- **Khi sửa kết quả:** các thao tác sửa không được hỗ trợ; ví dụ `put` và `remove` ném `UnsupportedOperationException`.
- **Khi nguồn đổi sau đó:** kết quả không phản ánh việc thêm/xóa/thay value của nguồn. Đó là snapshot của **cấu trúc entry**.
- **`null`:** bản thân map nguồn `null`, khóa `null` hoặc value `null` đều không hợp lệ, thường ném `NullPointerException` khi copy.
- **Thứ tự:** thứ tự duyệt entries/keys/values của map kết quả **không được bảo đảm**; đừng suy ra nó từ `LinkedHashMap` nguồn.
- **Danh tính object:** nếu nguồn đã là một map unmodifiable phù hợp, `copyOf` có thể tái sử dụng đối tượng. Không dùng `==` để kiểm tra “đã copy” và không phụ thuộc object identity của collection value-based.
- **Tính đồng thời:** API không tự đặt khóa, không tự tạo transaction, cũng không tự đảm bảo nhất quán nếu có người thay nguồn **trong lúc** copy.

Đây là những khác biệt cần nắm để đặt `Map.copyOf` đúng vị trí tại **ranh giới dữ liệu**.

### So sánh nhanh các lựa chọn

| API | Nguồn tạo | Có thể sửa kết quả? | Thay đổi map nguồn sau đó có phản ánh vào kết quả? | Tình huống thường gặp |
| --- | --- | --- | --- | --- |
| `new HashMap<>(source)` | Map đã có | Có | Không ở mức cấu trúc entry | Bản sao làm việc độc lập, còn cần `put/remove` |
| `Map.of("A", 1, "B", 2)` | Các cặp hằng số trực tiếp | Không | Không có map nguồn | Bảng tra cứu nhỏ, cố định tại chỗ |
| `Map.ofEntries(...)` | Các `Map.entry(k,v)` | Không | Không có map nguồn | Nhiều cặp cố định hơn overload tiện dụng của `Map.of` |
| `Map.copyOf(source)` | Map nguồn bất kỳ hợp lệ | Không | Không | Bảng tra cứu/snapshot từ dữ liệu xây dựng hoặc nạp ngoài |
| `Collections.unmodifiableMap(source)` | Map nguồn | Không qua view | **Có**, nếu nguồn được sửa qua tham chiếu khác | Live view có chủ ý để người đọc quan sát trạng thái nguồn |
| `Collectors.toUnmodifiableMap(...)` | Stream các phần tử | Không | Không có map nguồn | Thu thập dữ liệu thành map chỉ đọc sau pipeline |

`Map.of` và `Map.ofEntries` có từ **Java 9**, trong khi `Map.copyOf` và `Collectors.toUnmodifiableMap` được bổ sung ở **Java 10**. Tất cả đều còn hữu ích trên JDK được bảo trì. Không gán nhầm mọi API trong bảng cho Java 10.

## 4. Mô hình thiết kế: build mutable → validate → publish

Nên tách rõ thời gian **đang xây dựng dữ liệu** và thời gian **công bố dữ liệu cho người đọc**.

```text
Đầu vào (file/config/API)
        |
        v
Parse / chuẩn hóa / kiểm tra hợp lệ
        |
        v
HashMap hoặc LinkedHashMap mutable do một thành phần sở hữu
        |
        v
Kiểm tra khóa bắt buộc, giá trị, null và xung đột khóa
        |
        v
Map.copyOf(builder)
        |
        v
Công bố Map<K,V> không cho sửa cho reader
```

Quy trình cho một bản snapshot:

1. **Xác định schema:** key nào được chấp nhận? Value là số dương hay chuỗi không rỗng? Thiếu key có giá trị mặc định không? Có chấp nhận null không? Quy tắc này thuộc nghiệp vụ; `Map.copyOf` không tự hiểu chúng.
2. **Tạo builder riêng:** dùng `HashMap` hoặc `LinkedHashMap` trong phương thức nạp dữ liệu, không chia sẻ tham chiếu trong lúc đang điền entries.
3. **Chuẩn hóa:** ví dụ `trim` tên key, parse số, kiểm tra khoảng cho `timeoutMs`. Không mặc định mọi key có thể đổi hoa/thường nếu hợp đồng không nói vậy.
4. **Phát hiện duplicate theo nghiệp vụ:** nếu hai bản ghi cùng key là lỗi, phát hiện **trước khi** đưa vào map hoặc trong khi gọi `putIfAbsent`. Sau khi một `Map` đã được xây dựng, map tự nó không thể chứa hai entry có cùng key.
5. **Chốt snapshot:** gọi `Map.copyOf(builder)` khi builder ổn định và không bị sửa đồng thời.
6. **Công bố theo hợp đồng:** getter/API trả kiểu `Map<K,V>`, tài liệu hóa rằng kết quả không cho sửa; tránh trả reference builder mutable.
7. **Khi cần phiên bản mới:** tạo builder mới hoặc sao chép từ snapshot cũ, sửa trên builder riêng, rồi công bố **một snapshot mới**.

Với bảng tra cứu bất biến được viết hoàn toàn trong code, `Map.of` thường ngắn gọn hơn. `Map.copyOf` phát huy lợi thế khi nguồn map được tính toán, được nạp hoặc đang mutable.

## 5. Thiết kế bảng tra cứu chỉ đọc

### 5.1. Bảng nhỏ được khai báo trực tiếp

Nếu keys/values đã biết ngay lúc viết code:

```java
static final Map<String, Integer> HTTP_CODES = Map.of(
        "OK", 200,
        "NOT_FOUND", 404,
        "CONFLICT", 409);
```

Đây là **khai báo field trong một class**; cần `import java.util.Map;` nếu dùng đơn độc. `Map.of` không cho sửa và thích hợp khi số cặp nhỏ. Với nhiều cặp, có thể dùng `Map.ofEntries(Map.entry(...), ...)` hoặc tạo builder rồi gọi `Map.copyOf`.

`Map.of` và `Map.ofEntries` từ chối key trùng khi xây dựng bằng `IllegalArgumentException`; không được âm thầm lấy “giá trị cuối”. Chúng cũng không chấp nhận null key/value.

### 5.2. Bảng được tạo từ danh sách hoặc dữ liệu bên ngoài

Giả sử một ứng dụng nạp các cặp mã → giá trị từ dữ liệu đã xác thực. Một chiến lược:

```java
// Ví dụ trong một phương thức, entries là List<Entry> của domain.
var builder = new java.util.HashMap<String, Integer>();

for (var entry : entries) {
    var key = entry.code();
    var number = entry.value();

    java.util.Objects.requireNonNull(key);
    if (number <= 0) {
        throw new IllegalArgumentException("Value must be positive");
    }
    if (builder.putIfAbsent(key, number) != null) {
        throw new IllegalArgumentException("Duplicate key: " + key);
    }
}
var published = java.util.Map.copyOf(builder);
```

Đoạn này **minh họa** và giả định `Entry` là một record/class nghiệp vụ có `code()` và `value()`; không phải chương trình runnable độc lập. `number` là kiểu số nguyên primitive trong ví dụ; `putIfAbsent` phát hiện trùng khi các value đã đưa vào map không null.

Nếu có yêu cầu “bản ghi sau ghi đè bản trước”, dùng `put` có chủ đích và ghi rõ chính sách. Nếu không, phát hiện duplicate giúp tránh cấu hình âm thầm bị thay. `Map.copyOf` thực hiện **snapshot từ map cuối cùng**, không quyết định chính sách xử lý bản ghi trùng khi đang build.

### 5.3. Tra cứu khi khóa không tồn tại

```java
var codes = Map.of("OK", 200, "NOT_FOUND", 404);
var known = codes.get("OK");                   // 200
var absent = codes.get("MISSING");             // null
var fallback = codes.getOrDefault("MISSING", -1); // -1
```

`get` trả `null` khi không có ánh xạ (trên map của ví dụ, value không thể là null). Hãy chọn giữa:
- **Giá trị mặc định** bằng `getOrDefault` nếu domain có fallback rõ.
- **Báo lỗi** khi khóa phải tồn tại: dùng `containsKey` hoặc kiểm tra kết quả `get` và ném một exception phù hợp.
- **Trả `Optional<V>`** ở tầng API nếu tình trạng thiếu là bình thường. Không tự giả định mọi lookup đều có giá trị.

Không nên coi fallback `-1` là quy tắc chung. Nó chỉ là giá trị minh họa để output ổn định; trong hệ thống thật cần đặt theo hợp đồng.

## 6. Thiết kế ảnh chụp cấu hình

Một bản cấu hình có thể được nạp từ file, biến môi trường hoặc dịch vụ. Trong suốt một yêu cầu xử lý, ta thường muốn các tham số như `timeoutMs` và `retries` được đọc **từ cùng một phiên bản**.

```java
var builder = new java.util.HashMap<String, Integer>();
builder.put("timeoutMs", 500);
builder.put("retries", 2);

var configV1 = java.util.Map.copyOf(builder);
builder.put("timeoutMs", 800);
var configV2 = java.util.Map.copyOf(builder);

System.out.println(configV1.get("timeoutMs")); // 500
System.out.println(configV2.get("timeoutMs")); // 800
```

`configV1` và `configV2` là hai bản trạng thái khác nhau về **ánh xạ key/value**. Sửa builder không “nâng cấp” bản cũ. Mỗi reader có thể giữ một tham chiếu snapshot trong suốt quá trình tính toán.

### 6.1. Vì sao không trả `Collections.unmodifiableMap(builder)`?

`Collections.unmodifiableMap(builder)` tạo **view**. Nếu một thành phần khác giữ `builder` và gọi `put("timeoutMs", 800)` thì các reader của view thấy giá trị mới. Điều này thích hợp **chỉ khi** hợp đồng thực sự muốn view sống.

Ngược lại, `Map.copyOf(builder)` không phản ánh thao tác thêm/xóa/thay entry sau khi copy. Đối với cấu hình phiên bản, snapshot thường dễ suy luận hơn vì một request không bị đổi tham số giữa chừng chỉ do người khác sửa builder.

### 6.2. Cấu hình không đồng nghĩa mọi đối tượng đều bất biến

Nếu map chứa `Map<String, List<String>>` và một value là `ArrayList` mutable, `Map.copyOf` **không đóng băng danh sách bên trong**. Muốn công bố trạng thái sâu hơn:

```java
// Trong một phương thức; source có kiểu Map<String,List<String>>.
var stable = new java.util.HashMap<String, java.util.List<String>>();
for (var entry : source.entrySet()) {
    stable.put(entry.getKey(), java.util.List.copyOf(entry.getValue()));
}
var published = java.util.Map.copyOf(stable);
```

Việc copy danh sách con giúp chúng không cho sửa **cấu trúc list**. Nếu phần tử list tiếp tục là đối tượng mutable thì còn cần sao chép/đóng băng chúng theo hợp đồng. Với các value bất biến như `String`, `Integer` hoặc value objects được thiết kế bất biến, việc giữ snapshot dễ an toàn hơn.

### 6.3. Kiểm soát phiên bản và khả năng truy vết

Một ứng dụng lớn có thể gói snapshot với số phiên bản và thời điểm công bố trong một đối tượng bất biến riêng, thay vì tự thêm metadata vào cùng Map cấu hình. Ý nghĩa:

- Biết request đang dùng bản `v1` hay `v2` khi debug.
- So sánh snapshot mới/cũ trước khi publish.
- Có thể quay về snapshot cũ bằng **thay tham chiếu** nếu đó là chính sách được phép.
- Không biến `Map.copyOf` thành một cơ chế lưu lịch sử hoặc transaction tự động: các khả năng đó phải do ứng dụng thiết kế.

## 7. Cập nhật cấu hình an toàn cho nhiều reader bằng `AtomicReference`

Một hướng thiết kế hữu ích là giữ tham chiếu đến **Map không cho sửa**, rồi thay tham chiếu đó mỗi khi có phiên bản mới. `AtomicReference<Map<String,Integer>>` là một cách làm trên JDK hiện đại.

```java
private final AtomicReference<Map<String, Integer>> current =
        new AtomicReference<>(Map.of("timeoutMs", 500, "retries", 2));

Map<String, Integer> snapshot() {
    return current.get();
}

void replace(Map<String, Integer> supplied) {
    current.set(Map.copyOf(supplied));
}
```

Đây là **các thành viên của một class**, không phải chương trình độc lập. Khi `current.set(snapshot)`, mọi thao tác đọc `current.get()` lấy một **tham chiếu map hoàn chỉnh** thay vì quan sát từng `put` rời rạc trên cùng map mutable.

**Một quy tắc quan trọng cho người đọc:** đọc tham chiếu một lần để dùng nhất quán trong một tác vụ.

```java
var config = store.snapshot();
var timeoutMs = config.get("timeoutMs");
var retries = config.get("retries");
```

Nếu gọi `store.snapshot()` riêng cho từng key, giữa hai lần đọc có thể xảy ra một lần cập nhật, dẫn đến các giá trị lấy từ **hai phiên bản khác nhau**. Cầm một local snapshot giúp giữ nhất quán ở cấp **cùng phiên bản entry** (giả định keys/values là đối tượng bất biến phù hợp).

### 7.1. Cập nhật incremental kiểu copy-on-write

Với bản đang publish là unmodifiable, không gọi `current.get().put(...)`. Thay vào đó:

```java
void update(String key, int value) {
    current.updateAndGet(previous -> {
        var next = new java.util.HashMap<>(previous);
        next.put(key, value);
        return java.util.Map.copyOf(next);
    });
}
```

`AtomicReference.updateAndGet` sử dụng cơ chế cập nhật nguyên tử, có thể **gọi lại hàm cập nhật** nếu cạnh tranh giữa các thread. Bởi vậy lambda nên không có tác dụng phụ ngoài việc xây dựng và trả map mới; không thực hiện gửi email, ghi log nghiệp vụ đúng-một-lần hay ghi cơ sở dữ liệu trong lambda đó.

- **Reader** tiếp tục nhìn thấy snapshot cũ hoặc snapshot mới, không thấy map đang bị sửa từng phần bởi bước update.
- **Writer** có thể trả kết quả map mới; cập nhật không làm thay đổi nội dung snapshot cũ.
- **Công bố** qua AtomicReference tạo các bảo đảm visibility phù hợp cho chính tham chiếu và trạng thái được xây dựng trước khi công bố. Điều này không tự biến **đối tượng value mutable** thành thread-safe.
- **Hiệu năng:** mỗi lần update copy toàn map; phù hợp khi read nhiều, update ít và kích thước map vừa phải. Với dữ liệu lớn/cập nhật thường xuyên, cần cân nhắc cấu trúc dữ liệu và mô hình concurrency khác.

### 7.2. Không copy trực tiếp một map đang bị sửa đồng thời mà coi là transaction

Nếu một writer khác còn đang `put` vào `HashMap` nguồn **trong khi** `Map.copyOf(source)` chạy, API không hứa cho bạn một snapshot nhất quán theo thời điểm duy nhất. Không có cơ chế transaction trong `Map.copyOf`; có thể gặp kết quả không như dự kiến hoặc vấn đề thread safety.

Cách thiết kế rõ ràng là tạo builder **thuộc riêng thread đang xây dựng**, validate xong rồi snapshot, hoặc dùng đồng bộ phù hợp trước khi copy nguồn chia sẻ. `ConcurrentHashMap` có các bảo đảm truy cập đồng thời riêng, nhưng việc copy từ một map liên tục thay đổi không đương nhiên là phép snapshot nguyên tử cho toàn bộ entries.

Với cấu hình cần cập nhật ở tần suất cao, đọc/ghi theo sự kiện hoặc yêu cầu nhất quán giữa nhiều trường, nên thiết kế rõ cấu trúc trạng thái/version và cách publish, thay vì chỉ thêm `copyOf`.

## 8. Chương trình Java hoàn chỉnh: lookup, snapshot và cập nhật phiên bản

### 8.1. Chuẩn bị

Dùng một JDK hiện được nhà cung cấp hỗ trợ và cập nhật bản vá (ví dụ một bản phân phối JDK 21 hoặc 25 LTS còn trong vòng hỗ trợ). `Map.copyOf` là API Java 10 và vẫn tồn tại trên JDK mới; không cần dùng runtime Java 10 đã cũ.

```bash
java -version
javac -version
```

Tạo tệp **`ConfigSnapshotLab.java`** đúng tên class public sau:

```java
import java.util.Collections;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.concurrent.atomic.AtomicReference;

public class ConfigSnapshotLab {
    static final class ConfigStore {
        private final AtomicReference<Map<String, Integer>> current =
                new AtomicReference<>(
                        Map.of("timeoutMs", 500, "retries", 2));

        Map<String, Integer> snapshot() {
            return current.get();
        }

        // Caller truyền một map ổn định trong lúc thực hiện copy.
        void replace(Map<String, Integer> supplied) {
            current.set(Map.copyOf(supplied));
        }

        void update(String key, int value) {
            current.updateAndGet(previous -> {
                var draft = new HashMap<>(previous);
                draft.put(key, value);
                return Map.copyOf(draft);
            });
        }
    }

    public static void main(String[] args) {
        // Mutable builder -> unmodifiable snapshot.
        var draft = new LinkedHashMap<String, Integer>();
        draft.put("timeoutMs", 500);
        draft.put("retries", 2);
        var snapshot = Map.copyOf(draft);

        draft.put("retries", 9);
        System.out.println("source retries: " + draft.get("retries"));
        System.out.println("snapshot retries: " + snapshot.get("retries"));
        System.out.println("snapshot size: " + snapshot.size());

        try {
            snapshot.put("retries", 7);
        } catch (UnsupportedOperationException ex) {
            System.out.println("snapshot write: blocked");
        }

        // Unmodifiable view vẫn nhìn thấy thay đổi của backing map.
        var view = Collections.unmodifiableMap(draft);
        System.out.println("view sees source: " + view.get("retries"));

        // Bảng tra cứu hằng số nhỏ, không cần builder.
        var lookup = Map.of("OK", 200, "NOT_FOUND", 404);
        System.out.println("lookup OK: " + lookup.get("OK"));
        System.out.println("lookup absent: "
                + lookup.getOrDefault("UNKNOWN", -1));

        // Công bố toàn bộ map phiên bản mới qua một tham chiếu.
        var store = new ConfigStore();
        var oldConfig = store.snapshot();
        System.out.println("store initial timeout: "
                + oldConfig.get("timeoutMs"));

        var incoming = new HashMap<String, Integer>();
        incoming.put("timeoutMs", 800);
        incoming.put("retries", 3);

        store.replace(incoming);
        incoming.put("timeoutMs", 900);
        System.out.println("source after replace: "
                + incoming.get("timeoutMs"));
        System.out.println("stored after source edit: "
                + store.snapshot().get("timeoutMs"));
        System.out.println("old snapshot timeout: "
                + oldConfig.get("timeoutMs"));

        var priorUpdate = store.snapshot();
        store.update("retries", 4);
        System.out.println("updated retries: "
                + store.snapshot().get("retries"));
        System.out.println("prior snapshot retries: "
                + priorUpdate.get("retries"));

        // Map.copyOf từ chối null trong key hoặc value.
        var nullable = new HashMap<String, Integer>();
        nullable.put("bad", null);
        try {
            Map.copyOf(nullable);
        } catch (NullPointerException ex) {
            System.out.println("copy null value: NullPointerException");
        }

        // Map.of kiểm tra duplicate keys trong tập cặp trực tiếp.
        try {
            Map.of("A", 1, "A", 2);
        } catch (IllegalArgumentException ex) {
            System.out.println(
                    "Map.of duplicate key: IllegalArgumentException");
        }

        // Map.copyOf chỉ snapshot các entry, không deep-copy value.
        var mutable = new HashMap<String, StringBuilder>();
        mutable.put("banner", new StringBuilder("v1"));
        var shallow = Map.copyOf(mutable);
        mutable.get("banner").append("-v2");
        System.out.println("mutable value: " + shallow.get("banner"));
    }
}
```

Biên dịch và chạy trong thư mục chứa tệp:

```bash
javac ConfigSnapshotLab.java
java ConfigSnapshotLab
```

### 8.2. Output chính xác

```text
source retries: 9
snapshot retries: 2
snapshot size: 2
snapshot write: blocked
view sees source: 9
lookup OK: 200
lookup absent: -1
store initial timeout: 500
source after replace: 900
stored after source edit: 800
old snapshot timeout: 500
updated retries: 4
prior snapshot retries: 3
copy null value: NullPointerException
Map.of duplicate key: IllegalArgumentException
mutable value: v1-v2
```

Chương trình không in nguyên `Map.toString()` nên không phụ thuộc thứ tự duyệt của `Map.of` hay `Map.copyOf`. Mọi dòng output đều dựa vào một key xác định, `size()` hoặc một ngoại lệ có chủ đích được bắt theo loại.

### 8.3. Giải thích output

1. `draft` được sửa thành `retries=9` sau khi tạo snapshot, nhưng `snapshot.get("retries")` vẫn là `2`. Kết quả có đúng hai entry vì builder lúc copy có hai key.
2. `snapshot.put("retries",7)` ném `UnsupportedOperationException`; việc chặn sửa thuộc hợp đồng map kết quả.
3. `view` là wrapper của `draft` đang mutable, nên nhìn thấy `retries=9`. Wrapper này không tương đương snapshot.
4. Bảng `lookup` khai báo bằng `Map.of` trả `200` cho `OK`; key thiếu có fallback `-1`. Không có vấn đề null trong các cặp hằng số.
5. `oldConfig` giữ snapshot ban đầu `timeoutMs=500`. Sau `replace(incoming)`, store giữ bản mới với `800`. Việc caller sửa `incoming` thành `900` sau khi replace không làm đổi store.
6. `store.update("retries",4)` tạo một map mới từ bản trước đó, thay đúng key rồi publish. `priorUpdate` vẫn là snapshot cũ có `retries=3`; phiên bản mới có `4`.
7. `Map.copyOf(nullable)` phát hiện value null và ném `NullPointerException`. `Map.of("A",1,"A",2)` nhận key trùng và ném `IllegalArgumentException`.
8. `StringBuilder` là value mutable: `Map.copyOf` không sao chép sâu. Khi object được nối thêm `-v2`, `shallow.get("banner")` thể hiện `v1-v2`.

**Lưu ý về phạm vi:** lab này minh họa cấu trúc đã được xây dựng hợp lệ; nó không phải hệ thống cấu hình production hoàn chỉnh với parser, authentication, persistence hay audit. Cần thêm validation domain, báo lỗi và chiến lược reload phù hợp dự án thực tế.

## 9. Những giới hạn cần biết trước khi áp dụng

### 9.1. Null key, null value và null map

```java
var m = new java.util.HashMap<String, Integer>();
m.put(null, 1);
java.util.Map.copyOf(m); // NullPointerException

m.clear();
m.put("A", null);
java.util.Map.copyOf(m); // NullPointerException
```

Ngay cả khi `HashMap` chấp nhận null, `Map.copyOf` vẫn từ chối. Nếu null đang biểu thị “chưa cấu hình”, hãy quyết định rõ: bỏ entry, dùng giá trị mặc định hay từ chối đầu vào. Đừng cố chuyển null thành một chuỗi đặc biệt mà không có hợp đồng.

### 9.2. Duplicate key phải xử lý trước `Map.copyOf`

`Map` **không cho tồn tại đồng thời hai entry có key bằng nhau**. Nếu bạn build:

```java
var builder = new java.util.HashMap<String, Integer>();
builder.put("A", 1);
builder.put("A", 2);
var snapshot = java.util.Map.copyOf(builder);
System.out.println(snapshot.get("A")); // 2
```

`Map.copyOf` **không thể** phát hiện dữ liệu `A=1` từng xuất hiện, vì builder đã ghi đè thành `A=2` trước khi copy. Nếu duplicate là lỗi, kiểm tra trong giai đoạn parse/build.

Khi dữ liệu đi qua Stream, `Collectors.toUnmodifiableMap(keyMapper,valueMapper)` ném `IllegalStateException` khi có duplicate keys. Bản overload có **merge function** cho phép xử lý xung đột theo quy tắc được chọn. Đây là chính sách của collector, **không phải quy tắc mà `Map.copyOf` tự áp dụng**.

### 9.3. Thứ tự duyệt không được bảo đảm

`Map.copyOf(new LinkedHashMap<>(...))` không cam kết giữ thứ tự chèn của nguồn; do đó không so sánh chuỗi `Map.toString()` với một thứ tự cố định trong unit test.

Nếu API phải trả về dữ liệu **có thứ tự**, hãy chọn một hợp đồng khác phù hợp: ví dụ `List<Entry<K,V>>` đã sắp theo comparator rõ, hoặc một snapshot `TreeMap` bọc `Collections.unmodifiableSortedMap` và giữ bản sao backing ở phạm vi private. Cách sau là **view trên bản sao do ứng dụng sở hữu**, không phải `Map.copyOf`; cần giữ kín bản sao ấy để caller không thể sửa từ lối khác.

### 9.4. Key mutable gây rủi ro cho lookup

Một key có `equals/hashCode` phụ thuộc trường mutable không phù hợp cho cấu trúc hash-based nếu trường đó bị sửa sau khi đưa vào map. `Map.copyOf` không chữa được vấn đề này. Nên ưu tiên `String`, `UUID` hoặc domain value object bất biến cho key. Khi cần key tùy biến, định nghĩa equality ổn định trong suốt vòng đời key.

### 9.5. Giá trị mutable, thread safety và safe publication

`Map.copyOf` chỉ làm cấu trúc map không cho sửa qua API. Nếu value là `ArrayList`, bean có setter hoặc mảng, người còn giữ tham chiếu vẫn có thể thay nội dung bên trong. Nếu ứng dụng yêu cầu trạng thái không thay đổi, phải xử lý cả dữ liệu con.

Snapshot cùng `AtomicReference` giúp một reader lấy một map version hoàn chỉnh, nhưng không chứng minh toàn hệ thống là thread-safe. Phải bảo đảm builder không bị sửa đồng thời trong lúc copy, key/value phù hợp, các phụ thuộc liên quan được công bố an toàn và update function không có side effect ngoài ý muốn.

### 9.6. Chi phí copy và số lượng phiên bản

Mỗi lần tạo snapshot từ map mutable có thể cần duyệt/copy các entry, nên mô hình tạo mới toàn bộ map hợp lý hơn khi **đọc nhiều, cập nhật ít**. Không tạo snapshot sau mỗi `put` trong một vòng lặp dài nếu không cần phiên bản riêng. Thay vào đó, build một lần rồi publish. Nếu phải cập nhật hàng nghìn lần mỗi giây trên map lớn, hãy đo bằng benchmark và cân nhắc mô hình dữ liệu khác thay vì giả định `copyOf` luôn rẻ.

## 10. Bản thiết kế áp dụng: từ nguồn cấu hình đến API getter

Một API đơn giản nhưng rõ ràng có thể áp dụng bốn nguyên tắc:

- **Validate tại đầu vào:** kiểm tra key bắt buộc, kiểu value, miền giá trị, null và duplicate. Thông báo lỗi đủ ngữ cảnh để người vận hành sửa file cấu hình.
- **Không rò rỉ builder:** dữ liệu mutable dùng để xây dựng chỉ nằm trong phương thức/hệ thống sở hữu. Không trả thẳng nó cho reader.
- **Công bố kiểu chỉ đọc:** return type vẫn là `Map<String,Integer>` nhưng hợp đồng API phải nói kết quả **unmodifiable** và là snapshot; không khiến caller phải đoán dựa vào `var` hay concrete class.
- **Cập nhật theo phiên bản:** loader xây một snapshot mới, validate đầy đủ, rồi thực hiện một lần swap reference. Nếu parse thất bại, giữ nguyên snapshot đang hoạt động thay vì công bố một map cấu hình chỉ có một phần giá trị.

Ví dụ pseudo-flow có thể dịch sang kiến trúc thật:

```text
parse(resource)
    -> validate all keys and values
    -> build private HashMap
    -> Map.copyOf(validMap)
    -> AtomicReference.set(newSnapshot)
    -> reader: var currentVersion = snapshot()
    -> perform all lookups on currentVersion
```

Cách này không quy định nguồn config là JSON, YAML hay database. `Map.copyOf` xử lý **đối tượng Map đã được tạo**, không tự đọc file, parse text hoặc lưu kết quả vào bộ nhớ bền vững.

### Khi nào chỉ nên dùng `Map.of`?

Khi dữ liệu là hằng số nhỏ đã biết trong source code, `Map.of` diễn đạt ý định trực tiếp. Đừng tạo builder mutable và gọi `copyOf` chỉ để lưu hai cặp hằng số trong source code khi không có nhu cầu tính toán hoặc lấy nguồn ngoài.

### Khi nào cần map mutable?

Khi có luồng cập nhật thật sự, ví dụ cache ghi/xóa liên tục hoặc đang thu thập bản ghi, một map mutable phù hợp với ownership rõ ràng có thể hiệu quả hơn. Không áp dụng `Map.copyOf` như công cụ thay thế đồng bộ cho cache. Nếu yêu cầu cập nhật đồng thời theo từng key, cân nhắc `ConcurrentHashMap` và contract của nó, nhưng nhớ rằng đó là **mô hình khác** với bản cấu hình snapshot immutable.

## 11. Bài tập tự luyện có đáp án

### Bài 1 — Snapshot hay live view?

Cho:

```java
var input = new java.util.HashMap<String, Integer>();
input.put("retry", 1);
var copy = java.util.Map.copyOf(input);
var view = java.util.Collections.unmodifiableMap(input);
input.put("retry", 5);
```

**Hỏi:** `copy.get("retry")` và `view.get("retry")` bằng bao nhiêu?

**Đáp án:** `1` và `5`. `Map.copyOf` tạo snapshot entry; `unmodifiableMap` tạo view phản ánh nguồn.

### Bài 2 — Bảng tra cứu nhỏ

Một ứng dụng có bảng hằng số `"OK"→200` và `"ERROR"→500`, không cần sửa hoặc nạp ngoài. Chọn API?

**Đáp án:** `Map.of("OK",200,"ERROR",500)`. Chỉ cần `Map.copyOf` khi đã có map nguồn/đang xây dựng dữ liệu từ nhiều bước.

### Bài 3 — Cấu hình bị sửa sau publish

```java
var builder = new java.util.HashMap<String, Integer>();
builder.put("timeoutMs", 1000);
var config = java.util.Map.copyOf(builder);
builder.put("timeoutMs", 2000);
```

**Đáp án:** `config.get("timeoutMs")==1000`. Nếu muốn bản `2000`, phải tạo và công bố một snapshot mới.

### Bài 4 — Có thể “bắt duplicate” bằng `Map.copyOf` không?

Dữ liệu đầu vào có hai bản ghi cùng key `"region"`. Bạn dùng `builder.put(...)` lần lượt, rồi `Map.copyOf(builder)`. Kết quả có ném lỗi duplicate không?

**Đáp án:** Không phải vì duplicate trước đó. Map builder đã giữ một giá trị duy nhất cho key `region`. Nếu duplicate là lỗi, kiểm tra khi đọc từng bản ghi (`putIfAbsent` hoặc `containsKey` trước khi `put`), hoặc dùng collector có chính sách trùng phù hợp.

### Bài 5 — Chọn key/value

Bạn cần một bảng `Map<String, List<String>>` nhưng list values còn mutable. Chỉ gọi `Map.copyOf` đã tạo deep immutable snapshot chưa?

**Đáp án:** Chưa. Map không cho sửa entry, nhưng list value vẫn có thể thay đổi. Tạo bản `List.copyOf` cho từng list trước khi đưa vào map kết quả; nếu list element mutable thì còn phải xử lý chúng theo hợp đồng.

### Bài 6 — Concurrency: đọc hai key

Một request gọi `store.snapshot().get("timeoutMs")` rồi sau đó gọi riêng `store.snapshot().get("retries")`. Điều gì có thể xảy ra nếu cấu hình reload giữa hai lần đọc?

**Đáp án:** Hai giá trị có thể thuộc hai phiên bản. Hãy đọc một lần `var config = store.snapshot();` và tra cả hai key trên `config`. Các key/value phải có tính bất biến phù hợp nếu cần giữ ngữ nghĩa snapshot.

### Bài 7 — Update function có side effect

Hàm `AtomicReference.updateAndGet` nhận lambda và bên trong có lệnh trừ tiền hoặc gửi thông báo. Có an toàn để bảo đảm hành động thực hiện đúng một lần không?

**Đáp án:** Không. Khi cạnh tranh, hàm cập nhật có thể được đánh giá nhiều lần. Hãy giữ lambda thuần, tạo map mới và trả về; nghiệp vụ cần đúng-một-lần phải thiết kế ở một tầng điều phối khác.

### Bài 8 — Null và thứ tự

```java
var source = new java.util.LinkedHashMap<String, Integer>();
source.put("B", 2);
source.put("A", 1);
var snapshot = java.util.Map.copyOf(source);
```

Có thể assert `snapshot.toString().equals("{B=2, A=1}")` không? Và nếu thêm `source.put("C", null)` trước `copyOf` thì sao?

**Đáp án:** Không nên assert thứ tự hiển thị; `Map.copyOf` không cam kết iteration order. Value null làm `Map.copyOf` ném `NullPointerException`. Nên test `size` và `get(key)` để xác nhận nội dung.

### Bài 9 — Phân biệt cache và config

Một cache có rất nhiều lần `put/remove` mỗi giây, trong khi cấu hình feature flags chỉ thay vài lần mỗi ngày và được nhiều thread đọc. Có nên dùng cùng một chiến lược `copyOf` sau mỗi update cho cả hai?

**Đáp án:** Không nhất thiết. Với cấu hình ít thay, snapshot + atomic reference có thể rất phù hợp. Với cache cần cập nhật thường xuyên, phải lựa chọn cấu trúc mutable/concurrent và kiểm thử hiệu năng, consistency theo yêu cầu. Không dùng `Map.copyOf` như câu trả lời duy nhất cho mọi bài toán map.

## 12. Checklist review trong dự án

- [ ] Biết khi nào chọn `Map.of`, `Map.ofEntries`, `Map.copyOf` và `HashMap` mutable.
- [ ] Phân biệt snapshot cấu trúc với `Collections.unmodifiableMap` live view.
- [ ] Không trông chờ `Map.copyOf` chấp nhận null key/value hoặc trả thứ tự chèn.
- [ ] Không cho rằng `Map.copyOf` có thể phát hiện duplicate đã bị `put` ghi đè trong builder.
- [ ] Không so sánh object identity của map trả về để xác nhận tính unmodifiable.
- [ ] Chọn `Map<String,ImmutableValue>` hoặc defensive copy nếu cần trạng thái bất biến sâu.
- [ ] Kiểm tra key/value hợp lệ theo domain trước khi publish.
- [ ] Không chia sẻ mutable builder trong lúc `Map.copyOf` đang chạy.
- [ ] Nếu có nhiều reader và reload, đọc một snapshot tham chiếu một lần trong suốt request.
- [ ] Hiểu việc dùng `AtomicReference.updateAndGet` có thể gọi lại lambda; không đặt side effect trong lambda.
- [ ] Cân nhắc chi phí copy nếu update nhiều hoặc map lớn.
- [ ] Chạy `ConfigSnapshotLab.java` và đối chiếu chính xác **16 dòng stdout**.

## 13. Ghi nhớ

**Map mutable phục vụ xây dựng và cập nhật; `Map.copyOf` phục vụ công bố trạng thái đã chốt để nhiều nơi tra cứu mà không thể thay đổi entry qua map kết quả.** Với bảng hằng số nhỏ, `Map.of` đủ dùng. Với cấu hình phải reload, xây snapshot mới rồi thay tham chiếu công bố, giữ snapshot cũ cho các tác vụ còn đang chạy. Các bảo đảm này chỉ đúng ở mức cấu trúc map và theo hợp đồng API; giá trị mutable, khóa mutable, nguồn bị sửa đồng thời và chi phí copy vẫn cần được thiết kế riêng.

Đây là kiến thức Java 10 **còn áp dụng trong Java hiện đại**; không phụ thuộc vào sử dụng thư viện hay JDK legacy.

## Tài liệu chính thức

- [Oracle Java SE 25 — Map API: `copyOf`, `of`, `ofEntries`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Map.html): unmodifiable map, null, duplicate, thứ tự và hợp đồng copy.
- [Oracle Java SE 25 — Collections.unmodifiableMap](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Collections.html#unmodifiableMap(java.util.Map)): phân biệt read-only **view** với snapshot.
- [Oracle Java SE 25 — Collectors.toUnmodifiableMap](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Collectors.html): xây map từ Stream và cách xử lý duplicate keys.
- [Oracle Java SE 25 — AtomicReference](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/atomic/AtomicReference.html): công bố tham chiếu, `get`, `set`, `updateAndGet`.
- [Oracle — Creating Unmodifiable Lists, Sets, and Maps](https://docs.oracle.com/en/java/javase/25/core/creating-immutable-lists-sets-and-maps.html): hướng dẫn thực hành với `copyOf` và các factory không cho sửa.