# Xử lý phần dữ liệu còn lại bằng finisher

## 1. Khi nguồn kết thúc nhưng trạng thái Gatherer vẫn còn dữ liệu

Trong module **JAVA_STREAM_API**, pipeline `filter`, `map`, `reduce` và `collect` giúp xử lý dữ liệu theo cách khai báo. Nhưng không phải phép biến đổi nào cũng giải quyết được chỉ bằng một phần tử đầu vào. Có những thao tác phải **tích lũy nhiều phần tử**, ví dụ gom thành lô, chờ dấu phân cách, hoặc gom những giá trị giống nhau liên tiếp.

**Stream Gatherer** cho phép viết một phép biến đổi trung gian có trạng thái. Trong khi nhận đầu vào, `integrator` cập nhật state và phát kết quả khi đủ điều kiện. Đến lúc nguồn kết thúc, state có thể vẫn giữ một **phần đuôi chưa phát**. `finisher` giải quyết chính phần đuôi đó.

~~~text
Nguồn:       [A, B, C, D, E, F, G]
Kích thước lô = 3

Integrator:
  [A, B, C]  → phát lô 1
  [D, E, F]  → phát lô 2
  [G]        → còn chờ, chưa đủ 3

Finisher:
  [G]        → phát lô cuối

Kết quả: [[A, B, C], [D, E, F], [G]]
~~~

Nếu bỏ qua bước hoàn tất, `G` có thể bị mất. Ngược lại, nếu luôn phát buffer khi kết thúc mà không kiểm tra rỗng, có thể tạo thêm **lô rỗng giả** khi số phần tử chia hết cho kích thước lô.

Chủ đề **“Xử lý phần dữ liệu còn lại bằng finisher”** thuộc chương **Xây dựng Gatherer tùy biến**. Bài giải thích cơ chế hoạt động, cách phát phần dư, tôn trọng downstream khi ngừng sớm, các lỗi liên quan tới state mutable, và giới hạn khi thực thi song song.

**Yêu cầu phiên bản:** Stream Gatherers đã được chuẩn hóa trong **Java 24** (JEP 485), sau giai đoạn preview ở Java 22 và 23. Các ví dụ dùng `Gatherer` và `Stream.gather(...)` trong bài cần **Java 24+**; không biên dịch trực tiếp bằng Java 17 hoặc 21. Các lớp `public class` dưới đây có thể lưu thành file mang cùng tên lớp để chạy độc lập, trừ những snippet ngắn có ghi rõ dùng thành phần từ ví dụ trước.

### Các trường hợp cần finisher

| Mẫu xử lý | Khi nào integrator phát? | Finisher xử lý gì? |
| --- | --- | --- |
| Gom lô kích thước cố định | Khi đủ `k` phần tử | Lô cuối có dưới `k` phần tử |
| Tách đoạn bằng dòng trống | Khi gặp dấu phân cách | Đoạn cuối không có dấu phân cách |
| Nén phần tử giống nhau liên tiếp | Khi giá trị thay đổi | Đoạn liên tiếp cuối cùng |
| Tổng hợp chỉ phát cuối nguồn | Không phát trong khi đọc | Chuyển state thành kết quả tổng hợp |
| Parser theo cặp BEGIN/END | Khi gặp END | Báo lỗi hoặc xử lý bản ghi chưa đóng |

Điểm chung là **finisher không tự sinh lại dữ liệu nguồn**: nó chỉ xử lý những gì được giữ lại trong state và chính sách mà tác giả Gatherer đã định nghĩa.

## 2. Vòng đời và vai trò của bốn thành phần

Một `Gatherer<T, A, R>` có các loại dữ liệu:

- `T`: phần tử đầu vào.
- `A`: trạng thái tích lũy (*state*) do Gatherer quản lý.
- `R`: phần tử đầu ra được đẩy sang giai đoạn phía sau.

Các thành phần chính:

1. **Initializer** tạo một state thích hợp cho một lần đánh giá.
2. **Integrator** nhận từng phần tử `T`, cập nhật state, có thể gọi `downstream.push(R)`.
3. **Combiner** hợp nhất các state khi Gatherer hỗ trợ đánh giá song song.
4. **Finisher** hoàn tất state và có thể phát thêm phần tử `R` sau khi không còn nhận thêm input.

~~~text
                      Stream<T>
                          │
                          ▼
                   initializer()
                  tạo state A
                          │
                          ▼
                  integrator(A,T)
                    │        │
             cập nhật A   push(R) khi đủ điều kiện
                    │        │
                    └────┬───┘
                         │
                giai đoạn nhận đầu vào kết thúc
                         │
                         ▼
                finisher(A, downstream)
                         │
            ┌────────────┴────────────┐
            ▼                         ▼
     state không có đuôi        state còn đuôi
     không phát thêm            push(R) nếu được nhận
            └────────────┬────────────┘
                         ▼
                Pipeline phía sau
                         ▼
               Terminal operation
~~~

Đây là **mô hình logic** cho một Gatherer tuần tự khi pipeline được tiêu thụ bình thường. Không dùng số lần gọi callback hay thứ tự log làm hợp đồng cho các trường hợp terminal short-circuit hoặc hệ thống có tối ưu hóa.

### finisher khác với integrator

`integrator` trả `boolean`: nó có thể quyết định việc **tiếp tục nhận thêm input** hay không. `finisher` là callback dạng `BiConsumer`, **không trả Boolean** và không được dùng để đọc thêm dữ liệu nguồn. Nó có thể đề nghị đẩy 0, 1 hoặc nhiều kết quả cuối xuống downstream.

### finisher khác với Collector.finisher

| Thuộc tính | `Collector.finisher()` | `Gatherer.finisher()` |
| --- | --- | --- |
| Vị trí | Terminal `collect` | Intermediate `gather` |
| Đầu vào | State tích lũy | State và Downstream |
| Đầu ra | Hàm chuyển `A → R` | Gọi `push` 0, 1 hoặc nhiều lần |
| Có thể phát tiếp trong pipeline? | Không, tạo kết quả terminal | Có, gửi đầu ra tới các stage phía sau |
| Tương tác short-circuit | Không có Downstream của Gatherer | Cần tôn trọng downstream từ chối thêm phần tử |

