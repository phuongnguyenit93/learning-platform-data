# Thay đổi hằng interface và rủi ro giá trị bị nhúng vào mã đã biên dịch

Trong Java, một trường được khai báo trong interface luôn là `public static final`. Nếu trường đó là một **hằng số thời điểm biên dịch** (compile-time constant), compiler có thể chép trực tiếp giá trị của nó vào bytecode của lớp sử dụng. Vì thế, thay đổi giá trị hằng trong thư viện rồi chỉ phát hành lại thư viện có thể khiến chương trình đã biên dịch vẫn dùng giá trị cũ.

Đây là một vấn đề quan trọng khi tiến hóa API: mã nguồn có vẻ đang đọc một trường của thư viện, nhưng bytecode của client có thể đã chứa sẵn giá trị. Cần hiểu điều kiện nào khiến Java inline hằng số, cách tái hiện lỗi và cách thiết kế API khi giá trị có thể thay đổi theo phiên bản.

## 1. Trường trong interface là hằng công khai

Trong interface, khai báo:

~~~java
interface RetryPolicy {
    int MAX_RETRIES = 3;
}
~~~

tương đương về các modifier với:

~~~java
interface RetryPolicy {
    public static final int MAX_RETRIES = 3;
}
~~~

Các trường của interface phải có giá trị khởi tạo và ngầm định là:

- `public`: mã bên ngoài có thể truy cập nếu quyền truy cập của interface cho phép.
- `static`: trường thuộc về interface, không phải từng đối tượng.
- `final`: không thể gán lại trường sau khi khởi tạo.

Đây là trường hợp khác với trường instance trong một lớp. Interface không có các trường instance thông thường để mỗi đối tượng triển khai giữ một giá trị riêng. Vì trường interface là public, việc công bố nó cũng là một phần của API mà các client có thể phụ thuộc vào.

## 2. Khi nào compiler có thể inline hằng số?

Theo quy tắc Java, một *constant variable* là biến `final` có kiểu nguyên thủy hoặc `String`, được khởi tạo bằng một biểu thức hằng (constant expression). Trường interface có kiểu nguyên thủy hoặc `String` và được khởi tạo bằng biểu thức hằng thường đáp ứng điều kiện này.

Ví dụ:

~~~java
interface Protocol {
    int VERSION = 2;
    String HEADER = "X-Protocol-Version";
    long TIMEOUT_MILLIS = 1_000L * 5;
}
~~~

Các giá trị trên là biểu thức hằng hợp lệ. Khi mã khác tham chiếu trực tiếp đến `Protocol.VERSION`, compiler có thể đưa giá trị `2` vào bytecode của mã gọi.

Không phải mọi trường `static final` đều là compile-time constant:

~~~java
interface RuntimeValues {
    Integer RETRIES = 3;
    int PARSED = Integer.parseInt("3");
    int RANDOM_EXAMPLE = (int) System.currentTimeMillis();
}
~~~

- `Integer RETRIES` là kiểu tham chiếu, nên không phải constant variable theo định nghĩa Java, dù tham chiếu đó là `final`.
- `PARSED` dùng lời gọi phương thức, không phải biểu thức hằng.
- `RANDOM_EXAMPLE` phụ thuộc vào thời điểm chạy.

Các trường không phải compile-time constant cần được đọc như trường lúc chạy; chúng không được thay bằng giá trị hằng theo cùng cơ chế inline. `final` có nghĩa là không thể gán lại biến sau khi khởi tạo, còn “compile-time constant” là một khái niệm hẹp hơn.

## 3. Rủi ro khi đổi giá trị hằng trong một API

Giả sử phiên bản thư viện đầu tiên công bố:

~~~java
public interface ApiSettings {
    int MAX_RETRIES = 3;
    static int currentMaxRetries() {
        return MAX_RETRIES;
    }
}
~~~

Client được biên dịch với phiên bản này:

~~~java
public class Client {
    public static void main(String[] args) {
        System.out.println("constant=" + ApiSettings.MAX_RETRIES);
        System.out.println("method=" + ApiSettings.currentMaxRetries());
    }
}
~~~

Sau đó, thư viện đổi `MAX_RETRIES` từ `3` thành `5`. Nếu chỉ thay tệp lớp của thư viện mà không biên dịch lại `Client.class`, hai dòng có thể cho ra hai giá trị khác nhau:

- Truy cập trực tiếp `ApiSettings.MAX_RETRIES` có thể đã được compiler nhúng thành giá trị `3` trong bytecode của client.
- Lời gọi `ApiSettings.currentMaxRetries()` vẫn là một lời gọi phương thức. Nếu phiên bản mới của interface được nạp lúc chạy, phần thân phương thức mới trả về `5`.

Do đó, việc phát hành lại thư viện không tự động cập nhật các hằng đã được nhúng vào những client đã biên dịch trước đó. Đây thường là lỗi tương thích hành vi: chương trình vẫn chạy, nhưng một phần mã sử dụng giá trị cũ.

## 4. Tái hiện bằng hai phiên bản thư viện

