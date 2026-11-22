# Xác định thuật ngữ, từ đồng nghĩa và cùng một tên nhưng khác ý nghĩa

Trong module **DATABASE_DATA_MODELING**, mục tiêu là chuyển yêu cầu nghiệp vụ thành mô hình dữ liệu có thực thể, quan hệ, thuộc tính, ràng buộc và định danh rõ ràng; sau đó mới lựa chọn cách biểu diễn quan hệ, document, đồ thị hay phân tích. Ở chương **Khảo sát yêu cầu**, việc đầu tiên là hiểu chính xác các từ mà người dùng và tài liệu nghiệp vụ đang sử dụng. Nếu một khái niệm có nhiều tên hoặc một tên được dùng cho nhiều khái niệm, mô hình dữ liệu rất dễ tạo ra thực thể trùng lặp, gộp nhầm đối tượng hoặc đặt ra ràng buộc sai.

Bài này hướng dẫn cách nhận diện thuật ngữ, xác định từ đồng nghĩa, phát hiện tên gọi đa nghĩa và lập bảng thuật ngữ nghiệp vụ để làm cơ sở cho các quyết định mô hình hóa.

**Sau bài học, bạn có thể:**

- Phân biệt tên gọi (term) với khái niệm nghiệp vụ mà tên gọi đại diện.
- Xác định hai cách gọi có thực sự cùng chỉ một khái niệm trong một phạm vi cụ thể hay không.
- Phát hiện một tên đang được dùng cho nhiều khái niệm khác nhau.
- Ghi nhận tên chuẩn, bí danh, định nghĩa, phạm vi và các trường hợp cần làm rõ.
- Chuyển kết quả phân tích thuật ngữ thành đầu vào có thể truy vết cho mô hình dữ liệu.

## 1. Vì sao phải phân tích thuật ngữ trước khi mô hình hóa?

Yêu cầu nghiệp vụ thường được thu thập từ nhiều nguồn: phỏng vấn người dùng, quy trình vận hành, biểu mẫu, báo cáo, màn hình ứng dụng, API và tài liệu hiện có. Các nguồn này có thể gọi cùng một đối tượng bằng những tên khác nhau. Ngược lại, nhiều bộ phận có thể dùng cùng một từ nhưng đang nói về những đối tượng hoặc trạng thái khác nhau.

Ví dụ trong một hệ thống bán hàng:

- Nhân viên kinh doanh nói **đơn hàng**, trong khi bộ phận kho nói **đơn xuất**.
- Người dùng gọi một người là **khách hàng**, nhưng nhân viên giao nhận lại gọi người nhận bưu kiện là **người nhận hàng**.
- Màn hình chỉ hiển thị nhãn **trạng thái**, dù hệ thống đang theo dõi trạng thái đơn hàng, thanh toán và giao hàng.
- Tài liệu ghi **mã sản phẩm**, nhưng nhân viên kho lại dùng từ đó để nói về SKU hoặc mã vạch.

Nếu chỉ dựa vào từ ngữ, người thiết kế có thể tạo hai bảng cho cùng một khái niệm, hoặc gộp hai khái niệm có vòng đời và quy tắc khác nhau vào một bảng hay một thuộc tính. Hậu quả có thể xuất hiện ở nhiều tầng: khóa và quan hệ không đúng, dữ liệu bị trộn, trạng thái khó kiểm soát, báo cáo đếm sai hoặc quy tắc nghiệp vụ không thể kiểm chứng.

Cần phân biệt hai lớp:

- **Tên gọi (term):** từ hoặc cụm từ xuất hiện trong yêu cầu, ví dụ “khách hàng”, “mã đơn”, “trạng thái”.
- **Khái niệm (concept):** ý nghĩa nghiệp vụ cụ thể mà tên gọi đại diện trong một phạm vi, bao gồm định nghĩa, vai trò, quy tắc, vòng đời và quan hệ với các khái niệm khác.

Một tên gọi không tự động tương ứng với một bảng. Một khái niệm cũng có thể có nhiều tên gọi. Vì vậy, hãy xác định khái niệm trước, sau đó mới quyết định nó được biểu diễn thành thực thể, thuộc tính, quan hệ, sự kiện hay một cấu trúc khác.

## 2. Phân biệt từ đồng nghĩa và tên gọi có nhiều nghĩa

### 2.1. Từ đồng nghĩa hoặc bí danh

