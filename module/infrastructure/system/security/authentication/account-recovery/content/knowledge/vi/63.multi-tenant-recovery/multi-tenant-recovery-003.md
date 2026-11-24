# Tenant contact configuration — Cấu hình liên hệ theo tenant cho khôi phục tài khoản

## 1. Liên hệ đúng tenant là một phần của ranh giới bảo mật

Trong hệ thống nhiều tenant, người dùng có thể thuộc nhiều tổ chức và mỗi tổ chức có bộ phận hỗ trợ, đầu mối an ninh hoặc nhà cung cấp danh tính riêng. Khi họ mất mật khẩu, MFA, passkey hay thiết bị xác thực, hệ thống cần định tuyến yêu cầu và thông báo đến đúng nơi có trách nhiệm.

Tenant contact configuration là cấu hình mô tả các đầu mối liên hệ của một tenant, mục đích sử dụng, trạng thái xác minh và điều kiện áp dụng. Trong `SECURITY_AUTHENTICATION_ACCOUNT_RECOVERY`, cấu hình này hỗ trợ tiếp nhận yêu cầu, gửi cảnh báo và chuyển xử lý khi người dùng không thể tự khôi phục.

Một cấu hình sai có thể làm lộ thông tin hồ sơ sang tenant khác hoặc khiến người dùng được dẫn đến một kênh do kẻ tấn công kiểm soát. Rủi ro càng lớn nếu sản phẩm coi người kiểm soát hộp thư liên hệ là người được phép đặt lại mọi credential của tenant.

Vì vậy, cần giữ một ranh giới rõ ràng:

> Được nhận thông báo hoặc được hiển thị là đầu mối hỗ trợ không tự có nghĩa được phê duyệt, thực thi khôi phục hoặc sở hữu danh tính người dùng.

Cấu hình liên hệ giải quyết bài toán tìm đúng người hoặc hệ thống để liên lạc. Quyền thay đổi tài khoản vẫn phải được quyết định bởi chính sách xác thực, phân quyền, bằng chứng và phạm vi quản lý riêng.

## 2. Phân biệt các loại liên hệ

Một trường tổng quát như `recoveryEmail` dễ bị sử dụng cho nhiều mục đích trái nhau. Nên mô tả rõ mỗi loại liên hệ được dùng làm gì.

| Loại liên hệ | Mục đích | Không được tự suy ra |
|---|---|---|
| Liên hệ hỗ trợ công khai | Hướng dẫn người dùng tìm nơi tiếp nhận hoặc trang hỗ trợ | Có quyền đọc mọi hồ sơ hoặc đặt lại tài khoản |
| Liên hệ nhận cảnh báo bảo mật | Nhận thông tin phù hợp về sự kiện và rủi ro thuộc tenant | Được nhận token khôi phục của người dùng |
| Liên hệ chuyển cấp | Tiếp nhận trường hợp cần xử lý khi tuyến thông thường không hoạt động | Được bỏ qua bằng chứng hoặc tự phê duyệt |
| Tham chiếu người hoặc nhóm phê duyệt | Tìm chủ thể có thể được đánh giá quyền phê duyệt trong cổng quản trị | Một địa chỉ email tự tạo ra vai trò phê duyệt |
| Đầu mối nhà cung cấp danh tính | Hướng người dùng hoặc nhóm hỗ trợ đến hệ thống có thẩm quyền quản lý credential | Ứng dụng cục bộ được quyền sửa MFA ở hệ thống bên ngoài |
| Kênh khôi phục cá nhân | Phương tiện đã được cho phép để một chủ thể lấy lại quyền truy cập | Có thể thay bằng hộp thư hỗ trợ chung của tenant |

Một địa chỉ có thể được dùng cho nhiều mục đích nếu chính sách cho phép, nhưng quyền và nội dung gửi vẫn phải tách riêng. Ví dụ, cùng một nhóm nhận cả cảnh báo và yêu cầu chuyển cấp không có nghĩa mọi thành viên nhóm đều được thực thi khôi phục.

Không nên lấy một liên hệ công khai rồi tự thêm nó vào danh sách kênh khôi phục cá nhân của mọi người dùng. Cách đó biến việc quản lý hộp thư hỗ trợ thành một đường chiếm tài khoản hàng loạt.

