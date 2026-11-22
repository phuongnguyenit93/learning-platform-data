# Kiểm tra đầu vào bằng `Objects.requireNonNull` (Java 7+)

> **Bối cảnh:** `java.util.Objects` là lớp tiện ích có từ Java 7. `Objects.requireNonNull(...)` được thiết kế chủ yếu để xác minh **tham chiếu bắt buộc không được `null`** ở ranh giới của method, constructor và các đối tượng chứa dữ liệu. Khi hợp đồng không chấp nhận `null`, phương thức báo lỗi **ngay tại nơi nhận tham số**, thay vì để `NullPointerException` phát sinh khó hiểu nhiều bước sau. Hai overload cơ bản có từ Java 7 vẫn được sử dụng trong Java 17+; overload dùng `Supplier<String>` có từ Java 8. Đây là kiến thức hiện hành, không phải cách làm legacy.

## 1. Vấn đề: phát hiện `null` tại ranh giới, không chờ lỗi lan xa

Giả sử method nhận tên người dùng bắt buộc:

```java
static String greet(String username) {
    return "Hello, " + username.trim();
}
```

Đây là **snippet đặt trong class Java**, không phải chương trình độc lập. Nếu `username == null`, lời gọi `trim()` có thể tạo `NullPointerException` ở giữa logic. Caller sẽ phải lần theo stack trace để biết tham số nào đáng lẽ không được null.

Đưa điều kiện vào đầu method:

```java
import java.util.Objects;

static String greet(String username) {
    Objects.requireNonNull(username, "username must not be null");
    return "Hello, " + username.trim();
}
```

Đây vẫn là **snippet trong class**. Nếu tham số null, method ném `NullPointerException` với message rõ ràng tại bước kiểm tra. Nếu không null, code tiếp tục như bình thường. Nó không thay đổi giá trị username, không thay `trim()` và không tự kiểm tra tên rỗng.

**Fail-fast** ở đây nghĩa là: khi caller vi phạm hợp đồng “không nhận null”, hệ thống phát hiện sớm và rõ ràng. Nó **không** có nghĩa mọi lỗi nghiệp vụ cần được mô tả bằng `NullPointerException`, và cũng không có nghĩa mỗi biểu thức Java đều phải bọc bằng `requireNonNull`.

## 2. API chính và kết quả chính xác

Các chữ ký cần biết:

```java
public static <T> T requireNonNull(T obj);
public static <T> T requireNonNull(T obj, String message);
public static <T> T requireNonNull(T obj, Supplier<String> messageSupplier);
```

Đây là **chữ ký rút gọn để học API** từ `java.util.Objects`, không phải ba method được khai báo lại trong dự án. `Supplier` là `java.util.function.Supplier`.

| Overload | Phiên bản có từ | Khi `obj != null` | Khi `obj == null` |
| --- | --- | --- | --- |
| `requireNonNull(obj)` | Java 7 | Trả lại chính `obj` | Ném `NullPointerException` |
| `requireNonNull(obj, "message")` | Java 7 | Trả lại chính `obj` | Ném `NullPointerException` kèm message truyền vào |
| `requireNonNull(obj, () -> "message")` | Java 8 | Trả lại chính `obj`, không gọi supplier để tạo message | Gọi supplier lấy message rồi ném `NullPointerException` |

**Ba điều quan trọng:**

1. Đây là **generic method**: tham số kiểu `T` và giá trị trả về cũng là `T`. Khi đầu vào hợp lệ, không cần cast thủ công.
2. Nó **trả về đúng object đã nhận**, không tạo clone, không chuyển đổi dữ liệu và không thay đổi trạng thái object.
3. Với đầu vào `null`, nó **ném exception**, không trả về `null` và không trả về giá trị mặc định.

### 2.1. `requireNonNull` khác `Objects.nonNull`

`Objects.nonNull(x)` trả về `boolean` để kiểm tra điều kiện (Java 8+); `Objects.requireNonNull(x)` hoặc trả `x` hoặc **ném lỗi**. Hai API phục vụ mục tiêu khác nhau:

```java
if (Objects.nonNull(value)) {
    // Xử lý khi value khác null.
}

String required = Objects.requireNonNull(value, "value required");
```

Đây là **snippet** với `String value` đã khai báo. Dùng `nonNull` khi một nhánh tùy chọn là hợp lệ. Dùng `requireNonNull` khi `null` là **vi phạm hợp đồng của method/constructor**.

`Objects.isNull(x)` cũng trả boolean ngược lại, thường hữu ích khi dùng method reference trong stream. Không chọn chúng thay `requireNonNull` nếu mục tiêu là **bắt buộc có giá trị**.

## 3. Ví dụ đầy đủ: tham số bắt buộc và constructor

Lưu thành `RequireNonNullBasicsDemo.java`:

```java
import java.util.Objects;

public class RequireNonNullBasicsDemo {
    static final class UserProfile {
        private final String username;

        UserProfile(String username) {
            this.username = Objects.requireNonNull(
                    username, "username must not be null");
        }

        String greet() {
            return "Hello, " + username;
        }
    }

    static String normalize(String input) {
        String checked = Objects.requireNonNull(input, "input required");
        return checked.trim();
    }

    public static void main(String[] args) {
        String text = " java ";
        String same = Objects.requireNonNull(text, "text required");
        System.out.println("sameReference=" + (same == text));
        System.out.println("normalized=" + normalize(text));
        System.out.println(new UserProfile("Lan").greet());

        try {
            new UserProfile(null);
        } catch (NullPointerException error) {
            System.out.println("error=" + error.getMessage());
        }
    }
}
```

Chạy trên JDK 17+:

```bash
javac -encoding UTF-8 --release 17 RequireNonNullBasicsDemo.java
java RequireNonNullBasicsDemo
```

Stdout **đã xác minh bằng biên dịch và chạy**:

```text
sameReference=true
normalized=java
Hello, Lan
error=username must not be null
```

Giải thích:

- `Objects.requireNonNull(text, ...)` trả về **cùng tham chiếu** nên `same == text` là `true`.
- `normalize` kiểm tra trước rồi mới `trim()`. Thao tác trim làm thay đổi chuỗi kết quả, **không phải** `requireNonNull`.
- `UserProfile` dùng `Objects.requireNonNull` ngay khi gán field `final`. Vì vậy một instance được xây dựng thành công luôn có field username khác null, miễn là các invariant khác không bị phá vỡ qua cơ chế bên ngoài.
- Truyền `null` vào constructor ném `NullPointerException` có message do lập trình viên cung cấp. Tên tham số được ghi vào message để người gọi biết chính xác hợp đồng bị vi phạm.
- `try/catch` trong `main` chỉ nhằm **minh họa kết quả của trường hợp lỗi**; trong ứng dụng thực tế, một API có thể để lỗi này lan lên tầng xử lý phù hợp, thay vì bắt rồi tiếp tục như không có gì xảy ra.

**Hai vị trí thường phù hợp nhất:** ngay đầu method công khai có tham số bắt buộc, và khi tạo đối tượng immutable với những field không chấp nhận null.

## 4. Cách viết gọn nhờ giá trị trả về

Vì phương thức trả lại chính tham chiếu đầu vào khi hợp lệ, các cách sau đều đúng:

```java
Objects.requireNonNull(name, "name required");
this.name = name;
```

và:

```java
this.name = Objects.requireNonNull(name, "name required");
```

Đây là **hai snippet thay thế** trong constructor có field `name`. Bản thứ hai biểu đạt rõ điều kiện ngay tại phép gán, tránh thêm dòng tạm khi không cần.

### 4.1. Generic giúp giữ đúng kiểu

```java
static <T> T requireValue(T input) {
    return Objects.requireNonNull(input, "input required");
}
```

Đây là snippet cần import `java.util.Objects`. Khi gọi với `Integer`, nó trả `Integer`; với `Customer`, trả `Customer`. Không phải ép về `Object` rồi cast trở lại.

Tuy nhiên, việc giữ kiểu **không chứng minh object bên trong hợp lệ ở mọi khía cạnh**. Một `List<String>` khác null vẫn có thể chứa phần tử null nếu list implementation cho phép. Một `User` khác null vẫn có thể có field `address == null` nếu class cho phép. `requireNonNull` chỉ kiểm tra **tham chiếu trực tiếp được truyền vào**, không thực hiện deep validation.

### 4.2. Khi nào cần biến tạm?

```java
String checkedName = Objects.requireNonNull(name, "name required");
String normalized = checkedName.strip();
```

Đây là snippet Java 11+ vì `String.strip()` được thêm từ Java 11. Biến `checkedName` có thể hữu ích khi cần giải thích giai đoạn validation và transformation riêng. Không bắt buộc tạo biến tạm cho mọi `requireNonNull`.

### 4.3. Constructor nhiều tham số

```java
public Customer(String id, String email, Address address) {
    this.id = Objects.requireNonNull(id, "id required");
    this.email = Objects.requireNonNull(email, "email required");
    this.address = Objects.requireNonNull(address, "address required");
}
```

Đây là **snippet** trong class `Customer` có các field và class `Address` phù hợp. Mỗi message xác định tham số riêng. Khi constructor có nhiều tham số cùng kiểu, thông báo có tên tham số giúp việc chẩn đoán dễ hơn; tránh đưa dữ liệu cá nhân/bí mật của tham số vào message log.

**Lưu ý thứ tự:** Java đánh giá các biểu thức theo thứ tự thực thi. Constructor dừng tại kiểm tra đầu tiên thất bại. Nếu trước các kiểm tra có side effect, chúng có thể đã xảy ra. Vì thế nên kiểm tra tham số cần thiết **trước các thao tác gây tác động lớn** như ghi file, gọi API hoặc cập nhật cơ sở dữ liệu.

## 5. Overload với chuỗi thông báo: ưu điểm và giới hạn

Cách phổ biến nhất trong code API hiện nay:

```java
Objects.requireNonNull(repository, "repository must not be null");
```

- Nếu repository khác null, phép kiểm tra thành công và object được trả về.
- Nếu null, `NullPointerException.getMessage()` nhận chuỗi do caller cung cấp.
- `message` được dùng để chẩn đoán lỗi API; **không tự trở thành response JSON**, HTTP status hay cơ chế validation UI.
- Nếu dùng overload **không có message**, bạn không nên test dựa trên một message cố định. Chi tiết message của các NullPointerException khác có thể phụ thuộc tình huống và JDK; message rõ do bạn cung cấp là lựa chọn tốt khi cần tài liệu hóa hợp đồng.

Thông báo nên **ngắn, nêu tên tham số và điều kiện**:

```text
customerId must not be null
repository is required
request must not be null
```

Tránh ghi nguyên token, mật khẩu, dữ liệu sức khỏe hoặc thông tin riêng tư trong message chỉ vì muốn debug. Các hệ thống log có thể hiển thị exception message đến nhiều bên.

### 5.1. Message không thay đổi loại ngoại lệ

Dù message là `"bad request"` hoặc `"user input invalid"`, loại ném ra vẫn là `NullPointerException`. Nếu hợp đồng API cần trả `IllegalArgumentException` cho số lượng âm, hoặc lỗi validation riêng cho dữ liệu khách hàng, bạn cần **kiểm tra điều kiện đó bằng cơ chế thích hợp**. Không thể thay exception type của `requireNonNull` bằng một message khác.

## 6. Java 8+: tạo message theo nhu cầu với `Supplier<String>`

Overload:

```java
Objects.requireNonNull(value, () -> "value must not be null");
```

