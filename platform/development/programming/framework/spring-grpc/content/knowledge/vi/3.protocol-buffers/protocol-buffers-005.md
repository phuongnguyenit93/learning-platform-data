# Optional field trong proto3

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích **field presence** là gì và phân biệt field **không được gửi** với field **được đặt bằng giá trị mặc định** trong Protocol Buffers proto3.
- Khai báo **optional** cho các field scalar và enum, hiểu khác biệt với field thông thường, message field, **oneof**, **repeated** và **map**.
- Dùng các phương thức **hasXxx()**, **getXxx()**, **setXxx()** và **clearXxx()** của Java Protobuf để viết logic xử lý chính xác.
- Thiết kế request cập nhật từng phần cho dịch vụ Spring gRPC, bao gồm thao tác cố ý đặt chuỗi rỗng, số 0 hoặc **false**.
- Kiểm tra kết quả tuần tự hóa nhị phân, ProtoJSON, merge message và khả năng tương thích giữa các phiên bản schema.

## 1. Vì sao cần optional trong ứng dụng Spring gRPC?

Trong **SPRING_GRPC**, client và server trao đổi request/response được định nghĩa bằng hợp đồng **Protocol Buffers**. Công cụ **protoc** sinh các lớp Java từ tệp .proto; plugin gRPC sinh stub và lớp cơ sở cho các phương thức unary hoặc streaming RPC. Ứng dụng Spring xử lý các message đã được giải mã và áp dụng quy tắc nghiệp vụ trước khi trả kết quả.

Giả sử một client gửi lệnh sửa thông tin hồ sơ:

- Không gửi **display_name**: giữ nguyên tên hiện tại.
- Gửi **display_name = ""**: chủ động xóa tên hiển thị (nếu nghiệp vụ cho phép).
- Không gửi **is_public**: giữ nguyên chế độ hiển thị.
- Gửi **is_public = false**: chuyển hồ sơ sang chế độ riêng tư.

