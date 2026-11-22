# `yield` trong khối nhánh của switch expression — Java 17+

## 1. Mục tiêu: nhánh switch tạo ra một giá trị

Từ Java 14, **switch expression** là tính năng ổn định, nên Java 17 sử dụng trực tiếp, **không cần `--enable-preview`**. Khác với switch statement, switch expression **tạo ra một kết quả** để gán, trả về hoặc dùng trong biểu thức khác.

~~~java
int code = 2;
String label = switch (code) {
    case 1 -> "ONE";
    case 2 -> {
        String message = "TWO";
        yield message;
    }
    default -> "OTHER";
};
System.out.println(label); // TWO
~~~

Ở `case 2 -> { ... }`, khối chứa nhiều câu lệnh. Lệnh **`yield message;` cung cấp giá trị `"TWO"` của toàn bộ switch expression** và kết thúc nhánh đó. Đây là mục đích chính của `yield`.

Mục tiêu bài học:

- Phân biệt nhánh `-> value` với `-> { ... yield value; }`.
- Hiểu `yield` khác `break` và `return`.
- Biết dùng `yield` khi nhánh cần tính toán, kiểm tra điều kiện hoặc tạo biến tạm.
- Đảm bảo các đường đi hợp lệ **tạo được giá trị** hoặc **ném ngoại lệ**.
- Biết cú pháp switch expression với nhãn `case:` và cách xử lý kiểu kết quả, `default`, enum.

## 2. Khi nào không cần `yield`?

Một nhánh mũi tên chỉ cần **một biểu thức** thì viết trực tiếp kết quả:

~~~java
int number = 1;
String name = switch (number) {
    case 1 -> "ONE";
    case 2 -> "TWO";
    default -> "OTHER";
};
~~~

Nếu muốn vừa ghi log vừa tính kết quả, dùng **khối nhánh** và `yield`:

~~~java
String name = switch (number) {
    case 1 -> {
        System.out.println("Matched one");
        yield "ONE";
    }
    case 2 -> "TWO";
    default -> "OTHER";
};
~~~

**Exact stdout với `number = 1`:**

~~~text
Matched one
~~~

Giá trị cuối của biểu thức switch là `"ONE"`; chương trình trên chưa in biến `name`.

**Không phải cú pháp đúng:**

~~~java
// String s = switch (number) {
//     case 1 -> {
//         "ONE"; // Không thay yield; string literal không phải statement expression hợp lệ.
//     }
//     default -> "OTHER";
// };
~~~

Khối `{ ... }` của switch expression **không tự lấy giá trị của biểu thức cuối** như một số ngôn ngữ khác. Khi cần kết quả từ khối, dùng `yield result;` rõ ràng.

## 3. Vai trò chính xác của `yield`

Cú pháp:

~~~java
yield expression;
~~~

Ý nghĩa:

1. Đánh giá `expression` sau từ khóa `yield`.
2. Dùng giá trị thu được làm kết quả của **switch expression chứa nó**.
3. Chuyển điều khiển ra khỏi switch expression để tiếp tục phần chương trình xung quanh.

Ví dụ:

~~~java
int base = 6;
int computed = switch (base) {
    case 6 -> {
        int doubleBase = base * 2;
        int extra = 3;
        yield doubleBase + extra;
    }
    default -> 0;
};
System.out.println(computed); // 15
~~~

`yield` không phải khai báo biến và **không gán trực tiếp** vào `computed`; phép gán xảy ra vì switch expression đã trả giá trị 15.

**Một `yield` kết thúc đường đi được thực thi.** Các câu lệnh nằm sau `yield` trong cùng một đường đi không thể được thực thi; nếu compiler xác định câu lệnh sau là unreachable, chương trình sẽ không biên dịch.

## 4. `yield`, `break`, `return`, `throw`: không hoán đổi cho nhau

