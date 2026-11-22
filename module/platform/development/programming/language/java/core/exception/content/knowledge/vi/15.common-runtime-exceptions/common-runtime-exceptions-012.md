# `Objects.requireNonNull` và kiểm tra điều kiện trước khi xử lý trong Java

Trong Java, **kiểm tra tiền điều kiện** (*precondition validation*) nghĩa là xác minh các yêu cầu bắt buộc của một lời gọi **trước khi sử dụng dữ liệu hoặc thực hiện side effect**. Ví dụ một phương thức tạo đơn hàng có thể yêu cầu mã đơn hàng khác `null`, không rỗng, số lượng dương và trạng thái hệ thống cho phép ghi. Kiểm tra sớm giúp lỗi xuất hiện tại **ranh giới API**, thay vì đợi một câu lệnh bên trong ném ngoại lệ khó hiểu sau khi dữ liệu đã bị thay đổi một phần.

Trong module Java Core – Exception, nhóm **Ngoại lệ runtime**, `java.util.Objects.requireNonNull` là API nền tảng cho việc yêu cầu một **tham chiếu không được `null`**. Nó có thể trả về chính tham chiếu đầu vào, hoặc ném `NullPointerException` ngay tại điểm kiểm tra. Tuy vậy, **`requireNonNull` chỉ kiểm tra null**, không thay thế việc kiểm tra chuỗi rỗng, giá trị âm, trạng thái không hợp lệ, giới hạn kích thước, tính toàn vẹn dữ liệu hay quyền truy cập.

~~~java
static String normalizeName(String name) {
    Objects.requireNonNull(name, "name must not be null");
    if (name.isBlank()) {
        throw new IllegalArgumentException("name must not be blank");
    }
    return name.trim();
}
~~~

Đây là mảnh phương thức Java hợp lệ khi có `import java.util.Objects;`. Nó cố ý phân biệt **null** và **blank**: cả hai đều không hợp lệ nhưng phản ánh hai điều kiện khác nhau. Phần còn lại giải thích API, lựa chọn loại ngoại lệ, thời điểm kiểm tra, khác biệt giữa fallback eager/lazy, giới hạn của kiểm tra null và một chương trình Java 17+ chạy độc lập.

## 1. Vì sao kiểm tra trước khi xử lý lại quan trọng?

Giả sử một dịch vụ nhận yêu cầu:

~~~java
void sendReceipt(String email, int quantity) {
    inventory.decrease(quantity);
    emailClient.send(email, "Receipt");
}
~~~

Đây là **mã minh họa chưa độc lập**, giả định `inventory` và `emailClient` tồn tại. Nếu `email == null` hoặc `quantity <= 0`, ứng dụng có thể đã giảm tồn kho trước khi phát hiện yêu cầu không hợp lệ. Lúc đó việc bắt một `NullPointerException` đơn thuần **không hoàn tác** thay đổi tồn kho.

Một cấu trúc tốt hơn:

~~~java
void sendReceipt(String email, int quantity) {
    Objects.requireNonNull(email, "email");
    if (email.isBlank()) {
        throw new IllegalArgumentException("email is blank");
    }
    if (quantity <= 0) {
        throw new IllegalArgumentException("quantity must be positive");
    }

    inventory.decrease(quantity);
    emailClient.send(email, "Receipt");
}
~~~

Các kiểm tra rẻ, thuần túy được đặt trước side effect. Điều này giúp phát hiện dữ liệu sai trước khi gây thay đổi trạng thái.

**Nhưng validation không thay thế transaction.** Ngay cả khi input hợp lệ, cập nhật tồn kho có thể thành công rồi thao tác gửi email thất bại. Khi cần tính nhất quán, ứng dụng còn phải thiết kế transaction, outbox, idempotency hoặc chính sách xử lý lỗi phù hợp. “Kiểm tra trước” chỉ giải quyết **tiền điều kiện có thể biết trước**, không bảo đảm mọi thao tác tiếp theo thành công.

## 2. `Objects.requireNonNull` hoạt động như thế nào?

`Objects` là lớp tiện ích trong package `java.util`. Ba overload thường dùng:

~~~java
public static <T> T requireNonNull(T obj)

public static <T> T requireNonNull(T obj, String message)

public static <T> T requireNonNull(
        T obj, java.util.function.Supplier<String> messageSupplier)
~~~

Đây là **chữ ký API minh họa**, không phải một class tự định nghĩa. Cả ba overload đều có điểm chung:

1. Nếu `obj != null`, trả lại **chính tham chiếu `obj`**.
2. Nếu `obj == null`, ném `NullPointerException`.
3. Dạng message bổ sung thông tin để nhận diện tham số nào sai.
4. Dạng `Supplier<String>` cho phép tạo message **lười** khi phát hiện null.

Ví dụ đơn giản:

~~~java
String value = "Java";
String checked = Objects.requireNonNull(value);

System.out.println(checked == value);
// true
~~~

`requireNonNull` không sao chép đối tượng, không làm biến thành bất biến, không tự cắt khoảng trắng, không thay đổi kiểu dữ liệu. Giá trị trả về thường được dùng để gán trực tiếp cho trường hoặc chuyển tới API tiếp theo.

Nếu truyền null:

~~~java
Object missing = null;
Objects.requireNonNull(missing);
// Ném NullPointerException.
~~~

Đây là mảnh cố ý ném ngoại lệ khi chạy. Không dựa vào message của dạng không tham số trong kiểm thử; giá trị thông điệp của một `NullPointerException` mới có thể là `null`.

### Tại sao trả về giá trị đầu vào?

Dạng trả về giúp code gọn trong constructor:

~~~java
final class ConnectionConfig {
    private final String host;

    ConnectionConfig(String host) {
        this.host = Objects.requireNonNull(host, "host");
    }
}
~~~

Đây là một class Java hợp lệ khi có import `Objects`. Nếu caller truyền null, constructor thất bại trước khi hoàn tất, thay vì tạo một đối tượng có trường `host` không hợp lệ.

Lưu ý rằng `host` khác null **không chứng minh** chuỗi host đúng định dạng, tồn tại trong DNS hoặc kết nối được. Những điều kiện khác cần validation riêng.

