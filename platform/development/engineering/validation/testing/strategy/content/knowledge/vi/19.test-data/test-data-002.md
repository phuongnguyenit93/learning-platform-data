# Dữ liệu kiểm thử: Chọn dữ liệu tổng hợp, dữ liệu mẫu hoặc dữ liệu đã khử nhận dạng

## 1. Vì sao lựa chọn loại dữ liệu kiểm thử là một quyết định quan trọng?

Dữ liệu quyết định điều kiện mà phần mềm phải xử lý. Một bộ kiểm thử có thể được thiết kế tốt nhưng vẫn cho kết quả thiếu tin cậy nếu dữ liệu không đại diện, thiếu quan hệ, chứa trạng thái không hợp lệ hoặc không thể tái tạo. Ngược lại, dùng dữ liệu thật một cách tùy tiện có thể đưa thông tin cá nhân, bí mật kinh doanh hoặc dữ liệu nhạy cảm vào môi trường không được phép.

Ba lựa chọn thường gặp là **dữ liệu tổng hợp (synthetic data)**, **dữ liệu mẫu (sample data)** và **dữ liệu đã khử nhận dạng (de-identified data)**. Chúng phục vụ những mục đích khác nhau:

- Dữ liệu tổng hợp được tạo ra cho kiểm thử theo quy tắc hoặc phân phối đã định nghĩa, không cần sao chép bản ghi của người thật.
- Dữ liệu mẫu là tập dữ liệu đại diện hoặc ví dụ dùng để minh họa, phát triển và kiểm tra hành vi. Nó có thể được tạo tổng hợp, lấy từ nguồn công khai được phép hoặc trích xuất từ nguồn khác đã qua quy trình phê duyệt.
- Dữ liệu đã khử nhận dạng được biến đổi để giảm hoặc loại bỏ khả năng nhận biết cá nhân. Mức rủi ro còn lại phụ thuộc cách biến đổi, dữ liệu liên kết và khả năng tái nhận dạng.

Trong **VALIDATION_TESTING_STRATEGY**, lựa chọn dữ liệu cần cân bằng mục tiêu kiểm thử, tính đại diện, khả năng tái lập, quyền riêng tư, bảo mật và chi phí chuẩn bị. Không có một loại dữ liệu phù hợp cho mọi trường hợp. Nhóm cần biết nguồn gốc, mục đích sử dụng, giới hạn và cách quản lý của từng tập dữ liệu.

## 2. Phân biệt ba loại dữ liệu

### 2.1. Dữ liệu tổng hợp

Dữ liệu tổng hợp là dữ liệu được tạo mới bằng quy tắc, mô hình, thuật toán hoặc công cụ sinh dữ liệu. Nó mô phỏng cấu trúc và đặc điểm cần thiết cho kiểm thử, chẳng hạn kiểu dữ liệu, phân phối, quan hệ giữa các trường và các trường hợp biên.

Ví dụ:

- Tạo khách hàng giả lập với tên, địa chỉ và mã định danh không thuộc về người thật.
- Sinh hàng nghìn đơn hàng với trạng thái, giá trị và thời điểm khác nhau.
- Tạo dữ liệu giao dịch có phân phối số tiền tương tự workload mục tiêu.
- Sinh chuỗi sự kiện theo thứ tự để kiểm tra xử lý bất đồng bộ.
- Tạo dữ liệu biên như chuỗi rỗng, giá trị cực đại, ngày nhuận hoặc số lượng bằng không.

Ưu điểm của dữ liệu tổng hợp là có thể tạo theo nhu cầu, kiểm soát được nội dung và tái tạo bằng seed hoặc quy tắc đã lưu. Tuy nhiên, dữ liệu tổng hợp quá đơn giản có thể không phản ánh cấu trúc, tương quan hoặc chất lượng của dữ liệu vận hành.

### 2.2. Dữ liệu mẫu

Dữ liệu mẫu là tập dữ liệu được chọn để minh họa hoặc đại diện cho một miền nghiệp vụ. Khái niệm này mô tả mục đích và cách sử dụng nhiều hơn là nguồn gốc. Một bộ dữ liệu mẫu có thể là:

- Bộ dữ liệu nhỏ được tạo thủ công để hướng dẫn hoặc kiểm thử chức năng.
- Tập dữ liệu tổng hợp đại diện cho các nhóm giá trị phổ biến.
- Dữ liệu công khai có giấy phép và điều kiện sử dụng phù hợp.
- Tập trích xuất đã được phê duyệt từ một nguồn vận hành.
- Bộ dữ liệu chuẩn dùng làm fixture hoặc baseline để so sánh kết quả.

Vì vậy, “dữ liệu mẫu” không đồng nghĩa với “dữ liệu an toàn”. Nếu dữ liệu mẫu lấy từ người dùng hoặc hệ thống thật, cần đánh giá quyền sử dụng, thông tin nhận dạng, bí mật và khả năng liên kết với nguồn khác.

