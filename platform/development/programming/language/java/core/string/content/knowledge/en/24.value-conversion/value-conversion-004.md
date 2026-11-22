# toString() của String và của đối tượng khác trong Java

Trong Java, **toString()** là phương thức dùng để lấy cách biểu diễn một đối tượng dưới dạng **String**. Mọi lớp đều thừa hưởng phương thức này từ **java.lang.Object**, nhưng từng kiểu có thể định nghĩa lại cách biểu diễn của mình. Điểm đặc biệt là **String đã là chuỗi văn bản**, vì vậy **String.toString() trả về chính đối tượng String hiện tại**, trong khi nhiều đối tượng khác phải tạo hoặc trả về một biểu diễn chuỗi phù hợp.

Hiểu rõ sự khác nhau giúp đọc kết quả println, nối chuỗi, log, debug; tránh hiểu nhầm dấu @ trong biểu diễn mặc định; xử lý null đúng cách; và nhận ra tại sao toString() của mảng không in các phần tử như mong đợi.

## 1. toString() được khai báo ở đâu và có ý nghĩa gì?

Lớp **Object** định nghĩa phương thức public String toString(). Vì mọi lớp Java đều kế thừa Object (trực tiếp hoặc gián tiếp), các lớp như String, Integer, ArrayList, các lớp nghiệp vụ tự viết và cả đối tượng mảng đều có thể được chuyển sang cách biểu diễn dạng String thông qua toString().

Cách hoạt động cụ thể phụ thuộc vào lớp thực tế của đối tượng:

- **Object không ghi đè toString():** phương thức mặc định trả về chuỗi gồm tên lớp, dấu @ và giá trị hash code ở dạng thập lục phân.
- **Lớp ghi đè toString():** phương thức có thể trả về tên, thuộc tính, trạng thái hay thông tin dễ đọc, tùy định nghĩa của lớp.
- **String:** ghi đè toString() để **return this**, tức trả lại chính tham chiếu đến chuỗi ban đầu; không tạo thêm chuỗi nội dung tương đương.
- **Kiểu nguyên thủy** như int, long, boolean không phải Object và **không có phương thức thể hiện intVariable.toString()**; muốn tạo chuỗi có thể dùng String.valueOf(value) hoặc Integer.toString(value) cho kiểu phù hợp.

toString() được dùng để trình bày hoặc quan sát đối tượng. Nó **không phải phương thức tự động tuần tự hóa** dữ liệu thành JSON, XML hoặc dạng dữ liệu đủ để tái tạo đối tượng. Một kết quả toString() cũng không bảo đảm tính duy nhất, tính bất biến về định dạng, hoặc tính phù hợp để gửi cho máy khác phân tích.

## 2. String.toString(): trả về chính String đó

Trong Java, String là lớp final, không thể có lớp con sửa hành vi toString(). Phương thức **String.toString() trả về this**; vì vậy nếu biến s đang tham chiếu một String khác null, biểu thức s.toString() có cùng tham chiếu và cùng nội dung với s.

Ví dụ tệp **StringToStringDemo.java** (chạy với Java 17+):

