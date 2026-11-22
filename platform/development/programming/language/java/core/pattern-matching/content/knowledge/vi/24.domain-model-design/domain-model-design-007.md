# Visitor pattern và pattern switch trong thiết kế domain model (Java 21)

Khi xây dựng **domain model** có nhiều dạng đối tượng nhưng cùng một khái niệm nghiệp vụ, chúng ta thường cần thực hiện nhiều thao tác trên từng dạng: tính toán, kiểm tra, định dạng, chuyển đổi sang DTO, xuất báo cáo hoặc tạo mã. Hai cách tổ chức quen thuộc là **Visitor pattern** và **pattern matching for switch**.

- **Visitor pattern** dùng một đối tượng visitor định nghĩa thao tác theo từng kiểu cụ thể; phần tử của mô hình cung cấp phương thức `accept` để chuyển quyền xử lý cho visitor.
- **Pattern switch** dùng `switch` với *type patterns* hoặc *record patterns* để phân nhánh theo kiểu/cấu trúc dữ liệu ngay trong một phương thức. Với mô hình `sealed`, trình biên dịch có thể kiểm tra liệu mọi biến thể được xử lý hay chưa.

Cả hai đều giúp thay các chuỗi `instanceof` + cast dài bằng cấu trúc có chủ đích. Tuy nhiên, **chúng không đồng nhất về kiến trúc**: Visitor đưa hợp đồng xử lý vào domain type, trong khi pattern switch thường giữ thuật toán bên ngoài model và dựa vào các kiểu biến thể. Bài dùng **Java 21 trở lên**: `sealed` có từ Java 17, `record` ổn định từ Java 16, và pattern matching cho `switch` cùng record patterns ổn định từ Java 21 (JEP 441 và JEP 440).

## 1. Bài toán: một domain model có ba dạng biểu thức

Giả sử ứng dụng quản lý cây biểu thức số học. Ta có ba dạng:

- `Num(value)`: một số nguyên.
- `Add(left, right)`: tổng hai biểu thức.
- `Mul(left, right)`: tích hai biểu thức.

Ví dụ cây biểu thức `(2 + 3) * 4`:

```text
         Mul
        /   \
      Add   Num(4)
     /   \
  Num(2) Num(3)
```

Các thao tác có thể phát triển độc lập:

1. **Evaluate**: tính giá trị số (kết quả `20`).
2. **Print**: hiển thị biểu thức có ngoặc (`((2 + 3) * 4)`).
3. Tương lai có thể bổ sung kiểm tra điều kiện, phân tích thống kê hoặc chuyển sang một biểu diễn khác.

Một kiểu model tương thích với cả hai cách:

```java
sealed interface Expr permits Num, Add, Mul {
    <R> R accept(Visitor<R> visitor);
}

interface Visitor<R> {
    R visit(Num expr);
    R visit(Add expr);
    R visit(Mul expr);
}

record Num(int value) implements Expr {
    public <R> R accept(Visitor<R> visitor) {
        return visitor.visit(this);
    }
}

record Add(Expr left, Expr right) implements Expr {
    Add {
        java.util.Objects.requireNonNull(left, "left");
        java.util.Objects.requireNonNull(right, "right");
    }

    public <R> R accept(Visitor<R> visitor) {
        return visitor.visit(this);
    }
}

record Mul(Expr left, Expr right) implements Expr {
    Mul {
        java.util.Objects.requireNonNull(left, "left");
        java.util.Objects.requireNonNull(right, "right");
    }

    public <R> R accept(Visitor<R> visitor) {
        return visitor.visit(this);
    }
}
```

Các khai báo trên là **đoạn mã thành phần**; để chạy trực tiếp, dùng lớp hoàn chỉnh ở mục 9.

Giải thích các lựa chọn thiết kế:

- `sealed interface Expr permits Num, Add, Mul` giới hạn các lớp trực tiếp được phép triển khai `Expr`. Trong mô hình minh họa, ba record đều mặc định là `final`, nên tập biến thể đã được đóng.
- `record` biểu diễn dữ liệu gọn với các thành phần và accessor như `value()`, `left()`, `right()`.
- `Add` và `Mul` kiểm tra `left/right` trong compact constructor để cây không có nhánh con bằng `null`. Quy tắc này được thiết lập **chủ động bởi domain**, không tự có chỉ vì dùng record.
- `accept` là phần phục vụ Visitor. Nếu chọn thiết kế **chỉ dùng pattern switch**, interface và các record có thể bỏ `accept` cùng `Visitor` mà vẫn giữ các thành phần dữ liệu và ràng buộc `sealed`.

Model `sealed` hợp lý khi số loại biểu thức được kiểm soát trong cùng thư viện và người viết muốn compiler báo thiếu case khi thêm một dạng mới. Nếu bộ kiểu cần cho plugin bên ngoài tự do mở rộng, mô hình đóng như trên có thể không phù hợp.

## 2. Visitor pattern: tách thao tác khỏi cấu trúc dữ liệu

### Hợp đồng Visitor

`Visitor<R>` là giao diện có một phương thức xử lý cho **từng biến thể** của `Expr`:

```java
interface Visitor<R> {
    R visit(Num expr);
    R visit(Add expr);
    R visit(Mul expr);
}
```

`R` là kiểu kết quả của thao tác: `Integer` nếu muốn tính giá trị, `String` nếu muốn in biểu thức, hoặc một kiểu DTO khác.

Một visitor để đánh giá giá trị:

```java
static final class EvalVisitor implements Visitor<Integer> {
    public Integer visit(Num expr) {
        return expr.value();
    }

    public Integer visit(Add expr) {
        return Math.addExact(expr.left().accept(this),
                             expr.right().accept(this));
    }

    public Integer visit(Mul expr) {
        return Math.multiplyExact(expr.left().accept(this),
                                  expr.right().accept(this));
    }
}
```

Phần `visit(Add)` gọi `accept(this)` của hai nhánh con và cộng kết quả. `visit(Mul)` làm tương tự với phép nhân. `Math.addExact` và `Math.multiplyExact` ném `ArithmeticException` nếu số nguyên `int` bị tràn; điều này giúp hai cách triển khai trong bài dùng cùng một quy tắc về overflow.

### Double dispatch hoạt động thế nào?

Điểm khác biệt quan trọng của Visitor là **double dispatch**. Với:

```java
Expr tree = new Add(new Num(2), new Num(3));
int answer = tree.accept(new EvalVisitor());
```

Luồng gọi:

1. `tree.accept(...)` được chọn theo **kiểu runtime** của phần tử, ở đây là `Add`.
2. Bên trong `Add.accept`, mã gọi `visitor.visit(this)`. Đối số `this` tại đây có kiểu `Add`, nên trình biên dịch chọn overload `visit(Add)`.
3. Lời gọi tới implementation của `EvalVisitor` thực hiện phép cộng; hai nhánh con lại gọi `accept` trên chính chúng.

Vì vậy, người gọi không cần viết chuỗi `if (expr instanceof Add) ...` và cũng không cần cast đối tượng về `Add`. Chi tiết: việc **chọn overload `visit(Add)`** dựa trên kiểu tĩnh `Add` của `this` trong `Add.accept`, còn việc gọi implementation của visitor dùng cơ chế virtual dispatch thông thường. Đây là ý nghĩa thực tế của “double dispatch” trong mẫu này.

### Thêm một Visitor mới

Nếu cần in công thức thay vì tính toán, chỉ cần một lớp mới triển khai `Visitor<String>`:

```java
static final class PrintVisitor implements Visitor<String> {
    public String visit(Num expr) {
        return Integer.toString(expr.value());
    }

    public String visit(Add expr) {
        return "(" + expr.left().accept(this) + " + "
                   + expr.right().accept(this) + ")";
    }

    public String visit(Mul expr) {
        return "(" + expr.left().accept(this) + " * "
                   + expr.right().accept(this) + ")";
    }
}
```

