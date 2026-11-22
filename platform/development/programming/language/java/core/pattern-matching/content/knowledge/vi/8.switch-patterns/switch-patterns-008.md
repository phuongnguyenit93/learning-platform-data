# Arrow rule và colon group trong switch pattern (Java 21)

Trong Java 21, một `switch` có hai cách tổ chức nhánh:

- **Switch rule**: `case ... ->`, mỗi nhánh thực hiện phần bên phải mũi tên và **không fall-through** sang nhánh kế tiếp.
- **Switch labeled statement group**: `case ... :`, các nhãn gắn với một nhóm câu lệnh; trong `switch statement`, luồng điều khiển **có thể tiếp tục xuống nhóm sau** nếu không kết thúc bằng `break`, `return`, `throw` hoặc cơ chế thoát phù hợp.

Cả hai cách đều dùng được với **pattern matching for switch**, một tính năng chính thức của Java 21 (JEP 441). Chúng cũng áp dụng cho `switch statement` (câu lệnh thực thi hành động) và `switch expression` (biểu thức tạo ra một giá trị). Tuy nhiên, **cách kết thúc nhánh** khác nhau giữa statement/expression và giữa `->`/`:`.

Điểm cần đặc biệt chú ý với pattern là **pattern variable chỉ tồn tại trên đường đi mà pattern đã khớp**. Java 21 đặt thêm hạn chế đối với fall-through đi *vào* một nhãn `case` khai báo pattern variable để tránh sử dụng biến chưa được khởi tạo.

## 1. Nhận diện hai kiểu nhãn

### Arrow rule: `case L ->`

```java
static String describe(Object value) {
    return switch (value) {
        case null -> "missing";
        case String text -> "text: " + text;
        case Integer number -> "integer: " + number;
        default -> "other";
    };
}
```

Đây là một **method minh họa**, đặt trong class Java. Khi `value` khớp `String text`, kết quả nhánh là `"text: " + text`. Sau nhánh đó, `switch` kết thúc; không chạy tiếp vào `case Integer number` hay `default`.

Cú pháp `->` thể hiện rõ “nhãn nào khớp thì thực thi nhánh ấy”. Đối với `switch expression`, biểu thức sau `->` trực tiếp tạo giá trị kết quả.

### Colon group: `case L:`

```java
static String describeWithColon(Object value) {
    return switch (value) {
        case null:
            yield "missing";
        case String text:
            yield "text: " + text;
        case Integer number:
            yield "integer: " + number;
        default:
            yield "other";
    };
}
```

Đây cũng là một method minh họa. Với `switch expression`, nhóm câu lệnh sau dấu `:` phải đi tới `yield` (hoặc ném exception) để tạo giá trị; **`break` không thay thế `yield`**. Cả hai method trên trả cùng kết quả cho đầu vào tương ứng.

**Không trộn `->` và `:` trong cùng một `switch` block.** Chọn một dạng tổ chức thống nhất cho toàn bộ block.

## 2. Bảng so sánh trọng tâm

| Tiêu chí | Arrow rule `->` | Colon group `:` |
| --- | --- | --- |
| Cách tổ chức | Một nhãn dẫn đến một rule: expression, block hoặc `throw` | Nhãn dẫn đến một nhóm câu lệnh |
| Fall-through | Không | Có thể xảy ra trong `switch statement` nếu nhóm không thoát |
| `switch statement` | Không cần `break` ngăn fall-through; phần expression của rule phải là *statement expression* | Thường dùng `break`, `return` hoặc `throw` để tránh chạy xuống nhóm sau |
| `switch expression` | `-> biểu_thức` tạo giá trị trực tiếp; block cần `yield` hoặc `throw` | Dùng `yield biểu_thức;` hoặc `throw` ở đường đi tạo kết quả |
| Pattern variable | Trong guard và phần thân của rule đã khớp | Trong guard và nhóm câu lệnh tương ứng đã khớp |
| Mã mới | Thường ưu tiên vì rõ ràng, tránh fall-through vô tình | Hữu ích khi cần duy trì/cải tiến `switch` kiểu cũ hoặc có chủ ý dùng group |

`break` và `yield` không đồng nghĩa: `break` dùng để thoát `switch statement`, còn `yield` cung cấp kết quả cho một `switch expression`. Tên **arrow rule** hay **colon group** mô tả cấu trúc nhánh; không tự quyết định việc cả `switch` là statement hay expression.

## 3. `switch statement` với arrow rule: mỗi nhánh độc lập

