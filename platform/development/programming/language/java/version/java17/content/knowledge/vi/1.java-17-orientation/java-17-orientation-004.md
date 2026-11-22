# Quan hệ giữa `sealed`, `record` và pattern matching trong Java 17

Trong Java 17, `sealed`, `record` và pattern matching có thể kết hợp để mô hình hóa một tập kết quả hoặc trạng thái có số biến thể được kiểm soát, mỗi biến thể mang dữ liệu riêng và được xử lý theo đúng kiểu của nó. Ba tính năng giải quyết **ba vấn đề khác nhau**:

- **`sealed`** trả lời: *Những kiểu nào được phép kế thừa hoặc triển khai kiểu gốc này?*
- **`record`** trả lời: *Một biến thể chỉ mang dữ liệu được khai báo gọn, rõ và nhất quán như thế nào?*
- **Pattern matching với `instanceof`** trả lời: *Khi nhận một giá trị của kiểu gốc, làm thế nào nhận diện biến thể cụ thể và sử dụng nó mà không phải ép kiểu thủ công?*

Chúng **không phụ thuộc lẫn nhau**: một `record` không nhất thiết thuộc cây `sealed`; một cây `sealed` có thể chứa class thông thường; và `instanceof` pattern matching dùng được với nhiều kiểu tham chiếu, không chỉ `record`. Sự kết hợp đặc biệt hữu ích khi biểu diễn **kiểu tổng** (*sum type*: một giá trị thuộc một trong các biến thể) với các **kiểu tích** (*product type*: một biến thể chứa nhiều thành phần dữ liệu).

## 1. Trạng thái các tính năng trên Java 17

| Tính năng | Có thể sử dụng ổn định trên Java 17? | Ý nghĩa |
| --- | --- | --- |
| `record` | Có; chính thức từ Java 16 | Khai báo class chuyên mang dữ liệu, có constructor, accessor, `equals`, `hashCode`, `toString` được sinh tự động. |
| `sealed class` / `sealed interface` | Có; chính thức từ Java 17 | Giới hạn các kiểu con trực tiếp được phép kế thừa hoặc triển khai. |
| Pattern matching cho `instanceof` | Có; chính thức từ Java 16 | Kết hợp kiểm tra kiểu và tạo biến pattern đã được ép kiểu an toàn. |
| Pattern matching cho `switch` | **Chưa là tính năng chính thức trong Java 17** | Trên Java 17 chỉ ở trạng thái *preview*; chính thức từ Java 21. |
| Record patterns, ví dụ `case Point(int x, int y)` | **Không có bản chính thức trên Java 17** | Phân rã các thành phần record bằng pattern; chính thức từ Java 21. |

Tất cả ví dụ Java 17 chạy được dưới đây chỉ dùng các tính năng **đã chính thức**, không cần `--enable-preview`. Khi đọc tài liệu viết cho Java 21 trở lên, cần phân biệt **type pattern** (`instanceof Success s`) với **record pattern** (`Success(var value)`): record pattern chưa dùng được trong mã Java 17 thông thường.

## 2. Bài toán: một kết quả có nhiều dạng dữ liệu

Giả sử thao tác đăng nhập trả về đúng một trong ba kết quả:

1. **Thành công**: có mã người dùng và tên hiển thị.
2. **Sai mật khẩu**: có số lần thử còn lại.
3. **Tài khoản bị khóa**: có lý do khóa.

Nếu dùng một object với các trường `success`, `userId`, `remainingAttempts`, `lockReason` đều tùy chọn, chương trình có thể tạo nhiều tổ hợp vô nghĩa: thành công nhưng đồng thời có lý do bị khóa, hoặc sai mật khẩu mà vẫn có `userId`. Một phương án rõ hơn là khai báo **một kiểu gốc và các biến thể có cấu trúc khác nhau**:

```text
LoginResult (sealed interface)
├── LoggedIn       (record: userId, displayName)
├── WrongPassword  (record: remainingAttempts)
└── Locked         (record: reason)
```

