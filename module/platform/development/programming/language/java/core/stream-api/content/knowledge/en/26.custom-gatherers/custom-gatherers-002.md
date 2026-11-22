# Quản lý trạng thái riêng cho mỗi phân đoạn xử lý

Trong Java Stream API, `filter` và `map` thường được mô tả bằng các hàm không lưu trạng thái. Tuy nhiên, có những bài toán cần ghi nhớ dữ liệu giữa các phần tử: đếm số bản ghi đã gặp, tính tổng lũy kế, gom các phần tử liên tiếp thành một nhóm, hoặc tạo báo cáo chỉ khi nguồn kết thúc. **Stream Gatherers** cung cấp một cơ chế xây dựng phép toán trung gian có trạng thái, thay vì phải đưa biến đếm hoặc `ArrayList` dùng chung ra ngoài pipeline.

Chủ đề này có một điểm dễ hiểu sai: **trạng thái của Gatherer không nhất thiết là một đối tượng duy nhất cho cả Stream**. Với Gatherer có thể song song hóa, hệ thống có thể chia nguồn thành nhiều **phân đoạn xử lý** (*partitions*), tạo trạng thái độc lập cho từng phân đoạn, rồi **kết hợp các trạng thái**. Số lượng phân đoạn, thread thực thi và thời điểm kết hợp là những chi tiết mà chương trình không nên giả định cố định.

Bài **“Quản lý trạng thái riêng cho mỗi phân đoạn xử lý”** thuộc chương **Xây dựng Gatherer tùy biến** của module **JAVA_STREAM_API**. Ta sẽ liên hệ các khái niệm với pipeline lazy, `reduce`, `collect`, `Spliterator` và Stream song song, đồng thời làm rõ giới hạn về trạng thái, thứ tự, tài nguyên, kết thúc sớm và tính đúng đắn.

> **Mốc JDK:** `java.util.stream.Gatherer`, `Gatherers` và `Stream.gather` là API chuẩn từ **Java 24**. Java 22 và 23 từng cung cấp phiên bản preview, nhưng mã ví dụ dưới đây hướng đến **JDK 24+**, không phụ thuộc preview. Cần kiểm tra cả JDK build lẫn runtime triển khai.

## 1. Mục tiêu sau bài học

Hoàn thành bài này, bạn cần làm được những việc sau:

1. Giải thích kiểu tổng quát `Gatherer<T, A, R>` và vai trò của trạng thái `A`.
2. Phân biệt **trạng thái cục bộ của phân đoạn**, **trạng thái toàn pipeline** và **biến chia sẻ bên ngoài**.
3. Biết khi nào dùng `Gatherer.ofSequential(...)`, khi nào dùng `Gatherer.of(...)` với `combiner`.
4. Thiết kế `initializer` tạo **đối tượng trạng thái mới**, không trả một đối tượng mutable dùng chung.
5. Viết `integrator` có thể cập nhật trạng thái và phát kết quả qua `Downstream.push`.
6. Viết `combiner` bảo toàn dữ liệu khi hai phân đoạn được gộp, không dựa vào lịch thực thi cố định.
7. Dùng `finisher` để phát kết quả cuối, đồng thời tôn trọng yêu cầu dừng của downstream.
8. Kiểm thử trạng thái độc lập giữa các lần chạy và kết quả tương đương giữa tuần tự/song song.

## 2. Gatherer là gì trong một pipeline Stream?

Một Gatherer biến `Stream<T>` thành `Stream<R>`. Khác với `map` thông thường chỉ tạo một giá trị cho mỗi phần tử, Gatherer có thể tạo **không, một hoặc nhiều đầu ra**, duy trì trạng thái và phát kết quả cuối ở bước hoàn tất.

~~~java
import java.util.List;
import java.util.stream.Gatherers;

List<List<Integer>> windows = List.of(1, 2, 3, 4, 5)
    .stream()
    .gather(Gatherers.windowFixed(2))
    .toList();

System.out.println(windows);
// [[1, 2], [3, 4], [5]]
~~~

`Gatherers.windowFixed(2)` là Gatherer có sẵn, gom các phần tử thành cửa sổ tối đa hai phần tử. Nó có trạng thái để giữ những phần tử đang chờ tạo cửa sổ. Bài này đi xa hơn: **tự quản lý trạng thái** cho một Gatherer và quyết định cách xử lý khi nguồn được chia.

Các thành phần cơ bản của một Gatherer tùy chỉnh là:

~~~text
Nguồn Stream<T>
      |
      v
Gatherer<T, A, R>
  initializer: tạo A
  integrator: (A, T, Downstream<R>) -> boolean
  combiner:   (A, A) -> A
  finisher:   (A, Downstream<R>) -> void
      |
      v
Stream<R> -> filter/map/limit/collect/...
~~~

Đây là một **intermediate operation**, không phải một terminal collector. Sau `gather(...)`, pipeline có thể tiếp tục với `filter`, `limit`, `map` hoặc `collect`.

## 3. Ba tham số kiểu T, A và R

Giao diện tổng quát có dạng:

~~~java
Gatherer<T, A, R>
~~~

| Tham số | Vai trò | Ví dụ |
|---|---|---|
| `T` | Loại phần tử đầu vào | `Integer`, `Payment`, `String` |
| `A` | Loại **trạng thái trung gian**, có thể mutable | `CounterState`, `HashMap<String, Long>` |
| `R` | Loại phần tử phát ra downstream | `Summary`, `Run<String>`, `List<Integer>` |

Ví dụ, một Gatherer nhận số nguyên, lưu số lượng/tổng trong `CounterState` rồi phát một `Summary` có kiểu:

~~~java
Gatherer<Integer, CounterState, Summary>
~~~

`A` **không phải** số lượng phân đoạn, tên thread hay “kết quả cuối” mặc định. Nó chỉ là kiểu trạng thái mà các hàm của Gatherer sử dụng. Một phép xử lý song song có thể tạo **nhiều instance `A` khác nhau**.

Với một số factory method, kiểu `A` có thể được che bằng wildcard:

~~~java
Gatherer<Integer, ?, Summary> gatherer = ...;
~~~

Ẩn kiểu trạng thái trong API công khai là thực hành tốt khi người dùng Gatherer chỉ cần biết **đầu vào và đầu ra**, không cần phụ thuộc cấu trúc bộ chứa nội bộ.

## 4. Một phân đoạn xử lý là gì?

Hãy hình dung nguồn có tám phần tử:

~~~text
Nguồn: [2, 4, 3, 1, 5, 8, 6, 7]
~~~

Khi chạy song song, hệ thống *có thể* chia nguồn thành nhiều phân đoạn:

~~~text
                [2, 4, 3, 1, 5, 8, 6, 7]
                     /           \
              [2, 4, 3, 1]     [5, 8, 6, 7]
                  |                 |
             State A1           State A2
           count=4,sum=10     count=4,sum=26
                  \                /
                   combiner(A1, A2)
                         |
                   count=8,sum=36
                         |
                      finisher
                         |
                    Summary(8,36)
~~~

**Quan trọng:** sơ đồ chỉ là một cách phân chia *có thể xảy ra*. Java không bảo đảm đúng hai phân đoạn, chia chính giữa, mỗi phân đoạn gắn với một thread cố định hoặc `combiner` được gọi đúng một lần.

Một phân đoạn là **đơn vị tích lũy** do framework quản lý. Nó không phải “trang dữ liệu”, “giao dịch database” hoặc “nhóm nghiệp vụ” trừ khi thuật toán và nguồn thực sự định nghĩa như vậy.

### 4.1. Trạng thái riêng khác với ThreadLocal

| Trạng thái | Ý nghĩa | Có nên dùng làm `A`? |
|---|---|---|
| Đối tượng từ `initializer.get()` | Trạng thái của một phân đoạn Gatherer | **Có**, đây là mô hình chuẩn |
| Biến instance chứa state dùng chung ở ngoài | Nhiều lần chạy có thể cùng sửa một đối tượng | **Không**, nếu state đó được dùng làm bộ chứa mutable của Gatherer |
| Biến `static` mutable | Tồn tại xuyên các lần gọi và có thể xuyên nhiều thread | Không thích hợp để giữ trạng thái tích lũy của phân đoạn |
| `ThreadLocal` | Gắn với thread, không phải phân đoạn logic | Không thay thế cho `initializer` |
| Giá trị `T` đang xử lý | Một phần tử đầu vào | Không đồng nghĩa trạng thái tích lũy `A` |

