# stream, parallelStream và giới hạn không can thiệp nguồn

## 1. Stream là một phép xử lý trên nguồn dữ liệu

Giả sử một danh sách chứa các số từ 1 đến 10. Ta muốn lấy số chẵn, bình phương từng số rồi tạo danh sách kết quả. Có thể mô tả công việc bằng một chuỗi thao tác: nguồn → lọc → biến đổi → thu thập.

`Stream` là mô hình biểu diễn chuỗi xử lý đó. Nó không phải một danh sách chứa sẵn bản sao của dữ liệu, cũng không phải một luồng thực thi riêng theo nghĩa `Thread`. Trong tiếng Việt, cần phân biệt:

- **Luồng phần tử (stream):** dòng dữ liệu đi qua các bước xử lý.
- **Luồng thực thi (thread):** một đơn vị thực thi mã trong chương trình.

Một stream có thể được xử lý tuần tự hoặc song song. Khi xử lý song song, thư viện có thể phân chia công việc cho các luồng thực thi, nhưng điều đó không thay đổi trách nhiệm của người viết mã: nguồn dữ liệu và các hàm xử lý phải đáp ứng hợp đồng của stream.

Một pipeline, tức chuỗi xử lý stream, có ba thành phần:

| Thành phần | Vai trò | Ví dụ |
| --- | --- | --- |
| Nguồn dữ liệu | Cung cấp các phần tử | Một `List<Integer>` |
| Thao tác trung gian | Mô tả lọc, biến đổi hoặc tổ chức các phần tử | `filter`, `map`, `sorted` |
| Thao tác kết thúc | Yêu cầu tạo kết quả hoặc thực hiện hành động cuối | `toList`, `sum`, `count`, `forEach` |

Ví dụ minh họa, đặt trong một phương thức đã có biến `numbers` và các `import` cần thiết:

```java
List<Integer> squares = numbers.stream()
        .filter(n -> n % 2 == 0)
        .map(n -> n * n)
        .toList();
```

`filter` không xóa số lẻ khỏi `numbers`. Nó chọn những phần tử được đi tiếp trong pipeline. `map` không thay từng ô của danh sách nguồn bằng bình phương; nó tạo giá trị đầu ra cho bước tiếp theo.

Đó là lý do stream phù hợp với việc mô tả **kết quả cần tạo**. Nếu muốn trực tiếp xóa phần tử khỏi một collection, cần chọn thao tác sửa collection phù hợp thay vì sửa nguồn từ bên trong pipeline đang duyệt nó.

Bài này tập trung vào ba câu hỏi: khi nào nguồn được đọc, chế độ tuần tự hoặc song song ảnh hưởng điều gì, và giới hạn nào phải giữ để quá trình đọc không bị can thiệp.

## 2. Tạo pipeline chưa có nghĩa là đã duyệt xong nguồn

Các thao tác trung gian được đánh giá trì hoãn: gọi `filter` hoặc `map` thường mới xây dựng mô tả xử lý. Việc tính kết quả được yêu cầu khi gọi thao tác kết thúc.

Vì vậy, không nên hình dung `source.stream()` là “chụp toàn bộ source ngay lập tức”. Thời điểm nguồn được ràng buộc với quá trình duyệt còn phụ thuộc loại nguồn và `Spliterator` của nó.

Với `ArrayList` trong chương trình dưới đây, thêm phần tử sau khi tạo stream nhưng trước khi bắt đầu thao tác kết thúc sẽ được phản ánh trong kết quả. Đây không phải việc sửa nguồn trong lúc pipeline đang chạy.

Lưu vào `StreamLifecycleDemo.java`.

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.stream.Stream;