## 3. Chọn `NullPointerException`, `IllegalArgumentException` hay `IllegalStateException`?

Ba lớp đều là unchecked exceptions, nhưng truyền đạt ý nghĩa khác nhau.

| Điều kiện | Loại thường phù hợp | Ví dụ |
| --- | --- | --- |
| Một tham chiếu bắt buộc của API bằng `null` | `NullPointerException` | `Objects.requireNonNull(orderId, "orderId")` |
| Giá trị đối số khác null nhưng ngoài miền hợp lệ | `IllegalArgumentException` | `quantity <= 0` |
| Đối tượng/hệ thống ở trạng thái không cho phép thao tác | `IllegalStateException` | Chưa kết nối nhưng gọi `send()` |
| Chỉ số nằm ngoài miền của tập hợp | `IndexOutOfBoundsException` | `Objects.checkIndex(index, size)` |
| Giá trị không được tìm thấy nhưng là kết quả dự kiến | Có thể dùng `Optional`/result | Tra cứu ID không tồn tại |

Đây là **quy ước thiết kế thường dùng**, không phải một công thức tuyệt đối cho mọi public API. Một số thư viện coi `null` là đối số không hợp lệ và chủ động ném `IllegalArgumentException`. Điều quan trọng là **hợp đồng nhất quán, rõ nghĩa**.

### Điều kiện null

~~~java
Objects.requireNonNull(customerId, "customerId");
~~~

Dạng này thể hiện rõ “tham chiếu bắt buộc khác null”. Nếu thất bại, `getMessage()` của exception tạo từ overload nhận chuỗi là `"customerId"`.

### Điều kiện giá trị

~~~java
if (quantity <= 0) {
    throw new IllegalArgumentException(
            "quantity must be greater than zero");
}
~~~

`quantity` là kiểu nguyên thủy `int`, không thể là null; `requireNonNull` không có vai trò trong kiểm tra này.

### Điều kiện trạng thái

~~~java
if (!connected) {
    throw new IllegalStateException("connection is not ready");
}
~~~

Ở đây yêu cầu gửi có thể hoàn toàn hợp lệ, nhưng **trạng thái receiver** không cho phép tiếp tục.

### Không bắt `NullPointerException` để đoán tham số nào null

Không nên thay kiểm tra chủ động bằng:

~~~java
try {
    return user.getProfile().getName();
} catch (NullPointerException e) {
    return "unknown";
}
~~~

Đây là mảnh phản ví dụ. `NullPointerException` có thể do `user`, `getProfile()` hoặc logic bên trong một phương thức nào đó; bắt rộng rồi dùng fallback có thể che một lỗi lập trình quan trọng. Nếu một chuỗi tham chiếu nullable là trạng thái hợp lệ, hãy xử lý **từng ranh giới nullable theo hợp đồng**, không nuốt mọi NPE.

## 4. Hai cách viết message cho `requireNonNull`

**Message cố định:**

~~~java
Objects.requireNonNull(request, "request must not be null");
~~~

Thông điệp dễ đọc và không có chi phí tạo chuỗi phức tạp. Đối với phần lớn tham số, đây là lựa chọn mặc định tốt.

**Message động:**

~~~java
Objects.requireNonNull(request,
        () -> "request is required in phase " + phase);
~~~

Ở đây `request` và `phase` là biến có sẵn trong phạm vi. Lambda là `Supplier<String>`; nó chỉ tạo chuỗi khi `request == null`.

### Supplier được gọi lúc nào?

~~~java
String value = "present";
int[] calls = {0};

Objects.requireNonNull(value, () -> {
    calls[0]++;
    return "computed diagnostic";
});

System.out.println(calls[0]); // 0
~~~

Nếu object không null, supplier **không cần được gọi**. Với null:

~~~java
String value = null;
int[] calls = {0};

try {
    Objects.requireNonNull(value, () -> {
        calls[0]++;
        return "computed diagnostic";
    });
} catch (NullPointerException e) {
    System.out.println(e.getMessage()); // computed diagnostic
}
System.out.println(calls[0]); // 1
~~~

Đây là hai mảnh minh họa độc lập; chương trình chính cuối bài sẽ kiểm chứng cùng nguyên tắc.

### Supplier lười không có nghĩa an toàn để tạo side effect

Message supplier chỉ nên tính **thông tin chẩn đoán**. Tránh đặt trong đó cập nhật dữ liệu, gọi mạng hoặc ghi log có side effect:

~~~java
Objects.requireNonNull(value, () -> {
    chargeCreditCard(); // Không nên: side effect trong message.
    return "value is missing";
});
~~~

Đây là phản ví dụ có hàm giả định `chargeCreditCard()`. Khi null, Java chạy supplier để lấy message, dẫn tới thao tác nghiệp vụ không mong muốn **trong lúc đang tạo ngoại lệ**.

Một message supplier quá phức tạp còn có thể ném exception khác, làm che mất NPE mà `requireNonNull` lẽ ra báo. Hãy giữ message ngắn, không ném lỗi và không chứa dữ liệu nhạy cảm.

### Chú ý overload khi truyền null làm message

Không nên viết mơ hồ:

~~~java
Objects.requireNonNull(value, null);
~~~

Dạng này **không biên dịch** do có hai overload thứ hai nhận `String` và `Supplier<String>`, còn literal `null` có thể khớp cả hai mà không có kiểu cụ thể hơn.

Nếu thực sự muốn chọn overload message String với giá trị null, có thể ép kiểu:

~~~java
Objects.requireNonNull(value, (String) null);
~~~

Còn code thông thường nên truyền một message hữu ích, không cần ép kiểu null.

## 5. `Objects.requireNonNullElse`: lựa chọn giá trị dự phòng

Từ Java 9, `Objects` có thêm:

~~~java
public static <T> T requireNonNullElse(
        T obj, T defaultObj)
~~~

Nếu `obj != null`, trả về `obj`; nếu `obj == null`, trả về `defaultObj`, **nhưng giá trị được chọn không được null**.

~~~java
String name = Objects.requireNonNullElse(
        null, "anonymous");

System.out.println(name); // anonymous
~~~

Nếu cả giá trị chính và fallback đều null:

~~~java
Objects.requireNonNullElse(null, null);
// NullPointerException.
~~~

