# Tương thích nhị phân: chạy thành phần đã biên dịch mà không biên dịch lại

Trong nhóm **Các loại tương thích** của chủ đề **Java Advance Compatibility Migration**, tương thích nhị phân (binary compatibility) trả lời một câu hỏi rất thực tế: sau khi một thư viện Java được nâng cấp, chương trình đã biên dịch với phiên bản cũ có tiếp tục chạy được với phiên bản mới mà không cần biên dịch lại hay không?

Đây là yêu cầu quan trọng khi phát hành thư viện dùng chung, plugin, SDK, framework hoặc các thành phần được triển khai độc lập. Một ứng dụng có thể đã được đóng gói thành JAR và đang chạy ở môi trường khác; nhà cung cấp thư viện vẫn cần nâng cấp thư viện mà không buộc mọi ứng dụng tiêu thụ phải biên dịch lại ngay lập tức.

## 1. Hiểu đúng về tương thích nhị phân

Một phiên bản thư viện mới có **tương thích nhị phân ngược** với phiên bản cũ khi các chương trình đã được biên dịch với thư viện cũ vẫn có thể được JVM nạp, liên kết và thực thi khi thay thư viện cũ bằng thư viện mới, trong cùng điều kiện runtime phù hợp.

Luồng điển hình:

~~~text
Thư viện phiên bản 1
        |
        v
Biên dịch ứng dụng Client
        |
        v
Client.class / client.jar
        |
        |  Thay thư viện phiên bản 1 bằng phiên bản 2
        v
Thư viện phiên bản 2 + Client.class cũ
        |
        v
JVM nạp, liên kết và chạy
~~~

Điểm cốt lõi là file class của Client vẫn giữ nguyên. JVM phải tìm được những lớp, trường và phương thức mà bytecode cũ tham chiếu đến.

Cần phân biệt một số khái niệm:

| Loại tương thích | Câu hỏi cần trả lời |
|---|---|
| Tương thích nhị phân (binary compatibility) | Bytecode đã biên dịch có tiếp tục liên kết và chạy với phiên bản mới không? |
| Tương thích mã nguồn (source compatibility) | Mã nguồn cũ có biên dịch được khi dùng phiên bản mới không? |
| Tương thích hành vi (behavioral compatibility) | Chương trình có tiếp tục cho kết quả và tác dụng như trước không? |
| Tương thích dữ liệu (data compatibility) | Dữ liệu đã lưu, serialized object hoặc schema cũ có tiếp tục đọc/ghi được không? |
| Tương thích giao thức (protocol compatibility) | Các thành phần giao tiếp qua HTTP, message hoặc wire protocol có hiểu nhau không? |

Một thay đổi có thể tương thích nhị phân nhưng không tương thích mã nguồn hoặc hành vi. Ví dụ, thêm một overload thường không làm hỏng bytecode cũ, nhưng có thể khiến một lời gọi trong mã nguồn cũ trở nên mơ hồ khi biên dịch lại. Tương tự, thay đổi giá trị trả về của một phương thức vẫn giữ nguyên chữ ký nhị phân có thể làm thay đổi hành vi của ứng dụng.

Trong bài này, hướng tương thích được xét chủ yếu là **thư viện mới chạy cùng client đã biên dịch với thư viện cũ**. Chiều ngược lại — client mới chạy với thư viện cũ — là một yêu cầu khác và không tự động được bảo đảm.

## 2. Vì sao JVM có thể chạy bytecode cũ?

Khi biên dịch mã Java, **javac** chuyển mã nguồn thành bytecode trong file **.class**. Bytecode không chỉ chứa các lệnh thực thi; nó còn có constant pool lưu các tham chiếu ký hiệu đến lớp, phương thức, trường và các kiểu dữ liệu liên quan.

Ví dụ, client gọi:

~~~java
printer.print("Hello");
~~~

Trong bytecode, lời gọi này được biểu diễn bằng một tham chiếu đến lớp sở hữu phương thức, tên phương thức và descriptor của phương thức. Khi chạy, JVM dùng thông tin đó để tìm thành viên tương ứng trong các class đã được nạp.

Một method descriptor mô tả danh sách kiểu tham số và kiểu trả về. Ví dụ:

~~~text
(Ljava/lang/String;I)Ljava/lang/String;
~~~

Descriptor này có nghĩa là phương thức nhận một **String**, một **int** và trả về một **String**.

Một số descriptor thường gặp:

| Kiểu Java | Ký hiệu trong descriptor |
|---|---|
| **int** | **I** |
| **long** | **J** |
| **boolean** | **Z** |
| **void** | **V** |
| **String** | **Ljava/lang/String;** |
| **int[]** | **[I** |
| **String[]** | **[Ljava/lang/String;** |

Vì descriptor là một phần của tham chiếu nhị phân, hai phương thức cùng tên nhưng khác tham số là hai phương thức khác nhau ở mức bytecode. Kiểu trả về cũng nằm trong descriptor của JVM. Do đó, đổi kiểu trả về có thể làm thay đổi tham chiếu mà client cũ cần tìm.

Các lệnh bytecode thường gặp khi truy cập thành viên gồm:

- **invokevirtual**: gọi phương thức instance theo cơ chế dispatch động.
- **invokeinterface**: gọi phương thức thông qua interface.
- **invokestatic**: gọi phương thức static.
- **invokespecial**: dùng cho một số lời gọi đặc biệt như constructor, phương thức private hoặc lời gọi **super**.
- **getfield** và **putfield**: đọc, ghi trường instance.
- **getstatic** và **putstatic**: đọc, ghi trường static.

Khi JVM liên kết một tham chiếu, nó phải xác định được thành viên phù hợp và kiểm tra các điều kiện như loại thành viên, quyền truy cập và cấu trúc kế thừa. Nếu thư viện mới không còn đáp ứng tham chiếu mà bytecode cũ đã ghi lại, lỗi có thể chỉ xuất hiện lúc chạy.

### Generic và type erasure

Java generic chủ yếu được kiểm tra ở thời điểm biên dịch. JVM thường làm việc với kiểu đã xóa (erasure). Ví dụ, **List<String>** và **List<Integer>** đều có dạng runtime là **List**.

~~~java
public String find(List<String> values) {
    return values.get(0);
}
~~~

Tham số generic không làm descriptor runtime trở thành một kiểu **List<String>** riêng. Vì vậy, thay đổi tham số generic nhưng giữ nguyên kiểu sau erasure có thể vẫn tương thích nhị phân, trong khi mã nguồn biên dịch lại có thể phát sinh lỗi hoặc cảnh báo khác. Nếu thay đổi làm thay đổi erasure, descriptor có thể thay đổi và client cũ có thể không liên kết được.

Thông tin generic vẫn có thể được công cụ reflection đọc từ metadata của class, nên tương thích nhị phân không đồng nghĩa mọi hành vi reflection đều giữ nguyên.

## 3. Những thay đổi thường giữ được tương thích nhị phân

Nguyên tắc an toàn là giữ nguyên các thành viên mà client cũ đã tham chiếu, đồng thời bổ sung khả năng mới theo cách không làm mất đường liên kết cũ.

| Thay đổi | Tác động nhị phân thường gặp | Điều cần chú ý |
|---|---|---|
| Thêm một lớp mới | Thường tương thích | Không được làm thay đổi lớp cũ mà client đang dùng. |
| Thêm một phương thức mới | Thường tương thích | Cần xem xét interface, lớp con và dispatch động. |
| Thêm một overload | Thường tương thích với bytecode cũ | Mã nguồn biên dịch lại có thể bị mơ hồ khi overload mới cùng tham gia chọn phương thức. |
| Thêm một trường mới | Thường tương thích | Cần kiểm tra tên và kiểu trường không xung đột với cách dùng hiện tại. |
| Thay phần thân phương thức nhưng giữ nguyên chữ ký | Thường tương thích nhị phân | Có thể phá vỡ tương thích hành vi nếu đổi kết quả, ngoại lệ hoặc tác dụng phụ. |
| Bổ sung phương thức **default** cho interface | Thường an toàn hơn việc thêm phương thức abstract | Có thể phát sinh xung đột nếu nhiều interface cung cấp các default method không thể phân giải. |
| Bổ sung annotation hoặc metadata | Thường không đổi descriptor | Reflection, framework hoặc bộ xử lý annotation có thể quan sát được thay đổi. |

Các nhận định trên là quy tắc thực hành, không phải lời bảo đảm cho mọi hệ thống. Cần xem xét cả cây kế thừa, interface mà client triển khai, cách framework tìm thành viên và hành vi reflection.

### Thêm overload: bytecode cũ và mã nguồn mới có thể cho kết quả khác nhau

Giả sử phiên bản 1 có:

~~~java
public class MessageFormatter {
    public String format(String value) {
        return "[" + value + "]";
    }
}
~~~

Phiên bản 2 bổ sung:

~~~java
public String format(Object value) {
    return String.valueOf(value);
}
~~~

Bytecode cũ đã tham chiếu đến **format(String)** với descriptor cụ thể. Khi chạy với phiên bản 2, JVM vẫn có thể tìm đúng phương thức đó.

Tuy nhiên, nếu mã nguồn cũ được biên dịch lại, quy tắc chọn overload của trình biên dịch sẽ được áp dụng lại. Với các lời gọi có kiểu tham số phức tạp, **null**, generic hoặc kiểu được suy luận, overload mới có thể làm thay đổi kết quả chọn phương thức hoặc khiến lời gọi trở nên mơ hồ.

Vì vậy, kiểm tra source compatibility và binary compatibility cần được thực hiện riêng.

## 4. Những thay đổi dễ phá vỡ tương thích nhị phân

Các thay đổi sau thường phá vỡ tham chiếu đã được ghi trong bytecode cũ:

| Thay đổi | Hậu quả có thể gặp khi chạy client cũ |
|---|---|
| Xóa hoặc đổi tên lớp | **NoClassDefFoundError** |
| Xóa hoặc đổi tên phương thức | **NoSuchMethodError** |
| Đổi kiểu tham số hoặc kiểu trả về làm thay đổi descriptor | **NoSuchMethodError** |
| Xóa hoặc đổi tên trường | **NoSuchFieldError** |
| Đổi trường hoặc phương thức giữa **static** và instance | **IncompatibleClassChangeError** |
| Thu hẹp quyền truy cập của thành viên mà client cũ truy cập | **IllegalAccessError** |
| Đổi một kiểu từ class thành interface hoặc ngược lại | **IncompatibleClassChangeError** |
| Làm thay đổi cấu trúc kế thừa hoặc cách phân giải phương thức không tương thích | Có thể gặp **AbstractMethodError**, **IncompatibleClassChangeError** hoặc lỗi liên kết khác |
| Xóa constructor mà client cũ đang gọi | **NoSuchMethodError** |

### Xóa hoặc đổi chữ ký phương thức

Phiên bản 1:

~~~java
public class PaymentService {
    public Receipt pay(long amount) {
        return new Receipt(amount);
    }
}
~~~

Một client được biên dịch với phiên bản này sẽ tham chiếu đến phương thức **pay(long)** và kiểu trả về **Receipt**.

Nếu phiên bản 2 chỉ còn:

~~~java
public class PaymentService {
    public Receipt pay(String amount) {
        return new Receipt(Long.parseLong(amount));
    }
}
~~~

thì phương thức cũ đã biến mất khỏi API nhị phân. Việc có một phương thức cùng tên không giúp JVM liên kết lại, vì descriptor khác nhau. Client cũ có thể ném **NoSuchMethodError**.

Cách di chuyển an toàn hơn là giữ phương thức cũ và chuyển tiếp sang API mới:

~~~java
public class PaymentService {
    public Receipt pay(long amount) {
        return pay(String.valueOf(amount));
    }

    public Receipt pay(String amount) {
        return new Receipt(Long.parseLong(amount));
    }
}
~~~

Phương thức cũ có thể được đánh dấu **@Deprecated** để báo cho người dùng biết hướng di chuyển. Chỉ xóa nó khi đã có kế hoạch phát hành phiên bản phá vỡ tương thích và chấp nhận yêu cầu biên dịch lại từ các client.

### Đổi quyền truy cập

Nếu phiên bản cũ cung cấp phương thức **public** nhưng phiên bản mới đổi thành **private**, bytecode cũ vẫn có tham chiếu đến phương thức đó. Khi JVM kiểm tra quyền truy cập, client có thể gặp **IllegalAccessError**.

Đổi **public** thành **protected** hoặc package-private cũng cần được xem là thay đổi có nguy cơ phá vỡ client nằm ngoài phạm vi truy cập mới. Đừng dựa vào việc một client cụ thể tình cờ nằm cùng package hoặc cùng module để kết luận API vẫn tương thích.

### Đổi class và interface

Class và interface có vai trò khác nhau trong bytecode và quá trình phân giải lời gọi. Một client đã biên dịch để sử dụng một class không thể mặc nhiên thay thế bằng interface cùng tên. Thay đổi loại khai báo này có thể dẫn đến **IncompatibleClassChangeError**.

Tương tự, thay đổi quan hệ kế thừa có thể làm thay đổi phương thức được kế thừa, phương thức bị override hoặc cách JVM phân giải lời gọi. Những thay đổi này cần được kiểm tra trên các client và lớp triển khai thực tế.

## 5. Tiến hóa interface và abstract class

Interface thường là ranh giới mở rộng được nhiều nhóm hoặc module triển khai độc lập. Vì vậy, thay đổi interface cần được xem xét cẩn thận hơn thay đổi một lớp chỉ do một ứng dụng sở hữu.

### Thêm abstract method vào interface

Giả sử phiên bản 1 có:

~~~java
public interface Storage {
    void save(String value);
}
~~~

Một module khác đã biên dịch lớp triển khai:

~~~java
public class FileStorage implements Storage {
    @Override
    public void save(String value) {
        // Ghi dữ liệu xuống file
    }
}
~~~

Phiên bản 2 thêm phương thức abstract:

~~~java
public interface Storage {
    void save(String value);
    String read(String key);
}
~~~

Lớp **FileStorage** cũ có thể vẫn được JVM nạp, nhưng nó không có phần triển khai cho **read**. Nếu chương trình gọi phương thức mới trên đối tượng đó, JVM có thể ném **AbstractMethodError**.

Nếu biên dịch lại **FileStorage** với interface mới, trình biên dịch sẽ yêu cầu lớp cung cấp triển khai phù hợp, trừ khi lớp được thiết kế theo cách khác để đáp ứng hợp đồng mới.

### Dùng default method khi cần bổ sung hành vi mặc định

Với Java 8 trở lên, interface có thể khai báo **default** method:

~~~java
public interface Storage {
    void save(String value);

    default String read(String key) {
        throw new UnsupportedOperationException("read is not supported");
    }
}
~~~

Một triển khai cũ không cần thêm ngay phương thức **read** chỉ để thỏa mãn hợp đồng nhị phân mới; JVM có thể sử dụng phần triển khai mặc định.

Tuy nhiên, **default** không giải quyết mọi trường hợp. Nếu một lớp kế thừa nhiều interface có các default method cùng chữ ký mà không có quy tắc phân giải phù hợp, xung đột có thể xảy ra. Lớp triển khai cần override để xác định hành vi rõ ràng. Một default method mới cũng có thể làm thay đổi phương thức được chọn trong các cấu trúc kế thừa phức tạp.

### Thêm abstract method vào abstract class

Một abstract class có thể được mở rộng bởi lớp đã biên dịch ở module khác. Nếu phiên bản mới thêm abstract method, lớp con cũ có thể chưa triển khai phương thức đó. Khi một đường gọi thực tế yêu cầu phương thức chưa được triển khai, chương trình có thể gặp **AbstractMethodError**.

Do đó, khi cần thêm hành vi vào một abstract class được nhiều bên mở rộng, hãy cân nhắc một phương thức cụ thể có triển khai mặc định, một hook không bắt buộc hoặc một interface capability riêng. Chỉ thêm abstract method khi có thể yêu cầu và kiểm soát việc cập nhật tất cả lớp con.

## 6. Hằng số compile-time và thay đổi hành vi

Một trường **public static final** có kiểu nguyên thủy hoặc **String** và được khởi tạo bằng biểu thức hằng số tại compile time có thể được trình biên dịch nhúng trực tiếp vào bytecode của client.

Ví dụ, thư viện phiên bản 1:

~~~java
public class RetryPolicy {
    public static final int MAX_RETRIES = 3;
}
~~~

Client:

~~~java
System.out.println(RetryPolicy.MAX_RETRIES);
~~~

Sau khi biên dịch, bytecode của client có thể chứa trực tiếp giá trị **3**, thay vì đọc trường từ thư viện lúc chạy. Nếu thư viện phiên bản 2 đổi giá trị thành **5**, client cũ vẫn có thể tiếp tục dùng giá trị **3** cho đến khi được biên dịch lại.

Đây không nhất thiết là lỗi liên kết nhị phân: client vẫn chạy được, nhưng dữ liệu mà nó sử dụng đã cũ. Nếu giá trị cần thay đổi độc lập với vòng đời biên dịch của client, nên cung cấp một phương thức hoặc cấu hình runtime:

~~~java
public final class RetryPolicy {
    private RetryPolicy() {
    }

    public static int maxRetries() {
        return 5;
    }
}
~~~

Cần phân biệt hằng số compile-time với trường **static final** được khởi tạo bằng đối tượng hoặc lời gọi phương thức. Không phải mọi trường **static final** đều được nhúng vào bytecode client.

Ngoài ra, giữ nguyên chữ ký chỉ bảo đảm khả năng liên kết ở mức nhị phân. Nếu đổi phần thân phương thức, client cũ vẫn có thể chạy nhưng nhận kết quả khác, phát sinh ngoại lệ mới, thay đổi thứ tự tác dụng phụ hoặc vi phạm giả định mà client dựa vào. Vì thế, tương thích nhị phân là điều kiện cần cho nâng cấp an toàn, không phải bằng chứng rằng hành vi không đổi.

## 7. Thực hành: chạy client đã biên dịch với thư viện mới

Ví dụ này mô phỏng việc thay thư viện nhưng giữ nguyên file class của client.

### Bước 1: Tạo thư viện phiên bản 1

Tạo lớp **Greeting**:

~~~java
package com.example.api;

public class Greeting {
    public String greet(String name) {
        return "Xin chao " + name;
    }
}
~~~

Biên dịch và đóng gói:

~~~bash
javac -d out-v1 src-v1/com/example/api/Greeting.java
jar --create --file greeting-v1.jar -C out-v1 .
~~~

### Bước 2: Biên dịch client đúng một lần với phiên bản 1

Tạo **Client.java**:

~~~java
import com.example.api.Greeting;

public class Client {
    public static void main(String[] args) {
        Greeting greeting = new Greeting();
        System.out.println(greeting.greet("An"));
    }
}
~~~

Biên dịch client bằng thư viện phiên bản 1:

~~~bash
javac -cp greeting-v1.jar -d client-out Client.java
~~~

Từ thời điểm này, **client-out/Client.class** là bytecode đã biên dịch. Ta sẽ giữ nguyên file này trong các bước tiếp theo.

### Bước 3: Tạo thư viện phiên bản 2 nhưng giữ API cũ

Phiên bản 2 bổ sung phương thức mới, đồng thời giữ nguyên **greet(String)**:

~~~java
package com.example.api;

public class Greeting {
    public String greet(String name) {
        return "Xin chao " + name;
    }

    public String greet(String name, String language) {
        if ("en".equals(language)) {
            return "Hello " + name;
        }
        return greet(name);
    }

    public String version() {
        return "2";
    }
}
~~~

Biên dịch và đóng gói thư viện mới:

~~~bash
javac -d out-v2 src-v2/com/example/api/Greeting.java
jar --create --file greeting-v2.jar -C out-v2 .
~~~

### Bước 4: Chạy client cũ với thư viện mới

Không chạy lại **javac** cho **Client.java**. Chỉ thay JAR thư viện trong classpath:

~~~bash
# Windows
java -cp "greeting-v2.jar;client-out" Client

# Linux hoặc macOS
java -cp "greeting-v2.jar:client-out" Client
~~~

Kết quả:

~~~text
Xin chao An
~~~

Client đã được biên dịch với phiên bản 1 vẫn chạy với phiên bản 2 vì phương thức mà bytecode cũ tham chiếu đến vẫn tồn tại với descriptor tương ứng.

Nếu phiên bản 2 xóa **greet(String)** và chỉ giữ **greet(String, String)**, client cũ có thể ném **NoSuchMethodError**. Việc phương thức mới có tên gần giống hoặc có thể thực hiện cùng nghiệp vụ không giúp JVM tự chuyển lời gọi cũ sang chữ ký mới.

### Bước 5: Quan sát bytecode

Có thể dùng **javap** để xem descriptor và lời gọi mà client đã biên dịch:

~~~bash
javap -classpath greeting-v1.jar -s com.example.api.Greeting
javap -classpath client-out -c -verbose Client
~~~

Lệnh đầu hiển thị chữ ký và descriptor của các thành viên trong thư viện. Lệnh thứ hai hiển thị bytecode của client, bao gồm tham chiếu đến phương thức được gọi. Sau khi thay JAR, có thể chạy lại **javap** trên thư viện phiên bản 2 để kiểm tra xem thành viên cũ còn được cung cấp hay không.

Thực hành này chứng minh một điểm quan trọng: kiểm tra biên dịch thành công với thư viện mới chưa đủ. Muốn kiểm tra tương thích nhị phân, cần giữ lại bytecode được tạo từ thư viện cũ và thực sự chạy nó với thư viện mới.

## 8. Kiểm tra tương thích nhị phân trong dự án

Một quy trình kiểm tra có thể tổ chức theo các bước sau:

1. **Chốt phiên bản nền:** lưu lại artifact thư viện cũ đã phát hành, đúng phiên bản mà client đang sử dụng. Không dùng một bản build cũ đã bị thay đổi nội dung.
2. **So sánh API công khai:** kiểm tra class, interface, constructor, method, field, descriptor, quyền truy cập và quan hệ kế thừa giữa hai phiên bản.
3. **Chạy client đã biên dịch trước đó:** biên dịch một bộ client kiểm thử với thư viện cũ, sau đó chạy nguyên bytecode đó với thư viện mới.
4. **Kiểm tra các điểm mở rộng:** thử các lớp triển khai interface, lớp con của abstract class, plugin, reflection và service provider nếu thư viện hỗ trợ các cơ chế này.
5. **Kiểm tra môi trường runtime:** xác nhận phiên bản JDK, dependency, module path/classpath và class loader phù hợp.
6. **Đánh giá hành vi:** kiểm tra kết quả, ngoại lệ, tác dụng phụ và dữ liệu đầu ra. Đây là lớp kiểm tra riêng bên cạnh kiểm tra liên kết nhị phân.

Các công cụ như **Revapi** hoặc **japicmp** có thể giúp so sánh API giữa hai artifact và phát hiện nhiều thay đổi không tương thích. Chúng hỗ trợ việc rà soát tự động, nhưng không thay thế bài kiểm thử chạy client cũ với thư viện mới, đặc biệt khi dự án có plugin, reflection, class loader tùy chỉnh hoặc hành vi phụ thuộc runtime.

### Đừng nhầm API nhị phân với phiên bản class file

Một thư viện có thể giữ nguyên toàn bộ API nhưng được biên dịch bằng JDK mới hơn và tạo ra class file mà JVM cũ không hiểu. Khi đó, ứng dụng có thể gặp **UnsupportedClassVersionError**.

Ví dụ, client không cần biên dịch lại về mặt API, nhưng JVM đang chạy vẫn phải hỗ trợ phiên bản bytecode của thư viện mới. Cần kiểm tra target release khi biên dịch, phiên bản JDK triển khai, các API JDK mà thư viện sử dụng và dependency đi kèm.

Classpath cũng ảnh hưởng đến kết quả. Nếu runtime vô tình nạp một JAR cũ, một bản trùng lớp hoặc một dependency không tương thích, kết quả có thể khác với môi trường kiểm thử. Hãy xác nhận chính xác artifact và thứ tự nạp lớp khi điều tra lỗi.

## 9. Chiến lược migration để giữ client cũ hoạt động

Khi API cần thay đổi, một chiến lược theo giai đoạn giúp giảm rủi ro cho các module tiêu thụ độc lập.

### Giai đoạn 1: Mở rộng API

Thêm API mới nhưng giữ nguyên API cũ. Nếu cần, phương thức cũ chuyển tiếp sang phương thức mới để chỉ duy trì một nơi xử lý nghiệp vụ.

~~~java
public class CustomerService {
    public Customer findById(long id) {
        return findById(String.valueOf(id));
    }

    public Customer findById(String id) {
        // Triển khai cách tìm mới
        return loadCustomer(id);
    }

    private Customer loadCustomer(String id) {
        // Truy xuất dữ liệu
        return new Customer(id);
    }
}
~~~

### Giai đoạn 2: Thông báo và di chuyển người dùng

Đánh dấu API cũ bằng **@Deprecated**, ghi rõ API thay thế, lý do thay đổi và thời điểm dự kiến loại bỏ nếu đã có chính sách cụ thể.

~~~java
@Deprecated(since = "2.0", forRemoval = true)
public Customer findById(long id) {
    return findById(String.valueOf(id));
}
~~~

Người dùng có thể di chuyển mã nguồn theo lịch của họ. Trong giai đoạn này, các client chưa được biên dịch lại vẫn tiếp tục gọi được phương thức cũ.

### Giai đoạn 3: Loại bỏ trong phiên bản phá vỡ tương thích

Chỉ xóa API cũ khi đã chấp nhận rõ ràng yêu cầu nâng cấp client. Ghi nhận thay đổi trong release notes, chỉ dẫn migration và chính sách phiên bản. Với thư viện có nhiều nhóm tiêu thụ, cần tính đến thời gian phát hành độc lập của các module đó.

Một adapter hoặc bridge method nhỏ có thể là chi phí thấp để duy trì tương thích trong thời gian dài. Xóa một chữ ký cũ có thể tiết kiệm ít mã nguồn nhưng tạo ra chi phí nâng cấp lớn cho toàn bộ hệ sinh thái.

## 10. Đọc lỗi liên kết thường gặp

Khi client cũ chạy với thư viện mới, thông báo lỗi của JVM thường giúp khoanh vùng loại thay đổi:

| Lỗi | Ý nghĩa thường gặp | Hướng kiểm tra |
|---|---|---|
| **NoClassDefFoundError** | JVM cần một lớp nhưng không tìm thấy hoặc không thể sử dụng lớp đó trong quá trình liên kết/khởi tạo | Kiểm tra JAR, classpath, dependency và quá trình khởi tạo lớp. |
| **NoSuchMethodError** | Không tìm thấy phương thức với tên và descriptor mà bytecode yêu cầu | So sánh tên, tham số, kiểu trả về và artifact đang được nạp. |
| **NoSuchFieldError** | Không tìm thấy trường mà bytecode yêu cầu | Kiểm tra tên, kiểu trường và phiên bản thư viện thực tế. |
| **AbstractMethodError** | Đường gọi yêu cầu một phương thức abstract nhưng đối tượng runtime không có phần triển khai cụ thể phù hợp | Kiểm tra interface, abstract class và các lớp triển khai cũ. |
| **IllegalAccessError** | Thành viên tồn tại nhưng client không có quyền truy cập theo cấu trúc runtime hiện tại | Kiểm tra access modifier, module export và ranh giới package/module. |
| **IncompatibleClassChangeError** | Loại thành viên hoặc cấu trúc class/interface không khớp với giả định đã ghi trong bytecode | Kiểm tra thay đổi static/instance, class/interface và cấu trúc kế thừa. |
| **UnsupportedClassVersionError** | JVM hiện tại không hỗ trợ phiên bản class file được biên dịch | Kiểm tra JDK chạy ứng dụng và target bytecode. |

**ClassNotFoundException** và **NoClassDefFoundError** không giống nhau. **ClassNotFoundException** thường xuất hiện khi mã gọi API nạp lớp như **Class.forName** hoặc **ClassLoader.loadClass** không tìm thấy lớp theo yêu cầu. **NoClassDefFoundError** là lỗi liên kết ở runtime khi JVM cần một định nghĩa lớp mà không thể cung cấp. Khi điều tra, cần đọc cả nguyên nhân gốc (cause) và kiểm tra artifact thực tế trên runtime.

## 11. Checklist trước khi phát hành phiên bản mới

Trước khi thay một thư viện đã được nhiều client sử dụng, hãy kiểm tra:

- [ ] Các class và interface cũ mà client công khai sử dụng vẫn tồn tại.
- [ ] Các constructor cũ vẫn tồn tại với descriptor cần thiết.
- [ ] Các method và field cũ vẫn có tên, kiểu, descriptor và loại static/instance phù hợp.
- [ ] Quyền truy cập của thành viên cũ không bị thu hẹp.
- [ ] Quan hệ kế thừa và triển khai interface không tạo lỗi phân giải phương thức.
- [ ] Các interface được bổ sung hành vi có chiến lược phù hợp cho lớp triển khai cũ.
- [ ] Các hằng số compile-time được xem xét về nguy cơ client giữ giá trị cũ.
- [ ] Client đã biên dịch với artifact cũ chạy được với artifact mới.
- [ ] Kết quả và tác dụng phụ quan trọng vẫn đáp ứng hợp đồng hành vi.
- [ ] Phiên bản JDK, class file, dependency, classpath và module path của môi trường triển khai được hỗ trợ.
- [ ] Release notes mô tả rõ API mới, API deprecated và các thay đổi có thể yêu cầu biên dịch lại.

Tương thích nhị phân giúp các thành phần Java được phát hành và nâng cấp độc lập. Để đạt được điều đó, phiên bản mới cần duy trì những tham chiếu mà bytecode cũ phụ thuộc vào, cung cấp lộ trình chuyển đổi cho API cũ và kiểm tra bằng chính các client đã biên dịch từ phiên bản trước.
