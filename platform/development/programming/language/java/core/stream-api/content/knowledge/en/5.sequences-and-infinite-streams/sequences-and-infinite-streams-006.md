# Nhận diện pipeline không thể kết thúc trên nguồn vô hạn

Trong chương **Dãy số và Stream vô hạn** của **Java Stream API**, khả năng tạo ra dãy phần tử không giới hạn là một công cụ mạnh: ta có thể biểu diễn dữ liệu theo kiểu khai báo, ghép các thao tác `filter`, `map`, `reduce`, `collect` và chỉ xử lý phần cần thiết nhờ tính *lazy*. Nhưng điều đó cũng tạo ra một lớp lỗi nghiêm trọng: **pipeline chạy mãi vì không có điều kiện bảo đảm kết thúc**.

Bài này giải thích cách nhận diện nguy cơ đó từ **nguồn**, **thứ tự các thao tác trung gian**, **điều kiện dừng** và **terminal operation**. Các quy tắc cũng hữu ích khi xử lý Stream song song, collector, Spliterator và Stream Gatherers: mọi tối ưu hoặc mở rộng pipeline đều phải tuân thủ yêu cầu về số phần tử cần tiêu thụ để tạo ra kết quả.

## 1. Nguồn vô hạn không đồng nghĩa mọi pipeline đều vô hạn

Một nguồn Stream được gọi là *vô hạn* hoặc *không giới hạn* khi nó có thể tiếp tục sinh phần tử mãi mà không có điểm kết thúc tự nhiên.

~~~java
import java.util.stream.Stream;

Stream<String> repeated = Stream.generate(() -> "Java");

Stream<Integer> increasing = Stream.iterate(0, n -> n + 1);
~~~

- `Stream.generate(supplier)` gọi `supplier` để sinh các phần tử khi có nhu cầu; API tạo một Stream không giới hạn.
- `Stream.iterate(seed, next)` bắt đầu từ `seed` rồi liên tục tạo phần tử kế tiếp; phiên bản hai tham số không có điều kiện dừng.
- Trong cùng nhóm còn có các nguồn không giới hạn như `IntStream.generate(...)` và `Random.ints()` không truyền kích thước.

Các nguồn trên có thể bị giới hạn bằng thao tác trung gian:

~~~java
import java.util.List;
import java.util.stream.Stream;

List<String> firstThree = Stream.generate(() -> "Java")
        .limit(3)
        .toList();

System.out.println(firstThree); // [Java, Java, Java]
~~~

`limit(3)` tạo một giới hạn hữu hạn cho **số phần tử đầu ra**. Pipeline này có thể hoàn tất vì nguồn sinh được ba phần tử ngay khi cần.

Ngược lại, một danh sách hữu hạn vẫn có thể khiến chương trình tưởng như “đứng” khi biểu thức xử lý quá nặng, gặp I/O bị chặn hoặc có thao tác không bao giờ trả về. Bài này tập trung vào trường hợp cụ thể: **số phần tử cần lấy từ nguồn có thể là vô hạn**. “Chậm”, “bị chặn” và “không có điểm dừng về mặt logic” là những nguyên nhân khác nhau, cần phân biệt khi điều tra.

> **Ghi nhớ:** Chỉ biết nguồn vô hạn là chưa đủ để kết luận. Phải nhìn toàn bộ pipeline: nguồn → các thao tác trung gian theo đúng thứ tự → thao tác đầu cuối.

## 2. Laziness không tự tạo ra điều kiện kết thúc

Các thao tác trung gian như `map`, `filter`, `limit` thường được ghép thành pipeline *lazy*: việc khai báo pipeline không đồng nghĩa ngay lập tức duyệt qua các phần tử.

~~~java
import java.util.stream.Stream;

Stream<Integer> pipeline = Stream.generate(() -> 1)
        .map(n -> n + 1)
        .filter(n -> n > 0);

// Chưa có terminal operation: pipeline chưa được duyệt.
~~~

