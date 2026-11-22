# Giá trị trả về được tính trước khi thực thi finally trong Java

> Java Core – Exception · Phần: **Khối finally** · Tập trung vào thứ tự tính biểu thức `return`, biến cục bộ, tham chiếu đối tượng và trường hợp `finally` thay thế luồng điều khiển. Ví dụ Java 17+.

## 1. Quy tắc cốt lõi

Khi một phương thức Java thực thi câu lệnh `return expression;` trong `try` hoặc `catch` có `finally` liên quan, trình tự về mặt ngữ nghĩa là:

1. **Đánh giá toàn bộ `expression`** và thu được giá trị `V`, nếu biểu thức hoàn thành bình thường.
2. Ghi nhận lý do kết thúc luồng hiện tại là **trả về giá trị `V`**. Phương thức chưa chuyển điều khiển hẳn cho caller.
3. **Thực hiện các khối `finally` phải chạy** trên đường rời các phạm vi liên quan.
4. Nếu các khối `finally` hoàn thành bình thường, caller nhận **giá trị `V` đã tính** ở bước 1.
5. Nếu `finally` lại kết thúc bất thường, ví dụ tự `return` hoặc `throw`, lý do mới có thể **thay thế** yêu cầu trả về đang chờ. Khi đó caller **không nhất thiết** nhận `V`.

Điều này được mô tả trong [Java Language Specification 17, mục 14.17 – The return Statement](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.17) và [mục 14.20.2 – Execution of try-finally and try-catch-finally](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.20.2).

**Điều quan trọng nhất:** `finally` chạy **trước khi caller nhận kết quả**, nhưng **sau khi biểu thức của `return` đã được đánh giá**. Đừng nhầm “return được viết trước finally” với “phương thức đã thoát hoàn toàn trước khi finally chạy”.

### Sơ đồ luồng thực thi

```text
           Gặp return expression;
                     |
                     v
        Đánh giá expression trước
                /         \
      Thành công            Expression tự ném E
          |                         |
          v                         v
     Có giá trị V               Chưa có V
          |                         |
          +-------------+-----------+
                        |
                        v
                 Chạy finally
                  /        \
        Hoàn thành          Kết thúc bất thường
          bình thường         (return/throw khác)
            |                         |
            v                         v
       Dùng lý do gốc          Lý do mới có thể
       return V hoặc E          thay thế lý do gốc
            |                         |
            v                         v
      Caller nhận V           Caller nhận kết quả
      hoặc nhận lỗi E         khác / ngoại lệ khác
```

Sơ đồ là cách trực quan hóa quy tắc ngôn ngữ, không phải yêu cầu JVM lưu giá trị vào một biến tên `V` hoặc một bytecode cố định. Compiler có thể chọn cách triển khai khác nhau miễn giữ ngữ nghĩa JLS.

## 2. Mã ngắn nhất: sửa biến trong finally không đổi giá trị đã return

Xét một phương thức (đoạn dưới là **mã minh họa trong class**, chưa phải chương trình đầy đủ):

```java
static int example() {
    int number = 10;
    try {
        return number;
    } finally {
        number = 99;
    }
}
```

Giá trị của lời gọi `example()` là **`10`**, không phải `99`.

Phân tích từng bước:

- Khi gặp `return number;`, biểu thức biến `number` được đọc; giá trị nguyên thủy `int` hiện tại là `10`.
- Phương thức ghi nhận yêu cầu trả về `10` rồi chuyển sang khối `finally`.
- Khối `finally` gán biến cục bộ `number = 99`; thay đổi này diễn ra thật, nhưng không làm thay đổi giá trị `10` đã được tính cho việc return.
- Vì `finally` hoàn thành bình thường, phương thức hoàn tất việc trả giá trị đã ghi nhận.

Tương tự với các kiểu nguyên thủy `boolean`, `long`, `double` và các giá trị bất biến như tham chiếu đến một đối tượng `String`: phép **gán lại biến cục bộ** trong `finally` không tự đánh giá lại biểu thức `return` trước đó.

Không nên giải thích rằng “finally không thực hiện việc gán”: nó **vẫn thực hiện**, chỉ là giá trị trả về đã được tính trước.

## 3. Chương trình Java 17 hoàn chỉnh và stdout đã kiểm chứng

Lưu tệp **`FinallyReturnDemo.java`** với nội dung sau. Bảy tình huống được tách thành các phương thức để so sánh kết quả trả về nguyên thủy, biểu thức gọi hàm, tham chiếu đối tượng, return trong finally, throw trong finally, lỗi khi tính biểu thức return và return trong catch.

