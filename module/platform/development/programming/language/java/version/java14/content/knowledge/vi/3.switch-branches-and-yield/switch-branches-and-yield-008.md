# Phân biệt `yield`, `break` và `return` trong `switch` (Java 14+)

## 1. Vấn đề cần hiểu

Từ Java 14, `switch` có thể là **statement** (câu lệnh để điều khiển luồng) hoặc **expression** (biểu thức tạo ra một giá trị). Ba từ khóa `yield`, `break` và `return` đều có thể làm luồng thực thi chuyển sang vị trí khác, nhưng **đích chuyển và mục đích của chúng hoàn toàn khác nhau**:

- **`yield value;`**: cung cấp giá trị cho **`switch` expression gần nhất** chứa nó; quá trình tính `switch` expression kết thúc với giá trị đó. Sau đó phương thức vẫn có thể thực thi những câu lệnh tiếp theo.
- **`break;`**: kết thúc **`switch` statement hoặc vòng lặp** phù hợp ở bên trong phạm vi hiện tại; **không** cung cấp giá trị cho `switch` expression.
- **`return value;` / `return;`**: kết thúc việc thực thi **phương thức hoặc lambda** chứa nó và trả quyền điều khiển cho bên gọi; `return value;` trả kết quả của phương thức/lambda phù hợp, không phải của một `switch` expression.

Quan trọng: **không thể dùng `break` hoặc `return` để nhảy ra khỏi `switch` expression**. Dùng `yield` khi khối nhánh cần tính toán rồi trả về giá trị cho biểu thức `switch`. Sự phân biệt này vẫn áp dụng theo Java Language Specification hiện hành.

| Từ khóa | Đích điều khiển | Có cung cấp giá trị? | Dùng điển hình |
| --- | --- | --- | --- |
| `yield expr;` | `switch` **expression** gần nhất | Có, giá trị của `expr` trở thành giá trị biểu thức `switch` | Nhánh `case -> { ... }` có nhiều lệnh; `case: ... yield ...;` trong `switch` expression |
| `break;` | `switch` **statement** hoặc vòng lặp `for`/`while`/`do` gần nhất có thể làm đích | Không | Chặn rơi xuyên nhánh trong `switch` statement kiểu `case:`; thoát vòng lặp |
| `break label;` | Câu lệnh có nhãn `label` bao quanh, khi phép nhảy hợp lệ | Không | Thoát khỏi vòng lặp/khối có nhãn; không được nhảy xuyên qua `switch` expression |
| `return expr;` | Phương thức hoặc lambda nhận kết quả | Có, nếu kiểu trả về phù hợp | Kết thúc sớm phương thức; `return switch (...) { ... };` |
| `return;` | Phương thức `void` hoặc lambda `void` phù hợp | Không | Kết thúc sớm phương thức không trả giá trị |

**Ghi nhớ bằng ba câu hỏi:** “Giá trị này thuộc về `switch` expression?” → `yield`. “Chỉ muốn rời câu lệnh `switch` hay vòng lặp?” → `break`. “Muốn phương thức kết thúc ngay?” → `return`.

## 2. `yield`: cấp kết quả cho `switch` expression

### 2.1. Nhánh mũi tên trả giá trị trực tiếp

Đối với `switch` expression dùng quy tắc `case ... -> expression`, chính biểu thức bên phải `->` tạo ra kết quả. Không cần thêm `yield`:

```java
int code = 2;
String status = switch (code) {
    case 1 -> "NEW";
    case 2 -> "PROCESSING";
    default -> "UNKNOWN";
};
System.out.println(status); // PROCESSING
```

Đây là **biểu thức `switch`** vì toàn bộ `switch (...) { ... }` được gán cho biến `status`.

### 2.2. Nhánh mũi tên dạng khối cần `yield`

Nếu phải khai báo biến, kiểm tra điều kiện, ghi log hoặc tính nhiều bước, đặt các lệnh trong `{ ... }` và dùng `yield` để tạo giá trị cuối cùng:

```java
int code = 2;
String status = switch (code) {
    case 1 -> "NEW";
    case 2 -> {
        int next = code + 1;
        System.out.println("next = " + next);
        yield "NEXT_" + next;
    }
    default -> "UNKNOWN";
};
System.out.println(status);
```

Kết quả:

```text
next = 3
NEXT_3
```