Khi terminal operation cần kết quả, pipeline bắt đầu kéo phần tử từ nguồn. Nếu terminal operation cần biết **toàn bộ** dữ liệu nhưng nguồn không bao giờ kết thúc, quá trình duyệt có thể kéo dài vô hạn.

~~~java
long total = Stream.generate(() -> 1)
        .count(); // Không có số phần tử cuối cùng để đếm.
~~~

Trên một nguồn `generate` vô hạn, `count()` không thể hoàn tất bằng cách duyệt hết. Điều này khác với `count()` trên nguồn hữu hạn đã biết kích thước, nơi JDK có thể tối ưu để không cần xử lý từng phần tử. Khả năng tối ưu ở nguồn hữu hạn không giúp `generate` trở thành nguồn hữu hạn.

Không nên lấy việc “đã gọi terminal operation” làm bằng chứng rằng terminal operation chắc chắn trả về. **Terminal operation kích hoạt xử lý; khả năng kết thúc phụ thuộc vào lượng dữ liệu nó buộc phải yêu cầu.**

## 3. Phân loại terminal operation theo điều kiện dừng

Cần phân biệt các thao tác **duyệt đến khi nguồn kết thúc** và các thao tác **có khả năng dừng sớm** (*short-circuit*).

| Terminal operation | Thường cần gì để trả về? | Nguy cơ với nguồn vô hạn |
| --- | --- | --- |
| `count()`, `sum()`, `reduce(...)`, `collect(...)` | Duyệt hết dữ liệu cần tổng hợp | Không hoàn tất nếu phần đầu pipeline vẫn sinh phần tử mãi. |
| `forEach(...)`, `forEachOrdered(...)` | Xử lý toàn bộ luồng | Không có điểm kết thúc nếu luồng còn vô hạn. |
| `min(...)`, `max(...)`, `toList()` | Xem toàn bộ dữ liệu đầu ra | Không thể hoàn tất khi số phần tử đầu ra là vô hạn. |
| `findFirst()`, `findAny()` | Tìm được một phần tử | Có thể dừng sớm, nhưng **không có phần tử phù hợp** thì có thể chờ mãi. |
| `anyMatch(predicate)` | Tìm được ít nhất một phần tử làm điều kiện đúng; hoặc nguồn kết thúc | Nếu không có phần tử nào thỏa trên nguồn vô hạn, thao tác có thể chạy mãi. |
| `allMatch(predicate)` | Tìm được một phần tử làm điều kiện sai; hoặc nguồn kết thúc | Nếu mọi phần tử đều đúng trên nguồn vô hạn, thao tác có thể chạy mãi. |
| `noneMatch(predicate)` | Tìm được một phần tử làm điều kiện đúng; hoặc nguồn kết thúc | Nếu mọi phần tử đều sai đối với predicate trên nguồn vô hạn, thao tác có thể chạy mãi. |

Ví dụ cùng một nguồn sinh `1` liên tục, các terminal operation cho kết quả rất khác nhau:

~~~java
import java.util.stream.Stream;

int first = Stream.generate(() -> 1)
        .findFirst()
        .orElseThrow();                      // Trả về 1

boolean exists = Stream.generate(() -> 1)
        .anyMatch(n -> n == 1);             // Trả về true

boolean allAreOne = Stream.generate(() -> 1)
        .allMatch(n -> n == 1);             // Không thể xác nhận hết

boolean noneAreTwo = Stream.generate(() -> 1)
        .noneMatch(n -> n == 2);            // Không thể xác nhận hết
~~~

Hai câu cuối có vẻ hiển nhiên về mặt toán học vì ta biết mã của supplier. Nhưng Stream API không biến tính chất của supplier thành một chứng minh logic để terminal operation tự kết thúc; nó đánh giá từng phần tử theo hợp đồng của thao tác.

### Bộ lọc làm thay đổi điều kiện tìm thấy

`findFirst()` có khả năng dừng sớm, nhưng muốn trả về, nó cần **một phần tử đi qua tất cả các bước phía trước**:

~~~java
import java.util.stream.Stream;

String found = Stream.generate(() -> "A")
        .filter(s -> s.equals("B"))
        .findFirst()
        .orElse("Không có"); // Không đến được "Không có"
