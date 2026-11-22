# Tác động của thứ tự phép toán đến kết quả và chi phí

Trong Java Stream API, việc thay đổi vị trí của `filter`, `map`, `distinct`, `sorted`, `skip` hoặc `limit` không chỉ làm mã trông khác đi. Có những phép hoán đổi **giữ nguyên kết quả nhưng thay đổi chi phí**, và có những phép hoán đổi **làm thay đổi chính dữ liệu được chọn**. Điều này đặc biệt quan trọng khi cần chọn top N, phân trang, loại bản ghi trùng, xử lý nguồn rất lớn hoặc chuyển sang parallel stream.

Bài học thuộc chương **Thứ tự, loại trùng và cắt lát** của module `JAVA_STREAM_API`. Ta sẽ xét sự tương tác giữa pipeline lazy, `filter`, `map`, `reduce`, `collect`, thứ tự gặp phần tử (*encounter order*), các thao tác giữ trạng thái, phép ngắn mạch và chi phí CPU/bộ nhớ. Mục tiêu là biết **khi nào được đổi vị trí hai thao tác, vì sao và cách kiểm chứng**.

Các ví dụ dùng `List.of(...)` (Java 9+); với Java 8 có thể thay bằng `Arrays.asList(...)`. Các thao tác cốt lõi như `filter`, `map`, `sorted`, `distinct`, `skip` và `limit` đã có từ Java 8; những ví dụ dùng `takeWhile`/`dropWhile` yêu cầu Java 9+.

## 1. Phân biệt thứ tự gặp phần tử với thứ tự thao tác

Pipeline mô tả một chuỗi biến đổi:

```text
source → filter(...) → distinct() → sorted(...) → skip(...) → limit(...) → collect(...)
           │               │             │          │           │
       lọc phần tử      loại trùng    sắp xếp    bỏ phần đầu  lấy tối đa N
```

Có hai khái niệm dễ nhầm:

- **Thứ tự thao tác** là vị trí của `filter`, `distinct`, `sorted`, `limit`... trong pipeline. Đổi thứ tự thao tác có thể đổi ý nghĩa của phép tính.
- **Thứ tự gặp phần tử** (*encounter order*) là thứ tự logic mà nguồn và các thao tác cam kết duy trì. `List.stream()` thường có thứ tự theo danh sách; `HashSet.stream()` không cam kết thứ tự đó. `sorted()` tạo thứ tự theo comparator, còn `unordered()` loại bỏ ràng buộc thứ tự gặp phần tử ở các bước tiếp theo.

Đừng đánh đồng encounter order với **thứ tự thực thi từng lambda**. Trong pipeline song song, các phần tử có thể được xử lý trên nhiều luồng và theo thứ tự khác thứ tự kết quả. Ngay cả pipeline tuần tự cũng có các thao tác như `sorted` phải thu thập nhiều phần tử rồi mới phát ra kết quả.

Một bảng định hướng:

| Thao tác | Tác động chính | Đặc điểm cần chú ý |
| --- | --- | --- |
| `filter` | Giữ hoặc bỏ từng phần tử | Stateless, lazy; có thể phải duyệt nhiều đầu vào để tìm đủ phần tử |
| `map` | Biến đổi giá trị từng phần tử | Stateless, lazy; có thể làm nhiều phần tử trở nên bằng nhau |
| `distinct` | Loại phần tử trùng theo `equals` | Stateful; với Stream có thứ tự, giữ lần xuất hiện đầu |
| `sorted` | Sắp xếp theo thứ tự tự nhiên/comparator | Stateful; thường cần xem toàn bộ nguồn hữu hạn |
| `skip(n)` | Bỏ `n` phần tử đầu theo encounter order | Stateful; phụ thuộc những thao tác đứng trước |
| `limit(n)` | Giữ tối đa `n` phần tử đầu | Stateful, short-circuiting; có thể dừng sớm tùy pipeline |
| `takeWhile` / `dropWhile` | Lấy/bỏ **tiền tố liên tiếp** thỏa điều kiện | Có từ Java 9; phụ thuộc mạnh vào encounter order |
| `unordered` | Bỏ ràng buộc encounter order | Không có nghĩa là xáo trộn phần tử; ảnh hưởng phép chọn và tối ưu |

