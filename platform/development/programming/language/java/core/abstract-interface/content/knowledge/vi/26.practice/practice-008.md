# Mô hình hóa kết quả bằng sealed interface và record

## Mục tiêu

Khi một thao tác có thể kết thúc theo nhiều cách, chẳng hạn thành công, thất bại hoặc đang chờ xử lý, ta thường cần biểu diễn rõ từng trường hợp trong kiểu dữ liệu. Kết hợp `sealed interface` với `record` cho phép định nghĩa một tập hợp các biến thể có giới hạn và mô tả dữ liệu của mỗi biến thể bằng cú pháp ngắn gọn.

`sealed interface` quy định những kiểu nào được phép triển khai trực tiếp. Mỗi `record` biểu diễn một dạng kết quả cụ thể, chứa các thành phần dữ liệu và cung cấp sẵn constructor, accessor, `equals()`, `hashCode()` và `toString()`. Cách kết hợp này hữu ích khi muốn người đọc và trình biên dịch hiểu được những dạng kết quả mà một API có thể trả về.

## 1. Vì sao nên mô hình hóa kết quả thành các biến thể?

Giả sử một API tìm kiếm tài nguyên. Kết quả có thể là:

- Thành công: có dữ liệu và mã trạng thái.
- Thất bại: có mã lỗi và thông điệp giải thích.
- Đang chờ: có thông tin về thao tác đang thực hiện.

Một thiết kế thường gặp là trả về `Object`, dùng `null` cho một số trường hợp, hoặc trả về một lớp chứa nhiều trường có thể rỗng. Các cách đó dễ tạo ra trạng thái không hợp lệ: một kết quả vừa có dữ liệu thành công vừa có thông tin lỗi, hoặc không có thông tin nào để giải thích kết quả.

Một mô hình kiểu đóng biểu diễn mỗi trường hợp thành một kiểu riêng. Khi đó, dữ liệu cần thiết cho thành công nằm trong record thành công, dữ liệu lỗi nằm trong record thất bại, còn kết quả đang chờ có cấu trúc riêng. Người gọi có thể xử lý từng trường hợp bằng cách kiểm tra kiểu cụ thể thay vì suy luận từ tổ hợp nhiều trường nullable.

## 2. Vai trò của sealed interface và record

Một sealed interface khai báo danh sách kiểu con trực tiếp bằng `permits`:

```java
sealed interface ApiResult permits Success, Failure, Pending {
}
```

Danh sách này chỉ gồm các kiểu con trực tiếp. Mỗi kiểu được liệt kê phải thực sự `implements ApiResult`. Với một phân cấp sealed, các kiểu con trực tiếp phải đóng hoặc mở rộng phân cấp theo quy tắc của Java: lớp con phải là `final`, `sealed` hoặc `non-sealed`; record vốn đã ngầm định `final`.

Các record có thể triển khai sealed interface:

```java
record Success(String value, int status) implements ApiResult {
}

record Failure(String code, String message) implements ApiResult {
}

record Pending(String operation) implements ApiResult {
}
```

Mỗi record định nghĩa dữ liệu của một trường hợp. Java tự tạo accessor theo tên thành phần, ví dụ `value()`, `status()` hoặc `message()`. Record cũng có phương thức so sánh giá trị và biểu diễn chuỗi dựa trên các thành phần của nó.

Record không thể kế thừa một lớp ứng dụng tùy chỉnh vì nó đã kế thừa trực tiếp `java.lang.Record`; cú pháp khai báo record không có mệnh đề `extends` cho lớp cha tùy chỉnh. Tuy nhiên, record có thể triển khai một hoặc nhiều interface, bao gồm sealed interface. Đây là lý do mô hình `sealed interface + record` phù hợp cho các biến thể dữ liệu.

## 3. Ví dụ hoàn chỉnh có thể chạy trên Java 17+

Ví dụ sau mô hình hóa ba kết quả của một thao tác: thành công, thất bại và đang chờ. Các constructor kiểm tra dữ liệu đầu vào để ngăn tạo ra kết quả không hợp lệ. Phương thức `describe` xử lý từng biến thể bằng pattern matching cho `instanceof`, tính năng đã được hỗ trợ chính thức từ Java 16.

Lưu nội dung vào tệp `ResultModelDemo.java`:

```java
import java.util.List;
import java.util.Objects;

public class ResultModelDemo {
    public static void main(String[] args) {
        List<ApiResult> results = List.of(
            new Success("OK", 200),
            new Failure("NOT_FOUND", "resource not found"),
            new Pending("import-catalog")
        );

        for (ApiResult result : results) {
            System.out.println(describe(result));
        }
    }

    private static String describe(ApiResult result) {
        if (result instanceof Success success) {
            return "Success: " + success.value()
                    + " (" + success.status() + ")";
        }
        if (result instanceof Failure failure) {
            return "Failure: " + failure.code()
                    + " - " + failure.message();
        }
        if (result instanceof Pending pending) {
            return "Pending: " + pending.operation();
        }

        throw new IllegalStateException(
            "Unsupported result type: " + result.getClass().getName()
        );
    }
}

sealed interface ApiResult permits Success, Failure, Pending {
}

record Success(String value, int status) implements ApiResult {
    Success {
        Objects.requireNonNull(value, "value must not be null");
        if (value.isBlank()) {
            throw new IllegalArgumentException("value must not be blank");
        }
        if (status < 200 || status > 299) {
            throw new IllegalArgumentException("success status must be 2xx");
        }
    }
}

record Failure(String code, String message) implements ApiResult {
    Failure {
        Objects.requireNonNull(code, "code must not be null");
        Objects.requireNonNull(message, "message must not be null");
        if (code.isBlank()) {
            throw new IllegalArgumentException("code must not be blank");
        }
        if (message.isBlank()) {
            throw new IllegalArgumentException("message must not be blank");
        }
    }
}

record Pending(String operation) implements ApiResult {
    Pending {
        Objects.requireNonNull(operation, "operation must not be null");
        if (operation.isBlank()) {
            throw new IllegalArgumentException("operation must not be blank");
        }
    }
}
```

Biên dịch và chạy:

```text
javac --release 17 -encoding UTF-8 ResultModelDemo.java
java ResultModelDemo
```

Kết quả chuẩn:

```text
Success: OK (200)
Failure: NOT_FOUND - resource not found
Pending: import-catalog
```

Ví dụ cho thấy mỗi biến thể mang đúng dữ liệu của nó. `Success` kiểm tra dữ liệu thành công và mã trạng thái; `Failure` yêu cầu mã lỗi và thông điệp; `Pending` yêu cầu tên thao tác. Các kiểm tra này giữ bất biến cơ bản ngay khi đối tượng được tạo. Vì đây là biến thể `Success` cho kết quả theo HTTP, mã trạng thái được giới hạn ở nhóm `2xx`; một phản hồi `4xx` hoặc `5xx` cần được biểu diễn bằng biến thể lỗi thay vì tạo `Success` có nghĩa mâu thuẫn.

## 4. Cách người gọi xử lý các biến thể

Khi nhận một `ApiResult`, người gọi nên xác định loại kết quả rồi xử lý theo dữ liệu của loại đó. Trong ví dụ, `instanceof Success success` vừa kiểm tra kiểu vừa tạo biến tham chiếu có kiểu cụ thể để truy cập các accessor. Các nhánh tiếp theo xử lý `Failure` và `Pending`.

Vì `ApiResult` là sealed và các kiểu con được biết trước, danh sách các biến thể là hữu hạn trong phạm vi phân cấp đó. Điều này giúp rà soát logic dễ hơn: nếu thêm một kiểu kết quả mới, người phát triển có thể tìm các điểm xử lý hiện tại và quyết định cách bổ sung nhánh tương ứng.

Tuy nhiên, đoạn `if/instanceof` không tự bảo đảm mọi nhánh đều đã được xử lý. Nhánh cuối ném `IllegalStateException` để biểu thị trường hợp không mong đợi. Khi bổ sung một biến thể mới, cần cập nhật các hàm xử lý và kiểm thử liên quan.

Java 21 trở lên hỗ trợ pattern matching cho `switch` như một tính năng chính thức, có thể kết hợp với sealed hierarchy để viết phép phân nhánh rõ ràng hơn. Trên Java 17, pattern matching cho `switch` vẫn là preview, nên ví dụ này dùng `instanceof` để biên dịch mà không cần bật preview.

## 5. Giữ mô hình hợp lệ và dễ mở rộng

### Tránh trạng thái mâu thuẫn

