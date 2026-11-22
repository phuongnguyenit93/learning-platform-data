# Chọn `if` hoặc `switch` theo bản chất điều kiện — Java 17+

## 1. Nguyên tắc quyết định

Cả `if/else if/else` và `switch` đều điều khiển luồng thực thi, nhưng diễn đạt **hai loại bài toán** khác nhau:

- **`if`**: trả lời những câu hỏi **đúng/sai** tùy ý, chẳng hạn “điểm từ 70 trở lên”, “người dùng đủ 18 tuổi **và** đã xác minh”, hoặc “ưu tiên khẩn cấp”.
- **`switch`**: chọn xử lý theo **một giá trị rời rạc** có các trường hợp xác định, chẳng hạn mã trạng thái `1/2/3`, lệnh `"start"/"stop"` hoặc một hằng `enum`.

~~~java
int score = 85;
if (score >= 90) {
    System.out.println("A");
} else if (score >= 70) {
    System.out.println("B");
} else {
    System.out.println("C");
}

String command = "start";
switch (command) {
    case "start" -> System.out.println("START");
    case "stop" -> System.out.println("STOP");
    default -> System.out.println("UNKNOWN");
}
~~~

**Exact stdout:**

~~~text
B
START
~~~

**Đừng chọn theo cảm giác “switch trông ngắn hơn” hoặc “if chạy nhanh hơn”.** Hãy chọn theo **loại điều kiện cần biểu đạt**, quy tắc miền dữ liệu và khả năng bảo trì.

## 2. Bảng chọn nhanh

| Nhu cầu | Thường chọn | Lý do |
|---|---|---|
| Kiểm tra `age >= 18` | `if` | Điều kiện quan hệ, không phải một giá trị cố định |
| Kiểm tra `0 <= score <= 100` | `if` | Kết hợp nhiều điều kiện boolean |
| Phân loại điểm theo các khoảng 0–49, 50–69, 70–89, 90–100 | `if/else if` | Các ngưỡng và biên có ý nghĩa |
| Quy tắc `isAdmin || (verified && !blocked)` | `if` | Logic `&&`, `||`, `!` |
| Xử lý `code == 1`, `code == 2`, `code == 3` | `switch` | Các trường hợp rời rạc của cùng selector |
| Xử lý lệnh `"start"`, `"stop"` | `switch(String)` | Nhãn giá trị String dễ đọc |
| Xử lý `Status.NEW/RUNNING/DONE` | `switch(enum)` | Tập giá trị hữu hạn, đặt tên rõ |
| Một điều kiện có độ ưu tiên cao phải xét trước các điều kiện khác | `if/else if` | Thứ tự là một phần của quy tắc |
| Hai hành động phải cùng chạy nếu hai điều kiện đều true | Hai `if` độc lập | Chuỗi `else if` chỉ chọn nhánh đầu tiên |
| Phân loại `double` theo ngưỡng | `if` | `double` không là selector switch Java 17 ổn định |

Một bài toán có thể dùng **cả hai**: `if` xác thực đầu vào, sau đó `switch` xử lý mã lệnh hợp lệ.

## 3. `if` phù hợp với miền liên tục và điều kiện kết hợp

Giả sử điểm hợp lệ là `[0,100]` và quy định:

| Miền điểm | Kết quả |
|---|---|
| Ngoài `[0,100]` | INVALID |
| `[90,100]` | A |
| `[70,90)` | B |
| `[50,70)` | C |
| `[0,50)` | D |

~~~java
static String grade(int score) {
    if (score < 0 || score > 100) {
        return "INVALID";
    }
    if (score >= 90) {
        return "A";
    } else if (score >= 70) {
        return "B";
    } else if (score >= 50) {
        return "C";
    }
    return "D";
}
~~~

Cách này bộc lộ rõ **ngưỡng** và **biên bao gồm**:

- 90 thuộc A, 70 thuộc B, 50 thuộc C.
- 100 vẫn hợp lệ, 101 bị loại.
- Kiểm tra ngưỡng từ cao xuống thấp; nếu đặt `score >= 50` lên trước, các hạng A/B có thể bị nhánh rộng **che khuất**.

**Không nên thay bằng:**

~~~java
// switch (score) {
//     case 90 -> "A";
//     case 70 -> "B";
//     default -> "C";
// }
~~~

