# Tái cấu trúc switch dài mà giữ nguyên thứ tự tác dụng phụ

Khi chuyển một `switch` nhiều nhánh sang **switch expression** (có kết quả) hoặc rút gọn những nhánh lặp, mục tiêu không chỉ là làm mã ngắn hơn. Mã sau khi tái cấu trúc phải giữ đúng **giá trị trả về, đường đi điều khiển và thứ tự những tác dụng phụ quan sát được**: ghi log, cập nhật bộ đếm, thay đổi trạng thái, gọi dịch vụ, ghi tệp, ném ngoại lệ, v.v.

Trong Java 14 trở đi, `switch expression` và `yield` là các tính năng chính thức, vẫn được sử dụng trong Java hiện đại. Cú pháp `case ... ->` giúp tách các nhánh rõ ràng; tuy nhiên, đổi từ `case ...:` sang `->` một cách máy móc có thể làm mất hành vi **fall-through**. Ngoài ra, việc đặt lời gọi hàm vào vị trí mới có thể giữ nguyên kết quả tính toán nhưng thay đổi log, trạng thái hoặc thời điểm phát sinh lỗi.

Bài học tập trung vào bài toán **kiểu kết quả của switch**, đồng thời bảo toàn hành vi khi tối ưu những nhánh dài. Ví dụ biên dịch được bằng Java 17+ và không cần cờ preview.

## 1. “Tương đương hành vi” gồm những gì?

Hai cách viết `switch` chỉ thực sự tương đương theo yêu cầu nghiệp vụ khi chúng bảo toàn những điều liên quan:

| Khía cạnh | Câu hỏi khi review |
|---|---|
| **Giá trị/kết quả** | Cùng đầu vào có tạo cùng giá trị, đúng kiểu cần sử dụng hay không? |
| **Thứ tự tác dụng phụ** | Log, metric, cập nhật biến, gọi API, ghi dữ liệu có xảy ra theo cùng trình tự không? |
| **Số lần thực thi** | Biểu thức chọn nhánh và những hàm có tác dụng phụ có còn được gọi đúng số lần không? |
| **Điều kiện thực thi** | Tác dụng phụ trước đây chỉ xảy ra ở một nhánh có bị chuyển ra ngoài để chạy ở mọi nhánh không? |
| **Ngoại lệ** | Có ném cùng loại lỗi, ở cùng giai đoạn, sau những tác dụng phụ tương ứng không? |
| **Luồng điều khiển** | `break`, fall-through, `return` và những thao tác sau `switch` có còn hoạt động như trước không? |

Trong ngữ cảnh có luồng đồng thời, gọi mạng, transaction hoặc trạng thái dùng chung, “bảo toàn thứ tự” còn phải xét khả năng quan sát từ tác vụ khác. Chạy thử một lần chỉ là bằng chứng ban đầu; cần kiểm thử và đánh giá theo hành vi thực tế của hệ thống.

### Tác dụng phụ là gì?

Một phép tính **thuần** như `a + b` (với các biến nguyên thủy đã có giá trị) tạo kết quả nhưng không tự ghi dữ liệu ra ngoài. Ngược lại:

~~~java
audit("start");      // Ghi sự kiện
counter++;           // Thay đổi trạng thái
int x = charge();    // Có thể gọi dịch vụ hoặc cập nhật dữ liệu
save(x);             // Ghi trạng thái
~~~

đều có thể ảnh hưởng tới những gì người dùng hoặc hệ thống quan sát. Các lời gọi này không thể tùy tiện đổi chỗ chỉ vì số `x` cuối cùng không đổi.

## 2. Hiểu đúng hai dạng switch trước khi tái cấu trúc

**Switch statement** thực hiện câu lệnh, không tự có giá trị trả về:

~~~java
int result;
switch (code) {
    case 1:
        result = 10;
        break;
    default:
        result = 0;
}
~~~

**Switch expression** trả về một giá trị:

~~~java
int result = switch (code) {
    case 1 -> 10;
    default -> 0;
};
~~~

Hai ví dụ này là **đoạn mã minh họa** đặt trong nơi đã khai báo `int code`.

