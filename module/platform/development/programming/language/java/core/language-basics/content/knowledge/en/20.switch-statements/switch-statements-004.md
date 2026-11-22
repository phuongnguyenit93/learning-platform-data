# `break` để kết thúc switch statement — Java 17+

## 1. `break` làm gì trong `switch`?

Trong **switch statement** dùng cú pháp truyền thống `case ...:`, lệnh `break;` **kết thúc ngay switch gần nhất đang bao quanh nó**. Chương trình tiếp tục từ câu lệnh **sau** switch, không phải sau nhãn `case` kế tiếp.

~~~java
int choice = 2;
switch (choice) {
    case 1:
        System.out.println("One");
        break;
    case 2:
        System.out.println("Two");
        break;
    default:
        System.out.println("Other");
}
System.out.println("After switch");
~~~

**Exact expected stdout:**

~~~text
Two
After switch
~~~

Nếu thiếu `break;` sau `case 2`, thực thi có thể **rơi xuống nhánh `default`**, dù `choice` không khớp `default`. Đây là *fall-through*, nguồn lỗi thường gặp trong switch dạng dấu hai chấm.

Sau bài, bạn cần phân biệt `break` với `return` và `continue`, biết `break` thoát switch nào khi lồng nhau, khi nào có thể bỏ `break`, và cách dùng `case ... ->` trong Java 17 để tránh fall-through.

## 2. Luồng chạy switch dạng dấu hai chấm

~~~mermaid
flowchart TD
    A["Đánh giá selector"] --> B{"Nhãn case khớp?"}
    B -- "Có" --> C["Bắt đầu chạy từ case khớp"]
    B -- "Không" --> D{"Có default?"}
    D -- "Không" --> H["Sau switch"]
    D -- "Có" --> E["Bắt đầu chạy từ default"]
    C --> F{"Gặp break thoát switch?"}
    E --> F
    F -- "Có" --> H
    F -- "Không" --> G["Tiếp tục câu lệnh và có thể fall-through"]
    G --> F
~~~

Các bước quan trọng:

1. Selector được đánh giá.
2. Java xác định nhãn `case` khớp hoặc `default` nếu không có `case` khớp.
3. Với dạng `case:`, thực thi bắt đầu tại nhãn đã chọn và **tiến theo thứ tự câu lệnh**, không tự dừng ở cuối nhóm lệnh của nhãn.
4. Gặp `break;` không có nhãn thì thoát **switch hoặc vòng lặp gần nhất bao quanh**.
5. Nếu chạy tới hết switch mà không gặp `break`, chương trình cũng ra khỏi switch theo cách bình thường.

`break` **không phải bắt buộc về cú pháp ở mọi `case`**. Nó quan trọng khi cần ngăn chạy tiếp sang các nhãn phía sau.

## 3. Ví dụ thiếu `break`

~~~java
switch (2) {
    case 2: System.out.println("Two");
    case 3: System.out.println("Three"); break;
    default: System.out.println("Other");
}
~~~

Kết quả lần lượt là `Two`, `Three`: sau khi chọn case 2, Java chạy tiếp đến `break` mà không so lại nhãn case 3. Trọng tâm ở đây là vị trí đặt lệnh thoát; bài dạng dấu hai chấm đã mô tả chi tiết mọi đường fall-through.

## 4. Đặt `break` ở đúng vị trí

Nếu chỉ muốn xử lý một mã, đặt `break` sau các câu lệnh của mã đó:

~~~java
switch (code) {
    case 1:
        handleOne();
        break;
    case 2:
        handleTwo();
        break;
    default:
        handleOther();
}
~~~

Ví dụ trên các hàm `handleOne`, `handleTwo`, `handleOther` là những hàm nghiệp vụ do bạn tự định nghĩa; đoạn này minh họa **vị trí `break`**, không phải một chương trình độc lập.

Có thể viết cả khối để giữ biến cục bộ theo phạm vi:

~~~java
switch (code) {
    case 1: {
        String message = "one";
        System.out.println(message);
        break;
    }
    case 2: {
        String message = "two";
        System.out.println(message);
        break;
    }
    default:
        System.out.println("other");
}
~~~