Nếu mục tiêu chỉ là một số tổng hoặc một List cuối cùng, thường nên cân nhắc `reduce` hoặc `collect` trước khi tạo Gatherer riêng.

## 3. Hợp đồng finisher và Downstream

Ở mức API, `Gatherer.finisher()` cung cấp một callback với ý nghĩa kiểu:

~~~java
// Chữ ký khái niệm, không phải lớp độc lập.
BiConsumer<A, Gatherer.Downstream<? super R>> finisher;
~~~

`Downstream` cung cấp hai thao tác cần thiết:

| Thao tác | Ý nghĩa |
| --- | --- |
| `downstream.push(value)` | Đề nghị phát một phần tử; kết quả `boolean` báo việc có còn tiếp nhận thêm không |
| `downstream.isRejecting()` | Cho biết downstream hiện đang từ chối phần tử mới |

Mẫu finisher cho buffer:

~~~java
// Các phương thức hasPending()/snapshot() do state của bài toán định nghĩa.
(state, downstream) -> {
    if (state.hasPending() && !downstream.isRejecting()) {
        downstream.push(state.snapshot());
    }
}
~~~

Nếu finisher có thể phát **nhiều** giá trị cuối cùng, cần dừng vòng lặp khi downstream từ chối:

~~~java
// Pseudocode có R và state.pendingValues() do ứng dụng định nghĩa.
(state, downstream) -> {
    for (R value : state.pendingValues()) {
        if (downstream.isRejecting() || !downstream.push(value)) {
            break;
        }
    }
}
~~~

`finisher` không có quyền ép terminal operation chấp nhận tất cả đầu ra. Ví dụ, `limit(1)` chỉ cần một phần tử đầu ra: nếu downstream đã từ chối, phần đuôi đang giữ trong state không được mặc nhiên xuất hiện trong kết quả.

## 4. Bài toán đầy đủ: gom thành lô và xả phần đuôi

Ta viết một Gatherer nhận `Stream<T>` và tạo `Stream<List<T>>`. Mỗi lô có tối đa `batchSize` phần tử. Các lô đầy phát trong integrator; lô cuối chưa đủ kích thước phát trong finisher.

### 4.1. Bất biến của state

1. Buffer chỉ chứa **phần đã đọc nhưng chưa phát**.
2. Sau khi phát một lô đầy, buffer phải trở về rỗng.
3. Đầu ra phải là **bản sao độc lập**, không dùng chung chính `ArrayList` mutable.
4. Finisher chỉ phát khi buffer **không rỗng** và downstream còn tiếp nhận.
5. Mỗi đầu vào xuất hiện **đúng một lần** trong kết quả khi pipeline được tiêu thụ hết.

### 4.2. Java 24+: chương trình hoàn chỉnh

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import java.util.stream.Gatherer;

public class FixedBatchesDemo {

    static <T> Gatherer<T, ?, List<T>> batches(int batchSize) {
        if (batchSize <= 0) {
            throw new IllegalArgumentException("batchSize phải > 0");
        }

        return Gatherer.<T, ArrayList<T>, List<T>>ofSequential(
            // initializer: tạo buffer mới cho một lần thực thi
            () -> new ArrayList<>(batchSize),

            // integrator: tích lũy và phát lô khi đủ kích thước
            (buffer, element, downstream) -> {
                Objects.requireNonNull(element, "element");
                buffer.add(element);

                if (buffer.size() == batchSize) {
                    List<T> ready = List.copyOf(buffer);
                    buffer.clear();
                    return downstream.push(ready);
                }

                return true;
            },

            // finisher: chỉ phát phần dư còn trong buffer
            (buffer, downstream) -> {
                if (!buffer.isEmpty() && !downstream.isRejecting()) {
                    downstream.push(List.copyOf(buffer));
                }
            }
        );
    }

    public static void main(String[] args) {
        List<List<Integer>> result = List.of(
            1, 2, 3, 4, 5, 6, 7, 8
        ).stream()
            .gather(batches(3))
            .toList();

        System.out.println(result);
        // [[1, 2, 3], [4, 5, 6], [7, 8]]
    }
}
~~~

Ý nghĩa của tham số generic `Gatherer<T, ArrayList<T>, List<T>>`:

- `T`: một phần tử nguồn.
- `ArrayList<T>`: state mutable để tích lũy.
- `List<T>`: một phần tử đầu ra của Gatherer (một lô).

`Gatherer.ofSequential` phù hợp vì logic này muốn xử lý ranh giới batch theo encounter order, không tự định nghĩa cách gộp các buffer xử lý song song.

### 4.3. Tại sao trả downstream.push từ integrator?

Khi đã có một lô đầy, integrator gọi `downstream.push(ready)`. Nếu kết quả là `false`, downstream không muốn nhận thêm phần tử; integrator cũng trả `false` để dừng nhận input. Nếu chưa đủ lô, integrator trả `true` vì vẫn cần đọc tiếp.

Finisher không trả Boolean. Nó chỉ kiểm tra xem state còn đuôi và downstream có còn tiếp nhận hay không.

### 4.4. Bảng kết quả theo kích thước

| Nguồn | Batch size | Kết quả mong đợi |
| --- | ---: | --- |
| `[]` | 3 | `[]` |
| `[1]` | 3 | `[[1]]` |
| `[1,2]` | 3 | `[[1,2]]` |
| `[1,2,3]` | 3 | `[[1,2,3]]` |
| `[1,2,3,4]` | 3 | `[[1,2,3],[4]]` |
| `[1,2,3,4,5,6]` | 3 | `[[1,2,3],[4,5,6]]` |
| `[1,2,3,4,5,6,7]` | 3 | `[[1,2,3],[4,5,6],[7]]` |

Nếu nguồn có `N` phần tử, lô kích thước `k > 0` và pipeline tiêu thụ hết: integrator phát `floor(N/k)` lô đầy, finisher phát **một** lô nếu `N % k != 0`. Số lô bằng `ceil(N/k)` khi `N > 0`, bằng 0 khi nguồn rỗng.

