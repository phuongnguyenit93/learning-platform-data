# Bài toán và mục tiêu

## 1. Vì sao cần xác định bài toán trước khi xây dựng DSL?

Trong khoa học máy tính, nhiều công việc lặp lại có một tập khái niệm, quy tắc và thao tác tương đối ổn định. Ví dụ, truy vấn dữ liệu quan hệ thường xoay quanh bảng, cột, phép lọc và phép kết hợp; biểu thức chính quy mô tả mẫu ký tự; công cụ build mô tả các tác vụ, phụ thuộc và đầu ra; hệ thống điều phối mô tả tài nguyên, dịch vụ và trạng thái triển khai.

Ta có thể thực hiện những công việc đó bằng một ngôn ngữ lập trình đa dụng như Java, Python hoặc C. Tuy nhiên, cách biểu đạt bằng ngôn ngữ đa dụng đôi khi buộc người viết phải trình bày nhiều chi tiết kỹ thuật không trực tiếp phản ánh ý định của bài toán. Quy tắc của miền có thể bị phân tán giữa mã nguồn, cấu hình, lời gọi API và tài liệu. Người đọc phải hiểu cả cơ chế triển khai lẫn khái niệm nghiệp vụ kỹ thuật mới có thể kiểm tra một khai báo có đúng hay không.

**Ngôn ngữ miền chuyên biệt (Domain-Specific Language — DSL)** được thiết kế để diễn đạt một nhóm bài toán trong một miền xác định bằng những khái niệm và cấu trúc phù hợp với miền đó. DSL hướng người viết tập trung vào điều cần mô tả, đồng thời cung cấp các quy tắc để hệ thống có thể kiểm tra và xử lý mô tả ấy.

Trước khi thiết kế cú pháp hoặc viết bộ phân tích, cần trả lời rõ ba câu hỏi:

- Vấn đề cụ thể nào đang khó diễn đạt, khó kiểm tra hoặc khó tự động hóa?
- Ai sẽ viết, đọc, bảo trì và thực thi mô tả?
- DSL cần đạt kết quả gì, và giới hạn của nó nằm ở đâu?

Nếu chưa xác định được những điều này, DSL dễ trở thành một lớp cú pháp mới nhưng không giải quyết được khó khăn thực tế. Một ngôn ngữ có nhiều từ khóa hoặc cú pháp đẹp chưa chắc hữu ích nếu người dùng vẫn phải viết cùng lượng mã, vẫn mắc cùng loại lỗi hoặc phải học thêm một mô hình phức tạp.

## 2. Bài toán mà DSL thường giải quyết

Một bài toán phù hợp với DSL thường có một số đặc điểm sau:

1. **Miền vấn đề có ranh giới nhận biết được.** Có thể xác định các đối tượng, thuộc tính, thao tác và quy tắc thường xuyên xuất hiện. Chẳng hạn, miền truy vấn dữ liệu có bảng, trường, điều kiện và phép kết hợp.
2. **Công việc lặp lại hoặc có cấu trúc ổn định.** Nhiều người phải mô tả các trường hợp khác nhau nhưng vẫn dùng chung một bộ khái niệm và quy tắc.
3. **Cách biểu đạt hiện tại có chi phí đáng kể.** Mã đa dụng hoặc cấu hình tổng quát có thể chứa nhiều phần lặp, khó đọc, khó rà soát hoặc dễ tạo ra tổ hợp không hợp lệ.
4. **Có thể mô hình hóa ý định bằng một tập biểu thức giới hạn.** Các yêu cầu quan trọng có thể được biểu diễn bằng cú pháp và ngữ nghĩa rõ ràng, thay vì phải hỗ trợ mọi khả năng của một ngôn ngữ đa dụng.
5. **Có lợi ích khi kiểm tra hoặc tự động xử lý mô tả.** Hệ thống có thể phân tích cú pháp, kiểm tra kiểu và ràng buộc, lập kế hoạch thực thi, sinh mã hoặc chuyển mô tả thành hành động.

