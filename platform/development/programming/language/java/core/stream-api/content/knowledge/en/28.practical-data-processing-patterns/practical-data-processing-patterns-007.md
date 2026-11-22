# Phân trang dữ liệu trong bộ nhớ và giới hạn của `skip`, `limit`

## 1. Mục tiêu bài học và tình huống thực tế

Trong **Java Stream API** (`JAVA_STREAM_API`), xử lý dữ liệu khai báo thường gồm một nguồn, các bước trung gian lazy như `filter` và `map`, rồi một terminal operation như `collect`. Khi dữ liệu được lưu sẵn trong RAM nhưng giao diện chỉ hiển thị từng phần, ta cần **phân trang** (*pagination*): lấy một lát cắt của tập kết quả theo số trang và kích thước trang.

Ví dụ: ứng dụng có 23 sản phẩm, màn hình chỉ hiển thị tối đa 5 sản phẩm mỗi trang. Người dùng chọn trang thứ ba; chương trình phải lấy đúng các sản phẩm của trang đó, đồng thời biết tổng số trang và có còn trang tiếp theo hay không.

Stream API cung cấp hai thao tác trung gian:

- `skip(n)`: bỏ qua **tối đa `n` phần tử đầu** của stream theo encounter order, nếu stream có thứ tự.
- `limit(n)`: giữ **tối đa `n` phần tử đầu** của đoạn stream còn lại.

Một phép phân trang cơ bản:

```java
List<T> items = source.stream()
    .skip(offset)
    .limit(pageSize)
    .collect(Collectors.toList());
```

Đây là một **mẫu xử lý dữ liệu thực tế**, nhưng bản thân `skip` và `limit` không tự giải quyết mọi vấn đề: cách đánh số trang, tràn `offset`, tổng số kết quả, dữ liệu rỗng, lọc và sắp xếp, thay đổi dữ liệu giữa các lần lấy trang, chi phí khi bỏ qua rất nhiều phần tử và ngữ nghĩa của parallel stream.

Sau bài này, bạn sẽ có thể:

1. Tính `offset` từ `pageIndex` và `pageSize`, xử lý trang rỗng cùng đầu vào không hợp lệ.
2. Giải thích cách `skip`, `limit` tương tác với `filter`, `sorted`, `distinct` và `map`.
3. Chọn giữa `List.subList` và pipeline Stream khi dữ liệu đã nằm trong bộ nhớ.
4. Thiết kế một `Page<T>` chứa dữ liệu, tổng bản ghi, tổng trang và thông tin điều hướng.
5. Phân biệt **thứ tự gặp**, thứ tự hiển thị và tính ổn định giữa các yêu cầu phân trang.
6. Nhận diện giới hạn hiệu năng khi dữ liệu lớn, cần trang sâu hoặc chạy song song.
7. Viết kiểm thử bảo đảm không mất/lặp phần tử khi ghép các trang trong một snapshot dữ liệu.

Bài thuộc chương **Mẫu xử lý dữ liệu thực tế** và kết nối với grouping, collector, Spliterator, giới hạn trạng thái, tài nguyên cũng như hiệu năng của Java Stream API.

## 2. Quy ước trang và công thức cơ bản

Trong bài, **`pageIndex` bắt đầu từ 0**:

| `pageIndex` | Trang hiển thị cho người dùng | `pageSize` | `offset` | Vị trí được lấy |
| ---: | ---: | ---: | ---: | --- |
| 0 | 1 | 5 | 0 | 0–4 |
| 1 | 2 | 5 | 5 | 5–9 |
| 2 | 3 | 5 | 10 | 10–14 |
| 3 | 4 | 5 | 15 | 15–19 |
| 4 | 5 | 5 | 20 | 20–22 (nếu có 23 phần tử) |
| 5 | 6 | 5 | 25 | Rỗng |

Công thức:

```text
offset = pageIndex * pageSize

fromInclusive = offset
toExclusive   = min(totalElements, offset + pageSize)

totalPages = ceil(totalElements / pageSize)
```

**Cảnh báo:** tính `offset` bằng biểu thức `int pageIndex * int pageSize` có thể tràn `int` **trước khi kết quả được gán vào `long`**. Cần ép kiểu trước khi nhân hoặc dùng `Math.multiplyExact`.

```java
int pageIndex = 2;
int pageSize = 5;

// Tốt với hai giá trị int không âm: chuyển sang long trước phép nhân.
long offset = (long) pageIndex * pageSize;

System.out.println(offset); // 10
```

Nếu API của bạn nhận `pageIndex` kiểu `long` hoặc có thể nhận số cực lớn, dùng `Math.multiplyExact(pageIndex, (long) pageSize)` để **phát hiện tràn `long`**. Đừng xử lý tràn bằng cách để offset trở thành số âm rồi gọi `skip`.

### 2.1. Điều kiện đầu vào hợp lệ

Một quy ước rõ ràng:

- `pageIndex >= 0`.
- `pageSize > 0`.
- `offset >= 0` và phép nhân không tràn.
- Trang vượt quá cuối dữ liệu **trả danh sách rỗng**, không phải lỗi, nếu đó là hợp đồng API.
- Dữ liệu rỗng có `totalElements = 0`, `totalPages = 0` theo quy ước của bài.

`skip(n)` và `limit(n)` sẽ ném `IllegalArgumentException` nếu `n < 0`. Đặc biệt, `limit(0)` là hợp lệ nhưng trả kết quả rỗng; **không nên đồng nhất** điều đó với một `pageSize = 0` được chấp nhận trong nghiệp vụ phân trang, vì nó không tạo trang có thể điều hướng.

Nếu giao diện bắt đầu đếm từ 1, chuyển sang chỉ số nội bộ một cách tường minh:

```java
long pageNumber = 3L; // Người dùng chọn trang thứ 3.
if (pageNumber < 1) {
    throw new IllegalArgumentException(
        "pageNumber phai bat dau tu 1");
}
long pageIndex = pageNumber - 1L; // 2
```

Không trộn `pageNumber` (1-based) với `pageIndex` (0-based) trong cùng một công thức. Đây là nguyên nhân phổ biến của lỗi lệch một trang (*off-by-one*).

## 3. Ví dụ đầu tiên với `skip` và `limit`

Ví dụ Java 8+:

```java
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;

public class SimplePaging {
    public static void main(String[] args) {
        List<String> ten = Arrays.asList(
            "An", "Binh", "Chi", "Dung", "Giang",
            "Ha", "Hieu", "Khanh", "Lan", "Minh",
            "Nam", "Oanh"
        );

        int pageSize = 5;
        int pageIndex = 1; // Trang thứ 2 theo giao diện.

        long offset = (long) pageIndex * pageSize;

        List<String> page = ten.stream()
            .skip(offset)
            .limit(pageSize)
            .collect(Collectors.toList());

        System.out.println(page);
        // [Ha, Hieu, Khanh, Lan, Minh]
    }
}
```

Diễn giải:

```text
Nguồn: [An, Binh, Chi, Dung, Giang, Ha, Hieu, Khanh, Lan, Minh, Nam, Oanh]
                 skip(5) ──────────────┘
Còn lại: [Ha, Hieu, Khanh, Lan, Minh, Nam, Oanh]
                 limit(5) ───────────┘
Kết quả: [Ha, Hieu, Khanh, Lan, Minh]
```

`skip` **không thay đổi `ten`**, còn `limit` không tạo một danh sách độc lập nếu chưa có terminal operation. `collect` mới tiêu thụ pipeline và tạo collection kết quả.

### 3.1. Các trường hợp biên

