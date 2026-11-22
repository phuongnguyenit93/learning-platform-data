# Ngắn mạch không bảo đảm mọi pipeline trên nguồn vô hạn đều kết thúc — Java Stream

## 1. Mục tiêu bài học

Java Stream có các thao tác **short-circuiting (ngắn mạch)**, chẳng hạn `anyMatch`, `findFirst`, `limit` và `takeWhile`. Chúng **có thể** hoàn tất mà không duyệt mọi phần tử nguồn. Nhưng một suy luận sai thường gặp là:

> “Chỉ cần có thao tác ngắn mạch ở đâu đó, pipeline trên Stream vô hạn chắc chắn kết thúc.”

**Không đúng.** Khả năng dừng sớm chỉ có ích khi pipeline thực sự tạo được **bằng chứng để dừng**, và các giai đoạn trước thao tác ấy có thể **cung cấp phần tử/kết quả cần thiết trong thời gian hữu hạn**. Một bộ lọc không bao giờ chấp nhận phần tử, một phép tìm kiếm không bao giờ gặp giá trị cần tìm, hoặc một bước sắp xếp toàn bộ nguồn vô hạn có thể khiến terminal không trả kết quả.

Sau bài học, bạn có thể:

- Phân biệt **nguồn vô hạn**, **pipeline vô hạn**, **thao tác ngắn mạch** và **điều kiện kết thúc thực tế**.
- Đánh giá khả năng kết thúc của `limit`, `findFirst`, `findAny`, `anyMatch`, `allMatch`, `noneMatch`, `takeWhile`, `dropWhile` khi nguồn có thể sinh vô hạn phần tử.
- Hiểu vì sao `filter(...).limit(n)` có thể mãi chờ dù n hữu hạn; tại sao `distinct().limit(n)` có thể không đủ giá trị phân biệt; và tại sao `sorted().findFirst()` là một cách nguy hiểm để lấy cực trị trên nguồn vô hạn.
- Biết vị trí của `limit`, `sorted`, `filter` và `takeWhile` ảnh hưởng cả **ngữ nghĩa** lẫn khả năng kết thúc.
- Thiết kế giải pháp có **giới hạn nguồn, điều kiện dừng, timeout/cancellation ở tầng phù hợp**, và không thử chạy vô hạn các ví dụ được đánh dấu không kết thúc.
- Kiểm thử Java 17 với một chương trình hoàn chỉnh có **các pipeline thực sự kết thúc**, kèm giải thích những phản ví dụ cần tránh.

## 2. Thế nào là nguồn Stream vô hạn?

Java có thể biểu diễn một nguồn **không tự hết phần tử**:

~~~java
Stream<Integer> naturals = Stream.iterate(0, n -> n + 1);
Stream<String> repeated = Stream.generate(() -> "A");
~~~

Đây là các đoạn minh họa cần import `java.util.stream.Stream`. `Stream.iterate(seed, next)` dạng hai đối số liên tục tạo phần tử kế tiếp theo hàm `next`. Với `int`, giá trị sau rất nhiều lần sinh có thể tràn và quay vòng, nhưng bản thân **nguồn không có điểm kết thúc được khai báo**. `Stream.generate` cũng không có cơ chế tự dừng khi Supplier luôn trả giá trị hoặc không ném lỗi.

Đối chiếu với nguồn hữu hạn:

~~~java
Stream<Integer> finite = Stream.of(1, 2, 3);
Stream<Integer> range = IntStream.range(0, 5).boxed();
~~~

Hai nguồn hữu hạn có số phần tử được xác định. Một stream từ collection hữu hạn cũng có thể trở thành **pipeline không kết thúc** nếu callback tự mắc kẹt, nhưng khi nói “nguồn vô hạn” ở bài này, ta chủ yếu xét source có khả năng sinh tiếp vô hạn giá trị.

### 2.1. Vô hạn không đồng nghĩa đã chứa vô hạn phần tử trong RAM

Stream thường đánh giá **lazy**: nguồn có thể tạo phần tử **theo nhu cầu của terminal**, không cần chuẩn bị sẵn mọi phần tử. Việc mô tả một nguồn vô hạn chưa tự làm ứng dụng hết bộ nhớ.

Rủi ro xảy ra khi terminal hoặc intermediate operation đòi **toàn bộ dữ liệu**, cần đệm quá nhiều phần tử, hoặc tiếp tục sinh dữ liệu nhưng không bao giờ đạt điều kiện kết thúc. Khi đó CPU/thời gian/bộ nhớ có thể bị tiêu thụ không giới hạn.

### 2.2. Không tái sử dụng cùng đối tượng Stream

Một đối tượng Stream được thiết kế để tiêu thụ **một lần**. Không gọi nhiều terminal operation lên cùng biến Stream đã tiêu thụ:

~~~java
Stream<Integer> s = Stream.of(1, 2, 3);
long count = s.count();

// Sai: s đã bị tiêu thụ.
// List<Integer> second = s.toList();
~~~

Nếu muốn thử nhiều terminal, tạo **Stream mới** từ một factory/Supplier hoặc một nguồn có thể tạo lại, với lưu ý rằng nội dung nguồn và các side effect cũng có thể thay đổi.

## 3. Ngắn mạch chính xác là gì?

Một thao tác short-circuiting **có thể trả lời mà không cần tiêu thụ toàn bộ nguồn**. Không phải mọi dữ liệu đều cần được đánh giá khi đã có đủ thông tin.

| Loại | Thao tác | Điều kiện có thể hoàn tất |
| --- | --- | --- |
| Terminal | `anyMatch(p)` | Đã thấy ít nhất một phần tử mà p trả true, hoặc nguồn thực sự kết thúc |
| Terminal | `allMatch(p)` | Đã thấy ít nhất một phần tử mà p trả false, hoặc nguồn thực sự kết thúc |
| Terminal | `noneMatch(p)` | Đã thấy ít nhất một phần tử mà p trả true, hoặc nguồn thực sự kết thúc |
| Terminal | `findFirst()` | Đã xác định được phần tử đầu tiên theo encounter order, hoặc nguồn kết thúc |
| Terminal | `findAny()` | Đã tìm được một phần tử phù hợp, hoặc nguồn kết thúc |
| Intermediate | `limit(n)` | Đã có n phần tử **đi tới limit**, hoặc upstream kết thúc |
| Intermediate | `takeWhile(p)` | Với ordered stream, gặp phần tử đầu tiên p=false; hoặc nguồn kết thúc |

**Quan trọng:** Bảng này mô tả cơ hội dừng sớm, không cam kết một thời gian chạy hữu hạn trong mọi hoàn cảnh. Nếu callback treo hoặc không bao giờ có phần tử đạt điều kiện, toàn bộ pipeline vẫn có thể không hoàn tất.

