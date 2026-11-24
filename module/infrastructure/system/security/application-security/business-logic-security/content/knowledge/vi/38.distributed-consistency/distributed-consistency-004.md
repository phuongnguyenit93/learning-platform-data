# Distributed conflict resolution

## 1. Hội tụ dữ liệu chưa đủ để bảo vệ nghiệp vụ

Trong hệ thống phân tán, nhiều tiến trình hoặc nhiều vùng có thể xử lý những thay đổi dựa trên các ảnh chụp dữ liệu khác nhau. **Distributed conflict resolution** là cách phát hiện và quyết định xử lý các thay đổi cạnh tranh đó: chấp nhận một thay đổi, từ chối thay đổi cũ, hợp nhất theo quy tắc, chờ điều phối hoặc chuyển sang xử lý nghiệp vụ riêng.

Đối với bảo mật logic nghiệp vụ, kết quả không chỉ cần giống nhau ở mọi bản sao. Nó còn phải giữ đúng quyền hạn, điều kiện chuyển trạng thái và các giới hạn như không bán vượt tồn kho hoặc không dùng một phê duyệt nhiều lần.

Ví dụ xuyên suốt: hai vùng cùng nhìn thấy một mặt hàng còn 10 đơn vị. Vùng A xác nhận bán 6, vùng B cũng xác nhận bán 6. Sau khi đồng bộ, mọi nơi có thể cùng tính được đã bán 12 và còn -2. Dữ liệu đã hội tụ, nhưng invariant “chỉ xác nhận lượng hàng đã giữ chỗ hợp lệ” đã bị phá vỡ.

Một ví dụ khác: bản sao A nhận lệnh thu hồi quyền, bản sao B nhận cập nhật hồ sơ dựa trên dữ liệu cũ. Nếu cách hợp nhất phục hồi cả bản ghi người dùng từ B, quyền đã thu hồi có thể xuất hiện trở lại. Một thao tác sửa hồ sơ khi đó trở thành đường phục hồi quyền trái phép.

Điểm bắt đầu của giải quyết xung đột là xác định **điều gì được phép cạnh tranh** và **điều gì phải được phân xử trước khi tạo tác động**.

## 2. Các loại xung đột cần phân biệt

| Loại | Ví dụ | Vì sao cần quan tâm? |
|---|---|---|
| Cùng trường, khác giá trị | Hai vùng cùng sửa giá một sản phẩm | Không thể giữ cả hai giá hiện hành mà không có quy tắc nghiệp vụ |
| Khác trường nhưng cùng invariant | Một nơi đổi số lượng, nơi khác đổi hạn mức | Ghép các trường có thể tạo một tổ hợp chưa từng được kiểm tra |
| Chuyển trạng thái cạnh tranh | Một nơi hủy đơn, nơi khác xác nhận xuất kho | Trạng thái cuối cần phản ánh cả điều kiện và tác động đã xảy ra |
| Tạo tác động trùng | Hai worker cùng dùng một phê duyệt để cấp phiếu | Hai bản ghi khác ID vẫn có thể là hai tác động của cùng ý định |
| Cập nhật sau khi xóa hoặc thu hồi | Bản sao cũ gửi lại dữ liệu tài khoản đã vô hiệu hóa | Có thể làm sống lại đối tượng hoặc quyền đã bị thu hồi |
| Thông điệp trùng hoặc sai thứ tự | Sự kiện cũ đến sau sự kiện mới | Có thể làm trạng thái lùi hoặc thực hiện lại tác động |
| Mất quyền sở hữu xử lý | Worker cũ tiếp tục ghi sau khi quyền đã chuyển | Khóa hoặc lease không còn đủ để bảo vệ nơi tạo tác động |

Một số hiện tượng trên là lỗi truyền hoặc điều phối thay vì hai cập nhật độc lập. Tuy vậy, chúng có thể tạo cùng hậu quả nghiệp vụ, nên thiết kế cần xử lý cả nhận diện thao tác lặp lẫn cạnh tranh giữa các thao tác khác nhau.

Đừng chỉ tìm “hai request sửa cùng một dòng”. Một invariant có thể trải trên nhiều dòng, nhiều bảng hoặc nhiều dịch vụ. Hai transaction ghi hai dòng khác nhau vẫn có thể cùng làm vượt một hạn mức chung.

## 3. Xác định invariant và nơi có quyền quyết định

### 3.1. Phát biểu invariant theo miền nghiệp vụ

Với chức năng bán hàng, có thể xác định:

1. Mỗi lần xác nhận đơn phải gắn với lượng hàng đã được giữ chỗ hợp lệ.
2. Tổng quyền bán đã phân bổ không vượt lượng hàng được phép bán.
3. Một ý định đặt hàng không bị thực hiện thêm chỉ vì retry hoặc đổi định danh lần truyền.
4. Mọi điều chỉnh giá, số lượng và người hưởng lợi phải thuộc phạm vi đã được phê duyệt nếu chính sách yêu cầu.
5. Lệnh thu hồi quyền không được bị một bản ghi hồ sơ cũ ghi đè.
6. Bù trừ hoặc xử lý thủ công phải giữ lịch sử và không tạo thêm tác động trùng.

