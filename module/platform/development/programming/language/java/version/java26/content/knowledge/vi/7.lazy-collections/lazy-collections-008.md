# Kiểm thử thứ tự truy cập, ngoại lệ và truy cập đồng thời

## Mục tiêu

Sau bài học này, bạn có thể:

- Kiểm tra một phần tử của lazy list chỉ được tính khi index đó được truy cập.
- Kiểm tra một giá trị của lazy map chỉ được tính khi key tương ứng được truy cập.
- Phân biệt thứ tự gọi computing function với thứ tự duyệt của Map.
- Kiểm thử hành vi khi computing function ném exception, trả về null hoặc gọi đệ quy.
- Kiểm tra nhiều luồng truy cập cùng index/key và xác nhận một lần khởi tạo thành công.
- Nhận biết các thao tác như `toString()`, `hashCode()`, `equals()`, `values()` và `entrySet()` có thể kích hoạt thêm phần tử.
- Bật preview đúng cách và tránh đưa API chưa ổn định vào thư viện hoặc production nếu không chấp nhận rủi ro.

## 1. Phạm vi API cần kiểm thử

JDK 26 bổ sung hai factory method lazy cho Collections Framework:

~~~java
List.ofLazy(int size, IntFunction<? extends E> computingFunction)

Map.ofLazy(
    Set<? extends K> keys,
    Function<? super K, ? extends V> computingFunction
)
~~~

Cả hai là **preview API** trong Java 26, thuộc `java.base`, không cần thêm module incubator. Chúng tạo collection không sửa đổi được:

- Lazy list có kích thước cố định. Mỗi index có một giá trị được tính riêng khi lần đầu truy cập index đó.
- Lazy map nhận trước tập key. Mỗi value được tính riêng khi lần đầu truy cập key tương ứng.
- Giá trị đã khởi tạo thành công được giữ lại; truy cập lại cùng index/key trả về giá trị đó.
- Không cho phép phần tử hoặc value null. Nếu computing function trả null, thao tác truy cập ném `NullPointerException`.
- Các phương thức thay đổi collection ném `UnsupportedOperationException`.

Đây là lazy theo từng phần tử hoặc từng key, không phải lazy cho toàn bộ collection. Tạo collection chưa làm mọi giá trị được tính. Kích thước list và tập key của map đã được xác định ngay lúc tạo.

## 2. Kiểm thử thứ tự truy cập của List.ofLazy

Với list, `IntFunction` nhận index đang được truy cập. Có thể ghi nhận index trong một danh sách phụ để xác nhận thứ tự tính:

~~~java
List<Integer> computedIndexes = new ArrayList<>();

List<String> values = List.ofLazy(5, index -> {
    computedIndexes.add(index);
    return "value-" + index;
});

assertEquals(5, values.size());
assertTrue(computedIndexes.isEmpty());

assertEquals("value-3", values.get(3));
assertEquals("value-1", values.get(1));
assertEquals("value-3", values.get(3));

assertEquals(List.of(3, 1), computedIndexes);
~~~

Kết quả cho thấy:

1. Tạo list và gọi `size()` không tính phần tử.
2. `get(3)` chỉ tính phần tử tại index 3.
3. `get(1)` tính phần tử tại index 1.
4. Gọi lại `get(3)` dùng kết quả đã lưu, không gọi function lần nữa.

Mỗi index có vòng đời khởi tạo riêng. Việc index 3 đã được tính không làm index 0, 1, 2 hoặc 4 tự động được tính.

### Các trường hợp biên của index

- Index hợp lệ nằm trong khoảng từ 0 đến `size() - 1`.
- Index âm hoặc bằng/lớn hơn size làm `get(index)` ném `IndexOutOfBoundsException`.
- Kích thước âm khi gọi `List.ofLazy` làm factory ném `IllegalArgumentException`.
- List rỗng có size bằng 0 và không có index hợp lệ để truy cập.

Không viết test dựa vào việc gọi index sai có làm computing function chạy hay không; index ngoài miền không đại diện cho một phần tử hợp lệ.