~~~

Nguồn chỉ tạo ra `"A"` nên bộ lọc không bao giờ chuyển phần tử nào cho `findFirst()`. Phương thức `orElse` chỉ được gọi sau khi `findFirst()` trả về một `Optional`; nó **không** đóng vai trò timeout hoặc điều kiện thoát.

Cũng cần nhớ các terminal operation `findFirst()` và `anyMatch(...)` **không bảo đảm kết thúc trong mọi trường hợp**; chúng chỉ *có khả năng* dừng sớm khi điều kiện thích hợp xuất hiện.

## 4. Ba “bẫy” lớn trong thao tác trung gian

### 4.1. `filter` rồi `limit`: giới hạn đầu ra không bảo đảm tìm được đủ phần tử

~~~java
import java.util.stream.Stream;

var result = Stream.generate(() -> 1)
        .filter(n -> n == 2)
        .limit(5)
        .toList(); // Không hoàn tất: không có phần tử nào vượt qua filter.
~~~

`limit(5)` nghĩa là **lấy tối đa năm phần tử sau bộ lọc**, không phải chỉ kiểm tra tối đa năm phần tử của nguồn. Nếu cần xử lý tối đa năm phần tử **đầu vào**, hãy đưa `limit` lên trước `filter`:

~~~java
var result = Stream.generate(() -> 1)
        .limit(5)
        .filter(n -> n == 2)
        .toList(); // Kết thúc, kết quả []
~~~

Hai pipeline có **ngữ nghĩa khác nhau**:

- `filter(...).limit(5)`: cố lấy năm phần tử phù hợp, có thể cần đọc số lượng phần tử đầu vào không giới hạn.
- `limit(5).filter(...)`: chỉ xem năm phần tử đầu vào, kết quả có thể ít hơn năm.

Ngay cả khi dữ liệu *có thể* chứa phần tử phù hợp, nếu không có giới hạn về thời điểm chúng xuất hiện, thời gian hoàn tất vẫn không được bảo đảm.

### 4.2. `sorted` trước `limit`: cần xem toàn bộ nguồn mới biết phần tử nhỏ nhất

~~~java
import java.util.stream.Stream;

var result = Stream.iterate(0, n -> n + 1)
        .sorted()
        .limit(3)
        .toList(); // Không hoàn tất trên nguồn vô hạn.
~~~

`sorted()` là một thao tác trung gian **có trạng thái**. Để trả về kết quả sắp xếp tổng quát, nó cần thu thập đủ phần tử từ upstream. Với một nguồn không giới hạn và không có ranh giới ở phía trước, thao tác sắp xếp không nhìn thấy điểm kết thúc. Trường hợp này còn có thể tiêu tốn bộ nhớ ngày càng nhiều.

Đổi thứ tự nếu yêu cầu bài toán cho phép:

~~~java
var result = Stream.iterate(0, n -> n + 1)
        .limit(3)
        .sorted()
        .toList(); // [0, 1, 2]
~~~

Ở phiên bản thứ hai, `sorted()` chỉ cần sắp xếp ba phần tử. Tuy nhiên, `sorted().limit(3)` và `limit(3).sorted()` **không tương đương** trên nguồn bất kỳ: câu đầu muốn ba phần tử nhỏ nhất trong toàn bộ nguồn, câu sau chỉ sắp xếp ba phần tử đầu tiên.

### 4.3. `distinct` rồi `limit`: có thể không đủ giá trị khác nhau

~~~java
import java.util.stream.Stream;

var result = Stream.generate(() -> 1)
        .distinct()
        .limit(2)
        .toList(); // Không hoàn tất: chỉ có duy nhất giá trị 1.
~~~

`distinct()` giữ lại các phần tử phân biệt. Với nguồn chỉ phát `1`, sau phần tử đầu tiên, không bao giờ có phần tử thứ hai được chuyển tiếp. `limit(2)` không được thỏa.

~~~java
var result = Stream.generate(() -> 1)
        .limit(2)
        .distinct()
        .toList(); // [1], kết thúc.
~~~