```java
List<Integer> so = Arrays.asList(10, 20, 30);

System.out.println(
    so.stream().skip(0).limit(2)
        .collect(Collectors.toList())
); // [10, 20]

System.out.println(
    so.stream().skip(2).limit(2)
        .collect(Collectors.toList())
); // [30]

System.out.println(
    so.stream().skip(3).limit(2)
        .collect(Collectors.toList())
); // []

System.out.println(
    so.stream().skip(100).limit(2)
        .collect(Collectors.toList())
); // []

System.out.println(
    so.stream().skip(1).limit(0)
        .collect(Collectors.toList())
); // []
```

Khi `skip` lớn hơn số phần tử, stream không còn gì để `limit` lấy. **Không có phần tử nào được tạo thêm** để lấp đầy một trang.

Cũng cần nhớ stream **chỉ được dùng một lần**: trong ví dụ này, mỗi câu lệnh tạo một stream mới bằng `so.stream()`. Không lưu một `Stream` rồi gọi `collect` lần thứ hai trên chính stream đã tiêu thụ.

## 4. Thứ tự thao tác quyết định nội dung mỗi trang

`skip` và `limit` thực hiện cắt trên **dòng phần tử ở vị trí mà chúng xuất hiện trong pipeline**. Thay đổi vị trí `filter`, `sorted` hoặc `distinct` có thể thay đổi hoàn toàn câu trả lời.

### 4.1. Lọc trước, rồi mới phân trang

Giả sử nguồn là `[1, 2, 3, ..., 10]`. Giao diện chỉ hiển thị **số chẵn**, mỗi trang 3 số. Trang có `pageIndex = 0` phải hiển thị `[2, 4, 6]`, còn trang tiếp theo `[8, 10]`.

```java
import java.util.stream.IntStream;

List<Integer> dung = IntStream.rangeClosed(1, 10)
    .boxed()
    .filter(n -> n % 2 == 0)
    .skip(0)
    .limit(3)
    .collect(Collectors.toList());

System.out.println(dung); // [2, 4, 6]
```

Nếu cắt trang **trước** khi lọc:

```java
List<Integer> saiYeuCau = IntStream.rangeClosed(1, 10)
    .boxed()
    .skip(0)
    .limit(3)
    .filter(n -> n % 2 == 0)
    .collect(Collectors.toList());

System.out.println(saiYeuCau); // [2]
```

Pipeline thứ hai không sai về mặt Java, nhưng trả một **trang chỉ có một phần tử** dù tập kết quả lọc còn đủ số chẵn. Hai cách phục vụ **hai nghiệp vụ khác nhau**:

- `filter(...).skip(...).limit(...)`: phân trang **tập kết quả đã lọc**.
- `skip(...).limit(...).filter(...)`: chọn một lát cắt **dữ liệu gốc** rồi chỉ lọc trong lát cắt đó.

Trong hệ thống tìm kiếm và danh sách có bộ lọc, **lọc trước phân trang** thường mới là yêu cầu đúng.

### 4.2. Sắp xếp trước, rồi mới phân trang

```java
List<Integer> so = Arrays.asList(9, 1, 7, 2, 5);

List<Integer> dung = so.stream()
    .sorted()
    .skip(2)
    .limit(2)
    .collect(Collectors.toList());

List<Integer> khac = so.stream()
    .skip(2)
    .limit(2)
    .sorted()
    .collect(Collectors.toList());

System.out.println(dung); // [5, 7]
System.out.println(khac); // [2, 7]
```

`sorted().skip(2).limit(2)` chọn phần tử thứ 3 và thứ 4 của **toàn bộ tập đã sắp xếp**. `skip(2).limit(2).sorted()` chỉ sắp xếp hai phần tử của lát cắt gốc. Nếu giao diện muốn **toàn bộ kết quả** theo một tiêu chí, phải sắp xếp trước khi cắt trang.

### 4.3. Loại trùng trước, rồi mới phân trang

```java
List<String> ma = Arrays.asList("A", "B", "A", "C", "D");

List<String> uniquePage = ma.stream()
    .distinct()
    .skip(2)
    .limit(2)
    .collect(Collectors.toList());

List<String> pageThenDistinct = ma.stream()
    .skip(2)
    .limit(2)
    .distinct()
    .collect(Collectors.toList());

System.out.println(uniquePage);        // [C, D]
System.out.println(pageThenDistinct);  // [A, C]
```

Nếu yêu cầu là phân trang **các mã duy nhất**, nên đặt `distinct` trước `skip`/`limit`. `distinct` sau khi cắt trang không ngăn một mã trùng xuất hiện ở **hai trang khác nhau**.

### 4.4. `map` trước hay sau khi cắt?

Nếu `map` là một phép biến đổi **thuần, một-một** (không làm mất hay thêm phần tử) và thứ tự không thay đổi, có thể biến đổi sau `skip`/`limit` để chỉ xử lý phần tử của trang cần trả:

```java
List<String> ten = Arrays.asList("java", "go", "kotlin", "rust");

List<String> page = ten.stream()
    .skip(2)
    .limit(2)
    .map(String::toUpperCase)
    .collect(Collectors.toList());

System.out.println(page); // [KOTLIN, RUST]
```

Nhưng nếu cần **sắp xếp hoặc lọc theo giá trị đã biến đổi**, phải làm `map` đủ sớm. Và nếu `map` có tác dụng phụ, chuyển vị trí có thể thay đổi số lần/điều kiện gọi; tác dụng phụ không nên là cơ sở logic của một pipeline phân trang.

## 5. Muốn trang ổn định, phải xác định encounter order

Trên `ArrayList` hoặc mảng, stream có encounter order theo vị trí phần tử. Với nguồn **không có thứ tự được bảo đảm** như `HashSet`, hoặc pipeline gọi `unordered()`, ý nghĩa "bỏ qua 10 phần tử đầu" **không đại diện cho 10 phần tử nghiệp vụ cố định**.

```java
import java.util.HashSet;
import java.util.Set;

Set<Integer> nguon = new HashSet<>(Arrays.asList(5, 1, 4, 2, 3));

List<Integer> page = nguon.stream()
    .skip(2)
    .limit(2)
    .collect(Collectors.toList());

// Không dựa vào nội dung cụ thể của page để định nghĩa trang.
```

Muốn phân trang có thứ tự theo giá trị, xác lập nó bằng `sorted`:

```java
List<Integer> page = nguon.stream()
    .sorted()
    .skip(2)
    .limit(2)
    .collect(Collectors.toList());

System.out.println(page); // [3, 4]
```

`unordered()` **không bắt buộc xáo trộn** phần tử ngay trong một lần chạy, nhưng bỏ ràng buộc encounter order, nên không phù hợp khi người dùng đòi trang 1, 2, 3 có nội dung nhất quán theo một thứ tự đã xác định.

### 5.1. Thứ tự gặp ổn định chưa đủ nếu nguồn thay đổi

Ngay cả khi luôn dùng `List`, dữ liệu có thể thay đổi **giữa hai yêu cầu phân trang**:

```text
Ban đầu:  [A, B, C, D, E, F]
Trang 1:  [A, B, C]

Chèn X vào đầu trước khi tải trang 2:
Sau chèn: [X, A, B, C, D, E]
Trang 2 (skip 3): [C, D, E]
```

Phần tử `C` bị lặp ở cả hai trang. Nếu có xóa hoặc di chuyển mục, người dùng có thể **bỏ lỡ** một phần tử.

