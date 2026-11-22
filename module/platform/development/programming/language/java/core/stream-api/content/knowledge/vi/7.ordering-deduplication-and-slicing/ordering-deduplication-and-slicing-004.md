# Cắt lát dữ liệu bằng skip và limit

Khi một Stream chứa nhiều phần tử nhưng chương trình chỉ cần một đoạn, Java Stream API cung cấp hai phép toán trung gian là `skip(long n)` và `limit(long maxSize)`. Chúng thường đi cùng nhau để bỏ qua một số phần tử ở đầu và lấy một số lượng phần tử nhất định. Đây là kỹ thuật **cắt lát dữ liệu** (*slicing*), rất hữu ích khi hiển thị trang kết quả, lấy mẫu hữu hạn từ một nguồn dài hoặc kiểm soát số phần tử phải xử lý tiếp.

Bài học thuộc chương **Thứ tự, loại trùng và cắt lát** của module **JAVA_STREAM_API**. Trong mô hình xử lý khai báo bằng pipeline lười, `skip` và `limit` có liên hệ trực tiếp với `filter`, `map`, `sorted`, `distinct` và các phép toán kết thúc như `collect`, `reduce`. Hiểu đúng chúng cũng giúp tránh lỗi phân trang, chi phí lớn khi xử lý song song và các tình huống nguồn vô hạn không bao giờ trả kết quả.

## 1. Ý nghĩa chính xác của skip và limit

| Phép toán | Ý nghĩa | Đối số | Tính chất |
| --- | --- | --- | --- |
| `skip(n)` | Bỏ qua tối đa `n` phần tử đầu tiên **ở vị trí của bước đó** trong pipeline; chuyển tiếp các phần tử còn lại | Số `long` không âm | Trung gian, lười, có trạng thái vì phải theo dõi phần đầu đã bỏ |
| `limit(n)` | Chỉ cho tối đa `n` phần tử đầu tiên **ở vị trí của bước đó** đi tiếp | Số `long` không âm | Trung gian, lười, có trạng thái và có khả năng ngắn mạch (*short-circuiting*) |

Ví dụ, một nguồn có encounter order:

```text
Nguồn:                  [10, 20, 30, 40, 50, 60, 70, 80]
Sau skip(3):                     [40, 50, 60, 70, 80]
Sau limit(2):                    [40, 50]
```

Với một Stream có thứ tự, `skip(3).limit(2)` lấy hai phần tử ở **vị trí thứ tư và thứ năm** (nếu có). Hai phương thức này **không sửa Collection gốc**, không tạo danh sách con ngay khi được gọi và không tự kích hoạt việc duyệt phần tử.

Các trường hợp biên:

- `skip(0)` không bỏ phần tử nào; `limit(0)` không cho phần tử nào đi tiếp.
- Nếu nguồn hữu hạn có ít hơn `n` phần tử, `skip(n)` cho Stream rỗng.
- Nếu nguồn hữu hạn có ít hơn `n` phần tử, `limit(n)` cho tất cả phần tử còn lại.
- `skip(-1)` và `limit(-1)` ném `IllegalArgumentException` vì đối số âm.
- Khi nguồn không có encounter order, không thể dựa vào khái niệm “phần tử đầu tiên” theo thứ tự người dùng mong đợi; xem mục 6.

## 2. Chạy thử trên List: nhìn thấy lát cắt

Chương trình hoàn chỉnh sau dùng Java 8 trở lên:

```java
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;

public class SliceDemo {
    public static void main(String[] args) {
        List<String> names = Arrays.asList(
            "An", "Binh", "Chi", "Dung", "Ha", "Khoa", "Linh"
        );

        List<String> middle = names.stream()
            .skip(2)
            .limit(3)
            .collect(Collectors.toList());

        List<String> fromFourth = names.stream()
            .skip(3)
            .collect(Collectors.toList());

        List<String> firstTwo = names.stream()
            .limit(2)
            .collect(Collectors.toList());

        System.out.println(middle);
        System.out.println(fromFourth);
        System.out.println(firstTwo);
        System.out.println(names);
    }
}
```

Kết quả:

```text
[Chi, Dung, Ha]
[Dung, Ha, Khoa, Linh]
[An, Binh]
[An, Binh, Chi, Dung, Ha, Khoa, Linh]
```