Các terminal operation như `collect`, `count`, `findFirst` hoặc `anyMatch` kích hoạt pipeline. Bản thân việc lắp ghép thao tác trung gian thường chưa thực hiện duyệt; nhưng sự tồn tại của `sorted` hoặc `distinct` có thể khiến một terminal operation không tận dụng được khả năng dừng sớm.

## 2. filter và limit: chọn đủ N kết quả hay chỉ xét N đầu vào?

Cho một danh sách có thứ tự:

```java
import java.util.List;
import java.util.stream.Collectors;

List<Integer> numbers = List.of(7, 2, 9, 4, 6);

List<Integer> a = numbers.stream()
        .filter(n -> n % 2 == 0)
        .limit(2)
        .collect(Collectors.toList());

List<Integer> b = numbers.stream()
        .limit(2)
        .filter(n -> n % 2 == 0)
        .collect(Collectors.toList());

System.out.println(a); // [2, 4]
System.out.println(b); // [2]
```

- **`filter(...).limit(2)`** nghĩa là tìm **tối đa hai phần tử thỏa điều kiện** trong toàn nguồn. Pipeline có thể phải đi qua các phần tử bị loại trước khi lấy đủ hai phần tử.
- **`limit(2).filter(...)`** nghĩa là chỉ xem **hai phần tử đầu nguồn**, rồi lọc chúng. Số phần tử kết quả có thể ít hơn hai dù phía sau còn phần tử hợp lệ.

Không thể đẩy `limit` lên trước `filter` chỉ vì muốn xử lý ít dữ liệu hơn: như vậy thường thay đổi yêu cầu nghiệp vụ.

Khi dùng `findFirst`, đặt `filter` trước `findFirst` là cách tìm **phần tử đầu tiên thỏa điều kiện**; còn nếu muốn chỉ kiểm tra phần tử đầu tiên của nguồn, phải diễn đạt giới hạn một cách tường minh.

## 3. sorted và limit: top N toàn cục khác với sắp xếp N đầu vào

```java
List<Integer> scores = List.of(9, 2, 8, 1, 7);

List<Integer> smallestGlobal = scores.stream()
        .sorted()
        .limit(3)
        .collect(Collectors.toList());

List<Integer> sortedPrefix = scores.stream()
        .limit(3)
        .sorted()
        .collect(Collectors.toList());

System.out.println(smallestGlobal); // [1, 2, 7]
System.out.println(sortedPrefix);   // [2, 8, 9]
```

`sorted().limit(3)` tìm **ba giá trị nhỏ nhất của toàn bộ dữ liệu**. Với nguồn không biết trước thứ tự, `sorted` thường phải xem tất cả `N` phần tử, dùng bộ nhớ đáng kể và có chi phí sắp xếp điển hình `O(N log N)` trước khi có thể cho kết quả.

`limit(3).sorted()` chỉ giữ **ba phần tử đầu**, rồi sắp xếp chúng. Chi phí sắp xếp nhỏ hơn nhưng ý nghĩa là một truy vấn khác.

Tương tự, để tìm top ba lớn nhất:

```java
import java.util.Comparator;

List<Integer> top3 = scores.stream()
        .sorted(Comparator.reverseOrder())
        .limit(3)
        .collect(Collectors.toList());

System.out.println(top3); // [9, 8, 7]
```

Đối với tập dữ liệu rất lớn và chỉ cần vài phần tử đứng đầu, có thể cần thuật toán **top K bằng heap giới hạn K phần tử**, hoặc đẩy sắp xếp/giới hạn xuống nguồn dữ liệu có chỉ mục, thay vì luôn `sorted().limit(k)`. Không nên tự ý đổi thành `limit(k).sorted()` để tiết kiệm CPU vì kết quả sẽ khác.

## 4. distinct và limit: đủ N phần tử khác nhau hay loại trùng trong N đầu?

```java
List<Integer> ids = List.of(1, 1, 2, 3, 4);

List<Integer> uniqueFirst = ids.stream()
        .distinct()
        .limit(3)
        .collect(Collectors.toList());

List<Integer> limitedFirst = ids.stream()
        .limit(3)
        .distinct()
        .collect(Collectors.toList());

System.out.println(uniqueFirst);  // [1, 2, 3]
System.out.println(limitedFirst); // [1, 2]
```

