# Hằng thời điểm biên dịch và field cần khởi tạo lúc chạy trong interface Java

## 1. public static final chưa chắc là hằng biên dịch

Mọi field khai báo trực tiếp trong interface đều ngầm định public static final. Nhưng một **constant variable** còn phải có kiểu primitive hoặc String và được khởi tạo bằng constant expression theo quy tắc Java.

~~~java
interface AppSettings {
    int MAX_RETRIES = 3;                    // Constant variable
    String PREFIX = "api-" + "v1";          // Constant variable
    int TIMEOUT_MS = Integer.parseInt("1500"); // Runtime initialization
    Integer BOXED_RETRIES = 3;               // Runtime initialization
}
~~~

| Khai báo | Constant variable? | Lý do |
| --- | --- | --- |
| int A = 10; | Có | Primitive và literal |
| String B = "Java" + " Core"; | Có | Nối các constant expressions |
| int C = A + 1; | Có, nếu A là constant variable đã khai báo | Biểu thức hằng |
| int D = Integer.parseInt("10"); | Không | Gọi phương thức |
| Integer E = 10; | Không | Integer là kiểu tham chiếu |
| String F = new String("Hi"); | Không | Tạo đối tượng |
| int[] G = {1, 2}; | Không | Mảng là đối tượng |

Kiểu primitive thôi chưa đủ: một field int được gán bằng lời gọi phương thức vẫn không phải constant variable. Tương tự, final trên một tham chiếu không làm đối tượng được trỏ tới bất biến; nội dung đó được giải thích ở bài về final và immutability.

## 2. Quan sát thời điểm khởi tạo

Lưu chương trình sau vào **InterfaceFieldsDemo.java**:

~~~java
interface Configuration {
    int MAX_RETRIES = 2 + 3;
    String PREFIX = "/api/" + "v1";
    int TIMEOUT_MS = readTimeout();

    static int readTimeout() {
        System.out.println("Configuration initializing");
        return 1500;
    }
}

public class InterfaceFieldsDemo {
    public static void main(String[] args) {
        System.out.println("max = " + Configuration.MAX_RETRIES);
        System.out.println("prefix = " + Configuration.PREFIX);
        System.out.println("before runtime field");
        System.out.println("timeout = " + Configuration.TIMEOUT_MS);
    }
}
~~~

Biên dịch và chạy bằng JDK 17+:

~~~bash
javac InterfaceFieldsDemo.java
java InterfaceFieldsDemo
~~~

Stdout:

~~~text
max = 5
prefix = /api/v1
before runtime field
Configuration initializing
timeout = 1500
~~~

MAX_RETRIES và PREFIX là constant variables; compiler có thể đưa giá trị của chúng trực tiếp vào mã sử dụng. Việc đọc chúng không bắt buộc khởi tạo Configuration. Lần đầu đọc TIMEOUT_MS cần khởi tạo interface, nên readTimeout chạy và in thông báo. Việc khởi tạo kiểu diễn ra một lần cho định nghĩa kiểu được nạp bởi class loader tương ứng, không lặp lại mỗi lần đọc field.

Interface không cho khai báo khối static initializer như class. Logic chạy lúc khởi tạo phải được biểu diễn thông qua initializer của field hoặc được chuyển sang API/factory có vòng đời rõ ràng.

## 3. Vì sao client cũ có thể giữ giá trị hằng cũ?

Constant variables có thể được compiler nhúng trực tiếp vào bytecode của mã sử dụng. Ví dụ, thư viện phát hành phiên bản đầu:

~~~java
public interface ApiConstants {
    int VERSION = 1;
    int PORT = Integer.parseInt("8080");
}
~~~

Client:

~~~java
public class Client {
    public static void main(String[] args) {
        System.out.println("version = " + ApiConstants.VERSION);
        System.out.println("port = " + ApiConstants.PORT);
    }
}
~~~

Sau khi biên dịch cả hai tệp, đổi VERSION thành 2 và PORT thành giá trị runtime 9090, rồi chỉ biên dịch lại ApiConstants.java, client.class cũ có thể in:

~~~text
version = 1
port = 9090
~~~

VERSION là constant variable nên giá trị 1 có thể đã được nhúng vào Client.class. PORT không phải constant variable, vì vậy client cũ đọc field lúc chạy và thấy 9090. Biên dịch lại Client.java sẽ khiến mã sử dụng giá trị VERSION mới.

Đây là vấn đề tương thích nhị phân của API công khai: thay đổi giá trị compile-time constant có thể yêu cầu biên dịch lại các client phụ thuộc. Đừng dùng constant variable cho cấu hình mà người dùng kỳ vọng có thể đổi chỉ bằng cách thay JAR.

## 4. Những hành động có thể kích hoạt khởi tạo

Trong các tình huống thông thường, đọc một static field được khai báo bởi interface mà không phải constant variable hoặc gọi static method được khai báo bởi interface có thể kích hoạt khởi tạo kiểu. Đọc constant variable không tự kích hoạt việc đó. Các initializer runtime được xử lý theo thứ tự khai báo; vì vậy hãy tránh phụ thuộc vòng hoặc side effect khó dự đoán.

Một field kiểu List, mảng hay object cũng không phải constant variable chỉ vì nó là static final. Nó được khởi tạo khi interface được khởi tạo, còn trạng thái bên trong có sửa đổi được hay không phụ thuộc vào chính đối tượng.

Để hiểu các lỗi do dùng field phía sau trong initializer, xem bài về giới hạn tham chiếu và thứ tự khai báo; bài đó phân biệt lỗi biên dịch với việc đọc giá trị mặc định lúc chạy.

## 5. Quy tắc quyết định

- Dùng constant variable khi giá trị primitive hoặc String thực sự ổn định như một phần của hợp đồng công khai.
- Dùng field runtime-initialized khi chấp nhận giá trị được tính một lần lúc interface khởi tạo và không cần tự cập nhật mỗi lần đọc.
- Dùng method, service hoặc configuration object khi giá trị phụ thuộc môi trường, người dùng, request hoặc cần được truy vấn lại.
- Tránh đặt I/O, truy cập mạng hay xử lý lỗi phức tạp trong initializer của field.
- Khi đổi hằng công khai, đánh giá client đã biên dịch có cần build lại hay không.

### Tự kiểm tra

1. Integer BOXED = 3 có phải constant variable không? **Không**, vì Integer là kiểu tham chiếu.
2. Đọc constant variable có bắt buộc khởi tạo interface không? **Không**.
3. Lời gọi phương thức trong initializer có thể là constant expression không? **Không**.
4. Đổi một compile-time constant rồi chỉ phát hành JAR mới có đảm bảo client cũ dùng giá trị mới không? **Không**, vì client có thể đã inline giá trị.

Nguồn đặc tả: [JLS §4.12.4 — final Variables](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.12.4), [JLS §15.29 — Constant Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.29), và [JLS §12.4 — Initialization](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.4).