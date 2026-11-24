# Feature abuse threshold — Ngưỡng chống lạm dụng tính năng

## Mục tiêu bài học

Trong chương **Abuse Controls**, feature abuse threshold là ngưỡng dùng để nhận biết và kiểm soát việc khai thác một tính năng vượt quá mức sử dụng chấp nhận được. Trọng tâm là tác động nghiệp vụ: một người có thể gửi những yêu cầu hoàn toàn hợp lệ về cú pháp, có phiên đăng nhập hợp lệ, nhưng vẫn dùng tính năng để tiêu hao ngân sách, quấy rối người nhận hoặc chiếm tài nguyên của người khác.

Bài học thuộc phạm vi bảo mật logic nghiệp vụ: ngưỡng phải phối hợp với business invariants, state machine, quyền theo đối tượng, transaction và idempotency. Một ngưỡng được cấu hình tốt vẫn không bảo vệ được hệ thống nếu người dùng có thể đổi mã đối tượng để vượt quyền, bỏ qua bước duyệt hoặc gửi nhiều yêu cầu đồng thời trước khi bộ đếm được cập nhật.

Sau bài học, bạn có thể:

- Xác định một tính năng cần đo điều gì, trên chủ thể nào và trong khoảng thời gian nào.
- Phân biệt ngưỡng chống lạm dụng với hạn mức sản phẩm, quy tắc nghiệp vụ bắt buộc và giới hạn lưu lượng HTTP.
- Thiết kế việc kiểm tra và tiêu thụ hạn mức an toàn khi có retry, xử lý bất đồng bộ và yêu cầu đồng thời.
- Chọn phản ứng phù hợp, đo tác động lên người dùng hợp lệ và kiểm thử các cách lách ngưỡng.

## 1. Khi yêu cầu hợp lệ vẫn gây thiệt hại

Giả sử một nền tảng cho phép nhân viên được phân quyền phát hành mã ưu đãi cho khách hàng. Mỗi lần phát hành đều có thể thỏa mãn các kiểm tra thông thường:

- Nhân viên đã đăng nhập và thuộc đúng tổ chức.
- Chiến dịch đang hoạt động.
- Mệnh giá nằm trong danh sách cho phép.
- Ngân sách chiến dịch còn đủ.

Một tài khoản bị chiếm quyền có thể liên tục phát hành các mã nhỏ cho nhiều tài khoản do kẻ tấn công kiểm soát. Từng yêu cầu đều hợp lệ, nhưng tổng hành vi làm cạn ngân sách và cản trở hoạt động bình thường.

Ở đây có hai lớp bảo vệ khác nhau:

1. **Quy tắc bắt buộc:** không phát hành ngoài quyền, ngoài trạng thái cho phép hoặc vượt ngân sách đã duyệt.
2. **Kiểm soát lạm dụng:** chặn, trì hoãn hoặc yêu cầu xác minh khi tốc độ, số lượng, tổng giá trị hay cách phân phối mã trở nên bất thường.

Lớp thứ hai không được phép nới lỏng lớp thứ nhất. Hoàn thành CAPTCHA hoặc xác minh bổ sung không tạo ra quyền phát hành và không cho phép vượt ngân sách.

Một yêu cầu mỗi giây có thể là lưu lượng thấp đối với API, nhưng là tốc độ rất cao đối với một thao tác có giá trị lớn. Vì vậy, chỉ đếm request trên IP hoặc endpoint thường không phản ánh đủ rủi ro nghiệp vụ.

## 2. Phân biệt các loại kiểm soát

| Kiểm soát | Câu hỏi cần trả lời | Ví dụ |
|---|---|---|
| Quyền theo đối tượng | Chủ thể này có được thao tác trên đúng đối tượng này không? | Nhân viên tổ chức A không được phát hành mã từ chiến dịch của tổ chức B. |
| Business invariant | Điều gì luôn phải đúng sau mọi giao dịch? | Tổng giá trị đã phát hành cộng giá trị đang giữ chỗ không vượt ngân sách đã duyệt. |
| State machine | Từ trạng thái hiện tại có được thực hiện chuyển đổi này không? | Chiến dịch đang chờ duyệt không được phát hành mã. |
| Hạn mức sản phẩm | Quyền lợi hoặc giới hạn hợp đồng của khách hàng là gì? | Gói dịch vụ cho phép tối đa một số lượng chiến dịch nhất định. |
| Feature abuse threshold | Mức sử dụng nào cần can thiệp để hạn chế lạm dụng? | Một nhân viên tạo quá nhiều mã cho người nhận mới trong một khoảng ngắn. |
| Rate limit hạ tầng | Có cần bảo vệ khả năng phục vụ khỏi lưu lượng quá lớn không? | Giới hạn số request đến API trong một giây. |
| Giới hạn đồng thời | Có bao nhiêu công việc được phép đang chạy? | Một tổ chức chỉ có một số lượng tác vụ xuất dữ liệu đang xử lý. |
| Idempotency | Retry cùng một thao tác có tạo thêm tác động nghiệp vụ không? | Gửi lại cùng khóa idempotency không phát hành thêm mã. |

Cùng một cơ chế đếm có thể phục vụ nhiều mục đích, nhưng ý nghĩa và cách vận hành khác nhau. Nếu giới hạn là cam kết sản phẩm hoặc quy tắc bắt buộc, không được âm thầm thay đổi nó theo điểm rủi ro. Nếu là ngưỡng chống lạm dụng, cần có cách điều chỉnh, giải thích và theo dõi chặn nhầm.

## 3. Xác định đơn vị nghiệp vụ trước khi đặt số

### 3.1. Đặt tên cho hành động được bảo vệ