```java
public class FinallyReturnDemo {
    private static int calculate() {
        System.out.println("evaluate calculate()");
        return 7;
    }

    private static int primitive() {
        int value = 10;
        try {
            System.out.println("try primitive");
            return value + 1;
        } finally {
            value = 99;
            System.out.println("finally primitive value=" + value);
        }
    }

    private static int expression() {
        try {
            return calculate();
        } finally {
            System.out.println("finally expression");
        }
    }

    private static StringBuilder reference() {
        StringBuilder text = new StringBuilder("A");
        try {
            System.out.println("try reference");
            return text;
        } finally {
            text.append("B");
            text = new StringBuilder("C");
            System.out.println("finally reference local=" + text);
        }
    }

    private static int override() {
        try {
            System.out.println("try override");
            return 1;
        } finally {
            System.out.println("finally override");
            return 2; // Biên dịch được nhưng che giá trị return từ try.
        }
    }

    private static int throwFromFinally() {
        try {
            System.out.println("try throw");
            return 3;
        } finally {
            System.out.println("finally throw");
            throw new IllegalStateException("cleanup failed");
        }
    }

    private static int failedExpression() {
        try {
            System.out.println("try parse");
            return Integer.parseInt("bad");
        } finally {
            System.out.println("finally parse");
        }
    }

    private static int returnFromCatch() {
        try {
            throw new IllegalArgumentException("bad input");
        } catch (IllegalArgumentException ex) {
            System.out.println("catch returns");
            return 5;
        } finally {
            System.out.println("finally catch");
        }
    }

    public static void main(String[] args) {
        System.out.println("== primitive ==");
        System.out.println("result=" + primitive());

        System.out.println("== expression ==");
        System.out.println("result=" + expression());

        System.out.println("== reference ==");
        StringBuilder result = reference();
        System.out.println("result=" + result);

        System.out.println("== override ==");
        System.out.println("result=" + override());

        System.out.println("== throw ==");
        try {
            System.out.println("result=" + throwFromFinally());
        } catch (IllegalStateException ex) {
            System.out.println("caught=" + ex.getMessage());
        }

        System.out.println("== failed expression ==");
        try {
            System.out.println("result=" + failedExpression());
        } catch (NumberFormatException ex) {
            System.out.println("caught=NumberFormatException");
        }

        System.out.println("== catch return ==");
        System.out.println("result=" + returnFromCatch());
    }
}
```

### Biên dịch và chạy

Dùng JDK 17 hoặc mới hơn tại thư mục chứa file `FinallyReturnDemo.java`:

```bash
javac --release 17 -encoding UTF-8 FinallyReturnDemo.java
java FinallyReturnDemo
```

**Stdout chính xác:**

```text
== primitive ==
try primitive
finally primitive value=99
result=11
== expression ==
evaluate calculate()
finally expression
result=7
== reference ==
try reference
finally reference local=C
result=AB
== override ==
try override
finally override
result=2
== throw ==
try throw
finally throw
caught=cleanup failed
== failed expression ==
try parse
finally parse
caught=NumberFormatException
== catch return ==
catch returns
finally catch
result=5
```

Kết quả trên đã được kiểm chứng bằng cách **biên dịch với `javac --release 17` và chạy trên JDK có hỗ trợ Java 17**. Các thông điệp ngoại lệ do code tự tạo; chương trình không phụ thuộc cách JVM diễn giải stack trace hoặc thông điệp `NumberFormatException` để tạo stdout.

## 4. Phân tích chi tiết bảy trường hợp

### 4.1. `primitive()`: giá trị của biểu thức đã chốt trước finally

Trong nhánh `primitive()`:

```java
int value = 10;
try {
    System.out.println("try primitive");
    return value + 1;
} finally {
    value = 99;
    System.out.println("finally primitive value=" + value);
}
```

Thứ tự:

1. In `try primitive`.
2. Đọc `value == 10` và tính `value + 1 == 11` cho biểu thức return.
3. Đến `finally`, gán `value = 99` rồi in `finally primitive value=99`.
4. `finally` hoàn thành bình thường; method trả **`11`**, caller in `result=11`.

Nếu nhầm rằng cuối cùng method “đọc lại biến `value`”, bạn sẽ dự đoán `99` — sai. Một biểu thức return không tự động được đánh giá lại sau finally.