Nếu server chỉ gọi **getDisplayName()** hoặc **getIsPublic()** trên field scalar proto3 thông thường, nó không thể biết bên gửi cố ý đặt chuỗi rỗng/**false**, hay hoàn toàn không gửi field. Đây chính là vấn đề **field presence**.

**Optional** trong proto3 cho phép server nhận biết một scalar/enum field đã được đặt hay chưa, kể cả khi giá trị được đặt là mặc định. Điều này đặc biệt quan trọng với request **PATCH**, thao tác cập nhật từng phần, lựa chọn cấu hình, thông tin người dùng và dữ liệu có giá trị 0 mang ý nghĩa nghiệp vụ.

## 2. Phân biệt giá trị và sự hiện diện

Xét schema sau:

~~~proto
syntax = "proto3";

message UpdateProfileRequest {
  string profile_id = 1;
  string display_name = 2;
  optional bool is_public = 3;
}
~~~

**display_name** là scalar có **implicit presence**. Khi gọi **getDisplayName()**, Java trả về chuỗi rỗng nếu field chưa được đặt, và cũng trả về chuỗi rỗng nếu field được đặt bằng giá trị rỗng. API Java được sinh không có **hasDisplayName()** cho kiểu khai báo này.

**is_public** là scalar có **explicit presence** nhờ nhãn **optional**. Java sinh:

- **getIsPublic()**: trả giá trị boolean, mặc định **false** nếu field vắng mặt.
- **hasIsPublic()**: **true** nếu bên gửi hoặc builder thực sự đặt field, kể cả khi đặt **false**.
- **setIsPublic(boolean)** trên builder: đặt giá trị và đánh dấu field hiện diện.
- **clearIsPublic()** trên builder: xóa giá trị hiện diện, khiến **hasIsPublic()** thành **false**.

| Trường hợp | Giá trị đọc được | Có thể biết field đã được đặt? |
| --- | --- | --- |
| **string display_name** không gửi | **""** | Không, vì implicit presence. |
| **string display_name** đặt **""** | **""** | Không phân biệt được với không gửi. |
| **optional bool is_public** không gửi | **false** | Có: **hasIsPublic() == false**. |
| **optional bool is_public** đặt **false** | **false** | Có: **hasIsPublic() == true**. |
| **optional bool is_public** đặt **true** | **true** | Có: **hasIsPublic() == true**. |

**Giá trị mặc định không đồng nghĩa không có dữ liệu**. Với optional, giá trị và presence là hai thuộc tính phải kiểm tra riêng.

## 3. Cú pháp optional và các kiểu được phép

Proto3 khai báo optional bằng cách đặt từ khóa **optional** trước kiểu field:

~~~proto
syntax = "proto3";

package learning.profile.v1;

option java_package = "com.example.profile.v1";
option java_multiple_files = true;

enum Visibility {
  VISIBILITY_UNSPECIFIED = 0;
  VISIBILITY_PUBLIC = 1;
  VISIBILITY_PRIVATE = 2;
}

message ProfileSettings {
  optional string nickname = 1;
  optional bool notifications_enabled = 2;
  optional int32 max_sessions = 3;
  optional int64 storage_limit_bytes = 4;
  optional double score_threshold = 5;
  optional Visibility visibility = 6;
  optional bytes avatar_hash = 7;
}
~~~

Các trường trên đều có **hasXxx()** khi sinh mã Java. Nhãn optional cũng áp dụng được với nhiều kiểu scalar khác của proto3 như **uint32**, **sint64**, **fixed32**.

**Không dùng optional cho repeated hoặc map:**

~~~proto
message InvalidSettings {
  // Sai cú pháp:
  // optional repeated string tags = 1;
  // optional map<string, string> labels = 2;
}
~~~

Danh sách và map rỗng không biểu đạt được sự khác nhau giữa **không gửi** và **cố ý gửi cấu trúc rỗng** chỉ bằng repeated/map. Nếu bài toán cần sự phân biệt ấy, phải thiết kế thêm một cơ chế diễn đạt hành động cập nhật, chẳng hạn message bao ngoài, **oneof** hoặc **FieldMask**.

**Proto3 không có nhãn required.** Nhãn optional không có nghĩa field phải được gửi; ngược lại, nó diễn đạt rằng field có thể vắng mặt **và** bên nhận có thể kiểm tra điều đó. Những điều kiện như profile_id bắt buộc khác rỗng, số lượt kết nối phải dương hay nickname không vượt quá độ dài phải được kiểm tra tại tầng nghiệp vụ.

### Message field vốn đã có presence

Với message lồng nhau:

~~~proto
message Address {
  string city = 1;
}

message UpdateAddressRequest {
  string profile_id = 1;
  Address address = 2;
}
~~~

Java được sinh có **hasAddress()** ngay cả khi không thêm **optional**, vì message field trong proto3 vốn có explicit presence. **getAddress()** trả một default instance khi field vắng mặt; phải dùng **hasAddress()** nếu cần biết client đã gửi địa chỉ hay chưa.

Viết **optional Address address = 2;** trong proto3 không mang lại lợi ích presence mới ở mức API: với field message thông thường, presence đã tồn tại. Để mô tả **nhiều lựa chọn loại dữ liệu**, dùng **oneof** thay vì thêm optional vào mọi lựa chọn.

## 4. Giá trị mặc định của optional trong Java

Một field scalar optional vắng mặt vẫn có giá trị mặc định khi gọi getter:

| Kiểu proto3 | Giá trị mặc định khi không đặt | API presence |
| --- | --- | --- |
| **optional string** | **""** | **hasXxx()** |
| **optional bool** | **false** | **hasXxx()** |
| **optional int32**, **optional int64** và các kiểu số nguyên tương ứng | **0** | **hasXxx()** |
| **optional float**, **optional double** | **0.0** | **hasXxx()** |
| **optional bytes** | **ByteString.EMPTY** | **hasXxx()** |
| **optional enum** | Giá trị enum mang số **0** | **hasXxx()** |

Ví dụ:

~~~java
import com.example.profile.v1.ProfileSettings;

ProfileSettings untouched = ProfileSettings.newBuilder().build();

System.out.println(untouched.getNickname());               // ""
System.out.println(untouched.hasNickname());               // false
System.out.println(untouched.getNotificationsEnabled());  // false
System.out.println(untouched.hasNotificationsEnabled());  // false
System.out.println(untouched.getMaxSessions());           // 0
System.out.println(untouched.hasMaxSessions());           // false
~~~

Khi builder gọi setter, field trở nên hiện diện ngay cả khi đặt bằng giá trị mặc định:

~~~java
ProfileSettings explicitDefaults = ProfileSettings.newBuilder()
    .setNickname("")
    .setNotificationsEnabled(false)
    .setMaxSessions(0)
    .build();

System.out.println(explicitDefaults.hasNickname());             // true
System.out.println(explicitDefaults.hasNotificationsEnabled()); // true
System.out.println(explicitDefaults.hasMaxSessions());          // true
~~~

Đừng dùng so sánh **getMaxSessions() == 0** để kết luận field vắng mặt. Nếu 0 là một hành động hợp lệ, chẳng hạn khóa truy cập, đây có thể là nguyên nhân cập nhật sai dữ liệu.

## 5. has, set, clear và toBuilder

Builder của Protobuf Java cung cấp thao tác đặt và xóa presence. Message sau **build()** là bất biến; muốn chỉnh sửa, tạo builder mới hoặc dùng **toBuilder()**.

~~~java
ProfileSettings original = ProfileSettings.newBuilder()
    .setNickname("An")
    .setNotificationsEnabled(true)
    .build();

ProfileSettings cleared = original.toBuilder()
    .clearNickname()
    .setNotificationsEnabled(false)
    .build();

System.out.println(original.hasNickname());              // true
System.out.println(original.getNickname());              // "An"

System.out.println(cleared.hasNickname());               // false
System.out.println(cleared.getNickname());               // ""
System.out.println(cleared.hasNotificationsEnabled());   // true
System.out.println(cleared.getNotificationsEnabled());   // false
~~~

**clearNickname()** xóa sự hiện diện của field, không có nghĩa là đặt nickname thành chuỗi rỗng. Nếu thao tác nghiệp vụ cần **xóa giá trị đang lưu**, một request có thể quy ước **setNickname("")** để chỉ rõ hành động xóa; còn **clearNickname()** trên builder request sẽ tạo trường hợp **không gửi nickname**.

Không truyền **null** vào các setter scalar Java do protoc sinh để biểu đạt vắng mặt. Dùng **clearXxx()** hoặc không gọi setter. Quy ước sử dụng **null** ở tầng DTO Java khác cần được chuyển đổi tường minh trước khi dựng Protobuf message.

## 6. Optional thay đổi nội dung nhị phân như thế nào?

Field number và wire type xác định tag của field khi serialize. Với scalar **không có presence**, giá trị mặc định thường bị bỏ qua khi mã hóa; với **optional**, một field đã được đặt thành giá trị mặc định vẫn được mã hóa để giữ thông tin presence.

Ví dụ độc lập:

~~~proto
syntax = "proto3";

message PresenceSample {
  optional string title = 1;
  optional bool enabled = 2;
  optional int32 count = 3;
}
~~~

Khi tạo message với cả ba field được đặt thành giá trị mặc định:

~~~java
PresenceSample sample = PresenceSample.newBuilder()
    .setTitle("")
    .setEnabled(false)
    .setCount(0)
    .build();

byte[] bytes = sample.toByteArray();
// Một mã hóa hợp lệ:
// 0A 00 10 00 18 00
~~~

Giải thích:

| Byte | Ý nghĩa |
| --- | --- |
| **0A 00** | Field **1**, wire type **2** (length-delimited), độ dài chuỗi **0**. |
| **10 00** | Field **2**, wire type **0** (varint), giá trị boolean **false**. |
| **18 00** | Field **3**, wire type **0** (varint), giá trị integer **0**. |

Nếu **không đặt field nào**, message có thể được mã hóa thành mảng byte rỗng. Trong thực tế Protobuf không yêu cầu field xuất hiện theo thứ tự khai báo; khi kiểm thử, nên parse hoặc so sánh ý nghĩa field thay vì mặc định mọi serializer phải tạo cùng thứ tự byte.

Sau khi parse:

~~~java
PresenceSample restored = PresenceSample.parseFrom(bytes);

System.out.println(restored.hasTitle());   // true
System.out.println(restored.hasEnabled()); // true
System.out.println(restored.hasCount());   // true
~~~

**Optional không biến field thành bắt buộc và không đổi wire type của kiểu scalar.** Nó bổ sung ngữ nghĩa presence, đặc biệt khi giá trị bằng mặc định.

## 7. Thiết kế request cập nhật từng phần cho Spring gRPC

Giả sử một hồ sơ có tên hiển thị, chế độ công khai và số lượt đăng nhập tối đa. Hợp đồng:

~~~proto
syntax = "proto3";

package learning.profile.v1;
option java_package = "com.example.profile.v1";
option java_multiple_files = true;

message UpdateProfileRequest {
  string profile_id = 1;
  optional string display_name = 2;
  optional bool is_public = 3;
  optional int32 max_logins = 4;
}

message UpdateProfileResponse {
  bool updated = 1;
}

service ProfileService {
  rpc UpdateProfile(UpdateProfileRequest)
      returns (UpdateProfileResponse);
}
~~~

Mỗi optional field thể hiện sự khác biệt giữa **không yêu cầu cập nhật** và **yêu cầu cập nhật với giá trị cụ thể**. Ví dụ client muốn giữ nguyên tên, tắt công khai và đặt giới hạn bằng 0:

~~~java
UpdateProfileRequest request = UpdateProfileRequest.newBuilder()
    .setProfileId("p-42")
    .setIsPublic(false)
    .setMaxLogins(0)
    .build();

System.out.println(request.hasDisplayName()); // false
System.out.println(request.hasIsPublic());     // true
System.out.println(request.getIsPublic());     // false
System.out.println(request.hasMaxLogins());    // true
System.out.println(request.getMaxLogins());    // 0
~~~

Server đọc presence **trước** khi cập nhật:

~~~java
// Ví dụ phần logic nghiệp vụ, repository giả định cung cấp tìm/lưu hồ sơ.
void applyUpdate(UpdateProfileRequest request, ProfileEntity entity) {
    if (request.hasDisplayName()) {
        entity.setDisplayName(request.getDisplayName());
    }
    if (request.hasIsPublic()) {
        entity.setPublic(request.getIsPublic());
    }
    if (request.hasMaxLogins()) {
        entity.setMaxLogins(request.getMaxLogins());
    }
}
~~~

Ở đây **ProfileEntity** là kiểu domain minh họa, không phải lớp Protobuf tự sinh. Các setter ở entity cần tuân theo quy tắc dữ liệu của hệ thống thực tế.

Nếu code chỉ dùng **if (request.getIsPublic())**, thao tác đặt **false** sẽ bị bỏ qua. Nếu code luôn dùng **entity.setDisplayName(request.getDisplayName())**, một request chỉ cập nhật quyền riêng tư sẽ vô tình xóa tên cũ. Kiểm tra **hasXxx()** giải quyết cả hai lỗi.

### Dạng triển khai unary RPC

Đoạn server đơn giản để minh họa đọc presence và trả gRPC status:

~~~java
import com.example.profile.v1.ProfileServiceGrpc;
import com.example.profile.v1.UpdateProfileRequest;
import com.example.profile.v1.UpdateProfileResponse;
import io.grpc.Status;
import io.grpc.stub.StreamObserver;

public final class ProfileEndpoint
        extends ProfileServiceGrpc.ProfileServiceImplBase {

    private final ProfileRepository repository;

    public ProfileEndpoint(ProfileRepository repository) {
        this.repository = repository;
    }

    @Override
    public void updateProfile(
            UpdateProfileRequest request,
            StreamObserver<UpdateProfileResponse> observer) {

        if (request.getProfileId().isBlank()) {
            observer.onError(Status.INVALID_ARGUMENT
                .withDescription("profile_id must not be empty")
                .asRuntimeException());
            return;
        }

        ProfileEntity entity = repository.findById(request.getProfileId());
        if (entity == null) {
            observer.onError(Status.NOT_FOUND
                .withDescription("profile not found")
                .asRuntimeException());
            return;
        }

        if (request.hasDisplayName()) {
            entity.setDisplayName(request.getDisplayName());
        }
        if (request.hasIsPublic()) {
            entity.setPublic(request.getIsPublic());
        }
        if (request.hasMaxLogins()) {
            entity.setMaxLogins(request.getMaxLogins());
        }

        repository.save(entity);
        observer.onNext(UpdateProfileResponse.newBuilder()
            .setUpdated(true)
            .build());
        observer.onCompleted();
    }
}
~~~

**ProfileRepository** và **ProfileEntity** ở đây là các thành phần ứng dụng cần tự hiện thực. Cần đăng ký **ProfileEndpoint** với server theo cơ chế tích hợp Spring gRPC đang dùng; ví dụ chỉ tập trung vào ngữ nghĩa optional, không trình bày cấu hình server hay quản lý giao dịch.

**Deadline**, metadata, interceptor, TLS, retry và streaming là các khía cạnh khác của gRPC: chúng không thay đổi cách **hasXxx()** hoạt động, nhưng một hệ thống triển khai thực tế vẫn phải kiểm soát quyền cập nhật, kiểm tra đầu vào, giao dịch lưu dữ liệu và lỗi RPC.

## 8. Optional khác gì so với oneof?

**Optional** diễn đạt một field có thể được gửi hoặc không. **Oneof** diễn đạt một nhóm các lựa chọn mà tại một thời điểm chỉ có tối đa một lựa chọn được đặt.

~~~proto
message ContactUpdate {
  string profile_id = 1;

  oneof channel {
    string email = 2;
    string phone = 3;
  }
}
~~~

Trong Java:

~~~java
ContactUpdate update = ContactUpdate.newBuilder()
    .setEmail("")
    .build();

System.out.println(update.getChannelCase()); // EMAIL
System.out.println(update.getEmail());       // ""
~~~

Oneof có presence riêng theo nhánh được chọn. Nếu builder gọi **setEmail(...)** rồi **setPhone(...)**, nhánh sau thay thế nhánh trước. Sử dụng **optional** khi nhiều field cần được cập nhật **độc lập** trong một request; dùng **oneof** khi chỉ được chọn **một** phương án, chẳng hạn cập nhật email *hoặc* số điện thoại theo mô hình nghiệp vụ.

Đừng khai báo **optional** trực tiếp trong một nhánh oneof: cú pháp oneof đã biểu đạt presence. Với các kiểu scalar cần presence độc lập, optional thường gọn hơn việc tạo nhiều oneof chỉ chứa một field.

## 9. Optional và well-known wrapper types

Trước khi proto3 hỗ trợ optional cho scalar, một cách biểu đạt presence phổ biến là **wrapper message** như **google.protobuf.StringValue** hoặc **google.protobuf.BoolValue**:

~~~proto
syntax = "proto3";
import "google/protobuf/wrappers.proto";

message OldStyleSettings {
  google.protobuf.StringValue nickname = 1;
  google.protobuf.BoolValue enabled = 2;
}
~~~

Các wrapper là **message field**, do đó có **hasNickname()**, **hasEnabled()**. Với schema proto3 mới dùng API nhị phân, **optional string** và **optional bool** thường đơn giản hơn, giảm lớp message bao ngoài.

Không nên thay wrapper đã phát hành thành optional scalar trên **cùng một số hiệu** chỉ vì hai cách đều có presence. Dạng mã hóa của wrapper là message lồng nhau (length-delimited), còn optional bool là varint, và kiểu getter Java cũng khác. Đây là thay đổi wire đáng kể, phải dùng field mới hoặc xây dựng kế hoạch migration phù hợp.

Nếu API cần phân biệt nhiều trạng thái như **không thay đổi**, **đặt giá trị**, **xóa dữ liệu** mà một chuỗi rỗng vẫn là giá trị hợp lệ, thì optional đơn lẻ chưa đủ diễn đạt mọi hành động. Có thể dùng **oneof** chứa các command message, cờ xóa tường minh hoặc **FieldMask** với ngữ nghĩa được tài liệu hóa.

## 10. Optional trong ProtoJSON

Khi chuyển message sang ProtoJSON bằng **JsonFormat**, field scalar có explicit presence được đặt thành giá trị mặc định vẫn được xuất để giữ ý nghĩa đã đặt. Ví dụ:

~~~proto
message Preferences {
  optional string nickname = 1;
  optional bool enabled = 2;
}
~~~

Các trường hợp:

| Message | JSON điển hình |
| --- | --- |
| Không đặt field nào | **{}** |
| Đặt nickname thành chuỗi rỗng | **{"nickname":""}** |
| Đặt enabled thành false | **{"enabled":false}** |
| Đặt cả hai | **{"nickname":"","enabled":false}** |

Trong Java:

~~~java
import com.google.protobuf.util.JsonFormat;

Preferences preferences = Preferences.newBuilder()
    .setNickname("")
    .setEnabled(false)
    .build();

String json = JsonFormat.printer().print(preferences);
System.out.println(json);

Preferences.Builder parsed = Preferences.newBuilder();
JsonFormat.parser().merge(json, parsed);
System.out.println(parsed.hasNickname()); // true
System.out.println(parsed.hasEnabled());  // true
~~~

**Lưu ý về null:** Với field scalar optional thông thường, JSON **null** được ProtoJSON parser chấp nhận như **không đặt field**. Vì vậy, đừng dùng JSON null để diễn đạt thao tác cập nhật thành chuỗi rỗng hoặc để yêu cầu xóa dữ liệu khi hợp đồng chưa định nghĩa rõ:

~~~json
{
  "nickname": null
}
~~~

Payload này không tương đương với **{"nickname":""}** về presence. Khi cần cập nhật từng phần qua JSON gateway, phải thống nhất chính sách xử lý field bị thiếu và null, và kiểm thử đúng parser được gateway sử dụng.

Không đánh đồng **ProtoJSON** với JSON do một thư viện như Jackson tự động tạo từ đối tượng Java Protobuf; cơ chế mapping chung có thể cho kết quả khác. Trong ứng dụng, dùng **JsonFormat** khi yêu cầu tương thích chính thức với định dạng Protobuf JSON.

## 11. Merge semantics: vì sao optional tác động đến cập nhật?

Với Protobuf, **merge** kết hợp các message cùng kiểu. Khi field scalar có **implicit presence**, giá trị mặc định thường không được coi là dữ liệu đã được đặt để merge vào đích. Với **optional**, giá trị mặc định vẫn có presence nên có thể ghi đè giá trị trước đó.

Ví dụ:

~~~proto
message Patch {
  optional int32 retry_limit = 1;
}
~~~

~~~java
Patch original = Patch.newBuilder()
    .setRetryLimit(5)
    .build();

Patch resetToZero = Patch.newBuilder()
    .setRetryLimit(0)
    .build();

Patch merged = original.toBuilder()
    .mergeFrom(resetToZero)
    .build();

System.out.println(merged.hasRetryLimit()); // true
System.out.println(merged.getRetryLimit()); // 0
~~~

Nếu **retry_limit** chỉ là **int32** không có optional, message nguồn với giá trị 0 không thể mang ý nghĩa explicit presence như trên; merge có thể giữ lại 5. Đây là lý do explicit presence quan trọng cho các thao tác đặt lại cấu hình về **0**, **false** hoặc chuỗi rỗng.

Đối với **message field**, việc merge có thể gộp nội dung submessage thay vì thay thế toàn bộ. Đối với **repeated field**, merge thường nối thêm các phần tử. Vì vậy, không nên mặc định merge message là một phép PATCH nghiệp vụ hoàn chỉnh cho tất cả loại field; hãy thiết kế logic cập nhật riêng nếu cần thay thế danh sách, xóa nested data hoặc áp dụng ràng buộc miền.

## 12. FieldMask khi optional chưa đủ

Google Protobuf cung cấp well-known type **google.protobuf.FieldMask** để liệt kê rõ những field được cập nhật. Cơ chế này đặc biệt phù hợp khi request có message nhiều field lồng nhau hoặc cần đặt lại giá trị mặc định mà vẫn xác định phạm vi thay đổi.

Ví dụ hợp đồng:

~~~proto
syntax = "proto3";
import "google/protobuf/field_mask.proto";

message UserProfile {
  string display_name = 1;
  bool is_public = 2;
  repeated string labels = 3;
}

message PatchProfileRequest {
  string profile_id = 1;
  UserProfile profile = 2;
  google.protobuf.FieldMask update_mask = 3;
}
~~~

Client muốn đổi trạng thái công khai có thể gửi **profile.is_public = false**, đồng thời đặt đường dẫn **is_public** vào **update_mask**. Khi không có mặt trong mask, field không được cập nhật dù getter có trả về giá trị mặc định.

Ở đây server phải định nghĩa và thực thi quy tắc patch cho field trong mask, nhất là cách thay thế repeated field, xử lý submessage và trường hợp đường dẫn không hợp lệ. **FieldMask** không tự gọi repository hoặc quyết định thay thế dữ liệu; nó là một phần của hợp đồng để ứng dụng sử dụng.

Chọn cách thiết kế dựa vào nhu cầu:

| Tình huống | Cách diễn đạt thường phù hợp |
| --- | --- |
| Cập nhật độc lập vài scalar field | **optional scalar** |
| Chọn một trong nhiều phương án | **oneof** |
| Cập nhật nhiều field/nested field theo đường dẫn | **FieldMask** |
| Phân biệt đặt giá trị và lệnh xóa riêng | **oneof** với lệnh rõ ràng, hoặc hợp đồng có update_mask và quy tắc xóa |
| Danh sách cần thao tác thêm/xóa/tất cả | RPC/command chuyên biệt hoặc update_mask và quy tắc merge/replace rõ ràng |

## 13. Optional và tương thích nhiều phiên bản

Khi thêm một field mới:

~~~proto
message User {
  string id = 1;
  optional string nickname = 2;
}
~~~

Client cũ không biết field **2** nên có thể bỏ qua khi đọc Protobuf nhị phân. Server mới phải chấp nhận request từ client cũ mà không có nickname; không thể yêu cầu mọi request ngay lập tức có field mới chỉ vì đã cập nhật schema.

Khi đổi một field **string nickname = 2** đã tồn tại sang **optional string nickname = 2**, số hiệu và wire type không đổi. Đây thường là thay đổi tương thích về **định dạng nhị phân**. Tuy nhiên:

- Bản cũ có implicit presence thường **không serialize** giá trị mặc định **""**. Bản mới không thể suy ra người gửi bản cũ đã cố ý đặt rỗng hay không.
- Bản mới có optional có thể serialize **""** để ghi nhận presence. Reader bản cũ đọc được giá trị chuỗi nhưng không có API **hasNickname()**, và khi serialize lại có thể bỏ giá trị mặc định.
- Việc merge, so sánh message và cập nhật nghiệp vụ có thể đổi vì **present default** khác **absent** ở bản mới.
- Các code generator/language runtime cần đủ mới để hiểu cú pháp proto3 optional và cung cấp presence API tương ứng.

Vì vậy, đừng chỉ kiểm tra xem **parseFrom(...)** có báo lỗi hay không. Hãy thử cả dữ liệu **absent**, **present with default** và **present with non-default**, theo hai chiều giữa phiên bản cũ và mới.

Với service Spring gRPC chạy nhiều instance khi rolling deployment, một client mới có thể gọi server cũ hoặc ngược lại. Nếu logic mới phụ thuộc vào một field vừa được thêm, phải có chiến lược chấp nhận trường hợp thiếu field trong giai đoạn chuyển tiếp. Điều này cũng áp dụng cho unary và streaming RPC, chỉ khác cách request được gửi theo thời gian.

## 14. Kiểm thử field presence và round-trip

Để bảo đảm optional hoạt động theo đúng hợp đồng, tối thiểu cần kiểm tra:

1. Field không được đặt: **hasXxx()** trả **false** và getter trả giá trị mặc định.
2. Field đặt bằng mặc định: **hasXxx()** trả **true**, giá trị vẫn bằng mặc định.
3. Field đặt khác mặc định: presence và giá trị đều chính xác.
4. **clearXxx()** trên builder: xóa presence.
5. Serialize/parse nhị phân và ProtoJSON: giữ được presence khi field được đặt bằng mặc định.
6. Merge hai message: giá trị mặc định có presence vẫn được áp dụng.
7. Tích hợp gRPC: server giữ nguyên các field không được yêu cầu thay đổi và cập nhật chính xác field đặt thành **false**, **0** hoặc **""**.

Ví dụ JUnit 5 dùng lớp **ProfileSettings** từ mục 3:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import com.example.profile.v1.ProfileSettings;
import com.google.protobuf.util.JsonFormat;
import org.junit.jupiter.api.Test;

class ProfileSettingsTest {

    @Test
    void preservesExplicitDefaultsAcrossBinaryRoundTrip() throws Exception {
        ProfileSettings source = ProfileSettings.newBuilder()
            .setNickname("")
            .setNotificationsEnabled(false)
            .setMaxSessions(0)
            .build();

        ProfileSettings decoded =
            ProfileSettings.parseFrom(source.toByteArray());

        assertTrue(decoded.hasNickname());
        assertEquals("", decoded.getNickname());
        assertTrue(decoded.hasNotificationsEnabled());
        assertFalse(decoded.getNotificationsEnabled());
        assertTrue(decoded.hasMaxSessions());
        assertEquals(0, decoded.getMaxSessions());
    }

    @Test
    void distinguishesAbsentAndClearedValues() {
        ProfileSettings absent = ProfileSettings.newBuilder().build();
        ProfileSettings present = absent.toBuilder()
            .setNickname("")
            .build();
        ProfileSettings cleared = present.toBuilder()
            .clearNickname()
            .build();

        assertFalse(absent.hasNickname());
        assertTrue(present.hasNickname());
        assertFalse(cleared.hasNickname());
    }

    @Test
    void preservesExplicitDefaultInProtoJson() throws Exception {
        ProfileSettings source = ProfileSettings.newBuilder()
            .setNotificationsEnabled(false)
            .build();

        String json = JsonFormat.printer().print(source);
        assertTrue(json.contains("\"notificationsEnabled\""));

        ProfileSettings.Builder parsed = ProfileSettings.newBuilder();
        JsonFormat.parser().merge(json, parsed);
        assertTrue(parsed.hasNotificationsEnabled());
        assertFalse(parsed.getNotificationsEnabled());
    }
}
~~~

Trong kiểm thử tích hợp thực, có thể dùng gRPC in-process hoặc hạ tầng test phù hợp với stack Spring gRPC đang sử dụng, rồi gọi RPC qua client stub. Kiểm tra trạng thái gRPC khi dữ liệu không hợp lệ (ví dụ **INVALID_ARGUMENT**) tách biệt với kiểm tra field presence. Những phép thử ví dụ ở trên minh họa cách dùng API, không thay thế việc chạy build và kiểm thử của chính dự án.

## 15. Những lỗi thường gặp

| Sai lầm | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Dùng **getIsPublic() == false** để suy ra client không gửi field | Yêu cầu chủ động tắt công khai bị bỏ qua | Kiểm tra **hasIsPublic()** |
| Luôn cập nhật mọi field từ getter request | Xóa dữ liệu cũ vì getter trả mặc định | Chỉ cập nhật field có presence hoặc có trong FieldMask |
| Gọi **clearNickname()** để biểu đạt lệnh xóa nickname | Request trở thành không gửi nickname | Dùng **setNickname("")** nếu hợp đồng quy ước rỗng là xóa, hoặc lệnh xóa riêng |
| Cho rằng optional có nghĩa bắt buộc nhập | Server chấp nhận thiếu dữ liệu nghiệp vụ không hợp lệ | Kiểm tra quy tắc bắt buộc tại tầng ứng dụng |
| Dùng **optional repeated** hoặc **optional map** | Schema không hợp lệ | Dùng wrapper message/FieldMask/command cập nhật rõ ràng |
| Cho rằng JSON **null** tương đương chuỗi rỗng | Mất tín hiệu cập nhật hoặc xóa | Kiểm tra quy tắc ProtoJSON, quy ước absence và null |
| Đổi wrapper message sang optional scalar cùng số | Nguy cơ phá wire compatibility | Tạo field mới hoặc có lộ trình migration |
| Chỉ thử serialize và parse bằng cùng schema | Bỏ sót lỗi khi client/server dùng phiên bản khác | Chạy fixture và bộ đọc của ít nhất hai phiên bản |
| Giả định mergeFrom thực hiện PATCH cho mọi kiểu field | Sai cách xử lý nested message, repeated field | Thiết kế logic cập nhật/FieldMask theo từng loại dữ liệu |

## 16. Bài tập thực hành

Một dịch vụ cấu hình người dùng cần hỗ trợ các thao tác:

- Thay đổi tên hiển thị, cho phép đặt tên thành chuỗi rỗng.
- Bật hoặc tắt thông báo.
- Đặt số phiên đăng nhập tối đa, kể cả giá trị 0 (được hiểu là vô hiệu hóa truy cập).
- Bỏ qua field mà client không muốn cập nhật.

Hãy:

1. Viết message **UpdateSettingsRequest** có field **user_id** và ba optional scalar tương ứng.
2. Dựng một request chỉ **tắt thông báo** và **đặt max_sessions = 0**; xác nhận **hasNotificationsEnabled()** và **hasMaxSessions()** đều **true**, còn **hasDisplayName()** là **false**.
3. Serialize request thành byte, parse lại và xác nhận presence không mất.
4. Xuất ProtoJSON bằng JsonFormat, quan sát các khóa chứa **false** và **0**; thử parse JSON với một field mang giá trị **null** để phân tích khác biệt.
5. Viết hàm **applyUpdate** chỉ chỉnh sửa entity với field hiện diện.
6. Tạo fixture của phiên bản schema chưa có **optional** cho một field đã tồn tại, rồi thử đọc và serialize lại bằng phiên bản mới để đánh giá khác biệt presence.

Schema gợi ý:

~~~proto
syntax = "proto3";

message UpdateSettingsRequest {
  string user_id = 1;
  optional string display_name = 2;
  optional bool notifications_enabled = 3;
  optional int32 max_sessions = 4;
}
~~~

Nếu ứng dụng còn cần phân biệt **lệnh xóa** và **đặt một giá trị rỗng hợp lệ**, hãy đề xuất mở rộng hợp đồng bằng một **oneof** chứa các thao tác riêng hoặc thêm **FieldMask** cùng quy tắc cập nhật rõ ràng.

## 17. Ghi nhớ

- **Optional trong proto3** cho scalar/enum cung cấp **explicit presence**: biết field được đặt hay chưa, kể cả khi bằng giá trị mặc định.
- Getter vẫn trả mặc định khi field vắng mặt; muốn xác định presence, dùng **hasXxx()**.
- Builder **setXxx(default)** đánh dấu field hiện diện, còn **clearXxx()** xóa presence.
- Message field vốn có presence; repeated/map không dùng nhãn optional; oneof diễn đạt lựa chọn loại dữ liệu.
- Optional giúp xây dựng PATCH đơn giản, nhưng các thao tác xóa phức tạp, danh sách và message lồng nhau có thể cần **FieldMask** hoặc lệnh cập nhật riêng.
- Khi thay đổi schema, cần kiểm tra cả nhị phân, ProtoJSON, merge semantics và tương thích client/server chứ không chỉ kiểm tra compile.

Hiểu đúng optional field giúp triển khai request/response Spring gRPC an toàn hơn: server phân biệt được **không cập nhật** với **cập nhật thành giá trị mặc định**, tránh làm mất dữ liệu khi phục vụ nhiều phiên bản client trong các hệ thống unary và streaming RPC.
