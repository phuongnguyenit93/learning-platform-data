# Truy cập hằng thời điểm biên dịch không kích hoạt khởi tạo interface

Trong Java, việc đọc một **hằng thời điểm biên dịch** (*constant variable*) được khai báo trong interface không tự kích hoạt quá trình khởi tạo interface đó. Đây là một ngoại lệ quan trọng khi tìm hiểu thời điểm khởi tạo kiểu, bởi một số lần truy cập trường `static` có thể kích hoạt khởi tạo, trong khi truy cập hằng thời điểm biên dịch thì không.

Quy tắc này áp dụng cho biến `static final` có kiểu nguyên thủy hoặc `String`, được khởi tạo bằng một **biểu thức hằng** (*constant expression*). Chỉ có `static final` thôi là chưa đủ. Muốn xác định một lần đọc có kích hoạt khởi tạo interface hay không, hãy kiểm tra kiểu dữ liệu và biểu thức khởi tạo của trường.

## 1. Vì sao quy tắc này quan trọng?

Interface có thể khai báo trường, và các trường được ngầm định là `public static final`. Tuy vậy, không phải mọi trường trong interface đều là hằng thời điểm biên dịch.

Ví dụ:

~~~java
interface Limits {
    int MAX_ITEMS = 100;
    int COMPUTED_ITEMS = Integer.parseInt("100");
}
~~~

`MAX_ITEMS` là hằng thời điểm biên dịch: kiểu là `int` và biểu thức `100` là biểu thức hằng. Ngược lại, `COMPUTED_ITEMS` không phải hằng thời điểm biên dịch vì lời gọi phương thức `Integer.parseInt(...)` không phải biểu thức hằng, dù kết quả khi chạy là `100`.

Nếu mã khác chỉ đọc `Limits.MAX_ITEMS`, thao tác đọc này không yêu cầu khởi tạo `Limits`. Nếu mã đọc `Limits.COMPUTED_ITEMS` khi interface chưa được khởi tạo, việc đọc trường `static` không phải hằng sẽ kích hoạt khởi tạo interface.

## 2. Khi nào một trường là hằng thời điểm biên dịch?

Theo quy tắc của Java, một *constant variable* là biến `final` có kiểu nguyên thủy hoặc kiểu `String`, được khởi tạo bằng biểu thức hằng. Trong interface, `final` được ngầm định cho các trường, nhưng vẫn cần đáp ứng cả điều kiện kiểu dữ liệu và biểu thức khởi tạo.

| Khai báo trong interface | Là hằng thời điểm biên dịch? | Lý do |
| --- | --- | --- |
| `int COUNT = 12;` | Có | `int` và literal hằng |
| `static final long MASK = 1L << 4;` | Có | Kiểu nguyên thủy và phép toán trên các hằng |
| `String NAME = "Java" + " SE";` | Có | `String` được tạo từ biểu thức hằng |
| `int COUNT = Integer.parseInt("12");` | Không | Có lời gọi phương thức |
| `static final Integer COUNT = 12;` | Không | `Integer` là kiểu tham chiếu, không phải kiểu nguyên thủy hay `String` |
| `static final int COUNT = loadCount();` | Không | Lời gọi phương thức không phải biểu thức hằng |
| `static final String NAME = new String("Java");` | Không | Biểu thức tạo đối tượng không phải biểu thức hằng |

Từ khóa `static` và `final` không tự biến một trường thành hằng thời điểm biên dịch. Ví dụ `static final Integer VALUE = 5` vẫn là trường tham chiếu kiểu `Integer`; truy cập nó có thể kích hoạt khởi tạo interface nếu interface chưa được khởi tạo.

## 3. Ví dụ Java chạy hoàn chỉnh

Ví dụ dưới đây đặt một hằng thời điểm biên dịch và một trường `static` không phải hằng trong cùng interface. Phương thức khởi tạo in thông báo để có thể quan sát thời điểm khởi tạo.

~~~java
interface BuildInfo {
    int COMPILE_TIME_LIMIT = 100;
    String LABEL = "v" + "1";
    int RUNTIME_LIMIT = initialize();

    static int initialize() {
        System.out.println("BuildInfo initialized");
        return 200;
    }
}

