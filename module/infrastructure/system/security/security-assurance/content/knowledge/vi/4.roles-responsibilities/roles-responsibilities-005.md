# Control owner: Người chịu trách nhiệm về kiểm soát bảo mật

## 1. Control owner là ai?

**Control owner** (người sở hữu kiểm soát) là **cá nhân hoặc vai trò được giao trách nhiệm giải trình** về một *security control* cụ thể: mục tiêu của control là gì, control được thiết kế và vận hành ra sao, có bằng chứng chứng minh tính hiệu quả hay không, và các sai lệch được xử lý thế nào. Trong doanh nghiệp, control owner thường là người quản lý một dịch vụ, quy trình hoặc năng lực kỹ thuật có đủ khả năng điều phối người thực hiện và nguồn lực để duy trì control.

Một **security control** có thể là biện pháp kỹ thuật, quy trình hoặc tổ chức nhằm phòng ngừa, phát hiện hay giảm tác động của rủi ro. Ví dụ:

- Chỉ người dùng được cấp quyền mới có thể truy cập dữ liệu khách hàng.
- Mọi tài khoản quản trị được bảo vệ bằng xác thực đa yếu tố theo chính sách.
- Những thay đổi sản xuất quan trọng phải được xem xét và ghi nhận.
- Các sự kiện bảo mật trọng yếu được ghi log và có cơ chế giám sát.
- Bí mật ứng dụng được lưu trong hệ thống quản lý bí mật thay vì nằm trong mã nguồn.

Ở module **SECURITY_SECURITY_ASSURANCE**, vai trò control owner có ý nghĩa đặc biệt: hoạt động assurance cần người chịu trách nhiệm **chuyển yêu cầu bảo mật thành control có thể đánh giá, duy trì bằng chứng đáng tin cậy, xử lý phát hiện và kiểm tra lại hiệu quả** trong suốt quá trình phát triển và vận hành.

Control owner **không nhất thiết tự viết toàn bộ mã nguồn, tự vận hành mọi hệ thống hay trực tiếp chạy mọi kiểm thử**. Họ phải biết ai thực hiện những việc đó, tiêu chí đạt là gì, bằng chứng được tạo và lưu ở đâu, và phải can thiệp khi control không hoạt động theo kỳ vọng.

> Một control có thể được triển khai nhưng chưa chứng minh được hiệu quả. Trách nhiệm cốt lõi của control owner là bảo đảm có thể đưa ra kết luận về thiết kế và hoạt động của control dựa trên bằng chứng phù hợp, đồng thời quản lý các khoảng trống được phát hiện.

## 2. Vì sao cần chỉ định control owner?

Nếu control không có chủ sở hữu rõ ràng, tổ chức dễ gặp những tình huống:

1. Nhóm triển khai một cơ chế phân quyền nhưng không ai chịu trách nhiệm cập nhật khi mô hình vai trò thay đổi.
2. Công cụ quét báo một lỗ hổng nghiêm trọng nhưng ticket bị chuyển qua lại vì không xác định người xử lý.
3. Một báo cáo audit yêu cầu bằng chứng kiểm soát; mỗi nhóm cung cấp một phần nhưng không ai xác nhận phạm vi và phiên bản.
4. Cấu hình bảo mật đã đúng ở môi trường thử nghiệm nhưng khác ở môi trường chạy thực tế.
5. Phát hiện được đánh dấu "Fixed" sau khi sửa mã, nhưng chưa có kiểm thử xác nhận lỗi không còn xảy ra.

Chỉ định một control owner có thẩm quyền và trách nhiệm được mô tả rõ giúp:

| Lợi ích | Cơ chế | Bằng chứng có thể thấy |
| --- | --- | --- |
| **Trách nhiệm rõ ràng** | Có một đầu mối chịu trách nhiệm về kết quả của control | Control register ghi chủ sở hữu và phạm vi |
| **Độ bao phủ tốt hơn** | Đối chiếu hệ thống, luồng dữ liệu và yêu cầu với control | Ma trận áp dụng control cho các dịch vụ |
| **Giảm cấu hình sai lệch** | Theo dõi thay đổi, kiểm tra định kỳ và xử lý sai lệch | Báo cáo cấu hình, kết quả kiểm thử, lịch sử sửa |
| **Assurance có thể truy vết** | Liên kết yêu cầu, control, bằng chứng, phát hiện và kiểm thử lại | Evidence register và hồ sơ review |
| **Khắc phục nhất quán** | Điều phối action owner, ưu tiên và thời hạn | Ticket có chủ sở hữu, hạn, bằng chứng xác minh |
| **Kiểm toán thuận lợi hơn** | Chuẩn hóa cách thu thập và giải thích bằng chứng | Kết quả audit có phạm vi, thời điểm và người xác nhận |

