# Dấu ngoặc nhọn, dấu chấm phẩy và khối lệnh trong Java

> **Java core — language-basics / Cấu trúc chương trình**  
> **Yêu cầu thực hành:** JDK 17 trở lên; ví dụ sử dụng cú pháp hợp lệ trong Java 17.  
> **Mục tiêu:** Phân biệt chính xác `{ }` (dấu ngoặc nhọn), `;` (dấu chấm phẩy) và *block* (khối lệnh); biết nơi phải có hoặc không nên đặt `;`; hiểu phạm vi biến và luồng thực thi khi dùng `if`, `for`, `while`, `do...while`. Tự biên dịch, chạy và dự đoán đầu ra của một chương trình Java tối thiểu.

## 1. Ba ý niệm nền tảng

Trong Java, **cú pháp** quyết định đoạn mã có tạo thành câu lệnh hợp lệ hay không; **cấu trúc khối** quyết định nhóm câu lệnh nào thuộc về một nhánh hoặc một vòng lặp.

| Ký hiệu/khái niệm | Vai trò chính | Ví dụ | Điều không có nghĩa |
| --- | --- | --- | --- |
| `{` và `}` | Đánh dấu giới hạn của thân lớp, thân phương thức, khối câu lệnh; cũng có các cách dùng khác như khởi tạo mảng | `if (ok) { run(); }` | Không phải mọi cặp `{ }` đều là một block statement |
| `;` | Kết thúc nhiều loại statement/declaration hoặc là dấu phân tách trong header `for` | `int age = 20;` | Không có nghĩa mọi dòng Java đều phải kết thúc bằng `;` |
| **Block** (khối lệnh) | Một statement chứa **không hoặc nhiều** statement/khai báo cục bộ nằm giữa `{ }` | `{ int x = 1; print(x); }` | Xuống dòng hoặc thụt lề không tự tạo block |

Cần nhớ hai quy tắc độc lập:

- Dấu `;` thường **kết thúc một câu lệnh**, còn `{ }` tạo ranh giới cấu trúc cho một nhóm câu lệnh.
- Trong Java, **thụt lề giúp đọc code**, nhưng dấu ngoặc nhọn và ngữ pháp — không phải số khoảng trắng — quyết định nhánh `if` hoặc vòng lặp chứa những gì.

~~~mermaid
flowchart TD
    A["Câu lệnh trong main"] --> B["for (...) { ... }"]
    B --> C["if (điều kiện) { ... }"]
    C --> D["total += number;"]
    B --> E["Sau vòng for"]
    E --> F["System.out.println(...);"]
~~~

## 2. Chương trình Java 17+ tối thiểu có đủ ba thành phần

Tạo file **BlockSyntaxDemo.java**; tên tệp trùng với `public class BlockSyntaxDemo`:

~~~java
public final class BlockSyntaxDemo {

    private static int sumEvenUpTo(int limit) {
        int total = 0;

        for (int number = 1; number <= limit; number++) {
            if (number % 2 == 0) {
                total += number;
            }
        }

        return total;
    }

    public static void main(String[] args) {
        int limit = 6;
        int result = sumEvenUpTo(limit);

        System.out.println("Tong so chan tu 1 den " + limit + ": " + result);

        if (result > 0) {
            System.out.println("Da tim thay so chan");
        } else {
            System.out.println("Khong co so chan");
        }
    }
}
~~~

**Chạy trong terminal ở thư mục chứa tệp:**

~~~bash
java -version
javac -version
javac -encoding UTF-8 BlockSyntaxDemo.java
java BlockSyntaxDemo
~~~

Hai lệnh đầu giúp xác minh công cụ, không phải đầu ra của chương trình. Nếu biên dịch thành công, `javac` thường không in gì và tạo `BlockSyntaxDemo.class`. Lệnh cuối in **đúng hai dòng**:

~~~text
Tong so chan tu 1 den 6: 12
Da tim thay so chan
~~~

Vì các số chẵn trong khoảng từ 1 đến 6 là 2, 4, 6 nên tổng là 12.

### Quan sát từng kiểu dấu trong ví dụ

