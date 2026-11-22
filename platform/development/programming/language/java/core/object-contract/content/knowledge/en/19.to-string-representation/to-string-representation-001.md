# Vai trò của `toString()` trong quan sát và chẩn đoán đối tượng Java

## 1. `toString()` giúp quan sát điều gì?

Khi chương trình chạy, người phát triển cần biết **đối tượng đang đại diện cho cái gì, trạng thái đáng chú ý ra sao, và dữ liệu nào giúp liên hệ một hiện tượng với yêu cầu hoặc bản ghi cụ thể**. Phương thức `toString()` là một điểm mở rộng chuẩn của Java để cung cấp **biểu diễn văn bản dễ đọc** cho một đối tượng.

`toString()` đặc biệt hữu ích trong:

- **Gỡ lỗi:** quan sát đối tượng tại breakpoint, cửa sổ biến của IDE, hoặc các dòng in tạm trong quá trình điều tra.
- **Ghi log:** đưa một số trường có ý nghĩa vào log để liên kết lỗi với mã đơn hàng, trạng thái xử lý, số lần thử lại hoặc thời điểm nghiệp vụ.
- **Chẩn đoán sự cố:** đối chiếu trạng thái trước và sau thao tác, phát hiện giá trị bị sai, dữ liệu trống hoặc đối tượng đi nhầm luồng xử lý.
- **Quan sát collection:** khi in một `List`, `Set` hoặc `Map`, biểu diễn của các phần tử thường dựa vào `toString()`, nên một triển khai có ích giúp đọc kết quả dễ hơn.
- **Thông báo nội bộ và kiểm tra thủ công:** nhanh chóng hiểu đối tượng mà không phải tự in từng getter.

Ví dụ, với một yêu cầu xử lý thanh toán, biểu diễn:

```text
Payment{id='PAY-42', status='PENDING', attempts=2}
```

có giá trị chẩn đoán hơn dạng mặc định như:

```text
com.example.Payment@4e25154f
```

Chuỗi hex ở ví dụ thứ hai chỉ mang tính minh họa, không phải địa chỉ RAM hay kết quả cố định của chương trình. Dữ liệu trạng thái hữu ích cần được chọn **theo mục đích quan sát**, tránh lộ mã xác thực, thông tin cá nhân hoặc các trường rất dài.

**Phạm vi quan trọng:** `toString()` là một biểu diễn thuận tiện cho con người, **không phải** giao thức serialization, JSON contract, khóa định danh hay bằng chứng hai object bằng nhau. Những nhiệm vụ đó thuộc API, mô hình dữ liệu, `equals()`/`hashCode()` hoặc serializer chuyên dụng.

## 2. `Object.toString()` mặc định hoạt động thế nào?

Mọi lớp Java thông thường đều kế thừa `toString()` từ `java.lang.Object` trừ khi tự ghi đè. Hình thức kết quả mặc định của `Object.toString()` tương đương:

```java
getClass().getName() + "@" + Integer.toHexString(hashCode())
```

Trong biểu thức này:

1. `getClass().getName()` trả tên lớp runtime (kể cả package, và với lớp lồng nhau có thể xuất hiện ký hiệu `$`).
2. `hashCode()` được gọi trên đối tượng hiện tại; **nếu lớp đã ghi đè `hashCode()`, giá trị đó cũng được dùng**.
3. `Integer.toHexString(...)` biến số hash thành chuỗi hex.

Điều này lý giải vì sao nhìn thấy `TênLớp@...` thường chỉ cho biết loại đối tượng và một mã hash, không hiển thị trường nghiệp vụ.

Các hiểu nhầm cần tránh:

- **Phần sau `@` không mặc nhiên là địa chỉ bộ nhớ.** Đặc tả `Object.toString()` nói tới hash dạng hex, không hứa vị trí RAM; JVM có thể di chuyển đối tượng trong quá trình quản lý bộ nhớ.
- **Hash không bảo đảm duy nhất.** Hai object khác nhau có thể có cùng hash do va chạm, và mã hash không thay thế `==` khi cần kiểm tra cùng tham chiếu.
- **Chuỗi mặc định không ổn định xuyên lần chạy.** Không lưu hoặc phân tích nó như ID cố định trong database, sự kiện hay API.
- **Đừng suy diễn ý nghĩa từ hex.** Ngay cả khi chuỗi trông giống một giá trị định danh, nó không chứng minh trạng thái nghiệp vụ, phiên bản dữ liệu hay tính toàn vẹn của đối tượng.

Nếu cần gắn sự kiện log với một thực thể, hãy dùng **mã nghiệp vụ rõ ràng** như `orderId` hoặc `paymentId`, kèm trace/request ID theo cơ chế logging phù hợp.

## 3. Ghi đè `toString()`: chọn thông tin phù hợp cho chẩn đoán

Chữ ký phương thức chuẩn:

```java
@Override
public String toString() {
    return "Type{field=value}";
}
```

Đây là mảnh code minh họa bên trong một lớp. Khi override đúng, phương thức phải `public`, không nhận tham số và trả một `String`. Annotation `@Override` giúp trình biên dịch phát hiện lỗi chữ ký.

Ví dụ với một thanh toán:

```java
public final class Payment {
    private final String id;
    private final String status;
    private final int attempts;
    private final String accessToken;

    public Payment(String id, String status, int attempts, String accessToken) {
        this.id = id;
        this.status = status;
        this.attempts = attempts;
        this.accessToken = accessToken;
    }

    @Override
    public String toString() {
        return "Payment{id='" + id
            + "', status='" + status
            + "', attempts=" + attempts + "}";
    }
}
```

Đây là lớp có thể biên dịch nếu lưu vào `Payment.java`, nhưng chưa có `main` để tự chạy. Nó minh họa việc chọn trường: `id` hỗ trợ liên hệ với bản ghi; `status` và `attempts` cho biết trạng thái; `accessToken` **không** xuất hiện trong kết quả vì chứa thông tin nhạy cảm.

Không có nghĩa cứ trường `private` là phải đưa vào `toString()`. Chọn một tập trường **ngắn, có ý nghĩa, đủ để giải thích sự kiện**. Ví dụ không nên in toàn bộ payload HTTP, binary data, token đăng nhập, thẻ thanh toán, email cá nhân hoặc danh sách hàng triệu phần tử chỉ vì chúng có trong đối tượng.

### 3.1. Dùng `StringBuilder` khi có nhiều trường tùy chọn

Với biểu diễn phức tạp, `StringBuilder` giúp ghép các phần dễ đọc và có điều kiện. Với vài trường, nối chuỗi bằng `+` như ví dụ trên là hoàn toàn hợp lý, vì trình biên dịch và runtime Java đã có cơ chế tối ưu phù hợp cho các biểu thức nối chuỗi thông thường.

`String.format(...)` cũng có thể tạo kết quả rõ ràng, nhưng nếu `toString()` được gọi với tần suất cao, định dạng phức tạp có thể làm tăng chi phí. Hãy đo lường khi tối ưu, không thay cách viết rõ ràng bằng kỹ thuật thủ công chỉ vì giả định hiệu năng.

### 3.2. Kết quả cần dễ đọc và đủ nhất quán

Một số thói quen hữu ích:

- Mở đầu bằng tên loại đối tượng dễ nhận biết, ví dụ `Payment{...}` hoặc `JobState{...}`.
- Ghi tên field trước giá trị: `attempts=2` dễ hiểu hơn một danh sách chỉ gồm số.
- Giữ thứ tự trường nhất quán giữa các lần gọi.
- Với field có thể `null`, cho ra giá trị rõ ràng nếu field đó hữu ích để chẩn đoán.
- Chỉ hiển thị một phần hoặc số lượng phần tử nếu collection rất lớn.
- Nếu có mã định danh ổn định, ưu tiên in nó hơn thông tin tham chiếu/identity hash.
- Không biến văn bản `toString()` thành một định dạng máy móc mà bên khác phải parse để vận hành hệ thống.

