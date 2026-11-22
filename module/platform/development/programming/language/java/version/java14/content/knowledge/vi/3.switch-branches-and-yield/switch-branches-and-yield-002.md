# Khối lệnh sau mũi tên (`->`) và câu lệnh `yield` trong `switch` expression (Java 14+)

> Mục tiêu: biết khi nào dùng một biểu thức sau `->`, khi nào cần khối `{ ... }` và cách dùng `yield` để tạo giá trị của `switch` expression sau khi thực hiện nhiều câu lệnh. Nội dung tập trung vào cú pháp đã chính thức từ Java 14 và vẫn áp dụng trong Java hiện đại; ví dụ chạy bằng JDK 17 trở lên.

## 1. Tại sao cần khối sau mũi tên?

`switch` có thể dùng như một **biểu thức** để tạo ra giá trị và gán cho biến, truyền vào hàm hoặc trả về từ phương thức. Với nhánh `case ... ->`, Java chỉ thực hiện vế phải của nhánh phù hợp; không có hiện tượng tự động chạy tiếp sang `case` sau (fall-through).

Vế phải của một quy tắc `case ... ->` có ba dạng chính:

| Dạng | Cú pháp | Khi dùng trong `switch` expression |
|---|---|---|
| **Biểu thức trực tiếp** | `case "A" -> 10;` | Kết quả của biểu thức chính là giá trị nhánh; không cần `yield` |
| **Khối lệnh** | `case "B" -> { int x = 5; yield x * 2; }` | Cần nhiều bước: khai báo biến, tính toán, điều kiện, ghi log... rồi tạo giá trị bằng `yield` |
| **Ném ngoại lệ** | `default -> throw new IllegalArgumentException("...");` | Không có giá trị hợp lệ để trả, nên nhánh kết thúc bằng ngoại lệ |

Ví dụ minh họa đặt **bên trong một phương thức** có biến `mode` kiểu `String`:

```java
String result = switch (mode) {
    case "BASIC" -> "basic";
    case "CUSTOM" -> {
        int units = 2;
        String label = "custom-" + units;
        yield label;
    }
    default -> throw new IllegalArgumentException("Unknown mode: " + mode);
};
```

Ở `BASIC`, một biểu thức `"basic"` là đủ. Ở `CUSTOM`, các lệnh trong `{}` chuẩn bị biến trung gian; `yield label;` trả giá trị `"custom-2"` cho **toàn bộ switch expression**. Với `default`, không tạo kết quả giả cho chế độ không hỗ trợ.

**Phân biệt quan trọng:** `case -> { ... }` còn dùng được trong **switch statement** chỉ để thực thi câu lệnh, nhưng một `switch` **expression** cần tạo ra giá trị hoặc ném ngoại lệ trên mọi đường thực thi. Khối của statement có thể kết thúc bình thường; khối của expression không thể đi đến `}` mà chưa trả giá trị hoặc ném lỗi.

## 2. `yield` hoạt động như thế nào?

Cú pháp là `yield biểu_thức;`, ví dụ `yield total;`, `yield base + tax;`, `yield "UNKNOWN";`. Các bước diễn ra theo thứ tự:

1. Biểu thức lựa chọn của `switch` được đánh giá, sau đó Java chọn một `case` phù hợp.
2. Với nhánh `-> { ... }`, chương trình chạy các câu lệnh trong khối từ trên xuống; có thể khai báo biến cục bộ, kiểm tra điều kiện hoặc ném ngoại lệ.
3. Khi đến `yield expr;`, Java đánh giá `expr`. Nếu thành công, giá trị được chuyển tới **switch expression bao ngoài gần nhất**, nhánh kết thúc và `switch` tạo ra giá trị đó.
4. Câu lệnh bao ngoài (chẳng hạn phép gán `int cost = switch (...) { ... };` hoặc `return switch (...) { ... };`) tiếp tục theo ngữ nghĩa bình thường của nó. Nếu biểu thức tại `yield` ném ngoại lệ, ngoại lệ được lan truyền thay vì tạo giá trị.

`yield` **không phải** cơ chế tạm dừng chương trình, generator hay `Thread.yield()`. Đây là câu lệnh điều khiển luồng dành riêng cho việc tạo giá trị từ `switch` expression.

Ví dụ cần xử lý điều kiện trong khối (đoạn đặt trong phương thức có `member` và `plan`):

