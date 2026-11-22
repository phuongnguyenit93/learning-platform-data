# Role field protection: bảo vệ trường vai trò khỏi mass assignment

## 1. Một lần sửa hồ sơ có thể trở thành lần cấp quyền

Một API cho thành viên đổi tên hiển thị. Backend nhận JSON, ánh xạ toàn bộ thuộc tính vào entity thành viên rồi lưu. Người gọi bổ sung trường `roles` hoặc `isAdmin`, dù giao diện không hiển thị những trường đó.

Nếu cơ chế ánh xạ áp dụng chúng, người dùng có thể tự nâng quyền qua một endpoint vốn chỉ dành cho sửa hồ sơ.

**Mass assignment** xảy ra khi dữ liệu do người gọi kiểm soát được gán hàng loạt vào đối tượng hoặc cấu trúc lưu trữ mà không giới hạn đúng các thuộc tính được phép thay đổi. **Role field protection** là việc ngăn các trường làm thay đổi thẩm quyền bị ghi qua những đường không được cấp quyền quản trị tương ứng.

Ví dụ payload vượt hợp đồng:

```http
PATCH /tenants/tenant-A/members/member-17/profile
Content-Type: application/json

{
  "displayName": "An",
  "roles": ["FINANCE_APPROVER"],
  "isAdmin": true
}
```

Đăng nhập hợp lệ hoặc có quyền sửa hồ sơ của chính mình không cho người gọi quyền cấp role. Quyền sửa một đối tượng và quyền sửa mọi field của đối tượng là hai điều khác nhau.

Trong bảo vệ logic nghiệp vụ, lỗ hổng này có thể mở đường tự duyệt, sửa giá đặc biệt, chuyển owner, vượt tenant hoặc phát lệnh chi trả. Vì vậy, bảo vệ role cần được đặt ở ranh giới đầu vào, lớp ứng dụng và đường ghi dữ liệu, thay vì chỉ ở giao diện.

## 2. Xác định đầy đủ những field làm thay đổi quyền

Không chỉ một field có tên chính xác là `role` mới nhạy cảm.

| Nhóm thuộc tính | Ví dụ | Rủi ro |
|---|---|---|
| Role trực tiếp | `role`, `roles`, `roleIds` | Tự nhận hoặc thay role |
| Permission/authority | `permissions`, `authorities`, `capabilities` | Bỏ qua role để cấp quyền trực tiếp |
| Cờ đặc quyền | `isAdmin`, `isStaff`, `canImpersonate` | Kích hoạt nhánh đặc quyền |
| Nguồn kế thừa | Group ID, membership hoặc role bundle | Nhận role gián tiếp |
| Phạm vi quản trị | Tenant, phòng ban, wildcard scope | Mở rộng nơi quyền được dùng |
| Điều kiện hạn chế | Hạn mức, ngày hết hạn, restriction hoặc yêu cầu xác thực | Nới lỏng giới hạn của quyền đã có |
| Căn cứ phê duyệt | `approvedBy`, `assignmentStatus`, `overrideApproved` | Giả lập quyết định cấp quyền |

Tên cụ thể tùy mô hình. Cần theo dõi thuộc tính nào được policy dùng để quyết định quyền, không chỉ tìm một danh sách tên phổ biến.

### 2.1. Field trông như dữ liệu hồ sơ vẫn có thể là nguồn quyền

Nếu policy tự cấp role theo `accountType`, `employeeClass` hoặc một giá trị trong `settings`, cho người dùng tùy ý sửa các field đó có thể tương đương gán role.

Điều này không có nghĩa mọi thay đổi hồ sơ đều bị cấm. Cần xác định trường nào thực sự là dữ liệu có thẩm quyền cho quyền truy cập và đưa nó vào luồng được bảo vệ.

Không dùng tên hiển thị hoặc một nhãn tự khai làm nguồn xác định vai trò đặc biệt.

### 2.2. Xóa hoặc giảm một giá trị cũng có thể thay đổi quyền

Bảo vệ không chỉ là chặn thêm `ADMIN`. Xóa role của người khác là thao tác quản trị; xóa hạn chế, bỏ ngày hết hạn hoặc đặt yêu cầu kiểm soát thành `false` có thể mở rộng quyền.