Các invariant giúp chọn ranh giới điều phối. Không cần buộc mọi dữ liệu trong hệ thống phải được ghi đồng bộ toàn cục chỉ vì một trường có xung đột; nhưng những nơi tạo tác động phụ thuộc cùng một giới hạn phải được bảo vệ bằng một mô hình phù hợp.

### 3.2. Xác định authority cho mỗi quyết định

Cần chỉ rõ nơi có thẩm quyền quyết định tồn kho khả dụng, quyền hiện hành, trạng thái phê duyệt và kết quả một thao tác. Bản sao đọc, cache hoặc bảng tổng hợp không tự có quyền xác nhận một thay đổi nhạy cảm chỉ vì trả dữ liệu nhanh.

Ví dụ: giao diện có thể hiển thị tồn kho từ bản sao đọc, nhưng bước xác nhận đơn phải kiểm tra tại ranh giới giữ chỗ có thẩm quyền. Dữ liệu hiển thị đã cũ cần được thể hiện bằng hành vi chấp nhận hoặc từ chối rõ ràng, không được dùng như một bảo đảm đã giữ hàng.

Nếu hai vùng đều được phép chấp nhận cùng một loại thay đổi khi mất liên lạc, phải giải thích tại sao các thay đổi đó vẫn giữ invariant. Chỉ nói “sau đó sẽ merge” chưa trả lời được câu hỏi này.

## 4. Phát hiện xung đột bằng revision và quan hệ nhân quả

### 4.1. Revision do nguồn có thẩm quyền quản lý

Với một đối tượng có nguồn ghi được phân xử thống nhất, client có thể gửi `expected_revision`. Máy chủ chỉ cập nhật khi revision hiện tại vẫn đúng với điều kiện của lệnh.

Ví dụ SQL minh họa giữ chỗ tồn kho trong một kho có thẩm quyền:

```sql
UPDATE inventory
SET available = available - :quantity,
    reserved = reserved + :quantity,
    revision = revision + 1
WHERE tenant_id = :trusted_tenant
  AND sku = :sku
  AND revision = :expected_revision
  AND available >= :quantity;
```

Máy chủ phải xác nhận `quantity` là số dương trong giới hạn cho phép, kiểm tra quyền và định nghĩa lượng hàng đúng theo nghiệp vụ. Số dòng cập nhật khác 1 nghĩa là chưa giữ chỗ thành công; không được tiếp tục xác nhận đơn như thể đã giữ được hàng.

Bản ghi giữ chỗ, định danh thao tác và cập nhật số lượng cần chung transaction nếu chúng là một tác động cục bộ nguyên tử. Câu SQL chỉ minh họa điểm kiểm tra và ghi có điều kiện; nó không tự giải quyết tác động ở một cơ sở dữ liệu khác.

### 4.2. Revision cục bộ không tạo thứ tự toàn cục

Nếu hai vùng tự tăng revision từ cùng một nền dữ liệu, cả hai có thể tạo revision 12 với nội dung khác nhau. Con số bằng nhau không chứng minh cùng lịch sử, và chọn số lớn hơn không tự giải quyết xung đột giữa hai nhánh.

Các cơ chế theo dõi quan hệ nhân quả có thể phân biệt một cập nhật xuất phát từ cập nhật trước với hai cập nhật cạnh tranh. Ví dụ, vector phiên bản có thể biểu diễn hai nhánh không bao hàm nhau. Nhưng nhận diện “đang cạnh tranh” vẫn chưa quyết định được nhánh nào được phép thắng theo nghiệp vụ.

Không dùng timestamp do client tự gửi làm bằng chứng thứ tự có thẩm quyền. Người gọi có thể gửi thời gian tương lai để làm thay đổi của mình thắng lâu dài. Ngay cả timestamp do máy chủ tạo cũng chịu ảnh hưởng của sai lệch đồng hồ và không thể thay thế quyền hoặc điều kiện phê duyệt.

### 4.3. Kiểm tra cả nhóm dữ liệu giữ invariant

Một revision trên một dòng không tự ngăn xung đột liên quan nhiều dòng. Ví dụ, hai người phê duyệt cùng tự rút khỏi nhóm trong khi invariant yêu cầu luôn còn ít nhất một người đủ quyền. Mỗi transaction sửa một dòng khác nhau có thể vẫn làm nhóm không còn người phê duyệt.

Cần đặt ranh giới trên aggregate, bản ghi điều phối, mức cô lập hoặc cơ chế ràng buộc phù hợp với hệ quản trị và invariant. Không suy ra rằng mọi transaction có kiểm tra revision riêng từng dòng đều an toàn trước mọi lịch chạy cạnh tranh.

## 5. Chọn chiến lược theo ý nghĩa thay đổi

