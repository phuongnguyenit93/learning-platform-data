# Phương thức trừu tượng do từng hằng triển khai

## 1. Khi mỗi hằng cần một cách xử lý khác nhau

Một enum có thể khai báo một phương thức trừu tượng, rồi yêu cầu **mỗi hằng cung cấp phần cài đặt riêng**.

Ví dụ:

```java
enum Operation {
    ADD {
        @Override
        public int apply(int left, int right) {
            return Math.addExact(left, right);
        }
    },
    SUBTRACT {
        @Override
        public int apply(int left, int right) {
            return Math.subtractExact(left, right);
        }
    };

    public abstract int apply(int left, int right);
}
```

Cả hai hằng cùng tuân theo hợp đồng `apply(int, int)`, nhưng hành vi khác nhau:

- `ADD.apply(8, 3)` thực hiện phép cộng.
- `SUBTRACT.apply(8, 3)` thực hiện phép trừ.

Nơi gọi chỉ cần biết kiểu `Operation`:

```java
Operation operation = Operation.ADD;
int result = operation.apply(8, 3);
```

Việc chọn phần cài đặt dựa vào đối tượng hằng mà biến đang tham chiếu. Đây là đa hình (polymorphism), không phải một chuỗi `if` tự động được viết trong mã nguồn.

Cơ chế này vẫn được dùng trong Java hiện đại. Các chương trình và API minh họa bên dưới phù hợp Java 17+.

## 2. Đọc đúng cấu trúc khai báo

Trong ví dụ đầu có ba vùng cần phân biệt:

```text
ADD { ... }                   → thân lớp riêng của hằng ADD
SUBTRACT { ... }              → thân lớp riêng của hằng SUBTRACT
public abstract int apply...; → hợp đồng chung của kiểu Operation
```

Phần `{ ... }` sau tên hằng được gọi là thân lớp riêng của hằng (constant-specific class body). Nó không phải khối `switch`, không phải thân hàm tạo và không chỉ là một khối mã chạy một lần.

Các quy tắc dấu câu:

- Dấu phẩy ngăn cách các hằng, kể cả khi hằng có thân riêng.
- Dấu chấm phẩy sau hằng cuối ngăn danh sách hằng với thành viên chung.
- Phương thức trừu tượng chỉ khai báo chữ ký, không có thân; kết thúc bằng dấu chấm phẩy.
- Mỗi phần cài đặt riêng có thân phương thức thực sự.

Không viết:

```java
// Không hợp lệ:
// public abstract enum Operation { ... }
```

Khai báo enum vẫn dùng `enum Operation`; không thêm modifier `abstract` vào khai báo kiểu enum. Một enum được phép có phương thức trừu tượng theo những điều kiện riêng của ngôn ngữ.

## 3. Mọi hằng phải hoàn tất hợp đồng trừu tượng

Nếu enum khai báo một phương thức trừu tượng, phải có ít nhất một hằng và mọi hằng phải có thân riêng cung cấp các phần cài đặt cần thiết.

Ví dụ cố ý không biên dịch:

```java
enum BrokenOperation {
    ADD {
        @Override
        public int apply(int left, int right) {
            return Math.addExact(left, right);
        }
    },
    SUBTRACT; // Thiếu phần cài đặt apply.

    public abstract int apply(int left, int right);
}
```

Lỗi được phát hiện khi biên dịch. Không cần đợi đến lúc người dùng chọn `SUBTRACT` mới phát hiện thiếu hành vi.

Khi thêm hằng mới, trình biên dịch sẽ tiếp tục yêu cầu nó tuân theo cùng hợp đồng. Đây là một lợi ích khi mỗi giá trị thật sự cần một thuật toán riêng.

### 3.1. Ghi đè đúng chữ ký và quyền truy cập

Nếu phương thức chung là:

```java
public abstract int apply(int left, int right);
```

thì phần cài đặt không được giảm quyền truy cập:

```java
// Sai nếu dùng thay cho phương thức public:
// int apply(int left, int right) { return left + right; }
```

Thêm một overload khác tham số cũng không hoàn tất hợp đồng:

```java
// apply(long, long) không thay cho apply(int, int).
```

Dùng `@Override` giúp trình biên dịch xác nhận đúng quan hệ ghi đè. Tên, tham số và kiểu kết quả phải tuân theo quy tắc ghi đè của Java.

