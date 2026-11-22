# Pattern matching giải quyết vấn đề gì trong Java?

## 1. Vấn đề xuất phát từ đâu?

Trong Java, biến có **kiểu khai báo tại thời điểm biên dịch**, nhưng đối tượng mà biến tham chiếu có thể thuộc một kiểu cụ thể hơn khi chương trình chạy. Ví dụ, một tham số kiểu `Object` có thể nhận `String`, `Integer`, hoặc một đối tượng khác. Khi cần xử lý riêng từng kiểu, lập trình viên thường phải:

1. Kiểm tra đối tượng có thuộc kiểu cần xử lý hay không bằng `instanceof`.
2. Ép kiểu tường minh (cast) để truy cập thành viên của kiểu đó.
3. Tạo biến mới, rồi mới sử dụng dữ liệu.

Hai thao tác kiểm tra và ép kiểu thường nói về **cùng một đối tượng và cùng một kiểu**, nên cách viết cũ lặp lại thông tin. Với cấu trúc dữ liệu có nhiều biến thể, các nhánh điều kiện còn dễ dài, khó đọc và dễ nhầm biến. **Pattern matching** (khớp mẫu) cho phép diễn đạt đồng thời điều kiện nhận diện và việc lấy dữ liệu cần dùng, giúp trình biên dịch kiểm tra kiểu và phạm vi biến.

Ý tưởng ngắn gọn: thay vì hỏi `đối tượng này có phải String không?` rồi tự cast, ta viết `nếu đối tượng này là String, hãy gọi nó là s để dùng trong nhánh phù hợp`.

## 2. Trước và sau: ví dụ chạy được với Java 17

Tệp `PatternMatchingBasics.java`:

```java
public class PatternMatchingBasics {
    static String traditional(Object value) {
        if (value instanceof String) {
            String s = (String) value;
            return "Chuỗi dài " + s.length();
        }
        if (value instanceof Integer) {
            Integer n = (Integer) value;
            return "Số nhân đôi " + (n * 2);
        }
        return "Kiểu khác";
    }

    static String modern(Object value) {
        if (value instanceof String s) {
            return "Chuỗi dài " + s.length();
        }
        if (value instanceof Integer n) {
            return "Số nhân đôi " + (n * 2);
        }
        return "Kiểu khác";
    }

    public static void main(String[] args) {
        System.out.println(traditional("Java"));
        System.out.println(modern("Java"));
        System.out.println(modern(21));
        System.out.println(modern(null));
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac PatternMatchingBasics.java
java PatternMatchingBasics
```

Kết quả:

```text
Chuỗi dài 4
Chuỗi dài 4
Số nhân đôi 42
Kiểu khác
```

Trong `value instanceof String s`, **`String` là kiểu mẫu**, còn **`s` là biến mẫu (pattern variable)**. Nếu phép kiểm tra đúng, `s` đã có kiểu `String` nên có thể gọi `length()` trực tiếp. Nếu không khớp, nhánh đó không chạy. Hai hàm trả về cùng kết quả, nhưng bản `modern` bỏ được các cast và khai báo trùng lặp.

Cần phân biệt: `instanceof String s` không biến một đối tượng bất kỳ thành `String` và không đổi kiểu thật của `value`. Nó chỉ đặt tên một tham chiếu có kiểu thích hợp **khi điều kiện khớp**.

## 3. Pattern matching thực sự cải thiện điều gì?

| Vấn đề trong code truyền thống | Pattern matching hỗ trợ | Giới hạn cần nhớ |
| --- | --- | --- |
| Kiểm tra `instanceof` rồi lại cast cùng một kiểu | Gộp kiểm tra kiểu và khai báo biến vào một biểu thức | Không biến một đối tượng sai kiểu thành đúng kiểu |
| Nhiều biến tạm, nhiều đoạn cast lặp | Giảm mã khuôn mẫu, làm nhánh xử lý rõ hơn | Không tự loại bỏ mọi `if` hay `switch` |
| Dùng biến sau kiểm tra dễ bị sai phạm vi | Trình biên dịch phân tích nơi mẫu chắc chắn đã khớp | Biến mẫu không khả dụng trên mọi nhánh |
| Xử lý nhiều loại đối tượng qua `if/else if` dài | `switch` với type patterns (Java 21) biểu đạt các trường hợp trực tiếp | Phải xét thứ tự case, tính bao phủ và `null` |
| Lấy các trường của record cần gọi accessor thủ công | Record patterns (Java 21) lấy thành phần ngay trong mẫu | Chỉ áp dụng cho record tương ứng; không giải cấu trúc tùy ý mọi lớp |