Trong switch expression, nếu nhánh cần nhiều câu lệnh, hãy sử dụng block và `yield`:

~~~java
int result = switch (code) {
    case 1 -> {
        audit("start");
        int value = calculate(2);
        audit("end");
        yield value;
    }
    default -> 0;
};
~~~

Đoạn này minh họa cấu trúc; `audit` và `calculate` là các phương thức cần được định nghĩa trong chương trình sử dụng.

**Phân biệt:** `yield value;` cung cấp giá trị cho switch expression bao quanh; `break;` kết thúc switch statement và không trả giá trị; `return value;` trả giá trị từ phương thức. Không thể thay `yield` bằng `break` để tạo kết quả cho switch expression.

### Nhãn dấu hai chấm có fall-through

Cấu trúc:

~~~java
case 4:
    audit("pre-common");
case 5:
    result = shared();
    break;
~~~

có hai đường đi: chọn `4` sẽ ghi `pre-common` rồi chạy tiếp mã dưới `case 5`; chọn `5` sẽ chỉ gọi `shared()`. Nếu đổi cả hai thành `case 4, 5 -> shared();`, tác dụng phụ `audit("pre-common")` của nhánh `4` bị mất. Nếu chuyển dòng `audit` ra trước switch thì nhánh `5` lại ghi thêm sự kiện sai. Phải mô tả rõ **tác dụng phụ riêng** và **phần xử lý chung**.

## 3. Ví dụ trước–sau: cùng kết quả, cùng thứ tự tác dụng phụ

Tạo tệp **`SwitchSideEffectRefactor.java`**. Chương trình chứa đồng thời phiên bản cũ (`before`) và phiên bản được tái cấu trúc (`after`) để so sánh tự động.

~~~java
import java.util.ArrayList;
import java.util.List;

public class SwitchSideEffectRefactor {
    private static final List<String> events = new ArrayList<>();

    private static int select(int code) {
        events.add("select " + code);
        return code;
    }

    private static void audit(String message) {
        events.add("audit " + message);
    }

    private static int calculate(int input) {
        events.add("calculate " + input);
        return input * 10;
    }

    private static int shared() {
        audit("shared");
        return calculate(5);
    }

    // Phiên bản switch statement ban đầu.
    private static int before(int code) {
        int result;
        switch (select(code)) {
            case 1:
                audit("one");
                result = calculate(2);
                break;

            case 2:
            case 3:
                audit("group");
                int computed = calculate(3) + 1;
                audit("group done");
                result = computed;
                break;

            case 4:
                audit("pre-common");
                // Cố ý fall-through sang case 5.
            case 5:
                result = shared();
                break;

            default:
                audit("invalid");
                throw new IllegalArgumentException("invalid " + code);
        }
        audit("after");
        return result;
    }

    // Phiên bản switch expression, bảo toàn trình tự hành vi.
    private static int after(int code) {
        int result = switch (select(code)) {
            case 1 -> {
                audit("one");
                yield calculate(2);
            }

            case 2, 3 -> {
                audit("group");
                int computed = calculate(3) + 1;
                audit("group done");
                yield computed;
            }

            case 4 -> {
                audit("pre-common");
                yield shared();
            }

            case 5 -> shared();

            default -> {
                audit("invalid");
                throw new IllegalArgumentException("invalid " + code);
            }
        };
        audit("after");
        return result;
    }

    private static String invoke(boolean oldVersion, int code) {
        try {
            int value = oldVersion ? before(code) : after(code);
            return Integer.toString(value);
        } catch (IllegalArgumentException ex) {
            return ex.getClass().getSimpleName() + ":" + ex.getMessage();
        }
    }

    public static void main(String[] args) {
        for (int code : new int[] {1, 2, 3, 4, 5, 9}) {
            events.clear();
            String oldResult = invoke(true, code);
            String oldTrace = String.join(" > ", events);

            events.clear();
            String newResult = invoke(false, code);
            String newTrace = String.join(" > ", events);

            boolean same = oldResult.equals(newResult)
                    && oldTrace.equals(newTrace);

            System.out.println(
                    code + " | result=" + oldResult + " | same=" + same
            );
            System.out.println("  " + oldTrace);
        }
    }
}
~~~

