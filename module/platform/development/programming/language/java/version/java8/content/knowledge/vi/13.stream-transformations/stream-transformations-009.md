# Đặt `filter`, `map`, `sorted` theo ý nghĩa và chi phí trong Java Stream

Trong Java Stream, **thứ tự các phép biến đổi là một quyết định về tính đúng đắn trước khi là quyết định tối ưu hiệu năng**. Không có quy tắc luôn đặt `filter → map → sorted` cho mọi bài toán. Hãy xác định điều kiện lọc áp dụng lên dữ liệu gốc hay dữ liệu đã biến đổi, tiêu chí sắp xếp dựa trên giá trị nào, và kết quả cần có thứ tự gì; sau đó mới giảm số phần tử/công việc phải xử lý.

Các nguyên tắc dưới đây áp dụng cho Stream API từ Java 8 đến Java hiện đại; ví dụ dùng các API tương thích Java 8, không dựa vào hành vi đã lỗi thời.

## 1. Vai trò và chi phí của ba phép toán

| Phép toán | Ý nghĩa | Đặc điểm thực thi | Chi phí thường gặp |
| --- | --- | --- | --- |
| `filter(Predicate<T>)` | Giữ phần tử thỏa điều kiện; không đổi kiểu phần tử. | Trung gian (*intermediate*), lazy, stateless. | Duyệt tối đa `n` phần tử; xấp xỉ `O(n × chi phí predicate)`. |
| `map(Function<T,R>)` | Biến đổi từng phần tử từ `T` sang `R`, giữ nguyên số phần tử nếu pipeline đi hết. | Trung gian, lazy, stateless. | Xấp xỉ `O(n × chi phí mapper)`; có thể cấp phát đối tượng mới. |
| `sorted()` / `sorted(comparator)` | Sắp xếp theo thứ tự tự nhiên hoặc `Comparator`. | Trung gian, lazy nhưng **stateful**: cần nắm các phần tử đầu vào trước khi phát ra kết quả đã sắp xếp. | Với `k` phần tử đến bước sort: thường `O(k log k)` thời gian, `O(k)` bộ nhớ đệm; còn phụ thuộc comparator và triển khai. |

`n` là số phần tử đi vào pipeline, `k` là số phần tử còn lại trước `sorted`. Độ phức tạp nêu trên là ước lượng để thiết kế, **không phải lời bảo đảm về thuật toán cụ thể của Java API**. Bước cuối như `collect` cũng có chi phí lưu kết quả.

Một pipeline có dạng:

~~~text
nguồn dữ liệu → filter/map/sorted (0 hoặc nhiều bước) → terminal operation
~~~

Các bước trung gian **chưa chạy** khi chỉ khai báo. Khi có terminal operation như `collect`, `count` hoặc `forEach`, Stream mới được tiêu thụ. Với chuỗi các bước stateless, Java thường xử lý từng phần tử xuyên qua các bước thay vì tạo danh sách trung gian ở mỗi bước. `sorted` tạo điểm chặn cần giữ dữ liệu để sắp xếp. Stream sau khi tiêu thụ không dùng lại được; muốn chạy pipeline khác, tạo stream mới từ nguồn.

## 2. Chọn thứ tự dựa trên ý nghĩa

### Trường hợp A — Điều kiện lọc thuộc về dữ liệu gốc: `filter` trước `map`

Ví dụ yêu cầu: “Chỉ lấy số chẵn, đổi chúng thành trị tuyệt đối, rồi xếp tăng dần”.

~~~java
List<Integer> result = numbers.stream()
    .filter(n -> n % 2 == 0)  // điều kiện trên số gốc
    .map(Math::abs)           // chỉ biến đổi số còn lại
    .sorted()
    .collect(Collectors.toList());
~~~

Đặt `filter` sớm giúp tránh chạy `map` trên phần tử bị bỏ. Đây cũng là cách đọc đúng yêu cầu: **lọc số chẵn của dữ liệu đầu vào**, rồi biến đổi. Nếu mapper nặng hoặc cấp phát đối tượng, phần tiết kiệm càng đáng kể.

### Trường hợp B — Điều kiện lọc thuộc về giá trị sau biến đổi: `map` trước `filter`

Ví dụ yêu cầu: “Chuẩn hóa chuỗi bằng `trim()`, rồi bỏ các tên rỗng và sắp xếp”.

