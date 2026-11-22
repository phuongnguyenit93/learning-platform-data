# Thuộc tính interface ngầm định public static final và bắt buộc khởi tạo

## 1. Ba modifier mặc định

Mọi field được khai báo trực tiếp trong interface đều ngầm định **public static final**.

~~~java
interface ConnectionOptions {
    int DEFAULT_PORT = 8080;
    String PROTOCOL = "https";
}
~~~

Các field trên có cùng modifier như thể viết tường minh:

~~~java
interface ConnectionOptions {
    public static final int DEFAULT_PORT = 8080;
    public static final String PROTOCOL = "https";
}
~~~

| Modifier | Ý nghĩa |
| --- | --- |
| public | Mã có quyền truy cập interface có thể đọc field |
| static | Field thuộc về interface, dùng chung ở cấp kiểu |
| final | Field không thể được gán lại sau khi khởi tạo |

Vì field là static, cách đọc rõ nghĩa là ConnectionOptions.DEFAULT_PORT. Không cần tạo instance và không có field riêng cho từng đối tượng implements interface.

## 2. Initializer là bắt buộc

Mỗi field interface phải có biểu thức khởi tạo ngay tại khai báo:

~~~java
interface ServerConfig {
    int TIMEOUT_SECONDS = 30;
    String HOST = "localhost";
}
~~~

Đoạn sau không hợp lệ:

~~~java
interface BrokenConfig {
    int TIMEOUT_SECONDS;
}
~~~

Interface không có constructor instance để gán field sau này và không cho khai báo khối static initializer kiểu class. Constructor của class implements cũng không thể gán field của interface, vì field đó là static final thuộc interface.

Điều kiện “có initializer” không có nghĩa giá trị phải là hằng thời điểm biên dịch. Ví dụ, **int TIMEOUT = Integer.parseInt("1500");** có initializer hợp lệ nhưng được tính khi interface khởi tạo. Bài về hằng thời điểm biên dịch giải thích kỹ hơn sự khác nhau này.

## 3. Ví dụ chạy được

Lưu vào **InterfaceFieldRulesDemo.java**:

~~~java
interface Limits {
    int MAX_RETRIES = 3;
    String DEFAULT_MODE = "SAFE";
    long MAX_BYTES = 1_024L * 1_024;
}

public class InterfaceFieldRulesDemo {
    public static void main(String[] args) {
        System.out.println(Limits.MAX_RETRIES);
        System.out.println(Limits.DEFAULT_MODE);
        System.out.println(Limits.MAX_BYTES);
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac InterfaceFieldRulesDemo.java
java InterfaceFieldRulesDemo
~~~

Kết quả:

~~~text
3
SAFE
1048576
~~~

Tên interface trong biểu thức truy cập cho thấy nguồn khai báo của giá trị. Không cần implements Limits để đọc các field public. Chỉ implements một interface khi class thực sự đáp ứng hợp đồng mà interface đại diện.

## 4. Field interface không phải trạng thái instance

~~~java
interface PortDefaults {
    int PORT = 8080;
}

final class HttpClient {
    int defaultPort() {
        return PortDefaults.PORT;
    }
}
~~~

Mọi nơi truy cập PortDefaults.PORT đều đọc cùng field tĩnh đó. Nếu mỗi client cần cổng riêng, hãy đặt một field instance trong class và gán qua constructor, thay vì cố dùng field interface cho trạng thái từng đối tượng.

Field interface cũng không tự làm đối tượng tham chiếu trở nên bất biến. Ví dụ, field trỏ đến mảng vẫn có thể cho phép sửa phần tử; bài về final và immutability tập trung vào ranh giới này.

## 5. Modifier không hợp lệ

Các ví dụ sau minh họa từng lỗi riêng biệt, không ghép chung thành một chương trình:

~~~java
interface InvalidAccess {
    private int PORT = 8080;      // Sai: field interface không thể private
}
~~~

~~~java
interface InvalidVisibility {
    protected int PORT = 8080;    // Sai: field interface không thể protected
}
~~~

~~~java
interface MissingValue {
    int PORT;                     // Sai: thiếu initializer
}
~~~

~~~java
interface InvalidInitializer {
    int PORT = 8080;
    static {
        System.out.println("init"); // Sai: interface không có static initializer block
    }
}
~~~

Các modifier transient và volatile cũng không phù hợp với field interface. Không thể loại bỏ riêng static hoặc final để biến field thành dữ liệu instance hay dữ liệu có thể gán lại.

## 6. Có nên gom mọi hằng vào interface?

Một interface có thể công bố hằng khi các giá trị thực sự thuộc hợp đồng của nó. Nhưng dùng interface chỉ như kho hằng, rồi cho class implements chỉ để có thể viết tên field ngắn, thường tạo quan hệ kiểu gây hiểu nhầm.

Với hằng tiện ích không thuộc hợp đồng hành vi, có thể dùng utility class:

~~~java
public final class Defaults {
    private Defaults() {
        throw new AssertionError("No instances");
    }

    public static final int DEFAULT_TIMEOUT = 30;
}
~~~

Mã sử dụng viết **Defaults.DEFAULT_TIMEOUT** mà không cần implements. Nếu giá trị thay đổi theo môi trường hoặc cần đọc lại khi chạy, dùng API cấu hình hoặc object cấu hình thay vì giả định field final sẽ tự cập nhật.

Khi có nhiều interface với field trùng tên, hãy chỉ rõ interface sở hữu field; bài về truy cập hằng xử lý các xung đột đó.

### Tự kiểm tra

1. Field **int PORT = 8080;** trong interface có modifier ngầm định nào? **public static final**.
2. Có thể gán field interface trong constructor của class implements không? **Không**.
3. Mọi initializer đều là hằng thời điểm biên dịch không? **Không**; initializer có thể gọi phương thức hoặc tạo đối tượng.
4. Có nên implements một interface chỉ để lấy tên hằng ngắn? **Thông thường không**; truy cập qua tên interface rõ nghĩa hơn.

Ba modifier mặc định và initializer bắt buộc là quy tắc nền tảng của field interface. Chúng quyết định field thuộc về ai, ai có thể đọc và khi nào giá trị được cung cấp.