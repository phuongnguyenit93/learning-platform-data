# Câu lệnh biểu thức và câu lệnh rỗng trong Java

> **Java core — language-basics / Cấu trúc chương trình**  
> **Môi trường:** JDK 17 trở lên, không cần thư viện ngoài.  
> **Kết quả học tập:** Nhận biết expression statement và empty statement, phân biệt biểu thức hợp lệ/không hợp lệ khi đứng riêng, đọc đúng tác dụng của dấu `;`, dự đoán hành vi khi có câu lệnh rỗng trong `if` hoặc vòng lặp, và tự chạy một ví dụ Java hoàn chỉnh.

## 1. Biểu thức, câu lệnh và dấu chấm phẩy

**Biểu thức** (*expression*) là cấu trúc được đánh giá để tạo một giá trị hoặc kết quả kiểu `void`, đôi khi có tác dụng phụ. Ví dụ `2 + 3` tạo giá trị `5`; `number++` vừa tạo một giá trị vừa thay đổi `number`; `System.out.println("Hi")` có tác dụng in một dòng.

**Câu lệnh** (*statement*) là đơn vị hành động/điều khiển được Java cho phép ở một vị trí cụ thể. **Câu lệnh biểu thức** (*expression statement*) có hình thức một **statement expression** được phép, kết thúc bằng dấu `;`.

~~~java
int number = 1;             // Khai báo biến cục bộ: không phải expression statement.
number = number + 2;        // Expression statement: phép gán.
number++;                   // Expression statement: tăng hậu tố.
System.out.println(number); // Expression statement: gọi phương thức.
~~~

Kết quả in là `4`. Điểm quan trọng: **không phải mọi biểu thức đều được phép viết thành một statement chỉ bằng cách thêm dấu `;`**.

| Khái niệm | Ví dụ | Nhận xét |
| --- | --- | --- |
| Biểu thức có giá trị | `number + 2` | Tính ra giá trị nhưng không phải loại được phép đứng riêng thành statement |
| Câu lệnh biểu thức | `number += 2;` | Cú pháp hợp lệ vì thuộc nhóm phép gán |
| Khai báo biến cục bộ | `int number = 1;` | Statement khai báo, không phải expression statement |
| Câu lệnh rỗng | `;` | Statement hoàn chỉnh, không có công việc bên trong |
| Khối lệnh rỗng | `{}` | Một block chứa không statement; **khác cú pháp** với `;` |

## 2. Những expression statement hợp lệ

Java 17 quy định những loại statement expression sau:

| Loại | Ví dụ trong ngữ cảnh phù hợp | Tác dụng |
| --- | --- | --- |
| Gán (*assignment*) | `x = 10;`, `x += 2;` | Gán/thay đổi trạng thái của biến, field hoặc phần tử |
| Tăng, giảm tiền tố | `++x;`, `--x;` | Thay đổi giá trị; biểu thức tạo giá trị sau cập nhật |
| Tăng, giảm hậu tố | `x++;`, `x--;` | Thay đổi giá trị; biểu thức tạo giá trị trước cập nhật |
| Gọi phương thức | `System.out.println(x);`, `Math.abs(-5);` | Gọi method, có thể bỏ qua giá trị trả về |
| Tạo đối tượng bằng `new` | `new StringBuilder("abc");` | Tạo đối tượng, có thể không giữ tham chiếu |

Điều cần chú ý:

- `Math.abs(-5);` là statement hợp lệ nhưng **không in 5**. Kết quả được tính ra rồi bỏ đi. Muốn nhìn thấy nó, dùng `System.out.println(Math.abs(-5));`.
- `new StringBuilder("abc");` hợp lệ, nhưng khi không giữ hoặc sử dụng đối tượng, câu lệnh thường không phục vụ mục đích rõ ràng.
- `x++;` và `++x;` đều tăng `x` một đơn vị khi đứng riêng; giá trị biểu thức của chúng khác nhau **nếu dùng trong một biểu thức lớn hơn**.
- Một lời gọi phương thức không phải lúc nào cũng tạo tác dụng phụ, còn một phép gán hoặc tăng/giảm thường làm thay đổi trạng thái. Đừng định nghĩa expression statement đơn giản là “lệnh có tác dụng phụ”.