Nếu muốn log có cấu trúc thật sự, dùng API ghi log có trường riêng (ví dụ payment ID, event name, status, trace ID), thay vì trích xuất dữ liệu bằng regex từ `toString()`.

## 4. Khi nào Java tự gọi `toString()`?

Có nhiều con đường khiến biểu diễn của đối tượng xuất hiện mà bạn không gọi `obj.toString()` bằng tay.

### 4.1. `System.out.println(obj)`

Khi in một tham chiếu kiểu `Object`, `PrintStream.println(Object)` chuyển giá trị thành chuỗi theo cơ chế `String.valueOf(Object)`. Đối với đối tượng khác `null`, thao tác này gọi `toString()`; với tham chiếu `null`, văn bản nhận được là `"null"`.

```java
Object value = new Object();
System.out.println(value); // Dạng tên lớp @ hex hash (giá trị cụ thể tùy lần chạy).
System.out.println((Object) null); // null
```

Đây là mảnh code minh họa; dòng đầu có kết quả hash không xác định trước. Không hardcode stdout của một object chưa ghi đè `toString()` vào bài kiểm thử.

### 4.2. Ghép chuỗi

`"item=" + obj` chuyển đối tượng thành biểu diễn chuỗi khi đánh giá biểu thức nối chuỗi. Vì thế:

```java
String message = "payment=" + payment;
```

cũng sử dụng `toString()` của `payment` khi biến không `null`. Cần nhớ thời điểm đánh giá: phép nối chuỗi được thực hiện khi dựng `message`, kể cả khi log về sau bị bỏ qua. Trong luồng logging hiệu năng cao, nên dùng cơ chế message/parameterized logging phù hợp thư viện để tránh dựng thông điệp không cần thiết; khả năng trì hoãn chuyển chuỗi phụ thuộc API/logging framework.

### 4.3. `String.valueOf(...)` và `Objects.toString(...)`

`String.valueOf((Object) obj)` an toàn với `null` và tạo `"null"`; `Objects.toString(obj, "n/a")` cho phép cung cấp giá trị mặc định khi `obj == null`. Không nên viết `obj.toString()` khi `obj` có thể `null` mà không có kiểm tra, vì sẽ ném `NullPointerException`.

### 4.4. Collection và mảng

Các implementation quen thuộc của `List`, `Set` và `Map` có `toString()` thể hiện các phần tử/entry; đối tượng phần tử sẽ được chuyển sang chuỗi khi biểu diễn collection. Nếu phần tử có `toString()` rối, vô ích hoặc làm lộ dữ liệu, in collection cũng có vấn đề tương tự.

**Mảng là một trường hợp đặc biệt:** gọi `toString()` trực tiếp trên `int[]` thường chỉ cho dạng `[I@...`, vì mảng không có biểu diễn nội dung riêng do `Object.toString()` cung cấp. Dùng:

- `Arrays.toString(array)` để in phần tử của mảng một chiều.
- `Arrays.deepToString(array)` khi cần biểu diễn lồng nhau của mảng object, ví dụ `int[][]`.

Không được xem các phương thức in mảng là giải pháp serializing bền vững; chúng cung cấp biểu diễn tiện cho quan sát.

## 5. Ví dụ Java 17 có kết quả xác định

Ví dụ đầy đủ sau chỉ in các giá trị có thể dự đoán, đồng thời chỉ ra các giới hạn của `toString()`: hai đối tượng có cùng text vẫn không nhất thiết cùng tham chiếu hoặc bằng nhau theo `equals()`; biểu diễn cũng có thể bỏ qua trường bí mật.

Lưu tệp **`ToStringDiagnosticsDemo.java`**:

```java
import java.util.Arrays;
import java.util.List;
import java.util.Objects;

public class ToStringDiagnosticsDemo {
    static final class Payment {
        private final String paymentId;
        private final String status;
        private final int attempts;
        private final String accessToken;

        Payment(String paymentId, String status,
                int attempts, String accessToken) {
            this.paymentId = Objects.requireNonNull(paymentId);
            this.status = Objects.requireNonNull(status);
            this.attempts = attempts;
            this.accessToken = Objects.requireNonNull(accessToken);
        }

        @Override
        public String toString() {
            return "Payment{id='" + paymentId
                + "', status='" + status
                + "', attempts=" + attempts + "}";
        }
    }

    record PaymentSummary(String paymentId, String status, int attempts) {}

    static final class NoOverride {}

    public static void main(String[] args) {
        Payment first = new Payment("PAY-42", "PENDING", 2, "secret-123");
        Payment second = new Payment("PAY-42", "PENDING", 2, "other-secret");

        System.out.println("Object: " + first);
        System.out.println("Same text: "
            + first.toString().equals(second.toString()));
        System.out.println("Same reference: " + (first == second));
        System.out.println("Same equals: " + first.equals(second));
        System.out.println("Secret exposed: "
            + first.toString().contains("secret-123"));

        PaymentSummary summary =
            new PaymentSummary("PAY-42", "PENDING", 2);
        System.out.println("Record: " + summary);
        System.out.println("List: " + List.of(first, second));
        System.out.println("Array: " + Arrays.toString(new int[] {2, 4}));
        System.out.println("Matrix: "
            + Arrays.deepToString(new int[][] {{1, 2}, {3, 4}}));
        System.out.println("Null: " + String.valueOf((Object) null));

        Object plain = new NoOverride();
        String defaultText = plain.toString();
        String prefix = NoOverride.class.getName() + "@";
        System.out.println("Default form matches class@: "
            + defaultText.startsWith(prefix));
    }
}
```

Biên dịch và chạy từ thư mục chứa tệp bằng **JDK 17 trở lên**:

```bash
javac ToStringDiagnosticsDemo.java
java ToStringDiagnosticsDemo
```

Kết quả chuẩn:

```text
Object: Payment{id='PAY-42', status='PENDING', attempts=2}
Same text: true
Same reference: false
Same equals: false
Secret exposed: false
Record: PaymentSummary[paymentId=PAY-42, status=PENDING, attempts=2]
List: [Payment{id='PAY-42', status='PENDING', attempts=2}, Payment{id='PAY-42', status='PENDING', attempts=2}]
Array: [2, 4]
Matrix: [[1, 2], [3, 4]]
Null: null
Default form matches class@: true
```

**Giải thích:**

1. `Payment.toString()` cho văn bản tập trung vào mã thanh toán, trạng thái và số lần thử, nên dòng `Object` phù hợp để đọc log.
2. `first` và `second` có cùng chuỗi `toString()` vì các trường được chọn giống nhau; nhưng `first == second` là `false` (hai object), và `Payment` không override `equals()` nên `first.equals(second)` cũng là `false`. **Đừng suy ra equality từ biểu diễn chuỗi.**
3. Mỗi `Payment` có token nội bộ, nhưng `toString()` không đưa token vào chuỗi; kiểm tra chuỗi không chứa `"secret-123"` trả `false` cho “Secret exposed”.
4. `record PaymentSummary` được Java sinh sẵn `toString()` theo tên record và toàn bộ component của record. Điều này tiện cho dữ liệu tóm tắt không nhạy cảm; nếu record chứa token hoặc dữ liệu cá nhân, hành vi mặc định có thể làm lộ chúng khi log.
5. `List` hiển thị mỗi phần tử thông qua biểu diễn tương ứng. Việc in toàn bộ collection có thể làm log dài bất ngờ khi danh sách lớn.
6. `Arrays.toString` và `Arrays.deepToString` in nội dung của mảng một cấp hoặc mảng lồng nhau; dùng trực tiếp `array.toString()` không đáp ứng mục tiêu đó.
7. Dòng cuối chỉ kiểm tra tiền tố định dạng mặc định của `Object.toString()`, không khẳng định một giá trị hex cụ thể.

## 6. `toString()` liên quan gì tới `equals()` và `hashCode()`?