Cùng một cây:

```java
Expr tree = new Mul(
        new Add(new Num(2), new Num(3)),
        new Num(4));
System.out.println(tree.accept(new EvalVisitor()));  // 20
System.out.println(tree.accept(new PrintVisitor())); // ((2 + 3) * 4)
```

Đây là ưu điểm chính của Visitor: **thêm một thao tác** bằng cách tạo visitor mới mà không phải bổ sung phương thức nghiệp vụ tương ứng vào từng loại record. Đổi lại, mỗi loại model phải có `accept` và hệ thống duy trì hợp đồng `Visitor`.

## 3. Pattern switch: biểu diễn thao tác bằng một switch expression

Từ Java 21, có thể tính giá trị cây bằng `switch` kết hợp **record patterns**:

```java
static int evalBySwitch(Expr expr) {
    return switch (expr) {
        case Num(int value) -> value;
        case Add(var left, var right) ->
                Math.addExact(evalBySwitch(left), evalBySwitch(right));
        case Mul(var left, var right) ->
                Math.multiplyExact(evalBySwitch(left), evalBySwitch(right));
    };
}
```

Lợi ích nổi bật:

- `case Num(int value)` kiểm tra một record `Num` và lấy trực tiếp `value`, không cần `Num n = (Num) expr`.
- `case Add(var left, var right)` tách hai thành phần kiểu `Expr`; `var` **suy luận kiểu tĩnh** từ khai báo record.
- Với mỗi nhánh, `evalBySwitch` gọi đệ quy trên các biểu thức con. Thuật toán tương đương về kết quả với `EvalVisitor`.
- Không cần `visit` hoặc `accept` nếu kiến trúc không sử dụng Visitor.
- Không có `default`: vì `Expr` là `sealed` và cả ba biến thể `Num`, `Add`, `Mul` đã được xử lý, compiler có thể chứng minh **switch expression exhaustive** cho các giá trị `Expr` khác `null`.

Đây không phải chỉ là chuỗi cast được viết lại. Trình biên dịch hiểu **pattern variables** có phạm vi hợp lệ trong nhánh `case` tương ứng, nên `left`, `right`, `value` đã được ràng buộc trước khi sử dụng.

### Type pattern hay record pattern trong switch?

Nếu cần cả đối tượng record, dùng **type pattern**:

```java
static int readNum(Object value) {
    return switch (value) {
        case Num num -> num.value();
        default -> -1;
    };
}
```

Nếu cần trực tiếp thành phần, dùng **record pattern**:

```java
static int readNumParts(Object value) {
    return switch (value) {
        case Num(int number) -> number;
        default -> -1;
    };
}
```

Hai phương thức trên là **ví dụ minh họa** cần được đặt vào lớp có record `Num`. Cả hai nhận `Num` và trả số nguyên của nó. Tuy nhiên, với `switch (value)` mà `value == null`, các ví dụ trên không có `case null` nên sẽ ném `NullPointerException`; `default` không bắt selector `null` một cách mặc định. Điều này khác phép `instanceof`, vốn trả `false` cho `null`.

## 4. Tính exhaustive khi domain model được sealed

Giả sử `Expr` chỉ có ba kiểu được liệt kê trong `permits`, và các lớp con đều `final`. Khi dùng `switch` trên `Expr`, compiler biết tập trường hợp cần xử lý.

```java
return switch (expr) {
    case Num(int value) -> value;
    case Add(var left, var right) -> evalBySwitch(left) + evalBySwitch(right);
    case Mul(var left, var right) -> evalBySwitch(left) * evalBySwitch(right);
};
```

*Đây là đoạn minh họa cấu trúc; chương trình đầy đủ dùng `Math.addExact`/`Math.multiplyExact` để phát hiện overflow.*

Nếu sau này thêm một biến thể mới, ví dụ `Negate(Expr child)`, và cập nhật `permits` tương ứng, `switch` không có `default` thường sẽ bị compiler cảnh báo lỗi **không exhaustive** cho tới khi bổ sung case `Negate(...)`. Điều này giúp tìm ra các thuật toán cần sửa khi domain tiến hóa.