## 5. Đừng phát chính buffer mutable ra ngoài

Cách viết sai thường gặp:

~~~java
// SAI: minh họa trong integrator.
if (buffer.size() == batchSize) {
    downstream.push(buffer); // Đưa chính state ra ngoài.
    buffer.clear();          // Xóa nội dung kết quả vừa phát.
    return true;
}
~~~

Nếu downstream giữ tham chiếu tới `buffer`, những batch đã phát có thể bị xóa sạch hoặc thay đổi khi buffer nhận thêm dữ liệu. Nhiều batch còn có thể trỏ về **cùng một object**.

Cách đúng khi cấm null:

~~~java
List<T> ready = List.copyOf(buffer);
buffer.clear();
return downstream.push(ready);
~~~

`List.copyOf` tạo cấu trúc danh sách không sửa đổi được. Lệnh `buffer.clear()` không ảnh hưởng tới bản sao đã được phát.

Nếu nghiệp vụ **cho phép phần tử null**, `List.copyOf` không thích hợp vì nó ném `NullPointerException`. Có thể dùng bản sao cấu trúc và view không sửa được:

~~~java
List<T> ready = java.util.Collections.unmodifiableList(
    new java.util.ArrayList<>(buffer)
);
buffer.clear();
return downstream.push(ready);
~~~

`Collections.unmodifiableList(new ArrayList<>(buffer))` tạo view không sửa được của **bản sao**, không phải view của buffer gốc. Dù vậy, nếu `T` là object mutable, trạng thái bên trong phần tử vẫn có thể thay đổi: đây không phải **deep immutable snapshot**.

**Quy tắc:** Không gọi `Collections.unmodifiableList(buffer)` rồi tiếp tục sửa buffer, vì wrapper đó vẫn phản ánh các thay đổi của danh sách nền.

## 6. Nguồn rỗng, phần dư bằng 0 và downstream dừng sớm

### 6.1. Nguồn rỗng

~~~java
import java.util.List;
import java.util.stream.Stream;

List<List<Integer>> result = Stream.<Integer>empty()
    .gather(FixedBatchesDemo.batches(3))
    .toList();

System.out.println(result); // []
~~~

Vì không có phần tử cần phát, finisher phải kiểm tra `buffer.isEmpty()`, tránh phát `[]` giả.

### 6.2. Đúng bội số kích thước batch

~~~java
List<List<Integer>> result = List.of(1, 2, 3, 4, 5, 6)
    .stream()
    .gather(FixedBatchesDemo.batches(3))
    .toList();

System.out.println(result); // [[1, 2, 3], [4, 5, 6]]
~~~

Nếu finisher **luôn** gọi `downstream.push(List.copyOf(buffer))` mà không kiểm tra rỗng, kết quả có thể thêm một nhóm `[]` ở cuối. Đó là lỗi nghiệp vụ nếu mỗi batch đại diện cho một yêu cầu xử lý thực tế.

### 6.3. Short-circuit với limit

~~~java
List<List<Integer>> first = List.of(
    1, 2, 3, 4, 5, 6, 7
).stream()
    .gather(FixedBatchesDemo.batches(3))
    .limit(1)
    .toList();

System.out.println(first); // [[1, 2, 3]]
~~~

`limit(1)` không yêu cầu các batch phía sau. Nếu downstream từ chối thêm phần tử, integrator nên ngừng và finisher không cố đẩy phần dư. Không viết kiểm thử đòi integrator chạy trên **tất cả phần tử nguồn** chỉ vì `finisher` tồn tại.

### 6.4. Không dùng callback như cơ chế audit

Số lần `integrator`, `finisher` hoặc một lambda trong pipeline được gọi có thể bị ảnh hưởng bởi short-circuit và tối ưu hóa. Nếu hệ thống cần log nghiệp vụ bắt buộc, giao dịch hoặc gửi request, hãy thiết kế cơ chế điều phối riêng. `finisher` không thay thế một hook giao dịch chắc chắn chỉ chạy một lần.

## 7. Gom theo dấu phân cách: xử lý đoạn cuối không có dấu đóng

Một ví dụ khác là chia các dòng văn bản thành nhóm; dòng trống đóng nhóm hiện tại. File có thể kết thúc ngay sau một dòng nội dung thay vì một dòng trống.

~~~text
Dòng đầu vào:
alpha
beta

gamma
delta
EOF

Integrator:
  gặp dòng trống → phát [alpha, beta]
  còn [gamma, delta] khi hết nguồn

Finisher:
  phát [gamma, delta]

Kết quả:
[[alpha, beta], [gamma, delta]]
~~~

### 7.1. Chương trình Java 24+

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import java.util.stream.Gatherer;

public class DelimitedSectionsDemo {

    static Gatherer<String, ?, List<String>> sections() {
        return Gatherer.<String, ArrayList<String>, List<String>>
            ofSequential(
                ArrayList::new,

                (buffer, line, downstream) -> {
                    Objects.requireNonNull(line, "line");

                    if (line.isBlank()) {
                        if (buffer.isEmpty()) {
                            // Bỏ qua hai dấu phân cách liên tiếp.
                            return true;
                        }

                        List<String> ready = List.copyOf(buffer);
                        buffer.clear();
                        return downstream.push(ready);
                    }

                    buffer.add(line);
                    return true;
                },

                (buffer, downstream) -> {
                    if (!buffer.isEmpty() && !downstream.isRejecting()) {
                        downstream.push(List.copyOf(buffer));
                    }
                }
            );
    }

    public static void main(String[] args) {
        List<String> lines = List.of(
            "alpha", "beta", "", "gamma", "delta"
        );

        List<List<String>> groups = lines.stream()
            .gather(sections())
            .toList();

        System.out.println(groups);
        // [[alpha, beta], [gamma, delta]]
    }
}
~~~

### 7.2. Những trường hợp biên

| Nguồn | Kết quả theo chính sách của ví dụ |
| --- | --- |
| `[]` | `[]` |
| `[""]` | `[]` |
| `["A"]` | `[["A"]]` |
| `["A",""]` | `[["A"]]` |
| `["A","","","B"]` | `[["A"],["B"]]` |

