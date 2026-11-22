# Ảnh hưởng của vị trí `sorted()`, `limit()` và `distinct()` trong Java Stream

Trong Java Stream, `sorted()`, `limit()` và `distinct()` đều là **intermediate operation**: chúng mô tả cách tạo stream tiếp theo nhưng thường chưa thực sự tính kết quả cho tới khi có terminal operation như `toList()`, `count()` hoặc `forEach()`. Tuy nhiên, **thứ tự đặt ba operation trong pipeline làm thay đổi ý nghĩa của phép biến đổi**. Không thể tùy tiện đổi vị trí các bước chỉ vì chúng đều “lọc bớt hoặc sắp xếp dữ liệu”.

Bài học này tập trung vào ba câu hỏi: khi nào đổi vị trí làm thay đổi kết quả, khi nào có thể nhận cùng kết quả, và tại sao lựa chọn vị trí còn tác động đến hiệu năng, nhất là với parallel stream.

## 1. Hiểu đúng từng operation trước khi kết hợp

| Operation | Hành vi | Có thể thay đổi số lượng phần tử? | Liên hệ với thứ tự |
| --- | --- | --- | --- |
| `sorted()` | Sắp xếp theo thứ tự tự nhiên của các phần tử, hoặc `sorted(comparator)` theo bộ so sánh | Không | Thiết lập encounter order được sắp xếp; `sorted` có tính ổn định (*stable*) trên ordered stream |
| `limit(n)` | Giữ tối đa `n` phần tử đầu tại **vị trí này** trong pipeline | Có | Với ordered stream, chọn prefix theo encounter order |
| `distinct()` | Giữ một bản của mỗi giá trị theo `equals()` | Có | Với ordered stream, giữ **lần gặp đầu tiên** của mỗi giá trị; với unordered stream, không có cam kết chọn bản xuất hiện đầu |

Các điểm cần nhớ:

- `sorted()` **không loại trùng**: `[3, 1, 1]` thành `[1, 1, 3]`, còn nguyên hai số `1`.
- `distinct()` **không sắp xếp**: trên ordered stream `[3, 1, 3, 2]` thành `[3, 1, 2]`.
- `limit(3)` **không biết “nhỏ nhất” hay “khác nhau”**. Nó chỉ lấy tối đa ba phần tử đầu sau các bước đứng trước nó.
- `limit(n)` yêu cầu `n >= 0`; số âm ném `IllegalArgumentException`. `limit(0)` cho kết quả rỗng.
- `distinct()` so sánh phần tử bằng **`Object.equals`** (và các implementation thường dùng `hashCode` cho hiệu năng). Nó không dùng comparator của `sorted()` để quyết định trùng nhau.
- Cả ba là **stateful intermediate operations**: chúng có thể phải lưu hoặc theo dõi thông tin từ nhiều phần tử. Riêng `limit` là một thao tác *short-circuiting* có thể cho phép dừng lấy nguồn sớm.

## 2. Một danh sách, tám pipeline, tám cách diễn giải

Dùng nguồn có cả thứ tự “lộn xộn” và giá trị trùng:

```text
Nguồn: [4, 1, 1, 3, 2, 2, 5, 1]
         ^     ^              ^
         Các số 1 xuất hiện ba lần; số 2 xuất hiện hai lần.
```

Hãy xét các pipeline sau (`n = 3`):

| Pipeline | Kết quả | Diễn giải |
| --- | --- | --- |
| `sorted().limit(3)` | `[1, 1, 1]` | Sắp xếp toàn bộ theo giá trị rồi lấy ba phần tử đầu; có thể vẫn trùng |
| `limit(3).sorted()` | `[1, 1, 4]` | Chỉ lấy ba phần tử gốc `[4, 1, 1]` rồi sắp xếp |
| `distinct().limit(3)` | `[4, 1, 3]` | Lấy ba **giá trị khác nhau** đầu tiên theo thứ tự gặp |
| `limit(3).distinct()` | `[4, 1]` | Lấy ba phần tử trước, sau đó bỏ trùng; có thể còn ít hơn ba kết quả |
| `sorted().distinct().limit(3)` | `[1, 2, 3]` | Lấy ba giá trị **nhỏ nhất và khác nhau** |
| `sorted().limit(3).distinct()` | `[1]` | Chỉ xem ba phần tử nhỏ nhất (đều là `1`), rồi bỏ trùng |
| `distinct().sorted().limit(3)` | `[1, 2, 3]` | Bỏ trùng toàn nguồn, sắp xếp, rồi lấy ba giá trị đầu |
| `distinct().limit(3).sorted()` | `[1, 3, 4]` | Chỉ lấy ba giá trị khác nhau đầu theo nguồn, sau đó sắp xếp chính ba giá trị ấy |

