# Phân biệt tương thích mã nguồn, nhị phân và hành vi

Khi một thư viện Java được nâng cấp, câu hỏi “API mới có tương thích không?” có ít nhất ba câu trả lời khác nhau. Một thay đổi có thể vẫn cho phép mã nguồn cũ biên dịch, vẫn cho phép bytecode cũ liên kết với thư viện mới, nhưng lại làm chương trình chạy khác trước. Vì vậy, hãy đánh giá riêng **tương thích mã nguồn (source compatibility)**, **tương thích nhị phân (binary compatibility)** và **tương thích hành vi (behavioral compatibility)**.

## 1. Ba loại tương thích

### Tương thích mã nguồn

Một thay đổi tương thích mã nguồn khi mã nguồn client đang hợp lệ với phiên bản API cũ vẫn có thể biên dịch với phiên bản API mới, trong cùng điều kiện compiler và dependency phù hợp.

Đây là phép thử có biên dịch lại client. Kết quả có thể thay đổi vì compiler phân giải overload, generic type hoặc kiểu trả về dựa trên API mới. Do đó, “vẫn biên dịch được” cũng chưa chắc có nghĩa là chương trình sẽ gọi đúng overload như trước.

### Tương thích nhị phân

Một thay đổi tương thích nhị phân khi các class file đã biên dịch với API cũ vẫn liên kết được với phiên bản thư viện mới mà không cần biên dịch lại client. JVM tìm phương thức và trường bằng các thông tin như tên lớp, tên thành viên và descriptor nhị phân.

Tương thích nhị phân hữu ích khi thư viện được nâng cấp độc lập với ứng dụng. Tuy nhiên, nó không bảo đảm mọi đường chạy đều thành công: một lời gọi mới có thể gặp `AbstractMethodError`, một thành viên đã bị xóa có thể gây `NoSuchMethodError` hoặc `NoSuchFieldError`, và thay đổi hành vi vẫn có thể làm hỏng logic của ứng dụng.

### Tương thích hành vi

Một thay đổi tương thích hành vi khi chương trình tiếp tục đáp ứng hợp đồng mà client được quyền dựa vào. Hợp đồng có thể bao gồm giá trị trả về, ngoại lệ, tác dụng phụ, thứ tự phần tử, quy tắc xử lý `null`, tính bất biến của kết quả, tính an toàn luồng hoặc thời điểm thực hiện thao tác.

Không phải mọi chi tiết triển khai đều là hợp đồng. Nếu API không cam kết thứ tự phần tử, client không nên dựa vào thứ tự tình cờ quan sát được. Nhưng khi tài liệu đã cam kết thứ tự, thay đổi thứ tự có thể là phá vỡ tương thích hành vi dù chữ ký phương thức không đổi.

| Loại | Câu hỏi kiểm tra | Cách kiểm tra chính |
|---|---|---|
| Mã nguồn | Source cũ có biên dịch với API mới không? | Biên dịch lại các client đại diện |
| Nhị phân | Class file cũ có chạy với thư viện mới không? | Chạy client đã biên dịch mà không biên dịch lại |
| Hành vi | Kết quả và hợp đồng quan sát được có còn đúng không? | Kiểm thử hợp đồng, hồi quy và tích hợp |

## 2. Vì sao một thay đổi có thể ảnh hưởng khác nhau?

Xét một thư viện có lớp `Printer`. Phiên bản 1 chỉ có phương thức `print(Object)`. Một client gọi phương thức bằng `null`:

~~~java
new Printer().print(null);
~~~

Ở phiên bản 2, thư viện thêm overload `print(String)`. Mã nguồn client cũ vẫn có thể biên dịch, nhưng khi biên dịch lại, compiler chọn overload `print(String)` vì `String` cụ thể hơn `Object`. Trong khi đó, bytecode client đã biên dịch với phiên bản 1 vẫn chứa lời gọi đến descriptor của `print(Object)`.

