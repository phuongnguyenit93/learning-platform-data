# @SafeVarargs trên phương thức private của đối tượng

## 1. Mục đích của @SafeVarargs

Java hỗ trợ tham số biến số lượng bằng cú pháp varargs (`...`). Ví dụ:

```java
void print(String... values) {
    // values được sử dụng như một mảng String.
}
```

Khi gọi `print("Java", "Generics")`, trình biên dịch tạo hoặc truyền một mảng để phương thức nhận các phần tử. Với kiểu tham số thông thường như `String...`, kiểu phần tử có thể kiểm tra được tại runtime. Với kiểu generic không reifiable như `List<String>...`, thông tin `String` bị xóa do type erasure; kiểu mảng tại runtime chỉ còn là `List[]`.

Điều này tạo ra nguy cơ *heap pollution*: một tham chiếu được khai báo với kiểu tham số hóa, chẳng hạn `List<String>`, lại trỏ đến đối tượng có phần tử không phù hợp với `String`. Trình biên dịch cảnh báo khi một phương thức khai báo varargs với kiểu phần tử không reifiable vì phương thức có thể xử lý mảng theo cách không an toàn.

`@SafeVarargs` là lời cam kết của người viết rằng phần thân phương thức hoặc constructor không thực hiện thao tác có thể gây heap pollution thông qua tham số varargs. Annotation giúp biểu đạt cam kết đó và loại bỏ các cảnh báo unchecked liên quan đến việc sử dụng varargs khi cam kết là đúng.

## 2. Vì sao Java 9 cho phép dùng trên private instance method?

Từ Java 9, `@SafeVarargs` được phép đặt trên:

- Constructor có tham số varargs.
- Phương thức `static` có tham số varargs.
- Phương thức instance `final` có tham số varargs.
- Phương thức instance `private` có tham số varargs.

Trước Java 9, phương thức instance private chưa thuộc nhóm phương thức được phép dùng annotation này. Java 9 mở rộng quy tắc vì phương thức private không thể bị lớp con override. Vì vậy, người viết có thể kiểm soát toàn bộ phần triển khai của helper method và chịu trách nhiệm trực tiếp về cách nó sử dụng mảng varargs.

Một phương thức instance public hoặc protected muốn dùng `@SafeVarargs` phải là `final`; phương thức instance không private và không final không được phép dùng annotation này. Annotation chỉ áp dụng cho constructor hoặc phương thức thực sự khai báo tham số varargs. Đặt nó trên phương thức không có `...` là lỗi biên dịch.

Điểm cần nhớ là quyền sử dụng annotation không tự làm phương thức an toàn. Java 9 chỉ cho phép người viết đưa ra cam kết này trên private instance method.

## 3. Ví dụ private instance method hợp lệ và an toàn

Ví dụ sau khai báo `printGroups` là một phương thức instance `private`, không cần `static` hoặc `final`. Phương thức nhận nhiều danh sách chuỗi, chỉ đọc từng danh sách và in nội dung. Nó không sửa, lưu trữ hay trả lại mảng varargs.

```java
import java.util.List;

public class SafeVarargsPrivateDemo {
    @SafeVarargs
    private void printGroups(List<String>... groups) {
        for (List<String> group : groups) {
            System.out.println(String.join(", ", group));
        }
    }

    public static void main(String[] args) {
        SafeVarargsPrivateDemo demo = new SafeVarargsPrivateDemo();
        demo.printGroups(
                List.of("Java", "Generics"),
                List.of("Varargs")
        );
    }
}
```

Lưu mã nguồn trong tệp `SafeVarargsPrivateDemo.java`. Biên dịch và chạy với Java 17 trở lên:

```bash
javac --release 17 -Xlint:all SafeVarargsPrivateDemo.java
java SafeVarargsPrivateDemo
```

Kết quả:

```text
Java, Generics
Varargs
```

Lệnh biên dịch trên đã được kiểm tra với tùy chọn `--release 17 -Xlint:all`; ví dụ biên dịch không phát cảnh báo. Phương thức chỉ duyệt mảng và đọc các giá trị theo kiểu `List<String>`, do đó không làm thay đổi thành phần mảng hoặc để mảng thoát ra ngoài.

## 4. Điều kiện để lời cam kết thực sự đúng

Trước khi thêm `@SafeVarargs`, hãy xem xét cách phương thức sử dụng chính mảng varargs. Với tham số generic không reifiable, một cách triển khai thường an toàn là đọc từng phần tử và gọi các thao tác phù hợp với kiểu phần tử mà không làm lộ mảng.

Các hành vi cần tránh gồm:

- Gán mảng varargs cho `Object[]` rồi ghi vào đó một giá trị có kiểu generic không tương thích.
- Trả trực tiếp mảng varargs cho bên gọi.
- Lưu mảng vào field, collection hoặc một đối tượng có vòng đời dài hơn để mã khác có thể sửa nó.
- Chuyển mảng cho phương thức khác có thể thay thế các phần tử bằng giá trị không đúng kiểu.
- Ép kiểu mảng sang kiểu rộng hơn để ghi dữ liệu không an toàn.

Cần phân biệt việc đọc phần tử với việc thao tác trên mảng. Ví dụ, duyệt `for (List<String> group : groups)` và xử lý từng `group` là phù hợp khi phương thức không làm rò rỉ hoặc thay đổi mảng. Ngược lại, việc sửa mảng có thể phá vỡ giả định kiểu mà mã gọi đang dựa vào.

## 5. Ví dụ cam kết sai có thể gây heap pollution

Đoạn dưới đây cố ý không an toàn. Phương thức trả lại chính mảng varargs, khiến mảng có thể bị mã bên ngoài thay đổi:

```java
@SafeVarargs
private List<String>[] expose(List<String>... values) {
    return values; // Không an toàn: làm lộ mảng varargs.
}
```

Nếu bên gọi truyền vào một mảng `List<String>[]` đã tồn tại, phương thức trả về cùng đối tượng mảng. Vì kiểu phần tử thực tế của mảng đã bị xóa thành `List`, mã bên ngoài có thể ghi một `List<Integer>` thông qua góc nhìn `Object[]`:

```java
@SuppressWarnings("unchecked")
List<String>[] values =
        (List<String>[]) new List<?>[] { List.of("safe") };

List<String>[] leaked = demo.expose(values);
Object[] writable = leaked;
writable[0] = List.of(42);

String text = leaked[0].get(0); // ClassCastException
```

Khi đọc phần tử như `String`, JVM phải ép kiểu giá trị lấy ra từ danh sách. Giá trị thực tế là `Integer`, nên thao tác ném `ClassCastException`. Đây là hậu quả của heap pollution.

Khi biên dịch một phương thức cố ý làm lộ mảng như trên với `-Xlint:all`, javac có thể phát cảnh báo `[varargs]` ngay tại thao tác trả về tham số. Cảnh báo này cho biết phần thân có thao tác nguy hiểm dù phương thức đã được gắn `@SafeVarargs`. Hãy sửa thiết kế để mảng không bị lộ; không dùng annotation để che một triển khai sai.

## 6. @SafeVarargs khác gì @SuppressWarnings?

`@SafeVarargs` thể hiện một cam kết cụ thể về tính an toàn của tham số varargs. Nó cho compiler biết người viết đã kiểm tra phần thân và bảo đảm không có thao tác gây heap pollution qua tham số đó.

`@SuppressWarnings("unchecked")` chỉ yêu cầu compiler ẩn một nhóm cảnh báo unchecked trong phạm vi được gắn annotation. Nó không tự mô tả hợp đồng an toàn của varargs và cũng không biến một thao tác không an toàn thành an toàn.

Vì vậy:

- Dùng `@SafeVarargs` khi phương thức có varargs, kiểu phần tử không reifiable và người viết có thể chứng minh phần thân an toàn.
- Không thêm annotation chỉ để làm sạch cửa sổ cảnh báo.
- Nếu compiler vẫn báo `[varargs]` tại một thao tác trong phần thân, hãy xem lại thao tác đó và loại bỏ nguy cơ thay vì bỏ qua cảnh báo.

## 7. Checklist khi review private @SafeVarargs method

1. Phương thức có khai báo tham số varargs bằng `...` hay không?
2. Mã được biên dịch với Java 9 trở lên để private instance method được phép dùng annotation hay không?
3. Phương thức thực sự là `private`, `static` hoặc `final` theo điều kiện áp dụng hay không?
4. Kiểu phần tử có phải kiểu không reifiable, khiến cảnh báo varargs có liên quan hay không?
5. Phần thân chỉ đọc và xử lý phần tử, hay có sửa, ép kiểu, lưu trữ hoặc trả lại mảng?
6. Mảng có thể thoát ra ngoài hoặc được chuyển cho mã có thể sửa phần tử hay không?
7. Khi chạy `javac -Xlint:all`, còn cảnh báo `[varargs]` nào cần xử lý hay không?

`@SafeVarargs` trên private instance method là khả năng được Java 9 bổ sung để người viết helper method có thể khai báo rõ cam kết an toàn cho varargs generic. Hãy dùng nó sau khi đã kiểm tra cách mảng được đọc, sửa và chia sẻ; annotation ghi nhận trách nhiệm của người viết chứ không thay thế việc bảo đảm an toàn kiểu.