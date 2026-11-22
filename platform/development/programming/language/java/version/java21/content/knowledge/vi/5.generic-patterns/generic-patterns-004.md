# Suy luận kiểu với var trong các record pattern lồng nhau

Trong Java 21, từ khóa var có thể xuất hiện ở vị trí component pattern để trình biên dịch suy luận kiểu của biến được tạo ra. Khi record có tham số kiểu generic hoặc chứa record generic khác, trình biên dịch còn có thể suy luận các tham số kiểu của record pattern từ kiểu tĩnh của biểu thức đang được kiểm tra.

Nhờ đó, một pattern lồng nhiều cấp có thể ngắn gọn mà vẫn giữ kiểu cụ thể cho từng biến component. Ví dụ, nếu biểu thức có kiểu Box<Box<String>>, pattern Box(Box(var text)) cho biến text kiểu String.

## 1. var trong component pattern

Xét record không generic:

~~~java
record Point(double x, double y) {}
~~~

Khi dùng kiểu tường minh, pattern có thể viết:

~~~java
if (value instanceof Point(double x, double y)) {
    double distance = Math.hypot(x, y);
}
~~~

Vì kiểu của hai component đã được khai báo là double, có thể để trình biên dịch suy luận:

~~~java
if (value instanceof Point(var x, var y)) {
    // x và y đều có kiểu double
    double distance = Math.hypot(x, y);
}
~~~

var ở đây là kiểu component pattern được suy luận tại thời điểm biên dịch. Nó không biến biến pattern thành một biến có kiểu động và cũng không lấy kiểu từ giá trị runtime bằng reflection. Kiểu được suy luận từ kiểu component tương ứng của record sau khi kiểu record pattern đã được xác định.

## 2. Suy luận tham số kiểu của generic record

Khai báo một record generic đơn giản:

~~~java
record Box<T>(T value) {}
~~~

Giả sử phương thức nhận một Box<String>:

~~~java
static void printBox(Box<String> box) {
    if (box instanceof Box(var text)) {
        // text có kiểu String
        System.out.println(text.toUpperCase());
    }
}
~~~

Trình biên dịch suy luận pattern Box(var text) thành Box<String>(String text). Kiểu tĩnh Box<String> của biểu thức box cung cấp thông tin để suy luận tham số kiểu T là String; từ đó kiểu component T và kiểu của text cũng là String.

Có thể viết kiểu tường minh nếu muốn thể hiện rõ ràng hơn:

~~~java
if (box instanceof Box<String>(String text)) {
    System.out.println(text.toUpperCase());
}
~~~

Hai cách viết diễn đạt cùng một phép khớp trong ví dụ này. Dạng dùng var giảm phần lặp lại khi kiểu component đã rõ từ khai báo record và kiểu của biểu thức đang được kiểm tra.

## 3. Suy luận đệ quy trong record pattern lồng nhau

Khả năng suy luận vẫn tiếp tục qua nhiều cấp record generic. Với cùng khai báo Box<T>, xét phương thức nhận một Box<Box<String>>:

~~~java
static void printNestedBox(Box<Box<String>> box) {
    if (box instanceof Box(Box(var text))) {
        // text có kiểu String
        System.out.println(text.toUpperCase());
    }
}
~~~

Trình biên dịch suy luận cấu trúc pattern theo từng cấp:

| Vị trí | Kiểu được suy luận |
|---|---|
| Record pattern ngoài cùng | Box<Box<String>> |
| Component của record ngoài | Box<String> |
| Record pattern bên trong | Box<String> |
| Component của record bên trong | String |
| Biến pattern text | String |

Có thể đọc pattern từ ngoài vào trong: record ngoài chứa một Box<String>, record bên trong chứa một String. Vì vậy, var text nhận kiểu String mà không cần ghi lại các tham số kiểu ở từng cấp.

## 4. Suy luận kiểu qua các component có cấu trúc khác nhau

Ví dụ sau kết hợp một component chuỗi với một component là record generic:

~~~java
record Pair<A, B>(A first, B second) {}
record Response<T>(String requestId, T body) {}

static void handle(Response<Pair<String, Integer>> response) {
    if (response instanceof Response(
            var requestId,
            Pair(var label, var quantity))) {
        // requestId có kiểu String
        // label có kiểu String
        // quantity có kiểu Integer
        String message = requestId + ": " + label + " x " + quantity;
        System.out.println(message);
    }
}
~~~

Quá trình suy luận diễn ra từ kiểu tĩnh Response<Pair<String, Integer>>:

1. Record pattern ngoài được suy luận là Response<Pair<String, Integer>>.
2. Component thứ nhất có kiểu String, nên requestId có kiểu String.
3. Component thứ hai có kiểu Pair<String, Integer>, nên pattern lồng nhau được suy luận theo kiểu đó.
4. Hai component của Pair lần lượt có kiểu String và Integer, nên label và quantity nhận các kiểu tương ứng.

Ví dụ cho thấy var hữu ích khi cấu trúc dữ liệu có nhiều lớp generic: kiểu của từng biến vẫn chính xác theo khai báo component, dù pattern không lặp lại các tham số kiểu.

## 5. Sử dụng trong instanceof và switch