```java
static void printValue(Object input) {
    switch (input) {
        case null -> System.out.println("null");
        case String text -> System.out.println(text.toUpperCase());
        case Integer number -> {
            System.out.println("integer");
            System.out.println(number + 1);
        }
        default -> System.out.println("other");
    }
}
```

Đây là method minh họa (cần đặt trong class). Khi đầu vào là `"abc"`, chỉ in `ABC`. Nếu là `Integer`, chỉ chạy block của `Integer`. **Không cần thêm `break` ở cuối mỗi rule**.

Ở `switch statement`, vế `case L -> expression;` phải là **statement expression**, ví dụ lời gọi method, phép gán, phép tăng/giảm hoặc thao tác tạo đối tượng. Một phép tính trần như `case Integer i -> i + 1;` **không phải** một rule expression hợp lệ của `switch statement`: biểu thức `i + 1` không phải statement expression. Nếu muốn tạo giá trị, hãy dùng `switch expression`; nếu muốn thực hiện hành động, hãy dùng statement expression hoặc block.

Một rule có nhiều câu lệnh được đặt trong `{ ... }`. Pattern variable `text` hay `number` chỉ dùng ở rule của chính nó; không có trạng thái “chảy” qua rule khác.

## 4. `switch statement` với colon group: chú ý `break`

```java
static void printValueWithColon(Object input) {
    switch (input) {
        case null:
            System.out.println("null");
            break;
        case String text:
            System.out.println(text.toUpperCase());
            break;
        case Integer number:
            System.out.println("integer");
            System.out.println(number + 1);
            break;
        default:
            System.out.println("other");
    }
}
```

Các nhánh được ngăn cách bằng dấu `:`. Từng nhóm sẽ chạy các câu lệnh phía sau nhãn cho đến khi gặp hành động thoát phù hợp hoặc đi tới cuối block. Dùng `break` để tránh vô tình chạy sang nhóm kế tiếp. Nhóm `default` ở cuối có thể hoàn thành khi tới `}` mà không cần `break`.

Không phải `break` là lựa chọn duy nhất. Trong method trả giá trị, `return` cũng kết thúc method; `throw` ném exception và không chạy tiếp bình thường. Với `switch statement` nằm trong vòng lặp, `continue` có thể chuyển sang lần lặp tiếp theo nếu hợp lệ. Khi đọc code legacy, điều quan trọng là xác định **nhóm nào có thể hoàn thành bình thường**.

## 5. Fall-through thật sự: chỉ nên dùng khi có chủ đích

Một ví dụ cổ điển với nhãn hằng số (không khai báo pattern variable):

```java
static String collect(int level) {
    StringBuilder result = new StringBuilder();

    switch (level) {
        case 1:
            result.append("first/");
            // fall through có chủ đích
        case 2:
            result.append("second");
            break;
        default:
            result.append("other");
    }
    return result.toString();
}
```

- `collect(1)` trả `"first/second"`: khớp `case 1`, chạy `append("first/")`, rồi đi tiếp vào các câu lệnh của `case 2`.
- `collect(2)` trả `"second"`: bắt đầu ở `case 2`.
- `collect(3)` trả `"other"`.

Với arrow rule, `case 1 -> ...` **không bao giờ** tự chạy sang `case 2 -> ...`. Nếu muốn nhiều nhãn có cùng hành vi, dùng nhãn gộp:

```java
static String category(int level) {
    return switch (level) {
        case 1, 2 -> "small";
        default -> "other";
    };
}
```

Trong colon group, hai nhãn hằng số đứng liền nhau cũng có thể chia sẻ hành vi:

```java
static String categoryWithColon(int level) {
    switch (level) {
        case 1:
        case 2:
            return "small";
        default:
            return "other";
    }
}
```

Đây là hai cách **gộp nhãn cùng xử lý**, khác với “đã chạy một phần code rồi mới fall-through”. Nên dùng gộp nhãn thay vì fall-through có chủ đích nếu không cần hiệu ứng tích lũy giữa các nhóm.

## 6. Vì sao pattern variable khiến colon fall-through nhạy cảm hơn?

Xét ví dụ **không biên dịch trên Java 21**:

```java
// Ví dụ cố ý sai:
static void invalid(Object value) {
    switch (value) {
        case String text:
            System.out.println("text=" + text);
            // Thiếu break!
        case Integer number:
            System.out.println(number + 1); // có thể tới đây khi value là String
            break;
        default:
            break;
    }
}
```