## 3. Kiểm thử thứ tự truy cập của Map.ofLazy

Lazy map nhận một `Set` các key đã biết trước. Function được gọi với key đang cần value:

~~~java
List<String> computedKeys = new ArrayList<>();
Set<String> keys = Set.of("alpha", "beta", "gamma");

Map<String, String> values = Map.ofLazy(keys, key -> {
    computedKeys.add(key);
    return key.toUpperCase(Locale.ROOT);
});

assertEquals(3, values.size());
assertTrue(computedKeys.isEmpty());

assertEquals("BETA", values.get("beta"));
assertEquals("ALPHA", values.get("alpha"));
assertEquals("BETA", values.get("beta"));

assertEquals(List.of("beta", "alpha"), computedKeys);
~~~

Map chỉ tính value cho key được truy cập. Gọi lại `get("beta")` không gọi function lần nữa sau khi value của key đó đã khởi tạo thành công.

Có thể kiểm tra key đã biết mà chưa đọc value:

~~~java
assertTrue(values.containsKey("gamma"));
assertFalse(computedKeys.contains("gamma"));
~~~

Tập key được xác định khi tạo map; việc kiểm tra membership không đòi hỏi phải tạo value cho key. Nếu gọi `get()` với key không thuộc tập ban đầu, map không có mapping cho key đó và trả về `null`; computing function không được gọi để tự thêm key mới.

**Không kiểm tra thứ tự duyệt của Map bằng thứ tự Set đầu vào.** API của `Map.ofLazy` không cam kết encounter order của các mapping. Muốn kiểm tra thứ tự tính, gọi `get(key)` theo một chuỗi key xác định và ghi lại lời gọi function như ví dụ trên.

## 4. Dùng counter để xác nhận mỗi phần tử chỉ tính một lần thành công

Counter giúp phát hiện việc function bị gọi lại ngoài dự kiến:

~~~java
AtomicInteger[] calls = {
    new AtomicInteger(),
    new AtomicInteger(),
    new AtomicInteger()
};

List<String> items = List.ofLazy(3, index -> {
    calls[index].incrementAndGet();
    return "item-" + index;
});

items.get(2);
items.get(0);
items.get(2);

assertEquals(1, calls[0].get());
assertEquals(0, calls[1].get());
assertEquals(1, calls[2].get());
~~~

Với map, có thể dùng `ConcurrentHashMap` để lưu số lần gọi theo key:

~~~java
ConcurrentHashMap<String, AtomicInteger> calls = new ConcurrentHashMap<>();

Map<String, Integer> scores = Map.ofLazy(
    Set.of("A", "B"),
    key -> {
        calls.computeIfAbsent(key, ignored -> new AtomicInteger())
             .incrementAndGet();
        return key.length();
    }
);

scores.get("A");
scores.get("A");
scores.get("B");

assertEquals(1, calls.get("A").get());
assertEquals(1, calls.get("B").get());
~~~

Trong các ví dụ này, counter chỉ ghi nhận function được gọi. Nó không phải một phần trạng thái của lazy collection. Khi test nhiều luồng, dùng counter thread-safe như `AtomicInteger` hoặc `ConcurrentHashMap`; `ArrayList` không thích hợp để nhiều supplier cùng ghi đồng thời vào một danh sách.

## 5. Kiểm thử khi computing function ném exception

Nếu function ném exception, exception được chuyển lại cho caller đang kích hoạt việc tính. Không có value nào được ghi nhận cho index/key đó. Một lần truy cập sau có thể chạy function lại.

Ví dụ với list:

~~~java
AtomicInteger attempts = new AtomicInteger();

List<String> values = List.ofLazy(1, index -> {
    if (attempts.incrementAndGet() == 1) {
        throw new IllegalStateException("Nguồn dữ liệu tạm thời lỗi");
    }
    return "ready";
});

assertThrows(IllegalStateException.class, () -> values.get(0));