Các giá trị `null`, danh sách rỗng, field vắng mặt và giá trị mặc định cần có ngữ nghĩa rõ. Không để chúng trở thành đường xóa ràng buộc hoặc tạo một chế độ fallback có quyền rộng.

## 3. Vì sao các biện pháp bề mặt chưa đủ?

### 3.1. Ẩn field trên UI không bảo vệ API

Người dùng kiểm soát client của mình và có thể gửi field ngoài form. Hidden field, nút bị khóa hoặc JavaScript không chứa chức năng đổi role không làm payload trở nên đáng tin.

TLS bảo vệ đường truyền, không chứng minh người gọi được phép thay các thuộc tính đã gửi.

### 3.2. Chỉ kiểm tra quyền sửa người dùng là quá rộng

Một nhân viên hỗ trợ có thể được sửa tên hiển thị của thành viên khác nhưng không được cấp quyền duyệt tài chính. Nếu cùng permission `user:write` điều khiển mọi thuộc tính, ranh giới này biến mất.

Tương tự, tenant admin không mặc định được cấp role quản trị nền tảng, sửa membership ở tenant khác hoặc tự phê duyệt một assignment nhạy cảm.

### 3.3. Chỉ giấu field trong response không ngăn ghi

Không trả `roles` ra JSON là một quyết định về dữ liệu đầu ra. Nó không tự chứng minh parser đầu vào, form binder hoặc lớp mapping không nhận field đó.

Ngược lại, response có thể hiển thị role hợp lệ để người dùng biết quyền của mình mà vẫn không cho sửa role qua endpoint hồ sơ. Read model và write contract cần được thiết kế riêng.

### 3.4. Private field hoặc annotation không thay hợp đồng toàn đường ghi

Setter, constructor, builder, reflection, custom deserializer và mapper có thể có các đường gán khác nhau tùy công nghệ. Không kết luận an toàn chỉ vì field là `private` hoặc có một annotation ở một lớp.

Một cấu hình chỉ tác động JSON không nhất thiết bảo vệ form binding, import hoặc một mapper nội bộ. Một thuộc tính `readOnly` trong tài liệu schema cũng chỉ có hiệu lực thực tế nếu đường xử lý thực thi đúng hợp đồng đó.

Các cơ chế framework có thể hữu ích, nhưng phải biết chúng bảo vệ đường nào và kiểm thử ở ranh giới đó.

## 4. Allowlist đầu vào và tách DTO theo hành động

### 4.1. Không dùng entity hoặc response DTO làm request cập nhật

Một entity thành viên có thể chứa profile, role, trạng thái và quan hệ tenant. Một response có thể hiển thị thêm dữ liệu phục vụ quản trị.

Nếu dùng lại toàn bộ cấu trúc đó làm request, mỗi field mới được bổ sung có thể vô tình trở thành thuộc tính client được phép ghi.

Thay vào đó, endpoint sửa hồ sơ dùng một DTO hẹp, chẳng hạn:

```java
record UpdateMemberProfileCommand(
        String displayName,
        String notificationLocale,
        long expectedVersion) {}
```

Ví dụ này chọn các thuộc tính hồ sơ theo tenant, không cấp quyền sửa role, trạng thái tài khoản toàn cục hoặc membership khác.

### 4.2. Allowlist an toàn hơn danh sách cấm không đầy đủ

Với allowlist, chỉ những field được hợp đồng công bố mới đi vào command. Một field đặc quyền mới trong entity không tự trở thành đầu vào hợp lệ.

Với denylist như “bỏ `roles` và `isAdmin`”, field mới `permissionBundleId` có thể bị bỏ sót. Denylist có thể là lớp bổ sung, nhưng không nên là toàn bộ cơ chế giới hạn quyền ghi.

Allowlist cần áp dụng theo cấu trúc, không chỉ ở object ngoài cùng. Một `settings` hoặc `metadata` map tự do vẫn nguy hiểm nếu dữ liệu bên trong được dùng làm authority hoặc được merge vào entity nhạy cảm.

### 4.3. Chọn hành vi với field ngoài hợp đồng

Hai cách có thể được thiết kế:

- Từ chối request có field không được phép, với lỗi hợp đồng rõ và không cập nhật nghiệp vụ.
- Bỏ qua field ngoài hợp đồng trong một cơ chế tương thích có kiểm soát, bảo đảm không lớp nào phía sau áp dụng chúng.

