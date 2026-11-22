# Phỏng vấn chuyên gia miền

Khi xây dựng một ngôn ngữ chuyên biệt theo miền (Domain-Specific Language — DSL), nhóm phát triển cần hiểu sâu công việc mà ngôn ngữ sẽ mô tả. Tài liệu hiện có có thể cho biết quy trình chính thức, còn mã nguồn và cơ sở dữ liệu cho thấy cách hệ thống đang vận hành. Tuy nhiên, nhiều quyết định thực tế, ngoại lệ và cách hiểu thuật ngữ chỉ nằm trong kinh nghiệm của những người trực tiếp làm công việc đó.

**Phỏng vấn chuyên gia miền** là một phương pháp khám phá có chủ đích để thu thập tri thức này. Người phỏng vấn tìm hiểu cách công việc diễn ra, những khái niệm được sử dụng, các quyết định phải đưa ra, điều kiện và giới hạn chi phối quyết định, cũng như những trường hợp bất thường. Kết quả là đầu vào để xác định phạm vi miền, xây dựng mô hình khái niệm và quyết định DSL cần biểu đạt điều gì.

## 1. Mục tiêu của cuộc phỏng vấn

Trong dự án DSL, cuộc phỏng vấn không chỉ nhằm thu thập danh sách yêu cầu tính năng. Mục tiêu là hiểu được cấu trúc của miền và ngôn ngữ mà người trong miền dùng để suy nghĩ, trao đổi và thực hiện công việc.

Người phỏng vấn cần làm rõ các nhóm thông tin sau:

- **Mục tiêu và phạm vi công việc:** người dùng muốn đạt kết quả gì, công việc bắt đầu và kết thúc ở đâu, phần nào thuộc phạm vi của hệ thống.
- **Khái niệm và thuật ngữ:** những đối tượng, vai trò, trạng thái, sự kiện và đại lượng quan trọng; mỗi thuật ngữ có nghĩa chính xác ra sao.
- **Quy trình:** các bước thường thực hiện, thứ tự, điều kiện chuyển bước, người chịu trách nhiệm và thông tin được tạo ra ở từng bước.
- **Quy tắc và quyết định:** điều kiện nào dẫn đến hành động nào, quy tắc nào được ưu tiên, ai có quyền quyết định và vì sao.
- **Ngoại lệ và trường hợp biên:** điều gì xảy ra khi dữ liệu thiếu, thông tin mâu thuẫn, thời hạn bị trễ hoặc hai quy tắc cùng áp dụng.
- **Ràng buộc:** giới hạn pháp lý, chính sách, an toàn, hiệu năng, quyền truy cập, định dạng dữ liệu hoặc yêu cầu kiểm toán.
- **Mức độ biến động:** phần nào ổn định, phần nào thay đổi thường xuyên, ai được phép thay đổi và quy trình phê duyệt là gì.

Những thông tin này giúp nhóm phân biệt điều gì là khái niệm cốt lõi của miền, điều gì là chính sách có thể thay đổi, và điều gì chỉ là chi tiết của một hệ thống đang sử dụng.

## 2. Chọn đúng người cần phỏng vấn

Không phải người có chức danh cao nhất luôn là người hiểu rõ mọi tình huống. Một chuyên gia có thể nắm chính sách tổng thể nhưng ít thực hiện thao tác hằng ngày; người trực tiếp xử lý hồ sơ có thể biết rất rõ các ngoại lệ nhưng không có quyền giải thích lý do của chính sách.

Nên lập danh sách các góc nhìn cần có trước khi mời người tham gia:

| Nhóm người tham gia | Tri thức thường cung cấp |
|---|---|
| Người thực hiện công việc hằng ngày | Trình tự thực tế, thao tác, dữ liệu đầu vào, lỗi thường gặp và cách xử lý ngoại lệ |
| Chuyên gia nghiệp vụ hoặc người ra quyết định | Mục tiêu, chính sách, tiêu chí quyết định, trường hợp được miễn trừ |
| Người quản lý quy trình | Vai trò, trách nhiệm, điểm bàn giao, phê duyệt và chỉ số vận hành |
| Chuyên gia tuân thủ, pháp lý hoặc an toàn | Nghĩa vụ bắt buộc, giới hạn, lưu vết và hậu quả khi vi phạm |
| Nhân viên hỗ trợ hoặc vận hành hệ thống | Sự cố, dữ liệu không chuẩn, tình huống hiếm và cách khôi phục |
| Người tiếp nhận kết quả ở công đoạn sau | Định dạng đầu ra, tiêu chí chấp nhận và vấn đề phát sinh khi bàn giao |

Việc chọn người phụ thuộc vào phạm vi DSL. Với DSL mô tả quy tắc phê duyệt, cần hiểu cả người đề xuất, người phê duyệt và bộ phận kiểm soát. Với DSL truy vấn dữ liệu, có thể cần người tạo báo cáo, người sở hữu dữ liệu và người vận hành kho dữ liệu.

Khi có nhiều nhóm người dùng, nên phỏng vấn đại diện của từng nhóm. Không nên gộp các quan điểm khác nhau thành một câu trả lời trung bình. Sự khác biệt giữa các nhóm có thể là quy tắc phân quyền, khác biệt theo địa bàn hoặc chính là mâu thuẫn cần được giải quyết.

## 3. Chuẩn bị trước buổi phỏng vấn

### 3.1. Xác định câu hỏi nghiên cứu

Trước buổi gặp, nhóm nên viết ngắn gọn điều mình cần hiểu. Ví dụ:

- Làm thế nào một yêu cầu được tạo, xem xét và phê duyệt?
- Những điều kiện nào khiến yêu cầu bị từ chối hoặc cần bổ sung?
- Các vai trò có quyền thực hiện hành động nào?
- Một quy tắc được áp dụng theo ngày tạo yêu cầu, ngày xử lý hay ngày hiệu lực?
- Khi hai quy tắc cùng phù hợp, quy tắc nào có ưu tiên?

Câu hỏi nghiên cứu giúp cuộc trao đổi có trọng tâm. Chúng không phải kịch bản cứng buộc chuyên gia trả lời theo một thứ tự duy nhất.

### 3.2. Tìm hiểu tài liệu nền

Nếu được phép, hãy đọc trước biểu mẫu, hướng dẫn thao tác, quy trình, báo cáo, bảng thuật ngữ, sơ đồ, mẫu dữ liệu hoặc ví dụ đã được ẩn thông tin nhạy cảm. Tài liệu nền giúp người phỏng vấn hiểu các từ khóa và đặt câu hỏi cụ thể hơn.

Tuy nhiên, tài liệu chính thức có thể khác thực tế. Hãy coi nó là giả thuyết ban đầu để kiểm chứng, không phải sự thật cuối cùng. Nếu tài liệu nói một bước luôn phải được phê duyệt nhưng chuyên gia kể rằng có trường hợp tự động thông qua, cần tìm hiểu điều kiện và thẩm quyền của trường hợp đó.

### 3.3. Chuẩn bị cách ghi nhận

Có thể dùng biểu mẫu ghi chú với các trường: chủ đề, câu hỏi, câu trả lời, ví dụ cụ thể, thuật ngữ mới, quy tắc suy ra, ngoại lệ, nguồn xác nhận và điểm cần làm rõ. Nếu muốn ghi âm hoặc ghi hình, cần thông báo trước và xin sự đồng ý theo quy định của tổ chức.

Không nên chỉ ghi lại kết luận của người phỏng vấn. Hãy lưu cả ví dụ và bối cảnh dẫn đến kết luận, bởi một câu như “đơn này được duyệt” chưa cho biết ai duyệt, theo tiêu chí nào và trạng thái trước đó là gì.

## 4. Cấu trúc một buổi phỏng vấn hiệu quả

Một buổi phỏng vấn bán cấu trúc thường linh hoạt hơn bảng câu hỏi đóng. Người phỏng vấn chuẩn bị các chủ đề chính nhưng có thể hỏi sâu khi xuất hiện thuật ngữ, quyết định hoặc ngoại lệ quan trọng.

