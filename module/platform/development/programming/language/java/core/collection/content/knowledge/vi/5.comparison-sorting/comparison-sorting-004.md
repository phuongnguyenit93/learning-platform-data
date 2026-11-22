# thenComparing và sắp xếp nhiều tiêu chí

Một tiêu chí thường chưa đủ để trình bày dữ liệu theo ý nghĩa nghiệp vụ. Trong danh sách công việc, ta có thể muốn:

1. Độ ưu tiên cao hơn đứng trước.
2. Nếu cùng độ ưu tiên, hạn xử lý sớm hơn đứng trước.
3. Nếu vẫn hòa nhau, mã công việc tăng dần để kết quả có quy tắc rõ ràng.

`Comparator.thenComparing(...)` kết hợp các tiêu chí theo đúng thứ bậc đó. Tiêu chí sau chỉ giải quyết những cặp phần tử mà toàn bộ các tiêu chí trước chưa phân biệt được.

Bài sử dụng `Ticket` làm ví dụ. Số `priority` lớn hơn có nghĩa là ưu tiên cao hơn; `due == null` có nghĩa chưa có hạn xử lý. Đây là các quy ước nghiệp vụ được chọn cho ví dụ, không phải ý nghĩa Java tự áp đặt lên tên trường.

## 1. Vì sao cần tiêu chí phụ?

Dữ liệu mẫu:

| Mã | Độ ưu tiên | Hạn xử lý |
| --- | --- | --- |
| T4 | 2 | 2026-05-10 |
| T2 | 3 | 2026-05-08 |
| T6 | 3 | Chưa có |
| T1 | 3 | 2026-05-08 |
| T3 | 2 | 2026-05-06 |
| T5 | 3 | 2026-05-12 |

Chỉ sắp theo ưu tiên giảm dần có thể đưa toàn bộ nhóm ưu tiên `3` lên trước nhóm ưu tiên `2`. Nhưng nó chưa nói T1 và T5 trong cùng nhóm phải đứng như thế nào.

Thêm hạn xử lý sẽ sắp xếp từng nhóm ưu tiên theo hạn. Thêm mã sẽ tiếp tục phân biệt T1 và T2, vì hai công việc này có cùng ưu tiên và cùng hạn.

Kết quả theo đủ ba tiêu chí là:

~~~text
T1, T2, T5, T6, T3, T4
~~~

T3 có hạn sớm hơn T1 nhưng vẫn nằm sau nhóm ưu tiên `3`, vì **ưu tiên là tiêu chí chính**. Hạn xử lý không được phép đảo một kết quả đã được quyết định bởi độ ưu tiên.

Đây là khác biệt giữa thứ bậc tiêu chí và một cách chấm điểm tổng hợp. `thenComparing` không tính trung bình, không cân trọng số và không cho tiêu chí phụ “bù” cho tiêu chí chính.

## 2. Cơ chế: dùng kết quả khác 0 đầu tiên

Giả sử:

~~~java
Comparator<Ticket> order =
        primary.thenComparing(secondary).thenComparing(tertiary);
~~~

Khi so sánh hai công việc `left` và `right`, có thể hình dung:

~~~java
// Mã minh họa cơ chế; các comparator thành phần đã được khai báo.
int result = primary.compare(left, right);
if (result != 0) {
    return result;
}

result = secondary.compare(left, right);
if (result != 0) {
    return result;
}

return tertiary.compare(left, right);
~~~

Đoạn mã có `return` này là phần thân minh họa của một phép so sánh, không phải chương trình độc lập cần sao chép vào `main`.

Kết quả âm nghĩa là `left` đứng trước, dương nghĩa là `left` đứng sau, bằng `0` nghĩa là comparator chưa phân biệt được hai phần tử.

“Bằng nhau” ở bước quyết định có dùng tiêu chí tiếp theo hay không là **`compare(left, right) == 0`**, không phải `left.equals(right)`.

Ví dụ, T1 và T2 là hai công việc khác nhau nhưng comparator chỉ xét ưu tiên sẽ trả `0`. Vì vậy comparator hạn được xét tiếp, rồi comparator mã được xét khi hạn cũng bằng nhau.

Java gọi cách kết hợp này là thứ tự từ điển theo các comparator. Mô tả API và các overload có trong [Java SE 17 Comparator API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Comparator.html).

### Không cộng các kết quả so sánh

Cách kết hợp sau không biểu đạt đúng thứ bậc:

~~~java
// Ví dụ sai về ý tưởng, không nên dùng.
int result = primary.compare(left, right)
        + secondary.compare(left, right);
~~~

Một kết quả dương của tiêu chí này có thể bị kết quả âm của tiêu chí khác triệt tiêu. Hơn nữa, comparator chỉ quy định ý nghĩa của dấu; độ lớn kết quả không phải trọng số nghiệp vụ.

Cũng không viết phép trừ giữa hai khóa số rồi coi đó luôn là comparator đúng. Tràn số có thể làm đổi dấu. Các factory như `comparingInt` hoặc hàm `Integer.compare` phù hợp hơn cho khóa `int`.

## 3. Tạo comparator nhiều tiêu chí

Với kiểu dữ liệu:

~~~java
// Khai báo kiểu minh họa; cần import java.time.LocalDate.
record Ticket(String id, int priority, LocalDate due) {}
~~~

Ta tạo comparator cho ngày có thể thiếu:

~~~java
Comparator<LocalDate> dateOrder =
        Comparator.nullsLast(Comparator.naturalOrder());
~~~

Sau đó ghép quy tắc:

~~~java
Comparator<Ticket> order =
        Comparator.comparingInt(Ticket::priority)
                .reversed()
                .thenComparing(Ticket::due, dateOrder)
                .thenComparing(Ticket::id);
~~~

Đọc theo thứ tự:

- `comparingInt(Ticket::priority).reversed()`: ưu tiên giảm dần.
- `thenComparing(Ticket::due, dateOrder)`: trong cùng mức ưu tiên, ngày tăng dần; ngày thiếu đứng cuối trong nhóm.
- `thenComparing(Ticket::id)`: nếu hai tiêu chí trên đều hòa, mã theo thứ tự tự nhiên của `String`.

Mã tăng dần trong bài được hiểu theo so sánh chuỗi. Với những mã như `T2` và `T10`, thứ tự chuỗi không đồng nghĩa thứ tự của phần số bên trong. Nếu nghiệp vụ cần thứ tự số của mã, phải thiết kế khóa so sánh tương ứng.

### Một comparator là dữ liệu mô tả quy tắc

Tạo `order` chưa sắp xếp dữ liệu. Cần truyền nó vào thao tác sử dụng:

~~~java
// tickets là nguồn đã có; ArrayList tạo một danh sách có thể sửa.
List<Ticket> sorted = new ArrayList<>(tickets);
sorted.sort(order);
~~~

`sort` thay thứ tự trong danh sách nhận lời gọi. Comparator không tự quyết định phải sửa nguồn hay tạo bản sao; đó là lựa chọn của đoạn mã sử dụng nó.

Nếu gọi `sort` trực tiếp trên danh sách không hỗ trợ sửa đổi như kết quả `List.of(...)`, thao tác có thể thất bại bằng `UnsupportedOperationException`. Dùng một bản sao có thể sửa khi mục đích là giữ nguyên nguồn hoặc nguồn không cho đổi thứ tự.

## 4. Ba dạng thenComparing cần phân biệt

| Dạng | Đầu vào | Khi nào dùng |
| --- | --- | --- |
| `thenComparing(other)` | Comparator cho cùng loại phần tử | Đã có một quy tắc so sánh hoàn chỉnh muốn tái sử dụng làm tiêu chí tiếp theo. |
| `thenComparing(keyExtractor)` | Hàm lấy khóa có thứ tự tự nhiên | Khóa như `String` hoặc `LocalDate` không cần quy tắc riêng. |
| `thenComparing(keyExtractor, keyComparator)` | Hàm lấy khóa và comparator cho khóa | Muốn kiểm soát `null`, chiều so sánh hoặc quy tắc riêng của khóa. |

### Ghép comparator đã có

~~~java
Comparator<Ticket> byPriority =
        Comparator.comparingInt(Ticket::priority).reversed();

Comparator<Ticket> byDue =
        Comparator.comparing(Ticket::due, dateOrder);

Comparator<Ticket> order =
        byPriority.thenComparing(byDue).thenComparing(Ticket::id);
~~~

`byDue` so sánh hai `Ticket`. Vì vậy nó phù hợp với overload nhận một comparator cho phần tử.

### Ghép hàm lấy khóa

~~~java
Comparator<Ticket> order =
        byPriority.thenComparing(Ticket::id);
~~~

`Ticket::id` không phải comparator: nó nhận một công việc và trả một khóa `String`. Overload này lấy hai khóa rồi dùng thứ tự tự nhiên của chúng.

