# `NoSuchElementException` khi `Optional` rỗng: hiểu đúng `orElseThrow()` (Java 10+)

## 1. Bài toán: lấy giá trị từ `Optional` khi có thể không tồn tại

`java.util.Optional<T>` là một container mô tả **có hoặc không có một giá trị khác `null`**. Ví dụ phương thức tìm kiếm có thể trả về một kết quả hoặc thông báo gián tiếp rằng không tìm thấy:

```java
static java.util.Optional<String> findUser(String id) {
    return "42".equals(id)
            ? java.util.Optional.of("Lan")
            : java.util.Optional.empty();
}
```

Đây là đoạn phương thức minh họa cần đặt trong lớp. Nếu gọi `findUser("42")`, kết quả chứa chuỗi `"Lan"`; nếu gọi `findUser("0")`, kết quả là **`Optional.empty()`**.

Từ **Java 10**, `Optional` có overload **không tham số**:

```java
T orElseThrow()
```

Phương thức này thực hiện hai hành vi rõ ràng:

1. Nếu `Optional` có giá trị, **trả về giá trị đó**.
2. Nếu `Optional` rỗng, **ném `java.util.NoSuchElementException`**.

Đặc điểm này **vẫn có hiệu lực trong Java hiện hành**; `orElseThrow()` không bị loại bỏ và không phải preview API. Nó là một lựa chọn phù hợp khi **không có giá trị là lỗi và luồng xử lý phải dừng**.

Ví dụ đơn giản:

```java
var present = java.util.Optional.of("Java");
var empty = java.util.Optional.<String>empty();

System.out.println(present.orElseThrow()); // Java
// empty.orElseThrow(); // Ném java.util.NoSuchElementException.
```

**Đừng hiểu “or else” là “trả về mặc định” trong tên `orElseThrow`:** chữ `Throw` nghĩa là **ném ngoại lệ** khi không có giá trị. Nếu muốn giá trị dự phòng, dùng `orElse` hoặc `orElseGet` theo hợp đồng phù hợp.

## 2. Hợp đồng API chính xác và kiểu ngoại lệ

Trong `java.util.Optional<T>`, chữ ký đầy đủ của overload Java 10 là:

```java
public T orElseThrow()
```

| Trạng thái của Optional | Lời gọi | Kết quả |
| --- | --- | --- |
| `Optional.of("A")` | `orElseThrow()` | Trả về `String` `"A"` |
| `Optional.of(10)` | `orElseThrow()` | Trả về `Integer` `10` |
| `Optional.empty()` | `orElseThrow()` | Ném `NoSuchElementException` |
| `Optional.ofNullable(null)` | `orElseThrow()` | Ném `NoSuchElementException` |
| `Optional.ofNullable("A")` | `orElseThrow()` | Trả về `"A"` |

### 2.1. Ngoại lệ đến từ đâu?

`NoSuchElementException` là một lớp thuộc **`java.util`** và kế thừa `RuntimeException`. Đó là một **unchecked exception**:

- Không bắt buộc khai báo `throws NoSuchElementException` trong chữ ký phương thức.
- Không bắt buộc `catch` để chương trình biên dịch.
- Nếu không có đoạn code bắt ngoại lệ, ngoại lệ sẽ lan lên caller và có thể kết thúc luồng thực thi hiện tại.
- Nó **không phải** `NullPointerException`: `Optional.empty()` là một **Optional hợp lệ nhưng không có giá trị**. Nguyên nhân thiếu giá trị khác với việc gọi phương thức trên một biến reference đang bằng `null`.

Ví dụ:

```java
try {
    java.util.Optional.<String>empty().orElseThrow();
} catch (java.util.NoSuchElementException ex) {
    System.out.println(ex.getClass().getSimpleName());
}
```

Stdout:

```text
NoSuchElementException
```

