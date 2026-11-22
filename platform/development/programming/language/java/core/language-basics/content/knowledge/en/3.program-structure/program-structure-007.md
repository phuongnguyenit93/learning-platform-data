# Cách chương trình bắt đầu, gọi phương thức và kết thúc

## 1. Từ lệnh java đến phương thức main

Với **Java 17+** chạy ứng dụng ở chế độ class đã biên dịch, lệnh `java TenLop` chọn **lớp điểm vào**, khởi động JVM và gọi phương thức `main` phù hợp. Trước khi chạy thân `main`, JVM cần tải, liên kết và khởi tạo những lớp cần thiết. Các bộ khởi tạo `static` có thể in thông báo **trước** câu lệnh đầu tiên trong `main`.

Điểm vào thông dụng trên Java 17:

~~~java
public static void main(String[] args) {
    // Chương trình bắt đầu xử lý từ đây
}
~~~

Một lần chạy đơn giản diễn ra theo thứ tự: JVM khởi tạo lớp → gọi `main` → `main` gọi các method → các method trả về → `main` hoàn tất. Nếu có ngoại lệ hoặc các luồng đang chạy, đường đi có thể khác.

~~~mermaid
flowchart TD
    A["java FlowDemo"] --> B["Khởi tạo lớp cần thiết"]
    B --> C["main(String[] args)"]
    C --> D["Gọi phương thức"]
    D --> E{"Phương thức kết thúc?"}
    E -->|"return"| F["Quay lại bên gọi"]
    E -->|"throw"| G["Tìm catch trên chuỗi lời gọi"]
    F --> H["main tiếp tục"]
    G --> H
    G --> I["Không được xử lý: luồng kết thúc bất thường"]
    H --> J["main hoàn tất"]
    J --> K["JVM kiểm tra các luồng non-daemon còn sống"]
    I --> K
~~~

Sơ đồ mô tả luồng khái quát, không khẳng định mọi lỗi đều được bắt hoặc mọi tiến trình JVM đều kết thúc ngay sau `main`.

## 2. Chương trình thực hành có đầu ra dự đoán được

Tạo tệp đúng tên **`FlowDemo.java`**:

~~~java
public final class FlowDemo {
    static {
        System.out.println("0. Khoi tao lop");
    }

    private FlowDemo() {}

    static int twice(int number) {
        System.out.println("3. Vao twice(" + number + ")");
        if (number < 0) {
            throw new IllegalArgumentException("number must be >= 0");
        }
        int value = Math.multiplyExact(number, 2);
        System.out.println("4. Tra ve " + value);
        return value;
    }

    static void display(int result) {
        System.out.println("6. Ket qua: " + result);
    }

    public static void main(String[] args) {
        System.out.println("1. Bat dau main");

        int input = args.length == 0 ? 3 : Integer.parseInt(args[0]);
        System.out.println("2. Input: " + input);

        int answer = twice(input);
        System.out.println("5. Quay lai main");

        display(answer);
        System.out.println("7. Het main");
    }
}
~~~

Tại thư mục chứa file, kiểm tra JDK rồi biên dịch/chạy.

**Bash (Linux/macOS):**

~~~bash
java -version
javac -version
javac --release 17 -encoding UTF-8 FlowDemo.java
java -cp . FlowDemo
java -cp . FlowDemo 5
~~~

**PowerShell (Windows):**

~~~powershell
java -version
javac -version
javac --release 17 -encoding UTF-8 .\FlowDemo.java
java -cp . FlowDemo
java -cp . FlowDemo 5
~~~

**Đầu ra lần không có đối số:**

~~~text
0. Khoi tao lop
1. Bat dau main
2. Input: 3
3. Vao twice(3)
4. Tra ve 6
5. Quay lai main
6. Ket qua: 6
7. Het main
~~~

**Đầu ra khi truyền `5`:**

~~~text
0. Khoi tao lop
1. Bat dau main
2. Input: 5
3. Vao twice(5)
4. Tra ve 10
5. Quay lai main
6. Ket qua: 10
7. Het main
~~~

Mỗi lệnh `java` trong ví dụ khởi động một JVM mới nên phần `static` in dòng `0` trong **mỗi lần chạy**.


## 3. Đối số của `main` tham gia luồng thực thi thế nào?

Với `java -cp . FlowDemo 5`, launcher chọn lớp `FlowDemo` và truyền chuỗi `"5"` vào `args[0]`. Phương thức `main` dùng `Integer.parseInt(args[0])` để chuyển chuỗi thành `int` trước khi gọi `twice`. Nếu không có đối số, biểu thức `args.length == 0 ? 3 : ...` chọn số mặc định `3`.

