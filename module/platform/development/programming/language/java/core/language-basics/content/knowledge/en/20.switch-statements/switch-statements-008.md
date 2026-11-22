# Yêu cầu bao phủ các trường hợp và chọn kiểu kết quả của `switch` trong Java

> **Java core — language-basics / Switch**  
> **Phiên bản:** Java 17+ (không bật preview); chương trình độc lập, chỉ dùng JDK.  
> **Mục tiêu:** Hiểu vì sao `switch expression` phải **bao phủ toàn bộ trường hợp**, khi nào cần `default`, cách `yield`/`throw` ảnh hưởng đến đường đi, và vì sao **kiểu kết quả** phải phù hợp với nơi dùng biểu thức.

## 1. Phân biệt `switch statement` với `switch expression`

`switch statement` điều khiển các thao tác; nó **không bắt buộc** có `default`:

~~~java
int code = 9;
switch (code) {
    case 1 -> System.out.println("ONE");
    case 2 -> System.out.println("TWO");
}
// Không in gì khi code = 9: statement không có nhánh phù hợp.
~~~

`switch expression` **tính một giá trị** để trả về hoặc gán:

~~~java
int code = 9;
String text = switch (code) {
    case 1 -> "ONE";
    case 2 -> "TWO";
    default -> "OTHER";
};
System.out.println(text); // OTHER
~~~

Nếu không có `default` cho hai nhãn 1 và 2 ở `switch expression` trên `int`, trình biên dịch không thể đảm bảo có giá trị khi code bằng 9. Vì thế nó báo lỗi **switch expression does not cover all possible input values** (câu chữ tùy JDK).

**Tính bao phủ (exhaustiveness)** là yêu cầu được kiểm tra khi **biên dịch** cho switch expression; nó không có nghĩa mọi nhánh đều chạy hoặc mọi giá trị đều phải có một nhãn riêng.

## 2. `default` và bao phủ các giá trị số hoặc `String`

Đối với selector kiểu `int` hoặc `String` trong Java 17, cách thông dụng để bao phủ toàn bộ miền là thêm **một `default`**:

~~~java
static String classify(int value) {
    return switch (value) {
        case 0 -> "ZERO";
        case 1, 2 -> "SMALL";
        default -> "OTHER";
    };
}
~~~

`case 1, 2` gộp **hai giá trị khác nhau** vào một nhánh. `default` xử lý mọi giá trị `int` khác 0, 1, 2. Thứ tự nhãn trong dạng mũi tên không tạo fall-through.

Ví dụ lỗi (để trong comment, không đưa vào code chạy):

~~~java
// KHÔNG BIÊN DỊCH: còn vô số giá trị int không được xử lý.
// String label = switch (code) {
//     case 0 -> "ZERO";
//     case 1 -> "ONE";
// };
~~~

Với `String` cũng cần nhánh cho các nội dung không liệt kê:

~~~java
static String command(String input) {
    return switch (input) {
        case "go" -> "MOVE";
        case "stop" -> "HALT";
        default -> "UNKNOWN";
    };
}
~~~

**`default` không phải nhánh `null`**: Java 17 không bật preview sẽ ném `NullPointerException` nếu selector `String`/`enum`/wrapper là null. Nếu null là đầu vào hợp lệ của ứng dụng, cần kiểm tra nó **trước `switch`**.

## 3. `enum` có thể exhaustive mà không cần `default`

Với một `enum` đã biết đủ các hằng, mọi trường hợp có thể được liệt kê:

~~~java
enum State { NEW, RUNNING, DONE }

static String status(State state) {
    return switch (state) {
        case NEW -> "NEW";
        case RUNNING -> "IN_PROGRESS";
        case DONE -> "COMPLETE";
    };
}
~~~

`switch expression` trên `State` ở trên **đã bao phủ đủ** các hằng enum và không cần `default`.

Lợi ích khi **không** viết `default` cho enum đã liệt kê đầy đủ: nếu thêm một hằng mới rồi biên dịch lại mã nguồn, trình biên dịch có thể chỉ ra các switch expression cần cập nhật thay vì âm thầm chuyển trạng thái mới vào một nhánh mặc định chung.

