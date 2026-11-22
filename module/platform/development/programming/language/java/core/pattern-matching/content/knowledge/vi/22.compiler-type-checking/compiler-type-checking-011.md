# Dùng compiler như công cụ thiết kế trong Java Pattern Matching

**Compiler không chỉ kiểm tra cú pháp để tạo ra bytecode.** Trong Java, đặc biệt khi dùng **sealed types**, **records** và **pattern matching**, các lỗi biên dịch còn là tín hiệu để điều chỉnh **mô hình dữ liệu, số trường hợp nghiệp vụ, ranh giới kiểu và luồng xử lý**. Thay vì chỉ hỏi “đoạn code này chạy được chưa?”, ta có thể thiết kế để compiler buộc mình trả lời: “Đã xử lý hết các kiểu được phép chưa?”, “Nhánh nào che nhánh nào?”, “Biến này có chắc đã được ràng buộc?”, “Kết quả trả về có đúng kiểu không?”.

Bài học thuộc **Java Core Pattern Matching → Compiler và type checking**, tập trung vào cách tận dụng compiler như một **vòng phản hồi thiết kế** (compiler-guided design), cùng ví dụ có thể chạy trên **Java 21 trở lên**. Các tính năng được sử dụng đều đã hoàn thiện: sealed classes (Java 17, JEP 409), record patterns (Java 21, JEP 440), và pattern matching for `switch` (Java 21, JEP 441).

## 1. “Dùng compiler như công cụ thiết kế” nghĩa là gì?

Một hướng thiết kế tốt biến các giả định quan trọng của bài toán thành **quy tắc kiểu mà compiler có thể kiểm tra**, thay vì chỉ ghi trong comment. Ví dụ:

- Nếu một yêu cầu chỉ có ba dạng được chấp nhận, mô hình hóa bằng **`sealed interface`** và ba kiểu con được phép.
- Nếu mỗi dạng có những dữ liệu cố định, mô hình hóa bằng **`record`** với kiểu component cụ thể.
- Nếu mọi dạng đều phải được xử lý, dùng **`switch expression` exhaustive**, ưu tiên **không thêm `default` vô điều kiện** khi kiểu là một sealed hierarchy đã được bao phủ.
- Nếu một nhánh chỉ hợp lệ khi giá trị có kiểu nào đó, dùng **type pattern** hoặc **record pattern** để compiler theo dõi kiểu và phạm vi biến.
- Nếu các điều kiện cùng kiểu phải được xử lý khác nhau, dùng **`when` guard**, sắp thứ tự nhánh rõ ràng và để compiler kiểm tra dominance.

Nhờ vậy, khi mở rộng mô hình hay sửa cách xử lý, lỗi biên dịch có thể xuất hiện **ngay tại những đoạn code cần xem lại**.

**Giới hạn phải hiểu rõ:** compiler kiểm tra những thuộc tính suy ra được từ **mã nguồn và hệ thống kiểu**. Nó không tự chứng minh tên khách hàng không rỗng, số tuổi hợp pháp, quyền truy cập hợp lệ, dữ liệu JSON tuân theo hợp đồng API, hoặc toàn bộ logic nghiệp vụ là đúng.

## 2. Bắt đầu từ mô hình: `sealed interface` + `record`

Giả sử hệ thống chỉ nhận ba dạng yêu cầu:

```java
// Trích đoạn Java 21+, có thể khai báo cùng phạm vi phù hợp.
sealed interface Request permits Create, Delete, Ping {}

record Profile(String name, int age) {}

record Create(Profile profile, String source) implements Request {}

record Delete(String userId) implements Request {}

record Ping() implements Request {}
```

Cách thiết kế này nói với compiler:

1. `Request` là một **sealed interface**: các lớp triển khai trực tiếp phải nằm trong tập được cho phép theo quy tắc `permits`.
2. `Create`, `Delete`, `Ping` là các kiểu dữ liệu khác nhau, thay vì nhét mọi dữ liệu vào một đối tượng chung có trường `type` là chuỗi và nhiều trường tùy chọn.
3. Mỗi record có danh sách component rõ ràng: compiler biết `Create.profile()` trả về `Profile`, còn `Delete.userId()` trả về `String`.
4. Khi xử lý một biến có kiểu tĩnh `Request`, compiler có thông tin về tập biến thể được phép và có thể kiểm tra độ bao phủ của `switch`.