public class InterfaceConstantDemo {
    public static void main(String[] args) {
        System.out.println(BuildInfo.COMPILE_TIME_LIMIT);
        System.out.println(BuildInfo.LABEL);
        System.out.println("After constant access");
        System.out.println(BuildInfo.RUNTIME_LIMIT);
    }
}
~~~

Lưu mã vào tệp `InterfaceConstantDemo.java`, sau đó biên dịch và chạy bằng Java 17 trở lên:

~~~text
javac InterfaceConstantDemo.java
java InterfaceConstantDemo
~~~

Kết quả stdout chính xác:

~~~text
100
v1
After constant access
BuildInfo initialized
200
~~~

Hai lần đọc đầu tiên sử dụng `COMPILE_TIME_LIMIT` và `LABEL`. Cả hai là hằng thời điểm biên dịch nên việc đọc chúng không kích hoạt khởi tạo `BuildInfo`. Dòng `After constant access` xuất hiện trước thông báo khởi tạo, chứng minh điều đó trong lần chạy này.

Khi chương trình đọc `BuildInfo.RUNTIME_LIMIT`, JVM cần giá trị của một trường `static` không phải hằng thời điểm biên dịch. Việc đọc này kích hoạt khởi tạo interface; biểu thức khởi tạo gọi `initialize()`, in `BuildInfo initialized`, rồi trả về `200`.

Kết quả trên minh họa hành vi của chương trình khi interface chưa được khởi tạo bởi nguyên nhân nào khác. Nếu một thao tác trước đó đã khởi tạo interface, thông báo khởi tạo có thể đã xuất hiện trước lần đọc hằng.

## 4. Không phải mọi trường `static final` đều được nội tuyến

Trình biên dịch Java có thể thay một tham chiếu đến hằng thời điểm biên dịch bằng chính giá trị hằng trong mã gọi. Cơ chế này thường được gọi là *constant inlining* (nội tuyến hằng). Bởi vậy, mã dùng `BuildInfo.COMPILE_TIME_LIMIT` có thể không cần đọc trường đó tại thời gian chạy.

Đối với một trường `static final` không phải hằng thời điểm biên dịch, chẳng hạn `RUNTIME_LIMIT`, mã gọi vẫn cần lấy giá trị trường khi chạy. Nếu interface chưa được khởi tạo, lần đọc này là một hành động có thể kích hoạt khởi tạo.

Cần phân biệt:

- **Hằng thời điểm biên dịch:** kiểu nguyên thủy hoặc `String`, khai báo `final` và khởi tạo bằng biểu thức hằng. Đọc trường không tự kích hoạt khởi tạo interface.
- **Trường `static final` thông thường:** có thể mang giá trị cố định sau khi khởi tạo, nhưng biểu thức khởi tạo không phải biểu thức hằng hoặc kiểu dữ liệu không đáp ứng yêu cầu. Đọc trường khi interface chưa khởi tạo có thể kích hoạt khởi tạo.
- **Trường không `final`:** không phải hằng thời điểm biên dịch; đọc trường `static` khi interface chưa khởi tạo cũng có thể kích hoạt khởi tạo.

Nói cách khác, giá trị có vẻ không đổi khi chạy không có nghĩa là nó là hằng thời điểm biên dịch theo định nghĩa của Java.

## 5. Hệ quả khi thay đổi giá trị hằng trong thư viện

Do hằng thời điểm biên dịch có thể được nội tuyến vào mã gọi, thay đổi giá trị hằng trong một thư viện rồi chỉ thay tệp thư viện mà không biên dịch lại mã khách hàng có thể khiến chương trình tiếp tục dùng giá trị cũ.

Ví dụ, thư viện ban đầu khai báo `int RETRY_LIMIT = 3`, rồi phiên bản mới đổi thành `int RETRY_LIMIT = 5`. Nếu một lớp khách hàng đã được biên dịch khi giá trị là `3`, mã bytecode của lớp khách hàng có thể vẫn chứa số `3`. Chỉ cập nhật tệp thư viện không đảm bảo lớp khách hàng tự động nhận giá trị mới.

Khi thay đổi một hằng công khai có thể được sử dụng bởi mã đã biên dịch độc lập, hãy cân nhắc tương thích nhị phân và biên dịch lại các thành phần phụ thuộc khi cần. Nếu giá trị cần thay đổi mà không muốn nội tuyến vào mã khách hàng, có thể cung cấp một phương thức truy cập thay vì một trường hằng, sau khi cân nhắc API và yêu cầu tương thích.

