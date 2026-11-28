# Điều kiện `if` và tổ chức nhánh rõ ràng

Trong Java 27, câu lệnh `if` quyết định khối mã nào được thực hiện dựa trên một điều kiện đúng hoặc sai. Đây là công cụ điều khiển luồng cơ bản cho kiểm tra dữ liệu đầu vào, xử lý trạng thái, áp dụng quy tắc nghiệp vụ và chọn hành vi của chương trình. Viết được `if` là bước đầu; thiết kế các nhánh **dễ đọc, không chồng chéo và xử lý đủ trường hợp** mới là kỹ năng quan trọng khi phát triển phần mềm.

Bài học thuộc chương **Điều khiển luồng** của module **JAVA_VERSION_JAVA27 (Java 27 và các kiến thức liên quan)**. Các ví dụ sử dụng cú pháp và API vẫn được hỗ trợ trong Java 27, không dựa trên tính năng preview hay cách viết đã lỗi thời.

## 1. `if` đánh giá điều kiện như thế nào?

Cấu trúc cơ bản:

```java
if (condition) {
    // Chạy khi condition là true.
}
```

Biểu thức `condition` phải có kiểu `boolean` hoặc `Boolean`. Nếu kết quả là `true`, thân `if` được thực thi; nếu là `false`, JVM bỏ qua thân `if` và tiếp tục lệnh phía sau. Java không tự chuyển số, chuỗi hoặc đối tượng thành giá trị đúng/sai như một số ngôn ngữ khác.

```java
int stock = 3;

if (stock > 0) {
    System.out.println("Có thể nhận đơn hàng");
}
```

Ví dụ không hợp lệ:

```java
int stock = 3;

// Không biên dịch: int không tự chuyển thành boolean.
// if (stock) { ... }
```

Điều kiện được đánh giá ở thời điểm chương trình đi tới câu lệnh `if`, không phải một lần cho toàn bộ chương trình. Nếu việc đánh giá biểu thức ném ngoại lệ, nhánh `if` không tiếp tục chạy như bình thường; ngoại lệ được truyền theo quy tắc xử lý ngoại lệ của Java.

### 1.1. `if` kết hợp với `else`

Khi có đúng hai hướng xử lý loại trừ nhau, dùng `if`–`else`:

```java
boolean paid = true;

if (paid) {
    System.out.println("Đơn hàng đã thanh toán");
} else {
    System.out.println("Đơn hàng chưa thanh toán");
}
```

Trong một lần thực thi, chương trình chỉ chọn **một** trong hai nhánh. `else` không có điều kiện riêng: nó chạy khi điều kiện của `if` là `false`.

### 1.2. Nhiều nhánh với `else if`

Trong Java, `else if` là cách viết nối tiếp một câu lệnh `if` nằm trong nhánh `else` trước đó; nó cho phép biểu diễn chuỗi quyết định dễ đọc:

```java
int score = 84;

if (score < 0 || score > 100) {
    System.out.println("Điểm không hợp lệ");
} else if (score >= 90) {
    System.out.println("Xuất sắc");
} else if (score >= 70) {
    System.out.println("Đạt tốt");
} else if (score >= 50) {
    System.out.println("Đạt");
} else {
    System.out.println("Chưa đạt");
}
```

Điều kiện được xét **từ trên xuống dưới**. Khi gặp nhánh đầu tiên có điều kiện `true`, chương trình chạy nhánh đó rồi bỏ qua các nhánh còn lại trong chuỗi. Nếu tất cả điều kiện là `false`, nhánh `else` cuối cùng (nếu có) được thực thi. Nhờ đã kiểm tra `score >= 90` ở trên, nhánh `score >= 70` không cần viết thêm `score < 90`.

Với ngưỡng điểm, thứ tự rất quan trọng: nếu kiểm tra `score >= 50` trước `score >= 90`, điểm 95 sẽ rơi vào nhánh “Đạt” và không bao giờ tới nhánh “Xuất sắc”.

## 2. Phân biệt các `if` độc lập và chuỗi `if`–`else if`

Hai câu lệnh `if` độc lập có thể **đều** chạy nếu cả hai điều kiện đúng:

```java
boolean priorityCustomer = true;
int orderTotal = 2_000_000;

if (priorityCustomer) {
    System.out.println("Tặng điểm thưởng");
}

if (orderTotal >= 1_000_000) {
    System.out.println("Miễn phí vận chuyển");
}
```

