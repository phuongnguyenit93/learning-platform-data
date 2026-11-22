# Oneof và lựa chọn field

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Dùng **oneof** để mô tả một nhóm field mà tại một thời điểm chỉ có tối đa một lựa chọn được đặt.
- Khai báo lựa chọn bằng scalar, enum hoặc nested message trong proto3.
- Dùng API Java như **getXxxCase()**, **hasXxx()**, **setXxx()** và **clearXxx()** để đọc và cập nhật lựa chọn.
- Hiểu presence của oneof khi field mang giá trị mặc định, và cách oneof được biểu diễn trong Protobuf binary/ProtoJSON.
- Thiết kế request gRPC có nhiều dạng dữ liệu thay thế, đồng thời đánh giá các giới hạn tương thích khi thay đổi oneof.

## 1. Khi nào cần oneof?

Trong hợp đồng **SPRING_GRPC**, một request đôi khi có nhiều cách biểu diễn cùng một ý định. Ví dụ, phương thức thanh toán có thể dùng thẻ hoặc chuyển khoản; bộ lọc tìm kiếm có thể chọn theo mã hoặc theo email; đích liên hệ có thể là số điện thoại hoặc địa chỉ email.

Nếu khai báo các field độc lập:

~~~proto
message PaymentRequest {
  CardPayment card = 1;
  BankTransfer bank_transfer = 2;
}
~~~

message có thể chứa đồng thời cả card và bank_transfer, hoặc không có field nào. Server phải tự xác định trường hợp nào hợp lệ và xử lý xung đột.

**oneof** diễn đạt trực tiếp rằng một nhóm lựa chọn có tối đa một field được đặt:

~~~proto
message PaymentRequest {
  oneof payment_method {
    CardPayment card = 1;
    BankTransfer bank_transfer = 2;
  }
}
~~~

Một message có thể không chọn phương thức nào, hoặc chọn một trong các phương thức. Nếu client đặt card rồi đặt bank_transfer, lựa chọn card bị thay thế. Oneof giúp schema và API Java thể hiện quy tắc loại trừ này thay vì để từng server tự suy luận.

## 2. Khai báo oneof trong proto3

Cú pháp gồm tên nhóm và các field thành viên:

~~~proto
syntax = "proto3";

package learning.payment.v1;

option java_package = "com.example.payment.v1";
option java_multiple_files = true;

message CardPayment {
  string token = 1;
  string last_four = 2;
}

message BankTransfer {
  string bank_code = 1;
  string account_reference = 2;
}

message PaymentRequest {
  string order_id = 1;

  oneof payment_method {
    CardPayment card = 2;
    BankTransfer bank_transfer = 3;
  }
}
~~~

Trong schema:

- **payment_method** là tên nhóm oneof, không phải một field được truyền riêng.
- **card** và **bank_transfer** là các field thành viên, mỗi field vẫn có số hiệu riêng.
- Các thành viên có thể là scalar, enum hoặc message.
- Một oneof có thể có nhiều lựa chọn, nhưng tại một thời điểm chỉ có tối đa một lựa chọn hiện diện.
- Field number vẫn tuân theo quy tắc Protobuf thông thường: duy nhất trong message, không dùng số 0 và không tái sử dụng số đã phát hành.

Oneof không tạo một message bao ngoài trong binary wire. Field đang được chọn được mã hóa như field Protobuf thông thường bằng số hiệu và kiểu wire của chính nó.

## 3. Những kiểu field nào có thể nằm trong oneof?

Oneof có thể chứa:

- Scalar như **string**, **bool**, **int32**, **bytes**.
- Enum.
- Message, bao gồm nested message và well-known type.

Không thể khai báo trực tiếp **repeated** hoặc **map** làm thành viên oneof. Cũng không đặt nhãn **optional** trước một field bên trong oneof; chính oneof đã quản lý presence của lựa chọn.

Ví dụ hợp lệ:

~~~proto
syntax = "proto3";

package learning.search.v1;
option java_package = "com.example.search.v1";
option java_multiple_files = true;

message SearchCriterion {
  oneof value {
    string text = 1;
    int64 numeric_id = 2;
    bool active = 3;
  }
}
~~~

Nếu cần một lựa chọn là danh sách, hãy bọc danh sách trong message:

~~~proto
message StringValues {
  repeated string values = 1;
}