Các phân đoạn có thể được xử lý và gộp bởi những thread khác nhau. Đừng đặt giả định “một thread = một trạng thái Gatherer”.

## 5. Hợp đồng bốn hàm của Gatherer

Java 24 mô tả Gatherer qua bốn thành phần:

| Thành phần | Chữ ký khái quát | Nhiệm vụ |
|---|---|---|
| `initializer()` | `Supplier<A>` | Tạo trạng thái ban đầu cho một phân đoạn |
| `integrator()` | `Integrator<A, T, R>` | Nhận từng phần tử, cập nhật trạng thái và có thể phát đầu ra |
| `combiner()` | `BinaryOperator<A>` | Kết hợp trạng thái từ các phân đoạn đã xử lý |
| `finisher()` | `BiConsumer<A, Downstream<? super R>>` | Có thể phát đầu ra sau khi nguồn được xử lý xong |

Đối với một Gatherer **không có trạng thái**, `initializer` mặc định có thể biểu thị không cần bộ chứa. Đối với Gatherer **tuần tự**, combiner mặc định là một chỉ dấu rằng thao tác này **không được đánh giá theo cách phân đoạn song song**.

### 5.1. Vòng đời khái quát

~~~mermaid
flowchart TD
    A["Nguồn Stream"] --> B{"Gatherer cho phép song song?"}
    B -->|Không| C["Một luồng tích lũy logic"]
    B -->|Có| D["Các phân đoạn độc lập"]
    C --> E["initializer → integrator*"]
    D --> F["initializer riêng → integrator*"]
    F --> G["combiner hợp nhất state"]
    E --> H["finisher (nếu có)"]
    G --> H
    H --> I["Đầu ra downstream"]
~~~

Dấu `*` ở đây có nghĩa integrator được gọi nhiều lần tùy lượng dữ liệu cần xử lý. Đây là sơ đồ khái niệm, không mô tả số thread và số lần gọi cụ thể.

### 5.2. Ranh giới sở hữu state

Theo hợp đồng của Gatherer:

- State đưa vào `integrator` phải là state do `initializer` hoặc `combiner` tạo ra trước đó.
- Với đánh giá song song, các phân đoạn được xử lý độc lập; `combiner` chỉ gộp sau khi việc tích lũy tương ứng đã hoàn tất.
- Sau khi một state được chuyển đến `combiner` hoặc `finisher`, framework không đưa chính state đó vào `integrator` thêm lần nữa.
- Các hàm không được **giữ hoặc để lộ tham chiếu** đến state hoặc `Downstream` để thread khác dùng sau thời gian gọi hàm.
- Khi integrator trả `false`, việc tích lũy không tiếp tục theo cùng cách; đây là yêu cầu kết thúc sớm, không phải giá trị “bỏ qua phần tử”.

Điều đó cho phép một state **mutable cục bộ** mà không cần khóa quanh mọi trường, miễn nó không bị công bố ra ngoài hoặc dùng sai hợp đồng.

## 6. Chọn ofSequential hay of có combiner?

Java 24 cung cấp factory method để tránh phải viết toàn bộ lớp implements `Gatherer`.

### Gatherer có trạng thái, chỉ xử lý tuần tự

~~~java
Gatherer.ofSequential(
    initializer,
    integrator,
    finisher
)
~~~

Có thể bỏ `finisher` nếu không có việc cần làm ở cuối.

### Gatherer có trạng thái và cho phép song song hóa

~~~java
Gatherer.of(
    initializer,
    integrator,
    combiner,
    finisher
)
~~~

**Khác biệt then chốt:** `combiner` không phải tham số “tùy thêm để chạy nhanh hơn”. Nó là một **hợp đồng ngữ nghĩa** chứng minh các trạng thái cục bộ có thể được ghép mà không làm thay đổi kết quả mong đợi.

Nếu bài toán có trạng thái phụ thuộc toàn bộ **thứ tự liên tiếp** và không biết ghép các ranh giới phân đoạn một cách đúng đắn, **đừng viết combiner giả**. Chọn `ofSequential` trước để giữ tính đúng.

### 6.1. Một Stream parallel vẫn có thể chứa Gatherer tuần tự

~~~java
List<Integer> source = List.of(1, 2, 3, 4, 5);

List<Integer> output = source.parallelStream()
    .gather(mySequentialGatherer)
    .toList();
~~~

Đoạn này minh họa một biến Gatherer đã có tên `mySequentialGatherer`. Nếu Gatherer có `defaultCombiner()` (ví dụ được tạo bằng `ofSequential`), **phần đánh giá Gatherer đó** không được phân đoạn/song song theo hợp đồng.

Không nên suy diễn rằng mọi bước còn lại trong pipeline luôn chạy trên một thread, hoặc `parallelStream()` bị “đổi vĩnh viễn” thành một kiểu Stream khác. Hãy phân biệt **chế độ pipeline** với **khả năng song song hóa của một Gatherer cụ thể**.

## 7. Ví dụ 1: gom các chuỗi liên tiếp bằng trạng thái tuần tự

Bài toán: nguồn có nhiều mã trạng thái lặp liên tiếp, cần nén thành **giá trị + số lần xuất hiện liên tiếp** (*run-length encoding*).

~~~text
Đầu vào: [A, A, B, B, B, A, C, C]
Đầu ra: [Run(A,2), Run(B,3), Run(A,1), Run(C,2)]
~~~

Đây là ví dụ lý tưởng để hiểu state:

- `previous`: giá trị của nhóm liên tiếp hiện tại.
- `count`: số phần tử đã thấy trong nhóm đó.
- `present`: đã nhận phần tử đầu tiên hay chưa.

State phải được **tạo mới cho mỗi phép đánh giá**, không được đặt trong một danh sách/biến toàn cục dùng chung.

### 7.1. Chương trình Java 24+ hoàn chỉnh

Tạo file `SequentialRunsDemo.java`:

~~~java
import java.util.List;
import java.util.Objects;
import java.util.stream.Gatherer;
import java.util.stream.Stream;

public class SequentialRunsDemo {

    record Run<T>(T value, long count) {}

    static <T> Gatherer<T, ?, Run<T>> consecutiveRuns() {

        class State {
            boolean present;
            T previous;
            long count;
        }

        return Gatherer.<T, State, Run<T>>ofSequential(
            State::new,
            Gatherer.Integrator.ofGreedy(
                (state, value, downstream) -> {
                    if (!state.present) {
                        state.present = true;
                        state.previous = value;
                        state.count = 1L;
                        return true;
                    }

                    if (Objects.equals(state.previous, value)) {
                        state.count = Math.addExact(state.count, 1L);
                        return true;
                    }

                    // Gặp giá trị khác: hoàn tất nhóm cũ.
                    if (!downstream.push(
                            new Run<>(state.previous, state.count))) {
                        return false;
                    }

                    // Bắt đầu nhóm tiếp theo.
                    state.previous = value;
                    state.count = 1L;
                    return true;
                }
            ),
            (state, downstream) -> {
                // Chỉ phát nhóm cuối nếu downstream còn nhận dữ liệu.
                if (state.present && !downstream.isRejecting()) {
                    downstream.push(
                        new Run<>(state.previous, state.count)
                    );
                }
            }
        );
    }

    public static void main(String[] args) {
        List<Run<String>> result = Stream.of(
                "A", "A", "B", "B", "B", "A", "C", "C"
            )
            .gather(consecutiveRuns())
            .toList();

        System.out.println(result);
        // [Run[value=A, count=2], Run[value=B, count=3],
        //  Run[value=A, count=1], Run[value=C, count=2]]

        List<Run<String>> empty = Stream.<String>empty()
            .gather(consecutiveRuns())
            .toList();

        System.out.println(empty); // []
    }
}
~~~

### 7.2. Đọc sự thay đổi của state

| Phần tử đầu vào | `previous` trước | `count` trước | Hành động | Đầu ra ngay lúc đó |
|---|---|---:|---|---|
| A | Chưa có | 0 | Bắt đầu nhóm A | Không |
| A | A | 1 | Tăng số đếm | Không |
| B | A | 2 | Phát Run(A,2), bắt đầu B | Run(A,2) |
| B | B | 1 | Tăng số đếm | Không |
| B | B | 2 | Tăng số đếm | Không |
| A | B | 3 | Phát Run(B,3), bắt đầu A | Run(B,3) |
| C | A | 1 | Phát Run(A,1), bắt đầu C | Run(A,1) |
| C | C | 1 | Tăng số đếm | Không |
| Kết thúc | C | 2 | `finisher` phát nhóm cuối | Run(C,2) |

