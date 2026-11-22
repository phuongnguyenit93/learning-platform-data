# Nợ có chủ đích, nợ ngoài dự kiến và thay đổi bối cảnh

> **Chương:** Nợ kỹ thuật  
> **Học phần:** Code Quality Fundamentals (`CODE_QUALITY_FUNDAMENTALS`) — hiểu những thuộc tính quyết định mã nguồn có đáng tin cậy, dễ hiểu và dễ thay đổi hay không.

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích **nợ kỹ thuật (technical debt)** bằng chi phí thay đổi, kiểm thử, vận hành hoặc rủi ro phát sinh từ một quyết định thiết kế so với phương án phù hợp hơn trong bối cảnh hiện tại.
2. Phân biệt **nợ có chủ đích**, **nợ ngoài dự kiến** và **nợ xuất hiện vì bối cảnh thay đổi**, không tự đồng nhất chúng với lỗi lập trình, mã cũ hay quyết định thiếu trách nhiệm.
3. Nhận diện hai chiều độc lập: **có biết đang đánh đổi hay không** và **đánh đổi có được cân nhắc thận trọng hay không**.
4. Diễn giải “**gốc nợ**” và “**lãi nợ**” như những ẩn dụ giúp thảo luận chi phí, đồng thời tránh coi chúng là các con số tài chính chính xác.
5. Viết một bản ghi quyết định nợ có chủ đích: lý do, giới hạn, rủi ro, phương án thay thế, tín hiệu cần xem lại và kế hoạch giảm nợ.
6. Phân tích ví dụ Java về logic tính giá bị nhân bản và bài toán mở rộng từ một tiền tệ sang nhiều tiền tệ; đề xuất kiểm thử bảo vệ hành vi khi cải tiến.
7. Ưu tiên xử lý nợ theo **tác động và tần suất cản trở mục tiêu**, không theo số lượng “code smell” hoặc ai là tác giả.
8. Chọn giữa **giữ nguyên có giám sát**, **giảm nợ dần**, **tái thiết kế có mục tiêu** và **thay thế**, dựa trên bằng chứng thay vì cảm giác khó chịu khi đọc mã.

## 1. Nợ kỹ thuật không chỉ là “mã xấu”

Một nhóm cần đưa tính năng đặt hàng lên thử nghiệm trong phạm vi một cửa hàng. Để kịp học từ người dùng, nhóm chọn một lớp tính giá đơn giản cho VND và ghi rõ rằng hệ thống **chưa hỗ trợ nhiều tiền tệ**. Sáu tháng sau, sản phẩm mở rộng ra nhiều quốc gia và yêu cầu mới khiến cách biểu diễn tiền cũ trở nên hạn chế.

Một nhóm khác sao chép cùng quy tắc giảm giá vào hai dịch vụ mà không nhận ra. Vài tháng sau, hai bản sao khác nhau ở điều kiện ngưỡng; có đơn hiển thị giá khác số tiền thanh toán.

Cả hai tình huống có thể tạo chi phí thay đổi trong tương lai. Nhưng **nguồn gốc và cách quản lý** khác nhau:

- Ở tình huống đầu, nhóm **biết giới hạn**, chủ động đánh đổi tốc độ học hỏi với chi phí mở rộng về sau.
- Ở tình huống thứ hai, sự nhân bản hoặc sai khác có thể **không được nhận biết ngay**, nên chi phí phát sinh ngoài dự kiến.
- Trong tình huống đầu, ngay cả quyết định ban đầu hợp lý cũng có thể trở thành điểm nghẽn **khi bối cảnh kinh doanh đổi**.

**Nợ kỹ thuật** là một ẩn dụ về những lựa chọn hoặc điều kiện của hệ thống khiến công việc tương lai trở nên tốn kém, chậm, rủi ro hoặc khó dự đoán hơn so với một phương án thích hợp. Nó cần được xem trong **ngữ cảnh**: mục tiêu sản phẩm, thời gian, quy mô, bảo mật, kỹ năng và khả năng thay đổi.

Không phải mọi đoạn mã dài, thư viện cũ hoặc TODO đều là nợ kỹ thuật. Một đoạn mã cũ ổn định, được kiểm thử tốt và hầu như không cần sửa có thể **không tạo ra chi phí đáng kể**; ngược lại một chức năng mới, viết rất ngắn nhưng làm sai hợp đồng phân quyền có thể là **lỗi phải sửa ngay**, không nên dùng nhãn “nợ” để trì hoãn.

### Phân biệt những khái niệm thường bị gộp

| Hiện tượng | Ý nghĩa chính | Ví dụ | Cách phản ứng |
| --- | --- | --- | --- |
| **Lỗi hiện tại (defect)** | Hành vi đang vi phạm yêu cầu hoặc bất biến | Chuyển khoản bị ghi hai lần | Xử lý theo mức độ nghiêm trọng, không chỉ đưa vào backlog nợ |
| **Nợ kỹ thuật** | Cấu trúc/quyết định làm tăng chi phí hoặc rủi ro tương lai | Quy tắc giá bị nhân bản ở nhiều luồng, mỗi lần sửa phải đồng bộ | Đánh giá “lãi”, ưu tiên cải tiến có kiểm chứng |
| **Thiếu tính năng** | Khả năng sản phẩm chưa được cam kết triển khai | Chưa hỗ trợ đơn bằng JPY | Quyết định lộ trình sản phẩm, rồi đánh giá kiến trúc liên quan |
| **Giới hạn có chủ ý** | Phạm vi được công bố và chấp nhận trong điều kiện hiện tại | Chỉ xử lý VND ở bản thử nghiệm | Theo dõi điều kiện khiến giới hạn cần xem lại |
| **Mã cũ (legacy)** | Mã được kế thừa hoặc tồn tại lâu | Service ra đời nhiều năm trước | Đọc bằng bằng chứng thực tế; tuổi đời không phải chẩn đoán |
| **Rủi ro bảo mật/tuân thủ** | Có khả năng gây thiệt hại hoặc vi phạm nghĩa vụ | Đọc được đơn hàng tenant khác | Áp dụng chính sách xử lý rủi ro phù hợp; không viện lý do “trả nợ sau” |

Một quyết định có thể thuộc nhiều hàng. Ví dụ hệ thống xử lý nhiều tiền tệ bằng `double` có thể vừa tạo nợ về khả năng thay đổi vừa gây **lỗi số học thực tế**; khi đã có lỗi làm sai tiền, ưu tiên trước hết là **khôi phục tính đúng đắn**.

## 2. Ba nguồn gốc nợ cần nhận diện

### 2.1. Nợ có chủ đích: biết đang đánh đổi

Nhóm **nhìn thấy phương án bền vững hơn** nhưng chọn giải pháp có giới hạn để đạt một mục tiêu quan trọng trước mắt. Ví dụ:

- Dùng một bộ quy tắc tính giá cho VND khi sản phẩm mới chỉ phục vụ VND, chưa đầu tư mô hình đa tiền tệ.
- Chưa tách một module nhỏ thành dịch vụ riêng vì chưa có nhu cầu scale và chưa đủ bằng chứng về ranh giới.
- Dùng cơ chế cấu hình đơn giản cho bản thử nghiệm, đồng thời ghi điều kiện phải chuyển sang hệ thống quản lý cấu hình khi triển khai nhiều môi trường.
- Tạm thực hiện chuyển đổi dữ liệu theo batch có giám sát, với kế hoạch bổ sung cơ chế incremental khi khối lượng đạt ngưỡng.

Nợ có chủ đích **không mặc nhiên là sai**. Nó có thể là quyết định kinh tế/kỹ thuật hợp lý nếu nhóm hiểu chi phí, bảo vệ các ràng buộc thiết yếu và có điểm xem lại.

