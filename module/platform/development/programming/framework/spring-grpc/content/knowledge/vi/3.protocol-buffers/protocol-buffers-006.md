# Default value và presence

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích **default value** (giá trị mặc định) và **field presence** (sự hiện diện của field) trong Protocol Buffers proto3.
- Phân biệt **implicit presence** với **explicit presence** khi làm việc với scalar, enum, message, **optional**, **oneof**, **repeated** và **map**.
- Đọc đúng các API Java do **protoc** sinh ra như **getXxx()**, **hasXxx()**, **setXxx()**, **clearXxx()**, **get...Case()**.
- Dự đoán khác biệt khi serialize sang Protobuf nhị phân, chuyển sang ProtoJSON và gộp message bằng **mergeFrom()**.
- Thiết kế và kiểm thử request cập nhật từng phần cho dịch vụ Spring gRPC, tránh ghi đè dữ liệu vì nhầm giá trị mặc định với field vắng mặt.

## 1. Giá trị mặc định không trả lời được câu hỏi “client có gửi field này không?”

Trong **SPRING_GRPC**, hợp đồng Protocol Buffers mô tả message cho client/server unary hoặc streaming RPC. Công cụ **protoc** sinh lớp Java từ schema; ứng dụng Spring nhận các request đã được giải mã rồi thực hiện logic nghiệp vụ. Nếu chỉ quan sát giá trị trả về từ getter, server có thể hiểu sai ý định người gửi.

Xét trường hợp người dùng chỉnh cấu hình thông báo:

- Client **không gửi** trạng thái thông báo: server cần giữ nguyên cấu hình hiện tại.
- Client gửi giá trị **false**: server cần tắt thông báo.
- Client **không gửi** giới hạn truy cập: giữ số giới hạn hiện tại.
- Client gửi giá trị **0**: đặt giới hạn về 0 theo quy tắc nghiệp vụ.

Với field **bool** thông thường của proto3, getter Java trả **false** trong cả hai tình huống “không gửi” và “đặt false”. Tương tự, **int32** trả 0 và **string** trả chuỗi rỗng khi không có dữ liệu. Đây là **default value** của kiểu dữ liệu.

**Presence** trả lời câu hỏi khác: *field có thực sự được đặt trong message hay không?* Chỉ các field có **explicit presence** mới biểu đạt trực tiếp được sự khác nhau giữa “vắng mặt” và “có mặt nhưng mang giá trị mặc định”. Hiểu sự khác biệt này giúp tránh lỗi cập nhật nhầm, nhất là khi nhiều phiên bản client và server Spring gRPC cùng hoạt động.

## 2. Default value trong proto3 là gì?

Giá trị mặc định là kết quả mà getter cung cấp khi field không có giá trị được đặt rõ ràng. Với proto3, các giá trị mặc định thường gặp:

| Loại field | Giá trị khi field chưa được đặt | API Java thông dụng |
| --- | --- | --- |
| **string** | Chuỗi rỗng **""** | **getName()** trả String |
| **bool** | **false** | **getEnabled()** trả boolean |
| **int32**, **uint32**, **sint32** và các số nguyên 32-bit khác | **0** | Getter trả int |
| **int64**, **uint64**, **sint64** và các số nguyên 64-bit khác | **0L** | Getter trả long |
| **float**, **double** | **0.0** | Getter trả float/double |
| **bytes** | **ByteString.EMPTY** | Getter trả ByteString |
| **enum** | Thành viên có số hiệu **0** | Getter trả enum được sinh |
| **message** | **Default instance** của kiểu message | Getter trả đối tượng message, có thể kiểm tra presence riêng |
| **repeated** | Danh sách rỗng | **getXxxList()**, **getXxxCount()** |
| **map** | Map rỗng | **getXxxMap()**, **getXxxCount()** |

Lưu ý quan trọng:

1. **Mặc định của getter** không đồng nghĩa với giá trị được serialize. Field scalar proto3 không có explicit presence và đang bằng mặc định thường **không được ghi** ra binary.
2. **Enum** proto3 phải khai báo giá trị đầu tiên có số hiệu **0**. Thực tế nên đặt tên như **UNSPECIFIED** hoặc **UNKNOWN**, không mặc định hiểu số 0 là một trạng thái nghiệp vụ hợp lệ.
3. **Message** cũng có getter trả default instance nếu vắng mặt, nhưng bản thân field message **có presence**. Phải kiểm tra **hasXxx()** khi cần phân biệt không gửi submessage với gửi submessage rỗng.
4. **Repeated/map** không có presence của chính tập hợp theo cách thông thường; giá trị tập hợp rỗng không cho biết người gửi đã chủ ý gửi rỗng hay không.

Trong proto3 thông thường, bạn **không khai báo tùy ý default value** bằng cú pháp kiểu **[default = 10]** như một số schema proto2 cũ. Ví dụ, để mặc định giới hạn là 10 theo nghiệp vụ, server phải áp dụng 10 khi field vắng mặt; không thể dựa vào getter proto3 tự trả về 10.