Nếu bỏ sót `DONE` mà không có `default`, switch expression **không exhaustive** và không biên dịch. Ngược lại, `switch statement` có thể chỉ xử lý một số trạng thái mà không bắt buộc phải bao phủ tất cả.

Bao phủ đủ các hằng enum **không đồng nghĩa bao phủ null**. Cần guard null riêng khi dữ liệu có thể thiếu.

## 4. Mỗi đường đi bình thường phải tạo được giá trị

Với `switch expression`, một nhánh mũi tên ngắn có thể cung cấp kết quả trực tiếp:

~~~java
int score = 1;
int points = switch (score) {
    case 0 -> 0;
    case 1 -> 10;
    default -> 100;
};
~~~

Nếu một nhánh cần nhiều câu lệnh, đặt trong khối và dùng `yield value;`:

~~~java
int result = switch (score) {
    case 0 -> 0;
    default -> {
        int computed = score * 10;
        yield computed;
    }
};
~~~

Đường đi **kết thúc bình thường** của khối trong một switch expression phải cung cấp giá trị qua `yield`; không thể đi tới cuối khối mà thiếu kết quả.

Một nhánh được phép **ném ngoại lệ** thay vì trả giá trị:

~~~java
static int priority(int value) {
    return switch (value) {
        case 0 -> 0;
        default -> {
            if (value < 0) {
                throw new IllegalArgumentException("negative");
            }
            yield value * 10;
        }
    };
}
~~~

Cách này vẫn exhaustive: `default` xử lý tất cả giá trị khác 0, nhưng trường hợp âm kết thúc bằng exception chứ không hoàn thành bình thường.

Đừng nhầm `yield` với `break`: `break;` thoát switch statement dạng truyền thống; `yield expression;` tạo kết quả cho switch expression. `break value;` không phải cú pháp Java 17 hợp lệ.

## 5. Kiểu kết quả phải phù hợp với nơi dùng biểu thức

Java không chỉ xét nhánh nào chạy mà còn kiểm tra **kiểu của các biểu thức nhánh khi biên dịch**.

~~~java
int code = 1;
String label = switch (code) {
    case 1 -> "ONE";
    default -> "OTHER";
};
~~~

Ở đây mọi kết quả đều chuyển được sang `String`. Nhưng đoạn sau **không biên dịch**:

~~~java
// KHÔNG BIÊN DỊCH: nhánh int không dùng làm String.
// String wrong = switch (code) {
//     case 1 -> "ONE";
//     default -> 2;
// };
~~~

Quy tắc hữu ích:

- Nếu switch expression xuất hiện trong **ngữ cảnh gán hoặc truyền đối số**, nó có thể được **target-typed** (biểu thức *poly*): từng nhánh phải tương thích với kiểu đích.
- Ở ngữ cảnh không có kiểu đích thích hợp (*standalone expression*), Java xác định kiểu theo quy tắc riêng từ các nhánh, gồm nâng kiểu số hoặc kiểu tham chiếu chung khi phù hợp.
- `yield` bên trong khối cũng phải tạo một giá trị tương thích với kiểu kết quả yêu cầu.
- Không suy đoán kiểu từ **nhánh thực sự được chọn lúc chạy**; trình biên dịch kiểm tra các nhánh có thể cho kết quả.

Ví dụ đích là `double`, nhánh có literal `int` vẫn chuyển được:

~~~java
double number = switch (code) {
    case 1 -> 1;
    default -> 2.5;
};
// code=1: number=1.0.
~~~

Nếu đích là `Number`, có thể chọn các đối tượng số khác lớp:

~~~java
Number boxed = switch (code) {
    case 1 -> Integer.valueOf(10);
    default -> Double.valueOf(2.5);
};
// code=1: boxed thuộc lớp Integer.
~~~

