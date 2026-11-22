# Vai trò của chuyên gia nghiệp vụ và nhóm phát triển trong xây dựng mô hình

Trong Domain-Driven Design (DDD), mô hình miền không phải là bản vẽ do kiến trúc sư tạo ra rồi bàn giao cho lập trình viên, cũng không phải là bản sao của cấu trúc cơ sở dữ liệu. Đó là cách diễn đạt có chọn lọc về nghiệp vụ: những khái niệm quan trọng, mối quan hệ giữa chúng, các quy tắc chi phối hành vi và những quyết định mà phần mềm cần hỗ trợ.

Mô hình tốt hình thành từ sự cộng tác liên tục giữa **chuyên gia nghiệp vụ** và **nhóm phát triển**. Chuyên gia nghiệp vụ mang đến hiểu biết về mục tiêu, quy trình, chính sách và những ngoại lệ trong thực tế. Nhóm phát triển giúp biến hiểu biết đó thành mô hình rõ ràng, nhất quán, có thể kiểm chứng và triển khai trong phần mềm. Hai bên cùng đặt câu hỏi, kiểm tra giả định và điều chỉnh mô hình khi hiểu biết về miền nghiệp vụ thay đổi.

Sự cộng tác này là nền tảng của DDD. Nó giúp nhóm tìm đúng vấn đề cần giải quyết, xây dựng ngôn ngữ chung, xác định ranh giới mô hình ở mức chiến lược, rồi thể hiện các quy tắc nghiệp vụ bằng những cấu trúc ở mức chiến thuật như entity, value object, aggregate, repository và domain event.

## 1. Mô hình miền là kết quả của đối thoại

**Miền nghiệp vụ (domain)** là lĩnh vực vấn đề mà tổ chức đang hoạt động, chẳng hạn bán lẻ, vận tải, bảo hiểm hoặc quản lý bệnh viện. Trong một miền có nhiều hoạt động, quy tắc, vai trò và cách nhìn khác nhau. Phần mềm thường chỉ cần mô hình hóa một phần của miền để phục vụ một mục tiêu cụ thể.

**Mô hình miền (domain model)** là sự trừu tượng hóa những khía cạnh quan trọng của phần miền đó. Mô hình có thể mô tả:

- Các khái niệm nghiệp vụ, chẳng hạn Đơn hàng, Hợp đồng, Lịch giao hàng hoặc Khoản phải thu.
- Trạng thái và vòng đời của những khái niệm đó.
- Các quy tắc, điều kiện và bất biến mà nghiệp vụ phải tuân thủ.
- Mối quan hệ và cách các bộ phận nghiệp vụ phối hợp với nhau.
- Những sự kiện có ý nghĩa, chẳng hạn Đơn hàng đã được xác nhận hoặc Hợp đồng đã hết hiệu lực.

Mô hình không cố gắng phản ánh mọi chi tiết của thế giới thực. Nó chọn ra những gì cần thiết để giải thích và giải quyết bài toán đang xét. Vì vậy, hai nhóm làm việc ở hai mục tiêu khác nhau có thể cần hai mô hình khác nhau cho cùng một đối tượng ngoài đời.

Ví dụ, từ “đơn hàng” có thể được dùng trong bộ phận bán hàng để chỉ cam kết mua hàng của khách. Bộ phận kho lại quan tâm đến yêu cầu lấy và đóng gói hàng; bộ phận kế toán quan tâm đến chứng từ và nghĩa vụ thanh toán. Nếu cả hệ thống ép mọi bộ phận dùng chung một lớp `Order` với cùng ý nghĩa, mô hình có thể trở nên mơ hồ và chứa nhiều quy tắc không liên quan với nhau.

DDD giải quyết vấn đề này bằng việc cùng chuyên gia nghiệp vụ xác định phạm vi và ngôn ngữ của từng mô hình. Ở mức chiến lược, nhóm tìm các subdomain, bounded context và quan hệ giữa các context trong context map. Ở mức chiến thuật, nhóm thể hiện các khái niệm và quy tắc của từng context bằng entity, value object, aggregate, repository và domain event khi những cấu trúc đó thực sự phù hợp.

## 2. Vai trò của chuyên gia nghiệp vụ

