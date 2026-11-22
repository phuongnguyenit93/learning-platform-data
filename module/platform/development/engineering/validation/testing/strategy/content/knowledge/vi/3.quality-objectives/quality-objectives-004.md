# Xác định kết quả nghiệp vụ đúng và mức dịch vụ cần đáp ứng

## Mục tiêu học tập

Sau bài học này, người học có thể:

- Phân biệt kết quả nghiệp vụ, tính đúng đắn của nghiệp vụ và mục tiêu chất lượng dịch vụ.
- Chuyển mong đợi của người dùng và tổ chức thành các điều kiện chấp nhận có thể kiểm chứng.
- Giải thích SLI, SLO và SLA; lựa chọn chỉ số phù hợp để mô tả mức dịch vụ.
- Xác định ngưỡng, phạm vi đo, cửa sổ thời gian và điều kiện tải cho một mục tiêu chất lượng.
- Thiết kế hoạt động kiểm thử và thu thập bằng chứng để đánh giá cả tính đúng đắn nghiệp vụ lẫn mức dịch vụ.

## 1. Mục tiêu chất lượng trả lời hai câu hỏi

Trong phạm vi **VALIDATION_TESTING_STRATEGY**, việc xác định mục tiêu chất lượng giúp nhóm biết sản phẩm cần tạo ra kết quả gì và phải duy trì chất lượng ở mức nào trong quá trình sử dụng. Một chức năng có thể trả về phản hồi thành công nhưng vẫn làm sai nghiệp vụ; một chức năng có thể cho kết quả đúng trong môi trường thử nghiệm nhưng quá chậm hoặc thiếu ổn định khi nhiều người dùng cùng truy cập.

Vì vậy, cần xác định đồng thời hai nhóm mục tiêu:

1. **Kết quả nghiệp vụ đúng**: hệ thống thực hiện đúng quy tắc, chuyển trạng thái hợp lệ, bảo toàn dữ liệu và tạo ra kết quả mà người dùng hoặc tổ chức mong đợi.
2. **Mức dịch vụ cần đáp ứng**: hệ thống cung cấp kết quả với tốc độ, khả năng sẵn sàng, năng lực xử lý, độ tin cậy và các thuộc tính chất lượng đã thống nhất trong điều kiện sử dụng xác định.

Hai nhóm này có quan hệ chặt chẽ nhưng không thay thế nhau. Một đơn hàng có thể được tính đúng tổng tiền nhưng người mua phải chờ quá lâu mới nhận được xác nhận. Ngược lại, API có thể phản hồi trong vài trăm mili giây nhưng ghi nhận sai số lượng hàng hoặc tạo hai đơn cho một lần mua. Đánh giá chất lượng cần kiểm tra cả **đúng việc** lẫn **đúng mức**.

### Phân biệt đầu ra, kết quả và mục tiêu chất lượng

- **Đầu ra (output)** là thứ hệ thống tạo ra, chẳng hạn một phản hồi API, một hóa đơn hoặc một bản ghi đơn hàng.
- **Kết quả nghiệp vụ (business outcome)** là thay đổi có ý nghĩa đối với người dùng hoặc tổ chức, chẳng hạn người mua hoàn tất giao dịch và nhận đúng hàng đã đặt.
- **Mục tiêu chất lượng (quality objective)** là điều kiện có thể đánh giá để xác định đầu ra và dịch vụ có hỗ trợ kết quả đó hay không, chẳng hạn tổng tiền phải khớp quy tắc tính giá và 95% yêu cầu xác nhận đơn phải hoàn tất trong tối đa hai giây ở mức tải đã xác định.

Không nên lấy số lượng tính năng, số lần API trả mã thành công hoặc số ca kiểm thử đã chạy làm mục tiêu chất lượng duy nhất. Những con số đó chỉ có ý nghĩa khi gắn với kết quả mong đợi và điều kiện đo rõ ràng.

## 2. Bắt đầu từ người dùng và quy tắc nghiệp vụ

Trước khi đặt ngưỡng kỹ thuật, nhóm cần hiểu ai sử dụng chức năng, họ đang cố hoàn thành việc gì, điều gì được xem là thành công và hậu quả nào xảy ra nếu hệ thống làm sai. Cùng một chỉ số có thể có ý nghĩa khác nhau tùy bối cảnh. Một giây chậm thêm có thể chấp nhận được với báo cáo chạy cuối ngày nhưng gây khó chịu trong thao tác xác nhận thanh toán.

Với mỗi hành trình quan trọng, hãy làm rõ:

- **Đối tượng và mục đích**: người dùng hoặc hệ thống nào khởi tạo thao tác, và họ muốn hoàn thành việc gì?
- **Điều kiện đầu vào**: dữ liệu, quyền, trạng thái và điều kiện tiên quyết nào phải hợp lệ?
- **Quy tắc nghiệp vụ**: cách tính toán, giới hạn, ưu tiên, điều kiện từ chối và ngoại lệ nào phải được áp dụng?
- **Trạng thái cuối**: dữ liệu hoặc trạng thái nào phải được tạo, cập nhật hoặc giữ nguyên?
- **Tác động của sai sót**: lỗi có thể gây mất tiền, tạo dữ liệu trùng, lộ thông tin, gián đoạn công việc hay làm người dùng mất niềm tin không?
- **Điều kiện sử dụng**: số người dùng, lưu lượng, thiết bị, mạng, khu vực và các phụ thuộc bên ngoài có ảnh hưởng thế nào?

Ví dụ, mong đợi “đặt hàng thành công” còn quá chung. Nhóm cần xác định thành công nghĩa là đơn hàng được tạo đúng một lần, chứa đúng sản phẩm và số lượng, tổng tiền tuân theo quy tắc giá và khuyến mại, trạng thái thanh toán phù hợp, tồn kho được cập nhật theo quy tắc đã thống nhất, và người mua nhận được mã đơn hàng. Các bước này có thể do nhiều dịch vụ phối hợp thực hiện nên phải làm rõ cả kết quả cuối lẫn những trạng thái trung gian được phép.

## 3. Xác định tính đúng đắn của nghiệp vụ

Tính đúng đắn nghiệp vụ (business correctness) mô tả việc hệ thống thực hiện đúng các quy tắc và bảo toàn những điều kiện quan trọng của miền nghiệp vụ. Nó không chỉ là việc một hàm trả về giá trị mong đợi hoặc một endpoint trả mã HTTP thành công.

### 3.1. Viết quy tắc thành điều kiện kiểm chứng được

Một quy tắc cần nêu rõ điều kiện áp dụng, hành động và kết quả quan sát được. Có thể sử dụng cấu trúc Given–When–Then:

```gherkin
Given người mua có giỏ hàng còn hiệu lực gồm 2 sản phẩm A
And giá áp dụng tại thời điểm xác nhận là 100.000 đồng cho mỗi sản phẩm
And không có khuyến mại hoặc phí bổ sung
When người mua xác nhận đặt hàng
Then hệ thống tạo đúng một đơn hàng
And đơn hàng có 2 sản phẩm A
And tổng tiền hàng là 200.000 đồng
And phản hồi chứa mã đơn hàng đã được ghi nhận
```

Đây là ví dụ đơn giản để minh họa cách đặc tả. Dự án thực tế cần bổ sung quy tắc về thuế, vận chuyển, làm tròn, tiền tệ, thời điểm khóa giá, khuyến mại và thanh toán nếu chúng thuộc phạm vi chức năng.

### 3.2. Xác định các bất biến nghiệp vụ

**Bất biến (invariant)** là điều kiện phải luôn đúng trong mọi trạng thái hợp lệ của hệ thống. Bất biến giúp phát hiện lỗi mà một kiểm tra đầu ra đơn lẻ có thể bỏ sót. Ví dụ:

- Tổng số tiền của các dòng hàng, giảm giá, thuế và phí phải khớp với tổng tiền đơn hàng theo quy tắc tính toán đã công bố.
- Một mã chống gửi lặp chỉ được tạo tối đa một đơn hàng trong phạm vi và thời hạn được quy định.
- Đơn hàng đã hủy không được tiếp tục chuyển sang trạng thái giao hàng nếu không có một quy trình khôi phục hợp lệ.
- Người dùng chỉ được xem hoặc thay đổi dữ liệu thuộc phạm vi quyền của họ.
- Số lượng tồn kho không được giảm vượt quá quy tắc cho phép; thao tác giữ hàng và hoàn hàng phải có tác động đối ứng phù hợp.
- Một giao dịch đã ghi nhận không được mất dấu khi dịch vụ khởi động lại hoặc khi một thành phần phụ thuộc gặp lỗi, theo mức độ bền vững đã cam kết.

Các bất biến cần được xác nhận với chủ sở hữu nghiệp vụ và phản ánh trong kiểm thử ở những cấp phù hợp. Không tự suy ra quy tắc quan trọng từ cách hệ thống hiện đang hoạt động, vì cách triển khai hiện tại có thể chính là nơi chứa lỗi.

### 3.3. Kiểm tra cả luồng lỗi và chuyển trạng thái

Tính đúng đắn thể hiện rõ ở các trường hợp ngoại lệ: dữ liệu thiếu, giá thay đổi, tồn kho vừa hết, thanh toán bị từ chối, yêu cầu gửi lặp, hai người cùng cập nhật hoặc một dịch vụ bị ngắt giữa chừng. Với mỗi tình huống, nhóm phải xác định trạng thái nào được phép xảy ra và dữ liệu nào cần được giữ nguyên hoặc hoàn tác.

Ví dụ về đơn hàng:

| Tình huống | Kết quả nghiệp vụ cần xác định |
|---|---|
| Giỏ hàng hợp lệ và thanh toán thành công | Tạo một đơn hàng với đúng chi tiết và trạng thái đã thanh toán theo quy trình. |
| Dữ liệu giao hàng không hợp lệ | Từ chối xác nhận; không tạo đơn hàng ở trạng thái đã chấp nhận. |
| Thanh toán bị từ chối | Ghi nhận kết quả từ chối và giữ trạng thái đơn hàng theo quy tắc; không thể hiện giao dịch như đã thanh toán. |
| Máy khách gửi lại cùng yêu cầu | Trả về kết quả nhất quán và không tạo đơn hàng trùng. |
| Dịch vụ thanh toán phản hồi chậm | Xử lý trạng thái chờ hoặc thử lại theo chính sách; không ghi nhận thành công khi chưa có căn cứ. |
| Hai yêu cầu đồng thời mua sản phẩm cuối cùng | Kết quả phân bổ tồn kho tuân thủ quy tắc; không bán vượt số lượng cho phép. |

Với hệ thống phân tán, dữ liệu giữa các dịch vụ có thể cập nhật không đồng thời. Nhóm cần phân biệt trạng thái nhất quán ngay lập tức với nhất quán cuối cùng, xác định thời gian hội tụ chấp nhận được và các trạng thái trung gian hợp lệ. Không nên coi mọi độ trễ đồng bộ là lỗi nếu kiến trúc cho phép cập nhật bất đồng bộ; cũng không được chấp nhận độ trễ vô hạn khi nghiệp vụ cần kết quả trong một khoảng thời gian cụ thể.

## 4. Xác định mức dịch vụ bằng chỉ số đo được

Mức dịch vụ (service level) mô tả cách hệ thống phục vụ yêu cầu trong một phạm vi và điều kiện xác định. Các thuộc tính thường gặp gồm khả năng sẵn sàng, độ trễ, tỷ lệ lỗi, năng lực xử lý, độ bền vững dữ liệu và khả năng phục hồi.

### 4.1. Phân biệt SLI, SLO và SLA

Ba thuật ngữ thường được dùng cùng nhau:

- **SLI (Service Level Indicator)** là chỉ số đo thực tế của dịch vụ. Ví dụ: tỷ lệ yêu cầu hợp lệ được xử lý thành công, độ trễ p95 hoặc tỷ lệ tác vụ hoàn tất trong thời hạn.
- **SLO (Service Level Objective)** là mục tiêu đặt ra cho một SLI trong phạm vi và khoảng thời gian xác định. Ví dụ: ít nhất 99,9% yêu cầu đủ điều kiện nhận phản hồi thành công trong cửa sổ 30 ngày.
- **SLA (Service Level Agreement)** là cam kết dịch vụ giữa nhà cung cấp và khách hàng hoặc bên sử dụng, thường kèm điều kiện, cách tính, ngoại lệ và hệ quả nếu không đạt cam kết.

SLI cho biết điều gì đang xảy ra; SLO cho biết mức mà nhóm hướng tới; SLA quy định cam kết chính thức giữa các bên. Một tổ chức có thể đặt SLO nội bộ nghiêm ngặt hơn SLA để có khoảng dự phòng xử lý sự cố trước khi vi phạm cam kết bên ngoài.

### 4.2. Các chỉ số thường dùng

| Thuộc tính | SLI có thể sử dụng | Cách diễn giải |
|---|---|---|
| Khả năng sẵn sàng (availability) | Tỷ lệ yêu cầu đủ điều kiện được dịch vụ xử lý thành công; hoặc tỷ lệ thời gian dịch vụ sẵn sàng theo định nghĩa đã thống nhất | Cần xác định rõ cách đo theo yêu cầu hay theo thời gian, và thành phần nào được tính vào phạm vi. |
| Độ trễ (latency) | p50, p95 hoặc p99 thời gian từ điểm bắt đầu đến khi có kết quả | Phân vị cao cho thấy trải nghiệm của nhóm yêu cầu chậm; giá trị trung bình có thể che khuất đuôi phân phối. |
| Tỷ lệ lỗi (error rate) | Số yêu cầu lỗi thuộc phạm vi chia cho tổng yêu cầu đủ điều kiện | Phải phân loại lỗi của hệ thống và đầu vào không hợp lệ theo quy tắc đo đã công bố. |
| Năng lực xử lý (throughput) | Số yêu cầu hoặc tác vụ hoàn tất trong một đơn vị thời gian | Chỉ số cần đi cùng điều kiện tải và tiêu chí thành công; lưu lượng nhận vào cao không đồng nghĩa xử lý thành công cao. |
| Tính kịp thời (freshness) | Tỷ lệ dữ liệu hoặc sự kiện được cập nhật trong thời hạn quy định | Hữu ích cho hệ thống đồng bộ, báo cáo hoặc xử lý sự kiện bất đồng bộ. |
| Khả năng phục hồi | Thời gian khôi phục dịch vụ (RTO), mức mất dữ liệu tối đa chấp nhận được (RPO), tỷ lệ phục hồi thành công | Cần được kiểm chứng qua kịch bản lỗi và khôi phục thực tế. |
| Độ bền vững dữ liệu (durability) | Tỷ lệ giao dịch đã xác nhận nhưng vẫn tồn tại sau sự cố theo phạm vi kiểm tra | Cần xác định loại sự cố, thời gian quan sát và cách đối chiếu dữ liệu. |

