# Liên kết mô hình với yêu cầu

Trong quá trình xây dựng một ngôn ngữ miền đặc thù (Domain-Specific Language — DSL), mô hình miền mô tả những khái niệm, quan hệ, quy tắc và hành vi tồn tại trong lĩnh vực nghiệp vụ. Yêu cầu mô tả điều các bên liên quan cần hệ thống hoặc DSL hỗ trợ. Hai phần này phải được liên kết rõ ràng để bảo đảm mô hình phản ánh đúng nhu cầu và mỗi yêu cầu quan trọng đều có cách hiện thực, kiểm chứng và theo dõi.

**Liên kết mô hình với yêu cầu** là hoạt động thiết lập và duy trì quan hệ có thể truy vết giữa yêu cầu, bằng chứng nghiệp vụ, phần tử mô hình miền, cấu trúc DSL, thành phần thực thi và trường hợp kiểm thử. Mối liên kết này cho biết một phần tử mô hình tồn tại vì lý do gì, nó đáp ứng yêu cầu nào, và khi yêu cầu thay đổi thì những phần nào của mô hình hoặc DSL cần được xem xét.

Nếu yêu cầu và mô hình được quản lý riêng rẽ, nhóm dễ tạo ra mô hình đẹp về mặt kỹ thuật nhưng không giải quyết đúng vấn đề; ngược lại, một yêu cầu có thể bị bỏ sót khi chuyển thành khái niệm, quy tắc hoặc cú pháp DSL. Truy vết hai chiều giúp nhóm kiểm soát sự phù hợp từ lúc khám phá miền đến khi thiết kế, triển khai, kiểm thử và bảo trì DSL.

## 1. Yêu cầu và mô hình miền có vai trò gì?

### Yêu cầu mô tả nhu cầu và kết quả cần đạt

Yêu cầu (*requirement*) phát biểu một khả năng, quy tắc, chất lượng hoặc ràng buộc mà giải pháp cần đáp ứng. Nguồn yêu cầu có thể là mục tiêu kinh doanh, chính sách, quy định, kịch bản sử dụng, phản hồi của người dùng, hợp đồng tích hợp hoặc giới hạn của môi trường vận hành.

Trong dự án DSL, yêu cầu có thể nói về nhiều khía cạnh:

- Người dùng cần mô tả một quy trình nghiệp vụ bằng ngôn ngữ dễ đọc.
- Một đơn hàng chỉ được xác nhận khi thanh toán hợp lệ.
- Một lô hàng không được vượt quá số lượng hàng có thể xuất.
- DSL cần phát hiện lỗi tham chiếu đến khái niệm chưa được khai báo.
- Chỉ vai trò được cấp quyền mới có thể phê duyệt một quy tắc.
- Hệ thống phải ghi nhận lịch sử thay đổi và người thực hiện.
- Chương trình DSL phải có thể tích hợp với hệ thống quản lý kho hiện tại.

Yêu cầu nên mô tả điều cần đạt và điều kiện chấp nhận, thay vì vội chỉ định một giải pháp nội bộ như tên lớp, bảng cơ sở dữ liệu hoặc hàm cụ thể.

### Mô hình miền mô tả cấu trúc và quy tắc của lĩnh vực

Mô hình miền (*domain model*) biểu diễn có cấu trúc những khái niệm có ý nghĩa trong nghiệp vụ và quan hệ giữa chúng. Tùy cách tiếp cận, mô hình có thể bao gồm:

- **Khái niệm và thuật ngữ:** đơn hàng, mặt hàng, khách hàng, thanh toán, lô hàng.
- **Thực thể (entity):** đối tượng có danh tính và vòng đời, chẳng hạn đơn hàng hoặc phiếu giao hàng.
- **Đối tượng giá trị (value object):** giá trị được xác định bởi nội dung, chẳng hạn khoảng thời gian, địa chỉ hoặc số tiền có đơn vị tiền tệ.
- **Quan hệ:** một đơn hàng gồm nhiều dòng hàng; một lô giao hàng thuộc một đơn hàng.
- **Thuộc tính và kiểu dữ liệu:** mã đơn, số lượng, trạng thái, thời điểm tạo.
- **Bất biến và quy tắc:** số lượng phải dương; đơn đã hủy không được tiếp tục xuất kho.
- **Hành vi và sự kiện:** xác nhận đơn, giữ hàng, thanh toán thành công, giao hàng.
- **Trạng thái và chuyển trạng thái:** mới tạo, chờ thanh toán, đã xác nhận, đang giao, hoàn tất hoặc đã hủy.
- **Vai trò và quyền hạn:** người tạo đơn, nhân viên kho, người phê duyệt, quản trị viên.

Mô hình miền tạo ra ngữ nghĩa chung để chuyên gia nghiệp vụ, người thiết kế DSL và nhóm triển khai cùng hiểu một cách nhất quán. Nó không nhất thiết là mô hình cơ sở dữ liệu hoặc sơ đồ lớp của ứng dụng. Một khái niệm miền có thể được triển khai qua nhiều bảng, dịch vụ hoặc thành phần; một bảng lưu trữ cũng không tự động trở thành một khái niệm miền.

### Quan hệ giữa hai phần

Yêu cầu và mô hình miền bổ sung cho nhau. Yêu cầu cho biết vì sao cần một khả năng hoặc quy tắc; mô hình miền làm rõ những khái niệm và quan hệ cần có để diễn đạt quy tắc đó. Mô hình cũng có thể làm lộ ra yêu cầu chưa được phát biểu, ví dụ khi phát hiện một đối tượng có vòng đời hoặc một trạng thái cần được kiểm soát.

Không nên giả định rằng mỗi yêu cầu tương ứng đúng một lớp hoặc mỗi lớp chỉ phục vụ một yêu cầu. Một yêu cầu có thể liên quan đến nhiều phần tử mô hình; một phần tử mô hình có thể hỗ trợ nhiều yêu cầu. Quan hệ này thường là nhiều-nhiều và cần được ghi rõ.

## 2. Các loại yêu cầu cần liên kết

Trước khi liên kết, cần phân loại yêu cầu để chọn phần tử mô hình và cách kiểm chứng phù hợp.

| Loại yêu cầu | Nội dung | Ví dụ trong miền xử lý đơn hàng |
|---|---|---|
| Yêu cầu chức năng | Khả năng hoặc hành động hệ thống phải hỗ trợ. | Người dùng có thể tạo đơn hàng và thêm dòng hàng. |
| Quy tắc nghiệp vụ | Điều kiện, chính sách hoặc giới hạn quyết định kết quả nghiệp vụ. | Đơn chỉ được xác nhận khi thanh toán đã được chấp nhận. |
| Yêu cầu dữ liệu | Thông tin cần lưu, trao đổi, kiểm tra hoặc bảo vệ. | Mỗi dòng hàng phải tham chiếu một mặt hàng hợp lệ và có số lượng dương. |
| Yêu cầu trạng thái và vòng đời | Trạng thái hợp lệ và điều kiện chuyển đổi. | Đơn đã giao không thể chuyển ngược về trạng thái chờ thanh toán. |
| Yêu cầu về quyền | Vai trò nào được xem, tạo, thay đổi hoặc phê duyệt đối tượng. | Chỉ nhân viên có quyền mới được phê duyệt hủy đơn sau khi xuất kho. |
| Yêu cầu phi chức năng | Chất lượng hoặc thuộc tính của giải pháp. | Kiểm tra tính hợp lệ của một tệp DSL trong thời gian phản hồi đã thống nhất. |
| Yêu cầu tích hợp | Cách trao đổi dữ liệu và hành vi với hệ thống ngoài. | Khi thanh toán thành công, hệ thống nhận được sự kiện xác nhận từ cổng thanh toán. |
| Ràng buộc | Giới hạn pháp lý, tổ chức, kỹ thuật hoặc nền tảng. | Mã tiền tệ phải tuân theo danh mục mã được tổ chức chấp nhận. |