**Giới hạn rõ ràng:** `new int[3];` là **biểu thức tạo mảng**, không thuộc nhóm *class instance creation expression* được phép đứng riêng như expression statement. Cần gán mảng cho một biến hoặc dùng nó ở ngữ cảnh biểu thức phù hợp.

## 3. Chương trình mẫu hoàn chỉnh trên Java 17+

Lưu mã dưới tên **StatementKindsDemo.java**:

~~~java
public final class StatementKindsDemo {
    private static int calls = 0;

    private static void mark() {
        calls++;  // Post-increment expression statement.
    }

    public static void main(String[] args) {
        int number = 1;               // Khai báo biến.
        number = number + 2;          // Phép gán.
        number++;                     // Tăng hậu tố.
        mark();                       // Gọi phương thức.
        new StringBuilder("unused");  // Tạo object, bỏ tham chiếu.
        ;                             // Câu lệnh rỗng.

        int checks = 0;
        while (++checks < 3) {
            // Đây là một block rỗng, không phải dấu ; đứng riêng.
        }

        System.out.println("number = " + number);
        System.out.println("calls = " + calls);
        System.out.println("checks = " + checks);

        boolean enabled = false;
        if (enabled)
            ;  // Chỉ empty statement thuộc nhánh if.

        {  // Khối này độc lập với if, vì if đã kết thúc.
            System.out.println("Khoi doc lap van chay");
        }
    }
}
~~~

Mở terminal ở thư mục chứa `StatementKindsDemo.java` rồi chạy:

~~~bash
java -version
javac -version
javac -encoding UTF-8 StatementKindsDemo.java
java StatementKindsDemo
~~~

Hai lệnh `-version` dùng để kiểm tra môi trường; đầu ra riêng của chương trình sau lệnh `java StatementKindsDemo` là:

~~~text
number = 4
calls = 1
checks = 3
Khoi doc lap van chay
~~~

**Vì sao ra những số đó?** `number` chuyển từ 1 sang 3 bằng phép gán, rồi sang 4 bởi `number++`. `mark()` tăng `calls` một lần. Với điều kiện `++checks < 3`, giá trị được so lần lượt là 1, 2, 3; hai lần đầu đúng, lần thứ ba sai, và `checks` cuối cùng bằng **3**. Câu lệnh `new StringBuilder(...)` và `;` đứng riêng không in gì.

`enabled` bằng `false` nên empty statement là thân của `if` không chạy. Tuy nhiên, block `{ ... }` tiếp theo **không nằm trong `if`**, vì thế chương trình vẫn in dòng cuối.

~~~mermaid
flowchart TD
    A["main bắt đầu"] --> B["Gán / tăng / gọi mark / tạo object"]
    B --> C["Empty statement: ;"]
    C --> D["while: kiểm tra ++checks < 3"]
    D --> E["In number, calls, checks"]
    E --> F{"enabled?"}
    F -->|"true"| G["Thực hiện ; rỗng"]
    F -->|"false"| H["Bỏ qua ; rỗng"]
    G --> I["Block độc lập: in dòng cuối"]
    H --> I
~~~

## 4. Biểu thức nào không thể đứng riêng?

Các dòng sau được **comment vì cố ý không hợp lệ**. Không bỏ comment và kỳ vọng biên dịch thành công:

~~~java
int x = 5;

// x + 1;               // Lỗi: phép cộng đơn thuần không phải statement expression.
// x > 0;               // Lỗi: phép so sánh đơn thuần.
// "Hello";             // Lỗi: literal đứng riêng.
// (x == 0) ? 1 : 2;    // Lỗi: conditional expression đứng riêng.
// new int[3];          // Lỗi: array creation đứng riêng.
~~~

Với compiler, các dạng không hợp lệ thường bị báo `not a statement` hoặc một lỗi cú pháp liên quan. Vấn đề không nằm ở chỗ quên dấu `;`; các dòng này **đã có `;` nhưng vẫn không thuộc nhóm Java cho phép**.

