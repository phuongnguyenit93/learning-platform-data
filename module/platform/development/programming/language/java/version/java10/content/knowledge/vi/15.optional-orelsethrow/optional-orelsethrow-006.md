# Lựa chọn ngoại lệ mặc định hoặc ngoại lệ nghiệp vụ với `Optional.orElseThrow` (Java 10+)

## 1. Tại sao cần lựa chọn ngoại lệ?

`Optional<T>` biểu diễn một giá trị **có thể hiện diện hoặc vắng mặt**. Trong Java hiện đại, đây là kiểu hữu ích để một API tìm kiếm nói rõ rằng “không có kết quả” là một khả năng hợp lệ. Nhưng đến một điểm trong luồng xử lý, ứng dụng có thể **bắt buộc phải có giá trị** mới tiếp tục được. Khi ấy, `Optional.orElseThrow` giúp chuyển trạng thái rỗng thành một ngoại lệ.

Vấn đề cần quyết định không chỉ là **có ném ngoại lệ hay không**, mà là **ném loại ngoại lệ nào, ở tầng nào, với thông tin gì**. Có hai dạng chính:

```java
T value = optional.orElseThrow(); // Java 10+: ngoại lệ mặc định.

T value = optional.orElseThrow(
        () -> new SomeException("reason")); // Ngoại lệ do caller lựa chọn.
```

Đây là dạng chữ ký minh họa: `T`, `optional` và `SomeException` cần được khai báo phù hợp trong chương trình. Cả hai cách đều trả cùng **giá trị kiểu `T`** khi `Optional` có giá trị; khác biệt chỉ xảy ra khi `Optional` rỗng.

- **Không truyền tham số:** khi rỗng, ném `java.util.NoSuchElementException`. Dạng này được bổ sung trong **Java 10**.
- **Truyền `Supplier<? extends X>`:** khi rỗng, gọi supplier để lấy một đối tượng ngoại lệ `X extends Throwable` và ném chính ngoại lệ đó. Dạng này đã tồn tại từ **Java 8** và vẫn được sử dụng bình thường trong Java hiện đại.

Điểm quan trọng: `orElseThrow` **không thay đổi Optional gốc**, không bổ sung fallback và không tự biết ngữ nghĩa nghiệp vụ. Loại ngoại lệ được chọn là một phần **hợp đồng của API hoặc tầng xử lý sử dụng giá trị**.

### Mục tiêu bài học

Sau bài này, bạn có thể:

1. Phân biệt chính xác `orElseThrow()` và `orElseThrow(exceptionSupplier)`.
2. Chọn `NoSuchElementException` khi phù hợp và tạo exception riêng khi thiếu dữ liệu có ý nghĩa nghiệp vụ.
3. Hiểu checked và unchecked exception khi truyền supplier.
4. Giải thích tại sao supplier chỉ được đánh giá khi rỗng, tránh tạo ngoại lệ không cần thiết.
5. Đặt điểm ném lỗi ở boundary phù hợp: repository, service, API/controller hoặc xử lý dữ liệu nội bộ.
6. Không lạm dụng exception khi “không có giá trị” vốn là một nhánh bình thường.
7. Viết mã Java 10+ rõ ràng, kiểm thử được và không phụ thuộc vào chi tiết thông điệp ngoại lệ không được đặc tả.

Bài tập trung vào các API **vẫn được hỗ trợ hiện nay**, không dựa vào kỹ thuật đã lỗi thời hay legacy.

## 2. Hai overload và hợp đồng tại thời điểm biên dịch

Về ý nghĩa, `Optional<T>` cung cấp hai dạng:

```java
// Dạng Java 10+:
public T orElseThrow()

// Dạng tổng quát, có từ Java 8:
public <X extends Throwable> T orElseThrow(
        java.util.function.Supplier<? extends X> exceptionSupplier)
        throws X
```

Đây là chữ ký API minh họa, không phải hai phương thức để sao chép vào class của bạn.

| Trạng thái Optional | `orElseThrow()` | `orElseThrow(supplier)` |
| --- | --- | --- |
| Có giá trị | Trả chính giá trị `T` | Trả chính giá trị `T`; không gọi supplier |
| Rỗng | Ném `NoSuchElementException` | Gọi supplier và ném ngoại lệ được trả về |
| Ngoại lệ checked? | Không; `NoSuchElementException` là unchecked | Có thể checked hoặc unchecked, tùy loại `X` |
| Thông tin lỗi | Loại ngoại lệ mặc định, không mang context nghiệp vụ từ caller | Có thể truyền ID, mã lỗi, tên field, ngữ cảnh an toàn |
| Phù hợp | Điểm cần một giá trị và `NoSuchElementException` truyền tải đủ ý định | Boundary cần hợp đồng lỗi riêng, chẩn đoán rõ hoặc chính sách xử lý cụ thể |

Trong cả hai trường hợp, nếu `Optional` có giá trị, phương thức trả về **giá trị**, không trả về một `Optional<T>` mới.

Ngoại lệ mặc định là `java.util.NoSuchElementException`, một subclass của `RuntimeException`, nên không phải khai báo `throws NoSuchElementException` ở chữ ký. Dạng nhận supplier là generic: compiler có thể suy luận ra loại exception mà supplier tạo và áp dụng quy tắc **checked exception** thông thường.

## 3. Dùng ngoại lệ mặc định: `orElseThrow()`

Giả sử bạn đã có một `Optional<String>`:

```java
var present = java.util.Optional.of("READY");
String state = present.orElseThrow();

System.out.println(state); // READY
```

Khi có giá trị, không có ngoại lệ.

```java
var empty = java.util.Optional.<String>empty();

// empty.orElseThrow(); // Khi chạy sẽ ném NoSuchElementException.
```