Tại thư mục chứa file, biên dịch và chạy bằng một JDK hỗ trợ mục tiêu Java 17:

~~~bash
javac --release 17 SwitchSideEffectRefactor.java
java SwitchSideEffectRefactor
~~~

**Standard output chính xác:**

~~~text
1 | result=20 | same=true
  select 1 > audit one > calculate 2 > audit after
2 | result=31 | same=true
  select 2 > audit group > calculate 3 > audit group done > audit after
3 | result=31 | same=true
  select 3 > audit group > calculate 3 > audit group done > audit after
4 | result=50 | same=true
  select 4 > audit pre-common > audit shared > calculate 5 > audit after
5 | result=50 | same=true
  select 5 > audit shared > calculate 5 > audit after
9 | result=IllegalArgumentException:invalid 9 | same=true
  select 9 > audit invalid
~~~

**Phân tích theo đầu vào:**

- **`1`:** Gọi `select(1)` đúng một lần, ghi `audit("one")`, rồi mới gọi `calculate(2)` để có giá trị `20`. Sau khi switch kết thúc bình thường, ghi `audit("after")`.
- **`2` hoặc `3`:** Cả hai nhãn dùng chung nhánh. Thứ tự là `audit("group")` → `calculate(3)` → `audit("group done")` → cập nhật kết quả `31` → `audit("after")`. Biến `computed` giữ giá trị trước khi log hoàn tất.
- **`4`:** Bản đầu cố ý chạy từ `case 4` xuống `case 5`. Bản mới tạo nhánh riêng với `audit("pre-common")` trước lời gọi `shared()`, nên thứ tự vẫn đúng.
- **`5`:** Bản đầu đi thẳng vào `case 5`; bản mới dùng `case 5 -> shared()`. Không xuất hiện sự kiện `pre-common`.
- **`9`:** Hai phiên bản đều ghi `audit("invalid")` trước khi ném `IllegalArgumentException`. Không chạy `audit("after")` vì switch không hoàn thành bình thường.

Trường hợp `9` minh họa rằng việc bảo toàn ngoại lệ không chỉ là giữ thông báo lỗi; **thời điểm phát sinh lỗi so với các tác dụng phụ** cũng có ý nghĩa.

### Ý nghĩa của phép kiểm tra `same=true`

Trong chương trình mẫu, kết quả so sánh bao gồm **giá trị hoặc loại/thông báo ngoại lệ** và chuỗi các sự kiện trong `events`. Đây là một phép kiểm tra minh bạch, dễ tái hiện cho các đầu vào đã liệt kê. Nó chưa chứng minh toàn bộ hành vi với mọi đầu vào, luồng đồng thời, tài nguyên hay tích hợp bên ngoài. Dự án thực tế cần kiểm thử phù hợp với miền dữ liệu và tác dụng phụ của chính nó.

## 4. Các bước chuyển đổi một switch dài

### Bước 1 — Chốt “hợp đồng hành vi” trước khi sửa

Với từng nhánh, ghi lại:

1. Điều kiện chọn nhánh và việc **biểu thức selector được đánh giá một lần**.
2. Những câu lệnh có tác dụng phụ theo đúng thứ tự.
3. Có hay không có fall-through, và nếu có thì vào nhãn nào.
4. Giá trị cuối cùng gán cho kết quả, phương thức được gọi để tính giá trị, kiểu kết quả.
5. Điểm kết thúc: `break`, `return`, `throw` hoặc logic chạy tiếp sau switch.

Ví dụ từ chương trình mẫu:

| Đầu vào | Chuỗi tác dụng phụ trong nhánh | Giá trị hoặc ngoại lệ |
|---|---|---|
| `1` | `audit one` → `calculate 2` | `20` |
| `2, 3` | `audit group` → `calculate 3` → `audit group done` | `31` |
| `4` | `audit pre-common` → `audit shared` → `calculate 5` | `50` |
| `5` | `audit shared` → `calculate 5` | `50` |
| Khác | `audit invalid` | Ném `IllegalArgumentException` |

Bảng này là bản đồ hành vi cần bảo vệ. Hãy thêm những tác dụng phụ có thật của ứng dụng (cập nhật cơ sở dữ liệu, phát sự kiện, I/O) nếu có.