## 3. Hai mô hình presence: implicit và explicit

**Implicit presence** là mô hình áp dụng cho scalar/enum proto3 không khai báo **optional** và không thuộc **oneof**. Message có thể chứa giá trị khác mặc định, nhưng API không theo dõi độc lập việc scalar đã được đặt thành đúng giá trị mặc định.

**Explicit presence** lưu thông tin field có được đặt hay không. Trong proto3, các trường hợp điển hình là **optional scalar**, **message field** và các nhánh **oneof**.

Ví dụ:

~~~proto
syntax = "proto3";

message PresenceExample {
  bool enabled = 1;
  optional bool enabled_override = 2;
}
~~~

| Tình huống | enabled | enabled_override |
| --- | --- | --- |
| Chưa gọi setter | **getEnabled() == false** | **getEnabledOverride() == false**, **hasEnabledOverride() == false** |
| Gọi setter với **false** | **getEnabled() == false**, không có **hasEnabled()** | **getEnabledOverride() == false**, **hasEnabledOverride() == true** |
| Gọi setter với **true** | **getEnabled() == true** | **getEnabledOverride() == true**, **hasEnabledOverride() == true** |

Nếu server cần biết client *có yêu cầu tắt thông báo hay không*, chỉ đọc **getEnabled() == false** là chưa đủ. Cần thiết kế field có explicit presence và kiểm tra **hasEnabledOverride()**.

**Optional không làm field trở thành bắt buộc.** Nó bổ sung khả năng nhận biết presence; yêu cầu bắt buộc phải cung cấp một giá trị vẫn thuộc phần kiểm tra nghiệp vụ của ứng dụng.

## 4. Một hợp đồng minh họa đầy đủ

Giả sử dịch vụ gRPC quản lý sở thích của người dùng. Schema:

~~~proto
syntax = "proto3";

package learning.preferences.v1;

option java_package = "com.example.preferences.v1";
option java_multiple_files = true;

enum DeliveryMode {
  DELIVERY_MODE_UNSPECIFIED = 0;
  DELIVERY_MODE_EMAIL = 1;
  DELIVERY_MODE_PUSH = 2;
}

message ContactInfo {
  string email = 1;
}

message UserPreferences {
  string user_id = 1;
  string locale = 2;
  optional bool notifications_enabled = 3;
  optional int32 daily_limit = 4;
  optional string nickname = 5;
  optional DeliveryMode delivery_mode = 6;
  ContactInfo contact = 7;
  repeated string topics = 8;
  map<string, string> attributes = 9;

  oneof recovery_destination {
    string backup_email = 10;
    string backup_phone = 11;
  }
}

message PatchPreferencesRequest {
  string user_id = 1;
  optional bool notifications_enabled = 2;
  optional int32 daily_limit = 3;
  optional string nickname = 4;
  optional DeliveryMode delivery_mode = 5;
}

service PreferencesService {
  rpc PatchPreferences(PatchPreferencesRequest)
      returns (UserPreferences);
}
~~~

Trong message **UserPreferences**:

- **locale = 2** là scalar thông thường, có **implicit presence**.
- **notifications_enabled**, **daily_limit**, **nickname**, **delivery_mode** có **explicit presence** nhờ **optional**.
- **contact = 7** có presence vì là message field, không cần khai báo optional để có **hasContact()**.
- **topics** và **attributes** là tập hợp; không có **hasTopics()** hoặc **hasAttributes()** cho chính field đó.
- **recovery_destination** là **oneof**: tối đa một nhánh được đặt, được xác định qua **getRecoveryDestinationCase()**.

Request **PatchPreferencesRequest** tách riêng những field có thể cập nhật. Cách tổ chức này cho phép server áp dụng thay đổi có chủ đích mà không tự suy diễn từ các giá trị mặc định của **UserPreferences**.

## 5. Quan sát default value và presence trong Java

Từ schema trên, **protoc** sinh các builder và getter. Ví dụ:

~~~java
import com.example.preferences.v1.UserPreferences;

UserPreferences empty = UserPreferences.newBuilder().build();

System.out.println(empty.getLocale());                // ""
System.out.println(empty.getNotificationsEnabled());  // false
System.out.println(empty.hasNotificationsEnabled());  // false
System.out.println(empty.getDailyLimit());            // 0
System.out.println(empty.hasDailyLimit());            // false
System.out.println(empty.getNickname());              // ""
System.out.println(empty.hasNickname());              // false
System.out.println(empty.getTopicsCount());           // 0
System.out.println(empty.getAttributesCount());       // 0
System.out.println(empty.hasContact());               // false
~~~

Không có **hasLocale()**, vì **locale** là string proto3 không có explicit presence. **getContact()** vẫn trả một default instance, nhưng **hasContact() == false** cho biết message con chưa được đặt.

Đặt giá trị mặc định bằng builder:

~~~java
UserPreferences explicitDefaults = UserPreferences.newBuilder()
    .setLocale("")
    .setNotificationsEnabled(false)
    .setDailyLimit(0)
    .setNickname("")
    .build();

System.out.println(explicitDefaults.getLocale());               // ""
System.out.println(explicitDefaults.hasNotificationsEnabled()); // true
System.out.println(explicitDefaults.hasDailyLimit());           // true
System.out.println(explicitDefaults.hasNickname());             // true
~~~

**setLocale("")** không tạo presence riêng cho **locale**. Ngược lại, setter của optional đánh dấu field hiện diện, dù giá trị bằng mặc định.

Builder còn có **clearXxx()** để xóa giá trị field:

~~~java
UserPreferences cleared = explicitDefaults.toBuilder()
    .clearNickname()
    .build();

System.out.println(cleared.hasNickname()); // false
System.out.println(cleared.getNickname()); // ""
~~~

Về getter, hai message **explicitDefaults** và **cleared** đều trả chuỗi rỗng cho nickname, nhưng khác nhau về **hasNickname()**. Điều này ảnh hưởng đến serialization, merge và ý nghĩa lệnh cập nhật.

## 6. Vì sao message field có default instance nhưng vẫn có presence?

Với:

~~~proto
message ContactInfo {
  string email = 1;
}

message UserAccount {
  ContactInfo contact = 1;
}
~~~

Hai trường hợp:

~~~java
UserAccount absent = UserAccount.newBuilder().build();

UserAccount presentEmpty = UserAccount.newBuilder()
    .setContact(ContactInfo.newBuilder().build())
    .build();

System.out.println(absent.hasContact());       // false
System.out.println(presentEmpty.hasContact()); // true

System.out.println(absent.getContact().getEmail());       // ""
System.out.println(presentEmpty.getContact().getEmail()); // ""
~~~

**getContact()** trả default instance khi vắng mặt; nội dung con được đặt là message rỗng cũng trả email mặc định. Vì vậy, chỉ so sánh **getContact().getEmail()** không phân biệt được hai trường hợp. **hasContact()** mới là thông tin presence của field message.

Message field vốn có explicit presence trong proto3, vì thế có thể khai báo đơn giản **ContactInfo contact = 1;**. Khi cần kiểm tra sự tồn tại, không bắt buộc thêm nhãn **optional**.

Ở tầng nghiệp vụ, **contact hiện diện nhưng không có email** có thể biểu thị một hành động riêng; nhưng message rỗng tự nó **không** quy định phải xóa contact hay giữ nguyên. Ứng dụng phải định nghĩa và kiểm thử ý nghĩa đó.

## 7. Enum: số 0, optional và giá trị chưa biết

Xét:

~~~proto
enum DeliveryMode {
  DELIVERY_MODE_UNSPECIFIED = 0;
  DELIVERY_MODE_EMAIL = 1;
  DELIVERY_MODE_PUSH = 2;
}

message DeliverySettings {
  DeliveryMode mode = 1;
  optional DeliveryMode requested_mode = 2;
}
~~~

Khi không đặt field:

- **getMode()** trả **DELIVERY_MODE_UNSPECIFIED** nhưng không có **hasMode()**.
- **getRequestedMode()** trả **DELIVERY_MODE_UNSPECIFIED**, đồng thời **hasRequestedMode() == false**.

Nếu builder gọi **setRequestedMode(DELIVERY_MODE_UNSPECIFIED)**, **hasRequestedMode()** trở thành **true**. Server có thể phân biệt yêu cầu *đặt lại chế độ về chưa xác định* với *không yêu cầu chỉnh chế độ*.

Các phiên bản enum có thể tiến hóa. Nếu client nhận một giá trị số mà enum Java hiện tại chưa khai báo, runtime Java proto3 thông thường vẫn giữ số đó và **getMode()** có thể trả **UNRECOGNIZED**. Để xem số nguyên, dùng **getModeValue()**. Cần xử lý tình huống giá trị chưa biết trong logic nghiệp vụ; không tự hiểu mọi giá trị lạ là **UNSPECIFIED**.

Giá trị enum mặc định số 0 và trạng thái **vắng mặt** là hai khái niệm khác nhau. **Optional enum** giúp biểu đạt sự khác nhau ấy.

## 8. Repeated và map: rỗng không đồng nghĩa đã yêu cầu xóa

Xét:

~~~proto
message Subscription {
  repeated string topics = 1;
  map<string, string> labels = 2;
}
~~~

Nếu không thêm chủ đề hoặc nhãn, Java trả **danh sách rỗng** và **map rỗng**. Các phương thức tương ứng như **getTopicsList()**, **getTopicsCount()**, **getLabelsMap()**, **getLabelsCount()** giúp đọc nội dung.

Tuy nhiên, repeated và map không có **hasTopics()** hay **hasLabels()** để đánh dấu toàn bộ tập hợp được đặt rỗng. Trong binary, tập hợp không có phần tử không chứa các mục entry tương ứng. Vì thế server không thể chỉ nhìn vào repeated/map rỗng để biết client muốn **xóa toàn bộ** hay **không sửa**.

