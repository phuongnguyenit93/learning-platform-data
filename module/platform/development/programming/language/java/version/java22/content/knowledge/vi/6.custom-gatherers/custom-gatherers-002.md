# Initializer, integrator, combiner và finisher trong vòng đời xử lý

`Gatherer` là intermediate operation của Stream API, cho phép xây dựng phép biến đổi luồng dữ liệu có trạng thái và có thể phát ra nhiều kết quả cho mỗi phần tử đầu vào. Một Gatherer tùy biến thường được mô tả bằng bốn hàm: `initializer`, `integrator`, `combiner` và `finisher`. Bốn hàm này phối hợp để tạo trạng thái, xử lý phần tử, kết hợp trạng thái khi chạy song song và hoàn tất kết quả.

Gatherers xuất hiện lần đầu dưới dạng preview trong Java 22 qua JEP 461, tiếp tục preview trong Java 23 qua JEP 473 và trở thành API chính thức từ Java 24 qua JEP 485. Bài này dùng API ổn định từ Java 24 trở lên, phù hợp với Java hiện đại; các ví dụ không yêu cầu `--enable-preview`.

## 1. Vòng đời của một Gatherer

Một Gatherer biến đổi các phần tử kiểu `T` của luồng đầu vào thành các phần tử kiểu `R` của luồng đầu ra. Nếu phép biến đổi cần nhớ dữ liệu giữa các lần xử lý, nó sử dụng trạng thái trung gian kiểu `A`.

```text
                 initializer()
                       |
                       v
                state kiểu A
                       |
                       v
 input T ---> integrator(state, T, downstream)
                       |
               +-------+-------+
               |               |
          push output R    update state A
               |               |
               +-------<-------+
                       |
              hết input / dừng sớm
                       |
             combiner(state, state)
                 (nếu parallel)
                       |
                       v
              finisher(state, downstream)
                       |
                       v
                 output kiểu R
```

Trong xử lý tuần tự, có thể hình dung một trạng thái được khởi tạo, nhận lần lượt các phần tử qua integrator rồi được chuyển cho finisher. Khi xử lý song song, thư viện có thể chia input thành các partition độc lập. Mỗi partition có trạng thái riêng; sau khi tích hợp xong, các trạng thái được gộp bằng combiner rồi mới hoàn tất bằng finisher.

| Thành phần | Nhiệm vụ | Thời điểm sử dụng |
| --- | --- | --- |
| `initializer()` | Tạo trạng thái trung gian mới kiểu `A`. | Khi bắt đầu một lần xử lý hoặc một partition cần state. |
| `integrator()` | Nhận state và một input `T`, cập nhật state hoặc gửi output `R` xuống downstream. | Với từng phần tử đầu vào cho đến khi hết input hoặc integrator yêu cầu dừng. |
| `combiner()` | Gộp hai state của hai partition thành một state. | Khi Gatherer được đánh giá song song. |
| `finisher()` | Thực hiện công việc cuối cùng, có thể phát ra thêm output từ state. | Sau khi upstream hoàn tất; trong parallel, sau khi các state đã được kết hợp. |

Các hàm này có thể được cung cấp thông qua factory `Gatherer.of(...)` hoặc `Gatherer.ofSequential(...)`. Không phải Gatherer nào cũng cần cả bốn hàm tùy biến: các hàm mặc định thể hiện rằng phép biến đổi không cần state, không hỗ trợ parallel hoặc không có bước hoàn tất riêng.

## 2. Initializer: tạo trạng thái cho một lần xử lý

`initializer()` trả về `Supplier<A>`, dùng để tạo state mà integrator sẽ đọc và cập nhật. State có thể là một đối tượng mutable như `ArrayList`, bộ đếm, bộ tổng hợp thống kê hoặc cấu trúc dữ liệu chuyên biệt.

Ví dụ, một Gatherer tính tổng và số lượng phần tử có thể dùng một state đơn giản:

```java
static final class AverageState {
    long count;
    long sum;
}

static Gatherer<Integer, AverageState, Double> average() {
    return Gatherer.of(
            AverageState::new,
            (state, value, downstream) -> {
                state.count++;
                state.sum += value;
                return true;
            },
            (left, right) -> {
                left.count += right.count;
                left.sum += right.sum;
                return left;
            },
            (state, downstream) -> {
                if (state.count > 0) {
                    downstream.push((double) state.sum / state.count);
                }
            }
    );
}
```

Trong ví dụ này, `AverageState::new` tạo một state mới. Với stream tuần tự, Gatherer cần một state cho lần xử lý. Với stream song song, mỗi partition được xử lý độc lập và cần state riêng để các integrator không cùng cập nhật một đối tượng mutable.