**Kết luận quan trọng của bảng:** việc đặt `limit` **trước hay sau** `sorted` hoặc `distinct` có thể làm thay đổi tập kết quả, số phần tử trả về và cả ý nghĩa nghiệp vụ.

## 3. Ví dụ Java 17+ chạy đầy đủ và stdout chính xác

Lưu vào tệp `StreamOperationOrderDemo.java`:

```java
import java.util.List;

public class StreamOperationOrderDemo {
    public static void main(String[] args) {
        List<Integer> values = List.of(4, 1, 1, 3, 2, 2, 5, 1);

        System.out.println("source = " + values);

        System.out.println("sortedLimit = " + values.stream()
                .sorted().limit(3).toList());

        System.out.println("limitSorted = " + values.stream()
                .limit(3).sorted().toList());

        System.out.println("distinctLimit = " + values.stream()
                .distinct().limit(3).toList());

        System.out.println("limitDistinct = " + values.stream()
                .limit(3).distinct().toList());

        System.out.println("sortDistinctLimit = " + values.stream()
                .sorted().distinct().limit(3).toList());

        System.out.println("sortLimitDistinct = " + values.stream()
                .sorted().limit(3).distinct().toList());

        System.out.println("distinctSortLimit = " + values.stream()
                .distinct().sorted().limit(3).toList());

        System.out.println("distinctLimitSort = " + values.stream()
                .distinct().limit(3).sorted().toList());
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac StreamOperationOrderDemo.java
java StreamOperationOrderDemo
```

Kết quả stdout chính xác:

```text
source = [4, 1, 1, 3, 2, 2, 5, 1]
sortedLimit = [1, 1, 1]
limitSorted = [1, 1, 4]
distinctLimit = [4, 1, 3]
limitDistinct = [4, 1]
sortDistinctLimit = [1, 2, 3]
sortLimitDistinct = [1]
distinctSortLimit = [1, 2, 3]
distinctLimitSort = [1, 3, 4]
```

Mỗi dòng trong `main` tạo một `values.stream()` **mới**. Một stream chỉ được tiêu thụ một lần; không thể dùng lại sau terminal operation `toList()`. Dữ liệu đầu vào là `List`, nên encounter order đã xác định và các kết quả trong ví dụ không phụ thuộc lịch chạy luồng.

## 4. Cặp `sorted()` và `limit()`: “nhỏ nhất toàn nguồn” khác “sắp xếp một đoạn”

### `sorted().limit(n)`: lấy n phần tử đầu của toàn bộ dữ liệu đã sắp xếp

```java
List<Integer> smallest = List.of(9, 2, 8, 1, 7)
        .stream()
        .sorted()
        .limit(2)
        .toList();
// [1, 2]
```

`sorted()` tạo encounter order theo thứ tự tăng dần. Sau đó `limit(2)` chọn hai phần tử đầu tiên của thứ tự mới: `1` và `2`.

Đây **không hẳn** là “hai giá trị khác nhau nhỏ nhất”: nếu nguồn chứa hai số `1`, kết quả có thể là `[1, 1]`. Muốn giá trị **khác nhau**, phải xét thêm `distinct()`.

### `limit(n).sorted()`: chỉ sắp xếp n phần tử đầu của nguồn

```java
List<Integer> prefixSorted = List.of(9, 2, 8, 1, 7)
        .stream()
        .limit(2)
        .sorted()
        .toList();
// [2, 9]
```

