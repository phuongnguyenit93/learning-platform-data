# Biến cục bộ và yêu cầu được gán giá trị chắc chắn trong try/catch Java

Khi dùng `try/catch`, một biến cục bộ có thể **được khai báo** ở đầu phương thức nhưng chỉ **được gán giá trị** trong một số nhánh. Nếu chương trình đọc biến sau `try/catch`, trình biên dịch Java phải chứng minh biến đó đã được gán trên **mọi đường thực thi có thể đi tới điểm đọc**. Quy tắc này gọi là **definite assignment** (DA, gán giá trị chắc chắn).

Ví dụ phổ biến:

~~~java
int result;
try {
    result = Integer.parseInt(text);
} catch (NumberFormatException e) {
    System.out.println("Không phải số nguyên");
}
System.out.println(result); // Lỗi biên dịch: result có thể chưa được gán.
~~~

Đây là đoạn minh họa nằm trong phương thức có biến `text`. Nếu `Integer.parseInt(text)` ném `NumberFormatException`, điều khiển đi vào `catch` **trước khi phép gán `result = ...` hoàn tất**; khối `catch` chỉ in thông báo, nên tại `System.out.println(result)`, biến có thể chưa có giá trị. Java từ chối ngay khi biên dịch, kể cả bạn chỉ định gọi phương thức với chuỗi số hợp lệ.

Bài học giải thích cách Java phân tích các đường luồng điều khiển trong `try/catch`, cách sửa mã đúng nghiệp vụ, tác động của `return`, `throw`, `finally`, biến `final`, phạm vi biến và các trường hợp dễ nhầm.

## 1. Định nghĩa: definite assignment khác giá trị mặc định

**Biến cục bộ (local variable)** khai báo trong phương thức hoặc khối lệnh không được Java tự gán `0`, `false` hay `null` chỉ vì kiểu của nó là `int`, `boolean` hay kiểu tham chiếu.

~~~java
static void example() {
    int count;
    // System.out.println(count); // Không biên dịch: chưa được gán.
    count = 3;
    System.out.println(count);     // Hợp lệ.
}
~~~

Trong ví dụ, `count` tồn tại trong phạm vi cú pháp từ vị trí khai báo, nhưng chỉ được phép đọc sau khi Java xác định phép gán cần thiết đã xảy ra.

Cần phân biệt ba khái niệm:

| Khái niệm | Ý nghĩa |
| --- | --- |
| **Scope (phạm vi)** | Vị trí trong mã nơi tên biến có thể được tham chiếu |
| **Definite assignment** | Tại điểm đọc, trình biên dịch chứng minh biến đã được gán trên mọi đường tới được |
| **Giá trị runtime** | Giá trị cụ thể khi đường thực thi thật sự chạy tới đó |

Ví dụ: một biến khai báo ngoài `try` có thể còn trong phạm vi sau `catch`, nhưng **vẫn không được đọc** nếu chưa đạt điều kiện DA.

Đừng nhầm với **field** của một đối tượng hoặc `static field`: field được khởi tạo mặc định nếu không được gán tường minh (`0`, `false`, `null` tùy kiểu). Tương tự, phần tử mảng mới tạo cũng có giá trị mặc định. Quy tắc cần chứng minh gán trước khi đọc ở đây đặc biệt quan trọng đối với **biến cục bộ**.

## 2. Vì sao `try/catch` làm xuất hiện đường chưa gán?

Xem đoạn mã:

~~~java
int port;
try {
    port = Integer.parseInt(input);
} catch (NumberFormatException e) {
    System.out.println("Sai định dạng");
}
use(port);
~~~

Đây là đoạn **không độc lập**: giả sử `input` và phương thức `use` tồn tại. Dù `port` được gán trong khối `try`, có hai đường đi:

~~~text
                  int port;  // chưa có giá trị
                           |
                    Integer.parseInt(input)
                       /              \
                Phân tích được       Ném NumberFormatException
                      |                       |
               port = kết quả         catch in thông báo
                      |                       |
                      +-----------+-----------+
                                  |
                               use(port)
~~~

Đường bên phải đi tới `use(port)` mà không gán `port`. Do đó mã **không biên dịch** với lỗi đại loại `variable port might not have been initialized`.