Điều này **không có nghĩa giao trách nhiệm cho một cá nhân là đủ**. Người đó còn cần quyền tiếp cận thông tin, nguồn lực, chỉ số giám sát, đường chuyển cấp và sự hỗ trợ của các nhóm kỹ thuật.

## 3. Phân biệt control owner với các vai trò liên quan

Nhiều vấn đề trong quản trị bảo mật bắt nguồn từ việc nhầm lẫn các vai trò sở hữu khác nhau.

| Vai trò | Chịu trách nhiệm chính về | Câu hỏi đặc trưng |
| --- | --- | --- |
| **Control owner** | Thiết kế, duy trì, theo dõi và chứng minh hiệu quả của control trong phạm vi được giao | "Control này có đang đáp ứng mục tiêu với bằng chứng hợp lệ không?" |
| **Risk owner** | Quyết định và chịu trách nhiệm về phương án xử lý **rủi ro kinh doanh còn lại**, trong thẩm quyền | "Tổ chức sẽ xử lý, giảm thiểu, tránh hay chấp nhận rủi ro này như thế nào?" |
| **System / service owner** | Vòng đời, chất lượng, độ ổn định và trách nhiệm của một hệ thống/dịch vụ | "Ai chịu trách nhiệm cho dịch vụ này và những thay đổi của nó?" |
| **Data owner** | Phân loại, mục đích sử dụng, quyền và quy tắc bảo vệ tập dữ liệu | "Ai được dùng dữ liệu này, với mục đích gì?" |
| **Control operator / implementer** | Thực hiện các công việc vận hành hoặc triển khai kỹ thuật hằng ngày | "Ai cấu hình, kiểm tra hoặc sửa control?" |
| **CISO / security team** | Định hướng bảo mật, thiết lập tiêu chuẩn, tư vấn rủi ro và giám sát chuyên môn | "Các yêu cầu và control có phù hợp mục tiêu bảo mật chung không?" |
| **Assurance / test / audit** | Đánh giá bằng chứng và đưa ra kết luận trong phạm vi kiểm tra | "Bằng chứng có đủ để hỗ trợ kết luận đó không?" |

**Ví dụ:** dịch vụ đặt hàng có kiểm soát chỉ chủ đơn hàng được xem đơn của mình. Trưởng nhóm kỹ thuật có thể là **control owner** của kiểm tra phân quyền ở API; lập trình viên thực hiện mã là **control implementer**; chủ sản phẩm là **risk owner** với nguy cơ rò rỉ dữ liệu kinh doanh; kiểm thử viên bảo mật xác minh chính sách phân quyền có thực thi hay không.

Một người có thể kiêm nhiều vai trò trong tổ chức nhỏ. Tuy nhiên, khi có xung đột lợi ích, nhất là với control có rủi ro lớn, nên sử dụng rà soát chéo hoặc đánh giá độc lập phù hợp.

### 3.1. Control owner có quyền chấp nhận rủi ro không?

**Không mặc định.** Quyền chấp nhận rủi ro còn lại phụ thuộc điều lệ quản trị và phân quyền của tổ chức. Control owner có thể xác nhận control chưa đạt, đề xuất biện pháp bù trừ hoặc yêu cầu gia hạn khắc phục, nhưng không thể tự tuyên bố rủi ro đã được chấp nhận nếu không có thẩm quyền.

Ví dụ, control owner phát hiện 12% API chưa có test phân quyền. Họ phải nêu rõ khoảng trống và kế hoạch xử lý. Nếu đề nghị triển khai trong khi còn khoảng trống, **risk owner** hoặc cấp có quyền phê duyệt phải xem xét mức rủi ro, tác động, biện pháp bù trừ và các nghĩa vụ bắt buộc trước khi ra quyết định.

## 4. Những trách nhiệm xuyên suốt vòng đời control

### 4.1. Hiểu mục tiêu, rủi ro và phạm vi áp dụng

Control owner cần biết control tồn tại để giảm rủi ro gì và áp dụng cho những gì. Các câu hỏi đầu tiên nên là:

- **Mục tiêu bảo mật:** control cần bảo vệ tính bí mật, toàn vẹn, sẵn sàng, khả năng truy vết hay một mục tiêu khác?
- **Tài sản và mối đe dọa:** dữ liệu, tài khoản, dịch vụ nào được bảo vệ; hành vi lạm dụng nào cần ngăn chặn?
- **Phạm vi:** các ứng dụng, API, môi trường, tenant, tài khoản, luồng dữ liệu nào thuộc trách nhiệm?
- **Yêu cầu:** quy định kỹ thuật, chính sách nội bộ, hợp đồng hoặc tiêu chí áp dụng nào phải được đáp ứng?
- **Giới hạn:** có phần nào chưa được bao phủ hoặc đang dựa vào một control khác không?

