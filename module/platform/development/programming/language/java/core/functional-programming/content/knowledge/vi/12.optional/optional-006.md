# Optional.or(), orElseThrow() và lựa chọn xử lý khi không có giá trị

## Mục tiêu

`Optional<T>` trong `java.util` biểu diễn một kết quả **có thể có một giá trị khác `null` hoặc không có giá trị**. Khi `Optional` rỗng, không phải lúc nào ứng dụng cũng nên trả một hằng số mặc định: có trường hợp cần tìm tiếp ở một nguồn khác, có trường hợp cần báo lỗi, bỏ qua công việc hoặc kết thúc luồng xử lý.

Bài này tập trung vào hai nhóm thao tác:

- `or(Supplier<? extends Optional<? extends T>>)`: **tiếp tục tìm một `Optional` khác** khi nguồn đầu tiên rỗng.
- `orElseThrow()` và `orElseThrow(Supplier<? extends X>)`: **lấy giá trị bắt buộc** hoặc ném ngoại lệ khi không có giá trị.

Sau bài học, bạn sẽ phân biệt được các API xử lý “không có giá trị”, chọn được cơ chế fallback phù hợp, dự đoán khi nào Supplier được gọi, sử dụng checked exception đúng cách và tránh lỗi `null`, exception sai tầng hoặc truy vấn thừa.

## 1. Hiểu Optional trước khi lựa chọn nhánh xử lý

Một `Optional<String>` thường được tạo theo ba cách:

```java
import java.util.Optional;

Optional<String> present = Optional.of("An");
Optional<String> absent = Optional.empty();
Optional<String> possiblyAbsent = Optional.ofNullable(null);
```

- `Optional.of(value)` tạo Optional chứa `value` và ném `NullPointerException` nếu `value == null`.
- `Optional.ofNullable(value)` tạo Optional có giá trị khi `value != null`, hoặc Optional rỗng khi `value == null`.
- `Optional.empty()` tạo Optional rỗng.

Một `Optional` không phải “hộp chứa `null`”: nếu rỗng thì không có phần tử bên trong. Điều này giúp API biểu đạt việc không tìm thấy dữ liệu bằng một trạng thái có chủ đích, thay vì để mọi caller đoán xem `null` có ý nghĩa gì.

Xét nghiệp vụ tìm tên hiển thị:

1. Đầu tiên tìm tên được cấu hình riêng cho người dùng.
2. Nếu không có, thử tên ở hồ sơ dự phòng.
3. Nếu vẫn không có, hoặc dùng một tên mặc định hợp lệ, hoặc ném ngoại lệ tùy yêu cầu tính đúng đắn.

**Lựa chọn cuối cùng phải dựa trên nghiệp vụ.** Một trường không bắt buộc như biệt danh có thể trả mặc định; mã định danh giao dịch bắt buộc không nên tự nhận một mã giả.

## 2. Optional.or(): tìm một Optional khác theo nhu cầu

Chữ ký của `or` (có từ Java 9) là:

```java
public Optional<T> or(
    Supplier<? extends Optional<? extends T>> supplier);
```

Đây là chữ ký API để giải thích, không phải định nghĩa lại phương thức trong ứng dụng. `Supplier` thuộc `java.util.function`; function descriptor của nó là `() -> Optional<? extends T>`.

Luồng hoạt động:

1. Nếu Optional **đang có giá trị**, trả về Optional hiện có, **không gọi** `supplier.get()`.
2. Nếu Optional **rỗng**, gọi `supplier.get()` để lấy một Optional dự phòng.
3. Optional dự phòng có thể **có giá trị hoặc tiếp tục rỗng**.
4. Supplier hoặc Optional trả về là `null` không hợp lệ; đặc biệt khi Supplier được gọi mà trả `null`, `or` ném `NullPointerException`.

Ví dụ minh họa:

```java
Optional<String> local = Optional.empty();

Optional<String> result = local.or(
        () -> Optional.of("backup")
);

System.out.println(result.orElseThrow()); // backup
```

Ngược lại:

```java
Optional<String> local = Optional.of("primary");

Optional<String> result = local.or(() -> {
    System.out.println("Đọc nguồn dự phòng");
    return Optional.of("backup");
});

System.out.println(result.orElseThrow()); // primary
```

Ở trường hợp thứ hai, dòng `Đọc nguồn dự phòng` **không được in** vì Optional đầu đã có giá trị. Đây là **lazy fallback**: tác vụ dự phòng được đặt trong body lambda và chỉ chạy khi cần.

Các đoạn trên là minh họa độc lập từng tình huống; cần khai báo/import `Optional` và đặt trong phương thức hợp lệ.

