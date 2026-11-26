# Thiết kế gatherer tuần tự bằng Gatherer.ofSequential

Stream Gatherers cho phép định nghĩa phép biến đổi trung gian tùy chỉnh trong Stream API. Khi phép biến đổi cần ghi nhớ thông tin giữa các phần tử và phụ thuộc vào thứ tự xử lý, ta có thể thiết kế một gatherer tuần tự bằng @@BT@@Gatherer.ofSequential(...)@@BT@@.

@@BT@@Gatherer.ofSequential@@BT@@ phù hợp với các tác vụ như tính tổng lũy kế, gom dữ liệu theo lô, loại bỏ phần tử trùng liên tiếp hoặc xử lý một chuỗi sự kiện theo thứ tự. Gatherer giữ state riêng trong một lần chạy pipeline, cập nhật state khi nhận từng phần tử và có thể phát ra kết quả cuối cùng khi nguồn kết thúc.

Stream Gatherers từng ở trạng thái preview trong Java 22 và Java 23; API được hoàn thiện trong Java 24 theo JEP 485. Các ví dụ dưới đây dùng API ổn định trong @@BT@@java.util.stream@@BT@@, không cần bật preview feature.

## 1. Khi nào cần Gatherer tuần tự?

Các phép biến đổi như @@BT@@map@@BT@@ và @@BT@@filter@@BT@@ xử lý từng phần tử theo quy tắc đơn giản. Khi logic cần ghi nhớ dữ liệu trước đó, ta cần state.

Ví dụ:

- Tính tổng lũy kế và phát ra tổng sau mỗi phần tử.
- Gom các phần tử liên tiếp thành từng lô rồi phát ra một kết quả cho mỗi lô.
- Phát hiện khi giá trị thay đổi so với phần tử liền trước.
- Xử lý sự kiện theo thứ tự đến, trong đó trạng thái hiện tại phụ thuộc trạng thái trước đó.

Nếu state không thể chia thành các phần độc lập rồi kết hợp lại một cách chính xác, gatherer nên được thiết kế tuần tự. @@BT@@Gatherer.ofSequential@@BT@@ biểu đạt lựa chọn này trực tiếp: gatherer có initializer và integrator, có thể có thêm finisher, nhưng không có combiner để hợp nhất state của các nhánh song song.

Các ví dụ trong bài là những đoạn code đặt bên trong một lớp Java. Với lớp đầy đủ, các import thường dùng gồm `java.util.List`, `java.util.Objects`, `java.util.function.BiConsumer`, `java.util.function.Supplier`, `java.util.stream.Gatherer` và `java.util.stream.Stream`.

## 2. Cấu trúc Gatherer.ofSequential

Một gatherer có kiểu tổng quát:

@@BT@@@@BT@@@@BT@@java
Gatherer<T, A, R>
@@BT@@@@BT@@@@BT@@

Trong đó:

- @@BT@@T@@BT@@: kiểu phần tử đầu vào từ Stream.
- @@BT@@A@@BT@@: kiểu state nội bộ của gatherer.
- @@BT@@R@@BT@@: kiểu phần tử mà gatherer phát ra downstream.

@@BT@@Gatherer.ofSequential@@BT@@ có các overload chính:

@@BT@@@@BT@@@@BT@@java
Gatherer<T, A, R> ofSequential(
    Supplier<A> initializer,
    Gatherer.Integrator<A, T, R> integrator
)

Gatherer<T, A, R> ofSequential(
    Supplier<A> initializer,
    Gatherer.Integrator<A, T, R> integrator,
    BiConsumer<A, Gatherer.Downstream<? super R>> finisher
)
@@BT@@@@BT@@@@BT@@

Overload thứ nhất dành cho gatherer không cần hành động bổ sung khi nguồn kết thúc. Overload thứ hai cho phép xử lý state còn lại sau khi integrator đã nhận hết phần tử, chẳng hạn phát ra lô cuối chưa đủ kích thước.

Ba thành phần trong ví dụ có finisher:

| Thành phần | Kiểu hàm | Trách nhiệm |
|---|---|---|
| Initializer | @@BT@@Supplier<A>@@BT@@ | Tạo state mới cho một lần chạy |
| Integrator | @@BT@@Gatherer.Integrator<A, T, R>@@BT@@ | Nhận phần tử, cập nhật state và đẩy kết quả xuống downstream |
| Finisher | @@BT@@BiConsumer<A, Downstream<? super R>>@@BT@@ | Xử lý state còn lại khi nguồn kết thúc |

Một gatherer tuần tự không cần combiner. Vì vậy, nó không thể chia state thành nhiều phần để chạy integrator song song rồi hợp nhất kết quả.

## 3. Ví dụ: gom các số thành từng lô và tính tổng

Giả sử một luồng số cần được chia thành các lô liên tiếp có kích thước cố định. Mỗi khi nhận đủ số phần tử trong một lô, gatherer phát ra tổng của lô đó. Nếu nguồn kết thúc khi lô cuối chưa đủ phần tử, finisher phát ra tổng còn lại.

Ta cần lưu hai thông tin trong state:

- @@BT@@count@@BT@@: số phần tử đã nhận trong lô hiện tại.
- @@BT@@sum@@BT@@: tổng các phần tử của lô hiện tại.

### Khai báo state

@@BT@@@@BT@@@@BT@@java
static final class BatchState {
    int count;
    long sum;
}
@@BT@@@@BT@@@@BT@@

State là đối tượng có thể thay đổi, chỉ được dùng trong quá trình gatherer xử lý một lần chạy Stream. Không lưu state này vào biến static hoặc chia sẻ nó giữa nhiều pipeline.

### Định nghĩa gatherer

@@BT@@@@BT@@@@BT@@java
static Gatherer<Integer, BatchState, Long> sumBatches(int batchSize) {
    if (batchSize <= 0) {
        throw new IllegalArgumentException("batchSize must be positive");
    }

    return Gatherer.<Integer, BatchState, Long>ofSequential(
        BatchState::new,

        (state, value, downstream) -> {
            state.sum = Math.addExact(state.sum, value.longValue());
            state.count++;

            if (state.count < batchSize) {
                return true;
            }

            long completedSum = state.sum;
            state.sum = 0;
            state.count = 0;

            return downstream.push(completedSum);
        },

        (state, downstream) -> {
            if (state.count > 0) {
                downstream.push(state.sum);
            }
        }
    );
}
@@BT@@@@BT@@@@BT@@

Cách hoạt động:

1. @@BT@@BatchState::new@@BT@@ tạo state mới, ban đầu @@BT@@count@@BT@@ và @@BT@@sum@@BT@@ đều bằng 0.
2. Mỗi lần integrator nhận một @@BT@@Integer@@BT@@, nó cộng giá trị vào @@BT@@sum@@BT@@ và tăng @@BT@@count@@BT@@.
3. Nếu lô chưa đủ phần tử, integrator trả về @@BT@@true@@BT@@ để tiếp tục nhận dữ liệu.
4. Khi lô đủ kích thước, gatherer lưu tổng cần phát ra, đặt state về trạng thái rỗng để bắt đầu lô tiếp theo, rồi gọi @@BT@@downstream.push(completedSum)@@BT@@.
5. Khi nguồn kết thúc, finisher phát ra tổng của lô cuối nếu lô đó còn phần tử.

@@BT@@Math.addExact@@BT@@ được dùng để phát hiện tràn số kiểu @@BT@@long@@BT@@ thay vì âm thầm tạo ra kết quả sai. Nếu tổng vượt phạm vi @@BT@@long@@BT@@, phép cộng ném @@BT@@ArithmeticException@@BT@@.

### Sử dụng trong Stream

@@BT@@@@BT@@@@BT@@java
List<Long> batchTotals = Stream.of(4, 7, 2, 9, 1, 5, 3)
    .gather(sumBatches(3))
    .toList();

System.out.println(batchTotals); // [13, 15, 3]
@@BT@@@@BT@@@@BT@@

Diễn biến:

| Lô | Phần tử nhận được | Kết quả |
|---|---|---:|
| 1 | 4, 7, 2 | 13 |
| 2 | 9, 1, 5 | 15 |
| 3 | 3 | 3 |

Hai lô đầu được phát ra ngay khi đủ ba phần tử. Lô cuối chỉ có một phần tử nên được phát ra trong finisher. Nếu nguồn rỗng, state không có phần tử và finisher không phát ra kết quả nào.