Không có `finisher`, nhóm cuối chưa được phát vì **không còn phần tử mới** để kích hoạt việc đóng nhóm trước đó.

### 7.3. Tại sao cần biến present?

Một nguồn có thể hợp lệ chứa `null` nếu hợp đồng nguồn cho phép. Khi ấy, `previous == null` **không đủ** để phân biệt “chưa có phần tử” và “giá trị nhóm hiện tại là null”.

`present` đóng vai trò sentinel logic; `Objects.equals(a, b)` cho phép so sánh hai giá trị null an toàn. Tùy nghiệp vụ, bạn cũng có thể lọc bỏ null từ trước, nhưng đó là **một chính sách dữ liệu khác**.

### 7.4. Vì sao dùng ofSequential?

Hãy hình dung nguồn `[A, A, A, A]` bị chia:

~~~text
Phân đoạn 1: [A, A]  → Run(A,2)
Phân đoạn 2: [A, A]  → Run(A,2)

Kết quả mong muốn toàn cục: Run(A,4)
~~~

Nếu mỗi phân đoạn **phát Run(A,2) ngay trước khi kết hợp**, một `combiner` chỉ gộp số đếm cuối không thể “rút lại” hai kết quả đã phát xuống downstream. Muốn song song hóa đúng, phải thiết kế cách **giữ dữ liệu biên** và trì hoãn/hiệu chỉnh đầu ra, thay vì gắn một combiner cộng số đếm đơn giản.

Vì bài toán phụ thuộc vào **các phần tử kề nhau**, `ofSequential` là lựa chọn rõ ràng và đúng nghĩa cho phiên bản đầu tiên.

## 8. Greedy integrator và kết thúc sớm

Trong ví dụ trên, ta dùng:

~~~java
Gatherer.Integrator.ofGreedy((state, element, downstream) -> {
    // ...
    return true;
})
~~~

`Integrator.Greedy` biểu thị integrator **không chủ động short-circuit**: nó xử lý mọi đầu vào được chuyển đến, ngoại trừ trường hợp downstream không còn muốn nhận thêm phần tử.

Nếu không biết chắc thuật toán có phải greedy, đừng đánh dấu greedy chỉ để kỳ vọng tối ưu. Một integrator cần dừng khi đạt điều kiện nghiệp vụ phải dùng hợp đồng `Integrator` phù hợp và trả `false` khi muốn ngừng tiếp tục tích lũy.

### 8.1. Downstream.push trả boolean có nghĩa gì?

~~~java
boolean wantsMore = downstream.push(result);
~~~

- `true`: downstream còn chấp nhận đầu ra.
- `false`: downstream đã biết không cần nhận thêm; những lần `push` sau không còn được chấp nhận.

Một ví dụ thực tế là phần sau của pipeline dùng `limit(2)`. Sau khi nhận đủ hai kết quả, downstream có thể từ chối các kết quả tiếp theo. Vì thế integrator ở mục 7 **trả `false` nếu `push` trả `false`**, thay vì tiếp tục tính và phát vô ích.

`downstream.isRejecting()` là phép kiểm tra **best-effort** để biết downstream đã ngừng nhận. Nếu nó trả `true`, không nên tiếp tục phát đầu ra. Nếu nó trả `false`, chưa chắc downstream sẽ nhận mọi lần `push` tiếp theo; luôn kiểm tra kết quả của `push` khi cần xử lý chuỗi đầu ra.

### 8.2. Không dùng side effect làm thước đo số phần tử đã xử lý

~~~java
List<Run<String>> firstTwo = Stream.of(
        "A", "A", "B", "B", "C", "C"
    )
    .gather(consecutiveRuns())
    .limit(2)
    .toList();
~~~

Kết quả là hai run đầu tiên theo encounter order. Nhưng **không nên kiểm thử số lần gọi integrator, số thread hoặc số lần initializer bằng biến đếm ngoài pipeline**, vì hệ thống có thể dừng sớm hoặc dùng cách thực thi khác để thỏa hợp đồng.

## 9. Vì sao combiner không đơn thuần là cộng hai con số?

Với một thuật toán có state cục bộ, `combiner` cần trả lời:

> Nếu phân đoạn trái đã được xử lý độc lập và phân đoạn phải cũng vậy, làm sao ghép **toàn bộ ý nghĩa của hai kết quả trạng thái** để có cùng đầu ra như khi duyệt liên tục?

Một số thuật toán dễ kết hợp:

- Đếm số phần tử: cộng hai số đếm.
- Tính tổng: cộng hai tổng (cần chính sách overflow).
- Tìm giá trị lớn nhất: lấy max của hai giá trị có mặt.
- Đếm theo khóa: cộng số đếm cùng khóa từ hai Map.

Một số thuật toán khó kết hợp hơn:

- Đếm số lần thay đổi **giữa các phần tử liên tiếp**: cần biết giá trị ở biên phải/trái.
- Cửa sổ trượt: cần giữ đủ tiền tố/hậu tố để tái tạo cửa sổ băng qua ranh giới phân đoạn.
- Đánh số thứ tự toàn cục: mỗi phân đoạn chưa biết offset của những phần đứng trước.
- Phát lũy kế ở từng phần tử: các giá trị đã phát ở phân đoạn phải có thể cần cộng thêm tổng của phân đoạn trái.

Nếu chưa chứng minh được cách gộp đúng cho mọi cách phân đoạn, **không nên công bố Gatherer là parallelizable**.

## 10. Ví dụ 2: thống kê với trạng thái riêng của từng phân đoạn

Bài toán: nhận các số nguyên **không âm** và tạo đúng **một bản thống kê cuối cùng** gồm:

- `count`: số phần tử.
- `sum`: tổng các giá trị.
- `evenCount`: số phần tử chẵn.

Vì ba chỉ số đều có thể gộp bằng phép cộng, đây là một ví dụ phù hợp để viết `Gatherer.of(initializer, integrator, combiner, finisher)`.

### 10.1. Chương trình Java 24+ hoàn chỉnh

Lưu thành `PartitionStateDemo.java`:

~~~java
import java.util.List;
import java.util.Objects;
import java.util.stream.Gatherer;
import java.util.stream.Stream;

public class PartitionStateDemo {

    record Summary(long count, long sum, long evenCount) {}

    static Gatherer<Integer, ?, Summary> summarizeNonnegative() {

        class State {
            long count;
            long sum;
            long evenCount;
        }

        return Gatherer.<Integer, State, Summary>of(
            // Mỗi phân đoạn được cấp một state độc lập.
            State::new,

            // Tích lũy từ từng phần tử; chưa phát đầu ra.
            Gatherer.Integrator.ofGreedy(
                (state, element, downstream) -> {
                    Objects.requireNonNull(element, "element");
                    if (element < 0) {
                        throw new IllegalArgumentException(
                            "Chỉ chấp nhận số không âm");
                    }

                    state.count = Math.addExact(state.count, 1L);
                    state.sum = Math.addExact(
                        state.sum, element.longValue());

                    if ((element & 1) == 0) {
                        state.evenCount = Math.addExact(
                            state.evenCount, 1L);
                    }
                    return true;
                }
            ),

            // Ghép hai state đã xử lý độc lập.
            (left, right) -> {
                left.count = Math.addExact(left.count, right.count);
                left.sum = Math.addExact(left.sum, right.sum);
                left.evenCount =
                    Math.addExact(left.evenCount, right.evenCount);
                return left;
            },

            // Sau khi gộp xong, phát đúng một Summary.
            (state, downstream) -> {
                if (!downstream.isRejecting()) {
                    downstream.push(
                        new Summary(
                            state.count, state.sum, state.evenCount)
                    );
                }
            }
        );
    }

    public static void main(String[] args) {
        List<Integer> source = List.of(2, 4, 3, 1, 5, 8);

        List<Summary> sequential = source.stream()
            .gather(summarizeNonnegative())
            .toList();

        List<Summary> parallel = source.parallelStream()
            .gather(summarizeNonnegative())
            .toList();

        System.out.println(sequential);
        // [Summary[count=6, sum=23, evenCount=3]]

        System.out.println(parallel);
        // [Summary[count=6, sum=23, evenCount=3]]

        if (!sequential.equals(parallel)) {
            throw new AssertionError(
                "Kết quả tuần tự và song song khác nhau");
        }
    }
}
~~~

