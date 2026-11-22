# `switch` dạng dấu hai chấm và cơ chế rơi tiếp xuống nhánh sau — Java 17+

Trong Java, một `switch` dạng **dấu hai chấm** (*colon-style switch statement*) đặt các nhãn `case ...:` và `default:` trước những câu lệnh sẽ chạy. Điểm cần nhớ là **nhãn `case` không tự kết thúc một nhánh**: khi đã bắt đầu từ nhãn khớp, Java tiếp tục chạy các câu lệnh bên dưới, kể cả qua những nhãn `case` khác, cho đến khi gặp `break`, `return`, `throw` hoặc kết thúc khối `switch`.

Hiện tượng này gọi là **fall-through** (*rơi tiếp xuống nhánh sau*).

~~~java
int code = 1;
switch (code) {
    case 1:
        System.out.println("one");
    case 2:
        System.out.println("two");
        break;
    default:
        System.out.println("other");
}
~~~

Với `code = 1`, chương trình in **cả `one` và `two`**. Lý do: không có `break` sau `case 1:`, nên sau khi in `one`, luồng xử lý tiếp tục tới câu lệnh bên dưới `case 2:` mà **không kiểm tra lại điều kiện case 2**.

## 1. Cú pháp `switch` dạng dấu hai chấm

~~~java
switch (expression) {
    case CONSTANT_1:
        // Các câu lệnh cho nhãn thứ nhất
        break;
    case CONSTANT_2:
        // Các câu lệnh cho nhãn thứ hai
        break;
    default:
        // Trường hợp không nhãn case nào khớp
}
~~~

Quy tắc thực thi:

1. Java đánh giá **biểu thức chọn** `expression` đúng một lần cho lần thực hiện `switch` đó.
2. Tìm **nhãn `case` tương ứng** với giá trị, hoặc chuyển tới `default` nếu không nhãn nào khớp.
3. Bắt đầu chạy **từ vị trí nhãn đã chọn**.
4. Tiếp tục lần lượt qua các câu lệnh bên dưới; những nhãn xuất hiện tiếp theo **không phải hàng rào tự động**.
5. `break;` thông thường thoát khỏi `switch` gần nhất; câu lệnh phía sau khối `switch` được thực hiện tiếp.

**`default` không bắt buộc.** Nếu không có `case` khớp và không có `default`, Java bỏ qua toàn bộ thân `switch`.

### Bảng hành vi điển hình

~~~java
switch (n) {
    case 1:
        System.out.println("A");
    case 2:
        System.out.println("B");
    case 3:
        System.out.println("C");
        break;
    default:
        System.out.println("D");
}
~~~

| Giá trị `n` | Những dòng được in từ `switch` | Giải thích |
| --- | --- | --- |
| 1 | A, B, C | Rơi qua case 2 và case 3 trước khi gặp `break` |
| 2 | B, C | Rơi qua case 3 |
| 3 | C | Dừng tại `break` |
| 9 | D | Không case nào khớp; chạy `default` |

Không nên suy luận rằng chỉ vì biểu thức chọn bằng 1 thì “chỉ câu lệnh của case 1 được chạy”. Trong dạng dấu hai chấm, **`break` mới tạo ranh giới dừng thực thi**.

## 2. Chương trình Java 17+ hoàn chỉnh

Tạo tệp UTF-8 tên **`SwitchColonDemo.java`**:

~~~java
public class SwitchColonDemo {
    static void fallThrough(int value) {
        System.out.println("input=" + value);
        switch (value) {
            case 1:
                System.out.println("one");
            case 2:
                System.out.println("two");
            case 3:
                System.out.println("three");
                break;
            default:
                System.out.println("other");
        }
        System.out.println("after");
    }

    static void withBreak(int value) {
        System.out.println("break-input=" + value);
        switch (value) {
            case 1:
                System.out.println("break=one");
                break;
            case 2:
                System.out.println("break=two");
                break;
            default:
                System.out.println("break=other");
        }
        System.out.println("break-after");
    }

    static String season(int month) {
        switch (month) {
            case 12:
            case 1:
            case 2:
                return "winter";
            case 3:
            case 4:
            case 5:
                return "spring";
            case 6:
            case 7:
            case 8:
                return "summer";
            case 9:
            case 10:
            case 11:
                return "autumn";
            default:
                return "invalid";
        }
    }

