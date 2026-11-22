# `final` có thể được gán trong các nhánh loại trừ nhau — Java 17+

> **Java core — language-basics / Phạm vi và khởi tạo**  
> **Yêu cầu:** JDK 17+; ví dụ một file, chạy bằng `javac` và `java`.  
> **Mục tiêu:** Hiểu vì sao một biến `final` chưa khởi tạo có thể được gán **một lần trên mỗi đường thực thi**, chẳng hạn trong hai nhánh `if/else`; biết phân biệt *definite assignment* với *definite unassignment*, tránh thiếu gán/gán hai lần và áp dụng cho trường `final` trong constructor.

## 1. `final` giới hạn việc gán lại, không bắt buộc gán ngay

Với biến cục bộ (*local variable*), có hai cách khai báo `final`:

~~~java
final int fixed = 10; // Có giá trị ngay khi khai báo.

// Trong một phương thức:
final int selected;   // Blank final: chưa có initializer.
if (true) {
    selected = 20;    // Lần gán đầu tiên.
}
System.out.println(selected); // 20.
~~~

*Blank final* là biến `final` được khai báo **chưa có initializer**. Nó có thể nhận giá trị sau, miễn việc gán tuân theo quy tắc kiểm tra luồng điều khiển của Java.

- `final` không có nghĩa “mỗi nhánh được phép gán một lần rồi cộng lại”; tại **mỗi lần thực thi**, một biến `final` chỉ được nhận giá trị trong những trường hợp mà ngôn ngữ chứng minh được nó **chưa được gán** trước phép gán ấy.
- Để **đọc** một biến cục bộ, trình biên dịch phải xác định nó **chắc chắn đã được gán** (*definitely assigned*, DA) trên mọi đường đi tới vị trí đọc.
- Để **gán** cho một biến `final` chưa có initializer, trình biên dịch phải xác định nó **chắc chắn chưa được gán** (*definitely unassigned*, DU) ngay trước phép gán.

Các kiểm tra DA và DU được thực hiện khi **biên dịch**, dựa trên cấu trúc chương trình, không đợi đến lúc chạy rồi mới xem nhánh nào xảy ra.

## 2. Hai nhánh `if/else` loại trừ nhau: cách viết chuẩn

~~~java
static int select(boolean flag) {
    final int result;

    if (flag) {
        result = 11;
    } else {
        result = 22;
    }

    return result;
}
~~~

Hai nhánh của một câu lệnh `if/else` **không chạy đồng thời trong cùng một lượt gọi**. Khi tới `return result`, bất kể `flag` là `true` hay `false`, **đúng một nhánh** đã gán `result`. Vì vậy:

~~~java
System.out.println(select(true));  // 11
System.out.println(select(false)); // 22
~~~

**Phân tích đường đi:**

| Giá trị `flag` | Nhánh thực thi | Giá trị gán cho `result` | Đã gán trước `return`? |
| --- | --- | --- | --- |
| `true` | `if` | `11` | Có |
| `false` | `else` | `22` | Có |

Điểm quan trọng không phải biến `result` xuất hiện trong **hai câu lệnh gán ở mã nguồn**, mà là **không có đường thực thi hợp lệ nào đi qua cả hai phép gán đó**. Java xác minh sự loại trừ qua cấu trúc `if/else`.

Cách viết tương đương, ngắn hơn khi mỗi nhánh chỉ chọn một giá trị:

~~~java
final int result = flag ? 11 : 22;
~~~

Toán tử điều kiện `?:` trả một giá trị được lựa chọn để khởi tạo `result` đúng một lần; hãy dùng khi biểu thức đủ đơn giản để đọc.

## 3. Thiếu một nhánh gán: lỗi *might not have been initialized*

Đoạn sau **không biên dịch** nếu bỏ comment:

~~~java
// KHÔNG BIÊN DỊCH:
// static int missing(boolean flag) {
//     final int result;
//     if (flag) {
//         result = 11;
//     }
//     return result; // flag=false: result chưa hề được gán.
// }
~~~

