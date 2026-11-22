# Phân biệt Optional rỗng với dữ liệu sai hoặc lỗi xử lý

## 1. Vấn đề và quy tắc cốt lõi

`java.util.Optional<T>` biểu diễn **một giá trị có thể có hoặc không có**. Từ Java 10, `Optional.orElseThrow()` không tham số cho phép lấy giá trị nếu Optional có dữ liệu, hoặc ném `NoSuchElementException` nếu nó rỗng. API này vẫn được hỗ trợ trong Java hiện đại.

Nhưng không nên đánh đồng ba trường hợp sau:

1. **Vắng mặt hợp lệ (expected absence):** đầu vào hợp lệ, quá trình tra cứu hoàn tất bình thường, nhưng không có bản ghi/kết quả. Một phương thức được thiết kế để tìm kiếm có thể dùng `Optional.empty()` cho trường hợp này.
2. **Đầu vào hoặc dữ liệu sai (invalid input/data):** ví dụ ID bằng 0 trong hệ thống chỉ chấp nhận ID dương, bản ghi thiếu trường bắt buộc, hoặc chuỗi không parse được theo định dạng công bố. Cần báo lỗi validation hoặc một kiểu kết quả lỗi rõ ràng, không âm thầm biến thành empty nếu caller cần phân biệt.
3. **Lỗi xử lý (processing failure):** ví dụ dịch vụ phụ thuộc không khả dụng, timeout hoặc bug. Không nên nuốt các ngoại lệ này rồi trả `Optional.empty()` như thể chỉ không tìm thấy dữ liệu.

Ví dụ:

~~~java
// Đoạn minh họa trong một method; cần import java.util.Optional.
Optional<String> found = Optional.of("Java");
Optional<String> missing = Optional.empty();

System.out.println(found.orElseThrow()); // Java

// Nếu chạy, lệnh sau ném NoSuchElementException:
// missing.orElseThrow();
~~~

Điều `orElseThrow()` kiểm tra chỉ là **Optional present hay empty**. Nó không tự biết giá trị thiếu vì chưa có bản ghi, input sai, database gặp lỗi hay logic ứng dụng đã lọc dữ liệu. Đó là trách nhiệm thiết kế API ở tầng tạo ra Optional.

Bài học thuộc Java 10, nhưng chỉ sử dụng kiến thức còn áp dụng hiện nay. Các ví dụ hoàn chỉnh dùng Java 17+; `orElseThrow()` không tham số có từ Java 10, còn `orElseThrow(Supplier)` có từ Java 8.

## 2. Trạng thái của Optional và ý nghĩa của empty

Một đối tượng `Optional<T>` ở mức API có hai trạng thái:

- **Present:** chứa một giá trị tham chiếu không null.
- **Empty:** không chứa giá trị.

Không có trạng thái có sẵn kiểu “validation failed”, “access denied”, “database timeout” hoặc “internal error” trong bản thân `Optional<T>`.

~~~java
// Java 17+; Optional.isEmpty() được bổ sung từ Java 11.
var a = Optional.of("JDK");
var b = Optional.<String>empty();

System.out.println(a.isPresent()); // true
System.out.println(a.isEmpty());   // false
System.out.println(b.isEmpty());   // true
~~~

Nếu nhận một `Optional.empty()`, người gọi **không thể biết nguyên nhân** chỉ từ việc gọi `isEmpty()`. Ý nghĩa phải được định nghĩa tại **hợp đồng phương thức** trả Optional.

Xét phương thức minh họa:

~~~java
// Phương thức minh họa nằm trong một class.
static Optional<String> findLabel(int id) {
    if (id <= 0) {
        throw new IllegalArgumentException("id must be positive");
    }
    if (id == 503) {
        throw new IllegalStateException("storage unavailable");
    }
    return id == 1 ? Optional.of("Java") : Optional.empty();
}
~~~

Ở đây:

- `findLabel(1)` trả present, chứa `"Java"`.
- `findLabel(2)` trả empty: ID hợp lệ, kết quả tra cứu không có.
- `findLabel(0)` ném `IllegalArgumentException`: đầu vào không hợp lệ.
- `findLabel(503)` ném `IllegalStateException`: ví dụ mô phỏng hệ lưu trữ lỗi.

Các quy tắc trên là lựa chọn của **API mẫu**, không phải Java bắt mọi repository dùng các mã ID hay loại ngoại lệ này. Trong dự án thật, cần thiết kế hợp đồng đủ rõ để người gọi biết nên hiển thị “không tìm thấy”, yêu cầu sửa input, thử lại hay điều tra sự cố.