    static void defaultInMiddle(int value) {
        System.out.println("middle-input=" + value);
        switch (value) {
            case 1:
                System.out.println("case-one");
                break;
            default:
                System.out.println("default");
            case 2:
                System.out.println("case-two");
                break;
            case 3:
                System.out.println("case-three");
                break;
        }
    }

    static void continueInLoop() {
        for (int i = 0; i < 3; i++) {
            switch (i) {
                case 0:
                    System.out.println("loop-zero");
                    continue;
                case 1:
                    System.out.println("loop-one");
                    break;
                default:
                    System.out.println("loop-two");
            }
            System.out.println("loop-after=" + i);
        }
    }

    static void localScopes(int option) {
        switch (option) {
            case 1: {
                int local = 10;
                System.out.println("scope=" + local);
                break;
            }
            case 2: {
                int local = 20;
                System.out.println("scope=" + local);
                break;
            }
            default:
                System.out.println("scope=other");
        }
    }

    static String state(String code) {
        if (code == null) {
            return "null";
        }
        switch (code) {
            case "ON":
                return "enabled";
            case "OFF":
                return "disabled";
            default:
                return "unknown";
        }
    }

    public static void main(String[] args) {
        System.out.println("== fall-through ==");
        fallThrough(1);
        fallThrough(2);
        fallThrough(3);
        fallThrough(9);

        System.out.println("== break ==");
        withBreak(1);
        withBreak(2);
        withBreak(9);

        System.out.println("== grouped labels ==");
        System.out.println("season1=" + season(1));
        System.out.println("season4=" + season(4));
        System.out.println("season8=" + season(8));
        System.out.println("season10=" + season(10));
        System.out.println("season13=" + season(13));

        System.out.println("== default in middle ==");
        defaultInMiddle(9);
        defaultInMiddle(2);
        defaultInMiddle(1);
        defaultInMiddle(3);

        System.out.println("== switch inside loop ==");
        continueInLoop();

        System.out.println("== scoped cases ==");
        localScopes(1);
        localScopes(2);
        localScopes(7);

        System.out.println("== String selectors ==");
        System.out.println("stateON=" + state("ON"));
        System.out.println("stateNull=" + state(null));
        System.out.println("stateOther=" + state("UNKNOWN"));

        System.out.println("== switch expression with colon ==");
        String result = switch (2) {
            case 1:
                yield "one";
            case 2:
                yield "two";
            default:
                yield "other";
        };
        System.out.println("yieldResult=" + result);
    }
}
~~~

Dùng **JDK 17 trở lên**. Mở PowerShell (Windows) hoặc Bash (Linux/macOS) tại thư mục chứa file:

~~~bash
java -version
javac -version
javac -encoding UTF-8 SwitchColonDemo.java
java SwitchColonDemo
~~~

**Exact expected stdout** của riêng lệnh `java SwitchColonDemo`:

~~~text
== fall-through ==
input=1
one
two
three
after
input=2
two
three
after
input=3
three
after
input=9
other
after
== break ==
break-input=1
break=one
break-after
break-input=2
break=two
break-after
break-input=9
break=other
break-after
== grouped labels ==
season1=winter
season4=spring
season8=summer
season10=autumn
season13=invalid
== default in middle ==
middle-input=9
default
case-two
middle-input=2
case-two
middle-input=1
case-one
middle-input=3
case-three
== switch inside loop ==
loop-zero
loop-one
loop-after=1
loop-two
loop-after=2
== scoped cases ==
scope=10
scope=20
scope=other
== String selectors ==
stateON=enabled
stateNull=null
stateOther=unknown
== switch expression with colon ==
yieldResult=two
~~~

Hai lệnh `java -version` và `javac -version` cho thông tin phụ thuộc phiên bản JDK cài đặt và không nằm trong expected stdout cố định.

## 3. Điểm dừng của luồng fall-through

Nhãn `case:` không tạo ranh giới dừng; `break;` thoát switch gần nhất. `return` rời phương thức, còn `throw` chuyển điều khiển sang xử lý ngoại lệ. Khi switch nằm trong vòng lặp, `continue` tác động lên vòng lặp phù hợp. Các khác biệt về lệnh thoát, switch lồng nhau và vòng lặp được thực hành chi tiết ở bài kế tiếp.

## 4. Rơi tiếp có chủ ý: gom nhiều nhãn `case`