Ví dụ về cách tính một số chỉ số:

```text
Tỷ lệ yêu cầu thành công = số yêu cầu đủ điều kiện thành công
                           / tổng số yêu cầu đủ điều kiện x 100%

Tỷ lệ lỗi = số yêu cầu lỗi thuộc phạm vi đo
            / tổng số yêu cầu đủ điều kiện x 100%

Throughput = số tác vụ hoàn tất thành công / khoảng thời gian đo

Độ trễ của một yêu cầu = thời điểm hoàn tất - thời điểm bắt đầu đo
```

Các công thức chỉ có ý nghĩa khi mẫu số và điều kiện đo được định nghĩa. Ví dụ, yêu cầu bị từ chối vì người dùng nhập thiếu trường bắt buộc có thể là hành vi nghiệp vụ đúng; không nên tự động tính nó thành lỗi khả dụng của máy chủ. Tuy vậy, nhóm vẫn cần theo dõi tỷ lệ từ chối nghiệp vụ riêng để phát hiện giao diện khó dùng hoặc quy tắc gây cản trở người dùng.

### 4.3. Đo phân vị thay vì chỉ nhìn giá trị trung bình

Giả sử phần lớn yêu cầu hoàn tất trong 200 ms nhưng một nhóm nhỏ mất 8 giây. Thời gian trung bình có thể vẫn trông chấp nhận được, trong khi người dùng gặp các yêu cầu rất chậm. Vì vậy, mục tiêu độ trễ thường sử dụng phân vị:

- **p50**: một nửa số quan sát có độ trễ không lớn hơn giá trị này.
- **p95**: 95% số quan sát có độ trễ không lớn hơn giá trị này.
- **p99**: 99% số quan sát có độ trễ không lớn hơn giá trị này.

Chọn phân vị phù hợp với mức độ quan trọng và lưu lượng. Với lưu lượng nhỏ, p99 có thể dựa trên quá ít mẫu để ổn định; cần ghi nhận số mẫu, khoảng thời gian và cách tổng hợp. Khi tổng hợp nhiều máy hoặc nhiều cửa sổ thời gian, nên dùng histogram hoặc phương pháp có thể tổng hợp đúng phân vị thay vì lấy trung bình các giá trị p95 riêng lẻ.

## 5. Viết mục tiêu chất lượng đầy đủ

Một mục tiêu đo được cần mô tả ít nhất:

1. **Đối tượng và hành trình**: dịch vụ, chức năng, nhóm người dùng hoặc loại giao dịch nào thuộc phạm vi.
2. **Chỉ số**: điều gì được đo, đơn vị nào và điểm bắt đầu/kết thúc phép đo.
3. **Ngưỡng mục tiêu**: giá trị tối thiểu, tối đa hoặc khoảng cho phép.
4. **Điều kiện tải và môi trường**: lưu lượng, dữ liệu, cấu hình, khu vực, thiết bị và phụ thuộc liên quan.
5. **Cửa sổ đo**: một lần chạy, một giờ, một ngày hay 30 ngày; cách xử lý mẫu thiếu và sự cố đã lên lịch.
6. **Nguồn bằng chứng**: metric, log, trace, báo cáo kiểm thử, dữ liệu nghiệp vụ hoặc kết quả đối chiếu nào sẽ xác nhận mục tiêu.

Có thể sử dụng mẫu câu:

> Với **[hành trình hoặc nhóm người dùng]**, trong điều kiện **[phạm vi và tải]**, chỉ số **[SLI và cách tính]** phải đạt **[ngưỡng]** trong **[cửa sổ đo]**, được xác nhận bằng **[nguồn bằng chứng]**.

Ví dụ:

- Với yêu cầu xem chi tiết đơn hàng hợp lệ, p95 thời gian phản hồi của API không vượt quá 500 ms khi tải duy trì ở 200 yêu cầu/giây trong 30 phút, đo từ lúc dịch vụ nhận yêu cầu đến khi gửi xong phản hồi.
- Trong cửa sổ 30 ngày, ít nhất 99,9% yêu cầu đọc đơn hàng đủ điều kiện phải được xử lý thành công theo định nghĩa SLI đã thống nhất.
- Sau khi hệ thống nhận sự kiện thanh toán thành công, 99% đơn hàng liên quan phải phản ánh trạng thái thanh toán đúng trong vòng 5 giây.
- Khi khôi phục từ kịch bản mất một nút dịch vụ, dịch vụ đặt hàng phải hoạt động trở lại trong tối đa 15 phút và dữ liệu đã xác nhận phải đáp ứng RPO đã thống nhất.

