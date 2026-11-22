# Khối lệnh và rủi ro bỏ dấu ngoặc nhọn trong Java

> **Java core — language-basics / Rẽ nhánh if**  
> **Yêu cầu:** Java 17+, một file Java độc lập, chỉ dùng thư viện chuẩn.  
> **Mục tiêu:** Hiểu `if`/`else` điều khiển **một câu lệnh** hoặc **một khối lệnh `{ ... }`**; nhận diện lỗi do bỏ ngoặc nhọn, sai lệch thụt lề, `else` gắn nhầm và dấu chấm phẩy thừa. Biết viết nhánh rõ ràng, dễ sửa và dễ kiểm thử.

## 1. Một câu lệnh khác với một khối lệnh

Cú pháp `if` cơ bản:

~~~java
if (condition) {
    // Các câu lệnh thuộc nhánh if.
}
~~~

`condition` phải có kiểu `boolean` (hoặc `Boolean` có thể unbox). Một **khối** `{ ... }` được Java xem như **một câu lệnh khối**, chứa được nhiều câu lệnh con.

Java cho phép bỏ ngoặc nhọn khi thân `if` chỉ là **một câu lệnh**:

~~~java
boolean ready = true;
if (ready)
    System.out.println("READY");
~~~

Nhưng khi cần hai thao tác cùng phụ thuộc `ready`, phải dùng khối:

~~~java
if (ready) {
    System.out.println("READY");
    System.out.println("AUDITED");
}
~~~

Ngoặc nhọn quyết định **phạm vi thuộc nhánh**, còn dấu cách và thụt lề chỉ giúp người đọc. Java không dùng mức thụt lề để gom các câu lệnh như một số ngôn ngữ khác.

## 2. Lỗi kinh điển: nhìn thụt lề tưởng cả hai câu cùng thuộc `if`

Đoạn này hợp lệ về cú pháp nhưng có thể sai nghiệp vụ:

~~~java
boolean authorized = false;
if (authorized)
    System.out.println("Access granted");
    System.out.println("Sensitive action"); // LUÔN chạy.
~~~

Java hiểu là:

~~~java
if (authorized) {
    System.out.println("Access granted");
}
System.out.println("Sensitive action");
~~~

Lệnh in `"Sensitive action"` **nằm ngoài** `if`, cho dù được thụt vào cùng mức với lệnh đầu. Khi `authorized == false`, lệnh đó **vẫn chạy**.

Cách sửa an toàn:

~~~java
if (authorized) {
    System.out.println("Access granted");
    System.out.println("Sensitive action");
}
~~~

**Rủi ro khi bảo trì:** Ban đầu có thể chỉ một dòng sau `if` nên chương trình đúng. Người sửa thêm dòng thứ hai theo cùng thụt lề nhưng quên `{}`, khiến dòng mới chạy vô điều kiện. Những lỗi này đặc biệt nghiêm trọng nếu thân `if` là bước xác thực, trừ tiền, xóa dữ liệu hoặc đổi trạng thái.

## 3. Ngoặc nhọn thay đổi liên kết giữa các `if` lồng nhau

Khi viết `if` lồng mà không dùng ngoặc nhọn, `else` thuộc `if` gần nhất chưa có `else` (*dangling else*), không theo thụt lề:

~~~java
if (isMember)
    if (hasTicket)
        System.out.println("Enter");
    else
        System.out.println("No ticket");
~~~

Nếu `isMember` false, **không in dòng nào**; `else` thuộc `if (hasTicket)` nhưng toàn bộ câu `if` bên trong bị bỏ qua. Muốn `else` thuộc `if` ngoài, phải đóng **khối thân của `if` ngoài** trước `else`:

~~~java
if (isMember) {
    if (hasTicket) {
        System.out.println("Enter");
    }
} else {
    System.out.println("Not a member");
}
~~~

Với `isMember=false`, đoạn sau in `Not a member`. Đây là **hai hành vi khác nhau**, không chỉ hai cách format. Bài hiện tại nhấn mạnh **khối ngoặc quyết định phạm vi**; bài kế tiếp phân tích chuyên sâu luật gắn `else`, hai `else` lồng nhau, bảng trường hợp và thứ tự đánh giá.