## 4. Vai trò của Integrator và Downstream

Integrator là nơi xử lý từng phần tử. Nó nhận ba tham số:

@@BT@@@@BT@@@@BT@@java
(state, element, downstream) -> {
    // cập nhật state
    // có thể đẩy kết quả xuống downstream
    return true;
}
@@BT@@@@BT@@@@BT@@

@@BT@@state@@BT@@ là state được tạo bởi initializer. @@BT@@element@@BT@@ là phần tử đầu vào hiện tại. @@BT@@downstream@@BT@@ đại diện cho bước tiếp theo trong pipeline.

Phương thức @@BT@@downstream.push(result)@@BT@@ chuyển một kết quả xuống downstream và trả về boolean:

- @@BT@@true@@BT@@: downstream vẫn chấp nhận dữ liệu.
- @@BT@@false@@BT@@: downstream không muốn nhận thêm dữ liệu; integrator nên trả về @@BT@@false@@BT@@ để yêu cầu dừng nhận phần tử từ upstream.

Nếu integrator chưa phát ra kết quả, nó thường trả @@BT@@true@@BT@@ để tiếp tục xử lý. Không nên luôn trả @@BT@@true@@BT@@ sau một lần @@BT@@push@@BT@@ trả về @@BT@@false@@BT@@, vì như vậy gatherer không truyền yêu cầu dừng của downstream lên upstream.

### Tích hợp nhiều kết quả từ một phần tử

Một integrator có thể gọi @@BT@@downstream.push(...)@@BT@@ nhiều lần cho một phần tử đầu vào. Điều này hữu ích khi một phần tử chứa nhiều giá trị cần tách ra. Nếu một lần push trả về false, gatherer cần ngừng phát thêm kết quả và trả false từ integrator.

### Không giữ Downstream bên ngoài lời gọi

@@BT@@Downstream@@BT@@ chỉ được dùng trong thời gian gọi integrator hoặc finisher tương ứng. Không lưu tham chiếu downstream vào state, biến static hoặc một tác vụ chạy sau. State cũng không được giữ lại hay chia sẻ sang thread khác ngoài vòng đời mà API cho phép.

## 5. Vai trò của Initializer và Finisher

### Initializer tạo state mới

Initializer là một @@BT@@Supplier<A>@@BT@@. Nó được gọi để tạo state cho một lần thực thi gatherer:

@@BT@@@@BT@@@@BT@@java
() -> new BatchState()
@@BT@@@@BT@@@@BT@@

Nên tạo state mới mỗi lần initializer được gọi. Nếu trả về cùng một đối tượng mutable dùng chung cho nhiều lần chạy, dữ liệu từ lần chạy trước có thể rò sang lần chạy sau và gây lỗi khó phát hiện.

Có thể dùng một lớp state riêng để đặt tên cho các trường dữ liệu và giữ logic cập nhật tập trung. Với state nhỏ, một mảng hoặc collection cũng có thể dùng được, nhưng lớp riêng thường dễ đọc và dễ bảo trì hơn.

### Finisher xử lý phần dữ liệu còn lại

Finisher chạy sau khi gatherer đã xử lý các phần tử đầu vào mà upstream cung cấp. Nó nhận state cuối cùng và downstream, có thể phát ra thêm kết quả.

Trong ví dụ gom lô, finisher kiểm tra @@BT@@count@@BT@@:

@@BT@@@@BT@@@@BT@@java
(state, downstream) -> {
    if (state.count > 0) {
        downstream.push(state.sum);
    }
}
@@BT@@@@BT@@@@BT@@

Nếu không có phần tử còn lại, finisher không làm gì. Nếu có một lô chưa đủ kích thước, finisher phát ra tổng của lô đó. Với gatherer khác, finisher có thể flush buffer, phát ra thống kê cuối cùng hoặc hoàn tất một kết quả tích lũy.

Nếu gatherer không cần hành động cuối, hãy dùng overload @@BT@@ofSequential(initializer, integrator)@@BT@@ không có finisher.

## 6. Vì sao không có Combiner?