Một yêu cầu có thể thuộc nhiều loại. Ví dụ, quy tắc lưu lịch sử phê duyệt vừa là yêu cầu chức năng vừa liên quan đến kiểm toán, bảo mật và lưu trữ dữ liệu. Nên ghi nhận các khía cạnh liên quan thay vì cố ép mọi yêu cầu vào một nhãn duy nhất.

## 3. Truy vết yêu cầu là gì?

**Truy vết yêu cầu** (*requirements traceability*) là khả năng theo dõi mối quan hệ giữa một yêu cầu với nguồn gốc, các phần tử thiết kế, phần triển khai và bằng chứng xác nhận của nó. Trong dự án DSL, truy vết cần đi qua mô hình miền vì đây là nơi chuyển nhu cầu nghiệp vụ thành ngữ nghĩa mà DSL phải biểu diễn.

Truy vết thường có hai hướng:

- **Truy vết xuôi (forward traceability):** đi từ yêu cầu đến phần tử mô hình, cấu trúc DSL, thành phần thực thi và kiểm thử. Mục đích là biết yêu cầu đã được xử lý ở đâu.
- **Truy vết ngược (backward traceability):** đi từ phần tử mô hình, cấu trúc DSL hoặc chức năng đã xây dựng ngược về yêu cầu hoặc lý do nghiệp vụ. Mục đích là biết tại sao phần tử đó tồn tại và tránh phát triển những thành phần không có căn cứ.

Ví dụ, yêu cầu `REQ-ORDER-04` quy định đơn chỉ được xác nhận sau khi thanh toán thành công. Truy vết xuôi cho thấy yêu cầu liên quan đến khái niệm `Order`, `Payment`, trạng thái `CONFIRMED`, sự kiện `PaymentAccepted`, quy tắc chuyển trạng thái và các kiểm thử tương ứng. Truy vết ngược từ quy tắc chuyển trạng thái phải chỉ ra yêu cầu hoặc chính sách đã tạo ra nó.

Sơ đồ khái quát:

~~~mermaid
flowchart LR
    S[Nhà tài trợ, người dùng, chính sách] --> R[Yêu cầu có mã định danh]
    U[Kịch bản sử dụng] --> R
    R --> M[Mô hình miền]
    M --> D[Cấu trúc và ngữ nghĩa DSL]
    D --> I[Thành phần thực thi]
    R --> T[Trường hợp kiểm thử]
    M --> T
    D --> T
    T --> E[Bằng chứng xác nhận]
~~~

Sơ đồ thể hiện các quan hệ thường gặp, không phải quy trình bắt buộc một chiều. Trong quá trình khám phá, mô hình có thể làm xuất hiện yêu cầu mới; kiểm thử có thể phát hiện yêu cầu chưa rõ; phản hồi từ người dùng có thể khiến nhóm điều chỉnh mô hình.

## 4. Xây dựng yêu cầu có thể truy vết

Muốn liên kết hiệu quả, yêu cầu cần được viết rõ và quản lý bằng mã định danh ổn định. Một câu mô tả chung như “hệ thống xử lý đơn hàng đúng cách” không đủ để xác định phần tử mô hình hoặc kiểm thử nào chứng minh được kết quả.

### Tách yêu cầu lớn thành phát biểu có thể kiểm chứng

Yêu cầu nên tập trung vào một nghĩa chính, có điều kiện và kết quả có thể nhận biết. Ví dụ:

**Phát biểu quá chung:** “Đơn hàng phải được xử lý an toàn.”

**Các phát biểu cụ thể hơn:**

- `REQ-ORD-01`: Hệ thống chỉ chuyển đơn sang trạng thái `CONFIRMED` khi có xác nhận thanh toán hợp lệ cho đơn đó.
- `REQ-ORD-02`: Mỗi dòng hàng trong đơn phải tham chiếu đến một mặt hàng đang được phép kinh doanh.
- `REQ-ORD-03`: Số lượng của mỗi dòng hàng phải là số nguyên dương.
- `REQ-ORD-04`: Mọi lần thay đổi trạng thái đơn phải lưu thời điểm, tác nhân và trạng thái trước/sau.

Các yêu cầu này có thể liên kết với phần tử mô hình cụ thể và được kiểm tra bằng ví dụ. Việc tách nhỏ không có nghĩa là xóa bối cảnh: cần giữ liên kết đến mục tiêu, chính sách hoặc yêu cầu cấp cao hơn.

### Thông tin nên ghi cho mỗi yêu cầu

| Trường | Ý nghĩa |
|---|---|
| ID | Mã định danh duy nhất, ổn định qua các lần chỉnh sửa. |
| Tên | Tiêu đề ngắn thể hiện nội dung. |
| Phát biểu | Điều hệ thống hoặc DSL phải đáp ứng. |
| Nguồn | Người, nhóm, chính sách, hợp đồng hoặc kịch bản phát sinh yêu cầu. |
| Lý do | Mục tiêu hoặc rủi ro mà yêu cầu giải quyết. |
| Loại | Chức năng, quy tắc, dữ liệu, phi chức năng, tích hợp hoặc ràng buộc. |
| Mức ưu tiên | Mức cần thiết hoặc thứ tự thực hiện đã được thống nhất. |
| Tiêu chí chấp nhận | Điều kiện quan sát được để xác nhận yêu cầu. |
| Chủ sở hữu | Người hoặc vai trò chịu trách nhiệm xác nhận ý nghĩa. |
| Trạng thái | Đề xuất, đang làm rõ, đã duyệt, đang thực hiện, đã xác nhận hoặc đã thay thế. |
| Phiên bản và lịch sử | Thời điểm, lý do và nội dung thay đổi. |

Không nhất thiết mọi dự án phải dùng một công cụ quản lý yêu cầu phức tạp. Với phạm vi nhỏ, bảng tính hoặc tài liệu có cấu trúc cũng có thể đủ, miễn mã định danh không bị thay đổi tùy tiện và các liên kết được duy trì.

### Viết tiêu chí chấp nhận

Tiêu chí chấp nhận (*acceptance criteria*) mô tả điều kiện để xác nhận yêu cầu được đáp ứng. Có thể dùng cấu trúc Given–When–Then:

~~~text
Given: Đơn hàng ORD-100 đang ở trạng thái PENDING_PAYMENT
       và chưa có xác nhận thanh toán hợp lệ.
When:  Quy trình yêu cầu xác nhận đơn được thực hiện.
Then:  Đơn không chuyển sang trạng thái CONFIRMED
       và hệ thống trả về lý do chưa thanh toán.
~~~