Không bắt đầu bằng câu hỏi “mỗi API cho phép bao nhiêu request?”. Trước hết hãy mô tả hành động có ý nghĩa với sản phẩm, chẳng hạn:

- Phát hành một mã ưu đãi cho một người nhận.
- Thử áp dụng mã khuyến mãi cho một đơn hàng.
- Gửi một lời mời đến một người nhận mới.
- Tạo một yêu cầu hoàn tiền.
- Khởi chạy một tác vụ xuất dữ liệu.

Một hành động có thể được gọi qua REST, GraphQL, giao diện quản trị hoặc công việc nền. Tất cả đường gọi cùng thực hiện một quyền năng nghiệp vụ cần đi qua điểm kiểm soát chung ở tầng dịch vụ. Chặn một endpoint nhưng để đường gọi khác tiêu thụ cùng tài nguyên mà không kiểm soát sẽ tạo đường vòng.

### 3.2. Chọn chủ thể và phạm vi đếm

Một khóa đếm thường có dạng logic:

```text
(tenant, feature, scope_type, scope_id, metric, window, policy_version)
```

Ví dụ: đếm số lần phát hành của một nhân viên, tổng giá trị phát hành của một tổ chức, hoặc số mã dành cho cùng người nhận trong một chiến dịch.

| Phạm vi | Phát hiện được | Giới hạn cần nhớ |
|---|---|---|
| Tài khoản thực hiện | Một tài khoản tăng tốc hoặc bị chiếm quyền | Kẻ tấn công có thể chia hoạt động qua nhiều tài khoản. |
| Người nhận hoặc đối tượng đích | Nhiều tài khoản cùng nhắm vào một mục tiêu | Khóa đích cần được xác định và chuẩn hóa đúng nghiệp vụ. |
| Chiến dịch hoặc tài nguyên | Rút cạn một nguồn giá trị cụ thể | Có thể ảnh hưởng nhiều người hợp lệ cùng dùng tài nguyên. |
| Tổ chức | Lạm dụng phân tán trong cùng tổ chức | Cần kiểm soát công bằng giữa các thành viên. |
| IP hoặc thiết bị | Tín hiệu bổ sung về nguồn truy cập | IP dùng chung, proxy và thay thiết bị làm giảm độ tin cậy. |

Không lấy `tenantId`, vai trò hoặc danh tính thực hiện do client gửi lên làm nguồn sự thật. Backend xác định chúng từ ngữ cảnh xác thực và kiểm tra quan hệ với tài nguyên. IP từ header chuyển tiếp chỉ có ý nghĩa nếu header đó được xử lý qua chuỗi proxy tin cậy.

Người nhận cũng cần có định danh ổn định. Ưu tiên ID nội bộ nếu đã xác thực được người nhận. Nếu dùng địa chỉ liên hệ, áp dụng quy tắc chuẩn hóa do sản phẩm xác định; không tùy tiện gộp các địa chỉ khác nhau chỉ vì một nhà cung cấp có quy tắc riêng.

### 3.3. Chọn sự kiện được tính

Ba loại số liệu sau phục vụ ba câu hỏi khác nhau:

- **Lần thử:** có bao nhiêu nỗ lực gọi tính năng, kể cả thất bại? Hữu ích để phát hiện dò mã hoặc quấy rối.
- **Thao tác đã được tiếp nhận:** có bao nhiêu công việc đã được cấp quyền thực hiện, kể cả đang chờ xử lý? Hữu ích để ngăn xếp hàng vượt hạn mức.
- **Tác động đã hoàn tất:** có bao nhiêu mã thực sự được phát hành, thông báo thực sự được gửi hoặc giá trị thực sự được chuyển? Hữu ích để đo thiệt hại và kết quả.

Nếu chỉ đếm khi công việc hoàn tất, hàng nghìn công việc đang chờ có thể cùng vượt cổng trước khi bộ đếm thay đổi. Với giới hạn trên thao tác được tiếp nhận, phải tính cả phần đang giữ chỗ.

Retry cùng một thao tác không được tiêu thụ thêm hạn mức tác động nghiệp vụ. Tuy nhiên, từng request retry vẫn có thể được tính vào bộ đếm lưu lượng hoặc lần thử để bảo vệ hệ thống. Hai bộ đếm cần tên và chính sách riêng.

## 4. Mô hình hóa ngưỡng rõ ràng

Với một phạm vi `s`, thời điểm `t` và cửa sổ dài `W`, gọi:

```text
U(s, t, W) = tổng chi phí của các thao tác thuộc cửa sổ đang có hiệu lực
             bao gồm phần đã hoàn tất và phần đang giữ chỗ còn hợp lệ

Cho phép tiếp nhận nếu: U(s, t, W) + cost(request) <= limit(s, W)
```

Trong ví dụ cửa sổ trượt, có thể quy ước các sự kiện được tiếp nhận tại thời điểm `t_e` thỏa `t - W < t_e <= t`. Phải thống nhất quy ước biên này giữa lưu trữ, tính toán và kiểm thử; `U` chưa bao gồm yêu cầu đang được xét.

`cost(request)` không nhất thiết bằng 1:

- Đếm thao tác: một lần phát hành có chi phí 1.
- Đếm số người nhận: một lô phát hành có chi phí bằng số người nhận hợp lệ được chấp nhận.
- Đếm giá trị: chi phí bằng tổng giá trị do server tính từ mệnh giá và số lượng được phép.
- Đếm tài nguyên: một tác vụ có chi phí ước lượng theo số dòng hoặc dung lượng được xử lý.