### Bước 2 — Giữ nguyên selector và những thao tác trước switch

Bản đầu dùng `switch (select(code))`. Bản mới cũng giữ `switch (select(code))` để hàm `select` chạy một lần tại cùng vị trí trong luồng phương thức. Tránh gọi `select(code)` lại bên trong nhánh hoặc chuyển nó qua những thao tác có thể quan sát.

Trong Java, biểu thức selector của switch được đánh giá trước khi chọn nhánh. **Không** được giả định lời gọi trong selector là “chỉ đọc” hoặc có thể đánh giá lại an toàn: bản thân nó có thể ghi log, tăng bộ đếm hoặc ném ngoại lệ.

### Bước 3 — Gom những nhãn có cùng toàn bộ hành vi

Với:

~~~java
case 2:
case 3:
    audit("group");
    int computed = calculate(3) + 1;
    audit("group done");
    result = computed;
    break;
~~~

cả hai đầu vào đều thực hiện **chính xác cùng phần thân**, nên có thể thay bằng:

~~~java
case 2, 3 -> {
    audit("group");
    int computed = calculate(3) + 1;
    audit("group done");
    yield computed;
}
~~~

Đây là một nhánh của **switch expression**, không phải chương trình Java độc lập. Việc gom nhãn chỉ đúng nếu hai nhánh thực sự có cùng trình tự và cùng kết quả, không có câu lệnh riêng bị bỏ qua.

### Bước 4 — Chuyển fall-through có tác dụng phụ thành các nhánh rõ ràng

Với `case 4` và `case 5`, không được gom đơn giản vì nhánh `4` còn có `audit("pre-common")`. Trong switch expression dạng mũi tên, hãy thể hiện hai đường đi:

~~~java
case 4 -> {
    audit("pre-common");
    yield shared();
}
case 5 -> shared();
~~~

Tái sử dụng phương thức `shared()` để khỏi sao chép phần xử lý chung. Khi trích xuất phương thức, vẫn phải giữ **đúng vị trí được gọi**, số lần gọi và thứ tự nội bộ.

Trong một switch expression dùng nhãn dấu hai chấm, `fall-through` vẫn có thể tồn tại và nhánh cần `yield` để cung cấp kết quả. Chỉ chuyển sang dạng mũi tên sau khi đã mô hình hóa đầy đủ những đường đi này.

### Bước 5 — Giữ những thao tác sau switch ở nguyên vị trí

Trong cả hai phương thức mẫu, `audit("after")` chạy **sau khi đã có kết quả**. Vì vậy bản mới lưu kết quả vào biến rồi gọi `audit("after")` trước khi `return`:

~~~java
int result = switch (code) {
    case 1 -> 10;
    default -> 0;
};
audit("after");
return result;
~~~

Đây là đoạn minh họa trong một phương thức đã có biến `code` và phương thức `audit`.

Nếu đổi thành `return switch (code) {...};` rồi bỏ đoạn code phía sau, hành vi thay đổi vì `audit("after")` không còn xảy ra. Chỉ dùng kiểu rút gọn `return switch` khi thật sự không còn thao tác nào cần chạy sau phép chọn nhánh và điều đó đúng với hợp đồng của phương thức.

### Bước 6 — Kiểm tra kiểu kết quả trước khi hoàn tất

Switch expression là một **biểu thức có kiểu**. Khi gán kết quả vào biến `int result`, tất cả những đường đi tạo giá trị phải tương thích với ngữ cảnh `int`. Các nhánh trong chương trình mẫu đều trả `int` từ `calculate(...)`, từ `computed` hoặc từ `shared()`; nhánh `default` ném ngoại lệ nên không phải tạo một giá trị `int`.

Ví dụ hợp lệ khi cần `long`:

~~~java
long result = switch (code) {
    case 1 -> 10L;
    default -> 0L;
};
~~~