Một ứng dụng dễ hiểu của fall-through là **nhiều nhãn dùng chung một thân lệnh**:

~~~java
switch (month) {
    case 12:
    case 1:
    case 2:
        System.out.println("winter");
        break;
    case 3:
    case 4:
    case 5:
        System.out.println("spring");
        break;
    default:
        System.out.println("other");
}
~~~

Với `month == 12`, Java vào nhãn `case 12:`, đi qua `case 1:`, `case 2:` mà không có câu lệnh nào ở giữa, rồi in `winter`. Đây là **fall-through có chủ ý**, không phải rủi ro bị chạy các hành động khác nhau.

Trong Java 17, các nhãn có cùng thân cũng có thể viết theo dạng danh sách:

~~~java
switch (month) {
    case 12, 1, 2:
        System.out.println("winter");
        break;
    default:
        System.out.println("other");
}
~~~

Dạng dấu hai chấm vẫn cần `break` nếu muốn dừng sau nhóm. Khi nhiệm vụ chỉ là chọn một giá trị và không cần fall-through, `case ... ->` thường biểu đạt ý định rõ hơn.

## 5. `default` không bắt buộc đứng cuối

`default:` là điểm bắt đầu khi **không nhãn `case` nào khớp**, nhưng vị trí viết của nó trong khối `switch` có thể không ở cuối.

~~~java
switch (value) {
    case 1:
        System.out.println("one");
        break;
    default:
        System.out.println("default");
    case 2:
        System.out.println("two");
        break;
}
~~~

Nếu `value == 9`, Java bắt đầu ở `default`, in `default` rồi **rơi tiếp** xuống `case 2:` để in `two` trước khi gặp `break`. Nếu `value == 2`, Java bắt đầu **trực tiếp tại `case 2:`** và chỉ in `two`.

| `value` | Kết quả |
| --- | --- |
| 1 | `one` |
| 2 | `two` |
| 9 | `default`, rồi `two` |

**Khuyến nghị:** thông thường đặt `default` cuối và kết thúc rõ ràng từng nhánh giúp tránh gây nhầm lẫn; đặt `default` ở giữa là hợp lệ nhưng phải xét khả năng fall-through.

## 6. Phạm vi biến cục bộ trong các nhãn `case`

Một nhãn `case` **không tự tạo một scope mới**. Các khai báo biến cục bộ ở những case khác nhau trong cùng khối `switch` có thể xung đột tên, và việc sử dụng trước khi được gán có thể dẫn đến lỗi **definite assignment**.

Cách rõ ràng là tạo một khối riêng cho từng case:

~~~java
switch (option) {
    case 1: {
        int result = 10;
        System.out.println(result);
        break;
    }
    case 2: {
        int result = 20; // Khai báo lại hợp lệ vì ở block khác.
        System.out.println(result);
        break;
    }
    default: {
        System.out.println("unknown");
    }
}
~~~

Đừng nhầm `case:` với khối `{...}`: nhãn là điểm vào của luồng điều khiển; dấu ngoặc nhọn mới tạo phạm vi block rõ ràng. Cách viết có `{ }` còn giúp tránh vô tình đọc một biến chưa được khởi tạo ở đường đi khác.

## 7. Ràng buộc selector và nhãn

Trong Java 17 tiêu chuẩn, switch hỗ trợ `byte`, `short`, `char`, `int` và wrapper tương ứng, `String`, hoặc enum. Nhãn hằng phải hợp lệ ở compile time, tương thích miền giá trị và không trùng. Selector tham chiếu `null` gây `NullPointerException`, không chạy `default`. Các bảng kiểu selector và chính sách null có bài chuyên biệt; ở đây ta dùng chúng làm điều kiện đầu vào của cơ chế dấu hai chấm.

## 8. Đối chiếu nhanh với `case ... ->`

Dạng `case ...:` có thể fall-through và thường cần `break` sau phần thân. Dạng `case ... ->` thực hiện một rule, không chạy sang rule sau; có thể nhóm nhiều giá trị bằng `case 1, 2 -> ...`. Không trộn hai dạng trong một switch. Bài mũi tên giải thích riêng cách dùng block và scope.

## 9. Switch ở trong vòng lặp