Biểu thức trên chỉ khớp **đúng các số 90 hoặc 70**, không biểu diễn “từ 90 trở lên” hay “từ 70 trở lên”. Java 17 switch thông thường **không cho nhãn `case score >= 90`**.

## 4. `if` phù hợp với điều kiện nhiều biến và độ ưu tiên

~~~java
boolean eligible = age >= 18
        && verified
        && !banned;
~~~

Ba phép kiểm tra trên sử dụng **ba dữ liệu**, với quan hệ AND và NOT. `switch` không thay thế được biểu thức logic này một cách tự nhiên.

Với nhiều quy tắc ưu tiên:

~~~java
static String priority(int risk, boolean emergency) {
    if (risk < 0 || risk > 100) {
        return "INVALID";
    }
    if (emergency) {
        return "P0";
    } else if (risk >= 80) {
        return "P1";
    } else if (risk >= 50) {
        return "P2";
    }
    return "P3";
}
~~~

- **Khẩn cấp** thắng các ngưỡng rủi ro thông thường.
- Khi không khẩn cấp, mức rủi ro cao hơn được xét trước.
- Dữ liệu sai miền bị từ chối trước khi phân loại.

**Thứ tự các nhánh có ý nghĩa nghiệp vụ.** Không tự đảo thứ tự vì nghĩ điều kiện ngắn hơn nên đặt lên trước.

Nếu cần in/đánh dấu **cả hai tính chất** cùng đúng:

~~~java
if (score >= 50) {
    System.out.println("PASS");
}
if (score >= 90) {
    System.out.println("EXCELLENT");
}
~~~

Với score 95, **cả hai** được in. Nếu dùng `else if`, chỉ một nhánh được chạy. `switch` cũng không phải thay thế trực tiếp cho yêu cầu đánh giá nhiều tính chất độc lập.

## 5. `switch` phù hợp khi chọn một trong nhiều giá trị rời rạc

~~~java
static String status(int code) {
    return switch (code) {
        case 1 -> "NEW";
        case 2 -> "RUNNING";
        case 3 -> "DONE";
        default -> "UNKNOWN";
    };
}
~~~

Đây là **switch expression**, trả một `String`. Nó tự nhiên vì:

- Chỉ xét **một selector** `code`.
- Mỗi nhãn `case` là một giá trị hằng rời rạc.
- Các nhánh `->` không fall-through.
- `default` xử lý mã không được khai báo.

Nếu chỉ muốn in log hoặc thực hiện hành động mà **không tạo giá trị**, dùng switch **statement**:

~~~java
switch (code) {
    case 1 -> System.out.println("created");
    case 2 -> System.out.println("running");
    case 3 -> System.out.println("done");
    default -> System.out.println("unknown");
}
~~~

**Phân biệt:** `case ->` không tự động biến switch thành expression; **ngữ cảnh sử dụng** mới quyết định nó là statement hay expression.

## 6. Kiểm tra kiểu selector trước khi chọn switch

Java 17 ổn định (không preview) hỗ trợ selector `byte`, `short`, `char`, `int`, bốn wrapper tương ứng, `String` hoặc enum cụ thể. `long`, `float`, `double`, `boolean`, `Object` và các wrapper còn lại không được dùng trực tiếp.

Nếu mã nghiệp vụ là `long`, đừng ép sang `int` chỉ để dùng switch vì có thể mất thông tin. Chọn `if` hoặc thiết kế lại mô hình dữ liệu nếu có lý do. Bài đầu chương trình bày bảng selector và phạm vi phiên bản đầy đủ.

## 7. Chọn `switch(String)`: mã lệnh, không phải mọi chuỗi văn bản

Một lệnh có tập giá trị nhỏ và xác định rất phù hợp với switch:

~~~java
static String command(String input) {
    if (input == null) {
        return "MISSING";
    }
    String normalized = input.strip().toLowerCase(java.util.Locale.ROOT);

    return switch (normalized) {
        case "start", "run" -> "START";
        case "stop" -> "STOP";
        default -> "UNKNOWN";
    };
}
~~~

`switch(String)` so khớp theo **nội dung**, có phân biệt chữ hoa/thường. Ví dụ chủ động chuẩn hóa đầu vào ASCII như `"RUN"` hoặc `" Start "` trước khi chọn lệnh.

**Quan trọng:**

