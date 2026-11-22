# Tránh lồng quá nhiều toán tử ba ngôi trong Java

> **Java core — language-basics / Logic và điều kiện**  
> **Yêu cầu:** Java 17+, một file Java độc lập, không cần thư viện ngoài.  
> **Mục tiêu:** Dùng `?:` cho lựa chọn ngắn gọn; hiểu cách nhóm, nhánh thực sự được đánh giá và lý do nên thay chuỗi `?:` dài bằng `if/else`, phương thức có tên hoặc `switch` expression.

## 1. Toán tử ba ngôi `?:` là gì?

Cú pháp:

~~~java
result = condition ? valueIfTrue : valueIfFalse;
~~~

`condition` phải là biểu thức `boolean` hoặc `Boolean` có thể unbox thành `boolean`; nếu `Boolean` là `null` thì có thể ném `NullPointerException` khi đánh giá điều kiện. Java **chỉ đánh giá một trong hai nhánh kết quả**, tùy điều kiện:

~~~java
int age = 20;
String category = age >= 18 ? "adult" : "minor";
System.out.println(category); // adult
~~~

`?:` là **biểu thức tạo ra một giá trị**, khác `if/else` là cấu trúc điều khiển luồng. Nó phù hợp khi cả hai nhánh là biểu thức ngắn, dễ đọc, không mang tác dụng phụ khó hiểu.

## 2. Lồng `?:` nhiều tầng vẫn hợp lệ nhưng khó đọc

Ví dụ phân loại điểm:

~~~java
int score = 82;
String grade = score >= 90 ? "A"
             : score >= 80 ? "B"
             : score >= 70 ? "C"
             : "D";
~~~

Java cho phép biểu thức điều kiện **kết hợp từ phải sang trái**. Cách nhóm tương ứng:

~~~java
String grade = score >= 90 ? "A"
             : (score >= 80 ? "B"
             : (score >= 70 ? "C" : "D"));
~~~

Nếu `score == 82` thì `grade == "B"` về nội dung. Nhánh cho điểm từ 70 trở xuống không cần chạy khi đã chọn nhánh B.

Vấn đề là người đọc phải tự xác định:

- Mỗi dấu `?` thuộc điều kiện nào, mỗi dấu `:` thuộc nhánh nào.
- Các điều kiện có **thứ tự ưu tiên nghiệp vụ** không (ví dụ ngưỡng 90 phải xét trước 80).
- Nhánh mặc định cuối cùng ứng với trường hợp nào.
- Khi thêm một mức phân loại, ngoặc và căn lề có còn đúng không.

**Nguyên tắc:** Càng nhiều điều kiện/nhánh, `if/else` càng dễ kiểm tra, đặt breakpoint và thay đổi. Không có một “giới hạn cú pháp” bắt buộc về số tầng; đây là khuyến nghị về chất lượng mã.

## 3. Cách viết rõ hơn bằng `if/else`

~~~java
static String grade(int score) {
    if (score >= 90) {
        return "A";
    } else if (score >= 80) {
        return "B";
    } else if (score >= 70) {
        return "C";
    } else {
        return "D";
    }
}
~~~

Cách này giữ **cùng thứ tự xét ngưỡng** nhưng mỗi điều kiện là một nhánh rõ ràng. Có thể dùng *guard clauses* để tránh lồng khối:

~~~java
static String gradeWithEarlyReturns(int score) {
    if (score >= 90) return "A";
    if (score >= 80) return "B";
    if (score >= 70) return "C";
    return "D";
}
~~~

Với nhánh nhiều dòng, cần log, xử lý lỗi hoặc gọi phương thức có tác dụng phụ, dùng `if/else` thường dễ bảo trì hơn cố nhét cả logic vào `?:`.

## 4. Khi nào vẫn nên dùng một `?:`?

| Tình huống | Cách viết | Nhận xét |
| --- | --- | --- |
| Chọn một trong hai chuỗi ngắn | `passed ? "PASS" : "FAIL"` | Dễ đọc |
| Giá trị mặc định | `name != null ? name : "guest"` | Giữ guard trước nhánh sử dụng |
| Chọn nhãn sau nhiều ngưỡng | `a ? "A" : b ? "B" : c ? "C" : "D"` | Nên cân nhắc `if/else` |
| Hai nhánh nhiều lệnh hoặc log | `condition ? complexA() : complexB()` | Tách phương thức hoặc dùng `if/else` khi logic phức tạp |
| Nhiều trạng thái rời rạc | Chuỗi kiểm tra `status == ... ? ...` | Dùng `switch` expression/enum khi phù hợp |