### 2.3. Dữ liệu đã khử nhận dạng

Dữ liệu đã khử nhận dạng là dữ liệu đã được xử lý nhằm giảm khả năng xác định cá nhân hoặc chủ thể ban đầu. Các kỹ thuật có thể gồm:

- Loại bỏ định danh trực tiếp như tên, email, số điện thoại hoặc mã tài khoản.
- Thay thế định danh bằng giá trị giả hoặc mã thay thế.
- Tổng quát hóa giá trị, ví dụ ngày sinh thành nhóm tuổi hoặc địa chỉ thành khu vực rộng hơn.
- Làm nhiễu hoặc biến đổi giá trị nhạy cảm.
- Giảm độ chi tiết hoặc loại bỏ các trường không cần cho mục tiêu kiểm thử.

Khử nhận dạng không tự động bảo đảm dữ liệu không thể bị tái nhận dạng. Một người có thể được nhận biết qua tổ hợp thuộc tính hiếm, thời điểm, địa điểm hoặc dữ liệu liên kết từ nguồn khác. Nếu còn bảng ánh xạ để khôi phục định danh, dữ liệu thường được xem là dữ liệu giả danh (pseudonymized) và cần được bảo vệ như dữ liệu nhạy cảm theo chính sách áp dụng.

### 2.4. So sánh nhanh

| Tiêu chí | Dữ liệu tổng hợp | Dữ liệu mẫu | Dữ liệu đã khử nhận dạng |
| --- | --- | --- | --- |
| Nguồn | Được sinh mới theo quy tắc hoặc mô hình | Có thể là tổng hợp, công khai hoặc trích xuất được phép | Có nguồn ban đầu và đã qua biến đổi |
| Tính đại diện | Phụ thuộc chất lượng quy tắc/mô hình sinh | Phụ thuộc cách chọn mẫu và nguồn | Có thể giữ đặc điểm nguồn, tùy phép biến đổi |
| Quyền riêng tư | Thường dễ kiểm soát hơn nếu không sao chép bản ghi thật | Phụ thuộc nguồn gốc; không mặc nhiên an toàn | Có rủi ro tái nhận dạng cần đánh giá |
| Tính tái lập | Có thể cao nếu lưu seed, phiên bản và tham số | Cao nếu tập dữ liệu được quản lý phiên bản | Phụ thuộc nguồn, quy trình biến đổi và quyền truy cập |
| Phù hợp | Kiểm thử logic, biên, tải, dữ liệu giả lập và trạng thái hiếm | Demo, hướng dẫn, fixture và tập kiểm thử đại diện | Một số kiểm thử cần giữ cấu trúc dữ liệu vận hành |
| Hạn chế | Có thể thiếu tương quan và bất thường thực tế | Có thể quá nhỏ, thiên lệch hoặc có nguồn không phù hợp | Có thể mất tính hữu ích hoặc còn rủi ro riêng tư |

## 3. Chọn loại dữ liệu theo mục tiêu kiểm thử

### 3.1. Bắt đầu từ câu hỏi cần trả lời

Trước khi chọn nguồn dữ liệu, xác định:

1. Hành vi, yêu cầu hoặc rủi ro nào cần kiểm tra?
2. Dữ liệu cần có những trường, quan hệ và phân phối nào?
3. Cần dữ liệu thật đến mức nào để kết quả có ý nghĩa?
4. Có cần giữ liên kết giữa các bản ghi hoặc thứ tự thời gian không?
5. Có thông tin cá nhân, bí mật hoặc dữ liệu nhạy cảm không?
6. Ai được phép cung cấp, biến đổi, truy cập và phê duyệt dữ liệu?
7. Dữ liệu cần tồn tại bao lâu và được xóa bằng cách nào?

Nếu mục tiêu chỉ là kiểm tra quy tắc tính phí theo ngưỡng, dữ liệu tổng hợp thường đủ. Nếu cần đánh giá khả năng xử lý hàng triệu bản ghi với phân phối và quan hệ gần thực tế, cần một tập dữ liệu mẫu có cấu trúc phù hợp, có thể được sinh tổng hợp hoặc xây dựng từ thống kê đã được phê duyệt. Nếu cần tái hiện một lỗi chỉ xuất hiện trong cấu trúc dữ liệu vận hành, dữ liệu đã khử nhận dạng có thể được cân nhắc sau đánh giá rủi ro và quyền sử dụng.

### 3.2. Ma trận lựa chọn