| Đoạn mã | Tại sao viết như vậy? |
| --- | --- |
| `public final class BlockSyntaxDemo { ... }` | Dấu ngoặc nhọn bao quanh **thân lớp**; không có `;` bắt buộc sau dấu `}` cuối của khai báo lớp |
| `private static int sumEvenUpTo(int limit) { ... }` | Dấu ngoặc nhọn bao quanh **thân phương thức** |
| `int total = 0;` | Một câu lệnh khai báo biến cục bộ kết thúc bằng `;` |
| `for (...; ...; ...) { ... }` | Hai dấu `;` trong header phân tách ba phần của vòng `for` truyền thống |
| `if (number % 2 == 0) { ... }` | Block thuộc nhánh `if`; không thêm `;` giữa `)` và `{` |
| `total += number;` | Một expression statement thay đổi biến, kết thúc bằng `;` |
| `return total;` | Câu lệnh trả kết quả, kết thúc bằng `;` |
| `System.out.println(...);` | Lời gọi phương thức dùng như statement, kết thúc bằng `;` |

**Lưu ý về tên:** Dùng `java BlockSyntaxDemo` để khởi chạy class đã biên dịch, không dùng `java BlockSyntaxDemo.class`. Trong file nguồn không có khai báo `package`, nên tên class chạy ở ví dụ này chỉ là `BlockSyntaxDemo`.

## 3. `{ }` tạo khối lệnh như thế nào?

Một block statement có hình dạng:

~~~java
{
    // Có thể là 0, 1 hoặc nhiều câu lệnh.
    int first = 2;
    int second = 3;
    System.out.println(first + second);
}
~~~

Block trên **hợp lệ khi nằm trong thân một phương thức hoặc vị trí cho phép block statement**, nhưng đoạn riêng lẻ này **không phải tệp Java hoàn chỉnh** để gọi `java` trực tiếp.

Trong một phương thức, có thể lồng nhiều block:

~~~java
int outer = 10;
{
    int inner = 5;
    System.out.println(outer + inner); // 15
}
System.out.println(outer);             // 10
// System.out.println(inner);          // Sai: inner đã ra khỏi phạm vi.
~~~

**Phạm vi (scope):** biến cục bộ `inner` chỉ dùng được trong block khai báo nó, kể từ chỗ khai báo trở đi. Biến `outer` được khai báo bên ngoài nên block lồng bên trong có thể tham chiếu tới nó. Khi kết thúc block, tên biến cục bộ chỉ tồn tại trong block đó không còn truy cập được.

Đây cũng là điểm khác biệt với **field** của lớp:

~~~java
class Counter {
    private int total;  // Field của mỗi đối tượng Counter.

    void addOne() {
        int delta = 1;  // Biến cục bộ của phương thức.
        total += delta;
    }
}
~~~

`total` là field của object; `delta` là biến cục bộ chỉ có phạm vi trong phương thức. Không dùng thời điểm kết thúc một block để suy luận rằng object chứa field chắc chắn đã bị thu gom bộ nhớ; đó là hai khái niệm khác nhau.

### Ranh giới khai báo và che khuất tên

Trong các phạm vi cục bộ chồng lấp nhau, Java không cho khai báo lại một **biến cục bộ trùng tên** như cách làm bên dưới:

~~~java
void example() {
    int value = 1;
    {
        // int value = 2; // Lỗi biên dịch: trùng tên biến cục bộ còn trong phạm vi.
        System.out.println(value);
    }
}
~~~

Ngược lại, có thể có tên field và biến cục bộ trùng nhau; khi đó cú pháp như `this.value` giúp chỉ rõ field của đối tượng. Chỉ nên giới thiệu quy tắc này để tránh suy luận rằng “cứ thêm `{ }` là có thể tái sử dụng mọi tên”.

## 4. Khi nào cần dấu `;`?

Có nhiều statement kết thúc bằng dấu chấm phẩy, nhưng **không phải tất cả**. Bảng dưới tóm tắt những dạng thường gặp trong Java 17:

| Dạng | Ví dụ | Có `;`? |
| --- | --- | --- |
| Khai báo biến cục bộ | `int count = 0;` | Có |
| Gán và gọi method | `count++;`, `System.out.println(count);` | Có |
| Trả về | `return count;` hoặc `return;` trong method `void` | Có |
| Thoát/bỏ qua vòng lặp | `break;`, `continue;` | Có |
| Khai báo `package` và `import` | `package demo;`, `import java.util.List;` | Có |
| `if` có block | `if (ready) { work(); }` | **Không** đặt `;` sau header `if (...)` |
| `for` truyền thống | `for (int i = 0; i < 3; i++) { ... }` | Có **hai** `;` bên trong header |
| `while` có block | `while (ready) { work(); }` | Không có `;` giữa `)` và `{` |
| `do...while` | `do { work(); } while (ready);` | Có `;` ở cuối |
| Khai báo phương thức có thân | `void work() { ... }` | Không bắt buộc `;` sau `}` |
| Khai báo lớp có thân | `class Example { ... }` | Không cần `;` sau `}` |