Đoạn này minh họa khi có `int code`. Trong mã phức tạp, đừng đổi kiểu kết quả chỉ để khiến trình biên dịch chấp nhận: chuyển từ `int` sang `long`, từ số nguyên thủy sang lớp bao hoặc thêm `null` có thể tác động đến API gọi tiếp, so sánh và xử lý ngoại lệ. Nếu kiểu cần giữ là `int`, hãy kiểm tra sự tương thích của từng biểu thức `yield` với `int`.

## 5. Ba phép “tối ưu” làm hỏng thứ tự

### Sai lầm A — Đưa lời gọi có tác dụng phụ ra ngoài switch

**Bản cần giữ:**

~~~java
int result = switch (code) {
    case 1 -> calculate(2);
    default -> 0;
};
~~~

**Bản sai về mặt hành vi:**

~~~java
int calculated = calculate(2); // Bị gọi ở tất cả đầu vào!
int result = switch (code) {
    case 1 -> calculated;
    default -> 0;
};
~~~

Hai đoạn này là ví dụ minh họa với `int code` và `calculate` đã định nghĩa. Khi `code != 1`, bản đầu không gọi `calculate(2)`, còn bản sau có. Dù `result` vẫn là `0`, log hoặc trạng thái đã bị thay đổi.

### Sai lầm B — Tính kết quả sau khi ghi log “kết thúc”

**Thứ tự cần giữ:**

~~~java
audit("group");
int value = calculate(3) + 1;
audit("group done");
yield value;
~~~

**Thứ tự bị thay đổi:**

~~~java
audit("group");
audit("group done");
yield calculate(3) + 1;
~~~

Đây là các đoạn mã trong block của switch expression. Ở bản đầu, `calculate(3)` xảy ra **trước** `audit("group done")`; ở bản sau, nó xảy ra **sau**. Nếu `calculate` gọi dịch vụ, cập nhật trạng thái hoặc ném lỗi, thay đổi này đặc biệt nghiêm trọng.

### Sai lầm C — Gom các nhánh mà không xét fall-through

**Bản có hành vi riêng của nhánh `4`:**

~~~java
case 4:
    audit("pre-common");
case 5:
    result = shared();
    break;
~~~

**Bản sai:**

~~~java
case 4, 5 -> shared();
~~~

Bản sai bỏ mất `audit("pre-common")` khi chọn `4`. Bản đúng là hai nhánh mũi tên riêng đã trình bày ở bước 4.

### Sai lầm D — Đổi thứ tự ghi log và ném ngoại lệ

Nếu nhánh cũ ghi `audit("invalid")` rồi mới ném lỗi, bản mới phải giữ thứ tự đó:

~~~java
default -> {
    audit("invalid");
    throw new IllegalArgumentException("invalid " + code);
}
~~~

Không bỏ log hoặc dời nó xuống sau `throw` (mã sau `throw` trực tiếp sẽ không thể thực thi), và không chuyển log sang một nhánh khác chỉ vì thông báo lỗi vẫn giống.

## 6. Kiểu kết quả, phạm vi và xử lý ngoại lệ

### 6.1. Switch expression phải bao phủ đủ đường đi

Trong các ví dụ chọn `int`, những giá trị không liệt kê được xử lý bằng `default`. Switch expression phải bao phủ toàn bộ giá trị hợp lệ của selector (**exhaustive**) và không được hoàn thành bình thường mà không tạo kết quả.

Nhánh nào không tạo giá trị có thể kết thúc bằng `throw`; điều này hợp lệ:

~~~java
int value = switch (code) {
    case 0 -> 0;
    default -> throw new IllegalArgumentException("Unsupported");
};
~~~

Nếu bỏ `default` ở biểu thức switch trên `int` khi chỉ liệt kê một vài hằng số, chương trình không biên dịch vì thiếu trường hợp cần xử lý. Với một kiểu `enum` đã liệt kê đủ các hằng số, compiler có thể xác nhận exhaustiveness mà không có `default`, nhưng vẫn cần xem lại khi enum phát triển.

### 6.2. Không trả nhầm kiểu dữ liệu

Trong nhánh dạng block, viết `yield value;` với giá trị tương thích với kiểu kết quả của switch. Ví dụ sau **cố ý sai**:

~~~java
// Không biên dịch: cần kết quả int nhưng một nhánh yield String.
int value = switch (code) {
    case 0 -> 0;
    default -> {
        yield "unknown";
    }
};
~~~

