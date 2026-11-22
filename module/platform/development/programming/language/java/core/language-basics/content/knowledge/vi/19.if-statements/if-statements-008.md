# Kiểm tra từng nhánh bằng bảng trường hợp đầu vào trong Java

> **Java core — language-basics / Rẽ nhánh if**  
> **Môi trường:** JDK 17+, một file Java độc lập, không dùng thư viện bên ngoài.  
> **Mục tiêu:** Chuyển các nhánh `if / else if / else` thành **bảng trường hợp đầu vào – đầu ra mong đợi**, kiểm thử các biên và điều kiện chồng lấp, chạy kiểm tra tự động và nhận biết giới hạn của việc thử một vài giá trị ngẫu nhiên.

## 1. Tại sao cần bảng kiểm tra từng nhánh?

Một chuỗi `if / else if / else` có nhiều đường đi. Chạy một giá trị thuận tiện, ví dụ chỉ `score = 95`, **không chứng minh** các nhánh khác hoạt động đúng.

Cách làm có thể lặp lại:

1. Đọc điều kiện theo đúng **thứ tự** và xác định những nhánh có thể được chọn.
2. Ghi rõ mỗi **đầu vào**, **nhánh mong đợi** và **kết quả mong đợi** vào bảng.
3. Chọn ít nhất một trường hợp đi vào **mỗi nhánh**, kể cả `else` và đường xử lý dữ liệu không hợp lệ.
4. Thêm dữ liệu **ngay dưới, đúng tại và ngay trên** các ngưỡng có ý nghĩa.
5. Chạy chương trình, so sánh **actual** với **expected**, báo FAIL khi khác nhau.

**Lưu ý:** Bảng do người viết thiết kế là một bộ *test cases*, không tự động chứng minh mọi đầu vào đều đúng. Một bảng tốt giúp nhìn rõ nhánh còn thiếu; kiểm thử càng chặt cần xét cả tổ hợp điều kiện, lỗi, null và thay đổi trạng thái.

## 2. Ví dụ: phân loại điểm theo chuỗi loại trừ

Quy tắc nghiệp vụ: điểm phải thuộc `0..100`; các nhãn lần lượt là `A` (≥90), `B` (≥75), `C` (≥50), `D` (còn lại).

~~~java
static String classifyScore(int score) {
    if (score < 0 || score > 100) {
        return "INVALID";
    } else if (score >= 90) {
        return "A";
    } else if (score >= 75) {
        return "B";
    } else if (score >= 50) {
        return "C";
    } else {
        return "D";
    }
}
~~~

Java chỉ chọn **nhánh đúng đầu tiên** trong chuỗi. Do đó cần kiểm tra ngưỡng cao trước ngưỡng thấp: nếu kiểm tra `score >= 50` trước `score >= 90`, điểm 95 có thể bị phân loại thành C.

Các nhánh cần được quan sát: `INVALID`, `A`, `B`, `C`, `D`. Riêng điều kiện đầu `score < 0 || score > 100` có **hai lý do khác nhau** khiến giá trị không hợp lệ: quá thấp hoặc quá cao. Kiểm thử cả hai để tránh bỏ sót lỗi chỉ xuất hiện ở một phía.

## 3. Bảng test cases và giá trị sát ranh giới

| Đầu vào `score` | Nhánh mong đợi | Expected | Lý do chọn |
| ---: | --- | --- | --- |
| -1 | Không hợp lệ | `INVALID` | Dưới ngưỡng 0 |
| 0 | `else` | `D` | Biên dưới hợp lệ |
| 49 | `else` | `D` | Ngay dưới 50 |
| 50 | `score >= 50` | `C` | Ngay tại 50 |
| 74 | `score >= 50` | `C` | Ngay dưới 75 |
| 75 | `score >= 75` | `B` | Ngay tại 75 |
| 89 | `score >= 75` | `B` | Ngay dưới 90 |
| 90 | `score >= 90` | `A` | Ngay tại 90 |
| 100 | `score >= 90` | `A` | Biên trên hợp lệ |
| 101 | Không hợp lệ | `INVALID` | Trên ngưỡng 100 |

Bảng bao phủ **cả năm nhánh đầu ra** và các biên quan trọng. Đặc biệt, với `score == 50`, điều kiện `score >= 50` phải đúng; với `score == 49` phải sai. Cặp này giúp phát hiện lỗi vô tình đổi `>=` thành `>`.

Với nhánh kiểm tra `score < 0 || score > 100`, `score = -1` làm vế trái đúng nên vế phải không chạy do short-circuit; `score = 101` làm vế trái sai và vế phải đúng. Hai trường hợp kiểm thử các tình huống khác nhau của điều kiện ghép.

**Không nhất thiết liệt kê mọi điểm 0..100** để kiểm tra biên, nhưng có thể dùng thêm kiểm thử toàn miền hoặc sinh trường hợp khi yêu cầu độ tin cậy cao hơn.

## 4. Bảng cho nhiều `if` độc lập khác với chuỗi `else if`

