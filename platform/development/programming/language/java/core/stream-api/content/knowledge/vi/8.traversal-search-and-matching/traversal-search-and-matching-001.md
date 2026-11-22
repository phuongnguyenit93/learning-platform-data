# Đếm phần tử bằng `count` và nhận biết tối ưu hóa bỏ qua duyệt

## 1. Mục tiêu bài học

Trong **Java Stream API**, các pipeline thường kết hợp nguồn dữ liệu với những phép toán trung gian lazy như `filter`, `map`, `distinct`, `flatMap` và một phép toán kết thúc (terminal operation). Khi chỉ cần biết **có bao nhiêu phần tử trong kết quả**, ta dùng `count()` thay vì tạo một danh sách trung gian rồi gọi `size()`.

Điểm dễ nhầm là: **`count()` trả về số phần tử của kết quả pipeline, nhưng không cam kết duyệt qua từng phần tử**. Khi đã biết chính xác số lượng phần tử và các bước trung gian không làm thay đổi số lượng ấy, triển khai Stream có thể tính ngay kết quả. Vì thế, đặt log hoặc thao tác cập nhật bên trong `peek` hay `map` rồi gọi `count()` không bảo đảm log hoặc thao tác đó sẽ chạy.

Sau bài này, bạn có thể:

- Dùng `count()` với `Stream<T>` và các primitive stream như `IntStream`.
- Giải thích vì sao `count()` trả về `long`, hoạt động như terminal operation và có thể không duyệt dữ liệu.
- Nhận diện nguồn có kích thước xác định (chẳng hạn `List`) và các bước giữ nguyên hoặc có thể thay đổi số phần tử.
- Phân tích hiện tượng `peek`/`map` không được gọi trong một pipeline kết thúc bằng `count()`.
- Viết phép đếm có điều kiện, đếm phần tử duy nhất, xử lý stream có thể vô hạn và lựa chọn phép toán phù hợp cho bài toán.

Bài thuộc chương **Duyệt, tìm kiếm và đối sánh** của module **`JAVA_STREAM_API`**. Những kiến thức về lazy evaluation, đặc tính nguồn và giới hạn tối ưu hóa này cũng cần thiết khi học collector tùy chỉnh, `Spliterator`, xử lý song song hay Stream Gatherers.

## 2. `count()`: cú pháp, kiểu trả về và ý nghĩa

Chữ ký của phương thức trên `Stream<T>`:

```java
long count();
```

`count()` là **terminal operation**: khi gọi, pipeline được yêu cầu tạo ra kết quả cuối là một số `long`. Con số đó biểu thị **số phần tử trong stream tại điểm gọi `count()`**, tức sau mọi phép toán trung gian đứng trước nó.

Ví dụ đầy đủ, dùng được từ Java 8:

```java
import java.util.Arrays;
import java.util.List;

public class DemKhoaHoc {
    public static void main(String[] args) {
        List<String> khoaHoc = Arrays.asList(
            "Java Core",
            "Python",
            "Java Stream API",
            "Kotlin",
            "Java Spring"
        );

        long tongSo = khoaHoc.stream().count();

        long soKhoaJava = khoaHoc.stream()
            .filter(ten -> ten.startsWith("Java"))
            .count();

        System.out.println("Tổng: " + tongSo);
        System.out.println("Khóa Java: " + soKhoaJava);
    }
}
```

Kết quả:

```text
Tổng: 5
Khóa Java: 3
```

Ở pipeline thứ hai, `filter` loại "Python" và "Kotlin", nên `count()` nhận số lượng các phần tử vượt qua điều kiện. Kết quả `3` **không phải số lần phương thức `filter` được gọi**.

Một số biểu thức khác:

| Biểu thức | Kết quả | Ý nghĩa |
| --- | ---: | --- |
| `Stream.empty().count()` | `0L` | Stream rỗng. |
| `Stream.of("A", "B", "C").count()` | `3L` | Ba phần tử. |
| `Stream.of("A", "A", "B").distinct().count()` | `2L` | Hai giá trị phân biệt. |
| `Stream.of(3, 6, 9).filter(n -> n > 5).count()` | `2L` | Hai phần tử thỏa điều kiện. |
| `java.util.stream.IntStream.range(0, 100).count()` | `100L` | Một trăm số, từ 0 đến 99. |