Không tin `totalAmount`, `recipientCount` hoặc `riskCost` do client tự khai. Với một lô 100 người nhận, giới hạn request bằng 1 mà không tính kích thước lô sẽ bỏ sót tác động thực tế. Nếu cho phép chấp nhận một phần lô, phản hồi phải nêu rõ phần nào được tiếp nhận và lưu kết quả theo từng mục để retry không tạo thêm tác động.

Với giá trị tiền tệ, dùng đơn vị nguyên phù hợp hoặc kiểu thập phân chính xác theo miền nghiệp vụ. Không cộng nhiều loại tiền thành một số không có đơn vị. Nếu có quy đổi, phải xác định nguồn tỷ giá, thời điểm và cách làm tròn. Cần kiểm tra tràn số khi cộng hoặc nhân chi phí.

### Ví dụ chính sách minh họa

Các giá trị sau chỉ để phân tích thiết kế, không phải khuyến nghị áp dụng cho mọi hệ thống:

| Phạm vi | Chỉ số | Ngưỡng minh họa | Cửa sổ và phản ứng |
|---|---|---|---|
| Nhân viên | Số thao tác phát hành được tiếp nhận | 5 | 10 phút trượt; từ chối tạm thời khi vượt. |
| Nhân viên | Số thao tác phát hành được tiếp nhận | 30 | 24 giờ trượt; xử lý hành vi kéo dài. |
| Chiến dịch + người nhận | Số mã được tiếp nhận phát hành | 1 | 7 ngày trượt; tránh nhiều người cùng cấp mã cho một đích. |
| Tổ chức | Tổng giá trị được tiếp nhận phát hành | Một trần vận hành cấu hình riêng | Ngày UTC; chuyển sang xét duyệt khi vượt. |
| Chiến dịch | Ngân sách còn lại sau giữ chỗ | Không được âm | Quy tắc nghiệp vụ bắt buộc; không có ngoại lệ do xác minh rủi ro. |

Các điều kiện áp dụng đồng thời. Còn hạn mức nhân viên không có nghĩa là được bỏ qua ngưỡng người nhận hoặc ngân sách chiến dịch.

Đúng tại ngưỡng vẫn được phép nếu chính sách dùng `<=`: đã dùng 4, chi phí mới 1, giới hạn 5 thì được tiếp nhận; đã dùng 5 thì yêu cầu tiếp theo bị từ chối. Đừng để mô tả sản phẩm dùng một quy tắc còn code dùng quy tắc khác.

## 5. Chọn cửa sổ và cách đếm phù hợp

| Cơ chế | Đặc điểm | Lưu ý với lạm dụng nghiệp vụ |
|---|---|---|
| Cửa sổ cố định | Dễ giải thích, reset theo mốc thời gian | Có thể nhận gần hai lần hạn mức trong khoảng ngắn sát ranh giới hai cửa sổ. |
| Nhật ký cửa sổ trượt | Xét chính xác các sự kiện trong khoảng gần nhất | Chi phí lưu trữ và truy vấn tăng theo số sự kiện; cần xử lý biên và dọn dữ liệu đúng. |
| Bộ đếm trượt xấp xỉ | Giảm chi phí so với nhật ký đầy đủ | Có sai số; cần đánh giá sai số có làm lọt tác động không thể chấp nhận hay không. |
| Token bucket | Cho phép burst có kiểm soát và tốc độ bổ sung ổn định | Tham số là dung lượng và tốc độ nạp; không tự mang nghĩa giới hạn chính xác trong mọi cửa sổ trượt. |
| Giới hạn đang xử lý | Giữ số công việc đồng thời dưới một mức | Không thay thế giới hạn số lượng hoặc giá trị theo thời gian. |

Ví dụ cửa sổ cố định 5 lần mỗi 10 phút có thể nhận 5 lần ngay trước mốc reset và 5 lần ngay sau đó. Nếu mười lần trong vài giây là thiệt hại không thể chấp nhận, cách đếm này không đáp ứng yêu cầu, dù cấu hình ghi “5/10 phút”.

Có thể phối hợp cửa sổ ngắn để kiểm soát burst và cửa sổ dài để kiểm soát hành vi chậm, kéo dài. Với chi phí nhạy cảm, thêm giới hạn tổng giá trị và số người nhận duy nhất; giới hạn số thao tác đơn thuần có thể bị lách bằng cách tăng giá trị mỗi thao tác.

Hệ thống nhiều máy không nên dựa vào đồng hồ của client. Cần một cách xác định thời gian đáng tin cậy và nhất quán cho việc xét cửa sổ. Đồng hồ lệch giữa các máy, ngày UTC khác ngày kinh doanh và thời điểm xóa bộ đếm đều có thể làm thay đổi hành vi thực tế.

Việc hết cửa sổ đếm và việc hết hiệu lực của công việc giữ chỗ là hai vấn đề riêng. Một công việc hết hạn xử lý không tự chứng minh tác động bên ngoài chưa xảy ra.

## 6. Chọn ngưỡng từ tác động và dữ liệu

Một quy trình thực dụng:

1. **Xác định tổn thất cần hạn chế:** cạn ngân sách, gửi tin quấy rối, chiếm suất xử lý hay thu thập dữ liệu hàng loạt.
2. **Xác định mức sử dụng hợp lệ:** tách người dùng thông thường, khách hàng lớn, tích hợp được phê duyệt và tác vụ vận hành.
3. **Quan sát phân bố:** xem số lượng, giá trị, độ tập trung vào đối tượng đích và thời điểm hoạt động; tránh chỉ dùng trung bình.
4. **Chọn phản ứng theo chi phí sai lầm:** thao tác giá trị cao có thể cần duyệt; thao tác ít rủi ro có thể trì hoãn hoặc yêu cầu xác minh.
5. **Thử bằng chế độ quan sát:** ghi nhận quyết định giả định trên lưu lượng thực, đối chiếu các trường hợp hợp lệ và bất thường trước khi cưỡng chế.
6. **Triển khai có giới hạn:** theo dõi nhóm áp dụng, chặn nhầm và cách khôi phục khi chính sách có vấn đề.

