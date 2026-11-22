# Quy tắc `return` và đường đi trả về giá trị trong biểu thức lambda Java

## 1. Vì sao quy tắc return của lambda quan trọng?

Lambda trong Java biểu diễn một phần triển khai của **functional interface**: interface có một phương thức trừu tượng chức năng, thường gọi là *single abstract method* (SAM). Kiểu trả về của SAM quyết định lambda có phải tạo giá trị hay không. Hai lambda trông giống nhau có thể hợp lệ với interface này nhưng không hợp lệ với interface khác.

Ví dụ:

~~~java
Function<Integer, Integer> doubleIt = x -> x * 2;

Function<Integer, Integer> doubleItBlock = x -> {
    return x * 2;
};
~~~

Hai đoạn trên có cùng ý nghĩa, giả định đã import **java.util.function.Function**. Phiên bản đầu dùng **expression body**: giá trị của biểu thức **x * 2** là kết quả. Phiên bản sau dùng **block body**: phải viết **return** để trả kết quả.

Ngược lại, một callback chỉ thực hiện công việc:

~~~java
Consumer<String> print = text -> {
    System.out.println(text);
};
~~~

**Consumer.accept** trả về **void**, vì vậy không cần trả giá trị; đây là đoạn minh họa cần import **java.util.function.Consumer**.

Bài học này tập trung vào ba câu hỏi:

1. **Khi nào viết `return`, khi nào được bỏ?**
2. **Những nhánh nào phải trả giá trị, nhánh nào có thể kết thúc bằng `throw`?**
3. **Trình biên dịch kiểm tra đường đi trả về khác nhau ra sao giữa lambda trả `void` và lambda trả giá trị?**

Hiểu được các quy tắc này giúp tránh lỗi compile khó hiểu khi chuyển một lambda một dòng thành nhiều dòng, thêm các nhánh **if/else**, hoặc thay đổi kiểu đích từ **Consumer** sang **Function**.

## 2. Kiểu đích (target type) quyết định hợp đồng trả về

Lambda **không tự có kiểu độc lập**: trình biên dịch cần một ngữ cảnh tương thích với functional interface, gọi là **target type**. Xét các SAM phổ biến:

| Interface | Phương thức chức năng | Kết quả lambda |
| --- | --- | --- |
| **Runnable** | **void run()** | Không trả giá trị |
| **Consumer<T>** | **void accept(T)** | Không trả giá trị |
| **Predicate<T>** | **boolean test(T)** | Phải tính được boolean |
| **Function<T,R>** | **R apply(T)** | Phải tính được R |
| **Supplier<T>** | **T get()** | Phải tính được T |
| **IntUnaryOperator** | **int applyAsInt(int)** | Phải tính được int |

Ví dụ:

~~~java
Runnable job = () -> System.out.println("running");
Predicate<String> nonEmpty = s -> !s.isEmpty();
Supplier<Integer> answer = () -> 42;
~~~

Đây là các đoạn minh họa, cần import **Predicate** và **Supplier**. **Runnable** không có giá trị trả về, còn hai kiểu sau có kết quả tương ứng **boolean** và **Integer**.

**Chú ý:** `return` nằm trong phần thân lambda chỉ kết thúc lần thực hiện **lambda**, không kết thúc phương thức bao quanh nơi lambda được khai báo. Nó giống câu lệnh return trong implementation của SAM ở mức hành vi, dù hình thức triển khai dùng lambda.

Ví dụ trong một phương thức:

~~~java
Runnable task = () -> {
    System.out.println("inside");
    return; // Chỉ rời khỏi lambda này.
};

task.run();
System.out.println("outside");
~~~

Nếu chạy đoạn này bên trong **main**, đầu ra là:

~~~text
inside
outside
~~~

Đây là đoạn minh họa chèn vào một phương thức, không phải chương trình Java độc lập. Câu lệnh **return;** kết thúc **task.run()**, rồi việc thực thi trong **main** tiếp tục.