Với Visitor, nếu mở rộng `Visitor<R>` thêm phương thức `visit(Negate expr)`, các implementation cụ thể như `EvalVisitor`, `PrintVisitor` cũng phải cập nhật để thực hiện hợp đồng mới. `accept` của biến thể mới sẽ gọi overload phù hợp. **Cả hai cách đều có cơ chế phát hiện thiếu xử lý, nhưng vị trí lỗi biên dịch khác nhau.**

**Không nên thêm `default` chỉ để làm im compiler** khi tập biến thể thật sự được kiểm soát bởi `sealed`: nhánh `default` có thể che tình trạng chưa hỗ trợ kiểu mới. Chỉ thêm fallback khi domain thực sự đòi hỏi một hành vi hợp lệ cho các kiểu không được liệt kê, hoặc mô hình cho phép mở rộng không đóng.

### Guard when và thứ tự case

Pattern switch cũng cho phép điều kiện bổ sung:

```java
static String describeNumber(Expr expr) {
    return switch (expr) {
        case Num(int value) when value < 0 -> "negative";
        case Num(int value) -> "number=" + value;
        case Add(var l, var r) -> "addition";
        case Mul(var l, var r) -> "multiplication";
    };
}
```

Đoạn này là **phương thức minh họa** dành cho cùng model. Nhánh `Num` có `when` đứng trước nhánh `Num` tổng quát; nếu đảo ngược, nhánh rộng có thể che nhánh cụ thể và Java báo lỗi *dominance*.

Một nhánh có guard `when value < 0` **không tự bao phủ mọi `Num`**. Vì vậy, nhánh `Num(int value)` không có guard (hoặc một cách xử lý đủ rộng khác) vẫn cần để bảo đảm switch exhaustive.

## 5. Null và ràng buộc bất biến của domain

Có hai kiểu `null` cần xử lý tách biệt.

### Null ở selector của switch

Với phương thức `evalBySwitch(Expr expr)` ở trên, gọi:

```java
evalBySwitch(null);
```

sẽ ném `NullPointerException` vì `switch` pattern matching không có `case null`. Nếu `null` được phép và có ý nghĩa nghiệp vụ, hãy chỉ rõ:

```java
static String kindOrMissing(Expr expr) {
    return switch (expr) {
        case null -> "none";
        case Num(var value) -> "number";
        case Add(var left, var right) -> "addition";
        case Mul(var left, var right) -> "multiplication";
    };
}
```

Còn với Visitor, gọi `expr.accept(visitor)` khi `expr == null` cũng ném `NullPointerException` tại lời gọi phương thức. Nếu hai thuật toán phải có cùng chính sách đối với `null`, cần thiết kế hợp đồng chung và xử lý rõ ở lớp gọi.

### Null ở record con

`record Add(Expr left, Expr right)` mặc định không tự cấm tham chiếu `null`. Trong model của bài, **compact constructor** kiểm tra `Objects.requireNonNull(left, "left")` và tương tự cho `right`, nên `new Add(null, new Num(1))` bị từ chối ngay lúc tạo.

Đây là **bất biến của domain**. Nhờ nó, thuật toán Visitor và pattern switch đệ quy có thể giả định các nhánh của `Add`/`Mul` hợp lệ. Nếu bỏ kiểm tra trong constructor, record pattern `Add(var left, var right)` vẫn có thể khớp một `Add` với `left == null`: `var left` là *component pattern* có thể nhận `null`. Khi đó phép đệ quy `evalBySwitch(left)` sẽ gặp selector `null` và ném exception. Do đó **khớp record pattern không đồng nghĩa toàn bộ thành phần record đều khác null**.

## 6. Visitor và pattern switch: điểm mạnh, giới hạn

