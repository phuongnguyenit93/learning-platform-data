# Enum triển khai giao diện

## 1. Enum có thể vừa là một tập lựa chọn, vừa cung cấp hành vi

Một enum không chỉ có các nhãn để so sánh trong `switch`. Nó có thể thực hiện interface như một lớp Java thông thường, miễn đáp ứng đầy đủ hợp đồng của interface đó.

Ví dụ một hợp đồng tính toán trên hai số nguyên:

```java
interface IntOperation {
    int apply(int left, int right);
}
```

Một enum thực hiện hợp đồng:

```java
enum SelectionOperation implements IntOperation {
    MIN,
    MAX;

    @Override
    public int apply(int left, int right) {
        return switch (this) {
            case MIN -> Math.min(left, right);
            case MAX -> Math.max(left, right);
        };
    }
}
```

Mỗi hằng `MIN`, `MAX` là một giá trị `SelectionOperation`, đồng thời dùng được ở vị trí cần `IntOperation`:

```java
IntOperation operation = SelectionOperation.MAX;
int result = operation.apply(12, 5); // 12
```

Interface mô tả **đối tượng làm được gì**. Enum xác định **những lựa chọn cụ thể nào thuộc cùng kiểu liệt kê**. Hai vai trò bổ sung cho nhau.