### 2.1. Vì sao or() nhận Optional thay vì giá trị T?

`or` không đơn thuần cung cấp một giá trị thay thế. Nó cho phép **tiếp tục duy trì ngữ nghĩa có/không có giá trị** khi thử nguồn dự phòng:

```java
Optional<String> result = Optional.<String>empty()
        .or(() -> Optional.empty());

System.out.println(result.isEmpty()); // true
```

Nếu nguồn dự phòng cũng không có dữ liệu, kết quả vẫn là Optional rỗng để các tầng tiếp theo quyết định. Với chuỗi xử lý có nhiều nguồn, điều này hữu ích hơn việc bắt buộc cung cấp ngay một `String` giả định.

`orElseGet(Supplier<? extends T>)` khác `or`: nó trả trực tiếp **`T`**, không trả Optional. Viết `optional.or(() -> "backup")` không biên dịch vì lambda trả `String`, trong khi `or` yêu cầu Supplier trả một `Optional`. Viết `optional.or(() -> Optional.of("backup"))` mới đúng.

## 3. Chuỗi nguồn dự phòng: fallback theo thứ tự ưu tiên

Giả sử chương trình có các phương thức tìm dữ liệu:

```java
Optional<User> findInSession(String id);
Optional<User> findInDatabase(String id);
Optional<User> findInArchive(String id);
```

Đây chỉ là **chữ ký minh họa**; lớp `User` và các phương thức cần triển khai trong ứng dụng thực. Có thể kết hợp:

```java
Optional<User> user = findInSession(id)
        .or(() -> findInDatabase(id))
        .or(() -> findInArchive(id));
```

Với luồng này:

- Nếu session có `User`, không gọi database hoặc archive.
- Nếu session rỗng và database có `User`, không gọi archive.
- Chỉ khi hai nguồn đầu đều rỗng mới gọi archive.
- Nếu cả ba đều rỗng, kết quả cuối là `Optional.empty()`.

**Thứ tự nguồn rất quan trọng:** kết quả mang chính sách ưu tiên session → database → archive. Nếu đọc database hoặc archive tốn tài nguyên, `or` còn giúp tránh các lời gọi không cần thiết.

### Không vô tình đánh giá fallback sớm

```java
// Sai về ý định lazy: hàm đã chạy để tạo biến.
Optional<User> backup = findInDatabase(id);
Optional<User> result = findInSession(id).or(() -> backup);
```

Đoạn này có thể biên dịch trong một phương thức phù hợp, nhưng `findInDatabase(id)` đã chạy **trước** khi `or` quyết định có cần dữ liệu hay không. Muốn trì hoãn, đặt lệnh tìm kiếm bên trong lambda:

```java
Optional<User> result = findInSession(id)
        .or(() -> findInDatabase(id));
```

Tương tự, nếu tạo sẵn một Supplier nhưng phần dữ liệu đã được tải trước khi tạo nó, Supplier không làm thao tác đó trở thành lazy.

## 4. orElseThrow(): giá trị là bắt buộc

### 4.1. Bản không tham số

Phương thức:

```java
public T orElseThrow();
```

Có từ **Java 10**. Nếu Optional có giá trị, nó trả giá trị đó. Nếu rỗng, nó ném `NoSuchElementException`, là một **unchecked exception** thuộc `java.util`.

```java
String title = Optional.of("Java").orElseThrow();
// title là "Java".

Optional.<String>empty().orElseThrow();
// Ném NoSuchElementException.
```

Đây là hai biểu thức minh họa riêng. Không có cơ chế fallback trong bản không tham số: nó tuyên bố caller **yêu cầu phải có một giá trị**.

`Optional.get()` cũng trả giá trị hoặc ném `NoSuchElementException` khi rỗng. Trong mã hiện đại, `orElseThrow()` thường làm rõ ý định “thiếu dữ liệu là lỗi” hơn tên `get()`, đặc biệt khi đọc cùng các thao tác `or` và `orElseGet`.

**Không nên lạm dụng** `orElseThrow()` ở mọi điểm chỉ để thoát khỏi Optional. Nếu Optional rỗng là trạng thái nghiệp vụ bình thường, ném exception không phải lựa chọn đúng nhất.

### 4.2. Bản nhận Supplier tạo ngoại lệ

Chữ ký tổng quát:

```java
public <X extends Throwable> T orElseThrow(
        Supplier<? extends X> exceptionSupplier) throws X;
```

Bản này có từ **Java 8**. Khi Optional có giá trị, Supplier **không được gọi** và giá trị được trả về. Khi rỗng, Supplier được gọi để cung cấp một đối tượng `Throwable`, sau đó đối tượng đó được **ném ra**.