~~~java
List<String> names = rawNames.stream()
    .map(String::trim)
    .filter(name -> !name.isEmpty())
    .sorted()
    .collect(Collectors.toList());
~~~

Nếu lọc chuỗi rỗng **trước** bước chuẩn hóa, chuỗi chỉ gồm dấu cách (`"   "`) vẫn vượt qua kiểm tra `isEmpty()` và thành chuỗi rỗng sau `trim()`. Như vậy hai thứ tự cho kết quả khác nhau. Với Java 11+ có thể chọn `String::strip` khi cần xử lý khoảng trắng Unicode; `trim()` vẫn là API hợp lệ và có ý nghĩa trong ví dụ tương thích Java 8.

### Trường hợp C — Sắp xếp theo dữ liệu gốc hay dữ liệu đã biến đổi?

~~~java
// Sắp xếp số gốc rồi lấy trị tuyệt đối:
numbers.stream().sorted().map(Math::abs)

// Lấy trị tuyệt đối rồi sắp xếp theo trị tuyệt đối:
numbers.stream().map(Math::abs).sorted()
~~~

Hai pipeline có thể cho **thứ tự kết quả khác nhau**. Không được chuyển `map` qua `sorted` chỉ vì muốn tối ưu. Với phép biến đổi không bảo toàn thứ tự (ví dụ `abs`, đổi đơn vị có làm tròn, lấy độ dài chuỗi), vị trí `sorted` quyết định “đang sắp xếp theo tiêu chí nào”.

Với đối tượng nghiệp vụ, `sorted(Comparator.comparingInt(...))` thể hiện tiêu chí rõ hơn. Nếu muốn sắp xếp theo thuộc tính của đối tượng gốc, có thể lọc rồi sắp xếp đối tượng trước khi trích xuất trường; nếu muốn sắp xếp theo giá trị được tạo ra bởi `map`, cần đặt sort sau phép biến đổi đó. Luôn kiểm tra kiểu phần tử tại điểm gọi `sorted`.

### Trường hợp D — `filter` và `sorted`

Khi predicate chỉ phụ thuộc từng phần tử, comparator và predicate không có side effect, và yêu cầu cuối là sắp xếp **các phần tử được giữ lại theo cùng comparator**, thường nên:

~~~java
stream.filter(predicate).sorted(comparator)
~~~

thay vì:

~~~java
stream.sorted(comparator).filter(predicate)
~~~

Lọc sớm làm `k` nhỏ hơn trước bước sort. Chẳng hạn 100.000 phần tử, chỉ 2.000 phần tử hợp lệ: sort 2.000 phần tử thường rẻ hơn sort 100.000 phần tử. Tuy nhiên, khi có `limit`/`skip`, phụ thuộc thứ tự, comparator xử lý giá trị khác nhau, hoặc các hàm có side effect, **không được tự ý hoán đổi** mà không chứng minh kết quả tương đương.

## 3. Ví dụ hoàn chỉnh: cùng dữ liệu, khác thứ tự, khác kết quả

Lưu mã sau vào tệp `StreamOrderExample.java`:

~~~java
import java.util.Arrays;
import java.util.Comparator;
import java.util.List;
import java.util.stream.Collectors;

public class StreamOrderExample {
    public static void main(String[] args) {
        List<String> rawNames =
                Arrays.asList("  Nga  ", " ", "Lan", "Nam", "  An ");

        List<String> cleaned = rawNames.stream()
                .map(String::trim)
                .filter(name -> !name.isEmpty())
                .sorted()
                .collect(Collectors.toList());
        System.out.println("cleaned = " + cleaned);

        List<Integer> numbers = Arrays.asList(-10, 2, -3, 4, 7, -2);

        List<Integer> evenAbs = numbers.stream()
                .filter(n -> n % 2 == 0)
                .map(Math::abs)
                .sorted()
                .collect(Collectors.toList());
        System.out.println("evenAbs = " + evenAbs);

        List<Integer> sortThenAbs = numbers.stream()
                .sorted()
                .map(Math::abs)
                .collect(Collectors.toList());
        List<Integer> absThenSort = numbers.stream()
                .map(Math::abs)
                .sorted()
                .collect(Collectors.toList());
        System.out.println("sortThenAbs = " + sortThenAbs);
        System.out.println("absThenSort = " + absThenSort);

        List<Integer> greatest3 = numbers.stream()
                .sorted(Comparator.reverseOrder())
                .limit(3)
                .collect(Collectors.toList());
        List<Integer> first3Sorted = numbers.stream()
                .limit(3)
                .sorted(Comparator.reverseOrder())
                .collect(Collectors.toList());
        System.out.println("greatest3 = " + greatest3);
        System.out.println("first3Sorted = " + first3Sorted);
    }
}
~~~