Hai điểm quan trọng:

1. **Phép gán chỉ hoàn tất khi vế phải được đánh giá thành công.** Với `port = Integer.parseInt(input);`, nếu `parseInt` ném lỗi, `port` chưa nhận kết quả từ phép gán đó.
2. **Trình biên dịch kiểm tra mọi đường có thể kết thúc bình thường tại điểm dùng**, không chỉ đường bạn mong muốn xảy ra.

Nếu xử lý lỗi trong `catch` bằng cách in log rồi tiếp tục, bạn vẫn phải bảo đảm biến có giá trị hợp lệ hoặc chuyển hướng điều khiển để không đọc biến chưa gán.

## 3. Cách sửa 1: gán giá trị trong cả `try` và `catch`

Khi nghiệp vụ có giá trị thay thế hợp lệ:

~~~java
static int parseOrFallback(String input) {
    int result;
    try {
        result = Integer.parseInt(input);
    } catch (NumberFormatException e) {
        result = -1;
    }
    return result;
}
~~~

Phương thức này có thể đặt trong một lớp Java 17+. Phân tích:

- Nếu `parseInt` thành công, `result` nhận số nguyên vừa đọc.
- Nếu `parseInt` ném `NumberFormatException`, khối `catch` gán `-1`.
- Trên **mọi đường kết thúc bình thường** của `try/catch`, `result` đã được gán trước `return result;`. Đường nào gặp ngoại lệ khác không được bắt thì kết thúc bất thường và không đi tới lệnh `return`.

Đây là một phương án đúng về mặt biên dịch. Tuy nhiên về nghiệp vụ, `-1` chỉ là fallback an toàn nếu API quy định giá trị đó là giá trị thay thế hoặc dấu hiệu lỗi hợp lệ. Nếu `-1` cũng có thể là dữ liệu bình thường, caller sẽ khó phân biệt thành công với thất bại. Khi đó nên dùng kết quả có cấu trúc, xử lý lỗi ở tầng caller hoặc ném ngoại lệ phù hợp.

### Có thể gán giá trị ngay lúc khai báo

~~~java
static int parseWithDefault(String input) {
    int result = -1;
    try {
        result = Integer.parseInt(input);
    } catch (NumberFormatException e) {
        System.out.println("Sử dụng giá trị mặc định");
    }
    return result;
}
~~~

`result` đã được gán `-1` trước `try`, nên dù parse thất bại vẫn có giá trị để trả về. Cách này có ưu điểm đơn giản, nhưng cần **chọn mặc định có ý nghĩa**; đừng viết `int result = 0;` chỉ để làm compiler im lặng khi `0` có thể che lỗi.

## 4. Cách sửa 2: kết thúc nhánh lỗi bằng `return`

Nếu parsing thất bại thì phương thức có thể trả ngay giá trị thay thế:

~~~java
static int parseOrReturn(String input) {
    int result;
    try {
        result = Integer.parseInt(input);
    } catch (NumberFormatException e) {
        return -1;
    }
    return result;
}
~~~

Đoạn này **biên dịch** dù không gán `result` trong `catch`. Lý do: nhánh `catch` có `return -1;`, nên nhánh đó **không thể tới** `return result;` ở cuối. Mọi đường thực thi còn có thể tới lệnh cuối đều đã gán `result` thành công.

Đây là khác biệt giữa:

- “**Biến phải được gán trên mọi đường đi trong phương thức**” — phát biểu này quá rộng.
- “**Biến phải được gán trên mọi đường có thể thực sự tới điểm đọc**” — đây mới là ý nghĩa cần nhớ.

Không cần gán một giá trị cho biến ở đường đã `return` và không bao giờ đọc biến nữa.

## 5. Cách sửa 3: kết thúc nhánh lỗi bằng `throw`

Khi không có fallback hợp lệ, nhánh xử lý có thể chuyển lỗi lên caller:

~~~java
static int parseOrThrow(String input) {
    int result;
    try {
        result = Integer.parseInt(input);
    } catch (NumberFormatException cause) {
        throw new IllegalArgumentException(
                "Không thể đọc số nguyên: " + input, cause);
    }
    return result;
}
~~~

