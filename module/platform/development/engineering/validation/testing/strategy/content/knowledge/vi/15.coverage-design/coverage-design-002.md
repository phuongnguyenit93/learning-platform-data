# Xác định tiêu chí bao phủ theo chức năng, luồng và trạng thái

Tiêu chí bao phủ cho biết nhóm đã kiểm chứng đến đâu đối với những phần quan trọng của sản phẩm. Khi thiết kế kiểm thử, chỉ đếm số trường hợp đã chạy hoặc tỷ lệ bao phủ mã nguồn là chưa đủ. Nhóm cần xác định rõ những chức năng nào đã được kiểm tra, những hành trình nghiệp vụ nào đã được thực hiện và những trạng thái cùng chuyển tiếp nào đã được xác minh.

Ba góc nhìn này bổ sung cho nhau:

- **Bao phủ chức năng** cho biết các khả năng và quy tắc nghiệp vụ của sản phẩm đã được kiểm tra đến mức nào.
- **Bao phủ luồng** cho biết các hành trình và chuỗi hoạt động phối hợp giữa người dùng, dịch vụ hoặc hệ thống đã được kiểm chứng ra sao.
- **Bao phủ trạng thái** cho biết các trạng thái có thể có của đối tượng và những chuyển tiếp giữa chúng đã được kiểm tra đến đâu.

Một chức năng có thể được kiểm tra riêng nhưng chưa được kiểm tra trong hành trình thực tế. Một hành trình có thể hoàn tất thành công nhưng chưa kiểm tra các trạng thái lỗi, hủy hoặc phục hồi. Một trạng thái có thể được tạo ra nhưng chưa xác minh các cách chuyển vào và chuyển ra. Vì vậy, chiến lược kiểm thử cần định nghĩa tiêu chí cho cả ba góc nhìn, liên kết chúng với rủi ro và nêu rõ giới hạn của bằng chứng.

## 1. Bao phủ có ý nghĩa gì?

Bao phủ là mức độ mà một tập hợp kiểm thử đã chạm đến những đối tượng, hành vi, điều kiện hoặc rủi ro được xác định trong phạm vi. Đối tượng được bao phủ cần được định nghĩa trước. Nếu không có danh sách hoặc mô hình tham chiếu, một tỷ lệ bao phủ không có mẫu số rõ ràng và khó diễn giải.

Ví dụ, câu “đã bao phủ 90% chức năng” chỉ có ý nghĩa khi nhóm biết:

- Tổng số chức năng được tính là bao nhiêu?
- Chức năng được phân rã ở mức nào?
- Mỗi chức năng được coi là bao phủ khi có ít nhất một kiểm thử hay phải xác minh các quy tắc và nhánh quan trọng?
- Các chức năng ngoài phạm vi có được loại khỏi mẫu số không?
- Bằng chứng được lấy từ kiểm thử nào và ở phiên bản nào?

Một tiêu chí bao phủ hữu ích cần có:

1. **Đối tượng bao phủ:** chức năng, luồng, trạng thái, chuyển tiếp, điều kiện hoặc rủi ro.
2. **Phạm vi:** phần sản phẩm, phiên bản, vai trò và cấu hình liên quan.
3. **Điều kiện được tính là bao phủ:** bằng chứng tối thiểu cần có.
4. **Trọng số hoặc mức ưu tiên:** nếu các mục không có tầm quan trọng như nhau.
5. **Nguồn bằng chứng:** trường hợp kiểm thử, kết quả chạy, báo cáo hoặc xác nhận.
6. **Giới hạn:** phần chưa kiểm tra hoặc chỉ được kiểm tra ở mức đại diện.

Bao phủ không đồng nghĩa với chất lượng. Một bộ kiểm thử có thể đạt 100% danh sách chức năng nhưng các assertion yếu, chỉ kiểm tra đường đi thành công hoặc bỏ qua rủi ro nghiêm trọng. Mục tiêu là tạo bằng chứng có ý nghĩa về hành vi và rủi ro, không phải tối đa hóa một con số.

## 2. Xây dựng cơ sở để xác định tiêu chí bao phủ

Trước khi đặt mục tiêu, nhóm cần hiểu sản phẩm, người dùng, yêu cầu, quy tắc nghiệp vụ, kiến trúc và rủi ro. Đây là cơ sở để chọn đối tượng cần bao phủ.

Nguồn thông tin thường dùng:

- Danh sách yêu cầu, tiêu chí chấp nhận và quy tắc nghiệp vụ.
- Bản đồ chức năng và hành trình người dùng.
- Sơ đồ trạng thái hoặc mô hình vòng đời đối tượng.
- API, hợp đồng dịch vụ và luồng sự kiện.
- Kiến trúc, phụ thuộc và ranh giới tích hợp.
- Lịch sử lỗi, sự cố và phản hồi người dùng.
- Các thuộc tính chất lượng như hiệu năng, bảo mật, độ tin cậy và toàn vẹn dữ liệu.
- Thay đổi trong bản phát hành và vùng có nguy cơ hồi quy.

### Phân rã sản phẩm thành các đối tượng có thể kiểm tra

Không nên bắt đầu bằng một danh sách quá chi tiết hoặc quá thô. Hãy phân rã ở mức đủ để gắn với hành vi và bằng chứng.

Ví dụ với ứng dụng thương mại điện tử:

| Cấp độ | Ví dụ |
|---|---|
| Nhóm chức năng | Quản lý đơn hàng |
| Chức năng | Tạo đơn, sửa đơn, hủy đơn, xem đơn |
| Quy tắc | Chỉ được hủy trước khi đơn chuyển sang giao hàng |
| Luồng nghiệp vụ | Khách hàng đặt hàng và thanh toán |
| Trạng thái | Nháp, chờ thanh toán, đã thanh toán, đang giao, hoàn tất, đã hủy |
| Chuyển tiếp | Chờ thanh toán → Đã thanh toán |
| Rủi ro | Thanh toán thành công nhưng đơn vẫn ở trạng thái chờ |