## 3. Dạng biểu thức: trả kết quả mà không viết return

Lambda dạng biểu thức có cú pháp:

~~~java
(parameters) -> expression
~~~

Đối với SAM trả giá trị, kết quả của **expression** được dùng làm kết quả của lambda:

~~~java
Function<String, Integer> length = text -> text.length();
Predicate<Integer> positive = n -> n > 0;
Supplier<String> greeting = () -> "Xin chào";
~~~

Giả định import **Function**, **Predicate**, **Supplier**. **text.length()** tạo int và được boxing thành Integer khi cần; **n > 0** trả boolean; biểu thức literal **"Xin chào"** trả String.

Dạng biểu thức **không viết `return`**, và **không có dấu chấm phẩy ở bên trong biểu thức**. Dấu **;** sau dấu ngoặc hoặc biểu thức cuối là dấu kết thúc **khai báo/gán lambda**, ví dụ:

~~~java
Function<Integer, Integer> increment = n -> n + 1;
~~~

Nếu muốn thêm nhiều câu lệnh, bạn phải chuyển phần thân sang dạng khối **{ ... }** và tuân thủ quy tắc return của khối.

### 3.1. Expression lambda có thể dùng cho SAM trả void không?

Có, nhưng **không phải mọi biểu thức** đều hợp lệ. Khi SAM trả **void**, expression body phải là một **statement expression** hợp lệ theo cú pháp Java, ví dụ **method invocation**, phép gán, tăng/giảm, tạo đối tượng bằng **new**. Giá trị từ lời gọi phương thức (nếu có) sẽ bị bỏ đi.

~~~java
Consumer<String> logger = s -> System.out.println(s);
Runnable parse = () -> Integer.parseInt("123");
~~~

Hai lambda trên là những đoạn minh họa hợp lệ, với import **Consumer**. **Integer.parseInt** trả **int**, nhưng lời gọi phương thức là một *statement expression* nên có thể dùng làm phần thân của Runnable; kết quả int bị bỏ qua.

Trái lại:

~~~java
// KHÔNG BIÊN DỊCH:
Runnable invalid = () -> 42;
~~~

Literal **42** không phải một statement expression hợp lệ cho body của Runnable. Đây là ví dụ **cố ý không biên dịch** để phân biệt với việc gọi phương thức có giá trị trả về.

**Không suy luận** “biểu thức có giá trị thì không thể dùng với void”. Điều kiện thực tế là **cấu trúc biểu thức có được phép làm statement expression hay không**.

## 4. Dạng khối: phải trả giá trị tường minh khi SAM yêu cầu

Lambda dạng khối:

~~~java
(parameters) -> {
    statements
}
~~~

Với SAM trả giá trị, dùng **return expression;** để trả kết quả. Khác với expression body, việc viết một biểu thức đứng riêng trong khối không tự biến nó thành kết quả.

~~~java
Function<Integer, Integer> square = x -> {
    int result = x * x;
    return result;
};
~~~

Đoạn trên hợp lệ khi import Function. Nhưng:

~~~java
// KHÔNG BIÊN DỊCH:
Function<Integer, Integer> broken = x -> {
    int result = x * x;
};
~~~

Khối trên có thể kết thúc mà **không trả giá trị**, trái với SAM **Integer apply(Integer)**. Trình biên dịch báo không tương thích kiểu trả về hoặc thiếu giá trị, tùy cấu trúc.

Một lỗi thường gặp khi chuyển lambda một dòng sang nhiều dòng:

~~~java
// Hợp lệ:
Function<String, String> normalize1 = s -> s.strip();

// Hợp lệ:
Function<String, String> normalize2 = s -> {
    return s.strip();
};

// KHÔNG BIÊN DỊCH:
Function<String, String> normalize3 = s -> {
    s.strip(); // Gọi phương thức rồi bỏ kết quả.
};
~~~