Trong Stream **có encounter order**, `distinct` giữ **phần tử đầu tiên** trong mỗi nhóm bằng nhau. Sau khi loại trùng, `limit(3)` tìm đủ ba giá trị khác nhau nếu nguồn có ít nhất ba giá trị khác nhau. Đổi vị trí sẽ giới hạn số bản ghi thô trước khi loại trùng, nên có thể không thu được đủ ba giá trị.

`distinct()` thường cần một cấu trúc theo dõi các giá trị đã gặp. Kích thước bộ nhớ phụ thuộc số giá trị khác nhau đã xem (`U`); chi phí hash trung bình thường tăng theo lượng dữ liệu cần xét. Với ordered parallel stream, yêu cầu giữ phần tử gặp đầu tiên khiến `distinct` có thể tốn nhiều phối hợp và bộ đệm hơn.

**Nguy cơ với nguồn vô hạn:** `Stream.generate(() -> 1).distinct().limit(2)` không thể tìm thấy hai giá trị khác nhau; đừng chạy ví dụ này vì terminal operation có thể không kết thúc. `limit` đặt cuối pipeline không bảo đảm toàn bộ pipeline luôn hoàn tất.

## 5. map và distinct: kiểu giá trị sau biến đổi quyết định trùng lặp

`map` có thể biến hai giá trị ban đầu khác nhau thành cùng một giá trị. Vì vậy đổi `map` và `distinct` rất dễ gây sai:

```java
import java.util.Locale;

List<String> names = List.of("An", "AN", "Binh");

List<String> normalizeThenUnique = names.stream()
        .map(name -> name.toLowerCase(Locale.ROOT))
        .distinct()
        .collect(Collectors.toList());

List<String> uniqueThenNormalize = names.stream()
        .distinct()
        .map(name -> name.toLowerCase(Locale.ROOT))
        .collect(Collectors.toList());

System.out.println(normalizeThenUnique); // [an, binh]
System.out.println(uniqueThenNormalize); // [an, an, binh]
```

Với `map(...).distinct()`, trùng lặp được quyết định **sau chuẩn hóa**. Với `distinct().map(...)`, trùng lặp được quyết định **trước chuẩn hóa**, nên hai phần tử khác nhau ban đầu có thể thành hai bản sao giống nhau ở đầu ra.

Điều kiện để đổi vị trí mà vẫn giữ kết quả không chỉ là hàm `map` thuần (*pure*) và stateless: còn phải xem hàm có **bảo toàn quan hệ bằng nhau** hay không. Nếu phép ánh xạ làm hai giá trị khác nhau trở thành bằng nhau, hoán đổi không an toàn. Với dữ liệu object, `distinct()` dựa vào `equals`/`hashCode` của **kiểu đang có ở thời điểm đó**, không tự biết “trùng ID nghiệp vụ”.

Nếu muốn loại trùng theo khóa, hãy thể hiện rõ quy tắc bằng cấu trúc phù hợp, chẳng hạn map từ ID sang bản ghi với merge function xác định; việc dùng `distinct` trên toàn object có thể không đúng nghiệp vụ.

## 6. filter và distinct: trường hợp kết quả thường như nhau nhưng chi phí khác

Khi `filter` dùng một predicate cố định, không tác dụng phụ, kết quả không phụ thuộc vào những phần tử khác, và sự bằng nhau được xét nhất quán, ta thường có thể lọc trước hay sau loại trùng mà vẫn nhận cùng dãy giá trị:

```java
List<Integer> values = List.of(2, 2, 3, 3, 4, 4, 5);

List<Integer> filterThenDistinct = values.stream()
        .filter(n -> n % 2 == 0)
        .distinct()
        .collect(Collectors.toList());

List<Integer> distinctThenFilter = values.stream()
        .distinct()
        .filter(n -> n % 2 == 0)
        .collect(Collectors.toList());

System.out.println(filterThenDistinct); // [2, 4]
System.out.println(distinctThenFilter); // [2, 4]
```

