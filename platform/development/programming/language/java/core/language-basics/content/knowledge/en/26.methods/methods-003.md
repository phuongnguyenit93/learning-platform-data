# Phân biệt tham số hình thức và đối số — Java 17+

## 1. Hai khái niệm ở hai vị trí khác nhau

Khi **định nghĩa** một phương thức, các biến được khai báo trong danh sách giữa dấu ngoặc tròn là **tham số hình thức** (*formal parameters*). Khi **gọi** phương thức, các biểu thức cung cấp dữ liệu ở vị trí tương ứng là **đối số** (*arguments*).

~~~java
static int add(int left, int right) { // left, right: tham số hình thức.
    return left + right;
}

int result = add(2, 3);              // 2, 3: đối số của lời gọi.
~~~

- `left` và `right` được khai báo với kiểu `int` **trong định nghĩa phương thức**.
- `2` và `3` là hai **biểu thức đối số** tại lời gọi `add(2, 3)`.
- Khi gọi, giá trị của `2` được truyền cho tham số `left`; giá trị của `3` cho `right`.
- `return left + right;` tạo **kết quả trả về**, không phải một tham số hay đối số mới.

**Exact stdout**, nếu in kết quả bằng `System.out.println(result);`:

~~~text
5
~~~

Các thuật ngữ tiếng Việt có thể được diễn đạt là “tham số” và “đối số”; trong tài liệu này luôn dùng **tham số hình thức** cho biến ở phía khai báo, **đối số** cho giá trị/biểu thức ở phía lời gọi.

## 2. So sánh nhanh

| Đặc điểm | Tham số hình thức (*formal parameter*) | Đối số (*argument*) |
|---|---|---|
| Xuất hiện ở đâu? | Danh sách tham số của khai báo phương thức hoặc constructor | Danh sách biểu thức của lời gọi |
| Ví dụ | `int price` trong `cost(int price)` | `20` trong `cost(20)` |
| Có khai báo kiểu? | Có, chẳng hạn `String name` | Là biểu thức có kiểu suy ra/biết được; không phải khai báo tham số |
| Tên do ai đặt? | Người định nghĩa phương thức | Có thể truyền literal, biến hoặc biểu thức tùy ý |
| Phạm vi tồn tại | Trong thân phương thức theo quy tắc scope của Java | Biểu thức thuộc mã nơi lời gọi được viết |
| Có thể được phương thức sử dụng? | Có, bằng tên tham số | Giá trị đối số đã được chuyển đến tham số |
| Quan hệ | Nhận giá trị từ vị trí lời gọi tương ứng | Cung cấp giá trị để khởi tạo tham số tương ứng |

Ví dụ:

~~~java
static void welcome(String guest, int times) {
    for (int i = 0; i < times; i++) {
        System.out.println("Hello " + guest);
    }
}

String person = "Lan";
int count = 2;
welcome(person, count);
~~~

Ở lời gọi, **`person` và `count` là các biểu thức đối số**, không phải tham số hình thức. Chỉ **`guest` và `times`** trong khai báo `welcome` mới là tham số hình thức. Tên của biến phía caller **không cần trùng** tên tham số. Khi chạy đoạn minh họa trong một `main` phù hợp, stdout là:

~~~text
Hello Lan
Hello Lan
~~~

## 3. Ánh xạ vị trí, số lượng và kiểu

Với `static void display(String title, int score)`, lời gọi:

~~~java
display("Java", 90);
~~~

có ánh xạ:

~~~text
Lời gọi:        display("Java", 90)
                         │      │
                         ▼      ▼
Khai báo:        display(String title, int score)
                          title      score
~~~

Phương thức nhận từng giá trị theo **vị trí**. Không có cú pháp gọi theo tên kiểu `display(score = 90, title = "Java")` như một số ngôn ngữ khác; trong Java đây không phải *named arguments*.

Các lỗi phổ biến:

~~~java
// Định nghĩa minh họa:
static void display(String title, int score) { }

// display("Java");             // Thiếu đối số int.
// display("Java", 90, 100);    // Thừa đối số.
// display(90, "Java");         // Thứ tự/kiểu không khớp.
// display("Java", "90");       // String không tự là int.
~~~

Thông thường, số đối số phải phù hợp số tham số hình thức và kiểu đối số phải **tương thích với kiểu tham số theo quy tắc lời gọi Java**. Có những chuyển đổi hợp lệ như từ `int` sang `long`, boxing, hoặc cách xử lý đặc biệt của **varargs**; không nên kết luận các kiểu phải luôn khớp hoàn toàn theo đúng văn bản.

Java không tự lấy “giá trị mặc định của tham số bị thiếu” cho một phương thức bình thường. Khi cần cách gọi với ít dữ liệu hơn, có thể dùng overload hoặc thiết kế tham số thích hợp.

## 4. Đối số không nhất thiết là biến

Đối số là một **biểu thức**, nên nhiều dạng đều hợp lệ:

~~~java
static int square(int number) {
    return number * number;
}

int n = 4;
int a = square(3);          // Literal.
int b = square(n);          // Biến ở caller.
int c = square(n + 1);      // Biểu thức tính toán.
int d = square(square(2));  // Kết quả lời gọi khác.
~~~

Nếu in lần lượt `a`, `b`, `c`, `d`, stdout là:

~~~text
9
16
25
16
~~~

Trong **mọi lần gọi** `square(...)`, tham số hình thức vẫn là `int number`. Chỉ **giá trị đối số** tại từng lời gọi là khác nhau: `3`, `4`, `5`, `4`.

Có thể truyền giá trị trả về của phương thức khác làm đối số. Lời gọi lồng nhau cần được tính ra giá trị trước khi phương thức bên ngoài dùng nó.

## 5. Tham số nhận bản sao **giá trị của biểu thức đối số**

Java luôn **pass-by-value**. Trong lời gọi `f(expression)`, `expression` được tính ở caller, sau đó giá trị dùng để khởi tạo một biến tham số hình thức:

~~~java
static void increase(int number) { number++; }
int original = 5;
increase(original);
System.out.println(original); // 5.
~~~

`original` là một **biểu thức đối số**, `number` là **tham số**; vì là hai biến riêng nên gán lại `number` không đổi `original`.

Với kiểu tham chiếu, giá trị được sao chép là tham chiếu tới object. Hai biến có thể cùng trỏ tới **một mảng**, cho phép phương thức sửa nội dung của mảng chung:

~~~java
static void changeFirst(int[] values) { values[0] = 50; }
int[] data = {1, 2};
changeFirst(data);
System.out.println(java.util.Arrays.toString(data)); // [50, 2].
~~~

Gán lại `values = new int[]{99}` bên trong phương thức **không** làm biến `data` trỏ sang mảng mới. Bài này nhấn mạnh vị trí **khai báo tham số so với cung cấp đối số**; các bài về truyền tham trị và tham số mảng có ví dụ chuyên sâu về object alias, `null`, copy và mutation.


## 6. Tham số là biến cục bộ của lượt gọi

Các tham số có phạm vi trong thân phương thức. Mỗi lần phương thức được gọi, giá trị tham số được sử dụng trong **lần thực thi ấy**; không phải một biến toàn cục được dùng chung giữa mọi lời gọi.

~~~java
static int addBonus(int score) {
    score += 5;
    return score;
}

int first = addBonus(10);
int second = addBonus(30);
System.out.println(first);
System.out.println(second);
~~~

**Exact stdout:**

~~~text
15
35
~~~

Đổi tên tham số trong khai báo, ví dụ từ `score` thành `number`, không bắt caller đổi tên biến đối số. Ngược lại, caller có thể gọi `addBonus(first)`, `addBonus(10)` hoặc `addBonus(5 + 5)`.

