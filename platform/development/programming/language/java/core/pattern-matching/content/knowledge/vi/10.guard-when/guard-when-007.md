# Nhiều guard trên cùng một kiểu trong pattern switch (Java 21+)

## 1. Vấn đề: cùng một kiểu nhưng nhiều quy tắc xử lý

Trong Java 21, một `switch` có pattern có thể chứa **nhiều nhánh dùng cùng một type pattern** nhưng mỗi nhánh kèm một **guard `when` khác nhau**. Nhờ đó ta phân loại các giá trị cùng kiểu theo nội dung hoặc điều kiện nghiệp vụ, thay vì chỉ dựa vào class.

Ví dụ, cùng là `String` nhưng muốn phân biệt chuỗi rỗng/trắng, thông báo lỗi có tiền tố đặc biệt, chuỗi ngắn và văn bản thông thường:

```java
static String classify(Object input) {
    return switch (input) {
        case String s when s.isBlank() -> "blank";
        case String s when s.startsWith("ERR:") -> "error";
        case String s when s.length() < 5 -> "short";
        case String s -> "text";
        default -> "not a String";
    };
}
```

Các nhánh `case String s` ở đây **không bị coi là trùng lặp đơn giản**, vì các nhánh đầu có điều kiện `when` quyết định khi nào chúng được chọn. Nếu pattern khớp `String` nhưng guard trả về `false`, Java tiếp tục xét những nhánh thích hợp tiếp theo. Nhánh `case String s` **không có guard** ở cuối nhóm sẽ xử lý các chuỗi không thỏa bất kỳ guard nào trước đó.

Bài này tập trung vào kỹ thuật **“nhiều guard trên cùng một kiểu”**: cú pháp, trình tự khớp, phạm vi biến pattern, dominance, tính bao phủ, lỗi hay gặp và ví dụ chạy được.

**Phiên bản:** `when` guard trong pattern switch được chuẩn hóa ở **Java 21 (JEP 441)**. Dùng JDK 21+; không cần `--enable-preview`. Pattern matching cho `instanceof` đã có từ Java 16 nhưng **không** đồng nghĩa Java 17 hỗ trợ `case ... when ...` trong switch chuẩn.

## 2. Một guard kết hợp với type pattern như thế nào?

Cú pháp cơ bản:

```text
case Kiểu tênBiến when điềuKiệnBoolean -> kếtQuả;
```

Ví dụ:

```java
case String s when s.length() > 10 -> "long text";
```

Gồm ba bước về mặt ý nghĩa:

1. **Match kiểu:** selector value trước tiên phải khớp `String s`; với giá trị không phải `String`, guard không cần được đánh giá.
2. **Đánh giá guard:** nếu pattern khớp, biến `s` có kiểu tĩnh `String` và được dùng trong biểu thức sau `when`. Guard phải là điều kiện kiểu boolean hợp lệ.
3. **Chọn hoặc tiếp tục:** nếu guard đúng, chọn nhánh; nếu sai, nhánh này không được chọn và quá trình lựa chọn tiếp tục với những case label phía sau.

Ví dụ nhận `Object` nhưng nhiều nhánh cùng kiểu:

```java
static String classifyInteger(Object value) {
    return switch (value) {
        case Integer n when n < 0 -> "negative";
        case Integer n when n == 0 -> "zero";
        case Integer n -> "positive";
        default -> "not an Integer";
    };
}
```

Với `-5`, nhánh thứ nhất khớp; với `0`, guard thứ nhất sai và guard thứ hai đúng; với `7`, cả hai guard sai rồi nhánh `case Integer n` xử lý. Với `"7"`, không có pattern `Integer` nào khớp, nên dùng `default`. Số nguyên truyền vào tham số `Object` được autobox thành `Integer`.

**Lưu ý về selector:** biểu thức bên trong `switch (...)` được tính **một lần**. Các guard có thể được đánh giá lần lượt khi đến nhánh tương ứng, nhưng việc đi qua nhiều nhánh `case` không tự tính lại selector expression.

## 3. Tại sao nhiều nhánh `case String s` được phép cùng xuất hiện?

Mỗi `case String s when ...` là **một case label có pattern và guard riêng**. Các biến đều được đặt tên `s` trong ví dụ này nhưng không phải một biến được chia sẻ qua tất cả nhánh:

```java
static String examine(Object value) {
    return switch (value) {
        case String s when s.isBlank() ->
                "blank (length=" + s.length() + ")";
        case String s when s.startsWith("#") ->
                "tag=" + s.substring(1);
        case String s ->
                "plain=" + s;
        default ->
                "other";
    };
}
```

Compiler xác định kiểu tĩnh của `s` là `String` trong **từng** nhánh; phạm vi của biến pattern gắn với case label đó, guard của nó và phần thân nhánh được bảo đảm match. Việc dùng lại tên `s` ở các nhánh riêng là hợp lệ.

Ngược lại, không thể đọc `s` trong một `default` nằm ngoài phạm vi của các pattern trước đó:

```java
// Sai: default không được phép dùng biến s từ các case String ở trước.
// default -> "other=" + s;
```

Nếu muốn phân biệt vai trò từng nhánh, cũng có thể đặt tên riêng:

```java
case String blank when blank.isBlank() -> "blank";
case String code when code.startsWith("ERR:") -> "error";
case String text -> "text";
```

Tên biến khác nhau không làm thay đổi cơ chế match. Điều quan trọng là **kiểu pattern, guard và vị trí** của từng nhánh.

## 4. Thứ tự case quyết định ưu tiên khi điều kiện giao nhau

Đây là quy tắc thực tế quan trọng nhất: **nhánh thích hợp đầu tiên được chọn**. Một đối tượng có thể đồng thời thỏa nhiều guard cùng kiểu. Nếu nhiều nhánh cùng có thể match, **thứ tự xuất hiện** quyết định nhánh nào chạy.

Ví dụ chuỗi `"ERR:"` thỏa cả hai điều kiện:

- `s.startsWith("ERR:")` là `true`.
- `s.length() < 5` cũng là `true` vì độ dài bằng 4.

Với thứ tự:

```java
case String s when s.startsWith("ERR:") -> "error";
case String s when s.length() < 5 -> "short";
```

Chuỗi `"ERR:"` được phân loại là `"error"`.

Nếu đảo vị trí:

```java
case String s when s.length() < 5 -> "short";
case String s when s.startsWith("ERR:") -> "error";
```

Cùng chuỗi ấy lại được phân loại là `"short"`. Đây không phải lỗi biên dịch; cả hai guard đều hợp lệ. Nhưng đó có thể là **lỗi nghiệp vụ do thứ tự ưu tiên sai**.

Cách thiết kế dễ hiểu:

1. Đặt các quy tắc **cần ưu tiên cao nhất** trước, ví dụ dữ liệu lỗi, từ khóa đặc biệt, điều kiện an toàn.
2. Tiếp đến các quy tắc **cụ thể hơn** hoặc có ngưỡng riêng.
3. Đặt nhánh cùng kiểu **không có guard** sau các nhánh có guard để nhận phần còn lại.
4. Đặt `default` nếu selector có thể chứa kiểu khác và switch chưa được bao phủ đầy đủ.

Với các điều kiện không giao nhau, như `n < 0` và `n == 0`, thứ tự thường không thay đổi kết quả; tuy vậy vẫn nên giữ thứ tự nhất quán để đọc và bảo trì.

## 5. Chương trình Java 21 hoàn chỉnh: nhiều guard trên String, Integer và record

Lưu toàn bộ đoạn mã sau thành **MultipleGuardsDemo.java**:

```java
public class MultipleGuardsDemo {
    record Order(int amount, String owner) {}

    static String classify(Object value) {
        return switch (value) {
            case null -> "null";

            case String s when s.isBlank() -> "blank";
            case String s when s.startsWith("ERR:") ->
                    "error:" + s.substring(4);
            case String s when s.length() < 5 -> "short:" + s;
            case String s -> "text:" + s;

            case Integer n when n < 0 -> "negative:" + n;
            case Integer n when n == 0 -> "zero";
            case Integer n -> "positive:" + n;

            default -> "other";
        };
    }

    static String route(Object item) {
        return switch (item) {
            case Order(int amount, String owner) when amount < 0 ->
                    "invalid:" + owner;
            case Order(int amount, String owner) when amount >= 100 ->
                    "priority:" + owner;
            case Order(int amount, String owner) ->
                    "normal:" + owner;
            default -> "unsupported";
        };
    }

    public static void main(String[] args) {
        System.out.println(classify("   "));
        System.out.println(classify("ERR:"));
        System.out.println(classify("hi"));
        System.out.println(classify("hello"));
        System.out.println(classify(-3));
        System.out.println(classify(0));
        System.out.println(classify(8));
        System.out.println(classify(2.5));
        System.out.println(classify(null));

        System.out.println(route(new Order(-2, "An")));
        System.out.println(route(new Order(150, "Binh")));
        System.out.println(route(new Order(20, "Chi")));
    }
}
```

