# Message và field trong proto3

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Khai báo một **message** trong tệp Protocol Buffers phiên bản **proto3**, đặt tên field và cấp số hiệu field đúng quy tắc.
- Chọn giữa field đơn, **optional**, **repeated**, **map**, **oneof**, message lồng nhau và enum; hiểu kiểu dữ liệu tương ứng trong Java.
- Phân biệt **giá trị mặc định** với **sự hiện diện của field** (field presence), đặc biệt khi cập nhật dữ liệu qua gRPC.
- Sử dụng các lớp Java được sinh từ schema để tạo, đọc, tuần tự hóa message và xây dựng request/response.
- Thay đổi schema theo cách giảm rủi ro phá vỡ hợp đồng giữa client và server Spring gRPC.

## 1. Message nằm ở đâu trong ứng dụng Spring gRPC?

Trong ứng dụng Spring gRPC, tệp **.proto** mô tả hợp đồng giữa các tiến trình: dữ liệu nào được gửi và RPC nào nhận/trả dữ liệu đó. **Protocol Buffers (Protobuf)** định nghĩa cấu trúc dữ liệu và định dạng mã hóa nhị phân; **gRPC** sử dụng message ấy làm request/response khi gọi dịch vụ. Trình biên dịch **protoc** cùng các plugin sinh mã tạo lớp Java cho message và stub gRPC. Mã ứng dụng Spring sau đó làm việc với các lớp đã sinh thay vì tự phân tích byte.

Một **message** tương tự một kiểu dữ liệu có cấu trúc. Mỗi **field** là một thuộc tính có **kiểu**, **tên** và **số hiệu**. Ví dụ hệ thống quản lý hồ sơ người dùng cần gửi mã hồ sơ, tên hiển thị, kỹ năng và kênh liên hệ; một message có thể gom các thông tin đó vào một đối tượng thống nhất.

Luồng phát triển thường gặp:

~~~text
profile.proto
    |
    +-- protoc / plugin Java ------> Profile, GetProfileRequest, ...
    |
    +-- plugin gRPC Java ----------> ProfileServiceGrpc (stub, lớp cơ sở)
                                         |
                              Spring gRPC client/server
~~~

Việc chọn đúng field trong schema quan trọng hơn vẻ ngoài của cú pháp: dữ liệu mã hóa dựa trên **số hiệu field**, nên một quyết định hôm nay có thể ảnh hưởng đến khả năng đọc dữ liệu của phiên bản client/server cũ.

## 2. Ví dụ hợp đồng proto3 hoàn chỉnh

Giả sử dịch vụ quản lý hồ sơ dùng RPC unary để truy vấn một hồ sơ. Tệp **src/main/proto/profile.proto** có thể được định nghĩa như sau:

~~~proto
syntax = "proto3";

package learning.profile.v1;

option java_package = "com.example.profile.v1";
option java_multiple_files = true;

import "google/protobuf/timestamp.proto";

enum ProfileStatus {
  PROFILE_STATUS_UNSPECIFIED = 0;
  PROFILE_STATUS_ACTIVE = 1;
  PROFILE_STATUS_SUSPENDED = 2;
}

message Profile {
  string id = 1;
  string display_name = 2;
  optional string nickname = 3;
  repeated string skills = 4;
  map<string, string> labels = 5;
  ProfileStatus status = 6;
  google.protobuf.Timestamp updated_at = 7;

  oneof contact {
    string email = 8;
    string phone = 9;
  }

  message Address {
    string city = 1;
    string country_code = 2;
  }

  Address address = 10;

  // Các field đã ngừng dùng trong những phiên bản trước.
  reserved 11, 15 to 18;
  reserved "legacy_bio";
}

message GetProfileRequest {
  string profile_id = 1;
}

message GetProfileResponse {
  Profile profile = 1;
}

service ProfileService {
  rpc GetProfile(GetProfileRequest) returns (GetProfileResponse);
}
~~~

Các thành phần chính:

| Thành phần | Ý nghĩa |
| --- | --- |
| **syntax = "proto3"** | Chọn ngữ pháp proto3. |
| **package** | Namespace của schema Protobuf; giúp tránh xung đột tên giữa các hợp đồng. |
| **java_package** | Package của lớp Java được sinh, có thể khác Protobuf package. |
| **java_multiple_files = true** | Sinh các kiểu top-level như **Profile**, **GetProfileRequest**, **ProfileStatus** thành các lớp/tệp Java riêng. |
| **message Profile** | Kiểu dữ liệu dùng để truyền hồ sơ qua RPC. |
| **string id = 1** | Field có kiểu **string**, tên **id** và số hiệu **1**. |
| **service/rpc** | Mô tả phương thức gRPC nhận **GetProfileRequest**, trả **GetProfileResponse**. |

Đây là ví dụ minh họa cấu trúc hợp đồng. Phần **reserved** giả định các field số 11, 15–18 và tên **legacy_bio** từng tồn tại; với một schema mới hoàn toàn, chỉ khai báo **reserved** khi thực sự có số hiệu/tên cần chặn tái sử dụng.

## 3. Field number: danh tính trên đường truyền

Cú pháp phổ biến của một field là **[kiểu] [tên] = [số hiệu];**. Trong ví dụ **string display_name = 2;**, tên **display_name** giúp lập trình viên đọc mã nguồn, còn **2** là danh tính của field khi Protobuf mã hóa dữ liệu.

Quy tắc quan trọng:

1. Số hiệu hợp lệ từ **1 đến 536.870.911**, trừ khoảng **19.000–19.999** dành riêng cho triển khai Protobuf; **0** không hợp lệ.
2. Các field trong **cùng một message** không được trùng số hiệu. Message con hoặc message khác có phạm vi số hiệu riêng.
3. Field **1–15** có tag được mã hóa gọn hơn field **16–2047**; nên dành số nhỏ cho các field thường xuất hiện. Không cần đánh đổi tính rõ ràng chỉ để tối ưu khi chưa đo được tác động.
4. **Không đổi số hiệu** của field đã triển khai và **không tái sử dụng** số hiệu đã xóa. Hãy dùng **reserved** để giữ số hiệu hoặc tên cũ.
5. Đổi **tên field** nhưng giữ số hiệu thường không thay đổi cách đọc nhị phân; tuy nhiên có thể làm hỏng mã Java gọi getter/setter cũ hoặc hệ thống dùng Protobuf JSON. Vì vậy vẫn cần xem xét tác động của việc đổi tên.

Ví dụ, nếu một phiên bản trước có field **string old_note = 11;**, khi bỏ field đó, khai báo **reserved 11;** (và có thể **reserved "old_note";**) để tránh vô tình gán số 11 cho dữ liệu hoàn toàn khác. Không được khai báo **reserved** trùng field đang hoạt động trong cùng message.

## 4. Kiểu dữ liệu cơ bản và giá trị mặc định

Proto3 có các kiểu vô hướng (scalar) và kiểu cấu trúc. Một số ánh xạ thường dùng khi sinh mã Java:

| Kiểu trong proto3 | Java được sinh | Giá trị mặc định khi field scalar không có presence |
| --- | --- | --- |
| **string** | **String** | Chuỗi rỗng **""** |
| **bool** | **boolean** | **false** |
| **int32**, **sint32**, **uint32**, **fixed32**, **sfixed32** | **int** | **0** |
| **int64**, **sint64**, **uint64**, **fixed64**, **sfixed64** | **long** | **0L** |
| **float** | **float** | **0.0f** |
| **double** | **double** | **0.0d** |
| **bytes** | **com.google.protobuf.ByteString** | **ByteString.EMPTY** |
| **enum** | Enum Java được sinh | Phần tử có số hiệu **0** |

Lưu ý: **uint32/uint64** là kiểu số *không dấu* ở mức giao thức nhưng được biểu diễn bằng **int/long** có dấu của Java; khi cần xử lý toàn bộ miền giá trị, phải dùng thao tác chuyển đổi không dấu thích hợp. **sint32/sint64** dùng ZigZag, hiệu quả hơn **int32/int64** cho giá trị âm nhỏ; **fixed32/fixed64** có kích thước mã hóa cố định. Chọn kiểu theo dải dữ liệu và phân bố giá trị thực tế.

