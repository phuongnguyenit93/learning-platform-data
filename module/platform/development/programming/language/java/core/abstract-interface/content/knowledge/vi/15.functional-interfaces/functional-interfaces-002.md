# `@FunctionalInterface` và kiểm tra tại thời điểm biên dịch

`@FunctionalInterface` là annotation dùng để thể hiện rằng một interface được thiết kế làm **functional interface** và yêu cầu compiler xác minh điều đó. Nếu khai báo không đáp ứng quy tắc của Java, compiler báo lỗi ngay tại interface, giúp phát hiện thay đổi làm hỏng hợp đồng lambda trước khi chương trình chạy.

## 1. Annotation xác nhận điều gì?

```java
@FunctionalInterface
interface TextOperation {
    String apply(String input);
}

public class FunctionalInterfaceAnnotationDemo {
    public static void main(String[] args) {
        TextOperation upper = text -> text.toUpperCase(java.util.Locale.ROOT);
        System.out.println(upper.apply("java"));
    }
}
```

Lưu thành `FunctionalInterfaceAnnotationDemo.java`, rồi chạy:

```bash
javac FunctionalInterfaceAnnotationDemo.java
java FunctionalInterfaceAnnotationDemo
```

Kết quả:

```text
JAVA
```

Compiler chấp nhận khai báo vì `TextOperation` có một phương thức abstract chức năng là `apply(String)`. Lambda được gán cho kiểu đó nên phải đáp ứng chữ ký nhận `String` và trả về `String`.

Annotation **không bắt buộc** để dùng lambda. Nếu bỏ `@FunctionalInterface`, `TextOperation` vẫn là functional interface và ví dụ vẫn biên dịch. Lợi ích của annotation là biến ý định thiết kế thành một điều kiện compiler có thể kiểm tra.

## 2. Khi thêm phương thức abstract thứ hai

Đoạn sau cố ý không biên dịch:

```java
@FunctionalInterface
interface InvalidOperation {
    String apply(String input);
    String label(String input);
}
```

Hai phương thức có hai mục đích độc lập, nên interface không có một hợp đồng hàm duy nhất. Compiler từ chối annotation. Nếu chỉ bỏ annotation, khai báo có thể tồn tại như interface thông thường, nhưng vẫn không thể dùng một lambda đơn giản để triển khai cả `apply` lẫn `label`.

Khi API cần thêm hành vi, hãy chọn theo ý nghĩa thiết kế:

- Giữ phương thức abstract mới nếu mọi implementation thực sự phải cung cấp hành vi đó; khi ấy interface không còn phù hợp làm kiểu đích lambda.
- Dùng `default` chỉ khi có một cách triển khai mặc định đúng và có ý nghĩa cho mọi implementation.
- Dùng `static` cho tiện ích thuộc về interface, hoặc tách trách nhiệm thành interface riêng nếu hai hành vi không nên bị buộc chung.

Đừng biến một phương thức thành default chỉ để giữ annotation nếu phần thân mặc định không đúng về nghiệp vụ.

## 3. Interface không có phương thức abstract cũng không hợp lệ

Ví dụ này cũng không biên dịch:

```java
@FunctionalInterface
interface NoOperation {
    default void run() {
        System.out.println("running");
    }
}
```

`run()` đã có thân, vì vậy không còn phương thức abstract nào để lambda thực hiện. `@FunctionalInterface` không có nghĩa “interface có thể được gọi bằng lambda”; nó khẳng định interface phải thỏa quy tắc functional interface của Java.

## 4. Compiler áp dụng quy tắc Java đầy đủ

Việc xác định hợp đồng chức năng bao gồm các phương thức abstract được kế thừa, chữ ký tương đương và kiểu trả về. Những khai báo tương ứng với public instance methods của `Object`, cũng như các phương thức `default`, `static` và `private`, được xử lý theo quy tắc ngôn ngữ riêng. Vì vậy, không nên chỉ đếm số dòng khai báo trong interface hiện tại.

Các bài về kế thừa interface, phương thức của `Object` và các loại method trình bày chi tiết các trường hợp đó. Ở đây, điều cần kiểm tra là compiler có chấp nhận toàn bộ khai báo như một functional interface hay không.

## 5. Annotation không kiểm thử logic của chương trình

`@FunctionalInterface` kiểm tra **hình dạng của hợp đồng**, không chứng minh nội dung phương thức là đúng. Compiler vẫn có thể chấp nhận một lambda trả kết quả sai về nghiệp vụ, xử lý null không phù hợp hoặc ném unchecked exception khi chạy.

Ví dụ, cả hai lambda dưới đây đều có thể phù hợp với `TextOperation`, nhưng chỉ một lambda có thể đáp ứng yêu cầu thực tế của ứng dụng:

```java
TextOperation upper = text -> text.toUpperCase(java.util.Locale.ROOT);
TextOperation constant = text -> "JAVA";
```

Annotation cũng không sinh implementation, không tự xử lý ngoại lệ và không bảo đảm hiệu năng. Hãy dùng kiểm thử và tài liệu hợp đồng để kiểm tra hành vi; dùng annotation để giữ đúng cấu trúc functional interface.

## 6. Cách đọc lỗi compiler

Thông báo cụ thể thay đổi theo JDK, nhưng các tình huống thường gặp gồm:

| Tình huống | Nguyên nhân cần kiểm tra |
| --- | --- |
| Annotation bị từ chối vì có nhiều phương thức abstract | Có một phương thức abstract độc lập được thêm vào hoặc được kế thừa |
| Annotation bị từ chối vì không có functional method | Không còn phương thức abstract chức năng sau khi áp dụng quy tắc Java |
| Annotation được đặt trên class thay vì interface | `@FunctionalInterface` chỉ dành cho khai báo interface |
| Lambda dùng interface nhưng không biên dịch | Kiểm tra kiểu đích và chữ ký; bỏ annotation không biến interface nhiều phương thức thành SAM |

Khi sửa lỗi, hãy xem lại hợp đồng và các phương thức được kế thừa trước. Xóa annotation có thể che mất ý định ban đầu mà không khôi phục khả năng sử dụng lambda.

## 7. Checklist khi định nghĩa API

1. Interface có thực sự được thiết kế để nhận lambda hoặc method reference không?
2. Có một phương thức abstract chức năng hợp lệ theo quy tắc Java không?
3. Phương thức bổ sung có thực sự cần là abstract, hay một default/static method có ngữ nghĩa đúng hơn?
4. Tham số, kết quả và checked exception có diễn đạt rõ hợp đồng cần thiết không?
5. Có cần kiểm thử riêng cho logic, dữ liệu biên và lỗi runtime không?

**Ghi nhớ:** `@FunctionalInterface` là một xác nhận được compiler kiểm tra, không phải cơ chế tự tạo hành vi. Hãy dùng nó để bảo vệ ý định thiết kế interface, đồng thời kiểm tra logic và hợp đồng runtime bằng các phương tiện phù hợp.