sử dụng một `Supplier<String>`. Java **chỉ gọi `supplier.get()` khi tham chiếu đầu vào là null**, nên quá trình dựng message có thể được trì hoãn đến lúc thật sự xảy ra lỗi.

Lưu thành `RequireNonNullLazyDemo.java`:

```java
import java.util.Objects;
import java.util.function.Supplier;

public class RequireNonNullLazyDemo {
    public static void main(String[] args) {
        int[] evaluations = {0};
        Supplier<String> message = () -> {
            evaluations[0]++;
            return "name must not be null";
        };

        String name = Objects.requireNonNull("Lan", message);
        System.out.println("name=" + name);
        System.out.println("afterValid=" + evaluations[0]);

        try {
            Objects.requireNonNull(null, message);
        } catch (NullPointerException error) {
            System.out.println("error=" + error.getMessage());
        }
        System.out.println("afterNull=" + evaluations[0]);
    }
}
```

```bash
javac -encoding UTF-8 --release 17 RequireNonNullLazyDemo.java
java RequireNonNullLazyDemo
```

Stdout đã kiểm chứng:

```text
name=Lan
afterValid=0
error=name must not be null
afterNull=1
```

Điều này chứng minh:

1. Đầu vào `"Lan"` khác null, message supplier **không được gọi**, `evaluations[0] == 0`.
2. Đầu vào null, supplier được gọi để tạo message rồi ném NPE, nên bộ đếm tăng thành 1.
3. Không có quy tắc nào cho phép thay việc validate input bằng cách **chỉ gọi supplier**: supplier chỉ là cơ chế tạo chi tiết lỗi.

### 6.1. Khi nào nên dùng Supplier?

Nếu message có chi phí tính toán hoặc chỉ có ý nghĩa khi lỗi xảy ra, lazy message có thể hợp lý:

```java
Objects.requireNonNull(data, () -> "Missing data in stage " + stage);
```

Đây là snippet với `data` và `stage` đã có; biểu thức dựng chuỗi nằm trong lambda và chỉ thực thi khi null. Nếu message là hằng ngắn như `"data required"`, overload `String` thường đơn giản hơn.

**Chi phí không miễn phí:** việc tạo lambda/supplier cũng có thể có chi phí; tài liệu `Objects` khuyên cân nhắc chi phí tạo supplier so với trực tiếp tạo string. Đừng mặc định Supplier luôn nhanh hơn. Dùng profiler khi hiệu năng thực sự là vấn đề.

### 6.2. Không đặt side effect quan trọng vào message supplier

Nếu supplier gửi event hoặc sửa dữ liệu, side effect đó **chỉ xảy ra trên nhánh null**. Điều này dễ khiến chương trình sai nếu bạn kỳ vọng nó luôn chạy. Nên giữ supplier gần như thuần túy: chỉ xây chuỗi mô tả. Nếu supplier tự ném lỗi, exception từ supplier có thể xuất hiện thay vì NPE mong đợi — tránh làm thông báo lỗi phụ thuộc các thao tác có thể thất bại như truy vấn database.

### 6.3. Không nhầm thời điểm tạo `Supplier` với thời điểm chạy nó

Java vẫn phải **đánh giá biểu thức đối số** để truyền một supplier vào method. Nhưng phần thân lambda được hoãn đến khi `get()` được gọi. Nói “mọi thứ liên quan lambda đều không có chi phí khi input hợp lệ” là không chính xác. Điểm được hoãn là **nội dung tính toán message trong supplier**.

## 7. `requireNonNull` không thay thế validation nghiệp vụ

Null chỉ là một dạng đầu vào không hợp lệ. Các điều kiện sau **không được bảo đảm** bởi `Objects.requireNonNull`:

| Kiểu dữ liệu | Kiểm tra null | Kiểm tra thêm thường cần |
| --- | --- | --- |
| `String` | Tham chiếu phải tồn tại | Không rỗng, không blank, độ dài, pattern, chuẩn hóa |
| `Integer` | Wrapper khác null | Giá trị dương, phạm vi, quan hệ với tham số khác |
| `Collection` | Collection khác null | Không rỗng, phần tử hợp lệ, không có phần tử null nếu hợp đồng cấm |
| `List<Customer>` | Bản thân list khác null | Từng customer khác null, ID hợp lệ |
| `Path` | Object đường dẫn khác null | Quyền truy cập, tồn tại, đường dẫn hợp lệ theo ứng dụng |
| DTO/request | Object khác null | Các field, ràng buộc liên trường, quy tắc nghiệp vụ |

Nếu null là lỗi lập trình của caller, dùng `requireNonNull` là tự nhiên. Nếu request của người dùng cần tổng hợp nhiều thông báo lỗi, nên dùng cơ chế validation có cấu trúc để trả đúng trạng thái, thay vì chỉ bắt NPE và gửi nguyên message/stack trace đến người dùng.

### 7.1. Ví dụ đầy đủ: null, số lượng và chuỗi blank là ba điều khác nhau

Lưu thành `RequireNonNullValidationDemo.java`:

```java
import java.util.Objects;

public class RequireNonNullValidationDemo {
    static int validatedQuantity(Integer quantity) {
        int value = Objects.requireNonNull(
                quantity, "quantity must not be null");
        if (value <= 0) {
            throw new IllegalArgumentException("quantity must be positive");
        }
        return value;
    }

    static String validatedSku(String sku) {
        Objects.requireNonNull(sku, "sku must not be null");
        if (sku.isBlank()) {
            throw new IllegalArgumentException("sku must not be blank");
        }
        return sku;
    }

    public static void main(String[] args) {
        System.out.println("quantity=" + validatedQuantity(3));
        System.out.println("sku=" + validatedSku("SKU-7"));

        try {
            validatedQuantity(null);
        } catch (NullPointerException error) {
            System.out.println("quantityNull=" + error.getClass().getSimpleName()
                    + ": " + error.getMessage());
        }

        try {
            validatedQuantity(0);
        } catch (IllegalArgumentException error) {
            System.out.println("quantityRange=" + error.getClass().getSimpleName()
                    + ": " + error.getMessage());
        }

        try {
            validatedSku(" ");
        } catch (IllegalArgumentException error) {
            System.out.println("skuBlank=" + error.getClass().getSimpleName()
                    + ": " + error.getMessage());
        }
    }
}
```