Trong một phương thức, không thể khai báo một biến cục bộ khác **trùng tên tham số** khi tham số còn trong phạm vi:

~~~java
static void wrong(int n) {
    // int n = 3; // Lỗi biên dịch: trùng tên tham số.
}
~~~

Tham số có thể che tên một field của lớp; nếu đang ở instance method và cần truy cập field, dùng `this.score` để phân biệt với tham số `score`.

## 7. Tham số `final` và object mutable

Tham số hình thức có thể được khai báo `final`:

~~~java
static void print(final int number) {
    System.out.println(number);
    // number = 20; // Không hợp lệ: không được gán lại final parameter.
}
~~~

Với tham số mảng tham chiếu:

~~~java
static void update(final int[] values) {
    // values = new int[2]; // Không hợp lệ: gán lại tham số final.
    values[0] = 7;          // Hợp lệ: sửa object mảng được tham chiếu.
}
~~~

`final` áp dụng cho **biến tham số**, không tự tạo bản sao đối số và không khiến dữ liệu bên trong object trở thành bất biến. Khi không muốn method sửa mảng caller, có thể sao chép mảng bằng `Arrays.copyOf` rồi thao tác trên bản sao, hoặc không thực hiện mutation.

## 8. Thứ tự đánh giá biểu thức đối số

Trong Java, các biểu thức đối số được đánh giá theo **thứ tự từ trái sang phải**. Các giá trị đã được tính sẽ được truyền đến tham số tương ứng khi lời gọi được thực hiện.

~~~java
static int trace(String label, int value) {
    System.out.println("eval " + label + "=" + value);
    return value;
}

static int subtract(int left, int right) {
    return left - right;
}

int result = subtract(trace("left", 8), trace("right", 3));
System.out.println("result=" + result);
~~~

**Exact stdout:**

~~~text
eval left=8
eval right=3
result=5
~~~

Lời gọi `trace("left", 8)` được đánh giá trước `trace("right", 3)`. Nếu một biểu thức đối số ném ngoại lệ khiến lời gọi không thể tiếp tục, các biểu thức đối số phía sau có thể **không được đánh giá**.

Trong ví dụ số học đơn giản không tác dụng phụ, thứ tự dễ bị bỏ qua; khi đối số gọi method làm thay đổi trạng thái, việc hiểu thứ tự từ trái sang phải giúp tránh dự đoán sai kết quả.

## 9. Constructor và varargs vẫn dùng quy tắc tham số/đối số

Constructor cũng có **tham số hình thức** trong khai báo và nhận **đối số** khi dùng `new`:

~~~java
class Book {
    final String title;
    Book(String title) { this.title = title; }
}
Book book = new Book("Java"); // "Java" là đối số.
~~~

Một tham số `int... values` (*varargs*) có thể nhận nhiều phần tử mà caller cung cấp, nhưng trong thân phương thức, `values` chính là **một biến mảng `int[]`**:

~~~java
static int sum(int... values) {
    int result = 0;
    for (int n : values) result += n;
    return result;
}
System.out.println(sum());           // 0.
System.out.println(sum(2, 3));       // 5.
System.out.println(sum(new int[]{4})); // 4.
~~~

Đừng nhầm **số biểu thức đối số** ở `sum(2, 3)` với **số tham số hình thức**: khai báo chỉ có một `values`. Bài varargs/mảng sẽ xét chi tiết cách gọi, mảng có sẵn, `null` và overload.


## 10. Chương trình Java 17+ có thể chạy độc lập

Tạo file đúng tên **`ParametersArgumentsDemo.java`**:

~~~java
import java.util.Arrays;

public final class ParametersArgumentsDemo {
    private ParametersArgumentsDemo() {}

    static void welcome(String guest, int times) {
        for (int i = 0; i < times; i++) {
            System.out.println("Hello " + guest);
        }
    }

    static int add(int left, int right) {
        return left + right;
    }

    static int square(int number) {
        return number * number;
    }