Một nhánh có thể không gán gì, nhưng **không được đọc biến khi có đường đi tới chỗ đọc mà chưa gán**. Nếu cần một giá trị cho cả hai trường hợp, dùng `else`:

~~~java
static int withElse(boolean flag) {
    final int result;
    if (flag) {
        result = 11;
    } else {
        result = 0;
    }
    return result;
}
~~~

Hoặc sắp xếp luồng điều khiển để đường không gán **kết thúc trước khi đọc**:

~~~java
static int withEarlyReturn(boolean enabled) {
    final int code;
    if (!enabled) {
        return -1; // Đường này không bao giờ tới return code.
    }
    code = 42;
    return code;
}
~~~

Với `enabled == false`, phương thức trả `-1` ngay, nên không đọc `code`. Với `enabled == true`, `code` được gán `42` trước khi trả. Trình biên dịch có thể chứng minh `code` đã được gán trên mọi đường thực sự tới `return code`.

Tương tự, một nhánh có thể `throw` thay vì gán nếu nó **không tiếp tục** tới chỗ dùng biến. Việc có nhánh `return` hoặc `throw` không tự tạo thêm quyền gán nhiều lần cho `final`.

## 4. Gán lần thứ hai: vẫn là lỗi dù gán cùng giá trị

Một biến `final` đã có giá trị không thể gán lại:

~~~java
// KHÔNG BIÊN DỊCH:
// final int limit = 10;
// limit = 10; // Lỗi: gán lại dù giá trị không thay đổi.
~~~

Điều tương tự xảy ra khi đã gán qua một trong hai nhánh rồi tiếp tục gán sau đó:

~~~java
// KHÔNG BIÊN DỊCH:
// static int assignedTwice(boolean flag) {
//     final int result;
//     if (flag) {
//         result = 1;
//     } else {
//         result = 2;
//     }
//     result = 3; // Lỗi: result chắc chắn đã được gán.
//     return result;
// }
~~~

Không nên viết hai câu `if` độc lập để thay thế một `if/else` trong bài toán lựa chọn một giá trị. Trình biên dịch kiểm tra DA/DU theo quy tắc luồng điều khiển cụ thể; nó **không phải bộ chứng minh tùy ý mọi quan hệ logic** giữa các điều kiện. Cấu trúc `if/else` truyền đạt ý định “chính xác một nhánh” rõ ràng và dễ kiểm chứng hơn.

Với biến `final`, phép `++`, `--` và phép gán kết hợp như `+=` cũng là những thao tác gán lại và không thể dùng sau khi biến đã khởi tạo. `final` bảo vệ **giá trị được giữ trong biến**, không tự đảm bảo kết quả tính toán hay đối tượng là bất biến.

## 5. Nhiều nhánh `else if` và `switch`

Khi có ba hoặc nhiều lựa chọn, cần bao phủ mọi đường đi tới chỗ đọc:

~~~java
static String classify(int number) {
    final String category;

    if (number < 0) {
        category = "NEG";
    } else if (number == 0) {
        category = "ZERO";
    } else {
        category = "POS";
    }

    return category;
}
~~~

Các nhánh trong cùng chuỗi `if/else if/else` loại trừ nhau. Nhánh `else` bảo đảm rằng khi không thỏa hai điều kiện trước, biến vẫn được khởi tạo.

Trong Java 17, `switch` dùng **arrow cases** (`->`) giúp tránh lỗi chạy xuyên xuống case tiếp theo (*fall-through*):

~~~java
static String fromSwitch(int code) {
    final String label;

    switch (code) {
        case 0 -> label = "ZERO";
        case 1 -> label = "ONE";
        default -> label = "OTHER";
    }

    return label;
}
~~~

Ở đây mỗi nhánh `switch` chỉ thực thi một phép gán và `default` bao phủ các giá trị còn lại. Nếu bỏ `default` khỏi ví dụ này, còn đường đi không gán `label` khi `code` khác 0 và 1.