| Mục tiêu | Lựa chọn thường phù hợp | Lý do và điều cần xác nhận |
| --- | --- | --- |
| Unit test và kiểm tra quy tắc nghiệp vụ | Dữ liệu tổng hợp hoặc builder | Dễ tạo đúng điều kiện, giá trị biên và trạng thái đặc biệt |
| Kiểm thử validation và xử lý lỗi | Dữ liệu tổng hợp | Có thể sinh có chủ đích giá trị thiếu, sai định dạng hoặc vượt giới hạn |
| Demo và tài liệu hướng dẫn | Dữ liệu mẫu tổng hợp | Dễ hiểu, ổn định và không cần dữ liệu người thật |
| Kiểm thử tích hợp với tập bản ghi đại diện | Dữ liệu mẫu được phê duyệt | Cần đủ quan hệ và cấu trúc để xác nhận hợp đồng |
| Kiểm thử hiệu năng hoặc tải | Dữ liệu tổng hợp quy mô lớn hoặc tập mẫu đã phê duyệt | Cần khối lượng, phân phối và tương quan phù hợp với workload |
| Tái hiện lỗi liên quan dữ liệu lịch sử | Dữ liệu tổng hợp tái tạo lỗi; hoặc dữ liệu đã khử nhận dạng được phê duyệt | Cần bảo toàn điều kiện gây lỗi mà vẫn kiểm soát rủi ro dữ liệu |
| Kiểm tra migration hoặc tương thích schema | Bộ mẫu có phiên bản và dữ liệu tổng hợp theo schema cũ | Cần bao phủ giá trị, quan hệ và trường lịch sử |
| Kiểm thử ML hoặc phân tích dữ liệu | Dữ liệu tổng hợp, mẫu hoặc đã khử nhận dạng tùy mục tiêu | Cần đánh giá chất lượng, tính đại diện, thiên lệch và quyền sử dụng |

Ma trận chỉ là hướng dẫn ban đầu. Quyết định cuối cùng cần xét loại dữ liệu, mục tiêu, môi trường và chính sách của tổ chức.

### 3.3. Ưu tiên dữ liệu ít nhạy cảm nhất nhưng vẫn đủ dùng

Chọn dữ liệu theo nguyên tắc tối thiểu cần thiết:

- Không dùng dữ liệu cá nhân nếu dữ liệu tổng hợp đáp ứng mục tiêu.
- Không giữ các trường nhạy cảm nếu chúng không tham gia vào hành vi cần kiểm tra.
- Không dùng toàn bộ bản ghi khi một tập con có cấu trúc đại diện là đủ.
- Không giữ dữ liệu lâu hơn thời gian cần thiết.
- Không cấp quyền truy cập rộng hơn vai trò thực hiện kiểm thử.

Mức độ chân thực cần thiết là chân thực về cấu trúc và hành vi cần xác nhận, không nhất thiết phải chứa thông tin của người dùng thật.

## 4. Thiết kế dữ liệu tổng hợp có chất lượng

### 4.1. Sinh dữ liệu từ quy tắc nghiệp vụ

Trước khi sinh dữ liệu, mô tả các bất biến và quan hệ:

- Mỗi đơn phải thuộc một khách hàng hợp lệ.
- Tổng tiền phải phù hợp với số lượng, đơn giá, chiết khấu và thuế.
- Giao dịch phải tham chiếu đúng đơn hàng.
- Trạng thái và thời điểm phải theo thứ tự hợp lệ.
- Một mã giao dịch không được tạo tác dụng phụ thanh toán nhiều lần.

Generator nên tạo dữ liệu thỏa các quy tắc cơ bản trước, sau đó tạo riêng các bộ dữ liệu âm tính để kiểm tra hệ thống từ chối dữ liệu sai. Không nên để phần lớn dữ liệu ngẫu nhiên vi phạm quan hệ khiến test chỉ kiểm tra lỗi setup.

### 4.2. Tạo dữ liệu theo phân vùng tương đương và giá trị biên

Với mỗi trường, xác định các lớp đầu vào có hành vi tương tự và các ranh giới:

| Trường | Nhóm dữ liệu đại diện | Giá trị biên hoặc bất thường |
| --- | --- | --- |
| Số lượng | Số nguyên dương thông thường | 0, 1, giá trị tối đa, vượt tối đa, số âm |
| Giá tiền | Giá trị hợp lệ theo đơn vị tiền | 0, giá trị nhỏ nhất, nhiều chữ số thập phân, vượt hạn mức |
| Email | Địa chỉ theo định dạng hỗ trợ | Rỗng, thiếu phần tên/miền, độ dài cực đại, ký tự Unicode |
| Ngày giờ | Thời điểm trong khoảng nghiệp vụ | Ranh giới ngày, ngày nhuận, timezone, thời điểm hết hạn |
| Trạng thái | Trạng thái hợp lệ theo vòng đời | Trạng thái không hỗ trợ, chuyển tiếp bất hợp lệ |
| Văn bản | Chuỗi thường và ký tự được hỗ trợ | Rỗng, chỉ khoảng trắng, ký tự đặc biệt, chuỗi rất dài |

Các giới hạn cụ thể cần lấy từ hợp đồng hoặc yêu cầu. Không tự giả định mọi trường email, tiền hoặc thời gian đều có cùng giới hạn ở mọi hệ thống.

### 4.3. Giữ quan hệ và tương quan dữ liệu

