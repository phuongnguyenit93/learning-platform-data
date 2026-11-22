# Vì sao tương thích nhị phân chưa bảo đảm tương thích mã nguồn hoặc hành vi

Khi nâng cấp Java hoặc thay phiên bản một thư viện, một ứng dụng có thể tiếp tục chạy bằng các file `.class` đã biên dịch từ trước nhưng lại không biên dịch được khi build lại từ mã nguồn. Cũng có trường hợp ứng dụng biên dịch và liên kết thành công, nhưng kết quả nghiệp vụ thay đổi khi chạy. Những tình huống này xuất phát từ việc **tương thích mã nguồn, tương thích nhị phân và tương thích hành vi là ba khía cạnh khác nhau**.

Tương thích nhị phân tập trung vào khả năng mã bytecode đã tồn tại tiếp tục tham chiếu và liên kết với các class, field, method mà nó cần. Nó không chứng minh rằng compiler mới vẫn chấp nhận mọi mã nguồn cũ, cũng không chứng minh rằng các phương thức được gọi vẫn tạo ra kết quả như trước. Khi đánh giá một lần nâng cấp JDK hoặc dependency, cần kiểm tra riêng cả ba khía cạnh.

## 1. Ba khái niệm tương thích cần phân biệt

### 1.1. Tương thích mã nguồn (source compatibility)

Tương thích mã nguồn trả lời câu hỏi: **mã nguồn của chương trình có thể được biên dịch lại thành công với phiên bản thư viện, JDK hoặc compiler mới hay không?**

Compiler phân tích lại toàn bộ biểu thức và kiểu dữ liệu trong mã nguồn. Nó kiểm tra quyền truy cập, kiểu tham số, kiểu trả về, generic, overload, chuyển đổi kiểu, suy luận kiểu và nhiều quy tắc của ngôn ngữ Java. Vì thế, một thay đổi trong API có thể làm cho lời gọi trước đây hợp lệ trở thành mơ hồ hoặc không còn đúng kiểu, dù các method descriptor mà bytecode cũ sử dụng vẫn tồn tại.

Ví dụ, một thư viện thêm overload mới có thể làm lời gọi `send(null)` trở nên mơ hồ khi biên dịch lại. Mã nguồn cũ không đổi, nhưng compiler mới không thể chọn duy nhất phương thức phù hợp.

### 1.2. Tương thích nhị phân (binary compatibility)

Tương thích nhị phân tập trung vào khả năng các file `.class` đã biên dịch tiếp tục được JVM nạp, phân giải tham chiếu và liên kết với phiên bản thư viện mới. Bytecode chứa các tham chiếu biểu tượng đến class, field và method; khi chạy, JVM cần tìm được thành phần tương ứng với tên và descriptor mà bytecode yêu cầu.

Ví dụ, bytecode của một ứng dụng đã biên dịch có thể gọi method `send(Object)`. Nếu phiên bản thư viện mới vẫn giữ method đó với descriptor tương ứng, lời gọi cũ có thể tiếp tục liên kết thành công, ngay cả khi thư viện đã bổ sung thêm các overload khiến mã nguồn gọi `send(null)` không thể biên dịch lại.

Tương thích nhị phân vì vậy quan tâm đến hợp đồng ở mức class file và liên kết. Nó không chạy lại quá trình kiểm tra kiểu trên mã nguồn, cũng không xác nhận ý nghĩa nghiệp vụ của phương thức.

### 1.3. Tương thích hành vi (behavioral compatibility)

Tương thích hành vi trả lời câu hỏi: **khi chạy trong cùng điều kiện và với cùng đầu vào, chương trình có tiếp tục tạo ra kết quả và tác động mà bên sử dụng mong đợi hay không?**

Hành vi có thể bao gồm:

- Giá trị trả về và cách diễn giải giá trị đó.
- Dữ liệu được đọc, ghi, chuyển đổi hoặc sắp xếp.
- Ngoại lệ được ném ra, thời điểm ném và cách lỗi được xử lý.
- Tác dụng phụ như ghi database, gửi message hoặc gọi dịch vụ bên ngoài.
- Thứ tự xử lý, tính đồng thời và các bảo đảm về thread-safety.
- Thời gian phản hồi, mức dùng bộ nhớ và những đặc tính vận hành được hệ thống phụ thuộc.