Một gatherer có thể hỗ trợ song song nếu có combiner để hợp nhất state từ các phần dữ liệu khác nhau. @@BT@@Gatherer.ofSequential@@BT@@ không nhận combiner; nó sử dụng combiner mặc định của Gatherer, vốn chỉ cho phép đánh giá tuần tự.

Điều này phù hợp khi:

- Kết quả phụ thuộc thứ tự nhận phần tử.
- State không có phép hợp nhất tương đương giữa các phần.
- Việc chia dữ liệu sẽ làm thay đổi ngữ nghĩa của phép biến đổi.
- Cần giữ cách xử lý đơn giản, dễ kiểm chứng.

Ví dụ, phép tính tổng lũy kế cần giữ tổng của tất cả phần tử trước đó. Nếu chia nguồn thành nhiều partition, mỗi partition có tổng cục bộ riêng. Muốn chạy song song mà vẫn tạo đúng prefix sum, phải thiết kế thêm bước kết hợp và bù giá trị tích lũy cho từng partition. @@BT@@ofSequential@@BT@@ tránh việc giả định rằng state có thể ghép đơn giản.

Nếu bài toán có thể kết hợp state một cách đúng đắn và có lợi khi chạy song song, hãy xem xét @@BT@@Gatherer.of(initializer, integrator, combiner, finisher)@@BT@@. Combiner phải giữ đúng ngữ nghĩa của phép biến đổi; chỉ cộng state hoặc nối collection không phải lúc nào cũng đủ.

Dù nguồn Stream được tạo bằng @@BT@@parallelStream()@@BT@@, không nên kỳ vọng một gatherer tuần tự được song song hóa. Hãy chọn factory dựa trên đặc tính state, không dựa trên việc muốn bật parallel stream.

## 7. Một ví dụ tuần tự khác: chỉ phát ra khi giá trị thay đổi

Một trường hợp khác là loại bỏ các giá trị liên tiếp trùng nhau. Ta cần nhớ phần tử cuối cùng đã phát ra:

@@BT@@@@BT@@@@BT@@java
static final class DistinctState<T> {
    boolean hasPrevious;
    T previous;
}

static <T> Gatherer<T, DistinctState<T>, T> distinctConsecutive() {
    return Gatherer.ofSequential(
        DistinctState<T>::new,
        (state, value, downstream) -> {
            if (state.hasPrevious && Objects.equals(state.previous, value)) {
                return true;
            }

            state.previous = value;
            state.hasPrevious = true;
            return downstream.push(value);
        }
    );
}
@@BT@@@@BT@@@@BT@@

Sử dụng:

@@BT@@@@BT@@@@BT@@java
List<String> result = Stream.of("A", "A", "B", "B", "B", "C", "A", "A")
    .gather(distinctConsecutive())
    .toList();

System.out.println(result); // [A, B, C, A]
@@BT@@@@BT@@@@BT@@

Gatherer chỉ loại bỏ các phần tử trùng liền kề. Giá trị @@BT@@A@@BT@@ xuất hiện lại sau @@BT@@C@@BT@@ vẫn được giữ. Đây không phải phép loại bỏ mọi phần tử trùng lặp trong toàn bộ Stream như @@BT@@distinct()@@BT@@.

State phải cập nhật @@BT@@previous@@BT@@ và @@BT@@hasPrevious@@BT@@ trước khi trả về kết quả từ downstream. Nếu downstream từ chối phần tử, integrator truyền false để kết thúc việc nhận thêm phần tử.

## 8. Những lưu ý khi thiết kế và sử dụng

| Vấn đề | Cách xử lý |
|---|---|
| State bị chia sẻ giữa các lần chạy | Tạo đối tượng state mới trong initializer |
| Kết quả cuối còn nằm trong buffer | Dùng finisher để flush hoặc phát ra phần còn lại |
| Downstream đã từ chối dữ liệu | Trả lại kết quả false của @@BT@@downstream.push@@BT@@ |
| Phép biến đổi phụ thuộc encounter order | Dùng gatherer tuần tự trên một nguồn có encounter order |
| Cần xử lý song song | Thiết kế combiner đúng ngữ nghĩa và dùng @@BT@@Gatherer.of@@BT@@ |
| Có nguy cơ tràn số | Dùng @@BT@@Math.addExact@@BT@@ hoặc quy tắc kiểm tra phù hợp |
| Tài nguyên hoặc state có vòng đời riêng | Giải phóng và hoàn tất đúng trong phạm vi xử lý; không giữ downstream sau lời gọi |

