# Phép gán tham chiếu không tạo đối tượng mới trong Java

## 1. Bản chất của phép gán tham chiếu

Trong Java, một biến kiểu tham chiếu (ví dụ `Person`, `String`, mảng hay `List`) giữ **giá trị tham chiếu đến một đối tượng**, hoặc giá trị `null`. Với phép gán `b = a`, Java chép **giá trị tham chiếu** của `a` vào biến `b`. Bản thân phép gán không tạo thêm đối tượng và không sao chép các trường của đối tượng.

~~~java
Box first = new Box("A"); // new Box(...) tạo đối tượng.
Box alias = first;        // Chép tham chiếu, không tạo Box thứ hai.
~~~

Sau đó `first` và `alias` là **hai biến riêng biệt cùng tham chiếu một Box**:

~~~text
first ──┐
        ├──► Box { value = "A" }
alias ──┘
~~~

Khai báo biến tham chiếu không đồng nghĩa với tạo một đối tượng của lớp được tham chiếu. Trong `Box first = new Box("A")`, **biểu thức `new`** làm phát sinh đối tượng, còn phép gán chỉ đặt tham chiếu vào `first`. Câu “phép gán không tạo đối tượng mới” nói về thao tác sao chép tham chiếu; nó không phủ nhận rằng **biểu thức bên phải** có thể tự tạo đối tượng.

## 2. Ví dụ đầy đủ: alias, thay đổi trạng thái và gán lại

Tạo tệp `ReferenceAssignmentDemo.java`:

~~~java
public class ReferenceAssignmentDemo {
    static final class Box {
        String value;

        Box(String value) {
            this.value = value;
        }
    }

    public static void main(String[] args) {
        Box first = new Box("A");
        Box alias = first;

        System.out.println("same after assignment: " + (first == alias));

        alias.value = "B";
        System.out.println("first.value: " + first.value);

        alias = new Box("C");
        System.out.println("same after rebinding: " + (first == alias));
        System.out.println("first.value: " + first.value);
        System.out.println("alias.value: " + alias.value);
    }
}
~~~

Biên dịch và chạy bằng Java 17+:

~~~bash
javac -encoding UTF-8 ReferenceAssignmentDemo.java
java ReferenceAssignmentDemo
~~~

Stdout:

~~~text
same after assignment: true
first.value: B
same after rebinding: false
first.value: B
alias.value: C
~~~

Đọc từng bước:

1. `new Box("A")` tạo một đối tượng Box, `first` nhận tham chiếu đến đối tượng đó.
2. `Box alias = first` chép tham chiếu vào `alias`, nên `first == alias` là `true`.
3. `alias.value = "B"` **sửa trạng thái đối tượng dùng chung**. Qua `first.value` ta cũng thấy `"B"`.
4. `alias = new Box("C")` tạo Box thứ hai rồi gán tham chiếu của Box mới cho **riêng biến** `alias`.
5. `first` vẫn trỏ đến Box có `value = "B"`; `alias` trỏ đến Box có `value = "C"`. Hai biến không còn cùng tham chiếu, nên `==` trả `false`.

Phải phân biệt hai thao tác:

- **Sửa đối tượng:** `alias.value = "B"` tác động đến đối tượng mà các alias cùng trỏ tới.
- **Gán lại biến:** `alias = other`, `alias = null` hoặc `alias = new Box(...)` đổi giá trị tham chiếu trong riêng `alias`. Lệnh này không tự sửa đối tượng cũ và không đổi giá trị của `first`.

## 3. Khác biệt với gán kiểu nguyên thủy

Với kiểu nguyên thủy, giá trị được sao chép là số, ký tự hoặc giá trị boolean trực tiếp:

~~~java
int a = 10;
int b = a;
b = 20;
System.out.println(a); // 10
System.out.println(b); // 20
~~~

Với kiểu tham chiếu, phép gán vẫn sao chép **giá trị**, nhưng giá trị ấy chỉ đến đối tượng. Các biến tham chiếu độc lập khi bị **gán lại**, dù chúng có thể **chia sẻ đối tượng**. Vì vậy không nên gọi `Box b = a` là “sao chép Box”.