Một cách xử lý minh họa:

```java
try {
    java.util.Optional.<String>empty().orElseThrow();
} catch (java.util.NoSuchElementException ex) {
    System.out.println("missing");
}
```

Điều này hữu ích khi **lời gọi đã mang ngữ nghĩa đòi hỏi phần tử tồn tại** và việc thiếu phần tử là lỗi không nên bị xử lý bằng fallback tùy tiện.

### Khi nào ngoại lệ mặc định đủ rõ?

Ví dụ: một bước xử lý nội bộ xác nhận đã có ít nhất một phần tử đáp ứng điều kiện và chuyển từ `Optional` sang giá trị bắt buộc:

```java
var firstPositive = java.util.stream.Stream.of(3, 5, 8)
        .filter(value -> value > 0)
        .findFirst()
        .orElseThrow();

System.out.println(firstPositive); // 3
```

Nếu stream trống hoặc không có phần tử phù hợp, việc thiếu giá trị có thể được biểu diễn bằng `NoSuchElementException`. Lựa chọn này hợp lý **nếu hợp đồng code cho phép đúng loại ngoại lệ đó**.

Tuy nhiên, một API công khai như `requireCustomer(42)` thường cần cung cấp ngữ nghĩa **“không tìm thấy khách hàng”** thay vì một ngoại lệ quá chung chung. Khi đó nên cân nhắc loại ngoại lệ nghiệp vụ.

### Không phụ thuộc chuỗi thông điệp mặc định

Trong ví dụ chạy trên một JDK cụ thể, `NoSuchElementException.getMessage()` có thể là `"No value present"`. Nhưng điều nên dùng để xác định hợp đồng là **loại ngoại lệ**; không xây dựng logic nghiệp vụ dựa vào một chuỗi thông điệp do JDK phát sinh. Muốn có mã lỗi hoặc thông điệp ổn định, hãy chọn một exception do ứng dụng kiểm soát.

## 4. Ngoại lệ nghiệp vụ: `orElseThrow(() -> new ...)`

Giả sử tầng lưu trữ trả về `Optional<Customer>` khi tìm khách hàng theo mã. Với API yêu cầu chắc chắn có khách hàng, service có thể chuyển kết quả rỗng thành ngoại lệ riêng:

```java
static Customer requireCustomer(long id) {
    return findCustomer(id)
            .orElseThrow(() -> new CustomerNotFoundException(id));
}
```

Đây là **đoạn minh họa cần class `Customer`, hàm `findCustomer` và `CustomerNotFoundException` tương ứng**; chương trình hoàn chỉnh ở mục 11.

Loại ngoại lệ riêng:

```java
static final class CustomerNotFoundException extends RuntimeException {
    final long customerId;

    CustomerNotFoundException(long customerId) {
        super("CUSTOMER_NOT_FOUND: id=" + customerId);
        this.customerId = customerId;
    }
}
```

Khi tìm được khách hàng:

- `orElseThrow` trả giá trị `Customer`.
- Không xây dựng `CustomerNotFoundException`.
- Không có công việc phụ thuộc vào supplier được thực thi.

Khi không tìm được:

- `Optional.empty()` khiến supplier chạy.
- Supplier tạo `CustomerNotFoundException(id)`.
- Exception được ném ra và có thể được bắt ở tầng quản lý lỗi phù hợp.

### Lợi ích của exception riêng

1. **Diễn đạt nguyên nhân**: `CustomerNotFoundException` rõ nghĩa hơn `NoSuchElementException` chung chung.
2. **Có dữ liệu xử lý**: có thể lưu mã khách hàng, mã lỗi có cấu trúc hoặc nguyên nhân (cause) khi thích hợp.
3. **Phân loại ở boundary**: REST/controller có thể được thiết kế để ánh xạ loại lỗi này thành HTTP 404; xử lý HTTP là công việc **của tầng HTTP**, không tự xảy ra chỉ vì ném exception Java.
4. **Test rõ ràng**: test kiểm tra **loại lỗi** và các thuộc tính phù hợp, không cần dựa vào thông điệp của JDK.
5. **Tách trách nhiệm**: repository có thể vẫn trả `Optional.empty()` theo hợp đồng truy vấn, còn service áp dụng quy tắc “bắt buộc phải tìm thấy”.

Ngoại lệ nghiệp vụ cần được đặt tên có ý nghĩa, tránh tạo quá nhiều class không cung cấp giá trị chẩn đoán hoặc xử lý.

## 5. Đặt quyết định ném ngoại lệ ở đúng tầng

Một thiết kế thông thường có hai cấp API:

```java
// Tầng truy vấn: không tìm thấy là một kết quả hợp lệ.
Optional<Customer> findCustomer(long id);

// Tầng nghiệp vụ: không tìm thấy ở đây là lỗi.
Customer requireCustomer(long id);
```

Ở tầng repository, `Optional.empty()` cho phép caller quyết định: hiển thị “chưa có dữ liệu”, dùng fallback, hoặc báo lỗi.

Ở tầng nghiệp vụ, `requireCustomer` bảo đảm trả `Customer` khi thành công; nếu thiếu thì ném `CustomerNotFoundException`. Tên phương thức và hợp đồng thông báo rõ ý định.

Ví dụ trong service:

```java
Customer customer = repository.findCustomer(id)
        .orElseThrow(() -> new CustomerNotFoundException(id));
```

Đoạn này giả định `repository` có phương thức `findCustomer` trả `Optional<Customer>`. Không cần ép repository phải ném ngoại lệ cho mọi truy vấn rỗng.

### Phân loại một số tình huống