Ngoặc `{ ... }` **không làm `break` chỉ thoát khối ngoặc**: `break;` vẫn kết thúc switch bao quanh.

**Ghi chú:** nếu một `case` đã kết thúc bằng `return` hoặc `throw`, không cần đặt thêm `break` phía sau — dòng `break` đó có thể thành *unreachable statement* và gây lỗi biên dịch.

## 5. Dừng sau thân chung của nhiều nhãn

~~~java
switch (day) {
    case 6:
    case 7:
        System.out.println("Weekend");
        break;
    default:
        System.out.println("Weekday");
}
~~~

Hai nhãn liên tiếp cố ý dùng chung thân lệnh; `break` nằm **sau thân chung**. Nếu một nhánh thực hiện hành động riêng rồi rơi tiếp sang nhánh khác, cần xác nhận đó là chủ ý và ghi chú rõ.

## 6. `default` có cần `break`?

Nếu `default` là nhãn cuối và switch kết thúc ngay sau thân của nó thì không cần `break`. Khi `default` nằm giữa các `case:`, thiếu `break` vẫn gây fall-through. Hãy quyết định dựa trên **đường thực thi**, không dựa vào tên nhãn. Bài nhãn `case/default` có ví dụ đối chiếu vị trí.

## 7. `break` khác `return` và `continue`

| Câu lệnh | Hiệu ứng chính | Sau khi thực hiện |
|---|---|---|
| `break;` | Thoát switch hoặc vòng lặp gần nhất | Tiếp tục sau cấu trúc đã thoát |
| `return;` / `return value;` | Thoát **toàn bộ phương thức** | Không chạy câu lệnh sau switch trong cùng method |
| `continue;` | Bỏ phần còn lại của **lần lặp**, chỉ hợp lệ trong vòng lặp | Chuyển sang bước cập nhật/điều kiện của vòng lặp |
| `throw ...;` | Ném ngoại lệ | Chuyển điều khiển theo cơ chế exception |

Ví dụ `break` chỉ kết thúc switch:

~~~java
static void printChoice(int choice) {
    switch (choice) {
        case 1:
            System.out.println("one");
            break;
        default:
            System.out.println("other");
    }
    System.out.println("method continues");
}
~~~

Ví dụ `return` kết thúc method:

~~~java
static String label(int choice) {
    switch (choice) {
        case 1:
            return "ONE";
        default:
            return "OTHER";
    }
}
~~~

**Không thể thay máy móc `break` bằng `return`**: nếu phương thức còn xử lý sau switch, `return` sẽ bỏ qua phần xử lý đó.

`continue;` **không thay thế `break;` trong switch độc lập**; nó cần có vòng lặp bao quanh. Khi switch ở bên trong vòng lặp, `continue;` áp dụng cho vòng lặp ấy.

## 8. Switch bên trong vòng lặp: `break` không thoát vòng lặp

~~~java
for (int i = 0; i < 3; i++) {
    switch (i) {
        case 1:
            System.out.println("case one");
            break; // Thoát switch, KHÔNG thoát for.
        default:
            System.out.println("other " + i);
    }
    System.out.println("after switch " + i);
}
~~~

**Exact expected stdout:**

~~~text
other 0
after switch 0
case one
after switch 1
other 2
after switch 2
~~~

Khi `i == 1`, `break;` kết thúc switch, sau đó `System.out.println("after switch " + i)` vẫn chạy và vòng `for` tiếp tục.

Nếu cần thoát chính vòng lặp, đặt điều kiện `break` ở **ngoài switch**, hoặc dùng **labeled break** có chủ đích:

~~~java
outer:
for (int i = 0; i < 5; i++) {
    switch (i) {
        case 2:
            break outer; // Thoát hẳn vòng lặp có nhãn outer.
        default:
            System.out.println(i);
    }
}
~~~

**Exact expected stdout:**

~~~text
0
1
~~~

Sử dụng nhãn khi thực sự cần thoát một cấu trúc bao ngoài; không lạm dụng để thay cho việc thiết kế vòng lặp rõ ràng.