Các đặc điểm này là dấu hiệu để đánh giá, không phải điều kiện bắt buộc phải có đủ trong mọi trường hợp. Một tác vụ chỉ xuất hiện một lần, không có quy tắc ổn định hoặc thay đổi liên tục có thể chưa đáng để tạo DSL riêng.

### 2.1. Những khó khăn thường gặp khi không có DSL phù hợp

**Khoảng cách giữa ý định và mã thực thi.** Người dùng muốn mô tả “lấy các đơn hàng đã thanh toán, nhóm theo khách hàng và tính tổng tiền”, nhưng phải viết nhiều câu lệnh xử lý dữ liệu, cấu hình luồng và chi tiết thư viện. Người đọc cần suy luận ngược từ mã để hiểu ý định ban đầu.

**Quy tắc miền bị phân tán.** Một số quy tắc nằm trong mã ứng dụng, một số nằm trong cấu hình, một số khác chỉ được ghi trong tài liệu. Hai nhóm phát triển có thể diễn giải cùng một khái niệm theo những cách khác nhau.

**Lỗi chỉ xuất hiện khi chạy.** Cấu hình có thể chứa tên thuộc tính sai, thiếu tham số hoặc kết hợp các thao tác không tương thích. Nếu không có mô hình và bước kiểm tra riêng, lỗi có thể chỉ được phát hiện khi tác vụ bắt đầu thực thi.

**Khó giới hạn những gì người dùng được phép làm.** Một API hoặc ngôn ngữ đa dụng thường cho phép nhiều thao tác hơn mức cần thiết. Trong một miền có yêu cầu an toàn, khả năng kiểm soát hoặc tính dự đoán, tập biểu thức giới hạn có thể là lợi thế.

**Khó trao đổi giữa người tạo và người vận hành.** Một mô tả quá thiên về chi tiết triển khai khiến người chịu trách nhiệm về miền khó rà soát, phê duyệt hoặc tìm nguyên nhân khi có sự cố.

DSL có thể giảm các khó khăn trên bằng cách đưa khái niệm miền vào một mô hình thống nhất. Tuy nhiên, DSL chỉ có tác dụng khi mô hình, quy tắc và công cụ hỗ trợ phản ánh đúng công việc thực tế.

## 3. Ví dụ về bài toán trong các miền khoa học máy tính

| Miền | Nội dung cần mô tả | DSL hoặc ngôn ngữ chuyên biệt quen thuộc | Giá trị chính |
|---|---|---|---|
| Truy vấn cơ sở dữ liệu quan hệ | Chọn dữ liệu, lọc, kết hợp, nhóm và tổng hợp | SQL | Diễn đạt thao tác dữ liệu bằng các cấu trúc gần với mô hình quan hệ |
| Tìm kiếm mẫu văn bản | Mẫu ký tự, nhóm, lựa chọn và số lần lặp | Regular expressions | Mô tả mẫu ngắn gọn để tìm kiếm hoặc kiểm tra chuỗi |
| Tự động hóa build | Tác vụ, phụ thuộc, đầu vào và đầu ra | DSL của Gradle hoặc các công cụ build | Khai báo quy trình build có cấu trúc và có thể tự động thực thi |
| Mô tả giao diện | Thành phần, thuộc tính và quan hệ bố cục | HTML và CSS | Khai báo cấu trúc và cách trình bày giao diện |
| Điều phối hệ thống | Tài nguyên, dịch vụ, cấu hình và trạng thái mong muốn | Kubernetes manifests | Khai báo trạng thái hệ thống để bộ điều khiển đối chiếu và duy trì |

Các ví dụ trên có hình thức và cách thực thi khác nhau. Có DSL được nhúng trong một ngôn ngữ chủ, có DSL dùng cú pháp độc lập, có ngôn ngữ được khai báo trong tệp cấu hình và có ngôn ngữ được xử lý bởi một công cụ chuyên dụng. Điểm chung là chúng tập trung vào một miền với bộ khái niệm và quy tắc có chủ đích.