Luồng chạy: vào `case 2` → tính `next` → in `next = 3` → thực thi `yield "NEXT_3";` → toàn bộ `switch` expression cho ra `"NEXT_3"` → gán cho `status` → **tiếp tục chạy câu lệnh sau `switch`**. `yield` không thoát phương thức.

**Không bắt buộc mọi nhánh viết từ khóa `yield`:** nhánh `-> "NEW"` đã cho giá trị trực tiếp; chỉ nhánh dạng khối hoặc dạng nhóm `case:` cần `yield` khi phải tự tạo kết quả. Một nhánh kết thúc bằng `throw` có thể không tạo giá trị vì luồng thực thi chuyển sang ném ngoại lệ.

### 2.3. Dạng `case:` của `switch` expression

Nếu dùng cú pháp nhóm câu lệnh với dấu hai chấm trong **`switch` expression**, câu lệnh `yield` tạo giá trị:

```java
static String priority(int level) {
    return switch (level) {
        case 1:
            yield "HIGH";
        case 2:
            yield "MEDIUM";
        default:
            yield "LOW";
    };
}
```

Trong ví dụ này **`yield`** hoàn tất `switch` expression; **`return`** bên ngoài trả kết quả biểu thức về cho nơi gọi `priority`. Hai từ khóa phục vụ **hai tầng** khác nhau.

Dạng `case ... ->` thường dễ đọc hơn và tránh vô tình rơi xuyên qua nhãn; dùng dạng `case:` khi có lý do rõ ràng và bảo đảm các đường chạy cần thiết đều tạo kết quả hoặc ném ngoại lệ.

## 3. `break`: thoát khỏi `switch` statement hoặc vòng lặp

### 3.1. `break` trong `switch` statement truyền thống

```java
static String classify(int code) {
    String result;
    switch (code) {
        case 1:
            result = "ONE";
            break; // Chỉ rời switch statement
        case 2:
            result = "TWO";
            break;
        default:
            result = "OTHER";
    }
    return "RESULT: " + result;
}
```

Khi `code == 2`, `break;` đưa điều khiển đến **sau câu lệnh `switch`**. Lệnh `return "RESULT: " + result;` vẫn được chạy. Với các nhánh `case:`, thiếu `break` có thể dẫn đến *fall-through* (chạy tiếp mã ở nhánh kế) khi cấu trúc cho phép.

### 3.2. Dạng mũi tên trong `switch` statement thường không cần `break`

```java
static void printStatus(int code) {
    switch (code) { // switch statement vì không được dùng như giá trị
        case 1 -> System.out.println("NEW");
        case 2 -> System.out.println("PROCESSING");
        default -> System.out.println("UNKNOWN");
    }
    System.out.println("AFTER SWITCH");
}
```

Với `code == 2`, chương trình in `PROCESSING` rồi `AFTER SWITCH`. Dạng mũi tên thực thi **một nhánh duy nhất** nên không cần `break` chỉ để tránh fall-through. Cú pháp `->` tự nó **không xác định `switch` là statement hay expression**; hãy nhìn cách `switch` được sử dụng.

### 3.3. `break` trong vòng lặp nằm bên trong `switch` expression vẫn hợp lệ

Quy tắc “không `break` ra khỏi `switch` expression” **không** có nghĩa là cấm mọi từ khóa `break` xuất hiện trong khối đó. Nếu `break` thoát **vòng lặp con** hoàn toàn nằm bên trong một nhánh, sau đó nhánh vẫn có thể dùng `yield` để cấp kết quả:

```java
static int sumUntilTwo(int mode) {
    return switch (mode) {
        case 1 -> {
            int sum = 0;
            for (int i = 0; i < 4; i++) {
                if (i == 2) {
                    break; // Thoát for, KHÔNG thoát switch expression
                }
                sum += i;
            }
            yield sum; // sum = 0 + 1 = 1
        }
        default -> -1;
    };
}
```

`sumUntilTwo(1)` trả về `1`. Trong vòng lặp, `break` có đích là `for`; `yield` có đích là `switch` expression. Tương tự, `break label;` không được phép nhảy tới một đích bên ngoài bằng cách **vượt qua ranh giới** `switch` expression.

## 4. `return`: kết thúc phương thức, không “yield” giá trị nhánh

`return` trong thân **`switch` statement** có thể kết thúc toàn bộ phương thức ngay, kể cả còn lệnh phía sau `switch`:

```java
static String classifyEarly(int code) {
    switch (code) {
        case 1:
            return "ONE"; // Kết thúc classifyEarly ngay
        case 2:
            break;        // Chỉ thoát switch statement
        default:
            return "OTHER";
    }
    return "AFTER_SWITCH"; // Chỉ tới đây nếu case 2 thực thi break
}
```