## 9. Switch lồng nhau: `break` thoát switch gần nhất

~~~java
int outer = 1;
int inner = 7;

switch (outer) {
    case 1:
        switch (inner) {
            case 7:
                System.out.println("inner seven");
                break; // Chỉ thoát switch(inner).
            default:
                System.out.println("inner other");
        }
        System.out.println("after inner");
        break; // Thoát switch(outer).
    default:
        System.out.println("outer other");
}
~~~

**Exact expected stdout:**

~~~text
inner seven
after inner
~~~

Nếu bỏ `break` của switch ngoài, có thể tiếp tục fall-through sang nhãn phía sau của switch ngoài. **Mỗi switch có luồng điều khiển của riêng nó**.

## 10. Đối chiếu với nhánh mũi tên

Trong switch statement Java 17, `case 1 -> action();` không cần `break` để chống fall-through. Nếu nhánh cần nhiều lệnh thì dùng block `{ ... }`. Khi sửa switch dạng `case:` cũ, chỉ bỏ `break` khi đã chủ đích chuyển cú pháp sang rule mũi tên.

## 11. `break` khác `yield`

`break;` thoát switch statement hoặc vòng lặp thích hợp, không tạo giá trị. Switch **expression** với block `case 2 -> { ... }` cần `yield value;` trên đường đi bình thường. Không thay `yield` bằng `break` hoặc `break value`. Những đường đi có điều kiện, kết quả và ngoại lệ thuộc bài `yield`.

## 12. Ví dụ Java 17 hoàn chỉnh, chạy bằng CLI

Tạo file đúng tên **`SwitchBreakDemo.java`**:

~~~java
public final class SwitchBreakDemo {
    private SwitchBreakDemo() {}

    static String classify(int code) {
        String result;
        switch (code) {
            case 1:
                result = "ONE";
                break;
            case 2:
            case 3:
                result = "TWO_OR_THREE";
                break;
            default:
                result = "OTHER";
        }
        return result;
    }

    static void fallThrough(int code) {
        switch (code) {
            case 1:
                System.out.println("fall:one");
                // Fall through intentionally.
            case 2:
                System.out.println("fall:two");
                break;
            default:
                System.out.println("fall:other");
        }
        System.out.println("fall:after-switch");
    }

    static void arrow(int code) {
        switch (code) {
            case 1 -> System.out.println("arrow:one");
            case 2, 3 -> System.out.println("arrow:two-or-three");
            default -> System.out.println("arrow:other");
        }
    }

    static String withReturn(int code) {
        switch (code) {
            case 0:
                return "ZERO";
            default:
                return "NONZERO";
        }
    }

    static String nested(int outer, int inner) {
        String result;
        switch (outer) {
            case 1:
                result = "outer-one";
                switch (inner) {
                    case 7:
                        result = "inner-seven";
                        break; // Only exits the inner switch.
                    default:
                        result = "inner-other";
                }
                result += "-after-inner";
                break; // Exits the outer switch.
            case 2:
                result = "outer-two";
                break;
            default:
                result = "outer-other";
        }
        return result;
    }

    static void loopWithSwitch() {
        for (int i = 0; i < 3; i++) {
            switch (i) {
                case 1:
                    System.out.println("loop:case-one");
                    break;
                default:
                    System.out.println("loop:other-" + i);
            }
            System.out.println("loop:after-switch-" + i);
        }
    }

    static void labeledBreak() {
        outer:
        for (int i = 0; i < 5; i++) {
            switch (i) {
                case 2:
                    break outer;
                default:
                    System.out.println("labeled:" + i);
            }
        }
        System.out.println("labeled:after-loop");
    }

    static void blockBreak(int code) {
        switch (code) {
            case 1: {
                String message = "block:one";
                System.out.println(message);
                break;
            }
            default:
                System.out.println("block:other");
        }
        System.out.println("block:after-switch");
    }