### Ghép khóa cùng quy tắc riêng

~~~java
Comparator<Ticket> order =
        byPriority.thenComparing(
                Ticket::id,
                String.CASE_INSENSITIVE_ORDER
        );
~~~

Trong ví dụ này, tham số thứ hai là comparator của `String`, không phải comparator của `Ticket`.

Đừng nhầm hai tầng:

~~~text
Comparator<Ticket>
    so sánh Ticket với Ticket

Comparator<String>
    so sánh hai khóa id đã lấy từ Ticket
~~~

Nếu kiểu khóa không triển khai `Comparable`, overload nhận riêng hàm lấy khóa không đủ để chọn thứ tự tự nhiên. Khi đó phải truyền một comparator cho khóa hoặc ánh xạ đến khóa có quy tắc rõ ràng.

## 5. Các biến thể cho khóa nguyên thủy

Với khóa số, có các phương thức:

- `thenComparingInt(...)`: hàm lấy khóa trả `int`.
- `thenComparingLong(...)`: hàm lấy khóa trả `long`.
- `thenComparingDouble(...)`: hàm lấy khóa trả `double`.

Ví dụ bổ sung cho một kiểu dữ liệu khác:

~~~java
// Minh họa các khai báo trong một lớp; cần import java.util.Comparator.
record Shipment(
        String destination,
        int priority,
        long weightInGrams,
        double distance
) {}

Comparator<Shipment> order =
        Comparator.comparing(Shipment::destination)
                .thenComparingInt(Shipment::priority)
                .thenComparingLong(Shipment::weightInGrams)
                .thenComparingDouble(Shipment::distance);
~~~

Thứ bậc là nơi đến, rồi ưu tiên, rồi khối lượng, rồi khoảng cách. Tất cả ví dụ trên dùng chiều tăng theo mỗi khóa.

Các biến thể nguyên thủy làm rõ kiểu khóa và tránh yêu cầu boxing khóa thành `Integer`, `Long` hoặc `Double` trên đường so sánh tương ứng. Không ép giá trị `long` về `int` chỉ để dùng `thenComparingInt`: có thể mất thông tin và đổi kết quả.

Chọn kiểu dữ liệu và định nghĩa thứ tự trước. Nếu `distance` cho phép `NaN`, vô cực hoặc giá trị không hợp lệ với nghiệp vụ, phải xác định chính sách dữ liệu đó; việc API chấp nhận `double` không tự giải quyết ý nghĩa nghiệp vụ.

## 6. Điều khiển tăng và giảm cho từng tiêu chí

### Chỉ đảo tiêu chí chính

~~~java
Comparator<Ticket> order =
        Comparator.comparingInt(Ticket::priority)
                .reversed()
                .thenComparing(Ticket::due, dateOrder)
                .thenComparing(Ticket::id);
~~~

`reversed()` xuất hiện ngay sau comparator ưu tiên, trước khi ghép ngày và mã. Vì vậy nó chỉ đảo chiều ưu tiên.

### Đảo toàn bộ chuỗi

~~~java
Comparator<Ticket> different =
        Comparator.comparingInt(Ticket::priority)
                .thenComparing(Ticket::due, dateOrder)
                .thenComparing(Ticket::id)
                .reversed();
~~~

Ở thời điểm gọi `reversed()`, chuỗi đã gồm cả ba tiêu chí. Kết quả đảo cả ưu tiên, hạn và mã. Quan hệ “ngày thiếu đứng cuối” cũng bị đảo thành “ngày thiếu đứng đầu” trong nhóm tương ứng.

Không thể di chuyển `reversed()` từ giữa xuống cuối mà mặc nhiên giữ cùng ý nghĩa.

### Giảm dần một tiêu chí phụ

Giả sử cùng ưu tiên thì ngày muộn hơn đứng trước, nhưng ngày thiếu vẫn đứng cuối:

~~~java
Comparator<LocalDate> dueDescendingNullLast =
        Comparator.nullsLast(Comparator.reverseOrder());

Comparator<Ticket> order =
        Comparator.comparingInt(Ticket::priority)
                .reversed()
                .thenComparing(Ticket::due, dueDescendingNullLast)
                .thenComparing(Ticket::id);
~~~

Một cách khác khi muốn đảo một comparator phần tử đã có là truyền nó vào overload nhận comparator:

~~~java
// Ví dụ chỉ về phạm vi đảo: đảo toàn bộ quy tắc byDue sẵn có.
Comparator<Ticket> byPriorityThenReversedDue =
        byPriority.thenComparing(byDue.reversed());
~~~

Nếu `byDue` đã bọc `nullsLast` cho ngày, `byDue.reversed()` sẽ đảo cả vị trí `null`. Muốn `null` luôn ở cuối, nên tạo quy tắc khóa như `dueDescendingNullLast` ở ví dụ trước.

## 7. Null: chính sách ở từng tiêu chí và ở toàn phần tử

Nếu chỉ có ngày thiếu, xử lý ở comparator khóa ngày:

~~~java
Comparator<LocalDate> dateOrder =
        Comparator.nullsLast(Comparator.naturalOrder());

Comparator<Ticket> order =
        Comparator.comparingInt(Ticket::priority)
                .reversed()
                .thenComparing(Ticket::due, dateOrder)
                .thenComparing(Ticket::id);
~~~

Nếu danh sách còn có cả phần tử `Ticket == null`, bọc comparator hoàn chỉnh ở ngoài:

~~~java
Comparator<Ticket> nullTicketsLast =
        Comparator.nullsLast(order);
~~~

Hai lớp này giải quyết hai tình huống:

- Comparator ngoài kiểm tra chính phần tử `Ticket`.
- Comparator ngày xử lý giá trị `due` của một `Ticket` tồn tại.

Nếu `id` cũng có thể `null`, phải bổ sung quy tắc ở tiêu chí mã. Xử lý `null` cho `due` không tự xử lý `null` cho tất cả khóa khác.

### Không có ngoại lệ ở một bộ dữ liệu chưa chứng minh comparator an toàn

Vì tiêu chí phụ chỉ được dùng khi các tiêu chí trước hòa nhau, một khóa `null` có thể chưa được đọc trong một lần so sánh nào đó.

Ví dụ, hai công việc khác ưu tiên có thể được phân biệt ngay; comparator ngày chưa cần chạy. Nhưng chỉ cần thêm dữ liệu cùng ưu tiên, việc so ngày có thể phát sinh và làm lộ lỗi `null` chưa được xử lý.

Đừng dựa vào thứ tự so sánh tình cờ của thuật toán sort để che một dữ liệu không hợp lệ. Xác định rõ khóa nào được phép thiếu, ở mức nào và phải đứng đâu.

## 8. thenComparing trả comparator mới

Lời gọi không cập nhật biến comparator đã có:

~~~java
Comparator<Ticket> order =
        Comparator.comparingInt(Ticket::priority).reversed();

order.thenComparing(Ticket::id); // Bỏ qua comparator mới được trả về.
~~~

Sau đoạn mã này, biến `order` vẫn chỉ chứa quy tắc ưu tiên. Muốn dùng quy tắc đã ghép:

~~~java
order = order.thenComparing(Ticket::id);
~~~

Hoặc tạo thành một biểu thức hoàn chỉnh ngay từ đầu:

~~~java
Comparator<Ticket> order =
        Comparator.comparingInt(Ticket::priority)
                .reversed()
                .thenComparing(Ticket::id);
~~~

Điều này thuận tiện cho việc tái sử dụng các phần:

~~~java
Comparator<Ticket> base =
        Comparator.comparingInt(Ticket::priority).reversed();

Comparator<Ticket> forDashboard =
        base.thenComparing(Ticket::due, dateOrder)
                .thenComparing(Ticket::id);

Comparator<Ticket> forCodeLookup =
        base.thenComparing(Ticket::id);
~~~

Việc tạo một chuỗi mới không làm `base` tự xuất hiện các tiêu chí phụ. Tuy nhiên, các comparator vẫn có thể cùng tham chiếu các đối tượng bên ngoài do lambda bắt giữ; không nên hiểu điều này là mọi dữ liệu mà chúng đọc đều bất biến.

## 9. Chaining và sắp xếp nhiều lượt

Cách tự nhiên nhất để biểu đạt yêu cầu ưu tiên → hạn → mã là tạo một comparator rồi gọi sort một lần:

~~~java
sorted.sort(order);
~~~

Một nhầm lẫn phổ biến:

~~~java
sorted.sort(byPriority);
sorted.sort(byDueThenId);
~~~

Lần sort thứ hai sắp lại **toàn bộ danh sách** theo hạn và mã. Nó không tự hiểu “chỉ sắp các nhóm bằng nhau của lần đầu”.