Một cách ngắn gọn khác là **switch expression** trả giá trị khởi tạo trực tiếp:

~~~java
static String fromExpression(int code) {
    final String label = switch (code) {
        case 0 -> "ZERO";
        case 1 -> "ONE";
        default -> "OTHER";
    };
    return label;
}
~~~

Trong `switch expression`, tất cả nhánh của biểu thức phải đáp ứng quy tắc tạo kết quả/hoàn tất của biểu thức. Cả `fromSwitch` và `fromExpression` cho `code=0` kết quả `"ZERO"`, `code=1` kết quả `"ONE"`, và các giá trị khác kết quả `"OTHER"`.

## 6. Trường `final` chưa có initializer trong constructor

Quy tắc tương tự còn rất quan trọng với **blank final instance field**:

~~~java
class Plan {
    private final String tier;
    private final int quota;

    Plan(boolean premium) {
        if (premium) {
            tier = "PREMIUM";
            quota = 100;
        } else {
            tier = "BASIC";
            quota = 10;
        }
    }

    String summary() {
        return tier + ":" + quota;
    }
}
~~~

Mỗi đối tượng `Plan` có các trường `tier` và `quota` riêng; constructor gán đúng một lần cho mỗi trường trên mọi đường kết thúc bình thường. Có thể tạo hai đối tượng có giá trị cuối khác nhau:

~~~java
Plan first = new Plan(true);
Plan second = new Plan(false);
// first.summary()  -> "PREMIUM:100"
// second.summary() -> "BASIC:10"
~~~

Các điểm cần phân biệt:

- **Biến cục bộ blank final:** muốn **đọc** phải thỏa DA; nếu không đọc, vẫn cần tuân thủ quy tắc DU khi gán.
- **Blank final instance field:** phải được khởi tạo theo quy tắc Java trước khi constructor hoàn tất bình thường; nếu có nhiều constructor, các đường khởi tạo tương ứng đều phải hợp lệ.
- **Blank static final field:** được khởi tạo trong phạm vi khởi tạo static hợp lệ của lớp, không phải riêng mỗi lần tạo đối tượng.
- Không thể tạo thêm quyền gán field `final` sau khi đã khởi tạo bằng cách dùng một setter thông thường.

`final` trên trường không đồng nghĩa mọi đối tượng có trường đó là “hằng số tại thời điểm biên dịch”. Chỉ những trường hợp phù hợp quy tắc *constant variable* (ví dụ một số trường primitive/`String` có constant expression) mới có tính chất đó.

## 7. `final` tham chiếu: cấm đổi tham chiếu, không cấm sửa mảng

Trường hợp nhánh chọn một trong hai **mảng**:

~~~java
static int[] chooseArray(boolean shortArray) {
    final int[] values;

    if (shortArray) {
        values = new int[] {1, 2};
    } else {
        values = new int[] {3, 4, 5};
    }

    values[0] = 9; // HỢP LỆ: sửa nội dung mảng.
    return values;
}
~~~

Sau một trong hai nhánh, biến `values` chỉ giữ một tham chiếu được gán đúng một lần. `values[0] = 9` **không gán lại biến tham chiếu**; nó sửa phần tử của đối tượng mảng:

~~~java
// KHÔNG BIÊN DỊCH nếu đặt sau phần if/else:
// values = new int[] {8}; // Gán lại biến final đã khởi tạo.
~~~

Tương tự, một `final StringBuilder` vẫn có thể gọi `append(...)` để đổi trạng thái của đối tượng; còn phép `builder = new StringBuilder()` bị cấm sau lần gán ban đầu. Vì vậy **`final` không đồng nghĩa đối tượng bất biến (*immutable*)**.

Với mỗi lần gọi phương thức, biến cục bộ mới được tạo theo ngữ cảnh lời gọi. Nếu khai báo `final` ở bên trong thân vòng lặp và khởi tạo đúng cách, từng lượt lặp cũng có biến cục bộ theo phạm vi riêng; không được suy diễn rằng một biến `final` duy nhất nằm **ngoài vòng lặp** có thể liên tục nhận giá trị mới.