Không thể khai báo **optional repeated string topics = 1;** hoặc **optional map<string, string> labels = 2;**. Nếu cần thao tác cập nhật tập hợp, thiết kế một trong các cách:

- RPC riêng như **ReplaceTopics**, **AddTopic**, **RemoveTopic**.
- **FieldMask** để xác định trường phải cập nhật, đi kèm quy tắc thay thế/merge tập hợp rõ ràng.
- Message lệnh có **oneof** phân biệt **replace** và **clear**, nếu bài toán cần cả hai hành động.

Không được giả định rằng merge Protobuf tự động tương đương thao tác *thay toàn bộ danh sách*; repeated field khi merge thường **nối thêm phần tử**.

## 9. Oneof giữ presence bằng lựa chọn nhánh

Oneof biểu đạt một nhóm phương án mà tại một thời điểm chỉ có tối đa một phương án được chọn:

~~~proto
message Recovery {
  oneof destination {
    string email = 1;
    string phone = 2;
  }
}
~~~

Java cung cấp **getDestinationCase()** để xác định nhánh đang hiện diện:

~~~java
Recovery unset = Recovery.newBuilder().build();
Recovery withEmptyEmail = Recovery.newBuilder()
    .setEmail("")
    .build();

System.out.println(unset.getDestinationCase());
// DESTINATION_NOT_SET

System.out.println(withEmptyEmail.getDestinationCase());
// EMAIL

System.out.println(withEmptyEmail.getEmail()); // ""
~~~

Nếu đặt **setEmail(...)** rồi **setPhone(...)**, nhánh sau thay thế nhánh trước. Một nhánh oneof với chuỗi rỗng vẫn có presence; giá trị mặc định không có nghĩa lựa chọn chưa được đặt.

**Optional** phù hợp với những field có thể cập nhật độc lập; **oneof** phù hợp với nhóm phương án loại trừ nhau. Không thêm nhãn optional vào một field bên trong oneof, vì oneof đã quản lý sự hiện diện theo nhánh.

## 10. Binary wire: khi nào field mặc định được ghi ra byte?

Để thấy khác biệt cụ thể, xét message:

~~~proto
syntax = "proto3";

message WireProbe {
  bool enabled = 1;
  optional bool enabled_override = 2;
  optional int32 retry_limit = 3;
}
~~~

Với builder sau:

~~~java
WireProbe value = WireProbe.newBuilder()
    .setEnabled(false)
    .setEnabledOverride(false)
    .setRetryLimit(0)
    .build();

byte[] encoded = value.toByteArray();
// Một biểu diễn binary hợp lệ:
// 10 00 18 00
~~~

Giải thích:

| Byte hex | Ý nghĩa |
| --- | --- |
| Không có byte cho field số 1 | **enabled** là scalar implicit đang bằng mặc định **false**, nên không được serialize. |
| **10 00** | Tag **0x10** = field **2**, wire type **0** (varint); dữ liệu **0** = false. |
| **18 00** | Tag **0x18** = field **3**, wire type **0**; dữ liệu **0**. |

Hai field optional được ghi ra dù đang bằng mặc định vì chúng có explicit presence. Nếu không gọi setter cho cả ba field, message có thể được mã hóa thành mảng byte rỗng.

Sau khi giải mã:

~~~java
WireProbe parsed = WireProbe.parseFrom(encoded);

System.out.println(parsed.getEnabled());             // false
System.out.println(parsed.hasEnabledOverride());     // true
System.out.println(parsed.getEnabledOverride());     // false
System.out.println(parsed.hasRetryLimit());          // true
System.out.println(parsed.getRetryLimit());          // 0
~~~

Binary Protobuf không yêu cầu mọi serializer phải phát field theo cùng thứ tự. Trong kiểm thử nghiệp vụ, nên parse rồi kiểm tra **giá trị và presence**. Kiểm tra byte hex hữu ích khi học định dạng wire hoặc chẩn đoán serialization, nhưng không thay thế kiểm thử hợp đồng.

## 11. ProtoJSON: field vắng mặt và field hiện diện bằng mặc định

ProtoJSON có cách biểu diễn rõ các field optional hiện diện bằng giá trị mặc định.

Giả sử:

~~~proto
message JsonProbe {
  string locale = 1;
  optional bool enabled = 2;
  optional int32 retry_limit = 3;
  optional string nickname = 4;
}
~~~

| Đối tượng được tạo | ProtoJSON điển hình |
| --- | --- |
| Không đặt field nào | **{}** |
| Đặt **locale = ""** | Thường vẫn là **{}** theo cách in mặc định |
| Đặt **enabled = false** | **{"enabled":false}** |
| Đặt **retry_limit = 0** | **{"retryLimit":0}** |
| Đặt **nickname = ""** | **{"nickname":""}** |

