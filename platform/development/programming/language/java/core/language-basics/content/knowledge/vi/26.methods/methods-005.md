# `return` với giá trị và `return` trong phương thức `void` — Java 17+

## 1. Quy tắc cốt lõi

Trong Java, `return` **kết thúc lời gọi phương thức hiện tại** và chuyển điều khiển về nơi đã gọi. Việc có thể trả một giá trị hay không phụ thuộc **kiểu trả về trong khai báo phương thức**.

| Kiểu phương thức | Lệnh hợp lệ | Ý nghĩa |
|---|---|---|
| `int`, `boolean`, `String`… | `return expression;` | Tính biểu thức, trả giá trị phù hợp với kiểu khai báo và thoát phương thức |
| `void` | `return;` | Thoát sớm, **không trả giá trị** |
| `void` | Chạy hết thân mà không gặp `return` | Cũng kết thúc bình thường, không trả giá trị |

~~~java
static int square(int n) {
    return n * n;        // Giá trị int.
}

static void printIfPositive(int n) {
    if (n <= 0) return;  // Thoát sớm, không có biểu thức.
    System.out.println(n);
}
~~~

`square(4)` có giá trị `16`; `printIfPositive(4)` in `4` nhưng **không có giá trị để gán vào biến**. Trong cả hai trường hợp, `return` đều kết thúc lời gọi hiện tại.

## 2. `return expression;` trong phương thức không phải `void`

~~~java
static int larger(int a, int b) {
    if (a >= b) {
        return a;
    }
    return b;
}
~~~

Gọi `larger(3, 8)` trả `8`. Biểu thức sau `return` phải tạo giá trị **tương thích với kiểu trả về** của phương thức theo luật chuyển đổi của Java.

Các ví dụ khác:

~~~java
static boolean isAdult(int age) {
    return age >= 18;
}

static String status(boolean active) {
    return active ? "ACTIVE" : "INACTIVE";
}
~~~

**Đúng:** `return age >= 18;` vì biểu thức có kiểu `boolean`. **Sai:** trong phương thức khai báo `int`, viết `return "hello";` hoặc `return;` sẽ không biên dịch.

Với kiểu tham chiếu như `String`, `return null;` có thể hợp lệ về kiểu, nhưng caller cần xử lý null theo hợp đồng API. Với kiểu nguyên thủy như `int`, không thể `return null;`.

## 3. Phương thức trả giá trị phải xử lý đủ đường đi

~~~java
// SAI nếu bỏ chú thích: có đường flag == false không trả int.
// static int broken(boolean flag) {
//     if (flag) return 1;
// }
~~~

Compiler sẽ báo lỗi thiếu `return` khi một phương thức không phải `void` có thể **hoàn tất bình thường** mà chưa trả giá trị.

Sửa:

~~~java
static int choose(boolean flag) {
    if (flag) {
        return 1;
    }
    return 2;
}
~~~

Một đường đi có thể kết thúc bằng `throw` thay vì trả về:

~~~java
static int positiveOnly(int value) {
    if (value <= 0) {
        throw new IllegalArgumentException("must be positive");
    }
    return value;
}
~~~

**Không phải mọi dòng trong thân đều phải chứa `return`**; yêu cầu là các đường thực thi có thể kết thúc bình thường phải trả giá trị. Một nhánh `throw` kết thúc đột ngột và không cần giá trị trả về.

## 4. `return;` trong phương thức `void`: guard clause

`void` có nghĩa là phương thức không trả giá trị; `return;` hữu ích để **ngăn chạy phần còn lại** nếu đầu vào không phù hợp.

~~~java
static void announce(String message) {
    if (message == null || message.isBlank()) {
        System.out.println("skip empty");
        return;
    }
    System.out.println("announce:" + message);
}
~~~

Với `announce(null)`, chương trình in `skip empty` rồi thoát phương thức. Với `announce("Hi")`, điều kiện false nên chạy `announce:Hi`.

Lưu ý:

- `return;` hợp lệ trong phương thức `void`.
- `return 1;` **không hợp lệ** trong phương thức `void`.
- Không bắt buộc viết `return;` ở cuối phương thức `void`; Java tự kết thúc khi thân chạy hết.
- `void` không phải là một giá trị `null` hay số `0`; không viết `int x = announce("Hi");`.

Một lệnh `return` trong `main(String[] args)` (có kiểu `void`) cũng kết thúc `main` mà không trả giá trị.

## 5. `return` khác `break` và `continue`

Đặt lệnh trong một vòng lặp:

| Lệnh | Phạm vi tác động |
|---|---|
| `return value;` | Kết thúc **phương thức** hiện tại và trả giá trị |
| `return;` | Kết thúc phương thức `void` |
| `break;` | Thoát vòng lặp hoặc `switch` gần nhất phù hợp |
| `continue;` | Bỏ phần còn lại của lượt lặp gần nhất, chuyển sang lượt kế tiếp |

~~~java
static int firstEven(int[] numbers) {
    for (int number : numbers) {
        if (number % 2 == 0) {
            return number; // Thoát cả phương thức, không chỉ thoát vòng.
        }
    }
    return -1; // Không tìm thấy.
}
~~~

`firstEven(new int[]{3, 7, 10, 12})` trả `10` ngay khi gặp phần tử chẵn đầu tiên. Còn `firstEven(new int[]{3, 7})` trả `-1`.

Đừng thay `return number;` bằng `break;` nếu yêu cầu là **trả số tìm thấy**: `break` chỉ ra khỏi vòng và phương thức vẫn cần đường trả giá trị.

## 6. Thứ tự thực thi và câu lệnh không thể tới

~~~java
static int twice(int n) {
    System.out.println("inside twice");
    return n * 2;
}

System.out.println("before");
System.out.println("result=" + twice(4));
System.out.println("after");
~~~

**Exact stdout** khi ba câu gọi cuối nằm trong `main`:

~~~text
before
inside twice
result=8
after
~~~

Java đánh giá biểu thức sau `return`, kết thúc lời gọi, rồi caller tiếp tục. Lệnh nằm **trực tiếp sau một `return` vô điều kiện trong cùng block** là *unreachable statement* và gây lỗi biên dịch:

~~~java
// static int invalid() {
//     return 5;
//     System.out.println("never"); // Unreachable.
// }
~~~

`return` trong một nhánh `if` không tự làm mọi câu lệnh sau `if` trở nên unreachable: nhánh đó có thể không được chọn.

**`try/finally`:** Nếu `return` xảy ra trong `try`, `finally` vẫn được thực hiện trước khi việc trả về hoàn tất, theo quy tắc của Java. Tránh đặt `return` mới trong `finally` vì có thể làm thay đổi kết quả hoặc che ngoại lệ.

## 7. Java truyền và trả giá trị thế nào?

~~~java
static int changeLocal(int n) {
    n = 99;
    return n;
}

int x = 4;
int y = changeLocal(x);
System.out.println("x=" + x + ",y=" + y);
~~~

**Exact stdout:**

~~~text
x=4,y=99
~~~

Java truyền đối số **theo giá trị**; tham số `n` là bản sao của giá trị `x`, nên gán `n=99` không đổi `x`. `return n;` trả `99` để caller có thể lưu vào `y`.

Với object, giá trị truyền/nhận là **tham chiếu tới object**. Trả một tham chiếu không tự tạo bản sao object; nếu caller và callee cùng tham chiếu object mutable, thay đổi trạng thái object có thể quan sát được ở cả hai nơi. Điều này khác với gán lại biến tham số.

## 8. Chương trình Java 17 hoàn chỉnh

Tạo file **`ReturnValueVoidDemo.java`**:

~~~java
public final class ReturnValueVoidDemo {
    private ReturnValueVoidDemo() {}

    static int larger(int a, int b) {
        if (a >= b) return a;
        return b;
    }

    static String grade(int score) {
        if (score < 0 || score > 100) return "INVALID";
        if (score >= 90) return "A";
        if (score >= 70) return "B";
        return "C";
    }

    static void announce(String message) {
        if (message == null || message.isBlank()) {
            System.out.println("skip empty");
            return;
        }
        System.out.println("announce:" + message);
    }

    static int firstEven(int[] numbers) {
        for (int n : numbers) {
            if (n % 2 == 0) return n;
        }
        return -1;
    }

    static int twice(int n) {
        System.out.println("inside twice");
        return n * 2;
    }

    static int changeLocal(int n) {
        n = 99;
        return n;
    }

    static void finallyDemo() {
        try {
            System.out.println("inside try");
            return;
        } finally {
            System.out.println("inside finally");
        }
    }

