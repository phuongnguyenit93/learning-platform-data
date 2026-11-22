# Kiểm thử số lượng đầu ra, tính lười, dừng sớm và ghép trạng thái

> **Chương:** Xây dựng Gatherer tùy biến  
> **Module:** `JAVA_STREAM_API` — học xử lý dữ liệu khai báo bằng Java Stream API qua pipeline lazy, `filter`, `map`, `reduce`, `collect`; thực hành grouping, collector tùy chỉnh, `Spliterator`, xử lý song song và Stream Gatherers, đồng thời nhận diện giới hạn về trạng thái, tài nguyên và hiệu năng.

Khi tự viết một `Gatherer`, việc chạy được trên vài phần tử **chưa chứng minh được nó đúng**. Một Gatherer có thể phát ra **không, một hoặc nhiều phần tử** cho mỗi phần tử đầu vào; có thể đợi đến cuối nguồn mới phát kết quả; có thể tự yêu cầu dừng sớm; và nếu hỗ trợ song song, nó phải ghép trạng thái từ nhiều nhánh theo hợp đồng. Những hành vi này cần các ca kiểm thử khác nhau.

Bài học tập trung vào **cách thiết kế và kiểm thử Gatherer tùy biến**, không chỉ cách viết lambda. Các ví dụ sử dụng API `java.util.stream.Gatherer` và `Stream.gather(...)` đã là tính năng chính thức từ **Java 24**. Trên Java 22/23, Stream Gatherers ở trạng thái preview và cần cấu hình preview tương ứng; mã trong bài nhắm tới **JDK 24 trở lên**, không chạy trên JDK 17.

Sau bài này, bạn có thể:

1. Xác định số kết quả của Gatherer với nguồn rỗng, nguồn nhiều phần tử, batch chưa đầy và downstream giới hạn số phần tử.
2. Kiểm tra pipeline chỉ thực thi khi có terminal operation, không lấy side effect trong `peek` làm hợp đồng nghiệp vụ.
3. Phân biệt **dừng do integrator** và **dừng vì downstream không nhận thêm**; truyền tín hiệu `false` đúng cách.
4. Kiểm thử `initializer`, `integrator`, `combiner`, `finisher` của Gatherer có trạng thái; đối chiếu bản tuần tự và song song.
5. Phát hiện lỗi khi `combiner` bỏ dữ liệu, khi state bị dùng chung, hoặc khi phép gộp không kết hợp.

## 1. Nhắc lại hợp đồng `Gatherer<T, A, R>`

Một Gatherer là **intermediate operation** chuyển `Stream<T>` thành `Stream<R>`; không nhất thiết có tương quan 1:1 giữa số phần tử đầu vào và đầu ra. Với Gatherer có trạng thái, `A` là kiểu state nội bộ.

| Thành phần | Kiểu khái quát | Ý nghĩa khi kiểm thử |
| --- | --- | --- |
| `initializer` | `Supplier<A>` | Mỗi trạng thái phải được tạo mới, không rò rỉ giữa các lượt chạy hoặc các nhánh. |
| `integrator` | `Integrator<A, T, R>` | Nhận phần tử, có thể `push` 0..n kết quả, trả `true` để tiếp tục hoặc `false` để dừng. |
| `combiner` | `BinaryOperator<A>` | Ghép hai trạng thái từ các phân vùng; cần đúng với identity và associativity. |
| `finisher` | `BiConsumer<A, Downstream<? super R>>` | Tùy chọn phát kết quả cuối sau khi tích lũy, có thể tạo đầu ra cả khi nguồn rỗng. |

Hai phương thức liên quan tới dừng sớm:

```java
boolean accepted = downstream.push(result);
boolean rejecting = downstream.isRejecting();
```

- `push(result)` trả `false` nếu downstream không muốn nhận thêm kết quả. Nếu đã trả `false`, những lần `push` tiếp theo không được chấp nhận.
- `isRejecting()` chỉ là tín hiệu kiểm tra **best-effort**: không được dựa vào nó như bảo đảm tuyệt đối rằng downstream sẽ nhận thêm.
- `Integrator.integrate(...)` trả `false` để báo **không cần thêm đầu vào**. Khi đó không nên chờ integrator được gọi tiếp.
- `Gatherer.Integrator.Greedy` là loại integrator **không tự khởi phát dừng sớm**; nó chỉ có thể phản ánh yêu cầu dừng từ downstream. Không đánh dấu greedy cho một integrator chủ động trả `false` khi đạt số phần tử.

