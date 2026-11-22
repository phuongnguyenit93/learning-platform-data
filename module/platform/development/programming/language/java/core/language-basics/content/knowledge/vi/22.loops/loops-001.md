# `while` kiểm tra điều kiện trước mỗi lần lặp — Java 17+

Vòng lặp `while` thực thi một khối lệnh **chừng nào điều kiện còn đúng**. Điểm quan trọng nhất: Java **kiểm tra điều kiện trước mỗi lần chạy thân**, bao gồm cả lần đầu. Vì thế, nếu điều kiện sai ngay từ đầu, thân vòng lặp chạy **0 lần**.

~~~java
int n = 1;
while (n <= 3) {
    System.out.println(n);
    n++;
}
// In: 1, 2, 3; sau vòng lặp n == 4.
~~~

## 1. Cú pháp và thứ tự thực thi

~~~java
while (booleanCondition) {
    // Các lệnh thực hiện khi điều kiện true.
}
~~~

Quy trình:

1. **Đánh giá** biểu thức điều kiện `booleanCondition`.
2. Nếu `false`: thoát vòng `while`, tiếp tục câu lệnh ngay sau nó.
3. Nếu `true`: chạy thân vòng lặp, trừ trường hợp có điều khiển luồng như `break`, `return` hoặc ngoại lệ.
4. Sau khi thân hoàn tất bình thường (hoặc gặp `continue`), **quay lại bước 1**; không giữ nguyên kết quả điều kiện của lần trước.

~~~mermaid
flowchart TD
    A["Bắt đầu"] --> B{"Điều kiện true?"}
    B -- "Không" --> D["Câu lệnh sau while"]
    B -- "Có" --> C["Chạy thân while"]
    C --> B
~~~

**Điều kiện phải có kiểu `boolean`** (hoặc `Boolean` được unbox). Java không chấp nhận `while (1)` hay `while (number)` như một số ngôn ngữ khác; dùng biểu thức như `number > 0`.

## 2. Ví dụ Java 17+ chạy được bằng CLI

Tạo tệp UTF-8 tên **`WhilePrecheckDemo.java`**:

~~~java
public class WhilePrecheckDemo {
    static boolean check(int value) {
        System.out.println("check=" + value);
        return value < 2;
    }

    static void precheckTrace() {
        int n = 0;
        while (check(n)) {
            System.out.println("body=" + n);
            n++;
        }
        System.out.println("after=" + n);
    }

    static void zeroIterations() {
        int stock = 0;
        int visits = 0;
        while (stock > 0) {
            visits++;
            stock--;
        }
        System.out.println("visits=" + visits);
    }

    static void skipEvenNumbers() {
        int n = 0;
        while (n < 5) {
            n++; // Tiến triển trước nhánh continue.
            if (n % 2 == 0) {
                continue;
            }
            System.out.println("odd=" + n);
        }
        System.out.println("last=" + n);
    }

    static void stopOnSentinel() {
        String[] inputs = {"2", "bad", "4", "stop", "99"};
        int index = 0;
        int sum = 0;
        while (index < inputs.length) {
            String token = inputs[index++];
            if (token.equals("stop")) {
                System.out.println("found=stop");
                break;
            }
            try {
                sum += Integer.parseInt(token);
            } catch (NumberFormatException ex) {
                System.out.println("invalid=" + token);
            }
        }
        System.out.println("sum=" + sum);
        System.out.println("consumed=" + index);
    }

    static void exitInfiniteLoop() {
        int attempts = 0;
        while (true) {
            attempts++;
            if (attempts == 3) {
                System.out.println("breakAt=" + attempts);
                break;
            }
        }
        System.out.println("afterBreak=" + attempts);
    }

    public static void main(String[] args) {
        System.out.println("== count ==");
        int count = 1;
        while (count <= 3) {
            System.out.println("count=" + count);
            count++;
        }
        System.out.println("countAfter=" + count);

        System.out.println("== zero iterations ==");
        zeroIterations();

        System.out.println("== check before every body ==");
        precheckTrace();

        System.out.println("== continue ==");
        skipEvenNumbers();

        System.out.println("== sentinel and break ==");
        stopOnSentinel();

        System.out.println("== while true with exit ==");
        exitInfiniteLoop();
        System.out.println("done");
    }
}
~~~