### 4.2. `expression()`: lời gọi trong return được thực hiện trước finally

Đối với:

```java
try {
    return calculate();
} finally {
    System.out.println("finally expression");
}
```

Lời gọi `calculate()` diễn ra ngay khi đánh giá biểu thức của `return`; nó in `evaluate calculate()` rồi trả về `7`. **Sau khi đã có số `7`**, Java chạy finally và in `finally expression`. Caller mới nhận số `7`.

Vì vậy stdout không thể đảo thành `finally expression` trước `evaluate calculate()`. Điều này cũng đúng nếu biểu thức return chứa phép toán, truy cập mảng, hoặc các lời gọi khác: chúng được đánh giá theo quy tắc biểu thức trước khi thực hiện finally, miễn là bước đánh giá hoàn thành bình thường.

### 4.3. `reference()`: tham chiếu được chốt, trạng thái đối tượng vẫn có thể đổi

Đây là trường hợp thường gây hiểu nhầm lớn nhất:

```java
StringBuilder text = new StringBuilder("A");
try {
    return text;
} finally {
    text.append("B");
    text = new StringBuilder("C");
}
```

Điều được trả về là **giá trị tham chiếu đến đối tượng StringBuilder ban đầu**, không phải một bản sao bất biến của toàn bộ đối tượng. Diễn biến:

1. Biến `text` trỏ đến đối tượng `StringBuilder("A")`.
2. `return text;` đánh giá và giữ **tham chiếu đó** để trả về.
3. Trong finally, `text.append("B")` làm thay đổi **chính đối tượng đã được chọn trả về** từ nội dung `A` thành `AB`.
4. Sau đó, `text = new StringBuilder("C")` chỉ gán lại **biến cục bộ** `text` sang một đối tượng mới; giá trị tham chiếu đã chọn ở bước 2 không đổi.
5. Caller nhận đối tượng ban đầu, hiện có nội dung `AB`.

Do đó chương trình in `finally reference local=C` trong finally nhưng caller in `result=AB`. Không có nghịch lý: **giá trị tham chiếu** đã được chọn trước finally, còn **trạng thái của đối tượng mà tham chiếu chỉ đến** có thể bị sửa sau đó.

| Thao tác trong finally | Có làm thay đổi giá trị tham chiếu đã chọn để return? | Caller có thể thấy tác động? |
| --- | --- | --- |
| `text.append("B")` | Không | **Có**, vì đối tượng được trả về đã bị sửa |
| `text = new StringBuilder("C")` | Không | **Không**, nếu chỉ đổi biến cục bộ |
| `text = null` | Không | Không làm return biến thành null |
| Sửa trường/mảng của đối tượng được trả về | Không | Có, nếu trạng thái đó nằm trên đối tượng caller nhận |

Như vậy câu “giá trị trả về không đổi trong finally” cần được diễn đạt cẩn thận: với một **tham chiếu đến đối tượng mutable**, *tham chiếu* không đổi nhưng *đối tượng* vẫn có thể đổi.

### 4.4. `override()`: một return khác trong finally ghi đè ý định return trước

Xét:

```java
static int override() {
    try {
        return 1;
    } finally {
        return 2;
    }
}
```

Đây là một ví dụ **Java hợp lệ về cú pháp**, nhưng được khuyến nghị **không dùng trong code sản xuất**.

- `return 1;` đã được đánh giá, ghi nhận lý do kết thúc là “trả 1”.
- Khối `finally` thực thi `return 2;`, tạo **lý do kết thúc bất thường mới** là “trả 2”.
- Theo JLS mục 14.20.2, lý do mới từ finally **thay thế** lý do cũ.
- Caller nhận `2`; đây không phải vì biểu thức `return 1` được tính lại hay biến cục bộ bị đổi.

Trong chương trình đầy đủ, thứ tự là `try override` → `finally override` → `result=2`.

**Chỉ nên xem `return` trong finally như một ví dụ về ngữ nghĩa ngôn ngữ, không phải thủ thuật thiết kế**. Nó có thể che kết quả và lỗi nghiêm trọng, khiến code khó bảo trì và phân tích.

### 4.5. `throwFromFinally()`: finally ném lỗi, caller không nhận kết quả đã tính

Trong:

```java
static int throwFromFinally() {
    try {
        return 3;
    } finally {
        throw new IllegalStateException("cleanup failed");
    }
}
```