### Bước 1: Giới thiệu mục đích và phạm vi

Giải thích ngắn gọn dự án đang tìm hiểu miền nào, thông tin sẽ được dùng để làm gì, ai sẽ xem kết quả và thời lượng dự kiến. Nói rõ rằng mục tiêu là hiểu công việc, không phải đánh giá năng lực cá nhân hay kiểm tra câu trả lời đúng sai.

### Bước 2: Để chuyên gia mô tả công việc theo cách của họ

Bắt đầu bằng câu hỏi mở, chẳng hạn: “Anh/chị có thể kể lại từ đầu đến cuối một trường hợp điển hình gần đây không?”. Để chuyên gia tự chọn điểm bắt đầu và dùng từ ngữ quen thuộc. Ghi lại các thuật ngữ chưa rõ để hỏi sau.

### Bước 3: Đi sâu vào một trường hợp thực tế

Chọn một tình huống cụ thể và lần theo từng bước: ai làm, dùng thông tin nào, quyết định điều gì, kết quả được lưu ở đâu, bước tiếp theo là gì. Hỏi cả điều kiện khiến quy trình rẽ sang nhánh khác.

### Bước 4: Khám phá ngoại lệ và quy tắc

Khi đã hiểu luồng thông thường, hỏi về trường hợp bị từ chối, thiếu dữ liệu, trễ hạn, cần sửa, được miễn trừ hoặc phải chuyển cấp. Tìm hiểu thứ tự ưu tiên nếu nhiều điều kiện cùng đúng.

### Bước 5: Kiểm tra cách hiểu

Nhắc lại bằng lời của mình: “Tôi hiểu rằng yêu cầu chỉ chuyển sang trạng thái được duyệt sau khi cả hai điều kiện A và B đều đúng. Có trường hợp nào khác không?”. Đề nghị chuyên gia sửa lại nếu diễn giải chưa chính xác.

### Bước 6: Kết thúc bằng các điểm còn mở

Tóm tắt thuật ngữ, quy tắc và câu hỏi chưa có câu trả lời. Xác định ai có thể xác nhận thêm, tài liệu nào có thể cung cấp và khi nào nhóm nên gửi lại bản ghi để chuyên gia kiểm tra.

## 5. Đặt câu hỏi để khám phá tri thức miền

Câu hỏi tốt thường yêu cầu kể lại một việc đã xảy ra hoặc giải thích lý do đằng sau một quyết định. Những câu hỏi quá rộng như “Hệ thống cần có chức năng gì?” dễ dẫn đến danh sách mong muốn mà thiếu ngữ cảnh.

| Mục đích | Câu hỏi gợi mở |
|---|---|
| Hiểu quy trình | “Anh/chị hãy mô tả lần gần nhất công việc này được thực hiện.” |
| Xác định điểm bắt đầu và kết thúc | “Sự kiện nào khiến quy trình bắt đầu? Khi nào có thể coi là hoàn tất?” |
| Tìm dữ liệu cần thiết | “Trước khi đưa ra quyết định, anh/chị cần xem những thông tin nào?” |
| Làm rõ thuật ngữ | “Ở đây từ ‘hợp lệ’ có nghĩa chính xác là gì? Có ví dụ nào không hợp lệ không?” |
| Khám phá điều kiện | “Điều gì phải đúng thì bước tiếp theo mới được thực hiện?” |
| Tìm ngoại lệ | “Lần gần nhất quy trình không diễn ra như thường lệ là khi nào? Anh/chị đã xử lý ra sao?” |
| Hiểu ưu tiên | “Nếu cả hai điều kiện này cùng đúng thì điều gì xảy ra?” |
| Xác định thẩm quyền | “Ai được phép thay đổi quyết định này? Có cần người khác xác nhận không?” |
| Hiểu hậu quả | “Nếu bỏ qua bước này thì rủi ro hoặc hậu quả là gì?” |
| Kiểm chứng tính ổn định | “Quy tắc này có thay đổi theo thời gian, loại khách hàng hay khu vực không?” |

