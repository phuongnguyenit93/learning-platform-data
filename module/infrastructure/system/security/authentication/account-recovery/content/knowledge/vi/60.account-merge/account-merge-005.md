# Profile data reconciliation

## 1. Đối soát dữ liệu hồ sơ khi hợp nhất tài khoản

Trong quá trình khôi phục tài khoản, người dùng có thể phát hiện mình có hai tài khoản: một tài khoản cũ chứa lịch sử sử dụng và một tài khoản mới được tạo khi mất quyền truy cập. Nếu sản phẩm cho phép hợp nhất, hệ thống phải quyết định dữ liệu hồ sơ nào được giữ, dữ liệu nào được chuyển và trường nào cần người có thẩm quyền lựa chọn.

**Profile data reconciliation** là quá trình đối chiếu các giá trị hồ sơ, áp dụng chính sách theo từng trường, giải quyết xung đột và tạo một kết quả có thể giải thích, truy vết. Đây không phải thao tác sao chép toàn bộ đối tượng người dùng từ tài khoản này sang tài khoản kia.

Trong phạm vi `SECURITY_AUTHENTICATION_ACCOUNT_RECOVERY`, mục tiêu là giúp người dùng giữ lại thông tin cần thiết sau recovery mà không vô tình chuyển danh tính đã xác minh, yếu tố xác thực hoặc quyền truy cập sang một tài khoản không đủ điều kiện.

Ví dụ: tài khoản cũ của Linh có tên hiển thị “Linh Nguyễn”, ngôn ngữ tiếng Việt và một địa chỉ email đã được xác minh trong ngữ cảnh tài khoản cũ. Tài khoản mới có tên “Linh”, ngôn ngữ tiếng Anh và email khác. Hệ thống có thể cho Linh chọn tên hiển thị và ngôn ngữ, nhưng không được vì hợp nhất tên mà tự gắn cờ xác minh của email cũ cho email mới.

## 2. Điều kiện an toàn trước khi đọc và hợp nhất

Đối soát hồ sơ chỉ bắt đầu khi quy trình merge đã xác lập quyền thao tác đối với cả hai tài khoản theo chính sách sản phẩm. Đang đăng nhập vào tài khoản mới không đủ để lấy dữ liệu của tài khoản cũ.

Các điều kiện đầu vào cần có:

- Tài khoản nguồn và tài khoản đích đã được xác định từ dữ liệu có thẩm quyền.
- Người thao tác có quyền xem và đề nghị hợp nhất cả hai hồ sơ.
- Tuyến recovery hoặc xác thực cần thiết đã hoàn thành, còn hiệu lực và đúng phạm vi.
- Cặp tài khoản thuộc phạm vi merge được hỗ trợ, bao gồm tenant hoặc tổ chức nếu có.
- Không có trạng thái ngăn merge như hồ sơ đang bị điều tra hoặc ràng buộc quản lý chưa được giải quyết, nếu chính sách sản phẩm quy định.
- Hệ thống đã xác định tài khoản nào tồn tại sau merge và tài khoản nào trở thành nguồn chuyển dữ liệu.

Hai tài khoản có cùng tên, ảnh đại diện hoặc email giống nhau không tự chứng minh chúng thuộc cùng một chủ thể. So khớp hồ sơ có thể hỗ trợ phát hiện trùng, nhưng không thay thế việc xác minh thẩm quyền.

Ngay cả khi người dùng có quyền với cả hai tài khoản, họ vẫn không mặc nhiên được chuyển dữ liệu do một tổ chức quản lý sang tài khoản cá nhân. Quyền thao tác của người dùng và quyền chuyển từng loại dữ liệu là các điều kiện khác nhau.

## 3. Phân loại trường trước khi chọn quy tắc

Không thể áp dụng một chiến lược chung cho mọi thuộc tính trong bảng `user`.