Đưa `filter` lên trước có thể giảm số phần tử phải đưa vào cấu trúc loại trùng. Nếu predicate rẻ và loại bỏ phần lớn dữ liệu, đây thường là cách tốt. Nhưng không phải lúc nào cũng tiết kiệm: nếu predicate tốn kém và nguồn có rất nhiều bản sao, loại trùng trước có thể giảm số lần đánh giá predicate.

Ví dụ: với một triệu bản ghi nhưng chỉ có mười ID khác nhau, một phép kiểm tra mạng cho mỗi ID (dù nhìn chung không nên thực hiện I/O trong predicate) có chi phí khác hẳn với một phép toán `n % 2`. Cách giải thực tế có thể là gom ID rồi xử lý theo lô, thay vì tối ưu vị trí `filter` một cách máy móc.

**Điều kiện quan trọng:** nếu predicate phụ thuộc trạng thái thay đổi, thời gian hoặc tác dụng phụ, việc di chuyển nó có thể thay đổi kết quả. Với Stream API, các hàm hành vi nên stateless và không can thiệp vào nguồn; chỉ bàn chuyện hoán đổi khi hợp đồng này được giữ.

## 7. filter, map và chi phí của phép biến đổi

Một phép biến đổi đắt đỏ nên được áp dụng cho **ít phần tử nhất có thể**, miễn yêu cầu lọc vẫn đúng.

```java
List<Integer> raw = List.of(-2, 0, 1, 5, 8);

// "Chuẩn bị" ở đây chỉ là ví dụ cho phép tính có chi phí.
List<String> result = raw.stream()
        .filter(n -> n > 0)
        .map(n -> "item-" + n)
        .collect(Collectors.toList());

System.out.println(result); // [item-1, item-5, item-8]
```

Đặt `filter(n -> n > 0)` trước `map` tránh tạo chuỗi cho số không hợp lệ. Nhưng nếu điều kiện lọc được định nghĩa trên **kết quả đã biến đổi**, không thể tùy ý chuyển nó lên trước:

```java
List<String> codes = List.of(" A ", " ", "B", "  C ");

// Lọc sau khi chuẩn hóa, vì điều kiện dựa vào chuỗi đã trim.
List<String> cleaned = codes.stream()
        .map(String::trim)
        .filter(s -> !s.isEmpty())
        .collect(Collectors.toList());

System.out.println(cleaned); // [A, B, C]
```

Cần phân biệt phép biến đổi **đổi kiểu dữ liệu**, **đổi ý nghĩa dữ liệu** hoặc **tăng/giảm cardinality**. Chỉ khi predicate có thể diễn đạt tương đương trên đầu vào ban đầu và hàm ánh xạ an toàn, stateless thì việc chuyển `filter` lên trước mới đáng cân nhắc.

## 8. skip, limit và phân trang: thứ tự quyết định trang nào

Dùng `skip(offset).limit(pageSize)` để cắt một cửa sổ trong dãy đã xác định thứ tự:

```java
List<String> rows = List.of("A", "B", "C", "D", "E", "F");

List<String> page = rows.stream()
        .skip(2)
        .limit(3)
        .collect(Collectors.toList());

System.out.println(page); // [C, D, E]
```

Đảo thành `limit(3).skip(2)` chỉ giữ ba phần tử đầu rồi bỏ hai phần tử trong số đó: kết quả `[C]`. Hai pipeline không tương đương.

Vị trí `skip` so với `filter` cũng rất quan trọng:

```java
List<Integer> data = List.of(1, 2, 3, 4, 5, 6);

List<Integer> filteredPage = data.stream()
        .filter(n -> n % 2 == 0)
        .skip(1)
        .collect(Collectors.toList());

List<Integer> rawPage = data.stream()
        .skip(1)
        .filter(n -> n % 2 == 0)
        .collect(Collectors.toList());

System.out.println(filteredPage); // [4, 6]
System.out.println(rawPage);      // [2, 4, 6]
```

Nếu nghiệp vụ là “phân trang **các bản ghi thỏa điều kiện**”, thứ tự thông dụng là:

```text
source → filter(điều kiện) → sorted(thứ tự ổn định) → skip(offset) → limit(pageSize)
```

