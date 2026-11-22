# Exception, stack trace và cách truy nguyên nguyên nhân lỗi

Trong Java và Spring Boot, nhìn thấy dòng **Application run failed**, một HTTP **500 Internal Server Error** hoặc thông báo **Exception in thread "main"** mới chỉ cho biết *hệ thống đã thất bại ở một điểm nào đó*. Để sửa đúng lỗi, bạn cần xác định thao tác gì thất bại, thất bại xảy ra ở đâu, nguyên nhân nào dẫn tới nó, và thành phần nào có trách nhiệm cung cấp dữ liệu hoặc cấu hình bị thiếu.

Ba khái niệm tạo nên nền tảng cho việc điều tra:

- **Exception**: một đối tượng biểu diễn tình huống bất thường trong quá trình thực thi.
- **Stack trace**: chuỗi lời gọi phương thức được ghi nhận khi một đối tượng lỗi được tạo/ghi nhận dấu vết.
- **Cause chain**: các exception liên kết với nhau qua nguyên nhân, thường được in dưới nhãn **Caused by:**.

Spring Boot sử dụng cơ chế exception của Java và các cơ chế xử lý lỗi từ Spring Framework. Vì vậy, khi đọc log Spring Boot, bạn vẫn cần hiểu cách Java ném exception, cách Spring bọc hoặc chuyển đổi exception và cách tìm lại điểm liên quan trong mã ứng dụng.

## 1. Exception là gì?

Khi một phương thức không thể hoàn tất công việc theo hợp đồng, nó có thể ném (throw) một exception. Ví dụ:

~~~java
public int parseQuantity(String rawQuantity) {
    return Integer.parseInt(rawQuantity);
}
~~~

Với chuỗi **"12"**, phương thức trả về số nguyên **12**. Với chuỗi **"abc"**, **Integer.parseInt** ném một **NumberFormatException** vì chuỗi không biểu diễn một số nguyên hợp lệ.

Exception có thể chứa:

| Thành phần | Ý nghĩa |
|---|---|
| **Type** | Lớp exception, ví dụ **NumberFormatException**. |
| **Message** | Thông báo mô tả lỗi, có thể vắng mặt hoặc không đầy đủ. |
| **Stack trace** | Các stack frame xác định những lời gọi phương thức được ghi nhận. |
| **Cause** | Một Throwable khác giải thích nguyên nhân tạo ra exception hiện tại. |
| **Suppressed exceptions** | Các lỗi phụ phát sinh, chẳng hạn khi đóng tài nguyên sau một lỗi chính. |

Exception là một đối tượng trong Java. Một thông báo hiện trên giao diện, một mã HTTP hoặc một dòng log thường chỉ là **cách một tầng của ứng dụng trình bày exception**. Ví dụ, cùng lỗi parse có thể được tầng web chuyển thành HTTP **400 Bad Request** hoặc bị để lan lên thành HTTP **500**, tùy cách ứng dụng xử lý.

### 1.1. Cây kế thừa Throwable

~~~text
java.lang.Throwable
├── java.lang.Error
│   ├── OutOfMemoryError
│   ├── StackOverflowError
│   └── ...
└── java.lang.Exception
    ├── IOException
    ├── SQLException
    ├── ...
    └── java.lang.RuntimeException
        ├── NullPointerException
        ├── IllegalArgumentException
        │   └── NumberFormatException
        ├── IllegalStateException
        ├── IndexOutOfBoundsException
        └── ...
~~~

**Throwable** là lớp nền cho cả **Error** và **Exception**. Nó cung cấp các phương thức như **getMessage()**, **getCause()**, **getStackTrace()** và **printStackTrace()**.

- **Exception** thường đại diện cho những tình huống lỗi mà ứng dụng có thể xử lý hoặc chuyển tiếp.
- **RuntimeException** là một nhánh của Exception không bị ràng buộc bởi quy tắc kiểm tra checked exception của trình biên dịch.
- **Error** thường đại diện cho vấn đề nghiêm trọng ở runtime hoặc môi trường JVM. Thông thường không nên bắt mọi Error rồi cố tiếp tục như không có gì xảy ra.

Tên **Error** không có nghĩa tất cả bug của lập trình viên đều nằm ở nhánh này. Chẳng hạn bug dùng một tham chiếu null thường gây **NullPointerException**, tức là một RuntimeException.

### 1.2. Checked và unchecked exception

| Nhóm | Ví dụ | Trách nhiệm khi biên dịch |
|---|---|---|
| **Checked exception** | **IOException**, **SQLException** | Bên gọi phải bắt hoặc khai báo **throws** nếu exception có thể lan ra ngoài. |
| **Unchecked exception** | **NumberFormatException**, **NullPointerException**, **IllegalArgumentException** | Trình biên dịch không bắt buộc phải bắt hoặc khai báo. |
| **Error** | **OutOfMemoryError**, **StackOverflowError** | Không bắt buộc bắt hoặc khai báo. |

Theo định nghĩa của Java, unchecked throwable gồm **RuntimeException** và các lớp con của nó, cùng **Error** và các lớp con. Các lớp Exception khác không thuộc RuntimeException là checked exception.

Ví dụ checked exception:

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

public String readConfig(Path file) throws IOException {
    return Files.readString(file);
}
~~~

Phương thức **Files.readString** có thể ném IOException; vì vậy **readConfig** khai báo **throws IOException**. Ngược lại, **Integer.parseInt("abc")** có thể ném NumberFormatException mà không yêu cầu khai báo.

**Checked** không đồng nghĩa với “ít nguy hiểm hơn”, và **unchecked** không đồng nghĩa với “có thể bỏ qua”. Cách xử lý vẫn phụ thuộc việc tầng hiện tại có đủ thông tin để phục hồi hay không.

## 2. Exception lan truyền qua các phương thức như thế nào?

Xét lớp:

~~~java
public class OrderCalculator {
    public int calculateTotal(String quantityText, int price) {
        int quantity = parseQuantity(quantityText);
        return quantity * price;
    }

    private int parseQuantity(String quantityText) {
        return Integer.parseInt(quantityText);
    }
}
~~~

Khi gọi:

~~~java
new OrderCalculator().calculateTotal("abc", 100);
~~~

Luồng thực thi:

~~~text
main()
  └─ calculateTotal("abc", 100)
       └─ parseQuantity("abc")
            └─ Integer.parseInt("abc")
                 └─ throw NumberFormatException
~~~

