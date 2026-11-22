# Thực hiện hai nhánh bằng `Optional.ifPresentOrElse()`

`Optional.ifPresentOrElse()` cho phép xử lý cả hai trường hợp của một `Optional`: có giá trị và không có giá trị. Khi có giá trị, phương thức gọi một `Consumer` với giá trị đó; khi rỗng, phương thức chạy một `Runnable` riêng. Nhờ vậy, hai nhánh của cùng một quyết định được đặt cạnh nhau, dễ đọc và khó bỏ sót nhánh rỗng.

Phương thức này được bổ sung từ Java 9 và vẫn là API hiện hành. Nó phù hợp khi mỗi nhánh cần thực hiện một hành động. Nếu mục tiêu là tạo ra một giá trị kết quả, các phép biến đổi như `map()`, `flatMap()`, `orElse()` hoặc `orElseGet()` thường phù hợp hơn.

## 1. Chữ ký và cách hoạt động

Chữ ký của phương thức là:

```java
void ifPresentOrElse(Consumer<? super T> action, Runnable emptyAction)
```

Hai tham số có trách nhiệm khác nhau:

| Tham số | Kiểu | Khi nào được gọi |
| --- | --- | --- |
| `action` | `Consumer<? super T>` | Khi `Optional` có giá trị; nhận giá trị đó làm đối số |
| `emptyAction` | `Runnable` | Khi `Optional` rỗng; không nhận đối số |

Phương thức có kiểu trả về `void`. Nó không trả lại giá trị từ callback và không biến `Optional` thành một kết quả mới. Trong một lần gọi, chỉ callback tương ứng với trạng thái hiện tại được thực thi.

Ví dụ ngắn:

```java
Optional<String> name = Optional.of("Linh");

name.ifPresentOrElse(
        value -> System.out.println("Welcome, " + value + "!"),
        () -> System.out.println("No name was provided.")
);
```

Vì `name` có giá trị `Linh`, lambda thứ nhất được gọi với `value` bằng `Linh`. Lambda thứ hai không chạy.

## 2. Xử lý cả trường hợp có giá trị và rỗng

Trong thực tế, một phương thức tìm kiếm có thể trả về `Optional<T>` để biểu diễn rằng kết quả có thể tồn tại hoặc không tồn tại. Người gọi có thể đặt hai hành động tương ứng ngay tại nơi sử dụng:

```java
Optional<User> user = userRepository.findById(userId);

user.ifPresentOrElse(
        this::showUser,
        () -> showNotFound(userId)
);
```

Nếu tìm thấy người dùng, `showUser` nhận đối tượng đó. Nếu không tìm thấy, `showNotFound` được gọi với mã người dùng cần tra cứu. Cả hai nhánh đều được thể hiện tường minh, thay vì phải ghép `isPresent()` với một lời gọi `get()`.

Không nên gọi `get()` trong nhánh rỗng. Khi `Optional` rỗng, `get()` ném `NoSuchElementException`; `ifPresentOrElse()` đã cung cấp callback riêng để xử lý tình huống này.

## 3. Ví dụ Java hoàn chỉnh

Ví dụ sau minh họa ba trường hợp: một `Optional` có giá trị, một `Optional.empty()` và một giá trị `null` được chuyển thành `Optional` rỗng bằng `ofNullable()`.

Tạo tệp `IfPresentOrElseDemo.java`:

```java
import java.util.Optional;

public class IfPresentOrElseDemo {
    private static void report(Optional<String> maybeName) {
        maybeName.ifPresentOrElse(
                name -> System.out.println("Welcome, " + name + "!"),
                () -> System.out.println("No name was provided.")
        );
    }

    public static void main(String[] args) {
        report(Optional.of("Linh"));
        report(Optional.empty());
        report(Optional.ofNullable(null));
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac --release 17 IfPresentOrElseDemo.java
java IfPresentOrElseDemo
```

Kết quả stdout:

```text
Welcome, Linh!
No name was provided.
No name was provided.
```

`Optional.of("Linh")` tạo một `Optional` có giá trị. `Optional.empty()` tạo một `Optional` rỗng. `Optional.ofNullable(null)` cũng tạo `Optional` rỗng vì đầu vào là `null`; do đó cả hai trường hợp sau đều chạy `emptyAction`.

`Optional.of(null)` có hành vi khác: nó ném `NullPointerException` ngay khi tạo `Optional`. Dùng `ofNullable()` khi đầu vào có thể là `null` và muốn biểu diễn trường hợp đó bằng `Optional.empty()`.

## 4. Kiểu callback và method reference

Tham số thứ nhất là `Consumer<? super T>`, vì vậy callback nhận một đối số tương thích với kiểu giá trị chứa trong `Optional`. Tham số thứ hai là `Runnable`, vì nhánh rỗng không có giá trị để truyền vào.

Có thể dùng lambda:

```java
optional.ifPresentOrElse(
        value -> process(value),
        () -> handleMissingValue()
);
```

Hoặc dùng method reference khi đã có phương thức phù hợp:

```java
optional.ifPresentOrElse(
        this::process,
        this::handleMissingValue
);
```

Phương thức `process` phải nhận một tham số phù hợp với kiểu phần tử; `handleMissingValue` phải là phương thức không tham số và trả về `void`. Nếu nhánh rỗng cần dùng thêm thông tin bên ngoài `Optional`, lambda có thể capture biến đó như `userId` trong ví dụ tìm người dùng.

## 5. Điều gì xảy ra nếu callback không hợp lệ hoặc ném lỗi?

