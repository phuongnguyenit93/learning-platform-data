# Đẩy phép lọc và dừng sớm lên vị trí phù hợp

Trong **Java Stream API**, hiệu năng thường phụ thuộc nhiều vào **thứ tự các bước trong pipeline** hơn là số dòng code. `filter` giúp loại dữ liệu không cần thiết, còn các phép dừng sớm như `limit`, `findFirst` hay `anyMatch` giúp tránh xử lý phần tử sau khi đã đủ kết quả. Tuy nhiên, chỉ di chuyển các bước khi **ngữ nghĩa của bài toán vẫn được giữ nguyên**.

Bài này thuộc chương **Hiệu năng và bộ nhớ** của module **JAVA_STREAM_API**. Nó nối cách viết pipeline khai báo, lazy với các thao tác `map`, `reduce`, `collect`, đồng thời chỉ ra ảnh hưởng đến sắp xếp, gom nhóm, trạng thái, tài nguyên và stream song song.

## 1. Cơ chế cần hiểu trước khi tối ưu

Một pipeline Stream thường có ba phần:

```text
Nguồn (List, file, ...) → thao tác trung gian → terminal operation
                           filter / map / sorted   findFirst / collect / count
```

- Các thao tác trung gian như `filter`, `map`, `sorted`, `distinct` và `limit` đều **lazy**: gọi chúng chỉ tạo pipeline, chưa duyệt nguồn ngay.
- Terminal operation như `toList`, `collect`, `reduce`, `count` hay `findFirst` kích hoạt việc xử lý. Với pipeline tuần tự thông thường, các thao tác không có trạng thái như `filter` và `map` được kết hợp để xử lý từng phần tử, thay vì tạo một danh sách trung gian sau mỗi bước.
- Một số thao tác có trạng thái (`sorted`, `distinct` và một số cách dùng `limit`, `skip`) có thể phải lưu dữ liệu hoặc phối hợp giữa nhiều phần tử. Đây là nơi việc giảm số phần tử **trước** thao tác tốn kém thường mang lại lợi ích rõ rệt.
- Phép dừng sớm là **khả năng** kết thúc khi đã đủ thông tin, không phải lời hứa rằng số lần gọi predicate luôn bằng đúng số phần tử đầu tiên thấy được. Pipeline song song hoặc thao tác có trạng thái ở phía trước có thể xử lý thêm dữ liệu.

Ví dụ, pipeline sau không tạo ba danh sách trung gian:

```java
List<Integer> result = numbers.stream()
    .filter(n -> n > 0)
    .map(n -> n * 2)
    .limit(3)
    .toList();
```

Trong một stream tuần tự có thứ tự và không có thao tác cản trở dừng sớm, pipeline có thể kết thúc sau khi tìm đủ **3 số dương**, thay vì đọc toàn bộ nguồn.

## 2. Đưa `filter` lên trước thao tác đắt tiền

Giả sử có danh sách đơn hàng và cần lấy 20 đơn **đã thanh toán**, có giá trị cao nhất. Cả hai cách dưới đây cùng cho kết quả khi phép so sánh và predicate thuần túy, nhưng lượng dữ liệu cần sắp xếp khác nhau.

```java
record Order(long id, boolean paid, int totalCents) {}

Comparator<Order> byValueDescending =
    Comparator.comparingInt(Order::totalCents).reversed();

// Sắp xếp tất cả rồi mới lọc.
List<Order> slower = orders.stream()
    .sorted(byValueDescending)
    .filter(Order::paid)
    .limit(20)
    .toList();

// Lọc trước để giảm kích thước tập cần sắp xếp.
List<Order> better = orders.stream()
    .filter(Order::paid)
    .sorted(byValueDescending)
    .limit(20)
    .toList();
```

Nếu nguồn có `n` đơn và chỉ `m` đơn đã thanh toán (`m` nhỏ hơn nhiều `n`), chi phí sắp xếp điển hình giảm từ khoảng `O(n log n)` xuống `O(m log m)`. `sorted` vẫn phải chuẩn bị tập cần sắp xếp trước khi xuất phần tử đầu tiên, nên đặt `limit(20)` sau `sorted` **không** khiến thao tác sắp xếp chỉ xem 20 đơn. Bộ nhớ làm việc để sắp xếp cũng phụ thuộc số phần tử đi đến `sorted`.

