# estimateSize, getExactSizeIfKnown và các đặc tính nguồn

## 1. Bộ duyệt cần biết nhiều hơn “phần tử tiếp theo là gì?”

Một `Spliterator` vừa hỗ trợ duyệt phần tử, vừa hỗ trợ chia phần dữ liệu cho những công việc nhỏ hơn. Để quyết định chia thế nào, chuẩn bị vùng chứa ra sao hoặc có thể bỏ qua một bước xử lý nào, thư viện cần thông tin về nguồn.

Có hai nhóm thông tin chính:

- **Kích thước:** còn khoảng bao nhiêu phần tử; có bảo đảm biết chính xác hay không.
- **Đặc tính:** có thứ tự gặp, có phần tử trùng, có sắp xếp, có thể chứa `null`, và nguồn có chính sách thay đổi như thế nào.

Những thông tin mô tả này thường được gọi là siêu dữ liệu (metadata). Chúng là hợp đồng do bộ duyệt báo cáo. Chúng không phải kết quả tự động quét toàn bộ nguồn để kiểm chứng mọi thuộc tính.

Ví dụ, một `ArrayList` có bốn phần tử có thể cung cấp số lượng trước khi duyệt. Một iterator đến từ một quá trình tạo dữ liệu có thể chưa biết sẽ trả bao nhiêu phần tử. Cả hai đều có thể được biểu diễn bằng `Spliterator`, nhưng thư viện không được áp dụng cùng giả định về kích thước.

Cần phân biệt ba câu hỏi:

| Câu hỏi | API thường liên quan |
| --- | --- |
| Có thể ước lượng số phần tử sẽ gặp không? | `estimateSize()` |
| Bộ duyệt có báo một kích thước chính xác theo hợp đồng không? | `getExactSizeIfKnown()`, `SIZED` |
| Những bảo đảm nào đi kèm việc duyệt hoặc chia nguồn? | `characteristics()`, `hasCharacteristics(...)` |

“Bốn phần tử trong collection gốc”, “bốn phần tử còn thuộc phần việc của bộ duyệt này” và “bốn phần tử sẽ còn lại sau một bộ lọc” cũng là những điều khác nhau. Bài này đi từ kích thước của một bộ duyệt đến các đặc tính nguồn và cách chúng thay đổi khi xử lý.

Các chương trình độc lập dùng Java 17. Lưu đúng tên tệp theo `public class`; các lệnh biên dịch và stdout được ghi ngay sau từng chương trình.

## 2. estimateSize là ước lượng, không phải lệnh đếm

`estimateSize()` trả về một giá trị `long` ước lượng số phần tử mà việc duyệt phần còn lại sẽ gặp. Khi nguồn vô hạn, chưa biết kích thước hoặc tính số lượng quá tốn kém, phương thức có thể trả `Long.MAX_VALUE`.

Vì vậy:

- Một số hữu hạn trả về chưa tự chứng minh số đó chính xác.
- `Long.MAX_VALUE` không chứng minh nguồn chắc chắn vô hạn.
- Giá trị trả về không phải dung lượng mảng đã cấp phát cho collection.
- Nó mô tả phần việc của bộ duyệt đang hỏi, không phải lúc nào cũng là tổng kích thước nguồn ban đầu.