| Tình huống | Điều đã xảy ra | Cách biểu diễn có thể phù hợp |
| --- | --- | --- |
| ID hợp lệ nhưng không có bản ghi | Truy vấn hoàn tất, kết quả vắng mặt | `Optional.empty()` |
| ID hợp lệ, có bản ghi | Có kết quả | `Optional.of(value)` |
| ID âm trong API chỉ chấp nhận ID dương | Yêu cầu không hợp lệ | Validation exception hoặc result có lỗi |
| Dữ liệu tồn tại nhưng vi phạm invariant bắt buộc | Dữ liệu sai | Lỗi dữ liệu rõ ràng, không mặc nhiên coi là missing |
| Lỗi kết nối database | Tra cứu thất bại | Ngoại lệ xử lý giữ cause/loại lỗi |
| Không có quyền xem | Chính sách truy cập | Kết quả hoặc lỗi theo thiết kế bảo mật |
| Filter loại một giá trị present | Giá trị không đạt điều kiện | Phải phân biệt với không tìm thấy nếu nghiệp vụ yêu cầu |

## 3. Hai biến thể Optional.orElseThrow

### 3.1. orElseThrow() không tham số — từ Java 10

~~~java
// Đoạn ví dụ trong phương thức.
var present = Optional.of("Java");
var absent = Optional.<String>empty();

System.out.println(present.orElseThrow()); // Java

try {
    absent.orElseThrow();
} catch (java.util.NoSuchElementException expected) {
    System.out.println("empty");
}
// Dòng in sau Java: empty
~~~

Theo Javadoc, khi present, `orElseThrow()` trả giá trị. Khi empty, nó ném `java.util.NoSuchElementException`. Phương thức không gọi lại repository, không tự tạo giá trị mặc định và không suy ra lý do absence.

So với `Optional.get()`: `get()` **vẫn tồn tại** trong Java hiện đại và cũng ném `NoSuchElementException` khi empty. Javadoc khuyến nghị `orElseThrow()` vì tên phương thức chỉ rõ khả năng ném exception; không nên viết rằng `get()` đã bị xóa khỏi Java.

### 3.2. orElseThrow(Supplier) — chọn ngoại lệ có ngữ nghĩa

~~~java
var present = Optional.of("Java");
var absent = Optional.<String>empty();

String value = present.orElseThrow(
        () -> new IllegalStateException("required value missing")
);
System.out.println(value); // Java

try {
    absent.orElseThrow(
            () -> new IllegalStateException("required value missing")
    );
} catch (IllegalStateException expected) {
    System.out.println(expected.getMessage()); // required value missing
}
~~~

Ở ví dụ này, `IllegalStateException` chỉ minh họa cách truyền supplier. Ở ranh giới nghiệp vụ, một ngoại lệ domain như `ResourceNotFoundException` có thể giúp caller phân biệt chính xác “không có tài nguyên” với “trạng thái ứng dụng sai”.

Chữ ký của overload có supplier có dạng:

~~~java
// Chữ ký API để đọc kiểu generic, không phải định nghĩa lại trong class.
public <X extends Throwable> T orElseThrow(
        Supplier<? extends X> exceptionSupplier
) throws X
~~~

`X` là loại ngoại lệ do supplier tạo ra; Java có thể kiểm tra checked exception qua `throws`/`catch`. Overload này đã tồn tại trước Java 10. Không nhầm mốc có từ Java 8 của overload này với mốc Java 10 của biến thể không tham số.

### 3.3. Supplier chỉ được gọi khi Optional rỗng

~~~java
// Java 17+, minh họa lazy evaluation.
var calls = new java.util.concurrent.atomic.AtomicInteger();

String value = Optional.of("Java").orElseThrow(() -> {
    calls.incrementAndGet();
    return new IllegalStateException("missing");
});

System.out.println(value);       // Java
System.out.println(calls.get()); // 0
~~~

Khi present, hàm xây ngoại lệ không chạy. Điều này có lợi khi thông điệp lỗi cần ghép ID hoặc bối cảnh chỉ dành cho nhánh thiếu kết quả.

### 3.4. Không bọc tự động ngoại lệ phát sinh trước đó

~~~java
// findLabel(503) ném IllegalStateException ngay khi được gọi.
String result = findLabel(503).orElseThrow(
        () -> new IllegalArgumentException("no record")
);
~~~

Trong Java, phải tính xong `findLabel(503)` mới gọi được `orElseThrow`. Vì `findLabel(503)` đã ném lỗi hạ tầng mô phỏng, supplier không chạy; ngoại lệ `IllegalStateException("storage unavailable")` lan ra.

Đó là hành vi **đúng** khi muốn giữ riêng lỗi xử lý và absence. Không hiểu rằng cứ viết `orElseThrow(Supplier)` thì mọi exception của toàn biểu thức sẽ biến thành exception do supplier tạo.

## 4. Khi nào Optional.empty là một kết quả bình thường?

Một phương thức tìm kiếm thường cho phép “không có kết quả”:

~~~java
// Hợp đồng minh họa:
Optional<String> findNickname(int userId);
~~~

Nếu người dùng **có thể không đặt nickname**, không có giá trị là một kết quả hợp lệ. Caller có thể:

~~~java
// Minh họa nếu nickname là Optional<String> đã có.
String label = nickname.orElse("Anonymous");
~~~

Ở đây không cần exception, bởi fallback được thiết kế như một giá trị thay thế hợp lệ.

Tương tự, một repository `findById` có thể trả empty khi truy vấn ID hợp lệ đã hoàn tất nhưng không có bản ghi. Đó là tình huống bình thường cho một hàm tìm kiếm. Caller khác, ví dụ một thao tác cập nhật cần bản ghi bắt buộc tồn tại, có thể **nâng absence thành lỗi domain**:

~~~java
// Trong một class có các phương thức/type tương ứng:
static String requireLabel(int id) {
    return findLabel(id)
            .orElseThrow(() -> new MissingItemException(id));
}
~~~

Lúc này `findLabel(2)` tự nó không phải lỗi, nhưng `requireLabel(2)` nói rằng thao tác **bắt buộc cần dữ liệu** và ném lỗi “không tìm thấy”.

Chú ý: “Không tìm thấy” không đồng nghĩa tất cả ứng dụng buộc phải ném ngoại lệ. API có thể trả một kiểu kết quả rõ ràng hoặc trả trạng thái HTTP phù hợp; trách nhiệm được quyết định bởi tầng gọi.

## 5. Dữ liệu sai phải được biểu diễn khác absence

### 5.1. Validation ở biên đầu vào

Giả sử ID phải lớn hơn 0:

~~~java
static void validateId(int id) {
    if (id <= 0) {
        throw new IllegalArgumentException("id must be positive");
    }
}
~~~

Đầu vào `id = -3` không phải một “ID hợp lệ nhưng không tồn tại”. Nếu trả empty, caller có thể hiển thị thông báo sai cho người dùng và bỏ qua lỗi trong thao tác nhập liệu.

### 5.2. Dữ liệu tồn tại nhưng không hợp lệ

Giả sử một bản ghi có trường `price` bắt buộc là số:

~~~java
// Minh họa parse; đoạn lỗi sẽ ném NumberFormatException.
int price = Integer.parseInt("not-a-number");
~~~

Không nên bắt `NumberFormatException` rồi mặc nhiên trả `Optional.empty()` nếu kết quả “không tìm thấy bản ghi” vốn khác “có bản ghi nhưng dữ liệu sai”.

Dữ liệu invalid có thể được trả bằng validation result, ngoại lệ có bối cảnh, hoặc mô hình kết quả phong phú hơn, tùy tầng ứng dụng.

### 5.3. Optional.of và ofNullable có ý nghĩa khác nhau

~~~java
String maybeMissing = null;

// Khi null là trạng thái vắng mặt hợp lệ:
Optional<String> a = Optional.ofNullable(maybeMissing);
System.out.println(a.isEmpty()); // true

// Khi value bắt buộc non-null, đây là lỗi:
// Optional.of(maybeMissing); // NullPointerException
~~~

`Optional.ofNullable(null)` **cố tình** đổi null thành empty. Chỉ nên dùng nếu hợp đồng giá trị nguồn cho phép null có nghĩa “không có dữ liệu”. Nếu một hàm cam kết non-null nhưng lại trả null vì bug, dùng `ofNullable` sẽ che lỗi và biến thành absence.

Trong trường hợp muốn lộ vi phạm non-null, có thể dùng:

~~~java
// Minh họa: giá trị bắt buộc có, null là dữ liệu sai.
String required = java.util.Objects.requireNonNull(
        maybeMissing, "required field must not be null"
);
~~~

Không nên đổi mọi `Optional.of` thành `Optional.ofNullable` chỉ để tránh exception, nếu làm thế khiến hệ thống mất thông tin về dữ liệu lỗi.

## 6. Lỗi xử lý không được nuốt thành Optional.empty

Một phản mẫu phổ biến:

~~~java
// Khung ví dụ có repositoryLookup do ứng dụng cung cấp:
static Optional<String> unsafeFind(int id) {
    try {
        return repositoryLookup(id);
    } catch (Exception error) {
        return Optional.empty(); // Che mọi lỗi xử lý.
    }
}
~~~

Ví dụ là mã minh họa, không độc lập để chạy: `repositoryLookup` do ứng dụng định nghĩa. Nó có thể biến timeout, lỗi truy vấn, lỗi parse hoặc bug thành “không tìm thấy” dù thực tế thao tác chưa hoàn thành thành công.

Tác hại:

- Người dùng nhận “không tồn tại” thay vì lỗi tạm thời cần retry.
- Báo cáo và metric đếm sai tỉ lệ không tìm thấy.
- Lỗi hạ tầng bị che giấu, làm monitoring khó phát hiện vấn đề.
- Nguyên nhân `cause` và stack trace không còn đi tới tầng xử lý phù hợp.
- Quy tắc nghiệp vụ có thể tiếp tục với dữ liệu thiếu giả tạo.