| Tiêu chí | Visitor pattern | Pattern switch trên sealed/record |
| --- | --- | --- |
| Nơi định nghĩa hành vi | Các lớp `Visitor` riêng; `Expr` cần `accept` | Trong hàm chứa `switch`, thường nằm ngoài domain types |
| Chọn nhánh xử lý | `accept` + `visit` (double dispatch) | Runtime pattern matching qua `case` |
| Thêm thao tác mới | Tạo implementation `Visitor<R>` mới | Tạo phương thức hoặc service có `switch` mới |
| Thêm biến thể domain | Sửa interface visitor, visitor implementations, `accept` của biến thể mới | Thêm subtype, sửa những exhaustive switch chưa xử lý subtype |
| Boilerplate | Nhiều phương thức `accept`/`visit` | Ít boilerplate với `record` và `sealed` |
| Kết quả mỗi thao tác | Kiểu `R` của `Visitor<R>` | Kiểu trả về của hàm/`switch expression` |
| Null selector | Gọi `null.accept(...)` ném NPE | `switch(null)` ném NPE nếu không có `case null` |
| Bảo đảm đầy đủ | Compiler kiểm tra phương thức cần implement theo hợp đồng visitor | Compiler kiểm tra exhaustiveness/dominance của switch |
| Phiên bản ngôn ngữ | Mẫu Visitor sử dụng được từ các phiên bản Java cũ | Ví dụ có record patterns và pattern switch yêu cầu Java 21+ |

Đây là so sánh **cách tổ chức code**, không phải khẳng định một cách luôn nhanh hơn cách kia. Hiệu năng thực tế phụ thuộc cấu trúc cây, lượng cấp phát, JIT, triển khai visitor và khối lượng thuật toán; nên đo benchmark đại diện nếu hiệu năng là mối quan tâm thật.

### Khi nên chọn Visitor

Visitor hợp lý khi:

- Có nhiều thao tác độc lập trên một nhóm kiểu tương đối ổn định.
- Muốn biểu diễn các thao tác thành đối tượng có thể cấu hình, tiêm dependency, lưu trạng thái hoặc sử dụng chung qua API.
- Model cũ đã công khai hợp đồng `accept`/`Visitor` và nhiều thành phần hệ thống phụ thuộc vào hợp đồng này.
- Dự án vẫn phải hỗ trợ một phiên bản Java trước Java 21, nên không thể dùng pattern switch hiện đại.

**Đánh đổi:** mỗi biến thể cần triển khai `accept`; khi thêm một biến thể vào giao diện visitor, phải cập nhật các visitor tương ứng.

### Khi nên chọn pattern switch

Pattern switch thường hợp lý khi:

- Domain là một **tập biến thể đóng** được mô tả bằng `sealed interface`/`sealed class`.
- Các biến thể phần lớn là dữ liệu (`record`) và cần thuật toán thuần, không cần thêm phương thức dispatch vào chúng.
- Muốn đọc logic tại một nơi, nhìn trực tiếp từng nhánh và để compiler kiểm tra thiếu case.
- Dự án dùng Java 21+ và các thuật toán có thể triển khai bằng những hàm/service nhỏ, dễ test.

**Đánh đổi:** mỗi thao tác vẫn cần một bộ case riêng. Nếu cấu trúc cây rất sâu hoặc logic phức tạp, nên tách các hàm phụ, tránh biến một `switch` thành khối mã khổng lồ.

### Có thể dùng cả hai không?

Có. Ví dụ của bài cố ý dùng **cùng một model** có `accept` cho Visitor và cũng dùng `evalBySwitch` bên ngoài. Điều này hữu ích khi đang **di trú dần từ mã Visitor cũ sang pattern switch** hoặc cần so sánh kết quả.

Tuy nhiên, không nên bắt mọi domain type triển khai Visitor chỉ để sau đó không bao giờ dùng `accept`. Chọn một hướng làm mặc định cho module; duy trì song song khi có mục tiêu cụ thể và có test đối chiếu hành vi.

## 7. Tránh các refactor làm thay đổi ngữ nghĩa

Khi đổi Visitor sang pattern switch (hoặc ngược lại), không chỉ đối chiếu kết quả cho một cây đơn giản. Cần xét:

1. **Thứ tự duyệt cây.** Phép cộng và nhân trong demo xét nhánh trái rồi nhánh phải. Nếu các phép xử lý có tác dụng phụ, việc đảo thứ tự sẽ làm thay đổi hành vi.
2. **Ràng buộc null.** Dữ liệu bất biến `left/right != null` nằm ở constructor; nếu một cách xử lý null im lặng còn cách kia ném exception, hai thuật toán chưa tương đương.
3. **Overflow và lỗi nghiệp vụ.** Cả Visitor lẫn switch trong bài dùng `Math.addExact`/`Math.multiplyExact`; thay bằng `+` và `*` có thể làm thay đổi kết quả khi tràn `int`.
4. **Những subtype được phép.** `sealed` đóng tập biến thể; nếu domain mở rộng qua plugin, cần thiết kế cơ chế mở rộng thay vì một bộ case đóng.
5. **Trạng thái visitor.** Một visitor có thể giữ trạng thái, cache hoặc phụ thuộc dịch vụ. Đổi thành hàm `switch` thuần có thể cần chuyển trạng thái đó sang tham số hay một service.
6. **Ngoại lệ và logging.** Giữ thứ tự, thông điệp và chính sách lỗi khi đó là phần contract.
7. **Tính exhaustive.** Đừng dùng `default` rộng để che những subtype mới vừa thêm.

Đối với ứng dụng lớn, nên kiểm thử cùng một bộ cây (cây một nút, cây lồng sâu, số âm, số 0, giá trị biên, tình huống lỗi) trước khi loại bỏ Visitor cũ.

## 8. Chương trình Java 21 hoàn chỉnh: hai cách trên cùng domain

Lưu tệp **`VisitorVsPatternSwitch.java`**:

```java
public class VisitorVsPatternSwitch {
    sealed interface Expr permits Num, Add, Mul {
        <R> R accept(Visitor<R> visitor);
    }

    interface Visitor<R> {
        R visit(Num expr);
        R visit(Add expr);
        R visit(Mul expr);
    }

    record Num(int value) implements Expr {
        public <R> R accept(Visitor<R> visitor) {
            return visitor.visit(this);
        }
    }

    record Add(Expr left, Expr right) implements Expr {
        Add {
            java.util.Objects.requireNonNull(left, "left");
            java.util.Objects.requireNonNull(right, "right");
        }

        public <R> R accept(Visitor<R> visitor) {
            return visitor.visit(this);
        }
    }

    record Mul(Expr left, Expr right) implements Expr {
        Mul {
            java.util.Objects.requireNonNull(left, "left");
            java.util.Objects.requireNonNull(right, "right");
        }

        public <R> R accept(Visitor<R> visitor) {
            return visitor.visit(this);
        }
    }

    static final class EvalVisitor implements Visitor<Integer> {
        public Integer visit(Num expr) {
            return expr.value();
        }

        public Integer visit(Add expr) {
            return Math.addExact(expr.left().accept(this),
                                 expr.right().accept(this));
        }

        public Integer visit(Mul expr) {
            return Math.multiplyExact(expr.left().accept(this),
                                      expr.right().accept(this));
        }
    }

    static final class PrintVisitor implements Visitor<String> {
        public String visit(Num expr) {
            return Integer.toString(expr.value());
        }

        public String visit(Add expr) {
            return "(" + expr.left().accept(this) + " + "
                       + expr.right().accept(this) + ")";
        }

        public String visit(Mul expr) {
            return "(" + expr.left().accept(this) + " * "
                       + expr.right().accept(this) + ")";
        }
    }

    static int evalBySwitch(Expr expr) {
        return switch (expr) {
            case Num(int value) -> value;
            case Add(var left, var right) ->
                    Math.addExact(evalBySwitch(left), evalBySwitch(right));
            case Mul(var left, var right) ->
                    Math.multiplyExact(evalBySwitch(left), evalBySwitch(right));
        };
    }

    static String kindOrMissing(Expr expr) {
        return switch (expr) {
            case null -> "none";
            case Num(var value) -> "number";
            case Add(var left, var right) -> "addition";
            case Mul(var left, var right) -> "multiplication";
        };
    }

    public static void main(String[] args) {
        Expr tree = new Mul(
                new Add(new Num(2), new Num(3)),
                new Num(4));
        int visitorValue = tree.accept(new EvalVisitor());
        int switchValue = evalBySwitch(tree);

        System.out.println("visitor eval=" + visitorValue);
        System.out.println("switch eval=" + switchValue);
        System.out.println("visitor format=" + tree.accept(new PrintVisitor()));
        System.out.println("same=" + (visitorValue == switchValue));
        System.out.println("zero=" + evalBySwitch(new Add(new Num(-5), new Num(5))));
        System.out.println("kind=" + kindOrMissing(tree));
        System.out.println("null kind=" + kindOrMissing(null));

        try {
            evalBySwitch(null);
        } catch (NullPointerException ex) {
            System.out.println("null eval rejected");
        }

        try {
            new Add(null, new Num(1));
        } catch (NullPointerException ex) {
            System.out.println("null child rejected=" + ex.getMessage());
        }
    }
}
```

