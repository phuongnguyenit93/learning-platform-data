# Phân biệt null, vắng dữ liệu và lỗi

> **Chương:** Dữ liệu và trạng thái  
> **Học phần:** Code Quality Fundamentals (`CODE_QUALITY_FUNDAMENTALS`) — hiểu những thuộc tính quyết định mã nguồn có đáng tin cậy, dễ hiểu và dễ thay đổi hay không.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **`null`**, **giá trị không được cung cấp**, **không tìm thấy dữ liệu**, **giá trị rỗng**, **chưa tải dữ liệu** và **thao tác thất bại**.
2. Giải thích vì sao dùng cùng một giá trị `null` để biểu diễn nhiều trạng thái làm giảm tính đúng đắn, khả năng đọc và độ tin cậy của mã nguồn.
3. Chọn hợp đồng Java phù hợp: kiểu không-null, `Optional<T>`, exception hoặc kiểu kết quả có các trạng thái tường minh.
4. Nhận diện sự khác biệt giữa thuộc tính **vắng mặt** và thuộc tính **có giá trị JSON `null`** khi xử lý cập nhật một phần.
5. Tránh những sai sót phổ biến với `Map.get()`, SQL `NULL`, giá trị mặc định, cache và lời gọi dịch vụ ngoài.
6. Thiết kế kiểm thử theo từng trạng thái dữ liệu, bao gồm tình huống lỗi hạ tầng và ranh giới nghiệp vụ.

## 1. Một từ “không có” có thể che giấu nhiều trạng thái

Giả sử dịch vụ nhận yêu cầu đọc hồ sơ khách hàng:

- Không có khách hàng mang mã `123` trong cơ sở dữ liệu.
- Có khách hàng `123` nhưng họ chưa đặt biệt danh.
- Hồ sơ đang được tải từ dịch vụ khác.
- Truy vấn bị timeout nên không biết khách hàng có tồn tại không.
- API nhận lệnh cập nhật nhưng phía client không gửi trường `nickname`.
- Client gửi trường `nickname` với giá trị `null` vì muốn xóa biệt danh.

Sáu tình huống có thể bị gộp vào một kết quả `null`, nhưng cách xử lý đúng hoàn toàn khác nhau. Nếu gộp:

- “Không tìm thấy” có thể bị biến thành “không có quyền”, “thao tác thất bại” hoặc “tạo mới”.
- Timeout có thể bị hiểu nhầm là khách hàng không tồn tại và ghi đè dữ liệu.
- Yêu cầu cập nhật thiếu trường có thể vô tình xóa giá trị đang lưu.
- Giao diện có thể hiển thị “chưa có dữ liệu” khi thực tế hệ thống đang gặp sự cố.

Trong chương **Dữ liệu và trạng thái**, câu hỏi đầu tiên phải là: **“Trạng thái nghiệp vụ nào đang được biểu diễn?”** Sau đó mới quyết định kiểu Java, cấu trúc JSON hoặc giá trị trong database.

### Bảng phân biệt các khái niệm

| Trạng thái | Ý nghĩa | Ví dụ | Cách xử lý thường hợp lý |
| --- | --- | --- | --- |
| **Giá trị hiện diện** | Có dữ liệu hợp lệ | `nickname = "An"` | Sử dụng theo hợp đồng |
| **`null`** | Một biểu diễn kỹ thuật không có tham chiếu/giá trị; ý nghĩa do hợp đồng quy định | `String nickname = null` | Chỉ diễn giải sau khi biết hợp đồng của trường |
| **Vắng thuộc tính (missing)** | Trường không được gửi hoặc chưa có khóa | JSON không chứa `nickname` | Với PATCH có thể hiểu là “giữ nguyên” |
| **Không tìm thấy (not found)** | Tra cứu đã thực hiện thành công nhưng không có bản ghi khớp | Không có khách hàng ID `123` | `Optional.empty()` hoặc kết quả `NotFound` |
| **Rỗng (empty)** | Có giá trị thuộc một kiểu nhưng không có phần tử/ký tự | `""`, `List.of()` | Dùng giá trị rỗng nếu có ý nghĩa hợp lệ |
| **Không áp dụng (not applicable)** | Trường không có ý nghĩa đối với đối tượng này | `companyTaxId` đối với cá nhân | Mô hình hóa bằng loại đối tượng/điều kiện riêng |
| **Chưa tải (not loaded)** | Chưa biết dữ liệu vì chưa thực hiện hoặc chưa xong thao tác lấy | UI đang hiện spinner | Trạng thái riêng, không hiển thị như “không tồn tại” |
| **Lỗi (failure)** | Không thể hoàn thành thao tác theo hợp đồng | Database không kết nối được | Trả/ghi nhận lỗi, có chính sách thử lại hoặc xử lý |

**`null` không tự mang nghĩa “không tìm thấy” hay “lỗi”.** Nó chỉ cho biết một biến tham chiếu Java hiện không trỏ tới đối tượng nào, hoặc một trường JSON/cơ sở dữ liệu đang mang giá trị `null` theo đặc tả của hệ thống tương ứng.

## 2. Hợp đồng phải phân biệt ba câu hỏi độc lập

Khi gặp một giá trị có thể thiếu, hãy hỏi theo thứ tự:

1. **Thao tác có thành công không?** Nếu truy vấn lỗi, kết quả chưa xác định, kể cả khi kiểu trả về là `null`.
2. **Nếu thành công, dữ liệu có hiện diện không?** Ví dụ đã tra cứu xong và khách hàng không tồn tại.
3. **Nếu hiện diện, giá trị bên trong có hợp lệ/rỗng không?** Ví dụ hồ sơ có biệt danh là chuỗi rỗng hoặc chưa được đặt.

Ba câu hỏi nằm ở những cấp khác nhau:

~~~text
Thực hiện thao tác
├── Thất bại
│   └── Lỗi có ngữ cảnh, cách xử lý và khả năng thử lại
└── Thành công
    ├── Không có kết quả
    │   └── Đã kiểm tra và xác nhận không tìm thấy
    └── Có kết quả
        ├── Giá trị hợp lệ
        └── Giá trị có thể rỗng / null (nếu hợp đồng cho phép)
~~~

Hình này không khẳng định mọi API phải dùng đủ ba cấp đối tượng lồng nhau. Nó giúp tránh sai lầm phổ biến: **đưa thông tin về thất bại vào cùng một trạng thái với vắng dữ liệu**.

### Ví dụ về sự khác nhau trong hệ thống bán hàng

| Tình huống | Hợp đồng nên nói gì? |
| --- | --- |
| Tìm mã khuyến mãi không tồn tại | Tra cứu thành công, không tìm thấy mã |
| Khách hàng không nhập mã khuyến mãi | Không có mã được cung cấp, có thể áp dụng giá gốc |
| Khách nhập chuỗi `""` | Một giá trị chuỗi rỗng; chấp nhận hay từ chối tùy chính sách |
| Dịch vụ kiểm tra khuyến mãi timeout | Không thể xác định hợp lệ; cần chính sách lỗi rõ |
| Dịch vụ trả mã giảm giá 0 đồng | Có kết quả hợp lệ với **giá trị số bằng 0** |
| Phản hồi có khóa `discount` bằng `null` | Có trường nhưng giá trị không có; phải theo hợp đồng API |

Đặc biệt, **`0`, `false` và chuỗi rỗng không tự động là “không có dữ liệu”**. Nếu chúng là giá trị hợp lệ, không được xử lý như thiếu.

## 3. `null` trong Java: hợp lệ về kiểu, nguy hiểm khi ý nghĩa mơ hồ

Với biến tham chiếu Java, `null` là giá trị có thể gán trừ khi hợp đồng/kiểm tra cụ thể ngăn điều đó. Gọi phương thức trên `null` có thể dẫn đến `NullPointerException`:

~~~java
String nickname = null;
// nickname.trim(); // NullPointerException.
~~~

Đây có thể là lỗi lập trình, chứ không phải một trường hợp nghiệp vụ nên “chữa” bằng `catch (NullPointerException)`. Cách tốt hơn là xác định **giá trị nào được phép null ngay tại ranh giới**.

### 3.1. Đầu vào bắt buộc: kiểm tra sớm

Nếu mọi đơn hàng phải có mã khách hàng, hợp đồng nên thể hiện điều đó:

~~~java
import java.util.Objects;

record OrderCommand(String customerId, long amountVnd) {
    OrderCommand {
        Objects.requireNonNull(customerId, "customerId");
        if (customerId.isBlank() || amountVnd < 0) {
            throw new IllegalArgumentException("Invalid order");
        }
    }
}
~~~

`Objects.requireNonNull` giúp phát hiện thiếu tham chiếu tại nơi tạo dữ liệu; việc kiểm tra `isBlank()` bổ sung điều kiện nghiệp vụ. **Không-null không đồng nghĩa với hợp lệ**: chuỗi `""` có thể không-null nhưng vẫn không phải mã khách hàng.

Nếu `null` là giá trị hợp lệ trong nghiệp vụ, đừng thêm kiểm tra cấm null chỉ để “mã trông sạch”. Hãy ghi rõ lúc nào và tại sao nó được chấp nhận.

### 3.2. Đầu vào tùy chọn: đặt tên và quy tắc mặc định

Giả sử mã ghi chú là tùy chọn:

~~~java
static String displayNote(String rawNote) {
    if (rawNote == null || rawNote.isBlank()) {
        return "Không có ghi chú";
    }
    return rawNote;
}
~~~

Hàm này **cố ý** coi `null` và chuỗi trắng là tương đương để **hiển thị**. Điều đó không đồng nghĩa có thể ghi đè dữ liệu gốc bằng chuỗi “Không có ghi chú”. Ở tầng lưu trữ, có thể cần giữ nguyên sự khác biệt giữa giá trị vắng mặt và ghi chú rỗng.

Một quy tắc mặc định chỉ đúng khi nghiệp vụ cho phép. Với số tiền, giới hạn tín dụng, quyền truy cập hoặc trạng thái thanh toán, biến `null` thành `0`, `false` hay “đã thanh toán” có thể tạo sai sót nghiêm trọng.

### 3.3. Vị trí khai báo nullability