Khi `skip`/`limit` đứng trước `sorted`, bạn chỉ đang sắp xếp một đoạn của dữ liệu nguồn, không tạo “trang thứ N theo thứ tự toàn cục”.

**Phân trang tin cậy cần thứ tự nhất quán.** Nếu comparator cho phép hai bản ghi bằng nhau theo khóa sắp xếp, thứ tự của các bản ghi đó có thể chưa xác định đủ để chia trang ổn định giữa các lượt đọc, đặc biệt khi nguồn hoặc dữ liệu thay đổi. Nên bổ sung khóa phụ duy nhất (ví dụ ID) và cân nhắc cách phân trang theo khóa (*keyset pagination*) cho dữ liệu lớn, thay vì tăng `skip` liên tục.

## 9. takeWhile và dropWhile không giống filter

Từ Java 9, `takeWhile` và `dropWhile` xử lý **tiền tố liên tiếp** của Stream **có encounter order**.

```java
List<Integer> measures = List.of(1, 2, 5, 4, 3);

System.out.println(
        measures.stream()
                .filter(n -> n < 5)
                .collect(Collectors.toList())
); // [1, 2, 4, 3]

System.out.println(
        measures.stream()
                .takeWhile(n -> n < 5)
                .collect(Collectors.toList())
); // [1, 2]

System.out.println(
        measures.stream()
                .dropWhile(n -> n < 5)
                .collect(Collectors.toList())
); // [5, 4, 3]
```

- `filter(predicate)` xét từng phần tử độc lập và giữ **tất cả** phần tử thỏa điều kiện.
- `takeWhile(predicate)` nhận **tiền tố dài nhất** liên tục thỏa điều kiện rồi dừng nhận.
- `dropWhile(predicate)` bỏ **tiền tố dài nhất** liên tục thỏa điều kiện, sau đó giữ toàn bộ phần còn lại (kể cả phần tử lại thỏa điều kiện).

Vị trí của `sorted` trước `takeWhile` hoặc `dropWhile` có thể đổi tiền tố được chọn:

```java
List<Integer> unsorted = List.of(1, 2, 5, 4, 3);

List<Integer> afterSorting = unsorted.stream()
        .sorted()
        .takeWhile(n -> n < 5)
        .collect(Collectors.toList());

System.out.println(afterSorting); // [1, 2, 3, 4]
```

Với Stream unordered, `takeWhile`/`dropWhile` không giữ nghĩa tiền tố theo thứ tự danh sách gốc; theo hợp đồng, tập phần tử được chọn/bỏ có thể không như bạn dự đoán. Nếu yêu cầu “mọi giá trị nhỏ hơn 5”, hãy dùng `filter`.

## 10. Encounter order, unordered và parallel stream

`unordered()` không phải phép xáo trộn như `shuffle`. Nó thông báo các bước downstream rằng thứ tự gặp phần tử **không cần được tôn trọng**. Tùy nguồn và terminal operation, điều này có thể giúp một số phép toán chạy song song hiệu quả hơn nhưng làm mất cam kết về “đầu tiên”.

```java
List<Integer> numbers = List.of(4, 1, 4, 3, 2, 3, 5);

// Giữ thứ tự encounter order của List và lần xuất hiện đầu.
List<Integer> ordered = numbers.parallelStream()
        .distinct()
        .limit(3)
        .collect(Collectors.toList());

System.out.println(ordered); // [4, 1, 3]
```

Nếu thêm `unordered()`, không thể khẳng định ba phần tử khác nhau nào sẽ được giữ:

```java
List<Integer> someThree = numbers.parallelStream()
        .unordered()
        .distinct()
        .limit(3)
        .collect(Collectors.toList());

// Có tối đa ba giá trị khác nhau; thành viên và thứ tự
// không được bảo đảm trùng với [4, 1, 3].
```

Đối với pipeline trên, có ít nhất ba giá trị khác nhau, nên giới hạn cho ra ba phần tử nếu thực thi hoàn tất bình thường. Nhưng không được kỳ vọng đó là **ba giá trị đầu**, hay **ba giá trị nhỏ nhất**. Đặt `sorted()` **sau** `limit(3)` không sửa được sai nghĩa “top ba toàn cục”, vì các phần tử đã bị cắt trước khi sắp xếp.