Các ngưỡng trên chỉ là ví dụ minh họa. Mỗi dự án phải xác lập mục tiêu dựa trên nhu cầu người dùng, mức rủi ro, dữ liệu vận hành, năng lực kỹ thuật, chi phí và cam kết với khách hàng. Không sao chép con số ví dụ thành cam kết nếu chưa có sự thống nhất của các bên chịu trách nhiệm.

### Tránh mục tiêu mơ hồ

| Cách viết chưa đủ rõ | Cách viết có thể kiểm chứng hơn |
|---|---|
| Hệ thống phải nhanh. | p95 thời gian phản hồi của thao tác tra cứu không vượt quá ngưỡng đã thống nhất, tại mức tải và môi trường được mô tả. |
| Dịch vụ luôn hoạt động. | Tỷ lệ yêu cầu đủ điều kiện thành công đạt mục tiêu trong cửa sổ đo xác định; quy tắc tính sự cố và bảo trì được công bố. |
| Hệ thống chịu được nhiều người dùng. | Dịch vụ hoàn tất thành công lưu lượng mục tiêu trong thời gian chạy tải, với giới hạn độ trễ và tỷ lệ lỗi cụ thể. |
| Dữ liệu phải cập nhật ngay. | 99% sự kiện hợp lệ được phản ánh ở hệ thống đích trong vòng 5 giây kể từ thời điểm tiếp nhận. |
| Không được mất dữ liệu. | Các giao dịch đã xác nhận phải được giữ lại sau các kịch bản sự cố thuộc phạm vi, theo RPO và phương pháp đối chiếu đã thống nhất. |

## 6. Ví dụ xuyên suốt: chất lượng của hành trình đặt hàng

Giả sử một cửa hàng trực tuyến muốn người mua hoàn tất đặt hàng chính xác và nhận xác nhận đủ nhanh vào giờ cao điểm. Nhóm có thể chuyển mong đợi đó thành hai nhóm mục tiêu riêng:

### 6.1. Mục tiêu đúng đắn nghiệp vụ

| Mã mục tiêu | Điều kiện cần đạt | Cách kiểm chứng |
|---|---|---|
| `BO-01` | Đơn hàng chứa đúng sản phẩm và số lượng người mua đã xác nhận. | So sánh giỏ hàng tại thời điểm chốt với chi tiết đơn hàng đã lưu. |
| `BO-02` | Tổng tiền được tính theo giá, khuyến mại, thuế và phí đã áp dụng. | Kiểm tra các trường hợp tính toán, biên, làm tròn và đối chiếu với quy tắc nghiệp vụ. |
| `BO-03` | Gửi lặp cùng mã chống trùng không tạo đơn hàng thứ hai. | Gửi lại tuần tự và đồng thời; kiểm tra số đơn được ghi nhận và phản hồi. |
| `BO-04` | Trạng thái đơn hàng phản ánh đúng kết quả thanh toán. | Mô phỏng thanh toán thành công, bị từ chối, chờ xử lý và phản hồi chậm; đối chiếu trạng thái giữa các thành phần. |

### 6.2. Mục tiêu mức dịch vụ

| Mã mục tiêu | Chỉ số và ngưỡng minh họa | Điều kiện đo |
|---|---|---|
| `SLO-01` | p95 phản hồi yêu cầu xác nhận không vượt quá 2 giây. | 300 yêu cầu hợp lệ/giây trong 30 phút, với dữ liệu và cấu hình gần môi trường dự kiến. |
| `SLO-02` | Ít nhất 99,9% yêu cầu xác nhận đủ điều kiện được xử lý thành công trong cửa sổ 30 ngày. | Đo tại ranh giới dịch vụ đặt hàng; loại trừ yêu cầu sai định dạng theo quy tắc đã thống nhất và theo dõi chúng riêng. |
| `SLO-03` | 99% đơn hàng nhận trạng thái thanh toán cuối cùng trong vòng 5 giây kể từ khi có sự kiện kết quả hợp lệ. | Đo độ trễ từ tiếp nhận sự kiện đến khi trạng thái được phản ánh; phân loại sự kiện lỗi hoặc gửi lại. |

Các mục tiêu này cần được hiệu chỉnh theo lưu lượng thực tế, yêu cầu kinh doanh và năng lực hạ tầng. Việc đạt SLO-01 không chứng minh BO-01 đến BO-04 đúng; việc đạt các mục tiêu nghiệp vụ trong một lần chạy tải thấp cũng không chứng minh dịch vụ đạt SLO khi tải cao.

## 7. Dùng SLO và ngân sách lỗi để quản lý độ tin cậy