Khi exception được ném, Java tìm khối **catch** phù hợp. Nếu phương thức hiện tại không bắt, exception tiếp tục lan ngược về phương thức đã gọi nó. Quá trình này được gọi là **stack unwinding**. Nếu không được xử lý ở một ranh giới cao hơn, exception có thể kết thúc luồng thực thi hoặc được trình điều phối của framework xử lý.

Một ví dụ bắt lỗi dự kiến:

~~~java
try {
    int total = new OrderCalculator().calculateTotal("abc", 100);
    System.out.println(total);
} catch (NumberFormatException ex) {
    System.out.println("Số lượng phải là số nguyên.");
}
~~~

Trong một ứng dụng Spring MVC, exception thoát khỏi controller thường đi qua hệ thống **HandlerExceptionResolver** và có thể được một **@ExceptionHandler** xử lý. Nếu không có xử lý thích hợp, request có thể nhận phản hồi lỗi server. Do đó, việc một exception được ném **không nhất thiết làm dừng toàn bộ ứng dụng Spring Boot**.

### 2.1. Phân biệt throw, throws, catch và finally

| Cú pháp | Vai trò |
|---|---|
| **throw new IllegalArgumentException("...");** | Ném một exception cụ thể tại thời điểm chạy. |
| **void load() throws IOException** | Khai báo checked exception có thể lan từ phương thức. |
| **catch (IOException ex)** | Bắt và xử lý exception thuộc kiểu phù hợp. |
| **finally { ... }** | Thực hiện công việc dọn dẹp thông thường khi rời try/catch; không phải bảo đảm tuyệt đối nếu JVM bị chấm dứt đột ngột. |

Khi bắt exception, bạn có thể sửa tình huống, chuyển thành kết quả thất bại theo hợp đồng, ném tiếp hoặc bọc lỗi bằng một loại exception có ý nghĩa ở tầng hiện tại. Bắt mà không có một trong những hành động có chủ đích đó thường chỉ che mất vấn đề.

## 3. Stack trace là gì?

Trong mỗi luồng thực thi, JVM lưu dấu các lời gọi phương thức đang hoạt động ở **call stack**. Một **stack trace** của Throwable ghi nhận các stack frame, thường gồm tên lớp, phương thức, file nguồn và số dòng.

Ví dụ minh họa cho đoạn OrderCalculator:

~~~text
java.lang.NumberFormatException: For input string: "abc"
    at java.base/java.lang.NumberFormatException.forInputString(NumberFormatException.java:67)
    at java.base/java.lang.Integer.parseInt(Integer.java:668)
    at java.base/java.lang.Integer.parseInt(Integer.java:786)
    at com.example.orders.OrderCalculator.parseQuantity(OrderCalculator.java:8)
    at com.example.orders.OrderCalculator.calculateTotal(OrderCalculator.java:3)
    at com.example.orders.Main.main(Main.java:6)
~~~

*Số dòng và các frame thuộc Java ở trên chỉ dùng để giải thích cấu trúc; chúng có thể thay đổi theo phiên bản JDK, cách biên dịch và vị trí mã nguồn thực tế.*

### 3.1. Dòng đầu tiên: loại và message

~~~text
java.lang.NumberFormatException: For input string: "abc"
~~~

Phần bên trái dấu hai chấm là **tên lớp exception**, phần bên phải là **message**. Message trong ví dụ cho biết dữ liệu đầu vào là chuỗi **"abc"**. Có những exception không có message hoặc message chỉ nói rất chung chung, vì vậy cần đọc thêm các frame và cause.

### 3.2. Một stack frame chứa gì?

~~~text
at com.example.orders.OrderCalculator.parseQuantity(OrderCalculator.java:8)
~~~

| Phần | Diễn giải |
|---|---|
| **com.example.orders.OrderCalculator** | Tên đầy đủ của lớp. |
| **parseQuantity** | Phương thức nằm trong call stack. |
| **OrderCalculator.java** | File nguồn chứa phương thức khi được biên dịch. |
| **8** | Dòng liên quan trong bản source dùng để build. |

Thông thường, các dòng đầu stack trace nằm gần nơi Throwable ghi nhận dấu vết nhất. Các dòng phía dưới là những phương thức gọi ở tầng trên. Vì vậy thứ tự **hiển thị** từ trên xuống không phải thứ tự **lời gọi diễn ra theo thời gian**.

Ở ví dụ trên, **main** gọi **calculateTotal**, sau đó **parseQuantity** gọi **Integer.parseInt**. Nhưng trace in **Integer.parseInt** trước **parseQuantity**, rồi đến **calculateTotal** và **main**.

Khi điều tra, hãy tìm frame gần nhất nằm trong **package của ứng dụng**:

~~~text
at com.example.orders.OrderCalculator.parseQuantity(OrderCalculator.java:8)
~~~

Đây là vị trí code ứng dụng tương tác trực tiếp với thao tác gây lỗi. Nó chưa chắc là **nguồn gốc của dữ liệu sai**: chuỗi **"abc"** có thể đến từ request, file cấu hình hoặc một bước mapping phía trước.

### 3.3. Giới hạn của stack trace

Stack trace rất hữu ích nhưng không phải nhật ký toàn bộ cuộc đời của request:

- Nó chỉ ghi các frame liên quan đến một thời điểm và một luồng thực thi, không lưu mọi phép gán biến đã xảy ra.
- Logger, hệ thống gom log hoặc nền tảng giám sát có thể cắt bớt thông tin.
- Khi exception được tạo rồi được ném lại sau đó, dấu vết có thể phản ánh lúc exception được khởi tạo/ghi nhận trước đó, không phải toàn bộ các lần ném.
- Một frame có thể hiện **Unknown Source** hoặc **Native Method**, không có dòng Java cụ thể.
- Khi code chuyển sang thread khác, executor hoặc reactive pipeline, trace có thể không chứa toàn bộ chuỗi lời gọi ban đầu.
- Số dòng trong trace phải được đối chiếu với **đúng phiên bản mã nguồn đang chạy**, không nhất thiết là file mới nhất trên máy.

Vì vậy, stack trace là một bằng chứng quan trọng để bắt đầu truy tìm, nhưng đôi khi vẫn cần log trước/sau, giá trị đầu vào, cấu hình, transaction hoặc trace ID.

## 4. Caused by: đọc chuỗi nguyên nhân lồng nhau

Trong ứng dụng lớn, exception thường đi qua nhiều tầng. Một tầng thấp phát sinh lỗi kỹ thuật; tầng cao muốn giải thích lỗi bằng ngôn ngữ phù hợp hơn và bọc nó:

~~~java
public int parseQuantity(String text) {
    try {
        return Integer.parseInt(text);
    } catch (NumberFormatException cause) {
        throw new IllegalArgumentException(
                "quantity phải là số nguyên hợp lệ",
                cause
        );
    }
}
~~~

**IllegalArgumentException** là exception ngoài. **NumberFormatException** được lưu làm **cause** thông qua constructor nhận đối số thứ hai.

Log có thể có dạng:

~~~text
java.lang.IllegalArgumentException: quantity phải là số nguyên hợp lệ
    at com.example.orders.OrderCalculator.parseQuantity(OrderCalculator.java:12)
    at com.example.orders.OrderCalculator.calculateTotal(OrderCalculator.java:3)
    at com.example.orders.Main.main(Main.java:6)
Caused by: java.lang.NumberFormatException: For input string: "abc"
    at java.base/java.lang.NumberFormatException.forInputString(NumberFormatException.java:67)
    at java.base/java.lang.Integer.parseInt(Integer.java:668)
    at com.example.orders.OrderCalculator.parseQuantity(OrderCalculator.java:8)
    ... 2 more
~~~

Hai phần cho biết hai cấp độ:

1. **Lỗi tầng ứng dụng:** một số lượng không đáp ứng hợp đồng đầu vào; ứng dụng ném IllegalArgumentException.
2. **Lỗi kỹ thuật bên dưới:** thao tác parse số thất bại do gặp chuỗi **"abc"**.

Nếu tầng service bọc tiếp IllegalArgumentException trong một exception nghiệp vụ khác, trace sẽ có nhiều đoạn **Caused by:**. Đừng dừng tại exception ngoài cùng khi phần đó chỉ nói “Operation failed” hoặc “Error creating bean”.

### 4.1. Dòng ba chấm có nghĩa gì?

~~~text
... 2 more
~~~

Dấu **... N more** trong cause trace thông thường có nghĩa **N frame cuối trùng với phần stack trace bao ngoài** nên được rút gọn để tránh lặp. Nó không có nghĩa còn N exception khác.

### 4.2. Root cause là gì?

**Root cause** trong một exception chain thường được hiểu là exception sâu nhất được liên kết qua **getCause()**. Có thể lần theo chuỗi như sau:

~~~java
Throwable current = exception;
while (current.getCause() != null && current.getCause() != current) {
    current = current.getCause();
}
System.out.println(current);
~~~

Tuy nhiên, exception sâu nhất **không tự cho biết giải pháp**. Ví dụ, đáy chuỗi là **ConnectException: Connection refused** có thể do:

- Sai địa chỉ hoặc cổng của database.
- Database chưa được khởi động.
- Network policy hoặc firewall chặn kết nối.
- Ứng dụng chạy trong container và sử dụng sai hostname.

Hãy phân biệt:

| Thuật ngữ | Ví dụ |
|---|---|
| **Triệu chứng** | API trả HTTP 500. |
| **Exception ngoài** | Không lấy được danh sách đơn hàng. |
| **Cause kỹ thuật** | ConnectException: Connection refused. |
| **Nguyên nhân cần sửa** | URL database đang trỏ tới địa chỉ không thể kết nối trong môi trường triển khai. |

Đi từ cause đến cách sửa cần thêm bằng chứng về môi trường và cấu hình, tránh kết luận chỉ từ tên class.

## 5. Suppressed khác Caused by thế nào?

Khi có nhiều lỗi trong một lần xử lý, Java có thể lưu lại các exception phụ dưới phần **Suppressed:**. Ví dụ với **try-with-resources**, nếu phần xử lý ném exception và thao tác đóng tài nguyên cũng ném exception, lỗi đóng tài nguyên thường trở thành suppressed exception.

~~~java
try (MyResource resource = openResource()) {
    process(resource); // Thất bại A
} // resource.close() cũng thất bại B
~~~

Dạng trace minh họa:

~~~text
java.lang.IllegalStateException: Không xử lý được dữ liệu
    at com.example.demo.Importer.process(Importer.java:24)
    ...
    Suppressed: java.io.IOException: Không đóng được tài nguyên
        at com.example.demo.MyResource.close(MyResource.java:41)
        ...
~~~

**Caused by** diễn tả quan hệ *exception này được gây ra bởi exception kia*. **Suppressed** giữ lại một exception phát sinh thêm, nhưng không được chọn làm exception chính. Khi điều tra, xem cả hai: nguyên nhân lỗi chính và các tác động phụ có thể cần khắc phục.

## 6. Quy trình truy nguyên lỗi theo bằng chứng

Một cách làm có thể áp dụng cho lỗi Java thuần, lỗi Spring Boot startup và lỗi request:

### Bước 1: Xác định thời điểm thất bại

| Giai đoạn | Ví dụ triệu chứng | Nơi bắt đầu |
|---|---|---|
| **Biên dịch/build** | **cannot find symbol**, **Compilation failed** | Compiler output; đây có thể chưa phải exception runtime. |
| **Khởi động Spring Boot** | **Application run failed**, **Failed to start ApplicationContext** | Exception khởi động, chuỗi Caused by. |
| **Xử lý HTTP request** | HTTP **400**, **404**, **500** | Log của request, exception handler, input. |
| **Job hoặc message consumer** | Task fail, message retry, queue có dead-letter | Log trong job/consumer và nguyên nhân được truyền ra. |

Lỗi biên dịch không thể giải quyết bằng **@ExceptionHandler** vì ứng dụng chưa chạy. Lỗi startup có thể đến từ khởi tạo bean; lỗi request có thể đến từ dữ liệu và logic nghiệp vụ.

### Bước 2: Thu thập đầy đủ sự kiện

Bạn cần biết **hành động nào**, **thời điểm nào**, **môi trường nào** xảy ra lỗi. Với request, ghi nhận endpoint, HTTP method, mã phản hồi và request ID nếu có. Với task nền, ghi tên task, job ID hoặc message ID. Với startup, xem profile và cấu hình được kích hoạt.

Giữ **type, message, stack frame, Caused by và Suppressed**. Nếu chỉ còn một dòng “Internal Server Error” hoặc “Application run failed”, thông tin đang thiếu là cơ sở quan trọng để chẩn đoán.

Khi thu thập input hoặc cấu hình, che **mật khẩu, token, dữ liệu cá nhân và secret**. Không cần ghi bí mật ra log để kiểm tra xem một property có tồn tại.

### Bước 3: Xác định tầng báo lỗi

Đọc exception ngoài cùng để biết:

- **BeanCreationException**: container đang tạo bean và thất bại.
- **UnsatisfiedDependencyException**: một dependency cần thiết không được đáp ứng.
- **DataAccessException**: sự cố được Spring báo ở ranh giới truy cập dữ liệu.
- **HttpMessageNotReadableException**: đọc/chuyển đổi HTTP request body thất bại.
- **IllegalArgumentException**: một điều kiện đầu vào của phương thức không được thỏa mãn.

Đây mới là **định hướng**, không phải kết luận rằng framework hay thư viện tạo ra bug.

### Bước 4: Đi xuống chuỗi Caused by

Tìm exception cụ thể nhất còn xuất hiện và các chi tiết như:

- Tên **property** chưa có.
- Tên **bean** không khởi tạo được.
- Địa chỉ **host:port** không kết nối được.
- Tên **table**, **constraint**, SQL state hoặc thông điệp driver.
- Giá trị **input** sai định dạng.
- Tên **file** hoặc đường dẫn không tìm thấy.

Đừng hiểu **Failed to create bean** là nguyên nhân đủ cụ thể khi phần cause bên dưới còn ghi **Could not resolve placeholder**.

### Bước 5: Tìm frame trong package ứng dụng

Ví dụ:

~~~text
at com.example.payment.PaymentConfig.paymentClient(PaymentConfig.java:31)
~~~

Mở đúng file và phiên bản đang chạy, xem dòng được chỉ ra và những dòng liên quan. Câu hỏi quan trọng: phương thức này **đang làm gì**, nhận input từ đâu và vì sao lại gọi thành phần thấp hơn?

Nếu log có hàng trăm frame thuộc **java.base**, **org.springframework**, **org.hibernate** và server, tìm frame của ứng dụng sẽ giúp nối việc xử lý nội bộ framework với hành động của bạn. Nhưng nếu lỗi bắt nguồn từ cấu hình framework, đừng cố ép nguyên nhân vào một frame ứng dụng không tồn tại.

### Bước 6: Đưa ra giả thuyết kiểm chứng được

Thay vì “Spring Boot lỗi”, hãy hình thành giả thuyết cụ thể:

> “Ứng dụng không tạo được PaymentClient vì môi trường chạy thiếu property payment.api-key.”

Sau đó kiểm tra khai báo property, nguồn cấu hình, biến môi trường và profile. Với dữ liệu sai, tái hiện cùng input; với database, xem kết nối và constraint thực tế.

### Bước 7: Sửa nguyên nhân và tái hiện cùng tình huống

Đánh giá thành công bằng **hành vi đúng** sau thay đổi, không bằng việc log biến mất. Một catch rộng rồi trả HTTP **200** có thể che toàn bộ exception nhưng vẫn làm mất dữ liệu.

## 7. Ví dụ Spring Boot: lỗi tạo bean khi khởi động

Giả sử ứng dụng có bean được tạo từ một property bắt buộc:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class PaymentConfig {
    @Bean
    public PaymentClient paymentClient(
            @Value("${payment.api-key}") String apiKey) {
        return new PaymentClient(apiKey);
    }
}
~~~

**PaymentClient** là lớp ví dụ của ứng dụng. Spring cần giải quyết giá trị **payment.api-key** trước khi có thể gọi factory method tạo bean.

Nếu property không tồn tại trong các nguồn cấu hình khả dụng, log startup có thể có dạng rút gọn:

~~~text
org.springframework.beans.factory.BeanCreationException:
Error creating bean with name 'paymentClient'
    at org.springframework.beans.factory.support...
    ...
Caused by: java.lang.IllegalArgumentException:
Could not resolve placeholder 'payment.api-key'
in value "${payment.api-key}"
    at org.springframework.util.PropertyPlaceholderHelper...
    ...
~~~

*Đây là ví dụ minh họa cấu trúc log. Loại exception bao ngoài và các frame thực tế phụ thuộc phiên bản Spring, cách inject và cấu hình.*

Đọc theo các tầng:

| Dấu hiệu | Diễn giải |
|---|---|
| **Application run failed** | Quá trình khởi động không hoàn tất. |
| **BeanCreationException** | Spring không tạo được một bean. |
| **paymentClient** | Tên bean bị ảnh hưởng trực tiếp. |
| **Could not resolve placeholder** | Spring không tìm thấy property bắt buộc. |
| **payment.api-key** | Tên property cần kiểm tra trong môi trường chạy. |

Một cách cung cấp property thông qua file cấu hình là:

~~~yaml
payment:
  api-key: ${PAYMENT_API_KEY}
~~~

Khi đó môi trường triển khai phải cung cấp biến **PAYMENT_API_KEY** qua cơ chế quản lý secret thích hợp. Không nên hardcode khóa thật vào source, commit lên repository hoặc in giá trị đó ra log.

Giả sử bean graph là:

~~~text
PaymentController
       │ cần
       ▼
PaymentService
       │ cần
       ▼
PaymentClient
       │ cần
       ▼
payment.api-key
~~~

Một **UnsatisfiedDependencyException** có thể xuất hiện ở PaymentController dù nguyên nhân cụ thể nằm ở lúc tạo PaymentClient. Sửa constructor của controller sẽ không giúp nếu dependency cuối cùng vẫn thiếu cấu hình.

## 8. Ví dụ Spring Boot: dữ liệu request không hợp lệ

Ở ứng dụng HTTP, một exception có thể được chuyển thành một phản hồi có ý nghĩa cho client. Ví dụ service tự parse số lượng:

~~~java
package com.example.orders;

import org.springframework.stereotype.Service;

@Service
public class OrderService {
    public int calculateTotal(String quantityText, int unitPrice) {
        int quantity;
        try {
            quantity = Integer.parseInt(quantityText);
        } catch (NumberFormatException cause) {
            throw new InvalidQuantityException(
                    "Số lượng phải là số nguyên.",
                    cause
            );
        }

        if (quantity <= 0) {
            throw new InvalidQuantityException(
                    "Số lượng phải lớn hơn 0."
            );
        }

        return Math.multiplyExact(quantity, unitPrice);
    }
}
~~~

Exception nghiệp vụ:

~~~java
package com.example.orders;

public class InvalidQuantityException extends RuntimeException {
    public InvalidQuantityException(String message) {
        super(message);
    }

    public InvalidQuantityException(String message, Throwable cause) {
        super(message, cause);
    }
}
~~~

Controller Spring MVC:

~~~java
package com.example.orders;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class OrderController {
    private final OrderService orderService;

    public OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @GetMapping("/orders/total")
    public int total(@RequestParam String quantity) {
        return orderService.calculateTotal(quantity, 100);
    }
}
~~~