| Nhóm dữ liệu | Ví dụ | Cách xử lý phù hợp |
|---|---|---|
| Hồ sơ hiển thị | Tên hiển thị, giới thiệu ngắn, ảnh đại diện | Theo chính sách từng trường, có thể cần người dùng chọn |
| Tùy chọn trải nghiệm | Ngôn ngữ, múi giờ, định dạng ngày | Giữ đích hoặc cho chọn; không làm thay đổi mức tin cậy |
| Kênh liên hệ | Email, số điện thoại | Xử lý theo quy trình liên kết và xác minh riêng |
| Thuộc tính đã chứng thực | Tên đã xác minh, mức độ xác minh danh tính | Giữ nguồn gốc và phạm vi chứng thực; không sao chép cờ đơn lẻ |
| Quyền và quan hệ tổ chức | Vai trò, nhóm, tenant, quyền quản trị | Không hợp nhất như dữ liệu hồ sơ thông thường |
| Bí mật và yếu tố xác thực | Password hash, MFA secret, recovery code, passkey | Ngoài phạm vi đối soát hồ sơ; theo workflow bảo mật riêng |
| Cài đặt riêng tư và lựa chọn liên hệ | Mức công khai, tùy chọn nhận thông báo | Không tự mở rộng phạm vi công khai hoặc lựa chọn của người dùng |
| Dữ liệu do tổ chức quản lý | Chức danh, mã nhân viên, email doanh nghiệp | Theo nguồn quản lý và chính sách tổ chức |

Các danh sách trên chỉ là ví dụ. Mỗi sản phẩm cần một danh mục trường được phép merge rõ ràng. Trường chưa có quy tắc không nên tự động được thêm vào quá trình chuyển chỉ vì xuất hiện trong schema mới.

Một allowlist giúp ngăn lỗi mass assignment: chỉ các trường đã được phê duyệt mới được đưa vào kế hoạch đối soát. Không nhận một JSON tùy ý rồi ghi mọi key vào đối tượng hồ sơ đích.

## 4. Mô hình giá trị: không chỉ có null và chuỗi

Một trường hồ sơ cần phân biệt những trạng thái có ý nghĩa khác nhau:

| Trạng thái | Ý nghĩa | Ví dụ |
|---|---|---|
| `MISSING` | Chưa có giá trị trong nguồn dữ liệu này | Tài khoản mới chưa nhập phần giới thiệu |
| `VALUE` | Có giá trị được lưu hợp lệ | Ngôn ngữ giao diện là `vi` |
| `CLEARED` | Người có quyền đã chủ động xóa giá trị | Người dùng xóa phần giới thiệu cũ |
| Không đọc được | Không xác định được giá trị vì lỗi hoặc thiếu quyền | Dịch vụ hồ sơ nguồn không phản hồi |

“Không đọc được” không được biến thành `MISSING`. Nếu không, lỗi đọc nguồn có thể khiến hệ thống kết luận sai rằng không có xung đột hoặc ghi đè một giá trị hợp lệ bằng rỗng.

`CLEARED` cũng khác `MISSING`: một người có thể đã chủ động gỡ tên hiển thị cũ hoặc xóa thông tin cá nhân. Tự khôi phục giá trị cũ từ tài khoản nguồn có thể đảo ngược lựa chọn đó.

Ngoài giá trị, cần có metadata thích hợp:

```text
field_name
value_state
source_account_reference
source_system
field_version
updated_at
updated_by_reference
verification_reference, nếu có
management_policy_reference, nếu có
visibility_scope, nếu có
```

Không phải mọi trường đều cần toàn bộ metadata, nhưng giá trị cần được hiểu trong đúng ngữ cảnh. `verified=true` mà không biết xác minh giá trị nào, ở đâu và lúc nào là thông tin không đủ để chuyển mức tin cậy.

## 5. Các chiến lược đối soát theo từng trường

### Giữ giá trị đích

Phù hợp khi tài khoản đích được chọn làm hồ sơ tiếp tục sử dụng và người dùng đã cấu hình gần đây. Đây thường là lựa chọn ít gây thay đổi ngoài ý muốn, nhưng vẫn phải kiểm tra ràng buộc quản lý và yêu cầu của trường.

