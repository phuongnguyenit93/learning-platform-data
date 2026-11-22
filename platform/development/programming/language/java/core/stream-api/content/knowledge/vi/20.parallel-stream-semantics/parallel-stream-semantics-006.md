# Chi phí của sorted, distinct, skip, limit, takeWhile và dropWhile

> **Chương:** Ngữ nghĩa xử lý song song  
> **Module:** JAVA_STREAM_API  
> **Trọng tâm:** Nhận diện chi phí của các thao tác trung gian *có trạng thái* và thao tác chọn tiền tố trong Java Stream API, đặc biệt khi chuyển pipeline từ `stream()` sang `parallelStream()` hoặc gọi `parallel()`. Tìm cách tối ưu **mà không làm sai hợp đồng kết quả**.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích vì sao `sorted`, `distinct`, `skip`, `limit`, `takeWhile` và `dropWhile` không thể được đánh giá như một phép `map` độc lập trên từng phần tử.
2. Phân biệt **stateful intermediate operation**, **short-circuiting intermediate operation**, và **encounter order**.
3. Dự đoán kết quả trên Stream có thứ tự và hiểu mức tự do lựa chọn kết quả trên Stream không có thứ tự.
4. Nhận diện chi phí cần lưu trữ, phối hợp giữa các phân vùng, duyệt phần tử hoặc đồng bộ khi chạy song song.
5. Hiểu sự khác nhau giữa `filter` và `takeWhile`/`dropWhile`, kể cả trên dữ liệu chưa sắp xếp.
6. Đề xuất cách đặt `filter`, `distinct`, `sorted` và `limit` theo đúng yêu cầu, tránh những đổi thứ tự thao tác làm thay đổi kết quả.
7. Sử dụng `unordered()`, `SIZED`, `SUBSIZED` và nguồn có khả năng chia tốt khi thích hợp.
8. Viết bộ kiểm thử tính đúng và cách đo hiệu năng thực tế trước khi quyết định dùng parallel stream.

Các ví dụ dùng Java 17+. `sorted`, `distinct`, `skip`, `limit` và `parallelStream` đã có từ Java 8; `takeWhile` và `dropWhile` được bổ sung từ **Java 9**; `Stream.toList()` có từ Java 16. Các ví dụ áp dụng chung cho `Stream<T>` và, khi được nêu rõ, các Stream nguyên thủy như `IntStream`/`LongStream`.

---

## 1. Vấn đề: xử lý song song không chỉ là chia đều phần tử

Một pipeline chỉ có các biến đổi stateless thường dễ phân chia:

~~~java
import java.util.List;

List<Integer> source = List.of(2, 3, 4, 5, 6);

List<Integer> result = source.parallelStream()
        .filter(n -> n % 2 == 0)
        .map(n -> n * n)
        .toList();

System.out.println(result); // [4, 16, 36]
~~~

`filter` và `map` trên những phần tử độc lập không cần biết kết quả của **mọi phần tử khác** để quyết định giữ và biến đổi phần tử hiện tại.

Ngược lại:

- `sorted` cần xác lập **thứ tự toàn cục**, không chỉ sắp mỗi phân vùng.
- `distinct` phải biết một phần tử đã xuất hiện ở đâu khác hay chưa.
- `skip`/`limit` cần xác định những phần tử nào nằm trong **vùng bị bỏ** hoặc **vùng được lấy**.
- `takeWhile`/`dropWhile` trên Stream có thứ tự phụ thuộc ranh giới **tiền tố** (*prefix*) đầu tiên thỏa hoặc không thỏa điều kiện.

~~~text
Nguồn ORDERED: [a, b, c, d, e, f, g, h]
                     |
                 parallel()
                     |
           +---------+---------+
           |                   |
        [a,b,c,d]           [e,f,g,h]
           |                   |
      xử lý một nhánh      xử lý nhánh khác
           \                   /
            +--- cần phối hợp -+
                     |
                     v
              kết quả theo hợp đồng
~~~

Chỉ việc phân chia nguồn chưa đủ để hoàn thành những thao tác có ràng buộc toàn cục. Chúng có thể đòi hỏi bộ nhớ tạm, trao đổi dữ liệu, một lần gộp hoặc phối hợp thứ tự giữa các nhánh.

**Không có quy tắc “parallel luôn nhanh hơn”.** Chi phí phối hợp có thể lớn hơn lợi ích nhiều CPU, nhất là với nguồn nhỏ, nguồn I/O hoặc pipeline nhiều thao tác có trạng thái.

## 2. Ba khái niệm cần phân biệt trước khi đo

### 2.1. Stateful và stateless

| Loại | Ví dụ | Phụ thuộc vào phần tử khác? |
|---|---|---|
| Stateless intermediate | `map`, `filter` | Thông thường không, nếu lambda tuân thủ stateless/non-interfering |
| Stateful intermediate | `sorted`, `distinct` | Có: thứ tự hoặc các giá trị đã thấy |
| Stateful slicing | `skip`, `limit` | Có: vị trí/giới hạn của phần kết quả |
| Stateful prefix | `takeWhile`, `dropWhile` | Có: ranh giới tiền tố theo predicate |

Các thao tác có trạng thái vẫn là **intermediate operations**: việc gọi chúng chỉ cấu hình pipeline; terminal operation như `toList`, `count`, `findFirst` hay `sum` mới kích hoạt việc tiêu thụ nguồn.

### 2.2. Short-circuiting không có nghĩa miễn phí

Hai thao tác trong nhóm đang học được đặc tả là **short-circuiting intermediate operations**:

- `limit(n)` có thể ngắt pipeline khi đã lấy đủ `n` phần tử.
- `takeWhile(P)` có thể ngắt khi đã xác định phần tiền tố cần lấy.

`skip(n)` và `dropWhile(P)` không phải thao tác dừng sớm tổng quát: sau khi bỏ tiền tố, downstream vẫn có thể cần tất cả phần tử còn lại. `sorted()` cần xác định thứ tự trước khi phát kết quả được sắp; `distinct()` cần theo dõi các giá trị đã thấy.

Một downstream có `findFirst` hoặc `limit` có thể dừng **toàn pipeline** trong những trường hợp cụ thể, nhưng không nên suy ra mọi thao tác upstream sẽ duyệt ít phần tử hay không phải lưu đệm.

### 2.3. Encounter order không đồng nghĩa thứ tự chạy thread

Nguồn `List`, mảng hoặc `IntStream.range(...)` có encounter order xác định. Nguồn `HashSet` thông thường **không cam kết** encounter order.

~~~java
import java.util.List;

List<String> values = List.of("A", "B", "C", "D");

values.parallelStream().forEach(System.out::println);
// Thứ tự in không được bảo đảm.

List<String> collected = values.parallelStream().toList();
System.out.println(collected); // [A, B, C, D]
~~~

`toList()` duy trì encounter order nếu Stream có thứ tự, dù các thao tác trước đó có thể chạy đồng thời. `forEach` song song không bảo đảm thứ tự thực thi; `forEachOrdered` dành cho trường hợp cần áp dụng hành động terminal theo encounter order.

### 2.4. Ordered và unordered: câu hỏi về hợp đồng kết quả

`unordered()` bỏ ràng buộc encounter order ở tầng Stream; nó **không chủ động xáo trộn** dữ liệu. Nếu kết quả có thể là *bất kỳ* tập con hợp lệ mà không cần phần tử “đầu tiên”, bỏ ràng buộc thứ tự có thể mở cơ hội tối ưu. Nếu nghiệp vụ cần “10 phần tử đầu”, “bỏ 10 phần tử đầu” hoặc “đoạn đầu của log cho tới lỗi”, đừng bỏ thứ tự.

---

## 3. Bảng chi phí tổng quan

Bảng dưới đây mô tả **xu hướng**, không phải bảo đảm thời gian/bộ nhớ của một JDK cụ thể.

| Thao tác | Ngữ nghĩa chính | Chi phí điển hình ở nguồn tuần tự | Thách thức ở parallel ordered |
|---|---|---|---|
| `sorted()` | Sắp xếp toàn bộ theo natural order | Có thể cần giữ `n` phần tử; sắp xếp thường khoảng O(n log n) | Gộp các phần đã sắp, cần thứ tự toàn cục và bộ nhớ |
| `distinct()` | Giữ mỗi giá trị một lần theo `equals` | Theo dõi giá trị đã thấy; bộ nhớ tăng theo số giá trị duy nhất | Phối hợp loại trùng **và** giữ lần xuất hiện đầu tiên |
| `skip(n)` | Bỏ `n` phần tử đầu của encounter order | Duyệt qua phần bị bỏ trừ khi nguồn hỗ trợ bỏ qua hiệu quả | Xác định chính xác ranh giới giữa các phân vùng |
| `limit(n)` | Lấy tối đa `n` phần tử đầu | Có thể dừng sớm sau khi có đủ giá trị | Chọn đúng tiền tố, phối hợp/hủy công việc |
| `takeWhile(P)` | Lấy tiền tố dài nhất thỏa `P` | Có thể dừng tại phần tử đầu không thỏa | Phát hiện ranh giới đầu tiên theo thứ tự toàn cục |
| `dropWhile(P)` | Bỏ tiền tố dài nhất thỏa `P` | Duyệt đến phần tử đầu không thỏa, rồi chuyển tiếp phần còn lại | Xác định tiền tố cần bỏ trong nhiều phân vùng |