Các đoạn này minh họa quy tắc cú pháp; khi chạy cần import Function và chỉ giữ những khai báo hợp lệ. **String.strip()** không thay đổi chuỗi ban đầu vì String bất biến; chỉ gọi mà không trả kết quả là sai hợp đồng Function.

## 5. Mọi đường đi có thể kết thúc bình thường đều phải đáp ứng hợp đồng

Với một lambda dạng khối được dùng làm SAM trả giá trị, Java yêu cầu khối đó là **value-compatible**: mọi câu lệnh return trong khối phải có dạng **return expression;**, và khối **không thể kết thúc bình thường mà không trả về**. Các đường đi hợp lệ có thể kết thúc bằng **throw** thay vì return.

### 5.1. Các nhánh if/else đều trả giá trị

~~~java
Function<Integer, String> classify = n -> {
    if (n < 0) {
        return "negative";
    } else if (n == 0) {
        return "zero";
    } else {
        return "positive";
    }
};
~~~

Đây là đoạn minh họa hợp lệ với import Function. Khi đến nhánh nào, lambda cũng trả String.

Có thể viết cùng quy tắc bằng nhiều **return** sớm:

~~~java
Function<Integer, String> classify = n -> {
    if (n < 0) {
        return "negative";
    }
    if (n == 0) {
        return "zero";
    }
    return "positive";
};
~~~

Cả hai phiên bản đều có đường đi trả kết quả đầy đủ. Việc sử dụng **early return** có thể giúp tránh khối **else** lồng quá sâu, miễn là logic nghiệp vụ rõ ràng.

### 5.2. Nhánh bị bỏ sót: thiếu return

~~~java
// KHÔNG BIÊN DỊCH:
Function<Integer, String> incomplete = n -> {
    if (n > 0) {
        return "positive";
    }
    // n <= 0 đi đến cuối khối mà không trả giá trị.
};
~~~

Với đầu vào **0** hoặc **-1**, điều kiện không thỏa và luồng đi tới cuối khối. Vì SAM phải trả String, không thể chấp nhận đường đi này.

Cách sửa là thêm nhánh mặc định hoặc trả về sau if:

~~~java
Function<Integer, String> complete = n -> {
    if (n > 0) {
        return "positive";
    }
    return "non-positive";
};
~~~

Trong ví dụ thực tế, nhánh mặc định phải phù hợp nghiệp vụ; không nên thêm một giá trị giả chỉ để trình biên dịch hết báo lỗi.

### 5.3. Throw là một đường đi kết thúc hợp lệ

~~~java
Function<String, Integer> parsePositive = text -> {
    int parsed = Integer.parseInt(text);
    if (parsed <= 0) {
        throw new IllegalArgumentException("must be positive");
    }
    return parsed;
};
~~~

Đoạn minh họa trên hợp lệ với import Function. Nếu đầu vào không biểu diễn số nguyên, **Integer.parseInt** có thể ném **NumberFormatException**; nếu số không dương, lambda chủ động ném **IllegalArgumentException**. Những nhánh này không **trả giá trị** vì chúng **kết thúc đột ngột bằng exception**, nên không vi phạm hợp đồng của SAM trả Integer.

Không nên thay thế exception thật bằng giá trị sentinel như **0** hoặc **null** nếu nghiệp vụ yêu cầu báo lỗi; đây là quyết định về hợp đồng API, không phải yêu cầu để làm lambda biên dịch.

### 5.4. Trình biên dịch không chứng minh mọi sự thật nghiệp vụ

Đừng kỳ vọng Java tự hiểu rằng mọi giá trị dữ liệu thực tế đều nằm trong khoảng bạn dự đoán. Ví dụ:

~~~java
// KHÔNG BIÊN DỊCH:
Function<Integer, String> wrong = n -> {
    if (n > 0) {
        return "positive";
    }
    if (n <= 0) {
        return "non-positive";
    }
};
~~~