Khi gửi:

~~~http
GET /orders/total?quantity=abc HTTP/1.1
Host: localhost:8080
~~~

Luồng lỗi:

~~~text
HTTP request với quantity=abc
   ↓
OrderController.total()
   ↓
OrderService.calculateTotal()
   ↓
Integer.parseInt("abc")
   ↓
NumberFormatException
   ↓
InvalidQuantityException (giữ nguyên cause)
   ↓
Spring MVC exception handling
   ↓
HTTP response theo hợp đồng API
~~~

Vì tham số **quantity** được nhận dưới dạng **String**, việc chuyển đổi xảy ra trong service. Nếu controller nhận **@RequestParam int quantity**, Spring MVC thường chuyển đổi kiểu trước khi gọi method; lúc đó có thể xuất hiện **MethodArgumentTypeMismatchException** ở tầng binding. Cùng một chuỗi đầu vào sai nhưng exception tùy thuộc **nơi thực hiện chuyển đổi**.

### 8.1. Ánh xạ lỗi nghiệp vụ thành HTTP response

Trong Spring MVC, **@RestControllerAdvice** cùng **@ExceptionHandler** hỗ trợ xử lý exception tập trung. Ví dụ với Spring Framework 6 / Spring Boot 3:

~~~java
package com.example.orders;

import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class ApiExceptionHandler {
    @ExceptionHandler(InvalidQuantityException.class)
    public ResponseEntity<ProblemDetail> handleInvalidQuantity(
            InvalidQuantityException ex) {
        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
                HttpStatus.BAD_REQUEST, ex.getMessage()
        );
        problem.setTitle("Số lượng không hợp lệ");
        return ResponseEntity.badRequest().body(problem);
    }
}
~~~

Ở đây message trong **InvalidQuantityException** đã được thiết kế để an toàn cho người dùng. **Không trả ex.getMessage() của mọi exception** ra client: thông báo kỹ thuật có thể chứa SQL, đường dẫn, thông tin server hoặc secret.

| Tình huống | Cách phản hồi thường phù hợp |
|---|---|
| Request có dữ liệu hoặc cấu trúc không hợp lệ | HTTP **400 Bad Request** và mô tả ràng buộc. |
| Resource cần tìm không tồn tại | HTTP **404 Not Found** nếu đúng hợp đồng API. |
| Request xung đột với trạng thái hiện tại | Có thể dùng HTTP **409 Conflict**. |
| Lỗi cấu hình, bug hoặc dependency không dự kiến | HTTP **5xx** thích hợp và log chi tiết ở server. |

Không thể quyết định status chỉ bằng tên Java exception. Chẳng hạn **IllegalArgumentException** có thể do đầu vào của client sai hoặc do code nội bộ gọi sai một phương thức. Trong ứng dụng lớn, định nghĩa exception nghiệp vụ riêng giúp phân loại chính xác hơn.

### 8.2. Spring có thể bọc exception qua nhiều tầng

~~~text
Database driver / HTTP client
         ↓
Spring data access hoặc client abstraction
         ↓
Service: quy tắc nghiệp vụ
         ↓
Controller / @RestControllerAdvice
         ↓
HTTP response
~~~

Một driver có thể báo **SQLException**, tầng dữ liệu chuyển thành **DataAccessException**, service chuyển thành lỗi nghiệp vụ, rồi controller advice trả response. Khi chuyển tầng, giữ lại cause giúp người điều tra lần ngược đến lỗi cụ thể.

## 9. Những exception thường gặp và hướng truy nguyên

Tên exception là dấu hiệu ban đầu để chọn nơi điều tra, nhưng cần kết hợp message, cause và ngữ cảnh để kết luận.

| Loại lỗi | Ý nghĩa ban đầu | Cần điều tra gì? |
|---|---|---|
| **NullPointerException** | Một thao tác yêu cầu tham chiếu khác null nhưng nhận null. | Nguồn giá trị, giả định về null, frame ứng dụng đầu tiên. |
| **NumberFormatException** | Không chuyển đổi được chuỗi sang dạng số yêu cầu. | Nội dung và định dạng input, giá trị ngoài phạm vi biểu diễn. |
| **IllegalArgumentException** | Đầu vào không thỏa yêu cầu của phương thức. | Ai gọi phương thức và hợp đồng tham số. |
| **IllegalStateException** | Trạng thái hiện tại không phù hợp với thao tác. | Thứ tự thao tác, thay đổi trạng thái và cause. |
| **IndexOutOfBoundsException** | Truy cập vị trí ngoài phạm vi hợp lệ. | Điều kiện biên và kích thước dữ liệu. |
| **IOException** | Tác vụ I/O không hoàn tất. | File, quyền truy cập, thiết bị, kết nối hoặc môi trường. |
| **ConnectException** | Không tạo được kết nối TCP đến đích. | Host, port, dịch vụ đích, mạng và firewall. |
| **SocketTimeoutException** | Một thao tác socket vượt thời gian chờ. | Timeout cấu hình, tình trạng mạng và dịch vụ đích. |
| **BeanCreationException** | Spring không tạo/cấu hình được bean. | Tên bean, constructor/factory method và cause. |
| **UnsatisfiedDependencyException** | Spring không đáp ứng được dependency cần thiết. | Bean nào đang thiếu, tạo lỗi hoặc có nhiều ứng viên. |
| **NoSuchBeanDefinitionException** | Không có bean phù hợp trong context hiện tại. | Component scan, bean registration, điều kiện auto-configuration. |
| **NoUniqueBeanDefinitionException** | Có nhiều bean phù hợp nhưng không xác định được một bean. | Có cần **@Qualifier** hoặc **@Primary** không? |
| **HttpMessageNotReadableException** | Spring MVC không đọc/parse request body như yêu cầu. | JSON, content type, DTO và các lỗi conversion bên trong. |
| **MethodArgumentNotValidException** | Validation đối tượng argument không đạt trong đường binding phù hợp. | Field errors, annotation validation và dữ liệu. |
| **DataAccessException** cùng các lớp con | Lỗi được báo qua abstraction truy cập dữ liệu của Spring. | Cause từ JPA, JDBC, driver hoặc database. |

Trong thực tế, hai lỗi cùng lớp có thể có cách sửa rất khác nhau. **IllegalStateException** khi một luồng truy cập trạng thái chưa khởi tạo không giống một IllegalStateException do điều kiện của thư viện thứ ba. Ngay cả **ConnectException** cũng có thể là sai cấu hình hoặc sự cố hạ tầng tạm thời.

