# Trạng thái lỗi, null và đệ quy theo đặc tả Java 27

Trong Java 27, `java.lang.LazyConstant<T>` có bốn trạng thái cần phân biệt khi gọi `get()`: chưa khởi tạo, đang tính toán, đã khởi tạo và trạng thái lỗi. Nếu hàm tính toán trả về giá trị khác `null`, hằng được khởi tạo và mọi lần `get()` sau trả về cùng nội dung. Nếu hàm tính toán ném unchecked exception, trả về `null` hoặc gọi đệ quy chính lazy constant đang được khởi tạo, hằng chuyển sang trạng thái lỗi. Trạng thái lỗi là kết thúc: hàm tính toán không được chạy lại và các lần `get()` tiếp theo ném `NoSuchElementException`.

Đây là hợp đồng của **Lazy Constants (Third Preview)** trong JDK 27, JEP 531. API vẫn là preview, không phải tính năng Java SE ổn định. Nội dung bài tập trung vào quy tắc lỗi, null và đệ quy trong Java 27; cần dùng JDK 27 và bật preview ở cả lúc biên dịch lẫn chạy. [JEP 531](https://openjdk.org/jeps/531) · [JDK 27 Release Notes](https://www.oracle.com/java/technologies/javase/27-relnote-issues.html) · [Java 27 `LazyConstant` API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/LazyConstant.html) · [Lazy Constants — Java 27 Core Libraries](https://docs.oracle.com/en/java/javase/27/core/lazy-constants.html).

## 1. Vòng đời và trạng thái của một lazy constant

`LazyConstant.of(Supplier<? extends T>)` tạo một holder chưa có nội dung. Hàm `Supplier` chỉ được gọi khi có lần `get()` đầu tiên. Sau khi tính toán thành công, nội dung không thể thay đổi; JVM có thể tối ưu các lần đọc sau như đối với một hằng.

Tính bất biến ở đây áp dụng cho **liên kết giữa lazy constant và object được giữ**: không thể thay object sau khi khởi tạo. Object đó vẫn có thể mutable, ví dụ một `ArrayList`; thay đổi phần tử của object không làm lazy constant quay lại trạng thái chưa khởi tạo.

| Trạng thái | Điều gì xảy ra | Hành vi của `get()` |
|---|---|---|
| **Chưa khởi tạo** | Supplier chưa được gọi; chưa có nội dung. | Lần gọi đầu tiên bắt đầu tính toán. |
| **Đang tính toán** | Một thread được chọn chạy supplier. Các thread cạnh tranh chờ kết quả. | Thread đang tính toán thực hiện supplier; thread khác đợi cho đến khi thành công hoặc thất bại. |
| **Đã khởi tạo** | Supplier trả về một giá trị khác `null`; nội dung trở thành bất biến. | Trả về cùng nội dung đã được khởi tạo, không gọi supplier lần nữa. |
| **Lỗi** | Supplier ném unchecked exception, trả về `null`, hoặc phát hiện lời gọi đệ quy. | Lần gây lỗi ném `NoSuchElementException` có cause; các lần sau tiếp tục ném `NoSuchElementException` và không tính toán lại. |

Có thể hình dung luồng trạng thái như sau:

```text
             get() đầu tiên
  Chưa khởi tạo ----------------> Đang tính toán
                                      |
                   +------------------+------------------+
                   |                                     |
             trả về khác null                unchecked exception / null /
                   |                         recursive invocation
                   v                                     v
             Đã khởi tạo                              Trạng thái lỗi
                   |                                     |
             get() sau: value                    get() sau: NoSuchElementException
```

Điểm khác biệt quan trọng là trạng thái lỗi không giống trạng thái chưa khởi tạo. Một hằng ở trạng thái chưa khởi tạo vẫn có thể bắt đầu lần tính toán đầu tiên. Một hằng đã ở trạng thái lỗi sẽ không thử lại supplier, kể cả khi nguyên nhân lỗi ban đầu có thể đã biến mất.

## 2. Supplier ném unchecked exception: lỗi được ghi nhớ

Supplier có kiểu `Supplier<? extends T>`, nên phương thức `get()` của nó không khai báo checked exception. Các lỗi được xử lý theo hợp đồng này là unchecked exception, bao gồm `RuntimeException` và `Error`.

Khi supplier ném unchecked exception:

1. Lazy constant không được khởi tạo nội dung.
2. Lazy constant chuyển sang trạng thái lỗi.
3. Lần `LazyConstant.get()` gây ra lỗi ném `NoSuchElementException`; unchecked exception ban đầu được đặt làm `cause`.
4. Mọi lần `get()` tiếp theo tiếp tục ném `NoSuchElementException`, không gọi supplier nữa. Các exception ở những lần sau không có cause; thông báo có tên lớp của unchecked exception ban đầu.

Ví dụ:

```java
import java.util.NoSuchElementException;
import java.util.concurrent.atomic.AtomicInteger;
import java.lang.LazyConstant;

public class LazyFailureExample {
    public static void main(String[] args) {
        AtomicInteger attempts = new AtomicInteger();

        LazyConstant<String> config = LazyConstant.of(() -> {
            attempts.incrementAndGet();
            throw new IllegalStateException("configuration service unavailable");
        });

        for (int i = 1; i <= 2; i++) {
            try {
                config.get();
            } catch (NoSuchElementException ex) {
                System.out.println("Call " + i + ": " + ex.getClass().getSimpleName());
                System.out.println("Cause: " + ex.getCause());
            }
        }

        System.out.println("Supplier attempts: " + attempts.get());
    }
}
```

Kết quả cần hiểu:

- Lần gọi đầu tiên ném `NoSuchElementException` có cause là `IllegalStateException` với thông báo lỗi ban đầu.
- Lần gọi thứ hai cũng ném `NoSuchElementException`, nhưng không có cause và supplier không chạy lại.
- `attempts` bằng `1`, không phải `2`.

Không bắt riêng `IllegalStateException` ở phía gọi để chờ nó xuất hiện trực tiếp từ `config.get()`: Java 27 chuyển lỗi tính toán thành `NoSuchElementException` và giữ exception ban đầu trong `getCause()`. Nếu cần ghi log nguyên nhân, hãy ghi cả exception ngoài lẫn cause.

```java
try {
    config.get();
} catch (NoSuchElementException failure) {
    Throwable cause = failure.getCause();
    if (cause != null) {
        System.err.println("Lazy initialization failed: " + cause);
    } else {
        System.err.println("Lazy constant is already in an error state: "
                + failure.getMessage());
    }
}
```

Cause chỉ có ở lần lỗi đầu tiên theo cách xử lý được mô tả trong API. Vì vậy, nếu cần chẩn đoán nguyên nhân gốc, hãy ghi nhận exception ngay lần đầu; không dựa vào một lần `get()` bất kỳ về sau để lấy lại stack trace ban đầu.

## 3. Supplier trả về `null`

Lazy constant không thể chứa `null`. Khi supplier trả về `null`, lần `get()` đó ném `NoSuchElementException` với một `NullPointerException` làm cause. Lazy constant chuyển sang trạng thái lỗi; lần `get()` sau không gọi supplier lần nữa và tiếp tục ném `NoSuchElementException`.

```java
import java.util.NoSuchElementException;
import java.lang.LazyConstant;

public class LazyNullExample {
    public static void main(String[] args) {
        LazyConstant<String> name = LazyConstant.of(() -> null);

        try {
            name.get();
        } catch (NoSuchElementException ex) {
            System.out.println(ex.getCause() instanceof NullPointerException);
        }

        try {
            name.get();
        } catch (NoSuchElementException ex) {
            System.out.println(ex.getCause()); // null: lần gọi sau không có cause
        }
    }
}
```

Phân biệt hai trường hợp null:

| Tình huống | Kết quả |
|---|---|
| Truyền `null` thay cho supplier vào `LazyConstant.of(...)` | Factory ném `NullPointerException` ngay khi tạo lazy constant. Chưa có lazy constant nào được tạo để chuyển trạng thái. |
| Supplier hợp lệ nhưng trả về `null` khi `get()` gọi nó | Lazy constant chuyển sang trạng thái lỗi; lần `get()` đầu ném `NoSuchElementException` có cause `NullPointerException`. |

### Khi kết quả nghiệp vụ có thể vắng mặt

Nếu `null` có ý nghĩa nghiệp vụ, hãy bọc nó trong một holder khác null, thường là `Optional<T>`. `Optional.empty()` là một đối tượng hợp lệ nên lazy constant có thể lưu nó:

```java
import java.util.Optional;
import java.lang.LazyConstant;

LazyConstant<Optional<UserProfile>> profile = LazyConstant.of(
        () -> Optional.ofNullable(repository.findProfile(userId))
);

Optional<UserProfile> result = profile.get();
if (result.isPresent()) {
    System.out.println(result.orElseThrow().displayName());
} else {
    System.out.println("Profile does not exist");
}
```

Ở đây supplier luôn trả về một `Optional` khác null. Giá trị không tồn tại được biểu diễn bằng `Optional.empty()`, không biến lazy constant thành trạng thái lỗi. Cách này tách rõ “đã tính thành công và không có kết quả” với “không thể tính toán thành công”.

## 4. Đệ quy trực tiếp và gián tiếp

Một supplier không được gọi lại `get()` trên chính lazy constant đang chạy supplier đó. Nếu điều này xảy ra trực tiếp hoặc thông qua một chuỗi phụ thuộc, API phát hiện lời gọi đệ quy. Lần `get()` gây ra đệ quy ném `NoSuchElementException` với `IllegalStateException` làm cause và lazy constant chuyển sang trạng thái lỗi.

### Đệ quy trực tiếp

Ví dụ sau minh họa một supplier tự yêu cầu nội dung của chính lazy constant:

```java
import java.util.NoSuchElementException;
import java.lang.LazyConstant;

public class DirectRecursionExample {
    private static final LazyConstant<String> VALUE =
            LazyConstant.of(() -> DirectRecursionExample.VALUE.get());

    public static void main(String[] args) {
        try {
            VALUE.get();
        } catch (NoSuchElementException ex) {
            System.out.println(ex.getCause() instanceof IllegalStateException);
        }
    }
}
```

Lần `VALUE.get()` đầu bắt đầu chạy supplier. Supplier gọi `VALUE.get()` lần nữa trong khi lần tính toán đầu vẫn chưa hoàn tất. Đây là recursive invocation, không phải một lần đọc nội dung đã khởi tạo. Java 27 phát hiện tình huống này và báo lỗi theo hợp đồng của `LazyConstant`.

### Đệ quy gián tiếp qua dependency graph

Đệ quy cũng có thể xuất hiện khi hai hoặc nhiều lazy constant phụ thuộc vòng tròn:

```text
LazyConstant A
      |
      v
LazyConstant B
      |
      v
LazyConstant C
      |
      +----------> LazyConstant A
```

Ví dụ, supplier của `A` gọi `B.get()`, supplier của `B` gọi `C.get()`, và supplier của `C` gọi `A.get()`. Khi quay lại `A` trước khi lần khởi tạo ban đầu hoàn tất, API phát hiện đệ quy. Những lazy constant ở phía ngoài cũng có thể chuyển sang trạng thái lỗi khi supplier của chúng thoát ra bằng unchecked exception do dependency bên trong ném.

Một dependency graph một chiều là hợp lệ:

```java
static final LazyConstant<DatabaseConfig> DATABASE =
        LazyConstant.of(DatabaseConfig::load);

static final LazyConstant<ServiceClient> CLIENT =
        LazyConstant.of(() -> new ServiceClient(DATABASE.get()));
```

`CLIENT` phụ thuộc `DATABASE`, nhưng `DATABASE` không gọi ngược `CLIENT`. Khi `CLIENT.get()` được gọi lần đầu, `DATABASE` được khởi tạo trước nếu chưa có. Hãy thiết kế các dependency theo một chiều hoặc phá vòng phụ thuộc bằng cách tách phần dữ liệu chung thành một lazy constant độc lập.

## 5. Phân biệt đệ quy LazyConstant với chu trình khởi tạo class

Có hai loại chu trình có thể xuất hiện trong code dùng static lazy constants:

| Loại chu trình | Nguyên nhân | Cách hiểu |
|---|---|---|
| Recursive invocation của `LazyConstant` | Supplier đang tính toán gọi trực tiếp hoặc gián tiếp `get()` trên chính lazy constant đó. | API phát hiện đệ quy và ném `NoSuchElementException` với `IllegalStateException` làm cause; lazy constant đi vào trạng thái lỗi. |
| Chu trình khởi tạo class/interface | Các static field initializer hoặc static initializer của nhiều class phụ thuộc vòng tròn vào thứ tự khởi tạo class. | Được điều chỉnh bởi quy tắc khởi tạo class tại JLS §12.4; có thể gây lỗi khởi tạo class độc lập với cơ chế phát hiện đệ quy của `LazyConstant`. |

Javadoc Java 27 cảnh báo rằng việc dùng lazy constant trong static initializer có thể tương tác với thứ tự khởi tạo class. Do đó, không nên xem mọi lỗi liên quan đến dependency vòng tròn là cùng một exception. Hãy xác định stack trace cho biết lỗi xảy ra khi `LazyConstant.get()` phát hiện recursive invocation hay trong quá trình JVM khởi tạo class.

## 6. Lỗi có được thử lại không?

Không. Trong Java 27, một lazy constant chỉ được tính tối đa một lần. Khi supplier thất bại, lazy constant ghi nhớ trạng thái lỗi. Không có thao tác reset để chuyển nó về trạng thái chưa khởi tạo; gọi `get()` lại không chạy supplier lần nữa.

Điều này có ảnh hưởng trực tiếp đến cách thiết kế supplier:

- Không dùng lazy constant cho một thao tác vốn thường xuyên thất bại tạm thời và cần tự động thử lại ở lần truy cập tiếp theo.
- Nếu việc tạo nội dung cần retry, hãy thực hiện chính sách retry có giới hạn ngay bên trong supplier trước khi supplier trả kết quả hoặc ném exception cuối cùng.
- Nếu retry vẫn thất bại và supplier ném unchecked exception, lazy constant chuyển sang trạng thái lỗi vĩnh viễn.
- Nếu cần thử lại sau một khoảng thời gian hoặc sau khi cấu hình thay đổi, hãy dùng một cơ chế quản lý vòng đời có hỗ trợ retry/reset phù hợp; `LazyConstant` không phải cache có thời hạn hoặc một future có thể reset.
- Tránh để supplier phụ thuộc vào dữ liệu bên ngoài có thể thay đổi sau lần tính toán đầu tiên nếu nội dung cần phản ánh thay đổi đó.

Ví dụ retry có giới hạn ngay bên trong supplier:

```java
static String loadWithBoundedRetry() {
    RuntimeException lastFailure = null;

    for (int attempt = 1; attempt <= 3; attempt++) {
        try {
            return remoteConfigService().load();
        } catch (TemporaryServiceException ex) { // extends RuntimeException
            lastFailure = ex;
        }
    }

    throw new IllegalStateException("Cannot load configuration after 3 attempts",
            lastFailure);
}

static final LazyConstant<String> CONFIG =
        LazyConstant.of(MyApplication::loadWithBoundedRetry);
```

Trong ví dụ, supplier tự xử lý tối đa ba lần thử. Nếu cuối cùng vẫn thất bại, exception cuối cùng được chuyển thành nguyên nhân của lỗi trạng thái lazy constant. Không nên đặt vòng retry vô hạn trong supplier vì thread đầu tiên có thể giữ các thread khác chờ vô thời hạn.

## 7. Tính đồng thời khi có lỗi

Lazy constant được khởi tạo nguyên tử và tối đa một lần. Khi nhiều thread gọi `get()` cùng lúc:

1. Chỉ một thread được chọn chạy supplier; đây là computing thread.
2. Các thread còn lại chờ cho đến khi quá trình tính toán thành công hoặc thất bại.
3. Nếu thành công, các thread nhận cùng nội dung đã khởi tạo.
4. Nếu thất bại, các thread quan sát trạng thái lỗi; không thread nào được chạy supplier lần nữa.

Việc supplier chạy và nội dung được khởi tạo có quan hệ happens-before với việc đọc nội dung đã khởi tạo. Điều này bảo đảm safe publication cho nội dung, bao gồm các `final` field của đối tượng mới tạo. Khi supplier thất bại, không có nội dung hợp lệ để publish; các thread chờ sẽ thấy trạng thái lỗi theo hợp đồng API.

Thread bị interrupt không làm hủy quá trình khởi tạo: `LazyConstant.get()` không xóa interrupt status và không ném `InterruptedException`. Nếu supplier bị block vô thời hạn, các thread khác đang chờ cùng lazy constant cũng có thể bị block vô thời hạn. API không cung cấp timeout hoặc cancellation cho lần khởi tạo.

Vì vậy, supplier nên có thời gian thực thi hữu hạn và xử lý rõ timeout ở các thao tác I/O bên trong. Đừng dùng `LazyConstant` để giữ một tác vụ mạng không giới hạn thời gian nếu nhiều thread quan trọng sẽ cùng chờ `get()`.

## 8. Thay đổi quan trọng từ Java 26 sang Java 27

Đặc tả Java 26 và Java 27 mô tả hành vi lỗi khác nhau. Java 26 là lần preview thứ hai (JEP 526); Java 27 là lần preview thứ ba (JEP 531). Khi code theo JDK 27, phải tuân thủ hợp đồng Java 27:

| Trường hợp | Java 26 — Second Preview | Java 27 — Third Preview |
|---|---|---|
| Supplier ném unchecked exception | Throwable được chuyển trực tiếp tới caller; lazy constant vẫn chưa khởi tạo và lần `get()` sau có thể thử lại. | Lazy constant chuyển sang trạng thái lỗi; lần đầu ném `NoSuchElementException` có cause là unchecked exception ban đầu; lần sau không chạy lại supplier. |
| Supplier trả về `null` | Ném `NullPointerException`; lazy constant vẫn chưa khởi tạo. | Ném `NoSuchElementException` có cause là `NullPointerException`; lazy constant chuyển sang trạng thái lỗi. |
| Supplier gọi đệ quy `get()` | Ném `IllegalStateException`; lazy constant vẫn chưa khởi tạo. | Ném `NoSuchElementException` có cause là `IllegalStateException`; lazy constant chuyển sang trạng thái lỗi. |
| Quan sát trạng thái | Preview API có `isInitialized()` và `orElse(...)`. | Hai phương thức `isInitialized()` và `orElse(...)` đã bị loại khỏi API preview Java 27. |

Không mang giả định retry của JDK 26 sang JDK 27. Cũng không viết code mới dựa trên `isInitialized()` hoặc `orElse(...)` của preview Java 26: hai phương thức này không còn trong API Java 27. Nếu cần biểu diễn kết quả có thể vắng mặt, dùng `Optional` làm nội dung; nếu cần biết trạng thái, thiết kế API ở lớp ứng dụng thay vì dựa vào các phương thức preview đã bị loại bỏ.

## 9. Cách biên dịch và chạy trên JDK 27

`LazyConstant` thuộc package `java.lang` và module `java.base`. Không cần import bắt buộc cho `java.lang`, cũng không cần `--add-modules`. Tuy nhiên, vì đây là preview API, compiler và runtime đều phải bật preview:

```bash
# Dùng JDK 27 để biên dịch
javac --release 27 --enable-preview -d out src/LazyFailureExample.java

# Chạy bằng JDK 27 và bật preview
java --enable-preview -cp out LazyFailureExample
```

Không dùng class file đã biên dịch với preview của Java 26 để chạy trên Java 27. Preview được gắn với release cụ thể; hãy biên dịch lại bằng JDK 27. Trước khi sử dụng trong ứng dụng, kiểm tra lại preview status trong JDK mục tiêu vì API có thể tiếp tục thay đổi hoặc bị rút lại.

## 10. Checklist xử lý lỗi LazyConstant

- [ ] Đã xác nhận đang đọc Javadoc của đúng JDK 27, không áp dụng nhầm semantics của preview Java 26.
- [ ] Đã phân biệt lỗi do supplier ném exception, supplier trả `null`, factory nhận supplier `null` và recursive invocation.
- [ ] Đã bắt `NoSuchElementException` từ `get()` và đọc `getCause()` để ghi nhận nguyên nhân đầu tiên.
- [ ] Đã hiểu các lần `get()` sau lỗi không chạy lại supplier và exception sau không còn cause.
- [ ] Đã dùng `Optional` hoặc holder khác null khi kết quả nghiệp vụ có thể vắng mặt.
- [ ] Đã kiểm tra dependency graph để tránh vòng phụ thuộc trực tiếp hoặc gián tiếp.
- [ ] Đã phân biệt recursive invocation với lỗi do thứ tự khởi tạo class tại JLS §12.4.
- [ ] Đã quyết định retry ở bên trong supplier hoặc dùng cơ chế khác nếu cần retry sau khi lazy constant đã lỗi.
- [ ] Đã bảo đảm supplier không block vô thời hạn và hiểu interrupt không hủy khởi tạo.
- [ ] Đã loại bỏ sự phụ thuộc vào `isInitialized()` và `orElse(...)` của Java 26 preview.
- [ ] Đã bật `--enable-preview` ở cả biên dịch và chạy với cùng JDK 27.

## Tài liệu tham khảo chính thức

- [Java SE 27 — `LazyConstant`](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/LazyConstant.html)
- [Java SE 27 — Lazy Constants, Core Libraries](https://docs.oracle.com/en/java/javase/27/core/lazy-constants.html)
- [JDK 27 Release Notes — Lazy Constants (Third Preview)](https://www.oracle.com/java/technologies/javase/27-relnote-issues.html)
- [JDK 27 Significant Changes — Lazy Constants](https://docs.oracle.com/en/java/javase/27/migrate/significant-changes-jdk-27-release.html)
- [Java SE 26 — `LazyConstant` (Second Preview)](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/LazyConstant.html)
- [Java SE 26 — Preview API List](https://docs.oracle.com/en/java/javase/26/docs/api/preview-list.html)
- [JLS §12.4 — Initialization of Classes and Interfaces](https://docs.oracle.com/javase/specs/jls/se27/html/jls-12.html#jls-12.4)
- [JLS §17.4.5 — Happens-before Order](https://docs.oracle.com/javase/specs/jls/se27/html/jls-17.html#jls-17.4.5)
- [The `javac` Command — JDK 27](https://docs.oracle.com/en/java/javase/27/docs/specs/man/javac.html)

*Cập nhật nội dung: 27-11-2026. Lazy Constants vẫn là preview lần thứ ba trong Java 27; exception, null và recursion phải được xử lý theo hợp đồng Java 27 trước khi nâng cấp sang preview hoặc release tiếp theo.*