### 5.1. Dùng câu hỏi tiếp nối

Khi chuyên gia đưa ra một nhận định, người phỏng vấn có thể hỏi tiếp:

- “Anh/chị có thể cho một ví dụ cụ thể không?”
- “Điều gì khiến trường hợp này khác trường hợp thông thường?”
- “Ai là người quyết định điều đó?”
- “Thông tin nào được dùng để kết luận?”
- “Nếu giá trị này bị thiếu hoặc không xác định thì sao?”
- “Quy tắc này có áp dụng cho mọi loại yêu cầu không?”
- “Anh/chị có nhớ lần nào quy tắc này không áp dụng không?”

Các câu hỏi tiếp nối giúp biến câu trả lời chung thành quy tắc có điều kiện và có thể kiểm chứng.

### 5.2. Tránh câu hỏi dẫn dắt

Câu hỏi dẫn dắt chứa sẵn giả định hoặc gợi ý câu trả lời. Ví dụ, “Vậy quản lý luôn phải duyệt bước cuối, đúng không?” có thể khiến người tham gia đồng ý dù thực tế có ngoại lệ.

Có thể thay bằng: “Ai có quyền duyệt bước cuối? Quyền đó thay đổi trong những tình huống nào?”. Câu hỏi trung lập giúp phát hiện quy tắc chưa được người phỏng vấn biết trước.

Tránh hỏi nhiều vấn đề trong cùng một câu, dùng thuật ngữ kỹ thuật khi chuyên gia chưa dùng chúng, hoặc ép chuyên gia chọn giữa hai phương án chưa chắc đã bao quát thực tế. Khi câu trả lời mơ hồ, yêu cầu ví dụ thay vì tự diễn giải.

## 6. Khai thác quy trình, quy tắc và ngoại lệ

Đối với DSL, ba loại thông tin này đặc biệt quan trọng vì chúng có thể trở thành cấu trúc, điều kiện và hành động trong ngôn ngữ.

### 6.1. Lần theo một quy trình từ đầu đến cuối

Vẽ hoặc ghi lại các bước theo trình tự và hỏi ở mỗi bước:

- Tác nhân nào thực hiện?
- Bước nhận đầu vào gì và tạo ra đầu ra gì?
- Điều kiện nào cho phép bước này diễn ra?
- Bước có thể bị bỏ qua, lặp lại hoặc thực hiện lại không?
- Có bước nào xảy ra song song không?
- Trạng thái của đối tượng thay đổi như thế nào?
- Khi thất bại, quy trình dừng, quay lại hay chuyển cho người khác?

Không nên chỉ ghi một danh sách bước tuyến tính nếu thực tế có nhánh, vòng lặp, xử lý song song hoặc cơ chế quay lui.

### 6.2. Biến lời giải thích thành quy tắc rõ ràng

Một quy tắc có thể được ghi theo cấu trúc:

```text
Khi <điều kiện>
thì <hành động hoặc kết quả>
trong phạm vi <đối tượng và ngữ cảnh>
trừ khi <ngoại lệ hoặc quy tắc ưu tiên cao hơn>.
```

Ví dụ minh họa trong miền mua sắm nội bộ:

```text
Khi giá trị đơn mua vượt hạn mức của nhóm
thì yêu cầu phải được chuyển đến cấp quản lý có thẩm quyền.
```

Đây mới là bản ghi quy tắc ở mức nghiệp vụ, chưa phải cú pháp DSL hoàn chỉnh. Khi phỏng vấn, cần hỏi tiếp: giá trị được tính trước hay sau thuế, hạn mức có hiệu lực theo ngày nào, đơn vị tiền tệ là gì, cấp quản lý được xác định theo nhóm nào, và điều gì xảy ra khi không có người phê duyệt thay thế.

### 6.3. Tìm trường hợp biên có giá trị

Chuyên gia thường kể luồng bình thường trước. Người phỏng vấn nên chủ động hỏi về:

- Giá trị bằng đúng ngưỡng, thấp hơn hoặc cao hơn ngưỡng.
- Dữ liệu bị thiếu, sai định dạng, trùng lặp hoặc đến muộn.
- Hai quy tắc cùng áp dụng hoặc không có quy tắc nào áp dụng.
- Một hành động được yêu cầu lặp lại.
- Đối tượng thay đổi trạng thái trong khi một bước đang xử lý.
- Quyền của người thực hiện thay đổi giữa quy trình.
- Một quyết định cần được sửa hoặc thu hồi sau khi đã hoàn tất.

Các trường hợp biên thường quyết định DSL cần toán tử so sánh nào, cách biểu diễn giá trị chưa xác định, cách xử lý xung đột và cơ chế báo lỗi ra sao.

## 7. Thu thập ngôn ngữ và khái niệm của miền

Ngôn ngữ chuyên gia sử dụng là nguồn quan trọng để thiết kế từ vựng DSL. Tuy nhiên, không nên đưa nguyên xi mọi từ xuất hiện trong cuộc trò chuyện vào ngôn ngữ. Cần xác định nghĩa, phạm vi và quan hệ của từng thuật ngữ.

Có thể lập bảng thuật ngữ như sau:

| Thuật ngữ | Định nghĩa theo chuyên gia | Ví dụ | Thuật ngữ dễ nhầm |
|---|---|---|---|
| Yêu cầu mua | Đề nghị mua hàng đang chờ xử lý theo quy trình nội bộ | Một đề nghị mua thiết bị | Đơn đặt hàng đã gửi nhà cung cấp |
| Hạn mức | Giá trị tối đa một vai trò được phép phê duyệt trong phạm vi quy định | Hạn mức của trưởng nhóm | Ngân sách còn lại của bộ phận |
| Phê duyệt | Quyết định cho phép yêu cầu chuyển sang bước tiếp theo | Quản lý chấp thuận yêu cầu | Xác nhận đã nhận hồ sơ |

Bảng trên chỉ là ví dụ minh họa. Trong miền thực tế, định nghĩa cần được xác nhận với người có thẩm quyền và đối chiếu giữa các nhóm.

Với mỗi khái niệm, nên làm rõ:

- Nó là một đối tượng, vai trò, thuộc tính, trạng thái, sự kiện, hành động hay đại lượng?
- Nó có định danh riêng hay chỉ là giá trị?
- Nó có những thuộc tính nào và thuộc tính nào bắt buộc?
- Nó liên hệ với khái niệm nào khác? Quan hệ một-một, một-nhiều hay nhiều-nhiều?
- Các từ đồng nghĩa có thực sự cùng nghĩa không?
- Một thuật ngữ có nghĩa khác nhau giữa các phòng ban hoặc theo ngữ cảnh không?

Khi một từ có nhiều nghĩa, đừng vội chọn một nghĩa duy nhất. Ghi rõ ngữ cảnh và hỏi xem DSL có cần các tên khác nhau để tránh nhầm lẫn hay không.

## 8. Từ ghi chú phỏng vấn đến mô hình miền và DSL

Cuộc phỏng vấn chỉ tạo ra dữ liệu thô. Nhóm phát triển cần chuyển dữ liệu đó thành các mô hình có thể thảo luận và xác nhận.

### 8.1. Tổ chức bằng chứng

Mỗi nhận định quan trọng nên gắn với nguồn: người cung cấp, vai trò, ngày phỏng vấn, ví dụ minh họa, tài liệu liên quan và mức độ chắc chắn. Phân biệt rõ:

- **Sự kiện được quan sát:** điều thực tế đã xảy ra trong trường hợp cụ thể.
- **Quy tắc được chuyên gia phát biểu:** cách họ mô tả điều kiện hoặc chính sách.
- **Diễn giải của nhóm phát triển:** giả thuyết về ý nghĩa hoặc cách biểu diễn kỹ thuật.
- **Điểm chưa thống nhất:** các nguồn đưa ra câu trả lời khác nhau hoặc chưa có người xác nhận.

Việc phân biệt này tránh biến suy đoán của nhóm thành yêu cầu đã được chuyên gia xác nhận.

