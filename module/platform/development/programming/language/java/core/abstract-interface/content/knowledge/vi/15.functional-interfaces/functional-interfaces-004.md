# Loại trừ phương thức public của `Object` khi xác định hợp đồng hàm

Trong Java, một **functional interface** (interface hàm) cung cấp một hợp đồng gồm một phương thức trừu tượng để lambda expression hoặc method reference có thể biểu diễn hành vi của nó. Khi xác định hợp đồng đó, Java **không tính các khai báo abstract override-equivalent với phương thức public của `Object`** như `equals(Object)`, `hashCode()` và `toString()` vào phương thức chức năng.

Quy tắc này cho phép interface khai báo lại phương thức phổ biến của mọi đối tượng mà vẫn giữ được một phương thức chức năng duy nhất. Java xét chữ ký và quan hệ override-equivalent, không chỉ xét tên phương thức.

## 1. Hợp đồng hàm là gì?

Một functional interface có một phương thức chức năng (functional method, thường gọi là SAM — *Single Abstract Method*). Chữ ký của phương thức này xác định tham số, kiểu kết quả và các ngoại lệ mà lambda hoặc method reference phải đáp ứng.

```java
@FunctionalInterface
interface TextConsumer {
    void accept(String value);
}
```

`TextConsumer` có một phương thức abstract là `accept(String)`, vì vậy có thể làm kiểu đích cho lambda:

```java
TextConsumer printer = value -> System.out.println(value);
printer.accept("Java");
```

Khi biên dịch, Java kiểm tra kiểu đích và xác nhận lambda phù hợp với chữ ký của phương thức chức năng.

## 2. Vì sao phải loại trừ phương thức public của `Object`?

Mọi đối tượng Java đều có các phương thức công khai kế thừa từ `Object`. Những ví dụ thường gặp là:

- `boolean equals(Object other)` — so sánh tính bằng nhau.
- `int hashCode()` — cung cấp mã băm.
- `String toString()` — cung cấp biểu diễn dạng chuỗi.

Một interface có thể khai báo lại các phương thức này để thể hiện hợp đồng mà nó mong muốn. Tuy nhiên, các khai báo đó không tạo thêm phương thức chức năng, vì chúng tương ứng với phương thức public đã có trên mọi đối tượng Java.

```java
@FunctionalInterface
interface TextConsumer {
    void accept(String value);

    boolean equals(Object other);
    int hashCode();
    String toString();
}
```

Interface trên vẫn là functional interface. `accept(String)` là phương thức chức năng duy nhất; `equals(Object)`, `hashCode()` và `toString()` không được tính thành phương thức chức năng bổ sung. Lớp triển khai hoặc đối tượng lambda vẫn có các phương thức công khai tương ứng của `Object`.

Quy tắc dựa trên việc khai báo có *override-equivalent* với phương thức public của `Object` hay không. Ba phương thức trên là ví dụ phổ biến, không phải quy tắc chỉ dựa vào tên.

## 3. Ví dụ hoàn chỉnh có thể biên dịch và chạy

Lưu nội dung sau vào tệp `FunctionalObjectMethodsDemo.java`:

```java
@FunctionalInterface
interface TextConsumer {
    void accept(String value);

    // Các khai báo này không làm tăng số phương thức chức năng.
    boolean equals(Object other);
    int hashCode();
    String toString();
}

public class FunctionalObjectMethodsDemo {
    public static void main(String[] args) {
        TextConsumer printer =
                value -> System.out.println("Đã nhận: " + value);

        printer.accept("Java");
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```text
javac -encoding UTF-8 FunctionalObjectMethodsDemo.java
java FunctionalObjectMethodsDemo
```

Kết quả chuẩn:

```text
Đã nhận: Java
```

Lambda chỉ cung cấp hành vi cho `accept(String)`. Ba khai báo còn lại không yêu cầu lambda viết thêm phần thân phương thức. Chúng không thay đổi chữ ký mà lambda phải đáp ứng.

Có thể dùng method reference thay cho lambda trong cùng kiểu đích:

```java
TextConsumer printer = System.out::println;
printer.accept("Java");
```

Method reference cũng được kiểm tra theo phương thức chức năng `accept(String)`.

## 4. Chữ ký quan trọng hơn tên phương thức

Quy tắc loại trừ không áp dụng cho mọi phương thức chỉ vì nó có tên `equals`, `hashCode` hoặc `toString`. Chữ ký phải tương ứng theo quy tắc override-equivalent.

Ví dụ sau **không** phải functional interface:

```java
@FunctionalInterface
interface InvalidAction {
    void run();