**Vì sao kiểu `long`?** API dùng `long` để biểu diễn số lượng có thể lớn hơn giới hạn kiểu `int`. Nếu khai báo `int n = stream.count();` thì trình biên dịch báo lỗi không thể chuyển từ `long` sang `int` một cách tự động.

```java
long hopLe = Stream.of(1, 2, 3).count();

// KHÔNG BIÊN DỊCH: possible lossy conversion from long to int.
// int saiKieu = Stream.of(1, 2, 3).count();
```

Một stream chỉ được **tiêu thụ một lần**. Sau khi gọi `count()`, không tái sử dụng chính đối tượng stream đó cho `collect()`, `findFirst()` hay `count()` lần nữa; muốn tính thêm, hãy tạo stream mới từ nguồn.

## 3. Terminal operation có nhất thiết duyệt phần tử không?

Từ "terminal" có nghĩa là **yêu cầu kết quả cuối và kết thúc việc sử dụng stream**, không có nghĩa là **bắt buộc gọi mọi bước trung gian trên từng phần tử**.

### 3.1. Ví dụ `peek` không in gì nhưng `count()` vẫn đúng

Xét chương trình:

```java
import java.util.Arrays;
import java.util.List;

public class DemKhongDuyet {
    public static void main(String[] args) {
        List<String> ten = Arrays.asList("An", "Binh", "Chi");

        long soLuong = ten.stream()
            .peek(s -> System.out.println("Đã gặp: " + s))
            .count();

        System.out.println("Số lượng: " + soLuong);
    }
}
```

Trên nhiều triển khai JDK hiện đại (đặc biệt từ Java 9), kết quả có thể chỉ là:

```text
Số lượng: 3
```

Không có dòng `Đã gặp: ...` nào. **Đây là hành vi được phép**, không phải lỗi của `peek` hay `count()`.

Lý do: nguồn `List` có số phần tử xác định; `peek` không thêm hay loại phần tử; do vậy `count()` có thể lấy chính xác kết quả `3` mà không cần yêu cầu nguồn cung cấp từng phần tử. Khi không duyệt, hành động trong `peek` cũng không được thực hiện.

> Chú ý phiên bản và triển khai: tài liệu API mô tả rõ khả năng tối ưu này; không được viết chương trình phụ thuộc vào việc `peek` chắc chắn chạy hay chắc chắn bị bỏ qua. Java 8 và các phiên bản/triển khai khác có thể biểu hiện khác nhau.

### 3.2. `map` cũng có thể bị bỏ qua

`map` thay đổi **giá trị** nhưng thường không đổi **số lượng** phần tử:

```java
List<String> ten = Arrays.asList("An", "Binh", "Chi");

long soLuong = ten.stream()
    .map(s -> s.toUpperCase(java.util.Locale.ROOT))
    .count();

System.out.println(soLuong); // 3
```

Để tính số lượng, `count()` không cần biết các tên viết hoa ra sao. Nếu triển khai có đủ thông tin về kích thước, nó có thể bỏ qua việc gọi hàm `map` hoàn toàn.

Điều này đặc biệt quan trọng nếu lambda có **tác dụng phụ**:

```java
// Cách viết không đáng tin cậy:
long soLuong = ten.stream()
    .map(s -> {
        ghiLogHoacCapNhatHeThong(s);
        return s.toUpperCase(java.util.Locale.ROOT);
    })
    .count();
```

`ghiLogHoacCapNhatHeThong(s)` **không được bảo đảm sẽ chạy**, dù `count()` trả đúng `3`. Đoạn trên minh họa một cách thiết kế cần tránh; phương thức `ghiLogHoacCapNhatHeThong` là tên giả định.

**Quy tắc:** Hàm xử lý trong `map`, `filter`, `peek` nên không gây tác dụng phụ và không phụ thuộc vào việc được gọi bao nhiêu lần. Nếu mục tiêu là thực hiện một hành động cho từng phần tử, hãy dùng terminal operation phù hợp như `forEach`; còn nếu mục tiêu là đếm, hãy dùng `count` và chỉ dựa vào kết quả đếm.

## 4. Tại sao triển khai có thể biết số lượng trước khi duyệt?

### 4.1. Nguồn có kích thước chính xác

Nhiều nguồn dữ liệu biết sẵn số phần tử. Trong Stream API, thông tin này thường liên quan đến đặc tính **`Spliterator.SIZED`** của nguồn.