Java đã tính giá trị trả về là `3`, nhưng finally lại ném `IllegalStateException`. Yêu cầu trả về `3` **bị bỏ**, và caller nhận đường điều khiển ngoại lệ. Vì thế không có dòng `result=3` trong stdout; nhánh `catch` ở caller in `caught=cleanup failed`.

Phần tính biểu thức return có thể đã tạo tác dụng phụ trước khi exception từ finally xuất hiện. Exception không tự rollback những tác dụng phụ ấy.

Đây là một lý do cần xử lý cleanup cẩn trọng. Nếu một đoạn cleanup cần ném lỗi, phương thức có thể không trả được kết quả đã tính; lựa chọn xử lý nên có chủ đích thay vì ngẫu nhiên vì mã `finally` phức tạp.

### 4.6. `failedExpression()`: biểu thức return không tạo được giá trị

Trong:

```java
try {
    return Integer.parseInt("bad");
} finally {
    System.out.println("finally parse");
}
```

Lời gọi `Integer.parseInt("bad")` ném `NumberFormatException` **trong giai đoạn đánh giá expression**. Không có kết quả `int` nào được tạo ra để ghi nhận một giá trị return. Java vẫn thực hiện finally theo quy tắc, in `finally parse`, rồi exception từ parse tiếp tục đến caller (vì finally hoàn thành bình thường).

Trong chương trình, caller bắt đúng kiểu và in `caught=NumberFormatException`. Không có dòng `result=...` từ lời gọi này. Đây là khác biệt căn bản giữa:

- **Return expression thành công**: có giá trị `V` đang chờ trả về.
- **Return expression ném exception**: chưa có `V`; lý do chuyển điều khiển là ném lỗi, không phải trả giá trị.

Nếu finally tiếp tục ném lỗi thứ hai, lỗi thứ hai có thể thay thế lỗi parse gốc. Tránh viết finally mang nhiều nhánh exception chưa được kiểm soát.

### 4.7. `returnFromCatch()`: return trong catch cũng đi qua finally

Hãy xem:

```java
try {
    throw new IllegalArgumentException("bad input");
} catch (IllegalArgumentException ex) {
    System.out.println("catch returns");
    return 5;
} finally {
    System.out.println("finally catch");
}
```

Đây là đoạn bên trong phương thức minh họa. `try` ném lỗi; `catch` nhận và xử lý, rồi bắt đầu yêu cầu trả giá trị `5`. Trước khi caller nhận số `5`, `finally` vẫn chạy và in `finally catch`. Kết quả cuối cùng là `5`.

Thứ tự stdout: `catch returns` → `finally catch` → `result=5`.

**Không phải chỉ có return bên trong try mới chạy finally**. Return bên trong catch thuộc cùng cấu trúc cũng chịu quy tắc dọn dẹp tương ứng.

## 5. Phân biệt giá trị nguyên thủy, tham chiếu và trạng thái đối tượng

Java **truyền giá trị** khi trả kết quả qua lời gọi phương thức: kết quả có thể là giá trị nguyên thủy hoặc giá trị tham chiếu.

### Với kiểu nguyên thủy

```java
int x = 10;
try {
    return x;
} finally {
    x++;
}
```

Giả định ở trong một phương thức trả `int`. Kết quả trả về là `10`, không phải `11`. Biến `x` đã thay đổi trong finally nhưng biểu thức return trước đó không được tính lại.

Các biểu thức như `return x + 2;`, `return x++;` hoặc `return method();` vẫn tuân thứ tự: toàn bộ biểu thức return được tính trước finally.

**Trường hợp `x++`:** giá trị của hậu tố increment là giá trị **trước khi tăng**, trong khi biến `x` tăng như một tác dụng phụ trước khi cuối cùng sang finally:

```java
int x = 4;
try {
    return x++; // giá trị return được chọn là 4, x trở thành 5.
} finally {
    x = 100;
}
```

Ví dụ này trả `4`. Nó minh họa rằng cả tác dụng phụ của biểu thức return và công việc trong finally có thể thực thi, nhưng không làm giá trị đã chọn bị đánh giá lại.

### Với kiểu tham chiếu

```java
StringBuilder builder = new StringBuilder("Hello");
try {
    return builder;
} finally {
    builder.append(" Java");
}
```

Caller nhận tham chiếu đến **cùng một đối tượng** mà nội dung lúc được sử dụng có thể là `Hello Java`. Return không clone đối tượng và cũng không “đóng băng” toàn bộ trạng thái của nó. Một thiết kế API muốn giữ trạng thái bất biến nên trả về immutable object, copy phù hợp, hoặc tránh sửa đối tượng sau khi đã chọn trả về.