Ví dụ này dùng Java 17 trở lên. Ta biên dịch client với phiên bản 1, sau đó chạy chính bytecode client ấy cùng phiên bản 2 của thư viện. Không biên dịch lại client ở bước đầu tiên.

Tạo cấu trúc thư mục:

~~~text
api-v1/
  ApiSettings.java
api-v2/
  ApiSettings.java
client-src/
  Client.java
~~~

Nội dung `api-v1/ApiSettings.java`:

~~~java
public interface ApiSettings {
    int MAX_RETRIES = 3;

    static int currentMaxRetries() {
        return MAX_RETRIES;
    }
}
~~~

Nội dung `api-v2/ApiSettings.java`:

~~~java
public interface ApiSettings {
    int MAX_RETRIES = 5;

    static int currentMaxRetries() {
        return MAX_RETRIES;
    }
}
~~~

Nội dung `client-src/Client.java`:

~~~java
public class Client {
    public static void main(String[] args) {
        System.out.println("constant=" + ApiSettings.MAX_RETRIES);
        System.out.println("method=" + ApiSettings.currentMaxRetries());
    }
}
~~~

Trên macOS/Linux hoặc shell POSIX, chạy từ thư mục chứa ba thư mục trên:

~~~sh
mkdir -p out-v1 out-v2 out-client
javac -d out-v1 api-v1/ApiSettings.java
javac -cp out-v1 -d out-client client-src/Client.java
javac -d out-v2 api-v2/ApiSettings.java
java -cp out-client:out-v2 Client
~~~

Trên Windows PowerShell, dùng dấu chấm phẩy làm dấu phân cách classpath:

~~~powershell
New-Item -ItemType Directory -Force out-v1, out-v2, out-client | Out-Null
javac -d out-v1 api-v1/ApiSettings.java
javac -cp out-v1 -d out-client client-src/Client.java
javac -d out-v2 api-v2/ApiSettings.java
java -cp "out-client;out-v2" Client
~~~

Kết quả của client đã biên dịch với phiên bản 1 nhưng đang chạy với phiên bản 2:

~~~text
constant=3
method=5
~~~

Dòng đầu phản ánh hằng số đã được inline khi biên dịch `Client.java`. Dòng thứ hai gọi phương thức từ phiên bản 2 của `ApiSettings`, vì vậy trả về giá trị mới.

Để kiểm tra rằng biên dịch lại client sẽ cập nhật giá trị trực tiếp, biên dịch client với phiên bản 2:

~~~sh
mkdir -p out-client-v2
javac -cp out-v2 -d out-client-v2 client-src/Client.java
java -cp out-client-v2:out-v2 Client
~~~

Trên Windows PowerShell, lệnh chạy cuối là:

~~~powershell
New-Item -ItemType Directory -Force out-client-v2 | Out-Null
javac -cp out-v2 -d out-client-v2 client-src/Client.java
java -cp "out-client-v2;out-v2" Client
~~~

Kết quả sau khi biên dịch lại:

~~~text
constant=5
method=5
~~~

Ví dụ này cho thấy khác biệt giữa giá trị được chép vào bytecode của client và giá trị được trả về bởi một phương thức đang có trong thư viện lúc chạy. Các lệnh tạo thư mục có thể được bỏ qua nếu thư mục tương ứng đã tồn tại; để tái hiện sạch từ đầu, hãy dùng các thư mục đầu ra trống.

## 5. Vì sao đây là rủi ro khi tiến hóa API?

Giả sử một thư viện được dùng bởi nhiều ứng dụng hoặc nhiều module:

1. Phiên bản 1 được phát hành với `MAX_RETRIES = 3`.
2. Một module client được biên dịch và phát hành. Bytecode có thể đã chứa giá trị `3`.
3. Thư viện phát hành phiên bản 2 với `MAX_RETRIES = 5`.
4. Ứng dụng chỉ cập nhật thư viện mà giữ nguyên bytecode client.
5. Một số nơi vẫn dùng `3`, trong khi những nơi gọi API theo cách khác có thể thấy `5`.

Điều này gây khó khăn khi điều tra vì mã nguồn đang hiển thị `ApiSettings.MAX_RETRIES`, khiến người đọc nghĩ rằng giá trị sẽ được lấy từ thư viện hiện tại. Trên thực tế, giá trị có thể đã được thay bằng một literal trong bytecode.

Việc thay đổi giá trị một compile-time constant thường không gây lỗi liên kết kiểu `NoSuchFieldError` ở các chỗ tham chiếu trực tiếp đã được inline, bởi bytecode có thể không còn đọc trường đó lúc chạy. Tuy nhiên, đây vẫn là rủi ro tương thích hành vi. Các client có thể cần được biên dịch lại để đồng bộ giá trị mới.

Không nên nhầm điều này với mọi thay đổi API đều an toàn về nhị phân. Xóa hoặc đổi tên trường, thay đổi chữ ký phương thức, hoặc thay đổi cấu trúc kiểu có thể gây các lỗi liên kết khác. Mỗi loại thay đổi cần được đánh giá theo hợp đồng và cách client đã biên dịch sử dụng API.

## 6. Lựa chọn thiết kế khi giá trị có thể thay đổi