### 3.1. Một thao tác có thể short-circuit về mặt loại, nhưng không trên dữ liệu thực tế

Ví dụ:

~~~java
boolean exists = Stream.generate(() -> "A")
        .anyMatch("A"::equals);
~~~

Với Supplier luôn tạo `"A"`, phần tử đầu tiên là bằng chứng true nên pipeline có thể kết thúc nhanh.

Ngược lại, **không chạy phản ví dụ này**:

~~~java
// Không chạy: nguồn luôn trả "A", điều kiện luôn false.
// boolean exists = Stream.generate(() -> "A")
//         .anyMatch("B"::equals);
~~~

`anyMatch` chỉ có thể kết luận false khi **nguồn hết phần tử** và chưa tìm thấy phần tử phù hợp. Nguồn ở đây không hết, và cũng không bao giờ có "B": vì thế không có điểm dừng bình thường.

## 4. Tính lazy không bảo đảm có tiến triển

`filter`, `map`, `flatMap`, `peek` là intermediate operation lazy: gọi chúng để **xây dựng pipeline** chưa chạy toàn bộ công việc. Terminal operation mới kích hoạt quá trình đánh giá.

Ví dụ:

~~~java
Stream<Integer> pipeline = Stream.generate(() -> 1)
        .filter(n -> n > 1);

// Chỉ xây dựng pipeline, không đợi một phần tử nào tại đây.
~~~

Tuy nhiên, nếu sau đó gọi:

~~~java
// KHÔNG CHẠY: filter không bao giờ cho phần tử đi tiếp.
// int first = pipeline.findFirst().orElseThrow();
~~~

`findFirst` cần có một phần tử đi tới terminal. Nhưng `filter(n -> n > 1)` luôn trả false đối với giá trị 1 từ Supplier. Mỗi phần tử bị bỏ; upstream không hết; terminal không bao giờ có giá trị hoặc chứng cứ rằng stream đã kết thúc.

**Lazy** nghĩa là *chưa tính ngay*, không có nghĩa *tính xong trong thời gian hữu hạn*. Nó cũng không có nghĩa pipeline tự chạy ở thread nền hoặc có timeout mặc định.

## 5. limit(n) hữu hạn vẫn có thể chờ mãi

Một công thức thường đúng:

~~~java
List<Integer> firstFive = Stream.iterate(0, n -> n + 1)
        .limit(5)
        .toList();

// [0, 1, 2, 3, 4]
~~~

Nguồn có thể sinh 0,1,2,3,4 trong thời gian hữu hạn; `limit(5)` nhận đủ năm phần tử; `toList` hoàn tất.

Nhưng **limit tính số phần tử đi qua các bước trước nó**, không đếm trực tiếp mọi phần tử gốc nếu upstream đã lọc.

### 5.1. Filter trước limit: có thể không bao giờ đủ n phần tử

Không chạy:

~~~java
// KHÔNG CHẠY: chỉ có 1, còn filter đòi > 1.
// List<Integer> never = Stream.generate(() -> 1)
//         .filter(n -> n > 1)
//         .limit(3)
//         .toList();
~~~

`limit(3)` sẽ chờ ba phần tử sau filter. **Không một phần tử nào đi qua filter** nên nó không đạt n=3, dù số 3 là hữu hạn. `toList()` chờ mãi.

Đối chiếu một pipeline có phần tử hợp lệ xuất hiện:

~~~java
List<Integer> evens = Stream.iterate(0, n -> n + 1)
        .filter(n -> n > 0 && n % 2 == 0)
        .limit(3)
        .toList();

// [2, 4, 6]
~~~

Dãy đầu vào có 2,4,6 sau hữu hạn bước. Do đó chương trình có thể hoàn tất. **Điều kiện cần không chỉ là limit hữu hạn, mà upstream phải cung cấp đủ phần tử đi qua filter** trong một quá trình hữu hạn.

### 5.2. Đảo limit và filter thay đổi bài toán

~~~java
List<Integer> a = Stream.iterate(0, n -> n + 1)
        .filter(n -> n % 2 == 0)
        .limit(3)
        .toList();

List<Integer> b = Stream.iterate(0, n -> n + 1)
        .limit(3)
        .filter(n -> n % 2 == 0)
        .toList();
~~~

- `a = [0, 2, 4]`: lấy **ba số chẵn đầu tiên**.
- `b = [0, 2]`: chỉ **ba số tự nhiên đầu** 0,1,2 được đưa qua filter, nên kết quả có hai số chẵn.

Đưa `limit` lên trước filter **bảo đảm giới hạn số phần tử được đưa vào filter** khi nguồn có thể sinh đủ n phần tử; nhưng đổi thứ tự cũng đổi ngữ nghĩa. Nếu nghiệp vụ yêu cầu tìm ba phần tử đạt điều kiện, không thể tự biến thành “xét ba phần tử rồi chọn” mà vẫn báo kết quả tương đương.

### 5.3. limit(0) và limit âm

`limit(0)` mô tả một stream rỗng, có thể hoàn tất mà không cần xem phần tử trong những pipeline thông thường. `limit(-1)` không hợp lệ và ném `IllegalArgumentException`.

Không nên dựa vào `limit(0)` để buộc các thao tác upstream phải được gọi cho side effect; chúng có thể bị bỏ qua vì không cần thiết cho kết quả.

## 6. anyMatch: cần chứng cứ true, hoặc nguồn hữu hạn để trả false

Giả sử:

~~~java
boolean found = Stream.generate(() -> "ready")
        .anyMatch("ready"::equals);
// true
~~~

Có chứng cứ true ngay phần tử đầu.

Phản ví dụ:

~~~java
// KHÔNG CHẠY:
// Stream.generate(() -> "ready")
//       .anyMatch("missing"::equals);
~~~

Điều kiện luôn false và nguồn không hết. Không có cách nào để kết luận “không tồn tại” dựa trên một số hữu hạn các phần tử đã xét, vì phần tử phù hợp **về mặt tổng quát** có thể xuất hiện sau đó.

Đây là khác biệt giữa:

- **Bằng chứng tồn tại:** chỉ cần thấy một phần tử.
- **Bằng chứng không tồn tại trong toàn nguồn:** phải biết nguồn đã được xét hết, hoặc có một **bảo đảm miền dữ liệu/điều kiện dừng khác** đủ mạnh.

Đối với một tập dữ liệu nguồn được xác định là vô hạn và chỉ có giá trị “ready”, ta có thể **lập luận bằng kiến thức về Supplier** để biết không bao giờ có “missing”; nhưng bản thân generic terminal `anyMatch` không có phép chứng minh biểu tượng ấy. Nó cứ tiếp tục yêu cầu phần tử.