`LoginResult` xác định tập biến thể trực tiếp hợp lệ; mỗi `record` xác định dữ liệu của biến thể; `instanceof` giúp xử lý giá trị khi chưa biết biến thể tại thời điểm biên dịch.

### Ví dụ đầy đủ, chạy được với Java 17

Lưu đoạn mã sau thành `LoginDemo.java`:

```java
import java.util.Objects;

public class LoginDemo {

    public sealed interface LoginResult
            permits LoggedIn, WrongPassword, Locked {
    }

    public record LoggedIn(long userId, String displayName)
            implements LoginResult {

        public LoggedIn {
            if (userId <= 0) {
                throw new IllegalArgumentException("userId must be positive");
            }

            displayName = Objects.requireNonNull(displayName, "displayName").strip();
            if (displayName.isEmpty()) {
                throw new IllegalArgumentException("displayName must not be blank");
            }
        }
    }

    public record WrongPassword(int remainingAttempts)
            implements LoginResult {

        public WrongPassword {
            if (remainingAttempts < 0) {
                throw new IllegalArgumentException("remainingAttempts must be non-negative");
            }
        }
    }

    public record Locked(String reason)
            implements LoginResult {

        public Locked {
            reason = Objects.requireNonNull(reason, "reason").strip();
            if (reason.isEmpty()) {
                throw new IllegalArgumentException("reason must not be blank");
            }
        }
    }

    public static String render(LoginResult result) {
        Objects.requireNonNull(result, "result");

        if (result instanceof LoggedIn success) {
            return "Đăng nhập thành công: "
                    + success.displayName() + " (#" + success.userId() + ")";
        }

        if (result instanceof WrongPassword failure) {
            return "Sai mật khẩu; còn " + failure.remainingAttempts() + " lần thử";
        }

        if (result instanceof Locked locked) {
            return "Tài khoản bị khóa: " + locked.reason();
        }

        // if/instanceof không được Java 17 kiểm tra tính bao phủ mọi biến thể.
        throw new IllegalStateException(
                "Chưa xử lý kiểu kết quả: " + result.getClass().getName());
    }

    public static void main(String[] args) {
        System.out.println(render(new LoggedIn(7, " Lan ")));
        System.out.println(render(new WrongPassword(2)));
        System.out.println(render(new Locked("Vi phạm giới hạn đăng nhập")));
    }
}
```

Biên dịch và chạy bằng JDK 17:

```bash
javac --release 17 LoginDemo.java
java LoginDemo
```

Kết quả:

```text
Đăng nhập thành công: Lan (#7)
Sai mật khẩu; còn 2 lần thử
Tài khoản bị khóa: Vi phạm giới hạn đăng nhập
```

Ví dụ cũng minh họa **compact constructor** của record: các tham số constructor có thể được kiểm tra hoặc chuẩn hóa (`strip()`), sau đó Java tự gán giá trị cuối cùng vào các trường thành phần của record. `displayName()` và `remainingAttempts()` là accessor được sinh tự động, không phải `getDisplayName()` và `getRemainingAttempts()`.

## 3. `sealed`: kiểm soát các nhánh của mô hình

Với khai báo:

```java
sealed interface LoginResult permits LoggedIn, WrongPassword, Locked {}
```

trình biên dịch chỉ cho phép **các kiểu được liệt kê trong `permits`** trực tiếp triển khai `LoginResult`. Ví dụ `class Guest implements LoginResult {}` sẽ không hợp lệ nếu `Guest` không có trong danh sách cho phép. Điều này giúp tác giả API biết các dạng kết quả trực tiếp có thể xuất hiện và ngăn mã bên ngoài tùy ý bổ sung một biến thể mới vào giao diện đã đóng.

Một kiểu con trực tiếp của `sealed` cần thể hiện nó sẽ tiếp tục chính sách kế thừa ra sao:

| Cách khai báo kiểu con | Hệ quả |
| --- | --- |
| `final class` hoặc `record` | Không thể có kiểu con tiếp theo; `record` vốn **ngầm định `final`**. |
| `sealed class` / `sealed interface` | Tiếp tục giới hạn các kiểu con trực tiếp ở cấp kế tiếp. |
| `non-sealed class` / `non-sealed interface` | Mở lại quyền kế thừa hoặc triển khai qua nhánh đó. |

