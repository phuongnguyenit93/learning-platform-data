# Cú pháp `permits` và trường hợp suy ra danh sách cho phép

Trong Java, `sealed` giới hạn những kiểu nào được phép kế thừa trực tiếp một lớp hoặc triển khai trực tiếp một interface. Mệnh đề `permits` liệt kê các kiểu con trực tiếp được phép. Nếu các kiểu con đều được khai báo trong cùng một compilation unit, Java có thể tự suy ra danh sách này khi bỏ `permits`.

Các quy tắc này là kiểm tra ở thời điểm biên dịch. Chúng giúp mô hình hóa một hệ phân cấp có tập nhánh được kiểm soát, chẳng hạn các loại biểu thức, kết quả hoặc sự kiện mà chương trình biết trước.

## 1. Danh sách `permits` tường minh

Cú pháp cơ bản:

```java
sealed interface Shape permits Circle, Rectangle {
    double area();
}

record Circle(double radius) implements Shape {
    @Override
    public double area() {
        return Math.PI * radius * radius;
    }
}

final class Rectangle implements Shape {
    private final double width;
    private final double height;

    Rectangle(double width, double height) {
        this.width = width;
        this.height = height;
    }

    @Override
    public double area() {
        return width * height;
    }
}
```

Ở đây, `Circle` và `Rectangle` là hai kiểu triển khai trực tiếp của `Shape`, nên cả hai xuất hiện trong `permits`. `Circle` là record và do đó mặc định là `final`; `Rectangle` khai báo `final` tường minh.

Danh sách có thể gồm nhiều tên, phân tách bằng dấu phẩy. Các kiểu được liệt kê phải thực sự là kiểu con trực tiếp của kiểu sealed. Có thể đặt chúng trong các tệp nguồn khác nhau nếu tuân thủ quy tắc package/module ở phần dưới.

## 2. Khi nào Java tự suy ra danh sách?

Nếu bỏ mệnh đề `permits`, trình biên dịch tìm các khai báo kiểu con trực tiếp nằm trong **cùng compilation unit** với kiểu sealed. Compilation unit thường tương ứng với một tệp nguồn Java. Ví dụ:

```java
sealed interface Command {
    String describe();
}

record Start(String name) implements Command {
    @Override
    public String describe() {
        return "start " + name;
    }
}

record Stop() implements Command {
    @Override
    public String describe() {
        return "stop";
    }
}
```

Danh sách được suy ra ở đây là `Start` và `Stop`, vì cả hai record đều trực tiếp triển khai `Command` và được khai báo trong cùng compilation unit. Record tự động là `final`, nên không cần ghi thêm từ khóa đó.

Việc suy ra có phạm vi rõ ràng: Java không tìm kiếm tùy ý tất cả tệp trong package. Nếu một kiểu con nằm ở tệp nguồn khác, hãy khai báo danh sách `permits` tường minh. Khi bỏ `permits` mà không có kiểu con trực tiếp nào được khai báo trong cùng compilation unit, khai báo sealed không hợp lệ.

## 3. Ví dụ hoàn chỉnh chạy được với Java 17+

Lưu nội dung sau trong tệp `PermitsDemo.java`. Ví dụ minh họa cả danh sách tường minh (`Shape`) và danh sách được suy ra (`Command`).

```java
public class PermitsDemo {
    public static void main(String[] args) {
        Shape circle = new Circle(2.0);
        Shape rectangle = new Rectangle(3.0, 4.0);
        System.out.printf("circle area = %.2f%n", circle.area());
        System.out.printf("rectangle area = %.2f%n", rectangle.area());

        Command command = new Start("worker");
        System.out.println(command.describe());
    }
}

sealed interface Shape permits Circle, Rectangle {
    double area();
}

record Circle(double radius) implements Shape {
    Circle {
        if (radius < 0) {
            throw new IllegalArgumentException("radius must be non-negative");
        }
    }

    @Override
    public double area() {
        return Math.PI * radius * radius;
    }
}

final class Rectangle implements Shape {
    private final double width;
    private final double height;

    Rectangle(double width, double height) {
        if (width < 0 || height < 0) {
            throw new IllegalArgumentException("dimensions must be non-negative");
        }
        this.width = width;
        this.height = height;
    }

    @Override
    public double area() {
        return width * height;
    }
}

sealed interface Command {
    String describe();
}

record Start(String name) implements Command {
    @Override
    public String describe() {
        return "start " + name;
    }
}

record Stop() implements Command {
    @Override
    public String describe() {
        return "stop";
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 PermitsDemo.java
java PermitsDemo
```

Kết quả chính xác:

```text
circle area = 12.57
rectangle area = 12.00
start worker
```

Lưu ý: `--release 17` yêu cầu trình biên dịch tạo mã tương thích Java 17. Cần cài JDK có hỗ trợ tùy chọn này.

## 4. Quy tắc bắt buộc