### Với String bất biến

```java
String name = "A";
try {
    return name;
} finally {
    name = name + "B";
}
```

Kết quả là `"A"`. Vì `String` bất biến, phép nối tạo ra một String mới; gán lại biến `name` không sửa đối tượng String cũ. Điểm quan trọng vẫn là **tham chiếu trả về được chọn từ trước**, không phải vì Java có quy tắc đặc biệt cho keyword `String`.

## 6. Khi finally có return/throw mới: quy tắc ưu tiên chính xác

JLS mô tả luồng điều khiển của `try-finally` bằng các **lý do kết thúc** (reason for abrupt completion). Với một lý do cũ `R` từ try/catch:

- **Finally hoàn thành bình thường:** lý do `R` tiếp tục có hiệu lực. Với `return V`, trả `V`; với `throw E`, tiếp tục ném `E`.
- **Finally kết thúc bất thường vì lý do mới `S`:** toàn cấu trúc kết thúc theo `S`; lý do `R` bị thay thế.

Bảng so sánh:

| Trong try/catch | Trong finally | Hệ quả |
| --- | --- | --- |
| `return 10;` | Chỉ log, kết thúc bình thường | Caller nhận `10` |
| `return 10;` | Gán lại biến cục bộ rồi kết thúc bình thường | Caller vẫn nhận `10` |
| `return object;` | Sửa trạng thái của chính object | Caller nhận cùng tham chiếu, thấy object đã sửa |
| `return 10;` | `return 20;` | Caller nhận `20`, return cũ bị che |
| `return 10;` | `throw new RuntimeException();` | Caller không nhận 10; exception lan lên |
| `throw new IOException(...);` | Log, kết thúc bình thường | IOException gốc tiếp tục lan |
| `throw new IOException(...);` | `return 20;` | Exception gốc bị che; caller nhận 20 |
| `throw new IOException(...);` | `throw new IllegalStateException(...);` | Exception mới có thể thay thế lỗi gốc |

Hai dòng cuối là ví dụ **mã có hành vi nguy hiểm nhưng hợp lệ theo ngôn ngữ** (giả định đủ khai báo/handler). Chúng minh họa vì sao return trong finally thường bị xem là lỗi thiết kế. Không nên dùng để “sửa nhanh” một lỗi bằng cách ép phương thức luôn trả về thành công.

### Cleanup và suppressed exception là trường hợp riêng

`try-with-resources` có quy tắc chuyên biệt về việc đóng tài nguyên. Khi thân try và `close()` cùng phát sinh exception, exception đóng tài nguyên thường được thêm vào danh sách `getSuppressed()` của exception chính, thay vì mặc định thay thế nó theo cách một `finally` tự viết ném lỗi mới.

Điều này không làm đổi thứ tự tính biểu thức return: Java vẫn áp dụng các quy tắc ngôn ngữ về luồng thực thi và đóng tài nguyên. Tuy nhiên, **đừng trộn** quy tắc suppressed của tài nguyên với quy tắc một `finally` thủ công tự `throw`.

Nếu việc mở/đóng tài nguyên cần quản lý, ưu tiên cấu trúc `try-with-resources` với `AutoCloseable` khi phù hợp, thay vì một finally phức tạp và dễ che mất exception.

## 7. Return trong try/catch/finally: phân tích thứ tự cho các trường hợp khác

### 7.1. Nhiều return trong các nhánh điều kiện

```java
static int choose(boolean valid) {
    try {
        if (valid) {
            return 1;
        }
        return 2;
    } finally {
        System.out.println("cleanup");
    }
}
```

Trong một chương trình hợp lệ, nếu `valid == true` thì biểu thức trả về `1` được tính trước finally; nếu `false` thì tính `2` trước finally. Cả hai đường đều in `cleanup` trước khi caller nhận kết quả.

Không phải finally làm phương thức chỉ có một return; các nhánh quyết định kết quả từ trước, finally chỉ thực thi công việc theo đường đi đang rời phạm vi.

### 7.2. Return không có biểu thức trong void method

```java
static void save(boolean valid) {
    try {
        if (!valid) {
            return;
        }
        System.out.println("saving");
    } finally {
        System.out.println("cleanup");
    }
}
```

Với `return;` trong phương thức `void`, không có giá trị `V` cần tính, nhưng điều khiển vẫn đi qua finally trước khi caller tiếp tục. Đừng suy rằng finally chỉ chạy khi `return` có giá trị.