    public static void main(String[] args) {
        System.out.println("classify 1=" + classify(1));
        System.out.println("classify 2=" + classify(2));
        System.out.println("classify 3=" + classify(3));
        System.out.println("classify 9=" + classify(9));

        fallThrough(1);
        fallThrough(2);
        arrow(1);
        arrow(3);
        arrow(9);

        System.out.println("return 0=" + withReturn(0));
        System.out.println("return 8=" + withReturn(8));

        System.out.println("nested 1/7=" + nested(1, 7));
        System.out.println("nested 1/8=" + nested(1, 8));
        System.out.println("nested 2/7=" + nested(2, 7));

        loopWithSwitch();
        labeledBreak();
        blockBreak(1);

        int code = 2;
        String expression = switch (code) {
            case 1 -> "ONE";
            case 2 -> {
                String value = "TWO";
                yield value;
            }
            default -> "OTHER";
        };
        System.out.println("expression=" + expression);
    }
}
~~~

**Yêu cầu:** JDK 17 trở lên, terminal tại thư mục chứa `SwitchBreakDemo.java`; không cần Maven/Gradle, không sử dụng tính năng preview hoặc thư viện ngoài JDK.

**Bash (Linux/macOS):**

~~~bash
javac --release 17 -encoding UTF-8 SwitchBreakDemo.java
java -cp . SwitchBreakDemo
~~~

**PowerShell (Windows):**

~~~powershell
javac --release 17 -encoding UTF-8 .\SwitchBreakDemo.java
java -cp . SwitchBreakDemo
~~~

**Exact expected stdout:**

~~~text
classify 1=ONE
classify 2=TWO_OR_THREE
classify 3=TWO_OR_THREE
classify 9=OTHER
fall:one
fall:two
fall:after-switch
fall:two
fall:after-switch
arrow:one
arrow:two-or-three
arrow:other
return 0=ZERO
return 8=NONZERO
nested 1/7=inner-seven-after-inner
nested 1/8=inner-other-after-inner
nested 2/7=outer-two
loop:other-0
loop:after-switch-0
loop:case-one
loop:after-switch-1
loop:other-2
loop:after-switch-2
labeled:0
labeled:1
labeled:after-loop
block:one
block:after-switch
expression=TWO
~~~

### Đọc kết quả

- `classify` dùng `break` để bảo đảm mỗi mã chỉ được gán một kết quả.
- `fallThrough(1)` in cả `fall:one` và `fall:two` theo **chủ ý** thiếu `break`; `fallThrough(2)` chỉ in `fall:two`.
- `arrow` không fall-through, dù không có `break;`.
- `withReturn` trả trực tiếp từ phương thức, không chạy thêm câu lệnh trong method.
- `nested` cho thấy `break` của switch trong không tự thoát switch ngoài.
- `loopWithSwitch` vẫn chạy `for` sau khi switch dùng `break;`.
- `labeledBreak` thoát vòng `for` được gắn nhãn `outer`.
- `blockBreak` xác nhận `break` rời switch ngay cả khi nằm trong `case` có `{ ... }`.
- `yield` cung cấp `"TWO"` cho switch expression.

## 13. Bảng lỗi thường gặp

| Sai lầm | Hậu quả | Cách xử lý |
|---|---|---|
| Quên `break` sau `case:` | Chạy tiếp câu lệnh của case sau | Thêm `break;` hoặc dùng `->` |
| Nghĩ Java kiểm tra lại case sau fall-through | Diễn giải sai kết quả | Hiểu rằng thực thi chỉ tiếp tục tuần tự |
| Nghĩ `default` luôn tự kết thúc switch | Default đặt giữa vẫn fall-through | Thêm `break` nếu cần |
| Đặt `break` ngay sau `return` | Code không thể đạt tới, có thể lỗi biên dịch | Chọn một cơ chế thoát đúng mục đích |
| Dùng `break` rồi mong thoát cả phương thức | Method vẫn tiếp tục sau switch | Dùng `return` nếu muốn thoát method |
| Dùng `break` trong switch bên trong `for` để kết thúc `for` | Chỉ thoát switch | Đặt break ngoài switch hoặc dùng nhãn |
| Nghĩ `break` trong switch con thoát cả switch cha | Chỉ thoát cấu trúc gần nhất | Quản lý riêng từng mức hoặc dùng return khi phù hợp |
| Dùng `continue` trong switch không có vòng lặp | Không hợp lệ | `break` để thoát switch |
| Đặt `break;` để trả giá trị của switch expression | Không cung cấp kết quả | Dùng `yield` cho nhánh có block |
| Trộn cú pháp `case:` với `case ->` trong cùng switch | Lỗi biên dịch | Chọn một kiểu nhãn nhất quán |
| Dùng fall-through cho nhiều nhánh giống nhau nhưng không ghi chú | Người đọc tưởng thiếu break | Dùng nhãn rỗng liên tiếp hoặc `case 1, 2 ->` |