Với hai cờ `review` và `urgent`, **cả hai hành động có thể cần chạy**:

~~~java
StringBuilder actions = new StringBuilder();
if (review) {
    actions.append("REVIEW");
}
if (urgent) {
    if (actions.length() > 0) actions.append("+");
    actions.append("URGENT");
}
String result = actions.length() == 0 ? "NONE" : actions.toString();
~~~

Các trường hợp phải kiểm tra:

| `review` | `urgent` | Expected | Nhánh thực thi |
| --- | --- | --- | --- |
| false | false | `NONE` | Không nhánh nào |
| true | false | `REVIEW` | Chỉ `if` đầu |
| false | true | `URGENT` | Chỉ `if` thứ hai |
| true | true | `REVIEW+URGENT` | **Cả hai `if`** |

Nếu vô tình thay `if (urgent)` bằng `else if (urgent)`, trường hợp `true, true` sẽ bị thiếu `URGENT`. Đây là lý do bảng **tổ hợp các điều kiện** quan trọng hơn chỉ thử riêng từng cờ.

Với một chuỗi loại trừ `if/else if/else`, bảng lại cần xác nhận **chỉ một nhánh** chạy và điều kiện phía sau nhánh đã chọn không được đánh giá.

## 5. Phân biệt độ phủ nhánh và kiểm thử giá trị biên

| Kỹ thuật | Câu hỏi cần trả lời | Ví dụ |
| --- | --- | --- |
| Bao phủ nhánh đầu ra | Mọi nhánh `if/else if/else` đã được chọn ít nhất một lần chưa? | Đầu ra `INVALID`, `A`, `B`, `C`, `D` |
| Kiểm tra giá trị biên | Dấu `<`, `<=`, `>`, `>=` có chính xác tại ranh giới không? | 49/50, 74/75, 89/90 |
| Tổ hợp điều kiện | Các điều kiện đồng thời đúng/sai có bị bỏ quên không? | Hai cờ true/true |
| Điều kiện ghép | Mỗi nguyên nhân làm một điều kiện ghép đúng/sai đã được xét chưa? | Điểm `-1` và `101` |
| Giá trị ngoại lệ | Đầu vào ngoài miền, null hoặc trạng thái không hợp lệ được xử lý ra sao? | `score=-1`, `score=101` |

**Bao phủ nhánh chưa đủ để bảo đảm tính đúng.** Ví dụ một test có thể vào nhánh B bằng điểm 80, nhưng không phát hiện lỗi ở biên 75. Độ phủ cao cũng không thay thế việc đối chiếu với **yêu cầu nghiệp vụ**.

Khi điều kiện phụ thuộc thứ tự hoặc có side effect, hãy lập bảng thể hiện **biểu thức nào được đánh giá**; không giả định mọi `else if` đều chạy. Với `null`, cần thiết kế đầu vào có và không có dữ liệu, kiểm tra guard trước khi gọi phương thức.

## 6. Chương trình Java 17+ tự kiểm tra bảng đầu vào

Tạo file **IfBranchCaseTableDemo.java**:

~~~java
public final class IfBranchCaseTableDemo {
    private record ScoreCase(int input, String expected) {}
    private record FlagCase(boolean review, boolean urgent, String expected) {}

    private static String classifyScore(int score) {
        if (score < 0 || score > 100) {
            return "INVALID";
        } else if (score >= 90) {
            return "A";
        } else if (score >= 75) {
            return "B";
        } else if (score >= 50) {
            return "C";
        } else {
            return "D";
        }
    }

    private static String actions(boolean review, boolean urgent) {
        StringBuilder result = new StringBuilder();
        if (review) {
            result.append("REVIEW");
        }
        if (urgent) {
            if (result.length() > 0) {
                result.append("+");
            }
            result.append("URGENT");
        }
        return result.length() == 0 ? "NONE" : result.toString();
    }

    public static void main(String[] args) {
        ScoreCase[] scores = {
            new ScoreCase(-1, "INVALID"),
            new ScoreCase(0, "D"),
            new ScoreCase(49, "D"),
            new ScoreCase(50, "C"),
            new ScoreCase(74, "C"),
            new ScoreCase(75, "B"),
            new ScoreCase(89, "B"),
            new ScoreCase(90, "A"),
            new ScoreCase(100, "A"),
            new ScoreCase(101, "INVALID")
        };

        int scorePassed = 0;
        for (ScoreCase test : scores) {
            String actual = classifyScore(test.input());
            boolean passed = test.expected().equals(actual);
            if (passed) scorePassed++;
            System.out.println("score=" + test.input()
                    + ",expected=" + test.expected()
                    + ",actual=" + actual
                    + ",status=" + (passed ? "PASS" : "FAIL"));
        }
        System.out.println("scoreTests=" + scorePassed + "/" + scores.length);

        FlagCase[] flags = {
            new FlagCase(false, false, "NONE"),
            new FlagCase(true, false, "REVIEW"),
            new FlagCase(false, true, "URGENT"),
            new FlagCase(true, true, "REVIEW+URGENT")
        };

        int flagsPassed = 0;
        for (FlagCase test : flags) {
            String actual = actions(test.review(), test.urgent());
            boolean passed = test.expected().equals(actual);
            if (passed) flagsPassed++;
            System.out.println("review=" + test.review()
                    + ",urgent=" + test.urgent()
                    + ",expected=" + test.expected()
                    + ",actual=" + actual
                    + ",status=" + (passed ? "PASS" : "FAIL"));
        }
        System.out.println("flagTests=" + flagsPassed + "/" + flags.length);

        if (scorePassed != scores.length || flagsPassed != flags.length) {
            throw new AssertionError("At least one case failed");
        }
    }
}
~~~