Vì sao điều này quan trọng hơn một chuỗi `"CREATE"`/`"DELETE"`/`"PING"`? Chuỗi là tập giá trị mở tại thời điểm biên dịch; compiler không biết mọi giá trị text có thể xuất hiện. Một kiểu `sealed` tạo ra **hợp đồng các biến thể** rõ ràng hơn.

Không phải bài toán nào cũng cần sealed hierarchy. Với tập hằng đơn giản không mang dữ liệu riêng, `enum` có thể phù hợp hơn. Sealed + record hữu ích khi mỗi biến thể có **cấu trúc dữ liệu khác nhau** và cần phân nhánh theo kiểu.

## 3. Để compiler phát hiện nhánh `switch` còn thiếu

Xem một `switch expression` chưa đầy đủ:

```java
// CỐ Ý SAI: trích đoạn bên trong phương thức trả về String.
// Biến 'request' có kiểu Request theo các khai báo ở trên.
return switch (request) {
    case Create(var profile, var source) -> "create";
    case Delete(var userId) -> "delete";
    case null -> "missing";
};
```

Compiler từ chối vì biểu thức không bao phủ trường hợp `Ping`. `switch expression` phải **exhaustive**: mọi giá trị đầu vào có thể xảy ra phải có nhánh sinh kết quả hoặc kết thúc bất thường một cách hợp lệ.

Sửa bằng cách thêm:

```java
// Đoạn minh họa đúng (thay toàn bộ switch thiếu nhánh ở trên).
return switch (request) {
    case Create(var profile, var source) -> "create";
    case Delete(var userId) -> "delete";
    case Ping() -> "ping";
    case null -> "missing";
};
```

Ở đây **không cần `default`** vì đã bao phủ mọi biến thể hợp lệ của `Request`. `case null` xử lý riêng selector `null`; các record patterns không khớp đối tượng `null`.

### Sửa mô hình, compiler nhắc sửa nơi sử dụng

Sau này nghiệp vụ xuất hiện dạng yêu cầu `Suspend`. Nếu cập nhật khai báo `Request` để thêm `Suspend` vào tập `permits` và định nghĩa record tương ứng, một `switch expression` không có `default` mà chưa xử lý `Suspend` sẽ **không còn exhaustive khi biên dịch lại**. Đây là một phản hồi thiết kế rất hữu ích:

- Chỗ định nghĩa kiểu ghi nhận biến thể mới.
- Các nơi xử lý bắt buộc phải bao phủ biến thể mới được compiler chỉ ra.
- Người sửa code phải quyết định `Suspend` có hành vi gì tại mỗi điểm xử lý, thay vì mặc định rơi vào nhánh “other”.

Ngược lại, nếu đặt `default -> "other";` từ đầu, khi thêm biến thể mới compiler có thể **không cảnh báo** rằng logic dành cho kiểu mới chưa được thiết kế. Vì vậy, **ưu tiên exhaustive switch không `default` đối với sealed hierarchy khi phù hợp**; vẫn sử dụng `default` khi thật sự muốn một chính sách fallback cho tập kiểu mở.

Không được coi lời hứa “sealed luôn có ba loại” là vĩnh viễn: khi mã nguồn thay đổi và được biên dịch lại, **tập permitted subtypes đã thay đổi**; các nhánh xử lý cần được xem xét lại.

## 4. Compiler kiểm tra độ bao phủ nhưng không thay validation nghiệp vụ

Một `record` diễn tả hình dạng dữ liệu, **không mặc nhiên áp dụng quy tắc hợp lệ**. Chẳng hạn:

```java
new Profile(null, -10)
new Delete("   ")
new Create(null, "app")
```

Các đối tượng trên vẫn có thể được tạo nếu record không tự áp đặt ràng buộc ở constructor. Compiler biết kiểu của từng component, nhưng không thể suy ra “tên phải có ký tự” hay “tuổi phải đạt ngưỡng”.

Do đó có thể kết hợp **record pattern lồng nhau** với **`when` guard**:

```java
// Trích đoạn bên trong switch (request).
case Create(Profile(var name, var age), var source)
        when name != null && !name.isBlank() && age >= 18 ->
        "Create: " + name + " via " + source;

case Create(var profile, var source) ->
        "Invalid create";
```

Hai nhánh có vai trò khác nhau:

- Nhánh đầu khớp `Create` có `profile` là một `Profile` khác `null`, đồng thời kiểm tra `name` không rỗng/trắng và `age >= 18`.
- Nhánh thứ hai bao phủ những `Create` còn lại: `profile` bằng `null`, tên không hợp lệ, tuổi chưa đủ hoặc bất kỳ trường hợp nào không qua guard.
- Nếu `profile == null`, nhánh `Create(Profile(...), ...)` **không khớp**, nhưng `Create(var profile, ...)` vẫn có thể khớp; `var profile` có thể nhận `null`.
- Điều kiện `name != null && !name.isBlank()` dùng short-circuit để không gọi `isBlank()` trên `null`.

**Compiler bảo đảm** các tên `name`, `age`, `source` được ràng buộc đúng kiểu tại nhánh đã khớp, và có thể kiểm tra thứ tự pattern có hợp lệ. **Compiler không bảo đảm** một profile có dữ liệu nghiệp vụ hợp lệ nếu bạn bỏ các guard.

Trong hệ thống thật, còn có thể đặt invariant trong **compact canonical constructor** của record để đối tượng không hợp lệ bị từ chối ngay khi tạo. Nếu chọn cách đó, hãy cân nhắc hợp đồng khi deserialize dữ liệu và cách thông báo lỗi cho bên gọi. Compiler vẫn không tự nghĩ ra các invariant; người thiết kế phải khai báo chúng.

## 5. Compiler bắt lỗi dominance và nhánh không thể đạt tới

Giả sử selector có kiểu `Object`. Đoạn sau **không biên dịch**:

```java
// CỐ Ý SAI: nhánh String bị pattern kiểu cha che.
String label = switch (input) {
    case CharSequence seq -> "text-like";
    case String text -> "string";
    case null -> "missing";
    default -> "other";
};
```

`String` implements `CharSequence`. Vì thế, mọi giá trị khớp `String text` đã bị `case CharSequence seq` trước đó nhận, khiến nhánh `String` không thể được chọn. Compiler phát hiện **dominated case label**.

Sắp xếp đúng là **nhánh hẹp trước nhánh rộng**:

```java
// Trích đoạn hợp lệ với Object input.
String label = switch (input) {
    case String text -> "string";
    case CharSequence seq -> "text-like";
    case null -> "missing";
    default -> "other";
};
```

Tương tự, với hai nhánh cùng kiểu:

```java
// CỐ Ý SAI: String không có guard đứng trước guard.
String label = switch (input) {
    case String text -> "text";
    case String text when text.isBlank() -> "blank";
    case null -> "missing";
    default -> "other";
};
```

Cần đặt nhánh `when text.isBlank()` trước nhánh `String` tổng quát. **Lỗi dominance là một tín hiệu thiết kế**: bạn đã xếp các điều kiện sai thứ tự hoặc một nhánh đã trở nên vô nghĩa.

Compiler không thể xác định mọi quan hệ toán học giữa các guard tùy ý. Ví dụ, việc hai điều kiện nghiệp vụ khác nhau có giao nhau không vẫn cần thiết kế và kiểm thử. Vì vậy, không suy ra “biên dịch thành công” nghĩa là các guard đã phân loại đúng mọi dữ liệu.

## 6. Flow scoping: compiler giúp thiết kế luồng điều khiển

Pattern variables chỉ được sử dụng tại nơi compiler chứng minh pattern đã khớp. Ví dụ:

```java
// Trích đoạn bên trong phương thức trả về int.
if (!(input instanceof String text)) {
    return -1;
}
return text.length();
```

Ở đây, nếu `input` không phải `String`, phương thức kết thúc ngay. Bất kỳ luồng nào tới `return text.length()` đều phải qua nhánh khớp, nên biến `text` được xem là **definitely matched** ở vị trí đó.

Ngược lại, đoạn sau **không biên dịch**:

```java
// CỐ Ý SAI: nhánh không khớp vẫn có thể đi tiếp.
if (!(input instanceof String text)) {
    System.out.println("Not text");
}
return text.length(); // 'text' không chắc đã được ràng buộc.
```

Compiler không thể bảo đảm `text` tồn tại ở đường chạy không khớp. Đây là lý do **guard clause + return sớm** vừa làm code ít lồng nhau, vừa biểu đạt rành mạch tiền điều kiện của phần xử lý chính.

Với điều kiện kết hợp:

```java
// Hợp lệ: vế phải của && chỉ chạy khi pattern đã khớp.
if (input instanceof String text && !text.isBlank()) {
    System.out.println(text.trim());
}
```