```bash
javac -encoding UTF-8 --release 17 RequireNonNullValidationDemo.java
java RequireNonNullValidationDemo
```

Stdout đã chạy xác nhận:

```text
quantity=3
sku=SKU-7
quantityNull=NullPointerException: quantity must not be null
quantityRange=IllegalArgumentException: quantity must be positive
skuBlank=IllegalArgumentException: sku must not be blank
```

**Các điểm chính:**

- `quantity` là `Integer`, có thể nhận null. Trước khi unbox sang `int`, `Objects.requireNonNull` bảo đảm không null; nếu null, message rõ.
- Với `quantity == 0`, tham chiếu **khác null** nhưng giá trị **không hợp lệ**; do đó dùng kiểm tra `value <= 0` và `IllegalArgumentException` cho vi phạm phạm vi.
- Với `sku == " "`, chuỗi **khác null** nhưng không chứa ký tự không phải khoảng trắng; `String.isBlank()` (Java 11+) nhận diện điều này.
- `requireNonNull` xuất hiện từ Java 7, còn `String.isBlank` chỉ từ Java 11. Đây là ví dụ dùng Java 17+ để kết hợp các API hiện hành.
- Những `try/catch` trong `main` tách riêng từng lỗi chỉ để minh họa kết quả chính xác, không khuyến nghị ứng dụng production luôn bắt mọi `NullPointerException`.

### 7.2. Lưu ý autounboxing với kiểu nguyên thủy

`int`, `long`, `boolean` là primitive, **không thể chứa null**. `Objects.requireNonNull` được thiết kế cho object reference; với primitive, việc boxing chỉ khiến code khó đọc và không cung cấp ích lợi kiểm tra null thực chất.

Một tình huống quan trọng:

```java
static void process(int value) {
    // ...
}

Integer nullable = null;
process(nullable); // NullPointerException do unboxing tại lời gọi.
```

Đây là snippet minh họa: method `process` nhận primitive. Nếu `nullable` null, Java phải unbox `Integer` thành `int` trước khi gọi; vì thế lỗi xảy ra **trước khi thân process chạy**. Muốn kiểm tra null với message do mình kiểm soát, hãy validate wrapper `Integer` **trước khi chuyển sang primitive**, như `validatedQuantity(Integer)`.

## 8. Khi field thuộc object immutable, hãy bảo vệ invariant trong constructor

Một object được xây dựng thành công nên có các field bắt buộc hợp lệ theo hợp đồng. Với constructor:

```java
final class EmailMessage {
    private final String recipient;
    private final String subject;

    EmailMessage(String recipient, String subject) {
        this.recipient = Objects.requireNonNull(recipient, "recipient required");
        this.subject = Objects.requireNonNull(subject, "subject required");
    }
}
```

Đây là snippet class hợp lệ khi có import `java.util.Objects`. Nó bảo đảm **hai field khác null** sau constructor. Tuy nhiên `recipient` có thể là `""` hoặc chuỗi email sai cú pháp; `subject` có thể là chuỗi blank. Nếu ứng dụng yêu cầu định dạng email chuẩn, cần một bước kiểm tra khác.

### 8.1. Record trong Java hiện đại

Java records trở thành tính năng chính thức ở Java 16. Có thể đặt invariant trong compact constructor:

```java
record CustomerKey(String region, String id) {
    CustomerKey {
        Objects.requireNonNull(region, "region required");
        Objects.requireNonNull(id, "id required");
    }
}
```

Đây là snippet Java 16+; dùng JDK 17 trở lên. Với record compact constructor, Java gán các tham số component vào các field tương ứng sau phần thân constructor theo ngữ nghĩa của record. Kiểm tra này không làm giá trị được chuẩn hóa hoặc bảo đảm quy tắc nghiệp vụ khác. Không cần dùng record để hưởng lợi từ `requireNonNull` — class thường vẫn là lựa chọn hợp lệ.

### 8.2. Đừng dựa vào check ở constructor nếu object còn mutable

Nếu field có setter cho phép gán lại null sau khi xây dựng, invariant từ constructor có thể bị phá vỡ. Hãy kiểm tra ở mọi ranh giới **thay đổi trạng thái** phù hợp:

```java
void setDisplayName(String displayName) {
    this.displayName =
        Objects.requireNonNull(displayName, "displayName required");
}
```

Đây là snippet trong class có field `displayName`. Đặt validation tại method cập nhật thay vì mong constructor bảo vệ các cập nhật tương lai.

## 9. Đặt ở đâu trong call chain?

Một ứng dụng nhiều tầng có thể có controller, service và repository. Không phải tầng nào cũng cần lặp nguyên một thông báo `requireNonNull` cho cùng dữ liệu, nhưng mỗi public contract nên rõ **điều kiện tiền đề**.

Ví dụ:

```java
public InvoiceService(InvoiceRepository repository) {
    this.repository = Objects.requireNonNull(repository, "repository required");
}

public Invoice createInvoice(CreateInvoiceCommand command) {
    Objects.requireNonNull(command, "command required");
    // Validate nội dung command rồi thực thi nghiệp vụ.
}
```

Đây là snippet với các class ứng dụng giả định, không phải chương trình chạy độc lập.