Một số nguyên tắc thực hành:

- Không lưu state mutable trong field dùng chung của gatherer.
- Không giả định integrator chỉ được gọi đúng một lần hoặc chỉ nhận một phần tử.
- Không bỏ qua giá trị boolean trả về từ @@BT@@downstream.push@@BT@@.
- Giữ initializer, integrator và finisher có hành vi nhất quán, không phụ thuộc dữ liệu ngoài pipeline theo cách gây kết quả không xác định.
- Xác định rõ cách xử lý nguồn rỗng và phần dữ liệu chưa hoàn chỉnh khi nguồn kết thúc.
- Nếu thứ tự quan trọng, bảo đảm nguồn có encounter order và tránh loại bỏ thứ tự bằng @@BT@@unordered()@@BT@@.

## 9. Khi nào nên dùng ofSequential thay vì gatherer dựng sẵn?

Java đã cung cấp một số gatherer dựng sẵn trong @@BT@@Gatherers@@BT@@, chẳng hạn @@BT@@scan@@BT@@, @@BT@@fold@@BT@@, @@BT@@windowFixed@@BT@@ và @@BT@@windowSliding@@BT@@. Nên dùng các API đó nếu chúng đã đáp ứng yêu cầu.

Tự định nghĩa @@BT@@Gatherer.ofSequential@@BT@@ khi logic nghiệp vụ có state riêng, quy tắc phát kết quả hoặc hành động cuối mà gatherer dựng sẵn không thể biểu đạt trực tiếp.

| Nhu cầu | Lựa chọn |
|---|---|
| Tính prefix accumulation tiêu chuẩn | @@BT@@Gatherers.scan@@BT@@ |
| Gom cửa sổ cố định | @@BT@@Gatherers.windowFixed@@BT@@ |
| Gom cửa sổ trượt | @@BT@@Gatherers.windowSliding@@BT@@ |
| Tích lũy thành một kết quả cuối | @@BT@@Gatherers.fold@@BT@@ |
| State tùy chỉnh, xử lý tuần tự, có thể flush phần cuối | @@BT@@Gatherer.ofSequential(...)@@BT@@ |
| State có thể hợp nhất đúng cách để xử lý song song | @@BT@@Gatherer.of(...)@@BT@@ |

## Kết luận

@@BT@@Gatherer.ofSequential@@BT@@ là lựa chọn phù hợp để thiết kế phép biến đổi trung gian có state nhưng cần xử lý tuần tự. Initializer tạo state riêng cho một lần chạy, integrator cập nhật state và đẩy kết quả xuống downstream, còn finisher xử lý phần dữ liệu còn lại khi nguồn kết thúc.

Khi thiết kế gatherer, cần xác định rõ state chứa gì, lúc nào phát kết quả, cách kết thúc lô cuối và cách phản hồi khi downstream không nhận thêm dữ liệu. Nếu state không thể kết hợp an toàn, hãy giữ gatherer tuần tự. Nếu cần song song, phải thiết kế combiner có ngữ nghĩa đúng thay vì chỉ thay factory.

Stream Gatherers đã ổn định từ Java 24. Dùng @@BT@@Gatherer.ofSequential@@BT@@ trong các JDK hiện đại không cần preview flag.

## Tài liệu tham khảo

- [JEP 461: Stream Gatherers (Preview), JDK 22](https://openjdk.org/jeps/461)
- [JEP 473: Stream Gatherers (Second Preview), JDK 23](https://openjdk.org/jeps/473)
- [JEP 485: Stream Gatherers, JDK 24](https://openjdk.org/jeps/485)
- [Java SE 24 API — Gatherer.ofSequential](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/util/stream/Gatherer.html)
- [Java SE 24 API — Stream.gather](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/util/stream/Stream.html#gather(java.util.stream.Gatherer))
- [Oracle Java 24 — Stream Gatherers](https://docs.oracle.com/en/java/javase/24/core/stream-gatherers.html)
