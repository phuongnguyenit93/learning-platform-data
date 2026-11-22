# Phân biệt nhiều `if` độc lập với một chuỗi loại trừ trong Java

> **Java core — language-basics / Rẽ nhánh if**  
> **Yêu cầu:** Java 17+, một file Java độc lập, chỉ dùng thư viện chuẩn.  
> **Mục tiêu:** Phân biệt **nhiều câu lệnh `if` độc lập** với **một chuỗi `if / else if / else`**; dự đoán số nhánh được thực hiện, thứ tự kiểm tra điều kiện và lựa chọn cú pháp đúng theo nghiệp vụ.

## 1. Hai cấu trúc nhìn giống nhưng khác hành vi

**Nhiều `if` độc lập** là các câu lệnh riêng biệt:

~~~java
int score = 95;

if (score >= 60) {
    System.out.println("PASS");
}
if (score >= 80) {
    System.out.println("MERIT");
}
if (score >= 90) {
    System.out.println("HONOR");
}
// In cả ba dòng: PASS, MERIT, HONOR.
~~~

Vì cả ba điều kiện đều đúng, **cả ba khối được chạy**. Trong luồng thực thi bình thường, Java vẫn kiểm tra câu `if` tiếp theo sau khi xử lý xong câu trước.

**Một chuỗi loại trừ** dùng `if / else if / else`:

~~~java
int score = 95;

if (score >= 90) {
    System.out.println("A");
} else if (score >= 80) {
    System.out.println("B");
} else if (score >= 60) {
    System.out.println("C");
} else {
    System.out.println("F");
}
// Chỉ in: A.
~~~

Ngay khi `score >= 90` đúng, Java chọn nhánh `"A"` và **bỏ qua toàn bộ các điều kiện/nhánh `else if` phía sau** trong cùng chuỗi. Không phải ba phép kiểm tra đều chạy rồi Java mới chọn kết quả.

## 2. Bảng so sánh hành vi

| Khía cạnh | Nhiều `if` độc lập | `if / else if / else` |
| --- | --- | --- |
| Số nhánh có thể chạy | **0, 1 hoặc nhiều** | **Tối đa 1** |
| Khi điều kiện đầu đúng | Vẫn tới những `if` tiếp theo nếu luồng không bị ngắt | Không đánh giá những `else if` sau |
| Điều kiện chồng lấp | Có thể kích hoạt nhiều hành động | Chọn điều kiện đúng **đầu tiên** |
| Khi không điều kiện nào đúng | Không chạy nhánh nào (trừ khi có mã khác) | Chạy `else` nếu có |
| Mục đích điển hình | Các quy tắc/hành động **không loại trừ nhau** | Các kết quả/nhóm **chỉ chọn một** |

**Điểm tinh tế:** Không nên nói mọi `if` độc lập *chắc chắn* đều được đánh giá: nhánh trước có thể `return`, ném ngoại lệ, `break` hoặc `continue` khiến luồng không tới nhánh tiếp theo. Bảng mô tả trường hợp luồng tiếp tục bình thường.

Một chuỗi `else if` có thể **không có `else`**; khi mọi điều kiện sai, chuỗi không chạy nhánh nào.

## 3. Khi nào dùng `if` độc lập?

Dùng các `if` độc lập khi nhiều quy tắc **có thể đồng thời đúng** và mỗi quy tắc cần hành động riêng.

~~~java
boolean sendEmail = true;
boolean saveLog = true;

if (sendEmail) {
    System.out.println("SEND_EMAIL");
}
if (saveLog) {
    System.out.println("SAVE_LOG");
}
// In cả SEND_EMAIL và SAVE_LOG.
~~~

Nếu đổi thành `if (sendEmail) ... else if (saveLog) ...`, việc lưu log sẽ bị **bỏ qua** khi gửi email được chọn, dù `saveLog` cũng true. Đó là thay đổi logic, không chỉ thay đổi cách viết.

Ví dụ thực tế: áp dụng nhiều cảnh báo độc lập, bật nhiều tính năng, thực hiện nhiều phép kiểm tra chất lượng, hoặc thu thập nhiều lỗi validation thay vì dừng ở lỗi đầu tiên.

