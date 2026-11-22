# Spliterator: estimateSize() và getExactSizeIfKnown() trong Java

> **Phạm vi:** Java 8 — chủ đề Spliterator. Bài giải thích hai phương thức ước lượng và xác định số phần tử còn lại, cùng hợp đồng `SIZED`/`SUBSIZED`, cách chia nguồn và các lưu ý khi xử lý Stream song song. Các API này có từ Java 8 và vẫn còn áp dụng trong Java hiện hành.

## 1. Vấn đề cần giải quyết

Khi Java Stream xử lý một tập dữ liệu, đặc biệt bằng parallel stream, framework cần quyết định nên chia nguồn thành bao nhiêu phần, liệu có đủ công việc để tách tiếp không và có thể dự trù dung lượng kết quả đến mức nào. Giao diện `java.util.Spliterator<T>` cung cấp hai câu trả lời liên quan đến kích thước:

- `estimateSize()`: **ước lượng** số phần tử *còn lại* mà Spliterator sẽ cung cấp nếu duyệt hết. Kết quả không mặc nhiên là chính xác.
- `getExactSizeIfKnown()`: lấy **kích thước chính xác nếu Spliterator báo đặc tính `SIZED`**, nếu không trả về `-1L`.

Các phương thức này là **thông tin về nguồn trước/giữa quá trình duyệt**. Chúng không tương đương với việc tự thu thập tất cả phần tử rồi đếm.

Ví dụ đơn giản trên một mảng cố định:

~~~java
int[] values = {10, 20, 30, 40, 50, 60};
Spliterator.OfInt spliterator = Arrays.spliterator(values);

System.out.println(spliterator.estimateSize());         // 6
System.out.println(spliterator.getExactSizeIfKnown());  // 6
~~~

Đây là **đoạn minh họa**, cần `import java.util.Arrays;` và `import java.util.Spliterator;`. Spliterator được tạo từ mảng có `SIZED` và `SUBSIZED` nên lúc chưa duyệt, kích thước chính xác là `6`.

Ngược lại, một Spliterator được tạo từ Iterator không biết trước kích thước có thể có **sáu phần tử thật**, nhưng vẫn trả `-1` khi hỏi kích thước chính xác. “Không biết” không đồng nghĩa “rỗng”.

## 2. Hợp đồng API: đọc đúng từng giá trị

### 2.1. estimateSize()

Chữ ký:

~~~java
long estimateSize();
~~~

Ý nghĩa theo Javadoc: trả một **ước lượng số phần tử sẽ được gặp khi duyệt toàn bộ phần còn lại bằng `forEachRemaining`**. Nếu số phần tử là vô hạn, không biết hoặc chi phí tính toán chính xác quá cao, phương thức được phép trả `Long.MAX_VALUE`.

| Giá trị quan sát | Diễn giải đúng |
| --- | --- |
| `0L` | Ước lượng không có phần tử còn lại; nếu `SIZED` trong điều kiện được bảo đảm thì đúng là rỗng. |
| `6L` | Ước lượng còn sáu phần tử; chỉ là số đếm chắc chắn nếu có bảo đảm `SIZED` thích hợp. |
| `100L` | Ước lượng khoảng một trăm phần tử; với nguồn không `SIZED`, có thể lệch nhiều. |
| `Long.MAX_VALUE` | **Giá trị quy ước** khi vô hạn, không biết hoặc quá tốn công để tính; không được coi đó là số phần tử thật. |

**Cần tránh hai suy luận sai:**

1. Có `estimateSize() == 10` **không chứng minh** nguồn có đúng mười phần tử.
2. Có `estimateSize() == Long.MAX_VALUE` **không chứng minh** nguồn vô hạn; nguồn hữu hạn nhưng không có size metadata cũng có thể dùng giá trị này.

Từ “còn lại” rất quan trọng: đó không phải `Collection.size()` của toàn bộ nguồn ban đầu nếu Spliterator đã duyệt hoặc đã tách phần tử sang Spliterator khác.

### 2.2. getExactSizeIfKnown()

Chữ ký:

~~~java
default long getExactSizeIfKnown();
~~~

Hợp đồng của triển khai mặc định tương đương:

~~~java
return hasCharacteristics(Spliterator.SIZED)
        ? estimateSize()
        : -1L;
~~~

Đây là **biểu thức mô tả implementation mặc định**, không phải mã đầy đủ của một phương thức độc lập. Nó chỉ kiểm tra cờ `SIZED` rồi trả giá trị `estimateSize()` hoặc `-1L`; **không** duyệt nguồn để tự đếm, không có bước phân tích dữ liệu bổ sung.

| Tình huống | `getExactSizeIfKnown()` |
| --- | --- |
| Spliterator báo `SIZED`, có 6 phần tử chưa duyệt và ước lượng theo hợp đồng là 6 | `6L` |
| Spliterator báo `SIZED`, nguồn rỗng | `0L` |
| Spliterator **không** báo `SIZED`, dù thực tế có 6 phần tử | `-1L` |
| Spliterator **không** báo `SIZED`, dù `estimateSize()` tình cờ đúng bằng 6 | **Vẫn `-1L`** |
| Không báo `SIZED`, giá trị `estimateSize()` là `Long.MAX_VALUE` | `-1L` |