Ví dụ **bỏ đoạn rỗng**. Nếu hệ thống cần giữ đoạn rỗng giữa hai dấu phân cách, integrator phải có hợp đồng khác. Finisher chỉ xử lý **đoạn đang mở khi kết thúc**, không tự thay thế toàn bộ logic xác định ranh giới.

### 7.3. Rủi ro bộ nhớ

Nếu nguồn dài mà không có dòng trống, buffer sẽ tích lũy toàn bộ đoạn. Finisher không giúp giảm mức sử dụng RAM **trước khi kết thúc**. Với dữ liệu thực tế, có thể cần giới hạn số dòng hoặc kích thước byte, và báo lỗi/đẩy nhóm tạm tùy nghiệp vụ.


## 8. Run-length encoding: phát chuỗi cuối chưa được đóng

Một bài toán khác cần finisher là **run-length encoding**: gom các phần tử bằng nhau **liên tiếp** thành cặp (giá trị, số lần xuất hiện).

~~~text
Nguồn: A, A, B, B, B, A

Integrator:
  Khi gặp B đầu tiên → phát Run(A, 2)
  Khi gặp A cuối     → phát Run(B, 3)
  Đến EOF còn Run(A, 1) chưa phát

Finisher:
  phát Run(A, 1)

Đầu ra:
[Run(A, 2), Run(B, 3), Run(A, 1)]
~~~

### 8.1. Code hoàn chỉnh Java 24+

~~~java
import java.util.List;
import java.util.Objects;
import java.util.stream.Gatherer;

public class RunLengthDemo {

    record Run<T>(T value, long count) {}

    static final class State<T> {
        boolean hasValue;
        T currentValue;
        long count;
    }

    static <T> Gatherer<T, ?, Run<T>> runs() {
        return Gatherer.<T, State<T>, Run<T>>ofSequential(
            () -> new State<T>(),

            (state, element, downstream) -> {
                if (!state.hasValue) {
                    state.hasValue = true;
                    state.currentValue = element;
                    state.count = 1L;
                    return true;
                }

                if (Objects.equals(state.currentValue, element)) {
                    state.count = Math.addExact(state.count, 1L);
                    return true;
                }

                Run<T> finished = new Run<>(
                    state.currentValue, state.count
                );

                state.currentValue = element;
                state.count = 1L;
                return downstream.push(finished);
            },

            (state, downstream) -> {
                if (state.hasValue && !downstream.isRejecting()) {
                    downstream.push(new Run<>(
                        state.currentValue, state.count
                    ));
                }
            }
        );
    }

    public static void main(String[] args) {
        List<Run<String>> encoded = List.of(
            "A", "A", "B", "B", "B", "A"
        ).stream()
            .gather(RunLengthDemo.<String>runs())
            .toList();

        System.out.println(encoded);
        // [Run[value=A, count=2],
        //  Run[value=B, count=3],
        //  Run[value=A, count=1]]
    }
}
~~~

### 8.2. Vì sao cần hasValue?

Giá trị `currentValue` có thể bằng `null` nếu nguồn cho phép null. Nếu dùng `currentValue == null` để nhận biết “chưa có dữ liệu”, chương trình sẽ nhầm với một run thật của những phần tử null liên tiếp.

Cờ `hasValue` tách biệt hai trạng thái: **chưa thấy phần tử** và **đã thấy phần tử có giá trị null**. `Objects.equals` so sánh được cả hai null, còn record `Run<T>` không tự cấm null.

~~~java
import java.util.Arrays;
import java.util.List;

List<RunLengthDemo.Run<String>> encoded =
    Arrays.<String>asList(null, null, "A", null)
        .stream()
        .gather(RunLengthDemo.<String>runs())
        .toList();

System.out.println(encoded);
// [Run[value=null, count=2],
//  Run[value=A, count=1],
//  Run[value=null, count=1]]
~~~

`List.of` không cho phép null, nên ví dụ dùng `Arrays.asList`.

### 8.3. Vì sao không thay bằng groupingBy?

Với nguồn `["A", "A", "B", "A"]`:

- Run-length: `[Run(A,2), Run(B,1), Run(A,1)]`.
- `groupingBy(identity(), counting())`: `A→3`, `B→1`.

Run-length giữ **ranh giới liên tiếp theo encounter order**, trong khi groupingBy gộp mọi phần tử cùng khóa trên toàn nguồn. Với bài toán đếm tần suất đơn giản, dùng `groupingBy` sẽ ngắn gọn hơn.

## 9. Chỉ phát kết quả ở finisher: một bản thống kê cuối nguồn

Finisher không nhất thiết chỉ phát **phần dư** của một lô. Một Gatherer có thể không phát gì trong integrator rồi phát **một bản tổng hợp cuối cùng** từ state.

Ví dụ dưới đây chọn chính sách: **nguồn rỗng vẫn phát `Summary(count=0,sum=0)`**.

~~~java
import java.util.List;
import java.util.stream.Gatherer;
import java.util.stream.Stream;

public class FinalSummaryDemo {

    record Summary(long count, long sum) {}

    static final class State {
        long count;
        long sum;
    }

    static Gatherer<Integer, ?, Summary> summarize() {
        return Gatherer.<Integer, State, Summary>ofSequential(
            State::new,

            (state, number, downstream) -> {
                if (number == null) {
                    throw new IllegalArgumentException(
                        "Không nhận phần tử null"
                    );
                }
                state.count = Math.addExact(state.count, 1L);
                state.sum = Math.addExact(
                    state.sum, number.longValue()
                );

                // Chỉ tích lũy, chưa phát gì.
                return true;
            },

            (state, downstream) -> {
                if (!downstream.isRejecting()) {
                    downstream.push(
                        new Summary(state.count, state.sum)
                    );
                }
            }
        );
    }

    public static void main(String[] args) {
        System.out.println(
            List.of(2, 3, 5).stream()
                .gather(summarize())
                .toList()
        ); // [Summary[count=3, sum=10]]

        System.out.println(
            Stream.<Integer>empty()
                .gather(summarize())
                .toList()
        ); // [Summary[count=0, sum=0]]
    }
}
~~~