Ví dụ chính của bài chọn cách từ chối field đặc quyền trên endpoint hồ sơ. Khi chọn cách bỏ qua, test phải chứng minh role không đổi và response không khiến client tưởng field đó đã được áp dụng.

Không bắt lỗi binder rồi tiếp tục lưu một entity đã bị thay đổi một phần trước khi lỗi xảy ra.

## 5. Mapping và persistence phải giữ ranh giới

### 5.1. Tránh sao chép toàn bộ thuộc tính từ payload

Luồng nguy hiểm thường có dạng:

```text
đọc JSON thành map hoặc entity rộng
→ copy mọi thuộc tính có tên khớp sang user/member
→ lưu cả đồ thị đối tượng
```

Việc đã xác thực actor hoặc đã kiểm tra owner không làm bước copy trở nên an toàn. Cần mapping tường minh từ command hẹp sang những thay đổi được phép.

### 5.2. Tách profile với dữ liệu phân quyền khi phù hợp

Có thể quản lý profile thành viên và role assignment bằng aggregate/repository riêng. Repository sửa profile chỉ cập nhật các cột hồ sơ, không nhận danh sách role hoặc persist quan hệ role qua cascade.

Điều này giúp giảm khả năng một lần lưu entity rộng ghi nhầm dữ liệu quyền. Tuy nhiên, tách bảng không tự đủ nếu một service vẫn có thể dùng request để ghi cả hai bảng mà không qua policy.

### 5.3. Ghi lại snapshot quyền cũ cũng là một rủi ro

Không cần client trực tiếp gửi `roles` mới xảy ra lỗi. Một lần sửa profile có thể nạp entity cùng role cũ, trong khi quản trị viên vừa thu hồi role. Nếu mapper/cascade hoặc cơ chế ghi lại quan hệ áp snapshot cũ khi save, role đã thu hồi có thể bị phục hồi.

Hành vi cụ thể phụ thuộc ORM và mapping. Cần dùng đường ghi hẹp và kiểm thử thực tế, không mặc định mọi `save` đều chỉ chạm những gì giao diện định sửa.

### 5.4. Ví dụ cập nhật dữ liệu hẹp

```sql
UPDATE tenant_member_profile
SET display_name = :validated_display_name,
    notification_locale = :validated_locale,
    version = version + 1
WHERE tenant_id = :authorized_tenant_id
  AND member_id = :member_id
  AND version = :expected_version;
```

Câu lệnh không nhận hoặc cập nhật role. Vẫn phải kiểm tra quyền sửa profile, tenant, giá trị đầu vào và số dòng bị ảnh hưởng.

Đường này không thay thế API quản trị role. Nó cố ý chỉ thể hiện đúng khả năng của lệnh sửa hồ sơ.

## 6. Dữ liệu lồng nhau, PATCH và alias

### 6.1. Bảo vệ cả quan hệ lồng nhau

Ví dụ các cấu trúc cần được kiểm soát theo mô hình thực tế:

```json
{
  "profile": {"displayName": "An"},
  "memberships": [
    {
      "tenantId": "tenant-B",
      "roles": [{"id": "platform-admin"}]
    }
  ]
}
```

Một outer DTO an toàn trên danh nghĩa không đủ nếu vẫn chứa entity membership hoặc map được binder dùng để cập nhật quan hệ nhạy cảm.

Role ID tồn tại không có nghĩa người gọi được gán role đó, cho chủ thể đó hoặc trong tenant đó. ORM attach một entity theo ID không phải kiểm tra authorization.

### 6.2. JSON Patch và Merge Patch cần quyền theo đường dẫn

Nếu hỗ trợ patch theo path, không cho client thay root object, thay cả membership hoặc đi tới role qua một đường dẫn không được cấp quyền.

Allowlist cần hiểu cấu trúc path đã parse và các operation được hỗ trợ. So chuỗi prefix quá rộng có thể cho phép sửa field sâu mà endpoint không chủ ý cấp.

Với operation có nguồn như `copy` hoặc `move`, phải kiểm tra cả những đường dẫn liên quan theo hợp đồng, không chỉ đích cuối cùng. Không dùng patch như một máy cập nhật entity tổng quát ngoài kiểm soát.

Merge Patch cũng cần phân biệt vắng mặt, `null`, object rỗng và array rỗng. Không để việc thay một collection role hoặc xóa restriction được coi như sửa profile thông thường.