**Enum** trong proto3 phải có giá trị đầu tiên bằng **0**. Tên như **PROFILE_STATUS_UNSPECIFIED** giúp biểu đạt trạng thái "chưa xác định" khi không có giá trị tường minh. Không nên ngầm coi số 0 là một trạng thái nghiệp vụ đã được xác nhận.

**Message field** như **Profile address** hoặc **google.protobuf.Timestamp updated_at** có ngữ nghĩa presence: Java sinh phương thức **hasAddress()**, **hasUpdatedAt()**. Hàm **getAddress()** trả một default instance khi field vắng mặt, vì vậy cần gọi **hasAddress()** nếu phải phân biệt "không gửi địa chỉ" với "gửi địa chỉ rỗng".

## 5. Phân biệt mặc định, vắng mặt và optional

Đây là điểm dễ gây lỗi nhất khi thiết kế API cập nhật từng phần:

~~~proto
message UpdateDisplayNameRequest {
  string profile_id = 1;
  string display_name = 2;
  optional string nickname = 3;
}
~~~

Với **display_name** (scalar thông thường, implicit presence), Java gọi **getDisplayName()** sẽ nhận **""** cả khi client không gửi field lẫn khi client gửi chuỗi rỗng. Không có **hasDisplayName()** cho field scalar này.

Với **optional nickname** (explicit presence), Java có cả **hasNickname()** và **getNickname()**. Nhờ đó server phân biệt:

| Dữ liệu client gửi | hasNickname() | getNickname() | Cách hiểu khi cập nhật một phần |
| --- | --- | --- | --- |
| Không đặt **nickname** | **false** | **""** | Có thể giữ nguyên giá trị cũ |
| Đặt **nickname = ""** | **true** | **""** | Có thể chủ đích xóa biệt danh |
| Đặt **nickname = "An"** | **true** | **"An"** | Cập nhật thành **An** |

Ví dụ trong Java:

~~~java
UpdateDisplayNameRequest noChange = UpdateDisplayNameRequest.newBuilder()
    .setProfileId("p-42")
    .build();

UpdateDisplayNameRequest clearNickname = UpdateDisplayNameRequest.newBuilder()
    .setProfileId("p-42")
    .setNickname("")
    .build();

System.out.println(noChange.hasNickname());     // false
System.out.println(clearNickname.hasNickname()); // true
~~~

Không dùng **null** như tín hiệu "không có giá trị" khi làm việc với setter của mã Protobuf Java được sinh. **Optional** là đặc tính của schema, còn đối tượng message Java sau khi **build()** là bất biến.

Proto3 **không hỗ trợ nhãn required**. Muốn bắt buộc người gọi phải cung cấp mã hồ sơ không rỗng, hãy kiểm tra trong ứng dụng/server. Với một scalar phải phân biệt thiếu và giá trị mặc định, dùng **optional**, **oneof** hoặc message wrapper khi mô hình cụ thể cần; message field vốn đã có presence. Với các API cập nhật phức tạp, có thể kết hợp **FieldMask** để mô tả chính xác những field cần sửa.

## 6. repeated, map, enum, oneof và message lồng nhau

**repeated** đại diện cho danh sách gồm 0 hoặc nhiều phần tử:

~~~proto
repeated string skills = 4;
~~~

Java cung cấp các phương thức như **addSkills(...)**, **addAllSkills(...)**, **getSkillsList()**, **getSkillsCount()**. Danh sách rỗng là giá trị mặc định; bản thân repeated field không cho biết bên gửi đã "đặt danh sách rỗng" hay không truyền field. Thứ tự phần tử có ý nghĩa khi bạn sử dụng danh sách.

**map** biểu diễn tập khóa–giá trị:

~~~proto
map<string, string> labels = 5;
~~~

