# Thiết kế `toString()` ngắn gọn, có tên trường và đủ thông tin

## 1. Mục tiêu của biểu diễn `toString()`

Trong Java, `Object.toString()` tạo ra biểu diễn dạng `String` của một đối tượng. Khi lớp **không ghi đè**, cách cài đặt mặc định thường cho chuỗi dạng `TênLớp@maBamHex`, chẳng hạn `Order@3e25a5`; phần mã băm không bảo đảm duy nhất và không có ý nghĩa nghiệp vụ rõ ràng. Đối với đối tượng chứa nhiều trạng thái, người đọc log khó biết đơn hàng nào, trạng thái gì, các thuộc tính quan trọng ra sao.

Một `toString()` tốt nên trả lời nhanh: **Đây là loại đối tượng gì? Những trường nào giúp nhận diện và hiểu trạng thái hiện tại?** Chuỗi nên:

- **Ngắn gọn:** tránh in mọi trường, toàn bộ đồ thị đối tượng hoặc dữ liệu quá dài.
- **Có tên trường:** thể hiện rõ `id=...`, `status=...`, `count=...` thay vì dãy giá trị không nhãn khó hiểu.
- **Đủ thông tin:** ưu tiên mã nhận diện, trạng thái, số lượng hoặc thuộc tính thiết yếu để hiểu đối tượng khi đọc log.
- **Dễ đọc và nhất quán:** cùng một lớp dùng cùng quy ước tên, dấu phân cách và thứ tự trường.
- **An toàn:** không làm lộ mật khẩu, token, dữ liệu cá nhân hoặc nội dung không được phép ghi log; không chạy đệ quy vô hạn, không phát sinh tác dụng phụ đáng kể.

Ví dụ so sánh:

~~~text
Khó đọc:
Order@5f12a23
Order(ORD-104, PAID, 2, 120.50)

Dễ đọc:
Order{orderId='ORD-104', status=PAID, itemCount=2, total=120.50}
~~~

Trong ví dụ tốt, `Order` nói rõ kiểu đối tượng, các tên trường làm rõ ý nghĩa của từng giá trị và có thể nhận biết nhanh trạng thái đơn hàng. Dấu `{}` hay `[]` là **quy ước trình bày**, không phải một chuẩn ngôn ngữ bắt buộc. Quan trọng là tính thống nhất và dễ hiểu.

## 2. Hợp đồng `Object.toString()` và ý nghĩa của ghi đè

Trong Java, mọi lớp đều có thể ghi đè phương thức:

~~~java
@Override
public String toString() {
    return "...";
}
~~~

Đây là **đoạn minh họa cú pháp**, chưa phải chương trình chạy độc lập. `toString()` là phương thức không nhận tham số, trả về `String` và thường được gọi **ngầm** trong các thao tác:

~~~java
System.out.println(order);     // println(Object) sử dụng biểu diễn String.
String text = String.valueOf(order);
String message = "order=" + order;
~~~

Các dòng trên chỉ minh họa trong phạm vi đã có biến `order`; chúng không phải tệp độc lập. Nếu `order` là `null`, `String.valueOf(order)` trả về chuỗi `"null"`. Tuy nhiên, gọi trực tiếp `order.toString()` sẽ ném `NullPointerException` trong trường hợp `order == null`.

Những điểm quan trọng:

- `toString()` **không phải** `equals()` hoặc `hashCode()`; thay đổi định dạng `toString()` không tự thay đổi ngữ nghĩa bằng nhau, mã băm hay danh tính đối tượng.
- Tài liệu `Object.toString()` khuyến nghị cung cấp chuỗi ngắn gọn nhưng giàu thông tin, giúp người dùng dễ đọc.
- Nếu ứng dụng cần dữ liệu cho máy xử lý, truyền qua mạng, lưu cơ sở dữ liệu, ký số hay kiểm tra tính tương thích phiên bản, hãy dùng **định dạng và API chuyên dụng**, ví dụ JSON serializer hoặc DTO phù hợp. Đừng biến kết quả `toString()` thành giao thức dữ liệu ổn định ngoài ý định thiết kế.
- Không có hợp đồng chung bắt buộc mọi lớp phải chọn chính xác một kiểu dấu ngoặc, thứ tự trường hay định dạng ngày giờ. Hãy chọn phong cách nhất quán trong module.