Quy tắc thực hành: đặt những phép lọc **rẻ, có độ loại bỏ cao và không phụ thuộc kết quả bước sau** trước `sorted`, `distinct`, ánh xạ tốn kém và các collector gom nhóm. Ví dụ, lọc đơn hợp lệ trước khi `collect(groupingBy(...))` giúp giảm lượng dữ liệu phải đưa vào các nhóm.

### Lọc trước `map` khi có thể

```java
// Cần tạo báo cáo cho tối đa 50 đơn đã thanh toán, đủ ngưỡng.
List<Report> reports = orders.stream()
    .filter(Order::paid)
    .filter(o -> o.totalCents() >= 100_000)
    .limit(50)
    .map(this::buildReport)
    .toList();
```

Ở đây `buildReport` được giả định là phép biến đổi không có tác dụng phụ, tốn chi phí và không đổi số lượng phần tử. Cách đặt `limit` trước `map` giúp tránh tạo báo cáo ngoài 50 đơn cần lấy. Nếu phải lọc theo **thuộc tính chỉ xuất hiện sau khi map**, không thể tự ý kéo predicate lên; cần chứng minh hoặc viết lại một predicate tương đương trên dữ liệu gốc.

Một điểm nhỏ nhưng hữu ích: với các điều kiện độc lập, thường nên kiểm tra điều kiện rẻ trước điều kiện tốn kém. Chẳng hạn `.filter(o -> o.paid() && expensiveCheck(o))` tận dụng cơ chế đoản mạch của toán tử `&&`. Việc thay đổi thứ tự có thể làm thay đổi hành vi nếu các hàm có tác dụng phụ hoặc phát sinh ngoại lệ; predicate trong Stream nên thuần túy và không can thiệp vào nguồn.

## 3. `limit` đặt trước hay sau `filter` là hai bài toán khác nhau

Xét bốn đơn theo đúng thứ tự gặp:

```java
List<Order> sample = List.of(
    new Order(1, false, 900),
    new Order(2, true,  500),
    new Order(3, true, 1000),
    new Order(4, true,  700)
);

List<Long> firstTwoPaid = sample.stream()
    .filter(Order::paid)
    .limit(2)
    .map(Order::id)
    .toList(); // [2, 3]

List<Long> paidAmongFirstTwo = sample.stream()
    .limit(2)
    .filter(Order::paid)
    .map(Order::id)
    .toList(); // [2]
```

- `filter(...).limit(2)` nghĩa là **tìm tối đa hai phần tử thỏa điều kiện**.
- `limit(2).filter(...)` nghĩa là **chỉ xét hai phần tử đầu nguồn rồi lọc**.

Không có cách nào luôn nhanh hơn mà vẫn cho cùng đáp án; phải chọn theo yêu cầu nghiệp vụ. Tương tự, chuyển `limit` lên trước `sorted` biến “20 đơn lớn nhất” thành “sắp xếp 20 đơn đầu tiên”, hoàn toàn khác nhau.

Ngược lại, với phép `map` thuần túy, một-một và không thay đổi thứ tự, có thể cân nhắc đẩy `limit` lên trước để tránh ánh xạ phần tử thừa:

```java
// Khi chỉ cần 20 bản ghi đầu tiên sau khi đã lọc:
List<String> labels = orders.stream()
    .filter(Order::paid)
    .limit(20)
    .map(o -> "Order #" + o.id())
    .toList();
```

Đừng áp dụng suy luận này cho `flatMap` nếu mỗi phần tử đầu vào tạo ra số phần tử đầu ra khác nhau: `limit` trước `flatMap` đếm **phần tử cha**, còn `limit` sau `flatMap` đếm **phần tử con**.

## 4. Chọn phép dừng sớm đúng mục tiêu

| Mục tiêu | Terminal/intermediate phù hợp | Điều kiện kết thúc |
| --- | --- | --- |
| Chỉ cần biết có ít nhất một phần tử thỏa | `anyMatch(predicate)` | Có một kết quả `true` |
| Kiểm tra mọi phần tử đều thỏa | `allMatch(predicate)` | Gặp phần tử `false` |
| Kiểm tra không phần tử nào thỏa | `noneMatch(predicate)` | Gặp phần tử `true` |
| Lấy phần tử đầu tiên theo encounter order | `findFirst()` | Xác định được phần tử đầu tiên |
| Lấy một phần tử bất kỳ | `findAny()` | Có một phần tử thích hợp |
| Lấy tối đa `k` phần tử | `limit(k)` | Có tối đa `k` phần tử đầu ra |
| Lấy tiền tố liên tục thỏa điều kiện | `takeWhile(predicate)` | Đến phần tử đầu tiên không thỏa, trên stream có thứ tự |