Lợi ích chính là **mã ngắn hơn ở chỗ có lặp**, **ý định rõ hơn** và **kiểm tra tĩnh tốt hơn**. Đây là cải tiến về khả năng diễn đạt và tính an toàn kiểu; không có cam kết rằng chương trình sẽ chạy nhanh hơn trong mọi trường hợp.

## 4. Biến mẫu chỉ tồn tại ở nơi chắc chắn khớp

Java dùng phân tích luồng điều khiển để xác định một biến mẫu có được gán chắc chắn hay chưa (thường gọi là *flow scoping*). Ví dụ sau là một phương thức hợp lệ trong Java 17:

```java
static void printNonBlank(Object value) {
    if (value instanceof String s && !s.isBlank()) {
        System.out.println(s.trim());
    }
}
```

Phía phải của `&&` chỉ được đánh giá khi `value instanceof String s` đúng, nên `s` sử dụng hợp lệ ở đó và trong thân `if`. Ngược lại, không thể tùy tiện dùng `s` ở vế phải của `||`: vế đó có thể chạy khi mẫu **không khớp**. Tương tự, sau một `if` thông thường có thể rẽ cả hai nhánh, không được giả định `s` vẫn tồn tại.

Một trường hợp khác cũng hợp lệ là **kiểm tra thất bại rồi thoát sớm**:

```java
static int lengthOfString(Object value) {
    if (!(value instanceof String s)) {
        return 0;
    }
    return s.length();
}
```

Sau `if`, mọi đường đi còn tiếp tục đều đã khớp `String s`, nên `s` có thể dùng. Điều này an toàn hơn việc tự cast mà không kiểm tra. Dẫu vậy, pattern matching không thay thế việc hiểu luồng điều khiển: nếu thay `return` bằng thao tác không kết thúc nhánh, không được mặc định biến đã được gán.

### Trường hợp null

Với type pattern của `instanceof`, `null instanceof String s` là `false`. Vì vậy `modern(null)` trong ví dụ đầu trả về `"Kiểu khác"` và không gây `NullPointerException`. Tuy nhiên, không nên suy rộng rằng mọi phép `switch` pattern matching cũng tự xử lý `null`; đó là quy tắc khác, xem phần tiếp theo.

## 5. Từ nhiều if đến switch theo mẫu trong Java 21

Khi một biểu thức cần xét nhiều trường hợp, Java 21 cho phép **type patterns trong `switch`** và có cú pháp `when` để thêm điều kiện bảo vệ (*guard*). Với record, **record patterns** còn giúp tách các thành phần dữ liệu khi khớp. Cả pattern matching for switch (JEP 441) và record patterns (JEP 440) là tính năng chính thức từ **Java 21**.

Ví dụ độc lập, tệp `PatternSwitchDemo.java` (yêu cầu JDK 21 trở lên):

```java
public class PatternSwitchDemo {
    record Point(int x, int y) {}

    static String describe(Object value) {
        return switch (value) {
            case null -> "Giá trị null";
            case Point(int x, int y) when x == 0 && y == 0 -> "Gốc tọa độ";
            case Point(int x, int y) -> "Điểm (" + x + ", " + y + ")";
            case String s when s.isBlank() -> "Chuỗi trắng";
            case String s -> "Chuỗi: " + s;
            case Integer n -> "Số: " + n;
            default -> "Kiểu khác";
        };
    }

    public static void main(String[] args) {
        System.out.println(describe(new Point(0, 0)));
        System.out.println(describe(new Point(2, 3)));
        System.out.println(describe(" "));
        System.out.println(describe(7));
        System.out.println(describe(null));
    }
}
```

Lệnh chạy:

```bash
javac PatternSwitchDemo.java
java PatternSwitchDemo
```

Kết quả:

```text
Gốc tọa độ
Điểm (2, 3)
Chuỗi trắng
Số: 7
Giá trị null
```

Ở đây:

- `case Point(int x, int y)` khớp một `Point` và trích xuất các thành phần `x`, `y`. Không phải gọi `point.x()` rồi `point.y()` riêng.
- `when x == 0 && y == 0` chỉ nhận trường hợp `Point` tại gốc tọa độ. Khi guard sai, `switch` tiếp tục xét case `Point` kế tiếp.
- `case String s when s.isBlank()` phải đứng trước `case String s`, vì case `String` không điều kiện sẽ bao phủ mọi chuỗi không-null.
- `case null` xử lý đầu vào null một cách có chủ đích. Với pattern `switch` trên tham chiếu, nếu không có nhánh nhận null thì đầu vào null thường gây `NullPointerException`, kể cả khi có `default`.
- `default` là phương án cho các kiểu còn lại của tham số `Object`.