Khi SLO được định nghĩa theo tỷ lệ sự kiện thành công, phần không đạt mục tiêu tạo thành **ngân sách lỗi (error budget)**. Ví dụ, SLO tỷ lệ thành công 99,9% cho phép tối đa 0,1% sự kiện đủ điều kiện không thành công trong cửa sổ đo. Nếu có 1.000.000 yêu cầu đủ điều kiện trong cửa sổ đó, ngân sách tương ứng là tối đa 1.000 yêu cầu không thành công.

Với SLO khả dụng được tính theo thời gian, mục tiêu 99,9% trong một tháng 30 ngày tương đương khoảng 43,2 phút không khả dụng tối đa. Phép quy đổi này chỉ áp dụng cho định nghĩa đo theo thời gian; nếu SLI được tính theo số yêu cầu thì phải dùng số yêu cầu làm mẫu số, không tự quy đổi sang phút.

Ngân sách lỗi giúp nhóm cân bằng tốc độ thay đổi và độ tin cậy:

- Khi mức tiêu thụ ngân sách thấp, nhóm có thể tiếp tục phát hành theo quy trình kiểm soát rủi ro đã thống nhất.
- Khi ngân sách bị tiêu thụ nhanh, nhóm cần điều tra nguyên nhân, ưu tiên sửa lỗi độ tin cậy và xem xét giảm rủi ro của các thay đổi tiếp theo.
- Khi ngân sách đã cạn, tổ chức có thể áp dụng chính sách tạm dừng hoặc hạn chế phát hành tính năng mới cho đến khi dịch vụ ổn định hơn.

Đây là cơ chế quản trị cần được thống nhất trong tổ chức. Không nên áp dụng máy móc mà bỏ qua mức độ nghiêm trọng của lỗi nghiệp vụ, bảo mật hoặc tuân thủ; một lỗi có hậu quả nghiêm trọng vẫn cần xử lý ngay cả khi tỷ lệ SLO tổng thể còn trong mục tiêu.

## 8. Chuyển mục tiêu thành chiến lược kiểm thử

Mỗi mục tiêu chất lượng phải có phương pháp kiểm chứng phù hợp. Một loại kiểm thử đơn lẻ hiếm khi đủ để chứng minh cả tính đúng đắn nghiệp vụ và mức dịch vụ.

| Phương pháp | Mục tiêu phù hợp | Bằng chứng thường thu thập |
|---|---|---|
| Unit test | Công thức, quy tắc, điều kiện và bất biến ở phạm vi hàm hoặc thành phần nhỏ | Kết quả kiểm thử, dữ liệu biên, nhánh điều kiện và báo cáo bao phủ phù hợp. |
| Integration test | Quy tắc phối hợp, hợp đồng API, giao dịch và trạng thái giữa các thành phần | Request/response, sự kiện, trạng thái lưu trữ, log và trace liên quan. |
| System / end-to-end test | Hành trình hoàn chỉnh từ thao tác người dùng đến kết quả nghiệp vụ | Kịch bản, kết quả thực tế, mã giao dịch, trạng thái cuối và ảnh hoặc log hỗ trợ. |
| Acceptance test | Mức độ đáp ứng tiêu chí từ góc nhìn người dùng hoặc chủ sở hữu nghiệp vụ | Biên bản, kết quả kịch bản, xác nhận của bên có thẩm quyền và ngoại lệ còn lại. |
| Load test | Khả năng đáp ứng mức tải dự kiến | Throughput, p95/p99, tỷ lệ lỗi, tài nguyên và cấu hình tải. |
| Stress / spike test | Hành vi khi vượt tải hoặc tải tăng đột ngột | Điểm bão hòa, kiểu lỗi, thời gian suy giảm và khả năng phục hồi. |
| Soak test | Ổn định trong thời gian dài | Xu hướng độ trễ, lỗi, bộ nhớ, hàng đợi và tài nguyên theo thời gian. |
| Resilience / recovery test | Khả năng chịu lỗi, chuyển đổi dự phòng và khôi phục | Thời gian gián đoạn, RTO, RPO, dữ liệu đối chiếu và kết quả phục hồi. |

### 8.1. Thiết kế kiểm thử hiệu năng đúng với SLO

Kịch bản tải cần phản ánh cách sử dụng thực tế: tỷ lệ đọc/ghi, kích thước dữ liệu, số phiên đồng thời, thời gian nghĩ giữa thao tác, phân bố tải theo giờ và hành vi phụ thuộc. Báo cáo phải ghi rõ cấu hình máy phát tải, số lượng máy phát, môi trường, phiên bản và thời gian chạy. Nếu máy phát tải trở thành nút thắt, kết quả không đại diện cho năng lực của dịch vụ.

Không chỉ nhìn vào throughput tối đa. Cần đánh giá đồng thời:

- Lưu lượng thành công có đạt mức yêu cầu không?
- p95 hoặc p99 có vượt ngưỡng không?
- Tỷ lệ lỗi và timeout có tăng theo tải không?
- Hàng đợi, kết nối, CPU, bộ nhớ hoặc phụ thuộc có bão hòa không?
- Khi giảm tải, hệ thống có phục hồi và xử lý hết công việc tồn đọng không?