Chú ý rằng nguồn `names` không thay đổi. `collect(Collectors.toList())` mới là bước tạo danh sách kết quả. Trong ví dụ này, danh sách nguồn có thứ tự theo vị trí, nên đoạn được lấy có thể xác định rõ.

## 3. Vì sao hai phép toán đều lười nhưng chỉ limit ngắn mạch?

Xét pipeline:

```java
List<Integer> output = Arrays.asList(1, 2, 3, 4, 5, 6, 7, 8)
    .stream()
    .filter(n -> n % 2 == 0)
    .skip(1)
    .limit(2)
    .map(n -> n * 10)
    .collect(Collectors.toList());

// output = [40, 60]
```

Các bước có ý nghĩa như sau:

1. `filter` giữ các số chẵn, tạo dãy logic `[2, 4, 6, 8]`.
2. `skip(1)` bỏ số chẵn đầu tiên là `2`, còn `[4, 6, 8]`.
3. `limit(2)` chỉ yêu cầu tối đa hai phần tử tiếp theo, là `4` và `6`.
4. `map` nhân hai số đó với `10`; `collect` thu kết quả `[40, 60]`.

**Tính lười:** `filter`, `skip`, `limit` và `map` mô tả các bước xử lý; việc tiêu thụ thực tế bắt đầu khi `collect` được gọi. Pipeline tuần tự có thể kết hợp các bước trên khi đi qua từng phần tử, không nhất thiết tạo các danh sách trung gian như dãy logic minh họa.

**Khả năng dừng sớm:** `limit(2)` có thể khiến pipeline dừng yêu cầu phần tử ngay khi đã nhận đủ hai phần tử từ `skip`. Ngược lại, `skip(2)` tự nó không giới hạn số lượng phần tử còn lại: terminal muốn lấy hết kết quả sau `skip` vẫn phải tiếp tục cho tới khi nguồn kết thúc.

Không dùng việc in log trong `peek` hoặc tác dụng phụ của `map` để xác nhận mọi phần tử đã được xử lý đúng một lần. Java có quyền áp dụng các tối ưu hóa bảo toàn kết quả; chẳng hạn, `count()` trên nguồn biết trước kích thước có thể tính số phần tử sau `skip`/`limit` mà không cần gọi mọi lambda.

## 4. Đảo vị trí skip, limit và filter sẽ đổi bài toán

### skip trước limit khác limit trước skip

```java
List<Integer> input = Arrays.asList(10, 20, 30, 40, 50, 60);

List<Integer> a = input.stream()
    .skip(2)
    .limit(3)
    .collect(Collectors.toList()); // [30, 40, 50]

List<Integer> b = input.stream()
    .limit(3)
    .skip(2)
    .collect(Collectors.toList()); // [30]
```

Pipeline `a` bỏ hai phần tử đầu **rồi lấy ba phần tử tiếp theo**. Pipeline `b` chỉ xét ba phần tử đầu của nguồn **rồi bỏ hai phần tử** trong nhóm ba đó. Cả hai đều hợp lệ nhưng trả lời câu hỏi khác nhau.

### filter trước skip khác skip trước filter

```java
List<Integer> numbers = Arrays.asList(1, 2, 3, 4, 5, 6, 7, 8, 9, 10);

List<Integer> afterFiltering = numbers.stream()
    .filter(n -> n % 2 == 0)
    .skip(2)
    .limit(3)
    .collect(Collectors.toList()); // [6, 8, 10]

List<Integer> beforeFiltering = numbers.stream()
    .skip(2)
    .filter(n -> n % 2 == 0)
    .limit(3)
    .collect(Collectors.toList()); // [4, 6, 8]
```

Nếu yêu cầu là “bỏ hai **số chẵn** đầu tiên”, đặt `filter` trước `skip`. Nếu yêu cầu là “bỏ hai **bản ghi đầu nguồn** rồi lọc số chẵn”, đặt `skip` trước `filter`.

Một cách tự kiểm tra khi viết pipeline là đọc từng bước thành câu đầy đủ: **lọc gì, theo thứ tự nào, bỏ bao nhiêu, lấy bao nhiêu?**

## 5. Kết hợp sorted, distinct để cắt đúng đối tượng

Phân trang danh sách hoặc chọn một đoạn dữ liệu thường đòi hỏi **thứ tự xác định**. Khi nguồn vốn chưa có thứ tự phù hợp, hãy sắp xếp trước khi cắt:

```java
List<Integer> scores = Arrays.asList(9, 1, 7, 3, 6, 2);

List<Integer> sortedWindow = scores.stream()
    .sorted()
    .skip(2)
    .limit(2)
    .collect(Collectors.toList()); // [3, 6]

List<Integer> sortOnlyWindow = scores.stream()
    .skip(2)
    .limit(2)
    .sorted()
    .collect(Collectors.toList()); // [3, 7]
```

`sorted().skip(2).limit(2)` lấy phần tử thứ ba và thứ tư **trong dãy đã sắp xếp**. `skip(2).limit(2).sorted()` lại chọn hai phần tử theo thứ tự nguồn ban đầu, rồi mới sắp xếp riêng hai phần tử ấy.

Tương tự, nếu cần trang thứ hai của **danh sách mã không trùng nhau**, đặt `distinct()` trước `skip()`:

```java
List<String> codes = Arrays.asList("A", "A", "B", "C", "C", "D");

List<String> uniquePage = codes.stream()
    .distinct()
    .skip(1)
    .limit(2)
    .collect(Collectors.toList()); // [B, C]

List<String> slicedThenUnique = codes.stream()
    .skip(1)
    .limit(2)
    .distinct()
    .collect(Collectors.toList()); // [A, B]
```

`distinct` trên Stream có thứ tự giữ lại lần xuất hiện đầu tiên của mỗi giá trị. Đặt nó sau slicing sẽ loại trùng **chỉ trong phần dữ liệu đã lấy**, khiến số phần tử và vị trí trang có thể khác mong đợi.

Lưu ý về chi phí: `sorted` thường cần tiếp nhận toàn bộ đầu vào hữu hạn trước khi có thể phát kết quả đã sắp xếp. Vì vậy `sorted().skip(...).limit(...)` vẫn có thể phải đọc và sắp xếp cả nguồn; `limit` không làm bước `sorted` trước đó trở thành thao tác rẻ.

## 6. Encounter order: “đầu” và “sau” chỉ rõ ràng khi có thứ tự

`skip` và `limit` đặc biệt dễ hiểu trên nguồn có **encounter order**: thứ tự phần tử mà Stream nhận từ nguồn.

| Nguồn | Encounter order | Ý nghĩa của slicing |
| --- | --- | --- |
| `List.stream()` | Có, theo thứ tự List | `skip` và `limit` lấy đoạn theo vị trí List |
| `LinkedHashSet.stream()` | Có, theo thứ tự chèn | Đoạn theo thứ tự chèn của các giá trị không trùng |
| `TreeSet.stream()` | Có, theo thứ tự được sắp xếp | Đoạn theo thứ tự sắp xếp của Set |
| `HashSet.stream()` | Không bảo đảm | Không nên coi kết quả là “n phần tử đầu tiên” ổn định |
| `stream.unordered()` | Bỏ ràng buộc về encounter order | Cho phép các triển khai chọn phần tử theo cách không giữ thứ tự nguồn |

Ví dụ:

```java
Set<Integer> values = new HashSet<>(
    Arrays.asList(40, 10, 30, 20)
);

List<Integer> unpredictable = values.stream()
    .limit(2)
    .collect(Collectors.toList());
// Không dựa vào việc kết quả là [10, 20] hoặc một cặp cụ thể.

List<Integer> predictable = values.stream()
    .sorted()
    .skip(1)
    .limit(2)
    .collect(Collectors.toList());
// [20, 30]
```

Với nguồn không có encounter order, một phép `limit(n)` có thể chọn **bất kỳ** `n` phần tử phù hợp theo hợp đồng Stream; `skip(n)` có thể bỏ đi một tập `n` phần tử không xác định. Kết quả đúng về số lượng nhưng không bảo đảm ổn định giữa các lần chạy.

**Nếu ứng dụng cần phân trang ổn định, hãy tạo thứ tự có quy tắc và có yếu tố phân biệt khi trùng khóa**, ví dụ sắp xếp theo thời điểm rồi theo ID duy nhất. Chỉ sắp xếp theo một trường mà nhiều bản ghi cùng giá trị có thể chưa đủ để cố định vị trí trang khi dữ liệu và thứ tự nguồn thay đổi.

