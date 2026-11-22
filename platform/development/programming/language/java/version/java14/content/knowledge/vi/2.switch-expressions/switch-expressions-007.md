# Kiểm tra độ bao phủ khi dùng enum trong switch expression

## 1. Độ bao phủ (exhaustiveness) là gì?

Khi đối số của `switch` có kiểu `enum`, tập giá trị hợp lệ của nó được xác định bởi các hằng enum. **Kiểm tra độ bao phủ** nghĩa là bảo đảm mỗi hằng enum đều có một nhánh xử lý, trực tiếp hoặc nằm trong nhóm `case`, hoặc được xử lý qua `default`.

Với **switch expression** (cú pháp trả về một giá trị, được chuẩn hóa từ Java 14), trình biên dịch yêu cầu các nhánh phải bao phủ mọi khả năng. Nếu chuyển một enum thành kết quả mà bỏ sót hằng enum và không có `default`, mã sẽ **không biên dịch**. Đây là biện pháp phát hiện thiếu logic ngay khi build, đặc biệt hữu ích khi enum được bổ sung trạng thái về sau.

Ví dụ enum `OrderStatus` có `NEW`, `PAID`, `SHIPPING`, `DELIVERED` và `CANCELED`. Một switch expression có nhánh cho đủ năm giá trị được xem là exhaustive. Nhiều hằng có thể dùng chung một `case`; không bắt buộc mỗi hằng có một nhánh riêng.

Cần phân biệt hai điều:

- **Bao phủ khi biên dịch:** `javac` đối chiếu các hằng của *kiểu enum được biết tại thời điểm biên dịch* với nhãn `case`.
- **Xử lý dữ liệu ở runtime:** đầu vào `null`, chuỗi chưa chuyển thành enum, hoặc thư viện enum thay đổi mà mã phụ thuộc chưa được biên dịch lại là những vấn đề riêng. Kiểm tra exhaustive không tự giải quyết chúng.

## 2. Ví dụ đầy đủ, chạy được trên Java 17+

Tạo tệp `EnumSwitchExhaustiveness.java` với nội dung:

~~~java
public class EnumSwitchExhaustiveness {
    enum OrderStatus {
        NEW, PAID, SHIPPING, DELIVERED, CANCELED
    }

    static String label(OrderStatus status) {
        return switch (status) {
            case NEW -> "Mới tạo";
            case PAID -> "Đã thanh toán";
            case SHIPPING -> "Đang vận chuyển";
            case DELIVERED -> "Đã giao";
            case CANCELED -> "Đã hủy";
        };
    }

    static boolean canCancel(OrderStatus status) {
        return switch (status) {
            case NEW, PAID -> true;
            case SHIPPING, DELIVERED, CANCELED -> false;
        };
    }

    public static void main(String[] args) {
        for (OrderStatus status : OrderStatus.values()) {
            System.out.println(
                status + " -> " + label(status)
                    + "; canCancel=" + canCancel(status)
            );
        }
    }
}
~~~

Biên dịch và chạy (lưu tệp dưới dạng UTF-8):

~~~bash
javac -encoding UTF-8 EnumSwitchExhaustiveness.java
java EnumSwitchExhaustiveness
~~~

Kết quả:

~~~text
NEW -> Mới tạo; canCancel=true
PAID -> Đã thanh toán; canCancel=true
SHIPPING -> Đang vận chuyển; canCancel=false
DELIVERED -> Đã giao; canCancel=false
CANCELED -> Đã hủy; canCancel=false
~~~

**Phân tích:**

1. `label` trả về `String` trực tiếp từ `switch`; mỗi `case ... ->` trả về giá trị tương ứng, không cần biến tạm hay `break`.
2. `canCancel` gộp `NEW` và `PAID` vào một nhánh; gộp ba trạng thái còn lại vào nhánh khác. Hai nhóm vẫn bao phủ **toàn bộ** enum.
3. Không cần `default` vì tất cả hằng enum hiện có đã được liệt kê. Với enum switch expression exhaustive, trình biên dịch vẫn tạo cơ chế xử lý nội bộ cho trường hợp bất thường không khớp ở runtime; đó không phải nhánh nghiệp vụ dành cho trạng thái mới.
4. Vòng lặp `values()` minh họa kết quả của từng trạng thái. Nó là kiểm thử bổ trợ; chính `javac` mới bảo đảm tính exhaustive cho expression.