- **Constructor dependency:** phát hiện thiếu repository **ngay lúc lắp ghép object**, thay vì đến khi người dùng gọi chức năng mới phát sinh NPE khó truy vết.
- **Public service method:** có thể yêu cầu command không null, nhưng field của command vẫn phải được kiểm tra qua cấu trúc validation/constructor thích hợp.
- **Repository/database:** lỗi SQL, kết nối hoặc dữ liệu không tìm thấy không tự đồng nghĩa “tham số null”; không biến mọi lỗi trong tầng này thành NPE.
- **Boundary với dữ liệu người dùng:** quyết định giữa validation result (ví dụ HTTP 400 với chi tiết theo trường) và exception do API contract. Đừng gửi stack trace hoặc lỗi hệ thống thô ra client.

### 9.1. Tại sao “thêm requireNonNull khắp mọi chỗ” không phải thiết kế tốt?

Kiểm tra ở **nơi đảm bảo ranh giới** thường đáng giá hơn chèn một phép kiểm tra mỗi lần đọc field. Nếu một object immutable đã được validate trong constructor và không thể bị gán lại, những `requireNonNull` lặp lại ở mọi getter ít thêm ý nghĩa.

Tập trung vào:
- Tham số public method/constructor được ghi rõ là bắt buộc.
- Dependency được inject, giữ trong field.
- Kết quả từ API ngoài khi hợp đồng caller **không chấp nhận null**.
- Dữ liệu được đưa qua biên giới giữa module có hợp đồng nullable khác nhau.

Không dùng `requireNonNull` để che một thiết kế nullability không nhất quán.

## 10. Giá trị trả về của API ngoài và bẫy khi xử lý Map

Có lúc một API cho phép trả null khi không tìm thấy dữ liệu. Ví dụ `Map.get(key)` có thể trả null khi key không tồn tại **hoặc** khi key có mapping đến null (nếu implementation cho phép null value).

```java
String displayName =
    Objects.requireNonNull(namesById.get(userId), "displayName missing");
```

Đây là snippet với `Map` `namesById` và `userId` đã có. Nếu giá trị từ `get` null, đoạn này ném NPE; nó **không phân biệt** “không có key” với “key tồn tại nhưng value null”. Nếu ứng dụng cần hai trường hợp khác nhau, dùng API/kiểm tra rõ ràng như `containsKey` theo hợp đồng của map.

**Quan trọng:** nếu “không có dữ liệu” là trạng thái **hợp lệ**, đừng tùy tiện gọi `requireNonNull`. Có thể dùng `Optional`, kết quả có trạng thái, hoặc xử lý nhánh không tìm thấy:

```java
Optional<String> maybeName = Optional.ofNullable(namesById.get(userId));
```

Đây là snippet từ Java 8+ với import `java.util.Optional`. Nó diễn đạt **có thể vắng mặt**, trong khi `requireNonNull` diễn đạt **bắt buộc có**. Không phải chỗ nào có null cũng là lỗi lập trình.

### 10.1. List khác null chưa đủ

```java
Objects.requireNonNull(items, "items required");
for (String item : items) {
    Objects.requireNonNull(item, "items must not contain null");
}
```

Đây là snippet trong method có `Collection<String> items`. Check đầu bảo vệ **collection**, vòng lặp bảo vệ **từng phần tử**. Một list khác null vẫn có thể chứa null. Nếu dữ liệu không cho phép null, bạn có thể cân nhắc **immutable collection** phù hợp hoặc kiểm tra từng phần tử khi tiếp nhận.

**Ví dụ về API hiện đại:** `List.of(...)` (Java 9) không chấp nhận phần tử null. Nhưng điều đó **không** có nghĩa mọi `List` được tạo bằng những cách khác cũng từ chối null. Hãy tuân thủ hợp đồng của implementation thực tế.

### 10.2. Streams và method reference

```java
List<String> checked = items.stream()
        .map(Objects::requireNonNull)
        .toList();
```

Đây là snippet trên Java 16+ vì `Stream.toList()`, giả định `items` là list đã có và import cần thiết. `map(Objects::requireNonNull)` áp dụng kiểm tra trên từng phần tử **khi stream được tiêu thụ**, không phải ngay lúc tạo pipeline. Nếu cần nhận diện chính xác vị trí/phần tử sai, vòng lặp có index và message cụ thể thường tốt hơn. Dùng stream chỉ vì “ngắn” không có nghĩa dễ debug hơn.

## 11. Java 9+: khi null là hợp lệ và cần fallback, dùng API khác

`Objects.requireNonNull` có chính sách **từ chối null**. Nếu null hợp lệ và ứng dụng muốn một giá trị mặc định **không null**, Java 9 bổ sung:

```java
Objects.requireNonNullElse(obj, defaultObj);
Objects.requireNonNullElseGet(obj, supplier);
```

Đây là chữ ký sử dụng minh họa:

- `requireNonNullElse` trả `obj` nếu khác null; nếu null, dùng `defaultObj` và yêu cầu fallback khác null.
- `requireNonNullElseGet` trả `obj` nếu khác null; nếu null, gọi supplier tạo fallback và yêu cầu kết quả không null.
- Hai method **không có trên Java 7 hoặc Java 8**; dùng khi dự án chạy Java 9+.
- Nếu cả đầu vào và fallback đều null, chúng ném `NullPointerException`, thay vì trả null.

### 11.1. Ví dụ đầy đủ để phân biệt fail-fast với fallback

Lưu thành `RequireNonNullElseDemo.java`:

```java
import java.util.Objects;
import java.util.function.Supplier;

public class RequireNonNullElseDemo {
    public static void main(String[] args) {
        String first = Objects.requireNonNullElse("Lan", "Guest");
        String second = Objects.requireNonNullElse(null, "Guest");

        int[] fallbackCalls = {0};
        Supplier<String> fallback = () -> {
            fallbackCalls[0]++;
            return "Guest";
        };

        String supplied = Objects.requireNonNullElseGet(null, fallback);
        String retained = Objects.requireNonNullElseGet("Mai", fallback);

        System.out.println("first=" + first);
        System.out.println("second=" + second);
        System.out.println("supplied=" + supplied);
        System.out.println("retained=" + retained);
        System.out.println("fallbackCalls=" + fallbackCalls[0]);

        try {
            Objects.requireNonNullElse(null, null);
        } catch (NullPointerException error) {
            System.out.println("bothNull=" + error.getClass().getSimpleName());
        }
    }
}
```

```bash
javac -encoding UTF-8 --release 17 RequireNonNullElseDemo.java
java RequireNonNullElseDemo
```

Stdout đã xác minh:

```text
first=Lan
second=Guest
supplied=Guest
retained=Mai
fallbackCalls=1
bothNull=NullPointerException
```

**Phân tích:**

- `first` dùng object đầu vì không null; `second` dùng fallback "Guest".
- `requireNonNullElseGet(null, fallback)` gọi supplier, tăng bộ đếm.
- `requireNonNullElseGet("Mai", fallback)` không gọi supplier, vì object chính đã hợp lệ.
- `requireNonNullElse(null, null)` ném NPE; API yêu cầu kết quả fallback không null.

**Chọn theo hợp đồng, không theo sở thích cú pháp:** nếu thiếu `userId` là lỗi của caller, dùng `requireNonNull(userId)`. Nếu thiếu `displayName` được phép và cần giá trị hiển thị mặc định, `requireNonNullElse(displayName, "Guest")` có thể hợp lý. Trả fallback khi lỗi phải bị báo cáo là một bug là cách dễ che giấu dữ liệu sai.

### 11.2. Eager và lazy fallback

Với:

```java
Objects.requireNonNullElse(value, computeDefault());
```

Java phải **đánh giá biểu thức `computeDefault()` trước khi gọi method**, kể cả nếu `value` khác null. Nếu default đắt tiền và chỉ nên tính khi thiếu giá trị, chọn:

```java
Objects.requireNonNullElseGet(value, () -> computeDefault());
```

Đây là snippet với `value` và `computeDefault()` có kiểu phù hợp. `Supplier` chỉ được gọi khi cần fallback. Điều này tương tự ý tưởng lazy message supplier của `requireNonNull`, nhưng **mục đích khác**: một cái sinh message lỗi, một cái sinh giá trị mặc định.

## 12. Một số bẫy khi dùng `requireNonNull`

### 12.1. Chỉ thay NPE tự nhiên bằng NPE có message, không làm dữ liệu hợp lệ hơn

`requireNonNull(x)` là một precondition check cho tham chiếu. Nó không thay đổi kiểu, nội dung, phạm vi giá trị hoặc bảo đảm các phụ thuộc khác. Sau khi check một `String`, chuỗi vẫn có thể blank hoặc có ký tự không hợp lệ.

### 12.2. Ném lỗi sai loại từ dữ liệu người dùng

Ở tầng Java API, NPE có thể hợp lý khi caller truyền null vào tham số được document là non-null. Nhưng trong ứng dụng web, một field JSON bị thiếu có thể cần error response **có cấu trúc**, không nên trả raw stack trace NPE. Chọn API boundary phù hợp và không dùng `catch (NullPointerException e)` bao toàn bộ logic để đoán field nào sai.

### 12.3. Kiểm tra sau khi đã dereference

```java
int length = input.length();
Objects.requireNonNull(input, "input required");
```

Đây là **snippet sai về vị trí kiểm tra**: nếu input null, `length()` đã ném lỗi trước khi bạn cung cấp message. Hãy đặt precondition ở **trước lần dùng đầu tiên**.

### 12.4. Kiểm tra một tham chiếu rồi dùng lại field mutable có thể thay đổi

Trong code nhiều thread, nếu field `currentConfig` có thể được gán lại, check rồi truy cập lại field không nhất thiết bảo đảm cùng một tham chiếu.

```java
Config local = Objects.requireNonNull(currentConfig, "config required");
local.apply();
```

Đây là snippet với kiểu `Config` và các thành viên giả định. Lưu tham chiếu vào biến cục bộ bảo đảm hai thao tác dùng **cùng object đã check**; không tự tạo ra thread safety cho nội dung bên trong object hoặc các trạng thái mutable khác. Hãy dùng cơ chế đồng bộ phù hợp nếu cần.

### 12.5. Nhầm overload khi truyền tham số null không định kiểu

Từ Java 8, có overload `(T, String)` và `(T, Supplier<String>)`. Một biểu thức:

```java
Objects.requireNonNull(value, null);
```

có thể trở nên **mơ hồ về overload** vì Java không biết `null` thứ hai có ý là `String` hay `Supplier<String>`. Đây là **ví dụ có chủ đích để nhận diện lỗi biên dịch**. Trong code thực tế, hãy cung cấp một message cụ thể hoặc một lambda rõ ràng; không cần cố truyền null làm thông báo.

### 12.6. Kiểm tra null ở nơi null có ý nghĩa hợp lệ

Ví dụ một bộ lọc có tham số `query` tùy chọn. Nếu `null` nghĩa là “không lọc”, gọi `requireNonNull(query)` sẽ thay đổi hợp đồng. Hãy phân biệt **required** với **optional** trong thiết kế API, rồi mới chọn kiểm tra.

### 12.7. Dùng Supplier chỉ để tối ưu theo cảm giác

Với message cố định, `"parameter required"` không nhất thiết đắt hơn một lambda. Supplier có thể cải thiện tình huống message phức tạp, nhưng nên cân nhắc code rõ ràng và số lần đường lỗi xảy ra trước khi tối ưu. Không đặt thao tác tốn thời gian hoặc side effect vào supplier trừ khi đó là hành vi có chủ đích.

