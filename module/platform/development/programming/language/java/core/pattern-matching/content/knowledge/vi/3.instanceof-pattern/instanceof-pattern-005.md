# Kết hợp `instanceof` với biểu thức trả về trong Java

## 1. Tại sao `instanceof` thường xuất hiện ngay trong `return`?

Khi nhận một giá trị có kiểu khai báo rộng như `Object`, chương trình có thể cần trả lời hai câu hỏi: **giá trị có thuộc một kiểu cụ thể không?** và **nếu đúng thì kết quả cần trả về là gì?** Java cho phép kết hợp việc kiểm tra kiểu trực tiếp trong một biểu thức trả về. Cách này phù hợp với những phương thức ngắn như kiểm tra đầu vào, chuẩn hóa một chuỗi, lấy độ dài hoặc chọn giá trị mặc định.

Hãy phân biệt ba khái niệm:

- **`instanceof` là toán tử tạo biểu thức Boolean.** Chẳng hạn `value instanceof String` có kết quả `true` hoặc `false`; bản thân nó không trả về chuỗi.
- **Type pattern** trong `value instanceof String text` vẫn tạo một giá trị Boolean, nhưng còn khai báo biến `text` có kiểu `String` khi mẫu khớp.
- **`return` trả về giá trị của biểu thức phía sau nó.** Biểu thức đó có thể là phép kiểm tra `instanceof`, phép kết hợp `&&`, hoặc biểu thức điều kiện `?:`. Kiểu kết quả phải phù hợp với kiểu trả về của phương thức.

Ví dụ tối giản, có thể đặt bên trong một lớp Java:

```java
static boolean isString(Object value) {
    return value instanceof String;
}
```

Với `isString("Java")` kết quả là `true`; với `isString(17)` hoặc `isString(null)` kết quả là `false`. Trong trường hợp chỉ cần câu trả lời có/không, không cần khai báo biến mẫu rồi bỏ không.

Mục tiêu của bài là hiểu **biểu thức được đánh giá như thế nào, biến mẫu có hiệu lực ở đâu, kết quả `return` có kiểu gì và cách tránh lỗi với `null`**. Tất cả ví dụ thực hành chính dùng tính năng ổn định từ Java 16, chạy được trên Java 17 trở lên.

## 2. Trả về trực tiếp kết quả kiểm tra kiểu

### 2.1. Phương thức trả về `boolean`

Cách viết dài:

```java
static boolean isText(Object value) {
    if (value instanceof String) {
        return true;
    }
    return false;
}
```

Cùng hành vi đó có thể diễn đạt ngắn hơn:

```java
static boolean isText(Object value) {
    return value instanceof String;
}
```

Ở đây, `instanceof` tự trả về `boolean`; không cần viết thêm `? true : false`. Các ví dụ trên minh họa **hai cách triển khai thay thế cho cùng một phương thức**, không được đặt đồng thời trong một lớp với cùng chữ ký.

Lưu ý: `instanceof` kiểm tra quan hệ kiểu của đối tượng tại thời điểm chạy, không kiểm tra nội dung chuỗi. Cả `"Java"`, `""` và `"   "` đều là `String` nên `isText` trả về `true`. Kiểm tra giá trị có ích hay không cần thêm điều kiện ở bước sau.

### 2.2. Kết hợp với `&&` để trả về một điều kiện có ý nghĩa hơn

Java cho phép dùng **pattern variable** trong phần bên phải của `&&` sau khi phần bên trái xác nhận kiểu:

```java
static boolean hasNonBlankText(Object value) {
    return value instanceof String text && !text.isBlank();
}
```

Biểu thức chạy theo thứ tự:

1. Kiểm tra `value instanceof String text`.
2. Nếu **không khớp**, `&&` trả ngay `false`; Java **không** gọi `text.isBlank()`.
3. Nếu **khớp**, `text` đã chắc chắn là `String` và phần bên phải kiểm tra nội dung.
4. `return` trả về Boolean của toàn bộ biểu thức.