Ví dụ:

```java
List<String> ten = Arrays.asList("An", "Binh", "Chi");

long dem = ten.stream().count(); // 3
int kichThuoc = ten.size();      // 3
```

Với nguồn là một danh sách ổn định, việc lấy số lượng trực tiếp từ nguồn có thể tránh lặp qua tất cả phần tử.

Các nguồn phổ biến:

| Nguồn | Thông tin kích thước | Hệ quả đối với `count()` |
| --- | --- | --- |
| `Arrays.asList(...).stream()` | Thường xác định chính xác | Có thể tính trực tiếp nếu pipeline không phá thông tin số lượng. |
| `Stream.of(a, b, c)` | Xác định chính xác | Thường có thể tối ưu hóa đếm. |
| `IntStream.range(0, 1000)` | Có số phần tử xác định | Có thể tính số lượng mà không duyệt hết các số. |
| `Stream.iterate(seed, next)` | Không khai báo số phần tử hữu hạn | Thường không thể tự suy ra điểm kết thúc. |
| `Stream.generate(supplier)` | Có thể sinh vô hạn; không có kích thước xác định | Không thể tự xác định tổng số phần tử. |

Đặc tính `SIZED` cho biết nguồn có thể cung cấp số lượng phần tử còn lại một cách chính xác ở thời điểm phù hợp. Nó không đồng nghĩa **mọi pipeline xuất phát từ nguồn đó** đều biết chính xác kích thước sau các phép biến đổi.

### 4.2. Phép toán có giữ nguyên số phần tử không?

Hãy xét các phép toán trung gian trong pipeline:

| Phép toán | Tác động đến số lượng | Khả năng đếm mà không duyệt |
| --- | --- | --- |
| `map` | Mỗi đầu vào tạo một đầu ra | Có thể giữ thông tin kích thước. |
| `peek` | Không chủ ý thêm/bớt phần tử | Có thể giữ thông tin kích thước. |
| `sorted` | Sắp xếp, không thêm/bớt | Có thể vẫn tính số lượng trực tiếp mà không cần sắp xếp. |
| `unordered` | Bỏ yêu cầu về thứ tự, không đổi số lượng | Có thể giữ thông tin kích thước. |
| `filter` | Có thể loại một số phần tử | Thường phải đánh giá điều kiện để biết số lượng. |
| `distinct` | Có thể loại phần tử trùng | Thường phải xác định giá trị trùng. |
| `flatMap` | Mỗi phần tử có thể tạo 0, 1 hoặc nhiều phần tử | Thường phải xét các stream con. |
| `mapMulti` (Java 16+) | Có thể tạo 0, 1 hoặc nhiều phần tử | Thường phải duyệt để biết số lượng. |
| `takeWhile` / `dropWhile` (Java 9+) | Có thể bỏ phần tử tùy điều kiện | Thường phải kiểm tra điều kiện. |
| `limit(n)` / `skip(n)` | Giới hạn/bỏ số phần tử theo vị trí | Với nguồn có kích thước xác định, số lượng sau các bước này **có thể** được tính bằng phép toán số học. |

Ví dụ:

```java
List<String> ten = Arrays.asList("An", "Binh", "Chi", "Dung");

long a = ten.stream()
    .map(String::length)
    .count();                          // 4

long b = ten.stream()
    .filter(s -> s.length() >= 4)
    .count();                          // 2

long c = ten.stream()
    .skip(1)
    .limit(2)
    .count();                          // 2
```

- Với `a`, `map` thay giá trị nhưng số phần tử chắc chắn vẫn là 4.
- Với `b`, cần xác định những tên nào vượt qua bộ lọc; trong ví dụ là `Binh` và `Dung`.
- Với `c`, nguồn có bốn phần tử; bỏ một rồi lấy nhiều nhất hai phần tử nên đếm được 2.

Đây là **khả năng tối ưu**, không phải một lời hứa rằng mọi phiên bản JDK hoặc mọi kiểu pipeline sẽ áp dụng chính xác cùng một chiến lược. Tối ưu được phép thay đổi những bước trung gian thực tế được đánh giá, nhưng kết quả `count()` phải đúng theo ngữ nghĩa stream.

### 4.3. `SIZED` và `SUBSIZED` không giống nhau