Biên dịch và chạy trong thư mục chứa file (Bash, PowerShell hoặc Command Prompt):

~~~bash
javac -encoding UTF-8 IfBranchCaseTableDemo.java
java IfBranchCaseTableDemo
~~~

**Expected stdout chính xác:**

~~~text
score=-1,expected=INVALID,actual=INVALID,status=PASS
score=0,expected=D,actual=D,status=PASS
score=49,expected=D,actual=D,status=PASS
score=50,expected=C,actual=C,status=PASS
score=74,expected=C,actual=C,status=PASS
score=75,expected=B,actual=B,status=PASS
score=89,expected=B,actual=B,status=PASS
score=90,expected=A,actual=A,status=PASS
score=100,expected=A,actual=A,status=PASS
score=101,expected=INVALID,actual=INVALID,status=PASS
scoreTests=10/10
review=false,urgent=false,expected=NONE,actual=NONE,status=PASS
review=true,urgent=false,expected=REVIEW,actual=REVIEW,status=PASS
review=false,urgent=true,expected=URGENT,actual=URGENT,status=PASS
review=true,urgent=true,expected=REVIEW+URGENT,actual=REVIEW+URGENT,status=PASS
flagTests=4/4
~~~

Bài demo dùng `record` có sẵn trong Java 17 để khai báo từng dòng dữ liệu thử; test tách **expected** khỏi **actual** rồi so sánh bằng `equals`. Nếu thay đổi logic làm hai giá trị không trùng nhau, chương trình in `FAIL` và ném `AssertionError` sau khi chạy hết bảng.

Các giá trị expected phải được suy ra từ **đặc tả**, không sao chép máy móc từ output hiện tại của hàm cần kiểm thử; nếu không test có thể luôn PASS dù code sai yêu cầu.

## 7. Checklist trước khi kết luận nhánh đã được kiểm tra

- Tất cả nhánh có thể chọn, kể cả `else`, đã có ít nhất một test?
- Mọi ngưỡng có test ngay **dưới / bằng / trên** hay chưa?
- Điều kiện ghép `&&`/`||` có test cho các tình huống quyết định ở vế trái và vế phải?
- Nhiều `if` độc lập có test khi **cả hai cùng đúng**?
- Các trường hợp không hợp lệ, null, empty hoặc ngoài miền đã có expected rõ ràng?
- Mỗi hàng đều so sánh expected với actual và **báo lỗi khi mismatch**?
- Sau khi sửa thứ tự nhánh hoặc toán tử, các test cũ có được chạy lại không?

Để có độ tin cậy cao hơn, kết hợp test case table với kiểm thử tự động như JUnit khi dự án đã dùng framework; ví dụ trong bài này chỉ cần JDK 17 và chương trình `main` tự kiểm tra.

## 8. Bài tập thực hành

**Bài 1.** Lập bảng đầu vào cho `if (x < 0) ... else if (x == 0) ... else ...`. Chọn ít nhất `-1`, `0` và `1`, ghi đúng nhánh và expected.

**Bài 2.** Trong `classifyScore`, cố ý đổi `score >= 75` thành `score > 75`. Dòng nào trong bảng dự kiến FAIL? Vì sao?

**Bài 3.** Đổi thứ tự hai nhánh `score >= 90` và `score >= 50`. Hàng đầu vào nào giúp phát hiện lỗi chọn nhánh đầu tiên?

**Bài 4.** Với hai `if` độc lập cho `review` và `urgent`, giải thích vì sao cần đủ bốn tổ hợp. Điều gì xảy ra nếu đổi `if` thứ hai thành `else if`?

**Bài 5.** Thêm yêu cầu riêng cho `score == 100` (ví dụ nhãn `PERFECT`) và cập nhật cả code lẫn bảng test: nhánh mới nên đặt ở đâu để được chọn?

### Ghi nhớ

**Kiểm thử rẽ nhánh bắt đầu từ bảng đầu vào → nhánh dự kiến → kết quả dự kiến.** Mỗi nhánh cần có ca thử; các ngưỡng cần test sát biên; điều kiện chồng lấp và nhiều `if` độc lập cần test theo tổ hợp. Việc kiểm tra expected/actual chỉ có ý nghĩa khi expected được xác định độc lập với mã đang kiểm thử.
