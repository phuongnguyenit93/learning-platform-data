# Thiết kế gatherer có thể chạy song song và ghép trạng thái đúng thứ tự

## Mục tiêu

Sau bài học này, bạn có thể:

- Mô tả vai trò của `initializer`, `integrator`, `combiner` và `finisher` trong một `Gatherer`.
- Xác định khi nào một gatherer có thể chạy trên parallel stream.
- Thiết kế hàm `combiner` để ghép các trạng thái riêng của từng phân vùng mà vẫn giữ encounter order.
- Nhận biết khi nào chi phí ghép trạng thái khiến xử lý song song không còn có lợi.

## Phiên bản API cần sử dụng

Stream Gatherers được giới thiệu dưới dạng preview trong Java 22 và được chuẩn hóa thành API chính thức từ JDK 24 theo JEP 485. Vì vậy, các ví dụ trong bài dùng `Gatherer`, `Stream.gather()` và `Gatherers` theo API ổn định của JDK 24 trở lên; không cần bật preview bằng `--enable-preview`.

Một `Gatherer<T, A, R>` là một intermediate operation biến các phần tử đầu vào kiểu `T` thành không, một hoặc nhiều phần tử đầu ra kiểu `R`. Kiểu `A` là trạng thái trung gian mà gatherer sử dụng để ghi nhớ dữ liệu giữa các lần xử lý phần tử. Gatherer có thể xử lý trạng thái ngay khi đọc phần tử hoặc giữ dữ liệu để phát kết quả ở cuối luồng.

Khả năng chạy song song phụ thuộc vào cách gatherer kết hợp trạng thái. Gọi `parallel()` trên stream không tự làm cho một gatherer tuần tự trở thành gatherer song song.

## Bốn thành phần của Gatherer

| Thành phần | Vai trò | Câu hỏi cần trả lời khi thiết kế |
|---|---|---|
| `initializer()` | Tạo trạng thái ban đầu kiểu `A`. | Mỗi lần xử lý một phân vùng cần trạng thái riêng nào? |
| `integrator()` | Nhận một phần tử `T`, cập nhật trạng thái và có thể đẩy kết quả `R` xuống downstream. | Cần ghi nhận hoặc phát ra điều gì cho từng phần tử? |
| `combiner()` | Ghép hai trạng thái được tạo khi xử lý các phân vùng khác nhau. | Làm thế nào để kết quả sau khi ghép tương đương xử lý toàn bộ đoạn dữ liệu theo đúng thứ tự? |
| `finisher()` | Thực hiện bước cuối sau khi đã xử lý hết đầu vào; có thể phát thêm kết quả. | Có dữ liệu còn lại cần phát ra hoặc hoàn tất không? |

Trong một gatherer có trạng thái, bốn thành phần phối hợp như sau:

1. `initializer()` tạo trạng thái mới.
2. `integrator()` xử lý lần lượt các phần tử trong phạm vi dữ liệu được giao và cập nhật trạng thái đó.
3. Khi chạy song song, `combiner()` ghép trạng thái của các phân vùng sau khi chúng đã được xử lý.
4. `finisher()` nhận trạng thái cuối cùng và phát các kết quả còn lại xuống downstream.

`Gatherer.of(initializer, integrator, combiner, finisher)` tạo gatherer có khả năng được thực thi song song. Nếu không có phép ghép trạng thái đúng, dùng `Gatherer.ofSequential(...)` để xác định rõ gatherer chỉ chạy tuần tự.

## Vì sao phải thiết kế combiner cẩn thận?

Một parallel stream có thể chia nguồn dữ liệu thành nhiều phân vùng. Mỗi phân vùng được xử lý với trạng thái riêng, sau đó các trạng thái được ghép lại. Cách làm này tránh việc nhiều luồng cùng sửa một đối tượng trạng thái dùng chung.

Ví dụ, một nguồn có encounter order gồm:

```text
[10, 20, 30, 40, 50, 60]
```

Framework có thể chia nguồn thành các đoạn liên tiếp như sau:

```text
Phân vùng trái:  [10, 20, 30]
Phân vùng phải:  [40, 50, 60]
```

Mỗi phân vùng có trạng thái riêng. `combiner()` phải ghép trạng thái đại diện cho đoạn đứng trước với trạng thái đại diện cho đoạn đứng sau. Nếu đảo hai phía, kết quả có thể sai thứ tự dù từng phân vùng đã được xử lý đúng.

Một phép ghép phù hợp với parallel stream cần đáp ứng hai yêu cầu:

- **Kết quả nhất quán khi thay đổi cách chia phân vùng:** framework có thể ghép các kết quả từng cặp theo nhiều cấu trúc khác nhau. Vì vậy, phép ghép cần có tính kết hợp (*associative*): `(a ghép b) ghép c` phải tương đương `a ghép (b ghép c)`.
- **Bảo toàn encounter order khi thứ tự có ý nghĩa:** với nguồn có thứ tự, dữ liệu của đoạn trước phải đứng trước dữ liệu của đoạn sau. Phép ghép không nhất thiết phải có tính giao hoán (*commutative*); nối danh sách trái rồi phải là ví dụ về phép ghép có tính kết hợp nhưng không giao hoán.

Nếu nguồn không có encounter order hoặc pipeline gọi `unordered()`, ứng dụng không thể dựa vào một thứ tự toàn cục cố định. Khi kết quả phụ thuộc thứ tự, hãy giữ nguồn có thứ tự và không loại bỏ ràng buộc encounter order.

## Ví dụ: tạo các cặp phần tử liền kề

Ta xây dựng một gatherer nhận các số và phát ra từng cặp phần tử liền kề. Với đầu vào `[10, 20, 30, 40, 50]`, kết quả mong muốn là:

```text
[[10, 20], [20, 30], [30, 40], [40, 50]]
```

Điểm quan trọng nằm ở cặp `[20, 30]`: nếu hai phần tử thuộc hai phân vùng khác nhau, gatherer vẫn phải tạo được cặp nằm qua ranh giới phân vùng.

### Cài đặt gatherer

```java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Gatherer;

public class OrderedPairs {

    static <T> Gatherer<T, ArrayList<T>, List<T>> adjacentPairs() {
        return Gatherer.<T, ArrayList<T>, List<T>>of(
            // Mỗi phân vùng nhận một ArrayList độc lập.
            ArrayList::new,

            // Tích lũy phần tử vào trạng thái của phân vùng.
            (state, element, downstream) -> {
                state.add(element);
                return true;
            },

            // Ghép đoạn bên phải vào sau đoạn bên trái.
            (left, right) -> {
                left.addAll(right);
                return left;
            },

            // Chỉ tạo các cặp sau khi đã có trạng thái hoàn chỉnh.
            (state, downstream) -> {
                for (int i = 0; i + 1 < state.size(); i++) {
                    List<T> pair = List.of(state.get(i), state.get(i + 1));
                    if (!downstream.push(pair)) {
                        break;
                    }
                }
            }
        );
    }

    public static void main(String[] args) {
        List<List<Integer>> pairs = List.of(10, 20, 30, 40, 50)
            .parallelStream()
            .gather(adjacentPairs())
            .toList();

        System.out.println(pairs);
    }
}
```

Kết quả:

```text
[[10, 20], [20, 30], [30, 40], [40, 50]]
```

### Phân tích từng thành phần

**`initializer()`** dùng `ArrayList::new` để tạo vùng lưu trữ riêng. Khi framework chia nguồn thành nhiều phân vùng, mỗi phân vùng được khởi tạo với một danh sách riêng. Không có danh sách tĩnh hoặc danh sách dùng chung giữa các luồng.

**`integrator()`** thêm phần tử vào danh sách của phân vùng rồi trả về `true` để tiếp tục nhận đầu vào. Integrator không phát cặp ngay vì phần tử cuối của một phân vùng có thể cần ghép với phần tử đầu của phân vùng tiếp theo.