Không nên gom tất cả trường vào một record duy nhất như `Result(String value, String errorCode, String message, boolean pending)` nếu nhiều tổ hợp trường có thể xuất hiện nhưng không có ý nghĩa. Một record thành công có cả dữ liệu lỗi, hoặc một kết quả thất bại không có mã lỗi, làm tăng số trạng thái mà mọi người gọi phải kiểm tra.

Các biến thể riêng giúp giới hạn cấu trúc dữ liệu có thể tạo. Constructor compact của record cho phép kiểm tra đầu vào mà không cần viết lại phần gán các thành phần. Nếu dữ liệu đầu vào vi phạm bất biến, có thể ném `IllegalArgumentException` hoặc `NullPointerException` một cách nhất quán.

### Thêm biến thể mới có chủ đích

Nếu API cần thêm trạng thái như `Cancelled`, hãy bổ sung kiểu đó vào `permits` và triển khai sealed interface. Sau đó, cập nhật các hàm xử lý, tài liệu và kiểm thử. Thay đổi tập biến thể có thể ảnh hưởng đến mã khách hàng vốn giả định chỉ có các trường hợp cũ, vì vậy cần xem xét tương thích khi phát hành thư viện công khai.

Các kiểu được phép kế thừa hoặc triển khai phải tuân thủ điều kiện vị trí: trong named module, chúng phải thuộc cùng module; trong unnamed module, chúng phải ở cùng package. Đặt một kiểu con ở sai module hoặc package sẽ khiến phân cấp không hợp lệ.

### Hiểu giới hạn của record

Record phù hợp với dữ liệu có thành phần được xác định rõ và không cần kế thừa trạng thái từ lớp cha ứng dụng. Các thành phần record là final, nhưng tính bất biến chỉ ở mức nông: nếu một thành phần tham chiếu đến một đối tượng mutable, đối tượng đó vẫn có thể thay đổi. Trong ví dụ, các thành phần đều là `String`, vốn bất biến, nên vấn đề này không phát sinh.

Không cần tạo getter theo kiểu JavaBean như `getValue()`; accessor của record dùng trực tiếp tên thành phần, chẳng hạn `value()`. Nếu API yêu cầu quy ước hoặc hành vi khác, có thể khai báo thêm phương thức, nhưng cần giữ ý nghĩa rõ ràng và tránh trùng lặp không cần thiết.

## 6. Khi nào nên dùng mô hình này?

| Tình huống | Thiết kế phù hợp |
|---|---|
| Một thao tác có vài kết quả đã xác định rõ | Sealed interface cùng các record đại diện cho từng kết quả |
| Mỗi kết quả mang bộ dữ liệu khác nhau | Một record riêng cho mỗi biến thể |
| Cần giới hạn kiểu kết quả mà mã ứng dụng được phép tạo | Sealed interface với danh sách `permits` tường minh |
| Các kiểu cần chia sẻ trạng thái từ lớp cha tùy chỉnh | Xem xét sealed class với các lớp con thông thường |
| Các kết quả cần mở rộng bởi thư viện bên ngoài | Cân nhắc interface không sealed hoặc một nhánh `non-sealed`, hiểu rõ rằng phạm vi biến thể sẽ mở rộng |

Không nên chọn sealed chỉ vì cú pháp mới hơn. Sealed hữu ích khi việc giới hạn các biến thể là một phần của thiết kế. Nếu bên thứ ba cần tự định nghĩa kiểu triển khai mới, một interface mở có thể phù hợp hơn.

## Ghi nhớ

- `sealed interface` giới hạn những kiểu được phép triển khai trực tiếp; `permits` liệt kê các kiểu con trực tiếp.
- `record` mô tả dữ liệu của một biến thể, cung cấp accessor và các phương thức dựa trên giá trị; record ngầm định là `final`.
- Record không thể kế thừa lớp ứng dụng tùy chỉnh, nhưng có thể triển khai sealed interface.
- Tách thành các record riêng giúp tránh tổ hợp trường nullable và trạng thái mâu thuẫn.
- Sau khi thêm biến thể, cập nhật các điểm xử lý và kiểm thử; sealed giúp xác định phạm vi kiểu nhưng không tự bảo đảm logic nghiệp vụ đã đầy đủ.
- Ví dụ dùng Java 17 và `instanceof` pattern matching, không cần bật preview.