### 10.2. Vì sao combiner có thể sửa left?

`left` và `right` là **hai trạng thái cục bộ** mà framework đưa cho combiner sau khi các phân đoạn đã được tích lũy. Trong ví dụ, combiner chuyển tổng từ `right` vào `left` và trả `left`.

Điều này hợp lệ vì chúng không được sử dụng như hai bộ chứa đồng thời sau khi gộp; framework chỉ dùng **state kết hợp** theo hợp đồng. Nhưng không được đưa `left` vào biến `static`, lưu tham chiếu `right` ở nơi khác hoặc trả chúng ra qua Stream để mã bên ngoài tiếp tục sửa.

### 10.3. Vì sao không phát một Summary cho từng phân đoạn?

Trong ví dụ, integrator **chỉ tích lũy**, còn finisher mới `push` Summary. Khi chạy song song, các state cục bộ có thể gộp hoàn toàn trước khi phát **một kết quả cuối**.

Nếu integrator đẩy `Summary` cho từng phần tử hoặc từng phân đoạn rồi combiner cố gắng cộng ở cuối, các kết quả đã phát có thể không còn phản ánh thống kê **toàn bộ nguồn**. Một `combiner` của state **không tự sửa được dữ liệu đã phát** xuống downstream.

### 10.4. Tại sao dùng Math.addExact?

Với đầu vào đã được xác thực **không âm**, việc cộng dồn dễ kiểm tra hơn và `Math.addExact` sẽ ném `ArithmeticException` nếu `long` bị tràn. Đây là chính sách **báo lỗi thay vì âm thầm tràn số**.

Việc giữ đầu vào không âm cũng tránh trường hợp các tổng trung gian của dữ liệu dấu hỗn hợp có thể tràn theo một cách nhóm nhưng không tràn theo cách nhóm khác. Trong hệ thống có dữ liệu tùy ý và yêu cầu tổng chính xác không phụ thuộc cách chia, cân nhắc `BigInteger` hoặc chính sách số học được thiết kế rõ ràng.

### 10.5. Điểm then chốt của ví dụ

Ta **không tự chia List**, không gọi `new Thread` và không viết đồng bộ cho từng trường state. Framework Stream quản lý các phân đoạn; Gatherer cung cấp **cách tạo trạng thái**, **cách cập nhật từng state**, **cách gộp state** và **cách phát kết quả**.

Tuy nhiên, `parallelStream()` không bảo đảm chương trình thực tế luôn tạo hơn một state: hệ thống có thể chọn cách thực thi phù hợp với workload. Bài kiểm tra phải dựa vào **kết quả**, không dựa vào số lần supplier được gọi.

## 11. Bất biến (invariants) của state giúp chứng minh tính đúng

Trong ví dụ `PartitionStateDemo`, ta định nghĩa với mỗi phân đoạn đã xử lý một tập phần tử `P`:

~~~text
state.count     = số phần tử của P
state.sum       = tổng giá trị của P
state.evenCount = số phần tử chẵn của P
~~~

State mới từ initializer đại diện cho tập rỗng:

~~~text
count = 0, sum = 0, evenCount = 0
~~~

Sau mỗi lần integrator xử lý phần tử không âm `x`, cả ba bất biến vẫn đúng:

~~~text
count'     = count + 1
sum'       = sum + x
evenCount' = evenCount + (x chẵn ? 1 : 0)
~~~

Khi hai phân đoạn rời nhau `P1` và `P2` được gộp:

~~~text
count(P1 ∪ P2)     = count(P1) + count(P2)
sum(P1 ∪ P2)       = sum(P1) + sum(P2)
evenCount(P1 ∪ P2) = evenCount(P1) + evenCount(P2)
~~~

Vì phép cộng các bộ ba này **có tính kết hợp** trên miền giá trị hợp lệ, nhiều cách phân nhóm và gộp khác nhau cho cùng kết quả cuối, miễn không có overflow và không có thay đổi ngoài ý muốn đối với dữ liệu.

Đây là cơ sở thực sự để gọi `of(...)` với một combiner, chứ không phải vì “hàm này nhìn có vẻ chạy song song được”.

## 12. Ví dụ 3: trạng thái Map riêng cho từng phân đoạn

Bài toán khác: đếm số lần xuất hiện của mỗi từ khóa. Một `HashMap` là state tự nhiên cho mỗi phân đoạn; combiner gộp số đếm cùng khóa.

### 12.1. Chương trình Java 24+ hoàn chỉnh

~~~java
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.stream.Gatherer;

public class PartitionFrequencyDemo {

    static Gatherer<String, ?, Map<String, Long>> frequencies() {
        return Gatherer
            .<String, HashMap<String, Long>, Map<String, Long>>of(
                HashMap::new,

                Gatherer.Integrator.ofGreedy(
                    (counts, word, downstream) -> {
                        if (word == null || word.isBlank()) {
                            throw new IllegalArgumentException(
                                "Từ khóa không hợp lệ");
                        }

                        counts.merge(
                            word, 1L,
                            (a, b) -> Math.addExact(a, b)
                        );
                        return true;
                    }
                ),

                (left, right) -> {
                    right.forEach((word, amount) ->
                        left.merge(
                            word, amount,
                            (a, b) -> Math.addExact(a, b)
                        )
                    );
                    return left;
                },

                (counts, downstream) -> {
                    if (!downstream.isRejecting()) {
                        // Sao chép để không làm lộ Map tích lũy mutable.
                        downstream.push(Map.copyOf(counts));
                    }
                }
            );
    }

    public static void main(String[] args) {
        List<String> words = List.of(
            "java", "stream", "java", "api", "stream", "java"
        );

        List<Map<String, Long>> reports = words.parallelStream()
            .gather(frequencies())
            .toList();

        System.out.println(reports.size()); // 1

        Map<String, Long> expected = Map.of(
            "java", 3L,
            "stream", 2L,
            "api", 1L
        );

        if (!reports.get(0).equals(expected)) {
            throw new AssertionError("Kết quả đếm sai");
        }

        System.out.println(reports.get(0).get("java")); // 3
    }
}
~~~

### 12.2. Ba quyết định kỹ thuật cần chú ý

**Một là supplier `HashMap::new`.** Mỗi state ban đầu phải là một Map **mới**, không phải Map từ biến static hoặc object được tạo sẵn bên ngoài.

**Hai là merge theo khóa.** `left.putAll(right)` **sai** nếu có khóa xuất hiện ở hai phân đoạn vì nó sẽ ghi đè số đếm của `left`. `Map.merge` với phép cộng mới giữ đúng tổng số lần xuất hiện.

**Ba là snapshot ở finisher.** `Map.copyOf(counts)` tạo Map kết quả không thể sửa, tránh để caller nắm tham chiếu đến `HashMap` mutable dùng để tích lũy.

`Map.copyOf` không bảo đảm thứ tự duyệt khóa. Nếu đầu ra cần sắp xếp theo tên từ khóa, hãy chọn một cấu trúc kết quả thích hợp hoặc sắp xếp ở bước hiển thị; đừng tin rằng `HashMap` có thứ tự ổn định.

### 12.3. Khi nào không nên tự viết Gatherer đếm từ?

Nếu chỉ cần **một báo cáo tần suất cuối cùng**, cách ngắn gọn hơn thường là terminal collector:

~~~java
Map<String, Long> counts = words.parallelStream()
    .collect(java.util.stream.Collectors.groupingBy(
        word -> word,
        java.util.stream.Collectors.counting()
    ));
~~~

Cả hai có thể đáp ứng cùng một yêu cầu đơn giản. Gatherer đáng dùng khi cần **một thao tác trung gian có thể kết hợp tiếp** hoặc hành vi tùy chỉnh đặc biệt, không phải vì mọi phép tổng hợp đều cần chuyển thành Gatherer.

**Thiết kế theo mục tiêu:** nếu không cần `Stream.gather(...)`, đừng tăng độ phức tạp chỉ để thể hiện API mới.

## 13. Vì sao một state không được chia sẻ giữa nhiều phân đoạn?

Đây là ví dụ **sai**:

~~~java
class CounterState {
    long count;
}

CounterState shared = new CounterState();

// Sai: mọi lời gọi initializer đều trả đúng một object.
// Không dùng:
// Gatherer.of(
//     () -> shared,
//     (state, value, downstream) -> { state.count++; return true; },
//     (left, right) -> left,
//     (state, downstream) -> downstream.push(state.count)
// );
~~~