### 9.1. Khi ứng dụng không khởi động

Những thông báo dễ gặp:

~~~text
APPLICATION FAILED TO START
~~~

hoặc:

~~~text
Application run failed
~~~

Đây là **mô tả kết quả cuối** của startup. Khi đọc:

1. Tìm exception đang được Spring Boot báo.
2. Xác định tên bean, configuration hoặc web server bị ảnh hưởng.
3. Đi qua các đoạn **Caused by:**.
4. Tìm lỗi cụ thể: thiếu property, không tìm thấy bean, nhiều bean trùng kiểu, port đã được sử dụng, database không kết nối được hoặc factory method ném lỗi.
5. Đối chiếu với cấu hình và điều kiện thực sự của môi trường.

Ví dụ port đang được một tiến trình khác dùng có thể khiến embedded server không bind được. Trong trường hợp này, chỉ có đoạn **Failed to start web server** chưa đủ; cause liên quan đến **BindException: Address already in use** hoặc thông báo tương tự mới chỉ ra hướng kiểm tra cổng.

### 9.2. Khi lỗi phát sinh từ repository và database

~~~text
OrderService.saveOrder()
        ↓
OrderRepository.save(...)
        ↓
JPA / JDBC / driver
        ↓
Database
~~~

Spring có thể chuyển đổi lỗi persistence thành một exception thuộc họ **DataAccessException**. Cause có thể xuất phát từ JDBC driver và chứa thông tin chi tiết như constraint, SQL state hoặc lý do kết nối thất bại.

Một điều dễ gây nhầm lẫn: với JPA, thao tác **save** không nhất thiết ghi xuống database ngay tại dòng code gọi nó; lỗi database đôi khi chỉ xuất hiện ở thời điểm **flush** hoặc **commit**. Do đó, frame nơi exception hiện ra có thể cách xa thời điểm đối tượng nhận dữ liệu sai. Hãy lần theo vòng đời dữ liệu, transaction và ràng buộc database.

### 9.3. Khi một API bên ngoài bị lỗi

Phân biệt ít nhất bốn trường hợp:

- **Không kết nối được**: DNS, TCP, TLS hoặc cổng không phù hợp.
- **Kết nối được nhưng timeout**: server chậm, network chậm hoặc timeout quá ngắn.
- **Server đích trả HTTP lỗi**: cần đọc status và response theo hợp đồng của dịch vụ đó.
- **Response hợp lệ nhưng ứng dụng parse thất bại**: sai DTO, kiểu dữ liệu, định dạng ngày hoặc trường bắt buộc.

Mỗi trường hợp dẫn đến hướng điều tra khác. Đừng gom mọi exception từ client HTTP thành “API không hoạt động”.

## 10. Logging để giữ được bằng chứng

Trong ứng dụng Spring Boot, logging giúp giữ lại dấu vết của lỗi sau khi request kết thúc. Điều quan trọng là thông điệp log phải có **ngữ cảnh** và exception được truyền đúng cho logger.

Với SLF4J:

~~~java
try {
    paymentService.charge(orderId);
} catch (PaymentProviderException ex) {
    log.error("Thanh toán thất bại, orderId={}", orderId, ex);
    throw ex;
}
~~~

Đối số exception cuối cùng giúp logger có thể in stack trace và cause theo cấu hình. Cách sau thường làm mất những thông tin quan trọng:

~~~java
log.error("Thanh toán thất bại: {}", ex.getMessage());
~~~

Nó chỉ ghi chuỗi message và không truyền đối tượng Throwable cho logger.

### 10.1. Log ở đúng ranh giới

Một exception có thể đi qua repository, service, controller và exception handler. Nếu mọi tầng đều log cùng một stack trace ở mức ERROR, một lỗi sẽ xuất hiện thành nhiều sự kiện khó ghép. Nên chọn **ranh giới chịu trách nhiệm quan sát thất bại** để ghi log, và để các tầng khác ném tiếp hoặc chuyển nghĩa exception khi cần.

Đừng coi việc log là đã xử lý lỗi. Nếu ứng dụng chỉ log rồi tiếp tục trả kết quả thành công, trạng thái thực tế có thể sai.

### 10.2. Ghi nội dung có ích, tránh lộ dữ liệu nhạy cảm

Thông điệp tốt thường trả lời: **thao tác nào**, **đối tượng nào**, **ở bước nào**.

~~~text
Không cập nhật được đơn hàng, orderId=ORD-1052, stage=payment-confirmation
~~~

Thông điệp này hữu ích hơn một dòng chung chung:

~~~text
Error!
~~~

Không ghi mật khẩu, API token, access token, toàn bộ SQL chứa bí mật hoặc request body nhạy cảm. Nếu message từ một thư viện bên ngoài chứa dữ liệu người dùng, cần cân nhắc cách che và giới hạn dữ liệu ghi lại.

### 10.3. Request ID và correlation ID

Trong một service có hàng trăm request đồng thời, các log sẽ xen kẽ. **Request ID**, **correlation ID** hoặc **trace ID** giúp liên kết các thông báo của cùng một lần xử lý:

~~~text
2026-11-13T10:15:31Z INFO  requestId=r-102 POST /orders
2026-11-13T10:15:31Z ERROR requestId=r-102 PaymentService - Payment failed
2026-11-13T10:15:31Z INFO  requestId=r-103 GET /catalog
~~~

Nếu công việc chuyển qua thread pool, callback hoặc reactive pipeline, cơ chế truyền tracing context/MDC phải được thiết kế phù hợp. **Không giả định ThreadLocal tự lan qua mọi luồng hoặc mọi operator reactive**.

## 11. Những cách xử lý exception làm mất dấu lỗi

### 11.1. Bắt exception rồi bỏ qua

~~~java
try {
    repository.save(order);
} catch (Exception ex) {
    // Không làm gì
}
~~~

Đoạn code này khiến bên gọi có thể tưởng rằng đơn hàng đã lưu thành công. Nếu không có chiến lược phục hồi hợp lệ, đây là cách che giấu thất bại.

### 11.2. Ném exception mới nhưng bỏ mất cause

~~~java
catch (IOException ex) {
    throw new IllegalStateException("Không đọc được cấu hình");
}
~~~

Exception mới không giữ liên kết với IOException. Cách đúng hơn khi cần chuyển ngữ nghĩa lỗi:

~~~java
catch (IOException ex) {
    throw new IllegalStateException("Không đọc được cấu hình", ex);
}
~~~