Đây là mảnh cố ý gây lỗi runtime.

### Nó khác `requireNonNull` ở mục đích

| Phương thức | Khi đầu vào khác null | Khi đầu vào null |
| --- | --- | --- |
| `requireNonNull(obj)` | Trả lại `obj` | Ném `NullPointerException` |
| `requireNonNull(obj, message)` | Trả lại `obj` | Ném NPE với message |
| `requireNonNullElse(obj, fallback)` | Trả `obj` | Trả fallback không null, hoặc ném NPE |

`requireNonNullElse` chỉ phù hợp nếu **fallback là một giá trị hợp lệ theo hợp đồng**. Nếu thiếu input là lỗi, đừng dùng một chuỗi mặc định để che nó.

### Java đánh giá tham số trước khi gọi phương thức

Một điểm quan trọng:

~~~java
String result = Objects.requireNonNullElse(
        "primary", createExpensiveDefault());
~~~

Dù `"primary"` khác null, Java vẫn **đánh giá biểu thức tham số** `createExpensiveDefault()` trước khi gọi `requireNonNullElse`. Nó có thể tốn chi phí hoặc có side effect.

Đây là **mảnh code minh họa**, giả định `createExpensiveDefault()` trả một String. Nếu việc tạo fallback tốn tài nguyên, hãy cân nhắc `requireNonNullElseGet`.

## 6. `Objects.requireNonNullElseGet`: fallback tạo lười

Java 9+ cung cấp:

~~~java
public static <T> T requireNonNullElseGet(
        T obj,
        java.util.function.Supplier<? extends T> supplier)
~~~

Nếu `obj != null`, trả lại `obj` mà không gọi supplier tạo fallback. Nếu `obj == null`, Java lấy fallback từ supplier và yêu cầu **kết quả được chọn khác null**.

~~~java
String a = Objects.requireNonNullElseGet(
        "ready", () -> expensiveDefault());

String b = Objects.requireNonNullElseGet(
        null, () -> expensiveDefault());
~~~

Đây là mảnh minh họa có `expensiveDefault()` giả định đã được định nghĩa.

- Trường hợp `a`: supplier không được gọi.
- Trường hợp `b`: supplier được gọi để tạo giá trị dự phòng.

### Đầu vào hợp lệ nhưng supplier trả null?

~~~java
Objects.requireNonNullElseGet(
        null, () -> null);
// NullPointerException.
~~~

Dạng này không cho phép fallback bằng null. Nếu API thật sự cho phép trả null, không nên dùng `requireNonNullElseGet` như một cách âm thầm hợp thức hóa điều đó.

### Khi nào nên dùng `Else` và `ElseGet`?

Dùng `requireNonNullElse` nếu fallback đã có sẵn hoặc cực rẻ:

~~~java
String label = Objects.requireNonNullElse(rawLabel, "(none)");
~~~

Dùng `requireNonNullElseGet` nếu fallback cần dựng object, đọc cấu hình hoặc tính toán đáng kể:

~~~java
Settings settings = Objects.requireNonNullElseGet(
        suppliedSettings,
        () -> Settings.defaults());
~~~

Đây là mảnh minh họa với lớp `Settings` giả định. Tạo dữ liệu dự phòng nên là thao tác an toàn và hợp đồng cần nói rõ khi nào nó được tính.

**Không nhầm với `Optional.orElse`/`orElseGet`:** hai cặp đều thể hiện ý tưởng eager/lazy fallback, nhưng `Objects.requireNonNullElse(Get)` thao tác trên **tham chiếu có thể null**, còn `Optional` biểu diễn việc có/không có giá trị bằng một đối tượng API khác.

## 7. Chọn overload sao cho thông điệp hữu ích

Một message tốt nên mô tả **tên tham số và điều kiện**:

~~~java
Objects.requireNonNull(orderId, "orderId must not be null");
~~~

Kém hữu ích hơn:

~~~java
Objects.requireNonNull(orderId, "Error");
~~~

Trong hệ thống lớn, có thể thêm ngữ cảnh không nhạy cảm:

~~~java
Objects.requireNonNull(payload,
        () -> "payload is required for operation " + operation);
~~~

Nhưng cần tránh:

- Mật khẩu, token, secret, raw cookie, thông tin thẻ thanh toán.
- Toàn bộ request/body chứa dữ liệu nhạy cảm.
- Dùng message làm **mã lỗi máy đọc ổn định**.
- Dựa vào tên file/dòng code trong `printStackTrace()` để xác định điều kiện nghiệp vụ.

Nếu cần nhánh xử lý tự động, nên dùng một mã lỗi cấu trúc hoặc loại exception phù hợp. Message dành cho người đọc, có thể được sửa theo thời gian.

## 8. Tổ chức validation theo thứ tự ưu tiên

Với một yêu cầu nhiều trường, nên quyết định **thứ tự kiểm tra có ý nghĩa**.

Ví dụ:

~~~java
static void validate(
        String orderId,
        String email,
        int quantity,
        boolean systemReady) {

    Objects.requireNonNull(orderId, "orderId");
    Objects.requireNonNull(email, "email");

    if (orderId.isBlank()) {
        throw new IllegalArgumentException("orderId is blank");
    }
    if (email.isBlank()) {
        throw new IllegalArgumentException("email is blank");
    }
    if (quantity <= 0) {
        throw new IllegalArgumentException(
                "quantity must be positive");
    }
    if (!systemReady) {
        throw new IllegalStateException("system is not ready");
    }
}
~~~

Phương thức này có thể đặt trong một lớp Java có import `Objects`.

- Các tham chiếu cần thiết được kiểm tra null trước khi gọi `isBlank()`.
- Các miền giá trị được xác minh tiếp.
- Điều kiện trạng thái được kiểm tra trước khi gây side effect.
- Phương thức chỉ hoàn tất bình thường khi các tiền điều kiện đã thỏa.

Nếu có nhiều lỗi đồng thời, việc **fail fast** nghĩa là method ném lỗi tại **điều kiện đầu tiên không hợp lệ** theo thứ tự code. Nó không tạo danh sách mọi lỗi. Với form nhập liệu, bạn có thể muốn một bộ kiểm tra thu thập toàn bộ lỗi và trả kết quả cấu trúc, thay vì ném exception ở lỗi đầu tiên.