Nếu chương trình yêu cầu `int`, hãy giữ một giá trị nguyên phù hợp hoặc ném ngoại lệ có chủ đích. Không trộn kiểu một cách ngẫu nhiên chỉ để rút ngắn switch.

Đặc biệt, với kết quả nguyên thủy như `int`, việc chuyển qua wrapper và đưa `null` vào một đường đi có thể phát sinh lỗi unboxing tại runtime; cân nhắc thiết kế kết quả và yêu cầu không-null của phương thức.

### 6.3. Block riêng giúp tách phạm vi biến

Với nhiều nhánh mũi tên chứa nhiều câu lệnh, block `{ ... }` tạo phạm vi riêng cho biến cục bộ; mỗi block có thể dùng tên `value` mà không xung đột. Khi dùng nhãn dấu hai chấm theo nhóm, các nhãn không tự tạo scope riêng, nên việc trích xuất block có thể giải quyết va chạm tên biến và làm rõ nơi biến còn hiệu lực.

Tránh cố gắng dùng một biến kết quả có thể chưa được gán ở một đường đi; trong switch expression, cho mỗi nhánh `yield` một giá trị đúng kiểu hoặc ném lỗi một cách rõ ràng.

### 6.4. Giữ nguyên thứ tự kiểm tra null và ngoại lệ

Nếu selector là một tham chiếu có thể `null`, thay đổi cách kiểm tra `null` hoặc thay vị trí lời gọi selector có thể đổi thời điểm phát sinh `NullPointerException`. Khi ứng dụng cần tương thích với Java 17, không dùng `case null` như thể đó là cú pháp phổ biến của Java 17. Với các phiên bản Java hiện đại mới hơn, các khả năng pattern matching for switch mở rộng cách xử lý `null`, nhưng không vì thế mà tự đổi hợp đồng của mã đang tái cấu trúc.

Nếu nhánh cũ dùng `try`-with-resources hoặc `finally`, phải kiểm tra thời điểm đóng tài nguyên, ghi log và lan truyền ngoại lệ. Chuyển một lời gọi qua ranh giới `try`/`finally` có thể làm đổi thứ tự và loại lỗi thực tế dù giá trị thành công không đổi.

## 7. Quy trình kiểm chứng trước khi coi hai bản tương đương

Một quy trình thực tế:

1. **Chụp hành vi gốc:** Thiết lập đầu vào đại diện cho mọi nhánh, ghi lại giá trị, loại/thông báo ngoại lệ, trạng thái đối tượng và thứ tự các tương tác quan sát được.
2. **Lập bản đồ fall-through:** Đánh dấu mỗi nhãn `case ...:` có thể chạy tới nhãn tiếp theo. Phân biệt nhóm nhãn rỗng để dùng chung phần thân với nhánh có tác dụng phụ rồi mới fall-through.
3. **Chuyển đổi từng nhóm:** Giữ selector, chuyển câu lệnh theo đúng thứ tự, đặt `yield` tại điểm kết quả thật sự có sẵn, và giữ các thao tác sau switch.
4. **Kiểm tra kết quả và kiểu:** Đảm bảo mọi đường đi bình thường có giá trị đúng kiểu; kiểm tra `default`, nhánh ném lỗi và tình huống đầu vào đặc biệt.
5. **So sánh dấu vết:** Dùng test double, spy, event list hoặc log test để đối chiếu *đúng thứ tự* và *đúng số lần gọi*. Không chỉ so sánh một biến kết quả.
6. **Kiểm tra tích hợp:** Nếu nhánh thao tác database, filesystem, network hoặc shared state, chạy kiểm thử phù hợp để xác nhận ranh giới transaction, thời điểm phát sự kiện và ngoại lệ.

### Ma trận ca kiểm thử tối thiểu