Chuyên gia nghiệp vụ là người có hiểu biết sâu về công việc mà phần mềm cần hỗ trợ. Họ có thể là nhân viên trực tiếp vận hành, người quản lý quy trình, chuyên viên nghiệp vụ, người phụ trách chính sách hoặc người có thẩm quyền giải thích các quyết định trong lĩnh vực đó. Chức danh không quan trọng bằng khả năng cung cấp kiến thức đáng tin cậy và giải thích được lý do đằng sau cách nghiệp vụ vận hành.

### 2.1. Giải thích mục tiêu và bối cảnh

Chuyên gia giúp nhóm hiểu tổ chức đang cố đạt được điều gì, ai tham gia vào quy trình, kết quả nào được xem là thành công và vấn đề nào đang gây tốn kém hoặc rủi ro. Cùng một yêu cầu bề mặt có thể xuất phát từ những mục tiêu rất khác nhau.

Chẳng hạn, yêu cầu “cho phép hủy đơn hàng” chưa đủ để xây dựng mô hình. Chuyên gia cần giải thích khách hàng được hủy ở thời điểm nào, ai có quyền hủy, điều gì xảy ra khi kho đã đóng gói, khi hàng đã giao cho đơn vị vận chuyển hoặc khi thanh toán đã được quyết toán. Những câu trả lời này làm rõ chính sách nghiệp vụ mà phần mềm phải bảo vệ.

### 2.2. Cung cấp thuật ngữ và ý nghĩa chính xác

Trong thực tế, cùng một từ có thể mang nhiều nghĩa, và cùng một khái niệm có thể được gọi bằng nhiều tên. Chuyên gia giúp nhóm phân biệt những khác biệt có ý nghĩa nghiệp vụ.

Ví dụ, “khách hàng”, “người mua”, “người nhận hàng” và “người thanh toán” đôi khi là cùng một người, nhưng không phải lúc nào cũng vậy. Nếu nhóm gộp chúng thành một khái niệm chỉ vì giao diện hiện tại dùng chung một trường tên, mô hình có thể không biểu diễn được các trường hợp như mua hộ hoặc giao quà.

Chuyên gia cần giải thích:

- Một thuật ngữ có nghĩa gì trong quy trình cụ thể.
- Những thuật ngữ nào đồng nghĩa và những thuật ngữ nào cần phân biệt.
- Một khái niệm bắt đầu tồn tại, thay đổi trạng thái và kết thúc khi nào.
- Những từ nào chỉ là cách gọi quen thuộc, còn những từ nào gắn với một quy tắc hoặc trách nhiệm cụ thể.

Những thuật ngữ đã thống nhất trở thành một phần của **ngôn ngữ chung (Ubiquitous Language)**. Ngôn ngữ này cần được sử dụng nhất quán trong trao đổi, tài liệu, ví dụ, tên lớp, phương thức, sự kiện và kiểm thử trong phạm vi bounded context tương ứng.

### 2.3. Làm rõ quy tắc và ngoại lệ

Quy trình mô tả những gì thường xảy ra; quy tắc nghiệp vụ xác định điều gì được phép, bắt buộc hoặc bị cấm. Chuyên gia giúp nhóm đi từ mô tả chung đến điều kiện cụ thể.

Thay vì chỉ nói “đơn hàng có thể được sửa”, hãy làm rõ:

- Ai được sửa đơn hàng?
- Có thể sửa những thông tin nào?
- Việc sửa có bị giới hạn bởi trạng thái hiện tại không?
- Giá và khuyến mại được tính lại vào thời điểm nào?
- Nếu một mặt hàng hết tồn kho trong lúc sửa thì xử lý ra sao?
- Có trường hợp ngoại lệ nào được người quản lý phê duyệt không?

Các trường hợp ngoại lệ thường bộc lộ bản chất của mô hình. Chúng cho thấy đâu là quy tắc cốt lõi, đâu là chính sách có thể thay đổi và đâu là thao tác vận hành chỉ xuất hiện trong một số tình huống.

### 2.4. Đưa ra ví dụ thực tế và phản ví dụ

Một phát biểu như “chỉ giao hàng khi đã thanh toán” có thể nghe rõ ràng nhưng vẫn che giấu nhiều trường hợp: thanh toán khi nhận hàng, thanh toán một phần, thanh toán qua hạn mức tín dụng hoặc đơn hàng được miễn phí. Chuyên gia nên cung cấp các tình huống cụ thể, bao gồm cả trường hợp bình thường và trường hợp không tuân theo quy trình phổ biến.

