# Name clash do cùng erasure và kế thừa nhiều tham số kiểu trong Java

## 1. Name clash là gì?

**Name clash** xuất hiện khi hai khai báo phương thức có cùng erasure nhưng không tạo thành một quan hệ override hợp lệ. Type argument giúp compiler kiểm tra kiểu ở mã nguồn, nhưng thường không tạo ra descriptor JVM riêng.

Ví dụ cố ý không biên dịch:

~~~java
import java.util.List;

class InvalidOverload {
    void handle(List<String> values) {}
    void handle(List<Integer> values) {}
}
~~~

Cả hai chữ ký đều xóa thành handle(List). Java không thể phân biệt chúng ở bytecode chỉ dựa vào String hay Integer bên trong List. Đây là lỗi thiết kế chữ ký; đổi tên biến tham số, đổi kiểu trả về hoặc thêm @SuppressWarnings không sửa được.

Overload thông thường với kiểu tham số thực sự khác nhau vẫn hợp lệ, ví dụ handle(String) và handle(Integer). Vấn đề là type argument bên trong cùng một generic type bị xóa.

## 2. Hai interface độc lập có thể xung đột

~~~java
interface TextReceiver<T> {
    void accept(T value);
}

interface NumberReceiver<T> {
    void accept(T value);
}

// Cố ý không biên dịch:
class ConflictingReceiver
        implements TextReceiver<String>, NumberReceiver<Integer> {
    public void accept(String value) {}
    public void accept(Integer value) {}
}
~~~

Sau khi áp dụng type argument, một hợp đồng yêu cầu accept(String), hợp đồng còn lại yêu cầu accept(Integer). Nhưng cả hai phương thức khai báo trong interface đều có erasure accept(Object). Compiler không thể tạo hai bridge accept(Object) khác nhau để đoán mỗi lời gọi cần đi vào implementation nào.

Nếu hai interface có cùng hợp đồng sau khi thay type argument, một implementation duy nhất có thể đáp ứng cả hai:

~~~java
interface First<T> {
    void accept(T value);
}

interface Second<T> {
    void accept(T value);
}

final class SharedReceiver implements First<String>, Second<String> {
    @Override
    public void accept(String value) {
        System.out.println("accepted=" + value);
    }
}
~~~

Ở đây cả hai interface đều yêu cầu accept(String), nên SharedReceiver chỉ cần một phương thức. Bridge nếu cần sẽ được compiler tạo theo quy tắc thông thường; xem bài về type erasure và bridge method để biết cách quan sát chúng.

## 3. Không thể kế thừa cùng interface generic với type argument khác nhau

Đây là lỗi riêng với cấu trúc kế thừa:

~~~java
interface Receiver<T> {
    void receive(T value);
}

// Cố ý không biên dịch:
class InvalidReceiver implements Receiver<String>, Receiver<Integer> {
}
~~~

Java không cho một kiểu kế thừa cùng generic interface với các type argument khác nhau. Đừng nhầm trường hợp này với hai interface độc lập ở phần trước: chúng có nguyên nhân liên quan đến erasure, nhưng quy tắc vi phạm khác nhau.

## 4. Generic method cũng có thể cùng erasure

~~~java
class MethodClash {
    <T> void store(T value) {}
    void store(Object value) {}
}
~~~

Đoạn này không biên dịch vì erasure của **&lt;T&gt; void store(T)** là store(Object), trùng với phương thức bình thường. Hãy giữ một chữ ký duy nhất nếu mục đích là nhận mọi đối tượng; nếu thao tác khác nhau về ý nghĩa, chọn tên hoặc tham số thực sự khác nhau.

Tương tự, không thể tạo hai overload chỉ bằng cách đổi type argument của List, Map hoặc một generic type khác. Wildcard cũng không tạo descriptor khác sau erasure.

## 5. Phân biệt name clash với override hợp lệ