Hai từ được xem là cách gọi đồng nghĩa trong một phạm vi khi chúng cùng chỉ một khái niệm và có thể thay thế cho nhau trong các yêu cầu liên quan mà không làm thay đổi quy tắc nghiệp vụ.

Ví dụ, trong một doanh nghiệp, “đơn hàng” và “đơn mua” có thể là hai cách gọi của cùng một đơn do khách hàng tạo ra. Nếu cả hai cùng có một định danh, cùng vòng đời, cùng chủ thể sở hữu và cùng quy tắc xử lý, chúng có thể được ghi thành một tên chuẩn và một bí danh.

Tuy nhiên, sự giống nhau trong giao tiếp chưa đủ để kết luận. “Giỏ hàng” và “đơn hàng” đều liên quan đến việc mua sản phẩm nhưng thường khác nhau: giỏ hàng là tập lựa chọn chưa chắc đã được xác nhận, còn đơn hàng là yêu cầu mua đã được tạo theo một quy trình xác định. Hai khái niệm này không nên bị gộp chỉ vì đôi khi người dùng gọi chung là “đơn”.

**Phép thử thay thế:** thay tên A bằng tên B trong các câu yêu cầu quan trọng. Nếu việc thay thế làm thay đổi đối tượng, điều kiện, thời điểm, người chịu trách nhiệm hoặc kết quả nghiệp vụ, hai tên chưa thể được coi là đồng nghĩa hoàn toàn.

### 2.2. Cùng một tên nhưng mang ý nghĩa khác nhau

Một tên gọi có thể được dùng cho nhiều khái niệm. Trong ngôn ngữ học, cần phân biệt hiện tượng đồng âm với hiện tượng một từ có nhiều nghĩa liên quan. Khi phân tích yêu cầu, điều quan trọng hơn là nhận ra rằng **cùng một chuỗi từ có thể đang tham chiếu đến những đối tượng nghiệp vụ khác nhau**.

Ví dụ:

- **Trạng thái:** có thể là trạng thái xử lý đơn hàng, trạng thái thanh toán hoặc trạng thái giao hàng.
- **Mã:** có thể là khóa nội bộ, số đơn hiển thị cho khách, SKU hoặc mã vạch.
- **Địa chỉ:** có thể là địa chỉ mặc định của khách hàng, địa chỉ thanh toán hoặc địa chỉ giao hàng của một đơn cụ thể.
- **Tài khoản:** có thể là tài khoản đăng nhập, tài khoản công nợ hoặc tài khoản thanh toán.

Không nên tạo một thuộc tính chung tên **status** hoặc **code** rồi giả định mọi bộ phận đang nói về cùng một thứ. Cần đặt tên đầy đủ theo khái niệm và phạm vi, chẳng hạn **order_status**, **payment_status**, **shipment_status**; hoặc **order_number**, **sku**, **barcode**.

### 2.3. Từ gần nghĩa không nhất thiết là từ đồng nghĩa

Một số từ có ý nghĩa gần nhau nhưng biểu thị vai trò, giai đoạn hoặc phạm vi khác nhau. Chúng cần được ghi nhận riêng cho đến khi nghiệp vụ xác nhận có thể hợp nhất.

| Các cách gọi | Vì sao chưa thể gộp ngay? | Câu hỏi cần xác minh |
|---|---|---|
| Khách hàng / người mua | Khách hàng có thể là chủ tài khoản hoặc tổ chức; người mua có thể chỉ vai trò thực hiện giao dịch | Người mua có luôn là khách hàng đã đăng ký không? |
| Người mua / người nhận hàng | Một người đặt hàng có thể gửi hàng cho người khác | Hai vai trò có thể thuộc hai người khác nhau không? |
| Giỏ hàng / đơn hàng | Khác thời điểm xác nhận và vòng đời | Khi nào giỏ hàng trở thành đơn hàng? |
| Sản phẩm / biến thể sản phẩm | Một sản phẩm có thể có nhiều kích cỡ, màu sắc hoặc phiên bản bán được | Giá và tồn kho được quản lý ở cấp nào? |
| Địa chỉ mặc định / địa chỉ giao hàng | Một địa chỉ hồ sơ có thể được chọn hoặc thay đổi khi đặt đơn | Địa chỉ giao hàng có cần được lưu theo từng đơn không? |

