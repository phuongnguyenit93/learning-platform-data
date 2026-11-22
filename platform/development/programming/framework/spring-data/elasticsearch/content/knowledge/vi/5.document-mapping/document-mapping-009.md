# Type hint, trường `_class` và ánh xạ kiểu đa hình

Spring Data Elasticsearch chuyển đổi entity Java thành document JSON và chuyển document tìm được trở lại object Java. Khi thuộc tính Java có kiểu cụ thể, converter thường có thể biết cần tạo class nào từ khai báo thuộc tính. Nhưng khi thuộc tính được khai báo bằng interface, abstract class hoặc kiểu cha trong một cây kế thừa, converter cần thêm thông tin để nhận diện class thực tế.

Spring Data Elasticsearch giải quyết việc đó bằng **type hint**. Theo mặc định, type hint được ghi vào trường `_class` trong `_source`. Giá trị thường là tên đầy đủ của class Java; có thể thay bằng tên bí danh ổn định với `@TypeAlias`. Type hint giúp converter khôi phục kiểu runtime, đặc biệt khi document chứa object đa hình.

## 1. Type hint và `_class` là gì?

Giả sử một đơn hàng có thể thanh toán bằng thẻ hoặc chuyển khoản. Trong Java, thuộc tính `paymentMethod` có thể được khai báo bằng interface `PaymentMethod`, nhưng object thực tế lại là `CardPayment` hoặc `BankTransfer`.

Khi ghi document, Spring Data cần lưu dấu hiệu cho biết object đó thuộc class cụ thể nào. Type hint là metadata do Spring Data thêm vào document. Với cấu hình mặc định, metadata này có dạng:

~~~json
{
  "_class": "com.example.payment.CardPayment",
  "lastFourDigits": "4242"
}
~~~

`_class` là tên trường type hint mặc định. Đây là một thuộc tính trong JSON `_source` do Spring Data sử dụng, không phải metadata field đặc biệt của Elasticsearch như `_id`, `_index` hoặc `_version`. Elasticsearch không dùng `_class` để tự khởi tạo object Java; Spring Data đọc trường này trong quá trình mapping.

Type hint thường xuất hiện ở document gốc và các object phức hợp khi converter cần giữ thông tin kiểu. Giá trị mặc định thường là fully qualified class name, bao gồm package và tên class.

## 2. Vì sao cần type hint?

Với thuộc tính có kiểu cụ thể, converter đã biết class đích từ khai báo entity:

~~~java
public class Product {
    private Brand brand;
}
~~~

Khi đọc `Product`, Spring Data biết `brand` phải được chuyển thành `Brand`.

Nhưng với kiểu interface hoặc abstract class, khai báo không xác định được implementation cần tạo:

~~~java
public interface PaymentMethod {
    String getReference();
}

public class Order {
    private PaymentMethod paymentMethod;
}
~~~

`PaymentMethod` không thể được khởi tạo trực tiếp. Nếu document lưu một `CardPayment`, converter cần biết class thực tế để tạo đúng object và gán vào thuộc tính `paymentMethod`. Type hint cung cấp thông tin đó.

Type hint cũng hữu ích khi một thuộc tính được khai báo bằng class cha nhưng document chứa instance của class con. Nếu không có thông tin kiểu, converter có thể chỉ biết kiểu khai báo hoặc không thể khôi phục implementation mong muốn.

## 3. Ánh xạ kiểu đa hình bằng `_class`

Ví dụ mô hình có hai phương thức thanh toán:

~~~java
public interface PaymentMethod {
    String getReference();
}

public class CardPayment implements PaymentMethod {
    private String reference;
    private String lastFourDigits;

    // Constructor, getters và setters
}

public class BankTransfer implements PaymentMethod {
    private String reference;
    private String bankCode;

    // Constructor, getters và setters
}
~~~

Entity đơn hàng chứa danh sách các phương thức thanh toán:

~~~java
import java.util.List;

import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "orders")
public class Order {

    @Id
    private String id;

    @Field(type = FieldType.Nested)
    private List<PaymentMethod> paymentMethods;