## 3. Khi thiếu một enum constant thì chuyện gì xảy ra?

Xét chương trình **cố ý không biên dịch** sau, lưu thành `MissingCase.java`:

~~~java
public class MissingCase {
    enum Status { NEW, PAID, CANCELED }

    static String label(Status status) {
        return switch (status) {
            case NEW -> "Mới";
            case PAID -> "Đã thanh toán";
            // Thiếu CANCELED và không có default.
        };
    }
}
~~~

Chạy `javac MissingCase.java` sẽ báo lỗi biên dịch vì `switch expression` không bao phủ mọi giá trị của `Status`. Lời văn lỗi có thể khác nhau theo phiên bản JDK; điều cần nhớ là lỗi xảy ra **trước khi chạy chương trình**.

Có hai cách làm cho biểu thức hợp lệ:

- **Liệt kê bổ sung hằng còn thiếu:** thêm `case CANCELED -> "Đã hủy";`. Cách này giữ được lợi ích để compiler nhắc cập nhật mỗi khi enum phát triển.
- **Thêm `default`:** ví dụ `default -> "Khác";`. Cách này làm switch exhaustive ngay cả khi thiếu hằng cụ thể, nhưng cũng khiến compiler **không buộc bạn xử lý riêng** một hằng enum được thêm trong tương lai.

Với enum biểu diễn tập trạng thái nghiệp vụ đóng (thanh toán, đơn hàng, quyền truy cập...), nên **liệt kê đủ case và thường không đặt default** nếu mỗi trạng thái cần được xem xét tường minh. Dùng `default` khi yêu cầu nghiệp vụ thực sự quy định một hành vi chung cho mọi trường hợp còn lại; đồng thời chấp nhận rằng compiler sẽ không chỉ ra hằng mới bị gom vào nhánh đó.

## 4. Thêm hằng vào enum: compiler hỗ trợ bảo trì như thế nào?

Giả sử sau này thêm `RETURNED`:

~~~java
enum OrderStatus {
    NEW, PAID, SHIPPING, DELIVERED, CANCELED, RETURNED
}
~~~

Khi **biên dịch lại** chương trình ở mục 2, cả `label` lẫn `canCancel` đều thiếu `RETURNED`, nên `javac` báo lỗi tại các switch expression. Người phát triển buộc phải quyết định: trạng thái trả hàng hiển thị thế nào và có thể hủy đơn hay không. Đây là lợi ích lớn nhất của việc không đặt `default` một cách máy móc.

Tuy nhiên, bảo đảm này chỉ xuất hiện khi **biên dịch lại mã đang sử dụng enum**. Nếu một thư viện bổ sung hằng enum và ứng dụng vẫn chạy với class đã biên dịch từ phiên bản cũ, compiler không có cơ hội kiểm tra lại. Khi gặp hằng mới mà switch cũ không nhận diện, quá trình đánh giá expression có thể ném lỗi/ngoại lệ runtime (`MatchException` trong ngữ nghĩa switch hiện đại từ Java 21; bytecode được tạo bởi compiler đời cũ có thể ném `IncompatibleClassChangeError`). Không nên dựa vào ngoại lệ này như một chính sách xử lý trạng thái mới.

**Thực hành:** khi thay đổi enum dùng chung giữa các module hoặc dịch vụ, cập nhật phụ thuộc, **biên dịch lại toàn bộ nơi dùng enum**, chạy kiểm thử liên quan và xác định quy tắc nghiệp vụ cho từng hằng mới. Thêm một hằng vào enum là thay đổi có thể ảnh hưởng hành vi dù vẫn tương thích nhị phân.

## 5. Phân biệt switch expression và switch statement

Hai cấu trúc có thể dùng cú pháp mũi tên `->`, nhưng khác nhau về nghĩa:

| Tiêu chí | Switch expression | Switch statement thông thường trên enum |
| --- | --- | --- |
| Mục đích | Tính ra **một giá trị** | Thực hiện hành động |
| Tính exhaustive | **Bắt buộc** | Có thể thiếu case mà vẫn biên dịch |
| Thiếu enum constant, không có default | Lỗi biên dịch | Có thể không làm gì với giá trị bị bỏ sót |
| `case X ->` | Trả về biểu thức hoặc thực hiện khối có `yield` | Chạy câu lệnh/khối, không trả về giá trị cho switch |
| `case X:` | Có thể dùng nhưng phải `yield` giá trị trên nhánh hoàn tất bình thường | Dùng `break` nếu cần ngăn fall-through |