Dữ liệu ngoài hai phần tử đầu `[9, 2]` không được xem xét ở bước sort, vì chúng đã bị loại bởi `limit(2)`. Kết quả `[2, 9]` **không thể dùng** để kết luận hai số nhỏ nhất trong toàn bộ nguồn.

Hai đoạn trên là minh họa đặt trong phương thức, cần `import java.util.List;`.

### Trường hợp nên dùng

- Bài toán “**Top N giá trị nhỏ nhất**” thường cần `sorted(comparator).limit(n)` nếu chấp nhận chi phí sort.
- Bài toán “**Lấy N bản ghi đầu theo thứ tự đầu vào rồi trình bày theo tên**” dùng `limit(n).sorted(comparator)`.
- Bài toán “**Top N giá trị phân biệt nhỏ nhất**” cần kết hợp cả `distinct()` và `sorted()` **trước** `limit(n)`.

**Hiệu năng:** với nguồn hữu hạn, `limit(n).sorted()` có thể giảm đáng kể số phần tử phải sắp xếp, nhưng trả kết quả khác. `sorted().limit(n)` về mặt ngữ nghĩa phải xác định N phần tử nhỏ nhất **trong toàn nguồn**, nên thường đòi hỏi xem xét nhiều hơn N phần tử và có thể cần buffer/sort đáng kể. Không tối ưu bằng cách đổi vị trí nếu làm sai kết quả.

## 5. Cặp `distinct()` và `limit()`: “N giá trị khác nhau” khác “N phần tử rồi bỏ trùng”

Cho nguồn:

```java
List<String> names = List.of("An", "An", "Bình", "Chi", "Chi");
```

Với mục tiêu **hai tên phân biệt đầu tiên**:

```java
List<String> firstTwoUnique = names.stream()
        .distinct()
        .limit(2)
        .toList();
// [An, Bình]
```

Với mục tiêu **xem đúng hai bản ghi đầu rồi bỏ trùng**:

```java
List<String> uniqueInFirstTwo = names.stream()
        .limit(2)
        .distinct()
        .toList();
// [An]
```

Hai đoạn minh họa nằm trong phương thức và yêu cầu `import java.util.List;`.

Lưu ý rằng `distinct().limit(n)` có thể phải xem **nhiều hơn n phần tử từ nguồn** trước khi tìm được n giá trị khác nhau. Với nguồn chứa nhiều bản trùng, lần xuất hiện thứ n của một giá trị duy nhất có thể nằm rất xa. Nếu nguồn chỉ có một giá trị lặp lại mãi, pipeline tìm hai giá trị duy nhất có thể **không bao giờ kết thúc**:

```java
// Ví dụ minh họa nguy cơ treo: KHÔNG chạy toList() với pipeline này.
java.util.stream.Stream.generate(() -> "A")
        .distinct()
        .limit(2)
        .toList();
```

Đây là snippet cố ý không có đầu ra vì nguồn là vô hạn chỉ sinh `"A"`; `distinct()` chỉ có một giá trị để phát và `limit(2)` không nhận đủ hai phần tử để dừng.

Trong khi đó, `limit(2).distinct()` trên nguồn ấy sẽ trả `["A"]` vì chỉ lấy hai lần sinh ban đầu trước khi loại trùng. Điều đó minh họa đồng thời sự khác biệt về **kết quả** và **khả năng kết thúc**.

## 6. Cặp `sorted()` và `distinct()`: khi nào đổi chỗ vẫn cho kết quả giống nhau?

Với số nguyên, comparator tự nhiên và stream có thứ tự:

```java
List<Integer> values = List.of(4, 1, 1, 3, 2, 2);

List<Integer> a = values.stream()
        .sorted()
        .distinct()
        .toList();             // [1, 2, 3, 4]

List<Integer> b = values.stream()
        .distinct()
        .sorted()
        .toList();             // [1, 2, 3, 4]
```