## 3. Chọn đúng trường để hiển thị

Không nên tự động đưa **tất cả** trường vào `toString()`. Hãy chia nhóm để quyết định:

| Nhóm trường | Ví dụ | Quyết định thường phù hợp |
| --- | --- | --- |
| Nhận diện hữu ích | `orderId`, `taskId`, mã loại | Thường nên có khi được phép hiển thị |
| Trạng thái chính | `status`, `active`, `phase` | Thường nên có |
| Số liệu tổng hợp | `itemCount`, `total`, `size` | Thường hữu ích hơn cả danh sách dài |
| Dữ liệu có thể rất lớn | `payload`, `items`, `stackFrames` | Hiển thị số lượng, giới hạn độ dài hoặc lược bỏ |
| Thông tin nhạy cảm | `password`, `accessToken`, `sessionSecret`, thông tin cá nhân | Không đưa giá trị thật vào chuỗi; có thể bỏ qua hoặc che |
| Tham chiếu lồng nhau | `parent`, `children`, `owner` | Chỉ in một thuộc tính tóm tắt hoặc mã định danh; tránh đệ quy |
| Thông tin kỹ thuật ít có ích | Cache nội bộ, cờ đồng bộ, đối tượng service | Bỏ qua nếu không giúp chẩn đoán |

**“Đủ thông tin” không đồng nghĩa “đủ mọi trường”.** Một thông tin nên có khi nó giúp phân biệt sự kiện hoặc hiểu trạng thái cần thiết của đối tượng. Nếu toàn bộ collection có hàng nghìn phần tử, `itemCount=1000` thường phù hợp cho log hơn danh sách toàn bộ.

Ví dụ mục tiêu đối với `Order`:

~~~text
Order{orderId='ORD-104', status=PAID, itemCount=2, total=120.50}
~~~

Nếu `customerEmail` là trường nhạy cảm, tránh in nó trong `toString()` chỉ vì có sẵn trong đối tượng. Ngay cả mã ID cũng có thể nhạy cảm tùy hệ thống và chính sách log; hãy lựa chọn theo dữ liệu thực tế.

## 4. Ví dụ Java 17+ chạy độc lập

Ví dụ dưới đây dùng `StringJoiner` để xây dựng chuỗi dễ đọc, in một vài thuộc tính thiết yếu và cố ý không đưa `customerEmail` vào biểu diễn. Nó cũng minh họa cách hiển thị mảng lồng nhau, `null`, record và đối tượng có tham chiếu vòng.

Tạo tệp **`ToStringDesignDemo.java`**:

~~~java
import java.math.BigDecimal;
import java.util.Arrays;
import java.util.List;
import java.util.Objects;
import java.util.StringJoiner;

public class ToStringDesignDemo {
    static final class Order {
        private final String orderId;
        private final String customerEmail; // Không ghi vào toString().
        private final String status;
        private final int itemCount;
        private final BigDecimal total;

        Order(String orderId, String customerEmail, String status,
              int itemCount, BigDecimal total) {
            this.orderId = Objects.requireNonNull(orderId);
            this.customerEmail = Objects.requireNonNull(customerEmail);
            this.status = Objects.requireNonNull(status);
            this.itemCount = itemCount;
            this.total = Objects.requireNonNull(total);
        }

        @Override
        public String toString() {
            return new StringJoiner(", ", "Order{", "}")
                    .add("orderId='" + orderId + "'")
                    .add("status=" + status)
                    .add("itemCount=" + itemCount)
                    .add("total=" + total.toPlainString())
                    .toString();
        }
    }