**Ranh giới phiên bản:** `instanceof` type patterns là tính năng chính thức từ Java 16, nên dùng được với Java 17. Pattern `switch` và record patterns là tính năng chính thức từ Java 21. Không chép ví dụ `switch` ở trên vào dự án Java 17 rồi mong biên dịch bằng lệnh thông thường; các bản Java 17–20 từng có những phiên bản *preview* với quy tắc/cú pháp thay đổi. Ví dụ ở trên dùng cú pháp ổn định của Java 21.

## 6. Kết hợp với sealed types: kiểm tra đủ các trường hợp

Khi mô hình dữ liệu có **tập biến thể đóng** bằng `sealed interface` hoặc `sealed class`, trình biên dịch có thể kiểm tra `switch expression` đã xử lý đủ mọi kiểu con được phép. Đây là lợi ích khác với chuỗi `if/else`: bỏ sót một biến thể có thể bị phát hiện ngay lúc biên dịch.

Ví dụ độc lập, tệp `SealedSwitchDemo.java` (JDK 21+):

```java
public class SealedSwitchDemo {
    sealed interface Outcome permits Success, Failure {}
    record Success(String value) implements Outcome {}
    record Failure(String reason) implements Outcome {}

    static String describe(Outcome outcome) {
        return switch (outcome) {
            case Success(String value) -> "OK: " + value;
            case Failure(String reason) -> "Lỗi: " + reason;
        };
    }

    public static void main(String[] args) {
        System.out.println(describe(new Success("đã lưu")));
        System.out.println(describe(new Failure("timeout")));
    }
}
```

```bash
javac SealedSwitchDemo.java
java SealedSwitchDemo
```

```text
OK: đã lưu
Lỗi: timeout
```

Không cần `default` ở đây vì `Outcome` chỉ cho phép hai kiểu triển khai `Success` và `Failure`, và cả hai đều được xử lý. Nếu sau này bổ sung một kiểu con được phép, bộ biên dịch có thể yêu cầu cập nhật `switch` tương ứng. Đây là lợi ích bảo trì rất thiết thực đối với mô hình trạng thái, kết quả xử lý hoặc sự kiện có số biến thể rõ ràng.

Tuy nhiên, **bao phủ mọi kiểu không đồng nghĩa bao phủ null**: gọi `describe(null)` trong ví dụ này vẫn có thể ném `NullPointerException`. Cũng cần chú ý một case có `when` chỉ bao phủ những giá trị thỏa guard; chỉ các nhánh có guard thường không đủ để chứng minh tính đầy đủ.

## 7. Khi nào pattern matching là lựa chọn hợp lý?

Một số tình huống gần thực tế:

- **Xử lý đầu vào đa kiểu ở ranh giới hệ thống:** mã nhận `Object` từ một API chung, công cụ, bộ xử lý sự kiện, hoặc adapter và phải phân nhánh theo kiểu thực tế. Dùng `instanceof T t` giúp tránh cast lặp.
- **Kết quả có nhiều biến thể:** với `sealed` và `record`, một `switch` có thể mô tả rõ từng trường hợp thành công/thất bại và được kiểm tra tính đầy đủ.
- **Cấu trúc dữ liệu bất biến dạng record:** record patterns giúp lấy thành phần (kể cả mẫu lồng nhau khi kiểu phù hợp), hữu ích khi xử lý DTO, kết quả phân tích cú pháp, hình học hoặc dữ liệu phân loại.
- **Lọc một trường hợp trước khi dùng giá trị:** type pattern cùng `&&` diễn đạt vừa điều kiện kiểu vừa điều kiện nội dung, trong khi biến chỉ tồn tại ở nhánh an toàn.

Ví dụ, khi xử lý `Object value`, `value instanceof String text && !text.isBlank()` rõ ràng hơn chuỗi kiểm tra kiểu, cast rồi kiểm tra chuỗi. Nhưng nếu tất cả đầu vào vốn đã có một kiểu chung với phương thức đa hình thích hợp, việc gọi phương thức đó thường đơn giản hơn một `switch` lớn phân biệt từng lớp con.

## 8. Điều pattern matching không giải quyết