| Chiến lược | Phù hợp khi | Giới hạn cần tôn trọng |
|---|---|---|
| Từ chối thay đổi dựa trên phiên bản cũ | Cần người gọi đọc lại hoặc xác nhận lại | Không tự cập nhật revision rồi gửi lại nội dung cũ vô điều kiện |
| Thực thi lệnh lại trên trạng thái mới | Lệnh có ngữ nghĩa rõ và có thể kiểm tra lại | Phải giữ định danh, quyền, invariant và phạm vi phê duyệt |
| Hợp nhất tự động | Các thay đổi thực sự tương thích theo miền | Khác trường không đồng nghĩa độc lập |
| Chọn theo thứ tự do một authority phân xử | Tác động nhạy cảm cần một quyết định thống nhất | Phải xử lý lỗi kết nối, retry và dữ liệu đọc cũ |
| Phân bổ trước quyền thực hiện | Giới hạn có thể chia thành các phần không chồng lấn | Không tạo thêm quyền khi chuyển vùng, phục hồi hoặc phân bổ lại |
| Chuyển xử lý nghiệp vụ/thủ công | Có tác động không đảo ngược hoặc chưa đủ bằng chứng | Cần trạng thái, quyền quyết định và dấu vết rõ ràng |

Không có một chiến lược duy nhất cho mọi trường. Màu giao diện có thể chọn một giá trị theo chính sách đơn giản; quyền quản trị, giá đã phê duyệt và số hàng đã cam kết cần các quy tắc mạnh hơn.

## 6. Vì sao last-write-wins dễ làm mất quy tắc nghiệp vụ?

Last-write-wins, thường viết là LWW, chọn một giá trị theo thứ tự ghi đã định nghĩa. Nếu có quy tắc phá hòa ổn định, các bản sao có thể chọn cùng kết quả. Điều đó không chứng minh kết quả được chọn là hợp lệ.

### 6.1. Mất cập nhật và che giấu tác động

Hai vùng cùng đọc tồn kho 10, mỗi vùng bán 6 rồi ghi `available = 4`. LWW có thể chọn một trong hai giá trị 4. Con số trông không âm, nhưng hệ thống đã xác nhận tổng cộng 12 đơn vị. Việc chọn một ảnh chụp không làm biến mất cam kết đã gửi cho khách hàng.

Với tổng số lượng, chuyển sang một bộ đếm hợp nhất được có thể phản ánh đúng đã bán 12. Nhưng kết quả đúng về đếm vẫn không sửa được việc đã cam kết vượt giới hạn 10.

### 6.2. Quyền và trạng thái không phải giá trị tùy ý

Giả sử thao tác A thu hồi quyền quản trị, còn thao tác B sửa số điện thoại dựa trên bản ghi cũ vẫn chứa quyền quản trị. Nếu B ghi toàn bộ bản ghi và được chọn thắng, việc sửa số điện thoại có thể khôi phục quyền.

Biện pháp cần thiết gồm tách lệnh theo mục đích, chỉ cho sửa các trường được phép và dùng chính sách cạnh tranh rõ ràng cho quyền. Không cho resolver dùng toàn bộ dữ liệu từ một DTO cũ như nguồn có thẩm quyền để cấp lại quyền.

Một chính sách ưu tiên thu hồi có thể là lựa chọn bảo thủ khi hợp nhất quyền, nhưng nó không thu hồi được các hành động đã được một bản sao cũ cho phép trước đó. Nếu nghiệp vụ yêu cầu thu hồi có hiệu lực tại ranh giới thực hiện, bước kiểm tra quyền cần dựa vào authority hoặc một cơ chế phiên bản quyền đáp ứng yêu cầu đó.

### 6.3. Timestamp không thay thế phê duyệt

Không chọn giá cao hơn, giá thấp hơn, trạng thái có số thứ tự lớn hơn hoặc bản ghi có thời gian mới hơn như một quy tắc mặc định cho mọi xung đột. Một mức giá mới hơn vẫn có thể chưa được phê duyệt; trạng thái `SHIPPED` không tự thắng `CANCELLED` chỉ vì được gán một số lớn hơn.

Nếu dùng LWW cho một thuộc tính ít ảnh hưởng, cần ghi rõ đây là chính sách chấp nhận mất một thay đổi và bảo đảm thuộc tính đó không kéo theo quyền hoặc invariant nhạy cảm.

## 7. Hợp nhất tự động và CRDT: đúng trong phạm vi nào?

### 7.1. Hợp nhất theo trường vẫn cần kiểm tra liên hệ

Hai người sửa hai trường khác nhau có thể hợp nhất nếu các thay đổi độc lập theo nghiệp vụ. Nhưng sửa địa chỉ đường và mã bưu chính từ hai ảnh chụp khác nhau có thể tạo một địa chỉ không hợp lệ. Tương tự, thay số lượng và đơn giá riêng rẽ có thể vượt tổng tiền đã được duyệt.

Một resolver cần kiểm tra:

1. Mỗi thay đổi có nguồn và quyền hợp lệ không?
2. Các thay đổi dựa trên điều kiện nền nào?
3. Tổ hợp kết quả có giữ mọi invariant liên quan không?
4. Việc hợp nhất có mở rộng phạm vi đã được phê duyệt không?
5. Có tác động nào đã xảy ra mà trạng thái hợp nhất không thể biểu diễn đầy đủ không?

Nếu không đủ bằng chứng, giữ xung đột rõ ràng hoặc yêu cầu quyết định mới. Không chọn một tổ hợp chỉ vì có thể ghép các trường về mặt cú pháp.