Một tập dữ liệu có thể có từng trường hợp lệ nhưng toàn bộ lại không thực tế nếu quan hệ giữa các trường sai. Ví dụ:

- Ngày giao hàng sớm hơn ngày đặt hàng.
- Giao dịch hoàn tiền không có giao dịch thanh toán gốc.
- Trạng thái đơn là CANCELLED nhưng lại có sự kiện giao hàng thành công sau đó mà không có quy tắc ngoại lệ.
- Địa chỉ giao hàng không thuộc khách hàng hoặc tenant tương ứng.
- Số lượng tồn kho không khớp với các giao dịch nhập/xuất đã ghi.

Generator cần duy trì tính toàn vẹn tham chiếu, thứ tự thời gian và bất biến nghiệp vụ. Nếu muốn kiểm tra dữ liệu sai, hãy tạo bộ dữ liệu sai có chủ đích và ghi rõ quy tắc bị vi phạm.

### 4.4. Phân phối và độ đa dạng

Với kiểm thử tìm kiếm, báo cáo, tải hoặc phân tích, dữ liệu nên phản ánh các đặc điểm quan trọng:

- Tần suất các nhóm giá trị phổ biến và hiếm.
- Độ lệch phân phối, giá trị ngoại lệ và dữ liệu thiếu.
- Quan hệ giữa các trường.
- Mức độ trùng lặp.
- Tính tập trung theo khách hàng, khu vực hoặc thời gian.
- Kích thước bản ghi và độ dài văn bản.

Không cần sao chép chính xác mọi phân phối production nếu mục tiêu không yêu cầu. Nhưng nếu kiểm thử hiệu năng hoặc thuật toán phụ thuộc phân phối, một tập dữ liệu đồng đều quá đơn giản có thể dẫn đến kết luận sai.

### 4.5. Seed và khả năng tái lập

Với generator có yếu tố ngẫu nhiên, lưu seed, phiên bản generator, tham số và schema. Khi test thất bại, nhóm có thể tái tạo đúng tập dữ liệu.

~~~python
import random

def make_orders(seed: int, count: int):
    rng = random.Random(seed)
    orders = []

    for index in range(count):
        quantity = rng.randint(1, 8)
        unit_price = rng.choice([50000, 75000, 120000, 250000])
        orders.append({
            "order_id": f"TEST-{index:06d}",
            "quantity": quantity,
            "unit_price": unit_price,
            "total": quantity * unit_price,
        })

    return orders

orders = make_orders(seed=7319, count=100)
~~~

Đoạn mã minh họa cách tạo dữ liệu có thể tái lập. Generator thực tế cần kiểm tra tính duy nhất, quan hệ giữa bản ghi, quy tắc tiền tệ và các trường bắt buộc của hệ thống.

Không dùng seed cố định nếu mục tiêu là kiểm tra nhiều trường hợp ngẫu nhiên theo thời gian mà không lưu lại từng lần chạy. Trong trường hợp đó, hãy ghi seed của mỗi lần chạy để có thể tái hiện lỗi.

## 5. Sử dụng dữ liệu mẫu một cách có kiểm soát

### 5.1. Dữ liệu mẫu cần có mục đích rõ

Một tập dữ liệu mẫu nên trả lời được:

- Nó đại diện cho loại người dùng, giao dịch hoặc quy trình nào?
- Nó được tạo từ nguồn nào?
- Nó phù hợp với phiên bản schema hoặc sản phẩm nào?
- Có những giới hạn nào về tính đầy đủ hoặc quyền sử dụng?
- Có trường hợp nào cố ý bị loại bỏ?

Một tập mẫu nhỏ cho demo nên dễ hiểu và ổn định. Một tập mẫu cho kiểm thử tích hợp cần có quan hệ, trạng thái và dữ liệu đủ để xác nhận các hợp đồng. Một tập mẫu cho benchmark cần có kích thước và phân phối được ghi rõ.

### 5.2. Không dùng một tập mẫu cho mọi mục tiêu

Tập dữ liệu có 20 khách hàng và 50 đơn hàng có thể phù hợp cho demo nhưng không đủ để kiểm tra phân trang ở hàng triệu bản ghi. Tập dữ liệu lớn có thể phù hợp cho benchmark nhưng khó dùng để viết unit test chi tiết.

Hãy tạo các bộ dữ liệu theo mục đích:

- **Fixture nhỏ:** rõ ràng, ổn định, dùng trong test logic.
- **Bộ mẫu tích hợp:** có quan hệ và trạng thái đại diện.
- **Bộ mẫu hiệu năng:** quy mô và phân phối theo workload.
- **Bộ mẫu hồi quy:** tái hiện các lỗi đã biết.
- **Bộ mẫu tài liệu:** dễ hiểu, không chứa thông tin nhạy cảm.

### 5.3. Quản lý nguồn và phiên bản

Với mỗi tập dữ liệu mẫu, ghi nhận:

- Tên và mục đích.
- Nguồn và điều kiện cấp phép hoặc phê duyệt.
- Phiên bản schema.
- Thời điểm tạo hoặc cập nhật.
- Cách tạo và kiểm tra chất lượng.
- Chủ sở hữu.
- Hạn sử dụng hoặc lịch rà soát.

Nếu dữ liệu mẫu được dùng làm baseline so sánh, cần quản lý phiên bản để thay đổi ngoài ý muốn không làm kết quả kiểm thử thay đổi âm thầm.

## 6. Khử nhận dạng và bảo vệ dữ liệu

### 6.1. Nhận diện các trường có thể tiết lộ danh tính

Không chỉ tên hoặc số định danh mới có thể nhận diện cá nhân. Cần xem xét:

- **Định danh trực tiếp:** tên, email, số điện thoại, số giấy tờ, mã khách hàng.
- **Định danh gián tiếp/quasi-identifiers:** ngày sinh, mã bưu chính, nghề nghiệp, giới tính, địa điểm hoặc thời điểm chi tiết.
- **Thuộc tính nhạy cảm:** sức khỏe, tài chính, thông tin tài khoản hoặc dữ liệu riêng tư khác.
- **Định danh trong dữ liệu liên kết:** mã giao dịch, địa chỉ IP, ID thiết bị hoặc dấu vết hành vi.

Một trường riêng lẻ có thể không nhận diện được ai, nhưng tổ hợp nhiều trường hiếm có thể làm lộ danh tính.

### 6.2. Phân biệt xóa định danh, giả danh và ẩn danh

| Cách xử lý | Mô tả | Giới hạn |
| --- | --- | --- |
| Xóa trường định danh | Loại bỏ trường trực tiếp như tên hoặc email | Các thuộc tính còn lại vẫn có thể nhận diện khi kết hợp |
| Che/mask | Ẩn một phần giá trị, ví dụ chỉ giữ vài ký tự cuối | Giá trị bị che có thể vẫn đủ để liên kết hoặc đoán |
| Giả danh (pseudonymization) | Thay định danh bằng mã khác; có thể còn bảng ánh xạ | Nếu có khóa/bảng ánh xạ hoặc dữ liệu liên kết, có thể khôi phục danh tính |
| Tổng quát hóa | Giảm độ chi tiết, ví dụ ngày sinh thành nhóm tuổi | Có thể làm giảm tính hữu ích hoặc vẫn còn tổ hợp hiếm |
| Nhiễu/biến đổi | Thay đổi một số giá trị theo phương pháp xác định | Có thể phá vỡ tính nhất quán hoặc quan hệ nếu không thiết kế cẩn thận |
| Ẩn danh hóa (anonymization) | Xử lý để không thể nhận diện lại theo tiêu chí và bối cảnh đánh giá | Cần đánh giá rủi ro tái nhận dạng; không chỉ dựa vào việc đã xóa tên |

Tên gọi không quyết định mức an toàn. Một tập dữ liệu được gọi là “ẩn danh” nhưng vẫn giữ ngày sinh đầy đủ, địa điểm nhỏ và thời điểm chính xác có thể còn rủi ro đáng kể.

### 6.3. Đánh giá nguy cơ tái nhận dạng

Trước khi đưa dữ liệu đã khử nhận dạng vào môi trường test, xem xét:

- Có thể liên kết với nguồn công khai hoặc tập dữ liệu khác không?
- Có bản ghi hiếm hoặc tổ hợp thuộc tính duy nhất không?
- Có thể suy ra cá nhân từ chuỗi thời gian hoặc hành vi không?
- Bảng ánh xạ hoặc khóa thay thế được lưu ở đâu, ai có quyền?
- Dữ liệu có chứa văn bản tự do, ghi chú hoặc tệp đính kèm không?
- Mức độ chi tiết có thực sự cần cho mục tiêu kiểm thử không?

Không nên tự đánh giá rằng dữ liệu “không có tên” là đã an toàn. Với dữ liệu nhạy cảm hoặc có khả năng liên kết, cần quy trình đánh giá và phê duyệt theo chính sách của tổ chức.

### 6.4. Bảo toàn tính hữu ích sau khử nhận dạng

Biến đổi dữ liệu có thể làm hỏng điều kiện kiểm thử nếu không chú ý:

- Thay từng ID độc lập có thể làm đứt khóa ngoại.
- Dịch ngày tháng không nhất quán có thể làm sai thứ tự sự kiện.
- Làm tròn số tiền có thể thay đổi kết quả tính phí.
- Tổng quát hóa địa chỉ có thể làm mất điều kiện phân vùng.
- Xáo trộn trạng thái độc lập có thể tạo ra vòng đời không hợp lệ.

Quy trình biến đổi nên giữ các thuộc tính cần thiết cho mục tiêu:

1. Xác định trường phải loại bỏ, tổng quát hóa hoặc thay thế.
2. Xác định quan hệ và bất biến phải bảo toàn.
3. Dùng ánh xạ nhất quán cho các khóa liên quan.
4. Kiểm tra lại schema, khóa ngoại, thứ tự thời gian và quy tắc nghiệp vụ.
5. Đánh giá rủi ro tái nhận dạng trên dữ liệu sau biến đổi.
6. Ghi phiên bản quy trình, chủ sở hữu và giới hạn sử dụng.

Nếu mục tiêu không cần cấu trúc dữ liệu thật, tạo dữ liệu tổng hợp mới có thể đơn giản và an toàn hơn việc khử nhận dạng một bản sao dữ liệu vận hành.

## 7. Kiểm tra chất lượng dữ liệu trước khi sử dụng

### 7.1. Các chiều chất lượng

| Chiều | Câu hỏi kiểm tra |
| --- | --- |
| Đầy đủ | Trường và quan hệ bắt buộc có hiện diện không? |
| Hợp lệ | Giá trị có đúng kiểu, miền và định dạng không? |
| Nhất quán | Các trường và bản ghi liên quan có mâu thuẫn không? |
| Duy nhất | Khóa hoặc định danh có trùng ngoài chủ đích không? |
| Chính xác theo mục tiêu | Dữ liệu có phản ánh điều kiện cần kiểm tra không? |
| Đại diện | Phân phối và trường hợp hiếm có phù hợp mục tiêu không? |
| Tái lập | Có thể tạo lại đúng tập dữ liệu và phiên bản không? |
| An toàn | Nguồn, quyền truy cập và mức nhạy cảm có được kiểm soát không? |

### 7.2. Kiểm tra schema và quan hệ

Trước khi chạy test, xác nhận:

- Tên trường, kiểu dữ liệu và giá trị enum phù hợp schema.
- Trường bắt buộc có đủ.
- Khóa chính và khóa ngoại hợp lệ.
- Các quan hệ một-nhiều hoặc nhiều-nhiều có số lượng phù hợp.
- Thứ tự thời gian và trạng thái nhất quán.
- Đơn vị đo, tiền tệ, timezone và encoding rõ ràng.

Một tập dữ liệu có thể hợp lệ theo JSON schema nhưng vẫn sai nghiệp vụ. Ví dụ, tổng tiền có kiểu number nhưng không bằng số lượng nhân đơn giá theo quy tắc. Vì vậy cần cả kiểm tra cấu trúc và bất biến nghiệp vụ.

### 7.3. Kiểm tra dữ liệu thiếu và ngoại lệ

Đừng chỉ kiểm tra dữ liệu sạch. Hãy có bộ dữ liệu riêng cho:

- Trường null, vắng mặt và chuỗi rỗng.
- Giá trị trùng hoặc quan hệ mồ côi.
- Giá trị ngoài miền hoặc sai định dạng.
- Bản ghi có kích thước lớn.
- Thời điểm sát ngưỡng.
- Unicode, ký tự đặc biệt và văn bản nhiều dòng.
- Bản ghi đến trễ hoặc sai thứ tự.
- Dữ liệu cũ từ phiên bản schema trước.

Không trộn dữ liệu lỗi vào bộ mẫu chuẩn nếu mục tiêu là kiểm tra happy path. Phân tách rõ bộ dữ liệu hợp lệ và bộ dữ liệu cố ý không hợp lệ.

## 8. Quản lý dữ liệu theo môi trường và vòng đời

### 8.1. Phân loại môi trường

| Môi trường | Cách tiếp cận dữ liệu gợi ý |
| --- | --- |
| Local/unit test | Dữ liệu tổng hợp nhỏ, fixture hoặc builder tạo trong bộ nhớ |
| CI/component test | Dữ liệu tổng hợp có seed, fixture phiên bản hóa và dependency được kiểm soát |
| Integration/staging | Dữ liệu tổng hợp hoặc bộ mẫu đã phê duyệt; dữ liệu đã khử nhận dạng chỉ khi cần và được cho phép |
| Performance test | Tập dữ liệu tổng hợp quy mô lớn hoặc mẫu đã đánh giá, có phân phối phù hợp |
| UAT/demo | Dữ liệu mẫu dễ hiểu, không chứa thông tin nhạy cảm không cần thiết |
| Production | Dữ liệu vận hành theo quyền và mục đích sử dụng được phép; không dùng làm kho dữ liệu kiểm thử tùy tiện |

Môi trường gần production không có nghĩa là được phép sao chép dữ liệu production. Mức độ tương đồng nên được tạo qua schema, cấu hình, workload và dữ liệu phù hợp với chính sách.

### 8.2. Quy trình vòng đời dữ liệu