### Không che lỗi thứ nhất bằng lỗi thứ hai

Code kém:

~~~java
static void process(String code) {
    if (code.isBlank()) { // NPE khi code null.
        throw new IllegalArgumentException("blank");
    }
}
~~~

Cách tốt hơn:

~~~java
static void process(String code) {
    Objects.requireNonNull(code, "code");
    if (code.isBlank()) {
        throw new IllegalArgumentException("code is blank");
    }
}
~~~

Trình tự này tạo một contract rõ: null là NPE chủ động, blank là IAE.

## 9. Validation đầu vào không đồng nghĩa object bất biến

Sau khi `requireNonNull(value)` thành công, bạn biết **tham chiếu tại thời điểm kiểm tra** không null. Điều đó không chứng minh:

- Object không bị thay đổi bởi luồng khác.
- Nội dung của một list không chứa null.
- Các field của object đều hợp lệ.
- Dữ liệu có quyền truy cập hoặc bảo mật phù hợp.
- Object luôn ở trạng thái có thể sử dụng.
- Các thao tác I/O về sau không thất bại.

Ví dụ:

~~~java
List<String> names = Objects.requireNonNull(
        suppliedNames, "suppliedNames");
~~~

Đây là mảnh minh họa với `List` và biến `suppliedNames`. Nó chỉ xác minh **list reference không null**. Bên trong vẫn có thể có phần tử null:

~~~java
List<String> names =
        new java.util.ArrayList<>();
names.add(null);

Objects.requireNonNull(names);     // Thành công.
Objects.requireNonNull(names.get(0)); // Ném NPE.
~~~

Nếu hợp đồng yêu cầu mọi phần tử khác null, cần kiểm tra phần tử riêng hoặc dùng một API immutable/copy có các quy tắc rõ.

### Kiểm tra null trong constructor và copy phòng thủ

Với mutable collection:

~~~java
final class NameGroup {
    private final java.util.List<String> names;

    NameGroup(java.util.List<String> names) {
        this.names = java.util.List.copyOf(
                Objects.requireNonNull(names, "names"));
    }
}
~~~

`List.copyOf` tạo một danh sách unmodifiable và **từ chối phần tử null** theo hợp đồng của API. Nó giúp tránh giữ tham chiếu đến một list mutable do caller tiếp tục thay đổi, nhưng vẫn không kiểm tra quy tắc như chuỗi rỗng hay tên trùng nhau.

Đây là class hợp lệ nếu import `Objects`. Đừng suy ra rằng mọi phép copy hoặc mọi collection API đều có cùng chính sách null; đọc hợp đồng cụ thể.

## 10. `requireNonNull` trong constructor, record và setter

### Constructor

~~~java
final class Customer {
    private final String id;

    Customer(String id) {
        this.id = Objects.requireNonNull(id, "id");
    }
}
~~~

Nếu `id == null`, không có đối tượng `Customer` được tạo thành công để bàn giao cho caller.

### Record compact constructor trong Java 17

~~~java
record Product(String sku, int count) {
    Product {
        Objects.requireNonNull(sku, "sku");
        if (sku.isBlank()) {
            throw new IllegalArgumentException("sku is blank");
        }
        if (count < 0) {
            throw new IllegalArgumentException("count is negative");
        }
    }
}
~~~

Đây là khai báo record hợp lệ trong một lớp/tệp Java 17 phù hợp. Compact constructor có thể validation các component trước khi quá trình tạo record hoàn tất.

Lợi thế: bất kỳ lệnh `new Product(...)` dùng constructor này đều được kiểm tra tại ranh giới. Nhưng record không tự xác minh mọi quy tắc nghiệp vụ chỉ vì nó tạo accessor và là shallowly immutable.

### Setter

~~~java
void setDisplayName(String value) {
    this.displayName = Objects.requireNonNull(
            value, "displayName");
}
~~~

Đây là mảnh minh họa bên trong một class mutable. Kiểm tra trước khi gán giúp tránh đưa trạng thái null không hợp lệ vào object.

## 11. Tại sao không nên cố “gọi `requireNonNull` cho mọi thứ”?

Không phải mọi tham chiếu null đều là lỗi:

- Một trường `middleName` có thể tùy chọn.
- Một hàm tra cứu có thể trả `null` theo hợp đồng cũ.
- Một dependency có thể được tạo từ default khi không cung cấp.
- Một thuộc tính input có thể biểu diễn “không có giá trị”.

Nếu `null` là hợp lệ, hãy cho nó một ý nghĩa rõ ràng hoặc dùng API phù hợp như `Optional` cho kiểu trả về có/không. **Không ném NPE chỉ để tỏ ra defensive**.

Ví dụ một thuộc tính tùy chọn:

~~~java
static String visibleLabel(String label) {
    return Objects.requireNonNullElse(label, "(unnamed)");
}
~~~

Khác với mã bắt buộc:

~~~java
static String requiredLabel(String label) {
    return Objects.requireNonNull(label, "label");
}
~~~

Cả hai đều hợp lệ; chọn theo contract của phương thức.

Không nên đưa `Optional` vào mọi field, mọi tham số hoặc mọi collection element theo một khuôn cố định. `Optional` hữu ích đặc biệt ở những API trả về có khả năng không có giá trị, nhưng thiết kế nullability cần nhất quán theo ngữ cảnh.

## 12. `Objects.checkIndex` và những kiểm tra tiền điều kiện liên quan

Ngoài điều kiện tham chiếu khác null, phương thức có thể yêu cầu một **chỉ số hoặc dải chỉ số hợp lệ**. Java 17 cung cấp các helper:

~~~java
Objects.checkIndex(index, length);                 // 0 <= index < length
Objects.checkFromToIndex(from, to, length);        // 0 <= from <= to <= length
Objects.checkFromIndexSize(from, size, length);    // Vùng [from, from + size) nằm trong length
~~~

Đây là mã minh họa với các biến và `import java.util.Objects`. Các helper trả index/from khi hợp lệ, và ném `IndexOutOfBoundsException` nếu không. Helper cho range được thiết kế để kiểm tra an toàn cả điều kiện tràn số, thay vì cộng `int` một cách tùy tiện.