Ba phương thức có vai trò khác nhau:

| Phương thức | Câu hỏi trả lời | Điều cần bảo đảm |
| --- | --- | --- |
| `equals(Object)` | Hai đối tượng có được coi là bằng nhau theo quan hệ equality của class không? | Phản xạ, đối xứng, bắc cầu, nhất quán, không bằng `null` |
| `hashCode()` | Mã băm phục vụ các cấu trúc băm là bao nhiêu? | Đối tượng bằng nhau theo `equals()` phải có cùng hash |
| `toString()` | Biểu diễn văn bản hữu ích cho người quan sát là gì? | Không có hợp đồng bắt buộc là duy nhất, có thể parse hoặc phản ánh tất cả field |

Những hệ quả thường bị hiểu sai:

- **Hai object có `toString()` bằng nhau không nhất thiết `equals()` bằng nhau.** Bạn có thể chủ động bỏ các trường khỏi biểu diễn chẩn đoán.
- **Hai object `equals()` bằng nhau cũng không được ngôn ngữ buộc phải có `toString()` giống nhau.** Chẳng hạn hai entity cùng ID nhưng status cập nhật ở thời điểm khác nhau vẫn có thể in hai status khác.
- **`toString()` không nên được dùng làm `hashCode()` hay khóa bản ghi.** Tên field, thứ tự field và chính sách che giấu dữ liệu có thể thay đổi theo phiên bản ứng dụng.
- **Không sửa `equals/hashCode` chỉ để khiến log trông giống nhau.** Quan hệ bằng nhau là một quyết định về miền nghiệp vụ hoặc giá trị, không phải một yêu cầu định dạng.
- **Không dựa vào chuỗi `Class@hash` để suy luận về memory identity.** Hash có thể va chạm, lớp có thể override hash, và địa chỉ bộ nhớ không được cung cấp theo định dạng đó.

Nếu cần dữ liệu để so sánh tự động trong test, kiểm tra các field hoặc `equals()` theo định nghĩa của lớp. Chỉ kiểm tra `toString()` khi định dạng biểu diễn chính là hành vi bạn muốn cam kết; nếu không, kiểm thử chính xác từng dấu câu của `toString()` thường làm test dễ vỡ khi thay đổi cách hiển thị.

## 7. Phân biệt `toString()` với logging có cấu trúc và serialization

### 7.1. Log nên chứa thông tin ngữ cảnh

Log có ích cần trả lời được “sự kiện gì, khi nào, ở đâu, liên quan yêu cầu/bản ghi nào, trạng thái nào”. `toString()` của một object chỉ là một phần dữ liệu để bổ sung ngữ cảnh.

Ví dụ một dòng log hữu ích về mặt ý nghĩa:

```text
event=payment_retry requestId=REQ-18 paymentId=PAY-42 status=PENDING attempt=2
```

Đây là văn bản minh họa, không phải output do một API log cụ thể sinh ra. Ở hệ thống lớn, việc log các trường có tên riêng giúp tìm kiếm/lọc tốt hơn so với chuỗi `Payment{...}` tự do.

Với thư viện logging hỗ trợ tham số, ưu tiên gọi theo mẫu của thư viện khi phù hợp, để tránh tạo thông điệp tốn chi phí khi mức log bị tắt. Tuy nhiên, chi tiết định dạng và thời điểm gọi `toString()` phụ thuộc thư viện; **không suy đoán rằng mọi API log đều trì hoãn việc tính chuỗi**.

### 7.2. Serialization không phải `toString()`

`toString()` có thể thay đổi hình thức chỉ để giúp người đọc log. Không dùng nó làm JSON, CSV, payload mạng, khóa cache hay dữ liệu lưu database. Một serializer chuyên dụng phải có quy tắc rõ về tên trường, kiểu, escaping, phiên bản schema và kiểm soát các trường được công bố.

Một chuỗi `toString()` như `Order{id='O1', status='NEW'}` không phải JSON hợp lệ; cố parse ngược bằng regex rất dễ hỏng khi status chứa dấu nháy, xuống dòng hoặc khi thứ tự field thay đổi.

