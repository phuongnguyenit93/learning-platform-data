# Nhánh `default` và chính sách đối với giá trị ngoài dự kiến trong `switch` expression (Java 14+)

> Mục tiêu: hiểu khi nào phải có `default`, chọn hành vi phù hợp nếu xuất hiện giá trị chưa được dự kiến, và tránh che giấu lỗi nghiệp vụ. `switch` expression được chuẩn hóa từ Java 14 và vẫn là cú pháp được dùng trong các phiên bản Java hiện đại.

## 1. `default` có ý nghĩa gì?

`switch` **expression** tạo ra một giá trị (hoặc kết thúc bằng ngoại lệ). Vì vậy các nhánh phải **exhaustive**: trình biên dịch phải chứng minh mọi giá trị có thể có của biểu thức lựa chọn đều được xử lý.

- Với `int`, `String` và những tập giá trị không thể liệt kê đầy đủ bằng các nhãn `case` thông thường, cần một nhánh bao phủ phần còn lại, thường là `default`.
- `default` chỉ được chọn khi không có nhánh `case` phù hợp; nó **không** tự động có nghĩa là “bỏ qua lỗi” hay “giá trị hợp lệ”.
- Đối với `enum`, nếu đã liệt kê **tất cả hằng enum hiện có**, `switch` expression có thể đầy đủ mà không cần `default`.
- Cú pháp `case ... ->` không rơi xuyên sang nhánh tiếp theo (không có fall-through); nếu phải thực hiện nhiều câu lệnh rồi trả kết quả, dùng khối `{ ... yield value; }`.
- `default -> throw new ...` là hợp lệ: nhánh này kết thúc bằng ngoại lệ, nên không cần trả một giá trị giả.

Ví dụ thiếu nhánh cuối với chuỗi, **không biên dịch được**:

```java
String action = switch (command) {
    case "CREATE" -> "create";
    case "CANCEL" -> "cancel";
    // Lỗi biên dịch: switch expression không bao phủ mọi String.
};
```

Bổ sung một chính sách rõ ràng thì biểu thức mới đầy đủ:

```java
String action = switch (command) {
    case "CREATE" -> "create";
    case "CANCEL" -> "cancel";
    default -> throw new IllegalArgumentException("Unsupported command: " + command);
};
```

Các đoạn trên minh họa biểu thức bên trong phương thức có biến `command`; chương trình chạy độc lập ở phần 3.

## 2. Chọn chính sách dựa trên nguồn dữ liệu và tác động nghiệp vụ

| Tình huống | Chính sách `default` gợi ý | Lý do |
|---|---|---|
| Dữ liệu ngoài hệ thống chỉ dùng để **hiển thị** (ví dụ trạng thái mới từ đối tác) | Trả nhãn trung tính `UNKNOWN`/`OTHER`, có thể ghi nhận sự kiện để theo dõi | Giao diện vẫn hoạt động, không gán nhầm ý nghĩa cho trạng thái chưa biết |
| Lệnh đầu vào có tập hành động được hỗ trợ cố định (`CREATE`, `CANCEL`) | `throw new IllegalArgumentException(...)` hoặc trả kết quả lỗi hợp lệ của API | Không thực thi nhầm hành động; lỗi thể hiện đúng dữ liệu không được hỗ trợ |
| Một trạng thái nội bộ được xem là không thể xảy ra | `throw new IllegalStateException(...)` hoặc ngoại lệ miền tương ứng | Bộc lộ sự vi phạm bất biến để sửa nguyên nhân |
| Quyết định cấp quyền hoặc hoạt động nhạy cảm | **Từ chối theo mặc định** (`default -> false` / `DENY`) | Giá trị mới, không xác định không được cấp quyền vô tình |
| `enum` đóng với mọi hằng đều có hành vi riêng | Thường **liệt kê hết các `case` và bỏ `default`** | Khi thêm hằng enum rồi biên dịch lại, trình biên dịch nhắc cập nhật xử lý |

Các nguyên tắc thực dụng:

1. **Không cho giá trị mặc định tạo thành một đường đi thành công giả.** `default -> 0`, `default -> null` hoặc `default -> ""` thường khiến dữ liệu sai trông giống dữ liệu hợp lệ. Chỉ dùng nếu các giá trị đó được đặc tả là kết quả hợp lệ.
2. **Phân biệt dữ liệu sai với dữ liệu chưa biết nhưng chấp nhận được.** Ví dụ trạng thái từ đối tác có thể hiển thị “khác”; còn lệnh thanh toán hay thay đổi trạng thái đơn hàng phải tuân thủ danh sách hành động cho phép.
3. **Lỗi cần có ngữ cảnh.** Khi ném ngoại lệ, nêu tên miền/giá trị bị từ chối (sau khi loại bỏ dữ liệu nhạy cảm). Tại ranh giới HTTP/API, ánh xạ lỗi đầu vào thành phản hồi thích hợp thay vì để nguyên ngoại lệ làm kết quả nghiệp vụ.
4. **Quan sát giá trị mới.** Với fallback chủ đích, có thể đếm hoặc log mã chưa biết theo mức phù hợp, tránh lộ thông tin cá nhân, tránh log lặp quá nhiều. Nếu không, chính sách “khác” có thể che mất việc giao thức đối tác đã thay đổi.
5. **Chuẩn hóa có chủ đích.** `switch` với `String` so khớp chính xác và phân biệt hoa/thường; đừng tự `trim()` hoặc đổi chữ nếu hợp đồng dữ liệu không cho phép, vì thao tác đó có thể chấp nhận nhầm dữ liệu lỗi.

