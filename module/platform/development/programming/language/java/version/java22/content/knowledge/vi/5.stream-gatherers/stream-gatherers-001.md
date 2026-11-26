# JEP 461 và lộ trình tới API chính thức của Stream Gatherers trong JDK 24

## Trạng thái hiện tại

Stream Gatherers là một phần ổn định của Java SE từ JDK 24. Trong Java 24 trở lên, có thể dùng trực tiếp `Stream.gather(...)`, `Gatherer` và `Gatherers` mà không bật preview. Tài liệu API Java SE 26 vẫn ghi `Gatherer`, `Stream.gather` và các factory trong `Gatherers` có từ phiên bản 24.

Bài học này dùng cú pháp chính thức từ JDK 24 trở lên. Các mốc preview của JDK 22 và 23 chỉ được nhắc để giải thích quá trình hoàn thiện API và yêu cầu phiên bản khi chọn môi trường chạy.

## Lộ trình từ JEP 461 đến API chính thức

| Phiên bản JDK | JEP | Trạng thái | Ý nghĩa |
|---|---|---|---|
| JDK 22 | JEP 461 – Stream Gatherers | Preview lần đầu | Đưa điểm mở rộng cho các intermediate operation do lập trình viên định nghĩa vào Stream API. |
| JDK 23 | JEP 473 – Stream Gatherers (Second Preview) | Preview lần hai | Giữ nguyên thiết kế của vòng preview đầu để tiếp tục thu thập phản hồi và kinh nghiệm sử dụng. |
| JDK 24 | JEP 485 – Stream Gatherers | Chính thức | Hoàn thiện API và đưa nó thành API chuẩn của Java SE. |

JEP 461 giải quyết nhu cầu mở rộng Stream API bằng các phép biến đổi trung gian tùy chỉnh. JEP 473 tiếp tục thử nghiệm thiết kế đó. JEP 485 đưa tính năng vào bản phát hành chính thức của JDK 24. Vì vậy, khi phát triển ứng dụng hiện đại, hãy dựa trên API ổn định của JDK 24 trở lên thay vì hướng dẫn dùng preview của JDK 22 hoặc 23.

Các kiểu và phương thức chính nằm trong package `java.util.stream`:

- `Gatherer<T, A, R>`: mô tả phép biến đổi trung gian.
- `Stream.gather(Gatherer)`: áp dụng gatherer vào một stream và trả về stream mới.
- `Gatherers`: cung cấp năm gatherer dựng sẵn thường dùng.

## Vì sao Stream API cần Gatherers?

Stream API đã có nhiều intermediate operation hữu ích như `map`, `filter`, `flatMap` và `mapMulti`. Tuy nhiên, một tập hợp thao tác cố định không thể diễn đạt gọn mọi phép biến đổi dữ liệu. Một số bài toán cần nhớ các phần tử đã gặp, gom nhiều phần tử thành một nhóm, tạo kết quả tích lũy theo từng bước hoặc dừng đọc đầu vào khi đạt điều kiện.

Ví dụ thường gặp:

- Chia các bản ghi thành từng lô để ghi xuống cơ sở dữ liệu.
- Tạo các cửa sổ trượt để tính toán trên một nhóm phần tử liền kề.
- Tính tổng lũy kế hoặc trạng thái lũy kế sau mỗi phần tử.
- Loại bỏ các phần tử trùng nhau đứng cạnh nhau.
- Thực hiện một số tác vụ độc lập đồng thời với giới hạn số tác vụ đang chạy.

Trước Gatherers, những trường hợp này thường cần kết hợp nhiều thao tác, chuyển dữ liệu sang collection rồi xử lý bằng vòng lặp, hoặc tự viết một abstraction riêng. Gatherer cho phép đóng gói phép biến đổi thành một intermediate operation có thể tái sử dụng và kết hợp với các bước khác trong pipeline.

## Gatherer là gì?

Gatherer là một intermediate operation biến đổi một luồng đầu vào thành một luồng đầu ra. Nó có thể:

- Biến đổi một đầu vào thành một đầu ra, nhiều đầu ra hoặc không có đầu ra.
- Gom nhiều đầu vào thành một đầu ra, hoặc gom thành nhiều nhóm đầu ra.
- Duy trì trạng thái để phần tử hiện tại phụ thuộc vào những phần tử đã xử lý trước đó.
- Phát kết quả dần dần hoặc thực hiện hành động cuối khi đầu vào kết thúc.
- Dừng xử lý sớm khi không cần đọc thêm đầu vào.
- Hỗ trợ xử lý song song nếu có cách kết hợp trạng thái của các phân vùng.