Nếu được phép fall-through như trên, một `String` có thể làm chương trình đi vào phần câu lệnh của `case Integer number` **mà pattern `Integer number` chưa từng khớp**. Khi đó `number` sẽ không có giá trị hợp lệ. Java 21 **cấm** trường hợp nhóm trước có thể hoàn thành bình thường và rơi vào nhóm bắt đầu bằng một pattern label khai báo pattern variable.

Một tình huống sai khác:

```java
// KHÔNG BIÊN DỊCH:
static void invalidSharedBody(Object value) {
    switch (value) {
        case String text:
        case Integer number:
            System.out.println(number); // một nhãn khác có thể chọn body này
            break;
        default:
            break;
    }
}
```

Với **colon statement group**, không được có một statement gắn với **nhiều switch label** khi một trong các label là pattern khai báo biến; Java không thể đảm bảo rằng mọi biến do các nhãn khác nhau khai báo đều đã được khởi tạo.

Hai hạn chế này nhắm tới **khả năng đi vào một pattern label có binding chưa khớp**. Chúng không có nghĩa rằng *mọi hình thức fall-through trong mọi `switch` chứa pattern* đều bị cấm. Nhưng trong thực tế, với pattern variables hãy ưu tiên **mỗi nhóm độc lập và thoát tường minh**, hoặc dùng arrow rule.

Cách sửa ví dụ đầu:

```java
static void valid(Object value) {
    switch (value) {
        case String text:
            System.out.println("text=" + text);
            break;
        case Integer number:
            System.out.println(number + 1);
            break;
        default:
            break;
    }
}
```

Hoặc đơn giản hơn, dùng `->` để không thể vô tình fall-through.

## 7. `when` và scope của biến pattern ở cả hai dạng

Guard `when` được xét **sau khi pattern khớp**. Vì vậy, biến được khai báo trong pattern có thể được dùng ở guard và thân nhánh.

Dạng arrow:

```java
static String arrowGuard(Object value) {
    return switch (value) {
        case null -> "missing";
        case String text when text.isBlank() -> "blank";
        case String text -> "text:" + text.strip();
        default -> "other";
    };
}
```

Dạng colon:

```java
static String colonGuard(Object value) {
    return switch (value) {
        case null:
            yield "missing";
        case String text when text.isBlank():
            yield "blank";
        case String text:
            yield "text:" + text.strip();
        default:
            yield "other";
    };
}
```

Cả hai method đều là ví dụ minh họa cần đặt trong class. Thứ tự nhánh quan trọng: `String text when text.isBlank()` xử lý trường hợp blank, còn `String text` không có guard đứng sau mới xử lý các chuỗi còn lại. Đảo thứ tự có thể dẫn tới **dominated case**: nhánh `String text` không guard đã bao phủ mọi chuỗi, nên nhánh `String ... when ...` phía sau không bao giờ được chọn và Java báo lỗi biên dịch.

Dù dùng cùng tên `text` ở hai nhánh, mỗi label giới thiệu một **pattern variable thuộc phạm vi tương ứng**. Không dùng `text` ở `default` hay ngoài toàn bộ switch chỉ vì một nhánh đã khai báo nó.

## 8. `switch expression` với arrow: giá trị trực tiếp hoặc block `yield`

`switch expression` phải tạo ra **một giá trị** hoặc kết thúc bất thường bằng cách ném exception. Với arrow, có thể viết rất gọn:

```java
static int length(Object value) {
    return switch (value) {
        case null -> 0;
        case String text -> text.length();
        case Integer number -> number;
        default -> -1;
    };
}
```

Ở đây `case String text -> text.length()` hợp lệ vì `switch` là **expression** và `text.length()` tạo `int`. Lưu ý đây không phải trường hợp `switch statement` với expression `text.length()` nằm sau `->`; ngữ cảnh quyết định cú pháp được phép.

Nếu cần nhiều thao tác trong một rule, dùng block và `yield`:

```java
static String normalize(Object value) {
    return switch (value) {
        case null -> "missing";
        case String text -> {
            String normalized = text.strip();
            yield normalized.isEmpty() ? "blank" : normalized;
        }
        default -> "other";
    };
}
```

`yield` gửi giá trị ra khỏi `switch expression`. Nếu thay `yield` bằng `break`, `switch expression` không nhận được kết quả cần thiết; nếu block có đường đi kết thúc bình thường mà không `yield` hoặc `throw`, trình biên dịch cũng từ chối.