`text` có thể được sử dụng trong vế phải của `&&`. Nhưng thay bằng `input instanceof String text || text.isBlank()` là sai, vì vế phải của `||` chạy đúng khi pattern **không khớp**. Compiler giúp chặn truy cập một biến chưa được ràng buộc trong đường đi đó.

Hãy coi thông báo về scope là câu hỏi thiết kế: *“Đường đi nào khiến dữ liệu chưa được kiểm chứng nhưng vẫn bị sử dụng?”* Đôi khi câu trả lời đúng không phải thêm ép kiểu mà là **tổ chức lại control flow**.

## 7. Compiler bảo vệ kiểu kết quả của `switch expression`

Pattern matching trong `switch` có thể xuất hiện trong một biểu thức mà kết quả phải tương thích kiểu đích:

```java
// Trích đoạn hợp lệ với Request request.
int priority = switch (request) {
    case Create(var profile, var source) -> 3;
    case Delete(var userId) -> 2;
    case Ping() -> 0;
    case null -> -1;
};
```

Tất cả nhánh sinh giá trị kiểu `int`; compiler kiểm tra toàn bộ biểu thức có thể tạo được `int`. Nếu thay `case Ping() -> 0;` bằng `case Ping() -> "none";`, biểu thức trên không còn tương thích với kiểu `int` và sẽ bị từ chối.

Với nhánh nhiều lệnh, dùng `yield` để sinh giá trị:

```java
// Trích đoạn hợp lệ, phần của switch expression trả int.
case Create(var profile, var source) -> {
    int base = 3;
    int score = source == null ? base : base + 1;
    yield score;
}
```

Đây là **một nhánh mẫu**, phải đặt trong `switch expression` phù hợp. `yield` cung cấp giá trị cho biểu thức; `return` (nếu ở phương thức) là kết thúc phương thức. Hai lệnh không thể tùy tiện thay thế nhau.

Compiler sẽ kiểm tra nhánh block tạo giá trị hoặc kết thúc bất thường đúng cách. Nó không chứng minh thang điểm `3`/`4` đúng với sản phẩm; thang điểm là lựa chọn nghiệp vụ phải được kiểm thử.

## 8. Lưu ý về generic types, `null` và kiểu runtime

Compiler có thể ngăn một số phép kiểm tra generic **không an toàn**, nhưng không thể phục hồi mọi thông tin kiểu đã bị xóa bởi **type erasure**.

```java
record Box<T>(T value) {}

// CỐ Ý SAI khi input có kiểu Object.
if (input instanceof Box<String>(var text)) {
    System.out.println(text);
}
```

Với `Object input`, kiểm tra trực tiếp `Box<String>` đòi hỏi một kiểm tra tham số generic không thực hiện được an toàn ở runtime. Một cách có thể biên dịch trên Java 21+ là kiểm tra bản thân record với wildcard và **giá trị component**:

```java
// Trích đoạn hợp lệ với Object input.
if (input instanceof Box<?>(String text)) {
    System.out.println(text.toUpperCase());
}
```

Mẫu này nói rằng `input` là một `Box` có **component hiện đang chứa `String` khác `null`**, không chứng minh tham số kiểu gốc của đối tượng chính xác là `Box<String>`. Trường hợp `Box<CharSequence>` chứa chuỗi `String` vẫn có thể khớp.

Bài học thiết kế: một lỗi kiểu có thể chỉ ra ranh giới API đang quá rộng (mọi thứ đi qua `Object`), buộc bạn cân nhắc dùng kiểu tĩnh chính xác hơn, sealed hierarchy, hoặc validate dữ liệu tại boundary. **Đừng dùng raw types, unchecked cast hoặc thêm `default` chỉ để dập lỗi** mà chưa hiểu nguyên nhân.

### Compiler và `null`

- Type pattern `case String s` và record pattern `case Create(...)` không khớp selector `null`.
- `switch` trên một reference selector có thể nhận `null` cần xử lý riêng nếu đó là trường hợp hợp lệ; `default` không tự thay thế chính sách `case null`.
- Record pattern có component `var field` vẫn có thể ràng buộc **component tham chiếu bằng `null`**.
- Java compiler nói chung không thực hiện kiểm tra nullness toàn diện cho mọi tham chiếu. Cần validation, kiểm thử hoặc các công cụ phân tích bổ sung khi điều kiện này quan trọng.