Đặc tính `Spliterator.SIZED` nói về **kích thước chính xác của phần còn lại** mà spliterator đại diện. `Spliterator.SUBSIZED` bổ sung rằng các spliterator con thu được khi tách cũng có đặc tính `SIZED` và `SUBSIZED`.

Hai đặc tính này hữu ích cho tối ưu hóa, nhất là khi xử lý song song, nhưng **không tự động bảo đảm** mọi bước trung gian đều được bỏ qua. Chẳng hạn, `filter` có thể khiến số lượng kết quả không còn suy ra trực tiếp từ kích thước nguồn.

Khi tự triển khai `Spliterator` ở các bài học nâng cao, chỉ khai báo `SIZED` nếu thực sự đáp ứng hợp đồng chính xác về số phần tử còn lại. Khai báo sai có thể dẫn đến hành vi sai hoặc khó chẩn đoán.

## 5. Đếm sau `filter`, `distinct` và `flatMap`

### 5.1. Đếm theo điều kiện

Nếu yêu cầu là **"Có bao nhiêu khóa học Java?"**, nên đặt điều kiện trong `filter`:

```java
List<String> khoaHoc = Arrays.asList(
    "Java Core", "Python", "Java Stream API", "Java Spring"
);

long soKhoaJava = khoaHoc.stream()
    .filter(ten -> ten.startsWith("Java"))
    .count();

System.out.println(soKhoaJava); // 3
```

Nguồn có bốn phần tử nhưng không thể chỉ dùng số 4 để suy ra có bao nhiêu tên bắt đầu bằng "Java". `count()` cần quan tâm đến kết quả của bộ lọc.

**Không nhầm `filter` với `map`**:

```java
long saiYeuCau = khoaHoc.stream()
    .map(ten -> ten.startsWith("Java"))
    .count();

System.out.println(saiYeuCau); // 4, không phải 3
```

Ở đây `map` biến mỗi chuỗi thành `Boolean` (cả `true` lẫn `false` đều là một phần tử), vì vậy số lượng vẫn là bốn.

### 5.2. Đếm các giá trị duy nhất

`distinct` loại những giá trị trùng nhau theo `equals`:

```java
List<String> ngonNgu = Arrays.asList(
    "Java", "Kotlin", "Java", "Go", "Kotlin"
);

long soNgonNgu = ngonNgu.stream()
    .distinct()
    .count();

System.out.println(soNgonNgu); // 3
```

Nếu cần phân biệt không phụ thuộc chữ hoa/chữ thường, phải chuẩn hóa trước:

```java
import java.util.Locale;

List<String> ten = Arrays.asList("Java", "JAVA", "Go", "go");

long soTenKhacNhau = ten.stream()
    .map(s -> s.toLowerCase(Locale.ROOT))
    .distinct()
    .count();

System.out.println(soTenKhacNhau); // 2
```

Số lượng sau `distinct` phụ thuộc vào các giá trị cụ thể; nguồn biết kích thước chưa đủ để suy ra có bao nhiêu giá trị duy nhất.

### 5.3. Đếm phần tử sau khi làm phẳng

`flatMap` có thể biến một phần tử thành nhiều phần tử:

```java
List<List<String>> nhom = Arrays.asList(
    Arrays.asList("A", "B"),
    Arrays.asList("C"),
    Arrays.<String>asList()
);

long soNhom = nhom.stream().count(); // 3

long soPhanTu = nhom.stream()
    .flatMap(List::stream)
    .count();                       // 3
```

Trong ví dụ này hai kết quả đều là 3 **chỉ là trùng hợp**. Một luồng có ba danh sách con không có nghĩa là luồng sau khi làm phẳng luôn có ba phần tử.

## 6. `peek` phù hợp để quan sát, không phù hợp để thực hiện nghiệp vụ

Mặc dù `peek` thường được dùng để quan sát dữ liệu giữa các bước, nó **không phải cơ chế bảo đảm chạy tác vụ**. Đặc biệt, `count()` có thể không cần đánh giá `peek` nếu số lượng đã biết.

Ví dụ minh họa:

```java
List<String> ten = Arrays.asList("An", "Binh", "Chi", "Dung");

long tong = ten.stream()
    .peek(s -> System.out.println("Đang xét " + s))
    .count();

System.out.println("Tổng = " + tong);
```