| Tình huống | Lựa chọn thường phù hợp | Vì sao |
| --- | --- | --- |
| Dữ liệu không có là trường hợp bình thường | Tiếp tục dùng `Optional`, hoặc fallback hợp lệ | Không nên biến nhánh bình thường thành lỗi |
| Bước nội bộ yêu cầu ít nhất một phần tử, thiếu là vi phạm tiền đề | `orElseThrow()` | `NoSuchElementException` có thể đủ rõ |
| Thực thể được yêu cầu bắt buộc phải tồn tại theo nghiệp vụ | `orElseThrow(() -> new EntityNotFoundException(id))` | Có loại lỗi và context xác định |
| Không có cấu hình bắt buộc | Ngoại lệ cấu hình riêng hoặc `IllegalStateException` nếu đó là invariant thất bại | Phân biệt lỗi cấu hình với “not found” |
| Caller bắt buộc xử lý thiếu dữ liệu theo hợp đồng | Checked exception riêng | Compiler buộc khai báo hoặc xử lý |
| Cần một giá trị mặc định hợp lệ | `orElse` / `orElseGet` | Không có lý do để throw |
| Hàm chỉ là truy vấn tìm kiếm | Giữ `Optional<T>` | Cho caller lựa chọn chính sách |

**Không có quy tắc “luôn dùng exception riêng” hoặc “luôn dùng mặc định” cho mọi hệ thống.** Điều quan trọng là loại ngoại lệ phản ánh đúng **hợp đồng tại điểm chuyển từ Optional sang giá trị bắt buộc**.

## 6. Checked exception hay unchecked exception?

Overload nhận supplier cho phép tạo ngoại lệ kiểu `X extends Throwable`, kể cả **checked exception**.

### 6.1. Unchecked: lỗi nghiệp vụ có handler tập trung

```java
static Customer requireCustomer(long id) {
    return findCustomer(id)
            .orElseThrow(() -> new CustomerNotFoundException(id));
}
```

Vì `CustomerNotFoundException extends RuntimeException`, phương thức không buộc phải khai báo `throws CustomerNotFoundException`. Một API cũng có thể tài liệu hóa ngoại lệ này bằng Javadoc, đặc biệt nếu caller cần phân loại lỗi.

Unchecked exception phù hợp nếu ứng dụng đã có policy xử lý lỗi tại một boundary, hoặc nếu lỗi thiếu dữ liệu tại đây vi phạm hợp đồng của operation.

### 6.2. Checked: caller bắt buộc đối diện khả năng thiếu dữ liệu

Giả sử cấu hình bắt buộc phải có một key:

```java
static final class MissingSettingException extends Exception {
    MissingSettingException(String setting) {
        super("Missing setting: " + setting);
    }
}

static String requireSetting(
        java.util.Map<String, String> settings,
        String key) throws MissingSettingException {

    return java.util.Optional.ofNullable(settings.get(key))
            .orElseThrow(() -> new MissingSettingException(key));
}
```

Đoạn này gồm các thành viên của một class, không phải file Java độc lập.

`MissingSettingException` là checked exception vì kế thừa `Exception` mà không kế thừa `RuntimeException`. Tại call site, Java yêu cầu:

- **Bắt** ngoại lệ bằng `try/catch`; hoặc
- **Khai báo** `throws MissingSettingException` ở phương thức gọi.

Đây không phải lỗi của `Optional`, mà chính là quy tắc checked exceptions của Java áp dụng thông qua chữ ký generic `throws X` của `orElseThrow`.

Không được “chuyển sang unchecked để khỏi viết `throws`” một cách máy móc. Chọn checked hay unchecked theo hợp đồng API, khả năng phục hồi và chính sách xử lý lỗi của hệ thống.

### 6.3. Không có cơ chế tự bọc exception

Khi supplier tạo ra `MissingSettingException`, `orElseThrow` ném **chính instance exception ấy**, không tự chuyển nó thành `NoSuchElementException` hoặc `RuntimeException`. Nếu code cần giữ original cause, hãy tạo ngoại lệ phù hợp có constructor nhận cause và cung cấp cause một cách có chủ đích.

## 7. Supplier là lazy: chỉ tạo ngoại lệ khi Optional rỗng

Với overload có tham số:

```java
String result = optional.orElseThrow(
        () -> new CustomerNotFoundException(id));
```

Hàm lambda có vai trò **cung cấp ngoại lệ** chứ không chạy ngay lúc biểu thức được tạo. Nếu `optional` có giá trị, supplier **không được gọi**.

Ví dụ:

```java
var calls = new java.util.concurrent.atomic.AtomicInteger();

var value = java.util.Optional.of("cached")
        .orElseThrow(() -> {
            calls.incrementAndGet();
            return new IllegalStateException("missing");
        });

System.out.println(value);       // cached
System.out.println(calls.get()); // 0
```

Tại sao quan trọng?

- Không tạo exception và stack trace khi đường đi thành công.
- Không thực hiện truy vấn hoặc tính toán chỉ dùng để tạo thông điệp lỗi.
- Không phát sinh side effect nằm bên trong supplier nếu giá trị đã tồn tại.

Khi `Optional.empty()`, supplier được gọi để tạo exception:

```java
try {
    java.util.Optional.<String>empty().orElseThrow(
            () -> new IllegalStateException("required value missing"));
} catch (IllegalStateException ex) {
    System.out.println(ex.getMessage()); // required value missing
}
```

### Supplier phải trả một exception, không phải giá trị dự phòng

Cú pháp đúng:

```java
optional.orElseThrow(() -> new IllegalStateException("missing"));
```

Cú pháp sai:

```java
// optional.orElseThrow(new IllegalStateException("missing"));
// Sai kiểu tham số: phương thức yêu cầu Supplier chứ không nhận Exception trực tiếp.
```