Nguyên tắc là không hợp nhất chỉ vì từ ngữ gần nhau, và cũng không tách chỉ vì cách viết khác nhau. Quyết định phải dựa trên định nghĩa và quy tắc nghiệp vụ.

## 3. Quy trình phân tích và chuẩn hóa thuật ngữ

Có thể thực hiện theo các bước sau:

### Bước 1: Thu thập tên gọi cùng ngữ cảnh sử dụng

Ghi lại nguyên văn từ hoặc cụm từ trong yêu cầu. Mỗi lần xuất hiện nên có nguồn và ngữ cảnh, ví dụ:

- Câu yêu cầu hoặc mã yêu cầu chứa thuật ngữ.
- Bộ phận hoặc vai trò sử dụng từ đó.
- Quy trình, màn hình, báo cáo hoặc API liên quan.
- Hành động xảy ra trước và sau khi thuật ngữ được nhắc đến.

Không vội thay tất cả cách gọi bằng một tên chuẩn ngay khi thu thập. Việc giữ nguyên cách diễn đạt ban đầu giúp truy lại nguồn khi có tranh luận.

### Bước 2: Xác định đối tượng mà tên gọi đang tham chiếu

Với mỗi lần xuất hiện, hãy hỏi:

- Đây là người, tổ chức, vật thể, giao dịch, sự kiện, vai trò, trạng thái, thuộc tính hay chỉ số?
- Đối tượng có định danh riêng không?
- Ai tạo, sử dụng, cập nhật hoặc chịu trách nhiệm về nó?
- Nó tồn tại trong quy trình nào và có vòng đời ra sao?
- Có quy tắc hoặc ràng buộc nào áp dụng cho nó?

Cùng một từ có thể mang ý nghĩa khác nhau khi xuất hiện trong hai quy trình. Ví dụ “tài khoản” trong đăng nhập có thể là thông tin xác thực, còn “tài khoản” trong công nợ có thể là một đối tượng kế toán. Phải ghi nhận đúng ngữ cảnh thay vì mặc định chúng là một.

### Bước 3: Kiểm tra các tên có phải đồng nghĩa không

So sánh hai cách gọi theo các tiêu chí:

1. **Cùng đối tượng:** chúng có cùng tham chiếu đến một người, vật, giao dịch hoặc khái niệm không?
2. **Cùng định danh:** nếu đối tượng có mã định danh, hai cách gọi có dùng chung một định danh không?
3. **Cùng vòng đời:** chúng có được tạo, thay đổi, kết thúc ở cùng các thời điểm không?
4. **Cùng quy tắc:** các điều kiện, quyền hạn, ràng buộc và hành động có giống nhau không?
5. **Có thể thay thế:** thay tên này bằng tên kia trong các tình huống nghiệp vụ có làm thay đổi ý nghĩa không?

Nếu các tiêu chí không khớp, hãy ghi nhận là hai khái niệm riêng hoặc một trường hợp chưa đủ thông tin. Đừng ép chúng thành bí danh chỉ để bảng thuật ngữ ngắn hơn.

### Bước 4: Phát hiện và tách các nghĩa của cùng một tên

Khi một từ xuất hiện ở nhiều bộ phận hoặc quy trình, hãy so sánh đối tượng tham chiếu, người sở hữu, vòng đời và các quy tắc áp dụng. Dùng tên có ngữ cảnh để diễn đạt rõ sự khác biệt.

Ví dụ, thay vì ghi chung “trạng thái”, hãy xác định riêng:

- Trạng thái đơn hàng: đơn đang ở giai đoạn nào trong quy trình bán hàng?
- Trạng thái thanh toán: khoản thanh toán đã được khởi tạo, xác nhận hay hoàn tất?
- Trạng thái giao hàng: kiện hàng đang được chuẩn bị, vận chuyển hay đã giao?

Một đơn có thể đã được xác nhận trong khi thanh toán còn chờ xử lý; kiện hàng cũng có thể chưa được bàn giao cho đơn vị vận chuyển. Những trạng thái này có quan hệ với nhau nhưng không phải một khái niệm duy nhất.

### Bước 5: Chọn tên chuẩn và ghi rõ phạm vi

Tên chuẩn nên:

- Dễ hiểu với người làm nghiệp vụ và nhất quán trong tài liệu.
- Diễn đạt đúng khái niệm, tránh phụ thuộc vào tên nút hoặc nhãn màn hình.
- Đủ cụ thể để phân biệt với khái niệm gần nghĩa.
- Ổn định theo thời gian; nếu có mã viết tắt thì giải thích rõ.
- Có phạm vi áp dụng, nhất là khi một thuật ngữ được dùng ở nhiều bộ phận.