message Filter {
  oneof criterion {
    string exact_value = 1;
    StringValues any_of = 2;
  }
}
~~~

Lúc này **any_of** là message field trong oneof; repeated field nằm bên trong message StringValues. Cách bọc này cũng hữu ích khi một lựa chọn cần thêm metadata hoặc các thuộc tính đi kèm.

## 4. Java API: xác định lựa chọn hiện tại

Với oneof **payment_method**, Java code được sinh có enum case để chỉ lựa chọn hiện tại. Tên enum case được tạo từ tên nhóm, ví dụ **PaymentMethodCase**.

Các API chính:

| API | Ý nghĩa |
| --- | --- |
| **getPaymentMethodCase()** | Trả về lựa chọn hiện tại hoặc **PAYMENT_METHOD_NOT_SET**. |
| **getCard()** | Trả message CardPayment; nếu không được chọn thì trả default instance. |
| **getBankTransfer()** | Trả message BankTransfer; nếu không được chọn thì trả default instance. |
| **hasCard()**, **hasBankTransfer()** | Kiểm tra thành viên tương ứng có đang được chọn hay không. |
| **clearPaymentMethod()** trên builder | Xóa lựa chọn hiện tại của cả nhóm. |

Tên hằng case chính xác được xác định bởi code generator; với Java Protobuf thông dụng, enum case có các giá trị theo tên field và một giá trị kết thúc bằng **_NOT_SET**.

~~~java
import com.example.payment.v1.PaymentRequest;
import com.example.payment.v1.CardPayment;

PaymentRequest noMethod = PaymentRequest.newBuilder()
    .setOrderId("O-42")
    .build();

System.out.println(noMethod.getPaymentMethodCase());
// PAYMENT_METHOD_NOT_SET

PaymentRequest cardRequest = PaymentRequest.newBuilder()
    .setOrderId("O-42")
    .setCard(CardPayment.newBuilder()
        .setToken("tok_123")
        .setLastFour("4242"))
    .build();

System.out.println(cardRequest.getPaymentMethodCase()); // CARD
System.out.println(cardRequest.hasCard());              // true
~~~

Với ví dụ trên, CardPayment và BankTransfer là message top-level nên Java import các lớp riêng. Nếu khai báo chúng lồng trong PaymentRequest, kiểu Java tương ứng sẽ được truy cập qua lớp bao ngoài.

## 5. Giá trị mặc định vẫn có presence trong oneof

Một scalar member của oneof được chọn vẫn có presence, kể cả khi giá trị bằng mặc định:

~~~proto
message SearchCriterion {
  oneof value {
    string text = 1;
    int32 numeric_id = 2;
    bool active = 3;
  }
}
~~~

Ba message sau có getter mặc định giống nhau ở một số trường hợp, nhưng case khác nhau:

~~~java
SearchCriterion absent = SearchCriterion.newBuilder().build();

SearchCriterion emptyText = SearchCriterion.newBuilder()
    .setText("")
    .build();

SearchCriterion falseActive = SearchCriterion.newBuilder()
    .setActive(false)
    .build();

System.out.println(absent.getValueCase());      // VALUE_NOT_SET
System.out.println(emptyText.getValueCase());   // TEXT
System.out.println(falseActive.getValueCase()); // ACTIVE
System.out.println(falseActive.getActive());    // false
~~~

Không thể suy ra lựa chọn từ giá trị getter:

- **getText()** có thể trả chuỗi rỗng khi chưa chọn text hoặc khi text được chọn bằng chuỗi rỗng.
- **getActive()** có thể trả false khi chưa chọn active hoặc khi active được chọn bằng false.
- **getNumericId()** có thể trả 0 trong cả trường hợp chưa chọn và đã chọn số 0.

Hãy kiểm tra **getValueCase()** hoặc **hasXxx()** để xác định thành viên được chọn. Oneof cung cấp explicit presence cho các thành viên của nhóm mà không cần khai báo optional.

## 6. Đặt, thay thế và xóa lựa chọn

Builder cung cấp setter cho từng thành viên. Đặt một thành viên mới sẽ xóa thành viên trước đó trong cùng nhóm:

~~~java
SearchCriterion criterion = SearchCriterion.newBuilder()
    .setText("enabled")
    .setNumericId(42)
    .build();

System.out.println(criterion.getValueCase()); // NUMERIC_ID
System.out.println(criterion.getText());      // ""
System.out.println(criterion.getNumericId()); // 42
~~~