### 3.1. Ví dụ minh họa: mô tả một luồng xử lý dữ liệu

Giả sử một nhóm thường xuyên tạo báo cáo doanh thu. Yêu cầu điển hình là đọc dữ liệu đơn hàng, chỉ giữ đơn đã thanh toán, nhóm theo khách hàng, tính tổng tiền và ghi kết quả ra tệp. Nếu dùng một DSL giả định, mô tả có thể trông như sau:

```text
pipeline "customer-revenue" {
    source "orders.csv"
    filter status == "PAID"
    group_by customer_id
    aggregate total = sum(amount)
    output "customer-revenue.csv"
}
```

Đoạn trên không phải cú pháp của một công cụ có sẵn; đây là ví dụ để làm rõ cách tư duy về DSL. Người viết mô tả các bước theo thuật ngữ của miền xử lý dữ liệu. Một công cụ có thể phân tích mô tả thành cấu trúc trung gian, kiểm tra rằng `status`, `customer_id` và `amount` tồn tại trong nguồn dữ liệu, xác nhận phép `sum` áp dụng được cho kiểu dữ liệu tương ứng, rồi tạo và thực thi kế hoạch xử lý.

Nếu viết bằng một ngôn ngữ đa dụng, người lập trình có thể phải tự khởi tạo bộ đọc tệp, lọc bản ghi, tạo cấu trúc nhóm, cập nhật tổng và ghi tệp. Cách viết đó linh hoạt hơn, nhưng có thể làm lu mờ ý định của quy trình khi đây là một thao tác phổ biến và có quy tắc ổn định.

Ví dụ cũng cho thấy DSL phải định nghĩa ngữ nghĩa chính xác. `filter` xử lý giá trị rỗng ra sao? `sum` có chấp nhận số thập phân không? Dữ liệu đầu ra được sắp xếp theo thứ tự nào? Nếu không quy định những điều này, cùng một đoạn DSL có thể tạo ra kết quả khác nhau giữa các phiên bản hoặc môi trường.

## 4. Mục tiêu của một DSL

Mục tiêu tổng quát là giúp người dùng mô tả đúng ý định trong một miền bằng cách diễn đạt dễ hiểu, có quy tắc và có thể xử lý tự động. Tùy bài toán, mục tiêu cụ thể có thể gồm:

### 4.1. Diễn đạt khái niệm miền một cách trực tiếp

DSL nên cung cấp tên gọi và cấu trúc phản ánh những đối tượng, thuộc tính, quan hệ và thao tác mà người làm việc trong miền thường sử dụng. Khi đọc một biểu thức, người đọc có thể nhận ra nó đang mô tả điều gì mà không cần lần theo quá nhiều lớp gọi hàm hoặc chi tiết hạ tầng.

Mục tiêu này không đồng nghĩa với việc biến mọi thuật ngữ miền thành từ khóa. Một thiết kế tốt chọn những khái niệm có ý nghĩa ổn định, phân biệt rõ các khái niệm dễ nhầm lẫn và tránh đưa chi tiết nội bộ của một thư viện vào ngôn ngữ nếu người dùng không cần biết.

### 4.2. Giảm độ phức tạp khi thực hiện công việc lặp lại

DSL có thể gom các mẫu xử lý thường gặp thành cấu trúc tái sử dụng, giảm mã lặp và giảm số quyết định kỹ thuật mà người dùng phải tự đưa ra. Người viết tập trung vào dữ liệu, quy tắc hoặc kết quả mong muốn; công cụ phụ trách các bước triển khai đã được chuẩn hóa.

Hiệu quả cần được đánh giá bằng công việc thực tế: số bước cần viết, thời gian hoàn thành, khả năng đọc lại và chi phí bảo trì. Một cú pháp ngắn hơn nhưng khó hiểu hoặc đòi hỏi nhiều kiến thức ẩn không phải là cải thiện.