Với dữ liệu hữu hạn, `distinct` vẫn có thể phải duy trì tập giá trị đã thấy. Trên luồng vô hạn có nhiều phần tử khác nhau, bộ nhớ lưu trạng thái của `distinct` có thể tăng không giới hạn; dùng `limit` đủ sớm giúp kiểm soát số lượng đầu vào.

## 5. `takeWhile`, `dropWhile` và điều kiện thực sự có thể đạt tới

Từ **Java 9**, Stream có `takeWhile` và `dropWhile`. Trên Stream có *encounter order*, chúng hoạt động theo tiền tố của dãy:

- `takeWhile(predicate)` lấy phần tử liên tiếp từ đầu cho đến phần tử đầu tiên **không** thỏa điều kiện.
- `dropWhile(predicate)` bỏ phần tử liên tiếp từ đầu cho đến phần tử đầu tiên **không** thỏa điều kiện, sau đó chuyển tiếp phần còn lại.

Ví dụ dừng được:

~~~java
import java.util.List;
import java.util.stream.Stream;

List<Integer> values = Stream.iterate(0, n -> n + 1)
        .takeWhile(n -> n < 5)
        .toList();

System.out.println(values); // [0, 1, 2, 3, 4]
~~~

Ở đây, phần tử `5` là **nhân chứng rõ ràng cho điều kiện dừng**. `takeWhile` nhận được phần tử khiến predicate trả về `false`, nên phía downstream biết dãy đã kết thúc.

Ví dụ không có nhân chứng:

~~~java
var values = Stream.generate(() -> 1)
        .takeWhile(n -> n == 1)
        .toList(); // Không hoàn tất.
~~~

Predicate luôn đúng, vậy `takeWhile` không bao giờ gặp điểm cắt; `toList()` lại muốn nhận toàn bộ phần tử được chuyển tiếp.

Trường hợp của `dropWhile` còn dễ gây nhầm lẫn hơn:

~~~java
var firstAfterDrop = Stream.generate(() -> 1)
        .dropWhile(n -> n == 1)
        .findFirst(); // Không hoàn tất: không có phần tử đầu tiên sau đoạn bị bỏ.
~~~

Nếu predicate luôn đúng, `dropWhile` liên tục bỏ phần tử và không truyền kết quả xuống `findFirst()`.

**Lưu ý với luồng unordered:** Java cho phép `takeWhile` và `dropWhile` chọn tập hợp phần tử theo hợp đồng khác với tiền tố cố định khi luồng không có encounter order. Khi chứng minh điều kiện dừng, hãy xem cả tính thứ tự và đặc điểm nguồn; không nên suy từ ví dụ luồng có thứ tự sang mọi trường hợp song song hoặc unordered.

## 6. Hạn chế nguồn ngay khi có thể

### 6.1. Tạo một dãy hữu hạn bằng `iterate` có predicate

Từ Java 9, `Stream.iterate(seed, hasNext, next)` chỉ sinh phần tử khi `hasNext` còn đúng. Đây là cách diễn đạt điều kiện dừng trực tiếp tại nguồn.

~~~java
import java.util.List;
import java.util.stream.Stream;

List<Integer> firstFive = Stream.iterate(
        0,
        n -> n < 5,
        n -> n + 1)
        .toList();

System.out.println(firstFive); // [0, 1, 2, 3, 4]
~~~

Khi muốn tạo một khoảng số nguyên hữu hạn, `IntStream.range(...)` cũng thể hiện biên rõ ràng:

~~~java
import java.util.stream.IntStream;

int sum = IntStream.range(0, 5).sum(); // 0 + 1 + 2 + 3 + 4 = 10
~~~

Các phương án này cho phép pipeline có điểm kết thúc xác định, không phụ thuộc vào việc kết quả lọc có tình cờ xuất hiện hay không.

### 6.2. Đặt giới hạn trước thao tác có thể kéo dữ liệu vô hạn

Giả sử cần kiểm tra tối đa 1.000 mẫu để tìm một giá trị phù hợp:

~~~java
import java.util.Optional;
import java.util.stream.Stream;