Sau **setNumericId(42)**, lựa chọn text không còn hiện diện. Muốn xóa lựa chọn:

~~~java
SearchCriterion cleared = criterion.toBuilder()
    .clearValue()
    .build();

System.out.println(cleared.getValueCase()); // VALUE_NOT_SET
~~~

**clearValue()** là phương thức builder được sinh theo tên nhóm value; với nhóm payment_method, phương thức tương ứng là **clearPaymentMethod()**.

Xóa oneof khỏi một message request chỉ có nghĩa message không còn lựa chọn đó. Nó không tự động có nghĩa xóa dữ liệu đã lưu ở server. Nếu API cập nhật cần thao tác xóa, hãy quy định rõ ý nghĩa của trạng thái không chọn hoặc khai báo một lựa chọn tường minh như clear.

## 7. Oneof trong request gRPC

Ví dụ API tìm khách hàng cho phép tìm theo mã hoặc email:

~~~proto
syntax = "proto3";

package learning.customer.v1;

message CustomerLookup {
  oneof key {
    string customer_id = 1;
    string email = 2;
  }
}

message LookupCustomerRequest {
  CustomerLookup lookup = 1;
}

message Customer {
  string customer_id = 1;
  string display_name = 2;
}

service CustomerService {
  rpc LookupCustomer(LookupCustomerRequest)
      returns (Customer);
}
~~~

Server kiểm tra lựa chọn trước khi thực hiện truy vấn:

~~~java
switch (request.getLookup().getKeyCase()) {
    case CUSTOMER_ID ->
        findById(request.getLookup().getCustomerId());
    case EMAIL ->
        findByEmail(request.getLookup().getEmail());
    case KEY_NOT_SET ->
        throw invalidArgument("A lookup key is required");
}
~~~

Điểm chính là server không phải đoán field nào được ưu tiên nếu client gửi nhiều tiêu chí; schema và API oneof giới hạn lựa chọn ngay từ cấu trúc message.

Nếu lookup là message field, nó cũng có presence riêng: dùng **request.hasLookup()** để phân biệt không gửi toàn bộ message lookup với gửi một CustomerLookup rỗng. Sau đó dùng **getKeyCase()** để xác định có lựa chọn bên trong hay không.

Hai lớp kiểm tra này khác nhau:

- **hasLookup()** kiểm tra message con có được đặt hay không.
- **getKeyCase()** kiểm tra thành viên nào trong oneof được chọn.

## 8. ProtoJSON biểu diễn oneof

ProtoJSON không tạo một object bao ngoài mang tên nhóm oneof. Nó xuất field thành viên đang được chọn như thuộc tính bình thường:

~~~proto
message SearchCriterion {
  oneof value {
    string text = 1;
    int32 numeric_id = 2;
  }
}
~~~

Nếu chọn text:

~~~json
{
  "text": "active"
}
~~~

Nếu chọn numeric_id:

~~~json
{
  "numericId": 42
}
~~~

Nếu chưa chọn nhánh nào, message có thể được xuất thành object rỗng. Nếu một JSON object chứa nhiều field thuộc cùng oneof, payload vi phạm quy tắc chỉ chọn một nhánh và parser ProtoJSON có thể từ chối trường hợp xung đột.

Với Java, dùng **JsonFormat** trong **protobuf-java-util** để tuân theo ProtoJSON:

~~~java
import com.google.protobuf.util.JsonFormat;

String json = JsonFormat.printer().print(criterion);

SearchCriterion.Builder builder = SearchCriterion.newBuilder();
JsonFormat.parser().merge(json, builder);
SearchCriterion parsed = builder.build();

System.out.println(parsed.getValueCase());
~~~

Không nhầm tên nhóm oneof với tên JSON. Trong ví dụ trên, JSON chứa **text** hoặc **numericId**, không chứa khóa **value**.

## 9. Binary wire và nhiều thành viên xuất hiện

Oneof không có tag riêng. Khi một thành viên được chọn, Protobuf serialize chính field ấy với field number và wire type tương ứng. Vì vậy, payload nhị phân có thể được đọc bởi schema cũ như các field thông thường mà schema đó biết.