### 7.3. Một method được gọi trong biểu thức return có side effect

```java
static int logAndCompute() {
    System.out.println("compute");
    return 30;
}

static int example() {
    try {
        return logAndCompute() + 2;
    } finally {
        System.out.println("cleanup");
    }
}
```

Khi gọi `example()`, kết quả là 32. Dòng `compute` phải in trước `cleanup` vì lời gọi nằm trong biểu thức `return`. Phép cộng với 2 cũng hoàn thành trước finally nếu `logAndCompute()` trả về bình thường.

Nếu `logAndCompute()` ném exception trước khi trả kết quả, không có 32; Java đi qua finally theo đường exception như phần 4.6.

### 7.4. Nhiều finally lồng nhau

```java
static int nested() {
    try {
        try {
            return 9;
        } finally {
            System.out.println("inner");
        }
    } finally {
        System.out.println("outer");
    }
}
```

Kết quả trả về là `9`. Lý do `return 9` được xác lập trước, sau đó Java chạy finally **từ phạm vi trong ra phạm vi ngoài**, nên stdout bên trong method là `inner` rồi `outer`. Nếu một finally bên trong ném lỗi, luồng có thể vẫn đi qua finally ngoài; caller có thể nhận exception thay vì 9. Đoạn trên là phương thức minh họa trong class, không phải tệp Java độc lập.

## 8. Phân biệt “return đang chờ” và “phương thức đã trả xong”

Một cách ghi chú trong review code:

```text
return expression;   // Chọn giá trị cần trả, yêu cầu chuyển điều khiển.
finally { ... }      // Thực hiện trước khi phương thức chuyển hẳn điều khiển về caller.
caller                // Nhận kết quả nếu không có reason mới ghi đè.
```

JLS gọi việc `return` tạo ra lý do **abrupt completion**; từ *abrupt* ở đây không đồng nghĩa “đang xảy ra lỗi”. Câu lệnh `return` là một cách kết thúc có chủ đích, còn `throw` là một lý do abrupt khác. `finally` có thể chạy trên cả hai đường.

Việc chờ để hoàn tất return không bảo đảm không có side effect trong finally. Nếu finally thay đổi file, database, cache, collection hoặc đối tượng mà caller sắp nhận, những thay đổi ấy vẫn có thể quan sát thấy. Nhưng finally cũng có thể ném lỗi và khiến caller **không nhận** giá trị đã được tính.

**Không nên mô tả máy móc rằng “Java copy toàn bộ object vào vùng nhớ return”.** Ngôn ngữ chỉ bảo đảm giá trị biểu thức được đánh giá trước finally. Với đối tượng, giá trị đó là tham chiếu, không phải bản sao sâu; chi tiết bytecode hoặc vị trí lưu tạm là chuyện của trình biên dịch/JVM.

## 9. Kỹ thuật viết code rõ ràng hơn

### 9.1. Chỉ dùng finally để cleanup, tránh return trong finally

Mẫu nên dùng:

```java
static int calculateSafely() {
    try {
        return 10;
    } finally {
        System.out.println("cleanup");
    }
}
```

Ví dụ trên minh họa return từ try nhưng finally hoàn thành bình thường. Trong ứng dụng thật, phần cleanup có thể là giải phóng khóa/tài nguyên, cập nhật trạng thái dọn dẹp hoặc log ở mức phù hợp.

Mẫu gây hiểu nhầm:

```java
static int calculateBadly() {
    try {
        return 10;
    } finally {
        return 20; // Che mất ý định return của try.
    }
}
```

Đây là **mã có thể biên dịch nhưng không nên dùng**, trừ khi đang minh họa chính ngữ nghĩa `finally`. Một lỗi nguy hiểm hơn là `return` trong finally che exception thực sự từ try, khiến chương trình báo thành công giả.

### 9.2. Tách computation ra khỏi cleanup nếu thuận lợi

Nếu computation có nhiều side effect, có thể viết:

```java
static int clearer() {
    int answer;
    try {
        answer = compute();
    } finally {
        cleanUp();
    }
    return answer;
}
```

Đây là **mã minh họa**: `compute()` và `cleanUp()` phải được định nghĩa/nhập phù hợp. Nếu `compute()` và `cleanUp()` hoàn thành bình thường, kết quả trả về được xử lý rõ ràng sau cleanup. Nếu `compute()` ném lỗi, finally vẫn chạy, sau đó exception lan đi (trừ khi finally có lỗi mới). Không dùng cách này để né các quy tắc cleanup; nó chỉ có thể giúp một số trường hợp dễ đọc hơn.