Đây là ví dụ quan trọng: **thêm overload thường giữ lại liên kết nhị phân cũ, nhưng có thể thay đổi overload được chọn khi biên dịch lại source**. Nếu hai overload có hành vi khác nhau, kết quả còn có thể thay đổi theo việc client đã được biên dịch lại hay chưa.

### Thí nghiệm có thể chạy

Tạo cấu trúc tệp sau:

~~~text
v1/Printer.java
v2/Printer.java
Client.java
~~~

`v1/Printer.java`:

~~~java
public class Printer {
    public void print(Object value) {
        System.out.println("Object overload");
    }
}
~~~

`v2/Printer.java` giữ nguyên phương thức cũ và thêm overload:

~~~java
public class Printer {
    public void print(Object value) {
        System.out.println("Object overload");
    }

    public void print(String value) {
        System.out.println("String overload");
    }
}
~~~

`Client.java`:

~~~java
public class Client {
    public static void main(String[] args) {
        new Printer().print(null);
    }
}
~~~

Biên dịch client với phiên bản 1, sau đó thay class của thư viện bằng phiên bản 2 nhưng không biên dịch lại client:

~~~text
javac -d out v1/Printer.java Client.java
javac -d out v2/Printer.java
java -cp out Client
~~~

Kết quả:

~~~text
Object overload
~~~

Bây giờ biên dịch lại client với API phiên bản 2:

~~~text
javac -cp out -d out Client.java
java -cp out Client
~~~

Kết quả:

~~~text
String overload
~~~

Thí nghiệm dùng cú pháp Java thông thường, chạy được trên JDK 17 trở lên. Hai kết quả khác nhau không phải do JVM chọn overload lúc chạy: **overload được chọn lúc biên dịch**, rồi tên và descriptor của lời gọi được ghi vào bytecode.

## 3. Tiến hóa interface: thêm phương thức abstract và default

Thay đổi interface cần được xem xét cẩn thận vì nhiều lớp bên ngoài thư viện có thể đang triển khai interface đó.

### Thêm phương thức abstract

Giả sử phiên bản đầu có:

~~~java
public interface TextCodec {
    String encode(String input);
}
~~~

Một client đã cung cấp lớp `LegacyCodec implements TextCodec`. Nếu phiên bản mới thêm phương thức abstract `String id()`, mã nguồn `LegacyCodec` khi biên dịch lại sẽ lỗi cho đến khi nó triển khai `id()` hoặc kế thừa một triển khai hợp lệ.

Các class file cũ có thể vẫn được nạp và liên kết ở những đường chạy không gọi phương thức mới. Nhưng nếu client mới gọi `id()` trên một đối tượng `LegacyCodec` cũ không có triển khai tương ứng, JVM có thể ném `AbstractMethodError`. Vì vậy, thêm phương thức abstract có thể duy trì một số khía cạnh liên kết nhị phân mà vẫn làm hỏng source cũ và đường chạy mới.

~~~java
public interface TextCodec {
    String encode(String input);

    // Được thêm ở phiên bản API mới:
    String id();
}
~~~

Đoạn mã trên minh họa chữ ký ở phiên bản mới; nó không phải một ví dụ độc lập có thể biên dịch cùng mọi lớp triển khai cũ.

### Thêm phương thức default

Java cho phép interface cung cấp triển khai mặc định:

~~~java
public interface TextCodec {
    String encode(String input);

    default String normalize(String input) {
        return input.trim();
    }
}
~~~

Một lớp đã biên dịch chỉ triển khai `encode` thường có thể tiếp tục hoạt động với phiên bản interface mới và nhận triển khai mặc định của `normalize`. Client mới biên dịch với interface mới có thể gọi phương thức đó trên đối tượng triển khai cũ.

Dù vậy, thêm `default` không phải lúc nào cũng vô hại:

- Nếu một lớp triển khai hai interface có các phương thức default xung đột cùng chữ ký, lớp có thể phải ghi đè phương thức để giải quyết xung đột.
- Nếu lớp đã có phương thức phù hợp với chữ ký mới, phương thức của lớp có thể được dùng thay cho default và tạo ra hành vi khác mà tác giả thư viện không dự định.
- Nếu kiểu trả về, quyền truy cập hoặc các quan hệ kiểu khiến chữ ký mới xung đột với mã hiện hữu, việc biên dịch lại có thể thất bại.