## 9. Ví dụ hoàn chỉnh: thiết kế để compiler hỗ trợ

Tạo tệp **`CompilerDrivenDesignDemo.java`**:

```java
public class CompilerDrivenDesignDemo {
    sealed interface Request permits Create, Delete, Ping {}

    record Profile(String name, int age) {}

    record Create(Profile profile, String source) implements Request {}

    record Delete(String userId) implements Request {}

    record Ping() implements Request {}

    static String handle(Request request) {
        return switch (request) {
            case Create(Profile(var name, var age), var source)
                    when name != null && !name.isBlank() && age >= 18 ->
                    "Create: " + name + " via " + source;

            case Create(var profile, var source) ->
                    "Invalid create";

            case Delete(var userId)
                    when userId != null && !userId.isBlank() ->
                    "Delete: " + userId;

            case Delete(var userId) ->
                    "Invalid delete";

            case Ping() -> "Pong";

            case null -> "Missing request";
        };
    }

    static String review(Object input) {
        if (!(input instanceof Create(var profile, var source))) {
            return "Not create";
        }
        if (profile == null) {
            return "Missing profile";
        }
        return "Review " + profile.name() + " via " + source;
    }

    public static void main(String[] args) {
        System.out.println(handle(
                new Create(new Profile("Lan", 22), "web")));
        System.out.println(handle(
                new Create(new Profile("Minh", 16), "app")));
        System.out.println(handle(
                new Create(null, "app")));
        System.out.println(handle(new Delete("user-7")));
        System.out.println(handle(new Delete("  ")));
        System.out.println(handle(new Ping()));
        System.out.println(handle(null));

        System.out.println(review(
                new Create(new Profile("Lan", 22), "web")));
        System.out.println(review(new Create(null, "web")));
        System.out.println(review(new Ping()));
    }
}
```

Biên dịch bằng JDK 21 trở lên, đặt đúng tên tệp tương ứng với `public class`:

```bash
javac --release 21 -encoding UTF-8 CompilerDrivenDesignDemo.java
java CompilerDrivenDesignDemo
```

Kết quả:

```text
Create: Lan via web
Invalid create
Invalid create
Delete: user-7
Invalid delete
Pong
Missing request
Review Lan via web
Missing profile
Not create
```

### Phân tích những bảo đảm được mã hóa trong chương trình

**1. Ba biến thể của `Request`**

`sealed interface Request` và các record thực thi tạo một tập kiểu được compiler biết. Trong `handle`, các nhánh `Create`, `Delete` và `Ping` tạo độ bao phủ đầy đủ cho mọi Request không null đã khai báo, nên không cần `default`.

**2. Nhánh `Create` được kiểm tra hai tầng**

`Create(Profile(var name, var age), var source)` là nested record pattern. Nó khớp khi `Create.profile()` có một `Profile` thực. Guard kiểm tra `name != null`, tên không trắng và `age >= 18`. Trường hợp `Create(null, "app")` không qua nested pattern, nhưng nhánh `Create(var profile, var source)` nhận được và trả `"Invalid create"`.

**3. Nhánh `Delete` có guard và fallback**

`Delete("user-7")` thỏa guard. `Delete("  ")` khớp record pattern nhưng không thỏa `!userId.isBlank()`, nên được xử lý ở nhánh `Delete` tiếp theo. Compiler kiểm tra nhánh rộng không đứng trước nhánh guard hẹp hơn.

**4. `Ping()` là record không có component**

Pattern `case Ping()` khớp kiểu record `Ping`, không cần destructure dữ liệu. Nếu nhánh này bị xóa, `switch expression` trên `Request` không còn bao phủ hết tập kiểu.

**5. `review` dùng flow scoping**

`!(input instanceof Create(var profile, var source))` kết hợp `return` khi không khớp. Từ đó, `profile` và `source` được dùng bên ngoài `if` trong đường chạy thành công. Vì `profile` vẫn có thể `null`, phương thức kiểm tra thêm trước khi gọi `profile.name()`.

**6. Hợp đồng kiểu không tự làm sạch đầu vào**

Chương trình cố ý không kiểm tra mọi quy tắc của `source` hoặc các trường dữ liệu ngoài phạm vi ví dụ. Đây là phần cần **validation và test** thêm khi đưa vào hệ thống thực tế, chứ không phải lời hứa compiler tự hoàn thiện nghiệp vụ.