Ví dụ hai tiền điều kiện khác nhau trong cùng API:

~~~java
Objects.requireNonNull(array, "array");
Objects.checkIndex(index, array.length);
int value = array[index];
~~~

Tham chiếu null gây `NullPointerException`; index sai gây lỗi bounds. Không nên nuốt cả hai rồi trả `0` như thể đọc thành công. Ngược lại, truy cập `array[index]` vốn đã kiểm tra bounds; không bắt buộc gọi `checkIndex` trước **mọi** lần đọc. Bài về `IndexOutOfBoundsException` phân tích sâu phạm vi `[from, to)`, off-by-one và lựa chọn helper. Ở đây trọng tâm là **xác nhận tiền điều kiện trước side effect**.

## 13. `Objects.requireNonNull` và helpful NullPointerException

Trên JVM hỗ trợ helpful NPE messages, lỗi dereference null có thể đi kèm thông điệp mô tả biểu thức thất bại. Đây là **hỗ trợ debug**, không phải một hợp đồng nghiệp vụ ổn định để phân tích chuỗi `getMessage()`.

~~~java
String name = null;
Objects.requireNonNull(name, "name must not be null");
~~~

Đoạn minh họa yêu cầu import `java.util.Objects`. `requireNonNull` chủ động báo ràng buộc ngay tại ranh giới đầu vào, với message ứng dụng quyết định; còn helpful NPE tự động xuất hiện từ một số thao tác runtime. Cả hai có thể là `NullPointerException`, nhưng chúng trả lời hai câu hỏi khác nhau: **tiền điều kiện API bị vi phạm** hay **mã đã dereference null ở đâu**.

## 14. Tránh side effect trước validation và thứ tự đánh giá Java

Một chi tiết thực thi quan trọng: **đối số của một lời gọi method được đánh giá trước khi method bắt đầu chạy**.

Xem:

~~~java
save(
        Objects.requireNonNull(orderId, "orderId"),
        calculateAndChargeFee());
~~~

Dù tham số đầu tiên được `requireNonNull` kiểm tra trước khi đánh giá tham số thứ hai theo quy tắc **đánh giá đối số từ trái sang phải**, vẫn nên tránh tổ chức lời gọi phức tạp kiểu này khi side effect lớn hoặc cần kiểm tra nhiều dữ liệu. Đặt validation vào câu lệnh riêng giúp dễ đọc và dễ kiểm soát hơn.

~~~java
Objects.requireNonNull(orderId, "orderId");
validateFeePolicy();

int fee = calculateFee();
save(orderId, fee);
~~~

Đây là mảnh minh họa với các hàm giả định. Nếu `calculateFee()` có side effect, chỉ chạy nó sau các bước kiểm tra cần thiết.

Một phản ví dụ rõ hơn:

~~~java
save(
        calculateAndChargeFee(),
        Objects.requireNonNull(orderId, "orderId"));
~~~

Java đánh giá đối số **từ trái sang phải**: `calculateAndChargeFee()` có thể chạy trước khi `requireNonNull(orderId)` phát hiện null. Đừng để validation đứng sau các thao tác không thể hoàn tác.

**Đừng hiểu “fail fast” là “mọi validation tự xảy ra trước mọi biểu thức”.** Vị trí câu lệnh và thứ tự đánh giá thực tế vẫn quyết định khi nào lỗi được phát hiện.

## 15. Kiểm tra dữ liệu tại ranh giới, không kiểm tra đi kiểm tra lại vô hạn

Ở một API công khai, kiểm tra các tham số không-null giúp hợp đồng rõ ràng. Nhưng mỗi tầng nội bộ không nhất thiết phải lặp lại cùng một kiểm tra nếu invariants đã được thiết lập và bảo toàn.

Ví dụ một object immutable đã được constructor xác minh `id` không-null, các method nội bộ đọc `id` không cần gọi `Objects.requireNonNull(id)` mỗi lần chỉ để che việc invariants không được giữ.

Ngược lại, tại ranh giới giữa hệ thống với dữ liệu bên ngoài — HTTP, JSON, file, database, user input hoặc plugin — nên xác minh lại vì nguồn dữ liệu không thuộc quyền kiểm soát của module.

Một chiến lược thực tế:

1. Kiểm tra **kiểu/khả năng parse** của dữ liệu ở ranh giới nhập.
2. Kiểm tra **null và miền giá trị** ngay trước khi xây domain object.
3. Tạo object đảm bảo invariant nhờ constructor hoặc factory.
4. Truyền object hợp lệ qua các tầng thay vì một bộ tham số rời rạc dễ nhầm.
5. Vẫn xử lý các ngoại lệ I/O, cạnh tranh luồng và thay đổi trạng thái có thể xảy ra về sau.

Kiểm tra trước khi xử lý giúp **giảm lỗi do input**, không thay thế kiểm tra trạng thái ở thời điểm thực hiện thao tác thật.

## 16. Chương trình Java 17+ độc lập để kiểm chứng

Tạo tệp **`RequireNonNullDemo.java`**. Chương trình có đầu ra ổn định, minh họa `requireNonNull`, lazy message, fallback, tiền điều kiện, kiểu exception và kiểm tra chỉ số.

~~~java
import java.util.Objects;

public class RequireNonNullDemo {

    record Order(String id, int quantity) {}