Nếu giá trị dự kiến ổn định lâu dài và là một phần rõ ràng của hợp đồng, hằng số công khai có thể phù hợp. Ví dụ, một giá trị mã giao thức đã được chuẩn hóa hoặc một chuỗi định danh không thay đổi có thể là hằng số hợp lý. Dù vậy, nếu client cần cập nhật giá trị khi thư viện đổi phiên bản, cần có quy trình phát hành bao gồm biên dịch lại các client phụ thuộc.

Nếu giá trị có thể thay đổi theo phiên bản, môi trường triển khai, cấu hình người dùng hoặc chính sách nghiệp vụ, hãy ưu tiên một API đọc giá trị lúc chạy:

~~~java
public final class RetryPolicy {
    private RetryPolicy() {
    }

    public static int maxRetries() {
        return 5;
    }
}
~~~

Client gọi `RetryPolicy.maxRetries()`. Khi thư viện được thay bằng phiên bản mới có phần thân phương thức trả về giá trị khác, client đã biên dịch trước đó vẫn gọi phương thức khi chạy và có thể nhận giá trị mới. Điều này chỉ đúng khi lớp thư viện mới thực sự được triển khai và nạp; nếu toàn bộ ứng dụng vẫn chạy với phiên bản cũ, kết quả đương nhiên vẫn cũ.

Với cấu hình theo từng ứng dụng hoặc từng phiên chạy, một đối tượng cấu hình thường rõ ràng hơn một trường tĩnh:

~~~java
public record RetryConfig(int maxRetries) {
    public RetryConfig {
        if (maxRetries < 0) {
            throw new IllegalArgumentException("maxRetries must be >= 0");
        }
    }
}
~~~

Đối tượng cấu hình giúp truyền chính sách một cách tường minh, kiểm tra điều kiện hợp lệ và dùng các giá trị khác nhau cho những thành phần khác nhau. Record trên cần được lưu trong tệp `RetryConfig.java` nếu khai báo là kiểu public ở cấp cao nhất. Đây là một ví dụ độc lập về cách biểu diễn cấu hình, không phải phần bắt buộc của ví dụ hai phiên bản.

Chuyển trường hằng từ interface sang một lớp tiện ích **không tự nó loại bỏ inline**. Một trường `public static final` có giá trị compile-time constant trong lớp cũng có thể được inline vào client. Muốn giá trị được đọc từ phiên bản thư viện lúc chạy, hãy cung cấp một phương thức hoặc một đối tượng cấu hình có hợp đồng phù hợp, thay vì chỉ chuyển vị trí khai báo hằng số.

## 7. Hằng số trong interface và nguyên tắc thiết kế

Dùng interface chỉ để gom các hằng số thường tạo ra “constant interface”: các lớp triển khai interface nhận những tên hằng trong phạm vi sử dụng của mình dù không thực sự cần thể hiện một hành vi hay quan hệ kiểu. Cách này làm rối API và khiến việc tiến hóa các tên công khai khó hơn.

Một số nguyên tắc thực tế:

- Đặt hằng số cạnh khái niệm mà nó mô tả; tránh buộc lớp phải triển khai một interface chỉ để dùng hằng.
- Dùng hằng compile-time cho giá trị thực sự ổn định, không phải cho giá trị cấu hình hoặc chính sách có thể thay đổi.
- Nếu client cần nhìn thấy giá trị mới khi chỉ cập nhật thư viện lúc chạy, dùng phương thức truy cập hoặc đối tượng cấu hình.
- Khi thay đổi giá trị hằng compile-time trong API đã phát hành, đánh giá việc biên dịch lại toàn bộ module client phụ thuộc.
- Viết kiểm thử tương thích với đúng mô hình triển khai: kiểm thử source mới được biên dịch cùng thư viện mới không đủ để phát hiện bytecode client cũ còn chứa hằng cũ.

## 8. Phân biệt ba khái niệm dễ nhầm

| Khái niệm | Ý nghĩa | Hệ quả |
|---|---|---|
| `final` field | Không thể gán lại biến sau khi khởi tạo | Không đồng nghĩa với inline |
| Compile-time constant | Biến `final` kiểu nguyên thủy hoặc `String`, khởi tạo bằng biểu thức hằng | Compiler có thể chép giá trị vào bytecode của client |
| Runtime accessor | Phương thức hoặc cấu hình được đọc khi chương trình chạy | Có thể cung cấp giá trị mới nếu implementation mới được nạp |

Khi điều tra một giá trị cũ sau khi cập nhật thư viện, hãy kiểm tra xem mã nguồn tham chiếu trực tiếp một compile-time constant hay gọi phương thức. Tiếp theo, xác minh client có được biên dịch lại không, classpath lúc chạy thực sự nạp phiên bản thư viện nào, và có module nào khác vẫn mang bytecode cũ hay không.

Điểm cốt lõi khi tiến hóa API là phân biệt **giá trị cố định tại thời điểm biên dịch** với **giá trị được truy vấn lúc chạy**. Hằng interface tiện dụng, nhưng một giá trị đã inline sẽ không tự thay đổi chỉ vì thư viện được nâng cấp.