Ví dụ dưới đây là một **switch statement** trên enum: không xử lý `CANCELED` nhưng Java vẫn cho phép biên dịch.

~~~java
static void logStatus(OrderStatus status) {
    switch (status) {
        case NEW -> System.out.println("Mới");
        case PAID -> System.out.println("Đã thanh toán");
        // Các trạng thái khác không làm gì.
    }
}
~~~

Đoạn `logStatus` chỉ mang tính minh họa và giả định `OrderStatus` đã khai báo như ở mục 2. Trong Java 21+, một số **enhanced switch statements** (chẳng hạn switch dùng pattern) cũng phải exhaustive; quy tắc đó không làm thay đổi kết luận về switch statement thông thường trên enum ở ví dụ này.

**Kết luận khi lựa chọn cú pháp:** nếu muốn compiler kiểm soát việc ánh xạ từng enum thành kết quả, dùng **switch expression**. Nếu dùng switch statement cho tác dụng phụ, hãy tự đánh giá mức bao phủ cần thiết và thêm kiểm thử thích hợp.

## 6. Nhánh có nhiều câu lệnh: dùng yield, throw và nhóm case

Switch expression yêu cầu mỗi đường đi được chọn hoặc sinh ra giá trị hoặc kết thúc bằng ngoại lệ. Nhánh mũi tên có nhiều câu lệnh phải dùng khối `{ ... }` và `yield` để trao giá trị cho expression; `break` không thay thế được `yield`.

Ví dụ các phương thức dưới đây được đặt bên trong class có enum `OrderStatus` như mục 2:

~~~java
static String actionHint(OrderStatus status) {
    return switch (status) {
        case NEW, PAID -> {
            String prefix = "Đơn hàng";
            yield prefix + " còn xử lý được";
        }
        case SHIPPING -> "Đơn đang vận chuyển";
        case DELIVERED -> "Đơn đã hoàn tất";
        case CANCELED -> throw new IllegalStateException(
            "Không có hành động cho đơn đã hủy"
        );
    };
}
~~~

Tất cả hằng vẫn được bao phủ: `throw` là một cách kết thúc hợp lệ cho nhánh có chủ đích không tạo giá trị. Nhưng **đừng dùng `throw` một cách tùy tiện** chỉ để làm compiler im lặng; nó phải phản ánh quy tắc thật của bài toán.

Cú pháp `case X:` với `yield` cũng hợp lệ trong switch expression, nhưng `case X ->` dễ đọc hơn và tránh lỗi fall-through ngoài ý muốn.

## 7. Null không phải một enum constant

Một biến kiểu enum là kiểu tham chiếu nên có thể nhận `null`, nhưng `null` **không nằm trong `Enum.values()`**. Bao phủ toàn bộ hằng enum không đồng nghĩa xử lý được `null`.

Với Java 14–20 và cả Java mới khi không có nhánh xử lý null, truyền `null` vào `switch` sẽ gây `NullPointerException`. Cách tương thích Java 17 là kiểm tra tường minh trước switch:

~~~java
static String safeLabel(OrderStatus status) {
    if (status == null) {
        return "Chưa có trạng thái";
    }
    return label(status);
}
~~~

Từ **Java 21**, `case null` là cú pháp chính thức (không cần preview), nên có thể đưa nhánh null vào switch expression. Ví dụ sau chỉ dành cho Java 21+ và giả định enum `OrderStatus` đã khai báo:

~~~java
static String labelOrMissing(OrderStatus status) {
    return switch (status) {
        case null -> "Chưa có trạng thái";
        case NEW -> "Mới tạo";
        case PAID -> "Đã thanh toán";
        case SHIPPING -> "Đang vận chuyển";
        case DELIVERED -> "Đã giao";
        case CANCELED -> "Đã hủy";
    };
}
~~~