Một phương thức có thể giữ nguyên tên, kiểu tham số và kiểu trả về nên bytecode cũ vẫn gọi được. Tuy nhiên, nếu cách tính toán bên trong thay đổi, ứng dụng vẫn có thể cho kết quả khác. Đó là thay đổi hành vi dù không có lỗi liên kết nhị phân.

| Khía cạnh | Đối tượng được kiểm tra | Câu hỏi chính |
|---|---|---|
| Source compatibility | Mã nguồn và quy tắc biên dịch | Có thể biên dịch lại mã nguồn cũ không? |
| Binary compatibility | Bytecode và các tham chiếu class file | Bytecode đã có còn liên kết được với thư viện mới không? |
| Behavioral compatibility | Kết quả và tác động khi thực thi | Chương trình còn làm đúng điều mà người dùng và hệ thống mong đợi không? |

## 2. Vì sao tương thích nhị phân không bảo đảm tương thích mã nguồn?

Lý do chính nằm ở thời điểm và loại thông tin mà JVM và compiler sử dụng. Bytecode cũ đã ghi lại lời gọi method cùng descriptor được chọn tại thời điểm biên dịch. JVM không cần thực hiện lại việc phân giải overload trên biểu thức nguồn ban đầu. Ngược lại, khi biên dịch lại, compiler phải xét toàn bộ API mới và áp dụng các quy tắc kiểu của Java.

### 2.1. Thêm overload có thể làm mã nguồn cũ trở nên mơ hồ

Giả sử phiên bản đầu của thư viện có class sau:

```java
public class MessageSender {
    public void send(Object value) {
        System.out.println("Send object: " + value);
    }
}
```

Ứng dụng sử dụng thư viện:

```java
MessageSender sender = new MessageSender();
sender.send(null);
```

Ở phiên bản đầu, chỉ có `send(Object)`, nên compiler chọn phương thức này. Bytecode của ứng dụng ghi nhận lời gọi đến method có tham số `Object`.

Sau đó, nhà cung cấp thư viện bổ sung hai overload nhưng vẫn giữ phương thức cũ:

```java
public class MessageSender {
    public void send(Object value) {
        System.out.println("Send object: " + value);
    }

    public void send(String value) {
        System.out.println("Send text: " + value);
    }

    public void send(Integer value) {
        System.out.println("Send number: " + value);
    }
}
```

Khi biên dịch lại dòng lệnh:

```java
sender.send(null);
```

compiler thấy cả `send(String)` và `send(Integer)` đều có thể nhận `null`. Hai kiểu `String` và `Integer` không phải kiểu con của nhau, nên không có overload cụ thể duy nhất được chọn. Compiler báo lỗi lời gọi mơ hồ, thường với thông báo `reference to send is ambiguous`.

Tuy nhiên, ứng dụng đã biên dịch từ phiên bản đầu vẫn có thể chạy với thư viện mới: bytecode của nó vẫn tham chiếu đến `send(Object)`, và method này vẫn còn nguyên. Việc thêm overload không làm mất descriptor cũ.

```text
Mã nguồn cũ: sender.send(null)
          |
          v
Biên dịch với API phiên bản 1
          |
          v
Bytecode gọi send(Object)
          |
          v
Chạy với API phiên bản 2: vẫn tìm thấy send(Object)

Biên dịch lại mã nguồn cũ với API phiên bản 2
          |
          v
send(String) và send(Integer) cùng phù hợp
          |
          v
Lỗi biên dịch: lời gọi mơ hồ
```

Đây là ví dụ điển hình của trường hợp tương thích nhị phân vẫn được duy trì nhưng tương thích mã nguồn bị phá vỡ. Nếu cần biên dịch lại, ứng dụng có thể sửa lời gọi để chỉ rõ kiểu hoặc overload mong muốn, chẳng hạn `sender.send((Object) null)`. Việc sửa như vậy cần dựa trên ý nghĩa nghiệp vụ của lời gọi, không chỉ nhằm làm compiler hết báo lỗi.