    boolean equals(String other);
}
```

`equals(String)` không override-equivalent với `equals(Object)` của `Object` vì kiểu tham số khác nhau. Do đó, interface có hai phương thức abstract độc lập: `run()` và `equals(String)`. Chú thích `@FunctionalInterface` khiến trình biên dịch báo lỗi vì interface không đáp ứng điều kiện.

Tương tự, một phương thức có cùng tên nhưng thêm tham số, đổi kiểu tham số hoặc có chữ ký khác không tự động được loại trừ. Hãy xét toàn bộ chữ ký và quan hệ kế thừa thay vì chỉ tìm tên phương thức.

## 5. Interface chỉ khai báo lại một phương thức của `Object` thì sao?

```java
@FunctionalInterface
interface EqualityOnly {
    boolean equals(Object other);
}
```

Interface này không còn phương thức chức năng nào sau khi áp dụng quy tắc loại trừ. Vì vậy, nó không phải functional interface và trình biên dịch sẽ từ chối `@FunctionalInterface`. Không thể dùng nó làm kiểu đích cho lambda như thể nó có một SAM.

Điều này khác với `TextConsumer` ở ví dụ trước: `TextConsumer` còn có `accept(String)`, nên sau khi loại trừ các khai báo tương ứng với `Object` vẫn còn đúng một phương thức chức năng.

## 6. Phương thức kế thừa có cùng chữ ký

Khi interface kế thừa nhiều khai báo abstract có cùng chữ ký và kiểu trả về tương thích, các khai báo đó có thể quy về cùng một phương thức chức năng. Vì vậy, không nên chỉ đếm số dòng khai báo abstract trong mã nguồn.

```java
interface HasName {
    String value();
}

interface HasLabel {
    String value();
}

@FunctionalInterface
interface NamedValue extends HasName, HasLabel {
}
```

`NamedValue` vẫn có thể là functional interface vì hai khai báo `value()` tương thích và quy về cùng một chữ ký. Trường hợp này khác với việc loại trừ phương thức của `Object`: ở đây, các khai báo được hợp nhất do chữ ký và kế thừa; còn phương thức public của `Object` được bỏ qua khi xác định phương thức chức năng.

Nếu các khai báo kế thừa không tương thích, chẳng hạn kiểu trả về không thể dung hòa, bản thân interface có thể không biên dịch được. Quy tắc loại trừ phương thức của `Object` không giải quyết các xung đột kiểu như vậy.

## 7. Vai trò của `@FunctionalInterface`

`@FunctionalInterface` là chú thích kiểm tra tại thời điểm biên dịch. Nó yêu cầu trình biên dịch xác nhận interface đáp ứng quy tắc functional interface. Chú thích này không biến một interface bất kỳ thành functional interface và cũng không thay đổi cách xác định phương thức chức năng.

Nên dùng chú thích này khi chủ đích thiết kế interface cho lambda hoặc method reference. Nếu sau này thêm một phương thức abstract không tương thích với phương thức chức năng hiện có, lỗi biên dịch giúp phát hiện thay đổi làm hỏng hợp đồng.

Các phương thức `default`, `static` và `private` trong interface không phải phương thức abstract để tính vào SAM. Khi kiểm tra, hãy tập trung vào các khai báo abstract và phương thức abstract được kế thừa.

## 8. Cách xác định một interface có phải functional interface hay không

Có thể kiểm tra theo thứ tự sau:

1. Liệt kê các phương thức abstract được khai báo trực tiếp và kế thừa từ interface cha.
2. Loại trừ những khai báo override-equivalent với phương thức public của `Object`, chẳng hạn `equals(Object)`, `hashCode()` và `toString()`.
3. Xem các khai báo còn lại có cùng chữ ký và kiểu trả về tương thích để quy về một phương thức chức năng hay không.
4. Kiểm tra rằng kết quả có đúng một phương thức chức năng.
5. Thêm `@FunctionalInterface` để trình biên dịch xác nhận ý định này.

Khi lambda báo lỗi không phải functional interface, hãy kiểm tra chữ ký thực tế của các phương thức abstract, kể cả phương thức đến từ interface cha. Đừng giả định rằng các phương thức cùng tên luôn được gộp, hoặc rằng khai báo lại `equals(Object)` sẽ tạo thêm một SAM.

## 9. Những nhầm lẫn thường gặp

- **“Interface có nhiều khai báo abstract thì chắc chắn không phải functional interface.”** Không đúng. Khai báo override-equivalent với phương thức public của `Object` bị loại trừ; các khai báo kế thừa có chữ ký tương thích cũng có thể quy về cùng một phương thức chức năng.
- **“Cứ có tên `equals` là được loại trừ.”** Không đúng. `equals(String)` khác chữ ký với `equals(Object)` và vẫn có thể là một phương thức abstract độc lập.
- **“Thêm `@FunctionalInterface` sẽ làm interface hợp lệ.”** Không đúng. Chú thích chỉ yêu cầu kiểm tra và báo lỗi nếu điều kiện không được đáp ứng.
- **“Lambda phải cung cấp phần thân cho `equals`, `hashCode` và `toString` nếu interface khai báo chúng.”** Không đúng. Các khai báo tương ứng với phương thức public của `Object` không được tính vào phương thức chức năng.
- **“Phải có đúng một dòng khai báo abstract trong tệp.”** Không đúng. Điều cần xác định là phương thức chức năng sau khi xét chữ ký, kế thừa và quy tắc loại trừ.

## Kết luận

Khi xác định hợp đồng hàm của một interface, hãy tìm phương thức abstract còn lại sau khi áp dụng quy tắc chữ ký và kế thừa. Các khai báo override-equivalent với phương thức public của `Object` không làm tăng số phương thức chức năng. Nhờ đó, interface có thể khai báo lại `equals(Object)`, `hashCode()` hoặc `toString()` mà vẫn dùng được với lambda, miễn là nó có đúng một phương thức chức năng thực sự.