Phản ví dụ đặc biệt hữu ích. Khi nhóm đưa ra một mô hình hoặc quy tắc, chuyên gia có thể hỏi: “Nếu khách hàng trả lại một phần hàng thì sao?” hoặc “Nếu lệnh chuyển khoản đến sau khi đơn đã bị hủy thì sao?”. Câu trả lời giúp nhóm phát hiện giả định sai trước khi chúng trở thành mã nguồn.

### 2.5. Xác nhận mô hình có phản ánh đúng nghiệp vụ

Chuyên gia xem xét thuật ngữ, ví dụ, trạng thái và quy tắc mà nhóm đề xuất. Họ xác nhận mô hình có diễn đạt đúng cách tổ chức ra quyết định hay không, đồng thời chỉ ra những điểm thiếu hoặc sai.

Việc xác nhận không có nghĩa chuyên gia phải duyệt từng dòng mã. Họ cần tham gia ở những điểm có quyết định nghiệp vụ quan trọng, đặc biệt khi nhóm thay đổi cách hiểu về một khái niệm, chính sách hoặc ranh giới trách nhiệm.

Chuyên gia nghiệp vụ không cần tự thiết kế class, bảng dữ liệu hay kiến trúc kỹ thuật. Giá trị lớn nhất của họ là kiến thức thực tế, khả năng giải thích và quyền xác nhận ý nghĩa nghiệp vụ.

## 3. Vai trò của nhóm phát triển

Nhóm phát triển gồm những người cùng chịu trách nhiệm đưa phần mềm vào hoạt động. Tùy tổ chức, nhóm có thể có lập trình viên, kiến trúc sư, chuyên viên phân tích, người kiểm thử, product owner, nhà thiết kế trải nghiệm và các vai trò liên quan. Trong DDD, tất cả những người tham gia quyết định về mô hình cần hiểu ngôn ngữ và mục tiêu nghiệp vụ ở mức đủ để cộng tác.

### 3.1. Đặt câu hỏi để khám phá mô hình

Nhóm phát triển không chỉ ghi lại yêu cầu. Họ cần chủ động hỏi để làm rõ ý nghĩa, điều kiện, vòng đời, quyền hạn và ngoại lệ. Một câu hỏi kỹ thuật tốt có thể giúp chuyên gia nhận ra rằng hai bước tưởng như giống nhau thực ra có quy tắc khác nhau.

Ví dụ: “Khi nào hệ thống được xem là đã xác nhận đơn hàng: khi khách bấm nút đặt hàng, khi thanh toán được chấp nhận hay khi bộ phận bán hàng duyệt?”. Câu hỏi này làm lộ ra một quyết định quan trọng về thời điểm chuyển trạng thái và trách nhiệm của các bộ phận.

Nếu câu trả lời chưa rõ hoặc các chuyên gia bất đồng, nhóm cần ghi nhận điểm chưa thống nhất và tìm đúng người có thẩm quyền quyết định. Không nên tự biến một giả định kỹ thuật thành chính sách nghiệp vụ.

### 3.2. Chuyển kiến thức thành mô hình rõ ràng

Nhóm phát triển tổ chức kiến thức đã khám phá thành các khái niệm, hành vi, trạng thái, quy tắc và quan hệ. Họ dùng ngôn ngữ nghiệp vụ đã thống nhất để đặt tên cho các thành phần trong thiết kế và mã nguồn.

Ở mức chiến lược, nhóm phối hợp với chuyên gia để:

- Nhận diện các subdomain và hiểu phần nào tạo ra lợi thế cốt lõi, phần nào hỗ trợ hoặc có thể dùng giải pháp phổ thông.
- Xác định bounded context, nơi một mô hình và ngôn ngữ có ý nghĩa nhất quán.
- Làm rõ quan hệ giữa các context, cách chúng trao đổi thông tin và những phụ thuộc cần quản lý trong context map.

Ở mức chiến thuật, nhóm chọn cấu trúc phù hợp với quy tắc đã khám phá:

- **Entity** biểu diễn đối tượng cần được theo dõi bằng danh tính xuyên suốt vòng đời.
- **Value object** biểu diễn giá trị được xác định bởi các thuộc tính, thường có tính bất biến, chẳng hạn Tiền hoặc Khoảng thời gian.
- **Aggregate** gom các đối tượng quanh một ranh giới nhất quán và bảo vệ các bất biến nghiệp vụ; bên ngoài thường tương tác với aggregate thông qua aggregate root.
- **Repository** cung cấp cách truy xuất và lưu aggregate theo ngôn ngữ miền, che giấu chi tiết lưu trữ.
- **Domain event** biểu diễn một sự việc nghiệp vụ đã xảy ra và có ý nghĩa với các phần khác của mô hình hoặc hệ thống.

Những cấu trúc này không phải danh sách bắt buộc phải có trong mọi module. Nhóm chỉ sử dụng chúng khi chúng giúp diễn đạt và bảo vệ quy tắc của miền.

### 3.3. Phát hiện mâu thuẫn và giới hạn của mô hình

Khi chuyển lời giải thích thành quy tắc có thể thực thi, nhóm phát triển thường phát hiện những điểm chưa nhất quán: hai chính sách xung đột, một trạng thái không có đường chuyển tiếp, một thuật ngữ được dùng với hai ý nghĩa hoặc một quy trình phụ thuộc vào dữ liệu mà chưa có nguồn xác nhận.

Nhóm cần đưa các điểm đó trở lại cuộc trao đổi với chuyên gia. Kỹ năng kỹ thuật giúp nhóm nhìn thấy hệ quả của từng cách diễn giải, nhưng quyết định nghiệp vụ vẫn cần được xác nhận bởi người có hiểu biết và thẩm quyền phù hợp.

Nhóm cũng cần chỉ ra giới hạn của mô hình. Không phải mọi quy trình đều cần tự động hóa, không phải mọi khác biệt đều cần một entity riêng và không phải mọi sự kiện đều cần được phát tán ra toàn hệ thống. Mô hình cần đủ chính xác cho mục tiêu đã chọn mà vẫn có thể hiểu, kiểm thử và thay đổi.

### 3.4. Biến mô hình thành mã nguồn và kiểm thử

Trong DDD, mô hình cần dẫn dắt thiết kế phần mềm. Quy tắc quan trọng nên được đặt ở nơi có thể bảo vệ nó, thay vì phân tán trong nhiều controller, câu lệnh SQL hoặc giao diện.

Nhóm phát triển chuyển các ví dụ nghiệp vụ đã thống nhất thành kiểm thử. Các kiểm thử này giúp xác nhận phần mềm đang thực hiện đúng ngôn ngữ và quy tắc của mô hình. Khi chính sách thay đổi, nhóm cập nhật mô hình, mã nguồn và kiểm thử tương ứng.

Mã nguồn cũng là nơi kiểm tra chất lượng mô hình. Nếu một khái niệm nghiệp vụ không thể được đặt tên rõ ràng, nếu một aggregate có quá nhiều trách nhiệm hoặc nếu nhiều context phải hiểu chi tiết nội bộ của nhau, nhóm nên xem lại mô hình và ranh giới đã chọn.

### 3.5. Giữ cho mô hình và hệ thống không lệch nhau

Sau khi phần mềm được đưa vào sử dụng, nhóm tiếp tục thu thập phản hồi từ người vận hành, theo dõi các trường hợp ngoại lệ và xem xét tác động của thay đổi chính sách. Mô hình phải phát triển cùng nghiệp vụ. Nếu tài liệu nói một điều, mã nguồn làm một điều khác và người dùng hiểu theo một cách thứ ba, ngôn ngữ chung đã bị đứt gãy.

## 4. Trách nhiệm chung của hai bên

Chuyên gia nghiệp vụ và nhóm phát triển có chuyên môn khác nhau, nhưng cùng chịu trách nhiệm về chất lượng mô hình. Bảng dưới đây mô tả cách hai bên đóng góp trong các hoạt động chính.