**Chính xác hơn:** dấu `;` là một token ngữ pháp, không chỉ đơn giản “chốt dòng code”. Java cho phép nhiều statement cùng một dòng hoặc một statement trải qua nhiều dòng:

~~~java
int a = 1; int b = 2;
System.out.println(
        a + b
); // Kết thúc statement ở đây, không phải ở cuối dòng đầu.
~~~

Hai dạng sau không tương đương:

~~~java
int amount = 10;  // Statement hoàn chỉnh.
int amount = 10   // Nếu đây là một statement độc lập: thiếu dấu ;, lỗi biên dịch.
~~~

Dòng thứ hai chỉ là **mảnh minh họa cú pháp sai**, không phải code để đặt chung với dòng đầu vào một chương trình chạy được.


## 5. Bẫy cú pháp: dấu `;` trở thành thân của `if`

Một dấu `;` đứng độc lập là **empty statement**. Khi đặt ngay sau `if (condition)`, nó chính là toàn bộ thân của nhánh, còn block phía sau chạy độc lập:

~~~java
boolean ready = false;
if (ready); // Thân if rỗng.
{
    System.out.println("Khoi nay chay doc lap");
}
~~~

Dù `ready` là `false`, đoạn mã trên (nếu đặt trong một phương thức) vẫn in `Khoi nay chay doc lap`. Muốn chỉ in khi điều kiện đúng, hãy bỏ dấu `;` sau điều kiện và viết `if (ready) { ... }`.

Đây là ví dụ ngắn về tác động của token `;` lên cấu trúc khối. Bài **Câu lệnh biểu thức và câu lệnh rỗng** giải thích sâu hơn khi nào `;` là một statement riêng và hành vi của nó trong vòng lặp. Với các nhánh `if` lồng nhau thiếu ngoặc, `else` ghép theo cú pháp với `if` gần nhất có thể nhận nó, bất kể thụt lề.

## 6. Khối lệnh trong `for`, `while` và `do...while`

### 6.1. `for` truyền thống có hai dấu phân tách `;`

~~~java
for (int i = 0; i < 3; i++) {
    System.out.println(i);
}
~~~

Kết quả:

~~~text
0
1
2
~~~

Ba phần của header là:

1. `int i = 0` — khởi tạo, chạy một lần trước vòng.
2. `i < 3` — điều kiện kiểm tra trước mỗi lượt lặp.
3. `i++` — cập nhật sau mỗi lượt thực thi thân vòng.

Hai dấu `;` ở giữa là **bắt buộc đối với cấu trúc này**, ngay cả khi một số phần bỏ trống. Ví dụ `for (;;) { break; }` hợp lệ: header có hai dấu phân tách nhưng ba phần đều rỗng, vòng dừng nhờ `break;`.

### 6.2. Enhanced `for` không dùng hai dấu `;`

~~~java
int[] values = {2, 4, 6};
for (int value : values) {
    System.out.println(value);
}
~~~

Dấu `:` là cú pháp của enhanced for; đừng nhầm với `for (init; condition; update)`. Mảng `values` có khởi tạo bằng dấu ngoặc nhọn nhưng `{2, 4, 6}` ở đây là **array initializer**, không phải block statement.

### 6.3. `while` không có `;` sau điều kiện

~~~java
int remaining = 2;
while (remaining > 0) {
    System.out.println(remaining);
    remaining--;
}
~~~

Đầu ra là `2` rồi `1`. Dấu `;` xuất hiện ở **hai statement bên trong** block, không ở giữa `while (...)` và block. Nếu viết `while (remaining > 0);` với `remaining` không thay đổi ở header, bạn có thể tạo vòng lặp rỗng không kết thúc.

### 6.4. `do...while` cần dấu `;` cuối

~~~java
int remaining = 2;
do {
    System.out.println(remaining);
    remaining--;
} while (remaining > 0);
~~~

Dòng đóng `} while (...);` có dấu chấm phẩy **bắt buộc**. Điểm khác với `while` là thân `do` thực thi ít nhất một lần trước khi kiểm tra điều kiện.

## 7. Block quyết định cả phạm vi biến và tính hợp lệ của code

### Biến chỉ tồn tại trong nhánh khai báo

Đoạn sau minh họa lỗi phạm vi:

~~~java
if (args.length > 0) {
    String first = args[0];
    System.out.println(first);
}
// System.out.println(first); // Lỗi: first chỉ được khai báo trong block if.
~~~

