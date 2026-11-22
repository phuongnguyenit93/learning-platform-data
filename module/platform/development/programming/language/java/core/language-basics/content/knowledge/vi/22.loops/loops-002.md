# `do-while` thực thi thân ít nhất một lần trong Java

> **Java core — language-basics / Vòng lặp**  
> **Môi trường:** JDK 17+, một file Java độc lập, không cần thư viện ngoài.  
> **Mục tiêu:** Hiểu vì sao `do-while` kiểm tra điều kiện **sau** thân, chọn đúng giữa `while` và `do-while`, sử dụng vòng lặp để thử lại thao tác, và tránh các lỗi liên quan đến dấu `;`, `break`, `continue`.

## 1. Cú pháp và thứ tự thực thi

~~~java
do {
    // Công việc cần thực hiện.
} while (condition);
~~~

**Thứ tự khi chương trình đi tới vòng lặp:**

1. Thực thi thân `do { ... }` **trước khi kiểm tra điều kiện lần đầu**.
2. Sau khi thân hoàn thành bình thường, đánh giá `condition`, bắt buộc có kiểu `boolean` hoặc `Boolean` có thể unbox.
3. Nếu điều kiện `true`, quay lại thực thi thân; nếu `false`, thoát vòng lặp và chạy câu lệnh kế tiếp.

Nếu chương trình đã đi tới `do` thì thân **được bắt đầu ít nhất một lần**, kể cả điều kiện sẽ sai ngay ở lần kiểm tra đầu tiên. Điều đó không có nghĩa mọi câu lệnh trong thân chắc chắn chạy xong: `break`, `return`, ngoại lệ hoặc luồng bị ngắt có thể kết thúc sớm.

~~~java
int count = 0;

do {
    count++;
    System.out.println("count=" + count);
} while (count < 3);

// In count=1, count=2, count=3.
~~~

Dấu **`;` sau `while (condition)` là bắt buộc** trong cú pháp `do-while`. Đây là khác biệt dễ quên so với `while (condition) { ... }` thông thường.

## 2. So sánh `while` và `do-while` khi điều kiện sai ngay từ đầu

~~~java
int a = 0;
while (a < 0) {
    a++;
}

int b = 0;
do {
    b++;
} while (b < 0);

System.out.println(a); // 0
System.out.println(b); // 1
~~~

| Tiêu chí | `while` | `do-while` |
| --- | --- | --- |
| Kiểm tra điều kiện lần đầu | **Trước** thân | **Sau** thân |
| Điều kiện ban đầu false | Thân chạy **0 lần** | Thân chạy **1 lần** |
| Phù hợp với | Công việc chỉ được phép chạy nếu điều kiện đang đúng | Công việc phải thử/thực hiện lần đầu rồi mới quyết định lặp |
| Dấu `;` ở cuối cấu trúc | Không đặt sau khối `while { ... }` | **Phải có** sau `while (condition)` |

Đừng chọn `do-while` chỉ vì cú pháp ngắn. Hãy hỏi: **có cần thực hiện thao tác đầu tiên trước khi biết nên lặp lại không?** Nếu cần kiểm tra điều kiện trước khi cho phép thao tác, `while` hoặc `for` thường hợp lý hơn.

## 3. Bảng diễn tiến một vòng lặp cụ thể

Giả sử `n = 0` và điều kiện `n < 3`:

| Lượt thân | `n` trước thân | `n` sau `n++` | Kiểm tra `n < 3` | Tiếp tục? |
| ---: | ---: | ---: | --- | --- |
| 1 | 0 | 1 | true | Có |
| 2 | 1 | 2 | true | Có |
| 3 | 2 | 3 | false | Không |

Bảng này giúp kiểm tra lỗi lệch một lần (*off-by-one*). Trong `do-while`, điều kiện được đánh giá **sau khi** `n` đã tăng, nên chương trình in ba lượt, không phải bốn.

Một tình huống đơn giản chỉ muốn thực thi đúng một lần:

~~~java
int executions = 0;
do {
    executions++;
} while (false);
// executions == 1.
~~~

Cú pháp này hợp lệ, nhưng nếu **luôn chỉ thực hiện một lần** thì một khối lệnh thường dễ đọc hơn; không cần ép công việc một lần vào vòng lặp.

## 4. Ví dụ sử dụng: thử lại cho tới khi đầu vào hợp lệ