Không tạo state một lần ở bên ngoài rồi trả về cùng một đối tượng cho mọi lần gọi initializer:

```java
import java.util.function.Supplier;

// Không nên: mọi lần gọi đều trả về cùng một đối tượng mutable.
AverageState shared = new AverageState();
Supplier<AverageState> unsafeInitializer = () -> shared;
```

Hãy tạo state mới trong initializer. Không lưu state vào field dùng chung của Gatherer, không để state thoát khỏi vòng đời callback và không chia sẻ state giữa các partition.

### 2.1. Khi không cần state

Nếu mỗi phần tử có thể được xử lý độc lập mà không cần ghi nhớ dữ liệu trước đó, dùng dạng stateless. Có thể tạo Gatherer chỉ từ integrator:

```java
import java.util.Locale;

static Gatherer<String, ?, String> uppercase() {
    return Gatherer.of((state, value, downstream) ->
            downstream.push(value.toUpperCase(Locale.ROOT))
    );
}
```

Factory này dùng state kiểu `Void` và initializer mặc định. Không cần tự tạo một đối tượng state rỗng. Đây là dạng phù hợp cho phép biến đổi stateless; nếu phép biến đổi chỉ cần ánh xạ một-một, `Stream.map(...)` thường đơn giản hơn.

## 3. Integrator: xử lý từng phần tử và điều khiển luồng

`integrator()` trả về một `Gatherer.Integrator<A,T,R>`. Hàm `integrate` nhận ba đối số:

- `state`: state hiện tại do initializer hoặc combiner tạo ra.
- `element`: phần tử `T` tiếp theo từ upstream.
- `downstream`: đối tượng đại diện cho bước tiếp theo trong pipeline, nhận các output kiểu `R`.

Integrator có thể cập nhật state, phát ra không kết quả, một kết quả hoặc nhiều kết quả cho một input. Vì vậy, Gatherer có thể thực hiện những phép biến đổi khó biểu diễn bằng `map`, `filter` hoặc `flatMap` đơn giản.

Ví dụ dưới đây chỉ phát ra số chẵn:

```java
static Gatherer<Integer, ?, Integer> evenNumbers() {
    return Gatherer.of((state, value, downstream) -> {
        if (value % 2 != 0) {
            return true; // Bỏ qua phần tử này, tiếp tục đọc input.
        }

        return downstream.push(value);
    });
}
```

Giá trị trả về của integrator là `boolean`:

- `true`: Gatherer có thể tiếp tục nhận phần tử tiếp theo.
- `false`: integrator không muốn nhận thêm phần tử; thư viện xử lý như thể không còn phần tử nào để chuyển cho integrator.

`downstream.push(output)` cũng trả về `boolean`. `true` cho biết downstream vẫn có thể nhận output tiếp theo; `false` cho biết downstream không nhận thêm phần tử. Nếu integrator không thể tiếp tục khi downstream từ chối output, hãy truyền trạng thái đó bằng cách trả về `false`, như ví dụ trên.

`downstream.isRejecting()` cho biết theo cách best-effort rằng downstream đã biết chắc nó không muốn nhận thêm phần tử. Với cùng một Downstream instance, sau khi phương thức trả về `true`, nó không nên trả về `false` ở lần gọi sau. Đây là tín hiệu để tránh thực hiện công việc không cần thiết, không phải lời hứa rằng downstream luôn có thể dự đoán trước việc từ chối.

### 3.1. Một input có thể tạo nhiều output

Integrator không bị giới hạn ở một lần `push` cho mỗi input. Ví dụ, mỗi số nguyên có thể tạo ra cả dạng gốc và dạng bình phương:

```java
static Gatherer<Integer, ?, Integer> originalAndSquare() {
    return Gatherer.of((state, value, downstream) ->
            downstream.push(value)
                    && downstream.push(value * value)
    );
}
```

Nếu downstream từ chối output đầu tiên, biểu thức `&&` dừng và integrator trả về `false`. Nếu downstream nhận output đầu tiên nhưng từ chối output thứ hai, integrator cũng trả về `false`. Cách này truyền tín hiệu dừng về phía upstream.

### 3.2. Khi nào dùng `Integrator.Greedy`?

Nếu integrator không tự quyết định dừng sớm mà luôn tiêu thụ input cho đến khi downstream từ chối, có thể biểu diễn hợp đồng đó bằng `Gatherer.Integrator.Greedy`. Thông tin này giúp thư viện tối ưu vì nó biết integrator không tự short-circuit.