Sơ đồ tổng quát:

```text
Nguồn T ──► integrator(state, T, downstream)
                    │
                    ├── không push        → 0 kết quả
                    ├── push một lần      → 1 kết quả
                    ├── push nhiều lần    → nhiều kết quả
                    └── return false      → ngừng nhận phần tử nguồn
                              │
                              ▼
               combiner (nếu chia nhánh) + finisher
                              │
                              ▼
                         Stream<R>
```

Lưu ý `Gatherer.ofSequential(...)` tạo Gatherer có hợp đồng xử lý tuần tự cho chính giai đoạn gather. `Gatherer.of(initializer, integrator, combiner, finisher)` cho phép giai đoạn này phân vùng và ghép state khi cần. Không nên giả định mọi pipeline song song **bắt buộc** gọi combiner hoặc gọi nó một số lần cố định.

## 2. Ma trận kiểm thử cần chuẩn bị trước khi viết mã

| Tiêu chí | Ca kiểm thử | Kỳ vọng cần khẳng định |
| --- | --- | --- |
| Số đầu ra | 0 phần tử nguồn | 0 hoặc số đầu ra do finisher **được thiết kế rõ**, không tự mặc định. |
| Số đầu ra | Gatherer nhân đôi 3 phần tử | Đúng 6 phần tử và đúng nội dung. |
| Batch | 5 phần tử, cỡ batch 2 | Hai batch đầy và một batch cuối có 1 phần tử. |
| Lazy | Tạo pipeline nhưng chưa có terminal operation | Chưa duyệt nguồn. |
| Dừng do integrator | `takeFirst(3)` trên nguồn dài/vô hạn | Đúng 3 kết quả; kết thúc được mà không phải xử lý toàn nguồn. |
| Dừng do downstream | `duplicate().limit(3)` | Đúng 3 kết quả; integrator không cố gửi mãi sau khi bị từ chối. |
| Ghép state | Chia dữ liệu thành nhiều phần | Tổng kết hợp giống tính một lượt. |
| Identity | Gộp với state rỗng | Kết quả không đổi. |
| Associativity | `(A + B) + C` và `A + (B + C)` | Kết quả tương đương. |
| Song song | Cùng một dữ liệu, tuần tự và song song | Kết quả nghiệp vụ giống nhau. |
| Thứ tự | Nguồn `List` có encounter order | Giữ thứ tự nếu đây là hợp đồng của Gatherer. |

Không nên gom tất cả vào một kiểm thử tổng quát. Nếu chỉ kiểm `count()`, bạn có thể bỏ sót **thứ tự sai nhưng số phần tử đúng**; nếu chỉ kiểm dữ liệu nhỏ tuần tự, bạn có thể không phát hiện **combiner mất dữ liệu**.

## 3. Kiểm thử số lượng đầu ra: một đầu vào có thể tạo nhiều kết quả

Ví dụ nhỏ nhất là một Gatherer **phát mỗi phần tử hai lần**. Vì không cần trạng thái, ta dùng overload không có initializer:

```java
import java.util.stream.Gatherer;

static Gatherer<Integer, ?, Integer> duplicateEach() {
    return Gatherer.<Integer, Integer>ofSequential(
            (ignored, value, downstream) -> {
                if (!downstream.push(value)) {
                    return false;
                }
                return downstream.push(value);
            }
    );
}
```

`duplicateEach()` là một **intermediate operation**, không phải `map` thông thường: `map` phát đúng một kết quả cho một đầu vào còn Gatherer này phát tối đa hai.

```java
List<Integer> doubled = Stream.of(2, 4, 6)
        .gather(duplicateEach())
        .toList();

System.out.println(doubled); // [2, 2, 4, 4, 6, 6]
```

Nếu nguồn rỗng, kết quả rỗng. Nếu downstream dừng sau 3 đầu ra, kết quả là `[2, 2, 4]`: không có yêu cầu phải phát đủ cặp cho phần tử `4` **sau khi downstream từ chối**.

**Lỗi thường gặp:** viết hai lần `downstream.push(value)` rồi luôn `return true`. Khi `push` đầu tiên trả `false`, lời gọi thứ hai là công việc thừa và Gatherer không phản ánh tín hiệu dừng tới upstream.