**Điều cần chú ý:**

- `State` chỉ có các trường `count` và `sum`, không lưu mọi phần tử.
- `Math.addExact` giúp phát hiện overflow của `long`.
- Finisher phát một value object bất biến.
- Nếu “không có số liệu” khác với “tổng thực sự bằng 0”, có thể sửa finisher để **không phát** khi `state.count == 0` hoặc dùng kiểu kết quả mô tả rõ dữ liệu thiếu.

### Gatherer hay collect?

Nếu chỉ cần một thống kê cuối nguồn, terminal `collect` hoặc `reduce` thường phù hợp hơn:

~~~java
import java.util.IntSummaryStatistics;
import java.util.List;

IntSummaryStatistics stats = List.of(2, 3, 5)
    .stream()
    .mapToInt(Integer::intValue)
    .summaryStatistics();

System.out.println(stats.getCount()); // 3
System.out.println(stats.getSum());   // 10
~~~

Ví dụ summary bằng Gatherer ở đây nhằm minh họa **finisher có thể là bước phát đầu ra duy nhất**, không có nghĩa luôn nên thay terminal collector bằng Gatherer tùy biến.

## 10. Finisher có thể push nhiều giá trị cuối

`Gatherer.finisher()` là callback dạng `BiConsumer`, nên không bị giới hạn ở đúng một phần tử đầu ra. Một trạng thái có thể chứa nhiều thông báo hoặc nhiều mảnh dữ liệu cần phát khi kết thúc.

~~~java
// Pseudocode: state.pendingValues() trả Iterable<R> do ứng dụng định nghĩa.
(state, downstream) -> {
    for (R value : state.pendingValues()) {
        if (downstream.isRejecting()) {
            break;
        }
        if (!downstream.push(value)) {
            break;
        }
    }
}
~~~

Đây chỉ là mẫu minh họa; `pendingValues()` không phải phương thức của Gatherer API. Cần kiểm tra phản hồi của `push` vì terminal operation có thể dừng sớm. Không dùng `pending.forEach(downstream::push)` để ngầm bỏ qua yêu cầu ngừng phát.

Một finisher phát nhiều giá trị còn cần kiểm soát:

- Số lượng đầu ra cuối có bị chặn bởi giới hạn hợp lý không?
- State còn giữ các phần tử **chưa phát** hay vô tình gồm cả phần tử đã phát?
- Các đầu ra phát ra có cấu trúc bất biến/snapshot an toàn không?
- Nếu downstream từ chối sau vài giá trị, logic có dừng ngay không?

Không viết finisher phát một dãy vô hạn hoặc phụ thuộc vào một vòng lặp không có tiêu chí dừng.

## 11. Chính sách với phần cuối: giữ, loại, đệm hoặc báo lỗi

Không phải mọi domain đều muốn phát một batch cuối chưa đủ kích thước. Với đầu vào `[1,2,3,4]` và batch size 3:

| Chính sách | Kết quả | Hành vi finisher |
| --- | --- | --- |
| Giữ batch ngắn | `[[1,2,3],[4]]` | `push([4])` |
| Bỏ phần dư | `[[1,2,3]]` | Không phát |
| Đệm | `[[1,2,3],[4,0,0]]` | Đệm 0 rồi phát |
| Yêu cầu batch đầy | Ném lỗi | Phát hiện buffer chưa rỗng |

Trong xử lý giao dịch, bỏ phần dư có thể làm mất dữ liệu nghiêm trọng. Trong một số bài toán xử lý tín hiệu, việc bỏ cửa sổ cuối chưa đủ phần tử lại là quy ước hợp lệ.

Finisher có thể từ chối một lô thiếu:

~~~java
// Snippet cho trạng thái List, không phải chương trình độc lập.
(buffer, downstream) -> {
    if (!buffer.isEmpty()) {
        throw new IllegalStateException(
            "Lô cuối thiếu phần tử: " + buffer.size()
        );
    }
}
~~~

Một parser với cặp dấu `BEGIN/END` có thể chọn chính sách tương tự: nếu hết nguồn khi bản ghi chưa gặp `END`, finisher báo lỗi thay vì tự đóng bản ghi.

### Chính sách null phải đồng bộ ở hai nhánh

Nếu integrator dùng cấu trúc chấp nhận null để phát batch đầy, còn finisher dùng `List.copyOf(buffer)`, batch cuối có null sẽ phát sinh NPE không nhất quán. Hãy chọn chính sách cấm null ngay khi nhận hoặc cùng một cách snapshot hỗ trợ null trong cả integrator lẫn finisher.

## 12. Song song: finisher không thay thế combiner

Các ví dụ trong bài dùng `Gatherer.ofSequential(...)` vì logic phụ thuộc vào thứ tự và biên của dữ liệu. Với thuật toán run-length, chia nguồn có thể cắt ngang một run:

~~~text
Nguồn ordered: [A, A, A, B, B]

Chia thành:
Trái: [A, A]
Phải: [A, B, B]

Nếu mỗi nhánh xả đuôi và nối ngây thơ:
  Run(A,2), Run(A,1), Run(B,2)

Kết quả đúng:
  Run(A,3), Run(B,2)
~~~

Muốn thiết kế Gatherer thực sự hỗ trợ gộp state song song phải giải quyết:

1. State chứa những thông tin biên nào của mỗi phân đoạn?
2. Combiner kết hợp state có **tính kết hợp** hay không?
3. Hai run hoặc hai batch nằm vắt qua ranh giới chia được hợp nhất thế nào?
4. Encounter order có được tôn trọng khi thuật toán cần nó không?
5. Phần đuôi được phát **sau khi đã hợp nhất đầy đủ**, không xả quá sớm ra sao?

`ofSequential` không cung cấp combiner để gộp các state song song. `parallelStream().gather(sequentialGatherer)` cũng không tự sinh ra phép gộp state đúng. Không mặc định rằng gọi `parallel()` sẽ tăng tốc; cần benchmark trên dữ liệu phù hợp sau khi đã kiểm tra tính đúng.