Với `classifyEarly(1)`: kết quả là `ONE`, không chạy phần sau `switch`. Với `classifyEarly(2)`: `break` rời `switch` rồi phương thức trả `AFTER_SWITCH`.

### 4.1. `return switch (...) { ... };`: phối hợp hai tầng kết quả

Đây là cách viết phổ biến, gọn và **hợp lệ từ Java 14**:

```java
static String describe(int code) {
    return switch (code) {
        case 1 -> "NEW";
        case 2 -> {
            String value = "PROCESSING";
            yield value;
        }
        default -> "UNKNOWN";
    };
}
```

- `yield value;` chỉ gửi `"PROCESSING"` **ra khỏi `switch` expression**.
- Sau đó, biểu thức `switch` đã có kết quả để `return` **trả khỏi phương thức `describe`**.
- `return` được viết **bên ngoài** biểu thức `switch`; không viết `return value;` thay cho `yield value;` trong khối `case 2`.

Tương tự, khi dùng `String result = switch (...) { ... };` rồi mới `return result;`, các câu lệnh nằm giữa phép gán và `return` vẫn có thể chạy.

### 4.2. `return` bên trong nhánh của `switch` expression gây lỗi

Đoạn sau **cố ý không biên dịch được**:

```java
// Trích đoạn bên trong một phương thức trả int:
int result = switch (code) {
    case 1 -> {
        return 100; // LỖI: không thể return ra khỏi switch expression
    }
    default -> 0;
};
```

Trong một `switch` expression, `return` như trên cố gắng chuyển quyền điều khiển xuyên qua biểu thức đang được tính, nên trình biên dịch từ chối (ví dụ: `attempt to return out of a switch expression`). Đổi thành `yield 100;` nếu muốn **giá trị nhánh** là 100; hoặc chuyển việc quyết định trả khỏi phương thức ra **ngoài** `switch` expression.

Phân biệt với `switch` **statement**: `case 1 -> { return 100; }` có thể hợp lệ nếu nằm trong phương thức trả `int`, vì đây là phương thức được kết thúc, không có `switch` expression nào bị nhảy xuyên qua.

## 5. Chương trình hoàn chỉnh để quan sát cả ba từ khóa

Lưu đúng tên **`YieldBreakReturnDemo.java`**:

```java
public class YieldBreakReturnDemo {
    static String describe(int code) {
        String category = switch (code) {
            case 1 -> "NEW";
            case 2 -> {
                int next = code + 1;
                yield "NEXT_" + next;
            }
            default -> "UNKNOWN";
        };
        return "Category: " + category;
    }

    static String classify(int code) {
        switch (code) {
            case 1:
                return "ONE";
            case 2:
                break;
            default:
                return "OTHER";
        }
        return "AFTER_SWITCH";
    }

    static String fromColon(int code) {
        return switch (code) {
            case 1:
                yield "LOW";
            default:
                yield "OTHER";
        };
    }

    static int loopInExpression(int limit) {
        return switch (limit) {
            case 1 -> {
                int sum = 0;
                for (int i = 0; i < 4; i++) {
                    if (i == 2) break;
                    sum += i;
                }
                yield sum;
            }
            default -> -1;
        };
    }

    public static void main(String[] args) {
        System.out.println(describe(1));
        System.out.println(describe(2));
        System.out.println(classify(2));
        System.out.println(classify(1));
        System.out.println(fromColon(1));
        System.out.println(loopInExpression(1));
    }
}
```

Biên dịch và chạy bằng JDK 14 trở lên; dùng `--release 14` để kiểm chứng khả năng tương thích với chuẩn ngôn ngữ Java 14 khi đang dùng JDK mới:

```bash
javac --release 14 YieldBreakReturnDemo.java
java YieldBreakReturnDemo
```

Kết quả chuẩn (đã kiểm tra với `javac --release 14`):

```text
Category: NEW
Category: NEXT_3
AFTER_SWITCH
ONE
LOW
1
```

Diễn giải từng trường hợp:

1. `describe(1)`: nhánh `-> "NEW"` tạo giá trị biểu thức, sau đó `return` của phương thức nối tiền tố.
2. `describe(2)`: nhánh khối gọi `yield "NEXT_3"`, kết quả được gán vào `category` rồi `return` bên ngoài mới thoát phương thức.
3. `classify(2)`: `break` chỉ thoát `switch` statement; chạy tiếp `return "AFTER_SWITCH";`.
4. `classify(1)`: `return "ONE";` trong `switch` statement thoát ngay phương thức.
5. `fromColon(1)`: `yield "LOW";` tạo giá trị cho `switch` expression; `return switch (...)` trả kết quả đó khỏi phương thức.
6. `loopInExpression(1)`: `break` thoát `for` con khi `i == 2`; sau vòng lặp, `yield sum;` tạo kết quả `1`.

## 6. Các lỗi thường gặp và cách sửa

### Lỗi A — Dùng `break` thay cho `yield`

```java
// SAI: trích đoạn trong phương thức
int result = switch (code) {
    case 1 -> {
        break; // LỖI: attempt to break out of a switch expression
    }
    default -> 0;
};
```

Sửa:

```java
int result = switch (code) {
    case 1 -> {
        yield 10; // Trả giá trị cho switch expression
    }
    default -> 0;
};
```

`break;` không mang giá trị; không thể thay thế `yield expression;`.

### Lỗi B — Dùng `return` thay cho `yield` trong biểu thức

```java
// SAI: trích đoạn trong phương thức trả int
int result = switch (code) {
    case 1 -> { return 10; } // LỖI: return ra khỏi switch expression
    default -> 0;
};
```

Sửa bằng `yield 10;` nếu cần hoàn tất việc tính `switch` expression; dùng `return switch (...) { ... };` bên **ngoài** nếu phương thức phải trả ngay kết quả vừa tính.

### Lỗi C — Quên cấp giá trị cho một khối nhánh

```java
// SAI: khối case 1 có thể kết thúc mà chưa cho giá trị
String name = switch (code) {
    case 1 -> {
        System.out.println("Code 1");
    }
    default -> "Other";
};
```

Sửa: thêm `yield "One";` ở cuối nhánh `case 1`. Nếu có `if/else` trong khối, mọi đường thực thi có thể hoàn tất bình thường đều phải được tổ chức để **cung cấp một giá trị hoặc ném ngoại lệ**.

```java
String name = switch (code) {
    case 1 -> {
        System.out.println("Code 1");
        yield "One";
    }
    default -> "Other";
};
```

### Lỗi D — Dùng `yield` ở nơi chỉ có `switch` statement

```java
// SAI: đây là switch statement, không có switch expression làm đích yield
switch (code) {
    case 1:
        yield "One"; // LỖI: yield outside of switch expression
    default:
        break;
}
```

Nếu muốn **tạo một giá trị**, chuyển toàn bộ thành `String name = switch (code) { case 1 -> "One"; default -> "Other"; };`. Nếu chỉ cần thực thi tác vụ, tiếp tục dùng `switch` statement cùng `break` hoặc dạng mũi tên phù hợp.

### Lỗi E — Nhảy từ nhánh biểu thức ra vòng lặp bên ngoài

```java
// SAI: nhảy xuyên qua switch expression
outer:
for (int n = 0; n < 3; n++) {
    int value = switch (n) {
        case 1 -> {
            break outer; // LỖI: đích break nằm ngoài switch expression
        }
        default -> n;
    };
    System.out.println(value);
}
```

Sửa bằng cách để biểu thức `switch` tạo ra một **giá trị báo hiệu**, rồi xử lý `break outer;` **sau khi biểu thức đã kết thúc**:

```java
outer:
for (int n = 0; n < 3; n++) {
    boolean shouldStop = switch (n) {
        case 1 -> true;
        default -> false;
    };
    if (shouldStop) break outer;
    System.out.println(n);
}
```

Lúc này `break outer;` không còn đi xuyên qua một `switch` expression nào.

## 7. Phân biệt thêm các vấn đề liên quan

### `yield` không thay thế toàn bộ `return`

`yield` chỉ có nghĩa khi có **`switch` expression** làm đích, kể cả khi nó xuất hiện sâu trong một khối nhánh. `return` dùng để trả từ phương thức/lambda. Không thể viết `yield` bên ngoài `switch` expression để trả từ phương thức.

### Phạm vi gần nhất quyết định đích

