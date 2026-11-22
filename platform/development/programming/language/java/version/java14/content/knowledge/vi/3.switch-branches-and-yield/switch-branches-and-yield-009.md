# Giới hạn chuyển điều khiển qua biên biểu thức `switch` (Java 14+)

## Mục tiêu

Sau bài học, bạn có thể giải thích vì sao một nhánh của **switch expression** phải tạo ra giá trị hoặc ném ngoại lệ; phân biệt `yield` với `break` và `return`; xác định chính xác đích của `break`, `continue`, `return`, `yield` trong các cấu trúc lồng nhau; và nhận ra các bước nhảy bị trình biên dịch từ chối vì vượt qua biên của biểu thức `switch`.

Trong Java 14, `switch expression` đã trở thành tính năng chính thức. Các quy tắc trình bày ở đây vẫn được Java hiện đại áp dụng; ví dụ sử dụng cú pháp ổn định, không cần bật preview.

## 1. “Biên biểu thức switch” nghĩa là gì?

Xét mã:

```java
int score = switch (level) {
    case 1 -> 10;
    case 2 -> {
        int bonus = 5;
        yield 20 + bonus;
    }
    default -> throw new IllegalArgumentException("level=" + level);
};
```

Đây là **biểu thức**: toàn bộ `switch (...) { ... }` tham gia tính ra giá trị để gán cho `score`.

- `case 1 -> 10;` cung cấp trực tiếp giá trị `10`.
- `case 2 -> { ... yield 20 + bonus; }` chạy nhiều lệnh rồi cung cấp giá trị bằng `yield`.
- `default -> throw ...;` **không tạo giá trị**; nó kết thúc việc đánh giá biểu thức bằng cách ném ngoại lệ. Đó là một cách hoàn tất đột ngột hợp lệ.

**Biên của biểu thức** là vùng từ lúc bắt đầu đánh giá `switch` đến lúc nó trả ra giá trị hoặc bị ngắt bởi ngoại lệ. Một lệnh điều khiển trong nhánh không thể tùy tiện nhảy ra một vòng lặp, nhãn hay lời gọi phương thức nằm **bên ngoài** vùng này, bỏ qua nghĩa vụ cung cấp kết quả của biểu thức.

Điểm cần nhớ: quy tắc không đơn giản là “cấm mọi `break`/`continue`/`return` xuất hiện trong văn bản nhánh”. Trình biên dịch xét **đích thực sự** của lệnh nhảy. Nếu đích nằm hoàn toàn bên trong biểu thức, lệnh đó vẫn có thể hợp lệ.

## 2. Bốn nhóm chuyển điều khiển và giới hạn

| Lệnh / hình thức | Đích điều khiển | Khi nào hợp lệ trong `switch expression`? |
| --- | --- | --- |
| `case n -> expression;` | Giá trị của biểu thức nhánh | Hợp lệ nếu kiểu dữ liệu phù hợp với ngữ cảnh của `switch` |
| `yield expression;` | **Biểu thức `switch` gần nhất** bao quanh `yield` | Hợp lệ khi không phải nhảy xuyên qua ranh giới method/constructor/initializer/lambda; biểu thức `yield` không được có kiểu `void` |
| `throw exception;` | Lan truyền ngoại lệ đến nơi xử lý | Hợp lệ; nhánh có thể ném ngoại lệ thay vì trả giá trị |
| `break;` hoặc `break label;` | `switch statement` / vòng lặp / nhãn là đích `break` | Hợp lệ nếu đích nằm **bên trong** `switch expression`; không được dùng để thoát chính `switch expression` |
| `continue;` hoặc `continue label;` | Vòng lặp `for`/`while`/`do` là đích `continue` | Hợp lệ nếu vòng lặp đích nằm **bên trong** `switch expression`; không được tiếp tục vòng lặp bao ngoài |
| `return value;` / `return;` | Method, constructor hoặc lambda tương ứng | Không hợp lệ nếu phải nhảy xuyên qua `switch expression` để ra method; có thể hợp lệ trong **lambda lồng bên trong** khi chỉ trả về từ lambda đó |

### Phân biệt kết thúc bình thường với kết thúc đột ngột