### 8.2. Kiểm tra tính đúng đắn dưới tải và lỗi

Một hệ thống có thể đạt độ trễ mục tiêu nhưng tạo dữ liệu sai khi có truy cập đồng thời. Do đó, kiểm thử tải cần có kiểm tra hậu điều kiện nghiệp vụ, chẳng hạn số lượng đơn hàng, tổng tiền, số lượng tồn kho, tính duy nhất của mã giao dịch và trạng thái thanh toán. Khi mô phỏng lỗi phụ thuộc, cần xác minh hệ thống không báo thành công khi chưa ghi nhận được kết quả hợp lệ và không làm mất hoặc nhân đôi giao dịch khi thử lại.

### 8.3. Thu thập bằng chứng từ vận hành

Kiểm thử trước phát hành chứng minh hành vi trong môi trường và điều kiện đã thử. Metric, log và trace ở môi trường vận hành giúp xác nhận các giả định có còn đúng khi người dùng thật sử dụng. Nên gắn telemetry với hành trình và mã giao dịch phù hợp để có thể nối chỉ số dịch vụ với kết quả nghiệp vụ.

Ví dụ, một dashboard chỉ hiển thị CPU và thời gian phản hồi chưa cho biết người mua có đặt hàng thành công hay không. Bổ sung tỷ lệ xác nhận thành công, tỷ lệ đơn trùng, độ trễ cập nhật trạng thái thanh toán và số giao dịch ở trạng thái chờ sẽ giúp đánh giá tác động tới nghiệp vụ rõ hơn. Khi thu thập log hoặc trace, cần hạn chế dữ liệu cá nhân và bí mật theo chính sách bảo vệ dữ liệu của tổ chức.

## 9. Đánh giá kết quả và quyết định chấp nhận

Trước khi chấp nhận một thay đổi hoặc bản phát hành, nhóm cần xem xét các bằng chứng theo cả hai nhóm mục tiêu:

1. **Đúng nghiệp vụ**: các quy tắc quan trọng, bất biến, quyền truy cập và chuyển trạng thái có được kiểm tra không? Có lỗi nghiêm trọng hoặc sai lệch dữ liệu chưa được giải quyết không?
2. **Đạt mức dịch vụ**: SLI có được đo trong điều kiện đại diện không? Các ngưỡng về độ trễ, khả dụng, throughput và phục hồi có đạt không?
3. **Bằng chứng có thể truy nguyên**: kết quả gắn với đúng phiên bản, môi trường, dữ liệu, thời điểm và phạm vi đo không?
4. **Ngoại lệ và rủi ro còn lại**: kiểm thử nào chưa chạy, bị chặn hoặc không đủ dữ liệu? Ai có thẩm quyền chấp nhận rủi ro và trong thời hạn nào?

Không nên gộp mọi chỉ số thành một điểm trung bình duy nhất. Một dịch vụ có thể đạt độ trễ và khả dụng nhưng vẫn vi phạm một bất biến dữ liệu nghiêm trọng. Các mục tiêu quan trọng cần có ngưỡng chấp nhận riêng và quy tắc xử lý khi không đạt.

Khi một mục tiêu không đạt, báo cáo nên nêu rõ chỉ số, ngưỡng, giá trị thực tế, điều kiện đo, mức độ ảnh hưởng và bằng chứng hỗ trợ. Sau khi sửa, nhóm cần chạy lại kiểm thử liên quan và kiểm thử hồi quy để xác nhận thay đổi không làm hỏng quy tắc hoặc SLO khác.

## 10. Những sai lầm thường gặp khi đặt mục tiêu chất lượng

