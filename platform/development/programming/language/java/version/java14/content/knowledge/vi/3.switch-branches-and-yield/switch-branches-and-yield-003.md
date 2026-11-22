# Nhánh ném ngoại lệ thay cho trả giá trị trong switch expression (Java 14+)

## 1. Quy tắc cốt lõi: switch expression có thể trả giá trị **hoặc ném ngoại lệ**

Một `switch expression` được dùng ở vị trí cần **một giá trị**, chẳng hạn vế phải của phép gán hoặc sau `return`:

~~~java
String message = switch (status) {
    case READY -> "Sẵn sàng";
    case RUNNING -> "Đang xử lý";
    case REJECTED -> throw new IllegalStateException("Yêu cầu bị từ chối");
};
~~~

Ở hai nhánh đầu, biểu thức `switch` hoàn tất bình thường và cho ra `String`. Khi `status == REJECTED`, nhánh cuối thực thi `throw`: quá trình tính giá trị **kết thúc đột ngột bằng ngoại lệ**; không hề có giá trị `String` nào được tạo ra để gán cho `message`.

Điều này hoàn toàn hợp lệ trong Java 14 trở lên (`switch expression` là tính năng chính thức, không cần bật preview). Một nhánh của switch expression phải:

- Cung cấp giá trị bằng biểu thức sau `->`, chẳng hạn `case READY -> "OK";`;
- Hoặc, trong một khối `{ ... }`, hoàn tất với `yield <giá trị>;`;
- Hoặc kết thúc bằng ngoại lệ qua `throw`.

Đây là **quy tắc luồng điều khiển**, không có nghĩa mọi ngoại lệ đều là lựa chọn tốt về nghiệp vụ. Ném ngoại lệ khi trạng thái thực sự không cho phép tạo kết quả hoặc khi thao tác thất bại; với trạng thái bình thường, ưu tiên trả kết quả có nghĩa.

## 2. Cú pháp hợp lệ: throw trực tiếp, throw trong khối, và yield

Cú pháp `case ... ->` của switch hỗ trợ ba dạng phía bên phải: biểu thức, câu lệnh `throw`, hoặc khối lệnh. Vì vậy hai dạng sau tương đương về việc phát sinh ngoại lệ:

~~~java
case REJECTED -> throw new IllegalStateException("Không xử lý được");
~~~

~~~java
case REJECTED -> {
    throw new IllegalStateException("Không xử lý được");
}
~~~

Khối lệnh hữu ích nếu phải ghi log, tính toán thông tin lỗi hay kiểm tra một điều kiện trước khi `throw`. Chẳng hạn, khi một nhánh **có thể** trả kết quả hoặc có thể thất bại, dùng `yield` trên đường thành công và `throw` trên đường thất bại:

~~~java
enum Status { OK, FAILED }

static int toCode(Status status, boolean failFast) {
    return switch (status) {
        case OK -> 200;
        case FAILED -> {
            if (failFast) {
                throw new IllegalStateException("Thao tác thất bại");
            }
            yield 500;
        }
    };
}
~~~

Đoạn trên giả định được đặt bên trong một class, có `enum Status` như đã khai báo. Với `FAILED` và `failFast == true`, exception thoát ra; ngược lại, `yield 500` kết thúc nhánh bằng giá trị số nguyên. Không có nhánh nào rơi ra cuối khối mà thiếu giá trị.

**Khác biệt quan trọng:**

| Cấu trúc | Tác động đến switch expression |
| --- | --- |
| `case OK -> 200;` | Đưa giá trị `200` vào kết quả expression |
| `case OK -> { yield 200; }` | Đưa giá trị `200` ra khỏi khối nhánh |
| `case FAILED -> throw new RuntimeException(...);` | Kết thúc đột ngột, chuyển quyền điều khiển theo cơ chế exception |
| `case FAILED -> { throw new RuntimeException(...); }` | Tương tự, nhưng ở trong khối |
| `case FAILED -> { /* chỉ in log */ }` | Không hợp lệ nếu khối có thể hoàn tất bình thường mà không `yield`/`throw` |