### 2.2. Thay đổi generic có thể giữ nguyên descriptor nhưng đổi kết quả kiểm tra kiểu

Java sử dụng type erasure cho generic. Nhiều thông tin generic được giữ trong metadata của class file để compiler và công cụ đọc, nhưng descriptor mà JVM dùng để liên kết method dựa trên kiểu đã xóa (erasure).

Giả sử thư viện ban đầu khai báo:

```java
import java.util.List;

public class Catalog {
    public List<String> names() {
        return List.of("Java", "Spring");
    }
}
```

Ứng dụng gọi:

```java
String firstName = catalog.names().get(0);
```

Phiên bản mới thay đổi kiểu generic trả về:

```java
import java.util.List;

public class Catalog {
    public List<Object> names() {
        return List.of("Java", "Spring");
    }
}
```

Ở mức descriptor JVM, cả hai phiên bản đều có kiểu trả về đã xóa là `java.util.List`. Vì vậy, nếu tên method và các phần khác của descriptor được giữ nguyên, bytecode cũ vẫn có thể phân giải lời gọi `names()`.

Khi biên dịch lại mã nguồn, compiler đọc thông tin generic của API mới và xem `get(0)` trả về `Object`. Không thể gán trực tiếp `Object` vào biến `String`, nên dòng mã nguồn trên không còn biên dịch được nếu không có phép kiểm tra/chuyển kiểu phù hợp.

Ví dụ này cho thấy metadata kiểu mà compiler dùng có thể thay đổi trong khi descriptor liên kết của JVM không đổi. Nó cũng cho thấy việc bytecode cũ liên kết được không bảo đảm dữ liệu thực tế vẫn thỏa mãn giả định kiểu mà mã nguồn cũ từng có. Nếu thư viện mới thực sự trả về phần tử không phải `String`, bytecode cũ có thể gặp `ClassCastException` ở điểm kiểm tra kiểu do compiler đã sinh ra.

### 2.3. Quy tắc overload, suy luận kiểu và chuyển đổi kiểu thuộc về compiler

Ngoài hai trường hợp trên, các thay đổi API có thể ảnh hưởng đến mã nguồn thông qua:

- Bổ sung overload làm thay đổi lựa chọn phương thức hoặc tạo lời gọi mơ hồ.
- Thay đổi generic bounds làm một kiểu tham số trước đây hợp lệ không còn thỏa điều kiện.
- Thay đổi kiểu trả về generic khiến kết quả không còn gán được cho biến hoặc truyền vào method khác.
- Thêm thành viên vào interface hoặc superclass làm phát sinh xung đột tên, quy tắc kế thừa hoặc lựa chọn method ở mã nguồn.
- Thay đổi quyền truy cập hoặc cấu trúc package/module làm compiler từ chối truy cập.
- Thay đổi yêu cầu về phiên bản ngôn ngữ hoặc API chuẩn mà compiler được phép sử dụng.

Các quy tắc này được áp dụng khi biên dịch. JVM chạy bytecode không thực hiện lại toàn bộ phân tích nguồn, nên một binary cũ có thể vẫn hoạt động dù mã nguồn tương ứng không còn biên dịch được.

## 3. Vì sao tương thích nhị phân không bảo đảm tương thích hành vi?

Liên kết thành công chỉ chứng minh JVM tìm được các thành phần mà bytecode tham chiếu theo tên và descriptor. JVM không biết hợp đồng nghiệp vụ mà ứng dụng kỳ vọng, chẳng hạn đơn giá có bao gồm thuế hay không, chuỗi được giải mã theo encoding nào, hoặc danh sách phải được sắp xếp theo quy tắc nào.

### 3.1. Cùng chữ ký phương thức nhưng ý nghĩa kết quả thay đổi

Giả sử một thư viện tính phí có API:

```java
public class FeeCalculator {
    public long calculate(long amount) {
        return amount * 2 / 100;
    }
}
```

Ứng dụng đã được xây dựng dựa trên hợp đồng rằng phương thức trả về phí bằng 2% số tiền đầu vào. Phiên bản thư viện mới vẫn giữ nguyên method `calculate(long)` và kiểu trả về `long`, nhưng thay đổi cách tính do chính sách sản phẩm chuyển sang mức phí 3%:

```java
public class FeeCalculator {
    public long calculate(long amount) {
        return amount * 3 / 100;
    }
}
```

Tên method, kiểu tham số và kiểu trả về vẫn như cũ. Bytecode cũ tiếp tục liên kết và gọi được phương thức. Tuy nhiên, cùng đầu vào sẽ cho kết quả khác. Nếu ứng dụng không được cập nhật để chấp nhận chính sách mới, kết quả hóa đơn hoặc đối soát có thể sai so với mong đợi.

Vấn đề ở đây không nằm ở class file. Đó là thay đổi hợp đồng hành vi mà chữ ký Java không mô tả đầy đủ.

### 3.2. Giá trị mặc định hoặc dữ liệu môi trường thay đổi

Một phương thức có thể giữ nguyên chữ ký nhưng phụ thuộc vào giá trị mặc định của JDK hoặc hệ điều hành. Ví dụ, ứng dụng dùng `new String(bytes)` để giải mã dữ liệu mà không chỉ định charset. Từ Java 18, UTF-8 trở thành charset mặc định trong các môi trường tiêu chuẩn theo JEP 400. Nếu ứng dụng trước đây chạy ở môi trường có charset mặc định khác UTF-8, cùng byte array có thể được diễn giải thành chuỗi khác sau khi nâng cấp.

Bytecode vẫn gọi được constructor `String(byte[])`; tương thích nhị phân không bị ảnh hưởng. Nhưng nội dung văn bản được tạo ra có thể khác, làm sai dữ liệu nhập, xuất hoặc so sánh.

Để tránh phụ thuộc vào mặc định, hãy chỉ định encoding theo hợp đồng dữ liệu:

```java
import java.nio.charset.StandardCharsets;

String content = new String(bytes, StandardCharsets.UTF_8);
```

Những mặc định khác như locale, timezone, dữ liệu múi giờ, chính sách TLS hoặc thuật toán mật mã cũng có thể tác động đến hành vi trong khi các method descriptor vẫn giữ nguyên.

### 3.3. Cách xử lý ngoại lệ và tác dụng phụ có thể thay đổi

Một thư viện có thể vẫn cung cấp method `load(String)` nhưng thay đổi cách xử lý đầu vào không hợp lệ. Trước đây method trả về giá trị rỗng; phiên bản mới ném `IllegalArgumentException`. Bytecode gọi method không gặp lỗi liên kết, nhưng luồng xử lý của ứng dụng thay đổi vì một ngoại lệ mới xuất hiện.

Tương tự, method có thể tiếp tục nhận cùng tham số nhưng thay đổi tác dụng phụ: ghi thêm một bản ghi audit, gửi message trước khi transaction commit, gọi dịch vụ ngoài hoặc thay đổi thứ tự cập nhật dữ liệu. Các thay đổi này có thể ảnh hưởng đến tính nhất quán và tích hợp của toàn hệ thống.

Khi đánh giá hành vi, cần quan sát cả kết quả trả về lẫn ngoại lệ, dữ liệu được ghi, request gửi ra ngoài và trạng thái sau khi thực hiện. Chỉ kiểm tra rằng method không ném lỗi liên kết là chưa đủ.

### 3.4. Hiệu năng và tính đồng thời cũng có thể làm thay đổi trải nghiệm thực tế

Hai phiên bản có thể giữ nguyên API và tạo cùng kết quả trong một bài kiểm tra đơn giản, nhưng khác nhau về hiệu năng hoặc cách đồng bộ. Một thay đổi thuật toán có thể làm độ phức tạp tăng lên; một thay đổi trong quản lý thread hoặc cache có thể làm lộ race condition vốn ít xuất hiện trước đây.

Trong hệ thống đang hoạt động, độ trễ tăng, thứ tự message thay đổi hoặc tài nguyên bị tiêu thụ nhiều hơn cũng có thể phá vỡ giả định vận hành của các thành phần khác. Những khác biệt này không được thể hiện qua method descriptor và thường chỉ xuất hiện dưới tải hoặc khi có nhiều request đồng thời.

## 4. Các khía cạnh tương thích có thể độc lập với nhau

