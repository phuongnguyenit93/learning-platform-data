# So sánh anonymous class với lambda về this và phạm vi tên

Anonymous class (lớp ẩn danh) và lambda đều có thể cung cấp hành vi cho một functional interface, chẳng hạn Runnable. Khác biệt quan trọng nằm ở ngữ cảnh mà biểu thức tạo ra: anonymous class tạo một đối tượng thuộc lớp mới, còn lambda giữ ngữ cảnh từ vị trí khai báo. Điều này quyết định ý nghĩa của this, cách tra cứu tên và những thành viên có thể khai báo.

## 1. Bảng so sánh nhanh

| Khía cạnh | Anonymous class | Lambda |
|---|---|---|
| Ý nghĩa của this | this trỏ đến đối tượng anonymous class | this giữ nghĩa từ ngữ cảnh bao ngoài |
| Truy cập đối tượng bao ngoài | Dùng Outer.this khi cần chỉ rõ instance bên ngoài | this đã trỏ đến instance bao ngoài; có thể dùng Outer.this để viết rõ ý định |
| Thành viên riêng | Có thể khai báo field, method và initializer trong thân lớp | Không thể khai báo field hay method riêng trong thân lambda |
| Phạm vi tên | Có phạm vi thành viên của lớp; thành viên riêng có thể che khuất tên từ bên ngoài | Dùng phạm vi từ vựng của vị trí khai báo và phạm vi tham số/local của lambda |
| Biến local từ method bao ngoài | Chỉ được capture biến final hoặc effectively final | Cũng chỉ được capture biến final hoặc effectively final |
| Kiểu đích | Có thể tạo lớp con của class hoặc triển khai interface | Cần kiểu đích là functional interface, tức có một phương thức abstract cần triển khai |
| Khi phù hợp | Cần trạng thái riêng, nhiều method hoặc cần this của đối tượng callback | Cần truyền một hành vi ngắn gọn, tập trung vào một phương thức |

## 2. this trong anonymous class

Anonymous class có một đối tượng riêng. Vì vậy, bên trong method của nó, this là đối tượng anonymous class đang thực thi. Nếu lớp đó được khai báo trong một instance method của lớp ThisAndScopeDemo, biểu thức ThisAndScopeDemo.this trỏ đến instance bao ngoài.

Khi tên field trùng nhau, hãy dùng tiền tố thể hiện rõ đối tượng cần truy cập:

- this.name: field name của anonymous class nếu lớp đó khai báo field này.
- ThisAndScopeDemo.this.name: field name của instance ThisAndScopeDemo bao ngoài.
- Một lời gọi method không có tiền tố bên trong anonymous class được tra cứu trong ngữ cảnh lớp đó trước; dùng ThisAndScopeDemo.this.someMethod() khi cần gọi rõ method của instance bên ngoài.

Anonymous class cũng có thể khai báo method, field và initializer. Nó không khai báo constructor có tên riêng, vì bản thân lớp không có tên; có thể dùng initializer nếu cần khởi tạo trạng thái riêng.

## 3. this trong lambda

Lambda không tạo binding this mới. Nếu lambda được viết trong instance method của ThisAndScopeDemo, this bên trong lambda vẫn là instance ThisAndScopeDemo. Do đó, this.name đọc field của lớp bao ngoài.

Lambda cũng không tạo ngữ cảnh lớp mới cho super. Các tham chiếu this và super được hiểu theo ngữ cảnh từ vựng nơi lambda được khai báo. Nếu lambda nằm trong static method, không có instance bao ngoài để this trỏ đến, nên viết this tại đó vẫn là lỗi biên dịch.

Đừng nhầm this với chính đối tượng lambda. Lambda vẫn là một object có thể được gán cho biến, truyền làm đối số hoặc so sánh tham chiếu. Tuy nhiên, từ bên trong thân lambda, this có nghĩa là instance bao ngoài. Thông tin lớp được sinh ra cho object lambda là chi tiết triển khai; không nên dựa vào tên lớp sinh tự động hoặc hành vi identity của lambda để thiết kế logic nghiệp vụ.

## 4. Ví dụ Java chạy được

Lưu nội dung sau trong file ThisAndScopeDemo.java. Ví dụ minh họa cả this, field bị che khuất và biến local được capture.

~~~java
public class ThisAndScopeDemo {
    private final String name = "outer field";

    private void demonstrate() {
        String text = "captured local";

        Runnable anonymous = new Runnable() {
            private final String name = "anonymous field";

            @Override
            public void run() {
                System.out.println("anonymous this == outer: "
                        + (this == (Object) ThisAndScopeDemo.this));
                System.out.println("anonymous this.name = " + this.name);
                System.out.println("anonymous outer name = "
                        + ThisAndScopeDemo.this.name);
                System.out.println("anonymous captured text = " + text);
            }
        };

        Runnable lambda = () -> {
            System.out.println("lambda this == outer: "
                    + (this == ThisAndScopeDemo.this));
            System.out.println("lambda this.name = " + this.name);
            System.out.println("lambda captured text = " + text);
        };

        anonymous.run();
        lambda.run();
    }

    public static void main(String[] args) {
        new ThisAndScopeDemo().demonstrate();
    }
}
~~~

Biên dịch và chạy bằng Java 17 trở lên:

~~~text
javac ThisAndScopeDemo.java
java ThisAndScopeDemo
~~~

Kết quả stdout:

~~~text
anonymous this == outer: false
anonymous this.name = anonymous field
anonymous outer name = outer field
anonymous captured text = captured local
lambda this == outer: true
lambda this.name = outer field
lambda captured text = captured local
~~~