### 7.2. CRDT bảo đảm hội tụ theo mô hình đã chọn

CRDT là nhóm cấu trúc dữ liệu được thiết kế để các cập nhật và phép hợp nhất tuân theo những điều kiện cho phép hội tụ trong mô hình tương ứng. Nó hữu ích cho một số tập hợp, bộ đếm hoặc trạng thái có ngữ nghĩa hợp nhất rõ ràng.

Tuy nhiên, “hợp nhất được” không đồng nghĩa “giữ mọi ràng buộc nghiệp vụ”. Một bộ đếm cộng gộp đúng hai lượt bán vẫn có thể cho kết quả vượt tồn kho. Một tập hợp chứa cả hai định danh đổi thưởng vẫn có thể vi phạm quy tắc mỗi phiếu chỉ được sử dụng một lần.

Một phép kiểm tra thiết kế hữu ích: nếu hai bản sao đều hợp lệ khi xét riêng, hợp nhất chúng có luôn cho trạng thái hợp lệ theo invariant không? Nếu câu trả lời là không, cần điều phối, giới hạn quyền cập nhật hoặc một mô hình khác; chỉ bổ sung CRDT không giải quyết được ràng buộc đó.

### 7.3. Xóa, thu hồi và tombstone

Việc xóa ở một nơi cạnh tranh với cập nhật cũ ở nơi khác cần chính sách rõ ràng. Nếu xóa mọi dấu vết quá sớm, bản sao hoặc thông điệp cũ có thể làm sống lại đối tượng.

Tombstone là dấu vết tối thiểu cho biết đối tượng hoặc trạng thái đã bị loại bỏ theo chính sách. Thời gian giữ phải xét khả năng các bản sao và công việc cũ quay lại. Không thể dọn mọi bằng chứng rồi vẫn bảo đảm nhận diện vô hạn một bản ghi cũ đã bị quên.

Chính sách ưu tiên thêm hoặc ưu tiên xóa có thể phù hợp với từng loại tập hợp, nhưng phải được lựa chọn theo nghiệp vụ. Cấp lại một quyền sau thu hồi thường cần một lệnh mới có thẩm quyền, không chỉ là kết quả hợp nhất của dữ liệu cũ.

## 8. Giữ giới hạn trước khi tác động: điều phối hoặc phân bổ quyền

### 8.1. Một nơi phân xử cho invariant nhạy cảm

Có thể đặt việc giữ chỗ và xác nhận quyền bán tại một authority logic. Authority đó có thể được triển khai bằng một cụm có cơ chế sao chép và quyết định nhất quán; không nhất thiết là một tiến trình đơn lẻ.

Khi không thể liên lạc với nơi phân xử, hệ thống cần chọn hành vi phù hợp: giữ đơn ở trạng thái chờ, từ chối xác nhận hoặc chỉ cho thực hiện trong một phạm vi quyền đã được cấp trước. Không cho hai phía tự xác nhận cùng phần tài nguyên rồi hy vọng hợp nhất sẽ sửa được sau.

Đồng thời, một authority cũng cần chống retry và ghi đồng thời. Việc mọi request đến cùng một dịch vụ không tự bảo đảm nguyên tử nếu dịch vụ vẫn thực hiện “đọc số lượng rồi ghi lại” mà không có ràng buộc thích hợp.

### 8.2. Phân bổ trước quyền tiêu thụ giới hạn

Với một số miền, có thể chia quyền bán để các vùng xử lý cục bộ mà không tranh cùng phần tài nguyên. Ví dụ tổng 10 đơn vị được phân bổ thành quyền bán 6 ở A và 4 ở B.

- A chỉ xác nhận trong phạm vi quyền còn lại của A.
- B chỉ xác nhận trong phạm vi quyền còn lại của B.
- Tổng quyền chưa dùng, quyền đã dùng và quyền đang chuyển phải được hạch toán nhất quán.
- B muốn bán 6 phải xin thêm quyền hoặc chờ; không được tự dùng ảnh chụp tồn kho toàn cục 10 làm ngân sách mới.

Đây thường được mô tả theo mô hình escrow hoặc phân bổ trước quyền cập nhật. Nó đổi khả năng chấp nhận yêu cầu tại từng vùng để giữ giới hạn chung, thay vì cho mọi vùng tiêu thụ tự do.

### 8.3. Chuyển và thu hồi phân bổ cũng là nghiệp vụ cần phân xử

Nếu chuyển một đơn vị từ A sang B, không được cộng cho B trước rồi để A tiếp tục dùng đơn vị đó vì timeout hoặc phục hồi bản sao cũ. Cần một giao thức chuyển có định danh, trạng thái và bảo đảm không có hai bên cùng sở hữu quyền có hiệu lực.

Khi một vùng mất liên lạc, không mặc nhiên phân bổ lại toàn bộ quyền còn ghi ở vùng đó cho vùng khác. Vùng cũ có thể vẫn đang bán trong ngân sách đã nhận. Thu hồi hoặc chuyển quyền cần được chứng minh có hiệu lực theo mô hình đã chọn.