    static final class Node {
        private final String name;
        private Node next;

        Node(String name) {
            this.name = name;
        }

        void linkTo(Node next) {
            this.next = next;
        }

        @Override
        public String toString() {
            String nextName = next == null ? "null" : next.name;
            return "Node{name='" + name + "', nextName='"
                    + nextName + "'}";
        }
    }

    record Size(int width, int height) {}

    public static void main(String[] args) {
        Order order = new Order(
                "ORD-104",
                "example@private.invalid",
                "PAID",
                2,
                new BigDecimal("120.50"));

        System.out.println(order);

        Node first = new Node("A");
        Node second = new Node("B");
        first.linkTo(second);
        second.linkTo(first);
        System.out.println(first);

        Object[] nested = {"batch", new int[] {1, 2}};
        System.out.println("nested=" + Arrays.deepToString(nested));

        Size size = new Size(3, 5);
        System.out.println("record=" + size);

        String missing = null;
        System.out.println("optional="
                + Objects.toString(missing, "<none>"));
    }
}
~~~

Biên dịch và chạy bằng **JDK 17 trở lên**:

~~~bash
javac ToStringDesignDemo.java
java ToStringDesignDemo
~~~

Đầu ra xác định:

~~~text
Order{orderId='ORD-104', status=PAID, itemCount=2, total=120.50}
Node{name='A', nextName='B'}
nested=[batch, [1, 2]]
record=Size[width=3, height=5]
optional=<none>
~~~

### Giải thích từng dòng

1. `Order.toString()` có **tên lớp, tên trường, dấu phân cách và thứ tự rõ ràng**. Trường `customerEmail` vẫn tồn tại trong đối tượng nhưng không xuất hiện trong chuỗi. `BigDecimal.toPlainString()` duy trì cách biểu diễn thập phân `120.50` của giá trị đã khởi tạo, không phát sinh dạng khoa học trong ví dụ.
2. Hai `Node` liên kết thành vòng `A -> B -> A`. `Node.toString()` chỉ đọc `next.name` chứ **không gọi `next.toString()`**, nên không đệ quy qua liên kết vòng. Đầu ra cho biết nút kế tiếp mà không phải in cả đồ thị.
3. `Arrays.deepToString(nested)` cho biểu diễn nội dung mảng lồng nhau; `Arrays.toString(nested)` thông thường sẽ không in sâu nội dung `int[]` theo cách tương tự. Với cấu trúc mảng có tham chiếu vòng, `deepToString` có quy tắc đánh dấu vòng của mảng; điều đó không đồng nghĩa mọi kiểu đối tượng lồng nhau đều được xử lý vòng tự động.
4. Java `record` tự tạo `toString()` theo các thành phần, nên `Size(3, 5)` được in dưới dạng `Size[width=3, height=5]`.
5. `Objects.toString(missing, "<none>")` tạo chuỗi dự phòng rõ nghĩa khi giá trị là `null`. Dạng trình bày `<none>` là lựa chọn của ví dụ, không phải giá trị bắt buộc của Java.

Chương trình **không in ra** mã băm danh tính, giá trị ngẫu nhiên, thời gian hiện tại hoặc thứ tự duyệt không xác định, vì vậy các dòng stdout trên không phụ thuộc vào lần chạy.

## 5. Cách định dạng ngắn gọn và nhất quán

Có nhiều cách hợp lệ để tạo biểu diễn, miễn dễ đọc và an toàn.

### A. Ghép chuỗi trực tiếp cho vài trường

~~~java
// Minh họa bên trong lớp Customer, có trường id và status.
@Override
public String toString() {
    return "Customer{id='" + id + "', status=" + status + "}";
}
~~~

Cách này ngắn và phù hợp với vài trường. Java biên dịch phép nối chuỗi theo cơ chế hiệu quả cho nhiều tình huống thường gặp; không cần mặc định viết `StringBuilder` chỉ để tối ưu một chuỗi nhỏ.

