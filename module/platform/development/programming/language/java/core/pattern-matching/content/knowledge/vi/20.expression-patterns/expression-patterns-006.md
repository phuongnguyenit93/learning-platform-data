# `yield` trong `switch expression` (Java 21+)

## 1. Vai trò của `yield`

Từ Java 14 (JEP 361), `switch` có thể được dùng như một **biểu thức** (*switch expression*) trả ra giá trị, thay vì chỉ là một câu lệnh điều khiển. Kết quả đó có thể gán cho biến, truyền làm đối số hoặc trả về từ phương thức:

~~~java
int score = 85;
String grade = switch (score / 10) {
    case 10, 9 -> "A";
    case 8 -> "B";
    default -> "C";
};
System.out.println(grade); // B
~~~

Với nhánh `case X -> expression;`, biểu thức bên phải dấu `->` được đánh giá và trở thành kết quả của toàn bộ switch expression; **không cần viết `yield`**.

Nhưng một nhánh có thể cần chạy nhiều câu lệnh trước khi có kết quả: khai báo biến, xử lý trung gian, kiểm tra dữ liệu, hoặc các nhánh `if`. Khi đó dùng `-> { ... }` và **`yield value;`** để cấp giá trị cho switch expression bao quanh:

~~~java
int score = 85;
String grade = switch (score / 10) {
    case 10, 9 -> "A";
    case 8 -> {
        String label = "B";
        yield label;
    }
    default -> "C";
};
System.out.println(grade); // B
~~~

Trong block `case 8`, lệnh `yield label;` kết thúc **switch expression**, không kết thúc phương thức bao ngoài. Phương thức vẫn có thể tiếp tục thực thi sau khi biểu thức đã tính ra giá trị.

**Phiên bản:** `yield` và switch expression ổn định từ Java 14. Type patterns, record patterns và guard `when` trong `switch` ổn định từ **Java 21** (JEP 441/JEP 440). Bài này dùng **JDK 21+** để minh họa đồng thời các khả năng đó; không cần `--enable-preview`.

## 2. Ba dạng nhánh trong switch expression mũi tên

| Dạng nhánh | Khi nào dùng | Hành vi |
| --- | --- | --- |
| `case X -> expression;` | Chỉ cần một biểu thức | Lấy giá trị expression, không có `yield` |
| `case X -> { ... yield value; }` | Cần nhiều câu lệnh | `yield` cấp giá trị cho switch expression |
| `case X -> throw new ...;` | Nhánh dữ liệu lỗi | Ném exception, không cần cấp giá trị |

Ví dụ:

~~~java
int quantity = 3;
String message = switch (quantity) {
    case 0 -> "Hết hàng";
    case 1 -> "Một sản phẩm";
    case 2, 3 -> {
        String detail = "Số lượng: " + quantity;
        yield detail;
    }
    default -> throw new IllegalArgumentException("Ngoài phạm vi");
};
System.out.println(message); // Số lượng: 3
~~~

`yield` là một **statement** có cú pháp `yield <expression>;`; biểu thức của `yield` không được có kiểu `void`. Vì vậy:

~~~java
// Các case rời dưới đây minh họa cú pháp, không phải chương trình độc lập.

// SAI: yield là statement, không được đặt trực tiếp sau mũi tên.
// case 2 -> yield "Hai";

// ĐÚNG, biểu thức trực tiếp:
case 2 -> "Hai";

// ĐÚNG, block có yield:
case 2 -> {
    yield "Hai";
}
~~~

Nếu không cần biến trung gian hoặc logic nhiều dòng, ưu tiên nhánh expression vì ngắn và dễ hiểu.

## 3. Phân biệt `yield`, `return`, `break` và `throw`

- **`yield result;`**: chuyển `result` thành kết quả của **switch expression gần nhất** bao ngoài. Đây là công việc của `yield`.
- **`return result;`**: trả giá trị từ **phương thức hoặc lambda** chứa nó. `return` không dùng thay `yield` để nhảy xuyên qua switch expression.
- **`break;`**: kết thúc vòng lặp hoặc switch **statement** theo cấu trúc hợp lệ, không cung cấp kết quả cho switch expression. Không thể dùng `break` để thoát khỏi switch expression đang cần giá trị.
- **`throw exception;`**: làm việc đánh giá kết thúc bất thường. Một nhánh có thể `throw` thay cho `yield` vì không có đường thực thi bình thường cần giá trị.