Đối với mã xử lý tài nguyên, `try-with-resources` thường rõ ràng hơn một finally tự đóng tài nguyên phức tạp.

### 9.3. Đừng thay đổi đối tượng sắp return một cách bất ngờ

Nếu phương thức trả về một đối tượng mutable, hãy xem xét trạng thái tại thời điểm caller nhận. Việc sửa đối tượng trong finally **hợp lệ về Java** nhưng có thể khiến người đọc nhầm rằng caller nhận trạng thái cũ.

Ưu tiên hoàn thiện đối tượng trước khi viết `return`, hoặc trả về bản sao bất biến khi hợp đồng yêu cầu không bị sửa tiếp. Nếu phải làm cleanup có side effect, giải thích rõ ranh giới đó để việc đọc API và viết test không mơ hồ.

## 10. Cách dự đoán đầu ra của một đoạn finally

Để trả lời các câu hỏi phỏng vấn hoặc debug thực tế, hãy làm theo thứ tự:

1. **Xác định nơi có `return` hoặc `throw`.** Nó nằm trong try, catch hay finally?
2. **Đánh giá biểu thức return ngay tại thời điểm gặp return.** Ghi giá trị hoặc tham chiếu được chọn. Nếu biểu thức ném lỗi, ghi nhận exception thay vì giả định có giá trị trả về.
3. **Liệt kê side effect đã xảy ra** trong chính biểu thức return: tăng biến, sửa mảng, gọi phương thức, in log...
4. **Thực hiện finally theo thứ tự phạm vi**, từ trong ra ngoài. Phân biệt gán lại biến cục bộ với thay đổi nội dung của object.
5. **Xác định finally hoàn thành bình thường hay bất thường.** Nếu có `return`/`throw` trong finally, cập nhật lý do điều khiển cuối cùng.
6. **Suy ra kết quả caller quan sát:** giá trị nguyên thủy, tham chiếu (và trạng thái object), exception hoặc một đường điều khiển khác.
7. **Đọc stdout theo thời điểm:** các dòng in trong expression của return phải trước các dòng in trong finally; dòng in kết quả ở caller chỉ có khi lời gọi thực sự trả về bình thường.

Bài tập minh họa (đặt trong một phương thức trả `int`):

```java
int count = 4;
try {
    return count++;
} finally {
    count = 100;
    System.out.println("finally count=" + count);
}
```

Giải thích: biểu thức `count++` chọn **4** làm giá trị return rồi tăng biến lên **5**; finally gán biến thành **100**, in `finally count=100`; caller nhận **4** nếu finally hoàn thành bình thường.

Nếu một bạn khác dự đoán caller nhận 100, hãy chỉ ra rằng phần tăng và phần gán đều thực sự diễn ra nhưng không làm **tính lại** giá trị của biểu thức return đã hoàn thành.

## 11. Những lỗi hiểu sai phổ biến

- **“finally chạy trước return nên return dùng giá trị mới trong finally.”** Sai: biểu thức `return` được đánh giá **trước**, chỉ việc chuyển điều khiển cho caller được trì hoãn.
- **“Gán biến trong finally không hề có hiệu lực.”** Sai: việc gán có hiệu lực với biến đang tồn tại, nhưng không thay đổi giá trị đã chọn trả về.
- **“return một object nghĩa là snapshot của object trước finally.”** Sai: Java trả **giá trị tham chiếu**, còn object mutable có thể đổi.
- **“Đổi biến tham chiếu sang object mới trong finally làm caller nhận object mới.”** Sai: giá trị tham chiếu đã chọn trước khi gán lại.
- **“finally có return nhưng vẫn nhận return của try vì try chạy trước.”** Sai: return trong finally có thể thay thế lý do return của try.
- **“finally ném lỗi nhưng caller vẫn nhận giá trị return trước đó.”** Sai: nếu finally kết thúc bằng throw, caller nhận đường exception.
- **“Biểu thức return ném exception vẫn tạo ra một giá trị return.”** Sai: không có giá trị `V` khi expression hoàn thành bất thường.
- **“finally chỉ chạy khi xảy ra exception.”** Sai: nó cũng chạy khi try thành công, return bình thường hoặc return trong catch theo quy tắc cấu trúc.
- **“return trong catch bỏ qua finally.”** Sai: finally vẫn được thực hiện trước khi chuyển điều khiển hoàn toàn.
- **“finally luôn chạy trong mọi tình huống tuyệt đối.”** Không nên khẳng định: khi JVM/tiến trình bị chấm dứt đột ngột, mã cleanup có thể không có cơ hội chạy.
- **“return trong finally là cách chắc chắn không báo lỗi.”** Nó có thể **che lỗi nghiêm trọng**, không phải cách phục hồi đúng.
- **“try-with-resources và finally tự viết ném lỗi có cùng cơ chế suppressed.”** Sai: suppressed exception là quy tắc đặc thù của việc đóng resource tự động.

