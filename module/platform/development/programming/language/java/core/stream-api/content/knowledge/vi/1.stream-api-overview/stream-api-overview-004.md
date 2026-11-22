# Viết pipeline đầu tiên với `filter`, `map` và `collect`

## 1. Mục tiêu bài học

**Java Stream API** cho phép xử lý dữ liệu theo lối **khai báo**: mô tả dữ liệu cần chọn, cách biến đổi và kết quả cần thu về. Thay vì tự quản lý vòng lặp, danh sách tạm và thao tác thêm phần tử, ta ghép các phép xử lý thành một **pipeline** (chuỗi xử lý).

Sau bài này, bạn có thể:

- Tạo một `Stream` từ `List` và viết pipeline đầu tiên theo cấu trúc **nguồn dữ liệu → `filter` → `map` → `collect`**.
- Phân biệt `filter` (giữ hoặc loại phần tử), `map` (biến đổi phần tử) và `collect` (tạo kết quả cuối).
- Giải thích vì sao `filter` và `map` chưa chạy ngay khi được khai báo, còn `collect` kích hoạt việc xử lý.
- Đọc kiểu dữ liệu, dự đoán kết quả và nhận ra các lỗi cơ bản khi viết pipeline.

Đây là điểm bắt đầu cho các kỹ thuật Stream API rộng hơn như `reduce`, `groupingBy`, collector tùy chỉnh hoặc xử lý song song. Bài này tập trung vào một pipeline tuần tự, dễ hiểu và kiểm chứng.

## 2. Bài toán: lấy tên các khóa học Java và viết hoa

Giả sử hệ thống có các khóa học:

```text
Java Core, Python Basics, Java Stream API, Kotlin, Java Spring
```

Ta muốn **chỉ giữ khóa học có tên bắt đầu bằng `Java`**, chuyển tên của chúng thành chữ in hoa và tạo một `List<String>` mới.

Nếu dùng vòng lặp, ta phải duyệt từng phần tử, kiểm tra điều kiện, biến đổi chuỗi rồi thêm vào danh sách kết quả. Với Stream API, ba ý đó xuất hiện trực tiếp trong pipeline:

```java
import java.util.Arrays;
import java.util.List;
import java.util.Locale;
import java.util.stream.Collectors;

public class StreamPipelineDauTien {
    public static void main(String[] args) {
        List<String> khoaHoc = Arrays.asList(
            "Java Core",
            "Python Basics",
            "Java Stream API",
            "Kotlin",
            "Java Spring"
        );

        List<String> tenKhoaJava = khoaHoc.stream()
            .filter(ten -> ten.startsWith("Java"))
            .map(ten -> ten.toUpperCase(Locale.ROOT))
            .collect(Collectors.toList());

        System.out.println(tenKhoaJava);
        System.out.println(khoaHoc);
    }
}
```

Kết quả:

```text
[JAVA CORE, JAVA STREAM API, JAVA SPRING]
[Java Core, Python Basics, Java Stream API, Kotlin, Java Spring]
```

Ví dụ dùng `Collectors.toList()`, có từ **Java 8**. Dòng thứ hai xác nhận danh sách nguồn `khoaHoc` vẫn giữ nguyên: pipeline trên tạo kết quả mới, không sửa các chuỗi trong danh sách ban đầu.

## 3. Đọc từng bước của pipeline

```text
List<String> khoaHoc
        │
        ▼
     stream()       tạo Stream<String> từ danh sách
        │
        ▼
  filter(điều kiện) giữ tên bắt đầu bằng "Java"
        │
        ▼
    map(biến đổi)   đổi từng tên còn lại thành chữ in hoa
        │
        ▼
 collect(toList())  thu các phần tử thành List<String>
```