Khi parse thành công, `result` được gán và trả về. Khi parse thất bại, `catch` ném ngoại lệ mới, **không thể đi tiếp bình thường** đến `return result;`. Vì thế trình biên dịch chấp nhận đoạn mã.

Constructor `IllegalArgumentException(String, Throwable)` giữ `cause` là `NumberFormatException` gốc. Việc giữ nguyên nhân giúp chẩn đoán lỗi thay vì chỉ in log rồi trả một kết quả không rõ ý nghĩa.

Bạn cũng có thể dùng `throw cause;` để ném lại đối tượng đã bắt, nếu hợp đồng của phương thức cho phép và việc giữ loại lỗi gốc có ý nghĩa. Với checked exception, cần tiếp tục tuân thủ quy tắc `catch` hoặc `throws` tương ứng; điều đó độc lập với DA.

## 6. Ví dụ Java 17+ chạy độc lập

Tạo tệp **`DefiniteAssignmentDemo.java`**:

~~~java
public class DefiniteAssignmentDemo {
    public static void main(String[] args) {
        for (String input : new String[] {"18", "oops"}) {
            System.out.println(
                    "fallback(" + input + ")=" + withFallback(input));
            try {
                System.out.println(
                        "propagate(" + input + ")=" + withPropagation(input));
            } catch (IllegalArgumentException e) {
                System.out.println(
                        "propagate(" + input + ") failed: " + e.getMessage());
            }
        }

        System.out.println(
                "returnOnError(oops)=" + returnOnError("oops"));
        System.out.println(
                "finalLocal(oops)=" + useFinalLocal("oops"));
        System.out.println(
                "handled(9)=" + handled("9"));
    }

    static int withFallback(String raw) {
        int result;
        try {
            result = Integer.parseInt(raw);
        } catch (NumberFormatException e) {
            result = -1;
        }
        return result;
    }

    static int withPropagation(String raw) {
        int result;
        try {
            result = Integer.parseInt(raw);
        } catch (NumberFormatException e) {
            throw new IllegalArgumentException(
                    "bad integer: " + raw, e);
        }
        return result;
    }

    static int returnOnError(String raw) {
        int result;
        try {
            result = Integer.parseInt(raw);
        } catch (NumberFormatException e) {
            return -1;
        }
        return result;
    }

    static int useFinalLocal(String raw) {
        final int result = withFallback(raw);
        return result;
    }

    static int handled(String raw) {
        int result;
        try {
            if (raw.isBlank()) {
                return -1;
            }
            result = Integer.parseInt(raw);
        } catch (NumberFormatException e) {
            result = 0;
        }
        return result;
    }
}
~~~

Biên dịch, chạy từ thư mục chứa tệp:

~~~bash
javac DefiniteAssignmentDemo.java
java DefiniteAssignmentDemo
~~~

**Stdout:**

~~~text
fallback(18)=18
propagate(18)=18
fallback(oops)=-1
propagate(oops) failed: bad integer: oops
returnOnError(oops)=-1
finalLocal(oops)=-1
handled(9)=9
~~~

### Tại sao chương trình hợp lệ?

| Phương thức | Khi thành công | Khi có lỗi được bắt | Vì sao đọc biến an toàn? |
| --- | --- | --- | --- |
| `withFallback` | Gán `result` từ parse | Gán `result = -1` | Mọi nhánh bình thường đều gán |
| `withPropagation` | Gán rồi trả | `throw` ngoại lệ khác | Nhánh lỗi không đến điểm đọc |
| `returnOnError` | Gán rồi trả ở cuối | `return -1` ngay | Nhánh lỗi không đến điểm đọc |
| `useFinalLocal` | Gọi hàm lấy kết quả rồi gán `final result` | Hàm được gọi đã quyết định fallback | Biến `final` được khởi tạo một lần, trước khi đọc |
| `handled` | Gán qua `parseInt` | Gán `0` nếu parse thất bại; đầu vào trống `return -1` sớm | Mọi đường đến `return result` đều gán |

Các dòng stdout có thứ tự xác định vì chương trình xử lý lần lượt mảng chuỗi `{"18", "oops"}` và chỉ in các kết quả đã bắt. `Integer.parseInt("oops")` ném `NumberFormatException`, một lớp con của `IllegalArgumentException`. Vì `withPropagation` bọc lỗi đó thành `IllegalArgumentException`, nhánh `catch` trong `main` nhận được ngoại lệ như mong đợi.