Một yêu cầu "Bảo vệ API" quá chung. Yêu cầu "Mọi truy cập đọc đơn hàng của khách hàng phải xác minh quyền trên chính đơn hàng đó; không có quyền thì không trả dữ liệu" cho phép thiết kế kiểm thử rõ ràng.

### 4.2. Thiết kế control và tiêu chí thành công

Control owner không nhất thiết tự thiết kế mọi chi tiết, nhưng phải bảo đảm thiết kế có thể giải thích và kiểm chứng:

1. Xác định **điều kiện kích hoạt**, hành vi mong đợi và hành vi cần từ chối.
2. Định nghĩa điểm thực thi control: ở API, tầng nghiệp vụ, cơ sở dữ liệu, cổng truy cập hay hạ tầng.
3. Xác định phụ thuộc: định danh tin cậy, cơ chế cấp quyền, log, chứng thư, dịch vụ kiểm soát tập trung.
4. Mô tả các **kịch bản kiểm thử dương và âm**, gồm trường hợp biên và thất bại của thành phần phụ thuộc.
5. Ghi nhận cách giám sát để phát hiện control bị vô hiệu hóa hoặc không còn hiệu quả.

Điều quan trọng là phân biệt **hiệu quả thiết kế** (*design effectiveness*: nếu thực thi đúng, thiết kế có giải quyết rủi ro hay không) với **hiệu quả vận hành** (*operating effectiveness*: trên môi trường thực tế, control có vận hành ổn định như thiết kế hay không).

### 4.3. Tổ chức triển khai và bàn giao

Khi triển khai, control owner phối hợp với người thực hiện để xác định:

- Ai phát triển hoặc cấu hình control và kiểm thử cơ bản.
- Tài liệu kiến trúc, policy, hướng dẫn vận hành được lưu ở đâu.
- Những hệ thống và phiên bản nào đã áp dụng.
- Ai tiếp nhận cảnh báo, yêu cầu thay đổi và phát hiện.
- Điều kiện chuyển giao khi đội vận hành hoặc nhà cung cấp thay đổi.

Control dùng chung (ví dụ nền tảng xác thực tập trung) thường có **owner của nền tảng** chịu trách nhiệm cho phần dịch vụ dùng chung; **owner của ứng dụng** vẫn chịu trách nhiệm dùng đúng giao diện và kiểm tra quyền đặc thù trong ứng dụng. Phân định ranh giới này cần được ghi trong control register và mô hình trách nhiệm.

### 4.4. Thu thập bằng chứng assurance

Đây là trách nhiệm quan trọng để chuyển việc "đã cấu hình control" thành **khẳng định có thể kiểm chứng**. Bằng chứng có thể bao gồm:

| Nhóm bằng chứng | Ví dụ | Chứng minh điều gì? | Điểm giới hạn |
| --- | --- | --- | --- |
| Chính sách và thiết kế | Tiêu chí phân quyền, sơ đồ kiến trúc, tài liệu threat model | Mục tiêu và cách control được kỳ vọng hoạt động | Chưa chứng minh hệ thống thực thi đúng |
| Triển khai | Pull request, cấu hình, infrastructure-as-code, build artifact | Có biện pháp được đưa vào phiên bản cụ thể | Chưa chắc môi trường chạy đã áp dụng |
| Kiểm thử | Integration test, kiểm thử từ chối truy cập, kiểm thử xâm nhập | Một số tình huống thực tế có kết quả đúng/sai | Không bao phủ mọi kịch bản nếu phạm vi hẹp |
| Vận hành | Telemetry, giám sát cấu hình, nhật ký truy cập đã giới hạn dữ liệu | Control đang hiện diện và vận hành trong khoảng thời gian quan sát | Log có thể thiếu, sai lệch hoặc không phản ánh lỗi logic |
| Độc lập | Kết quả security review, audit hoặc đánh giá bên ngoài | Có sự rà soát từ góc nhìn khác với bên triển khai | Chỉ có hiệu lực trong phạm vi, thời điểm được đánh giá |
| Khắc phục | Ticket, commit sửa, bản phát hành, kết quả retest | Phát hiện đã được xử lý và kiểm tra lại | Chưa chắc các hệ thống tương tự đều đã sửa |

Mỗi bằng chứng nên có **nguồn, người hoặc hệ thống tạo, thời điểm, đối tượng được đánh giá, phiên bản/môi trường, kết quả, liên kết và phạm vi hiệu lực**. Chỉ đưa dữ liệu cần thiết vào hồ sơ, che thông tin nhạy cảm, giới hạn người xem và bảo vệ tính toàn vẹn của kết quả.