Ví dụ, nếu chỉ cần xác định có đơn lớn và đã thanh toán, không nên tạo danh sách kết quả rồi kiểm tra rỗng:

```java
boolean exists = orders.stream()
    .anyMatch(o -> o.paid() && o.totalCents() >= 100_000);
```

Cách `.filter(...).findFirst().isPresent()` cũng có thể dừng sớm, nhưng `anyMatch` diễn đạt trực tiếp mục tiêu “có tồn tại hay không”. `allMatch` và `noneMatch` trên stream rỗng đều trả về `true` theo quy tắc logic; phải xử lý riêng nếu bài toán đòi hỏi tồn tại ít nhất một phần tử.

Khi cần **đơn đầu tiên**, chọn `findFirst` nếu thứ tự nguồn mang ý nghĩa. `findAny` có thể giảm yêu cầu phối hợp ở stream song song khi **bất kỳ** phần tử nào cũng được. Không hứa hẹn `findAny` luôn nhanh hơn, và không giả định kết quả ổn định giữa các lần chạy.

## 5. Phân biệt `filter` với `takeWhile` và `dropWhile`

Từ Java 9, `takeWhile` và `dropWhile` hỗ trợ xử lý tiền tố của stream; chúng **không** thay thế `filter` trong mọi trường hợp.

```java
List<Integer> values = List.of(2, 4, 7, 6, 8);

List<Integer> filtered = values.stream()
    .filter(n -> n % 2 == 0)
    .toList(); // [2, 4, 6, 8]

List<Integer> prefix = values.stream()
    .takeWhile(n -> n % 2 == 0)
    .toList(); // [2, 4]

List<Integer> remainder = values.stream()
    .dropWhile(n -> n % 2 == 0)
    .toList(); // [7, 6, 8]
```

`takeWhile` đặc biệt phù hợp khi **dữ liệu có thứ tự** và điều kiện mô tả một tiền tố, chẳng hạn các sự kiện đã được sắp theo thời gian và chỉ lấy đến một mốc. Nếu dữ liệu không sắp đúng thứ tự, `takeWhile` sẽ dừng ở phần tử vi phạm đầu tiên và có thể bỏ qua phần tử hợp lệ phía sau. Trên stream không có thứ tự, ý nghĩa phần tập con được lấy bởi `takeWhile`/`dropWhile` khác với tiền tố xác định; không dùng chúng thay `filter` để tính kết quả chính xác theo vị trí.

## 6. Các “hàng rào” có thể làm mất lợi ích của dừng sớm

Pipeline lazy không có nghĩa mọi bước đều xử lý được từng phần tử rồi xuất ngay:

```java
// Phải sắp xếp tập phần tử phù hợp trước khi biết ai là nhỏ nhất.
Optional<Order> smallestPaid = orders.stream()
    .filter(Order::paid)
    .sorted(Comparator.comparingInt(Order::totalCents))
    .findFirst();
```

Nếu chỉ cần **giá trị nhỏ nhất**, hãy dùng phép reduction chuyên dụng, thường tránh phải sắp xếp toàn bộ tập:

```java
Optional<Order> smallestPaid = orders.stream()
    .filter(Order::paid)
    .min(Comparator.comparingInt(Order::totalCents));
```

`min` vẫn phải xét các ứng viên phù hợp để bảo đảm đúng kết quả; lợi ích chính là không cần sắp xếp toàn bộ tập. Với dữ liệu hữu hạn, `min` điển hình cần `O(n)` lần so sánh và bộ nhớ phụ nhỏ, trong khi `sorted` thường có chi phí `O(n log n)` cùng bộ đệm sắp xếp.

Các hàng rào thường gặp:

- `sorted` cần nhiều trạng thái; một `limit` phía sau không bảo đảm bỏ được việc sắp xếp các phần tử trước đó.
- `distinct` theo dõi các phần tử đã gặp; với nguồn có nhiều giá trị khác nhau, lượng trạng thái có thể tăng đáng kể.
- `skip(k)` và `limit(k)` trên stream song song **có thứ tự** có thể yêu cầu phối hợp để giữ chính xác vị trí.
- `collect`/`groupingBy` thông thường phải nhận các phần tử tới cuối pipeline; chỉ đưa phần tử thực sự cần thiết vào collector. Với một số source/terminal, JDK có thể tối ưu đếm hoặc bỏ qua các bước trung gian không ảnh hưởng kết quả, nên không dùng side effect trong `peek` để suy ra chính xác bao nhiêu phần tử đã được xử lý.

Muốn lấy **top K** trên nguồn rất lớn với giới hạn bộ nhớ nghiêm ngặt, cân nhắc thuật toán heap kích thước K hoặc collector chuyên dụng thay vì `sorted(...).limit(k)`; đó là thay đổi thuật toán, cần xử lý comparator, kết quả trùng, thứ tự và tính kết hợp của collector cẩn thận.

## 7. Cần chứng minh phép đổi thứ tự giữ nguyên kết quả

| Thay đổi thứ tự | Có nên? | Điều kiện cần xem xét |
| --- | --- | --- |
| `filter → sorted` thay cho `sorted → filter` | Thường có lợi | Predicate không phụ thuộc vị trí/xếp hạng; comparator và predicate thuần túy; vẫn giữ quy tắc xử lý phần tử bằng nhau |
| `filter → map` thay cho `map → filter` | Có điều kiện | Có predicate tương đương trên đầu vào, và phép ánh xạ không cần thực hiện cho phần tử bị loại |
| `limit → map` thay cho `map → limit` | Có điều kiện | Map thuần túy, một-một, không đổi thứ tự và không có yêu cầu phải thực hiện map trên phần tử bị bỏ |
| `limit → filter` thay cho `filter → limit` | Thường sai | Đổi “đủ K phần tử đạt điều kiện” thành “lọc trong K phần tử đầu” |
| `limit → sorted` thay cho `sorted → limit` | Thường sai | Đổi chọn top K toàn nguồn thành top K trên đoạn đầu nguồn |
| `filter ↔ distinct` | Cần xét kỹ | Predicate phải cho cùng kết quả trên các phần tử được xem là bằng nhau; việc chọn phần tử đại diện và thứ tự có thể ảnh hưởng kết quả |
| `takeWhile` thay `filter` | Chỉ khi đúng ý | Cần tiền tố liên tục, thường dựa vào encounter order thích hợp |

Ví dụ `filter` và `distinct` không luôn hoán đổi an toàn: hai đối tượng được coi bằng nhau theo `equals` nhưng khác thuộc tính dùng để lọc có thể khiến `distinct().filter(...)` giữ phần tử đại diện không thỏa, trong khi `filter(...).distinct()` giữ một phần tử khác. Tương tự, nếu việc gọi `map`, predicate hoặc comparator tạo hiệu ứng phụ, ném lỗi theo dữ liệu hay phụ thuộc trạng thái ngoài, thay đổi thứ tự còn có thể thay đổi những hiệu ứng quan sát được. Stream API khuyến khích các hàm **stateless, non-interfering** (không sửa nguồn đang duyệt).

## 8. Stream tuần tự, song song và encounter order

Với danh sách có thứ tự, `filter(...).limit(10)` diễn đạt “10 phần tử đạt điều kiện đầu tiên”. Ở pipeline tuần tự, nó thường cho phép ngừng kéo phần tử từ nguồn sớm. Ở `parallelStream()`, việc bảo đảm **đầu tiên** có thể đòi hỏi các nhánh phối hợp, lưu đệm hoặc xử lý thêm phần tử. Phụ thuộc source, kích thước dữ liệu, độ tốn kém của predicate và đặc tính `Spliterator` (`ORDERED`, `SIZED`, `SUBSIZED`, ...), bản song song có thể chậm hơn tuần tự.

```java
// Chỉ dùng nếu yêu cầu cho phép lấy bất kỳ 10 đơn đạt điều kiện.
List<Order> anyTen = orders.parallelStream()
    .unordered()
    .filter(Order::paid)
    .limit(10)
    .toList();
```

`unordered()` từ bỏ yêu cầu encounter order cho các bước phía sau, **không** xáo trộn dữ liệu theo cách có thể dự đoán. Việc này đôi khi giúp `limit`/`findAny` hoạt động hiệu quả hơn khi chạy song song, nhưng không phù hợp với yêu cầu “10 đơn đầu tiên”, “đầu tiên theo thời gian” hoặc tái lập kết quả cố định. Không tự bật `parallel()` chỉ vì dữ liệu lớn; hãy đo với khối lượng và cách truy cập dữ liệu thật.