## 7. Ứng dụng phân trang với skip và limit

Giả sử trang được đánh số bắt đầu từ **1**, kích thước trang là `pageSize`. Công thức tính số phần tử cần bỏ:

\[
\text{offset} = (\text{pageNumber} - 1) \times \text{pageSize}
\]

Sau đó:

```java
stream
    .skip(offset)
    .limit(pageSize)
    .collect(Collectors.toList());
```

Ví dụ hoàn chỉnh với danh sách mã đơn hàng:

```java
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;

public class OrderPagingDemo {
    public static List<String> page(
            List<String> orderIds, int pageNumber, int pageSize) {
        if (pageNumber < 1 || pageSize < 1) {
            throw new IllegalArgumentException(
                "pageNumber và pageSize phải lớn hơn 0"
            );
        }

        long offset = Math.multiplyExact(
            (long) pageNumber - 1,
            (long) pageSize
        );

        return orderIds.stream()
            .sorted() // Với ví dụ này, mã là khóa duy nhất và thứ tự mong muốn.
            .skip(offset)
            .limit(pageSize)
            .collect(Collectors.toList());
    }

    public static void main(String[] args) {
        List<String> ids = Arrays.asList(
            "ORD-104", "ORD-102", "ORD-105", "ORD-101", "ORD-103"
        );

        System.out.println(page(ids, 1, 2)); // [ORD-101, ORD-102]
        System.out.println(page(ids, 2, 2)); // [ORD-103, ORD-104]
        System.out.println(page(ids, 3, 2)); // [ORD-105]
        System.out.println(page(ids, 4, 2)); // []
    }
}
```

Trong đoạn mã:

1. Kiểm tra `pageNumber` và `pageSize` dương để tránh tham số sai.
2. Ép sang `long` trước khi nhân và dùng `Math.multiplyExact` để phát hiện tràn số; `skip` nhận đối số `long`.
3. Sắp xếp mã ID trước khi lấy trang để cùng một danh sách đầu vào cho kết quả xác định.
4. Dùng `skip(offset).limit(pageSize)`, trang vượt cuối danh sách nhận `List` rỗng.

Một vài giới hạn thực tế:

- `skip` **không tương đương truy cập ngẫu nhiên O(1)**. Khi offset lớn, pipeline có thể cần duyệt hoặc bỏ nhiều phần tử; Stream không tự biến thành công cụ phân trang hiệu quả cho bảng dữ liệu rất lớn.
- `sorted()` ở ví dụ có thể đọc và lưu toàn bộ dữ liệu đầu vào để sắp xếp. Nếu dữ liệu đã có thứ tự phù hợp và ổn định, không cần sắp xếp lặp lại.
- Dữ liệu thay đổi giữa hai lần lấy trang có thể làm bản ghi bị lặp hoặc bị bỏ sót khi dùng offset. Với cơ sở dữ liệu, thường nên thực hiện phân trang tại truy vấn với `ORDER BY` xác định và cân nhắc phân trang theo khóa (*keyset/cursor pagination*) nếu tập dữ liệu lớn hoặc liên tục thay đổi.
- `skip`/`limit` làm việc trên **Stream tại thời điểm tiêu thụ**; chúng không tạo snapshot và cũng không khóa Collection khỏi sửa đổi đồng thời.

## 8. Cắt lát nguồn rất dài hoặc vô hạn

Tính lười cho phép lấy một đoạn hữu hạn từ nguồn có thể sinh vô số phần tử:

```java
List<Integer> window = IntStream.iterate(0, n -> n + 1)
    .skip(100)
    .limit(5)
    .boxed()
    .collect(Collectors.toList());

// [100, 101, 102, 103, 104]
```

Trong ví dụ tuần tự này, pipeline bỏ 100 số đầu rồi thu năm số tiếp theo; `limit(5)` cho phép terminal `collect` hoàn tất mà không phải tiêu thụ vô hạn phần tử.

Tuy nhiên, `skip` và `limit` **không tự đảm bảo mọi pipeline sẽ kết thúc**. Nếu bước `filter` phía trước không cho đủ phần tử, giới hạn phía sau không bao giờ đạt:

```java
// Ví dụ để phân tích, KHÔNG chạy: nguồn chỉ sinh số dương.
// Stream.iterate(BigInteger.ONE, n -> n.add(BigInteger.ONE))
//     .filter(n -> n.signum() < 0)
//     .skip(2)
//     .limit(3)
//     .collect(Collectors.toList());
```

Hoặc nếu đặt `sorted()` **trước** giới hạn trên nguồn vô hạn, phép sắp xếp thông thường cần nhận hết nguồn trước khi xuất phần tử đầu tiên:

```java
// KHÔNG chạy: sorted() chờ toàn bộ nguồn vô hạn.
// IntStream.iterate(1, n -> n + 1).sorted().limit(5).sum();

// Có thể kết thúc: chỉ sắp xếp năm phần tử đã lấy.
int sum = IntStream.iterate(1, n -> n + 1)
    .limit(5)
    .sorted()
    .sum(); // 15
```

Với nguồn có thể chặn khi lấy phần tử (như đọc dữ liệu ngoài), `limit` cũng **không phải timeout**. Nó đặt giới hạn số lượng, không phải giới hạn thời gian.

## 9. Chạy song song: chi phí giữ đúng vị trí cắt

Cùng một pipeline có thể được tạo từ `collection.parallelStream()` hoặc chuyển chế độ bằng `parallel()`:

```java
List<Integer> values = IntStream.rangeClosed(1, 20)
    .boxed()
    .collect(Collectors.toList());

List<Integer> page = values.parallelStream()
    .skip(5)
    .limit(4)
    .collect(Collectors.toList());

System.out.println(page); // [6, 7, 8, 9]
```

Do List có encounter order, kết quả slicing vẫn phải tuân thủ thứ tự ấy, kể cả khi một số phần tử được xử lý đồng thời. Chính yêu cầu “bỏ **đúng năm phần tử đầu** và lấy **đúng bốn phần tử tiếp**” có thể làm `skip`/`limit` trên Stream song song tốn nhiều công sức phối hợp, nhất là khi nguồn khó chia hoặc kích thước không biết trước.

Nếu **thực sự không quan tâm phần tử nào được chọn**, có thể bỏ ràng buộc thứ tự để triển khai có thêm tự do tối ưu:

```java
List<Integer> sample = values.parallelStream()
    .unordered()
    .skip(5)
    .limit(4)
    .collect(Collectors.toList());

// Có tối đa bốn phần tử, nhưng không dựa vào chúng là [6, 7, 8, 9].
```

`unordered()` **không xáo trộn ngẫu nhiên** dữ liệu và cũng không hứa kết quả là một mẫu ngẫu nhiên công bằng; nó chỉ gỡ ràng buộc encounter order. Với phân trang thực tế, thường **không** nên dùng nó vì ứng dụng cần vị trí và thứ tự trang có thể dự đoán.

Đặc tính `SIZED`/`SUBSIZED` của `Spliterator` giúp Stream tối ưu cắt lát trên một số nguồn có kích thước và phân vùng rõ ràng. Kết quả thực tế vẫn phụ thuộc nguồn, kích thước, phép toán phía trước, terminal và môi trường chạy. Chuyển sang `parallelStream()` không bảo đảm nhanh hơn; chỉ nên quyết định sau khi đo đạc trên dữ liệu đại diện.

## 10. Những lỗi dễ gặp

| Tình huống | Hệ quả | Cách xử lý |
| --- | --- | --- |
| `limit` đặt trước `skip` mà muốn lấy trang kích thước cố định | Trang có thể ngắn hoặc rỗng bất ngờ | Thường dùng `skip(offset).limit(pageSize)` |
| `skip` đặt trước `filter` mà muốn bỏ các phần tử **đã lọc** | Bỏ phần tử của nguồn gốc, không phải của tập kết quả lọc | Đặt `filter` trước `skip` |
| `distinct` đặt sau slicing khi muốn phân trang giá trị duy nhất | Các trang có thể thiếu giá trị hoặc trùng giữa trang | Loại trùng trước khi cắt |
| Phân trang `HashSet` mà không sắp xếp | Không có cam kết về trang nào chứa phần tử nào | Dùng thứ tự rõ ràng, ví dụ `sorted` |
| Tính `pageNumber * pageSize` bằng `int` | Có nguy cơ tràn số trước khi truyền cho `skip` | Kiểm tra tham số, chuyển sang `long` và cân nhắc `Math.multiplyExact` |
| Dùng `skip(1_000_000)` trên nguồn lớn rồi mong truy cập tức thì | Có thể tốn nhiều lượt duyệt và xử lý | Cân nhắc truy vấn tại nguồn, chỉ số hoặc cursor |
| Gọi hai terminal trên cùng Stream | Stream bị tiêu thụ, thường gây `IllegalStateException` | Tạo Stream mới cho mỗi lần tiêu thụ |
| Cho rằng `limit` giới hạn thời gian hoặc luôn chấm dứt nguồn vô hạn | Có thể chờ mãi khi nguồn bị chặn hoặc không có đủ phần tử vượt qua bước trước | Thiết kế điều kiện dừng và cơ chế hủy riêng |