**`-1L` là “không có số đếm chính xác được cam kết”, không phải “có -1 phần tử” hay “không có phần tử”.** Trước khi lấy `int` hoặc tạo mảng theo kết quả này phải kiểm tra rõ điều kiện.

### 2.3. Hai phương thức không làm công việc gì?

- Không **biến** một Spliterator thành `SIZED` nếu trước đó nó không báo cờ.
- Không bắt buộc phải **duyệt hết** dữ liệu để tính size.
- Không tự làm thay `Stream.count()`, `Collection.size()` hay `List.size()`.
- Không tự kiểm tra được dữ liệu nguồn có bị một thread khác sửa giữa các lời gọi hay không.
- Không hứa số thread, số task hoặc tốc độ chạy parallel.

Một nguồn có thể hữu hạn, không có `SIZED` và vẫn tạo ra mọi phần tử bình thường; không nên bỏ dữ liệu chỉ vì `getExactSizeIfKnown() == -1`.

## 3. SIZED và SUBSIZED: khi nào ước lượng thực sự chính xác?

Hai characteristic thuộc `java.util.Spliterator`, không phải `Collector.Characteristics`.

### 3.1. SIZED

`Spliterator.SIZED` có nghĩa `estimateSize()` **trước khi bắt đầu duyệt hoặc tách** biểu thị **kích thước hữu hạn chính xác**, với điều kiện không có thay đổi cấu trúc nguồn trái với hợp đồng.

Ví dụ: một Spliterator mới từ mảng `int[]` cố định có đủ metadata để biết số phần tử cần duyệt.

**Giới hạn quan trọng trong Javadoc:** Nếu Spliterator chỉ có `SIZED` và đã duyệt một phần hoặc đã tách, lời hứa tổng quát về độ chính xác ở mọi thời điểm có thể không còn như lúc ban đầu. Việc `getExactSizeIfKnown()` tiếp tục gọi `estimateSize()` **không tự bổ sung bảo đảm mới**. Đừng viết thuật toán tùy biến giả định size luôn được cập nhật chính xác sau mọi hành động nếu implementation không hứa điều đó.

Một số implementation thực tế (ví dụ Spliterator mảng) có thể cập nhật số phần tử còn lại rất chính xác; nhưng mã tổng quát nên dựa vào hợp đồng `Spliterator` hoặc hợp đồng chặt hơn của nguồn cụ thể.

### 3.2. SUBSIZED

`Spliterator.SUBSIZED` là hợp đồng **mạnh hơn khi chia nguồn**: mọi Spliterator con sinh ra từ `trySplit()` đều có đặc tính **`SIZED` và `SUBSIZED`**.

Một Spliterator có `SUBSIZED` phải có `SIZED` tương ứng; nếu không, tập characteristic của nó không nhất quán. Khác với `SIZED` đơn thuần, `SUBSIZED` hỗ trợ suy luận kích thước các phần sau khi tách.

| Câu hỏi | `SIZED` | `SUBSIZED` |
| --- | --- | --- |
| Kích thước Spliterator mới, trước duyệt/tách, chính xác? | Có, theo điều kiện hợp đồng | Có, vì cũng phải `SIZED` |
| Các Spliterator con chắc chắn cũng báo `SIZED`? | **Không** | **Có** |
| Mọi Spliterator con cũng có `SUBSIZED`? | **Không** | **Có** |
| Sau một lần `trySplit()` thành công, tổng size hai phần bằng size trước đó? | Chỉ có ràng buộc bất đẳng thức chung | **Có**, theo hợp đồng |
| Bắt buộc tách đúng 50/50? | Không | **Không** |

`SUBSIZED` **không** có nghĩa Spliterator chắc chắn tách được tại mọi thời điểm. `trySplit()` vẫn được phép trả `null` do nguồn rỗng, không thể tách, chi phí không hợp lý hoặc trạng thái đã duyệt.

### 3.3. Vì sao SIZED nhưng không SUBSIZED vẫn có ích?

Hãy hình dung một cây có bộ đếm tổng phần tử chính xác, nhưng không giữ bộ đếm riêng từng cây con. Spliterator ở gốc có thể biết chính xác kích thước toàn bộ cây (**`SIZED`**) trong khi kích thước mỗi phần sau tách chưa chắc được biết (**không `SUBSIZED`**). Đây là mô hình được Javadoc nêu để phân biệt hai cờ; không phải mọi loại cây trong JDK đều có đặc điểm này.

Với parallel stream, `SIZED` có thể hữu ích cho hoạch định công việc, còn `SUBSIZED` đặc biệt hữu ích để dự trù chính xác kích thước từng nhánh. Tuy nhiên, có size chính xác **không bảo đảm** phải chạy parallel hoặc tự động nhanh hơn.

## 4. trySplit() tác động đến estimateSize() như thế nào?

### 4.1. Trước và sau chia nguồn

`trySplit()` có chữ ký:

~~~java
Spliterator<T> trySplit();
~~~

