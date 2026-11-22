# Phạm vi tên trong khối, vòng lặp và phương thức — Java 17+

> **Java core — language-basics / Phạm vi và khởi tạo**  
> **Mục tiêu:** Xác định một tên biến/tham số có thể dùng ở đâu, vì sao tên biến trong vòng lặp không dùng được bên ngoài, lúc nào được dùng lại tên, và phân biệt **phạm vi tên (scope)** với **biến đã được gán giá trị (definite assignment)**.

## 1. Phạm vi tên (scope) là gì?

*Scope* là **vùng mã nguồn mà khai báo một tên có hiệu lực để tham chiếu tới thực thể đó**. Với biến cục bộ khai báo trong một khối lệnh, phạm vi thông thường kéo dài từ vị trí khai báo đến cuối khối chứa khai báo; không tự mở rộng ra ngoài dấu `}`.

~~~java
static void example() {
    int outer = 10;
    {
        int inner = 5;
        System.out.println(outer + inner); // 15: thấy cả hai tên.
    }
    System.out.println(outer); // 10.
    // System.out.println(inner); // LỖI BIÊN DỊCH: inner ngoài scope.
}
~~~

Dấu `{ ... }` có thể mở ra một khối trong phương thức, nhánh `if`, thân vòng lặp hoặc `try`. Quy tắc phạm vi giúp giới hạn chỗ có thể sử dụng tên; **không** có nghĩa đối tượng tham chiếu từ biến nhất thiết bị hủy ngay khi rời khối.

Ba câu hỏi hữu ích khi gặp lỗi `cannot find symbol`:

1. Tên đã được khai báo **trước vị trí đang dùng** và trong vùng nhìn thấy chưa?
2. Tên thuộc **biến cục bộ**, **tham số**, **biến vòng lặp** hay **trường của lớp/đối tượng**?
3. Nếu nhìn thấy tên, biến đã được **gán chắc chắn** trước lúc đọc chưa?

## 2. Khối lệnh `{ }`: biến ngoài nhìn vào được, biến trong không đi ra được

~~~java
int total = 0;

if (total == 0) {
    int adjustment = 3;
    total += adjustment; // Sửa được total của khối ngoài.
}
System.out.println(total); // 3.
// System.out.println(adjustment); // LỖI: adjustment hết scope.
~~~

Trong một khối, tên của biến cục bộ có phạm vi từ **khai báo của nó** về phía sau, không phải từ đầu khối:

~~~java
{
    // System.out.println(score); // LỖI: score chưa được khai báo.
    int score = 8;
    System.out.println(score); // Hợp lệ.
}
~~~

Hai khối **không chồng lấn** có thể khai báo lại cùng một tên:

~~~java
{
    int temp = 7;
    System.out.println(temp);
}
{
    int temp = 8; // Hợp lệ: temp trước đã hết scope.
    System.out.println(temp);
}
~~~

Nhưng Java **không cho khai báo lại biến cục bộ cùng tên trong phạm vi chồng lấn**, kể cả ở khối con:

~~~java
// KHÔNG BIÊN DỊCH:
// int count = 1;
// {
//     int count = 2; // Tên count ngoài vẫn đang có hiệu lực.
// }
~~~

Đây là khác biệt quan trọng so với việc *che khuất trường của đối tượng* bằng một biến cục bộ, được trình bày ở phần 6.

## 3. Biến trong vòng `for` thông thường

Biến khai báo trong phần **khởi tạo** của `for` có thể dùng tại phần điều kiện, phần cập nhật và thân vòng lặp; nó không có hiệu lực sau câu lệnh `for`:

~~~java
for (int i = 0; i < 3; i++) {
    System.out.println("i=" + i);
}
// System.out.println(i); // LỖI BIÊN DỊCH: i hết scope.
~~~

Có thể dùng lại tên biến trong hai vòng `for` độc lập, nối tiếp:

~~~java
for (int i = 0; i < 2; i++) {
    System.out.print(i); // 01.
}
for (int i = 2; i < 4; i++) {
    System.out.print(i); // 23.
}
~~~