Không phải mọi invariant đều chia được theo cách này. Một phê duyệt dùng đúng một lần hoặc một quyết định thu hồi quyền có thể cần điểm phân xử riêng thay vì chia thành ngân sách.

## 9. Retry lệnh trên trạng thái mới mà không vượt quyền

### 9.1. Lệnh nghiệp vụ tốt hơn ảnh chụp cần ghi đè

Thay vì gửi toàn bộ đối tượng với `status`, `price`, `owner` và các trường cũ, nên biểu diễn mục đích bằng lệnh có phạm vi rõ: giữ chỗ một lượng hàng, yêu cầu hủy hoặc đề nghị thay giá.

Lệnh có thể gồm:

```text
operation_id
business_intent_id
entity_id
expected_revision
command_type
các tham số có ý nghĩa nghiệp vụ
approval_reference nếu cần
```

Tenant, quyền và dữ liệu có thẩm quyền phải được xác định ở máy chủ. Client không được tự biến `approved=true` hoặc một mức ưu tiên trong request thành quyền thắng xung đột.

### 9.2. Retry phải thực thi lại điều kiện, không chỉ thay revision

Luồng khái niệm:

```text
nhận lệnh và xác thực chủ thể
tra cứu kết quả đã có theo định danh thao tác

nếu cần một lần thực thi mới của lệnh:
    đọc trạng thái có thẩm quyền
    kiểm tra quyền hiện tại và invariant liên quan
    kiểm tra điều kiện nền và phạm vi phê duyệt
    ghi có điều kiện trong transaction phù hợp

nếu có xung đột:
    đọc lại trạng thái hoặc trả yêu cầu xác nhận lại
    chỉ retry tự động nếu ngữ nghĩa lệnh vẫn hợp lệ
    giữ định danh để không tạo thêm tác động
```

Ví dụ, giữ chỗ thêm 2 đơn vị có thể được đánh giá lại trên tồn kho mới nếu còn đủ quyền và số lượng. Nhưng lệnh chấp nhận báo giá 500.000 không được tự chuyển thành chấp nhận báo giá 600.000 chỉ để retry thành công.

Nếu thay đổi sau xung đột làm khác số tiền, người hưởng lợi, số lượng hoặc nội dung đã được phê duyệt, cần áp dụng chính sách xác nhận/phê duyệt lại. Không dùng quyền của resolver nội bộ để mở rộng một lệnh mà người gọi không có quyền tạo.

### 9.3. Phân biệt phát lại kết quả với thực hiện lệnh mới

Một thao tác đã thành công có thể trả lại kết quả cũ cho người còn quyền, không cần thực hiện tác động lần nữa. Một thao tác chưa rõ kết quả cần đối soát trước khi quyết định retry.

Lỗi mạng sau commit không chứng minh thất bại. Nếu cơ sở dữ liệu đã commit nhưng phản hồi bị mất, việc đọc lại revision rồi gửi một operation ID mới có thể gây tác động trùng. Cần giữ định danh ý định và kiểm tra sổ thao tác.

## 10. State machine, sự kiện và quyền worker

### 10.1. Xung đột chuyển trạng thái phải xét tác động

Giả sử một đơn đang `APPROVED`. Một lệnh muốn chuyển sang `CANCELLED`, lệnh khác muốn chuyển sang `SHIPPING`. Có thể dùng trạng thái/revision có điều kiện tại nơi phân xử để chỉ một chuyển trạng thái nền được chấp nhận trước.

Lệnh còn lại phải được đánh giá trên trạng thái mới. Nếu đã có yêu cầu xuất kho ra bên ngoài, “hủy” có thể trở thành yêu cầu ngừng giao hoặc một nghiệp vụ bù trừ, không phải ghi đè một nhãn trạng thái.

Không sắp xếp enum rồi lấy trạng thái lớn nhất. Một state machine cần biểu diễn cả điều kiện chuyển, quyền, trạng thái đang chờ và kết quả thực tế của tác động.

### 10.2. Sự kiện trùng và sai thứ tự

Consumer cần phân biệt định danh sự kiện để nhận diện giao lại với sequence/revision dùng để hiểu thứ tự theo hợp đồng. Một UUID không tự biểu diễn thứ tự nhân quả.

Nếu hợp đồng có sequence liên tiếp theo từng aggregate, consumer có thể phát hiện khoảng thiếu, giữ sự kiện trong bộ đệm có giới hạn hoặc đồng bộ lại từ nguồn có thẩm quyền. Không mặc định mọi revision của mọi hệ thống đều liên tiếp, và không bỏ qua khoảng thiếu khi sự kiện ở giữa có tác động bắt buộc.

Ghi inbox nhận diện sự kiện và tác động cục bộ trong cùng transaction khi chúng cần cùng số phận. Điều này ngăn giao lại sau commit tạo thêm tác động, nhưng không tự sửa một chuỗi sự kiện đã được thiết kế sai ngữ nghĩa.

### 10.3. Worker cũ không được ghi bằng quyền đã mất

Lease hoặc khóa phân tán có thể hết hạn trong khi worker cũ vẫn chạy. Cần một cơ chế để nơi ghi kiểm tra quyền sở hữu hiện hành, chẳng hạn epoch tăng dần được authority quản lý và đối chiếu tại mọi điểm ghi liên quan.

