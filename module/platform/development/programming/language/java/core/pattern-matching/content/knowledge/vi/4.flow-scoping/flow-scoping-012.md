# Đọc flow scope qua control flow trong Java 21

Trong Java, **flow scope** của một *pattern variable* được quyết định bởi **đường đi thực thi mà trình biên dịch có thể chứng minh**, chứ không chỉ bởi vị trí dấu ngoặc nhọn. Để đọc đúng scope, hãy theo các nhánh `true`/`false` của biểu thức, các điểm dừng (`return`, `throw`, `continue`) và các nhánh `switch`, rồi xác định tại mỗi điểm liệu một pattern đã **chắc chắn khớp** hay chưa.

Ví dụ, `value instanceof String text` vừa kiểm tra kiểu vừa giới thiệu biến `text`. Nhưng sự xuất hiện của tên `text` trong điều kiện không có nghĩa nó được dùng ở mọi câu lệnh phía sau. Nó chỉ có hiệu lực nơi mọi đường đi tới đó đều xác nhận phép `instanceof` thành công. Đây là ý nghĩa thực hành của *flow scoping* và *definite matching*.

Bài này dùng Java 21. Type pattern cho `instanceof`, pattern matching cho `switch` và record pattern trong ví dụ đều đã là tính năng ổn định, không cần bật preview.

## 1. Đọc từ đường đi, không đọc theo vị trí dòng

Xét method minh họa:

```java
static void printLength(Object value) {
    if (value instanceof String text) {
        System.out.println(text.length()); // hợp lệ
    } else {
        // System.out.println(text); // lỗi biên dịch
    }

    // System.out.println(text); // lỗi biên dịch
}
```

Đường đi của chương trình:

```text
                 value instanceof String text
                         /          \
                      true          false
                       |              |
                 text đã khớp    không có text
                       |              |
                  nhánh if       nhánh else
                       \              /
                        hợp nhất luồng
                       không bảo đảm text
```

Tại nhánh `if`, mọi đường đi đều bắt nguồn từ kết quả `true`, nên `text` có thể được sử dụng. Nhánh `else` bắt nguồn từ `false`, nên không có biến `text` hợp lệ. Sau `if/else`, chương trình có thể đi đến từ cả hai nhánh; không thể khẳng định pattern đã khớp.

Cách suy luận này còn đúng khi điều kiện chứa nhiều phép toán và khi một nhánh thoát sớm: ta cần xem **những đường đi còn có thể tới vị trí sử dụng biến**, thay vì chỉ xem biến được khai báo ở gần đó.

## 2. Quy tắc truyền trạng thái `true`/`false`

Đặt `P` là biểu thức `value instanceof String text`. Nếu `P` đúng, `text` chắc chắn đã khớp; nếu `P` sai, `text` không được tạo bởi pattern ấy. Đối với biểu thức điều kiện phức tạp, có thể dùng bảng suy luận:

| Cấu trúc | Điều đã biết khi đi tiếp | Hệ quả đối với pattern variable |
| --- | --- | --- |
| `P` trả `true` | `value` là `String` | `text` sử dụng được trên đường đi đó |
| `P` trả `false` | Mẫu không khớp | Không dùng `text` trên đường đi đó |
| `!P` trả `false` | `P` thực ra đúng | `text` sử dụng được |
| `P && C`: bắt đầu đánh giá `C` | `P` đã đúng | `C` được phép dùng `text` |
| `P || C`: bắt đầu đánh giá `C` | `P` đã sai | `C` không được dùng `text` dựa vào `P` |
| `!P || C`: bắt đầu đánh giá `C` | `!P` sai, nên `P` đúng | `C` được phép dùng `text` |
| `if (!P) return;` rồi chạy tiếp | Nhánh `!P` không thể chạy tiếp | `text` được dùng sau `if` |

Bảng chỉ mô tả một pattern `P` và những đường đi trực tiếp liên quan. Với nhiều pattern, mỗi biến có trạng thái khớp riêng. Trình biên dịch dựa trên quy tắc điều khiển luồng của Java, không suy luận tùy ý từ kiến thức nghiệp vụ của người viết.

## 3. `&&`: đi tới vế phải nghĩa là vế trái đúng

`&&` dùng *short-circuit evaluation*: Java **chỉ** chạy vế phải khi vế trái đã trả `true`.

```java
static boolean validName(Object value) {
    return value instanceof String name
            && !name.isBlank()
            && name.length() <= 40;
}
```

Lần theo `value instanceof String name`:

1. Nếu sai, toàn bộ `&&` trả `false`; hai vế còn lại không được đánh giá.
2. Nếu đúng, `name` là `String` và vế `!name.isBlank()` mới chạy.
3. Nếu tên không rỗng, phép kiểm tra độ dài mới chạy. Mọi lần sử dụng `name` trong các vế phía sau đều an toàn.

Tuy vậy, **khi cả điều kiện `&&` sai, không thể suy ngược rằng pattern sai**: có thể pattern đã khớp nhưng điều kiện `isBlank()` hoặc độ dài thất bại.

```java
static String check(Object value) {
    if (value instanceof String name && name.length() > 3) {
        return "long:" + name; // hợp lệ
    } else {
        // name không chắc chắn khớp: value có thể là "abc".
        return "not long";
    }
}
```

Một lỗi thường gặp là nhìn thấy `instanceof` trong điều kiện rồi dùng `name` trong `else`. Để quyết định scope, cần hỏi nhánh `else` có thể đến từ **những kết quả thất bại nào**.

## 4. `||`: đi tới vế phải nghĩa là vế trái sai

Với `||`, Java chỉ chạy vế phải khi vế trái là `false`. Vì vậy, mã sau không hợp lệ:

```java
// KHÔNG BIÊN DỊCH; value là tham số kiểu Object.
static boolean invalid(Object value) {
    return value instanceof String text || text.isEmpty();
}
```

Khi cần đánh giá `text.isEmpty()`, `instanceof` đã trả `false`; tại điểm đó không có `text` được bảo đảm khớp.

Mặt khác, khi đảo điều kiện bên trái thì kết quả suy luận cũng đảo:

```java
static boolean missingOrBlank(Object value) {
    return !(value instanceof String text) || text.isBlank();
}
```

Đường đi:

```text
                    !(value instanceof String text)
                         /                 \
                       true               false
                        |                   |
                   trả về true        instanceof đúng
                   không chạy RHS          |
                                           v
                                      text.isBlank()
```

Để tới `text.isBlank()`, phép phủ định phải là `false`; điều đó chứng minh `value instanceof String text` là `true`. Đây là trường hợp **hợp lệ** dùng pattern variable trong vế phải của `||`.

Không nên nhớ mẹo máy móc “`&&` cho phép còn `||` cấm”. Quy tắc thực sự là **vế phải chạy theo đường nào và đường đó chứng minh điều gì**.

## 5. Kết quả chung của `&&` hoặc `||` có thể mất thông tin

Xét điều kiện:

```java
static boolean enabled(Object value, boolean fallback) {
    if ((value instanceof String text && !text.isBlank()) || fallback) {
        // System.out.println(text); // KHÔNG BIÊN DỊCH
        return true;
    }
    return false;
}
```

Có **hai cách** đi vào thân `if`:

- `value` là chuỗi không rỗng: pattern `text` khớp.
- `fallback` là `true` dù `value` không phải chuỗi: pattern không khớp.

Do đó, tại điểm hợp nhất của hai đường đi, không thể sử dụng `text`. Việc một vế biểu thức *có thể* khớp không đủ; **mọi đường đi hợp lệ** tới vị trí sử dụng đều phải bảo đảm khớp.

Nếu cần dùng chuỗi, đặt thao tác trong nhánh mà `instanceof` trực tiếp bảo vệ:

```java
static void printOrFallback(Object value, boolean fallback) {
    if (value instanceof String text && !text.isBlank()) {
        System.out.println(text.trim());
    } else if (fallback) {
        System.out.println("fallback");
    }
}
```

Cách tổ chức nhánh này thường rõ ràng hơn các biểu thức `&&`/`||` lồng sâu.

## 6. `!`, `return` và `throw`: loại bỏ đường đi thất bại

Điều kiện phủ định làm **đổi chỗ** kết quả đúng/sai của pattern. Nếu đường đi không khớp đã kết thúc, phần còn lại của method chỉ có thể chạy khi pattern khớp:

```java
static String normalize(Object value) {
    if (!(value instanceof String text)) {
        return "not-string";
    }

    return text.strip().toLowerCase(); // hợp lệ
}
```

Đọc từ cuối ngược lên: để tới `text.strip()`, chương trình phải vượt qua `if` mà không `return`. Điều đó chỉ xảy ra nếu `!(value instanceof String text)` sai, nghĩa là `instanceof` đúng.

Cùng ý tưởng với `throw`:

```java
static int lengthOrThrow(Object value) {
    if (!(value instanceof String text)) {
        throw new IllegalArgumentException("String required");
    }
    return text.length();
}
```