    public static void main(String[] args) {
        System.out.println("larger=" + larger(3, 8));
        System.out.println("grade -1=" + grade(-1));
        System.out.println("grade 69=" + grade(69));
        System.out.println("grade 70=" + grade(70));
        System.out.println("grade 90=" + grade(90));
        System.out.println("grade 101=" + grade(101));

        announce(null);
        announce(" ");
        announce("Hi");

        System.out.println("firstEven=" + firstEven(new int[]{3, 7, 10, 12}));
        System.out.println("none=" + firstEven(new int[]{3, 7}));

        System.out.println("before twice");
        System.out.println("twice=" + twice(4));
        System.out.println("after twice");

        int x = 4;
        int y = changeLocal(x);
        System.out.println("x=" + x + ",y=" + y);

        finallyDemo();
        System.out.println("after finally");
    }
}
~~~

**Bash (Linux/macOS), JDK 17+:**

~~~bash
javac --release 17 -encoding UTF-8 ReturnValueVoidDemo.java
java -cp . ReturnValueVoidDemo
~~~

**PowerShell (Windows), JDK 17+:**

~~~powershell
javac --release 17 -encoding UTF-8 .\ReturnValueVoidDemo.java
java -cp . ReturnValueVoidDemo
~~~

### Exact expected stdout

~~~text
larger=8
grade -1=INVALID
grade 69=C
grade 70=B
grade 90=A
grade 101=INVALID
skip empty
skip empty
announce:Hi
firstEven=10
none=-1
before twice
inside twice
twice=8
after twice
x=4,y=99
inside try
inside finally
after finally
~~~

**Đối chiếu:** `larger` trả `int`; `grade` trả sớm theo các ngưỡng điểm; `announce` dùng `return;` để bỏ qua đầu vào rỗng; `firstEven` thoát cả phương thức từ trong vòng; `twice` tính xong trước khi caller in kết quả; `finallyDemo` vẫn chạy `finally` trước khi quay về `main`.

## 9. Lỗi thường gặp và bài tập

| Sai lầm | Vì sao sai? | Cách sửa |
|---|---|---|
| `return 1;` trong phương thức `void` | Không được trả giá trị | Dùng `return;` |
| `return;` trong phương thức `int` | Thiếu giá trị trả về | Dùng `return intExpression;` |
| `return "A";` trong phương thức `boolean` | Sai kiểu | Trả biểu thức boolean |
| Thiếu `return` ở một đường có thể kết thúc bình thường | `missing return statement` | Xử lý đủ đường đi |
| Nghĩ `return` chỉ thoát vòng | `return` thoát **phương thức** | Dùng `break` nếu chỉ muốn ra vòng |
| Đặt lệnh sau `return` vô điều kiện | `unreachable statement` | Đặt trước `return` hoặc sửa luồng |
| Gán kết quả của phương thức `void` | Không có giá trị | Gọi như một statement |
| Bỏ qua `finally` khi phân tích `return` | Thứ tự thực thi bị hiểu sai | Xét khối `finally` |

**Bài A.** Phương thức `static void stop() { return; }` hợp lệ không? **Có.** Nó thoát khỏi `void`, không trả giá trị.

**Bài B.** `static int sign(int n) { if (n > 0) return 1; }` có biên dịch không? **Không**, vì khi `n <= 0`, thân có thể kết thúc mà không trả `int`. Có thể thêm `return 0;` nếu hợp đồng quy định như vậy.

**Bài C.** Gọi `firstEven(new int[]{1, 3, 6, 8})` trả gì? **`6`**, vì `return` ngay tại số chẵn đầu tiên.

**Bài D.** Phương thức `void` không có `return;` có được không? **Có**, nếu chạy hết thân thì nó kết thúc bình thường.

## 10. Checklist và kết luận

- [ ] Phân biệt `return expression;` và `return;`.
- [ ] Biết `void` không trả giá trị và có thể kết thúc tự nhiên.
- [ ] Biết kiểu biểu thức trả về phải phù hợp với kiểu khai báo.
- [ ] Biết phương thức không `void` phải xử lý đủ đường hoàn thành bình thường.
- [ ] Hiểu `return` thoát **phương thức**, khác `break`/`continue`.
- [ ] Nhận diện `unreachable statement` sau `return` vô điều kiện.
- [ ] Hiểu giá trị trả về được caller sử dụng sau khi lời gọi kết thúc.
- [ ] Xét `finally` khi theo dõi đường `return`.
- [ ] Biên dịch và chạy `ReturnValueVoidDemo.java` với Java 17+, đối chiếu stdout.

**Kết luận:** `return expression;` cung cấp **một giá trị phù hợp kiểu trả về** và kết thúc phương thức; `return;` trong `void` **chỉ kết thúc sớm**, không sinh ra giá trị. Cả hai đều trả quyền điều khiển về nơi gọi, không chỉ thoát vòng lặp chứa chúng.