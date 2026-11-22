# Nested message và nested enum

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Khai báo **message lồng nhau** và **enum lồng nhau** trong proto3.
- Tham chiếu đúng kiểu lồng nhau từ message khác và hiểu phạm vi tên của chúng.
- Sử dụng các kiểu Java được sinh như **Customer.Address** và **Customer.State**.
- Phân biệt presence của nested message với giá trị mặc định của nested enum.
- Chọn khi nào nên lồng kiểu dữ liệu và khi nào nên tách thành kiểu top-level để tái sử dụng.
- Đánh giá tác động của việc đổi tên, di chuyển hoặc mở rộng nested type đối với hợp đồng Spring gRPC.

## 1. Khi nào nên lồng message hoặc enum?

Trong hợp đồng **SPRING_GRPC**, message Protobuf định nghĩa cấu trúc request và response cho RPC. Một message có thể chứa dữ liệu con chỉ có ý nghĩa trong ngữ cảnh của nó. Ví dụ, **Customer** có **Address** và **State**; địa chỉ và trạng thái này là một phần của mô hình khách hàng.

Proto3 cho phép khai báo **message** hoặc **enum** bên trong một message khác. Kiểu được lồng có phạm vi tên gắn với message bao ngoài, giúp nhóm các kiểu liên quan và tránh đưa mọi tên vào package-level namespace.

Nên cân nhắc nested type khi:

- Kiểu con chỉ có ý nghĩa trong một message cha, ví dụ **Customer.Address**.
- Kiểu enum mô tả một thuộc tính riêng của message cha, ví dụ **Customer.State**.
- Muốn người đọc schema thấy ngay mối quan hệ giữa cấu trúc cha và cấu trúc con.

Nên dùng kiểu top-level khi nhiều message hoặc nhiều service cần tái sử dụng cùng một kiểu, hoặc khi kiểu con đã trở thành khái niệm độc lập trong miền nghiệp vụ.

## 2. Khai báo nested message và nested enum

Ví dụ:

~~~proto
syntax = "proto3";

package learning.customer.v1;

option java_package = "com.example.customer.v1";
option java_multiple_files = true;

message Customer {
  string customer_id = 1;
  string display_name = 2;
  Address address = 3;
  State state = 4;

  message Address {
    string street = 1;
    string city = 2;
    string country_code = 3;
  }

  enum State {
    STATE_UNSPECIFIED = 0;
    STATE_ACTIVE = 1;
    STATE_SUSPENDED = 2;
  }
}
~~~

Trong schema:

- **Address** là message được khai báo bên trong **Customer**.
- **State** là enum được khai báo bên trong **Customer**.
- Các field **address** và **state** sử dụng trực tiếp kiểu con trong message bao ngoài.
- Field number của **Address** bắt đầu từ 1 trong phạm vi message Address; chúng không xung đột với các field 1–4 của Customer.
- Enum **State** có miền số riêng; giá trị đầu tiên phải là 0 theo quy tắc proto3.

Nested type không tự động kế thừa field, enum value hoặc dữ liệu của message cha. **Customer.Address** là một message độc lập có schema riêng; **Customer** chỉ chứa một field có kiểu đó.

## 3. Phạm vi tên và cách tham chiếu kiểu lồng nhau

Trong chính message bao ngoài, có thể dùng tên ngắn:

~~~proto
message Customer {
  Address address = 1;

  message Address {
    string city = 1;
  }
}
~~~

Từ một message khác trong cùng package, dùng tên có tiền tố message cha:

~~~proto
message CustomerSearchResult {
  Customer.Address primary_address = 1;
  Customer.State customer_state = 2;
}
~~~

Tên đầy đủ của kiểu Protobuf còn bao gồm package. Với package **learning.customer.v1**, các symbol tương ứng có dạng:

- **learning.customer.v1.Customer**
- **learning.customer.v1.Customer.Address**
- **learning.customer.v1.Customer.State**

Đây là tên trong namespace Protobuf, không nhất thiết giống package Java. **java_package** chỉ định package Java được sinh; nó không đổi package hoặc tên đầy đủ của symbol trong schema Protobuf.

### Tránh xung đột enum value

Tên enum value được đặt trong phạm vi bao quanh enum, không phải một namespace độc lập giống tên enum. Vì thế, khi có nhiều enum trong cùng package hoặc cùng message, nên dùng tiền tố:

~~~proto
message Customer {
  enum State {
    STATE_UNSPECIFIED = 0;
    STATE_ACTIVE = 1;
  }

  enum VerificationState {
    VERIFICATION_STATE_UNSPECIFIED = 0;
    VERIFICATION_STATE_PENDING = 1;
    VERIFICATION_STATE_VERIFIED = 2;
  }
}
~~~

