# Kiểu đích trong phép gán, lời gọi phương thức và `return` — kiểu kết quả của `switch`

> **Phạm vi:** Bài thuộc chủ đề Java 14, tập trung vào cách **biểu thức `switch`** xác định kiểu kết quả khi được đặt ở vị trí có kiểu đích. `switch` expression và `yield` đã là cú pháp Java chính thức từ Java 14 và tiếp tục được sử dụng ở Java hiện đại. Các ví dụ dùng cú pháp chuẩn từ Java 14, không sử dụng tính năng preview cũ hoặc phụ thuộc API đã lỗi thời.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Xác định **target type (kiểu đích)** của `switch` từ biến nhận kết quả, tham số của phương thức hoặc kiểu trả về của phương thức.
2. Hiểu vì sao `switch` ở các ngữ cảnh đó là **poly expression (biểu thức phụ thuộc ngữ cảnh)**, và khi nào nó là **standalone expression (biểu thức tự xác định kiểu)**.
3. Phân tích từng nhánh `case ... -> expression` hoặc `yield expression;` có tương thích với kiểu đích hay không.
4. Phân biệt target typing, chuyển đổi kiểu ngầm định, suy luận generic, boxing/unboxing và phép mở rộng/thu hẹp kiểu số.
5. Chỉ ra lỗi biên dịch khi một nhánh không thể chuyển sang kiểu đích, dù các nhánh khác hợp lệ.

Câu hỏi xuyên suốt là: **Khi cùng một `switch` nằm ở phép gán, tham số hoặc `return`, Java dùng thông tin kiểu ở bên ngoài để kiểm tra kết quả bên trong như thế nào?**

## 2. Hai khái niệm nền: target type và poly `switch`

**Target type** là kiểu mà ngữ cảnh xung quanh mong đợi. Ví dụ:

```java
String label = switch (status) {
    case 0 -> "NEW";
    default -> "DONE";
};
```

Trong khai báo này, `String` là target type `T`. Kết quả các nhánh phải tương thích với `String`; toàn bộ `switch` có kiểu `String`.

Theo **Java Language Specification (JLS) `15.28**, một `switch` expression là **poly expression** nếu nó xuất hiện trong **assignment context** hoặc **invocation context**. Khi ấy:

- Java truyền cùng loại ngữ cảnh và target type `T` xuống **các result expression** của `switch`.
- Mỗi result expression phải tương thích với `T` theo quy tắc chuyển đổi của loại ngữ cảnh đó.
- Kiểu của toàn bộ poly `switch` là **`T`**.
- Nếu một nhánh trả về giá trị không tương thích, chương trình **không biên dịch được**; Java không chọn kiểu chỉ dựa vào nhánh chắc chắn chạy ở thời điểm thực thi.

`return switch (...) { ... };` trong phương thức trả về một giá trị cũng được kiểm tra theo **kiểu trả về khai báo** của phương thức. JLS `14.17 quy định biểu thức trả về phải *assignment compatible* với kiểu trả về. Vì vậy, khi đọc code cần bắt đầu từ chữ ký phương thức để xác định `T`.

**Result expression** gồm: biểu thức ngay sau mũi tên `case ... -> ...`, hoặc biểu thức trong `yield ...;` của một block nhánh. Nếu nhánh chỉ `throw` ngoại lệ thì nó không cung cấp giá trị kết quả bình thường; đó là một cách kết thúc hợp lệ cho nhánh, miễn biểu thức `switch` thỏa các quy tắc còn lại.

**Phân biệt với kiểu của selector:** Trong `switch (status)`, `status` là **selector** dùng để chọn nhánh. Kiểu của `status` quyết định các `case` hợp lệ. Target type `String` ở bên ngoài lại quyết định **giá trị kết quả** được chấp nhận. Đây là hai câu hỏi khác nhau.

## 3. Bảng ba ngữ cảnh thường gặp