| Hoạt động | Chuyên gia nghiệp vụ đóng góp | Nhóm phát triển đóng góp | Kết quả cùng tạo ra |
| --- | --- | --- | --- |
| Xác định vấn đề | Mục tiêu, khó khăn, tác động và mức độ ưu tiên | Phạm vi phần mềm, khả năng kỹ thuật và câu hỏi cần khám phá | Mục tiêu mô hình rõ ràng |
| Khám phá quy trình | Vai trò, công việc, chính sách, ngoại lệ | Cách ghi nhận luồng, trạng thái, quyết định và dữ liệu liên quan | Bức tranh nghiệp vụ có thể thảo luận |
| Thống nhất thuật ngữ | Ý nghĩa và cách dùng trong thực tế | Phát hiện mơ hồ, đề xuất tên nhất quán trong thiết kế và mã | Ubiquitous Language |
| Xác định ranh giới | Khác biệt về trách nhiệm, quy trình và cách ra quyết định | Phân tích subdomain, bounded context và phụ thuộc giữa context | Ranh giới mô hình và context map |
| Mô hình hóa quy tắc | Xác nhận chính sách, điều kiện và ngoại lệ | Biểu diễn hành vi, bất biến và cấu trúc phù hợp | Domain model có thể kiểm chứng |
| Kiểm tra giải pháp | Đánh giá tính đúng đắn và khả năng áp dụng | Kiểm thử, đánh giá khả năng bảo trì và tích hợp | Phần mềm phù hợp với nghiệp vụ |
| Tiến hóa mô hình | Thông báo thay đổi và giải thích lý do | Đánh giá tác động, cập nhật mô hình, mã và kiểm thử | Mô hình tiếp tục phản ánh thực tế |

Không nên hiểu bảng này như một quy trình bàn giao tuần tự. Hai bên cần trao đổi trong suốt quá trình, đặc biệt khi một quyết định kỹ thuật làm lộ ra câu hỏi nghiệp vụ mới.

## 5. Cách cộng tác để xây dựng mô hình

Một vòng cộng tác có thể bắt đầu từ một vấn đề cụ thể và lặp lại khi nhóm học thêm về miền nghiệp vụ.

### Bước 1: Chọn phạm vi và kết quả cần đạt

Nhóm cùng chuyên gia xác định một năng lực nghiệp vụ, quy trình hoặc vấn đề cần cải thiện. Phạm vi đủ nhỏ để có thể khám phá sâu nhưng đủ quan trọng để tạo ra giá trị. Nhóm cần biết ai sử dụng kết quả, quyết định nào cần được hỗ trợ và tiêu chí nào cho thấy giải pháp có ích.

Đây cũng là lúc tránh mô hình hóa toàn bộ tổ chức trong một lần. Một sản phẩm lớn có thể chứa nhiều subdomain và bounded context với nhu cầu khác nhau.

### Bước 2: Khám phá bằng câu chuyện và tình huống thực tế

Thay vì chỉ hỏi “quy trình chuẩn là gì?”, hãy yêu cầu chuyên gia kể lại một trường hợp vừa xảy ra, từ lúc bắt đầu đến khi có kết quả. Nhóm hỏi thêm ai thực hiện từng bước, thông tin nào được dùng, điều kiện nào làm thay đổi hướng xử lý và điều gì xảy ra khi có lỗi.

Một số kỹ thuật hữu ích:

- **Domain Storytelling**: kể lại quy trình qua các tác nhân, hành động và đối tượng nghiệp vụ để cả nhóm nhìn thấy cách công việc diễn ra.
- **EventStorming**: cùng khám phá các domain event, quyết định, lệnh và chính sách để làm rõ dòng chảy nghiệp vụ và những điểm cần thảo luận.
- **Example Mapping**: tách một quy tắc thành các ví dụ cụ thể và câu hỏi chưa được giải đáp, giúp xác định điều kiện chấp nhận rõ ràng.
- **Phỏng vấn và quan sát công việc**: kiểm tra sự khác nhau giữa quy trình được mô tả và cách nhân viên thực sự xử lý tình huống.

Các kỹ thuật này hỗ trợ đối thoại; chúng không thay thế kiến thức và quyết định của chuyên gia.

### Bước 3: Thống nhất ngôn ngữ và quy tắc

Nhóm ghi lại các thuật ngữ quan trọng, định nghĩa, ví dụ và những từ dễ gây nhầm lẫn. Mỗi thuật ngữ nên được hiểu trong một ngữ cảnh rõ ràng. Nếu hai bộ phận dùng cùng một từ với ý nghĩa khác nhau, hãy ghi nhận sự khác biệt thay vì ép họ dùng một định nghĩa chung.