Không lấy một phân vị cao rồi kết luận tự động rằng mọi hành vi phía trên đều là tấn công. Phân bố có thể chứa sẵn lạm dụng; khách hàng lớn hợp lệ cũng có thể nằm ở phần đuôi. Ngưỡng cần gắn với tổn thất có thể chấp nhận và khả năng hỗ trợ người dùng.

Ví dụ, giả sử 100.000 thao tác/ngày có 200 thao tác lạm dụng. Chính sách phát hiện 80% trong số đó sẽ chặn 160 thao tác xấu. Nếu đồng thời chặn nhầm 0,5% trong 99.800 thao tác hợp lệ, nó tạo khoảng 499 lượt chặn nhầm. Khi ấy, nhiều lượt bị chặn là hợp lệ dù tỷ lệ phát hiện 80% nghe có vẻ tốt.

Ví dụ này nhấn mạnh sự cần thiết của dữ liệu có nhãn, xem xét thủ công và cơ chế khắc phục. Trong thực tế, tỷ lệ phát hiện không thể suy ra chỉ từ số lượt bị chặn nếu chưa biết các trường hợp lọt qua.

## 7. Đặt quyết định tại nơi tạo tác động nghiệp vụ

Một luồng xử lý phù hợp có thể được tổ chức như sau:

```text
Nhận yêu cầu
  -> kiểm tra định dạng và giới hạn lưu lượng cơ bản
  -> xác thực, xác định tenant và tài nguyên từ dữ liệu tin cậy
  -> kiểm tra quyền theo đối tượng
  -> nhận diện thao tác bằng idempotency key và nội dung chuẩn hóa
  -> nếu thao tác đã tồn tại: trả kết quả/trạng thái được phép xem
  -> với thao tác mới: kiểm tra trạng thái, invariant và mọi ngưỡng liên quan
  -> giữ chỗ hạn mức và tạo thao tác theo cùng ranh giới nhất quán
  -> thực hiện tác động hoặc ghi công việc bền vững để xử lý sau
  -> hoàn tất hoặc đối soát kết quả
```

Kiểm tra sớm giúp tiết kiệm tài nguyên, nhưng trạng thái có thể thay đổi sau khi kiểm tra. Quyền phụ thuộc trạng thái, ngân sách và các điều kiện cạnh tranh phải được bảo vệ hoặc kiểm tra lại tại thời điểm ghi nhận thao tác. Không coi một kết quả đọc cũ là bằng chứng rằng giao dịch hiện tại vẫn hợp lệ.

Khi retry thao tác đã có, vẫn xác thực và kiểm tra quyền xem kết quả. Không trả dữ liệu đã lưu chỉ vì client đoán đúng idempotency key. Nếu chính sách quyền đã thay đổi, xử lý theo quy tắc truy cập hiện tại mà không tạo lại tác động nghiệp vụ.

### Tính chi phí trong Java

Đoạn Java sau chỉ minh họa phép so sánh cho một chỉ số nguyên; nó không thực hiện giữ chỗ hay giải quyết cạnh tranh:

```java
static boolean fits(long used, long cost, long limit) {
    if (used < 0 || cost <= 0 || limit < 0) {
        throw new IllegalArgumentException("Invalid usage or limit");
    }

    // So sánh bằng phép trừ để tránh tràn số ở used + cost.
    return cost <= limit && used <= limit - cost;
}
```

`fits(4, 1, 5)` trả về `true`; `fits(5, 1, 5)` trả về `false`. Đầu vào `cost` phải được tính từ dữ liệu nghiệp vụ đã xác minh. Với nhiều chỉ số, tất cả điều kiện phải thỏa và việc ghi nhận phải theo đúng ngữ nghĩa nguyên tử đã chọn.

Sai lầm phổ biến là đọc `used`, gọi hàm này rồi tăng bộ đếm bằng một thao tác riêng. Hàm tính đúng nhưng toàn bộ cơ chế vẫn có thể sai.

## 8. Chống vượt ngưỡng do xử lý đồng thời

Giả sử đã dùng 4/5 lượt. Hai request cùng đọc giá trị 4, cùng quyết định rằng `4 + 1 <= 5`, rồi cùng tạo mã. Kết quả là 6 mã dù không request nào thấy mình vượt ngưỡng.

Việc **kiểm tra và giữ chỗ** phải có một điểm quyết định nhất quán. Với một thiết kế dùng chung cơ sở dữ liệu cho trạng thái nghiệp vụ và hạn mức, luồng giả mã có thể là:

```text
BEGIN TRANSACTION

  Phân xử quyền sở hữu idempotency key trong đúng tenant/actor/feature.
  Nếu đã có thao tác cùng nội dung: trả trạng thái/kết quả hiện có.
  Nếu cùng key nhưng khác nội dung: từ chối xung đột.

  Khóa/kiểm tra phiên bản các trạng thái nghiệp vụ cần bảo vệ.
  Kiểm tra lại quyền, trạng thái chiến dịch và ngân sách khả dụng.

  Xác định và khóa các phạm vi hạn mức theo thứ tự nhất quán.
  Đọc lượng sử dụng và phần giữ chỗ còn hiệu lực tại thời điểm xét.
  Kiểm tra mọi ngưỡng, bao gồm chi phí của toàn bộ thao tác mới.

  Nếu không đạt: không tạo thao tác và không giữ chỗ hạn mức nghiệp vụ.
  Nếu đạt:
    Ghi nhận giữ chỗ cho mọi ngưỡng áp dụng.
    Giữ chỗ ngân sách theo quy tắc nghiệp vụ.
    Tạo operation duy nhất gắn với idempotency key.
    Tạo bản ghi công việc bền vững/outbox nếu cần xử lý bất đồng bộ.

COMMIT
```