Với dữ liệu và ngữ nghĩa trên, hai pipeline cùng trả các giá trị phân biệt được sắp tăng dần. Tuy nhiên **không nên suy rộng vô điều kiện** sang mọi comparator, mọi nguồn hoặc code có side effect:

- `distinct()` dùng `equals()`; `sorted(comparator)` dùng comparator. Hai tiêu chí có thể **khác nhau**, ví dụ comparator chỉ so sánh độ dài chuỗi trong khi `equals` so sánh toàn bộ nội dung.
- Trên **ordered stream**, `distinct()` chọn phần tử xuất hiện đầu tiên theo `equals` và `sorted` giữ thứ tự tương đối của phần tử được comparator coi là bằng nhau (*stable sort*). Khi comparator bất nhất với `equals`, kết quả theo “nhóm bằng nhau” của comparator có thể khiến thứ tự các bản ghi có ý nghĩa hơn chỉ tập các giá trị.
- Trên **unordered stream**, `distinct` không cam kết chọn đại diện đầu tiên khi các phần tử bằng nhau theo `equals`. Một comparator có nhiều phần tử bằng nhau cũng không cam kết thứ tự giữa những phần tử đó nếu stream ban đầu unordered.
- `distinct().sorted()` thường làm giảm số phần tử cần sắp xếp khi dữ liệu có nhiều bản trùng; `sorted().distinct()` có thể phải sắp xếp cả phần tử trùng. **Dù vậy không có bảo đảm hiệu năng tuyệt đối**; cấu trúc nguồn, dữ liệu, JVM và parallelism đều ảnh hưởng.

### Comparator “bằng nhau” không đồng nghĩa với `equals()`

```java
List<String> values = List.of("aa", "BB", "c");
List<String> result = values.stream()
        .sorted(String.CASE_INSENSITIVE_ORDER)
        .distinct()
        .toList();
// [aa, BB, c]
```

Đoạn trên minh họa việc `distinct()` không loại phần tử chỉ vì comparator coi hai giá trị bằng nhau. Tuy nhiên với ví dụ cụ thể `"aa"`, `"BB"`, `"c"`, comparator cũng không coi chúng bằng nhau; để thấy rõ khác biệt, dùng:

```java
List<String> values = List.of("a", "A", "b");
List<String> result = values.stream()
        .sorted(String.CASE_INSENSITIVE_ORDER)
        .distinct()
        .toList();
// [a, A, b]
```

Ở đây comparator không phân biệt hoa/thường nên coi `"a"` và `"A"` tương đương để sắp xếp; `String.equals` lại coi chúng khác nhau. Vì vậy `distinct` giữ cả hai. Những đoạn này là snippet trong phương thức, cần `java.util.List`.

**Nếu muốn khử trùng theo một khóa** như tên không phân biệt hoa/thường, phải mô tả quy tắc đó tường minh (chẳng hạn chuẩn hóa khóa, gom nhóm hoặc dùng map theo khóa). Chỉ gọi `sorted(comparator).distinct()` sẽ không thay thế chính sách ấy.

## 7. Vì sao `limit()` là ranh giới quan trọng trong pipeline?

Ba câu lệnh có cùng nguồn có thể thể hiện ba câu hỏi rất khác:

```java
List<Integer> data = List.of(4, 1, 1, 3, 2, 2, 5, 1);

List<Integer> a = data.stream().sorted().distinct().limit(3).toList();
// a = [1, 2, 3]: ba GIÁ TRỊ PHÂN BIỆT nhỏ nhất toàn nguồn.

List<Integer> b = data.stream().distinct().limit(3).sorted().toList();
// b = [1, 3, 4]: ba GIÁ TRỊ PHÂN BIỆT đầu theo nguồn, rồi sắp chúng.

List<Integer> c = data.stream().sorted().limit(3).distinct().toList();
// c = [1]: trong ba PHẦN TỬ nhỏ nhất, chỉ còn một GIÁ TRỊ PHÂN BIỆT.
```

Đây là snippet trong phương thức, cần `java.util.List`.

Câu hỏi “Lấy 3 cái đầu tiên” chỉ có nghĩa khi xác định **cái gì đã được tính trước khi giới hạn**:

1. Nếu cần **top N phân biệt toàn nguồn**, `limit` phải đứng sau cả phép loại trùng và phép sắp xếp.
2. Nếu chỉ cần **N phần tử/nhóm đầu trong nguồn**, `limit` đứng trước các bước biến đổi về sau theo đúng chính sách.
3. Nếu nghiệp vụ chấp nhận **dưới N kết quả** do loại trùng, `limit(n).distinct()` có thể phù hợp; nếu cần đủ N giá trị phân biệt khi nguồn có đủ, chọn `distinct().limit(n)`.

## 8. Encounter order, unordered source và parallel stream

`List.stream()` có encounter order theo list. `HashSet.stream()` không bảo đảm encounter order; vì vậy `limit(n)` trên `HashSet` không có ý nghĩa ổn định “N phần tử đầu” khi chạy lại.

```java
java.util.Set<Integer> values = new java.util.HashSet<>(
        List.of(4, 1, 3, 2, 5)
);
List<Integer> picked = values.stream().limit(2).toList();
// Không bảo đảm một cặp hoặc thứ tự cụ thể.
```

Nếu yêu cầu kết quả quyết định được từ giá trị, có thể sắp xếp trước `limit`:

```java
List<Integer> picked = values.stream()
        .sorted()
        .limit(2)
        .toList();
// [1, 2]
```

Đây là các snippet trong phương thức và cần `java.util.List`.

Với `parallelStream()` bắt nguồn từ `List`, encounter order vẫn tồn tại. Ví dụ:

```java
List<Integer> result = List.of(4, 1, 1, 3, 2)
        .parallelStream()
        .distinct()
        .sorted()
        .limit(3)
        .toList();
// [1, 2, 3]
```

Java có thể thực thi callback và gộp dữ liệu trên nhiều luồng theo lịch khác nhau, nhưng kết quả của ordered stream với `toList()` tôn trọng encounter order ở cuối pipeline. **Thứ tự thực thi callback không nhất thiết bằng thứ tự kết quả**.

### `unordered()` là nới lỏng yêu cầu thứ tự, không phải xáo trộn dữ liệu

```java
List<Integer> picked = List.of(4, 1, 1, 3, 2, 2)
        .parallelStream()
        .unordered()
        .distinct()
        .limit(2)
        .toList();
```

`picked` có thể gồm hai giá trị khác nhau, nhưng không thể cam kết luôn là hai giá trị phân biệt đầu tiên `4` và `1`. `unordered()` không tự biến stream thành một phép shuffle ngẫu nhiên; nó chỉ bỏ nghĩa vụ duy trì encounter order.

Giữ hoặc bỏ thứ tự là một **quyết định nghiệp vụ**, không chỉ là tùy chọn tối ưu hóa. Nếu cần trang dữ liệu ổn định hay kết quả “top N”, đừng bỏ thứ tự mà không thiết lập một thứ tự có ý nghĩa trước khi chọn prefix.

## 9. Hiệu năng: cùng mục tiêu kết quả, chi phí có thể khác

Bảng sau mô tả tác động thường gặp; đây là **định hướng**, không phải cam kết độ phức tạp cho mọi implementation hay JVM.

| Pipeline | Công việc có thể phát sinh | Khi nên cân nhắc |
| --- | --- | --- |
| `sorted().limit(n)` | Phải xác định các giá trị nhỏ nhất từ nhiều phần tử nguồn; sorting/buffering có thể đáng kể | Khi mục tiêu đúng là top N theo comparator |
| `limit(n).sorted()` | Sắp xếp tối đa n phần tử được chọn trước | Khi chỉ cần sắp phần tử đầu của nguồn |
| `distinct().limit(n)` | Phải theo dõi phần tử đã gặp; có thể đọc nhiều hơn n đầu vào mới tìm đủ n giá trị riêng | Khi cần n giá trị phân biệt đầu |
| `limit(n).distinct()` | Giới hạn đầu vào còn tối đa n phần tử rồi mới loại trùng | Khi nghiệp vụ chỉ xét prefix của nguồn |
| `distinct().sorted().limit(n)` | Có cơ hội giảm số phần tử đem sắp xếp nếu nguồn trùng nhiều | Khi cần top N giá trị phân biệt |
| `sorted().distinct().limit(n)` | Có thể sắp cả các phần tử trùng trước khi khử trùng | Khi cách diễn đạt này rõ ràng hơn hoặc dữ liệu đặc thù |