Biên dịch và chạy từ thư mục chứa tệp:

```bash
javac MultipleGuardsDemo.java
java MultipleGuardsDemo
```

Đầu ra chính xác:

```text
blank
error:
short:hi
text:hello
negative:-3
zero
positive:8
other
null
invalid:An
priority:Binh
normal:Chi
```

Giải thích từng trường hợp:

| Giá trị đầu vào | Nhánh được chọn | Lý do |
| --- | --- | --- |
| `"   "` | `String s when s.isBlank()` | Chuỗi toàn dấu cách; guard đầu đúng |
| `"ERR:"` | `String s when s.startsWith("ERR:")` | Có tiền tố lỗi; được ưu tiên trước điều kiện độ dài |
| `"hi"` | `String s when s.length() < 5` | Không blank, không có tiền tố lỗi, độ dài nhỏ hơn 5 |
| `"hello"` | `String s` | Không thỏa ba guard nhưng vẫn là chuỗi |
| `-3` | `Integer n when n < 0` | Số nguyên âm |
| `0` | `Integer n when n == 0` | Guard âm sai; guard bằng 0 đúng |
| `8` | `Integer n` | Không âm, không bằng 0, vẫn là Integer |
| `2.5` | `default` | `Double` không khớp các pattern `String`/`Integer` |
| `null` | `case null` | Xử lý giá trị null riêng |

Phương thức `route` dùng **record pattern** (Java 21) với cùng record `Order`:

- `Order(-2, "An")`: amount âm, trả `"invalid:An"`.
- `Order(150, "Binh")`: amount lớn hơn hoặc bằng 100, trả `"priority:Binh"`.
- `Order(20, "Chi")`: không thỏa hai guard, trả `"normal:Chi"`.

Các biến component `amount` và `owner` được tạo bởi record pattern **tương ứng ở từng nhánh**, không phải biến tồn tại xuyên suốt toàn bộ switch. Nếu component có khả năng `null`, guard gọi phương thức trên component ấy cần kiểm tra an toàn riêng; chẳng hạn dùng `owner != null && owner.startsWith("A")`.

## 6. Khi guard sai thì chuyện gì xảy ra?

Một nhánh có pattern và guard chỉ được chọn khi **cả hai** cùng phù hợp. Khi pattern khớp nhưng guard trả về `false`, Java **không chạy phần thân nhánh đó**; quá trình tìm nhánh tiếp tục.

Xét:

```java
static String size(Object value) {
    return switch (value) {
        case String s when s.length() > 10 -> "large";
        case String s when s.length() > 5 -> "medium";
        case String s -> "small";
        default -> "other";
    };
}
```

- Với chuỗi dài 12 ký tự, nhánh `"large"` được chọn ngay.
- Với chuỗi dài 8 ký tự, guard đầu sai, guard thứ hai đúng, trả `"medium"`.
- Với chuỗi dài 3 ký tự, cả hai guard sai, nhánh `String s` không guard trả `"small"`.
- Với đối tượng `Integer`, các pattern `String` đều không khớp, trả `"other"`.

Cơ chế này có nét giống chuỗi `if / else if / else`, nhưng có thêm kiểm tra kiểu và biến pattern ngay trong case label. Dù vậy, nó **không** có nghĩa mọi guard đều được thực hiện: các nhánh đứng sau nhánh được chọn sẽ không chạy.

**Guard không khớp khác guard ném ngoại lệ.** Nếu biểu thức `when` ném ngoại lệ, Java **không** coi đó là `false` để thử case tiếp theo. Ngoại lệ truyền ra theo quy tắc Java bình thường, trừ khi được xử lý. Ví dụ `case String s when Integer.parseInt(s) > 0` sẽ ném `NumberFormatException` khi gặp `"abc"`; nhánh `case String s` ở sau **không** tự cứu tình huống này.