Đây là giả mã về hợp đồng xử lý, không phải SQL có thể chạy nguyên văn. Triển khai thực tế cần xử lý cả trường hợp chưa có bản ghi bộ đếm hoặc idempotency key. Khóa một dòng bằng truy vấn đọc không tự khóa được một dòng chưa tồn tại; cần cơ chế tạo duy nhất, ràng buộc duy nhất, khóa phù hợp hoặc retry giao dịch khi cạnh tranh.

Thứ tự khóa phải nhất quán giữa các luồng dùng chung tài nguyên, không chỉ trong một hàm. Khi có deadlock hoặc xung đột phiên bản, retry giao dịch nội bộ phải giữ nguyên danh tính thao tác và không lặp tác động bên ngoài.

Nếu một ngưỡng không đạt, không được để lại phần giữ chỗ ở các ngưỡng đã kiểm tra trước đó. Bộ đếm lần thử có thể vẫn tăng theo chính sách riêng, nhưng cần phân biệt với hạn mức của thao tác được tiếp nhận.

### Khi bộ đếm và dữ liệu nghiệp vụ ở hai hệ thống

Một thao tác nguyên tử trên bộ đếm phân tán chỉ bảo đảm tính nguyên tử trong phạm vi mà công cụ đó cung cấp. Nó không tự biến việc cập nhật cơ sở dữ liệu nghiệp vụ thành cùng một giao dịch. Tương tự, cập nhật nhiều khóa ở nhiều phân vùng không tự có tính nguyên tử chỉ vì từng khóa cập nhật nguyên tử.

Các lựa chọn cần được đánh giá rõ:

- Đưa quyết định hạn mức bắt buộc về cùng ranh giới giao dịch với thao tác nghiệp vụ.
- Dùng giữ chỗ bền vững và state machine để điều phối, phục hồi và đối soát giữa các hệ thống.
- Chấp nhận độ vượt ngưỡng có giới hạn cho một kiểm soát mềm, sau khi định lượng tác động và vẫn giữ invariant bắt buộc ở nơi nhất quán.

Không dùng bộ đếm đồng bộ trễ để bảo đảm ngân sách không âm. Một cổng bảo vệ lưu lượng có thể chấp nhận sai số; một quy tắc tài chính bắt buộc cần ranh giới bảo đảm phù hợp.

## 9. Idempotency, giữ chỗ và lỗi không xác định

Một khóa idempotency cần được ràng buộc ít nhất với phạm vi tổ chức, chủ thể và tính năng theo thiết kế API. Lưu thêm dấu vân tay của nội dung nghiệp vụ đã chuẩn hóa, bao gồm tài nguyên, người nhận, mệnh giá và các trường ảnh hưởng tác động. Không chỉ băm toàn bộ JSON thô nếu khác thứ tự trường có thể làm thay đổi dấu vân tay dù ý nghĩa không đổi.

- Cùng khóa, cùng nội dung, đang xử lý: trả trạng thái hiện tại theo hợp đồng API.
- Cùng khóa, cùng nội dung, đã hoàn tất: trả kết quả được phép xem; không giữ chỗ lần nữa.
- Cùng khóa, khác nội dung: từ chối xung đột; không biến khóa cũ thành thao tác mới.
- Khóa mới, cùng mục đích lạm dụng: vẫn chịu các ngưỡng theo chủ thể, đối tượng và giá trị.

Idempotency ngăn lặp một thao tác; nó không ngăn kẻ tấn công tạo nhiều thao tác mới.

### Vòng đời giữ chỗ

```text
RESERVED -> PROCESSING -> SUCCEEDED
                 |
                 +----> FAILED_CONFIRMED
                 |
                 +----> UNKNOWN -> đối soát -> SUCCEEDED hoặc FAILED_CONFIRMED
```

| Tình huống | Cách xử lý hạn mức |
|---|---|
| Đã tiếp nhận, công việc còn đang chờ | Giữ phần đã đặt chỗ để công việc khác không vượt cổng. |
| Tác động đã hoàn tất | Chuyển phần giữ chỗ sang phần đã sử dụng, không cộng thêm lần thứ hai. |
| Đã xác nhận không có tác động | Có thể hoàn phần hạn mức tác động theo chính sách; số lần thử vẫn được giữ nếu cần. |
| Mất kết nối hoặc timeout sau khi gửi yêu cầu ra ngoài | Giữ trạng thái chưa rõ và đối soát; không tự kết luận thất bại. |
| Worker nhận lại cùng một công việc | Khử trùng lặp theo operation/event ID; không tạo thêm mã hoặc trừ hạn mức lần nữa. |

Quy tắc hoàn hạn mức phụ thuộc vào điều đang đo. Nếu ngưỡng giới hạn số lần tiếp nhận công việc gây tốn tài nguyên, một công việc thất bại vẫn có thể phải được tính. Nếu ngưỡng giới hạn tác động thành công, có thể giải phóng sau khi chứng minh tác động chưa xảy ra.

Không tự động hoàn toàn bộ hạn mức chỉ vì hết timeout. Kẻ tấn công có thể cố tình làm timeout để lấy lại hạn mức trong khi tác động thực tế vẫn xảy ra. Lease hết hạn chỉ cho phép xem xét thu hồi quyền xử lý; cần ngăn worker cũ tiếp tục tạo tác động và đối soát trạng thái bên ngoài trước khi kết luận có thể hoàn.