### 4.5. Theo dõi, ứng phó khi sai lệch và khắc phục

Khi xuất hiện phát hiện từ kiểm thử, audit, sự cố hoặc giám sát, control owner:

1. **Xác nhận phát hiện:** xác định hệ thống, phiên bản, kịch bản và mức độ đáng tin của bằng chứng.
2. **Đánh giá phạm vi ảnh hưởng:** control có bị lỗi trên một endpoint hay trên nhiều hệ thống; có cần hành động khẩn cấp?
3. **Phối hợp phân loại rủi ro:** trao đổi cùng risk owner, CISO và bộ phận liên quan.
4. **Chỉ định action owner:** ai sửa, ai cập nhật cấu hình, ai bổ sung kiểm thử và thời hạn nào.
5. **Theo dõi giảm thiểu tạm thời:** nếu cần, hạn chế tính năng, tăng giám sát hoặc áp dụng control bù trừ theo quy trình.
6. **Xác minh bản sửa:** kiểm thử lại tại phiên bản và môi trường phù hợp; đánh giá có tái phát ở đường truy cập khác không.
7. **Cập nhật trạng thái:** ghi kết quả, rủi ro còn lại và quyết định phê duyệt hoặc chuyển cấp.

Control owner có trách nhiệm **báo cáo trung thực khoảng trống** ngay cả khi bản sửa đang bị trì hoãn. Không nên tự đóng phát hiện chỉ vì ticket chuyển sang trạng thái "Done".

### 4.6. Giám sát theo thay đổi và đánh giá định kỳ

Bằng chứng từng hợp lệ có thể mất giá trị khi:

- Thêm endpoint hoặc thay đổi role/quyền truy cập.
- Chuyển hệ thống sang cloud, vùng triển khai hoặc nhà cung cấp mới.
- Nâng cấp framework, thư viện, gateway hoặc cơ chế xác thực.
- Sửa chính sách lưu trữ, log, mã hóa hoặc thời hạn bảo vệ dữ liệu.
- Mở rộng môi trường sản xuất, dữ liệu, tenant hoặc người dùng.
- Xảy ra sự cố cho thấy giả định kiểm soát trước đây không còn đúng.

Control owner cần thiết lập **trigger tái đánh giá theo thay đổi** và **lịch kiểm tra định kỳ theo mức rủi ro**, không giả định chứng nhận hoặc kết quả kiểm thử một lần có giá trị vĩnh viễn.

## 5. Control register: hồ sơ quản lý tối thiểu

Một **control register** (danh mục control) giúp biết từng control nhằm mục tiêu gì, ai chịu trách nhiệm, có bằng chứng nào và trạng thái gần nhất. Mẫu trường:

| Trường | Mục đích |
| --- | --- |
| Control ID, tên | Định danh duy nhất và mục đích ngắn gọn |
| Risk/requirement ID | Liên kết control với rủi ro và yêu cầu |
| Control owner | Người chịu trách nhiệm giải trình và phạm vi quyền |
| Operator/implementer | Nhóm thực hiện hoặc vận hành |
| Scope | Dịch vụ, API, môi trường, quy trình được bao phủ |
| Design/operating criteria | Điều kiện để coi control được thiết kế và hoạt động đạt |
| Evidence source và reviewer | Nơi lấy bằng chứng và người đánh giá |
| Frequency/change trigger | Nhịp kiểm tra và thay đổi nào buộc đánh giá lại |
| Findings/exceptions | Phát hiện chưa đóng, biện pháp bù trừ, ngoại lệ có thời hạn |
| Last verified/next review | Mốc kiểm tra và thời điểm cần xem lại |
| Escalation | Cấp nhận vấn đề khi vượt ngưỡng rủi ro hoặc quyền hạn |

Ví dụ **hồ sơ minh họa**, không phải record từ một hệ thống đang vận hành:

~~~yaml
control_id: "AUTHZ-ORDER-01"
name: "Phan quyen doc don hang cap doi tuong"
objective: "Khong cho phep doc don hang cua nguoi khac"
risk_id: "RISK-DATA-ACCESS-DEMO"
requirement_id: "REQ-AUTHZ-02"
control_owner: "Truong nhom Orders API"
risk_owner: "Chu san pham Orders"
implementers:
  - "Nhom phat trien Orders"
  - "Nhom van hanh API"
scope:
  service: "orders-api"
  environment: "production"
  endpoints:
    - "GET /api/orders/{orderId}"
success_criteria:
  - "Nguoi khong co quyen khong nhan du lieu"
  - "Nguoi duoc cap quyen truy xuat dung du lieu"
evidence_plan:
  - "Integration test voi user A va user B"
  - "Review rule phan quyen va PR"
  - "Danh gia cau hinh va trien khai"