assertEquals("ready", values.get(0));
assertEquals("ready", values.get(0));
assertEquals(2, attempts.get());
~~~

Lần đầu thất bại, nên index 0 chưa được khởi tạo. Lần thứ hai thử lại và thành công. Lần thứ ba lấy giá trị đã lưu.

Điểm cần kiểm thử là **mỗi index/key được khởi tạo thành công tối đa một lần**. Không được hiểu thành function chỉ được gọi một lần trong mọi tình huống. Những lần thất bại có thể làm function chạy lại cho đến khi có một kết quả thành công.

Với lazy map, semantics tương tự nhưng độc lập theo từng key:

~~~java
AtomicInteger attempts = new AtomicInteger();

Map<String, String> values = Map.ofLazy(Set.of("config"), key -> {
    if (attempts.incrementAndGet() == 1) {
        throw new IllegalStateException("Config chưa sẵn sàng");
    }
    return "loaded";
});

assertThrows(IllegalStateException.class, () -> values.get("config"));
assertEquals("loaded", values.get("config"));
assertEquals(2, attempts.get());
~~~

Không nên để function có side effect không thể lặp lại an toàn. Nếu lần đầu ghi dữ liệu nghiệp vụ rồi mới ném exception, lần truy cập sau có thể thực hiện side effect lần nữa. Hãy làm supplier idempotent, tách bước chuẩn bị khỏi bước commit hoặc có cơ chế chống thực hiện trùng.

## 6. Kiểm thử trường hợp function trả null

Lazy list và lazy map không cho phép lưu null. Nếu function trả null, lần truy cập ném `NullPointerException` và giá trị không được ghi nhận. Lần sau có thể thử lại.

~~~java
AtomicInteger attempts = new AtomicInteger();

List<String> values = List.ofLazy(1, index -> {
    if (attempts.incrementAndGet() == 1) {
        return null;
    }
    return "available";
});

assertThrows(NullPointerException.class, () -> values.get(0));
assertEquals("available", values.get(0));
assertEquals(2, attempts.get());
~~~

Nếu nghiệp vụ cần phân biệt “đã tính và không có kết quả” với “chưa tính”, hãy dùng `Optional` làm kiểu phần tử:

~~~java
List<Optional<String>> values = List.ofLazy(
    3,
    index -> index == 1
        ? Optional.empty()
        : Optional.of("value-" + index)
);
~~~

Ở đây collection không chứa null; `Optional.empty()` là một giá trị hợp lệ đã được khởi tạo.

## 7. Kiểm thử truy cập đồng thời cùng index hoặc key

Lazy collection bảo đảm function được gọi thành công tối đa một lần cho mỗi index/key, kể cả khi nhiều luồng cùng truy cập. Khi một phần tử đang được tính, các luồng cạnh tranh truy cập phần tử đó sẽ chờ cho đến khi việc tính hoàn tất hoặc kết thúc bất thường.

Ví dụ JUnit 5 kiểm tra hai luồng cùng lấy một index:

~~~java
import java.util.List;
import java.util.concurrent.Callable;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

@Test
void sameListIndexIsSuccessfullyComputedOnlyOnce() throws Exception {
    AtomicInteger calls = new AtomicInteger();
    CountDownLatch ready = new CountDownLatch(2);
    CountDownLatch start = new CountDownLatch(1);
    CountDownLatch aboutToGet = new CountDownLatch(2);
    CountDownLatch supplierStarted = new CountDownLatch(1);
    CountDownLatch releaseSupplier = new CountDownLatch(1);

    List<String> values = List.ofLazy(1, index -> {
        calls.incrementAndGet();
        supplierStarted.countDown();

        try {
            if (!releaseSupplier.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Test timed out");
            }
            return "shared";
        } catch (InterruptedException error) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException(error);
        }
    });

    ExecutorService pool = Executors.newFixedThreadPool(2);

    try {
        Callable<String> task = () -> {
            ready.countDown();
            start.await();
            aboutToGet.countDown();
            return values.get(0);
        };

        Future<String> first = pool.submit(task);
        Future<String> second = pool.submit(task);

        assertTrue(ready.await(5, TimeUnit.SECONDS));
        start.countDown();

        assertTrue(aboutToGet.await(5, TimeUnit.SECONDS));
        assertTrue(supplierStarted.await(5, TimeUnit.SECONDS));
        releaseSupplier.countDown();

        assertEquals("shared", first.get(5, TimeUnit.SECONDS));
        assertEquals("shared", second.get(5, TimeUnit.SECONDS));
        assertEquals(1, calls.get());
    } finally {
        releaseSupplier.countDown();
        pool.shutdownNow();
    }
}
~~~

