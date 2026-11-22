# `Objects.requireNonNull()` và thông báo lỗi tường minh

## 1. Mục đích: kiểm tra điều kiện không-null ngay tại điểm nhận dữ liệu

Trong Java, một tham chiếu có thể bằng `null`, tức là không trỏ đến đối tượng nào. Nếu chương trình gọi phương thức hoặc truy cập trường qua tham chiếu `null`, JVM thường ném `NullPointerException` (NPE). Lỗi có thể phát sinh ở một vị trí rất xa nơi giá trị không hợp lệ đi vào ứng dụng, khiến việc xác định nguyên nhân khó khăn.

`java.util.Objects.requireNonNull()` là công cụ chuẩn để **khẳng định một tham chiếu bắt buộc khác `null`** và thất bại sớm, ngay tại constructor, phương thức, hoặc điểm thiết lập trạng thái:

```java
this.customerId =
        Objects.requireNonNull(customerId, "customerId must not be null");
```

Nếu `customerId` khác null, phương thức trả về **chính tham chiếu đã truyền vào**. Nếu bằng null, nó ném `NullPointerException` kèm thông báo mà lập trình viên chỉ định. Nhờ đó lỗi được phát hiện ở ranh giới rõ ràng, thay vì chờ đến lần gọi `customerId.toString()` ở sâu trong ứng dụng.

Đây là quy tắc dành cho **trường/tham số bắt buộc**. Nếu `null` là một trạng thái có ý nghĩa hợp lệ, đừng áp `requireNonNull` một cách máy móc; hãy thiết kế chính sách xử lý giá trị tùy chọn phù hợp.

## 2. Các overload của `Objects.requireNonNull`

`Objects` trong package `java.util` cung cấp ba overload phổ biến:

| Phương thức | Khi đối số khác null | Khi đối số bằng null |
| --- | --- | --- |
| `Objects.requireNonNull(obj)` | Trả về chính `obj` | Ném `NullPointerException`, không đặt thông báo tùy chỉnh |
| `Objects.requireNonNull(obj, String message)` | Trả về chính `obj` | Ném `NullPointerException` với thông báo `message` |
| `Objects.requireNonNull(obj, Supplier<String> messageSupplier)` | Trả về chính `obj`, không gọi supplier | Gọi supplier để tạo thông báo và ném `NullPointerException` |

Mỗi overload có thể dùng trực tiếp trong câu lệnh gán vì kết quả có kiểu generic `T` tương ứng với đối số:

```java
String id = Objects.requireNonNull(rawId, "rawId is required");
```

Đây là fragment giả định biến `rawId` đã được khai báo. `requireNonNull` **không tạo bản sao, không chuyển chuỗi, không chuẩn hóa dữ liệu**; nó chỉ giữ nguyên đối tượng khác null hoặc ném ngoại lệ.

### Overload 1: không có thông báo tùy chỉnh

```java
Objects.requireNonNull(value);
```

Cách này hữu ích khi điều kiện đủ hiển nhiên tại điểm gọi. Nhưng thông báo trong exception có thể không giúp xác định tên tham số nghiệp vụ. Phân biệt với **Helpful NullPointerExceptions** từ JVM khi dereference trực tiếp: đừng mặc định một NPE do `Objects.requireNonNull` ném sẽ có chính phần diễn giải mà JVM sinh ra cho mọi biểu thức dereference. Nếu cần nêu rõ tham số, chọn overload có message.

### Overload 2: thông báo `String`

```java
Objects.requireNonNull(
        customerId,
        "customerId must not be null");
```

Ở thời điểm gọi, Java **đánh giá các đối số** trước khi vào phương thức. Vì vậy nếu xây thông báo bằng phép nối chuỗi, truy vấn hay một hàm tốn kém, chi phí đó xảy ra cả khi `customerId` khác null.

```java
Objects.requireNonNull(
        customerId,
        "Invalid customer: " + buildDiagnosticContext());
```

Fragment trên giả định `buildDiagnosticContext()` tồn tại và minh họa cách đánh giá tham số. Nó được gọi trước `requireNonNull`, ngay cả khi `customerId` hợp lệ. Nếu phần xây message đơn giản và hầu như không tốn chi phí, overload `String` thường dễ đọc nhất.