evaluation_triggers:
  - "Thay doi role hoac policy"
  - "Them endpoint truy xuat don hang"
  - "Cap nhat logic truy xuat du lieu"
last_verified: null
next_review: "Can dat theo muc rui ro"
finding_status: "CHUA_DANH_GIA"
~~~

Các giá trị như tên vai trò, mã ID và trạng thái trong mẫu chỉ nhằm giải thích cấu trúc. **Không dùng mẫu này để tuyên bố một control đã được kiểm chứng**. Trong thực tế, chỉ đánh dấu "Verified" khi có liên kết đến kết quả đánh giá hợp lệ.

## 6. Ví dụ kỹ thuật: control owner của phân quyền API Java/Spring Boot

Giả sử hệ thống bán hàng có API:

~~~http
GET /api/orders/841
Authorization: Bearer <access-token>
~~~

**Rủi ro:** người dùng A thay đổi ID và đọc đơn hàng 841 thuộc người dùng B. Việc xác thực token hợp lệ chưa đủ để cấp quyền trên từng đơn hàng (*broken object-level authorization*).

### 6.1. Vai trò của control owner trong kịch bản

Control owner (ví dụ tech lead của Orders API) phối hợp để thiết lập:

- **Security claim:** người dùng chỉ đọc được đơn hàng họ có quyền xem; các vai trò đặc biệt tuân theo chính sách rõ ràng.
- **Control:** dịch vụ kiểm tra quyền ở tầng nghiệp vụ/dữ liệu, dựa trên danh tính đã xác minh và quan hệ với đối tượng.
- **Đầu vào tin cậy:** customer ID lấy từ context xác thực đáng tin; không lấy trực tiếp từ query parameter do client gửi.
- **Tiêu chí:** người dùng đúng quyền lấy dữ liệu; người không có quyền không nhận nội dung; yêu cầu chưa xác thực bị từ chối.
- **Bằng chứng:** review thiết kế, commit, test run các tình huống được phép/bị từ chối, đánh giá sau triển khai.
- **Khắc phục:** người triển khai sửa lỗi, nhóm kiểm thử xác minh; control owner cập nhật kết luận và báo risk owner nếu còn rủi ro.

Trích đoạn Java **minh họa cấu trúc** ở tầng service:

~~~java
@Service
public class OrderReadService {
    private final OrderRepository orders;
    private final CurrentCustomer currentCustomer;

    public OrderReadService(OrderRepository orders,
                            CurrentCustomer currentCustomer) {
        this.orders = orders;
        this.currentCustomer = currentCustomer;
    }

    @Transactional(readOnly = true)
    public OrderView getOrder(long orderId) {
        // Phải ánh xạ từ phiên xác thực đã xác minh,
        // không lấy customerId do request tự khai báo.
        long customerId = currentCustomer.customerId();

        return orders.findByIdAndCustomerId(orderId, customerId)
                .map(OrderView::from)
                .orElseThrow(() ->
                    new ResponseStatusException(HttpStatus.NOT_FOUND));
    }
}
~~~

Đây là trích đoạn mang tính mô hình: các kiểu phụ trợ như **OrderRepository**, **OrderView** và **CurrentCustomer** phải được định nghĩa trong ứng dụng. **CurrentCustomer** cần được triển khai an toàn dựa trên context xác thực của request. Chính sách truy cập dành cho quản trị viên hoặc người dùng được ủy quyền phải có quy tắc riêng, được kiểm thử. Trả về HTTP 404 trong ví dụ có thể giúp không tiết lộ sự tồn tại của đối tượng; mã phản hồi 403 hay 404 cần tuân theo chính sách của sản phẩm.

Ví dụ test matrix để control owner yêu cầu:

| Kịch bản | Kết quả mong đợi |
| --- | --- |
| A đọc đơn hàng thuộc A | Trả về dữ liệu đúng theo quyền |
| A đọc đơn hàng thuộc B | Từ chối, không trả dữ liệu đơn |
| Yêu cầu thiếu xác thực | Từ chối theo cấu hình bảo mật |
| ID không tồn tại | Không trả dữ liệu |
| A có quyền được ủy quyền hợp lệ theo chính sách | Chỉ trả dữ liệu trong phạm vi được ủy quyền |
| Vai trò bị thu hồi quyền | Quyền mới có hiệu lực theo yêu cầu hệ thống, không tiếp tục cấp quyền sai |
| Endpoint mới truy xuất đơn hàng | Tuân thủ cùng chính sách và có test kiểm chứng |

**Chủ sở hữu control phải kiểm tra độ bao phủ:** một test tích hợp đi qua một endpoint không chứng minh tất cả endpoint, batch job, luồng quản trị hoặc truy cập nội bộ đều an toàn.