Để sửa, hãy **dùng giá trị** vào một hoạt động có ý nghĩa:

~~~java
int x = 5;
int next = x + 1;
boolean positive = x > 0;

System.out.println(next);
System.out.println(positive);
System.out.println(x == 0 ? "Bang 0" : "Khac 0");
~~~

Kết quả:

~~~text
6
true
Khac 0
~~~

`int next = x + 1;` là **khai báo biến cục bộ có biểu thức khởi tạo**; `System.out.println(...)` là **method invocation expression statement**. Biểu thức điều kiện `?:` được đặt **bên trong đối số** của một lời gọi hợp lệ, không được viết thành statement độc lập.

## 5. Empty statement: khi toàn bộ statement chỉ là `;`

Về ngữ pháp, một **câu lệnh rỗng** chỉ gồm dấu chấm phẩy:

~~~java
;
~~~

Nó không tự thay đổi giá trị, không gọi phương thức và không in gì. Nhưng vẫn là **một statement hợp lệ** ở nơi Java chấp nhận statement.

~~~java
int total = 0;
;        // Empty statement thứ nhất.
;        // Empty statement thứ hai.
total++; // Expression statement: tăng total.
System.out.println(total); // 1.
~~~

**Ba cấu trúc dễ lẫn nhau:**

| Cách viết | Bản chất |
| --- | --- |
| `;` | Một empty statement |
| `{}` | Một block rỗng, chứa 0 statement |
| `int total = 0;` | Một local variable declaration statement kết thúc bằng `;` |

Một dấu `;` kết thúc khai báo **không đồng thời tạo thêm empty statement**. Tương tự, dấu `;` dùng để phân tách các phần trong header `for` có vai trò ngữ pháp riêng.

## 6. Empty statement và block rỗng: giống hành vi, khác cú pháp

Cả `;` và `{}` đều có thể biểu thị **không có công việc cần làm**, nhưng chúng là **hai loại statement khác nhau**. Với nhánh `if`, Java có thể nhận một empty statement làm thân:

~~~java
boolean allowed = false;
if (allowed)
    ;
else
    System.out.println("Bi tu choi");
~~~

Trong đoạn mã **bên trong một phương thức**, kết quả là `Bi tu choi`. Dấu `;` là toàn bộ thân nhánh `if`, còn `else` vẫn thuộc chính `if` này. Viết block rỗng có thể diễn đạt ý định rõ hơn:

~~~java
if (allowed) {
    // Chưa có việc cần làm khi được phép.
} else {
    System.out.println("Bi tu choi");
}
~~~

Hai đoạn có cùng hành vi với giá trị `allowed` nêu trên, nhưng block giúp người đọc nhận ra ranh giới nhánh và thuận tiện thêm statement sau này. Một dấu `;` **vô tình** giữa `if (allowed)` và một block chứa `println` sẽ khiến block đó độc lập và chạy bất kể điều kiện; đó là một lỗi logic có thể biên dịch thành công.

Với ví dụ thực tế, thường nên sửa ý định thiếu thành một điều kiện và block rõ nghĩa thay vì giữ những nhánh rỗng khó hiểu. Phần tiếp theo xem trường hợp empty statement nằm trong **vòng lặp**, nơi nó còn ảnh hưởng tới số lượt đánh giá điều kiện.


## 7. Câu lệnh rỗng bên trong vòng lặp

### `while` với empty statement

~~~java
int attempts = 0;
while (++attempts < 3)
    ;
System.out.println(attempts); // 3
~~~

Điều kiện tự tăng `attempts`. Nó được kiểm tra lần lượt với 1, 2, 3 và dừng tại 3. Trong ví dụ này, thân `while` chỉ là dấu `;`.

Ngược lại, dạng sau nếu bỏ comment có nguy cơ lặp vô hạn:

~~~java
// int attempts = 0;
// while (attempts < 3);
// Điều kiện không làm thay đổi attempts, thân vòng cũng không cập nhật nó.
~~~