```java
int price = switch (plan) {
    case "FREE" -> 0;
    case "PRO" -> {
        int standardPrice = 200;
        if (member) {
            yield standardPrice - 20;
        }
        yield standardPrice;
    }
    default -> throw new IllegalArgumentException("Unknown plan: " + plan);
};
```

- `plan = "PRO"` và `member = true`: kết quả `180`; câu `yield standardPrice;` bên dưới **không chạy**.
- `plan = "PRO"` và `member = false`: đi qua `if`, kết quả `200`.
- Tất cả đường đi hợp lệ của nhánh `PRO` đều gặp `yield`, nên không có đường nào kết thúc khối mà không tạo giá trị.

## 3. Quy tắc luồng điều khiển và phạm vi biến

**(a) Mỗi đường đi trong khối phải kết thúc thích hợp.** Với `switch` expression, khối `case -> { ... }` không được kết thúc bình thường mà thiếu `yield` hoặc `throw`. Có thể dùng hai nhánh `if/else` cùng `yield`, hoặc dùng một `yield` chung sau phần tính toán. Trong trường hợp có lỗi đầu vào, `throw` là kết thúc hợp lệ.

```java
case "EXPRESS" -> {
    if (items > 4) {
        throw new IllegalArgumentException("Too many items");
    }
    int cost = 40 + items * 10;
    yield cost;
}
```

**(b) `yield` khác `return` và `break`.** `yield value;` làm cho `switch` expression tạo giá trị. `return value;` trả về từ phương thức hoặc lambda phù hợp; không thể đặt `return` trực tiếp trong thân `switch` expression để thay `yield`. `break` không tạo giá trị cho `switch` expression. Đừng dùng cú pháp `break value;` để trả giá trị: đó không phải cú pháp của Java 14+ chính thức.

**(c) Khối `{}` giới hạn phạm vi biến.** Biến khai báo trong nhánh `case -> { ... }` chỉ tồn tại trong khối đó; nhánh khác không truy cập được. Hai nhánh có thể dùng cùng tên biến cục bộ mà không xung đột, bởi mỗi nhánh có phạm vi riêng.

**(d) Kiểu của giá trị phải tương thích.** Nếu `switch` được dùng như `int cost = switch (...) { ... };`, các kết quả được chọn phải tương thích với kiểu `int`. `yield "hello";` không thể thay thế cho giá trị số. `yield` cũng không nhận biểu thức kiểu `void`; muốn in thông báo rồi trả kết quả, hãy viết hai câu lệnh riêng.

**(e) `yield` hướng tới switch expression bao ngoài gần nhất.** Khi lồng nhiều switch expression, `yield` bên trong switch con trả giá trị cho switch con; cần một `yield` khác để trả giá trị từ khối switch cha. `yield` không thể nhảy xuyên ra khỏi thân phương thức hoặc lambda lồng bên trong.

Ví dụ **phương thức minh họa độc lập về cú pháp**, có thể thêm vào một class Java:

```java
static int nestedValue(int category, int level) {
    return switch (category) {
        case 1 -> {
            int inner = switch (level) {
                case 0 -> 2;
                default -> {
                    yield 4; // Trả về switch của level.
                }
            };
            yield inner * 10; // Trả về switch của category.
        }
        default -> 0;
    };
}
```

`nestedValue(1, 0)` trả `20`; `nestedValue(1, 3)` trả `40`. Mỗi `yield` tác động đến đúng switch expression trực tiếp bao ngoài nó.

## 4. Chương trình hoàn chỉnh: tính phí bằng khối và `yield`

Tạo tệp `ArrowYieldDemo.java` (tên tệp phải trùng tên public class):