Điều này **không phải bug riêng của `skip`**: offset pagination phụ thuộc vào vị trí trong tập tại **thời điểm truy vấn**. Nếu cần giao diện phân trang nhất quán qua nhiều yêu cầu, hãy dùng một snapshot ổn định, version của dữ liệu hoặc chiến lược cursor/keyset tùy hệ thống.

### 5.2. Sắp xếp theo khóa duy nhất để tránh hòa thứ hạng

Khi nhiều bản ghi có cùng điểm hoặc thời gian, chỉ `sorted` theo một trường không tạo ra thứ tự nghiệp vụ **duy nhất**. Đối với nguồn đã có thứ tự, Java có thể giữ thứ tự gặp của các bản ghi bằng nhau theo comparator; nhưng nếu nguồn không bảo đảm thứ tự hoặc dữ liệu được nạp lại theo thứ tự khác, trang có thể đổi nội dung.

Nên thêm **tie-breaker** như mã định danh duy nhất:

```java
Comparator<SanPham> theoGiaRoiMa =
    Comparator.comparingLong((SanPham p) -> p.gia)
        .thenComparing(p -> p.ma);
```

Giả định `SanPham` có các trường `gia` kiểu `long` và `ma` kiểu `String` không rỗng. Comparator có khóa phụ độc nhất giúp tổng thứ tự rõ ràng, nhưng không thể **chống dữ liệu bị chèn/xóa giữa các yêu cầu**; muốn điều đó phải cố định snapshot hoặc dùng cơ chế phân trang khác.

## 6. Tính `offset` an toàn, tránh tràn số

Đừng dùng công thức sau nếu số trang có thể lớn:

```java
int pageIndex = 1_500_000_000;
int pageSize = 100;

// SAI: phép nhân int có thể tràn trước khi gán vào long.
long offsetSai = pageIndex * pageSize;
```

Một hàm xác thực và tính offset cho API 0-based:

```java
static long checkedOffset(long pageIndex, int pageSize) {
    if (pageIndex < 0) {
        throw new IllegalArgumentException("pageIndex phai >= 0");
    }
    if (pageSize <= 0) {
        throw new IllegalArgumentException("pageSize phai > 0");
    }

    try {
        return Math.multiplyExact(pageIndex, (long) pageSize);
    } catch (ArithmeticException ex) {
        throw new IllegalArgumentException("offset tran long", ex);
    }
}
```

`Math.multiplyExact(long, long)` của Java 8 phát hiện tràn thay vì âm thầm tạo offset sai. Nếu offset hợp lệ nhưng vượt quá số phần tử, kết quả trang **rỗng**; đây là hai trạng thái khác nhau:

- **Invalid request**: pageIndex âm, pageSize không dương hoặc phép nhân tràn.
- **Valid empty page**: offset hợp lệ nhưng không còn phần tử.

Không nên cố "sửa" yêu cầu bằng cách `Math.min(offset, total)` rồi gán lại pageIndex hoặc âm thầm quay về trang đầu. Người gọi cần biết trang họ yêu cầu không còn dữ liệu.

### 6.1. Tổng số trang không dùng phép làm tròn sai

Với `totalElements` không âm và `pageSize > 0`:

```java
static long totalPages(long totalElements, int pageSize) {
    if (totalElements < 0 || pageSize <= 0) {
        throw new IllegalArgumentException("metadata khong hop le");
    }

    return totalElements == 0
        ? 0
        : 1 + (totalElements - 1) / pageSize;
}
```

Không dùng `(totalElements + pageSize - 1) / pageSize` nếu `totalElements` có thể gần `Long.MAX_VALUE` vì phép cộng có thể tràn. Dạng `1 + (totalElements - 1) / pageSize` tránh cộng `pageSize` vào một tổng quá lớn.

Ví dụ:

```text
totalElements = 0, pageSize = 5  → totalPages = 0
totalElements = 5, pageSize = 5  → totalPages = 1
totalElements = 6, pageSize = 5  → totalPages = 2
totalElements = 23, pageSize = 5 → totalPages = 5
```

Quy ước `totalPages = 0` khi không có bản ghi là lựa chọn rõ ràng. Một số giao diện vẫn hiển thị trang rỗng số 1; đó là **quy ước trình bày**, không có nghĩa trong dữ liệu thực tồn tại một trang có phần tử.

## 7. `List.subList`: một lựa chọn trực tiếp hơn khi nguồn đã nằm trong RAM

Khi đã có `List<T>` hoàn chỉnh, đặc biệt là `ArrayList`, bạn có thể cắt trang bằng chỉ số:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

List<Integer> so = Arrays.asList(10, 20, 30, 40, 50, 60, 70);
int from = 3;
int to = Math.min(from + 3, so.size());

List<Integer> page = new ArrayList<>(so.subList(from, to));

System.out.println(page); // [40, 50, 60]
```

Phương thức `subList(fromInclusive, toExclusive)` lấy đoạn trong khoảng `[from, to)`. Các chỉ số phải nằm trong phạm vi hợp lệ và `from <= to`; nếu không, list có thể ném ngoại lệ kiểm tra chỉ số.

### 7.1. View so với bản sao

**`source.subList(from, to)` trả một *view* gắn với list gốc**, không phải một snapshot độc lập. Vì vậy:

```java
List<String> source = new ArrayList<>(
    Arrays.asList("A", "B", "C", "D"));

List<String> view = source.subList(1, 3);
System.out.println(view); // [B, C]