Nếu hai phân đoạn cùng nhận `shared`, chúng cùng cập nhật `count`. Điều này vừa tạo **race condition** vừa phá hợp đồng tích lũy độc lập. Combiner còn có thể nhận hai tham chiếu **đến cùng object**, khiến việc cộng/gộp bị đếm trùng.

Sửa bằng supplier thực sự tạo instance mới:

~~~java
CounterState::new
~~~

Và giữ state ở phạm vi được framework chuyển đến callback:

~~~java
(state, value, downstream) -> {
    state.count++;
    return true;
}
~~~

Việc khóa `synchronized` quanh `state.count++` **không phải giải pháp đúng cho initializer dùng chung**, vì bản thân thiết kế state không còn độc lập và combiner vẫn không biết ranh giới các phần dữ liệu. Hãy sửa **hợp đồng sở hữu state**, không chỉ che race bằng một khóa.

## 14. Combiner phải hợp nhất đúng và không giả định thứ tự kết hợp

Một combiner đúng phải phù hợp với ý nghĩa dữ liệu được gộp.

Ví dụ với số đếm:

~~~java
(left, right) -> {
    left.count += right.count;
    return left;
}
~~~

Về toán học, phép cộng số đếm có tính kết hợp. Nhưng với phép nối hoặc kết hợp có phụ thuộc thứ tự, cần xem kỹ **encounter order** và thứ tự kết hợp mà thuật toán cho phép.

### 14.1. Không dùng phép trừ như combiner tích lũy

~~~java
// Sai cho việc gộp tổng:
(left, right) -> {
    left.sum -= right.sum;
    return left;
}
~~~

Phép trừ không có tính kết hợp: `(a - b) - c` có thể khác `a - (b - c)`. Nguồn chia theo cách khác có thể làm kết quả thay đổi.

### 14.2. Không bỏ dữ liệu của một phân đoạn

~~~java
// Sai nếu cả hai phân đoạn đều có dữ liệu cần giữ:
(left, right) -> left
~~~

Nếu `right` có phần tử đã tích lũy, việc trả `left` mà không gộp là **mất dữ liệu**. Nó chỉ đúng với những thuật toán có hợp đồng đặc biệt chứng minh rằng trạng thái right không cần thiết.

### 14.3. Phân đoạn rỗng cũng phải hợp lệ

Một state vừa tạo từ initializer phải đại diện cho **phần tử chưa nhận**. Khi gộp với state rỗng, kết quả phải giống state không rỗng về mặt quan sát:

~~~text
combine(empty, A) ≡ A
combine(A, empty) ≡ A
~~~

Dấu `≡` có nghĩa tương đương về kết quả nghiệp vụ, không đòi hỏi cùng một object reference.

### 14.4. Không phụ thuộc combiner chạy đúng một lần

Với ba phân đoạn `A`, `B` và `C`, việc gộp có thể thực hiện theo nhiều cây khác nhau. Nếu thuật toán chỉ đúng cho một cách nhóm cố định, nó **chưa đáp ứng yêu cầu song song hóa**.

Khi cần kết quả phụ thuộc thứ tự, phải chứng minh cách ghép đó vẫn bảo toàn đúng thứ tự và thông tin biên. Không dùng biến đếm ngoài để gán “số phân đoạn thứ nhất, thứ hai...”.

## 15. Bài toán khó: tổng lũy kế qua ranh giới phân đoạn

Giả sử muốn tạo tổng lũy kế:

~~~text
Đầu vào: [1, 2, 3, 4]
Đầu ra:  [1, 3, 6, 10]
~~~

Nếu chia nguồn thành:

~~~text
Đoạn trái: [1, 2] → [1, 3], state.sum = 3
Đoạn phải: [3, 4] → [3, 7], state.sum = 7
~~~

Kết quả đúng cho đoạn phải trong toàn nguồn phải là `[6, 10]`, vì mỗi giá trị cần cộng **offset 3** từ đoạn trái. Nếu nhánh phải đã `push` `[3,7]` rồi, combiner chỉ cộng `3+7` ở cuối **không thể tự sửa các phần tử đã phát**.

Đây là lý do không nên viết “scan song song” bằng cách gắn combiner cộng state mà bỏ qua ngữ nghĩa đầu ra.

Nếu chưa triển khai được chiến lược scan song song đúng (chẳng hạn tính tổng từng khối, tính offset rồi áp dụng lên kết quả khối), hãy dùng Gatherer tuần tự hoặc built-in thích hợp:

~~~java
import java.util.List;
import java.util.stream.Gatherers;

List<Integer> prefixSums = List.of(1, 2, 3, 4)
    .stream()
    .gather(Gatherers.scan(
        () -> 0,
        Integer::sum
    ))
    .toList();

System.out.println(prefixSums); // [1, 3, 6, 10]
~~~

`Gatherers.scan` là một lựa chọn chuẩn cho phép cộng lũy kế có thứ tự. Ví dụ sử dụng số nhỏ nên không xét overflow; với dữ liệu lớn, chọn `long` và quy tắc số học phù hợp.

## 16. Trạng thái phân đoạn khác với cửa sổ nghiệp vụ

Một lỗi thiết kế phổ biến là muốn “mỗi 100 bản ghi tạo một lô” rồi coi **mỗi phân đoạn parallel** là một lô 100 bản ghi.

Điều này sai vì:

- Framework có thể chia nguồn thành những phân đoạn có kích thước khác nhau.
- Một phân đoạn có thể chứa ít hơn hoặc nhiều hơn 100 phần tử.
- Một phép toán short-circuit có thể khiến một số phần không bao giờ được duyệt.
- Cách chia phụ thuộc `Spliterator`, đặc tính nguồn và việc điều phối.

Nếu nghiệp vụ cần **cửa sổ kích thước 100 theo encounter order**, hãy dùng một thuật toán định nghĩa **ranh giới cửa sổ từ dữ liệu và thứ tự**, chẳng hạn:

~~~java
List<List<Integer>> batches = java.util.stream.IntStream
    .range(0, 7)
    .boxed()
    .gather(java.util.stream.Gatherers.windowFixed(3))
    .toList();

System.out.println(batches);
// [[0, 1, 2], [3, 4, 5], [6]]
~~~

Kích thước cửa sổ `3` ở đây là quy tắc nghiệp vụ, **không phải** số phần tử tình cờ nằm trong một phân đoạn nội bộ.

## 17. Đừng dùng ThreadLocal để mô phỏng state của Gatherer

Cách viết sau thường xuất phát từ giả định “mỗi thread cần một biến đếm”:

~~~java
ThreadLocal<long[]> counter =
    ThreadLocal.withInitial(() -> new long[1]);
~~~

Ngay cả khi mỗi thread có một mảng riêng, nó vẫn **không đồng nhất với phân đoạn xử lý**:

1. Một thread có thể thực thi nhiều tác vụ/phân đoạn.
2. State của một phân đoạn có thể được bàn giao cho các pha kết hợp.
3. `ThreadLocal` không cung cấp một combiner đúng nghĩa cho các giá trị tích lũy.
4. Trong các thread pool tồn tại lâu, quên dọn state có thể giữ dữ liệu/tài nguyên quá lâu.

Chỉ dùng `ThreadLocal` cho những nhu cầu có **ngữ nghĩa thực sự gắn với thread**, không dùng thay `initializer` của Gatherer. Với bài toán Stream, state nên được framework tạo, truyền và gộp theo đúng hợp đồng Gatherer.

## 18. Tránh làm lộ trạng thái mutable xuống downstream

Giả sử state giữ một danh sách:

~~~java
class State {
    final java.util.ArrayList<String> values =
        new java.util.ArrayList<>();
}
~~~

Đoạn finisher dưới đây có thể làm **lộ danh sách đang được sở hữu bởi state**:

~~~java
// Không nên nếu caller cần kết quả độc lập, không thể sửa:
// (state, downstream) -> downstream.push(state.values);
~~~

Một biến thể an toàn hơn:

~~~java
(state, downstream) -> {
    if (!downstream.isRejecting()) {
        downstream.push(List.copyOf(state.values));
    }
}
~~~

`List.copyOf` tạo một danh sách không thể sửa và **không chấp nhận phần tử null**. Nếu state có thể chứa null, hãy chọn cách sao chép phù hợp với chính sách null, chẳng hạn một `ArrayList` mới kèm wrapper không thể sửa.

Điểm quan trọng là **không truyền state nguyên trạng cho mã ngoài tiếp tục cập nhật**. Một bản snapshot giúp tránh việc kết quả của người dùng thay đổi do các phép xử lý nội bộ sau đó, đồng thời làm rõ quyền sở hữu dữ liệu.