Tiêu chí này giúp xác định phần tử mô hình cần có: trạng thái đơn, thông tin thanh toán, điều kiện chuyển trạng thái và kết quả từ chối. Nó cũng cung cấp ví dụ để kiểm thử ngữ nghĩa DSL.

## 5. Liên kết yêu cầu với phần tử mô hình miền

Không phải yêu cầu nào cũng liên kết với cùng một loại phần tử. Cần chọn phần tử mô hình thể hiện đúng ý nghĩa nghiệp vụ của yêu cầu.

| Nội dung yêu cầu | Phần tử mô hình có thể liên quan | Câu hỏi cần xác nhận |
|---|---|---|
| Một đối tượng có danh tính riêng | Thực thể | Đối tượng có vòng đời và cần được nhận diện xuyên suốt không? |
| Một giá trị gồm nhiều thành phần | Đối tượng giá trị | Giá trị có được xác định hoàn toàn bởi nội dung và có nên bất biến không? |
| Các đối tượng có quan hệ | Liên kết hoặc kết hợp | Quan hệ có bội số, hướng sở hữu hoặc vòng đời riêng không? |
| Một điều kiện phải luôn đúng | Bất biến hoặc ràng buộc | Điều kiện phải đúng ở mọi thời điểm hay chỉ tại một hành động? |
| Một hành động nghiệp vụ | Hành vi hoặc thao tác miền | Hành động tác động lên đối tượng nào và điều kiện nào cho phép? |
| Một thay đổi đã xảy ra | Sự kiện miền | Sự kiện được phát sinh khi nào và ai cần phản ứng? |
| Vòng đời của đối tượng | Trạng thái và chuyển trạng thái | Những trạng thái nào hợp lệ và sự kiện nào kích hoạt chuyển đổi? |
| Người thực hiện được giới hạn quyền | Vai trò và chính sách ủy quyền | Quyền phụ thuộc vào vai trò, đối tượng, trạng thái hay ngữ cảnh? |
| Chất lượng hệ thống | Ràng buộc kiến trúc hoặc vận hành | Chất lượng được đo ở thành phần nào, trong điều kiện nào? |
| Trao đổi với hệ thống ngoài | Hợp đồng tích hợp hoặc cổng giao tiếp | Dữ liệu, giao thức, lỗi và trách nhiệm thuộc bên nào? |

Một yêu cầu về hiệu năng, chẳng hạn kiểm tra tệp DSL trong một khoảng thời gian xác định, thường không được biểu diễn bằng một thuộc tính của thực thể miền. Nó có thể liên kết đến trình phân tích cú pháp, bộ kiểm tra ngữ nghĩa, quy mô đầu vào và phép đo hiệu năng. Liên kết phải phản ánh nơi yêu cầu được thực hiện và kiểm chứng thực tế.

### Xác định đúng mức trừu tượng

Mô hình miền nên giữ ngôn ngữ và quy tắc của lĩnh vực. Nếu một yêu cầu được chuyển thẳng thành cấu trúc kỹ thuật như bảng `ORDER_TBL` hoặc lớp `OrderRepositoryImpl`, nhóm có thể đang trộn mô hình miền với thiết kế lưu trữ hoặc kiến trúc ứng dụng.

Ví dụ, yêu cầu “một đơn hàng có một hoặc nhiều dòng hàng” trước tiên nên được mô hình hóa thành quan hệ giữa `Order` và `OrderLine`, cùng quy tắc số lượng dòng hàng. Sau đó, nhóm triển khai mới quyết định cách lưu trữ quan hệ đó. DSL cần biểu diễn khái niệm và quy tắc ở mức mà người dùng miền hiểu được.

### Ghi rõ loại quan hệ truy vết

Chỉ ghi rằng yêu cầu “liên quan đến” một lớp thường chưa đủ. Nên dùng quan hệ có nghĩa rõ ràng, ví dụ:

- **realizes / hiện thực hóa:** phần tử mô hình cung cấp cấu trúc hoặc hành vi đáp ứng yêu cầu.
- **constrains / ràng buộc:** yêu cầu đặt giới hạn lên phần tử mô hình hoặc hành vi.
- **refines / làm rõ:** phần tử hoặc yêu cầu cấp thấp hơn cụ thể hóa một phát biểu cấp cao.
- **depends on / phụ thuộc:** việc đáp ứng một yêu cầu phụ thuộc vào phần tử hoặc khả năng khác.
- **validates / xác nhận:** trường hợp kiểm thử hoặc bằng chứng dùng để kiểm tra yêu cầu.
- **derived from / suy ra từ:** yêu cầu hoặc phần tử được rút ra từ nguồn hay yêu cầu khác.
- **conflicts with / xung đột với:** hai phát biểu không thể đồng thời được đáp ứng trong cùng điều kiện.

Tên quan hệ có thể khác nhau giữa các nhóm, nhưng ý nghĩa phải được định nghĩa trong quy ước dự án. Không nên gán `realizes` chỉ vì một phần tử có nhắc đến cùng thuật ngữ với yêu cầu.

## 6. Ví dụ xuyên suốt: Mô hình miền xử lý đơn hàng

Giả sử một nhóm xây dựng DSL để mô tả chính sách và quy trình xử lý đơn hàng. DSL cần giúp chuyên viên nghiệp vụ khai báo điều kiện xác nhận, giữ hàng, giao hàng và hủy đơn. Từ các cuộc trao đổi, nhóm thu thập một số yêu cầu ban đầu.

### Danh sách yêu cầu

| ID | Phát biểu yêu cầu | Tiêu chí chấp nhận tiêu biểu |
|---|---|---|
| REQ-01 | Mỗi đơn hàng có mã định danh duy nhất và chứa ít nhất một dòng hàng. | Không thể tạo đơn thiếu dòng hàng hoặc dùng mã đã tồn tại. |
| REQ-02 | Mỗi dòng hàng tham chiếu một mặt hàng hợp lệ và có số lượng nguyên dương. | Dòng hàng không có mặt hàng hoặc có số lượng bằng 0 bị từ chối. |
| REQ-03 | Đơn chỉ được xác nhận khi thanh toán hợp lệ đã được chấp nhận. | Yêu cầu xác nhận khi chưa thanh toán không làm đơn chuyển trạng thái. |
| REQ-04 | Hệ thống chỉ giữ hàng khi số lượng tồn khả dụng đáp ứng số lượng yêu cầu. | Không thể giữ số lượng lớn hơn tồn khả dụng. |
| REQ-05 | Đơn đã giao không thể bị hủy theo luồng hủy thông thường. | Yêu cầu hủy đơn đã giao bị từ chối hoặc chuyển đến quy trình ngoại lệ được phê duyệt. |
| REQ-06 | Mọi thay đổi trạng thái đơn phải có lịch sử tác nhân và thời điểm. | Mỗi lần chuyển trạng thái tạo một bản ghi truy vết. |

Đây là các phát biểu minh họa. Trong dự án thực tế, nhóm phải xác nhận định nghĩa “thanh toán hợp lệ”, “tồn khả dụng”, “đã giao” và “ngoại lệ được phê duyệt” với chủ sở hữu nghiệp vụ.

### Mô hình miền khái quát

Các khái niệm có thể được xác định như sau:

| Khái niệm | Ý nghĩa | Quan hệ hoặc quy tắc chính |
|---|---|---|
| `Order` | Đơn hàng có danh tính và vòng đời. | Có một hoặc nhiều `OrderLine`; có trạng thái; có lịch sử chuyển trạng thái. |
| `OrderLine` | Dòng hàng trong đơn. | Tham chiếu một `Product`; có `quantity` nguyên dương. |
| `Product` | Mặt hàng có thể được đặt. | Có mã và trạng thái kinh doanh. |
| `Payment` | Giao dịch thanh toán liên quan đến đơn. | Có kết quả và tham chiếu đến đơn tương ứng. |
| `InventoryItem` | Thông tin tồn kho của một mặt hàng tại một địa điểm. | Có số lượng khả dụng và số lượng đã giữ. |
| `Reservation` | Lượng hàng được giữ cho đơn. | Không được vượt quá lượng hàng khả dụng tại thời điểm giữ. |
| `Shipment` | Thông tin giao hàng cho đơn hoặc một phần đơn. | Có trạng thái giao nhận và sự kiện hoàn tất giao hàng. |
| `OrderStatusHistory` | Dấu vết thay đổi trạng thái. | Ghi trạng thái trước/sau, thời điểm và tác nhân. |

Mô hình này có thể được thể hiện bằng sơ đồ quan hệ khái niệm:

~~~mermaid
classDiagram
    class Order {
      +OrderId id
      +OrderStatus status
      +confirm()
      +cancel()
    }
    class OrderLine {
      +Quantity quantity
    }
    class Product {
      +ProductId id
      +ProductStatus status
    }
    class Payment {
      +PaymentStatus status
      +Money amount
    }
    class InventoryItem {
      +Quantity available
      +reserve(quantity)
    }
    class Reservation {
      +Quantity quantity
    }
    class Shipment {
      +ShipmentStatus status
    }
    class OrderStatusHistory {
      +OrderStatus fromStatus
      +OrderStatus toStatus
      +Instant changedAt
      +ActorId changedBy
    }
    Order "1" --> "1..*" OrderLine
    OrderLine "*" --> "1" Product
    Order "1" --> "0..*" Payment
    Order "1" --> "0..*" Reservation
    Reservation "*" --> "1" InventoryItem
    Order "1" --> "0..*" Shipment
    Order "1" --> "0..*" OrderStatusHistory
~~~

Sơ đồ chỉ nêu một cách mô hình hóa khả dĩ. Bội số, việc một đơn có nhiều thanh toán hay nhiều lô giao, và cách quản lý đặt giữ hàng cần được xác nhận theo nghiệp vụ thực tế.

### Bảng truy vết yêu cầu – mô hình

| Yêu cầu | Phần tử mô hình liên quan | Quan hệ | Cách xác nhận |
|---|---|---|---|
| REQ-01 | `Order`, `OrderLine`, `OrderId` | `realizes`, `constrains` | Kiểm thử tạo đơn thiếu dòng, mã trùng và đơn hợp lệ. |
| REQ-02 | `OrderLine`, `Product`, `Quantity` | `constrains` | Kiểm thử tham chiếu mặt hàng và giá trị số lượng. |
| REQ-03 | `Order`, `Payment`, `OrderStatus`, `confirm()` | `constrains`, `realizes` | Kiểm thử chuyển trạng thái với thanh toán thành công và chưa thành công. |
| REQ-04 | `InventoryItem`, `Reservation`, `reserve()` | `constrains`, `realizes` | Kiểm thử giữ hàng trong giới hạn và vượt tồn khả dụng. |
| REQ-05 | `OrderStatus`, `cancel()` | `constrains` | Kiểm thử hủy đơn ở trạng thái đang xử lý và đã giao. |
| REQ-06 | `OrderStatusHistory`, sự kiện chuyển trạng thái | `realizes`, `validates` | Kiểm thử mỗi chuyển trạng thái đều tạo dấu vết có tác nhân và thời điểm. |

Bảng này là công cụ làm rõ thiết kế. Nó không thay thế mô tả chi tiết của yêu cầu hoặc mô hình. Mỗi liên kết nên có thể mở đến định nghĩa yêu cầu, phần tử mô hình và bằng chứng kiểm thử cụ thể.

### Biểu diễn một phần quy tắc trong DSL

Khi mô hình miền và yêu cầu đã được xác nhận, nhóm có thể thiết kế một cấu trúc DSL để người dùng diễn đạt quy tắc. Ví dụ giả định:

~~~text
order_policy StandardOrder {
    require order.lines.count >= 1
    require each order.lines has line.quantity > 0
    require each order.lines references active Product

    transition Order.PENDING_PAYMENT -> Order.CONFIRMED
        when payment.status == ACCEPTED

    reserve inventory for order
        only when inventory.available >= order.requestedQuantity

    prohibit cancel Order
        when order.status == DELIVERED

    audit every Order.status change
        with actor, previousStatus, newStatus, timestamp
}
~~~

Đoạn trên minh họa cách yêu cầu có thể đi qua mô hình miền để trở thành cấu trúc DSL. Nó không phải cú pháp chuẩn. Nhóm thiết kế phải xác định ngữ nghĩa của `require`, `transition`, `reserve`, `prohibit` và `audit`, bao gồm cách kiểm tra tĩnh, xử lý lúc chạy và thông báo lỗi.

## 7. Liên kết yêu cầu phi chức năng với mô hình

Yêu cầu phi chức năng thường bị bỏ quên khi nhóm chỉ lập bảng truy vết giữa yêu cầu chức năng và các thực thể miền. Tuy nhiên, các yêu cầu này cũng cần có phần tử chịu trách nhiệm và cách kiểm chứng.

| Yêu cầu phi chức năng | Thành phần hoặc thuộc tính có thể liên quan | Bằng chứng xác nhận |
|---|---|---|
| Hiệu năng | Trình phân tích cú pháp, bộ kiểm tra ngữ nghĩa, kích thước mô hình và cấu trúc dữ liệu. | Đo thời gian xử lý trên bộ đầu vào đại diện và giới hạn đã thống nhất. |
| Bảo mật | Vai trò, chính sách truy cập, nguồn dữ liệu và môi trường thực thi. | Kiểm thử quyền, kiểm thử truy cập trái phép và đánh giá cấu hình. |
| Khả năng kiểm toán | Sự kiện miền, lịch sử thay đổi, định danh tác nhân và thời điểm. | Kiểm tra khả năng truy ngược một quyết định hoặc thay đổi cụ thể. |
| Khả năng bảo trì | Cấu trúc mô hình, quy tắc dùng chung, phiên bản DSL và tài liệu. | Thử thay đổi một quy tắc và đánh giá phạm vi ảnh hưởng. |
| Khả năng tích hợp | Kiểu dữ liệu, hợp đồng giao tiếp, adapter và ánh xạ khái niệm. | Kiểm thử hợp đồng với hệ thống bên ngoài. |
| Độ tin cậy | Trạng thái thực thi, giao dịch, xử lý lỗi và cơ chế phục hồi. | Kiểm thử lỗi phụ thuộc, thử lại, tính nhất quán và phục hồi. |
| Khả năng sử dụng | Thuật ngữ DSL, cấu trúc cú pháp, thông báo lỗi và công cụ biên tập. | Quan sát người dùng hoàn thành tác vụ và thu thập phản hồi. |

