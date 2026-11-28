# `Stream.toList()` trong Java 16 và Java hiện đại

`Stream.toList()` là terminal operation được bổ sung vào Stream API từ Java 16. Phương thức này thu các phần tử của một stream thành `List<T>` không sửa đổi được. Nếu stream có encounter order, danh sách kết quả giữ nguyên thứ tự đó.

Đây là cách ngắn gọn để nhận kết quả sau các bước `filter`, `map`, `sorted` hoặc `flatMap`. Điểm cần nhớ khi dùng là danh sách trả về không cho phép sửa đổi; nếu chương trình cần thêm, xóa hoặc thay thế phần tử, hãy chủ động tạo một danh sách mutable.

## 1. Cú pháp và cách hoạt động

```java
List<T> result = stream.toList();
```

- `T` là kiểu phần tử của stream.
- `toList()` trả về `List<T>` chứa các phần tử stream đã phát ra.
- Đây là **terminal operation**: khi gọi, pipeline được thực thi và stream được tiêu thụ. Không thể tiếp tục dùng chính stream đó cho một terminal operation khác.
- Phương thức có từ Java 16, vì vậy mã nguồn gọi phương thức này cần được biên dịch và chạy trên Java 16 trở lên.

Ví dụ, dùng `record` để biểu diễn đơn hàng và chuyển kết quả lọc thành danh sách mã đơn:

```java
import java.util.List;

record Order(String code, long total) {}

List<Order> orders = List.of(
    new Order("DH-001", 1_500_000),
    new Order("DH-002", 450_000),
    new Order("DH-003", 2_200_000)
);

List<String> highValueOrderCodes = orders.stream()
    .filter(order -> order.total() >= 1_000_000)
    .map(Order::code)
    .toList();

System.out.println(highValueOrderCodes);
// [DH-001, DH-003]
```

Pipeline lọc đơn hàng có tổng tiền từ một triệu trở lên, ánh xạ mỗi đơn hàng thành mã đơn rồi thu kết quả thành `List<String>`. Vì nguồn là một `List` có encounter order, thứ tự mã đơn trong kết quả giống thứ tự các đơn hàng phù hợp ở nguồn.

## 2. Danh sách trả về không sửa đổi được

Hợp đồng quan trọng nhất của `Stream.toList()` là danh sách trả về **unmodifiable**. Các thao tác thay đổi danh sách như `add`, `remove`, `set`, `clear` hoặc `sort` sẽ ném `UnsupportedOperationException`.

```java
import java.util.List;

List<String> names = List.of("An", "Bình", "Chi").stream()
    .filter(name -> name.length() <= 3)
    .toList();

// names.add("Dung");       // UnsupportedOperationException
// names.set(0, "Anh");     // UnsupportedOperationException
// names.sort(String::compareTo); // UnsupportedOperationException
```

Vì vậy, hãy hoàn thành việc lọc, ánh xạ và sắp xếp ngay trong pipeline trước khi gọi `toList()`:

```java
import java.util.List;

List<String> namesSource = List.of("Chi", "An", "Bình", "Dung");

List<String> sortedNames = namesSource.stream()
    .filter(name -> !name.isBlank())
    .map(String::trim)
    .sorted()
    .toList();
```

Tên gọi *unmodifiable* mô tả cấu trúc danh sách, không đảm bảo các đối tượng nằm bên trong cũng bất biến. Nếu phần tử là đối tượng mutable, chương trình vẫn có thể thay đổi trạng thái của đối tượng đó:

```java
import java.util.List;
import java.util.stream.Stream;

List<StringBuilder> values = Stream.of(new StringBuilder("A")).toList();
values.get(0).append("B"); // Hợp lệ: thay đổi đối tượng StringBuilder
// values.add(new StringBuilder("C")); // Không hợp lệ: thay đổi cấu trúc List
```

Danh sách không sửa đổi được, nhưng điều đó không tạo ra bản sao bất biến sâu của toàn bộ object graph.

## 3. Giữ thứ tự phần tử

Nếu stream có encounter order, `toList()` đưa các phần tử vào kết quả theo thứ tự đó. Ví dụ, stream từ `List`, sau các thao tác `filter` và `map`, vẫn giữ thứ tự tương đối của những phần tử còn lại.

```java
import java.util.List;

List<Integer> oddNumbers = List.of(5, 2, 7, 4, 1).parallelStream()
    .filter(number -> number % 2 != 0)
    .toList();

System.out.println(oddNumbers);
// [5, 7, 1]
```

Việc dùng `parallelStream()` không tự làm mất encounter order. Tuy nhiên, nếu nguồn không có encounter order hoặc pipeline gọi `unordered()`, không nên dựa vào một thứ tự cụ thể trong danh sách kết quả.

## 4. Chọn `toList()` hay một collector khác?

`Stream.toList()` và `Collectors.toList()` có tên gần giống nhau nhưng hợp đồng về khả năng sửa đổi khác nhau.