Các tên khác được giữ lại dưới dạng bí danh hoặc cách gọi theo nguồn. Tên chuẩn giúp tài liệu nhất quán; bí danh giúp người đọc vẫn tìm được thuật ngữ quen thuộc.

### Bước 6: Xác nhận với người có trách nhiệm nghiệp vụ

Đưa ra tình huống cụ thể thay vì chỉ hỏi “hai từ này có giống nhau không?”. Hãy hỏi ai thực hiện, đối tượng nào bị tác động, quy tắc nào được áp dụng và điều gì xảy ra trong trường hợp ngoại lệ. Xác nhận với các bộ phận có liên quan nếu cùng thuật ngữ xuất hiện trong nhiều quy trình.

### Bước 7: Liên kết thuật ngữ với mô hình dữ liệu

Sau khi ý nghĩa đã rõ, ghi nhận khái niệm sẽ được xem xét như thực thể, thuộc tính, quan hệ, vai trò, sự kiện hay chỉ số. Đây là gợi ý để bước mô hình hóa tiếp tục phân tích, không phải quyết định tạo bảng tự động từ mỗi dòng trong bảng thuật ngữ.

Quy trình tổng quát:

~~~mermaid
flowchart TD
    A["Thu thập từ ngữ trong yêu cầu"] --> B["Ghi nguồn và ngữ cảnh"]
    B --> C["Xác định khái niệm được tham chiếu"]
    C --> D{"Các cách gọi có cùng ý nghĩa?"}
    D -->|Có| E["Chọn tên chuẩn và lưu bí danh"]
    D -->|Không hoặc chưa rõ| F["Tách nghĩa hoặc ghi câu hỏi cần xác minh"]
    E --> G["Xác nhận với nghiệp vụ"]
    F --> G
    G --> H["Lập bảng thuật ngữ có truy vết"]
    H --> I["Liên kết với mô hình dữ liệu"]
~~~

## 4. Ví dụ thực tế: phân tích thuật ngữ trong hệ thống bán hàng

Giả sử nhóm phân tích nhận được yêu cầu:

> Khách hàng chọn sản phẩm và tạo đơn hàng. Đơn được giao đến địa chỉ khách hàng. Sau khi thanh toán, nhân viên cập nhật trạng thái. Mỗi sản phẩm và đơn hàng có mã riêng.

Đoạn mô tả có vẻ dễ hiểu nhưng còn nhiều điểm chưa đủ rõ để thiết kế dữ liệu.

| Từ hoặc cụm từ | Những cách hiểu có thể có | Cần hỏi hoặc xác minh |
|---|---|---|
| Khách hàng | Người đặt mua, chủ tài khoản, người thanh toán hoặc người nhận hàng | Người đặt và người nhận có thể khác nhau không? Có đơn hàng mua hộ hoặc mua cho tổ chức không? |
| Địa chỉ khách hàng | Địa chỉ mặc định, địa chỉ thanh toán, địa chỉ giao hàng | Địa chỉ nào được dùng cho đơn? Nếu hồ sơ khách hàng thay đổi, địa chỉ của đơn cũ có thay đổi theo không? |
| Trạng thái | Trạng thái đơn, thanh toán hoặc giao hàng | Ai cập nhật từng trạng thái? Sự kiện nào làm trạng thái thay đổi? |
| Mã | Khóa nội bộ, số đơn hiển thị, SKU hoặc mã vạch | Ai sử dụng mã? Mã có duy nhất trong phạm vi nào? Có thay đổi được không? |
| Sản phẩm | Mặt hàng trong danh mục hoặc biến thể có thể bán | Tồn kho và giá được quản lý theo sản phẩm chung hay theo từng biến thể? |

### 4.1. Tách vai trò của khách hàng

Không nên giả định người đặt hàng, người thanh toán và người nhận hàng luôn là một người. Trong đơn tặng quà, người mua và người nhận khác nhau. Trong mua hàng doanh nghiệp, người đặt, người phê duyệt và pháp nhân thanh toán có thể là các chủ thể khác nhau.

Trước khi mô hình hóa, cần làm rõ:

- Khách hàng là cá nhân, tổ chức hay cả hai?
- Người mua có bắt buộc phải có tài khoản không?
- Người nhận hàng có cần được quản lý như một khách hàng độc lập không?
- Hệ thống có cần lưu người thanh toán hoặc người phê duyệt riêng không?

Nếu cùng một người có thể đóng nhiều vai trò, mô hình có thể biểu diễn một chủ thể với các vai trò khác nhau. Chỉ tạo các thực thể riêng khi có định danh, vòng đời hoặc quy tắc độc lập được nghiệp vụ xác nhận.

### 4.2. Phân biệt các loại địa chỉ

“Địa chỉ khách hàng” là cách nói chưa đủ cụ thể. Địa chỉ trong hồ sơ khách hàng có thể được chỉnh sửa; địa chỉ giao hàng của đơn là thông tin gắn với một giao dịch cụ thể. Địa chỉ thanh toán có thể có mục đích và quy tắc kiểm tra khác.

Một câu hỏi quan trọng là: khi khách hàng đổi địa chỉ mặc định, đơn hàng đã đặt có tiếp tục giao đến địa chỉ cũ không? Nếu nghiệp vụ yêu cầu giữ lại địa chỉ tại thời điểm đặt hàng, dữ liệu giao hàng cần được lưu theo đơn hoặc theo một cơ chế lịch sử phù hợp. Không thể suy ra quyết định này chỉ từ cụm từ “địa chỉ khách hàng”.

### 4.3. Tách các loại trạng thái

Một thuộc tính tên **status** không đủ diễn đạt ba vòng đời khác nhau. Cần xác nhận riêng các trạng thái hợp lệ và sự kiện chuyển trạng thái của từng quy trình.

| Khái niệm chuẩn | Câu hỏi nghiệp vụ | Ví dụ tên trong mô hình |
|---|---|---|
| Trạng thái đơn hàng | Đơn đang ở giai đoạn nào của quy trình bán hàng? | **order_status** |
| Trạng thái thanh toán | Giao dịch thanh toán đã được xử lý đến đâu? | **payment_status** |
| Trạng thái giao hàng | Việc chuẩn bị và vận chuyển kiện hàng đang ở giai đoạn nào? | **shipment_status** |

Các giá trị cụ thể như “chờ xác nhận”, “đã xác nhận”, “đã thanh toán” hay “đã giao” chỉ nên được đưa vào mô hình sau khi xác nhận quy tắc chuyển trạng thái. Không phải mọi trạng thái đều áp dụng cho mọi quy trình.

### 4.4. Phân biệt các loại mã

“Mã” là tên gọi quá chung. Ví dụ:

- **order_id:** định danh nội bộ của đơn hàng, phục vụ liên kết dữ liệu.
- **order_number:** số đơn dễ đọc để khách hàng và nhân viên tra cứu.
- **sku:** mã nhận diện một đơn vị hàng hóa có thể bán hoặc quản lý tồn kho.
- **barcode:** mã được mã hóa để thiết bị quét, có thể liên kết tới SKU hoặc đối tượng khác theo quy tắc hệ thống.

Các mã này có thể cùng xuất hiện trên một màn hình nhưng có mục đích, phạm vi duy nhất và vòng đời khác nhau. Không nên dùng một cột **code** chung nếu chưa chứng minh được các loại mã có cùng ý nghĩa và quy tắc.

### 4.5. Bảng thuật ngữ rút gọn sau khi xác minh

Bảng sau minh họa cách ghi nhận kết quả. Các bí danh và định nghĩa cần được xác nhận với doanh nghiệp trước khi coi là chính thức.

| ID khái niệm | Tên chuẩn | Bí danh có thể chấp nhận | Không đồng nhất với |
|---|---|---|---|
| **CUSTOMER** | Khách hàng | Người mua, nếu cùng chỉ chủ thể mua trong phạm vi bán hàng | Người nhận hàng, người liên hệ |
| **ORDER** | Đơn hàng | Đơn mua, nếu cùng vòng đời giao dịch | Giỏ hàng, phiếu giao hàng |
| **ORDER_STATUS** | Trạng thái đơn hàng | Trạng thái đơn | Trạng thái thanh toán, trạng thái giao hàng |
| **PAYMENT_STATUS** | Trạng thái thanh toán | Trạng thái giao dịch, nếu cùng quy trình thanh toán | Trạng thái đơn hàng |
| **SHIPPING_ADDRESS** | Địa chỉ giao hàng | Địa chỉ nhận hàng | Địa chỉ thanh toán, địa chỉ mặc định |
| **SKU** | Mã SKU | Mã hàng, nếu doanh nghiệp dùng đúng nghĩa này | Mã đơn hàng, mã vạch |