Hai chú ý đặc biệt:

1. **Chi phí bộ nhớ không luôn O(n)** cho mọi triển khai; `distinct` có thể dùng cấu trúc băm, `sorted` có thể chọn thuật toán/phân vùng thích hợp, còn `skip/limit` có thể tận dụng kích thước và `Spliterator`. Bảng mô tả nguyên nhân, không định nghĩa thuật toán nội bộ.
2. Chi phí xử lý phụ thuộc **vị trí thao tác trong pipeline**, đặc tính nguồn, `SIZED`/`SUBSIZED`, kích thước kết quả và terminal operation. Không đánh giá chỉ từ tên phương thức.

## 4. sorted: chi phí của thứ tự toàn cục

`sorted()` (hoặc `sorted(comparator)`) là **stateful intermediate operation**. Để bảo đảm phần tử đầu tiên trong kết quả thật sự nhỏ nhất theo comparator, một phép sắp tổng quát thường cần quan sát đủ dữ liệu hữu hạn trước khi phát kết quả hoàn chỉnh.

~~~java
import java.util.List;

List<Integer> values = List.of(9, 1, 7, 3, 5);

List<Integer> sorted = values.parallelStream()
        .sorted()
        .toList();

System.out.println(sorted); // [1, 3, 5, 7, 9]
~~~

Không có bảo đảm phải sắp theo thuật toán nào. Với nguồn và dữ liệu tổng quát, sắp xếp so sánh thường tốn **O(n log n)** phép so sánh và cần thêm bộ nhớ; xử lý song song có thể sắp từng phần rồi phối hợp/gộp để tạo thứ tự toàn cục.

### 4.1. sorted ổn định khi Stream có encounter order

Với `Stream<T>` có thứ tự, `sorted` bảo đảm **stable sort**: những phần tử được comparator coi là bằng nhau giữ thứ tự tương đối ban đầu. Với Stream không có thứ tự, không có bảo đảm về tính ổn định.

~~~java
import java.util.Comparator;
import java.util.List;

record Row(String code, int priority) {}

List<Row> rows = List.of(
        new Row("A", 2),
        new Row("B", 1),
        new Row("C", 2)
);

List<Row> sorted = rows.parallelStream()
        .sorted(Comparator.comparingInt(Row::priority))
        .toList();

System.out.println(
        sorted.stream().map(Row::code).toList()
); // [B, A, C]
~~~

`A` đứng trước `C` vì hai dòng có cùng `priority = 2` và nguồn `List` có encounter order.

Nếu muốn một thứ tự **được định nghĩa hoàn toàn, không lệ thuộc thứ tự đến trước khi đồng hạng**, hãy thêm tie-breaker:

~~~java
Comparator<Row> byPriorityThenCode =
        Comparator.comparingInt(Row::priority)
                  .thenComparing(Row::code);
~~~

### 4.2. sorted trên nguồn vô hạn không thể cho kết quả đầu tiên một cách tổng quát

~~~java
import java.util.stream.Stream;

// Không nên chạy: nguồn vô hạn không có bảo đảm
// sorted() có thể xác định phần tử nhỏ nhất để phát.
// Stream.iterate(0, n -> n + 1)
//         .sorted()
//         .findFirst();
~~~

Ngược lại, đặt một giới hạn **trước** `sorted` có thể tạo tập đầu vào hữu hạn:

~~~java
import java.util.List;
import java.util.stream.Stream;

List<Integer> result = Stream.iterate(10, n -> n - 1)
        .limit(5)
        .sorted()
        .toList();

System.out.println(result); // [6, 7, 8, 9, 10]
~~~

Nhưng `limit(5).sorted()` không mang cùng nghĩa với `sorted().limit(5)` trên một nguồn tổng quát.

### 4.3. sorted sớm hay muộn?

Nếu yêu cầu chỉ cần các giá trị hợp lệ rồi sắp chúng, thường có lợi khi **lọc trước khi sắp**:

~~~java
import java.util.List;

List<Integer> values = List.of(9, -1, 7, -3, 5, 2);

List<Integer> result = values.parallelStream()
        .filter(n -> n >= 0)
        .sorted()
        .toList();

System.out.println(result); // [2, 5, 7, 9]
~~~

`filter` giảm số phần tử đầu vào của `sorted`. Với predicate thuần độc lập và comparator phù hợp, việc chuyển `filter` lên trước có thể giữ cùng tập dữ liệu được sắp. Nếu predicate phụ thuộc **vị trí** hoặc **trạng thái thay đổi**, hoặc pipeline có `limit/skip/takeWhile` xen giữa, không được tự ý hoán đổi.

### 4.4. Cẩn trọng với sort chỉ để lấy vài phần tử

~~~java
import java.util.Comparator;
import java.util.List;

List<Integer> values = List.of(9, 1, 7, 3, 5);

List<Integer> topThree = values.stream()
        .sorted(Comparator.reverseOrder())
        .limit(3)
        .toList();

System.out.println(topThree); // [9, 7, 5]
~~~

Đây là kết quả đúng theo yêu cầu **ba phần tử lớn nhất**. Tuy vậy, `sorted` tổng quát có thể phải xử lý toàn bộ nguồn trước khi `limit` lấy ba phần tử. Với tập cực lớn và `k` rất nhỏ, thuật toán top-K dùng heap kích thước `k` hoặc collector phù hợp có thể giảm chi phí, nhưng phải thiết kế đúng comparator, tie-break và ngữ nghĩa dữ liệu.

**Không** đổi thành `limit(3).sorted(reverseOrder())` nếu mục tiêu vẫn là top-K toàn cục.

---

## 5. distinct: loại trùng và chi phí ghi nhớ giá trị đã thấy

`distinct()` dùng `Object.equals` (hoặc ngữ nghĩa tương đương cho primitive stream) để giữ mỗi giá trị duy nhất một lần.

~~~java
import java.util.List;

List<Integer> values = List.of(2, 1, 2, 3, 1, 4);

System.out.println(values.stream().distinct().toList());
// [2, 1, 3, 4]

System.out.println(values.parallelStream().distinct().toList());
// [2, 1, 3, 4]
~~~

Với Stream có encounter order, `distinct` **ổn định**: trong các phần tử bằng nhau, giữ phần tử xuất hiện **đầu tiên** theo encounter order. `Integer` trong ví dụ giúp dễ thấy thứ tự.

### 5.1. Nguồn càng nhiều giá trị khác nhau, trạng thái distinct có thể càng lớn

Một cách loại trùng điển hình sử dụng cấu trúc lưu các giá trị đã thấy, nên bộ nhớ có thể tăng theo số phần tử duy nhất. Với `n` phần tử và `u` giá trị duy nhất, trạng thái theo dõi có thể tỷ lệ với `u` (ngoài chi phí khác của pipeline).

Nếu các giá trị có `hashCode` phân bố tốt, cách làm dựa trên băm thường hiệu quả; nhưng không nên gán một độ phức tạp thời gian tuyệt đối cho mọi triển khai hoặc mọi lớp đối tượng.

### 5.2. Vì sao distinct song song có thứ tự có thể đắt?

Để giữ **lần xuất hiện đầu tiên**, framework phải biết một giá trị trong phân vùng sau có từng xuất hiện ở phân vùng trước hay không.

~~~text
Nguồn ORDERED:
[ A, B, A ] | [ C, B, D ] | [ D, E ]

Kết quả yêu cầu:
[ A, B, C, D, E ]

Không chỉ cần biết "đã thấy B":
còn phải biết B đầu tiên thuộc phân vùng nào.
~~~

Với parallel stream có thứ tự, `distinct` có thể đòi hỏi rào cản xử lý (*full barrier*), bộ nhớ tạm và phối hợp giữa các phần. Đây là một trong những ví dụ điển hình mà giữ encounter order làm chi phí song song tăng.

### 5.3. Khi không cần “bản ghi đầu tiên”, có thể bỏ ràng buộc thứ tự