    static void increasePrimitive(int value) {
        value++;
        System.out.println("inside primitive=" + value);
    }

    static void changeArray(int[] values) {
        values[0] += 10;
        System.out.println("inside array=" + Arrays.toString(values));
    }

    static void rebindArray(int[] values) {
        values = new int[]{99};
        System.out.println("inside rebound=" + Arrays.toString(values));
    }

    static void changeString(String text) {
        text = "B";
        System.out.println("inside string=" + text);
    }

    static int trace(String label, int value) {
        System.out.println("eval " + label + "=" + value);
        return value;
    }

    static int subtract(int left, int right) {
        return left - right;
    }

    static int sum(int... numbers) {
        int total = 0;
        for (int number : numbers) {
            total += number;
        }
        return total;
    }

    static void showVarargs(String tag, int... numbers) {
        System.out.println(tag + " values=" + Arrays.toString(numbers)
                + " sum=" + sum(numbers));
    }

    public static void main(String[] args) {
        int result = add(2, 3);
        System.out.println("add=" + result);

        String person = "Lan";
        int repeat = 2;
        welcome(person, repeat);

        System.out.println("literal square=" + square(3));
        System.out.println("expression square=" + square(2 + 2));
        System.out.println("nested square=" + square(square(2)));

        int original = 5;
        increasePrimitive(original);
        System.out.println("outside primitive=" + original);

        int[] data = {1, 2};
        changeArray(data);
        System.out.println("outside array=" + Arrays.toString(data));
        rebindArray(data);
        System.out.println("outside rebound=" + Arrays.toString(data));

        String originalText = "A";
        changeString(originalText);
        System.out.println("outside string=" + originalText);

        int difference = subtract(
                trace("left", 8), trace("right", 3));
        System.out.println("subtract=" + difference);

        showVarargs("empty");
        showVarargs("many", 3, 4);
        int[] existing = {4, 5};
        showVarargs("existing", existing);
    }
}
~~~

**Yêu cầu:** JDK 17 trở lên; không cần thư viện ngoài JDK hoặc tính năng preview.

**Bash (Linux/macOS):**

~~~bash
javac --release 17 -encoding UTF-8 ParametersArgumentsDemo.java
java -cp . ParametersArgumentsDemo
~~~

**PowerShell (Windows):**

~~~powershell
javac --release 17 -encoding UTF-8 .\ParametersArgumentsDemo.java
java -cp . ParametersArgumentsDemo
~~~

### Exact expected stdout

~~~text
add=5
Hello Lan
Hello Lan
literal square=9
expression square=16
nested square=16
inside primitive=6
outside primitive=5
inside array=[11, 2]
outside array=[11, 2]
inside rebound=[99]
outside rebound=[11, 2]
inside string=B
outside string=A
eval left=8
eval right=3
subtract=5
empty values=[] sum=0
many values=[3, 4] sum=7
existing values=[4, 5] sum=9
~~~

**Đọc theo thứ tự:** `add` ghép cặp hai đối số `2,3` với hai tham số `left,right`; `welcome` nhận đối số từ **biến** chứ không nhất thiết từ literal. Thay `value` nguyên thủy trong method không làm đổi caller, nhưng thay phần tử qua tham số `int[]` có thể đổi object mà caller giữ. Gán lại tham số `values` hoặc tham số `text` không đổi biến caller. Hai biểu thức `trace` cho thấy thứ tự đánh giá trái → phải. Varargs sử dụng một tham số `int[]` nhận các dạng đối số linh hoạt.

## 11. Các nhầm lẫn thường gặp