```java
String token = maybeToken.orElseThrow(
        () -> new IllegalStateException("Token bắt buộc")
);
```

Với `maybeToken` kiểu `Optional<String>` đã khai báo, biểu thức trên:

- Trả chuỗi khi có token.
- Khi rỗng, tạo và ném `IllegalStateException` chứa thông điệp cụ thể.

Bằng cách truyền **Supplier tạo exception**, chương trình có thể trì hoãn việc tạo exception cho đến khi thực sự cần. Điều này vừa diễn đạt chính sách lỗi, vừa tránh tạo object exception không cần thiết khi dữ liệu tồn tại.

### 4.3. Checked exception và throws X

Một lợi ích quan trọng của bản nhận Supplier là có thể **ném checked exception có kiểu cụ thể**:

```java
static String requireToken(Optional<String> source)
        throws java.io.IOException {
    return source.orElseThrow(
            () -> new java.io.IOException("missing token")
    );
}
```

Ví dụ trên minh họa một phương thức hoàn chỉnh cần đặt trong class có import `Optional`. Vì Supplier tạo `IOException`, việc gọi `orElseThrow` có thể ném checked exception đó. Phương thức bao quanh phải khai báo `throws IOException` hoặc bắt ngoại lệ.

**Điểm dễ nhầm:** `Supplier.get()` **không khai báo checked exception**. Trong ví dụ, lambda **không tự ném `IOException` từ body**; nó **trả về một object `IOException`** để `Optional.orElseThrow` ném. Đó là lý do bản này tương thích với `Supplier<? extends X>` dù phương thức `get()` không có `throws`.

Không đồng nhất hai cách sau:

```java
// Đúng: lambda trả object IOException.
() -> new java.io.IOException("missing")

// Sai khi gán cho Supplier<IOException>: body ném checked IOException
// từ chính phương thức Supplier.get(), vốn không khai báo throws.
() -> { throw new java.io.IOException("missing"); }
```

Hai lambda trên chỉ là **đoạn minh họa cần một target type thích hợp**. Chúng thể hiện khác biệt giữa **tạo và trả exception** với **ném exception từ body Supplier**.

### 4.4. Supplier trả null là lỗi

Nếu Optional rỗng mà exception supplier trả `null`, chương trình không có đối tượng Throwable hợp lệ để ném; `NullPointerException` xảy ra.

```java
Optional.<String>empty()
        .orElseThrow(() -> null); // NPE
```

Không nên dùng Supplier trả null để biểu đạt “không cần báo lỗi”. Nếu rỗng là bình thường, chọn `orElse`, `orElseGet`, `ifPresentOrElse` hoặc trả lại Optional tùy hợp đồng.

## 5. So sánh các lựa chọn khi không có giá trị

| Nhu cầu | Phương thức | Khi Optional rỗng | Kiểu kết quả |
| --- | --- | --- | --- |
| Cần tìm tiếp nguồn khác, vẫn giữ Optional | `or(supplier)` | Gọi Supplier cung cấp **Optional** khác | `Optional<T>` |
| Có giá trị dự phòng tính sẵn | `orElse(value)` | Trả giá trị dự phòng | `T` |
| Cần tạo giá trị dự phòng theo nhu cầu | `orElseGet(supplier)` | Gọi Supplier cung cấp `T` | `T` |
| Thiếu giá trị là lỗi, không cần thông điệp riêng | `orElseThrow()` | Ném `NoSuchElementException` | `T` hoặc exception |
| Thiếu giá trị là lỗi nghiệp vụ cụ thể | `orElseThrow(exceptionSupplier)` | Gọi Supplier tạo exception rồi ném | `T` hoặc exception |
| Làm hai nhánh hành động, không cần trả T | `ifPresentOrElse(action, emptyAction)` | Chạy `Runnable` ở nhánh rỗng | `void` |
| Chỉ xử lý khi có giá trị | `ifPresent(action)` | Không làm gì | `void` |
| Muốn trả 0 hoặc 1 phần tử vào Stream | `stream()` | Tạo Stream rỗng | `Stream<T>` |

**`orElse` không lazy đối với biểu thức đối số.** Java đánh giá đối số trước khi vào phương thức:

```java
String result = optional.orElse(expensiveDefault());
```

`expensiveDefault()` vẫn chạy dù `optional` đã có giá trị. Ngược lại:

```java
String result = optional.orElseGet(() -> expensiveDefault());
```