**Không phụ thuộc vào nội dung `ex.getMessage()` mặc định.** API bảo đảm **kiểu ngoại lệ**, nhưng ứng dụng không nên viết điều kiện nghiệp vụ hoặc bài kiểm thử phụ thuộc một câu thông báo cụ thể mà một bản triển khai JDK đang sử dụng.

### 2.2. Nó không tự phát sinh `null`

`Optional.empty().orElseThrow()` **không** trả về `null`. Nó ném ngoại lệ trước khi trả kết quả. Vì vậy:

```java
// Cách hiểu sai:
// String name = Optional.<String>empty().orElseThrow();
// name == null? Không đến được bước kiểm tra này vì đã ném ngoại lệ.
```

Nếu phương thức nào đó trả về một biến `Optional` **bản thân đang là `null`**, thì gọi `optional.orElseThrow()` gây `NullPointerException` do dereference null. Đây là lỗi hợp đồng của code trả về `null` thay vì một `Optional` hợp lệ, **không** phải quy tắc của Optional rỗng.

Tài liệu API hiện hành khuyến cáo reference có kiểu `Optional` không nên là `null`; khi không có kết quả, hãy trả `Optional.empty()`.

## 3. Vì sao có `Optional` rỗng?

`Optional.empty()` là trạng thái bình thường của API và có thể xuất hiện từ nhiều đường đi khác nhau.

### 3.1. Tạo trực tiếp bằng `Optional.empty()`

```java
var missing = java.util.Optional.<String>empty();
System.out.println(missing.isPresent()); // false
// missing.orElseThrow();                 // NoSuchElementException
```

Type witness `<String>` chỉ định loại giá trị mà Optional **nếu có** sẽ chứa. Dù không có giá trị, generic type vẫn được xác định lúc biên dịch; không có nghĩa Optional trở thành một `String` rỗng.

### 3.2. Tạo từ reference có thể null

```java
String raw = null;
var wrapped = java.util.Optional.ofNullable(raw);

System.out.println(wrapped.isPresent()); // false
// wrapped.orElseThrow();                 // NoSuchElementException
```

`Optional.ofNullable(raw)` trả về Optional rỗng khi `raw == null`. So sánh:

```java
// Optional.of(null) ném NullPointerException NGAY KHI TẠO,
// không tạo được Optional rỗng để orElseThrow xử lý.
```

**Phân biệt thứ tự phát sinh lỗi:** `Optional.of(null)` ném `NullPointerException` ở bước tạo; `Optional.ofNullable(null).orElseThrow()` ném `NoSuchElementException` ở bước yêu cầu lấy giá trị.

### 3.3. Không có kết quả sau khi tìm kiếm trên Stream

```java
var first = java.util.stream.Stream.<String>empty().findFirst();
// first có kiểu Optional<String> và không có giá trị.
// first.orElseThrow(); // NoSuchElementException
```

Một số thao tác khác như `findAny()`, `max()`, `min()`, `reduce(...)` dạng trả Optional cũng có thể không tìm được phần tử/kết quả phù hợp. Nếu pipeline trống ở thời điểm cần lấy phần tử, `orElseThrow()` sẽ ném ngoại lệ vì **Optional kết quả rỗng**, không phải vì bản thân Stream có vấn đề về cú pháp.

### 3.4. `filter` loại bỏ giá trị

```java
var result = java.util.Optional.of(12)
        .filter(value -> value > 100);

// result là Optional<Integer> rỗng.
// result.orElseThrow(); // NoSuchElementException
```

`filter` không ném ngoại lệ khi điều kiện sai; nó trả Optional rỗng. Ngoại lệ chỉ xuất hiện khi **sau đó** code gọi `orElseThrow()` trên kết quả rỗng.

### 3.5. `map` trả về `null`

```java
var missingAfterMap = java.util.Optional.of("A")
        .map(s -> (String) null);

// missingAfterMap là Optional<String> rỗng.
```

`Optional.map` xử lý kết quả mapper như `ofNullable`: kết quả mapper `null` làm Optional mới rỗng. Vì vậy `missingAfterMap.orElseThrow()` sẽ ném `NoSuchElementException`. Điều này không giống `flatMap`, nơi mapper phải trả một Optional hợp lệ, không được trả `null`.

