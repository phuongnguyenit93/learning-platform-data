# Kiểm chứng nguồn rỗng, cửa sổ chưa đủ, dừng sớm, ngoại lệ và thực thi song song

## 1. Vì sao phải kiểm chứng các trường hợp biên?

Một Gatherer tùy biến thường hoạt động đúng với dữ liệu mẫu thông thường nhưng có thể sai khi Stream rỗng, phần tử cuối không đủ tạo thành một nhóm, downstream dừng nhận kết quả, hoặc pipeline chạy song song. Các lỗi này thường xuất hiện ở `initializer`, `integrator`, `finisher` và `combiner` vì mỗi hàm có một thời điểm và trách nhiệm khác nhau.

`Gatherer<T, A, R>` là một intermediate operation: nhận phần tử kiểu `T`, dùng state kiểu `A` nếu cần, rồi phát ra phần tử kiểu `R` cho downstream. API có bốn thành phần:

| Thành phần | Trách nhiệm | Cần kiểm chứng |
|---|---|---|
| `initializer()` | Tạo state mới cho lần xử lý hoặc partition. | State ban đầu có hợp lệ khi không có phần tử không? |
| `integrator()` | Xử lý một phần tử, cập nhật state và có thể gọi `downstream.push`. | Có xử lý đúng phần tử cuối, downstream từ chối và điều kiện dừng không? |
| `combiner()` | Ghép hai state khi Gatherer được xử lý song song. | Ghép state có cho kết quả tương đương xử lý tuần tự không? |
| `finisher()` | Thực hiện bước cuối khi upstream kết thúc; có thể phát phần dữ liệu còn đệm. | Có xử lý state rỗng hoặc phần còn dư đúng không? |

Stream Gatherers được giới thiệu ở Java 22 dưới dạng preview, tiếp tục preview ở Java 23 và trở thành API chính thức từ Java 24 qua JEP 485. Các ví dụ trong bài dùng API ổn định từ Java 24 trở lên, không yêu cầu bật preview.

## 2. Trường hợp nguồn rỗng

Nguồn rỗng không gọi integrator vì không có phần tử để xử lý. Nếu Gatherer có state, `initializer()` tạo state ban đầu và `finisher()` có thể nhận state đó để hoàn tất. Vì vậy, finisher phải xử lý được tình huống chưa có phần tử nào được tích lũy.

Ví dụ Gatherer tìm giá trị lớn nhất và chỉ phát kết quả nếu đã nhận ít nhất một phần tử:

```java
import java.util.stream.Gatherer;
import java.util.stream.Stream;

static final class MaxState {
    boolean hasValue;
    int max;
}

static Gatherer<Integer, MaxState, Integer> maximum() {
    return Gatherer.ofSequential(
            MaxState::new,
            (state, value, downstream) -> {
                if (!state.hasValue || value > state.max) {
                    state.hasValue = true;
                    state.max = value;
                }
                return true;
            },
            (state, downstream) -> {
                if (state.hasValue) {
                    downstream.push(state.max);
                }
            });
}

public static void main(String[] args) {
    var emptyResult = Stream.<Integer>empty()
            .gather(maximum())
            .findFirst();

    var normalResult = Stream.of(4, 9, 2, 7)
            .gather(maximum())
            .findFirst();

    System.out.println(emptyResult);  // Optional.empty
    System.out.println(normalResult); // Optional[9]
}
```

`hasValue` phân biệt state rỗng với state có giá trị `0`. Không nên dùng một giá trị mặc định như `0` để đại diện cho “chưa có phần tử” nếu dữ liệu hợp lệ có thể âm hoặc bằng `0`.

Nếu Gatherer không có công việc cuối, có thể dùng finisher mặc định. Nếu finisher tự viết, hãy kiểm tra state trước khi đọc hoặc phát kết quả. Một Stream rỗng cũng không đồng nghĩa với việc phải phát ra một phần tử mặc định; điều đó phụ thuộc vào hợp đồng mà Gatherer muốn cung cấp.

## 3. Cửa sổ hoặc batch cuối chưa đủ phần tử

Một Gatherer gom theo nhóm thường chỉ phát nhóm khi đã đủ kích thước. Khi upstream kết thúc, phần còn lại có thể chưa đủ. Có hai chính sách thường gặp:

- Phát phần cuối chưa đủ như một nhóm nhỏ hơn.
- Bỏ phần cuối chưa đủ vì nghiệp vụ chỉ chấp nhận nhóm đầy đủ.

Chính sách phải được thể hiện rõ trong `finisher()`. Ví dụ dưới đây chọn cách phát phần còn dư:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.stream.Gatherer;
import java.util.stream.Stream;

static <T> Gatherer<T, List<T>, List<T>> batches(int batchSize) {
    if (batchSize < 1) {
        throw new IllegalArgumentException("batchSize phải lớn hơn 0");
    }

    return Gatherer.ofSequential(
            ArrayList<T>::new,
            (buffer, element, downstream) -> {
                buffer.add(element);

                if (buffer.size() < batchSize) {
                    return true;
                }

                boolean keepGoing = downstream.push(
                        Collections.unmodifiableList(new ArrayList<>(buffer)));
                buffer.clear();
                return keepGoing;
            },
            (buffer, downstream) -> {
                if (!buffer.isEmpty()) {
                    downstream.push(
                            Collections.unmodifiableList(new ArrayList<>(buffer)));
                }
            });
}

public static void main(String[] args) {
    var fullAndPartial = Stream.of(1, 2, 3, 4, 5, 6, 7, 8)
            .gather(batches(3))
            .toList();

    var shorterThanBatch = Stream.of(10, 20)
            .gather(batches(3))
            .toList();

    var empty = Stream.<Integer>empty()
            .gather(batches(3))
            .toList();

    System.out.println(fullAndPartial);   // [[1, 2, 3], [4, 5, 6], [7, 8]]
    System.out.println(shorterThanBatch); // [[10, 20]]
    System.out.println(empty);            // []
}
```

Trong ví dụ:

1. `initializer` tạo buffer rỗng.
2. `integrator` thêm từng phần tử vào buffer.
3. Khi buffer đủ `batchSize`, integrator phát một bản sao không thể sửa, xóa buffer và tiếp tục. Cách tạo bản sao này vẫn giữ được phần tử `null` nếu kiểu dữ liệu đầu vào cho phép.
4. Khi upstream kết thúc, `finisher` phát buffer còn dư nếu nó không rỗng.

Với nguồn rỗng, finisher nhận buffer rỗng và không phát gì. Với nguồn ngắn hơn batch size, finisher phát đúng một batch nhỏ. Nếu nghiệp vụ không chấp nhận batch thiếu, chỉ cần bỏ phần `downstream.push` trong finisher; khi đó phần dư sẽ bị loại bỏ.

## 4. Dừng sớm bằng giá trị `false` của integrator

`Gatherer.Integrator.integrate` trả về `boolean`:

- `true`: Gatherer muốn nhận phần tử tiếp theo.
- `false`: xem như không còn phần tử đầu vào nào cần chuyển cho integrator.

Đây là cơ chế short-circuit của Gatherer. Ví dụ sau phát ra số đầu tiên lớn hơn hoặc bằng ngưỡng rồi dừng:

```java
import java.util.stream.Gatherer;
import java.util.stream.Stream;

static Gatherer<Integer, Void, Integer> firstAtLeast(int threshold) {
    return Gatherer.ofSequential((unused, value, downstream) -> {
        if (value >= threshold) {
            downstream.push(value);
            return false;
        }

        return true;
    });
}