## 7. allMatch và noneMatch: có thể dừng khi gặp phản ví dụ

### 7.1. allMatch

`allMatch(p)` trả false khi gặp một phần tử p=false:

~~~java
boolean allLessThanFive = Stream.iterate(0, n -> n + 1)
        .allMatch(n -> n < 5);
// false, vì eventually gặp 5.
~~~

Với ordered sequential pipeline đơn giản, các giá trị 0 đến 4 cho true, đến 5 thì predicate false và terminal đủ dữ liệu để kết luận.

Ngược lại:

~~~java
// KHÔNG CHẠY: tất cả phần tử luôn bằng "A".
// boolean allA = Stream.generate(() -> "A")
//         .allMatch("A"::equals);
~~~

Để trả true, `allMatch` phải biết mọi phần tử của nguồn đều phù hợp. Nguồn vô hạn không bao giờ kết thúc, nên không có điểm dừng bình thường khi mọi lời kiểm tra đều true.

### 7.2. noneMatch

`noneMatch(p)` trả false khi gặp phần tử p=true:

~~~java
boolean noneIsFive = Stream.iterate(0, n -> n + 1)
        .noneMatch(n -> n == 5);
// false.
~~~

Ngược lại:

~~~java
// KHÔNG CHẠY: không bao giờ tìm thấy "B".
// boolean noneB = Stream.generate(() -> "A")
//         .noneMatch("B"::equals);
~~~

Để xác nhận true trên một nguồn không kết thúc, generic terminal phải biết toàn bộ nguồn không có phần tử thỏa; nó không thể quyết định chỉ bằng việc kiểm tra mãi những phần tử "A".

### 7.3. Bảng dấu hiệu dừng

| Terminal | Chứng cứ có thể dừng sớm | Trường hợp vô hạn dễ không kết thúc |
| --- | --- | --- |
| `anyMatch(p)` | Một giá trị p=true | p luôn false |
| `allMatch(p)` | Một giá trị p=false | p luôn true |
| `noneMatch(p)` | Một giá trị p=true | p luôn false |

Trên **stream rỗng thực sự**, `anyMatch` trả false, `allMatch` và `noneMatch` trả true. Nhưng **nguồn vô hạn không bao giờ trở thành rỗng sau khi đã xét vài giá trị không phù hợp**; không được áp dụng nhầm quy tắc stream rỗng cho phần dữ liệu chưa duyệt.

## 8. findFirst/findAny: phần tử đi tới terminal mới có ý nghĩa

Một trường hợp kết thúc:

~~~java
Optional<Integer> firstSeven = Stream.iterate(0, n -> n + 1)
        .filter(n -> n > 0 && n % 7 == 0)
        .findFirst();

// Optional chứa 7.
~~~

Sau hữu hạn giá trị, filter cho số 7 đi tiếp nên `findFirst` có kết quả.

Phản ví dụ:

~~~java
// KHÔNG CHẠY:
// Stream.generate(() -> 1)
//       .filter(n -> n == 2)
//       .findFirst();
~~~

Không phần tử nào đi qua filter. Vấn đề không phải `findFirst` có ngắn mạch hay không, mà là **nó không bao giờ nhận được phần tử đầu tiên**.

### 8.1. findFirst khác findAny

`findFirst` cần tôn trọng **encounter order** của một ordered stream. `findAny` có thể chọn bất kỳ phần tử phù hợp nào và thường linh hoạt hơn trong parallel execution.

Nếu Stream vô hạn có thể cung cấp phần tử ngay cho terminal, cả hai có thể kết thúc. Nếu filter không bao giờ đưa phần tử nào qua thì cả hai đều có thể chờ mãi. Dùng `findAny` **không chữa** một nguồn/upstream không có giá trị hợp lệ.

Một lưu ý khác: `findFirst/findAny` trả `Optional<T>` không chứa null. Nếu phần tử được chọn là null, có thể ném `NullPointerException`; đó là lỗi, không phải kết thúc bình thường với empty.

## 9. takeWhile: cần gặp biên dừng

Java 9+ có `takeWhile(predicate)`. Với **ordered stream**, nó lấy tiền tố dài nhất mà các phần tử liên tiếp thỏa predicate, rồi dừng ở phần tử đầu tiên không thỏa.

~~~java
List<Integer> prefix = Stream.iterate(0, n -> n + 1)
        .takeWhile(n -> n < 4)
        .toList();

// [0, 1, 2, 3]
~~~

Nguồn vô hạn nhưng phần tử 4 là **ranh giới dừng xuất hiện sau hữu hạn bước**, nên terminal `toList` có thể hoàn tất.

Phản ví dụ:

~~~java
// KHÔNG CHẠY:
// Stream.generate(() -> "A")
//       .takeWhile("A"::equals)
//       .toList();
~~~

Predicate luôn true, không có phần tử đầu tiên làm `takeWhile` dừng, nên luồng kết quả vẫn vô hạn và `toList` chờ mãi (hoặc hết tài nguyên).

### 9.1. takeWhile khác filter

~~~java
List<Integer> source = List.of(1, 2, 5, 1, 0);

List<Integer> a = source.stream()
        .takeWhile(n -> n < 5)
        .toList(); // [1, 2]

List<Integer> b = source.stream()
        .filter(n -> n < 5)
        .toList(); // [1, 2, 1, 0]
~~~

Với ordered stream, `takeWhile` chỉ lấy **tiền tố**; `filter` chọn mọi phần tử phù hợp được duyệt. Nếu điều kiện có thể trở lại true sau một phần tử false, hai thao tác không tương đương.

### 9.2. Unordered stream và parallel

Với unordered stream, không có một “tiền tố đầu” có ý nghĩa theo thứ tự nhìn thấy. Hợp đồng `takeWhile` cho phép chọn một tập con phù hợp theo quy tắc dành cho unordered stream; đừng diễn dịch kết quả như cắt tại một vị trí thời gian cụ thể. Trên ordered parallel stream, việc bảo đảm ranh giới tiền tố có thể tốn công việc đáng kể.

## 10. dropWhile không tự làm nguồn hữu hạn

`dropWhile(predicate)` trên ordered stream **bỏ tiền tố đầu còn thỏa**, rồi **chuyển tiếp tất cả phần tử còn lại**. Nó khác `takeWhile`:

~~~java
List<Integer> suffix = Stream.iterate(0, n -> n + 1)
        .dropWhile(n -> n < 5)
        .limit(3)
        .toList();

// [5, 6, 7]
~~~

Khi gặp 5, `dropWhile` ngừng bỏ phần tử. Nhưng nguồn sau đó **vẫn có thể vô hạn**, nên ở ví dụ phải dùng **limit(3)** để chỉ lấy ba phần tử.