Một JDK có thể in chỉ `Tổng = 4`, trong khi JDK khác có thể in thêm các dòng quan sát. Chương trình đúng chỉ dựa vào `tong == 4`.

Khi thêm `filter`:

```java
long hopLe = ten.stream()
    .filter(s -> s.length() >= 4)
    .peek(s -> System.out.println("Hợp lệ: " + s))
    .count();

System.out.println("Số tên hợp lệ = " + hopLe); // 2
```

Trong pipeline thông thường, vì số lượng sau `filter` không biết sẵn nên quá trình phải kiểm tra các phần tử và log `peek` có thể xuất hiện. Tuy nhiên, **không dùng số dòng log để xác minh số lần xử lý** và không dựa vào tác dụng phụ này làm kết quả nghiệp vụ.

Nếu yêu cầu thực sự là **"Ghi nhận mỗi tên hợp lệ"**, hãy biểu diễn hành động thành terminal operation rõ ràng:

```java
ten.stream()
    .filter(s -> s.length() >= 4)
    .forEach(s -> System.out.println("Hợp lệ: " + s));
```

Nếu vừa cần **đếm** vừa cần **thực hiện hành động**, hãy xác định mục tiêu và thiết kế tường minh: chẳng hạn thu các phần tử hợp lệ thành danh sách nếu dữ liệu đủ nhỏ, dùng `size()` của danh sách đó và xử lý danh sách theo yêu cầu. Với dữ liệu lớn, cân nhắc luồng xử lý chuyên dụng; không dựa vào tác dụng phụ bên trong pipeline chỉ để buộc `count()` duyệt.

Cũng không nên chèn các hàm giả tạo làm thay đổi số lượng để "ép" `peek` chạy. Điều đó làm sai ý nghĩa pipeline và có thể làm giảm hiệu năng.

## 7. Đếm stream vô hạn: phải có điểm dừng phù hợp

`count()` không tự dừng một nguồn có thể sinh vô hạn. Với những dãy như `Stream.iterate` hoặc `Stream.generate`, cần hạn chế số phần tử hoặc có điều kiện kết thúc trước khi muốn lấy kết quả đếm.

### 7.1. Đếm 10 số đầu tiên

```java
import java.util.stream.Stream;

long soLuong = Stream.iterate(0, n -> n + 1)
    .limit(10)
    .count();

System.out.println(soLuong); // 10
```

`limit(10)` bảo đảm pipeline chỉ yêu cầu tối đa mười phần tử. Việc `count()` có duyệt và gọi từng bước trung gian hay không còn tùy nguồn và triển khai; đây là cách biểu diễn yêu cầu hữu hạn.

### 7.2. Lọc trước khi giới hạn

```java
long soSoChan = Stream.iterate(1, n -> n + 1)
    .filter(n -> n % 2 == 0)
    .limit(5)
    .count();

System.out.println(soSoChan); // 5
```

Pipeline phải tìm đủ năm số chẵn, tương ứng 2, 4, 6, 8, 10. Nếu đổi thứ tự:

```java
long soChanTrongNamSoDau = Stream.iterate(1, n -> n + 1)
    .limit(5)
    .filter(n -> n % 2 == 0)
    .count();

System.out.println(soChanTrongNamSoDau); // 2
```

Khác biệt là **đếm năm số chẵn đầu tiên** so với **đếm số chẵn trong năm số đầu tiên**.

### 7.3. Những pipeline không được chạy thử

Các ví dụ sau có thể không bao giờ hoàn thành:

```java
// KHÔNG CHẠY: không giới hạn nguồn vô hạn.
// Stream.iterate(0, n -> n + 1).count();

// KHÔNG CHẠY: filter không bao giờ cho phần tử nào đi qua,
// nên limit(1) không nhận đủ phần tử.
// Stream.iterate(0, n -> n + 1)
//     .filter(n -> false)
//     .limit(1)
//     .count();
```

Với Java 9+, có thể dùng `takeWhile` trên dãy có thứ tự hoặc dạng `Stream.iterate(seed, hasNext, next)` để tạo điểm dừng dựa trên trạng thái:

```java
long dem = Stream.iterate(0, n -> n < 100, n -> n + 1)
    .count(); // 100 — Java 9+
```

Chỉ viết `filter(n -> n < 100)` **không thay thế** điều kiện dừng: bộ lọc loại phần tử nhưng có thể tiếp tục yêu cầu nguồn sinh giá trị mãi mãi.