Không nên âm thầm bỏ dữ liệu nguồn. Bản xem trước có thể cho biết trường nào không được chuyển và tại sao, trong giới hạn dữ liệu mà người xem được phép truy cập.

### Điền từ nguồn khi đích chưa có

Có thể áp dụng cho trường hiển thị không nhạy cảm đã được cho phép. Ví dụ, đích chưa chọn múi giờ còn nguồn có một giá trị hợp lệ.

Quy tắc này chỉ áp dụng khi đích thực sự `MISSING`, không phải đã chủ động xóa, bị che do quyền hoặc tạm thời không đọc được. Cũng phải xác nhận nguồn đáp ứng chính sách dữ liệu hiện hành.

### Yêu cầu lựa chọn rõ ràng

Nếu cả hai bên có giá trị khác nhau, hiển thị các giá trị và cho người có thẩm quyền chọn. Bản lựa chọn cần gắn với phiên bản kế hoạch, không chỉ gửi chuỗi mới rời rạc.

Ví dụ, người dùng chọn tên từ nguồn nhưng giữ ngôn ngữ từ đích. Hệ thống lưu quyết định theo từng trường, thay vì một nút “ưu tiên nguồn cho tất cả” có thể kéo theo các thuộc tính nhạy cảm.

### Giữ nguồn quản lý có thẩm quyền

Với dữ liệu do tổ chức quản lý, lựa chọn của cá nhân có thể không có hiệu lực. Nếu chức danh hoặc mã nhân viên đến từ directory của tổ chức, việc merge không được biến giá trị tự nhập thành giá trị quản lý chính thức.

Nếu hai nguồn quản lý mâu thuẫn, có thể phải dừng trường đó hoặc dừng cả merge tùy mức ràng buộc. Không chọn ngẫu nhiên theo thời điểm cập nhật.

### Hợp nhất tập giá trị

Chỉ dùng khi trường thật sự có ngữ nghĩa tập hợp, chẳng hạn danh sách sở thích không nhạy cảm. Cần chuẩn hóa, loại trùng, kiểm tra giới hạn và nguồn hợp lệ.

Không áp dụng phép hợp cho danh sách quyền, nhóm truy cập, thiết bị tin cậy hoặc phương thức khôi phục. Hợp hai tập quyền có thể làm tài khoản đích có nhiều đặc quyền hơn bất kỳ tuyến merge nào cho phép.

### Không chuyển hoặc yêu cầu xác minh lại

Áp dụng với các trường chưa đáp ứng điều kiện chuyển. Một kênh liên hệ mới có thể được giữ dưới dạng chưa liên kết hoặc chờ xác minh theo quy trình riêng, thay vì biến thành kênh recovery ngay khi merge hồ sơ.

## 6. Vì sao “giá trị mới nhất thắng” thường không đủ?

Timestamp chỉ cho biết thời điểm ghi theo một nguồn, không chứng minh độ đúng hoặc quyền chỉnh sửa.

Ví dụ:

- Tên hiển thị mới nhất có thể do người tấn công sửa trong một phiên bị chiếm đoạt.
- Một bản đồng bộ directory chạy hôm nay có thể mang dữ liệu có hiệu lực từ nhiều tháng trước.
- Hai hệ thống dùng đồng hồ khác nhau hoặc cập nhật `updated_at` khi chỉ thay metadata.
- Việc chủ động xóa giá trị ở đích có thể bị dữ liệu cũ được ghi lại ở nguồn lấn át.

Do đó, last-write-wins chỉ phù hợp khi trường và nguồn dữ liệu có các giả định rõ ràng. Không dùng timestamp làm quy tắc chung cho email, tên đã chứng thực, trạng thái xác minh hoặc dữ liệu do tổ chức quản lý.

Tương tự, “giá trị đã xác minh thắng” không phải quy tắc phổ quát. Một giá trị có thể đã được xác minh cho tài khoản nguồn, mục đích và thời điểm nhất định nhưng không đủ điều kiện áp dụng cho đích. Cần xét phạm vi của chứng thực, không chỉ một cờ boolean.