## 7. Dominance: nhánh không guard đặt sớm sẽ che nhánh có guard

Compiler Java 21 kiểm tra **dominance** để phát hiện nhánh mà các nhãn trước đã bao phủ hoàn toàn.

Đoạn sau **không biên dịch**:

```java
static String wrong(Object value) {
    return switch (value) {
        case String s -> "any String";
        case String s when s.length() > 3 -> "long String";
        default -> "other";
    };
}
```

Vì `case String s` ở trước khớp tất cả chuỗi khác `null`, nên một nhánh `String` có guard phía sau sẽ không thể được chọn. Compiler báo case label phía sau bị **dominated**.

Cách sửa:

```java
static String correct(Object value) {
    return switch (value) {
        case String s when s.length() > 3 -> "long String";
        case String s -> "other String";
        default -> "other";
    };
}
```

Nhánh có guard đặt trước, nhánh cùng kiểu không guard đặt sau.

### Hai trường hợp đặc biệt: `when true` và `when false`

- `case String s when true -> ...` tương đương việc guard luôn đúng khi pattern khớp. Nó có thể **dominate** những pattern `String` phía sau như nhánh không guard.
- `case String s when false -> ...` là lỗi biên dịch theo Java 21: guard là hằng boolean `false`; nhánh không thể được chọn.

Đây là các trường hợp compiler có thể xác định rõ. Với các điều kiện động như `s.length() > 0` rồi `s.length() > 3`, compiler không nhất thiết chứng minh mọi quan hệ logic giữa các guard. Ví dụ đặt điều kiện `> 0` trước `> 3` thường khiến nhánh sau **không bao giờ chạy đối với chuỗi dài**, dù code có thể vẫn biên dịch.

Hãy rà soát **mức độ giao nhau của các điều kiện**, không chỉ trông chờ trình biên dịch cảnh báo dominance.

## 8. Một case dùng một guard; kết hợp nhiều điều kiện bằng `&&` và `||`

Khi một nhánh chỉ có ý nghĩa nếu đồng thời thỏa nhiều điều kiện, đặt biểu thức boolean kết hợp sau **một** `when`:

```java
static String errorKind(Object value) {
    return switch (value) {
        case String s when s.startsWith("ERR:")
                && s.length() > 4 -> "error with detail";
        case String s when s.startsWith("ERR:") -> "empty error";
        case String s -> "plain";
        default -> "other";
    };
}
```

Với `"ERR:42"` trả `"error with detail"`; với `"ERR:"` trả `"empty error"`. Điều kiện con trong guard tuân theo quy tắc Java bình thường, gồm đánh giá ngắn mạch của `&&` và `||`.

**Không viết hai mệnh đề `when` liên tiếp trên một nhãn:**

```java
// Không hợp lệ:
// case String s when s.startsWith("ERR:") when s.length() > 4 -> ...
```

Nếu muốn nhiều hướng xử lý, hãy viết **nhiều nhãn `case ... when ...`**. Nếu muốn một nhánh yêu cầu đồng thời nhiều ràng buộc, dùng `&&`. Nếu chỉ cần một trong các ràng buộc, dùng `||` và chú ý dấu ngoặc để làm rõ ưu tiên toán tử.

**Đừng dùng dấu phẩy thay cho một chuỗi guard.** Nhãn nhiều hằng kiểu `case RED, BLUE -> ...` là cơ chế nhóm *constant labels*; nó không có nghĩa “thêm một guard” hay “nối nhiều biến pattern” vào cùng nhánh.

## 9. `null`, tính bao phủ và nhánh dự phòng

### Selector có thể là `null`

Trong Java 21 pattern switch, `case String s` không khớp `null`; guard `s.isBlank()` cũng không được đánh giá nếu selector null. Nếu nghiệp vụ cho phép null, nên xử lý rõ:

```java
static String safe(Object value) {
    return switch (value) {
        case null -> "missing";
        case String s when s.isBlank() -> "blank";
        case String s -> "text";
        default -> "other";
    };
}
```

Trong switch trên kiểu tham chiếu theo Java 21, `default` **không** tự thay thế `case null`: nếu không có nhãn xử lý null và selector nhận `null`, một `NullPointerException` có thể xảy ra.

### Switch expression phải exhaustive