Việc phân rã giúp nhóm nhìn thấy các loại bằng chứng khác nhau. Một kiểm thử chức năng có thể xác minh quy tắc hủy đơn; một kiểm thử luồng xác minh hành trình từ tạo đơn đến xác nhận; một kiểm thử trạng thái xác minh rằng đơn không thể chuyển từ đã giao sang chờ thanh toán.

### Xác định mức độ quan trọng

Không phải mọi chức năng, luồng và trạng thái đều có rủi ro như nhau. Hãy ưu tiên dựa trên:

- Tác động nếu hành vi sai.
- Khả năng xảy ra lỗi.
- Số lượng người dùng hoặc giao dịch bị ảnh hưởng.
- Độ phức tạp và số lượng phụ thuộc.
- Lịch sử lỗi và tần suất thay đổi.
- Khả năng phát hiện và phục hồi.
- Yêu cầu pháp lý, hợp đồng hoặc bảo mật.

Các tiêu chí bao phủ nên thể hiện rõ phần nào cần kiểm tra sâu, phần nào có thể kiểm tra đại diện và phần nào được chấp nhận chưa kiểm tra trong phạm vi hiện tại.

## 3. Xác định tiêu chí bao phủ chức năng

Bao phủ chức năng đo mức độ các khả năng, quy tắc và điều kiện nghiệp vụ đã được kiểm tra. Đây thường là điểm khởi đầu vì chức năng được mô tả trong yêu cầu và có thể liên kết với trường hợp kiểm thử.

Tuy nhiên, một chức năng không nên được xem là bao phủ chỉ vì có một test case mang tên tương ứng. Nhóm cần xác định những hành vi quan trọng của chức năng và điều kiện cần kiểm tra.

### Những khía cạnh cần bao phủ cho một chức năng

Tùy mức độ rủi ro, có thể xem xét:

- **Luồng bình thường:** đầu vào hợp lệ tạo ra kết quả mong đợi.
- **Điều kiện đầu vào:** trường bắt buộc, định dạng, kiểu dữ liệu và giới hạn.
- **Quy tắc nghiệp vụ:** điều kiện, công thức, chính sách và quyền.
- **Giá trị biên:** ngay dưới, tại và ngay trên giới hạn.
- **Đầu vào không hợp lệ:** hệ thống từ chối hoặc xử lý có kiểm soát.
- **Trạng thái không phù hợp:** thao tác bị từ chối khi đối tượng chưa đủ điều kiện.
- **Quyền và vai trò:** người dùng chỉ thực hiện được hành động được phép.
- **Lỗi phụ thuộc:** dịch vụ, cơ sở dữ liệu hoặc mạng không sẵn sàng.
- **Gửi lặp và đồng thời:** hệ thống tránh tạo dữ liệu trùng hoặc trạng thái mâu thuẫn.
- **Tính toàn vẹn dữ liệu:** kết quả được lưu và trao đổi chính xác.
- **Thông báo và phản hồi:** người dùng nhận được thông tin phù hợp khi thành công hoặc thất bại.

Không phải chức năng nào cũng cần mọi khía cạnh. Nhóm nên chọn dựa trên quy tắc và rủi ro của chức năng.

### Ví dụ: chức năng áp dụng mã giảm giá

Giả sử chức năng áp dụng mã giảm giá có các quy tắc:

- Mã phải tồn tại và còn hiệu lực.
- Đơn hàng phải đạt giá trị tối thiểu.
- Mã chỉ áp dụng cho một số nhóm sản phẩm.
- Mỗi tài khoản có giới hạn số lần sử dụng.
- Mức giảm không vượt quá giá trị tối đa.

Một tiêu chí bao phủ chức năng có thể yêu cầu kiểm tra:

| Nhóm quy tắc | Tình huống cần kiểm chứng |
|---|---|
| Mã và thời hạn | Mã hợp lệ, không tồn tại, đã hết hạn, chưa đến thời điểm áp dụng |
| Giá trị đơn | Thấp hơn, bằng và cao hơn ngưỡng tối thiểu |
| Phạm vi sản phẩm | Sản phẩm được áp dụng và không được áp dụng |
| Giới hạn sử dụng | Chưa dùng, còn lượt, hết lượt và hai yêu cầu đồng thời |
| Mức giảm | Giá trị thông thường, bằng mức tối đa và vượt mức tối đa |
| Kết quả dữ liệu | Tổng tiền, chi tiết giảm giá và lịch sử sử dụng được ghi đúng |

Nếu chỉ kiểm tra mã hợp lệ với một đơn hàng thông thường, chức năng mới được kiểm tra một phần. Tiêu chí cần nêu các quy tắc trọng yếu và bằng chứng tương ứng.

### Cách đo bao phủ chức năng

Có thể dùng công thức đơn giản:

\[
\text{Bao phủ chức năng} =
\frac{\text{Số chức năng đáp ứng tiêu chí bao phủ}}
{\text{Tổng số chức năng trong phạm vi}}
\times 100\%
\]

Nhóm phải định nghĩa thế nào là “đáp ứng tiêu chí”. Ví dụ, một chức năng chỉ được tính là bao phủ khi các quy tắc trọng yếu, đường đi bình thường và những điều kiện lỗi có rủi ro cao đã có bằng chứng đạt.

Nếu các chức năng có tầm quan trọng khác nhau, có thể dùng trọng số:

\[
\text{Bao phủ có trọng số} =
\frac{\sum \text{trọng số của các chức năng đã đạt}}
{\sum \text{trọng số của các chức năng trong phạm vi}}
\times 100\%
\]