Hai method trên là đoạn minh họa cần đặt trong class. Đối với `null`, `instanceof String` cũng là `false`; nhánh `return` hoặc `throw` sẽ được chọn.

**Không phải mọi câu lệnh trong nhánh thất bại đều loại bỏ đường đi.** Ví dụ sau không biên dịch:

```java
// KHÔNG BIÊN DỊCH:
static int missingExit(Object value) {
    if (!(value instanceof String text)) {
        System.out.println("wrong type"); // vẫn có thể đi tiếp
    }
    return text.length(); // không chắc chắn text đã khớp
}
```

`System.out.println` không chặn luồng đi tiếp; muốn dùng `text` sau `if` cần có một đường bảo đảm, như `return` hoặc `throw` trong nhánh không khớp.

## 7. Kết hợp phủ định và short-circuit với early return

Một mẫu thực tế là từ chối đầu vào không đúng kiểu hoặc không hợp lệ:

```java
static String readNonBlank(Object value) {
    if (!(value instanceof String text) || text.isBlank()) {
        return "skip";
    }

    return "read:" + text.strip(); // hợp lệ
}
```

Để câu lệnh cuối chạy, điều kiện `if` phải là `false`. Với `A || B` sai, **cả `A` và `B` đều sai**:

- `!(value instanceof String text)` sai → pattern `String text` đã khớp.
- `text.isBlank()` sai → chuỗi không trống/toàn khoảng trắng.

Bằng cách đó, code sau guard clause có thể an toàn sử dụng `text` và dựa vào kiểm tra nghiệp vụ đã thực hiện.

Nếu nhánh `if` chỉ log rồi chạy tiếp, kết luận này không còn đúng. Khi review code, nên phân biệt rõ **kết quả boolean** với **khả năng câu lệnh hoàn thành bình thường**.

## 8. Đọc `if` lồng nhau như các đường riêng biệt

```java
static String classify(Object value) {
    if (value instanceof CharSequence sequence) {
        if (sequence instanceof String text) {
            return "string:" + text.length();
        }
        return "other character sequence:" + sequence.length();
    }
    return "not character sequence";
}
```

Trong nhánh `if` ngoài, `sequence` chắc chắn là một `CharSequence`. Trong nhánh `if` trong, `text` chắc chắn là một `String`. Nhưng khi `if` trong không khớp, chỉ `sequence` vẫn còn hiệu lực; `text` không thể được dùng.

Hãy tưởng tượng mỗi lần khớp thêm pattern là có thêm **bằng chứng cục bộ** trên đường đi. Khi rẽ sang đường không khớp, không được đem theo bằng chứng của nhánh kia. Ngược lại, bằng chứng đã có từ nhánh bao ngoài vẫn có thể tiếp tục dùng trong phạm vi của nó.

## 9. Vòng lặp: điều kiện và điểm rời vòng lặp

Với vòng `while`, phần thân chỉ chạy khi điều kiện đúng:

```java
static void printWhile(Object value) {
    while (value instanceof String text && !text.isEmpty()) {
        System.out.println(text);
        break;
    }

    // System.out.println(text); // không hợp lệ tại đây
}
```

Trong thân `while`, `text` đã khớp. Sau vòng, có ít nhất một đường đi không vào thân lần nào vì `value` sai kiểu, nên không được dựa vào biến này. Đặc biệt, `break` có thể làm vòng lặp kết thúc **không phải do điều kiện trở thành false**; vì vậy cần đọc các cạnh thoát vòng thay vì đoán trạng thái từ điều kiện.

Với vòng lặp qua nhiều phần tử, guard `continue` có thể giữ code ở dưới gọn hơn:

```java
static void printStrings(java.util.List<?> values) {
    for (Object item : values) {
        if (!(item instanceof String text)) {
            continue;
        }
        System.out.println(text.strip());
    }
}
```

Sau `continue`, luồng chuyển sang lần lặp tiếp theo; trong **lần lặp hiện tại**, những câu lệnh bên dưới chỉ chạy khi `item` khớp `String`. Biến `text` không có phạm vi ra ngoài vòng `for` và không được tái sử dụng qua lần lặp khác.

Đối với `do ... while`, thân chạy trước khi điều kiện cuối vòng được đánh giá, nên không thể lấy một pattern nằm ở điều kiện cuối làm bằng chứng cho những câu lệnh trước đó trong thân.

## 10. Toán tử điều kiện `?:`