## 3. Xác định thẩm quyền trong mô hình nhiều tenant

### 3.1. Tài khoản và tư cách thành viên có thể khác phạm vi

Một danh tính toàn cục có thể là thành viên của tenant A và tenant B. Quản trị viên A thường có quyền xử lý những việc được giao trong A, không tự có quyền thay credential toàn cục để ảnh hưởng đến cả B.

Cấu hình liên hệ phải đi cùng mô hình này. Liên hệ A có thể nhận yêu cầu về tư cách thành viên của A, trong khi yêu cầu thay mật khẩu toàn cục cần chuyển đến bên có thẩm quyền đối với danh tính toàn cục.

Nếu credential do nhà cung cấp danh tính của tổ chức quản lý, luồng khôi phục cần hướng về đúng hệ thống đó. Không tạo mật khẩu cục bộ hoặc kênh dự phòng mới chỉ để một đầu mối hỗ trợ có thể xử lý nhanh hơn.

### 3.2. Không lấy tenant do bên gọi khai báo làm thẩm quyền

URL, hostname hoặc lựa chọn tenant trên giao diện có thể giúp định tuyến ban đầu. Máy chủ vẫn phải đối chiếu chúng với cấu hình được phép và ngữ cảnh yêu cầu trước khi đọc, sửa hoặc sử dụng dữ liệu riêng của tenant.

Đối với thao tác quản trị, tenant hiệu lực phải được xác định từ ngữ cảnh có thẩm quyền và quyền hiện tại của người vận hành. Một trường `tenantId` trong JSON không cho người gọi quyền đổi liên hệ của tenant đó.

Đối với luồng chưa xác thực, chỉ hiển thị thông tin hỗ trợ được phép công khai trong ngữ cảnh đã xác định. Không dùng phản hồi liên hệ khác nhau để tiết lộ rằng một email cụ thể có tồn tại hoặc thuộc một tenant nào.

### 3.3. Tuyến dự phòng cũng phải có phạm vi

Nếu liên hệ A không dùng được, không lấy liên hệ B vì “cùng một người quản trị” hoặc “cùng domain”. Tuyến dự phòng phải được thiết lập và cho phép trước, chẳng hạn một đầu mối vận hành nền tảng có phạm vi hỗ trợ đã xác định.

Ngay cả tuyến nền tảng cũng cần giới hạn thông tin được xem và quyền được thực hiện. Vai trò tiếp nhận chuyển cấp không phải quyền tự quyết định danh tính chủ tài khoản.

## 4. Mô hình cấu hình có phiên bản

Một cấu hình có thể tách thông tin hiển thị khỏi các điểm nhận thông báo đã được kiểm soát. Ví dụ:

```json
{
  "tenantId": "tenant-A",
  "revision": 12,
  "support": {
    "displayName": "Hỗ trợ tổ chức A",
    "publicUrl": "https://support.tenant-a.example/recovery"
  },
  "contacts": [
    {
      "contactId": "contact-71",
      "purpose": "SECURITY_NOTIFICATION",
      "channel": "EMAIL",
      "destination": "security@tenant-a.example",
      "verificationState": "VERIFIED",
      "lifecycleState": "ACTIVE"
    },
    {
      "contactId": "contact-72",
      "purpose": "RECOVERY_ESCALATION",
      "channel": "EMAIL",
      "destination": "recovery-team@tenant-a.example",
      "verificationState": "VERIFIED",
      "lifecycleState": "ACTIVE"
    }
  ]
}
```

Đây là ví dụ dữ liệu lưu phía máy chủ, không phải một payload mà phía trình duyệt được phép tự đặt các cờ `VERIFIED` hoặc `ACTIVE`.

Trong triển khai, bản ghi còn có thể cần thời điểm xác minh, phiên bản điểm nhận, người thay đổi, người phê duyệt nếu áp dụng, hiệu lực, lịch sử và các tham chiếu quyền. Những thuộc tính này phải do các quy trình có thẩm quyền cập nhật.

Phân biệt `verificationState` và `lifecycleState` giúp tránh nhầm lẫn: địa chỉ đã từng được xác minh có thể đã bị ngừng sử dụng; địa chỉ mới được đề xuất có thể đã có bản ghi nhưng chưa được phép nhận thông tin nhạy cảm.