Hai task bắt đầu gần nhau và cùng gọi `get(0)`. Supplier được giữ lại bằng latch để tạo khoảng thời gian cạnh tranh. Sau khi cho supplier hoàn tất, cả hai future phải nhận cùng giá trị và counter bằng 1.

Có thể viết test tương tự cho `Map.ofLazy`: dùng hai task cùng gọi `map.get("shared-key")`, một supplier có latch và counter; sau khi hoàn tất, cả hai phải nhận cùng value và function chỉ có một lần khởi tạo thành công.

### Kiểm thử nhiều index hoặc key khác nhau

Một điểm quan trọng khác là lazy collection tính riêng từng phần tử. Hai luồng truy cập hai index khác nhau không cần dùng chung một kết quả:

~~~java
AtomicInteger[] calls = {
    new AtomicInteger(),
    new AtomicInteger()
};

List<String> values = List.ofLazy(2, index -> {
    calls[index].incrementAndGet();
    return "value-" + index;
});
~~~

Chạy `values.get(0)` và `values.get(1)` trên hai luồng; sau khi cả hai hoàn tất, mỗi counter phải bằng 1. Không viết assertion rằng hai supplier bắt buộc chạy song song: API bảo đảm kết quả theo index/key, không hứa lịch thực thi hoặc tốc độ song song cụ thể.

### Tránh test phụ thuộc thời gian hoặc trạng thái thread

Không dùng `Thread.sleep()` để suy luận rằng thread thứ hai chắc chắn đang bị block. Lịch chạy phụ thuộc scheduler và môi trường CI. Dùng `CountDownLatch`, `Future.get(timeout, unit)` và counter để tạo đồng bộ xác định. Timeout trong test chỉ là giới hạn để test không treo vô hạn; nó không phải timeout của API lazy collection.

## 8. Kiểm thử đệ quy cùng index hoặc key

Nếu computing function gọi lại chính lazy collection để truy cập đúng index/key đang được tính, API ném `IllegalStateException`.

Ví dụ với list:

~~~java
AtomicReference<List<String>> reference = new AtomicReference<>();

reference.set(List.ofLazy(
    1,
    index -> reference.get().get(index)
));

assertThrows(
    IllegalStateException.class,
    () -> reference.get().get(0)
);
~~~

Với map:

~~~java
AtomicReference<Map<String, String>> reference = new AtomicReference<>();

reference.set(Map.ofLazy(
    Set.of("loop"),
    key -> reference.get().get(key)
));

assertThrows(
    IllegalStateException.class,
    () -> reference.get().get("loop")
);
~~~

Đây là test hữu ích để phát hiện supplier tự phụ thuộc vào kết quả mà nó đang tạo. Nếu function truy cập một index/key khác, cần phân tích dependency graph riêng; tránh tạo chu trình gián tiếp giữa nhiều phần tử.

## 9. Các thao tác tưởng như chỉ quan sát cũng có thể khởi tạo phần tử

Không chỉ `get(index)` hoặc `get(key)` mới có thể kích hoạt tính toán. Một số thao tác duyệt hoặc biểu diễn collection cần đọc các giá trị bên trong.

Với lazy list:

- `subList()` và `reversed()` tạo view vẫn giữ hành vi lazy.
- `equals()`, `hashCode()` và `toString()` có thể kích hoạt một hoặc nhiều phần tử.
- Duyệt iterator, stream hoặc chuyển sang array sẽ cần đọc các phần tử mà thao tác đó duyệt.

Với lazy map:

- `values()` và `entrySet()` là view có value lazy; đọc value của entry có thể kích hoạt function tương ứng.
- `equals()`, `hashCode()` và `toString()` có thể kích hoạt một hoặc nhiều value.
- Duyệt toàn bộ entries hoặc values có thể khiến nhiều key được khởi tạo.

Ví dụ, đoạn log sau có thể làm nhiều phần tử được khởi tạo ngoài dự kiến:

~~~java
logger.debug("Loaded items: {}", lazyItems);
logger.debug("Configuration map: {}", lazyConfig);
~~~

Nếu logger đánh giá đối số và gọi `toString()`, collection có thể tính nhiều phần tử. Trong code cần giữ lazy behavior, hãy log metadata như `size()` hoặc danh sách key thay vì stringify toàn bộ collection.

Đừng viết test yêu cầu `toString()` phải khởi tạo đúng một phần tử hay theo một thứ tự cụ thể. Javadoc chỉ nói các Object methods có thể kích hoạt một hoặc nhiều phần tử; chi tiết số lượng và thứ tự không phải hợp đồng nên phụ thuộc.

## 10. Kiểm tra giới hạn và tính không sửa đổi được

Lazy list và lazy map là collection không sửa đổi được. Các phép thay đổi như `add`, `set`, `remove`, `put` hoặc `clear` không được hỗ trợ và ném `UnsupportedOperationException`.

~~~java
List<String> list = List.ofLazy(2, i -> "v" + i);
Map<String, String> map = Map.ofLazy(
    Set.of("a"),
    key -> "value-" + key
);

assertThrows(UnsupportedOperationException.class, () -> list.set(0, "changed"));
assertThrows(UnsupportedOperationException.class, () -> map.put("b", "new"));
~~~

Collection không sửa đổi được không đồng nghĩa object được chứa bên trong là immutable sâu. Nếu function trả về một object mutable, caller vẫn có thể thay đổi trạng thái object đó. Hãy chọn giá trị bất biến hoặc quản lý quyền sửa đổi ở tầng ứng dụng.

Cả lazy list và lazy map đều không Serializable theo hợp đồng API JDK 26. Không dựa vào việc serialize để lưu trạng thái các phần tử đã khởi tạo.

## 11. Ma trận test cần có

| Nhóm kiểm thử | Lazy List | Lazy Map | Kỳ vọng |
|---|---|---|---|
| Tạo collection | Tạo với size | Tạo với Set key | Chưa gọi computing function |
| Truy cập lần đầu | `get(index)` | `get(key)` | Tính đúng một phần tử/key |
| Truy cập lặp | Cùng index | Cùng key | Dùng lại kết quả |
| Thứ tự truy cập | Ghi index | Ghi key | Khớp chuỗi gọi get trong test |
| Truy cập phần khác | Index khác | Key khác | Tính độc lập |
| Exception | Function ném lỗi | Function ném lỗi | Exception truyền tới caller; chưa ghi value |
| Retry | Truy cập lại index lỗi | Truy cập lại key lỗi | Có thể tính lại và thành công |
| Null | Function trả null | Function trả null | Ném NPE; không lưu null |
| Đệ quy | Gọi lại cùng index | Gọi lại cùng key | Ném IllegalStateException |
| Đồng thời | Nhiều thread cùng index | Nhiều thread cùng key | Một lần khởi tạo thành công; cùng kết quả |
| Object methods | equals/hashCode/toString | equals/hashCode/toString | Có thể kích hoạt phần tử/value |
| Mutator | add/set/remove | put/remove/clear | UnsupportedOperationException |

## 12. Chạy test với JDK 26 preview

`List.ofLazy` và `Map.ofLazy` là preview API trong JDK 26. Để biên dịch và chạy test, dùng đúng JDK 26 và bật preview cho cả compiler lẫn runtime.