Có thể dùng chú thích kiểu `@Nullable`, `@NonNull` và công cụ phân tích tĩnh nếu dự án đã chọn một hệ chú thích cụ thể. Các annotation này có thư viện và mức hỗ trợ khác nhau; **chúng không tự thay thế validation lúc chạy** tại ranh giới nhận dữ liệu từ HTTP, database hoặc thư viện khác.

Tên biến, kiểu dữ liệu, constructor và tài liệu hợp đồng nên thống nhất về việc có chấp nhận `null` hay không. Nếu annotation nói non-null nhưng phương thức thực tế trả `null` khi timeout, vấn đề chính là **hợp đồng sai**, không phải thiếu cú pháp annotation.

## 4. `Optional<T>` biểu diễn sự vắng mặt được mong đợi

Trong Java, `Optional<T>` hữu ích nhất khi **kết quả có thể không tồn tại như một trường hợp bình thường**, đặc biệt ở kiểu trả về của phương thức tra cứu.

~~~java
import java.util.Optional;

record Customer(long id, String nickname) {}

interface CustomerRepository {
    // Tìm thấy -> Optional chứa Customer.
    // Không tồn tại -> Optional.empty().
    // Lỗi truy cập dữ liệu -> ném lỗi theo hợp đồng tầng dữ liệu.
    Optional<Customer> findById(long id);
}

final class CustomerService {
    private final CustomerRepository repository;

    CustomerService(CustomerRepository repository) {
        this.repository = repository;
    }

    Customer loadRequiredCustomer(long id) {
        return repository.findById(id)
                .orElseThrow(() ->
                        new IllegalArgumentException("Customer not found"));
    }
}
~~~

Điểm quan trọng: **`Optional.empty()` chỉ đại diện việc không tìm thấy sau một lần tra cứu thành công** trong hợp đồng này. Nếu kết nối database lỗi, repository không nên bắt exception rồi trả empty, vì điều đó khiến tầng dịch vụ hiểu nhầm một sự cố hạ tầng thành “khách hàng không tồn tại”.

Trong mã sản phẩm, hãy dùng exception hoặc kiểu lỗi riêng thay cho `IllegalArgumentException` minh họa nếu API cần phân biệt không tìm thấy với tham số không hợp lệ; ánh xạ sang HTTP phải theo hợp đồng API.

### 4.1. Cách dùng và giới hạn của `Optional`

~~~java
Optional<String> maybeNickname = Optional.of("An");
String display = maybeNickname.orElse("Khách hàng");

Optional<String> noNickname = Optional.empty();
String fallback = noNickname.orElse("Khách hàng");
~~~

- `Optional.of(value)` đòi hỏi `value` không-null; nếu null sẽ ném `NullPointerException`.
- `Optional.ofNullable(value)` tạo empty khi `value == null`, **làm mất phân biệt** nếu ban đầu có nhiều lý do khác nhau cho null.
- `Optional.map(...)` biến kết quả mapper bằng null thành empty. Do đó không thích hợp nếu mapper trả null là một trạng thái cần được giữ riêng.
- `orElse(defaultValue)` luôn đánh giá biểu thức argument trước khi gọi; nếu tạo mặc định tốn công hoặc có side effect, dùng `orElseGet(supplier)` để đánh giá khi empty.
- `get()` trên empty ném `NoSuchElementException`; thường nên dùng `orElseThrow(...)` với ý nghĩa lỗi rõ ràng, `ifPresent(...)` hoặc `map(...)`.

Không nên mặc định đưa `Optional` vào mọi field entity, mọi tham số hoặc mọi cấu trúc serialize; hiệu quả phụ thuộc framework, quy ước dự án và contract. Đặc biệt, **`Optional<Optional<T>>` thường là tín hiệu cần mô hình trạng thái rõ hơn** nếu một lớp Optional đang cố phân biệt “không gửi” với “gửi null”.

### 4.2. Giá trị rỗng có thể tốt hơn `null`

Nếu yêu cầu tìm danh sách đơn hàng của một khách không có đơn, một danh sách rỗng có thể là kết quả hợp lý:

~~~java
List<OrderSummary> orders = List.of();
boolean hasOrders = !orders.isEmpty();
~~~

Trả `List.of()` thay vì `null` giúp bên gọi duyệt và đếm an toàn hơn khi **không có phần tử** là trạng thái hợp lệ. Tuy nhiên, nếu truy vấn lỗi thì **không được trả danh sách rỗng** để che lỗi. Khi cần phân biệt “chưa tải” với “đã tải nhưng rỗng”, lưu thêm trạng thái tải.

## 5. Khi “không có dữ liệu” và “lỗi” đều là kết quả cần xử lý

Không phải mọi thất bại đều phải là ngoại lệ. Tùy API, có thể dùng:

- **`Optional<T>` + exception:** thích hợp khi không tìm thấy là tình huống bình thường, còn lỗi hạ tầng cần truyền lên và xử lý ở ranh giới cao hơn.
- **Kiểu kết quả nhiều nhánh (result type):** thích hợp khi caller cần xử lý rõ “tìm thấy”, “không tìm thấy”, “không khả dụng” như các nhánh thuộc hợp đồng.
- **Exception riêng:** phù hợp với lỗi không được mong đợi ở luồng thành công, nhưng cần phân biệt những loại lỗi quan trọng.