Nó dùng biến `args` có sẵn **bên trong `main(String[] args)`**. Việc bình thường hóa khoảng trắng hay thêm dấu `;` **không** giải quyết lỗi tên biến nằm ngoài phạm vi.

### Khác biệt giữa “đã khai báo” và “đã gán giá trị”

Một biến cục bộ phải **được gán chắc chắn** (*definitely assigned*) trước khi đọc giá trị:

~~~java
int result;
if (args.length > 0) {
    result = args.length;
} else {
    result = 0;
}
System.out.println(result);  // Hợp lệ: mọi nhánh đều gán result.
~~~

Nếu bỏ nhánh `else`, compiler có thể báo `variable result might not have been initialized`. Java **không** tự khởi tạo biến cục bộ thành 0 chỉ vì kiểu là `int`; quy tắc mặc định giá trị của field khác với quy tắc definite assignment cho biến cục bộ.

Đây là ví dụ tốt để thấy `{ }` không chỉ “để code đẹp”: chúng thể hiện nhánh kiểm tra, phạm vi và đường đi điều khiển mà compiler phân tích.

## 8. Không phải mọi `{ }` đều là block statement

Dấu ngoặc nhọn cũng xuất hiện trong các cấu trúc Java 17 khác:

### 8.1. Khởi tạo mảng

~~~java
int[] scores = {8, 9, 10};
System.out.println(scores.length); // 3
~~~

`{8, 9, 10}` là **array initializer**. Dấu `;` cuối là dấu kết thúc **khai báo biến**, không phải dấu bắt buộc sau mọi `}`.

### 8.2. Lambda có thân là block

~~~java
Runnable task = () -> {
    System.out.println("Lam viec");
};
task.run();
~~~

Lời gọi `println` bên trong kết thúc bằng `;`; dấu `;` sau `}` kết thúc **statement gán lambda cho biến `task`**. Không suy ra “mọi block `{ }` đều cần `;` ở cuối”.

### 8.3. `switch` expression trong Java 17

~~~java
int day = 2;
String label = switch (day) {
    case 1 -> "Mon";
    case 2 -> "Tue";
    default -> "Other";
};
System.out.println(label);
~~~

Kết quả: `Tue`. Ở đây dấu `;` sau `}` kết thúc **khai báo biến `label`** dùng một biểu thức `switch`. Khi một nhánh `case` có nhiều statement, nó có thể dùng block và `yield` để trả giá trị của switch expression:

~~~java
int n = 4;
String category = switch (n) {
    case 4 -> {
        System.out.println("Dang xet so 4");
        yield "Chan";
    }
    default -> "Khac";
};
~~~

Đây là cú pháp hỗ trợ trong Java 17; `yield "Chan";` dùng để tạo giá trị cho switch expression, không đồng nghĩa với `return` thoát khỏi phương thức.

**Tóm lại:** cần xác định dấu `{ }` đang đóng **khối lệnh, thân khai báo hay initializer** trước khi quyết định đặt dấu `;`.

## 9. Lỗi cú pháp: xem lỗi theo ngữ cảnh thay vì đoán

| Thông báo/triệu chứng | Nguyên nhân khả dĩ | Cách sửa phù hợp |
| --- | --- | --- |
| `';' expected` | Thiếu dấu `;` sau khai báo biến hoặc expression statement | Xác định statement cần kết thúc ở đâu |
| `reached end of file while parsing` | Thiếu `}` hoặc một phần cú pháp chưa đóng | Đối chiếu các cặp `{ }`, dấu `( )` |
| `'else' without 'if'` | Có statement hoặc `;` làm thay đổi cấu trúc nhánh | Kiểm tra dấu `;` sau `if` và các block |
| `variable ... is already defined` | Khai báo lại biến cục bộ trùng tên trong phạm vi chồng lấp | Đổi tên hoặc sửa phạm vi đúng mục đích |
| `cannot find symbol` với biến trong block trước | Biến nằm ngoài phạm vi nhìn thấy | Khai báo ở phạm vi phù hợp, truyền qua tham số hoặc trả kết quả |
| `variable ... might not have been initialized` | Có đường đi tới chỗ đọc nhưng chưa chắc chắn gán giá trị | Bảo đảm gán trước khi dùng trên mọi nhánh cần thiết |
| Vòng lặp `while` không dừng | Vô tình dùng `while (condition);` với thân rỗng | Bỏ dấu `;` sai và kiểm tra điều kiện cập nhật |
| `if` luôn “in” dù điều kiện false | Có `;` sau `if (...)`, block sau đó độc lập | Ghép đúng `if (condition) { ... }` |