- `null` cần được kiểm tra trước; selector String null có thể ném `NullPointerException` trong switch Java 17 ổn định, `default` **không bắt null**.
- Không coi chuẩn hóa tất cả chuỗi về chữ thường là phù hợp mọi nghiệp vụ; ID, token hoặc mật khẩu có thể phân biệt hoa/thường.
- `case` phải là hằng phù hợp; không thể dùng một biến String runtime làm case constant chỉ vì giá trị của nó hiện là `"start"`.

## 8. `switch(enum)`: các trạng thái đặt tên rõ ràng

~~~java
enum Channel { WEB, MOBILE, API }

static String channelName(Channel channel) {
    if (channel == null) {
        return "MISSING";
    }
    return switch (channel) {
        case WEB -> "BROWSER";
        case MOBILE -> "PHONE";
        case API -> "SERVICE";
    };
}
~~~

Vì đã liệt kê đủ tất cả hằng `Channel`, switch expression có thể **không cần `default`**. Đây là ưu điểm khi muốn compiler hỗ trợ phát hiện thiếu trường hợp nếu enum được mở rộng.

Ngược lại, thêm `default` là hợp lý khi thực sự có một chính sách cho giá trị chưa liệt kê; không nên thêm mặc định tùy tiện khiến một trạng thái mới bị xử lý lặng lẽ như trạng thái cũ.

Trong switch của enum ở Java 17 ổn định, nhãn viết `case WEB`, **không** viết `case Channel.WEB`.

Với enum nullable, vẫn phải guard null trước switch.

## 9. Chọn statement hay expression

Khi cần thực hiện hành động, dùng switch statement; khi cần tạo một giá trị, dùng switch expression. Trong Java 17, nhánh `->` không fall-through. Mã `case:` vẫn hợp lệ nhưng cần xem có phải dùng `break` để dừng trước nhánh kế không. Với switch expression có block nhiều lệnh, dùng `yield` để tạo kết quả. Đây là lựa chọn **sau khi** đã xác nhận bài toán phù hợp selector rời rạc.

## 10. Câu hỏi lựa chọn theo yêu cầu

Trước khi quyết định, hãy thử trả lời theo thứ tự:

~~~mermaid
flowchart TD
    A["Yêu cầu rẽ nhánh"] --> B{"Điều kiện là khoảng, so sánh, nhiều biến, ưu tiên?"}
    B -- "Có" --> C["Dùng if / else if"]
    B -- "Không" --> D{"Chọn theo một selector có kiểu switch hỗ trợ?"}
    D -- "Không" --> E["Dùng if hoặc thiết kế lại mô hình"]
    D -- "Có" --> F{"Các trường hợp rời rạc, case constant/enum?"}
    F -- "Có" --> G["Dùng switch"]
    F -- "Không" --> C
    G --> H{"Cần tạo một giá trị?"}
    H -- "Có" --> I["Switch expression, -> và yield khi cần"]
    H -- "Không" --> J["Switch statement, ưu tiên -> khi không muốn fall-through"]
~~~

Đây là **quy tắc thực hành**, không phải luật bắt buộc. Có thể viết `if (code == 1) ... else if (code == 2)` vẫn đúng; khi nhiều lựa chọn cùng một selector, switch thường dễ quét hơn.

Không quyết định chỉ vì tuyên bố hiệu năng: JVM/JIT và đặc điểm dữ liệu ảnh hưởng đến tối ưu hóa, còn **đúng ngữ nghĩa và dễ đọc** là tiêu chí đầu tiên. Nếu hiệu năng thực sự là yêu cầu, đo đạc bằng benchmark đúng phương pháp với dữ liệu đại diện.

## 11. Kết hợp `if` và `switch` khi cần

Một ứng dụng có thể vừa kiểm tra dữ liệu, vừa phân loại lệnh:

~~~java
static String execute(String command, boolean authenticated) {
    if (!authenticated) {
        return "DENIED";
    }
    if (command == null) {
        return "MISSING";
    }
    return switch (command) {
        case "start" -> "STARTED";
        case "stop" -> "STOPPED";
        default -> "UNKNOWN";
    };
}
~~~

Trong ví dụ:

1. `if` áp dụng **quy tắc xác thực** trước.
2. `if` loại selector `null`.
3. `switch` lựa chọn theo **giá trị command**.