Ngược lại, nếu chỉ chọn **một nhãn mức độ** hoặc **một tuyến xử lý ưu tiên**, chuỗi loại trừ phù hợp hơn.

## 4. Khi nào dùng chuỗi `if / else if / else`?

Khi các nhánh cùng quyết định **một kết quả**, chuỗi loại trừ bảo đảm chỉ một nhánh được chọn.

Ví dụ phân loại điểm từ cao xuống thấp:

~~~java
static String grade(int score) {
    if (score >= 90) {
        return "A";
    } else if (score >= 80) {
        return "B";
    } else if (score >= 60) {
        return "C";
    } else {
        return "F";
    }
}
~~~

**Thứ tự điều kiện quan trọng.** Cách viết sai thứ tự dưới đây vẫn biên dịch:

~~~java
static String wrongGrade(int score) {
    if (score >= 60) {
        return "C";
    } else if (score >= 80) {
        return "B"; // Không thể tới với điểm >= 80.
    } else if (score >= 90) {
        return "A"; // Không thể tới với điểm >= 90.
    }
    return "F";
}
~~~

Vì điểm `95` thỏa `score >= 60` ngay nhánh đầu nên kết quả là `"C"`, không phải `"A"`. Để xử lý mức ưu tiên, kiểm tra ngưỡng **cao trước thấp** hoặc thiết kế những điều kiện thực sự tách biệt.

## 5. Điều kiện chồng lấp và nhánh mặc định

Xét `int score = 85` với ba điều kiện `score >= 60`, `score >= 80`, `score >= 90`:

| Điều kiện | Với `score = 85` | `if` độc lập | Chuỗi loại trừ theo thứ tự 90 → 80 → 60 |
| --- | --- | --- | --- |
| `score >= 90` | false | Không chạy | Xét rồi bỏ qua |
| `score >= 80` | true | Chạy | **Chọn và dừng xét nhánh sau** |
| `score >= 60` | true | Chạy | **Không xét** |

Dùng nhiều `if` để **gắn nhiều thuộc tính tích lũy** (PASS, MERIT). Dùng `else if` để **chọn đúng một loại** (A, B, C, F).

Ngay cả khi các điều kiện không chồng lấp, như `x < 0` và `x > 0`, các `if` độc lập *có thể* chỉ chạy tối đa một nhánh do chính các điều kiện loại trừ nhau; **cú pháp `if` độc lập không tự bảo đảm điều đó**.

Với các điều kiện không bao phủ mọi khả năng (ví dụ `x < 0` và `x > 0` bỏ sót số 0), dùng `else` khi muốn có kết quả mặc định rõ ràng.

## 6. Điều kiện sau có được đánh giá không?

Khác biệt không chỉ là **khối lệnh nào chạy** mà còn là **biểu thức điều kiện nào thực sự được đánh giá**.

~~~java
StringBuilder independentTrace = new StringBuilder();

if (check(independentTrace, "A", true)) {
    independentTrace.append("1");
}
if (check(independentTrace, "B", true)) {
    independentTrace.append("2");
}
// Dấu vết: A1B2 — cả A và B được kiểm tra và chạy.
~~~

Còn trong chuỗi loại trừ:

~~~java
StringBuilder exclusiveTrace = new StringBuilder();

if (check(exclusiveTrace, "A", true)) {
    exclusiveTrace.append("1");
} else if (check(exclusiveTrace, "B", true)) {
    exclusiveTrace.append("2");
}
// Dấu vết: A1 — B không được gọi, không có tác dụng phụ B.
~~~

Trong hai đoạn trên, `check(log, label, value)` là hàm minh họa có trong chương trình runnable phía dưới.

Điều này quan trọng nếu điều kiện chứa lời gọi hàm, truy cập dữ liệu, tăng biến hoặc có thể ném ngoại lệ. **Không chuyển các `if` độc lập thành `else if` chỉ để “tối ưu” số lần kiểm tra** nếu nghiệp vụ thực sự cần đánh giá từng quy tắc.

## 7. Lưu ý về `else` và các điều kiện phụ thuộc

`else` luôn gắn với **`if` gần nhất chưa có `else`** khi không có ngoặc nhọn để đổi cấu trúc.

~~~java
if (isMember) {
    System.out.println("Member");
}
if (isActive) {
    System.out.println("Active");
} else {
    System.out.println("Inactive");
}
~~~