Khi tách thành công, phương thức trả một Spliterator mới bao phủ **một số phần tử mà Spliterator gốc sẽ không duyệt nữa**. Với Spliterator có `ORDERED`, phần mới phải là **prefix nghiêm ngặt** của phần chưa duyệt theo encounter order.

Giả sử trước khi tách:

~~~text
Nguồn có 8 phần tử:
[1, 2, 3, 4, 5, 6, 7, 8]
    estimateSize() = 8, getExactSizeIfKnown() = 8
~~~

Một cách chia **có thể** xảy ra:

~~~text
                  [1,2,3,4,5,6,7,8]
                     trySplit()
                     /        \
          prefix [1,2,3,4]    remaining [5,6,7,8]
             size = 4              size = 4
~~~

Đây chỉ là **mô hình minh họa**; Java không hứa chia thành hai nửa bằng nhau. Với `SUBSIZED`, nếu tách thành công, số phần tử ước tính được bảo đảm:

~~~text
estimateSize(trước khi split)
    = estimateSize(prefix sau split)
      + estimateSize(remaining sau split)
~~~

Ví dụ tổng vẫn là `8`, kể cả khi framework chia thành `3 + 5` hoặc `1 + 7` (nếu việc chia đó phù hợp implementation).

Với Spliterator tổng quát **không có `SUBSIZED`**, đặc tả chỉ ràng buộc bất đẳng thức:

~~~text
estimateSize(trước khi split)
    >= estimateSize(prefix sau split)
       + estimateSize(remaining sau split)
~~~

Không được tự suy ra dấu bằng; và với giá trị không biết như `Long.MAX_VALUE`, **không được cộng `long` một cách mù quáng** vì có thể overflow.

### 4.2. Không tính cố định số lần tách

Một chương trình không nên dựa vào các giả định:

- `trySplit()` luôn trả một object mới nếu còn trên một phần tử.
- Kích thước hai nửa luôn bằng nhau.
- `estimateSize()` chắc chắn giảm một nửa sau mọi lời gọi `trySplit()`.
- Cứ tách được thì chạy parallel là nhanh.
- `getExactSizeIfKnown()` của mọi Spliterator con đều khác `-1` dù Spliterator cha chỉ có `SIZED`.

Đối với nguồn hữu hạn, việc gọi `trySplit()` lặp lại phải **cuối cùng đạt đến trường hợp không chia tiếp được**. Nhưng số lần và kích thước các phần phụ thuộc cấu trúc dữ liệu, đặc tính của nguồn và implementation.

### 4.3. Tách có liên quan tới thread safety không?

Spliterator **không mặc định thread-safe**. Thông thường một thread tách Spliterator rồi giao Spliterator *khác* cho một tác vụ riêng, tránh hai thread cùng gọi `tryAdvance`/`trySplit` đồng thời trên **chính một đối tượng**. Hai phương thức size không làm traversal thread-safe.

Cờ `Spliterator.CONCURRENT` (nguồn có cơ chế nhất quán khi thay đổi đồng thời) cũng **khác** với `Collector.Characteristics.CONCURRENT` (accumulator có thể nhận cập nhật đồng thời trên cùng container). Không trộn hai khái niệm.

## 5. Ví dụ chạy được: SIZED, SUBSIZED, nguồn chưa biết size và split

Lưu chương trình sau thành **SpliteratorSizeDemo.java**. Ví dụ cố ý **không in kích thước chính xác từng phần sau split**, vì hợp đồng không bắt buộc một chiến lược chia cố định. Thay vào đó, chương trình chỉ in những kết quả được bảo đảm.

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Spliterator;
import java.util.Spliterators;
import java.util.stream.Collectors;
import java.util.stream.StreamSupport;

public class SpliteratorSizeDemo {
    public static void main(String[] args) {
        int[] values = {10, 20, 30, 40, 50, 60};

        // Spliterator.OfInt từ mảng: kích thước xác định và có thể chia.
        Spliterator.OfInt sized = Arrays.spliterator(values);
        System.out.println("sized flag = "
                + sized.hasCharacteristics(Spliterator.SIZED));
        System.out.println("subsized flag = "
                + sized.hasCharacteristics(Spliterator.SUBSIZED));
        System.out.println("estimate initially = " + sized.estimateSize());
        System.out.println("exact initially = "
                + sized.getExactSizeIfKnown());

        // Không giả định trySplit luôn tạo ra hai nửa bằng nhau.
        long beforeSplit = sized.estimateSize();
        Spliterator.OfInt prefix = sized.trySplit();
        long remainingEstimate = sized.estimateSize();
        long prefixEstimate =
                prefix == null ? 0L : prefix.estimateSize();
        System.out.println("split sizes add up = "
                + (beforeSplit == remainingEstimate + prefixEstimate));

        // Với ORDERED, phần được trả về là prefix.
        List<Integer> rejoined = new ArrayList<>();
        if (prefix != null) {
            prefix.forEachRemaining((int n) -> rejoined.add(n));
        }
        sized.forEachRemaining((int n) -> rejoined.add(n));
        System.out.println("rejoined = " + rejoined);

        // Iterator hữu hạn, nhưng factory cố ý không biết size ban đầu.
        Spliterator<Integer> unknown =
                Spliterators.spliteratorUnknownSize(
                        Arrays.asList(10, 20, 30, 40, 50, 60)
                                .iterator(),
                        Spliterator.ORDERED);
        System.out.println("unknown sized flag = "
                + unknown.hasCharacteristics(Spliterator.SIZED));
        System.out.println("unknown exact = "
                + unknown.getExactSizeIfKnown());

        // Đếm thực sự bằng một stream terminal operation.
        long actualCount = StreamSupport.stream(unknown, false).count();
        System.out.println("unknown actual count = " + actualCount);

        // Nguồn rỗng có SIZED: biết chính xác 0.
        Spliterator.OfInt empty = Arrays.spliterator(new int[0]);
        System.out.println("empty exact = "
                + empty.getExactSizeIfKnown());

        // Spliterator từ mảng mới, dùng trong parallel pipeline.
        List<Integer> doubled =
                StreamSupport.intStream(Arrays.spliterator(values), true)
                        .map(n -> n * 2)
                        .boxed()
                        .collect(Collectors.toList());
        System.out.println("parallel doubled = " + doubled);
    }
}
~~~