| Nhầm lẫn | Giải thích / cách sửa |
|---|---|
| Gọi biến `n` ở caller là “tham số hình thức” | Ở vị trí `f(n)`, `n` là **biểu thức đối số** |
| Phải đặt tên biến caller giống tham số | Không; ánh xạ theo **vị trí** và khả năng tương thích kiểu |
| Đối số luôn là literal | Có thể là biến, phép tính hoặc kết quả method |
| Đổi tham số `int` sẽ đổi biến caller | Java truyền giá trị nguyên thủy bằng bản sao |
| Java truyền mảng theo kiểu pass-by-reference | Java sao chép **giá trị tham chiếu**; mảng được tham chiếu có thể bị sửa |
| Gán `values = new int[...]` làm caller đổi tham chiếu | Chỉ gán lại biến tham số |
| `return` là một tham số khác | Return value là **kết quả** mà phương thức trả về |
| Quên số/thứ tự/kiểu đối số | Compiler cần lời gọi phù hợp khai báo/overload |
| Tưởng `int... numbers` khai báo nhiều tham số | Đó là **một** tham số varargs kiểu mảng trong thân |
| Cho rằng argument expressions luôn chạy đồng thời | Java đánh giá từ **trái sang phải** |

## 12. Bài tập và đáp án

**A — Chỉ ra vị trí:**

~~~java
static void printScore(String name, int score) {
    System.out.println(name + ":" + score);
}
printScore("An", 90);
~~~

**Đáp án:** `String name`, `int score` là hai **tham số hình thức**; `"An"`, `90` là hai **đối số**.

**B — Dùng biến caller:**

~~~java
int current = 10;
System.out.println(square(current + 1));
~~~

**Đáp án:** đối số là toàn bộ biểu thức `current + 1`, giá trị bằng 11; stdout là **`121`**.

**C — Dự đoán thay đổi biến:**

~~~java
static void setValue(int value) {
    value = 99;
}
int x = 7;
setValue(x);
System.out.println(x);
~~~

**Đáp án:** **`7`**, vì phép gán tác động tham số `value`, không tác động biến `x`.

**D — Dự đoán thay đổi mảng:**

~~~java
static void setFirst(int[] array) {
    array[0] = 99;
}
int[] a = {1};
setFirst(a);
System.out.println(a[0]);
~~~

**Đáp án:** **`99`**, vì phương thức sửa phần tử trên **đối tượng mảng được tham chiếu chung**.

**E — Với varargs:** `static int sum(int... numbers)` có bao nhiêu tham số hình thức?  
**Đáp án:** **một** (`numbers`), kiểu mảng `int[]` trong thân. Lời gọi `sum(1,2,3)` cung cấp ba phần tử được đóng gói cho tham số varargs.

## 13. Checklist và kết luận

- [ ] Phân biệt **khai báo tham số hình thức** và **biểu thức đối số** tại lời gọi.
- [ ] Hiểu đối số được ánh xạ theo vị trí vào tham số tương ứng.
- [ ] Biết kiểu/số lượng đối số phải phù hợp khai báo, trừ các quy tắc đặc biệt như varargs.
- [ ] Biết đối số có thể là literal, biến, biểu thức hoặc lời gọi khác.
- [ ] Hiểu Java luôn **pass-by-value**, kể cả khi truyền giá trị tham chiếu object/mảng.
- [ ] Phân biệt sửa object qua tham số và gán lại biến tham số.
- [ ] Hiểu tham số là biến trong phạm vi lần gọi, khác với biến caller.
- [ ] Nhận diện tham số `final` và giới hạn của nó.
- [ ] Biết Java đánh giá biểu thức đối số từ trái sang phải.
- [ ] Chạy `ParametersArgumentsDemo.java` với JDK 17+ và đối chiếu exact stdout.

**Kết luận:** **Tham số hình thức** là các biến được **khai báo** ở phía phương thức; **đối số** là các biểu thức cung cấp giá trị tại **lời gọi**. Java truyền giá trị đối số theo thứ tự vào tham số tương ứng. Với kiểu nguyên thủy, giá trị được sao chép; với mảng/object, giá trị **tham chiếu** được sao chép — đây là chìa khóa để hiểu khi nào phương thức có thể làm thay đổi dữ liệu mà caller quan sát.