Ví dụ Java 17 dùng `sealed interface` và `record`:

~~~java
import java.util.Objects;

sealed interface FetchResult<T>
        permits Found, Missing, Failed {}

record Found<T>(T value) implements FetchResult<T> {
    public Found {
        Objects.requireNonNull(value, "value");
    }
}

record Missing<T>() implements FetchResult<T> {}

record Failed<T>(String errorCode) implements FetchResult<T> {
    public Failed {
        Objects.requireNonNull(errorCode, "errorCode");
    }
}
~~~

Một phía gọi có thể xử lý ba trạng thái mà không suy từ null:

~~~java
static String describe(FetchResult<String> result) {
    if (result instanceof Found<?> found) {
        return "Tìm thấy: " + found.value();
    }
    if (result instanceof Missing<?>) {
        return "Không tìm thấy";
    }
    if (result instanceof Failed<?> failure) {
        return "Không thể tra cứu: " + failure.errorCode();
    }
    throw new IllegalStateException("Unknown result type");
}
~~~

Với kiểu kết quả có tham số generic, Java 17 chưa cho dùng một số dạng pattern matching theo kiểu tham số cụ thể do type erasure; dùng wildcard như trên và thiết kế API để tránh ép kiểu không an toàn.

**Không nhất thiết tạo result type cho mọi phương thức.** Mục đích là làm nhánh có ý nghĩa rõ, không tăng lớp một cách máy móc. Nếu thư viện đã có cơ chế biểu diễn thất bại đủ rõ, nên tận dụng nhất quán.

### 5.1. Phải giữ nguyên nguyên nhân lỗi

~~~java
try {
    return repository.findById(customerId);
} catch (DatabaseTimeoutException ex) {
    // Sai: timeout không có nghĩa là customer không tồn tại.
    return Optional.empty();
}
~~~

Đoạn trên là **phản ví dụ**, với `DatabaseTimeoutException` là loại exception minh họa. Thay vì trả empty, tầng dữ liệu nên giữ nguyên exception hoặc chuyển thành lỗi được định nghĩa rõ, kèm nguyên nhân để dễ chẩn đoán. Trên ranh giới API, có thể che chi tiết kỹ thuật khỏi người dùng nhưng vẫn ghi nhận ngữ cảnh cần thiết trong log có kiểm soát.

Trả về mã lỗi riêng cũng cần cân nhắc khi nào retry được và khi nào không. “Không tìm thấy”, “bị cấm truy cập”, “đầu vào sai” và “dịch vụ không khả dụng” không phải cùng một loại thất bại.

## 6. Trường JSON không được gửi khác trường có `null`

Đây là nơi mất thông tin rất dễ xảy ra khi triển khai cập nhật một phần hồ sơ.

Xét ba yêu cầu:

~~~json
{}
~~~

~~~json
{"nickname": null}
~~~

~~~json
{"nickname": "An"}
~~~

Nếu API quy định:

- **Không có khóa `nickname`:** giữ nguyên biệt danh hiện tại.
- **Có khóa và giá trị `null`:** xóa biệt danh, nếu nghiệp vụ cho phép.
- **Có khóa và chuỗi:** đặt biệt danh mới sau khi kiểm tra giá trị.

Thì đây là **ba trạng thái khác nhau**. Một DTO Java chỉ chứa `String nickname` và được deserialize để nhận `null` ở cả hai trường hợp đầu có thể làm **mất thông tin về sự hiện diện của thuộc tính**.

### 6.1. Một ví dụ Java tối giản phân biệt missing và null

Giả sử lớp parse JSON đã cung cấp `Map<String, Object>` và vẫn giữ khóa có giá trị null, có thể minh họa như sau:

~~~java
import java.util.Map;
import java.util.Objects;

final class ProfilePatch {
    private ProfilePatch() {}

    static String applyNickname(
            String currentNickname,
            Map<String, Object> patch
    ) {
        Objects.requireNonNull(patch, "patch");

        if (!patch.containsKey("nickname")) {
            return currentNickname; // Không gửi -> giữ nguyên.
        }

        Object raw = patch.get("nickname");
        if (raw == null) {
            return null; // Gửi null -> xóa, nếu API cho phép.
        }

        if (!(raw instanceof String nickname)) {
            throw new IllegalArgumentException("Nickname must be a string");
        }
        if (nickname.isBlank() || nickname.length() > 50) {
            throw new IllegalArgumentException("Invalid nickname");
        }
        return nickname;
    }
}
~~~

`containsKey("nickname")` cho biết khóa có tồn tại hay không; `get("nickname") == null` **không đủ** để phân biệt hai trường hợp. Khi thiết kế thật, thường nên dùng DTO/tầng parse có mô hình **`unchanged / clear / set`** thay vì cho `Map<String,Object>` lan vào domain. Đoạn ví dụ chỉ diễn giải hợp đồng PATCH; nó chưa kiểm tra toàn bộ JSON, quyền thay đổi hồ sơ, Unicode grapheme length hay persistence.

Không phải API nào cũng dùng null làm lệnh xóa. **JSON Merge Patch** có quy tắc riêng về null khi xóa thành viên đối tượng; **JSON Patch** biểu diễn thao tác bằng lệnh riêng; một API PATCH tùy biến có thể chọn quy tắc khác. Vì vậy phải xác định chính xác **Content-Type và hợp đồng cập nhật**, không mặc định mọi PATCH hoạt động như ví dụ.