### 4.3. Làm rõ và kiểm tra các quy tắc của miền

DSL cần thể hiện những điều kiện khiến một mô tả hợp lệ. Tùy miền, đó có thể là kiểu dữ liệu, phạm vi giá trị, quan hệ giữa các thành phần, thứ tự thao tác hoặc điều kiện phụ thuộc.

Ví dụ, một bước tổng hợp chỉ được tham chiếu đến trường có trong dữ liệu đầu vào; một tác vụ build phải khai báo phụ thuộc hợp lệ; một cấu hình tài nguyên phải tuân theo kiểu và giới hạn đã quy định. Nếu công cụ phát hiện lỗi trước khi thực thi, người dùng có thể sửa vấn đề sớm và nhận thông báo gắn với khái niệm miền.

### 4.4. Tạo điều kiện tự động hóa và thực thi nhất quán

Khi mô tả tuân theo cấu trúc và ngữ nghĩa đã định nghĩa, công cụ có thể xử lý nó theo một quy trình ổn định: phân tích cú pháp, xây dựng mô hình, kiểm tra, lập kế hoạch và thực thi hoặc sinh mã. Điều này giúp giảm khác biệt do mỗi người tự cài đặt cùng một quy tắc theo cách riêng.

Tùy mục tiêu, kết quả xử lý có thể là truy vấn, mã nguồn, cấu hình, đồ thị tác vụ, kế hoạch thực thi hoặc hành động trên một hệ thống. DSL không bắt buộc phải có trình biên dịch riêng; một bộ thông dịch, thư viện nhúng hoặc công cụ chuyển đổi cũng có thể xử lý DSL.

### 4.5. Giới hạn khả năng biểu đạt để tăng khả năng kiểm soát

Một DSL thường chỉ hỗ trợ những thao tác cần thiết cho miền. Phạm vi giới hạn có thể giúp kiểm soát quyền, ngăn các biểu thức không phù hợp, dự đoán hành vi và đơn giản hóa việc kiểm tra. Đây là mục tiêu quan trọng trong các công cụ cấu hình hạ tầng, truy vấn, kiểm thử hoặc tự động hóa.

Giới hạn phải được chọn theo nhu cầu thật. Nếu DSL quá chặt, người dùng sẽ liên tục phải thoát ra ngôn ngữ chủ hoặc viết phần mở rộng phức tạp. Nếu DSL quá rộng, nó có thể mất đi lợi ích về tính rõ ràng và khả năng kiểm soát.

### 4.6. Hỗ trợ bảo trì và phát triển lâu dài

Một DSL được thiết kế tốt cần có quy tắc nhất quán, thông báo lỗi hữu ích, khả năng kiểm tra tự động và cách quản lý thay đổi phiên bản. Người khác có thể đọc lại mô tả, hiểu tác dụng của nó và dự đoán ảnh hưởng khi cấu trúc hoặc quy tắc miền thay đổi.

Mục tiêu bảo trì cũng bao gồm khả năng tích hợp với hệ thống hiện có, khả năng quan sát khi thực thi và cách xử lý các mô tả cũ khi DSL tiến hóa. Cú pháp dễ viết chỉ là một phần của trải nghiệm sử dụng.

## 5. Xác định phạm vi: DSL sẽ giải quyết đến đâu?

Phạm vi miền là ranh giới của những khái niệm và công việc mà DSL cam kết hỗ trợ. Cần mô tả phạm vi này đủ rõ để tránh hai thái cực: ngôn ngữ quá nhỏ không giải quyết được công việc chính, hoặc ngôn ngữ quá rộng trở thành một ngôn ngữ đa dụng khó kiểm soát.

Khi xác định phạm vi, hãy làm rõ:

- **Đối tượng sử dụng:** lập trình viên, kỹ sư vận hành, chuyên gia dữ liệu, người kiểm thử hay người dùng có kiến thức kỹ thuật khác.
- **Công việc được hỗ trợ:** những tác vụ nào là trọng tâm và tần suất xuất hiện của chúng.
- **Khái niệm cốt lõi:** thực thể, thuộc tính, quan hệ, thao tác và trạng thái của miền.
- **Đầu vào và đầu ra:** dữ liệu hoặc tài nguyên mà mô tả tham chiếu, cùng kết quả mà công cụ phải tạo ra.
- **Ràng buộc:** điều kiện hợp lệ, giới hạn bảo mật, hiệu năng, môi trường và quyền thực thi.
- **Phần nằm ngoài phạm vi:** các trường hợp hiếm gặp hoặc quá tổng quát nên được xử lý bằng ngôn ngữ chủ, API hoặc công cụ khác.

Ví dụ, DSL báo cáo có thể hỗ trợ đọc nguồn dữ liệu, lọc, nhóm, tổng hợp và xuất kết quả. Nó có thể không hỗ trợ viết thuật toán tùy ý, quản lý giao dịch hoặc điều khiển giao diện người dùng. Nêu rõ giới hạn giúp người dùng biết khi nào nên sử dụng DSL và khi nào nên chuyển sang công cụ khác.

## 6. Phân biệt mục tiêu với giải pháp triển khai

Khi mới bắt đầu, rất dễ đồng nhất bài toán với một lựa chọn kỹ thuật, chẳng hạn “cần viết parser”, “cần dùng ANTLR”, “cần tạo cú pháp giống JSON” hoặc “cần nhúng DSL vào Java”. Đây là các quyết định triển khai. Chúng chỉ nên được đưa ra sau khi đã hiểu vấn đề và mục tiêu.

| Câu hỏi về bài toán và mục tiêu | Câu hỏi về giải pháp triển khai |
|---|---|
| Người dùng đang cần mô tả công việc nào? | Cú pháp sẽ dùng dấu ngoặc, từ khóa hay lời gọi hàm? |
| Khái niệm nào thuộc miền và cần được biểu đạt? | Dùng parser tự viết hay công cụ sinh parser? |
| Những mô tả nào hợp lệ hoặc không hợp lệ? | Kiểm tra bằng type checker, validator hay bước biên dịch? |
| Kết quả cần tạo ra là gì? | Diễn giải trực tiếp, sinh mã hay chuyển thành mô hình trung gian? |
| Thành công được đo bằng tiêu chí nào? | Chọn thư viện, runtime và cấu trúc dự án nào? |

Nhiều lựa chọn triển khai có thể cùng đáp ứng một mục tiêu. Chẳng hạn, DSL có thể là **DSL bên ngoài (external DSL)** với cú pháp và bộ phân tích riêng, hoặc **DSL nhúng (internal/embedded DSL)** sử dụng cú pháp của một ngôn ngữ chủ. Lựa chọn phụ thuộc vào người dùng, độ phức tạp cú pháp, công cụ cần tích hợp, khả năng kiểm tra và chi phí bảo trì.

## 7. Tiêu chí đánh giá mức độ đạt mục tiêu

Mục tiêu cần được chuyển thành tiêu chí có thể quan sát hoặc đo lường. Không phải dự án nào cũng cần tất cả tiêu chí dưới đây; hãy chọn những tiêu chí gắn trực tiếp với bài toán.