So sánh hai phương thức:

~~~java
static String withMoreWork(int level) {
    String name = switch (level) {
        case 1 -> "Cơ bản";
        case 2 -> {
            yield "Nâng cao";
        }
        default -> "Khác";
    };
    return "Cấp độ: " + name;
}

static String returnSwitch(int level) {
    return switch (level) {
        case 1 -> "Cơ bản";
        case 2 -> {
            yield "Nâng cao";
        }
        default -> "Khác";
    };
}
~~~

`withMoreWork(2)` trả `"Cấp độ: Nâng cao"`: sau `yield`, Java tiếp tục lệnh `return "Cấp độ: " + name;`. `returnSwitch(2)` trả `"Nâng cao"`: `return` áp dụng cho **toàn bộ switch expression** sau khi nhánh đã tạo ra giá trị.

Không nhầm `yield` với việc trả kết quả của phương thức hay với câu lệnh `break` của switch statement truyền thống.

## 4. Tất cả đường đi bình thường phải có giá trị

Một switch expression phải có kiểu kết quả, và nhánh được chọn **không được kết thúc bình thường mà không trả ra giá trị**. Các đường thực thi trong một block phải đi đến `yield`, hoặc kết thúc bất thường như `throw`.

Ví dụ đúng:

~~~java
static String sign(int n) {
    return switch (n) {
        case 0 -> "zero";
        default -> {
            if (n > 0) {
                yield "positive";
            } else {
                yield "negative";
            }
        }
    };
}
~~~

Cả hai nhánh của `if` đều `yield`. Ngược lại, đoạn sau **cố ý không biên dịch**:

~~~java
int result = switch (1) {
    case 1 -> {
        int value = 10;
        System.out.println(value);
        // Thiếu yield hoặc throw, block có thể kết thúc bình thường.
    }
    default -> 0;
};
~~~

Sửa bằng cách thêm `yield value;` sau `println`. Nếu có đường dẫn lỗi, có thể sử dụng `throw`:

~~~java
int size = 4;
int result = switch (size) {
    case 0 -> 0;
    default -> {
        if (size < 0) {
            throw new IllegalArgumentException("size âm");
        }
        yield size * 3;
    }
};
System.out.println(result); // 12
~~~

Ở đường bình thường `size >= 0`, block tạo giá trị `size * 3`; ở đường size âm, nó ném exception. **Không được** viết `yield System.out.println("x");` vì `println` có kiểu `void`. Hãy gọi `println` riêng rồi `yield` một giá trị thích hợp.

## 5. Kết hợp `yield` với type pattern trong `case` (Java 21)

Pattern matching cho `switch` cho phép kiểm tra kiểu đối tượng và giới thiệu pattern variable ngay trong nhãn `case`. Khi đã khớp, biến có thể dùng ở guard và block tương ứng:

~~~java
static String describe(Object input) {
    return switch (input) {
        case String text -> {
            String clean = text.strip();
            yield "Văn bản: " + clean;
        }
        case Integer number -> {
            int doubled = number * 2;
            yield "Số nhân đôi: " + doubled;
        }
        case null -> "Không có dữ liệu";
        default -> "Loại khác";
    };
}
~~~

- `case String text` chỉ khớp khi `input` là `String` và khác `null`. `text` có kiểu tĩnh `String` trong block.
- `case Integer number` ràng buộc biến `number` kiểu `Integer` ở nhánh khác.
- `yield` trả chuỗi kết quả; nó **không** kiểm tra kiểu và **không** ràng buộc pattern variable.
- Mỗi biến pattern có phạm vi ở nhánh của chính nó; `text` không còn trong phạm vi của `case Integer number`.

Cần **`case null`** nếu selector có thể null và muốn xử lý có chủ đích. Với switch expression trên reference type, `default` không tự bắt null; không có `case null` thì input null thường gây `NullPointerException`.

## 6. Guard `when`, thứ tự pattern và `yield`

Guard `when` thêm điều kiện vào một case pattern. Ví dụ phân biệt chuỗi trắng với chuỗi thông thường:

~~~java
static String label(Object input) {
    return switch (input) {
        case String s when s.isBlank() -> {
            yield "Chuỗi trắng";
        }
        case String s -> {
            String normalized = s.strip();
            yield "Nội dung: " + normalized;
        }
        case null -> "null";
        default -> "Khác";
    };
}
~~~