## 7. Biến khai báo ngoài `try` và biến khai báo bên trong `try`

**Phạm vi** là một vấn đề khác với việc gán chắc chắn.

~~~java
static void scopeExample(String input) {
    try {
        int parsed = Integer.parseInt(input);
        System.out.println(parsed);
    } catch (NumberFormatException e) {
        System.out.println("Sai số");
    }

    // System.out.println(parsed); // Sai: parsed đã ngoài phạm vi.
}
~~~

Ở đây, `parsed` được khai báo bên trong khối `try`. Sau dấu `}` kết thúc khối, tên này không còn trong phạm vi. Kể cả nó chắc chắn được gán ở nhánh thành công, bạn cũng không thể tham chiếu tên `parsed` sau `try/catch`.

Ngược lại:

~~~java
static void scopeAndAssignment(String input) {
    int parsed;
    try {
        parsed = Integer.parseInt(input);
    } catch (NumberFormatException e) {
        parsed = -1;
    }
    System.out.println(parsed);
}
~~~

`parsed` được khai báo ngoài `try` nên vẫn trong phạm vi, đồng thời cả nhánh thành công lẫn nhánh bắt lỗi đều gán giá trị. Có **cả scope lẫn definite assignment** thì mới đọc biến được.

Tham số của `catch`, chẳng hạn `NumberFormatException e`, cũng chỉ có phạm vi trong chính khối `catch`. Đối tượng ngoại lệ do runtime chuyển vào tham số đó; không cần gán `e` thủ công trước khi dùng `e.getMessage()`.

## 8. Nhiều nhánh `catch`: mỗi đường phải được xét

Giả sử một thao tác có thể ném hai loại ngoại lệ khác nhau:

~~~java
static int readOrFallback(String text, boolean unavailable) {
    int result;
    try {
        if (unavailable) {
            throw new IllegalStateException("Nguồn không sẵn sàng");
        }
        result = Integer.parseInt(text);
    } catch (NumberFormatException e) {
        result = -1;
    } catch (IllegalStateException e) {
        result = -2;
    }
    return result;
}
~~~

Phương thức này hợp lệ. Nếu `Integer.parseInt` thành công, `result` nhận số; nếu thất bại do định dạng, nhận `-1`; nếu nguồn không sẵn sàng, nhận `-2`. Mọi đường hoàn tất bình thường của `try/catch` trước `return` đều có giá trị.

Nhưng nếu nhánh thứ hai chỉ ghi log:

~~~java
static int broken(String text, boolean unavailable) {
    int result;
    try {
        if (unavailable) {
            throw new IllegalStateException("Nguồn không sẵn sàng");
        }
        result = Integer.parseInt(text);
    } catch (NumberFormatException e) {
        result = -1;
    } catch (IllegalStateException e) {
        System.out.println("Nguồn lỗi");
    }
    return result; // Không biên dịch: nhánh catch thứ hai chưa gán.
}
~~~

thì `return result` có thể được thực thi sau `catch (IllegalStateException e)` mà chưa có phép gán. Cần gán giá trị có ý nghĩa, `return` hoặc `throw` ở nhánh đó.

**Đừng chỉ kiểm tra nhánh `catch` mà bạn cho là thường gặp.** Quy tắc DA phải xét tất cả đường đến điểm đọc theo phân tích luồng điều khiển của trình biên dịch.

## 9. Ngoại lệ ở vế phải của phép gán

Đây là điểm dễ bị bỏ qua:

~~~java
int value;
try {
    value = Integer.parseInt(input);
} catch (NumberFormatException e) {
    // value vẫn chưa được gán bởi phép gán ở trên.
}
~~~

Java đánh giá vế phải `Integer.parseInt(input)` trước khi hoàn tất gán vào `value`. Nếu lời gọi ném `NumberFormatException`, toàn bộ biểu thức gán không hoàn tất. Không thể suy ra rằng `value` đã “được gán dở” với một giá trị.

Ngay cả với biểu thức phức tạp:

~~~java
int result;
try {
    result = calculate(input);
} catch (IllegalArgumentException e) {
    // Không có bảo đảm result nhận giá trị từ calculate(input).
}
~~~