public static void main(String[] args) {
    var found = Stream.of(2, 5, 8, 12, 20)
            .gather(firstAtLeast(10))
            .toList();

    var notFound = Stream.of(2, 5, 8)
            .gather(firstAtLeast(10))
            .toList();

    var empty = Stream.<Integer>empty()
            .gather(firstAtLeast(10))
            .toList();

    System.out.println(found);    // [12]
    System.out.println(notFound); // []
    System.out.println(empty);    // []
}
```

Khi gặp `12`, integrator phát `12` rồi trả `false`, nên `20` không được chuyển tiếp cho integrator. Nếu không có phần tử phù hợp hoặc nguồn rỗng, Gatherer không phát kết quả.

Giá trị `false` không phải exception và cũng không có nghĩa là bỏ qua riêng phần tử hiện tại rồi tiếp tục. Nó yêu cầu kết thúc việc tích hợp các phần tử tiếp theo. Nếu muốn bỏ qua phần tử hiện tại nhưng tiếp tục, hãy trả về `true` mà không gọi `downstream.push`.

## 5. Phân biệt integrator tự dừng và downstream yêu cầu dừng

`downstream.push(result)` cũng trả về `boolean`:

- `true`: downstream vẫn sẵn sàng nhận thêm kết quả.
- `false`: downstream không muốn nhận thêm kết quả.

Nếu integrator có thể tiếp tục xử lý, hãy truyền tín hiệu này bằng cách trả về kết quả của `downstream.push`:

```java
static Gatherer<String, Void, String> normalize() {
    return Gatherer.ofSequential((unused, value, downstream) -> {
        String normalized = value.strip().toLowerCase();
        return downstream.push(normalized);
    });
}
```

Ví dụ này không tự quyết định dừng theo dữ liệu. Nó chỉ dừng khi downstream không muốn nhận thêm kết quả, chẳng hạn pipeline phía sau đã đủ phần tử do `limit` hoặc terminal operation short-circuit.

So sánh với Gatherer ở mục 4: `firstAtLeast` tự dừng khi gặp điều kiện nghiệp vụ, bất kể downstream còn muốn nhận thêm hay không. Khi cần cả hai điều kiện, hãy kết hợp chúng rõ ràng trong integrator.

Không giữ tham chiếu tới `Gatherer.Downstream` hoặc state để dùng sau khi phương thức integrator/finisher hiện tại kết thúc. Đây là các đối tượng thuộc lần gọi hiện tại, không phải callback để lưu trữ hoặc chuyển sang thread khác.

## 6. Xử lý ngoại lệ trong Gatherer

Các hàm của Gatherer có thể phát sinh unchecked exception. Ví dụ, dữ liệu không hợp lệ có thể khiến integrator ném `IllegalArgumentException`:

```java
static Gatherer<String, Void, String> nonBlankStrings() {
    return Gatherer.ofSequential((unused, value, downstream) -> {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("Chuỗi không được rỗng");
        }

        return downstream.push(value.strip());
    });
}

public static void main(String[] args) {
    try {
        var result = Stream.of(" Java ", "Gatherer", "   ")
                .gather(nonBlankStrings())
                .toList();
        System.out.println(result);
    } catch (IllegalArgumentException exception) {
        System.err.println("Không thể xử lý dữ liệu: " + exception.getMessage());
    }
}
```

Khi phần tử thứ ba không hợp lệ, terminal operation thất bại và ném exception ra phía gọi. Chương trình không nhận được danh sách kết quả hoàn chỉnh từ `toList()`. Các side effect đã xảy ra trước thời điểm lỗi, nếu có, không tự động được hoàn tác.

Nếu xử lý lỗi là một phần của nghiệp vụ, có thể chọn một trong các cách sau:

- Ném exception để từ chối toàn bộ pipeline.
- Phát một kiểu kết quả biểu diễn thành công/thất bại, chẳng hạn `Result<T>` hoặc `Optional<T>`, rồi để downstream quyết định.
- Bỏ qua phần tử lỗi và tiếp tục bằng cách không phát kết quả nhưng trả `true`, nếu việc bỏ qua phù hợp với yêu cầu.

Không nên bắt mọi `RuntimeException` rồi âm thầm bỏ qua. Cách đó có thể che giấu lỗi lập trình như `NullPointerException`, `IndexOutOfBoundsException` hoặc trạng thái bị hỏng. Nếu gọi API có checked exception bên trong lambda, hãy chuyển đổi theo quy ước phù hợp, ví dụ bọc `IOException` thành `UncheckedIOException`, rồi xử lý tại nơi thực hiện terminal operation.

Trong pipeline song song, một partition có thể đã thực hiện side effect trước khi partition khác ném exception. Không dựa vào thứ tự side effect hoặc giả định rằng exception sẽ hủy tức thì mọi công việc đang chạy.

## 7. Thực thi song song và vai trò của combiner

Một Gatherer có thể được xử lý song song khi nó cung cấp combiner phù hợp. Khi đó, Stream có thể chia nguồn thành các partition, tạo state độc lập cho từng partition, chạy integrator trên từng phần rồi dùng combiner để ghép state. Finisher chạy trên state đã ghép.

Nếu dùng `Gatherer.ofSequential(...)` hoặc để combiner là `Gatherer.defaultCombiner()`, Gatherer chỉ được đánh giá tuần tự. Gọi `.parallel()` trên Stream nguồn không làm Gatherer đó tự trở thành song song.

Ví dụ dưới đây tính giá trị lớn nhất bằng Gatherer có combiner:

```java
import java.util.stream.Gatherer;
import java.util.stream.Stream;