### 6.2. Vắng mặt và null ở các vị trí khác nhau

| Ngữ cảnh | Vắng mặt | Có giá trị `null` | Điều cần làm rõ |
| --- | --- | --- | --- |
| POST tạo mới | Trường không được gửi | Trường có mặt, giá trị null | Có mặc định không? Trường bắt buộc hay tùy chọn? |
| PATCH cập nhật một phần | Không thay đổi (nếu hợp đồng quy định) | Xóa/gán null (nếu được phép) | Phải phân biệt presence và value |
| JSON response | Trường bị bỏ qua | Trường có mặt với null | Client có được phép suy một nghĩa chung không? |
| `Map<K,V>` Java | `containsKey(k) == false` | `containsKey(k) == true` và `get(k) == null` | `Map.get(k)` đơn lẻ không đủ |
| Biểu mẫu web | Không có input được gửi | Thường không có giá trị null bản địa như JSON | Cần quy tắc parse form cụ thể |
| Database | Không có hàng | Có hàng, cột mang SQL `NULL` | Tra cứu bản ghi và giá trị cột là hai cấp khác nhau |

### 6.3. Một enum/kiểu tổng thể có thể làm API dễ hiểu hơn

Trong use case nhận cập nhật, ta có thể mô hình hóa một trường bằng ba lệnh:

~~~java
sealed interface NicknameUpdate
        permits KeepNickname, ClearNickname, SetNickname {}

record KeepNickname() implements NicknameUpdate {}
record ClearNickname() implements NicknameUpdate {}
record SetNickname(String value) implements NicknameUpdate {
    public SetNickname {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("Nickname required");
        }
    }
}
~~~

Ưu điểm: phía domain không cần đoán `null` là “không gửi”, “xóa” hay “lỗi”; mỗi nhánh có tên rõ. Tầng API chịu trách nhiệm chuyển JSON thành một trong ba lệnh, còn tầng domain áp dụng quy tắc tương ứng.

Nếu thực tế chỉ có hai trạng thái và không tồn tại thao tác xóa, một kiểu ba nhánh có thể là phức tạp không cần thiết. **Số trạng thái trong mô hình nên khớp số trạng thái của nghiệp vụ.**

## 7. SQL `NULL` không giống hàng không tồn tại

Trong SQL, cột mang `NULL` thường đại diện giá trị chưa biết hoặc không áp dụng tùy mô hình. Một hàng tồn tại với cột null **khác** với việc truy vấn không trả hàng nào.

~~~sql
-- Có hàng với nickname NULL:
SELECT id, nickname
FROM customers
WHERE id = 123;

-- Đúng cách kiểm tra cột NULL:
SELECT id
FROM customers
WHERE nickname IS NULL;

-- Không dùng = NULL để kiểm tra thiếu:
SELECT id
FROM customers
WHERE nickname = NULL;
~~~

SQL sử dụng **logic ba giá trị** cho nhiều biểu thức: `TRUE`, `FALSE` và `UNKNOWN`. So sánh thông thường với `NULL` thường tạo `UNKNOWN`, nên điều kiện `WHERE nickname = NULL` không chọn các hàng null như người mới có thể kỳ vọng.

Cần chú ý:

- `COUNT(*)` đếm hàng; `COUNT(nickname)` chỉ đếm các giá trị `nickname` không-null. Chúng có thể khác nhau dù truy vấn cùng một tập hàng.
- `COALESCE(nickname, 'Khách hàng')` thay null bằng giá trị hiển thị trong truy vấn, nhưng có thể che sự khác biệt cần thiết ở tầng nghiệp vụ.
- Ràng buộc `NOT NULL` chỉ ngăn SQL null, **không tự kiểm tra** chuỗi rỗng, khoảng trắng hay giá trị nghiệp vụ bất hợp lệ.
- Ngữ nghĩa của unique index với null và một số phép toán phụ thuộc hệ quản trị CSDL; không giả định cùng hành vi cho tất cả database.

### JDBC: giá trị nguyên thủy và `wasNull()`

Với JDBC, một số getter kiểu nguyên thủy trả giá trị mặc định khi cột SQL là NULL. Muốn phân biệt **SQL null với giá trị thật là 0**, cần gọi `ResultSet.wasNull()` ngay sau getter liên quan:

~~~java
int creditLimit = resultSet.getInt("credit_limit");
boolean missingCreditLimit = resultSet.wasNull();

if (missingCreditLimit) {
    // Giá trị SQL NULL; không được hiểu là hạn mức bằng 0.
} else {
    // creditLimit có thể bằng 0 một cách hợp lệ.
}
~~~

Đây là trích đoạn bên trong mã xử lý `ResultSet`, không phải chương trình độc lập. Các ORM và kiểu mapping khác có cơ chế riêng; người lập trình cần xem hợp đồng thư viện đang dùng.

## 8. “Chưa tải”, “không tìm thấy” và “lỗi tải” trong bộ nhớ/cache

Một giá trị trong cache có thể nằm ở các tình trạng:

1. **Chưa kiểm tra cache/nguồn**.
2. **Đang tải**.
3. **Đã tải và tìm thấy giá trị**.
4. **Đã tải và chắc chắn không có giá trị** (negative cache, nếu thiết kế hỗ trợ).
5. **Tải thất bại**.

Nếu chỉ lưu `Map<Id, Data>` và để `get(id) == null` biểu thị tất cả, chương trình không biết cần tải thêm, hiển thị “không tìm thấy” hay báo lỗi. Việc lưu một marker cho negative cache cần thời hạn hợp lý vì bản ghi mới có thể xuất hiện sau đó.

~~~mermaid
stateDiagram-v2
    [*] --> NotLoaded
    NotLoaded --> Loading: bắt đầu tải
    Loading --> Loaded: nhận giá trị
    Loading --> NotFound: truy vấn thành công nhưng trống
    Loading --> Failed: timeout / lỗi
    Failed --> Loading: thử lại theo chính sách
    NotFound --> Loading: hết hạn cache / làm mới
    Loaded --> Loading: cần làm mới
~~~

Không nhất thiết mọi hệ thống phải lưu đủ trạng thái nêu trên. Nhưng một giao diện hiển thị dữ liệu bất đồng bộ thường phải phân biệt ít nhất **loading / success / empty / error** để không đánh lừa người dùng.

### Không suy diễn lỗi thành vắng mặt

Ví dụ dịch vụ tra cứu kho hàng không phản hồi. Trả `Optional.empty()` có thể khiến hệ thống giả định “không có sản phẩm” hoặc “hết tồn kho” và đưa ra quyết định sai. Nếu dữ liệu quá hạn nhưng vẫn được cho phép dùng tạm, hãy mô tả rõ đó là **dữ liệu cache cũ** với thời điểm cập nhật và chính sách chấp nhận rủi ro, không giả vờ rằng truy vấn mới thành công.

## 9. Giá trị mặc định, sentinel và Null Object: dùng có chủ đích

### 9.1. Giá trị mặc định

`defaultIfNull(value, 0)` có vẻ giúp tránh `NullPointerException`, nhưng chỉ an toàn khi `0` thật sự là mặc định nghiệp vụ. Nếu `0` là “giá trị thật”, việc thay null bằng 0 che mất trạng thái chưa biết.

~~~java
// Ví dụ sai nếu null nghĩa là chưa biết hạn mức:
long creditLimit = rawLimit == null ? 0L : rawLimit;
~~~

Mặc định hợp lý có thể là **ngôn ngữ hiển thị**, **số mục trên mỗi trang** hoặc một tùy chọn giao diện, nếu hợp đồng đã xác định. Không nên tự thay trạng thái thất bại bằng mặc định thành công.

### 9.2. Sentinel value

`-1`, `"UNKNOWN"` hay `Long.MIN_VALUE` đôi khi được dùng làm giá trị đặc biệt. Cách này cần đảm bảo sentinel **không thể là giá trị hợp lệ** và mọi nơi đều hiểu thống nhất. Nếu không, một phép tính hoặc chuyển đổi có thể vô tình biến sentinel thành dữ liệu thật.

Kiểu có nghĩa như `OptionalLong`, `enum` hoặc `record` thường dễ đọc hơn với dữ liệu nghiệp vụ quan trọng.

### 9.3. Null Object pattern

Một đối tượng “không làm gì” có thể hữu ích cho các hành vi phụ trợ:

~~~java
interface Notifier {
    void send(String message);
}

final class NoOpNotifier implements Notifier {
    @Override
    public void send(String message) {
        // Cố ý không gửi thông báo theo cấu hình này.
    }
}
~~~

`NoOpNotifier` là lựa chọn có ý nghĩa khi nghiệp vụ **cho phép không gửi thông báo**. Nó không phù hợp nếu thông báo là bắt buộc theo hợp đồng. Null Object có thể cải thiện khả năng đọc và giảm kiểm tra null lặp lại, nhưng cũng có thể che lỗi cấu hình nếu áp dụng sai.

## 10. Ví dụ xuyên suốt: tra cứu và cập nhật biệt danh khách hàng

Giả sử hệ thống cho phép đọc hồ sơ và cập nhật biệt danh tùy chọn.

**Hợp đồng đọc:**

- Khách hàng tồn tại, biệt danh có thể null: trả hồ sơ, thể hiện rõ dữ liệu tùy chọn.
- Khách hàng không tồn tại: kết quả “không tìm thấy”.
- Database không khả dụng: lỗi, không được trả “không tìm thấy”.

**Hợp đồng PATCH:**

- Không gửi `nickname`: giữ nguyên.
- Gửi `nickname: null`: xóa biệt danh nếu được phép.
- Gửi `nickname: "An"`: cập nhật sau validation.
- Gửi `nickname: ""`: từ chối hoặc xử lý theo quy tắc nghiệp vụ đã chọn.

Một thiết kế nguy hiểm là:

~~~java
Customer load(long id) {
    try {
        return repository.findById(id).orElse(null);
    } catch (RuntimeException ignored) {
        return null; // Gộp lỗi hạ tầng với không tìm thấy.
    }
}
~~~