Body của Supplier chỉ chạy khi Optional rỗng. Những đoạn này là minh họa, giả định `optional` và `expensiveDefault()` đã tồn tại trong ngữ cảnh sử dụng.

**Về `null`:** `orElse(null)` và `orElseGet(() -> null)` có thể trả null khi Optional rỗng; còn `or(() -> null)` không hợp lệ về hợp đồng và ném NPE khi Supplier được gọi. `orElseThrow(() -> null)` cũng phát sinh NPE ở nhánh rỗng. Hãy tránh dùng null làm “kết quả dự phòng” nếu caller đang kỳ vọng một giá trị có nghĩa.

## 6. Chương trình Java 17: or(), orElseThrow() và nhánh rỗng

Ví dụ sau sử dụng `AtomicInteger` để đếm số lần chạy Supplier, chứng minh fallback thực sự lazy và minh họa cả ngoại lệ checked lẫn unchecked.

Tạo tệp **`OptionalFallbackDemo.java`**:

```java
import java.io.IOException;
import java.util.NoSuchElementException;
import java.util.Optional;
import java.util.concurrent.atomic.AtomicInteger;

public class OptionalFallbackDemo {
    static Optional<String> fromBackup(AtomicInteger calls) {
        calls.incrementAndGet();
        return Optional.of("backup");
    }

    static String requireToken(Optional<String> source) throws IOException {
        return source.orElseThrow(() -> new IOException("missing token"));
    }

    public static void main(String[] args) {
        AtomicInteger backupCalls = new AtomicInteger();
        Optional<String> first = Optional.empty();

        Optional<String> found = first.or(() -> fromBackup(backupCalls));
        System.out.println("Found: " + found.orElseThrow());
        System.out.println("Backup calls: " + backupCalls.get());

        Optional<String> existing = Optional.of("primary");
        String chosen = existing
                .or(() -> fromBackup(backupCalls))
                .orElseThrow();
        System.out.println("Existing: " + chosen);
        System.out.println("Backup calls after existing: " + backupCalls.get());

        AtomicInteger exceptionCalls = new AtomicInteger();
        String safe = existing.orElseThrow(() -> {
            exceptionCalls.incrementAndGet();
            return new IllegalArgumentException("required");
        });
        System.out.println("Safe: " + safe);
        System.out.println("Exception suppliers: " + exceptionCalls.get());

        try {
            Optional.<String>empty().orElseThrow();
        } catch (NoSuchElementException e) {
            System.out.println("Empty: " + e.getClass().getSimpleName());
        }

        try {
            requireToken(Optional.empty());
        } catch (IOException e) {
            System.out.println("Checked: " + e.getMessage());
        }

        try {
            Optional.<String>empty().or(() -> null);
        } catch (NullPointerException e) {
            System.out.println("Null Optional supplier: "
                    + e.getClass().getSimpleName());
        }

        Optional<String> notFound = Optional.<String>empty()
                .or(Optional::empty);
        System.out.println("Still empty: " + notFound.isEmpty());
    }
}
```

Biên dịch và chạy bằng **JDK 17 hoặc mới hơn**:

```bash
javac OptionalFallbackDemo.java
java OptionalFallbackDemo
```

Đầu ra tiêu chuẩn:

```text
Found: backup
Backup calls: 1
Existing: primary
Backup calls after existing: 1
Safe: primary
Exception suppliers: 0
Empty: NoSuchElementException
Checked: missing token
Null Optional supplier: NullPointerException
Still empty: true
```

### Đối chiếu mã với kết quả

1. `first` rỗng nên `first.or(...)` gọi `fromBackup`, tăng `backupCalls` thành `1`, rồi trả Optional chứa `"backup"`. `found.orElseThrow()` lấy chuỗi thành công.
2. `existing` chứa `"primary"` nên `or` **không gọi** `fromBackup`. Số lần dùng nguồn dự phòng giữ nguyên `1`.
3. `existing.orElseThrow(exceptionSupplier)` thấy có giá trị nên không chạy body Supplier, không tăng `exceptionCalls`. `safe` là `"primary"`.
4. `Optional.empty().orElseThrow()` ném `NoSuchElementException`; `catch` in tên lớp, không phụ thuộc thông điệp mặc định có thể thay đổi.
5. `requireToken(Optional.empty())` gọi Supplier tạo `IOException("missing token")`, sau đó ném `IOException`; `main` bắt và in `Checked: missing token`.
6. `Optional.empty().or(() -> null)` yêu cầu Supplier cung cấp Optional nhưng nhận null, nên phát sinh `NullPointerException`. Chương trình bắt để tiếp tục.
7. `Optional.empty().or(Optional::empty)` vẫn rỗng; `Optional::empty` là method reference tới factory static trả Optional rỗng.

