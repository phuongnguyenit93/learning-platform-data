# Phân biệt `break`, `continue`, `return` và `yield` — Java 17+

Bốn từ khóa này đều **thay đổi luồng thực thi**, nhưng **khác nhau về nơi chúng chuyển điều khiển tới**. Không thể thay chúng cho nhau chỉ vì tất cả đều có thể kết thúc một đoạn lệnh.

| Lệnh | Tác động chính | Nơi dùng điển hình | Sau lệnh, chương trình đi đâu? |
| --- | --- | --- | --- |
| `break;` | Thoát **vòng lặp hoặc `switch` gần nhất** | `for`, `while`, `do-while`, switch statement | Lệnh sau cấu trúc vừa thoát |
| `continue;` | Bỏ phần còn lại của **lượt lặp hiện tại** | Bên trong vòng lặp | Bước chuẩn bị lượt kế tiếp của vòng lặp gần nhất |
| `return value;` / `return;` | Kết thúc **phương thức** hiện tại | Trong phương thức, nếu loại `return` phù hợp với kiểu trả về | Trở về nơi gọi, không chạy tiếp phần còn lại của phương thức |
| `yield value;` | Tạo giá trị rồi kết thúc **switch expression** đang bao quanh | Nhánh hoặc khối bên trong switch expression | Tiếp tục ở biểu thức/câu lệnh đang sử dụng kết quả `switch` |

**Quy tắc nhớ nhanh:** `break` thoát cấu trúc, `continue` sang lượt lặp kế tiếp, `return` thoát phương thức, còn `yield` trả giá trị **cho một biểu thức `switch`**, không tự thoát phương thức.

## 1. `break`: dừng vòng lặp hoặc `switch` gần nhất

~~~java
for (int i = 0; i < 5; i++) {
    if (i == 3) {
        break;
    }
    System.out.println(i);
}
System.out.println("after-loop");
~~~

In `0`, `1`, `2` rồi `after-loop`. Khi `i == 3`, `break` bỏ phần còn lại của thân, **không** thực hiện phần cập nhật `i++` thêm một lần và thoát hẳn vòng.

Trong một `switch` nằm bên trong vòng lặp, `break;` thoát **`switch`**, không mặc nhiên thoát vòng lặp ngoài:

~~~java
for (int i = 0; i < 2; i++) {
    switch (i) {
        case 0:
            System.out.println("zero");
            break; // Chỉ ra khỏi switch.
        default:
            System.out.println("other");
    }
    System.out.println("after-switch=" + i);
}
~~~

Dù có `break` ở `case 0`, dòng `after-switch=0` vẫn được in và vòng `for` tiếp tục. Với các vòng lặp lồng nhau, `break;` không nhãn chỉ thoát **vòng gần nhất**. Cách thoát nhiều tầng bằng nhãn hoặc tách phương thức là vấn đề riêng, không phải hành vi mặc định.

## 2. `continue`: bỏ phần còn lại của lượt hiện tại

~~~java
for (int i = 0; i < 4; i++) {
    if (i % 2 == 0) {
        continue;
    }
    System.out.println(i);
}
// In 1 rồi 3.
~~~

`continue` không kết thúc toàn bộ vòng. Trong basic `for`, nó chuyển tới **phần cập nhật** rồi mới kiểm tra điều kiện:

~~~java
for (int i = 0; i < 3; i++) {
    if (i == 1) {
        continue; // Vẫn chạy i++ trước khi lặp tiếp.
    }
    System.out.println("i=" + i);
}
~~~

Với `while`, `continue` chuyển tới **kiểm tra điều kiện**; với `do-while`, nó chuyển tới **lần kiểm tra ở cuối thân**. Nếu cập nhật biến đếm nằm sau `continue` trong `while`, vòng có thể **không tiến triển** và lặp vô hạn.

`continue;` không chuyển tới nhãn `case` tiếp theo của `switch`. Nếu một `switch` nằm trong vòng lặp, `continue;` bên trong `switch` sẽ tiếp tục **vòng lặp bao quanh**. Nếu `switch` không nằm trong vòng lặp, `continue;` là không hợp lệ.

## 3. `return`: rời cả phương thức

~~~java
static String find(int wanted) {
    for (int i = 0; i < 3; i++) {
        if (i == wanted) {
            return "found:" + i;
        }
    }
    return "missing";
}
~~~

`return` kết thúc **toàn bộ lời gọi phương thức**, kể cả khi đang nằm trong vòng `for` hoặc `switch`. Nếu tìm thấy phần tử, Java không chạy các lượt lặp tiếp theo hoặc câu lệnh bình thường nằm sau `return`.

- Phương thức trả giá trị, như `String find(...)`, dùng `return expression;` có kiểu tương thích.
- Phương thức `void` có thể dùng `return;` để rời phương thức sớm.
- `return;` không được dùng để trả về từ một phương thức đòi giá trị; ngược lại, `return 5;` không hợp lệ trong phương thức `void`.
- `return` của một phương thức không kết thúc cả chương trình: **nơi gọi** nhận kết quả rồi thực thi tiếp.