Ở ví dụ này, khách hàng được cả hai quyền lợi nên dùng hai `if` là phù hợp. Nếu thay câu lệnh thứ hai bằng `else if`, khách hàng ưu tiên sẽ không được kiểm tra điều kiện miễn phí vận chuyển.

| Yêu cầu nghiệp vụ | Cách tổ chức | Lý do |
|---|---|---|
| Có thể áp dụng nhiều quy tắc cùng lúc | Nhiều `if` độc lập | Mỗi điều kiện có thể kích hoạt một hành động |
| Chỉ chọn một kết quả trong nhiều mức ưu tiên | `if`–`else if`–`else` | Nhánh khớp đầu tiên quyết định kết quả |
| Chỉ có hai kết quả đối lập | `if`–`else` | Bao phủ hai khả năng của một điều kiện boolean |
| Dữ liệu không hợp lệ phải dừng xử lý sớm | `if` + `return`/`throw` | Tách kiểm tra đầu vào khỏi luồng nghiệp vụ chính |

Quyết định cấu trúc trước khi viết mã: **các hành động có được phép xảy ra đồng thời không?** Nếu có, các `if` độc lập thường diễn đạt đúng ý hơn; nếu không, cân nhắc chuỗi nhánh loại trừ nhau.

## 3. Xây dựng điều kiện boolean an toàn

### 3.1. Toán tử so sánh và logic

| Toán tử | Ý nghĩa | Ví dụ |
|---|---|---|
| `==`, `!=` | Bằng, khác bằng đối với giá trị nguyên thủy; so sánh tham chiếu đối với đối tượng | `quantity == 0` |
| `<`, `<=`, `>`, `>=` | So sánh thứ tự của giá trị số hoặc kiểu tương ứng | `age >= 18` |
| `&&` | Và logic, dừng đánh giá khi vế trái `false` | `age >= 18 && verified` |
| `||` | Hoặc logic, dừng đánh giá khi vế trái `true` | `isAdmin || isOwner` |
| `!` | Phủ định logic | `!paid` |

Ví dụ kiểm tra một số nằm trong khoảng:

```java
int quantity = 8;

if (quantity >= 1 && quantity <= 100) {
    System.out.println("Số lượng hợp lệ");
}
```

Java không hỗ trợ cách viết gộp `1 <= quantity <= 100`; cần tạo **hai** phép so sánh và nối bằng `&&`.

Khi kết hợp nhiều điều kiện, nên dùng dấu ngoặc để truyền đạt chủ ý, kể cả khi người viết biết quy tắc ưu tiên toán tử:

```java
boolean canApprove = isManager && (hasBudget || hasOverride);

if (canApprove) {
    System.out.println("Có quyền phê duyệt");
}
```

Tên `canApprove` thể hiện ý nghĩa nghiệp vụ rõ hơn một biểu thức dài nằm trực tiếp trong `if`.

### 3.2. Short-circuit giúp tránh lỗi truy cập `null`

`&&` và `||` thực hiện **short-circuit evaluation** (đánh giá đoản mạch). Với `&&`, nếu vế trái sai thì vế phải không được đánh giá; với `||`, nếu vế trái đúng thì vế phải không được đánh giá.

```java
String email = null;

if (email != null && !email.isBlank()) {
    System.out.println(email.toLowerCase());
}
```

Vì `email != null` là `false`, phần `email.isBlank()` không chạy; chương trình tránh được `NullPointerException`. Thứ tự vế trái và phải phải được giữ đúng:

```java
// Sai: có thể gọi isBlank() trên null trước khi kiểm tra null.
// if (!email.isBlank() && email != null) { ... }
```

Với `||`, có thể viết một điều kiện từ chối dữ liệu:

```java
if (email == null || email.isBlank()) {
    System.out.println("Email bắt buộc");
}
```

`&` và `|` cũng có thể áp dụng lên các giá trị `boolean`, nhưng **luôn đánh giá cả hai vế**. Vì thế, khi diễn đạt điều kiện điều khiển luồng và cần kiểm tra an toàn theo thứ tự, `&&` và `||` thường là lựa chọn thích hợp.

### 3.3. So sánh chuỗi và đối tượng đúng cách