## 4. Dấu `;` thừa có thể tạo một nhánh rỗng

`;` đơn lẻ là **câu lệnh rỗng** (*empty statement*). Vì vậy:

~~~java
int attempts = 0;
if (false); // Dấu ; chính là toàn bộ thân if: không làm gì.
attempts++;
System.out.println(attempts); // 1
~~~

`attempts++` nằm **ngoài** `if` và chạy bất kể điều kiện false. Dấu `;` sau `if (condition)` thường là lỗi gõ phím.

**Đúng:**

~~~java
if (allowed) {
    performAction();
}
~~~

**Sai về ý định:**

~~~java
if (allowed); // Nhánh if rỗng.
{
    performAction(); // Khối này độc lập, vẫn chạy.
}
~~~

Dùng formatter và lint/static analysis để phát hiện `if` có thân rỗng bất thường; vẫn cần review ngữ nghĩa vì chương trình **có thể biên dịch bình thường**.

## 5. Ngoặc nhọn còn tạo phạm vi biến (*scope*)

Bên trong khối có thể khai báo biến cục bộ chỉ dùng trong khối:

~~~java
int total = 0;
if (true) {
    int increment = 7;
    total += increment;
}
System.out.println(total); // 7
// System.out.println(increment); // LỖI BIÊN DỊCH: ngoài phạm vi.
~~~

Ngoặc nhọn giúp giới hạn thời gian **biến cục bộ có thể được gọi bằng tên đó trong mã** (lexical scope); không có nghĩa mọi đối tượng được tạo trong khối bị hủy ngay khi khối kết thúc. Với `if` và `else`, mỗi khối có thể có các biến cục bộ riêng.

Cần chú ý **definite assignment** khi gán giá trị trong nhánh:

~~~java
int discount;
if (eligible) {
    discount = 10;
} else {
    discount = 0;
}
System.out.println(discount); // Hợp lệ: cả hai nhánh đều gán.
~~~

Nếu chỉ gán `discount` trong `if` nhưng không có `else`, sau đó dùng `discount` thì trình biên dịch có thể báo biến chưa được gán ở mọi đường đi. Ngoặc nhọn giúp thấy rõ đường đi, nhưng **không thay thế kiểm tra luồng gán của Java**.

## 6. Quy tắc chọn cách viết

| Tình huống | Nên làm |
| --- | --- |
| `if` hiện tại chỉ có một câu lệnh | Vẫn dùng `{ ... }` để dễ bổ sung sau này |
| `if` lồng `if / else` | Dùng khối và thụt lề rõ, tránh *dangling else* |
| Sau điều kiện có dấu `;` đáng ngờ | Kiểm tra xem có vô tình tạo câu lệnh rỗng không |
| Nhánh bảo vệ thao tác quan trọng | Đặt mọi thao tác được bảo vệ vào cùng một khối |
| Cần biến cục bộ phục vụ riêng một nhánh | Khai báo bên trong khối nhánh |
| Thêm/sửa câu lệnh trong code cũ không ngoặc | Xác minh lại phạm vi điều khiển trước và sau khi sửa |

**Khuyến nghị thực hành:** Luôn viết ngoặc nhọn cho `if`, `else if` và `else` ngay cả khi chỉ có một câu lệnh. Java không bắt buộc quy tắc này, nhưng nó làm ý định rõ ràng và giúp hạn chế lỗi khi thêm dòng. Format code tự động để phát hiện thụt lề đáng ngờ; viết test cho cả nhánh đúng và sai.

## 7. Chương trình Java 17+ chạy độc lập

Tạo file **IfBlocksDemo.java**:

~~~java
public final class IfBlocksDemo {
    private static void withoutBraces(boolean authorized) {
        if (authorized)
            System.out.println("unguardedProtected");
            System.out.println("unguardedAlways");
    }

    private static void withBraces(boolean authorized) {
        if (authorized) {
            System.out.println("guardedProtected");
            System.out.println("guardedAudit");
        }
        System.out.println("guardedAfter");
    }