Cấu trúc tốt hơn:

~~~java
// Khung minh họa:
static Optional<String> safeFind(int id) {
    validateId(id);              // Đầu vào sai thì báo validation.
    return repositoryLookup(id); // Empty chỉ khi không có bản ghi;
                                  // lỗi xử lý lan ra hoặc được bọc có cause.
}
~~~

**Không có một ánh xạ bắt buộc cho mọi repository.** Điều quan trọng là phương thức phải công bố rõ: khi nào empty, khi nào ngoại lệ/lỗi riêng và ai chịu trách nhiệm retry.

Có thể có chính sách bảo mật cố tình không tiết lộ sự tồn tại của một đối tượng khi người dùng thiếu quyền. Khi đó sự đánh đồng phải là **quyết định tường minh** và vẫn cần observability phù hợp; nó không biện minh cho việc catch mọi `Exception` rồi trả empty.

## 7. Optional.map, filter và flatMap có thể tạo ra những tình huống dễ nhầm

### 7.1. map trả null làm Optional rỗng

~~~java
var result = Optional.of("Java")
        .map(s -> (String) null);

System.out.println(result.isEmpty()); // true
~~~

Theo hợp đồng Java, `Optional.map` bọc kết quả mapper giống như `Optional.ofNullable`: nếu mapper trả null, nó tạo empty. Vì vậy empty **không chứng minh** rằng giá trị đầu vào `"Java"` đã vắng mặt.

Một lỗi thực tế:

~~~java
// Mã minh họa, khi User.getName() có thể trả null.
Optional<String> name = userOptional.map(User::getName);
~~~

Nếu phương thức `getName()` trả null, `name` rỗng dù `userOptional` có user. Nếu tên là trường bắt buộc, có thể coi đó là vi phạm invariant, cần validate riêng thay vì coi user “không tồn tại”.

### 7.2. filter loại một giá trị hiện diện

~~~java
var age = Optional.of(16);
var adultAge = age.filter(a -> a >= 18);

System.out.println(adultAge.isEmpty()); // true
~~~

Một giá trị present **không qua điều kiện** cũng tạo Optional.empty. Nếu nghiệp vụ phân biệt “không tìm thấy user” với “user chưa đủ tuổi” hoặc “user đã bị khóa”, không nên kết hợp toàn bộ điều kiện trong `filter` rồi báo chung “user missing”.

Phản mẫu khái niệm:

~~~java
// Nếu cần phân biệt inactive và not-found, cách này che nguyên nhân:
findUser(id)
        .filter(User::isActive)
        .orElseThrow(() -> new UserNotFoundException(id));
~~~

Đoạn minh họa giả định `User`/`findUser`/exception tồn tại. User có thật nhưng inactive sẽ bị báo như không tìm thấy. Hãy tìm user trước rồi kiểm tra trạng thái để phát ra lỗi thích hợp, trừ khi chính sách yêu cầu cố tình che dấu.

### 7.3. flatMap không chấp nhận mapper trả null

~~~java
// Đoạn sau ném NullPointerException, không tạo empty.
Optional.of("Java")
        .flatMap(s -> (Optional<String>) null);
~~~

`Optional.flatMap` yêu cầu mapper trả một `Optional` không null. Khác `map`, một kết quả mapper null là lỗi.

### 7.4. Exception trong mapper/predicate lan ra

~~~java
// NumberFormatException lan ra từ mapper.
Optional.of("bad")
        .map(Integer::parseInt);
~~~

`map` không bắt `NumberFormatException` để tạo empty. `filter` cũng không tự chuyển exception của predicate thành empty. Chỉ giá trị hoặc điều kiện theo hợp đồng biến đổi mới tạo empty. Việc catch lỗi rồi tự trả empty là lựa chọn của code ứng dụng, cần kiểm tra xem có đúng hợp đồng hay không.

**Bài học:** khi thấy một Optional rỗng, hãy xem **đường đi tạo ra nó**. Empty có thể phát sinh từ một tra cứu vắng mặt hợp lệ, từ `ofNullable(null)`, từ `map` trả null hoặc từ `filter` không đạt điều kiện. Nếu nghiệp vụ cần phân biệt các trường hợp, một Optional duy nhất không đủ.

## 8. orElse, orElseGet và orElseThrow: chọn theo nghĩa nghiệp vụ

| Phương thức | Khi present | Khi empty | Dùng trong tình huống nào |
| --- | --- | --- | --- |
| `orElse(value)` | Trả giá trị Optional | Trả giá trị mặc định | Absence có fallback hợp lệ |
| `orElseGet(supplier)` | Trả giá trị Optional, không gọi supplier | Tính fallback bằng supplier | Fallback cần tính lười |
| `orElseThrow()` | Trả giá trị Optional | `NoSuchElementException` | Yêu cầu kết quả bắt buộc, lỗi chung đủ dùng |
| `orElseThrow(exceptionSupplier)` | Trả giá trị Optional | Ném ngoại lệ do supplier tạo | Cần lỗi domain giàu ngữ cảnh |