view.set(0, "X");
System.out.println(source); // [A, X, C, D]
```

Thay đổi nội dung qua `view` được phản ánh ở nguồn. Nếu nguồn bị sửa cấu trúc bên ngoài view, hành vi của view có thể trở nên không xác định theo hợp đồng `List.subList`.

Khi trả dữ liệu cho một lớp khác hoặc cần snapshot phần tử trang, nên tạo bản sao:

```java
List<String> copy = new ArrayList<>(source.subList(1, 3));
```

`copy` tách cấu trúc danh sách khỏi nguồn. Đây là **bản sao nông**: nếu phần tử là đối tượng mutable, sửa thuộc tính của đối tượng vẫn được quan sát qua mọi tham chiếu cùng đối tượng.

### 7.2. Chọn `subList` hay `stream().skip().limit()`?

| Tiêu chí | `List.subList(from, to)` | `stream().skip(offset).limit(size)` |
| --- | --- | --- |
| Nguồn | Cần `List` | Bất kỳ nguồn `Stream` phù hợp |
| Phân trang trực tiếp theo chỉ số | Rõ ràng | Biểu đạt bằng số phần tử bỏ qua/giữ lại |
| Kết quả ban đầu | View của list gốc | Stream trung gian, chưa là list |
| Muốn list độc lập | Bọc `new ArrayList<>(...)` | Dùng `collect(Collectors.toList())` |
| Có pipeline `filter` / `map` | Cần xử lý trước hoặc kết hợp bước khác | Tự nhiên trong pipeline |
| Trang sâu trên `ArrayList` | Lấy lát cắt bằng chỉ số, tránh đi tuần tự qua mọi phần tử bỏ qua | `skip` có thể phải thực hiện công việc để tiến qua đầu nguồn; runtime có thể tối ưu tùy nguồn |
| Nguồn `LinkedList` | Truy cập theo chỉ số / duyệt lát cắt có thể tốn kém | Cũng cần đi qua phần tử; đo nếu dữ liệu lớn |

**Không khẳng định `skip` luôn O(offset) trong mọi trường hợp.** Với nguồn `SIZED` / `SUBSIZED` có thể chia theo vị trí, runtime có thể tối ưu đoạn cần đọc. Nhưng API không cam kết truy cập ngẫu nhiên tức thời cho mọi `Stream`, đặc biệt với pipeline có `filter` hoặc nguồn dữ liệu tuần tự.

Khi nguồn đã là `ArrayList` lớn và yêu cầu chỉ chọn một đoạn, `subList` rồi sao chép đoạn đó thường là cách **đơn giản và dễ dự đoán chi phí hơn**.

## 8. Ví dụ đầy đủ: `Page<T>` với metadata và hai cách lấy trang

Bài toán thực tế thường cần nhiều hơn một list: **tổng số bản ghi**, **tổng số trang**, **chỉ số trang** và **có trang kế tiếp hay không**. Chương trình Java 8+ dưới đây triển khai:

- `checkedOffset` để xác thực đầu vào và chống tràn.
- `pageByStream` dùng `skip/limit`.
- `pageByList` dùng `subList`.
- `Page<T>` chứa nội dung và metadata; nội dung được bọc thành danh sách không cho phép sửa cấu trúc.

Toàn bộ chương trình là một file `InMemoryPaginationDemo.java`:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;
import java.util.Objects;
import java.util.stream.Collectors;

public class InMemoryPaginationDemo {
    static final class Page<T> {
        final long pageIndex;
        final int pageSize;
        final long totalElements;
        final long totalPages;
        final List<T> items;

        Page(long pageIndex, int pageSize,
                long totalElements, List<T> items) {

            this.pageIndex = pageIndex;
            this.pageSize = pageSize;
            this.totalElements = totalElements;
            this.totalPages = totalElements == 0
                ? 0
                : 1 + (totalElements - 1) / pageSize;

            // Sao chép cấu trúc; không lộ list có thể sửa ra ngoài.
            this.items = Collections.unmodifiableList(
                new ArrayList<>(items));
        }

        boolean hasNext() {
            return pageIndex < totalPages - 1;
        }

        @Override
        public String toString() {
            return "Page{index=" + pageIndex
                + ", size=" + pageSize
                + ", total=" + totalElements
                + ", pages=" + totalPages
                + ", next=" + hasNext()
                + ", items=" + items + "}";
        }
    }

    static long checkedOffset(long pageIndex, int pageSize) {
        if (pageIndex < 0 || pageSize <= 0) {
            throw new IllegalArgumentException(
                "pageIndex >= 0 va pageSize > 0");
        }

        try {
            return Math.multiplyExact(pageIndex, (long) pageSize);
        } catch (ArithmeticException ex) {
            throw new IllegalArgumentException(
                "offset vuot mien long", ex);
        }
    }

    static <T> Page<T> pageByStream(
            List<T> source, long pageIndex, int pageSize) {

        Objects.requireNonNull(source, "source");
        long offset = checkedOffset(pageIndex, pageSize);

        List<T> items;
        if (offset >= source.size()) {
            items = Collections.emptyList();
        } else {
            items = source.stream()
                .skip(offset)
                .limit(pageSize)
                .collect(Collectors.toList());
        }

        return new Page<>(pageIndex, pageSize,
            source.size(), items);
    }

    static <T> Page<T> pageByList(
            List<T> source, long pageIndex, int pageSize) {

        Objects.requireNonNull(source, "source");
        long offset = checkedOffset(pageIndex, pageSize);

        List<T> items;
        if (offset >= source.size()) {
            items = Collections.emptyList();
        } else {
            int from = (int) offset;
            int to = (int) Math.min(
                (long) source.size(), offset + pageSize);

            items = new ArrayList<>(source.subList(from, to));
        }

        return new Page<>(pageIndex, pageSize,
            source.size(), items);
    }

    public static void main(String[] args) {
        List<Integer> data = Arrays.asList(
            1, 2, 3, 4, 5, 6, 7,
            8, 9, 10, 11, 12
        );

        System.out.println(pageByStream(data, 0, 5));
        System.out.println(pageByList(data, 1, 5));
        System.out.println(pageByStream(data, 2, 5));
        System.out.println(pageByList(data, 3, 5));
    }
}
```

Kết quả:

```text
Page{index=0, size=5, total=12, pages=3, next=true, items=[1, 2, 3, 4, 5]}
Page{index=1, size=5, total=12, pages=3, next=true, items=[6, 7, 8, 9, 10]}
Page{index=2, size=5, total=12, pages=3, next=false, items=[11, 12]}
Page{index=3, size=5, total=12, pages=3, next=false, items=[]}
```

Hàm `hasNext()` dựa trên metadata của **snapshot dữ liệu dùng tại lần phân trang đó**. Với trang vượt quá `totalPages`, nó trả `false`. Nếu nguồn bị một thread khác sửa trong lúc đang đọc, `source.size()` hoặc việc duyệt có thể không còn nhất quán; mã mẫu giả định **nguồn không thay đổi trong suốt lời gọi**.

Lớp `Page<T>` là một mẫu học tập chứ không phải định dạng API bắt buộc. Ứng dụng có thể thêm `hasPrevious`, đường dẫn điều hướng hoặc tiêu chí sắp xếp; cần giữ hợp đồng chỉ số và cách tính tổng nhất quán.

**Lưu ý về bất biến:** `Collections.unmodifiableList` chỉ ngăn sửa cấu trúc list thông qua kết quả; nó không làm các phần tử mutable trở thành bất biến.


## 9. Mẫu thực tế: lọc, sắp xếp ổn định, rồi phân trang

Một hệ thống danh sách sản phẩm thường có nhiều yêu cầu cùng lúc:

- Chỉ hiển thị sản phẩm **đang hoạt động**.
- Sắp xếp theo **giá giảm dần**.
- Với các sản phẩm đồng giá, sắp xếp theo **mã tăng dần** để có thứ tự xác định.
- Trả trang `pageIndex` với `pageSize` cho giao diện.
- Tính tổng số kết quả sau lọc, **không** tính bằng số dòng của trang hiện tại.

Thứ tự pipeline phù hợp:

```text
Danh sách trong RAM
    |
  filter(active)
    |
  sorted(price DESC, id ASC)
    |
  skip(pageIndex * pageSize)
    |
  limit(pageSize)
    |
  collect
```

### 9.1. Chương trình Java 8+ hoàn chỉnh

Đoạn sau tự chứa và có thể đặt trong file `ProductPaginationExample.java`:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Comparator;
import java.util.List;
import java.util.stream.Collectors;

public class ProductPaginationExample {
    static final class Product {
        final String id;
        final String name;
        final long price;
        final boolean active;

        Product(String id, String name,
                long price, boolean active) {
            this.id = id;
            this.name = name;
            this.price = price;
            this.active = active;
        }

        @Override
        public String toString() {
            return id;
        }
    }