**Kết luận:** hãy tìm **nguồn phát sinh Optional rỗng** trong pipeline trước khi điều tra ngoại lệ. `orElseThrow()` chỉ bộc lộ trạng thái rỗng bằng một tín hiệu lỗi rõ ràng.

## 4. So sánh `orElseThrow()` với `get()`

`Optional.get()` và `Optional.orElseThrow()` **không tham số** có cùng hành vi cơ bản:

| API | Khi có giá trị | Khi rỗng | Ghi chú |
| --- | --- | --- | --- |
| `get()` | Trả về giá trị | Ném `NoSuchElementException` | Vẫn tồn tại trong Java hiện hành |
| `orElseThrow()` | Trả về giá trị | Ném `NoSuchElementException` | Được bổ sung ở Java 10; **API Note khuyến nghị thay cho `get()`** |

```java
var present = java.util.Optional.of("Java");

String a = present.get();
String b = present.orElseThrow();

System.out.println(a.equals(b)); // true
```

Điểm mạnh của `orElseThrow()` nằm ở **tên gọi mô tả rõ ý định “lấy hoặc ném lỗi”**. Nó giúp code review nhìn thấy rằng việc thiếu giá trị là một tình huống cần phải xử lý.

Không nên nói rằng `get()` đã biến mất hay tự động khác kiểu ngoại lệ trong Java mới. Hợp đồng hai phương thức vẫn hiện hành; Java API chỉ ưu tiên `orElseThrow()` về khả năng diễn đạt.

## 5. Hai overload `orElseThrow`: ngoại lệ mặc định và ngoại lệ do ứng dụng chọn

Java có **hai phương thức trùng tên**, nhưng chúng giải quyết các nhu cầu khác nhau.

### 5.1. Không tham số: Java 10+, cố định `NoSuchElementException`

```java
String name = optional.orElseThrow();
```

Nếu `optional` là `Optional<String>` có giá trị, trả chuỗi. Nếu rỗng, ném `java.util.NoSuchElementException` theo hợp đồng API. **Không có chỗ để truyền thông điệp lỗi hoặc loại ngoại lệ khác** ở overload này.

### 5.2. Có `Supplier`: cho phép ngoại lệ tùy biến

Overload có từ Java 8:

```java
<X extends Throwable> T orElseThrow(
        java.util.function.Supplier<? extends X> exceptionSupplier
) throws X
```

`Supplier` được gọi **chỉ khi Optional rỗng**, để tạo ngoại lệ mà ứng dụng muốn ném:

```java
var user = java.util.Optional.<String>empty();

String name = user.orElseThrow(
        () -> new IllegalArgumentException("Không tìm thấy người dùng")
);
```

Dòng trên ném `IllegalArgumentException`, **không** ném `NoSuchElementException`. Ta có thể chọn loại ngoại lệ phù hợp với hợp đồng nghiệp vụ, ví dụ `IllegalStateException` khi trạng thái nội bộ không đúng, hoặc một exception chuyên biệt đã định nghĩa cho ứng dụng.

Nếu muốn **giữ cùng loại `NoSuchElementException` nhưng thêm thông báo có ngữ cảnh**, dùng:

```java
String name = user.orElseThrow(
        () -> new java.util.NoSuchElementException("Không có user theo id")
);
```

Trong trường hợp này, ngoại lệ được **chính ứng dụng khởi tạo**, nên thông điệp được cung cấp là một phần hành vi do ứng dụng lựa chọn.

### 5.3. `Supplier` của overload tùy biến là lazy

```java
var present = java.util.Optional.of("Java");

String value = present.orElseThrow(
        () -> new IllegalStateException("Không được gọi nếu có dữ liệu")
);

System.out.println(value); // Java
```