`default` thông thường không nên được xem là nhánh null: nếu cần xử lý null, hãy kiểm tra rõ ràng hoặc dùng `case null` trên JDK hỗ trợ. Nếu null là dữ liệu không hợp lệ theo hợp đồng API, có thể chọn `Objects.requireNonNull(status)` và báo lỗi sớm, thay vì trả một nhãn mặc định gây hiểu nhầm.

Tương tự, khi nhận chuỗi từ HTTP/JSON và gọi `OrderStatus.valueOf(text)`, chuỗi không khớp hằng sẽ gây `IllegalArgumentException` **trước khi switch được thực hiện**. Cần xác thực/chuyển đổi đầu vào ở biên ứng dụng; exhaustive switch không thay thế bước đó.

## 8. Lỗi thường gặp và cách rà soát

1. **Thêm `default -> null` để “hết lỗi compile”.** Điều này che giấu trạng thái mới và đẩy lỗi sang đoạn code phía sau. Hãy bổ sung case thật hoặc nêu chính sách fallback rõ ràng.
2. **Cho rằng chỉ cần nhóm vài trạng thái phổ biến là exhaustive.** Mọi enum constant vẫn phải xuất hiện trong các nhóm `case` nếu không có default.
3. **Cho rằng mọi switch statement đều được compiler kiểm tra như switch expression.** Statement thông thường trên enum có thể bỏ sót hằng mà vẫn biên dịch.
4. **Thay `yield` bằng `break` trong switch expression.** `break` không cung cấp giá trị; dùng `yield` cho khối nhiều câu lệnh hoặc viết biểu thức sau `->`.
5. **Tin rằng exhaustive xử lý được null hoặc dữ liệu chuỗi lạ.** Hãy xử lý null và parse input đúng chỗ.
6. **Thêm hằng vào thư viện mà không build lại ứng dụng sử dụng.** Kiểm tra exhaustive ở compile time không thể phát hiện thay đổi của thư viện khi ứng dụng chỉ chạy class đã build cũ.
7. **Dùng `default` bất kể chính sách nghiệp vụ.** Việc giữ tất cả case tường minh tạo tác dụng cảnh báo hữu ích mỗi khi một enum đóng được mở rộng.

Checklist khi review một enum switch expression:

- Kiểu của selector có thực sự là enum cụ thể cần xử lý không?
- Mỗi hằng trong enum hiện tại đã được nhắc tới trong một `case` hoặc thuộc chính sách `default` được chủ đích lựa chọn chưa?
- Mỗi nhánh sinh ra giá trị đúng kiểu hoặc `throw` có chủ đích chưa?
- Có hợp đồng rõ ràng về null, dữ liệu đầu vào và việc bổ sung hằng enum về sau chưa?
- Các module phụ thuộc enum đã được biên dịch lại và kiểm thử sau thay đổi chưa?

## 9. Tự luyện tập

**Bài 1.** Trong ví dụ mục 2, thêm trạng thái `RETURNED`. Biên dịch lại và quan sát các chỗ compiler yêu cầu sửa. Quyết định nhãn hiển thị và quy tắc `canCancel` rồi bổ sung `case` phù hợp; kiểm tra lại đầu ra của `values()`.

**Bài 2.** Thêm `default -> false` vào `canCancel` trước khi tạo `RETURNED`. So sánh khả năng phát hiện nhánh nghiệp vụ bị bỏ sót khi biên dịch lại. Giải thích vì sao build thành công chưa chắc đồng nghĩa nghiệp vụ đúng.

**Bài 3.** Truyền `null` cho `label`, rồi thử `safeLabel`. Nếu đang dùng JDK 21+, thử `labelOrMissing` và lý giải vì sao `case null` là vấn đề tách biệt với độ bao phủ hằng enum.

## Tài liệu chính thức

- [Oracle — Switch Expressions (Java 21)](https://docs.oracle.com/en/java/javase/21/language/switch-expressions-and-statements.html): cú pháp, `yield` và quy tắc exhaustive.
- [Java Language Specification — Switch Blocks (Java 21)](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11.1.1): tiêu chí exhaustive và phân biệt switch statement.
- [OpenJDK JEP 361 — Switch Expressions](https://openjdk.org/jeps/361): tính năng được chuẩn hóa trong Java 14.
- [Java Language Specification — Switch Expressions (Java 21)](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.28): đánh giá expression, kết quả và trường hợp không khớp tại runtime.