Biên dịch và chạy với JDK 17+ (mã cũng dùng được với Java 8):

~~~bash
javac -encoding UTF-8 StreamOrderExample.java
java StreamOrderExample
~~~

Đầu ra chính xác:

~~~text
cleaned = [An, Lan, Nam, Nga]
evenAbs = [2, 2, 4, 10]
sortThenAbs = [10, 3, 2, 2, 4, 7]
absThenSort = [2, 2, 3, 4, 7, 10]
greatest3 = [7, 4, 2]
first3Sorted = [2, -3, -10]
~~~

Giải thích:

- `cleaned` cần chuẩn hóa trước khi xác định “rỗng”.
- `evenAbs` chỉ biến đổi các số chẵn của dữ liệu gốc và sau đó mới sắp xếp kết quả.
- `sortThenAbs` giữ thứ tự theo **số gốc**, còn `absThenSort` sắp xếp theo **trị tuyệt đối**.
- `greatest3` lấy ba giá trị lớn nhất của toàn bộ đầu vào (với dữ liệu này). `first3Sorted` chỉ lấy ba phần tử **đầu tiên theo encounter order**, rồi sắp xếp ba phần tử đó. Đảo `sorted` và `limit` làm đổi bài toán.

## 4. Cân nhắc chi phí khi xây dựng pipeline

**Ưu tiên giảm số phần tử trước công việc đắt đỏ khi đúng ngữ nghĩa.** Một predicate rẻ, có khả năng loại nhiều phần tử, nên thường đứng trước mapper nặng hoặc sort. Nếu có nhiều filter độc lập, có thể cân nhắc độ chọn lọc và chi phí mỗi predicate; nhưng đừng đổi thứ tự nếu điều kiện phụ thuộc kết quả bước trước, có thể ném lỗi khác nhau, hoặc yêu cầu nghiệp vụ đòi đúng trình tự.

**Chỉ sort khi cần thứ tự.** `filter` và `map` thông thường không cần giữ tất cả phần tử trong bộ đệm; `sorted` thì cần. Nếu chỉ cần tổng/đếm/kiểm tra tồn tại, thường không cần `sorted` trước `sum`, `count`, `anyMatch`. Đừng thêm sort chỉ để kết quả “trông đẹp” khi không có yêu cầu thứ tự.

**Đừng nhầm “top K” với sort rẻ.** `sorted(comparator).limit(k)` biểu đạt đúng việc lấy K phần tử đứng đầu **sau khi sắp xếp**; cách triển khai thông thường vẫn cần xử lý dữ liệu để sort. Với dữ liệu rất lớn và K nhỏ, thuật toán dùng hàng đợi ưu tiên kích thước K có thể giảm chi phí xuống khoảng `O(n log K)` và bộ nhớ `O(K)`, nhưng đó là thiết kế thuật toán khác, cần chứng minh kết quả và đo đạc. `limit(k).sorted()` không tương đương vì nó chỉ sắp xếp tiền tố K phần tử đầu vào.

**Chú ý chi phí Comparator.** Với `sorted(Comparator.comparingInt(Item::getScore))`, comparator có thể được gọi nhiều lần. Tránh tính toán phức tạp, truy vấn I/O hoặc thay đổi trạng thái bên trong comparator. Nếu khóa sort rất đắt để tính, có thể tính một lần thành cấu trúc chứa phần tử và khóa rồi sắp xếp cấu trúc đó. Viết comparator đúng hợp đồng so sánh; không dùng phép trừ `a - b` để so sánh số nguyên vì có nguy cơ tràn số: dùng `Integer.compare(a, b)` hoặc `Comparator.comparingInt(...)`.

**Kiểm soát bộ nhớ và tính hữu hạn.** Sort trên tập phần tử khổng lồ gây áp lực bộ nhớ; với stream vô hạn, yêu cầu sắp xếp toàn bộ trước khi xuất kết quả không thể hoàn tất. Đảm bảo nguồn có giới hạn hoặc giới hạn dữ liệu **theo đúng ngữ nghĩa** trước khi sort.