Trọng số cần được thống nhất và giải thích. Không nên dùng điểm số để che khuất một chức năng quan trọng chưa được kiểm tra. Bên cạnh tỷ lệ tổng, cần hiển thị danh sách các mục rủi ro cao còn thiếu bằng chứng.

## 4. Xác định tiêu chí bao phủ luồng nghiệp vụ

Bao phủ luồng đo mức độ các hành trình và chuỗi hoạt động đã được kiểm chứng. Một luồng có thể đi qua nhiều chức năng, vai trò, dịch vụ và hệ thống bên ngoài.

Kiểm tra từng chức năng riêng lẻ không đảm bảo các bước phối hợp đúng. Lỗi có thể xuất hiện khi dữ liệu chuyển từ bước này sang bước khác, trạng thái được cập nhật không đồng bộ hoặc một bước thất bại giữa quy trình.

### Phân loại luồng cần bao phủ

Có thể chia luồng thành:

- **Luồng chính:** hành trình phổ biến để đạt mục tiêu nghiệp vụ.
- **Luồng thay thế:** cách hoàn thành mục tiêu bằng lựa chọn khác.
- **Luồng ngoại lệ:** bị từ chối do điều kiện nghiệp vụ hoặc dữ liệu.
- **Luồng lỗi:** một thành phần hoặc phụ thuộc gặp sự cố.
- **Luồng hủy hoặc quay lui:** người dùng dừng quy trình hoặc hệ thống hoàn tác.
- **Luồng phục hồi:** tiếp tục hoặc đối soát sau khi lỗi được khắc phục.
- **Luồng đồng thời:** nhiều người dùng hoặc tiến trình tác động đến cùng dữ liệu.

Với mỗi luồng, cần xác định điểm bắt đầu, điều kiện tiền đề, các bước, nhánh, điểm tích hợp, trạng thái cuối và kết quả cần xác minh.

### Ví dụ: luồng đặt hàng

Một luồng chính có thể gồm:

1. Khách hàng đăng nhập.
2. Chọn sản phẩm và thêm vào giỏ.
3. Nhập địa chỉ giao hàng.
4. Xác nhận đơn.
5. Hệ thống giữ chỗ tồn kho.
6. Thanh toán thành công.
7. Đơn được xác nhận và thông báo được gửi.

Những luồng thay thế và ngoại lệ có thể gồm:

- Sản phẩm hết hàng trước khi xác nhận.
- Mã giảm giá không hợp lệ.
- Thanh toán bị từ chối.
- Nhà cung cấp thanh toán timeout.
- Người dùng hủy trước khi thanh toán.
- Hai khách hàng cùng mua sản phẩm cuối cùng.
- Thông báo thanh toán được gửi lại.
- Dịch vụ thông báo không khả dụng sau khi đơn đã xác nhận.

### Tiêu chí bao phủ luồng

Một luồng có thể được coi là bao phủ khi:

- Các bước trọng yếu đã được thực hiện theo thứ tự hợp lệ.
- Những nhánh rủi ro cao đã được kiểm tra.
- Dữ liệu được truyền đúng giữa các bước.
- Các điểm tích hợp quan trọng có bằng chứng.
- Trạng thái cuối và các bất biến nghiệp vụ được xác minh.
- Hành vi khi lỗi, hủy hoặc phục hồi được kiểm tra theo mức rủi ro.
- Có thể truy vết kết quả về yêu cầu hoặc mục tiêu nghiệp vụ.

Không nên tính một luồng là hoàn toàn bao phủ chỉ vì đường đi chính đạt. Có thể ghi trạng thái bao phủ riêng cho luồng chính và các nhánh quan trọng.

### Cách đo bao phủ luồng

\[
\text{Bao phủ luồng} =
\frac{\text{Số luồng đáp ứng tiêu chí đã định}}
{\text{Tổng số luồng trong phạm vi}}
\times 100\%
\]

Với luồng có nhiều nhánh, có thể đo riêng số nhánh quan trọng đã kiểm tra. Mẫu số cần được xác định theo mô hình luồng hoặc danh sách nhánh đã thống nhất, không lấy mọi tổ hợp lý thuyết nếu chúng không có ý nghĩa.

## 5. Xác định tiêu chí bao phủ trạng thái

Bao phủ trạng thái đánh giá mức độ các trạng thái của đối tượng và chuyển tiếp giữa chúng đã được kiểm tra. Cách tiếp cận này đặc biệt hữu ích với quy trình có vòng đời, giao dịch, yêu cầu phê duyệt, phiên người dùng, thiết bị hoặc quy trình bất đồng bộ.

Một đối tượng thường có:

- Tập trạng thái hợp lệ.
- Các sự kiện hoặc điều kiện kích hoạt chuyển trạng thái.
- Các chuyển tiếp được phép.
- Các chuyển tiếp bị cấm.
- Điều kiện đầu vào và tác động dữ liệu.
- Quy tắc thời gian hoặc timeout.
- Hành vi khi lỗi hoặc xử lý lặp.

### Phân biệt bao phủ trạng thái và bao phủ chuyển tiếp

**Bao phủ trạng thái** cho biết mỗi trạng thái cần quan tâm đã được đưa vào kiểm thử hay chưa. Ví dụ, đơn hàng đã từng được kiểm tra ở trạng thái chờ thanh toán, đã thanh toán, đang giao, hoàn tất và đã hủy.

**Bao phủ chuyển tiếp** cho biết các đường chuyển giữa trạng thái đã được kiểm tra hay chưa. Ví dụ, đơn hàng chuyển từ chờ thanh toán sang đã thanh toán, hoặc từ chờ thanh toán sang đã hủy.

Chỉ bao phủ trạng thái chưa đủ. Một trạng thái có thể được tạo trực tiếp trong dữ liệu kiểm thử mà không xác minh được điều kiện chuyển vào nó. Ngược lại, kiểm tra một chuyển tiếp không chứng minh tất cả trạng thái và đường ra của trạng thái đó đều đúng.