Nếu bỏ limit:

~~~java
// KHÔNG CHẠY: phần còn lại vẫn vô hạn.
// Stream.iterate(0, n -> n + 1)
//       .dropWhile(n -> n < 5)
//       .toList();
~~~

Pipeline không hoàn tất bình thường khi cố materialize toàn bộ suffix.

Nếu predicate không bao giờ false:

~~~java
// KHÔNG CHẠY: không qua được tiền tố cần bỏ.
// Stream.generate(() -> "A")
//       .dropWhile("A"::equals)
//       .limit(1)
//       .toList();
~~~

**limit(1)** chờ một phần tử sau dropWhile, nhưng `dropWhile` vẫn loại mãi từng "A". Không phần tử nào đi đến limit. Đây là cùng kiểu bẫy như `filter(alwaysFalse).limit(1)`.

## 11. distinct rồi limit: số phần tử không phải số giá trị phân biệt

`distinct()` là intermediate operation **stateful**: nó phải theo dõi những giá trị đã gặp để loại trùng.

Một trường hợp kết thúc:

~~~java
List<String> one = Stream.generate(() -> "A")
        .distinct()
        .limit(1)
        .toList();

// [A]
~~~

Giá trị phân biệt đầu tiên có ngay, nên đủ một phần tử cho `limit(1)`.

Nhưng:

~~~java
// KHÔNG CHẠY: không có giá trị phân biệt thứ hai.
// Stream.generate(() -> "A")
//       .distinct()
//       .limit(2)
//       .toList();
~~~

Sau "A" đầu tiên, mọi "A" tiếp theo đều trùng và bị `distinct` bỏ. `limit(2)` không bao giờ nhận được phần tử thứ hai. Dù source đã sinh hàng triệu phần tử, **số lượng sau distinct chỉ là một**.

### 11.1. Rủi ro bộ nhớ

Khi có nhiều giá trị phân biệt, `distinct` có thể phải giữ trạng thái tập các giá trị đã gặp. Một pipeline trên nguồn rất lớn/vô hạn với terminal không thể kết thúc có thể vừa tiêu thụ CPU lâu vừa tăng bộ nhớ.

Không nên kết luận mọi pipeline `distinct().limit(k)` luôn cần lưu vô hạn: nếu k phần tử phân biệt xuất hiện sớm, pipeline có thể kết thúc. Vấn đề nằm ở khả năng **đạt đủ k giá trị phân biệt trong thời gian hữu hạn** và cách thực thi cụ thể.

## 12. sorted trước short-circuit: rào cản stateful

`sorted()` là intermediate operation **lazy nhưng stateful**: sắp xếp tổng quát cần biết thứ tự của toàn bộ tập đầu vào ở giai đoạn đó.

Trên nguồn hữu hạn:

~~~java
int smallest = Stream.of(9, 2, 5)
        .sorted()
        .findFirst()
        .orElseThrow();

// 2
~~~

`findFirst` chỉ cần một phần tử **sau sorted**, nhưng để xác định phần tử đầu theo thứ tự tăng dần, bước sort thường cần xem toàn bộ nguồn.

Với nguồn không kết thúc, mẫu:

~~~java
// KHÔNG CHẠY: sắp toàn bộ một nguồn không có điểm cuối.
// Stream.iterate(0, n -> n + 1)
//       .sorted()
//       .findFirst();
~~~

không phải cách an toàn để lấy số nhỏ nhất. Pipeline không có giới hạn đầu vào cho sorted; một sort tổng quát không có điểm kết thúc để xác định đã xét hết giá trị.

**Tránh phát biểu tuyệt đối về mọi tối ưu:** JVM có thể bỏ qua hoặc tối ưu những bước không ảnh hưởng một terminal nhất định, và nguồn đã có characteristic SORTED có thể được xử lý khác. Điều cần nhớ là **không có bảo đảm kết thúc** chỉ vì sau sorted có findFirst/limit.

### 12.1. Giới hạn trước sorted

~~~java
List<Integer> smallestFromFirstFive =
        Stream.iterate(0, n -> n + 1)
                .map(n -> 5 - n)
                .limit(5)
                .sorted()
                .toList();

// [1, 2, 3, 4, 5]
~~~

Bước `limit(5)` đặt **trước sorted**, nên sorted chỉ nhận năm phần tử (trong pipeline này). Terminal hoàn tất.

### 12.2. sorted().limit(k) không bằng limit(k).sorted()

Hai cách diễn đạt:

- `sorted().limit(k)`: chọn k phần tử nhỏ nhất **trong toàn bộ upstream** nếu sắp xếp hoàn tất.
- `limit(k).sorted()`: chỉ sắp **k phần tử đầu upstream**.

Chúng có thể cho kết quả khác nhau, ví dụ với `[7,1,9,3]`: cách thứ nhất trả `[1,3]`, cách thứ hai `[1,7]`.

**Không đổi thứ tự chỉ để tránh không kết thúc mà không kiểm tra yêu cầu nghiệp vụ.** Nếu cần cực trị trên **mọi phần tử của nguồn vô hạn**, bản thân câu hỏi thường thiếu điều kiện biên (thời gian, số bản ghi, một tập hữu hạn/điều kiện kết thúc) để có thể trả lời trong thời gian hữu hạn.

## 13. flatMap: một stream con cũng có thể chặn cả pipeline

`flatMap` cho phép một phần tử nguồn tạo ra một stream con. Vấn đề không chỉ nằm ở stream nguồn ngoài.

Ví dụ hữu hạn và an toàn:

~~~java
List<Integer> values = Stream.of(1, 2)
        .flatMap(n -> Stream.of(n, n * 10))
        .toList();

// [1, 10, 2, 20]
~~~

Nhưng nếu một phần tử đầu tạo **stream con vô hạn** và terminal đòi xử lý mọi phần tử, pipeline có thể không đến được các phần tử ngoài tiếp theo:

~~~java
// KHÔNG CHẠY:
// Stream.of("first", "second")
//       .flatMap(label -> Stream.generate(() -> label))
//       .toList();
~~~

Một `limit(3)` sau flatMap có thể khiến pipeline lấy ba phần tử đầu từ stream con đầu tiên rồi dừng; nhưng điều đó **không có nghĩa** phần tử "second" đã được xem xét.

Khi có yêu cầu “phải xử lý ít nhất một giá trị của mỗi nhóm”, **flatMap vô hạn** không tương đương với một vòng round-robin công bằng. Cần thiết kế cơ chế phân phối, giới hạn từng stream con, hoặc thuật toán có bảo đảm tiến triển phù hợp.

## 14. Một predicate/callback không trả về cũng gây không kết thúc