```java
public class ArrowYieldDemo {
    enum Stage { NEW, VERIFIED }

    static int fee(String service, int items, boolean member) {
        if (service == null) {
            throw new IllegalArgumentException("service is required");
        }
        if (items <= 0) {
            throw new IllegalArgumentException("items must be positive");
        }

        return switch (service) {
            case "PICKUP" -> 0; // Biểu thức trực tiếp, không cần yield.

            case "STANDARD" -> {
                int baseFee = 20;
                int itemFee = items * 5;
                yield baseFee + itemFee;
            }

            case "EXPRESS" -> {
                if (items > 4) {
                    throw new IllegalArgumentException(
                        "EXPRESS supports at most 4 items");
                }
                int price = 40 + items * 10;
                if (member) {
                    yield price - 15;
                }
                yield price;
            }

            default -> throw new IllegalArgumentException(
                "Unsupported service: " + service);
        };
    }

    static String stageLabel(Stage stage) {
        if (stage == null) {
            throw new IllegalArgumentException("stage is required");
        }
        return switch (stage) {
            case NEW -> "new";
            case VERIFIED -> {
                String prefix = "state";
                yield prefix + "-verified";
            }
        };
    }

    public static void main(String[] args) {
        System.out.println("PICKUP=" + fee("PICKUP", 2, false));
        System.out.println("STANDARD=" + fee("STANDARD", 2, false));
        System.out.println("EXPRESS(member)=" + fee("EXPRESS", 2, true));
        System.out.println("EXPRESS(guest)=" + fee("EXPRESS", 2, false));
        System.out.println("STAGE=" + stageLabel(Stage.VERIFIED));

        try {
            fee("EXPRESS", 5, false);
        } catch (IllegalArgumentException ex) {
            System.out.println("EXPRESS(5): " + ex.getMessage());
        }

        try {
            fee("SAME_DAY", 1, false);
        } catch (IllegalArgumentException ex) {
            System.out.println("SAME_DAY: " + ex.getMessage());
        }
    }
}
```

Biên dịch và chạy bằng JDK 17+ (cũng dùng đúng cú pháp switch expression ổn định từ Java 14):

```bash
javac -encoding UTF-8 ArrowYieldDemo.java
java ArrowYieldDemo
```

**Stdout chính xác:**

```text
PICKUP=0
STANDARD=30
EXPRESS(member)=45
EXPRESS(guest)=60
STAGE=state-verified
EXPRESS(5): EXPRESS supports at most 4 items
SAME_DAY: Unsupported service: SAME_DAY
```

Giải thích kết quả:

- `PICKUP`: nhánh biểu thức trực tiếp tạo `0`.
- `STANDARD`: khối tạo hai biến cục bộ, rồi `yield 20 + 2 * 5`, tức `30`.
- `EXPRESS` với 2 mặt hàng: giá gốc `40 + 2 * 10 = 60`. Thành viên nhận `yield 60 - 15`, tức `45`; khách thường đi tới `yield 60`.
- `EXPRESS` với 5 mặt hàng: `throw` xảy ra trước `yield`; biểu thức không tạo kết quả và ngoại lệ được `catch` ở lời gọi.
- `Stage` là `enum` và cả hai hằng `NEW`, `VERIFIED` đều có nhánh, nên `switch` expression bao phủ hết enum mà không cần `default`. Khi thêm hằng enum và biên dịch lại, trình biên dịch sẽ yêu cầu xử lý hằng mới.
- `SAME_DAY` không phù hợp nhánh nào, nên `default -> throw` từ chối mã chưa hỗ trợ.

## 5. Những lỗi biên dịch phổ biến và cách sửa

Các đoạn dưới đây cố ý **không biên dịch được**; chỉ minh họa lỗi, không ghép vào chương trình ở mục 4.

### Lỗi 1: khối có đường đi hết mà chưa `yield`

```java
int result = switch (mode) {
    case "A" -> {
        int value = 10;
        System.out.println(value);
        // Thiếu yield: có thể chạm đến dấu } cuối khối.
    }
    default -> 0;
};
```

Sửa bằng cách thêm `yield value;` sau `System.out.println(value);`. Nếu một `if` có nhánh `yield` nhưng nhánh còn lại không có `yield`, `throw` hoặc đường đi tới `yield` chung, đó cũng là lỗi.

### Lỗi 2: dùng `return` hoặc `break` để tạo giá trị

```java
int result = switch (mode) {
    case "A" -> {
        return 10; // Sai: return trực tiếp trong switch expression.
    }
    default -> 0;
};
```

Sửa `return 10;` thành `yield 10;`. Nếu muốn cả phương thức trả giá trị, hãy viết `return switch (mode) { ... };` **bên ngoài** các nhánh, như chương trình ở mục 4. `break;` không thay được `yield 10;`.

### Lỗi 3: `yield` một biểu thức trả về `void`

```java
int result = switch (mode) {
    case "A" -> {
        yield System.out.println("A"); // Sai: println trả về void.
    }
    default -> 0;
};
```

Phải tách tác dụng phụ và kết quả:

```java
int result = switch (mode) {
    case "A" -> {
        System.out.println("A");
        yield 10;
    }
    default -> 0;
};
```

### Lỗi 4: kiểu `yield` không phù hợp ngữ cảnh