```java
static Gatherer<Integer, ?, Integer> increment() {
    Gatherer.Integrator.Greedy<Void, Integer, Integer> integrator =
            Gatherer.Integrator.ofGreedy(
                    (state, value, downstream) -> downstream.push(value + 1)
            );

    return Gatherer.of(integrator);
}
```

Chỉ khai báo integrator là greedy khi nó thực sự tiêu thụ toàn bộ input được chuyển đến nó, ngoại trừ trường hợp downstream không muốn nhận thêm output. Nếu integrator có điều kiện dừng riêng, hãy dùng `Integrator` thông thường và trả về `false` đúng thời điểm.

## 4. Combiner: gộp state khi xử lý song song

`combiner()` trả về `BinaryOperator<A>`, nhận hai state và tạo ra một state kết hợp. Đây là phần quyết định một Gatherer có thể được đánh giá song song hay chỉ tuần tự.

Khi stream chạy song song, thư viện có thể chia input thành các partition. Mỗi partition có state riêng, và integrator xử lý phần tử trong partition đó. Khi hai partition hoàn tất, combiner nhận hai state tương ứng và gộp chúng. Các lần gộp tiếp theo có thể kết hợp nhiều partition thành một state cuối.

Ví dụ trong phần initializer dùng `AverageState`. Combiner cộng `count` và `sum` của state bên phải vào state bên trái rồi trả về state đã gộp:

```java
(left, right) -> {
    left.count += right.count;
    left.sum += right.sum;
    return left;
}
```

Sau khi hai state được đưa vào combiner, chúng không được chuyển trở lại integrator. State được combiner trả về có thể tiếp tục được gộp với state khác hoặc được chuyển đến finisher.

### 4.1. Điều kiện để combiner đúng

Combiner phải bảo toàn ý nghĩa của phép biến đổi khi kết hợp kết quả của các partition. Nếu phép toán phụ thuộc thứ tự encounter, cần gộp state theo cách bảo toàn thứ tự đó. Không thể chỉ nối hoặc cộng hai state tùy ý nếu kết quả sẽ khác với xử lý tuần tự.

Đối với phép tổng hợp số lượng và tổng như `AverageState`, phép gộp có tính kết hợp nên có thể kết hợp state của các partition. Với phép biến đổi cần nhớ ranh giới giữa các phần tử kề nhau, cần thiết kế state và combiner cẩn thận hơn.

Không nên dùng biến mutable dùng chung trong integrator để thay cho combiner. Cách đó tạo tranh chấp dữ liệu giữa các thread và phá vỡ tính độc lập của partition.

### 4.2. Không có combiner nghĩa là chỉ xử lý tuần tự

Nếu Gatherer không cung cấp combiner tùy biến, mặc định nó dùng `Gatherer.defaultCombiner()`. Combiner mặc định đánh dấu rằng Gatherer chỉ được đánh giá tuần tự.

Khi biết trước phép biến đổi không thể kết hợp state đúng cách, hãy khai báo rõ ý định bằng `Gatherer.ofSequential(...)`:

```java
static Gatherer<Integer, List<Integer>, List<Integer>> fixedWindows(int size) {
    if (size <= 0) {
        throw new IllegalArgumentException("size must be positive");
    }

    return Gatherer.ofSequential(
            ArrayList::new,
            (buffer, value, downstream) -> {
                buffer.add(value);

                if (buffer.size() == size) {
                    List<Integer> window = List.copyOf(buffer);
                    buffer.clear();
                    return downstream.push(window);
                }

                return true;
            },
            (buffer, downstream) -> {
                if (!buffer.isEmpty()) {
                    downstream.push(List.copyOf(buffer));
                }
            }
    );
}
```

Gatherer trên giữ các phần tử đang tạo thành một cửa sổ trong `buffer`. Khi đủ `size` phần tử, integrator gửi một bản sao bất biến xuống downstream rồi xóa buffer. Nếu stream kết thúc khi buffer chưa đủ kích thước, finisher gửi cửa sổ cuối cùng có ít phần tử hơn.

Phép chia cửa sổ phụ thuộc thứ tự phần tử và ranh giới nhóm. Không có combiner được thiết kế để gộp các buffer của partition mà vẫn bảo toàn chính xác cửa sổ tuần tự, vì vậy ví dụ chọn `ofSequential`. Gọi Gatherer này trên một stream song song không biến nó thành phép xử lý song song.

## 5. Finisher: hoàn tất state và phát ra kết quả cuối

`finisher()` nhận state cuối cùng và downstream. Finisher chạy sau khi Gatherer đã xử lý hết input; trong xử lý song song, finisher nhận state sau khi các partition được kết hợp.