~~~java
import java.util.List;
import java.util.Set;
import java.util.stream.Collectors;

List<Integer> values = List.of(2, 1, 2, 3, 1, 4);

Set<Integer> unique = values.parallelStream()
        .unordered()
        .distinct()
        .collect(Collectors.toSet());

System.out.println(unique.equals(Set.of(1, 2, 3, 4))); // true
~~~

`unordered()` cho phép `distinct` không phải giữ phần tử đầu tiên theo encounter order. Nhưng **không được dùng cách này** nếu người dùng cần chính bản ghi xuất hiện sớm nhất trong danh sách.

Nếu mục tiêu cuối cùng chỉ là một `Set` và không cần bất kỳ logic trung gian nào phụ thuộc thứ tự, `collect(Collectors.toSet())` cũng là lựa chọn trực tiếp; `distinct().collect(toSet())` đôi khi dư thừa.

### 5.4. DISTINCT là theo equals, không phải khóa nghiệp vụ

~~~java
import java.util.List;

record Product(long id, String name) {}

List<Product> products = List.of(
        new Product(7L, "Bút cũ"),
        new Product(7L, "Bút mới")
);

System.out.println(products.stream().distinct().count()); // 2
~~~

Hai `record` khác nhau ở `name` nên `equals` trả `false`. `distinct` không tự gộp theo `id`.

Nếu yêu cầu “mỗi ID lấy bản ghi có revision cao nhất”, hãy dùng collector `toMap` với merge function xác định theo nghiệp vụ, không dùng `distinct` và hy vọng nó xử lý khóa trùng.

### 5.5. Tránh đối tượng mutable làm thay đổi equals/hashCode khi đang duyệt

`distinct` có thể dựa trên `equals` và `hashCode`. Nếu trạng thái liên quan tới hai hàm ấy thay đổi trong lúc pipeline xử lý, kết quả có thể sai hoặc không ổn định.

Hàm hành vi Stream phải **non-interfering**, **stateless**; dữ liệu nguồn cũng cần được quản lý phù hợp. Không sửa object để “đánh dấu đã gặp” ngay trong `distinct` hay một `peek` trước đó.

---

## 6. skip: bỏ tiền tố theo vị trí

`skip(n)` bỏ **n phần tử đầu tiên** của Stream có encounter order. Nếu nguồn có ít hơn `n` phần tử, kết quả rỗng.

~~~java
import java.util.List;

List<String> values = List.of("A", "B", "C", "D", "E");

List<String> result = values.parallelStream()
        .skip(2)
        .toList();

System.out.println(result); // [C, D, E]
~~~

`skip` là stateful intermediate operation nhưng **không** phải thao tác short-circuiting tổng quát. Sau khi bỏ hai phần tử, downstream vẫn có thể cần cả phần còn lại.

### 6.1. Chi phí skip trên nguồn tuần tự

Với một `Iterator` chỉ có thể đi về phía trước, muốn bỏ `n` phần tử có thể phải gọi hàm duyệt n lần. Với nguồn có khả năng đánh chỉ số/phân chia chính xác, Stream có thể tận dụng thông tin để bỏ hẳn những đoạn không cần thiết.

Do đó không thể nói `skip(n)` luôn cần thực sự xử lý từng phần tử bị bỏ; chi phí phụ thuộc `Spliterator` và pipeline.

### 6.2. Chi phí skip trên parallel ordered

Để bỏ **đúng n phần tử đầu** theo thứ tự toàn cục, các phần xử lý phải cùng xác định ranh giới:

~~~text
Nguồn ORDERED:
     [A, B, C] | [D, E, F] | [G, H]
skip(4):
     bỏ A,B,C,D
     giữ E,F,G,H
~~~

Nếu biết chính xác kích thước từng phân vùng, việc tìm ranh giới có thể hiệu quả. Nếu nguồn không biết kích thước hoặc không chia đều, framework có thể phải phối hợp/buffer nhiều hơn.

### 6.3. Skip trên unordered stream

Nếu bỏ encounter order:

~~~java
import java.util.List;

List<Integer> source = List.of(10, 20, 30, 40, 50);

List<Integer> result = source.parallelStream()
        .unordered()
        .skip(2)
        .toList();

System.out.println(result.size()); // 3
// Không dự đoán chính xác ba giá trị nào được giữ.
~~~

Với Stream không có encounter order, `skip(2)` có quyền bỏ **bất kỳ hai phần tử nào** của nguồn có ít nhất hai phần tử. Đây là ngữ nghĩa khác với “bỏ hai phần tử đầu tiên trong List”.

### 6.4. Skip và offset pagination

~~~java
import java.util.List;

List<String> rows = List.of("A", "B", "C", "D", "E", "F");

int pageNumber = 1; // Đánh số từ 0
int pageSize = 2;

List<String> page = rows.stream()
        .skip((long) pageNumber * pageSize)
        .limit(pageSize)
        .toList();

System.out.println(page); // [C, D]
~~~

Trang kết quả chỉ ổn định nếu **thứ tự dữ liệu là ổn định**. Nếu nguồn là kết quả truy vấn không có sort rõ ràng, hoặc danh sách bị cập nhật giữa các lần đọc, `skip/limit` không tự đảm bảo phân trang nhất quán.

Với offset rất lớn hoặc nguồn từ cơ sở dữ liệu, đừng tải toàn bộ tập dữ liệu vào Java chỉ để bỏ hàng triệu phần tử; hãy cân nhắc phân trang ở nguồn hoặc keyset pagination. Đây là quyết định về kiến trúc nguồn, không chỉ về Stream.

---

## 7. limit: lấy tối đa n phần tử và có thể dừng sớm

`limit(n)` chọn tối đa `n` phần tử đầu theo encounter order, nếu Stream có thứ tự.

~~~java
import java.util.List;

List<Integer> values = List.of(2, 4, 6, 8, 10, 12);

List<Integer> firstThree = values.parallelStream()
        .limit(3)
        .toList();

System.out.println(firstThree); // [2, 4, 6]
~~~

`limit` là **short-circuiting stateful intermediate operation**. Khi đã xác định đủ phần tử cần lấy, downstream không còn cần phần còn lại, nhưng trong xử lý song song các nhánh khác có thể đã bắt đầu công việc.

### 7.1. Limit không có nghĩa mapper chỉ chạy n lần

~~~java
import java.util.List;

List<Integer> result = List.of(1, 2, 3, 4, 5, 6)
        .parallelStream()
        .map(n -> n * 10)
        .limit(2)
        .toList();

System.out.println(result); // [10, 20]
~~~

Kết quả có đúng hai phần tử đầu theo encounter order. Nhưng `parallel` có thể đã bắt đầu xử lý phần tử nằm ngoài tiền tố được giữ, nên không đếm số lần mapper được gọi làm dữ liệu nghiệp vụ. Những tối ưu được phép của Stream cũng có thể bỏ qua một số lambda trong pipeline khi không ảnh hưởng kết quả.

### 7.2. Unordered limit giảm ràng buộc nhưng thay đổi ý nghĩa

~~~java
import java.util.List;

List<Integer> values = List.of(10, 20, 30, 40, 50);

List<Integer> sample = values.parallelStream()
        .unordered()
        .limit(2)
        .toList();

System.out.println(sample.size()); // 2
// Không có bảo đảm sample là [10, 20].
~~~

Nếu yêu cầu là “chọn bất kỳ hai bản ghi” và phần tử không cần ưu tiên theo vị trí, đây có thể là lựa chọn hợp lệ. Nếu yêu cầu là “hai bản ghi đầu theo thời gian”, bỏ thứ tự là sai nghiệp vụ.

### 7.3. Limit đặt trước hay sau sorted?

~~~java
import java.util.Comparator;
import java.util.List;

List<Integer> values = List.of(2, 9, 4, 7, 1);

List<Integer> largestTwo = values.stream()
        .sorted(Comparator.reverseOrder())
        .limit(2)
        .toList();

List<Integer> largestAmongFirstTwo = values.stream()
        .limit(2)
        .sorted(Comparator.reverseOrder())
        .toList();

System.out.println(largestTwo);          // [9, 7]
System.out.println(largestAmongFirstTwo); // [9, 2]
~~~

**Hai pipeline có ý nghĩa khác nhau.** Hoán đổi `limit` và `sorted` có thể giảm chi phí sắp xếp nhưng đổi bài toán từ “top-K toàn cục” thành “sắp xếp K bản ghi đầu nguồn”.

### 7.4. limit(0) và n âm

~~~java
import java.util.stream.IntStream;

System.out.println(IntStream.range(0, 100).limit(0).count()); // 0