## 14. Bài tập có đáp án

### Bài A — dự đoán fall-through

~~~java
int x = 1;
switch (x) {
    case 1:
        System.out.println("A");
    case 2:
        System.out.println("B");
        break;
    default:
        System.out.println("C");
}
~~~

**Đáp án:**

~~~text
A
B
~~~

`case 1` khớp nhưng không có `break`, nên chạy tiếp lệnh của `case 2`.

### Bài B — chỉ chạy case đã chọn

Viết lại ví dụ trên để `x == 1` chỉ in A.

**Một đáp án:**

~~~java
switch (x) {
    case 1:
        System.out.println("A");
        break;
    case 2:
        System.out.println("B");
        break;
    default:
        System.out.println("C");
}
~~~

Cũng có thể dùng nhánh `case 1 -> System.out.println("A");` trong Java 17.

### Bài C — `break` trong vòng lặp

~~~java
for (int i = 0; i < 2; i++) {
    switch (i) {
        case 0:
            break;
        default:
            System.out.println("default");
    }
    System.out.println("after " + i);
}
~~~

**Đáp án:**

~~~text
after 0
default
after 1
~~~

Lệnh `break;` chỉ kết thúc switch ở vòng đầu tiên, không kết thúc `for`.

### Bài D — switch lồng nhau

~~~java
switch (1) {
    case 1:
        switch (7) {
            case 7:
                System.out.println("inner");
                break;
        }
        System.out.println("outer continues");
        break;
}
~~~

**Đáp án:**

~~~text
inner
outer continues
~~~

Break trong chỉ thoát switch trong; câu lệnh của case ngoài vẫn chạy.

### Bài E — switch expression

Cần tạo một `String` từ switch có nhánh xử lý gồm nhiều câu lệnh. Nên dùng `break` hay `yield`?

**Đáp án:** trong switch **expression**, dùng `yield value;` để trả giá trị từ block:

~~~java
String label = switch (code) {
    case 1 -> {
        String value = "ONE";
        yield value;
    }
    default -> "OTHER";
};
~~~

## 15. Checklist và kết luận

- [ ] Hiểu `break;` kết thúc switch gần nhất và chương trình tiếp tục **sau switch**.
- [ ] Biết `case:` không tự dừng; thiếu `break` có thể fall-through.
- [ ] Biết khi nào fall-through là chủ ý (gộp case hoặc luồng đã được thiết kế).
- [ ] Không xem `default` là nơi tự động dừng nếu nó không đứng cuối.
- [ ] Phân biệt `break` thoát switch với `return` thoát phương thức.
- [ ] Phân biệt `break` với `continue` của vòng lặp.
- [ ] Hiểu `break` trong switch lồng `for` không thoát vòng `for`.
- [ ] Hiểu `break` trong switch con không tự thoát switch cha.
- [ ] Biết `case ->` của Java 17 **không fall-through**, không cần `break` để chống rơi nhánh.
- [ ] Biết switch expression dùng `yield` để trả giá trị từ block.
- [ ] Không đặt `break` sau một `return` không thể quay lại.
- [ ] Chạy `SwitchBreakDemo.java` bằng JDK 17+ và đối chiếu exact stdout.

**Kết luận:** Với switch statement dạng `case:`, lệnh `break;` là cách rõ ràng để **ngăn fall-through** và rời switch tại vị trí mong muốn. Nó không rời phương thức hay tự thoát vòng lặp bao ngoài. Trong Java 17, cú pháp `case ->` là lựa chọn tốt khi mỗi case chỉ nên chạy một nhánh mà không cần `break`.