## 12. Tự kiểm tra kiến thức

**Câu 1.** Tại sao `int x=10; try {return x;} finally {x=99;}` trả về 10?

*Đáp án:* Vì giá trị biểu thức `return x` được đọc là 10 trước finally. Gán 99 sau đó không làm giá trị đã chọn bị đánh giá lại.

**Câu 2.** Với `return text;`, finally gọi `text.append("B")` rồi `text = new StringBuilder("C")`, caller nhận gì?

*Đáp án:* Cùng object ban đầu được chọn trước finally, nhưng nội dung có thể đã thêm B. Gán lại biến cục bộ chỉ đổi tham chiếu của biến đó.

**Câu 3.** Nếu finally chứa `return 2;` còn try đã đánh giá `return 1;`, kết quả là gì?

*Đáp án:* Caller nhận 2, vì finally kết thúc bất thường với lý do return mới thay thế yêu cầu return cũ.

**Câu 4.** Nếu finally ném `IllegalStateException` trong lúc try đang yêu cầu trả số 3, caller có nhận 3 không?

*Đáp án:* Không. Lý do throw từ finally có thể thay thế return đang chờ; caller thấy ngoại lệ.

**Câu 5.** Nếu biểu thức `Integer.parseInt("bad")` trong return ném lỗi, finally có chạy không?

*Đáp án:* Có theo quy tắc try/finally bình thường; chưa có giá trị int để return. Nếu finally hoàn thành bình thường, NumberFormatException được truyền ra ngoài.

**Câu 6.** Return trong catch có phải bỏ qua finally không?

*Đáp án:* Không; finally vẫn chạy trước khi caller nhận giá trị nếu không bị một lý do điều khiển mới thay thế.

**Câu 7.** Một `return x++;` mà `x` ban đầu là 4, finally gán `x=100` thì giá trị method trả là gì?

*Đáp án:* 4. Hậu tố tăng trả giá trị cũ, side effect tăng và phép gán trong finally không làm kết quả return bị tính lại.

**Câu 8.** Tại sao không nên `return` trong finally để “bảo đảm có kết quả”?

*Đáp án:* Vì nó có thể che kết quả từ try/catch hoặc che exception thật sự, khiến caller nhận trạng thái thành công sai.

## 13. Tài liệu đối chiếu chính thức

- [Java SE 17 JLS mục 14.17 – The return Statement](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.17): thứ tự đánh giá expression, giá trị return và điều khiển bị trì hoãn bởi finally.
- [Java SE 17 JLS mục 14.20.2 – Execution of try-finally and try-catch-finally](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.20.2): nguyên tắc lý do abrupt completion được giữ hoặc bị thay thế.
- [Java SE 17 JLS mục 14.1 – Normal and Abrupt Completion of Statements](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.1): phân biệt return và throw như các lý do chuyển điều khiển.
- [Java SE 17 JLS mục 15.6 – Normal and Abrupt Completion of Evaluation](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.6): nếu chính biểu thức return ném ngoại lệ.
- [Java SE 17 JLS mục 14.20.3 – try-with-resources](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.20.3): ngữ nghĩa đóng tài nguyên và suppressed exception.
- [Java SE 17 API – StringBuilder](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/StringBuilder.html): ví dụ đối tượng mutable khi trả tham chiếu.

**Kết luận:** `return expression;` **chọn giá trị hoặc tham chiếu trước khi finally thực thi**. Nếu finally hoàn thành bình thường, caller nhận giá trị đã chọn; sửa biến cục bộ không tính lại return, nhưng thay đổi trạng thái object vẫn có thể được quan sát qua cùng tham chiếu. Nếu finally tự return hoặc throw, nó có thể **thay thế kết quả đang chờ**. Thiết kế an toàn nhất thường là dùng finally để cleanup, không để quyết định kết quả trả về.