// Ném IllegalArgumentException:
// IntStream.range(0, 100).limit(-1);
~~~

`skip` cũng yêu cầu số phần tử cần bỏ không âm. Nếu `pageNumber * pageSize` có nguy cơ tràn `int`, chuyển sang phép tính `long` và kiểm tra đầu vào trước khi dùng làm offset.

---

## 8. takeWhile: lấy tiền tố dài nhất thỏa điều kiện

`takeWhile(P)` (Java 9+) không giống `filter(P)`.

Với nguồn **có encounter order**, nó chọn **tiền tố dài nhất gồm những phần tử liên tiếp ở đầu Stream** thỏa predicate. Khi gặp phần tử đầu tiên không thỏa, phần kết quả kết thúc.

~~~java
import java.util.List;

List<Integer> values = List.of(2, 4, 7, 8, 10);

List<Integer> prefix = values.stream()
        .takeWhile(n -> n % 2 == 0)
        .toList();

List<Integer> allEven = values.stream()
        .filter(n -> n % 2 == 0)
        .toList();

System.out.println(prefix);  // [2, 4]
System.out.println(allEven); // [2, 4, 8, 10]
~~~

`takeWhile` có thể dừng khi gặp `7`; `filter` phải tiếp tục xem các phần tử sau để tìm những số chẵn khác, trừ khi downstream còn thao tác dừng sớm riêng.

### 8.1. Chi phí takeWhile tuần tự

Với nguồn tuần tự và predicate đơn giản, việc xác định tiền tố thường cần đánh giá cho các phần tử thỏa và **phần tử đầu tiên không thỏa** (nếu có). Sau đó không cần tiếp tục đọc nguồn để tạo kết quả của riêng thao tác này.

Nếu mọi phần tử của nguồn hữu hạn đều thỏa, nó phải duyệt đến cuối để chứng minh tiền tố bao gồm toàn bộ nguồn. Với **nguồn vô hạn mà mọi phần tử đều thỏa**, phép thu thập tất cả thành List không kết thúc.

~~~java
import java.util.stream.IntStream;

List<Integer> finite = IntStream.iterate(0, n -> n + 1)
        .takeWhile(n -> n < 5)
        .boxed()
        .toList();

System.out.println(finite); // [0, 1, 2, 3, 4]
~~~

### 8.2. Vì sao takeWhile parallel ordered có thể rất đắt?

Giả sử nguồn được chia thành các nhánh:

~~~text
ORDERED: [1, 2, 3, 4] | [5, 6, 7, 8] | [9, 10]
Predicate: n < 7

Kết quả bắt buộc: [1, 2, 3, 4, 5, 6]

Nhánh bên phải có thể chạy trước, nhưng chỉ được quyết định
kết quả theo "phần đầu dài nhất" sau khi biết các nhánh trước.
~~~

Để giữ tiền tố dài nhất theo **encounter order**, framework cần biết vị trí đầu tiên không thỏa trên toàn nguồn. Đó là ràng buộc đồng bộ/sự phối hợp có thể làm `takeWhile` song song có thứ tự tốn kém hơn nhiều so với chạy tuần tự.

### 8.3. takeWhile trên unordered stream có hợp đồng khác

Với Stream **không có encounter order**, `takeWhile` có thể lấy **một tập con bất kỳ của các phần tử thỏa predicate**; không bắt buộc giữ tiền tố dài nhất của một thứ tự nguồn gốc. Nếu tất cả phần tử đều thỏa, tập con được lấy cũng không nhất thiết phải gồm mọi phần tử.

~~~java
import java.util.List;

List<Integer> values = List.of(1, 2, 3, 4, 5, 6);

List<Integer> selected = values.parallelStream()
        .unordered()
        .takeWhile(n -> n < 4)
        .toList();

// Mọi phần tử được chọn đều phải thỏa n < 4.
// Không dự đoán selected chính xác bằng [1, 2, 3].
System.out.println(selected);
~~~

Nếu bạn cần **tất cả** phần tử thỏa `n < 4` bất kể vị trí, hãy dùng `filter(n -> n < 4)`. Việc bỏ thứ tự trước `takeWhile` không biến nó thành `filter`.

### 8.4. takeWhile không tự sắp xếp dữ liệu

~~~java
import java.util.List;

List<Integer> values = List.of(1, 3, 8, 5, 6);

System.out.println(values.stream()
        .takeWhile(n -> n < 7).toList()); // [1, 3]
~~~

Phần tử `5` và `6` vẫn nhỏ hơn 7 nhưng nằm **sau** `8`, nên không thuộc tiền tố dài nhất. Nếu muốn kiểm tra “mọi số nhỏ hơn 7 ở bất kỳ đâu”, dùng `filter`. Nếu muốn chặn theo ngưỡng trên một dãy đã sắp, cần xác minh nguồn thật sự có thứ tự thích hợp.

---

## 9. dropWhile: bỏ tiền tố dài nhất, giữ phần còn lại

`dropWhile(P)` (Java 9+) bỏ **tiền tố dài nhất** của Stream có thứ tự mà các phần tử liên tiếp đầu nguồn thỏa predicate.

~~~java
import java.util.List;

List<Integer> values = List.of(2, 4, 7, 8, 10);

List<Integer> remaining = values.stream()
        .dropWhile(n -> n % 2 == 0)
        .toList();

List<Integer> onlyOdd = values.stream()
        .filter(n -> n % 2 != 0)
        .toList();

System.out.println(remaining); // [7, 8, 10]
System.out.println(onlyOdd);   // [7]
~~~

`dropWhile` không loại bỏ mọi phần tử thỏa `P`: sau khi gặp phần tử đầu tiên không thỏa, phần còn lại được giữ **nguyên theo dòng dữ liệu**.

### 9.1. Chi phí dropWhile tuần tự

`dropWhile` cần xác định ranh giới ở đầu nguồn, nhưng sau đó thường phải **tiếp tục chuyển các phần tử còn lại** cho downstream. Vì vậy nó **không phải short-circuiting intermediate operation** theo nghĩa `takeWhile`.

~~~java
import java.util.List;

List<Integer> values = List.of(1, 2, 7, 3, 4);

List<Integer> afterBoundary = values.stream()
        .dropWhile(n -> n < 5)
        .toList();

System.out.println(afterBoundary); // [7, 3, 4]
~~~

Phần tử `3` và `4` có thể thỏa `n < 5`, nhưng đã nằm sau phần tử phá vỡ tiền tố `7`, nên vẫn được giữ.

### 9.2. Parallel ordered đòi xác định ranh giới toàn cục

Nếu nhiều phân vùng được xử lý đồng thời, framework không thể quyết định tùy tiện loại những phần tử thỏa predicate ở giữa hay cuối. Nó cần biết tất cả phần tử thuộc **tiền tố** phải bỏ và giữ lại mọi phần tử nằm sau ranh giới đầu tiên.

Ràng buộc này có thể gây buffer, phối hợp phân vùng hoặc giảm mức song song hữu ích — nhất là khi dữ liệu đầu nguồn không biết kích thước hoặc khó tách.

### 9.3. dropWhile trên unordered stream

Với Stream không có encounter order, `dropWhile` có thể bỏ **một tập con bất kỳ của những phần tử thỏa predicate**. Nó không nhất thiết bỏ hết mọi phần tử thỏa.

~~~java
import java.util.List;

List<Integer> values = List.of(1, 2, 3, 4, 5);

List<Integer> result = values.parallelStream()
        .unordered()
        .dropWhile(n -> n < 4)
        .toList();

// Các phần tử không thỏa n < 4, ví dụ 4 và 5,
// không được loại chỉ bởi dropWhile.
// Các phần tử 1, 2, 3 có thể bị bỏ một phần hoặc toàn bộ.
System.out.println(result);
~~~

Nếu yêu cầu “giữ mọi phần tử có n >= 4”, dùng `filter(n -> n >= 4)` để diễn đạt điều đó, không dùng `unordered().dropWhile(n -> n < 4)`.

### 9.4. Trường hợp biên: tất cả hoặc không phần tử nào thỏa

| Nguồn hữu hạn ORDERED | `takeWhile(P)` | `dropWhile(P)` |
|---|---|---|
| Mọi phần tử thỏa `P` | Toàn bộ nguồn | Stream rỗng |
| Phần tử đầu không thỏa `P` | Stream rỗng | Toàn bộ nguồn |
| Nguồn rỗng | Stream rỗng | Stream rỗng |

Với nguồn **vô hạn** và mọi phần tử đều thỏa `P`, `dropWhile(P)` có thể không bao giờ phát ra phần tử nào cho downstream, vì ranh giới bỏ tiền tố không bao giờ xuất hiện.