Trên Java 17, điểm vào truyền thống là `public static void main(String[] args)`: launcher gọi phương thức `static` đó mà không tạo đối tượng; `args` là mảng các chuỗi đối số ứng dụng. Phân tích từng thành phần chữ ký và quy tắc kiểm tra `args.length` nằm ở bài **Vai trò của public static void main(String[] args)**. Tại đây, hãy quan sát **thời điểm** chuyển dữ liệu: truyền `abc` khiến `Integer.parseInt` ném `NumberFormatException` ngay trong `main`, trước cả khi `twice` được gọi.

Lệnh `java -cp . FlowDemo.class` không hợp lệ trong class mode; launcher nhận tên lớp `FlowDemo`. Nếu lớp nằm trong package, cần tên lớp đầy đủ và classpath root phù hợp, chẳng hạn `java -cp out demo.Entry`.

## 4. Cơ chế gọi method: ai chạy trước và ai nhận kết quả?

Trong ví dụ `FlowDemo`, `main` gặp biểu thức:

~~~java
int answer = twice(input);
~~~

Lúc đó:

1. Java đánh giá đối số `input` rồi thực hiện lời gọi `twice`.
2. Thân `twice` chạy từ đầu cho tới `return` hoặc khi ném exception.
3. `return value;` làm lời gọi `twice` **hoàn tất bình thường** và chuyển giá trị `int` về biểu thức ở bên gọi.
4. `main` gán giá trị đó vào `answer` rồi mới in dòng `5`.
5. `main` gọi `display(answer)`. Vì `display` trả `void`, nó không gửi lại một giá trị có thể gán.
6. Khi `display` kết thúc, `main` chạy tiếp dòng `7`.

| Dòng in | Method đang hoạt động | Vì sao xuất hiện lúc đó? |
|---|---|---|
| 0 | Bộ khởi tạo static | JVM khởi tạo lớp trước khi gọi main |
| 1, 2 | `main` | Các lệnh đầu trong main |
| 3, 4 | `twice` | `main` đã gọi twice và đang chờ kết quả |
| 5 | `main` | twice đã return |
| 6 | `display` | main gọi display |
| 7 | `main` | display hoàn tất, main tiếp tục |

**Khai báo một method phía trên `main` trong file không khiến nó chạy trước `main`.** Method chạy vì có lời gọi, không vì vị trí được viết trong source.

### return chỉ thoát phương thức hiện tại

~~~java
static void printIfPositive(int value) {
    if (value <= 0) {
        return;
    }
    System.out.println(value);
}

// Đặt trong một main:
printIfPositive(0);
System.out.println("main van tiep tuc");
~~~

Kết quả chỉ là `main van tiep tuc`. `return;` ở `printIfPositive` **không** kết thúc `main`, càng không phải lệnh tắt JVM.

## 5. Call stack: đường đi xuống và quay trở lại

Mỗi luồng Java có **call stack** gồm các frame của những lời gọi method đang thực thi. Khi gọi method mới, ngữ cảnh của bên gọi được giữ lại để có thể tiếp tục sau khi method con trả về.

~~~text
Khi main đang chạy:           Khi main gọi twice:
+-----------------------+     +-----------------------+
| main(args)            |     | twice(number=3)       |  <-- đang chạy
+-----------------------+     +-----------------------+
                              | main(args)            |
                              +-----------------------+
Sau return: chỉ còn main tiếp tục tại câu lệnh sau lời gọi.
~~~

Đây là mô hình giải thích, không phải sơ đồ địa chỉ bộ nhớ thực tế của mọi JVM.

Thử thêm chương trình **`CallChain.java`**:

~~~java
public class CallChain {
    static int inner(int x) {
        System.out.println("inner");
        return x * 2;
    }

    static int middle(int x) {
        System.out.println("middle");
        return inner(x) + 1;
    }

    static void outer() {
        System.out.println("outer");
        int value = middle(3);
        System.out.println("value = " + value);
    }

    public static void main(String[] args) {
        System.out.println("main starts");
        outer();
        System.out.println("main ends");
    }
}
~~~

Chạy:

~~~bash
javac --release 17 CallChain.java
java -cp . CallChain
~~~

Đầu ra:

~~~text
main starts
outer
middle
inner
value = 7
main ends
~~~

Thứ tự lời gọi đi xuống là `main → outer → middle → inner`. Kết quả đi lên là `inner` trả `6`, `middle` trả `7`, rồi `outer` in `7`. Vì vậy `main ends` chỉ xuất hiện sau khi `outer` kết thúc.

## 6. Tham số: Java luôn truyền theo giá trị

Khi gọi method, Java **sao chép giá trị đối số** vào tham số. Với primitive, đó là giá trị như `int`. Với đối tượng, đó là **giá trị tham chiếu**, nên cả bên gọi và bên được gọi có thể trỏ đến cùng object.