Java 21 hỗ trợ suy luận tham số kiểu cho generic record pattern trong các ngữ cảnh nhận pattern, bao gồm biểu thức instanceof, câu lệnh switch và biểu thức switch.

Với instanceof, kiểu của biến được suy luận từ kiểu tĩnh của biểu thức đang được kiểm tra:

~~~java
static void inspect(Box<String> box) {
    if (box instanceof Box(var value)) {
        String upper = value.toUpperCase();
        System.out.println(upper);
    }
}
~~~

Trong biểu thức switch, kiểu selector cũng cung cấp thông tin để suy luận:

~~~java
static String uppercase(Box<String> box) {
    return switch (box) {
        case null -> "(null)";
        case Box(var value) -> value.toUpperCase();
    };
}
~~~

Ở nhánh case Box(var value), pattern được suy luận theo Box<String>, do đó value có kiểu String. Nhánh case null xử lý riêng giá trị null; record pattern không khớp với null.

## 6. Kiểu được suy luận đến từ đâu?

Khi đọc một generic record pattern, cần phân biệt hai bước:

1. **Xác định kiểu của record pattern:** trình biên dịch suy luận hoặc kiểm tra tham số kiểu của record dựa trên kiểu tĩnh của biểu thức được khớp và các ràng buộc kiểu liên quan.
2. **Xác định kiểu của component pattern:** sau khi kiểu record đã được xác định, kiểu component được lấy từ khai báo record đã thay thế tham số generic tương ứng. var nhận kiểu component đó.

Ví dụ với Box<String>, tham số T được xác định là String, vì vậy component value cũng có kiểu String. Với Box<Box<String>>, quá trình này tiếp tục đệ quy để component bên trong cùng có kiểu String.

Đây là suy luận kiểu tại thời điểm biên dịch. Java không đọc được tham số generic thực tế của một đối tượng từ runtime để quyết định kiểu biến pattern; thông tin generic bị xóa theo cơ chế type erasure. Vì vậy, kiểu tĩnh và khả năng kiểm tra an toàn của phép khớp vẫn có ý nghĩa quyết định.

Nếu kiểu tĩnh của biểu thức không cung cấp đủ thông tin cho người đọc mã, có thể ghi tường minh tham số kiểu trong record pattern để làm rõ ý định. Dùng var giúp giảm lặp, nhưng không nên làm cho cấu trúc generic khó hiểu hơn.

## 7. Giới hạn và lỗi thường gặp

### Không nhầm var với kiểu của đối tượng tại runtime

var trong Box(var value) không yêu cầu JVM xác định kiểu generic của đối tượng tại runtime. Kiểu của value được suy luận trong quá trình biên dịch từ kiểu record pattern và kiểu component.

### Không thể yêu cầu một phép chuyển đổi generic không an toàn

Một record pattern tham số hóa chỉ hợp lệ khi phép kiểm tra kiểu tương ứng không đòi hỏi unchecked conversion. Ví dụ, không thể kiểm tra trực tiếp một biến có kiểu Object bằng pattern Box<String>(var value), vì JVM không thể xác nhận tham số kiểu String sau type erasure. Nếu đầu vào chỉ có kiểu Object, có thể kiểm tra record trước rồi kiểm tra component:

~~~java
static void inspect(Object value) {
    if (value instanceof Box<?> box
            && box.value() instanceof String text) {
        System.out.println(text.toUpperCase());
    }
}
~~~

Khi API đã biết dữ liệu là Box<String>, hãy giữ kiểu generic đó trong khai báo và chữ ký phương thức để trình biên dịch có đủ thông tin suy luận.

### Kiểm tra đúng thứ tự component

Các component pattern khớp theo thứ tự khai báo trong record. Với Pair<A, B>(A first, B second), pattern Pair(var first, var second) suy luận hai kiểu theo đúng thứ tự A, rồi B. Đổi vị trí hai pattern sẽ đổi component mà biến nhận được.

### Record pattern lồng nhau phải khớp cấu trúc thực tế

Với Box<Box<String>>, pattern Box(Box(var text)) yêu cầu component ngoài là một Box và component bên trong cũng phải khớp record pattern. Nếu component lồng nhau là null, pattern lồng nhau không khớp và phần thân tương ứng không chạy.

### Không dùng pattern để thay thế kiểm tra null tổng quát

instanceof với record pattern không khớp null. Trong switch, nếu selector có thể là null, cần xử lý trường hợp đó rõ ràng khi logic của chương trình yêu cầu.

## 8. Cấu hình biên dịch và thực hành

Record patterns và suy luận kiểu cho generic record patterns là tính năng ngôn ngữ chuẩn trong Java 21, không cần bật preview flag. Có thể biên dịch mã ví dụ bằng JDK 21 với:

~~~shell
javac --release 21 Example.java
java Example
~~~

Khi thực hành, hãy thử thay kiểu khai báo của biến đầu vào từ Box<String> thành Box<Box<String>>, rồi quan sát cách pattern lồng nhau suy luận kiểu của biến component. Cũng có thể viết một phiên bản với tham số kiểu tường minh để so sánh tính dễ đọc và xác nhận kiểu mà trình biên dịch suy luận.

Tài liệu tham khảo:

- [Oracle Java 21 — Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html)
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440)