Đây là một chương trình **độc lập**, không chứa thao tác mạng hoặc dữ liệu ngoài. Mỗi nhánh được xây dựng để đầu ra xác định. `AtomicInteger` được dùng làm bộ đếm quan sát trong ví dụ; nó không có nghĩa `Optional.or` tự mang trạng thái hay tự cache kết quả.

## 7. Chọn fail-fast hay fallback theo ngữ nghĩa dữ liệu

### 7.1. Không có giá trị là trường hợp bình thường

Tìm bộ lọc tùy chọn, biệt danh hoặc mô tả phụ có thể không thành công mà không phải lỗi. Những cách xử lý thường phù hợp:

```java
String displayName = nickname.orElse("Guest");
```

hoặc:

```java
nickname.ifPresent(name -> System.out.println("Tên: " + name));
```

hoặc giữ Optional ở tầng dữ liệu:

```java
Optional<String> nickname = repository.findNickname(userId);
return nickname;
```

Đây là các đoạn minh họa **riêng**, giả định `nickname`, `repository`, `userId` và kiểu trả về của phương thức bao quanh đã được khai báo thích hợp. Giữ Optional khi caller có quyền quyết định chính sách thiếu dữ liệu; đừng ép repository tự chọn một tên giả làm sai lệch ý nghĩa kết quả.

### 7.2. Có nguồn dự phòng mang ý nghĩa nghiệp vụ

Một hệ thống có thể tìm người dùng theo thứ tự session, bộ nhớ đệm rồi database:

```java
Optional<User> user = session.find(userId)
        .or(() -> cache.find(userId))
        .or(() -> database.find(userId));
```

Nếu cả ba nguồn đều hợp lệ và có cùng mô hình `Optional<User>`, `or` diễn tả rất rõ việc **thử nguồn sau chỉ khi nguồn trước không có giá trị**. Hãy lưu ý khả năng kết quả ở từng nguồn có độ mới khác nhau, lỗi truy cập nguồn không đồng nghĩa “không tìm thấy” và I/O có thể ném exception.

Đừng bắt tất cả exception rồi chuyển thành `Optional.empty()` để ép pipeline tiếp tục, trừ khi chính sách thực sự coi lỗi truy cập là “không có dữ liệu”. Mất kết nối database khác với người dùng không tồn tại.

### 7.3. Thiếu dữ liệu vi phạm hợp đồng

Ví dụ mã cấu hình bắt buộc hoặc một thực thể mà API cam kết phải tồn tại:

```java
User user = repository.findRequiredUser(userId)
        .orElseThrow(() ->
                new IllegalStateException("User not found: " + userId));
```

Đây là mã minh họa. Nếu không có user là **lỗi đầu vào của caller**, có thể dùng `IllegalArgumentException`; nếu là **bất biến hệ thống bị vi phạm**, có thể chọn `IllegalStateException`; trong service có lớp lỗi riêng có thể tạo exception nghiệp vụ. Chọn loại exception dựa trên **hợp đồng API** chứ không theo thói quen.

Trong API HTTP, nhiều ứng dụng chuyển lỗi “không tìm thấy” thành HTTP 404 ở lớp biên; không nên để lớp domain tự phụ thuộc vào HTTP nếu nó còn được dùng trong CLI hoặc batch processing. `orElseThrow` là điểm ra quyết định “thiếu dữ liệu không thể tiếp tục”, còn cách trả phản hồi do lớp phù hợp thực hiện.

### 7.4. Muốn thử nguồn khác khi một nguồn báo lỗi?

`or` chỉ được gọi khi Optional **rỗng**, không tự bắt exception từ nguồn trước:

```java
Optional<User> user = primary.find(id)
        .or(() -> secondary.find(id));
```

Nếu `primary.find(id)` ném exception, biểu thức không tạo được kết quả Optional và `secondary.find(id)` không được gọi thông qua `or`. Nếu yêu cầu fallback cả khi hỏng mạng, phải thiết kế riêng chính sách bắt/retry/chuyển lỗi. Đừng đánh đồng “rỗng” với “thất bại”.

## 8. Kết hợp với map(), flatMap(), filter() và stream()

### 8.1. Tránh Optional lồng nhau

Giả sử:

```java
Optional<User> user = findUser(id);
```

Nếu `User.getNickname()` trả `Optional<String>`, dùng `flatMap` để tránh tạo `Optional<Optional<String>>`:

```java
Optional<String> nickname = user
        .flatMap(User::getNickname)
        .or(() -> findGlobalNickname(id));
```