Nếu dữ liệu wire chứa nhiều thành viên thuộc cùng oneof, parser chỉ giữ lựa chọn xuất hiện sau cùng theo thứ tự đọc. Do đó, không thiết kế producer gửi đồng thời nhiều lựa chọn và không dựa vào thứ tự serialize để giải quyết xung đột nghiệp vụ.

Một điểm cần lưu ý với message member: dữ liệu của message được mã hóa dưới dạng length-delimited như message field thông thường. Oneof chỉ bổ sung quy tắc lựa chọn ở cấp schema/runtime; nó không biến payload con thành một định dạng mã hóa khác.

## 10. Quy tắc tương thích khi thay đổi oneof

Oneof cần được quản lý cẩn thận khi schema đã được client/server sử dụng:

| Thay đổi | Rủi ro và cách đánh giá |
| --- | --- |
| Thêm một thành viên mới vào oneof | Reader cũ không biết thành viên mới và có thể xem nhóm là chưa chọn. Kiểm thử đường đi qua client cũ, đặc biệt nếu message được chuyển đổi hoặc dựng lại. |
| Xóa một thành viên | Reader mới không còn API cho lựa chọn cũ; giữ số và tên bằng **reserved**, đồng thời xử lý dữ liệu cũ. |
| Di chuyển field đang tồn tại vào oneof | Không an toàn: message cũ có thể chứa nhiều field cùng lúc; schema mới chỉ giữ được một lựa chọn. |
| Di chuyển field ra khỏi oneof | Có thể thay đổi ngữ nghĩa và làm xuất hiện nhiều giá trị đồng thời; cần migration có chủ đích. |
| Đổi số hiệu field | Không an toàn; field number là danh tính trên wire. |
| Đổi kiểu hoặc ý nghĩa field | Có thể phá wire hoặc nghiệp vụ; đánh giá riêng, thường dùng field mới. |

Nếu xóa một oneof member đã phát hành, reserve cả số và tên trong message:

~~~proto
message Contact {
  oneof destination {
    string email = 1;
    string phone = 2;
  }
}
~~~

Sau khi loại bỏ phone:

~~~proto
message Contact {
  oneof destination {
    string email = 1;
  }

  reserved 2;
  reserved "phone";
}
~~~

**reserved** ngăn schema mới tái sử dụng số 2 hoặc tên phone. Nó không ngăn client cũ tiếp tục gửi field 2; parser mới có thể xem dữ liệu đó là unknown field. Khi đi qua gateway JSON hoặc code dựng lại message thủ công, unknown field có thể bị mất.

### Vì sao di chuyển field vào oneof nguy hiểm?

Giả sử schema cũ có hai field độc lập:

~~~proto
message LegacyContact {
  string email = 1;
  string phone = 2;
}
~~~

Một message cũ có thể chứa cả email và phone. Nếu schema mới gom chúng vào một oneof, parser mới chỉ giữ được một lựa chọn theo quy tắc oneof; thông tin còn lại có thể bị loại khỏi cách biểu diễn message mới. Vì thế, không thực hiện việc chuyển field đang dùng vào oneof như một thao tác refactor tên đơn thuần.

## 11. Lựa chọn oneof hay các field độc lập?

| Nhu cầu nghiệp vụ | Thiết kế phù hợp |
| --- | --- |
| Chỉ một trong email hoặc phone được dùng | **oneof** |
| Có thể cập nhật email và phone độc lập, đồng thời cả hai cùng tồn tại | Hai field độc lập, thường có explicit presence nếu cần patch |
| Chọn một trong nhiều loại payload khác cấu trúc | **oneof** chứa các message |
| Có nhiều tag cùng lúc | **repeated** |
| Tra cứu giá trị theo khóa | **map** |
| Cần phân biệt không đổi, đặt giá trị và xóa | Oneof với lệnh rõ ràng hoặc FieldMask cùng semantics được định nghĩa |

Oneof biểu diễn **tối đa một lựa chọn**, không tự bảo đảm phải có lựa chọn. Nếu nghiệp vụ bắt buộc chọn một phương án, server vẫn cần kiểm tra case ***_NOT_SET** và trả lỗi phù hợp, chẳng hạn **INVALID_ARGUMENT**.

## 12. Kiểm thử oneof trong Java

Các kiểm thử nên xác nhận:

1. Message mới chưa chọn nhánh trả case ***_NOT_SET**.
2. Đặt một nhánh có giá trị mặc định vẫn làm nhánh đó hiện diện.
3. Đặt nhánh thứ hai thay thế nhánh thứ nhất.
4. **clearXxx()** xóa toàn bộ lựa chọn của nhóm.
5. Binary và ProtoJSON round-trip giữ đúng nhánh.
6. Server xử lý request không chọn nhánh như hợp đồng quy định.

Ví dụ JUnit 5:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import com.example.search.v1.SearchCriterion;
import org.junit.jupiter.api.Test;

class SearchCriterionTest {
    @Test
    void tracksSelectedMemberEvenWhenValueIsDefault() {
        SearchCriterion absent = SearchCriterion.newBuilder().build();
        SearchCriterion selected = SearchCriterion.newBuilder()
            .setActive(false)
            .build();

        assertEquals(
            SearchCriterion.ValueCase.VALUE_NOT_SET,
            absent.getValueCase());
        assertEquals(
            SearchCriterion.ValueCase.ACTIVE,
            selected.getValueCase());
        assertFalse(selected.getActive());
    }

    @Test
    void settingAnotherMemberReplacesPreviousChoice() {
        SearchCriterion criterion = SearchCriterion.newBuilder()
            .setText("enabled")
            .setNumericId(42)
            .build();

        assertEquals(
            SearchCriterion.ValueCase.NUMERIC_ID,
            criterion.getValueCase());
        assertEquals(42, criterion.getNumericId());
    }

    @Test
    void clearRemovesTheWholeChoice() {
        SearchCriterion cleared = SearchCriterion.newBuilder()
            .setText("enabled")
            .clearValue()
            .build();

        assertEquals(
            SearchCriterion.ValueCase.VALUE_NOT_SET,
            cleared.getValueCase());
    }
}
~~~

Tên **ValueCase** và hằng **VALUE_NOT_SET** trong ví dụ được sinh từ oneof có tên value; khi đổi tên nhóm, tên enum case và phương thức builder cũng đổi theo. Hãy dùng đúng tên API từ lớp Java được sinh trong dự án.

## 13. Bài tập thực hành

Thiết kế message **NotificationTarget** cho dịch vụ gửi thông báo. Một thông báo chỉ được gửi tới email, số điện thoại hoặc device token:

~~~proto
message NotificationTarget {
  oneof destination {
    string email = 1;
    string phone = 2;
    string device_token = 3;
  }
}
~~~

Hãy:

1. Tạo message chưa chọn đích và kiểm tra **getDestinationCase()**.
2. Đặt **email = ""** rồi giải thích vì sao nhánh email vẫn hiện diện.
3. Đặt tiếp phone trên cùng builder và xác nhận email không còn là lựa chọn.
4. Dùng **clearDestination()** để đưa message về trạng thái chưa chọn.
5. Serialize/parse binary và ProtoJSON, kiểm tra nhánh sau round-trip.
6. Viết kiểm tra server từ chối request có **DESTINATION_NOT_SET**.
7. Giả sử cần bổ sung lựa chọn webhook sau khi client cũ đã phát hành; giải thích cách client cũ có thể quan sát message và những đường chuyển đổi có thể làm mất lựa chọn mới.

**Tiêu chí hoàn thành:** giải thích được oneof là nhóm lựa chọn có tối đa một thành viên, dùng đúng Java case API, và nhận biết các thay đổi schema có thể làm mất dữ liệu.

## 14. Ghi nhớ

- **oneof** nhóm các field loại trừ nhau; tại một thời điểm tối đa một thành viên được chọn.
- Một message có thể chưa chọn thành viên nào; oneof không tự biến lựa chọn thành bắt buộc.
- Thành viên scalar được chọn vẫn có presence khi giá trị là **false**, **0** hoặc chuỗi rỗng.
- Java dùng **getXxxCase()**, **hasXxx()**, các setter thành viên và **clearXxx()**.
- Repeated/map không thể là thành viên trực tiếp; bọc trong message nếu cần đưa collection vào một lựa chọn.
- Không tùy tiện di chuyển field đã phát hành vào/ra oneof; khi xóa member, reserve số và tên.

Dùng oneof đúng chỗ giúp hợp đồng Protocol Buffers diễn đạt rõ các lựa chọn thay thế, giảm trạng thái xung đột trong request và giúp dịch vụ Spring gRPC xử lý dữ liệu nhất quán giữa các phiên bản client/server.