Đừng dùng vòng **busy-wait** rỗng để chờ một sự kiện trong chương trình thực: ngoài nguy cơ không dừng, nó có thể làm tiêu tốn CPU và gây vấn đề về giao tiếp giữa các thread.

### `for`: hai dấu phân tách ở header không phải empty statement

~~~java
int seen = 0;
for (int i = 0; i < 3; i++)
    ;
seen++;
System.out.println(seen); // 1
~~~

Trong `for (int i = 0; i < 3; i++)`, hai dấu `;` chia ba phần **khởi tạo / điều kiện / cập nhật**. Dấu `;` **sau dấu `)`** mới là empty statement làm thân vòng. `seen++` nằm **sau** vòng, vì vậy chỉ thực hiện một lần.

Muốn tăng `seen` sau mỗi lượt:

~~~java
int seen = 0;
for (int i = 0; i < 3; i++) {
    seen++;
}
System.out.println(seen); // 3
~~~

`for (;;) ;` hợp lệ về cú pháp: hai dấu `;` trong header, còn dấu cuối là thân rỗng. Nhưng **không có điều kiện dừng hoặc break**, nên đây là vòng lặp vô hạn; **không nên chạy để thử**.

### `do...while`: dấu chấm phẩy cuối là bắt buộc

~~~java
int count = 0;
do {
    count++;
} while (count < 2);
System.out.println(count); // 2
~~~

Dấu `;` sau `while (count < 2)` là **bộ phận bắt buộc của cú pháp do-while**, không phải một empty statement thêm vào. Dạng `do ; while (false);` cũng hợp lệ: dấu `;` đầu là thân rỗng, dấu thứ hai kết thúc câu lệnh do-while.

## 8. Khi expression statement xuất hiện trong `for`

Trong phần cập nhật của `for`, Java cho phép một **danh sách statement expressions** được phân tách bằng dấu phẩy:

~~~java
int sum = 0;
for (int i = 1; i <= 3; i++, sum += i) {
    // Block rỗng.
}
System.out.println(sum); // 9
~~~

**Tại sao là 9 mà không phải 6?** Sau mỗi lượt, Java đánh giá `i++` **trước** `sum += i`, tức `sum` lần lượt nhận thêm 2, 3, 4. Tổng là 9. Nếu đổi thứ tự thành `sum += i, i++` thì kết quả là 6.

Lưu ý: dấu phẩy ở đây là cú pháp của danh sách biểu thức trong `for`; Java **không** có một toán tử “comma expression” dùng tự do như trong một số ngôn ngữ khác.

Với `for (int i = 0; i < 3; i++);`, dấu `;` cuối (nằm ngoài dấu ngoặc tròn) có thể khiến vòng lặp chạy không có nội dung mà lập trình viên không cố ý.

## 9. Kết quả của method có thể bị bỏ qua

Một expression statement không nhất thiết in thông báo hoặc cập nhật biến. Ví dụ:

~~~java
String label = "java";
label.toUpperCase();
System.out.println(label);
~~~

Kết quả:

~~~text
java
~~~

`String` là immutable. Phương thức `toUpperCase()` trả về một chuỗi mới; gọi xong mà không dùng kết quả thì `label` vẫn giữ `"java"`. Nếu muốn lưu:

~~~java
label = label.toUpperCase();
System.out.println(label); // JAVA
~~~

Điều này giải thích vì sao **Java cho phép** câu lệnh gọi phương thức nhưng **việc bỏ kết quả** đôi khi là lỗi logic. Ngược lại, lời gọi `System.out.println(...)` hữu ích chính vì tác dụng phụ là in ra stdout.

## 10. Lỗi và cách kiểm tra