Do `instanceof` không khớp `null`, `hasNonBlankText(null)` trả về `false` mà không gây `NullPointerException`. Với `""` hoặc `"  "`, kết quả cũng là `false` vì `String.isBlank()` coi chuỗi rỗng hoặc chỉ gồm ký tự khoảng trắng là blank.

Đây là một ví dụ về **đánh giá ngắn mạch** (*short-circuit evaluation*): vế phải của `&&` chỉ chạy khi vế trái là `true`. Cú pháp pattern variable giúp bạn tránh ép kiểu thủ công và liên kết trực tiếp điều kiện kiểm tra kiểu với điều kiện kiểm tra dữ liệu.

### 2.3. Thêm nhiều ràng buộc mà vẫn giữ điều kiện an toàn

```java
static boolean isValidAge(Object value) {
    return value instanceof Integer age && age >= 0 && age <= 120;
}
```

Nếu `value` là `"18"` (chuỗi) thì hàm trả về `false`, dù nội dung trông như số. Pattern matching **không tự parse** chuỗi thành số nguyên. Nếu `value` là `Integer.valueOf(18)` thì cả ba điều kiện đều đúng.

Ưu điểm của cách viết này là biểu thức trả về phản ánh đúng quy tắc: *phải là `Integer` và nằm trong khoảng cho phép*. Khi quy tắc nhiều nhánh hoặc cần thông báo lỗi riêng, nên tách thành các `if` để dễ đọc và kiểm thử.

## 3. Dùng `instanceof` trong toán tử điều kiện `?:`

Nếu phương thức cần trả về một giá trị **khác Boolean**, có thể dùng toán tử điều kiện:

```java
static int textLengthOrZero(Object value) {
    return value instanceof String text ? text.length() : 0;
}
```

Trong biểu thức `condition ? whenTrue : whenFalse`:

- `value instanceof String text` là điều kiện Boolean.
- Nhánh sau `?` được chọn khi mẫu khớp; lúc này biến `text` có hiệu lực và `text.length()` trả về `int`.
- Nhánh sau `:` được chọn khi mẫu không khớp, trong đó có `null`; kết quả là `0`.
- Cả hai nhánh trả về kiểu tương thích với `int` của phương thức.

Ví dụ: `textLengthOrZero("Java")` trả về `4`, `textLengthOrZero(42)` trả về `0`, và `textLengthOrZero(null)` trả về `0`. Giá trị `0` ở đây là **mặc định do lập trình viên chọn**, không phải hành vi tự động của `instanceof`.

### 3.1. Biến mẫu chỉ sẵn sàng ở nhánh được chứng minh là khớp

```java
static String label(Object value) {
    return value instanceof String text
            ? "Chuỗi: " + text.strip()
            : "Không phải chuỗi";
}
```

`text` dùng được trong nhánh `?` vì chỉ có thể đi vào nhánh đó khi `instanceof` trả về `true`. Không được giả định `text` tồn tại trong nhánh `:`.

Ví dụ **sai, không biên dịch**:

```java
static int invalidLength(Object value) {
    return value instanceof String text ? 0 : text.length();
    // SAI: nhánh ':' chạy khi value không khớp String.
}
```

Nếu cần xử lý cả hai trường hợp bằng một biến, hãy khai báo biến chung với kiểu và giá trị phù hợp, hoặc dùng `if` với hai đường trả về độc lập. Không cố dùng biến mẫu ngoài đường đi đã xác nhận kiểu.

### 3.2. Kết hợp `&&` với `?:` để chọn dữ liệu trả về

```java
static String displayName(Object value) {
    return (value instanceof String text && !text.isBlank())
            ? text.strip()
            : "(không có tên hợp lệ)";
}
```