Việc chuyển quyền phải bảo đảm worker cũ không còn được ghi theo giao thức đã chọn; chỉ tạo một số epoch mới trong bộ nhớ worker mới không có tác dụng nếu nơi lưu không kiểm tra. Với dịch vụ bên ngoài, cơ chế cục bộ này cũng không thu hồi được lời gọi đã gửi, nên vẫn cần định danh và đối soát ở ranh giới ngoài.

## 11. Khi cần quyết định thủ công hoặc bù trừ

### 11.1. Biểu diễn xung đột thành dữ liệu có thể xử lý

Một hồ sơ xung đột có thể lưu:

| Thông tin | Mục đích |
|---|---|
| `conflict_id`, tenant, đối tượng | Định danh và kiểm soát phạm vi |
| Các operation ID và fingerprint | Biết những lệnh nào đang cạnh tranh |
| Phiên bản nền và trạng thái có thẩm quyền | Hiểu điều kiện mà mỗi lệnh đã dựa vào |
| Quyền/phê duyệt liên quan | Xác định giới hạn một quyết định được phép thực hiện |
| Tác động đã xác nhận và tác động chưa rõ | Tránh chọn một giá trị rồi bỏ quên việc đã xảy ra |
| Trạng thái xử lý và revision | Ngăn hai người giải quyết cùng hồ sơ trái nhau |
| Quyết định, người thực hiện và kết quả | Truy vết và hỗ trợ retry thao tác giải quyết |

Hồ sơ không nhất thiết chứa toàn bộ dữ liệu nhạy cảm của request. Cần giữ đủ bằng chứng trong phạm vi người xử lý được phép đọc.

### 11.2. Giữ trạng thái chờ đúng nghĩa

Có thể dùng trạng thái như `CONFLICT_PENDING` hoặc `MANUAL_REVIEW` để thể hiện cần quyết định. Nhưng một nhãn chờ không tự đóng băng mọi tác động: các đường ghi liên quan phải kiểm tra trạng thái hoặc điều kiện đã được đặt ra.

Nếu vẫn cho cập nhật những trường độc lập, cần định nghĩa rõ phạm vi. Không giữ khóa cơ sở dữ liệu xuyên suốt nhiều giờ chờ con người; thay vào đó lưu trạng thái bền vững và kiểm tra lại revision khi áp dụng quyết định.

### 11.3. Quyết định giải quyết cũng là một lệnh có quyền hạn

Người xử lý cần quyền trên tenant, đối tượng và loại tác động. Nếu thay giá hoặc mở rộng số lượng cần phê duyệt, đường giải quyết xung đột không được miễn điều kiện đó chỉ vì là công cụ quản trị.

Khi áp dụng quyết định:

```text
bắt đầu transaction
    xác thực phạm vi và kiểm tra quyền giải quyết hiện tại
    kiểm tra hồ sơ xung đột và phiên bản dữ liệu hiện tại
    xác lập định danh lệnh giải quyết
    kiểm tra invariant và phê duyệt của phương án đã chọn
    áp dụng thay đổi, ghi quyết định và ý định phát sự kiện nếu cần
commit
```

Nếu dữ liệu đã đổi từ lúc người xử lý xem hồ sơ, cần đánh giá lại; không bỏ điều kiện phiên bản để ép phương án cũ thắng. Hai lần gửi cùng quyết định sau mất phản hồi không được tạo thêm tác động.

### 11.4. Tác động đã xảy ra cần nghiệp vụ bù trừ

Nếu hai đơn đều đã được xác nhận hoặc một kiện hàng đã giao, chọn một bản ghi cuối không làm tác động còn lại biến mất. Cần xác định khả năng hủy, điều chỉnh, giao bù hoặc xử lý với khách hàng theo chính sách.

Bù trừ là một nghiệp vụ mới, có định danh và điều kiện hiện tại. Nó phải chống trùng và ghi dấu vết liên kết với tác động gốc. Không đặt lại số dư hay tồn kho về một ảnh chụp cũ vì có thể xóa các thay đổi hợp lệ phát sinh sau đó.

Với tác động ngoài, có thể có trạng thái đang chờ hoặc chưa rõ kết quả. Outbox giúp lưu ý định cùng transaction cục bộ nhưng không tạo rollback xuyên hệ thống. Cần theo dõi đến khi có đủ bằng chứng về kết quả hoặc chuyển sang quy trình xử lý phù hợp.

## 12. Các cách lạm dụng xung đột cần phòng ngừa