Cách sử dụng trong pipeline rất trực tiếp:

~~~java
List<List<Integer>> batches =
    Stream.of(10, 20, 30, 40, 50, 60, 70)
          .gather(Gatherers.windowFixed(3))
          .toList();
~~~

Kết quả:

~~~text
[[10, 20, 30], [40, 50, 60], [70]]
~~~

`gather` là intermediate operation nên nó vẫn trả về một `Stream`. Việc thực thi pipeline vẫn diễn ra khi có terminal operation như `toList`, `findFirst` hoặc `forEach`.

### Ba tham số kiểu của Gatherer

Khai báo tổng quát của interface là:

~~~java
Gatherer<T, A, R>
~~~

| Tham số | Vai trò | Ví dụ |
|---|---|---|
| `T` | Kiểu phần tử đầu vào | `Integer` |
| `A` | Kiểu trạng thái trung gian mà gatherer quản lý | `ArrayList<Integer>` hoặc một lớp State riêng |
| `R` | Kiểu phần tử đầu ra | `List<Integer>` |

Trạng thái `A` có thể thay đổi trong lúc xử lý. Nó thường được ẩn khỏi mã gọi thông qua wildcard, chẳng hạn `Gatherer<Integer, ?, Integer>`.

### Bốn thành phần tạo nên một Gatherer

Một gatherer có thể được mô tả bằng bốn hàm. Tùy bài toán, một số hàm có thể dùng triển khai mặc định.

| Thành phần | Chức năng |
|---|---|
| `initializer()` | Tạo trạng thái mới cho một lần xử lý hoặc một phân vùng. |
| `integrator()` | Nhận một phần tử đầu vào, cập nhật trạng thái và có thể gửi kết quả xuống bước tiếp theo. |
| `combiner()` | Kết hợp hai trạng thái trung gian khi xử lý song song. |
| `finisher()` | Thực hiện hành động cuối hoặc phát thêm kết quả sau khi đã đọc hết đầu vào. |

Trong đó, integrator là thành phần bắt buộc. Nó nhận ba đối số: trạng thái hiện tại, phần tử đầu vào và đối tượng `Downstream`.

~~~java
(state, element, downstream) -> {
    // Cập nhật state nếu cần.
    // Gọi downstream.push(value) để phát kết quả.
    return true; // Tiếp tục nhận phần tử đầu vào.
}
~~~

`downstream.push(value)` chuyển một kết quả sang bước kế tiếp và trả về `boolean` cho biết bước tiếp theo còn muốn nhận kết quả hay không. Integrator cũng trả về `boolean`: `true` để tiếp tục đọc đầu vào, `false` để kết thúc việc tích hợp. Khi không cần tự dừng sớm, có thể dùng `Gatherer.Integrator.ofGreedy(...)` để biểu thị integrator xử lý toàn bộ đầu vào, trừ trường hợp downstream từ chối nhận thêm.

### Khác nhau giữa Gatherer và Collector

Hai abstraction này cùng hỗ trợ gom và biến đổi dữ liệu, nhưng hoạt động ở hai vị trí khác nhau trong pipeline.

| Tiêu chí | Gatherer | Collector |
|---|---|---|
| Loại thao tác | Intermediate operation | Terminal reduction |
| Cách gọi | `stream.gather(gatherer)` | `stream.collect(collector)` |
| Kết quả trực tiếp | Một `Stream` mới | Một kết quả cuối cùng |
| Mục đích | Biến đổi luồng để các bước sau tiếp tục xử lý | Gom luồng thành collection hoặc một giá trị |

Dùng Collector khi mục tiêu là tạo kết quả cuối cùng như `List`, `Map` hoặc chuỗi. Dùng Gatherer khi cần thêm một bước biến đổi có thể đặt giữa các intermediate operation khác.

## Năm gatherer dựng sẵn trong Gatherers

JDK cung cấp năm phương thức dựng sẵn trong lớp `Gatherers`. Chúng giải quyết những mẫu xử lý phổ biến mà không cần tự cài đặt interface.

### 1. windowFixed: chia thành các nhóm cố định

`windowFixed(n)` gom các phần tử liên tiếp thành nhóm có tối đa `n` phần tử. Nhóm cuối cùng có thể ít phần tử hơn nếu tổng số phần tử không chia hết cho kích thước cửa sổ.