Ngay cả một nguồn hữu hạn cũng có thể bị treo nếu chính hành vi được truyền vào không kết thúc:

~~~java
// Phản ví dụ khái niệm; không chạy:
// boolean result = Stream.of(1).anyMatch(n -> {
//     while (true) { /* never returns */ }
// });
~~~

Vì predicate không trả true/false, `anyMatch` không có bằng chứng để quyết định. Do đó muốn chứng minh pipeline có thể kết thúc, phải xét:

1. Mỗi lời gọi mapper/predicate/supplier được thực thi có hoàn tất không?
2. Stream có đủ phần tử phù hợp trong thời gian hữu hạn không?
3. Các giai đoạn stateful có thể xuất đầu ra mà không cần nguồn kết thúc không?
4. Terminal có thể kết luận sau một số hữu hạn kết quả đầu vào không?

**Short-circuit không phải timeout, giới hạn CPU hoặc cơ chế hủy tác vụ bị treo.**

## 15. Chương trình Java 17 hoàn chỉnh — chỉ chạy các trường hợp kết thúc

Chương trình dưới đây cố ý **không thực thi bất kỳ pipeline vô hạn không kết thúc nào**. Mỗi nguồn vô hạn đều có một bằng chứng dừng sớm hoặc một giới hạn hữu hạn đạt được trong ví dụ.

Tạo file **InfiniteStreamShortCircuitDemo.java**:

~~~java
import java.util.List;
import java.util.Optional;
import java.util.stream.Stream;

public class InfiniteStreamShortCircuitDemo {
    public static void main(String[] args) {
        List<Integer> firstFive =
                Stream.iterate(0, n -> n + 1)
                        .limit(5)
                        .toList();

        List<Integer> evens =
                Stream.iterate(0, n -> n + 1)
                        .filter(n -> n > 0 && n % 2 == 0)
                        .limit(3)
                        .toList();

        Optional<Integer> firstSeven =
                Stream.iterate(0, n -> n + 1)
                        .filter(n -> n > 0 && n % 7 == 0)
                        .findFirst();

        boolean anyReady = Stream.generate(() -> "ready")
                .anyMatch("ready"::equals);

        boolean allLessThanFive =
                Stream.iterate(0, n -> n + 1)
                        .allMatch(n -> n < 5);

        boolean noneIsFive =
                Stream.iterate(0, n -> n + 1)
                        .noneMatch(n -> n == 5);

        List<Integer> prefix =
                Stream.iterate(0, n -> n + 1)
                        .takeWhile(n -> n < 4)
                        .toList();

        List<Integer> suffix =
                Stream.iterate(0, n -> n + 1)
                        .dropWhile(n -> n < 5)
                        .limit(3)
                        .toList();

        List<String> uniqueOne =
                Stream.generate(() -> "A")
                        .distinct()
                        .limit(1)
                        .toList();

        List<Integer> sortedBounded =
                Stream.iterate(0, n -> n + 1)
                        .map(n -> 5 - n)
                        .limit(5)
                        .sorted()
                        .toList();

        List<Integer> skippedThenLimited =
                Stream.iterate(0, n -> n + 1)
                        .skip(4)
                        .limit(2)
                        .toList();

        List<Integer> boundedSource =
                Stream.iterate(0, n -> n < 4, n -> n + 1)
                        .toList();

        System.out.println("first five: " + firstFive);
        System.out.println("evens: " + evens);
        System.out.println("first seven: "
                + firstSeven.orElse(-1));
        System.out.println("any ready: " + anyReady);
        System.out.println("all less than five: "
                + allLessThanFive);
        System.out.println("none is five: " + noneIsFive);
        System.out.println("takeWhile: " + prefix);
        System.out.println("dropWhile + limit: " + suffix);
        System.out.println("one distinct: " + uniqueOne);
        System.out.println("bounded sorted: " + sortedBounded);
        System.out.println("skip + limit: " + skippedThenLimited);
        System.out.println("bounded source: " + boundedSource);
    }
}
~~~

Biên dịch và chạy với **JDK 17 trở lên**:

~~~bash
javac InfiniteStreamShortCircuitDemo.java
java InfiniteStreamShortCircuitDemo
~~~

**Đầu ra dự kiến:**

~~~text
first five: [0, 1, 2, 3, 4]
evens: [2, 4, 6]
first seven: 7
any ready: true
all less than five: false
none is five: false
takeWhile: [0, 1, 2, 3]
dropWhile + limit: [5, 6, 7]
one distinct: [A]
bounded sorted: [1, 2, 3, 4, 5]
skip + limit: [4, 5]
bounded source: [0, 1, 2, 3]
~~~

### 15.1. Diễn giải kết quả

- **first five:** Có thể sinh đủ năm số đầu trong thời gian hữu hạn, nên limit làm pipeline kết thúc.
- **evens:** Filter cho ba số chẵn dương 2,4,6 đi qua sau hữu hạn bước, nên limit nhận đủ ba phần tử.
- **first seven:** FindFirst nhận được 7 từ filter, không cần xét tiếp nguồn.
- **any ready:** Điều kiện true ngay với phần tử đầu.
- **all less than five:** Gặp 5 làm predicate false, nên allMatch có thể trả false.
- **none is five:** Gặp 5 làm predicate true, nên noneMatch có thể trả false.
- **takeWhile:** Phần tử 4 làm điều kiện n<4 sai, xác lập ranh giới kết thúc tiền tố.
- **dropWhile + limit:** Sau khi bỏ các số 0..4, suffix vẫn có vô hạn số, nhưng limit chỉ lấy 5,6,7.
- **one distinct:** Chỉ cần một giá trị phân biệt là "A", có sẵn ngay.
- **bounded sorted:** Chỉ năm phần tử qua limit vào sorted, nên sort có đầu vào hữu hạn.
- **skip + limit:** Bỏ bốn số đầu, lấy hai số tiếp theo. Skip hữu hạn tự nó không làm nguồn vô hạn thành hữu hạn, nhưng limit phía sau tạo bound.
- **bounded source:** Overload ba đối số của Stream.iterate có điều kiện `n < 4` để **tự giới hạn nguồn**; nó khác overload hai đối số không có điều kiện dừng.

### 15.2. Vì sao chương trình không chạy các phản ví dụ?

Nếu chạy trực tiếp `filter(alwaysFalse).findFirst()`, `distinct().limit(2)` trên nguồn luôn là "A", hoặc `takeWhile(alwaysTrue).toList()`, tiến trình có thể chạy vô hạn và tiêu thụ tài nguyên. Vì vậy chúng được trình bày **dưới dạng code comment/đoạn phản ví dụ**, không đặt trong phương thức main của chương trình chạy được.