## 8. Chọn `count()`, `size()`, `anyMatch()` hay `Collectors.counting()`

Nhu cầu khác nhau có những API phù hợp khác nhau:

| Nhu cầu | API nên cân nhắc | Ví dụ |
| --- | --- | --- |
| Đếm toàn bộ phần tử của `Collection` đã có | `collection.size()` | `ten.size()` |
| Đếm phần tử sau các bước xử lý Stream | `stream.count()` | `stream.filter(...).count()` |
| Chỉ cần biết có ít nhất một phần tử thỏa điều kiện | `anyMatch(predicate)` | `stream.anyMatch(s -> s.isEmpty())` |
| Kiểm tra có không phần tử nào thỏa điều kiện | `noneMatch(predicate)` | `stream.noneMatch(String::isEmpty)` |
| Đếm theo từng nhóm | `Collectors.groupingBy(..., counting())` | `Map<K, Long>` |
| Cần kết quả và danh sách các phần tử hợp lệ | `collect(toList())` rồi `size()` | Chỉ phù hợp khi cần thực sự lưu danh sách |

### 8.1. Vì sao không luôn dùng `count() > 0`?

`count()` cho biết số lượng chính xác; `anyMatch()` là **short-circuiting terminal operation** và có thể dừng ngay khi tìm được phần tử thỏa điều kiện.

```java
List<String> ten = Arrays.asList("An", "Binh", "Chi", "Dung");

boolean coTenDai = ten.stream()
    .anyMatch(s -> s.length() >= 4);

System.out.println(coTenDai); // true
```

Nếu chỉ cần câu trả lời **có/không**, `anyMatch` thể hiện ý định rõ hơn và có thể tránh duyệt toàn bộ nguồn. Ngược lại, nếu báo cáo cần "có **bao nhiêu** tên dài", dùng `filter(...).count()`.

### 8.2. `count()` và `Collectors.counting()`

`count()` trả về tổng số phần tử của cả pipeline:

```java
long tong = ten.stream().count();
```

`Collectors.counting()` thường có ích **bên trong collector khác**, chẳng hạn đếm số khóa học theo nhóm:

```java
import java.util.Arrays;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

List<String> khoaHoc = Arrays.asList(
    "Java Core", "Java Stream", "Go", "Python", "Java Spring"
);

Map<Boolean, Long> theoNhom = khoaHoc.stream()
    .collect(Collectors.groupingBy(
        s -> s.startsWith("Java"),
        Collectors.counting()
    ));

System.out.println(theoNhom.get(true));  // 3
System.out.println(theoNhom.get(false)); // 2
```

Ở đây `groupingBy` phân phần tử thành hai nhóm và `counting()` đếm số phần tử **trong từng nhóm**. Nếu không cần phân nhóm, `count()` thường đơn giản và rõ ràng hơn.

### 8.3. `count()` khác số lần hành động được gọi

`count()` mô tả **số phần tử cuối cùng**, không mô tả số lần `map`, `peek`, comparator của `sorted` hoặc một callback bất kỳ được thực thi. Số lần gọi và thứ tự gọi các hàm hành vi là chi tiết triển khai, còn một số phép toán có thể short-circuit hoặc được bỏ qua khi không ảnh hưởng đến kết quả.

Điều này cũng quan trọng khi chuyển sang xử lý song song: dù kết quả đếm giống nhau, không được suy luận về thứ tự chạy hoặc số lần gọi của các thao tác có tác dụng phụ dựa trên kết quả `count()`.

## 9. Cách kiểm chứng và chẩn đoán tối ưu hóa

Khi thấy `peek` không in gì, trước tiên kiểm tra:

1. **Nguồn có biết số phần tử không?** Ví dụ `List`, mảng, `Stream.of`, `IntStream.range` thường có thông tin kích thước.
2. **Những bước nào có thể thay đổi số lượng?** `map` và `peek` giữ nguyên số lượng; `filter`, `distinct`, `flatMap` thường khiến kết quả phụ thuộc dữ liệu.
3. **Terminal operation có thật sự cần giá trị từng phần tử không?** `count()` có thể không cần; `collect(toList())` thường phải tạo giá trị đầu ra.
4. **Có dựa vào tác dụng phụ không?** Nếu có, hãy thiết kế lại để hành động nghiệp vụ được biểu diễn tường minh.
5. **Có nguồn vô hạn hoặc phép toán chặn trước `limit` không?** Kiểm tra khả năng pipeline không bao giờ hoàn thành.