Với dữ liệu bài này, T3 có ưu tiên `2` nhưng hạn sớm nhất, nên sẽ bị đưa lên đầu nếu sort toàn bộ theo hạn ở bước cuối. Kết quả trái với yêu cầu ưu tiên là tiêu chí chính.

### Sắp nhiều lượt có thể làm được khi hiểu tính ổn định

`List.sort` là sắp xếp ổn định: các phần tử được comparator xem là bằng nhau giữ thứ tự tương đối trước lần sort đó.

Nếu thật sự cần sắp nhiều lượt, có thể sort tiêu chí phụ trước rồi sort ổn định theo tiêu chí chính:

~~~java
sorted.sort(byDueThenId);
sorted.sort(byPriority);
~~~

Lần sort cuối tạo các nhóm ưu tiên. Trong từng nhóm, nó giữ thứ tự hạn và mã đã được tạo ở lần trước.

Đây là một kỹ thuật có điều kiện, không phải quy tắc dùng được với mọi thuật toán sort:

- Các lượt phải áp dụng từ tiêu chí ít quan trọng hơn đến tiêu chí quan trọng hơn.
- Phép sort phù hợp phải giữ ổn định để bảo toàn kết quả phụ trong nhóm hòa nhau.
- Dữ liệu và quy tắc so sánh phải không thay đổi giữa chừng.

Một chuỗi `thenComparing` thường dễ đọc và ít nhầm thứ bậc hơn, đồng thời không yêu cầu người đọc suy luận ngược qua nhiều lần thay đổi danh sách.

## 10. Sắp xếp ổn định khác với thứ tự được xác định đầy đủ

Chỉ sắp theo ưu tiên và hạn:

~~~java
Comparator<Ticket> priorityThenDue =
        byPriority.thenComparing(Ticket::due, dateOrder);
~~~

T1 và T2 vẫn hòa nhau. Nếu đầu vào đặt T2 trước T1, một lần `List.sort` ổn định giữ T2 trước T1. Nếu nguồn đầu vào đảo hai bản ghi, kết quả trong nhóm hòa có thể đảo theo.

Tính ổn định không tự tạo một tiêu chí còn thiếu. Nếu muốn kết quả được xác định theo dữ liệu thay vì phụ thuộc thứ tự đầu vào, cần chọn một quy tắc giải quyết hòa phù hợp, như mã duy nhất trong ví dụ:

~~~java
Comparator<Ticket> fullOrder =
        priorityThenDue.thenComparing(Ticket::id);
~~~

Điều này có giá trị với:

- Kiểm thử cần kết quả có thể tái lập.
- Xuất báo cáo cùng một tập dữ liệu.
- Phân trang cần thứ tự rõ ràng giữa các bản ghi ngang nhau theo tiêu chí chính.

Tuy nhiên, thêm mã cuối chuỗi không tự giải quyết mọi vấn đề phân trang. Dữ liệu có thể thay đổi giữa các yêu cầu, và mã có thể chỉ duy nhất trong một phạm vi. Hệ thống cần xác định cả phạm vi duy nhất, tính nhất quán dữ liệu và cách tạo con trỏ hoặc snapshot.

Đừng thêm `identityHashCode`, số ngẫu nhiên hoặc thời gian hiện tại chỉ để tránh `compare == 0`. Các giá trị đó không biểu đạt một thứ tự nghiệp vụ bền vững.

## 11. Dữ liệu bằng nhau theo comparator và TreeSet

Nếu comparator chỉ xét ưu tiên, T1 và T2 có thể cho kết quả `0` dù là hai công việc khác nhau.

- Với danh sách, sort không tự xóa phần tử vì hòa nhau.
- Với `TreeSet`, quan hệ so sánh còn quyết định việc xem hai phần tử thuộc cùng một vị trí trong tập hợp.
- Với `TreeMap`, comparator tham gia quyết định hai khóa có tương đương hay không.

Vì vậy, comparator thiết kế cho màn hình “nhóm theo độ ưu tiên” chưa chắc phù hợp làm comparator cho tập hợp chứa tất cả công việc.

Thêm mã có thể giúp phân biệt các công việc nếu mã thực sự là định danh duy nhất của chúng. Nhưng yêu cầu “nhất quán với `equals`” cần được kiểm tra theo định nghĩa `equals` thực tế.