Các tên **STATE_ACTIVE** và **VERIFICATION_STATE_VERIFIED** giúp tránh xung đột khi thêm enum khác. Không nên đặt hai enum value cùng tên trong một phạm vi bao ngoài.

## 4. Nested type được sinh thành kiểu Java nào?

Với **java_package = "com.example.customer.v1"**, mã Java cho nested type được truy cập qua lớp message bao ngoài:

- **Customer** là lớp message cha.
- **Customer.Address** là lớp message con.
- **Customer.State** là enum con.

**java_multiple_files = true** có thể tạo các lớp top-level như **CustomerSearchResult** thành file Java riêng, nhưng nested type vẫn được tham chiếu thông qua lớp bao ngoài.

Ví dụ tạo message:

~~~java
import com.example.customer.v1.Customer;

Customer.Address address = Customer.Address.newBuilder()
    .setStreet("12 Nguyen Hue")
    .setCity("Ho Chi Minh City")
    .setCountryCode("VN")
    .build();

Customer customer = Customer.newBuilder()
    .setCustomerId("C-42")
    .setDisplayName("Nguyen An")
    .setAddress(address)
    .setState(Customer.State.STATE_ACTIVE)
    .build();

System.out.println(customer.getAddress().getCity());
System.out.println(customer.getState());
~~~

Nested message có builder riêng và bất biến sau **build()**, giống message top-level. Có thể tạo trực tiếp từ builder con trong builder cha:

~~~java
Customer customer = Customer.newBuilder()
    .setCustomerId("C-42")
    .setAddress(Customer.Address.newBuilder()
        .setCity("Da Nang")
        .setCountryCode("VN"))
    .build();
~~~

Đối với enum, dùng tên có tiền tố lớp cha như **Customer.State.STATE_ACTIVE**. Không tạo một enum Java thủ công để thay thế enum được sinh nếu message Protobuf vẫn sử dụng kiểu enum gốc.

## 5. Presence của nested message và default value của nested enum

Nested message field có **explicit presence** ngay cả khi không khai báo **optional**:

~~~proto
message Customer {
  Address address = 1;

  message Address {
    string city = 1;
  }
}
~~~

Java cung cấp **hasAddress()**:

~~~java
Customer absent = Customer.newBuilder().build();

Customer presentEmpty = Customer.newBuilder()
    .setAddress(Customer.Address.getDefaultInstance())
    .build();

System.out.println(absent.hasAddress());       // false
System.out.println(presentEmpty.hasAddress()); // true
System.out.println(absent.getAddress().getCity()); // ""
~~~

**getAddress()** trả default instance khi field vắng mặt. Vì vậy, không kiểm tra null để xác định sự hiện diện; dùng **hasAddress()**.

Nested enum field thông thường là scalar enum và dùng **implicit presence**:

~~~proto
message Customer {
  State state = 1;

  enum State {
    STATE_UNSPECIFIED = 0;
    STATE_ACTIVE = 1;
  }
}
~~~

Nếu không đặt **state**, **getState()** trả **STATE_UNSPECIFIED**, và không có **hasState()**. Nếu cần phân biệt không gửi với chủ động đặt số 0, khai báo **optional State state = 1;**; khi đó Java sinh **hasState()**.

Không nhầm **nested** với **optional**: nested mô tả vị trí khai báo và phạm vi tên; optional mô tả presence của scalar/enum field. Hai đặc tính giải quyết hai vấn đề khác nhau.

## 6. Dùng nested type trong request/response gRPC

Nested type có thể được tham chiếu từ request, response và các message khác:

~~~proto
message GetCustomerRequest {
  string customer_id = 1;
}

message GetCustomerResponse {
  Customer customer = 1;
}

message UpdateCustomerAddressRequest {
  string customer_id = 1;
  Customer.Address address = 2;
}

service CustomerService {
  rpc GetCustomer(GetCustomerRequest) returns (GetCustomerResponse);
  rpc UpdateAddress(UpdateCustomerAddressRequest)
      returns (GetCustomerResponse);
}
~~~

**UpdateCustomerAddressRequest** dùng **Customer.Address** để tái sử dụng đúng kiểu con, thay vì định nghĩa một **Address** thứ hai có cấu trúc gần giống. Nếu địa chỉ chỉ thuộc mô hình Customer, cách này giữ quan hệ trong schema rõ ràng.

Khi dùng Java stub, request có thể được dựng như sau:

~~~java
import com.example.customer.v1.Customer;
import com.example.customer.v1.UpdateCustomerAddressRequest;

UpdateCustomerAddressRequest request =
    UpdateCustomerAddressRequest.newBuilder()
        .setCustomerId("C-42")
        .setAddress(Customer.Address.newBuilder()
            .setCity("Can Tho")
            .setCountryCode("VN"))
        .build();
~~~

Không cần tạo service hay lớp Spring boilerplate riêng để sử dụng nested type. Đây chỉ là kiểu dữ liệu được sinh; server/client dùng nó như các message Protobuf khác.

## 7. Khi nào nên chuyển nested type thành top-level?

Ban đầu **Customer.Address** có thể chỉ được dùng trong Customer. Về sau, hệ thống cần cùng cấu trúc địa chỉ cho Supplier, Branch và DeliveryDestination. Khi ấy có thể cân nhắc đưa thành top-level message:

~~~proto
message Address {
  string street = 1;
  string city = 2;
  string country_code = 3;
}

message Customer {
  string customer_id = 1;
  Address address = 2;
}

message Supplier {
  string supplier_id = 1;
  Address address = 2;
}
~~~

Việc chuyển từ **Customer.Address** sang **Address** làm thay đổi **fully qualified Protobuf name** và kiểu Java (**Customer.Address** thành **Address**). Mã nguồn tham chiếu kiểu cũ phải cập nhật; descriptor và công cụ dựa trên tên đầy đủ cũng thấy một symbol khác.

Nếu cấu trúc field bên trong giữ nguyên, binary payload của field message có thể vẫn đọc được vì field ngoài vẫn là length-delimited và nội dung message con có cùng field number/kiểu. Tuy nhiên, không nên coi việc đổi tên kiểu là thay đổi hoàn toàn vô hại: các hệ thống dùng **google.protobuf.Any** type URL, descriptor, reflection, schema registry hoặc JSON mapping có thể phụ thuộc tên kiểu.

Quy tắc lựa chọn:

| Nên giữ nested | Nên tách top-level |
| --- | --- |
| Chỉ có ý nghĩa trong message cha | Nhiều message/service cần tái sử dụng |
| Không có vòng đời hoặc hợp đồng độc lập | Có thể được quản lý, version hoặc tài liệu hóa độc lập |
| Tên cha giúp hiểu rõ ngữ cảnh | Tên kiểu đã trở thành khái niệm chung |
| Thay đổi thường đi cùng message cha | Nhiều nhóm cần phát triển kiểu riêng |

Không nên lồng quá sâu chỉ để gom file. Mỗi tầng lồng làm tên kiểu dài hơn và có thể khiến việc tái sử dụng, tìm kiếm và quản lý version khó hơn.

## 8. Phát triển nested message và enum qua phiên bản

Các quy tắc tương thích cơ bản vẫn áp dụng:

- Khi thêm field vào nested message, chọn số chưa dùng trong **chính nested message đó**.
- Khi xóa field, reserve số và tên cũ trong nested message tương ứng.
- Không đổi số enum value đã phát hành; khi xóa giá trị, reserve cả số và tên trong enum.
- Khi thêm enum value, client cũ có thể nhận **UNRECOGNIZED** trong Java; dùng **getXxxValue()** nếu cần giữ số gốc.
- Đổi tên hoặc di chuyển nested type làm thay đổi symbol đầy đủ và API Java, ngay cả khi cấu trúc binary bên trong không đổi.

Ví dụ mở rộng **Customer.Address**:

~~~proto
message Customer {
  Address address = 3;

  message Address {
    string street = 1;
    string city = 2;
    string country_code = 3;
    optional string postal_code = 4;

    reserved 5;
    reserved "legacy_region";
  }
}
~~~

**postal_code = 4** được thêm bằng số mới trong phạm vi **Address**. **reserved 5** và **reserved "legacy_region"** chỉ có hiệu lực trong **Address**; chúng không reserve số 5 hoặc tên đó trong message **Customer**.

Nếu một phiên bản cũ chưa biết **postal_code**, nó có thể bỏ qua field mới trên binary wire. Server mới phải xử lý trường hợp field vắng mặt, đặc biệt nếu ứng dụng dùng giá trị này để xác định vùng giao hàng.

## 9. Kiểm tra nested type trong Java

Một số kiểm tra hữu ích:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import com.example.customer.v1.Customer;
import org.junit.jupiter.api.Test;