Trật tự có thể quan trọng: nếu không xác thực, không nên tiết lộ những nhánh xử lý có sẵn cho người gọi. Đây chỉ là ví dụ về luồng điều khiển; kiểm soát quyền thực tế còn đòi xác thực và kiểm tra phía đáng tin cậy.

## 12. Chương trình Java 17 hoàn chỉnh

Tạo file đúng tên **`IfOrSwitchDecisionDemo.java`**:

~~~java
import java.util.Locale;

public final class IfOrSwitchDecisionDemo {
    private IfOrSwitchDecisionDemo() {}

    enum Channel { WEB, MOBILE, API }

    static String grade(int score) {
        if (score < 0 || score > 100) return "INVALID";
        if (score >= 90) return "A";
        if (score >= 70) return "B";
        if (score >= 50) return "C";
        return "D";
    }

    static String ageGroup(int age) {
        if (age < 0) return "INVALID";
        if (age >= 65) return "SENIOR";
        if (age >= 18) return "ADULT";
        return "MINOR";
    }

    static String wrongAgeGroup(int age) {
        if (age >= 18) return "ADULT";
        if (age >= 65) return "SENIOR";
        return "MINOR";
    }

    static boolean eligible(int age, boolean verified, boolean banned) {
        return age >= 18 && verified && !banned;
    }

    static String priority(int risk, boolean emergency) {
        if (risk < 0 || risk > 100) return "INVALID";
        if (emergency) return "P0";
        if (risk >= 80) return "P1";
        if (risk >= 50) return "P2";
        return "P3";
    }

    static String status(int code) {
        return switch (code) {
            case 1 -> "NEW";
            case 2 -> "RUNNING";
            case 3 -> "DONE";
            default -> "UNKNOWN";
        };
    }

    static String command(String input) {
        if (input == null) return "MISSING";
        String normalized = input.strip().toLowerCase(Locale.ROOT);
        return switch (normalized) {
            case "start", "run" -> "START";
            case "stop" -> "STOP";
            default -> "UNKNOWN";
        };
    }

    static String channelName(Channel channel) {
        if (channel == null) return "MISSING";
        return switch (channel) {
            case WEB -> "BROWSER";
            case MOBILE -> "PHONE";
            case API -> "SERVICE";
        };
    }

    static String traditionalStatement(int code) {
        String result;
        switch (code) {
            case 1:
                result = "ONE";
                break;
            case 2:
                result = "TWO";
                break;
            default:
                result = "OTHER";
        }
        return result;
    }

    static String execute(String command, boolean authenticated) {
        if (!authenticated) return "DENIED";
        if (command == null) return "MISSING";
        return switch (command) {
            case "start" -> "STARTED";
            case "stop" -> "STOPPED";
            default -> "UNKNOWN";
        };
    }

    public static void main(String[] args) {
        System.out.println("grade 49=" + grade(49));
        System.out.println("grade 50=" + grade(50));
        System.out.println("grade 69=" + grade(69));
        System.out.println("grade 70=" + grade(70));
        System.out.println("grade 89=" + grade(89));
        System.out.println("grade 90=" + grade(90));
        System.out.println("grade 101=" + grade(101));

        System.out.println("age 17=" + ageGroup(17));
        System.out.println("age 18=" + ageGroup(18));
        System.out.println("age 65=" + ageGroup(65));
        System.out.println("wrong age 70=" + wrongAgeGroup(70));
        System.out.println("right age 70=" + ageGroup(70));

        System.out.println("eligible yes=" + eligible(20, true, false));
        System.out.println("eligible banned=" + eligible(20, true, true));
        System.out.println("eligible minor=" + eligible(17, true, false));

        System.out.println("priority emergency=" + priority(99, true));
        System.out.println("priority high=" + priority(99, false));
        System.out.println("priority low=" + priority(49, false));
        System.out.println("priority invalid=" + priority(-1, true));

        System.out.println("status 1=" + status(1));
        System.out.println("status 2=" + status(2));
        System.out.println("status 9=" + status(9));

        System.out.println("command start=" + command(" Start "));
        System.out.println("command run=" + command("RUN"));
        System.out.println("command stop=" + command("stop"));
        System.out.println("command pause=" + command("pause"));
        System.out.println("command null=" + command(null));

        System.out.println("channel WEB=" + channelName(Channel.WEB));
        System.out.println("channel MOBILE=" + channelName(Channel.MOBILE));
        System.out.println("channel null=" + channelName(null));

        System.out.println("statement 2=" + traditionalStatement(2));
        System.out.println("statement 5=" + traditionalStatement(5));

        System.out.println("execute blocked=" + execute("start", false));
        System.out.println("execute null=" + execute(null, true));
        System.out.println("execute start=" + execute("start", true));

        int[] sample = {70, 95};
        for (int score : sample) {
            if (score >= 50) System.out.println("passed " + score);
            if (score >= 90) System.out.println("excellent " + score);
        }
    }
}
~~~