Không suy ra quyền từ chuỗi domain trong `destination`. Một hộp thư cùng domain có thể là nhóm chia sẻ hoặc tài khoản không còn phù hợp. Ngược lại, một nhà cung cấp hỗ trợ bên ngoài có thể dùng domain khác nhưng vẫn được tổ chức ủy quyền rõ ràng theo quy trình.

## 5. Đăng ký liên hệ và xác minh điểm nhận

Cần tách hai câu hỏi: ai có quyền đề xuất cấu hình cho tenant, và ai kiểm soát điểm nhận được đề xuất. Xác minh hộp thư chỉ trả lời câu hỏi thứ hai ở mức mà cơ chế đó hỗ trợ.

Một luồng đăng ký có thể gồm:

1. Người vận hành được xác thực và có quyền cấu hình liên hệ trong đúng tenant.
2. Máy chủ tạo phiên bản đề xuất với mục đích và điểm nhận cụ thể.
3. Hệ thống gửi một thử thách xác minh tới điểm nhận qua kênh phù hợp.
4. Kết quả được đối chiếu với tenant, liên hệ, phiên bản, mục đích, thời hạn và trạng thái chưa dùng.
5. Chính sách đánh giá điều kiện kích hoạt, kể cả phê duyệt độc lập hoặc thời gian chờ nếu cần.
6. Hệ thống kích hoạt đúng phiên bản và lưu dấu vết.

Thử thách cần có thời hạn, giới hạn thử và cơ chế dùng một lần thích hợp. Nếu điểm nhận thay đổi trong lúc chờ, kết quả xác minh cũ không nên kích hoạt điểm nhận mới.

Link xác minh địa chỉ không nên đồng thời tạo một phiên quản trị hoặc gán vai trò khôi phục. Người được chuyển tiếp email có thể mở link; việc đó không chứng minh họ có thẩm quyền quản lý tenant.

Với một hộp thư dùng chung, tổ chức cần quản lý ai truy cập được và cách thay đổi thành viên. Các quyết định phê duyệt nhạy cảm nên được gắn với chủ thể xác thực có thể truy vết trong hệ thống quản trị, thay vì chỉ ghi “đã nhận email từ nhóm hỗ trợ”.

## 6. Thay đổi liên hệ là một thay đổi nhạy cảm

Kẻ tấn công chiếm một phiên quản trị có thể đổi đầu mối để nhận thông tin về các lần khôi phục tiếp theo hoặc dẫn người dùng tới một trang giả mạo. Vì vậy, thay đổi liên hệ cần được đánh giá theo tác động, không chỉ như sửa văn bản giao diện.

Chính sách có thể yêu cầu xác thực lại, giới hạn vai trò, phê duyệt độc lập hoặc thời gian chờ cho những loại thay đổi có rủi ro cao. Các yêu cầu cụ thể phụ thuộc mô hình vận hành và không nên bị thay thế chỉ bằng một mã gửi đến địa chỉ mới.

Một phiên bản mới nên đi qua trạng thái đề xuất, xác minh và kích hoạt. Không ghi đè điểm nhận đang hoạt động rồi mới tìm cách xác minh sau, trong khi hệ thống đã bắt đầu gửi hồ sơ nhạy cảm tới địa chỉ đó.

Thông báo về thay đổi có thể cần gửi đến những đầu mối đã được thiết lập theo chính sách. Tuy nhiên, không gửi mù quáng mọi chi tiết tới kênh cũ nếu có căn cứ kênh đó đã bị chiếm. Quy trình cần quyết định nội dung, người nhận và mức khẩn phù hợp với tình huống.

Nếu thay đổi bị từ chối hoặc hết hạn, giữ được lịch sử đề xuất nhưng không dùng điểm nhận chưa được kích hoạt. Việc gửi lại email xác minh không nên âm thầm cấp quyền mới hoặc làm sống lại một đề xuất đã bị thu hồi.

## 7. Nội dung được gửi phải phù hợp với mục đích

Một liên hệ hợp lệ không có nghĩa được nhận toàn bộ dữ liệu của mọi hồ sơ. Cần có chính sách về nội dung cho từng loại thông báo.

