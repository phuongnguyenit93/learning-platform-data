# Dạng mũi tên `->` và phạm vi của khối nhánh trong Java

> **Java core — language-basics / Switch**  
> **Môi trường:** JDK 17+, không bật preview, không dùng thư viện ngoài.  
> **Mục tiêu:** Viết đúng `switch` dạng `case ... ->`, phân biệt `switch` **statement** và **expression**, hiểu phạm vi biến trong mỗi khối `{ ... }`, biết khi nào cần `yield` và vì sao không xảy ra *fall-through* như dạng `case ...:`.

## 1. Quy tắc cơ bản của dạng mũi tên

Dạng truyền thống sử dụng nhãn `case ...:` và thường cần `break`. Dạng mũi tên `case ... ->` được hỗ trợ chính thức ở Java 17 và **chỉ chạy nhánh được chọn**, không tự chuyển sang mã của nhánh tiếp theo:

~~~java
int code = 2;
switch (code) {
    case 1 -> System.out.println("ONE");
    case 2 -> System.out.println("TWO");
    default -> System.out.println("OTHER");
}
// Chỉ in TWO.
~~~

Cấu trúc `switch` này là một **statement**, tức thao tác điều khiển, không phải biểu thức trả về giá trị.

Một nhánh mũi tên trong switch statement có thể là một **statement expression** (ví dụ lời gọi phương thức), **block `{...}`** hoặc câu lệnh `throw`. Nếu phải thực hiện nhiều câu lệnh trong nhánh, đặt chúng trong một khối:

~~~java
switch (code) {
    case 1 -> {
        System.out.println("ONE");
        System.out.println("Audited");
    }
    case 2 -> System.out.println("TWO");
    default -> System.out.println("OTHER");
}
~~~

Không cần `break` sau nhánh `->`. Việc thêm ngoặc nhọn là để nhóm nhiều câu lệnh và xác định phạm vi biến, **không phải để ngăn fall-through** như dạng `:`.

## 2. Statement và expression đều có thể dùng `->`

`switch (code) { case 1 -> System.out.println("ONE"); default -> System.out.println("OTHER"); }` là **statement** thực hiện thao tác. Ngược lại, `String label = switch (code) { case 1 -> "ONE"; default -> "OTHER"; };` là **expression** tạo giá trị.

Cả hai đều không fall-through. Expression còn phải bao phủ các trường hợp và tạo kết quả đúng kiểu; những bài sau phân tích riêng điều này. Ở đây trọng tâm là rule mũi tên và phạm vi biến.

## 3. Phạm vi biến cục bộ của khối nhánh

Mỗi khối `{ ... }` của một nhánh mũi tên là một **phạm vi cục bộ riêng**:

~~~java
int code = 1;
switch (code) {
    case 1 -> {
        int amount = 10;
        System.out.println(amount);
    }
    case 2 -> {
        int amount = 20; // HỢP LỆ: biến khác, trong khối khác.
        System.out.println(amount);
    }
    default -> System.out.println("OTHER");
}
~~~

Biến `amount` của nhánh 1 không nhìn thấy ở nhánh 2 hoặc sau `switch`. Nhánh 2 có thể khai báo **tên giống hệt** vì phạm vi hai biến không giao nhau. Biến cục bộ chỉ tồn tại trong **khối khai báo của nó**; nó không tự trở thành biến dùng chung giữa các case.

~~~java
// KHÔNG BIÊN DỊCH nếu đặt sau switch ở ví dụ trên:
// System.out.println(amount); // Cannot find symbol.
~~~

Nếu dữ liệu phải được sử dụng **sau `switch`**, chọn một trong hai cách:

- Với dữ liệu là **một giá trị**, ưu tiên `String result = switch (...) { ... };`.
- Với statement cần cập nhật biến có sẵn, khai báo biến ngoài switch rồi gán rõ ràng theo từng nhánh; đảm bảo mọi đường đi cần thiết đều gán giá trị.

Không dựa vào thụt lề để tạo scope: Java dựa vào dấu `{ }` và vị trí khai báo. Việc dùng cùng tên ở nhiều nhánh giúp minh họa phạm vi, nhưng thực tế vẫn nên đặt tên có ý nghĩa.

## 4. Khi block cần trả giá trị

Trong switch expression, nhánh đơn có thể là `case 0 -> "ZERO";`. Nếu nhánh cần nhiều lệnh, block trả kết quả qua `yield`:

~~~java
String result = switch (code) {
    case 2 -> {
        int scaled = code * 10;
        yield "GROUP-" + scaled;
    }
    default -> "OTHER";
};
~~~