Cả kiểm tra kiểu lẫn kiểm tra nội dung phải đúng thì nhánh `?` mới chạy. Thêm dấu ngoặc quanh điều kiện giúp người đọc nhận ra rõ ràng toàn bộ điều kiện của toán tử `?:`. `String.strip()` loại bỏ khoảng trắng ở hai đầu theo quy tắc của Java; nó chỉ chạy sau khi Java đã xác nhận `text` là `String`.

Biểu thức `?:` phù hợp khi hai nhánh ngắn và cùng diễn đạt một quyết định. Nếu các nhánh dài, lồng nhiều lần hoặc ném các lỗi khác nhau, `if/else` thường rõ hơn.

## 4. Kết hợp `instanceof` với `return` sớm

Không phải lúc nào cũng cần dùng toán tử `?:`. Khi giá trị sai kiểu cần thoát ngay, hãy dùng **guard clause** (điều kiện chặn) và trả về sớm:

```java
static int lengthAfterGuard(Object value) {
    if (!(value instanceof String text)) {
        return 0;
    }
    return text.length();
}
```

Vì nhánh không khớp đã `return`, mọi đường chạy đến câu lệnh cuối đều bảo đảm `value` khớp `String`. Vì thế `text` hợp lệ sau `if`. Cơ chế xác định phạm vi theo luồng điều khiển này gọi là **flow scoping**.

So sánh với cách viết biểu thức đơn:

```java
static int lengthWithConditional(Object value) {
    return value instanceof String text ? text.length() : 0;
}
```

Cả hai cùng trả về độ dài nếu đầu vào là `String`, còn lại trả về `0`. Chúng là **hai phương thức khác tên** để minh họa lựa chọn phong cách:

- Dùng `?:` khi lựa chọn rất ngắn.
- Dùng `if` + `return` sớm khi cần giải thích vì sao từ chối hoặc còn nhiều bước xử lý sau kiểm tra.

Lưu ý phạm vi biến mẫu sau điều kiện thông thường:

```java
static int simpleIf(Object value) {
    if (value instanceof String text) {
        return text.length();
    }
    return 0;
}
```

`text` nằm trong nhánh `if` khớp mẫu. Mã dưới đây **không hợp lệ** vì dòng cuối có thể chạy sau khi mẫu không khớp:

```java
static int invalidScope(Object value) {
    if (value instanceof String text) {
        System.out.println("Đã khớp");
    }
    return text.length(); // SAI: text không chắc chắn tồn tại tại đây.
}
```

Khác biệt nằm ở đường đi có thể đến câu lệnh `return`, không chỉ ở vị trí dấu ngoặc nhọn.

## 5. `&&`, `||` và dấu `!` ảnh hưởng đến biến mẫu thế nào?

Người mới học dễ cho rằng chỉ cần thấy `instanceof String text` là từ đó mọi nơi đều dùng được `text`. Trên thực tế, Java chỉ cho phép dùng biến ở những vị trí mà đường đi chắc chắn đã làm mẫu khớp.

| Biểu thức | Có hợp lệ không? | Vì sao? |
| --- | --- | --- |
| `return value instanceof String text && text.length() > 2;` | Có | Khi đánh giá vế phải `&&`, vế trái đã đúng |
| `return value instanceof String text ? text.length() : 0;` | Có | Nhánh `?` chỉ chạy khi mẫu khớp |
| `return !(value instanceof String text) || text.isBlank();` | Có | Vế phải `||` chỉ chạy khi phủ định là sai, tức mẫu đã khớp |
| `return value instanceof String text || text.isBlank();` | Không | Khi vế trái là sai, `text` chưa được ràng buộc |
| `return value instanceof String text ? 0 : text.length();` | Không | Nhánh `:` chạy khi mẫu không khớp |

Ví dụ **hợp lệ** với phủ định và `||`:

```java
static boolean shouldReject(Object value) {
    return !(value instanceof String text) || text.isBlank();
}
```