**Không** viết `yield throw new ...`: `throw` là một câu lệnh, không phải biểu thức mang giá trị để `yield`. Cũng không dùng `break` để trả về kết quả của switch expression.

## 3. Chương trình hoàn chỉnh chạy trên Java 17+

Ví dụ dưới đây kết hợp ba loại nhánh: trả giá trị trực tiếp, trả giá trị qua `yield`, và ném ngoại lệ. Đồng thời minh họa cả ngoại lệ **unchecked** và **checked**.

Lưu đúng tên tệp `SwitchThrowBranchDemo.java`, mã nguồn mã hóa UTF-8:

~~~java
import java.io.IOException;

public class SwitchThrowBranchDemo {
    enum RequestState {
        READY, RUNNING, REJECTED
    }

    enum Source {
        CACHE, REMOTE
    }

    static String message(RequestState state) {
        return switch (state) {
            case READY -> "Sẵn sàng";
            case RUNNING -> {
                String prefix = "Đang";
                yield prefix + " xử lý";
            }
            case REJECTED -> throw new IllegalStateException(
                "Yêu cầu đã bị từ chối"
            );
        };
    }

    static int loadCount(Source source) throws IOException {
        return switch (source) {
            case CACHE -> 3;
            case REMOTE -> throw new IOException(
                "Không đọc được nguồn từ xa"
            );
        };
    }