Không nên học “hành vi không kết thúc” bằng cách khởi chạy vô hạn rồi chờ xem máy có treo không. Có thể kiểm tra bằng lập luận về dữ liệu sinh ra và điều kiện dừng, hoặc dùng **nguồn hữu hạn mô phỏng** để quan sát số phần tử được yêu cầu.

## 16. Overload Stream.iterate có điều kiện dừng

Java 9+ có:

~~~java
Stream.iterate(seed, hasNext, next)
~~~

Ví dụ:

~~~java
List<Integer> finite = Stream.iterate(
                0,
                n -> n < 5,
                n -> n + 1)
        .toList();

// [0, 1, 2, 3, 4]
~~~

Đây là **nguồn hữu hạn khi predicate hasNext cuối cùng trở thành false**. Nếu predicate luôn true, dùng overload ba đối số vẫn có thể tạo nguồn không bao giờ kết thúc.

Lợi ích của dạng ba đối số là **điều kiện giới hạn nằm ngay trong nguồn**, giúp việc đọc code dễ nhận ra ranh giới. Tuy nhiên, nó chỉ thích hợp khi hasNext có thể quyết định điểm dừng và phép sinh tiếp theo có thể tiến đến điểm đó.

Đừng giả định một predicate có biểu thức trông giống giới hạn sẽ chắc chắn dừng. Chẳng hạn nếu `next` không làm giá trị tiến triển, hoặc giá trị bị tràn theo cách làm điều kiện không bao giờ false, pipeline vẫn có thể chạy mãi.

## 17. Khi nào có thể lập luận pipeline sẽ kết thúc?

Đối với một sequential stream có source và behavioral parameter đều không treo, có thể dùng bảng câu hỏi thực dụng:

| Pipeline | Cần chứng minh để có kết thúc bình thường |
| --- | --- |
| `source.limit(k).toList()` | Source sinh được k phần tử, hoặc tự kết thúc sớm |
| `source.filter(p).limit(k).toList()` | Có đủ k phần tử p=true sau hữu hạn nguồn đầu vào, hoặc source kết thúc |
| `source.findFirst()` | Phần tử đầu có thể được cung cấp, hoặc source kết thúc |
| `source.filter(p).findFirst()` | Có phần tử p=true sau hữu hạn bước, hoặc source kết thúc |
| `source.anyMatch(p)` | Xuất hiện p=true sau hữu hạn bước, hoặc source kết thúc |
| `source.allMatch(p)` | Xuất hiện p=false sau hữu hạn bước, hoặc source kết thúc |
| `source.noneMatch(p)` | Xuất hiện p=true sau hữu hạn bước, hoặc source kết thúc |
| `source.takeWhile(p).toList()` | Trên ordered stream, có phần tử đầu p=false sau hữu hạn bước, hoặc source kết thúc |
| `source.dropWhile(p).limit(k).toList()` | Bỏ được tiền tố và có đủ k phần tử phía sau sau hữu hạn bước, hoặc source kết thúc |
| `source.distinct().limit(k).toList()` | Có đủ k giá trị phân biệt sau hữu hạn bước, hoặc source kết thúc |
| `source.sorted().findFirst()` | Trước sorted có đầu vào hữu hạn hoặc thuộc trường hợp tối ưu được chứng minh an toàn; đừng giả định nguồn vô hạn sẽ kết thúc |

**Đây không phải công cụ chứng minh hình thức cho mọi Java program**. Nó là mô hình suy luận dựa trên semantics thông thường; các thao tác song song, nguồn concurrent, lỗi/exception, callback bị treo và các tối ưu của JDK có thể làm đường thực thi khác nhau. Đối với production, nên định nghĩa một **giới hạn hữu hạn hoặc điều kiện dừng có thể quan sát** thay vì chỉ hy vọng một giá trị sẽ xuất hiện.

## 18. Không kết thúc, lỗi và cạn tài nguyên là những trạng thái khác nhau

Một pipeline có thể:

1. **Hoàn tất bình thường** và trả kết quả.
2. **Ném exception** từ source, mapper, predicate hoặc terminal.
3. **Không hoàn tất** vì liên tục yêu cầu phần tử nhưng không có bằng chứng dừng.
4. **Cạn tài nguyên** (CPU, heap, file descriptor, connection...) trước khi hoàn tất.
5. **Bị hủy/ngắt từ bên ngoài** nếu ứng dụng có cơ chế quản lý tác vụ, nhưng Stream API không tự cung cấp một thời hạn chạy mặc định.

Ví dụ một `toList()` trên stream vô hạn có thể tăng bộ nhớ rồi ném `OutOfMemoryError`, chứ không nhất thiết “chạy mãi mãi với bộ nhớ ổn định”. Dù theo cách nào, đó đều **không phải pipeline hoàn tất thành công với kết quả mong muốn**.

Một pipeline có `anyMatch` cũng có thể ném lỗi từ predicate trước khi gặp một phần tử phù hợp. Vì vậy không được đánh đồng “được phép short-circuit” với “không thể thất bại”.

## 19. Timeout, cancellation và giới hạn kinh doanh

Nếu hệ thống làm việc với dữ liệu thực sự mở (event stream, network messages, queue, dữ liệu streaming lâu dài), cần **hợp đồng dừng ở tầng phù hợp**:

- **Giới hạn số bản ghi đầu vào**: lấy tối đa N bản ghi từ nguồn, sau đó xử lý một batch hữu hạn.
- **Giới hạn thời gian**: API nguồn hoặc tầng điều phối chịu trách nhiệm timeout; không có `Stream.limit(Duration)` chuẩn áp dụng cho mọi Stream<T>.
- **Deadline/cancellation**: dùng cơ chế hủy tác vụ, đóng tài nguyên và kiểm tra trạng thái hủy theo API nguồn/thư viện; không kỳ vọng một terminal short-circuit hủy được callback đang chặn vô thời hạn.
- **Giới hạn dữ liệu nghiệp vụ**: khoảng thời gian, ID cuối, partition, cursor hoặc điều kiện kết thúc có thể kiểm chứng.
- **Giới hạn tài nguyên**: tránh sort/collect toàn bộ một nguồn chưa có điểm cuối; kiểm soát memory, backpressure và số phần tử trong batch.

### 19.1. Không tự bịa “timeout” bằng limit

`limit(100)` giới hạn **số phần tử đi qua nó**, không giới hạn **thời gian chờ**. Nếu 100 phần tử không bao giờ xuất hiện vì filter hoặc nguồn bị kẹt, `limit(100)` không có cơ chế tự ngừng sau vài giây.