Tuy nhiên, “chúng ta cố ý làm nhanh” **không phải giấy phép** bỏ kiểm tra quyền, làm sai thanh toán, bỏ sao lưu quan trọng hoặc phớt lờ rủi ro không thể chấp nhận. Những bất biến cốt lõi vẫn phải được bảo vệ.

### 2.2. Nợ ngoài dự kiến: không nhận ra chi phí lúc tạo ra

Đôi khi nhóm không biết rằng một lựa chọn sẽ làm công việc tương lai khó hơn:

- Hai lớp vô tình sao chép một quy tắc nghiệp vụ vì không biết nơi sở hữu chính sách.
- Một API trả `null` cho cả “không tìm thấy” lẫn “database timeout”; sự mơ hồ chỉ lộ khi caller phát triển.
- Một lớp giữ quá nhiều trách nhiệm do cấu trúc tăng trưởng dần, không có ai cố tình muốn tạo “god class”.
- Thiếu test hợp đồng khiến đổi trường JSON âm thầm phá client cũ.
- Cấu hình kết nối và transaction ban đầu không được kiểm thử ở điều kiện đồng thời, làm việc mở rộng tốn công.

Người viết có thể đã làm đúng theo thông tin và quy ước sẵn có. **“Ngoài dự kiến” không đồng nghĩa thiếu năng lực hoặc cá nhân có lỗi**; đôi khi đặc tả, cấu trúc nhóm, tài liệu hoặc feedback loop đều góp phần tạo vấn đề.

Điều quan trọng là **phát hiện, làm rõ hậu quả và bổ sung phòng vệ**: hợp đồng, test, người sở hữu và quy tắc review ở nơi vấn đề thường lặp lại.

### 2.3. Nợ do thay đổi bối cảnh: giải pháp cũ từng phù hợp

Một thiết kế có thể hợp lý lúc ban đầu nhưng không còn phù hợp khi có:

- **Quy mô mới:** từ hàng trăm lên hàng triệu bản ghi, một query đơn giản trở thành nút thắt.
- **Mô hình kinh doanh mới:** từ một cửa hàng thành nhiều tenant; ranh giới truy cập cần chặt hơn.
- **Nghiệp vụ mới:** từ VND sang nhiều tiền tệ, đa thuế hoặc nhiều chính sách giá.
- **Độ tin cậy mới:** service nội bộ chuyển thành API công khai có SLA và yêu cầu khôi phục cao hơn.
- **Tích hợp mới:** nhiều client độc lập cần hợp đồng và phiên bản hóa ổn định.
- **Hạ tầng mới:** runtime, thư viện hoặc DB thay đổi, làm giả định trước đây không còn đúng.

Trong trường hợp này, **không nên viết lại lịch sử** thành “thiết kế ban đầu tệ”. Khi yêu cầu tăng, giải pháp đủ tốt hôm qua có thể tạo chi phí ngày mai. Nhận diện điều đó giúp nhóm lựa chọn đúng lúc thay vì tự trách hoặc cố bảo vệ quyết định cũ vô thời hạn.

### Ba loại không nhất thiết tách biệt

Một giải pháp VND-only được chọn có chủ đích; sau này xuất hiện yêu cầu đa tiền tệ (bối cảnh đổi); khi triển khai, nhóm còn phát hiện nhiều nơi đang ngầm giả định VND mà trước đó không biết (nợ ngoài dự kiến). Một câu chuyện nợ thực tế có thể có **cả ba lớp nguyên nhân**.

Phân loại giúp chọn cách xử lý, không nhằm tìm “ai có lỗi”.

## 3. Hai chiều khác: nhận biết và mức thận trọng

Có thể phân tích quyết định theo hai câu hỏi:

1. **Có nhận thức rõ** rằng một giải pháp sẽ tạo chi phí/rủi ro tương lai không?
2. **Có cân nhắc thận trọng** giữa thời hạn, lựa chọn thay thế, hậu quả và cách giảm thiểu không?

| | **Có chủ đích** | **Ngoài dự kiến** |
| --- | --- | --- |
| **Thận trọng** | Chọn giải pháp hẹp vì cần kiểm chứng sản phẩm, ghi ranh giới và điều kiện xem lại | Đã cân nhắc tốt với hiểu biết lúc đó nhưng vẫn phát hiện giới hạn không lường trước |
| **Thiếu thận trọng** | Biết rủi ro nghiêm trọng nhưng chấp nhận vô thời hạn, không phòng vệ hay chủ sở hữu | Bỏ qua kiến thức/tiêu chuẩn sẵn có, tạo cấu trúc khó sửa mà không nhận ra |

Đây là **khung suy nghĩ**, không phải bảng kết tội. Rất khó suy ra một quyết định “thiếu thận trọng” chỉ bằng cách nhìn mã nhiều tháng sau. Muốn đánh giá, phải biết thông tin và áp lực **tại thời điểm ra quyết định**.

Một dấu hiệu tích cực của nợ có chủ đích được quản lý tốt là **có thể kể lại bằng chứng và trade-off**: chọn gì, để đạt mục tiêu nào, chấp nhận hạn chế nào, khi nào phải xem lại.

## 4. Gốc nợ và lãi nợ: dùng phép ẩn dụ đúng mức

Phép ẩn dụ tài chính giúp thảo luận:

- **Gốc nợ (principal):** công sức một lần cần để chỉnh cấu trúc, thay đổi hợp đồng, di chuyển dữ liệu hoặc loại bỏ hạn chế.
- **Lãi nợ (interest):** chi phí phát sinh lặp lại vì còn giữ giải pháp: sửa cùng một quy tắc ở nhiều nơi, test lâu, debug khó, retry sự cố, chờ release, vá thủ công...
- **Rủi ro:** những thiệt hại có thể xảy ra nhưng chưa xảy ra; không phải “lãi đã trả” theo nghĩa chi phí chắc chắn.
- **Cơ hội:** việc chưa đầu tư sớm có thể tiết kiệm công sức nếu yêu cầu dự kiến không bao giờ xuất hiện.

Ví dụ một chính sách giảm giá bị sao chép ở ba nơi:

~~~text
Mỗi lần đổi chính sách:
  ├─ Sửa checkout
  ├─ Sửa chức năng báo giá
  ├─ Sửa báo cáo
  └─ Test sự đồng bộ cả ba đường
~~~

Nếu việc đổi giá diễn ra hàng tuần, “lãi” có thể cao. Nếu ba đường không bao giờ được sửa, chi phí trước mắt có thể nhỏ hơn tưởng tượng, dù vẫn có rủi ro latent.

**Không nên tự suy các phép đo này có độ chính xác như lãi suất ngân hàng.** Thông thường ta chỉ ước lượng: nhóm đang mất bao nhiêu lần sửa, incident, thời gian CI, thời gian onboarding, hoặc bị chặn bao lâu vì lựa chọn hiện tại.

### Phân biệt chi phí đã xảy ra và rủi ro tương lai

| Quan sát | Loại bằng chứng | Cách dùng |
| --- | --- | --- |
| Bốn PR gần nhất đều phải sửa cùng ba bản sao quy tắc | Chi phí thực đã quan sát | Ước lượng “lãi” khi tiếp tục thay đổi |
| Hai incident do hai bản sao áp dụng ngưỡng khác nhau | Hậu quả thực và dấu hiệu rủi ro | Ưu tiên test/hợp nhất chính sách |
| Có thể mất dữ liệu nếu DB timeout ở thời điểm khó | Rủi ro chưa chắc xảy ra | Phân tích mức độ nghiêm trọng và khả năng phòng vệ |
| Mất khoảng một tuần để refactor trong ước lượng hiện tại | Ước lượng gốc nợ | So với lợi ích/rủi ro được giảm, không coi là số chắc chắn |
| Thêm module mới làm người đọc phải hiểu sáu lớp trung gian | Chi phí hiểu và thay đổi | Đánh giá có nên đơn giản hóa thay vì mở rộng abstraction |