Đầu ra mặc định chuyển tên **retry_limit** thành **retryLimit**. Các tùy chọn của **JsonFormat.Printer** có thể khiến một số giá trị mặc định implicit cũng được in, nhưng **việc xuất chúng ra JSON không tự tạo presence** khi parse trở lại thành kiểu field implicit.

Sử dụng thư viện **protobuf-java-util** với API **com.google.protobuf.util.JsonFormat**:

~~~java
import com.google.protobuf.util.JsonFormat;

JsonProbe original = JsonProbe.newBuilder()
    .setLocale("")
    .setEnabled(false)
    .setRetryLimit(0)
    .build();

String json = JsonFormat.printer().print(original);

JsonProbe.Builder builder = JsonProbe.newBuilder();
JsonFormat.parser().merge(json, builder);
JsonProbe restored = builder.build();

System.out.println(restored.hasEnabled());    // true
System.out.println(restored.hasRetryLimit()); // true
System.out.println(restored.getLocale());     // ""
~~~

Với field scalar optional thông thường, ProtoJSON parser chấp nhận giá trị **null** như trường hợp **không đặt field** khi parse vào builder mới:

~~~json
{
  "nickname": null
}
~~~

Điều này khác với **{"nickname":""}**, vì chuỗi rỗng có thể hiện diện tường minh. Đừng tự gán ngữ nghĩa “xóa dữ liệu” cho JSON null khi hợp đồng chưa quy định điều đó. Một hệ thống REST gateway cần thống nhất chính sách **missing**, **null** và **present default**.

**ProtoJSON** không hoàn toàn giống JSON do thư viện chung như Jackson tự động tạo từ lớp Java Protobuf. Khi yêu cầu tuân thủ hợp đồng ProtoJSON, hãy dùng serializer/parser hiểu đúng quy tắc Protobuf.

## 12. Merge semantics: default và presence ảnh hưởng đến cách gộp

**mergeFrom()** gộp nội dung của một message vào builder của message khác. Đối với scalar có implicit presence, giá trị mặc định của nguồn thường **không ghi đè** đích. Với optional scalar, một giá trị mặc định đã được đặt vẫn **ghi đè** được.

Sử dụng schema **UserPreferences** ở mục 4:

~~~java
UserPreferences current = UserPreferences.newBuilder()
    .setUserId("u-42")
    .setLocale("vi")
    .setNickname("An")
    .setDailyLimit(10)
    .build();

UserPreferences incoming = UserPreferences.newBuilder()
    .setLocale("")
    .setNickname("")
    .setDailyLimit(0)
    .build();

UserPreferences merged = current.toBuilder()
    .mergeFrom(incoming)
    .build();

System.out.println(merged.getLocale());         // "vi"
System.out.println(merged.getNickname());       // ""
System.out.println(merged.hasNickname());       // true
System.out.println(merged.getDailyLimit());     // 0
System.out.println(merged.hasDailyLimit());     // true
~~~

**locale** vẫn là **vi** vì nguồn chỉ có một scalar implicit bằng mặc định **""**, không có presence để ra lệnh ghi đè. **nickname** và **daily_limit** thay đổi vì nguồn giữ explicit presence của giá trị mặc định.

Cần phân biệt **merge message** với thao tác **PATCH nghiệp vụ**. Message con có thể được merge theo từng field, repeated field có thể nối thêm phần tử, map có cơ chế gộp entry theo key. Nếu ứng dụng cần thay thế toàn bộ hoặc xóa dữ liệu lồng nhau, phải quy định rõ logic thay thế và không mặc định **mergeFrom()** thực hiện điều đó.

## 13. Cập nhật từng phần qua gRPC: dùng presence đúng cách

Schema **PatchPreferencesRequest** ở mục 4 cho phép client chỉ gửi field muốn cập nhật:

~~~java
import com.example.preferences.v1.PatchPreferencesRequest;

PatchPreferencesRequest request =
    PatchPreferencesRequest.newBuilder()
        .setUserId("u-42")
        .setNotificationsEnabled(false)
        .setDailyLimit(0)
        .build();

System.out.println(request.hasNotificationsEnabled()); // true
System.out.println(request.getNotificationsEnabled()); // false
System.out.println(request.hasDailyLimit());           // true
System.out.println(request.getDailyLimit());           // 0
System.out.println(request.hasNickname());             // false
~~~

Ý định của client là **tắt thông báo**, **đặt giới hạn về 0**, đồng thời **không sửa nickname**. Một server chỉ dựa vào getter sẽ dễ bỏ sót thao tác false/0 hoặc vô tình thay nickname thành chuỗi rỗng.

Ví dụ logic xử lý của một RPC unary sử dụng các lớp gRPC được sinh:

~~~java
import com.example.preferences.v1.PatchPreferencesRequest;
import com.example.preferences.v1.PreferencesServiceGrpc;
import com.example.preferences.v1.UserPreferences;
import io.grpc.Status;
import io.grpc.stub.StreamObserver;