~~~java
List<List<Integer>> batches =
    Stream.of(1, 2, 3, 4, 5, 6, 7, 8)
          .gather(Gatherers.windowFixed(3))
          .toList();
~~~

Kết quả:

~~~text
[[1, 2, 3], [4, 5, 6], [7, 8]]
~~~

Ứng dụng: chia danh sách bản ghi thành từng lô để gửi đến dịch vụ bên ngoài, ghi dữ liệu theo batch hoặc xử lý từng nhóm có giới hạn kích thước.

Kích thước cửa sổ phải lớn hơn 0. Các danh sách cửa sổ được trả về là danh sách không thể sửa đổi. Tài liệu API lưu ý rằng cửa sổ có thể được cấp phát liền kề và sớm; vì vậy, kích thước cửa sổ lớn trên một stream nhỏ có thể tiêu thụ nhiều bộ nhớ.

### 2. windowSliding: tạo cửa sổ trượt

`windowSliding(n)` tạo các nhóm có kích thước tối đa `n`. Mỗi nhóm mới giữ lại các phần tử của nhóm trước, bỏ phần tử cũ nhất rồi thêm phần tử tiếp theo.

~~~java
List<List<Integer>> windows =
    Stream.of(1, 2, 3, 4, 5)
          .gather(Gatherers.windowSliding(3))
          .toList();
~~~

Kết quả:

~~~text
[[1, 2, 3], [2, 3, 4], [3, 4, 5]]
~~~

Ứng dụng: tính trung bình trượt, phân tích chuỗi thời gian, kiểm tra một nhóm sự kiện gần nhau hoặc so sánh các đoạn dữ liệu liền kề.

Nếu stream rỗng thì không có cửa sổ nào được tạo. Nếu stream có ít phần tử hơn kích thước cửa sổ thì chỉ có một cửa sổ chứa toàn bộ các phần tử đó. Kích thước cửa sổ phải lớn hơn 0 và các danh sách kết quả không thể sửa đổi.

### 3. scan: tạo giá trị tích lũy sau mỗi phần tử

`scan(initial, scanner)` thực hiện phép tích lũy tiền tố. Nó lấy trạng thái ban đầu từ `Supplier`, cập nhật trạng thái với từng phần tử và phát trạng thái mới sau mỗi lần cập nhật.

~~~java
List<Integer> runningTotals =
    Stream.of(10, 20, 5)
          .gather(Gatherers.scan(() -> 0, Integer::sum))
          .toList();
~~~

Kết quả:

~~~text
[10, 30, 35]
~~~

Giá trị ban đầu `0` được dùng làm trạng thái bắt đầu, không được phát thành một phần tử riêng. Với mỗi đầu vào, gatherer phát tổng mới tương ứng.

Ứng dụng: tính tổng lũy kế, số dư sau mỗi giao dịch, số lượng tích lũy hoặc trạng thái tiến trình theo từng sự kiện.

### 4. fold: gộp toàn bộ đầu vào thành một kết quả

`fold(initial, folder)` thực hiện phép gộp có thứ tự. Nó giữ một giá trị tích lũy và cập nhật giá trị đó khi đọc từng phần tử. Nếu xử lý không gặp ngoại lệ, gatherer phát một kết quả duy nhất.

~~~java
import java.util.StringJoiner;

String path =
    Stream.of("orders", "payments", "shipping")
          .gather(Gatherers.fold(
              () -> new StringJoiner(" -> "),
              StringJoiner::add
          ))
          .map(StringJoiner::toString)
          .findFirst()
          .orElse("");
~~~

Kết quả:

~~~text
orders -> payments -> shipping
~~~

Ứng dụng: xây dựng chuỗi theo thứ tự sự kiện hoặc thực hiện một phép gộp mà không có combiner phù hợp. `fold` là phép gộp có thứ tự; nếu cần phát trạng thái sau mỗi phần tử thì dùng `scan`.

### 5. mapConcurrent: ánh xạ nhiều phần tử đồng thời có giới hạn

`mapConcurrent(maxConcurrency, mapper)` gọi hàm ánh xạ trên nhiều phần tử cùng lúc, với số tác vụ đồng thời tối đa do ứng dụng chỉ định. API sử dụng virtual thread và vẫn giữ thứ tự gặp của stream trong kết quả.

~~~java
List<Customer> customers =
    customerIds.stream()
               .gather(Gatherers.mapConcurrent(8, this::loadCustomer))
               .toList();
~~~