## 4. Danh tính đối tượng: == khác equals

`==` trên hai tham chiếu tương thích kiểm tra chúng có cùng giá trị tham chiếu hay không: cùng đối tượng, hoặc cả hai cùng `null`. `equals(Object)` là phương thức để lớp định nghĩa ý nghĩa “bằng nhau” theo quy ước; nhiều lớp, ví dụ `String`, ghi đè phương thức này để so nội dung. Nếu một lớp không ghi đè, nó kế thừa hành vi so sánh danh tính từ `Object`.

~~~java
String x = new String("java");
String y = new String("java");
System.out.println(x == y);      // false
System.out.println(x.equals(y)); // true
~~~

Hai biểu thức `new String("java")` tạo hai đối tượng String khác nhau, nhưng nội dung hai chuỗi bằng nhau. Chỉ dùng `new String(...)` ở đây để minh họa danh tính; với chuỗi thông thường nên dùng literal như `"java"`.

Đừng dựa vào `System.identityHashCode(obj)` để chứng minh danh tính: mã băm danh tính không được bảo đảm duy nhất cho mỗi đối tượng. Để nhận biết hai tham chiếu có trỏ đến **chính cùng đối tượng** hay không, dùng `==`.

## 5. Truyền đối tượng vào phương thức: Java vẫn truyền theo giá trị

Java luôn **truyền tham số theo giá trị**. Khi đối số là biến tham chiếu, tham số phương thức nhận **bản sao của giá trị tham chiếu**. Bởi vậy phương thức có thể sửa một đối tượng dùng chung, nhưng phép gán lại tham số không thể làm biến ở phía gọi tự đổi tham chiếu.

Tạo tệp `ParameterPassingDemo.java`:

~~~java
public class ParameterPassingDemo {
    static class Box {
        String value;

        Box(String value) {
            this.value = value;
        }
    }

    static void reassign(Box parameter) {
        parameter = new Box("mới");
    }

    static void mutate(Box parameter) {
        parameter.value = "đã đổi";
    }

    public static void main(String[] args) {
        Box original = new Box("ban đầu");

        reassign(original);
        System.out.println("after reassign: " + original.value);

        mutate(original);
        System.out.println("after mutate: " + original.value);
    }
}
~~~

~~~bash
javac -encoding UTF-8 ParameterPassingDemo.java
java ParameterPassingDemo
~~~

Stdout:

~~~text
after reassign: ban đầu
after mutate: đã đổi
~~~

Trong `reassign`, biến cục bộ `parameter` nhận tham chiếu đến đối tượng mới, nhưng `original` ở phía gọi không bị gán lại. Trong `mutate`, tham số và `original` cùng tham chiếu Box ban đầu nên thay đổi `value` được quan sát ở bên ngoài. Nếu muốn người gọi chuyển sang đối tượng khác, hãy **trả về tham chiếu** và gán rõ ràng ở phía gọi, chẳng hạn `original = createBox();`.

## 6. final, null và khả năng truy cập đối tượng

### Biến final không đồng nghĩa đối tượng bất biến

~~~java
final Box selected = new Box("A");
selected.value = "B";      // Được phép nếu đối tượng có trường có thể sửa.
// selected = new Box("C"); // Không biên dịch nếu bỏ //: selected là final.
~~~

`final` cấm gán lại **biến**, không tự làm đối tượng trở thành immutable. Đối tượng bất biến là kết quả của thiết kế lớp, ví dụ chỉ công khai các thao tác không sửa trạng thái.

### null không tạo hoặc hủy đối tượng

~~~java
Box first = new Box("A");
Box alias = first;
first = null;
// alias vẫn tham chiếu đến Box("A").
~~~

`Box b = null` không tạo Box nào. `first = null` chỉ đổi tham chiếu trong `first`; Box cũ vẫn có thể được truy cập qua `alias`. Khi một đối tượng không còn có thể truy cập qua các đường tham chiếu mạnh thích hợp, nó có thể đủ điều kiện để được garbage collector thu hồi; Java không bảo đảm thu hồi ngay tại thời điểm gán biến.