Với từng quy tắc, nhóm nên làm rõ điều kiện, hành động, kết quả và trường hợp ngoại lệ. Những câu hỏi chưa có câu trả lời cần được giữ lại như vấn đề cần xác minh, có người phụ trách và thời điểm xem xét.

### Bước 4: Xác định subdomain và bounded context

Chuyên gia giúp nhận diện các lĩnh vực công việc và sự khác biệt trong cách vận hành. Nhóm phát triển cùng phân tích mức độ phức tạp, trách nhiệm và nhu cầu tích hợp để đề xuất ranh giới mô hình.

Subdomain là cách phân chia miền nghiệp vụ thành các phần có mục đích và năng lực riêng. Bounded context là ranh giới mà bên trong đó một mô hình và ngôn ngữ có ý nghĩa nhất quán. Hai khái niệm liên quan nhưng không đồng nhất: một subdomain có thể được triển khai bởi một hoặc nhiều bounded context, tùy phạm vi và cách tổ chức hệ thống.

Khi các context cần trao đổi, context map mô tả mối quan hệ và cách phối hợp giữa chúng. Nhóm cần làm rõ dữ liệu nào được chia sẻ, context nào sở hữu quy tắc nào và thay đổi ở một bên ảnh hưởng đến bên kia ra sao.

### Bước 5: Thể hiện quy tắc bằng mô hình chiến thuật

Trong từng bounded context, nhóm xác định các khái niệm có danh tính, các giá trị, ranh giới nhất quán và những sự kiện nghiệp vụ quan trọng. Ví dụ, nếu một đơn hàng có quy tắc chuyển trạng thái và chính sách hủy, nhóm có thể xem xét đặt các hành vi bảo vệ quy tắc đó trong aggregate `Order`.

Chuyên gia kiểm tra xem hành vi được mô hình hóa có đúng chính sách hay không. Nhóm phát triển kiểm tra xem cấu trúc đó có bảo vệ được bất biến, có thể kiểm thử và không tạo phụ thuộc không cần thiết hay không.

### Bước 6: Kiểm chứng bằng ví dụ và phản ví dụ

Với mỗi quy tắc quan trọng, hãy cùng đi qua ít nhất một trường hợp hợp lệ, một trường hợp không hợp lệ và một trường hợp biên. Chuyển các tình huống đã thống nhất thành kiểm thử để mô hình có thể được xác nhận lặp lại.

Nếu ví dụ không thể được giải thích bằng ngôn ngữ hiện tại, hoặc hai người hiểu cùng một quy tắc theo hai cách khác nhau, hãy quay lại làm rõ thuật ngữ và chính sách trước khi mở rộng triển khai.

### Bước 7: Đưa ngôn ngữ vào mã và tiếp tục học

Tên lớp, phương thức, sự kiện, API và kiểm thử nên phản ánh ngôn ngữ đã thống nhất trong context. Tài liệu thuật ngữ cần được cập nhật khi mô hình thay đổi. Nhóm tiếp tục trao đổi với chuyên gia trong quá trình phát triển và vận hành, thay vì coi buổi khám phá ban đầu là nguồn thông tin duy nhất.

## 6. Ví dụ: mô hình hóa việc hủy đơn hàng

Giả sử một hệ thống bán hàng trực tuyến cần hỗ trợ khách hàng hủy đơn. Ban đầu, yêu cầu chỉ có một câu: “Khách hàng được hủy đơn hàng”. Nếu nhóm lập tức tạo một nút Hủy và một phương thức `cancel()`, nhiều quy tắc quan trọng có thể bị bỏ sót.

Trong buổi trao đổi, chuyên gia nghiệp vụ giải thích các tình huống:

1. Đơn hàng mới được tạo nhưng chưa thanh toán có thể được hủy ngay.
2. Đơn đã thanh toán nhưng kho chưa bắt đầu chuẩn bị hàng cần được kiểm tra khả năng hoàn tiền.
3. Đơn đã đóng gói có thể cần nhân viên kho xác nhận trước khi hủy.
4. Đơn đã bàn giao cho đơn vị vận chuyển không còn được xử lý như đơn chưa giao; có thể phải tạo yêu cầu hoàn hàng.
5. Khách hàng chỉ có thể tự hủy trong một khoảng thời gian; sau đó nhân viên có quyền xử lý theo chính sách khác.