Một yêu cầu như “DSL dễ sử dụng” cần được làm rõ bằng đối tượng người dùng, tác vụ đại diện và tiêu chí quan sát được. Có thể đo thời gian hoàn thành tác vụ, tỷ lệ lỗi hoặc khả năng hiểu thông báo lỗi. Sau đó, yêu cầu được liên kết với thiết kế cú pháp, tài liệu, trình soạn thảo và bộ kiểm tra.

## 8. Tổ chức ma trận truy vết

Ma trận truy vết (*traceability matrix*) là một cách đơn giản để quản lý quan hệ giữa các yêu cầu và phần tử khác. Với dự án DSL, có thể mở rộng ma trận qua nhiều cột:

| ID yêu cầu | Nguồn / kịch bản | Phần tử mô hình | Thành phần DSL | Kiểm thử | Trạng thái |
|---|---|---|---|---|---|
| REQ-01 | UC-ORDER-01 | `Order`, `OrderLine` | `order`, `line` declarations | TEST-ORDER-01 | Đã liên kết |
| REQ-02 | UC-ORDER-01 | `Product`, `Quantity` | `references`, `require` | TEST-ORDER-02 | Đã liên kết |
| REQ-03 | UC-ORDER-02 | `Payment`, `OrderStatus` | `transition ... when` | TEST-ORDER-03 | Đã liên kết |
| REQ-04 | UC-INVENTORY-01 | `InventoryItem`, `Reservation` | `reserve inventory` | TEST-INVENTORY-01 | Đã liên kết |
| REQ-05 | POLICY-CANCEL-01 | `OrderStatus`, `cancel()` | `prohibit cancel` | TEST-ORDER-05 | Cần xác nhận ngoại lệ |

Ma trận có thể được lưu trong bảng tính, công cụ quản lý yêu cầu, hệ thống quản lý mô hình hoặc kho tài liệu có liên kết. Điều quan trọng là mỗi ID phải ổn định và quan hệ có thể cập nhật khi nội dung thay đổi.

### Ma trận nhiều-nhiều

Một yêu cầu có thể liên quan đến nhiều phần tử mô hình, và một phần tử mô hình có thể đáp ứng nhiều yêu cầu. Vì vậy, ma trận nên cho phép nhiều liên kết trên một hàng hoặc tách quan hệ thành một bảng riêng.

Ví dụ, `OrderStatus` có thể tham gia REQ-03, REQ-05 và REQ-06. Điều đó không có nghĩa ba yêu cầu trùng nhau; chúng sử dụng cùng khái niệm trạng thái cho những mục đích khác nhau. Ngược lại, REQ-03 cần `Order`, `Payment`, `OrderStatus` và hành vi xác nhận để thể hiện đầy đủ.

Khi dự án lớn, nên lưu quan hệ như các bản ghi độc lập:

| Source ID | Relationship | Target ID | Rationale |
|---|---|---|---|
| REQ-03 | constrains | MODEL-ORDER-STATUS | Quy tắc giới hạn điều kiện chuyển sang CONFIRMED. |
| REQ-03 | constrains | MODEL-PAYMENT | Điều kiện dựa trên trạng thái thanh toán. |
| MODEL-ORDER-STATUS | realized-by | DSL-TRANSITION | DSL cung cấp cú pháp khai báo chuyển trạng thái. |
| REQ-03 | validated-by | TEST-ORDER-03 | Kiểm tra cả trường hợp được và không được xác nhận. |

Cách lưu quan hệ riêng giúp truy vấn, lọc, thống kê và ghi nhận lý do của từng liên kết.

## 9. Quy trình liên kết mô hình với yêu cầu

Một quy trình thực hiện có thể chia thành các bước sau.

### Bước 1: Thu thập nguồn và xác định phạm vi yêu cầu

Thu thập mục tiêu kinh doanh, chính sách, kịch bản sử dụng, quy định, hợp đồng tích hợp và phản hồi người dùng. Xác định phần nào thuộc phạm vi miền đang mô hình hóa. Ghi nguồn gốc và người có thể xác nhận mỗi phát biểu.

### Bước 2: Làm rõ và phân rã yêu cầu

Tách phát biểu lớn thành các yêu cầu có nghĩa rõ, phân loại chúng và xác định tiêu chí chấp nhận. Ghi lại giả định và câu hỏi mở. Nếu hai bên đưa ra yêu cầu mâu thuẫn, cần ghi nhận xung đột và người có thẩm quyền giải quyết.

### Bước 3: Xây dựng mô hình miền từ bằng chứng nghiệp vụ

Xác định thuật ngữ, thực thể, đối tượng giá trị, quan hệ, quy tắc, hành vi, sự kiện và trạng thái. Mỗi khái niệm quan trọng cần có định nghĩa và ví dụ. Tránh tạo phần tử chỉ vì nó xuất hiện như một danh từ trong yêu cầu; phải hiểu vai trò và ngữ nghĩa của nó.

### Bước 4: Liên kết yêu cầu với phần tử mô hình

Với từng yêu cầu, hỏi phần tử nào thực hiện, ràng buộc hoặc làm rõ yêu cầu đó. Ghi loại quan hệ và lý do. Với từng phần tử mô hình, hỏi yêu cầu hoặc bằng chứng nào biện minh cho sự tồn tại của nó.

### Bước 5: Kiểm tra tính đầy đủ và tính hợp lý

Tìm yêu cầu chưa có phần tử mô hình hỗ trợ, phần tử chưa có nguồn gốc, quan hệ không rõ nghĩa và các yêu cầu có nhiều cách hiểu. Kiểm tra xem phần tử mô hình có thể đáp ứng đồng thời các yêu cầu liên quan hay đang tạo ra xung đột.

### Bước 6: Liên kết với thiết kế DSL và kiểm thử

Xác định cấu trúc cú pháp, quy tắc ngữ nghĩa, thành phần thực thi và thông báo lỗi tương ứng. Chuyển tiêu chí chấp nhận thành kiểm thử. Mỗi yêu cầu quan trọng cần có bằng chứng cho thấy nó được kiểm tra ở đúng lớp: kiểm tra cú pháp, kiểm tra ngữ nghĩa, kiểm tra lúc chạy hoặc kiểm thử tích hợp.

### Bước 7: Xác nhận cùng các bên liên quan

Tổ chức buổi rà soát để chuyên gia miền xác nhận khái niệm và quy tắc, người dùng xác nhận khả năng diễn đạt, nhóm kỹ thuật xác nhận tính khả thi và nhóm kiểm soát xác nhận các ràng buộc. Ghi nhận quyết định, người phê duyệt và phiên bản mô hình.

### Bước 8: Duy trì liên kết khi có thay đổi

Khi yêu cầu, mô hình hoặc DSL thay đổi, cập nhật các liên kết liên quan và đánh giá tác động. Không xem ma trận truy vết là tài liệu lập một lần rồi bỏ quên.

## 10. Kiểm tra độ bao phủ và phát hiện khoảng trống

Ma trận truy vết giúp phát hiện những khoảng trống quan trọng. Có thể xem xét từ cả hai hướng.

### Từ yêu cầu đi đến mô hình

Với từng yêu cầu, kiểm tra:

- Yêu cầu có nguồn và người xác nhận không?
- Có phần tử mô hình nào hỗ trợ hoặc ràng buộc yêu cầu không?
- Nếu yêu cầu cần được biểu diễn bằng DSL, đã xác định cấu trúc và ngữ nghĩa tương ứng chưa?
- Có tiêu chí chấp nhận và trường hợp kiểm thử không?
- Có bằng chứng cho thấy kiểm thử đã được thực hiện và đạt kết quả không?

Yêu cầu chưa có liên kết mô hình có thể chưa được phân tích, nằm ngoài phạm vi, hoặc chưa rõ cách hiện thực. Cần ghi trạng thái và quyết định rõ ràng thay vì tự coi là đã hoàn tất.

### Từ mô hình đi ngược về yêu cầu

Với từng phần tử mô hình, kiểm tra:

- Phần tử có xuất phát từ thuật ngữ, quy tắc hoặc nhu cầu đã được xác nhận không?
- Có người sở hữu định nghĩa hoặc quy tắc không?
- Nó có bị trùng ý nghĩa với phần tử khác không?
- Nếu không còn yêu cầu sử dụng, có thể loại bỏ hoặc hợp nhất không?
- Việc thay đổi phần tử sẽ ảnh hưởng đến yêu cầu, DSL và dữ liệu hiện có nào?

Phần tử không có liên kết ngược có thể là thiết kế thừa, nhưng cũng có thể là một ràng buộc kỹ thuật hoặc yêu cầu ngầm chưa được ghi nhận. Hãy tìm hiểu trước khi loại bỏ.

### Dùng chỉ số bao phủ một cách thận trọng

Nhóm có thể tính một số chỉ số hỗ trợ quản lý:

- Tỷ lệ yêu cầu trong phạm vi có ít nhất một liên kết mô hình hợp lệ.
- Tỷ lệ yêu cầu quan trọng có tiêu chí chấp nhận và kiểm thử.
- Số phần tử mô hình chưa có nguồn gốc hoặc lý do được ghi nhận.
- Số yêu cầu đang có xung đột, giả định hoặc quyết định còn mở.
- Số liên kết bị ảnh hưởng bởi một thay đổi gần đây.

Ví dụ, nếu 18 trong 20 yêu cầu đã duyệt có liên kết đến mô hình thì độ bao phủ liên kết ở mức yêu cầu là 90%. Con số này chỉ phản ánh sự tồn tại của liên kết. Nó không chứng minh rằng mô hình đúng, yêu cầu được hiểu đúng hoặc kiểm thử đủ tốt. Cần đánh giá cả chất lượng liên kết và bằng chứng xác nhận.

Không nên đặt mục tiêu 100% liên kết một cách máy móc. Một số yêu cầu có thể được xác nhận là ngoài phạm vi, bị thay thế hoặc chưa thể hiện thực vì phụ thuộc quyết định khác. Các trường hợp này cần có trạng thái và lý do rõ ràng.

## 11. Kiểm chứng liên kết bằng ví dụ và kiểm thử

Liên kết trên tài liệu chỉ có giá trị khi có thể kiểm tra bằng tình huống thực tế. Các kỹ thuật sau thường hữu ích:

**Duyệt mô hình cùng chuyên gia miền.** Đưa ra một yêu cầu và phần tử mô hình tương ứng, yêu cầu chuyên gia giải thích vì sao quan hệ đó đúng. Dùng ví dụ và phản ví dụ để làm rõ định nghĩa.

**Đi qua kịch bản sử dụng.** Với từng bước trong kịch bản, xác định khái niệm, hành động, điều kiện và trạng thái nào tham gia. Nếu một bước không thể biểu diễn bằng mô hình hiện tại, cần tìm hiểu xem mô hình thiếu gì hoặc bước đó có nằm ngoài phạm vi không.

**Kiểm thử ràng buộc.** Chuyển bất biến và điều kiện thành kiểm thử hợp lệ/không hợp lệ. Ví dụ: số lượng bằng 0 phải bị từ chối; đơn đã giao không được hủy theo luồng thông thường.

**Kiểm thử chuyển trạng thái.** Kiểm tra từng chuyển trạng thái được phép và không được phép, bao gồm điều kiện trước, sự kiện kích hoạt và kết quả.

**Kiểm thử ví dụ DSL đầu cuối.** Viết một chương trình DSL nhỏ thể hiện yêu cầu, phân tích cú pháp, kiểm tra ngữ nghĩa và thực thi hoặc mô phỏng kết quả. So sánh kết quả với tiêu chí chấp nhận.

**Kiểm thử hợp đồng tích hợp.** Khi yêu cầu liên quan đến hệ thống ngoài, kiểm tra kiểu dữ liệu, ý nghĩa trường, điều kiện lỗi và cách xử lý khi hệ thống phụ trợ không sẵn sàng.

Ví dụ một kiểm thử ngữ nghĩa cho REQ-03:

~~~text
Scenario: Không xác nhận đơn khi thanh toán chưa được chấp nhận
Given order.status = PENDING_PAYMENT
  And payment.status = PENDING
When evaluate transition PENDING_PAYMENT -> CONFIRMED
Then transition is rejected
  And order.status remains PENDING_PAYMENT
  And diagnostic identifies missing accepted payment
~~~

Kiểm thử này vừa kiểm tra quy tắc miền vừa kiểm tra cách DSL diễn giải khai báo chuyển trạng thái. Nếu chỉ kiểm tra cú pháp chấp nhận được mà không kiểm tra ngữ nghĩa, yêu cầu nghiệp vụ vẫn có thể bị vi phạm.

## 12. Liên kết với kiến trúc DSL

Mô hình miền thường là cơ sở để thiết kế các lớp khác nhau của DSL. Việc truy vết giúp xác định mỗi yêu cầu được xử lý ở đâu.

| Lớp hoặc thành phần DSL | Vai trò | Ví dụ liên kết yêu cầu |
|---|---|---|
| Ngôn ngữ thuật ngữ và mô hình miền | Định nghĩa khái niệm, kiểu, quan hệ và ngữ nghĩa nghiệp vụ. | `Order`, `Payment`, `Quantity`, `OrderStatus`. |
| Cú pháp cụ thể | Quy định cách người dùng viết cấu trúc DSL. | Khai báo `order_policy`, `require`, `transition`. |
| Cú pháp trừu tượng | Biểu diễn cấu trúc chương trình sau phân tích cú pháp. | AST node cho khai báo chính sách và biểu thức điều kiện. |
| Kiểm tra ngữ nghĩa | Kiểm tra tham chiếu, kiểu, quyền và quy tắc tĩnh. | Từ chối tham chiếu mặt hàng không tồn tại hoặc chuyển trạng thái không hợp lệ. |
| Trình thực thi hoặc trình sinh mã | Thực hiện quy tắc hoặc sinh cấu hình/mã cho nền tảng đích. | Kiểm tra thanh toán, giữ hàng và ghi lịch sử trạng thái. |
| Chẩn đoán và công cụ phát triển | Giúp người dùng hiểu lỗi và sửa chương trình DSL. | Báo dòng khai báo vi phạm điều kiện số lượng. |
| Kiểm thử và quan sát | Cung cấp bằng chứng hành vi và trạng thái thực thi. | Bộ ví dụ xác nhận và nhật ký thực thi theo yêu cầu. |