Outbox giúp lưu bền vững công việc cùng giao dịch nghiệp vụ, nhưng bản thân nó không bảo đảm tác động bên ngoài chỉ xảy ra một lần. Bên nhận hoặc nhà cung cấp cần hỗ trợ khử trùng lặp/idempotency, hoặc hệ thống phải có cơ chế đối soát phù hợp.

Thời gian lưu bản ghi idempotency phải đủ cho vòng đời retry và công việc bất đồng bộ. Sau khi bản ghi hết hạn, các ràng buộc nghiệp vụ bền vững vẫn cần ngăn tác động trùng mà sản phẩm không cho phép.

## 10. Chọn phản ứng khi chạm ngưỡng

Không phải mọi ngưỡng đều nên dẫn tới khóa tài khoản:

| Phản ứng | Khi có thể phù hợp | Điều kiện cần giữ |
|---|---|---|
| Ghi nhận để quan sát | Chính sách mới, chưa đủ bằng chứng | Phân biệt rõ chưa cưỡng chế với đang được bảo vệ. |
| Làm chậm hoặc xếp hàng | Tài nguyên có thể điều tiết theo thời gian | Hàng đợi phải có giới hạn và công việc được tiếp nhận phải được tính. |
| Từ chối tạm thời | Vượt số lượng/tốc độ có cửa sổ rõ ràng | Hướng dẫn retry phù hợp; retry không làm phát sinh tác động trùng. |
| Xác minh bổ sung | Rủi ro tăng nhưng chưa đủ kết luận lạm dụng | Xác minh phải gắn đúng thao tác và không thay thế quyền hoặc invariant. |
| Chuyển sang phê duyệt | Thao tác giá trị cao, cần người đánh giá | Chờ duyệt không tạo tác động trước; bản duyệt không cho phép sửa payload tùy ý. |
| Đình chỉ tính năng có mục tiêu | Có bằng chứng mạnh hoặc đang gây thiệt hại | Phạm vi đình chỉ và cơ chế khôi phục phải rõ ràng. |

Một thử thách xác minh cần gắn với chủ thể, tính năng, tài nguyên, nội dung thao tác, thời hạn và cách tiêu thụ kết quả. Nếu chỉ cấp một cờ “đã xác minh” có thể dùng lại vô hạn, kẻ tấn công sẽ xác minh một lần rồi tiếp tục lạm dụng.

Với API HTTP, `429 Too Many Requests` phù hợp với từ chối do tần suất hoặc số lượng yêu cầu theo thời gian. Không gán mọi quyết định rủi ro thành 429; yêu cầu phê duyệt, thiếu quyền và xung đột trạng thái cần hợp đồng phản hồi riêng. `Retry-After`, nếu cung cấp, nên phản ánh thời điểm có thể thử lại theo chính sách và không hứa chắc thành công khi nhiều điều kiện vẫn còn áp dụng.

Không trả chi tiết điểm rủi ro hoặc toàn bộ ngưỡng nội bộ cho client. Người dùng vẫn cần thông báo có ích như thời gian có thể thử lại hoặc cách yêu cầu xét duyệt. Nội bộ cần mã lý do ổn định để vận hành và hỗ trợ.

Với yêu cầu bị từ chối trước khi tiếp nhận, phải quy định rõ có lưu kết quả từ chối theo idempotency key hay không. Nếu không lưu lâu dài, client có thể dùng lại khóa cho cùng nội dung sau khi được phép thử lại. Nếu có lưu kết quả từ chối, tài liệu API phải nêu cách bắt đầu lần thử mới; tránh để client lặp mãi một kết quả đã được ghi nhớ.

## 11. Những cách lách ngưỡng cần dự liệu

| Cách lạm dụng | Vì sao ngưỡng đơn giản bỏ sót | Hướng kiểm soát |
|---|---|---|
| Chia qua nhiều tài khoản | Mỗi tài khoản đều dưới giới hạn | Kết hợp theo người nhận, tài nguyên và tổ chức; dùng tín hiệu liên quan khi có căn cứ. |
| Đổi IP hoặc đi qua proxy | Bộ đếm chỉ gắn với nguồn mạng | Dựa thêm vào danh tính nghiệp vụ; không coi IP là danh tính duy nhất. |
| Nhắm vào cùng một nạn nhân | Nhiều người gửi hợp lệ về mặt quyền | Đặt ngưỡng nhận theo đối tượng đích và phát hiện tập trung bất thường. |
| Chia một khoản lớn thành nhiều khoản nhỏ | Mỗi thao tác dưới trần giá trị | Giới hạn cả tổng giá trị, số lượng và khoảng thời gian. |
| Gộp nhiều phần tử trong một lô | Một request gây nhiều tác động | Tính chi phí theo nội dung lô và giới hạn kích thước lô. |
| Gửi đồng thời | Nhiều lần đọc thấy cùng lượng còn lại | Kiểm tra và giữ chỗ nguyên tử trên mọi phạm vi liên quan. |
| Gửi sát thời điểm reset | Hai cửa sổ độc lập vẫn nhận burst lớn | Dùng cửa sổ phù hợp hoặc phối hợp nhiều khoảng thời gian. |
| Retry sau timeout | Tạo thao tác mới trong khi thao tác cũ đã xảy ra | Idempotency, trạng thái chưa rõ và đối soát. |
| Chuyển API hoặc đường quản trị | Chính sách chỉ nằm ở một controller | Thực thi tại dịch vụ nghiệp vụ chung; ngoại lệ phải có quyền và lưu vết. |
| Giả định danh tenant/đối tượng | Khóa đếm do client chọn sai phạm vi | Xác định chủ thể từ server và kiểm tra quyền theo đối tượng. |
| Cố tình gây lỗi để được hoàn hạn mức | Mọi lỗi đều được coi là chưa có tác động | Chỉ hoàn khi đáp ứng điều kiện đã xác định cho loại hạn mức đó. |
| Hoạt động chậm trong thời gian dài | Không bao giờ vượt cửa sổ ngắn | Bổ sung cửa sổ dài, chỉ số tổng giá trị và độ tập trung vào đích. |

