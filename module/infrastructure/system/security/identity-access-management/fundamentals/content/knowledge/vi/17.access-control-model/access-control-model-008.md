# Field-level access

## 1. Field-level access bảo vệ điều gì?

**Field-level access** là kiểm soát quyền truy cập ở mức từng trường dữ liệu của một tài nguyên. Người được phép truy cập một hồ sơ chưa chắc được đọc hoặc sửa mọi thuộc tính trong hồ sơ đó.

Ví dụ, hồ sơ nhân viên có thể chứa:

```json
{
  "id": "E-104",
  "displayName": "Lan",
  "department": "Platform",
  "workEmail": "lan@example.test",
  "homeAddress": "Địa chỉ minh họa",
  "salary": 30000000,
  "managerNotes": "Ghi chú nội bộ minh họa",
  "tenantId": "acme",
  "managerId": "E-020"
}
```

Toàn bộ giá trị trong bài là dữ liệu giả định. Đồng nghiệp có thể cần tên, phòng ban và email công việc. Lan cần xem thông tin cá nhân của mình. Người quản lý cần một số ghi chú về nhân viên trực tiếp. Bộ phận payroll cần dữ liệu lương trong phạm vi được giao.

Nếu API chỉ kiểm tra “được xem hồ sơ E-104” rồi serialize toàn bộ object, những người này có thể nhận nhiều dữ liệu hơn quyền của họ.