Khi không cần bổ sung ngữ nghĩa hay xử lý gì, có thể để exception truyền lên theo hợp đồng phương thức thay vì bọc vô ích.

### 11.3. Tạo lại exception chỉ từ message

~~~java
catch (RuntimeException ex) {
    throw new RuntimeException(ex.getMessage());
}
~~~

Lúc này lớp exception mới và stack trace mới có thể che mất lỗi ban đầu. Nếu chỉ muốn chuyển tiếp exception hiện có:

~~~java
catch (RuntimeException ex) {
    throw ex;
}
~~~

Hoặc bỏ khối catch nếu nó không thêm hành vi hữu ích.

### 11.4. Log lỗi nhưng vẫn báo thành công

~~~java
try {
    paymentService.charge(orderId);
} catch (RuntimeException ex) {
    log.error("Charge failed", ex);
}
return "SUCCESS";
~~~

Nếu thanh toán là bước bắt buộc, kết quả trả về không đúng sự thật. Chỉ phục hồi từ exception khi thực sự có **phương án thay thế hợp lệ** và trạng thái dữ liệu vẫn nhất quán.

### 11.5. Chuyển mọi exception thành một HTTP status

Không nên bắt rộng **Exception** rồi coi tất cả là đầu vào sai và trả HTTP 400. **NullPointerException** do bug và **InvalidQuantityException** do người dùng nhập sai là hai tình huống khác nhau. Chọn status theo **ngữ nghĩa nghiệp vụ và hợp đồng API**, không chỉ theo việc một exception được ném.

### 11.6. Trả stack trace trực tiếp cho client

Stack trace có thể tiết lộ cấu trúc package, đường dẫn file, tên bảng, SQL, nội dung message hoặc dịch vụ nội bộ. Trong production, phản hồi ra ngoài thường chỉ cần **status, mã lỗi, thông báo an toàn và request ID**; stack trace đầy đủ nên nằm ở hệ thống log được kiểm soát quyền truy cập.

### 11.7. Dùng exception cho mọi luồng điều khiển

Không phải tình huống không tìm thấy dữ liệu nào cũng cần ném exception. Có thể dùng **Optional.empty()**, một kết quả có kiểu rõ ràng hoặc một nhánh kiểm tra bình thường khi hợp đồng cho phép. Dùng exception quá rộng làm mờ ranh giới giữa dữ liệu hợp lệ nhưng không có kết quả và một sự cố thực sự.

## 12. Exception trong đa luồng và xử lý bất đồng bộ

Trong lời gọi đồng bộ:

~~~text
Controller → Service → Repository → Driver
~~~

stack trace thường chứa nhiều tầng của chuỗi lời gọi trên cùng một thread.

Nhưng với xử lý bất đồng bộ:

~~~text
Thread A
  └─ HTTP Controller
       └─ Submit task
              │
              ▼
Thread B
  └─ Executor
       └─ BackgroundJob.execute()
            └─ Exception
~~~

Stack trace ở Thread B có thể chỉ chứa executor và phương thức xử lý task, **không có** đầy đủ controller ở Thread A. Với **Future**, lỗi của task có thể được đưa ra bên gọi dưới dạng **ExecutionException**; với **CompletableFuture**, có thể gặp **CompletionException**. Cause của chúng thường quan trọng để đọc lỗi bên trong.

Ví dụ:

~~~java
try {
    resultFuture.join();
} catch (java.util.concurrent.CompletionException ex) {
    Throwable cause = ex.getCause();
    // Phân tích hoặc xử lý theo hợp đồng của tác vụ.
}
~~~

Khi điều tra, kiểm tra nơi task được tạo, input truyền cho task, log tại điểm thực thi và liên kết giữa các sự kiện. Với **Spring WebFlux/Reactor**, stack trace có thể có thêm thông tin về assembly hoặc operator khi bật công cụ quan sát thích hợp, nhưng vẫn cần hiểu sự khác nhau giữa đường gọi đồng bộ và pipeline bất đồng bộ.

## 13. Công cụ hỗ trợ xác định nguyên nhân

### 13.1. Debugger và exception breakpoint

IDE thường cho phép đặt breakpoint vào một dòng code hoặc dừng khi exception được ném. Khi dừng, có thể xem tham số, biến cục bộ, trạng thái đối tượng và call stack.

Exception breakpoint đặc biệt hữu ích khi framework bắt một exception rồi bọc lại khiến log chỉ thấy exception ở tầng cao. Tuy nhiên, các thư viện đôi khi ném và bắt exception cho một tình huống hợp lệ; vì vậy không phải mọi lần debugger dừng ở **throw** đều là lỗi cần sửa.

### 13.2. Đọc log như một sự kiện hoàn chỉnh

Tìm mốc thời gian, request ID và phần đầu stack trace; sau đó đọc liên tục đến hết **Caused by** và **Suppressed**. Một từ khóa **ERROR** có thể chỉ xuất hiện ở dòng đầu, trong khi các dòng stack tiếp theo không có nhãn cấp log riêng.

Nếu log bị cắt giữa chừng, kiểm tra giới hạn formatter hoặc log collector trước khi kết luận “exception không có cause”.

### 13.3. Chẩn đoán của Spring Boot

Khi startup thất bại, Spring Boot có thể hiển thị mô tả và hướng khắc phục cho một số loại lỗi được hỗ trợ. Tùy cấu hình, chạy ứng dụng với chế độ debug cũng có thể cung cấp **condition evaluation report**, giúp biết vì sao một số auto-configuration thỏa hoặc không thỏa điều kiện.

Báo cáo này bổ trợ cho việc hiểu thiết lập Boot; nó không thay thế stack trace và cause của một exception cụ thể.

### 13.4. Test để lưu lại tình huống gây lỗi

Khi đã biết một input từng gây lỗi, bạn có thể mô tả hợp đồng mong muốn trong unit test. Ví dụ cho service ở phần trước:

~~~java
import static org.junit.jupiter.api.Assertions.assertThrows;
import org.junit.jupiter.api.Test;

class OrderServiceTest {
    private final OrderService service = new OrderService();

    @Test
    void rejectsNonNumericQuantity() {
        assertThrows(
                InvalidQuantityException.class,
                () -> service.calculateTotal("abc", 100)
        );
    }
}
~~~

Test này minh họa việc từ chối dữ liệu không hợp lệ ở tầng service. Nếu hợp đồng có cả HTTP status và response body, phần xử lý ở tầng web cần được xem xét riêng. **Một test chỉ xác nhận lớp exception chưa chứng minh API hoặc logging đã đúng**.