Vì Optional đang có giá trị, Java trả về `"Java"` và **không gọi** lambda tạo exception. Đây là nguyên tắc quan trọng khi dựng lỗi có thông tin tốn kém; việc tạo exception không cần thiết sẽ không xảy ra nếu dữ liệu đã tồn tại.

**Đừng nhầm chữ `Supplier` trong overload này với `Supplier<T>` của `orElseGet`:** `orElseThrow` cần một supplier **trả ngoại lệ**, còn `orElseGet` cần supplier **trả giá trị dự phòng**.

## 6. Khi nào ném ngoại lệ, khi nào chọn giá trị dự phòng?

Không phải mọi Optional rỗng đều là lỗi nghiệp vụ. Hãy phân biệt ba chính sách.

### Chính sách A — Bắt buộc phải có giá trị

```java
String user = findUser("42").orElseThrow();
```

Phù hợp khi caller hoặc thuật toán đã xác lập bất biến rằng kết quả **phải tồn tại**, và nếu không có thì cần dừng xử lý thay vì tiếp tục với dữ liệu giả.

Nếu giá trị vắng mặt là điều bình thường (ví dụ tra cứu không bắt buộc), **không nên** dùng `orElseThrow()` chỉ để “lấy cho nhanh”.

### Chính sách B — Có giá trị mặc định

```java
String display = findUser("0").orElse("Khách");
```

`orElse(other)` trả Optional value khi có, nếu rỗng thì trả `other`. Nó **không ném `NoSuchElementException`** chỉ vì Optional rỗng.

**Lưu ý về đánh giá đối số:** biểu thức truyền vào `orElse(other)` được Java đánh giá khi gọi phương thức, kể cả Optional đã có giá trị. Nếu tạo default tốn chi phí, cân nhắc `orElseGet`.

### Chính sách C — Tạo giá trị dự phòng khi cần

```java
String display = findUser("0").orElseGet(
        () -> "Tài khoản khách"
);
```

`orElseGet(Supplier<? extends T>)` gọi supplier **chỉ khi Optional rỗng**. Chọn nó khi fallback là một thao tác cần tính toán hoặc cần gọi một phương thức.

| Lựa chọn | Optional có giá trị | Optional rỗng | Điểm khác biệt |
| --- | --- | --- | --- |
| `orElseThrow()` | Trả giá trị | `NoSuchElementException` | Thiếu dữ liệu là lỗi |
| `orElseThrow(() -> new X(...))` | Trả giá trị | Ngoại lệ `X` do supplier tạo | Tùy biến hợp đồng lỗi |
| `orElse(defaultValue)` | Trả giá trị | Trả default | Đối số default được đánh giá trước lời gọi |
| `orElseGet(() -> fallback())` | Trả giá trị | Gọi supplier và trả kết quả | Chỉ tạo fallback khi cần |
| `isPresent()`/`isEmpty()` | Kiểm tra trạng thái | Kiểm tra trạng thái | Không lấy giá trị hay ném `NoSuchElementException` do trạng thái rỗng |

`isEmpty()` được bổ sung từ **Java 11**; ví dụ hoàn chỉnh của bài biên dịch trên Java 17+, nên có thể dùng. Nếu mã phải chạy đúng Java 10, dùng `!optional.isPresent()` thay cho `optional.isEmpty()`.

## 7. Khi catch `NoSuchElementException`, hãy hiểu đúng tầng xử lý

Ví dụ xử lý tại ranh giới ứng dụng:

```java
try {
    String name = findUser("0").orElseThrow();
    System.out.println(name);
} catch (java.util.NoSuchElementException ex) {
    System.out.println("Không tìm thấy dữ liệu");
}
```

Đây là một **lựa chọn thiết kế**, không phải quy tắc buộc phải catch mọi lời gọi. Với nhiều API, cho exception lan lên caller xử lý ở ranh giới thích hợp sẽ rõ ràng hơn.

**Cần cẩn trọng khi catch quá rộng:**