| Vị trí sử dụng | Ví dụ rút gọn | Kiểu đích `T` | Điều được kiểm tra |
| --- | --- | --- | --- |
| **Khởi tạo/gán biến** | `String s = switch (x) { ... };` | `String` | Mỗi kết quả nhánh gán được vào `String`. |
| **Đối số lời gọi phương thức** | `printName(switch (x) { ... });` | Kiểu tham số `String` của `printName(String)` | Mỗi kết quả nhánh tương thích với tham số được chọn. |
| **Biểu thức trong `return`** | `String name(int x) { return switch (x) { ... }; }` | Kiểu trả về khai báo `String` | Mỗi kết quả nhánh có thể trả về như một `String`. |

Với lời gọi phương thức **có overload**, compiler còn phải thực hiện chọn phương thức (`15.12`). Vì thế target type có thể phụ thuộc overload nào được chọn; đôi khi lời gọi trở nên **ambiguous**. Không tự suy luận rằng mọi overload sẽ chấp nhận một kết quả `switch` chỉ vì một nhánh có kiểu phù hợp.

### 3.1. Trong phép gán

```java
String result = switch (code) {
    case 200 -> "OK";
    case 404 -> "NOT_FOUND";
    default -> "OTHER";
};
```

Kiểu `String` có sẵn từ vế trái. Không cần gán trước thành một biến `Object` rồi ép kiểu trở lại; compiler có thể kiểm tra trực tiếp từng nhánh đối với `String`.

Điều này cũng áp dụng khi gán lại:

```java
String result;
result = switch (code) {
    case 200 -> "OK";
    default -> "ERROR";
};
```

**Lưu ý:** `int code` ở ví dụ không quyết định kiểu kết quả. `code` vẫn là selector có kiểu `int`, còn kết quả `switch` có kiểu `String`.

### 3.2. Trong lời gọi phương thức

```java
static void display(String message) {
    System.out.println(message);
}

static void example(int code) {
    display(switch (code) {
        case 200 -> "Success";
        default -> "Failure";
    });
}
```

Với phương thức `display(String)`, kiểu tham số `String` đóng vai trò target type cho `switch`. Không cần tạo biến trung gian để «giúp compiler đoán». Nếu một nhánh trả về một kiểu không có chuyển đổi invocation phù hợp sang `String` thì lời gọi không biên dịch.

Ở lời gọi generic như `accept(List<String>)`, target type còn có thể truyền xuống các biểu thức generic ở nhánh, hỗ trợ suy luận type argument. Đừng lẫn **suy luận kiểu nhánh** với **chọn overload**: compiler phải thỏa toàn bộ quy tắc áp dụng của lời gọi phương thức.

### 3.3. Trong `return`

```java
static String toLabel(int code) {
    return switch (code) {
        case 200 -> "OK";
        case 404 -> "Missing";
        default -> "Unknown";
    };
}
```

Kiểu trả về đã khai báo của `toLabel` là `String`; các kết quả của `switch` phải tương thích với `String`. Nếu sửa riêng nhánh `default` thành `42`, phương thức sẽ có **lỗi biên dịch**, kể cả nếu bạn chỉ dự định gọi phương thức với `code == 200`. Compiler kiểm tra *mọi* result expression có thể xuất hiện trong biểu thức.

**Không dùng `return` bên trong một block nhánh để cung cấp giá trị cho `switch`:** `return` rời khỏi phương thức hoặc lambda bao ngoài và không thay thế `yield`; JLS còn hạn chế vị trí `return` nằm trong `switch` expression. Hãy dùng `case ... -> value` hoặc `yield value;`.

## 4. Chương trình Java hoàn chỉnh: cả ba ngữ cảnh

Lưu file dưới tên **`SwitchTargetTypes.java`**:

```java
import java.util.List;

public class SwitchTargetTypes {
    static void display(String message) {
        System.out.println("argument=" + message);
    }

    static String labelOf(int mode) {
        return switch (mode) {
            case 0 -> "zero";
            case 1 -> {
                String computed = "one";
                yield computed;
            }
            default -> "other";
        };
    }

    static List<String> tagsOf(int mode) {
        return switch (mode) {
            case 0 -> List.of();
            default -> List.of("java", "switch");
        };
    }

    public static void main(String[] args) {
        int mode = 1;

        String assigned = switch (mode) {
            case 0 -> "zero";
            case 1 -> "one";
            default -> "other";
        };
        System.out.println("assignment=" + assigned);

        display(switch (mode) {
            case 0 -> "zero";
            default -> "one";
        });

        System.out.println("return=" + labelOf(mode));

        byte compact = switch (mode) {
            case 0 -> 10;
            default -> 20;
        };
        System.out.println("byte=" + compact);

        List<String> generic = switch (mode) {
            case 0 -> List.of();
            default -> List.of("java", "switch");
        };
        System.out.println("generic=" + generic);

        System.out.println("return-generic=" + tagsOf(mode));

        var inferred = switch (mode) {
            case 0 -> 10;
            default -> 20;
        };
        System.out.println("standalone=" + inferred);
    }
}
```

Biên dịch/chạy trên JDK 17+ có hỗ trợ Java 14, hoặc trực tiếp trên bản JDK hiện hành đã chọn:

```bash
javac --release 14 SwitchTargetTypes.java
java SwitchTargetTypes
```

**Stdout chính xác:**

```text
assignment=one
argument=one
return=one
byte=20
generic=[java, switch]
return-generic=[java, switch]
standalone=20
```

Đọc lần lượt:

1. **`assignment`** có kiểu `String` nên kết quả mọi nhánh được kiểm tra với `String`.
2. **`display(...)`** truyền `switch` trực tiếp vào tham số `String`, thuộc invocation context.
3. **`labelOf(...)`** dùng `return switch`; `yield computed` đưa giá trị `String` của block về `switch`, rồi phương thức trả kết quả ấy.
4. **`compact`** có target type `byte`; từng literal `10`/`20` là hằng `int` nằm trong phạm vi của `byte` và được phép thu hẹp theo quy tắc assignment context.
5. **`generic`** và **`tagsOf`** dùng target type `List<String>`; các lời gọi `List.of()` và `List.of("java", "switch")` được suy luận generic phù hợp với target type.
6. Với **`var inferred`**, không có kiểu biến khai báo trước để làm target `T`; `switch` được xem là standalone expression. Cả hai nhánh là `int` nên kiểu suy luận của `inferred` là `int`.

Code không cần `--enable-preview`; Java 14 đã chuẩn hóa switch expression. Với một dự án production, dùng toolchain Java hiện đang được bảo trì; `--release 14` ở đây chỉ phục vụ kiểm chứng tính tương thích ngược theo bài học.

## 5. Vì sao `byte` hợp lệ trong một trường hợp và lỗi trong trường hợp khác?

Xét đoạn sau:

```java
int choice = 1;

byte direct = switch (choice) {
    case 0 -> 10;
    default -> 20;
};
```

Vì `switch` là poly expression trong assignment context có target `byte`, mỗi kết quả nhánh là hằng số `int` biểu diễn được bằng `byte`, nên được **constant narrowing conversion** cho phép. Kiểu của cả `switch` là `byte`.

Bây giờ xét:

```java
int choice = 1;

var intermediate = switch (choice) {
    case 0 -> 10;
    default -> 20;
};

// byte later = intermediate; // LỖI: intermediate có kiểu int.
```

`var` không mang sẵn target type cụ thể cho initializer. `switch` đứng độc lập, hai nhánh `int` nên suy luận thành `int`. Sau đó gán **biến `int` không phải hằng** vào `byte` là phép thu hẹp không được thực hiện ngầm. Không suy luận rằng vì `10`/`20` nằm trong phạm vi `byte` nên mọi đường gán tiếp theo đều hợp lệ.