Đây là mã minh họa, cần định nghĩa `User` và các phương thức tìm kiếm. `flatMap` ở đây chuyển từ Optional của User sang Optional của nickname. `or` sau đó cung cấp một Optional dự phòng **cùng kiểu giá trị String**.

Nếu dùng `map(User::getNickname)` với phương thức trả `Optional<String>`, kết quả có dạng `Optional<Optional<String>>`, không phải dạng cuối mong muốn. Đây là một trong những nguyên nhân người học khó kết hợp chuỗi Optional.

### 8.2. filter() làm Optional trở thành rỗng khi không thỏa điều kiện

```java
Optional<String> active = Optional.of("  ")
        .filter(value -> !value.isBlank())
        .or(() -> Optional.of("Guest"));

System.out.println(active.orElseThrow()); // Guest
```

`filter` không chuyển đổi giá trị mà giữ hoặc loại bỏ giá trị theo `Predicate`. Vì chuỗi toàn khoảng trắng không hợp lệ cho tên hiển thị, kết quả sau filter rỗng, khiến `or` được gọi.

### 8.3. stream() cho xử lý tập hợp

Từ Java 9, `Optional.stream()` chuyển Optional có giá trị thành Stream một phần tử và Optional rỗng thành Stream rỗng:

```java
List<Optional<String>> candidates = List.of(
        Optional.empty(),
        Optional.of("An"),
        Optional.of("Mai")
);

List<String> names = candidates.stream()
        .flatMap(Optional::stream)
        .toList(); // [An, Mai]
```

Đoạn minh họa cần import `List` và `Optional`. Kỹ thuật này phù hợp khi muốn **thu thập tất cả giá trị hiện có**; khác với `or` dùng để chọn nguồn đầu tiên có giá trị theo thứ tự ưu tiên. Đừng đổi `or` thành xử lý toàn bộ Stream nếu nghiệp vụ chỉ cần nguồn đầu tiên và không muốn gọi nguồn đắt đỏ.

## 9. Phân biệt lỗi lập trình với trạng thái thiếu giá trị

### 9.1. Optional không thay thế kiểm tra null ở mọi tầng

`Optional.ofNullable(raw)` hữu ích tại ranh giới với API cũ có thể trả null. Nhưng bản thân việc tồn tại Optional không buộc mọi object, collection hoặc field đều tự hợp lệ. Đặc biệt, `or` kỳ vọng **Supplier trả về một Optional object, không phải null**; thiết kế phương thức trả Optional nên tuân thủ hợp đồng không trả null.

Ví dụ sai:

```java
Optional<String> result = Optional.<String>empty()
        .or(() -> null); // ném NullPointerException
```

Sửa:

```java
Optional<String> result = Optional.<String>empty()
        .or(Optional::empty); // vẫn rỗng, hợp lệ
```

Nếu nguồn cũ có thể trả `String` null, hãy bao bọc đúng:

```java
Optional<String> result = Optional.<String>empty()
        .or(() -> Optional.ofNullable(legacyLookup()));
```

Các đoạn trên là minh họa; `legacyLookup()` phải được định nghĩa trong chương trình thực.

### 9.2. Không dùng exception cho luồng bình thường với tần suất lớn

Lặp lại `orElseThrow()` rồi bắt `NoSuchElementException` ở một vòng xử lý hàng triệu kết quả vắng mặt có thể gây chi phí và làm rối ý nghĩa. Nếu rỗng là trường hợp bình thường, dùng `ifPresent`, `ifPresentOrElse`, `orElse` hoặc `stream`; chỉ ném exception khi thật sự **không thể tiếp tục đúng**.

### 9.3. Không bọc ngoại lệ thành Optional.empty() vô điều kiện

Một helper làm:

```java
try {
    return repository.load(id);
} catch (Exception e) {
    return Optional.empty();
}
```

là đoạn minh họa có thể che giấu lỗi mạng, lỗi phân quyền hoặc hỏng dữ liệu. Khi truyền qua `or`, nguồn tiếp theo có thể được gọi dù nguyên nhân thực tế là hệ thống hỏng, tạo hành vi khó giám sát. Chỉ chuyển một số ngoại lệ cụ thể thành “không có dữ liệu” khi nghiệp vụ cho phép và vẫn quan sát được lỗi kỹ thuật.

### 9.4. Không nhầm “Supplier ném lỗi” với “Supplier tạo lỗi”