**Yêu cầu:** JDK 17 trở lên; mở terminal tại thư mục chứa file. Chỉ dùng API tiêu chuẩn JDK, không cần Maven, Gradle hoặc preview feature.

**Bash (Linux/macOS):**

~~~bash
javac --release 17 -encoding UTF-8 IfOrSwitchDecisionDemo.java
java -cp . IfOrSwitchDecisionDemo
~~~

**PowerShell (Windows):**

~~~powershell
javac --release 17 -encoding UTF-8 .\IfOrSwitchDecisionDemo.java
java -cp . IfOrSwitchDecisionDemo
~~~

### Exact expected stdout

~~~text
grade 49=D
grade 50=C
grade 69=C
grade 70=B
grade 89=B
grade 90=A
grade 101=INVALID
age 17=MINOR
age 18=ADULT
age 65=SENIOR
wrong age 70=ADULT
right age 70=SENIOR
eligible yes=true
eligible banned=false
eligible minor=false
priority emergency=P0
priority high=P1
priority low=P3
priority invalid=INVALID
status 1=NEW
status 2=RUNNING
status 9=UNKNOWN
command start=START
command run=START
command stop=STOP
command pause=UNKNOWN
command null=MISSING
channel WEB=BROWSER
channel MOBILE=PHONE
channel null=MISSING
statement 2=TWO
statement 5=OTHER
execute blocked=DENIED
execute null=MISSING
execute start=STARTED
passed 70
passed 95
excellent 95
~~~

**Cách đọc output:**

1. Các mốc 49/50/69/70/89/90 cho thấy `if` phù hợp với **ngưỡng**, và 101 bị từ chối trước khi xếp loại.
2. `wrong age 70=ADULT` là lỗi **nhánh rộng che nhánh hẹp**; sửa bằng xét `age >= 65` trước.
3. `eligible` dùng nhiều biến boolean và điều kiện kết hợp; `priority` có ưu tiên khẩn cấp.
4. `status` xử lý các mã rời rạc; `command` xử lý String đã chuẩn hóa; `channelName` xử lý enum.
5. `traditionalStatement` dùng `break` để ngăn fall-through; `execute` dùng `if` để bảo vệ trước `switch`.
6. Hai câu `if` độc lập cho phép `95` in **cả** `passed` và `excellent`.

## 13. Sai lầm thường gặp

| Sai lầm | Hậu quả | Cách phù hợp |
|---|---|---|
| Dùng switch để kiểm tra `score >= 90` | `case 90` chỉ khớp số 90 | Dùng `if` cho ngưỡng |
| Chọn switch cho `double` hoặc `long` trên Java 17 ổn định | Lỗi compile | Dùng `if` hoặc thiết kế kiểu khác |
| Đặt `age >= 18` trước `age >= 65` | Nhánh senior bị che khuất | Xét ngưỡng cụ thể/ưu tiên trước |
| Dùng `else if` cho hai tính chất phải cùng báo | Chỉ nhánh đầu true chạy | Hai `if` độc lập |
| Không validate điểm ngoài `[0,100]` | Điểm 101 có thể thành A | Guard miền trước |
| Dùng `switch(String)` với null | NullPointerException | Kiểm tra null trước |
| Nghĩ switch trên String so tham chiếu `==` | Sai ý nghĩa so khớp | Switch so nội dung, case-sensitive |
| Quên `break` trong dạng `case:` | Fall-through ngoài ý muốn | Dùng `break` hoặc `case ->` |
| Nghĩ `case ->` chỉ có ở switch expression | Switch statement cũng hỗ trợ | Nhìn ngữ cảnh |
| Không có `default` trong switch expression trên int | Không bao phủ giá trị | Thêm default |
| Thêm `default` vào enum để che mọi thay đổi | Có thể bỏ sót trạng thái mới cần xử lý | Cân nhắc exhaustiveness của enum |
| Chọn chỉ vì “switch nhanh hơn” | Không bảo đảm hiệu năng ở mọi tình huống | Chọn theo đúng ngữ nghĩa, đo nếu cần |
| Chuẩn hóa String vô điều kiện | Có thể đổi ý nghĩa token phân biệt hoa/thường | Chỉ chuẩn hóa khi yêu cầu cho phép |