Không phải yêu cầu nào cũng cần được thực hiện trong một lớp duy nhất. Ví dụ, quy tắc số lượng nguyên dương có thể được kiểm tra ở thời điểm biên dịch nếu giá trị đã biết tĩnh, đồng thời vẫn cần kiểm tra lúc chạy nếu giá trị được lấy từ dữ liệu bên ngoài. Khi một quy tắc được kiểm tra ở nhiều nơi, cần bảo đảm các cách kiểm tra có cùng ngữ nghĩa.

## 13. Quản lý thay đổi và phân tích tác động

Yêu cầu và mô hình miền luôn có thể thay đổi khi nhóm hiểu rõ hơn về nghiệp vụ, chính sách hoặc hệ thống tích hợp. Truy vết giúp xác định phạm vi ảnh hưởng trước khi chỉnh sửa.

Ví dụ, chính sách mới cho phép hủy đơn sau khi đã giao trong một số trường hợp được phê duyệt. Thay đổi này có thể ảnh hưởng đến:

- Yêu cầu `REQ-05` và tiêu chí chấp nhận.
- Quy tắc chuyển trạng thái của `Order`.
- Khái niệm `CancellationApproval` hoặc vai trò phê duyệt.
- Cú pháp và ngữ nghĩa của khai báo hủy trong DSL.
- Bộ kiểm tra quyền và điều kiện lúc chạy.
- Kiểm thử hủy đơn, kiểm thử lịch sử trạng thái và kiểm thử tích hợp.
- Tài liệu hướng dẫn và chương trình DSL hiện có.

Một quy trình xử lý thay đổi có thể gồm:

1. Ghi nhận yêu cầu thay đổi, nguồn, lý do và người đề xuất.
2. Xác định yêu cầu, mô hình, DSL, kiểm thử và thành phần triển khai có liên kết.
3. Đánh giá tác động, rủi ro tương thích và dữ liệu hiện có.
4. Xác định người có quyền phê duyệt và các bên cần tham vấn.
5. Cập nhật yêu cầu và mô hình theo cùng một quyết định đã duyệt.
6. Cập nhật cấu trúc DSL, kiểm thử và tài liệu liên quan.
7. Chạy các kiểm thử bị ảnh hưởng và ghi nhận bằng chứng.
8. Cập nhật trạng thái truy vết và lịch sử phiên bản.

Không nên sửa mô hình trước rồi mới tìm cách hợp thức hóa yêu cầu. Nếu nhóm phát hiện mô hình không đáp ứng được tình huống, cần quay lại làm rõ yêu cầu và ghi nhận quyết định điều chỉnh.

### Quản lý phiên bản

ID yêu cầu nên ổn định ngay cả khi tên hoặc nội dung được chỉnh sửa. Nếu một yêu cầu được chia thành nhiều yêu cầu con, nên giữ quan hệ `derived from` hoặc `decomposes into`. Nếu yêu cầu bị thay thế, đánh dấu trạng thái `superseded` và liên kết đến yêu cầu thay thế thay vì xóa dấu vết cũ.

Phần tử mô hình cũng cần mã định danh hoặc đường dẫn ổn định trong kho mô hình. Nếu đổi tên hoặc hợp nhất phần tử, cập nhật các liên kết và lưu lịch sử để có thể truy ngược phiên bản đã dùng trong một bản phát hành DSL.

## 14. Phân biệt yêu cầu, quyết định thiết kế và phần tử mô hình

Ba loại thông tin này thường bị trộn lẫn:

- **Yêu cầu:** điều mà giải pháp phải đáp ứng, ví dụ “đơn chỉ được xác nhận khi thanh toán hợp lệ”.
- **Quyết định thiết kế:** lựa chọn cách đáp ứng, ví dụ “dùng sự kiện `PaymentAccepted` để kích hoạt chuyển trạng thái”.
- **Phần tử mô hình:** cấu trúc và ngữ nghĩa được định nghĩa, ví dụ thực thể `Payment`, trạng thái `ACCEPTED` và chuyển trạng thái của `Order`.

Một yêu cầu có thể được đáp ứng bằng nhiều phương án thiết kế. Mô hình miền là biểu diễn ngữ nghĩa được chọn, còn quyết định thiết kế giải thích vì sao chọn cách đó. Ghi riêng ba loại thông tin giúp nhóm thay đổi giải pháp mà không làm mất nhu cầu ban đầu.

Ví dụ, yêu cầu “ghi nhận lịch sử thay đổi trạng thái” có thể được thực hiện bằng một thực thể lịch sử riêng, nhật ký sự kiện hoặc một cơ chế kiểm toán nền tảng. Yêu cầu không nhất thiết bắt buộc một cách lưu trữ cụ thể. Nhóm cần chọn mô hình phù hợp và ghi lại quyết định để người khác hiểu được trade-off.

## 15. Những sai lầm thường gặp

**Liên kết chỉ bằng tên giống nhau.** Hai phần tử cùng chứa từ “đơn hàng” chưa chắc có quan hệ thực hiện yêu cầu. Cần giải thích rõ phần tử hỗ trợ, ràng buộc hay xác nhận yêu cầu như thế nào.

**Chỉ truy vết một chiều.** Nếu chỉ từ yêu cầu đến mô hình, nhóm có thể không phát hiện các phần tử thừa. Nếu chỉ từ mô hình về yêu cầu, nhóm có thể bỏ sót yêu cầu chưa được mô hình hỗ trợ. Cần kiểm tra cả hai hướng.

**Mô hình hóa theo cấu trúc lưu trữ.** Bắt đầu từ bảng hoặc API hiện có dễ khiến mô hình phản ánh thiết kế kỹ thuật cũ thay vì ngôn ngữ nghiệp vụ mà DSL cần diễn đạt.

**Yêu cầu quá mơ hồ.** Các phát biểu như “nhanh”, “an toàn”, “linh hoạt” không đủ để xác định phần tử hoặc kiểm thử. Cần làm rõ điều kiện, đối tượng và tiêu chí chấp nhận.

**Không phân biệt quy tắc và hành động.** “Người dùng nhấn xác nhận” là hành động tương tác; “chỉ xác nhận khi thanh toán được chấp nhận” là quy tắc. Trộn hai nội dung khiến quy tắc khó tái sử dụng và kiểm tra.

**Gán một yêu cầu cho một lớp duy nhất.** Nhiều quy tắc liên quan đến nhiều khái niệm và hành vi. Ép quan hệ một-một có thể làm mất ngữ nghĩa hoặc tạo mô hình nhân tạo.

**Không ghi lý do của liên kết.** Khi người khác xem lại, họ không biết vì sao một phần tử được cho là đáp ứng yêu cầu. Nên lưu rationale hoặc tham chiếu đến ví dụ chứng minh.

**Coi có liên kết là đã hoàn thành.** Một dòng trong ma trận không chứng minh rằng phần tử mô hình đúng hoặc hành vi đã được kiểm thử. Cần có bằng chứng xác nhận.

**Bỏ quên yêu cầu phi chức năng.** Các yêu cầu về bảo mật, hiệu năng, khả năng quan sát, bảo trì và tích hợp cũng cần nơi thực hiện và cách đo.