## 10. Quy trình compiler-guided design từng bước

<escape>1.</escape> **Mô hình hóa miền nghiệp vụ.** Hỏi: những biến thể nào được cho phép? Dữ liệu của từng biến thể là gì? Dùng `enum`, `sealed interface/class`, `record` hoặc kiểu thông thường theo nhu cầu thực tế.

<escape>2.</escape> **Viết xử lý có coverage rõ ràng.** Với sealed hierarchy, viết `switch expression` khớp từng biến thể và thử **không dùng `default`**. Để compiler chỉ ra thiếu nhánh thay vì viết một nhánh mặc định che lấp trường hợp mới.

<escape>3.</escape> **Biên dịch sớm.** Dùng `javac` hoặc IDE. Đọc lỗi theo câu hỏi “mô hình đang thiếu thông tin gì?” trước khi sửa. Ví dụ: not exhaustive → còn một biến thể; dominated → thứ tự/ý nghĩa của case có vấn đề; variable not in scope → có đường chạy chưa chứng minh match.

<escape>4.</escape> **Sửa cấu trúc, không chỉ sửa thông báo.** Nếu thường xuyên phải cast từ `Object`, xem lại kiểu API hoặc ranh giới nhận dữ liệu. Nếu phải đặt hàng chục guard không liên quan, cân nhắc tách phương thức hoặc nâng ràng buộc vào kiểu/constructor phù hợp.

<escape>5.</escape> **Thử thay đổi mô hình.** Thêm một permitted subtype trong nhánh phát triển riêng, biên dịch lại và xem các `switch` exhaustive nào cần cập nhật. Nếu compiler không phát hiện, kiểm tra xem `default` đã che trường hợp mới hay chưa.

<escape>6.</escape> **Dùng cảnh báo để tăng tín hiệu.** Tùy dự án, có thể bật `-Xlint:all` để xem các loại warning của `javac` và cân nhắc `-Werror` để warning khiến build không thành công. Dùng `--release 21` khi cần bảo đảm mã nguồn/API tương thích với Java 21; không nên dựa vào cú pháp mới chỉ có ở JDK đang cài.

<escape>7.</escape> **Kết hợp kiểm thử.** Chạy unit tests cho nghiệp vụ, biên dữ liệu, `null`, guard, logic authorization, I/O, transaction. Compiler chứng minh **tính hợp lệ kiểu và control flow trong phạm vi của nó**, không chứng minh chương trình làm đúng điều người dùng mong muốn.

Ví dụ câu lệnh cho dự án dùng JDK 21+:

```bash
javac --release 21 -Xlint:all -encoding UTF-8 CompilerDrivenDesignDemo.java
java CompilerDrivenDesignDemo
```

Có thể thêm `-Werror` trong CI khi nhóm đã xử lý và chủ động quản lý các warning liên quan; không nên bật vô điều kiện trên một codebase đang có nhiều warning chưa được phân loại.

## 11. Bảng lỗi biên dịch như tín hiệu thiết kế

| Triệu chứng | Compiler đang cảnh báo điều gì? | Hướng xem xét |
| --- | --- | --- |
| `switch expression does not cover all possible input values` hoặc chẩn đoán tương đương | Chưa bao phủ mọi kiểu/case có thể xảy ra | Thêm nhánh đúng cho từng biến thể; xem lại sealed hierarchy |
| `case label is dominated` | Một case trước đã bao phủ case sau | Đặt nhánh hẹp hoặc guard cụ thể trước |
| `cannot find symbol` với pattern variable ở ngoài nhánh | Biến chưa nằm trong phạm vi được chứng minh match | Dùng flow scoping đúng hoặc tổ chức lại guard/return |
| `incompatible types` giữa kết quả nhánh và kiểu đích | Một nhánh sinh giá trị khác hợp đồng kiểu kết quả | Thống nhất kiểu kết quả, cân nhắc result type rõ nghĩa |
| Unchecked cast/conversion với generic | Compiler không thể chứng minh an toàn kiểu | Giữ thông tin generic trong API; wildcard + component pattern có kiểm tra cụ thể |
| Record pattern sai số lượng component | Số vị trí phân rã không đúng cấu trúc record | Viết đủ component pattern, đúng thứ tự |
| Thiếu cách xử lý `null` ở runtime dù đã biên dịch | Nullness không được bảo đảm chỉ bởi type system Java thông thường | Xác định chính sách `null`, validation, test |
| Code vẫn compile dù case mới đi vào `default` | Fallback đã che tác động của việc mở rộng mô hình | Chỉ giữ `default` khi fallback thật sự là chủ đích thiết kế |