### Giá trị mặc định không được che lỗi bắt buộc

~~~java
var language = Optional.<String>empty()
        .orElse("English");
System.out.println(language); // English
~~~

Fallback hợp lý nếu ngôn ngữ là cấu hình có giá trị mặc định. Không dùng fallback “giả” cho một mã giao dịch, giá trị giá bán hoặc thông tin bảo mật **bắt buộc tồn tại** nếu thiếu dữ liệu cần phải báo lỗi.

### orElse so với orElseGet về đánh giá tham số

~~~java
var value = Optional.of("Java");
var result = value.orElseGet(() -> "fallback");
System.out.println(result); // Java
~~~

Vì `orElseGet` nhận supplier, nó không tính fallback khi present. Nhưng `orElse(expensiveCall())` là lời gọi phương thức Java thông thường: `expensiveCall()` được **đánh giá trước khi `orElse` nhận tham số**, dù Optional đã có giá trị. Nếu tính fallback tốn tài nguyên hoặc có side effect, hãy dùng `orElseGet`.

### orElseThrow chỉ chuyển absence, không thay thế exception handling

Nếu bước đọc dữ liệu ném `IllegalStateException`, `orElseThrow(() -> new MissingItemException(...))` phía sau không chạy. Không dùng nó như khối `catch`.

### checked exception qua supplier

`orElseThrow(Supplier)` có kiểu generic cho exception, nên có thể ném cả một checked exception:

~~~java
// Minh họa trong method có khai báo throws java.io.IOException:
String required = Optional.<String>empty().orElseThrow(
        () -> new java.io.IOException("value missing")
);
~~~

Compiler yêu cầu khai báo `throws` hoặc xử lý checked exception theo quy tắc Java. Chọn exception dựa vào hợp đồng caller, không phải chỉ để viết cú pháp ngắn nhất.

## 9. Ví dụ Java 17+ đầy đủ: present, missing, invalid và processing failure

Lưu tệp **`OptionalEmptyVsFailureDemo.java`**. Chương trình mô phỏng một truy vấn có kết quả, một truy vấn không có bản ghi, một ID không hợp lệ và một lỗi lưu trữ. Ngoài hai biến thể `orElseThrow`, nó minh họa mapper/filter và lazy supplier.

~~~java
import java.util.NoSuchElementException;
import java.util.Optional;
import java.util.concurrent.atomic.AtomicInteger;

public class OptionalEmptyVsFailureDemo {

    static final class MissingItemException extends RuntimeException {
        MissingItemException(int id) {
            super("item " + id + " not found");
        }
    }

    static Optional<String> findLabel(int id) {
        if (id <= 0) {
            throw new IllegalArgumentException("id must be positive");
        }
        if (id == 503) {
            throw new IllegalStateException("storage unavailable");
        }
        if (id == 1) {
            return Optional.of("Java");
        }
        return Optional.empty();
    }

    static String requireLabel(int id) {
        return findLabel(id)
                .orElseThrow(() -> new MissingItemException(id));
    }

    public static void main(String[] args) {
        System.out.println("found=" + findLabel(1).orElseThrow());
        System.out.println("empty=" + findLabel(2).isEmpty());

        try {
            findLabel(2).orElseThrow();
        } catch (NoSuchElementException expected) {
            System.out.println("emptyException="
                    + expected.getClass().getSimpleName());
        }

        try {
            requireLabel(2);
        } catch (MissingItemException expected) {
            System.out.println("domainException=" + expected.getMessage());
        }

        try {
            requireLabel(0);
        } catch (IllegalArgumentException expected) {
            System.out.println("invalidInput=" + expected.getMessage());
        }

        try {
            requireLabel(503);
        } catch (IllegalStateException expected) {
            System.out.println("processingFailure=" + expected.getMessage());
        }

        var calls = new AtomicInteger();
        var present = findLabel(1).orElseThrow(() -> {
            calls.incrementAndGet();
            return new MissingItemException(1);
        });

        System.out.println("supplierValue=" + present);
        System.out.println("supplierCalls=" + calls.get());

        Optional<String> nullable = Optional.ofNullable(null);
        System.out.println("nullableEmpty=" + nullable.isEmpty());

        Optional<String> mappedNull = Optional.of("Java")
                .map(s -> (String) null);
        System.out.println("mappedNullEmpty=" + mappedNull.isEmpty());

        var filtered = Optional.of(16).filter(age -> age >= 18);
        System.out.println("filteredEmpty=" + filtered.isEmpty());

        try {
            Optional.of("Java").flatMap(s -> (Optional<String>) null);
        } catch (NullPointerException expected) {
            System.out.println("flatMapNullRejected=true");
        }

        try {
            Optional.of((String) null);
        } catch (NullPointerException expected) {
            System.out.println("ofNullRejected=true");
        }

        try {
            Optional.of("bad").map(Integer::parseInt).orElseThrow();
        } catch (NumberFormatException expected) {
            System.out.println("mapperFailurePreserved=true");
        }

        System.out.println("fallback="
                + findLabel(2).orElseGet(() -> "default"));
    }
}
~~~