### 8.2. Tạo mô hình khái niệm

Từ các cuộc phỏng vấn, nhóm có thể xác định:

- Các khái niệm miền và thuộc tính.
- Quan hệ giữa các khái niệm.
- Vai trò và quyền hạn.
- Trạng thái và sự kiện làm thay đổi trạng thái.
- Điều kiện, hành động, giới hạn và ngoại lệ.

Có thể biểu diễn bằng bảng thuật ngữ, sơ đồ quan hệ, sơ đồ trạng thái, sơ đồ quy trình hoặc bảng quyết định. Chọn cách biểu diễn phù hợp với loại tri thức cần làm rõ.

### 8.3. Xác định ứng viên cho DSL

Không phải mọi chi tiết thu thập được đều cần trở thành cú pháp. Hãy xem xét:

- Khái niệm nào được dùng lặp lại và có ý nghĩa ổn định?
- Quy tắc nào người dùng cần đọc, viết hoặc thay đổi?
- Điều kiện và hành động nào có thể biểu đạt bằng một cấu trúc nhất quán?
- Dữ liệu nào là đầu vào của biểu thức và kết quả nào cần được tạo ra?
- Phần nào nên là cấu hình tĩnh, phần nào cần được biểu diễn bằng biểu thức?
- Những thao tác nào phải bị cấm hoặc giới hạn?

Ví dụ, nếu chuyên gia thường mô tả quyết định theo dạng điều kiện và hành động, DSL có thể cần cấu trúc `WHEN ... THEN ...`. Nếu công việc chủ yếu là mô tả quan hệ giữa tài nguyên, một mô hình khai báo có thể phù hợp hơn. Đây là giả thuyết thiết kế cần thử nghiệm với người dùng, không phải kết luận tự động từ một cuộc phỏng vấn.

## 9. Ví dụ một đoạn phỏng vấn và cách phân tích

Giả sử nhóm đang tìm hiểu quy trình phê duyệt yêu cầu mua sắm. Một đoạn trao đổi giả định:

**Người phỏng vấn:** Anh/chị có thể kể về một yêu cầu mua gần đây đã được phê duyệt không?

**Chuyên gia:** Nhân viên tạo yêu cầu và nhập các mặt hàng. Trưởng nhóm kiểm tra trước. Nếu tổng giá trị vượt hạn mức của trưởng nhóm thì chuyển lên giám đốc bộ phận. Nếu thiếu báo giá thì trả lại để bổ sung.

**Người phỏng vấn:** Tổng giá trị được tính như thế nào? Có tính thuế và phí vận chuyển không?

**Chuyên gia:** Theo quy trình hiện tại, tổng giá trị dùng để so hạn mức đã bao gồm thuế và phí vận chuyển.

**Người phỏng vấn:** Nếu giá trị đúng bằng hạn mức thì sao?

**Chuyên gia:** Trưởng nhóm vẫn có thể duyệt. Chỉ khi vượt hạn mức mới chuyển cấp.

**Người phỏng vấn:** Nếu trưởng nhóm vắng mặt thì ai xử lý?

**Chuyên gia:** Người được ủy quyền có thể duyệt trong thời gian ủy quyền còn hiệu lực.

Từ đoạn trao đổi này, nhóm có thể ghi nhận các thông tin sau:

| Loại thông tin | Nội dung thu được | Câu hỏi cần xác nhận thêm |
|---|---|---|
| Vai trò | Nhân viên, trưởng nhóm, giám đốc bộ phận, người được ủy quyền | Ai cấp và thu hồi quyền ủy quyền? |
| Quy trình | Tạo yêu cầu → trưởng nhóm xem xét → có thể chuyển cấp | Trạng thái nào được lưu ở từng bước? |
| Quy tắc | Chỉ chuyển cấp khi tổng giá trị vượt hạn mức | Hạn mức được xác định theo thời điểm nào? |
| Dữ liệu | Tổng giá trị gồm thuế và phí vận chuyển | Cách xử lý ngoại tệ và làm tròn? |
| Ngoại lệ | Thiếu báo giá thì trả lại; người được ủy quyền có thể duyệt | Có loại yêu cầu nào được miễn báo giá? |