Nhưng không thể khai báo `int i` ở một `for` nằm bên trong thân của `for` khác khi `i` của vòng ngoài vẫn còn scope:

~~~java
// KHÔNG BIÊN DỊCH:
// for (int i = 0; i < 2; i++) {
//     for (int i = 0; i < 3; i++) { } // i bị khai báo trùng.
// }
~~~

Để duyệt lồng nhau, dùng các tên khác như `row` và `column`. Nếu khai báo biến **trước** vòng lặp, nó thuộc phạm vi của khối bao ngoài, nên có thể đọc sau vòng lặp:

~~~java
int i = 0;
for (; i < 3; i++) {
    // Thân có thể dùng i.
}
System.out.println(i); // 3: i được khai báo bên ngoài for.
~~~

## 4. Enhanced `for` và biến khai báo trong thân vòng lặp

Với enhanced `for`, biến phần tử `element` được khai báo ở đầu vòng lặp và được dùng trong **thân** của vòng:

~~~java
for (String word : new String[] {"A", "B"}) {
    System.out.println(word);
}
// System.out.println(word); // LỖI: word không tồn tại ở đây.
~~~

Biểu thức nguồn ở bên phải dấu `:` **không dùng được biến phần tử mới khai báo** như một tên đã có sẵn. Mỗi lần lặp, biến này nhận giá trị phần tử tương ứng. Nếu nguồn chứa kiểu tham chiếu, giá trị nhận được là **bản sao tham chiếu**, không có tác dụng kéo dài scope ra ngoài vòng.

Trong thân `for`/`while`, biến mới khai báo chỉ dùng được trong thân hoặc khối con phù hợp:

~~~java
int sum = 0;
for (int n = 1; n <= 3; n++) {
    int part = n * 2;
    sum += part;
}
// System.out.println(part); // LỖI: part nằm trong thân vòng.
// System.out.println(n);    // LỖI: n thuộc phạm vi for.
System.out.println(sum); // 12: sum khai báo bên ngoài.
~~~

Nếu cần kết quả sau khi duyệt, hãy khai báo biến kết quả trong khối **bao ngoài**, như `sum`, và cập nhật nó trong vòng lặp. Tránh cố đọc một biến tạm chỉ được khai báo trong thân vòng.

## 5. `while`, `if` và tham số của phương thức

Một biến cục bộ tạo trong thân `while` có scope thuộc thân đó; biến điều khiển khai báo ở ngoài thì tiếp tục nhìn thấy sau vòng:

~~~java
int turn = 0;
while (turn < 2) {
    int step = turn + 10;
    System.out.println(step); // 10 rồi 11.
    turn++;
}
// System.out.println(step); // LỖI: ngoài scope.
System.out.println(turn); // 2.
~~~

Trong `if`/`else`, biến khai báo **trong nhánh** chỉ nhìn thấy ở nhánh đó. Nếu cần một kết quả chung, khai báo biến ở khối bao ngoài và gán trong các nhánh:

~~~java
static int choose(boolean flag) {
    int result;
    if (flag) {
        result = 1;
    } else {
        result = 2;
    }
    return result; // Cả hai nhánh đã gán.
}
~~~

Tham số hình thức của một phương thức có scope trong **thân phương thức đó**, gồm các khối lồng bên trong; chúng không xuất hiện trong phương thức gọi hoặc phương thức khác:

~~~java
static String format(int input) {
    String prefix = "P";
    return prefix + input;
}
// Ở phương thức khác, không thể dùng riêng tên input hoặc prefix.
~~~

Không được khai báo `int input` trong một khối lồng của chính `format` vì tên tham số `input` đang có hiệu lực. Các phương thức khác nhau có thể dùng cùng tên tham số mà không xung đột.

## 6. Trường của đối tượng và che khuất tên (*shadowing*)

Phạm vi một **field** không giống phạm vi local: trong phương thức instance, tham số hoặc biến cục bộ được phép trùng tên field. Khi ấy tên ngắn chọn biến gần hơn, còn `this.count` chỉ đúng field của đối tượng:

~~~java
class Counter {
    private int count = 100;
    void show() {
        int count = 3;
        System.out.println(count);      // 3: local
        System.out.println(this.count); // 100: instance field
    }
}
~~~

Với field `static`, viết `ClassName.field` để phân biệt với local cùng tên; trong phương thức `static` không có `this`. Hai khai báo **local-local** chồng phạm vi vẫn bị cấm, dù local trùng field là hợp lệ. Bài về *tham số/biến cục bộ che khuất trường* sẽ phân tích kỹ lỗi tự gán `value = value;` và cách sửa.

## 7. Scope khác với *definite assignment* và vòng đời dữ liệu

Có thể **nhìn thấy tên**, nhưng vẫn **chưa được phép đọc biến cục bộ** nếu Java không chứng minh được nó đã được gán giá trị:

~~~java
// KHÔNG BIÊN DỊCH:
// static int bad(boolean condition) {
//     int result;
//     if (condition) {
//         result = 1;
//     }
//     return result; // Có đường đi condition=false chưa gán.
// }
~~~

Trong ví dụ `choose` ở phần 5, hai nhánh `if` và `else` đều gán `result` trước lúc `return`, nên biên dịch thành công.

| Khái niệm | Câu hỏi cần trả lời |
| --- | --- |
| **Scope** | Ở vị trí này có thể tham chiếu đến **tên** đã khai báo không? |
| **Definite assignment** | Trước khi **đọc giá trị** biến cục bộ, mọi đường đến đây đã gán nó chưa? |
| **Lifetime / thời gian tồn tại** | Giá trị, vùng nhớ hoặc đối tượng liên quan còn tồn tại trong bao lâu? |

Mỗi lần gọi một phương thức thông thường tạo ngữ cảnh gọi riêng cho tham số và biến cục bộ. Nếu trả về tham chiếu tới một đối tượng, đối tượng đó **có thể tiếp tục tồn tại** sau khi tên biến cục bộ đi ra khỏi scope; thời điểm thu gom rác không được quyết định chỉ bằng dấu `}`.

`final` ngăn gán lại biến sau khi đã được gán theo quy tắc Java, nhưng **không mở rộng scope** và không tự làm đối tượng mutable trở thành bất biến. Các pattern variable của `instanceof`/`switch` có quy tắc phạm vi theo luồng điều khiển riêng; không nên áp dụng máy móc quy tắc khối đơn giản cho chúng.

## 8. Chương trình Java 17+ chạy độc lập

Tạo file **ScopeBlocksDemo.java**:

~~~java
public final class ScopeBlocksDemo {
    private static int shared = 50;
    private int count = 100;

    private static int increment(int number) {
        int result = number + 1;
        return result;
    }

    private static String format(int input) {
        String prefix = "P";
        return prefix + input;
    }

    private static int choose(boolean flag) {
        int result;
        if (flag) {
            result = 1;
        } else {
            result = 2;
        }
        return result;
    }

    private void demonstrate() {
        int count = 3;
        System.out.println("localCount=" + count);
        System.out.println("fieldCount=" + this.count);

        {
            int inside = 5;
            System.out.println("inside=" + inside);
        }

        {
            int temp = 7;
            System.out.println("siblingA=" + temp);
        }
        {
            int temp = 8;
            System.out.println("siblingB=" + temp);
        }

        for (int i = 0; i < 3; i++) {
            System.out.println("forIndex=" + i);
        }

        for (String item : new String[] {"A", "B"}) {
            System.out.println("item=" + item);
        }

        int total = 0;
        for (int i = 1; i <= 3; i++) {
            int part = i * 2;
            total += part;
        }
        System.out.println("total=" + total);

        int turn = 0;
        while (turn < 2) {
            int step = turn + 10;
            System.out.println("whileStep=" + step);
            turn++;
        }
        System.out.println("afterWhile=" + turn);
    }