## 7. Kênh liên hệ, chứng thực và quyền truy cập

Một trong những lỗi nghiêm trọng nhất là hợp nhất dữ liệu hiển thị đồng thời nâng mức tin cậy của tài khoản.

Ví dụ sai:

```text
Nguồn: email = old@example.invalid, emailVerified = true
Đích:  email = new@example.invalid, emailVerified = false

Sau merge: email = new@example.invalid, emailVerified = true
```

Cờ xác minh của địa chỉ cũ đã bị gắn sang địa chỉ mới. Đây là thay đổi ý nghĩa bảo mật, không phải giải quyết xung đột hồ sơ.

Một mô hình đúng cần giữ xác minh gắn với giá trị và ngữ cảnh:

```text
verification.subject_reference
verification.value_reference
verification.purpose
verification.method
verification.verified_at
verification.expires_at, nếu có
verification.issuer_reference
```

Chỉ chuyển hoặc tái sử dụng chứng thực nếu workflow riêng xác định được điều kiện hợp lệ. Nếu không, giữ trạng thái chưa xác minh hoặc yêu cầu thực hiện lại bước cần thiết.

Tên hiển thị giống nhau cũng không làm hai tài khoản trở thành cùng một danh tính pháp lý hay danh tính tổ chức. Tên đã được một nhà cung cấp chứng thực có thể phải giữ dưới dạng claim do nguồn đó quản lý, tách khỏi tên tự nhập.

Password hash, bí mật MFA, recovery code và khóa passkey không thuộc danh sách trường profile để tự sao chép. Việc giữ hoặc thay đổi phương thức đăng nhập sau merge cần quy trình riêng về ràng buộc chủ thể, phiên, token và thông báo bảo mật.

Vai trò quản trị, quyền thuê bao, tài sản hay dữ liệu giao dịch cũng không tự hợp nhất theo quy tắc hồ sơ. Chúng cần mô hình chuyển giao riêng nếu sản phẩm có hỗ trợ.

## 8. Tạo kế hoạch đối soát trước khi ghi

Một kế hoạch nên mô tả dữ liệu đầu vào và kết quả đề nghị theo từng trường:

```json
{
  "mergeCaseId": "mc_example_420",
  "planRevision": 3,
  "sourceProfileVersion": 18,
  "targetProfileVersion": 7,
  "policyVersion": "profile-merge-example-v4",
  "fields": [
    {
      "field": "displayName",
      "strategy": "USER_CHOICE",
      "resolution": "KEEP_TARGET"
    },
    {
      "field": "locale",
      "strategy": "FILL_MISSING_TARGET",
      "resolution": "COPY_SOURCE"
    },
    {
      "field": "email",
      "strategy": "SEPARATE_CONTACT_WORKFLOW",
      "resolution": "NOT_CHANGED"
    }
  ]
}
```

Ví dụ chỉ mô tả tham chiếu và quyết định. Hệ thống thực tế cần giữ snapshot hoặc tham chiếu tới các giá trị có phiên bản để biết chính xác dữ liệu được chọn; không dựa vào một profile luôn bị sửa tại chỗ.

Bản xem trước cho người dùng có thể hiển thị giá trị cũ, giá trị dự kiến và lý do. Chỉ đưa dữ liệu của cả hai bên lên giao diện sau khi quyền xem tương ứng đã được xác lập. Bản xem trước cũng không nên chứa token, giấy tờ hoặc các thuộc tính nội bộ.

Nếu còn xung đột bắt buộc chưa được giải quyết, không cho commit âm thầm bằng giá trị mặc định. Có thể tiếp tục các trường độc lập chỉ khi sản phẩm đã định nghĩa rõ merge một phần; không để tài khoản ở trạng thái nửa hợp nhất mà không ai biết.

## 9. Minh họa đối soát tên hiển thị bằng Java