Một hệ thống có thể chứa nhiều mục nợ nhưng tác động khác nhau. **Đếm số lượng mục nợ không bằng tổng mức rủi ro hoặc tổng chi phí của hệ thống.**

## 5. Khi nào nợ có chủ đích là lựa chọn hợp lý?

Một quyết định đánh đổi có thể phù hợp khi:

1. **Mục tiêu ngắn hạn rõ và có giá trị:** ví dụ ra bản thử nghiệm để xác minh người dùng cần tính năng nào.
2. **Giải pháp vẫn đúng trong phạm vi công bố:** không làm sai bất biến tiền, quyền, dữ liệu và bảo mật cơ bản.
3. **Chi phí của phương án tổng quát hiện còn cao hoặc bất định:** ví dụ chưa biết có bao nhiêu chính sách tiền tệ cần hỗ trợ.
4. **Đường chuyển đổi có thể thực hiện được:** thiết kế tránh khóa chặt dữ liệu hoặc API theo cách không thể di chuyển.
5. **Có tín hiệu khiến quyết định phải được xem lại:** chuẩn bị phục vụ tiền tệ thứ hai, tăng số tenant, số lần sửa bản sao, p95 vượt ngưỡng...
6. **Có người chịu trách nhiệm theo dõi và ngân sách/ràng buộc thích hợp:** tránh “để sau” vô thời hạn.

### Ví dụ: không tổng quát hóa trước khi có thông tin

Ở bản thử nghiệm chỉ có VND, một lớp `VndPricing` với phép toán nguyên và chính sách làm tròn rõ có thể **đơn giản hơn** một framework hỗ trợ 100 loại tiền tệ, plug-in thuế, reflection và cấu hình động.

Việc chưa xây framework tổng quát không tự động là nợ. Nó trở thành **một giới hạn gây chi phí** khi yêu cầu mới thực sự đến hoặc khi có bằng chứng cụ thể rằng các giả định VND-only đang lan sang những chỗ khó thay đổi.

### Điều không được lấy “nợ có chủ đích” làm lý do

Không nên trì hoãn xử lý:

- Truy cập dữ liệu của người khác hoặc tenant khác do thiếu kiểm tra quyền.
- Mất dữ liệu, ghi sai giao dịch hoặc nhân đôi thanh toán không kiểm soát.
- Lộ thông tin nhạy cảm trong log/API.
- Bỏ qua lỗi hạ tầng rồi báo thành công giả.
- Thiếu kiểm soát tối thiểu đối với một rủi ro đã được xác định là không thể chấp nhận.

Nên quản lý những vấn đề này theo **mức độ nghiêm trọng, nghĩa vụ và chính sách rủi ro**; không biến “technical debt” thành nhãn giảm ưu tiên.

## 6. Ví dụ Java: nhân bản quy tắc có thể tạo lãi nợ

Giả sử một hệ thống có hai luồng: **checkout** và **báo giá**. Ban đầu mỗi luồng tính tổng theo quy tắc VIP 10% từ 1.000.000 VND trở lên.

Hai cách thực hiện được viết ở hai nơi (rút gọn):

~~~java
// Trong CheckoutService:
long amountForCheckout(long subtotalVnd, boolean vip) {
    if (vip && subtotalVnd >= 1_000_000L) {
        return subtotalVnd - subtotalVnd / 10;
    }
    return subtotalVnd;
}
~~~

~~~java
// Trong QuoteService:
long amountForQuote(long subtotalVnd, boolean vip) {
    if (vip && subtotalVnd > 1_000_000L) {
        return subtotalVnd - subtotalVnd / 10;
    }
    return subtotalVnd;
}
~~~

Đây là **phản ví dụ**. Vì một bên dùng `>=` và bên kia dùng `>`, tổng đúng **1.000.000 VND** cho hai kết quả khác nhau. Nếu nghiệp vụ yêu cầu “từ ngưỡng trở lên”, báo giá đã sai. Nếu cả hai từng giống nhau nhưng một bản sao bị sửa thiếu, đó là dấu hiệu chi phí lặp lại của việc nhân bản đã biến thành lỗi.

Điều cần phân biệt:

- **Nợ cấu trúc:** hai nơi cùng sở hữu một chính sách và phải sửa đồng thời.
- **Lỗi hiện tại:** báo giá và checkout đang khác nhau ở một trường hợp hợp lệ.
- **Giải pháp:** bảo vệ tính đúng đắn bằng test, sau đó quyết định ranh giới sở hữu một chính sách để tránh tái phát.

Khi đã có lỗi tiền thực tế, **không chờ một đợt “trả nợ” tùy ý** mới kiểm soát nó. Cần theo quy trình xử lý sự cố/defect phù hợp, đồng thời giảm nguyên nhân cấu trúc.

## 7. Giảm nợ có mục tiêu bằng một hợp đồng tính giá

Giả sử đã xác nhận chính sách của ví dụ:

- `subtotalVnd` là số nguyên VND không âm.
- Khách VIP có tổng **từ 1.000.000 VND trở lên** được giảm 10%.
- Tiền giảm tính bằng phép chia nguyên `subtotalVnd / 10`, tức làm tròn xuống số VND giảm.
- Hai luồng checkout và báo giá phải dùng **cùng kết quả** cho cùng đầu vào.

Có thể đặt logic ở một thành phần nhỏ, có tên rõ, và để các luồng gọi theo cùng hợp đồng:

~~~java
final class VndPricing {
    private static final long VIP_THRESHOLD_VND = 1_000_000L;

    private VndPricing() {}

    static long amountDueVnd(long subtotalVnd, boolean vip) {
        if (subtotalVnd < 0) {
            throw new IllegalArgumentException("Negative subtotal");
        }

        if (vip && subtotalVnd >= VIP_THRESHOLD_VND) {
            return subtotalVnd - subtotalVnd / 10;
        }
        return subtotalVnd;
    }
}
~~~

Lớp này không kết nối database, không gửi thanh toán và không giữ trạng thái mutable. Nó gom **một quy tắc đã được xác nhận**, không phải “thêm abstraction vì code bị lặp hai dòng”.

Phía gọi sử dụng:

~~~java
// Mã minh họa; biến subtotalVnd và vip do các luồng cung cấp.
long checkoutAmount = VndPricing.amountDueVnd(subtotalVnd, vip);
long quotedAmount = VndPricing.amountDueVnd(subtotalVnd, vip);
~~~

Đây là ví dụ về **một nguồn chính sách**. Trong ứng dụng thật, hợp đồng còn phải quy định thuế, phí, voucher khác, hoàn tiền, giới hạn giá trị và tính ổn định của báo giá theo thời gian. Việc thống nhất một phương thức không tự giải quyết tranh chấp trạng thái hay thanh toán trùng.

### Kiểm thử cho quy tắc đã hợp nhất

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class VndPricingTest {
    @Test
    void appliesVipDiscountAtExactThreshold() {
        assertEquals(900_000L,
                VndPricing.amountDueVnd(1_000_000L, true));
    }

    @Test
    void doesNotDiscountVipBelowThreshold() {
        assertEquals(999_999L,
                VndPricing.amountDueVnd(999_999L, true));
    }

    @Test
    void doesNotDiscountNonVip() {
        assertEquals(1_500_000L,
                VndPricing.amountDueVnd(1_500_000L, false));
    }

    @Test
    void makesTheIntegerRoundingRuleObservable() {
        assertEquals(900_005L,
                VndPricing.amountDueVnd(1_000_005L, true));
    }

    @Test
    void rejectsInvalidNegativeSubtotal() {
        assertThrows(IllegalArgumentException.class,
                () -> VndPricing.amountDueVnd(-1L, true));
    }
}
~~~