Đây là đoạn minh họa giả định `calculate` có thể ném `IllegalArgumentException`. Muốn đọc `result` sau đó, phải xử lý đường `catch` hoặc khởi tạo trước. Phân tích DA không dựa vào kết quả **có thể** sinh ra nếu hàm chạy thành công; nó yêu cầu kết quả **chắc chắn** tồn tại trên mọi đường tới điểm đọc.

## 10. Biến `final` cục bộ: chắc chắn đã gán và không gán hai lần

`final` không tạo ngoại lệ đặc biệt cho `try/catch`; nó bổ sung yêu cầu **không được gán lại** sau khi biến đã có giá trị. Một biến `final` cục bộ chưa khởi tạo khi khai báo thường được gọi là *blank final*. Đối với đường thực thi hợp lệ, trình biên dịch còn kiểm tra điều kiện *definite unassignment* (chắc chắn chưa được gán) tại điểm gán để ngăn việc ghi lại.

Cách dễ đọc nhất:

~~~java
static int finalLocalExample(String text) {
    final int result = parseOrFallback(text);
    return result;
}

static int parseOrFallback(String text) {
    try {
        return Integer.parseInt(text);
    } catch (NumberFormatException e) {
        return -1;
    }
}
~~~

Đây là hai phương thức có thể đặt cùng một lớp. `final result` được gán **đúng một lần** từ giá trị mà `parseOrFallback` trả. Nếu hàm được gọi kết thúc bất thường, phép gán không hoàn tất và phương thức gọi cũng không đi tới `return result` theo đường đó.

### Đừng sửa bằng cách gán hai lần cho `final`

~~~java
final int result = 0;
try {
    result = Integer.parseInt(text); // Lỗi: không thể gán lại final.
} catch (NumberFormatException e) {
    System.out.println("Không hợp lệ");
}
~~~

Đây là **phản ví dụ không biên dịch**. Khởi tạo `result = 0` đã gán biến `final`; phép gán trong `try` là không hợp lệ.

Với một *blank final* được gán qua nhiều nhánh `try/catch`, các quy tắc definite assignment **và** definite unassignment có thể khó suy luận hơn, đặc biệt khi exception có thể phát sinh tại các vị trí khác nhau trong `try`. Không mặc định rằng mẫu gán một lần trên giấy sẽ luôn hợp lệ với `final`; với logic phức tạp, ưu tiên **mỗi nhánh trả kết quả** hoặc trích thành một hàm trả giá trị rồi khai báo `final result = ...` bên ngoài. Cách này tránh trạng thái biến nửa chừng và đơn giản hóa luồng điều khiển.

## 11. `finally` có giúp biến tự được gán không?

`finally` chủ yếu dùng cho việc dọn dẹp, hoặc thực hiện hành động cần chạy khi rời `try/catch`. Nó **không tự cấp giá trị mặc định** cho biến cục bộ và không làm trình biên dịch bỏ qua các đường chưa gán.

Ví dụ phương thức hợp lệ:

~~~java
static int parseWithCleanup(String input) {
    int result;
    try {
        result = Integer.parseInt(input);
    } finally {
        System.out.println("Hoàn tất bước đọc");
    }
    return result;
}
~~~

Nếu parse thành công, `result` được gán, `finally` chạy, rồi phương thức trả `result`. Nếu parse ném `NumberFormatException`, `finally` vẫn thường chạy nhưng ngoại lệ tiếp tục truyền ra; đường lỗi **không tới** `return result`. Vì vậy việc đọc `result` ở cuối hợp lệ theo phân tích DA.

Không nên chuyển `System.out.println(result)` vào `finally` trong ví dụ trên khi `result` có thể chưa được gán tại thời điểm `finally` chạy. Trước khi sử dụng biến trong `finally`, cũng phải bảo đảm nó đã được gán trên mọi đường có thể đến chính điểm đọc đó.

Một ví dụ gán mặc định trước khi vào `try`:

~~~java
static int parseWithFinally(String input) {
    int result = -1;
    try {
        result = Integer.parseInt(input);
    } catch (NumberFormatException e) {
        System.out.println("Dùng fallback");
    } finally {
        System.out.println("Xử lý xong");
    }
    return result;
}
~~~