Nhóm phát triển hỏi tiếp: “Trạng thái nào xác định kho đã bắt đầu chuẩn bị?”, “Ai có quyền xác nhận hủy?”, “Việc hoàn tiền là một phần của thao tác hủy hay là quy trình riêng?” và “Nếu yêu cầu hủy đến cùng lúc với xác nhận giao hàng thì quy tắc nào được ưu tiên?”. Những câu hỏi này giúp chuyên gia nói rõ chính sách và trách nhiệm của từng bộ phận.

Từ cuộc trao đổi, nhóm có thể đi đến một số quyết định mô hình:

- Trong bounded context bán hàng, `Order` có danh tính và vòng đời riêng; hành vi `cancel` chỉ thành công khi thỏa điều kiện của chính sách bán hàng.
- Các giá trị như `Money` hoặc địa chỉ giao hàng có thể được biểu diễn bằng value object nếu mô hình cần bảo vệ quy tắc và tính nhất quán của chúng.
- Aggregate `Order` có thể bảo vệ các bất biến liên quan đến trạng thái và các dòng hàng của đơn. Những thao tác cần phối hợp với kho hoặc thanh toán có thể được điều phối qua quy trình phù hợp thay vì nhồi toàn bộ trách nhiệm vào một aggregate.
- Khi đơn được hủy thành công, hệ thống có thể phát sinh domain event `OrderCancelled`. Context thanh toán hoặc kho tiếp nhận thông tin đó theo hợp đồng tích hợp đã thống nhất.
- Trong context kho, đối tượng phục vụ việc lấy hàng và giao hàng có thể có tên, trạng thái và quy tắc riêng. Nó không nhất thiết phải là cùng một entity `Order` của context bán hàng.

Đây chỉ là một mô hình minh họa. Quyết định cuối cùng phải dựa trên chính sách thật của tổ chức, cách các bộ phận vận hành và ranh giới trách nhiệm đã được xác nhận. Giá trị của ví dụ nằm ở cách hai bên cùng khám phá câu hỏi, kiểm tra trường hợp biên và thống nhất mô hình.

## 7. Những cách làm dễ khiến mô hình thất bại

| Cách làm | Hệ quả | Cách cải thiện |
| --- | --- | --- |
| Chuyên gia chỉ tham gia ở giai đoạn lấy yêu cầu | Nhóm phải tự suy đoán khi gặp ngoại lệ hoặc thay đổi chính sách | Duy trì trao đổi với chuyên gia trong lúc thiết kế, triển khai và kiểm chứng |
| Nhóm phát triển chỉ ghi chép mà không đặt câu hỏi | Các giả định mơ hồ đi vào thiết kế và mã nguồn | Hỏi về điều kiện, lý do, trạng thái, quyền hạn và phản ví dụ |
| Chuyên gia chỉ định cấu trúc kỹ thuật | Mô hình có thể bị giới hạn bởi cách triển khai hiện tại | Để chuyên gia giải thích nhu cầu và quy tắc; nhóm cùng tìm cấu trúc kỹ thuật phù hợp |
| Nhóm áp đặt mô hình kỹ thuật lên nghiệp vụ | Thuật ngữ và hành vi trong mã không còn phản ánh cách tổ chức làm việc | Bắt đầu từ ngôn ngữ và quy tắc miền, sau đó mới chọn cấu trúc triển khai |
| Dùng một mô hình chung cho mọi bộ phận | Một thuật ngữ mang nhiều nghĩa, các quy tắc không liên quan bị trộn lẫn | Xác định bounded context và ghi rõ cách các context trao đổi |
| Chỉ mô hình hóa luồng thành công | Các trường hợp lỗi, hủy, hoàn tiền và ngoại lệ không được bảo vệ | Dùng phản ví dụ và tình huống biên để kiểm tra mô hình |
| Tài liệu, kiểm thử và mã nguồn dùng thuật ngữ khác nhau | Mô hình bị phân mảnh, khó trao đổi và bảo trì | Dùng Ubiquitous Language nhất quán trong từng context |
| Coi mô hình là tài liệu hoàn tất một lần | Phần mềm dần lệch khỏi nghiệp vụ thực tế | Xem mô hình là công cụ sống, cập nhật khi tổ chức học thêm hoặc thay đổi |