Ví dụ sau chỉ xử lý một trường hiển thị, không dùng cho email, quyền hoặc chứng thực. Đầu vào phải được backend đọc từ đúng hai hồ sơ đã được cho phép, và lựa chọn của người dùng phải được ràng buộc với kế hoạch hiện hành.

```java
import java.util.Objects;

public final class DisplayNameReconciler {
    public enum Kind { MISSING, VALUE, CLEARED }
    public enum Pick { NONE, KEEP_TARGET, USE_SOURCE }
    public enum Resolution { KEEP_TARGET, COPY_SOURCE, NEEDS_CHOICE }

    public record FieldValue(Kind kind, String value) {
        public FieldValue {
            Objects.requireNonNull(kind);
            if (kind == Kind.VALUE) {
                if (value == null || value.isBlank()) {
                    throw new IllegalArgumentException("Missing display name");
                }
            } else if (value != null) {
                throw new IllegalArgumentException("Unexpected value");
            }
        }
    }

    public record Result(Resolution resolution, FieldValue selected) {}

    public Result reconcile(FieldValue target, FieldValue source, Pick pick) {
        Objects.requireNonNull(target);
        Objects.requireNonNull(source);
        Objects.requireNonNull(pick);

        if (pick == Pick.KEEP_TARGET) {
            return new Result(Resolution.KEEP_TARGET, target);
        }

        if (pick == Pick.USE_SOURCE) {
            if (source.kind() == Kind.MISSING) {
                throw new IllegalArgumentException("Source has no value to select");
            }
            return new Result(Resolution.COPY_SOURCE, source);
        }

        if (target.kind() == Kind.CLEARED || source.kind() == Kind.MISSING) {
            return new Result(Resolution.KEEP_TARGET, target);
        }

        if (target.kind() == Kind.MISSING && source.kind() == Kind.VALUE) {
            return new Result(Resolution.COPY_SOURCE, source);
        }

        if (target.equals(source)) {
            return new Result(Resolution.KEEP_TARGET, target);
        }

        return new Result(Resolution.NEEDS_CHOICE, null);
    }
}
```

Trong quy tắc minh họa, giá trị đã chủ động xóa ở đích không bị tự khôi phục từ nguồn. Nếu người dùng chủ động chọn nguồn trong một kế hoạch hợp lệ, đó là quyết định rõ ràng khác với tự động điền thiếu.

`COPY_SOURCE` với nguồn `CLEARED` biểu thị người dùng đã chọn trạng thái xóa, không phải sao chép chuỗi rỗng. Giao diện phải diễn đạt rõ hậu quả này trước khi xác nhận.

`NEEDS_CHOICE` không mang giá trị có thể ghi. Coordinator phải dừng việc commit trường chưa giải quyết, thay vì chuyển `null` thành lệnh xóa dữ liệu đích.

Đoạn mã không biểu diễn lỗi đọc nguồn: lỗi đó phải được xử lý trước khi tạo `FieldValue`. Nó cũng chưa kiểm tra độ dài, ký tự, chính sách tổ chức, phiên bản hay giao dịch. Các kiểm tra ấy thuộc pipeline theo trường và bước thực thi kế hoạch.

## 10. Chuẩn hóa và kiểm tra dữ liệu

Chuẩn hóa giúp đối chiếu nhất quán nhưng không được làm mất ý nghĩa hoặc biến dữ liệu thành bằng chứng danh tính.

Ví dụ:

- Ngôn ngữ và múi giờ được kiểm tra bằng tập giá trị sản phẩm hỗ trợ.
- Tên hiển thị cần giới hạn độ dài và xử lý ký tự điều khiển theo chính sách.
- Văn bản giới thiệu được hiển thị bằng cơ chế escape hoặc lọc nội dung phù hợp.
- Ảnh đại diện được chuyển qua pipeline tệp được phép, không tùy ý tải URL do người dùng cung cấp từ backend.
- Danh sách sở thích được kiểm tra phần tử, loại trùng và giới hạn số lượng.