| Cấu trúc | Mục đích | Tác động |
|---|---|---|
| `yield value;` | Cung cấp kết quả của **switch expression** | Rời switch expression, tiếp tục biểu thức/câu lệnh bao ngoài |
| `break;` | Thoát switch **statement** hoặc vòng lặp | Không tạo ra giá trị cho switch expression |
| `return value;` | Trả kết quả của **phương thức** | Rời phương thức, không chỉ rời switch |
| `throw exception;` | Báo lỗi qua ngoại lệ | Không trả giá trị bình thường; switch expression có thể dùng một nhánh `throw` |

Trong switch statement truyền thống:

~~~java
switch (code) {
    case 1:
        System.out.println("one");
        break; // Kết thúc switch statement, không trả giá trị.
    default:
        System.out.println("other");
}
~~~

Trong switch expression:

~~~java
String result = switch (code) {
    case 1 -> {
        yield "ONE"; // Giá trị của switch expression.
    }
    default -> "OTHER";
};
~~~

**Sai:**

~~~java
// String result = switch (code) {
//     case 1 -> { break; } // Không dùng break để kết thúc switch expression.
//     default -> "OTHER";
// };
// String result = switch (code) {
//     case 1 -> { break "ONE"; } // Java 17 không có cú pháp break value.
//     default -> "OTHER";
// };
~~~

Muốn rời toàn bộ phương thức sớm, đặt lệnh `return` bên ngoài switch expression hoặc thiết kế các nhánh trả giá trị rồi `return switch (...)`:

~~~java
static String describe(int code) {
    return switch (code) {
        case 1 -> "ONE";
        default -> "OTHER";
    };
}
~~~

## 5. `yield` trong `if/else` bên trong khối nhánh

Không phải nhánh nào cũng tính giá trị theo một công thức đơn giản. Có thể dùng điều kiện phụ:

~~~java
static String sign(int value) {
    return switch (Integer.signum(value)) {
        case -1 -> {
            yield "NEGATIVE";
        }
        case 0 -> "ZERO";
        default -> {
            yield "POSITIVE";
        }
    };
}
~~~

Hoặc sử dụng nhiều `yield` ở những đường đi loại trừ nhau:

~~~java
static int normalize(int input) {
    return switch (input) {
        case 0 -> 0;
        default -> {
            if (input < 0) {
                yield -1;
            }
            yield 1;
        }
    };
}
~~~

Khi `input < 0`, `yield -1;` kết thúc switch expression; câu `yield 1;` chỉ thực thi khi điều kiện trước false.

**Không cần** biến kết quả trung gian chỉ để lưu sau mỗi nhánh nếu một `yield` ở cuối khối diễn đạt rõ hơn. Nhưng với nhánh dài, nên cân nhắc tách logic thành một method giúp dễ kiểm thử.

## 6. Mỗi đường đi phải tạo ra kết quả hoặc ném ngoại lệ

Switch expression phải có cách cho ra giá trị trên mọi đường đi có thể **hoàn thành bình thường**. Ví dụ sau thiếu `yield` khi `value <= 0`:

~~~java
// int result = switch (code) {
//     case 1 -> {
//         if (value > 0) {
//             yield value;
//         }
//         // LỖI: có đường đi hết khối mà không tạo giá trị.
//     }
//     default -> 0;
// };
~~~

Cách sửa:

~~~java
int result = switch (code) {
    case 1 -> {
        if (value > 0) {
            yield value;
        }
        yield 0;
    }
    default -> 0;
};
~~~

Một nhánh **có thể ném ngoại lệ** thay vì trả giá trị:

~~~java
int result = switch (code) {
    case 1 -> 100;
    case 2 -> {
        if (value < 0) {
            throw new IllegalArgumentException("negative value");
        }
        yield value * 2;
    }
    default -> 0;
};
~~~

Đây là hợp lệ: đường đi có `throw` không hoàn thành bình thường, còn đường đi hợp lệ có `yield`.

**Lỗi cần tránh:** viết `yield;` (không có giá trị). Switch expression cần một biểu thức sau `yield`; không có cú pháp `yield;` đơn lẻ.

## 7. Cú pháp dấu hai chấm `case:` trong switch expression

Switch expression vẫn có thể dùng dạng nhóm câu lệnh `case VALUE:`, nhưng khi nhánh tính ra giá trị cần **`yield`**:

~~~java
static String word(int code) {
    return switch (code) {
        case 1:
            yield "ONE";
        case 2:
        case 3:
            String message = "TWO_OR_THREE";
            yield message;
        default:
            yield "OTHER";
    };
}
~~~

Với `code=2`, chương trình trả `"TWO_OR_THREE"`.

**Khác dạng mũi tên:**

- `case 2 -> "TWO";`: kết quả viết ngay sau `->`.
- `case 2 -> { yield "TWO"; }`: phải `yield` từ khối.
- `case 2: yield "TWO";`: nhóm câu lệnh kiểu truyền thống, dùng `yield`.

Trong dạng `case:`, **fall-through vẫn là điều cần xét** nếu một đường đi không kết thúc bằng `yield`/`throw` trước nhãn tiếp theo. Với switch expression, nên viết rõ ràng để không có fall-through khó hiểu.

**Không trộn `case:` và `case ->` trong cùng một switch block.**

## 8. `yield` phải trả giá trị tương thích kiểu đích

Compiler kiểm tra mọi nhánh có tạo giá trị tương thích ngữ cảnh kết quả. Đích `double` có thể nhận `int` trong một nhánh:

~~~java
double amount = switch (code) {
    case 1 -> { yield 10; }
    default -> 2.5;
};
~~~

Với `code == 1`, `amount` là `10.0`. `yield` không bỏ qua kiểm tra kiểu; nên chọn kiểu kết quả tường minh khi nghiệp vụ cần thống nhất. Bài tiếp theo đi sâu vào target typing và chuyển kiểu số.

## 9. Bao phủ trường hợp và `default`

Switch expression phải exhaustive: với `int`/`String` thường có `default`; với enum có thể liệt kê đủ các hằng. Điều kiện này **độc lập** với việc từng block cần `yield` hoặc `throw` trên mọi đường đi phù hợp. `default` không tự xử lý selector `null` trong Java 17 tiêu chuẩn. Bài kế tiếp tập trung vào chứng minh độ bao phủ và kiểu kết quả.

## 10. `break` trong vòng lặp lồng ở nhánh không thay `yield`

Một nhánh mũi tên có thể chứa **vòng lặp**, và `break;` bên trong vòng lặp đó chỉ kết thúc **vòng lặp gần nhất**. Sau vòng lặp vẫn cần cung cấp kết quả cho switch expression:

~~~java
int count = switch (code) {
    case 1 -> {
        int sum = 0;
        for (int i = 1; i <= 5; i++) {
            if (i == 3) {
                break; // Thoát for, không trả giá trị switch.
            }
            sum += i;
        }
        yield sum;
    }
    default -> 0;
};
~~~

Khi `code == 1`, vòng lặp cộng `1 + 2` rồi dừng, `yield sum;` trả **3**.

**Nguyên tắc:** mỗi cấu trúc điều khiển có mục đích riêng; `break` của vòng lặp không thay thế `yield` của switch expression.

## 11. Phạm vi biến và tác dụng phụ trong nhánh

Biến khai báo trong block rule `case -> { ... }` có phạm vi ở block đó:

~~~java
String result = switch (code) {
    case 1 -> {
        String message = "first";
        yield message;
    }
    default -> {
        String message = "other"; // Hợp lệ: block khác.
        yield message;
    }
};
~~~

Đặt biến tạm trong khối giúp tránh xung đột tên và dễ bảo trì.

Chỉ nhánh được chọn mới được đánh giá runtime:

~~~java
static int trace(String name, int value) {
    System.out.println("evaluated " + name);
    return value;
}

int n = switch (code) {
    case 1 -> {
        yield trace("one", 10);
    }
    default -> {
        yield trace("other", 20);
    }
};
~~~

Với `code == 1`, chỉ in `evaluated one`, không gọi nhánh default.

Tuy nhiên, **không nên dựa vào side effect để xác định kết quả nghiệp vụ** nếu có thể tách việc ghi log/validation khỏi phép tính. `yield` làm rõ giá trị được trả, không tự làm thao tác bên trong nhánh thành atomic hoặc thread-safe.