## 6. Interface khởi tạo khác với class khởi tạo như thế nào?

Quy tắc về hằng cần được đặt trong bối cảnh quy tắc khởi tạo kiểu rộng hơn:

- Khởi tạo một class thường bao gồm việc khởi tạo superclass của nó và một số superinterface liên quan có khai báo phương thức `default`.
- Khởi tạo một interface không tự động khởi tạo tất cả superinterface của nó.
- Việc đọc một trường `static` không phải hằng thời điểm biên dịch được khai báo trong interface có thể kích hoạt khởi tạo interface đó.
- Việc đọc hằng thời điểm biên dịch được khai báo trong interface không tự kích hoạt khởi tạo interface đó.

Không nên suy luận rằng bất kỳ thao tác nào có nhắc đến tên interface đều khởi tạo interface. Tên kiểu có thể xuất hiện trong kiểu khai báo, chữ ký, hoặc một tham chiếu hằng đã được trình biên dịch thay bằng giá trị. Hành động thực tế và loại thành viên được truy cập mới quyết định có kích hoạt khởi tạo hay không.

## 7. Các tình huống dễ nhầm

| Tình huống | Có tự kích hoạt khởi tạo interface? | Giải thích |
| --- | --- | --- |
| Đọc `Settings.TIMEOUT`, trong đó `TIMEOUT` là `static final int` được khởi tạo bằng literal | Không | Đây là hằng thời điểm biên dịch |
| Đọc `Settings.NAME`, trong đó `NAME` là `String` được ghép từ các literal | Không | Biểu thức ghép là biểu thức hằng |
| Đọc `Settings.TIMEOUT`, trong đó trường được gán bằng lời gọi phương thức | Có, nếu interface chưa khởi tạo | Đây là trường `static` không phải hằng thời điểm biên dịch |
| Đọc `Settings.VALUE`, trong đó trường có kiểu `Integer` và là `static final` | Có, nếu interface chưa khởi tạo | `Integer` không đáp ứng yêu cầu kiểu của constant variable |
| Đọc một hằng sau khi interface đã được khởi tạo vì một nguyên nhân khác | Không tạo ra lần khởi tạo mới | Việc khởi tạo chỉ xảy ra một lần cho mỗi class loader |
| Dùng một hằng trong biểu thức mã nguồn | Thông thường không | Nếu đó là hằng thời điểm biên dịch hợp lệ, giá trị có thể được nội tuyến khi biên dịch |

Bảng trên nói về việc thao tác đó có tự kích hoạt khởi tạo hay không. Nó không khẳng định rằng interface chắc chắn chưa từng được khởi tạo trước thao tác đang xét.

## 8. Cách kiểm tra trong dự án thực tế

Khi điều tra vì sao một thông báo khởi tạo xuất hiện sớm hoặc muộn, hãy kiểm tra các điểm sau:

1. Xác nhận trường có kiểu nguyên thủy hoặc `String` và được khởi tạo bằng biểu thức hằng hay không. Đừng chỉ dựa vào `static final`.
2. Tìm các nơi truy cập trường `static` không phải hằng, gọi phương thức `static` của interface, hoặc các hành động khác có thể khởi tạo kiểu.
3. Tạo một ví dụ tối giản có thông báo trong biểu thức khởi tạo để quan sát thứ tự thực tế.
4. Nếu thay đổi hằng trong thư viện, kiểm tra xem các lớp khách hàng đã được biên dịch lại hay vẫn chứa giá trị đã nội tuyến.
5. Khi kiểm tra thứ tự khởi tạo, đảm bảo không có thao tác trước đó đã khởi tạo interface và làm sai lệch quan sát.

## 9. Ghi nhớ

Điều quyết định là **hằng thời điểm biên dịch** theo định nghĩa của Java, chứ không đơn thuần là trường `static final`. Đọc hằng thời điểm biên dịch được khai báo trong interface không tự kích hoạt khởi tạo interface. Đọc trường `static` không phải hằng thời điểm biên dịch có thể kích hoạt khởi tạo nếu interface chưa được khởi tạo. Sự khác biệt này cũng giải thích vì sao hằng công khai có thể được nội tuyến vào mã khách hàng và vì sao việc cập nhật giá trị hằng đôi khi cần biên dịch lại các thành phần phụ thuộc.