Không nên xem ba loại tương thích như một thang điểm mà đạt loại này thì tự động đạt loại tiếp theo. Một thay đổi có thể giữ một khía cạnh nhưng phá vỡ khía cạnh khác.

| Tình huống | Mã nguồn cũ biên dịch lại | Bytecode cũ liên kết | Hành vi được giữ nguyên | Giải thích |
|---|---|---|---|---|
| Thêm overload `send(String)` và `send(Integer)`, giữ `send(Object)` | Không, nếu mã nguồn gọi `send(null)` | Có | Có thể có, nếu lời gọi cũ vẫn đi vào `send(Object)` và logic không đổi | Lời gọi nguồn trở nên mơ hồ, còn bytecode cũ vẫn gọi descriptor đã chọn trước đó. |
| Đổi `process(int)` thành `process(long)` | Có thể có, nếu lời gọi nguồn truyền `int` và được widening | Không với binary cũ chỉ tham chiếu `process(int)` | Chưa thể kết luận | Compiler có thể biên dịch lời gọi mới sang `process(long)`, nhưng bytecode cũ vẫn tìm descriptor `process(int)`. |
| Giữ nguyên chữ ký nhưng đổi cách tính phí | Có | Có | Không | JVM liên kết được, nhưng kết quả nghiệp vụ thay đổi. |
| Giữ API, descriptor và hợp đồng xử lý | Có | Có | Có, trong phạm vi đã kiểm chứng | Cả ba khía cạnh đều được duy trì. |

Ví dụ đổi `process(int)` thành `process(long)` cho thấy chiều ngược lại cũng quan trọng: **tương thích mã nguồn không tự động bảo đảm tương thích nhị phân**. Mã nguồn được biên dịch lại có thể dùng phép mở rộng kiểu `int` sang `long`, nhưng bytecode cũ vẫn yêu cầu method descriptor có tham số `int`. Nếu descriptor cũ đã bị loại bỏ, JVM có thể ném `NoSuchMethodError` khi thực hiện lời gọi.

Vì vậy, khi một thư viện được dùng bởi nhiều ứng dụng hoặc plugin đã biên dịch ở những thời điểm khác nhau, việc chỉ build lại một ứng dụng đại diện không chứng minh mọi binary hiện có đều tương thích.

## 5. Tương thích nhị phân được bảo đảm trong phạm vi nào?

Tương thích nhị phân là một khái niệm có phạm vi cụ thể. Nó phụ thuộc vào những class file, API và phiên bản thư viện thực sự được sử dụng. Một thư viện có thể tương thích nhị phân với các lời gọi phổ biến nhưng vẫn phát sinh lỗi ở một nhánh ít được chạy, khi class được nạp động hoặc khi một dependency khác phiên bản xuất hiện.

Một số giới hạn cần lưu ý:

1. **Chỉ kiểm tra các tham chiếu thực sự có trong binary.** Một class hoặc method được gọi qua reflection, cấu hình, tên chuỗi hoặc plugin có thể không được thể hiện như lời gọi thông thường trong bytecode.
2. **Classpath và dependency bắc cầu vẫn quan trọng.** Một binary liên kết được với thư viện A nhưng có thể thất bại nếu thư viện B mà A phụ thuộc bị thay đổi hoặc bị nạp sai phiên bản.
3. **Class loader có thể làm thay đổi class được tìm thấy.** Hai class có cùng tên nhưng được nạp bởi class loader khác nhau không nhất thiết là cùng một kiểu trong JVM.
4. **Native code và Java agent có hợp đồng riêng.** JNI/JNA, agent biến đổi bytecode hoặc thư viện gắn với hệ điều hành có thể không tương thích dù API Java bề mặt vẫn giữ nguyên.
5. **Lỗi có thể chỉ xuất hiện khi thực thi một nhánh cụ thể.** Một binary khởi động được chưa chứng minh mọi method, plugin, đường dẫn reflection và luồng xử lý đều liên kết thành công.

Ngoài ra, tương thích nhị phân của một thư viện không đồng nghĩa với tương thích của toàn bộ ứng dụng. Ứng dụng là tổ hợp nhiều thành phần; một dependency cập nhật có thể kéo theo thay đổi ở các dependency khác, cấu hình runtime hoặc dữ liệu được trao đổi giữa các dịch vụ.