---

## 10. So sánh sáu thao tác trên cùng dữ liệu

~~~java
import java.util.List;

List<Integer> source = List.of(4, 2, 2, 6, 3, 5, 8);
~~~

| Pipeline tuần tự có thứ tự | Kết quả | Giải thích |
|---|---|---|
| `source.stream().sorted()` | `[2, 2, 3, 4, 5, 6, 8]` | Sắp toàn bộ |
| `source.stream().distinct()` | `[4, 2, 6, 3, 5, 8]` | Giữ lần xuất hiện đầu tiên |
| `source.stream().skip(3)` | `[6, 3, 5, 8]` | Bỏ ba phần tử đầu |
| `source.stream().limit(3)` | `[4, 2, 2]` | Lấy ba phần tử đầu |
| `source.stream().takeWhile(n -> n % 2 == 0)` | `[4, 2, 2, 6]` | Dừng trước số lẻ đầu tiên (`3`) |
| `source.stream().dropWhile(n -> n % 2 == 0)` | `[3, 5, 8]` | Bỏ tiền tố chẵn, giữ cả `8` sau ranh giới |

Code đối chiếu:

~~~java
import java.util.List;

List<Integer> source = List.of(4, 2, 2, 6, 3, 5, 8);

System.out.println(source.stream().sorted().toList());
System.out.println(source.stream().distinct().toList());
System.out.println(source.stream().skip(3).toList());
System.out.println(source.stream().limit(3).toList());
System.out.println(source.stream().takeWhile(n -> n % 2 == 0).toList());
System.out.println(source.stream().dropWhile(n -> n % 2 == 0).toList());
~~~

Bảng này là **kết quả của Stream tuần tự có encounter order**; nếu thêm `unordered()`, đừng chép lại những kết quả dựa trên tiền tố hoặc lần xuất hiện đầu tiên như một khẳng định bắt buộc.

## 11. Vì sao SIZED và SUBSIZED quan trọng với skip/limit?

`Spliterator` mô tả nguồn dữ liệu cho Stream API.

- `ORDERED`: nguồn có encounter order.
- `SIZED`: số phần tử còn lại được biết chính xác theo hợp đồng.
- `SUBSIZED`: các Spliterator phát sinh qua `trySplit` cũng có kích thước chính xác.

~~~java
import java.util.Spliterator;
import java.util.stream.IntStream;

Spliterator.OfInt source = IntStream.range(0, 100).spliterator();

System.out.println(source.hasCharacteristics(Spliterator.ORDERED));  // true
System.out.println(source.hasCharacteristics(Spliterator.SIZED));    // true
System.out.println(source.hasCharacteristics(Spliterator.SUBSIZED)); // true
~~~

Khi nguồn có thể chia thành các phần liên tiếp có kích thước được biết, `skip`/`limit` có thể xác định ranh giới mà không cần duyệt toàn bộ từng phần bị bỏ.

~~~text
ORDERED và SUBSIZED:
[0..24] | [25..49] | [50..74] | [75..99]

skip(50).limit(10) có thể xác định:
  bỏ hai phân vùng đầu
  lấy 50..59 từ phần thứ ba
  không cần giữ các phần còn lại
~~~

Đây là **khả năng tối ưu**, không phải lời hứa mọi phiên bản JDK sẽ thực thi đúng theo sơ đồ này.

Ngược lại, một iterator từ nguồn I/O không biết số phần tử còn lại thường không có `SIZED/SUBSIZED`. Việc nhảy tới vị trí toàn cục trong parallel ordered trở nên khó hơn.

### 11.1. Không tự gắn SIZED/SUBSIZED để ép tăng tốc

Nếu viết custom Spliterator và báo sai kích thước, framework có thể tối ưu dựa trên thông tin sai. Ví dụ với `count()`, một pipeline có bảo đảm kích thước có thể không cần duyệt từng phần tử.

Chỉ công bố `SIZED` nếu `estimateSize()` có ý nghĩa chính xác theo hợp đồng. Chỉ công bố `SUBSIZED` nếu việc phân chia cũng bảo đảm được tính chính xác ấy.

### 11.2. Nguồn “có thứ tự” chưa đủ nói lên khả năng chia

Một danh sách và một iterator trên tệp có thể đều có thứ tự, nhưng:

- Danh sách thường có thể chia thành lát chỉ số có kích thước biết trước.
- Iterator trên tệp có thể chỉ đọc tiến tới, không biết số bản ghi cuối hoặc không thể chia hiệu quả.

Hai nguồn cùng `ORDERED` nhưng có chi phí `skip/limit` song song rất khác nhau. Đừng rút ra kết luận hiệu năng chỉ từ `ORDERED`.

---

## 12. Hoán đổi thứ tự thao tác: tối ưu nào giữ nghĩa?

Một nguyên tắc: **chỉ đổi vị trí thao tác khi có thể chứng minh kết quả không đổi theo yêu cầu**.

### 12.1. filter trước sorted: thường có ích

~~~java
import java.util.List;

List<Integer> values = List.of(9, -1, 3, -2, 7);

List<Integer> a = values.stream()
        .filter(n -> n >= 0)
        .sorted()
        .toList();

List<Integer> b = values.stream()
        .sorted()
        .filter(n -> n >= 0)
        .toList();

System.out.println(a); // [3, 7, 9]
System.out.println(b); // [3, 7, 9]
~~~

Với predicate thuần, tập phần tử được giữ không phụ thuộc thứ tự và không có thao tác dựa vào vị trí xen giữa, lọc trước giảm số phần tử cần sắp.

### 12.2. distinct trước sorted: có thể giảm số phần tử cần sắp

~~~java
import java.util.List;

List<Integer> values = List.of(7, 3, 7, 1, 3, 5);

List<Integer> result = values.stream()
        .distinct()
        .sorted()
        .toList();

System.out.println(result); // [1, 3, 5, 7]
~~~

Với `Integer` natural order, cách đặt `distinct` trước `sorted` thường hợp lý nếu nguồn có nhiều giá trị lặp. Nhưng việc loại trùng cũng tốn bộ nhớ và chi phí xử lý; nếu comparator không nhất quán với `equals` hoặc bài toán yêu cầu chọn đại diện cụ thể giữa các object, cần phân tích thứ tự và tie-break kỹ hơn.

### 12.3. limit trước sorted: thường đổi bài toán

~~~java
import java.util.List;

List<Integer> values = List.of(8, 1, 7, 2, 9);

System.out.println(values.stream()
        .sorted()
        .limit(2)
        .toList()); // [1, 2]

System.out.println(values.stream()
        .limit(2)
        .sorted()
        .toList()); // [1, 8]
~~~

Trường hợp đầu chọn **hai giá trị nhỏ nhất toàn nguồn**; trường hợp sau sắp **hai giá trị đầu tiên**. Không tối ưu chỉ dựa trên thời gian mà bỏ qua khác biệt này.

### 12.4. skip và distinct không hoán đổi tự do

~~~java
import java.util.List;

List<Integer> values = List.of(1, 1, 2, 3);

System.out.println(values.stream()
        .skip(1)
        .distinct()
        .toList()); // [1, 2, 3]

System.out.println(values.stream()
        .distinct()
        .skip(1)
        .toList()); // [2, 3]
~~~

`skip(1)` trên dữ liệu gốc bỏ một **vị trí**, còn `skip(1)` sau `distinct` bỏ một **giá trị duy nhất đầu tiên**. Hai câu hỏi không giống nhau.

### 12.5. takeWhile và filter không hoán đổi tùy ý

~~~java
import java.util.List;

List<Integer> values = List.of(1, 2, 9, 3, 4);

System.out.println(values.stream()
        .takeWhile(n -> n < 5)
        .filter(n -> n % 2 == 0)
        .toList()); // [2]

System.out.println(values.stream()
        .filter(n -> n % 2 == 0)
        .takeWhile(n -> n < 5)
        .toList()); // [2, 4]
~~~

Trong pipeline thứ hai, `filter` đã loại `9` trước khi `takeWhile` đánh giá ranh giới. Điều đó **làm thay đổi tiền tố**.

### 12.6. sorted + takeWhile trên dữ liệu đã sắp

~~~java
import java.util.List;

List<Integer> values = List.of(7, 1, 3, 9, 5);

List<Integer> small = values.stream()
        .sorted()
        .takeWhile(n -> n < 6)
        .toList();

System.out.println(small); // [1, 3, 5]
~~~