### Overload 3: thông báo sinh lười bằng `Supplier<String>`

```java
Objects.requireNonNull(
        customerId,
        () -> "Invalid customer: " + buildDiagnosticContext());
```

`Supplier<String>` là functional interface; biểu thức lambda được truyền vào, và `get()` chỉ được gọi khi `customerId == null`. Nhờ đó, quá trình tạo thông báo phức tạp chỉ chạy ở nhánh lỗi.

Điều kiện cần hiểu chính xác:

- Java vẫn phải **tạo/đánh giá biểu thức supplier** tại thời điểm gọi. Thứ được trì hoãn là **thân supplier** (`get()`), chứ không phải toàn bộ quá trình chuẩn bị argument.
- Lambda có thể giữ tham chiếu tới các biến được capture; việc capture phải tuân thủ yêu cầu biến local là final hoặc effectively final.
- Nếu xây message không tốn kém, `String` overload có thể rõ ràng hơn. `Supplier` chủ yếu có giá trị khi tạo message cần tính toán hoặc khi cần tránh thực hiện thao tác lỗi trên đường thành công.
- Nếu supplier tự ném ngoại lệ, ngoại lệ đó có thể xuất hiện thay vì NPE dự kiến. Hãy giữ thao tác tạo diagnostic đơn giản, an toàn và không có side effect ngoài ý muốn.

## 3. Ví dụ Java 17 đầy đủ, có stdout

Lưu mã vào tệp `RequireNonNullDemo.java`:

```java
import java.util.Objects;

public class RequireNonNullDemo {

    static final class OrderService {
        private final String tenantId;

        OrderService(String tenantId) {
            this.tenantId = Objects.requireNonNull(
                    tenantId, "tenantId must not be null");
        }

        String send(String orderId) {
            Objects.requireNonNull(
                    orderId,
                    () -> "orderId must not be null for tenant=" + tenantId);
            return "sent:" + tenantId + "/" + orderId;
        }
    }

    static String buildDiagnostic(int[] counter) {
        counter[0]++;
        return "diagnostic created";
    }

    public static void main(String[] args) {
        String id = "A7";
        System.out.println("same reference: "
                + (Objects.requireNonNull(id, "id required") == id));

        try {
            Objects.requireNonNull(null);
        } catch (NullPointerException e) {
            System.out.println("no custom message: "
                    + (e.getMessage() == null));
        }

        try {
            Objects.requireNonNull(null, "id required");
        } catch (NullPointerException e) {
            System.out.println("explicit message: " + e.getMessage());
        }

        try {
            new OrderService(null);
        } catch (NullPointerException e) {
            System.out.println("constructor message: " + e.getMessage());
        }

        OrderService service = new OrderService("t1");
        try {
            service.send(null);
        } catch (NullPointerException e) {
            System.out.println("service message: " + e.getMessage());
        }
        System.out.println("send: " + service.send("o7"));

        int[] eagerCounter = {0};
        Objects.requireNonNull(
                "present", buildDiagnostic(eagerCounter));
        System.out.println("eager evaluations: " + eagerCounter[0]);

        int[] lazyCounter = {0};
        Objects.requireNonNull(
                "present", () -> buildDiagnostic(lazyCounter));
        System.out.println("lazy evaluations before null: "
                + lazyCounter[0]);

        try {
            Objects.requireNonNull(
                    null, () -> buildDiagnostic(lazyCounter));
        } catch (NullPointerException e) {
            System.out.println("lazy message: " + e.getMessage());
        }
        System.out.println("lazy evaluations after null: "
                + lazyCounter[0]);

        System.out.println("fallback: "
                + Objects.requireNonNullElse(null, "anonymous"));
    }
}
```

Dùng JDK 17 hoặc mới hơn; từ thư mục chứa tệp, biên dịch và chạy:

```bash
javac RequireNonNullDemo.java
java RequireNonNullDemo
```

Stdout kỳ vọng chính xác:

```text
same reference: true
no custom message: true
explicit message: id required
constructor message: tenantId must not be null
service message: orderId must not be null for tenant=t1
send: sent:t1/o7
eager evaluations: 1
lazy evaluations before null: 0
lazy message: diagnostic created
lazy evaluations after null: 1
fallback: anonymous
```

Cách đọc chương trình:

1. `Objects.requireNonNull(id, "...") == id` là `true` vì trả nguyên cùng tham chiếu `String` `id`, không copy.
2. `requireNonNull(null)` ném NPE không có custom message; `e.getMessage() == null` là `true` trong ví dụ.
3. Constructor chặn `tenantId` null ngay khi tạo `OrderService`. Do đó instance được tạo thành công giữ invariant `tenantId != null`.
4. Phương thức `send` dùng message supplier để thêm ngữ cảnh `tenantId` khi `orderId` null. Đường thành công trả `sent:t1/o7` mà không cần sinh lỗi.
5. Lời gọi với `String` message đánh giá `buildDiagnostic(eagerCounter)` ngay, khiến counter lên `1` dù đối tượng `"present"` không null.
6. Lời gọi với lambda supplier và đối tượng `"present"` không chạy `buildDiagnostic`, nên counter vẫn `0`. Khi đầu vào null, supplier chạy đúng một lần trong tình huống này, thông báo `diagnostic created` xuất hiện và counter trở thành `1`.
7. `requireNonNullElse(null, "anonymous")` là API **khác**: trả giá trị mặc định khác null thay vì ném NPE. Chỉ dùng khi nghiệp vụ **cho phép mặc định hóa**, không dùng để che mất dữ liệu bắt buộc.

Đoạn `try/catch` ở đây chỉ để quan sát lỗi và so sánh các overload. Trong service thật, không nên bắt rồi bỏ qua `NullPointerException` do vi phạm tiền điều kiện; để exception nổi lên tới nơi xử lý lỗi phù hợp hoặc chuyển thành lỗi API có chủ đích ở ranh giới hệ thống.

## 4. Thông báo lỗi tường minh nên viết như thế nào?

Một thông báo hữu ích cần chỉ ra **giá trị nào** bị thiếu và **điều kiện nào** đã bị vi phạm:

| Thông báo | Đánh giá |
| --- | --- |
| `"null"` | Quá chung chung |
| `"Invalid input"` | Không biết input nào |
| `"orderId must not be null"` | Chỉ rõ tham số và yêu cầu |
| `"orderId must not be null for tenant=t1"` | Có ngữ cảnh nghiệp vụ khi cần tra cứu |

Thông điệp tiếng Việt hay tiếng Anh đều được; dự án nên có một quy ước nhất quán. Một số gợi ý:

- Gọi đúng tên tham số hoặc trường (`orderId`, `customerId`, `config`).
- Nêu quy tắc bị vi phạm (ví dụ “must not be null”).
- Chỉ bổ sung ngữ cảnh không nhạy cảm thực sự giúp gỡ lỗi, chẳng hạn tên thao tác hoặc id kỹ thuật khi được phép.
- Tránh đưa mật khẩu, access token, dữ liệu cá nhân nhạy cảm, hoặc dump toàn bộ object vào message. Exception thường được log và có thể đi qua nhiều hệ thống.
- Thông báo lỗi không phải định dạng hợp đồng trả về cho người dùng cuối. Nếu có tầng REST/API, tầng đó cần chuyển exception sang phản hồi đúng theo chính sách của hệ thống.

Ví dụ tham số bắt buộc:

```java
public void approve(String requestId, String reviewerId) {
    Objects.requireNonNull(requestId,
            "requestId must not be null");
    Objects.requireNonNull(reviewerId,
            "reviewerId must not be null");

    // Tiếp tục xử lý khi cả hai tham số hợp lệ.
}
```

Đây là một **phương thức minh họa**, không phải chương trình chạy độc lập. Lợi ích thực tế là caller biết chính xác tham số sai, ngay cả trước khi business logic truy cập đến nó.

## 5. Dùng trong constructor để bảo vệ invariant

Một invariant là điều kiện luôn phải đúng đối với instance đã được tạo thành công. Nếu `Order` không thể tồn tại hợp lệ khi thiếu `id`, hãy chặn `null` trong constructor và lưu trường `final`:

```java
final class Order {
    private final String id;

    Order(String id) {
        this.id = Objects.requireNonNull(
                id, "Order.id must not be null");
    }
}
```

Fragment này cần `import java.util.Objects;`. Cách viết không cho phép tạo một instance `Order` có `id == null` qua constructor ấy. Nó không kiểm tra các trường hợp khác như `id.isBlank()`: **khác null chưa chắc có giá trị hợp lệ**.

Nếu nghiệp vụ yêu cầu mã khác rỗng, thêm kiểm tra riêng sau bước null:

```java
this.id = Objects.requireNonNull(id, "id required");
if (this.id.isBlank()) {
    throw new IllegalArgumentException("id must not be blank");
}
```

Đây là fragment đặt trong constructor. `String.isBlank()` có từ Java 11 và hoạt động khi tham chiếu khác null. Việc phân biệt “không được null” và “không được rỗng” giúp điều kiện rõ ràng hơn.

Nếu object có nhiều tham số, check những trường bắt buộc tại ranh giới constructor/factory, thay vì hy vọng mọi lời gọi sau đó tự kiểm tra null. Tuy nhiên đừng lặp lại check tốn kém ở mọi nơi nếu invariant đã được đảm bảo.

## 6. Chọn `NullPointerException` hay `IllegalArgumentException`?

`Objects.requireNonNull` **luôn chủ đích dùng `NullPointerException`** khi đối tượng bắt buộc không tồn tại; nó không có overload cho phép chọn kiểu exception khác.

- `NullPointerException` phù hợp và phổ biến khi tham chiếu null vi phạm tiền điều kiện của một API Java.
- `IllegalArgumentException` thường dùng khi đối tượng không null nhưng giá trị không đạt điều kiện, ví dụ số lượng âm hoặc `String` rỗng trái quy tắc.
- Một số hệ thống có convention exception riêng và có thể cần phân loại lỗi tại lớp boundary. Hãy giữ chính sách nhất quán; không phải mọi null đều bắt buộc được xử lý cùng một kiểu lỗi nghiệp vụ.

Nếu API thiết kế coi null là input hợp lệ mang ý nghĩa “không có yêu cầu”, đừng ném NPE. Ngược lại, nếu null là lỗi lập trình của caller, việc báo lỗi sớm bằng `requireNonNull` có giá trị hơn một NPE phát sinh vô tình tại dòng truy cập sau đó.

### `requireNonNull` không biến mất khi chạy production

`Objects.requireNonNull` là lời gọi phương thức thông thường. Khác với kiểm tra bằng `assert`, nó không phụ thuộc bật/tắt assertion trên JVM. Nếu `null` đi tới đó, phương thức vẫn ném NPE theo hợp đồng ngay cả khi không bật `-ea`.

```java
assert customerId != null;
Objects.requireNonNull(customerId, "customerId required");
```

Đoạn trên chỉ dùng để so sánh ý nghĩa; không nên dùng cả hai chỉ để kiểm tra cùng một tiền điều kiện trong ứng dụng. `assert` dành cho giả định nội bộ phục vụ phát triển, và mặc định thường không được kích hoạt; `requireNonNull` phù hợp để cưỡng chế một tiền điều kiện bắt buộc ở runtime.

## 7. So sánh với `requireNonNullElse` và `requireNonNullElseGet`

Cùng thuộc `Objects` nhưng hai phương thức sau chọn **giá trị thay thế**, không đơn thuần thông báo lỗi:

| API | Nếu đầu vào khác null | Nếu đầu vào null |
| --- | --- | --- |
| `requireNonNull(obj, message)` | Trả chính `obj` | Ném NPE với message |
| `requireNonNullElse(obj, defaultObj)` | Trả chính `obj` | Trả `defaultObj`, yêu cầu default khác null |
| `requireNonNullElseGet(obj, supplier)` | Trả chính `obj` | Lấy giá trị từ supplier, yêu cầu giá trị trả về khác null |

Các overload `Else` có mặt từ Java 9. Chọn theo ý nghĩa:

```java
String displayName =
        Objects.requireNonNullElse(inputName, "Anonymous");
```

Fragment này giả định `inputName` đã khai báo. Khi nghiệp vụ cho phép tên hiển thị mặc định, đây là lựa chọn phù hợp. Khi `orderId` bắt buộc, tự động thay `"UNKNOWN"` có thể biến dữ liệu sai thành trạng thái khó truy vết; lúc đó `requireNonNull` báo lỗi rõ ràng hơn.

Một khác biệt nữa: `requireNonNullElseGet` **trì hoãn tạo giá trị mặc định** khi đầu vào không null, nhưng nó phải sinh **giá trị hợp lệ** khi đầu vào null; `requireNonNull(obj, Supplier<String>)` trì hoãn tạo **thông báo lỗi** và vẫn ném NPE nếu đầu vào null. Đừng nhầm hai hành vi.

## 8. Những bẫy phổ biến

### a. Nghĩ `requireNonNull` kiểm tra luôn chuỗi rỗng, danh sách rỗng, số âm

`requireNonNull("")`, `requireNonNull(List.of())` và `requireNonNull(-1)` đều có thể thành công vì các giá trị/đối tượng đó không null. Cần thêm quy tắc validation riêng:

```java
String name = Objects.requireNonNull(
        rawName, "name required");
if (name.isBlank()) {
    throw new IllegalArgumentException("name must not be blank");
}
```

Đây là fragment. Không nên dùng message `"name must not be blank"` cho riêng `requireNonNull` vì exception đó chỉ kích hoạt khi `name == null`; message phải mô tả đúng điều kiện thực sự được kiểm tra.

### b. Đánh giá message tốn kém trên đường thành công

`requireNonNull(obj, buildMessage())` gọi `buildMessage()` trước khi biết `obj` null hay không, vì đây là đối số thông thường. Muốn tránh đánh giá thân hàm ở đường thành công, truyền `() -> buildMessage()` vào overload supplier.

Cũng không nên đưa những side effect quan trọng (ghi DB, thay đổi state, cập nhật metrics nghiệp vụ) vào supplier tạo thông báo: supplier chỉ được chạy trên nhánh null nên logic sẽ bị phụ thuộc lỗi input.

### c. Truyền literal `null` làm tham số message không rõ overload

Vì Java có overload thứ hai là `String` và `Supplier<String>`, cách gọi `Objects.requireNonNull(value, null)` có thể **không biên dịch** do overload mơ hồ. Nếu thực sự muốn không có thông báo tùy chỉnh, dùng `Objects.requireNonNull(value)`. Nếu muốn cố ý truyền message null (không được khuyến khích), cần ép kiểu rõ ràng, chẳng hạn `(String) null`.

### d. Lạm dụng thông báo có dữ liệu nhạy cảm

`() -> "token=" + token` có thể vô tình làm lộ credential vào log khi check thất bại. Message nên mô tả **tên trường, loại yêu cầu và ngữ cảnh không nhạy cảm**, tránh in giá trị bí mật.

### e. Bắt NPE quá rộng để đoán điều kiện null

Một `try` bao trùm toàn bộ nghiệp vụ rồi bắt mọi `NullPointerException` và báo “missing orderId” có thể che giấu một lỗi lập trình ở nơi khác. Hãy kiểm tra tại **điểm nhận dữ liệu**, để lỗi cung cấp đúng thông tin, và chỉ bắt/chuyển ngoại lệ ở ranh giới đã định nghĩa.

### f. Trả về kết quả mà không duy trì invariant

`Objects.requireNonNull(dto.getId())` chỉ đảm bảo giá trị của **lời gọi getter tại thời điểm check** khác null. Nếu getter phụ thuộc trạng thái mutable hoặc tính toán, gọi lại sau đó có thể cho kết quả khác. Khi cần giá trị ổn định cho xử lý tiếp, hãy giữ kết quả trả về trong biến local hoặc trường `final`:

```java
String id = Objects.requireNonNull(
        dto.getId(), "dto.id required");
process(id);
```