## 4. `yield`: đưa giá trị ra khỏi `switch expression`

Từ Java 14, `switch` có thể là **biểu thức trả về một giá trị**. Khi nhánh dạng khối cần thực hiện nhiều lệnh, dùng `yield`:

~~~java
static String classify(int n) {
    String label = switch (n) {
        case 0 -> "zero";
        case 1 -> {
            System.out.println("preparing");
            yield "one";
        }
        default -> "other";
    };
    System.out.println("after-expression");
    return label;
}
~~~

Với `n == 1`, Java in `preparing` rồi **`after-expression`**, và phương thức mới kết thúc tại `return label`. Như vậy `yield "one";` kết thúc nhánh switch expression, **không** kết thúc `classify`.

### Dạng dấu hai chấm cũng dùng `yield` được

~~~java
int score = switch (level) {
    case 1:
        yield 10;
    case 2:
        yield 20;
    default:
        yield -1;
};
~~~

Đây là **switch expression** có các nhãn `case:`, không phải switch statement truyền thống. `yield` cung cấp kết quả cho toàn bộ biểu thức. Không viết `break 20;` để tạo kết quả: Java 17 dùng `yield 20;`.

### `switch statement` khác `switch expression`

~~~java
// SWITCH STATEMENT: thực hiện hành động, không tạo giá trị.
switch (status) {
    case "ON":
        System.out.println("enabled");
        break;
    default:
        System.out.println("unknown");
}

// SWITCH EXPRESSION: tạo giá trị.
String result = switch (status) {
    case "ON" -> "enabled";
    default -> "unknown";
};
~~~

- `yield` thuộc **switch expression**, không dùng như một lệnh thay `break` trong switch statement.
- `return` không được phép dùng **bên trong switch expression** để thay việc cấp giá trị cho nhánh; dùng biểu thức sau `->` hoặc `yield`.
- `case ->` không tự động đồng nghĩa với switch expression: Java 17 cũng cho phép **switch statement** có nhãn mũi tên.
- Không nhất thiết mọi nhánh đều dùng `yield`: nhánh `case X -> expression` tự cung cấp kết quả.
- Switch expression cần bao phủ đầy đủ (*exhaustive*) các giá trị chọn theo quy tắc của Java; thường dùng `default` khi cần.

## 5. Chương trình Java 17+ hoàn chỉnh

Tạo file UTF-8 **`FlowTransferDemo.java`**:

~~~java
public class FlowTransferDemo {
    static void breakLoop() {
        for (int i = 0; i < 5; i++) {
            if (i == 3) {
                System.out.println("break=" + i);
                break;
            }
            System.out.println("seen=" + i);
        }
        System.out.println("afterBreak");
    }

    static void continueLoop() {
        for (int i = 0; i < 4; i++) {
            if (i % 2 == 0) {
                System.out.println("skip=" + i);
                continue;
            }
            System.out.println("keep=" + i);
        }
        System.out.println("afterContinue");
    }

    static String find(int target) {
        for (int i = 0; i < 4; i++) {
            if (i == target) {
                return "found:" + i;
            }
        }
        return "missing";
    }

    static String expression(int n) {
        String result = switch (n) {
            case 0 -> "zero";
            case 1 -> {
                System.out.println("insideYield=" + n);
                yield "one";
            }
            default -> "other";
        };
        System.out.println("afterExpr=" + result);
        return "value:" + result;
    }

    static int colonExpression(int n) {
        int result = switch (n) {
            case 1:
                yield 10;
            case 2:
                yield 20;
            default:
                yield -1;
        };
        System.out.println("afterColon=" + result);
        return result;
    }

    static void switchInsideLoop() {
        for (int n = 0; n < 3; n++) {
            switch (n) {
                case 0:
                    System.out.println("caseZero");
                    break;
                case 1:
                    System.out.println("caseOne");
                    continue;
                default:
                    System.out.println("caseOther");
            }
            System.out.println("afterSwitch=" + n);
        }
    }

    static String returnFromSwitch(String code) {
        if (code == null) {
            return "missing";
        }
        switch (code) {
            case "GO":
                return "run";
            default:
                return "unknown";
        }
    }

    public static void main(String[] args) {
        System.out.println("== break ==");
        breakLoop();

        System.out.println("== continue ==");
        continueLoop();

        System.out.println("== return ==");
        System.out.println("return1=" + find(2));
        System.out.println("return2=" + find(9));

        System.out.println("== yield ==");
        System.out.println("expression1=" + expression(1));
        System.out.println("expression9=" + expression(9));

        System.out.println("== colon-style expression ==");
        System.out.println("colon2=" + colonExpression(2));

        System.out.println("== switch in loop ==");
        switchInsideLoop();

        System.out.println("== return in switch statement ==");
        System.out.println("codeGo=" + returnFromSwitch("GO"));
        System.out.println("codeNull=" + returnFromSwitch(null));
        System.out.println("done");
    }
}
~~~

Dùng **JDK 17 trở lên**, mở PowerShell hoặc Bash tại thư mục chứa file:

~~~bash
java -version
javac -version
javac -encoding UTF-8 FlowTransferDemo.java
java FlowTransferDemo
~~~

**Exact expected stdout** của riêng lệnh `java FlowTransferDemo`:

~~~text
== break ==
seen=0
seen=1
seen=2
break=3
afterBreak
== continue ==
skip=0
keep=1
skip=2
keep=3
afterContinue
== return ==
return1=found:2
return2=missing
== yield ==
insideYield=1
afterExpr=one
expression1=value:one
afterExpr=other
expression9=value:other
== colon-style expression ==
afterColon=20
colon2=20
== switch in loop ==
caseZero
afterSwitch=0
caseOne
caseOther
afterSwitch=2
== return in switch statement ==
codeGo=run
codeNull=missing
done
~~~

`java -version` và `javac -version` cho thông tin phụ thuộc bản JDK cài đặt, không thuộc khối stdout cố định. Ví dụ chỉ dùng API Java chuẩn.

## 6. Những trường hợp dễ nhầm

| Hiểu nhầm | Cách đúng |
| --- | --- |
| “`break` là thoát phương thức.” | Nó chỉ thoát vòng lặp hoặc switch gần nhất |
| “`continue` thoát hẳn vòng.” | Nó bỏ phần còn lại của **lượt hiện tại** |
| “`continue` trong basic `for` bỏ phần cập nhật.” | Vẫn chạy phần cập nhật khi tiếp tục vòng đó |
| “`break` trong switch nằm trong vòng lặp sẽ thoát vòng ngoài.” | Nó thoát switch gần nhất |
| “`continue` trong switch đi tới case sau.” | Nó hướng tới vòng lặp gần nhất, hoặc bị cấm nếu không có vòng |
| “`return` và `yield` đều thoát phương thức.” | Chỉ `return` thoát phương thức; `yield` tạo kết quả switch expression |
| “Switch expression dùng `break value;`.” | Dùng `yield value;` hoặc `case -> expression` |
| “Dùng `return value;` thay `yield value;` trong switch expression.” | Không hợp lệ trong switch expression |
| “Mọi `switch case ->` đều trả giá trị.” | Switch statement cũng có thể dùng dạng mũi tên |

### Thoát bất thường và `finally`

Các lệnh chuyển luồng vẫn tuân thủ cơ chế `finally` của Java. Nếu đường thực thi đi ra khỏi một khối `try` qua `break`, `continue` hoặc `return`, khối `finally` thích hợp vẫn được thực hiện. Không nên dùng các lệnh này với giả định có thể bỏ qua việc dọn dẹp tài nguyên; với tài nguyên cần đóng, ưu tiên `try-with-resources`. Điều này không thay đổi **đích tác động về mặt ngữ nghĩa** của bốn từ khóa.

## 7. Bài tập tự kiểm tra

1. `break;` trong `for` làm phần `i++` của lượt đó chạy tiếp không?  
   *Đáp án:* Không.
2. `continue;` trong basic `for` thì `i++` có chạy không?  
   *Đáp án:* Có, nếu `continue` nhắm tới vòng `for` đó.
3. `return "ok";` bên trong vòng lặp có chạy câu lệnh bình thường sau vòng trong cùng phương thức không?  
   *Đáp án:* Không; phương thức đã kết thúc.
4. `yield "ok";` bên trong switch expression có kết thúc luôn phương thức bao ngoài không?  
   *Đáp án:* Không; nó cung cấp kết quả của switch expression.
5. Khi `switch` nằm trong `while`, `break;` từ một nhánh `case:` thoát cấu trúc nào?  
   *Đáp án:* Thoát switch; vòng while vẫn có thể tiếp tục.
6. `continue;` trong một `switch` không có vòng lặp bao ngoài có biên dịch không?  
   *Đáp án:* Không.
7. Có thể viết `yield` trong switch statement thông thường để trả giá trị của statement không?  
   *Đáp án:* Không; dùng switch expression nếu cần giá trị.

## Checklist

- [ ] Xác định đúng **đích điều khiển**: vòng/switch gần nhất, lượt tiếp theo, phương thức hay switch expression.
- [ ] Dùng `break` khi muốn **dừng** vòng/switch, `continue` khi muốn **bỏ qua một lượt**.
- [ ] Dùng `return` để **kết thúc phương thức** đúng kiểu trả về.
- [ ] Dùng `yield` khi cần **cung cấp giá trị** từ nhánh khối hoặc nhánh dấu hai chấm của switch expression.
- [ ] Không nhầm switch statement với switch expression.
- [ ] Kiểm tra cập nhật vòng lặp và xử lý tài nguyên khi đổi luồng.

**Kết luận:** `break` dừng cấu trúc bao quanh gần nhất; `continue` chuyển đến lượt vòng lặp tiếp theo; `return` rời phương thức; `yield` rời nhánh **switch expression** với một giá trị. Nắm đúng điểm đến của mỗi lệnh giúp tránh lỗi dừng sai phạm vi và viết mã Java 17 rõ ràng.