### Ví dụ vòng đời đơn hàng

| Trạng thái hiện tại | Sự kiện hoặc điều kiện | Trạng thái tiếp theo | Quy tắc cần xác minh |
|---|---|---|---|
| Nháp | Khách hàng xác nhận | Chờ thanh toán | Đơn có dữ liệu hợp lệ và giá trị được chốt |
| Chờ thanh toán | Thanh toán thành công | Đã thanh toán | Giao dịch được ghi nhận đúng và không trùng |
| Chờ thanh toán | Khách hàng hủy hợp lệ | Đã hủy | Giữ chỗ tồn kho được giải phóng |
| Đã thanh toán | Đơn được bàn giao vận chuyển | Đang giao | Thông tin vận chuyển được liên kết đúng |
| Đang giao | Giao hàng thành công | Hoàn tất | Thời điểm và kết quả giao được ghi nhận |
| Đã thanh toán | Yêu cầu hoàn tiền được chấp nhận | Đang hoàn tiền | Số tiền và lý do hoàn hợp lệ |
| Đang hoàn tiền | Nhà cung cấp xác nhận hoàn tất | Đã hoàn tiền | Trạng thái và giao dịch hoàn tiền nhất quán |

Bảng cần được điều chỉnh theo quy tắc sản phẩm. Có thể tồn tại thêm trạng thái thất bại, chờ đối soát hoặc hoàn tiền một phần.

### Kiểm tra chuyển tiếp hợp lệ và không hợp lệ

Ngoài các chuyển tiếp được phép, cần kiểm tra những chuyển tiếp không được phép. Ví dụ:

- Đơn đã hủy không thể chuyển trực tiếp sang đang giao.
- Đơn đã hoàn tất không thể quay lại chờ thanh toán.
- Người dùng không có quyền không thể phê duyệt yêu cầu.
- Thanh toán đã hoàn tất không được ghi nhận thành công lần thứ hai.
- Một yêu cầu đã hết hạn không thể được chấp thuận nếu quy tắc không cho phép.

Các kiểm thử chuyển tiếp bị cấm giúp phát hiện lỗi phân quyền, cập nhật trạng thái sai thứ tự và xử lý lặp.

### Cách đo bao phủ trạng thái và chuyển tiếp

Bao phủ trạng thái:

\[
\text{Bao phủ trạng thái} =
\frac{\text{Số trạng thái đã kiểm tra}}
{\text{Tổng số trạng thái trong phạm vi}}
\times 100\%
\]

Bao phủ chuyển tiếp:

\[
\text{Bao phủ chuyển tiếp} =
\frac{\text{Số chuyển tiếp đã kiểm tra}}
{\text{Tổng số chuyển tiếp trong phạm vi}}
\times 100\%
\]

Nên theo dõi hai chỉ số riêng. Một hệ thống có thể đạt 100% trạng thái nhưng chỉ kiểm tra một phần các chuyển tiếp giữa chúng.

## 6. Mô hình hóa trạng thái trước khi thiết kế kiểm thử

Để đo bao phủ trạng thái có ý nghĩa, nhóm cần mô hình hóa vòng đời đối tượng. Có thể dùng bảng chuyển trạng thái hoặc sơ đồ trạng thái.

Một sơ đồ đơn giản cho đơn hàng:

~~~mermaid
stateDiagram-v2
    [*] --> Draft
    Draft --> PendingPayment: Confirm
    PendingPayment --> Paid: PaymentSuccess
    PendingPayment --> Cancelled: Cancel
    PendingPayment --> PaymentReview: Timeout
    PaymentReview --> Paid: ReconcileSuccess
    PaymentReview --> Cancelled: ReconcileFailure
    Paid --> Shipping: Dispatch
    Shipping --> Completed: DeliveryConfirmed
    Paid --> Refunding: RefundApproved
    Refunding --> Refunded: RefundConfirmed
    Cancelled --> [*]
    Completed --> [*]
    Refunded --> [*]
~~~

Sơ đồ giúp nhận diện:

- Trạng thái khởi đầu và kết thúc.
- Chuyển tiếp hợp lệ.
- Chuyển tiếp phụ thuộc vào kết quả bên ngoài.
- Trạng thái trung gian cần xử lý.
- Trạng thái có thể bị mắc kẹt nếu sự kiện không đến.

Sau khi mô hình hóa, hãy xác định trạng thái nào cần kiểm tra, sự kiện nào kích hoạt chuyển tiếp và điều kiện nào khiến chuyển tiếp bị từ chối. Với mỗi chuyển tiếp, kiểm tra cả trạng thái trước, điều kiện, kết quả và tác động dữ liệu.

### Trạng thái không thể tiếp cận trực tiếp

Một số trạng thái chỉ xuất hiện sau một chuỗi thao tác hoặc điều kiện đặc biệt. Ví dụ, trạng thái đang hoàn tiền có thể chỉ được tạo sau khi yêu cầu được phê duyệt. Không nên luôn đặt dữ liệu trực tiếp vào trạng thái đó rồi coi như đã kiểm tra quy trình.

Có thể dùng dữ liệu khởi tạo để kiểm tra một trạng thái ở cấp độ đơn vị hoặc thành phần, nhưng cần một kiểm thử tích hợp hoặc hệ thống để xác minh đường đi thực tế tạo ra trạng thái đó.

### Trạng thái trung gian và timeout

Các trạng thái như đang xử lý, chờ xác nhận hoặc chờ đối soát thường dễ bị bỏ qua. Chúng có thể tồn tại lâu hơn dự kiến khi dịch vụ ngoài chậm hoặc thông điệp bị mất.

Cần xác định:

- Trạng thái trung gian có thời hạn bao lâu?
- Điều gì xảy ra khi hết thời gian?
- Có retry hoặc đối soát không?
- Người dùng có thể hủy hoặc gửi lại yêu cầu không?
- Trạng thái có được phục hồi sau khi dịch vụ khởi động lại không?
- Có cảnh báo khi đối tượng bị mắc kẹt không?

## 7. Kết hợp ba loại bao phủ trong một ma trận

Mỗi góc nhìn trả lời một câu hỏi khác nhau. Có thể liên kết chúng trong ma trận để phát hiện phần đã được kiểm tra ở một góc nhìn nhưng còn thiếu ở góc nhìn khác.

| Chức năng | Luồng nghiệp vụ | Trạng thái hoặc chuyển tiếp | Bằng chứng cần có |
|---|---|---|---|
| Tạo đơn | Đặt hàng thành công | Nháp → Chờ thanh toán | Kiểm thử quy tắc tạo đơn và E2E đại diện |
| Thanh toán | Hoàn tất thanh toán | Chờ thanh toán → Đã thanh toán | Kiểm thử hợp đồng, tích hợp và trạng thái giao dịch |
| Hủy đơn | Hủy trước khi thanh toán | Chờ thanh toán → Đã hủy | Kiểm thử điều kiện hủy và giải phóng tồn kho |
| Hoàn tiền | Xử lý yêu cầu hoàn tiền | Đã thanh toán → Đang hoàn tiền → Đã hoàn tiền | Kiểm thử quyền, giới hạn số tiền và đối soát |
| Giao hàng | Hoàn tất giao hàng | Đang giao → Hoàn tất | Kiểm thử cập nhật vận chuyển và xác nhận giao |

Ma trận có thể mở rộng thêm cột rủi ro, mức ưu tiên, tầng kiểm thử, người sở hữu, mã test và kết quả chạy. Điều quan trọng là có thể truy vết từ yêu cầu đến bằng chứng.

### Cách đọc ma trận để tìm khoảng trống

Một chức năng có thể đã có kiểm thử đơn vị nhưng không xuất hiện trong luồng nghiệp vụ nào. Điều đó có thể hợp lý với chức năng nội bộ, nhưng cũng có thể cho thấy chưa ai kiểm tra cách người dùng tiếp cận nó.

Một luồng có thể đã chạy thành công nhưng trạng thái lỗi chưa được kiểm tra. Khi đó, nhóm cần bổ sung kiểm thử chuyển tiếp hoặc nhánh lỗi.

Một trạng thái có thể được kiểm tra nhưng không có kiểm thử cho đường chuyển vào hoặc ra. Cần xác minh quy tắc tạo trạng thái và các thao tác được phép từ trạng thái đó.

Không nên yêu cầu mọi ô trong ma trận phải có một kiểm thử riêng. Có thể một kiểm thử cung cấp bằng chứng cho nhiều đối tượng, nhưng phải chỉ rõ assertion nào xác minh từng tiêu chí.

## 8. Đặt mục tiêu bao phủ theo rủi ro

Một mục tiêu bao phủ chung cho toàn sản phẩm thường không phản ánh mức quan trọng của từng phần. Thay vào đó, nhóm nên đặt mục tiêu theo nhóm rủi ro và loại bằng chứng.

Ví dụ:

| Mức rủi ro | Tiêu chí bao phủ gợi ý |
|---|---|
| Cao | Tất cả quy tắc trọng yếu, luồng chính, nhánh lỗi nghiêm trọng và chuyển tiếp trạng thái quan trọng có bằng chứng |
| Trung bình | Luồng chính và các trường hợp biên hoặc ngoại lệ có khả năng xảy ra được kiểm tra |
| Thấp | Kiểm tra chức năng cơ bản và một số trường hợp đại diện phù hợp |

Các mục tiêu có thể được diễn đạt bằng điều kiện cụ thể:

- Mọi chức năng liên quan đến thanh toán phải có kiểm thử cho quy tắc số tiền, trạng thái và quyền.
- Mọi luồng nghiệp vụ cốt lõi phải có ít nhất một kiểm thử thành công và các nhánh lỗi có hậu quả cao.
- Mọi trạng thái giao dịch quan trọng phải được kiểm tra khi đi vào và khi rời khỏi trạng thái.
- Mọi chuyển tiếp bị cấm có nguy cơ gây mất dữ liệu hoặc giao dịch sai phải có kiểm thử từ chối.
- Mọi điểm tích hợp quan trọng phải có bằng chứng hợp đồng hoặc tích hợp.

Tránh đặt mục tiêu như “bao phủ 100% mọi luồng” nếu chưa xác định được phạm vi và chi phí. Nếu dùng tỷ lệ, cần kèm danh sách rủi ro cao còn thiếu để không che khuất khoảng trống quan trọng.

## 9. Xử lý số lượng tổ hợp lớn

Một chức năng có thể có nhiều điều kiện; một luồng có nhiều nhánh; một đối tượng có nhiều trạng thái và vai trò. Nếu thử mọi tổ hợp, số lượng kiểm thử có thể tăng rất nhanh.

Ví dụ, nếu có 4 vai trò, 5 trạng thái, 3 phương thức thanh toán và 4 loại dữ liệu, số tổ hợp lý thuyết đã là:

\[
4 \times 5 \times 3 \times 4 = 240
\]

Nếu thêm thiết bị, trình duyệt, ngôn ngữ và trạng thái phụ thuộc, số lượng còn tăng nữa. Không phải mọi tổ hợp đều hợp lệ hoặc có giá trị kiểm thử.

Các cách giảm số lượng nhưng vẫn giữ trọng tâm:

- **Phân vùng tương đương:** chọn đại diện cho các nhóm dữ liệu có hành vi tương tự.
- **Phân tích giá trị biên:** tập trung vào giới hạn có nguy cơ lỗi cao.
- **Bảng quyết định:** xác định tổ hợp điều kiện ảnh hưởng đến kết quả.
- **Kiểm thử theo cặp:** bảo đảm các cặp giá trị quan trọng được kết hợp ít nhất một lần.
- **Ưu tiên theo rủi ro:** kiểm tra sâu tổ hợp có hậu quả lớn hoặc lịch sử lỗi.
- **Kiểm thử dựa trên thuộc tính:** kiểm tra bất biến trên nhiều dữ liệu được sinh ra.
- **Kiểm thử thăm dò:** tìm tình huống bất ngờ mà mô hình chưa dự đoán.

Khi giảm tổ hợp, cần ghi rõ chiến lược lấy mẫu và lý do. Không nên nói đã bao phủ mọi tổ hợp nếu chỉ dùng một tập đại diện.

## 10. Định nghĩa điều kiện để tính một mục là đã bao phủ

Một trong những nguyên nhân khiến tỷ lệ bao phủ gây hiểu nhầm là mỗi nhóm định nghĩa “đã bao phủ” theo cách khác nhau. Cần quy định điều kiện đủ rõ để có thể đánh giá nhất quán.

Ví dụ:

| Đối tượng | Điều kiện tính là đã bao phủ |
|---|---|
| Chức năng | Có kiểm thử cho hành vi chính, quy tắc trọng yếu và các trường hợp rủi ro cao; assertion xác minh đúng kết quả |
| Luồng | Các bước chính, điểm tích hợp và trạng thái cuối được xác minh; nhánh rủi ro cao có bằng chứng riêng |
| Trạng thái | Trạng thái được tạo bằng đường đi hợp lệ hoặc có lý do rõ khi khởi tạo trực tiếp; dữ liệu và hành vi trong trạng thái được xác minh |
| Chuyển tiếp | Điều kiện kích hoạt, trạng thái trước, trạng thái sau và tác động dữ liệu được kiểm tra |
| Chuyển tiếp bị cấm | Hệ thống từ chối đúng thao tác và không làm thay đổi dữ liệu ngoài ý muốn |
| Rủi ro | Có phép kiểm chứng phù hợp, người sở hữu và bằng chứng gần nhất còn hiệu lực |

Một mục có thể ở trạng thái “bao phủ một phần” nếu mới kiểm tra đường đi chính nhưng thiếu nhánh lỗi. Cần giữ trạng thái này thay vì ép mọi mục thành đạt hoặc chưa đạt.

### Trạng thái theo dõi bao phủ

Có thể dùng các trạng thái:

- **Chưa phân tích:** chưa xác định điều kiện và rủi ro cần kiểm tra.
- **Chưa có kiểm thử:** đã xác định đối tượng nhưng chưa có phép kiểm chứng.
- **Đã thiết kế:** có trường hợp kiểm thử nhưng chưa thực thi.
- **Đã chạy, chưa đạt:** có kết quả thất bại hoặc bằng chứng chưa đáp ứng.
- **Bao phủ một phần:** một số điều kiện đã đạt nhưng còn khoảng trống.
- **Đã bao phủ:** đáp ứng tiêu chí đã định và có bằng chứng.
- **Ngoài phạm vi:** được loại trừ có lý do và có người chấp nhận.
- **Cần xem xét lại:** yêu cầu, kiến trúc hoặc hành vi đã thay đổi khiến bằng chứng cũ có thể không còn phù hợp.

Các trạng thái giúp phân biệt có test case với có bằng chứng đạt. Chỉ chuyển sang “đã bao phủ” sau khi kiểm thử chạy và xác minh đúng điều kiện.

## 11. Liên kết tiêu chí bao phủ với tầng kiểm thử

Không phải mọi tiêu chí đều cần được kiểm tra ở cùng một tầng. Chọn tầng phù hợp giúp kiểm thử nhanh, dễ khoanh vùng và giảm chi phí.

| Loại bằng chứng | Tầng thường phù hợp | Ví dụ |
|---|---|---|
| Quy tắc chức năng nhỏ | Đơn vị | Công thức giảm giá, điều kiện hủy |
| Hành vi một thành phần | Thành phần | Xử lý trạng thái đơn trong một dịch vụ |
| Tương thích giữa hai phía | Hợp đồng | Schema API, mã trạng thái, sự kiện |
| Dữ liệu và giao tiếp thật | Tích hợp | Ghi đơn, giữ chỗ tồn kho, nhận webhook |
| Hành trình hoàn chỉnh | Hệ thống hoặc E2E | Đặt hàng và thanh toán |
| Nhu cầu người dùng | Chấp nhận | Người dùng hoàn thành quy trình thực tế |
| Hiệu năng, bảo mật, phục hồi | Kiểm thử chuyên biệt | Tải, phân quyền, khôi phục |

Một tiêu chí bao phủ có thể được xác minh bằng nhiều tầng. Ví dụ, chức năng hủy đơn có thể có kiểm thử đơn vị cho quy tắc điều kiện, tích hợp cho việc giải phóng tồn kho và E2E cho hành trình người dùng. Ma trận cần cho biết từng bằng chứng đóng góp vào phần nào.

## 12. Ví dụ tổng hợp: thiết kế tiêu chí bao phủ cho hệ thống đặt lịch

Giả sử một hệ thống cho phép khách hàng đặt lịch dịch vụ. Nhân viên quản lý lịch và quản trị viên cấu hình dịch vụ, địa điểm, thời lượng và khung giờ.

### Bao phủ chức năng

Các chức năng chính:

- Tìm dịch vụ và địa điểm.
- Xem khung giờ còn trống.
- Tạo lịch.
- Sửa lịch.
- Hủy lịch.
- Gửi thông báo.
- Quản lý quyền khách hàng, nhân viên và quản trị viên.