### 12.8. Primitive, boxed type và nullability

`int` không null, `Integer` có thể null; nếu unboxing xảy ra trước khi method nhận primitive, NPE phát sinh ở caller. Hãy kiểm tra tham số wrapper ngay khi nó đi vào ranh giới cần non-null.

## 13. Thiết kế kiểm thử cho `requireNonNull`

Một bộ test hữu ích nên xác minh:

1. **Đầu vào hợp lệ:** giá trị trả về là chính object ban đầu. Với immutable object hoặc constructor, các invariant liên quan được giữ.
2. **Đầu vào null:** loại exception đúng là `NullPointerException`.
3. **Message khi có String overload:** `getMessage()` khớp message **do ứng dụng truyền vào**, không lệ thuộc hệ thống.
4. **Supplier overload:** supplier không được gọi khi object khác null; được gọi khi object null.
5. **Validation khác:** giá trị khác null nhưng sai range/blank vẫn bị từ chối bằng quy tắc riêng.
6. **Không có side effect trước precondition:** những tác vụ không nên diễn ra khi dữ liệu null cần được đặt sau bước validate.
7. **Kết quả fallback:** nếu dùng API Java 9+ thì kiểm tra cả primary có giá trị, null primary với fallback hợp lệ và fallback null.

### 13.1. JUnit 5 khi dự án có test framework

Trong dự án dùng JUnit 5, có thể viết:

```java
import static org.junit.jupiter.api.Assertions.*;
import java.util.Objects;
import org.junit.jupiter.api.Test;

class RequiredArgumentTest {
    @Test
    void rejectsNull() {
        NullPointerException error = assertThrows(
                NullPointerException.class,
                () -> Objects.requireNonNull(null, "name required")
        );
        assertEquals("name required", error.getMessage());
    }
}
```

Đây là **unit test dùng thư viện ngoài JDK**; cần cấu hình JUnit 5 trong Maven/Gradle hay test runner. Không trình bày nó như chương trình tự chạy chỉ với `javac` thuần. Ưu điểm là test có thể xác minh contract và chạy tự động trong CI.

### 13.2. Test không cần thư viện ngoài

Một cách viết đơn giản bằng JDK:

```java
try {
    Objects.requireNonNull(null, "id required");
    throw new AssertionError("Expected NullPointerException");
} catch (NullPointerException error) {
    if (!"id required".equals(error.getMessage())) {
        throw new AssertionError("Wrong error message");
    }
}
```

Đây là snippet trong method; mã dùng `AssertionError` tường minh nên không phụ thuộc cờ `-ea` của Java. Trong dự án thật, framework assertion giúp báo lỗi và tổ chức test dễ hơn. Không nên coi việc **chỉ in message** là tương đương một assertion.

## 14. Bảng chọn API theo tình huống

| Tình huống | Cách làm thường phù hợp | Lưu ý |
| --- | --- | --- |
| Tham số bắt buộc không được null | `Objects.requireNonNull(arg, "arg required")` | Fail-fast bằng NPE |
| Lưu dependency vào field constructor | `this.repo = Objects.requireNonNull(repo, "repo required")` | Giữ invariant khi object tạo thành công |
| Cần thông báo lỗi dựng khi null | `Objects.requireNonNull(arg, () -> expensiveMessage())` | Supplier overload Java 8+; giữ message pure |
| Null là trạng thái tùy chọn | `if (arg == null) ...` hoặc `Optional.ofNullable(arg)` | Không biến trạng thái hợp lệ thành exception |
| Cần một default khác null | `Objects.requireNonNullElse(arg, fallback)` | Java 9+ |
| Fallback đắt tiền, chỉ tạo khi null | `Objects.requireNonNullElseGet(arg, supplier)` | Java 9+ |
| Muốn kiểm tra chuỗi blank | `String.isBlank()` kết hợp non-null check | `isBlank` từ Java 11; không được thay bằng check null |
| Muốn kiểm tra số trong phạm vi | Condition/validation riêng | `requireNonNull` chỉ kiểm tra wrapper reference |
| Cần báo lỗi người dùng theo nhiều trường | Structured validation/error result | Tránh raw NPE/stack trace ra ngoài |
| Collection phải không chứa phần tử null | Validate từng phần tử hoặc construction API phù hợp | `requireNonNull(list)` chỉ kiểm tra list |
| Cần predicate trên stream | `Objects::nonNull` | Trả boolean; không phải fail-fast `requireNonNull` |

## 15. Checklist code review

- Tham số nào thật sự **bắt buộc không null**, tham số nào **nullable** theo API contract?
- `requireNonNull` đặt **trước thao tác đầu tiên dùng** tham số chưa?
- Thông báo lỗi nêu tên tham số và không chứa dữ liệu nhạy cảm?
- Giá trị trả về `T` có được dùng đúng để gán field hoặc lưu biến cần thiết?
- Với `String`, numeric wrapper, collection và DTO, đã có validation bổ sung cho **nội dung** chứ không chỉ null?
- Có trường hợp unboxing `Integer`→`int` xảy ra **trước** khi check không?
- Có lợi ích thật khi dùng `Supplier<String>`, hay String hằng đơn giản hơn?
- Null có thể là trạng thái hợp lệ/“không tìm thấy”? Nếu có, có nên dùng Optional/default/result khác không?
- Với field mutable hoặc đa luồng, code có dùng **chính tham chiếu đã check** thay vì đọc lại field không?
- Test đã bao gồm cả object hợp lệ, null và các trường hợp sai điều kiện khác chưa?
- Có dùng API từ Java 8/9/11/16 không? Nếu có, đã ghi rõ version và build target phù hợp chưa?

## 16. Bài tập tự kiểm tra có đáp án

**Câu 1.** `Objects.requireNonNull("abc")` trả về gì?  
**Đáp án:** Trả về chính tham chiếu `"abc"`; không copy, không chuyển đổi chuỗi.