    // Constructor, getters và setters
}
~~~

Khi lưu một `Order` chứa `CardPayment` và `BankTransfer`, `_source` có thể có cấu trúc minh họa như sau:

~~~json
{
  "_class": "com.example.order.Order",
  "paymentMethods": [
    {
      "_class": "com.example.payment.CardPayment",
      "reference": "PAY-001",
      "lastFourDigits": "4242"
    },
    {
      "_class": "com.example.payment.BankTransfer",
      "reference": "PAY-002",
      "bankCode": "EXAMPLE"
    }
  ]
}
~~~

Khi đọc document, converter sử dụng type hint của từng phần tử để nhận ra implementation tương ứng. Kết quả Java có thể là một `List<PaymentMethod>` gồm một object `CardPayment` và một object `BankTransfer`.

`@Field(type = FieldType.Nested)` trong ví dụ điều khiển cách Elasticsearch lập chỉ mục mảng object để có thể truy vấn các điều kiện trên cùng một phần tử. Nó không tạo ra type hint. Hai chức năng độc lập:

- `_class` giúp Spring Data xác định class Java thực tế khi chuyển đổi dữ liệu.
- `FieldType.Nested` yêu cầu Elasticsearch giữ quan hệ giữa các field trong cùng một phần tử mảng khi lập chỉ mục và truy vấn.

Nếu không cần ngữ nghĩa truy vấn nested của Elasticsearch, thuộc tính object có thể dùng mapping `object` phù hợp. Chọn `object` hay `nested` theo nhu cầu truy vấn; không chọn `nested` chỉ vì Java có interface hoặc class con.

## 4. Dùng `@TypeAlias` thay cho tên class đầy đủ

Giá trị mặc định của `_class` thường chứa package và tên class. Ví dụ:

~~~json
{
  "_class": "com.example.payment.CardPayment"
}
~~~

Điều này tạo liên hệ giữa dữ liệu đã lưu và tên class trong source code. Nếu chuyển class sang package khác hoặc đổi tên class, các document cũ vẫn giữ tên cũ và converter có thể không tìm được class tương ứng.

`@TypeAlias` cho phép đặt tên ngắn, ổn định hơn cho type hint. Annotation thuộc `org.springframework.data.annotation.TypeAlias`.

~~~java
import org.springframework.data.annotation.TypeAlias;

@TypeAlias("card-payment")
public class CardPayment implements PaymentMethod {
    private String reference;
    private String lastFourDigits;

    // Constructor, getters và setters
}

@TypeAlias("bank-transfer")
public class BankTransfer implements PaymentMethod {
    private String reference;
    private String bankCode;

    // Constructor, getters và setters
}
~~~

Khi ghi document, type hint có thể dùng alias:

~~~json
{
  "paymentMethods": [
    {
      "_class": "card-payment",
      "reference": "PAY-001",
      "lastFourDigits": "4242"
    },
    {
      "_class": "bank-transfer",
      "reference": "PAY-002",
      "bankCode": "EXAMPLE"
    }
  ]
}
~~~

Alias giúp dữ liệu ít phụ thuộc vào package và tên class Java. Khi refactor package hoặc đổi tên implementation, có thể giữ alias cũ để document hiện hữu tiếp tục được ánh xạ tới class mới.

### 4.1. Đăng ký type alias trong mapping context

`@TypeAlias` chỉ có tác dụng khi Spring Data Elasticsearch biết class được gắn alias. Mapping context phải nhận diện các entity đó để xây dựng quan hệ giữa alias và `TypeInformation` tương ứng.

Vì vậy, hãy bảo đảm các implementation đa hình được đưa vào entity scanning hoặc được đăng ký trong cấu hình mapping context của ứng dụng. Chỉ thêm annotation vào một class mà ứng dụng chưa bao giờ nhận diện không đảm bảo converter có thể phân giải alias khi đọc document.

Khi một alias không được nhận diện, dữ liệu có thể không được chuyển đổi về class mong muốn. Hãy kiểm tra entity scanning/registration và đảm bảo alias duy nhất trong phạm vi mapping context.