**Nguyên tắc:** Nếu chưa chứng minh được việc combine state đúng, ưu tiên Gatherer tuần tự. Khi muốn parallel, thiết kế một Gatherer có combiner hợp lệ và kiểm thử nhiều cách chia khác nhau.


## 13. Finisher không phải finally hoặc close

Tên `finisher` dễ khiến người học liên tưởng đến `finally` hoặc `AutoCloseable.close()`. Nhưng hai nhóm trách nhiệm hoàn toàn khác nhau:

- **`Gatherer.finisher()`:** hoàn tất **dữ liệu trong state**, có thể phát kết quả còn lại.
- **`Stream.close()`, `onClose()`, try-with-resources:** giải phóng tài nguyên ngoài như file, reader, socket hoặc connection.

Không được phụ thuộc vào finisher như một callback “chắc chắn chạy một lần” để đóng tài nguyên, thực hiện thanh toán hay ghi nhận một giao dịch. Short-circuit, exception và cách thực thi pipeline có thể thay đổi đường đi xử lý; trách nhiệm đóng tài nguyên cần được kiểm soát riêng.

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.stream.Stream;

public class FileSectionsDemo {
    static List<List<String>> readSections(Path file)
        throws IOException {

        try (Stream<String> lines = Files.lines(file)) {
            return lines
                .gather(DelimitedSectionsDemo.sections())
                .toList();
        }
    }
}
~~~

Ở đây:

1. `Files.lines(file)` tạo Stream gắn với tài nguyên file.
2. `gather(sections())` gom các dòng thành nhóm, finisher phát nhóm cuối khi EOF không có dòng trống.
3. `try-with-resources` đảm bảo đóng Stream/file theo hợp đồng của API, kể cả khi có exception trong lúc duyệt.

Nếu Gatherer tự tạo thêm tài nguyên bên ngoài, phải thiết kế rõ **ai sở hữu, ai đóng và cơ chế phục hồi khi lỗi**. Finisher chỉ là một bước biến đổi đầu ra, không phải một cơ chế tài nguyên thay thế.

## 14. Kiểm thử để chứng minh phần đuôi không bị mất hoặc lặp

Đối với batching theo encounter order và chính sách **giữ phần dư**, có thể kiểm tra bất biến:

~~~text
N = số phần tử đầu vào, k = kích thước batch > 0

Tổng số phần tử trong mọi batch = N
Số batch:
  N = 0: 0
  N > 0: ceil(N / k)

Mỗi batch có từ 1 tới k phần tử.
Nối các batch theo thứ tự == đúng danh sách nguồn.
~~~

Đây là kiểm thử **đầu ra**, không phải kiểm thử số lần `integrator` hoặc `finisher` được gọi.

### 14.1. Chương trình kiểm thử không cần thư viện ngoài

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.IntStream;

public class BatchFinisherChecks {

    static void check(int count, int batchSize) {
        List<Integer> source = IntStream.range(0, count)
            .boxed()
            .toList();

        List<List<Integer>> actual = source.stream()
            .gather(FixedBatchesDemo.batches(batchSize))
            .toList();

        int expectedNumberOfBatches = count == 0
            ? 0
            : (count - 1) / batchSize + 1;

        if (actual.size() != expectedNumberOfBatches) {
            throw new AssertionError(
                "Sai số batch, N=" + count + ", k=" + batchSize
            );
        }

        ArrayList<Integer> flattened = new ArrayList<>();

        for (List<Integer> batch : actual) {
            if (batch.isEmpty() || batch.size() > batchSize) {
                throw new AssertionError(
                    "Batch rỗng hoặc vượt giới hạn"
                );
            }
            flattened.addAll(batch);
        }

        if (!flattened.equals(source)) {
            throw new AssertionError(
                "Mất, lặp hoặc đảo phần tử"
            );
        }
    }

    public static void main(String[] args) {
        for (int k : new int[] {1, 2, 3, 5, 8}) {
            for (int n = 0; n <= 30; n++) {
                check(n, k);
            }
        }
        System.out.println("PASS");
    }
}
~~~

Các ca này bao gồm:

- Nguồn rỗng.
- Nguồn ngắn hơn batch.
- Nguồn vừa đủ một hoặc nhiều batch.
- Nguồn có phần dư 1 đến `k-1` phần tử.
- Batch size bằng 1.
- Nhiều kích thước nguồn để phát hiện lỗi ranh giới.

### 14.2. Kiểm tra downstream dừng sớm

~~~java
import java.util.List;

List<List<Integer>> result = List.of(
    1, 2, 3, 4, 5, 6, 7
).stream()
    .gather(FixedBatchesDemo.batches(3))
    .limit(1)
    .toList();

if (!result.equals(List.of(List.of(1, 2, 3)))) {
    throw new AssertionError("limit(1) nhận sai batch");
}
~~~

Kiểm thử trên không yêu cầu nguồn phải được duyệt toàn bộ. `limit(1)` chỉ quan tâm một đầu ra, và Gatherer phải tôn trọng điều đó.

### 14.3. Kiểm tra run cuối

~~~java
import java.util.List;

List<RunLengthDemo.Run<String>> actual = List.of(
    "A", "A", "B", "B", "B", "A"
).stream()
    .gather(RunLengthDemo.<String>runs())
    .toList();

List<RunLengthDemo.Run<String>> expected = List.of(
    new RunLengthDemo.Run<>("A", 2),
    new RunLengthDemo.Run<>("B", 3),
    new RunLengthDemo.Run<>("A", 1)
);

if (!actual.equals(expected)) {
    throw new AssertionError("Sai phần run cuối");
}
~~~

Nhờ `Run` là record, `equals` so sánh các trường theo giá trị; bài kiểm tra phát hiện được lỗi **quên phát run cuối** và **phát lặp run đã hoàn tất**.

### 14.4. Kiểm thử với lỗi và null

Ngoài các ca đúng, cần kiểm tra chính sách lỗi:

- `batchSize <= 0` phải bị từ chối.
- `null` trong batch không hợp lệ phải bị phát hiện theo quy tắc.
- `Math.addExact` trong summary có thể ném khi tràn.
- Delimiter liên tiếp và delimiter ở đầu/cuối tạo số nhóm đúng.
- Run-length với null tạo run hợp lệ nếu đã chọn chính sách cho null.

Không suy luận rằng một test trên vài phần tử chứng minh thuật toán đúng với mọi nguồn; mục tiêu của kiểm thử là bao phủ **các ranh giới có ý nghĩa**.

## 15. Hiệu năng và API chuẩn thay cho custom Gatherer

### 15.1. Bộ nhớ state

| Thuật toán | State điển hình | Giới hạn cần lưu ý |
| --- | --- | --- |
| Batch kích thước `k` | Buffer tối đa `k` phần tử | Cấp phát bản sao khi phát |
| Run-length | Giá trị hiện tại + bộ đếm | Kiểm tra overflow bộ đếm |
| Nhóm theo dấu phân cách | Buffer từ dấu phân cách trước | Có thể lớn nếu hiếm delimiter |
| Summary cuối nguồn | Vài biến đếm/tổng | Có thể không phát tới khi EOF |
| Parser đang mở bản ghi | Trạng thái cú pháp + dữ liệu chưa đóng | Cần giới hạn và chính sách EOF |

`finisher` không thể giảm RAM **trước khi kết thúc** nếu integrator tích lũy vô hạn. Với một Stream vô hạn và Gatherer chỉ phát ở finisher, terminal có thể **không bao giờ nhận được đầu ra**, vì không có điểm EOF để kích hoạt phát.

### 15.2. Snapshot có chi phí nhưng cần thiết

`List.copyOf(buffer)` hoặc `new ArrayList<>(buffer)` cần bộ nhớ và công sao chép. Đây là chi phí bảo vệ khỏi lỗi **rò tham chiếu mutable**. Không thay bằng `push(buffer)` rồi `clear` chỉ để giảm một lần cấp phát khi downstream cần giữ dữ liệu.

### 15.3. Nếu chỉ cần cửa sổ cố định, xem Gatherers.windowFixed

Java 24 cung cấp các Gatherer tích hợp sẵn. Khi bài toán đúng là chia thành cửa sổ kích thước cố định, `Gatherers.windowFixed(int)` là lựa chọn nên cân nhắc trước khi tự viết:

~~~java
import java.util.List;
import java.util.stream.Gatherers;

List<List<Integer>> result = List.of(
    1, 2, 3, 4, 5, 6, 7
).stream()
    .gather(Gatherers.windowFixed(3))
    .toList();

System.out.println(result);
// [[1, 2, 3], [4, 5, 6], [7]]
~~~

Viết custom Gatherer khi cần quy tắc chuyên biệt: batch cuối phải đệm hoặc báo lỗi; mỗi batch có metadata; giới hạn theo byte; nhóm theo giao thức nhiều dấu; hoặc phát event cuối với trạng thái nghiệp vụ.

Với bài toán chỉ cần một tổng `sum` hoặc đếm `count`, ưu tiên terminal chuẩn. Không xây Gatherer mới chỉ vì API có khả năng làm được.

## 16. Mười lỗi phổ biến khi viết finisher

### Lỗi 1 — Quên xả buffer cuối

Integrator chỉ phát lô đầy. Nếu không có logic finisher, các phần tử cuối ít hơn batch size bị bỏ.

**Sửa:** kiểm tra state còn dữ liệu và phát phần đuôi theo chính sách.

### Lỗi 2 — Phát thêm một batch rỗng giả

Finisher `push(List.copyOf(buffer))` kể cả khi buffer rỗng.

**Sửa:** chỉ phát khi `!buffer.isEmpty()`.

### Lỗi 3 — Đưa chính buffer mutable ra ngoài

`downstream.push(buffer)` rồi `buffer.clear()` khiến output bị thay đổi sau khi phát.

**Sửa:** snapshot độc lập trước khi làm sạch.

### Lỗi 4 — Không làm sạch state đã phát

Sau batch đầy, không xóa buffer, nên finisher phát lại dữ liệu cũ.

**Sửa:** state chỉ chứa những phần tử **chưa phát**.

### Lỗi 5 — Dùng một buffer chung cho nhiều pipeline

~~~java
// Không nên: initializer luôn trả cùng object mutable.
// ArrayList<String> shared = new ArrayList<>();
// Gatherer.ofSequential(() -> shared, integrator, finisher);
~~~

**Sửa:** initializer tạo state riêng cho từng lần đánh giá.

### Lỗi 6 — Bỏ qua Downstream từ chối

`push` trả false nhưng integrator cứ tiếp tục đọc và đẩy dữ liệu. Finisher không kiểm tra `isRejecting()`.

**Sửa:** trả false từ integrator, và dừng phát nếu downstream từ chối.

### Lỗi 7 — Chính sách null không nhất quán

Lô đầy dùng một container nhận null, nhưng lô cuối dùng `List.copyOf` rồi NPE.

**Sửa:** kiểm tra hoặc chuyển null nhất quán trong cả hai nhánh.

### Lỗi 8 — Coi finisher là hook đóng file/gửi thông báo

Finisher là bước hoàn tất dữ liệu, không phải giao thức side effect bảo đảm.

**Sửa:** xử lý tài nguyên và hành động nghiệp vụ bằng cơ chế riêng.

### Lỗi 9 — Chỉ thêm parallel mà không có combiner đúng

Algorithm phụ thuộc ranh giới liên tiếp nhưng được kỳ vọng tự phân chia và gộp.

**Sửa:** dùng `ofSequential` hoặc thiết kế combiner theo luật kết hợp, kiểm thử nhiều cách chia.

### Lỗi 10 — Chờ EOF trên nguồn vô hạn

Nếu chỉ phát trong finisher, một nguồn không kết thúc sẽ không tạo kết quả cuối.

**Sửa:** phát dần trong integrator hoặc thêm giới hạn/điều kiện kết thúc phù hợp.

## 17. Checklist trước khi bàn giao một custom Gatherer