    public static void main(String[] args) {
        for (RequestState state : RequestState.values()) {
            try {
                System.out.println(state + ": " + message(state));
            } catch (IllegalStateException ex) {
                System.out.println(
                    state + ": ERROR - " + ex.getMessage()
                );
            }
        }

        try {
            System.out.println("CACHE: " + loadCount(Source.CACHE));
            System.out.println("REMOTE: " + loadCount(Source.REMOTE));
        } catch (IOException ex) {
            System.out.println(
                "REMOTE: ERROR - " + ex.getMessage()
            );
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 SwitchThrowBranchDemo.java
java SwitchThrowBranchDemo
~~~

Kết quả chuẩn:

~~~text
READY: Sẵn sàng
RUNNING: Đang xử lý
REJECTED: ERROR - Yêu cầu đã bị từ chối
CACHE: 3
REMOTE: ERROR - Không đọc được nguồn từ xa
~~~

**Giải thích luồng chạy:**

1. Với `READY`, nhánh trả `"Sẵn sàng"`; `System.out.println` nhận được chuỗi và in kết quả.
2. Với `RUNNING`, chương trình vào khối, tạo `prefix` rồi `yield` chuỗi `"Đang xử lý"`.
3. Với `REJECTED`, `IllegalStateException` được ném **trước khi** lệnh `println` hoàn tất việc tính đối số. Khối `catch` xử lý ngoại lệ và in thông báo lỗi; không có dòng kết quả thành công giả.
4. Với `CACHE`, `loadCount` trả số `3`. Với `REMOTE`, `IOException` xuất hiện; biểu thức nối chuỗi `"REMOTE: " + loadCount(...)` không hoàn tất, nên chỉ dòng do `catch` in ra xuất hiện.

Lệnh `return switch (...) { ... };` trả về giá trị **chỉ khi** nhánh đã chọn tạo được giá trị; nó không bắt buộc mọi lần gọi phương thức phải trả về bình thường. Nếu ngoại lệ không được bắt ở nơi gọi, nó tiếp tục lan theo call stack theo quy tắc Java thông thường.

## 4. Ngoại lệ checked và unchecked: throw không loại bỏ nghĩa vụ xử lý

Một nhánh `throw` được phép ném cả ngoại lệ unchecked (ví dụ `IllegalStateException`, `IllegalArgumentException`) lẫn checked (ví dụ `IOException`). **Switch expression không tạo ngoại lệ đặc biệt cho quy tắc checked exception.**

- `IllegalStateException` là unchecked; phương thức `message` không phải khai báo `throws IllegalStateException`, dù phía gọi vẫn có thể `catch`.
- `IOException` là checked; `loadCount` trong chương trình trên khai báo `throws IOException`, và mã gọi có `catch (IOException ex)`. Nếu bỏ cả khai báo lẫn xử lý, chương trình không biên dịch.
- Loại exception nên thể hiện nguyên nhân thất bại. `IllegalArgumentException` phù hợp cho tham số không hợp lệ; `IllegalStateException` phù hợp cho trạng thái không cho phép thao tác; `IOException` phù hợp cho lỗi I/O. Đừng ném một ngoại lệ chung cho mọi tình huống nếu điều đó làm mất thông tin cần xử lý.

Ví dụ nguyên tắc:

~~~java
// Hợp lệ nếu phương thức khai báo throws IOException,
// hoặc xử lý IOException ngay trong phương thức:
case REMOTE -> throw new IOException("Kết nối thất bại");
~~~

Việc dùng `throw` **không đổi kiểu kết quả** của nhánh thành `IOException`. Nhánh này không tạo giá trị; các nhánh thực sự trả giá trị mới quyết định kiểu mà switch expression phải tương thích tại vị trí sử dụng.

## 5. Độ bao phủ (exhaustiveness) vẫn bắt buộc

Với switch expression, trình biên dịch yêu cầu **mọi khả năng của selector đều được bao phủ**. Nhánh `throw` được tính là một cách xử lý hợp lệ cho một trường hợp cụ thể; nó không tự biến những hằng enum **bị thiếu case** thành đã được xử lý.

Trong chương trình ở mục 3, `RequestState` chỉ có `READY`, `RUNNING` và `REJECTED`, nên ba case là đủ. Nếu thêm `CANCELED` vào enum mà không sửa `message` và không có `default`, biên dịch lại sẽ báo lỗi vì switch expression không exhaustive. Việc `REJECTED` có `throw` không giải quyết thiếu sót này.

Có thể viết `default -> throw new IllegalArgumentException("Unknown state");` khi muốn từ chối mọi giá trị không được nhận diện. Tuy nhiên, với một enum chứa tập trạng thái nghiệp vụ cố định, **liệt kê hết các case và không thêm default khi không cần** thường giúp compiler báo khi có hằng mới cần quyết định xử lý. Nếu đặt `default`, các hằng mới có thể đi thẳng vào nhánh ném ngoại lệ mà không tạo lỗi compile, kể cả khi nghiệp vụ muốn xử lý riêng chúng.

Ví dụ lựa chọn có chủ ý:

~~~java
enum PaymentResult { SUCCESS, DECLINED, ERROR }

static String receipt(PaymentResult result) {
    return switch (result) {
        case SUCCESS -> "Đã thanh toán";
        case DECLINED -> "Bị từ chối";
        case ERROR -> throw new IllegalStateException(
            "Không thể tạo biên nhận khi xử lý lỗi"
        );
    };
}
~~~

Ví dụ này là đoạn phương thức minh họa, đặt trong một class có enum `PaymentResult` như khai báo. Ném ngoại lệ cho `ERROR` chỉ đúng nếu hợp đồng nghiệp vụ thực sự cấm tạo biên nhận ở trạng thái đó. Nếu `ERROR` phải hiện nhãn cho người dùng, hãy trả một chuỗi thích hợp thay vì throw.

## 6. Lỗi biên dịch thường gặp

Các ví dụ lỗi sau **cố ý không chạy được**, dùng để phân biệt cách viết. Giả định có `enum State { OK, FAIL }` và biến `state` kiểu `State`.

**Lỗi 1 — Khối có thể chạy hết mà không tạo giá trị:**

~~~java
String label = switch (state) {
    case OK -> "OK";
    case FAIL -> {
        System.out.println("Không có kết quả");
        // Thiếu yield hoặc throw: lỗi biên dịch.
    }
};
~~~

Dù đã in thông báo, nhánh `FAIL` không trả kết quả và không kết thúc bằng exception. Muốn coi đây là lỗi thật, thêm `throw new IllegalStateException("Không có kết quả");`; nếu là tình huống hợp lệ, dùng `yield "Thất bại";`.

**Lỗi 2 — Tạo exception nhưng không ném:**

~~~java
String label = switch (state) {
    case OK -> "OK";
    case FAIL -> new IllegalStateException("Thất bại");
};
~~~

Đây là một **biểu thức tạo đối tượng**, không phải `throw`. Một nhánh trả `String`, nhánh kia trả `IllegalStateException`; kết quả không tương thích với phép gán `String`. Sửa thành `case FAIL -> throw new IllegalStateException("Thất bại");`.

**Lỗi 3 — Câu lệnh không thể tới sau throw:**

~~~java
String label = switch (state) {
    case OK -> "OK";
    case FAIL -> {
        throw new IllegalStateException("Thất bại");
        // yield "Khôi phục"; // Bỏ chú thích sẽ thành mã không thể tới.
    }
};
~~~

Vì `throw` vô điều kiện đã kết thúc nhánh, mọi câu lệnh thực thi sau nó trong cùng đường đi đều không thể tới; `javac` báo lỗi `unreachable statement`. Nếu muốn có hai hướng, đặt `throw` trong điều kiện và để `yield` ở đường còn lại, như mục 2.

**Lỗi 4 — Dùng return/break thay cho yield:**

Trong thân nhánh của một switch **expression**, `return` không phải cách cung cấp giá trị của expression và không được nhảy xuyên qua expression để thoát phương thức; `break` cũng không được dùng để thoát một switch expression. Khi cần cho nhánh khối sinh ra kết quả, viết `yield value;`. Khi cần báo lỗi, viết `throw ...;`.

**Lỗi 5 — Quên kết thúc một biểu thức sau return hoặc phép gán:**

~~~java
static String result(State state) {
    return switch (state) {
        case OK -> "OK";
        case FAIL -> throw new IllegalStateException("Thất bại");
    }; // Dấu ; kết thúc return statement.
}
~~~

Dấu `;` sau `}` cần có vì toàn bộ `return switch (...) { ... };` là một câu lệnh `return`. Dấu chấm phẩy sau từng nhánh `->` cũng là một phần cú pháp ở các ví dụ này.

## 7. Vị trí bắt ngoại lệ và tính nguyên tử của biểu thức

Khi một nhánh ném ngoại lệ, biểu thức bao quanh nó cũng không hoàn tất. Ví dụ:

~~~java
String text = "Kết quả: " + switch (state) {
    case OK -> "thành công";
    case FAIL -> throw new IllegalStateException("Hỏng");
};
System.out.println(text);
~~~

Nếu `state == FAIL` thì phép nối chuỗi không hoàn tất, phép gán `text` không được thực hiện và dòng `println` phía sau không chạy trong luồng bình thường. Ngoại lệ tiếp tục lan đến `catch` thích hợp bên ngoài (nếu có).

Đối với API, cần chọn **ranh giới bắt ngoại lệ** hợp lý: tầng nội bộ có thể `throw` để giữ thông tin lỗi; tầng điều phối, controller hoặc lớp giao tiếp với người dùng có thể bắt lỗi và chuyển thành kết quả/API response phù hợp. Không nên bắt ngay trong nhánh chỉ để che một thất bại, hoặc trả `null` khiến nơi gọi khó nhận biết nguyên nhân.

Nếu phương thức xử lý dữ liệu hoặc tác động lên hệ thống trước khi throw (ghi log, gửi yêu cầu mạng, cập nhật cơ sở dữ liệu), việc ném exception **không tự hoàn tác** các tác động đó. Transaction/compensation phải được thiết kế riêng theo ngữ cảnh ứng dụng.

## 8. Giá trị null và trạng thái hợp lệ nhưng không mong muốn

Các enum constant đều đã được bao phủ cũng không có nghĩa `null` được xử lý. Trên Java 17, truyền `null` vào `switch` enum thông thường gây `NullPointerException` trước khi có nhánh giá trị nào phù hợp. Muốn đưa ra lỗi rõ ràng, kiểm tra đầu vào trước:

~~~java
static String requireMessage(RequestState state) {
    if (state == null) {
        throw new IllegalArgumentException("state không được null");
    }
    return message(state);
}
~~~

Đoạn này dùng enum và phương thức `message` đã định nghĩa ở chương trình mục 3; là ví dụ bổ sung trong cùng class.

Từ Java 21, cú pháp `case null -> ...` là tính năng chính thức và có thể dùng trong switch expression nếu muốn xử lý null ngay trong switch. Đây là lựa chọn cho dự án Java 21+, **không dùng trực tiếp trong ví dụ cần chạy trên Java 17**. Nhánh `default` đơn thuần không nên được xem là cơ chế bắt null cho switch thông thường.

Tách hai trường hợp:

- **Trạng thái hợp lệ nhưng có kết quả thất bại:** ví dụ `DECLINED` có thể là một kết quả kinh doanh bình thường. Khi ấy nên trả một giá trị biểu diễn việc bị từ chối.
- **Trạng thái không hợp lệ đối với phép tính hiện tại:** ví dụ gọi hàm tạo biên nhận khi hệ thống chưa có dữ liệu bắt buộc. Khi ấy một `throw` được đặt có chủ đích giúp hợp đồng phương thức rõ ràng.

Lạm dụng throw cho mọi trạng thái không vui sẽ khiến luồng nghiệp vụ khó theo dõi và buộc tầng gọi xử lý exception cho những trường hợp vốn nên mô hình hóa bằng giá trị.

## 9. Checklist khi viết hoặc review

1. Tất cả giá trị selector có được bao phủ bởi `case`/`default` theo quy tắc exhaustive của switch expression?
2. Trên **mỗi đường đi** trong khối nhánh, chương trình hoặc `yield` một giá trị hợp lệ, hoặc `throw`?
3. `throw` có biểu thị một lỗi thật theo hợp đồng phương thức, thay vì thay thế tùy tiện cho một kết quả kinh doanh bình thường?
4. Loại ngoại lệ và thông điệp có đủ chính xác để tầng gọi xử lý không? Với checked exception, đã `catch` hoặc khai báo `throws`?
5. Mã gọi có hiểu rằng biểu thức và các phép tính bao quanh sẽ không hoàn tất nếu nhánh ném exception?
6. Đã xác định cách xử lý `null`, cách cập nhật khi enum có hằng mới, và kiểm thử các nhánh trả giá trị lẫn nhánh throw?
7. Nếu nhánh có tác động phụ trước khi ném ngoại lệ, đã cân nhắc khả năng cần rollback/compensation?

## 10. Bài tập thực hành

**Bài 1 — Chọn yield hay throw.** Mở rộng `RequestState` ở mục 3 với `PAUSED`. Tùy hợp đồng nghiệp vụ, trả `"Tạm dừng"` hoặc ném một exception có thông điệp rõ nghĩa. Biên dịch lại để thấy compiler buộc cập nhật switch expression khi chưa có default.

**Bài 2 — Nhánh điều kiện.** Viết `toCode(Status status, boolean failFast)` theo mục 2. Gọi hai lần với `FAILED, true` và `FAILED, false`; quan sát một lần chuyển quyền điều khiển sang `catch` và một lần trả `500`.

**Bài 3 — Checked exception.** Bỏ `throws IOException` khỏi `loadCount` và quan sát lỗi compile. Sau đó khôi phục, giải thích vì sao nhánh `case CACHE -> 3` vẫn dùng được dù nhánh khác có khả năng ném `IOException`.

## Tài liệu chính thức

- [Oracle — Switch Expressions (Java 21)](https://docs.oracle.com/en/java/javase/21/language/switch-expressions-and-statements.html): các dạng nhánh `->`, `yield`, `throw` và quy tắc kết thúc.
- [Oracle — Switch Expressions and Statements (Java 26)](https://docs.oracle.com/en/java/javase/26/language/switch-expressions-statements.html): hướng dẫn cập nhật về switch và khả năng bao phủ.
- [OpenJDK JEP 361 — Switch Expressions](https://openjdk.org/jeps/361): thiết kế và việc chuẩn hóa tính năng trong Java 14.
- [Java Language Specification — Switch Expressions (Java 25)](https://docs.oracle.com/javase/specs/jls/se25/html/jls-15.html#jls-15.28): ngữ nghĩa biểu thức, nhánh `yield` và hoàn tất đột ngột.