| Thành phần | Vai trò | Đầu vào → đầu ra trong ví dụ |
| --- | --- | --- |
| `khoaHoc.stream()` | Mở luồng xử lý từ danh sách | `List<String>` → `Stream<String>` |
| `.filter(ten -> ten.startsWith("Java"))` | Chỉ giữ phần tử thỏa điều kiện | `Stream<String>` → `Stream<String>` |
| `.map(ten -> ten.toUpperCase(Locale.ROOT))` | Biến đổi mỗi phần tử còn lại | `Stream<String>` → `Stream<String>` |
| `.collect(Collectors.toList())` | Kích hoạt pipeline và thu kết quả | `Stream<String>` → `List<String>` |

### 3.1. `filter`: chọn phần tử

`filter` nhận một **`Predicate<T>`**, tức hàm kiểm tra một phần tử kiểu `T` và trả về `boolean`:

```java
.filter(ten -> ten.startsWith("Java"))
```

- `true`: phần tử được đưa tiếp sang bước sau.
- `false`: phần tử bị loại khỏi pipeline, nên sẽ không được `map` xử lý.

Ở ví dụ trên, `"Python Basics"` và `"Kotlin"` không qua được bộ lọc. Điều kiện `startsWith("Java")` **phân biệt chữ hoa và chữ thường**: tên bắt đầu bằng `"java"` sẽ không được giữ lại.

### 3.2. `map`: biến đổi phần tử

`map` nhận một **`Function<T, R>`**, tức hàm biến một phần tử kiểu `T` thành một giá trị kiểu `R`:

```java
.map(ten -> ten.toUpperCase(Locale.ROOT))
```

Ở đây `T` và `R` đều là `String`, nhưng `map` **có thể đổi kiểu dữ liệu**. Chẳng hạn, sau khi chọn tên khóa học Java, ta lấy độ dài của từng tên:

```java
List<Integer> doDaiTen = khoaHoc.stream()
    .filter(ten -> ten.startsWith("Java"))
    .map(String::length)
    .collect(Collectors.toList());

System.out.println(doDaiTen); // [9, 15, 11]
```

Lúc này `map(String::length)` biến `Stream<String>` thành `Stream<Integer>`. Cú pháp `String::length` là **method reference**, cách viết gọn tương đương `ten -> ten.length()` trong trường hợp này.

### 3.3. `collect`: thu kết quả

`collect` là một **terminal operation** (phép toán kết thúc). Nó tiêu thụ stream để tạo kết quả theo chiến lược của một `Collector`:

```java
.collect(Collectors.toList())
```

`Collectors.toList()` thu các phần tử thành danh sách, giữ thứ tự gặp phần tử đối với nguồn có thứ tự như `List` ở pipeline tuần tự này. Có thể thu theo cách khác tùy nhu cầu:

```java
// Thu các tên thành một chuỗi, ngăn cách bởi dấu phẩy.
String chuoiTen = khoaHoc.stream()
    .filter(ten -> ten.startsWith("Java"))
    .collect(Collectors.joining(", "));

// Kết quả: "Java Core, Java Stream API, Java Spring"
```

Một chi tiết hữu ích về phiên bản Java: từ **Java 16**, có thể viết `stream.toList()` thay cho `collect(Collectors.toList())` khi chỉ cần thu về danh sách. Tuy nhiên, `Stream.toList()` trả về danh sách **không cho phép sửa đổi**, còn `Collectors.toList()` **không cam kết** kiểu cụ thể hoặc khả năng sửa đổi của danh sách trả về. Nếu thực sự cần một `ArrayList` có thể sửa, hãy dùng `collect(Collectors.toCollection(ArrayList::new))`.

## 4. Pipeline chạy khi nào? Hiểu tính lazy

`filter` và `map` là **intermediate operations** (phép toán trung gian): việc gọi chúng chỉ xây dựng các bước xử lý. Chúng **chưa duyệt dữ liệu ngay**. Khi có terminal operation như `collect`, pipeline mới được thực thi.

Quan sát đoạn mã sau (dùng lại danh sách `khoaHoc` ở ví dụ đầu):