Quy trình: Java kiểm tra `input` có là `String` không, rồi mới đánh giá `s.isBlank()`. Nếu guard đúng, vào block đầu; nếu guard sai, tiếp tục tìm case phù hợp và có thể khớp `case String s` ở dưới.

**Thứ tự quan trọng:** `case String s when s.isBlank()` phải đứng **trước** `case String s` không có guard. Nếu đặt mẫu String tổng quát trước, nó che mẫu cụ thể và có thể gây lỗi dominance lúc biên dịch.

Có thể kết hợp nhánh `-> expression` và `-> { ... yield ...; }` trong cùng một switch expression kiểu mũi tên; chỉ cần dùng block ở nhánh thực sự có nhiều bước.

## 7. `yield` sau khi tách record pattern

Record pattern của Java 21 cho phép tách giá trị các component ngay trong `case`:

~~~java
record Point(int x, int y) {}

static String formatPoint(Object obj) {
    return switch (obj) {
        case Point(int x, int y) when x == y -> {
            int total = x + y;
            yield "Điểm chéo, tổng = " + total;
        }
        case Point(var x, var y) -> "Điểm (" + x + ", " + y + ")";
        case null -> "null";
        default -> "Không phải Point";
    };
}
~~~

`x` và `y` của nhánh đầu được ràng buộc từ hai component của `Point`, dùng được trong `when x == y` và trong block. `yield` cấp chuỗi kết quả được tính từ chúng. Nhánh thứ hai sử dụng `var` để suy luận `x` và `y` có kiểu `int`, trả expression trực tiếp.

Trong bài này:

- Record pattern: quyết định đối tượng có khớp cấu trúc record và ràng buộc component hay không.
- Guard: điều kiện bổ sung trên dữ liệu đã tách.
- Yield: chỉ **tạo giá trị trả ra từ switch expression** khi đã chọn nhánh.
- Nhánh tổng quát `Point(var x, var y)` nằm sau nhánh có guard để tránh che nhánh cụ thể.

Với component kiểu tham chiếu, `var` có thể nhận `null`. Đừng mặc định mọi component đã được tách đều khác null; nếu cần gọi phương thức của component, hãy kiểm tra trước khi dùng.

## 8. Dạng `case: ... yield` và khác biệt với switch statement

Ngoài cú pháp mũi tên, switch expression hỗ trợ nhóm nhãn dấu hai chấm và `yield`:

~~~java
int n = 2;
int value = switch (n) {
    case 0:
        yield 0;
    case 1, 2:
        yield n * 10;
    default:
        yield -1;
};
System.out.println(value); // 20
~~~

Những case này thuộc một **switch expression** vì toàn bộ `switch (n) { ... }` được gán cho `value`. Các nhánh dùng `:` cần cung cấp kết quả qua `yield`. Cách viết dấu hai chấm có luật điều khiển luồng truyền thống và dễ gây nhầm lẫn về fall-through, nên code mới thường ưu tiên `case ... -> ...`.

**Không trộn** nhãn `case X:` và quy tắc `case Y ->` trong cùng một switch block. Chọn một dạng nhất quán.

So với **switch statement**:

~~~java
int n = 2;
switch (n) {
    case 2:
        System.out.println("Hai");
        break;
    default:
        System.out.println("Khác");
}
~~~

Ở đây `break` chỉ kết thúc switch statement. Không có giá trị của toàn bộ `switch` để gán cho biến, và `yield` không phải cách để trả giá trị từ switch statement.

## 9. Exhaustiveness, kiểu kết quả và switch lồng nhau

**Tính bao quát (exhaustiveness):** switch expression phải xử lý đầy đủ các trường hợp mà bộ kiểm tra kiểu Java xem là có thể xuất hiện. Với selector `Object`, thường cần `default` cho các kiểu chưa liệt kê; có thể cần `case null` để xử lý riêng null. Với enum hoặc hệ sealed có các nhánh đã bao trùm hết, `default` đôi khi không cần thiết theo luật exhaustiveness.

**Kiểu giá trị:** các nhánh của switch expression phải trả giá trị phù hợp kiểu kết quả của biểu thức. Ví dụ:

~~~java
static double asDouble(Object input) {
    return switch (input) {
        case Integer n -> n.doubleValue();
        case Double d -> {
            yield d;
        }
        case null -> 0.0;
        default -> -1.0;
    };
}
~~~

Mọi nhánh tạo giá trị đều phù hợp với `double`. Với nhánh từ chối dữ liệu có thể dùng `throw` mà không cần tạo giá trị.

**Switch expression lồng nhau:** `yield` luôn hướng đến switch expression **gần nhất** mà nó nằm trong:

~~~java
int outer = 1;
int inner = 2;

int answer = switch (outer) {
    case 1 -> {
        int part = switch (inner) {
            case 0 -> 0;
            case 2 -> {
                yield 20;      // Kết quả của switch(inner).
            }
            default -> -1;
        };
        yield part + 1;        // Kết quả của switch(outer).
    }
    default -> 0;
};
System.out.println(answer); // 21
~~~

`yield 20` cho `part = 20` rồi chương trình tiếp tục tính `part + 1`. `yield part + 1` mới kết thúc switch bên ngoài. Không thể dùng `yield` để nhảy xuyên qua ranh giới method, constructor, initializer hoặc lambda được lồng trong switch expression.

## 10. Ví dụ Java 21+ hoàn chỉnh, có đầu ra kiểm chứng

Lưu vào tệp **`YieldSwitchDemo.java`**:

~~~java
public class YieldSwitchDemo {
    record Point(int x, int y) {}
    record Box(String label, int quantity) {}

    static String describe(Object input) {
        return switch (input) {
            case null -> "Không có dữ liệu";
            case String s when s.isBlank() -> {
                yield "Chuỗi chỉ có khoảng trắng";
            }
            case String s -> {
                String clean = s.strip();
                yield "Văn bản: " + clean;
            }
            case Point(int x, int y) when x == y -> {
                int sum = x + y;
                yield "Điểm chéo, tổng = " + sum;
            }
            case Point(var x, var y) -> "Điểm (" + x + ", " + y + ")";
            case Box(var label, var quantity) when quantity > 0 -> {
                String name = label == null ? "?" : label.strip();
                yield name + ": " + quantity;
            }
            default -> "Không hỗ trợ";
        };
    }

    static int level(int score) {
        return switch (score) {
            case 0: yield 0;
            case 1, 2: yield 10 * score;
            default: yield -1;
        };
    }

    static int length(Object input) {
        return switch (input) {
            case String s -> {
                if (s.isBlank()) {
                    yield 0;
                }
                yield s.length();
            }
            case null -> 0;
            default -> -1;
        };
    }

    public static void main(String[] args) {
        System.out.println(describe("  Java  "));
        System.out.println(describe("   "));
        System.out.println(describe(new Point(4, 4)));
        System.out.println(describe(new Point(2, 5)));
        System.out.println(describe(new Box("  sách  ", 3)));
        System.out.println(describe(new Box(null, 2)));
        System.out.println(describe(new Box("bút", 0)));
        System.out.println(describe(null));
        System.out.println(level(2));
        System.out.println(level(9));
        System.out.println(length("  "));
        System.out.println(length("Java"));
    }
}
~~~

Biên dịch và chạy bằng **JDK 21 hoặc mới hơn**:

~~~bash
javac --release 21 YieldSwitchDemo.java
java YieldSwitchDemo
~~~

Đầu ra:

~~~text
Văn bản: Java
Chuỗi chỉ có khoảng trắng
Điểm chéo, tổng = 8
Điểm (2, 5)
sách: 3
?: 2
Không hỗ trợ
Không có dữ liệu
20
-1
0
4
~~~

Diễn giải các trường hợp:

- Chuỗi có nội dung: `strip()` và `yield` trả chuỗi chuẩn hóa.
- Chuỗi chỉ có khoảng trắng: guard `s.isBlank()` khớp nhánh đầu.
- `Point(4, 4)`: record pattern và guard `x == y`, tính tổng rồi `yield`.
- `Point(2, 5)`: nhánh mũi tên với expression trực tiếp.
- `Box("  sách  ", 3)`: biến component `label` được xử lý rồi `yield`; `Box(null, 2)` dùng `"?"` để xử lý null component.
- `Box("bút", 0)`: guard `quantity > 0` không đúng, chuyển đến `default`.
- Selector null vào `case null`.
- `level` chứng minh cú pháp `case: yield`; `length` chứng minh có thể `yield` sớm ở một đường đi, rồi `yield` ở đường còn lại.