`estimateSize()` không phải một thao tác kết thúc stream đếm bằng cách duyệt qua mọi phần tử. Nó được thiết kế để cung cấp thông tin có thể dùng cho việc tổ chức xử lý, kể cả khi thông tin chỉ gần đúng. [Javadoc Spliterator.estimateSize](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Spliterator.html#estimateSize())

Một ước lượng vẫn có giá trị sử dụng. Chẳng hạn, biết một phần việc có khả năng lớn hơn phần khác giúp quyết định có tiếp tục chia hay không. Tuy nhiên, không lấy một ước lượng chưa được bảo đảm làm số lượng để kết luận rằng tất cả dữ liệu đã được xử lý.

### SIZED đặt điều kiện chính xác lên ước lượng

Đặc tính `SIZED` cho biết kích thước được báo có bảo đảm chính xác trong điều kiện của hợp đồng. Điểm thời gian rất quan trọng:

1. Nếu bộ duyệt có `SIZED` và chưa bị duyệt một phần hoặc chia, ước lượng phải là số phần tử chính xác cho một lần duyệt đầy đủ hợp lệ.
2. Nếu bộ duyệt có `SUBSIZED` và chưa bị duyệt một phần, bảo đảm chính xác còn áp dụng sau khi chia.
3. Ngoài những điều kiện đó, không chỉ nhìn cờ rồi suy ra mọi cách triển khai đều luôn cập nhật đúng số phần tử còn lại sau từng lần `tryAdvance`.

Các bảo đảm còn giả định nguồn không bị can thiệp trái với chính sách của nó. Không dùng một số lượng đã lấy trước đó để chứng minh nguồn không thể thay đổi.

Một số lớp cập nhật kích thước còn lại rất chính xác sau mỗi bước. Chương trình về `ArrayList` bên dưới cho thấy hành vi đó. Đây là điều tốt của cách triển khai cụ thể, không phải lý do bỏ qua điều kiện trạng thái của giao diện.

## 3. getExactSizeIfKnown không tự duyệt để tìm đáp án

Cách triển khai mặc định của `getExactSizeIfKnown()` có logic tương đương đoạn minh họa sau:

```java
// Mã minh họa logic mặc định, không phải chương trình độc lập.
return hasCharacteristics(Spliterator.SIZED) ? estimateSize() : -1L;
```

Nó hỏi bộ duyệt có báo `SIZED` hay không. Nếu có, trả về `estimateSize()`; nếu không, trả về `-1`. Phương thức không biến một nguồn chưa biết số lượng thành nguồn đã được đếm. [Javadoc getExactSizeIfKnown](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Spliterator.html#getExactSizeIfKnown())

Tên phương thức cần được đọc cùng hợp đồng về trạng thái bộ duyệt:

- Trước khi duyệt hoặc chia, `SIZED` là cơ sở để dùng số lượng chính xác.
- Khi nguồn có bảo đảm mạnh hơn như `SUBSIZED`, có thể giữ thông tin chính xác qua các lần chia theo điều kiện tương ứng.
- Sau khi đã duyệt một phần, cách triển khai mặc định vẫn chỉ kiểm tra `SIZED` rồi chuyển tiếp sang `estimateSize()`; nó không bổ sung một cơ chế kiểm đếm độc lập.

Do đó, muốn viết thuật toán tổng quát cho mọi `Spliterator`, không dùng tên “exact” để suy rộng rằng số trả về sau mọi trạng thái luôn là một bộ đếm còn lại được cập nhật.

### -1 và 0 mang ý nghĩa khác nhau

`-1` là tín hiệu không báo một kích thước chính xác. Nó không phải số lượng âm của dữ liệu và không đồng nghĩa nguồn rỗng.

`0` là một số lượng. Với một bộ duyệt mới có kích thước được bảo đảm chính xác và nguồn hợp lệ, `0` cho biết không có phần tử để duyệt.

Nếu thực sự cần số phần tử của một nguồn chưa biết kích thước, phải chọn một phép đếm có duyệt. Việc đó tiêu thụ bộ duyệt hoặc stream tương ứng, có thể tốn chi phí và không thể hoàn tất với nguồn vô hạn. Đọc metadata và duyệt để đếm là hai công việc khác nhau.

## 4. Thí nghiệm: kích thước của ArrayList khi duyệt và chia

Lưu vào `SpliteratorSizesDemo.java`.

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Spliterator;

public class SpliteratorSizesDemo {
    public static void main(String[] args) {
        List<Integer> source = new ArrayList<>(List.of(1, 2, 3, 4, 5, 6));
        Spliterator<Integer> remaining = source.spliterator();

        System.out.println("initialEstimate=" + remaining.estimateSize());
        System.out.println("initialExact=" + remaining.getExactSizeIfKnown());
        System.out.println("sized=" + remaining.hasCharacteristics(Spliterator.SIZED));
        System.out.println("subsized="
                + remaining.hasCharacteristics(Spliterator.SUBSIZED));

        List<Integer> first = new ArrayList<>();
        remaining.tryAdvance(first::add);
        System.out.println("first=" + first);
        long beforeSplit = remaining.estimateSize();
        System.out.println("estimateAfterOne=" + beforeSplit);
        System.out.println("exactAfterOne=" + remaining.getExactSizeIfKnown());

        Spliterator<Integer> prefix = remaining.trySplit();
        if (prefix == null) {
            throw new IllegalStateException("Expected a split for this ArrayList");
        }
        System.out.println("prefixExact=" + prefix.getExactSizeIfKnown());
        System.out.println("remainingExact=" + remaining.getExactSizeIfKnown());
        System.out.println("splitEstimatesAddUp="
                + (beforeSplit == prefix.estimateSize() + remaining.estimateSize()));

        List<Integer> left = new ArrayList<>();
        List<Integer> right = new ArrayList<>();
        prefix.forEachRemaining(left::add);
        remaining.forEachRemaining(right::add);
        System.out.println("prefixValues=" + left);
        System.out.println("remainingValues=" + right);
        System.out.println("remainingEstimateAfterDrain=" + remaining.estimateSize());
        System.out.println("source=" + source);
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 SpliteratorSizesDemo.java
java SpliteratorSizesDemo
```

Stdout:

```text
initialEstimate=6
initialExact=6
sized=true
subsized=true
first=[1]
estimateAfterOne=5
exactAfterOne=5
prefixExact=2
remainingExact=3
splitEstimatesAddUp=true
prefixValues=[2, 3]
remainingValues=[4, 5, 6]
remainingEstimateAfterDrain=0
source=[1, 2, 3, 4, 5, 6]
```

Đầu tiên, bộ duyệt bao phủ sáu phần tử nên cả ước lượng lẫn kích thước chính xác đều là 6. Nó báo `SIZED` và `SUBSIZED`.

Sau `tryAdvance`, phần tử `1` đã được xử lý. Với bộ duyệt của `ArrayList` trong chương trình, số lượng còn lại được cập nhật thành 5.

Lần `trySplit` tiếp theo trả về một bộ duyệt cho tiền tố `[2, 3]`; đối tượng `remaining` giữ phần `[4, 5, 6]`. Có thể hình dung:

```text
Ban đầu:            [1, 2, 3, 4, 5, 6]  kích thước 6
Đã duyệt:           [1]
Còn trước khi chia: [2, 3, 4, 5, 6]     kích thước 5
Sau khi chia:
  prefix            [2, 3]              kích thước 2
  remaining         [4, 5, 6]           kích thước 3
```

Tổng hai ước lượng sau chia bằng ước lượng trước chia: `2 + 3 = 5`. Đây là quan hệ mà `SUBSIZED` yêu cầu khi chia thành công.

Các bộ duyệt xử lý những phần việc tách nhau; `trySplit` không nhân bản mọi phần tử để cả hai đối tượng cùng duyệt toàn bộ nguồn. Sau khi phần việc của `remaining` được duyệt hết, ước lượng của nó trong ví dụ là 0. Danh sách nguồn vẫn giữ nguyên sáu số.

### SIZED và SUBSIZED không thay thế cho nhau

`SIZED` nói về thông tin kích thước của bộ duyệt hiện tại ở điều kiện đã nêu. `SUBSIZED` bổ sung bảo đảm rằng các bộ duyệt con được tạo trực tiếp hoặc gián tiếp bởi `trySplit` cũng có `SIZED` và `SUBSIZED`.

Một cấu trúc có thể biết tổng số phần tử nhưng không lưu sẵn số phần tử chính xác của mỗi nhánh nhỏ. Khi đó, báo `SIZED` cho bộ duyệt gốc chưa đủ để báo `SUBSIZED`.

Các quan hệ cần nhớ là:

```text
SUBSIZED ⇒ SIZED
SIZED ⇏ SUBSIZED
```

Tỷ lệ chia `2/3` trong chương trình là kết quả quan sát với `ArrayList` và trạng thái cụ thể. Không đặt yêu cầu mọi nguồn phải luôn chia đúng nửa. Một nguồn có thể không chia được hoặc quyết định không chia vì chi phí; `trySplit()` trả `null` không tự chứng minh rằng nguồn rỗng.

## 5. Thí nghiệm: nguồn hữu hạn nhưng không biết kích thước

Lưu vào `UnknownSizeSpliteratorDemo.java`.

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Spliterator;
import java.util.Spliterators;

public class UnknownSizeSpliteratorDemo {
    public static void main(String[] args) {
        Spliterator<String> unknown = Spliterators.spliteratorUnknownSize(
                List.of("red", "blue", "green").iterator(),
                Spliterator.ORDERED);

        System.out.println("estimateIsMax="
                + (unknown.estimateSize() == Long.MAX_VALUE));
        System.out.println("exact=" + unknown.getExactSizeIfKnown());
        System.out.println("sized=" + unknown.hasCharacteristics(Spliterator.SIZED));

        List<String> visited = new ArrayList<>();
        unknown.tryAdvance(visited::add);
        System.out.println("first=" + visited);
        System.out.println("estimateAfterOneIsMax="
                + (unknown.estimateSize() == Long.MAX_VALUE));
        System.out.println("exactAfterOne=" + unknown.getExactSizeIfKnown());

        unknown.forEachRemaining(visited::add);
        System.out.println("allVisited=" + visited);
        System.out.println("actualVisitedCount=" + visited.size());
        System.out.println("exactAfterDrain=" + unknown.getExactSizeIfKnown());
        System.out.println("hasAnother=" + unknown.tryAdvance(visited::add));

        Spliterator<String> empty = Spliterators.emptySpliterator();
        System.out.println("knownEmptyEstimate=" + empty.estimateSize());
        System.out.println("knownEmptyExact=" + empty.getExactSizeIfKnown());
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 UnknownSizeSpliteratorDemo.java
java UnknownSizeSpliteratorDemo
```

Stdout:

```text
estimateIsMax=true
exact=-1
sized=false
first=[red]
estimateAfterOneIsMax=true
exactAfterOne=-1
allVisited=[red, blue, green]
actualVisitedCount=3
exactAfterDrain=-1
hasAnother=false
knownEmptyEstimate=0
knownEmptyExact=0
```

Nguồn chỉ có ba chuỗi. Tuy nhiên, chương trình cố ý bọc iterator bằng `Spliterators.spliteratorUnknownSize`, nên bộ duyệt không báo `SIZED`. Phương thức hỗ trợ này cũng không báo `SIZED` hoặc `SUBSIZED` ngay cả nếu người gọi truyền các cờ đó vào tham số đặc tính. [Javadoc spliteratorUnknownSize](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Spliterators.html#spliteratorUnknownSize(java.util.Iterator,int))

Đọc các dòng kết quả:

- `estimateIsMax=true`: dùng `Long.MAX_VALUE` để biểu thị không có một ước lượng hữu hạn hữu ích lúc này.
- `exact=-1`: không báo kích thước chính xác.
- `first=[red]`: bộ duyệt vẫn duyệt bình thường dù chưa biết kích thước.
- Sau một phần tử, ước lượng trong cách triển khai này vẫn là `Long.MAX_VALUE`.
- `actualVisitedCount=3`: việc duyệt thật đã xử lý ba phần tử.
- `exactAfterDrain=-1`: không tự xuất hiện cờ `SIZED` chỉ vì đã đi đến cuối.
- `hasAnother=false`: `tryAdvance` mới trực tiếp xác nhận không còn phần tử cho lần gọi đó.
- Bộ duyệt rỗng được tạo bằng `emptySpliterator` báo ước lượng và kích thước chính xác là 0.

Điều này cho thấy **không biết kích thước** và **không có phần tử** là hai trạng thái khác nhau.

### Không dùng metadata thay cho điều kiện duyệt

Không viết vòng lặp tổng quát kiểu “cứ duyệt khi `getExactSizeIfKnown() > 0`”. Với nguồn chưa biết kích thước, giá trị `-1` sẽ khiến bỏ qua cả nguồn đang có dữ liệu.

Cũng không dùng “`estimateSize() == Long.MAX_VALUE` thì dừng vì nguồn vô hạn”. Chương trình vừa kiểm chứng một nguồn hữu hạn có đúng giá trị ước lượng đó.

Khi mục tiêu là duyệt từng phần tử, dùng kết quả của `tryAdvance` hoặc thao tác duyệt phù hợp. Khi mục tiêu là quyết định chiến lược, đọc metadata cùng các bảo đảm của nó.

### Đếm nguồn sẽ tiêu thụ nguồn

Biến `actualVisitedCount` trong ví dụ được suy ra từ danh sách các giá trị đã thu thập sau khi duyệt. Đây là một phép kiểm chứng có chi phí duyệt và lưu kết quả.

Nếu chỉ cần đếm, có thể dùng một phép tổng hợp đếm thay cho lưu tất cả. Nhưng vẫn không thể dùng lại bộ duyệt đã bị tiêu thụ để đi qua nguồn lần nữa. Muốn vừa có kết quả vừa có số lượng, thiết kế phép xử lý để giữ thông tin cần thiết hoặc tạo một bộ duyệt mới từ nguồn có thể duyệt lại.

## 6. Đặc tính nào liên quan trực tiếp đến kích thước?

`characteristics()` là mặt nạ bit công bố các bảo đảm của bộ duyệt. Có thể gọi `hasCharacteristics(mask)` để hỏi xem bộ duyệt có đủ **tất cả** bit trong mặt nạ hay không. Khi đang quyết định về kích thước, hai bit cần xem trước là:

| Bit | Điều được bảo đảm |
| --- | --- |
| `SIZED` | Kích thước ước lượng chính xác khi đáp ứng điều kiện về trạng thái duyệt và nguồn không bị can thiệp sai hợp đồng. |
| `SUBSIZED` | Những bộ duyệt tạo ra trực tiếp hoặc gián tiếp qua `trySplit` tiếp tục có bảo đảm `SIZED` và `SUBSIZED`. |

Quan hệ là `SUBSIZED ⇒ SIZED`, còn `SIZED` không suy ra `SUBSIZED`. Vì vậy, một bộ duyệt biết số lượng toàn nguồn vẫn có thể không biết chính xác kích thước của từng phần được chia. `getExactSizeIfKnown()` mặc định dựa vào `SIZED` và `estimateSize()`; nó không tự đếm lại phần còn lại.

Những bit khác trả lời câu hỏi khác: `ORDERED` nói về thứ tự gặp, `SORTED` về quy tắc sắp xếp, `DISTINCT` về phần tử không trùng theo equals, `NONNULL` về việc không có phần tử null, `IMMUTABLE` về nguồn ổn định khi duyệt và `CONCURRENT` về chính sách cập nhật nguồn. Không có một bit không có nghĩa thuộc tính đối nghịch chắc chắn đúng. Các điều kiện và quan hệ của từng bit được phân tích riêng trong bài *ORDERED, SORTED, DISTINCT, SIZED, IMMUTABLE và CONCURRENT*.

## 7. Đối chiếu nguồn để không suy kích thước từ tên lớp

Trên JDK 17, bộ duyệt `ArrayList` thông thường có `SIZED` và `SUBSIZED`, nên ví dụ ở mục 4 kiểm chứng được kích thước của hai phần sau chia. Bộ duyệt `TreeSet` báo `SIZED` nhưng không báo `SUBSIZED`: biết tổng số phần tử chưa đủ để yêu cầu mọi nhánh con có số lượng chính xác. Một nguồn bọc iterator bằng `spliteratorUnknownSize` như mục 5 không báo `SIZED` dù dữ liệu thực tế hữu hạn.

`CopyOnWriteArrayList` có cơ chế duyệt ảnh chụp và báo `IMMUTABLE`, trong khi khung nhìn khóa `ConcurrentHashMap` báo `CONCURRENT` và không cam kết kích thước chính xác như một ảnh chụp nguyên tử khi nguồn có thể được cập nhật. Đây là sự khác biệt trong **chính sách nguồn**, không phải chứng minh bộ duyệt hoặc hàm xử lý tự an toàn khi nhiều luồng cùng sửa trạng thái ngoài pipeline.

Khi viết thuật toán, hãy kiểm tra bit của **đối tượng Spliterator đang sử dụng**, thay vì lấy một bảng cờ của lớp khác để suy diễn. Phần tiếp theo xét vì sao chính các thao tác của Stream có thể làm thay đổi metadata đó.

## 8. Kích thước nguồn không phải kích thước của mọi pipeline

Một danh sách có bốn phần tử không có nghĩa mọi stream bắt đầu từ nó đều biết trước số phần tử đầu ra.

- `map` thông thường biến mỗi phần tử đầu vào thành một phần tử đầu ra, nên có thể giữ thông tin số lượng.
- `filter` có thể loại bao nhiêu phần tử tùy giá trị và điều kiện; trước khi đánh giá, chưa chắc biết số lượng đầu ra.
- `limit` có thể làm thông tin số lượng thay đổi theo một giới hạn đã biết.
- Các bước khác còn có thể làm thay đổi những đặc tính như `DISTINCT` hoặc `SORTED`.

Cần hỏi metadata của đúng bộ duyệt đang xử lý, không lấy metadata nguồn ban đầu rồi áp nguyên cho đầu ra.

Lưu vào `StreamSizeMetadataDemo.java`.

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Spliterator;

public class StreamSizeMetadataDemo {
    private static void describe(String name, Spliterator<?> spliterator) {
        System.out.println(name + ":estimate=" + spliterator.estimateSize()
                + ",exact=" + spliterator.getExactSizeIfKnown()
                + ",sized=" + spliterator.hasCharacteristics(Spliterator.SIZED));
    }

    public static void main(String[] args) {
        List<String> source = new ArrayList<>(
                List.of("A", "BB", "CCC", "DDDD"));

        describe("source", source.spliterator());
        describe("mapped", source.stream().map(String::length).spliterator());

        Spliterator<String> filtered = source.stream()
                .filter(value -> value.length() >= 3)
                .spliterator();
        describe("filtered", filtered);
        List<String> selected = new ArrayList<>();
        filtered.forEachRemaining(selected::add);
        System.out.println("filteredActual=" + selected);
        System.out.println("filteredActualCount=" + selected.size());

        describe("limited", source.stream().limit(2).spliterator());
        System.out.println("source=" + source);
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 StreamSizeMetadataDemo.java
java StreamSizeMetadataDemo
```

Stdout:

```text
source:estimate=4,exact=4,sized=true
mapped:estimate=4,exact=4,sized=true
filtered:estimate=4,exact=-1,sized=false
filteredActual=[CCC, DDDD]
filteredActualCount=2
limited:estimate=2,exact=2,sized=true
source=[A, BB, CCC, DDDD]
```

Đây là kết quả kiểm chứng trên JDK 17:

| Trường hợp | Ước lượng | Kích thước chính xác báo được | Quan sát |
| --- | --- | --- | --- |
| Nguồn `ArrayList` | 4 | 4 | Biết số lượng trước khi duyệt |
| Sau `map(String::length)` | 4 | 4 | Không thay đổi số lượng |
| Sau `filter` giữ chuỗi dài từ 3 ký tự | 4 | -1 | Chưa biết chính xác số chuỗi qua lọc |
| Sau `limit(2)` trên nguồn đã biết kích thước | 2 | 2 | Cách triển khai tính được giới hạn số lượng |

Với `filtered`, ước lượng 4 không phải số phần tử kết quả thực. Khi duyệt, chỉ có `CCC` và `DDDD`, nên số thực là 2.

Không suy rộng rằng mọi ước lượng chưa có `SIZED` đều luôn là một cận trên chặt hoặc luôn bằng số phần tử nguồn. Hợp đồng chung cho phép ước lượng không chính xác; bảng chỉ mô tả các bộ duyệt cụ thể trong chương trình.

Cũng không dùng ví dụ này để khẳng định mọi nguồn hoặc mọi cách triển khai stream đều phải báo bộ cờ giống nhau sau mỗi thao tác. Phía sử dụng đọc những bảo đảm thực tế được báo, còn kết quả phép xử lý vẫn phải tuân theo hợp đồng của thao tác stream.

### Lấy spliterator từ stream là chuyển quyền điều khiển việc duyệt

`Stream.spliterator()` là một thao tác kết thúc đặc biệt cho phép người gọi tự điều khiển việc duyệt. Sau khi đã lấy bộ duyệt, không tiếp tục dùng chính đối tượng stream đó cho một thao tác kết thúc khác. [Javadoc BaseStream.spliterator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/BaseStream.html#spliterator())

Chương trình tạo một stream mới cho mỗi trường hợp `mapped`, `filtered` và `limited`. Riêng `filtered` được duyệt qua bộ duyệt đã lấy, không quay lại gọi `toList()` trên một stream đã sử dụng.

Việc gọi `estimateSize` hoặc `getExactSizeIfKnown` trên bộ duyệt không đồng nghĩa đã xử lý từng phần tử. Tuy nhiên, lấy bộ duyệt từ stream đã xác lập cách sử dụng stream đó; không nhầm hai vòng đời này.

## 9. Hỏi kích thước có thể làm nguồn ràng buộc sớm

Một bộ duyệt ràng buộc muộn chưa nhất thiết chốt phạm vi nguồn ngay lúc được tạo. Theo hợp đồng của loại bộ duyệt này, lần duyệt đầu, lần chia đầu hoặc lần hỏi kích thước ước lượng đầu có thể là thời điểm ràng buộc với nguồn.

Vì vậy, thao tác “chỉ xem thử kích thước” không nhất thiết hoàn toàn vô nghĩa đối với vòng đời của bộ duyệt.

Đoạn dưới minh họa mốc cần chú ý, không phải chương trình mẫu với kết quả duyệt sau sửa được bảo đảm:

```java
List<String> source = new ArrayList<>(List.of("A", "B"));
Spliterator<String> spliterator = source.spliterator();

long initialEstimate = spliterator.estimateSize();
// Lần hỏi kích thước đã ràng buộc bộ duyệt ArrayList với nguồn.

source.add("C");
// Không tiếp tục xem đây là cùng tình huống với việc thêm trước ràng buộc.
// Duyệt tiếp trên bộ duyệt đã ràng buộc có thể phát hiện can thiệp.
```

`getExactSizeIfKnown` mặc định gọi `estimateSize` khi có `SIZED`, nên cũng có thể dẫn tới việc ràng buộc đó.

Không dùng một lần ghi nhật ký thông tin mô tả rồi giả định bộ duyệt vẫn còn ở trạng thái hoàn toàn chưa đụng đến nguồn. Nếu cần xử lý dữ liệu sau khi đã sửa một collection thông thường, tạo bộ duyệt mới ở thời điểm hợp lệ hoặc thiết kế một ảnh chụp riêng.

### Có kích thước chính xác không có nghĩa nguồn không đổi

`SIZED` mô tả số lượng trong những điều kiện hợp lệ, không cung cấp khóa hay ngăn một bên khác sửa nguồn. `ArrayList` vẫn cần tuân thủ chính sách không can thiệp trong lúc duyệt.

Bộ duyệt fail-fast có thể ném `ConcurrentModificationException` khi phát hiện thay đổi, nhưng việc phát hiện không bảo đảm bắt mọi trường hợp. Không có ngoại lệ chưa chứng minh dữ liệu không bị can thiệp.

Tương tự, `CONCURRENT` không giải quyết mọi yêu cầu về tính nhất quán. Nếu nguồn đang thay đổi, cần đọc chính sách của nguồn để biết kết quả duyệt có thể quan sát các cập nhật như thế nào, thay vì đòi một kích thước cố định suốt quá trình.

## 10. Dùng metadata để lựa chọn, không bịa thêm bảo đảm

### Chuẩn bị vùng chứa

Nếu có một kích thước chính xác trong trạng thái được bảo đảm, thông tin đó có thể giúp chuẩn bị vùng chứa phù hợp. Nếu chỉ có ước lượng hoặc giá trị không biết, vùng chứa cần tăng trưởng linh hoạt.

Trước khi dùng một giá trị `long` để tạo vùng chứa có kích thước kiểu `int`, cần kiểm tra phạm vi. Không ép `Long.MAX_VALUE` hoặc `-1` thành một kích thước mảng rồi xem đó là số phần tử thực.

Trong mã ứng dụng thông thường, thao tác thu thập của stream thường đã xử lý những quyết định này. Không cần tự dựng một thuật toán cấp phát chỉ để thay một lời gọi thu thập rõ ràng.

### Chia công việc

`estimateSize` giúp đánh giá quy mô phần việc; `SUBSIZED` cho thêm bảo đảm về kích thước các phần sau chia. Tuy nhiên, biết kích thước không nói rằng mỗi phần tử có cùng chi phí xử lý.

Hai phần có cùng số phần tử vẫn có thể mất thời gian rất khác nhau. Ngược lại, một nguồn có ước lượng chưa chính xác vẫn có thể chia và xử lý hiệu quả. Các cờ là thông tin đầu vào cho chiến lược, không phải kết quả đo hiệu năng.

### Tối ưu thao tác stream

Biết số lượng và đặc tính có thể giúp thư viện chọn cách xử lý tốt hơn. Ví dụ, khi số lượng đã biết và những bước trung gian không làm thay đổi số lượng, một phép `count` có thể không cần duyệt từng phần tử. Điều này cũng là lý do không đặt hành động bắt buộc vào một bước quan sát rồi giả định nó luôn được gọi. [Javadoc Stream.count](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html#count())

Không tự gắn `SIZED`, `SORTED` hoặc `DISTINCT` cho một bộ duyệt chỉ để mong thư viện chạy nhanh hơn. Nếu thông tin báo sai, phía sử dụng có thể bỏ qua những công việc mà thực tế vẫn cần làm.

### Những lỗi cần nhận ra

| Cách hiểu sai | Điều cần sửa |
| --- | --- |
| `estimateSize` luôn là số phần tử thật | Kiểm tra `SIZED`, `SUBSIZED`, trạng thái duyệt và chính sách nguồn |
| `Long.MAX_VALUE` chứng minh nguồn vô hạn | Nó còn có thể biểu thị chưa biết hoặc tính kích thước quá tốn kém |
| `getExactSizeIfKnown` tự đếm toàn bộ | Cách mặc định chỉ kiểm tra cờ rồi trả metadata hoặc `-1` |
| `-1` nghĩa là hết dữ liệu | Dùng thao tác duyệt để xác định còn phần tử; `-1` là không biết kích thước |
| Có `SIZED` thì mọi con sau chia cũng có | Cần phân biệt với bảo đảm `SUBSIZED` |
| Bộ duyệt đã duyệt một phần vẫn luôn báo chính xác phần còn lại | Đọc bảo đảm theo trạng thái và cách triển khai; không suy rộng từ một ví dụ |
| `ORDERED` đồng nghĩa `SORTED` | Thứ tự chỉ số hoặc thứ tự chèn không phải thứ tự sắp xếp |
| Không có `NONNULL` nghĩa là chắc có null | Thiếu cờ chỉ có nghĩa không cung cấp cam kết đó |
| `IMMUTABLE` làm mọi đối tượng phần tử bất biến | Nó mô tả nguồn phần tử của lần duyệt, không phải bất biến sâu |
| `CONCURRENT` cho phép nhiều bên dùng cùng bộ duyệt tùy ý | Tách chính sách cập nhật nguồn khỏi quyền truy cập đối tượng bộ duyệt |
| `hasCharacteristics` với mặt nạ A và B chỉ cần có một cờ | Phương thức yêu cầu có tất cả cờ trong mặt nạ |
| Hỏi kích thước không ảnh hưởng trạng thái nguồn ràng buộc | Trên nguồn ràng buộc muộn, việc hỏi có thể kích hoạt ràng buộc |

## 11. Thực hành đọc đúng những bảo đảm

### Bài 1: một số hữu hạn chưa có SIZED

Một bộ duyệt báo `estimateSize() == 100` nhưng không có `SIZED`. Có thể dùng 100 làm tổng số phần tử chắc chắn sẽ duyệt không? Cách mặc định của `getExactSizeIfKnown()` trả gì?

**Đối chiếu:**

Không thể khẳng định số thật là 100 chỉ từ ước lượng. Cách mặc định trả `-1` vì không có `SIZED`. Số hữu hạn và kích thước được bảo đảm chính xác là hai điều kiện khác nhau.

### Bài 2: nguồn có ba phần tử nhưng ước lượng cực lớn

`spliteratorUnknownSize` bọc iterator của một danh sách có ba phần tử. Nó báo `Long.MAX_VALUE` và `-1` ở hai phương thức kích thước. Dữ liệu có bị mất hoặc nguồn có bắt buộc vô hạn không?

**Đối chiếu:**

Không cho cả hai câu. Lớp bao không cung cấp kích thước chính xác nhưng vẫn duyệt được ba phần tử. Có thể kiểm chứng bằng `tryAdvance` hoặc `forEachRemaining`; việc đó thực sự tiêu thụ các phần tử.

### Bài 3: biết tổng nhưng chưa biết từng phần

Một bộ duyệt gốc có `SIZED` nhưng không có `SUBSIZED`. Sau `trySplit`, có được mặc định mọi bộ duyệt con đều có kích thước chính xác không?

**Đối chiếu:**

Không. Phải xem đặc tính và hợp đồng của từng bộ duyệt con. Bảo đảm `SIZED` của gốc không tự tạo bảo đảm đệ quy về kích thước các phần chia.

### Bài 4: dữ liệu đang không null

Một `ArrayList<String>` đang chứa `[A, B]`, nhưng bộ duyệt không báo `NONNULL`. Có mâu thuẫn không?

**Đối chiếu:**

Không. Hai giá trị hiện tại đều khác `null`, nhưng lớp không cung cấp cam kết `NONNULL` qua bộ duyệt đó. Thiếu cờ không đồng nghĩa khẳng định ngược lại.

### Bài 5: sắp xếp và thứ tự tự nhiên

Một bộ duyệt có `SORTED`, và `getComparator()` trả `null`. Nó có còn phải báo `ORDERED` không? Giá trị `null` có nghĩa nguồn không được sắp xếp không?

**Đối chiếu:**

Nó vẫn phải có `ORDERED`. Giá trị `null` ở trường hợp có `SORTED` biểu thị dùng thứ tự tự nhiên. Nếu không có `SORTED`, lời gọi `getComparator` không phải trả `null` để báo “không biết” mà ném `IllegalStateException`.

### Bài 6: cờ có trước và sau phép lọc

Nguồn có bốn chuỗi, nhưng chỉ hai chuỗi thỏa điều kiện. Bộ duyệt của pipeline sau `filter` báo ước lượng 4, kích thước chính xác `-1`. Cần dùng số nào làm số kết quả thật?

**Đối chiếu:**

Chưa có số kết quả thật từ metadata đó. Phải thực hiện phép xử lý để biết có hai chuỗi qua lọc. Không gán số 4 cho kích thước kết quả chỉ vì đó là kích thước nguồn hoặc ước lượng đang được báo.

### Bài 7: đọc mặt nạ nhiều cờ

Một bộ duyệt có `ORDERED` và `SIZED`, nhưng không có `SORTED`. Dự đoán:

```java
// Đoạn câu hỏi, s là bộ duyệt có các cờ vừa nêu.
boolean first = s.hasCharacteristics(Spliterator.ORDERED | Spliterator.SIZED);
boolean second = s.hasCharacteristics(Spliterator.ORDERED | Spliterator.SORTED);
```

**Đối chiếu:**

Biểu thức đầu trả `true`; biểu thức sau trả `false`. Phải có đủ mọi cờ được yêu cầu.

### Bài 8: kiểm tra sau một phần đã duyệt

Trong `SpliteratorSizesDemo`, sau khi duyệt phần tử đầu, cả hai phương thức đều cho 5. Có thể biến kết quả này thành quy tắc bắt buộc cho mọi `Spliterator` có `SIZED` sau từng `tryAdvance` không?

**Đối chiếu:**

Không. Chương trình kiểm chứng cách triển khai của `ArrayList` ở trạng thái cụ thể. Hợp đồng chung của ước lượng phân biệt trạng thái chưa duyệt, đã chia và đã duyệt một phần. Cách mặc định của `getExactSizeIfKnown` không tự bổ sung phép đếm còn lại.

Khi thiết kế một phép xử lý mới, hãy ghi rõ đang hỏi bộ duyệt nào, đã tiêu thụ hoặc chia phần nào, nguồn có thể thay đổi theo chính sách nào và cờ nào thật sự được báo. Những thông tin đó mới cho phép dùng metadata đúng ý nghĩa.
