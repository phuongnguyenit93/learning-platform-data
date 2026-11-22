# Jackson là gì và giải quyết bài toán trao đổi dữ liệu nào

Hãy hình dung một ứng dụng Java có đối tượng `Order` đang nằm trong bộ nhớ. Ứng dụng cần gửi đơn hàng đó cho giao diện web, một dịch vụ Java khác, hoặc lưu thành tệp để xử lý sau. Đối tượng `Order` là cấu trúc dữ liệu của chương trình Java; một ứng dụng viết bằng JavaScript hay Python không thể nhận trực tiếp đối tượng đang nằm trong bộ nhớ JVM. Hai phía cần một cách biểu diễn dữ liệu chung mà cả hai đều có thể đọc và tạo ra.

Đó là bài toán trao đổi dữ liệu. **Jackson** là một thư viện trong hệ sinh thái Java giúp giải quyết bài toán này bằng cách chuyển đổi dữ liệu giữa các đối tượng Java và những định dạng dữ liệu có cấu trúc, phổ biến nhất là JSON.

## 1. Vì sao các ứng dụng cần trao đổi dữ liệu?

Một chương trình thường không hoạt động một mình. Nó có thể trao đổi thông tin với:

- Giao diện web hoặc ứng dụng di động.
- Một dịch vụ khác trong cùng hệ thống.
- Hệ thống của đối tác.
- Hàng đợi thông điệp hoặc một tiến trình chạy độc lập.
- Tệp cấu hình, tệp dữ liệu được lưu để đọc lại sau này.

Mỗi chương trình có thể dùng ngôn ngữ, nền tảng và cách tổ chức dữ liệu riêng. Chẳng hạn, Java biểu diễn một đơn hàng bằng class hoặc record; JavaScript có thể biểu diễn cùng thông tin bằng object. Dù cách lưu trữ trong bộ nhớ khác nhau, hai phía vẫn cần thống nhất **dữ liệu nào được gửi, tên trường là gì và mỗi trường mang kiểu giá trị nào**.

Một đối tượng Java không phải là định dạng trao đổi phù hợp vì nó gắn với cấu trúc class, kiểu dữ liệu và môi trường chạy của Java. Gửi nguyên trạng vùng nhớ của một đối tượng cũng không tạo ra một hợp đồng dữ liệu ổn định cho chương trình khác. Thay vào đó, hệ thống thường chuyển dữ liệu thành một biểu diễn có cấu trúc, độc lập với ngôn ngữ, rồi truyền biểu diễn đó qua HTTP, ghi vào tệp hoặc gửi qua message broker.

Ví dụ, thông tin một đơn hàng có thể được biểu diễn bằng JSON như sau:

```json
{
  "id": "DH-1001",
  "amount": 129.50,
  "paid": true
}
```

JSON thể hiện dữ liệu bằng văn bản với các kiểu giá trị cơ bản như object, array, string, number, boolean và null. Nhiều ngôn ngữ có thư viện để đọc và tạo JSON, vì vậy các hệ thống có thể thống nhất cách trao đổi mà không cần dùng chung class Java.

## 2. Jackson là gì?

Jackson là một bộ thư viện mã nguồn mở dành cho Java, được dùng để đọc, ghi và chuyển đổi dữ liệu có cấu trúc. JSON là định dạng Jackson thường gặp nhất trong ứng dụng Java, đặc biệt khi xây dựng REST API.

Điểm cần phân biệt:

- **JSON** là một định dạng biểu diễn dữ liệu.
- **Jackson** là thư viện Java có thể đọc và ghi JSON, đồng thời hỗ trợ các cách làm việc với dữ liệu có cấu trúc khác thông qua các thành phần mở rộng.
- **Đối tượng Java** là dữ liệu được chương trình biểu diễn trong bộ nhớ bằng class, record, collection và các kiểu Java khác.

Jackson đứng giữa đối tượng Java và biểu diễn dữ liệu cần trao đổi. Nó giúp chương trình không phải tự ghép từng chuỗi JSON hoặc tự phân tích từng ký tự để dựng lại đối tượng.

Trong hệ sinh thái Jackson, ba thành phần thường được nhắc đến là:

| Thành phần | Vai trò chính |
| --- | --- |
| `jackson-core` | Đọc và ghi JSON ở mức luồng token, cung cấp nền tảng xử lý JSON. |
| `jackson-databind` | Ánh xạ dữ liệu JSON với object Java và cung cấp API như `ObjectMapper`. |
| `jackson-annotations` | Cung cấp annotation để điều khiển cách ánh xạ, chẳng hạn tên thuộc tính trong JSON. |

Khi mới bắt đầu, bạn thường làm việc trực tiếp với `ObjectMapper` thuộc `jackson-databind`. Các thành phần bên dưới phối hợp để phân tích JSON, xác định giá trị và tạo ra kết quả Java tương ứng.

## 3. Hai chiều chuyển đổi: Serialization và Deserialization