Không áp dụng một phép lowercase hoặc bỏ ký tự chung cho mọi trường. Ví dụ, biến đổi tên có thể làm thay đổi cách người dùng tự giới thiệu; quy tắc so sánh địa chỉ liên hệ cũng không nên tự phát minh bằng xử lý chuỗi đơn giản.

Chuỗi Unicode nhìn giống nhau không chứng minh hai danh tính giống nhau. Nếu sản phẩm chuẩn hóa Unicode cho một trường, phải lưu và so sánh theo chính sách nhất quán; không lấy sự giống nhau sau chuẩn hóa làm điều kiện đủ cho merge.

Đường dẫn ảnh, nội dung HTML và liên kết trong phần giới thiệu là dữ liệu không tin cậy. Dữ liệu đã tồn tại ở tài khoản nguồn không tự trở nên an toàn chỉ vì được chuyển nội bộ sang đích.

## 11. Riêng tư và lựa chọn liên hệ

Hợp nhất giá trị không nên âm thầm mở rộng nơi dữ liệu xuất hiện.

Ví dụ: nguồn có số điện thoại chỉ dùng nội bộ, còn đích có hồ sơ công khai. Nếu sản phẩm cho phép chuyển số điện thoại, không tự gắn mức hiển thị công khai của đích vào số vừa chuyển. Quy tắc visibility cần được xác định theo trường và ngữ cảnh.

Một mặc định thận trọng cho dữ liệu được phép chuyển là không mở rộng phạm vi công khai nếu chưa có quyết định phù hợp. Tuy nhiên, không nên mô tả mọi phạm vi thành một thứ tự đơn giản “private nhỏ hơn public”: dữ liệu dùng trong một tổ chức và dữ liệu dùng trong một nhóm khác có thể là hai phạm vi không thể so sánh trực tiếp.

Lựa chọn nhận email tiếp thị, thông báo sản phẩm và cảnh báo bảo mật cũng không phải một cờ duy nhất. Không lấy sự đồng ý ở nguồn để tự bật mọi loại liên hệ ở đích. Cần giữ mục đích, kênh, bối cảnh và phiên bản lựa chọn theo mô hình sản phẩm.

Thông báo bảo mật cần thiết cho merge thuộc chính sách riêng, không bị vô tình tắt chỉ vì một tùy chọn quảng cáo được giữ từ nguồn. Ngược lại, cần chống gửi lặp và chỉ gửi qua kênh đã được hệ thống cho phép.

## 12. Ghi kết quả nhất quán và chống thay đổi đồng thời

Giữa lúc người dùng xem trước và lúc xác nhận, hồ sơ có thể thay đổi. Nếu commit không kiểm tra phiên bản, hệ thống có thể ghi đè một chỉnh sửa mới mà người dùng chưa từng xem.

Luồng thực thi có thể là:

1. Đọc snapshot hoặc phiên bản hồ sơ nguồn và đích.
2. Tạo kế hoạch với chính sách, kết quả từng trường và xung đột còn lại.
3. Nhận lựa chọn đã được phân quyền, gắn với revision của kế hoạch.
4. Trước khi ghi, kiểm tra lại quyền, trạng thái merge case và hiệu lực xác minh.
5. Khóa hoặc kiểm tra phiên bản các dữ liệu có liên quan.
6. Áp dụng các trường được phép, lưu provenance và audit trong giao dịch phù hợp.
7. Đánh dấu kết quả kế hoạch cùng sự kiện đồng bộ phát sinh.
8. Commit rồi mới cập nhật các hệ thống phụ hoặc gửi thông báo.

Một câu cập nhật có điều kiện cho hồ sơ đích có thể là:

```sql
UPDATE user_profile
SET display_name = :selected_display_name,
    locale = :selected_locale,
    profile_version = profile_version + 1
WHERE tenant_id = :tenant_id
  AND account_id = :target_account_id
  AND profile_version = :expected_target_version;
```