Không viết mã cố tình có side effect lớn trong supplier chỉ để tận dụng laziness. Exception supplier nên đơn giản: dựng thông điệp, tạo loại exception đúng và trả về.

Một method reference tới constructor không tham số cũng hợp lệ:

```java
var value = java.util.Optional.of("ok")
        .orElseThrow(IllegalStateException::new);
```

Nhưng khi cần đưa `id` hoặc context vào thông điệp, lambda thường rõ ràng hơn:

```java
.orElseThrow(() -> new CustomerNotFoundException(id))
```

Dòng này là **phần đuôi của một expression**, không phải câu lệnh Java độc lập.

## 8. Những lựa chọn dễ nhầm: `orElse`, `orElseGet` và `orElseThrow`

Ba nhóm phương thức có hợp đồng khác nhau:

| Phương thức | Khi Optional có giá trị | Khi Optional rỗng | Tình huống |
| --- | --- | --- | --- |
| `orElse(T other)` | Trả giá trị trong Optional | Trả `other` | Có fallback sẵn, chấp nhận được |
| `orElseGet(Supplier<? extends T>)` | Trả giá trị trong Optional | Gọi supplier để **tạo giá trị T** | Fallback cần tính toán khi thiếu |
| `orElseThrow()` | Trả giá trị trong Optional | Ném `NoSuchElementException` | Thiếu giá trị là lỗi chung |
| `orElseThrow(Supplier<? extends X>)` | Trả giá trị trong Optional | Gọi supplier để **tạo exception X**, rồi ném | Cần lỗi nghiệp vụ rõ ràng |

Ví dụ giá trị fallback hợp lệ:

```java
String displayName = optionalName.orElse("Anonymous");
String generatedName = optionalName.orElseGet(
        () -> generateDisplayName());
```

Đoạn này giả định có `optionalName` kiểu `Optional<String>` và hàm `generateDisplayName()`.

Nếu `optionalName` rỗng **không phải lỗi**, sử dụng `orElseThrow` có thể làm luồng xử lý phức tạp không cần thiết.

### Khác biệt eager vs lazy trong fallback

```java
var name = optionalName.orElse(expensiveDefault());
```

Với `orElse`, biểu thức tham số `expensiveDefault()` được Java đánh giá khi gọi phương thức, **ngay cả khi Optional có giá trị**. Với `orElseGet(() -> expensiveDefault())`, fallback chỉ được tính khi rỗng.

`orElseThrow(() -> new SomeException())` cũng lazy nhưng supplier của nó phải trả **ngoại lệ**, không phải giá trị fallback. Không thay `orElseGet` bằng `orElseThrow` khi thiếu giá trị thực sự có thể được phục hồi.

## 9. Chuỗi xử lý Optional: lỗi thuộc về điều kiện rỗng cuối cùng

Nhiều đoạn xử lý dùng `map`, `filter` hoặc `flatMap` trước khi gọi `orElseThrow`:

```java
String normalized = findCustomer(id)
        .map(customer -> customer.name)
        .filter(name -> !name.isBlank())
        .orElseThrow(() -> new IllegalStateException(
                "Customer name is missing or blank"));
```

Đây là code minh họa sử dụng `Customer.name` và `findCustomer` từ chương trình hoàn chỉnh.

Cần chú ý: sau pipeline, `Optional.empty()` **có thể đến từ nhiều nguyên nhân**:

1. `findCustomer(id)` không tìm thấy khách hàng.
2. Tên khách hàng rỗng hoặc chỉ chứa khoảng trắng, nên `filter` loại phần tử.
3. Một `map` trả `null` có thể biến kết quả thành Optional rỗng theo quy tắc `Optional.map`.

Khi các nguyên nhân cần được phân biệt bằng mã lỗi khác nhau, **không gom mọi nguyên nhân vào một lần `orElseThrow` cuối**.

Cách tách rõ:

```java
Customer customer = findCustomer(id)
        .orElseThrow(() -> new CustomerNotFoundException(id));

String name = java.util.Optional.ofNullable(customer.name)
        .filter(text -> !text.isBlank())
        .orElseThrow(() -> new IllegalStateException(
                "Customer name is missing or blank"));
```

Khi đó thiếu customer được phân loại khác với lỗi dữ liệu customer không hợp lệ. Thời điểm đặt `orElseThrow` quyết định ý nghĩa của ngoại lệ được ném.

### Optional rỗng không thể cho biết nguyên nhân

`Optional.empty()` chỉ nói **không có giá trị**, không mang sẵn mã lý do. Nếu API cần phân biệt “không tồn tại”, “không được phép”, “tạm không khả dụng” và “hệ thống lỗi”, đừng nhồi tất cả vào cùng `Optional.empty()` rồi cố suy luận tại caller. Hãy thiết kế hợp đồng khác (loại kết quả có trạng thái, ngoại lệ có phân loại, hoặc các operation riêng) cho những tình huống cần biết nguyên nhân.

## 10. Chọn exception theo hợp đồng của API, không theo HTTP hay framework tự động

Một số mô hình hợp lý:

**Truy vấn không bắt buộc:**

```java
Optional<Customer> findCustomer(long id);
```

Caller có thể dùng `ifPresent`, `map`, fallback hoặc chủ động throw.

**Lấy dữ liệu bắt buộc:**

```java
Customer requireCustomer(long id);
```

Chữ ký này có thể công bố rằng trường hợp không tìm thấy sẽ ném `CustomerNotFoundException`. Tại tầng service, dùng `orElseThrow(() -> ...)` để thực thi hợp đồng.

**Truy vấn với lý do lỗi nghiệp vụ riêng:**

```java
Customer requireActiveCustomer(long id);
```