Biên dịch và chạy bằng **JDK 21 hoặc mới hơn**:

```bash
javac --release 21 -encoding UTF-8 VisitorVsPatternSwitch.java
java VisitorVsPatternSwitch
```

**Stdout chính xác:**

```text
visitor eval=20
switch eval=20
visitor format=((2 + 3) * 4)
same=true
zero=0
kind=multiplication
null kind=none
null eval rejected
null child rejected=left
```

Giải thích:

- Cây `Mul(Add(Num(2), Num(3)), Num(4))` tạo phép tính `(2 + 3) * 4`. `EvalVisitor` và `evalBySwitch` cùng trả `20`.
- `PrintVisitor` định dạng cây theo thứ tự đệ quy thành `((2 + 3) * 4)`.
- `same=true` đối chiếu hai thuật toán trên cùng đầu vào; `zero=0` cho thấy trường hợp tổng số âm và số dương.
- `kindOrMissing(tree)` nhận diện kiểu `Mul`; `kindOrMissing(null)` dùng nhánh `case null`.
- `evalBySwitch(null)` không có nhánh `case null` nên phát sinh `NullPointerException` được bắt, in `null eval rejected`.
- Constructor của `Add` dùng `Objects.requireNonNull(left,"left")`, nên thử tạo `Add(null,...)` bị từ chối với thông điệp `left`.

Chương trình được kiểm chứng bằng `javac --release 21` và chạy thực tế với kết quả như trên.

## 9. Các lỗi phổ biến

1. **Nhầm Visitor và pattern switch là cùng một cú pháp.** Visitor là mẫu thiết kế dựa trên giao diện, phương thức `accept`/`visit`; pattern switch là tính năng của ngôn ngữ Java 21.
2. **Giữ một model mở nhưng mong switch luôn exhaustive mà không cần fallback.** `sealed` làm rõ tập subtype; nếu một nhánh subtype tiếp tục mở rộng (`non-sealed`), yêu cầu phân loại cần tính đến các giá trị có thể thuộc nhánh mở ấy.
3. **Thêm `default` để né lỗi khi model thêm subtype.** Điều đó làm mất cơ hội compiler buộc xử lý biến thể mới. Nên bổ sung case cụ thể nếu đó là hướng thiết kế.
4. **Đặt case rộng trước case cụ thể.** `case Expr e` có thể che các case `Num(...)`, `Add(...)` phía sau; nhánh bị che có thể khiến compiler báo lỗi dominance.
5. **Nghĩ `case null` ở một switch sẽ xử lý null ở mọi thành phần.** `case null` chỉ bắt **selector** của chính `switch`. Thành phần record cần chính sách riêng.
6. **Cho rằng record pattern không bao giờ tách ra `null`.** Component pattern `var left` có thể nhận một thành phần tham chiếu `null`. Hãy ràng buộc đầu vào bằng constructor hoặc kiểm tra trước khi đệ quy.
7. **Không dùng `public` cho `accept` khi triển khai interface.** Phương thức của interface là `public`; implementation của record cũng phải cung cấp phương thức có phạm vi truy cập tương thích.
8. **Bỏ sót `visit` khi thêm subtype.** Visitor interface và mọi implementation phải được bảo trì để hỗ trợ kiểu mới.
9. **Nhầm `var` với kiểu động.** Trong `Add(var left,var right)`, compiler suy ra `left` và `right` có kiểu `Expr` từ định nghĩa record; giá trị runtime được xét khi khớp.
10. **So sánh Visitor và switch chỉ bằng một happy path.** Cần kiểm tra null, nested cases, overflow, exception và kết quả định dạng.
11. **Chạy mã dùng record pattern trên Java 17 và mong được hỗ trợ mặc định.** `switch` pattern matching và record pattern trong bài yêu cầu Java 21+.