Trong pipeline song song có encounter order, `skip`, `limit` và `distinct` thường tốn chi phí phối hợp để duy trì ràng buộc “phần tử đầu tiên”. Chỉ dùng `unordered()` khi nghiệp vụ thực sự **không quan tâm phần tử nào được chọn**. `sorted()` trước `limit()` có ý nghĩa khác, nên không thể thay bằng `unordered()` để lấy top N.

### forEach và forEachOrdered

```java
List.of(10, 20, 30).parallelStream()
        .forEach(System.out::println); // Thứ tự in không được bảo đảm.

List.of(10, 20, 30).parallelStream()
        .forEachOrdered(System.out::println); // 10, 20, 30
```

`forEachOrdered` bảo đảm quan hệ encounter order của việc thực hiện hành động đối với các phần tử khi Stream có thứ tự. Không nên xem thứ tự in của `peek` hoặc trạng thái biến dùng chung trong `map` là căn cứ kiểm chứng thứ tự kết quả.

## 11. Lazy, short-circuit và hai loại chi phí

Thứ tự thao tác quyết định **bao nhiêu phần tử phải đi qua một bước**, nhưng không thể suy đoán số lần chạy lambda bằng một công thức cứng cho mọi nguồn và mọi terminal operation.

Với pipeline tuần tự:

```java
import java.util.stream.IntStream;

long found = IntStream.rangeClosed(1, 1_000_000)
        .filter(n -> n % 1_000 == 0)
        .limit(2)
        .count();

System.out.println(found); // 2
```

Để tìm hai số chia hết cho 1.000 đầu tiên, pipeline có thể cần xét tới số 2.000, nhưng không cần duyệt cả một triệu số. Vậy `limit(2)` **giới hạn số đầu ra**, không giới hạn đầu vào phải kiểm tra đến đúng hai phần tử.

Ngược lại:

```java
long top = IntStream.rangeClosed(1, 1_000_000)
        .boxed()
        .sorted(Comparator.reverseOrder())
        .limit(2)
        .count();

System.out.println(top); // 2
```

Việc đặt `sorted` trước `limit` có thể buộc pipeline phải xem toàn bộ đầu vào để biết phần tử lớn nhất, dù chỉ trả về hai phần tử. Tuy nhiên, không được suy luận **đã thực sự có một triệu lời gọi comparator** chỉ từ mã nguồn này: Stream API cho phép một số terminal operation (đặc biệt `count` trên pipeline biết kích thước) tối ưu hóa bỏ qua việc duyệt khi kết quả đếm không thay đổi. Muốn thấy giá trị top hai, hãy dùng `collect` thay vì `count`.

### Stream vô hạn và thứ tự đặt limit

```java
import java.util.stream.Stream;

List<Long> firstFiveSorted = Stream.iterate(0L, n -> n + 1)
        .limit(5)
        .sorted()
        .collect(Collectors.toList());

System.out.println(firstFiveSorted); // [0, 1, 2, 3, 4]
```

Ở đây `limit(5)` biến nguồn vô hạn thành đoạn hữu hạn rồi `sorted` xử lý được. Đảo thành `Stream.iterate(...).sorted().limit(5)` có thể khiến pipeline **không bao giờ tạo phần tử đầu**, vì `sorted` cần xác định thứ tự trước khi phát kết quả từ nguồn không kết thúc. Đây là ví dụ về thay đổi thứ tự vừa sai về khả năng hoàn tất, vừa nguy hiểm cho bộ nhớ.

### Các phép trung gian có trạng thái

| Thao tác | Chi phí điển hình (nguồn hữu hạn) | Khả năng dừng sớm |
| --- | --- | --- |
| `map` / `filter` | Theo số phần tử thực sự được xét, thường không cần bộ đệm toàn cục | Có thể kết hợp với `limit`, `findFirst` hoặc `anyMatch` |
| `distinct` | Theo số phần tử xem và số khóa khác nhau đã gặp; có thể giữ tập khóa | `distinct().limit(k)` có thể dừng khi đủ k giá trị, nhưng không luôn đạt đủ |
| `sorted` | Thường `O(N log N)` thời gian và `O(N)` bộ nhớ | Thường không phát kết quả trước khi xác định thứ tự cần thiết |
| `skip(n)` | Cần bỏ qua n phần tử theo encounter order | Với nguồn có kích thước/khả năng tách phù hợp có thể tối ưu |
| `limit(n)` | Chỉ phát tối đa n phần tử downstream | Có khả năng dừng sớm, trừ khi upstream giữ trạng thái cản trở |