## 3. Ví dụ Java 17+ hoàn chỉnh, chạy được

Tạo tệp `DefaultPolicyDemo.java` với nội dung sau (cũng tương thích cú pháp `switch` expression của Java 14):

```java
public class DefaultPolicyDemo {
    enum Priority { LOW, MEDIUM, HIGH }

    // Miền enum đã bao phủ hết: không cần default.
    static String priorityLabel(Priority priority) {
        return switch (priority) {
            case LOW -> "low";
            case MEDIUM -> "medium";
            case HIGH -> "high";
        };
    }

    // Dữ liệu chỉ phục vụ hiển thị: fallback trung tính được cho phép.
    static String statusColor(String status) {
        if (status == null) return "gray";
        return switch (status) {
            case "READY" -> "green";
            case "WAITING" -> "yellow";
            default -> "gray";
        };
    }

    // Lệnh có tác động: từ chối mã chưa được cho phép.
    static String commandRoute(String command) {
        if (command == null) {
            throw new IllegalArgumentException("command is required");
        }
        return switch (command) {
            case "CREATE" -> "/create";
            case "CANCEL" -> "/cancel";
            default -> throw new IllegalArgumentException(
                "Unsupported command: " + command);
        };
    }

    public static void main(String[] args) {
        System.out.println(priorityLabel(Priority.HIGH));
        System.out.println(statusColor("READY"));
        System.out.println(statusColor("UNRECOGNIZED"));
        System.out.println(commandRoute("CREATE"));

        try {
            System.out.println(commandRoute("REFUND"));
        } catch (IllegalArgumentException ex) {
            System.out.println(ex.getMessage());
        }
    }
}
```

Biên dịch và chạy (JDK 17 trở lên):

```bash
javac -encoding UTF-8 DefaultPolicyDemo.java
java DefaultPolicyDemo
```

**Stdout chính xác:**

```text
high
green
gray
/create
Unsupported command: REFUND
```

Ba lựa chọn trong cùng chương trình có chủ ý khác nhau: `Priority` là miền đóng cần xử lý tường minh; màu hiển thị có fallback an toàn; tuyến lệnh từ chối giá trị lạ. Không có một chính sách `default` phù hợp cho tất cả trường hợp.

## 4. `enum`: vì sao đôi khi nên bỏ `default`?

Trong `priorityLabel`, `LOW`, `MEDIUM`, `HIGH` bao phủ toàn bộ `Priority`, nên trình biên dịch chấp nhận không có `default`. Giả sử sau này thêm `URGENT` vào `Priority` rồi **biên dịch lại** phương thức `priorityLabel`: switch thiếu xử lý `URGENT` và sẽ có lỗi biên dịch, giúp phát hiện công việc cần cập nhật.

Nếu viết `default -> "unknown"` từ đầu, lỗi này bị che đi và `URGENT` có thể lặng lẽ nhận nhãn sai. Nếu yêu cầu nghiệp vụ là mọi hằng enum phải được đối xử riêng, hãy ưu tiên sự kiểm tra này.

Lưu ý: khi các module được biên dịch riêng, mã switch đã biên dịch có thể gặp lỗi ở **thời gian chạy** nếu enum thay đổi mà module tiêu thụ chưa được biên dịch lại. Đừng dựa vào nhánh tổng hợp của trình biên dịch như chính sách xử lý phiên bản; cần đồng bộ và kiểm thử khi thay đổi enum.

Ngược lại, nếu `enum` có chủ ý quy định “mọi giá trị khác thuộc nhóm OTHER” thì `default` rõ ràng vẫn phù hợp. Điều quyết định là **hợp đồng nghiệp vụ**, không phải thói quen luôn thêm hoặc luôn bỏ `default`.

## 5. `default` trả giá trị qua `yield` hay ném ngoại lệ

Khi nhánh có nhiều câu lệnh nhưng vẫn trả một giá trị, dùng `yield` trong khối `-> { ... }`. Đoạn sau là **phương thức minh họa** có thể đặt bên trong một class:

```java
static String externalState(String status) {
    if (status == null) return "UNKNOWN";
    return switch (status) {
        case "OK" -> "READY";
        default -> {
            System.err.println("Unknown external status: " + status);
            yield "UNKNOWN";
        }
    };
}
```

Khi lựa chọn đúng là từ chối, dùng `default -> throw new ...`; không đặt `yield` sau `throw` và không dùng `break value` để trả kết quả của switch expression. Cách `case ... ->` có lợi vì không thể vô tình rơi sang case tiếp theo.

## 6. Các trường hợp dễ hiểu sai

**`null` không phải trường hợp mà `default` tự động bắt.** Với `switch` expression theo cú pháp Java 14/JDK 17, truyền `null` làm selector kiểu tham chiếu như `String` hoặc `enum` dẫn tới `NullPointerException` trước khi có một nhánh `default` áp dụng. Hãy quyết định rõ: từ chối bằng `Objects.requireNonNull`/kiểm tra `if`, hoặc xử lý riêng `null` nếu miền dữ liệu cho phép. Từ Java 21, `case null` có thể dùng với các dạng `switch` hỗ trợ tương ứng, nhưng cú pháp này **không chạy ở Java 14 hoặc 17**.

**`default` không bắt ngoại lệ của case khác.** Nếu một nhánh gọi hàm và hàm đó ném lỗi, `default` không được chạy như `catch`. Phần xử lý ngoại lệ thuộc cơ chế `try`/`catch` và chính sách lỗi của ứng dụng.

**Đầy đủ về cú pháp khác với hợp lệ về nghiệp vụ.** Có `default` giúp `switch` expression đầy đủ theo luật biên dịch, nhưng một `default -> "SUCCESS"` cho mã giao dịch lạ vẫn là lỗi logic nghiêm trọng.

**Chọn exception đúng ngữ cảnh.** `IllegalArgumentException` thường hợp lý với tham số đầu vào không hợp lệ; `IllegalStateException` phù hợp khi nội bộ vi phạm trạng thái mong đợi. Với ứng dụng có kiểu kết quả lỗi miền riêng, sử dụng kiểu đó theo hợp đồng API.

**Tránh nhầm với `switch` statement.** Với dạng `switch` statement truyền thống không dùng pattern, Java vẫn cho phép bỏ `default` và có thể bỏ qua đầu vào không khớp. `switch` expression thì phải exhaustive. Những dạng `switch` statement có pattern của các Java mới hơn còn có luật exhaustive riêng; không suy rộng luật statement truyền thống cho mọi cú pháp mới.

## 7. Kịch bản kiểm thử tối thiểu

| Đầu vào / thay đổi | Kết quả mong đợi |
|---|---|
| `commandRoute("CREATE")` | `"/create"` |
| `commandRoute("REFUND")` | `IllegalArgumentException`, có thông tin mã không hỗ trợ |
| `commandRoute(null)` | Lỗi đầu vào với thông điệp `command is required`, không phụ thuộc NPE ngẫu nhiên |
| `statusColor("READY")` | `"green"` |
| `statusColor("UNRECOGNIZED")` và `statusColor(null)` | `"gray"` vì **chính sách hiển thị** cho phép fallback |
| Thêm `URGENT` vào enum `Priority`, rồi biên dịch lại | Trình biên dịch buộc cập nhật `priorityLabel` nếu chưa xử lý hằng mới |
| Thay đổi format/hoa-thường của mã từ hệ thống ngoài | Test đúng hợp đồng chuẩn hóa, không âm thầm quy đổi sai |

Khi kiểm thử API thực tế, bổ sung kiểm tra phản hồi lỗi cho client, ghi nhận giá trị lạ, không cấp quyền trái phép và không thực hiện tác vụ có tác động ngoài ý muốn.

## 8. Checklist khi viết `default`

- Giá trị mới thực sự là **không được hỗ trợ**, **sai trạng thái**, hay **có thể hiển thị theo fallback**?
- Nếu là lệnh hoặc phân quyền, nhánh chưa biết có **từ chối** một cách an toàn không?
- `null` được xử lý theo hợp đồng đầu vào chưa?
- Nếu là `enum` phải xử lý mọi hằng riêng, có nên bỏ `default` để nhận lỗi biên dịch khi enum mở rộng?
- Đã thử giá trị hợp lệ, giá trị lạ, `null` và việc thêm giá trị enum hay chưa?
- Có đang dùng giá trị mặc định khiến lỗi biến thành dữ liệu thành công giả không?

## Tài liệu chính thức

- Oracle, *Switch Expressions* (Java 14): https://docs.oracle.com/en/java/javase/14/language/switch-expressions.html
- Dev.java, *Branching with Switch Expressions*: https://dev.java/learn/branching-with-switch-expressions/
- Java Language Specification, các quy tắc switch và exhaustive trong Java hiện đại: https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-14.html