Với biểu thức `condition ? a : b`, nhánh `a` chỉ chạy nếu `condition` đúng, còn `b` chạy nếu điều kiện sai.

```java
static String label(Object value) {
    return value instanceof String text ? text.strip() : "other";
}
```

Ở nhánh `text.strip()`, điều kiện `instanceof` chắc chắn đúng nên `text` hợp lệ. Ở nhánh `"other"`, pattern có thể không khớp; không được dùng `text` chỉ dựa vào pattern trong điều kiện.

Có thể áp dụng cùng phương pháp cho điều kiện phủ định: `!(value instanceof String text) ? "other" : text.strip()`. Khi đến nhánh thứ ba, phép phủ định là `false`, nên phép khớp bên trong là `true`.

## 11. Các nhánh `switch` và guard `when` trong Java 21

Pattern matching cho `switch` đưa pattern variable vào **nhánh `case` mà pattern khớp**. Với `when`, biến ấy còn được dùng để đánh giá guard của chính nhánh đó.

```java
record Point(int x, int y) {}

static String describe(Object value) {
    return switch (value) {
        case null -> "missing";
        case String text when !text.isBlank() -> "text:" + text.strip();
        case String ignored -> "blank";
        case Point(var x, var y) when x > 0 && y > 0 -> "quadrant I";
        case Point(var x, var y) -> "point:" + x + "," + y;
        default -> "other";
    };
}
```

Đây là đoạn minh họa yêu cầu đặt `record` và method trong cùng ngữ cảnh class/package Java hợp lệ; chưa phải chương trình độc lập.

Đọc riêng từng `case`:

1. `case String text when ...`: trước khi đánh giá guard, Java đã xác định selector khớp `String text`; `text` dùng được trong guard và phần sau `->`.
2. Nếu guard này không đạt, `switch` có thể xét `case String ignored`. Biến `ignored` thuộc nhánh sau, không kế thừa phạm vi của `text`.
3. Với `case Point(var x, var y) when x > 0 && y > 0`, cả `x` và `y` đã được tách từ record trước khi xét guard. Các biến của `case Point` phía sau cũng là khai báo riêng cho nhánh đó.
4. Trong `default`, không có bằng chứng selector khớp `String` hay `Point`, nên không dùng biến của các nhánh ấy.

`switch` cũng có các quy tắc khác như **dominance** (nhánh kiểu rộng có thể che nhánh kiểu hẹp) và **exhaustiveness** (biểu thức `switch` phải bao phủ mọi khả năng). Chúng liên quan tới việc một đường đi có thể được chọn, nhưng **không thay thế** quy tắc scope: variable thuộc pattern có hiệu lực nơi pattern tương ứng chắc chắn đã khớp. Khi selector có thể là `null`, xử lý riêng bằng `case null` nếu muốn; `default` không mặc nhiên bắt `null`.

## 12. Phân tích nhanh một lỗi thường gặp

Xét ý định “nếu đầu vào là chuỗi hợp lệ hoặc người dùng được cấp quyền ngoại lệ thì đi tiếp”:

```java
// KHÔNG BIÊN DỊCH:
static String incorrect(Object input, boolean privileged) {
    if (input instanceof String text && !text.isBlank() || privileged) {
        return text.strip(); // privileged có thể true khi input không là String
    }
    return "rejected";
}
```

Java ưu tiên `&&` trước `||`, nên điều kiện có nghĩa `(P && nonBlank) || privileged`. Khi `privileged` đúng, `P` có thể sai mà vẫn vào nhánh `if`. Không có cơ sở để dùng `text` ở đó.

Có thể sửa cấu trúc để không lẫn “quyền đi tiếp” với “đã kiểm tra kiểu”:

```java
static String correct(Object input, boolean privileged) {
    if (input instanceof String text && !text.isBlank()) {
        return text.strip();
    }
    if (privileged) {
        return "privileged";
    }
    return "rejected";
}
```

Việc tách nhánh còn làm rõ yêu cầu nghiệp vụ: trường hợp ngoại lệ trả về trạng thái riêng thay vì cố gọi method dành cho `String` lên một đầu vào chưa kiểm tra kiểu.

## 13. Chương trình hoàn chỉnh: lần theo nhiều đường đi

Tạo file **`FlowScopeControlFlowDemo.java`**:

```java
public class FlowScopeControlFlowDemo {
    record Point(int x, int y) {}

    static String normalize(Object value, boolean allowBlank) {
        if (!(value instanceof String text)) {
            return "not-string";
        }
        if (text.isBlank() && !allowBlank) {
            return "blank-rejected";
        }
        return "accepted:" + text.strip();
    }

    static String readNonBlank(Object value) {
        if (!(value instanceof String text) || text.isBlank()) {
            return "skip";
        }
        return "read:" + text.strip();
    }

    static String describe(Object value) {
        return switch (value) {
            case null -> "missing";
            case String text when !text.isBlank() -> "text:" + text.strip();
            case String ignored -> "blank";
            case Point(var x, var y) when x > 0 && y > 0 -> "quadrant I";
            case Point(var x, var y) -> "point:" + x + "," + y;
            default -> "other";
        };
    }

    public static void main(String[] args) {
        System.out.println(normalize("  Java  ", false));
        System.out.println(normalize(17, false));
        System.out.println(normalize("  ", false));
        System.out.println(normalize("", true));

        System.out.println(readNonBlank("  scope  "));
        System.out.println(readNonBlank(" "));
        System.out.println(readNonBlank(42));

        System.out.println(describe(new Point(2, 3)));
        System.out.println(describe(new Point(-1, 3)));
        System.out.println(describe(""));
        System.out.println(describe(null));
    }
}
```

Biên dịch và chạy với **JDK 21**:

```bash
javac --release 21 FlowScopeControlFlowDemo.java
java FlowScopeControlFlowDemo
```

Stdout:

```text
accepted:Java
not-string
blank-rejected
accepted:
read:scope
skip
skip
quadrant I
point:-1,3
blank
missing
```

Giải thích các đường đi:

- `normalize("  Java  ", false)`: `instanceof` đúng; nhánh `return "not-string"` không chạy, nên `text` có hiệu lực ở các kiểm tra tiếp theo.
- `normalize(17, false)`: pattern không khớp và method thoát ngay; không có đường đi nào tới câu lệnh dùng `text` khi giá trị sai kiểu.
- `normalize("  ", false)`: `text` khớp về kiểu nhưng không đạt quy tắc chuỗi không trống; flow scoping bảo đảm kiểu, còn `isBlank()` kiểm tra nội dung.
- `readNonBlank("  scope  ")`: cả hai vế của `A || B` đều sai ở điều kiện `if`, chứng minh được pattern khớp và chuỗi không blank khi tới câu `return` cuối.
- `describe(new Point(2, 3))`: record pattern khớp, guard xác nhận `x` và `y` dương; đối tượng `Point(-1, 3)` chuyển sang nhánh record pattern kế tiếp. Cả hai nhánh có scope riêng.
- `describe(null)`: `case null` xử lý giá trị selector rỗng trước các pattern khác.

## 14. Checklist khi đọc control flow của một biểu thức mới

Với mỗi lần gặp pattern variable trong code, hãy làm lần lượt:

1. **Xác định pattern khai báo biến.** Ví dụ `input instanceof String text` hoặc `case Point(var x, var y)`; tránh nhầm với biến cục bộ trùng tên ở phạm vi khác.
2. **Vẽ hai cạnh `true`/`false`.** Với `!`, đảo cạnh. Với `&&`, vế phải nhận cạnh `true`; với `||`, vế phải nhận cạnh `false`. Chú ý dấu ngoặc và thứ tự ưu tiên toán tử.
3. **Theo mọi đường tới điểm dùng biến.** Nếu có dù chỉ một đường không khớp pattern mà vẫn đến được điểm đó, biến không được bảo đảm trong phạm vi.
4. **Xóa các đường đã kết thúc.** Nhánh có `return`, `throw` hoặc `continue` có thể loại bỏ đường không khớp khỏi phần code đang xét; nhánh chỉ log thì không.
5. **Tách riêng scope của từng `case` hoặc lần lặp.** Pattern variable trong một nhánh `switch` không tự có hiệu lực ở nhánh khác; pattern ở điều kiện vòng lặp phải được đánh giá theo các điểm vào/ra vòng.
6. **Kiểm tra cả logic nghiệp vụ.** “Biến đã khớp kiểu” khác với “giá trị hợp lệ”. Flow scoping chứng minh tính an toàn của việc sử dụng biến, không chứng minh quy tắc như không rỗng, số dương hay có quyền truy cập.

Khi có thể trả lời câu hỏi **“tại điểm này, mọi đường đi đều đã chứng minh pattern khớp chưa?”**, bạn đã có cách đọc flow scope qua control flow. Đây là nền tảng để dùng pattern matching vừa ngắn gọn vừa an toàn, đặc biệt trong các biểu thức boolean phức tạp và guard clause.