| Cách thu thập | Hợp đồng về kết quả | Khi nên dùng |
| --- | --- | --- |
| `stream.toList()` | Trả về `List` không sửa đổi được; giữ encounter order nếu stream có thứ tự. | Khi chỉ cần đọc hoặc chuyển giao kết quả dưới dạng danh sách không sửa đổi được. |
| `stream.collect(Collectors.toList())` | Không có bảo đảm về kiểu triển khai, khả năng sửa đổi, khả năng tuần tự hóa hoặc thread-safety của `List`. | Khi cần dùng collector `toList`; không dựa vào việc một JDK cụ thể hiện trả về `ArrayList`. |
| `stream.collect(Collectors.toUnmodifiableList())` | Trả về danh sách không sửa đổi được và từ chối phần tử `null` bằng `NullPointerException`. | Khi muốn thể hiện rõ chính sách không nhận `null` trong collector. |
| `stream.collect(Collectors.toCollection(ArrayList::new))` | Tạo đúng loại collection do factory chỉ định; với `ArrayList::new`, kết quả là `ArrayList` mutable. | Khi cần thêm, xóa, sắp xếp hoặc thay thế phần tử sau khi thu thập. |

Ví dụ tạo danh sách có thể chỉnh sửa:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Collectors;

List<String> source = List.of(" An ", "Bình", "", "Chi ");

List<String> mutableNames = source.stream()
    .filter(name -> !name.isBlank())
    .map(String::trim)
    .collect(Collectors.toCollection(ArrayList::new));

mutableNames.add("Dung"); // Hợp lệ
```

Nếu đã có kết quả từ `toList()` và chỉ muốn tạo một bản sao mutable, có thể dùng constructor của `ArrayList`:

```java
import java.util.ArrayList;
import java.util.List;

List<String> source = List.of("An", "Bình", "Chi");
List<String> readOnlyNames = source.stream().toList();
List<String> editableNames = new ArrayList<>(readOnlyNames);
editableNames.add("Dung");
```

`Collectors.toList()` không cam kết kết quả luôn mutable, dù một số triển khai JDK thường trả về `ArrayList`. Nếu tính mutable là yêu cầu của chương trình, hãy nói rõ loại collection bằng `toCollection(...)`.

## 5. Những điều không nên giả định

**Không giả định kiểu triển khai.** Kiểu trả về được khai báo là `List<T>`. Không ép kiểu kết quả thành `ArrayList` hoặc phụ thuộc vào một lớp triển khai cụ thể:

```java
import java.util.List;

List<String> names = List.of("An", "Bình").stream().toList();
```

**Không dựa vào identity của danh sách.** API cho biết kết quả có thể là value-based. Không dùng `==`, `System.identityHashCode()` hoặc khóa `synchronized` trên danh sách này để xây dựng logic. Nếu cần so sánh nội dung, dùng `equals()`.

**Không xem đây là bản sao sâu.** Danh sách mới chứa các phần tử do stream phát ra; nếu các phần tử là object mutable, các tham chiếu trong danh sách vẫn trỏ tới những object đó.

**Không thu thập stream không giới hạn mà không đặt giới hạn.** `toList()` phải thu toàn bộ phần tử kết quả trước khi trả về, nên cần bộ nhớ tương ứng với số phần tử. Với nguồn vô hạn hoặc rất lớn, hãy giới hạn dữ liệu trước khi thu thập hoặc xử lý theo cách không cần giữ toàn bộ kết quả trong bộ nhớ:

```java
import java.util.List;
import java.util.stream.Stream;

List<Integer> firstHundred = Stream.iterate(1, number -> number + 1)
    .limit(100)
    .toList();
```

## 6. Cách dùng trong mã nguồn hiện đại

Ưu tiên `toList()` khi pipeline tạo ra một kết quả danh sách chỉ cần đọc, chẳng hạn danh sách DTO, mã định danh hoặc các mục đã lọc để trả về từ một phương thức. Điều này thể hiện rõ ý định rằng bên nhận không được sửa đổi danh sách kết quả.

Nếu hợp đồng của phương thức yêu cầu bên gọi được quyền chỉnh sửa danh sách, hãy tạo collection mutable có chủ đích bằng `Collectors.toCollection(...)` hoặc sao chép kết quả vào `ArrayList`. Đừng để hành vi của mã phụ thuộc vào lớp triển khai mà `Collectors.toList()` tình cờ trả về trên một phiên bản JDK.

`Stream.toList()` vẫn là API chuẩn trong các phiên bản Java hiện đại. Khi đọc hoặc viết code, hãy nhớ ba điểm: đây là terminal operation có từ Java 16, danh sách kết quả không sửa đổi được, và encounter order được giữ nếu stream có thứ tự.

## Tài liệu tham khảo

- [Stream.toList() – Java SE API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Stream.html#toList())
- [Collectors.toList(), toUnmodifiableList() và toCollection() – Java SE API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Collectors.html)