    public static void main(String[] args) {
        List<Product> source = Arrays.asList(
            new Product("P04", "Chuot", 100, true),
            new Product("P01", "Ban phim", 120, true),
            new Product("P03", "Tai nghe", 120, false),
            new Product("P02", "Loa", 120, true),
            new Product("P06", "Cap", 70, true),
            new Product("P05", "Pad", 100, true),
            new Product("P07", "Gia do", 90, true)
        );

        Comparator<Product> byPriceThenId =
            Comparator.comparingLong((Product p) -> p.price)
                .reversed()
                .thenComparing(p -> p.id);

        // Cố định tập kết quả sau lọc/sắp xếp,
        // rồi lấy nhiều trang từ cùng một danh sách.
        List<Product> filteredSorted = source.stream()
            .filter(p -> p.active)
            .sorted(byPriceThenId)
            .collect(Collectors.toList());

        int pageSize = 3;
        int total = filteredSorted.size();
        int totalPages = total == 0
            ? 0 : 1 + (total - 1) / pageSize;

        for (int pageIndex = 0; pageIndex < totalPages;
                pageIndex++) {
            int from = pageIndex * pageSize;
            int to = Math.min(from + pageSize, total);

            List<Product> page = new ArrayList<>(
                filteredSorted.subList(from, to));

            System.out.println(
                "Trang " + (pageIndex + 1) + ": " + page);
        }

        System.out.println("Tong: " + total);
        System.out.println("So trang: " + totalPages);
    }
}
```

Kết quả:

```text
Trang 1: [P01, P02, P04]
Trang 2: [P05, P07, P06]
Tong: 6
So trang: 2
```

**Phân tích:** sản phẩm `P03` không hoạt động nên bị loại trước khi đếm hoặc phân trang. `P01` và `P02` cùng giá 120 nhưng có thứ tự do khóa phụ `id` xác định. Không cần chạy lại `filter` và `sorted` cho mỗi trang vì ta đã tạo **một danh sách kết quả sau xử lý**.

**Điều kiện quan trọng:** danh sách `filteredSorted` không được thay đổi cấu trúc trong khi đang phục vụ các trang từ snapshot đó. Các phần tử `Product` trong mã có trường `final`, thuận lợi để giữ giá trị ổn định; nếu phần tử thực tế là đối tượng mutable, việc sao chép list chưa tạo bản sao sâu của các sản phẩm.

### 9.2. Khi nào tạo snapshot là hợp lý?

Tạo danh sách đã lọc/sắp xếp là lựa chọn tốt khi:

- Dữ liệu đã tồn tại trong RAM, đủ nhỏ để lưu thêm một danh sách.
- Người dùng có thể duyệt **nhiều trang** của cùng một tập kết quả.
- Lọc và sắp xếp tốn chi phí, không nên chạy lại mỗi lần chọn trang.
- Cần một tập kết quả **nhất quán** trong khoảng thời gian giao diện điều hướng.

Đổi lại, việc giữ snapshot tiêu tốn bộ nhớ theo số phần tử đã lọc. Với danh sách rất lớn hoặc cập nhật liên tục, cần chiến lược khác như cache có thời hạn, snapshot versioned, xử lý tại nguồn hoặc phân trang ở cơ sở dữ liệu.

## 10. Tổng số bản ghi phải được tính sau lọc, không phải sau cắt trang

Giả sử có 10 số từ 1 đến 10, nhưng chỉ 5 số chẵn hợp lệ. Nếu `pageSize = 3`:

```java
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.IntStream;

List<Integer> even = IntStream.rangeClosed(1, 10)
    .filter(n -> n % 2 == 0)
    .boxed()
    .collect(Collectors.toList());

int totalElements = even.size(); // 5
int pageSize = 3;
int totalPages = 1 + (totalElements - 1) / pageSize; // 2

List<Integer> firstPage = even.stream()
    .limit(pageSize)
    .collect(Collectors.toList());

System.out.println(firstPage); // [2, 4, 6]
System.out.println(totalElements); // 5
System.out.println(totalPages); // 2
```

Đừng dùng `firstPage.size()` làm tổng số kết quả; nó chỉ là **số phần tử của trang**. Cũng đừng lấy `source.size()` khi nguồn vẫn còn các phần tử không thỏa bộ lọc.

Nếu không lưu danh sách `even`, có thể đếm và lấy trang bằng **hai stream khác nhau**:

```java
long total = source.stream()
    .filter(predicate)
    .count();

List<Item> items = source.stream()
    .filter(predicate)
    .skip(offset)
    .limit(pageSize)
    .collect(Collectors.toList());
```

Đây là **mã minh họa kiểu tổng quát**: cần khai báo `Item`, `source`, `predicate` và `offset` trong chương trình thực tế. Hai lượt duyệt phải sử dụng cùng bộ lọc và nguồn ổn định để metadata khớp với dữ liệu trang. Ngoài ra, cách làm này **đánh giá bộ lọc hai lần**, có thể đắt với dữ liệu lớn.

Nếu nguồn là tập kết quả xử lý trong bộ nhớ, thu thành list một lần thường đơn giản hơn:

```text
filter/sort → List kết quả ổn định → total = size()
                                 → subList cho từng trang
```

Trường hợp cần các thống kê phức tạp hơn, có thể sử dụng collector kết hợp hoặc cấu trúc dữ liệu phụ trợ, nhưng phải đảm bảo tính đúng và tài nguyên tương xứng.

## 11. Giới hạn thực sự của `skip` và `limit`

`skip` và `limit` là **stateful intermediate operations**: chúng cần theo dõi số phần tử đã bỏ qua hoặc đã giữ. Cả hai hoạt động trên **dòng phần tử của pipeline**, không cung cấp một API truy cập ngẫu nhiên cho mọi nguồn.

### 11.1. Trang sâu có thể phải duyệt nhiều phần tử

```java
List<Integer> page = java.util.stream.IntStream
    .range(0, 1_000_000)
    .boxed()
    .skip(900_000)
    .limit(20)
    .collect(Collectors.toList());

System.out.println(page.get(0)); // 900000
System.out.println(page.size()); // 20
```

Về mặt ngữ nghĩa, pipeline bỏ 900.000 phần tử trước khi lấy 20. **Không được khẳng định mọi triển khai sẽ thực hiện 900.000 lần `tryAdvance`**: nguồn có kích thước và khả năng chia theo đoạn có thể giúp runtime tối ưu. Tuy nhiên, ở nguồn tuần tự không hỗ trợ truy cập theo vị trí, bỏ rất nhiều phần tử có thể thực sự tốn thời gian tương ứng.

`skip` là lựa chọn tiện lợi cho pipeline; nó **không hứa** độ phức tạp O(1) đối với mọi nguồn hoặc mọi chuỗi intermediate operation.

### 11.2. `filter` trước `skip` có thể làm trang sâu đắt hơn

```java
List<Integer> page = java.util.stream.IntStream
    .range(0, 1_000_000)
    .filter(n -> n % 17 == 0)
    .skip(20_000)
    .limit(10)
    .boxed()
    .collect(Collectors.toList());
```

Để bỏ qua **20.000 giá trị thỏa bộ lọc**, pipeline có thể phải kiểm tra nhiều hơn 20.000 giá trị nguồn. `skip(20_000)` đếm **các phần tử đi qua `filter`**, không đếm mọi phần tử ban đầu.

Trên dữ liệu đã có trong RAM, nếu người dùng thường xuyên chuyển giữa các trang, đáng cân nhắc **lọc một lần và lưu snapshot** thay vì lặp lại một bộ lọc đắt cho từng yêu cầu.

### 11.3. `sorted` có thể cần toàn bộ dữ liệu đầu vào

```java
List<Integer> page = numbers.stream()
    .sorted()
    .skip(100)
    .limit(20)
    .collect(Collectors.toList());
```

Với dữ liệu tổng quát chưa sắp xếp, `sorted` là thao tác có trạng thái và thường cần nắm các phần tử đầu vào để xác lập thứ tự toàn cục. Vì vậy, `limit(20)` phía sau **không bảo đảm** chỉ có 120 phần tử được quan sát hoặc chỉ cần một lượng bộ nhớ nhỏ.

Nếu dữ liệu đã được sắp xếp trước, tránh sắp xếp lại mỗi trang. Nếu chỉ cần top-k trên một nguồn rất lớn, một thuật toán chọn top-k dùng hàng đợi ưu tiên có thể phù hợp hơn việc sắp xếp toàn bộ; nhưng đó là bài toán khác với phân trang tùy ý theo chỉ số.

### 11.4. Nguồn vô hạn: cần xem vị trí các phép toán

```java
import java.util.stream.LongStream;