```java
import java.util.stream.Stream;

Stream<String> pipeline = khoaHoc.stream()
    .filter(ten -> {
        System.out.println("filter: " + ten);
        return ten.startsWith("Java");
    })
    .map(ten -> {
        System.out.println("map: " + ten);
        return ten.toUpperCase(Locale.ROOT);
    });

System.out.println("Pipeline đã được khai báo");

List<String> ketQua = pipeline.collect(Collectors.toList());
System.out.println(ketQua);
```

Đầu tiên chỉ in `Pipeline đã được khai báo`. Sau đó, lời gọi `collect` mới làm xuất hiện các dòng `filter:` và `map:`. Trong pipeline tuần tự đơn giản này, Java thường xử lý **từng phần tử đi qua các bước**: nếu `filter` loại một tên, `map` không được gọi cho tên đó. Đây không phải hai vòng lặp tách biệt bắt buộc quét toàn bộ danh sách.

Các lệnh `println` chỉ phục vụ việc quan sát. Khi viết mã thực tế, nên dùng `filter`/`map` như những hàm không có tác dụng phụ, tránh sửa dữ liệu bên ngoài hoặc dựa vào thứ tự log để quyết định logic chương trình.

**Lưu ý:** Mỗi `Stream` chỉ được tiêu thụ một lần. Sau khi đã gọi `pipeline.collect(...)`, không tiếp tục dùng chính `pipeline` cho một phép kết thúc khác; muốn xử lý lại, hãy tạo stream mới từ nguồn bằng `khoaHoc.stream()`.

## 5. Thứ tự các bước ảnh hưởng kết quả

Với dữ liệu đã sạch, `filter` trước `map` giúp bỏ qua việc biến đổi những phần tử chắc chắn bị loại. Nhưng nếu điều kiện lọc phụ thuộc vào **giá trị đã chuẩn hóa**, cần `map` trước `filter`.

Ví dụ dữ liệu nhập từ biểu mẫu có khoảng trắng dư và cách viết hoa không thống nhất:

```java
List<String> tenNhap = Arrays.asList(
    "  Java Core  ", "java Stream API", " Python ", "   "
);

List<String> tenJava = tenNhap.stream()
    .map(String::trim)
    .filter(ten -> !ten.isEmpty())
    .filter(ten -> ten.toLowerCase(Locale.ROOT).startsWith("java"))
    .map(ten -> ten.toUpperCase(Locale.ROOT))
    .collect(Collectors.toList());

System.out.println(tenJava);
// [JAVA CORE, JAVA STREAM API]
```

Ở đây, `trim` phải chạy trước bước kiểm tra tên bắt đầu bằng `java`; nếu lọc ngay trên chuỗi gốc, `"  Java Core  "` sẽ bị bỏ sót. Việc `filter` và `map` xuất hiện nhiều lần trong cùng một pipeline là hoàn toàn bình thường.

Khi dữ liệu có thể chứa `null`, cần xử lý trước khi gọi `startsWith`, `trim` hoặc `toUpperCase`, chẳng hạn dùng `.filter(java.util.Objects::nonNull)` trước các bước đó. Nếu không, pipeline có thể phát sinh `NullPointerException` khi được thực thi.

## 6. Ví dụ nghiệp vụ: lọc giá sản phẩm và tính giá sau giảm

Ta có danh sách giá tính bằng đồng và muốn lấy các sản phẩm **có giá từ 100.000 đồng trở lên**, giảm **10%** rồi thu thành danh sách mới:

```java
List<Integer> giaGoc = Arrays.asList(90_000, 150_000, 300_000, 60_000);

List<Integer> giaSauGiam = giaGoc.stream()
    .filter(gia -> gia >= 100_000)
    .map(gia -> gia - gia / 10)
    .collect(Collectors.toList());

System.out.println(giaSauGiam); // [135000, 270000]
System.out.println(giaGoc);      // [90000, 150000, 300000, 60000]
```

Đọc theo yêu cầu nghiệp vụ:

1. `stream()` lấy từng giá từ danh sách nguồn.
2. `filter` giữ `150_000` và `300_000`, loại hai giá thấp hơn ngưỡng.
3. `map` trừ đi 10% của từng giá được giữ lại.
4. `collect` thu hai giá mới thành `List<Integer>`.

Ví dụ dùng phép chia số nguyên để dễ học; bài toán tiền tệ thực tế cần quy tắc làm tròn rõ ràng, kiểu dữ liệu phù hợp (thường là `BigDecimal`) và kiểm tra tràn số khi tính toán.

## 7. Những lỗi thường gặp

| Tình huống | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Gọi `stream().filter(...).map(...)` nhưng không thấy kết quả | Chưa có phép toán kết thúc; các bước trung gian là lazy | Thêm `collect`, `count` hoặc terminal operation phù hợp |
| Dùng `map(ten -> ten.startsWith("Java"))` để lọc | `map` biến tên thành `Boolean`, không loại phần tử | Dùng `filter(ten -> ten.startsWith("Java"))` |
| Dùng `forEach` rồi cố gán kết quả vào `List` | `forEach` trả về `void`, chủ yếu để thực hiện hành động với từng phần tử | Dùng `collect(Collectors.toList())` để thu danh sách |
| Cố gọi `collect` hai lần trên cùng một `Stream` | Stream đã bị tiêu thụ | Tạo stream mới từ nguồn |
| Điều kiện `startsWith("Java")` bỏ sót `"java Core"` | So sánh phân biệt hoa/thường | Chuẩn hóa hoặc dùng phép so sánh phù hợp |
| Gọi phương thức chuỗi trên phần tử `null` | Truy cập vào đối tượng không tồn tại | Lọc `null` trước khi xử lý |
| Cố sửa danh sách do `Stream.toList()` trả về | Danh sách này không cho phép sửa đổi | Chọn collector tạo danh sách có thể sửa nếu thật sự cần |

Stream API giúp diễn đạt ý định xử lý rõ ràng, nhưng **không mặc nhiên nhanh hơn vòng lặp**. Với dữ liệu nhỏ hoặc logic đơn giản, ưu tiên khả năng đọc và bảo trì; chưa cần dùng `parallelStream()` cho pipeline đầu tiên.

## 8. Tự thực hành

Cho danh sách:

```java
List<String> ngonNgu = Arrays.asList(
    "Java", "JavaScript", "Python", "Go", "Kotlin", "Python"
);
```

Hãy viết pipeline dùng `filter`, `map` và `collect` để **giữ các tên có ít nhất 5 ký tự**, **chuyển sang chữ thường** và **thu thành `List<String>`**. Trước khi chạy, thử dự đoán kết quả. Các giá trị trùng nhau có còn không?

<details>
<summary>Gợi ý lời giải</summary>

```java
List<String> ketQua = ngonNgu.stream()
    .filter(ten -> ten.length() >= 5)
    .map(ten -> ten.toLowerCase(Locale.ROOT))
    .collect(Collectors.toList());

System.out.println(ketQua); // [javascript, python, kotlin, python]
```

Các phần tử `"Java"`, `"Go"` không đủ 5 ký tự nên bị loại. `filter`, `map`, `collect(toList())` **không tự xóa phần tử trùng**: hai lần xuất hiện của `"Python"` đều được giữ trong danh sách kết quả.

</details>

## 9. Ghi nhớ

Một pipeline Stream API đầu tiên có dạng:

```java
List<R> ketQua = nguon.stream()
    .filter(phanTu -> dieuKien)
    .map(phanTu -> giaTriMoi)
    .collect(Collectors.toList());
```

Trong đó, `filter` trả lời **giữ phần tử nào**, `map` trả lời **biến thành giá trị gì**, còn `collect` trả lời **lấy kết quả dưới dạng nào**. `filter` và `map` chỉ mô tả xử lý; `collect` kích hoạt việc chạy pipeline. Khi đã hiểu ba bước này, bạn có nền tảng để tiếp tục học `reduce`, `Collectors.groupingBy` và các pipeline phức tạp hơn.