// PreferencesRepository là interface ứng dụng tự định nghĩa, cung cấp
// phương thức findById(String) và save(UserPreferences).
public final class PreferencesEndpoint
        extends PreferencesServiceGrpc.PreferencesServiceImplBase {

    private final PreferencesRepository repository;

    public PreferencesEndpoint(PreferencesRepository repository) {
        this.repository = repository;
    }

    @Override
    public void patchPreferences(
            PatchPreferencesRequest request,
            StreamObserver<UserPreferences> observer) {

        if (request.getUserId().isBlank()) {
            observer.onError(Status.INVALID_ARGUMENT
                .withDescription("user_id must not be empty")
                .asRuntimeException());
            return;
        }

        UserPreferences current = repository.findById(request.getUserId());
        if (current == null) {
            observer.onError(Status.NOT_FOUND
                .withDescription("preferences not found")
                .asRuntimeException());
            return;
        }

        UserPreferences.Builder updated = current.toBuilder();

        if (request.hasNotificationsEnabled()) {
            updated.setNotificationsEnabled(
                request.getNotificationsEnabled());
        }
        if (request.hasDailyLimit()) {
            updated.setDailyLimit(request.getDailyLimit());
        }
        if (request.hasNickname()) {
            updated.setNickname(request.getNickname());
        }
        if (request.hasDeliveryMode()) {
            updated.setDeliveryModeValue(
                request.getDeliveryModeValue());
        }

        UserPreferences saved = repository.save(updated.build());
        observer.onNext(saved);
        observer.onCompleted();
    }
}
~~~

**PreferencesRepository** ở ví dụ là thành phần do ứng dụng tự hiện thực; server còn cần đăng ký **PreferencesEndpoint** theo cấu hình Spring gRPC cụ thể. Khi triển khai thực tế, phải bổ sung kiểm tra quyền truy cập, điều kiện miền, cập nhật nguyên tử, xử lý xung đột đồng thời và các lỗi hạ tầng.

Việc dùng **setDeliveryModeValue(...)** bảo toàn số enum trong trường hợp giá trị chưa được khai báo ở enum Java cũ; tuy nhiên ứng dụng vẫn cần chính sách chấp nhận hoặc từ chối trạng thái không nhận diện. Nếu nghiệp vụ chỉ cho phép một tập trạng thái cố định, hãy kiểm tra trước khi lưu.

Trong gRPC, metadata, deadline, interceptor, TLS và status giải quyết những mối quan tâm khác; chúng không thay đổi cách Protobuf biểu diễn presence. Với streaming RPC, quy tắc presence áp dụng **riêng cho từng message** trong luồng.

## 14. Khi chỉ có “absent” và “present” vẫn chưa đủ

Optional scalar phân biệt:

1. **Không đặt field**: thường hiểu là không cập nhật.
2. **Đặt field với một giá trị**: cập nhật bằng giá trị đó, kể cả false, 0 hoặc chuỗi rỗng.

Nhưng một số bài toán cần ba hành động độc lập:

- Không sửa nickname.
- Đặt nickname thành chuỗi rỗng, bởi chuỗi rỗng là giá trị hợp lệ.
- Xóa nickname, làm trường dữ liệu trở thành không có giá trị trong kho lưu trữ.

Nếu “đặt rỗng” khác “xóa”, một optional string không tự thể hiện đủ ba lệnh. Một thiết kế rõ ràng hơn là dùng **oneof** với lệnh xóa:

~~~proto
syntax = "proto3";
import "google/protobuf/empty.proto";

message ChangeNickname {
  string user_id = 1;

  oneof operation {
    string set_value = 2;
    google.protobuf.Empty clear_value = 3;
  }
}
~~~

Khi **operation** không được đặt, server có thể từ chối request vì thiếu hành động; khi đặt **set_value = ""**, server lưu chuỗi rỗng; khi chọn **clear_value**, server xóa giá trị theo định nghĩa nghiệp vụ. **getOperationCase()** cho biết chính xác nhánh nào được chọn.

Một phương án khác là **google.protobuf.FieldMask** để liệt kê field cần sửa, kết hợp chính sách xóa hoặc thay thế dữ liệu. FieldMask đặc biệt hữu ích khi cập nhật message lồng nhau và tập hợp, nhưng cần quy định rõ hành vi từng đường dẫn; bản thân FieldMask không tự cập nhật database.

## 15. Thay đổi schema và tương thích presence

Việc thêm field mới với số hiệu chưa dùng thường tương thích ở mức cấu trúc wire: client cũ không biết field đó có thể bỏ qua khi đọc, còn server mới phải chấp nhận trường hợp field vắng mặt.

Thay đổi một field đã phát hành từ:

~~~proto
string nickname = 2;
~~~

sang:

~~~proto
optional string nickname = 2;
~~~

thường giữ nguyên **field number** và **wire type** trên binary. Tuy vậy, semantics không hoàn toàn giống nhau:

| Tình huống | Reader/schema implicit cũ | Reader/schema optional mới |
| --- | --- | --- |
| Field vắng mặt | Getter trả **""**; không có has | Getter trả **""** và **hasNickname() == false** |
| Field có giá trị **"An"** | Getter trả **"An"** | Getter trả **"An"**, **hasNickname() == true** |
| Field được gửi tường minh dưới dạng **""** | Getter trả **""**, không biết presence | Getter trả **""**, **hasNickname() == true** |
| Gửi lại một message chứa giá trị mặc định | Có thể không serialize lại field **""** | Serialize được trường hợp present-default |

Đặc biệt, nếu một message đi qua một trung gian dùng schema cũ, trung gian ấy có thể làm mất explicit presence của giá trị mặc định khi parse rồi serialize lại. Phiên bản mới sẽ không còn biết trường hợp “đã chủ động đặt rỗng” ở đầu đường truyền.

Trước khi dựa vào proto3 optional, cần dùng **protoc** và plugin sinh mã/runtime Java hỗ trợ cú pháp optional. Các phiên bản Protobuf quá cũ có thể không hỗ trợ hoặc không sinh API presence tương ứng.

Nên kiểm thử cả hai hướng **client cũ → server mới** và **client mới → server cũ**, kể cả giai đoạn rolling deployment và đường đi qua gateway JSON. Tương thích nhị phân không đảm bảo tương thích ngữ nghĩa khi server bắt đầu yêu cầu các field mà client cũ chưa biết.

## 16. Kiểm thử giá trị mặc định và presence

Một bộ kiểm thử tối thiểu cần xác nhận:

| Trường hợp | Điều phải chứng minh |
| --- | --- |
| Optional không đặt | Getter trả mặc định, **hasXxx() == false** |
| Optional được đặt bằng mặc định | Getter trả mặc định, **hasXxx() == true** |
| Optional được xóa trên builder | **clearXxx()** đưa presence về false |
| Scalar implicit đặt mặc định | Không có has; khi merge không ghi đè như optional |
| Message con vắng mặt / message con rỗng | Getter có thể giống về nội dung nhưng **hasMessage()** khác nhau |
| Oneof chọn nhánh có giá trị mặc định | **get...Case()** báo đúng nhánh |
| Binary/ProtoJSON round-trip | Presence của optional present-default được bảo toàn |
| Client/server khác phiên bản | Không suy diễn sai ý định hoặc ghi đè field không được cập nhật |

Ví dụ JUnit 5 dựa trên schema **UserPreferences** ở mục 4:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import com.example.preferences.v1.UserPreferences;
import com.google.protobuf.util.JsonFormat;
import org.junit.jupiter.api.Test;

class PresenceTest {

    @Test
    void distinguishesAbsentFromPresentDefaults() {
        UserPreferences absent = UserPreferences.newBuilder().build();
        UserPreferences present = UserPreferences.newBuilder()
            .setNotificationsEnabled(false)
            .setDailyLimit(0)
            .setNickname("")
            .build();

        assertFalse(absent.hasNotificationsEnabled());
        assertFalse(absent.hasDailyLimit());
        assertFalse(absent.hasNickname());

        assertTrue(present.hasNotificationsEnabled());
        assertTrue(present.hasDailyLimit());
        assertTrue(present.hasNickname());
        assertFalse(present.getNotificationsEnabled());
        assertEquals(0, present.getDailyLimit());
        assertEquals("", present.getNickname());
    }

    @Test
    void survivesBinaryAndJsonRoundTrips() throws Exception {
        UserPreferences original = UserPreferences.newBuilder()
            .setNotificationsEnabled(false)
            .setDailyLimit(0)
            .build();

        UserPreferences fromBinary =
            UserPreferences.parseFrom(original.toByteArray());
        assertTrue(fromBinary.hasNotificationsEnabled());
        assertTrue(fromBinary.hasDailyLimit());

        String json = JsonFormat.printer().print(original);
        assertTrue(json.contains("\"notificationsEnabled\""));
        assertTrue(json.contains("\"dailyLimit\""));

        UserPreferences.Builder jsonBuilder = UserPreferences.newBuilder();
        JsonFormat.parser().merge(json, jsonBuilder);
        UserPreferences fromJson = jsonBuilder.build();
        assertTrue(fromJson.hasNotificationsEnabled());
        assertTrue(fromJson.hasDailyLimit());
    }

    @Test
    void mergeRespectsExplicitDefaults() {
        UserPreferences current = UserPreferences.newBuilder()
            .setLocale("vi")
            .setDailyLimit(10)
            .build();
        UserPreferences change = UserPreferences.newBuilder()
            .setLocale("")
            .setDailyLimit(0)
            .build();

        UserPreferences result = current.toBuilder()
            .mergeFrom(change)
            .build();

        assertEquals("vi", result.getLocale());
        assertEquals(0, result.getDailyLimit());
        assertTrue(result.hasDailyLimit());
    }
}
~~~