## 8. Ví dụ Java 17+ chạy độc lập

Tạo file **FinalExclusiveBranchesDemo.java**:

~~~java
import java.util.Arrays;

public final class FinalExclusiveBranchesDemo {
    private final String tier;
    private final int quota;

    public FinalExclusiveBranchesDemo(boolean premium) {
        if (premium) {
            tier = "PREMIUM";
            quota = 100;
        } else {
            tier = "BASIC";
            quota = 10;
        }
    }

    public String summary() {
        return tier + ":" + quota;
    }

    private static int select(boolean flag) {
        final int result;
        if (flag) {
            result = 11;
        } else {
            result = 22;
        }
        return result;
    }

    private static int withEarlyReturn(boolean enabled) {
        final int code;
        if (!enabled) {
            return -1;
        }
        code = 42;
        return code;
    }

    private static String classify(int number) {
        final String category;
        if (number < 0) {
            category = "NEG";
        } else if (number == 0) {
            category = "ZERO";
        } else {
            category = "POS";
        }
        return category;
    }

    private static String fromSwitch(int code) {
        final String label;
        switch (code) {
            case 0 -> label = "ZERO";
            case 1 -> label = "ONE";
            default -> label = "OTHER";
        }
        return label;
    }

    private static String fromExpression(int code) {
        final String label = switch (code) {
            case 0 -> "ZERO";
            case 1 -> "ONE";
            default -> "OTHER";
        };
        return label;
    }

    private static int throwOrAssign(boolean valid) {
        final int value;
        if (!valid) {
            throw new IllegalArgumentException("invalid");
        }
        value = 7;
        return value;
    }

    private static int[] chooseArray(boolean shortArray) {
        final int[] values;
        if (shortArray) {
            values = new int[] {1, 2};
        } else {
            values = new int[] {3, 4, 5};
        }
        values[0] = 9;
        return values;
    }

    private static int loopSum() {
        int sum = 0;
        for (int i = 0; i < 3; i++) {
            final int increment;
            if (i % 2 == 0) {
                increment = i * 10;
            } else {
                increment = i;
            }
            sum += increment;
        }
        return sum;
    }

    public static void main(String[] args) {
        System.out.println("trueBranch=" + select(true));
        System.out.println("falseBranch=" + select(false));
        System.out.println("guardOff=" + withEarlyReturn(false));
        System.out.println("guardOn=" + withEarlyReturn(true));

        System.out.println("negative=" + classify(-2));
        System.out.println("zero=" + classify(0));
        System.out.println("positive=" + classify(5));
        System.out.println("switchZero=" + fromSwitch(0));
        System.out.println("switchOne=" + fromSwitch(1));
        System.out.println("switchOther=" + fromSwitch(8));
        System.out.println("expression=" + fromExpression(1));

        FinalExclusiveBranchesDemo premium =
                new FinalExclusiveBranchesDemo(true);
        FinalExclusiveBranchesDemo basic =
                new FinalExclusiveBranchesDemo(false);
        System.out.println("premium=" + premium.summary());
        System.out.println("basic=" + basic.summary());

        System.out.println("shortArray=" + Arrays.toString(chooseArray(true)));
        System.out.println("longArray=" + Arrays.toString(chooseArray(false)));
        System.out.println("loopSum=" + loopSum());

        System.out.println("throwValid=" + throwOrAssign(true));
        try {
            System.out.println("throwInvalid=" + throwOrAssign(false));
        } catch (IllegalArgumentException ex) {
            System.out.println("throwInvalid=IllegalArgumentException");
        }
    }
}
~~~

Biên dịch và chạy tại thư mục chứa file trong Bash, PowerShell hoặc Command Prompt:

~~~bash
javac -encoding UTF-8 FinalExclusiveBranchesDemo.java
java FinalExclusiveBranchesDemo
~~~

**Expected stdout chính xác:**