`sorted` khiến các giá trị dưới ngưỡng liên tiếp ở đầu, nên `takeWhile` có nghĩa gần với `filter(n -> n < 6)` trong dữ liệu đã sắp tăng. Tuy nhiên chi phí sắp toàn bộ nguồn có thể lớn; nếu chỉ cần **mọi** giá trị dưới ngưỡng và không cần sắp, dùng `filter`.

---

## 13. unordered(): khi nào giảm ràng buộc là an toàn?

`unordered()` là một intermediate operation **không phải phép xáo trộn**. Nó chỉ tuyên bố kết quả downstream **không cần giữ encounter order** của phần đầu vào.

Các trường hợp có thể cân nhắc:

- Chỉ cần một **tập giá trị duy nhất**, không quan trọng phần tử xuất hiện đầu tiên.
- Chỉ cần **bất kỳ n phần tử** để thử nghiệm, không có khái niệm “đầu tiên”.
- Đang chạy `distinct` song song trên dữ liệu lớn và thứ tự không mang nghĩa nghiệp vụ.
- Phép tổng hợp cuối là `Set` hoặc một cấu trúc thứ tự không quan trọng theo hợp đồng.

Các trường hợp **không** nên dùng:

- Lấy trang đầu tiên trong danh sách đã sắp theo thời gian.
- Đọc log từ đầu tới sự kiện lỗi, dùng `takeWhile`.
- Bỏ tất cả bản ghi trước checkpoint đầu tiên, dùng `dropWhile`.
- Giữ “bản ghi đầu tiên” trong các phần tử trùng nhau.
- Cần kết quả danh sách có thứ tự để so khớp, hiển thị hoặc xuất dữ liệu.

### 13.1. Unordered không bảo đảm tăng tốc

~~~java
import java.util.List;

List<Integer> values = List.of(8, 1, 8, 3, 1, 5);

List<Integer> result = values.parallelStream()
        .unordered()
        .distinct()
        .toList();
~~~

Có thể không có tăng tốc rõ rệt trên sáu phần tử vì overhead song song. Kết quả vẫn chứa đúng các giá trị duy nhất theo `equals`, nhưng không cam kết thứ tự.

Bỏ encounter order chỉ **cho phép** một số chiến lược thực thi rẻ hơn; framework không có nghĩa vụ chọn một cách nhất định.

---

## 14. Bài toán thực tế: lọc và xếp hạng đơn hàng

Giả sử có một danh sách đơn hàng, cần lấy **5 đơn đang hoạt động có tổng tiền cao nhất**, sắp theo giá giảm dần và sau đó theo ID tăng dần.

~~~java
import java.util.Comparator;
import java.util.List;

record Order(String id, long totalCents, boolean active) {}

List<Order> orders = List.of(
        new Order("O-01", 500, true),
        new Order("O-02", 900, true),
        new Order("O-03", 1200, false),
        new Order("O-04", 700, true),
        new Order("O-05", 400, true),
        new Order("O-06", 1500, true),
        new Order("O-07", 300, true),
        new Order("O-08", 1100, true)
);

Comparator<Order> ranking =
        Comparator.comparingLong(Order::totalCents)
                  .reversed()
                  .thenComparing(Order::id);

List<Order> topFive = orders.parallelStream()
        .filter(Order::active)
        .sorted(ranking)
        .limit(5)
        .toList();

System.out.println(topFive.stream().map(Order::id).toList());
// [O-06, O-08, O-02, O-04, O-01]
~~~

Vì sao thứ tự này hợp lý?

1. `filter` loại các đơn không hoạt động trước khi sắp, giảm đầu vào của `sorted`.
2. `sorted(ranking)` xác định thứ tự ưu tiên toàn cục, với tie-break rõ ràng.
3. `limit(5)` chọn đúng năm đơn đầu **sau khi sắp**.
4. `toList()` trả danh sách theo thứ tự kết quả của Stream có thứ tự.

**Không** di chuyển `limit(5)` lên trước `sorted`, vì sẽ chọn năm đơn từ thứ tự nguồn thay vì top năm theo tiêu chí xếp hạng.

### 14.1. Có nên dùng parallel ở đây?

Có thể, nhưng không mặc định. Với tám đơn hàng, chạy tuần tự thường đủ và overhead song song có thể cao hơn công việc sắp. Với hàng triệu đơn, còn phải đo chi phí sort và mức phân chia nguồn.

Nếu top-K là truy vấn thường xuyên trên tập rất lớn, một thuật toán chọn K phần tử bằng heap có thể phù hợp hơn sắp toàn bộ, nhưng phải kiểm tra thứ tự cuối, tie-break, xử lý trùng và khả năng gộp trung gian trước khi thiết kế collector tùy chỉnh song song.

---

## 15. Bài toán thực tế: log sự kiện và ranh giới đầu tiên

Giả sử `events` được bảo đảm **theo thời gian tăng dần**. Bạn muốn lấy các sự kiện trước marker `"STOP"`.

~~~java
import java.util.List;

List<String> events = List.of(
        "BEGIN",
        "READY",
        "WORK",
        "STOP",
        "CLEANUP",
        "END"
);

List<String> beforeStop = events.stream()
        .takeWhile(event -> !event.equals("STOP"))
        .toList();

List<String> afterStop = events.stream()
        .dropWhile(event -> !event.equals("STOP"))
        .toList();

System.out.println(beforeStop); // [BEGIN, READY, WORK]
System.out.println(afterStop);  // [STOP, CLEANUP, END]
~~~

`dropWhile` giữ **chính marker STOP** vì marker là phần tử đầu tiên không thỏa predicate bỏ tiền tố. Nếu cần bỏ cả marker:

~~~java
List<String> afterMarker = events.stream()
        .dropWhile(event -> !event.equals("STOP"))
        .skip(1)
        .toList();

System.out.println(afterMarker); // [CLEANUP, END]
~~~

Cách này chỉ đúng nếu “bỏ một phần tử đầu tiên sau dropWhile” chính là yêu cầu; nếu không có marker, toàn bộ Stream bị bỏ bởi `dropWhile`, và `skip(1)` nhận nguồn rỗng.

**Không thêm `unordered()`** vào hai pipeline trên: khái niệm “trước STOP” và “sau STOP” **chỉ có nghĩa khi thứ tự sự kiện được xác định**. Dùng parallel ordered có thể phải phối hợp để tìm ranh giới đầu tiên; với nhiều nguồn log phải đọc tuần tự, chạy tuần tự đôi khi là lựa chọn đúng và đủ nhanh.

---

## 16. Nguồn vô hạn và cách tránh pipeline không kết thúc

Các thao tác trung gian có thể tương tác khó lường về **khả năng hoàn tất** trên nguồn vô hạn.

| Pipeline trên nguồn vô hạn | Nguy cơ hoặc hành vi |
|---|---|
| `sorted().limit(10)` | Có thể không bao giờ phát phần tử đầu, vì sort cần xác lập thứ tự toàn cục |
| `distinct().limit(10)` | Có thể kết thúc nếu nguồn tạo ít nhất 10 giá trị khác nhau theo thời gian, nhưng không có bảo đảm chung |
| `skip(10).limit(5)` | Có thể kết thúc nếu nguồn cung cấp đủ phần tử |
| `takeWhile(P).toList()` | Có thể kết thúc khi xuất hiện phần tử đầu không thỏa; nếu không có ranh giới thì không |
| `dropWhile(P).limit(5)` | Có thể kết thúc nếu có ranh giới và đủ phần tử sau đó; nếu luôn thỏa P thì không |
| `limit(10).sorted()` | Có đầu vào hữu hạn cho sort; thường kết thúc nếu nguồn cung cấp đủ phần tử |

Minh họa nguồn hữu hạn được tạo từ nguồn có thể chạy mãi:

~~~java
import java.util.List;
import java.util.stream.Stream;

List<Integer> values = Stream.iterate(0, n -> n + 1)
        .skip(10)
        .limit(5)
        .toList();

System.out.println(values); // [10, 11, 12, 13, 14]
~~~

Khi đặt `sorted` trước `limit` trên nguồn vô hạn, một downstream dừng sớm **không tự biến sort thành phép tìm top-K có thể phát kết quả ngay**.

Nguồn vô hạn cũng đặt ra vấn đề tài nguyên và hủy tác vụ. Không xây vòng lặp side effect kéo dài trong lambda rồi kỳ vọng `limit` luôn có cơ chế ngắt vòng lặp đó.

---

## 17. Kiểm tra tính đúng khi đổi sequential sang parallel

Một pipeline song song chỉ đáng dùng khi **vẫn giữ nghĩa dữ liệu**. Hãy kiểm tra đúng từng thao tác, không chỉ so hai giá trị cuối trên một bộ dữ liệu nhỏ.

### 17.1. Bộ dữ liệu cố tình có trùng, trật tự khác và ranh giới giữa chừng