**Với ordered parallel stream**, `distinct` cần bảo toàn bản xuất hiện đầu tiên, `limit` phải chọn prefix đúng, và `sorted` phải tạo thứ tự toàn cục. Những ràng buộc này có thể cần thêm bộ nhớ, buffer hoặc phối hợp nhánh song song. Đặc biệt, các operation stateful có thể giảm lợi ích của parallel stream.

Các điểm tối ưu đáng làm:

- Ưu tiên **đúng ngữ nghĩa**: không đẩy `limit` lên trước `sorted` hay `distinct` nếu điều đó đổi kết quả.
- Nếu có bước `filter` độc lập, việc lọc trước `sorted` có thể giảm số phần tử cần sort, nhưng phải xác nhận yêu cầu lọc đúng ở vị trí đó.
- Nếu nguồn là database lớn, nên cân nhắc `ORDER BY` và cơ chế phân trang ở tầng truy vấn thay vì tải hết dữ liệu về Java rồi gọi `stream().sorted().limit(n)`.
- Đừng giả định `parallelStream()` nhanh hơn; đo trên kích thước dữ liệu, comparator, tỉ lệ trùng và điều kiện chạy thực tế.

## 10. `sorted()` có ảnh hưởng đến tác dụng phụ và lần gọi callback không?

Như mọi Stream pipeline, `sorted`, `limit`, `distinct` vận hành **lazy** và được phép áp dụng các tối ưu hóa giữ đúng kết quả cuối. `limit` có thể dừng sớm, còn `distinct` hoặc `sorted` có thể cần kiểm tra nhiều phần tử hơn trước khi phát đầu ra.

Đừng dựa vào `peek`, `map` hoặc comparator có side effect để ghi dữ liệu bắt buộc:

```java
List<Integer> result = List.of(4, 1, 3, 2)
        .stream()
        .peek(n -> System.out.println("seen " + n))
        .sorted()
        .limit(2)
        .toList();
// result = [1, 2]; không nên dùng dòng "seen" làm hợp đồng nghiệp vụ.
```

Ví dụ này có thể in các giá trị `seen` khi pipeline duyệt nguồn, nhưng thứ tự/đầy đủ của những tác dụng phụ ở intermediate operation không phải API để quyết định kết quả nghiệp vụ, nhất là sau khi thêm terminal operation khác hoặc chuyển sang parallel stream. `peek` chủ yếu phục vụ quan sát/debug.

Hàm comparator nên **tuân thủ hợp đồng Comparator**: ổn định về kết quả với cùng cặp đầu vào và nhất quán với thứ tự cần sắp. Comparator có hành vi thay đổi theo thời gian, hoặc sửa dữ liệu đang được sort, có thể dẫn đến kết quả bất thường hoặc exception.

Khi cần xuất dữ liệu, thu thập kết quả trước rồi thực hiện hành động I/O tại ranh giới dễ kiểm soát:

```java
List<Integer> result = values.stream()
        .distinct()
        .sorted()
        .limit(3)
        .toList();

result.forEach(System.out::println);
```

Đây là đoạn minh họa trong phương thức có `values` kiểu `List<Integer>`; thao tác in là hoạt động có chủ ý sau khi kết quả đã được chọn xong.

## 11. Những sai lầm điển hình