Ở đây `else` thuộc **`if (isActive)`**, không thuộc `if (isMember)` hoặc “cả hai `if`”. Hai `if` vẫn độc lập.

Trường hợp có điều kiện phụ thuộc:

~~~java
String name = null;

// SAI nếu nghĩ if thứ nhất ngăn if thứ hai:
// if (name == null) System.out.println("Missing");
// if (name.isBlank()) System.out.println("Blank"); // Có thể NPE.

// ĐÚNG: các trường hợp loại trừ nhau và có guard.
if (name == null) {
    System.out.println("Missing");
} else if (name.isBlank()) {
    System.out.println("Blank");
} else {
    System.out.println("Present");
}
~~~

Với chuỗi này, khi `name == null`, Java không đánh giá `name.isBlank()`. Khi dùng các `if` độc lập, bạn có thể thay bằng `name != null && name.isBlank()` để bảo vệ vế phụ thuộc, nếu vẫn cần thực hiện từng kiểm tra độc lập.

**Luôn dùng ngoặc nhọn `{}`** để làm rõ nhánh, đặc biệt khi sửa điều kiện hoặc bổ sung hành động.

## 8. Chương trình Java 17+ chạy độc lập

Tạo file **IndependentIfVsElseIfDemo.java**:

~~~java
public final class IndependentIfVsElseIfDemo {
    private static String tags(int score) {
        StringBuilder result = new StringBuilder();
        if (score >= 60) {
            result.append("PASS");
        }
        if (score >= 80) {
            result.append("+MERIT");
        }
        if (score >= 90) {
            result.append("+HONOR");
        }
        return result.length() == 0 ? "NONE" : result.toString();
    }

    private static String grade(int score) {
        if (score >= 90) {
            return "A";
        } else if (score >= 80) {
            return "B";
        } else if (score >= 60) {
            return "C";
        } else {
            return "F";
        }
    }

    private static String wrongGrade(int score) {
        if (score >= 60) {
            return "C";
        } else if (score >= 80) {
            return "B";
        } else if (score >= 90) {
            return "A";
        }
        return "F";
    }

    private static boolean check(
            StringBuilder log, String label, boolean value) {
        log.append(label);
        return value;
    }

    private static String nameStatus(String name) {
        if (name == null) {
            return "MISSING";
        } else if (name.isBlank()) {
            return "BLANK";
        }
        return "PRESENT";
    }

    public static void main(String[] args) {
        for (int score : new int[] {55, 60, 79, 80, 89, 90, 95}) {
            System.out.println("score=" + score
                    + ",tags=" + tags(score)
                    + ",grade=" + grade(score));
        }

        System.out.println("wrongOrdered95=" + wrongGrade(95));

        boolean sendEmail = true;
        boolean saveLog = true;
        StringBuilder independentActions = new StringBuilder();
        if (sendEmail) {
            independentActions.append("SEND_EMAIL");
        }
        if (saveLog) {
            if (independentActions.length() > 0) {
                independentActions.append("+");
            }
            independentActions.append("SAVE_LOG");
        }
        System.out.println("independentActions=" + independentActions);

        String exclusiveAction;
        if (sendEmail) {
            exclusiveAction = "SEND_EMAIL";
        } else if (saveLog) {
            exclusiveAction = "SAVE_LOG";
        } else {
            exclusiveAction = "NONE";
        }
        System.out.println("exclusiveAction=" + exclusiveAction);

        StringBuilder independentTrace = new StringBuilder();
        if (check(independentTrace, "A", true)) {
            independentTrace.append("1");
        }
        if (check(independentTrace, "B", true)) {
            independentTrace.append("2");
        }
        System.out.println("independentTrace=" + independentTrace);

        StringBuilder exclusiveTrace = new StringBuilder();
        if (check(exclusiveTrace, "A", true)) {
            exclusiveTrace.append("1");
        } else if (check(exclusiveTrace, "B", true)) {
            exclusiveTrace.append("2");
        }
        System.out.println("exclusiveTrace=" + exclusiveTrace);

        System.out.println("guardNull=" + nameStatus(null));
        System.out.println("guardBlank=" + nameStatus("  "));
        System.out.println("guardText=" + nameStatus("Java"));

        int value = 0;
        String independentNoMatch = "NONE";
        if (value < 0) {
            independentNoMatch = "NEGATIVE";
        }
        if (value > 0) {
            independentNoMatch = "POSITIVE";
        }
        System.out.println("independentNoMatch=" + independentNoMatch);

        String exclusiveFallback;
        if (value < 0) {
            exclusiveFallback = "NEGATIVE";
        } else if (value > 0) {
            exclusiveFallback = "POSITIVE";
        } else {
            exclusiveFallback = "ZERO";
        }
        System.out.println("exclusiveFallback=" + exclusiveFallback);
    }
}
~~~