Khi thiết kế API interface, hãy cân nhắc phương thức default cho chức năng có triển khai mặc định hợp lý; ghi rõ hợp đồng của nó và kiểm thử với các kiểu triển khai tiêu biểu. Đừng coi `default` là bảo đảm tuyệt đối cho mọi client.

## 4. Thay đổi hành vi dù chữ ký không đổi

Giả sử API công khai phương thức:

~~~java
List<String> names();
~~~

Chữ ký này có thể không thay đổi qua nhiều phiên bản, nên source và bytecode client vẫn biên dịch/liên kết. Nhưng phiên bản mới có thể phá vỡ hành vi nếu thay đổi một cam kết trước đó, ví dụ:

- Kết quả từng có thứ tự theo tên nay trả về thứ tự không xác định.
- Danh sách có thể sửa đổi nay trở thành danh sách chỉ đọc.
- Đầu vào `null` từng được hỗ trợ nay gây `NullPointerException`.
- Một trường hợp không tìm thấy trước đây trả về `Optional.empty()` nay ném ngoại lệ.
- Phương thức trước đây không sửa đối tượng đầu vào nay thay đổi nó.
- Một thao tác từng an toàn khi gọi đồng thời nay dùng trạng thái dùng chung không được bảo vệ.
- Phương thức từng thực hiện nhanh và đồng bộ nay thực hiện I/O hoặc gọi callback bất ngờ.

Một số ví dụ chỉ là phá vỡ tương thích nếu hợp đồng cũ đã cam kết hành vi đó. Khi hành vi chưa được đặc tả, hãy phân biệt rõ giữa lỗi thực sự của thư viện và giả định riêng mà client xây dựng từ chi tiết triển khai không được bảo đảm.

Khi thay đổi hành vi là cần thiết, hãy cập nhật tài liệu, release notes và kiểm thử. Nếu thay đổi có khả năng ảnh hưởng client, cân nhắc phương thức mới hoặc cơ chế opt-in để người dùng chuyển đổi có chủ đích.

## 5. Bảng tham khảo khi tiến hóa API

| Thay đổi | Mã nguồn | Nhị phân | Rủi ro hành vi / lưu ý |
|---|---|---|---|
| Thêm phương thức tiện ích mới với tên khác | Thường tương thích | Thường tương thích | Kiểm tra overload, trạng thái dùng chung và hợp đồng |
| Thêm overload vào phương thức đang có | Có thể đổi cách phân giải hoặc gây mơ hồ | Thường giữ được lời gọi cũ nếu thành viên cũ còn nguyên | Client biên dịch lại có thể gọi overload khác |
| Thêm phương thức abstract vào interface | Có thể làm lớp triển khai cũ không biên dịch | Class file cũ có thể liên kết nhưng lời gọi phương thức mới có thể lỗi | Nguy cơ `AbstractMethodError` |
| Thêm phương thức default vào interface | Thường tương thích, nhưng có thể phát sinh xung đột | Thường tương thích | Triển khai kế thừa hoặc ghi đè có thể làm đổi kết quả |
| Xóa hoặc đổi tên phương thức công khai | Không tương thích nếu source dùng phương thức đó | Không tương thích nếu bytecode còn tham chiếu | Có thể gặp `NoSuchMethodError` |
| Đổi kiểu tham số của phương thức | Thường không tương thích | Descriptor cũ không còn khớp | Kiểm tra mọi client gọi phương thức |
| Đổi kiểu trả về của phương thức công khai | Có thể làm source cũ lỗi | Thường phá vỡ descriptor nhị phân | Không nhầm với bridge method do compiler tạo cho override covariant |
| Chỉ đổi cách thực hiện, giữ nguyên chữ ký | Thường tương thích về biên dịch | Thường tương thích về liên kết | Có thể phá vỡ hợp đồng hành vi |
| Siết điều kiện đầu vào hoặc đổi ngoại lệ | Có thể khiến client phải sửa mã | Thường không đổi descriptor | Client hợp lệ trước đây có thể thất bại lúc chạy |