Java cung cấp **putLabels(...)**, **putAllLabels(...)**, **getLabelsMap()**, **containsLabels(...)**. Khóa map chỉ có thể là kiểu số nguyên phù hợp, **bool** hoặc **string**; không được là **float**, **double**, **bytes**, enum hay message. Giá trị map có thể là scalar, enum hoặc message (không trực tiếp là một map khác). **Không dựa vào thứ tự duyệt map** làm một phần của giao thức. Khi có mục nhập trùng khóa trong dữ liệu nhận, chỉ một giá trị có hiệu lực.

**oneof** diễn đạt "tối đa một trong các lựa chọn" cho cùng một nhóm dữ liệu:

~~~proto
oneof contact {
  string email = 8;
  string phone = 9;
}
~~~

Nếu builder gọi **setEmail(...)** rồi **setPhone(...)**, lựa chọn sau thay thế lựa chọn trước. Java tạo **getContactCase()** để xác định field hiện được chọn, kể cả khi giá trị field được đặt bằng giá trị mặc định:

~~~java
Profile profile = Profile.newBuilder()
    .setId("p-42")
    .setEmail("")
    .build();

System.out.println(profile.getContactCase()); // EMAIL
System.out.println(profile.getEmail());       // ""
~~~

Khi không có lựa chọn nào, **getContactCase()** cho **CONTACT_NOT_SET**. Không đưa **repeated** hoặc **map** trực tiếp vào **oneof**. Khi xử lý dữ liệu mã hóa có nhiều lựa chọn oneof, lựa chọn được gặp sau cùng sẽ có hiệu lực.

**Message lồng nhau** giúp nhóm dữ liệu theo ngữ cảnh: **Profile.Address** có **city** và **country_code**. Số hiệu **1**, **2** của **Address** không xung đột với số hiệu **1**, **2** của **Profile**. Không nên lồng quá sâu khiến hợp đồng khó tái sử dụng hoặc khó đọc.

**google.protobuf.Timestamp** là một *well-known type*, dùng để truyền mốc thời gian với ngữ nghĩa thống nhất thay vì tự quy ước chuỗi thời gian. Tệp .proto phải có câu lệnh **import** tương ứng; ứng dụng Java dùng kiểu **com.google.protobuf.Timestamp**.

## 7. Sử dụng các lớp Java được sinh

Sau khi cấu hình quá trình sinh mã Protobuf/gRPC của dự án, **java_multiple_files = true** cho phép truy cập các lớp như **Profile**, **GetProfileRequest**, **GetProfileResponse** và **ProfileServiceGrpc** trong package Java đã chọn.

Tạo một message bằng **Builder**:

~~~java
import com.example.profile.v1.Profile;
import com.example.profile.v1.ProfileStatus;

Profile profile = Profile.newBuilder()
    .setId("p-42")
    .setDisplayName("Nguyen An")
    .setNickname("") // Có presence dù là chuỗi rỗng.
    .addSkills("Java")
    .addSkills("gRPC")
    .putLabels("team", "platform")
    .setStatus(ProfileStatus.PROFILE_STATUS_ACTIVE)
    .setEmail("an@example.com")
    .setAddress(Profile.Address.newBuilder()
        .setCity("Ha Noi")
        .setCountryCode("VN")
        .build())
    .build();

System.out.println(profile.getDisplayName());  // Nguyen An
System.out.println(profile.getSkillsCount());   // 2
System.out.println(profile.hasNickname());      // true
System.out.println(profile.getContactCase());   // EMAIL
System.out.println(profile.hasAddress());       // true
~~~

**build()** tạo message bất biến. Muốn thay đổi một bản đã tạo, dùng **toBuilder()**, chỉnh sửa rồi **build()** lại. Trường **display_name** của proto thường trở thành getter Java **getDisplayName()** và setter builder **setDisplayName(...)**; Protobuf vẫn dùng số hiệu field để truyền dữ liệu.

Giao tiếp ở mức byte cũng dựa trên chính schema đó:

~~~java
byte[] bytes = profile.toByteArray();
Profile decoded = Profile.parseFrom(bytes);

System.out.println(decoded.equals(profile)); // true
~~~