Với selector `Object`, chỉ hai nhánh có guard trên `String` không bao phủ toàn bộ các loại đối tượng:

```java
// Không exhaustive cho selector Object:
// return switch (value) {
//     case String s when s.isBlank() -> "blank";
//     case String s when s.length() > 10 -> "long";
// };
```

Cần thêm các nhánh xử lý phần còn lại, chẳng hạn `case String s -> "other text";` và `default -> "other";`.

Nếu selector chỉ có kiểu tĩnh `String`, hai guard vẫn không bảo đảm bao phủ **mọi chuỗi**: có thể tồn tại chuỗi không thỏa guard nào. Một nhánh `case String s` không guard có thể bao phủ mọi giá trị `String` khác null, giúp switch expression exhaustive về kiểu.

**Guard động không tự trở thành “bao phủ đủ”.** Dù người lập trình cho rằng hai điều kiện `s.length() > 0` và `s.length() <= 0` đã chia hết chuỗi theo logic toán học, compiler không nhất thiết dùng suy luận logic đó để chứng minh exhaustiveness. Hãy bổ sung nhánh không guard hoặc `default` phù hợp.

### Record pattern và null component

Một selector có thể là record khác null nhưng component của record có thể null. Ví dụ `Order(1, null)` vẫn là một `Order` hợp lệ trừ khi constructor cấm. Guard `owner.isBlank()` khi owner null có thể ném NPE; cần `owner != null && owner.isBlank()` hoặc thiết kế bất biến dữ liệu.

Cần phân biệt **null của selector** và **null trong dữ liệu được deconstruct**; kiểm tra `case null` chỉ xử lý trường hợp thứ nhất.

## 10. Guard có tác dụng phụ: vì sao nên tránh?

Một guard là biểu thức Java có thể gọi phương thức, và phương thức ấy có thể thay đổi trạng thái hoặc ném ngoại lệ. Điều này hợp lệ về cú pháp trong nhiều trường hợp, nhưng làm việc hiểu thứ tự nhánh khó hơn.

```java
static int checks = 0;

static boolean isLong(String text) {
    checks++;
    return text.length() > 5;
}

static String classify(Object value) {
    return switch (value) {
        case String s when s.isBlank() -> "blank";
        case String s when isLong(s) -> "long";
        case String s -> "ordinary";
        default -> "other";
    };
}
```

Khi selector không phải `String`, `isLong` không được gọi; khi `String` blank, nhánh đầu đã khớp và `isLong` cũng không được gọi; khi `String` không blank, Java mới đến guard có `isLong`.

Có thể dùng ví dụ như trên để **quan sát thứ tự đánh giá**, nhưng trong code nghiệp vụ nên ưu tiên các guard đơn giản, xác định và không có side effects. Điều kiện làm thay đổi cơ sở dữ liệu, đọc I/O hoặc phụ thuộc thời điểm hiện tại có thể khiến cùng selector được phân loại khác nhau và khó tái hiện lỗi.

Nhắc lại: selector expression được tính một lần, **không có nghĩa mọi guard chỉ chạy một lần trong toàn chương trình**. Mỗi lần gọi switch mới có thể đánh giá lại các guard được đi qua; một guard có thể được gọi nhiều lần ở các lượt gọi khác nhau.

## 11. So với `if / else if`: nên dùng khi nào?

Cùng logic phân loại một `Object`:

```java
static String withIf(Object value) {
    if (value instanceof String s && s.isBlank()) {
        return "blank";
    } else if (value instanceof String s && s.length() > 10) {
        return "long";
    } else if (value instanceof String s) {
        return "text";
    }
    return "other";
}
```

Biểu đạt bằng switch Java 21:

```java
static String withSwitch(Object value) {
    return switch (value) {
        case String s when s.isBlank() -> "blank";
        case String s when s.length() > 10 -> "long";
        case String s -> "text";
        default -> "other";
    };
}
```

Cả hai cách có thể biểu đạt cùng thứ tự ưu tiên. Switch giúp gom các nhánh dựa trên một **selector duy nhất**, giúp compiler kiểm tra dominance/exhaustiveness và có thể dễ đọc hơn khi có nhiều kiểu dữ liệu.

Nên cân nhắc `if / else if` nếu các điều kiện không xoay quanh một selector chung hoặc có nhiều bước chuẩn bị khác nhau. Dùng switch nếu bài toán là phân loại **một giá trị** theo kiểu và điều kiện bổ sung, đặc biệt với sealed hierarchy hay record pattern.