## 4. Kiểm thử batch cuối: `finisher` có thể thay đổi số đầu ra

Một mẫu phổ biến là gom từng nhóm `size` phần tử thành `List<T>`. Nếu còn nhóm chưa đầy khi nguồn hết, `finisher` cần phát nốt. Đây là ví dụ **tuần tự**, để tránh yêu cầu phức tạp về vị trí ghép các batch giữa những nhánh song song.

```java
static Gatherer<Integer, ?, List<Integer>> fixedBatches(int size) {
    if (size <= 0) {
        throw new IllegalArgumentException("size phải dương");
    }
    return Gatherer.<Integer, List<Integer>, List<Integer>>ofSequential(
            ArrayList::new,
            (buffer, value, downstream) -> {
                buffer.add(value);
                if (buffer.size() == size) {
                    List<Integer> batch = List.copyOf(buffer);
                    buffer.clear();
                    return downstream.push(batch);
                }
                return true;
            },
            (buffer, downstream) -> {
                if (!buffer.isEmpty() && !downstream.isRejecting()) {
                    downstream.push(List.copyOf(buffer));
                }
            }
    );
}
```

Kết quả:

```java
List<List<Integer>> batches = Stream.of(1, 2, 3, 4, 5)
        .gather(fixedBatches(2))
        .toList();
// [[1, 2], [3, 4], [5]]
```

Ở đây:

- Đầu vào có 5 phần tử, đầu ra chỉ có **3 phần tử**, mỗi phần tử đầu ra lại là một `List<Integer>`.
- `integrator` phát batch ngay khi đủ 2 phần tử.
- `finisher` phát batch cuối chỉ nếu còn dữ liệu và downstream chưa biết là đang từ chối.
- Với nguồn rỗng, kết quả là danh sách rỗng vì `buffer` rỗng; khác với một Gatherer tổng hợp toàn kỳ có thể cố ý phát **một đối tượng tổng kết rỗng**.
- `List.copyOf(buffer)` tách batch đầu ra khỏi buffer mutable đang dùng lại. Nếu đẩy trực tiếp `buffer` rồi gọi `clear()`, những batch đã trả có thể bị thay đổi ngoài ý muốn.

Đừng chỉ kiểm `batches.size() == 3`: còn phải kiểm từng batch, vì các lỗi `[1,2], [2,3], [4]` cũng cho ba batch nhưng sai nội dung.

## 5. Kiểm thử tính lười: phân biệt tạo pipeline với chạy pipeline

Gatherer là phép toán trung gian, nên **việc tạo pipeline không tự kéo phần tử từ nguồn**. Mã kiểm thử có thể dùng một biến đếm chỉ để quan sát số lần bước trung gian được đánh giá:

```java
AtomicInteger visited = new AtomicInteger();

Stream<Integer> pipeline = IntStream.rangeClosed(1, 4)
        .boxed()
        .map(n -> {
            visited.incrementAndGet(); // Chỉ dùng làm đo đạc trong test
            return n;
        })
        .gather(duplicateEach());

check(visited.get() == 0, "Pipeline chạy quá sớm");
List<Integer> result = pipeline.toList();
check(result.equals(List.of(1, 1, 2, 2, 3, 3, 4, 4)),
        "Nội dung đầu ra");
check(visited.get() == 4, "Nguồn không được xử lý đủ");
```

Trong ví dụ này, `toList()` cần các kết quả mà Gatherer tạo ra, vì vậy bốn đầu vào phải đi qua `map`. Tuy nhiên, **không suy rộng** rằng mọi `map` hoặc `peek` luôn được gọi đúng một lần cho mỗi phần tử ở mọi pipeline: Java Stream cho phép tối ưu bỏ qua thao tác trung gian nếu nó không ảnh hưởng kết quả terminal operation.

**Nguyên tắc:** biến đếm ngoài pipeline là công cụ **quan sát trong ca kiểm thử cụ thể**, không phải thiết kế nghiệp vụ. Ở sản phẩm thực, tránh đặt ghi dữ liệu, tăng bộ đếm kinh doanh hoặc gửi thông báo trong `peek` rồi mặc định pipeline sẽ luôn thực thi chúng.

## 6. Kiểm thử dừng sớm do chính Gatherer

Một Gatherer kiểu `takeFirst(maximum)` có state đếm số phần tử đã phát. Ngay khi phát đủ số lượng, integrator trả `false`.