## 14. Bài tập có đáp án

### Bài A — phân loại khoảng

Yêu cầu: nhiệt độ dưới 0 → COLD, từ 0 đến dưới 30 → NORMAL, từ 30 trở lên → HOT.

**Nên chọn:** `if/else if`, vì so sánh **miền**:

~~~java
String label;
if (temperature < 0) {
    label = "COLD";
} else if (temperature < 30) {
    label = "NORMAL";
} else {
    label = "HOT";
}
~~~

### Bài B — chọn mã thao tác

Mã `1` → CREATE, `2` → UPDATE, `3` → DELETE, còn lại → UNKNOWN.

**Nên chọn:** `switch` vì đây là các giá trị rời rạc:

~~~java
String action = switch (code) {
    case 1 -> "CREATE";
    case 2 -> "UPDATE";
    case 3 -> "DELETE";
    default -> "UNKNOWN";
};
~~~

### Bài C — nhiều điều kiện

Yêu cầu chỉ chấp nhận khi tuổi từ 18 trở lên, đã xác minh và chưa bị khóa.

**Nên chọn:** biểu thức boolean/ `if`:

~~~java
boolean accepted = age >= 18 && verified && !blocked;
~~~

Không dùng `switch` cho ba điều kiện độc lập này.

### Bài D — hai hành động có thể cùng đúng

Với điểm 95, cần ghi đồng thời PASS và EXCELLENT.

**Đáp án:** hai `if` độc lập, không dùng `else if`:

~~~java
if (score >= 50) System.out.println("PASS");
if (score >= 90) System.out.println("EXCELLENT");
~~~

**Exact stdout:**

~~~text
PASS
EXCELLENT
~~~

### Bài E — switch và null

~~~java
String command = null;
// switch (command) {
//     case "start" -> System.out.println("start");
//     default -> System.out.println("unknown");
// }
~~~

**Đáp án:** không dùng `default` để thay null guard; selector String null gây NPE trong Java 17 ổn định. Kiểm tra `if (command == null)` trước khi switch.

## 15. Checklist và kết luận

- [ ] Chọn `if` khi cần so sánh quan hệ, khoảng giá trị, điều kiện kết hợp hay ưu tiên.
- [ ] Chọn `switch` khi xét nhiều **giá trị rời rạc của cùng một selector** hợp lệ.
- [ ] Phân biệt chuỗi `else if` với nhiều `if` độc lập.
- [ ] Kiểm tra biên dưới, biên trên và các mốc phân loại.
- [ ] Không đặt điều kiện rộng lên trước để che mất nhánh cụ thể.
- [ ] Biết các kiểu selector được hỗ trợ trong Java 17 không bật preview.
- [ ] Biết switch String so nội dung và phân biệt hoa/thường.
- [ ] Kiểm tra null trước switch với String, enum và wrapper.
- [ ] Biết switch statement `case:` có thể fall-through; `case ->` không.
- [ ] Biết switch expression tạo kết quả và dùng `yield` khi nhánh là block.
- [ ] Không lạm dụng `default` để che trường hợp enum mới quan trọng.
- [ ] Đừng quyết định theo tốc độ mà không có đo đạc phù hợp.
- [ ] Chạy `IfOrSwitchDecisionDemo.java` bằng Java 17+ và đối chiếu exact stdout.

**Kết luận:** Hãy chọn `if` để **diễn đạt một điều kiện boolean** (ngưỡng, miền, tổ hợp, ưu tiên), và chọn `switch` để **phân phối xử lý theo một tập giá trị rời rạc đã biết**. Hai cấu trúc có thể kết hợp: dùng `if` để bảo vệ/validate, dùng `switch` để chọn hành động. Điều quan trọng nhất là **đúng bản chất điều kiện, rõ biên và dễ bảo trì**.