Test ở đúng ngưỡng xác nhận phần lỗi cũ. Nhưng **chỉ unit test chưa chứng minh** cả checkout và báo giá thật đã chuyển sang gọi `VndPricing`, JSON/DB vẫn giữ đúng đơn vị, hoặc adapter thanh toán dùng số tiền cuối thay vì subtotal. Vì thế cần kiểm thử component/integration tại các ranh giới quan trọng, nhất là khi các luồng có side effect.

### Tránh biến giảm nợ thành breaking change âm thầm

Một số hành vi cũ có thể đang sai hoặc mơ hồ. Khi hợp nhất, phải phân biệt:

- **Refactor bảo toàn hành vi:** đổi cấu trúc nhưng giữ hợp đồng đã xác nhận.
- **Sửa lỗi:** thay kết quả sai (ví dụ `>` thành `>=`) theo đặc tả.
- **Thay đổi chính sách:** nghiệp vụ quyết định mức giảm/đơn vị khác.

Gộp cả ba vào một PR với mô tả “cleanup code” khiến reviewer khó đánh giá rủi ro. Khi cần, hãy tách thành các bước có test và tài liệu phù hợp.

## 8. Khi bối cảnh đổi: VND-only sang nhiều tiền tệ

Ví dụ `VndPricing` ở phần 7 có thể phù hợp khi hệ thống chỉ phục vụ VND. Nếu công ty quyết định nhận cả JPY và USD, câu hỏi không còn là “đặt lại tên biến”, mà là **hợp đồng dữ liệu và chính sách nào đang thay đổi?**

Các câu hỏi phải giải quyết:

- Mỗi giá trị tiền thuộc currency nào? Có được cộng hai currency khác nhau không?
- Số tiền dùng đơn vị nhỏ nhất hay đơn vị hiển thị? Có tiền tệ có số chữ số thập phân khác nhau không?
- Quy tắc làm tròn ở từng bước, từng thuế/phí và tỷ giá ra sao?
- Thời điểm chọn tỷ giá nào, có cần lưu lịch sử để đối soát không?
- API và dữ liệu đã lưu chứa tiền VND nguyên có còn được client cũ hiểu đúng không?
- Những lớp nào đang giả định ngầm `long amountVnd` hoặc ngưỡng `1_000_000L`?

### Thay đổi mô hình đúng mức

Có thể tạo kiểu biểu diễn tiền có currency tường minh:

~~~java
import java.math.BigDecimal;
import java.util.Currency;
import java.util.Objects;

record Money(Currency currency, BigDecimal amount) {
    Money {
        Objects.requireNonNull(currency, "currency");
        Objects.requireNonNull(amount, "amount");
    }

    Money add(Money other) {
        Objects.requireNonNull(other, "other");
        if (!currency.equals(other.currency())) {
            throw new IllegalArgumentException(
                    "Cannot add different currencies");
        }
        return new Money(currency, amount.add(other.amount()));
    }
}
~~~

Đây mới chỉ là **hạt nhân mô hình**, không phải thư viện tiền tệ hoàn chỉnh. `BigDecimal` giúp tính thập phân chính xác theo phép toán phù hợp, nhưng **không tự quy định** rounding mode, số chữ số hợp lệ, chính sách tỷ giá, thuế/phí hoặc cách hiển thị. Không nên suy rằng cùng `Money` dùng được cho mọi phép tính và mọi currency mà không thêm bất biến tương ứng.

Khi chuyển đổi, cần kiểm tra dữ liệu và consumer cũ:

1. Phân biệt VND nguyên đã lưu với giá trị thập phân trong kiểu mới.
2. Chọn cách biểu diễn và versioning API phù hợp; không tự đổi ý nghĩa một field cũ.
3. Di chuyển và đối soát dữ liệu theo từng giai đoạn.
4. Chạy test trên nhiều currency, điều kiện biên, làm tròn và dữ liệu lịch sử.
5. Duy trì đường đọc/ghi tương thích trong thời gian cần thiết, với cơ chế rollback phù hợp.
6. Đo tác động về hiệu năng/tài nguyên nếu xử lý tiền hoặc truy vấn thay đổi đáng kể.

**Một giải pháp ban đầu chỉ hỗ trợ VND không nhất thiết là “thiết kế tồi”**. Khi yêu cầu mới xuất hiện, chi phí chuyển đổi là điều cần quản lý; đánh giá trách nhiệm dựa vào dữ liệu hiện có và những giả định được công bố lúc ra quyết định.

## 9. Phát hiện nợ ngoài dự kiến qua dấu hiệu thực tế

Một số dấu hiệu gợi ý nợ đang tích lũy:

| Dấu hiệu | Câu hỏi cần kiểm chứng |
| --- | --- |
| Mỗi PR sửa chính sách phải sửa nhiều lớp cùng logic | Có bản sao nào không nhất quán? Chính sách nên có một chủ sở hữu không? |
| Một thay đổi nhỏ kéo theo rất nhiều mock, wiring hoặc migration | Ranh giới trách nhiệm/phụ thuộc có phù hợp không? |
| Lỗi cũ tái xuất hiện sau khi sửa ở nơi khác | Có test hoặc contract nào thiếu ở ranh giới chung? |
| Người mới mất nhiều ngày mới biết nơi sửa đúng | Tên, module và tài liệu có làm lộ chủ sở hữu không? |
| CI rất chậm hoặc thường flaky khiến nhóm ngại thay đổi | Vòng phản hồi và khả năng chẩn đoán có phải “lãi” của thiết kế test không? |
| Khó tách một tính năng khỏi quyền admin toàn hệ thống | Có phụ thuộc bảo mật quá rộng cần xử lý theo rủi ro không? |
| Dữ liệu phải chuyển đổi thủ công mỗi lần thêm tenant | Giả định single-tenant có còn phù hợp không? |
| Monitoring không thể phân biệt timeout với “không có dữ liệu” | Hợp đồng lỗi có đang che dấu thông tin quan trọng? |

Những dấu hiệu này **không phải kết luận tự động**. Chậm CI có thể do tài nguyên runner thiếu, không do kiến trúc test. Nhiều mock có thể phản ánh component tích hợp hợp lệ. Cần **xác minh nguyên nhân cụ thể** trước khi gắn nhãn nợ.

### Dùng lịch sử thay đổi nhưng không dùng để đổ lỗi

Những file hay thay đổi cùng nhau, vùng có lỗi lặp lại hoặc test thường thất bại có thể là nơi cần xem lại. Nhưng tần suất commit cao đôi khi chỉ cho biết tính năng đang phát triển nhanh; ít commit không tự chứng minh thiết kế tốt.

Dữ liệu nên hỗ trợ câu hỏi: “Chúng ta mất thời gian ở đâu, thay đổi nào rủi ro?” — không biến `git blame` thành phương pháp tìm “người tạo nợ” để xếp hạng cá nhân.

## 10. Ghi nhận nợ có chủ đích thành quyết định có thể xem lại

Một mục nợ có chủ đích nên được **diễn đạt như quyết định có điều kiện**, không chỉ là bình luận `// TODO: refactor later`.

Mẫu ngắn có thể dùng trong issue, architecture decision record (ADR) hoặc tài liệu nhóm:

~~~text
Tiêu đề:
  Tạm giữ mô hình giá VND-only cho bản thử nghiệm.

Bối cảnh và mục tiêu:
  Trong 3 tháng đầu, tất cả đơn thuộc một thị trường dùng VND.
  Cần triển khai để kiểm chứng nhu cầu thay vì thiết kế đa tiền tệ sớm.

Quyết định hiện tại:
  Lưu số tiền nguyên VND, tên biến/field có hậu tố Vnd.

Phương án khác đã xem xét:
  Tạo Money + currency-aware pricing ngay từ đầu.