Hàm trên có đường lỗi được xử lý với giá trị mặc định; `finally` không thay thế cho phép khởi tạo `result = -1`.

**Chú ý:** Viết `return` hoặc `throw` mới một cách thiếu cân nhắc trong `finally` có thể thay đổi/che kết quả hay ngoại lệ đang truyền. Đừng sử dụng `finally` như một mẹo để đánh lừa definite assignment; hãy thiết kế đường thành công và thất bại rõ ràng.

## 12. `try-with-resources` và phạm vi biến

Cú pháp try-with-resources mở rộng bài toán bằng tài nguyên được đóng tự động:

~~~java
static String firstLine(String input)
        throws java.io.IOException {
    try (java.io.BufferedReader reader =
                 new java.io.BufferedReader(
                         new java.io.StringReader(input))) {
        return reader.readLine();
    }
}
~~~

`reader` được khởi tạo trong phần khai báo tài nguyên của `try`, và phạm vi của biến tài nguyên gắn với cấu trúc try-with-resources theo luật Java. Phần thân có thể đọc `reader` vì quá trình khởi tạo tài nguyên phải thành công trước khi vào thân `try`.

Nếu constructor hoặc biểu thức khởi tạo tài nguyên thất bại, phần thân có thể không chạy; Java thực hiện các quy tắc đóng tài nguyên liên quan và lan truyền ngoại lệ thích hợp. Điều này không khiến một biến kết quả khai báo ngoài `try` tự động được gán.

Ví dụ khác:

~~~java
String content;
try (java.io.BufferedReader reader =
             new java.io.BufferedReader(
                     new java.io.StringReader(input))) {
    content = reader.readLine();
} catch (java.io.IOException e) {
    content = "fallback";
}
System.out.println(content);
~~~

Đây là **đoạn minh họa trong một phương thức có `input`**. Cả đường đọc thành công và đường `catch` đều gán `content`. Nhưng việc đọc và đóng tài nguyên có thể phát sinh checked exception, và những ngoại lệ không được bắt bởi đoạn `catch` sẽ khiến phương thức kết thúc bất thường. Trường hợp `reader.readLine()` trả `null` khi không có dòng cũng là một **giá trị đã được gán**, dù ứng dụng có thể cần kiểm tra `null` theo nghiệp vụ.

## 13. DA là kiểm tra tĩnh, không phải phép đo giá trị đầu vào

Java xác định definite assignment bằng quy tắc phân tích luồng của ngôn ngữ. Nó không chạy thử chương trình, không chờ dữ liệu thực tế và không có nhiệm vụ chứng minh những giả thiết tùy ý về người dùng.

Ví dụ:

~~~java
int parsed;
try {
    parsed = Integer.parseInt("123");
} catch (NumberFormatException e) {
    System.out.println("Đầu vào sai");
}
System.out.println(parsed); // Không dựa vào giả thiết "123" luôn hợp lệ.
~~~

Đây là **đoạn minh họa không biên dịch**. Dù người đọc biết `"123"` hợp lệ, trình biên dịch vẫn phân tích các đường exception theo quy tắc Java, thay vì chứng minh mọi hành vi runtime của thư viện bằng cách giải thích chuỗi literal.

Ngược lại, `int parsed = 123;` rõ ràng đã gán biến ngay khi khai báo. Phân tích DA cũng xét một số cấu trúc điều khiển cụ thể của ngôn ngữ như `if/else`, `return`, `throw`, biểu thức boolean và vòng lặp theo các quy tắc riêng; không phải mọi điều kiện đều được đánh giá như một định lý logic tùy ý.

**Nếu chương trình biên dịch**, Java bảo vệ bạn khỏi đọc một biến cục bộ chưa được gán trên đường đi được phân tích. Điều đó **không bảo đảm giá trị đã gán là đúng**. Gán `-1` chỉ để vượt compiler có thể giải quyết DA nhưng gây lỗi miền dữ liệu.

## 14. Một hướng viết gọn: trả trực tiếp từ mỗi nhánh

Khi không cần giữ biến trung gian, đây thường là mẫu dễ đọc:

~~~java
static int parseSafe(String text) {
    try {
        return Integer.parseInt(text);
    } catch (NumberFormatException e) {
        return -1;
    }
}
~~~

Tại đây không có biến cục bộ `result` phải được theo dõi qua nhiều đường. Nếu parsing thành công thì trả số, nếu thất bại thì trả fallback. Với checked exception, phương thức tương tự có thể `throws` để chuyển lỗi lên caller; chọn cách phù hợp theo hợp đồng.

Nếu cần phân biệt rõ thành công/thất bại mà `-1` cũng có thể là dữ liệu hợp lệ, hãy cân nhắc kết quả có cấu trúc:

~~~java
record ParseResult(boolean success, int value) {}

static ParseResult parseWithStatus(String text) {
    try {
        return new ParseResult(true, Integer.parseInt(text));
    } catch (NumberFormatException e) {
        return new ParseResult(false, 0);
    }
}
~~~

Đây là hai khai báo Java 17+ có thể đặt chung trong một lớp hoặc ở phạm vi phù hợp. `value = 0` khi `success = false` chỉ là thành phần không mang nghĩa kết quả thành công; caller nên kiểm tra `success` trước khi dùng `value`. Việc trả về từ cả hai nhánh tránh tình huống biến local chưa được gán, đồng thời hợp đồng báo lỗi rõ ràng hơn một sentinel mơ hồ.

## 15. Các lỗi thường gặp

**Lỗi 1 — Tưởng biến cục bộ tự động nhận `0`/`null`.**  
Biến cục bộ không có khởi tạo mặc định để đọc. Field và phần tử mảng mới tạo có quy tắc khác.

**Lỗi 2 — Tưởng khai báo bên ngoài `try` là đủ.**  
Khai báo quyết định phạm vi tên biến. Nó không bảo đảm biến được gán trên mọi đường sau `catch`.

**Lỗi 3 — Chỉ nhìn đường parse thành công.**  
Phải xét đường exception xảy ra **trước khi phép gán hoàn tất**. Khối `catch` chỉ ghi log có thể để biến chưa gán.

**Lỗi 4 — Gán mặc định không có ý nghĩa.**  
`int port = 0;` có thể làm mã biên dịch nhưng gây kết quả sai nếu `0` bị caller hiểu nhầm là cổng hợp lệ. Dùng fallback được hợp đồng chấp nhận hoặc phản ánh thất bại rõ ràng.

**Lỗi 5 — Nhầm `return`/`throw` với đường chạy tiếp.**  
Một nhánh `catch` đã `return` hay `throw` thì không thể đi đến câu lệnh sau `try/catch` theo đường đó. Không cần gán biến chỉ để thỏa một điểm đọc không thể tới.

**Lỗi 6 — Bỏ sót một nhánh `catch`.**  
Nếu nhánh thứ nhất gán biến nhưng nhánh thứ hai chỉ in log và kết thúc bình thường, biến vẫn có thể chưa gán tại điểm đọc.

**Lỗi 7 — Dùng biến ngoài phạm vi.**  
Biến khai báo trong khối `try` không thể được đọc sau khi ra khỏi khối đó, dù trong nhánh thành công nó đã có giá trị. Đây là lỗi scope, khác lỗi DA.

**Lỗi 8 — Dùng `final` rồi cố gán lại.**  
`final int x = 0;` sau đó `x = ...;` luôn sai. Nếu cần giá trị từ các nhánh, nên trả kết quả từ một hàm rồi gán `final` một lần.

**Lỗi 9 — Dựa vào `finally` để làm biến “chắc chắn có giá trị”.**  
`finally` không tự khởi tạo local. Khi đọc biến bên trong `finally` cũng phải xét đường lỗi xảy ra trước phép gán.

**Lỗi 10 — Cho rằng không có `catch` thì mọi đường phải gán biến.**  
Nếu ngoại lệ lan ra ngoài và phương thức kết thúc bất thường, đường đó không đến điểm đọc sau `try`. DA xét các đường có thể tới điểm đọc; không ép đường không thể tới phải gán.

**Lỗi 11 — Xóa lỗi biên dịch bằng cách làm rỗng `catch`.**  
`catch (Exception ignored) {}` không làm phép gán thất bại thành công. Nó có thể còn che mất lỗi gốc và khiến việc chẩn đoán khó hơn.