Với mã nguồn Java độc lập:

~~~bash
javac --release 26 --enable-preview -d out LazyCollectionsExample.java
java --enable-preview -cp out LazyCollectionsExample
~~~

Với JUnit, cấu hình tương đương ở build tool:

- Compiler dùng release 26 và `--enable-preview`.
- JVM chạy test cũng nhận `--enable-preview`.
- Test runtime dùng đúng JDK 26.
- Ghi lại vendor và build JDK khi chạy CI.

Không chỉ bật preview lúc compile. Nếu runtime không bật preview, class có sử dụng preview API có thể không chạy được. Preview gắn với release cụ thể; không giả định class được biên dịch cho preview JDK 26 sẽ chạy trên một release khác.

## 13. Đọc kết quả test và đưa ra quyết định

Một test đúng nên kiểm tra hợp đồng API thay vì kiểm tra chi tiết implementation:

- Dùng counter để xác nhận số lần khởi tạo thành công cho từng index/key.
- Dùng chuỗi truy cập rõ ràng để xác nhận thứ tự gọi function.
- Dùng latch để tạo cạnh tranh giữa các luồng và future timeout để ngăn test treo.
- Kiểm tra exception truyền đến caller và lần truy cập sau có thể thử lại.
- Không khẳng định thứ tự duyệt của Map.
- Không khẳng định số phần tử cụ thể được khởi tạo bởi `toString()`, `hashCode()` hoặc `equals()`.
- Không dùng test timing để suy luận supplier chạy song song hay tuần tự.

Nếu test cho thấy một phần tử bị tính lại sau khi đã thành công, hãy thu nhỏ test để kiểm tra liệu thực tế lần đầu có ném exception hoặc trả null hay không. Nếu nhiều luồng cùng truy cập, xác nhận chúng đang dùng cùng một lazy collection instance và cùng index/key.

## 14. Trạng thái và phạm vi sử dụng

`List.ofLazy` và `Map.ofLazy` là preview API của Java 26, không phải API Java SE ổn định. Có thể dùng chúng để thử nghiệm và đánh giá mô hình lazy per-element/per-key trên JDK 26. Trước khi sử dụng trong production hoặc public library, kiểm tra trạng thái API trên JDK đích và khả năng chấp nhận phụ thuộc preview của dự án.

Các nguyên tắc kiểm thử trong bài vẫn có giá trị cho bất kỳ abstraction memoization/lazy collection nào: tách trạng thái chưa tính, đang tính, đã thành công và thất bại; kiểm tra retry; kiểm tra cạnh tranh; không để các thao tác quan sát kích hoạt công việc tốn kém ngoài ý muốn.

## Kết luận

Kiểm thử lazy collection cần theo dõi từng index của list hoặc từng key của map. Tạo collection không gọi computing function; lần truy cập đầu khởi tạo giá trị tương ứng; truy cập lặp dùng lại kết quả thành công. Exception và null không ghi value nên lần sau có thể thử lại; nhiều luồng cùng index/key chỉ có một lần khởi tạo thành công và các luồng cạnh tranh chờ kết quả. Cần chú ý các view và Object methods có thể kích hoạt thêm giá trị, đồng thời không giả định thứ tự duyệt của Map. Trên JDK 26, cả `List.ofLazy` và `Map.ofLazy` đều là preview API, nên phải bật preview ở cả compile và runtime.

## Tài liệu tham khảo

- [Java 26 API – List.ofLazy](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/List.html)
- [Java 26 API – Map.ofLazy](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Map.html)
- [Java 26 Core Libraries Guide – Lazy Lists and Lazy Maps](https://docs.oracle.com/en/java/javase/26/core/lazy-constants.html)
- [Java 26 javac Command – --enable-preview](https://docs.oracle.com/en/java/javase/26/docs/specs/man/javac.html)
- [Java 26 java Command – --enable-preview](https://docs.oracle.com/en/java/javase/26/docs/specs/man/java.html)