Không cố dùng nhiều guard chỉ để thay thế một điều kiện ngắn đơn giản. Nếu không có các nhánh phân loại thật sự, lời gọi phương thức hoặc `if` đơn giản có thể phù hợp hơn.

## 12. Các lỗi thường gặp và cách sửa

| Lỗi | Vì sao xảy ra | Cách sửa |
| --- | --- | --- |
| Đặt `case String s` trước các nhánh `String ... when ...`. | Nhánh không guard khớp tất cả String nên các nhánh sau bị dominated. | Đưa các nhánh có guard lên trước, nhánh tổng quát về cuối. |
| Cho rằng Java tự ưu tiên điều kiện “cụ thể nhất”. | Với nhiều guard động, thứ tự nhánh có ý nghĩa; compiler không sắp xếp lại theo nghiệp vụ. | Sắp xếp các guard theo thứ tự ưu tiên rõ ràng. |
| Viết `when true` rồi thêm một case cùng kiểu phía sau. | Guard đúng hằng giống nhánh không guard; có thể khiến case sau bị dominated. | Bỏ guard thừa hoặc đổi thứ tự/điều kiện. |
| Viết `when false` như nhánh dự phòng. | Guard hằng false bị từ chối khi biên dịch. | Xóa nhánh không thể chạy; dùng nhánh fallback hợp lệ. |
| Viết `when cond1 when cond2`. | Một nhãn không nối nhiều mệnh đề `when` như vậy. | Kết hợp bằng `&&` hoặc viết case label riêng. |
| Cho rằng guard sai sẽ ném ngoại lệ. | Guard trả false chỉ khiến Java thử nhánh sau. | Dùng nhánh fallback; phân biệt với guard thật sự ném ngoại lệ. |
| Cho rằng guard ném ngoại lệ sẽ tự chuyển sang case kế tiếp. | Ngoại lệ không được diễn giải thành false. | Xử lý lỗi ngay trong logic phù hợp hoặc để caller bắt có chủ đích. |
| Dùng biến `s` từ một case ở `default`. | Pattern variable thuộc phạm vi luồng điều khiển của case riêng. | Khai báo một biến khác ở phạm vi ngoài nếu cần. |
| Chỉ có vài nhánh có guard rồi bỏ tất cả nhánh khác. | Switch expression có thể không exhaustive. | Thêm nhánh không guard hoặc `default` phù hợp. |
| Dùng `default` để mong bắt `null`. | Java 21 không coi default là thay thế case null trong switch tham chiếu. | Thêm `case null` khi null là đầu vào dự kiến. |
| Guard gọi method trên component null. | Type pattern match hoặc record deconstruction không bảo đảm mọi component đều non-null. | Kiểm tra `null` hoặc áp dụng bất biến dữ liệu trước khi gọi. |
| Giả định Java 17 có cú pháp `when` cho switch pattern chuẩn. | Tính năng được chuẩn hóa từ Java 21. | Biên dịch bằng Java 21+ hoặc dùng cấu trúc tương thích Java 17. |

## 13. Bài tập và lời giải

### Bài 1 — Dự đoán ưu tiên khi hai guard giao nhau

Cho:

```java
static String route(Object value) {
    return switch (value) {
        case String s when s.length() > 0 -> "non-empty";
        case String s when s.length() > 3 -> "long";
        case String s -> "empty";
        default -> "other";
    };
}
```

`route("hello")` trả gì? Liệu compiler có nhất thiết báo dominance cho nhánh `"long"`?

**Đáp án:** trả `"non-empty"`. Với `"hello"`, guard đầu đã đúng nên nhánh `"long"` phía sau không được chọn. Java 21 có thể chấp nhận đoạn mã này vì việc chứng minh quan hệ logic giữa **hai guard động** không giống dominance của type pattern không guard. Để nhánh `"long"` có ý nghĩa, nên đặt điều kiện `s.length() > 3` trước điều kiện `s.length() > 0`.

### Bài 2 — Phân loại số nguyên với ba guard

Hãy viết switch expression nhận `Object`; khi là `Integer`, trả `"even negative"` nếu âm và chẵn, `"negative"` nếu âm và lẻ, `"non-negative"` nếu không âm. Các kiểu khác trả `"other"`.