## 9. `switch expression` với colon: không dùng `break` để trả kết quả

Dạng statement group có thể biểu diễn cùng logic:

```java
static String normalizeWithColon(Object value) {
    return switch (value) {
        case null:
            yield "missing";
        case String text:
            String normalized = text.strip();
            yield normalized.isEmpty() ? "blank" : normalized;
        default:
            yield "other";
    };
}
```

Trong `switch expression`, **`yield` trả giá trị**, còn `break` không được dùng như cách trả về giá trị cho switch. Đừng viết:

```java
// KHÔNG BIÊN DỊCH như switch expression:
static int wrong(Object value) {
    return switch (value) {
        case null:
            break; // không tạo ra kết quả cho expression
        default:
            yield 1;
    };
}
```

Colon group của một `switch expression` vẫn có thể cho phép fall-through giữa các nhãn hằng số phù hợp, nhưng mọi đường thực thi đều phải cuối cùng `yield` hoặc `throw`. Khi có pattern binding, các giới hạn fall-through của pattern vẫn cần được tuân thủ.

Nếu không có lý do cụ thể để dùng colon group, cú pháp arrow thường dễ kiểm tra hơn: mỗi nhánh tạo kết quả riêng, giảm rủi ro quên `yield`.

## 10. Pattern switch còn phải thỏa các quy tắc chung

Sự khác biệt giữa `->` và `:` không thay thế các quy tắc của *pattern matching for switch*:

1. **Exhaustiveness:** `switch expression` phải bao phủ các giá trị hợp lệ. Trong Java 21, một **enhanced switch statement** có pattern label hoặc `case null` cũng phải exhaustive. Với selector `Object`, dùng `default` hoặc một pattern bao phủ phù hợp.
2. **Dominance:** các label được xét theo thứ tự; một pattern rộng không guard ở trước có thể che hoàn toàn pattern hẹp ở sau. Ví dụ `case CharSequence c` trước `case String s` sẽ khiến nhánh `String` bị dominated.
3. **`null`:** type pattern như `case String s` không khớp `null`. Khi `switch` trên reference có thể nhận `null`, thêm `case null` nếu cần xử lý; `default` không mặc định xử lý selector `null`.
4. **Flow scope:** biến pattern chỉ được dùng trong guard và phần code có bằng chứng pattern tương ứng đã khớp; ở colon group phải đặc biệt cẩn trọng với các đường fall-through.
5. **Guard `when`:** chỉ được gắn với pattern label; `case String s when s.isBlank()` không tương đương kiểm tra mọi selector trước khi khớp kiểu. Để đến `s.isBlank()`, phép khớp `String s` đã thành công.
6. **Một kiểu switch block:** không pha trộn arrow rules và colon groups. Đây là lựa chọn cú pháp cho cả block, không phải tùy chọn riêng từng nhánh.

Khi một chương trình cần nhiều nhãn cho cùng hành vi mà không cần pattern variable, cân nhắc `case A, B -> ...` hoặc các nhãn hằng số cùng một colon group thay vì tạo fall-through khó theo dõi.

## 11. Chương trình đầy đủ, chạy được với JDK 21

Tạo file **`ArrowVsColonPatternDemo.java`**:

```java
public class ArrowVsColonPatternDemo {
    static String arrowExpression(Object value) {
        return switch (value) {
            case null -> "missing";
            case String s when s.isBlank() -> "blank";
            case String s -> "text:" + s.strip();
            case Integer n -> "number:" + n;
            default -> "other";
        };
    }

    static String colonExpression(Object value) {
        return switch (value) {
            case null:
                yield "missing";
            case String s when s.isBlank():
                yield "blank";
            case String s:
                yield "text:" + s.strip();
            case Integer n:
                yield "number:" + n;
            default:
                yield "other";
        };
    }

    static String arrowStatement(Object value) {
        StringBuilder output = new StringBuilder();
        switch (value) {
            case null -> output.append("missing");
            case String s when s.isBlank() -> output.append("blank");
            case String s -> output.append("text:").append(s.strip());
            case Integer n -> output.append("number:").append(n);
            default -> output.append("other");
        }
        return output.toString();
    }

    static String colonStatement(Object value) {
        String output;
        switch (value) {
            case null:
                output = "missing";
                break;
            case String s when s.isBlank():
                output = "blank";
                break;
            case String s:
                output = "text:" + s.strip();
                break;
            case Integer n:
                output = "number:" + n;
                break;
            default:
                output = "other";
        }
        return output;
    }

    static String fallthrough(int level) {
        StringBuilder output = new StringBuilder();
        switch (level) {
            case 1:
                output.append("first/");
                // fall through intentionally
            case 2:
                output.append("second");
                break;
            default:
                output.append("other");
        }
        return output.toString();
    }

    public static void main(String[] args) {
        Object[] values = {"  Java  ", "  ", 7, 4.5, null};

        for (Object value : values) {
            System.out.println(
                    arrowExpression(value) + " | " + colonExpression(value));
        }

        System.out.println("statement-arrow=" + arrowStatement("  A  "));
        System.out.println("statement-colon=" + colonStatement("  A  "));
        System.out.println("fallthrough-1=" + fallthrough(1));
        System.out.println("fallthrough-2=" + fallthrough(2));
    }
}
```