Diễn giải: từ chối nếu giá trị không phải `String` **hoặc** nếu là `String` thì chuỗi blank. Khi `value` sai kiểu, vế trái `||` đúng và Java không đánh giá vế phải. Khi giá trị đúng kiểu, phủ định sai nên vế phải mới chạy và `text` đã có hiệu lực.

Ví dụ **sai**:

```java
static boolean invalidOr(Object value) {
    return value instanceof String text || text.isBlank();
    // SAI: nếu vế trái false, vế phải cần dùng text chưa khớp.
}
```

Có thể sửa thành:

```java
static boolean isStringOrFallback(Object value, boolean fallback) {
    return value instanceof String || fallback;
}
```

Nếu chỉ cần kết hợp hai Boolean độc lập, không cần dùng biến mẫu. Đặc biệt tránh thay `&&` bằng `&` hoặc `||` bằng `|` một cách máy móc: các toán tử không ngắn mạch sẽ đánh giá cả hai vế và không cung cấp cùng bảo đảm về phạm vi biến.

## 6. Ví dụ hoàn chỉnh chạy với Java 17

Chương trình sau tổng hợp bốn trường hợp: trả về Boolean, trả về kết quả của `?:`, khai thác một interface rộng hơn `String`, và thoát sớm với `return`. Nó dùng Java 17, không cần `--enable-preview`.

Lưu toàn bộ mã thành **`InstanceofReturnDemo.java`**:

```java
public class InstanceofReturnDemo {
    static boolean isNonBlankText(Object value) {
        return value instanceof String text && !text.isBlank();
    }

    static String display(Object value) {
        return (value instanceof String text && !text.isBlank())
                ? text.strip()
                : "(trống hoặc sai kiểu)";
    }

    static int textLength(Object value) {
        return value instanceof CharSequence text ? text.length() : 0;
    }

    static String describe(Object value) {
        if (value instanceof Integer number) {
            return "int=" + number;
        }
        if (value instanceof String text) {
            return "str=" + text.strip();
        }
        return "other";
    }

    static boolean shouldReject(Object value) {
        return !(value instanceof String text) || text.isBlank();
    }

    static int lengthAfterGuard(Object value) {
        if (!(value instanceof String text)) {
            return 0;
        }
        return text.length();
    }

    public static void main(String[] args) {
        System.out.println(isNonBlankText("  Java  "));
        System.out.println(isNonBlankText(" \t "));
        System.out.println(isNonBlankText(null));

        System.out.println(display("  Java  "));
        System.out.println(display(12));
        System.out.println(textLength(new StringBuilder("xyz")));

        System.out.println(describe(7));
        System.out.println(describe("  A  "));
        System.out.println(describe(null));

        System.out.println(shouldReject("  "));
        System.out.println(shouldReject("OK"));

        System.out.println(lengthAfterGuard("Hello"));
        System.out.println(lengthAfterGuard(25));
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 --release 17 InstanceofReturnDemo.java
java InstanceofReturnDemo
```

Kết quả chuẩn:

```text
true
false
false
Java
(trống hoặc sai kiểu)
3
int=7
str=A
other
true
false
5
0
```

Giải thích các dòng đáng chú ý:

- `isNonBlankText(null)` là `false` vì toán tử `instanceof` không khớp `null` và `&&` dừng sớm.
- `display("  Java  ")` trả về `Java`: đầu vào là `String` không blank; sau đó `strip()` bỏ khoảng trắng hai đầu.
- `textLength(new StringBuilder("xyz"))` trả về `3`: `StringBuilder` triển khai `CharSequence`. Pattern matching không chỉ dùng với `String`; biến `text` có kiểu tĩnh là `CharSequence`.
- `describe(7)` trả về `int=7` nhờ nhánh `Integer`. `describe(null)` đi đến `return "other"`.
- `shouldReject("  ")` là `true` vì chuỗi blank; `shouldReject("OK")` là `false`.
- `lengthAfterGuard(25)` trả về `0` ngay ở nhánh chặn, không có lời gọi `text.length()` trên giá trị sai kiểu.