Hai callback phải được cung cấp phù hợp với nhánh mà chúng xử lý. Nếu `Optional` có giá trị nhưng `action` là `null`, lời gọi ném `NullPointerException`. Nếu `Optional` rỗng nhưng `emptyAction` là `null`, lời gọi cũng ném `NullPointerException`. Hãy truyền lambda hoặc method reference hợp lệ cho cả hai nhánh.

Nếu callback được gọi ném một unchecked exception, exception đó truyền ra khỏi lời gọi `ifPresentOrElse()`; phương thức không tự bắt lỗi và cũng không tự chạy nhánh còn lại. Ví dụ, nếu `action` ném lỗi thì `emptyAction` không được chạy như một cơ chế fallback.

Callback của `ifPresentOrElse()` được thực thi ngay trong luồng đang gọi phương thức. API này không tự tạo thread, không chạy bất đồng bộ và không tự xử lý retry. Nếu callback thực hiện I/O hoặc cập nhật hệ thống bên ngoài, cần tự thiết kế xử lý lỗi và tác dụng phụ phù hợp.

## 6. So sánh với các phương thức Optional liên quan

| Phương thức | Mục đích |
| --- | --- |
| `ifPresent(action)` | Chỉ thực hiện hành động khi có giá trị; khi rỗng thì không làm gì |
| `ifPresentOrElse(action, emptyAction)` | Thực hiện một trong hai hành động tùy theo trạng thái |
| `map(mapper)` | Chuyển giá trị đang có thành giá trị khác, vẫn giữ kết quả dưới dạng `Optional` |
| `flatMap(mapper)` | Chuyển thành một `Optional` khác mà không lồng `Optional<Optional<T>>` |
| `orElse(other)` | Lấy giá trị đang có hoặc dùng giá trị thay thế |
| `orElseGet(supplier)` | Lấy giá trị đang có hoặc gọi supplier để tạo giá trị thay thế khi rỗng |
| `orElseThrow(supplier)` | Lấy giá trị đang có hoặc ném exception khi rỗng |

Ví dụ, nếu chỉ cần tạo một thông báo chuỗi, có thể dùng phép biến đổi và giá trị mặc định:

```java
String message = optionalName
        .map(name -> "Welcome, " + name + "!")
        .orElse("No name was provided.");
```

Đoạn mã này tạo ra một `String` để dùng tiếp. Ngược lại, `ifPresentOrElse()` thích hợp khi mỗi nhánh thực hiện một hành động như hiển thị thông tin, ghi nhận trạng thái hoặc gọi một phương thức xử lý.

`orElse()` đánh giá đối số của nó trước khi lời gọi phương thức diễn ra, kể cả khi `Optional` đã có giá trị. `orElseGet()` chỉ gọi supplier khi `Optional` rỗng. Nếu việc tạo giá trị thay thế tốn tài nguyên hoặc có tác dụng phụ, hãy cân nhắc `orElseGet()`.

## 7. Những lỗi thường gặp

- **Đảo thứ tự hai callback:** tham số thứ nhất luôn dành cho nhánh có giá trị; tham số thứ hai dành cho nhánh rỗng.
- **Viết nhầm `Runnable` thành lambda có tham số:** `emptyAction` không nhận giá trị. Dùng `() -> ...`, không dùng `value -> ...`.
- **Gọi `get()` trong nhánh rỗng:** nhánh này chỉ chạy khi không có giá trị, nên `get()` sẽ thất bại.
- **Truyền `null` thay callback:** callback của nhánh được thực thi phải hợp lệ; truyền lambda rỗng `() -> {}` nếu thật sự không cần hành động ở nhánh đó.
- **Mong phương thức trả về kết quả:** `ifPresentOrElse()` trả về `void`. Dùng `map`, `flatMap`, `orElse` hoặc `orElseGet` nếu cần một giá trị.
- **Cho rằng phương thức bắt exception:** lỗi từ callback truyền ra ngoài. Nếu cần xử lý lỗi, thực hiện trong callback hoặc tại nơi gọi.
- **Gọi trên một tham chiếu Optional bị null:** `Optional` bản thân phải là một đối tượng hợp lệ. Nếu nguồn có thể trả về tham chiếu null, chuẩn hóa bằng `Optional.ofNullable()` tại ranh giới phù hợp.

## 8. Cách sử dụng trong mã ứng dụng

Giữ callback ngắn và thể hiện đúng một hành động cho mỗi nhánh. Nếu xử lý phức tạp, tách thành các phương thức có tên để lời gọi dễ đọc:

```java
Optional<Order> order = orderService.findOrder(orderId);
order.ifPresentOrElse(
        this::confirmOrder,
        () -> reportMissingOrder(orderId)
);
```

Không cần viết `if (optional.isPresent())` rồi gọi `get()` chỉ để tách hai trường hợp. `ifPresentOrElse()` đã diễn đạt trực tiếp điều kiện và hai hành động. Tuy nhiên, nếu cần nhiều nhánh nghiệp vụ, cần trả về kết quả, hoặc cần kết hợp nhiều phép biến đổi, hãy chọn cấu trúc điều khiển hay chuỗi `Optional` phù hợp thay vì nhồi toàn bộ logic vào lambda.

`ifPresentOrElse()` giúp xử lý đầy đủ hai trạng thái của `Optional` tại một điểm gọi. Dùng callback thứ nhất cho giá trị hiện có, callback thứ hai cho trạng thái rỗng; chọn phương thức biến đổi hoặc lấy giá trị mặc định khi mục tiêu là tạo ra dữ liệu để tiếp tục xử lý.