Lý do chấp nhận đánh đổi:
  Yêu cầu đa tiền tệ chưa xác định; tránh abstraction phức tạp chưa cần.

Giới hạn không được vi phạm:
  Giá và giảm giá phải đúng; có kiểm tra tràn, test ranh giới,
  quyền truy cập và đối soát thanh toán.

Rủi ro/chí phí dự kiến:
  Khi hỗ trợ currency thứ hai phải di chuyển mô hình, API và dữ liệu cũ.

Điểm kích hoạt xem lại:
  Có kế hoạch phát hành cho thị trường dùng currency thứ hai,
  hoặc một tích hợp mới yêu cầu dữ liệu nhiều currency.

Chủ sở hữu:
  Nhóm sở hữu pricing; cập nhật khi ownership thay đổi.

Cách giảm nợ:
  Thiết kế Money, làm rõ rounding/exchange, kiểm tra contract,
  migration dữ liệu và rollout tương thích.

Ngày xem lại:
  Trước mốc lập kế hoạch phát hành đa tiền tệ hoặc theo lịch đã thống nhất.

Trạng thái:
  Accepted / Needs review / In progress / Resolved.
~~~

Đây là **mẫu**, không phải quyết định đang tồn tại trong dự án này. Không bắt buộc mọi mục nhỏ đều có ADR dài. Điều cần giữ là **giả định, trade-off, người phụ trách và điều kiện đổi quyết định**.

### Tín hiệu kích hoạt hữu ích hơn một lời hứa chung chung

“Refactor khi rảnh” thường không có điểm bắt đầu. Tín hiệu tốt hơn có thể là:

- Trước khi thêm tenant/currency/đối tác thứ hai.
- Khi một chính sách phải sửa ở nhiều hơn một ranh giới thường xuyên.
- Khi một lỗi cùng nguyên nhân đã tái diễn và có chi phí đáng kể.
- Trước khi mở API cho client độc lập.
- Khi thời gian phản hồi kiểm thử vượt mục tiêu và gây ảnh hưởng thực.
- Khi giả định bảo mật/tuân thủ hoặc khối lượng dữ liệu đã đổi.

Có thể đặt **ngày xem lại** ngoài trigger để không bỏ quên, nhưng thời gian chỉ là lời nhắc; quyết định ưu tiên vẫn cần dữ liệu và rủi ro thực tế.

## 11. Ưu tiên trả nợ theo lợi ích và rủi ro, không theo số “code smell”

Một danh sách chứa 300 cảnh báo static analysis chưa chắc đáng ưu tiên hơn một mục làm sai trạng thái thanh toán. Ngược lại, một module có nhiều TODO nhưng ít thay đổi có thể cần giám sát hơn là viết lại.

Để ưu tiên, cân nhắc:

1. **Tác động nếu giữ nguyên:** lỗi nghiệp vụ, bảo mật, độ tin cậy, thời gian sửa, nguy cơ phát hành.
2. **Tần suất phải chạm vào khu vực:** nhiều thay đổi tương lai khiến chi phí lặp lại quan trọng hơn.
3. **Bằng chứng chi phí đã xảy ra:** PR, incident, thời gian điều tra, thao tác thủ công.
4. **Khả năng giảm rủi ro bằng bước nhỏ:** test, loại bản sao, làm rõ hợp đồng, giới hạn quyền.
5. **Chi phí/chuyển đổi của phương án mới:** migration, phụ thuộc, downtime, API compatibility, kỹ năng, chi phí review.
6. **Độ không chắc chắn:** có bằng chứng hay chỉ là dự đoán; cần thu thêm dữ liệu gì?
7. **Cửa sổ cơ hội:** đang sửa đúng module, chuẩn bị thay đổi lớn hoặc có thể giảm nợ an toàn cùng một task.

### Ma trận quyết định minh họa

| Mục nợ/rủi ro | Lãi hoặc rủi ro quan sát | Chi phí/độ khó xử lý | Hướng ưu tiên |
| --- | --- | --- | --- |
| Ngưỡng VIP khác giữa báo giá và thanh toán | Đã có hành vi sai với đầu vào hợp lệ | Bổ sung test và hợp nhất chính sách ở mức vừa phải | **Sửa defect theo độ nghiêm trọng trước**, rồi giảm nhân bản |
| Ba adapter có cùng đoạn mapping, thay đổi vài lần/năm | Chưa có sai khác, mỗi lần sửa mất thêm thời gian | Refactor nhỏ, test sẵn | Làm khi gần khu vực hoặc ở đợt cải tiến có mục tiêu |
| Lớp truy vấn ít thay đổi nhưng khá dài | Chưa có bằng chứng gây lỗi/chậm sửa | Tái cấu trúc toàn diện rủi ro cao | Giữ nguyên, theo dõi; không refactor vì số dòng |
| Mô hình VND-only trước yêu cầu đa tiền tệ | Yêu cầu mới sắp triển khai, nhiều API cần đổi | Migration phức tạp, cần hợp đồng | Bắt đầu thiết kế/migration theo lộ trình sản phẩm |
| Bỏ sót phân quyền theo tenant ở một route | Nguy cơ lộ dữ liệu ngoài quyền | Có thể cần hotfix và kiểm thử rộng | Theo quy trình bảo mật, **không** trì hoãn như nợ thông thường |
| Suite tích hợp flaky làm PR phải chạy lại nhiều lần | CI chậm, phản hồi không đáng tin | Cần cô lập dữ liệu và test double phù hợp | Ưu tiên nếu đang cản trở nhiều thay đổi |

Các mô tả không phải score khách quan. Nếu muốn chấm điểm, phải giải thích công thức và dữ liệu đầu vào, tránh tạo độ chính xác giả bằng cách nhân vài nhãn “cao/trung bình/thấp”.

### Khi không trả nợ ngay là quyết định hợp lý

Giữ một mục nợ có thể đúng khi **chi phí thay đổi cao, lợi ích chưa chắc**, hoặc khu vực sắp bị loại bỏ. Khi đó nên ghi rõ giả định, rủi ro chấp nhận và điều kiện xem lại. “Không sửa bây giờ” khác với “không quản lý”.

## 12. Những chiến lược giảm nợ thường gặp

Không phải mọi mục nợ cần một cuộc viết lại lớn. Có thể lựa chọn theo phạm vi:

| Chiến lược | Khi phù hợp | Ví dụ | Điều cần bảo vệ |
| --- | --- | --- | --- |
| **Làm rõ hợp đồng** | Vấn đề chủ yếu là cách hiểu dữ liệu/lỗi | Phân biệt not found và timeout | API/consumer tương thích |
| **Bổ sung test đặc trưng hành vi** | Chưa chắc mã hiện làm gì | Test ở ngưỡng VIP, trạng thái thanh toán | Test phản ánh hợp đồng được xác nhận |
| **Loại bỏ nhân bản có chọn lọc** | Một chính sách bị sửa nhiều nơi | Đưa tính giá vào `VndPricing` | Các luồng thật gọi cùng chính sách |
| **Tách trách nhiệm dần** | Lớp lớn thường xuyên phải sửa vì nhiều lý do | Chuyển serialize ra adapter | Coupling mới không tăng quá mức |
| **Áp dụng adapter/compatibility layer** | Bên ngoài vẫn dựa hợp đồng cũ | Vẫn xuất `totalVnd` khi thêm `amountDueVnd` | Bảo đảm dữ liệu cùng ý nghĩa |
| **Thay đổi dữ liệu theo giai đoạn** | Domain/schema không còn phù hợp | Thêm currency, chuyển đổi bản ghi | Đối soát, rollback, dữ liệu lịch sử |
| **Giới hạn/phòng vệ tạm thời** | Không thể di chuyển ngay nhưng rủi ro cần giảm | Validation, timeout, quyền, feature flag | Không che lỗi thực hay đưa ra quyền sai |
| **Thay thế thành phần** | Cấu trúc hiện tại gây chi phí liên tục và khó cải tiến | Thay thư viện không còn được hỗ trợ | Migration, test, hiệu năng và vận hành |
| **Giữ nguyên có giám sát** | Lãi thấp, vùng ổn định hoặc sắp ngừng dùng | Module cũ chỉ đọc dữ liệu lịch sử | Quyền truy cập, sự cố và trigger xem lại |