static final class ParallelMaxState {
    boolean hasValue;
    int max;
}

static Gatherer<Integer, ParallelMaxState, Integer> parallelMaximum() {
    return Gatherer.of(
            ParallelMaxState::new,
            (state, value, downstream) -> {
                if (!state.hasValue || value > state.max) {
                    state.hasValue = true;
                    state.max = value;
                }
                return true;
            },
            (left, right) -> {
                if (!left.hasValue) return right;
                if (!right.hasValue) return left;

                if (right.max > left.max) {
                    left.max = right.max;
                }
                return left;
            },
            (state, downstream) -> {
                if (state.hasValue) {
                    downstream.push(state.max);
                }
            });
}

public static void main(String[] args) {
    var result = Stream.of(5, 12, 3, 28, 7, 19)
            .parallel()
            .gather(parallelMaximum())
            .findFirst();

    System.out.println(result); // Optional[28]
}
```

Combiner chọn state có giá trị lớn nhất. Phép `max` có tính kết hợp và không phụ thuộc thứ tự ghép, nên kết quả vẫn đúng khi dữ liệu được chia thành nhiều partition. State của mỗi partition được tạo riêng; combiner chỉ ghép hai state đã xử lý xong.

Với nguồn rỗng, state cuối có `hasValue == false`, nên finisher không phát gì và `findFirst()` trả `Optional.empty()`.

## 8. Vì sao không phải Gatherer nào cũng có thể song song?

Một Gatherer xử lý theo thứ tự liên tiếp có thể cần biết phần tử cuối của partition bên trái trước khi xử lý phần tử đầu của partition bên phải. Ví dụ:

- Loại bỏ phần tử trùng liên tiếp.
- Gom batch có phần dư ở cuối.
- Cửa sổ trượt qua ranh giới hai partition.
- Tính chuỗi prefix mà mỗi kết quả phụ thuộc toàn bộ phần trước.

Để song song hóa đúng, combiner phải mang đủ thông tin biên để ghép hai phần. Chỉ nối hai buffer hoặc cộng hai bộ đếm không phải lúc nào cũng đúng. Nếu không thể mô tả phép ghép bảo toàn kết quả, hãy dùng `ofSequential`.

Một combiner tốt cần đáp ứng:

1. Mỗi state được tạo độc lập từ initializer.
2. Ghép state trái và phải cho kết quả tương đương xử lý tuần tự theo hợp đồng của Gatherer.
3. Cách ghép có tính kết hợp để kết quả không phụ thuộc cách Stream chia partition.
4. Không giữ lại state hoặc downstream ngoài thời gian gọi hàm.
5. Không chia sẻ mutable state toàn cục giữa các partition.

Parallel không đảm bảo nhanh hơn. Nếu combiner tốn kém, nguồn nhỏ hoặc công việc mỗi phần tử quá nhẹ, chi phí chia và ghép state có thể lớn hơn lợi ích.

### 8.1. Dừng sớm trong pipeline song song

Khi một integrator trả về `false` trong một partition, partition đó không nhận thêm phần tử. Những partition khác có thể đã bắt đầu xử lý hoặc đã phát kết quả. Theo hợp đồng Gatherer, khi xử lý song song, kết quả và state nằm sau partition dừng sớm có thể bị loại bỏ khi các state được ghép.

Vì vậy, dừng sớm trong Gatherer song song không phải cam kết rằng không có phần tử nào sau điều kiện dừng đã từng được xử lý. Nếu logic có side effect như ghi file, gửi email hoặc cập nhật cơ sở dữ liệu, không nên dựa vào thứ tự thực thi hoặc giả định chỉ có một partition chạm tới dữ liệu. Với yêu cầu “gặp phần tử đầu tiên theo encounter order rồi không thực hiện bất kỳ công việc nào sau nó”, Gatherer tuần tự thường dễ suy luận hơn.

## 9. Greedy Integrator và short-circuit

`Gatherer.Integrator.Greedy` là biến thể dành cho integrator cam kết không tự yêu cầu dừng. Nó chỉ có thể trả `false` khi downstream từ chối nhận thêm kết quả. Có thể tạo nó bằng `Gatherer.Integrator.ofGreedy(...)`.

```java
var integrator = Gatherer.Integrator.ofGreedy(
        (Void state, String value, Gatherer.Downstream<? super String> downstream) ->
                downstream.push(value.strip()));