Optional<Integer> candidate = Stream.generate(() -> 1)
        .limit(1_000)
        .filter(n -> n == 2)
        .findFirst();

System.out.println(candidate); // Optional.empty
~~~

`limit(1_000)` bảo đảm pipeline chỉ yêu cầu tối đa 1.000 phần tử từ nguồn (trong pipeline tuần tự này), và terminal operation có thể trả về `Optional.empty()` nếu không có kết quả. Đặt `limit` *sau* `filter` sẽ thay đổi mục tiêu thành “tìm một số phần tử đạt điều kiện”, vốn không có biên đầu vào xác định.

Nếu muốn đặt giới hạn thời gian thực (*timeout*), cần dùng cơ chế hủy/giới hạn thời gian của tác vụ bao ngoài, phù hợp với loại nguồn dữ liệu. `limit` đếm **phần tử**, không đếm thời gian; một supplier bị chặn I/O vẫn có thể không trả về phần tử đầu tiên. Stream API cũng không cung cấp một terminal operation tổng quát có timeout tích hợp.

## 7. Chứng minh một pipeline có điểm kết thúc bằng bốn câu hỏi

Có thể kiểm tra theo trình tự sau, ngay cả khi chưa chạy mã.

### Câu hỏi 1: Nguồn có giới hạn hữu hạn không?

- `List.stream()`, `Stream.of(...)`, `IntStream.range(...)`: thông thường có số phần tử hữu hạn, rõ ràng.
- `Stream.generate(...)`, `Stream.iterate(seed, next)`, các overload không giới hạn của nguồn số ngẫu nhiên: không có điểm kết thúc tự nhiên.
- Nguồn đọc I/O hoặc bộ sinh do ứng dụng tạo: phải xem hợp đồng của nguồn, không suy đoán chỉ theo tên phương thức.

### Câu hỏi 2: Có giới hạn **đầu vào** trước thao tác nguy hiểm không?

Tìm `limit(n)`, `takeWhile(...)` hoặc predicate ngay tại nguồn trước các thao tác như `sorted`, `distinct`, `filter` có thể loại bỏ phần lớn dữ liệu.

Không chỉ tìm xem pipeline *có* `limit` hay không. Hãy đọc **đúng thứ tự**: giới hạn sau một thao tác cần vô hạn phần tử có thể chẳng bao giờ được chạm tới.

### Câu hỏi 3: Terminal operation cần “một chứng nhân” hay “đọc đến hết”?

- Nếu cần đọc đến hết, phải tìm được ranh giới hữu hạn của luồng đầu ra.
- Nếu có khả năng short-circuit, phải chứng minh sự kiện giúp dừng **chắc chắn xuất hiện** sau một lượng phần tử hữu hạn, hoặc chứng minh nguồn kết thúc.
- Một xác suất thành công dương trong dữ liệu ngẫu nhiên thường có thể làm thao tác kết thúc *với xác suất 1* trong mô hình lý tưởng, nhưng không bảo đảm số lượt thử tối đa. Bài toán cần giới hạn cứng thì phải đặt giới hạn thực tế.

### Câu hỏi 4: Có thao tác có trạng thái giữ lại toàn bộ đầu vào không?

`sorted` có thể cần đệm toàn bộ nguồn trước khi xuất phần tử; `distinct` giữ trạng thái các giá trị đã thấy; `collect` tích lũy dữ liệu và nhiều collector tạo collection. Ngay cả khi chương trình không bị kẹt vô hạn, nó có thể hết bộ nhớ trước khi cho kết quả.

Sơ đồ quyết định đơn giản:

~~~text
Nguồn có điểm kết thúc?
  ├─ Có ──> Các thao tác có kết thúc và tài nguyên đủ? ──> Có thể hoàn tất
  └─ Không
       ├─ Có giới hạn hữu hạn trước bước cần duyệt toàn bộ? ──> Xem lại độ an toàn của giới hạn
       └─ Không
            ├─ Terminal cần duyệt hết? ──> Có nguy cơ không kết thúc
            └─ Terminal short-circuit?
                 ├─ Có chứng cứ sẽ gặp điều kiện dừng? ──> Có thể kết thúc
                 └─ Không ──> Không bảo đảm kết thúc