Một lệnh `yield` làm khối lệnh bên trong kết thúc theo cơ chế chuyển điều khiển, **nhưng khiến toàn bộ `switch expression` hoàn thành bình thường với giá trị**. Một lệnh `throw` khiến toàn bộ biểu thức kết thúc đột ngột, không có giá trị để gán. `break` và `continue` có thể kết thúc vòng lặp hoặc `switch statement` lồng bên trong, sau đó nhánh vẫn có cơ hội tiếp tục đến `yield`.

Với nhánh dạng `case ... -> { ... }`, khối không được kết thúc bình thường mà không cung cấp kết quả. Ví dụ chỉ in log rồi hết khối sẽ gây lỗi biên dịch; phải có `yield`, một nhánh `throw` thích hợp hoặc cấu trúc không thể hoàn thành bình thường. Đừng hiểu sai thành “mọi nhánh luôn phải viết `yield`”: nhánh mũi tên trả biểu thức trực tiếp không cần `yield`.

## 3. Chương trình Java chạy được: đích điều khiển nằm ở đâu?

Ví dụ sau dùng các cấu trúc lồng nhau để làm rõ từng biên. Hãy lưu nguyên văn thành tệp **`SwitchBoundaryDemo.java`**.

```java
public final class SwitchBoundaryDemo {
    private SwitchBoundaryDemo() {
    }

    static String describe(int code) {
        return switch (code) {
            case 0 -> "ZERO";

            case 1 -> {
                int sum = 0;
                for (int i = 0; i < 5; i++) {
                    if (i % 2 == 0) {
                        continue; // Only continues the INNER for loop.
                    }
                    if (i == 3) {
                        break;    // Only exits the INNER for loop.
                    }
                    sum += i;
                }
                yield "LOOP=" + sum;
            }

            case 2 -> {
                int inner = switch (code + 1) {
                    case 3 -> {
                        yield 30; // Yields from the INNER switch.
                    }
                    default -> 0;
                };
                yield "NESTED=" + inner; // Yields from the OUTER switch.
            }

            case 3 -> {
                java.util.function.IntSupplier supplier = () -> {
                    return 7; // Returns from the lambda, not the method.
                };
                yield "LAMBDA=" + supplier.getAsInt();
            }

            default -> throw new IllegalArgumentException(
                    "unsupported " + code);
        };
    }

    public static void main(String[] args) {
        for (int code = 0; code <= 3; code++) {
            System.out.println(code + " => " + describe(code));
        }

        try {
            describe(-1);
        } catch (IllegalArgumentException ex) {
            System.out.println("-1 => " + ex.getMessage());
        }
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên (mã nguồn chỉ dùng tính năng đã ổn định trong Java 14):

```bash
javac --release 14 SwitchBoundaryDemo.java
java SwitchBoundaryDemo
```

**Stdout mong đợi chính xác:**

```text
0 => ZERO
1 => LOOP=1
2 => NESTED=30
3 => LAMBDA=7
-1 => unsupported -1
```

Giải thích từng ca:

1. **`code=0`:** nhánh mũi tên trả chuỗi trực tiếp; `return switch (...)` chỉ trả về từ method **sau khi biểu thức `switch` tính ra chuỗi**. `return` này đứng ngoài thân biểu thức nên hợp lệ.
2. **`code=1`:** `continue` bỏ qua các `i` chẵn trong vòng `for` *nằm bên trong* khối nhánh; tại `i=1` cộng `1` vào `sum`; tại `i=3`, `break` thoát chính vòng `for`. Sau đó `yield` trả `"LOOP=1"`. Không lệnh nào nhảy xuyên qua biên `switch expression`.
3. **`code=2`:** `yield 30` thuộc biểu thức `switch` **trong cùng**. Biểu thức trong trả `30` rồi gán cho `inner`; `yield "NESTED=" + inner` thuộc biểu thức `switch` **ngoài**. Không có cơ chế để một `yield` “nhảy tắt” qua một `switch expression` khác.
4. **`code=3`:** `return 7` nằm trong thân lambda `IntSupplier`. Nó trở về từ **lần gọi lambda**, không trở về từ `describe`. Vì đích nằm bên trong biểu thức `switch` ngoài nên hợp lệ; sau đó `yield` cung cấp chuỗi kết quả cho biểu thức ngoài.
5. **`code=-1`:** ngoại lệ thoát phép đánh giá `switch`; `catch` của method `main` nhận ngoại lệ và in thông điệp. Nhánh `default` không cần `yield` vì nó luôn ném ngoại lệ.

Khi đối chiếu mã, hãy khoanh vùng **toàn bộ biểu thức `switch`**, rồi xác định đích mỗi lệnh điều khiển. Chỉ nhìn thấy từ khóa `break` hoặc `return` chưa đủ để kết luận có lỗi.

## 4. Những trường hợp bị từ chối khi biên dịch

Tất cả đoạn trong mục này là **mã minh họa cố ý sai**, không ghép chúng vào `SwitchBoundaryDemo.java` để chạy. Dạng thông báo lỗi có thể khác nhau giữa các phiên bản `javac`; vấn đề chính là quy tắc ngôn ngữ bị vi phạm.

### 4.1. `return` từ method bên trong nhánh

```java
static int invalidReturn(int code) {
    return switch (code) {
        case 0 -> {
            return 10; // ERROR: would exit invalidReturn
                       // across the switch expression.
        }
        default -> 20;
    };
}
```

`return 10;` có đích là method `invalidReturn`, trong khi biểu thức `switch` bao quanh lệnh `return`. Lệnh này phải nhảy **qua** biểu thức nên bị cấm. Sửa bằng `yield 10;` hoặc viết trực tiếp `case 0 -> 10;`. `return switch (...)` ở ngoài thân biểu thức vẫn đúng như chương trình chạy ở mục 3.

### 4.2. `continue` đến vòng lặp bao ngoài

```java
for (int attempt = 0; attempt < 2; attempt++) {
    int result = switch (attempt) {
        case 0 -> {
            continue; // ERROR: would continue the OUTER for loop.
        }
        default -> 10;
    };
    System.out.println(result);
}
```

`continue` ở đây có đích là vòng `for` **bọc bên ngoài** biểu thức `switch`. Nó sẽ bỏ dở việc tính `result` nên bị cấm. Nếu cần bỏ qua cả lần lặp, hãy kiểm tra điều kiện **trước khi** bắt đầu đánh giá biểu thức `switch`:

```java
for (int attempt = 0; attempt < 2; attempt++) {
    if (attempt == 0) {
        continue; // Valid: outside the switch expression.
    }
    int result = switch (attempt) {
        default -> 10;
    };
    System.out.println(result);
}
```

Mã sửa là **đoạn trong method**; nếu chạy riêng vòng lặp này, nó in một dòng `10`.

### 4.3. `break` qua nhãn nằm bên ngoài

```java
outer: {
    int result = switch (code) {
        case 0 -> {
            break outer; // ERROR: the target is outside
                         // the switch expression.
        }
        default -> 10;
    };
    System.out.println(result);
}
```

`break outer;` cố thoát khối có nhãn `outer`, nhưng khối đích bao quanh cả biểu thức `switch`. Đây là chuyển điều khiển qua biên và bị cấm, ngay cả khi `break` có nhãn hợp lệ. Cách sửa là biến quyết định nhánh thành **giá trị**, sau đó thực hiện `break outer` nếu thật sự cần ở một câu lệnh **bên ngoài** biểu thức.

`break;` không nhãn cũng **không** dùng để “thoát switch expression”, vì biểu thức `switch` không phải đích của một `break`. Ngược lại, một `break` trong vòng lặp hoặc `switch statement` lồng **bên trong** nhánh là hợp lệ nếu chỉ thoát cấu trúc lồng đó.

### 4.4. Thiếu `yield` ở khối có thể kết thúc bình thường

```java
static int invalidNoValue(int code) {
    return switch (code) {
        case 0 -> {
            System.out.println("zero");
            // ERROR: this rule block may complete normally.
        }
        default -> 10;
    };
}
```

Mã đã chạy đến hết khối `case 0` mà không có giá trị cho biểu thức. Sửa bằng `yield 0;` ở cuối khối, hoặc bỏ khối và dùng `case 0 -> 0;` nếu không cần lệnh trung gian.

### 4.5. `yield` không thể nhảy xuyên qua lambda

```java
int result = switch (code) {
    case 0 -> {
        java.util.function.IntSupplier supplier = () -> {
            yield 7; // ERROR: yield target is outside the lambda.
        };
        yield supplier.getAsInt();
    }
    default -> 0;
};
```

`yield 7` tìm đích là biểu thức `switch` bên ngoài lambda; nhưng lambda nằm giữa, nên lệnh `yield` đó bị cấm. Nếu cần trả `7` từ lambda, dùng `return 7;`; sau đó đặt `yield supplier.getAsInt();` trong khối nhánh bên ngoài lambda (như mục 3). Khi có hai biểu thức `switch` lồng nhau, một `yield` có đích là **biểu thức trong gần nhất**, không “bỏ qua” nó để trả về từ biểu thức ngoài.

## 5. Những điểm dễ nhầm khi cấu trúc lồng nhau

### `switch statement` khác `switch expression`

Cả hai dạng vẫn được Java hỗ trợ. Trong **switch statement**, `break` không nhãn có thể kết thúc statement đó; statement không bắt buộc tạo giá trị. Trong **switch expression**, cần tạo ra giá trị và `break` không phải cơ chế tạo kết quả.

Đây là **đoạn mã hợp lệ đặt bên trong một method**, thể hiện `break` chỉ thoát `switch statement` lồng trong `switch expression`:

```java
int value = switch (code) {
    case 1 -> {
        int calculated;
        switch (code) { // A switch STATEMENT inside the expression.
            case 1:
                calculated = 100;
                break;   // Exits this inner switch statement only.
            default:
                calculated = -1;
        }
        yield calculated; // Completes the OUTER switch expression.
    }
    default -> 0;
};
```

Với `code=1`, kết quả `value` là `100`. `break` hợp lệ vì nó **không đi ra ngoài** `switch expression`. Một lệnh `break` chỉ thoát vòng `for` nằm trong nhánh hoạt động theo cùng nguyên tắc.

### `yield` khác `return` và `throw`

- `yield x;` tạo ra **giá trị của biểu thức `switch` gần nhất**; method chứa biểu thức vẫn tiếp tục chạy sau khi biểu thức hoàn tất, trừ khi câu lệnh bên ngoài là `return switch (...)`.
- `return x;` trả về từ method/constructor/lambda thích hợp; bị cấm nếu đích của nó nằm ngoài một biểu thức `switch` bao quanh.
- `throw e;` ném ngoại lệ và làm biểu thức `switch` thất bại theo đường ngoại lệ. Không yêu cầu tạo giá trị ở nhánh luôn ném.
- `break` và `continue` quản lý đích là statement/vòng lặp; **không thay thế `yield`**.

Một khối `try/finally` nằm trên đường thực thi vẫn tuân theo quy tắc Java: `finally` có thể chạy khi có `yield` hoặc `throw`. Nếu `finally` tự ném ngoại lệ, ngoại lệ đó có thể thay đổi kết quả cuối. Đừng coi `yield` là cách bỏ qua dọn dẹp tài nguyên.

### Quy trình đọc lỗi biên dịch

1. Xác định đoạn này là `switch expression` hay `switch statement`; kiểm tra nó đang được gán, truyền vào hàm hay trả về như **một giá trị**.
2. Tìm lệnh điều khiển đang gây lỗi (`break`, `continue`, `return`, `yield`) và xác định **đích theo quy tắc Java**, không chỉ nhìn độ thụt dòng.
3. Kiểm tra có `switch expression` nào nằm **giữa lệnh và đích** hay không. Với `yield`, cũng xét ranh giới lambda/method và biểu thức `switch` gần nhất.
4. Nếu lệnh nhảy ra ngoài biểu thức, đổi thiết kế: trước tiên **tính một giá trị hoặc ném ngoại lệ**, sau đó quyết định `return`/`break`/`continue` trong phạm vi ngoài, nơi lệnh có đích hợp lệ.
5. Nếu khối thiếu giá trị, bổ sung `yield` ở đường chạy cần thiết; nếu chỉ cần biểu thức đơn, ưu tiên `case -> expression` để mã dễ kiểm chứng.

## 6. Các lỗi thường gặp

| Nhầm lẫn | Hệ quả | Cách sửa |
| --- | --- | --- |
| “Cứ có `break` trong nhánh là sai” | Hiểu nhầm `break` hợp lệ trong vòng lặp / `switch statement` lồng | Nhìn đích của `break`; đích trong biểu thức là được |
| “`break;` có thể trả kết quả của biểu thức” | Không có giá trị cho phép gán/trả | Dùng `yield value;` hoặc `case -> value` |
| “`return` trong lambda cũng trả khỏi method chứa switch” | Nhầm phạm vi return | `return` của lambda chỉ kết thúc lambda; method ngoài không bị trả về |
| “Dùng `continue outer` để bỏ qua một lần lặp khi tính switch” | Bị cấm nếu đích vòng lặp bên ngoài biểu thức | Đưa `continue` ra ngoài biểu thức; hoặc để switch tạo giá trị rồi xử lý |
| “Mọi nhánh đều phải viết `yield`” | Viết thừa, dễ sai cấu trúc | `case -> expression` trực tiếp không cần `yield`; `throw` là đường thoát hợp lệ |
| “`yield` bên trong switch lồng trả cho switch ngoài” | Nhầm đích gần nhất | Dùng kết quả biểu thức trong và `yield` riêng ở biểu thức ngoài |
| “Không có lỗi compile vì method khai báo kiểu trả về đúng” | Vẫn vi phạm quy tắc chuyển điều khiển | Lỗi nằm ở đích nhảy qua biên, không phải chỉ ở kiểu trả về |

## 7. Bài thực hành có thể tự kiểm chứng

1. Viết `String category(int n)` bằng `return switch (n)`: `n=0` trả `"ZERO"`, `n=1` chạy một vòng lặp `for` *trong nhánh* rồi `yield "ONE"`, còn lại ném `IllegalArgumentException`. Biên dịch và chạy với `0,1,2`. Với đầu vào `2`, hãy bắt ngoại lệ ở vị trí gọi method.
2. Thay `yield "ONE"` thành `return "ONE"` ngay trong khối nhánh. Dự đoán kết quả **biên dịch**, lý giải đích của `return` và kiểm tra lại với `javac`. Sau đó khôi phục `yield`.
3. Chuyển vòng `for` từ bên trong nhánh ra **bao ngoài** biểu thức `switch` rồi để `continue` ở trong nhánh. Dự đoán quy tắc nào bị vi phạm. Sửa bằng cách đưa `continue` ra ngoài `switch expression`.
4. Tạo `switch expression` lồng nhau, mỗi biểu thức dùng `yield` đúng đích. Thử một `break` trong vòng lặp đặt trong nhánh của biểu thức trong và xác nhận nó chỉ thoát vòng lặp đó.

Một bài giải đạt yêu cầu khi chỉ ra được: **đích thật của mỗi lệnh**, cấu trúc nào nằm giữa lệnh và đích, **biểu thức `switch` nào sinh ra giá trị**, và điều gì xảy ra nếu nhánh chỉ ném ngoại lệ.

## Tài liệu đối chiếu

- [Java Language Specification, Java SE 25 — `14.15 (`break`), `14.16 (`continue`), `14.17 (`return`), `14.21 (`yield`)](https://docs.oracle.com/javase/specs/jls/se25/jls25.pdf).
- [Oracle — Switch Expressions and Statements](https://docs.oracle.com/en/java/javase/17/language/switch-expressions-and-statements.html), hướng dẫn các trường hợp `yield` và lệnh nhảy bị từ chối. Cú pháp cốt lõi được chuẩn hóa từ Java 14 và vẫn sử dụng trong các phiên bản hiện nay.

**Nguyên tắc xuyên suốt:** một `switch expression` phải tạo được kết quả để tiếp tục phép tính, hoặc kết thúc bằng ngoại lệ; các bước nhảy đến đích bên ngoài nó bị trình biên dịch ngăn chặn. Khi đích nằm hoàn toàn bên trong (vòng lặp, statement hoặc lambda lồng), bước nhảy vẫn có thể hợp lệ.