### B. `StringJoiner` khi cần nhiều trường

~~~java
// Minh họa bên trong lớp Job, có id, state và retries.
@Override
public String toString() {
    return new java.util.StringJoiner(", ", "Job{", "}")
            .add("id='" + id + "'")
            .add("state=" + state)
            .add("retries=" + retries)
            .toString();
}
~~~

`StringJoiner` giúp thống nhất dấu phẩy, tiền tố và hậu tố; thêm hoặc bỏ trường dễ hơn mà ít lỗi dấu phân cách. Ví dụ trong mục 4 dùng chính cơ chế này.

### C. `StringBuilder` khi có nhánh điều kiện hoặc vòng lặp cần kiểm soát

~~~java
// Minh họa phương thức trong lớp Response, với statusCode, requestId và warning.
@Override
public String toString() {
    StringBuilder result = new StringBuilder("Response{");
    result.append("statusCode=").append(statusCode);
    result.append(", requestId='").append(requestId).append("'");
    if (warning != null) {
        result.append(", warning='").append(warning).append("'");
    }
    return result.append('}').toString();
}
~~~

Cách này hữu ích khi cần thêm trường theo điều kiện. Tuy vậy, **việc ẩn trường có giá trị `null` nên là lựa chọn có chủ ý**. Nếu `warning=null` có ý nghĩa phân biệt “không có cảnh báo” với “không biết”, quyết định hiển thị cần nhất quán trong nhóm sử dụng.

### D. Record

~~~java
record Point(int x, int y) {}
~~~

Đây là **đoạn khai báo minh họa**; record đã có `toString()` sinh tự động và thường cho dạng `Point[x=1, y=2]` khi tạo `new Point(1, 2)`. Record có ích cho dữ liệu nhỏ, rõ nghĩa và không có thành phần nhạy cảm. Nhưng tự động hiển thị **mọi thành phần** có thể không phù hợp nếu record chứa bí mật hoặc object graph lớn; lúc đó cần ghi đè theo nhu cầu.

Các đoạn trong mục 5 là **mẫu thay thế**, không phải các phần phải dán liền nhau vào cùng một lớp.

## 6. Đặt tên trường, định dạng giá trị và xử lý `null`

### Dùng tên trường đúng ý nghĩa

So sánh:

~~~text
Không rõ: Transfer{A1, B9, 350}
Rõ hơn: Transfer{sourceAccount='A1', targetAccount='B9', amount=350}
~~~

Khi đọc log sau này, người vận hành có thể hiểu vai trò mỗi giá trị mà không phải tìm ngay khai báo lớp. Tránh các nhãn quá mơ hồ như `x`, `v1`, `data` nếu miền nghiệp vụ có tên rõ hơn.

### Xử lý `null` có chủ đích

Khi một trường có thể là `null`:

- `String.valueOf(value)` và `Objects.toString(value)` tạo chuỗi `"null"` cho đối tượng `null`.
- `Objects.toString(value, defaultText)` cho phép chọn chuỗi thay thế như `"<unset>"` hoặc `"<none>"`.
- Phép nối chuỗi `"field=" + value` không tự ném `NullPointerException` chỉ vì `value == null`; gọi `value.toString()` trực tiếp thì có.

Nếu `null` nghĩa là “chưa thiết lập”, nên viết `status=<unset>` hoặc `status=null` theo quy ước của nhóm, miễn người đọc hiểu được. Không biến `null` thành chuỗi rỗng khi điều đó che mất thông tin chẩn đoán quan trọng.

### Dùng biểu diễn số, ngày giờ và chuỗi nhất quán