Để áp dụng timeout, có thể chạy một tác vụ trong executor có chính sách hủy, nhưng phải hiểu rằng **hủy một Future không chắc chấm dứt một thread đang chạy callback không hợp tác**. Một số thao tác I/O không tự phản hồi interruption; cần timeout ở chính API I/O, đóng tài nguyên, hoặc dùng thư viện stream/bất đồng bộ có cơ chế cancel/backpressure rõ.

### 19.2. Vì sao parallel không giải quyết được bài toán?

`parallel()` có thể tăng mức độ xử lý đồng thời nhưng **không biến điều kiện bất khả thi thành có thể đạt được**. Nếu Supplier luôn sinh "A" còn filter đòi "B", không có số thread hữu hạn nào sinh được "B" từ nguồn đó.

Với ordered stream, các thao tác như `findFirst`, `limit`, `takeWhile` có thể đòi phối hợp thứ tự và tăng chi phí khi parallel. Với các terminal ngắn mạch, tác vụ đã khởi chạy có thể tiếp tục một phần công việc sau khi nhánh khác có kết quả. Không viết test kỳ vọng mọi thread dừng ngay sau callback đầu tiên trả true.

## 20. Tránh side effect và trạng thái mutable trong predicate

Một Predicate phù hợp cho Stream nên **stateless, non-interfering**, không sửa nguồn và không phụ thuộc vào số lượt gọi.

Không nên viết:

~~~java
AtomicInteger counter = new AtomicInteger();

Predicate<Integer> everyThirdTest =
        n -> counter.incrementAndGet() % 3 == 0;
~~~

Đây là mảnh ghép minh họa có import `AtomicInteger` và `Predicate`. Quy tắc này không trả lời câu hỏi về giá trị n mà phụ thuộc **lịch sử gọi**. Thay terminal, thứ tự nguồn, mức parallelism hoặc tối ưu có thể làm số lượt kiểm tra thay đổi, dẫn tới kết quả bất ngờ.

Với nguồn vô hạn, một Predicate phụ thuộc trạng thái có thể vô tình tạo/loại điều kiện dừng, khó chứng minh khả năng kết thúc. Việc dùng `AtomicInteger` làm phép tăng thread-safe **không biến predicate thành stateless**.

Nếu cần “mỗi phần tử thứ ba” theo **vị trí**, hãy mô hình hóa chỉ số nguồn rõ ràng; nếu cần “sau 1000 lần thử thì bỏ cuộc”, đó là **chính sách giới hạn lượt** của tầng điều phối, không nên ẩn trong một predicate tùy ý.

### 20.1. `peek` không phải cơ chế báo cáo xử lý đầy đủ

~~~java
long count = List.of(1, 2, 3).stream()
        .peek(System.out::println)
        .count();
~~~

`count()` có thể dựa vào kích thước nguồn đã biết và không gọi `peek` khi không ảnh hưởng kết quả. Với terminal short-circuit, một số phần tử phía sau cũng có thể không được duyệt.

Không dùng `peek` để audit, ghi giao dịch, xác nhận xử lý mọi phần tử hoặc thay thế cơ chế retry. Tách hiệu ứng bắt buộc thành một bước nghiệp vụ có hợp đồng rõ ràng, có kiểm soát lỗi và trạng thái.

## 21. Cách kiểm thử an toàn mà không cố làm máy bị treo

### 21.1. Dùng nguồn hữu hạn để mô phỏng

Để thấy `filter(...).limit(3)` chỉ nhận hai phần tử phù hợp khi nguồn kết thúc:

~~~java
List<Integer> result = Stream.of(1, 2, 3, 4)
        .filter(n -> n % 2 == 0)
        .limit(3)
        .toList();

// [2, 4] vì nguồn đã hết.
~~~

Ở nguồn **hữu hạn**, limit có thể trả ít hơn ba phần tử khi upstream kết thúc. Điều này khác nguồn **vô hạn không sinh được phần tử thứ ba**: terminal có thể đợi mãi vì nó không hề biết rằng một giá trị phù hợp không bao giờ xuất hiện.

### 21.2. Kiểm thử kết quả, không chốt số lần callback nếu không được bảo đảm

Với `anyMatch`, kiểm thử true/false và nguồn rỗng theo hợp đồng. Với `findAny`, kiểm tra giá trị thuộc tập phù hợp; không buộc parallel findAny phải trả “phần tử đầu tiên”.

Với ví dụ minh họa short-circuit tuần tự, một AtomicInteger có thể giúp quan sát số lần predicate chạy. Nhưng số lần callback không phải invariant toàn cục của mọi pipeline và mode; test production nên xác minh **kết quả và chính sách dừng/giới hạn**, không phụ thuộc trace implementation.

### 21.3. Không chạy stress test nguồn vô hạn thiếu giới hạn

Không tạo một test kiểu:

~~~java
// KHÔNG CHẠY TRỰC TIẾP TRONG BỘ TEST:
// Stream.generate(() -> 1).filter(n -> n == 2).findFirst();
~~~

rồi kỳ vọng JUnit timeout tự “giải cứu” mọi tài nguyên. Thay vào đó, chứng minh điều kiện dừng bằng reasoning và test trên **nguồn hữu hạn**/fake source có cấu hình. Khi bắt buộc đo liveness của một thành phần có thể chặn, dùng test isolation và cơ chế timeout/cancellation thích hợp, không dùng một worker thread không thể hủy rồi để lại ảnh hưởng toàn bộ test suite.

## 22. Các lỗi thường gặp

| Lỗi | Điều gì thực sự xảy ra | Cách sửa |
| --- | --- | --- |
| Có `limit(n)` nên pipeline chắc chắn kết thúc | Upstream có thể không sinh đủ n phần tử | Giới hạn **nguồn đầu vào** hoặc xác lập khả năng có đủ n kết quả |
| `filter(alwaysFalse).findFirst()` sẽ trả Optional.empty | Nguồn vô hạn không hết nên không chứng minh được empty | Dùng nguồn hữu hạn/timeout thích hợp |
| `anyMatch` với predicate luôn false sẽ trả false | Chưa bao giờ thấy true, nguồn không hết | Xác định giới hạn tìm kiếm |
| `allMatch` luôn true trên nguồn vô hạn sẽ trả true | Cần biết mọi phần tử; không có điểm cuối | Giới hạn nguồn |
| `noneMatch` luôn false trên nguồn vô hạn sẽ trả true | Không thể kết luận “không có” khi còn phần tử mãi | Giới hạn nguồn |
| `takeWhile(alwaysTrue).toList()` sẽ dừng | Không có phần tử tạo biên kết thúc | Điều kiện biên khả đạt |
| `dropWhile` tự biến nguồn thành hữu hạn | Chỉ bỏ tiền tố, suffix vẫn có thể vô hạn | Thêm giới hạn phía sau |
| `distinct().limit(2)` trên nguồn chỉ có một giá trị | Không xuất hiện giá trị phân biệt thứ hai | Giới hạn đầu vào hoặc thay đổi yêu cầu |
| `sorted().findFirst()` chỉ cần một phần tử gốc | Sort tổng quát cần xét nhiều/toàn bộ phần tử | Giới hạn trước sorted hoặc dùng thuật toán phù hợp |
| `parallel()` chữa được mọi pipeline treo | Không sửa điều kiện dừng sai; thêm rủi ro điều phối | Thiết kế termination trước khi tối ưu |
| `limit(n)` là timeout | Limit đếm phần tử, không đếm thời gian | Timeout ở tầng nguồn/executor được kiểm soát |
| Lambda update counter để ghi nhận đủ phần tử | Callback có thể không chạy cho tất cả phần tử | Tách quy trình audit/processing |
| `toList()` trên nguồn vô hạn chỉ tốn thời gian | Có thể tiêu tốn RAM và thất bại | Không materialize nguồn chưa được chặn |
| Đưa `limit` trước `filter` mà không xem nghiệp vụ | Kết quả thay đổi | So sánh semantics và test |
| Chạy phản ví dụ không kết thúc trong main | Treo tiến trình/cạn tài nguyên | Chỉ minh họa bằng comment và lập luận |

