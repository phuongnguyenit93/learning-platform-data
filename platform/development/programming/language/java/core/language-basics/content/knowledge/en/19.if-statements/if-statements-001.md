# Cú pháp `if`, `else` và chuỗi `else if` — Java 17+

`if` là câu lệnh **rẽ nhánh theo điều kiện**: chương trình đánh giá một biểu thức `boolean` và chỉ chạy khối lệnh phù hợp. Có thể viết một `if` đơn, thêm nhánh `else`, hoặc nối các trường hợp bằng `else if`.

~~~java
int age = 20;

if (age >= 18) {
    System.out.println("Đủ tuổi");
} else {
    System.out.println("Chưa đủ tuổi");
}
~~~

Ở ví dụ này, điều kiện `age >= 18` là `true` nên chỉ nhánh đầu tiên chạy. Không có cơ chế tự động chạy tiếp nhánh `else`.

## 1. Ba dạng cú pháp nền tảng

### Dạng 1 — Chỉ `if`

~~~java
int quantity = 3;

if (quantity > 0) {
    System.out.println("Có hàng");
}
~~~

Nếu điều kiện false, khối bị bỏ qua; chương trình tiếp tục ở câu lệnh sau `if`. **`else` không bắt buộc**.

### Dạng 2 — `if / else`

~~~java
int balance = 50;

if (balance >= 100) {
    System.out.println("Đủ tiền");
} else {
    System.out.println("Chưa đủ tiền");
}
~~~

Chọn **một trong hai** khối. `else` không có điều kiện riêng: nó được chọn khi điều kiện `if` là false.

### Dạng 3 — Chuỗi `if / else if / else`

~~~java
int score = 83;

if (score >= 90) {
    System.out.println("A");
} else if (score >= 75) {
    System.out.println("B");
} else if (score >= 60) {
    System.out.println("C");
} else {
    System.out.println("D");
}
~~~

Java đánh giá các điều kiện **từ trên xuống**. Gặp điều kiện true đầu tiên thì chạy nhánh tương ứng và **bỏ qua tất cả nhánh còn lại**. `else` cuối cùng là nhánh mặc định, có thể bỏ nếu không cần.

**`else if` không phải từ khóa ghép riêng:** về cú pháp, đó là một `else` theo sau bởi một câu lệnh `if`; cách viết liền mạch tạo thành chuỗi nhiều trường hợp.

## 2. Sơ đồ lựa chọn nhánh

~~~mermaid
flowchart TD
    Start["Bắt đầu"] --> C1{"Điều kiện 1?"}
    C1 -- true --> B1["Chạy nhánh if"]
    C1 -- false --> C2{"Điều kiện 2?"}
    C2 -- true --> B2["Chạy nhánh else if"]
    C2 -- false --> B3["Chạy else (nếu có)"]
    B1 --> End["Lệnh sau chuỗi"]
    B2 --> End
    B3 --> End
~~~

Sơ đồ minh họa một `else if`. Có thể thêm nhiều `else if` theo cách tương tự; nguyên tắc vẫn là **nhánh đúng đầu tiên thắng**.

| Cấu trúc | Điều kiện được xét | Số nhánh có thể chạy trong một lần đi qua |
| --- | --- | --- |
| `if (c) {...}` | Một điều kiện | 0 hoặc 1 |
| `if (c) {...} else {...}` | Một điều kiện | Đúng 1 nếu điều kiện hoàn tất bình thường |
| `if (a) {...} else if (b) {...} else {...}` | Lần lượt `a` rồi `b` khi cần | Đúng 1 nếu có `else` và không có ngoại lệ |
| Hai câu `if` độc lập | Mỗi câu có điều kiện riêng | Có thể chạy cả hai |

Nếu một điều kiện đang được đánh giá ném ngoại lệ, chuỗi không hoàn tất theo đường đi bình thường; các bảng trên giả định điều kiện được đánh giá thành công.

## 3. Chương trình Java 17+ có thể biên dịch và chạy

Ví dụ này tập trung vào ba dạng cú pháp vừa học. Các kỹ thuật như `Boolean` nullable, `if` độc lập, khối lệnh và guard clause được thực hành riêng ở các bài tiếp theo.

Tạo tệp UTF-8 tên **`IfElseChainDemo.java`**:

~~~java
public class IfElseChainDemo {
    static String grade(int score) {
        if (score < 0 || score > 100) {
            return "invalid";
        }
        if (score >= 90) {
            return "A";
        } else if (score >= 75) {
            return "B";
        } else if (score >= 60) {
            return "C";
        } else {
            return "D";
        }
    }

    public static void main(String[] args) {
        System.out.println("== if ==");
        int stock = 3;
        if (stock > 0) {
            System.out.println("stock=available");
        }

        System.out.println("== if / else ==");
        int age = 20;
        if (age >= 18) {
            System.out.println("age=adult");
        } else {
            System.out.println("age=minor");
        }

        System.out.println("== else if ==");
        for (int score : new int[] {95, 75, 60, 59, -1, 101}) {
            System.out.println(score + "=" + grade(score));
        }
        System.out.println("end");
    }
}
~~~