- `yield` nhắm đến `switch` expression **gần nhất**. Trong trường hợp có `switch` expression lồng nhau, nhánh trong có thể `yield` cho biểu thức trong; nếu nhánh ngoài dạng khối cần tạo giá trị thì nó cần kết quả riêng (ví dụ `yield inner + 1;`).
- `break` không nhắm đến `switch` expression. Nó nhắm đến vòng lặp hoặc `switch` **statement** có thể làm đích, trừ khi có nhãn chỉ rõ một đích hợp lệ.
- `return` nhắm đến phương thức hoặc lambda chứa nó. Bất kỳ `switch` expression nào nằm giữa lệnh `return` và đích cần thoát sẽ khiến cách nhảy đó không hợp lệ.

### Yêu cầu kiểu và bao phủ của `switch` expression

Một `switch` expression cần tạo được **giá trị với kiểu phù hợp ngữ cảnh** (hoặc hoàn tất đột ngột, chẳng hạn ném ngoại lệ). `yield` phải kèm một biểu thức **không có kiểu `void`**; không thể viết `yield;` hoặc `yield doSomethingVoid();`. Với `switch` trên `int`, thường thêm `default` để bao phủ các giá trị chưa liệt kê; với một số kiểu đóng như `enum`, có thể bao phủ mọi khả năng mà không cần `default`.

Ví dụ hợp lệ khi nhánh muốn báo lỗi thay vì tạo giá trị:

```java
static int requirePositive(int code) {
    return switch (code) {
        case 1 -> 100;
        case 2 -> {
            int result = code * 100;
            yield result;
        }
        default -> throw new IllegalArgumentException("Unsupported code");
    };
}
```

`throw` làm luồng chạy kết thúc bằng ngoại lệ, không cấp giá trị; đây là lựa chọn hợp lệ khi đầu vào không được hỗ trợ. Tránh dùng `break` hoặc `return` trong nhánh biểu thức để thay thế cho xử lý lỗi.

### Một quy tắc dễ nhớ về dấu hai chấm và mũi tên

- `switch` **statement**, `case ...:`: `break` thường được dùng để tránh rơi tiếp sang nhánh sau.
- `switch` **statement**, `case ... ->`: không có fall-through, thường không cần `break`.
- `switch` **expression**, `case ... -> expression`: giá trị lấy từ biểu thức bên phải mũi tên.
- `switch` **expression**, `case ... -> { ... }` hoặc `case ...:`: dùng `yield value;` để tạo kết quả ở đường đi phù hợp.
- **Bất kể cú pháp nhãn**, `return` muốn thoát phương thức phải xuất hiện ở vị trí hợp lệ, không nhảy xuyên qua `switch` expression.

## 8. Bài tập tự đánh giá

**Câu 1.** Trong `String s = switch (n) { case 1 -> { /* xử lý */ } default -> "Other"; };`, lệnh nào cần thêm để nhánh `case 1` có kết quả chuỗi?

**Đáp án:** `yield "One";` (hoặc sửa nhánh thành `case 1 -> "One";` nếu không cần khối lệnh).

**Câu 2.** Trong một phương thức, `switch (n) { case 1: break; default: return; }` là `switch` statement. Khi `n == 1`, phương thức có kết thúc tại `break` không?

**Đáp án:** Không; `break` chỉ rời `switch` statement và phương thức tiếp tục ở lệnh kế tiếp. `return;` trong `default` mới kết thúc phương thức, với điều kiện phương thức có kiểu trả về `void`.

**Câu 3.** Có thể viết `break;` bên trong `for` nằm trong nhánh `case -> { ... yield result; }` không?

**Đáp án:** Có, khi `break` thoát **vòng lặp con** và không nhảy xuyên qua `switch` expression; sau vòng lặp cần tạo kết quả cho nhánh thích hợp.

**Câu 4.** Trong `return switch (n) { case 1 -> { yield 10; } default -> 0; };`, `yield 10` và `return` có giống nhau không?

**Đáp án:** Không. `yield` hoàn thành `switch` expression với `10`; `return` trả giá trị `10` đó về cho nơi gọi phương thức.

## Tài liệu chuẩn, còn áp dụng

- [Java Language Specification, Java SE 26 — `14.15 `break`, `14.17 `return`, `14.21 `yield`](https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-14.html): định nghĩa đích điều khiển và các trường hợp nhảy qua `switch` expression không hợp lệ.
- [Java Language Specification, Java SE 26 — `15.28 `switch` Expressions](https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-15.html): cách `switch` expression nhận giá trị từ nhánh và `yield`.
- [Oracle Java 14 — Switch Expressions](https://docs.oracle.com/en/java/javase/14/language/switch-expressions.html): hướng dẫn dùng `case ->`, `yield`, nhánh khối và quy tắc tránh rơi xuyên nhánh.