- `NoSuchElementException` còn được dùng bởi các API khác, ví dụ khi gọi `Iterator.next()` không còn phần tử; đừng tự động giả định **mọi** exception thuộc loại này đều do `Optional.orElseThrow()`.
- Tránh bọc một khối xử lý rất lớn bằng `catch (NoSuchElementException)` rồi mặc định trả “không tìm thấy user”: exception có thể bắt nguồn từ thao tác khác trong khối và bị hiểu sai.
- Nếu cần báo lỗi nghiệp vụ cụ thể (ví dụ một đơn hàng không tồn tại), `orElseThrow(() -> new OrderNotFoundException(id))` — khi ứng dụng có loại exception đó — thường làm contract rõ hơn.
- Không dùng `catch (Exception e)` để nuốt lỗi rồi trả `null` hoặc giá trị giả nếu điều đó che giấu bất biến bị vi phạm.

Với application API, nên phân biệt “không tìm thấy là kết quả bình thường” với “không tìm thấy là tình huống lỗi”. `Optional` cho phép caller quyết định tại nơi thích hợp.

## 8. Chương trình Java 17+ hoàn chỉnh

Lưu nội dung sau trong tệp **`OptionalEmptyDemo.java`**:

```java
import java.util.NoSuchElementException;
import java.util.Optional;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.stream.Stream;

public class OptionalEmptyDemo {

    static Optional<String> findUser(String id) {
        return "42".equals(id)
                ? Optional.of("Lan")
                : Optional.empty();
    }

    static String requireUser(String id) {
        return findUser(id).orElseThrow();
    }

    public static void main(String[] args) {
        var present = Optional.of("Java");
        var empty = Optional.<String>empty();

        System.out.println("present=" + present.orElseThrow());
        System.out.println("isEmpty=" + empty.isEmpty());

        try {
            empty.orElseThrow();
        } catch (NoSuchElementException ex) {
            System.out.println(
                    "emptyException=" + ex.getClass().getSimpleName());
        }

        try {
            Optional.ofNullable((String) null).orElseThrow();
        } catch (NoSuchElementException ex) {
            System.out.println(
                    "nullableException=" + ex.getClass().getSimpleName());
        }

        System.out.println("default=" + empty.orElse("guest"));

        // orElseGet không chạy supplier nếu Optional có giá trị.
        var supplierCalls = new AtomicInteger();
        var unchanged = present.orElseGet(() -> {
            supplierCalls.incrementAndGet();
            return "fallback";
        });
        System.out.println("unchanged=" + unchanged);
        System.out.println("supplierCallsBefore=" + supplierCalls.get());

        var provided = empty.orElseGet(() -> {
            supplierCalls.incrementAndGet();
            return "generated";
        });
        System.out.println("provided=" + provided);
        System.out.println("supplierCallsAfter=" + supplierCalls.get());

        // orElseThrow có Supplier không tạo ngoại lệ khi có giá trị.
        var exceptionCalls = new AtomicInteger();
        var safe = present.orElseThrow(() -> {
            exceptionCalls.incrementAndGet();
            return new IllegalStateException("should not be called");
        });
        System.out.println("safe=" + safe);
        System.out.println("exceptionCalls=" + exceptionCalls.get());

        try {
            empty.orElseThrow(
                    () -> new IllegalArgumentException("missing user"));
        } catch (IllegalArgumentException ex) {
            System.out.println(
                    "customException=" + ex.getClass().getSimpleName());
        }

        System.out.println("foundUser=" + requireUser("42"));
        try {
            requireUser("0");
        } catch (NoSuchElementException ex) {
            System.out.println(
                    "missingUser=" + ex.getClass().getSimpleName());
        }

        try {
            Stream.<String>empty().findFirst().orElseThrow();
        } catch (NoSuchElementException ex) {
            System.out.println(
                    "emptyStream=" + ex.getClass().getSimpleName());
        }
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 -encoding UTF-8 OptionalEmptyDemo.java
java OptionalEmptyDemo
```

**Stdout chính xác:**