**Lời giải:**

```java
static String classifyNumber(Object value) {
    return switch (value) {
        case Integer n when n < 0 && n % 2 == 0 ->
                "even negative";
        case Integer n when n < 0 -> "negative";
        case Integer n -> "non-negative";
        default -> "other";
    };
}
```

Các kết quả: `classifyNumber(-4)` trả `"even negative"`, `classifyNumber(-3)` trả `"negative"`, `classifyNumber(0)` trả `"non-negative"` và `classifyNumber("4")` trả `"other"`. Nếu đặt `case Integer n when n < 0` trước nhánh âm-chẵn, nhánh âm-chẵn sẽ không được chọn cho số âm.

### Bài 3 — Phát hiện lỗi dominance

Đoạn sau có hợp lệ không?

```java
static String bad(Object input) {
    return switch (input) {
        case String s when true -> "any String";
        case String s when s.startsWith("A") -> "starts with A";
        default -> "other";
    };
}
```

**Đáp án:** không. `when true` là điều kiện đúng hằng khi pattern match; nhánh thứ nhất bao phủ tất cả chuỗi và khiến nhánh `String` sau bị dominated. Sửa bằng cách đưa nhánh `startsWith("A")` lên trước rồi dùng `case String s -> "any String";`.

### Bài 4 — Bổ sung fallback cho record

Có record:

```java
record Score(int points) {}
```

Hãy xử lý cùng một record với các điều kiện: điểm từ 90 trở lên → `"excellent"`; từ 60 trở lên → `"pass"`; thấp hơn → `"retry"`; các giá trị không phải Score → `"unknown"`.

**Lời giải:**

```java
static String level(Object input) {
    return switch (input) {
        case Score(int points) when points >= 90 -> "excellent";
        case Score(int points) when points >= 60 -> "pass";
        case Score(int points) -> "retry";
        default -> "unknown";
    };
}
```

Đặt ngưỡng 90 trước ngưỡng 60 vì giá trị từ 90 trở lên **đồng thời** thỏa `>= 60`. Kết quả `level(new Score(95))` là `"excellent"`, `level(new Score(75))` là `"pass"` và `level(new Score(40))` là `"retry"`. Đây là minh họa record pattern Java 21, cần đặt khai báo `Score` trong ngữ cảnh hợp lệ.

### Bài 5 — Guard sai có tạo thêm biến ở nhánh kế tiếp không?

```java
static String describe(Object input) {
    return switch (input) {
        case String text when text.length() > 5 -> "long";
        case String text -> "other String";
        default -> "other";
    };
}
```

**Đáp án:** với chuỗi dài 3, guard đầu sai, Java xét lại nhãn `String text` ở nhánh thứ hai và nhánh ấy khớp. Biến `text` ở nhánh thứ hai là **pattern variable của chính nhánh thứ hai**, không phải việc giữ lại biến thuộc guard đầu. Không có biến pattern chung được chia sẻ xuyên case labels.

## 14. Ghi nhớ

**Nhiều guard trên cùng một kiểu** nghĩa là đặt nhiều `case T x when condition` trong một pattern switch, thường kết thúc bằng `case T x` không guard. Java 21 thử các nhánh theo thứ tự: pattern phải khớp kiểu, rồi guard mới được đánh giá; nếu guard sai, tìm nhánh thích hợp tiếp theo.

Ba nguyên tắc nên nhớ nhất:

1. **Ưu tiên rõ ràng:** khi guard giao nhau, case đứng trước thắng; sắp xếp nhánh từ chuyên biệt/quan trọng tới tổng quát.
2. **Không đặt type pattern tổng quát quá sớm:** `case String s` hoặc `when true` có thể dominate các nhánh `String` phía sau.
3. **Bao phủ và an toàn:** xử lý `null` có chủ đích, bảo đảm switch exhaustive và giữ guard đơn giản, tránh tác dụng phụ hoặc ngoại lệ ngoài dự kiến.

Tài liệu chính thức:
- [JEP 441 — Pattern Matching for switch (Java 21)](https://openjdk.org/jeps/441)
- [Oracle Java 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html)
- [Java Language Specification SE 21 — The switch Statement (§14.11)](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11)
- [Java Language Specification SE 21 — The switch Expression (§15.28)](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.28)