| Mục đích | Nội dung có thể phù hợp | Nội dung không nên gửi chỉ vì có địa chỉ liên hệ |
|---|---|---|
| Hướng dẫn hỗ trợ công khai | Cách liên lạc, giờ phục vụ, đường dẫn hỗ trợ đã được kiểm soát | Sự tồn tại của tài khoản hoặc chi tiết hồ sơ riêng |
| Cảnh báo bảo mật | Loại sự kiện, mức ưu tiên, định danh tham chiếu và đường dẫn cổng được bảo vệ | Token đặt lại mật khẩu, mã khôi phục, seed MFA |
| Chuyển cấp | Mã hồ sơ và thông tin tối thiểu để đơn vị có thẩm quyền tiếp nhận | Toàn bộ giấy tờ định danh hoặc bằng chứng nhạy cảm qua email thông thường |
| Thông báo cho người có thể phê duyệt | Yêu cầu đăng nhập vào cổng để xem nhiệm vụ được phép | Quyền phê duyệt vô điều kiện chỉ bằng việc sở hữu link |

Đường dẫn tới cổng quản trị không thay thế kiểm tra quyền khi mở hồ sơ. Nếu người nhận mất vai trò sau lúc gửi, họ không nên tiếp tục xem hay phê duyệt chỉ vì email cũ vẫn còn.

Các mẫu thông báo cần tránh lộ thêm tenant hoặc tài khoản ngoài phạm vi. Khi một danh tính tham gia nhiều tổ chức, thông tin dành cho A không nên liệt kê tư cách thành viên của họ ở B nếu không có căn cứ cho phép.

## 8. Định tuyến tại thời điểm sử dụng cấu hình

Một yêu cầu có thể được tạo trước lúc liên hệ thay đổi và chỉ được xử lý sau đó. Hệ thống phải quyết định sẽ dùng phiên bản nào và kiểm tra điều kiện nào trước khi gửi.

Không có một quy tắc “luôn dùng cũ” hoặc “luôn dùng mới” phù hợp với mọi loại thông báo. Thông báo về chính thay đổi liên hệ có thể cần tham chiếu những điểm nhận khác với một cảnh báo phát sinh sau khi phiên bản mới đã có hiệu lực.

Tuy vậy, các bất biến cần giữ là:

- Tenant của sự kiện, hồ sơ và cấu hình được chọn phải khớp theo thẩm quyền.
- Mục đích của liên hệ phải phù hợp với loại thông báo.
- Điểm nhận phải có trạng thái được phép sử dụng theo chính sách tại bước gửi.
- Không chuyển sang địa chỉ chưa xác minh chỉ vì cấu hình mới vừa được đề xuất.
- Không gửi tới điểm nhận đã bị cấm sử dụng mà chỉ dựa vào một snapshot cũ trong hàng đợi.
- Quyết định chọn người nhận phải có đủ dấu vết để đối chiếu.

Một luồng chọn liên hệ có thể được mô tả như sau:

```text
Đọc sự kiện từ nguồn nội bộ có thẩm quyền
  → xác định tenant và loại thông báo
  → tải hồ sơ trong đúng tenant nếu cần
  → áp dụng quy tắc chọn phiên bản cấu hình
  → chọn liên hệ đúng mục đích và trạng thái cho phép
  → kiểm tra lại giới hạn tiết lộ thông tin
  → tạo công việc gửi có định danh chống xử lý lặp
```

Không cho phép payload sự kiện từ một nguồn chưa được tin cậy chỉ định tùy ý địa chỉ nhận. Nếu có tích hợp bên ngoài, quyền tạo sự kiện và dữ liệu được phép cung cấp phải được kiểm tra trước khi vào luồng này.

Khi cache cấu hình, khóa cache cần bao gồm tenant và các chiều ảnh hưởng đến kết quả, chẳng hạn mục đích và phiên bản. Một cache chỉ dùng khóa `recovery-contact` có thể trả liên hệ của tenant trước đó cho tenant khác.

Thời hạn cache không thay thế cơ chế ngừng sử dụng một điểm nhận nguy hiểm. Thiết kế cần có cách làm mới hoặc kiểm tra trạng thái phù hợp khi liên hệ bị thu hồi khẩn cấp.

## 9. Ví dụ mô hình khóa tra cứu trong Java

Ví dụ dưới đây minh họa cách thể hiện phạm vi trong khóa tra cứu. Nó không triển khai xác thực người gọi hoặc quyết định nội dung thông báo.