~~~text
trueBranch=11
falseBranch=22
guardOff=-1
guardOn=42
negative=NEG
zero=ZERO
positive=POS
switchZero=ZERO
switchOne=ONE
switchOther=OTHER
expression=ONE
premium=PREMIUM:100
basic=BASIC:10
shortArray=[9, 2]
longArray=[9, 4, 5]
loopSum=21
throwValid=7
throwInvalid=IllegalArgumentException
~~~

`trueBranch` và `falseBranch` chứng minh hai nhánh có thể gán cho cùng một blank final; `guardOff` chứng minh một nhánh kết thúc sớm không cần gán giá trị để đi tiếp; `switchZero/One/Other` chứng minh các case loại trừ nhau. Hai trường `final` của constructor được gán trong mỗi nhánh; `shortArray` và `longArray` cho thấy `final` không cấm sửa phần tử mảng.

## 9. Lỗi thường gặp và bài tập

| Hiểu nhầm / vấn đề | Cách kiểm tra hoặc sửa |
| --- | --- |
| Biến `final` phải được gán ngay tại chỗ khai báo | Không bắt buộc với *blank final*; có thể gán hợp lệ ở các nhánh |
| Hai phép gán xuất hiện trong `if/else` là gán hai lần | Sai nếu mỗi đường thực thi chỉ chạy một nhánh |
| Chỉ `if(flag) value=1;` rồi dùng `value` | Thiếu gán khi `flag=false`, không đạt DA |
| `if/else` đã gán rồi lại `value=3` | Gán lần hai, vi phạm quy tắc của `final` |
| Bỏ `default` trong `switch` rồi vẫn đọc biến | Có thể còn đường không gán |
| `final int[] values` không cho sửa `values[0]` | Sai; cấm gán lại tham chiếu, không cấm sửa mảng |
| Trường blank `final` có thể để không gán khi constructor kết thúc | Không; phải khởi tạo hợp lệ trên mọi đường hoàn tất bình thường |
| Nhiều câu `if` độc lập luôn được phân tích như một `if/else` | Không nên giả định; dùng cấu trúc nhánh rõ ràng |
| `final` làm một đối tượng bất biến hoàn toàn | Không; tính bất biến của đối tượng còn phụ thuộc thiết kế kiểu |

**Bài 1.** Viết `static int pick(boolean flag)` có `final int n;`, gán `5` trong nhánh `if` và `8` trong nhánh `else`. Dự đoán kết quả với hai giá trị `flag`.

**Bài 2.** Bỏ nhánh `else` của bài 1 nhưng giữ `return n;`. Giải thích lỗi DA; sửa bằng cách trả sớm hoặc bao phủ đủ các nhánh.

**Bài 3.** Sau `if/else` hợp lệ, thêm `n = 100;`. Giải thích vì sao dù gán cùng giá trị cũ hay khác giá trị, lệnh vẫn bị từ chối.

**Bài 4.** Khai báo lớp có trường `private final String category;` và constructor nhận số. Trong `if/else if/else`, gán các nhãn phù hợp; kiểm tra mọi đường constructor kết thúc.

**Bài 5.** Thay `if/else` bằng `switch` có `default` hoặc `switch expression` trên Java 17. So sánh khả năng bao phủ nhánh và độ rõ ràng.

**Bài 6.** Dùng `final int[] selected;`, chọn một trong hai mảng theo `boolean`, sau đó sửa `selected[0]`. Vì sao sửa phần tử hợp lệ nhưng `selected = new int[2]` thì không?

### Ghi nhớ

**Một blank `final` có thể xuất hiện trong nhiều phép gán ở các nhánh loại trừ nhau**, miễn trình biên dịch chứng minh nó **chưa được gán trước từng phép gán** và **đã được gán trước mọi lần đọc**. `if/else` và `switch` bao phủ đầy đủ trường hợp giúp diễn đạt quy tắc này rõ nhất; `return`/`throw` có thể kết thúc sớm một đường đi. `final` cấm đổi giá trị biến sau khi khởi tạo, nhưng không tự làm đối tượng tham chiếu trở nên bất biến.