Không có một ngưỡng đơn lẻ bao phủ mọi kiểu lạm dụng. Phối hợp nhiều phạm vi phải đi kèm đánh giá chặn nhầm; không tự động coi mọi người dùng chung IP, thiết bị hoặc tổ chức là cùng một kẻ tấn công.

## 12. Vận hành an toàn khi có sự cố hoặc thay đổi chính sách

### 12.1. Khi thành phần đánh giá ngưỡng không hoạt động

Chọn hành vi theo từng tính năng và hậu quả:

- Với thao tác có thể gây mất giá trị không thể thu hồi, có thể tạm ngừng tiếp nhận hoặc đưa vào trạng thái chờ xét duyệt.
- Với tính năng ít tác động hơn, có thể dùng cơ chế dự phòng với giới hạn cục bộ chặt hơn và ghi nhận để đối soát.
- Không coi “không đọc được bộ đếm” là “đã dùng bằng 0”.

Giới hạn cục bộ trên mỗi máy không bằng giới hạn toàn hệ thống. Nếu có N máy và mỗi máy cho phép L thao tác độc lập, tổng có thể lên tới N × L. Việc chấp nhận cơ chế dự phòng cần tính đến tác động cộng dồn này.

Dù chọn cách nào, lỗi dịch vụ ngưỡng không được vô hiệu hóa kiểm tra quyền, trạng thái hoặc ngân sách bắt buộc. Thao tác đang xử lý cũng cần được phân biệt với thao tác mới chưa tiếp nhận.

### 12.2. Khi sửa ngưỡng

Chính sách cần có phiên bản, phạm vi áp dụng, người phê duyệt và thời điểm có hiệu lực. Lưu phiên bản đã dùng để giải thích vì sao một quyết định xảy ra, đồng thời xác định thao tác đang chờ có cần đánh giá lại khi thực thi hay không.

Không đưa `policy_version` vào khóa rồi vô tình reset mọi lượng đã dùng mỗi lần đổi cấu hình. Nếu thay ngưỡng trong cùng kỳ đếm, cần đọc được lượng sử dụng liên quan trước đó hoặc có kế hoạch chuyển đổi rõ ràng. Giảm giới hạn xuống dưới lượng đã dùng thường có nghĩa là ngừng tiếp nhận thêm, không tự hủy tác động đã hoàn tất.

Ngoại lệ cho khách hàng lớn hoặc vận hành phải được giới hạn phạm vi, có thời hạn và có lưu vết. Không dùng một header do client tự đặt hoặc một cờ không hết hạn để bỏ qua toàn bộ kiểm soát.

## 13. Quan sát để biết ngưỡng có tác dụng

Một quyết định nên có dữ liệu đủ để giải thích và đối soát:

- Mã thao tác hoặc correlation ID.
- Tính năng, tenant và phạm vi kiểm soát.
- Phiên bản chính sách, loại cửa sổ và thời điểm đánh giá.
- Quyết định: cho phép, từ chối, trì hoãn, xác minh hoặc chờ duyệt.
- Mã lý do và chỉ số quyết định liên quan.
- Trạng thái giữ chỗ, hoàn tất, hoàn hạn mức hoặc chưa rõ kết quả.

Hạn chế ghi thông tin cá nhân; không ghi token, OTP hoặc toàn bộ nội dung nhạy cảm. Định danh giả hoặc giá trị băm vẫn có thể là dữ liệu nhạy cảm. Với không gian đầu vào lớn, tránh tạo nhãn metrics theo từng email, IP hoặc người nhận; dùng log có kiểm soát truy cập cho điều tra chi tiết, metrics tổng hợp cho giám sát.

Các chỉ số hữu ích gồm tỷ lệ bị can thiệp theo nhóm người dùng, số trường hợp hỗ trợ xác nhận chặn nhầm, giá trị lạm dụng đã xác minh, thời gian chờ duyệt và số thao tác `UNKNOWN` tồn đọng. Theo dõi cả mức vượt ngưỡng thực tế khi có cạnh tranh, số giữ chỗ không được giải quyết và tuổi của công việc đang treo.

Tỷ lệ từ chối tăng không tự chứng minh kiểm soát tốt hơn. Nó có thể do tấn công tăng, do cấu hình quá chặt hoặc do một nhóm khách hàng hợp lệ bắt đầu chiến dịch lớn. Cần đối chiếu với kết quả nghiệp vụ và mẫu trường hợp có đánh giá đáng tin cậy.

## 14. Kiểm thử theo tình huống tấn công logic

### 14.1. Kiểm thử biên và chi phí

| Tình huống | Kết quả cần xác minh |
|---|---|
| Đã dùng 4/5, thêm chi phí 1 | Được tiếp nhận và lượng sử dụng trở thành 5. |
| Đã dùng 5/5, thêm chi phí 1 | Bị từ chối, không có mã mới hoặc giữ chỗ nghiệp vụ mới. |
| Đã dùng 3/5, gửi lô chi phí 3 | Không nhận toàn bộ lô nếu vượt; nếu hỗ trợ nhận một phần thì phải kiểm tra đúng hợp đồng từng mục. |
| Chi phí âm, bằng 0 hoặc phép nhân số lượng gây tràn | Bị xử lý theo xác thực đầu vào; không làm giảm bộ đếm. |
| Sự kiện đúng tại biên cửa sổ | Được tính hoặc loại đúng theo quy ước đã công bố. |
| Đổi ngưỡng giữa kỳ | Không reset lượng đã dùng ngoài chủ đích; quyết định có thể truy được phiên bản. |