    public static void main(String[] args) {
        System.out.println("== basic non-null ==");
        String original = "java";
        String checked = Objects.requireNonNull(original);
        System.out.println("sameReference=" + (original == checked));

        attempt("missing", () ->
                Objects.requireNonNull(null, "id is required"));

        System.out.println("== lazy message ==");
        int[] messageCalls = {0};
        Objects.requireNonNull("present", () -> {
            messageCalls[0]++;
            return "not present";
        });
        System.out.println("callsAfterPresent=" + messageCalls[0]);

        attempt("lazyMissing", () ->
                Objects.requireNonNull(null, () -> {
                    messageCalls[0]++;
                    return "computed message";
                }));
        System.out.println("callsAfterMissing=" + messageCalls[0]);

        System.out.println("== non-null fallback ==");
        System.out.println("elseValue="
                + Objects.requireNonNullElse(null, "guest"));
        System.out.println("elsePrimary="
                + Objects.requireNonNullElse("owner", "guest"));
        attempt("elseBothNull", () ->
                Objects.requireNonNullElse(null, null));

        System.out.println("== eager versus lazy ==");
        System.out.println("eagerResult="
                + Objects.requireNonNullElse(
                        "primary", makeFallback()));
        int[] fallbackCalls = {0};
        String lazyPrimary = Objects.requireNonNullElseGet(
                "primary", () -> {
                    fallbackCalls[0]++;
                    return "created";
                });
        System.out.println("lazyPrimary=" + lazyPrimary);
        System.out.println("fallbackCalls=" + fallbackCalls[0]);

        String lazyMissing = Objects.requireNonNullElseGet(
                null, () -> {
                    fallbackCalls[0]++;
                    return "created";
                });
        System.out.println("lazyMissing=" + lazyMissing);
        System.out.println("fallbackCalls=" + fallbackCalls[0]);
        attempt("lazyNullResult", () ->
                Objects.requireNonNullElseGet(null, () -> null));

        System.out.println("== domain validation ==");
        Order order = createOrder("O-1", 2, true);
        System.out.println("created=" + order.id()
                + ",quantity=" + order.quantity());

        attempt("nullId", () ->
                createOrder(null, 2, true));
        attempt("blankId", () ->
                createOrder("  ", 2, true));
        attempt("invalidQuantity", () ->
                createOrder("O-2", 0, true));
        attempt("systemNotReady", () ->
                createOrder("O-3", 2, false));

        System.out.println("== index validation ==");
        System.out.println("index=" + Objects.checkIndex(2, 3));
        System.out.println("fromTo="
                + Objects.checkFromToIndex(1, 3, 3));
        System.out.println("fromSize="
                + Objects.checkFromIndexSize(1, 2, 3));
        attempt("invalidIndex", () -> Objects.checkIndex(3, 3));
    }

    static String makeFallback() {
        System.out.println("fallbackFactoryCalled");
        return "backup";
    }

    static Order createOrder(
            String id, int quantity, boolean systemReady) {
        Objects.requireNonNull(id, "id");

        if (id.isBlank()) {
            throw new IllegalArgumentException("id is blank");
        }
        if (quantity <= 0) {
            throw new IllegalArgumentException(
                    "quantity must be positive");
        }
        if (!systemReady) {
            throw new IllegalStateException(
                    "system is not ready");
        }
        return new Order(id, quantity);
    }