**Câu 2.** `Objects.requireNonNull(null, "id required")` trả về null hay ném exception?  
**Đáp án:** Ném `NullPointerException` với message `"id required"`.

**Câu 3.** Vì sao đặt `requireNonNull` đầu constructor thường tốt hơn chờ một method khác gọi `field.trim()`?  
**Đáp án:** Phát hiện vi phạm invariant sớm và chỉ rõ tham số bị thiếu; tránh tạo object có field không hợp lệ rồi lỗi ở thời điểm khó truy vết.

**Câu 4.** `Objects.requireNonNull("")` có ném exception không?  
**Đáp án:** Không, vì chuỗi rỗng vẫn là object khác null. Cần kiểm tra `isEmpty`, `isBlank` hoặc điều kiện nghiệp vụ khác.

**Câu 5.** Một `List<String>` không null nhưng chứa phần tử null có được `requireNonNull(list)` phát hiện không?  
**Đáp án:** Không. API chỉ xét tham chiếu list. Kiểm tra các phần tử riêng nếu hợp đồng không cho phép chúng null.

**Câu 6.** Tại sao `Objects.requireNonNull(value, () -> message())` có thể tránh xây message khi value hợp lệ?  
**Đáp án:** Thân supplier chỉ được gọi nếu `value` null. Việc tạo supplier/lambda vẫn có chi phí riêng.

**Câu 7.** Java nào có overload `requireNonNull(T, Supplier<String>)`?  
**Đáp án:** Java 8 trở lên. Overload một tham số và overload với `String message` có từ Java 7.

**Câu 8.** Nếu một `Integer` null được truyền vào method nhận `int`, method có thể gọi `requireNonNull` bên trong để kiểm tra wrapper không?  
**Đáp án:** Không; null đã gây NPE khi unboxing ở phía caller, trước khi thân method được chạy. Hãy validate ở ranh giới nhận `Integer`.

**Câu 9.** Khi null là trạng thái cho phép và muốn giá trị mặc định, dùng API nào từ Java 9?  
**Đáp án:** `requireNonNullElse` hoặc `requireNonNullElseGet`. Không dùng `requireNonNull` nếu mục tiêu là fallback.

**Câu 10.** `Objects.requireNonNullElse(null, null)` có trả null không?  
**Đáp án:** Không; nó ném `NullPointerException` vì yêu cầu giá trị trả về phải khác null.

**Câu 11.** Tại sao `Objects.requireNonNull(value, null)` có thể lỗi compile trên Java 8+?  
**Đáp án:** Đối số null thứ hai không đủ để phân biệt overload `String` và `Supplier<String>`. Cần truyền message hoặc supplier có kiểu rõ.

**Câu 12.** Có nên dùng `catch (NullPointerException)` bao cả service để tự coi mọi NPE là lỗi nhập liệu không?  
**Đáp án:** Không. NPE có thể xuất phát từ lỗi lập trình ở vị trí khác. Dùng validation ở đúng ranh giới và mapping lỗi có chủ đích.

**Bài thực hành A — Constructor:** Mở rộng `UserProfile` thêm `email`, kiểm tra hai tham số riêng, thử lần lượt truyền null vào mỗi vị trí để kiểm tra message.

**Bài thực hành B — Supplier:** Chạy `RequireNonNullLazyDemo`, thay message thành một phép tính tốn thời gian giả lập được đo bằng counter, so sánh số lần supplier chạy ở đầu vào hợp lệ/null. Không cần `Thread.sleep` để chứng minh lazy evaluation.

**Bài thực hành C — Quantity:** Dùng `RequireNonNullValidationDemo` rồi thêm mức tối đa 1.000. Phân biệt null, 0, 1, 1.000, 1.001 và kiểm tra loại lỗi đúng.

**Bài thực hành D — Fallback:** Chạy `RequireNonNullElseDemo`, thay supplier mặc định trả null. Quan sát kết quả và giải thích tại sao `requireNonNullElseGet` không chấp nhận fallback null.

**Bài thực hành E — Collection:** Viết method nhận `List<String>` không null và cấm phần tử null. Cho test tạo list bằng `Arrays.asList("A", null, "C")`, rồi kiểm tra lỗi tại vị trí phần tử thứ hai.

**Bài thực hành F — Map:** Viết một `Map<String,String>` có key không tồn tại, sau đó dùng `get` và `requireNonNull` để quan sát lỗi. So sánh chính sách với `containsKey` và `Optional.ofNullable` khi thiếu dữ liệu là bình thường.

## 17. Tài liệu chính thức

- [Oracle Java SE 17 — java.util.Objects](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Objects.html): các overload `requireNonNull`, mô tả giá trị trả về, NPE và version `Since`.
- [Oracle Java SE 17 — java.util.function.Supplier](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/function/Supplier.html): hàm tạo giá trị theo nhu cầu.
- [Oracle Java SE 17 — NullPointerException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/NullPointerException.html): loại lỗi dùng cho tham chiếu null.
- [Oracle Java SE 17 — Optional](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Optional.html): biểu diễn giá trị có thể vắng mặt thay vì ép mọi null thành lỗi.
- [Oracle Java SE 17 — String](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html): `isBlank()`, `strip()` và các phép kiểm tra nội dung chuỗi.

**Tóm tắt:** Dùng `Objects.requireNonNull` tại những ranh giới có hợp đồng **tham chiếu bắt buộc khác null**. Nó trả lại chính object hợp lệ hoặc ném `NullPointerException` rõ ràng; overload `String` từ Java 7 và overload `Supplier<String>` từ Java 8 còn phù hợp trong Java hiện đại. Đừng nhầm check null với validation toàn bộ dữ liệu, và đừng dùng fail-fast nếu null là trạng thái tùy chọn hợp lệ.