Đoạn mã này làm caller không biết vì sao kết quả null. Việc bắt tất cả `RuntimeException` còn che cả lỗi lập trình, khiến chẩn đoán khó khăn hơn.

Thiết kế có hợp đồng rõ hơn:

~~~java
Optional<Customer> findCustomer(long id) {
    // Repository chỉ trả empty nếu tra cứu thành công nhưng không có bản ghi.
    // Lỗi truy cập dữ liệu phải được chuyển thành lỗi tương ứng.
    return repository.findById(id);
}

// Phần cập nhật chỉ nhận trạng thái sau khi tầng HTTP đã parse/validate:
// KeepNickname, ClearNickname hoặc SetNickname.
~~~

Ở đây hai đoạn là minh họa hợp đồng: `repository` là phụ thuộc của service, còn các kiểu lệnh cập nhật được định nghĩa ở phần 6.3. Khi triển khai đầy đủ, cần thêm kiểm tra quyền sở hữu, xác thực, xử lý cạnh tranh cập nhật và transaction. Bài học tập trung vào **đúng đắn của trạng thái dữ liệu**, không thay thế thiết kế bảo mật hay tính nhất quán giao dịch.

### Bảng kết quả mong đợi

| Đầu vào/sự kiện | Trạng thái đúng | Điều không được xảy ra |
| --- | --- | --- |
| GET ID có hồ sơ, biệt danh null | Có hồ sơ; biệt danh chưa được đặt | Trả 404 chỉ vì biệt danh null |
| GET ID không có hồ sơ | Not found | Trả hồ sơ mặc định như thể đã lưu |
| GET khi database timeout | Failure | Trả empty/404 như một tra cứu thành công |
| PATCH `{}` | Giữ nguyên biệt danh | Tự xóa biệt danh |
| PATCH `{"nickname":null}` | Xóa biệt danh nếu được phép | Bỏ qua lệnh xóa do không phân biệt missing |
| PATCH `{"nickname":"An"}` | Đặt biệt danh mới | Ghi giá trị thiếu kiểm tra |
| PATCH `{"nickname":""}` | Theo chính sách: từ chối hoặc chấp nhận | Âm thầm thay bằng null nếu hợp đồng cấm |

## 11. Kiểm thử để không đánh đồng các trạng thái

Một bộ kiểm thử tốt cần chọn các **tình huống khác nhau về ngữ nghĩa**, không chỉ những đầu vào dễ viết.

Ví dụ JUnit 5 cho `ProfilePatch.applyNickname` từ phần 6.1:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;
import java.util.HashMap;
import java.util.Map;

class ProfilePatchTest {
    @Test
    void missingFieldKeepsCurrentValue() {
        assertEquals("Cũ",
                ProfilePatch.applyNickname("Cũ", Map.of()));
    }

    @Test
    void explicitNullClearsValue() {
        Map<String, Object> patch = new HashMap<>();
        patch.put("nickname", null); // Map.of không cho null.
        assertNull(ProfilePatch.applyNickname("Cũ", patch));
    }

    @Test
    void providedValueReplacesCurrent() {
        assertEquals("Mới",
                ProfilePatch.applyNickname("Cũ",
                        Map.of("nickname", "Mới")));
    }

    @Test
    void blankOrWrongTypeIsRejected() {
        assertThrows(IllegalArgumentException.class,
                () -> ProfilePatch.applyNickname(
                        "Cũ", Map.of("nickname", "")));
        assertThrows(IllegalArgumentException.class,
                () -> ProfilePatch.applyNickname(
                        "Cũ", Map.of("nickname", 123)));
    }
}
~~~

Tình huống truy vấn cần tách riêng:

| Test | Điều phải khẳng định |
| --- | --- |
| Repository trả `Optional.of(customer)` | Service trả khách hàng, dù trường tùy chọn bên trong null |
| Repository trả `Optional.empty()` | Service xử lý “không có bản ghi” theo hợp đồng |
| Repository ném lỗi kết nối/timeout | Lỗi được truyền hoặc ánh xạ đúng, **không thành empty** |
| Map có khóa với giá trị null | Khác Map không có khóa |
| SQL cột NULL | Không bị hiểu thành giá trị nguyên thủy 0 |
| Phản hồi lỗi bên ngoài | Không bị ghi cache như kết quả “không tìm thấy” |
| Cache đã có negative entry | Khi hết hạn có thể kiểm tra lại nguồn |

Đối với test tích hợp, cần xác minh cách thư viện JSON thực sự deserialize **missing và explicit null**, cũng như cách ORM ánh xạ SQL `NULL`. Các unit test chỉ dùng `Map` không chứng minh được parser ngoài thực tế bảo toàn thông tin hiện diện của trường.

## 12. Checklist code review khi gặp null và dữ liệu vắng mặt