### 6.3. Alias và tên field phải có một cách hiểu nhất quán

Framework có thể hỗ trợ naming strategy hoặc alias cho cùng một property. Nếu đường xử lý chấp nhận các tên thay thế, bảo vệ phải áp dụng cho property thực tế sau khi diễn giải đúng hợp đồng.

Không chỉ kiểm tra chuỗi `isAdmin` ở lớp ngoài trong khi binder phía sau còn nhận một alias khác. Đồng thời, không mặc định mọi chuỗi trông giống nhau đều là alias: test theo cấu hình thực sự được hỗ trợ.

Key JSON trùng, tham số form lặp hoặc khác biệt giữa query và body cần được từ chối hoặc có quy tắc thống nhất. Không để validator đọc một giá trị còn mapper áp dụng giá trị khác.

### 6.4. Form binding và bulk API

Nếu form binder hỗ trợ đường dẫn thuộc tính lồng nhau hoặc collection, cần giới hạn tương ứng. Một field không có trên form vẫn có thể được gửi trực tiếp.

Batch phải áp dụng cùng write contract và quyền theo từng đối tượng. Không bảo vệ API đơn lẻ rồi cho bulk update nhận bất kỳ field nào trong một map.

## 7. Minh họa Java cho đường sửa profile an toàn

### 7.1. Adapter nhận một command hẹp

Ví dụ giả định `profileInput.decodeStrict` thực thi schema chỉ có `displayName`, `notificationLocale`, `expectedVersion`, kiểm tra kích thước và xử lý biểu diễn mơ hồ theo hợp đồng.

```java
UpdateMemberProfileCommand command = profileInput.decodeStrict(rawBody);
ProfileReceipt result = profileService.update(
        routeTenantId, routeMemberId, command);
```

Đây là hợp đồng minh họa, không phải API parser có sẵn. Không nhận một command chứa role rồi chỉ mong service không dùng đến.

Các entry point khác có thể dựng cùng command sau khi kiểm tra đầu vào của mình. Bất biến quan trọng vẫn là command và service này không có khả năng thay dữ liệu quyền.

### 7.2. Service cập nhật đúng khả năng

```java
ProfileReceipt update(
        UUID tenantId,
        UUID memberId,
        UpdateMemberProfileCommand command) {

    ActorContext actor = identity.requireTenantActor(tenantId);
    DisplayName name = profileRules.requireDisplayName(command.displayName());
    LocalePreference locale = profileRules.requireLocale(
            command.notificationLocale());

    return transactions.required(() -> {
        MemberProfile profile = profiles
                .lockByTenantAndMemberId(actor.tenantId(), memberId)
                .orElseThrow(NotFound::new);

        profilePolicy.requireCanEdit(actor, profile);
        profile.requireVersion(command.expectedVersion());

        int changed = profiles.updatePresentationFields(
                actor.tenantId(), memberId, profile.version(), name, locale);

        if (changed != 1) {
            throw new Conflict("CONCURRENT_MODIFICATION");
        }

        ProfileReceipt result = new ProfileReceipt(
                memberId, profile.version() + 1, name.value(), locale.value());

        audit.appendProfileUpdated(actor, profile, result);
        return result;
    });
}
```

Các dependency là thành phần ứng dụng. Các điều kiện cần được triển khai thật:

- Actor và tenant lấy từ ngữ cảnh đã xác minh, không từ role hoặc actor ID trong body.
- `profilePolicy` kiểm tra quyền sửa đúng profile trong tenant; quyền tự sửa không tự mở quyền sửa người khác.
- `MemberProfile` và repository không dùng dữ liệu request để cascade role assignment hoặc trạng thái bảo mật.
- Giá trị hồ sơ được kiểm tra theo domain; không dùng tên hiển thị hay locale để suy ra đặc quyền.
- Cập nhật có điều kiện và kiểm tra số dòng bị ảnh hưởng.
- Audit thành công và thay đổi tham gia transaction theo yêu cầu nguyên tử; lỗi không bị nuốt thành success.
- Response được xây từ kết quả có thẩm quyền, không echo các field role do request khai.

Đổi một thuộc tính trình bày không nhất thiết là thay đổi quyền. Nếu hệ thống thực sự dùng một thuộc tính làm nguồn authorization, thuộc tính đó không còn phù hợp để sửa qua đường profile hẹp này.