**Một biên giới cần nhớ:** `switch` expression **không phải constant expression theo JLS `15.29**, nên không thể áp dụng quy tắc thu hẹp hằng số cho một `switch` standalone như thể cả biểu thức là một integer literal.

Ví dụ lỗi ngay ở poly `switch`:

```java
int choice = 1;

// Không biên dịch: 128 ngoài phạm vi của byte.
byte invalid = switch (choice) {
    case 0 -> 10;
    default -> 128;
};
```

Compiler kiểm tra từng nhánh đối với `byte`; không thể bỏ qua nhánh `default` vì biết `choice` hiện đang bằng `1`. Nếu bài toán cần giá trị ngoài phạm vi `byte`, chọn kiểu đích đủ rộng (như `int`), thay vì cố ép kiểu gây mất dữ liệu.

## 6. Standalone `switch` khác poly `switch` thế nào?

Nếu `switch` **không** nằm trong assignment hoặc invocation context thì nó là standalone expression và phải xác định kiểu dựa vào các result expression của chính nó. JLS `15.28 nêu quy tắc lần lượt:

1. Nếu mọi result expression có **cùng kiểu**, kiểu đó là kiểu của `switch`.
2. Nếu tất cả có kiểu `boolean` hoặc `Boolean`, unboxing khi cần để có kiểu `boolean`.
3. Nếu các result expression đều chuyển được sang kiểu số, áp dụng **general numeric promotion**.
4. Trong trường hợp còn lại, boxing các primitive nếu cần và xác định kiểu chung thông qua **least upper bound** (LUB) của các kiểu tham chiếu.

Ví dụ standalone:

```java
int code = 1;

var value = switch (code) {
    case 0 -> (byte) 7;
    default -> (short) 9;
};

// value có kiểu int vì numeric promotion.
int doubled = value * 2;
System.out.println(doubled);
```

**Stdout:**

```text
18
```

Dù các nhánh lần lượt có kiểu `byte` và `short`, phép numeric promotion trong standalone `switch` dẫn tới `int`. Ngược lại, khi khai báo `byte value = switch ...` và các kết quả nhánh phù hợp, compiler sẽ áp dụng quy tắc assignment context theo target type `byte`.

**Không đánh đồng hai thao tác:** một là xác định kiểu của một **poly expression** bằng target `T`; hai là xác định kiểu một **standalone expression** rồi xem nó có được chuyển đổi sang kiểu mà ngữ cảnh ngoài yêu cầu hay không.

Đặc biệt, khi bọc `switch` trong biểu thức khác như phép toán số học, phép cast hoặc lời gọi khác, cần kiểm tra **ngữ cảnh trực tiếp của chính biểu thức `switch`**, không chỉ nhìn kiểu của biến ở rất xa ngoài cùng. Ví dụ `int x = 1 + switch (...) { ... };` khiến `switch` nằm trong numeric context của phép `+`, thay vì trực tiếp là phép gán vào `int`. Các quy tắc tính kiểu có thể khác với `int x = switch (...) { ... };`.

## 7. Kiểu tham chiếu, `null` và generic

### 7.1. `null` hợp lệ khi target là kiểu tham chiếu

```java
String message = switch (flag) {
    case 0 -> "ready";
    default -> null;
};
```

Target `String` cho phép một nhánh trả `null`. **Điều này không có nghĩa kết quả an toàn để dereference:** nếu nhánh `default` được chọn thì `message.length()` có thể ném `NullPointerException`.

Ngược lại:

```java
int amount = switch (flag) {
    case 0 -> 10;
    // default -> null; // LỖI: null không gán được cho primitive int.
    default -> 20;
};
```