`Number` là lớp cha chung; kết quả thực tế vẫn có thể là `Integer` hoặc `Double` tùy nhánh. Đây **không** phải lời khuyên trộn kiểu tùy tiện: trong code nghiệp vụ, chọn kiểu đích thống nhất và rõ nghĩa sẽ giảm bất ngờ khi chuyển đổi/boxing.

## 6. Bảng chọn cách bao phủ và kiểu kết quả

| Tình huống | Bao phủ hợp lệ trong Java 17 | Kiểu kết quả |
| --- | --- | --- |
| Switch expression trên `int` | Có `default` cho các giá trị ngoài `case` | Mọi nhánh trả kiểu phù hợp |
| Switch expression trên `String` | Có `default` cho nội dung chưa liệt kê; xử lý `null` riêng | Ví dụ `String` |
| Switch expression trên `enum` | Liệt kê đủ hằng, hoặc có nhánh mặc định phù hợp | Ví dụ `String` |
| Nhánh arrow chứa nhiều lệnh | `{ ... yield value; }` hoặc ném ngoại lệ | `yield` tương thích kiểu đích |
| Nhánh chỉ có `throw` | Kết thúc bất thường, không cần giá trị trên đường đó | Các nhánh trả kết quả còn lại vẫn phải tương thích |
| Switch statement dùng để in log | Có thể không cần `default` | Không có kiểu giá trị của cả switch |

Hai kiểm tra **độc lập**: (1) cấu trúc bao phủ mọi selector cần thiết; (2) các nhánh trả kết quả tương thích với kiểu đích. Có `default` vẫn có thể lỗi vì nhánh trả sai kiểu; mọi nhánh cùng trả `String` vẫn có thể lỗi vì thiếu `default`.

Đừng nhầm exhaustive với “không bao giờ lỗi”: một nhánh có thể ném exception, selector null có thể gây NPE, và dữ liệu đầu vào vẫn cần được kiểm tra theo nghiệp vụ.

## 7. Ví dụ Java 17+ chạy độc lập

Tạo file **ExhaustiveSwitchTypeDemo.java**:

~~~java
public final class ExhaustiveSwitchTypeDemo {
    enum State { NEW, RUNNING, DONE }

    private static String action(int code) {
        return switch (code) {
            case 0 -> "ZERO";
            case 1, 2 -> "SMALL";
            default -> {
                String label = "OTHER:" + code;
                yield label;
            }
        };
    }

    private static String stateName(State state) {
        return switch (state) {
            case NEW -> "NEW";
            case RUNNING -> "IN_PROGRESS";
            case DONE -> "COMPLETE";
        };
    }

    private static String command(String text) {
        return switch (text) {
            case "go" -> "MOVE";
            case "stop" -> "HALT";
            default -> "UNKNOWN";
        };
    }

    private static double numeric(int code) {
        return switch (code) {
            case 1 -> 1;
            default -> 2.5;
        };
    }

    private static Number boxed(int code) {
        return switch (code) {
            case 1 -> Integer.valueOf(10);
            default -> Double.valueOf(2.5);
        };
    }

    private static int priority(int value) {
        return switch (value) {
            case 0 -> 0;
            default -> {
                if (value < 0) {
                    throw new IllegalArgumentException("negative");
                }
                yield value * 10;
            }
        };
    }

    public static void main(String[] args) {
        System.out.println("action0=" + action(0));
        System.out.println("action1=" + action(1));
        System.out.println("action2=" + action(2));
        System.out.println("action3=" + action(3));
        System.out.println("actionMinus1=" + action(-1));

        System.out.println("enumNew=" + stateName(State.NEW));
        System.out.println("enumRunning=" + stateName(State.RUNNING));
        System.out.println("enumDone=" + stateName(State.DONE));

        System.out.println("commandGo=" + command(new String("go")));
        System.out.println("commandOther=" + command("GO"));

        System.out.println("numeric1=" + numeric(1));
        System.out.println("numeric2=" + numeric(2));

        Number a = boxed(1);
        Number b = boxed(2);
        System.out.println("boxed1=" + a.getClass().getSimpleName() + ":" + a);
        System.out.println("boxed2=" + b.getClass().getSimpleName() + ":" + b);

        System.out.println("priority0=" + priority(0));
        System.out.println("priority3=" + priority(3));
        try {
            priority(-1);
        } catch (IllegalArgumentException ex) {
            System.out.println("priorityNegative=IllegalArgumentException");
        }

        try {
            command(null);
        } catch (NullPointerException ex) {
            System.out.println("nullSelector=NullPointerException");
        }
    }
}
~~~