~~~

Các nhánh “có thể hoàn tất” giả định supplier, predicate, mapper và thao tác I/O thực thi xong trong thời gian hữu hạn. Một lambda chạy vô hạn hoặc bị chặn có thể khiến cả pipeline hữu hạn không trả về.

## 8. So sánh nhanh các pipeline

Bảng sau giả định nguồn sinh phần tử tức thời, không phát sinh ngoại lệ và chạy tuần tự theo thứ tự thông thường.

| Pipeline từ nguồn vô hạn | Có kết thúc? | Giải thích |
| --- | --- | --- |
| `generate(() -> 1).limit(3).count()` | Có | Đã giới hạn số phần tử cần đếm. |
| `generate(() -> 1).count()` | Không | Không có điểm cuối để hoàn tất việc đếm. |
| `generate(() -> 1).findFirst()` | Có | Lấy được phần tử đầu. |
| `generate(() -> 1).filter(n -> n == 2).findFirst()` | Không | Không bao giờ có phần tử vượt qua bộ lọc. |
| `generate(() -> 1).filter(n -> n == 2).limit(3).toList()` | Không | Giới hạn đặt sau bộ lọc không đạt được. |
| `generate(() -> 1).limit(3).filter(n -> n == 2).toList()` | Có | Chỉ kiểm tra ba phần tử, trả danh sách rỗng. |
| `generate(() -> 1).distinct().limit(2).toList()` | Không | Chỉ có một giá trị phân biệt. |
| `generate(() -> 1).limit(2).distinct().toList()` | Có | Xử lý hai phần tử, nhận danh sách một phần tử. |
| `generate(() -> 1).sorted().limit(2).toList()` | Không | Sắp xếp phải chờ hết nguồn vô hạn. |
| `generate(() -> 1).limit(2).sorted().toList()` | Có | Sắp xếp một tập hữu hạn. |
| `generate(() -> 1).anyMatch(n -> n == 1)` | Có | Gặp phần tử thỏa ngay lập tức. |
| `generate(() -> 1).allMatch(n -> n == 1)` | Không | Không thể chứng minh mọi phần tử bằng cách duyệt đến hết. |
| `generate(() -> 1).noneMatch(n -> n == 1)` | Có | Gặp phần tử bác bỏ điều kiện ngay lập tức. |
| `generate(() -> 1).dropWhile(n -> n == 1).findFirst()` | Không | Mọi phần tử đều bị loại ở đầu luồng. |

Trong bảng, `generate(() -> 1)` là cách viết rút gọn của `Stream.generate(() -> 1)`; các dòng chứa `toList()` cần Java 16 trở lên.

## 9. Hiệu năng, parallel stream và giới hạn tài nguyên

Một pipeline có thể **kết thúc về mặt logic** nhưng vẫn cần quá nhiều thời gian hoặc bộ nhớ. Ví dụ `limit(1_000_000_000L)` là hữu hạn, nhưng nếu phía sau cần gom tất cả phần tử vào `List`, chi phí vẫn có thể vượt tài nguyên ứng dụng.

- **Bộ nhớ:** `sorted` và một số collector lưu dữ liệu; `distinct` lưu các khóa phân biệt đã thấy. `toList` và `Collectors.toList` giữ kết quả. Những thao tác này cần đánh giá về kích thước dữ liệu trước khi dùng.
- **Xử lý song song:** `parallel()` không tạo điều kiện dừng cho nguồn vô hạn. Trên luồng có encounter order, `limit`, `skip`, `takeWhile` hoặc `dropWhile` còn có thể tốn chi phí điều phối lớn khi chạy song song. Hãy kiểm tra tính đúng đắn và giới hạn trước khi tối ưu bằng song song.
- **Spliterator:** các đặc tính như `SIZED` mô tả kích thước đã biết/khả năng tính toán của nguồn, nhưng không phải nguồn nào cũng có kích thước hữu hạn. Một Spliterator tùy chỉnh báo sai đặc tính/kích thước có thể làm tối ưu hóa và kết quả không còn đúng.
- **Stream Gatherers (Java 24+):** một gatherer có thể tự giới hạn hoặc biến đổi dòng dữ liệu, nhưng không nên mặc định rằng bất kỳ gatherer nào cũng làm pipeline vô hạn kết thúc. Hãy xem hợp đồng về việc có thể dừng upstream và số phần tử đầu vào mà gatherer cần tiêu thụ.
- **Side effect:** dùng `peek` để quan sát tiến độ có thể hữu ích khi gỡ lỗi, nhưng không phải cơ chế bảo đảm tiến độ hay timeout. Các tối ưu của pipeline có thể bỏ qua việc xử lý từng phần tử ở một số trường hợp.