Ví dụ ngắn:

```java
sealed interface Message permits TextMessage, ExtensibleMessage {}

record TextMessage(String text) implements Message {}

non-sealed interface ExtensibleMessage extends Message {}

class CustomMessage implements ExtensibleMessage {}
```

Ở đây `Message` chỉ có hai kiểu con **trực tiếp**, nhưng cây kiểu vẫn có thể mở rộng qua `ExtensibleMessage`. Vì thế, `sealed` không nhất thiết có nghĩa mọi lớp cháu/chắt của kiểu gốc đều được liệt kê hữu hạn. Khi muốn một tập biến thể thực sự đóng, các nhánh cuối thường dùng `record` hoặc `final class`, và tránh `non-sealed`.

Các giới hạn quan trọng trong Java 17:

- Kiểu được liệt kê trong `permits` phải kế thừa/triển khai **trực tiếp** kiểu `sealed`, không chỉ gián tiếp.
- Trong **named module** (có `module-info.java`), kiểu gốc và các kiểu con được cấp phép phải cùng module; trong **unnamed module**, chúng phải cùng package.
- Nếu các kiểu con được khai báo trong cùng một compilation unit, danh sách `permits` có thể được suy ra, nhưng khai báo tường minh giúp đọc cấu trúc dễ hơn.
- `sealed` giới hạn **quyền tạo kiểu con**, không kiểm soát ai được khởi tạo object của những kiểu con có constructor truy cập được; đây cũng không phải một cơ chế xác thực hay phân quyền bảo mật.

**Vì sao ở ví dụ chính dùng `sealed interface`?** Một record luôn kế thừa `java.lang.Record`, nên không thể kế thừa thêm một class tùy ý. Nhưng record **có thể `implements` interface**. Do vậy, `sealed interface` thường là lựa chọn tự nhiên khi các biến thể đều là record. Nếu cần chia sẻ cài đặt hoặc trạng thái của một cây class thông thường, `sealed abstract class` vẫn là lựa chọn hợp lệ, nhưng các nhánh record không thể `extends` class đó.

## 4. `record`: đóng gói dữ liệu khác nhau cho từng biến thể

Xét:

```java
record WrongPassword(int remainingAttempts) implements LoginResult {}
```

Java sinh ra thành phần lưu trữ `private final`, constructor chuẩn tương ứng, accessor `remainingAttempts()`, cùng `equals`, `hashCode` và `toString` theo các thành phần record. Ví dụ hai `new WrongPassword(2)` có `equals()` bằng `true`, còn `new WrongPassword(1)` thì khác.

Vì record là `final`, một kiểu con khác không thể thay đổi cấu trúc của `WrongPassword` bằng cách kế thừa nó. Đây là lý do record hợp với **biến thể lá** của cây `sealed`: mỗi nhánh có kiểu và dữ liệu rõ ràng.

### Record không bảo đảm bất biến sâu

Một record giữ tham chiếu thành phần bằng trường `final`; nếu thành phần trỏ tới object có thể thay đổi, nội dung object đó vẫn có thể đổi. Ví dụ `record Tags(List<String> values) {}` không tự chặn người dùng sửa `ArrayList` truyền vào. Khi muốn dữ liệu ít thay đổi ngoài ý muốn, cần **sao chép phòng vệ**:

```java
import java.util.List;
import java.util.Objects;

record Tags(List<String> values) {
    public Tags {
        values = List.copyOf(Objects.requireNonNull(values, "values"));
    }
}
```

`List.copyOf` tạo danh sách không cho chỉnh sửa qua API của `List` (đồng thời từ chối phần tử `null`), nhưng **không sao chép sâu** các object mutable bên trong danh sách. Với array hoặc cấu trúc lồng nhau có thể thay đổi, phải cân nhắc sao chép ở cả constructor và accessor nếu muốn tránh lộ trạng thái nội bộ. Việc record sinh `equals()` cũng **không** có nghĩa các mảng bên trong được so sánh từng phần tử: thành phần kiểu array vẫn tuân theo phép so sánh của array, vốn dựa trên identity nếu không tự thiết kế lại.