## 6. Cách kiểm tra riêng từng loại tương thích khi nâng cấp

Một kế hoạch migration nên xác định rõ binary nào cần tiếp tục chạy, source nào cần biên dịch lại và hành vi nào phải được giữ nguyên. Các bước sau giúp thu thập bằng chứng cho từng câu hỏi.

### Bước 1: Xác định các bên tiêu thụ API

Liệt kê ứng dụng, module, plugin, job nền và dịch vụ đang sử dụng thư viện. Phân biệt thành phần có thể build lại cùng lúc với thành phần chỉ có binary được triển khai độc lập.

Điều này đặc biệt quan trọng khi nâng thư viện dùng chung. Một module có thể được biên dịch lại ngay, nhưng plugin của bên khác hoặc một ứng dụng cũ vẫn đang sử dụng JAR đã phát hành từ trước.

### Bước 2: Kiểm tra tương thích mã nguồn

Biên dịch lại các consumer với JDK, compiler options và dependency phiên bản mục tiêu. Xem xét các lỗi liên quan đến overload, generic, kiểu trả về, quyền truy cập, module và API bị loại bỏ.

Nếu có lỗi, xác định thay đổi nào trong API làm lời gọi cũ không còn hợp lệ. Sửa mã nguồn theo ý nghĩa mong muốn, đồng thời cân nhắc liệu thay đổi API có thể được thiết kế theo cách ít gây gián đoạn hơn hay không.

### Bước 3: Kiểm tra tương thích nhị phân

Nếu cần hỗ trợ các ứng dụng đã biên dịch, hãy thử chạy artifact cũ với dependency mới trong môi trường tương ứng. Kiểm tra các lỗi liên kết như:

- `NoSuchMethodError`: bytecode yêu cầu method nhưng JVM không tìm thấy descriptor tương ứng.
- `NoSuchFieldError`: field mà bytecode tham chiếu không còn tồn tại với tên và descriptor cần thiết.
- `AbstractMethodError`: một lời gọi method không tìm được phần triển khai phù hợp tại runtime.
- `IncompatibleClassChangeError`: cấu trúc hoặc cách sử dụng class/member không còn phù hợp với binary đã biên dịch.
- `UnsupportedClassVersionError`: JVM đang chạy không hỗ trợ phiên bản class file của class được nạp.

Các công cụ phân tích API như Revapi hoặc japicmp có thể hỗ trợ so sánh hai phiên bản thư viện để phát hiện thay đổi có khả năng phá vỡ tương thích. Kết quả phân tích cần được đối chiếu với cách ứng dụng thực sự sử dụng API; công cụ không thể tự chứng minh mọi đường chạy đều an toàn.

### Bước 4: Kiểm tra tương thích hành vi

Xác định các hợp đồng cần giữ nguyên trước khi chạy thử: đầu vào hợp lệ, đầu vào biên, kết quả mong đợi, ngoại lệ, tác dụng phụ, thứ tự xử lý, định dạng dữ liệu, timeout và yêu cầu hiệu năng.

Tạo regression test hoặc contract test cho các hợp đồng đó. Với một dịch vụ tính phí, chẳng hạn, cần kiểm tra quy tắc làm tròn, đơn vị tiền tệ, mức phí, trường hợp số tiền nhỏ và giá trị biên; chỉ kiểm tra method trả về một `long` là chưa đủ.

Khi có thể, chạy cùng bộ dữ liệu trên phiên bản cũ và mới rồi so sánh kết quả. Nếu khác biệt là chủ ý, ghi nhận thay đổi hợp đồng và cập nhật các consumer phụ thuộc vào hành vi mới.

### Bước 5: Đánh giá ảnh hưởng riêng của JDK và dependency

Nếu một đợt nâng cấp đồng thời thay JDK, framework và nhiều thư viện, khi có lỗi sẽ khó xác định nguyên nhân. Nên ghi lại phiên bản của từng thành phần và chia kiểm tra theo nhóm thay đổi. Với ứng dụng quan trọng, có thể giữ nguyên dependency để thử JDK mới trước, sau đó nâng dependency theo từng nhóm có kiểm soát.