## 14. Tình huống tổng hợp: lỗi tạo đơn hàng và database

Giả sử client gọi API tạo đơn hàng và nhận:

~~~http
HTTP/1.1 500 Internal Server Error
~~~

Log server có dạng minh họa:

~~~text
org.springframework.dao.DataIntegrityViolationException:
could not execute statement
    at org.springframework.orm.jpa...
    at com.example.orders.OrderService.create(OrderService.java:57)
    at com.example.orders.OrderController.create(OrderController.java:24)
    ...
Caused by: org.hibernate.exception.ConstraintViolationException:
could not execute statement
    ...
Caused by: java.sql.SQLException:
duplicate key value violates unique constraint "uk_orders_external_id"
    ...
~~~

*Class exception và message thực tế thay đổi theo database, JDBC driver, ORM và phiên bản tích hợp. Ví dụ chỉ mô tả cấu trúc nguyên nhân lồng nhau.*

Lần theo bằng chứng:

1. **Triệu chứng:** client nhận HTTP 500 khi tạo đơn hàng.
2. **Tầng lỗi ngoài:** Spring báo lỗi toàn vẹn dữ liệu.
3. **Cause bên trong:** cơ sở dữ liệu từ chối bản ghi do trùng giá trị ở unique constraint **uk_orders_external_id**.
4. **Frame ứng dụng:** OrderService.create gần lời gọi lưu dữ liệu.
5. **Câu hỏi cần kiểm chứng:** external ID đã tồn tại chưa? Client gửi request lặp? Hai request đồng thời? Logic sinh ID có tạo trùng? Constraint có đúng với quy tắc nghiệp vụ?
6. **Giải pháp phụ thuộc vào kết quả:** có thể cần xử lý tính idempotent, sửa cách sinh ID, phát hiện xung đột trước hoặc ánh xạ tình huống trùng thành HTTP response phù hợp.

Không nên xóa unique constraint chỉ để “hết lỗi” nếu ràng buộc đó bảo vệ tính đúng đắn của dữ liệu. Stack trace giúp xác định điểm thất bại; **hợp đồng nghiệp vụ và mô hình dữ liệu** mới quyết định cách sửa.

### 14.1. Vị trí exception xuất hiện chưa chắc là nơi tạo dữ liệu sai

Khi dùng JPA và transaction, database có thể chỉ phát hiện lỗi ở lúc **flush** hoặc **commit**. Dữ liệu trùng có thể được tạo ra trong một bước trước đó. Vì vậy cần theo dõi:

~~~text
HTTP input / Message
       ↓
DTO + validation
       ↓
Domain service
       ↓
ID generation / mapping
       ↓
Repository + transaction
       ↓
Database constraint
~~~

Tương tự, một lỗi startup xuất hiện ở BeanFactory có thể có nguồn gốc là một biến môi trường thiếu từ trước khi application context được khởi tạo.

## 15. Bài tập đọc stack trace

### Tình huống 1: Không parse được số lượng

~~~text
java.lang.IllegalArgumentException: Invalid quantity
    at com.example.orders.OrderService.place(OrderService.java:35)
    at com.example.orders.OrderController.submit(OrderController.java:19)
Caused by: java.lang.NumberFormatException: For input string: "two"
    at java.base/java.lang.Integer.parseInt(Integer.java:...)
    at com.example.orders.OrderService.place(OrderService.java:31)
    ... 1 more
~~~

Hãy chỉ ra exception ngoài, cause bên trong và vị trí trong mã ứng dụng cần mở.

**Hướng đọc:** exception ngoài là **IllegalArgumentException**; cause là **NumberFormatException**; thao tác trong **OrderService.place** đã thử parse chuỗi **"two"**. Cần kiểm tra nguồn dữ liệu quantity, cách validation và hợp đồng phản hồi khi input sai.

### Tình huống 2: Dependency không được cung cấp

~~~text
org.springframework.beans.factory.UnsatisfiedDependencyException:
Error creating bean with name 'reportController'
    ...
Caused by: org.springframework.beans.factory.NoSuchBeanDefinitionException:
No qualifying bean of type 'com.example.reports.ReportGenerator' available
    ...
~~~

**Hướng đọc:** **reportController** là bean bị ảnh hưởng; **ReportGenerator** là dependency đang thiếu trong application context. Cần kiểm tra bean implementation, phạm vi component scan, điều kiện cấu hình và module cung cấp implementation. Không có cơ sở để khẳng định lỗi ở Spring Framework.

### Tình huống 3: Exception khi đóng tài nguyên

~~~text
java.lang.IllegalStateException: Failed to export
    at com.example.export.ExportService.write(ExportService.java:44)
    Suppressed: java.io.IOException: Failed to close output
        at com.example.export.ExportWriter.close(ExportWriter.java:80)
~~~

**Hướng đọc:** exception khi export là lỗi chính. IOException khi đóng output là **suppressed exception**. Cần xem cả hai nhưng không coi Suppressed là Caused by.

## 16. Những nguyên tắc cần ghi nhớ

- **Đọc type, message, frame và toàn bộ chuỗi Caused by** trước khi quyết định lỗi nằm ở đâu.
- **Tìm frame thuộc code của ứng dụng** rồi đối chiếu đúng phiên bản source, input, cấu hình và trạng thái liên quan.
- **Phân biệt vị trí exception phát sinh với nguyên nhân tạo điều kiện cho lỗi**; đặc biệt quan trọng với bean graph, database và xử lý bất đồng bộ.
- **Giữ cause khi bọc exception** bằng một loại mới phù hợp với tầng nghiệp vụ.
- **Bắt exception ở ranh giới có khả năng phục hồi hoặc phản hồi đúng hợp đồng**, tránh bắt rồi bỏ qua.
- **Không dùng HTTP status để thay thế việc đọc log**; một mã 500 chỉ là triệu chứng.
- **Ghi log có ngữ cảnh và request ID**, hạn chế lặp stack trace, không để lộ secret hoặc stack trace cho người dùng cuối.
- **Kiểm chứng giả thuyết bằng tình huống tái hiện**, tránh chỉ tắt log hoặc nuốt exception rồi coi như vấn đề đã được giải quyết.

Khi nắm được exception, stack trace và cause chain, những dòng log dài chứa các lớp **java.base**, **org.springframework** và **org.hibernate** sẽ trở thành dấu vết có thể phân tích. Bạn có thể xác định tầng đang báo lỗi, lần theo nguyên nhân, tìm đúng dữ liệu hoặc cấu hình gây thất bại và sửa ở nơi thực sự chịu trách nhiệm.