**Refactor không được đánh đồng với sửa lỗi nghiệp vụ.** Khi chuyển chức năng, cần phân biệt hành vi đang được bảo đảm với những lỗi đã nhận diện cần sửa riêng.

### “Boy Scout Rule” có giới hạn

Cải thiện nhỏ ở khu vực vừa chạm tới có thể tiết kiệm thời gian: đổi tên biến mơ hồ, thêm test biên, tách một hàm có trách nhiệm rõ. Nhưng không nên biến mọi PR thành cơ hội format cả module hoặc đổi public contract. **Quy mô cải tiến phải tương xứng với rủi ro và khả năng review**.

## 13. Kế hoạch giảm nợ theo từng bước với tính đúng đắn được bảo vệ

Ví dụ một nhóm cần giảm nợ nhân bản chính sách giá và chuẩn bị hỗ trợ currency thứ hai:

~~~mermaid
flowchart TD
    A["Quan sát lãi/rủi ro"] --> B["Xác nhận hợp đồng và phạm vi"]
    B --> C["Test hành vi và ranh giới quan trọng"]
    C --> D["Giảm nhân bản / làm rõ chủ sở hữu"]
    D --> E["Đo lại và giám sát"]
    E --> F{"Bối cảnh mới đã yêu cầu đổi mô hình?"}
    F -->|"Chưa"| G["Giữ đơn giản, ghi trigger xem lại"]
    F -->|"Có"| H["Thiết kế kiểu tiền + migration/compatibility"]
    H --> I["Rollout từng giai đoạn, kiểm thử dữ liệu"]
    I --> J["Đối soát và thu hẹp hợp đồng cũ khi an toàn"]
~~~

Quy trình không yêu cầu phải làm tất cả ngay. Có thể triển khai từng bước để học từ bằng chứng:

1. **Khoanh vùng quyết định và hành vi:** chính sách giảm giá, đơn vị tiền, đối tượng sở hữu code.
2. **Xác nhận đặc tả:** điều kiện ngưỡng, làm tròn, ưu đãi chồng lấp, phạm vi đầu vào hợp lệ.
3. **Bảo vệ bằng test:** unit ở ngưỡng, component cho báo giá/checkout, contract/API với client, integration DB/gateway khi liên quan.
4. **Tách thay đổi cấu trúc khỏi thay đổi hành vi:** xử lý lỗi hiện tại có ghi nhận, không giấu nó trong “cleanup”.
5. **Đưa các luồng về một chính sách:** thay từng caller, so sánh kết quả, loại bản sao sau khi đã xác minh.
6. **Theo dõi kết quả:** số nơi cần sửa, thời gian PR, lỗi lặp lại và ảnh hưởng đến code review.
7. **Chỉ khi yêu cầu đa currency rõ:** thiết kế domain Money, API mới, lộ trình dữ liệu và tính tương thích.
8. **Triển khai và đối soát:** tránh xóa biểu diễn cũ khi còn consumer hoặc bản ghi lịch sử chưa được chuyển.
9. **Xem lại quyết định nợ:** cập nhật trạng thái, ghi bài học, không giữ issue mở chỉ vì “nợ đã tồn tại lâu”.

### Kiểm thử cần đi cùng từng thay đổi

| Thay đổi | Kiểm thử nên có | Điều test ở cấp thấp không chứng minh |
| --- | --- | --- |
| Hợp nhất hàm giảm giá | Đúng/ngay dưới/ngay trên ngưỡng, không VIP, dữ liệu âm, làm tròn | Checkout và báo giá thật đều đã gọi hàm mới |
| Thay gọi hàm trong checkout | Component test kiểm tra số tiền cuối truyền vào adapter | Gateway thật dùng đúng đơn vị và idempotency |
| Đổi field API về tiền | Contract test cho client cũ/mới, serialization thực | Mọi client độc lập đã nâng cấp |
| Thêm currency trong dữ liệu | Migration test, đối soát số tiền cũ/mới, test lịch sử | Mọi tình huống vận hành production đều an toàn |
| Đổi query hoặc caching | Integration/load test với tenant, dữ liệu và tải đại diện | Mọi mẫu tải và tất cả sự cố ngoài đời đã được thử |

Không nên lấy kết quả compile/formatter/linter thành bằng chứng đầy đủ rằng một đợt giảm nợ không phá hành vi. Chúng quan trọng nhưng bảo vệ những thuộc tính khác với contract và dữ liệu thật.

## 14. Nợ kỹ thuật cần theo dõi như một danh mục quyết định, không phải bảng xếp hạng cá nhân

Một danh mục nợ hữu ích không cần đo mọi code smell bằng một điểm số chung. Nó cần trả lời:

- **Mục tiêu hoặc rủi ro nào bị ảnh hưởng?**
- **Ai đang sở hữu khu vực hệ thống** và có quyền ra quyết định?
- **Giả định nào vẫn đúng hoặc đã thay đổi?**
- **Chi phí đã xảy ra**, ví dụ thời gian sửa, incident hay phần việc bị chặn?
- **Tác động nếu không xử lý** và chi phí/điểm nguy hiểm của chuyển đổi?
- **Trigger** và thời điểm xem lại?
- **Kế hoạch kiểm chứng** sau khi xử lý?
- **Có lộ trình thay thế/tháo bỏ** khiến cải tiến toàn diện không còn hiệu quả không?

### Mẫu bảng quản lý nợ

| Mục | Nguồn gốc | Bằng chứng “lãi”/rủi ro | Trigger | Quyết định hiện tại |
| --- | --- | --- | --- | --- |
| Logic VIP ở nhiều luồng | Chưa rõ; phát hiện khi có sai ngưỡng | Kết quả báo giá khác checkout | Khi sửa chính sách/đang có defect | Sửa lỗi và hợp nhất có test |
| Giá chỉ dùng VND | Có chủ đích, sau đó bối cảnh đổi | Thị trường mới yêu cầu USD | Trước thiết kế sản phẩm đa currency | Lập kế hoạch migration |
| Adapter cũ dài | Tích lũy theo thời gian | Chưa có chi phí cụ thể | Khi sửa nhiều hoặc xuất hiện incident | Giữ nguyên, quan sát |
| CI integration flaky | Ngoài dự kiến | Nhiều lần phải retry và khó tìm lỗi | Khi ảnh hưởng tốc độ phát hành | Cô lập dữ liệu, cải thiện test |
| API v1 giữ tên JSON cũ | Giới hạn vì tương thích | Client ngoài vẫn dùng trường | Khi hết thời hạn hỗ trợ đã công bố | Duy trì adapter, không xóa sớm |

Trong danh mục này, “**nguồn gốc**” cung cấp bối cảnh, còn “**bằng chứng và quyết định**” hỗ trợ hành động. Không nên biến mục nợ thành bảng quy trách nhiệm theo tên người từng commit.

### Chỉ số hỗ trợ theo dõi, không thay thế đánh giá

Có thể theo dõi thời gian build, tỷ lệ flaky, thời gian hiểu module, lỗi lặp lại hoặc số lần sửa cùng một quy tắc ở nhiều nơi. Nhưng phải ghi **cách tính, mẫu số và giới hạn**. Một chỉ số giảm sau refactor chưa chứng minh refactor là nguyên nhân duy nhất nếu đồng thời khối lượng thay đổi, dữ liệu hay CI cũng đổi.