```text
present=Java
isEmpty=true
emptyException=NoSuchElementException
nullableException=NoSuchElementException
default=guest
unchanged=Java
supplierCallsBefore=0
provided=generated
supplierCallsAfter=1
safe=Java
exceptionCalls=0
customException=IllegalArgumentException
foundUser=Lan
missingUser=NoSuchElementException
emptyStream=NoSuchElementException
```

### Giải thích kết quả

1. `present=Java`: `orElseThrow()` trên Optional có giá trị trả thẳng `String`.
2. `isEmpty=true`: Optional được tạo bằng `Optional.<String>empty()` không có phần tử. `isEmpty()` từ Java 11 chỉ kiểm tra trạng thái, không ném ngoại lệ.
3. `emptyException` và `nullableException` đều là `NoSuchElementException`, dù một Optional được tạo trực tiếp bằng `empty()`, còn cái kia đến từ `ofNullable(null)`.
4. `default=guest`: `orElse` không ném ngoại lệ khi rỗng, mà trả giá trị dự phòng.
5. `supplierCallsBefore=0`, `supplierCallsAfter=1`: supplier của `orElseGet` chỉ được thực thi trong nhánh rỗng.
6. `exceptionCalls=0`: supplier của `orElseThrow(Supplier)` không chạy khi Optional có giá trị.
7. `customException=IllegalArgumentException`: khi truyền supplier tùy biến, ngoại lệ ném ra là kiểu do ứng dụng chọn, không bắt buộc là `NoSuchElementException`.
8. `foundUser=Lan` và `missingUser=NoSuchElementException`: cùng phương thức `requireUser` có thể thành công hoặc dừng khi không tìm được đối tượng.
9. `emptyStream=NoSuchElementException`: `Stream.findFirst()` với stream không có phần tử trả Optional rỗng; chính lời gọi `orElseThrow()` sau đó ném ngoại lệ.

Chương trình sử dụng API còn hiệu lực trong Java hiện hành và cú pháp ổn định; không cần bật preview.

## 9. Trường hợp thường gặp trong ứng dụng

### 9.1. Tra cứu theo ID

```java
Optional<User> lookup(String id) {
    // Trả Optional<User> khi tìm thấy, Optional.empty() nếu không.
}
```

Đây chỉ là **chữ ký và ý tưởng**, không phải phương thức runnable độc lập: `User` là kiểu domain do ứng dụng định nghĩa, phần thân cần triển khai.

Nếu người gọi **bắt buộc** cần user:

```java
User user = lookup(id).orElseThrow();
```

Cách này mô tả rằng không tìm thấy là lỗi. Nếu muốn ngoại lệ có mã nghiệp vụ hoặc ID, dùng overload supplier:

```java
User user = lookup(id).orElseThrow(
        () -> new IllegalArgumentException("User không tồn tại: " + id)
);
```

Trong hệ thống lớn, một exception domain chuyên biệt có thể thích hợp hơn `IllegalArgumentException`; ví dụ chỉ dùng lớp chuẩn để minh họa.

Nếu thiếu user là trạng thái bình thường:

```java
String displayName = lookup(id)
        .map(User::displayName)
        .orElse("Khách");
```

Cũng là đoạn minh họa trong ngữ cảnh có class `User` với phương thức `displayName()`. Ở đây API trả fallback thay vì ném exception.

### 9.2. Kết quả của pipeline Stream

```java
var top = java.util.stream.Stream.of(3, 7, 5)
        .filter(n -> n > 10)
        .findFirst();
```

`top` là Optional rỗng vì không có số thỏa điều kiện. Lời gọi `top.orElseThrow()` sẽ ném `NoSuchElementException`; đây không phải “Stream bị lỗi”, mà là kết quả truy vấn không tìm thấy.

Nếu kết quả có thể vắng mặt, chọn:

```java
int value = top.orElse(0);
```

Nếu không có kết quả đồng nghĩa bất biến vi phạm, `orElseThrow()` có thể là quyết định đúng.

### 9.3. Không nhất thiết phải mở Optional ngay