Biên dịch và chạy tại thư mục chứa file (Bash, PowerShell hoặc Command Prompt):

~~~bash
javac -encoding UTF-8 ExhaustiveSwitchTypeDemo.java
java ExhaustiveSwitchTypeDemo
~~~

**Expected stdout chính xác:**

~~~text
action0=ZERO
action1=SMALL
action2=SMALL
action3=OTHER:3
actionMinus1=OTHER:-1
enumNew=NEW
enumRunning=IN_PROGRESS
enumDone=COMPLETE
commandGo=MOVE
commandOther=UNKNOWN
numeric1=1.0
numeric2=2.5
boxed1=Integer:10
boxed2=Double:2.5
priority0=0
priority3=30
priorityNegative=IllegalArgumentException
nullSelector=NullPointerException
~~~

`action3`/`actionMinus1` đi qua `default` và `yield`; enum không cần `default` do đã đủ hằng. `numeric1=1.0` là chuyển `int` sang `double`; `boxed1`/`boxed2` cho thấy kiểu đích `Number` có thể nhận các lớp con khác nhau. Nhánh `priority(-1)` ném ngoại lệ nhưng toàn bộ biểu thức vẫn exhaustive.

## 8. Lỗi thường gặp và bài tập

| Lỗi | Cách sửa |
| --- | --- |
| Switch expression trên `int` chỉ có `case 1` | Thêm `default` để bao phủ đầu vào khác |
| Switch expression trên enum thiếu một hằng | Thêm `case` còn thiếu hoặc nhánh mặc định phù hợp |
| Nhánh block không `yield` trên đường hoàn thành bình thường | Viết `yield value;` hoặc dùng nhánh biểu thức trực tiếp |
| Dùng `break value;` để tạo kết quả | Thay bằng `yield value;` |
| Kết quả `String` và `int` trong đích `String` | Đổi nhánh sang kiểu tương thích |
| Cho rằng `default` xử lý `null` | Kiểm tra null trước switch Java 17 tiêu chuẩn |
| Dùng switch statement mong nhận giá trị | Chuyển sang switch expression |

**Bài 1.** Viết switch expression phân loại `int level`: 0 → `"LOW"`, 1 → `"MEDIUM"`, còn lại → `"OTHER"`. Thử bỏ `default` và giải thích lỗi.

**Bài 2.** Tạo enum có ba hằng và viết switch expression liệt kê đủ ba nhánh không có `default`. Thêm hằng thứ tư rồi thử biên dịch lại.

**Bài 3.** Viết một nhánh `case 2 -> { int x = 20; yield "Value=" + x; }`. Vì sao không thể chỉ viết `x;` ở cuối khối?

**Bài 4.** So sánh kiểu của kết quả `double x = switch (...) { case 1 -> 1; default -> 2.5; };` với `Number x = switch (...) { case 1 -> Integer.valueOf(1); default -> Double.valueOf(2.5); };`.

**Bài 5.** Viết nhánh `default` ném `IllegalArgumentException` nếu đầu vào âm, trả giá trị nếu dương. Hệ thống có cần giá trị từ nhánh ném exception không? Vì sao?

### Ghi nhớ

**Switch expression phải exhaustive và có kiểu kết quả hợp lệ.** Với `int`/`String` thường cần `default`; với `enum` có thể bao phủ đủ hằng. Nhánh một biểu thức trả giá trị trực tiếp, khối nhiều lệnh dùng **`yield`**, nhánh lỗi có thể `throw`. Java kiểm tra sự tương thích kiểu của **các nhánh khi biên dịch**, không đợi đến khi một nhánh được chọn.