~~~java
static void change(int n, StringBuilder box) {
    n = 99;
    box.append("!");
    box = new StringBuilder("Khac");
}

// Trong main:
int count = 3;
StringBuilder text = new StringBuilder("Hi");
change(count, text);
System.out.println(count); // 3
System.out.println(text);  // Hi!
~~~

Gán `n = 99` không đổi biến `count` bên gọi. `box.append("!")` thay đổi **trạng thái object dùng chung**, nên `text` thấy `Hi!`. Gán lại `box` không làm `text` trỏ sang đối tượng mới.

Không diễn giải Java là “pass-by-reference” chỉ vì một object mutable có thể bị thay đổi qua tham số.

## 7. Ném exception khác với return

Trong `twice`, số âm sẽ bị từ chối:

~~~java
if (number < 0) {
    throw new IllegalArgumentException("number must be >= 0");
}
~~~

Thử:

~~~bash
java -cp . FlowDemo -1
~~~

Trước stack trace, chương trình in:

~~~text
0. Khoi tao lop
1. Bat dau main
2. Input: -1
3. Vao twice(-1)
~~~

Sau đó `IllegalArgumentException` lan từ `twice` lên `main` do không có `catch` phù hợp. Stack trace thường chứa thông tin dạng:

~~~text
Exception in thread "main" java.lang.IllegalArgumentException: number must be >= 0
    at FlowDemo.twice(FlowDemo.java:...)
    at FlowDemo.main(FlowDemo.java:...)
~~~

Số dòng trong dấu `...` tùy file. Các dòng `4` đến `7` không in vì lời gọi không hoàn tất theo đường bình thường.

Với:

~~~bash
java -cp . FlowDemo abc
~~~

`Integer.parseInt("abc")` ném `NumberFormatException` khi tính `input`, **trước** dòng `2` và trước lời gọi `twice`. Chỉ dòng `0`, `1` xuất hiện trước thông báo lỗi.

Để phục hồi từ một exception dự kiến, bên gọi có thể xử lý:

~~~java
try {
    int answer = twice(-1);
    System.out.println(answer);
} catch (IllegalArgumentException ex) {
    System.out.println("Input sai: " + ex.getMessage());
}
System.out.println("Tiep tuc");
~~~

Khi đặt snippet trong một method hợp lệ, nó in `3. Vao twice(-1)`, rồi `Input sai: number must be >= 0`, sau đó `Tiep tuc`. Câu lệnh `System.out.println(answer)` bên trong `try` không chạy vì exception đã chuyển luồng đến `catch`.

Exception chưa xử lý có thể làm **luồng main** kết thúc bất thường; điều đó không phải lời gọi `System.exit` và không bảo đảm không còn các luồng khác.

## 8. Khi nào một ứng dụng Java thật sự dừng?

Phân biệt ba tình huống:

| Trường hợp | Hệ quả |
|---|---|
| `main` chạy tới hết hoặc `return;` | Luồng main hoàn thành |
| `main` thoát vì exception chưa xử lý | Luồng main kết thúc bất thường; thường có stack trace |
| `System.exit(status)` | Yêu cầu JVM thực hiện trình tự shutdown với mã trạng thái |

Trong ứng dụng đơn luồng như `FlowDemo`, `main` kết thúc bình thường, JVM thường dừng với **exit code 0**. Nhưng nếu còn **luồng non-daemon** sống, JVM thông thường vẫn tiếp tục chạy sau khi `main` hoàn tất.

Thử **`ThreadExitDemo.java`**:

~~~java
public class ThreadExitDemo {
    public static void main(String[] args) {
        Thread worker = new Thread(() -> {
            try {
                Thread.sleep(200);
                System.out.println("worker finished");
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        });
        worker.start();
        System.out.println("main finished");
    }
}
~~~

Chạy:

~~~bash
javac --release 17 ThreadExitDemo.java
java -cp . ThreadExitDemo
~~~

Bạn sẽ thấy cả `main finished` và `worker finished`. Thứ tự in là kết quả của lịch chạy các luồng, không nên xem là hợp đồng cố định; JVM vẫn chờ worker non-daemon hoàn tất trước khi shutdown bình thường.

`System.exit(2)` yêu cầu dừng **cả JVM** với status 2 (thường quy ước khác 0 nghĩa là lỗi). Nó không tương đương `return;`, và **không bảo đảm các block `finally` của luồng đang bị dừng chạy như khi rời method bình thường**. Tránh gọi `System.exit` trong các method thư viện; để tầng khởi chạy quyết định cách báo lỗi và dừng ứng dụng.

## 9. finally trong đường return

Method có `return` trong `try` vẫn thực hiện `finally` trước khi trả quyền điều khiển về bên gọi, nếu JVM rời block theo cơ chế bình thường:

~~~java
static int compute() {
    try {
        System.out.println("A. try");
        return 10;
    } finally {
        System.out.println("B. finally");
    }
}

// Gọi trong main:
int value = compute();
System.out.println("C. value = " + value);
~~~

Kết quả:

~~~text
A. try
B. finally
C. value = 10
~~~

Không đặt `return` trong `finally` để tránh che mất exception hoặc thay đổi kết quả của `try`. Nếu quản lý tài nguyên như file/stream, dùng `try-with-resources` khi phù hợp thay vì trông chờ JVM sắp kết thúc.

## 10. Bảng chẩn đoán thường gặp

| Hiện tượng | Nguyên nhân có thể có | Bước kiểm tra |
|---|---|---|
| `Main method not found` | Class không có entry point theo Java 17 | Chữ ký `public static void main(String[] args)` |
| `Could not find or load main class` | Sai package, classpath hoặc tên class | Classpath root, file `.class`, tên đầy đủ |
| Không in dòng sau lời gọi method | `throw`, `return` sớm hoặc nhánh không chạy | Trace lời gọi và stack trace |
| `NumberFormatException` | `args[0]` không phải số nguyên hợp lệ | Xác thực và xử lý input |
| `ArithmeticException` tại `multiplyExact` | Kết quả nhân vượt miền `int` | Kiểm tra miền giá trị/kiểu dữ liệu |
| Chạy xong main mà terminal chưa trả dấu nhắc | Vẫn còn worker non-daemon hoặc tác vụ chờ | Quan sát trạng thái threads, blocking I/O |
| Dòng log không theo thứ tự đoán giữa hai threads | Lịch chạy không cố định | Đồng bộ khi cần thứ tự, đừng suy luận từ log ngẫu nhiên |

## 11. Bài tập với đáp án

### Bài A — lần theo lời gọi

~~~java
static int addOne(int x) {
    System.out.println("B");
    return x + 1;
}
// Trong main:
System.out.println("A");
int y = addOne(4);
System.out.println("C:" + y);
~~~

**Đáp án:**

~~~text
A
B
C:5
~~~

Vì bên gọi chỉ in `C:5` khi `addOne` đã hoàn thành và trả về `5`.

### Bài B — return có tắt JVM không?

Nếu `validate()` gặp `return;` nhưng `main` còn `System.out.println("done");` phía sau lời gọi, điều gì xảy ra?

**Đáp án:** `validate` kết thúc; `main` vẫn in `done` nếu không có exception hoặc đường rẽ khác ngăn cản.

### Bài C — dự đoán đầu ra khi nhập sai

Với `FlowDemo`, chạy:

~~~bash
java -cp . FlowDemo -1
~~~

**Đáp án:** chương trình in các dòng `0`, `1`, `2`, `3` rồi báo `IllegalArgumentException`; không in `4` đến `7`.

### Bài D — tràn số ở phương thức con

~~~bash
java -cp . FlowDemo 2147483647
~~~

**Đáp án:** `Math.multiplyExact` ném `ArithmeticException` do vượt miền `int`; không có giá trị trả về hợp lệ để `main` gán cho `answer`.

### Bài E — main đã hết nhưng worker còn chạy

Ứng dụng còn một thread non-daemon đang xử lý. JVM có buộc phải dừng ngay khi `main` return không?

**Đáp án:** Không. Kết thúc luồng main khác với kết thúc toàn bộ tiến trình JVM; bình thường JVM còn đợi worker non-daemon.

## 12. Checklist

- [ ] Biết chữ ký điểm vào `main` thông dụng trên Java 17.
- [ ] Chạy đúng lệnh `javac` và `java`, hiểu `args[0]`.
- [ ] Giải thích vì sao static initializer có thể chạy trước thân main.
- [ ] Theo dõi được `main → method → return → main`.
- [ ] Hiểu frame của call stack và truyền tham số theo giá trị.
- [ ] Phân biệt `return`, `throw` và `System.exit`.
- [ ] Biết đọc stack trace và vị trí phát sinh lỗi.
- [ ] Nhận diện được trường hợp `main` kết thúc nhưng JVM còn chạy.
- [ ] Hiểu `finally` trong đường `return` và rủi ro dừng JVM cưỡng bức.

**Kết luận:** Launcher chọn class có điểm vào; JVM khởi tạo lớp cần thiết rồi gọi `main`. Lời gọi method chuyển điều khiển vào thân phương thức, `return` đưa kết quả về caller, còn exception có thể đi theo đường khác. `main` kết thúc không đồng nghĩa JVM luôn dừng ngay: vòng đời tiến trình còn phụ thuộc các luồng non-daemon và cơ chế shutdown.