## 16. Câu hỏi tự kiểm tra

1. Vì sao `int x; System.out.println(x);` không biên dịch, còn đọc một field `int` mới tạo lại hợp lệ?
2. `int value; try { value = Integer.parseInt(text); } catch (NumberFormatException e) { }` có cho phép đọc `value` sau khối không? Tại sao?
3. Có cần gán `value` trong nhánh `catch` nếu nhánh đó kết thúc bằng `return -1;` không?
4. Nếu một nhánh `catch` ném tiếp `IllegalArgumentException`, nó có thể đi tới `return value;` sau `try/catch` không?
5. Trong mẫu `int result = -1; try { result = parseInt(text); } catch (...) {}`, mã biên dịch nhờ điều gì? Rủi ro nghiệp vụ là gì?
6. Biến `parsed` khai báo bên trong `try` có thể dùng ngoài `try/catch` không? Lỗi này thuộc phạm vi hay DA?
7. Một `try` có hai `catch`; nhánh thứ nhất gán `result` còn nhánh thứ hai chỉ log. Có đủ chắc chắn để đọc `result` sau đó không?
8. Vì sao vế phải ném exception khiến phép gán ở vế trái chưa hoàn tất?
9. Biến `final int x = 0;` có được gán lại ở `try` không? Cách nào có thể tránh phân nhánh gán cho `final`?
10. Khi nào có thể đọc biến sau `try/finally` dù thao tác trong `try` có thể ném ngoại lệ trước phép gán?
11. Vì sao việc `Integer.parseInt("123")` hầu như chắc chắn thành công với dữ liệu đó không phải cách đáng tin để bỏ qua phân tích DA?
12. Nếu fallback sentinel cũng là dữ liệu hợp lệ, có phương án kết quả nào rõ hơn?
13. Có thể dùng `return Integer.parseInt(text);` trong `try` và `return -1;` trong `catch` để tránh biến trung gian không?
14. Trong ví dụ chính, vì sao `withPropagation("oops")` không đọc biến chưa gán mặc dù nhánh lỗi không gán `result`?

### Gợi ý đáp án

1. Local không có khởi tạo mặc định, field có giá trị mặc định.
2. Không; parse có thể ném trước phép gán và `catch` không gán.
3. Không; `return` chấm dứt đường lỗi trước điểm đọc.
4. Không; nhánh đó kết thúc bất thường và tìm handler ngoài.
5. Có giá trị mặc định trước `try`; có thể che lỗi hoặc trả giá trị gây hiểu nhầm.
6. Không, vì biến ra ngoài scope.
7. Không, vì đường `catch` thứ hai vẫn có thể đi tới điểm đọc chưa gán.
8. Do vế phải được đánh giá trước khi gán và đã kết thúc bất thường.
9. Không; trả kết quả từ một helper hoặc mọi nhánh có `return` rồi khởi tạo `final` một lần.
10. Khi mọi đường có thể kết thúc bình thường tới điểm đọc đều đã gán; đường exception lan ra ngoài không tới đó.
11. DA là phân tích luồng của trình biên dịch, không dựa vào mong đợi runtime về chuỗi.
12. Trả kiểu kết quả có trạng thái, dùng cách biểu diễn có phân biệt thành công/lỗi hoặc ném ngoại lệ theo hợp đồng.
13. Có; hai nhánh đều trả trực tiếp.
14. Vì nhánh lỗi `throw` ngoại lệ, không thể tới `return result;`.

## 17. Ghi nhớ

**Biến cục bộ phải được gán chắc chắn tại điểm đọc, không nhất thiết phải được gán trong mọi nhánh đã xuất hiện trong mã nguồn.** Với `try/catch`, hãy lần theo mọi đường có thể đến điểm dùng biến: nhánh thành công có phép gán, nhánh `catch` có phép gán hợp lệ, hoặc nhánh thất bại kết thúc bằng `return`/`throw` và không đến điểm đọc. Phân biệt **scope**, **definite assignment**, **giá trị mặc định** và **ngữ nghĩa lỗi nghiệp vụ** sẽ giúp bạn sửa đúng nguyên nhân thay vì thêm một giá trị giả chỉ để mã biên dịch.