## 19. Quản lý bộ nhớ và tài nguyên khi state lớn

State phân đoạn làm cho nhiều thuật toán dễ diễn đạt, nhưng **không miễn phí**.

| Thiết kế state | Chi phí/rủi ro | Gợi ý |
|---|---|---|
| Chỉ vài số đếm/tổng | Nhẹ, dễ ghép | Phù hợp với bài toán aggregation |
| `HashMap` theo khóa | Bộ nhớ tăng theo số khóa của từng phân đoạn | Cần giới hạn cardinality và gộp đúng |
| `ArrayList` lưu mọi phần tử | Bộ nhớ có thể gần bằng số phần tử nguồn, nhân với các bộ chứa trung gian | Chỉ lưu khi thật sự cần |
| Bộ nhớ đệm cửa sổ | Cần tính giới hạn cửa sổ và xử lý phần còn lại | Dùng thuật toán window có invariant rõ |
| State chứa resource I/O | Dễ khó quản lý thời điểm đóng và ngoại lệ | Tách trách nhiệm và xác định lifecycle |

### 19.1. Nhiều phân đoạn có thể tạo nhiều bộ chứa

Với parallel Gatherer, framework có thể tạo nhiều state rồi hợp nhất. Nếu mỗi state khởi tạo sẵn một mảng rất lớn hoặc mở một kết nối, tổng tài nguyên sử dụng có thể tăng mạnh dù số phần tử nguồn không lớn.

Hãy ưu tiên **state nhỏ**, cấp phát theo nhu cầu khi phù hợp và tránh giả định chỉ có một initializer.

### 19.2. Finisher không phải nơi thay thế toàn bộ quản lý tài nguyên

`finisher` là hook hoàn tất của Gatherer; nếu nguồn là `Files.lines(...)`, việc **đóng nguồn** vẫn thuộc trách nhiệm của nơi sở hữu Stream:

~~~java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

Path path = Path.of("events.txt");

try (Stream<String> lines = Files.lines(
        path, StandardCharsets.UTF_8)) {
    // lines.gather(...).collect(...)
}
~~~

Terminal operation không tự động đóng `Files.lines`. Đừng kỳ vọng `finisher` của Gatherer thay thế `try-with-resources` cho file nguồn.

### 19.3. Không lưu Downstream để phát kết quả sau này

Một Gatherer **không được giữ tham chiếu `Downstream`** để gọi lại từ thread khác hoặc một callback bất đồng bộ sau khi lời gọi `integrator`/`finisher` đã kết thúc.

Ví dụ kiểu thiết kế sai:

~~~java
// Sai về lifetime:
// savedDownstream = downstream;
// executor.submit(() -> savedDownstream.push(value));
~~~

Nếu muốn tích hợp xử lý bất đồng bộ, hãy thiết kế một mô hình có quản lý luồng dữ liệu và vòng đời riêng. `Downstream` của Gatherer không phải kênh gửi tin nhắn có thể giữ lại tùy ý.

## 20. Kiểm tra dữ liệu rỗng, null, tràn số và kết thúc sớm

### 20.1. Nguồn rỗng

Chọn rõ nghĩa của kết quả:

- Gatherer nén run (`consecutiveRuns`) trả **không có run**.
- Gatherer thống kê cuối (`summarizeNonnegative`) có thể phát **một Summary(0,0,0)**.
- Gatherer tần suất cuối có thể phát **một Map rỗng**.

Đây là ba chính sách **khác nhau**, đều có thể hợp lý. Người xây Gatherer phải xác định loại kết quả phù hợp với yêu cầu nghiệp vụ và kiểm thử trên nguồn rỗng.

### 20.2. Null

`Stream` có thể chứa null trong một số trường hợp, nhưng callback có thể không xử lý được nó. Ví dụ `consecutiveRuns` dùng `Objects.equals` để nhóm null an toàn, còn `summarizeNonnegative` chủ động từ chối null vì không có giá trị số phù hợp.

Nếu kết quả được sao chép bằng `List.copyOf` hoặc `Map.copyOf`, cần nhớ các API này **không nhận phần tử/khóa/giá trị null**. Đừng để chính sách null chỉ xuất hiện dưới dạng một ngoại lệ khó hiểu ở finisher.

### 20.3. Tràn số

Dù `long` lớn hơn `int`, một `count` hay `sum` vẫn có thể tràn. `Math.addExact` là một lựa chọn **báo lỗi khi tràn**, phù hợp nếu mục tiêu là phát hiện dữ liệu vượt giới hạn. Với yêu cầu chính xác lớn hơn `long`, cân nhắc `BigInteger`.

Khi parallel, cách nhóm số có thể thay đổi, vì vậy còn phải xét **tính kết hợp của phép toán và chính sách overflow**. Nếu dùng `double`, thứ tự cộng có thể tạo sai khác do làm tròn, dù phép toán về toán học có tính kết hợp.

### 20.4. Short-circuit

Nếu downstream dùng `limit(1)` hoặc `findFirst()`, một số phần tử nguồn có thể không cần được xử lý. `Downstream.push` trả `false` khi downstream không muốn nhận thêm; `isRejecting()` chỉ là phép kiểm tra hỗ trợ.

Không viết test đòi integrator luôn được gọi đúng bằng số phần tử nguồn trong mọi pipeline; khi có short-circuit, giả định đó không còn phù hợp.

## 21. Đánh giá song song và đúng thứ tự

Không phải cứ có combiner thì Gatherer luôn chạy nhanh hơn.

Các yếu tố quyết định:

1. **Nguồn có chia tốt không?** `Spliterator.trySplit` có tạo những phần độc lập, cân bằng và không trùng không?
2. **Chi phí mỗi phần tử có đủ lớn không?** Một phép cộng số đơn giản có thể rẻ hơn overhead song song.
3. **Combiner có đắt không?** Gộp hai `HashMap` lớn tốn nhiều thao tác băm và cấp phát.
4. **Có cần encounter order không?** Thuật toán phụ thuộc kề nhau hoặc tổng lũy kế có thể không cho phép ghép tùy ý.
5. **State có nặng không?** Một số lượng lớn phân đoạn có thể nhân bộ nhớ trung gian.
6. **Có short-circuit không?** Việc dừng sớm có thể ảnh hưởng lượng công việc và nhánh kết quả được giữ.

`Gatherer.of(...)` với combiner đúng **cho phép** song song hóa; nó không bắt buộc runtime phải chia nguồn. Ngược lại, `ofSequential(...)` nói rõ rằng thuật toán cần một diễn tiến tích lũy tuần tự để giữ đúng nghĩa.

**Nguyên tắc:** kiểm chứng **kết quả tuần tự và song song tương đương** trước, rồi mới đo thời gian bằng công cụ phù hợp như JMH. Không dùng `System.out.println` trong integrator để đo hiệu năng, vì console I/O chia sẻ có thể làm kết quả sai lệch.

## 22. So sánh Gatherer với Collector và Spliterator

| Thành phần | Vai trò chính | Liên hệ với state phân đoạn |
|---|---|---|
| `Spliterator` | Cung cấp và chia nguồn | Quyết định khả năng phân hoạch dữ liệu đầu vào |
| `Gatherer` | Biến đổi **trung gian** có thể có state | Có initializer/integrator/combiner/finisher, phát 0..n đầu ra |
| `Collector` | **Terminal reduction** thành một kết quả | Có supplier/accumulator/combiner/finisher, tích lũy vào kết quả cuối |
| `reduce` | Rút gọn theo phép kết hợp giá trị | Thường không dành cho việc sửa một identity mutable dùng chung |
| `map`/`filter` | Biến đổi/lọc phần tử | Thường không cần state của các phần tử trước |

### 22.1. Khi chỉ cần báo cáo cuối, Collector thường rõ hơn

Ví dụ đếm theo từ khóa:

~~~java
Map<String, Long> counts = words.stream()
    .collect(java.util.stream.Collectors.groupingBy(
        word -> word,
        java.util.stream.Collectors.counting()
    ));
~~~

Nếu mục tiêu chỉ là Map cuối cùng, hãy ưu tiên collector. Một Gatherer đếm từ như mục 12 có giá trị học thuật ở chỗ cho thấy **state phân đoạn và combiner**, nhưng không nhất thiết là lựa chọn gọn nhất trong ứng dụng thực.