Switch statement có block thì chỉ thực hiện lệnh và **không cần** `yield`. Bài `yield` phân tích đường đi, `break` và `throw` chi tiết hơn.

## 5. Gộp nhãn, `default`, `throw` và nhánh không được chọn

Có thể nhóm nhiều giá trị khác nhau trên một nhánh mũi tên:

~~~java
String group = switch (code) {
    case 1, 2 -> "SMALL";
    case 3 -> "THREE";
    default -> "OTHER";
};
~~~

`case 1, 2` không chạy nhánh hai lần; đó là **một nhánh** được chọn khi code là 1 **hoặc** 2. Các nhãn trùng giá trị trong cùng switch bị từ chối khi biên dịch.

Một nhánh biểu thức có thể ném ngoại lệ, thay vì tạo giá trị:

~~~java
static String positiveLabel(int value) {
    return switch (value) {
        case -1 -> throw new IllegalArgumentException("negative");
        case 0 -> "ZERO";
        default -> {
            int twice = value * 2;
            yield "DOUBLE=" + twice;
        }
    };
}
~~~

Nếu `value == 0` thì **không chạy** khối `default`. Nếu `value == -1` thì ném ngoại lệ từ nhánh được chọn. Trong cả hai trường hợp, Java không chạy mã của nhánh khác chỉ vì nó xuất hiện bên dưới.

Trong Java 17 không bật preview, selector `String`/`enum`/wrapper có giá trị `null` có thể gây `NullPointerException`; `default` không tự bắt null. Hãy kiểm tra null trước nếu dữ liệu cho phép vắng mặt.

## 6. So sánh phạm vi và fall-through với dạng dấu hai chấm

`switch` dạng dấu hai chấm dùng **nhóm câu lệnh** `case ...:`; nếu thiếu `break`, mã có thể chạy xuyên tới nhóm tiếp theo:

~~~java
static String colonDemo(int code) {
    StringBuilder log = new StringBuilder();
    switch (code) {
        case 1:
            log.append("ONE");
        case 2:
            log.append("+TWO");
            break;
        default:
            log.append("OTHER");
    }
    return log.toString();
}
// colonDemo(1) = "ONE+TWO" (fall-through).
// colonDemo(2) = "+TWO".
~~~

Ngược lại, `case 1 -> log.append("ONE");` trong switch statement mũi tên **không** tự thực hiện case 2.

| Vấn đề | Dạng `case ...:` | Dạng `case ... ->` |
| --- | --- | --- |
| Fall-through ngoài ý muốn | Có thể xảy ra nếu thiếu `break` | Không có |
| Khối cục bộ `{...}` | Nên thêm khi cần scope riêng | Rõ ràng theo từng nhánh block |
| Nhiều nhãn dùng chung | Nhiều `case` liên tiếp | `case 1, 2 ->` |
| Nhiều lệnh trong nhánh | Các statement tới `break` hoặc nhóm tiếp | Viết `{ statement1; statement2; }` |

Với case dạng dấu hai chấm, các biến khai báo trực tiếp trong cùng khối switch có thể gây xung đột tên hoặc lỗi *definite assignment* khi luồng nhảy vào nhãn khác. Đặt khối `{...}` cho từng nhóm cũng giúp tránh nhầm scope trong dạng truyền thống.

**Không trộn** `case ...:` và `case ... ->` trong cùng một `switch`.

## 7. Ví dụ Java 17+ chạy độc lập

Tạo file **ArrowSwitchScopeDemo.java**:

~~~java
public final class ArrowSwitchScopeDemo {
    enum State { NEW, RUNNING, DONE }

    private static String statement(int code) {
        StringBuilder log = new StringBuilder();
        switch (code) {
            case 0 -> log.append("ZERO");
            case 1 -> {
                int local = code + 10;
                log.append("ONE=").append(local);
            }
            case 2 -> {
                int local = code + 20; // Hợp lệ: scope riêng.
                log.append("TWO=").append(local);
            }
            default -> log.append("UNKNOWN");
        }
        return log.toString();
    }

    private static String expression(int code) {
        return switch (code) {
            case 0 -> "ZERO";
            case 1, 2 -> {
                int scaled = code * 10;
                yield "GROUP-" + scaled;
            }
            default -> "OTHER";
        };
    }

    private static String byState(State state) {
        return switch (state) {
            case NEW -> "new";
            case RUNNING -> "running";
            case DONE -> "done";
        };
    }

    private static String colonDemo(int code) {
        StringBuilder log = new StringBuilder();
        switch (code) {
            case 1:
                log.append("ONE");
            case 2:
                log.append("+TWO");
                break;
            default:
                log.append("OTHER");
        }
        return log.toString();
    }