### Minh họa tương phản

```java
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;

public class KiemTraCount {
    public static void main(String[] args) {
        List<String> ten = Arrays.asList("A", "BB", "CCC");

        long dem = ten.stream()
            .map(String::toLowerCase)
            .peek(s -> System.out.println("peek: " + s))
            .count();

        List<String> danhSach = ten.stream()
            .map(String::toLowerCase)
            .collect(Collectors.toList());

        System.out.println("Đếm: " + dem);
        System.out.println("Danh sách: " + danhSach);
    }
}
```

Kết quả logic cần kiểm tra là:

```text
Đếm: 3
Danh sách: [a, bb, ccc]
```

Các dòng `peek: ...` có thể có hoặc không tùy triển khai và cách tối ưu. Chúng **không phải phần của điều kiện đúng/sai** cho ví dụ.

Khi kiểm thử, nên khẳng định trực tiếp các giá trị `dem == 3` và `danhSach.equals(Arrays.asList("a", "bb", "ccc"))`. Đừng viết test giả định `peek` luôn gọi ba lần, hoặc giả định số log không bao giờ xuất hiện.

## 10. Những lỗi thường gặp

| Lỗi hoặc hiểu nhầm | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `peek` không in gì khi dùng `count()` | Pipeline có thể được tối ưu mà không duyệt phần tử | Chỉ dùng `peek` để quan sát; không dựa vào tác dụng phụ |
| `map` bị bỏ qua, tác vụ trong lambda không chạy | `map` giữ nguyên số phần tử, `count` không cần kết quả biến đổi | Di chuyển tác vụ nghiệp vụ sang cách thực thi tường minh |
| `map(predicate).count()` trả về tổng số phần tử | `map` biến dữ liệu thành `Boolean`, không lọc | Thay bằng `filter(predicate).count()` |
| `int n = stream.count()` không biên dịch | `count` trả về `long` | Khai báo `long n` |
| Gọi `count()` rồi dùng lại cùng stream | Stream đã bị tiêu thụ | Tạo stream mới từ nguồn |
| `count()` trên stream vô hạn không hoàn thành | Không có điều kiện dừng | Thêm giới hạn hữu hạn hoặc điều kiện kết thúc |
| `filter(...).limit(n)` chạy mãi | Không bao giờ tìm đủ `n` phần tử phù hợp | Cân nhắc giới hạn nguồn trước `filter` |
| Dùng `collect(toList()).size()` chỉ để đếm | Tạo cấu trúc trung gian không cần thiết | Dùng `count()` |
| Dùng `count() > 0` chỉ để kiểm tra tồn tại | Có thể yêu cầu tính toàn bộ số lượng | Dùng `anyMatch` khi cần kiểm tra điều kiện |
| Thấy kết quả đúng rồi cho rằng lambda chắc chắn đã chạy | Tối ưu hóa có thể bỏ qua phép toán không ảnh hưởng đến số lượng | Viết logic không phụ thuộc tác dụng phụ |

Hiểu sai về tối ưu hóa có thể dẫn đến lỗi khó nhận ra vì **số lượng vẫn đúng** trong khi một thao tác phụ mong đợi lại không được thực thi.

## 11. Bài tập thực hành

### Bài 1 — Đếm phần tử theo điều kiện

Cho:

```java
List<Integer> diem = Arrays.asList(4, 7, 8, 10, 5, 7, 9);
```

Viết pipeline đếm số điểm **từ 7 trở lên**. Kết quả phải là `long`. Giải thích vì sao `map(d -> d >= 7).count()` không giải được yêu cầu.

### Bài 2 — Phân tích `peek` và `map`

```java
List<String> ten = Arrays.asList("A", "BB", "CCC", "DDDD");

long n = ten.stream()
    .map(s -> s + "!")
    .peek(System.out::println)
    .count();
```

`n` bằng bao nhiêu? Có thể khẳng định chương trình sẽ in đúng bốn dòng `A!`, `BB!`, `CCC!`, `DDDD!` không? Vì sao?

### Bài 3 — Thứ tự `filter` và `limit`

