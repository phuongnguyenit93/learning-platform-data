# Nhận diện câu lệnh không thể tới và ảnh hưởng tới biên dịch — Java 17+

## 1. `Unreachable statement` là gì?

Java kiểm tra **tính có thể tới được** (*reachability*) của các câu lệnh khi biên dịch. Nếu quy tắc ngôn ngữ chứng minh rằng không có đường điều khiển hợp lệ nào dẫn đến một câu lệnh, `javac` báo lỗi **`unreachable statement`** và không tạo được chương trình hợp lệ.

Ví dụ sai:

~~~java
static int answer() {
    return 42;
    // System.out.println("after return");
    // Nếu bỏ chú thích ở dòng trên: lỗi unreachable statement.
}
~~~

Sau `return 42;`, phương thức đã kết thúc. Câu lệnh ngay sau nó trong cùng khối không có cơ hội được thực thi.

**Phân biệt hai tình huống:**

- **Không thể tới được theo quy tắc biên dịch:** lỗi *compile-time*, ví dụ câu lệnh đứng trực tiếp sau `return` vô điều kiện.
- **Có thể tới được về cú pháp nhưng thực tế không chạy với dữ liệu đang xét:** thường **không phải lỗi biên dịch**, ví dụ nhánh `if (false)` hoặc một điều kiện phụ thuộc dữ liệu luôn sai trong bài toán.

Đừng dựa chỉ vào quan sát “tôi chạy thử chưa thấy dòng này được in” để kết luận compiler sẽ báo unreachable.

## 2. Bảng nhận diện nhanh

| Mẫu mã | Câu lệnh phía sau có thể tới? | Kết quả |
|---|---|---|
| `return; statement;` cùng khối | Không | **Lỗi biên dịch** |
| `throw ex; statement;` cùng khối | Không | **Lỗi biên dịch** |
| `break; statement;` trong cùng nhánh vòng lặp | Không | **Lỗi biên dịch** |
| `continue; statement;` trong cùng nhánh vòng lặp | Không | **Lỗi biên dịch** |
| `while (true) { ... }` không có đường `break` thoát | Không, đối với câu lệnh tiếp sau vòng | **Lỗi biên dịch** |
| `for (;;) { ... }` không có `break` thoát | Không, đối với câu lệnh tiếp sau vòng | **Lỗi biên dịch** |
| `while (false) { statement; }` | Body không thể tới | **Lỗi biên dịch** |
| `if (false) { statement; }` | Quy tắc `if` cho phép dạng này | **Hợp lệ**, nhánh không chạy |
| `if (flag) return; statement;` | Có đường đi `flag == false` | **Hợp lệ** |
| `while (true) { if (stop) break; }` rồi một câu lệnh | Có đường `break` thoát | **Có thể hợp lệ** |
| `do { statement; } while (false);` | Body chạy một lượt | **Hợp lệ** |

Các dòng dạng mẫu rút gọn không phải những chương trình tự chạy; phần cuối bài có chương trình Java 17+ độc lập với stdout cụ thể.

## 3. Sau `return`: không còn đường đi trong phương thức

~~~java
static String getLabel() {
    return "READY";
    // System.out.println("unreachable"); // Không được bật dòng này.
}
~~~

`return` kết thúc phương thức ngay; mọi câu lệnh đứng trực tiếp phía sau trong cùng khối đều không thể tới.

**Nhưng `return` có điều kiện thì khác:**

~~~java
static String status(boolean active) {
    if (active) {
        return "ACTIVE";
    }
    return "INACTIVE"; // Hợp lệ khi active == false.
}
~~~

`status(true)` trả `"ACTIVE"`, `status(false)` trả `"INACTIVE"`; câu `return` cuối vẫn có đường đi tới.

**Nếu cả hai nhánh đều kết thúc phương thức:**

~~~java
// Ví dụ không biên dịch nếu bật dòng cuối:
static int choose(boolean flag) {
    if (flag) {
        return 1;
    } else {
        return 2;
    }
    // System.out.println("after if/else"); // Unreachable.
}
~~~

Khi phân tích, hãy xem **tất cả đường đi** của các nhánh, không chỉ nhánh được dùng ở một lần gọi cụ thể.

## 4. Sau `throw`: luồng bình thường không tiếp tục