Một biểu diễn quy tắc ở mức khái niệm có thể là:

```text
WHEN request.total_with_tax_and_shipping > approver.limit
THEN route_to(department_director)

WHEN request.quotation_is_missing
THEN return_for_completion
```

Đoạn mã giả này không phải DSL hoàn chỉnh. Nó cho thấy cách các phát hiện từ phỏng vấn có thể gợi ý cấu trúc điều kiện và hành động. Trước khi đưa vào DSL, nhóm phải xác nhận thêm ý nghĩa của “tổng giá trị”, quy tắc chọn người phê duyệt, cách xử lý ủy quyền và những trường hợp ngoại lệ khác.

## 10. Kiểm chứng kết quả với chuyên gia

Không nên coi một cuộc phỏng vấn là xác nhận cuối cùng cho mô hình miền. Sau khi tổng hợp, hãy gửi lại bản tóm tắt ngắn hoặc tổ chức buổi walkthrough để chuyên gia kiểm tra.

Có thể trình bày một quy trình, bảng quyết định hoặc ví dụ DSL và hỏi:

- Mô hình này có phản ánh đúng cách công việc diễn ra không?
- Có bước, vai trò hoặc điều kiện nào bị thiếu không?
- Các thuật ngữ có được dùng đúng nghĩa không?
- Trường hợp nào làm quy tắc này cho kết quả sai?
- Hai nhóm có thể hiểu biểu thức này theo hai cách khác nhau không?
- Ai có thẩm quyền quyết định khi các chuyên gia bất đồng?

Đặc biệt, hãy dùng các ví dụ thực tế và trường hợp biên để kiểm chứng. Một mô hình có thể khớp với tình huống thông thường nhưng vẫn sai khi dữ liệu thiếu hoặc có ủy quyền.

Khi chuyên gia sửa mô hình, ghi lại nội dung thay đổi và lý do. Nếu hai chuyên gia không thống nhất, hãy ghi nhận cả hai quan điểm, phạm vi áp dụng và người có quyền quyết định chính sách. Không nên tự giải quyết bất đồng bằng cách chọn câu trả lời dễ triển khai hơn.

## 11. Những sai lầm thường gặp khi phỏng vấn

| Sai lầm | Hệ quả | Cách cải thiện |
|---|---|---|
| Chỉ phỏng vấn quản lý | Thiếu chi tiết thao tác và ngoại lệ thực tế | Bổ sung người trực tiếp thực hiện và người tiếp nhận đầu ra |
| Hỏi ngay về tính năng phần mềm | Thu được danh sách giải pháp thay vì hiểu vấn đề | Hỏi về công việc, quyết định và khó khăn trước |
| Chỉ hỏi quy trình lý tưởng | Bỏ qua cách hệ thống được dùng trong thực tế | Yêu cầu kể lại một trường hợp gần đây, kể cả trường hợp thất bại |
| Chấp nhận thuật ngữ mơ hồ | Các nhóm hiểu khác nhau về cùng một từ | Yêu cầu định nghĩa, ví dụ và trường hợp không thuộc khái niệm |
| Bỏ qua ngoại lệ | DSL không biểu đạt được tình huống quan trọng | Hỏi về ngưỡng, dữ liệu thiếu, xung đột và quyền thay thế |
| Dẫn dắt câu trả lời | Chuyên gia có thể đồng ý với giả định sai | Dùng câu hỏi trung lập và câu hỏi mở |
| Ghi nhận suy luận như sự thật | Mô hình miền chứa giả định chưa kiểm chứng | Gắn nguồn và trạng thái xác nhận cho từng nhận định |
| Coi một người là đại diện cho tất cả | Bỏ qua khác biệt giữa vai trò hoặc đơn vị | Đối chiếu nhiều góc nhìn và làm rõ phạm vi áp dụng |
| Không gửi lại kết quả để xác nhận | Sai lệch chỉ được phát hiện khi DSL đã triển khai | Tổ chức walkthrough bằng ví dụ và tình huống biên |