`orElseThrow(() -> new IOException("missing"))` tạo object IOException để chính `orElseThrow` ném, vì thế gọi method bao quanh cần khai báo `throws IOException`. Nhưng body lambda kiểu `() -> { throw new IOException("missing"); }` không tương thích với `Supplier<IOException>` do `Supplier.get` không khai báo checked exception. Đây là khác biệt của **hợp đồng hàm**, không chỉ khác cú pháp.

## 10. Thời điểm thực thi và hiệu năng

| Biểu thức | Đánh giá tác vụ dự phòng khi Optional có giá trị? | Khi Optional rỗng? |
| --- | --- | --- |
| `opt.or(() -> findBackup())` | Không | Gọi `findBackup()`, nhận Optional |
| `opt.orElse(expensiveValue())` | Có, để tính đối số | Giá trị đã được tính, trả kết quả đó |
| `opt.orElseGet(() -> expensiveValue())` | Không | Gọi Supplier tạo giá trị T |
| `opt.orElseThrow(() -> new DomainException())` | Không | Tạo và ném exception |
| `opt.orElseThrow()` | Không có Supplier | Ném NoSuchElementException |

Ở mọi nhánh, **biểu thức bên ngoài body lambda** vẫn được đánh giá theo thứ tự Java. Nếu muốn trì hoãn truy cập database, đặt việc đó **trong Supplier**. Nếu đã gọi database trước rồi capture một giá trị, đó không còn là lazy fallback.

Mức tối ưu thực sự phụ thuộc chi phí tạo giá trị và tần suất rỗng. Nếu fallback chỉ là hằng số `"Guest"`, `orElse("Guest")` đơn giản và dễ hiểu. Nếu fallback cần I/O hoặc tính toán đắt, `orElseGet` hay `or` có thể tránh tác vụ không cần thiết. Không nên thay thế toàn bộ mã bằng lambda chỉ vì “functional” nếu nó làm luồng nghiệp vụ khó đọc hơn.

## 11. Bảo đảm và giới hạn khi dùng nhiều luồng

`Optional` là kiểu value-based; không dựa vào danh tính của object Optional để khóa đồng bộ, so sánh reference `==` hoặc quản lý cache. So sánh dữ liệu qua giá trị hoặc hợp đồng nghiệp vụ thay vì nhận dạng instance.

`Optional.or` không bảo đảm supplier có thể được gọi ở môi trường concurrent một cách an toàn nếu bản thân Supplier dùng mutable state. Việc tạo/đánh giá fallback diễn ra khi bạn gọi phương thức theo ngữ nghĩa thông thường, không tự chuyển sang thread khác. Nếu nhiều thread chia sẻ dữ liệu hoặc cache, đồng bộ phải được thiết kế ở nơi dữ liệu thay đổi.

Tránh ngộ nhận rằng thứ tự fallback giải quyết tất cả race condition: dữ liệu có thể thay đổi giữa các nguồn hoặc giữa lần tìm và hành động tiếp theo. Với thao tác đòi nguyên tử hoặc giao dịch, sử dụng API database/caching thích hợp thay vì chỉ dựa vào biểu thức Optional.

## 12. Những lỗi thường gặp

1. **Viết `or(() -> "backup")`:** Sai kiểu trả về; `or` cần Supplier trả `Optional<T>`, không phải `T`.
2. **Trả `null` từ Supplier của `or`:** Vi phạm hợp đồng; khi được gọi sẽ gây `NullPointerException`.
3. **Tin rằng `or` luôn gọi nguồn dự phòng:** Sai khi Optional đã có giá trị; Supplier không được gọi ở nhánh đó.
4. **Tính fallback trước lambda:** `Optional<T> backup = expensive(); opt.or(() -> backup)` đã thực thi `expensive()` sớm.
5. **Nhầm `orElseThrow()` với `orElseGet()`:** Một cái ném exception khi rỗng, một cái trả giá trị do Supplier tạo.
6. **Dùng `orElseThrow` khi thiếu dữ liệu là bình thường:** Exception nên diễn đạt lỗi thật sự; tránh dùng làm luồng điều khiển thường xuyên.
7. **Dùng `orElseThrow(() -> null)`:** Khi rỗng, nó gây NPE chứ không tạo một loại lỗi nghiệp vụ hữu ích.
8. **Không khai báo checked exception:** `orElseThrow(() -> new IOException(...))` có thể cần `throws IOException` hoặc `try/catch` ở caller.
9. **Dùng `map` khi mapper đã trả Optional:** Dễ tạo Optional lồng nhau; cân nhắc `flatMap`.
10. **Coi lỗi nguồn dữ liệu là không tìm thấy:** `or` không bắt lỗi; việc chuyển lỗi kỹ thuật thành Optional.empty() phải theo quy tắc riêng.
11. **Nhầm phương án xử lý dữ liệu thiếu:** Một chuỗi hiển thị có thể mặc định, nhưng một token bảo mật hoặc khóa giao dịch bắt buộc phải báo lỗi phù hợp.
12. **Đồng nhất Optional với khả năng cho null:** Optional rỗng khác với object Optional bằng `null`; API trả Optional nên không trả `null`.