### 3.2. Phương thức cần là phương thức thể hiện

Không thể kết hợp `static abstract` để đạt cơ chế này. Phương thức static không được phân phối động theo hằng như một phương thức thể hiện.

Phương thức private cũng không phải một hợp đồng trừu tượng có thể được các lớp riêng của hằng ghi đè. Chọn mức truy cập phù hợp với nơi cần dùng; ví dụ dùng `public` để cung cấp API rõ ràng cho nơi gọi.

## 4. Cơ chế lớp riêng và một kiểu enum chung

Một hằng có thân lớp riêng tạo ra một lớp con ẩn danh gắn với chính hằng đó. Các hằng vẫn được dùng qua kiểu enum chung:

```text
Operation
    ├── lớp riêng của ADD       → apply thực hiện cộng
    └── lớp riêng của SUBTRACT  → apply thực hiện trừ
```

Đây là sơ đồ khái niệm, không phải những lớp con mà người dùng tự đặt tên để khởi tạo.

Các hệ quả:

- `Operation.values()` vẫn trả mảng các hằng có kiểu phần tử `Operation`.
- Biến `Operation` có thể tham chiếu đến bất kỳ hằng của kiểu đó.
- Nơi gọi dùng `operation.apply(...)` mà không cast sang lớp riêng.
- Không dùng `new` để tạo thêm thể hiện của lớp riêng của hằng.
- Các thân riêng không làm enum trở thành một hệ mở để lớp ngoài tùy ý thêm giá trị.

### 4.1. getClass() có thể khác getDeclaringClass()

Với các hằng có thân riêng:

```java
Operation.ADD.getClass() != Operation.SUBTRACT.getClass()
```

có thể là `true` vì mỗi thân riêng định nghĩa một lớp riêng. Nhưng:

```java
Operation.ADD.getDeclaringClass() == Operation.class
```

là `true`.

Nếu mục tiêu là nhận diện **kiểu enum chứa hằng**, dùng `getDeclaringClass()`. Không phụ thuộc tên nhị phân kiểu `Operation$1` hay số thứ tự của lớp do trình biên dịch sinh; chúng là chi tiết không nên dùng làm mã nghiệp vụ.

Không kết luận một đối tượng “không phải hằng của Operation” chỉ vì `getClass() != Operation.class`.

## 5. Kết hợp phần cài đặt riêng với dữ liệu và phương thức chung

Enum có thể giữ dữ liệu cho từng hằng bằng hàm tạo và trường chung, đồng thời để hành vi khác nhau trong thân riêng:

```java
ADD("add") {
    @Override
    public int apply(int left, int right) {
        return Math.addExact(left, right);
    }
}
```

Đây là một khai báo hằng minh họa trong enum, không phải chương trình độc lập.

Chuỗi `"add"` đi vào hàm tạo chung của enum. Phần `{ ... }` cung cấp cách cài đặt `apply`. Hai phần có trách nhiệm khác nhau.

Một phương thức chung có thể gọi phương thức trừu tượng:

```java
public String describe(int left, int right) {
    return code + "=" + apply(left, right);
}
```

Khi gọi `Operation.ADD.describe(8, 3)`, phần `describe` dùng chung vẫn gọi `apply` của `ADD`.

Đây là cách giữ phần thao tác chung ở một nơi, còn phần thay đổi theo hằng nằm tại hằng tương ứng.

Các trường private của enum nên được dùng qua phương thức chung phù hợp nếu phần cài đặt riêng cần đọc chúng. Chẳng hạn, cung cấp `code()` thay vì coi thân lớp riêng là nơi bỏ qua mọi quy tắc truy cập và kế thừa của Java.

## 6. Chương trình hoàn chỉnh

Lưu thành `EnumAbstractMethodDemo.java`:

```java
import java.util.Objects;

public class EnumAbstractMethodDemo {
    public enum Operation {
        ADD("add") {
            @Override
            public int apply(int left, int right) {
                return Math.addExact(left, right);
            }
        },
        SUBTRACT("subtract") {
            @Override
            public int apply(int left, int right) {
                return Math.subtractExact(left, right);
            }
        },
        MULTIPLY("multiply") {
            @Override
            public int apply(int left, int right) {
                return Math.multiplyExact(left, right);
            }
        };

        private final String code;

        Operation(String code) {
            this.code = Objects.requireNonNull(code, "code");
        }

        public String code() {
            return code;
        }

        public abstract int apply(int left, int right);

        public String describe(int left, int right) {
            return code + "=" + apply(left, right);
        }
    }

    public static void main(String[] args) {
        for (Operation operation : Operation.values()) {
            System.out.println(operation.name()
                    + "(8, 3) = " + operation.apply(8, 3));
        }

        Operation selected = Operation.ADD;
        System.out.println("shared method = " + selected.describe(8, 3));
        System.out.println("same enum type = "
                + (Operation.ADD.getDeclaringClass()
                == Operation.MULTIPLY.getDeclaringClass()));
        System.out.println("different runtime class = "
                + (Operation.ADD.getClass() != Operation.MULTIPLY.getClass()));

        try {
            Operation.ADD.apply(Integer.MAX_VALUE, 1);
        } catch (ArithmeticException failure) {
            System.out.println("overflow = detected");
        }
    }
}
```

Biên dịch và chạy bằng JDK 17+:

```shell
javac --release 17 -encoding UTF-8 -Xlint:all EnumAbstractMethodDemo.java
java EnumAbstractMethodDemo
```

Stdout chính xác:

```text
ADD(8, 3) = 11
SUBTRACT(8, 3) = 5
MULTIPLY(8, 3) = 24
shared method = add=11
same enum type = true
different runtime class = true
overflow = detected
```

Ví dụ chọn `Math.addExact`, `subtractExact` và `multiplyExact` để công bố một chính sách nhất quán: kết quả vượt miền `int` làm phát sinh `ArithmeticException`, thay vì âm thầm quay vòng số nguyên.

Chính sách số học là hợp đồng của phương thức `apply`, không phải do enum tự cung cấp. Các phần cài đặt riêng vẫn phải được kiểm tra về tính đúng đắn; trình biên dịch chỉ bảo đảm chúng tồn tại và khớp chữ ký.

## 7. So với phương thức mặc định và switch

### 7.1. Phương thức có thân chung chỉ yêu cầu ghi đè khi cần

Nếu enum có phương thức thông thường với phần cài đặt chung, một hằng có thể dùng lại nó mà không khai báo thân riêng:

```java
enum Decoration {
    PLAIN,
    BRACKETED {
        @Override
        public String render(String text) {
            return "[" + text + "]";
        }
    };

    public String render(String text) {
        return text;
    }
}
```

`PLAIN` dùng phương thức chung. `BRACKETED` ghi đè nó.

Đây khác với `public abstract String render(...)`: khi hợp đồng là trừu tượng, mọi hằng phải cung cấp phần cài đặt. Chọn phương thức trừu tượng khi không có một hành vi mặc định hợp lý mà mọi hằng chưa ghi đè được phép dùng.

### 7.2. switch có thể phù hợp khi hành vi thuộc một ngữ cảnh khác

Một thao tác bên ngoài có thể dùng `switch` trên enum mà không cần thay enum. Điều đó hữu ích nếu thao tác thuộc về một thành phần khác, chẳng hạn cách trình bày phụ thuộc giao diện.

Thân riêng của hằng phù hợp khi hành vi là một phần cốt lõi, ổn định của chính giá trị enum và mọi nơi gọi đều cần cùng hợp đồng đó.

| Câu hỏi | Gợi ý |
| --- | --- |
| Mỗi hằng bắt buộc có thuật toán riêng? | Cân nhắc phương thức trừu tượng do từng hằng cài đặt |
| Phần lớn hằng dùng chung một hành vi hợp lý? | Phương thức có thân chung, ghi đè có chọn lọc |
| Mọi hằng chỉ khác một hệ số hoặc dữ liệu? | Trường và hàm tạo có thể đủ |
| Cách xử lý thuộc về một lớp trình bày hoặc ngữ cảnh khác? | Một thao tác bên ngoài hoặc chiến lược riêng có thể rõ hơn |
| Cần bổ sung loại hành vi từ plugin lúc chạy? | Một tập enum đóng có thể không phù hợp |

Không dùng đa hình chỉ để thay một biểu thức dữ liệu đơn giản bằng nhiều thân lớp trùng lặp.