Ở dòng đầu, phép ép kiểu sang Object giúp so sánh hai tham chiếu có kiểu tĩnh khác nhau. Kết quả false cho thấy this trong anonymous class là đối tượng callback; dòng tương ứng của lambda là true vì this trong lambda chính là instance bao ngoài. Anonymous class khai báo field name riêng nên this.name đọc field đó, còn ThisAndScopeDemo.this.name đọc field của instance bao ngoài.

## 5. Phạm vi tên và che khuất tên

### Field cùng tên

Trong ví dụ trên, cả lớp bao ngoài và anonymous class đều có field name. Tên không định danh this.name trong method của anonymous class trỏ đến field của đối tượng anonymous class. Muốn truy cập field của lớp bao ngoài, phải chỉ rõ ThisAndScopeDemo.this.name.

Trong lambda, không có field riêng thuộc thân lambda. Biểu thức this.name vì vậy trỏ đến field name của instance bao ngoài. Quy tắc này giúp lambda thường giữ cách tra cứu tên gần với code được viết trực tiếp trong method bao ngoài.

### Tham số và biến local

Tham số lambda có phạm vi trong lambda. Tên tham số hoặc biến local của lambda không được trùng tên với biến local hay tham số đang có trong phạm vi bao ngoài. Ví dụ sau cố ý không biên dịch:

~~~java
String value = "outer";
java.util.function.Consumer<String> consumer =
        value -> System.out.println(value); // Lỗi: tên value đã được khai báo ở scope bao ngoài
~~~

Hãy đổi tên tham số, chẳng hạn item, để tránh xung đột. Quy tắc này áp dụng cả khi tham số lambda nằm trong biểu thức nhiều dòng.

Anonymous class có phạm vi lớp riêng, nên có thể khai báo thành viên với tên trùng tên thành viên của lớp bao ngoài. Khi tên có khả năng gây nhầm lẫn, hãy dùng this.field cho thành viên của anonymous class và Outer.this.field cho thành viên của instance bao ngoài. Method bên trong anonymous class cũng có phạm vi tham số và biến local riêng của method đó.

### Capture biến local

Cả anonymous class lẫn lambda đều chỉ capture biến local hoặc tham số được khai báo final hay effectively final. Effectively final nghĩa là sau khi gán giá trị ban đầu, biến không được gán lại. Ví dụ, text trong chương trình mẫu được đọc từ hai callback nhưng không được gán lại nên hợp lệ.

Capture không biến biến local thành một biến có thể gán lại từ callback. Nếu cần thay đổi trạng thái, hãy chọn mô hình dữ liệu phù hợp, chẳng hạn một object có trạng thái mutable được thiết kế rõ ràng, hoặc chuyển trạng thái thành field của một object có vòng đời phù hợp. Không nên dùng wrapper mutable chỉ để lách quy tắc khi một thiết kế đơn giản hơn có thể giải quyết vấn đề.

## 6. Cách chọn

Chọn lambda khi cần triển khai một hành vi đơn lẻ cho functional interface, chẳng hạn predicate, comparator, callback hoặc thao tác trên stream. Cú pháp ngắn hơn và this tiếp tục trỏ đến instance bao ngoài, nên ít gây bất ngờ khi callback cần gọi method hoặc đọc field của lớp đang viết.

Chọn anonymous class khi cần field riêng cho từng callback, cần nhiều method trong thân lớp, cần tạo lớp con của một abstract class hoặc chủ ý cần this trỏ đến đối tượng callback. Với interface chỉ có một abstract method, cả hai cách đều có thể phù hợp; hãy chọn cách thể hiện rõ ý định và làm cho phạm vi tên dễ hiểu.

Đừng chuyển anonymous class sang lambda chỉ để giảm số dòng nếu thay đổi đó làm đổi ý nghĩa của this, super hoặc cách tra cứu tên. Trước khi refactor, hãy kiểm tra mọi lần dùng this, super, field trùng tên, method không định danh và biến local được capture.

## 7. Lỗi thường gặp

- Dùng this trong lambda như thể nó trỏ đến object callback. Trong lambda, this giữ ngữ cảnh bao ngoài.
- Dùng this.name trong anonymous class rồi nghĩ rằng nó luôn đọc field của lớp bao ngoài. Nếu anonymous class có field name, biểu thức đọc field của anonymous class; dùng Outer.this.name để chỉ rõ.
- Gán lại biến local sau khi biến đã được capture. Cả hai kiểu callback đều yêu cầu biến local được capture là final hoặc effectively final.
- Khai báo tham số lambda trùng tên biến local trong method bao ngoài. Hãy chọn tên khác để tránh lỗi biên dịch.
- Dựa vào tên lớp được sinh tự động hoặc identity của lambda. Đó không phải hợp đồng ổn định cho logic nghiệp vụ.
- Cho rằng lambda có thể khai báo field hoặc method như một lớp. Nếu callback cần trạng thái hoặc nhiều method, hãy cân nhắc anonymous class hoặc một lớp có tên.

## 8. Tự kiểm tra

1. Trong method của anonymous class, this.name trỏ đến đâu nếu anonymous class khai báo field name? Trả lời: field name của anonymous class.
2. Trong lambda viết bên trong instance method, this.name trỏ đến đâu? Trả lời: field name của instance bao ngoài.
3. Hai callback có thể capture một biến local không được khai báo final tường minh không? Có, nếu biến đó effectively final.
4. Khi cần gọi rõ method của instance bao ngoài từ anonymous class, nên viết thế nào? Dùng Outer.this.methodName() với tên lớp bao ngoài phù hợp.