## 11. Lỗi thường gặp và cách sửa

| Lỗi | Nguyên nhân | Sửa |
| --- | --- | --- |
| `case 1 -> yield 10;` | `yield` là statement, không phải expression ở vế phải mũi tên | `case 1 -> 10;` hoặc `case 1 -> { yield 10; }` |
| Block case thiếu `yield` | Nhánh có thể kết thúc bình thường mà không có giá trị | Bổ sung `yield` trên mọi đường cần thiết hoặc `throw` |
| `yield System.out.println(...);` | `println` trả `void` | Tách lệnh in và `yield` một giá trị |
| Dùng `break` để lấy giá trị từ switch expression | `break` không cấp giá trị và không được nhảy ra khỏi switch expression | Dùng `yield value;` |
| Dùng `return` thay cho `yield` trong case block | `return` hướng đến method, không phải switch expression | `yield` tại nhánh, `return switch(...)` tại method nếu cần |
| Chỉ dùng `default` và mong xử lý được null | `default` không phải nhánh null | Thêm `case null` |
| Quên bao phủ một kiểu selector có thể xảy ra | Switch expression có thể không exhaustive | Thêm case cụ thể hoặc `default` |
| Đặt nhánh `String s` chung trước nhánh `String s when ...` | Nhánh chung dominate nhánh đặc biệt | Đặt guard trước |
| Trộn `case X:` và `case Y ->` | Hai dạng switch block không được trộn | Dùng một dạng thống nhất |
| Dùng `case ... when` hoặc record pattern trên JDK 17 như cú pháp chuẩn | Pattern switch và record patterns chuẩn từ Java 21 | Dùng JDK 21+ |
| Nhầm `yield` kết thúc cả method | `yield` chỉ hoàn thành switch expression gần nhất | Dùng `return` ngoài expression nếu muốn trả khỏi method |

## 12. Bài tập và đáp án

**Bài 1.** Viết hàm dùng `return switch (obj)` để trả `"blank"` nếu `obj` là chuỗi trắng, trả chuỗi đã strip nếu là chuỗi thường, trả `"null"` nếu đầu vào null, và `"other"` cho kiểu khác. Dùng `yield` trong block xử lý String.

**Bài 2.** Đoạn sau thiếu gì?

~~~java
int n = 2;
int x = switch (n) {
    case 2 -> {
        int doubled = n * 2;
        // Chưa tạo giá trị cho nhánh này.
    }
    default -> -1;
};
~~~

**Bài 3.** Với switch lồng nhau ở mục 9, kết quả in ra là bao nhiêu? Hai lệnh `yield` nhắm đến switch nào?

**Bài 4.** Với `record Point(int x, int y) {}`, hãy viết case có `when x == y`, tính tổng hai tọa độ rồi `yield` chuỗi `"Tổng = ..."`. Vì sao case này phải nằm trước case tổng quát `Point(var x, var y)`?

**Gợi ý giải:**

~~~java
// Bài 1: đặt trong một class.
static String normalize(Object obj) {
    return switch (obj) {
        case String s -> {
            if (s.isBlank()) {
                yield "blank";
            }
            yield s.strip();
        }
        case null -> "null";
        default -> "other";
    };
}

// Bài 2: thêm 'yield doubled;' ở cuối block của case 2.

// Bài 4: nhánh đặt trong switch trên Object hoặc Point:
// case Point(int x, int y) when x == y -> {
//     yield "Tổng = " + (x + y);
// }
~~~

Bài 3 cho kết quả `21`; `yield 20` nhắm đến switch `inner`, còn `yield part + 1` nhắm đến switch `outer`. Bài 4 cần đặt nhánh có guard trước để nhánh tổng quát không dominate nó.

## Tham khảo

- [JEP 361 — Switch Expressions](https://openjdk.org/jeps/361): switch expression và `yield` từ Java 14.
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441): case pattern và `when` từ Java 21.
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440): record patterns từ Java 21.
- [Oracle Java 21 — Switch Expressions and Statements](https://docs.oracle.com/en/java/javase/21/language/switch-expressions-and-statements.html).
- [JLS 21, `14.21 Yield](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.21) và [`15.28 Switch Expressions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.28).