```java
enum ContactPurpose {
    SECURITY_NOTIFICATION,
    RECOVERY_ESCALATION
}

record ContactLookupKey(
        String tenantId,
        ContactPurpose purpose,
        long configurationRevision) {
}

record DeliveryReference(
        String eventId,
        String tenantId,
        String contactId,
        long contactRevision,
        ContactPurpose purpose) {
}
```

`tenantId` trong những đối tượng này phải đến từ ngữ cảnh được máy chủ xác lập, không phải giá trị mà trình duyệt tự chọn để vượt phạm vi. Lớp lưu trữ cũng phải truy vấn đúng tenant khi tải liên hệ, thay vì chỉ lọc dữ liệu sau khi đã trả cả danh sách nhiều tenant cho bên gọi.

`DeliveryReference` giúp lưu lại liên hệ nào và phiên bản nào đã được chọn mà không cần sao chép toàn bộ nội dung nhạy cảm vào log. Trước khi gửi lại một công việc thất bại, hệ thống cần áp dụng lại quy tắc về hiệu lực điểm nhận; định danh công việc không phải giấy phép gửi đến một địa chỉ đã bị thu hồi.

Nếu có nhiều liên hệ cùng mục đích, chính sách cần quy định gửi đến tất cả, dùng thứ tự ưu tiên hay chuyển cấp sau lỗi. Không chọn phần tử đầu tiên của một truy vấn không có quy tắc chỉ vì mã nguồn dễ viết hơn.

## 10. Bảo vệ địa chỉ, URL và tích hợp thông báo

### 10.1. Địa chỉ email và nội dung hiển thị

Địa chỉ cần được kiểm tra cú pháp và xử lý bằng cơ chế gửi thư phù hợp, không ghép thẳng dữ liệu chưa kiểm tra vào header hoặc cấu trúc lệnh. Tên hiển thị và văn bản hỗ trợ cũng cần được hiển thị an toàn, tránh diễn giải thành mã hoặc nội dung ngoài dự kiến.

Chuẩn hóa để tra cứu phải có quy tắc rõ ràng và không tự coi mọi địa chỉ trông giống nhau là cùng một hộp thư. Việc sửa hoặc rút gọn một điểm nhận có thể làm thay đổi ý nghĩa của nó.

### 10.2. Đường dẫn hỗ trợ

Một URL được cấu hình sai có thể trở thành đường dẫn lừa người dùng trong thời điểm họ đang lo mất tài khoản. Cần giới hạn giao thức và các thuộc tính được phép, quản lý thẩm quyền thay đổi, đồng thời có quy trình kiểm tra điểm đến phù hợp.

Link chứa trong thông báo nên được dựng từ cấu hình máy chủ đã được cho phép. Không lấy trực tiếp host hoặc URL do yêu cầu chưa được tin cậy cung cấp để tạo một link khôi phục có vẻ chính thức.

Nếu cho tenant dùng trang hỗ trợ bên ngoài, cần phân biệt việc xác minh quyền cấu hình với việc trang đó có quyền xử lý credential. Không yêu cầu người dùng nhập mật khẩu hiện tại, seed MFA hoặc mã khôi phục vào một trang chỉ được đăng ký làm đầu mối hỗ trợ.

### 10.3. Webhook hoặc điểm nhận tự động

Nếu sản phẩm hỗ trợ webhook, đó là một kênh riêng với chính sách riêng, không chỉ là một URL thay cho email. Cần kiểm soát đích mà máy chủ được phép kết nối, chuyển hướng và mạng nội bộ để tránh biến cấu hình liên hệ thành khả năng gọi tùy ý từ hạ tầng.

Cơ chế xác thực thông báo, quản lý bí mật và xử lý lặp cũng phải được thiết kế tương ứng. Không lưu bí mật ký webhook vào các trường hiển thị công khai hoặc ghi nguyên giá trị vào log hỗ trợ.

Việc tự động truy cập một URL để kiểm tra cấu hình cũng phải chịu các giới hạn kết nối đó. Không cần phát sinh lời gọi có quyền rộng chỉ vì người quản trị vừa bấm lưu địa chỉ.

## 11. Xử lý lỗi gửi và giữ đúng mức bảo đảm