- Với số tiền, chọn cách trình bày chính xác theo miền nghiệp vụ, ví dụ `BigDecimal.toPlainString()` cho một giá trị thập phân cần tránh ký hiệu khoa học.
- Với thời gian, nếu cần hiển thị thời điểm, nên ưu tiên dạng rõ múi giờ/offset như `Instant` hoặc `OffsetDateTime` thay vì một thời điểm mơ hồ.
- Trường `String` có thể thêm dấu nháy để phân biệt chuỗi với số hoặc giá trị `null`. Nếu dữ liệu có dấu nháy, xuống dòng hay ký tự điều khiển, cân nhắc **escape/truncate** để log không bị nhầm hoặc bị chèn dòng mới. Dấu nháy đơn quanh chuỗi trong ví dụ chỉ để người đọc dễ quan sát; ví dụ không triển khai thuật toán escape hoàn chỉnh.
- Với dữ liệu dài, chọn hiển thị `length=...`, `size=...` hoặc một bản tóm tắt có giới hạn, theo quy định bảo mật và vận hành.

`toString()` nhằm phục vụ con người; đừng kỳ vọng đầu ra luôn đúng chuẩn JSON hoặc có thể parse đáng tin từ dấu phân cách thủ công.

## 7. Mảng, collection và cấu trúc lồng nhau

Một lỗi dễ thấy là nối mảng trực tiếp:

~~~java
int[] numbers = {1, 2};
String notUseful = "numbers=" + numbers;
String useful = "numbers=" + java.util.Arrays.toString(numbers);
~~~

Đây là **đoạn minh họa**. `notUseful` có dạng tên kiểu mảng kèm mã băm theo danh tính, ví dụ `numbers=[I@...`; hậu tố không cố định. `useful` là `numbers=[1, 2]`. Với mảng tham chiếu lồng nhau không có vòng, `Arrays.deepToString(...)` giúp in nội dung sâu.

Với `List`, `Map` hoặc tập đối tượng lồng nhau, đừng mặc định gọi `toString()` của cả cấu trúc nếu kích thước lớn hoặc có tham chiếu vòng. Các chuỗi có thể quá dài và có thể kích hoạt các phương thức `toString()` của từng phần tử, gây lộ dữ liệu hoặc đệ quy ngoài dự kiến.

Ví dụ chọn mức tóm tắt:

~~~text
Ít hữu ích: Batch{items=[hàng nghìn đối tượng với nội dung dài ...]}
Phù hợp hơn: Batch{batchId='B-22', itemCount=3200, status=RUNNING}
~~~

**Về vòng tham chiếu:** Hai đối tượng `parent` và `child` có thể cùng tham chiếu nhau. Nếu mỗi `toString()` in toàn bộ đối tượng liên kết, lời gọi `parent.toString()` sẽ gọi `child.toString()` rồi quay lại `parent.toString()` và có thể dẫn đến `StackOverflowError`. Biện pháp đơn giản nhất thường là **chỉ in một mã hoặc tên tóm tắt của đối tượng được liên kết**, thay vì mở rộng toàn bộ đồ thị.

Nếu bài toán thực sự cần in đồ thị, hãy tạo **hàm debug riêng** sử dụng tập các đối tượng đã thăm theo danh tính, ví dụ `IdentityHashMap`, và đặt giới hạn số nút/độ sâu. Không bắt mọi `toString()` phải thực hiện duyệt đồ thị.

## 8. An toàn thông tin và khả năng vận hành

`toString()` có thể được gọi ngầm khi log đối tượng, in exception context hoặc gỡ lỗi. Vì vậy nó trở thành điểm **rò rỉ dữ liệu** nếu hiển thị bừa bãi:

- **Không in mật khẩu, secret, API key, access token, private key, session cookie** hoặc dữ liệu xác thực.
- Với thông tin cá nhân (email, số điện thoại, địa chỉ) và dữ liệu nghiệp vụ nhạy cảm, tuân thủ chính sách xử lý log; khi phù hợp chỉ hiển thị một ID được phép hoặc giá trị đã che hợp lệ.
- Không đưa toàn bộ request/response body, tập khách hàng hoặc file đính kèm vào `toString()` mặc định.
- Đừng phụ thuộc vào việc “log hiện tại chưa in đối tượng này”: mã ứng dụng khác có thể gọi `String.valueOf(obj)` hoặc nối `obj` vào chuỗi sau này.
- Cẩn thận với các trường có dữ liệu do người dùng nhập: xuống dòng, ký tự điều khiển hoặc chuỗi quá dài có thể gây nhiễu hoặc làm log khó phân tích. Escape/truncate theo một quy tắc rõ ràng.