`?:` chỉ dùng được khi hai nhánh có kiểu **tương thích theo quy tắc kiểu của Java**. Ví dụ `true ? 1 : 2.5` có kiểu `double` và trả `1.0`; không phải lúc nào kiểu kết quả cũng giống đúng kiểu của nhánh được chọn. Tránh dựa vào phép chuyển kiểu ngầm khó đoán ở chuỗi `?:` nhiều tầng.

## 5. Java 17: `switch` expression cho lựa chọn theo trạng thái

Với một trạng thái có nhiều giá trị rời rạc, `switch` expression có thể sáng sủa hơn chuỗi `?:`:

~~~java
enum State { NEW, APPROVED, REJECTED }

static String label(State state) {
    return switch (state) {
        case NEW -> "New";
        case APPROVED -> "Approved";
        case REJECTED -> "Rejected";
    };
}
~~~

Đây là cú pháp chuẩn trong Java 17, không cần bật preview. `switch` expression phải **exhaustive** (bao phủ hết các trường hợp). Ở ví dụ `enum` trên, đã liệt kê đủ ba hằng; nếu bổ sung trạng thái mới, trình biên dịch sẽ buộc xử lý cho phù hợp.

**Chọn công cụ theo bài toán:** Dãy kiểm tra **khoảng số** thường hợp với `if/else if`; tập **trạng thái rời rạc** thường hợp với `switch`. Không ép mọi bài toán sang `switch` chỉ để bỏ dấu `?:`.

## 6. Nhánh không được chọn không chạy — nhưng cẩn thận khi refactor

~~~java
StringBuilder log = new StringBuilder();
String selected = false
        ? trace(log, "X", "unused")
        : trace(log, "R", "chosen");
// selected="chosen", log="R"; nhánh X hoàn toàn không chạy.
~~~

Các điều kiện trong chuỗi `?:` lồng nhau được đánh giá theo cách nhóm và **chỉ khi cần**. Nếu nhánh không được chọn gọi hàm, tăng biến, truy cập null hoặc ném ngoại lệ, tác dụng phụ đó không xảy ra trong lần đánh giá ấy.

Tuy nhiên, **tránh nhét tác dụng phụ vào điều kiện hoặc nhánh** chỉ vì cú pháp cho phép. Khi chuyển sang `if/else`, phải giữ nguyên thứ tự xét điều kiện, không gọi lại hàm có side effect và không vô tình thực hiện cả hai nhánh.

Ví dụ guard an toàn:

~~~java
String text = null;
String display = text != null ? text.toUpperCase() : "(unknown)";
// Không gọi text.toUpperCase() khi text == null.
~~~

Ví dụ quá phức tạp để viết một dòng:

~~~java
// Khó kiểm tra khi tăng số nhánh:
String access = !loggedIn ? "SIGN_IN"
              : suspended ? "BLOCKED"
              : admin ? "ADMIN"
              : "USER";
~~~

Refactor bằng phương thức rõ nghĩa:

~~~java
static String accessLabel(boolean loggedIn,
                          boolean suspended,
                          boolean admin) {
    if (!loggedIn) return "SIGN_IN";
    if (suspended) return "BLOCKED";
    return admin ? "ADMIN" : "USER";
}
~~~

Giữ một `?:` đơn giản ở cuối vẫn ổn; mục tiêu là **giảm độ phức tạp**, không cấm tuyệt đối toán tử ba ngôi.

## 7. Chương trình Java 17+ runnable

Tạo file **ReadableTernaryDemo.java**:

~~~java
public final class ReadableTernaryDemo {
    enum State { NEW, APPROVED, REJECTED }

    private static String gradeNested(int score) {
        return score >= 90 ? "A"
             : score >= 80 ? "B"
             : score >= 70 ? "C"
             : "D";
    }

    private static String gradeClear(int score) {
        if (score >= 90) return "A";
        if (score >= 80) return "B";
        if (score >= 70) return "C";
        return "D";
    }

    private static String accessLabel(boolean loggedIn,
                                      boolean suspended,
                                      boolean admin) {
        if (!loggedIn) return "SIGN_IN";
        if (suspended) return "BLOCKED";
        return admin ? "ADMIN" : "USER";
    }