Trạng thái gửi cần phân biệt đã tạo công việc, nhà cung cấp đã nhận, báo lỗi, hoặc chưa rõ kết quả. Nhà cung cấp chấp nhận email không chứng minh người có thẩm quyền đã đọc, đồng ý hay thực hiện hành động.

Nếu gửi thất bại, cần thử lại theo chính sách với giới hạn phù hợp, ghi nhận kết quả và chuyển cấp khi cần. Không thay địa chỉ bằng một giá trị từ yêu cầu hiện tại để làm cho thông báo gửi được.

Các trạng thái và cách xử lý có thể gồm:

| Tình huống | Cách xử lý phù hợp |
|---|---|
| Lỗi tạm thời của nhà cung cấp | Thử lại có kiểm soát, giữ định danh sự kiện và phạm vi |
| Điểm nhận không còn tồn tại | Đánh dấu cần quản trị viên có thẩm quyền cập nhật, dùng tuyến dự phòng đã được phép nếu có |
| Điểm nhận bị thu hồi vì nghi xâm nhập | Ngừng sử dụng theo chính sách, không gửi lại mù quáng các công việc cũ |
| Cấu hình chưa có liên hệ hợp lệ cho mục đích bắt buộc | Ghi trạng thái thiếu cấu hình và áp dụng giới hạn hoặc chuyển cấp tương ứng |
| Chưa biết thông báo đã gửi hay chưa | Đối chiếu bằng định danh công việc, tránh khẳng định đã được người nhận xử lý |

Việc thiếu một liên hệ không nên tạo ra đường bỏ qua phê duyệt. Nếu quy trình cần một người có thẩm quyền mà hiện không tìm được, phải chuyển xử lý theo quy trình đã thiết lập thay vì cho phép tự duyệt.

Giờ phục vụ hoặc múi giờ có thể giúp định tuyến hỗ trợ. Chúng không tự thay đổi hạn token, hạn phê duyệt hoặc cho phép trì hoãn cảnh báo trái chính sách của sự kiện.

## 12. Khi tenant mất toàn bộ quản trị viên khả dụng

Một tình huống đặc biệt là mọi quản trị viên đều mất phương tiện xác thực hoặc tài khoản cuối cùng có quyền cấu hình không còn sử dụng được. Không thể giải quyết an toàn bằng cách gửi một mã tới bất kỳ email nào được người yêu cầu khai báo.

Đầu mối chuyển cấp được thiết lập trước có thể giúp bắt đầu quy trình. Tuy nhiên, việc người đó đọc được email vẫn không tự chứng minh họ sở hữu tổ chức hoặc được phép chọn quản trị viên thay thế.

Quy trình phục hồi thẩm quyền cần được thiết kế riêng: bằng chứng phù hợp với tổ chức, người hoặc nhóm có quyền thẩm định, phân tách trách nhiệm, hành động được phép và dấu vết. Cấu hình liên hệ chỉ là một đầu vào định tuyến trong quy trình đó.

Nếu cần cơ chế truy cập khẩn cấp, quyền kích hoạt và tác động của nó phải được xác định trước. Không giấu một tài khoản quản trị toàn quyền phía sau một hộp thư hỗ trợ thông thường.

Khi đã khôi phục được chủ thể quản trị hợp lệ, việc cập nhật liên hệ mới vẫn phải đi qua điều kiện kích hoạt tương ứng. Không giữ một địa chỉ tạm chưa kiểm soát rõ làm đầu mối lâu dài chỉ vì nó đã được dùng trong sự cố.

## 13. Ví dụ xuyên suốt: thay hộp thư chuyển cấp của tenant A

Tenant A đang dùng `recovery-team@tenant-a.example` để tiếp nhận chuyển cấp. Một quản trị viên được phép đề xuất chuyển sang hộp thư mới. Máy chủ tạo phiên bản đề xuất 13 và giữ phiên bản 12 hoạt động trong phạm vi mà chính sách còn cho phép.

Hộp thư mới nhận thử thách gắn với tenant A, mục đích chuyển cấp và phiên bản 13. Hoàn thành thử thách chỉ ghi nhận quyền kiểm soát điểm nhận. Người vận hành vẫn phải đạt các điều kiện thay đổi cấu hình, chẳng hạn xác thực lại và phê duyệt độc lập nếu chính sách yêu cầu.