## 5. Type hint ở document gốc và object lồng nhau

Type hint có thể xuất hiện ở nhiều cấp của `_source`:

~~~json
{
  "_class": "order-v1",
  "customer": {
    "_class": "individual-customer",
    "fullName": "Nguyen An"
  },
  "paymentMethods": [
    {
      "_class": "card-payment",
      "lastFourDigits": "4242"
    }
  ]
}
~~~

Trong ví dụ này:

- Type hint ở cấp gốc xác định kiểu entity được lưu.
- Type hint trong `customer` xác định implementation thực tế của object khách hàng nếu thuộc tính được khai báo bằng kiểu cha/interface.
- Type hint trong từng phần tử `paymentMethods` xác định implementation tương ứng cho phần tử đó.

Không phải mọi field đều cần type hint. Các giá trị đơn như chuỗi, số, boolean hoặc ngày giờ đã có kiểu rõ ràng từ mapping và không cần xác định class Java riêng. Type hint có ý nghĩa với entity và object phức hợp, đặc biệt khi kiểu runtime có thể khác kiểu khai báo.

## 6. Phân biệt `_class` với field nghiệp vụ và mapping Elasticsearch

`_class` là metadata phục vụ quá trình chuyển đổi object của Spring Data. Không nên dùng nó thay cho một field nghiệp vụ như `paymentType`, `customerType` hoặc `documentKind`.

Ví dụ, nếu ứng dụng cần lọc các đơn hàng thanh toán bằng thẻ, nên lưu một field nghiệp vụ có ý nghĩa rõ ràng:

~~~json
{
  "paymentType": "CARD",
  "paymentMethods": [
    {
      "_class": "card-payment",
      "lastFourDigits": "4242"
    }
  ]
}
~~~

Field `paymentType` có thể được khai báo `keyword` và dùng trong query, aggregation hoặc báo cáo. `_class` phản ánh cấu trúc Java hiện tại và có thể thay đổi khi refactor code; vì vậy nó không phải hợp đồng dữ liệu nghiệp vụ ổn định.

`_class` cũng không phải trường `type` trong mapping Elasticsearch. Mapping định nghĩa cách field được lập chỉ mục, ví dụ `keyword`, `text`, `object` hoặc `nested`. Type hint chỉ cho Spring Data biết cách dựng object Java từ `_source`.

Khi Elasticsearch sử dụng dynamic mapping, field `_class` có thể được nhận diện như một field chuỗi. Nếu mapping đặt `dynamic: strict`, mọi field được ghi vào document phải được khai báo trước; khi đó cần tính cả `_class` vào mapping hoặc cấu hình type hint phù hợp với phiên bản Spring Data đang dùng. Nếu `dynamic: false`, field không được lập chỉ mục nhưng vẫn có thể nằm trong `_source` để converter đọc.

Ví dụ khai báo mapping tường minh cho type hint và các field đa hình:

~~~json
{
  "mappings": {
    "properties": {
      "_class": { "type": "keyword" },
      "paymentMethods": {
        "type": "nested",
        "properties": {
          "_class": { "type": "keyword" },
          "reference": { "type": "keyword" },
          "lastFourDigits": { "type": "keyword" },
          "bankCode": { "type": "keyword" }
        }
      }
    }
  }
}
~~~

Khai báo `_class` thành `keyword` hữu ích nếu cần lưu field trong mapping tường minh hoặc quan sát giá trị type hint. Thông thường, ứng dụng không cần query theo `_class` để xử lý nghiệp vụ.

## 7. Điều gì xảy ra khi thiếu hoặc không đọc được type hint?

Kết quả phụ thuộc vào kiểu khai báo của thuộc tính và dữ liệu còn lại trong `_source`:

| Trường hợp | Hành vi có thể xảy ra |
| --- | --- |
| Thuộc tính khai báo bằng class cụ thể và `_class` không có | Converter có thể dùng kiểu khai báo để dựng object. |
| Thuộc tính khai báo bằng interface/abstract class và `_class` không có | Converter không biết implementation cần tạo; quá trình đọc có thể thất bại. |
| `_class` chứa tên class hoặc alias không phân giải được | Converter không thể ánh xạ type hint sang kiểu Java đã biết. |
| `_class` trỏ tới implementation đã bị xóa hoặc đổi package | Document cũ có thể không còn đọc được nếu không có alias hoặc chiến lược tương thích. |
| `_class` bị loại khỏi kết quả `_source` | Converter mất thông tin kiểu cần thiết cho các thuộc tính đa hình. |

Khi gặp lỗi chuyển đổi, kiểm tra nội dung `_source` trước, sau đó kiểm tra kiểu khai báo của property, alias và danh sách entity đã được đăng ký. Không nên giải quyết lỗi bằng cách đổi toàn bộ property về `Object`, vì khi đó ứng dụng mất kiểu dữ liệu rõ ràng và phải tự xử lý việc chuyển đổi.

## 8. Source filtering và type hint

Elasticsearch cho phép chỉ trả về một phần `_source` để giảm payload. Tuy nhiên, nếu kết quả chứa thuộc tính đa hình, việc lọc bỏ `_class` có thể khiến Spring Data không biết class cụ thể cần tạo.

Ví dụ query sau chỉ lấy các field dữ liệu mà không lấy type hint:

~~~json
{
  "_source": [
    "paymentMethods.reference",
    "paymentMethods.lastFourDigits"
  ],
  "query": {
    "match_all": {}
  }
}
~~~

Nếu ứng dụng chuyển kết quả này thành `Order` và `paymentMethods` được khai báo bằng `PaymentMethod`, converter có thể không khôi phục được implementation. Khi dùng source filtering, cần giữ các đường dẫn `_class` cần thiết, ví dụ `paymentMethods._class`, cùng những field dữ liệu muốn đọc.

Không áp dụng source filtering một cách máy móc cho mọi repository. Nếu dùng projection hoặc DTO không cần ánh xạ đa hình, có thể chủ động bỏ type hint; nếu chuyển thành entity gốc, hãy giữ metadata cần thiết cho converter.

## 9. Thay đổi class và dữ liệu đã lưu

Type hint mặc định chứa tên class đầy đủ khiến việc đổi package hoặc tên class có thể ảnh hưởng dữ liệu cũ. Ví dụ:

~~~text
Trước refactor:
com.example.payment.CardPayment

Sau refactor:
com.acme.checkout.payment.CardPayment
~~~

Các document đã lưu vẫn chứa tên cũ. Khi đọc, mapping context hiện tại có thể không tìm được class tương ứng.

Có một số cách quản lý thay đổi:

1. Dùng `@TypeAlias` ổn định ngay từ đầu cho các kiểu có vòng đời dữ liệu dài.
2. Khi refactor, giữ alias cũ và ánh xạ alias đó tới implementation mới.
3. Nếu đã ghi fully qualified class name vào dữ liệu, thực hiện chuyển đổi dữ liệu/reindex hoặc có chiến lược tương thích để đọc tên cũ.
4. Kiểm thử đọc document cũ trước khi triển khai phiên bản code mới.

Ví dụ giữ alias qua refactor:

~~~java
@TypeAlias("card-payment")
public class CardPaymentV2 implements PaymentMethod {
    private String reference;
    private String lastFourDigits;

    // Constructor, getters và setters
}
~~~

Document cũ có `_class: "card-payment"` vẫn có thể được ánh xạ tới class mới nếu mapping context đã nhận diện alias đó và cấu trúc dữ liệu tương thích. Nếu tên class cũ đã được ghi trực tiếp vào `_class`, việc thêm alias mới không tự động đổi giá trị trong document cũ; cần kiểm tra và lên kế hoạch chuyển đổi.

## 10. Khi nào nên giữ hoặc tắt type hint?

Với entity có thuộc tính đa hình, type hint thường cần thiết để converter khôi phục đúng kiểu runtime. Nếu mọi thuộc tính đều có kiểu cụ thể, schema ổn định và ứng dụng không cần lưu thông tin class, có thể cân nhắc giảm hoặc tắt việc ghi type hint để `_source` gọn hơn.