| Nhóm tiêu chí | Câu hỏi đánh giá | Dấu hiệu đạt yêu cầu |
|---|---|---|
| Tính phù hợp miền | DSL có dùng đúng khái niệm và quy tắc của miền không? | Người có kiến thức miền hiểu được mô tả và nhận ra các thao tác quen thuộc |
| Khả năng diễn đạt | Các trường hợp sử dụng trọng tâm có thể mô tả đầy đủ không? | Người dùng không phải thường xuyên viết mã vòng quanh hoặc né tránh DSL |
| Tính dễ đọc | Người khác có hiểu ý định khi xem mô tả không? | Tên gọi, cấu trúc và thứ tự biểu thức nhất quán |
| Tính đúng đắn | Mô tả không hợp lệ có được phát hiện không? | Lỗi cú pháp và lỗi quy tắc miền được báo rõ trước khi thực thi khi có thể |
| Hiệu quả | DSL có giảm công sức so với cách hiện tại không? | Thời gian, lượng mã lặp hoặc chi phí bảo trì giảm trong các tình huống đại diện |
| Khả năng kiểm soát | Có thể giới hạn hành vi và quyền thực thi không? | Chỉ những thao tác được cho phép mới được chấp nhận và thực thi |
| Khả năng bảo trì | Ngôn ngữ có thể tiến hóa mà không gây thay đổi bất ngờ không? | Có quy tắc phiên bản, kiểm thử và hướng dẫn chuyển đổi phù hợp |
| Tích hợp | DSL có làm việc được với hệ thống hiện có không? | Đầu vào, đầu ra và lỗi có thể kết nối với quy trình hiện tại |

Nên đánh giá bằng một tập tình huống đại diện, bao gồm trường hợp thông thường, trường hợp biên và trường hợp không hợp lệ. So sánh với cách làm hiện tại giúp xác định DSL có tạo ra lợi ích thực tế hay chỉ chuyển độ phức tạp từ nơi này sang nơi khác.

## 8. Quy trình phát biểu bài toán và mục tiêu

Có thể dùng quy trình sau để chuyển một nhu cầu ban đầu thành mô tả bài toán đủ rõ cho giai đoạn thiết kế DSL:

1. **Thu thập tình huống thực tế.** Ghi lại các ví dụ người dùng đang xử lý, cách họ thực hiện và những điểm thường gây nhầm lẫn hoặc tốn công.
2. **Tìm mẫu lặp và khái niệm chung.** Nhóm các tình huống theo đối tượng, thao tác, quan hệ và quy tắc xuất hiện thường xuyên.
3. **Mô tả vấn đề hiện tại.** Nêu ai gặp khó khăn, khó khăn xảy ra ở bước nào, nguyên nhân và hậu quả của nó.
4. **Xác định người dùng và phạm vi.** Chỉ rõ ai viết hoặc đọc DSL, các trường hợp được hỗ trợ và những trường hợp nằm ngoài phạm vi.
5. **Phát biểu mục tiêu.** Mô tả kết quả cần đạt bằng các động từ cụ thể như diễn đạt, kiểm tra, chuẩn hóa, tự động hóa hoặc giới hạn.
6. **Đặt tiêu chí thành công.** Chọn cách quan sát hoặc đo lường để so sánh kết quả với quy trình hiện tại.
7. **Kiểm tra bằng ví dụ.** Viết thử một số mô tả đại diện và hỏi người dùng miền xem chúng có thể hiện đúng ý định không. Ở bước này, ví dụ là công cụ xác minh mô hình vấn đề; chưa cần chốt cú pháp cuối cùng.

Một phát biểu bài toán có thể theo mẫu:

> Nhóm **[người dùng]** cần mô tả **[công việc trong miền]**. Cách làm hiện tại gặp **[khó khăn cụ thể]**, dẫn đến **[hậu quả]**. DSL dự kiến cung cấp các khái niệm **[khái niệm cốt lõi]** để người dùng có thể **[kết quả mong muốn]**. DSL sẽ hỗ trợ **[phạm vi]**, tuân theo **[ràng buộc chính]** và được đánh giá bằng **[tiêu chí thành công]**.

Ví dụ điền mẫu cho bài toán báo cáo dữ liệu:

> Nhân viên phân tích dữ liệu cần mô tả các bước tạo báo cáo doanh thu định kỳ. Cách làm hiện tại yêu cầu lặp lại nhiều đoạn mã đọc, lọc, nhóm và xuất dữ liệu; quy tắc giữa các báo cáo dễ bị triển khai không nhất quán. DSL dự kiến cung cấp các khái niệm nguồn dữ liệu, điều kiện lọc, khóa nhóm, phép tổng hợp và đích xuất để người dùng mô tả quy trình theo một cấu trúc thống nhất. DSL hỗ trợ các phép biến đổi dữ liệu dạng bảng đã xác định, kiểm tra tên trường và kiểu dữ liệu trước khi chạy, đồng thời được đánh giá qua độ chính xác, thời gian tạo báo cáo và khả năng đọc lại cấu hình.

## 9. Những sai lầm cần tránh khi xác định mục tiêu

- **Bắt đầu từ cú pháp yêu thích.** Chọn dấu ngoặc, từ khóa hoặc định dạng tệp trước khi hiểu người dùng cần làm gì có thể khiến thiết kế bị chi phối bởi hình thức.
- **Đặt phạm vi quá rộng.** Cố gắng hỗ trợ mọi trường hợp làm tăng số khái niệm, quy tắc và ngoại lệ, khiến DSL khó học và khó kiểm soát.
- **Chỉ tối ưu độ ngắn.** Ít ký tự không đảm bảo dễ hiểu; cú pháp quá cô đọng có thể làm ý nghĩa trở nên mơ hồ.
- **Bỏ qua ngữ nghĩa.** Cú pháp hợp lệ chưa đủ. Cần xác định biểu thức có ý nghĩa gì, điều kiện nào áp dụng và kết quả được tạo ra như thế nào.
- **Không xác định người dùng.** Ngôn ngữ dành cho chuyên gia miền có thể khác ngôn ngữ dành cho lập trình viên hoặc người vận hành; không có đối tượng rõ ràng sẽ khó chọn mức trừu tượng phù hợp.
- **Không đặt tiêu chí thành công.** Nếu chỉ dựa vào cảm nhận rằng DSL “đẹp” hoặc “hiện đại”, nhóm phát triển khó biết nó có thực sự cải thiện quy trình hay không.
- **Bỏ qua chi phí vòng đời.** Tài liệu, công cụ hỗ trợ, thông báo lỗi, kiểm thử, tương thích phiên bản và đào tạo đều là một phần của chi phí sở hữu DSL.

## 10. Kết luận định hướng

Bài toán của DSL bắt đầu từ nhu cầu diễn đạt và xử lý một nhóm công việc có đặc điểm chung trong một miền xác định. Mục tiêu của DSL là đưa khái niệm miền vào cách biểu đạt, giảm phần phức tạp không cần thiết, làm rõ quy tắc, hỗ trợ kiểm tra và giúp công cụ xử lý mô tả nhất quán.

Một đề xuất DSL có cơ sở khi xác định được người dùng, tình huống thực tế, khó khăn của cách làm hiện tại, phạm vi hỗ trợ và tiêu chí đánh giá. Khi những yếu tố đó đã rõ, nhóm phát triển mới có căn cứ để lựa chọn mô hình, cú pháp, ngữ nghĩa và cách triển khai phù hợp.

## Câu hỏi tự kiểm tra

1. Vì sao việc xác định bài toán cần được thực hiện trước khi lựa chọn cú pháp hoặc công cụ phân tích DSL?
2. Nêu ba khó khăn có thể xuất hiện khi dùng ngôn ngữ lập trình đa dụng để mô tả một công việc thuộc miền chuyên biệt.
3. Trong ví dụ luồng xử lý dữ liệu, hãy chỉ ra các khái niệm miền và nêu hai quy tắc ngữ nghĩa mà DSL cần định nghĩa.
4. Phân biệt mục tiêu của DSL với quyết định triển khai như dùng parser riêng hoặc nhúng DSL vào Java.
5. Hãy phát biểu một bài toán DSL trong một miền khoa học máy tính mà bạn biết, bao gồm người dùng, khó khăn hiện tại, phạm vi và tiêu chí thành công.