Không phải mọi phương thức cùng erasure đều lỗi. Khi phương thức lớp con thật sự override hợp lệ phương thức generic được kế thừa, compiler có thể sinh bridge để giữ dispatch:

~~~java
class Box<T> {
    public T echo(T value) {
        return value;
    }
}

final class StringBox extends Box<String> {
    @Override
    public String echo(String value) {
        return "echo=" + value;
    }
}
~~~

StringBox.echo(String) override Box&lt;String&gt;.echo(T) sau khi T được thay bằng String. Bridge nhận Object có thể chuyển tiếp tới echo(String). Đây khác với hai overload độc lập handle(List&lt;String&gt;) và handle(List&lt;Integer&gt;), vì cặp overload đó không override nhau.

## 6. Bảng phân biệt

| Trường hợp | Kết quả | Lý do |
| --- | --- | --- |
| f(String) và f(Integer) | Thường hợp lệ | Descriptor tham số khác nhau |
| f(List&lt;String&gt;) và f(List&lt;Integer&gt;) | Không hợp lệ | Cùng erasure f(List) |
| Hai interface cùng yêu cầu accept(String) | Có thể hợp lệ | Một implementation đáp ứng cả hai |
| Hai interface yêu cầu accept(String) và accept(Integer), cả hai erasure accept(Object) | Không thể triển khai bằng hai overload đó | Không có một dispatch Object duy nhất phù hợp với cả hai |
| Kế thừa Receiver&lt;String&gt; và Receiver&lt;Integer&gt; | Không hợp lệ | Cùng interface generic bị kế thừa với type argument khác nhau |
| Override generic hợp lệ ở lớp con | Hợp lệ | Compiler có thể sinh bridge để giữ dispatch |

## 7. Cách xử lý khi gặp lỗi

1. Tìm tất cả phương thức cùng tên trong class, superclass và interface được kế thừa.
2. Tính erasure từng chữ ký: List&lt;String&gt; và List&lt;Integer&gt; đều thành List; T không bound thành Object; T extends Number thành Number.
3. Kiểm tra phương thức có thật sự override hay chỉ là overload. Dùng @Override để compiler xác nhận ý định override.
4. Kiểm tra type argument của các interface cha và xem có một implementation duy nhất đáp ứng được các hợp đồng không.
5. Chọn cách sửa theo ý nghĩa API: đổi tên phương thức nếu thao tác khác nhau; dùng một generic method nếu logic chung; thống nhất type argument khi các hợp đồng thực sự cùng kiểu; hoặc tách interface nếu chúng mô tả các hành vi không tương thích.

Không dùng raw type, unchecked cast hoặc @SuppressWarnings để né name clash. Các cách đó không tạo ra chữ ký JVM khác và có thể làm mất kiểm tra kiểu ở những vị trí khác. Khi lỗi liên quan đến bridge, hãy xem bài type erasure; khi lỗi liên quan đến raw type hoặc unchecked warning, hãy xem bài tương ứng trong chương.

## 8. Tự kiểm tra

1. Vì sao handle(List&lt;String&gt;) và handle(List&lt;Integer&gt;) không phải hai overload hợp lệ? Vì cả hai có erasure handle(List).
2. Vì sao hai interface có thể cùng được triển khai nếu đều yêu cầu accept(String)? Vì một phương thức duy nhất đáp ứng cả hai.
3. Vì sao không thể kế thừa Receiver&lt;String&gt; và Receiver&lt;Integer&gt;? Vì cùng generic interface không được kế thừa với type argument khác nhau.
4. Bridge method có phải cách để tự sửa overload trùng erasure không? Không; compiler chỉ sinh bridge khi cần duy trì một quan hệ override hợp lệ.
5. Nếu hai thao tác khác nhau, nên đổi tên hay ép kiểu? Hãy thiết kế chữ ký thể hiện đúng hợp đồng, không dùng cast để che xung đột.