Biên dịch bằng JDK 17+ với ngôn ngữ và API Java 8:

~~~bash
javac --release 8 SpliteratorSizeDemo.java
java SpliteratorSizeDemo
~~~

**Stdout kỳ vọng:**

~~~text
sized flag = true
subsized flag = true
estimate initially = 6
exact initially = 6
split sizes add up = true
rejoined = [10, 20, 30, 40, 50, 60]
unknown sized flag = false
unknown exact = -1
unknown actual count = 6
empty exact = 0
parallel doubled = [20, 40, 60, 80, 100, 120]
~~~

**Phân tích đầu ra:**

1. `Arrays.spliterator(int[])` tạo Spliterator của mảng với `SIZED` và `SUBSIZED`, vì vậy kích thước ban đầu là `6` và cả hai phương thức size trả `6`.
2. Khi `trySplit()` thành công, `SUBSIZED` bảo đảm kích thước hai phần cộng lại bằng kích thước trước đó. Nếu Spliterator không tách ở lần gọi ấy, `prefix` là `null` và toàn bộ phần chưa duyệt vẫn do `sized` giữ; phép kiểm tra vẫn đúng.
3. Mảng có encounter order. Phần tách mới (nếu có) là prefix, nên ghép duyệt prefix rồi phần còn lại sẽ tái tạo `[10, 20, 30, 40, 50, 60]`.
4. `Spliterators.spliteratorUnknownSize(iterator, ORDERED)` **không báo `SIZED` hoặc `SUBSIZED`**. Dữ liệu thật vẫn có sáu phần tử, nhưng `getExactSizeIfKnown()` trả `-1`.
5. `StreamSupport.stream(unknown, false).count()` là một terminal operation trên Spliterator chưa tiêu thụ và trả **số lượng thực tế là `6`**. Không cố tái sử dụng `unknown` để đếm một lần nữa.
6. Spliterator mới từ mảng rỗng được biết chính xác có `0` phần tử, khác hoàn toàn với `-1`.
7. `StreamSupport.intStream(..., true)` tạo parallel `IntStream` từ một Spliterator mới. Dù scheduler chia nguồn ra sao, `map` thuần và collector List trên ordered stream vẫn cho các giá trị theo encounter order.

Các dòng in ra đều **không phụ thuộc vào số thread, thời điểm thực thi hay kích thước từng nhánh sau split**.

## 6. Vì sao Spliterator không biết size vẫn xử lý được Stream?

Một nguồn không báo `SIZED` chỉ nói rằng **không có cam kết về số lượng còn lại**. Nó **không** ngăn:

- Gọi `tryAdvance` hoặc `forEachRemaining` để lấy dữ liệu.
- Gọi `trySplit` nếu implementation hỗ trợ; khả năng chia có thể hạn chế.
- Tạo Stream bằng `StreamSupport.stream(spliterator, false/true)`.
- Dùng các terminal operation như `count`, `collect`, `reduce` hay `forEach` theo hợp đồng của chúng.

Ví dụ, Iterator đọc tuần tự từ nguồn được cung cấp dần có thể không biết trước số dòng. Một Spliterator bao quanh Iterator vẫn có thể duyệt được dữ liệu cho đến khi hết.

### 6.1. Số lượng ước tính không phải giới hạn cứng

Nếu `estimateSize()` trên một Spliterator không `SIZED` trả `100`, không có nghĩa lời gọi `tryAdvance` thứ 101 bị cấm. Ước lượng chỉ phục vụ lập kế hoạch; số phần tử thật do phép duyệt và trạng thái nguồn quyết định.

Tương tự, nếu có `Long.MAX_VALUE` vì không biết trước số phần tử, không được tạo một mảng có dung lượng tương ứng; đó là **sentinel**, không phải chỉ thị cấp phát.

### 6.2. getExactSizeIfKnown không “đi đếm thay bạn”

Mã sau **sai về ý định** nếu nghiệp vụ thực sự cần biết số phần tử:

~~~java
long total = unknown.getExactSizeIfKnown();
// Với unknown không có SIZED, total == -1.
// Không thể coi -1 là tổng số bản ghi hoặc là lỗi dữ liệu.
~~~

Đây là đoạn minh họa; `unknown` là một Spliterator chưa duyệt được tạo từ nguồn không báo `SIZED`.

Nếu bắt buộc biết số phần tử thật của một nguồn hữu hạn, cần **duyệt dữ liệu** để đếm hoặc dùng nguồn cung cấp metadata chính xác:

~~~java
long total = StreamSupport.stream(unknown, false).count();
~~~

Phép đếm này **tiêu thụ Spliterator**. Với nguồn rất lớn hoặc nguồn vô hạn, việc đếm có thể tốn thời gian, tài nguyên hoặc không hoàn thành. Không dùng `count()` một cách tùy tiện chỉ để chuẩn bị dung lượng nếu chưa thực sự cần kết quả số lượng.

### 6.3. Trường hợp nguồn vô hạn

Một nguồn có thể sinh dữ liệu vô hạn, ví dụ `Stream.iterate(0, n -> n + 1)` trong Java 8. Không có số phần tử hữu hạn để báo. Đừng gọi terminal `count()` trên nguồn vô hạn không được giới hạn; phép tính không hoàn thành trong điều kiện bình thường.

Muốn làm việc với số phần tử hữu hạn, hãy giới hạn pipeline theo nghiệp vụ, ví dụ:

~~~java
long firstHundred = Stream.iterate(0, n -> n + 1)
        .limit(100)
        .count();
// 100
~~~

Đây là đoạn minh họa cần `import java.util.stream.Stream;`. `limit(100)` giúp **đầu ra pipeline** có hữu hạn 100 phần tử; điều đó **không** có nghĩa Spliterator nguồn gốc tự biến thành `SIZED` hoặc có thể suy ra chính xác tổng phần tử nguồn vô hạn.

## 7. Khác nhau giữa Collection.size(), Stream.count() và hai phương thức Spliterator

| API | Loại câu hỏi được trả lời | Có tiêu thụ pipeline không? | Điểm cần lưu ý |
| --- | --- | --- | --- |
| `Collection.size()` | Số phần tử hiện có của collection tại thời điểm gọi, theo hợp đồng collection | Không tạo/tiêu thụ Stream | Là metadata của collection; không tự mô tả phần đã lọc bằng Stream |
| `Spliterator.estimateSize()` | Ước lượng số phần tử **còn lại của Spliterator** | Không yêu cầu duyệt hết để đếm | Không mặc nhiên chính xác; `Long.MAX_VALUE` có thể là sentinel |
| `Spliterator.getExactSizeIfKnown()` | Kích thước theo `SIZED` nếu có, nếu không `-1` | Không yêu cầu duyệt hết để đếm | Chỉ kiểm tra characteristic, không biến nguồn không biết size thành đã biết |
| `Stream.count()` | Tổng số phần tử của **kết quả pipeline** khi terminal operation hoàn tất | **Có**, là terminal operation | Implementation có thể dùng metadata để tối ưu, không nhất thiết gọi mọi callback không ảnh hưởng kết quả |

Ví dụ:

~~~java
List<Integer> data = Arrays.asList(1, 2, 3, 4, 5, 6);

int sourceSize = data.size();                     // 6
long evenCount = data.stream()
        .filter(n -> n % 2 == 0)
        .count();                                 // 3
~~~

Đây là đoạn minh họa; `data.size()` đếm **collection gốc**, còn `Stream.count()` đếm **các phần tử sau filter**. `estimateSize()` của Spliterator gốc không thể được dùng trực tiếp để suy ra số phần tử còn lại sau một predicate tùy ý.

### 7.1. Pipeline có thể làm thay đổi việc biết trước kích thước

Một số thao tác giữ số phần tử (như `map` với hàm trả đúng một giá trị cho mỗi đầu vào); một số khác làm thay đổi số lượng (như `filter`, `flatMap`, `distinct`).

- `map` không làm thay đổi số phần tử theo ngữ nghĩa, nhưng cần xem Spliterator thực tế của pipeline báo những đặc tính nào.
- `filter` có thể loại bỏ bất kỳ số lượng phần tử nào; biết kích thước **nguồn trước filter** không đủ để biết kích thước kết quả.
- `flatMap` có thể tạo 0, 1 hoặc nhiều phần tử cho mỗi đầu vào.
- `distinct` có thể loại trùng, và độ giảm phụ thuộc dữ liệu.
- `limit`/`skip` giới hạn hoặc bỏ qua phần tử theo pipeline; đừng suy ra mọi Spliterator trung gian đều `SIZED` chỉ vì đã có chặn số phần tử.

Khi cần hỏi kích thước của một Spliterator cụ thể, hãy kiểm tra characteristic **trên chính Spliterator đó**, không giả định mọi thao tác trong pipeline đều giữ nguyên các cờ của Spliterator gốc.

### 7.2. Không xây logic bắt buộc dựa vào side effect của count()