```java
static Gatherer<Integer, ?, Integer> takeFirst(int maximum) {
    if (maximum < 0) {
        throw new IllegalArgumentException("maximum âm");
    }
    return Gatherer.<Integer, int[], Integer>ofSequential(
            () -> new int[1],
            (state, value, downstream) -> {
                if (state[0] >= maximum) {
                    return false;
                }
                state[0]++;
                return downstream.push(value) && state[0] < maximum;
            }
    );
}
```

Kiểm thử:

```java
List<Integer> firstThree = Stream.iterate(1, n -> n + 1)
        .gather(takeFirst(3))
        .toList();
// [1, 2, 3]
```

Nguồn `Stream.iterate` có thể vô hạn. Nếu Gatherer không dừng đúng lúc, terminal operation `toList()` sẽ không kết thúc. Trong một bộ kiểm thử tự động lớn, nên bổ sung **timeout của cả ca kiểm thử**, để khi code dừng sớm bị lỗi, suite không treo vô hạn.

Đừng sử dụng `Gatherer.Integrator.ofGreedy(...)` cho `takeFirst`: integrator này **tự chủ động** ngừng nhận phần tử nguồn theo số lượng, nên không thỏa ý nghĩa *greedy*.

### `maximum == 0` có nghĩa gì?

`takeFirst(0)` tạo **đầu ra rỗng**. Với triển khai mẫu, nó có thể nhận một phần tử đầu vào để integrator xác định cần dừng rồi mới trả `false`; vì vậy không nên quảng bá phép kiểm thử này như bảo đảm **không kéo bất kỳ phần tử nguồn nào**. Nếu nghiệp vụ cần không chạm vào nguồn khi số lượng bằng 0, đặt `limit(0)` trước khi bắt đầu xử lý hoặc thiết kế riêng phía gọi.

## 7. Kiểm thử dừng do downstream: `push` và `limit`

Khác với `takeFirst`, ở đây **downstream** là phía quyết định đã đủ dữ liệu:

```java
List<Integer> limited = Stream.iterate(1, n -> n + 1)
        .gather(duplicateEach())
        .limit(3)
        .toList();

System.out.println(limited); // [1, 1, 2]
```

Sau `limit(3)`, downstream không cần thêm phần tử. Gatherer cần ngừng gửi thêm ngay khi `push` báo `false`, không tiếp tục cố nhân đôi các phần tử tiếp theo.

Hai hướng dừng cần kiểm tra độc lập:

| Nguồn dừng | Mã ví dụ | Tín hiệu chính |
| --- | --- | --- |
| Integrator chủ động dừng | `gather(takeFirst(3))` | `integrate` trả `false` khi đạt hạn mức. |
| Downstream từ chối | `gather(duplicateEach()).limit(3)` | `downstream.push(...)` trả `false`, integrator truyền lại. |

Đối với pipeline song song hoặc có buffer, **không kiểm thử bằng giả định rằng upstream nhất định chỉ truy cập đúng 3 phần tử**. Các bước có thể đã kéo trước hoặc xử lý thêm phần tử theo chi tiết triển khai. Hãy kiểm tra **đầu ra và khả năng kết thúc**; chỉ dùng các mốc đếm chính xác khi hợp đồng hoặc thiết kế nguồn thực sự bảo đảm chúng.

## 8. Ghép trạng thái: kiểm thử identity và associativity

Gatherer thu thập thống kê có thể dùng `A = CountState`, trong đó `count` và `sum` được cập nhật khi nhận phần tử. Thay vì phát kết quả ở từng lần tích lũy, `finisher` phát **một** `Summary` sau khi xử lý xong.

```java
record Summary(long count, long sum) {}

static final class CountState {
    long count;
    long sum;

    void add(long n) {
        count = Math.addExact(count, 1);
        sum = Math.addExact(sum, n);
    }

    CountState merge(CountState right) {
        count = Math.addExact(count, right.count);
        sum = Math.addExact(sum, right.sum);
        return this;
    }

    Summary snapshot() {
        return new Summary(count, sum);
    }
}
```

Với Gatherer có bốn thành phần:

```java
static Gatherer<Long, ?, Summary> countAndSum() {
    return Gatherer.<Long, CountState, Summary>of(
            CountState::new,
            Gatherer.Integrator.ofGreedy((state, value, downstream) -> {
                state.add(value);
                return true; // Không tự dừng trước khi nguồn kết thúc
            }),
            CountState::merge,
            (state, downstream) -> {
                if (!downstream.isRejecting()) {
                    downstream.push(state.snapshot());
                }
            }
    );
}
```