Một số phiên bản Spring Data Elasticsearch cung cấp tùy chọn cấu hình việc ghi type hint ở cấp `@Document` hoặc thông qua mapping converter/type mapper. API và phạm vi tác động phụ thuộc phiên bản thư viện; cần kiểm tra tài liệu đúng phiên bản đang sử dụng trước khi thay đổi.

Trước khi tắt type hint, hãy xác nhận:

- Không có property interface hoặc abstract class cần khôi phục implementation.
- Không có nested object đa hình phụ thuộc vào type hint.
- Các document hiện có và mới có thể được chuyển đổi với kiểu khai báo hiện tại.
- Mapping không ở chế độ strict gây xung đột với field `_class` đang được ghi.
- Các source filter, projection và query đang dùng không phụ thuộc vào type hint.

Nếu muốn tùy chỉnh tên field type hint hoặc cách ánh xạ class, Spring Data có thể được cấu hình bằng type mapper/mapping converter. Đây là thay đổi ở tầng mapping; cần giữ tương thích với document cũ và mọi ứng dụng khác đọc cùng index.

## 11. Ví dụ đầy đủ với `@TypeAlias`

Các class implementation dùng alias ổn định:

~~~java
import org.springframework.data.annotation.TypeAlias;

@TypeAlias("card-payment")
public class CardPayment implements PaymentMethod {
    private String reference;
    private String lastFourDigits;

    // Constructor, getters và setters
}

@TypeAlias("bank-transfer")
public class BankTransfer implements PaymentMethod {
    private String reference;
    private String bankCode;

    // Constructor, getters và setters
}
~~~

Entity gốc:

~~~java
import java.util.List;

import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.TypeAlias;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "orders")
@TypeAlias("order-v1")
public class Order {

    @Id
    private String id;

    @Field(type = FieldType.Nested)
    private List<PaymentMethod> paymentMethods;

    // Constructor, getters và setters
}
~~~

Khi ghi entity, Spring Data lấy `id` làm metadata `_id` của Elasticsearch; type hint của entity và các phần tử đa hình được ghi vào `_source`. Khi đọc, converter phân giải alias `order-v1`, `card-payment` và `bank-transfer` thành các class đã được mapping context nhận diện.

Kết quả là code nghiệp vụ có thể làm việc với interface `PaymentMethod`, còn object cụ thể vẫn được khôi phục đúng sau khi đọc từ Elasticsearch.

## 12. Quy trình thiết kế và kiểm tra

Khi thiết kế mapping có kiểu đa hình, hãy thực hiện theo trình tự:

1. Xác định property nào thực sự cần đa hình; chỉ dùng interface hoặc abstract class khi có nhiều implementation hợp lệ.
2. Quyết định có cần lưu type hint để khôi phục implementation hay không.
3. Dùng `@TypeAlias` ổn định cho các class có dữ liệu tồn tại lâu dài hoặc có khả năng refactor package/tên class.
4. Đảm bảo các implementation được mapping context nhận diện.
5. Chọn Elasticsearch field type `object` hoặc `nested` theo nhu cầu query, độc lập với type hint.
6. Kiểm tra mapping nếu index dùng `dynamic: strict`, và đảm bảo `_class` không bị loại khỏi `_source` trong các luồng cần khôi phục entity.
7. Tạo document bằng từng implementation, đọc lại qua repository/`ElasticsearchOperations` và xác nhận class runtime.
8. Kiểm thử dữ liệu cũ sau khi đổi alias, package hoặc cấu hình type mapper.

Type hint và `_class` là cầu nối giữa cấu trúc object Java và document JSON. Chúng cho phép Spring Data Elasticsearch khôi phục kiểu cụ thể khi thuộc tính được khai báo bằng kiểu cha hoặc interface. Dùng alias ổn định, đăng ký đầy đủ entity và giữ type metadata trong `_source` khi cần sẽ giúp dữ liệu tiếp tục đọc được qua các lần thay đổi code.