Để hệ thống vận hành bền vững, hãy đặt giới hạn sát nguồn khi yêu cầu cho phép; thiết kế xử lý kết quả theo từng phần nhỏ nếu có thể; và dùng cơ chế hủy, đóng tài nguyên, giới hạn thời gian ở cấp tác vụ khi nguồn có thể bị chặn.

## 10. Bài tập tự kiểm tra

**Bài 1 — Dự đoán khả năng kết thúc**

~~~java
var result = Stream.iterate(0, n -> n + 1)
        .filter(n -> n % 2 == 0)
        .limit(3)
        .toList();
~~~

**Đáp án:** Kết thúc, nhận `[0, 2, 4]`. Mặc dù nguồn vô hạn, có ít nhất ba số chẵn ở những vị trí hữu hạn và `limit(3)` dừng sau khi lấy đủ.

**Bài 2 — Sửa lỗi theo đúng ý nghĩa “tối đa 100 lượt kiểm tra”**

~~~java
var found = Stream.generate(() -> 1)
        .filter(n -> n == 2)
        .limit(100)
        .findFirst();
~~~

**Đáp án:** Đưa `limit` lên trước bộ lọc:

~~~java
var found = Stream.generate(() -> 1)
        .limit(100)
        .filter(n -> n == 2)
        .findFirst(); // Optional.empty
~~~

Bản gốc cố chờ các phần tử đã qua bộ lọc nên không có giới hạn về số lần gọi supplier. Bản sửa kiểm tra tối đa 100 phần tử đầu vào.

**Bài 3 — Vì sao `limit(5)` không cứu được pipeline?**

~~~java
var firstFive = Stream.generate(() -> 10)
        .sorted()
        .limit(5)
        .toList();
~~~

**Đáp án:** `sorted` phải thu nhận toàn bộ dữ liệu nguồn trước khi có thể xác định kết quả sắp xếp, trong khi `generate` không có điểm cuối. Nếu chỉ cần sắp xếp năm phần tử đầu tiên, dùng `limit(5).sorted()`; nếu cần năm phần tử nhỏ nhất của **toàn bộ** dãy vô hạn bất kỳ, bài toán đòi hỏi thêm ràng buộc về nguồn hoặc đặc tính dữ liệu.

**Bài 4 — Terminal operation dừng sớm có luôn kết thúc không?**

~~~java
boolean exists = Stream.generate(() -> "X")
        .anyMatch(s -> s.equals("Y"));
~~~

**Đáp án:** Không. `anyMatch` chỉ có thể dừng sớm khi gặp giá trị `"Y"`, còn nguồn luôn phát `"X"`. Muốn kiểm tra trong phạm vi hữu hạn, có thể dùng `limit(n)` trước `anyMatch`.

**Ghi nhớ cuối bài:** Muốn chứng minh một pipeline trên nguồn vô hạn kết thúc, phải xác định **ranh giới hữu hạn trước thao tác cần duyệt hết** hoặc **điều kiện short-circuit chắc chắn đạt được sau hữu hạn phần tử**. Thứ tự `filter`, `distinct`, `sorted`, `limit` và `takeWhile` có thể quyết định pipeline trả kết quả hay chạy mãi; chỉ thêm một terminal operation hoặc bật xử lý song song không tự giải quyết được vấn đề.