List<Long> page = LongStream.iterate(0L, n -> n + 1L)
    .skip(1_000_000L)
    .limit(5)
    .boxed()
    .collect(Collectors.toList());

System.out.println(page);
// [1000000, 1000001, 1000002, 1000003, 1000004]
```

Nguồn ở đây có thể phát vô hạn phần tử. `limit(5)` bảo đảm pipeline này có thể dừng sau khi đã **bỏ qua** đủ số phần tử, nhưng phải thực hiện công việc để tới vị trí đó.

Ngược lại, một phép toán có trạng thái cần toàn bộ dữ liệu như `sorted()` trên nguồn vô hạn tổng quát có thể không bao giờ tạo ra phần tử kết quả. `limit` nằm **sau `sorted`** không tự biến nó thành thuật toán khả thi.

### 11.5. Trả `Stream<T>` ra ngoài không tự đóng tài nguyên

Với `List.stream()`, không có directory handle hoặc kết nối cơ sở dữ liệu do list cung cấp. Nhưng nếu đầu vào là nguồn I/O như `Files.lines(...)` hoặc `Files.walk(...)`, `skip`/`limit` **không tự giải phóng tài nguyên**. Dùng `try-with-resources`:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

static List<String> readLinesPage(
        Path path, long offset, long pageSize)
        throws IOException {

    if (offset < 0 || pageSize < 0) {
        throw new IllegalArgumentException("offset/size am");
    }

    try (Stream<String> lines =
            Files.lines(path, StandardCharsets.UTF_8)) {
        return lines.skip(offset)
            .limit(pageSize)
            .collect(Collectors.toList());
    }
}
```

Đoạn này chỉ minh họa **vòng đời tài nguyên**, không phải mẫu API phân trang dữ liệu trong RAM: khi lấy trang sâu từ tệp, phải đọc/bỏ qua nhiều dòng, đồng thời trạng thái tệp có thể thay đổi giữa các lần yêu cầu.

## 12. `parallelStream()` có giúp phân trang nhanh hơn không?

Có thể, nhưng không nên mặc định:

```java
List<Integer> page = java.util.stream.IntStream
    .range(0, 1_000_000)
    .parallel()
    .skip(900_000)
    .limit(20)
    .boxed()
    .collect(Collectors.toList());
```

`IntStream.range` có encounter order và biết kích thước, nên kết quả logic phải là 900.000 đến 900.019. Tuy nhiên, trên **ordered parallel stream**, `skip` và `limit` có thể đòi hỏi phối hợp giữa các phần việc để giữ chính xác đoạn phần tử theo vị trí. Hiệu năng phụ thuộc spliterator nguồn, kích thước dữ liệu, số lõi, chi phí mỗi phần tử và các thao tác ở trước.

Nếu chỉ muốn lấy lát cắt của một `ArrayList`, tạo tác vụ song song có thể tốn overhead **nhiều hơn** việc dùng `subList`. Nên đo với workload thật trước khi thêm `parallel()`.

### 12.1. `unordered()` không phù hợp cho trang theo vị trí

```java
List<Integer> page = java.util.stream.IntStream.range(0, 100)
    .parallel()
    .unordered()
    .skip(20)
    .limit(10)
    .boxed()
    .collect(Collectors.toList());
```

`unordered()` có thể cho phép runtime bỏ một số ràng buộc thứ tự và cải thiện hiệu năng trong những bài toán không quan tâm phần tử nào được chọn. Nhưng **không còn bảo đảm** đây là trang chứa 20, 21, ..., 29. Nếu giao diện cần vị trí cố định, đừng bỏ encounter order chỉ để tối ưu.

### 12.2. `forEach` không phải cách tạo trang có thứ tự

```java
List<Integer> output = new ArrayList<>();

// KHÔNG NÊN: ArrayList không an toàn để nhiều thread add,
// còn forEach không cam kết encounter order.
numbers.parallelStream()
    .skip(10)
    .limit(10)
    .forEach(output::add);
```

Thay bằng `collect(Collectors.toList())`, hoặc khi nguồn đã là `List` và chỉ cắt trang, dùng `subList` kèm bản sao. `forEachOrdered` có thể áp dụng hành động theo encounter order nhưng không giải quyết nhu cầu thu list tốt bằng collector phù hợp.

## 13. Lấy nhiều trang: nhất quán, bộ nhớ và thuật toán

Khi một người dùng lần lượt tải trang 0, 1, 2, ..., 100 từ **cùng một snapshot dữ liệu đã nằm trong RAM**, liên tục chạy:

```java
source.stream().skip((long) pageIndex * pageSize)
    .limit(pageSize)
    .collect(Collectors.toList());
```

có thể phải lặp lại công việc bỏ qua hoặc tính toán trong pipeline. Nếu dữ liệu đã có chỉ số và thứ tự, có thể chọn trực tiếp các đoạn bằng `subList`.

Để thiết kế ổn định:

1. Chuẩn hóa một tập kết quả theo **filter + thứ tự đầy đủ**.
2. Tạo snapshot theo phiên dữ liệu hoặc một thời điểm hợp lý.
3. Tính `totalElements` và `totalPages` trên **chính tập kết quả đó**.
4. Dùng offset hợp lệ để lấy trang từ snapshot.
5. Trả page metadata kèm nội dung; nếu snapshot thay đổi, xác định rõ cách invalidate hoặc làm mới.

Với nguồn rất lớn, việc đưa toàn bộ dữ liệu vào bộ nhớ có thể là sai kiến trúc. `skip` không làm giảm chi phí **tải mọi bản ghi** về RAM rồi mới cắt trang.

### 13.1. Khác biệt với phân trang ở cơ sở dữ liệu

Trong hệ thống có hàng triệu bản ghi, nên cân nhắc để nơi lưu trữ thực hiện việc lọc, sắp xếp và giới hạn thay vì tải hết:

```sql
-- Cú pháp ví dụ; LIMIT/OFFSET khác nhau giữa các hệ quản trị.
SELECT id, name, price
FROM products
WHERE active = TRUE
ORDER BY created_at DESC, id ASC
LIMIT :page_size OFFSET :offset;
```

Điều đó **không có nghĩa LIMIT/OFFSET trong cơ sở dữ liệu là O(1)**: truy vấn trang sâu vẫn có thể phải bỏ qua nhiều hàng, và việc chèn/xóa giữa các yêu cầu có thể gây trùng/bỏ sót.

Với luồng dữ liệu thay đổi nhanh và yêu cầu lấy trang tiếp theo, **keyset/cursor pagination** thường là một lựa chọn:

```text
Nhớ khóa của bản ghi cuối trong trang trước.
Trang tiếp theo lọc các bản ghi nằm sau khóa đó
theo cùng thứ tự xác định.
```

Keyset có những đánh đổi riêng: không tự hỗ trợ nhảy đến trang bất kỳ theo số thứ tự và cần khóa sắp xếp phù hợp. Đây là định hướng để chọn kiến trúc, không phải lời khuyên luôn thay `skip` trong mọi ứng dụng RAM.

## 14. Kiểm chứng phân trang bằng các ca biên (Java 8+)

Một cách kiểm tra tốt là **nối tất cả các trang hợp lệ** từ cùng một snapshot rồi so sánh với nguồn: không được bỏ sót hoặc lặp phần tử. Với dữ liệu có giá trị trùng, so sánh `List.equals` thay vì chỉ so sánh `Set`.

Chương trình sau dùng lại lớp `InMemoryPaginationDemo` ở mục 8; đặt cạnh file đó và chạy trên Java 8+:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.IntStream;