Mỗi chức năng có quy tắc và trường hợp cần kiểm tra. Ví dụ, tạo lịch cần xác minh thời gian hợp lệ, dịch vụ đang hoạt động, nhân viên có khả năng phục vụ và khung giờ còn trống.

### Bao phủ luồng

Các luồng quan trọng:

- Khách hàng tìm dịch vụ và đặt lịch thành công.
- Khách hàng đổi lịch theo chính sách.
- Khách hàng hủy lịch.
- Nhân viên xác nhận hoặc thay đổi lịch.
- Hai khách hàng cùng chọn một khung giờ.
- Dịch vụ thông báo tạm thời không khả dụng.
- Người dùng thử lại sau timeout.

### Bao phủ trạng thái

Một lịch có thể có các trạng thái:

| Trạng thái | Chuyển tiếp vào | Chuyển tiếp ra |
|---|---|---|
| Nháp | Khách hàng bắt đầu đặt | Chờ xác nhận hoặc bị hủy |
| Chờ xác nhận | Yêu cầu hợp lệ được gửi | Đã xác nhận, bị từ chối hoặc hết hạn |
| Đã xác nhận | Nhân viên hoặc hệ thống chấp thuận | Đã hoàn tất, đã hủy hoặc cần đổi lịch |
| Đã hủy | Khách hàng hoặc nhân viên hủy hợp lệ | Kết thúc theo chính sách |
| Đã hoàn tất | Dịch vụ đã được cung cấp | Kết thúc |
| Hết hạn | Không xác nhận trong thời gian quy định | Kết thúc hoặc tạo yêu cầu mới |

Nhóm cần kiểm tra cả trạng thái và chuyển tiếp. Ví dụ, lịch đã hủy không thể được xác nhận lại bằng một yêu cầu cũ nếu chính sách không cho phép.

### Ma trận tiêu chí bao phủ minh họa

| Đối tượng | Tiêu chí | Bằng chứng |
|---|---|---|
| Tạo lịch | Kiểm tra dữ liệu, thời gian, dịch vụ và khung giờ | Đơn vị, tích hợp |
| Hủy lịch | Kiểm tra điều kiện và giới hạn thời gian | Đơn vị, E2E |
| Đặt lịch thành công | Hoàn thành hành trình từ tìm kiếm đến xác nhận | E2E |
| Đặt trùng lịch | Hai yêu cầu đồng thời không chiếm cùng một khung giờ | Tích hợp, kiểm thử đồng thời |
| Chờ xác nhận → Đã xác nhận | Chỉ vai trò được phép mới thực hiện chuyển tiếp | API, tích hợp |
| Đã xác nhận → Đã hủy | Giữ đúng chính sách hủy và cập nhật thông báo | Tích hợp, E2E |
| Hết hạn | Hệ thống chuyển trạng thái đúng khi quá thời gian | Kiểm thử thời gian, tích hợp |
| Thông báo lỗi | Lịch vẫn nhất quán khi dịch vụ thông báo ngừng hoạt động | Tích hợp, vận hành |

Sau khi chạy kiểm thử, nhóm cập nhật trạng thái bằng chứng cho từng hàng. Nếu hành trình đặt lịch thành công nhưng chưa kiểm tra đặt trùng, luồng chỉ được bao phủ một phần theo tiêu chí đã định.

## 13. Báo cáo bao phủ và giới hạn của chỉ số

Báo cáo nên cung cấp cả tỷ lệ tổng và danh sách khoảng trống. Một bảng tổng hợp có thể gồm:

| Góc nhìn | Tổng số mục | Đã bao phủ | Bao phủ một phần | Chưa có bằng chứng |
|---|---:|---:|---:|---:|
| Chức năng | 20 | 15 | 3 | 2 |
| Luồng | 8 | 5 | 2 | 1 |
| Trạng thái | 10 | 8 | 1 | 1 |
| Chuyển tiếp | 18 | 12 | 4 | 2 |

Số liệu trên chỉ minh họa cách trình bày. Khi tính tỷ lệ, cần nêu mẫu số và quy tắc phân loại. Có thể tính tỷ lệ “đã bao phủ” riêng, hoặc tính cả phần bao phủ một phần với trọng số khác, nhưng không nên trộn lẫn mà không giải thích.

### Những chỉ số bổ sung có ích

- Tỷ lệ bao phủ các chức năng rủi ro cao.
- Tỷ lệ luồng chính và nhánh lỗi quan trọng đã kiểm tra.
- Tỷ lệ trạng thái và chuyển tiếp quan trọng có bằng chứng.
- Số rủi ro cao chưa có phép kiểm chứng.
- Số kiểm thử có trạng thái không ổn định.
- Thời gian từ khi phát hiện khoảng trống đến khi bổ sung bằng chứng.
- Tỷ lệ kiểm thử đã lỗi thời sau thay đổi yêu cầu hoặc kiến trúc.

Không nên diễn giải tỷ lệ bao phủ như xác suất không có lỗi. Bao phủ cao không đảm bảo assertion tốt, dữ liệu đại diện hoặc kiểm thử đủ sâu. Một tỷ lệ thấp ở một nhóm rủi ro thấp có thể chấp nhận được, trong khi một chuyển tiếp quan trọng chưa được kiểm tra có thể là vấn đề chặn phát hành.

## 14. Duy trì tiêu chí bao phủ khi sản phẩm thay đổi

Tiêu chí bao phủ không phải tài liệu cố định. Khi chức năng, luồng hoặc vòng đời đối tượng thay đổi, mô hình và bằng chứng có thể trở nên lỗi thời.

Cần xem xét cập nhật khi:

- Thêm hoặc loại bỏ chức năng.
- Thay đổi quy tắc nghiệp vụ hoặc tiêu chí chấp nhận.
- Thêm trạng thái hoặc chuyển tiếp mới.
- Thay đổi API, sự kiện hoặc ranh giới dịch vụ.
- Thay đổi vai trò và quyền.
- Có lỗi hoặc sự cố cho thấy một tiêu chí chưa đủ.
- Thay đổi cấu hình, nền tảng hoặc nhà cung cấp.
- Một kiểm thử bị tắt, xóa hoặc không còn chạy trong pipeline.

Khi thay đổi, nhóm cần đánh giá tác động đến ma trận bao phủ, cập nhật mẫu số nếu phạm vi thay đổi và xác định kiểm thử nào cần chạy lại. Không nên giữ tỷ lệ cũ nếu danh sách chức năng hoặc trạng thái đã thay đổi.

### Gắn chủ sở hữu cho tiêu chí và bằng chứng

Mỗi nhóm đối tượng nên có người chịu trách nhiệm duy trì:

- Người sở hữu chức năng và quy tắc.
- Người sở hữu hành trình nghiệp vụ.
- Người sở hữu mô hình trạng thái.
- Người duy trì kiểm thử và dữ liệu.
- Người tổng hợp bằng chứng và báo cáo.

Với sản phẩm nhỏ, một người có thể đảm nhận nhiều vai trò. Với hệ thống nhiều nhóm, cần đầu mối điều phối để tránh khoảng trống ở ranh giới.

## 15. Những sai lầm thường gặp khi thiết kế tiêu chí bao phủ

- **Chỉ đo bao phủ mã nguồn:** mã được thực thi không đồng nghĩa hành vi nghiệp vụ đã được xác minh.
- **Coi có test case là đã bao phủ:** cần xem assertion, điều kiện và kết quả thực tế.
- **Chỉ đếm chức năng:** bỏ qua hành trình xuyên thành phần và trạng thái trung gian.
- **Chỉ kiểm tra trạng thái, không kiểm tra chuyển tiếp:** trạng thái có thể được tạo trực tiếp nhưng đường chuyển vào sai.
- **Chỉ kiểm tra đường đi thành công:** các nhánh từ chối, hủy, timeout và phục hồi có thể bị bỏ sót.
- **Dùng mẫu số không rõ:** tỷ lệ bao phủ không thể so sánh nếu cách phân rã và loại trừ khác nhau.
- **Coi mọi mục có trọng số ngang nhau:** rủi ro nghiêm trọng có thể bị che khuất bởi nhiều mục ít quan trọng.
- **Cố đạt 100% bằng mọi giá:** số lượng tổ hợp có thể rất lớn và nhiều tổ hợp không có giá trị thực tế.
- **Không ghi phần ngoài phạm vi:** người đọc có thể hiểu nhầm rằng những phần chưa kiểm tra đã đạt.
- **Không cập nhật sau thay đổi:** bằng chứng cũ không còn đại diện cho hành vi mới.

## 16. Mẫu thiết kế tiêu chí bao phủ

Có thể dùng cấu trúc sau để thiết kế và theo dõi tiêu chí:

~~~text
PHẠM VI SẢN PHẨM / BẢN PHÁT HÀNH:
MỤC TIÊU CHẤT LƯỢNG:
NGUỒN YÊU CẦU:

A. BAO PHỦ CHỨC NĂNG
- Chức năng:
- Quy tắc trọng yếu:
- Điều kiện bình thường:
- Điều kiện biên / lỗi:
- Tiêu chí được tính là bao phủ:
- Kiểm thử và bằng chứng:
- Trạng thái:

B. BAO PHỦ LUỒNG
- Luồng nghiệp vụ:
- Điểm bắt đầu và kết thúc:
- Các bước chính:
- Nhánh quan trọng:
- Điểm tích hợp:
- Trạng thái cuối và bất biến:
- Tiêu chí được tính là bao phủ:
- Kiểm thử và bằng chứng:
- Trạng thái:

C. BAO PHỦ TRẠNG THÁI
- Đối tượng:
- Danh sách trạng thái:
- Chuyển tiếp hợp lệ:
- Chuyển tiếp bị cấm:
- Điều kiện và sự kiện:
- Tác động dữ liệu:
- Tiêu chí trạng thái / chuyển tiếp:
- Kiểm thử và bằng chứng:
- Trạng thái:

D. ƯU TIÊN VÀ GIỚI HẠN
- Rủi ro cao chưa được bao phủ:
- Mục bao phủ một phần:
- Phần ngoài phạm vi và lý do:
- Biện pháp kiểm soát bổ sung:
- Người sở hữu:
- Ngày xem xét lại:
~~~

Mẫu có thể được quản lý trong công cụ yêu cầu, công cụ kiểm thử hoặc tài liệu nhóm. Không cần tạo một bảng riêng cho mỗi chức năng nếu có thể duy trì truy vết trong hệ thống hiện tại.

## Kết luận

Tiêu chí bao phủ cần được thiết kế theo ba góc nhìn bổ sung: chức năng, luồng nghiệp vụ và trạng thái cùng chuyển tiếp. Bao phủ chức năng xác minh các khả năng và quy tắc; bao phủ luồng xác minh sự phối hợp của nhiều bước và thành phần; bao phủ trạng thái xác minh vòng đời và những chuyển tiếp được phép hoặc bị cấm.

Khi định nghĩa rõ đối tượng, mẫu số, điều kiện được tính là bao phủ, bằng chứng và giới hạn, nhóm có thể đánh giá chất lượng kiểm thử thực chất hơn. Các mục tiêu cần ưu tiên theo rủi ro, được liên kết với tầng kiểm thử phù hợp và cập nhật khi sản phẩm thay đổi. Tỷ lệ bao phủ khi đó trở thành công cụ hỗ trợ quyết định, giúp nhận diện khoảng trống và giải thích phần nào đã được kiểm chứng thay vì chỉ là một con số để đạt.