### 7.3. Không thêm mapper tổng quát ở cuối luồng

Một DTO hẹp có thể bị vô hiệu nếu service còn giữ raw body rồi merge lại vào entity sau khi xử lý command. Tương tự, custom field hook hoặc plugin không được tự áp dụng các property ngoài hợp đồng.

Ranh giới cần tồn tại từ parser tới persistence, không chỉ ở chữ ký hàm.

## 8. Luồng quản trị role hợp lệ phải tách riêng

### 8.1. Role có thể thay đổi nhưng cần đúng hành động

Không phải bảo vệ role nghĩa là role bất biến vĩnh viễn. Hệ thống có thể có các lệnh riêng:

```text
requestRoleAssignment
approveRoleAssignment
activateRoleAssignment
changeAssignmentScope
extendRoleAssignment
revokeRoleAssignment
```

Những lệnh này có DTO và policy quản trị rõ, không dùng chung `UpdateMemberProfileCommand`.

### 8.2. DTO quản trị vẫn là đầu vào không đáng tin

Một admin gửi role ID, subject ID, scope hoặc ngày hết hạn vẫn phải được kiểm tra:

- Có quyền quản trị loại assignment này không?
- Role có nằm trong catalog được phép cấp không?
- Người nhận và scope có thuộc tenant/phạm vi được quản trị không?
- Hạn mức, thời hạn và khả năng ủy quyền có hợp lệ không?
- Có cần phê duyệt độc lập hoặc kiểm tra tổ hợp role xung đột không?

Có một DTO tên `AdminUpdateUserRequest` không tự tạo quyền cho mọi field. Một người giữ role nghiệp vụ cũng không mặc định có quyền cấp role đó.

### 8.3. Bảo vệ cả nguồn quyền gián tiếp

Nếu không cho sửa `roles` nhưng cho tùy ý thêm mình vào group có đặc quyền, khả năng leo thang vẫn còn. Tương tự với sửa role definition, permission bundle hoặc quan hệ kế thừa.

Cần cùng mô hình quản trị cho các đường làm thay đổi quyền hiệu lực. Không giới hạn việc rà soát vào một cột `role`.

### 8.4. Không cho tự xác nhận phê duyệt bằng field

`assignmentStatus = ACTIVE`, `approvedBy` hoặc `overrideApproved = true` từ request không thay được quyết định phê duyệt đã lưu.

Nếu cần maker–checker, kiểm tra người đề nghị/người duyệt theo danh tính và scope chính sách, kể cả account phụ và ủy quyền. Dữ liệu đầu vào không được tự khai rằng điều kiện độc lập đã đạt.

## 9. Đăng ký tài khoản, token, import và service nội bộ

### 9.1. Role khởi tạo phải do quy trình server xác định

API đăng ký không nên nhận entity đầy đủ rồi áp `role` tùy ý. Server chọn trạng thái và role ban đầu theo chính sách đăng ký.

Một luồng tạo tenant có thể chủ ý cấp quyền quản trị tenant mới cho người sáng lập đã đáp ứng điều kiện. Đó là kết quả của workflow được thiết kế, không phải quyền tự chọn bất kỳ role nền tảng nào trong body.

### 9.2. Token issuer không được ký đặc quyền tự khai

Nếu server mint token từ các role trong request chưa được xác minh, người gọi có thể nhận một token ký hợp lệ nhưng mang authority sai.

Claim quyền phải được tạo từ nguồn có thẩm quyền và đúng tenant/ngữ cảnh. Kiểm tra chữ ký ở request sau không sửa được lỗi server đã ký cho role trái phép.

Ngược lại, sửa JSON của token không tạo quyền nếu cơ chế xác thực kiểm tra đúng. Không nhầm bảo vệ token với bảo vệ đường dữ liệu đã dùng để cấp token.

### 9.3. Import hoặc đồng bộ không mặc định được ghi mọi field

CSV, job provisioning hoặc API service cần hợp đồng riêng về dữ liệu được phép quản trị. Một nguồn chỉ cập nhật profile không được tùy ý gán role vì file có thêm cột đó.

Với nguồn được cấp quyền đồng bộ group/role, mapping và phạm vi phải được xác minh. Không ánh xạ một tên tùy ý bên ngoài thành role đặc quyền mà không có cấu hình có thẩm quyền.