Khác biệt với `duplicateEach`:

- `initializer` tạo **state riêng** cho mỗi phân vùng.
- `integrator` chỉ cập nhật state, **không phát gì trong lúc duyệt**.
- `combiner` gộp count và sum của hai state. Một `CountState` đã gộp vẫn phải hợp lệ để gộp tiếp.
- `finisher` phát một `Summary` sau khi tích lũy; ngay cả nguồn rỗng, nếu finisher được chạy và downstream nhận kết quả thì đầu ra là `Summary(0, 0)`.

Phép gộp phải thỏa:

```text
identity:      merge(a, empty)           ~ a
associativity: merge(merge(a,b), c)     ~ merge(a, merge(b,c))
```

`~` nghĩa là **tương đương về kết quả**, không đòi hai biểu thức phải trả cùng địa chỉ đối tượng. Trong bài toán với `count` và `sum`, state rỗng `(0, 0)` là phần tử trung hòa; cộng các giá trị trong miền `long` hợp lệ có tính kết hợp. `Math.addExact` ném ngoại lệ nếu tràn, giúp lỗi số học không bị che giấu.

### Kiểm thử combiner trực tiếp

Không nên chỉ chạy `parallelStream()` với ba phần tử và kỳ vọng combiner phải được gọi. Framework có quyền chọn chia ít hoặc không chia. Hãy gọi phép merge **trực tiếp** với các state độc lập:

```java
static CountState stateOf(long... values) {
    CountState state = new CountState();
    for (long value : values) {
        state.add(value);
    }
    return state;
}

Summary leftGrouped = stateOf(1, 2)
        .merge(stateOf(3))
        .merge(stateOf(4, 5))
        .snapshot();

Summary rightGrouped = stateOf(1, 2)
        .merge(stateOf(3).merge(stateOf(4, 5)))
        .snapshot();

check(leftGrouped.equals(rightGrouped), "Ghép state phụ thuộc cách chia");
check(leftGrouped.equals(new Summary(5, 15)), "Ghép state sai");
check(stateOf(1, 2).merge(new CountState())
        .snapshot().equals(new Summary(2, 3)), "Identity sai");
```

Phép thử này có thể phát hiện lỗi quên cộng `right.count` hoặc `right.sum` dù lúc chạy tuần tự chưa thấy vấn đề.

### Kiểm thử trên Stream tuần tự và song song

```java
List<Summary> sequential = LongStream.rangeClosed(1, 100)
        .boxed()
        .gather(countAndSum())
        .toList();

List<Summary> parallel = LongStream.rangeClosed(1, 100)
        .parallel()
        .boxed()
        .gather(countAndSum())
        .toList();

check(sequential.equals(List.of(new Summary(100, 5050))),
        "Tổng tuần tự sai");
check(parallel.equals(sequential), "Tổng song song khác tuần tự");
```

Đây là kiểm thử **kết quả**, không phải kiểm thử số thread, thứ tự thực thi hoặc số lần gọi combiner. Vì chỉ phát một `Summary` trong finisher sau khi đã gộp các nhánh, kết quả được kiểm soát bằng hợp đồng tích lũy và gộp.

### Những gatherer KHÔNG thể ghép state đơn giản

Đối với thao tác phụ thuộc thứ tự như lấy “3 phần tử đầu tiên”, “batch 2 phần tử liên tiếp” hoặc “trung bình trượt”, không thể tự cho `combiner` gộp hai `List` bất kỳ rồi suy rằng kết quả song song sẽ đúng.

Ví dụ batch ở ranh giới nhánh có thể phải kết hợp phần dư của nhánh trái với phần đầu nhánh phải. Nếu không quản lý thứ tự, vị trí, phần dư và tính kết hợp thật chặt, **hãy dùng `Gatherer.ofSequential`**. Chỉ chuyển sang `Gatherer.of` có combiner khi đã chứng minh được phép gộp tương đương xử lý toàn nguồn theo encounter order.

## 9. Chương trình Java 24+ hoàn chỉnh để tự kiểm tra