### 14.2. Kiểm thử đồng thời

Cho hạn mức 5, lượng dùng ban đầu 0 và 20 thao tác khác nhau cùng cạnh tranh trong một phạm vi. Đồng bộ thời điểm bắt đầu để tăng khả năng các yêu cầu thực sự chạy đồng thời. Trong điều kiện mọi kiểm tra khác đều đạt, không có lỗi hạ tầng và chính sách từ chối ngay khi đầy:

- Đúng 5 thao tác được tiếp nhận.
- 15 thao tác còn lại không tạo tác động hoặc giữ chỗ nghiệp vụ.
- Tổng phần đã dùng và phần giữ chỗ không vượt 5.
- Nếu mỗi thao tác tạo một outbox event, chỉ có 5 event nghiệp vụ tương ứng.

Không chỉ kiểm tra mã HTTP; cần kiểm tra trạng thái bền vững và tác động cuối cùng. Kiểm thử trên cơ chế lưu trữ thực tế cần bảo vệ, vì mock một bộ đếm thường không bộc lộ lỗi cạnh tranh.

Lặp lại với hai phạm vi: nhân viên còn hạn mức nhưng người nhận đã đầy. Sau từ chối, không được mất hạn mức nghiệp vụ ở nhân viên. Khi kiểm thử deadlock hoặc retry giao dịch, kiểm tra rằng thao tác cuối cùng vẫn chỉ được ghi nhận một lần.

### 14.3. Kiểm thử idempotency và phục hồi

1. Gửi đồng thời 20 request cùng khóa và cùng nội dung: tối đa một operation và một tác động; các phản hồi còn lại tuân theo hợp đồng đang xử lý hoặc kết quả đã có.
2. Dùng lại khóa nhưng sửa người nhận hoặc mệnh giá: xung đột, không tạo thêm mã.
3. Mất phản hồi sau commit rồi retry: trả trạng thái/kết quả cũ, không tiêu thụ thêm hạn mức tác động.
4. Worker dừng sau khi tác động bên ngoài xảy ra nhưng trước khi lưu kết quả: công việc không được tự hoàn hạn mức hoặc phát hành lại; khử trùng lặp hoặc đối soát giải quyết kết quả.
5. Worker nhận lại event đã hoàn tất: không tạo thêm tác động và không chuyển giữ chỗ sang đã dùng lần thứ hai.
6. Hết lease khi worker cũ còn chạy: xác minh cơ chế ngăn xử lý trùng và quy tắc đối soát trước khi hoàn.

### 14.4. Kiểm thử quyền và đường vòng

- Đổi `tenantId`, `campaignId` hoặc người nhận sang đối tượng ngoài quyền: bị từ chối trước khi tạo tác động.
- Gọi cùng tính năng qua API khác, tác vụ nền và giao diện quản trị: cùng chính sách, trừ ngoại lệ được cấp rõ ràng.
- Phân tán qua nhiều tài khoản đến cùng người nhận: ngưỡng theo người nhận vẫn có hiệu lực.
- Gửi trước và sau mốc reset: kết quả phù hợp với thuật toán cửa sổ đã chọn.
- Dùng hàng loạt khóa idempotency mới: vẫn chịu ngưỡng tổng theo chủ thể và đối tượng.
- Dừng thành phần đánh giá ngưỡng: hành vi dự phòng đúng chính sách, không bỏ qua invariant.

Các kiểm thử nên mô tả điều không được phép xảy ra trong trạng thái nghiệp vụ, ví dụ “không có mã thứ sáu được tiếp nhận” hoặc “không có hai tác động cho một operation”, thay vì chỉ xác nhận một nhánh code đã chạy.

## 15. Bảng tự kiểm khi thiết kế

Trước khi đưa một ngưỡng vào sử dụng, cần trả lời được:

1. Tính năng nào được bảo vệ, tổn thất cụ thể là gì và mọi đường gọi đã được bao phủ chưa?
2. Đang đếm lần thử, lần tiếp nhận, tác động hoàn tất, tổng giá trị hay số công việc đồng thời?
3. Danh tính và phạm vi được xác định từ nguồn tin cậy nào?
4. Cửa sổ, múi giờ, biên thời gian và đơn vị chi phí đã rõ chưa?
5. Mọi ngưỡng liên quan có được kiểm tra và giữ chỗ theo ranh giới nhất quán không?
6. Retry, xử lý lô và giao việc lại có gây tiêu thụ hoặc tác động trùng không?
7. Timeout, lỗi chưa rõ kết quả và việc hoàn hạn mức được giải quyết thế nào?
8. Phản ứng khi chạm ngưỡng có phù hợp với mức rủi ro và người dùng hợp lệ không?
9. Thay chính sách, ngoại lệ và sự cố thành phần có làm reset hoặc vô hiệu hóa bảo vệ không?
10. Có dữ liệu để đo chặn nhầm, lạm dụng lọt qua và trạng thái giữ chỗ tồn đọng không?

Một feature abuse threshold có hiệu quả khi vừa giới hạn được tác động lạm dụng, vừa giữ đúng quyền, trạng thái và tính nhất quán của thao tác nghiệp vụ. Con số giới hạn chỉ là một phần của thiết kế; ý nghĩa sự kiện, ranh giới giao dịch và vòng đời thao tác quyết định con số đó có thực sự được thực thi hay không.