SQL chỉ minh họa bước ghi các giá trị đã được giải quyết. Nó không tự kiểm tra quyền với nguồn, trạng thái xóa, chính sách từng trường hoặc tính hợp lệ của toàn bộ merge.

Nếu nguồn cũng có thể thay đổi, phải bảo vệ phiên bản nguồn trong cùng chiến lược nhất quán. Chỉ kiểm tra phiên bản đích là chưa đủ khi kế hoạch đang sao chép dữ liệu nguồn. Cách thực hiện có thể là khóa các bản ghi cần thiết hoặc dùng điều kiện phiên bản được bảo đảm bởi ranh giới giao dịch thích hợp.

Khi phát hiện xung đột, đọc lại và tạo bản xem trước mới. Không tự áp lựa chọn cũ cho một giá trị mới chỉ vì tên trường giống nhau.

## 13. Idempotency, đồng bộ và hoàn tác

Người dùng có thể bấm xác nhận nhiều lần hoặc gửi lại sau timeout. Một kế hoạch đã áp dụng không nên bị chạy lần nữa làm tăng phiên bản liên tục, gửi nhiều thông báo hay khôi phục dữ liệu cũ.

Khóa idempotency cần gắn với merge case, revision kế hoạch, người có quyền và nhận diện lựa chọn. Cùng khóa với payload khác phải được phát hiện. Khi khóa hết thời gian lưu, trạng thái của kế hoạch vẫn cần ngăn áp dụng lặp.

Nếu dữ liệu còn được đồng bộ tới search index, cache hoặc dịch vụ hồ sơ khác, sự kiện nên mang revision và định danh thao tác. Consumer cần chống trùng và không áp sự kiện cũ lên trạng thái mới hơn. Hồ sơ được bảo vệ riêng tư không nên tạm xuất hiện công khai vì index chưa cập nhật đúng thứ tự.

Hoàn tác cũng cần giới hạn rõ. Có thể khôi phục một số trường hồ sơ từ snapshot nếu còn đủ điều kiện, nhưng không được ghi đè các chỉnh sửa hợp lệ đã xảy ra sau merge. Có thể dùng điều kiện “chỉ hoàn tác nếu giá trị và phiên bản vẫn thuộc thao tác này”, còn xung đột thì chuyển xử lý riêng.

Không hứa rằng toàn bộ account merge luôn đảo ngược được chỉ vì có thể hoàn tác tên hiển thị. Dữ liệu nghiệp vụ, liên kết định danh và quyền truy cập có thể có cơ chế khác. Snapshot chứa dữ liệu cá nhân cũng cần kiểm soát quyền đọc và thời hạn lưu phù hợp, không tạo thêm một bản sao không được quản lý.

## 14. Audit và khả năng giải thích

Một kết quả đối soát tốt cho phép trả lời: trường nào thay đổi, từ đâu, theo quy tắc nào và ai đã chọn.

Audit có thể ghi:

```text
merge_case_id / reconciliation_plan_revision
source_account_reference / target_account_reference
source_profile_version / target_profile_version
field_name / resolution_strategy
selected_origin_reference
user_choice_reference, nếu có
policy_version
actor_reference
applied_at / operation_id
resulting_profile_version
```

Không cần đưa toàn bộ giá trị hồ sơ vào log ứng dụng. Có thể giữ tham chiếu tới snapshot được bảo vệ và ghi thông tin thay đổi tối thiểu cho mục đích vận hành. Địa chỉ liên hệ, ghi chú cá nhân và dữ liệu xác minh không nên bị sao chép tới nhiều hệ thống log.

Với người dùng, giải thích có thể ngắn gọn: “Giữ tên hiển thị của tài khoản đích theo lựa chọn của bạn”, “Lấy múi giờ từ tài khoản nguồn vì đích chưa đặt”, “Email được giữ nguyên và xử lý theo bước xác minh riêng”. Không cần lộ mã nội bộ hoặc dữ liệu của bên họ không có quyền xem.

## 15. Tình huống xuyên suốt