Với chương trình nhập liệu, có thể cần **đọc lần đầu**, kiểm tra kết quả, rồi hỏi lại khi không hợp lệ. Ví dụ dưới đây sử dụng mảng đầu vào mô phỏng để chạy bằng CLI mà không phải nhập tay:

~~~java
int[] candidates = {-2, 0, 7};
int index = 0;
int selected;

do {
    selected = candidates[index++];
    System.out.println("candidate=" + selected);
} while (selected <= 0 && index < candidates.length);

System.out.println("selected=" + selected);
~~~

Kết quả lần lượt là `candidate=-2`, `candidate=0`, `candidate=7` và `selected=7`.

**Lưu ý an toàn:** Ví dụ có ít nhất một phần tử. Nếu mảng có thể rỗng, phải kiểm tra độ dài **trước khi vào `do`** vì thân vẫn thử truy cập mảng một lần. Điều kiện `index < candidates.length` ngăn việc lặp tiếp quá giới hạn nhưng **không bảo vệ lần truy cập đầu tiên**.

Ngoài ra, nếu dữ liệu thử hết mà vẫn không có phần tử hợp lệ, vòng lặp cũng kết thúc vì hết dữ liệu; ứng dụng thực cần phân biệt **hết lượt thử** với **đã có kết quả hợp lệ**, ví dụ kiểm tra `selected > 0` sau vòng lặp.

## 5. `break` và `continue` trong `do-while`

- `break;` kết thúc ngay vòng lặp gần nhất; điều kiện ở cuối vòng **không** được đánh giá cho lượt bị `break`.
- `continue;` bỏ qua phần thân còn lại của lượt hiện tại và chuyển tới bước **đánh giá điều kiện `while (...)`** rồi mới quyết định có vào lượt mới hay không.
- `return` kết thúc phương thức, có thể đồng thời kết thúc vòng lặp; ngoại lệ chưa xử lý cũng có thể ngắt luồng.

Ví dụ với `break`:

~~~java
int tries = 0;
do {
    tries++;
    if (tries == 2) {
        System.out.println("breakAt=" + tries);
        break;
    }
} while (tries < 4);
// In: breakAt=2; tries == 2.
~~~

Ví dụ với `continue`:

~~~java
int i = 0;
do {
    i++;                         // Luôn cập nhật i trước continue.
    if (i % 2 == 0) {
        continue;
    }
    System.out.println("odd=" + i);
} while (i < 4);
// In odd=1, odd=3; i == 4.
~~~

Ở lượt `i == 2`, `continue` không trở lại đầu thân ngay lập tức: Java **kiểm tra `i < 4`** trước. Nếu quên cập nhật biến kiểm soát trước `continue`, vòng lặp có thể không bao giờ kết thúc.

## 6. Các lỗi phổ biến

| Lỗi | Vì sao nguy hiểm | Cách sửa |
| --- | --- | --- |
| Quên `;` sau `while (condition)` | Sai cú pháp `do-while` | Viết `} while (condition);` |
| Nghĩ điều kiện được xét trước thân | Có thể chạy một lần ngoài ý muốn | Dùng `while` nếu phải kiểm tra trước |
| Điều kiện không bao giờ false | Vòng lặp vô hạn, tốn tài nguyên | Cập nhật trạng thái và quy định điểm dừng |
| `continue` trước thao tác cập nhật | Có thể kẹt cùng một trạng thái | Cập nhật trước `continue` hoặc thiết kế lại |
| Dùng `do` để truy cập mảng có thể rỗng | Truy cập sai chỉ số ở lượt đầu | Guard kiểm tra rỗng trước vòng lặp |
| Cho rằng kết thúc vòng nghĩa là dữ liệu hợp lệ | Có thể dừng do hết lượt thử | Kiểm tra riêng trạng thái thành công |
| Dùng `int` thay vì boolean làm điều kiện | Không biên dịch trong Java | So sánh tường minh như `count < limit` |

Ví dụ vòng lặp dễ bị vô hạn, **không nên chạy**:

~~~java
// int x = 0;
// do {
//     System.out.println(x);
// } while (x < 3); // x không đổi, điều kiện luôn đúng.
~~~

`Boolean` wrapper có giá trị `null` cũng không phải một giá trị điều kiện hợp lệ lúc chạy: Java sẽ cố unbox và có thể ném `NullPointerException`. Dùng biến `boolean` nguyên thủy hoặc đảm bảo wrapper không null.