Finisher thường dùng để:

- Phát ra phần dữ liệu còn đệm nhưng chưa đủ điều kiện phát ra trong integrator.
- Tạo kết quả tổng hợp cuối từ state, chẳng hạn tổng, trung bình, min/max hoặc báo cáo.
- Đóng gói state thành một hoặc nhiều output cuối cùng.
- Thực hiện bước hoàn tất mà chỉ có thể thực hiện khi đã biết không còn input.

Ví dụ trong Gatherer `average()` chỉ phát ra trung bình sau khi đã đọc hết input:

```java
(state, downstream) -> {
    if (state.count > 0) {
        downstream.push((double) state.sum / state.count);
    }
}
```

Nếu input rỗng, state có `count == 0`, do đó không phát ra kết quả. Việc chọn phát ra giá trị mặc định, `OptionalDouble` hay không phát output là quyết định của thiết kế Gatherer.

Finisher có kiểu `BiConsumer<A, Downstream<? super R>>`, nên không trả trực tiếp kết quả qua `return`. Nó phát ra kết quả bằng `downstream.push(...)`. Finisher không được giữ lại state hoặc downstream để dùng sau khi callback kết thúc.

Nếu không cần hành động cuối, Gatherer dùng `Gatherer.defaultFinisher()`. Finisher mặc định thể hiện rằng Gatherer không có end-of-stream hook; thư viện có thể bỏ qua việc gọi nó.

## 6. Ví dụ đầy đủ: tổng hợp thống kê với cả bốn thành phần

Ví dụ dưới đây tạo một Gatherer nhận `Double`, tính số lượng, tổng, nhỏ nhất, lớn nhất và trung bình. Kết quả được phát ra đúng một lần ở finisher. Vì có combiner gộp được các thống kê từng partition, Gatherer có thể chạy trên parallel stream.

```java
import java.util.DoubleSummaryStatistics;
import java.util.List;
import java.util.stream.Gatherer;

record Summary(long count, double sum, double min,
               double max, double average) { }

static Gatherer<Double, DoubleSummaryStatistics, Summary> summarize() {
    return Gatherer.of(
            // 1. Initializer: tạo state riêng cho mỗi lần xử lý/partition.
            DoubleSummaryStatistics::new,

            // 2. Integrator: đưa từng input vào state.
            (stats, value, downstream) -> {
                stats.accept(value);
                return true;
            },

            // 3. Combiner: gộp thống kê của hai partition.
            (left, right) -> {
                left.combine(right);
                return left;
            },

            // 4. Finisher: phát ra kết quả tổng hợp cuối cùng.
            (stats, downstream) -> {
                if (stats.getCount() > 0) {
                    downstream.push(new Summary(
                            stats.getCount(),
                            stats.getSum(),
                            stats.getMin(),
                            stats.getMax(),
                            stats.getAverage()
                    ));
                }
            }
    );
}

public static void main(String[] args) {
    List<Double> values = List.of(2.0, 4.0, 6.0, 8.0);

    List<Summary> summaries = values.parallelStream()
            .gather(summarize())
            .toList();

    System.out.println(summaries);
}
```

Kết quả là một danh sách có một `Summary` với `count = 4`, `sum = 20`, `min = 2`, `max = 8` và `average = 5`. Stream được phép xử lý các partition độc lập, sau đó kết hợp các `DoubleSummaryStatistics` trước khi finisher tạo `Summary`.

`parallelStream()` chỉ cho phép pipeline được đánh giá song song; nó không bảo đảm rằng mọi Gatherer sẽ chạy song song hoặc nhanh hơn. Với tập dữ liệu nhỏ hay combiner tốn kém, xử lý tuần tự có thể hiệu quả hơn.

## 7. Các quy tắc vòng đời cần tuân thủ

### 7.1. State thuộc về một lần xử lý

State được tạo từ initializer hoặc combiner. Không tự tạo state rồi đưa vào integrator, combiner hoặc finisher từ một nguồn khác. Thư viện chuyển state qua các callback theo hợp đồng của Gatherer.

Khi một state đã được chuyển cho combiner hoặc finisher, state đó sẽ không được chuyển lại cho integrator. Vì vậy, không tiếp tục cập nhật state cũ sau khi đã kết hợp hoặc hoàn tất.

### 7.2. Không giữ reference đến state hoặc downstream

Không capture, giữ lại hoặc công khai reference đến state hay `Gatherer.Downstream` lâu hơn thời gian callback nhận chúng. Không chuyển các reference này sang thread khác. Nếu cần giữ dữ liệu để dùng sau, hãy sao chép giá trị cần thiết sang cấu trúc do ứng dụng sở hữu, tuân thủ quy tắc an toàn bộ nhớ và đồng bộ của ứng dụng.