Target là primitive `int`, nên `null` không tương thích. Nếu nhánh trả wrapper `Integer` và compiler unbox sang `int`, giá trị wrapper `null` vẫn có thể gây `NullPointerException` khi thực thi. Tính hợp lệ về kiểu không đồng nghĩa không thể có lỗi runtime.

### 7.2. Các nhánh không cần có cùng kiểu cụ thể

```java
Object value = switch (flag) {
    case 0 -> 123;
    default -> "ready";
};
```

Target `Object` cho phép `int` được boxing thành `Integer` và `String` widening lên `Object`. Compiler không đòi mọi nhánh đều là `String` hoặc đều là `Integer`; **nó đòi từng nhánh tương thích với target**.

Tuy nhiên:

```java
// LỖI: nhánh 123 không tương thích với String.
String value = switch (flag) {
    case 0 -> 123;
    default -> "ready";
};
```

Java **không tự gọi** `String.valueOf(123)` và cũng không áp dụng phép nối chuỗi ngầm trong phép gán kiểu `String`. Nếu muốn hiển thị số, trả về `"123"` hoặc chuyển đổi một cách tường minh trong chính nhánh đó.

### 7.3. Target type giúp suy luận generic

```java
import java.util.List;

class GenericSwitch {
    static List<String> names(int kind) {
        return switch (kind) {
            case 0 -> List.of();
            default -> List.of("Ann", "Binh");
        };
    }
}
```

Trong `return` này, target type là `List<String>`. Lời gọi generic `List.of()` ở nhánh đầu không tự có phần tử nào để suy ra từ giá trị; target type giúp suy luận thành kết quả tương thích `List<String>`.

Đối với kiểu generic phức tạp, **không dùng `var` như một công cụ ép compiler suy ra đúng kiểu bạn mong muốn**. Nếu cần hợp đồng rõ ràng cho API hoặc biến, khai báo kiểu cụ thể như `List<String>` và kiểm tra cảnh báo unchecked conversion, wildcard và các ràng buộc generic.

## 8. `yield` trong block: kiểu đích vẫn đi tới giá trị được tạo

Dùng block khi một nhánh cần nhiều câu lệnh trước khi tạo kết quả:

```java
static String describe(int level) {
    return switch (level) {
        case 0 -> "low";
        case 1 -> {
            String prefix = "mid";
            yield prefix.toUpperCase();
        }
        default -> {
            String prefix = "high";
            yield prefix.toUpperCase();
        }
    };
}
```

Mỗi `yield expression;` là kết quả của `switch`, nên đều phải phù hợp với target type `String` từ `return`. `yield` kết thúc nhánh với một **giá trị**; bản thân nó không thay thế `return` của phương thức bao ngoài.

Đoạn sau có lỗi vì block đi đến cuối mà không `yield`/`throw`:

```java
// LỖI BIÊN DỊCH:
String name = switch (code) {
    case 0 -> {
        System.out.println("processing");
        // thiếu yield hoặc throw
    }
    default -> "other";
};
```

Sửa đúng:

```java
String name = switch (code) {
    case 0 -> {
        System.out.println("processing");
        yield "zero";
    }
    default -> "other";
};
```

Một nhánh `case 0 -> throw new IllegalArgumentException("bad");` cũng hợp lệ: nhánh này kết thúc bằng ngoại lệ, không có giá trị được trả về bình thường để chuyển sang target type. Các nhánh còn lại vẫn phải đáp ứng quy tắc kiểm tra kiểu.

## 9. Điều kiện biên dịch không phụ thuộc nhánh chạy thực tế

Một `switch` expression cần **exhaustive**: phải bao phủ mọi trường hợp selector có thể chọn theo quy tắc của loại selector. Các ví dụ `int` trong bài dùng `default` để đảm bảo có nhánh kết quả cho mọi giá trị.

Có thể viết:

```java
static String state(int code) {
    return switch (code) {
        case 0 -> "NEW";
        case 1 -> "DONE";
        default -> throw new IllegalArgumentException("Unsupported: " + code);
    };
}
```