**Điểm quan trọng:** thông báo compiler có thể chỉ tới một dòng **sau** chỗ đặt sai dấu `{`, `}` hoặc `;`, vì trình phân tích cú pháp chỉ phát hiện mâu thuẫn ở vị trí tiếp theo. Khi thấy lỗi, đọc cả vài dòng trước đó.

## 10. Quy tắc trình bày code giúp ngăn lỗi

- Mỗi cặp `{`/`}` nên được thụt lề nhất quán; đóng ngoặc đúng cấp khối.
- Ưu tiên dùng `{ }` cho thân `if`/`else`/`for`/`while` dù ngữ pháp Java có thể cho một statement không cần ngoặc. Điều này giảm rủi ro khi bổ sung câu lệnh.
- Đừng thêm `;` ngay sau phần điều kiện `if (...)`, `for (...)` hoặc `while (...)` nếu bạn định chạy một block.
- Với `do { ... } while (...);`, đừng quên dấu `;` cuối.
- Không chỉ đếm dấu ngoặc trên **văn bản**: ký tự `{`, `}`, `;` xuất hiện bên trong **chuỗi** hoặc **comment** không tự biến thành cú pháp điều khiển.

Ví dụ:

~~~java
String text = "{ ; }"; // Các ký tự bên trong chuỗi không tạo block.
System.out.println(text); // In đúng: { ; }
~~~

Đừng cố sửa bằng cách xóa mọi dấu chấm phẩy sau dấu `}`, vì trường hợp khai báo biến với mảng, lambda hoặc switch expression **cần** dấu đó để kết thúc statement.

## 11. Bài tập tự luyện

**Bài 1 — Đoán đầu ra của chương trình chính.** Với `limit = 6`, những lần nào `total += number;` thực sự chạy? Thử đổi `limit` thành 5 và dự đoán tổng; sau đó biên dịch lại để kiểm tra.

**Bài 2 — Tìm dấu sai.** Trong phương thức `main`, đoạn sau in mấy dòng và vì sao?

~~~java
boolean pass = false;
if (pass);
{
    System.out.println("PASS");
}
~~~

*Định hướng:* Một dòng `PASS`. `if (pass)` đang điều khiển empty statement; block riêng vẫn chạy.

**Bài 3 — Tính phạm vi.** Đoạn sau có biên dịch được không? Nếu không, sửa để in được giá trị:

~~~java
{
    int count = 3;
}
System.out.println(count);
~~~

*Định hướng:* Không. `count` được khai báo trong block đã kết thúc; có thể khai báo `count` ở phạm vi bên ngoài nếu cần sử dụng sau đó.

**Bài 4 — Điền dấu phân tách.** Viết vòng `for` in 1, 2, 3. Chỉ ra hai dấu `;` trong header và dấu `;` kết thúc lời gọi `println` bên trong.

**Bài 5 — So sánh hai loại `while`.** Viết một vòng `while` và một vòng `do...while` với điều kiện ban đầu `false`, quan sát số lần thực thi thân vòng và vị trí dấu chấm phẩy.

**Bài 6 — Nhận diện kiểu `{ }`.** Trong `int[] a = {1, 2};`, `if (ok) { work(); }` và `Runnable r = () -> { work(); };`, dấu ngoặc nhọn thuộc loại nào? Dấu `;` ngoài cùng đang kết thúc cấu trúc nào?

## 12. Tự kiểm tra cuối bài

Bạn hiểu chủ đề nếu có thể giải thích chính xác:

1. **Block** bắt đầu và kết thúc ở đâu, vì sao thụt lề không quyết định cấu trúc.
2. Dấu `;` nào kết thúc statement, dấu nào phân tách ba phần của `for`.
3. Tại sao `if (condition); { ... }` nguy hiểm dù thường không phải lỗi biên dịch.
4. Tại sao `do...while` cần `;` cuối nhưng `while (...) { ... }` không.
5. Khi nào biến cục bộ nằm ngoài phạm vi, và tại sao nó còn có thể bị lỗi *definite assignment*.
6. Vì sao `int[] values = {2, 4};` hoặc `String s = switch (...) { ... };` cần dấu chấm phẩy cuối dù vừa có dấu `}`.

**Ghi nhớ:** Trong Java, **`{ }` là ranh giới cấu trúc**, còn **`;` là token ngữ pháp** để kết thúc hoặc phân tách theo từng dạng câu lệnh. Hãy nhìn **loại cấu trúc đang viết**, không chỉ nhìn vị trí xuống dòng.