Khả năng enum thực hiện superinterface được quy định trong [JLS §8.9](https://docs.oracle.com/javase/specs/jls/se25/html/jls-8.html#jls-8.9). Các ví dụ trong bài dùng Java 17 trở lên và vẫn áp dụng cho Java hiện đại.

## 2. Vì sao truyền interface thay vì buộc nơi gọi dùng đúng một enum?

Giả sử một hàm cần thực hiện phép toán, không cần biết phép toán thuộc nhóm enum nào:

```java
static int evaluate(IntOperation operation, int left, int right) {
    return Objects.requireNonNull(operation, "operation").apply(left, right);
}
```

Nơi gọi có thể truyền bất kỳ đối tượng nào thực hiện đúng hợp đồng `IntOperation` của ví dụ. Hàm không cần kiểm tra tên enum hoặc viết một chuỗi nhánh phụ thuộc mọi loại phép toán có thể xuất hiện.

Điều này là đa hình: cùng lời gọi `apply` nhưng hành vi được quyết định bởi đối tượng thực tế đang được truyền vào.

Nếu chữ ký nhận riêng `SelectionOperation`, nó chỉ chấp nhận `MIN` và `MAX` của kiểu đó. Nếu chữ ký nhận `IntOperation`, nó có thể làm việc với một enum phép toán số học khác, một lớp thông thường hoặc một lambda/method reference phù hợp khi interface là functional interface.

Không phải lúc nào cũng nên mở chữ ký thành interface. Nếu nghiệp vụ thực sự chỉ chấp nhận một tập hằng cụ thể, tham số enum có thể chính xác hơn. Hãy chọn kiểu tham số theo điều hàm cần bảo đảm, không chỉ theo mong muốn có thêm tính linh hoạt.

Các đoạn rời trong bài cần import kiểu thư viện chuẩn tương ứng khi đưa vào một lớp Java.

## 3. Cách thứ nhất: triển khai chung trong thân enum

`SelectionOperation` phía trên có một phương thức `apply` chung cho mọi hằng. Phương thức dùng `this` để phân biệt `MIN` với `MAX`.

Cách này phù hợp khi hành vi có chung cấu trúc và phần lựa chọn còn gọn, dễ đọc. Một enum cũng có thể lưu dữ liệu riêng của từng hằng rồi dùng một phương thức chung dựa trên dữ liệu đó.

Không cần tạo một phần thân riêng cho mọi hằng nếu khác biệt chỉ là một giá trị cấu hình nhỏ. Ngược lại, nếu mỗi hằng có thuật toán khác hẳn nhau và nhiều nơi phải lặp lại cùng một `switch`, có thể cân nhắc đưa hành vi vào từng hằng.

Điều quan trọng là interface được thỏa mãn bởi các phương thức phù hợp, không phải mọi enum thực hiện interface đều bắt buộc theo một mẫu cấu trúc duy nhất.

## 4. Cách thứ hai: mỗi hằng có phần triển khai riêng

Có thể đặt phương thức ghi đè trong phần thân của hằng:

```java
enum ArithmeticOperation implements IntOperation {
    ADD {
        @Override
        public int apply(int left, int right) {
            return Math.addExact(left, right);
        }
    },
    MULTIPLY {
        @Override
        public int apply(int left, int right) {
            return Math.multiplyExact(left, right);
        }
    };

    @Override
    public abstract int apply(int left, int right);
}
```

Ví dụ này là một phiên bản rút gọn độc lập; chương trình đầy đủ phía dưới còn thêm nhãn cho các phép toán.

`ADD` và `MULTIPLY` vẫn là các hằng của cùng kiểu `ArithmeticOperation`, nhưng lời gọi `apply` đi tới phần triển khai tương ứng của từng hằng.

Khi enum khai báo một phương thức abstract như trên, mỗi hằng phải cung cấp một triển khai cụ thể phù hợp. Không dùng `abstract enum` để biểu đạt điều đó; quy tắc riêng của enum kiểm tra rằng các hằng có triển khai đầy đủ.

Phần thân riêng của hằng được ngôn ngữ mô hình hóa bằng một lớp con ẩn danh của enum. Điều này không mở quyền cho mã bên ngoài tự kế thừa enum để thêm hằng mới. Các quy tắc được mô tả ở [JLS §8.9.1](https://docs.oracle.com/javase/specs/jls/se25/html/jls-8.html#jls-8.9.1).

Trong ví dụ, `Math.addExact` và `multiplyExact` ném `ArithmeticException` nếu kết quả tràn `int`. Đây là lựa chọn hợp đồng của phép toán, không phải một đặc tính tự động của enum hoặc interface.

## 5. Phương thức triển khai phải có mức truy cập phù hợp

Phương thức abstract thông thường được khai báo trong interface là `public`. Khi thực hiện nó trong enum, cần giữ mức truy cập đó:

```java
@Override
public int apply(int left, int right) {
    return Math.min(left, right);
}
```

Nếu bỏ `public` và chỉ tạo một phương thức có quyền truy cập package, enum không thỏa mãn phương thức public mà interface yêu cầu.

`@Override` giúp compiler phát hiện những nhầm lẫn như sai tên, sai kiểu tham số hoặc vô tình tạo overload thay vì triển khai đúng phương thức. Enum không được miễn các quy tắc về kiểu trả về, ngoại lệ được phép hay khả năng truy cập của interface.

Một triển khai có thể được cung cấp bởi phương thức chung trong enum, phần thân hằng hoặc một phương thức kế thừa phù hợp. Không cần viết lại một phương thức đã được thỏa mãn đúng chỉ vì kiểu đang là enum.

## 6. Một enum có thể thực hiện nhiều interface

Có thể khai báo:

```text
enum ArithmeticOperation implements IntOperation, Labeled
```

Đây là dạng tiêu đề khai báo rút gọn. `IntOperation` mô tả phép tính; `Labeled` mô tả khả năng cung cấp một nhãn.

Với:

```java
interface Labeled {
    String label();
}
```

một hằng có thể được dùng qua hai góc nhìn:

```java
IntOperation operation = ArithmeticOperation.MULTIPLY;
Labeled labeled = ArithmeticOperation.MULTIPLY;
```

Hai biến cùng có thể trỏ tới một đối tượng hằng nhưng cho phép gọi những phương thức khác nhau theo kiểu tĩnh của chúng. Qua `IntOperation` đã định nghĩa trong bài, không tự gọi được `label()`; qua `Labeled`, không tự gọi được `apply()`.

Mọi enum trực tiếp kế thừa `java.lang.Enum<E>` theo cơ chế ngôn ngữ. Không viết một `extends` để enum kế thừa lớp dữ liệu khác. Việc thực hiện nhiều interface không chiếm vị trí lớp cha đó. Xem lớp nền [Enum](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Enum.html).

## 7. Phương thức default và hợp đồng kế thừa vẫn theo quy tắc Java

Interface có thể cung cấp một phương thức `default` xây từ phương thức bắt buộc:

```java
@FunctionalInterface
interface IntOperation {
    int apply(int left, int right);

    default int applyToSameValue(int value) {
        return apply(value, value);
    }
}
```

Trong phiên bản này, interface vẫn có một phương thức abstract nên có thể là functional interface. Enum thực hiện `apply` có thể dùng luôn `applyToSameValue`; lời gọi bên trong tiếp tục đi tới hành vi của hằng cụ thể.

Nếu hai interface cung cấp các default xung đột và những quy tắc ưu tiên không giải quyết được, enum phải ghi đè để xác định rõ hành vi, giống một lớp thông thường. Không có cơ chế riêng tự chọn ngẫu nhiên default vì đối tượng là enum.

Các quy tắc kế thừa/ghi đè của interface nằm trong [JLS §9.4.1](https://docs.oracle.com/javase/specs/jls/se25/html/jls-9.html#jls-9.4.1).

## 8. Tập hằng vẫn thuộc từng enum, không thuộc interface

Giả sử `ArithmeticOperation` và `SelectionOperation` đều thực hiện `IntOperation`:

- `ArithmeticOperation.values()` liệt kê hằng của `ArithmeticOperation`.
- `SelectionOperation.values()` liệt kê hằng của `SelectionOperation`.
- `IntOperation` không tự có một `values()` tổng hợp mọi cách triển khai.

Hai enum không trở thành cùng một kiểu chỉ vì cùng interface. Một biến `ArithmeticOperation` không tự nhận được `SelectionOperation.MIN`. Nhưng cả hai dùng được trong `List<IntOperation>` để xử lý thống nhất theo hành vi.

Qua tham chiếu `IntOperation` của bài này, cũng không tự gọi được `name()` hoặc `ordinal()`: chúng không thuộc hợp đồng interface đã khai báo. Nếu một hàm cần biết danh tính hằng enum chứ không chỉ cần phép tính, phải biểu đạt thêm yêu cầu đó trong thiết kế API phù hợp.

Đừng thêm `name()` vào mọi interface chỉ để ép mọi triển khai có hình thức giống enum. Một lớp thông thường hoặc method reference thực hiện hành vi có thể không có khái niệm tên hằng enum.

Interface thông thường của ví dụ cho phép có những triển khai khác ngoài hai enum. Thêm một enum mới thực hiện interface không thêm hằng vào các enum cũ; tập lựa chọn của mỗi enum vẫn do chính khai báo đó xác định.

## 9. Chương trình hoàn chỉnh

Lưu vào `EnumInterfaceDemo.java`, dùng Java 17 trở lên:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public class EnumInterfaceDemo {
    @FunctionalInterface
    interface IntOperation {
        int apply(int left, int right);

        default int applyToSameValue(int value) {
            return apply(value, value);
        }
    }

    interface Labeled {
        String label();
    }

    enum ArithmeticOperation implements IntOperation, Labeled {
        ADD("+") {
            @Override
            public int apply(int left, int right) {
                return Math.addExact(left, right);
            }
        },
        MULTIPLY("*") {
            @Override
            public int apply(int left, int right) {
                return Math.multiplyExact(left, right);
            }
        };

        private final String label;

        ArithmeticOperation(String label) {
            this.label = label;
        }

        @Override
        public String label() {
            return label;
        }

        @Override
        public abstract int apply(int left, int right);
    }

    enum SelectionOperation implements IntOperation {
        MIN,
        MAX;

        @Override
        public int apply(int left, int right) {
            return switch (this) {
                case MIN -> Math.min(left, right);
                case MAX -> Math.max(left, right);
            };
        }
    }

    static int evaluate(IntOperation operation, int left, int right) {
        return Objects.requireNonNull(operation, "operation").apply(left, right);
    }

    public static void main(String[] args) {
        IntOperation arithmetic = ArithmeticOperation.ADD;
        IntOperation selection = SelectionOperation.MAX;
        IntOperation subtraction = Math::subtractExact;
        System.out.println("add = " + evaluate(arithmetic, 12, 5));
        System.out.println("max = " + evaluate(selection, 12, 5));
        System.out.println("subtract = " + evaluate(subtraction, 12, 5));
        System.out.println("same value = " + ArithmeticOperation.ADD.applyToSameValue(3));

        Labeled labeled = ArithmeticOperation.MULTIPLY;
        System.out.println("label = " + labeled.label());

        List<IntOperation> operations = List.of(
                ArithmeticOperation.ADD,
                ArithmeticOperation.MULTIPLY,
                SelectionOperation.MIN,
                SelectionOperation.MAX,
                subtraction);
        List<Integer> results = new ArrayList<>();
        for (IntOperation operation : operations) {
            results.add(evaluate(operation, 12, 5));
        }
        System.out.println("results = " + results);
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -Xlint:all -Werror -encoding UTF-8 EnumInterfaceDemo.java
java EnumInterfaceDemo
```

Kết quả chuẩn:

```text
add = 17
max = 12
subtract = 7
same value = 6
label = *
results = [17, 60, 5, 12, 7]
```

Các điểm cần đọc từ ví dụ:

1. `evaluate` chỉ cần khả năng `apply`, nên nhận `IntOperation`.
2. `ArithmeticOperation` dùng phần triển khai riêng từng hằng và một phần triển khai nhãn chung.
3. `SelectionOperation` dùng một phương thức chung với `switch` gọn.
4. Phương thức `default` gọi lại hành vi được enum cung cấp.
5. `Math::subtractExact` thực hiện cùng functional interface mà không cần là hằng enum.
6. Danh sách thao tác được nhóm tường minh bằng `List.of`; interface không tự cung cấp một bộ liệt kê tất cả triển khai.

Dữ liệu đầu vào được truyền qua tham số và kết quả được trả về; các hằng không lưu dữ liệu riêng của từng lần yêu cầu. Điều này giữ vai trò “lựa chọn hành vi dùng chung” rõ ràng.

## 10. Khi nào thiết kế này hữu ích?

Enum thực hiện interface phù hợp khi có một tập lựa chọn hành vi đã biết, cần danh tính hằng rõ ràng và muốn dùng các lựa chọn đó qua một hợp đồng chung.

Ví dụ một bộ xử lý cần chọn một trong vài chính sách tính toán cố định có thể nhận interface của chính sách. Enum cung cấp những lựa chọn chuẩn, còn nơi gọi không phải biết chi tiết từng hằng thực hiện thế nào.

Tuy nhiên, không nên gom mọi dịch vụ khác nhau vào một enum chỉ để có cú pháp `implements`. Nếu mỗi cách triển khai cần dữ liệu cấu hình riêng cho từng đối tượng, phụ thuộc có vòng đời riêng hoặc cần tạo số lượng instance tùy ý, một lớp thông thường có thể phù hợp hơn.

Một hằng enum là đối tượng được dùng chung. Thêm trường mutable ghi trạng thái riêng của từng yêu cầu có thể làm các nơi gọi tác động lẫn nhau. Việc thực hiện interface không tự tạo bản sao hằng hoặc bảo đảm an toàn luồng cho mọi trường dữ liệu.

Cũng cần tách hai quyết định:

| Quyết định | Câu hỏi cần trả lời |
| --- | --- |
| Dùng enum hay lớp thông thường | Tập lựa chọn và cách tạo instance có phù hợp miền hữu hạn không? |
| API nhận enum hay interface | Nơi nhận cần chính tập hằng đó hay chỉ cần một khả năng hành vi? |
| Triển khai chung hay riêng từng hằng | Khác biệt chủ yếu là dữ liệu hay những thuật toán khác nhau? |
| Có cần nhiều interface không | Các khả năng có hợp đồng độc lập, có ý nghĩa cho người dùng không? |

Không cần tránh mọi `switch`. Một `switch` nội bộ đơn giản có thể dễ đọc hơn nhiều phần thân riêng gần như giống nhau. Ngược lại, nhiều `switch` rải khắp ứng dụng chỉ để chọn cùng một hành vi có thể là dấu hiệu nên đưa hành vi vào hợp đồng và triển khai tương ứng.

## 11. Những lỗi thường gặp

**Quên `public` ở phương thức triển khai.** Phương thức cần đáp ứng hợp đồng public của interface; giảm quyền truy cập gây lỗi biên dịch.

**Sai chữ ký rồi tưởng đã triển khai.** `apply(long, long)` không thay thế cho `apply(int, int)` chỉ vì cùng tên. Dùng `@Override` để phát hiện sớm.

**Một hằng không triển khai phương thức abstract bắt buộc.** Khi enum yêu cầu từng hằng cung cấp hành vi cụ thể, bỏ trống một hằng làm enum không hoàn chỉnh theo quy tắc ngôn ngữ.

**Dùng `static` để thay phương thức instance của interface.** Một phương thức static cùng tên không cung cấp hành vi đa hình cho đối tượng theo hợp đồng instance.

**Truy cập mọi tiện ích enum qua biến interface.** Kiểu tĩnh `IntOperation` chỉ cho phép các thành viên thuộc hợp đồng tương ứng. Không tự có `values()`, `name()` hay phương thức riêng của enum.

**Nghĩ cùng interface làm mọi hằng thuộc cùng enum.** Interface cho một kiểu cha hành vi chung; nó không hợp nhất các tập hằng hay cho phép kế thừa enum để thêm hằng.

**Đặt trạng thái riêng mỗi lần gọi vào hằng dùng chung.** Truyền trạng thái qua đối số hoặc dùng đối tượng có vòng đời phù hợp khi cần; đừng mặc định mỗi nơi gọi được một bản hằng enum độc lập.

## 12. Tự kiểm tra

**Câu 1.** Vì sao có thể gán `ArithmeticOperation.ADD` vào biến `IntOperation`?

Vì enum đã khai báo thực hiện interface và đáp ứng hợp đồng `apply`. Hằng của enum là đối tượng dùng được ở vị trí cần interface đó.

**Câu 2.** Một enum có thể triển khai cả `IntOperation` và `Labeled` không?

Có, nếu đáp ứng các hợp đồng và giải quyết các xung đột phương thức nếu có. Enum vẫn có lớp cha do ngôn ngữ quản lý.

**Câu 3.** Nếu chỉ cần gọi `apply`, hàm phải nhận chính xác `ArithmeticOperation` không?

Không nhất thiết. Nhận `IntOperation` biểu đạt nhu cầu hành vi và cho phép những triển khai phù hợp khác. Nếu nghiệp vụ cố ý chỉ cho nhóm hằng số học, kiểu enum riêng vẫn có thể là lựa chọn đúng.

**Câu 4.** `IntOperation.values()` có tự liệt kê cả hai enum và method reference trong chương trình không?

Không. `values()` thuộc từng kiểu enum cụ thể, không phải cơ chế liệt kê mọi đối tượng thực hiện interface.

**Câu 5.** Vì sao các phương thức `apply` trong enum đều ghi `public`?

Chúng phải thực hiện phương thức public của interface mà không giảm mức truy cập. Enum không có ngoại lệ cho quy tắc này.