1. **Không thay thế thiết kế hướng đối tượng.** Nếu chính bạn sở hữu các lớp và mỗi loại tự biết cách thực hiện một hành vi, đa hình (interface/override) thường tránh được việc phải kiểm tra kiểu ở khắp nơi. Pattern matching rất hữu ích ở điểm phải *phân loại dữ liệu*, nhưng không phải lý do để mọi luồng nghiệp vụ trở thành một `switch` khổng lồ.
2. **Không kiểm tra kiểu phần tử của generic đã bị xóa kiểu.** Không thể dùng type pattern `instanceof java.util.List<String> strings` để xác nhận mọi phần tử là `String`. Do *type erasure*, có thể kiểm tra `instanceof java.util.List<?> list`, sau đó kiểm tra phần tử khi cần.
3. **Không phải regex hoặc so khớp văn bản.** Pattern ở đây diễn đạt kiểu/cấu trúc dữ liệu trong ngôn ngữ Java, không tìm chuỗi con theo biểu thức chính quy.
4. **Không tự xác minh điều kiện nghiệp vụ.** `case Point(int x, int y)` chỉ trích xuất thành phần của record; nếu cần xác thực giới hạn tọa độ, phải đặt điều kiện/validation phù hợp.
5. **Không bảo đảm hiệu năng cao hơn.** Lợi ích trực tiếp là độ rõ ràng và khả năng kiểm tra tĩnh; việc tối ưu phụ thuộc trình biên dịch, runtime và bài toán cụ thể.

## 9. Lỗi thường gặp và cách tránh

| Dễ mắc lỗi | Vì sao / cách xử lý |
| --- | --- |
| Dùng biến mẫu ở nhánh có thể chưa khớp, chẳng hạn vế phải `||` | Dùng `&&` khi muốn kiểm tra thêm điều kiện sau khi khớp; hoặc tách logic theo luồng điều khiển rõ ràng |
| Tưởng `instanceof` với null sẽ khớp một kiểu tham chiếu | `null` không khớp type pattern; xử lý null riêng nếu cần |
| Đặt `case CharSequence cs` trước `case String s` trong switch Java 21 | Case đầu đã bao phủ mọi String, khiến case sau bị che khuất (*dominated*) và không hợp lệ; đặt trường hợp cụ thể trước |
| Chỉ viết các nhánh có `when` trong switch expression mà quên trường hợp khác | Guard làm một case chỉ nhận tập con; thêm case tổng quát hoặc `default` khi cần tính đầy đủ |
| Dùng cú pháp `when`/record patterns của Java 21 trong dự án build Java 17 | Kiểm tra phiên bản JDK, `--release` và ngôn ngữ nguồn; dùng `instanceof` type patterns khi cần tương thích Java 17 |
| Tưởng pattern `List<?>` xác nhận kiểu mọi phần tử | Kiểm tra và xử lý từng phần tử nếu có yêu cầu về kiểu generic |
| Dùng pattern matching ở mọi nơi thay cho phương thức đa hình | Giữ hành vi trong kiểu đối tượng khi thiết kế miền cho phép; dùng pattern khi mục tiêu thật sự là phân loại/giải cấu trúc dữ liệu |

## 10. Cách tự quyết định có nên dùng

Khi gặp một đoạn Java dài vì phải kiểm tra kiểu, hãy tự hỏi:

1. Có đang viết lặp `instanceof` và cast cùng một đối tượng không? Nếu có, `instanceof T variable` thường là cải tiến trực tiếp, tương thích Java 17.
2. Có nhiều biến thể dữ liệu và dự án dùng Java 21+ không? Cân nhắc pattern `switch`, nhất là khi đầu vào là `sealed` hoặc `record`.
3. Có cần lấy các thành phần của record không? Record patterns giúp trích xuất rõ ràng trong chính nơi kiểm tra.
4. Có cần xử lý null, thứ tự case, guard và các biến thể mới không? Thiết kế đủ các nhánh trước khi thay `if/else` bằng `switch`.
5. Có thể giải quyết bằng đa hình đơn giản hơn không? Nếu có, ưu tiên thiết kế miền rõ ràng.

**Kết luận:** Pattern matching giải quyết phần mã lặp và dễ sai giữa **nhận diện một giá trị** với **sử dụng giá trị đó dưới kiểu/cấu trúc đã biết**. Bắt đầu từ `instanceof` type patterns trong Java 17, rồi tiến đến `switch` và record patterns trong Java 21 khi bài toán có nhiều biến thể hoặc dữ liệu dạng record. Giá trị cốt lõi là code dễ đọc, ít cast, biến có phạm vi an toàn và nhiều lỗi thiếu trường hợp được phát hiện ngay lúc biên dịch.