Nếu cần phân biệt *không tồn tại* với *đã bị vô hiệu hóa*, nên kiểm tra ở các bước tương ứng và ném loại exception phản ánh từng lý do. Không dùng cùng `NoSuchElementException` cho mọi nguyên nhân nếu caller phải xử lý khác nhau.

**REST controller:** một exception nghiệp vụ có thể được tầng HTTP **ánh xạ** sang 404/409/422 tùy thiết kế. Bản thân `orElseThrow` không có tri thức HTTP và **không tự trả status**. Mã lỗi HTTP, logging và thông báo dành cho client thuộc về cơ chế xử lý ở boundary của ứng dụng.

**Tích hợp nội bộ:** khi không có giá trị là một lỗi cấu hình, `IllegalStateException` hoặc ngoại lệ cấu hình chuyên biệt có thể đúng hơn `CustomerNotFoundException`.

Lỗi API nên mang đủ context giúp chẩn đoán, nhưng **không tự động đưa dữ liệu nhạy cảm, thông tin bí mật, token hoặc toàn bộ object vào exception message**. Chọn ID/mã đã được phép ghi log và tách message nội bộ khỏi thông điệp trả cho người dùng cuối khi cần.

## 11. Chương trình Java 10+ đầy đủ, đã biên dịch và chạy

Tạo tệp **`OptionalOrElseThrowDemo.java`**:

```java
import java.util.Map;
import java.util.NoSuchElementException;
import java.util.Optional;
import java.util.concurrent.atomic.AtomicInteger;

public final class OptionalOrElseThrowDemo {
    static final class Customer {
        final long id;
        final String name;

        Customer(long id, String name) {
            this.id = id;
            this.name = name;
        }
    }

    static final class CustomerNotFoundException extends RuntimeException {
        final long customerId;

        CustomerNotFoundException(long customerId) {
            super("CUSTOMER_NOT_FOUND: id=" + customerId);
            this.customerId = customerId;
        }
    }

    static final class MissingSettingException extends Exception {
        MissingSettingException(String setting) {
            super("Missing setting: " + setting);
        }
    }

    private static final Map<Long, Customer> CUSTOMERS =
            Map.of(1L, new Customer(1L, "Ada"));

    static Optional<Customer> findCustomer(long id) {
        return Optional.ofNullable(CUSTOMERS.get(id));
    }

    static Customer requireCustomer(long id) {
        return findCustomer(id)
                .orElseThrow(() -> new CustomerNotFoundException(id));
    }

    static String requireSetting(Map<String, String> settings, String key)
            throws MissingSettingException {
        return Optional.ofNullable(settings.get(key))
                .orElseThrow(() -> new MissingSettingException(key));
    }

    public static void main(String[] args) throws MissingSettingException {
        System.out.println("default present=" +
                Optional.of("ready").orElseThrow());

        try {
            Optional.<String>empty().orElseThrow();
        } catch (NoSuchElementException ex) {
            System.out.println("default missing=" +
                    ex.getClass().getSimpleName() + ": " + ex.getMessage());
        }

        System.out.println("customer=" + requireCustomer(1L).name);

        try {
            requireCustomer(9L);
        } catch (CustomerNotFoundException ex) {
            System.out.println("domain missing=" + ex.getMessage());
        }

        var supplierCalls = new AtomicInteger();
        var existing = Optional.of("cached").orElseThrow(() -> {
            supplierCalls.incrementAndGet();
            return new IllegalStateException("no cache");
        });
        System.out.println("supplier after present=" +
                supplierCalls.get() + ", value=" + existing);

        try {
            Optional.<String>empty().orElseThrow(() -> {
                supplierCalls.incrementAndGet();
                return new IllegalStateException("no cache");
            });
        } catch (IllegalStateException ex) {
            System.out.println("supplier after empty=" +
                    supplierCalls.get() + ", exception=" + ex.getMessage());
        }

        System.out.println("setting=" +
                requireSetting(Map.of("mode", "safe"), "mode"));

        try {
            requireSetting(Map.of(), "mode");
        } catch (MissingSettingException ex) {
            System.out.println("checked missing=" + ex.getMessage());
        }

        try {
            Optional.<String>empty().orElseThrow(() -> null);
        } catch (NullPointerException ex) {
            System.out.println("null exception=" +
                    ex.getClass().getSimpleName());
        }
    }
}
```

Biên dịch bằng một JDK có hỗ trợ `--release 10` rồi chạy:

```bash
javac --release 10 OptionalOrElseThrowDemo.java
java OptionalOrElseThrowDemo
```

**Stdout chính xác trong lần kiểm chứng:**

```text
default present=ready
default missing=NoSuchElementException: No value present
customer=Ada
domain missing=CUSTOMER_NOT_FOUND: id=9
supplier after present=0, value=cached
supplier after empty=1, exception=no cache
setting=safe
checked missing=Missing setting: mode
null exception=NullPointerException
```

Cách đọc kết quả:

1. `default present=ready`: `orElseThrow()` trả giá trị có sẵn, không ném lỗi.
2. `default missing=NoSuchElementException: No value present`: Optional rỗng gây ngoại lệ mặc định. Chuỗi thông điệp được ghi từ lần chạy; trong thiết kế API, dựa vào **loại exception**, không coi message JDK là hợp đồng nghiệp vụ.
3. `customer=Ada`: tìm thấy khách hàng, trả object bình thường.
4. `domain missing=CUSTOMER_NOT_FOUND: id=9`: không tìm thấy thì ném ngoại lệ nghiệp vụ riêng với ID của yêu cầu.
5. `supplier after present=0`: supplier không chạy khi có giá trị. `supplier after empty=1`: supplier chạy đúng khi rỗng rồi tạo `IllegalStateException`.
6. `setting=safe` và `checked missing=...`: phương thức có checked exception xử lý thành công hoặc ném ngoại lệ đúng loại khi thiếu cấu hình.
7. `null exception=NullPointerException`: supplier trả `null` không phải một cách hợp lệ để biểu diễn “không có ngoại lệ”. Khi Optional rỗng, không có exception để ném nên Java ném `NullPointerException`. Đây là **trường hợp cố ý minh họa lỗi**, không phải mẫu thiết kế nên dùng.