~~~java
static int requirePositive(int n) {
    if (n <= 0) {
        throw new IllegalArgumentException("n must be positive");
        // System.out.println("never"); // Unreachable.
    }
    return n;
}
~~~

Một `throw` kết thúc đường điều khiển thông thường tại vị trí đó. Exception có thể được **bắt ở caller hoặc một `catch` bao ngoài thích hợp**, nhưng Java không quay lại thực hiện câu lệnh đứng ngay sau `throw` trong cùng block.

Một ví dụ bất hợp lệ nếu viết liền:

~~~java
// throw new IllegalStateException("fail");
// System.out.println("after throw"); // Unreachable.
~~~

Không nhầm lỗi unreachable với thông báo về **checked exception**: đó là kiểm tra khác, liên quan đến khai báo và xử lý ngoại lệ.

## 5. Sau `break` và `continue` trong cùng khối

`break` rời vòng lặp hoặc `switch` phù hợp; `continue` chuyển sang lượt tiếp theo của vòng lặp.

~~~java
for (int i = 0; i < 3; i++) {
    if (i == 1) {
        continue;
        // System.out.println("after continue"); // Unreachable.
    }
    System.out.println("i=" + i);
}
~~~

**Exact stdout:**

~~~text
i=0
i=2
~~~

Với `break`:

~~~java
for (int i = 0; i < 3; i++) {
    if (i == 1) {
        break;
        // System.out.println("after break"); // Unreachable.
    }
    System.out.println("visit=" + i);
}
System.out.println("loop finished");
~~~

**Exact stdout:**

~~~text
visit=0
loop finished
~~~

Quan trọng: **câu lệnh trực tiếp sau `break`/`continue` trong cùng nhánh** mới là lỗi. Câu lệnh **sau toàn bộ vòng lặp** không nhất thiết unreachable: với `break`, luồng có thể đến được nó.

## 6. Vòng lặp vô hạn và khả năng hoàn thành bình thường

Một vòng `while (true)` hoặc `for (;;)` không có đường `break` rời vòng lặp **không thể hoàn thành bình thường** theo kiểm tra reachability của Java.

~~~java
// static void bad() {
//     while (true) {
//         System.out.println("repeat");
//     }
//     System.out.println("after loop"); // Lỗi unreachable statement.
// }
~~~

Dòng in sau vòng không thể được chạy theo đường thực thi bình thường. Nếu mục đích là lặp vô hạn có điều kiện thoát, hãy cung cấp một đường `break` hợp lệ:

~~~java
static int countTo(int limit) {
    int count = 0;
    while (true) {
        if (count >= limit) {
            break;
        }
        count++;
    }
    return count; // Hợp lệ: có đường break ra khỏi while.
}
~~~

Nếu `limit=3`, `countTo` trả 3.

**Lưu ý:** Sự tồn tại của một `break` **có thể tới được theo cú pháp**, nhắm đúng vòng lặp, mới có ý nghĩa cho luật hoàn thành bình thường. `break` đặt trong vòng lặp **khác** hoặc trong `switch` không đương nhiên chứng minh được vòng `while(true)` bao ngoài có thể kết thúc.

Vòng vô hạn là hợp lệ nếu không có câu lệnh theo sau cần tới; lỗi nằm ở phần mã bất khả đạt theo luật biên dịch, không phải ở bản thân `while(true)`.

## 7. Ngoại lệ quan trọng: `if (false)` khác `while (false)`

Java cố ý cho phép thân của `if` ngay cả khi điều kiện là **biểu thức hằng `false`**. Điều đó hỗ trợ các nhánh bật/tắt theo cấu hình khi biên dịch:

~~~java
if (false) {
    System.out.println("disabled");
}
System.out.println("after disabled branch");
~~~

**Exact stdout:**

~~~text
after disabled branch
~~~

Trái lại, thân của `while` với điều kiện là hằng `false` bị coi là không thể tới:

~~~java
// KHÔNG BIÊN DỊCH nếu bật đoạn này:
// while (false) {
//     System.out.println("unreachable body");
// }
~~~

`for` cơ bản có condition là hằng `false` cũng có vấn đề tương tự:

~~~java
// KHÔNG BIÊN DỊCH:
// for (int i = 0; false; i++) {
//     System.out.println(i);
// }
~~~

**Với `do-while`:**

~~~java
int count = 0;
do {
    count++;
} while (false);
System.out.println("count=" + count);
~~~

**Exact stdout:**