Nếu sử dụng một `Gatherer` hay collector tùy chỉnh có trạng thái, cần xem xét riêng khả năng dừng sớm, lượng dữ liệu lưu lại và quy tắc kết hợp khi chạy song song. Không mặc định rằng cách tối ưu của một chuỗi `filter/map` đơn giản áp dụng y hệt cho các bước có trạng thái này.

## 9. Dừng sớm với nguồn giữ tài nguyên

Đọc file theo dòng là một trường hợp tiết kiệm cả thời gian lẫn I/O khi dừng sớm:

```java
Path path = Path.of("events.log");

try (Stream<String> lines = Files.lines(path, StandardCharsets.UTF_8)) {
    List<String> firstHundredNonBlank = lines
        .filter(line -> !line.isBlank())
        .limit(100)
        .toList();

    // Dùng firstHundredNonBlank trong phạm vi cần thiết.
}
```

Dùng `try-with-resources` để đóng stream và file ngay cả khi `limit` khiến việc đọc dừng trước cuối file, hoặc terminal operation phát sinh lỗi. Không lưu stream rồi dùng sau khi đóng; không đọc cả file bằng `readAllLines` nếu mục tiêu chỉ là một số dòng đầu đạt điều kiện. Việc dừng sớm trên nguồn thực tế còn phụ thuộc cơ chế đọc đệm, đặc tính `Spliterator` và các bước ở phía trước.

## 10. Cách đo và quyết định trong dự án thực tế

1. **Viết rõ kết quả cần lấy**: “K phần tử đầu tiên đạt điều kiện”, “K phần tử lớn nhất”, “có tồn tại”, hay “mọi phần tử đều đạt”. Các mục tiêu này dẫn đến pipeline khác nhau.
2. **Xác định bước tốn kém hoặc giữ trạng thái**: `map` tạo object, lời gọi I/O, `sorted`, `distinct`, `groupingBy` và các collector tùy chỉnh. Đặt `filter` độc lập trước các bước ấy nếu giữ nguyên ý nghĩa.
3. **Kiểm chứng ngữ nghĩa bằng dữ liệu góc cạnh**: nguồn rỗng, ít hơn K phần tử đạt, nhiều giá trị trùng, phần tử đầu không đạt, dữ liệu không theo thứ tự giả định; kiểm tra cả các side effect cần loại bỏ.
4. **Đo sau khi có phương án đúng**: dùng JMH khi đo vi mô, warm-up JVM, giữ dữ liệu đầu vào và cách tiêu thụ kết quả tương đương; quan sát throughput, allocation và GC, cân nhắc dữ liệu lớn/nhỏ cũng như tuần tự/song song. Không dựa vào một phép đo thời gian đơn lẻ bằng `System.nanoTime()` để kết luận.
5. **Đo tổng thể trước khi làm phức tạp code**: nếu predicate quá rẻ hoặc nguồn nhỏ, lợi ích có thể không đáng kể. Đọc được, đúng nghiệp vụ và khả năng bảo trì vẫn là tiêu chí.

### Bài tập tự kiểm tra

Với danh sách đơn hàng ở mục 3, dự đoán kết quả của ba pipeline sau rồi tự chạy để kiểm tra:

```java
sample.stream().filter(Order::paid).limit(2).map(Order::id).toList();
sample.stream().limit(2).filter(Order::paid).map(Order::id).toList();
sample.stream().filter(Order::paid)
    .sorted(Comparator.comparingInt(Order::totalCents).reversed())
    .limit(2).map(Order::id).toList();
```

**Đáp án:** lần lượt là `[2, 3]`, `[2]` và `[3, 4]`. Pipeline cuối có sắp xếp, nên đáp án phản ánh hai đơn đã thanh toán có giá trị lớn nhất thay vì hai đơn đã thanh toán xuất hiện đầu tiên.

**Ghi nhớ khi thiết kế pipeline:** lọc sớm khi điều kiện độc lập, dừng sớm theo đúng mục tiêu, và luôn kiểm tra các bước có trạng thái/encounter order trước khi đổi thứ tự. Với Stream, tối ưu hiệu năng chỉ hợp lệ khi **kết quả quan sát được vẫn đúng**.