Trong ví dụ `Order`, trường `customerEmail` được giữ bên trong nhưng `toString()` chỉ hiển thị `orderId`, `status`, `itemCount` và `total`. Đây là **quyết định thiết kế trong tình huống minh họa**; triển khai thực tế vẫn phải kiểm tra xem từng trường định in có được phép xuất hiện trong log không.

Ngoài ra, `toString()` nên tránh **I/O, truy vấn cơ sở dữ liệu, gọi mạng, tải lazy data, khóa đồng bộ kéo dài hoặc thay đổi trạng thái**. Một phương thức vốn được gọi chỉ để hiển thị không nên bất ngờ làm chậm hệ thống, phát sinh ngoại lệ nghiệp vụ hoặc thay đổi dữ liệu.

## 9. `toString()` không phải nơi định nghĩa tính bằng nhau

Một lỗi thiết kế khác là so sánh hai đối tượng bằng chuỗi:

~~~java
// Sai về mặt thiết kế trong đa số trường hợp:
boolean same = a.toString().equals(b.toString());
~~~

Đây là **đoạn minh họa**, giả định `a` và `b` khác `null`. Chuỗi có thể bỏ qua một số thuộc tính quan trọng, bị rút gọn, che dữ liệu hoặc thay đổi kiểu định dạng theo phiên bản. Hai đối tượng khác nhau có thể có chuỗi giống nhau; hai đối tượng bằng nhau theo nghiệp vụ cũng không nhất thiết có biểu diễn giống hệt nếu `toString()` chứa trường trạng thái ngoài định nghĩa `equals()`.

Để định nghĩa tính bằng nhau theo giá trị, hãy triển khai `equals()` và `hashCode()` theo đúng hợp đồng. Để sắp xếp, dùng `Comparable` hoặc `Comparator`. Để truyền dữ liệu qua API, dùng DTO và serializer phù hợp. `toString()` chỉ tập trung vào **biểu diễn dễ hiểu cho con người**.

Tương tự, không nên dùng `toString()` làm khóa ổn định trong `Map` hoặc làm ID lâu dài: thay đổi việc hiển thị (đổi tên trường, thêm dấu nháy, che dữ liệu) không nên làm thay đổi danh tính logic của một đối tượng.

## 10. Trước và sau khi cải tiến

Giả sử một lớp `Job` có ID, trạng thái, số lần thử, một payload dài, token bảo mật và liên kết đến Job cha.

**Thiết kế khó sử dụng:**

~~~text
Job@4317a9
Job(72, RUNNING, 3, [payload rất dài], token=..., parent=...)
~~~

Chuỗi đầu không có ngữ cảnh; chuỗi thứ hai không có tên trường, có thể dài vô hạn và nguy hiểm do token hoặc liên kết vòng.

**Thiết kế hướng đến đọc log:**

~~~text
Job{id='J-72', state=RUNNING, attempts=3, payloadBytes=8192, parentId='J-50'}
~~~

Giá trị có tên, đủ tóm tắt trạng thái công việc, dùng `payloadBytes` thay payload đầy đủ và dùng `parentId` thay việc gọi `parent.toString()`. Không hiển thị token. Người đọc cũng dễ so sánh hai lần log nếu thứ tự và tên trường ổn định.

Không bắt buộc phải hiển thị đúng 5 trường như ví dụ: thiết kế theo những câu hỏi chẩn đoán chính của chính đối tượng và độ nhạy cảm của từng thuộc tính.

## 11. Checklist khi tự triển khai và review