- [ ] Tôi biết `null` mang nghĩa gì ở từng field/giá trị trả về, và liệu hợp đồng có cho phép nó không.
- [ ] Tôi phân biệt “không có bản ghi” với “có bản ghi nhưng trường tùy chọn null”.
- [ ] Tôi phân biệt “chưa tải” với “đã tải xong nhưng không có kết quả”.
- [ ] Tôi phân biệt tra cứu thành công nhưng rỗng với timeout/lỗi hạ tầng.
- [ ] Tôi không vô tình biến `0`, `false`, `""` hoặc collection rỗng thành giá trị vắng mặt.
- [ ] Với API cập nhật một phần, tôi phân biệt trường không được gửi và trường được gửi với null.
- [ ] Tôi không dùng `Map.get()` đơn lẻ khi cần biết khóa có tồn tại.
- [ ] Tôi không trả `Optional.empty()` trong catch block chỉ để che lỗi.
- [ ] Giá trị mặc định hoặc Null Object thực sự được nghiệp vụ cho phép.
- [ ] Tôi đã kiểm tra ranh giới JSON, database, cache và dịch vụ ngoài nếu dữ liệu đi qua chúng.
- [ ] Kiểm thử có tình huống thất bại, missing, null, rỗng và giá trị hợp lệ khi các trạng thái ấy khác nhau về ý nghĩa.

Các dấu hiệu cần chú ý khi đọc code là tên `getOrNull()` không có hợp đồng, `catch (Exception) { return null; }`, `Optional.ofNullable(...)` đặt ngay sau mọi nguồn dữ liệu, dùng `COALESCE` không có lý do và các if/else dài cố suy nghĩa từ một giá trị sentinel.

## 13. Những ngộ nhận thường gặp

**“`null` luôn là lỗi.”** Trong một số hợp đồng, null là biểu diễn hợp lệ của trường tùy chọn; vấn đề là ý nghĩa có rõ và nhất quán hay không.

**“Trả `Optional.empty()` thì luôn an toàn.”** Empty chỉ nên biểu diễn sự vắng mặt bình thường. Lỗi hạ tầng bị chuyển thành empty làm hệ thống mất tín hiệu lỗi.

**“Chuỗi rỗng và null giống nhau.”** `""` là một đối tượng chuỗi có độ dài 0; null không tham chiếu đến chuỗi. Nghiệp vụ có thể cố tình gộp khi hiển thị, nhưng không thể tự gộp trong mọi trường hợp.

**“`Map.get(key) == null` chứng minh không tồn tại khóa.”** Với Map hỗ trợ giá trị null, khóa có thể hiện diện và ánh xạ tới null.

**“API PATCH thiếu trường và gửi trường bằng null là một.”** Hai trạng thái có thể có lệnh nghiệp vụ khác nhau; cần giữ thông tin đó qua parse/DTO.

**“SQL `NULL` và không có hàng là một.”** Một hàng có cột NULL vẫn tồn tại; việc tìm bản ghi và đọc giá trị cột là hai bước khác nhau.

**“Dùng giá trị mặc định sẽ giúp xử lý lỗi dễ hơn.”** Mặc định sai có thể biến mất dữ liệu/lỗi thành kết quả thành công giả.

**“Nếu đã kiểm tra null thì dữ liệu chắc chắn hợp lệ.”** Còn phải kiểm tra miền giá trị, nội dung, quyền truy cập, nhất quán và các ràng buộc khác.

## 14. Câu hỏi tự kiểm tra

1. Một API tra cứu sản phẩm trả `null` khi không có sản phẩm và cũng trả `null` khi database timeout. Điều gì có thể sai ở tầng gọi? Bạn sẽ sửa hợp đồng thế nào?
2. Vì sao `Optional<Customer>` có thể hợp lý làm kiểu trả về `findById()` nhưng không đủ để biểu diễn cả “không tìm thấy” và “không thể truy vấn” nếu cả hai đều được trả thành empty?
3. So sánh `null`, `""`, `List.of()`, `0` và `false`. Khi nào chúng là dữ liệu hợp lệ?
4. Với PATCH `{}` và PATCH `{"nickname":null}`, phương thức nhận dữ liệu cần giữ thông tin nào để thực hiện đúng hai thao tác khác nhau?
5. Vì sao `Map.containsKey(k)` quan trọng khi `Map.get(k)` trả null?
6. Một câu SQL `WHERE nickname = NULL` có tìm được các hàng chứa SQL NULL không? Nên viết gì?
7. Trong JDBC, làm sao phân biệt cột số nguyên SQL NULL với giá trị thật bằng 0?
8. Có nên dùng `COALESCE(discount, 0)` trong mọi trường hợp? Hãy nêu một ngữ cảnh làm vậy là đúng và một ngữ cảnh gây sai.
9. Cache chứa negative entry nhưng nguồn dữ liệu sau đó có thêm bản ghi. Cần yếu tố nào để tránh giữ kết luận “không tìm thấy” mãi mãi?
10. Hãy đề xuất ít nhất năm test cho luồng “tìm hồ sơ và cập nhật biệt danh”, bao gồm lỗi hạ tầng và explicit null.

## Ghi nhớ

**`null` là biểu diễn, còn “vắng dữ liệu” và “lỗi” là những trạng thái có ý nghĩa khác nhau.** Mã nguồn đáng tin cậy phải nói rõ khi nào dữ liệu không được gửi, không tồn tại, chưa tải, rỗng hoặc không thể truy xuất. Chọn `Optional`, exception, kiểu kết quả tường minh hay giá trị mặc định theo đúng hợp đồng; giữ nguyên sự phân biệt qua JSON, Java, SQL và cache; kiểm tra các nhánh này để hành vi đúng và dễ thay đổi.