public class PaginationCheck {
    static void check(boolean ok, String message) {
        if (!ok) {
            throw new AssertionError(message);
        }
    }

    public static void main(String[] args) {
        List<Integer> source = IntStream.rangeClosed(1, 23)
            .boxed().collect(Collectors.toList());

        List<Integer> joined = new ArrayList<>();

        for (int page = 0; page < 5; page++) {
            InMemoryPaginationDemo.Page<Integer> a =
                InMemoryPaginationDemo.pageByStream(
                    source, page, 5);

            InMemoryPaginationDemo.Page<Integer> b =
                InMemoryPaginationDemo.pageByList(
                    source, page, 5);

            check(a.items.equals(b.items),
                "Hai cach cho trang khac nhau: " + page);
            check(a.totalElements == 23L, "Sai tong ban ghi");
            check(a.totalPages == 5L, "Sai tong so trang");

            joined.addAll(a.items);
        }

        check(joined.equals(source),
            "Mat hoac lap phan tu qua cac trang");

        check(InMemoryPaginationDemo.pageByStream(
                source, 4, 5).items
            .equals(Arrays.asList(21, 22, 23)),
            "Sai trang cuoi");

        check(InMemoryPaginationDemo.pageByStream(
                source, 5, 5).items.isEmpty(),
            "Trang vuot qua cuoi phai rong");

        check(InMemoryPaginationDemo.pageByList(
                Collections.<Integer>emptyList(), 0, 5)
            .totalPages == 0L, "Nguon rong");

        boolean rejectedNegative = false;
        try {
            InMemoryPaginationDemo.pageByStream(source, -1, 5);
        } catch (IllegalArgumentException ex) {
            rejectedNegative = true;
        }
        check(rejectedNegative, "Phai tu choi pageIndex am");

        boolean rejectedZeroSize = false;
        try {
            InMemoryPaginationDemo.pageByList(source, 0, 0);
        } catch (IllegalArgumentException ex) {
            rejectedZeroSize = true;
        }
        check(rejectedZeroSize, "Phai tu choi pageSize 0");

        boolean rejectedOverflow = false;
        try {
            InMemoryPaginationDemo.pageByStream(
                source, Long.MAX_VALUE, 2);
        } catch (IllegalArgumentException ex) {
            rejectedOverflow = true;
        }
        check(rejectedOverflow, "Phai phat hien tran offset");

        System.out.println("PASS: phan trang trong bo nho");
    }
}
```

Kết quả mong đợi:

```text
PASS: phan trang trong bo nho
```

Những ca này kiểm tra các hợp đồng cụ thể, chưa phải kiểm thử đồng thời khi một thread khác sửa nguồn. Nếu ứng dụng phục vụ nhiều yêu cầu cùng lúc, hãy quy định rõ cách tạo snapshot và phạm vi chia sẻ dữ liệu bất biến.

## 15. Các lỗi và hiểu nhầm thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Trang đầu không đúng | Nhầm `pageNumber` 1-based với `pageIndex` 0-based | Chuẩn hóa chỉ số ngay ở ranh giới API. |
| `skip` ném `IllegalArgumentException` | Offset âm, thường do đầu vào âm hoặc nhân tràn | Xác thực và dùng `Math.multiplyExact` cho long. |
| `limit(0)` làm giao diện luôn rỗng | `pageSize` được chấp nhận bằng 0 | Quy định `pageSize > 0`. |
| Trang cuối có ít phần tử | Không đủ dữ liệu để lấp đầy | Đây là hành vi bình thường, không thêm bản ghi giả. |
| `totalElements` bằng kích thước trang | Đếm sau `limit` | Đếm sau lọc nhưng **trước** cắt trang. |
| Một trang chỉ còn 1 bản ghi dù còn nhiều bản ghi hợp lệ | `filter` đặt sau `limit` | Lọc trước phân trang nếu phân trang tập đã lọc. |
| Trang bị trùng mã giữa các trang | `distinct` đặt sau `skip/limit` | Loại trùng trước phân trang nếu nghiệp vụ cần duy nhất. |
| Trang theo giá không đúng | `sorted` đặt sau `skip/limit` | Sắp xếp toàn bộ kết quả trước khi cắt. |
| Nội dung trang thay đổi giữa hai lần truy vấn | Nguồn thay đổi, không có snapshot | Dùng snapshot/version hoặc giải pháp cursor thích hợp. |
| Thứ tự thay đổi ở bản ghi đồng giá | Comparator thiếu khóa phụ duy nhất | Thêm tie-breaker ổn định. |
| `HashSet` cho các trang khó đoán | Nguồn không có encounter order | Thiết lập `sorted` với thứ tự rõ ràng. |
| `parallel().unordered()` lấy trang khác vị trí | Đã bỏ ràng buộc thứ tự gặp | Không dùng `unordered` khi phân trang vị trí. |
| `List.subList` bị ảnh hưởng khi nguồn đổi | `subList` là view, không phải bản sao | Sao chép `new ArrayList<>(subList)` và quản lý vòng đời nguồn. |
| Lấy trang sâu chậm | `skip` có thể phải bỏ qua lượng lớn dữ liệu | Dùng snapshot list có chỉ số, hoặc phân trang tại nguồn dữ liệu. |
| `sorted().limit(...)` dùng nhiều bộ nhớ | `sorted` có trạng thái và cần thông tin toàn nguồn | Cân nhắc sort sẵn, top-k hoặc giới hạn dữ liệu tại nguồn. |
| Tạo nhiều stream trên cùng instance đã tiêu thụ | Stream chỉ dùng một lần | Tạo stream mới từ nguồn, không tái sử dụng object Stream. |
| `forEach` song song làm mất thứ tự/dữ liệu | Sửa list ngoài pipeline không đồng bộ | Dùng `collect` hoặc `subList`. |
| Chỉ tải 20 bản ghi nhưng đã đọc cả bảng | Lọc và phân trang sau khi nạp toàn bộ | Đẩy lọc/phân trang xuống nguồn dữ liệu khi phù hợp. |

## 16. Bài tập thực hành

### Bài 1 — Công thức offset

Với `pageSize = 8`, tính `offset` cho các `pageIndex` 0, 1, 4. Danh sách có 35 phần tử, trang cuối theo chỉ số 0-based là trang nào và có mấy phần tử?

### Bài 2 — Phân trang số chẵn

Cho nguồn 1 đến 20, chỉ lấy số chẵn, mỗi trang 4 phần tử. Hãy viết pipeline cho `pageIndex = 1`. Dự đoán kết quả và giải thích vị trí của `filter` so với `skip`.

### Bài 3 — Cắt trang và sắp xếp

Nguồn `[9, 1, 7, 2, 5]`. So sánh:

```java
source.stream().sorted().skip(2).limit(2)
source.stream().skip(2).limit(2).sorted()
```

Kết quả có giống nhau không? Nếu giao diện muốn thứ tự tăng dần trên toàn bộ dữ liệu, cách nào đúng?

### Bài 4 — Trang vượt cuối và tham số sai

Một list có 12 phần tử, `pageSize = 5`. Hãy viết logic trả trang cho `pageIndex = 2`, 3 và -1 theo hợp đồng đã chọn. Có nên tự động chuyển yêu cầu trang 3 về trang 2 không?

### Bài 5 — Snapshot và view

Một `ArrayList` chứa `[A, B, C, D]`. Tạo `subList(1,3)` rồi gọi `view.set(0,"X")`. List gốc thế nào? Nếu muốn kết quả trang không thay đổi cấu trúc khi list gốc bị chỉnh sửa, cần làm gì?

### Bài 6 — Tổng số bản ghi và trang cuối

Có 23 bản ghi sau lọc, `pageSize = 5`. Hãy tính `totalPages` và các phần tử nếu bản ghi được đánh số 1..23 ở `pageIndex = 4`. Tại sao `pageIndex = 5` có thể trả trang rỗng mà không phải lỗi?

### Bài 7 — Quyết định kiến trúc

Ứng dụng có 2 triệu bản ghi trong database nhưng người dùng chỉ xem 20 bản ghi mỗi lần. Nêu vì sao việc tải tất cả vào RAM rồi gọi `skip`/`limit` không phải mặc định tốt. So sánh ưu/nhược của offset pagination tại database, snapshot ổn định và keyset/cursor pagination.

## 17. Đáp án và gợi ý

**Bài 1.** Công thức `offset = pageIndex * pageSize` cho kết quả 0, 8 và 32. Với 35 phần tử, `totalPages = 1 + (35 - 1) / 8 = 5`; trang cuối có `pageIndex = 4` và gồm 3 phần tử.

**Bài 2.** Các số chẵn là `[2,4,6,8,10,12,14,16,18,20]`. Trang thứ hai có `pageIndex = 1`, bỏ qua bốn số chẵn đầu rồi lấy bốn số tiếp theo:

```java
List<Integer> result = java.util.stream.IntStream
    .rangeClosed(1, 20)
    .filter(n -> n % 2 == 0)
    .skip(4)
    .limit(4)
    .boxed()
    .collect(Collectors.toList());