~~~java
public class StringToStringDemo {
    public static void main(String[] args) {
        String text = new String("Java");
        String converted = text.toString();

        System.out.println("content: " + converted);
        System.out.println("same reference: " + (text == converted));
        System.out.println("same content: " + text.equals(converted));

        Object objectRef = text;
        System.out.println("via Object: " + objectRef.toString());
        System.out.println("same via Object: " + (objectRef.toString() == text));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 StringToStringDemo.java
java StringToStringDemo
~~~

Kết quả:

~~~text
content: Java
same reference: true
same content: true
via Object: Java
same via Object: true
~~~

**Vì sao đều đúng?**

1. **new String("Java")** cố ý tạo một đối tượng String mới để ví dụ không dựa vào cơ chế String pool.
2. **text.toString()** trả lại chính text; vì vậy toán tử **==** cho kết quả true giữa hai tham chiếu.
3. **equals()** so sánh nội dung chuỗi và cũng cho true, nhưng đây là phép kiểm tra khác với ==.
4. Dù biến **objectRef** có kiểu khai báo là Object, đối tượng thực tế vẫn là String. Java dùng **dynamic dispatch** để gọi String.toString() đã ghi đè, nên nhận lại đúng chuỗi "Java".

Không cần gọi toString() mỗi lần đã có String. Ví dụ, viết **String result = text;** thường diễn đạt ý định rõ hơn **String result = text.toString();**. Việc gọi toString() trên String không làm sạch, chuyển đổi mã hóa, chuẩn hóa Unicode, bỏ khoảng trắng hay tạo bản sao.

**Chú ý null:** kết luận trả về this chỉ áp dụng khi tham chiếu String **khác null**. Nếu **String s = null**, gọi **s.toString()** sẽ ném NullPointerException trước khi có một chuỗi nào được trả về.

## 3. Object.toString() mặc định: tên lớp, @ và hash

Nếu một lớp không ghi đè toString(), nó sử dụng cách triển khai kế thừa của **Object**. Mẫu kết quả về mặt khái niệm:

~~~text
ten.goi.Lop@maHashHe16
~~~

Theo hợp đồng của Object.toString(), giá trị được tạo như khi ghép:

~~~java
getClass().getName() + "@" + Integer.toHexString(hashCode())
~~~

Chẳng hạn, một phiên chạy có thể hiển thị **java.lang.Object@5acf9800**. Phần sau dấu @ phụ thuộc hashCode của đối tượng, nên **không được cố định chuỗi này trong kỳ vọng output**.

Tệp **ObjectToStringDemo.java**:

~~~java
public class ObjectToStringDemo {
    public static void main(String[] args) {
        Object obj = new Object();
        String result = obj.toString();

        System.out.println(result.startsWith("java.lang.Object@"));
        System.out.println(result.equals(
                obj.getClass().getName() + "@"
                        + Integer.toHexString(obj.hashCode())
        ));
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 ObjectToStringDemo.java
java ObjectToStringDemo
~~~

Output chính xác:

~~~text
true
true
~~~

Ở đây tránh in trực tiếp mã hash thay đổi giữa các đối tượng/lần chạy; thay vào đó kiểm tra hai thuộc tính bảo đảm bởi triển khai mặc định.

**Hash code không phải địa chỉ bộ nhớ đáng tin cậy.** Dấu @ và đoạn hex của Object.toString() không chứng minh đối tượng đang ở vị trí nào trong RAM; giá trị hashCode không được thiết kế làm ID nghiệp vụ duy nhất. Hai đối tượng khác nhau cũng có thể có cùng hash code.

Ngoài ra, một lớp có thể ghi đè **hashCode()** nhưng không ghi đè **toString()**; khi đó Object.toString() sẽ sử dụng kết quả hashCode của lớp đó, nên không nên suy luận rằng phần hex nhất thiết là mã định danh mặc định của JVM.

## 4. Lớp tự viết: ghi đè toString() để nội dung dễ đọc

Phần lớn các lớp nghiệp vụ cần cách hiển thị có ý nghĩa hơn tên lớp và mã hash. Ta có thể ghi đè toString() bằng **@Override** và trả về String mô tả những thuộc tính hữu ích.

Tạo tệp **OrderToStringDemo.java**:

~~~java
public class OrderToStringDemo {
    static final class Order {
        private final int id;
        private final String status;

        Order(int id, String status) {
            this.id = id;
            this.status = status;
        }

        @Override
        public String toString() {
            return "Order{id=" + id + ", status='" + status + "'}";
        }
    }

    public static void main(String[] args) {
        Order order = new Order(42, "PAID");

        System.out.println(order.toString());
        System.out.println(order);
        System.out.println("Current: " + order);
    }
}
~~~

~~~bash
javac -encoding UTF-8 OrderToStringDemo.java
java OrderToStringDemo
~~~

~~~text
Order{id=42, status='PAID'}
Order{id=42, status='PAID'}
Current: Order{id=42, status='PAID'}
~~~

Trong ví dụ:

- **@Override** giúp trình biên dịch kiểm tra chữ ký phương thức đang ghi đè một phương thức của lớp cha.
- Phương thức ghi đè là **public String toString()**, không nhận tham số và trả về String.
- **System.out.println(order)** có thể sử dụng cách biểu diễn chuỗi của order; phần nối chuỗi trong **"Current: " + order** cũng sử dụng cách biểu diễn này.
- toString() ở đây **tạo ra cách biểu diễn văn bản** của Order. Đừng dựa vào việc nó luôn tạo đối tượng String mới hay luôn dùng đúng format này khi lớp được sửa ở phiên bản khác.

Nếu lớp chứa thông tin nhạy cảm như mật khẩu, token, khóa API, số định danh riêng tư, **không đưa những giá trị đó vào toString()** vì phương thức dễ được gọi ngầm khi ghi log hoặc xử lý lỗi. Với đối tượng phức tạp, nên ưu tiên nội dung ngắn, dễ hiểu và tránh gọi dịch vụ ngoài hay tính toán tốn kém bên trong toString().

### Phương thức được chọn theo lớp thực tế

Nếu một biến khai báo kiểu Object đang trỏ tới Order, gọi biến.toString() vẫn chạy **Order.toString()**. Cơ chế này gọi là **đa hình**, không phụ thuộc việc biến được khai báo kiểu Object hay Order. Java không cần ép kiểu về Order để tìm phương thức ghi đè phù hợp.

**Lưu ý với record:** trong Java 17, một record chưa tự định nghĩa toString() được compiler cung cấp cách biểu diễn dựa trên tên record và các thành phần của nó. Ví dụ **record Point(int x, int y)** có thể in **Point[x=2, y=3]**. Điều này tiện khi debug, nhưng vẫn không biến toString() thành định dạng trao đổi dữ liệu ổn định.

## 5. String.valueOf(Object), Objects.toString và xử lý null

Dễ nhầm **x.toString()** với **String.valueOf(x)**. Cả hai có thể tạo cách biểu diễn chuỗi, nhưng khác nhau đáng kể khi tham chiếu **null**:

| Cách viết | x khác null | x là null |
| --- | --- | --- |
| x.toString() | Gọi toString() của lớp thực tế. | **NullPointerException**. |
| String.valueOf((Object) x) | Gọi x.toString(). | Trả về chuỗi **"null"**. |
| Objects.toString(x) | Gọi x.toString(). | Trả về chuỗi **"null"**. |
| Objects.toString(x, "không có") | Gọi x.toString(). | Trả về chuỗi dự phòng **"không có"**. |

Lý do viết **(Object)** trong bảng: String.valueOf có nhiều overload như nhận Object, char[] và kiểu nguyên thủy; ép kiểu Object làm rõ ta đang nói đến **String.valueOf(Object)**.

Tệp **NullToStringDemo.java**:

~~~java
import java.util.Objects;

public class NullToStringDemo {
    public static void main(String[] args) {
        Object present = Integer.valueOf(25);
        Object missing = null;

        System.out.println(String.valueOf(present));
        System.out.println(String.valueOf(missing));
        System.out.println(Objects.toString(missing, "(empty)"));

        try {
            System.out.println(missing.toString());
        } catch (NullPointerException ex) {
            System.out.println("toString on null: NullPointerException");
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 NullToStringDemo.java
java NullToStringDemo
~~~

~~~text
25
null
(empty)
toString on null: NullPointerException
~~~

Đây là output gồm **bốn dòng**. Dòng thứ hai có nội dung văn bản "null", không có nghĩa biến missing đã biến thành một String.

**Cẩn thận với lời gọi String.valueOf(null) không ép kiểu:** do Java chọn overload phù hợp nhất, biểu thức với literal null có thể chọn overload **char[]** thay vì Object, dẫn đến lỗi khi chạy. Khi muốn đúng hành vi tạo chuỗi "null", hãy chỉ rõ **String.valueOf((Object) null)** hoặc sử dụng **Objects.toString(null)**.

String.valueOf còn có overload riêng cho boolean, char, int, long, float, double...; với kiểu nguyên thủy, nó tạo cách biểu diễn của giá trị nguyên thủy mà không cần tạo trước một wrapper object một cách tường minh. Với đối tượng, hành vi phụ thuộc vào toString() của lớp thực tế.

## 6. toString() của mảng khác với in nội dung phần tử

Trong Java, **mảng là đối tượng**, nhưng các lớp mảng không cung cấp kiểu toString liệt kê phần tử như người mới học thường kỳ vọng. Gọi **numbers.toString()** với một int[] dùng cách biểu diễn mặc định, thường bắt đầu bằng **[I@** (tên lớp mảng int ở dạng JVM) và thêm hash code.

Muốn quan sát nội dung mảng, dùng các tiện ích trong **java.util.Arrays**:

- **Arrays.toString(array)** cho mảng một chiều.
- **Arrays.deepToString(objectArray)** cho mảng nhiều chiều hoặc chứa các mảng con, chẳng hạn int[][].
- Với mảng **char[]**, overload **String.valueOf(char[])** đặc biệt tạo String từ các ký tự; nó khác String.valueOf((Object) charArray).

Ví dụ tệp **ArrayToStringDemo.java**:

~~~java
import java.util.Arrays;

public class ArrayToStringDemo {
    public static void main(String[] args) {
        int[] numbers = {2, 4, 6};
        int[][] matrix = {{1, 2}, {3, 4}};
        char[] letters = {'J', 'a', 'v', 'a'};

        System.out.println(numbers.toString().startsWith("[I@"));
        System.out.println(Arrays.toString(numbers));
        System.out.println(Arrays.deepToString(matrix));
        System.out.println(String.valueOf(letters));
        System.out.println(String.valueOf((Object) letters)
                .startsWith("[C@"));
    }
}
~~~

~~~bash
javac -encoding UTF-8 ArrayToStringDemo.java
java ArrayToStringDemo
~~~

~~~text
true
[2, 4, 6]
[[1, 2], [3, 4]]
Java
true
~~~

Dòng đầu xác nhận kiểu tên mảng int mà không đoán mã hash. Dòng cuối chứng minh sự khác nhau giữa hai overload của String.valueOf: truyền trực tiếp char[] tạo String từ ký tự, còn ép sang Object buộc gọi toString() của đối tượng mảng.

Nếu có **Object[]** chứa mảng con, Arrays.toString có thể vẫn cho cách biểu diễn dạng tên lớp và hash của mảng con; Arrays.deepToString mới hiển thị các phần tử lồng nhau phù hợp. Với mảng tự tham chiếu, deepToString có cách xử lý chống đệ quy vô hạn theo hợp đồng API.

## 7. toString() của đối tượng có thể thay đổi trạng thái khác gì String?

Đối tượng có thể **mutable**, ví dụ StringBuilder. Gọi StringBuilder.toString() tạo một String biểu diễn **nội dung tại thời điểm gọi**; chuỗi kết quả là bất biến, nên những lần sửa StringBuilder sau đó không thay đổi snapshot đã lấy.

Tệp **BuilderToStringDemo.java**:

~~~java
public class BuilderToStringDemo {
    public static void main(String[] args) {
        StringBuilder builder = new StringBuilder("v1");
        String snapshot = builder.toString();

        builder.append("-updated");

        System.out.println("builder: " + builder);
        System.out.println("snapshot: " + snapshot);
        System.out.println("snapshot type: " + snapshot.getClass().getSimpleName());
    }
}
~~~

~~~bash
javac -encoding UTF-8 BuilderToStringDemo.java
java BuilderToStringDemo
~~~

~~~text
builder: v1-updated
snapshot: v1
snapshot type: String
~~~

**So sánh hai trường hợp:** String.toString() trả lại **cùng đối tượng String**, vì String đã bất biến và chính là dạng chuỗi mong muốn. StringBuilder.toString() trả về **String chứa nội dung hiện tại** của bộ dựng chuỗi; snapshot không tiếp tục cập nhật khi builder thay đổi. Không nên viết logic dựa vào việc đối tượng String do StringBuilder tạo ra có tham chiếu mới trong mọi hoàn cảnh; điều quan trọng theo API là **giá trị chuỗi được bảo toàn sau khi builder thay đổi**.

Nhiều lớp thư viện khác cũng cung cấp toString() dễ đọc, ví dụ các lớp số như Integer và các collection. Tuy vậy, định dạng chính xác phụ thuộc từng lớp; một collection có thể sử dụng toString() của các phần tử, nên phần tử hiển thị thế nào vẫn do lớp của chúng quyết định.

## 8. toString() được gọi ngầm ở đâu?

Java và các thư viện thường chuyển đối tượng sang văn bản mà ta không gọi trực tiếp phương thức toString():

- **System.out.println(object)**: các overload in ra có cơ chế chuyển đối tượng thành văn bản. Nếu object là null, println(Object) in **null** thay vì gọi phương thức trên tham chiếu null.
- **"value = " + object**: toán tử nối chuỗi chuyển toán hạng đối tượng sang cách biểu diễn String; null trở thành văn bản **"null"**.
- **String.valueOf(object)** và **Objects.toString(object)**: gọi toString() nếu đối tượng không null.
- **StringBuilder.append(Object)**: thường dùng String.valueOf(Object) rồi nối văn bản vào builder.
- Một số cách định dạng hay logger có thể sử dụng toString(), nhưng cơ chế riêng của từng thư viện có thể khác; không khẳng định mọi logger luôn gọi toString() theo cùng cách.

Do đó, override toString() hợp lý giúp debug, nhưng cũng có thể khiến việc in đối tượng **tốn kém**, phát sinh ngoại lệ hoặc vô tình lộ dữ liệu. Tránh đưa mật khẩu, access token, dữ liệu cá nhân và khối văn bản quá dài vào giá trị toString() mặc định của mô hình nghiệp vụ.

Nếu cần **format dành cho người dùng**, **dữ liệu lưu trữ**, hoặc **dữ liệu truyền qua API**, nên viết phương thức/serializer dành riêng cho mục đích đó. toString() chủ yếu là cách biểu diễn văn bản của đối tượng, không bảo đảm hợp đồng serialize ổn định.

## 9. Những nhầm lẫn thường gặp

| Nhầm lẫn | Giải thích đúng |
| --- | --- |
| String.toString() tạo một bản sao String mới. | String.toString() trả về **this**, tức cùng đối tượng. |
| Mọi đối tượng dùng Object.toString() mặc định. | Lớp có thể ghi đè toString(); Java gọi theo **kiểu đối tượng thực tế**. |
| Phần hex trong ClassName@hex là địa chỉ bộ nhớ. | Nó là biểu diễn hex của **hashCode()**, không phải địa chỉ RAM được bảo đảm. |
| Gọi toString() trên tham chiếu null trả về "null". | Gọi phương thức trên null gây **NullPointerException**; muốn null-safe hãy dùng String.valueOf((Object) x) hoặc Objects.toString(x). |
| String.valueOf(null) luôn tương đương String.valueOf((Object) null). | Có overload char[]; cần ép kiểu để tránh chọn sai overload khi truyền literal null. |
| array.toString() in tất cả phần tử. | Mảng thường dùng biểu diễn kiểu và hash; sử dụng Arrays.toString/deepToString. |
| Nối đối tượng vào String chỉ gọi Object.toString(). | Phương thức được chọn theo **lớp thực tế**, có thể là override của lớp con. |
| toString() luôn phải trả về tên lớp và các trường. | Đó là **thiết kế** của lớp; API chỉ yêu cầu trả về một String, nội dung có thể khác. |
| toString() là định dạng chuẩn cho JSON hay lưu trữ. | Không có bảo đảm đó; dùng serializer hoặc định dạng được định nghĩa riêng. |
| Override toString() có thể in cả secret cho dễ debug. | Lời gọi ngầm rất phổ biến; phải tránh để lộ thông tin nhạy cảm trong log. |

## 10. Checklist khi thiết kế và sử dụng toString()

1. **Đã có String?** Có thể sử dụng trực tiếp, vì gọi toString() không thay đổi tham chiếu hay nội dung.
2. **Đối tượng tùy biến cần dễ đọc?** Cân nhắc ghi đè public String toString(), thêm @Override và chọn các trường ngắn gọn, không nhạy cảm.
3. **Biến có thể null?** Dùng String.valueOf((Object) value), Objects.toString(value) hoặc Objects.toString(value, fallback) khi phù hợp.
4. **Đang xử lý array?** Xem Arrays.toString, Arrays.deepToString hoặc String.valueOf(char[]) tùy loại mảng.
5. **Đang chuyển StringBuilder hay đối tượng mutable?** Xem String trả về là biểu diễn/snapshot tại thời điểm gọi.
6. **Cần dữ liệu để so sánh, định danh hay lưu trữ?** Không mặc định toString() là hợp đồng dữ liệu; dùng equals/hashCode, khóa định danh hoặc serializer riêng tùy mục tiêu.

Quy tắc nhớ nhanh: **String.toString() giữ nguyên chính String; Object.toString() mặc định mô tả lớp và hash; các lớp khác có thể ghi đè để tạo biểu diễn có ý nghĩa.** Khi Java cần hiển thị đối tượng, hành vi phụ thuộc lớp thực tế và chính sách xử lý null của API gọi đến.