Trong lúc chờ, người dùng Lan mở một hồ sơ mất MFA của danh tính có tư cách ở cả A và B. Luồng của A chỉ tạo thông tin chuyển cấp thuộc phạm vi A; nó không thông báo cho B hoặc cho phép đầu mối A thay credential toàn cục nếu A không có thẩm quyền đó.

Sau khi phiên bản 13 có hiệu lực, một công việc thông báo cũ được lấy ra khỏi hàng đợi. Dịch vụ không gửi tùy tiện tới bất kỳ địa chỉ mới nhất nào. Nó áp dụng quy tắc của loại sự kiện, kiểm tra điểm nhận còn được phép và lưu lại phiên bản đã sử dụng.

Nếu hộp thư cũ bị xác định đã bị chiếm, các công việc chưa gửi phải xử lý theo quyết định thu hồi và tuyến dự phòng được phép. Không gửi chi tiết hồ sơ đến hộp thư đó chỉ vì nó có mặt trong snapshot lúc tạo sự kiện.

Người nhận ở hộp thư mới bấm link mở hồ sơ. Cổng quản trị vẫn yêu cầu xác thực và kiểm tra quyền hiện tại. Việc được nhận email không tự gán vai trò phê duyệt hoặc quyền vô hiệu MFA của Lan.

## 14. Dấu vết, duy trì cấu hình và lỗi cần tránh

Nhật ký cần liên kết được tenant, liên hệ, mục đích, phiên bản, người đề xuất, kết quả xác minh, người cho phép kích hoạt nếu có và thời điểm hiệu lực. Với thông báo, cần truy được sự kiện nào đã chọn điểm nhận nào và kết quả gửi ra sao.

Địa chỉ liên hệ và thông tin hồ sơ là dữ liệu cần được giới hạn quyền xem. Báo cáo vận hành có thể chỉ dùng định danh hoặc giá trị đã che khi không cần địa chỉ đầy đủ. Không đưa mã xác minh, token khôi phục hoặc bí mật tích hợp vào nhật ký.

Cấu hình cần được duy trì khi nhân sự nghỉ việc, nhóm hỗ trợ thay đổi, hợp đồng tích hợp kết thúc hoặc tenant chuyển nhà cung cấp danh tính. Tần suất xác nhận lại và cách phát hiện điểm nhận không còn phù hợp nên gắn với rủi ro, không mặc định một lần xác minh là đủ mãi mãi.

| Lỗi | Hậu quả |
|---|---|
| Dùng một email tổng quát cho mọi mục đích | Nhầm thông báo với quyền khôi phục hoặc làm lộ dữ liệu quá mức |
| Tin `tenantId` do bên gọi tự khai báo | Đọc hoặc sửa cấu hình tenant khác |
| Xác minh địa chỉ rồi tự gán quyền quản trị | Người kiểm soát hộp thư có thể chiếm thẩm quyền ngoài ý muốn |
| Kích hoạt địa chỉ mới trước khi đủ điều kiện | Gửi hồ sơ đến điểm nhận chưa được phép |
| Cache cấu hình thiếu khóa tenant | Trộn đầu mối giữa các tổ chức |
| Gửi lại công việc cũ mà không xét thu hồi điểm nhận | Làm lộ thông tin cho kênh đã bị cấm sử dụng |
| Gửi token khôi phục cá nhân tới hộp thư hỗ trợ chung | Biến nhóm liên hệ thành đường truy cập tài khoản người dùng |
| Dùng tuyến dự phòng chưa được ủy quyền | Vượt ranh giới tenant hoặc làm mất dấu người chịu trách nhiệm |
| Coi email gửi thành công là phê duyệt | Bỏ qua xác thực, quyền và quyết định của chủ thể có thẩm quyền |

Cấu hình liên hệ đáng tin cậy phải giữ đúng tenant, mục đích và phiên bản tại cả lúc quản trị lẫn lúc sử dụng. Khi các đầu mối chỉ có khả năng liên lạc đã được cho phép, còn quyền thay đổi tài khoản được kiểm tra riêng, hệ thống có thể hỗ trợ người dùng hiệu quả mà không tạo thêm một đường vượt qua quy trình khôi phục.