## 5. Lập bảng thuật ngữ nghiệp vụ

Bảng thuật ngữ (business glossary) là nơi lưu tên chuẩn và định nghĩa đã thống nhất. Đây là tài liệu dùng chung giữa người phân tích, người làm nghiệp vụ, nhà phát triển, người kiểm thử và người quản trị dữ liệu.

Một mục thuật ngữ nên có các thông tin:

| Trường | Mục đích |
|---|---|
| **concept_id** | Định danh ổn định của khái niệm, không phụ thuộc cách viết tên |
| **canonical_name** | Tên chuẩn được dùng trong tài liệu và mô hình |
| **definition** | Định nghĩa nghiệp vụ ngắn gọn, có thể kiểm chứng |
| **scope** | Bộ phận, quy trình hoặc ngữ cảnh áp dụng |
| **aliases** | Từ đồng nghĩa, tên cũ, cách gọi trên màn hình hoặc cách gọi địa phương |
| **not_same_as** | Các khái niệm dễ nhầm nhưng phải phân biệt |
| **source_requirements** | Yêu cầu hoặc tài liệu làm căn cứ |
| **owner** | Người hoặc bộ phận có trách nhiệm xác nhận ý nghĩa |
| **status** | Trạng thái xác nhận hoặc câu hỏi còn mở |

Ví dụ cấu trúc có thể dùng trong tài liệu dự án:

~~~yaml
terms:
  - concept_id: CUSTOMER
    canonical_name: Khách hàng
    scope: Bán hàng
    definition: Chủ thể mua hàng hoặc duy trì quan hệ mua bán với doanh nghiệp.
    aliases:
      - Người mua
    not_same_as:
      - Người nhận hàng
      - Người liên hệ
    source_requirements:
      - REQ-SALES-001
    owner: Bộ phận kinh doanh
    status: confirmed

  - concept_id: ORDER_STATUS
    canonical_name: Trạng thái đơn hàng
    scope: Vòng đời đơn hàng
    definition: Giá trị thể hiện giai đoạn xử lý của một đơn hàng.
    aliases:
      - Trạng thái đơn
    not_same_as:
      - Trạng thái thanh toán
      - Trạng thái giao hàng
    source_requirements:
      - REQ-ORDER-004
    owner: Bộ phận vận hành đơn hàng
    status: confirmed

  - concept_id: SHIPPING_ADDRESS
    canonical_name: Địa chỉ giao hàng
    scope: Đơn hàng
    definition: Địa điểm được chọn để giao một đơn hàng cụ thể.
    aliases:
      - Địa chỉ nhận hàng
    not_same_as:
      - Địa chỉ thanh toán
      - Địa chỉ mặc định của khách hàng
    source_requirements:
      - REQ-DELIVERY-002
    owner: Bộ phận giao nhận
    status: unresolved
    open_questions:
      - Có cần lưu lại địa chỉ tại thời điểm đặt đơn không?
~~~

Trong ví dụ, **CUSTOMER** và **ORDER_STATUS** đã được xác nhận, còn **SHIPPING_ADDRESS** vẫn có câu hỏi mở. Trạng thái **unresolved** có nghĩa là chưa đủ căn cứ để chốt quyết định mô hình hóa. Không nên tự điền một câu trả lời kỹ thuật thay cho xác nhận nghiệp vụ.

## 6. Từ bảng thuật ngữ đến mô hình dữ liệu

Bảng thuật ngữ giúp quyết định mô hình dựa trên ý nghĩa đã thống nhất. Một số nguyên tắc quan trọng:

- **Nhiều bí danh, một khái niệm:** dùng một định danh khái niệm và một cách biểu diễn nhất quán. Không tạo nhiều bảng hoặc cột chỉ vì tài liệu dùng nhiều từ khác nhau.
- **Một tên, nhiều khái niệm:** tách tên theo ngữ cảnh và quy tắc. Ví dụ trạng thái đơn, thanh toán và giao hàng cần được mô tả riêng.
- **Nhiều vai trò, một chủ thể:** nếu cùng một người có thể là người mua và người nhận, hãy xác định quan hệ vai trò trước khi quyết định có cần thực thể riêng.
- **Một từ chỉ một vai trò trong một quy trình:** “người phê duyệt” có thể là vai trò của nhân viên, không nhất thiết là một loại thực thể mới.
- **Định danh có mục đích riêng:** phân biệt khóa kỹ thuật, mã nghiệp vụ hiển thị và mã dùng cho vận hành.
- **Không chọn cấu trúc lưu trữ chỉ từ tên gọi:** cần xác định ý nghĩa và quy tắc trước, rồi mới lựa chọn cách biểu diễn.

Cùng một bảng thuật ngữ có thể hỗ trợ nhiều kiểu mô hình:

| Cách mô hình hóa | Cách dùng kết quả phân tích thuật ngữ |
|---|---|
| Quan hệ | Xác định tên bảng, cột, khóa ngoại và ràng buộc; ví dụ tách dữ liệu đơn hàng, thanh toán và giao hàng khi chúng có vòng đời riêng |
| Document | Giữ tên trường có ngữ nghĩa rõ trong tài liệu; ví dụ phân biệt **orderStatus** và **paymentStatus**, dù hai phần dữ liệu có thể cùng nằm trong một document |
| Đồ thị | Xác định đúng loại nút và quan hệ; ví dụ **Customer** — **PLACED** → **Order**, còn người nhận có thể được biểu diễn bằng vai trò hoặc quan hệ khác |
| Phân tích | Định nghĩa nhất quán chiều và chỉ số; ví dụ không trộn trạng thái thanh toán với trạng thái giao hàng khi phân tích hiệu quả vận hành |

Một khái niệm có thể được biểu diễn khác nhau tùy mục tiêu và ràng buộc hệ thống. Bảng thuật ngữ giữ cho ý nghĩa nghiệp vụ nhất quán dù cấu trúc vật lý thay đổi.

## 7. Làm rõ thuật ngữ trong các ngữ cảnh khác nhau

Không phải lúc nào doanh nghiệp cũng có một định nghĩa duy nhất cho một từ trên toàn hệ thống. Ví dụ, “khách hàng” trong bán hàng có thể là người mua; trong kế toán, khái niệm khách hàng có thể gắn với hồ sơ công nợ; trong chăm sóc khách hàng, nó có thể gắn với người liên hệ và lịch sử hỗ trợ.

Khi đó, cần ghi rõ **phạm vi nghiệp vụ** cho từng định nghĩa. Hai khái niệm trong hai ngữ cảnh có thể liên quan hoặc dùng chung một định danh chủ thể, nhưng không nên mặc định chúng có cùng thuộc tính và quy tắc. Nếu cần trao đổi dữ liệu giữa các ngữ cảnh, hãy ghi rõ cách ánh xạ và trách nhiệm của từng bên.

Một cách kiểm tra hữu ích là hỏi:

- Từ này được dùng trong quy trình nào?
- Ai là người có quyền tạo hoặc thay đổi dữ liệu?
- Định nghĩa có khác khi chuyển sang bộ phận khác không?
- Hai hệ thống có cùng quy tắc định danh và cập nhật không?
- Nếu hai bên không thống nhất, bên nào là nguồn có thẩm quyền cho từng thuộc tính?

Khi thuật ngữ thay đổi theo thời gian, hãy giữ lại bí danh hoặc tên cũ cùng thời điểm và nguồn áp dụng. Không âm thầm đổi định nghĩa của một thuật ngữ đang được dùng trong báo cáo, API hoặc dữ liệu lịch sử.

## 8. Những lỗi thường gặp