Có thể thử thay `new StringBuilder("xyz")` bằng `"abc"` và `42` để quan sát cả nhánh khớp và không khớp. Nhớ rằng biến `text` trong `textLength` có kiểu `CharSequence`, chỉ dùng được những phương thức mà interface này công bố.

## 7. So sánh cách viết trước và sau khi có type pattern

### 7.1. Tránh kiểm tra kiểu rồi ép kiểu thủ công

Cách viết cũ:

```java
static int lengthOld(Object value) {
    return value instanceof String
            ? ((String) value).length()
            : 0;
}
```

Cách viết với pattern:

```java
static int lengthNew(Object value) {
    return value instanceof String text
            ? text.length()
            : 0;
}
```

Hai phương thức có cùng hành vi đối với đối số `String`, đối số sai kiểu và `null`. Bản dùng pattern bỏ phép ép kiểu lặp lại và giúp trình biên dịch theo dõi biến đã đúng kiểu. Đây là refactor phù hợp khi mục tiêu thật sự là sử dụng giá trị sau khi xác nhận kiểu.

### 7.2. Không phải mọi phương thức đều nên viết thành một dòng

Giả sử cần trả thông báo khác nhau cho giá trị sai kiểu, chuỗi blank và chuỗi hợp lệ:

```java
static String explain(Object value) {
    if (!(value instanceof String text)) {
        return "Đầu vào không phải String";
    }
    if (text.isBlank()) {
        return "Chuỗi không có nội dung";
    }
    return "Nội dung: " + text.strip();
}
```

Tình huống này phù hợp với nhiều `return` sớm. Một chuỗi `?:` lồng nhau sẽ khó theo dõi hơn và khiến người đọc bỏ sót các điều kiện. Thêm nữa, nếu có thao tác có thể ném ngoại lệ hoặc cần log ngữ cảnh, tách thành các lệnh `if` giúp kiểm tra luồng xử lý rõ ràng.

### 7.3. Đúng kiểu trả về mới là điều kiện hoàn chỉnh

Với `boolean`, trả về trực tiếp điều kiện:

```java
static boolean isInteger(Object value) {
    return value instanceof Integer;
}
```

Với `int`, cần một biểu thức tạo `int` ở cả hai nhánh:

```java
static int integerOrZero(Object value) {
    return value instanceof Integer number ? number : 0;
}
```

Với `String`, chọn hai kết quả có thể dùng như `String`:

```java
static String stringOrFallback(Object value) {
    return value instanceof String text ? text : "(mặc định)";
}
```

Không thể cho rằng `instanceof` tự biến thành kiểu trả về được yêu cầu. Ví dụ sau **sai kiểu trả về**:

```java
static String invalidReturn(Object value) {
    return value instanceof String;
    // SAI: biểu thức có kiểu boolean, phương thức cần String.
}
```

Khi phối hợp các nhánh trong `?:`, hãy quan tâm cả kiểu suy luận, ép kiểu số, tự động boxing/unboxing và việc một nhánh có thể là `null`. Đừng trộn kết quả không cùng ý nghĩa chỉ để rút ngắn code.

## 8. Đọc đúng hành vi với `null` và giá trị không khớp

Những tình huống thường gặp:

| Đầu vào | `value instanceof String text` | `text` có được dùng trong nhánh khớp? | `return value instanceof String text ? text.length() : 0;` |
| --- | --- | --- | --- |
| `"Java"` | `true` | Có, là `"Java"` | `4` |
| `""` | `true` | Có, là chuỗi rỗng | `0` |
| `"  "` | `true` | Có, là chuỗi khoảng trắng | `2` |
| `Integer.valueOf(5)` | `false` | Không | `0` |
| `null` | `false` | Không | `0` |

Điều cần nhớ: **`instanceof` kiểm tra kiểu, còn `isBlank()` kiểm tra nội dung**. `String` rỗng vẫn khớp pattern `String`. Ngoài ra, toán tử `?:` chỉ đánh giá nhánh được chọn; một biểu thức ở nhánh còn lại không chạy.