Đoạn dưới đây tập hợp các Gatherer đã giới thiệu và kiểm thử trong một tệp. Lưu thành `GathererVerificationDemo.java`; yêu cầu **JDK 24+**.

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.stream.Gatherer;
import java.util.stream.IntStream;
import java.util.stream.LongStream;
import java.util.stream.Stream;

public class GathererVerificationDemo {

    record Summary(long count, long sum) {}

    static final class CountState {
        long count;
        long sum;

        void add(long n) {
            count = Math.addExact(count, 1);
            sum = Math.addExact(sum, n);
        }

        CountState merge(CountState other) {
            count = Math.addExact(count, other.count);
            sum = Math.addExact(sum, other.sum);
            return this;
        }

        Summary snapshot() {
            return new Summary(count, sum);
        }
    }

    static Gatherer<Integer, ?, Integer> duplicateEach() {
        return Gatherer.<Integer, Integer>ofSequential(
                (ignored, value, downstream) -> {
                    if (!downstream.push(value)) {
                        return false;
                    }
                    return downstream.push(value);
                }
        );
    }

    static Gatherer<Integer, ?, List<Integer>> fixedBatches(int size) {
        if (size <= 0) {
            throw new IllegalArgumentException("size phải dương");
        }
        return Gatherer.<Integer, List<Integer>, List<Integer>>ofSequential(
                ArrayList::new,
                (buffer, value, downstream) -> {
                    buffer.add(value);
                    if (buffer.size() == size) {
                        List<Integer> batch = List.copyOf(buffer);
                        buffer.clear();
                        return downstream.push(batch);
                    }
                    return true;
                },
                (buffer, downstream) -> {
                    if (!buffer.isEmpty() && !downstream.isRejecting()) {
                        downstream.push(List.copyOf(buffer));
                    }
                }
        );
    }

    static Gatherer<Integer, ?, Integer> takeFirst(int maximum) {
        if (maximum < 0) {
            throw new IllegalArgumentException("maximum âm");
        }
        return Gatherer.<Integer, int[], Integer>ofSequential(
                () -> new int[1],
                (state, value, downstream) -> {
                    if (state[0] >= maximum) {
                        return false;
                    }
                    state[0]++;
                    return downstream.push(value) && state[0] < maximum;
                }
        );
    }

    static Gatherer<Long, ?, Summary> countAndSum() {
        return Gatherer.<Long, CountState, Summary>of(
                CountState::new,
                Gatherer.Integrator.ofGreedy(
                        (state, value, downstream) -> {
                            state.add(value);
                            return true;
                        }),
                CountState::merge,
                (state, downstream) -> {
                    if (!downstream.isRejecting()) {
                        downstream.push(state.snapshot());
                    }
                }
        );
    }

    static CountState stateOf(long... values) {
        CountState state = new CountState();
        for (long value : values) {
            state.add(value);
        }
        return state;
    }

    static void check(boolean ok, String message) {
        if (!ok) {
            throw new AssertionError(message);
        }
    }

    static void testOutputCounts() {
        check(Stream.<Integer>empty().gather(duplicateEach())
                .toList().isEmpty(), "Nguồn rỗng");
        check(Stream.of(2, 4, 6).gather(duplicateEach())
                .toList().equals(List.of(2, 2, 4, 4, 6, 6)),
                "Số lượng/nội dung khi nhân đôi");

        List<List<Integer>> batches = Stream.of(1, 2, 3, 4, 5)
                .gather(fixedBatches(2))
                .toList();
        check(batches.equals(List.of(
                List.of(1, 2), List.of(3, 4), List.of(5))),
                "Batch cuối");
        check(Stream.<Integer>empty()
                .gather(fixedBatches(2)).toList().isEmpty(),
                "Batch nguồn rỗng");
    }

    static void testLaziness() {
        AtomicInteger visited = new AtomicInteger();
        Stream<Integer> pipeline = IntStream.rangeClosed(1, 4)
                .boxed()
                .map(n -> {
                    visited.incrementAndGet(); // Đo trong test
                    return n;
                })
                .gather(duplicateEach());

        check(visited.get() == 0, "Chưa terminal mà đã duyệt");
        check(pipeline.toList().equals(
                List.of(1, 1, 2, 2, 3, 3, 4, 4)),
                "Kết quả lazy pipeline");
        check(visited.get() == 4, "Sai số phần tử được duyệt");
    }