### Khi nào không nên chọn record?

Record phù hợp với kết quả trả về, thông điệp, lệnh, giá trị cấu hình hoặc dữ liệu chỉ đọc có cấu trúc cố định. Một đối tượng có **vòng đời thay đổi trạng thái**, cần kế thừa class hay phải tuân thủ cơ chế proxy/no-arg constructor của một framework có thể phù hợp với class thông thường hơn. `sealed` không bắt buộc phải đi kèm record: một nhánh `final class` hoàn toàn hợp lệ nếu hành vi và trạng thái của nó cần được cài đặt theo cách khác.

## 5. Pattern matching: làm việc với đúng biến thể

Trước khi có pattern matching cho `instanceof`, việc kiểm tra kiểu rồi ép kiểu phải viết thành hai thao tác:

```java
if (result instanceof LoggedIn) {
    LoggedIn success = (LoggedIn) result;
    System.out.println(success.displayName());
}
```

Trên Java 17, có thể viết:

```java
if (result instanceof LoggedIn success) {
    System.out.println(success.displayName());
}
```

`success` là **pattern variable** có kiểu tĩnh `LoggedIn`, chỉ khả dụng tại các vị trí mà phân tích luồng của trình biên dịch xác định việc so khớp đã thành công. Việc đọc dữ liệu qua `success.displayName()` vì vậy không cần ép kiểu thủ công.

Pattern variable cũng có thể xuất hiện trong điều kiện phối hợp bằng `&&`:

```java
if (result instanceof LoggedIn success && success.userId() > 0) {
    System.out.println(success.displayName());
}
```

Toán hạng bên phải chỉ được đánh giá khi phép `instanceof` bên trái đúng. Không thể mặc nhiên dùng `success` ở mọi nhánh khác hoặc trong một biểu thức `||` mà nhánh bên phải vẫn có thể chạy khi phép so khớp thất bại. Phạm vi biến do **flow scoping** quyết định, không đơn thuần bởi cặp dấu ngoặc nhọn.

**Điểm phân biệt quan trọng:** `instanceof LoggedIn success` trên Java 17 chỉ nhận diện **kiểu** và đưa ra một tham chiếu đã được kiểm tra kiểu. Nó **không tự bóc** `userId` và `displayName` thành các biến riêng; để lấy từng thành phần, vẫn gọi `success.userId()` và `success.displayName()`. Cú pháp bóc thành phần bằng *record pattern* được chuẩn hóa ở Java 21.

### Có thể tự động biết đã xử lý hết các nhánh không?

**Không, với chuỗi `if (x instanceof ...)` trên Java 17.** Dù `LoginResult` chỉ cho phép ba biến thể, trình biên dịch không bắt buộc `render` phải xét đủ ba nhánh. Nếu mai sau thêm `Expired` vào `permits`, phương thức `render` hiện tại vẫn có thể biên dịch và chỉ rơi vào `IllegalStateException` khi gặp giá trị mới. Vì thế, cần rà lại các nơi xử lý biến thể mỗi lần thay đổi cây kiểu; nhánh dự phòng báo lỗi rõ ràng giúp phát hiện thiếu sót lúc chạy.

Một điều kiện `instanceof` cũng **không khớp với `null`**. Trong ví dụ, `Objects.requireNonNull(result, "result")` xác định rõ hợp đồng đầu vào, tránh để `null` đi đến nhánh xử lý không mong muốn.

## 6. Mối quan hệ với `switch` theo phiên bản Java

Với Java 17, cách triển khai ổn định để rẽ nhánh theo **kiểu biến thể** là `instanceof` pattern matching. `switch` truyền thống vẫn phù hợp với giá trị `enum`, chuỗi hoặc các kiểu được Java 17 hỗ trợ trong biểu thức `switch`, nhưng **không có cú pháp `switch` theo kiểu (`case LoggedIn s -> ...`) chính thức**.

Trên các phiên bản mới hơn:

- **Java 21** chính thức hỗ trợ pattern matching cho `switch`, cho phép `case LoggedIn success -> ...` và các nhánh theo kiểu khác.
- **Java 21** chính thức hỗ trợ record patterns, có thể so khớp và bóc thành phần của record trong pattern.
- Với `switch` pattern matching, trình biên dịch có thể sử dụng thông tin từ cây `sealed` để kiểm tra tính **exhaustive** của những nhánh hợp lệ. Cần xét riêng cách xử lý `null` khi API cho phép nhận `null`.

Ở Java 17, pattern matching cho `switch` mới là *preview*; cú pháp và hành vi của các bản preview đã tiến hóa qua những đời Java tiếp theo. Khi xây dựng ứng dụng Java 17 cần ổn định và dễ bảo trì, nên dùng các tính năng đã chính thức như ví dụ trên, thay vì đem nguyên ví dụ `switch` của Java 21 vào mã Java 17 hoặc phụ thuộc cú pháp preview cũ.

## 7. `sealed` + `record` khác gì `enum`?

Cả `enum` lẫn `sealed` đều hữu ích để diễn đạt tập trường hợp được kiểm soát, nhưng cách mô hình hóa dữ liệu khác nhau:

| Yêu cầu | `enum` | `sealed interface` + các `record` |
| --- | --- | --- |
| Các giá trị cố định như `NEW`, `RUNNING`, `DONE` | Rất phù hợp | Thường không cần thiết |
| Mỗi trường hợp có **kiểu dữ liệu đi kèm khác nhau** | Cần tự thiết kế thêm các trường/hành vi và quy tắc hợp lệ | Tự nhiên: mỗi record khai báo đúng các thành phần của nó |
| Tạo nhiều instance với dữ liệu khác nhau cho cùng một biến thể | Enum constant là các instance cố định | Có thể tạo `new LoggedIn(...)` hoặc `new WrongPassword(...)` nhiều lần |
| Dùng `switch` kiểm tra đầy đủ các enum constant trong Java 17 | Có thể, nhất là với `switch` expression | Rẽ nhánh theo kiểu sealed bằng `switch` chưa chính thức ở Java 17 |
| Kiểm soát nhánh kế thừa trực tiếp | Enum vốn không là cây kiểu mở tùy ý | Có `permits`, `final`, `sealed`, `non-sealed` |

Nếu chỉ cần ba trạng thái **không kèm payload khác nhau**, ví dụ `PENDING`, `APPROVED`, `REJECTED`, một `enum` thường đơn giản hơn. Nếu kết quả thành công phải mang `userId` còn lỗi phải mang `reason`, ba record trong một `sealed interface` biểu diễn cấu trúc từng trường hợp chính xác hơn.

## 8. Ví dụ mở rộng: cây biểu thức dạng đệ quy

Mô hình kết quả đăng nhập là ví dụ nghiệp vụ; ba tính năng này còn rất hữu ích khi mô hình hóa cú pháp, quy tắc hoặc cấu trúc phân cấp. Một cây biểu thức cộng có thể gồm **số nguyên** hoặc **phép cộng hai biểu thức**:

```java
public class ExpressionDemo {
    sealed interface Expr permits NumberExpr, AddExpr {}

    record NumberExpr(int value) implements Expr {}

    record AddExpr(Expr left, Expr right) implements Expr {}

    static int evaluate(Expr expression) {
        if (expression instanceof NumberExpr number) {
            return number.value();
        }
        if (expression instanceof AddExpr add) {
            return evaluate(add.left()) + evaluate(add.right());
        }
        throw new IllegalArgumentException("Biểu thức không được hỗ trợ");
    }

    public static void main(String[] args) {
        Expr expression = new AddExpr(new NumberExpr(10), new NumberExpr(32));
        System.out.println(evaluate(expression)); // 42
    }
}
```

Ở đây:

- `Expr` nói rõ những nút trực tiếp hợp lệ trong ngôn ngữ biểu thức nhỏ này.
- `NumberExpr` và `AddExpr` mang các thành phần dữ liệu khác nhau, nhưng đều được đối xử như `Expr`.
- `evaluate` chọn hành vi dựa trên kiểu thực tế; nhánh `AddExpr` tiếp tục xử lý đệ quy hai biểu thức con.