`==` giữa hai tham chiếu đối tượng kiểm tra chúng có trỏ tới cùng một đối tượng hay không. Khi cần so sánh **nội dung** của chuỗi, dùng `.equals()` hoặc `.equalsIgnoreCase()` nếu nghiệp vụ cho phép bỏ qua khác biệt hoa/thường:

```java
String status = "READY";

if ("READY".equals(status)) {
    System.out.println("Sẵn sàng xử lý");
}
```

Viết hằng chuỗi ở bên trái giúp biểu thức trả về `false` thay vì ném ngoại lệ khi `status == null`. Với hai tham chiếu bất kỳ, `java.util.Objects.equals(left, right)` là lựa chọn so sánh nội dung có xử lý `null` an toàn nếu kiểu dữ liệu triển khai `equals` phù hợp.

### 3.4. Chú ý kiểu `Boolean` có thể nhận `null`

Điều kiện `if` chấp nhận `Boolean`, nhưng Java phải **unbox** thành `boolean` để quyết định nhánh. Nếu giá trị là `null`, thao tác này ném `NullPointerException`:

```java
Boolean approved = null;

// Có thể ném NullPointerException:
// if (approved) { ... }

if (Boolean.TRUE.equals(approved)) {
    System.out.println("Đã duyệt");
}
```

`Boolean.TRUE.equals(approved)` phù hợp khi nghiệp vụ quy định chỉ `true` mới được xử lý, còn `false` và `null` cùng là “chưa được duyệt”. Nếu `null` mang ý nghĩa “chưa biết” và cần xử lý riêng, hãy viết nhánh phân biệt thay vì âm thầm xem nó là `false`.

## 4. Tổ chức nhánh để người đọc hiểu ngay

### 4.1. Luôn dùng dấu ngoặc nhọn `{}`

Java cho phép `if` không có `{}` khi phần thân chỉ gồm một câu lệnh, nhưng cách viết đó dễ làm người bảo trì hiểu sai vị trí của lệnh mới được thêm vào.

```java
// Dễ nhầm: chỉ lệnh đầu tiên thuộc if.
if (hasPermission)
    saveDocument();
    auditChange();
```

`auditChange()` ở ví dụ trên **luôn chạy**. Cách viết rõ ràng:

```java
if (hasPermission) {
    saveDocument();
    auditChange();
}
```

Dấu ngoặc còn làm rõ một quy tắc cú pháp: nếu có nhiều `if` lồng nhau mà thiếu `{}`, từ khóa `else` gắn với `if` gần nhất chưa có `else` (*dangling else*). Dùng khối `{}` để biểu đạt đúng cây quyết định và tránh phải suy từ độ thụt lề.

### 4.2. Dùng guard clause để kiểm tra đầu vào sớm

Một **guard clause** là điều kiện kiểm tra ngoại lệ hoặc tiền điều kiện ở đầu phương thức, thường kết thúc bằng `return` hoặc `throw`. Nó giúp giảm số tầng `if` lồng nhau và làm luồng xử lý chính nổi bật.

```java
static String shipmentStatus(String customerId, int quantity, boolean paid) {
    if (customerId == null || customerId.isBlank()) {
        return "Thiếu mã khách hàng";
    }
    if (quantity <= 0) {
        return "Số lượng phải lớn hơn 0";
    }
    if (!paid) {
        return "Chờ thanh toán";
    }

    return "Sẵn sàng giao hàng";
}
```

Đoạn mã có hai tầng ý nghĩa: **loại bỏ trường hợp không thể tiếp tục**, rồi trả về kết quả chính. Mỗi guard xử lý một điều kiện rõ ràng. Không cần viết `else` sau `return` vì nhánh trước đã kết thúc phương thức.

Guard clause chỉ phù hợp khi thoát sớm không bỏ qua thao tác bắt buộc. Chẳng hạn, với giao dịch cơ sở dữ liệu hoặc tài nguyên cần giải phóng, phải bảo đảm việc đóng tài nguyên bằng cấu trúc quản lý vòng đời tương ứng (như `try`-with-resources).

### 4.3. Sắp xếp nhánh theo ý nghĩa và độ ưu tiên

Một thứ tự dễ hiểu cho nhiều quy tắc nghiệp vụ là:

1. Kiểm tra dữ liệu đầu vào không hợp lệ.
2. Xử lý điều kiện ngăn thao tác tiếp tục, như thiếu quyền hoặc chưa thanh toán.
3. Xét những ngoại lệ hoặc trường hợp ưu tiên cao.
4. Xử lý trường hợp thông thường.

Không phải mọi bài toán đều tuân theo đúng thứ tự này. Điều quyết định là **ưu tiên nghiệp vụ** phải hiện rõ và không để nhánh rộng bắt mất dữ liệu của nhánh hẹp.

Ví dụ, nhánh `amount >= 500_000` phải nằm **sau** nhánh `amount >= 2_000_000` nếu cả hai thuộc cùng chuỗi `else if` và mức chiết khấu cao hơn cần được ưu tiên.

### 4.4. Đặt tên cho quy tắc thay vì lặp điều kiện phức tạp

Khi một điều kiện có ý nghĩa riêng trong nghiệp vụ, đặt tên bằng biến `boolean` hoặc phương thức có tên rõ ràng:

```java
boolean isLargeOrder = itemCount >= 10;
boolean isPriorityCustomer = customerTier >= 3;

if (isLargeOrder || isPriorityCustomer) {
    System.out.println("Chuyển sang hàng đợi ưu tiên");
}
```

Tránh đặt tên mơ hồ như `flag`, `check`, `x` hoặc phủ định chồng nhau như `!notAllowed`. Nếu điều kiện dựa vào trạng thái có thể thay đổi, nên bảo đảm biến trung gian được tính vào đúng thời điểm, tránh dùng kết quả đã cũ.

## 5. `if` hiện đại với pattern matching `instanceof`

Java 27 tiếp tục hỗ trợ **type pattern** trong `instanceof`, tính năng đã chính thức từ Java 16. Cách viết này vừa kiểm tra kiểu của đối tượng, vừa tạo biến có kiểu tương ứng khi pattern khớp:

```java
static String displayName(Object value) {
    if (value instanceof String text && !text.isBlank()) {
        return text.trim();
    }
    return "Chưa có tên hợp lệ";
}
```

Ở đây, `text` chỉ được sử dụng sau khi phép kiểm tra `value instanceof String text` khớp. Toán tử `&&` bảo đảm `text` có giá trị trước khi gọi `isBlank()`; biểu thức `instanceof` đối với `null` trả về `false`.

Phạm vi của biến pattern phụ thuộc vào **luồng điều khiển**, không chỉ vào dấu ngoặc. Ví dụ guard clause sau hợp lệ:

```java
static int textLength(Object value) {
    if (!(value instanceof String text)) {
        return 0;
    }

    return text.length();
}
```

Sau khi nhánh `return 0` kết thúc, chỉ còn khả năng pattern đã khớp, nên `text` có thể được sử dụng. Tránh giả định rằng biến pattern luôn dùng được ở nhánh `else`, hoặc sau một biểu thức `||` có thể đúng mà không cần pattern khớp; trình biên dịch Java kiểm soát những trường hợp này.

## 6. Ví dụ hoàn chỉnh: quyết định xử lý đơn hàng

Ví dụ sau dùng `record` (cú pháp đã ổn định trong Java 27), guard clause và chuỗi quyết định loại trừ nhau. Tệp `OrderDecision.java` có thể chạy trực tiếp bằng `java OrderDecision.java` trên JDK 27:

```java
public class OrderDecision {
    record Order(String customerId, int quantity, boolean paid, boolean priority) {}

    static String decide(Order order) {
        if (order == null) {
            return "LỖI: Thiếu đơn hàng";
        }
        if (order.customerId() == null || order.customerId().isBlank()) {
            return "LỖI: Mã khách hàng không hợp lệ";
        }
        if (order.quantity() <= 0) {
            return "LỖI: Số lượng không hợp lệ";
        }
        if (!order.paid()) {
            return "Chờ thanh toán";
        }

        if (order.priority() || order.quantity() >= 10) {
            return "Chuyển xử lý ưu tiên";
        }

        return "Xử lý tiêu chuẩn";
    }

    public static void main(String[] args) {
        System.out.println(decide(new Order("KH01", 2, true, false)));
        System.out.println(decide(new Order("KH02", 12, true, false)));
        System.out.println(decide(new Order("KH03", 3, false, true)));
    }
}
```

Chạy chương trình:

```bash
java --version
java OrderDecision.java
```

Kết quả:

```text
Xử lý tiêu chuẩn
Chuyển xử lý ưu tiên
Chờ thanh toán
```

Thứ tự này phản ánh quy tắc: **đơn chưa thanh toán không được xử lý ưu tiên**, dù `priority == true`. Chỉ sau khi bảo đảm đơn hợp lệ và đã thanh toán, chương trình mới đánh giá điều kiện ưu tiên.

Trong ứng dụng thực tế, tùy yêu cầu API, lỗi dữ liệu đầu vào có thể được thể hiện bằng exception hoặc kiểu kết quả riêng thay vì chuỗi. Ví dụ trên chủ ý giữ kết quả đơn giản để tập trung vào luồng `if`.

## 7. Khi nào nên dùng `if`, toán tử ba ngôi hoặc `switch`?

`if` thường phù hợp nhất khi điều kiện là phép so sánh ngưỡng, kiểm tra quyền, kết hợp nhiều mệnh đề hoặc cần thực hiện hành động khác nhau. Với lựa chọn **một giá trị rất đơn giản** giữa hai trường hợp, có thể dùng biểu thức ba ngôi `condition ? whenTrue : whenFalse`:

```java
String label = paid ? "Đã thanh toán" : "Chưa thanh toán";
```

Đừng lồng nhiều toán tử ba ngôi chỉ để thay thế một chuỗi `if`–`else if`: mã sẽ khó đọc và khó kiểm tra điều kiện ưu tiên. Khi nhiều nhánh cùng xét **một giá trị phân loại** (như `enum` hoặc một tập nhãn trạng thái), `switch` expression của Java hiện đại đôi khi rõ ràng hơn. Ví dụ, bên trong một lớp có thể khai báo:

```java
enum State { NEW, PAID, SHIPPED }

static String label(State state) {
    return switch (state) {
        case NEW -> "Mới tạo";
        case PAID -> "Đã thanh toán";
        case SHIPPED -> "Đã giao";
    };
}
```

`switch` expression với `enum` có thể được kiểm tra tính đầy đủ các trường hợp ở thời điểm biên dịch; ví dụ trên chỉ dành cho giá trị `state` khác `null`. Nếu đầu vào có thể là `null`, hãy quy định cách xử lý nó rõ ràng. Giữ `if` cho các điều kiện dạng khoảng, tổ hợp boolean và guard clause; chọn cấu trúc mô tả đúng bài toán nhất.

## 8. Những lỗi thường gặp và cách phòng tránh

| Lỗi | Hậu quả | Cách khắc phục |
|---|---|---|
| Đặt điều kiện rộng trước điều kiện hẹp trong `else if` | Nhánh cụ thể không bao giờ chạy | Xếp điều kiện theo ưu tiên và kiểm tra ngưỡng biên |
| Dùng các `if` độc lập cho các trường hợp phải loại trừ nhau | Nhiều hành động cùng chạy ngoài ý muốn | Dùng `if`–`else if`–`else` hoặc `return` rõ ràng |
| Bỏ `{}` và tin vào độ thụt lề | Lệnh nằm ngoài nhánh mong muốn; `else` gắn nhầm `if` | Luôn đặt thân nhánh trong `{}` |
| Viết dấu `;` ngay sau `if (condition)` | Thân `if` trở thành lệnh rỗng, khối sau đó có thể chạy vô điều kiện | Viết `if (condition) { ... }` và kiểm tra bằng trình định dạng/linter |
| Gọi phương thức trước khi kiểm tra `null` | `NullPointerException` | Kiểm tra `null` trước bằng `&&` hoặc `||` |
| Dùng `==` để so sánh nội dung chuỗi | So sánh tham chiếu thay vì giá trị | Dùng `.equals()` hoặc `Objects.equals()` |
| Dùng `Boolean` có thể là `null` trực tiếp trong `if` | Unboxing có thể gây `NullPointerException` | Quy định cách xử lý `null`; cân nhắc `Boolean.TRUE.equals(value)` |
| Kết hợp `&`/`|` khi cần short-circuit | Vế phải vẫn chạy và có thể gây tác dụng phụ/lỗi | Dùng `&&`/`||` khi phù hợp |
| Vừa kiểm tra vừa thay đổi trạng thái trong biểu thức dài | Khó dự đoán thứ tự và khó kiểm thử | Tách việc cập nhật trạng thái khỏi điều kiện, đặt tên cho biểu thức |