## 23. Bài tập tự luyện

### Bài 1 — Nhận diện điều kiện dừng

Với nguồn `Stream.generate(() -> "A")`, những pipeline nào có thể hoàn tất bình thường?

~~~java
// (1)
Stream.generate(() -> "A").limit(3).toList();

// (2)
Stream.generate(() -> "A").filter("B"::equals).limit(1).toList();

// (3)
Stream.generate(() -> "A").distinct().limit(1).toList();

// (4)
Stream.generate(() -> "A").distinct().limit(2).toList();
~~~

**Đáp án:** (1) có thể hoàn tất với [A,A,A]; (3) có thể hoàn tất với [A]. (2) không có phần tử sau filter; (4) không có giá trị phân biệt thứ hai. **Không chạy (2) và (4) trực tiếp**.

### Bài 2 — Ba phép match

Với nguồn không bao giờ kết thúc và chỉ tạo số 1:

~~~java
Stream.generate(() -> 1)
~~~

Điều gì xảy ra nếu áp dụng `anyMatch(n -> n == 2)`, `allMatch(n -> n == 1)`, `noneMatch(n -> n == 2)`?

**Đáp án:** cả ba đều không có điểm dừng bình thường: anyMatch thiếu chứng cứ true, allMatch thiếu chứng cứ false, noneMatch cũng thiếu chứng cứ true. Kết quả logic có thể được con người suy ra từ mã Supplier, nhưng terminal của Java không tự chứng minh điều đó.

### Bài 3 — takeWhile và dropWhile

Xét nguồn vô hạn `Stream.iterate(0, n -> n+1)`:

- `takeWhile(n -> n < 3).toList()` → **[0,1,2]**, vì gặp 3 làm dừng.
- `dropWhile(n -> n < 3).limit(2).toList()` → **[3,4]**.
- `dropWhile(n -> n < 3).toList()` → không có điểm kết thúc bình thường vì suffix vẫn vô hạn.

### Bài 4 — Chọn top 5 từ nguồn vô hạn

Bạn muốn “năm số nhỏ nhất từ một luồng số không bao giờ kết thúc” bằng `sorted().limit(5)`. Vì sao cách viết này không đủ?

**Đáp án:** để chắc chắn có năm số nhỏ nhất toàn bộ luồng, phải biết không có giá trị nhỏ hơn xuất hiện về sau; nếu nguồn vô hạn không có ràng buộc khác, không thể quyết định bằng một tiền tố hữu hạn nói chung. Cần giới hạn cửa sổ dữ liệu theo N bản ghi/thời gian, hoặc thiết kế một bài toán khác có điều kiện biên và bằng chứng đúng.

### Bài 5 — Sửa API có nguy cơ treo

Một hệ thống muốn lấy tối đa 10 đơn đủ điều kiện từ event stream, nhưng stream có thể không bao giờ phát đơn hợp lệ:

~~~java
events.filter(Event::eligible).limit(10).toList();
~~~

**Gợi ý:** xác định trước yêu cầu “10 đơn hợp lệ, chờ tối đa bao lâu/bao nhiêu sự kiện?”; đưa giới hạn đầu vào qua một batch hữu hạn hoặc một API đọc có deadline/cancellation. Nếu chỉ đọc tối đa 1000 sự kiện, có thể viết `events.limit(1000).filter(Event::eligible).limit(10).toList()` trong ngữ cảnh Event và events phù hợp, nhưng kết quả có thể có ít hơn 10 đơn. Đó là **chính sách nghiệp vụ mới cần được chấp nhận**, không phải tối ưu tự động tương đương.

### Bài 6 — Viết kiểm thử không treo

Viết test cho điều kiện “chỉ tìm trong 20 phần tử đầu”, dùng `Stream.iterate(0,n->n+1).limit(20)` rồi `anyMatch(n -> n == 30)`. Kết quả phải là **false** vì nguồn đầu vào của terminal là hữu hạn và không chứa 30. Không kiểm thử bằng cách gọi `anyMatch(n -> n == 30)` trên một nguồn sinh mãi giá trị không phù hợp.

## 24. Ghi nhớ

**Ngắn mạch là một khả năng dừng sớm, không phải bảo đảm mọi pipeline trên nguồn vô hạn sẽ kết thúc.**

Hãy hỏi bốn câu trước khi gọi terminal trên nguồn chưa có điểm cuối:

1. **Terminal cần chứng cứ gì để trả kết quả?** Ví dụ anyMatch cần true, allMatch cần false hoặc nguồn hết.
2. **Upstream có cung cấp chứng cứ ấy trong hữu hạn bước không?** Một filter hoặc distinct có thể làm số phần tử đi tiếp ít hơn nhiều so với số phần tử đã sinh.
3. **Có bước stateful cản trở không?** Sorted trên đầu vào chưa giới hạn có thể không bao giờ phát phần tử đầu.
4. **Có giới hạn tài nguyên và thời gian ở đúng tầng không?** Limit không phải timeout; parallel không tự giải quyết liveness.

Dùng `limit`, `takeWhile`, `findFirst`, `anyMatch` đúng hoàn cảnh; với dữ liệu mở hoặc vô hạn, hãy **thiết kế ranh giới rõ ràng** cho nguồn hay cửa sổ xử lý. Chỉ khi khả năng cung cấp dữ liệu, tính hoàn tất của callback và điều kiện dừng đều phù hợp, thao tác ngắn mạch mới giúp pipeline hoàn tất một cách đáng tin cậy.