Trong record `Ticket(id, priority, due)` của bài, `equals` xét cả ba thành phần. Chuỗi comparator đầy đủ cũng xét ba thành phần theo các quy tắc tương ứng. Nếu thay định nghĩa dữ liệu, cho phép mã trùng hoặc thêm quy tắc bỏ qua chữ hoa–thường, phải xem lại quan hệ tương đương thay vì chỉ giữ chuỗi comparator cũ.

## 12. Chi phí và tính nhất quán của các tiêu chí

Tiêu chí sau chỉ được gọi khi chuỗi trước trả `0`. Đây là một đặc điểm có thể giảm số lần tính khóa phụ.

Nhưng không nên đổi thứ tự các tiêu chí chỉ để giảm chi phí nếu việc đó làm sai yêu cầu nghiệp vụ. Chuyển mã duy nhất lên đầu sẽ khiến các tiêu chí ưu tiên và hạn gần như không còn được dùng để quyết định thứ tự giữa các bản ghi khác mã.

Hãy tối ưu trong phạm vi giữ đúng ý nghĩa:

- Dùng biến thể `thenComparingInt/Long/Double` cho khóa nguyên thủy phù hợp.
- Tránh gọi mạng hoặc truy vấn cơ sở dữ liệu trong hàm lấy khóa.
- Cân nhắc tính trước các khóa tốn kém cho một lượt xử lý.
- Không để khóa thay đổi trong khi đang sort.
- Không dựa vào số lần gọi comparator cố định của một thuật toán.

Một comparator cần cho kết quả nhất quán trong thời gian sử dụng: đổi chỗ hai đối tượng phải đảo dấu; quan hệ thứ tự phải có tính bắc cầu; các phần tử so sánh bằng nhau phải có cùng quan hệ về dấu với một phần tử thứ ba.

Ghép các comparator hợp lệ là cách biểu đạt quy tắc rõ ràng. Nó không sửa được một comparator thành phần vốn sai hợp đồng hoặc đọc dữ liệu thay đổi ngẫu nhiên.

## 13. Chương trình hoàn chỉnh

Lưu thành **MultiCriteriaSortDemo.java**. Chương trình dùng API có trong Java 17; `Ticket` là record để dữ liệu ví dụ không bị sửa khóa giữa lúc so sánh.

~~~java
import java.time.LocalDate;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;

public class MultiCriteriaSortDemo {
    record Ticket(String id, int priority, LocalDate due) {}

    public static void main(String[] args) {
        List<Ticket> tickets = List.of(
                new Ticket("T4", 2, LocalDate.of(2026, 5, 10)),
                new Ticket("T2", 3, LocalDate.of(2026, 5, 8)),
                new Ticket("T6", 3, null),
                new Ticket("T1", 3, LocalDate.of(2026, 5, 8)),
                new Ticket("T3", 2, LocalDate.of(2026, 5, 6)),
                new Ticket("T5", 3, LocalDate.of(2026, 5, 12))
        );

        Comparator<LocalDate> dateOrder =
                Comparator.nullsLast(Comparator.naturalOrder());

        Comparator<Ticket> byPriorityDescending =
                Comparator.comparingInt(Ticket::priority).reversed();

        Comparator<Ticket> byDueThenId =
                Comparator.comparing(Ticket::due, dateOrder)
                        .thenComparing(Ticket::id);

        Comparator<Ticket> priorityThenDue =
                byPriorityDescending.thenComparing(Ticket::due, dateOrder);

        Comparator<Ticket> fullOrder =
                priorityThenDue.thenComparing(Ticket::id);

        Comparator<Ticket> wholeOrderReversed =
                Comparator.comparingInt(Ticket::priority)
                        .thenComparing(Ticket::due, dateOrder)
                        .thenComparing(Ticket::id)
                        .reversed();

        printSorted("Priority only", tickets, byPriorityDescending);
        printSorted("Priority then due", tickets, priorityThenDue);
        printSorted("Full order", tickets, fullOrder);
        printSorted("Whole chain reversed", tickets, wholeOrderReversed);

        List<Ticket> wrongPassOrder = new ArrayList<>(tickets);
        wrongPassOrder.sort(byPriorityDescending);
        wrongPassOrder.sort(byDueThenId);
        System.out.println("Primary sort then secondary sort = "
                + ids(wrongPassOrder));

        List<Ticket> correctPassOrder = new ArrayList<>(tickets);
        correctPassOrder.sort(byDueThenId);
        correctPassOrder.sort(byPriorityDescending);
        System.out.println("Secondary sort then primary stable sort = "
                + ids(correctPassOrder));

        Ticket t1 = tickets.get(3);
        Ticket t2 = tickets.get(1);
        Ticket t4 = tickets.get(0);

        System.out.println("Primary compare T1,T2 = "
                + byPriorityDescending.compare(t1, t2));
        System.out.println("Full compare T1,T2 sign = "
                + Integer.signum(fullOrder.compare(t1, t2)));

        int[] secondaryReads = {0};
        Comparator<Ticket> probe =
                byPriorityDescending.thenComparing(ticket -> {
                    secondaryReads[0]++;
                    return ticket.id();
                });

        probe.compare(t2, t4);
        System.out.println("Secondary reads when primary differs = "
                + secondaryReads[0]);

        secondaryReads[0] = 0;
        probe.compare(t2, t1);
        System.out.println("Secondary reads when primary ties = "
                + secondaryReads[0]);

        System.out.println("Original = " + ids(tickets));
    }