| Ca | Cần chứng minh |
|---|---|
| Mỗi nhánh độc lập | Đúng giá trị, không phát sinh lời gọi của nhánh khác |
| Nhiều nhãn chung một thân | Tất cả giá trị được gom đều có cùng hành vi |
| Fall-through có chủ đích | Nhánh đầu chạy tác dụng phụ riêng rồi tới phần chung; nhánh sau chỉ chạy phần chung |
| `default` | Cùng loại và thời điểm ngoại lệ; log đã ghi trước lỗi vẫn tồn tại |
| Selector có tác dụng phụ | Chỉ đánh giá một lần, tại đúng vị trí |
| Lỗi giữa nhánh | Những tác dụng phụ trước lỗi vẫn xảy ra; những thao tác sau lỗi không chạy |
| Kiểu kết quả biên | Không thay đổi kiểu API hoặc phát sinh boxing/unboxing ngoài ý muốn |
| Đường đi sau switch | Cùng thao tác hậu xử lý trước khi trả kết quả |

Đối với chương trình mẫu, ma trận `1, 2, 3, 4, 5, 9` đi qua tất cả đường đi chính. Khi ứng dụng dùng dữ liệu bên ngoài, hãy bổ sung giá trị biên, lỗi từ dependency và thử nghiệm với trạng thái độc lập cho mỗi lần chạy; tránh để một lần thử tác động đến lần thử khác.

## 8. Bài tập tự kiểm tra

**Câu 1.** Bản cũ thực hiện `audit("begin")`, rồi `calculate(4)`, rồi `audit("end")`. Đoạn mới dưới đây có tương đương không?

~~~java
case 1 -> {
    audit("begin");
    audit("end");
    yield calculate(4);
}
~~~

**Đáp án:** Không. `calculate(4)` bị chuyển xuống sau `audit("end")`. Cần lưu giá trị từ `calculate(4)` trước khi ghi `end`, sau đó `yield` giá trị đã lưu.

**Câu 2.** Bản đầu có `case 7: audit("special"); case 8: result = shared(); break;`. Có thể thay bằng `case 7, 8 -> shared();` không?

**Đáp án:** Không. Nhánh `7` sẽ mất `audit("special")`. Dùng nhánh `7 -> { audit("special"); yield shared(); }` và `8 -> shared()`, đồng thời giữ các thao tác bên trong `shared()` đúng như cũ.

**Câu 3.** Khi chuyển từ switch statement sang switch expression, có thể thay mọi `break;` thành `yield result;` ngay lập tức không?

**Đáp án:** Không nên chuyển máy móc. Phải xác định `break` thuộc switch/loop nào, nhánh có fall-through hay không, biến `result` được tính khi nào, điều gì chạy sau switch và liệu mọi đường đi bình thường đều trả kết quả đúng kiểu.

**Câu 4.** Nếu hai phiên bản cùng trả `31`, vậy đã đủ chứng minh tương đương chưa?

**Đáp án:** Chưa. Một bản có thể ghi log trước khi gọi dịch vụ, bản kia ghi sau; có thể gọi dịch vụ nhiều lần; hoặc có thể ném lỗi tại thời điểm khác. Cần đối chiếu tác dụng phụ, thứ tự và số lần gọi.

**Câu 5.** Vì sao trong phương thức `after`, ta vẫn giữ `audit("after")` sau phép gán `result = switch (...)`?

**Đáp án:** Vì hành vi gốc ghi sự kiện này sau khi switch hoàn tất bình thường nhưng trước khi trả kết quả. Nếu rút gọn bằng `return switch (...)` và bỏ nó, trace sẽ khác.

## Ghi nhớ

**Một switch expression đúng kiểu chưa chắc tương đương với switch cũ.** Hãy coi **giá trị**, **đường đi**, **ngoại lệ** và **chuỗi tác dụng phụ** là một hợp đồng thống nhất. Chỉ gom các nhãn có cùng hành vi, biểu diễn fall-through có chủ đích bằng nhánh tường minh, giữ các lời gọi có tác dụng phụ tại vị trí cũ và xác nhận bằng các bài kiểm thử so sánh thứ tự thực thi.

Tài liệu ngôn ngữ tham khảo: [OpenJDK JEP 361 — Switch Expressions](https://openjdk.org/jeps/361) (switch expression và `yield` được chuẩn hóa từ Java 14); [Java Language Specification, `14.11 — The switch Statement](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.11) và [`15.28 — switch Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.28) (đặc tả Java 17).