Con người biết với **int** thì một trong hai điều kiện sẽ đúng, nhưng kiểm tra đường đi của Java không phải bộ chứng minh logic tổng quát cho các điều kiện này. Hãy dùng **else** hoặc **return mặc định** rõ ràng:

~~~java
Function<Integer, String> right = n -> {
    if (n > 0) {
        return "positive";
    } else {
        return "non-positive";
    }
};
~~~

Đoạn này giúp **mọi đường đi** hiển nhiên trả String và dễ bảo trì khi thêm nhánh.

## 6. Lambda trả void: return; chỉ để thoát sớm

Với **void-compatible block**, mọi **return** bên trong (nếu có) phải là **return;** không kèm giá trị. Khối void có thể chạy hết rồi kết thúc bình thường; không cần return bắt buộc.

~~~java
Consumer<String> printNonBlank = s -> {
    if (s == null || s.isBlank()) {
        return;
    }
    System.out.println(s);
};
~~~

Đây là đoạn hợp lệ với import Consumer. Nếu đầu vào null/rỗng/khoảng trắng, lambda kết thúc mà không in. Nếu hợp lệ, nó in và tự kết thúc ở cuối khối.

Nhưng:

~~~java
// KHÔNG BIÊN DỊCH:
Consumer<Integer> wrong = n -> {
    return n * 2;
};
~~~

Vì **Consumer.accept** có kiểu **void**, không được trả một biểu thức có giá trị. Cũng không được dùng **return;** trong khối lambda được dùng làm SAM trả giá trị như **Function<Integer,Integer>**.

Đặt cạnh nhau:

| SAM của target type | Lambda dạng khối | Kết luận |
| --- | --- | --- |
| **void run()** | **() -> { return; }** | Hợp lệ |
| **void accept(T)** | **x -> { log(x); }** | Hợp lệ nếu log được định nghĩa và câu lệnh hợp lệ |
| **R apply(T)** | **x -> { return transform(x); }** | Hợp lệ nếu transform trả R tương thích |
| **R apply(T)** | **x -> { transform(x); }** | Không hợp lệ khi khối có thể kết thúc bình thường |
| **void accept(T)** | **x -> { return x; }** | Không hợp lệ vì trả giá trị |
| **R apply(T)** | **x -> { return; }** | Không hợp lệ vì thiếu giá trị |

Các biểu thức **log(x)** và **transform(x)** trong bảng là tên mô tả giả định; bảng dùng để phân loại quy tắc, không phải chương trình độc lập.

## 7. Chương trình Java 17: return với biểu thức, khối và các nhánh

Tạo tệp **LambdaReturnDemo.java**:

~~~java
import java.util.List;
import java.util.Locale;
import java.util.function.Consumer;
import java.util.function.Function;
import java.util.function.Predicate;
import java.util.function.Supplier;

public class LambdaReturnDemo {
    public static void main(String[] args) {
        Function<Integer, Integer> doubleIt = n -> n * 2;

        Function<Integer, String> classify = n -> {
            if (n < 0) {
                return "negative";
            }
            if (n == 0) {
                return "zero";
            }
            return "positive";
        };

        Function<String, Integer> safeLength = s -> {
            if (s == null) {
                return 0;
            }
            return s.strip().length();
        };

        Predicate<String> nonBlank =
                s -> s != null && !s.isBlank();

        Consumer<String> printUpper = s -> {
            if (!nonBlank.test(s)) {
                return; // Thoát khỏi lần chạy Consumer.
            }
            System.out.println(s.toUpperCase(Locale.ROOT));
        };

        Supplier<String> defaultLabel = () -> "unknown";

        List<Integer> inputs = List.of(-2, 0, 3);
        List<String> labels = inputs.stream()
                .map(classify)
                .toList();

        System.out.println("Double: " + doubleIt.apply(6));
        System.out.println("Classes: " + labels);
        System.out.println("Length: " + safeLength.apply(" Java "));
        System.out.println("Null length: " + safeLength.apply(null));
        printUpper.accept("java");
        printUpper.accept("   ");
        System.out.println("Fallback: " + defaultLabel.get());
    }
}
~~~