Bảng này là hướng dẫn đánh giá ban đầu, không thay thế việc kiểm tra chi tiết chữ ký, kế thừa, generic type, module và các đường chạy thực tế. “Thường tương thích” không có nghĩa là được miễn kiểm thử.

## 6. Cách đánh giá một thay đổi trước khi phát hành

1. **Xác định hợp đồng công khai.** Liệt kê chữ ký, kiểu trả về, ngoại lệ, quy tắc `null`, khả năng sửa đổi kết quả, thứ tự và các cam kết khác mà client được phép dựa vào.
2. **Kiểm tra source compatibility.** Biên dịch lại một tập client đại diện với thư viện mới. Bao gồm cả các trường hợp overload, lambda, method reference, generic type và lớp tự triển khai interface.
3. **Kiểm tra binary compatibility.** Chạy các class file đã biên dịch với thư viện mới mà không biên dịch lại client. Kiểm tra các đường chạy có gọi thành viên thay đổi, nhất là phương thức mới trên đối tượng triển khai cũ.
4. **Kiểm tra behavioral compatibility.** Dùng kiểm thử hợp đồng và hồi quy để so sánh đầu ra, ngoại lệ, tác dụng phụ, thứ tự, khả năng sửa đổi và các thuộc tính được tài liệu cam kết.
5. **Đọc kỹ các lỗi ở thời điểm chạy.** `NoSuchMethodError` và `NoSuchFieldError` thường cho thấy bytecode đang tìm một thành viên không còn tồn tại với descriptor mong đợi. `AbstractMethodError` có thể xuất hiện khi lời gọi không tìm được triển khai cụ thể. Các lỗi này khác với lỗi biên dịch source.
6. **Thông báo rõ thay đổi.** Release notes nên nêu hành vi thay đổi, client bị ảnh hưởng, cách chuyển đổi và phiên bản cần dùng. Nếu cần, cung cấp giai đoạn chuyển tiếp hoặc phương thức mới trước khi loại bỏ API cũ.

Công cụ phân tích tương thích nhị phân có thể phát hiện nhiều thay đổi về chữ ký và cấu trúc, nhưng không chứng minh được tương thích hành vi. Kiểm thử tích hợp cũng không thay thế biên dịch client cũ; mỗi loại kiểm tra trả lời một câu hỏi khác nhau.

## 7. Lỗi đánh giá thường gặp

- **Chỉ kiểm tra biên dịch:** source có thể biên dịch nhưng gọi overload khác hoặc nhận hành vi mới.
- **Chỉ chạy test sau khi build lại tất cả:** cách này bỏ qua rủi ro của class file cũ còn được triển khai ngoài thực tế.
- **Cho rằng API có chữ ký giống nhau là tương thích:** hành vi, ngoại lệ và điều kiện đầu vào cũng là một phần của hợp đồng.
- **Cho rằng thêm default method luôn an toàn:** xung đột giữa interface và phương thức có sẵn vẫn có thể xuất hiện.
- **Cho rằng một lỗi của client chứng minh thư viện không tương thích:** trước tiên hãy xác định client có dựa vào hành vi được tài liệu cam kết hay vào chi tiết triển khai không được bảo đảm.
- **Sửa nhiều thay đổi cùng lúc:** khi một bản phát hành đổi chữ ký và đổi hành vi đồng thời, rất khó xác định nguyên nhân hồi quy. Chia nhỏ thay đổi và ghi lại hợp đồng trước/sau sẽ giúp đánh giá dễ hơn.

Khi xem xét một bản nâng cấp Java, hãy ghi riêng kết luận cho ba trục: mã nguồn, nhị phân và hành vi. Chỉ kết luận “tương thích” khi đã nêu rõ tương thích với client nào, trong điều kiện nào, và đã kiểm tra bằng phương pháp nào.