Đồng thời kiểm tra các yếu tố runtime như charset, timezone, TLS, JVM flags, garbage collector và giới hạn container. Những thay đổi này có thể làm thay đổi hành vi ngay cả khi API của ứng dụng không thay đổi.

### Bước 6: Triển khai thử và theo dõi

Triển khai trên staging hoặc một nhóm instance nhỏ với cấu hình gần production. Theo dõi lỗi biên dịch, lỗi liên kết, exception nghiệp vụ, sai lệch dữ liệu, tỷ lệ request thất bại, độ trễ và tài nguyên. Giữ sẵn artifact cùng cấu hình cũ để có thể rollback nếu phát hiện khác biệt vượt ngưỡng chấp nhận.

| Câu hỏi cần xác nhận | Bằng chứng phù hợp |
|---|---|
| Source cũ có biên dịch lại được không? | Kết quả compile của các consumer với compiler và API mục tiêu. |
| Binary cũ có tiếp tục chạy được không? | Kiểm thử artifact đã biên dịch với dependency và runtime mới; phân tích API diff. |
| Hành vi có được giữ nguyên không? | Regression test, contract test, so sánh dữ liệu và kiểm thử tải. |
| Toàn bộ hệ thống có vận hành ổn định không? | Staging/canary, log, metric, tracing và theo dõi lỗi thực tế. |

## 7. Những nhầm lẫn thường gặp

**“Không có `NoSuchMethodError` thì đã tương thích.”** Không có lỗi liên kết chỉ là một tín hiệu về binary trên những đường chạy đã được thực hiện. Mã nguồn có thể vẫn không biên dịch được, và hành vi vẫn có thể thay đổi.

**“Thêm method mới luôn an toàn vì không xóa API cũ.”** Giữ method cũ có thể duy trì liên kết nhị phân, nhưng overload mới có thể làm mã nguồn trở nên mơ hồ hoặc thay đổi lựa chọn overload ở những lần biên dịch mới.

**“Cùng chữ ký Java thì cùng hành vi.”** Chữ ký mô tả cách gọi ở mức kiểu. Nó không mô tả đầy đủ thuật toán, quy tắc nghiệp vụ, ngoại lệ, tác dụng phụ, thứ tự hoặc hiệu năng.

**“Build thành công chứng minh các binary đã phát hành đều chạy được.”** Build thường tạo binary mới. Nó không tự kiểm tra mọi artifact cũ còn đang được triển khai, plugin độc lập hoặc consumer không có trong workspace hiện tại.

**“Một bộ unit test thành công chứng minh tương thích hoàn toàn.”** Unit test chỉ bao phủ những trường hợp đã viết. Cần kết hợp phân tích API, kiểm thử tích hợp, contract test và quan sát trên môi trường gần production.

## 8. Kết luận

Tương thích nhị phân, tương thích mã nguồn và tương thích hành vi trả lời ba câu hỏi khác nhau. Binary compatibility cho biết bytecode đã biên dịch có tiếp tục liên kết được với API mới hay không. Source compatibility cho biết mã nguồn có thể được compiler chấp nhận khi build lại hay không. Behavioral compatibility cho biết chương trình còn tạo ra kết quả, ngoại lệ và tác động phù hợp với hợp đồng mà hệ thống mong đợi hay không.

Một thay đổi có thể giữ nguyên method descriptor nhưng làm mã nguồn trở nên mơ hồ, thay đổi kiểu generic mà compiler nhìn thấy, hoặc thay đổi kết quả nghiệp vụ. Ngược lại, mã nguồn có thể biên dịch lại nhờ chuyển đổi kiểu nhưng binary cũ lại không tìm thấy descriptor mà nó đã tham chiếu. Vì vậy, migration JDK hoặc dependency cần kiểm tra riêng từng lớp: biên dịch source, chạy binary đã phát hành và xác nhận hành vi bằng kiểm thử cùng dữ liệu đại diện. Chỉ khi cả ba nhóm bằng chứng đáp ứng yêu cầu của hệ thống, mới có cơ sở kết luận nâng cấp tương thích.