**Không cập nhật khi thay đổi.** Ma trận cũ có thể tạo cảm giác an toàn giả. Mọi thay đổi được duyệt cần cập nhật các liên kết và đánh giá ảnh hưởng.

## 16. Mẫu bảng liên kết có thể sử dụng

Một mẫu đơn giản có thể được dùng trong bảng tính hoặc công cụ quản lý dự án:

| ID yêu cầu | Nội dung ngắn | Nguồn | Phần tử mô hình | Loại quan hệ | DSL / thành phần | Kiểm thử | Chủ sở hữu | Trạng thái |
|---|---|---|---|---|---|---|---|---|
| REQ-XXX | Phát biểu có thể kiểm chứng | UC / policy / stakeholder | MODEL-ID | realizes / constrains / refines | DSL-ID | TEST-ID | Vai trò | Trạng thái |

Ví dụ một bản ghi chi tiết:

~~~yaml
requirement:
  id: REQ-ORD-03
  title: Confirm order only after accepted payment
  statement: An order can enter CONFIRMED only when a valid payment is ACCEPTED.
  source: UC-ORDER-02
  owner: Order Domain Owner
  acceptance:
    - pending payment keeps order in PENDING_PAYMENT
    - accepted payment permits transition to CONFIRMED
  status: approved

trace:
  - target: MODEL-ORDER-STATUS
    relation: constrains
    rationale: Defines the allowed transition to CONFIRMED.
  - target: MODEL-PAYMENT
    relation: depends_on
    rationale: Transition requires an accepted payment for the same order.
  - target: DSL-ORDER-TRANSITION
    relation: realizes
    rationale: DSL syntax declares the transition condition.
  - target: TEST-ORDER-03
    relation: validated_by
    rationale: Tests accepted and pending payment cases.
~~~

Đây là định dạng minh họa. Có thể dùng JSON, YAML, bảng dữ liệu hoặc liên kết trong công cụ mô hình tùy quy ước dự án. Cần thống nhất tên quan hệ, cách định danh và nơi lưu dữ liệu trước khi áp dụng rộng.

## 17. Vai trò của các bên trong việc xác nhận liên kết

Liên kết mô hình với yêu cầu không chỉ là nhiệm vụ của người thiết kế DSL. Các vai trò khác nhau cần tham gia ở những điểm phù hợp:

| Vai trò | Trách nhiệm trong hoạt động truy vết |
|---|---|
| Chuyên gia miền | Xác nhận thuật ngữ, khái niệm, quy tắc và các trường hợp ngoại lệ. |
| Người dùng DSL | Xác nhận cấu trúc ngôn ngữ diễn đạt đúng công việc và có thể hiểu, sử dụng. |
| Chuyên viên phân tích nghiệp vụ | Quản lý nguồn yêu cầu, tiêu chí chấp nhận, ưu tiên và các vấn đề còn mở. |
| Nhà thiết kế mô hình miền | Định nghĩa phần tử mô hình, quan hệ và bất biến; duy trì liên kết đến yêu cầu. |
| Nhà thiết kế/người triển khai DSL | Ánh xạ mô hình sang cú pháp, ngữ nghĩa, kiểm tra và thực thi. |
| Nhóm kiểm thử | Chuyển yêu cầu thành ví dụ, kiểm thử và bằng chứng xác nhận. |
| Nhóm bảo mật, vận hành và tích hợp | Xác nhận các ràng buộc phi chức năng, quyền hạn và hợp đồng hệ thống. |
| Chủ sản phẩm hoặc người có thẩm quyền | Phê duyệt phạm vi, ưu tiên, quyết định nghiệp vụ và thay đổi quan trọng. |

Với mỗi yêu cầu quan trọng, cần biết ai có quyền xác nhận nội dung nghiệp vụ và ai chịu trách nhiệm xác nhận phần triển khai. Hai trách nhiệm này có thể thuộc hai vai trò khác nhau.

## 18. Kết quả cần có sau hoạt động liên kết

Khi hoàn tất một vòng liên kết, nhóm nên có:

1. **Danh mục yêu cầu có định danh:** gồm nguồn, phát biểu, loại, ưu tiên, chủ sở hữu và tiêu chí chấp nhận.
2. **Mô hình miền có định nghĩa:** gồm thuật ngữ, khái niệm, quan hệ, quy tắc, hành vi và trạng thái đã được xác nhận.
3. **Ma trận hoặc đồ thị truy vết:** thể hiện quan hệ giữa yêu cầu, mô hình, cấu trúc DSL và kiểm thử.
4. **Danh sách khoảng trống:** yêu cầu chưa có mô hình hỗ trợ, phần tử mô hình chưa có nguồn gốc, quan hệ chưa rõ hoặc vấn đề còn mở.
5. **Bằng chứng xác nhận:** biên bản duyệt, ví dụ nghiệp vụ, kết quả kiểm thử hoặc xác nhận của người có thẩm quyền.
6. **Lịch sử thay đổi:** ghi nhận phiên bản yêu cầu, mô hình và các liên kết bị ảnh hưởng.

Các đầu ra này giúp nhóm kiểm soát phạm vi và chất lượng ngữ nghĩa của DSL. Chúng cũng hỗ trợ giải thích một cấu trúc DSL được đưa vào vì lý do gì, một yêu cầu được đáp ứng ở đâu và cần kiểm tra những gì khi có thay đổi.

## 19. Quy trình thực hành tổng hợp

Khi bắt đầu một phần miền mới, có thể áp dụng trình tự sau:

1. Thu thập mục tiêu, kịch bản sử dụng, chính sách và ràng buộc có liên quan.
2. Gán ID ổn định, phân loại và viết lại yêu cầu thành phát biểu có thể kiểm chứng.
3. Xác định thuật ngữ và xây dựng mô hình miền từ ví dụ nghiệp vụ.
4. Với từng yêu cầu, xác định phần tử mô hình hỗ trợ hoặc bị ràng buộc và ghi loại quan hệ.
5. Với từng phần tử mô hình, truy ngược về yêu cầu, nguồn hoặc lý do nghiệp vụ.
6. Liên kết các phần tử mô hình với cấu trúc cú pháp, ngữ nghĩa DSL và thành phần thực thi.
7. Chuyển tiêu chí chấp nhận thành kiểm thử và lưu bằng chứng xác nhận.
8. Rà soát khoảng trống, xung đột, phần tử thừa và các quyết định chưa được duyệt.
9. Xác nhận với chuyên gia miền, người dùng và nhóm kỹ thuật.
10. Cập nhật truy vết khi yêu cầu, mô hình hoặc DSL thay đổi.

Chất lượng của liên kết được thể hiện ở khả năng trả lời rõ ràng: **yêu cầu này bắt nguồn từ đâu, phần tử mô hình nào thể hiện nó, cấu trúc DSL nào cho phép sử dụng nó, và bằng chứng nào chứng minh yêu cầu đã được đáp ứng?** Đồng thời, với mỗi phần tử mô hình, nhóm có thể giải thích nó phục vụ nhu cầu nào và thay đổi của nó ảnh hưởng đến những yêu cầu nào. Khi duy trì được cả hai hướng truy vết, mô hình miền trở thành cầu nối đáng tin cậy giữa nhu cầu nghiệp vụ và ngôn ngữ DSL được thiết kế.