Biên dịch và chạy:

```bash
javac --release 21 ArrowVsColonPatternDemo.java
java ArrowVsColonPatternDemo
```

Không cần `--enable-preview` cho pattern matching switch trên Java 21. **Stdout chính xác:**

```text
text:Java | text:Java
blank | blank
number:7 | number:7
other | other
missing | missing
statement-arrow=text:A
statement-colon=text:A
fallthrough-1=first/second
fallthrough-2=second
```

Các điểm để đối chiếu:

- Hai `switch expression` chỉ khác kiểu tổ chức nhánh; cùng selector thì cùng kết quả. Arrow tạo giá trị qua expression; colon dùng `yield`.
- Hai `switch statement` cũng có cùng kết quả: arrow thực hiện statement expression mà không rơi xuống rule khác, còn colon dùng `break` để ngăn rơi xuống nhóm tiếp theo.
- `"  "` khớp `String s` nhưng guard `s.isBlank()` đúng, nên ra `blank`. `"  Java  "` ra `text:Java` sau `strip()`.
- `7` được boxing thành `Integer` khi đặt vào `Object[]`, khớp `case Integer n`; `4.5` boxing thành `Double`, đi vào `default`.
- `null` được bắt bởi `case null` để không gây `NullPointerException`.
- `fallthrough(1)` cố ý chạy tiếp tới code `case 2`; `fallthrough(2)` chỉ thực hiện code của `case 2`. Đây là `switch` theo **constant labels**, không vướng quy tắc ngăn fall-through vào pattern variable chưa được khởi tạo.

## 12. Checklist khi viết hoặc review `switch pattern`

- **Chọn statement hay expression trước:** cần hành động/side effect thì statement, cần một giá trị để gán/trả về thì expression.
- **Ưu tiên `->` cho code mới:** tránh fall-through không chủ ý, dễ nhìn đường đi và phạm vi pattern.
- **Với `:`, kiểm tra điểm kết thúc từng nhóm:** `break` trong statement, `yield` trong expression hoặc một lệnh thoát phù hợp; không giả định `break` sinh giá trị.
- **Kiểm tra pattern variable:** không cho phép fall-through từ nhóm trước vào một `case` khai báo pattern variable; không gộp nhiều label với cùng nhóm nếu một label khai báo biến pattern.
- **Kiểm tra thứ tự và guard:** đặt pattern có guard/hẹp trước nhánh rộng không guard, tránh dominance.
- **Bao phủ đầu vào:** xét `null`, `default` và yêu cầu exhaustiveness của enhanced switch.
- **Biên dịch ở đúng phiên bản:** dùng `javac --release 21` để xác nhận cú pháp Java 21; không lẫn với tính năng preview hoặc thay đổi ở JDK mới hơn.

**Kết luận:** `case ... ->` và `case ... :` đều hỗ trợ pattern switch trong Java 21, nhưng chúng mang **mô hình điều khiển luồng khác nhau**. Arrow rule là lựa chọn mặc định rõ ràng, không fall-through; colon group đòi hỏi theo dõi kỹ `break`/`yield` và phạm vi pattern variable. Hiểu sự khác nhau này giúp chuyển code `switch` cũ sang pattern matching mà không tạo lỗi biên dịch hoặc lỗi điều khiển luồng khó thấy.

### Tài liệu tham khảo

- [Oracle Java 21 — Switch Expressions and Statements](https://docs.oracle.com/en/java/javase/21/language/switch-expressions-and-statements.html)
- [Oracle Java 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html)
- [Java Language Specification 21 — §14.11, Switch Statement](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11)
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441)