Đây là fragment và giả định `dto` không null; nếu `dto == null` thì gọi `dto.getId()` sẽ ném NPE **trước** khi `requireNonNull` nhận đối số. Khi chuỗi truy cập có thể null, kiểm tra từng ranh giới thích hợp:

```java
Objects.requireNonNull(dto, "dto required");
String id = Objects.requireNonNull(
        dto.getId(), "dto.id required");
```

### g. Hiểu sai việc giá trị generic được trả về

`requireNonNull` giữ lại đúng kiểu generic `T` cho tham chiếu đầu vào và trả **chính tham chiếu**. Nó không tự động chuyển `Optional.empty()` thành lỗi: một `Optional` khác null vẫn thỏa `requireNonNull` kể cả khi chính Optional không chứa giá trị. Muốn bắt buộc giá trị nằm bên trong `Optional`, phải dùng API thích hợp như `orElseThrow` theo yêu cầu nghiệp vụ.

## 9. Checklist khi review code

1. Tham số/trường đang kiểm tra có thật sự **bắt buộc khác null** theo hợp đồng API không?
2. Đã đặt `requireNonNull` tại constructor, factory hoặc boundary đủ sớm để lỗi được gắn với nguồn input chưa?
3. Message có nêu tên trường và điều kiện chính xác, chẳng hạn `"orderId must not be null"`?
4. Có nguy cơ message chứa dữ liệu nhạy cảm hoặc gọi logic dễ ném lỗi phụ không?
5. Tạo message có tốn chi phí đến mức nên dùng `Supplier<String>` không?
6. Có cần kiểm tra giá trị khác null nhưng chưa hợp lệ (rỗng, blank, sai format, sai miền) riêng không?
7. Có lẫn `requireNonNull` với API lấy giá trị mặc định `requireNonNullElse...` hoặc hiểu nhầm null-safe `Objects.equals` không?
8. Có đang giả định check một lần đảm bảo trạng thái mãi mãi dù tham chiếu hoặc dữ liệu liên quan có thể thay đổi không?
9. Khi xảy ra exception, hệ thống có ghi nhận và hiển thị theo đúng chính sách API/log, thay vì nuốt lỗi hoặc làm lộ dữ liệu không?

## 10. Tự kiểm tra

**Câu 1.** `Objects.requireNonNull("x", "required")` trả gì?

**Đáp án:** Trả lại **cùng tham chiếu** đến chuỗi `"x"`; không ném ngoại lệ.

**Câu 2.** `Objects.requireNonNull(null, "userId required")` ném gì?

**Đáp án:** `NullPointerException` với message `"userId required"`.

**Câu 3.** Vì sao `Objects.requireNonNull(nonNull, expensiveMessage())` vẫn gọi `expensiveMessage()`?

**Đáp án:** Java đánh giá tất cả đối số của lời gọi thông thường trước khi thực hiện phương thức. Đổi thành `() -> expensiveMessage()` để trì hoãn thân xây thông báo.

**Câu 4.** `Objects.requireNonNull(null, () -> "missing")` có ném NPE không?

**Đáp án:** Có; supplier chỉ cung cấp **thông báo** `"missing"`, không phải giá trị thay thế.

**Câu 5.** `Objects.requireNonNullElse(null, "guest")` khác gì `Objects.requireNonNull(null, "guest")`?

**Đáp án:** Phương thức `Else` trả `"guest"` như giá trị mặc định; phương thức `requireNonNull` ném NPE mang message `"guest"`.

**Câu 6.** `Objects.requireNonNull("")` có ném NPE không?

**Đáp án:** Không. Chuỗi rỗng là một đối tượng khác null; phải kiểm tra rỗng/blank riêng nếu không hợp lệ.

## Kết luận

`Objects.requireNonNull()` là cách ngắn gọn, rõ ý định để **cưỡng chế tiền điều kiện “tham chiếu này phải khác null”**. Dùng overload `String` cho message đơn giản và `Supplier<String>` khi cần trì hoãn tính toán message đến lúc xảy ra lỗi. Đặt check ở ranh giới đầu vào, viết thông báo nêu rõ trường vi phạm, tránh lộ dữ liệu nhạy cảm và phân biệt kiểm tra null với validation giá trị hay lựa chọn fallback.