public class StreamLifecycleDemo {
    public static void main(String[] args) {
        List<String> source = new ArrayList<>(List.of("a", "bb", "ccc"));
        Stream<String> pipeline = source.stream()
                .filter(value -> value.length() >= 2)
                .map(value -> value.toUpperCase(Locale.ROOT));

        System.out.println("sizeWhenPipelineCreated=" + source.size());
        source.add("dddd");
        System.out.println("sizeBeforeTerminal=" + source.size());

        List<String> result = pipeline.toList();
        System.out.println("result=" + result);
        System.out.println("sourceAfterTerminal=" + source);

        try {
            pipeline.count();
        } catch (IllegalStateException e) {
            System.out.println("reuse=IllegalStateException");
        }

        source.add("eeeee");
        System.out.println("resultAfterLaterAdd=" + result);
        System.out.println("newStreamCount=" + source.stream().count());
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 StreamLifecycleDemo.java
java StreamLifecycleDemo
```

Stdout:

```text
sizeWhenPipelineCreated=3
sizeBeforeTerminal=4
result=[BB, CCC, DDDD]
sourceAfterTerminal=[a, bb, ccc, dddd]
reuse=IllegalStateException
resultAfterLaterAdd=[BB, CCC, DDDD]
newStreamCount=5
```

Chương trình có ba mốc thời gian cần tách biệt:

```text
Tạo ArrayList
    ↓
Tạo stream và khai báo filter/map
    ↓
Thêm dddd vào nguồn trước thao tác kết thúc
    ↓
Gọi toList: thực hiện pipeline và nhận kết quả
    ↓
Thêm eeeee vào nguồn sau khi pipeline đã xong
```

Khi tạo pipeline, nguồn có ba phần tử. Trước `toList`, nguồn có thêm `dddd`, nên kết quả chứa `DDDD`. Hai bước lọc và chuyển chữ hoa chỉ ảnh hưởng kết quả: danh sách nguồn vẫn là `[a, bb, ccc, dddd]`.

Sau đó, thêm `eeeee` không tự cập nhật danh sách kết quả đã tạo. Muốn xử lý trạng thái mới của nguồn, chương trình gọi `source.stream()` lần nữa.

### Một stream chỉ dùng cho một lần xử lý

Sau thao tác kết thúc, pipeline đã được tiêu thụ. Không dùng lại nó để thực hiện phép tổng hợp thứ hai, cũng không tách một đối tượng stream thành hai nhánh sử dụng độc lập.

Trong ví dụ, gọi `pipeline.count()` sau `pipeline.toList()` ném `IllegalStateException`. Quy tắc là không tái sử dụng stream; không xây chương trình dựa trên giả định rằng mọi cách tái sử dụng sai đều chắc chắn được phát hiện. [Javadoc Stream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html)

Giữ nguồn và tạo stream mới khi cần duyệt lại là hai việc khác với giữ một stream đã chạy. Stream từ collection thông thường cũng không đại diện cho một tiến trình luôn theo dõi mọi lần cập nhật tiếp theo của collection.

### Kết quả trong ví dụ có yêu cầu phiên bản nào?

`Stream.toList()` có từ Java 16, nên dùng được với Java 17 trong bài. Nó trả về danh sách không cho sửa cấu trúc. Không mặc định rằng có thể gọi `result.add(...)` trên kết quả đó.

Nếu cần một danh sách cho phép thêm hoặc xóa, có thể yêu cầu rõ một collection kết quả thích hợp; phần thu thập kết quả ở dưới dùng `Collectors.toCollection(ArrayList::new)`.

## 3. stream và parallelStream khác nhau ở chế độ thực thi

`Collection.stream()` tạo stream tuần tự. `parallelStream()` cho phép yêu cầu xử lý song song; cách triển khai mặc định tạo stream ở chế độ song song, dù hợp đồng giao diện `Collection` cho phép một cách triển khai trả về stream tuần tự. Có thể kiểm tra chế độ thực tế bằng `isParallel()`. [Javadoc Collection.stream và parallelStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collection.html)

Với các collection JDK được dùng trong bài:

| Cách gọi | Ý nghĩa |
| --- | --- |
| `source.stream()` | Bắt đầu với chế độ tuần tự |
| `source.parallelStream()` | Bắt đầu với chế độ song song |
| `stream.parallel()` | Đặt chế độ xử lý song song cho pipeline |
| `stream.sequential()` | Đặt chế độ xử lý tuần tự cho pipeline |
| `stream.isParallel()` | Hỏi chế độ hiện tại, không phải đếm số luồng thực thi |

Không đọc một chuỗi có `parallel()` ở giữa rồi kết luận “các bước trước chạy tuần tự, các bước sau chạy song song”. Chế độ được đặt gần nhất áp dụng cho việc thực thi toàn pipeline khi thao tác kết thúc yêu cầu xử lý.

### Thí nghiệm về chế độ và thứ tự kết quả

Lưu vào `StreamExecutionModeDemo.java`.

```java
import java.util.List;
import java.util.StringJoiner;
import java.util.stream.IntStream;

public class StreamExecutionModeDemo {
    public static void main(String[] args) {
        List<Integer> source = IntStream.rangeClosed(1, 10).boxed().toList();

        System.out.println("streamParallel=" + source.stream().isParallel());
        System.out.println("parallelStreamParallel="
                + source.parallelStream().isParallel());
        System.out.println("afterSequential="
                + source.parallelStream().sequential().isParallel());
        System.out.println("afterParallel="
                + source.stream().parallel().isParallel());

        List<Integer> sequential = source.stream()
                .filter(n -> n % 2 == 0)
                .map(n -> n * n)
                .toList();
        List<Integer> parallel = source.parallelStream()
                .filter(n -> n % 2 == 0)
                .map(n -> n * n)
                .toList();

        System.out.println("sequential=" + sequential);
        System.out.println("parallel=" + parallel);
        System.out.println("sameResult=" + sequential.equals(parallel));

        StringJoiner ordered = new StringJoiner(",");
        source.parallelStream()
                .filter(n -> n % 2 == 0)
                .forEachOrdered(n -> ordered.add(n.toString()));
        System.out.println("orderedActions=" + ordered);
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 StreamExecutionModeDemo.java
java StreamExecutionModeDemo
```

Stdout:

```text
streamParallel=false
parallelStreamParallel=true
afterSequential=false
afterParallel=true
sequential=[4, 16, 36, 64, 100]
parallel=[4, 16, 36, 64, 100]
sameResult=true
orderedActions=2,4,6,8,10
```

Hai danh sách `sequential` và `parallel` bằng nhau vì cùng thực hiện phép lọc, biến đổi độc lập trên nguồn có thứ tự. Trong pipeline này, `toList()` giữ thứ tự gặp phần tử của stream, nên kết quả vẫn là `[4, 16, 36, 64, 100]`.

Không thể từ kết quả có thứ tự suy ra rằng các phép bình phương đã chạy lần lượt trên cùng một luồng thực thi. **Thứ tự của kết quả** và **thời điểm thực hiện mỗi phép tính** là hai vấn đề khác nhau.

Dòng `orderedActions` dùng `forEachOrdered`. Khi stream có thứ tự gặp, thao tác này thực hiện hành động theo thứ tự đó. Các hành động được thực hiện lần lượt và có quan hệ hoàn tất trước giữa hành động trước với hành động sau; vì vậy `StringJoiner` trong ví dụ không bị nhiều hành động sửa đồng thời. Điều này không cam kết tất cả hành động chạy trên cùng một luồng thực thi. [Javadoc forEachOrdered](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html#forEachOrdered(java.util.function.Consumer))

Nếu đổi thành `forEach` trên parallel stream, không còn bảo đảm thứ tự gặp cho các hành động, cũng không thể dùng chung `StringJoiner` như thể chỉ có một bên sửa. Muốn thu thập dữ liệu, nên dùng thao tác thu thập thay vì tự sửa một đối tượng kết quả bên ngoài.

### Spliterator giúp phân chia nguồn, không làm nguồn tự an toàn

`Spliterator` có nhiệm vụ hỗ trợ duyệt và phân chia phần tử. Khi xử lý song song, thư viện có thể chia nguồn thành các phần, xử lý rồi kết hợp kết quả. Khả năng chia cân bằng và chi phí chia ảnh hưởng lợi ích của cách thực thi này.

Các đặc tính như `ORDERED`, `SIZED`, `IMMUTABLE` hoặc `CONCURRENT` mô tả những bảo đảm của quá trình duyệt. Chúng không phải bằng chứng rằng mọi đối tượng phần tử hoặc mọi hàm do người dùng truyền vào đều an toàn khi chạy đồng thời. [Javadoc Spliterator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Spliterator.html)

Do đó, `parallelStream()` không biến `ArrayList` thành collection cho phép nhiều bên tùy ý thêm hoặc xóa trong lúc duyệt. Nó cũng không cấp một luồng thực thi riêng cho mỗi phần tử, không cam kết một số luồng cố định và không tự bảo vệ trạng thái dùng chung của các hàm xử lý.

## 4. Không can thiệp nguồn là điều kiện của cả hai chế độ

Với nguồn thông thường không hỗ trợ cập nhật đồng thời, các hàm được truyền vào pipeline phải không sửa nguồn đang được xử lý. Điều này áp dụng cả khi dùng `stream()`, không chỉ `parallelStream()`.

Trong các thao tác kết thúc thông thường của bài, khoảng thời gian cần bảo vệ bắt đầu khi gọi thao tác kết thúc và kết thúc khi thao tác đó hoàn tất. Các cách lấy `iterator()` hoặc `spliterator()` để tự điều khiển việc duyệt là trường hợp riêng: trách nhiệm bảo vệ phải kéo dài theo việc duyệt thực tế. [Quy tắc non-interference của Stream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/package-summary.html#NonInterference)

### “Nguồn” là đối tượng thực, không chỉ là tên biến

Xét đoạn mã sai sau. Đây là đoạn minh họa lỗi trong một phương thức, không phải chương trình độc lập và không có stdout được bảo đảm:

```java
List<Integer> source = new ArrayList<>(List.of(1, 2, 3, 4));

source.stream().forEach(n -> {
    if (n == 2) {
        source.add(99);
    }
});
```

Khi `forEach` đang duyệt `source`, hành động lại thêm phần tử vào chính `source`. Dùng `stream()` tuần tự không làm việc đó hợp lệ. Việc đọc và sửa có thể xung đột về quy tắc duyệt ngay trên một luồng thực thi.

Cũng không tránh được vấn đề bằng cách sửa qua một tên khác:

```java
// Đoạn minh họa sai; source là ArrayList đang được stream duyệt.
List<Integer> alias = source;
source.stream().forEach(n -> alias.remove(n));
```

`alias` vẫn trỏ đến cùng đối tượng. Tương tự, một phương thức được gọi trong `map` hoặc `filter` có thể sửa nguồn một cách gián tiếp; không phải chỉ những lời gọi `source.add` nhìn thấy ngay trong lambda mới đáng kiểm tra.

### Không chỉ add và remove mới cần xem xét

Thêm, xóa hoặc xóa toàn bộ nguồn là những trường hợp rõ nhất. Thay phần tử bằng `set`, sắp xếp lại collection hoặc sửa một khung nhìn dùng chung cấu trúc cũng có thể làm dữ liệu được đọc thay đổi trong khi pipeline đang thực hiện.

Riêng với `ArrayList`, `set` không được phân loại là thay đổi cấu trúc theo cách theo dõi của lớp. Điều đó không biến việc thay phần tử trong lúc stream đang đọc thành một hợp đồng xử lý đáng tin. **Không làm bộ đếm thay đổi cấu trúc tăng** và **không can thiệp nguồn** không phải cùng một điều kiện.

Nguồn cũng có thể bị sửa bởi một luồng thực thi khác mà không có bất kỳ câu lệnh sửa nào trong lambda. Để chạy pipeline đúng, cần kiểm soát mọi đường sửa nguồn trong khoảng thời gian xử lý.

### ConcurrentModificationException không phải cơ chế đồng bộ

Một nguồn có cơ chế phát hiện thay đổi có thể ném `ConcurrentModificationException`. Tuy nhiên, cơ chế fail-fast chỉ hỗ trợ phát hiện lỗi trên cơ sở cố gắng phát hiện, không bảo đảm bắt được mọi can thiệp. Không có ngoại lệ cũng chưa chứng minh rằng phép tính đúng. [Javadoc ArrayList về fail-fast](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html)

Với đoạn mã vi phạm hợp đồng, có thể gặp ngoại lệ, kết quả không đúng hoặc hành vi không còn theo giả định của chương trình. Không viết kiểm thử bắt buộc mọi cách sửa nguồn sai đều phải ném đúng một ngoại lệ tại đúng một phần tử.

Ngoại lệ cũng không hoàn tác những thay đổi đã xảy ra trước đó. Thử sửa nguồn rồi bắt `ConcurrentModificationException` để chạy lại không phải cách an toàn để triển khai một phép xử lý dữ liệu.

### forEachOrdered không cấp quyền sửa nguồn

`forEachOrdered` điều phối thứ tự hành động cuối. Nó không thay đổi hợp đồng của nguồn. Nếu hành động thêm hoặc xóa chính danh sách đang được duyệt, vấn đề can thiệp nguồn vẫn tồn tại.

Cần tách rõ hai yêu cầu: thứ tự hành động và tính hợp lệ của việc đọc nguồn. Giải quyết yêu cầu thứ nhất không tự giải quyết yêu cầu thứ hai.

## 5. Tạo kết quả mới hoặc tách giai đoạn sửa nguồn

Có ba cách diễn đạt thường phù hợp hơn việc vừa stream vừa sửa nguồn:

1. Dùng `filter` và `map` để tạo kết quả mới.
2. Nếu muốn sửa trực tiếp collection, dùng thao tác được thiết kế cho mục đích đó, chẳng hạn `removeIf`, ngoài pipeline đang duyệt.
3. Nếu cần xử lý một trạng thái đã chọn của dữ liệu, tạo bản sao nguồn tại thời điểm được bảo vệ rồi xử lý bản sao.

Lưu vào `NonInterferingTransformDemo.java`.

```java
import java.util.ArrayList;
import java.util.List;

public class NonInterferingTransformDemo {
    public static void main(String[] args) {
        List<Integer> source = new ArrayList<>(List.of(1, 2, 3, 4, 5, 6));

        List<Integer> transformed = source.parallelStream()
                .filter(n -> n % 2 == 0)
                .map(n -> n * 10)
                .toList();
        System.out.println("transformed=" + transformed);
        System.out.println("sourceUnchanged=" + source);

        List<Integer> snapshot = new ArrayList<>(source);
        source.removeIf(n -> n % 2 == 0);

        List<Integer> fromSnapshot = snapshot.parallelStream()
                .filter(n -> n % 2 == 0)
                .map(n -> n * 10)
                .toList();
        System.out.println("sourceAfterRemoveIf=" + source);
        System.out.println("snapshot=" + snapshot);
        System.out.println("fromSnapshot=" + fromSnapshot);
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 NonInterferingTransformDemo.java
java NonInterferingTransformDemo
```

Stdout:

```text
transformed=[20, 40, 60]
sourceUnchanged=[1, 2, 3, 4, 5, 6]
sourceAfterRemoveIf=[1, 3, 5]
snapshot=[1, 2, 3, 4, 5, 6]
fromSnapshot=[20, 40, 60]
```

Lần xử lý đầu lấy số chẵn rồi nhân 10. Nguồn vẫn có đủ sáu số vì pipeline chỉ tạo `transformed`.

Sau khi lần xử lý đó kết thúc, chương trình sao chép cấu trúc nguồn sang `snapshot`, rồi gọi `removeIf` trên nguồn. Khi stream của `snapshot` chạy, nó đọc danh sách riêng, nên vẫn tính từ sáu số ban đầu dù nguồn hiện tại chỉ còn `[1, 3, 5]`.

`removeIf` trong ví dụ là một thao tác riêng. Không đặt nó vào hàm xử lý của chính stream đang đọc collection đó. Biểu thức kiểm tra điều kiện cũng chỉ đọc giá trị, không tiếp tục sửa collection bằng một đường khác.

### Bản sao phải được tạo khi việc đọc nguồn hợp lệ

`new ArrayList<>(source)` không phải nút “làm an toàn đồng thời” cho mọi nguồn. Để sao chép đúng, bản thân quá trình đọc `source` lúc sao chép cũng phải được bảo vệ khỏi những cập nhật không hợp lệ.

Trong chương trình trên, chỉ có một luồng thực thi sở hữu và sửa danh sách, nên việc sao chép được thực hiện ở thời điểm ổn định. Trong ứng dụng có nhiều bên ghi, cần một cơ chế phối hợp thích hợp cho giai đoạn lấy dữ liệu; sau đó có thể xử lý bản sao độc lập về cấu trúc.

Một lớp bao không cho sửa như `Collections.unmodifiableList(source)` cũng chưa phải bản sao. Nếu bên khác vẫn giữ `source` và sửa nó, lớp bao vẫn dùng dữ liệu nền đó.

### Bản sao cấu trúc không sao chép sâu phần tử

Danh sách chứa các `Integer` trong ví dụ dùng phần tử bất biến. Với đối tượng có trạng thái thay đổi được, `new ArrayList<>(source)` vẫn giữ cùng các tham chiếu phần tử.

Ví dụ, sao chép một `List<Order>` không tự tạo các đối tượng `Order` mới. Nếu bên khác đổi trường giá trị trong những `Order` đó, pipeline trên bản sao vẫn cần được đánh giá về tính nhất quán dữ liệu.

Sửa trạng thái phần tử khác với thêm hoặc xóa khỏi collection. Không thể chỉ nhìn thấy một lời gọi setter rồi kết luận mọi trường hợp đều sai; cần xem đối tượng có được dùng chung, có xuất hiện nhiều lần, có bị đọc hoặc ghi đồng thời và có làm kết quả phụ thuộc thời điểm thực thi hay không. Khi mục tiêu là biến đổi dữ liệu, tạo đối tượng đầu ra mới thường làm trách nhiệm rõ hơn việc sửa đối tượng đang dùng chung.

## 6. Không sửa nguồn vẫn chưa đủ nếu có trạng thái dùng chung

Một pipeline có thể không động vào collection nguồn nhưng vẫn sai khi các hàm của nó cùng sửa một đối tượng bên ngoài.

Đoạn dưới minh họa lỗi, không phải chương trình mẫu để chạy và không có kết quả đầu ra đáng tin:

```java
List<Integer> output = new ArrayList<>();

numbers.parallelStream()
        .map(n -> n * 2)
        .forEach(output::add);
```

`output` không phải nguồn `numbers`, nên lỗi ở đây không phải thêm vào chính nguồn. Lỗi là nhiều hành động có thể gọi `ArrayList.add` đồng thời trên cùng một danh sách không được bảo vệ. Có thể mất phần tử, sai trạng thái hoặc gặp ngoại lệ.

Dùng danh sách có đồng bộ có thể bảo vệ từng thao tác thêm, nhưng không tự diễn đạt đúng thứ tự kết quả cần có và tạo ra điểm tranh chấp chung. Với mục tiêu thu thập kết quả, nên để thao tác thu thập của stream quản lý các vùng tích lũy.

### Thí nghiệm dùng collect và phép tổng hợp

Lưu vào `ParallelReductionDemo.java`.

```java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.IntStream;

public class ParallelReductionDemo {
    public static void main(String[] args) {
        List<Integer> source = IntStream.rangeClosed(1, 12).boxed().toList();

        List<Integer> doubled = source.parallelStream()
                .map(n -> n * 2)
                .collect(Collectors.toCollection(ArrayList::new));
        int sequentialSum = source.stream().mapToInt(Integer::intValue).sum();
        int parallelSum = source.parallelStream().mapToInt(Integer::intValue).sum();
        long evenCount = source.parallelStream().filter(n -> n % 2 == 0).count();

        System.out.println("doubled=" + doubled);
        System.out.println("sequentialSum=" + sequentialSum);
        System.out.println("parallelSum=" + parallelSum);
        System.out.println("evenCount=" + evenCount);
        System.out.println("source=" + source);
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 ParallelReductionDemo.java
java ParallelReductionDemo
```

Stdout:

```text
doubled=[2, 4, 6, 8, 10, 12, 14, 16, 18, 20, 22, 24]
sequentialSum=78
parallelSum=78
evenCount=6
source=[1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]
```

`Collectors.toCollection(ArrayList::new)` cung cấp cách tạo các collection tích lũy do thư viện quản lý. Với cơ chế thu thập này, các phần kết quả được tích lũy riêng rồi kết hợp phù hợp; không phải mọi luồng thực thi cùng gọi `add` vào một `ArrayList` bên ngoài.

Vì thế có thể dùng `ArrayList` làm vùng tích lũy trong cách thu thập này dù `ArrayList` không tự an toàn cho mọi lời gọi đồng thời. Đây là bảo đảm từ giao thức thu thập, không phải một thay đổi về tính chất của lớp `ArrayList`. [Javadoc Collectors](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Collectors.html)

`sum` và `count` cũng cho phép thư viện tổ chức việc tích lũy kết quả thay vì người dùng tự tăng biến chung. Trong ví dụ, tổng từ 1 đến 12 bằng 78, có sáu số chẵn và nguồn không bị sửa.

### Kết hợp kết quả phải đúng về mặt toán học

Nếu dùng `reduce` hoặc tự xây cách thu thập, cần tuân thủ hợp đồng kết hợp. Khi chia dữ liệu thành các nhóm, kết quả không được thay đổi chỉ vì thư viện chọn cách nhóm khác.

Ví dụ với phép trừ:

```text
(10 - 3) - 2 = 5
10 - (3 - 2) = 9
```

Phép trừ không có tính kết hợp. Đổi một phép giảm dùng phép trừ sang song song rồi mong nó luôn giống cách trừ từ trái sang phải là đặt sai yêu cầu lên thư viện.

Trong ví dụ dùng số nguyên nhỏ của bài, tổng không bị tràn và không gặp vấn đề làm tròn. Với phép cộng số thực, đổi cách nhóm có thể tạo khác biệt làm tròn; không áp dụng máy móc kỳ vọng “kết quả giống từng bit” cho mọi phép tổng hợp.

### Trạng thái an toàn khi cập nhật vẫn có thể sai ý nghĩa

Giả sử dùng một bộ đếm nguyên tử trong `filter` và giữ ba phần tử có ba lần tăng đầu tiên. Bộ đếm có thể không mất cập nhật, nhưng ở chế độ song song, ba phần tử được xử lý trước không nhất thiết là ba phần tử đầu trong thứ tự nguồn.

Nếu yêu cầu là “ba phần tử đầu”, hãy diễn đạt bằng `limit(3)` trên stream có thứ tự phù hợp. Một cấu trúc an toàn đồng thời chỉ giải quyết cách truy cập trạng thái, không tự biến một quy tắc phụ thuộc lịch chạy thành đúng yêu cầu.

### Không dùng peek làm bước bắt buộc cho nghiệp vụ

Đoạn sau chỉ minh họa việc quan sát, không hứa chắc có ba dòng được in:

```java
// Đoạn minh họa; numbers là List<Integer> đã có.
long count = numbers.stream()
        .peek(System.out::println)
        .count();
```

Nếu số lượng phần tử đã biết và các bước giữa không làm thay đổi số lượng, thư viện có thể tính `count` mà không duyệt từng phần tử. Khi đó `peek` có thể không được gọi. [Javadoc Stream.count](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html#count())

Ngoài ra, thao tác kết thúc ngắn mạch có thể không cần đọc hết nguồn. Đừng đặt một cập nhật bắt buộc phải xảy ra cho mọi phần tử vào `map`, `filter` hoặc `peek` rồi giả định nó luôn chạy đủ lần. Hãy thể hiện kết quả cần tính bằng giá trị trả về, phép tổng hợp hoặc một giai đoạn hành động rõ ràng.

## 7. Loại nguồn quyết định chính sách khi dữ liệu thay đổi

Không thể chỉ nhìn tên phương thức `stream()` rồi kết luận mọi loại collection đều lấy cùng một trạng thái dữ liệu.

Ba trường hợp cần phân biệt:

| Loại nguồn | Cách nhìn quá trình duyệt | Khi dữ liệu thay đổi |
| --- | --- | --- |
| `ArrayList` thông thường | Có cơ chế ràng buộc muộn và phát hiện can thiệp | Thay trước khi xử lý có thể được phản ánh; không sửa trong lúc xử lý |
| `CopyOnWriteArrayList` | Duyệt ảnh chụp của mảng tại lúc tạo bộ duyệt | Những lần thêm hoặc xóa sau đó không đi vào ảnh chụp đang duyệt |
| Tập khóa của `ConcurrentHashMap` | Bộ duyệt hỗ trợ cập nhật đồng thời, nhất quán yếu | Không hứa cho một ảnh chụp nguyên tử của toàn bộ map |

Lưu vào `SourceTraversalPoliciesDemo.java`.

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Spliterator;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.stream.Stream;

public class SourceTraversalPoliciesDemo {
    public static void main(String[] args) {
        List<String> regular = new ArrayList<>(List.of("A", "B"));
        Stream<String> regularStream = regular.stream();
        regular.add("C");
        System.out.println("regularResult=" + regularStream.toList());
        System.out.println("regularConcurrent=" + regular.spliterator()
                .hasCharacteristics(Spliterator.CONCURRENT));

        CopyOnWriteArrayList<String> copyOnWrite =
                new CopyOnWriteArrayList<>(List.of("A", "B"));
        Stream<String> snapshotStream = copyOnWrite.stream();
        copyOnWrite.add("C");
        System.out.println("copyOnWriteResult=" + snapshotStream.toList());
        System.out.println("copyOnWriteCurrent=" + copyOnWrite);
        System.out.println("copyOnWriteImmutableTraversal="
                + copyOnWrite.spliterator()
                .hasCharacteristics(Spliterator.IMMUTABLE));
        System.out.println("copyOnWriteConcurrentTraversal="
                + copyOnWrite.spliterator()
                .hasCharacteristics(Spliterator.CONCURRENT));

        ConcurrentHashMap<String, Integer> concurrent = new ConcurrentHashMap<>();
        concurrent.put("B", 2);
        concurrent.put("A", 1);
        System.out.println("keySetConcurrentTraversal="
                + concurrent.keySet().spliterator()
                .hasCharacteristics(Spliterator.CONCURRENT));
        System.out.println("stableKeysForDisplay="
                + concurrent.keySet().stream().sorted().toList());
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 SourceTraversalPoliciesDemo.java
java SourceTraversalPoliciesDemo
```

Stdout:

```text
regularResult=[A, B, C]
regularConcurrent=false
copyOnWriteResult=[A, B]
copyOnWriteCurrent=[A, B, C]
copyOnWriteImmutableTraversal=true
copyOnWriteConcurrentTraversal=false
keySetConcurrentTraversal=true
stableKeysForDisplay=[A, B]
```

### Với ArrayList: không chụp ngay tại lời gọi stream

`regularStream` được tạo khi danh sách có `A` và `B`. Thêm `C` trước thao tác kết thúc khiến kết quả gồm cả `C`. Đặc tính `CONCURRENT` là `false`; đây không phải nguồn được thiết kế để nhận các cập nhật đồng thời tùy ý trong lúc stream đang đọc.

Sự ràng buộc muộn thu hẹp khoảng thời gian có thể xảy ra can thiệp. Nó không xóa yêu cầu bảo vệ trong thời gian thực thi pipeline.

### Với CopyOnWriteArrayList: ảnh chụp của quá trình duyệt

`CopyOnWriteArrayList` cho phép sửa chính danh sách, nhưng spliterator của nó duyệt một ảnh chụp mảng đã có khi spliterator được tạo. Trong chương trình, stream cũ cho `[A, B]`, còn trạng thái hiện tại của danh sách đã là `[A, B, C]`.

Đặc tính `IMMUTABLE` ở đây mô tả nguồn phần tử của bộ duyệt đó, không có nghĩa đối tượng `CopyOnWriteArrayList` không thể gọi `add`. Nó cũng không có nghĩa các đối tượng phần tử đã trở thành bất biến. [Javadoc CopyOnWriteArrayList.spliterator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CopyOnWriteArrayList.html#spliterator())

Không chọn lớp này chỉ để che một pipeline đang sửa nguồn sai cách. Mỗi lần ghi có chi phí sao chép; cần dùng khi chính sách ảnh chụp và đặc điểm đọc nhiều hơn ghi phù hợp với yêu cầu.

### Với ConcurrentHashMap: hỗ trợ cập nhật không đồng nghĩa chụp nguyên tử

`keySetConcurrentTraversal=true` cho thấy bộ duyệt tập khóa báo đặc tính `CONCURRENT`. Đây là ví dụ về nguồn được thiết kế để duyệt trong khi có cập nhật theo hợp đồng của nó.

Tuy nhiên, một lần duyệt có thể quan sát trạng thái ở các thời điểm khác nhau. Không xem kết quả tổng hợp trong lúc map đang thay đổi là ảnh chụp nhất quán của toàn bộ map tại một thời điểm duy nhất. [Javadoc ConcurrentHashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html)

Chương trình không tạo cập nhật cạnh tranh thực tế cho map, nên dòng `stableKeysForDisplay` chỉ in hai khóa đã thêm và sắp xếp chúng để kết quả hiển thị ổn định. Dòng đó không phải thí nghiệm chứng minh mọi cập nhật đồng thời đều được quan sát.

Ngoại lệ về nguồn concurrent cũng không làm các hàm xử lý tự hết trạng thái dùng chung. Nếu một lambda sửa một `ArrayList` kết quả bên ngoài hoặc đọc một biến đang thay đổi không có phối hợp, các vấn đề đó vẫn phải được giải quyết riêng.

Nếu nghiệp vụ cần xử lý đúng toàn bộ dữ liệu tại cùng một thời điểm, phải thiết kế cách lấy trạng thái nhất quán. Đổi collection sang concurrent chỉ để không còn `ConcurrentModificationException` chưa đủ để chứng minh yêu cầu đó.

## 8. Chỉ chọn song song sau khi phép xử lý đã đúng

Chế độ song song là lựa chọn thực thi, không phải bước sửa tính đúng đắn. Trước hết cần xác định:

- Hàm lọc và biến đổi có thể tính độc lập cho từng phần tử hay không.
- Có nguồn nào bị sửa trong thời gian pipeline chạy hay không.
- Việc kết hợp kết quả có tuân thủ hợp đồng không.
- Thứ tự nào cần giữ ở đầu ra hoặc ở các hành động.
- Có trạng thái dùng chung bên ngoài pipeline hay không.

Sau đó mới cân nhắc chi phí. Phân chia công việc, lập lịch và kết hợp kết quả đều có chi phí. Nguồn nhỏ hoặc thao tác quá nhẹ có thể không thu được lợi ích; nguồn khó chia cân bằng cũng có thể làm một số phần hoàn thành muộn hơn nhiều phần khác. Không suy ra `parallelStream()` luôn nhanh hơn `stream()`. [Oracle Java Tutorial: Parallelism](https://docs.oracle.com/javase/tutorial/collections/streams/parallelism.html)

Một nguồn `ArrayList` ổn định có thể được đọc bởi parallel stream dù bản thân collection không cung cấp mọi thao tác an toàn đồng thời. Điều kiện ở đây là không có bên sửa nguồn trong thời gian xử lý và các hàm tham gia đáp ứng hợp đồng. Không cần biến mọi nguồn chỉ đọc thành collection concurrent chỉ vì chọn chế độ song song.

Nếu kết quả đúng nhưng cần kết luận về tốc độ, đo với dữ liệu và môi trường thực tế bằng cách đo thích hợp cho JVM. Một lần in tên luồng thực thi hoặc một phép đo thời gian rất ngắn chưa đủ để chứng minh lợi ích.

Các chương trình trong bài dùng đầu vào nhỏ để kiểm chứng hành vi và kết quả. Chúng không phải bài đo hiệu năng.

### Khi nào vòng lặp là cách diễn đạt phù hợp?

Nếu công việc phải sửa nhiều cấu trúc có liên hệ với nhau theo thứ tự rõ ràng, một vòng lặp tuần tự có thể diễn đạt trách nhiệm tốt hơn một pipeline chứa nhiều tác động phụ.

Tuy vậy, đổi stream sang vòng lặp `for-each` cũng không tự cho phép thêm hoặc xóa trực tiếp collection đang được iterator của vòng lặp duyệt. Muốn xóa trong khi duyệt, chọn API và quy tắc duyệt phù hợp, chẳng hạn `removeIf` hoặc thao tác xóa của iterator trong trường hợp được hỗ trợ.

Điều cần giữ là hợp đồng của nguồn và thuật toán, không phải hình thức viết lambda hay vòng lặp.

## 9. Những hiểu nhầm dễ làm phép xử lý sai

| Hiểu nhầm | Điều cần kiểm tra hoặc sửa |
| --- | --- |
| `stream()` là bản sao dữ liệu | Xác định loại nguồn và thời điểm ràng buộc; tạo bản sao riêng nếu cần |
| Chỉ parallel stream mới cấm sửa nguồn | Quy tắc không can thiệp áp dụng cả pipeline tuần tự |
| Không gặp `ConcurrentModificationException` nghĩa là an toàn | Cơ chế phát hiện lỗi không bảo đảm bắt mọi can thiệp |
| Thay bằng `set` thì chắc chắn hợp lệ vì không đổi size | Dữ liệu nguồn vẫn bị thay trong thời gian duyệt |
| Đổi sang tên biến khác thì không còn sửa nguồn | Kiểm tra đối tượng thực và mọi đường tham chiếu dùng chung |
| `forEachOrdered` làm mọi thao tác hợp lệ | Nó xử lý thứ tự hành động, không cấp quyền sửa nguồn |
| Parallel stream làm nguồn tự an toàn đồng thời | Nguồn và các hàm vẫn phải đáp ứng hợp đồng riêng |
| Có danh sách kết quả bên ngoài là có thể gọi `add` từ mọi lambda | Dùng thao tác thu thập; tránh tích lũy không được bảo vệ |
| Bộ đếm nguyên tử làm mọi thuật toán có trạng thái đúng thứ tự | Phân biệt an toàn cập nhật với ý nghĩa lựa chọn phần tử |
| `peek` luôn chạy một lần cho mỗi phần tử | Có thể tối ưu bỏ bước hoặc kết thúc sớm |
| Collection concurrent luôn cho ảnh chụp cố định | Đọc chính sách của bộ duyệt; nhất quán yếu khác ảnh chụp |
| Tạo `new ArrayList<>(source)` bảo vệ cả mọi đối tượng phần tử | Bản sao cấu trúc vẫn dùng chung tham chiếu phần tử |
| Thêm `parallel()` ở giữa chỉ làm đoạn sau song song | Chế độ được đặt gần nhất áp dụng cho toàn pipeline khi chạy |

Một cách tự kiểm tra hữu ích là tách ba câu hỏi:

1. **Nguồn có ổn định hoặc có chính sách cập nhật phù hợp không?**
2. **Hàm xử lý có phụ thuộc trạng thái đang thay đổi hoặc gây tranh chấp không?**
3. **Thao tác kết thúc và cách kết hợp có bảo đảm đúng kết quả cần có không?**

Trả lời “có dùng collection an toàn đồng thời” mới xử lý được một phần của câu hỏi đầu, không thay thế hai câu hỏi còn lại.

## 10. Thực hành dự đoán và sửa cách xử lý

### Bài 1: thay đổi trước và sau thao tác kết thúc

Một `ArrayList` ban đầu chứa `[1, 2]`. Tạo stream có `filter(n -> n > 1)`, thêm `3` vào danh sách rồi gọi `toList()`. Sau khi có kết quả, thêm `4` vào danh sách. Kết quả đã tạo chứa những phần tử nào?

**Đối chiếu:**

Kết quả là `[2, 3]`. Lần thêm `3` xảy ra trước thao tác kết thúc và được stream từ `ArrayList` trong tình huống này quan sát. Lần thêm `4` xảy ra sau đó không tự cập nhật danh sách kết quả. Muốn xử lý cả `4`, tạo stream mới từ nguồn.

### Bài 2: thay đổi trong lúc duyệt tuần tự

Một pipeline dùng `source.stream().forEach(...)`; bên trong hành động, gọi `source.remove(...)`. Có thể kết luận an toàn vì không dùng `parallelStream()` không?

**Đối chiếu:**

Không. Pipeline đang đọc và sửa cùng nguồn thông thường trong một lần duyệt. Vấn đề vẫn có thể xảy ra trên một luồng thực thi. Nếu yêu cầu là loại phần tử theo điều kiện, dùng `removeIf` riêng hoặc tạo danh sách mới bằng `filter`, tùy việc có cần sửa nguồn hay không.

Không đặt một stdout hay một ngoại lệ cố định làm hợp đồng cho đoạn mã vi phạm.

### Bài 3: thu thập từ parallel stream

Đoạn mã có `List<Integer> result = new ArrayList<>();`, sau đó dùng parallel stream với `forEach(result::add)`. Nguồn hoàn toàn không bị sửa. Đoạn mã đã đủ điều kiện đúng chưa?

**Đối chiếu:**

Chưa. Các hành động có thể cập nhật cùng `result` đồng thời. Với mục đích tạo danh sách, dùng `toList()` nếu không cần sửa cấu trúc kết quả, hoặc `collect(Collectors.toCollection(ArrayList::new))` nếu cần một `ArrayList` cho phép sửa.

Sự ổn định của nguồn và cách tích lũy kết quả là hai điều kiện riêng.

### Bài 4: thứ tự kết quả và thứ tự hành động

Một `List` có thứ tự được lọc và biến đổi bằng parallel stream. Khi kết thúc bằng `toList()`, kết quả có thể giữ thứ tự gặp. Điều đó có chứng minh các lời gọi hàm `map` đã xảy ra tuần tự không? Thay thao tác kết thúc bằng `forEach` có bảo đảm thứ tự hành động giống danh sách không?

**Đối chiếu:**

Không cho cả hai câu. Thư viện có thể xử lý các phần độc lập rồi ghép kết quả đúng thứ tự. `forEach` trên parallel stream không cam kết tôn trọng thứ tự gặp. Nếu cần thứ tự hành động trên một stream có thứ tự, xem xét `forEachOrdered`; vẫn phải giữ các giới hạn về nguồn và trạng thái dùng chung.

### Bài 5: collection an toàn đồng thời và ảnh chụp

Tạo stream từ `CopyOnWriteArrayList` có `[A, B]`, sau đó thêm `C` trước khi gọi `toList()`. So sánh với tình huống tương tự trên `ArrayList`. Vì sao chương trình `SourceTraversalPoliciesDemo` cho hai kết quả khác nhau?

**Đối chiếu:**

Stream từ `CopyOnWriteArrayList` trong ví dụ duyệt ảnh chụp tại lúc bộ duyệt được tạo, nên cho `[A, B]`. Stream từ `ArrayList` dùng cơ chế ràng buộc muộn trong tình huống đó, nên cho `[A, B, C]`. Cùng lời gọi `stream()` không thay thế hợp đồng riêng của loại nguồn.

### Bài 6: sửa một yêu cầu có trạng thái

Yêu cầu là “lấy ba phần tử đầu tiên thỏa điều kiện theo thứ tự nguồn”. Một giải pháp dùng bộ đếm nguyên tử trong `filter` để giữ ba lần xử lý đầu trên parallel stream. Vì sao cách đó không diễn đạt đúng yêu cầu?

**Đối chiếu:**

Thứ tự các luồng thực thi đến bộ đếm không phải thứ tự gặp phần tử trong nguồn. Bộ đếm có thể cập nhật an toàn nhưng chọn sai ba phần tử theo yêu cầu. Diễn đạt bằng cách lọc điều kiện rồi `limit(3)` trên stream có thứ tự phù hợp.

### Bài 7: thiết kế một phép biến đổi không can thiệp nguồn

Cho danh sách số `[1, 2, 3, 4, 5, 6]`. Viết chương trình tạo danh sách bình phương các số lẻ, rồi kiểm chứng:

- Nguồn vẫn là `[1, 2, 3, 4, 5, 6]`.
- Kết quả là `[1, 9, 25]`.
- Bản tuần tự và bản song song có cùng kết quả có thứ tự.
- Không dùng danh sách bên ngoài để tích lũy bằng `forEach`.
- Không dựa vào tên luồng thực thi, số lần gọi một bước quan sát hoặc ngoại lệ fail-fast để quyết định đúng sai.

Có thể phát triển từ `StreamExecutionModeDemo`: đổi điều kiện thành số lẻ, giữ phép bình phương và tạo kết quả bằng `toList()`. Sau đó giải thích tại sao phép xử lý không sửa nguồn, không có trạng thái dùng chung cần cập nhật và vẫn giữ đúng thứ tự kết quả.