    private static String guarded(int value) {
        return switch (value) {
            case -1 -> throw new IllegalArgumentException("negative");
            case 0 -> "ZERO";
            default -> {
                int twice = value * 2;
                yield "DOUBLE=" + twice;
            }
        };
    }

    public static void main(String[] args) {
        System.out.println("stmt0=" + statement(0));
        System.out.println("stmt1=" + statement(1));
        System.out.println("stmt2=" + statement(2));
        System.out.println("stmt9=" + statement(9));

        System.out.println("expr0=" + expression(0));
        System.out.println("expr1=" + expression(1));
        System.out.println("expr2=" + expression(2));
        System.out.println("expr9=" + expression(9));

        System.out.println("enumNew=" + byState(State.NEW));
        System.out.println("enumDone=" + byState(State.DONE));

        System.out.println("colon1=" + colonDemo(1));
        System.out.println("colon2=" + colonDemo(2));
        System.out.println("colon9=" + colonDemo(9));

        System.out.println("guard0=" + guarded(0));
        System.out.println("guard3=" + guarded(3));
        try {
            guarded(-1);
        } catch (IllegalArgumentException ex) {
            System.out.println("guardNegative=IllegalArgumentException");
        }
    }
}
~~~

Biên dịch/chạy tại thư mục chứa file (Bash, PowerShell hoặc Command Prompt):

~~~bash
javac -encoding UTF-8 ArrowSwitchScopeDemo.java
java ArrowSwitchScopeDemo
~~~

**Expected stdout chính xác:**

~~~text
stmt0=ZERO
stmt1=ONE=11
stmt2=TWO=22
stmt9=UNKNOWN
expr0=ZERO
expr1=GROUP-10
expr2=GROUP-20
expr9=OTHER
enumNew=new
enumDone=done
colon1=ONE+TWO
colon2=+TWO
colon9=OTHER
guard0=ZERO
guard3=DOUBLE=6
guardNegative=IllegalArgumentException
~~~

Hai nhánh statement của `code=1`/`code=2` đều khai báo biến `local` mà không xung đột vì có scope riêng. Các dòng `expr1`/`expr2` minh họa `yield` từ block. `colon1=ONE+TWO` đối chiếu fall-through của `:` với việc `->` chỉ thực hiện một nhánh.

## 8. Lỗi thường gặp và bài tập

| Trường hợp | Cách xử lý |
| --- | --- |
| Muốn thực hiện nhiều statement sau `->` | Đặt chúng trong `{ ... }` |
| Đọc biến cục bộ của nhánh ở bên ngoài khối | Khai báo biến dùng chung ở ngoài hoặc trả giá trị bằng switch expression |
| Khối của switch expression không trả giá trị | Viết `yield value;` trên đường đi hoàn thành bình thường |
| Cố dùng `break value;` thay `yield` | Dùng `yield value;` |
| Lo phải thêm `break` sau nhánh `->` | Không cần; arrow rule không fall-through |
| Muốn nhóm nhiều giá trị | `case 1, 2 -> ...` |
| Selector nullable trong Java17 | Kiểm tra `null` trước switch |

**Bài 1.** Viết `switch` statement dùng `->` với mã 1, 2, mặc định. Ở mỗi nhánh, thêm hai câu lệnh in; xác định có cần `break` không.

**Bài 2.** Trong hai khối `case 1 -> { int x = 1; ... }` và `case 2 -> { int x = 2; ... }`, tại sao cùng tên `x` không gây lỗi? Thử dùng `x` sau switch để xem vấn đề scope.

**Bài 3.** Chuyển `switch` statement tính nhãn thành `switch` expression. Khi một nhánh cần tạo biến rồi trả giá trị, dùng từ khóa nào?

**Bài 4.** Dự đoán kết quả của `colonDemo(1)` và giải thích vì sao switch dạng `->` không có cùng hiện tượng.

**Bài 5.** Viết switch expression trên enum chứa đủ các hằng để không cần `default`. Kiểm tra riêng trường hợp selector `null` trong Java 17.

### Ghi nhớ

**`case ... ->` không fall-through.** Một nhánh có nhiều câu lệnh cần `{...}`, cũng là nơi giới hạn phạm vi biến cục bộ. Với **switch expression**, nhánh đơn có thể trả biểu thức trực tiếp; nhánh block nhiều lệnh dùng **`yield`** để trả giá trị. `switch statement` thực hiện thao tác, còn `switch expression` tính giá trị và phải bao phủ các trường hợp hợp lệ.