    static void attempt(String label, Runnable operation) {
        try {
            operation.run();
            System.out.println(label + "=OK");
        } catch (RuntimeException e) {
            System.out.println(label + "="
                    + e.getClass().getSimpleName()
                    + ":" + e.getMessage());
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac RequireNonNullDemo.java
java RequireNonNullDemo
~~~

**Stdout chính xác (Java 17+):**

~~~text
== basic non-null ==
sameReference=true
missing=NullPointerException:id is required
== lazy message ==
callsAfterPresent=0
lazyMissing=NullPointerException:computed message
callsAfterMissing=1
== non-null fallback ==
elseValue=guest
elsePrimary=owner
elseBothNull=NullPointerException:defaultObj
== eager versus lazy ==
fallbackFactoryCalled
eagerResult=primary
lazyPrimary=primary
fallbackCalls=0
lazyMissing=created
fallbackCalls=1
lazyNullResult=NullPointerException:supplier.get()
== domain validation ==
created=O-1,quantity=2
nullId=NullPointerException:id
blankId=IllegalArgumentException:id is blank
invalidQuantity=IllegalArgumentException:quantity must be positive
systemNotReady=IllegalStateException:system is not ready
== index validation ==
index=2
fromTo=1
fromSize=1
invalidIndex=IndexOutOfBoundsException:Index 3 out of bounds for length 3
~~~

### Giải thích chương trình

**`basic non-null`:** `requireNonNull(original)` trả đúng tham chiếu, nên `sameReference=true`. Khi `obj == null`, overload nhận message tạo `NullPointerException` có thông điệp được truyền.

**`lazy message`:** lần đầu giá trị `"present"` khác null, supplier không chạy và biến đếm bằng `0`. Lần sau null khiến supplier chạy một lần để tạo message; `attempt` bắt NPE và in nội dung.

**`non-null fallback`:** khi obj null, `requireNonNullElse` trả `"guest"`. Khi obj khác null, trả `"owner"`. Với cả hai null, JDK 17 ném NPE có thông điệp `defaultObj` theo cách triển khai chuẩn. Không dựa vào chi tiết message này làm hợp đồng phân loại lỗi ứng dụng.

**`eager versus lazy`:** phương thức `makeFallback()` chạy **trước** `requireNonNullElse` dù primary khác null, nên in `fallbackFactoryCalled`. Ngược lại, supplier của `requireNonNullElseGet` không được gọi khi primary khác null; khi primary null, supplier được gọi một lần và trả `"created"`.

**`domain validation`:** `createOrder` phân biệt null id (NPE), blank id và quantity không dương (IAE), hệ thống chưa sẵn sàng (ISE). Validation được thực hiện trước khi tạo record `Order`; caller nhận loại lỗi cụ thể.

**`index validation`:** `Objects.checkIndex` và hai hàm kiểm tra khoảng trả điểm bắt đầu/chỉ số hợp lệ. Khi index bằng length, phương thức ném `IndexOutOfBoundsException`.

### Độ ổn định của thông điệp JDK

Chương trình in message của một số exception được JDK 17 tạo trong các helper `Objects`. Những thông điệp như `defaultObj`, `supplier.get()` hoặc `Index 3 out of bounds for length 3` là **các thông điệp của JDK 17 tiêu chuẩn**, nhưng **không nên dùng chúng làm API contract** hoặc điều kiện logic trong hệ thống. Nếu cần test di động qua nhiều JDK, hãy kiểm tra type của exception và thông tin có cấu trúc do ứng dụng tự kiểm soát; đừng buộc test phụ thuộc nguyên văn message JDK.

## 17. Null trong generic API và suy luận kiểu

`Objects.requireNonNull` có dạng generic `<T> T` để giữ nguyên type tĩnh của đối tượng:

~~~java
String text = Objects.requireNonNull(
        suppliedText, "suppliedText");

java.util.List<String> names = Objects.requireNonNull(
        suppliedNames, "suppliedNames");
~~~

Đây là mảnh minh họa có biến đầu vào tương ứng. Generic ở đây **không kiểm tra sâu type argument** hoặc nội dung collection. Nó chỉ cho compiler biết kiểu trả về tương thích với type của `obj`.

Với method trả đối tượng generic:

~~~java
static <T> T required(T value) {
    return Objects.requireNonNull(value, "value");
}
~~~

Method giữ type `T` và báo NPE nếu object null. Nó không biến một giá trị nullable thành một bằng chứng compile-time chắc chắn không null theo toàn bộ hệ thống type Java (Java 17 không tích hợp null-safety ở cấp type như một số ngôn ngữ khác).

Các annotation như `@NonNull` hoặc `@Nullable` đến từ thư viện và công cụ phân tích tĩnh riêng; chúng có thể tăng chất lượng kiểm tra nhưng không thay thế hành vi runtime của `Objects.requireNonNull`.

## 18. Những hiểu lầm và lỗi thường gặp

### 18.1. “`requireNonNull` sửa giá trị null bằng một mặc định”

Sai. `requireNonNull` ném NPE khi null. Nếu hợp đồng có fallback hợp lệ, dùng `requireNonNullElse` hoặc `requireNonNullElseGet`.

### 18.2. “`requireNonNull` chứng minh String không rỗng”

Sai. `""` và `"   "` đều khác null. Kiểm tra `isEmpty()` hoặc `isBlank()` theo yêu cầu.

### 18.3. “Dùng `requireNonNull` cho số nguyên primitive”

Primitive `int`, `long`, `boolean` không thể null. Nếu một wrapper như `Integer` có thể null thì `requireNonNull` mới kiểm tra tham chiếu wrapper đó.

### 18.4. “`Objects.requireNonNullElse` không bao giờ tạo fallback nếu object đã có”

Sai nếu fallback được truyền bằng **biểu thức gọi hàm**. Java đánh giá tham số trước khi gọi method. Chỉ `requireNonNullElseGet` mới trì hoãn việc **thực thi supplier** theo điều kiện chọn fallback.

### 18.5. “`requireNonNullElseGet` cho phép fallback null”

Sai. Khi cần lấy fallback, giá trị do supplier trả phải khác null; nếu không phương thức ném NPE.

### 18.6. “Message supplier luôn được gọi”

Sai. Với `requireNonNull(obj, Supplier<String>)`, supplier chỉ được dùng khi obj null. Dùng message supplier thuần túy để tránh side effect bất ngờ.

### 18.7. “Đặt mọi thứ vào `catch (NullPointerException)` là defensive programming”

Sai. Nó có thể che lỗi lập trình bất ngờ bên trong nhiều lời gọi khác nhau. Chủ động kiểm tra **tham số có hợp đồng không-null**, không nuốt mọi NPE.

### 18.8. “Mọi dữ liệu khác null đều hợp lệ”

Sai. Số âm, email sai định dạng, độ dài ngoài miền, trạng thái không sẵn sàng và điều kiện bảo mật vẫn cần xác minh.

### 18.9. “`IllegalArgumentException` và `IllegalStateException` thay nhau được”

Không nên. IAE thường mô tả giá trị đối số không hợp lệ; ISE thường mô tả trạng thái receiver không cho phép thao tác.

### 18.10. “Kiểm tra trước là đủ chống mọi lỗi”

Sai. Sau validation vẫn có thể có lỗi I/O, cạnh tranh luồng, thay đổi dữ liệu, timeout, tài nguyên hết, hoặc lỗi side effect. Cần thiết kế giao dịch/lifecycle.

### 18.11. “`requireNonNull(list)` kiểm tra mọi phần tử”

Sai. Nó kiểm tra list reference. Nếu muốn toàn bộ phần tử khác null, phải kiểm tra phần tử hoặc dùng API có hợp đồng kiểm tra như `List.copyOf`.

### 18.12. “Có helpful NPE nên không cần validation”

Sai. Helpful NPE hỗ trợ chẩn đoán nhưng không thay thế một hợp đồng precondition rõ ràng. Message tự động cũng không nên được parse.

### 18.13. “`Objects.checkIndex` báo NPE nếu index vượt miền”

Sai. Với index nguyên, lỗi kiểm tra miền là `IndexOutOfBoundsException`, không phải vấn đề tham chiếu null.

### 18.14. “Bắt một NPE là có thể tiếp tục mọi trạng thái”

Sai. Một NPE bất ngờ có thể báo invariant bị phá vỡ. Nếu không có phương án phục hồi chính xác, nên để lỗi lan truyền tới handler phù hợp.

### 18.15. “Các tham số được đánh giá sau khi method bắt đầu”

Sai. Java đánh giá các biểu thức đối số từ trái sang phải **trước lời gọi method**. Side effect ở đối số trước vẫn có thể chạy trước một validation ở đối số sau.

### 18.16. “Validation nên báo lỗi chung chung để giấu tên tham số”

Không hẳn. Với log nội bộ và API dành cho lập trình viên, tên tham số thường hữu ích. Điều cần giấu là dữ liệu nhạy cảm, không phải mọi ngữ cảnh chẩn đoán.

### 18.17. “Một nullable field luôn là bug”

Không. `null` có thể là trạng thái tùy chọn theo hợp đồng. Lỗi là **không thống nhất** giữa khả năng null và cách sử dụng.

### 18.18. “Fail fast là cách duy nhất cho form validation”

Không. Với API nhập liệu tương tác, việc trả nhiều lỗi cùng lúc đôi khi tốt hơn ném exception ngay ở lỗi đầu tiên. Chọn theo cách caller cần trình bày và phục hồi.

## 19. Checklist trước khi xử lý một yêu cầu

1. **Phân biệt bắt buộc với tùy chọn:** Field nào không được null, field nào có thể thiếu?
2. **Kiểm tra null sớm:** Dùng `Objects.requireNonNull` nếu null là vi phạm hợp đồng.
3. **Kiểm tra miền giá trị:** Chuỗi rỗng/blank, số âm, độ dài, khoảng giá trị, định dạng.
4. **Kiểm tra trạng thái:** Receiver/hệ thống có đang ở trạng thái cho phép thao tác?
5. **Chọn loại lỗi rõ:** NPE cho null bắt buộc; IAE cho giá trị đối số không hợp lệ; ISE cho trạng thái sai; IOBE cho chỉ số.
6. **Đặt validation trước side effect:** Tránh ghi dữ liệu/gọi mạng rồi mới phát hiện input sai.
7. **Không lạm dụng fallback:** Giá trị dự phòng phải hợp lệ về nghiệp vụ; chỉ lazy nếu cần tính muộn.
8. **Không parse message lỗi:** Dùng type hoặc mã lỗi cấu trúc nếu cần logic máy.
9. **Giữ thông tin nhạy cảm khỏi message:** Đừng vô tình để lộ token hoặc toàn bộ request.
10. **Kiểm tra chiều sâu hợp đồng:** Non-null reference không chứng minh dữ liệu bên trong hợp lệ.
11. **Xử lý cạnh tranh và I/O riêng:** Validation ban đầu không loại bỏ race hoặc side-effect failure.
12. **Kiểm thử tại biên:** Null, blank, giá trị ngoài miền, trạng thái không hợp lệ và nhánh thành công.
13. **Duy trì invariants sau construction:** Constructor/factory nên tạo object hợp lệ để code nội bộ không lặp kiểm tra vô hạn.
14. **Định nghĩa public API rõ:** Caller biết khi nào ném ngoại lệ và khi nào nhận kết quả dự phòng.

## 20. Câu hỏi tự kiểm tra

1. `Objects.requireNonNull` trả gì khi object khác null?
2. Nó ném loại exception gì khi object null?
3. `requireNonNull("x")` có tạo một String mới không?
4. Hai overload tạo message khác nhau ở điểm nào?
5. Supplier message được gọi nếu object khác null không?
6. Vì sao nên tránh side effect trong message supplier?
7. `requireNonNull(null, "id")` có message là gì?
8. `requireNonNull("", "name")` có ném lỗi không? Vì sao?
9. `String.isBlank()` khác kiểm tra null như thế nào?
10. Khi nào nên dùng `IllegalArgumentException` sau `requireNonNull`?
11. Khi nào nên dùng `IllegalStateException`?
12. `requireNonNullElse(null, "guest")` trả gì?
13. `requireNonNullElse(null, null)` làm gì?
14. Dùng một lời gọi tạo fallback trong `requireNonNullElse` thì nó chạy lúc nào?
15. `requireNonNullElseGet("present", supplier)` có gọi supplier không?
16. `requireNonNullElseGet(null, () -> null)` có hợp lệ không?
17. Vì sao `requireNonNullElseGet` có thể có lợi khi fallback đắt?
18. Nếu một list reference không null, có chắc từng phần tử không null không?
19. Một record compact constructor có thể kiểm tra null và miền giá trị không?
20. `Objects.checkIndex(index, length)` trả gì nếu hợp lệ?
21. `checkIndex(length, length)` ném lỗi gì?
22. `Objects.checkFromToIndex(1, 3, 3)` trả gì?
23. Dùng `catch (NullPointerException)` bao toàn bộ xử lý có rủi ro gì?
24. Helpful NPE có thay thế hợp đồng validation chủ động không?
25. Nếu kiểm tra null đặt sau lời gọi cập nhật database, chuyện gì có thể xảy ra?
26. `int` nguyên thủy có thể bằng null không?
27. Nếu tham số nullable là hợp lệ, có nên luôn gọi `requireNonNull` không?
28. Vì sao cùng lúc cần validation và transaction?
29. Khi nào nên trả danh sách lỗi validation thay vì ném exception đầu tiên?
30. Nên kiểm thử kiểu ngoại lệ hay nội dung message JDK tự tạo?

### Đáp án gợi ý

1. Chính tham chiếu object đã truyền.
2. `NullPointerException`.
3. Không.
4. `String` có message sẵn; `Supplier<String>` tạo message lười khi null.
5. Không.
6. Nó có thể chạy trong lúc tạo lỗi và gây hành vi bất ngờ hoặc lỗi khác.
7. `"id"`.
8. Không; chuỗi rỗng vẫn là object khác null.
9. `isBlank` kiểm tra ký tự/trống; `requireNonNull` kiểm tra tham chiếu.
10. Khi object đã khác null nhưng giá trị đối số vi phạm tiền điều kiện.
11. Khi trạng thái hiện tại không cho phép thao tác.
12. `"guest"`.
13. Ném NPE.
14. Biểu thức đối số được đánh giá trước khi method bắt đầu, dù primary có sẵn.
15. Không.
16. Không; ném NPE khi fallback kết quả null.
17. Supplier chỉ được tính khi primary null.
18. Không.
19. Có.
20. Trả lại `index`.
21. `IndexOutOfBoundsException`.
22. `1`.
23. Có thể nuốt lỗi lập trình hoặc che vị trí thất bại thực.
24. Không.
25. Side effect có thể đã xảy ra trước khi phát hiện input sai.
26. Không.
27. Không; phải làm theo hợp đồng nullable.
28. Validation kiểm tra input trước; transaction xử lý tính nhất quán khi thao tác sau vẫn có thể lỗi.
29. Khi caller cần hiển thị/sửa nhiều field lỗi trong một lượt.
30. Ưu tiên kiểm tra loại lỗi và dữ liệu ổn định; không parse message JDK.

## 21. Tổng kết

**`Objects.requireNonNull` giúp xác nhận tham chiếu bắt buộc không được `null` và báo `NullPointerException` ngay tại ranh giới API.** Dạng trả về cho phép dùng trực tiếp trong constructor/gán field; overload `Supplier<String>` chỉ tạo message khi cần. Nếu có fallback hợp lệ, `requireNonNullElse` cung cấp giá trị thay thế, còn `requireNonNullElseGet` tạo fallback lười. Những công cụ đó **không** thay thế kiểm tra chuỗi blank, miền số, trạng thái, chỉ số hoặc bảo mật. Hãy kiểm tra các điều kiện có thể biết **trước side effect**, phân biệt NPE/IAE/ISE/IOBE theo ngữ nghĩa, và giữ cơ chế xử lý I/O, transaction, cạnh tranh luồng độc lập với validation.