Trong nhiều API, phương thức nên **trả Optional cho caller** để caller quyết định chính sách thiếu dữ liệu:

```java
static Optional<String> findByCode(String code) {
    return "A".equals(code)
            ? Optional.of("Active")
            : Optional.empty();
}
```

Nếu tầng dữ liệu có thể không tìm thấy, không bắt buộc phải gọi `orElseThrow()` ngay tại tầng này. Cung cấp kết quả Optional giúp tầng ứng dụng phân biệt điều kiện “không có kết quả” bình thường và “thiếu dữ liệu cần báo lỗi”.

Đồng thời, đừng trả **`null` thay cho `Optional.empty()`**; điều đó làm vô hiệu mục đích của Optional và tạo nguy cơ `NullPointerException` khi người gọi sử dụng.

## 10. Lỗi thường gặp và cách sửa

**Lỗi 1 — Cho rằng `orElseThrow()` trả về `null` khi rỗng.**  
Sai. Nó ném `NoSuchElementException`. Muốn có fallback có thể `null`, API `orElse(null)` chấp nhận điều đó, nhưng hãy cân nhắc vì có thể làm mất lợi ích tránh null của Optional.

**Lỗi 2 — Gọi `Optional.of(null)` và mong nhận Optional rỗng.**  
Sai. `of(null)` ném `NullPointerException` ngay lúc tạo. Dùng `Optional.ofNullable(value)` khi biến nguồn có thể bằng null.

**Lỗi 3 — Nhầm `orElseThrow()` với `orElseThrow(Supplier)`.**  
Sai. Không tham số luôn dùng `NoSuchElementException` khi rỗng; overload supplier ném exception do supplier tạo. Chọn đúng overload theo hợp đồng lỗi.

**Lỗi 4 — Nghĩ `get()` an toàn hơn vì tên giống getter.**  
Sai. `get()` cũng ném `NoSuchElementException` khi rỗng. API Note hiện hành khuyến nghị `orElseThrow()` vì tên thể hiện khả năng ném ngoại lệ.

**Lỗi 5 — Gọi `isPresent()` trước rồi vẫn xử lý cùng nhánh rỗng bằng `get()` mà không có lý do.**  
Ví dụ:

```java
if (user.isPresent()) {
    return user.get();
}
throw new java.util.NoSuchElementException();
```

Đây là **đoạn code minh họa** trong một phương thức trả `String` và với biến `user` là `Optional<String>`. Khi đúng ý định “phải có hoặc ném lỗi”, có thể rút gọn thành `return user.orElseThrow();` mà vẫn rõ nghĩa.

**Lỗi 6 — Trông chờ `orElseThrow()` luôn gắn thông tin nghiệp vụ.**  
Không tham số không nhận ID hoặc thông điệp. Muốn lỗi có ngữ cảnh, dùng `orElseThrow(() -> new MyException(...))` với loại exception phù hợp hoặc tự tạo `NoSuchElementException("...")` qua supplier.

**Lỗi 7 — Nuốt mọi `NoSuchElementException` trong đoạn xử lý rộng.**  
Ngoại lệ này cũng có thể đến từ iterator hoặc API khác. Hãy bắt ngoại lệ ở phạm vi đúng và tránh chuyển nhầm lỗi lập trình khác thành “không tìm thấy”.

**Lỗi 8 — Nghĩ `orElseGet` và `orElseThrow` có cùng Supplier.**  
Sai: `orElseGet` cần supplier **trả giá trị**, `orElseThrow` cần supplier **trả Throwable**. Không dùng cách này thay cho cách kia khi mục tiêu khác nhau.

**Lỗi 9 — Đánh đồng “không có giá trị” với “lỗi luôn phải ném”.**  
Optional rỗng có thể hoàn toàn hợp lệ. Chỉ gọi `orElseThrow()` khi caller cần biến thiếu dữ liệu thành ngoại lệ. Nếu không, dùng fallback hoặc tiếp tục truyền Optional.