## 12. Chương trình Java 17 hoàn chỉnh

Lưu file đúng tên **`SwitchYieldDemo.java`**:

~~~java
public final class SwitchYieldDemo {
    private SwitchYieldDemo() {}

    enum Channel { WEB, MOBILE, API }

    static String channelName(Channel channel) {
        return switch (channel) {
            case WEB -> "BROWSER";
            case MOBILE -> {
                String label = "PHONE";
                yield label;
            }
            case API -> "SERVICE";
        };
    }

    static String grade(int score) {
        if (score < 0 || score > 100) {
            return "INVALID";
        }
        return switch (score / 10) {
            case 10, 9 -> "A";
            case 8, 7 -> {
                String label = "B";
                yield label;
            }
            case 6, 5 -> "C";
            default -> "D";
        };
    }

    static String fromColon(int code) {
        return switch (code) {
            case 1:
                yield "ONE";
            case 2:
            case 3:
                String label = "TWO_OR_THREE";
                yield label;
            default:
                yield "OTHER";
        };
    }

    static int sign(int value) {
        return switch (value) {
            case 0 -> {
                System.out.println("zero branch");
                yield 0;
            }
            default -> {
                if (value < 0) {
                    yield -1;
                }
                yield 1;
            }
        };
    }

    static int sumUntilThree(int code) {
        return switch (code) {
            case 1 -> {
                int sum = 0;
                for (int i = 1; i <= 5; i++) {
                    if (i == 3) {
                        break;
                    }
                    sum += i;
                }
                yield sum;
            }
            default -> 0;
        };
    }

    static double promoted(int code) {
        return switch (code) {
            case 1 -> {
                yield 10;  // int: chuyển thành double.
            }
            default -> 2.5;
        };
    }

    static int checkedDouble(int value) {
        return switch (value) {
            case 0 -> 0;
            default -> {
                if (value < 0) {
                    throw new IllegalArgumentException("negative");
                }
                yield value * 2;
            }
        };
    }

    static int trace(String name, int value) {
        System.out.println("evaluated " + name);
        return value;
    }

    static int traceChoice(int code) {
        return switch (code) {
            case 1 -> {
                yield trace("one", 10);
            }
            default -> {
                yield trace("other", 20);
            }
        };
    }

    static void statementExample(int code) {
        switch (code) {
            case 1 -> System.out.println("statement:one");
            default -> System.out.println("statement:other");
        }
    }

    public static void main(String[] args) {
        System.out.println("channel WEB=" + channelName(Channel.WEB));
        System.out.println("channel MOBILE=" + channelName(Channel.MOBILE));
        System.out.println("channel API=" + channelName(Channel.API));

        System.out.println("grade -1=" + grade(-1));
        System.out.println("grade 49=" + grade(49));
        System.out.println("grade 50=" + grade(50));
        System.out.println("grade 70=" + grade(70));
        System.out.println("grade 90=" + grade(90));
        System.out.println("grade 100=" + grade(100));

        System.out.println("colon 1=" + fromColon(1));
        System.out.println("colon 2=" + fromColon(2));
        System.out.println("colon 3=" + fromColon(3));
        System.out.println("colon 4=" + fromColon(4));

        System.out.println("sign 0=" + sign(0));
        System.out.println("sign -5=" + sign(-5));
        System.out.println("sign 5=" + sign(5));

        System.out.println("loop 1=" + sumUntilThree(1));
        System.out.println("loop 9=" + sumUntilThree(9));
        System.out.println("numeric promotion=" + promoted(1));

        System.out.println("checked 7=" + checkedDouble(7));
        try {
            System.out.println(checkedDouble(-2));
        } catch (IllegalArgumentException ex) {
            System.out.println("checked -2=" + ex.getMessage());
        }

        System.out.println("trace result=" + traceChoice(1));
        statementExample(1);
        statementExample(2);
    }
}
~~~

**Yêu cầu:** JDK 17 trở lên, mở terminal tại thư mục chứa `SwitchYieldDemo.java`; không cần Maven/Gradle, thư viện ngoài JDK hay cờ preview.