Một số pipeline có đủ thông tin kích thước chính xác để `count()` cho đáp án mà không cần duyệt và gọi toàn bộ `peek`/`map` không ảnh hưởng kết quả. Vì vậy:

~~~java
// Không thiết kế nghiệp vụ bắt buộc dựa vào println trong peek:
long total = data.stream()
        .peek(System.out::println)
        .count();
~~~

Đây là đoạn minh họa. Kết quả `total` phải đúng theo hợp đồng, nhưng không dùng số lần in để suy ra cách `count` đã tính hoặc thời điểm các stage thực thi.

## 8. Các điều kiện giới hạn độ tin cậy của estimateSize()

### 8.1. Đã duyệt hoặc đã tách một phần

`estimateSize()` mô tả phần còn lại, nhưng hợp đồng độ chính xác có điều kiện:

- Có `SIZED` và chưa duyệt/tách: kích thước hữu hạn ban đầu chính xác khi không có can thiệp vào cấu trúc nguồn.
- Có `SUBSIZED` và chưa duyệt một phần: thông tin size vẫn có bảo đảm cần thiết sau khi chia nguồn.
- Chỉ có `SIZED` nhưng đã tách hoặc duyệt: cần đọc hợp đồng chi tiết của implementation; không suy ra luôn chính xác.
- Không có `SIZED`: chỉ là ước lượng; có thể tình cờ đúng nhưng không được phụ thuộc.

Vì vậy, **đừng dựa vào việc gọi `getExactSizeIfKnown()` nhiều lần sau các hành động khác nhau mà không xét trạng thái và characteristic**.

### 8.2. Nguồn bị thay đổi

Nếu một thread thay đổi cấu trúc `ArrayList` khi Spliterator đang duyệt mà không có cơ chế hỗ trợ tương ứng, mã có thể gặp lỗi hoặc kết quả không được bảo đảm. `estimateSize()` không phải phép khóa snapshot và `SIZED` cũng không tạo tính bất biến cho nguồn.

Với nguồn concurrent có chính sách nhất quán riêng, kích thước có thể thay đổi theo thời gian. Javadoc lưu ý Spliterator ở **cấp nguồn cao nhất** không nên vừa báo `CONCURRENT` vừa báo `SIZED` vì kích thước hữu hạn có thể thay đổi khi duyệt.

Khi cần kết quả chính xác theo một thời điểm, hãy chọn snapshot/đồng bộ hoặc thiết kế dữ liệu có hợp đồng nhất quán rõ ràng. Không dùng size metadata làm cơ chế đồng bộ.

### 8.3. Spliterator do người dùng tự cài đặt

Nếu tự viết Spliterator, người triển khai phải:

1. Cho `estimateSize()` giá trị phù hợp với số phần tử còn lại, hoặc `Long.MAX_VALUE` khi không biết/vô hạn/quá đắt.
2. Chỉ khai báo `SIZED` nếu có thể đáp ứng hợp đồng kích thước hữu hạn chính xác theo điều kiện Javadoc.
3. Chỉ khai báo `SUBSIZED` nếu **mọi Spliterator con** đều giữ `SIZED` và `SUBSIZED`, và việc chia đáp ứng phương trình tổng size.
4. Đảm bảo `trySplit()` không tạo phần tử trùng hoặc bỏ phần tử; với `ORDERED`, phần được trả về phải là prefix.
5. Giữ các characteristic nhất quán theo hợp đồng; không tự gắn cờ chỉ để hy vọng tăng hiệu năng.
6. Không coi Spliterator là object an toàn để nhiều thread cùng gọi `tryAdvance`/`trySplit` trên một instance.

Sai kích thước hoặc cờ `SIZED`/`SUBSIZED` có thể làm framework áp dụng tối ưu hóa dựa trên tiền đề sai. Hệ quả có thể là kết quả sai hoặc những lỗi khó tái hiện, đặc biệt khi dùng parallel stream.

## 9. Sai lầm thường gặp và cách sửa

### Lỗi 1 — Coi estimateSize là size tuyệt đối

**Sai:** “`estimateSize() == 500`, vậy luôn có đúng 500 phần tử.”  
**Đúng:** Chỉ xem là chính xác khi có `SIZED` và đáp ứng điều kiện hợp đồng. Với Spliterator không `SIZED`, số 500 vẫn chỉ là dự đoán.

### Lỗi 2 — Coi -1 là rỗng

**Sai:** Nếu `getExactSizeIfKnown() == -1` thì bỏ qua xử lý vì “không có dữ liệu”.  
**Đúng:** `-1` là sentinel **không biết kích thước**. Vẫn có thể duyệt bình thường để xử lý dữ liệu.

### Lỗi 3 — Coi Long.MAX_VALUE là tổng số phần tử thật

**Sai:** Tạo mảng có kích thước bằng `estimateSize()` dù nó bằng `Long.MAX_VALUE`.  
**Đúng:** Cần phân biệt sentinel với số lượng chính xác; thiết kế cấp phát tăng dần hoặc xử lý từng phần nếu không biết size.

### Lỗi 4 — Nghĩ SIZED luôn suy ra SUBSIZED