| Câu hỏi | Câu trả lời cần có |
| --- | --- |
| Input `T` và output `R` là gì? | Kiểu và ý nghĩa từng phần tử |
| State `A` chứa gì? | Chỉ phần chưa phát hoặc thống kê cuối |
| Tại sao cần finisher? | Đầu ra nào chưa đủ điều kiện phát trong integrator |
| State rỗng có phát không? | Quy tắc explicit cho nguồn rỗng |
| Batch cuối thiếu xử lý thế nào? | Giữ, bỏ, đệm hoặc báo lỗi |
| Có chấp nhận null? | Chính sách validate và snapshot thống nhất |
| Đầu ra có cần immutable? | Copy state trước push, xét mutable elements |
| Downstream có thể dừng sớm? | Tôn trọng `push` và `isRejecting()` |
| Có nguồn vô hạn? | Điều kiện kết thúc không phụ thuộc chỉ EOF |
| Có yêu cầu song song? | Combiner đúng, kiểm thử biên phân đoạn |
| Có tài nguyên ngoài cần đóng? | Try-with-resources/close riêng |
| Đã có operation chuẩn? | Cân nhắc `Gatherers.windowFixed`, `collect`, `reduce` |
| Kiểm thử kết quả gì? | Không mất/trùng, rỗng, dư, short-circuit |

## 18. Câu hỏi ôn tập và bài mở rộng

1. **Finisher khác integrator thế nào?** Integrator xử lý từng input; finisher hoàn tất state và có thể phát phần còn lại.
2. **Finisher nhận hai đối số gì?** State tích lũy và `Gatherer.Downstream`.
3. **Finisher có trả trực tiếp một kết quả như Collector.finisher không?** Không; nó dùng `push`, có thể phát nhiều phần tử.
4. **Với 8 phần tử và batch size 3, đầu ra gồm mấy batch?** Ba batch với kích thước 3, 3, 2 nếu giữ đuôi.
5. **Với 6 phần tử và batch size 3, có cần thêm batch rỗng không?** Không.
6. **Nếu nguồn rỗng, một batcher có nên phát `[]` không?** Không theo chính sách giữ batch thực trong bài.
7. **Vì sao phải snapshot trước khi clear?** Tránh downstream giữ tham chiếu tới state mutable.
8. **`List.copyOf` có chấp nhận null không?** Không.
9. **Integrator nên làm gì khi `push` trả false?** Trả false để yêu cầu ngừng input.
10. **Finisher kiểm tra `isRejecting()` để làm gì?** Tránh phát thêm vào downstream đã từ chối.
11. **Run-length encoding cần finisher khi nào?** Để phát run cuối không có giá trị tiếp theo kích hoạt phát.
12. **Vì sao cần cờ `hasValue` nếu phần tử có thể null?** Để phân biệt chưa có dữ liệu và đã thấy null.
13. **Gom theo delimiter gặp EOF không có dấu đóng sẽ ra sao?** Finisher có thể phát nhóm cuối hoặc báo lỗi tùy hợp đồng.
14. **`ofSequential` có cần combiner?** Không; nó dành cho Gatherer tuần tự.
15. **Một parallel gatherer có thể xả từng phần rìa độc lập không?** Không nếu nhóm có thể nằm vắt qua ranh giới; phải gộp state đúng.
16. **Finisher có thay thế việc đóng Stream từ `Files.lines` không?** Không; cần `try-with-resources`.
17. **Bài toán summary một giá trị nên cân nhắc API nào khác?** `reduce`, `collect` hoặc `summaryStatistics`.
18. **Làm thế nào kiểm tra batch không mất/lặp phần tử?** Nối toàn bộ batch và so sánh với input ordered.
19. **Vì sao không dùng finisher làm lệnh gửi email bắt buộc?** Nó là hook biến đổi dữ liệu, không phải hợp đồng giao dịch/side effect.
20. **Nếu nguồn vô hạn và Gatherer chỉ phát trong finisher?** Đầu ra cuối có thể không bao giờ xuất hiện.

### Bài mở rộng A — Batch mang metadata

Sửa batcher để phát `record Batch<T>(long index, List<T> items, boolean complete)`. Batch đủ kích thước có `complete = true`, batch cuối chưa đủ có `complete = false`. Kiểm thử nguồn rỗng và chia hết.

### Bài mở rộng B — Parser có BEGIN/END

Viết Gatherer nhận `BEGIN`, nội dung và `END`. Nếu EOF khi vẫn còn một bản ghi mở, finisher ném exception có thông báo rõ vị trí. Kiểm thử trường hợp hai BEGIN liên tiếp.

### Bài mở rộng C — Nén null

Cho input `Arrays.asList(null, null, "A", null)` vào RunLengthDemo. Kiểm tra kết quả gồm ba run tương ứng null×2, A×1, null×1.

### Bài mở rộng D — Phân biệt giới hạn trước và sau Gatherer

So sánh `source.stream().limit(5).gather(batches(4))` với `source.stream().gather(batches(4)).limit(1)`. Một pipeline giới hạn **số input**, pipeline kia giới hạn **số batch output**, nên không đồng nghĩa.

### Bài mở rộng E — Giới hạn buffer

Trong DelimitedSectionsDemo, thêm giới hạn 1.000 dòng mỗi nhóm. Nếu chưa gặp dấu phân cách mà vượt giới hạn, xác định chính sách báo lỗi hoặc phát nhóm tạm, tránh giữ vô hạn trong state.

**Ghi nhớ:** `Gatherer.finisher()` xử lý phần trạng thái **còn lại khi nguồn hoặc giai đoạn tích lũy kết thúc**. Với batching, delimiter và run-length, nó giúp không bỏ sót lô/nhóm/run cuối. Hãy giữ state chỉ chứa phần chưa phát, tạo snapshot độc lập, tránh phát nhóm rỗng giả, tôn trọng downstream dừng sớm và thống nhất chính sách null. Finisher không thay thế quản lý tài nguyên, không tự giải quyết vấn đề nguồn vô hạn hoặc gộp trạng thái song song; dùng Gatherer chuẩn và collector thông thường khi chúng đã phù hợp.