**`combiner()`** thực hiện `left.addAll(right)` và trả về `left`. Trạng thái của đoạn bên phải được nối sau trạng thái của đoạn bên trái. Phép nối danh sách có tính kết hợp, do đó kết quả vẫn đúng khi framework ghép nhiều phân vùng theo các nhóm khác nhau.

**`finisher()`** chạy sau khi trạng thái đã được ghép. Nó duyệt danh sách hoàn chỉnh và tạo các cặp ở mọi vị trí liền kề. Vì danh sách đã chứa phần tử qua ranh giới các phân vùng, những cặp như `[20, 30]` cũng được tạo ra. `downstream.push()` trả về `false` khi downstream không muốn nhận thêm kết quả; finisher dừng phát phần tử trong trường hợp đó.

Ví dụ này cố ý giữ toàn bộ đầu vào trong bộ nhớ để làm rõ cách ghép trạng thái và xử lý ranh giới phân vùng. Chi phí bộ nhớ là O(n), và kết quả chỉ được phát ở cuối luồng. Đây là ví dụ học cách thiết kế combiner, không phải mẫu tối ưu cho mọi bài toán.

## Quy tắc bảo toàn thứ tự và tính độc lập của trạng thái

Khi thiết kế một gatherer song song, hãy kiểm tra các điểm sau:

1. **Khởi tạo trạng thái riêng:** `initializer()` phải tạo đối tượng mới cho mỗi lần được gọi. Không trả về cùng một `ArrayList` tĩnh hoặc dùng chung một biến mutable bên ngoài.
2. **Không dựa vào thứ tự chạy của thread:** các integrator của những phân vùng khác nhau có thể chạy đồng thời. Không dùng thời điểm hoàn tất hoặc tên thread để suy ra vị trí phần tử trong nguồn.
3. **Ghép đúng hướng:** với phép biến đổi phụ thuộc encounter order, ghép trạng thái của đoạn trước rồi đến đoạn sau. Không đảo hai trạng thái chỉ vì muốn tái sử dụng một đối tượng cụ thể.
4. **Bảo đảm tính kết hợp:** kết quả không được phụ thuộc vào việc framework ghép `(A + B) + C` hay `A + (B + C)`.
5. **Xử lý dữ liệu qua ranh giới phân vùng:** nếu một kết quả cần phần tử ở cả hai phía ranh giới, trạng thái phải giữ đủ thông tin để tạo kết quả đó sau khi ghép, hoặc combiner phải tự xử lý phần giao nhau.
6. **Không giữ tham chiếu downstream hoặc trạng thái ngoài thời gian gọi:** không lưu các tham chiếu này vào field dùng về sau hoặc chuyển chúng cho thread khác.

Một gatherer không cần phải có combiner giao hoán nếu stream có encounter order. Điều cần thiết là phép ghép phải bảo toàn thứ tự và cho kết quả nhất quán với mọi cách nhóm phép ghép hợp lệ.

## Khi nào gatherer thực sự chạy song song?

| Cách tạo gatherer | Khả năng thực thi |
|---|---|
| `Gatherer.of(initializer, integrator, combiner, finisher)` | Có thể chạy song song vì đã cung cấp combiner. |
| `Gatherer.of(integrator)` | Gatherer không trạng thái và có thể chạy song song. |
| `Gatherer.ofSequential(initializer, integrator, finisher)` | Chỉ chạy tuần tự. |
| Gatherer dùng `Gatherer.defaultCombiner()` | Chỉ chạy tuần tự, kể cả khi stream nguồn là parallel. |

Có combiner chỉ làm cho gatherer **có khả năng** chạy song song. Framework vẫn quyết định cách thực thi phù hợp; parallel stream không bảo đảm nhanh hơn. Nếu combiner phải sao chép một lượng dữ liệu lớn, chi phí ghép có thể lớn hơn lợi ích của việc xử lý đồng thời.