Yêu cầu **JDK 17 trở lên**. Mở PowerShell (Windows) hoặc Bash (Linux/macOS) tại thư mục chứa tệp rồi chạy:

~~~bash
java -version
javac -version
javac -encoding UTF-8 WhilePrecheckDemo.java
java WhilePrecheckDemo
~~~

**Expected stdout chính xác** của riêng lệnh `java WhilePrecheckDemo`:

~~~text
== count ==
count=1
count=2
count=3
countAfter=4
== zero iterations ==
visits=0
== check before every body ==
check=0
body=0
check=1
body=1
check=2
after=2
== continue ==
odd=1
odd=3
odd=5
last=5
== sentinel and break ==
invalid=bad
found=stop
sum=6
consumed=4
== while true with exit ==
breakAt=3
afterBreak=3
done
~~~

`java -version` và `javac -version` hiển thị thông tin tùy bản JDK, không thuộc stdout cố định.

## 3. Vì sao `while` có thể lặp 0 lần?

~~~java
int available = 0;
while (available > 0) {
    System.out.println("processing");
    available--;
}
System.out.println("finished");
~~~

Điều kiện `available > 0` là false ngay tại lần kiểm tra đầu tiên. Vì vậy **không in `processing`**, chỉ in `finished`. Không có “một lượt đầu tiên bắt buộc” trong `while`.

Nếu yêu cầu nghiệp vụ là *thực hiện thân ít nhất một lần rồi mới kiểm tra*, có thể xem xét `do ... while`:

~~~java
int n = 0;
do {
    System.out.println("run once");
} while (n > 0);
~~~

Đoạn này in `run once` một lần dù điều kiện false. Đây là khác biệt về **thời điểm kiểm tra**, không phải tên hai cú pháp tương đương.

| Cấu trúc | Thời điểm kiểm tra | Số lượt ít nhất |
| --- | --- | ---: |
| `while (condition) { ... }` | Trước từng lượt, kể cả lượt đầu | 0 |
| `do { ... } while (condition);` | Sau từng lượt | 1 |
| `for (init; condition; update) { ... }` | Kiểm tra trước từng lượt sau init | 0 |

## 4. Điều kiện được đánh giá lại, không phải chỉ một lần

Trong `precheckTrace()`, phương thức `check(n)` in giá trị khi **được gọi**:

~~~text
check=0
body=0
check=1
body=1
check=2
after=2
~~~

Dòng `check=2` xuất hiện nhưng **không có `body=2`**: điều kiện đã false và vòng lặp dừng ngay.

Nếu biểu thức điều kiện đọc biến hoặc gọi phương thức, giá trị có thể thay đổi qua mỗi lần đánh giá. Vì vậy hãy tránh đặt **tác dụng phụ khó quan sát** trong điều kiện; nếu buộc phải dùng, làm rõ thứ tự và điểm dừng.

Cũng không nên lẫn `while (flag = true)` với `while (flag == true)`: nếu `flag` có kiểu `boolean`, **phép gán `=` hợp lệ** và làm `flag` luôn true, dễ tạo vòng lặp vô hạn. Thường chỉ cần `while (flag)` khi muốn kiểm tra cờ.

## 5. Cần có cơ chế tiến triển và điểm dừng

Ví dụ lỗi:

~~~java
int n = 1;
// while (n <= 3) {
//     System.out.println(n);
//     // Quên n++: điều kiện cứ đúng mãi nếu không có can thiệp.
// }
~~~

Một vòng `while` hợp lý thường cần **biến điều khiển thay đổi**, dữ liệu đầu vào được tiêu thụ hoặc một lệnh thoát được bảo đảm xảy ra theo giả định nghiệp vụ.

Ví dụ an toàn theo kích thước mảng:

~~~java
String[] items = {"A", "B", "C"};
int index = 0;
while (index < items.length) {
    System.out.println(items[index]);
    index++;
}
~~~

Biến `index` tăng từ 0 tới `items.length`; ngay trước khi truy cập mảng, điều kiện xác nhận chỉ số nằm trong miền hợp lệ. Đừng sửa mảng/dữ liệu ngoài theo cách khiến giả định dừng không còn đúng.

**Cẩn thận `continue`:** nó bỏ phần còn lại của thân và quay về **kiểm tra điều kiện**. Nếu lệnh tăng biến nằm sau `continue`, vòng lặp có thể không tiến triển:

~~~java
int n = 0;
// while (n < 5) {
//     if (n == 0) continue; // Sai: n vẫn bằng 0.
//     n++;
// }
~~~

Trong `skipEvenNumbers()`, lệnh `n++` được đặt **trước** `continue` nên vòng lặp vẫn kết thúc.

## 6. `break`, `continue`, `return` và ngoại lệ

| Trường hợp | Tác dụng |
| --- | --- |
| Kết thúc thân bình thường | Quay lại đánh giá điều kiện `while` |
| `continue;` | Bỏ các lệnh còn lại của lượt hiện tại, quay về kiểm tra điều kiện của vòng lặp |
| `break;` | Thoát vòng lặp gần nhất, đi tới câu lệnh sau vòng |
| `return;` / `return value;` | Thoát **phương thức** hiện tại |
| `throw ...;` | Ném ngoại lệ, không tiếp tục luồng bình thường |

Dùng `while (true)` khi **chủ ý** điều khiển dừng bằng `break`/`return` hoặc ngoại lệ. Trong demo, điều kiện luôn true nhưng khi `attempts == 3`, `break` khiến vòng lặp kết thúc.

Với vòng lặp đọc dữ liệu cho tới ký hiệu kết thúc (*sentinel*) như `"stop"`, `break` giúp dừng ngay khi gặp ký hiệu. Trong ví dụ, `"99"` đứng sau `"stop"` **không được xử lý**, nên tổng chỉ là 2 + 4 = 6.

## 7. Tránh các lỗi phổ biến

| Nhầm lẫn | Điều đúng |
| --- | --- |
| “Thân `while` chạy rồi mới xét điều kiện.” | `while` **kiểm tra trước**, có thể chạy 0 lần |
| “Điều kiện chỉ đánh giá một lần.” | Đánh giá lại trước **mỗi lượt** |
| “`while (1)` giống C.” | Java yêu cầu điều kiện kiểu `boolean` |
| “`continue` đi thẳng tới cuối vòng mà không kiểm tra lại điều kiện.” | `while` vẫn đánh giá lại điều kiện |
| “`break` thoát luôn phương thức.” | `break` chỉ thoát vòng lặp (hoặc switch) gần nhất |
| “Thân không cần thay đổi gì vì điều kiện tự cập nhật.” | Cần cơ chế tiến triển/thoát phù hợp |
| “`while (flag = true)` chỉ kiểm tra flag.” | Đây là **gán true**, có thể gây vòng vô hạn |
| “Thêm `;` sau `while (condition)` vô hại.” | Tạo **thân rỗng**, khối sau đó có thể không thuộc vòng lặp |

Nếu điều kiện là một wrapper `Boolean` có giá trị `null`, việc unbox để đánh giá `while` sẽ gây `NullPointerException`. Với đầu vào có thể null, kiểm tra rõ ràng trước khi lặp hoặc dùng điều kiện an toàn như `Boolean.TRUE.equals(flag)`.

## 8. Bài tập và checklist

1. `int n = 5; while (n < 5) { n++; }` lặp mấy lượt? **0 lượt**.
2. `int n = 0; while (n < 2) { n++; }` điều kiện được đánh giá bao nhiêu lần nếu không có thoát bất thường? **3 lần** (đúng hai lần, sai lần cuối).
3. Vì sao `continue` trước `n++` có thể gây vô hạn? **Biến điều khiển không thay đổi**.
4. `while (true) { break; }` có thoát được không? **Có**, thoát ngay tại `break`.
5. Khi nào cân nhắc `do ... while`? **Khi thân phải chạy ít nhất một lần**.

**Tự kiểm:** Tôi có xác định rõ điều kiện kiểu `boolean`, thời điểm điều kiện được đánh giá, cơ chế tiến triển, đường thoát và hành vi khi điều kiện false ngay từ đầu hay chưa?

**Kết luận:** `while` là **vòng lặp kiểm tra trước**. Mỗi lượt đều phải qua điều kiện; thân có thể không chạy lần nào. Viết vòng lặp an toàn bằng cách giữ điều kiện rõ nghĩa, bảo đảm có tiến triển hoặc điểm dừng, và hiểu chính xác `break`/`continue`.