Pattern matching **không phải cơ chế bắt ngoại lệ**. Nếu bạn gọi phương thức bên trong nhánh khớp và phương thức đó ném ngoại lệ vì lý do khác, `instanceof` không tự xử lý ngoại lệ ấy. Hãy dùng điều kiện hợp lý hoặc xử lý lỗi riêng khi nghiệp vụ yêu cầu.

## 9. Những lỗi dễ mắc và cách sửa

| Lỗi | Điều cần sửa |
| --- | --- |
| Viết `return value instanceof String text;` trong phương thức trả về `String` | Biểu thức `instanceof` có kiểu `boolean`; đổi kiểu trả về thành `boolean` hoặc chọn `String` bằng `?:` |
| Dùng `text` sau `instanceof` dù không chắc đã khớp | Phân tích flow scoping; đặt việc sử dụng biến trong nhánh đúng hoặc sau guard thoát sớm |
| Dùng `value instanceof String text || text.isBlank()` | `text` chưa có hiệu lực khi vế trái `||` sai; dùng `&&` hoặc đổi logic với phủ định nếu phù hợp |
| Để `text.length()` ở nhánh `:` khi condition là `instanceof String text` | Nhánh `:` là nơi mẫu không khớp; trả mặc định hoặc dùng biểu thức độc lập |
| Cho rằng `instanceof` tự chuyển `"12"` thành `Integer` | Pattern không tự parse; nếu cần chuyển chuỗi thành số, dùng API chuyển đổi riêng với xử lý lỗi |
| Cho rằng `instanceof` nhận `null` là một `String` | Mẫu kiểu trong `instanceof` luôn không khớp `null` |
| Nhầm `String.isBlank()` với kiểm tra giá trị có kiểu String | Kiểu và nội dung là hai điều kiện độc lập; sắp xếp qua `&&` để tránh gọi trên sai kiểu |
| Viết nhiều toán tử `?:` lồng nhau để xử lý nghiệp vụ phức tạp | Chọn `if/else` và các `return` sớm có tên điều kiện rõ nghĩa |
| Dùng type pattern cho một biểu thức đã có kiểu tĩnh chắc chắn là kiểu đích | Tránh pattern thừa; một số trường hợp bị Java bác vì mẫu chắc chắn khớp theo kiểu tĩnh |
| Nghĩ `return` đầu tiên đã bảo đảm nhánh sau chạy an toàn khi nó không loại bỏ mọi giá trị sai kiểu | Xem tất cả đường đi đến câu lệnh sau và lý do mà trình biên dịch biết mẫu đã khớp |

Trong các lỗi “sai” ở bài này, ví dụ được gắn nhãn cố ý để bạn đọc lỗi trình biên dịch. Khi tự chạy, chỉ sao chép các ví dụ được đánh dấu hợp lệ hoặc chương trình hoàn chỉnh ở mục 6.

## 10. Bài tập thực hành có tiêu chí kiểm tra

**Bài 1 — Kiểm tra Boolean:** Viết `static boolean isPositiveInteger(Object value)` dùng đúng một câu lệnh `return` và `instanceof Integer n`. Hàm trả về `true` khi `n > 0`, ngược lại `false`. Thử lần lượt `5`, `0`, `-3`, `"5"` và `null`. Tự giải thích vì sao chuỗi `"5"` không được chấp nhận.

**Bài 2 — Chọn kết quả bằng `?:`:** Viết `static String upperOrUnknown(Object value)`. Khi đầu vào là `String` không blank, trả về chuỗi sau khi `strip()` và chuyển thành chữ hoa bằng `toUpperCase(java.util.Locale.ROOT)`. Nếu sai kiểu hoặc blank, trả về `"UNKNOWN"`. Dùng một biểu thức `return` rõ ràng, với `instanceof` và `&&`.