### 9.4. Credential service rộng không thay quyền người khởi xướng

Một service có quyền ghi nhiều tenant không được dùng nó để thực hiện bất kỳ thay đổi role nào mà client gián tiếp gửi. Giữ nguồn khởi xướng, loại lệnh, tenant và căn cứ ủy nhiệm đã được xác minh.

Không thấy một request role hợp lệ thì fallback sang “service nội bộ được phép tất cả”. Thiếu dữ liệu bắt buộc phải chặn hoặc chuyển sang quy trình xử lý rõ ràng.

## 10. Từ chối, transaction, cache và audit

### 10.1. Hợp đồng lỗi không được che cập nhật một phần

Với thiết kế strict trong ví dụ, payload profile chứa field role bị cấm phải bị từ chối theo hợp đồng và không sửa profile hay quyền như một phần thành công ngầm.

Ứng dụng có thể trả `400` cho field ngoài hợp đồng. Với một lệnh role hợp lệ về cấu trúc nhưng thiếu quyền, có thể dùng `403` hoặc `404` theo chính sách tiết lộ. Không trả stack trace hoặc chi tiết role riêng tư của tenant khác.

Nếu dùng cách bỏ qua unknown field, phản hồi cần đúng ý nghĩa những gì đã áp dụng; tuyệt đối không echo role client khai như dữ liệu đã lưu.

### 10.2. Transaction không thay allowlist

Một transaction có thể commit nguyên vẹn việc nâng quyền trái phép nếu dữ liệu đã được mapper chấp nhận. Cần ngăn assignment ở ranh giới command và kiểm tra policy trước ghi.

Ngược lại, khi phát hiện vi phạm sau một bước xử lý trong transaction, lỗi phải rollback các ghi cần nguyên tử. Không catch exception rồi vẫn commit entity đã bị thay đổi.

### 10.3. Quyền thay đổi hợp lệ phải cập nhật các bản sao liên quan

Luồng role được phép cần quản lý authority version, cache invalidation và hiệu lực token theo cam kết. Endpoint profile không nên có đường làm thay đổi role mà bỏ qua các bước đó.

Nếu phát hiện dữ liệu quyền đã bị sửa trái phép từ trước, chặn mass assignment mới chưa đủ. Cần điều tra assignment hiện có, token/cache và tác động liên quan qua quy trình được cấp quyền.

### 10.4. Audit phân biệt sửa profile với sửa quyền

Ghi rõ actor thực tế, tenant, đối tượng, loại hành động và các field được đổi. Với role, cần role/scope/thời hạn trước–sau cùng căn cứ cấp, sửa hoặc thu hồi.

Với payload bị chặn, có thể ghi tên/path field đặc quyền và mã lý do theo giới hạn phù hợp, không cần lưu nguyên token, credential hoặc payload nhạy cảm.

Audit từ chối cần cơ chế không mất theo transaction nghiệp vụ rollback. Lỗi ghi log không được trở thành lý do cho phép field role đi qua.

## 11. Kiểm thử bảo vệ field role

### 11.1. Ma trận tình huống

| Tình huống | Kỳ vọng |
|---|---|
| Thêm `role`, `roles` hoặc role ID vào profile update | Không thay dữ liệu quyền; outcome đúng hợp đồng |
| Thêm cờ đặc quyền hoặc permission trực tiếp | Không đi vòng qua việc chặn field roles |
| Gửi role trong membership/đối tượng lồng nhau | Không cascade thay đổi trái phép |
| Dùng alias thực sự được binder hỗ trợ | Bảo vệ cùng property, không chỉ một tên chuỗi |
| JSON Patch thay root, role path hoặc collection membership | Không vượt allowlist theo operation/path |
| Null, array rỗng hoặc bỏ thời hạn/restriction | Không xóa điều kiện bảo vệ ngoài quyền |
| Role không phải ADMIN nhưng vẫn nhạy cảm | Không chỉ chặn một giá trị role cụ thể |
| Nhân viên hỗ trợ sửa profile người khác kèm role | Quyền sửa profile không mở quyền quản trị role |
| Tenant admin xin role nền tảng hoặc scope tenant khác | Bị chặn theo thẩm quyền quản trị |
| Body khai người duyệt hoặc status ACTIVE | Không thay quyết định có thẩm quyền |
| Đăng ký kèm role đặc quyền | Role khởi tạo theo policy server, không theo body |
| Response DTO có role được gửi ngược làm request | Không biến field đọc thành field ghi |
| Import/profile sync có cột role ngoài hợp đồng | Không gán quyền vì nguồn có thêm dữ liệu |
| Thay group/role bundle qua endpoint khác | Không là đường cấp quyền gián tiếp không được bảo vệ |
| Thu hồi role đồng thời với sửa profile | Profile save không phục hồi snapshot quyền cũ |
| Key JSON/tham số trùng | Validator và mapper không áp hai giá trị khác nhau |
| Payload hợp lệ chỉ sửa field profile được phép | Thành công, quyền giữ nguyên |
| Lệnh role hợp lệ từ quản trị viên đúng scope | Luồng quản trị riêng vẫn hoạt động |