Các đoạn trên là ví dụ học tập sử dụng API Java được sinh, không phải kết quả đã chạy trên repository. Khi dự án có cấu hình Spring gRPC đầy đủ, cần bổ sung kiểm thử RPC thật (có thể qua in-process gRPC) để xác nhận server không ghi đè dữ liệu khi request thiếu field, và xử lý đúng **false**, **0**, **""** khi field hiện diện.

## 17. Các lỗi thường gặp

| Sai lầm | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Kiểm tra **getEnabled() == false** để suy ra field chưa gửi | Bỏ sót lệnh cố ý tắt thông báo | Dùng **optional bool** và **hasEnabled()** |
| Luôn ghi mọi field từ getter vào entity | Field vắng mặt ghi đè dữ liệu đang lưu bằng mặc định | Chỉ cập nhật field có presence hoặc trong mask |
| Gọi **clearNickname()** để ra lệnh xóa trong request patch | Field bị bỏ khỏi request, server có thể hiểu là không sửa | Dùng lệnh xóa riêng hoặc quy ước rõ về giá trị rỗng |
| Cho rằng message con không có presence vì getter không trả null | Không phân biệt vắng mặt và message rỗng | Kiểm tra **hasContact()** |
| Cho rằng repeated/map rỗng nghĩa là client muốn xóa | Xóa dữ liệu ngoài ý muốn | Dùng FieldMask, command hoặc RPC thay thế rõ ràng |
| Xem enum số 0 là trạng thái đã được xác nhận | Xử lý nhầm giá trị chưa xác định | Dùng tên **UNSPECIFIED**, kiểm tra presence khi cần |
| Cho rằng default in JSON luôn là dữ liệu đã gửi | Parser/formatter có thể in mặc định mà không có presence | Phân biệt explicit và implicit, kiểm thử serializer |
| Đổi scalar implicit thành optional mà không kiểm tra đường đi qua phiên bản cũ | Presence của giá trị mặc định có thể mất | Kiểm thử v1/v2 và mọi gateway/trung gian liên quan |
| Xem mergeFrom như PATCH hoàn chỉnh | Dữ liệu repeated/nested có thể bị nối hoặc gộp sai | Xây dựng semantics cập nhật theo nghiệp vụ |

## 18. Bài tập thực hành

Hãy xây dựng một API gRPC quản lý cấu hình thiết bị:

~~~proto
syntax = "proto3";

message UpdateDeviceSettingsRequest {
  string device_id = 1;
  optional bool enabled = 2;
  optional int32 sample_interval_seconds = 3;
  optional string alias = 4;
}
~~~

Yêu cầu:

1. Giải thích getter sẽ trả gì và **hasXxx()** sẽ trả gì với request chỉ đặt **device_id**.
2. Tạo request **enabled = false**, **sample_interval_seconds = 0** và **không đặt alias**. Kiểm tra tất cả trạng thái presence sau khi build.
3. Serialize/parse request, chứng minh hai giá trị mặc định đang hiện diện vẫn được giữ.
4. Chuyển request sang ProtoJSON bằng **JsonFormat** rồi parse lại; quan sát giá trị false/0.
5. Viết hàm cập nhật entity chỉ sửa field có **hasXxx() == true**, giữ alias cũ nếu client không gửi.
6. Nếu alias rỗng là một giá trị hợp lệ và thao tác xóa alias khỏi database là hành động khác, hãy đề xuất một message lệnh dùng **oneof**.
7. Thử thay **optional int32 sample_interval_seconds** thành **int32 sample_interval_seconds** trong một phiên bản schema khác; phân tích rủi ro khi phải đặt giới hạn về 0 và có trung gian dùng phiên bản cũ.

**Tiêu chí hoàn thành:** xử lý đúng cả ba giá trị **false**, **0**, **""**, không nhầm giữa getter mặc định và sự hiện diện; mô tả được giới hạn của optional đối với collection và thao tác xóa; giải thích được vì sao đổi presence có thể tác động đến merge và tương thích khi client/server triển khai độc lập.

## 19. Ghi nhớ

- **Default value** là giá trị getter trả về khi field chưa được đặt; **presence** là thông tin cho biết field đã được đặt hay chưa.
- Scalar/enum proto3 thông thường dùng **implicit presence**; **optional** tạo explicit presence và có **hasXxx()**.
- Field message vốn có presence; oneof có presence theo nhánh; repeated/map không có presence trực tiếp cho tập hợp.
- Với explicit presence, **false**, **0**, **""** có thể được serialize và merge như những giá trị được cố ý đặt.
- **clearXxx()** xóa presence trên builder; nó không mặc nhiên là một lệnh xóa dữ liệu đã lưu ở server.
- Kiểm tra cả binary, ProtoJSON, merge và nhiều phiên bản schema trước khi dựa vào presence cho tính năng cập nhật từng phần.

Nắm vững default value và presence giúp ứng dụng Spring gRPC diễn giải đúng ý định của client, tránh làm mất dữ liệu khi xử lý request unary hoặc từng message trong streaming RPC. Đây là nền tảng để thiết kế API, kiểm thử tích hợp và vận hành dịch vụ có độ tin cậy cao.