### 6.2. Từ test đến bằng chứng có thể kiểm tra lại

Giả sử pipeline CI chạy các test phân quyền. Control owner cần bảo đảm mỗi kết quả lưu được ít nhất:

1. Commit/build và phiên bản ứng dụng.
2. Tên kịch bản, tài khoản/role thử nghiệm, dữ liệu dùng để test đã được ẩn thông tin thật.
3. Môi trường chạy và cấu hình liên quan.
4. Kết quả PASS/FAIL và báo cáo có thể truy cập lại.
5. Người rà soát/phê duyệt, liên kết tới yêu cầu và control ID.
6. Ngày chạy, lý do phải kiểm thử lại khi policy hoặc code thay đổi.

Một báo cáo "100% test passed" chỉ có ý nghĩa trong **phạm vi test đã thực sự chạy**. Nếu không có kịch bản truy cập chéo tài khoản thì con số đó không chứng minh control phân quyền đang đạt.

### 6.3. Khi test bị FAIL

Ví dụ tình huống giả định: test "A đọc đơn B" trả HTTP 200 và có dữ liệu. Control owner cần ghi nhận phát hiện, xác định phạm vi ảnh hưởng, phối hợp mức độ ưu tiên theo rủi ro, chỉ định người sửa và yêu cầu test lại. Nếu cần phát hành gấp, control owner **không tự chấp nhận nguy cơ rò rỉ dữ liệu**; họ đưa phương án giảm thiểu và bằng chứng cho risk owner/cấp phê duyệt có thẩm quyền.

Chỉ đóng phát hiện khi đã có bằng chứng kết quả trên bản sửa, trong môi trường thích hợp. Sau đó cần cập nhật test hồi quy để tránh lỗi tái diễn.

## 7. Ma trận RACI cho một control

RACI giải thích bốn loại trách nhiệm:

- **R (Responsible):** trực tiếp thực hiện công việc.
- **A (Accountable):** chịu trách nhiệm cuối cùng về việc hoàn thành hoạt động/đầu ra.
- **C (Consulted):** cần được tham vấn.
- **I (Informed):** được thông báo.

Ma trận minh họa cho control phân quyền đơn hàng:

| Hoạt động | Control owner | Developer/Operator | Security reviewer | Risk owner | Audit độc lập |
| --- | --- | --- | --- | --- | --- |
| Định nghĩa control và tiêu chí đạt | A | R | C | C | I |
| Cài đặt kiểm tra phân quyền | A | R | C | I | I |
| Vận hành, giám sát control | A | R | C | I | I |
| Chạy và lưu test tích hợp | A | R | C | I | I |
| Đánh giá độc lập control trong kỳ audit | C | C | C | I | A/R |
| Điều phối khắc phục phát hiện kỹ thuật | A | R | C | C | I |
| Quyết định chấp nhận rủi ro trong thẩm quyền risk owner | C | C | C | A/R | I |

Đây là **mẫu tham khảo**, phải sửa theo cơ cấu tổ chức và quyền được giao. Một hoạt động nên có **một chủ thể chịu trách nhiệm cuối cùng (A)** rõ ràng; có thể có nhiều người thực hiện. Nếu công việc đánh giá được thực hiện bởi bộ phận độc lập, control owner phối hợp cung cấp bằng chứng nhưng **không quyết định thay kết luận audit**.

### 7.1. Nếu một control phủ nhiều dịch vụ?

Ví dụ kiểm soát **MFA cho tài khoản quản trị** có thể liên quan nền tảng danh tính, ứng dụng quản trị và hệ thống giám sát. Cần mô tả rõ:

- Ai là **owner** của chính sách và dịch vụ MFA tập trung.
- Ai triển khai tích hợp MFA cho từng ứng dụng.
- Ai kiểm tra tài khoản hoặc luồng đặc biệt bị bỏ sót.
- Ai xử lý phát hiện tại phần dùng chung và phần tích hợp.
- Ai tổng hợp bằng chứng toàn phạm vi và báo cáo sai lệch.

Nếu phạm vi quá rộng, có thể chia thành các control con, mỗi control có một chủ sở hữu được định danh, rồi chỉ định một đầu mối phối hợp cho control cấp tổ chức. Không dùng khái niệm "cùng sở hữu" để che giấu khoảng trống trách nhiệm.

## 8. Những quyết định mà control owner cần được hỗ trợ

Một control owner muốn làm đúng trách nhiệm thường cần đường hỗ trợ ở các thời điểm:

| Tình huống | Điều control owner thực hiện | Ai có thể cần tham gia |
| --- | --- | --- |
| Yêu cầu bảo mật mơ hồ | Đề nghị làm rõ mục tiêu, tiêu chí kiểm chứng | Security, risk owner, product owner |
| Không có đủ nhân lực để vá lỗi | Trình mức rủi ro, ảnh hưởng và các lựa chọn | Quản lý kỹ thuật, chủ sản phẩm, hội đồng bảo mật |
| Không thể lấy bằng chứng từ nhà cung cấp | Ghi hạn chế assurance, đề xuất kiểm tra bù trừ | Nhà cung cấp, procurement, risk/compliance |
| Control chung đổi cấu hình | Đánh giá phạm vi ảnh hưởng và kích hoạt test hồi quy | Platform owner, application owner |
| Lỗi quan trọng phát hiện khi đang vận hành | Kích hoạt ứng cứu và phối hợp giảm thiểu theo quy trình | SOC/incident commander, vận hành, risk owner |
| Cần ngoại lệ so với baseline | Chuẩn bị hồ sơ rủi ro, phương án và thời hạn | Risk owner và người phê duyệt đủ thẩm quyền |
| Audit có kết luận bất lợi | Xác thực phát hiện, lên kế hoạch sửa và cung cấp bằng chứng xác minh | Auditor, security, operator |

Control owner chịu trách nhiệm giữ đầu mối hành động, nhưng **không thay thế hệ thống phân quyền quản trị rủi ro**. Đặc biệt, việc chấp nhận rủi ro nghiêm trọng cần đúng người có thẩm quyền và không thể dùng để bỏ qua nghĩa vụ bắt buộc.

## 9. Chỉ số đánh giá hiệu quả trách nhiệm control owner

Để theo dõi kết quả, nên dùng chỉ số có ngữ cảnh và liên hệ với các security claims.

| Chỉ số tham khảo | Cách đo | Cách hiểu đúng |
| --- | --- | --- |
| Tỷ lệ control có owner và scope rõ | Số control có chủ sở hữu hợp lệ / tổng control trong phạm vi | Chỉ kiểm tra phân công, chưa chứng minh hiệu quả |
| Tỷ lệ control trọng yếu có bằng chứng còn hiệu lực | Control đạt tiêu chí bằng chứng / tổng control trọng yếu | Phải đánh giá chất lượng, phạm vi và phiên bản bằng chứng |
| Tỷ lệ kiểm tra theo lịch hoàn tất và đã review | Số lần kiểm tra hợp lệ / số lần đến hạn | Tránh "đánh dấu đạt" khi thiếu xác minh |
| Thời gian khắc phục theo mức rủi ro | Từ xác nhận phát hiện đến lúc bản sửa được kiểm thử lại | Không dừng đồng hồ khi mới tạo PR hoặc đóng ticket |
| Số phát hiện trọng yếu quá hạn | Các phát hiện chưa xử lý/chưa được quyết định đúng thẩm quyền | Xem tác động và biện pháp bù trừ kèm theo |
| Tỷ lệ lỗi tái phát | Phát hiện lặp lại sau khi đã xác minh sửa / số phát hiện đã sửa được theo dõi | Có thể phản ánh test hồi quy hoặc vấn đề nguyên nhân gốc |
| Tỷ lệ thay đổi quan trọng có đánh giá tác động | Thay đổi liên quan control đã review / tổng thay đổi liên quan | Hạn chế đếm review hình thức |

Ví dụ: có 15 control trọng yếu, 12 control có bằng chứng đúng phiên bản và chưa quá hạn. Tỷ lệ bao phủ bằng chứng là **12/15 = 80%**, **không có nghĩa hệ thống an toàn 80%**. Ba control thiếu bằng chứng có thể là các control quan trọng nhất, nên phải xem độ trọng yếu và rủi ro còn lại.

Chỉ số tốt giúp control owner nhận ra khoảng trống và ưu tiên hành động, không nên chỉ dùng để so sánh hoặc thưởng phạt số lượng ticket.

## 10. Các sai lầm thường gặp

### 10.1. "Có người đứng tên" nhưng không có quyền hoặc thông tin

Một cá nhân được ghi làm owner nhưng không được xem log, không điều phối được team và không biết thay đổi nào ảnh hưởng control. Cách khắc phục là trao quyền tiếp cận cần thiết, chỉ định operator, đường chuyển cấp và cơ chế cập nhật khi có thay đổi.

### 10.2. Nhầm "control tồn tại" với "control hiệu quả"

Chỉ thấy một policy, checkbox hoặc cấu hình bật không chứng minh nó đang hoạt động đúng. Phải kết hợp rà soát thiết kế, kiểm thử hành vi, giám sát vận hành và bằng chứng đúng phiên bản.

### 10.3. Thu gom báo cáo mà không nêu claim