OWASP gọi nhóm lỗi liên quan là Broken Object Property Level Authorization: truy cập một đối tượng không đủ để kết luận được đọc hay thay đổi mọi property của đối tượng đó. Lỗi có thể xảy ra ở cả chiều trả dữ liệu và chiều nhận cập nhật. [Nguồn: OWASP API Security Top 10 — API3:2023](https://owasp.org/API-Security/editions/2023/en/0xa3-broken-object-property-level-authorization/).

Trong IAM, field-level access là một mức phân quyền chi tiết. Nó cần kết hợp danh tính, hành động, tài nguyên, quan hệ và ngữ cảnh phù hợp với nghiệp vụ.

## 2. Phân biệt quyền chức năng, quyền đối tượng và quyền trường

| Mức kiểm soát | Câu hỏi | Ví dụ |
| --- | --- | --- |
| Function-level | Có được dùng chức năng này không? | Có được gọi API quản lý nhân viên? |
| Object-level hoặc row-level | Có được truy cập đối tượng cụ thể không? | Có được xem hồ sơ E-104 thuộc Acme? |
| Field-level hoặc property-level | Được đọc hoặc ghi phần nào của đối tượng? | Có được đọc salary hoặc sửa managerId? |

Các mức kiểm soát bổ sung cho nhau.

Một người có quyền đọc trường salary trong phạm vi payroll vẫn không được đọc salary của tenant khác nếu không có quyền trên đối tượng tương ứng. Ngược lại, có quyền xem một hồ sơ trong danh bạ không tự cho phép đọc salary.

Một biểu thức khái niệm:

```text
allow_read_field(subject, object, field, context)
    = được truy cập object trong phạm vi phù hợp
      AND được đọc field theo chính sách
      AND thỏa các điều kiện bắt buộc
```

Với ghi:

```text
allow_write_field(subject, object, field, proposed_value, context)
    = được thực hiện loại cập nhật trên object
      AND được thay đổi field
      AND được thực hiện chuyển trạng thái tương ứng
      AND dữ liệu hợp lệ
```

Quyền truy cập và tính hợp lệ của giá trị là hai điều kiện khác nhau. Một mức lương đúng kiểu số và nằm trong khoảng hợp lệ vẫn không được chấp nhận nếu người gửi không có quyền điều chỉnh lương.

## 3. Quyền đọc và quyền ghi cần được mô hình hóa riêng

Một trường có thể:

- Được đọc nhưng không được sửa.
- Được ghi qua một nghiệp vụ đặc biệt nhưng không được đọc lại nguyên giá trị.
- Được đọc ở dạng rút gọn nhưng chỉ một nhóm được xem đầy đủ.
- Không được xuất hiện trong API thông thường.

Ví dụ, Lan có thể xem salary của mình nhưng không được tự tăng salary. Người quản lý có thể sửa managerNotes của nhân viên trực tiếp nhưng không được đọc salary nếu chính sách tổ chức không cấp quyền đó.

Không nên dùng một cờ `accessible=true` chung cho cả hai chiều. Hệ thống có thể cần các quyền:

```text
employee.read_field.salary
employee.update_compensation
employee.read_field.manager_notes
employee.write_field.manager_notes
employee.change_reporting_line
```

Đây là tên quyền minh họa, không phải chuẩn bắt buộc. Chọn một hành động nghiệp vụ như `update_compensation` thường rõ hơn cho thao tác cần phê duyệt hoặc kiểm soát bổ sung, thay vì cho phép ghi một cột bất kỳ qua API hồ sơ chung.

Quyền ghi một field cũng không tự bao gồm quyền thay đổi những field khác có quan hệ. Sửa `displayName` không cho phép sửa `tenantId`, `managerId` hoặc những thuộc tính quyết định phân quyền.

## 4. Ví dụ chính sách cho hồ sơ nhân viên

### 4.1. Giả định nghiệp vụ

Ta xét ứng dụng nhân sự của Acme với các phạm vi:

- **Bản thân**: người dùng truy cập đúng hồ sơ gắn với danh tính mình.
- **Quản lý trực tiếp**: quan hệ quản lý hiện hành với nhân viên.
- **Payroll được phân công**: người có quyền payroll trên tập nhân viên được giao.
- **Đồng nghiệp**: chỉ có quyền danh bạ trong phạm vi tổ chức cho phép.

Giả định mọi tài khoản đang hoạt động và các kiểm tra tenant, phạm vi đối tượng đã đạt. Bảng dưới chỉ mô tả quyền trường trong những điều kiện đó.

### 4.2. Quyền đọc

| Trường | Bản thân | Quản lý trực tiếp | Payroll được phân công | Đồng nghiệp |
| --- | --- | --- | --- | --- |
| id, displayName, department, workEmail | Có | Có | Có | Có |
| homeAddress | Có | Không | Không | Không |
| salary | Có | Không | Có | Không |
| managerNotes | Không | Có | Không | Không |

Việc payroll không được đọc homeAddress trong ví dụ là một lựa chọn nghiệp vụ. Một hệ thống khác có thể cần địa chỉ cho công việc thuế, nhưng phải cấp quyền theo nhu cầu đó, không tự suy ra từ nhãn payroll.

Một người có nhiều quan hệ hoặc role cần được đánh giá theo quy tắc kết hợp được thiết kế. Ví dụ, một payroll user đọc hồ sơ của chính mình có thể xem homeAddress qua quan hệ bản thân, dù nhánh payroll không cấp trường đó.

### 4.3. Quyền ghi

| Thao tác hoặc trường | Người được phép theo ví dụ |
| --- | --- |
| Đổi displayName qua luồng hồ sơ cá nhân | Bản thân |
| Đổi homeAddress qua luồng hồ sơ cá nhân | Bản thân |
| Sửa managerNotes | Quản lý trực tiếp của nhân viên tương ứng |
| Điều chỉnh salary | Payroll được phân công, qua nghiệp vụ điều chỉnh lương |
| Đổi department hoặc managerId | Quy trình quản trị nhân sự riêng, ngoài API hồ sơ cá nhân |
| Đổi id hoặc tenantId | Không cho cập nhật qua những API đang xét |

Quy trình điều chỉnh lương còn có ràng buộc tách nhiệm vụ: người có quyền payroll không được tự điều chỉnh lương của mình trong ví dụ này. Quyền role được cấp chưa làm mất điều kiện hạn chế đó.

Những ràng buộc bắt buộc như tenant hoặc tách nhiệm vụ không nên bị một nhánh allow rộng vô tình bỏ qua. Cần định nghĩa thứ tự và cách kết hợp chính sách rõ ràng.

### 4.4. Kết hợp RBAC, ABAC và ReBAC

Một quyết định có thể dựa trên nhiều loại dữ kiện:

```text
Được đọc salary nếu:
    người gọi là chính nhân viên
    OR là payroll được phân công trong phạm vi phù hợp

Được sửa managerNotes nếu:
    người gọi có quan hệ quản lý trực tiếp hiện hành

Được điều chỉnh salary nếu:
    có quyền payroll phù hợp
    AND được phân công đối tượng
    AND người gọi không phải chính nhân viên
    AND quy trình điều chỉnh cho phép chuyển trạng thái này
```

Role thể hiện chức năng, quan hệ thể hiện người quản lý hoặc phạm vi phân công, còn thuộc tính và ngữ cảnh thể hiện điều kiện bổ sung. Field-level access là mức chi tiết của quyết định, không bắt buộc chỉ dùng một kiểu mô hình.

## 5. Kiểm soát chiều đọc: chỉ dựng biểu diễn được phép trả

### 5.1. Không trả domain entity nguyên vẹn

Một cách dễ gây lộ dữ liệu là:

```text
requireCanReadEmployee(principal, employee)
return serialize(employee)
```

Dòng kiểm tra có thể chỉ cấp quyền danh bạ, trong khi entity còn chứa salary, homeAddress và managerNotes.

Cách tiếp cận rõ ràng hơn là xây response từ những field được phép:

```text
requireObjectAccess(principal, employee)

readableFields = policy.readableFields(principal, employee, context)
response = approvedProjection(employee, readableFields)

return response
```

Không nên chuyển toàn bộ entity xuống client rồi dùng JavaScript ẩn field. Dữ liệu đã tới trình duyệt vẫn có thể được xem qua công cụ phát triển hoặc một HTTP client khác.

### 5.2. Ví dụ ánh xạ có kiểm soát

Đoạn mã kiểu Java sau minh họa việc dựng response. Nó giả định đã kiểm tra object và những field danh bạ luôn được đọc trong luồng này:

```java
Map<String, Object> response = new LinkedHashMap<>();
response.put("id", employee.id());
response.put("displayName", employee.displayName());
response.put("department", employee.department());
response.put("workEmail", employee.workEmail());

if (policy.canRead(principal, employee, EmployeeField.HOME_ADDRESS, context)) {
    response.put("homeAddress", employee.homeAddress());
}

if (policy.canRead(principal, employee, EmployeeField.SALARY, context)) {
    response.put("salary", employee.salary());
}

if (policy.canRead(principal, employee, EmployeeField.MANAGER_NOTES, context)) {
    response.put("managerNotes", employee.managerNotes());
}
```

Đây là minh họa ý tưởng, không phải mã tích hợp sẵn vào repository. Các type và dịch vụ policy cần được hiện thực trong hệ thống thật.

Điểm quan trọng là danh sách field đầu ra được chủ động xác định. Khi entity có thêm một cột nhạy cảm, cột đó không tự xuất hiện chỉ vì serializer phát hiện getter mới.

### 5.3. DTO và projection hỗ trợ ranh giới dữ liệu

Một DTO danh bạ có thể chỉ chứa:

```java
record EmployeeDirectoryView(
    String id,
    String displayName,
    String department,
    String workEmail
) {}
```

DTO làm rõ hợp đồng đầu ra, nhưng chưa tự chứng minh người gọi được xem đối tượng. Với các trường phụ thuộc quan hệ hoặc ngữ cảnh, vẫn cần policy trước khi tạo biểu diễn.

Projection ở tầng truy vấn giúp không lấy những cột không cần thiết. Tuy nhiên, truy vấn chọn ít cột và việc ra quyết định quyền là hai trách nhiệm khác nhau; một projection cố định chưa thay thế chính sách động.

## 6. Bỏ field, trả null và che một phần dữ liệu

### 6.1. Bỏ field khỏi response

Nếu người gọi không được đọc salary, API có thể không đưa field salary vào response. Cách này thể hiện rằng field không thuộc biểu diễn đang được cấp.

Ví dụ response danh bạ:

```json
{
  "id": "E-104",
  "displayName": "Lan",
  "department": "Platform",
  "workEmail": "lan@example.test"
}
```

### 6.2. Trả null

Một số hợp đồng API chọn trả `salary: null`. Khi đó cần quy định null mang nghĩa không có giá trị, bị ẩn hay cả hai.

Nếu client phải phân biệt “chưa nhập” với “không được xem”, có thể cần một biểu diễn riêng. Nhưng metadata về việc field có dữ liệu cũng có thể nhạy cảm; không nên tự công bố `hasSalary=true` nếu chính sách không cho phép.

### 6.3. Masking là một mức công bố dữ liệu

Trường tài khoản ngân hàng có thể không được trả nguyên giá trị, nhưng được công bố phần cuối:

```json
{
  "bankAccountLast4": "4321"
}
```

Đây là quyền đọc một biểu diễn đã rút gọn, không phải quyền đọc full bankAccount. Cần bảo đảm giá trị đầy đủ không vẫn nằm trong field ẩn, response header, log hoặc object lồng bên cạnh.

Masking cũng không đồng nghĩa mã hóa hay ẩn danh. Bốn số cuối, độ dài hoặc tiền tố có thể là thông tin đáng bảo vệ tùy dữ liệu và bối cảnh.

### 6.4. Yêu cầu chọn field không tạo quyền

API có thể nhận:

```text
GET /employees/E-104?fields=id,displayName,salary
```

Tập field được trả phải nằm trong phạm vi được yêu cầu và được phép:

```text
returned_fields
    = requested_fields
      INTERSECT allowed_read_fields
      INTERSECT supported_response_fields
```

Hợp đồng cũng có thể chọn từ chối request nếu yêu cầu chứa field không được phép, thay vì trả tập con. Cần chọn hành vi rõ ràng và nhất quán.

Dù chọn cách nào, client yêu cầu salary không tự cấp cho client quyền đọc salary.

## 7. Kiểm soát chiều ghi và mass assignment

### 7.1. Lỗi bind request vào entity

Giả sử API hồ sơ cá nhân cho phép sửa displayName và homeAddress. Người dùng gửi:

```json
{
  "displayName": "Lan mới",
  "homeAddress": "Địa chỉ mới minh họa",
  "salary": 90000000,
  "tenantId": "other-tenant",
  "managerId": "E-999"
}
```

Nếu framework bind mọi field vào entity và backend gọi save, các thuộc tính nhạy cảm có thể bị thay đổi dù giao diện chưa từng hiển thị ô nhập tương ứng.

Đây là một dạng mass assignment. OWASP khuyến nghị dùng input DTO dành riêng và allowlist những thuộc tính có thể bind; các biện pháp đó vẫn phải đi cùng kiểm tra quyền trên đối tượng và hành động. [Nguồn: OWASP — Mass Assignment Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Mass_Assignment_Cheat_Sheet.html).

### 7.2. Allowlist tốt hơn việc chỉ loại vài field đã biết

Nếu input cho phép mọi field trừ salary và tenantId, một field mới như `isPrivileged` có thể trở nên sửa được khi entity được mở rộng.

Một hợp đồng cập nhật tên có thể chỉ nhận:

```java
record ChangeDisplayNameCommand(String displayName) {}
```

Hợp đồng này không có managerId hoặc salary. Backend vẫn phải kiểm tra người gọi có được đổi displayName của đúng hồ sơ hay không.

Không nên dùng cùng một DTO đọc đầy đủ làm DTO cập nhật. Danh sách field được đọc và được ghi thường khác nhau.

### 7.3. Chọn cách xử lý field bị cấm

Với ví dụ này, ta chọn hành vi nghiêm ngặt: nếu request cập nhật hồ sơ chứa một field không được phép, toàn bộ request bị từ chối và không field nào được lưu.

Như vậy, request ở phần 7.1 không được đổi displayName rồi âm thầm bỏ salary. Client nhận một kết quả phù hợp với hợp đồng và có thể sửa request.

Một API khác có thể chủ ý bỏ qua một số unknown field để tương thích, nhưng phải phân biệt rõ unknown field với một field nhạy cảm bị cấm. Không được báo cập nhật thành công một giá trị mà hệ thống thực ra không chấp nhận.

### 7.4. Kiểm tra trước khi làm thay đổi entity được quản lý

Luồng an toàn về thứ tự xử lý:

```text
1. Xác thực principal.
2. Nạp đúng đối tượng trong phạm vi tenant.
3. Phân tích các field và thao tác được yêu cầu.
4. Kiểm tra quyền đối tượng và toàn bộ field liên quan.
5. Kiểm tra giá trị và chuyển trạng thái nghiệp vụ.
6. Áp dụng các thay đổi đã được cho phép.
7. Ghi dữ liệu theo giao dịch phù hợp.
8. Dựng response theo quyền đọc, không trả entity nguyên vẹn.
```

Không nên bind trước vào một entity đang được ORM quản lý rồi mới kiểm tra. Dirty checking hoặc một lần flush ngoài dự kiến có thể làm dữ liệu bị thay đổi trước khi luồng kiểm tra kết thúc.

Một field bị cấm vẫn cần bị từ chối nếu giá trị gửi vào trùng với giá trị hiện hành, theo hợp đồng nghiêm ngặt đang chọn. Không nên dùng việc so sánh bí mật với input của người dùng làm cách quyết định họ có được gửi field đó hay không.

## 8. Cập nhật từng phần: absent, null và thao tác xóa

### 8.1. Field không có trong request khác với field có giá trị null

Với một API cập nhật từng phần:

```json
{
  "displayName": "Lan mới"
}
```

không nên tự hiểu là xóa homeAddress chỉ vì homeAddress không xuất hiện.

Trong khi:

```json
{
  "homeAddress": null
}
```

có thể là yêu cầu xóa hoặc đặt giá trị null, tùy hợp đồng. Cả việc gán lẫn xóa đều là thay đổi cần quyền.

Một DTO chỉ dùng nullable field có thể không phân biệt được “không gửi” và “gửi null”. Tầng phân tích request cần giữ được thông tin presence nếu giao thức đòi hỏi.

### 8.2. JSON Merge Patch

Trong JSON Merge Patch, giá trị null trong một member của object biểu thị việc loại bỏ member đó khỏi tài liệu đích; các member không xuất hiện không bị thay đổi theo cách đó. Đây là ngữ nghĩa của định dạng, không phải quy tắc chung cho mọi PATCH JSON. [Nguồn: RFC 7396 — JSON Merge Patch](https://www.rfc-editor.org/rfc/rfc7396).

Khi ánh xạ vào domain, phải xác định việc loại bỏ member tương ứng với điều gì và có được nghiệp vụ cho phép không. Một field bắt buộc hoặc field hệ thống không thể bị xóa chỉ vì patch hợp lệ về cú pháp.

### 8.3. Thay thế toàn bộ đối tượng

Một thao tác thay thế có thể ảnh hưởng cả những field không có trong body, vì hợp đồng có thể gán lại chúng về mặc định hoặc loại bỏ chúng.

Không chỉ kiểm tra những key được gửi rồi bỏ qua các thay đổi ngầm. Cần xác định toàn bộ tác động dự kiến trước khi lưu.

Với dữ liệu có nhiều field hệ thống, API hành động chuyên biệt thường dễ giữ ranh giới hơn một endpoint thay thế entity tùy ý.