Java cũng cho phép gán vào một biến `boolean` ngay trong điều kiện, chẳng hạn `if (ready = check())`, nhưng cách viết này dễ bị nhầm với phép so sánh. Trong mã nghiệp vụ thông thường, nên tách phép gán khỏi biểu thức `if` để tăng khả năng đọc và rà soát.

## 9. Kiểm thử nhánh và giá trị biên

Kiểm thử điều kiện không chỉ dừng ở một trường hợp đúng và một trường hợp sai. Với `else if`, cần kiểm tra **thứ tự ưu tiên**; với `&&` và `||`, cần kiểm tra các tổ hợp giá trị; với dữ liệu đầu vào, cần kiểm tra `null`, chuỗi trắng và các ngưỡng biên.

Ví dụ các trường hợp nên kiểm tra cho phương thức `decide` ở trên:

| Đầu vào | Kết quả mong đợi | Nhánh cần xác nhận |
|---|---|---|
| `order == null` | `LỖI: Thiếu đơn hàng` | Guard đầu tiên |
| `customerId == null` hoặc chỉ chứa khoảng trắng | `LỖI: Mã khách hàng không hợp lệ` | Kiểm tra chuỗi, short-circuit |
| `quantity == 0` hoặc âm | `LỖI: Số lượng không hợp lệ` | Ngưỡng thấp nhất |
| `paid == false`, `priority == true` | `Chờ thanh toán` | Thứ tự nhánh ưu tiên |
| `paid == true`, `priority == true`, `quantity == 2` | `Chuyển xử lý ưu tiên` | Vế trái của `||` |
| `paid == true`, `priority == false`, `quantity == 10` | `Chuyển xử lý ưu tiên` | Giá trị đúng tại ngưỡng 10 |
| `paid == true`, `priority == false`, `quantity == 9` | `Xử lý tiêu chuẩn` | Giá trị ngay dưới ngưỡng 10 |

Một lỗi thiết kế thường gặp là thêm nhánh mà không bổ sung trường hợp kiểm thử tương ứng. Khi quy tắc nghiệp vụ thay đổi, cập nhật ví dụ đầu vào và kết quả mong đợi để thể hiện rõ nhánh nào được chọn. Với codebase thực tế, những trường hợp này có thể được tự động hóa bằng JUnit.

## 10. Checklist khi viết `if` trong Java 27

1. Điều kiện có kiểu `boolean` hoặc `Boolean` và xử lý đúng mọi trường hợp `null` có thể xảy ra không?
2. Các nhánh có được phép chạy đồng thời, hay bắt buộc loại trừ nhau?
3. Thứ tự `else if` có đúng theo mức ưu tiên và các ngưỡng nghiệp vụ không?
4. Dấu ngoặc `{}` và tên điều kiện có khiến người đọc hiểu ngay luồng chạy không?
5. Có thể dùng guard clause để giảm lồng nhau mà vẫn bảo đảm tài nguyên được xử lý đúng không?
6. Các phép kiểm tra nhiều vế có dùng `&&`/`||` và thứ tự đánh giá an toàn không?
7. Các trường hợp biên, dữ liệu lỗi và nhánh mặc định đã được kiểm thử chưa?

Trong Java 27, các công cụ như pattern matching `instanceof`, record và switch expression có thể hỗ trợ viết luồng điều khiển rõ ràng hơn, nhưng không làm thay đổi nguyên tắc cốt lõi: **mỗi nhánh phải có ý nghĩa, điều kiện dễ hiểu, và các trường hợp đầu vào cần được bao phủ có chủ đích**.

## 11. Tài liệu tham khảo chính thức

- [Java Language Specification, Java SE 27 — §14.9: The `if` Statement](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-14.html#jls-14.9): kiểu điều kiện, quy tắc chọn nhánh và vấn đề *dangling else*.
- [Java Language Specification, Java SE 27 — §15.23 và §15.24](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-15.html): toán tử điều kiện `&&`, `||` và thứ tự đánh giá.
- [Java Language Specification, Java SE 27 — §6.3](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-6.html#jls-6.3): phạm vi biến pattern theo luồng điều khiển.
- [Java Language Specification, Java SE 27 — §14.30](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-14.html#jls-14.30): pattern và quy tắc khớp pattern.