~~~java
import java.util.List;

List<Integer> source = List.of(4, 2, 2, 6, 3, 5, 8);

List<Integer> expectedDistinct = List.of(4, 2, 6, 3, 5, 8);
List<Integer> expectedTopTwo = List.of(8, 6);
List<Integer> expectedPrefix = List.of(4, 2, 2, 6);

List<Integer> distinct = source.parallelStream()
        .distinct()
        .toList();

List<Integer> topTwo = source.parallelStream()
        .sorted(java.util.Comparator.reverseOrder())
        .limit(2)
        .toList();

List<Integer> prefix = source.parallelStream()
        .takeWhile(n -> n % 2 == 0)
        .toList();

if (!expectedDistinct.equals(distinct)
        || !expectedTopTwo.equals(topTwo)
        || !expectedPrefix.equals(prefix)) {
    throw new AssertionError("Kết quả song song sai hợp đồng");
}
~~~

Nguồn là `List` có encounter order, vì vậy các kết quả mong đợi trong ví dụ là **cụ thể**. Với `unordered()`, đừng so danh sách vị trí cụ thể nếu hợp đồng cho phép nhiều đáp án.

### 17.2. Kiểm tra unordered bằng bất biến thay vì một thứ tự cố định

~~~java
import java.util.List;
import java.util.Set;
import java.util.stream.Collectors;

List<Integer> source = List.of(1, 1, 2, 3, 4, 5);

Set<Integer> distinct = source.parallelStream()
        .unordered()
        .distinct()
        .collect(Collectors.toSet());

if (!distinct.equals(Set.of(1, 2, 3, 4, 5))) {
    throw new AssertionError("Sai tập giá trị duy nhất");
}

List<Integer> sample = source.parallelStream()
        .unordered()
        .limit(3)
        .toList();

if (sample.size() != 3 || !source.containsAll(sample)) {
    throw new AssertionError("Sai cardinality hoặc giá trị");
}
~~~

Với nguồn có trùng, `containsAll` kiểm tra **tính thuộc tập** nhưng không bảo vệ số lần xuất hiện. Nếu multiplicity là điều kiện nghiệp vụ, cần kiểm tra theo **multiset** (bảng tần suất) hoặc thiết kế phép kiểm đủ mạnh.

### 17.3. Ca biên quan trọng

| Ca | Điều cần kiểm chứng |
|---|---|
| Nguồn rỗng | `sorted/distinct/skip/limit/takeWhile/dropWhile` cho kết quả rỗng phù hợp |
| `limit(0)` | Kết quả không có phần tử |
| `skip(0)` | Không bỏ phần tử |
| `skip(n)` với `n > size` | Kết quả rỗng |
| Dữ liệu toàn trùng | `distinct` giữ đúng một phần tử theo `equals` |
| Comparator có giá trị đồng hạng | `sorted` có bảo toàn thứ tự tương đối khi ORDERED? |
| Predicate đúng với toàn bộ nguồn | `takeWhile` lấy hết, `dropWhile` bỏ hết trên nguồn hữu hạn ORDERED |
| Predicate sai ở phần tử đầu | `takeWhile` rỗng, `dropWhile` giữ toàn bộ |
| Predicate đổi từ đúng sang sai rồi đúng lại | `takeWhile/dropWhile` xử lý **một ranh giới duy nhất**, không giống `filter` |
| `unordered()` | Chỉ kiểm tra bất biến được hợp đồng yêu cầu, không cố định tiền tố |
| Dữ liệu lớn, nhiều phân vùng | Kết quả đúng và không có trạng thái chia sẻ |
| Nguồn không `SIZED/SUBSIZED` | Không giả định chi phí bỏ qua phần tử thấp |
| Nguồn I/O | Bảo đảm đóng nguồn và xử lý ngoại lệ |

---

## 18. Đo hiệu năng đúng cách: benchmark khác với ví dụ in thời gian

Đừng dùng duy nhất:

~~~java
long start = System.nanoTime();
// pipeline chạy một lần
long elapsed = System.nanoTime() - start;
~~~

để kết luận “parallel nhanh hơn 2 lần”. Một lần đo có thể bị ảnh hưởng bởi **JIT warm-up**, GC, thread scheduling, máy đang có tải, cấu trúc nguồn, kích thước dữ liệu và cách kết quả được sử dụng.

### 18.1. Ma trận benchmark đề xuất

| Biến cần thử | Giá trị tham khảo |
|---|---|
| Kích thước `n` | Nhỏ, vừa, lớn (ví dụ 100, 100.000, 10.000.000 phần tử) |
| Kiểu nguồn | `ArrayList`, `IntStream.range`, nguồn iterator không biết size |
| Trạng thái thứ tự | ORDERED, hoặc `unordered()` nếu nghiệp vụ cho phép |
| Tỷ lệ trùng | 0%, thấp, cao |
| Vị trí ranh giới while | Đầu nguồn, giữa nguồn, gần cuối, không có |
| `skip/limit` | Bỏ/lấy ít, trung bình, nhiều |
| Thao tác sắp xếp | Natural order, comparator có tie-break và chi phí khác nhau |
| Chế độ | `stream()` vs `parallelStream()` |
| Đầu ra | Cùng kết quả nghiệp vụ hoặc cùng bất biến chấp nhận được |

Đối với ứng dụng quan trọng, dùng **JMH** và một thiết kế benchmark thích hợp. Cần bảo đảm kết quả được tiêu thụ, dữ liệu đầu vào tương đương, thời gian warm-up đủ và không tạo dữ liệu ngoài ý muốn ngay trong vùng đo nếu mục tiêu chỉ là đo pipeline.

### 18.2. Đo cái gì?

- **Throughput/latency** của toàn pipeline.
- **Allocation/GC**: nhiều thao tác stateful có thể cần buffer hoặc cấu trúc băm.
- **CPU utilization**: dùng nhiều core có hữu ích hay chỉ tăng contention?
- **Peak memory**: nhất là `sorted` và `distinct` trên nguồn lớn.
- **Tính đúng** của kết quả: sai dữ liệu thì mọi kết luận tăng tốc đều vô nghĩa.

### 18.3. Không lấy tốc độ ở pipeline khác nghĩa để so sánh

`unordered().limit(100)` có thể nhanh hơn `limit(100)` có thứ tự, nhưng **hai pipeline không bảo đảm chọn cùng 100 phần tử**. Chỉ coi đây là tối ưu nếu nghiệp vụ thật sự cho phép chọn bất kỳ 100 phần tử.

Tương tự, `filter(P)` và `takeWhile(P)` trả hai tập dữ liệu khác nhau trên nguồn không sắp phù hợp. Benchmark chúng như hai thuật toán “tương đương” là sai phương pháp nếu kết quả không cùng nghĩa.

---

## 19. Cách chọn API và chiến lược tối ưu an toàn

| Nhu cầu thật sự | API gợi ý | Điểm kiểm tra trước khi bật parallel |
|---|---|---|
| Sắp xếp toàn bộ | `sorted(comparator)` | Chi phí sort/bộ nhớ; comparator stateless; thứ tự tie-break |
| Lấy top-K toàn cục | `sorted(comparator).limit(k)` hoặc thuật toán top-K chuyên dụng | Không đổi thứ tự thành `limit(k).sorted()` |
| Loại trùng và giữ lần gặp đầu tiên | `distinct()` trên Stream ORDERED | Có thể có barrier và chi phí giữ encounter order |
| Chỉ cần tập giá trị duy nhất | `unordered().distinct()` hoặc `toSet()` | Thứ tự/đại diện không quan trọng |
| Bỏ n bản ghi đầu | `skip(n)` | Encounter order và nguồn `SIZED/SUBSIZED` |
| Lấy n bản ghi đầu | `limit(n)` | Chỉ có nghĩa “đầu” trên nguồn ORDERED |
| Chọn bất kỳ n phần tử | `unordered().limit(n)` | Nghiệp vụ thật sự cho phép tập con bất kỳ |
| Lấy tới phần tử đầu vi phạm điều kiện | `takeWhile(P)` | Định nghĩa ranh giới dựa trên encounter order |
| Bỏ mọi phần tử trước ranh giới | `dropWhile(P)` | Ranh giới và vị trí của phần tử đầu không thỏa |
| Lấy tất cả phần tử thỏa predicate | `filter(P)` | Không thay bằng `takeWhile` trên dữ liệu bất kỳ |
| Loại tất cả phần tử thỏa predicate | `filter(P.negate())` | Không thay bằng `dropWhile` trên dữ liệu bất kỳ |

Quy trình tối ưu:

1. **Viết hợp đồng kết quả bằng lời.** “Ba phần tử đầu”, “ba phần tử lớn nhất”, “ba phần tử bất kỳ” là ba yêu cầu khác nhau.
2. **Xác định encounter order** của nguồn và liệu nghiệp vụ có cần giữ thứ tự hay không.
3. **Ước lượng quy mô và phân bố:** số phần tử, tỷ lệ trùng, vị trí ranh giới, độ lớn phân trang.
4. **Giảm dữ liệu hợp lệ trước thao tác đắt**, ví dụ `filter` thuần trước `sorted` nếu không đổi nghĩa.
5. **Chọn dữ liệu và cấu trúc nguồn phù hợp**, khai thác `SIZED/SUBSIZED` khi có, không khai báo sai.
6. **Thử tuần tự trước**, xác định oracle độc lập và các ca biên.
7. **Thử song song**, kiểm tra kết quả theo đúng thứ tự/tập con mà hợp đồng yêu cầu.
8. **Chỉ thử `unordered()` khi hợp đồng cho phép**; kiểm tra lại toàn bộ các thao tác downstream.
9. **Benchmark có kiểm soát** và chỉ giữ parallel khi lợi ích vượt chi phí phối hợp/bộ nhớ.

---

## 20. Bài tập củng cố (kèm đáp án)

### Bài 1. Dự đoán kết quả

~~~java
import java.util.List;

List<Integer> numbers = List.of(5, 2, 5, 3, 2);

System.out.println(numbers.stream().distinct().toList());
System.out.println(numbers.stream().sorted().toList());
System.out.println(numbers.stream().skip(2).toList());
System.out.println(numbers.stream().limit(2).toList());
~~~

**Đáp án:** Lần lượt là `[5, 2, 3]`, `[2, 2, 3, 5, 5]`, `[5, 3, 2]`, `[5, 2]`. `distinct` giữ lần xuất hiện đầu trên Stream có thứ tự; `skip/limit` dựa vào encounter order của List.

### Bài 2. takeWhile khác filter

~~~java
import java.util.List;

List<Integer> values = List.of(2, 4, 7, 8, 10);

System.out.println(values.stream()
        .takeWhile(n -> n % 2 == 0).toList());

System.out.println(values.stream()
        .filter(n -> n % 2 == 0).toList());
~~~

**Đáp án:** `[2, 4]` và `[2, 4, 8, 10]`. `takeWhile` dừng ở `7`, còn `filter` tìm mọi số chẵn.

### Bài 3. dropWhile có xóa tất cả phần tử thỏa?

~~~java
import java.util.List;

List<Integer> values = List.of(1, 2, 7, 3, 4);

System.out.println(values.stream()
        .dropWhile(n -> n < 5).toList());
~~~

**Đáp án:** `[7, 3, 4]`. Chỉ bỏ `1, 2` ở **tiền tố**. Số `3, 4` sau ranh giới `7` vẫn được giữ.

### Bài 4. Có nên đổi limit và sorted?

**Đề:** Bài toán cần lấy hai điểm cao nhất của `[2, 9, 4, 7, 1]`. Có thể dùng `limit(2).sorted(reverseOrder())` để giảm chi phí không?

**Đáp án:** Không, vì sẽ chỉ sắp hai phần tử đầu `[2, 9]` thành `[9, 2]`; top hai toàn nguồn phải là `[9, 7]`. Phải xác định bài toán top-K đúng trước khi tối ưu.

### Bài 5. distinct song song có thứ tự đắt vì sao?

**Đề:** Nguồn `[A, B, A] | [C, B, D]` được phân vùng song song và phải giữ lần gặp đầu.

**Đáp án:** Phân vùng sau không được giữ `B` nếu `B` đã xuất hiện ở phân vùng trước. Do vậy cần phối hợp giữa các phân vùng để giữ đại diện đầu tiên, có thể tăng buffer và chi phí đồng bộ. Nếu chỉ cần tập các giá trị và không quan tâm đại diện đầu, cân nhắc bỏ ràng buộc thứ tự.

### Bài 6. unordered limit có bảo đảm lấy phần tử đầu?

**Đề:** `List.of(10,20,30,40).parallelStream().unordered().limit(2).toList()` có bắt buộc trả `[10,20]` không?

**Đáp án:** Không. Nó được phép chọn một tập con bất kỳ có hai phần tử nếu nguồn có đủ; vẫn phải tuân thủ số lượng và phần tử nguồn. Chỉ dùng khi thứ tự không có ý nghĩa nghiệp vụ.

### Bài 7. unordered takeWhile có thành filter?

**Đề:** Nếu gọi `unordered().takeWhile(n -> n < 10)` trên nguồn chứa cả số dưới và trên 10, có luôn lấy tất cả số dưới 10 không?

**Đáp án:** Không. Với Stream không có encounter order, `takeWhile` có thể chọn **một tập con bất kỳ** của những phần tử thỏa. Nếu yêu cầu lấy **tất cả** số nhỏ hơn 10, dùng `filter(n -> n < 10)`.

### Bài 8. skip và distinct có đổi chỗ được không?

~~~java
import java.util.List;

List<Integer> values = List.of(1, 1, 2, 3);
~~~

**Đáp án:** Không nói chung. `skip(1).distinct()` trả `[1, 2, 3]`, còn `distinct().skip(1)` trả `[2, 3]`. Bỏ một **phần tử gốc** khác bỏ một **giá trị duy nhất**.

### Bài 9. Vì sao SIZED/SUBSIZED giúp slicing?

**Đề:** Nguồn có 100 phần tử, chia thành bốn lát liên tiếp mỗi lát 25 phần tử. Cần `skip(50).limit(10)`.

**Đáp án:** Nếu Spliterator biết chính xác kích thước mỗi lát và bảo đảm thứ tự, framework có thể xác định hai lát đầu đều bị bỏ và lấy 10 phần tử đầu của lát thứ ba. Không phải đoán ranh giới bằng đếm từng phần tử của mọi lát. Đây là khả năng tối ưu, không phải quy tắc thời gian cố định.

### Bài 10. Nguồn vô hạn nào có thể không kết thúc?

**Đề:** Giải thích vì sao `Stream.iterate(0,n -> n+1).sorted().limit(5).toList()` không phù hợp.

**Đáp án:** `sorted` cần xác định thứ tự trên nguồn vô hạn trước khi phát kết quả tổng quát, nên có thể không bao giờ cho phần tử đầu. Đặt `limit(5)` trước `sorted` nếu yêu cầu thực sự là “sắp năm phần tử đầu”, hoặc thay thuật toán nếu mục tiêu là top-K của một nguồn có thể vô hạn.

### Bài 11. Benchmark có ý nghĩa không?

**Đề:** Một nhóm đo `limit(100)` và `unordered().limit(100)` trên nguồn có thứ tự rồi tuyên bố cách thứ hai “cùng kết quả nhưng nhanh hơn”.

**Đáp án:** Không thể khẳng định cùng hợp đồng kết quả: bản không thứ tự có thể lấy 100 phần tử khác. Phải hỏi nghiệp vụ có chấp nhận bất kỳ 100 phần tử hay không. Chỉ so thời gian khi hai pipeline đều đáp ứng yêu cầu kết quả.

### Bài 12. Chọn cách viết cho dữ liệu log

**Đề:** Danh sách sự kiện theo thời gian `[OPEN, READY, ERROR, RECOVER, CLOSE]`. Cần lấy những sự kiện từ đầu **trước ERROR**, không bao gồm ERROR.

**Đáp án:**

~~~java
import java.util.List;

List<String> events = List.of(
        "OPEN", "READY", "ERROR", "RECOVER", "CLOSE"
);

List<String> beforeError = events.stream()
        .takeWhile(s -> !s.equals("ERROR"))
        .toList();

System.out.println(beforeError); // [OPEN, READY]
~~~

Không dùng `unordered()` vì ranh giới “trước ERROR” cần encounter order.

---

**Ghi nhớ:** `sorted` phải xác lập **thứ tự toàn cục**, `distinct` phải giải quyết **trùng lặp giữa các phần**, `skip/limit` phụ thuộc **vị trí**, còn `takeWhile/dropWhile` phụ thuộc **ranh giới tiền tố**. Khi chạy song song, giữ encounter order có thể khiến chúng phải lưu đệm và phối hợp giữa các phân vùng; `unordered()` chỉ thích hợp nếu nghiệp vụ thật sự không cần thứ tự. Hãy xác định chính xác nghĩa kết quả, tận dụng nguồn `SIZED/SUBSIZED` khi có, kiểm chứng với bộ ca biên và benchmark trước khi chọn pipeline parallel.