```

Chỉ dùng greedy khi integrator luôn muốn xử lý phần tử tiếp theo và không có điều kiện nghiệp vụ khiến nó trả `false`. Nếu Gatherer cần tự dừng sau một số phần tử, gặp sentinel hoặc đạt ngưỡng, hãy dùng integrator thông thường. Khai báo greedy sai hợp đồng có thể khiến implementation tối ưu hóa dựa trên giả định không đúng.

## 10. Checklist kiểm chứng Gatherer tùy biến

Trước khi sử dụng Gatherer trong ứng dụng, hãy kiểm tra các trường hợp sau:

| Trường hợp | Câu hỏi cần trả lời | Kết quả mong đợi |
|---|---|---|
| Nguồn rỗng | Finisher có đọc state chưa khởi tạo dữ liệu không? | Không lỗi; phát kết quả theo đúng hợp đồng, thường là không phát gì. |
| Nguồn chỉ có một phần tử | Có xử lý được nhóm chưa đủ kích thước không? | Phát hoặc bỏ phần dư theo chính sách đã chọn. |
| Nguồn ngắn hơn batch/window | Finisher có xử lý buffer còn lại không? | Không mất hoặc phát dư dữ liệu ngoài ý muốn. |
| Nguồn vừa đủ kích thước | Integrator có xóa/reset buffer đúng lúc không? | Mỗi nhóm xuất hiện đúng một lần. |
| Nguồn có phần dư | Finisher có phát đúng một phần cuối không? | Không lặp nhóm cuối hoặc bỏ sót phần tử. |
| Downstream dừng | Integrator có relay `false` từ `push` không? | Không tiếp tục xử lý khi downstream đã từ chối. |
| Điều kiện dừng riêng | Integrator có trả `false` đúng thời điểm không? | Không nhận thêm phần tử sau điều kiện dừng. |
| Dữ liệu lỗi | Exception được xử lý ở đâu? | Pipeline thất bại rõ ràng hoặc phát kiểu lỗi theo hợp đồng. |
| Parallel | Combiner có ghép state đúng và có tính kết hợp không? | Kết quả tương đương chạy tuần tự. |
| State mutable | Có dùng chung state giữa các lần chạy hoặc partition không? | Mỗi lần khởi tạo có state riêng. |

Nên kiểm tra cả Stream rỗng, Stream có một phần tử, Stream có đúng một nhóm, Stream có nhiều nhóm và Stream có phần dư. Với Gatherer song song, so sánh kết quả tuần tự và song song trên nhiều kích thước dữ liệu, bao gồm cả nguồn rỗng và dữ liệu chỉ có một partition nhỏ.

## 11. Tài liệu tham khảo

- [Java SE 26 API: Gatherer](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Gatherer.html) — hợp đồng của initializer, integrator, combiner, finisher và các quy tắc xử lý song song.
- [Java SE 26 API: Gatherer.Integrator](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Gatherer.Integrator.html) — giá trị trả về của integrator và factory methods `of`/`ofGreedy`.
- [Java SE 26 API: Gatherer.Downstream](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Gatherer.Downstream.html) — hợp đồng của `push` và khả năng nhận thêm kết quả.
- [Oracle Java SE 26: Stream Gatherers](https://docs.oracle.com/en/java/javase/26/core/stream-gatherers.html) — ví dụ tạo Gatherer, dừng sớm và xử lý song song.
- [JEP 485: Stream Gatherers](https://openjdk.org/jeps/485) — trạng thái chính thức từ Java 24.