Một dấu hiệu đáng chú ý là nhóm thường xuyên phải giải thích cùng một thuật ngữ theo nhiều cách. Đó có thể là dấu hiệu của một bounded context chưa rõ, một từ đang bị dùng quá rộng hoặc một quyết định nghiệp vụ chưa được thống nhất.

## 8. Nguyên tắc duy trì sự cộng tác

Để mô hình tiếp tục có giá trị, nhóm nên duy trì một số nguyên tắc trong công việc hằng ngày:

- **Có người chịu trách nhiệm giải thích nghiệp vụ.** Nhóm biết cần trao đổi với ai khi có câu hỏi, và biết ai có thẩm quyền xác nhận một chính sách.
- **Trao đổi bằng tình huống cụ thể.** Ví dụ thực tế giúp phát hiện khác biệt trong cách hiểu nhanh hơn những phát biểu chung chung.
- **Ghi nhận quyết định và điểm chưa rõ.** Lưu lại định nghĩa, ví dụ, lý do của quyết định và người cần xác minh để tránh lặp lại tranh luận.
- **Giữ thuật ngữ nhất quán trong từng bounded context.** Nếu một từ có nghĩa khác ở context khác, hãy thể hiện rõ ranh giới và cách dịch giữa hai mô hình.
- **Kiểm chứng mô hình bằng hành vi.** Quy tắc quan trọng cần có ví dụ và kiểm thử tương ứng; sơ đồ chỉ có giá trị khi giải thích được cách hệ thống phải hoạt động.
- **Cập nhật mô hình khi nghiệp vụ thay đổi.** Khi chính sách, vai trò hoặc quy trình đổi khác, nhóm đánh giá tác động đến ngôn ngữ, ranh giới context, mã nguồn và hợp đồng tích hợp.
- **Tôn trọng chuyên môn của nhau.** Chuyên gia chịu trách nhiệm về ý nghĩa nghiệp vụ; nhóm phát triển chịu trách nhiệm về cách thể hiện và vận hành mô hình trong phần mềm. Các quyết định giao nhau cần được thảo luận cùng nhau.

DDD không yêu cầu chuyên gia nghiệp vụ phải trở thành lập trình viên, cũng không yêu cầu lập trình viên phải tự biết mọi chi tiết của ngành. DDD yêu cầu hai bên cùng xây dựng sự hiểu biết đủ sâu để đưa ra quyết định tốt. Chuyên gia giúp mô hình bám sát thực tế; nhóm phát triển giúp mô hình trở thành phần mềm có cấu trúc và có thể thay đổi. Khi đối thoại được duy trì, ngôn ngữ chung đi vào thiết kế, mã nguồn và kiểm thử, mô hình trở thành công cụ phối hợp giữa nghiệp vụ và kỹ thuật.

## 9. Câu hỏi tự kiểm tra

1. Vì sao domain model không nên được xem đơn thuần là sơ đồ lớp hoặc cấu trúc bảng dữ liệu?
2. Chuyên gia nghiệp vụ cần cung cấp những loại thông tin nào để nhóm phát triển hiểu đúng một quy tắc?
3. Vì sao nhóm phát triển cần hỏi về ngoại lệ và phản ví dụ thay vì chỉ ghi lại quy trình phổ biến?
4. Ubiquitous Language giúp cải thiện trao đổi và mã nguồn như thế nào? Vì sao ngôn ngữ này cần được hiểu trong phạm vi bounded context?
5. Phân biệt vai trò của subdomain và bounded context khi xác định phạm vi mô hình.
6. Hãy giải thích cách entity, value object, aggregate, repository và domain event có thể giúp biểu diễn quy tắc đã được hai bên thống nhất.
7. Khi chuyên gia nghiệp vụ và nhóm phát triển hiểu khác nhau về một chính sách, nhóm nên làm gì trước khi triển khai?
8. Hãy chọn một quy trình quen thuộc, nêu một quy tắc chính và ba tình huống biên mà chuyên gia cùng nhóm phát triển cần làm rõ để xây dựng mô hình.