Trong thư mục chứa tệp, dùng **JDK 17 trở lên** với PowerShell hoặc Bash:

~~~bash
javac -encoding UTF-8 IfElseChainDemo.java
java IfElseChainDemo
~~~

**Exact expected stdout** của lệnh `java IfElseChainDemo`:

~~~text
== if ==
stock=available
== if / else ==
age=adult
== else if ==
95=A
75=B
60=C
59=D
-1=invalid
101=invalid
end
~~~

Cả ba dạng đều có thể chạy độc lập. `grade` còn xác thực điểm ngoài miền trước khi phân loại, giúp đầu vào không hợp lệ không bị gán nhãn.

## 4. Điều kiện của `if`: boolean, không phải truthiness

Java chỉ chấp nhận biểu thức điều kiện có kiểu `boolean` hoặc `Boolean` có thể **unbox**. Số, chuỗi hay đối tượng không tự chuyển thành true/false:

~~~java
int count = 3;
if (count > 0) {
    System.out.println("has items");
}
// if (count) { } // Lỗi biên dịch: int không phải boolean.
~~~

Một biến `Boolean` có thể null; `if (nullableFlag)` sẽ ném `NullPointerException` khi unbox nếu giá trị null. Muốn chỉ chấp nhận true, dùng `Boolean.TRUE.equals(nullableFlag)`; với `String`, guard `s != null && !s.isBlank()` tránh gọi phương thức trên null.

Cẩn thận `if (flag = true)`: đây là **phép gán boolean**, có thể biên dịch và khiến nhánh chạy, không phải phép kiểm tra thuần túy. Chủ đề `Boolean` nullable, unboxing, biểu thức điều kiện và short-circuit được giải thích sâu ở bài chuyên `boolean/Boolean`.


## 5. Nhánh đúng đầu tiên thắng: sắp điều kiện có chủ đích

Với điểm từ 0 đến 100, phải kiểm tra **ngưỡng hẹp/cao** trước ngưỡng rộng/thấp:

~~~java
if (score >= 90) {
    level = "A";
} else if (score >= 75) {
    level = "B";
} else if (score >= 60) {
    level = "C";
} else {
    level = "D";
}
~~~

Nếu đảo thành `if (score >= 60) ... else if (score >= 90)`, điểm 95 rơi vào nhánh đầu và bị phân loại sai. Trong chương trình chính, `grade` còn kiểm tra `score < 0 || score > 100` trước khi xếp loại.

Khi lập quy tắc phân loại, hãy xác định miền hợp lệ, **nhánh ưu tiên** và giá trị tại đúng biên. Bài điều kiện biên sẽ xây dựng bảng điểm ngay dưới/đúng/trên các ngưỡng và phân tích nhánh bị che khuất.


## 6. Nhiều `if` độc lập có thể cùng chạy

~~~java
int value = 5;
if (value > 0) {
    System.out.println("positive");
}
if (value < 10) {
    System.out.println("below ten");
}
~~~

Hai điều kiện đều đúng nên cả hai dòng được in. Nếu đổi `if` thứ hai thành `else if`, nó **không được xét** sau khi nhánh đầu đã chạy. Dùng nhiều `if` khi cần nhiều hành động đồng thời; dùng một chuỗi `else if` khi chỉ chọn **một** hành động/nhãn.

Quy tắc này còn ảnh hưởng tới **việc điều kiện sau có được đánh giá không**, đặc biệt nếu chứa lời gọi phương thức có tác dụng phụ. Bài chuyên so sánh `if` độc lập và chuỗi loại trừ phân tích bảng hành vi, cảnh báo tích lũy và trace của hai cách viết.


## 7. Ngoặc nhọn xác định đúng thân nhánh

~~~java
boolean authorized = false;
if (authorized)
    System.out.println("authorized");
System.out.println("always"); // Luôn chạy.
~~~

Khi bỏ `{}`, chỉ **một câu lệnh** ngay sau điều kiện là thân `if`; mức thụt lề không thay đổi ngữ pháp. Với `if` lồng nhau, `else` gắn với `if` gần nhất chưa có `else`:

~~~java
if (outer) {
    if (inner) {
        System.out.println("inner true");
    } else {
        System.out.println("inner false");
    }
}
~~~

Dùng ngoặc nhọn ngay cả khi chỉ có một câu lệnh để bảo vệ phạm vi và tránh lỗi sau khi bổ sung code. Đừng đặt dấu `;` thừa sau `if (condition)`, vì `;` có thể trở thành **empty statement** làm thân `if` rỗng. Hai bài chuyên về khối lệnh và `dangling else` trình bày chi tiết phạm vi biến, các cách ghép `else` và ví dụ gây lỗi logic.