## 13. Bài tập tự kiểm tra

**Bài 1.** Với `Optional.of("A").or(() -> Optional.of("B"))`, kết quả là gì? Supplier có được gọi không?

**Bài 2.** Với `Optional.<String>empty().or(Optional::empty)`, trạng thái sau cùng là gì? Tại sao không ném ngoại lệ?

**Bài 3.** Hãy viết pipeline thử `findLocal(id)`, `findCache(id)` rồi `findRemote(id)` chỉ khi những nguồn trước rỗng. Cuối pipeline, nếu vẫn không tìm thấy, ném `IllegalStateException` với thông điệp chứa `id`.

**Bài 4.** Phân biệt kết quả và chi phí thực thi của `opt.orElse(expensive())` với `opt.orElseGet(() -> expensive())` khi Optional đang có giá trị.

**Bài 5.** Viết phương thức nhận `Optional<String>` và buộc caller xử lý `IOException` nếu giá trị không tồn tại.

**Bài 6.** Vì sao `Optional.empty().or(() -> null)` không phải cách hợp lệ để “không có nguồn dự phòng”? Cách viết đúng để giữ Optional rỗng là gì?

**Bài 7.** Khi `Optional.of("ready").orElseThrow(() -> new IllegalStateException())`, exception supplier có tạo object exception không?

**Bài 8.** Một repository gọi database thất bại do timeout và trả Optional.empty(). Nếu phía sau `or` sẽ đọc một cache, cách thiết kế này có thể che giấu điều gì?

**Bài 9.** `Optional<User>` có method `getNickname()` trả `Optional<String>`. Hãy dùng `flatMap` rồi `or` để lấy nickname dự phòng, không tạo Optional lồng nhau.

**Bài 10.** Với `List<Optional<String>>` gồm 2 Optional có giá trị và một Optional rỗng, dùng `Optional::stream` để thu được `List<String>` chỉ chứa 2 chuỗi.

### Gợi ý đáp án

1. Trả Optional chứa `"A"`; Supplier không được gọi.
2. Trả Optional rỗng hợp lệ; Supplier đã trả một object `Optional.empty()`, không phải null.
3. `findLocal(id).or(() -> findCache(id)).or(() -> findRemote(id)).orElseThrow(() -> new IllegalStateException("Not found: " + id))`.
4. `orElse` đánh giá `expensive()` trước khi gọi; `orElseGet` không gọi Supplier khi đã có giá trị.
5. `static String require(Optional<String> x) throws IOException { return x.orElseThrow(() -> new IOException("missing")); }`; cần import `Optional` và `IOException` trong class chứa phương thức.
6. Vì `or` cần Optional khác; dùng `.or(Optional::empty)`.
7. Không; body Supplier không chạy khi giá trị tồn tại.
8. Che giấu lỗi kết nối/timeout và khiến cache fallback trông như kết quả hợp lệ của tìm kiếm bình thường.
9. `user.flatMap(User::getNickname).or(() -> findFallbackNickname())`, khi những phương thức đã được định nghĩa phù hợp.
10. `items.stream().flatMap(Optional::stream).toList()`.

## Kết luận

Khi `Optional` rỗng, hãy **lựa chọn cách xử lý theo hợp đồng nghiệp vụ**:

- Dùng **`or()`** để thử một nguồn khác nhưng tiếp tục biểu diễn kết quả bằng `Optional<T>`.
- Dùng **`orElseThrow()`** khi thiếu giá trị là lỗi và `NoSuchElementException` đã đủ rõ.
- Dùng **`orElseThrow(exceptionSupplier)`** khi cần ngoại lệ có ý nghĩa nghiệp vụ hoặc checked exception cụ thể.
- Dùng **`orElse`, `orElseGet`, `ifPresentOrElse` hoặc `stream`** khi thiếu giá trị là điều được phép và không cần ném lỗi.

Sự khác biệt then chốt nằm ở **kiểu giá trị dự phòng, thời điểm thực thi Supplier và ý nghĩa của trạng thái rỗng**. Hiểu đúng những điểm này giúp mã Java vừa dễ đọc, vừa tránh I/O thừa, exception sai tầng và các nhánh xử lý không phản ánh đúng yêu cầu ứng dụng.