## 11. Câu hỏi tự kiểm tra

**Câu 1.** `Optional.<String>empty().orElseThrow()` có ném `NullPointerException` không?  
**Đáp án:** Không. Nó ném **`NoSuchElementException`** vì Optional tồn tại hợp lệ nhưng rỗng.

**Câu 2.** `Optional.ofNullable(null).orElseThrow()` khác `Optional.of(null)` ở điểm nào?  
**Đáp án:** Cách thứ nhất tạo Optional rỗng rồi ném `NoSuchElementException` khi gọi `orElseThrow`; cách thứ hai ném `NullPointerException` ngay tại `of`.

**Câu 3.** Khi Optional có giá trị, `orElseThrow(() -> new IllegalStateException())` có tạo ngoại lệ rồi bỏ đi không?  
**Đáp án:** Không. Exception supplier không được gọi, giá trị được trả về.

**Câu 4.** Có thể bắt `NoSuchElementException` bằng `catch (RuntimeException e)` không?  
**Đáp án:** Có về mặt phân cấp kiểu, vì nó là subtype của `RuntimeException`; nhưng việc bắt rộng như vậy thường không phù hợp nếu chỉ muốn xử lý thiếu dữ liệu.

**Câu 5.** Nếu một stream không có kết quả từ `findFirst()`, lời gọi `findFirst().orElseThrow()` làm gì?  
**Đáp án:** `findFirst()` trả Optional rỗng; `orElseThrow()` ném `NoSuchElementException`.

**Câu 6.** Khi nào chọn `orElse("guest")` thay cho `orElseThrow()`?  
**Đáp án:** Khi việc không có dữ liệu là tình huống được chấp nhận và application có giá trị mặc định hợp lệ.

**Câu 7.** `get()` có bị xóa khỏi API Java hiện nay không?  
**Đáp án:** Không. `get()` vẫn tồn tại, nhưng Java API Note nói `orElseThrow()` là lựa chọn được ưu tiên khi muốn lấy giá trị hoặc ném ngoại lệ.

## 12. Ghi nhớ

1. **`Optional.orElseThrow()` không tham số có từ Java 10**: có giá trị thì trả về; rỗng thì ném **`java.util.NoSuchElementException`**.
2. `NoSuchElementException` là unchecked exception, không phải `NullPointerException` và không phải giá trị `null`.
3. `Optional.empty()`, `ofNullable(null)`, kết quả stream không tìm thấy, `filter` loại bỏ dữ liệu hoặc `map` trả null đều có thể tạo Optional rỗng.
4. `Optional.get()` cũng ném cùng loại ngoại lệ khi rỗng, nhưng API hiện hành ưu tiên `orElseThrow()` để tên gọi rõ ý định.
5. **`orElseThrow(Supplier)` khác overload không tham số**: cho phép tự chọn exception, chỉ gọi supplier khi Optional rỗng.
6. Dùng `orElse`/`orElseGet` khi sự vắng mặt có thể được xử lý bằng fallback; dùng `orElseThrow()` khi không có giá trị là lỗi đúng với hợp đồng.
7. Khi điều tra ngoại lệ, tìm **lý do Optional rỗng**, tránh catch rộng làm che giấu lỗi không liên quan và không phụ thuộc câu thông báo mặc định.

## Tài liệu tham khảo chính thức còn áp dụng

- Java SE 26 API — `Optional<T>`, `orElseThrow()`, `orElseThrow(Supplier)`, `get()`, `empty()` và `ofNullable()`: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Optional.html
- Java SE 26 API — `NoSuchElementException`: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/NoSuchElementException.html
- Java SE 26 API — `Stream.findFirst()`: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Stream.html
- Dev.java — Using Optionals, các cách xử lý Optional rỗng: https://dev.java/learn/api/streams/optionals/
- Java SE 10 API — lịch sử bổ sung `Optional.orElseThrow()` không tham số (Since 10): https://docs.oracle.com/javase/10/docs/api/java/util/Optional.html