~~~mermaid
flowchart TD
    A["Xác định mục tiêu và dữ liệu tối thiểu"] --> B{"Có thể dùng dữ liệu tổng hợp?"}
    B -->|"Có"| C["Sinh dữ liệu theo quy tắc và seed"]
    B -->|"Không"| D{"Có bộ dữ liệu mẫu được phép?"}
    D -->|"Có"| E["Kiểm tra nguồn, quyền và chất lượng"]
    D -->|"Không"| F["Đánh giá khả năng dùng dữ liệu đã khử nhận dạng"]
    F --> G["Phê duyệt, biến đổi và đánh giá tái nhận dạng"]
    G --> H["Kiểm tra schema, quan hệ và bất biến"]
    C --> H
    E --> H
    H --> I["Cấp quyền, ghi phiên bản và sử dụng"]
    I --> J["Theo dõi, hết hạn và thu hồi/xóa"]
~~~

Quy trình thực tế có thể có bước phê duyệt riêng theo mức nhạy cảm và chính sách dữ liệu. Không đưa dữ liệu vào môi trường trước khi xác định nguồn gốc và quyền sử dụng.

### 8.3. Quyền truy cập và lưu trữ

- Chỉ cấp quyền cho người và dịch vụ cần dùng.
- Tách quyền truy cập dữ liệu khỏi quyền sửa đổi dữ liệu.
- Mã hóa dữ liệu khi lưu và truyền theo tiêu chuẩn môi trường.
- Không đưa bản sao dữ liệu nhạy cảm vào log, artifact hoặc máy cá nhân không được quản lý.
- Ghi lại ai tạo, tải, biến đổi và xóa dữ liệu khi yêu cầu quản trị cần thiết.
- Xóa dữ liệu khi hết mục đích hoặc hết thời hạn được phép.

Với dữ liệu giả danh còn bảng ánh xạ, lưu bảng đó tách biệt, kiểm soát khóa và giới hạn người có thể khôi phục. Không lưu mapping trong cùng thư mục fixture hoặc repository test.

### 8.4. Phiên bản hóa và làm mới

Ghi nhận:

- Dataset ID và phiên bản.
- Schema hoặc phiên bản ứng dụng tương thích.
- Nguồn và phương pháp tạo/biến đổi.
- Seed và tham số generator nếu có.
- Thời điểm tạo và thời hạn sử dụng.
- Chủ sở hữu và phê duyệt.
- Kết quả kiểm tra chất lượng.

Khi schema thay đổi, cần đánh giá dữ liệu mẫu và generator có còn hợp lệ không. Không âm thầm sửa dataset chuẩn vì nó có thể làm thay đổi kết quả hồi quy hoặc benchmark.

## 9. Ví dụ: lựa chọn dữ liệu cho kiểm thử quy trình đặt lịch

### 9.1. Mục tiêu

Kiểm tra tìm khung giờ, đặt lịch, thanh toán, hủy lịch và bảo đảm không tạo hai lịch cho cùng tài nguyên và thời gian.

### 9.2. Bộ dữ liệu tổng hợp

Tạo:

- Hai khách hàng giả lập thuộc hai tenant.
- Một tài nguyên với các khung giờ AVAILABLE, HELD và BOOKED.
- Một lịch đã thanh toán, một lịch chưa thanh toán và một lịch đã hủy.
- Các giao dịch thành công, thất bại, pending và callback lặp.
- Thời điểm trước, đúng và sau ngưỡng hủy.

Bộ này phù hợp cho unit, component, API và nhiều kịch bản tích hợp vì trạng thái được kiểm soát và có thể tái tạo.

### 9.3. Bộ dữ liệu mẫu

Tạo một tập mẫu có:

- Nhiều loại dịch vụ và thời lượng.
- Nhiều múi giờ hoặc khu vực được hỗ trợ.
- Các vai trò người dùng.
- Khối lượng lịch đại diện cho tìm kiếm và phân trang.
- Một số trường hợp hiếm được gắn nhãn.

Bộ mẫu phù hợp cho demo, kiểm tra UI, báo cáo và tích hợp. Nguồn dữ liệu cần được ghi nhận; không đưa thông tin người dùng thật vào chỉ vì cần dữ liệu trông thực tế.

### 9.4. Bộ dữ liệu đã khử nhận dạng

Nếu cần tái hiện một lỗi chỉ xảy ra với cấu trúc lịch sử phức tạp, nhóm có thể xem xét một tập dữ liệu nguồn đã được phê duyệt. Trước khi dùng:

- Loại bỏ định danh trực tiếp.
- Đánh giá tổ hợp thuộc tính hiếm có thể nhận diện lại người dùng.
- Thay thế khóa nhất quán để giữ quan hệ.
- Biến đổi thời gian nhất quán nếu cần bảo vệ thời điểm thật.
- Kiểm tra trạng thái, quan hệ và bất biến sau biến đổi.
- Giới hạn người truy cập, môi trường và thời gian lưu.

Nếu cấu trúc lỗi có thể tái tạo bằng generator, nên ưu tiên bộ tổng hợp tái hiện điều kiện đó. Điều này giúp tránh mang dữ liệu nguồn nhạy cảm vào quy trình kiểm thử.