Dự đoán kết quả:

```java
long a = java.util.stream.IntStream.rangeClosed(1, 20)
    .filter(x -> x % 2 == 0)
    .limit(5)
    .count();

long b = java.util.stream.IntStream.rangeClosed(1, 20)
    .limit(5)
    .filter(x -> x % 2 == 0)
    .count();
```

### Bài 4 — Chọn terminal operation

Trong danh sách 100.000 sản phẩm, bạn chỉ cần biết **có sản phẩm nào đang hết hàng hay không**. Nên dùng `filter(p -> p.isOutOfStock()).count() > 0` hay `anyMatch(p -> p.isOutOfStock())`? Khi nào cần dùng `count()`?

### Bài 5 — Nhận diện pipeline có thể bị treo

```java
long n = Stream.iterate(1, x -> x + 1)
    .filter(x -> false)
    .limit(2)
    .count();
```

Đoạn mã có thể kết thúc không? Viết một cách sửa để phép đếm hoàn thành hữu hạn mà không thay đổi ý nghĩa "không có phần tử nào thỏa điều kiện".

### Đáp án tham khảo

**Bài 1:**

```java
long soDiemDat = diem.stream()
    .filter(d -> d >= 7)
    .count();

System.out.println(soDiemDat); // 5
```

Các điểm thỏa điều kiện là 7, 8, 10, 7, 9. `map` chỉ tạo các giá trị `true`/`false` nên tổng số phần tử vẫn là bảy.

**Bài 2:** `n == 4`. Cả `map` lẫn `peek` đều không thay đổi số lượng. Trên một triển khai biết sẵn kích thước, `count` có thể trả bốn ngay mà không đánh giá chúng. Do đó không có bảo đảm số dòng được in.

**Bài 3:** `a == 5` vì có ít nhất năm số chẵn trong 1..20; `b == 2` vì chỉ có 2 và 4 trong năm số đầu tiên.

**Bài 4:** Dùng `anyMatch(p -> p.isOutOfStock())` vì chỉ hỏi tồn tại và có thể dừng sớm khi gặp sản phẩm hết hàng. Dùng `filter(...).count()` khi cần **số sản phẩm hết hàng chính xác**.

**Bài 5:** Pipeline có thể chạy vô hạn vì `filter(x -> false)` không cho phần tử nào qua, nên `limit(2)` không bao giờ nhận đủ hai phần tử. Nếu chỉ cần đếm kết quả trong **100 trạng thái đầu tiên**, hãy giới hạn nguồn trước:

```java
long n = Stream.iterate(1, x -> x + 1)
    .limit(100)
    .filter(x -> false)
    .count();

System.out.println(n); // 0
```

Ở trường hợp điều kiện thật sự luôn sai, dùng luôn `Stream.empty().count()` cũng cho số 0; ý nghĩa tổng quát của bài tập là phải bảo đảm nguồn hữu hạn trước khi muốn tính số lượng chính xác.

## 12. Ghi nhớ

`count()` là terminal operation trả về **`long`**: số phần tử còn lại sau các bước xử lý. Vì số lượng có thể biết từ nguồn và thông tin cardinality của pipeline, **`count()` có thể trả kết quả mà không duyệt phần tử hoặc gọi các thao tác trung gian như `map` và `peek`**.

Để viết đúng:

- Dùng `filter(predicate).count()` để đếm phần tử thỏa điều kiện, `distinct().count()` để đếm giá trị duy nhất.
- Dùng `anyMatch` khi chỉ cần biết **có ít nhất một phần tử phù hợp**, hoặc `Collection.size()` khi chỉ cần kích thước của collection đã có.
- Không đặt các tác vụ bắt buộc thực hiện trong `peek` hoặc `map` chỉ để chờ `count()` kích hoạt.
- Kiểm soát điểm dừng khi nguồn có thể vô hạn, đồng thời chú ý thứ tự `filter` và `limit`.
- Đánh giá kết quả dựa vào **giá trị đếm**, không dựa vào số dòng log hay thứ tự gọi hàm.

Nhận biết khả năng bỏ qua duyệt giúp đọc đúng pipeline lazy, tránh lỗi do tác dụng phụ và hiểu nền tảng tối ưu hóa của Java Stream API trước khi chuyển sang grouping, collector tùy chỉnh, Spliterator và xử lý song song.