| Cách lạm dụng hoặc giả định sai | Hậu quả | Cách kiểm soát |
|---|---|---|
| Gửi timestamp tương lai để thắng LWW | Giá trị của kẻ tấn công lấn át thay đổi hợp lệ | Không dùng thời gian do client tự khai làm authority; kiểm tra quyền và ngữ nghĩa |
| Tạo hai request đồng thời dựa trên cùng tồn kho | Bán vượt kho hoặc vượt hạn mức | Phân xử tại ranh giới giữ chỗ hoặc dùng quyền tiêu thụ đã phân bổ |
| Đổi nonce/operation ID cho cùng phê duyệt | Tạo thêm tác động dù từng request riêng đều có vẻ mới | Ràng buộc theo ý định/phê duyệt nghiệp vụ, không chỉ định danh lần truyền |
| Gửi DTO cũ sau thu hồi quyền | Khôi phục quyền hoặc chủ sở hữu cũ | Dùng lệnh theo mục đích, giới hạn trường được sửa và chính sách quyền riêng |
| Lấy revision mới rồi tự gửi lại toàn bộ ảnh chụp cũ | Ghi đè thay đổi mới qua một retry có vẻ hợp lệ | Đánh giá lại lệnh và invariant, không chỉ sửa `expected_revision` |
| Dùng công cụ resolver như đường đặc quyền | Bỏ qua phê duyệt hoặc quyền theo đối tượng | Kiểm tra quyền và điều kiện nghiệp vụ cho quyết định giải quyết |
| Xóa tombstone để giảm dung lượng | Bản ghi hoặc quyền cũ sống lại khi đồng bộ | Chính sách giữ dấu vết khớp với cửa sổ bản sao/thông điệp cũ quay lại |
| Chọn enum lớn nhất làm trạng thái cuối | Coi đã giao hoặc đã hủy dù tác động thực tế khác | Dùng state machine và bằng chứng tác động |
| Worker cũ tiếp tục ghi sau hết lease | Ghi đè kết quả của chủ sở hữu mới | Kiểm tra quyền ghi hiện hành tại nơi tạo tác động |
| Reset mọi xung đột rồi phát lại lô | Tạo tác động trùng và mất bằng chứng | Phân loại từng thao tác, giữ định danh và đối soát kết quả chưa rõ |
| Cho hai vùng dùng cùng ngân sách sau lỗi kết nối | Tiêu thụ hai lần quyền đã phân bổ | Giao thức chuyển/thu hồi quyền có định danh và không tạo sở hữu trùng |

Một người gọi hợp lệ cũng có thể chủ động tạo cạnh tranh để thử vượt giới hạn. Vì vậy, không chỉ coi xung đột là tình huống hiếm do mạng. Các điều kiện quyết định phải nằm ở phía máy chủ và được thực thi cả khi nhiều request đến đồng thời.

## 13. Kiểm thử tính đúng đắn dưới cạnh tranh

Kiểm thử nên điều khiển được lịch chạy: cho hai worker đọc cùng nền, dừng trước ghi, đảo thứ tự thông điệp, ngắt phản hồi sau commit hoặc làm lease hết hạn trong khi worker cũ còn chạy. Không chỉ gửi hai request tuần tự rồi kết luận đã xử lý cạnh tranh.

| Kịch bản | Điều cần xác nhận |
|---|---|
| Hai lệnh cùng `expected_revision` tại một authority | Không cùng ghi đè từ một nền; lệnh không được chấp nhận có kết quả rõ |
| Hai vùng cùng muốn tiêu thụ quá tổng quyền | Tổng cam kết hợp lệ không vượt ngân sách được bảo vệ |
| Mỗi vùng đúng giới hạn cục bộ nhưng dùng ảnh chụp toàn cục | Kiểm thử phát hiện invariant chung bị phá vỡ, không đánh giá đạt chỉ vì đã hội tụ |
| Hai transaction sửa các dòng khác nhau của một invariant | Ranh giới aggregate/ràng buộc vẫn bảo vệ giới hạn chung |
| Cùng ý định, khác nonce hoặc operation ID | Không tạo thêm tác động ngoài phạm vi nghiệp vụ |
| Giá hoặc số lượng thay đổi sau phê duyệt | Retry không tự mở rộng nội dung đã duyệt |
| Thu hồi quyền cạnh tranh cập nhật hồ sơ | Hồ sơ không khôi phục quyền; đường thực hiện kiểm tra quyền đúng yêu cầu |
| Cập nhật cạnh tranh xóa | Không làm sống lại đối tượng trái chính sách |
| Timestamp client ở tương lai | Không khiến request tự có quyền thắng hoặc bỏ qua điều kiện |
| Hợp nhất hai trường phụ thuộc | Tổ hợp kết quả được kiểm tra, không chỉ ghép cú pháp |
| Sự kiện đến trùng hoặc sai thứ tự | Không lùi trạng thái hoặc tạo lại tác động; khoảng thiếu được xử lý theo hợp đồng |
| Worker cũ còn chạy sau chuyển quyền | Không ghi bằng quyền đã mất tại các điểm được bảo vệ |
| Mất phản hồi sau commit | Tra cứu được thao tác cũ, không đổi ID để tạo tác động lần nữa |
| Chuyển quyền bán bị timeout giữa hai vùng | Không có hai ngân sách cùng có hiệu lực cho cùng quyền được chuyển |
| Hai người xử lý cùng hồ sơ xung đột | Chỉ quyết định hợp lệ theo phiên bản hiện tại được áp dụng |
| Bù trừ bị retry sau crash | Không đảo ngược một tác động nhiều lần |
| Phục hồi từ bản sao dữ liệu cũ | Không coi quyền đã dùng hoặc tác động ngoài còn tồn tại là chưa xảy ra |
| Mất liên lạc với authority | Hành vi chờ/từ chối/phạm vi quyền cấp trước đúng với thiết kế |