Đây là cách diễn đạt rõ ràng: giá trị `0`/`1` cho kết quả `String`, các giá trị khác từ chối bằng ngoại lệ. Không cần tạo chuỗi giả hoặc trả `null` chỉ để làm đầy các nhánh.

Nếu chuyển sang `switch` với enum hoặc pattern, phải áp dụng đúng quy tắc exhaustive tương ứng **của Java release đang dùng**. Các ví dụ của bài cố ý sử dụng selector `int` và cú pháp `case ... ->` tiêu chuẩn, tránh tính năng preview hoặc phụ thuộc sự khác biệt giữa các release mới.

## 10. Lỗi thường gặp và cách đọc lỗi compiler

| Lỗi tư duy | Ví dụ hoặc biểu hiện | Cách khắc phục |
| --- | --- | --- |
| Nghĩ kiểu selector cũng là kiểu kết quả | `switch (intCode)` mà cố trả kết quả `int` | Tách selector `intCode` khỏi target type của kết quả (ví dụ `String`). |
| Chỉ xét một nhánh đang chạy | `String s = switch (...) { case 0 -> "ok"; default -> 42; };` | Mọi result expression đều phải tương thích target `String` ở compile time. |
| Trộn `return` và `yield` | `return` bên trong block nhằm «trả giá trị switch» | Dùng `yield` trong nhánh, đặt `return switch (...)` ở ngoài. |
| Quên kết quả của block | `case 0 -> { doWork(); }` trong switch expression | Thêm `yield value;` hoặc kết thúc nhánh bằng `throw`. |
| Nhầm `var` với target typing | `var x = switch (...) { ... };` rồi mong x có kiểu khai báo tùy ý | `var` suy luận từ kiểu standalone `switch`; khai báo biến có kiểu cụ thể nếu cần target. |
| Cho rằng mọi số nhỏ tự gán vào `byte` | Gán `int` biến sang `byte` mà không cast | Phân biệt narrowing của *hằng* trong assignment với chuyển đổi từ biến `int`. |
| Nghĩ Java tự đổi mọi thứ thành `String` | Một nhánh trả `int`, target `String` | Chuyển sang chuỗi tường minh hoặc sửa target type. |
| Bỏ qua overload | Truyền `switch` vào nhiều overload có tham số cùng phù hợp | Xem từng overload và quy tắc phân giải lời gọi; có thể cần chỉ rõ kiểu. |
| Bỏ qua `null` và unboxing | Target `int` nhưng nhánh trả `Integer` có thể `null` | Đảm bảo giá trị không null hoặc xử lý trước khi unbox. |

Khi có lỗi compiler, thử phân tích theo thứ tự: **ngữ cảnh trực tiếp → target type `T` → từng result expression → conversion được phép → exhaustive/flow control**. Cách này tìm nguyên nhân nhanh hơn việc thêm cast vào từng nhánh mà không hiểu hợp đồng kiểu.

## 11. Bài tập tự kiểm tra

**Bài 1 — Dự đoán kiểu và kết quả**

```java
int k = 0;
byte a = switch (k) { case 0 -> 5; default -> 7; };
var b = switch (k) { case 0 -> 5; default -> 7; };
System.out.println(a + ":" + b);
```

**Đáp án:** `a` có kiểu `byte` nhờ target của phép gán và cả hai hằng `int` tương thích `byte`; `b` có kiểu `int` do standalone switch trong `var`. Stdout: `5:5`.

**Bài 2 — Nhánh nào làm chương trình không biên dịch?**

```java
String s = switch (k) {
    case 0 -> "zero";
    case 1 -> null;
    default -> 2;
};
```

**Đáp án:** `default -> 2` vì `int` không chuyển ngầm sang `String`. `null` vẫn gán được cho kiểu tham chiếu `String`, dù cần cân nhắc rủi ro runtime.