## 7. Chương trình Java 17+ chạy độc lập

Tạo file **DoWhileDemo.java**:

~~~java
public final class DoWhileDemo {
    public static void main(String[] args) {
        int whileCount = 0;
        while (whileCount < 0) {
            whileCount++;
        }
        System.out.println("whileInitiallyFalse=" + whileCount);

        int doCount = 0;
        do {
            doCount++;
        } while (doCount < 0);
        System.out.println("doInitiallyFalse=" + doCount);

        int rounds = 0;
        do {
            rounds++;
            System.out.println("round=" + rounds);
        } while (rounds < 3);

        int[] candidates = {-2, 0, 7};
        int index = 0;
        int selected;
        do {
            selected = candidates[index++];
            System.out.println("candidate=" + selected);
        } while (selected <= 0 && index < candidates.length);
        System.out.println("selected=" + selected);
        System.out.println("valid=" + (selected > 0));

        int tries = 0;
        do {
            tries++;
            if (tries == 2) {
                System.out.println("breakAt=" + tries);
                break;
            }
        } while (tries < 4);
        System.out.println("breakCount=" + tries);

        int i = 0;
        do {
            i++;
            if (i % 2 == 0) {
                continue;
            }
            System.out.println("odd=" + i);
        } while (i < 4);
        System.out.println("continueCount=" + i);

        int once = 0;
        do {
            once++;
        } while (false);
        System.out.println("once=" + once);
    }
}
~~~

Biên dịch và chạy tại thư mục chứa file (PowerShell, Command Prompt hoặc Bash):

~~~bash
javac -encoding UTF-8 DoWhileDemo.java
java DoWhileDemo
~~~

**Expected stdout chính xác:**

~~~text
whileInitiallyFalse=0
doInitiallyFalse=1
round=1
round=2
round=3
candidate=-2
candidate=0
candidate=7
selected=7
valid=true
breakAt=2
breakCount=2
odd=1
odd=3
continueCount=4
once=1
~~~

Đối chiếu: `doInitiallyFalse=1` khẳng định thân chạy một lần khi điều kiện ban đầu false; `round=1..3` thể hiện kiểm tra điều kiện sau thân; `breakCount=2` và `continueCount=4` minh họa hai lệnh điều khiển. `valid=true` chứng minh giá trị cuối cùng hợp lệ, thay vì chỉ suy luận từ việc vòng lặp đã dừng.

## 8. Bài tập và checklist

**Bài 1.** Với `int n = 5;`, so sánh số lần thân được chạy của `while (n < 3)` và `do { n++; } while (n < 3);`. Giải thích nguyên nhân.

**Bài 2.** Viết `do-while` tăng biến `i` từ 0 và in `i` cho đến khi `i == 4`. Lập bảng trạng thái trước thân, sau thân và sau phép kiểm tra.

**Bài 3.** Cho một danh sách số có thể rỗng: hãy bổ sung guard trước `do` để tránh truy cập sai phần tử đầu tiên, và trả trạng thái lỗi nếu hết danh sách mà chưa gặp số dương.

**Bài 4.** Chèn `continue` khi `i` là số chẵn, chỉ in số lẻ từ 1 đến 5. Đặt thao tác cập nhật ở đâu để chắc chắn vòng lặp kết thúc?

**Bài 5.** Dùng `break` khi gặp giá trị cần tìm và giải thích điều kiện cuối vòng có còn được đánh giá trong lượt bị `break` hay không.

**Checklist:** Điều kiện boolean hợp lệ chưa? Biến kiểm soát có thay đổi trong mọi đường đi cần thiết không? Lượt đầu tiên có an toàn không? Có phân biệt dừng do thành công, giới hạn hay lỗi không? Đã ghi `;` kết thúc cú pháp `do-while` chưa?

### Ghi nhớ

**`do { ... } while (condition);` luôn bắt đầu thực hiện thân trước lần kiểm tra điều kiện đầu tiên.** Nó thích hợp cho công việc **phải thử một lần rồi mới quyết định lặp**. Khác với `while`, điều kiện ban đầu false không ngăn lượt đầu; hãy kiểm tra an toàn đầu vào, điểm dừng và vị trí cập nhật biến, đặc biệt khi dùng `continue`.