Chạy bằng JDK 17 trở lên:

~~~bash
javac -encoding UTF-8 LambdaReturnDemo.java
java LambdaReturnDemo
~~~

Stdout:

~~~text
Double: 12
Classes: [negative, zero, positive]
Length: 4
Null length: 0
JAVA
Fallback: unknown
~~~

**Giải thích:**

- **doubleIt** là expression lambda: kết quả **n * 2** tự trở thành giá trị trả về.
- **classify** là block lambda có ba khả năng; n âm, bằng 0 và dương đều đi đến một **return String**.
- **safeLength** dùng early return khi null, rồi trả chiều dài chuỗi đã **strip()**; đây là ví dụ hợp đồng xử lý dữ liệu thiếu một cách tường minh.
- **nonBlank** dùng Predicate trả boolean qua biểu thức, được tái sử dụng trong Consumer.
- **printUpper** có SAM trả void, nên **return;** chỉ kết thúc Consumer khi chuỗi rỗng. Nó không dừng **main**; các dòng sau vẫn chạy.
- **defaultLabel** trả String thông qua expression lambda không tham số.
- **Stream.map(classify)** sử dụng Function phù hợp và tạo ba nhãn. **toList()** là terminal operation từ Java 16+, có trên Java 17.

Đừng nhầm **“không in dòng nào”** với **“không trả giá trị cho Function”**: Consumer không yêu cầu kết quả, còn Function cần đường đi hợp lệ tạo kết quả.

## 8. Java 17: đường đi return hoặc throw ở quy tắc nghiệp vụ

Một nghiệp vụ thường có nhiều nhánh quyết định: trả giá trị khi hợp lệ, hoặc ném exception khi đầu vào vi phạm hợp đồng. Trong trường hợp này cần kiểm soát chặt chẽ tất cả đường đi.

Tạo tệp **RegistrationRulesDemo.java**:

~~~java
import java.util.List;
import java.util.function.Function;

record Registration(String id, int age, boolean consent) {}