Biên dịch và chạy bằng JDK 17 hoặc mới hơn có hỗ trợ Java 17:

~~~bash
javac --release 17 OptionalEmptyVsFailureDemo.java
java OptionalEmptyVsFailureDemo
~~~

**Stdout chính xác:**

~~~text
found=Java
empty=true
emptyException=NoSuchElementException
domainException=item 2 not found
invalidInput=id must be positive
processingFailure=storage unavailable
supplierValue=Java
supplierCalls=0
nullableEmpty=true
mappedNullEmpty=true
filteredEmpty=true
flatMapNullRejected=true
ofNullRejected=true
mapperFailurePreserved=true
fallback=default
~~~

### Vì sao kết quả như vậy?

1. `findLabel(1)` trả `Optional.of("Java")` và `orElseThrow()` lấy giá trị. `findLabel(2)` trả empty vì ID hợp lệ nhưng không có bản ghi.
2. `findLabel(2).orElseThrow()` ném `NoSuchElementException`. `requireLabel(2)` dùng overload có supplier nên tạo `MissingItemException` chứa ID.
3. `requireLabel(0)` ném lỗi đầu vào trước khi trả Optional; `requireLabel(503)` ném lỗi xử lý trước. Hai ngoại lệ không bị đổi thành lỗi “không có bản ghi”.
4. Supplier của `findLabel(1).orElseThrow(...)` không được gọi vì Optional present; biến đếm vẫn bằng `0`.
5. `Optional.ofNullable(null)` tạo empty. `Optional.map` cũng trả empty khi mapper trả null.
6. `filter` biến giá trị present `16` thành empty vì không đạt điều kiện tuổi, dù giá trị ban đầu tồn tại.
7. `flatMap` với mapper trả null và `Optional.of(null)` đều ném `NullPointerException`.
8. `map(Integer::parseInt)` với `"bad"` ném `NumberFormatException`, không chuyển thành Optional rỗng.
9. `orElseGet` cho `"default"` ở `findLabel(2)` vì absence là trạng thái hợp lệ. Nếu `findLabel` ném lỗi xử lý, fallback sẽ không chạy.

Đầu ra không phụ thuộc vào nội dung message mặc định của JDK; chương trình chỉ in tên class ngoại lệ `NoSuchElementException`. Không cần thư viện ngoài. `Optional.isEmpty()` có từ Java 11, nên target Java 17 đáp ứng.

## 10. Thiết kế API theo từng tầng

### Validation và repository

Ở ranh giới nhận yêu cầu, kiểm tra ID, định dạng, miền giá trị. Nếu input sai, báo lỗi cụ thể trước khi truy vấn.

Một repository có thể có hợp đồng:

~~~java
// Chữ ký minh họa của một repository trong ứng dụng:
Optional<User> findById(long id);
~~~

`User` là kiểu nghiệp vụ do ứng dụng định nghĩa. Một contract phù hợp có thể là: trả present khi tìm thấy; empty khi truy vấn thành công nhưng không có bản ghi; ném ngoại lệ truy vấn nếu hạ tầng thất bại.

### Service quyết định khi nào absence là lỗi

~~~java
// Ví dụ ngữ cảnh application service:
User user = repository.findById(id)
        .orElseThrow(() -> new UserNotFoundException(id));
~~~

`UserNotFoundException` là kiểu domain giả định; đây là đoạn minh họa không độc lập. Nếu service đang làm thao tác bắt buộc có user, absence cần được báo rõ. Nếu chỉ kiểm tra sự hiện diện, service có thể giữ `Optional<User>` mà không ném exception.

### API adapter chọn mã trả về

Trong một REST API thường gặp, có thể ánh xạ:

- ID sai thành HTTP 400.
- Tài nguyên hợp lệ nhưng không tìm thấy thành HTTP 404.
- Lỗi nội bộ thành HTTP 500, hoặc lỗi phụ thuộc tạm thời thành HTTP 503 khi phù hợp chính sách.
- Trường hợp không đủ quyền theo chính sách bảo mật tương ứng.

Đây là **lựa chọn ứng dụng**, không phải hành vi tự động của `Optional`. Không viết một `catch (Exception)` chung rồi luôn trả 404.

### Nếu cần nhiều trạng thái hơn hai

`Optional<T>` chỉ biểu diễn present/empty. Nếu caller cần tách “không tồn tại”, “bị vô hiệu”, “dữ liệu sai” và “cần thử lại”, có thể dùng một kiểu kết quả gồm nhiều trường hợp.

Ví dụ Java 17+ có **sealed interface**:

~~~java
// Các khai báo minh họa bên trong một class.
sealed interface LookupResult permits Found, Missing, Invalid {
}

record Found(String value) implements LookupResult {}
record Missing(int id) implements LookupResult {}
record Invalid(String reason) implements LookupResult {}
~~~

Mã gọi có thể phân nhánh theo kiểu kết quả và tránh nhồi mọi trạng thái vào `Optional.empty`. Đây chỉ là một mô hình khả thi; nếu ngoại lệ domain là quy ước ứng dụng thì không nhất thiết dùng sealed interface.

## 11. Test đúng: kiểm tra loại lỗi thay vì chỉ kiểm tra Optional.isEmpty

Những trường hợp tối thiểu nên có trong test:

| Đầu vào / nhánh | Kết quả cần kiểm |
| --- | --- |
| Tra cứu có bản ghi | Optional present; `orElseThrow` trả đúng giá trị |
| Tra cứu hợp lệ không có bản ghi | Optional empty, không tự coi là processing failure |
| Bắt buộc có bản ghi nhưng thiếu | `orElseThrow` ném đúng domain exception |
| ID ngoài miền hợp lệ | Validation error, không thành Optional.empty |
| Repository ném ngoại lệ xử lý | Lỗi được giữ/chuyển có cause, không thành absence |
| Mapper trả null trái hợp đồng | Không bị che mất khi cần phát hiện lỗi dữ liệu |
| Filter thất bại | Có thể phân biệt không đạt điều kiện với không tồn tại |
| Exception supplier khi Optional present | Không được gọi |
| Optional.of(null) hoặc flatMap trả null | Ném `NullPointerException` theo Javadoc |
| Parser trong mapper ném exception | Ngoại lệ lan ra, không tự biến thành empty |

**Đừng quá phụ thuộc vào văn bản thông báo mặc định của `NoSuchElementException`.** Với unit test, kiểm **loại ngoại lệ**, còn thông điệp ổn định cho người dùng nên được tự thiết kế trong ngoại lệ domain.

Nếu dùng JUnit, có thể kiểm `assertThrows` cho các lỗi riêng, nhưng ví dụ hoàn chỉnh không yêu cầu bất kỳ thư viện kiểm thử nào.

### Logging và giám sát

- **Absence hợp lệ:** có thể đo theo số lượt tìm kiếm không ra kết quả, nhưng không nhất thiết coi là lỗi hệ thống.
- **Validation failure:** cần chỉ rõ trường và quy tắc sai, không ghi dữ liệu nhạy cảm không cần thiết.
- **Processing failure:** nên giữ cause, loại lỗi và đủ bối cảnh để phân biệt tình huống retry, lỗi mã hoặc lỗi dữ liệu.
- **Không che lỗi:** nếu catch exception để bọc lỗi, nên giữ cause và ném/hoàn trả kiểu lỗi mới rõ ràng; tránh trả `Optional.empty()` khi không có chính sách cho việc ấy.

## 12. Lỗi thường gặp và checklist

| Phản mẫu | Vấn đề | Cách sửa |
| --- | --- | --- |
| `catch (Exception ex) { return Optional.empty(); }` | Che toàn bộ lỗi thành “không tìm thấy” | Tách exception xử lý với absence hợp lệ |
| `ofNullable(requiredValue)` khi contract non-null | Bug null thành empty | Kiểm tra invariant bằng `Objects.requireNonNull` |
| `optional.map(x -> null)` rồi kết luận bản ghi không tồn tại | `map` biến null result thành empty | Kiểm tra mapper và hợp đồng dữ liệu |
| `findUser(id).filter(User::active)` rồi ném NotFound | User inactive bị coi là missing | Phân biệt tra cứu với kiểm trạng thái |
| `orElse("fake")` cho dữ liệu bắt buộc | Fallback che lỗi thiếu giá trị | Dùng `orElseThrow` hoặc result lỗi rõ |
| `orElse(expensiveDefault())` và nghĩ lazy | Đối số được tính ngay | Dùng `orElseGet` |
| Bắt `NoSuchElementException` ở phạm vi quá rộng | Ngoại lệ cũng có thể phát sinh từ mã khác | Dùng loại exception domain hoặc catch quanh lời gọi cụ thể |
| Giả định `orElseThrow(Supplier)` bắt lỗi từ repository | Lỗi trước khi có Optional lan ra | Giữ xử lý validation/processing riêng |
| Trả null từ phương thức công bố `Optional<T>` | Caller sẽ lỗi khi gọi method trên null | Luôn trả Optional không null theo contract |
| Dùng `==` để xác định hai Optional.empty giống nhau | Optional là value-based class, identity không có cam kết | Dùng `isEmpty`/`isPresent` |

### Checklist trước khi công bố API