**Bài 3 — Mục đích của `yield`**

```java
static int measure(int k) {
    return switch (k) {
        case 0 -> 0;
        default -> {
            int x = k * 2;
            yield x;
        }
    };
}
```

**Đáp án:** `yield x` gửi giá trị `int` từ block nhánh về `switch`; `return` ở ngoài gửi kết quả `switch` ra khỏi phương thức. `measure(3)` trả `6`.

**Bài 4 — Đối số phương thức và kiểu đích**

```java
static void takeNumber(Number number) { }

static void test(int k) {
    takeNumber(switch (k) {
        case 0 -> 10;
        default -> 3.5;
    });
}
```

**Đáp án:** Lời gọi `takeNumber(Number)` cung cấp target type `Number` cho poly `switch`; mỗi nhánh có thể boxing (`int` thành `Integer`, `double` thành `Double`), đều là subtype của `Number`. Chú ý: điều này khác kiểu của standalone `switch` với hai giá trị số, vốn áp dụng numeric promotion.

**Bài 5 — Code có chạy với Java 14 không?**

Chương trình `SwitchTargetTypes.java` ở mục 4 dùng `case ... ->`, `yield`, `var` và `List.of()`. Hãy dựa trên các mốc cú pháp/API và thử `javac --release 14` với compiler hỗ trợ.

**Đáp án:** Các cấu trúc này đều nằm trong bộ Java 14 chính thức: `switch` expression và `yield` chuẩn từ Java 14, `var` từ Java 10 và `List.of()` từ Java 9. Do vậy chương trình không cần bật preview. Kiểm chứng bằng build/test thực tế vẫn cần để phát hiện các phụ thuộc khác ngoài ví dụ.

## 12. Nguồn đặc tả chính thức và cách tra cứu tiếp

- [Java Language Specification — `15.28 Switch Expressions (Java SE 25)](https://docs.oracle.com/javase/specs/jls/se25/html/jls-15.html#jls-15.28): điều kiện poly/standalone, định nghĩa result expression và cách xác định kiểu.
- [JLS `5.2 Assignment Contexts (Java SE 25)](https://docs.oracle.com/javase/specs/jls/se25/html/jls-5.html#jls-5.2): các phép chuyển kiểu gán, kể cả narrowing của literal hằng trong phạm vi đích.
- [JLS `5.3 Invocation Contexts (Java SE 25)](https://docs.oracle.com/javase/specs/jls/se25/html/jls-5.html#jls-5.3): chuyển kiểu đối số phương thức; đọc cùng [`15.12 Method Invocation](https://docs.oracle.com/javase/specs/jls/se25/html/jls-15.html#jls-15.12) khi có overload.
- [JLS `14.17 Return Statement (Java SE 25)](https://docs.oracle.com/javase/specs/jls/se25/html/jls-14.html#jls-14.17): tính tương thích của biểu thức trả về với kiểu return khai báo.
- [JLS `15.29 Constant Expressions (Java SE 25)](https://docs.oracle.com/javase/specs/jls/se25/html/jls-15.html#jls-15.29): xác định vì sao `switch` không phải constant expression.
- [JLS Java SE 14](https://docs.oracle.com/javase/specs/jls/se14/html/index.html): đối chiếu cú pháp nếu cần nhắm đến Java 14.
- [Oracle JDK migration guide — thay đổi trong Java 14](https://docs.oracle.com/en/java/javase/24/migrate/significant-changes-jdk-14.html): xác nhận `switch` expression được chuẩn hóa, không còn là preview từ Java 14.

**Ghi nhớ khi review:** Đối với `switch` expression, hãy xác định **target type của phép gán, tham số hoặc `return`**, rồi xét *từng nhánh tạo kết quả*. Nếu không có target theo hai loại ngữ cảnh JLS quy định, chuyển sang quy tắc xác định kiểu standalone.