Trong gRPC, framework đảm nhận tuần tự hóa request/response. Phía client chỉ cần dựng **GetProfileRequest** và gọi stub; phía server nhận **GetProfileRequest** đã giải mã. Ví dụ phần xử lý RPC phía server:

~~~java
import com.example.profile.v1.GetProfileRequest;
import com.example.profile.v1.GetProfileResponse;
import com.example.profile.v1.Profile;
import com.example.profile.v1.ProfileServiceGrpc;
import io.grpc.Status;
import io.grpc.stub.StreamObserver;

public final class ProfileEndpoint
        extends ProfileServiceGrpc.ProfileServiceImplBase {

    @Override
    public void getProfile(GetProfileRequest request,
                           StreamObserver<GetProfileResponse> observer) {
        String id = request.getProfileId();
        if (id.isBlank()) {
            observer.onError(Status.INVALID_ARGUMENT
                .withDescription("profile_id must not be empty")
                .asRuntimeException());
            return;
        }

        Profile profile = Profile.newBuilder()
            .setId(id)
            .setDisplayName("Nguyen An")
            .build();

        observer.onNext(GetProfileResponse.newBuilder()
            .setProfile(profile)
            .build());
        observer.onCompleted();
    }
}
~~~

**ProfileEndpoint** cần được đăng ký như một dịch vụ gRPC theo cơ chế bean/binding của cấu hình Spring gRPC đang dùng. Ví dụ này minh họa việc đọc field từ request, kiểm tra điều kiện nghiệp vụ, xây dựng response và trả **INVALID_ARGUMENT** khi dữ liệu không hợp lệ; nội dung bảo mật, metadata, deadline, streaming và interceptor được xử lý ở các lớp/chủ đề khác.

## 8. Thay đổi schema mà vẫn giữ tương thích

Trong hệ thống phân tán, client và server có thể triển khai phiên bản khác nhau cùng lúc. Vì vậy cần đánh giá thay đổi dựa trên định dạng truyền, mã Java được sinh và bất kỳ hệ thống JSON nào đang sử dụng.

| Thay đổi | Đánh giá và cách làm |
| --- | --- |
| Thêm field mới với **số hiệu chưa dùng** | Thường tương thích ở mức wire: phiên bản cũ bỏ qua field chưa biết; phiên bản mới phải xử lý trường hợp field vắng mặt. |
| Xóa field | Ngừng dùng số hiệu đó và thêm **reserved** cho số/tên cũ. Không cấp lại số cho dữ liệu khác. |
| Đổi số hiệu của field đang dùng | **Không an toàn**: bên nhận có thể hiểu là field khác hoặc không nhận được giá trị. |
| Đổi kiểu field | Có thể thay đổi wire type hoặc ý nghĩa dữ liệu; chỉ thực hiện sau khi đánh giá tương thích cụ thể, thường nên tạo field mới. |
| Đổi tên field | Có thể giữ tương thích nhị phân nếu giữ số hiệu/kiểu, nhưng có thể phá API Java và tên field khi trao đổi JSON. |
| Đổi field thường sang **oneof**, hoặc chuyển field giữa các oneof | Có nguy cơ mất dữ liệu/đổi ngữ nghĩa presence; phải đánh giá kỹ với message đã triển khai. |
| Thêm giá trị enum | Bên nhận cũ có thể gặp số enum không nhận biết; phải có nhánh xử lý giá trị ngoài dự kiến. Không tái sử dụng số enum đã bỏ. |

Proto3 thường bỏ qua field chưa biết khi đọc; việc bảo toàn unknown fields phụ thuộc vào đường đi dữ liệu và cách serialize lại. Đặc biệt, trung gian chuyển sang JSON hoặc ánh xạ thủ công có thể làm mất thông tin chưa biết, nên không mặc định mọi quá trình chuyển tiếp sẽ bảo toàn chúng.

Ví dụ phiên bản mới cần thêm ảnh đại diện:

~~~proto
message Profile {
  // ... các field 1 đến 10 vẫn giữ nguyên ...
  string avatar_url = 12;
  reserved 11, 15 to 18;
  reserved "legacy_bio";
}
~~~