### 7.3. Short-circuit có thể ảnh hưởng partition khác

Khi integrator trả `false`, thư viện xem như không còn input nào cần chuyển cho integrator đó. Trong đánh giá song song, một số partition phía sau có thể đã được xử lý trước khi phát hiện điều kiện dừng ở partition trước. Output và state của phần dữ liệu nằm sau điểm dừng có thể bị loại bỏ.

Vì vậy, tránh đặt tác dụng phụ không thể hoàn tác vào integrator của Gatherer song song, chẳng hạn ghi file hoặc gửi giao dịch ra hệ thống bên ngoài. Ưu tiên xử lý dữ liệu trong state và phát output qua downstream.

### 7.4. Chỉ dùng Greedy khi không tự short-circuit

`Gatherer.Integrator.Greedy` cho biết integrator không tự khởi tạo short-circuit; nó chỉ có thể truyền tiếp tín hiệu rằng downstream không nhận thêm phần tử. Khi integrator có điều kiện dừng dựa trên state hoặc input, hãy dùng `Integrator` thông thường.

### 7.5. Các hàm accessor phải ổn định về ngữ nghĩa

Các lần gọi `initializer()`, `integrator()`, `combiner()` và `finisher()` phải cung cấp những hàm có ngữ nghĩa tương đương. Không để kết quả phụ thuộc vào việc accessor được gọi bao nhiêu lần hoặc theo thứ tự nào.

## 8. Chọn factory phù hợp

| Factory | Khi dùng | Khả năng xử lý |
| --- | --- | --- |
| `Gatherer.of(initializer, integrator, combiner, finisher)` | Gatherer có state và có thể gộp state đúng cách. | Có thể parallelize. |
| `Gatherer.of(integrator)` | Gatherer stateless, không cần finisher riêng. | Có thể parallelize. |
| `Gatherer.of(integrator, finisher)` | Gatherer stateless nhưng cần hành động cuối. | Có thể parallelize. |
| `Gatherer.ofSequential(initializer, integrator)` | Gatherer có state nhưng không có cách gộp state đúng. | Chỉ tuần tự. |
| `Gatherer.ofSequential(initializer, integrator, finisher)` | Gatherer có state, cần finisher và chỉ xử lý tuần tự. | Chỉ tuần tự. |

Nếu phép biến đổi đã có trong Stream API, hãy ưu tiên các operation tiêu chuẩn như `map`, `filter`, `flatMap`, `mapMulti`, `distinct` hoặc `sorted`. Nếu cần windowing hoặc scan phổ biến, kiểm tra các factory có sẵn trong `Gatherers` trước khi tự viết. Custom Gatherer phù hợp khi phép biến đổi cần trạng thái hoặc quy tắc phát output riêng mà các operation có sẵn không biểu đạt tốt.

## Ghi nhớ

- `initializer` tạo state mới; trong parallel, mỗi partition được xử lý độc lập với state riêng.
- `integrator` nhận state và input, cập nhật state hoặc gửi output bằng `downstream.push`; trả `false` để dừng nhận input.
- `combiner` gộp hai state. Nếu không cung cấp combiner tùy biến, Gatherer mặc định chỉ xử lý tuần tự.
- `finisher` nhận state cuối và có thể gửi thêm output sau khi upstream kết thúc.
- `downstream.push` trả `false` khi downstream không nhận thêm output; integrator nên truyền tín hiệu dừng về upstream.
- State và downstream không được giữ lại sau callback hoặc chia sẻ tùy tiện giữa các thread.
- Stream Gatherers là preview trong Java 22 và 23, đã trở thành API chính thức từ Java 24. Code hiện đại dùng API stable, không bật preview.

## Tài liệu tham khảo

- [JEP 461: Stream Gatherers (Preview, JDK 22)](https://openjdk.org/jeps/461)
- [JEP 473: Stream Gatherers (Second Preview, JDK 23)](https://openjdk.org/jeps/473)
- [JEP 485: Stream Gatherers (Final, JDK 24)](https://openjdk.org/jeps/485)
- [Java SE 27 API — `Gatherer`](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/stream/Gatherer.html)
- [Java SE 27 API — `Gatherer.Downstream`](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/stream/Gatherer.Downstream.html)
- [Java SE 27 API — `Gatherer.Integrator.Greedy`](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/stream/Gatherer.Integrator.Greedy.html)
- [Oracle Core Libraries Guide — Stream Gatherers](https://docs.oracle.com/en/java/javase/24/core/stream-gatherers.html)