```java
int result = switch (mode) {
    case "A" -> {
        yield "ten"; // Sai: không thể tạo String cho kết quả int.
    }
    default -> 0;
};
```

Thay `"ten"` bằng giá trị `int` thích hợp hoặc đổi kiểu đích nếu hợp đồng bài toán thực sự cần `String`.

### Lỗi 5: dùng `yield` mà không có switch expression nhận giá trị

```java
switch (mode) { // Đây là switch statement.
    case "A" -> {
        yield 1; // Sai: không có switch expression nhận yield.
    }
    default -> {
        System.out.println("Other");
    }
}
```

Nếu chỉ muốn thực thi hành động, bỏ `yield` và giữ switch statement. Nếu muốn giá trị, đổi thành `int value = switch (mode) { ... };` với các nhánh tạo giá trị. `yield` không thể tự đứng ngoài switch expression.

## 6. Kiểm tra tính đầy đủ, `null` và chính sách lỗi

- `switch` **expression** phải bao phủ các giá trị selector có thể có. Với `String`, thông thường cần `default`; với `enum` đã liệt kê mọi hằng, có thể bỏ `default` để nhận cảnh báo lỗi biên dịch khi enum mở rộng.
- `default` không có nhiệm vụ tự xử lý `null` trong cách dùng Java 14/JDK 17. Nếu selector tham chiếu bằng `null` đi vào `switch`, thường sẽ phát sinh `NullPointerException`; vì vậy ví dụ kiểm tra `service == null` tường minh trước khi switch. Java 21+ có cú pháp `case null` cho các switch hỗ trợ; chỉ dùng khi mức JDK mục tiêu cho phép.
- Một nhánh `throw` không phải `yield` thất bại: đó là lựa chọn hợp lệ khi không có giá trị để trả. Tuy nhiên, kiểu ngoại lệ phải đúng hợp đồng API; dữ liệu đầu vào lỗi thường phù hợp với `IllegalArgumentException`.
- `yield null;` có thể hợp lệ với một số kiểu tham chiếu nếu được cho phép bởi ngữ cảnh kiểu, nhưng dễ khiến code sau phải xử lý `null`; chỉ làm vậy nếu hợp đồng kết quả yêu cầu.
- Đừng thêm `default -> 0` hoặc `yield 0` chỉ để làm mã biên dịch nếu `0` không có nghĩa nghiệp vụ. Có thể `throw` để lộ trạng thái bất thường và tránh tạo kết quả thành công giả.
- `case X ->` không fall-through nên không cần `break` chống rơi nhánh; tránh pha lẫn tư duy của `switch` statement dùng nhãn dấu `:` với `switch` expression.

## 7. Bảng tự kiểm tra trước khi dùng

| Tình huống | Cần kiểm tra |
|---|---|
| Nhánh chỉ có một phép tính | Có thể viết trực tiếp `case X -> expression;` mà không cần khối/`yield`? |
| Nhánh có nhiều lệnh/biến tạm | Đã dùng `{ ... yield value; }` với phạm vi cục bộ rõ ràng chưa? |
| Nhánh có `if`, `try`, điều kiện sớm | Mọi đường đi có `yield` hoặc kết thúc bằng `throw` hay không? |
| Nhánh phải từ chối đầu vào | Có ném ngoại lệ phù hợp, không trả giá trị giả không? |
| Biểu thức gán cho `int`, `String`, kiểu miền... | Giá trị tạo ra ở mọi nhánh có tương thích kiểu đích không? |
| Có `enum` | Mọi hằng đã được xử lý riêng; có nên tránh `default` để phát hiện hằng mới? |
| Đầu vào tham chiếu có thể `null` | Chính sách `null` đã rõ cho phiên bản JDK mục tiêu chưa? |
| Đã thử chạy chương trình | Đã kiểm tra giá trị bình thường, điều kiện thành viên, nhánh `throw`, `default`, `null` và kiểu dữ liệu? |

## Tài liệu tham khảo chính thức

- Oracle Dev.java, *Branching with Switch Expressions*: https://dev.java/learn/branching-with-switch-expressions/
- Oracle, *Switch Expressions* (Java 14): https://docs.oracle.com/en/java/javase/14/language/switch-expressions.html
- Java Language Specification hiện hành, mục `yield` statement: https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-14.html#jls-14.21
- Java Language Specification hiện hành, mục `switch` expression: https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-15.html#jls-15.28