**Bash (Linux/macOS):**

~~~bash
javac --release 17 -encoding UTF-8 SwitchYieldDemo.java
java -cp . SwitchYieldDemo
~~~

**PowerShell (Windows):**

~~~powershell
javac --release 17 -encoding UTF-8 .\SwitchYieldDemo.java
java -cp . SwitchYieldDemo
~~~

### Exact expected stdout

~~~text
channel WEB=BROWSER
channel MOBILE=PHONE
channel API=SERVICE
grade -1=INVALID
grade 49=D
grade 50=C
grade 70=B
grade 90=A
grade 100=A
colon 1=ONE
colon 2=TWO_OR_THREE
colon 3=TWO_OR_THREE
colon 4=OTHER
zero branch
sign 0=0
sign -5=-1
sign 5=1
loop 1=3
loop 9=0
numeric promotion=10.0
checked 7=14
checked -2=negative
evaluated one
trace result=10
statement:one
statement:other
~~~

**Giải thích nhanh:**

1. `channelName` xử lý đầy đủ enum; nhánh MOBILE tạo biến rồi `yield`, nhưng không cần `default`.
2. `grade` kiểm tra miền 0–100 trước khi switch, nên `grade(100)` là A và `grade(-1)` là INVALID.
3. `fromColon` minh họa dạng `case:` của switch expression vẫn dùng được `yield`.
4. `sign(0)` in `zero branch` **trước** dòng `sign 0=0` vì lời gọi được đánh giá trước khi in toàn biểu thức nối chuỗi.
5. `sumUntilThree(1)` cộng 1 và 2; `break` chỉ rời `for`, `yield` trả tổng 3.
6. `promoted(1)` trả 10.0 theo kiểu double của switch expression trong ngữ cảnh này.
7. `checkedDouble(-2)` ném ngoại lệ, không phải `yield` từ đường đi lỗi.
8. Chỉ có `evaluated one`: nhánh default của `traceChoice(1)` không được đánh giá.
9. `statementExample` dùng `case ->` nhưng **không tạo giá trị**, khác với các phương thức trả `switch`.

## 13. Lỗi thường gặp

| Lỗi hoặc nhầm lẫn | Vấn đề | Cách sửa |
|---|---|---|
| `case 1 -> { "ONE"; }` | Không tạo giá trị; literal không là statement hợp lệ | `yield "ONE";` |
| `case 1 -> { break; }` | Không dùng `break` để kết thúc switch expression | `yield value;` |
| `break "ONE";` | Java 17 không có break-with-value | `yield "ONE";` |
| Quên `yield` ở một đường đi trong block | Switch expression có thể hoàn thành mà không có kết quả | Bảo đảm mọi đường đi yield/throw |
| `yield;` | Thiếu biểu thức giá trị | `yield expression;` |
| Nghĩ `return` và `yield` giống nhau | `return` rời method, `yield` rời switch expression | Chọn đúng mức điều khiển |
| Nhánh `->` luôn phải dùng `yield` | Biểu thức đơn giản đã trả kết quả trực tiếp | `case 1 -> "ONE";` |
| Nghĩ nhánh `->` có fall-through | Rule `->` không fall-through | Dùng nhánh riêng hoặc gộp `case 1, 2` |
| Dùng `case:` mà quên tác động fall-through | Có thể chạy tới nhóm sau | Thiết kế đường đi yield/throw rõ |
| Thiếu `default` cho switch expression trên `int` | Không bao phủ mọi giá trị | Thêm `default` |
| Cố ép các nhánh trả kiểu không tương thích | Không compile | Chọn kiểu chung hợp lệ/target type |
| Dùng `break` trong vòng lặp rồi tưởng đã trả switch | Chỉ rời vòng lặp | `yield` sau vòng lặp |
| Đưa `case null` của pattern switch mới vào code Java 17 thường | Khác chế độ/tính năng | Kiểm tra null trước khi switch |

## 14. Bài tập có đáp án

### Bài A — thêm `yield`