1. **Gộp từ vì nghe giống nhau:** “khách hàng” và “người nhận” có thể là hai vai trò khác nhau. Cần kiểm tra tình huống thực tế trước khi gộp.
2. **Tách đối tượng chỉ vì có nhiều tên:** “đơn mua” và “đơn hàng” có thể là bí danh trong một quy trình. Hãy kiểm tra định danh và vòng đời trước khi tạo hai thực thể.
3. **Dùng tên chung cho nhiều nghĩa:** các trường **status**, **code**, **type** khó hiểu nếu không có ngữ cảnh và định nghĩa.
4. **Lấy tên trên giao diện làm định nghĩa:** nhãn hiển thị thường được rút gọn để tiết kiệm chỗ, không phải lúc nào cũng thể hiện đầy đủ ý nghĩa dữ liệu.
5. **Bỏ qua phạm vi:** một từ có thể mang nghĩa khác trong bán hàng, kế toán và kho vận.
6. **Không lưu nguồn và người xác nhận:** khi phát sinh tranh luận, nhóm dự án không biết định nghĩa đến từ đâu và ai có quyền quyết định.
7. **Tự giải quyết câu hỏi nghiệp vụ bằng lựa chọn kỹ thuật:** nếu chưa rõ địa chỉ giao hàng có cần lưu lịch sử, không thể tự kết luận chỉ vì chọn document hay quan hệ.
8. **Không cập nhật bí danh:** tên cũ trong biểu mẫu, API hoặc báo cáo vẫn có thể xuất hiện; nếu không lưu lại, người đọc sẽ khó đối chiếu.

## 9. Checklist kiểm tra trước khi chuyển sang mô hình hóa

- [ ] Các thuật ngữ quan trọng đều có nguồn và ngữ cảnh xuất hiện.
- [ ] Mỗi khái niệm có một định nghĩa đủ rõ để người khác kiểm tra.
- [ ] Các bí danh đã được kiểm tra bằng đối tượng, vòng đời và quy tắc nghiệp vụ.
- [ ] Các từ có nhiều nghĩa đã được tách theo phạm vi hoặc ghi thành câu hỏi cần xác minh.
- [ ] Tên chuẩn đủ cụ thể để tránh nhầm với khái niệm gần nghĩa.
- [ ] Các vai trò như người mua, người nhận, người thanh toán và người phê duyệt đã được phân biệt.
- [ ] Các mã định danh và trạng thái có mục đích, phạm vi và quy tắc riêng.
- [ ] Mỗi mục quan trọng có người hoặc bộ phận chịu trách nhiệm xác nhận.
- [ ] Các câu hỏi chưa được giải quyết được ghi rõ, không bị biến thành giả định trong mô hình.
- [ ] Thuật ngữ đã được liên kết với yêu cầu nguồn để có thể truy vết khi mô hình thay đổi.

## 10. Bài tập áp dụng

Một yêu cầu khác ghi:

> Người mua có thể cập nhật địa chỉ mặc định trong hồ sơ. Khi tạo đơn, người mua chọn địa chỉ giao hàng. Kế toán theo dõi trạng thái thanh toán, còn kho theo dõi trạng thái giao hàng. Khách hàng có thể tra cứu đơn bằng mã đơn.

Hãy xác định:

1. “Người mua” và “khách hàng” có thể là bí danh trong phạm vi nào? Cần xác minh điều gì?
2. “Địa chỉ mặc định” và “địa chỉ giao hàng” có phải một khái niệm không?
3. Hai cụm “trạng thái thanh toán” và “trạng thái giao hàng” có thể dùng chung một thuộc tính nghiệp vụ không?
4. “Mã đơn” nên được phân biệt thế nào với khóa nội bộ của đơn hàng?

**Gợi ý phân tích:**

- “Người mua” có thể là cách gọi của “khách hàng” trong quy trình đặt mua nếu cùng chỉ một chủ thể. Cần xác minh trường hợp mua hộ, mua cho tổ chức hoặc đặt hàng không cần tài khoản.
- “Địa chỉ mặc định” thuộc hồ sơ khách hàng; “địa chỉ giao hàng” gắn với lựa chọn của một đơn. Có thể chúng chứa cùng thông tin địa chỉ nhưng khác mục đích và thời điểm áp dụng.
- Trạng thái thanh toán và trạng thái giao hàng thuộc hai quy trình do hai bộ phận theo dõi, vì vậy cần định nghĩa và quy tắc chuyển trạng thái riêng.
- Mã đơn dùng để tra cứu với người dùng có thể là số đơn nghiệp vụ; khóa nội bộ dùng để liên kết dữ liệu. Hai giá trị có thể cùng định danh một đơn nhưng có mục đích, định dạng và quy tắc khác nhau.

Kết quả mong đợi của bài tập là một bảng thuật ngữ có tên chuẩn, bí danh, phạm vi, định nghĩa, khái niệm dễ nhầm và câu hỏi còn mở. Khi các ý nghĩa đã được xác nhận, nhóm mới có đủ căn cứ để quyết định thực thể, thuộc tính, quan hệ, khóa và ràng buộc trong mô hình dữ liệu.