### 22.2. Khi cần phát kết quả giữa pipeline, Gatherer có lợi thế

Ví dụ nén các chuỗi liên tiếp:

~~~java
List<Run<String>> longRuns = words.stream()
    .gather(consecutiveRuns())
    .filter(run -> run.count() >= 2)
    .toList();
~~~

Ở đây đầu ra của Gatherer tiếp tục đi qua `filter`. Một collector cuối cùng thông thường không thể thay trực tiếp bước trung gian này mà không thay đổi cấu trúc pipeline.

## 23. Những lỗi phổ biến khi quản lý state theo phân đoạn

| Lỗi | Hậu quả | Cách sửa |
|---|---|---|
| `initializer` trả đối tượng mutable dùng chung | Race condition, gộp sai, rò rỉ trạng thái giữa các lần chạy | Trả state mới từ `State::new` |
| Dùng `ThreadLocal` thay state phân đoạn | Nhầm thread với partition, khó gộp | Để framework quản lý state qua initializer |
| `combiner` trả `left` mà không gộp `right` | Mất dữ liệu | Hợp nhất đầy đủ trước khi trả |
| `combiner` dùng phép toán không associative | Kết quả có thể thay đổi khi chia khác nhau | Chứng minh tính kết hợp hoặc dùng sequential |
| Dùng `of(...)` cho phép scan lũy kế phát từng bước | Không thể sửa đầu ra đã phát ở phân đoạn phải | Dùng `ofSequential` hoặc thuật toán parallel scan đúng |
| Phân đoạn được coi là “batch 100 phần tử” | Kích thước batch phụ thuộc runtime | Dùng cửa sổ nghiệp vụ rõ ràng |
| `finisher` trả thẳng container mutable | Caller có thể sửa hoặc thấy trạng thái nội bộ | Trả bản sao/snapshot có chính sách rõ |
| Giữ `Downstream` để phát từ thread khác | Vi phạm lifetime API | Chỉ dùng downstream trong callback tương ứng |
| Không kiểm tra `push` trả `false` | Lãng phí hoặc vi phạm yêu cầu dừng | Truyền tín hiệu dừng phù hợp |
| Tạo state rất lớn ở mỗi initializer | Tăng bộ nhớ khi phân đoạn nhiều | State nhỏ, cấp phát có kiểm soát |
| Giả định combiner gọi đúng một lần | Hỏng khi runtime chia/ghép khác | Thiết kế đúng cho mọi cách chia hợp lệ |
| Cho rằng `parallel()` luôn nhanh hơn | Overhead chia/gộp cao | Đo bằng benchmark đại diện |
| Dùng `static long count` để thống kê | Kết quả nhiễm giữa các lần đánh giá | Giữ count trong state, gộp bằng combiner |
| Không xử lý nguồn rỗng | Finisher có thể phát kết quả sai nghĩa | Định nghĩa rõ zero-output hay kết quả rỗng |
| Không xác định null/overflow | Báo cáo sai hoặc lỗi muộn | Kiểm tra đầu vào và chọn chính sách số học |

## 24. Bài thực hành 1: kiểm tra kết quả qua nhiều lần chạy

**Yêu cầu:** dùng `summarizeNonnegative()` ở mục 10 để kiểm chứng mỗi phép đánh giá Stream có state riêng và các phân đoạn không được chia sẻ state giữa hai lần gọi.

Đặt đoạn sau trong `main` của `PartitionStateDemo`:

~~~java
List<Integer> first = List.of(2, 4, 6);
List<Integer> second = List.of(1, 3);

List<Summary> firstReport = first.parallelStream()
    .gather(summarizeNonnegative())
    .toList();

List<Summary> secondReport = second.parallelStream()
    .gather(summarizeNonnegative())
    .toList();

System.out.println(firstReport);
// [Summary[count=3, sum=12, evenCount=3]]

System.out.println(secondReport);
// [Summary[count=2, sum=4, evenCount=0]]
~~~

Nếu state bị giữ trong một biến static và tái sử dụng, báo cáo thứ hai có thể nhận số đếm/tổng từ lần chạy thứ nhất. Với `State::new` đúng hợp đồng, mỗi lần đánh giá có bộ chứa độc lập.

**Đừng viết test kiểm tra số lần gọi initializer bằng một biến toàn cục.** Số phân đoạn là chi tiết thực thi; điều cần kiểm tra là kết quả nghiệp vụ.

## 25. Bài thực hành 2: tự viết Gatherer lấy giá trị lớn nhất

**Đề bài:** tạo Gatherer nhận `Integer` không null, phát **một giá trị lớn nhất** khi nguồn kết thúc; nếu nguồn rỗng thì không phát đầu ra. Cho phép chạy song song bằng state riêng và combiner đúng hợp đồng.

### Lời giải tham khảo (Java 24+)

~~~java
import java.util.List;
import java.util.Objects;
import java.util.stream.Gatherer;
import java.util.stream.Stream;

public class MaxGathererPractice {

    static Gatherer<Integer, ?, Integer> maxValue() {
        class State {
            boolean present;
            int maximum;
        }

        return Gatherer.<Integer, State, Integer>of(
            State::new,

            Gatherer.Integrator.ofGreedy(
                (state, value, downstream) -> {
                    Objects.requireNonNull(value, "value");
                    if (!state.present) {
                        state.present = true;
                        state.maximum = value;
                    } else {
                        state.maximum = Math.max(
                            state.maximum, value
                        );
                    }
                    return true;
                }
            ),

            (left, right) -> {
                if (!right.present) {
                    return left;
                }
                if (!left.present) {
                    return right;
                }
                left.maximum = Math.max(
                    left.maximum, right.maximum
                );
                return left;
            },

            (state, downstream) -> {
                if (state.present && !downstream.isRejecting()) {
                    downstream.push(state.maximum);
                }
            }
        );
    }

    public static void main(String[] args) {
        List<Integer> values = List.of(4, 9, 2, 7, 1);

        List<Integer> result = values.parallelStream()
            .gather(maxValue())
            .toList();

        System.out.println(result); // [9]

        List<Integer> empty = Stream.<Integer>empty()
            .gather(maxValue())
            .toList();

        System.out.println(empty); // []
    }
}
~~~

### Vì sao combiner xử lý state rỗng trước?

State mới từ `initializer` có `present = false`. Nếu dùng `Math.max(left.maximum, right.maximum)` ngay, giá trị mặc định `0` có thể làm sai kết quả khi nguồn toàn số âm.

Ví dụ `[-10, -4, -8]` phải cho kết quả `-4`, không phải `0`. Cờ `present` đảm bảo:

- Khi một bên rỗng, chọn state của bên còn dữ liệu.
- Khi cả hai có dữ liệu, lấy max của hai giá trị.
- Khi cả hai rỗng, kết quả vẫn không có phần tử.
- Không giả định các giá trị đầu vào không âm.

Đây là một **bất biến state** quan trọng: giá trị `maximum` chỉ có ý nghĩa khi `present == true`.

## 26. Bài thực hành 3: phân tích một combiner sai

Một lập trình viên viết Gatherer đếm phần tử, với state là `long[]` kích thước 1:

~~~java
// Ví dụ cố ý sai:
Gatherer<Integer, ?, Long> counter = Gatherer.of(
    () -> new long[1],
    Gatherer.Integrator.ofGreedy(
        (state, value, downstream) -> {
            state[0]++;
            return true;
        }
    ),
    (left, right) -> left,
    (state, downstream) -> downstream.push(state[0])
);
~~~

### Câu hỏi

1. `initializer` có tạo state riêng không?
2. `integrator` có thực hiện đếm trong từng state không?
3. `combiner` có bảo toàn số đếm các phân đoạn không?
4. Vì sao pipeline tuần tự có thể cho kết quả đúng nhưng song song cho kết quả sai?
5. Hãy sửa combiner và giải thích điều kiện để phép cộng là hợp lệ.

### Lời giải

~~~java
(left, right) -> {
    left[0] = Math.addExact(left[0], right[0]);
    return left;
}
~~~

`initializer` và `integrator` của ví dụ cơ bản đúng hướng. **Lỗi nằm ở combiner**: trả `left` làm mất số đếm `right`. Trong một lần chạy tuần tự, combiner có thể không được gọi nên lỗi chưa lộ; khi chia nguồn và gộp state, lỗi trở nên rõ ràng.