    private static void printSorted(
            String label,
            List<Ticket> source,
            Comparator<? super Ticket> order
    ) {
        List<Ticket> copy = new ArrayList<>(source);
        copy.sort(order);
        System.out.println(label + " = " + ids(copy));
    }

    private static List<String> ids(List<Ticket> tickets) {
        List<String> result = new ArrayList<>();
        for (Ticket ticket : tickets) {
            result.add(ticket.id());
        }
        return result;
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~shell
javac --release 17 -encoding UTF-8 MultiCriteriaSortDemo.java
java MultiCriteriaSortDemo
~~~

Stdout:

~~~text
Priority only = [T2, T6, T1, T5, T4, T3]
Priority then due = [T2, T1, T5, T6, T3, T4]
Full order = [T1, T2, T5, T6, T3, T4]
Whole chain reversed = [T6, T5, T2, T1, T4, T3]
Primary sort then secondary sort = [T3, T1, T2, T4, T5, T6]
Secondary sort then primary stable sort = [T1, T2, T5, T6, T3, T4]
Primary compare T1,T2 = 0
Full compare T1,T2 sign = -1
Secondary reads when primary differs = 0
Secondary reads when primary ties = 2
Original = [T4, T2, T6, T1, T3, T5]
~~~

### Đọc từng nhóm kết quả

**Priority only**

Nhóm ưu tiên `3` xuất hiện trước nhóm ưu tiên `2`. Trong từng nhóm, chưa có quy tắc hạn hay mã nên `List.sort` giữ thứ tự tương đối ban đầu: T2, T6, T1, T5 trong nhóm `3`.

**Priority then due**

T2 và T1 cùng hạn `2026-05-08`, nên vẫn giữ T2 trước T1. T5 đến sau vì có hạn muộn hơn; T6 không có hạn nên đứng cuối nhóm ưu tiên `3`.

**Full order**

Mã được xét để giải quyết cặp T1 và T2. T1 đứng trước T2 vì so sánh mã tăng dần. Các quan hệ đã được quyết định bằng ưu tiên hoặc hạn được giữ nguyên.

**Whole chain reversed**

Chuỗi tăng dần theo ưu tiên, hạn, mã bị đảo ở cuối. Nhóm ưu tiên `3` lên trước, nhưng ngày trong nhóm đi theo chiều ngược; T6 có ngày `null` còn bị đưa lên đầu. Kết quả không phải quy tắc đầy đủ mong muốn.

**Hai thứ tự gọi sort**

Sort chính rồi sort phụ đưa T3 lên đầu vì lần cuối ưu tiên hạn. Sort phụ rồi sort ổn định theo chính cho cùng dãy mã như chuỗi comparator đầy đủ.

**So sánh T1 và T2**

Comparator ưu tiên trả `0`. Comparator đầy đủ trả dấu âm vì cuối cùng mã T1 đứng trước mã T2. Chương trình in dấu bằng `Integer.signum`, không giả định mọi comparator chỉ trả `-1, 0, 1`.

**Đếm số lần lấy khóa phụ**

Khi hai công việc khác ưu tiên, khóa mã phụ không được đọc: số đếm là `0`. Khi cùng ưu tiên, hàm lấy mã đọc khóa cho hai đối tượng: số đếm là `2`.

Bộ đếm này chỉ là dụng cụ quan sát cho hai lời gọi `compare` riêng lẻ trong ví dụ. Không viết logic nghiệp vụ phụ thuộc số lần comparator được thuật toán sort gọi, và không thêm tác dụng phụ như cập nhật dữ liệu trong hàm lấy khóa.

**Dữ liệu nguồn**

Các thao tác sort trong chương trình đều dùng bản sao. Vì vậy dòng `Original` giữ dãy mã ban đầu. Tạo comparator mới và sắp xếp bản sao là hai cơ chế riêng, cùng giúp ví dụ quan sát rõ mà không thay dữ liệu nguồn.

## 14. Những lỗi dễ gặp

| Lỗi | Hệ quả | Cách sửa |
| --- | --- | --- |
| Xét tiêu chí phụ khi `equals` trả true | Nhầm bằng nhau của đối tượng với hòa theo tiêu chí | Dùng kết quả `compare == 0` trong cơ chế kết hợp. |
| Cộng các kết quả comparator | Mất thứ bậc và có thể triệt tiêu dấu | Dùng kết quả khác `0` đầu tiên hoặc `thenComparing`. |
| Đổi vị trí hai tiêu chí để “tối ưu” | Đổi yêu cầu nghiệp vụ | Giữ thứ bậc rồi tối ưu cách tính khóa. |
| Bỏ qua giá trị trả về của `thenComparing` | Comparator cũ chưa có tiêu chí mới | Gán kết quả hoặc ghép trong một biểu thức. |
| Đặt `reversed` ở cuối khi chỉ muốn đảo tiêu chí đầu | Đảo cả hạn, mã và quan hệ với `null` | Đảo đúng comparator thành phần. |
| Sort chính rồi sort phụ và mong chỉ nhóm hòa thay đổi | Lần cuối sắp lại toàn bộ danh sách | Dùng một chuỗi comparator, hoặc hiểu rõ kỹ thuật nhiều lượt ổn định. |
| Tin stable sort sẽ tạo thứ tự duy nhất | Nhóm hòa vẫn phụ thuộc đầu vào | Thêm tiêu chí giải quyết hòa có ý nghĩa khi cần. |
| Không xử lý khóa `null` vì bộ dữ liệu nhỏ chưa lỗi | Lỗi chỉ xuất hiện khi tiêu chí đó thật sự được dùng | Kiểm thử từng mức hòa và chính sách dữ liệu thiếu. |
| Dùng comparator chỉ xét một phần dữ liệu cho TreeSet | Những phần tử ngang nhau có thể bị gộp | Kiểm tra định nghĩa duy nhất và quan hệ với `equals`. |
| Dùng thuộc tính đang thay đổi hoặc số ngẫu nhiên làm khóa | Quan hệ so sánh không nhất quán | Dùng khóa ổn định trong lượt xử lý. |

## 15. Tự kiểm tra và thực hành

1. Viết bằng lời thứ bậc của `byA.thenComparing(byB).thenComparing(byC)`. Khi nào `byC` được gọi?
2. Tạo hai công việc khác ưu tiên nhưng ngày theo chiều ngược lại. Chứng minh ưu tiên vẫn quyết định kết quả.
3. Tạo hai công việc cùng ưu tiên, khác ngày, rồi hai công việc cùng ưu tiên và cùng ngày nhưng khác mã. Kiểm thử riêng hai tầng hòa.
4. Sửa comparator thành: ưu tiên giảm dần, ngày giảm dần nhưng ngày thiếu cuối, mã tăng dần.
5. Bổ sung dữ liệu có phần tử `Ticket == null`. Đặt phần tử đó ở đầu mà vẫn giữ ngày thiếu ở cuối trong từng nhóm công việc hợp lệ.
6. Đảo thứ tự đầu vào của T1 và T2. So sánh kết quả khi có và khi chưa có tiêu chí mã.
7. Bỏ qua kết quả trả về của `thenComparing` trong một bản thử nghiệm. Viết ca kiểm thử để phát hiện tiêu chí phụ chưa được áp dụng.
8. Cho một comparator chỉ xét ưu tiên vào `TreeSet`. Quan sát số phần tử, giải thích vì sao kết quả khác một danh sách đã sort, rồi chọn lại cấu trúc hoặc comparator theo yêu cầu giữ dữ liệu.

Khi đánh giá một chuỗi comparator, hãy viết rõ từng tiêu chí, chiều tăng–giảm, chính sách giá trị thiếu và ý nghĩa hòa nhau. Sau đó kiểm thử các cặp chỉ khác ở đúng một tầng để xác nhận chuỗi biểu đạt đúng thứ bậc mong muốn.