Trao đổi dữ liệu thường cần hai chiều chuyển đổi.

### Serialization: từ đối tượng Java sang JSON

Serialization (tuần tự hóa) là quá trình chuyển dữ liệu trong chương trình thành một biểu diễn có thể ghi hoặc truyền đi. Với Jackson, một trường hợp phổ biến là chuyển object Java thành chuỗi JSON.

Ví dụ, ứng dụng đang có một đơn hàng:

```java
Order order = new Order("DH-1001", new BigDecimal("129.50"), true);
```

Jackson có thể chuyển object đó thành JSON:

```json
{
  "id": "DH-1001",
  "amount": 129.50,
  "paid": true
}
```

Sau bước này, ứng dụng có thể ghi chuỗi JSON vào tệp hoặc đưa nó cho thành phần HTTP để gửi đến client. Bên nhận không cần biết object ban đầu được tạo từ class hay record nào trong Java.

### Deserialization: từ JSON sang đối tượng Java

Deserialization (giải tuần tự hóa) là chiều ngược lại: đọc dữ liệu đã được biểu diễn, phân tích cấu trúc của nó và tạo ra giá trị hoặc object tương ứng trong chương trình.

Ví dụ, server nhận được JSON:

```json
{
  "id": "DH-1001",
  "amount": 129.50,
  "paid": true
}
```

Jackson có thể ánh xạ các trường `id`, `amount` và `paid` vào một đối tượng `Order`. Sau đó, code Java có thể đọc `order.id()`, `order.amount()` hoặc `order.paid()` như dữ liệu Java thông thường.

Có thể nhớ hai chiều này bằng bảng sau:

| Hướng chuyển đổi | Tên gọi | Kết quả |
| --- | --- | --- |
| Java object → JSON | Serialization | Dữ liệu dạng JSON để ghi hoặc gửi đi |
| JSON → Java object | Deserialization | Object hoặc giá trị Java để chương trình xử lý |

## 4. Ví dụ tối giản với ObjectMapper

`ObjectMapper` là API cấp cao thường dùng để chuyển đổi giữa JSON và kiểu Java. Ví dụ sau dùng một Java record để mô tả đơn hàng:

```java
import com.fasterxml.jackson.databind.ObjectMapper;

import java.math.BigDecimal;

record Order(String id, BigDecimal amount, boolean paid) {}

public class JacksonExample {
    public static void main(String[] args) throws Exception {
        ObjectMapper mapper = new ObjectMapper();

        // Dữ liệu đang tồn tại dưới dạng object Java.
        Order original = new Order(
                "DH-1001",
                new BigDecimal("129.50"),
                true
        );

        // Serialization: object Java -> chuỗi JSON.
        String json = mapper.writeValueAsString(original);
        System.out.println(json);

        // Deserialization: chuỗi JSON -> object Java.
        Order restored = mapper.readValue(json, Order.class);
        System.out.println(restored.amount());
    }
}
```

Trong ví dụ này:

1. `ObjectMapper` là đối tượng cung cấp các thao tác ánh xạ JSON.
2. `writeValueAsString(original)` đọc dữ liệu từ object và tạo chuỗi JSON.
3. `readValue(json, Order.class)` phân tích JSON và tạo một `Order`.
4. `Order.class` cho Jackson biết kiểu Java mà kết quả cần được ánh xạ vào.

Ví dụ tập trung vào ý tưởng chuyển đổi. Trong dự án thực tế, class hoặc record dùng để nhận và trả dữ liệu thường được thiết kế như DTO (Data Transfer Object), phù hợp với hợp đồng API của hệ thống.

## 5. Jackson tham gia vào quá trình trao đổi dữ liệu như thế nào?

Trong một API, dữ liệu thường đi qua một luồng như sau:

```text
Client
  │
  │ gửi JSON trong HTTP request
  ▼
HTTP message converter + Jackson
  │
  │ deserialization
  ▼
Java DTO
  │
  │ xử lý nghiệp vụ
  ▼
Java DTO hoặc kết quả trả về
  │
  │ serialization
  ▼
HTTP message converter + Jackson
  │
  │ JSON trong HTTP response
  ▼
Client
```

Khi client gửi request, Jackson giúp chuyển phần JSON trong request thành kiểu Java mà controller hoặc tầng xử lý có thể sử dụng. Khi server trả kết quả, Jackson giúp chuyển object Java thành JSON trong response.

Với Spring Boot Web, khi các dependency phù hợp có mặt, framework thường tích hợp Jackson thông qua HTTP message converter. Vì vậy, controller có thể nhận một DTO làm tham số và trả về một object; Spring MVC phối hợp với converter để đọc hoặc ghi JSON. Jackson đảm nhiệm việc ánh xạ dữ liệu, còn Spring MVC quản lý luồng xử lý HTTP và gọi controller.

Điều này cũng cho thấy Jackson không phải là REST API hay giao thức HTTP. HTTP quy định cách request và response được truyền; REST là phong cách thiết kế API; JSON là định dạng dữ liệu; Jackson là thư viện Java giúp đọc và ghi định dạng đó.