## 8. Những lỗi thường gặp

### 8.1. Chỉ thêm một phương thức mới trong thân riêng

```java
enum Example {
    FIRST {
        public String special() {
            return "first";
        }
    }
}
```

Đây là đoạn khai báo hợp lệ, nhưng `special()` không được khai báo trên kiểu `Example`. Vì vậy, mã dùng `Example.FIRST.special()` không có một phương thức như vậy trong kiểu tĩnh `Example`.

Nếu hành vi cần được gọi qua enum, khai báo hợp đồng chung trên enum rồi ghi đè nó. Không cố cast sang một lớp ẩn danh không có tên nguồn để sử dụng phương thức riêng.

### 8.2. Quên xử lý một hằng mới

Nếu hợp đồng là trừu tượng, hằng mới thiếu phần cài đặt sẽ không biên dịch. Không sửa bằng cách thêm một phương thức chung luôn ném `UnsupportedOperationException` chỉ để che việc chưa thiết kế hành vi, trừ khi không hỗ trợ là một phần có chủ đích của hợp đồng.

### 8.3. Giảm quyền truy cập hoặc khai báo nhầm static

Một phương thức `public abstract` cần phần ghi đè có quyền truy cập phù hợp. Phương thức static không thay cho phương thức thể hiện cần được ghi đè. `@Override` là công cụ kiểm tra hữu ích cho cả hai loại sai sót.

### 8.4. Dùng trạng thái mutable làm ngữ cảnh riêng của mỗi lời gọi

Thân riêng có thể khai báo trường, nhưng hằng enum là đối tượng được chia sẻ. Một bộ đếm hoặc biến tạm đặt trên hằng có thể bị nhiều lời gọi hoặc nhiều luồng cùng tác động.

Trong ví dụ, mọi phép tính nhận dữ liệu qua tham số và không sửa hằng. Khi cần trạng thái của từng tác vụ, giữ nó ở đối tượng tác vụ hoặc truyền qua tham số, thay vì đặt trên `Operation.ADD`.

### 8.5. Gọi hành vi ghi đè quá sớm trong hàm tạo

Tránh gọi phương thức có thể được hằng ghi đè từ hàm tạo enum khi hành vi đó phụ thuộc vào các trường của thân lớp riêng. Phần khởi tạo của lớp riêng có thể chưa hoàn tất khi hàm tạo của enum đang chạy.

Hàm tạo nên thiết lập dữ liệu đơn giản; gọi hành vi sau khi các hằng đã được khởi tạo đầy đủ.

## 9. Cách kiểm tra một thiết kế

Với enum có phương thức trừu tượng, hãy xác nhận:

1. Hợp đồng chung có tên, tham số, kết quả và điều kiện lỗi rõ ràng.
2. Mọi hằng đều cài đặt đủ các phương thức bắt buộc.
3. Phần chung không bị sao chép vào từng hằng nếu có thể đặt ở một phương thức dùng chung.
4. Các thân riêng không chứa trạng thái thuộc từng người dùng hoặc từng tác vụ.
5. Mã gọi chỉ cần kiểu enum chung và không phụ thuộc tên lớp do trình biên dịch sinh.
6. Kiểm chứng từng hành vi và những điều kiện biên quan trọng, như tràn số trong ví dụ.

Một enum theo mẫu này kết hợp được tập giá trị đóng với nhiều cách cài đặt của cùng một hợp đồng. Nơi gọi chọn một hằng rồi dùng hành vi qua kiểu chung, còn trình biên dịch giúp phát hiện hằng nào chưa hoàn tất nghĩa vụ của nó.

## Tài liệu đối chiếu

- [JLS §8.9.1 — Enum Constants](https://docs.oracle.com/javase/specs/jls/se25/html/jls-8.html#jls-8.9.1): thân lớp riêng của từng hằng.
- [JLS §8.9.2 — Enum Body Declarations](https://docs.oracle.com/javase/specs/jls/se25/html/jls-8.html#jls-8.9.2): điều kiện khi enum có phương thức trừu tượng.
- [Java Enum.getDeclaringClass](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Enum.html#getDeclaringClass()): phân biệt kiểu enum với lớp thực tế của hằng có thân riêng.
- [Java Math API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Math.html): các phép toán `Exact` và kiểm tra tràn số.