Trong ví dụ, `loadCustomer` có thể đại diện cho thao tác tải thông tin khách hàng độc lập, chẳng hạn gọi một dịch vụ bên ngoài. Giá trị `8` giới hạn số thao tác đang được thực hiện đồng thời.

Ứng dụng: gọi nhiều dịch vụ hoặc đọc nhiều nguồn dữ liệu độc lập trong khi vẫn kiểm soát số yêu cầu đang chạy. Hãy chọn giới hạn phù hợp với khả năng của dịch vụ đích và tài nguyên của ứng dụng. Kết quả vẫn theo thứ tự đầu vào; thứ tự các tác vụ bắt đầu hoặc hoàn thành có thể khác nhau. Nếu mapper gặp lỗi khi kết quả tương ứng cần được phát, API sẽ ném lại lỗi dưới dạng `RuntimeException` và hủy các tác vụ còn lại.

## Tự tạo Gatherer

Khi năm gatherer dựng sẵn chưa đáp ứng yêu cầu, có thể tạo gatherer bằng cách triển khai interface hoặc dùng factory method `Gatherer.of(...)` và `Gatherer.ofSequential(...)`.

Ví dụ sau loại bỏ các phần tử trùng nhau đứng cạnh nhau. Nó cần nhớ phần tử trước đó, vì vậy có một trạng thái trung gian:

~~~java
import java.util.Objects;
import java.util.stream.Gatherer;

final class GathererExamples {
    static <T> Gatherer<T, ?, T> distinctAdjacent() {
        class State {
            T previous;
            boolean hasPrevious;
        }

        return Gatherer.<T, State, T>ofSequential(
            State::new,
            Gatherer.Integrator.ofGreedy((state, element, downstream) -> {
                if (!state.hasPrevious
                        || !Objects.equals(state.previous, element)) {
                    state.previous = element;
                    state.hasPrevious = true;
                    return downstream.push(element);
                }
                return !downstream.isRejecting();
            })
        );
    }
}
~~~

Cách sử dụng:

~~~java
List<String> result =
    Stream.of("A", "A", "B", "B", "B", "C", "A")
          .gather(GathererExamples.distinctAdjacent())
          .toList();
~~~

Kết quả:

~~~text
[A, B, C, A]
~~~

Trong ví dụ này:

- `State` giữ phần tử gần nhất và cờ cho biết đã xử lý phần tử nào chưa.
- `State::new` tạo trạng thái mới cho lần xử lý.
- Integrator so sánh phần tử hiện tại với phần tử trước bằng `Objects.equals`.
- Nếu phần tử khác phần tử trước, nó cập nhật trạng thái và gửi phần tử xuống downstream.
- Nếu phần tử giống phần tử trước, nó bỏ qua phần tử đó.
- `ofSequential` biểu thị gatherer này chỉ xử lý tuần tự vì ví dụ chưa cung cấp cách kết hợp hai trạng thái.

Đây là ví dụ về một phép biến đổi có trạng thái. Nếu chỉ cần ánh xạ độc lập từng phần tử, hãy ưu tiên `map`; nếu chỉ cần phát không hoặc nhiều kết quả cho từng phần tử mà không cần trạng thái giữa các phần tử, hãy xem xét `mapMulti`.

## Kết hợp nhiều Gatherer

Gatherer có thể được đặt liên tiếp trong pipeline hoặc kết hợp bằng `andThen`. Ví dụ, tính tổng lũy kế rồi chia kết quả thành từng cặp:

~~~java
Gatherer<Integer, ?, Integer> runningTotal =
    Gatherers.scan(() -> 0, Integer::sum);

List<List<Integer>> groupedTotals =
    Stream.of(2, 3, 5, 7, 11)
          .gather(runningTotal)
          .gather(Gatherers.windowFixed(2))
          .toList();
~~~

Kết quả:

~~~text
[[2, 5], [10, 17], [28]]
~~~

Có thể viết hai gatherer thành một phép kết hợp:

~~~java
List<List<Integer>> groupedTotals =
    Stream.of(2, 3, 5, 7, 11)
          .gather(runningTotal.andThen(Gatherers.windowFixed(2)))
          .toList();
~~~

Cách kết hợp này giúp đóng gói một chuỗi phép biến đổi thành một gatherer có thể tái sử dụng.

## Xử lý song song và các lưu ý khi thiết kế

