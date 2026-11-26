# Từ JEP 447 trong Java 22 tới Flexible Constructor Bodies chính thức từ JDK 25

Flexible Constructor Bodies cho phép một constructor thực hiện một số câu lệnh trước lời gọi constructor tường minh `super(...)` hoặc `this(...)`. Nhờ đó, constructor có thể kiểm tra dữ liệu đầu vào, tính toán đối số hoặc gán trước một số trường của đối tượng trước khi constructor của lớp cha chạy.

Tính năng này xuất hiện lần đầu dưới dạng preview trong Java 22, được điều chỉnh qua Java 23 và Java 24, rồi trở thành tính năng chính thức trong Java 25. Vì vậy, khi học Java 22 ở thời điểm hiện tại, cần hiểu Java 22 là điểm khởi đầu của quá trình preview; cú pháp và quy tắc nên áp dụng trong dự án mới là phiên bản đã được chuẩn hóa từ Java 25.

## 1. Vấn đề của quy tắc constructor cũ

Trước Java 22, lời gọi constructor tường minh phải là câu lệnh đầu tiên trong constructor. Một constructor con vì thế không thể viết các bước kiểm tra hoặc xử lý dữ liệu thành câu lệnh riêng trước `super(...)`:

```java
class PositiveBigInteger extends java.math.BigInteger {
    PositiveBigInteger(long value) {
        if (value <= 0) { // Không hợp lệ theo quy tắc constructor cũ
            throw new IllegalArgumentException("value must be positive");
        }
        super(Long.toString(value));
    }
}
```

Trước khi có tính năng này, lập trình viên vẫn có thể xử lý dữ liệu trong biểu thức đối số của `super(...)`, chẳng hạn gọi một phương thức `static` để kiểm tra và chuyển đổi giá trị. Tuy nhiên, khi logic gồm nhiều bước, cách đó thường khiến biểu thức constructor khó đọc hoặc buộc phải tách logic sang phương thức phụ.

Flexible Constructor Bodies cho phép đặt các câu lệnh phù hợp trước lời gọi constructor tường minh. Việc kiểm tra có thể kết thúc bằng một ngoại lệ ngay tại constructor con; khi đó constructor lớp cha chưa được gọi.

## 2. Quá trình từ Java 22 đến Java 25

