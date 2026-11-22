# `Stream.dropWhile` và phần còn lại sau tiền tố

Từ Java 9, `Stream` có phương thức trung gian `dropWhile(Predicate)`. Phương thức này bỏ các phần tử khớp điều kiện ở **đầu luồng** và trả về phần còn lại, bắt đầu từ phần tử đầu tiên không khớp điều kiện. Với stream có encounter order, nó bỏ đúng tiền tố dài nhất thỏa mãn predicate.

`dropWhile` hữu ích khi dữ liệu đã có thứ tự và ta muốn bỏ một đoạn mở đầu theo điều kiện, sau đó giữ nguyên toàn bộ phần đuôi. Nó khác `filter`: `filter` kiểm tra từng phần tử trong toàn bộ stream, còn `dropWhile` chỉ bỏ đoạn tiền tố liên tiếp.

## 1. Cú pháp và giá trị trả về

```java
Stream<T> dropWhile(Predicate<? super T> predicate)
```

- Đây là **intermediate operation** (thao tác trung gian), trả về một `Stream` mới trong pipeline.
- Đây là thao tác **stateful** vì kết quả phụ thuộc vào việc xác định ranh giới giữa tiền tố cần bỏ và phần còn lại.
- Phương thức không thực thi toàn bộ pipeline ngay tại lời gọi. Stream chỉ xử lý khi có terminal operation như `collect`, `forEach`, `count` hoặc `findFirst`.
- Predicate phải không can thiệp làm thay đổi nguồn stream và nên không có trạng thái thay đổi trong lúc chạy (non-interfering, stateless).
- Truyền predicate `null` sẽ gây `NullPointerException`.

`dropWhile` không sửa collection nguồn. Nó tạo một bước xử lý trong pipeline; stream nguồn vẫn tuân theo quy tắc dùng một lần của Stream API.

## 2. Quy tắc với stream có thứ tự

Với một stream có encounter order, `dropWhile(predicate)` bỏ **tiền tố dài nhất** mà mọi phần tử trong tiền tố đều thỏa mãn predicate. Phần tử đầu tiên không thỏa mãn được giữ lại, cùng với tất cả phần tử theo sau nó, kể cả khi những phần tử sau lại thỏa mãn predicate.

Ví dụ, xét dãy:

```text
[1, 2, 3, 4, 1, 2]
```

Với điều kiện `n -> n < 3`, hai phần tử `1` và `2` ở đầu dãy bị bỏ. Phần tử `3` là phần tử đầu tiên không thỏa mãn điều kiện, nên nó và toàn bộ phần còn lại được giữ:

```text
Đầu vào:  [1, 2, 3, 4, 1, 2]
Điều kiện: n < 3
Đầu ra:   [3, 4, 1, 2]
```

Điểm cần chú ý: hai phần tử `1` và `2` ở cuối dãy vẫn xuất hiện trong kết quả. Khi đã gặp phần tử đầu tiên không thỏa mãn predicate, `dropWhile` không tiếp tục loại bỏ các phần tử khớp điều kiện ở phía sau.

Ba trường hợp biên:

| Trường hợp | Kết quả |
| --- | --- |
| Stream rỗng | Stream kết quả rỗng |
| Phần tử đầu tiên không khớp predicate | Không bỏ phần tử nào; giữ toàn bộ stream |
| Mọi phần tử đều khớp predicate | Bỏ toàn bộ; kết quả rỗng |

## 3. Khác biệt giữa `dropWhile` và `filter`

Hai thao tác có thể nhận cùng một predicate nhưng ý nghĩa khác nhau.

```java
List<Integer> values = Arrays.asList(1, 2, 3, 4, 1, 2);

List<Integer> suffix = values.stream()
    .dropWhile(n -> n < 3)
    .collect(Collectors.toList());

List<Integer> matching = values.stream()
    .filter(n -> n >= 3)
    .collect(Collectors.toList());
```

Kết quả:

```text
dropWhile: [3, 4, 1, 2]
filter:    [3, 4]
```

`dropWhile` giữ toàn bộ hậu tố từ vị trí đầu tiên không thỏa mãn điều kiện. `filter` giữ mọi phần tử thỏa mãn điều kiện ở bất kỳ vị trí nào và loại bỏ các phần tử không thỏa mãn ở toàn bộ stream.

Chọn `dropWhile` khi yêu cầu là bỏ một đoạn đầu liên tiếp. Chọn `filter` khi yêu cầu là lọc tất cả phần tử theo điều kiện.

## 4. Stream không có encounter order