Các khẳng định cần đo tác động có hiệu lực, quyền hiện hành, tổng quyền đã phân bổ, liên kết phê duyệt và trạng thái phụ thuộc. Việc mọi bản sao có cùng checksum chỉ chứng minh chúng giống nhau tại thời điểm kiểm tra; không chứng minh nội dung đó giữ invariant.

Với tình huống tác động đã ra bên ngoài, kiểm thử cần xác nhận cả tham chiếu bên nhận hoặc cơ chế mô phỏng của ranh giới đó. Rollback dữ liệu cục bộ trong kiểm thử không được che mất một tác động ngoài đã xảy ra.

## 14. Ví dụ thiết kế: hai vùng bán cùng một mặt hàng

### 14.1. Thiết kế gây lỗi

Cả A và B có ảnh chụp `available = 10`. Mỗi vùng xác nhận bán 6 rồi ghi `available = 4`. Sau đồng bộ:

- LWW có thể cho tồn kho 4 nhưng che giấu một lần tiêu thụ.
- Bộ đếm cộng gộp có thể cho đã bán 12, còn -2, phản ánh được tổng tác động nhưng không giữ giới hạn.
- Đổi nhãn một đơn thành `CONFLICT` không thu hồi thông báo đã xác nhận cho khách hàng.

Cả ba biểu hiện đều cho thấy cần thay đổi ranh giới xác nhận, không chỉ đổi thuật toán chọn giá trị cuối.

### 14.2. Phương án một authority giữ chỗ

Mọi xác nhận bán đều cần giữ chỗ tại authority. Hai request tiêu thụ 6 cạnh tranh trên tổng 10; chỉ một request đủ điều kiện giữ chỗ theo giao thức. Request còn lại phải chờ, giảm số lượng theo lựa chọn được người dùng chấp nhận hoặc bị từ chối.

Mỗi giữ chỗ gắn với ý định đặt hàng và định danh thao tác. Nếu phản hồi bị mất sau commit, client tra cứu cùng thao tác thay vì giữ thêm 6 với một ID mới. Hủy hoặc hết hạn giữ chỗ cũng cần giao thức trạng thái để không vừa giải phóng hàng vừa cho đơn cũ tiếp tục xác nhận.

### 14.3. Phương án phân bổ quyền bán

A nhận ngân sách 6, B nhận 4. A có thể xác nhận 6 trong ngân sách của mình. B không được xác nhận yêu cầu 6 khi chỉ có quyền bán 4, dù bản sao hiển thị tổng tồn kho từng là 10.

Nếu B cần thêm 2, nó phải xin chuyển quyền hoặc chờ cơ chế điều phối. Khi không thể chứng minh quyền đã được chuyển an toàn, không tự cộng thêm ngân sách. Đây là giới hạn chấp nhận yêu cầu được lựa chọn để giữ invariant.

### 14.4. Khi lỗi cũ đã tạo hai đơn được xác nhận

Cần đối soát lượng hàng thực tế, giữ chỗ, tác động xuất kho và cam kết với khách hàng. Quyết định hủy, giao bù hoặc điều chỉnh là một nghiệp vụ có điều kiện, không phải chọn một dòng để xóa.

Sau khắc phục, cần giữ liên kết giữa các lệnh cạnh tranh, tác động gốc và hành động bù trừ. Điều đó giúp retry, điều tra và đồng bộ muộn không làm tái xuất hiện tác động đã xử lý.

## 15. Các câu hỏi cần trả lời trước khi triển khai

- Invariant nào phải luôn được giữ trước khi tạo tác động, invariant nào chấp nhận trạng thái tạm thời?
- Nơi nào có thẩm quyền quyết định và các vùng ghi có thực sự cùng được phân xử không?
- Revision có ý nghĩa toàn cục trong phạm vi nào, hay chỉ là bộ đếm cục bộ?
- Hai thay đổi hợp lệ riêng rẽ có luôn hợp nhất thành trạng thái hợp lệ không?
- Retry có giữ định danh ý định và kiểm tra lại quyền, điều kiện nền, phê duyệt không?
- Lệnh thu hồi, xóa hoặc hủy cạnh tranh với cập nhật mới được xử lý thế nào?
- Khi mất liên lạc, hệ thống chờ, từ chối hay dùng quyền đã cấp trước trong giới hạn nào?
- Worker mất quyền và thông điệp cũ còn có thể tạo tác động ở những đâu?
- Tác động không đảo ngược hoặc chưa rõ kết quả được đối soát và bù trừ ra sao?
- Công cụ giải quyết xung đột có chống retry trùng, kiểm tra phiên bản và giữ audit không?

Giải quyết xung đột phân tán cần gắn với ý nghĩa của lệnh, quyền và tác động. Phát hiện đúng cạnh tranh, chọn ranh giới phân xử phù hợp và kiểm tra kết quả theo invariant sẽ giúp dữ liệu hội tụ mà không biến quá trình hợp nhất thành một đường vượt quy tắc nghiệp vụ.