class CustomerNestedTypeTest {
    @Test
    void buildsAndParsesNestedMessage() throws Exception {
        Customer source = Customer.newBuilder()
            .setCustomerId("C-42")
            .setAddress(Customer.Address.newBuilder()
                .setCity("Da Nang")
                .setCountryCode("VN"))
            .setState(Customer.State.STATE_ACTIVE)
            .build();

        Customer parsed = Customer.parseFrom(source.toByteArray());

        assertTrue(parsed.hasAddress());
        assertEquals("Da Nang", parsed.getAddress().getCity());
        assertEquals(Customer.State.STATE_ACTIVE, parsed.getState());
    }

    @Test
    void distinguishesAbsentAndEmptyNestedMessage() {
        Customer absent = Customer.newBuilder().build();
        Customer emptyAddress = Customer.newBuilder()
            .setAddress(Customer.Address.getDefaultInstance())
            .build();

        assertFalse(absent.hasAddress());
        assertTrue(emptyAddress.hasAddress());
    }
}
~~~

Kiểm thử đầu xác nhận nested message và enum được dựng/parse đúng. Kiểm thử thứ hai chứng minh message con vắng mặt khác với message con hiện diện nhưng rỗng. Khi thay đổi schema, cần bổ sung fixture từ phiên bản cũ để xác nhận client/server khác phiên bản vẫn đọc được dữ liệu và xử lý enum chưa biết.

## 10. Lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Tham chiếu **Address** từ message khác mà quên tiền tố **Customer.** | Compiler không tìm thấy kiểu trong phạm vi hiện tại | Dùng **Customer.Address** hoặc tên đầy đủ phù hợp. |
| Cho rằng nested type tự kế thừa package Java | Import hoặc tên lớp sai | Xem **java_package**; nested type được truy cập qua lớp message cha. |
| Dùng enum value tên chung như **ACTIVE** ở nhiều enum | Xung đột tên trong phạm vi bao ngoài | Dùng tiền tố như **CUSTOMER_STATE_ACTIVE**. |
| Cho rằng nested enum có presence mặc định | Không phân biệt được field vắng mặt và số 0 | Dùng **optional** nếu cần **hasState()**. |
| Kiểm tra null với nested message | Bỏ sót default instance | Dùng **hasAddress()**. |
| Lồng một kiểu được nhiều service dùng chung | Tăng phụ thuộc vào message cha | Cân nhắc top-level message. |
| Di chuyển nested type nhưng không cập nhật descriptor/Java | Mã nguồn hoặc hệ thống reflection bị lỗi | Đánh giá symbol đầy đủ, API Java và các hệ thống phụ thuộc. |

## 11. Bài tập thực hành

Thiết kế message **Device** với:

- Nested message **Network** chứa **ip_address**, **port** và **optional string dns_name**.
- Nested enum **ConnectionState** gồm **UNSPECIFIED = 0**, **DISCONNECTED = 1**, **CONNECTED = 2**.
- Field **network** và **connection_state** trong **Device**.
- Một message **UpdateDeviceRequest** bên ngoài dùng lại **Device.Network**.

Hãy:

1. Viết schema proto3 hoàn chỉnh và xác định tên đầy đủ của **Device.Network** và **Device.ConnectionState**.
2. Tạo một **Device** bằng Java builder, đặt network và trạng thái CONNECTED.
3. So sánh **hasNetwork()** với **getConnectionState()** khi field không được đặt.
4. Serialize/parse message và kiểm tra nested message.
5. Giải thích vì sao **ConnectionState** số 0 không tự chứng minh client đã gửi field.
6. Đề xuất khi nào **Network** nên chuyển thành top-level message nếu nhiều service cùng sử dụng.

## 12. Ghi nhớ

- **Nested message/enum** nhóm kiểu dữ liệu trong phạm vi một message cha; tên đầy đủ của kiểu bao gồm tên cha.
- Trong Java, nested type được truy cập qua lớp message cha, ví dụ **Customer.Address** và **Customer.State**.
- Nested message field vốn có presence; nested enum field thông thường vẫn là scalar enum với implicit presence.
- Enum value cần tên rõ ràng và số 0 mang nghĩa **UNSPECIFIED**; tiền tố giúp tránh xung đột tên.
- Chỉ nên lồng kiểu có quan hệ chặt với message cha; kiểu cần tái sử dụng rộng nên cân nhắc top-level.
- Khi đổi tên hoặc di chuyển nested type, kiểm tra API Java, descriptor, reflection, **Any type URL** và các client/server khác phiên bản.

Thiết kế nested message và nested enum đúng cách giúp hợp đồng Protocol Buffers thể hiện rõ cấu trúc miền nghiệp vụ, giữ API Java dễ hiểu và hỗ trợ dịch vụ Spring gRPC phát triển an toàn theo thời gian.