    static void testShortCircuit() {
        check(Stream.iterate(1, n -> n + 1)
                .gather(takeFirst(3))
                .toList().equals(List.of(1, 2, 3)),
                "Integrator không dừng sớm");
        check(Stream.of(1, 2, 3)
                .gather(takeFirst(0)).toList().isEmpty(),
                "Lấy 0 phần tử");
        check(Stream.iterate(1, n -> n + 1)
                .gather(duplicateEach())
                .limit(3)
                .toList().equals(List.of(1, 1, 2)),
                "Không tôn trọng downstream limit");
    }

    static void testStateCombiner() {
        Summary left = stateOf(1, 2)
                .merge(stateOf(3))
                .merge(stateOf(4, 5))
                .snapshot();
        Summary right = stateOf(1, 2)
                .merge(stateOf(3).merge(stateOf(4, 5)))
                .snapshot();

        check(left.equals(right), "Combiner không kết hợp");
        check(left.equals(new Summary(5, 15)), "Combiner bỏ dữ liệu");
        check(stateOf(1, 2).merge(new CountState())
                .snapshot().equals(new Summary(2, 3)),
                "Phần tử trung hòa sai");

        List<Summary> sequential = LongStream.rangeClosed(1, 100)
                .boxed().gather(countAndSum()).toList();
        List<Summary> parallel = LongStream.rangeClosed(1, 100)
                .parallel().boxed().gather(countAndSum()).toList();

        check(sequential.equals(List.of(new Summary(100, 5050))),
                "Tổng tuần tự");
        check(parallel.equals(sequential),
                "Tổng song song khác tuần tự");
        check(Stream.<Long>empty().gather(countAndSum()).toList()
                .equals(List.of(new Summary(0, 0))),
                "Finisher với nguồn rỗng");
    }