## 8. `return` sớm cho trường hợp đã kết luận

Một phương thức có thể **kết thúc ngay** khi đã biết kết quả, nhờ vậy không cần lồng mọi trường hợp vào nhiều nhánh:

~~~java
static String sign(int n) {
    if (n > 0) {
        return "positive";
    }
    if (n < 0) {
        return "negative";
    }
    return "zero";
}
~~~

Hai `if` ở đây không cần `else if` vì `return` đã kết thúc phương thức ở nhánh được chọn. Tuy nhiên, nếu nhánh trước **không `return`/`throw`**, thay `else if` bằng `if` độc lập có thể đổi hành vi. Dùng guard clause khi cần loại trường hợp không hợp lệ hoặc kết thúc sớm trước đường xử lý chính; bài guard clause đi sâu vào thứ tự, ngoại lệ, vòng lặp và dọn dẹp tài nguyên.


## 9. Các lỗi thường gặp

| Sai lầm | Cách hiểu đúng |
| --- | --- |
| “`if (1)` hợp lệ vì 1 nghĩa là true.” | Java yêu cầu `boolean`, không có truthiness cho số |
| “`else` bắt buộc sau mọi `if`.” | `else` là tùy chọn |
| “Mọi `else if` đều được chạy để tìm tất cả nhánh đúng.” | Chỉ kiểm tra đến **nhánh true đầu tiên** |
| “Hai `if` liên tiếp giống `if / else if`.” | Hai `if` độc lập có thể cùng chạy |
| “Thứ tự điều kiện không quan trọng.” | Điều kiện rộng đặt trước có thể che điều kiện cụ thể |
| “`if (flag = true)` tương đương kiểm tra flag.” | Đó là phép gán true, có thể tạo bug |
| “`Boolean null` tự hiểu là false.” | Unboxing null gây `NullPointerException` |
| “Nếu bỏ ngoặc nhọn, mọi dòng thụt đầu dòng đều thuộc `if`.” | Chỉ **một câu lệnh** ngay sau điều kiện |
| “`else` luôn gắn với `if` ngoài cùng.” | Gắn với `if` gần nhất chưa có `else` |
| “`if (condition);` có khối điều kiện phía sau.” | Dấu `;` làm thân `if` trở thành câu lệnh rỗng |

## 10. Bài tập tự kiểm tra

1. `int x = 7; if (x > 5) {...} else {...}` chạy nhánh nào?  
   *Đáp án:* Nhánh `if`.
2. `int x = 5; if (x > 0) {...} if (x < 10) {...}` có thể chạy bao nhiêu nhánh?  
   *Đáp án:* Cả hai.
3. Với `score = 95`, vì sao `if (score >= 60) ... else if (score >= 90) ...` sai ý định phân loại?  
   *Đáp án:* Nhánh `>= 60` đã đúng nên `>= 90` không được xét.
4. `if (0)` có biên dịch không?  
   *Đáp án:* Không; điều kiện phải có kiểu boolean.
5. `Boolean b = null; if (b) {...}` có hành vi gì khi chạy?  
   *Đáp án:* Ném `NullPointerException` do unboxing.
6. `if (n > 0);` có tác dụng gì?  
   *Đáp án:* Điều kiện được kiểm tra, nhưng thân là **câu lệnh rỗng**.
7. Với hai `if` lồng không có ngoặc nhọn, `else` gắn với nhánh nào?  
   *Đáp án:* `if` gần nhất còn chưa có `else`.
8. Chuỗi `else if` có thể kết thúc không có `else` không?  
   *Đáp án:* Có; nếu không nhánh nào đúng thì không khối nào được chạy.

## Checklist

- [ ] Viết đúng `if (booleanCondition) { ... }`.
- [ ] Biết `else` là tùy chọn và `else if` nối thêm những trường hợp theo thứ tự.
- [ ] Hiểu **chỉ nhánh đúng đầu tiên** trong chuỗi được chạy.
- [ ] Phân biệt nhiều `if` độc lập với chuỗi `else if`.
- [ ] Kiểm tra kiểu `boolean`, wrapper null và các điều kiện ngắn mạch.
- [ ] Đặt điều kiện cụ thể trước điều kiện rộng khi có chồng lấp.
- [ ] Luôn ưu tiên dấu ngoặc nhọn để tránh lỗi `dangling else` và thụt dòng gây hiểu nhầm.
- [ ] Không vô tình thêm `;` ngay sau `if (...)` hoặc gán `=` thay cho kiểm tra.

**Kết luận:** `if`, `else` và chuỗi `else if` là công cụ rẽ nhánh cốt lõi của Java. Đọc đúng **điều kiện boolean**, **thứ tự đánh giá**, **phạm vi ngoặc nhọn** và **mối quan hệ giữa các nhánh** giúp tránh lỗi logic mà trình biên dịch không nhất thiết phát hiện.