~~~text
count=1
~~~

Vì `do-while` thực thi thân **trước lần kiểm tra điều kiện đầu tiên**, phần thân vẫn reachable dù điều kiện là `false`.

**Chú ý:** `final boolean OFF = false;` là constant variable; `while (OFF)` cũng bị phân tích như điều kiện hằng false. Một biến boolean được đọc ở runtime (không phải constant expression) thường không bị suy luận theo cách này chỉ vì nó hiện chứa `false`.

## 8. Compile-time reachability không phải bộ giải mọi điều kiện logic

Ví dụ:

~~~java
static void check(int value) {
    if (value > 100 && value < 0) {
        System.out.println("impossible for int");
    }
    System.out.println("checked=" + value);
}
~~~

Điều kiện bên trong `if` không thể đúng với cùng một giá trị `int`, nhưng compiler Java 17 **không bắt buộc chứng minh mọi mâu thuẫn toán học** để cấm thân nhánh. Do vậy đây là code **biên dịch hợp lệ**, dù dòng `"impossible for int"` sẽ không xuất hiện.

Ngược lại, một lỗi unreachable sau `return` được quyết định từ cấu trúc điều khiển rõ ràng, không cần phân tích dữ liệu thực tế.

Ví dụ `if (flag) return;` vẫn có đường đi `flag == false`. Java không cấm câu lệnh theo sau chỉ vì trong một lần chạy bạn luôn truyền `true`.

**Quy tắc thực hành:** khác biệt giữa “không thể đạt **theo đặc tả reachability**” và “không thể xảy ra **theo yêu cầu nghiệp vụ**” cần được kiểm chứng riêng.

## 9. `finally` có thể chạy khi đang chuyển luồng

Với `try/finally`, câu lệnh trong `finally` thường vẫn chạy khi `try` thực hiện `return`, `break` hoặc `continue`:

~~~java
static int readValue() {
    try {
        System.out.println("inside try");
        return 5;
    } finally {
        System.out.println("inside finally");
    }
}
~~~

**Exact stdout nếu gọi `System.out.println("result=" + readValue());`:**

~~~text
inside try
inside finally
result=5
~~~

Vì vậy không được suy luận rằng “mọi code chạy sau khi biểu thức `return` được đánh giá đều unreachable”: `finally` thuộc luồng kết thúc của `try` và có quy tắc đặc biệt.

Tránh đặt một `return` hoặc `throw` mới vào `finally` một cách tùy tiện vì nó có thể **thay đổi kết quả hoặc che ngoại lệ ban đầu**.

## 10. Phân biệt unreachable với các lỗi compile-time khác

| Vấn đề | Ví dụ | Chẩn đoán / bản chất |
|---|---|---|
| Câu lệnh không thể tới | `return 1; println();` | `unreachable statement` |
| Biến chưa được gán chắc chắn | `int x; if (flag) x=1; println(x);` | `variable x might not have been initialized` |
| Thiếu đường trả giá trị | Phương thức trả `int` nhưng có nhánh đi hết không `return` | `missing return statement` |
| Điều kiện không là boolean | `if (1) { ... }` | Lỗi kiểu dữ liệu, không phải unreachable |
| Nhãn `break` sai đích | `break unknown;` | Lỗi giải quyết nhãn |
| Nhánh luôn sai theo nghiệp vụ | `if (n>100 && n<0)` | Vẫn có thể biên dịch, nhưng cần sửa logic |

Các lỗi này có thể cùng xuất hiện trong dự án, nhưng **không nên sửa bằng cùng một thủ thuật**. Lỗi reachability thường được xử lý bằng cách đặt lại trật tự câu lệnh hoặc sửa luồng thoát; lỗi definite assignment phải đảm bảo biến có giá trị trên mọi đường dùng biến.

## 11. Mẫu refactor khi gặp unreachable statement

**Sai — viết log sau `return`:**

~~~java
// static int compute(int x) {
//     return x * 2;
//     System.out.println("finished"); // Unreachable.
// }
~~~

**Đúng — log trước `return`:**

~~~java
static int compute(int x) {
    int result = x * 2;
    System.out.println("finished");
    return result;
}
~~~

**Sai — câu lệnh sau `continue` trong cùng block:**

~~~java
// if (skip) {
//     continue;
//     total++; // Unreachable.
// }
~~~