    private static String stateLabel(State state) {
        return switch (state) {
            case NEW -> "New";
            case APPROVED -> "Approved";
            case REJECTED -> "Rejected";
        };
    }

    private static String trace(StringBuilder log,
                                String label, String value) {
        log.append(label);
        return value;
    }

    public static void main(String[] args) {
        for (int score : new int[] {95, 82, 74, 40}) {
            System.out.println("grade=" + score + ":"
                    + gradeNested(score) + "/" + gradeClear(score));
        }

        boolean passed = true;
        System.out.println("simple=" + (passed ? "PASS" : "FAIL"));

        System.out.println("accessGuest="
                + accessLabel(false, false, true));
        System.out.println("accessBlocked="
                + accessLabel(true, true, true));
        System.out.println("accessAdmin="
                + accessLabel(true, false, true));
        System.out.println("accessUser="
                + accessLabel(true, false, false));

        System.out.println("state=" + stateLabel(State.APPROVED));

        String name = null;
        String display = name != null ? name.toUpperCase() : "(unknown)";
        System.out.println("nullSafe=" + display);

        StringBuilder branchLog = new StringBuilder();
        String selected = false
                ? trace(branchLog, "X", "unused")
                : trace(branchLog, "R", "chosen");
        System.out.println("selected=" + selected);
        System.out.println("branchTrace=" + branchLog);

        double numeric = true ? 1 : 2.5;
        System.out.println("numericType=" + numeric);
    }
}
~~~

Biên dịch/chạy ở thư mục chứa file (Bash, PowerShell hoặc Command Prompt):

~~~bash
javac -encoding UTF-8 ReadableTernaryDemo.java
java ReadableTernaryDemo
~~~

**Expected stdout chính xác:**

~~~text
grade=95:A/A
grade=82:B/B
grade=74:C/C
grade=40:D/D
simple=PASS
accessGuest=SIGN_IN
accessBlocked=BLOCKED
accessAdmin=ADMIN
accessUser=USER
state=Approved
nullSafe=(unknown)
selected=chosen
branchTrace=R
numericType=1.0
~~~

Hai cột điểm `A/A`, `B/B`, ... chứng tỏ hai cách triển khai phân loại thống nhất với dữ liệu thử; `branchTrace=R` cho thấy nhánh X không được gọi. `numericType=1.0` minh họa kiểu kết quả do Java quyết định, không chỉ dựa vào literal `1` của nhánh được chọn.

## 8. Checklist và bài tập

Trước khi giữ một chuỗi `?:` lồng nhau, tự kiểm tra:

- Có thể hiểu kết quả chỉ bằng một lần đọc, không cần đếm dấu `?`/`:` không?
- Các điều kiện có thứ tự ưu tiên rõ ràng và trường hợp mặc định dễ nhận thấy không?
- Có nhánh nào cần nhiều câu lệnh, log, exception hoặc thay đổi trạng thái không?
- Khi thêm nhánh mới, đoạn mã có dễ viết test cho các đường đi không?
- `if/else`, helper có tên hoặc `switch` expression có giúp ý nghĩa sáng tỏ hơn không?

**Bài 1.** Viết lại chuỗi chọn `"A"/"B"/"C"/"D"` từ điểm bằng `if/else if`; thử các mốc 69, 70, 79, 80, 89, 90.

**Bài 2.** Giải thích cách nhóm của `a ? x : b ? y : z`. Với `a=false` và `b=true`, giá trị được chọn là gì?

**Bài 3.** Chuyển lựa chọn theo trạng thái `NEW`/`APPROVED`/`REJECTED` sang `switch` expression của Java 17.

**Bài 4.** Cho `String s = null;`, giải thích tại sao `s != null ? s.trim() : ""` không ném `NullPointerException`.

**Bài 5.** Với lời gọi có side effect trong mỗi nhánh `?:`, trình bày cách refactor sang `if/else` mà vẫn chỉ thực hiện **một nhánh được chọn**.

### Ghi nhớ

**`?:` tốt cho lựa chọn ngắn, nhưng lồng nhiều tầng làm điều kiện khó đọc và khó bảo trì.** Java nhóm biểu thức điều kiện từ phải sang trái và chỉ đánh giá nhánh được chọn. Khi có nhiều ngưỡng, ưu tiên `if/else if`; khi có nhiều trạng thái rời rạc, cân nhắc `switch` expression; với quy tắc nghiệp vụ, đặt tên phương thức rõ ràng.