- **Chỉ đặt mục tiêu kỹ thuật**: nhóm theo dõi CPU hoặc độ trễ nhưng không biết người dùng có hoàn tất công việc đúng hay không. Hãy bổ sung chỉ số kết quả nghiệp vụ và quy tắc dữ liệu.
- **Chỉ kiểm tra kết quả thành công**: luồng bình thường đạt nhưng lỗi, gửi lặp, truy cập đồng thời và trạng thái chuyển tiếp chưa được xác định. Hãy đặc tả các tình huống ngoại lệ và bất biến.
- **Dùng từ không đo được**: “nhanh”, “ổn định”, “luôn sẵn sàng” không xác định được ngưỡng hoặc phạm vi. Hãy định nghĩa SLI, ngưỡng và cửa sổ đo.
- **Không xác định mẫu số**: tỷ lệ thành công có thể bị hiểu khác nhau nếu không nêu loại yêu cầu nào được tính. Hãy công bố cách phân loại yêu cầu hợp lệ, lỗi hệ thống và lỗi nghiệp vụ.
- **Chỉ nhìn trung bình**: giá trị trung bình che khuất trải nghiệm của nhóm yêu cầu chậm. Hãy theo dõi phân vị và số lượng mẫu phù hợp.
- **Đặt mục tiêu không có căn cứ**: ngưỡng quá cao có thể làm tăng chi phí không cần thiết; ngưỡng quá thấp không bảo vệ được người dùng. Hãy dùng dữ liệu nền, nhu cầu và rủi ro để thống nhất mục tiêu.
- **Đồng nhất SLO với SLA**: mục tiêu nội bộ và cam kết hợp đồng có phạm vi, ngoại lệ và hệ quả khác nhau. Hãy ghi rõ bên chịu trách nhiệm và quy tắc tính.
- **Kiểm thử tải mà không đối chiếu dữ liệu**: dịch vụ nhanh nhưng có thể ghi sai hoặc nhân đôi giao dịch. Hãy xác minh hậu điều kiện nghiệp vụ sau khi chạy tải.
- **Dùng kết quả thử nghiệm cũ cho phiên bản mới**: thay đổi mã, cấu hình hoặc phụ thuộc có thể làm kết quả trước không còn đại diện. Hãy gắn bằng chứng với phiên bản và chạy lại khi phạm vi ảnh hưởng yêu cầu.

## 11. Quy trình xác lập và kiểm chứng mục tiêu

Nhóm có thể áp dụng quy trình sau khi xây dựng hoặc cập nhật chiến lược kiểm thử:

1. **Xác định hành trình quan trọng**: chọn các chức năng và nhóm người dùng có tác động lớn đến kết quả nghiệp vụ.
2. **Làm rõ quy tắc và bất biến**: thống nhất điều kiện hợp lệ, cách tính, trạng thái, quyền và cách xử lý ngoại lệ với chủ sở hữu nghiệp vụ.
3. **Định nghĩa kết quả mong đợi**: mô tả trạng thái cuối và bằng chứng có thể chứng minh hệ thống đã thực hiện đúng.
4. **Chọn thuộc tính dịch vụ cần đo**: dựa trên trải nghiệm, rủi ro, kiến trúc, phụ thuộc và cam kết đã có.
5. **Đặc tả SLI và SLO**: nêu công thức, mẫu số, điểm đo, ngưỡng, cửa sổ thời gian, điều kiện tải và ngoại lệ.
6. **Thiết kế kiểm thử**: nối từng mục tiêu với kiểm thử chức năng, tích hợp, chấp nhận, hiệu năng hoặc phục hồi phù hợp.
7. **Chuẩn bị quan sát và dữ liệu**: bảo đảm metric, log, trace và dữ liệu kiểm thử đủ để đánh giá kết quả mà không thu thập thông tin nhạy cảm không cần thiết.
8. **Thực thi và đánh giá**: lưu phiên bản, môi trường, tải, kết quả, sai lệch và giới hạn của phép đo.
9. **Ra quyết định và cải tiến**: xử lý lỗi, chấp nhận rủi ro theo thẩm quyền, theo dõi SLO và điều chỉnh mục tiêu khi nhu cầu hoặc dữ liệu vận hành thay đổi.

## 12. Tự kiểm tra

Trước khi kết luận một tính năng hoặc dịch vụ đạt chất lượng, hãy tự hỏi:

- Kết quả nghiệp vụ nào quan trọng nhất đối với người dùng và tổ chức?
- Quy tắc, bất biến và trạng thái nào phải luôn đúng?
- Các tình huống lỗi, gửi lặp, đồng thời và phụ thuộc chậm đã có kết quả mong đợi chưa?
- Những thuộc tính dịch vụ nào ảnh hưởng trực tiếp đến hành trình đó?
- Mỗi SLI đã có công thức, mẫu số, điểm đo và cửa sổ thời gian rõ ràng chưa?
- Ngưỡng SLO có căn cứ từ nhu cầu, rủi ro, dữ liệu nền và năng lực hệ thống không?
- Có bằng chứng cho thấy hệ thống vừa xử lý đúng nghiệp vụ vừa đáp ứng mức dịch vụ trong điều kiện đại diện không?
- Những ngoại lệ và rủi ro còn lại đã được ghi nhận và người có thẩm quyền chấp nhận chưa?

## Kết luận

Mục tiêu chất lượng cần diễn tả rõ kết quả nghiệp vụ phải đúng và mức dịch vụ phải duy trì trong điều kiện sử dụng xác định. Quy tắc và bất biến nghiệp vụ bảo vệ tính chính xác của dữ liệu và hành trình người dùng; SLI, SLO và SLA giúp đo lường, đặt mục tiêu và quản lý cam kết dịch vụ. Khi mỗi mục tiêu được nối với tiêu chí kiểm chứng, phương pháp kiểm thử và bằng chứng có thể truy nguyên, nhóm có căn cứ rõ ràng để đánh giá chất lượng và đưa ra quyết định phát hành.