**Đúng — đặt xử lý ở nhánh không skip:**

~~~java
for (int i = 0; i < 4; i++) {
    if (i % 2 == 0) {
        continue;
    }
    System.out.println("process " + i);
}
~~~

**Exact stdout:**

~~~text
process 1
process 3
~~~

Nếu thật sự cần chạy bước cập nhật ở cả hai nhánh, hãy xem bước đó thuộc thân vòng, phần update của `for` hay `finally` theo mục tiêu. **Đừng xóa một dòng chỉ để compiler hết lỗi** khi nó chứa side effect nghiệp vụ quan trọng; hãy chuyển nó tới đường đi đúng.

## 12. Chương trình Java 17+ chạy độc lập

Lưu đúng tên **`ReachabilityDemo.java`**:

~~~java
public final class ReachabilityDemo {
    private ReachabilityDemo() {}

    static String branch(boolean active) {
        if (active) {
            return "ACTIVE";
        }
        return "INACTIVE";
    }

    static int firstPositive(int[] data) {
        for (int i = 0; i < data.length; i++) {
            if (data[i] > 0) {
                return i;
            }
        }
        return -1;
    }

    static int countTo(int limit) {
        int count = 0;
        while (true) {
            if (count >= limit) {
                break;
            }
            count++;
        }
        return count;
    }

    static int requirePositive(int n) {
        if (n <= 0) {
            throw new IllegalArgumentException("n must be positive");
        }
        return n;
    }

    static void testContinue() {
        for (int i = 0; i < 3; i++) {
            if (i == 1) {
                continue;
            }
            System.out.println("continue:visit=" + i);
        }
    }

    static void testBreak() {
        for (int i = 0; i < 3; i++) {
            if (i == 1) {
                break;
            }
            System.out.println("break:visit=" + i);
        }
        System.out.println("break:after loop");
    }

    static void constantIf() {
        if (false) {
            System.out.println("disabled");
        }
        System.out.println("after if(false)");
    }

    static void doOnce() {
        int count = 0;
        do {
            count++;
        } while (false);
        System.out.println("do-while count=" + count);
    }

    static void check(int value) {
        if (value > 100 && value < 0) {
            System.out.println("impossible for int");
        }
        System.out.println("checked=" + value);
    }

    static int withFinally() {
        try {
            System.out.println("inside try");
            return 5;
        } finally {
            System.out.println("inside finally");
        }
    }

    public static void main(String[] args) {
        System.out.println("branch true=" + branch(true));
        System.out.println("branch false=" + branch(false));
        System.out.println("first positive=" + firstPositive(new int[]{-2, 0, 7, 9}));
        System.out.println("first missing=" + firstPositive(new int[]{-2, 0}));
        System.out.println("countTo 3=" + countTo(3));

        try {
            requirePositive(0);
        } catch (IllegalArgumentException ex) {
            System.out.println("throw caught=" + ex.getMessage());
        }
        System.out.println("require 4=" + requirePositive(4));

        testContinue();
        testBreak();
        constantIf();
        doOnce();
        check(5);
        System.out.println("finally result=" + withFinally());
    }
}
~~~

**Yêu cầu:** JDK 17 trở lên, mở terminal trong thư mục chứa file. Chương trình chỉ dùng API chuẩn JDK; không có tính năng preview, Maven hay Gradle.

**Bash (Linux/macOS):**

~~~bash
javac --release 17 -encoding UTF-8 ReachabilityDemo.java
java -cp . ReachabilityDemo
~~~

**PowerShell (Windows):**

~~~powershell
javac --release 17 -encoding UTF-8 .\ReachabilityDemo.java
java -cp . ReachabilityDemo
~~~

### Exact expected stdout

~~~text
branch true=ACTIVE
branch false=INACTIVE
first positive=2
first missing=-1
countTo 3=3
throw caught=n must be positive
require 4=4
continue:visit=0
continue:visit=2
break:visit=0
break:after loop
after if(false)
do-while count=1
checked=5
inside try
inside finally
finally result=5
~~~

**Đọc kết quả:**