public class RegistrationRulesDemo {
    public static void main(String[] args) {
        Function<Registration, String> classify = r -> {
            if (r == null) {
                throw new IllegalArgumentException(
                        "registration required");
            }
            if (r.age() < 0) {
                throw new IllegalArgumentException(
                        "age must be non-negative");
            }
            if (r.age() < 18) {
                return "MINOR";
            }
            if (!r.consent()) {
                return "NO_CONSENT";
            }
            return "ACCEPTED";
        };

        List<Registration> requests = List.of(
                new Registration("A", 15, true),
                new Registration("B", 21, false),
                new Registration("C", 25, true)
        );

        for (Registration request : requests) {
            System.out.println(request.id() + " -> "
                    + classify.apply(request));
        }
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 RegistrationRulesDemo.java
java RegistrationRulesDemo
~~~

Stdout:

~~~text
A -> MINOR
B -> NO_CONSENT
C -> ACCEPTED
~~~

**Vì sao hợp lệ?** Có những nhánh ném exception và những nhánh trả String. Không có đường đi nào kết thúc bình thường mà thiếu giá trị. Nếu thêm nhánh nghiệp vụ mới nhưng bỏ sót **return**, trình biên dịch sẽ chặn nhiều trường hợp; tuy vậy, trình biên dịch **không kiểm tra rằng các nhãn hoặc điều kiện đó đúng với chính sách kinh doanh**. Điều này vẫn cần unit test.

**Vì sao nên kiểm tra null trước?** Nếu gọi **r.age()** khi **r == null**, Java sẽ ném NullPointerException; đoạn mã đang chọn thông báo hợp đồng rõ hơn bằng IllegalArgumentException. Không nhất thiết mọi API đều phải chuyển NPE thành IAE; nhất quán theo hợp đồng đã định nghĩa là điều quan trọng.

## 9. Những trường hợp đặc biệt trong quy tắc tương thích

### 9.1. Block có thể dùng với cả void và value khi chỉ throw

Một khối **không thể kết thúc bình thường** và **không có câu lệnh return** có thể tương thích với cả SAM trả void và SAM trả giá trị. Ví dụ:

~~~java
Runnable failAction = () -> {
    throw new IllegalStateException("failed");
};

Supplier<Integer> failValue = () -> {
    throw new IllegalStateException("failed");
};
~~~

Đây là các đoạn hợp lệ với import Supplier. Cả hai đều **ném exception khi gọi**; chúng không trả giá trị. Sự tương thích được xét ở mức cú pháp/đường đi của khối, không có nghĩa supplier trả được Integer nếu luôn ném lỗi.

Trường hợp này giúp hiểu chính xác định nghĩa: **value-compatible** không nhất thiết chứa một câu lệnh **return expression;** khi mọi đường đi đều kết thúc đột ngột bằng **throw**.

### 9.2. Khối vừa return có giá trị, vừa return; là không tương thích

~~~java
// KHÔNG BIÊN DỊCH với Function<Integer,Integer>:
Function<Integer, Integer> mixed = n -> {
    if (n > 0) {
        return n;
    }
    return;
};
~~~

Khối trộn **return n;** với **return;**, nên không đáp ứng quy tắc tương thích của functional interface trả giá trị hay void. Để sửa, chọn một hợp đồng thống nhất: **trả một giá trị**, hoặc **ném exception** nếu đường đi thực sự không thể cung cấp kết quả.

### 9.3. Return trong lambda lồng nhau không thay return của lambda ngoài

~~~java
Supplier<Supplier<String>> factory = () -> {
    return () -> {
        return "inner";
    };
};
~~~

Đây là đoạn minh họa với import Supplier. **return "inner";** thuộc **lambda bên trong**; lambda bên ngoài trả về một đối tượng **Supplier<String>**. Hai cấp lambda có hai hợp đồng và hai luồng trả về khác nhau.

Nếu lambda được truyền vào **forEach**, một **return;** bên trong Consumer chỉ kết thúc xử lý của phần tử hiện tại, không tương đương **break** để ngừng toàn bộ vòng duyệt hay **return** khỏi phương thức bao ngoài. Muốn dừng sớm trong Stream có thể cân nhắc terminal operation short-circuit như **anyMatch**, **findFirst** hoặc sử dụng vòng lặp phù hợp với yêu cầu điều khiển.

### 9.4. Lambda dạng biểu thức với switch expression

Trên Java 17, **switch expression** trả về giá trị và có thể làm body của Function:

~~~java
Function<Integer, String> label = n -> switch (n) {
    case 0 -> "zero";
    case 1 -> "one";
    default -> "other";
};
~~~

Đoạn này là minh họa có import Function. **switch expression** phải tạo một giá trị cho tất cả các nhánh hợp lệ; dấu **;** sau dấu ngoặc đóng là dấu kết thúc khai báo biến. Trong switch expression có khối, dùng **yield** để tạo kết quả của nhánh switch; **return** thuộc về phương thức/lambda bao quanh và không phải cách thay thế trực tiếp cho **yield** bên trong switch expression.

Ví dụ khối switch expression:

~~~java
Function<Integer, String> label = n -> switch (n) {
    case 0 -> "zero";
    default -> {
        String text = "value-" + n;
        yield text;
    }
};
~~~

Đoạn này cũng là minh họa: nhánh default dùng **yield** để đóng góp giá trị cho switch expression. **yield** và **return** có trách nhiệm khác nhau.

### 9.5. Tham số và kết quả phải tương thích kiểu

~~~java
Predicate<Integer> isEven = n -> n % 2 == 0;
Function<Integer, String> text = n -> "n=" + n;
~~~

Đây là hai đoạn hợp lệ với import tương ứng. Nhưng:

~~~java
// KHÔNG BIÊN DỊCH:
Predicate<Integer> wrong = n -> "yes";
~~~

Predicate phải trả boolean/Boolean tương thích, nên String không đáp ứng hợp đồng. Ngoài chuyện có **return** hay không, Java còn kiểm tra kiểu dữ liệu của kết quả và checked exception được phép bởi SAM.

### 9.6. Checked exception vẫn cần được xử lý đúng hợp đồng

~~~java
// KHÔNG BIÊN DỊCH nếu IOException chưa được bắt hoặc khai báo
// trong SAM có kiểu Function<Path,String>:
Function<Path, String> read = path -> Files.readString(path);
~~~

Đây là ví dụ **cố ý không biên dịch**, giả định import **java.nio.file.Files**, **java.nio.file.Path**, và **Function**. **Files.readString** có thể ném checked **IOException**, còn **Function.apply** không khai báo exception đó.

Một lựa chọn nếu nghiệp vụ cho phép chuyển thành unchecked exception là bắt IOException trong block và ném **UncheckedIOException**; hoặc khai báo một functional interface riêng có SAM **throws IOException**. Không nên nuốt lỗi rồi trả String rỗng chỉ để hợp lệ cú pháp, trừ khi đó là chính sách được xác định rõ.

## 10. Lỗi thường gặp và cách chẩn đoán

| Hiện tượng | Nguyên nhân thường gặp | Cách sửa |
| --- | --- | --- |
| **Missing return statement** hoặc incompatible lambda body | Một nhánh của block lambda trả giá trị đi đến cuối mà không return | Rà soát từng nhánh, thêm return/else/throw phù hợp |
| **Unexpected return value** | Dùng **return expression;** trong Consumer/Runnable trả void | Chuyển sang hành vi void, dùng **return;** nếu chỉ thoát |
| **Incompatible types: void cannot be converted** | Body trả void ở chỗ đòi giá trị | Dùng Function/Supplier có phép tính tạo giá trị hoặc đổi hợp đồng |
| **Not a statement** hoặc bad return type | Dùng literal/arithmetic expression làm expression body của SAM void | Đổi body thành statement expression hợp lệ hoặc chọn SAM trả giá trị |
| Biểu thức trong block không có **return** | Nhầm expression body với block body | Viết **return expression;** khi cần giá trị |
| Lambda gọi từ **forEach** với **return;** nhưng không dừng toàn bộ Stream | Return chỉ thoát một lần chạy Consumer | Dùng vòng lặp/break hoặc terminal operation dừng sớm |
| Nhiều lambda lồng nhau trả kết quả sai tầng | Return thuộc lambda gần nhất đang bao đoạn mã | Xác định SAM và kiểu kết quả ở từng cấp |
| Body trả sai kiểu | Kết quả không tương thích với kiểu trả về của SAM | Sửa biểu thức hoặc chọn interface phù hợp |
| Lỗi checked exception | Body gọi API ném checked exception mà SAM không cho phép | Catch theo chính sách hoặc thiết kế SAM có throws thích hợp |
| Dựa vào compiler để kiểm chứng nghiệp vụ | Compiler kiểm tra kiểu/cú pháp/đường đi, không chứng minh đúng quy tắc nghiệp vụ | Viết test các nhánh, biên và lỗi |

Một cách chẩn đoán gọn:

1. **Xem SAM của target type trả gì.**
2. **Xác định body là expression hay block.**
3. **Nếu là block trả giá trị, vẽ từng nhánh: return giá trị, throw, hay rơi ra cuối?**
4. **Nếu là void block, kiểm tra mọi return không chứa giá trị.**
5. **Kiểm tra kiểu dữ liệu của biểu thức return và các checked exception.**
6. **Kiểm tra lại đầu ra thực tế, không chỉ việc biên dịch thành công.**

Đừng che lỗi bằng cách thêm **return null;** hoặc **return 0;** cho mọi nhánh. Giá trị mặc định phải có ý nghĩa và phải được diễn đạt trong hợp đồng ứng dụng.

## 11. Tự luyện tập

### Bài 1: Phân loại tính hợp lệ

Xét các khai báo sau và xác định cái nào biên dịch được (giả định các import tương ứng):

~~~java
Function<Integer, Integer> a = x -> x + 1;
Function<Integer, Integer> b = x -> { return x + 1; };
Function<Integer, Integer> c = x -> { x + 1; };
Consumer<Integer> d = x -> { System.out.println(x); };
Consumer<Integer> e = x -> { return x; };
Supplier<Integer> f = () -> { throw new IllegalStateException(); };
~~~

Đây là tập **ví dụ phân loại có phần tử cố ý sai**, không biên dịch nguyên khối. Đáp án: **a**, **b**, **d**, **f** hợp lệ; **c** sai do **x + 1** không phải statement expression hợp lệ và không trả Integer; **e** sai vì Consumer không trả giá trị. Với **f**, đường đi duy nhất ném exception nên khối tương thích với Supplier<Integer>.

### Bài 2: Sửa đường đi bị thiếu

~~~java
// KHÔNG BIÊN DỊCH:
Function<Integer, String> sign = n -> {
    if (n > 0) {
        return "POSITIVE";
    }
    if (n < 0) {
        return "NEGATIVE";
    }
};
~~~

Hãy bổ sung trường hợp **n == 0** bằng **return "ZERO";** cuối khối hoặc viết **if/else if/else** bảo đảm mọi nhánh đều trả String. Sau đó kiểm thử với **-1, 0, 1**.

### Bài 3: Chuyển expression lambda thành block lambda

Chuyển **Predicate<String> nonEmpty = s -> s != null && !s.isEmpty();** thành khối nhiều dòng nhưng giữ nguyên kết quả với null, chuỗi rỗng và chuỗi thường. Dùng **return** phù hợp với boolean.

### Bài 4: Thoát sớm trong void lambda

Tạo **Consumer<String>** chỉ in dữ liệu khi chuỗi không null và không blank. Dùng **return;** để bỏ qua đầu vào không hợp lệ. Giải thích vì sao câu lệnh đó không làm dừng phương thức **main**.

### Bài 5: Phân biệt return và yield

Viết một **Function<Integer,String>** dùng switch expression để phân loại 0 và số khác 0. Tạo một nhánh switch có khối dùng **yield**. Giải thích **yield** đưa kết quả cho switch expression, còn **return** kết thúc body lambda.

## 12. Ghi nhớ

- **Expression lambda** trả giá trị biểu thức khi SAM cần giá trị; không viết `return` trong body dạng biểu thức.
- **Block lambda trả giá trị** phải bảo đảm không có đường đi kết thúc bình thường mà thiếu giá trị; dùng **return expression;** hoặc **throw** khi thích hợp.
- **Block lambda trả void** có thể kết thúc tự nhiên, hoặc dùng **return;** để thoát sớm; không được **return expression;**.
- **Expression lambda của SAM void** chỉ hợp lệ nếu body là **statement expression** (như lời gọi phương thức), kể cả khi lời gọi đó tạo kết quả bị bỏ qua.
- **Return chỉ kết thúc lambda đang thực thi**, không tự động thoát khỏi phương thức bao quanh hoặc vòng xử lý Stream.
- **Kiểu đích, đường đi điều khiển, kiểu trả về và checked exception** cùng quyết định lambda có biên dịch được hay không.

Khi chuyển từ lambda một dòng sang nhiều nhánh, hãy đọc từng nhánh theo câu hỏi: **“Lời gọi này trả giá trị, ném lỗi hay chỉ kết thúc công việc?”** Đó là cách đơn giản để viết callback đúng hợp đồng và tránh sai sót khi mở rộng logic.