Đây là nhận định để **định hướng thiết kế**, không phải cam kết về thuật toán nội bộ mọi JDK. Thao tác có thể được tối ưu hoặc thực thi khác tùy nguồn, đặc tính `Spliterator`, terminal operation và parallelism.

## 12. Checklist để quyết định có được đổi thứ tự hay không

Trước khi chuyển một thao tác lên sớm hơn để “nhanh hơn”, hãy lần lượt hỏi:

1. **Yêu cầu chọn phần tử nào?** `limit`, `skip`, `takeWhile`, `findFirst` có phụ thuộc encounter order không?
2. **Phần tử có đổi ý nghĩa sau `map` không?** Nếu `map` chuẩn hóa, làm tròn hoặc lấy khóa, `distinct` trước và sau có thể loại các nhóm khác nhau.
3. **Predicate có độc lập với dữ liệu khác không?** Chỉ hoán đổi những hàm thuần, stateless, không có tác dụng phụ và giữ nguyên ý nghĩa.
4. **Có cần sắp xếp toàn cục không?** `sorted().limit(k)` và `limit(k).sorted()` giải hai bài toán khác nhau.
5. **Nguồn hữu hạn hay vô hạn?** `sorted` và một số `distinct` có thể không hoàn tất khi đặt trước short-circuit.
6. **Nguồn có encounter order không?** Nếu không, “đầu tiên” có thể không xác định; thêm `unordered` có thể mở quyền chọn phần tử khác.
7. **Chi phí nằm ở đâu?** Lọc sớm giảm lượng dữ liệu đi qua bước tốn bộ nhớ, nhưng có thể tăng số lần gọi predicate đắt tiền nếu nó đứng trước `distinct`.
8. **Đã đo trên nguồn thực chưa?** Đo cả CPU, bộ nhớ, số bản ghi trả về, thời gian đọc nguồn và sự ổn định của kết quả.

Một bảng ví dụ ngắn:

| Hoán đổi | Kết quả có thường giống nhau không? | Lý do |
| --- | --- | --- |
| `filter` ↔ `limit` | **Không** | Lọc đủ N giá trị khác với xét N đầu vào |
| `sorted` ↔ `limit` | **Không** | Top N toàn cục khác sắp xếp N phần tử đầu |
| `distinct` ↔ `limit` | **Không** | Số giá trị khác nhau sau cắt có thể ít hơn N |
| `skip` ↔ `limit` | **Không** | Thay cửa sổ cắt |
| `filter` ↔ `skip` | **Không** | Bỏ phần tử trước hay sau lọc |
| `map` ↔ `distinct` | **Không, nếu map làm thay đổi quan hệ bằng nhau** | Trùng lặp được xét trên hai kiểu/giá trị khác nhau |
| `filter` ↔ `distinct` | **Thường có**, khi predicate thuần và nhất quán với equality | Chi phí lọc/hash có thể khác |
| `filter` ↔ `sorted` | **Thường có**, nếu predicate thuần, comparator phù hợp và chỉ cần kết quả đã lọc có thứ tự | Lọc trước thường giảm khối lượng sắp xếp |
| `takeWhile` ↔ `sorted` | **Không** | Điều kiện tiền tố được áp dụng trên thứ tự khác |

## 13. Ví dụ tổng hợp: chọn top ba điểm sản phẩm theo quy tắc nghiệp vụ

Giả sử danh sách điểm sản phẩm có thể chứa bản ghi trùng, điểm dưới ngưỡng và xuất hiện không theo thứ tự. Nhiệm vụ là **lấy ba điểm cao nhất khác nhau, sau khi loại điểm dưới 8**.

```java
import java.util.Comparator;
import java.util.List;
import java.util.stream.Collectors;

List<Integer> scores = List.of(6, 10, 10, 8, 12, 5, 12, 9);

List<Integer> topDistinct = scores.stream()
        .filter(score -> score >= 8)
        .distinct()
        .sorted(Comparator.reverseOrder())
        .limit(3)
        .collect(Collectors.toList());

System.out.println(topDistinct); // [12, 10, 9]
```