Đã có field **11** trong lịch sử thì tiếp tục giữ **reserved 11** và cấp số **12** cho **avatar_url**. Không cố gán một ý nghĩa mới cho số 11, ngay cả khi mã nguồn hiện tại không còn dùng field cũ.

## 9. Lỗi phổ biến và cách tự kiểm tra

- **Quên ý nghĩa của giá trị mặc định:** **getId() == ""** chưa khẳng định client cố ý gửi chuỗi rỗng. Hãy kiểm tra yêu cầu nghiệp vụ hoặc dùng explicit presence khi phù hợp.
- **Dùng field scalar như trường bắt buộc:** proto3 không có **required**; tự kiểm tra **id.isBlank()**, giới hạn độ dài, miền enum và tính hợp lệ của dữ liệu trong server.
- **Dùng repeated để diễn tả cập nhật một phần:** danh sách rỗng và không gửi danh sách không thể phân biệt chỉ bằng repeated field; thiết kế thêm cơ chế cập nhật nếu cần.
- **Quên trường hợp enum chưa xác định:** quy ước phần tử số 0 là **UNSPECIFIED** và có nhánh xử lý giá trị chưa biết khi tương tác nhiều phiên bản.
- **Đổi số hiệu khi đổi tên field:** số hiệu là danh tính ở mức wire; đổi tên và đổi số là hai việc có tác động rất khác nhau.
- **Tin vào thứ tự của map:** map dùng cho tra cứu theo khóa; nếu thứ tự mang ý nghĩa nghiệp vụ, dùng **repeated** message chứa cặp khóa–giá trị.
- **Truy cập message con mà không kiểm tra presence:** dùng **hasAddress()** hoặc **hasUpdatedAt()** trước khi coi dữ liệu con là đã được gửi.

Một bài kiểm thử nhỏ nên xác nhận cả giá trị và presence:

~~~java
import static org.junit.jupiter.api.Assertions.*;

Profile source = Profile.newBuilder()
    .setId("p-42")
    .setNickname("")
    .setPhone("0900000000")
    .build();

Profile result = Profile.parseFrom(source.toByteArray());

assertEquals("p-42", result.getId());
assertTrue(result.hasNickname());
assertEquals("", result.getNickname());
assertEquals(Profile.ContactCase.PHONE, result.getContactCase());
assertFalse(result.hasAddress());
~~~

Tương tự, kiểm thử một request **không set nickname** để xác nhận **hasNickname() == false**, và kiểm thử phiên bản schema cũ/mới với các field được thêm để phát hiện vấn đề tương thích trước khi triển khai độc lập client/server.

## 10. Bài tập thực hành

Mở rộng hợp đồng **Profile** mà không thay đổi các số hiệu đã có:

1. Thêm **optional string bio = 13;** để phân biệt không cập nhật tiểu sử với chủ đích đặt tiểu sử rỗng.
2. Thêm **repeated string certifications = 14;** để lưu nhiều chứng chỉ. Quan sát các phương thức builder/list Java được sinh.
3. Viết một **GetProfileResponse** chứa **Profile**, serialize rồi parse lại, xác nhận **hasNickname()**, **getContactCase()** và **getCertificationsList()** sau round-trip.
4. Giả lập một yêu cầu cập nhật có **bio** vắng mặt và một yêu cầu đặt **bio = ""**; giải thích vì sao server phải xử lý khác nhau.
5. Giải thích vì sao không được dùng số **11** cho field mới, dù số đó không còn xuất hiện trong các field đang hoạt động.

**Kết quả cần đạt:** bạn phân biệt được ba khái niệm độc lập nhưng liên quan chặt chẽ: **tên field** giúp lập trình viên sử dụng API, **số hiệu field** bảo vệ khả năng trao đổi dữ liệu giữa các phiên bản, và **presence** quyết định server có biết bên gửi thực sự cung cấp một giá trị hay không. Đây là nền tảng để thiết kế request/response gRPC ổn định trước khi bổ sung streaming, interceptor, TLS hay các chính sách độ tin cậy.