Có thể gọi `parallel()` trên stream, nhưng điều đó không tự động làm cho mọi gatherer chạy song song. Gatherer cần có combiner hợp lệ để ghép trạng thái của các phân vùng. Nếu dùng combiner mặc định hoặc factory `ofSequential`, gatherer chỉ được đánh giá tuần tự.

Khi tự cài đặt gatherer có hỗ trợ song song, cần bảo đảm:

1. Initializer tạo trạng thái độc lập cho từng lần xử lý hoặc từng phân vùng.
2. Combiner kết hợp đúng hai trạng thái trung gian và giữ được ngữ nghĩa của phép biến đổi.
3. Trạng thái không bị chia sẻ tùy tiện giữa các luồng.
4. Finisher chỉ phát kết quả cuối phù hợp với trạng thái đã được tích lũy.
5. Không lưu giữ hoặc chuyển đối tượng `Downstream` sang luồng khác hay sử dụng nó lâu hơn thời gian gọi integrator/finisher.

Không nên thêm combiner chỉ để bật song song. Với phép biến đổi phụ thuộc chặt vào thứ tự, chi phí kết hợp trạng thái có thể cao hoặc không thể bảo đảm kết quả đúng. Hãy giữ xử lý tuần tự nếu đó là mô hình phù hợp. Riêng `mapConcurrent` đã cung cấp cách chạy mapper đồng thời có giới hạn mà không yêu cầu chuyển toàn bộ stream sang parallel stream.

Một số lưu ý thực tế:

- Dùng `windowFixed` khi các nhóm không chồng lấp; dùng `windowSliding` khi cần các nhóm chồng lấp.
- Dùng `scan` khi cần mọi trạng thái tích lũy; dùng `fold` khi chỉ cần kết quả gộp cuối cùng.
- Các cửa sổ do `windowFixed` và `windowSliding` tạo ra là danh sách không thể sửa đổi.
- Chọn kích thước cửa sổ hợp lý vì cửa sổ lớn có thể làm tăng mức sử dụng bộ nhớ.
- Với `mapConcurrent`, đặt giới hạn đồng thời theo khả năng chịu tải của dịch vụ hoặc tài nguyên đích.
- Không dùng side effect bên ngoài làm cơ chế lưu trạng thái của gatherer; hãy quản lý trạng thái qua initializer và integrator.

## Chọn API theo bài toán

| Nhu cầu | API nên xem xét |
|---|---|
| Biến đổi độc lập từng phần tử | `map` |
| Lọc phần tử | `filter` |
| Phát không hoặc nhiều phần tử cho mỗi đầu vào | `flatMap` hoặc `mapMulti` |
| Chia thành nhóm cố định | `Gatherers.windowFixed` |
| Tạo nhóm chồng lấp | `Gatherers.windowSliding` |
| Tính trạng thái tích lũy sau từng phần tử | `Gatherers.scan` |
| Gộp thành một kết quả theo thứ tự | `Gatherers.fold` |
| Chạy mapper đồng thời với giới hạn | `Gatherers.mapConcurrent` |
| Tạo phép biến đổi trung gian có trạng thái riêng | `Gatherer.of` hoặc `Gatherer.ofSequential` |
| Gom stream thành kết quả cuối cùng | `collect` với `Collector` |

## Phiên bản Java cần dùng

- Dùng JDK 24 trở lên để sử dụng Stream Gatherers như API chính thức.
- Các ví dụ trong bài không cần `--enable-preview`.
- JDK 22 và JDK 23 chỉ có các phiên bản preview của API; mã thử nghiệm từ hai phiên bản đó không phải mốc triển khai ổn định cho ứng dụng mới.
- Khi dự án cần chạy trên JDK cũ hơn 24, hãy kiểm tra lại baseline và chọn cách triển khai tương thích trước khi dùng `Stream.gather`.

## Tài liệu tham khảo

- [JEP 461 – Stream Gatherers (Preview)](https://openjdk.org/jeps/461)
- [JEP 473 – Stream Gatherers (Second Preview)](https://openjdk.org/jeps/473)
- [JEP 485 – Stream Gatherers](https://openjdk.org/jeps/485)
- [JDK 22 Release Notes](https://www.oracle.com/java/technologies/javase/22-relnote-issues.html)
- [JDK 23 Release Notes](https://www.oracle.com/java/technologies/javase/23-relnote-issues.html)
- [JDK 24 Release Notes](https://www.oracle.com/java/technologies/javase/24-relnote-issues.html)
- [Gatherer – Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Gatherer.html)
- [Gatherers – Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Gatherers.html)
- [Stream – Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Stream.html)