Toàn bộ chương trình chỉ dùng Java SE và các cấu trúc có thể biên dịch dưới mức ngôn ngữ **Java 10**, phù hợp module, đồng thời vẫn chạy trên JDK hiện hành.

## 12. Trường hợp biên và các giả định sai

### 12.1. Supplier trả `null`

```java
var present = Optional.of("value");
var result = present.orElseThrow(() -> null); // Trả "value".

// Optional.<String>empty().orElseThrow(() -> null);
// Khi rỗng: NullPointerException.
```

Với Optional có giá trị, supplier không được gọi nên nó không tạo ra exception. Với Optional rỗng, supplier trả `null` sẽ gây `NullPointerException`. Một supplier trả null hoặc chính đối tượng supplier là null không phải cách cấu hình lỗi hữu ích. Trong ứng dụng, hãy bảo đảm supplier thực sự cung cấp một exception.

### 12.2. Viết sai hình thức tham số

```java
// SAI: orElseThrow không nhận Exception instance trực tiếp.
// optional.orElseThrow(new IllegalStateException("missing"));

// ĐÚNG: truyền Supplier tạo ra Exception.
optional.orElseThrow(() -> new IllegalStateException("missing"));
```

Đoạn minh họa yêu cầu biến `optional` có kiểu `Optional<T>` hợp lệ. Lỗi khác là tạo ra **giá trị fallback** thay vì exception:

```java
// SAI: Supplier<String> không phải Supplier<? extends Throwable>.
// optional.orElseThrow(() -> "fallback");
```

`orElseThrow` yêu cầu supplier tạo một loại `Throwable` thích hợp.

### 12.3. Checked exception nhưng quên `throws`

```java
static String requireName(Optional<String> name)
        throws java.io.IOException {
    return name.orElseThrow(
            () -> new java.io.IOException("Name unavailable"));
}
```

Nếu bỏ `throws IOException` khỏi chữ ký và không xử lý checked exception theo cách hợp lệ, compiler báo lỗi. `orElseThrow` không biến checked exception thành unchecked. Đây là yêu cầu của hệ kiểu Java, không phải lỗi runtime.

### 12.4. Xây dựng exception không liên quan tới nguyên nhân

Một lời gọi như:

```java
findCustomer(id).orElseThrow(
        () -> new IllegalArgumentException("bad request"));
```

có thể làm mất ý nghĩa: không tìm thấy bản ghi không nhất thiết đồng nghĩa request có cú pháp/đối số sai. Chọn `CustomerNotFoundException(id)` hoặc một loại lỗi phản ánh đúng hợp đồng nghiệp vụ.

Tương tự, đừng dùng `NoSuchElementException` làm đại diện duy nhất cho lỗi truy cập bị từ chối, lỗi mạng, lỗi phân quyền hoặc lỗi validate dữ liệu nếu caller cần phân biệt và xử lý các trường hợp đó.

### 12.5. Exception quá nhiều thông tin hoặc bị rò rỉ

Không đưa cả dữ liệu nhạy cảm hoặc thông tin bảo mật vào message để “dễ debug”. Khi cần chẩn đoán, dùng mã lỗi ổn định, correlation ID và logging có kiểm soát theo chính sách hệ thống. Một exception domain có thể mang field cấu trúc để handler quyết định thông điệp được phép gửi ra ngoài.

### 12.6. Lấy `Optional.empty()` làm tín hiệu cho mọi lỗi

`Optional.empty()` chỉ mô tả **không có kết quả**, không phân biệt tại sao. Không nên bắt mọi exception từ I/O/database rồi chuyển thành `Optional.empty()`, sau đó để `orElseThrow()` báo `NoSuchElementException`; cách này đánh mất nguyên nhân thật và gây khó vận hành. Lỗi nguồn dữ liệu nên được giữ dưới dạng lỗi thích hợp; “không tồn tại” mới là một trường hợp Optional rỗng tự nhiên.

### 12.7. Dùng `orElseThrow` khi tồn tại fallback hợp lệ

Nếu sản phẩm cho phép ẩn danh, cấu hình mặc định hoặc xử lý “không tìm thấy” như nhánh bình thường, việc ném exception chỉ tạo thêm control flow không cần thiết. Dùng `Optional` ở call site, `orElse` hoặc `orElseGet` tùy yêu cầu.

### 12.8. Dùng `orElseThrow()` rồi bắt exception ngay để tiếp tục như bình thường

```java
// Mã cần cân nhắc lại nếu "không có" là tình huống thường xuyên:
try {
    return maybe.orElseThrow();
} catch (NoSuchElementException ex) {
    return defaultValue;
}
```

Đây là mã minh họa nằm trong thân một phương thức có `maybe` và `defaultValue`. Nếu thiếu dữ liệu là chuyện bình thường, viết `return maybe.orElse(defaultValue);` hoặc `return maybe.orElseGet(...);` thường trực tiếp hơn, tránh dùng exception như nhánh rẽ nghiệp vụ thông thường.

## 13. Chọn điểm throw sao cho lỗi nhất quán

### 13.1. Service sở hữu ý nghĩa “bắt buộc”

Ví dụ:

```java
Customer requireCustomer(long id) {
    return repository.findCustomer(id)
            .orElseThrow(() -> new CustomerNotFoundException(id));
}
```

Repository giữ hợp đồng truy vấn; service chịu trách nhiệm bắt buộc tồn tại. Exception này là phần hợp đồng của `requireCustomer`.

### 13.2. Không throw quá sớm khi caller còn có thể xử lý thiếu dữ liệu

Ví dụ một màn hình có thể hiển thị lời nhắc thay vì lỗi:

```java
String label = repository.findCustomer(id)
        .map(customer -> customer.name)
        .orElse("Customer not found");
```

Trong tình huống đó, throw ở repository sẽ khiến tầng UI phải bắt ngoại lệ chỉ để hiển thị nhánh bình thường. Trả `Optional` là lựa chọn sạch hơn.

### 13.3. Không throw quá muộn khiến mất nguyên nhân

Nếu một pipeline loại phần tử vì không hợp lệ nhưng chỉ ném `NoSuchElementException` ở cuối, caller không biết lỗi nằm ở “không tồn tại” hay “không thỏa điều kiện”. Đặt `orElseThrow` ở từng boundary ý nghĩa khi cần phân loại riêng.

### 13.4. Tài liệu hóa hợp đồng

Trong JavaDoc của API bắt buộc:

```java
/**
 * Returns a required customer.
 *
 * @throws CustomerNotFoundException if no customer exists for id
 */
static Customer requireCustomer(long id) {
    return findCustomer(id)
            .orElseThrow(() -> new CustomerNotFoundException(id));
}
```

Đây là đoạn thành viên trong class ví dụ, không phải code chạy độc lập. Javadoc làm rõ loại lỗi caller cần chờ đợi, ngay cả khi ngoại lệ là unchecked và chữ ký không bắt buộc phải ghi `throws`.

## 14. Kiểm thử đúng các nhánh hành vi

Các bài test có giá trị nhất không chỉ xác minh câu lệnh biên dịch, mà xác minh các **nhánh** của hợp đồng.

| Kiểm thử | Kỳ vọng |
| --- | --- |
| `Optional.of(value).orElseThrow()` | Trả đúng value |
| `Optional.empty().orElseThrow()` | Ném `NoSuchElementException` |
| `Optional.of(value).orElseThrow(supplier)` | Trả value và **không gọi supplier** |
| `Optional.empty().orElseThrow(supplier)` | Gọi supplier và ném đúng loại exception |
| Service `requireCustomer(foundId)` | Trả đúng customer |
| Service `requireCustomer(missingId)` | Ném `CustomerNotFoundException` có ID phù hợp |
| Checked exception `requireSetting(...)` thiếu key | Ném `MissingSettingException`, caller phải catch/declare |
| Supplier trả null khi Optional rỗng | `NullPointerException`; đây là lỗi của supplier |

Nếu sử dụng framework test, kiểm tra loại exception và các trường cấu trúc thay vì so sánh tùy tiện chuỗi thông điệp của JDK. Với exception nghiệp vụ do bạn thiết kế, có thể test mã lỗi, ID hoặc thuộc tính nghiệp vụ cụ thể.

Thử thêm case null đầu vào khi tạo Optional:

```java
String maybeNull = null;
var optional = java.util.Optional.ofNullable(maybeNull);

System.out.println(optional.isEmpty()); // true (Java 11+)
```

Đoạn trên minh họa `isEmpty()` được bổ sung trong **Java 11**. Trong một dự án dùng chính xác Java 10, có thể dùng `!optional.isPresent()` hoặc gọi `orElseThrow` để kiểm tra tình huống rỗng; điều cốt lõi là dùng `Optional.ofNullable` nếu nguồn có thể null. `Optional.of(null)` tự ném `NullPointerException` ngay khi tạo Optional, trước khi có thể gọi `orElseThrow`.

**Không hiểu nhầm:** `Optional.orElseThrow` chỉ được gọi trên một đối tượng Optional có thật. Nếu biến Optional tự nó là `null`, cố gọi phương thức sẽ gây `NullPointerException`, không phải `NoSuchElementException` hay ngoại lệ do supplier cung cấp.

## 15. Checklist code review trước khi dùng `orElseThrow`

- [ ] **Thiếu giá trị tại đây có thật sự là lỗi?** Nếu không, giữ `Optional` hoặc dùng fallback.
- [ ] **Loại lỗi mặc định `NoSuchElementException` có đủ rõ với caller?** Nếu không, tạo exception nghiệp vụ.
- [ ] **Exception được ném ở đúng tầng?** Repository có thể trả `Optional.empty()`; service/boundary quyết định hợp đồng bắt buộc.
- [ ] **Nguyên nhân rỗng có một nghĩa hay nhiều nghĩa?** Nếu nhiều nguyên nhân cần phân loại khác nhau, tách pipeline hoặc dùng mô hình kết quả phù hợp.
- [ ] **Supplier trả exception không-null?** Không đưa trực tiếp exception instance hoặc fallback value vào overload yêu cầu Supplier.
- [ ] **Có checked exception không?** Đã `catch` hoặc khai báo `throws` đúng loại chưa?
- [ ] **Exception có context an toàn và đủ dùng?** ID/mã lỗi được phép log; không đưa thông tin bí mật vào message.
- [ ] **Có phụ thuộc message mặc định của JDK không?** Test nên dựa loại exception, không dựa chuỗi có thể thay đổi.
- [ ] **Supplier chỉ chứa công việc tạo lỗi?** Không dựa vào side effect của supplier ở nhánh có giá trị.
- [ ] **Có dùng `orElse` hay `orElseGet` sẽ tốt hơn không?** Đặc biệt khi thiếu dữ liệu là trạng thái bình thường.
- [ ] **API lỗi có được tài liệu hóa?** Caller biết khi nào sẽ gặp exception cụ thể.
- [ ] **Đã kiểm thử cả present và empty?** Bao gồm loại exception, checked/unchecked và tính lazy.