Thứ tự ở đây có ý nghĩa rõ ràng:

1. `filter(score >= 8)` loại dữ liệu không đạt yêu cầu ngay từ đầu.
2. `distinct()` giữ một lần xuất hiện cho mỗi điểm; ở bài này, việc trùng lặp tính theo **giá trị điểm**.
3. `sorted(reverseOrder())` sắp xếp tất cả điểm hợp lệ khác nhau từ cao xuống thấp.
4. `limit(3)` chọn đúng ba giá trị cao nhất khác nhau, nếu đủ giá trị.

Một phiên bản tưởng như “tiết kiệm” nhưng đổi ý nghĩa:

```java
List<Integer> wrong = scores.stream()
        .filter(score -> score >= 8)
        .limit(3)
        .distinct()
        .sorted(Comparator.reverseOrder())
        .collect(Collectors.toList());

System.out.println(wrong); // [10, 8]
```

Phiên bản này chỉ xét ba điểm hợp lệ đầu `[10, 10, 8]`, nên bỏ lỡ `12` và `9` nằm phía sau. Đây là lỗi nghiệp vụ, không đơn thuần là khác biệt về hiệu năng.

Nếu muốn một trang gồm bản ghi sản phẩm thay vì điểm, nên có comparator mang khóa phân biệt ổn định, xác định rõ tiêu chí “trùng” (ID sản phẩm, biến thể hay điểm) và cân nhắc đưa truy vấn sắp xếp/phân trang xuống nguồn dữ liệu để tránh tải toàn bộ vào bộ nhớ.

## 14. Câu hỏi tự kiểm tra

1. Với `[7, 2, 9, 4, 6]`, vì sao `filter(chẵn).limit(2)` khác `limit(2).filter(chẵn)`? **Vì** một bên chọn hai giá trị hợp lệ, bên kia chỉ lọc trong hai giá trị đầu.
2. `sorted().limit(3)` và `limit(3).sorted()` có cùng nhiệm vụ không? **Không**: một bên tìm ba giá trị đầu theo sắp xếp toàn cục, bên kia sắp xếp ba giá trị đầu nguồn.
3. Trên `["An", "AN"]`, tại sao `map(lowercase).distinct()` cho một phần tử còn `distinct().map(lowercase)` cho hai? **Vì** phép chuẩn hóa thay đổi quan hệ bằng nhau.
4. `Stream.generate(() -> 1).distinct().limit(2)` có hoàn tất không? **Không**, vì không thể tìm hai giá trị khác nhau.
5. `unordered()` có đảo ngẫu nhiên một `List` không? **Không**; nó bỏ cam kết encounter order, nên downstream được phép chọn/thực thi khác.
6. Khi phân trang các bản ghi đã lọc và sắp xếp, `skip`/`limit` nên đặt ở đâu? **Sau** bước lọc và sắp xếp theo yêu cầu nghiệp vụ.
7. Vì sao `takeWhile(x < 5)` không tương đương `filter(x < 5)` trên một dãy chưa sắp xếp? **Vì** `takeWhile` chỉ lấy tiền tố liên tiếp thỏa điều kiện.
8. Muốn đánh giá chi phí của `sorted` trên nguồn lớn, vì sao không nên dùng mỗi `count()` để suy ra số phần tử thực sự đã được sắp xếp? **Vì** JDK có thể tối ưu `count` khi biết kích thước mà không cần duyệt pipeline.

**Nguyên tắc áp dụng:** Trước tiên mô tả đúng **tập phần tử cần giữ** và **thứ tự cần cam kết**, rồi mới tối ưu. Đẩy các phép lọc đơn giản lên trước thao tác tốn kém khi an toàn, giữ `sorted` trước `limit` nếu cần top N toàn cục, và không di chuyển `distinct` hay `skip` qua `map`/`filter` khi điều đó đổi ý nghĩa. Đo chi phí trên dữ liệu và JDK thực tế, đặc biệt với pipeline parallel hoặc có nguồn vô hạn.