## 10. Các lỗi thường gặp khi chọn và quản lý dữ liệu

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Cho rằng dữ liệu mẫu luôn an toàn | Có thể đưa dữ liệu cá nhân hoặc dữ liệu không được cấp phép vào test | Xác minh nguồn, quyền và mức nhạy cảm |
| Chỉ xóa tên và email rồi gọi là ẩn danh | Quasi-identifiers có thể cho phép tái nhận dạng | Đánh giá tổ hợp thuộc tính và dữ liệu liên kết |
| Dùng dữ liệu tổng hợp quá đơn giản | Bỏ sót phân phối, tương quan và trường hợp hiếm | Mô hình hóa các đặc điểm quan trọng theo mục tiêu |
| Sinh ngẫu nhiên không lưu seed | Không tái tạo được lỗi | Lưu seed, phiên bản generator và tham số |
| Biến đổi từng trường độc lập | Mất khóa ngoại, thứ tự thời gian hoặc bất biến | Dùng mapping nhất quán và kiểm tra lại quan hệ |
| Dùng cùng một dataset cho mọi loại test | Bộ dữ liệu quá nhỏ cho tải hoặc quá phức tạp cho unit test | Tạo dataset theo mục tiêu |
| Chia sẻ fixture có thể thay đổi | Test ảnh hưởng lẫn nhau | Dùng dữ liệu bất biến hoặc tạo riêng theo test |
| Không có thời hạn lưu/xóa | Dữ liệu tồn tại lâu hơn mục đích | Đặt owner, expiry và quy trình cleanup |
| Không ghi phiên bản schema | Test thất bại khó giải thích sau thay đổi | Gắn dataset với schema và artifact |

## 11. Mẫu mô tả và phê duyệt tập dữ liệu

~~~text
Dataset ID / tên:
Mục tiêu kiểm thử:
Loại dữ liệu: tổng hợp / mẫu / đã khử nhận dạng
Nguồn gốc:
Chủ sở hữu:
Người phê duyệt (nếu cần):

Schema / phiên bản tương thích:
Quy mô và phạm vi:
Các trường/quan hệ quan trọng:
Phân phối hoặc đặc điểm đại diện:
Trường hợp biên và dữ liệu bất thường:

Phương pháp tạo hoặc biến đổi:
Seed / tham số / phiên bản generator:
Kiểm tra chất lượng đã thực hiện:
Đánh giá riêng tư và nguy cơ tái nhận dạng:

Môi trường được phép:
Vai trò được truy cập:
Thời hạn sử dụng:
Vị trí lưu trữ:
Quy trình thu hồi/xóa:
Giới hạn và giả định:
~~~

Mẫu này giúp người dùng dữ liệu biết tập dữ liệu đến từ đâu, phù hợp với mục tiêu nào và có giới hạn gì. Với dữ liệu tổng hợp đơn giản, có thể lược bớt phần phê duyệt; với dữ liệu nguồn nhạy cảm, cần áp dụng đầy đủ quy trình của tổ chức.

## 12. Checklist chọn dữ liệu kiểm thử

- [ ] Mục tiêu và rủi ro kiểm thử đã được xác định trước khi chọn dữ liệu.
- [ ] Đã cân nhắc liệu dữ liệu tổng hợp có đáp ứng đủ mục tiêu không.
- [ ] Dữ liệu mẫu có nguồn gốc, quyền sử dụng và phiên bản rõ ràng.
- [ ] Dữ liệu đã khử nhận dạng được đánh giá nguy cơ tái nhận dạng, kể cả qua tổ hợp thuộc tính và nguồn liên kết.
- [ ] Đã phân biệt dữ liệu giả danh với dữ liệu thực sự được ẩn danh theo tiêu chí áp dụng.
- [ ] Chỉ giữ trường và số lượng dữ liệu cần thiết.
- [ ] Generator bảo toàn schema, quan hệ, thứ tự thời gian và bất biến cần kiểm tra.
- [ ] Dữ liệu có phân vùng tương đương, giá trị biên và trường hợp lỗi phù hợp.
- [ ] Seed, tham số và phiên bản generator được lưu để tái lập.
- [ ] Bộ dữ liệu được kiểm tra tính đầy đủ, hợp lệ, nhất quán và duy nhất.
- [ ] Quyền truy cập, lưu trữ, thời hạn và cleanup được xác định.
- [ ] Thay đổi schema hoặc mục tiêu kiểm thử kích hoạt rà soát dataset.
- [ ] Báo cáo nêu rõ nguồn, giới hạn và phạm vi sử dụng của dữ liệu.

Chọn dữ liệu tổng hợp, dữ liệu mẫu hay dữ liệu đã khử nhận dạng là quyết định dựa trên mục tiêu kiểm thử và mức độ nhạy cảm của thông tin. Khi nguồn gốc minh bạch, dữ liệu đủ đại diện, quan hệ được bảo toàn và vòng đời được kiểm soát, nhóm có thể tạo bằng chứng kiểm thử đáng tin cậy mà vẫn giảm thiểu rủi ro riêng tư và chi phí vận hành.