Vì `AddExpr` chứa `Expr`, một cây có thể lồng nhiều lớp mà không cần tạo thêm kiểu tùy ý ngoài danh sách cho phép. Nếu cấu trúc được tạo từ nguồn bên ngoài, vẫn cần kiểm tra đầu vào hợp lệ (chẳng hạn không chấp nhận `null` cho `left` hoặc `right`) và cân nhắc độ sâu đệ quy; `sealed` tự nó không đảm bảo các bất biến đó.

## 9. Các lỗi thiết kế và hiểu nhầm thường gặp

1. **Cho rằng `sealed` tự làm cho `if/else` exhaustive.** Java 17 không kiểm tra đủ các pattern `instanceof`; thêm biến thể mới cần cập nhật code xử lý.
2. **Cho rằng `record` bất biến sâu.** Các đối tượng mutable như list, map, array vẫn cần chiến lược sao chép và công bố dữ liệu phù hợp.
3. **Cho rằng `record` bắt buộc `extends` một `sealed class`.** Record không thể kế thừa class đó; muốn kết hợp thường dùng `sealed interface`.
4. **Dùng `non-sealed` trong một cây mong muốn hoàn toàn đóng.** `non-sealed` cho phép xuất hiện những kiểu con khác dưới nhánh ấy.
5. **Dùng `getX()` hoặc truy cập field của record như class DTO quen thuộc.** Accessor chuẩn của record có dạng `x()`, và field lưu trữ là `private`.
6. **Dùng cú pháp record pattern hoặc type-pattern `switch` từ Java 21 trong source Java 17.** Những tính năng đó chưa chính thức ở Java 17; phiên bản ngôn ngữ mà dự án biên dịch phải được xác định rõ.
7. **Dùng `sealed` cho API cố ý cho bên thứ ba tự tạo subtype.** Đây là hợp đồng extension mở; giới hạn `permits` có thể phá vỡ điểm mở rộng mong muốn.
8. **Thêm trường trạng thái không liên quan vào record để gộp mọi kết quả.** Nếu các trường chỉ hợp lệ trong những trường hợp riêng, nên tạo các biến thể có payload khác nhau.

## 10. Cách chọn và phối hợp trong thực tế

Khi thiết kế một API Java 17, có thể tự hỏi theo thứ tự:

1. **Có tập trường hợp hữu hạn mà nhóm phát triển kiểm soát không?** Nếu có, cân nhắc `sealed interface` cho kiểu gốc. Nếu cần người dùng API tự mở rộng subtype, giao diện thường có thể phù hợp hơn.
2. **Mỗi trường hợp chủ yếu mang dữ liệu rõ ràng và ít thay đổi không?** Nếu có, dùng `record` làm biến thể lá. Nếu có trạng thái thay đổi và vòng đời phức tạp, cân nhắc `final class` hoặc một phân cấp class phù hợp.
3. **Mỗi biến thể có payload khác nhau hay chỉ là tên một trạng thái?** Với các nhãn đơn giản, `enum` có thể đủ. Với payload theo biến thể, `sealed` kết hợp record thường rõ ràng hơn.
4. **Cần xử lý từng biến thể trên Java 17 thế nào?** Dùng `instanceof` type pattern, khai thác accessor của record và có cơ chế báo lỗi khi gặp nhánh chưa xử lý; cập nhật các điểm này khi mở rộng `permits`.

**Ghi nhớ mối quan hệ:** `sealed` **đóng tập kiểu con trực tiếp**, `record` **mô tả dữ liệu của mỗi trường hợp**, còn pattern matching **nhận diện kiểu cụ thể khi xử lý**. Trên Java 17, bộ ba này cung cấp cách mô hình hóa dữ liệu đa biến thể rõ ràng và an toàn về kiểu, trong khi khả năng phân rã record bằng pattern và kiểm tra exhaustive bằng type-pattern `switch` thuộc các bản Java mới hơn.