- **Chỉ liệt kê kiểu con trực tiếp.** Nếu `C` triển khai `B`, còn `B` triển khai `A`, thì `A` chỉ cho phép `B`; `C` thuộc nhánh của `B`, không được liệt kê trực tiếp trong `permits` của `A`.
- **Mọi kiểu con trực tiếp đều phải được cho phép.** Với danh sách tường minh, kiểu con trực tiếp bị bỏ sót sẽ gây lỗi biên dịch.
- **Kiểu con trực tiếp phải đóng hoặc khai báo cách mở rộng.** Nó phải là `final`, `sealed` hoặc `non-sealed`. Record mặc định là `final`, nên không cần ghi `final record`.
- **Quy tắc package/module phải được đáp ứng.** Trong unnamed module, kiểu sealed và các kiểu con được phép phải ở cùng package. Trong named module, chúng phải thuộc cùng module; chúng có thể nằm ở các package khác nhau trong module đó.
- **Suy ra danh sách chỉ dựa vào cùng compilation unit.** Các kiểu con ở tệp khác không tự được thêm vào danh sách khi bỏ `permits`.
- **`permits` chỉ dùng trên khai báo `sealed`.** Nó không phải danh sách mọi lớp có thể xuất hiện trong chương trình và cũng không thay thế các quy tắc kế thừa thông thường.

Nếu một kiểu con trực tiếp là `sealed`, kiểu đó có thể tiếp tục định nghĩa danh sách con riêng. Nếu là `non-sealed`, nhánh đó mở cho các kiểu khác kế thừa tiếp. Nếu là `final`, nhánh dừng tại kiểu đó.

## 5. Phân biệt kiểu con trực tiếp và gián tiếp

Trong ví dụ dưới đây, `Expr` cho phép `Literal` và `Binary`. `Add` và `Multiply` là các kiểu con trực tiếp của `Binary`, vì vậy chúng nằm trong danh sách của `Binary`, không phải của `Expr`.

```java
sealed interface Expr permits Literal, Binary {}

record Literal(int value) implements Expr {}

sealed interface Binary extends Expr permits Add, Multiply {}

record Add(Expr left, Expr right) implements Binary {}

record Multiply(Expr left, Expr right) implements Binary {}
```

Mỗi record là một kiểu con cuối cùng. Cấu trúc này thể hiện rõ hai tầng: `Expr` quyết định các nhánh cấp một, còn `Binary` quyết định các phép toán nhị phân được phép.

## 6. Kiểu sealed có tham số kiểu

Với kiểu generic, các tên trong `permits` là tên kiểu, không ghi đối số kiểu tại danh sách:

```java
sealed interface Result<T> permits Success, Failure {}

record Success<T>(T value) implements Result<T> {}

record Failure<T>(String message) implements Result<T> {}
```

`Success<T>` và `Failure<T>` trực tiếp triển khai `Result<T>`; các record là `final` ngầm định. Quy tắc suy ra danh sách cũng áp dụng cho kiểu generic nếu các kiểu con trực tiếp được khai báo trong cùng compilation unit.

## 7. Lỗi thường gặp và cách tìm nguyên nhân

| Tình huống | Nguyên nhân và cách sửa |
|---|---|
| Bỏ `permits`, nhưng kiểu con nằm ở tệp khác | Thêm danh sách `permits` tường minh và liệt kê kiểu con trực tiếp. |
| Có kiểu con trực tiếp không nằm trong danh sách | Bổ sung kiểu đó vào `permits`, hoặc điều chỉnh quan hệ kế thừa cho đúng thiết kế. |
| Liệt kê một kiểu không trực tiếp kế thừa/triển khai kiểu sealed | Sửa danh sách để chỉ chứa kiểu con trực tiếp. |
| Kiểu con trực tiếp không phải `final`, `sealed` hoặc `non-sealed` | Chọn một trong các trạng thái này; record đã là `final` ngầm định. |
| Các kiểu ở sai package hoặc module | Đưa chúng về cùng package trong unnamed module hoặc cùng module trong named module. |
| Bỏ `permits` nhưng không có kiểu con trực tiếp trong cùng tệp | Khai báo ít nhất một kiểu con trực tiếp trong compilation unit hoặc dùng `permits` tường minh. |

Khi đọc thông báo lỗi, hãy kiểm tra theo thứ tự: kiểu nào khai báo `sealed`, quan hệ `extends`/ `implements` nào là trực tiếp, danh sách `permits` đang khai báo gì, rồi mới kiểm tra package/module và từ khóa của kiểu con.

## 8. Chọn danh sách tường minh hay suy ra?

Dùng danh sách tường minh khi các kiểu con được đặt ở nhiều tệp, khi muốn thấy hợp đồng của hệ phân cấp ngay tại khai báo, hoặc khi danh sách cho phép cần được rà soát rõ ràng trong code review.

Có thể bỏ `permits` khi toàn bộ kiểu con trực tiếp được gom trong cùng compilation unit và việc suy ra giúp mã gọn hơn. Khi đó, thêm một kiểu con trực tiếp mới vào cùng tệp cũng làm thay đổi danh sách được suy ra, vì vậy hãy cân nhắc liệu sự thay đổi ngầm này có phù hợp với mục đích của hệ phân cấp hay không.

Trước khi hoàn tất một khai báo, kiểm tra nhanh:

1. Kiểu cha đã được khai báo `sealed` chưa?
2. Danh sách chỉ gồm các kiểu con trực tiếp chưa?
3. Mọi kiểu con trực tiếp đã được cho phép chưa?
4. Nếu bỏ `permits`, tất cả kiểu con trực tiếp có nằm trong cùng compilation unit không?
5. Mỗi kiểu con trực tiếp đã là `final`, `sealed`, `non-sealed` hoặc record chưa?
6. Quy tắc package/module có đúng không?

## Tài liệu tham khảo

- [Java Language Specification 17: Sealed Classes](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.1.6)
- [Java Language Specification 17: Sealed Interfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.1.4)