Với stream có encounter order, Java có thể xác định chính xác tiền tố dài nhất cần bỏ. Với stream không có encounter order (unordered stream), không tồn tại một vị trí đầu/cuối có ý nghĩa để xác định tiền tố.

Trong trường hợp unordered, hợp đồng API cho phép `dropWhile` bỏ **một tập con bất kỳ** trong các phần tử thỏa mãn predicate. Kết quả có thể khác nhau giữa các lần chạy hoặc cách thực thi; không được giả định rằng mọi phần tử khớp điều kiện đều bị bỏ hoặc một phần tử cụ thể chắc chắn được giữ.

Ví dụ, `HashSet` không bảo đảm thứ tự duyệt. Nếu tạo stream từ một `HashSet` rồi gọi `dropWhile`, không nên suy luận kết quả dựa trên thứ tự phần tử được viết trong mã nguồn.

Nếu logic cần một tiền tố xác định, hãy dùng nguồn có encounter order và giữ nguyên ràng buộc thứ tự. Không gọi `unordered()` trước `dropWhile` trừ khi chương trình chấp nhận ngữ nghĩa bỏ một tập con không xác định.

## 5. Hành vi trong pipeline song song

`dropWhile` vẫn có thể dùng với `parallelStream()` hoặc stream đã chuyển sang parallel. Với nguồn có thứ tự, kết quả vẫn phải tuân thủ quy tắc bỏ tiền tố dài nhất theo encounter order.

Để bảo đảm quy tắc này, một pipeline song song có thể phải phối hợp các phần xử lý để xác định ranh giới tiền tố. Vì vậy, `dropWhile` trên ordered parallel stream có thể tốn chi phí đáng kể, đặc biệt khi nguồn lớn hoặc predicate khó xác định ranh giới.

Nếu thứ tự không quan trọng đối với nghiệp vụ, gọi `unordered()` có thể nới lỏng ràng buộc encounter order và giúp pipeline song song hoạt động hiệu quả hơn:

```java
List<Integer> result = values.parallelStream()
    .unordered()
    .dropWhile(n -> n < 3)
    .collect(Collectors.toList());
```

Không dùng kết quả ví dụ unordered để kiểm tra một danh sách đầu ra cố định: tập phần tử bị bỏ được phép thay đổi. Nếu yêu cầu là giữ đúng hậu tố sau tiền tố đầu tiên, không bỏ thứ tự.

`sequential()` chỉ yêu cầu pipeline xử lý tuần tự; nó không tự tạo encounter order cho một nguồn vốn unordered. Muốn dựa vào vị trí đầu/cuối, cần một nguồn có thứ tự hoặc chủ động tạo thứ tự bằng thao tác thích hợp trước đó.

## 6. Tính lazy, stateful và predicate

Vì là intermediate operation, `dropWhile` không tiêu thụ stream ngay khi được gọi:

```java
Stream<Integer> suffix = values.stream().dropWhile(n -> n < 3);
// Chưa có terminal operation nên pipeline chưa được thực thi hoàn chỉnh.

List<Integer> result = suffix.collect(Collectors.toList());
```

Đối với ordered stream, thao tác phải tìm được phần tử đầu tiên không thỏa mãn predicate để biết điểm bắt đầu của hậu tố. Khi đã qua ranh giới đó, các phần tử còn lại được chuyển tiếp mà không bị loại chỉ vì chúng lại khớp predicate.

Predicate nên thuần về mặt tác động lên pipeline: không sửa collection nguồn, không thay đổi biến trạng thái dùng chung và không phụ thuộc vào số lần được gọi. Không nên dựa vào thứ tự hoặc số lần gọi predicate để tạo side effect; việc thực thi song song và tối ưu pipeline có thể ảnh hưởng cách các phần tử được xử lý.

Với stream vô hạn có thứ tự mà predicate đúng mãi mãi, sẽ không có phần tử đầu tiên sai điều kiện để xác định điểm kết thúc của tiền tố. Một terminal operation cần phần tử ở phía sau tiền tố đó có thể không bao giờ hoàn tất. Ví dụ, `Stream.iterate(0, n -> n + 1).dropWhile(n -> true).findFirst()` không thể tìm thấy phần tử đầu tiên của hậu tố vì predicate luôn đúng và luồng có vô hạn phần tử.

Ngược lại, nếu phần tử đầu tiên không khớp predicate, phần tử đó thuộc kết quả và pipeline có thể chuyển tiếp từ đầu stream.

## 7. Ví dụ hoàn chỉnh chạy với Java 9 trở lên

Chương trình sau minh họa tiền tố bị bỏ, trường hợp không bỏ phần tử nào, trường hợp bỏ toàn bộ và sự khác nhau với `filter`.