**Bài 3 — Guard clause:** Viết `static int countChars(Object value)`. Nếu đầu vào không phải `CharSequence`, trả về `0` ngay. Nếu đúng kiểu, trả về `length()`. Không dùng ép kiểu thủ công; kiểm tra với `"ab"`, `new StringBuilder("abc")`, `new Object()` và `null`.

**Bài 4 — Đọc lỗi biên dịch:** Cho các biểu thức:
- `return input instanceof String text && text.length() > 1;`
- `return input instanceof String text || text.length() > 1;`
- `return !(input instanceof String text) || text.isBlank();`

Giả sử chúng nằm trong ba phương thức `boolean` nhận `Object input`. Hãy phân loại hợp lệ/không hợp lệ, giải thích mỗi vế được chạy trong điều kiện nào, sau đó thử với trình biên dịch. Điều quan trọng là nêu được **đường đi làm biến mẫu chắc chắn được ràng buộc**.

**Bài 5 — Chọn cách viết:** Một phương thức cần trả về thông báo riêng cho `null`, sai kiểu, chuỗi trắng và chuỗi hợp lệ. Viết hai phiên bản: (a) dùng `?:` nếu có thể giữ rõ nghĩa, (b) dùng `if` + `return` sớm. Giải thích phiên bản nào dễ mở rộng khi có thêm điều kiện xác thực và vì sao.

Gợi ý tự đối chiếu: mỗi phương thức nên có ca kiểm tra đầu vào **đúng kiểu**, **sai kiểu**, **`null`** và một ca **biên** phù hợp. Với phương thức trả về `String`, xác minh cả giá trị lẫn chữ hoa/chữ thường, khoảng trắng. Với Boolean, không cần dùng `? true : false` sau một biểu thức Boolean.

## 11. Checklist nắm vững trước khi chuyển bài

Bạn đã hiểu cách kết hợp `instanceof` với biểu thức trả về khi có thể giải thích rõ:

1. Vì sao `return value instanceof String;` hợp lệ trong phương thức `boolean` nhưng không hợp lệ trong phương thức `String`?
2. `value instanceof String text` tạo ra Boolean hay một `String`? Biến `text` nhận giá trị ở điều kiện nào?
3. Vì sao `&&` ngăn lời gọi `text.isBlank()` trên đầu vào sai kiểu và `null`?
4. Biến mẫu có thể được dùng ở nhánh nào của `condition ? x : y`, và vì sao?
5. Khi nào `!(value instanceof String text)` kết hợp `||` lại hợp lệ?
6. Dùng `return` sớm ảnh hưởng thế nào đến phạm vi biến pattern sau câu lệnh `if`?
7. Khi nào một `return` có `?:` dễ đọc hơn, và khi nào nên dùng nhiều `return` sớm?

Nếu trả lời được bằng lý giải luồng chạy và tự kiểm tra được các ví dụ Java 17, bạn có thể chuyển sang nội dung flow scoping hoặc phân nhánh theo nhiều kiểu. Tư duy cốt lõi ở đây là **mẫu kiểm tra kiểu trả về Boolean; các nhánh điều khiển xác định lúc nào biến mẫu an toàn; `return` lấy kết quả của biểu thức phù hợp với hợp đồng phương thức**.

## 12. Nguồn tham khảo

- [JEP 394 — Pattern Matching for instanceof](https://openjdk.org/jeps/394): quy tắc type pattern và flow scoping, trở thành tính năng chính thức trong Java 16.
- [Java Language Specification, Java SE 17 — `instanceof`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.20.2): ngữ nghĩa biểu thức kiểm tra kiểu.
- [Java Language Specification, Java SE 17 — `?:`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.25): điều kiện, nhánh được đánh giá và kiểu kết quả.
- [Java Language Specification, Java SE 17 — Pattern variable scope](https://docs.oracle.com/javase/specs/jls/se17/html/jls-6.html#jls-6.3): phạm vi biến mẫu theo luồng điều khiển.