Cố truy cập trường hoặc gọi phương thức thực thể qua tham chiếu `null` sẽ gây `NullPointerException`. Việc so sánh `b == null` hoặc gán `b = null` tự nó vẫn hợp lệ.

## 7. Mảng, collection và sao chép thực sự

Mảng cũng là đối tượng, nên phép gán mảng tạo alias:

~~~java
int[] numbers = {1, 2};
int[] same = numbers;
same[0] = 99;
System.out.println(numbers[0]);      // 99
System.out.println(numbers == same); // true
~~~

Với collection cũng vậy: `List<String> b = a;` không tạo danh sách mới; `a` và `b` trỏ vào cùng List, nên các thao tác thêm/xóa phần tử qua một biến sẽ được biến kia quan sát.

Nếu muốn tạo **đối tượng chứa độc lập**, phải yêu cầu tạo hoặc sao chép rõ ràng:

~~~java
int[] copy = numbers.clone();
System.out.println(numbers == copy); // false
~~~

`clone()` của mảng tạo mảng mới. Với **mảng chứa tham chiếu**, đây là **sao chép nông**: mảng mới vẫn giữ tham chiếu tới các đối tượng phần tử cũ. Tương tự, `new ArrayList<>(oldList)` tạo List mới nhưng các phần tử kiểu tham chiếu của nó không tự được sao chép sâu. Nếu cần mọi phần tử tùy biến độc lập, phải xây dựng quy tắc sao chép từng phần tử (copy constructor hoặc phương thức tạo bản sao phù hợp).

### Trường hợp String

~~~java
String first = "Java";
String alias = first;
alias = alias + " 17";
System.out.println(first); // Java
~~~

Hai biến ban đầu cùng tham chiếu một String. Tuy nhiên `String` là **immutable**: thao tác nối xây dựng giá trị chuỗi mới và gán kết quả cho `alias`, không sửa chuỗi mà `first` đang tham chiếu. Vì vậy không thể dùng ví dụ chuỗi để kết luận rằng các đối tượng mutable cũng không chia sẻ thay đổi trạng thái.

## 8. Hiểu lầm phổ biến

| Hiểu lầm | Điều thực sự diễn ra |
| --- | --- |
| `Box b = a` tạo một bản sao Box. | Sai. `b` và `a` tham chiếu cùng Box. |
| `b.field = x` giống `b = other`. | Lệnh đầu sửa đối tượng; lệnh sau gán lại biến `b`. |
| Java truyền tham chiếu “theo tham chiếu”, vì vậy phương thức có thể gán lại biến của người gọi. | Sai. Tham số nhận bản sao của giá trị tham chiếu. |
| Hai đối tượng có dữ liệu giống nhau thì `==` là `true`. | Sai. `==` so sánh danh tính; `equals` có thể so nội dung nếu lớp định nghĩa. |
| Biến `final` làm đối tượng bất biến. | Sai đối với các đối tượng mutable. |
| Gán `null` hoặc gán sang đối tượng mới xóa ngay đối tượng cũ. | Sai. Khả năng truy cập và thời điểm GC là vấn đề khác. |
| Sao chép List/mảng là sao chép sâu mọi phần tử. | Sai với cách sao chép nông thông thường. |

## 9. Kỹ thuật dự đoán kết quả khi đọc code

Vẽ mỗi **đối tượng** bằng một hộp, mỗi **biến tham chiếu** bằng một mũi tên. Khi gặp `new` (hoặc thao tác thực sự tạo đối tượng), thêm hộp tương ứng. Khi gặp `b = a`, chỉ cập nhật mũi tên của `b` để nó giống `a`. Khi gặp `b.field = value`, cập nhật trường trong hộp mà `b` đang trỏ tới. Khi gặp `b = null`, xóa mũi tên của riêng `b`. Khi gặp `b = new Box(...)`, vẽ hộp mới và chuyển riêng mũi tên của `b` sang đó.

Cách làm này tách bạch **danh tính đối tượng**, **trạng thái được chia sẻ** và **giá trị tham chiếu của từng biến**. Nó đủ để suy luận về aliasing mà không cần biết địa chỉ bộ nhớ thực tế hay cách JVM bố trí đối tượng.