**Sai:** Cha báo `SIZED` nên mọi con của `trySplit` chắc chắn có size chính xác.  
**Đúng:** Điều này chỉ được hứa khi có thêm `SUBSIZED`; chỉ `SIZED` không đủ.

### Lỗi 5 — Nghĩ SUBSIZED yêu cầu chia đôi

**Sai:** Nếu ban đầu có 10 phần tử thì con phải có 5 và cha còn 5.  
**Đúng:** `SUBSIZED` cam kết tổng kích thước, không cam kết độ cân bằng; `trySplit` còn được phép trả `null`.

### Lỗi 6 — Hỏi size nguồn để suy ra số phần tử sau filter

**Sai:** Từ `source.spliterator().getExactSizeIfKnown() == 100` suy ra `stream.filter(p).count() == 100`.  
**Đúng:** `filter` có thể loại bất kỳ số lượng phần tử nào, phải xét kết quả pipeline.

### Lỗi 7 — Tái sử dụng Spliterator đã được Stream tiêu thụ

**Sai:** Tạo Stream từ một Spliterator, chạy terminal rồi dùng tiếp chính Spliterator đó như thể nguồn chưa bị động đến.  
**Đúng:** Mỗi phép tính cần Spliterator/Stream mới từ nguồn còn hợp lệ.

### Lỗi 8 — Dùng giá trị getExactSizeIfKnown để ép kiểu int không kiểm tra

**Sai:** `new Object[(int) exact]` khi `exact == -1` hoặc lớn hơn `Integer.MAX_VALUE`.  
**Đúng:** Chỉ dùng làm dung lượng khi chắc chắn số không âm, nằm trong giới hạn kiểu/memory và đáp ứng hợp đồng; nếu không thì cấp phát theo tăng trưởng hoặc chọn chiến lược khác.

### Lỗi 9 — Cho rằng size metadata chứng minh chạy song song sẽ nhanh

**Sai:** Một nguồn có `SIZED`/`SUBSIZED` chắc chắn tăng tốc.  
**Đúng:** Size giúp chia việc/dự trù, còn hiệu năng phụ thuộc chi phí xử lý từng phần tử, chiến lược split, kết hợp kết quả, overhead và tài nguyên máy.

### Lỗi 10 — Chia hay duyệt cùng một Spliterator đồng thời

**Sai:** Hai worker cùng thao tác trực tiếp trên một instance Spliterator không có bảo đảm.  
**Đúng:** Tách rồi giao mỗi instance riêng cho một tác vụ; không coi hai phương thức size là phép đồng bộ.

## 10. Cách dùng đúng trong bài toán thực tế

### 10.1. Chỉ cần ước lượng để quyết định chia tiếp

Một thuật toán song song có thể dùng `estimateSize()` để quyết định “phần này có đủ lớn để chia không?”. Với nguồn không `SIZED`, giá trị chỉ mang tính heuristic. Không dùng nó để quyết định phần tử nào được phép bỏ qua.

~~~java
// Minh họa ý tưởng; không phải đầy đủ thuật toán fork/join.
if (spliterator.estimateSize() > threshold) {
    Spliterator<T> prefix = spliterator.trySplit();
    if (prefix != null) {
        // Có thể xử lý prefix ở một tác vụ và phần còn lại ở tác vụ khác.
    }
}
~~~

Ở đây `spliterator` là một Spliterator chưa duyệt, `threshold` là ngưỡng phù hợp, và `T` là type parameter sẵn có. Đoạn này chỉ mô tả **ý tưởng chia việc**, không tự quản lý thread hay xử lý kết quả.

### 10.2. Cần tạo cấu trúc lưu trữ biết trước dung lượng

Có thể tham khảo `getExactSizeIfKnown()` để dự trù capacity **khi** biết chính xác kích thước, phù hợp giới hạn bộ nhớ và không bị nguồn thay đổi trái hợp đồng. Nếu nhận `-1` thì không được coi là exception hoặc là size hợp lệ; tiếp tục bằng container tăng trưởng hoặc thuật toán không cần preallocate.

Lưu ý: kể cả size chính xác, **số lượng phần tử** không phải **dung lượng bộ nhớ tính bằng byte**. Mỗi object, entry hoặc collection có overhead riêng; việc cấp phát toàn bộ theo một size cực lớn có thể làm cạn heap.

### 10.3. Cần đếm dữ liệu sau một phép biến đổi

Nếu mục tiêu là “còn bao nhiêu người đạt chuẩn sau filter?”, hãy sử dụng `filter(...).count()` và để Stream thực hiện terminal operation theo hợp đồng. Không suy ra từ `estimateSize()` của nguồn.

### 10.4. Nguồn không biết trước kích thước

Dùng `Spliterators.spliteratorUnknownSize` khi xuất phát từ Iterator không có metadata đáng tin. Không khai báo `SIZED`/`SUBSIZED` giả chỉ để truyền một con số ước lượng; factory này chủ động bỏ hai characteristic ấy vì kích thước không được bảo đảm.

## 11. Bài tập tự kiểm tra