## 11. Bài tập tự kiểm tra

**Bài 1 — Dự đoán kết quả.** Với `List<Integer> data = Arrays.asList(2, 4, 6, 8, 10, 12);`, hai biểu thức sau có kết quả gì?

```java
data.stream().skip(2).limit(2).collect(Collectors.toList());
data.stream().limit(2).skip(2).collect(Collectors.toList());
```

**Đáp án:** Biểu thức đầu trả `[6, 8]`; biểu thức sau trả `[]` vì chỉ cho hai phần tử đầu đi qua rồi bỏ cả hai.

**Bài 2 — Lọc rồi phân trang.** Từ các số từ 1 đến 15, chọn trang thứ hai (đánh số từ 1), mỗi trang ba **số lẻ**, giữ thứ tự tăng dần.

```java
List<Integer> pageTwo = IntStream.rangeClosed(1, 15)
    .filter(n -> n % 2 != 0)
    .skip(3)
    .limit(3)
    .boxed()
    .collect(Collectors.toList()); // [7, 9, 11]
```

**Giải thích:** Các số lẻ là `[1, 3, 5, 7, 9, 11, 13, 15]`. Bỏ ba số lẻ đầu rồi lấy ba số lẻ tiếp theo.

**Bài 3 — Chọn vị trí của distinct.** Dữ liệu `["A", "B", "A", "C", "D", "C"]`; yêu cầu lấy hai **giá trị khác nhau** sau giá trị khác nhau đầu tiên. Viết pipeline đúng.

```java
List<String> unique = Arrays.asList("A", "B", "A", "C", "D", "C")
    .stream()
    .distinct()
    .skip(1)
    .limit(2)
    .collect(Collectors.toList()); // [B, C]
```

**Giải thích:** `distinct()` phải xử lý toàn bộ phần đầu cần thiết trước khi xác định vị trí trên dãy không trùng.

**Bài 4 — Trang cuối.** Một List có bảy phần tử. Phân trang kích thước ba, đánh số trang từ 1. Trang 1, 2, 3 và 4 có bao nhiêu phần tử?

**Đáp án:** Lần lượt là `3, 3, 1, 0`. `skip(9)` trên List bảy phần tử cho Stream rỗng; `limit(3)` không thể tự tạo thêm phần tử.

**Bài 5 — Hiệu năng.** Vì sao `parallelStream().sorted().skip(1000).limit(10)` chưa chắc nhanh hơn pipeline tuần tự?

**Đáp án:** `sorted` thường phải thu và sắp xếp toàn bộ nguồn trước khi cắt, trong khi `skip`/`limit` phải giữ đúng vị trí theo encounter order. Chi phí chia việc, sắp xếp và ghép kết quả có thể lớn hơn lợi ích song song, đặc biệt với nguồn nhỏ hoặc khó chia.

## Ghi nhớ

`skip(n)` bỏ tối đa `n` phần tử đầu **tại vị trí được đặt**, còn `limit(n)` chỉ cho tối đa `n` phần tử kế tiếp đi tiếp và có thể giúp dừng sớm. Cặp `skip(offset).limit(pageSize)` là cách cắt lát và phân trang thông dụng của Java Stream API, nhưng kết quả chỉ thực sự có ý nghĩa theo **vị trí xác định** khi pipeline có encounter order phù hợp. Hãy suy luận thứ tự `filter`, `distinct`, `sorted` với slicing trước khi tối ưu, kiểm soát tràn offset và chi phí bỏ qua lượng lớn dữ liệu, đồng thời chú ý nguồn vô hạn và ràng buộc thứ tự khi chạy song song.