Để tránh tràn `long`, dùng `Math.addExact` ở cả accumulator và combiner nếu hợp đồng nghiệp vụ yêu cầu báo lỗi khi vượt giới hạn. Không thể chỉ kiểm tra kết quả trên một Stream ngắn mà kết luận combiner luôn đúng.

## 27. Kiểm thử nên dựa trên hợp đồng, không dựa trên lịch chạy

Một Gatherer có state cần được kiểm thử ở ít nhất các chiều:

| Ca kiểm thử | Ý nghĩa |
|---|---|
| Stream rỗng | Zero-output hay bản tổng hợp rỗng đúng chính sách |
| Một phần tử | Không bị bỏ sót/đếm hai lần |
| Nhiều phần tử lặp liên tiếp | State được giữ đúng giữa các input |
| Nhiều nhóm có cùng giá trị ở ranh giới tưởng tượng | Không phát sai các run |
| Nhiều lần đánh giá liên tiếp | Không rò rỉ state giữa các lần chạy |
| Tuần tự và song song | Kết quả tương đương với Gatherer có combiner hợp lệ |
| Mọi phần tử đều âm (max) | Không dùng 0 như một sentinel sai |
| Giá trị null | Báo lỗi hoặc xử lý theo chính sách |
| Tổng quá lớn | Báo overflow hoặc dùng kiểu số phù hợp |
| Downstream `limit`/`findFirst` | Không yêu cầu callback phát sau khi downstream từ chối |
| Nguồn có encounter order và không có order | Không tự giả định thứ tự ở nguồn unordered |
| Map có khóa xuất hiện ở hai phân đoạn | Combiner cộng đúng thay vì ghi đè |
| Khối lượng lớn | Không giữ quá nhiều state, không rò tài nguyên |

Đối với tính đúng khi chia, **đừng cố ép framework tạo đúng hai phân đoạn** rồi xem đó là toàn bộ kiểm thử. Có thể **kiểm thử riêng hàm gộp state** bằng các trạng thái tự tạo theo hợp đồng; so sánh kết quả cho các cách nhóm `(A⊕B)⊕C` và `A⊕(B⊕C)`, kể cả state rỗng.

Việc kiểm tra logic combiner trực tiếp giúp phát hiện lỗi mà một pipeline thực tế nhỏ chưa chắc kích hoạt.

## 28. Câu hỏi tự kiểm tra

1. `Gatherer<T, A, R>` có ý nghĩa gì? — **Đầu vào T, trạng thái A, đầu ra R**.
2. Một phép đánh giá parallel Gatherer có luôn đúng một state không? — **Không**; có thể có nhiều state cục bộ rồi được gộp.
3. `initializer` nên trả gì khi state mutable? — **Một instance mới** cho mỗi lần được gọi.
4. `integrator` nhận gì? — **State, phần tử đầu vào, Downstream**.
5. `combiner` nhận gì? — **Hai state đã tích lũy**, tạo state kết hợp.
6. `finisher` dùng để làm gì? — **Tùy chọn phát đầu ra cuối khi hoàn tất**.
7. `ofSequential` thể hiện điều gì? — **Gatherer không được chia/gộp như một Gatherer parallelizable**.
8. `of` với combiner có tự đảm bảo nhanh hơn không? — **Không**, chỉ mở khả năng song song hóa.
9. Vì sao không nên dùng `ThreadLocal` thay state phân đoạn? — **Thread không đồng nhất với phân đoạn**.
10. `Downstream.push` trả `false` nghĩa là gì? — **Downstream không còn chấp nhận đầu ra tiếp theo**.
11. `Integrator.Greedy` có được chủ động dừng tùy ý không? — **Không**, chỉ phản ánh yêu cầu dừng từ downstream.
12. Vì sao run-length encoding đơn giản dùng `ofSequential`? — **Các nhóm có thể nối qua ranh giới phân đoạn**.
13. Vì sao scan lũy kế không thể chỉ thêm combiner cộng tổng? — **Đầu ra đã phát của nhánh phải cần offset từ nhánh trái**.
14. `combiner` nhận hai Map có cùng khóa thì dùng `putAll` được không? — **Không**, nếu cần cộng số đếm.
15. Khi nào cần sao chép state ở finisher? — **Khi không muốn lộ bộ chứa mutable hoặc cần snapshot**.
16. Có nên lưu `Downstream` để đẩy dữ liệu từ thread khác sau callback không? — **Không**, vi phạm lifetime của API.
17. Số lượng phân đoạn có phải quy tắc batch nghiệp vụ không? — **Không**, do framework quyết định.
18. Có thể dùng `Collector` thay Gatherer để thống kê một Map cuối không? — **Có**, nhiều khi ngắn và rõ hơn.
19. Stream Gatherers chuẩn có từ JDK nào? — **Java 24**.
20. Điều kiện quan trọng nhất trước khi cho phép parallel Gatherer là gì? — **Combiner và cách phát đầu ra phải giữ ngữ nghĩa với mọi cách chia hợp lệ**.

## 29. Checklist thiết kế Gatherer có state

Trước khi đưa một Gatherer tùy biến vào dự án, tự hỏi:

- [ ] **Hợp đồng đầu vào/đầu ra** đã rõ, kể cả nguồn rỗng?
- [ ] **State A** chứa đúng dữ liệu cần giữ, không gắn giả tạo với thread?
- [ ] `initializer` có tạo state độc lập khi cần?
- [ ] `integrator` có duy trì bất biến sau mỗi phần tử?
- [ ] Khi phát đầu ra, có tôn trọng `Downstream.push` và short-circuit?
- [ ] Có thật cần `finisher`? Nếu có, đã xét downstream rejecting?
- [ ] Có **chứng minh được combiner đúng** và không làm mất dữ liệu?
- [ ] Đã xét dữ liệu biên giữa các phân đoạn, nhất là thuật toán phụ thuộc thứ tự?
- [ ] Nếu không có combiner đúng, đã dùng `ofSequential`?
- [ ] State và Downstream có **không bị lưu, lộ hoặc dùng sau callback**?
- [ ] Kết quả cuối có tránh lộ Map/List mutable nếu API không cho phép sửa?
- [ ] Null, overflow và ngoại lệ có chính sách rõ ràng?
- [ ] Nguồn I/O có quản lý `try-with-resources` ở nơi sở hữu?
- [ ] Đã kiểm thử tuần tự, song song, nguồn rỗng và các lần chạy liên tiếp?
- [ ] Đã đo hiệu năng trước khi tuyên bố parallel nhanh hơn?
- [ ] Môi trường build/runtime thực sự hỗ trợ **Java 24+**?

## 30. Kết luận

**Trạng thái riêng cho mỗi phân đoạn xử lý** là nền tảng để triển khai Gatherer có state mà vẫn có khả năng song song hóa. `initializer` tạo state độc lập; `integrator` cập nhật state từ dữ liệu được giao; `combiner` gộp những state đã xử lý; `finisher` tạo đầu ra cuối. Một Gatherer có thể chạy song song **chỉ khi cách ghép trạng thái và đầu ra bảo toàn đúng ngữ nghĩa**.

Hãy ghi nhớ ba lựa chọn thiết kế:

1. Nếu phép toán phụ thuộc **thứ tự toàn cục** hoặc các phần tử kề nhau, bắt đầu với **`Gatherer.ofSequential`**.
2. Nếu state có thể gộp bằng phép **kết hợp đúng, có state rỗng hợp lệ** và đầu ra được phát ở thời điểm phù hợp, có thể dùng **`Gatherer.of` với combiner**.
3. Nếu chỉ cần **một kết quả tổng hợp cuối**, hãy đánh giá xem `Collector` chuẩn có đơn giản hơn một Gatherer tùy chỉnh hay không.

Không chia sẻ state mutable giữa các phân đoạn, không đồng nhất phân đoạn với thread, không lộ `Downstream` ra ngoài callback và không dùng `parallel()` như một cách tối ưu mặc định. Nắm chắc những nguyên tắc này giúp bạn xây các phép biến đổi Stream có trạng thái **đúng hợp đồng, dễ kiểm thử, quản lý tài nguyên tốt và có thể mở rộng**.

### Tài liệu đối chiếu API Java 24

- [Java SE 24 — Gatherer](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/util/stream/Gatherer.html)
- [Java SE 24 — Gatherer.Integrator](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/util/stream/Gatherer.Integrator.html)
- [Java SE 24 — Gatherer.Downstream](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/util/stream/Gatherer.Downstream.html)
- [Oracle — Stream Gatherers](https://docs.oracle.com/en/java/javase/24/core/stream-gatherers.html)