Một thư mục có hàng trăm báo cáo scan vẫn có thể thiếu bằng chứng cho câu hỏi "người dùng có đọc được dữ liệu người khác không?". Mỗi bằng chứng nên gắn với yêu cầu và kịch bản rủi ro mà nó hỗ trợ.

### 10.4. Giao nhiều owner nhưng không xác định đầu mối

Khi một control đi qua hạ tầng, dịch vụ và ứng dụng, nhiều nhóm có thể cùng tham gia nhưng mỗi phần trách nhiệm phải được phân ranh. Ghi rõ owner cấp control, owner thành phần và cơ chế tổng hợp.

### 10.5. Tự xác nhận hiệu quả ở mọi trường hợp

Người trực tiếp cài đặt control có thể bỏ sót giả định trong thiết kế của mình. Với control rủi ro cao, nên dùng review độc lập hoặc kiểm thử bởi người khác có năng lực phù hợp.

### 10.6. Đóng phát hiện trước khi kiểm thử lại

Bản sửa chưa được triển khai hoặc chưa được test trên môi trường phù hợp chỉ là **tiến độ thực hiện**, chưa phải bằng chứng khắc phục thành công.

### 10.7. Không cập nhật bằng chứng sau thay đổi

Kết quả đánh giá phiên bản cũ mất giá trị nếu cấu hình, role hoặc dữ liệu thay đổi đáng kể. Cần đánh giá tác động của thay đổi và tái kiểm chứng theo trigger đã định nghĩa.

## 11. Checklist áp dụng cho một control owner mới

Có thể dùng danh sách sau để rà soát một control trước khi nhận trách nhiệm:

- [ ] Tôi biết **rủi ro**, **security objective**, **yêu cầu** và **phạm vi** control cần giải quyết.
- [ ] Control có ID, mô tả, owner và các operator/implementer cụ thể.
- [ ] Tôi hiểu điều kiện thiết kế đúng và **tiêu chí vận hành đạt**.
- [ ] Tôi biết control phụ thuộc vào hệ thống, nhóm và nhà cung cấp nào.
- [ ] Có kế hoạch bằng chứng, nguồn dữ liệu, cách lưu giữ và người đánh giá.
- [ ] Có test cho trường hợp được phép, bị từ chối và các trường hợp quan trọng theo rủi ro.
- [ ] Có lịch đánh giá và các thay đổi buộc đánh giá lại.
- [ ] Có quy trình tiếp nhận, ưu tiên, sửa và kiểm thử lại phát hiện.
- [ ] Có đường chuyển cấp khi lỗi vượt khả năng sửa hoặc ngưỡng rủi ro.
- [ ] Tôi biết rủi ro nào cần chuyển cho risk owner/người có thẩm quyền phê duyệt.
- [ ] Có cách bàn giao khi owner hoặc team vận hành thay đổi.
- [ ] Tôi có thể trình bày bằng chứng và **những giới hạn còn tồn tại** của kết luận assurance.

Checklist là điểm khởi đầu, không thay thế đánh giá bảo mật và quy trình quản trị cụ thể.

## 12. Tự kiểm tra kiến thức

1. Control owner khác risk owner ở trách nhiệm ra quyết định và quản lý rủi ro còn lại như thế nào?
2. Khi test phân quyền không có kịch bản truy cập chéo người dùng, vì sao kết quả 100% test PASS chưa chứng minh control hiệu quả?
3. Nếu control triển khai trên 15 hệ thống nhưng chỉ có bằng chứng từ 10 hệ thống, control owner cần làm gì trước khi báo cáo đạt?
4. Trong tình huống nhà cung cấp danh tính thay đổi cấu hình MFA, ai nên đánh giá tác động và kiểm tra các ứng dụng tích hợp?
5. Một bản vá đã được merge nhưng chưa triển khai hoặc kiểm thử lại. Control owner có nên đóng phát hiện không? Cần bằng chứng gì?
6. Vì sao nên tách vai trò owner của một nền tảng dùng chung với owner của việc tích hợp nền tảng đó ở ứng dụng?

## 13. Tổng kết

**Control owner** là người chịu trách nhiệm giải trình về **một security control có phạm vi xác định**, từ hiểu mục tiêu, tổ chức triển khai, duy trì vận hành, quản lý bằng chứng đến khắc phục phát hiện. Trong chương trình **security assurance liên tục**, control owner giúp kết nối **rủi ro → yêu cầu → control → kiểm thử/audit → bằng chứng → kết luận → sửa và xác minh lại**. Vai trò này hữu ích nhất khi được giao quyền rõ ràng, phối hợp đúng với risk owner và người đánh giá độc lập, và luôn trình bày trung thực cả hiệu quả lẫn giới hạn của control.