    public static void main(String[] args) {
        testOutputCounts();
        testLaziness();
        testShortCircuit();
        testStateCombiner();
        System.out.println("ALL GATHERER TESTS PASS");
    }
}
```

Trên JDK 24+ có thể biên dịch và chạy trực tiếp:

```text
javac GathererVerificationDemo.java
java GathererVerificationDemo
```

Kết quả mong đợi khi mọi kiểm tra đạt:

```text
ALL GATHERER TESTS PASS
```

Trong chương trình, `check` ném `AssertionError` nếu kết quả sai nên không phụ thuộc cờ `-ea` của lệnh `java`. Phần này cung cấp **mã kiểm thử cho người học**, không khẳng định chương trình đã được biên dịch/thực thi trong bước viết tài liệu.

## 10. Những lỗi thường gặp khi kiểm thử Gatherer

| Lỗi | Vì sao nguy hiểm | Hướng kiểm thử/khắc phục |
| --- | --- | --- |
| Giả định mỗi đầu vào chỉ phát một đầu ra | Gatherer có thể nhân đôi, lọc, gom batch, hoặc phát từ finisher | Kiểm tra cả số lượng và nội dung với dữ liệu mẫu và nguồn rỗng. |
| `push` tiếp sau khi downstream báo `false` | Gây việc thừa, có thể làm mất ý nghĩa short-circuit | Trả `false` ngay và kiểm thử với `limit`. |
| Dùng `Integrator.Greedy` cho gatherer tự dừng sau N phần tử | Khai báo sai hợp đồng; hệ thống có thể bỏ qua tín hiệu dừng | Dùng integrator thường khi chủ động short-circuit. |
| Quên phát batch chưa đủ trong finisher | Mất phần tử cuối | Thử đầu vào cỡ 0, 1, đúng bội số batch, hơn bội số một phần tử. |
| Gửi buffer mutable rồi `clear()` | Kết quả đã phát bị thay đổi | Phát bản sao độc lập; kiểm tra danh sách batch. |
| Suy từ `count()` rằng `peek` luôn được gọi | Một số phép toán cho phép tối ưu bỏ qua stage không ảnh hưởng kết quả | Kiểm tra lazy bằng kết quả, không dùng side effect làm hợp đồng. |
| Chỉ kiểm chạy `parallel()` mà không kiểm combiner | Nguồn nhỏ có thể không chia nhánh | Thử trực tiếp identity/associativity và đối chiếu tuần tự/song song. |
| Cho nhiều nhánh dùng chung state mutable | Race, mất dữ liệu, kết quả khó lặp | `initializer` tạo state độc lập; chỉ gộp qua combiner. |
| Dùng phép trừ hay trung bình hai trung bình làm combiner | Có thể cho kết quả khác khi đổi cách chia | Gộp các đại lượng đủ thông tin, ví dụ `sum` và `count`. |
| Khẳng định số lần gọi callback bằng một số cố định khi chạy parallel | Lập lịch/chia nhánh là chi tiết triển khai | Kiểm thử kết quả và bất biến, không ép lịch gọi. |
| Kiểm thử nguồn vô hạn mà không có timeout | Một lỗi dừng sớm có thể treo suite | Đặt timeout ở test runner; có thêm ca finite để chẩn đoán. |

## 11. Bài tập mở rộng

**Bài 1 — Kiểm thử 0, 1, N đầu ra.** Viết Gatherer loại các số âm (`0` đầu ra cho số âm), giữ nguyên số không âm (`1` đầu ra), rồi thay đổi thành nhân đôi số dương (`2` đầu ra). Với `[-2, 0, 3]`, tự xác định đầu ra và kiểm bằng `toList()`.

Gợi ý: trong integrator, có thể không gọi `push` khi loại phần tử; nhưng nếu không phát gì mà còn muốn nhận phần tử kế tiếp, phải trả `true`.

**Bài 2 — Batch biên.** Với `fixedBatches(3)`, kiểm tra nguồn có `0`, `1`, `3`, `4`, `6` phần tử. Dự đoán số batch và danh sách phần tử từng batch. Vì sao chỉ kiểm `count()` chưa đủ?

**Bài 3 — Dừng sớm.** Thay `takeFirst(N)` bằng `takeUntilInclusive(predicate)`: phát cả phần tử đầu tiên thỏa predicate, sau đó dừng. Với `[1, 3, 5, 6, 8]` và predicate là số chẵn, đầu ra phải là `[1, 3, 5, 6]`.

```java
static Gatherer<Integer, ?, Integer> takeUntilEven() {
    return Gatherer.<Integer, Integer>ofSequential(
            (ignored, n, downstream) ->
                    downstream.push(n) && n % 2 != 0
    );
}
```

**Bài 4 — Ghép trạng thái sai.** Thử thay `CountState::merge` bằng phép chỉ giữ `left`. Dự đoán vì sao bản tuần tự có thể vẫn đúng, nhưng bản song song có thể sai; tạo kiểm thử **trực tiếp** để chắc chắn phát hiện lỗi ngay cả khi framework không chia nguồn.

**Bài 5 — Kiểm thử nguồn rỗng.** So sánh `Stream.empty().gather(duplicateEach())` với `Stream.empty().gather(countAndSum())`: vì sao cái đầu rỗng còn cái sau có thể có một `Summary(0, 0)`? Gợi ý: `finisher` quyết định có phát một giá trị tổng hợp cho nguồn rỗng hay không.

**Bài 6 — Khả năng song song.** Thiết kế Gatherer tính `min`, `max`, `count` của các số nguyên. Đặc tả trạng thái cho nhóm rỗng, cách gộp identity và associativity, sau đó kiểm thử với 1.000 số ở cả chế độ tuần tự và song song.

## 12. Ghi nhớ

- Gatherer không bị giới hạn tỷ lệ 1:1: kiểm thử **đầu vào rỗng, 0/1/nhiều đầu ra cho mỗi phần tử và finisher**.
- `gather` là intermediate operation: pipeline lười đến terminal operation. Không biến `peek` hoặc side effect quan sát được thành điều kiện đúng đắn của nghiệp vụ.
- `Integrator.integrate` trả `false` để dừng nhận thêm phần tử; `Downstream.push` trả `false` khi downstream không muốn nhận thêm. **Phải lan truyền tín hiệu dừng** và tránh đẩy tiếp sau khi bị từ chối.
- Gatherer có combiner phải dùng state độc lập và phép gộp thỏa **identity/associativity**; kiểm tra trực tiếp phép gộp rồi mới đối chiếu kết quả tuần tự/song song.
- Không kiểm thử dựa trên số thread, số lần gọi combiner hay lượng prefetch bất biến; kiểm tra **giá trị, thứ tự, số đầu ra và khả năng hoàn tất** trên dữ liệu đại diện.

**Tài liệu API tham khảo:** [Gatherer (JDK 24)](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/util/stream/Gatherer.html), [Gatherer.Integrator](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/util/stream/Gatherer.Integrator.html) và [Gatherer.Downstream](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/util/stream/Gatherer.Downstream.html).