| Hiện tượng | Nguyên nhân thường gặp | Khắc phục |
| --- | --- | --- |
| `not a statement` | Biểu thức đứng riêng không thuộc nhóm statement expression | Dùng kết quả trong phép gán, khai báo hoặc lời gọi |
| `';' expected` | Thiếu dấu kết thúc statement/declaration cần dấu `;` | Kiểm tra dạng ngữ pháp đang viết |
| `if` in nội dung dù điều kiện false | `;` đứng sau `if (...)`; block phía sau độc lập | Bỏ `;` sai và dùng `if (...) { ... }` |
| `while` hoặc `for` không kết thúc | Thân rỗng và điều kiện không tiến về false | Thêm cập nhật/điều kiện dừng hợp lý |
| Vòng chạy ba lần nhưng biến chỉ tăng một lần | Câu tăng đứng **sau** vòng, không nằm trong thân | Chuyển câu tăng vào block của vòng |
| Gọi `toUpperCase()` nhưng chuỗi không đổi | Đã bỏ giá trị trả về | Gán lại hoặc sử dụng giá trị trả về |
| Tạo object nhưng không dùng | `new SomeClass();` có kết quả bị bỏ qua | Cân nhắc lưu tham chiếu hoặc loại bỏ lệnh |

Có những lỗi logic **compiler không nhất thiết cảnh báo**: đặc biệt `if (condition);` có thể hợp lệ. IDE/linter có thể giúp phát hiện nhưng không thay thế việc đọc code để xác định **statement nào thật sự nằm trong nhánh hoặc vòng lặp**.

### Ba câu hỏi chẩn đoán dấu `;`

1. `;` này đang **kết thúc** một expression/declaration statement?
2. `;` này đang **phân tách** các phần bên trong `for (...)` hoặc kết thúc cú pháp `do...while`?
3. `;` này đang **tự nó tạo thành empty statement**, có thể làm sai cấu trúc `if`/vòng lặp?

## 11. Bài tập thực hành

**Bài 1 — Phân loại.** Giả sử `int x = 1;` đã có. Với `x += 3;`, `x > 0;`, `x++;`, `;`, `new Object();`, `"hello";`, `System.out.println(x);`, hãy phân loại thành expression statement, empty statement hoặc không hợp lệ.

*Đáp án định hướng:* `x > 0;` và `"hello";` không hợp lệ. `;` là empty statement. Các trường hợp còn lại là expression statements.

**Bài 2 — Dự đoán đầu ra.** Khi `boolean ready = false; if (ready); { System.out.println("OK"); }` được chạy trong method, có in `OK` không? Vì sao?

*Đáp án:* Có; `if` chỉ quản lý empty statement, block tiếp theo độc lập.

**Bài 3 — Cập nhật điều kiện.** Với `int n = 0; while (++n < 5) ;`, sau vòng `n` bằng bao nhiêu? Đổi `++n` thành `n++` làm khác hành vi kiểm tra ra sao?

*Định hướng:* Với `++n`, n cuối cùng là 5. Với `n++`, so sánh dùng giá trị trước tăng, và n cuối cùng là 6.

**Bài 4 — Sửa statement sai.** Chuyển `int x = 4; x * 2;` thành một phương án in `8` và một phương án lưu kết quả trong biến `doubleX`.

**Bài 5 — Thử source chạy được.** Trong `StatementKindsDemo`, thay `if (enabled) ;` và block độc lập thành `if (enabled) { ... }`. Chạy với `enabled` lần lượt false và true, so sánh số dòng output.

**Bài 6 — Thứ tự side effect.** Thay `i++, sum += i` trong header `for` bằng `sum += i, i++`, giải thích vì sao tổng thay đổi từ 9 sang 6.

## 12. Tự đánh giá

Bạn nắm bài nếu không còn nhầm:

- **`x++;`** — statement biểu thức hợp lệ;
- **`x + 1;`** — không phải statement hợp lệ;
- **`;`** — empty statement;
- **`{ }`** — block rỗng, **không đồng nhất** với empty statement;
- **`if (condition); { ... }`** — block sau `if` chạy độc lập;
- **`for (a; b; c)`** — hai `;` chia ba phần header, không phải hai empty statement.

**Kết luận:** Java chỉ cho một số dạng biểu thức nhất định đứng riêng thành câu lệnh. Dấu `;` có thể **kết thúc** một câu lệnh, **phân tách** phần header, hoặc **tự nó là một câu lệnh rỗng**. Hãy xác định vai trò theo **ngữ pháp xung quanh**, không theo chỗ xuống dòng.