Nếu switch nằm trong `for`, thiếu `break` vẫn gây fall-through **bên trong switch**. Trái lại, `continue;` chuyển tới lần lặp kế tiếp và bỏ qua phần còn lại của thân vòng lặp, không nhảy sang nhãn case khác. Bài `break` có trace cụ thể về tương tác giữa switch, vòng lặp và các cấu trúc lồng nhau.

## 10. Lỗi thường gặp

| Hiểu nhầm | Cách hiểu đúng |
| --- | --- |
| “Mỗi `case:` tự kết thúc như `if/else if`.” | Không; thiếu `break` có thể rơi tiếp |
| “Java kiểm tra lại điều kiện ở mỗi nhãn sau.” | Không; đã nhảy tới nhãn khớp thì chạy tuần tự |
| “`break` trong switch luôn kết thúc phương thức.” | Chỉ thoát switch gần nhất |
| “`default` đứng giữa sẽ luôn dừng trước case sau.” | Vẫn có thể fall-through |
| “`case 1: case 2:` là lỗi.” | Hợp lệ và dùng để gom nhãn |
| “Hai case có thể khai báo cùng tên biến vì case tạo scope.” | Case không tự tạo block; cần `{ }` khi thích hợp |
| “`switch(null)` tự động chạy `default`.” | Thông thường ném `NullPointerException` trong Java 17 |
| “`case x ->` cũng có fall-through nếu không có `break`.” | Dạng rule `->` không rơi tiếp |
| “`continue` trong switch chuyển sang case tiếp theo.” | Nó chuyển sang lần lặp kế khi switch nằm trong vòng lặp |
| “Trong switch expression, `break` tạo giá trị trả về.” | Dùng `yield` hoặc switch rule thích hợp |

## 11. Bài tập tự kiểm tra

1. `switch(1) { case 1: print("A"); case 2: print("B"); break; }` có thể in gì?  
   *Đáp án:* `AB` theo thứ tự, vì thiếu `break` sau case 1.
2. Nếu thêm `break;` ngay sau `print("A")` thì còn in `B` không?  
   *Đáp án:* Không.
3. Với `case 1: case 2: System.out.println("yes"); break;`, giá trị 1 và 2 có chạy chung phần thân không?  
   *Đáp án:* Có.
4. `default` có bắt buộc đặt cuối khối `switch` không?  
   *Đáp án:* Không; nhưng đặt giữa cần chú ý fall-through.
5. Trong switch có `default: print("D"); case 2: print("B"); break;`, chọn giá trị 9 cho gì?  
   *Đáp án:* In `D` rồi `B`.
6. Dùng `break` trong switch nằm trong vòng `for` có kết thúc luôn vòng lặp không?  
   *Đáp án:* Không; chỉ thoát switch gần nhất.
7. Vì sao nên dùng `{ }` cho mỗi case có khai báo biến cục bộ?  
   *Đáp án:* Tạo scope rõ ràng và tránh xung đột tên/khởi tạo.
8. `switch` dạng mũi tên `case 1 -> ...` có rơi qua case 2 không?  
   *Đáp án:* Không.
9. Nếu selector là `String null` trong Java 17 thông thường, `default` có xử lý nó không?  
   *Đáp án:* Không; phải xử lý null trước để tránh `NullPointerException`.

## Checklist

- [ ] Phân biệt `case ...:` (dạng dấu hai chấm) với `case ... ->` (dạng mũi tên).
- [ ] Hiểu điểm vào `case` và việc **rơi tiếp** qua nhãn sau nếu không dừng.
- [ ] Đặt `break` khi mỗi nhánh cần độc lập; ghi rõ ý định khi cố tình fall-through.
- [ ] Biết gom nhiều nhãn dùng chung phần thân.
- [ ] Không mặc định `default` tạo ranh giới dừng.
- [ ] Dùng khối `{ }` khi khai báo biến cục bộ trong case.
- [ ] Phân biệt `break`, `continue`, `return` và `yield`.
- [ ] Xử lý null selector trước khi dùng `switch` Java 17 thông thường.

**Kết luận:** Điểm khác biệt lớn nhất của `switch` dạng dấu hai chấm là **fall-through**: khi đã vào một nhãn, Java chạy tiếp các câu lệnh phía dưới cho đến khi bị ngắt hoặc hết khối. Dùng `break` có chủ đích, gom nhãn khi cần chung hành vi và cân nhắc dạng `->` để giảm nguy cơ rơi tiếp ngoài ý muốn.