    private static String danglingElse(boolean member, boolean ticket) {
        if (member)
            if (ticket)
                return "ENTER";
            else
                return "NO_TICKET";
        return "NO_BRANCH";
    }

    private static String outerElse(boolean member, boolean ticket) {
        if (member) {
            if (ticket) {
                return "ENTER";
            }
        } else {
            return "NOT_MEMBER";
        }
        return "NO_TICKET";
    }

    public static void main(String[] args) {
        System.out.println("authorized=false");
        withoutBraces(false);
        withBraces(false);

        System.out.println("authorized=true");
        withoutBraces(true);
        withBraces(true);

        System.out.println("danglingFalseTrue=" + danglingElse(false, true));
        System.out.println("danglingTrueFalse=" + danglingElse(true, false));
        System.out.println("danglingTrueTrue=" + danglingElse(true, true));

        System.out.println("outerFalseTrue=" + outerElse(false, true));
        System.out.println("outerTrueFalse=" + outerElse(true, false));
        System.out.println("outerTrueTrue=" + outerElse(true, true));

        int attempts = 0;
        if (false);
        attempts++;
        System.out.println("emptyStatementAttempts=" + attempts);

        int total = 0;
        if (true) {
            int increment = 7;
            total += increment;
        }
        System.out.println("blockScopeTotal=" + total);

        boolean eligible = false;
        int discount;
        if (eligible) {
            discount = 10;
        } else {
            discount = 0;
        }
        System.out.println("discount=" + discount);
    }
}
~~~

Biên dịch và chạy tại thư mục chứa file (Bash, PowerShell hoặc Command Prompt):

~~~bash
javac -encoding UTF-8 IfBlocksDemo.java
java IfBlocksDemo
~~~

**Expected stdout chính xác:**

~~~text
authorized=false
unguardedAlways
guardedAfter
authorized=true
unguardedProtected
unguardedAlways
guardedProtected
guardedAudit
guardedAfter
danglingFalseTrue=NO_BRANCH
danglingTrueFalse=NO_TICKET
danglingTrueTrue=ENTER
outerFalseTrue=NOT_MEMBER
outerTrueFalse=NO_TICKET
outerTrueTrue=ENTER
emptyStatementAttempts=1
blockScopeTotal=7
discount=0
~~~

Dòng `unguardedAlways` xuất hiện **cả khi authorized=false** dù nhìn như nằm trong `if`; `guardedAudit` chỉ xuất hiện khi true. `danglingFalseTrue=NO_BRANCH` khác `outerFalseTrue=NOT_MEMBER` vì `else` thuộc các `if` khác nhau. `emptyStatementAttempts=1` cho thấy `;` tạo thân rỗng.

## 8. Bài tập tự luyện

**Bài 1.** Dự đoán đầu ra với `boolean active = false; if (active) System.out.println("A"); System.out.println("B");`. Thêm ngoặc nhọn để cả A và B chỉ in khi `active` true.

**Bài 2.** Viết `if (member) if (ticket) enter(); else reject();` có ngoặc nhọn để `else` chắc chắn thuộc `if (member)`; nêu khác biệt khi `member=false`.

**Bài 3.** Giải thích ý nghĩa của `if (enabled); doWork();` và sửa lại để `doWork()` chỉ chạy khi `enabled` đúng.

**Bài 4.** Khai báo biến `int amount` trong khối `if`. Thử sử dụng bên ngoài khối và giải thích lỗi scope; viết cách lưu kết quả hợp lệ để dùng về sau.

**Bài 5.** Tạo `if/else` gán một biến ở cả hai nhánh, rồi thử xóa phép gán trong nhánh `else`. Vì sao Java không cho đọc biến cục bộ có thể chưa được gán?

### Ghi nhớ

**Không có `{}`, `if`/`else` chỉ điều khiển đúng một câu lệnh; thụt lề không quyết định luồng chạy.** `else` gắn với `if` gần nhất chưa có `else`, còn dấu `;` thừa có thể khiến thân `if` rỗng. Dùng ngoặc nhọn nhất quán để bảo vệ thao tác, làm rõ phạm vi biến và tránh lỗi khó nhìn thấy khi chỉnh sửa.