Nếu phép biến đổi phụ thuộc chặt chẽ vào trạng thái tích lũy trước đó và không thể tạo một combiner đúng, hãy dùng `Gatherer.ofSequential(...)`. API `Gatherers.fold(...)` cũng phù hợp với phép gộp có thứ tự mà không thể xây dựng combiner.

## Chọn gatherer có sẵn khi bài toán đã được hỗ trợ

Trước khi tự viết gatherer, hãy kiểm tra lớp `java.util.stream.Gatherers`:

| API | Công dụng |
|---|---|
| `Gatherers.windowFixed(size)` | Gom phần tử thành các cửa sổ có kích thước cố định; cửa sổ cuối có thể ngắn hơn. |
| `Gatherers.windowSliding(size)` | Tạo các cửa sổ trượt, mỗi cửa sổ kế tiếp giữ các phần tử cũ trừ phần tử đầu và thêm phần tử tiếp theo. |
| `Gatherers.scan(initial, scanner)` | Phát từng kết quả tích lũy theo tiền tố của luồng. |
| `Gatherers.fold(initial, folder)` | Thực hiện phép gộp có thứ tự và chỉ phát kết quả cuối. |
| `Gatherers.mapConcurrent(maxConcurrency, mapper)` | Ánh xạ các phần tử đồng thời với giới hạn số tác vụ đang chạy và giữ encounter order của kết quả. |

Ví dụ, nếu mục tiêu chỉ là tạo cặp phần tử liền kề, có thể dùng gatherer dựng sẵn:

```java
import java.util.List;
import java.util.stream.Gatherers;

List<List<Integer>> pairs = List.of(10, 20, 30, 40, 50).stream()
    .gather(Gatherers.windowSliding(2))
    .toList();
```

Tự viết gatherer khi cần quy tắc chuyển đổi riêng mà các intermediate operation hoặc gatherer dựng sẵn chưa đáp ứng. Điều này giúp giảm mã trạng thái tùy biến và tránh phải tự chịu trách nhiệm cho các trường hợp biên đã được API chuẩn xử lý.

## Các lỗi thiết kế thường gặp

- **Bỏ qua combiner rồi gọi `parallel()`:** gatherer vẫn chỉ được đánh giá tuần tự nếu dùng combiner mặc định.
- **Dùng một trạng thái mutable chung:** nhiều phân vùng có thể sửa cùng đối tượng, gây race condition và kết quả không xác định.
- **Ghép ngược hai trạng thái:** kết quả có thể đảo thứ tự hoặc làm sai các phần tử nằm qua ranh giới phân vùng.
- **Viết combiner không có tính kết hợp:** kết quả thay đổi theo cách framework nhóm các phân vùng.
- **Phát kết quả quá sớm:** nếu kết quả phụ thuộc phần tử ở phân vùng kế tiếp, phát trong integrator có thể làm mất thông tin cần thiết để xử lý ranh giới.
- **Giả định parallel luôn nhanh hơn:** việc tạo trạng thái, đồng bộ luồng và ghép dữ liệu đều có chi phí; cần đo với dữ liệu thực tế.

## Tự kiểm tra

1. Vì sao một gatherer có `defaultCombiner()` vẫn chạy tuần tự dù stream đã gọi `parallel()`?
2. Trong ví dụ `adjacentPairs()`, vì sao `combiner()` phải nối `right` vào sau `left`?
3. Tính kết hợp của phép ghép giúp kết quả ổn định như thế nào khi framework chia dữ liệu thành nhiều phân vùng?
4. Vì sao ví dụ `adjacentPairs()` cần giữ toàn bộ đầu vào đến `finisher()` để tạo cặp nằm qua ranh giới phân vùng?
5. Khi nào nên chọn `Gatherer.ofSequential()` hoặc một gatherer dựng sẵn thay vì tự cài đặt combiner?

## Tài liệu tham khảo

- [JEP 485: Stream Gatherers](https://openjdk.org/jeps/485)
- [Gatherer — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Gatherer.html)
- [Gatherers — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Gatherers.html)
- [Stream — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Stream.html)