Mở terminal tại thư mục chứa file (Bash, PowerShell hoặc Command Prompt):

~~~bash
javac -encoding UTF-8 IndependentIfVsElseIfDemo.java
java IndependentIfVsElseIfDemo
~~~

**Expected stdout chính xác:**

~~~text
score=55,tags=NONE,grade=F
score=60,tags=PASS,grade=C
score=79,tags=PASS,grade=C
score=80,tags=PASS+MERIT,grade=B
score=89,tags=PASS+MERIT,grade=B
score=90,tags=PASS+MERIT+HONOR,grade=A
score=95,tags=PASS+MERIT+HONOR,grade=A
wrongOrdered95=C
independentActions=SEND_EMAIL+SAVE_LOG
exclusiveAction=SEND_EMAIL
independentTrace=A1B2
exclusiveTrace=A1
guardNull=MISSING
guardBlank=BLANK
guardText=PRESENT
independentNoMatch=NONE
exclusiveFallback=ZERO
~~~

Bảy dòng điểm chứng minh `if` độc lập tích lũy nhiều tag trong khi chuỗi loại trừ chọn một grade. `wrongOrdered95=C` phơi bày sai thứ tự ưu tiên. Hai dòng `Trace` cho thấy `else if` không đánh giá B sau khi A đúng. `exclusiveFallback=ZERO` chứng minh vai trò của nhánh `else`.

## 9. Checklist và bài tập tự luyện

Trước khi quyết định dùng cấu trúc nào, hãy hỏi:

- Một đối tượng có thể thỏa **nhiều quy tắc cần cùng chạy**, hay chỉ được **chọn một kết quả**?
- Các điều kiện có chồng lấp không? Nếu có, chọn **tất cả** hay ưu tiên **điều kiện đầu tiên**?
- Thứ tự xét điều kiện có làm thay đổi kết quả hoặc tác dụng phụ không?
- Khi mọi điều kiện sai, có cần nhánh `else` làm mặc định không?
- Có điều kiện phụ thuộc vào guard (null, chỉ số mảng, trạng thái...) không?

**Bài 1.** Với `int score = 90`, dự đoán có bao nhiêu `if` độc lập đúng cho các ngưỡng 60, 80, 90. Chuỗi `if/else if/else` từ cao xuống sẽ chạy bao nhiêu nhánh?

**Bài 2.** Cho hai cờ `sendEmail=true` và `saveLog=true`. Giải thích vì sao đổi hai `if` độc lập thành `if/else if` khiến một hành động bị bỏ qua.

**Bài 3.** Đổi chuỗi xét ngưỡng điểm theo thứ tự `>=60`, `>=80`, `>=90` thành đúng thứ tự và kiểm tra với điểm 95.

**Bài 4.** Viết xử lý `String name` có ba trạng thái null, blank, có nội dung bằng `if/else if/else` sao cho không ném `NullPointerException`.

**Bài 5.** Viết hai phương thức: một phương thức thu thập **tất cả** cảnh báo thỏa điều kiện, một phương thức trả **cảnh báo ưu tiên cao nhất**. Cấu trúc nào phù hợp cho từng phương thức?

### Ghi nhớ

**Nhiều `if` độc lập có thể thực hiện nhiều nhánh; `if / else if / else` là một chuỗi chỉ chọn tối đa một nhánh — nhánh đúng đầu tiên.** Với nhiều `if`, những điều kiện tiếp theo vẫn được xét nếu luồng tiếp tục bình thường; với `else if`, điều kiện sau nhánh đã chọn không được đánh giá. Chọn cú pháp theo **ngữ nghĩa nghiệp vụ**, không chỉ theo số dòng mã.