## 15. Khi nào nợ không đáng trả hoặc trả quá sớm trở thành vấn đề?

### 15.1. Module ổn định và ít thay đổi

Một lớp 600 dòng xử lý định dạng báo cáo cũ có test tốt, không phát sinh bug và sẽ bị thay thế trong quý tới. Tách nó thành 12 lớp hôm nay có thể tạo **chi phí review, regression và migration** cao hơn lợi ích.

### 15.2. Chưa có yêu cầu để chọn abstraction đúng

Viết một framework đa tiền tệ trước khi biết sản phẩm thực sự bán tại đâu, chịu thuế thế nào và API nào cần dùng có thể khiến nhóm thiết kế trên giả định sai. Sự tổng quát hóa quá sớm cũng tạo **nợ mới** khi abstraction không còn khớp thực tế.

### 15.3. Tập trung sai loại nợ

Format code hoặc đổi tên toàn bộ lớp không giải quyết lỗi timeout bị trả `Optional.empty()`. Cần nhắm vào **chi phí hoặc rủi ro gây vấn đề**.

### 15.4. Tối ưu cấu trúc nhưng phá hợp đồng

Xóa field `totalVnd` để chuẩn hóa tên thành `amountDueVnd` có thể làm client cũ lỗi. Khi trả nợ nội bộ, **tính tương thích API và dữ liệu lịch sử** vẫn là ràng buộc cần bảo vệ.

### 15.5. Biến “technical debt” thành từ đồng nghĩa mọi bất đồng thiết kế

Hai lập trình viên có thể thích những phong cách khác nhau. Muốn gọi một lựa chọn là nợ, hãy chỉ ra **chi phí/rủi ro hiện có hoặc có cơ chế hợp lý để dự đoán**, không chỉ nói “tôi không thích mẫu này”.

Một cách phản hồi có ích: “Mỗi lần thêm chính sách giảm giá, chúng ta sửa ba bản sao và đã bỏ sót một nơi; chi phí này có thể giảm bằng một nguồn quy tắc chung và test tích hợp”, thay vì “lớp này xấu, viết lại đi”.

## 16. Câu hỏi code review giúp tìm đúng nợ

Khi đọc một thay đổi Java, có thể hỏi:

1. **Phạm vi hiện tại là gì?** Giải pháp chỉ hỗ trợ trường hợp nào, và điều đó có được ghi rõ không?
2. **Hạn chế là chủ ý hay phát sinh?** Nếu chủ ý, vì sao chọn và điều kiện xem lại là gì?
3. **Điều gì khiến mã khó thay đổi?** Logic nhân bản, trạng thái chung, phụ thuộc chéo, test thiếu hay API công khai?
4. **Chúng ta đã phải trả “lãi” bao lần?** Các PR, incident hoặc bước sửa thủ công nào minh họa?
5. **Bối cảnh nào đã đổi?** Người dùng, số tenant, tiền tệ, SLA, lưu lượng, công nghệ hay nghĩa vụ bảo mật?
6. **Giải pháp thay thế có giảm rủi ro thật không?** Hay chỉ tạo thêm abstraction và coupling?
7. **Có thể giảm từng bước không?** Bổ sung test, di chuyển một caller, thêm adapter, loại bản sao?
8. **Điều gì tuyệt đối không được phá?** Quyền, tính đúng đắn của tiền, transaction, API compatibility, dữ liệu lịch sử?
9. **Làm sao biết cải tiến thành công?** Test, đo phản hồi, số lỗi lặp lại hay một công việc tương lai dễ thực hiện hơn?
10. **Ai quyết định và khi nào xem lại?** Quyền sở hữu theo thành phần, không tìm người để đổ lỗi.

Một nhận xét review tốt có **quan sát, rủi ro, đề xuất và phương pháp kiểm chứng**, không chỉ nhắc từ “tech debt”.

### Ví dụ nhận xét mang tính xây dựng

> “Điều kiện VIP hiện có ở cả checkout và quote, hai nơi đang khác nhau tại đúng ngưỡng 1.000.000 VND. Đây vừa là lỗi tính giá cần sửa vừa là dấu hiệu nợ nhân bản. Có thể xác nhận quy tắc với sản phẩm, thêm test ngưỡng cho hai luồng, sau đó đưa về một `VndPricing` và kiểm tra adapter thanh toán không?”

Nhận xét này không đổ lỗi cho tác giả, và không nhầm công việc sửa lỗi cấp bách với hoạt động refactor dài hạn.

## 17. Những ngộ nhận thường gặp

**“Mọi nợ kỹ thuật đều là mã chất lượng kém do ai đó làm ẩu.”** Có nợ được chọn thận trọng và có nợ xuất hiện vì bối cảnh đổi; cần hiểu thông tin tại thời điểm ra quyết định.

**“Nợ có chủ đích luôn được phép trì hoãn.”** Không nếu nó vi phạm ràng buộc an toàn, bảo mật, tính đúng đắn hoặc nghĩa vụ hiện tại.

**“Mã cũ chắc chắn là nợ.”** Tuổi đời không đo chi phí thay đổi; một thành phần cũ ổn định và có test có thể không cần sửa.

**“Tất cả TODO và cảnh báo linter là nợ phải trả ngay.”** Nhiều cảnh báo chỉ là tín hiệu cần phân loại; mức ưu tiên phụ thuộc tác động và chi phí thực.

**“Trả hết nợ một lần sẽ cho kiến trúc sạch vĩnh viễn.”** Bối cảnh tiếp tục thay đổi; thiết kế mới cũng có thể tạo trade-off. Mục tiêu là quản lý chất lượng theo thời gian, không tuyên bố hết nợ mãi mãi.

**“Nợ có chủ đích chỉ cần thêm comment // TODO.”** Cần hiểu giới hạn, lý do, trigger, chủ sở hữu và cách kiểm tra khi đổi quyết định.

**“Tổng điểm code smell quyết định ưu tiên.”** Một lỗi tiền hay lộ dữ liệu có thể quan trọng hơn hàng trăm cảnh báo style.

**“Refactor nghĩa là sửa luôn quy tắc nghiệp vụ.”** Refactor nên bảo vệ hành vi đã xác nhận; sửa lỗi/đổi chính sách cần mô tả và test có chủ đích.

**“Nếu metric cải thiện sau refactor, chắc chắn nguyên nhân là refactor.”** Còn phải xét thay đổi workload, CI, phạm vi mã và các can thiệp đồng thời.

**“Nợ làm code khó sửa nên cứ tăng số lớp là tốt.”** Quá nhiều lớp và abstraction không đúng có thể tăng coupling và nợ mới.

**“Vì quyết định ban đầu hợp lý nên không được gọi là nợ hôm nay.”** Một lựa chọn có thể hợp lý lúc trước nhưng nay tạo chi phí do nhu cầu đã đổi; thừa nhận điều đó không phủ nhận công sức ban đầu.

## 18. Bài tập thực hành

### Bài tập A — phân loại nguồn gốc và ưu tiên

Xét bốn tình huống:

1. Bản thử nghiệm chỉ hỗ trợ VND, có ghi kế hoạch hỗ trợ USD khi mở thị trường.
2. Hai endpoint vô tình có hai cách xử lý timeout khác nhau; một bên trả empty thay vì lỗi.
3. Chương trình từng phục vụ một tenant nay phải phục vụ nhiều tenant độc lập.
4. Một job nền dùng token admin vĩnh viễn và có khả năng xóa mọi bảng, dù chỉ cần đọc một view.

Với mỗi tình huống, hãy nêu: nguồn gốc nợ (có thể nhiều loại), lỗi/rủi ro hiện tại, thông tin còn thiếu, và **quyết định an toàn** trước mắt. Tình huống nào không nên đưa vào backlog “làm khi rảnh”?