### 11.2. Kiểm tra nguồn quyền thực tế, không chỉ response

Sau request, kiểm tra bảng/aggregate role assignment, permission trực tiếp, group và thuộc tính bảo mật liên quan. Một response không hiển thị role không chứng minh role không bị đổi.

Có thể kiểm tra hành động đặc quyền bằng ngữ cảnh xác thực phù hợp. Không chỉ dùng token cũ để kết luận quyền không đổi, vì role trong DB có thể đã bị nâng nhưng token cũ chưa phản ánh. Kiểm tra cả nguồn quyền hiện hành hoặc phiên mới theo thiết kế, không tự làm giả token để thay việc đó.

### 11.3. Thử tổ hợp field hợp lệ và đặc quyền

Gửi cả `displayName` hợp lệ và `roles` bị cấm. Với hợp đồng strict, cả lệnh phải bị từ chối theo thiết kế, không có cập nhật một phần. Với hợp đồng bỏ qua, chỉ field được phép có thể đổi và quyền phải giữ nguyên.

Kỳ vọng cần cụ thể theo API đã chọn, không chấp nhận mọi status miễn test không báo lỗi.

### 11.4. Regression khi entity thay đổi

Khi thêm field mới ảnh hưởng authorization, kiểm tra nó không tự trở thành đầu vào của các endpoint cũ. Đây là lý do command hẹp và mapping tường minh có lợi hơn copy toàn bộ entity rồi duy trì denylist.

Kiểm thử API qua parser/binder thật của ứng dụng để bắt alias và cấu trúc lồng nhau. Với cascade, transaction và race profile–role, integration test trên mapping/cơ sở dữ liệu triển khai có ý nghĩa hơn chỉ unit test DTO.

Không chỉ assert một validator được gọi. Điều cần chứng minh là không thể thay quyền hiệu lực qua đường chỉ được sửa dữ liệu thường.

## 12. Tự rà soát role field protection

Trước khi hoàn tất một endpoint cập nhật người dùng/thành viên, hãy trả lời:

1. Endpoint cấp khả năng sửa những field nào, cho ai và trong tenant nào?
2. Request DTO có chứa entity, response model hoặc map có thể mang dữ liệu quyền không?
3. Ngoài role trực tiếp, field nào làm thay đổi permission, scope, hạn mức hoặc điều kiện bảo vệ?
4. Allowlist có bao phủ cấu trúc lồng nhau, PATCH và các alias thực sự được hỗ trợ không?
5. Mapper, hook và persistence có thể ghi lại field ngoài command hoặc snapshot role cũ không?
6. Luồng đăng ký, import, token issuer và service nội bộ có cùng giữ ranh giới tin cậy không?
7. Quản trị role có lệnh, policy, phê duyệt và audit riêng không?
8. Group, role definition và kế thừa có mở một đường cấp quyền gián tiếp không được kiểm soát không?
9. Từ chối có thực sự không thay quyền hoặc commit một phần trái hợp đồng không?
10. Test có kiểm tra nguồn quyền thực tế và cả luồng profile/role hợp lệ không?

Bảo vệ field role nghĩa là mọi thay đổi thẩm quyền chỉ đi qua hành động đã được cấp phép và kiểm tra đúng ngữ nghĩa. Một request sửa hồ sơ phải giữ đúng khả năng của nó, kể cả khi người gọi gửi thêm field, cấu trúc lồng nhau hoặc dữ liệu mà cơ chế ánh xạ tự động có thể hiểu.