1. **Nghĩ `sorted().limit(3)` luôn trả ba giá trị khác nhau:** không; dữ liệu trùng vẫn còn. Cần `distinct` nếu đó là yêu cầu.
2. **Đẩy `limit` lên trước `sorted` để tăng tốc mà không xét kết quả:** khi đó chỉ sort prefix ban đầu, không còn là top N toàn nguồn.
3. **Dùng `limit(n).distinct()` để yêu cầu đúng n giá trị khác nhau:** có thể ít hơn n. Dùng `distinct().limit(n)` nếu muốn n giá trị riêng đầu và nguồn có đủ.
4. **Cho rằng `distinct()` dựa vào comparator:** nó dựa vào `equals`; comparator chỉ dùng trong `sorted(comparator)`.
5. **Nhầm “không trùng theo ID” với `equals` mặc định:** đối tượng có hai instance khác nhau nhưng cùng ID không tự được `distinct` gộp nếu `equals` không thể hiện quan hệ đó. Cần quy tắc so sánh/khóa rõ ràng.
6. **Dùng `HashSet.stream().limit(3)` để lấy ba phần tử đầu ổn định:** `HashSet` không cam kết encounter order.
7. **Lạm dụng `unordered()` vì nghĩ nó giữ nguyên prefix:** `unordered` giải phóng ràng buộc chọn prefix ban đầu.
8. **Quên stream chỉ dùng được một lần:** mỗi pipeline trong các ví dụ phải bắt đầu từ một stream mới.
9. **Tự thay đổi collection nguồn trong `peek`/comparator:** vi phạm nguyên tắc non-interfering của stream và có thể phá kết quả.
10. **Dùng kết quả thử nghiệm song song như bảo đảm thứ tự:** thứ tự callback không phải thứ tự logic của kết quả.

## 12. Câu hỏi tự đánh giá

**1.** Với `List.of(4, 1, 1, 3, 2)`, `sorted().limit(3)` và `sorted().distinct().limit(3)` có giống nhau không?

Không. Cách đầu trả `[1, 1, 2]`; cách sau trả `[1, 2, 3]`.

**2.** Muốn ba mã khác nhau đầu tiên theo thứ tự nhập, nên chọn `distinct().limit(3)` hay `limit(3).distinct()`?

Chọn `distinct().limit(3)`; `limit(3).distinct()` chỉ xét ba bản ghi đầu và có thể còn ít hơn ba mã.

**3.** Khi đã biết `List<Integer>` cần ba giá trị phân biệt nhỏ nhất, có thể đổi giữa `distinct().sorted().limit(3)` và `sorted().distinct().limit(3)` không?

Với số nguyên và thứ tự tự nhiên như trong bài, cả hai tạo cùng các giá trị phân biệt nhỏ nhất. Tuy nhiên có thể khác chi phí thực thi; khi comparator không phù hợp với `equals`, phải xem kỹ yêu cầu thứ tự và tính duy nhất.

**4.** `parallelStream().sorted().limit(3).toList()` có bảo đảm callback chạy theo thứ tự tăng dần không?

Không. Pipeline có thể chạy song song; `sorted` quyết định thứ tự logic của kết quả, không buộc mọi callback trung gian thực thi theo thứ tự đó.

**5.** Vì sao không nên dùng `Stream.generate(() -> "A").distinct().limit(2).toList()`?

Nguồn vô hạn chỉ có một giá trị khác nhau, nên `distinct()` không thể cung cấp kết quả thứ hai; lời gọi có thể không kết thúc.

## Ghi nhớ

- `sorted()`: **sắp xếp**, không loại trùng.
- `distinct()`: **loại trùng theo `equals()`**, không nhất thiết sắp xếp.
- `limit(n)`: **lấy tối đa n phần tử đầu tại đúng vị trí xuất hiện trong pipeline**.
- `sorted().limit(n)` và `limit(n).sorted()` thường phục vụ hai yêu cầu khác nhau.
- `distinct().limit(n)` và `limit(n).distinct()` có thể khác cả số phần tử trả về.
- Để tìm **N giá trị khác nhau nhỏ nhất** của ordered stream số nguyên, dùng `distinct().sorted().limit(n)` hoặc `sorted().distinct().limit(n)` theo ngữ nghĩa phù hợp.
- Chọn thứ tự operation dựa trên ý nghĩa dữ liệu trước; sau đó mới cân nhắc tối ưu hiệu năng bằng phép đo.