### 7.3. Exception và stack trace

`Throwable.toString()` thông thường cho tên lớp exception và thông điệp lỗi; nó **không đồng nghĩa với toàn bộ stack trace**. Muốn quan sát stack trace, sử dụng cơ chế của logger để ghi exception/stack trace hoặc gọi `printStackTrace` trong bối cảnh thích hợp. Không cố nhồi toàn bộ stack trace hay object graph vào `toString()` của domain object.

## 8. An toàn dữ liệu: thông tin nào không nên xuất hiện?

`toString()` rất dễ được gọi gián tiếp khi in object hoặc collection; vì vậy cần xem đây là một **bề mặt có thể làm lộ dữ liệu**.

Các ví dụ nên hạn chế/che giấu khi biểu diễn đối tượng gồm:

- Password, access token, API key, secret, cookie xác thực, mã OTP.
- Số thẻ hoặc thông tin tài chính nhạy cảm.
- Thông tin cá nhân không cần thiết cho việc chẩn đoán (địa chỉ, email, số điện thoại, hồ sơ y tế).
- Payload/response body có thể chứa dữ liệu khách hàng hoặc bí mật.
- Dữ liệu binary, khóa mật mã, session state, đối tượng chứa đường dẫn/tài nguyên riêng tư.

Chỉ che mật khẩu bằng `"****"` là chưa đủ nếu các trường khác vẫn có thể lộ dữ liệu. Thiết kế một **allowlist** các trường an toàn để in thường tốt hơn liệt kê hết mọi field rồi chỉ chặn vài cái tên nhạy cảm.

Với record, IDE code generator hoặc Lombok, phải xem lại code `toString()` được sinh tự động: nó có thể đưa tất cả field/component vào kết quả, kể cả field mới thêm trong tương lai. Phần dành cho log nội bộ cũng có thể bị chuyển sang hệ thống tập trung hoặc xuất qua kênh hỗ trợ, vì vậy không nên phụ thuộc vào giả định “chỉ developer thấy”.

Nếu dữ liệu có xuống dòng hoặc ký tự điều khiển do người dùng nhập, ghi log dạng văn bản tự do có thể bị nhiễu bởi log injection. Sử dụng logging có cấu trúc, escaping và giới hạn độ dài theo chính sách hệ thống; đừng kỳ vọng `toString()` tự xử lý an toàn các giá trị tùy ý.

## 9. Những rủi ro về hiệu năng và side effect

`toString()` thường xuất hiện trên đường chẩn đoán, nhưng đôi khi được gọi rất nhiều trong quá trình chạy thực tế. Một phương thức hữu ích nên:

1. **Nhanh và có chi phí dự đoán được.** Không tải toàn bộ dữ liệu từ database, đọc file, gọi HTTP, tính toán phức tạp hoặc tuần tự hóa cả đồ thị đối tượng chỉ để tạo một dòng.
2. **Không gây side effect.** Tránh cập nhật trạng thái, tăng bộ đếm, xóa phần tử hoặc ghi log khác trong `toString()`; một hành động “chỉ quan sát” không nên làm thay đổi chương trình.
3. **Không gây đệ quy vô hạn.** Hai object tham chiếu qua lại có thể làm `toString()` của mỗi bên gọi ngược lại bên kia mãi.
4. **Không làm log bùng nổ.** Giới hạn độ dài text, số phần tử hoặc độ sâu của cấu trúc lồng nhau.
5. **Không phụ thuộc vào các tác vụ có thể thất bại.** Getter có tải dữ liệu lười (*lazy loading*) hoặc proxy ORM có thể thực hiện truy vấn ngoài ý muốn, ném exception hoặc tiếp xúc với trạng thái transaction.
6. **Dễ dùng khi xảy ra lỗi.** Tránh các chuỗi truy cập null không có kiểm tra, lỗi định dạng hoặc giả định object liên quan luôn được khởi tạo.

Ví dụ đồ thị hai chiều:

```java
// Minh họa nguy cơ, không phải lớp Java độc lập.
class Parent {
    Child child;
    @Override public String toString() { return "Parent{child=" + child + "}"; }
}
class Child {
    Parent parent;
    @Override public String toString() { return "Child{parent=" + parent + "}"; }
}
```

Nếu `parent.child.parent == parent`, gọi `parent.toString()` có thể lặp `Parent.toString() → Child.toString() → Parent.toString() → ...` và cuối cùng gây `StackOverflowError`. Cách xử lý thường là in mã tham chiếu ổn định của đối tượng liên quan, ví dụ `childId` thay vì toàn bộ `child.toString()`, hoặc giới hạn độ sâu có chủ đích.

Với collection, `Arrays.deepToString` giúp biểu diễn mảng lồng nhau, nhưng **không vì thế mà tự động phù hợp để in dữ liệu cực lớn hoặc nhạy cảm**. Quan sát cần có mục đích và phạm vi.

## 10. Dạng `toString()` tốt cho các loại object khác nhau

| Loại đối tượng | Nên cân nhắc thể hiện | Nên tránh |
| --- | --- | --- |
| Entity nghiệp vụ | ID ổn định, trạng thái cơ bản, thông tin chẩn đoán được phép công bố | Toàn bộ quan hệ ORM, token, danh sách bản ghi con |
| Value object nhỏ | Các thành phần làm nên giá trị, khi an toàn | Giá trị nhạy cảm không phục vụ chẩn đoán |
| DTO/record | Các trường an toàn, đủ để hiểu sự kiện | In tự động mọi field khi DTO chứa dữ liệu cá nhân |
| Cấu trúc dữ liệu | Kích thước, loại phần tử, vài phần tử mẫu | In hàng triệu phần tử hay binary payload |
| Tác vụ bất đồng bộ | ID tác vụ, trạng thái, số lần thử, thời gian đã biết | Gọi mạng hoặc thay đổi trạng thái bên trong `toString()` |
| Wrapper/proxy | Tên loại, ID và trạng thái proxy cần thiết | Tự động kích hoạt lazy loading sâu |
| Exception | Loại, message đã được kiểm soát, mã lỗi | Thông tin bí mật; coi `toString()` thay stack trace |

Không phải đối tượng nào cũng cần override `toString()`. Với lớp nội bộ không cần chẩn đoán bằng text, mặc định có thể đủ. Với dữ liệu chẩn đoán xuất hiện thường xuyên, viết một biểu diễn ngắn và ổn định về ý nghĩa thường giúp tiết kiệm nhiều thời gian điều tra.

## 11. Một số lỗi dễ gặp khi dùng `toString()`

### Lỗi 1: coi chuỗi là định danh

`object.toString()` không phải khóa đáng tin cậy cho database, HTTP endpoint, metrics label hoặc tracing. Nếu nhiều đối tượng có cùng text, việc phân biệt sai sẽ gây lỗi; nếu text đổi sau khi sửa status, khóa được sinh ra cũng đổi. Hãy dùng business ID, trace ID hoặc ID tác vụ chuyên dụng.

### Lỗi 2: dùng `toString()` để kiểm tra equality

Hai object có text giống nhau vẫn có thể là hai instance khác nhau. Khi cần kiểm tra cùng tham chiếu, dùng `==`; khi cần equality theo ngữ nghĩa, dùng `equals()` đã được thiết kế đúng.

### Lỗi 3: in trực tiếp array và tưởng đã in phần tử

`array.toString()` trên một mảng không cung cấp nội dung như mong đợi. Sử dụng `Arrays.toString` cho mảng một chiều và `Arrays.deepToString` cho mảng lồng nhau phù hợp.

### Lỗi 4: nhồi toàn bộ object graph

Ví dụ `Order.toString()` gọi `Customer.toString()`, rồi `Customer.toString()` lại gọi tất cả `Order`; chuỗi rất dài hoặc đệ quy vô hạn. Chỉ in mã định danh của quan hệ và vài trường trạng thái cần thiết.