Điền phần còn thiếu để nhánh tính toán trả tổng:

~~~java
int n = 3;
int value = switch (n) {
    case 3 -> {
        int sum = 1 + 2 + 3;
        yield sum;
    }
    default -> 0;
};
System.out.println(value);
~~~

**Đáp án:** dùng `yield sum;`, stdout:

~~~text
6
~~~

### Bài B — dự đoán thứ tự in

~~~java
int n = 1;
String value = switch (n) {
    case 1 -> {
        System.out.println("inside");
        yield "ONE";
    }
    default -> "OTHER";
};
System.out.println(value);
~~~

**Đáp án:**

~~~text
inside
ONE
~~~

### Bài C — hai đường đi trong cùng block

Yêu cầu: `n > 0` trả 1, còn lại trả -1:

~~~java
int result = switch (code) {
    case 1 -> {
        if (n > 0) {
            yield 1;
        }
        yield -1;
    }
    default -> 0;
};
~~~

**Đáp án:** cả hai đường đi của case 1 đều trả giá trị qua `yield`.

### Bài D — phân biệt switch statement và expression

~~~java
switch (code) {
    case 1 -> System.out.println("one");
    default -> System.out.println("other");
}
~~~

**Đáp án:** đây là **switch statement** vì được dùng để thực hiện câu lệnh; không cần yield. Để tạo giá trị, viết `String result = switch (code) { case 1 -> "ONE"; default -> "OTHER"; };`.

### Bài E — `break` trong vòng lặp

Vì sao `break;` của vòng `for` nằm trong block case không thay thế `yield`?

**Đáp án:** `break` không nhãn thoát **vòng lặp gần nhất**. Sau đó, block case vẫn phải dùng `yield` hoặc một đường đi ném ngoại lệ để switch expression tạo kết quả.

### Bài F — nhãn kiểu dấu hai chấm

Hoàn thành switch expression dùng nhãn `case:`:

~~~java
String result = switch (code) {
    case 1:
        yield "ONE";
    case 2:
        yield "TWO";
    default:
        yield "OTHER";
};
~~~

**Đáp án:** dạng `case:` được dùng trong switch expression Java 17, nhưng thay `break` bằng `yield` khi cần trả kết quả.

## 15. Checklist và kết luận

- [ ] Biết switch expression tạo giá trị và có thể dùng trong phép gán/`return`.
- [ ] Biết nhánh `case x -> expression` trả giá trị trực tiếp.
- [ ] Biết dùng `case x -> { ... yield expression; }` khi nhánh có nhiều câu lệnh.
- [ ] Hiểu `yield` kết thúc switch expression và truyền giá trị ra ngoài.
- [ ] Không thay `yield` bằng `break`, `return` hay `break value`.
- [ ] Bảo đảm mọi đường đi có thể hoàn thành bình thường đều trả kết quả hoặc ném ngoại lệ.
- [ ] Hiểu `yield` có thể nằm trong `if/else` ở block nhánh.
- [ ] Biết switch expression dạng `case:` cũng dùng `yield`.
- [ ] Nhớ rule mũi tên `->` không fall-through, còn dạng `case:` cần xét fall-through.
- [ ] Hiểu quy tắc kiểu kết quả, numeric conversion, target typing và các lỗi kiểu.
- [ ] Biết switch expression phải bao phủ selector; enum đầy đủ có thể không cần default.
- [ ] Phân biệt `break` của vòng lặp lồng trong nhánh với `yield` của switch.
- [ ] Biên dịch và chạy `SwitchYieldDemo.java` bằng Java 17+; đối chiếu từng dòng exact stdout.

**Kết luận:** Trong Java 17, khi một nhánh của **switch expression** là khối `{ ... }`, dùng **`yield value;`** để trả giá trị cho toàn switch expression. Một nhánh đơn giản có thể viết `case ... -> value` không cần yield. Hãy phân biệt rõ `yield` (trả giá trị của switch expression), `break` (thoát statement/vòng lặp) và `return` (thoát phương thức), đồng thời bảo đảm đủ đường đi và đúng kiểu kết quả.