## 6. Jackson có thể ánh xạ những loại dữ liệu nào?

Với cơ chế ánh xạ dữ liệu, Jackson có thể làm việc với nhiều cấu trúc thường gặp:

- **Kiểu đơn giản:** `String`, số, `boolean` và các kiểu tương ứng.
- **Object:** class hoặc record có các thuộc tính.
- **Object lồng nhau:** một object chứa object khác.
- **Collection:** `List`, mảng và các cấu trúc tập hợp phù hợp.
- **Map:** dữ liệu dạng cặp khóa và giá trị.
- **Enum:** các giá trị được định nghĩa trong một kiểu liệt kê.
- **Cây JSON:** dùng `JsonNode` khi muốn đọc hoặc thao tác với cấu trúc JSON mà chưa cần ánh xạ ngay vào một class cụ thể.

Jackson còn có các module để hỗ trợ những kiểu dữ liệu hoặc định dạng bổ sung. Chẳng hạn, dự án có thể bổ sung module phù hợp khi cần xử lý kiểu ngày giờ của Java Time. Khả năng ánh xạ cụ thể phụ thuộc vào phiên bản, module và cấu hình đang dùng.

## 7. Jackson giải quyết phần nào và không giải quyết phần nào?

Jackson tập trung vào việc đọc, ghi và ánh xạ cấu trúc dữ liệu. Nó không tự quyết định ý nghĩa nghiệp vụ của dữ liệu.

Ví dụ, Jackson có thể đọc trường `amount` thành `BigDecimal`, nhưng việc số tiền đó có hợp lệ với đơn hàng hay người dùng có quyền thanh toán hay không thuộc về validation và logic nghiệp vụ. Tương tự, Jackson có thể tạo JSON, nhưng không tự gửi HTTP request, xác thực người gọi, mã hóa kết nối hay bảo đảm thông điệp được giao đến hệ thống đích.

Khi thiết kế dữ liệu trao đổi, ứng dụng vẫn cần thống nhất các quy tắc như:

- Tên trường trong JSON và kiểu giá trị của từng trường.
- Trường nào bắt buộc, trường nào có thể vắng mặt hoặc nhận `null`.
- Cách biểu diễn ngày giờ, số thập phân và giá trị enum.
- Cách xử lý trường mới hoặc trường không còn được sử dụng khi hai phía được triển khai ở thời điểm khác nhau.
- Trường nào được phép công khai ra bên ngoài.

Đặc biệt, không nên mặc định rằng mọi field trong entity nội bộ đều phù hợp để đưa thẳng ra API. DTO giúp xác định rõ dữ liệu nào thuộc hợp đồng trao đổi, tránh vô tình công khai thông tin nội bộ hoặc làm API phụ thuộc quá chặt vào mô hình lưu trữ.

Nếu JSON không khớp với kiểu Java mong đợi, quá trình ánh xạ có thể thất bại. Ví dụ, một trường được mong đợi là số nhưng phía gửi lại cung cấp một chuỗi không thể chuyển đổi. Khi đó ứng dụng cần xử lý lỗi đầu vào phù hợp; Jackson không thể tự suy đoán chính xác ý nghĩa nghiệp vụ thay cho chương trình.

## 8. Khi nào nên nghĩ đến Jackson?

Jackson hữu ích khi một ứng dụng Java cần:

1. Nhận JSON từ REST API và chuyển thành DTO để xử lý.
2. Chuyển kết quả Java thành JSON để trả về client.
3. Đọc hoặc ghi dữ liệu JSON trong tệp.
4. Gửi và nhận payload JSON qua hệ thống message hoặc tích hợp với dịch vụ khác.
5. Phân tích JSON linh hoạt bằng cây dữ liệu khi cấu trúc đầu vào chưa cố định hoàn toàn.

Trong những tình huống này, Jackson đảm nhận phần chuyển đổi giữa biểu diễn dữ liệu bên ngoài và kiểu dữ liệu mà chương trình Java sử dụng. Nhờ vậy, code nghiệp vụ có thể làm việc với object Java thay vì phải tự xử lý chuỗi JSON ở mọi nơi.

## Ghi nhớ

Jackson là bộ thư viện xử lý dữ liệu cho Java, thường được dùng nhất để làm việc với JSON. Nó giải quyết nhu cầu chuyển đổi dữ liệu giữa các object Java và một biểu diễn có cấu trúc mà những ứng dụng hoặc ngôn ngữ khác có thể trao đổi.

- Java object sang JSON là **serialization**.
- JSON sang Java object là **deserialization**.
- `ObjectMapper` là API cấp cao phổ biến để thực hiện hai chiều chuyển đổi.
- Jackson xử lý việc đọc, ghi và ánh xạ dữ liệu; hợp đồng API, validation, nghiệp vụ và truyền tải thuộc những phần trách nhiệm khác của ứng dụng.