## 12. Đạo đức, bảo mật và chất lượng thông tin

Chuyên gia có thể chia sẻ dữ liệu khách hàng, thông tin kinh doanh hoặc trường hợp nhạy cảm. Chỉ thu thập dữ liệu cần thiết cho mục tiêu nghiên cứu; ưu tiên ví dụ đã ẩn danh; lưu trữ ghi chú theo chính sách của tổ chức; giới hạn người được truy cập và không đưa dữ liệu thật vào ví dụ DSL hoặc tài liệu đào tạo nếu chưa được phép.

Giải thích cách sử dụng ghi chú và bản ghi, xin phép trước khi ghi âm, và cho người tham gia cơ hội sửa những nội dung được trích dẫn hoặc diễn giải sai. Không ghi tên cá nhân vào tài liệu chia sẻ rộng nếu danh tính không cần thiết để hiểu quy tắc.

Chất lượng thông tin cũng cần được xem xét. Một chuyên gia có thể nhớ sai một trường hợp hiếm, mô tả quy trình theo quy định thay vì theo thực tế, hoặc dùng từ khác với nhóm khác. Hãy đối chiếu lời kể với tài liệu, dữ liệu đã được phép sử dụng, quan sát quy trình và phỏng vấn bổ sung. Mọi kết luận quan trọng nên có bằng chứng và phạm vi áp dụng rõ ràng.

## 13. Kết quả cần có sau hoạt động phỏng vấn

Kết quả không chỉ là tệp ghi âm hoặc biên bản dài. Một bộ đầu ra hữu ích cho khám phá miền và thiết kế DSL thường gồm:

1. **Bản đồ người liên quan:** vai trò, trách nhiệm, góc nhìn và người có thẩm quyền xác nhận.
2. **Bảng thuật ngữ:** tên khái niệm, định nghĩa, ví dụ, từ đồng nghĩa và điểm dễ nhầm.
3. **Mô tả quy trình:** các bước, nhánh, sự kiện, trạng thái, điểm bàn giao và tác nhân.
4. **Danh sách quy tắc:** điều kiện, hành động, phạm vi, ưu tiên, ngoại lệ và nguồn xác nhận.
5. **Danh sách ràng buộc:** quyền hạn, giới hạn, yêu cầu pháp lý, dữ liệu và vận hành.
6. **Tập tình huống:** ví dụ thông thường, ngoại lệ và trường hợp biên để kiểm chứng mô hình.
7. **Các câu hỏi còn mở:** vấn đề chưa rõ, mâu thuẫn giữa nguồn và người cần đưa ra quyết định.
8. **Ứng viên cho DSL:** khái niệm, biểu thức, dữ liệu đầu vào và hành động có khả năng cần được ngôn ngữ hỗ trợ.

Những đầu ra này giúp nhóm chuyển từ hiểu biết rời rạc sang mô hình miền có thể thảo luận. Chúng cũng tạo cơ sở để thiết kế từ vựng, cú pháp, ngữ nghĩa và bộ kiểm tra của DSL.

## 14. Kết luận

Phỏng vấn chuyên gia miền giúp nhóm phát triển khám phá cách công việc thực sự diễn ra, hiểu chính xác thuật ngữ, tìm ra quy tắc và ngoại lệ, đồng thời nhận diện những khác biệt giữa các vai trò. Để có kết quả đáng tin cậy, người phỏng vấn cần chuẩn bị câu hỏi, chọn đúng góc nhìn, khai thác ví dụ thực tế, ghi nhận bằng chứng và xác nhận lại cách diễn giải.

Trong quá trình xây dựng DSL, phỏng vấn là một phần của vòng lặp khám phá và kiểm chứng. Những gì chuyên gia nói cần được chuyển thành mô hình rõ ràng, thử với tình huống thực tế rồi xác nhận lại. DSL chỉ nên biểu đạt những khái niệm và quy tắc đã được hiểu đủ rõ, có phạm vi áp dụng xác định và có ngữ nghĩa nhất quán.