1. Hai nhánh của `branch` cho thấy `return` có điều kiện không làm mọi dòng sau `if` unreachable.
2. `firstPositive` có `return` sớm khi tìm thấy và đường `return -1` khi duyệt hết.
3. `countTo` có vòng `while(true)` nhưng vẫn hoàn thành bình thường nhờ `break`.
4. `requirePositive` ném exception ở đường lỗi và trả kết quả ở đường hợp lệ.
5. `continue` bỏ `i=1`, `break` dừng tại `i=1` rồi vẫn in được dòng sau vòng.
6. `if(false)` không thực thi nhánh nhưng chương trình vẫn biên dịch; `do-while(false)` chạy một lượt.
7. Điều kiện `value > 100 && value < 0` không thể đúng với `int`, nhưng compiler không nhất thiết cấm nhánh; chỉ dòng `checked=5` xuất hiện.
8. `finally` được thực hiện trước khi caller in kết quả trả về.

## 13. Bài tập và đáp án

### Bài A — câu lệnh nào không thể tới?

~~~java
static int f() {
    return 10;
    // System.out.println("X"); // Nếu bỏ comment?
}
~~~

**Đáp án:** `System.out.println("X")` là **unreachable statement**, gây lỗi biên dịch. Muốn ghi log hãy đặt nó **trước** `return`.

### Bài B — `if(false)` hay `while(false)`?

~~~java
if (false) {
    System.out.println("A");
}
// while (false) {
//     System.out.println("B");
// }
System.out.println("C");
~~~

**Đáp án:** ví dụ đang được bật biên dịch và in `C`. Nếu bỏ comment cho `while(false)`, compiler Java 17 báo unreachable ở **body của while**.

### Bài C — có `break` thì câu sau vòng có reachable không?

~~~java
int count = 0;
while (true) {
    if (count == 2) break;
    count++;
}
System.out.println(count);
~~~

**Đáp án:** reachable vì có đường `break`; stdout `2`.

### Bài D — `continue` trong nhánh

~~~java
for (int i = 0; i < 3; i++) {
    if (i == 1) {
        continue;
        // System.out.println("X");
    }
}
~~~

**Đáp án:** nếu bật dòng in `X`, nó unreachable; chuyển xử lý mong muốn lên **trước** `continue` hoặc sang nhánh phù hợp.

### Bài E — lỗi chưa khởi tạo có phải unreachable?

~~~java
// static void f(boolean flag) {
//     int x;
//     if (flag) x = 1;
//     System.out.println(x);
// }
~~~

**Đáp án:** không. Câu `println` vẫn có thể tới, nhưng `x` chưa chắc được gán trên đường `flag == false`. Đây là lỗi **definite assignment**, không phải lỗi reachability.

## 14. Checklist và kết luận

- [ ] Phân biệt **câu lệnh unreachable theo compiler** với code không chạy do dữ liệu thực tế.
- [ ] Nhận diện câu lệnh trực tiếp sau `return` hoặc `throw` vô điều kiện.
- [ ] Nhận diện câu lệnh trực tiếp sau `break`/`continue` trong cùng nhánh.
- [ ] Biết `while(true)`/`for(;;)` không có đường break làm mã theo sau unreachable.
- [ ] Hiểu đường `break` hợp lệ cho phép mã sau vòng có thể tới.
- [ ] Nhớ Java cho `if(false)` hợp lệ nhưng `while(false)` có body không hợp lệ.
- [ ] Hiểu `do ... while(false)` vẫn thực thi body một lượt.
- [ ] Không nhầm mâu thuẫn logic trong `if` với lỗi unreachable được compiler phát hiện.
- [ ] Biết `finally` có thể chạy trong quá trình `return` hoặc chuyển luồng khác.
- [ ] Phân biệt unreachable với `missing return` và `variable might not have been initialized`.
- [ ] Khi sửa mã, giữ nguyên ý nghĩa nghiệp vụ và đường đi của side effect.
- [ ] Chạy `ReachabilityDemo.java` bằng `javac`/`java` Java 17+, đối chiếu exact stdout.

**Kết luận:** Java 17 kiểm tra reachability bằng **các quy tắc tĩnh của luồng điều khiển**, không phải bằng thử chạy mọi dữ liệu có thể. Đặt mã trực tiếp sau một chuyển luồng vô điều kiện thường gây **lỗi biên dịch**, trong khi một nhánh không được thực thi ở runtime có thể vẫn hợp lệ (đặc biệt `if(false)`). Phân tích từng đường `return`, `throw`, `break`, `continue` và cơ chế dừng của vòng lặp giúp sửa lỗi **đúng luồng**, thay vì chỉ xóa thông báo từ compiler.