**Câu 1.** Một Spliterator không có `SIZED`, `estimateSize()` trả `12` và thực tế có đúng 12 phần tử. `getExactSizeIfKnown()` trả gì?

**Đáp án:** `-1L`. Dù ước lượng tình cờ đúng, phương thức mặc định vẫn kiểm tra characteristic `SIZED`.

**Câu 2.** Nguồn hữu hạn nhưng chưa biết có bao nhiêu phần tử, `estimateSize()` có thể trả `Long.MAX_VALUE` không? Điều đó có chứng minh nguồn vô hạn?

**Đáp án:** Có thể trả `Long.MAX_VALUE`; không chứng minh vô hạn, vì đây còn là sentinel cho **không biết hoặc quá tốn công để tính**.

**Câu 3.** Với Spliterator mới từ mảng sáu phần tử, có `SIZED` và `SUBSIZED`, `getExactSizeIfKnown()` trả gì?

**Đáp án:** `6L` trước khi duyệt/tách. Với mảng rỗng, kết quả là `0L` chứ không phải `-1L`.

**Câu 4.** Sau một lần `trySplit` thành công trên Spliterator `SUBSIZED`, kích thước hai phần bắt buộc bằng nhau không? Tổng hai kích thước bằng gì?

**Đáp án:** Không bắt buộc bằng nhau. Tổng hai giá trị `estimateSize()` sau split phải bằng `estimateSize()` trước split, theo hợp đồng `SUBSIZED`.

**Câu 5.** Một Spliterator báo `SIZED` nhưng không báo `SUBSIZED`. Mọi Spliterator con chắc chắn `SIZED` không?

**Đáp án:** Không. `SIZED` chỉ mô tả Spliterator hiện tại ở điều kiện được bảo đảm. Muốn mọi con có `SIZED` và `SUBSIZED` cần `SUBSIZED` ở cha.

**Câu 6.** Nếu `getExactSizeIfKnown() == -1`, có thể gọi `StreamSupport.stream(spliterator, false).count()` để đếm chính xác một nguồn hữu hạn không?

**Đáp án:** Có, nếu nguồn hữu hạn và có thể duyệt hợp lệ. Đây là terminal operation tiêu thụ Spliterator; chi phí có thể lớn, nên chỉ đếm khi thực sự cần.

**Câu 7.** Tại sao không được lấy size nguồn để kết luận số lượng phần tử sau `filter`?

**Đáp án:** Vì `filter` có thể loại bỏ phần tử. Size trước filter không đủ để biết số phần tử thỏa predicate.

**Câu 8.** Spliterator `SUBSIZED` có bắt buộc `trySplit()` luôn thành công trên tập dữ liệu lớn không?

**Đáp án:** Không. `SUBSIZED` cam kết kích thước của các phần **nếu** split thành công; không cam kết khả năng tách tại mọi thời điểm.

**Câu 9.** `getExactSizeIfKnown()` có an toàn làm số phần tử để cấp phát mảng `new Object[(int) size]` trong mọi trường hợp không?

**Đáp án:** Không. Giá trị có thể là `-1`, có thể vượt khả năng biểu diễn kiểu `int` hoặc vượt giới hạn bộ nhớ; chỉ dùng khi đáp ứng tất cả điều kiện.

## 12. Ghi nhớ

- `estimateSize()` **ước lượng số phần tử còn lại**, có thể trả `Long.MAX_VALUE` cho nguồn vô hạn, không biết hoặc quá đắt để tính.
- `getExactSizeIfKnown()` mặc định trả `estimateSize()` nếu có `SIZED`, nếu không **`-1L`**. Nó không tự duyệt để đếm.
- `SIZED` đảm bảo kích thước hữu hạn ban đầu chính xác trong các điều kiện của Javadoc; **không mặc nhiên đảm bảo** mọi Spliterator con đều chính xác.
- `SUBSIZED` bảo đảm mọi con sau `trySplit` cũng `SIZED + SUBSIZED` và tổng size hai phần sau split bằng size trước đó.
- `trySplit()` không phải phép luôn chia đôi; `null` là kết quả hợp lệ.
- Nguồn **không `SIZED` vẫn có thể duyệt và đếm bình thường**. Không được dùng `-1` như trạng thái “không có dữ liệu”.
- Thông tin size hỗ trợ lập kế hoạch xử lý song song, nhưng **không bảo đảm hiệu năng** và không bảo vệ việc thay đổi nguồn không an toàn.
- Các hợp đồng này có từ **Java 8**, vẫn là kiến thức quan trọng trong Java hiện hành.

### Tài liệu tham khảo chính thức

- [Oracle Java SE 8 — Spliterator](https://docs.oracle.com/javase/8/docs/api/java/util/Spliterator.html)
- [Oracle Java SE 25 — Spliterator: estimateSize, getExactSizeIfKnown, SIZED và SUBSIZED](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Spliterator.html)
- [Oracle Java SE 25 — Spliterators: spliteratorUnknownSize](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Spliterators.html)
- [Oracle Java SE 25 — Stream: count, filter và các hợp đồng pipeline](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Stream.html)
- [Oracle Java SE 25 — StreamSupport](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/StreamSupport.html)