**Không tự động chuyển sang parallel stream.** `sorted` là bước stateful gây đồng bộ/đệm đáng kể trong pipeline song song; nguồn nhỏ, mapper nhẹ hoặc comparator đắt có thể khiến `parallelStream()` chậm hơn. Chỉ áp dụng sau khi đo bằng dữ liệu đại diện; tối ưu hóa theo số liệu, không theo số dòng code.

## 5. Các lỗi dễ gặp và cách tránh

1. **Đặt `filter` trước khi tạo ra trường cần lọc.** Hỏi predicate đang nói về phần tử gốc hay phần tử sau `map`; với chuẩn hóa, chuyển kiểu hoặc tính điểm, đáp án có thể là “map trước”.
2. **Tự ý chuyển `sorted` qua `map`.** Chỉ hợp lệ khi có thể chứng minh tiêu chí và thứ tự kết quả không đổi. Ví dụ `Math::abs` cho thấy điều ngược lại.
3. **Cho rằng `sorted` giống `filter`/`map` về bộ nhớ.** `sorted` là stateful và có thể đệm toàn bộ dữ liệu; chi phí đáng kể nhất thường nằm ở đây.
4. **Đổi `sorted` với `limit`/`skip` mà không xem lại yêu cầu.** “Lấy K lớn nhất” khác “lấy K đầu tiên rồi sắp xếp”. Nguồn `List` có encounter order; nhiều nguồn như `HashSet` không có thứ tự duyệt bảo đảm.
5. **Cho rằng kết quả đã `sorted` thì `forEach` luôn in theo thứ tự.** Đặc biệt với parallel stream, `forEach` không bảo đảm thứ tự; nếu cần thứ tự quan sát được, dùng `forEachOrdered` hoặc gom kết quả vào danh sách có thứ tự.
6. **Sử dụng `sorted()` cho kiểu không có natural ordering, hoặc comparator không xử lý null.** Các phần tử phải so sánh được bằng `Comparable` hoặc cần `Comparator` phù hợp; với null, cân nhắc `Comparator.nullsFirst`/`nullsLast` theo nghiệp vụ.
7. **Dựa vào side effect trong `filter`, `map`, comparator hoặc `peek`.** Stream có thể tối ưu bỏ một số lần gọi, hoặc chạy trên các thread khác nhau; hàm xử lý nên non-interfering và stateless, không sửa nguồn đang duyệt.
8. **Nhầm hai API gom danh sách.** `collect(Collectors.toList())` tương thích Java 8 nhưng không bảo đảm danh sách trả về có thể sửa được; `Stream.toList()` (Java 16+) trả danh sách không sửa được. Lựa chọn theo môi trường và hợp đồng kết quả, không thay máy móc.

## 6. Checklist chọn thứ tự trong thực tế

1. Viết rõ **điều kiện chọn** (trên dữ liệu gốc hay sau chuyển đổi), **giá trị cần tạo**, **khóa cần sort**, và có cần giữ encounter order không.
2. Vẽ luồng dữ liệu theo kiểu phần tử: `Stream<T>` → (lọc `T`) → `Stream<T>` → (map thành `R`) → `Stream<R>` → (sort theo `R`).
3. Chỉ đẩy filter lên trước mapper/sort nếu predicate còn đúng trên kiểu và giá trị ở vị trí mới.
4. Chỉ đẩy sort trước/sau map nếu tiêu chí sắp xếp vẫn đúng; xem riêng các trường hợp có `limit`, `skip` và các giá trị bằng nhau.
5. Ước lượng số phần tử vào mỗi bước, chi phí của predicate/mapper/comparator, nhu cầu bộ nhớ; bỏ sort nếu terminal không cần thứ tự.
6. Kiểm tra với dữ liệu biên: danh sách rỗng, trùng khóa, số âm, null (nếu được phép), nguồn không có encounter order, số lượng rất lớn. Khi hiệu năng quan trọng, đo trên dữ liệu thực tế.

**Nguyên tắc cần nhớ:** Đặt phép toán theo **ngữ nghĩa của dữ liệu và kết quả**; khi nhiều cách là tương đương, ưu tiên lọc sớm trước biến đổi/sắp xếp tốn kém. `sorted` là điểm cần chú ý nhất về chi phí và bộ nhớ.

## Tài liệu chuẩn để đối chiếu

- [Java Stream API — `filter`, `map`, `sorted`, `limit`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Stream.html)
- [Java `java.util.stream` — pipeline, laziness, stateless/stateful, ordering, side effects](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/package-summary.html)