1. Đã định nghĩa rõ `Optional.empty()` có nghĩa gì chưa?
2. Có trường hợp lỗi validation mà bị gộp nhầm vào empty không?
3. Có exception xử lý nào bị catch rồi bỏ qua không?
4. Mapper hoặc `ofNullable` có biến null trái hợp đồng thành absence không?
5. `filter` có khiến hai trạng thái nghiệp vụ khác nhau thành một empty không?
6. Caller nên dùng fallback hay cần bắt buộc có kết quả?
7. Nếu cần exception, đã chọn overload `orElseThrow` và loại ngoại lệ thích hợp chưa?
8. Có cần mô hình nhiều trạng thái như sealed result type không?
9. Test đã tách present, empty, invalid, processing failure và mapper error chưa?
10. Có đang dùng API hợp lệ trên Java target? `orElseThrow()` từ 10, `isEmpty()` từ 11, Java 17+ đáp ứng đầy đủ.

### Tự đánh giá

**Câu 1.** `Optional.empty().orElseThrow()` ném ngoại lệ gì?

**Đáp án:** `NoSuchElementException`; không nói nguyên nhân khiến Optional rỗng.

**Câu 2.** Nếu ID hợp lệ không có bản ghi, trả `Optional.empty()` có sai không?

**Đáp án:** Không, nếu hợp đồng coi absence là kết quả bình thường.

**Câu 3.** Một truy vấn bị timeout có nên catch rồi trả empty?

**Đáp án:** Thông thường không. Đó là lỗi xử lý cần được giữ/báo riêng, trừ trường hợp có chính sách rõ ràng khác.

**Câu 4.** `Optional.ofNullable(null)` và `Optional.of(null)` có giống nhau?

**Đáp án:** Không. `ofNullable(null)` trả empty; `of(null)` ném `NullPointerException`.

**Câu 5.** `Optional.of("Java").map(s -> (String)null)` cho kết quả gì?

**Đáp án:** Empty. `map` bọc kết quả qua quy tắc tương tự `ofNullable`.

**Câu 6.** `Optional.of(16).filter(a -> a>=18)` rỗng có nghĩa user không tồn tại?

**Đáp án:** Không. Dữ liệu `16` hiện diện nhưng không đạt predicate.

**Câu 7.** Với Optional present, nhà cung cấp ngoại lệ của `orElseThrow(Supplier)` có được gọi không?

**Đáp án:** Không, vì supplier chỉ được gọi khi empty.

**Câu 8.** `findLabel(503).orElseThrow(() -> new MissingItemException(503))` có chắc ném MissingItemException?

**Đáp án:** Không. Nếu `findLabel` ném lỗi xử lý trước khi trả Optional, lỗi ấy lan ra trước; supplier không chạy.

**Câu 9.** `Optional.get()` còn tồn tại trên Java 17+ không?

**Đáp án:** Có. Javadoc khuyến nghị `orElseThrow()` thay cho `get()` để nêu rõ khả năng ném exception.

**Câu 10.** Cần diễn đạt “không tồn tại”, “dữ liệu sai”, “bị khóa” và “lỗi backend” cùng lúc bằng một Optional có đủ không?

**Đáp án:** Không. Optional chỉ có present/empty, cần ngoại lệ phân loại rõ hoặc kiểu kết quả có nhiều nhánh.

## 13. Tài liệu chính thức còn áp dụng

- [Oracle Java SE 26 — Optional](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Optional.html): hợp đồng `empty`/`present`, `orElseThrow()`, `orElseThrow(Supplier)`, `ofNullable`, `map`, `filter`, `flatMap` và `isEmpty`.
- [Oracle Java SE 17 — Optional](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Optional.html): API tương ứng với chương trình Java 17+.
- [Oracle Java SE 10 — Optional](https://docs.oracle.com/javase/10/docs/api/java/util/Optional.html): xác nhận `orElseThrow()` không tham số đã có từ Java 10.
- [Dev.java — Using Optionals](https://dev.java/learn/api/streams/optionals/): hướng dẫn cách dùng `Optional`, chọn `orElseThrow`, `orElseGet` và xử lý empty.
- [Oracle Java SE 17 — NoSuchElementException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/NoSuchElementException.html): loại ngoại lệ từ `orElseThrow()` không tham số khi empty.
- [Oracle Java SE 17 — Objects.requireNonNull](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Objects.html#requireNonNull(T,java.lang.String)): kiểm tra null khi một giá trị theo contract bắt buộc non-null.

**Ghi nhớ:** `Optional.empty()` chỉ nói **không có giá trị**, không tự ghi nhận lý do. `Optional.orElseThrow()` (Java 10+) ném `NoSuchElementException` khi empty; overload nhận `Supplier` cho phép ngoại lệ phù hợp nghiệp vụ. Để hệ thống đáng tin cậy, phải phân biệt **vắng mặt hợp lệ**, **dữ liệu/đầu vào sai** và **lỗi xử lý** tại điểm sinh ra chúng; không âm thầm biến tất cả thành empty.