Sau khi hoàn thành tuyến recovery cần thiết, Linh được phép merge tài khoản cũ A vào tài khoản mới B. Chính sách xác định B là tài khoản tồn tại sau merge và không cho chuyển quyền tổ chức trong bước hồ sơ.

| Trường | Nguồn A | Đích B | Kết quả đề nghị |
|---|---|---|---|
| Tên hiển thị | Linh Nguyễn | Linh | Yêu cầu Linh chọn |
| Ngôn ngữ | Tiếng Việt | Tiếng Anh | Giữ B hoặc chọn rõ ràng |
| Múi giờ | Asia/Ho_Chi_Minh | Chưa đặt | Điền từ A nếu hợp lệ |
| Phần giới thiệu | Có nội dung cũ | Đã chủ động xóa | Giữ trạng thái xóa của B |
| Email | Địa chỉ cũ đã xác minh | Địa chỉ mới chưa xác minh | Không chuyển cờ xác minh |
| Vai trò quản trị | Có trong tổ chức cũ | Không có | Ngoài phạm vi đối soát hồ sơ |

Linh chọn tên từ A, giữ ngôn ngữ ở B và đồng ý dùng múi giờ nguồn. Hệ thống ghi các lựa chọn vào plan revision 3, gắn với hai phiên bản hồ sơ đã xem.

Trước lúc commit, Linh đổi tên ở B trong một tab khác. Phiên bản B thay đổi nên lần xác nhận merge bị phát hiện xung đột. Hệ thống tạo bản xem trước mới, thay vì dùng lựa chọn cũ để ghi đè tên vừa sửa.

Sau khi xác nhận lại trên revision mới, hệ thống áp dụng các trường được phép, giữ phần giới thiệu đã xóa, giữ nguyên trạng thái email và không sao chép vai trò quản trị. Sự kiện đồng bộ chỉ được phát sau khi giao dịch thành công, có định danh để chống xử lý lặp.

Linh vẫn cần hoàn thành workflow liên hệ nếu muốn sử dụng email khác làm kênh recovery. Việc giữ tên và múi giờ không làm giảm điều kiện xác minh ở bước đó.

## 16. Những lỗi thiết kế thường gặp

- **Sao chép toàn bộ đối tượng user:** kéo theo quyền, tenant hoặc bí mật xác thực ngoài phạm vi.
- **Luôn chọn giá trị mới nhất:** bỏ qua nguồn quản lý, trạng thái xóa và nguy cơ chỉnh sửa trong phiên bị chiếm đoạt.
- **Chuyển cờ xác minh mà không gắn giá trị:** nâng mức tin cậy cho email hoặc số điện thoại chưa được chứng minh.
- **Coi lỗi đọc là không có dữ liệu:** tạo kết quả sai hoặc xóa dữ liệu ngoài ý muốn.
- **Tự phục hồi trường đã xóa:** đảo ngược lựa chọn riêng tư trước đó.
- **Hợp tất cả các tập giá trị:** cộng dồn quyền hoặc quan hệ tổ chức không được phép.
- **Hiển thị cả hai hồ sơ trước khi xác minh quyền:** làm lộ dữ liệu qua chức năng xem trước.
- **Không ràng buộc lựa chọn với phiên bản:** áp lựa chọn cũ lên dữ liệu đã đổi.
- **Cho consumer áp sự kiện cũ:** ghi đè kết quả merge bằng trạng thái trước đó.
- **Hứa hoàn tác toàn bộ từ snapshot hồ sơ:** bỏ qua các phần merge có tính chất và ràng buộc khác.

Profile data reconciliation cần tạo ra một hồ sơ đích hợp lệ và giải thích được, đồng thời giữ nguyên ý nghĩa bảo mật của từng loại dữ liệu. Quy tắc theo trường, provenance, lựa chọn có phiên bản và thực thi nhất quán giúp việc hợp nhất sau recovery giữ lại thông tin hữu ích mà không tự trao thêm quyền truy cập hoặc độ tin cậy.