System.out.println(result); // [10, 12, 14, 16]
```

Lọc trước khi phân trang vì yêu cầu là trang của **các số chẵn**, không phải lọc bốn vị trí trong nguồn gốc.

**Bài 3.** `sorted().skip(2).limit(2)` cho `[5,7]`; `skip(2).limit(2).sorted()` cho `[2,7]`. Muốn toàn bộ dữ liệu có thứ tự tăng dần trước khi chọn trang thì dùng cách thứ nhất.

**Bài 4.** `pageIndex = 2` lấy phần tử thứ 11 và 12 (nếu 1-based trong phần hiển thị). `pageIndex = 3` có `offset=15` nên trả list rỗng theo hợp đồng. `pageIndex = -1` phải bị từ chối. Không tự chuyển trang 3 về trang 2 nếu API chưa định nghĩa hành vi đó.

**Bài 5.** `subList` là view; đổi phần tử đầu của view từ `B` thành `X` khiến nguồn thành `[A, X, C, D]`. Dùng `new ArrayList<>(source.subList(from, to))` để tách cấu trúc danh sách. Nếu phần tử là mutable object, cần thêm chính sách sao chép đối tượng khi yêu cầu snapshot sâu.

**Bài 6.** `totalPages=5`. Trang `pageIndex=4` lấy `[21,22,23]`. Trang `pageIndex=5` hợp lệ về tham số nhưng nằm ngoài dữ liệu, nên trả rỗng; phân biệt với chỉ số âm hoặc offset tràn.

**Bài 7.** Tải 2 triệu hàng tốn bộ nhớ, truyền dữ liệu và thời gian trước khi cắt 20 hàng. Offset pagination tại database giúp đẩy lọc/giới hạn xuống nguồn nhưng trang sâu vẫn có thể tốn chi phí, đồng thời dữ liệu thay đổi gây trùng/bỏ sót. Snapshot/version giúp các trang nhất quán trong một tập đã cố định nhưng tốn quản lý/bộ nhớ. Keyset/cursor thường thuận lợi cho "trang tiếp theo" trên thứ tự có khóa ổn định, nhưng khó nhảy đến một trang bất kỳ theo chỉ số và cần thiết kế khóa/điều kiện truy vấn phù hợp.

## 18. Checklist áp dụng trong ứng dụng

Trước khi phát hành một API phân trang trong bộ nhớ, kiểm tra:

- [ ] Đã quy định rõ `pageIndex` bắt đầu từ 0 hay 1.
- [ ] `pageSize > 0`, `pageIndex >= 0` và có giới hạn kích thước trang hợp lý cho ứng dụng.
- [ ] `offset` được tính bằng `long` và có xử lý tràn khi nhận trang quá lớn.
- [ ] `filter`, `distinct`, `sorted` được đặt trước `skip/limit` nếu phân trang trên **kết quả đã xử lý**.
- [ ] Có thứ tự xác định và tie-breaker nếu các khóa sắp xếp có thể bằng nhau.
- [ ] Tổng số bản ghi và tổng số trang phản ánh **tập dữ liệu sau lọc**, không phải kích thước trang.
- [ ] Trang cuối thiếu phần tử hoặc trang vượt cuối trả kết quả theo hợp đồng đã công bố.
- [ ] Nguồn có trạng thái ổn định trong lúc phân trang; biết có cần snapshot giữa nhiều yêu cầu không.
- [ ] Nếu dùng `subList`, đã xác định dùng view hay bản sao và hệ quả khi nguồn thay đổi.
- [ ] Không dựa vào `unordered` / `forEach` song song để bảo toàn vị trí trong trang.
- [ ] Đã cân nhắc chi phí của `skip` trang sâu, `sorted` và việc tính lại pipeline trên mỗi yêu cầu.
- [ ] Nếu dữ liệu gốc quá lớn, đã xem xét phân trang tại nguồn hoặc mô hình cursor.
- [ ] Nếu nguồn gắn với I/O, đã quản lý vòng đời tài nguyên đúng cách.
- [ ] Đã thử nguồn rỗng, một phần tử, đúng bội số `pageSize`, trang cuối không đầy, trang vượt cuối, tham số âm/0 và tràn số.

## 19. Tổng kết

Công thức phân trang theo vị trí đơn giản:

```java
long offset = Math.multiplyExact(pageIndex, (long) pageSize);

List<T> page = source.stream()
    .skip(offset)
    .limit(pageSize)
    .collect(Collectors.toList());
```

Đây là mẫu minh họa: trước khi chạy, phải xác thực chỉ số và kích thước trang; `source` và `T` cần được khai báo trong chương trình thực tế.

Các nguyên tắc quan trọng nhất:

- **Đúng nội dung:** xác lập thứ tự, lọc và sắp xếp **trước** khi cắt nếu đó là tập kết quả cần phân trang.
- **Đúng chỉ số:** thống nhất 0-based/1-based, dùng `long` để tính offset và phát hiện tràn.
- **Đúng metadata:** đếm trên tập sau lọc, tính tổng trang không tràn, không nhầm kích thước trang với tổng số bản ghi.
- **Đúng vòng đời dữ liệu:** nếu dữ liệu thay đổi giữa hai lần tải, offset có thể lặp hoặc bỏ sót bản ghi; cần snapshot hoặc cursor tùy yêu cầu.
- **Đúng lựa chọn công cụ:** với `ArrayList` đã ở RAM và chỉ cần một đoạn, `subList` kèm bản sao thường rõ nghĩa hơn; với pipeline xử lý, `skip`/`limit` thuận tiện nhưng không bảo đảm phân trang trang sâu nhanh trên mọi nguồn.
- **Đúng tài nguyên:** phân trang sau khi đã tải toàn bộ dữ liệu lớn vào RAM không thay thế được phân trang tại nguồn.

Hiểu rõ giới hạn của `skip` và `limit` giúp bạn thiết kế những pipeline Java Stream API có kết quả chính xác, dễ kiểm thử và phù hợp hiệu năng thực tế thay vì chỉ tạo ra một danh sách ngắn hơn.