### Lỗi 5: tin rằng mọi giá trị đều an toàn để log

Giá trị `record.toString()` sinh tự động có thể chứa field mới được thêm sau này. Với object dùng để ghi log, kiểm tra policy dữ liệu và chỉ cho xuất một tập trường đã được phép.

### Lỗi 6: để `toString()` ném lỗi phụ

Nếu đang chẩn đoán một exception khác mà `toString()` lại gọi phương thức có thể ném exception hoặc truy cập object chưa khởi tạo, thông tin chẩn đoán bị mất hoặc gây nhiễu. Nên ưu tiên dữ liệu đã có, kiểm tra giá trị có thể `null` và không gọi tài nguyên ngoài.

### Lỗi 7: test cứng định dạng khi không cần

Kiểm thử `toString()` là hợp lý nếu lớp cam kết định dạng text cụ thể cho công cụ vận hành. Nếu text chỉ phục vụ debug, test bám sát khoảng trắng/dấu phẩy/cách đặt ngoặc có thể làm code khó đổi. Hãy test những trường quan trọng và nguyên tắc không lộ bí mật; tránh dựa vào identity hash biến động.

## 12. Câu hỏi tự kiểm tra

**Câu 1.** Hai instance `Payment` khác nhau có cùng `toString()`. Có thể kết luận `a == b` hoặc `a.equals(b)` là `true` không?

**Đáp án:** Không. `toString()` chỉ biểu diễn các trường được chọn; nó không quyết định quan hệ tham chiếu hay equality.

**Câu 2.** Tên lớp theo sau dấu `@` trong `Object.toString()` có phải địa chỉ RAM không?

**Đáp án:** Không. `Object.toString()` dùng tên lớp và hash của đối tượng dưới dạng hex; hash không phải địa chỉ, cũng không bảo đảm duy nhất.

**Câu 3.** Với `int[] a = {1, 2}`, cách in nội dung dễ đọc là gì?

**Đáp án:** `Arrays.toString(a)` cho `[1, 2]`. Với `int[][]`, dùng `Arrays.deepToString(...)` để in các hàng lồng nhau.

**Câu 4.** `record Credentials(String user, String token) {}` có phù hợp để log trực tiếp không?

**Đáp án:** Thông thường không, vì `toString()` được sinh tự động sẽ thể hiện cả component `token`. Nên thiết kế biểu diễn an toàn hoặc chỉ log các field đã được phép công bố.

**Câu 5.** Một phương thức `toString()` gọi database để lấy danh sách chi tiết trước khi in. Rủi ro là gì?

**Đáp án:** Thêm độ trễ, truy vấn ngoài ý muốn, lỗi khi transaction không còn, tải lượng lớn và khả năng ném exception trong lúc đang chẩn đoán. Hãy giới hạn vào trạng thái sẵn có.

**Câu 6.** Khi phân tích lỗi, có thể dùng `exception.toString()` thay thế stack trace hoàn chỉnh không?

**Đáp án:** Không. Nó thường cho loại exception và message, trong khi stack trace chứa ngữ cảnh lời gọi; cần sử dụng cơ chế ghi exception/stack trace riêng.

**Câu 7.** Một lớp đã override `hashCode()` theo business ID nhưng giữ `Object.toString()`. Phần hex sau `@` phản ánh điều gì?

**Đáp án:** Nó là biểu diễn hex của kết quả `hashCode()` hiện tại, nên có thể phản ánh hash theo business ID đã override. Không nên coi đó là identity hash hay ID gốc.

---

**Ghi nhớ:** `toString()` giúp đối tượng **dễ quan sát và chẩn đoán**, đặc biệt ở debugger, log và khi in collection. Hãy chọn những trường an toàn, ngắn gọn, có ý nghĩa; tránh side effect, dữ liệu nhạy cảm, đệ quy và I/O. Giữ riêng vai trò của `toString()` với `equals()`, `hashCode()`, định danh nghiệp vụ, serialization và logging có cấu trúc.