    public static void main(String[] args) {
        ScopeBlocksDemo demo = new ScopeBlocksDemo();
        demo.demonstrate();

        System.out.println("methodOne=" + increment(5));
        System.out.println("methodTwo=" + increment(10));
        System.out.println("format=" + format(4));
        System.out.println("assignedTrue=" + choose(true));
        System.out.println("assignedFalse=" + choose(false));

        int shared = 9;
        System.out.println("localShared=" + shared);
        System.out.println("fieldShared=" + ScopeBlocksDemo.shared);
    }
}
~~~

Biên dịch và chạy trong thư mục chứa file (Bash, PowerShell hoặc Command Prompt):

~~~bash
javac -encoding UTF-8 ScopeBlocksDemo.java
java ScopeBlocksDemo
~~~

**Expected stdout chính xác:**

~~~text
localCount=3
fieldCount=100
inside=5
siblingA=7
siblingB=8
forIndex=0
forIndex=1
forIndex=2
item=A
item=B
total=12
whileStep=10
whileStep=11
afterWhile=2
methodOne=6
methodTwo=11
format=P4
assignedTrue=1
assignedFalse=2
localShared=9
fieldShared=50
~~~

Các dòng `siblingA`/`siblingB` chứng minh có thể dùng lại tên ở hai khối không chồng lấn; `forIndex` và `item` chỉ tồn tại trong vòng tương ứng; `total` có thể in sau vòng vì được khai báo bên ngoài; `localCount`/`fieldCount` chứng minh hiện tượng che khuất trường.

## 9. Checklist và bài tập

| Tình huống | Kiểm tra / cách giải quyết |
| --- | --- |
| `cannot find symbol` với tên vừa khai báo trong khối | Tên đã ra ngoài dấu `}` hoặc chưa tới vị trí khai báo? |
| Muốn dùng kết quả sau `for` | Khai báo biến kết quả ngoài `for` rồi cập nhật ở trong |
| Hai vòng `for (int i...)` nối tiếp | Hợp lệ nếu phạm vi hai biến `i` không chồng lấn |
| Vòng `for` lồng nhau cùng tên `i` | Không hợp lệ; đổi tên biến vòng trong |
| Khai báo local trùng local/parameter bên ngoài còn scope | Không hợp lệ trong vùng chồng lấn |
| Local trùng tên trường | Hợp lệ nhưng shadowing; cân nhắc `this.field` hoặc `ClassName.field` |
| Biến được khai báo nhưng chưa chắc được gán | Kiểm tra *definite assignment* trên mọi đường đi |
| Trả về đối tượng rồi rời khối | Đối tượng vẫn có thể tồn tại qua tham chiếu bên ngoài |

**Bài 1.** Khai báo `int sum = 0` ngoài vòng `for` và `int term` bên trong. Tính tổng bình phương từ 1 đến 4, sau đó in `sum`. Vì sao không in `term` sau vòng được?

**Bài 2.** Viết hai vòng `for (int i...)` nối tiếp, rồi thử khai báo một vòng cùng tên `i` lồng trong vòng trước. Dự đoán lỗi biên dịch.

**Bài 3.** Tạo hai khối liên tiếp cùng khai báo `String message`. Sau đó thử đặt chúng lồng nhau để thấy khi nào trùng tên bị cấm.

**Bài 4.** Viết phương thức nhận tham số `int count` và lớp có trường `count`. In giá trị tham số, trường và một local trong khối con; so sánh phạm vi các tên.

**Bài 5.** Viết hàm `int choose(boolean flag)` dùng biến `result` khai báo trước `if`. Thử bỏ nhánh `else` để thấy quy tắc *definite assignment*.

### Ghi nhớ

**Scope xác định tên dùng được ở đâu, không đồng nghĩa biến đã được gán hoặc đối tượng bị hủy khi hết khối.** Biến khai báo trong `{ }`/thân vòng lặp không dùng được ngoài vùng của nó; biến `for` khai báo ở phần khởi tạo cũng hết scope sau vòng. Tham số có hiệu lực trong thân phương thức. Các local cùng tên không được chồng phạm vi, nhưng local có thể che khuất field, truy cập field qua `this` hoặc tên lớp phù hợp.