## 16. Câu hỏi tự kiểm tra có đáp án

**Câu 1.** `Optional.empty().orElseThrow()` ném loại ngoại lệ nào?

**Đáp án:** `NoSuchElementException`, một unchecked exception thuộc `java.util`. Dạng không tham số có từ Java 10.

**Câu 2.** Với `Optional.of("A").orElseThrow(() -> new IllegalStateException("missing"))`, exception có được tạo không?

**Đáp án:** Không. Optional có giá trị nên `orElseThrow` trả `"A"` mà không gọi supplier.

**Câu 3.** Vì sao cần `() -> new CustomerNotFoundException(id)` thay vì truyền trực tiếp `new CustomerNotFoundException(id)`?

**Đáp án:** Overload nhận `Supplier<? extends X>`. Lambda cung cấp exception **khi thiếu**, đúng chữ ký và tránh tạo đối tượng ngoại lệ ở nhánh có giá trị.

**Câu 4.** Khi một API tìm kiếm cho phép “không tìm thấy”, nên trả `Optional.empty()` hay luôn ném exception?

**Đáp án:** Thường nên trả `Optional.empty()` theo hợp đồng truy vấn. Caller/service có thể lựa chọn fallback hoặc `orElseThrow` ở điểm giá trị trở thành bắt buộc.

**Câu 5.** Cần báo “không tìm thấy khách hàng có mã 9” theo hợp đồng nghiệp vụ. Hai cách `orElseThrow()` và `orElseThrow(() -> new CustomerNotFoundException(9))` khác nhau thế nào?

**Đáp án:** Dạng mặc định ném `NoSuchElementException` không mang ngữ nghĩa domain cụ thể. Dạng thứ hai ném `CustomerNotFoundException` mang thông tin ID và có thể được tầng xử lý lỗi phân loại rõ hơn.

**Câu 6.** Nếu supplier tạo `IOException`, có cần `throws IOException` ở phương thức không?

**Đáp án:** Có, hoặc phải xử lý checked exception bằng `try/catch`. Overload generic có `throws X` và Java áp dụng kiểm tra checked exception theo kiểu `X`.

**Câu 7.** `orElseThrow(() -> null)` hoạt động thế nào?

**Đáp án:** Nếu Optional có giá trị, supplier không được gọi nên trả giá trị như bình thường. Nếu rỗng, supplier trả `null` gây `NullPointerException`; đây là mã sai cần tránh.

**Câu 8.** `orElseThrow` có tự biến `CustomerNotFoundException` thành HTTP 404 không?

**Đáp án:** Không. HTTP status cần được ánh xạ ở tầng controller/exception handler theo chính sách API; Java Optional không gắn với HTTP.

**Câu 9.** Một pipeline `findCustomer(id).filter(c -> c.active).orElseThrow(...)` không có giá trị. Có thể khẳng định customer không tồn tại không?

**Đáp án:** Không. Có thể không tìm thấy customer, hoặc customer có nhưng không qua `filter`. Nếu cần lỗi “không tìm thấy” và “không hoạt động” riêng, tách bước và tạo exception ở từng điểm.

**Câu 10.** `orElse("Anonymous")` và `orElseThrow()` có vai trò tương đương không?

**Đáp án:** Không. `orElse` cung cấp giá trị thay thế khi rỗng; `orElseThrow` coi việc rỗng là lỗi. Chọn dựa trên hợp đồng nghiệp vụ.

**Câu 11.** Có nên so sánh exception message `"No value present"` để xác định lỗi trong code sản phẩm không?

**Đáp án:** Không. Nên dùng loại exception hoặc mã lỗi do ứng dụng kiểm soát, tránh phụ thuộc vào text mặc định của JDK.

**Câu 12.** Một Optional rỗng có thể mang nhiều nguyên nhân lỗi khác nhau không?

**Đáp án:** Không. `Optional.empty()` chỉ biểu đạt sự vắng mặt. Nếu nhiều nguyên nhân cần phân loại, dùng thiết kế trả kết quả/ngoại lệ phù hợp hoặc phân tách điểm kiểm tra.

## 17. Tài liệu tham khảo chính thức, vẫn có hiệu lực

- [Java SE — `Optional.orElseThrow()` và `orElseThrow(Supplier)`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Optional.html): hợp đồng hai overload, `NoSuchElementException` và supplier exception.
- [Java SE — `NoSuchElementException`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/NoSuchElementException.html): loại unchecked exception của Java Collections.
- [Java SE — `Supplier<T>`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/function/Supplier.html): functional interface được dùng để tạo ngoại lệ khi cần.
- [Java SE — `RuntimeException`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/RuntimeException.html): nền tảng của unchecked business exception.
- [Java Language Specification — Chapter 11, Exceptions](https://docs.oracle.com/javase/specs/jls/se25/html/jls-11.html): hệ thống checked/unchecked exceptions và quy tắc xử lý/khai báo.
- [Java SE — `Optional.orElse` và `orElseGet`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Optional.html): phân biệt fallback với ném ngoại lệ.

**Kết luận:** `orElseThrow()` là cách rõ ràng để nói “giá trị phải tồn tại, và ngoại lệ mặc định là đủ”. `orElseThrow(() -> new DomainException(context))` là cách nói “giá trị phải tồn tại **theo một hợp đồng nghiệp vụ cụ thể**”. Hãy chọn theo ngữ nghĩa của API, điểm xử lý và yêu cầu của caller — không phải theo độ ngắn của cú pháp.