```java
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;

public class Main {
    public static void main(String[] args) {
        List<Integer> values = Arrays.asList(1, 2, 3, 4, 1, 2);

        List<Integer> afterPrefix = values.stream()
            .dropWhile(n -> n < 3)
            .collect(Collectors.toList());

        List<Integer> unchanged = values.stream()
            .dropWhile(n -> n < 1)
            .collect(Collectors.toList());

        List<Integer> empty = values.stream()
            .dropWhile(n -> n < 10)
            .collect(Collectors.toList());

        List<Integer> filtered = values.stream()
            .filter(n -> n >= 3)
            .collect(Collectors.toList());

        System.out.println(afterPrefix);
        System.out.println(unchanged);
        System.out.println(empty);
        System.out.println(filtered);
    }
}
```

Lưu mã vào tệp `Main.java`, sau đó biên dịch và chạy với JDK 9 trở lên:

```bash
javac --release 9 Main.java
java Main
```

Stdout chính xác:

```text
[3, 4, 1, 2]
[1, 2, 3, 4, 1, 2]
[]
[3, 4]
```

Giải thích:

1. `afterPrefix`: bỏ `1`, `2` ở đầu vì chúng nhỏ hơn `3`; giữ phần còn lại bắt đầu từ `3`.
2. `unchanged`: phần tử đầu tiên là `1`, không nhỏ hơn `1`; không có tiền tố nào cần bỏ.
3. `empty`: tất cả phần tử đều nhỏ hơn `10`; toàn bộ stream bị bỏ.
4. `filtered`: chỉ giữ các giá trị từ `3` trở lên ở mọi vị trí, nên hai phần tử `1`, `2` cuối dãy không còn.

## 8. Các kiểu Stream nguyên thủy

Java 9 cũng bổ sung `dropWhile` cho `IntStream`, `LongStream` và `DoubleStream`. Cách sử dụng và quy tắc tiền tố tương tự `Stream<T>`, nhưng predicate tương ứng là `IntPredicate`, `LongPredicate` và `DoublePredicate`.

Ví dụ với `IntStream`:

```java
int[] result = IntStream.of(1, 2, 3, 4, 1, 2)
    .dropWhile(n -> n < 3)
    .toArray();
```

Kết quả mảng là `[3, 4, 1, 2]`. Khi dùng ví dụ này, cần import `java.util.stream.IntStream`.

## 9. Lỗi thường gặp và cách chọn thao tác

- Dùng `dropWhile` với mong muốn lọc toàn bộ stream: các phần tử khớp predicate ở sau ranh giới đầu tiên vẫn được giữ. Dùng `filter` nếu cần lọc mọi vị trí.
- Nghĩ rằng `dropWhile` bỏ tất cả phần tử khớp predicate: nó chỉ bỏ tiền tố liên tiếp trên ordered stream.
- Cho rằng phần tử đầu tiên khớp điều kiện sẽ luôn bị bỏ trong unordered stream: API không bảo đảm một tiền tố xác định khi không có encounter order.
- Dùng `unordered()` nhưng vẫn kỳ vọng một kết quả theo đúng vị trí: thao tác này nới lỏng ngữ nghĩa thứ tự, vì vậy không phù hợp nếu nghiệp vụ cần hậu tố xác định.
- Dùng predicate có side effect hoặc sửa nguồn: predicate cần non-interfering và stateless để pipeline cho kết quả đáng tin cậy.
- Mong terminal operation trên stream vô hạn luôn kết thúc: nếu predicate đúng vô hạn và không có ranh giới tiền tố, phần hậu tố không thể bắt đầu.
- Tạo một terminal operation rồi tiếp tục dùng lại cùng stream: stream đã được tiêu thụ không thể dùng lại; tạo pipeline mới từ nguồn nếu cần xử lý lần nữa.

## 10. Ghi nhớ

1. `dropWhile` có từ Java 9 và là intermediate operation có trạng thái.
2. Trên ordered stream, nó bỏ tiền tố dài nhất thỏa mãn predicate và giữ toàn bộ phần còn lại.
3. Các phần tử khớp predicate ở phía sau phần tử đầu tiên không khớp vẫn được giữ.
4. `filter` kiểm tra toàn bộ stream; `dropWhile` chỉ bỏ phần đầu liên tiếp.
5. Trên unordered stream, tập phần tử khớp predicate bị bỏ không được xác định thành một tiền tố cụ thể.
6. Ordered parallel `dropWhile` có thể tốn kém; chỉ dùng `unordered()` khi thứ tự không còn là yêu cầu.
7. Predicate cần non-interfering và stateless; stream chỉ thực thi khi có terminal operation.