## 10. Bài tập áp dụng

**Bài 1.** Vì sao `evalBySwitch` không cần `default` trong ví dụ?

*Đáp án:* `Expr` là `sealed` chỉ cho phép ba record `Num`, `Add`, `Mul` ở cấp trực tiếp, và chúng đều là biến thể cuối; mọi dạng khác `null` của `Expr` đều được các case tương ứng xử lý.

**Bài 2.** Nếu thêm `record Negate(Expr child) implements Expr` vào mô hình và đưa vào `permits`, cần chú ý điều gì?

*Đáp án:* Bổ sung `case Negate(...)` cho các exhaustive switch; với Visitor cần mở rộng hợp đồng `visit(Negate)`, cập nhật các visitor implementations và triển khai `accept` của record mới. Đồng thời đặt quy tắc `child != null` nếu domain yêu cầu.

**Bài 3.** Tại sao `record Add(Expr left, Expr right)` có `Objects.requireNonNull` trong constructor, trong khi bản thân record pattern `Add(var left,var right)` vẫn có thể khớp null component?

*Đáp án:* Constructor chủ động bảo đảm bất biến **khi tạo đối tượng**. `Add(var left,var right)` chỉ tách thành phần; một `var` component pattern không loại bỏ `null` nếu dữ liệu cho phép. Trong chương trình đã cho, constructor chặn việc tạo `Add` với nhánh null qua đường khởi tạo thông thường.

**Bài 4.** Cùng một model có thể dùng `PrintVisitor` và `evalBySwitch` không?

*Đáp án:* Có. Một thao tác được thực hiện qua `accept/visit`, thao tác kia qua `switch`; các lớp con không bắt buộc thay đổi. Tuy nhiên nên tránh duy trì hai hệ thống xử lý trùng lặp lâu dài nếu không có nhu cầu cụ thể.

**Bài 5.** Hãy tự viết `sizeBySwitch(Expr expr)` trả số nút trong cây. Với `Mul(Add(Num(2), Num(3)), Num(4))`, kết quả phải bằng **5**.

*Gợi ý:*

```java
static int sizeBySwitch(Expr expr) {
    return switch (expr) {
        case Num(var value) -> 1;
        case Add(var left, var right) ->
                1 + sizeBySwitch(left) + sizeBySwitch(right);
        case Mul(var left, var right) ->
                1 + sizeBySwitch(left) + sizeBySwitch(right);
    };
}
```

Đoạn này là phương thức bổ sung vào lớp có các record đã khai báo, không phải tệp Java độc lập.

**Tài liệu chính thức:** [JEP 409 – Sealed Classes](https://openjdk.org/jeps/409), [JEP 395 – Records](https://openjdk.org/jeps/395), [JEP 440 – Record Patterns](https://openjdk.org/jeps/440), [JEP 441 – Pattern Matching for switch](https://openjdk.org/jeps/441), [Oracle Java 21 – Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html), [Oracle Java 21 – Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html).