### Bài tập B — tìm gốc và lãi

Một nhóm mất khoảng hai giờ mỗi lần đổi chính sách giảm giá vì phải sửa ba bản sao; năm gần đây nhóm thực hiện sáu thay đổi tương tự. Một refactor dự kiến mất ba ngày làm việc nhưng còn rủi ro migration/kiểm thử.

Hãy:

- Tính **thời gian lặp lại đã quan sát** từ số liệu minh họa.
- Giải thích vì sao số đó **chưa phải tổng chi phí nợ** (còn lỗi, kiểm thử, cơ hội và sự bất định).
- Xác định dữ liệu nào cần để ước lượng giá trị của việc refactor sớm.
- Đề xuất một bước nhỏ có lợi ích và ít rủi ro trước khi quyết định viết lại toàn bộ.

### Bài tập C — refactor không che lỗi

Từ hai hàm báo giá/checkout ở phần 6:

1. Chỉ ra giá trị đầu vào khiến chúng trả khác nhau.
2. Viết test mô tả chính sách đã xác nhận.
3. Đề xuất thứ tự sửa defect và gom logic.
4. Nêu test tích hợp chứng minh cả hai caller dùng cùng quy tắc.
5. Vì sao việc đổi `>=` và trích xuất hàm không nên được mô tả chung chung là “format cleanup”?

### Bài tập D — bối cảnh đổi

Một hệ thống đang lưu tiền như `long totalVnd`, nhưng sản phẩm chuẩn bị hỗ trợ nhiều tiền tệ và tỷ giá. Viết quyết định kỹ thuật ngắn gồm phương án, dữ liệu lịch sử, API tương thích, quy tắc làm tròn, cách rollout, test và điều kiện rollback.

### Bài tập E — phản biện một đề xuất trả nợ

Một thành viên muốn viết lại 20.000 dòng của module cũ vì “kiến trúc khó nhìn”. Module này chỉ được sửa một lần/năm và sắp bị thay thế.

Hãy đặt các câu hỏi về lãi nợ, rủi ro thực, chi phí chuyển đổi và thời hạn khai tử; đề xuất lựa chọn **không refactor ngay** nếu bằng chứng chưa đủ, nhưng vẫn giữ kiểm soát rủi ro hiện tại.

## 19. Checklist sử dụng khi ghi nhận và xử lý nợ kỹ thuật

### Hiểu đúng tình trạng

- [ ] Tôi phân biệt defect đang xảy ra, thiếu tính năng, giới hạn được chấp nhận và nợ kỹ thuật.
- [ ] Tôi xác định được mục đích ban đầu, thông tin sẵn có và bối cảnh hiện tại.
- [ ] Tôi không dùng nguồn gốc nợ để xếp hạng hoặc đổ lỗi cho cá nhân.
- [ ] Tôi biết ràng buộc nào không thể bị đánh đổi: tính đúng đắn, bảo mật, dữ liệu, quyền và hợp đồng thiết yếu.

### Đánh giá tác động

- [ ] Tôi có bằng chứng hoặc giả thuyết rõ về chi phí lặp lại (“lãi”).
- [ ] Tôi có ước lượng và độ bất định của chi phí xử lý (“gốc”).
- [ ] Tôi đã xét tần suất sửa code, mức phơi nhiễm và tác động nếu lỗi xảy ra.
- [ ] Tôi phân biệt chỉ số quan sát với kết luận nhân quả.
- [ ] Tôi xem xét khả năng giải pháp bị loại bỏ hoặc yêu cầu chưa đủ chắc chắn.

### Chọn hướng xử lý

- [ ] Tôi biết vì sao nên giữ, giảm từng bước, chuyển đổi lớn hoặc thay thế.
- [ ] Với nợ có chủ đích, có quyết định, chủ sở hữu, điểm kích hoạt và lịch xem lại.
- [ ] Với nợ ngoài dự kiến, có phân tích nguyên nhân hệ thống và phòng vệ ngăn tái diễn.
- [ ] Với bối cảnh mới, có xác nhận yêu cầu mới và kế hoạch tương thích/migration.
- [ ] Tôi có test bảo vệ hành vi hiện tại và test cho thay đổi dự kiến.
- [ ] Tôi không che một thay đổi nghiệp vụ hoặc API breaking trong PR “refactor”.
- [ ] Tôi theo dõi tác dụng phụ về coupling, CI, hiệu năng, tài nguyên và vận hành.
- [ ] Sau khi cải tiến, tôi cập nhật trạng thái và ghi lại bài học.

## 20. Câu hỏi tự kiểm tra

1. Nợ kỹ thuật khác defect, TODO và mã cũ như thế nào?
2. Vì sao một quyết định có chủ đích có thể hợp lý mà vẫn tạo chi phí tương lai?
3. Nợ ngoài dự kiến có nhất thiết chứng minh người viết thiếu năng lực không? Tại sao?
4. Nêu ví dụ một thiết kế tốt lúc ban đầu trở thành điểm nghẽn khi quy mô hoặc nghiệp vụ đổi.
5. Hai chiều “nhận thức rõ” và “thận trọng” giúp nhìn nguồn gốc nợ chính xác hơn ra sao?
6. Gốc nợ và lãi nợ là gì? Vì sao không thể dùng chúng như con số tài chính chắc chắn?
7. Trong ví dụ VIP, khác biệt giữa nợ nhân bản và defect ở ngưỡng là gì?
8. Tại sao unit test của `VndPricing` chưa đủ chứng minh toàn bộ luồng thanh toán đúng?
9. Khi mở rộng từ VND sang USD/JPY, ngoài kiểu `BigDecimal` còn phải thống nhất những chính sách nào?
10. Một TODO “refactor sau” đang thiếu những thông tin gì để được quản lý hữu ích?
11. Trường hợp nào nên giữ nợ có giám sát thay vì trả nợ ngay?
12. Vì sao xếp hạng nợ bằng số lượng code smell có thể khiến ưu tiên sai?
13. Bạn sẽ làm gì nếu một mục “nợ” đang gây lộ dữ liệu khách hàng?
14. Một thay đổi giảm thời gian CI sau refactor có chứng minh nguyên nhân duy nhất là refactor không?
15. Tại sao việc xóa field API cũ để thống nhất nội bộ có thể tạo thêm nợ hoặc lỗi?
16. Hãy kể một tình huống cả ba loại: có chủ đích, ngoài dự kiến và bối cảnh thay đổi cùng xuất hiện.
17. Nêu ba điều kiện kích hoạt cần xem lại một quyết định nợ có chủ đích.
18. Một cuộc viết lại toàn diện cần những bằng chứng nào trước khi ưu tiên thay vì thay đổi từng bước?
19. Khi nào nên giữ một adapter tương thích lâu hơn dự kiến?
20. Hãy viết một nhận xét code review đề xuất giảm nợ với bằng chứng, rủi ro và phương pháp kiểm chứng rõ ràng.

## Ghi nhớ

**Nợ kỹ thuật là chi phí và rủi ro của những quyết định hoặc giới hạn trong một bối cảnh nhất định, không phải nhãn đánh giá con người.** Có nợ được chấp nhận chủ đích, có nợ xuất hiện ngoài dự kiến, và có nợ nảy sinh vì yêu cầu thay đổi; các nguồn gốc này có thể giao nhau. Hãy phân biệt defect cấp bách với chi phí cấu trúc, ghi quyết định và điều kiện xem lại, theo dõi “lãi” bằng bằng chứng thực, ưu tiên theo tác động rồi giảm nợ theo bước có kiểm thử. Mục tiêu của `CODE_QUALITY_FUNDAMENTALS` không phải xóa sạch mọi dấu hiệu mã cũ, mà là giữ mã **đáng tin cậy, dễ hiểu và dễ thay đổi** khi hệ thống tiếp tục phát triển.