1. **Nhận diện:** chuỗi có tên kiểu hoặc ngữ cảnh đủ để biết đang nhìn đối tượng nào không?
2. **Tên trường:** các giá trị có nhãn dễ hiểu như `status`, `itemCount`, `orderId` hay chỉ có một dãy giá trị?
3. **Đủ dùng:** có những thuộc tính giúp chẩn đoán trạng thái quan trọng, nhưng không kéo theo dữ liệu thừa?
4. **Ngắn gọn:** collection, blob, text hoặc mảng lớn đã được giới hạn hoặc tóm tắt?
5. **Bảo mật:** chuỗi không chứa password, token hoặc dữ liệu cá nhân/trường nghiệp vụ cấm ghi log?
6. **Xử lý lồng nhau:** có nguy cơ `toString()` gọi lẫn nhau qua tham chiếu vòng không? Mảng có được định dạng phù hợp?
7. **`null`:** các trường tùy chọn được hiển thị nhất quán, không gây `NullPointerException` do gọi trực tiếp trên giá trị null?
8. **Độ ổn định:** tên trường và dấu phân cách nhất quán, không chứa thứ tự ngẫu nhiên hoặc mã băm vô nghĩa khi không cần?
9. **Tác dụng phụ:** không thay đổi đối tượng, không thực hiện I/O hoặc nghiệp vụ phức tạp?
10. **Đúng vai trò:** không bị lạm dụng như cơ chế serialize, ID lâu dài hay thay thế `equals()`/`hashCode()`?

## 12. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao `Person{An, 25}` khó dùng hơn `Person{name='An', age=25}` khi đọc log?

**Đáp án:** Chuỗi thứ hai có tên trường, người đọc hiểu ngay ý nghĩa dữ liệu và không phải đoán vị trí tham số.

**Câu 2.** Có nên in mọi phần tử trong một `List<Order>` hàng trăm nghìn mục?

**Đáp án:** Thường không. Nên dùng số lượng hoặc tóm tắt có giới hạn, tránh chuỗi quá lớn, chi phí tạo chuỗi và khả năng rò rỉ dữ liệu.

**Câu 3.** Một đối tượng `Employee` có `manager` trỏ đến đối tượng `Employee` khác, và hai đối tượng có thể trỏ ngược nhau. `toString()` nên làm gì?

**Đáp án:** Chỉ in mã hoặc tên tóm tắt của `manager`, hoặc sử dụng một hàm debug có theo dõi danh tính và giới hạn độ sâu. Không đệ quy vô hạn qua `manager.toString()`.

**Câu 4.** `record` có bảo đảm không lộ dữ liệu qua `toString()` không?

**Đáp án:** Không. Record tự sinh `toString()` từ các thành phần; nếu chúng chứa dữ liệu nhạy cảm, cần thiết kế thành phần hoặc ghi đè biểu diễn cho phù hợp.

**Câu 5.** Có nên lưu `order.toString()` làm mã đơn hàng trong cơ sở dữ liệu?

**Đáp án:** Không. Chọn mã nghiệp vụ riêng như `orderId`; biểu diễn `toString()` có thể thay đổi khi cải tiến việc gỡ lỗi, thêm/bớt trường hoặc áp dụng quy tắc bảo mật.

**Ghi nhớ:** `toString()` tốt giúp **đọc nhanh — hiểu đúng — không lộ dữ liệu**. Chọn ít trường nhưng có ý nghĩa, đặt tên rõ ràng, thể hiện `null` và cấu trúc lồng nhau có chủ đích, tránh in sâu đồ thị hoặc dữ liệu nhạy cảm. Để `toString()` là công cụ biểu diễn cho con người, không biến nó thành hợp đồng dữ liệu hay danh tính đối tượng.

## Tham khảo

- [Java SE 17 — `Object.toString()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html#toString())
- [Java SE 17 — `StringJoiner`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/StringJoiner.html)
- [Java SE 17 — `Objects.toString()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Objects.html)