| Phiên bản | JEP | Trạng thái và thay đổi chính |
|---|---|---|
| Java 22 | [JEP 447 – Statements before `super(...)`](https://openjdk.org/jeps/447) | Preview lần đầu. Cho phép đặt câu lệnh trước lời gọi constructor tường minh nếu các câu lệnh đó không truy cập đối tượng đang được khởi tạo. |
| Java 23 | [JEP 482 – Flexible Constructor Bodies (Second Preview)](https://openjdk.org/jeps/482) | Preview lần hai, đổi tên thành Flexible Constructor Bodies và cho phép gán trường được khai báo trong chính lớp đang xây dựng trước lời gọi constructor. |
| Java 24 | [JEP 492 – Flexible Constructor Bodies (Third Preview)](https://openjdk.org/jeps/492) | Preview lần ba, tiếp tục hoàn thiện đặc tả trước khi chuẩn hóa. |
| Java 25 | [JEP 513 – Flexible Constructor Bodies](https://openjdk.org/jeps/513) | Tính năng chính thức, không còn là preview. |

Java 22 và Java 23/24 đều yêu cầu bật preview khi biên dịch và chạy chương trình. Từ Java 25, mã nguồn sử dụng Flexible Constructor Bodies không cần cờ `--enable-preview`.

## 3. Prologue, epilogue và early construction context

Constructor có lời gọi tường minh được chia thành hai phần:

- **Prologue**: các câu lệnh nằm trước `super(...)` hoặc `this(...)`.
- **Epilogue**: các câu lệnh nằm sau lời gọi đó.

Phần prologue cùng với các biểu thức đối số của lời gọi constructor tạo thành **early construction context** (ngữ cảnh khởi tạo sớm). Trong ngữ cảnh này, đối tượng hiện tại chưa hoàn tất việc khởi tạo lớp cha, vì vậy mã nguồn bị giới hạn khi truy cập đối tượng.

Các quy tắc quan trọng trong Java 25 trở đi:

1. Có thể dùng tham số constructor, biến cục bộ, biểu thức, lời gọi phương thức `static` và các câu lệnh kiểm tra dữ liệu, miễn là chúng không truy cập đối tượng đang được khởi tạo.
2. Không được đọc trường của đối tượng hiện tại, gọi phương thức instance của đối tượng đó, dùng đối tượng hiện tại làm đối số, hoặc truy cập thành viên của nó thông qua `this`/`super` trong early construction context.
3. Có một ngoại lệ có chủ đích: prologue được phép **gán giá trị cho trường được khai báo trong chính lớp đang xây dựng**. Có thể dùng phép gán đơn như `this.value = value`, nhưng không được đọc giá trị trường đó trong prologue.
4. Không được đặt câu lệnh `return` trong prologue.
5. Một constructor dùng `this(...)` để gọi constructor khác trong cùng lớp; dùng `super(...)` để gọi constructor của lớp cha trực tiếp. Một constructor không viết lời gọi tường minh sẽ nhận lời gọi `super()` ngầm định ở đầu; các câu lệnh thông thường của constructor đó vẫn chạy sau lời gọi ngầm định.

Điểm thứ ba là ngoại lệ quan trọng được bổ sung trong lần preview Java 23. Nó cho phép lớp con gán trước trường của mình để constructor lớp cha không quan sát thấy giá trị mặc định của trường đó khi gọi một phương thức bị override.

## 4. Kiểm tra dữ liệu trước khi gọi constructor lớp cha

Ví dụ sau dùng cú pháp đã được chuẩn hóa trong Java 25. Constructor kiểm tra giá trị trước khi chuyển nó thành chuỗi và truyền cho constructor của `BigInteger`:

```java
import java.math.BigInteger;

public class PositiveBigInteger extends BigInteger {
    public PositiveBigInteger(long value) {
        if (value <= 0) {
            throw new IllegalArgumentException("value must be positive");
        }

        super(Long.toString(value));
    }
}
```

Nếu `value` không dương, constructor ném `IllegalArgumentException` và lời gọi `BigInteger(...)` không diễn ra. Nếu dữ liệu hợp lệ, `super(...)` nhận chuỗi đã được tạo từ tham số.

Đây là trường hợp phù hợp với phần mở đầu của tính năng từ Java 22: prologue chỉ làm việc với tham số và dữ liệu độc lập với instance đang được xây dựng.

## 5. Gán trường trước khi constructor lớp cha chạy

Một tình huống khác liên quan đến việc gọi phương thức có thể bị override trong constructor lớp cha. Xét ví dụ:

```java
class Parent {
    Parent() {
        printValue();
    }

    void printValue() {
        System.out.println("Parent");
    }
}

class Child extends Parent {
    private final int value;

    Child(int value) {
        this.value = value;
        super();
    }

    @Override
    void printValue() {
        System.out.println(value);
    }
}

class ConstructorDemo {
    public static void main(String[] args) {
        new Child(42);
    }
}
```

Kết quả:

```text
42
```

Khi `Child` được tạo, prologue gán `42` cho trường `value` trước khi gọi `Parent()`. Constructor `Parent` gọi `printValue()`, và cơ chế dispatch vẫn gọi phiên bản override trong `Child`. Vì trường đã được gán, phương thức đọc được giá trị `42` thay vì giá trị mặc định `0`.

Nếu không có Flexible Constructor Bodies, lời gọi `super()` ngầm định chạy trước các câu lệnh trong constructor `Child`. Khi đó `Parent()` có thể gọi `Child.printValue()` trước khi `value` được gán và nhận kết quả `0`.

Lưu ý: trình tự khởi tạo trường và initializer của lớp vẫn có ý nghĩa. Initializer của instance trong lớp con chạy sau khi constructor lớp cha hoàn tất. Vì vậy, với trường không `final`, field initializer hoặc instance initializer có thể ghi đè giá trị đã gán trong prologue. Với trường `final`, compiler vẫn áp dụng quy tắc definite assignment và không cho phép gán trái quy định. Ví dụ trên dùng blank `final` field và chỉ gán nó một lần.

Việc gán trường sớm chỉ giải quyết trường hợp cụ thể cần thiết cho constructor lớp cha. Gọi phương thức có thể bị override từ constructor vẫn là thiết kế dễ gây lỗi: phương thức đó có thể đọc những trường khác của lớp con chưa được khởi tạo. Khi có thể, nên tránh gọi phương thức có thể override trong constructor của lớp cha.

## 6. Dùng prologue với `this(...)` trong record

Flexible Constructor Bodies cũng áp dụng cho lời gọi `this(...)`. Điều này hữu ích khi một constructor cần chuyển đổi hoặc xác thực dữ liệu rồi ủy quyền cho constructor khác trong cùng lớp.

Với record, constructor không canonical phải gọi constructor canonical bằng `this(...)`; nó không gọi `super(...)` trực tiếp. Các câu lệnh kiểm tra và tính toán có thể đứng trước lời gọi `this(...)`:

```java
record Dimensions(int width, int height) {
    Dimensions(String text) {
        String[] parts = text.split("x", -1);
        if (parts.length != 2) {
            throw new IllegalArgumentException("Expected width x height");
        }

        int width = Integer.parseInt(parts[0].trim());
        int height = Integer.parseInt(parts[1].trim());
        if (width <= 0 || height <= 0) {
            throw new IllegalArgumentException("Dimensions must be positive");
        }

        this(width, height);
    }
}
```

Constructor nhận chuỗi, tách hai kích thước, kiểm tra định dạng và giá trị, rồi chuyển quyền khởi tạo cho constructor canonical `Dimensions(int, int)`. Nếu dữ liệu không hợp lệ, ngoại lệ được ném trước khi constructor được ủy quyền chạy.

## 7. Biên dịch theo phiên bản Java

Với JDK 25 trở lên, hãy biên dịch mã nguồn như tính năng Java thông thường:

```bash
javac --release 25 ConstructorDemo.java
java ConstructorDemo
```

Nếu cần thử nghiệm đúng giai đoạn preview của Java 22, hãy dùng JDK 22 và bật preview ở cả bước biên dịch lẫn chạy:

```bash
javac --enable-preview --release 22 ConstructorDemo.java
java --enable-preview ConstructorDemo
```

Ở Java 22, chỉ dùng phần prologue không truy cập instance, chẳng hạn kiểm tra tham số trước `super(...)`. Cú pháp gán trường của lớp đang xây dựng trước lời gọi constructor được bổ sung ở JEP 482 trong Java 23. Với Java 23 và Java 24, thay `22` trong lệnh trên bằng phiên bản tương ứng và tiếp tục bật `--enable-preview`.

## 8. Khi nào nên sử dụng

Flexible Constructor Bodies phù hợp khi cần:

- Kiểm tra điều kiện đầu vào và dừng sớm trước khi constructor lớp cha thực hiện công việc.
- Chuẩn hóa hoặc tính toán đối số phức tạp trước khi gọi `super(...)` hay `this(...)`.
- Gán một số trường của lớp con trước khi constructor lớp cha chạy, đặc biệt khi lớp cha gọi phương thức có thể bị override.
- Kiểm tra và chuyển đổi dữ liệu trước khi một constructor record không canonical gọi `this(...)`.

Không nên xem prologue là nơi có thể sử dụng toàn bộ đối tượng. Early construction context vẫn giới hạn việc đọc trường và gọi phương thức instance. Hãy giữ phần này ngắn, tập trung vào tham số đầu vào, phép tính độc lập với instance và những phép gán trường thực sự cần thiết.

## 9. Kết luận

JEP 447 đưa khả năng viết câu lệnh trước lời gọi constructor vào Java 22 dưới dạng preview. JEP 482 mở rộng khả năng đó bằng cách cho phép gán trường của chính lớp đang xây dựng; JEP 492 tiếp tục preview trong Java 24; và JEP 513 chuẩn hóa tính năng trong Java 25.

Khi phát triển với Java hiện đại, hãy dùng quy tắc chính thức từ Java 25 trở đi. Những ví dụ chỉ kiểm tra tham số có thể chạy từ giai đoạn preview Java 22, còn ví dụ gán trường trước `super(...)` cần ít nhất phiên bản preview Java 23 hoặc phiên bản chính thức Java 25.

## Tài liệu tham khảo

- [JEP 447 – Statements before `super(...)` (Java 22 Preview)](https://openjdk.org/jeps/447)
- [JEP 482 – Flexible Constructor Bodies (Second Preview, Java 23)](https://openjdk.org/jeps/482)
- [JEP 492 – Flexible Constructor Bodies (Third Preview, Java 24)](https://openjdk.org/jeps/492)
- [JEP 513 – Flexible Constructor Bodies (Java 25)](https://openjdk.org/jeps/513)
- [Java Language Changes by Release – Java SE 25](https://docs.oracle.com/en/java/javase/25/language/java-language-changes-release.html)
- [Flexible Constructor Bodies – Java SE 26 Language Guide](https://docs.oracle.com/en/java/javase/26/language/flexible-constructor-bodies.html)