Thông báo lỗi chính xác có thể thay đổi theo JDK, vị trí lỗi và cú pháp. Bảng trên mô tả **loại vấn đề**, không yêu cầu compiler xuất đúng từng từ.

## 12. Bài tập thực hành và hướng dẫn kiểm chứng

Cho mô hình:

```java
sealed interface Event permits Login, Logout {}
record Login(String username) implements Event {}
record Logout(String username) implements Event {}
```

**Bài 1 — Exhaustiveness.** Viết `String describe(Event event)` bằng `switch expression` trả `"login"` cho `Login`, `"logout"` cho `Logout` và `"missing"` cho `null`, **không có `default`**.

**Đáp án:**

```java
static String describe(Event event) {
    return switch (event) {
        case Login(var username) -> "login";
        case Logout(var username) -> "logout";
        case null -> "missing";
    };
}
```

**Bài 2 — Thêm biến thể.** Thêm `record Locked(String username) implements Event {}` vào tập permitted subtypes. Nếu không sửa `describe`, điều gì xảy ra khi biên dịch lại?

**Đáp án:** `switch expression` không còn exhaustive, nên compiler yêu cầu xử lý `Locked`. Nếu có `default` bao phủ mọi kiểu còn lại, lỗi có thể không xuất hiện. Đây là lý do tránh default khi muốn compiler nhắc sửa mọi điểm xử lý biến thể mới.

**Bài 3 — Dominance.** Tại sao đoạn sau sai?

```java
// CỐ Ý SAI với Object input.
String text = switch (input) {
    case Object obj -> "any";
    case String value -> "string";
};
```

**Đáp án:** Pattern `Object obj` bao phủ mọi giá trị không `null` thuộc kiểu `String`, nên `case String value` bị dominated. Ngoài ra, selector `null` cần được xem xét riêng: không mặc nhiên được xử lý bởi type pattern tổng quát. Hãy đổi thứ tự để nhánh `String` trước `Object` nếu đúng nhu cầu, và thêm `case null` khi muốn hỗ trợ null.

**Bài 4 — Flow scoping.** Viết guard clause cho `Object input`: nếu không phải `Login` thì trả `"Not login"`; nếu là `Login` thì trả `username` viết hoa, đồng thời xử lý `username == null` bằng `"No name"`.

**Đáp án:**

```java
static String loginLabel(Object input) {
    if (!(input instanceof Login(var username))) {
        return "Not login";
    }
    if (username == null) {
        return "No name";
    }
    return username.toUpperCase();
}
```

Compiler có thể chứng minh `username` đã được ràng buộc sau guard clause; việc kiểm tra `null` là trách nhiệm mã nghiệp vụ.

## 13. Ghi nhớ

- **Compiler-guided design** là chủ động mô hình hóa các giả định quan trọng bằng kiểu và control flow để compiler kiểm tra.
- **Sealed hierarchy** khai báo tập biến thể; **record** mô tả dữ liệu có cấu trúc; **pattern matching** giúp xử lý các biến thể theo kiểu và component.
- **Exhaustive `switch expression` không `default`** giúp compiler nhắc khi thiếu trường hợp hoặc khi sealed hierarchy mở rộng.
- **Dominance** giúp phát hiện nhánh bị che; **flow scoping** phát hiện nơi pattern variable chưa chắc được ràng buộc; **result typing** bảo vệ kiểu đầu ra.
- **Compiler không thay thế validation và test**: dữ liệu có thể `null`, sai nghiệp vụ, thiếu quyền hoặc không phù hợp contract bên ngoài dù chương trình biên dịch.
- Quy trình tốt là **thiết kế kiểu → viết pattern và xử lý → biên dịch → đọc lỗi như phản hồi thiết kế → sửa mô hình/luồng → kiểm thử**.

Tài liệu chính thức: [JEP 409 — Sealed Classes](https://openjdk.org/jeps/409), [JEP 440 — Record Patterns](https://openjdk.org/jeps/440), [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441), [JEP 394 — Pattern Matching for instanceof](https://openjdk.org/jeps/394), [Oracle — Pattern Matching for switch (Java 21)](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html).
