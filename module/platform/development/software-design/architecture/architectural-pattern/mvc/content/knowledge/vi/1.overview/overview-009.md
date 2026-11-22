# Trường hợp phù hợp và trường hợp chưa cần MVC

MVC (Model–View–Controller) phù hợp khi ứng dụng có dữ liệu và nghiệp vụ cần được trình bày qua một hoặc nhiều giao diện, đồng thời người dùng thực hiện các thao tác làm thay đổi trạng thái. Mẫu này giúp tách phần quản lý dữ liệu và quy tắc nghiệp vụ khỏi phần hiển thị và phần tiếp nhận yêu cầu.

Tuy vậy, MVC không phải lựa chọn mặc định cho mọi chương trình. Một trang tĩnh, một tiện ích nhỏ hoặc một tác vụ chạy nền có thể hoạt động rõ ràng hơn với cấu trúc đơn giản. Quyết định nên dựa trên cách ứng dụng tương tác với người dùng, độ phức tạp của luồng xử lý và khả năng thay đổi trong tương lai.

## 1. Nhìn vào đặc điểm của ứng dụng trước khi chọn MVC

Ba thành phần của MVC có trách nhiệm khác nhau:

- **Model** biểu diễn trạng thái và dữ liệu mà ứng dụng làm việc, cùng các quy tắc liên quan đến dữ liệu đó. Trong ứng dụng web, phần này thường phối hợp với lớp dịch vụ và lớp truy cập dữ liệu.
- **View** trình bày thông tin cho người dùng hoặc tạo biểu diễn đầu ra. View có thể là trang HTML, mẫu giao diện, hoặc một định dạng phản hồi như JSON khi kiến trúc áp dụng MVC cho API.
- **Controller** tiếp nhận tương tác hoặc yêu cầu, kiểm tra dữ liệu đầu vào ở mức phù hợp, gọi phần xử lý nghiệp vụ và chọn kết quả cần trả về.

MVC có ích khi ba trách nhiệm này có lý do để thay đổi độc lập. Ví dụ, cách hiển thị danh sách đơn hàng có thể thay đổi mà quy tắc tính tổng tiền vẫn giữ nguyên; hoặc một nghiệp vụ có thể được truy cập từ màn hình nhân viên và màn hình quản trị.

Không nên quyết định chỉ dựa trên số lượng màn hình hay số dòng mã. Một ứng dụng nhỏ nhưng có nhiều trạng thái biểu mẫu, quyền truy cập và quy trình phê duyệt vẫn có thể hưởng lợi từ MVC. Ngược lại, một ứng dụng có nhiều trang nội dung tĩnh chưa chắc cần đầy đủ cấu trúc MVC.

## 2. Những trường hợp MVC phù hợp

### 2.1. Ứng dụng web có nhiều luồng tương tác

MVC thường phù hợp với ứng dụng web nhận request, xử lý dữ liệu rồi trả về giao diện. Mỗi thao tác của người dùng có thể đi qua một luồng rõ ràng: Controller nhận request, phần nghiệp vụ xử lý dữ liệu trong Model hoặc service, sau đó View trình bày kết quả.

Ví dụ:

- Cổng quản lý nhân sự có màn hình hồ sơ, nghỉ phép, chấm công và phê duyệt.
- Hệ thống bán hàng có danh sách sản phẩm, giỏ hàng, đơn hàng và thanh toán.
- Ứng dụng quản lý học tập có khóa học, bài học, bài nộp và kết quả đánh giá.

Các ứng dụng này có nhiều loại dữ liệu, trạng thái và thao tác. Đặt phần tiếp nhận request, xử lý dữ liệu và trình bày vào những khu vực riêng giúp người phát triển tìm đúng nơi cần sửa.

### 2.2. Một nguồn dữ liệu được trình bày theo nhiều cách

Khi cùng một dữ liệu xuất hiện trong nhiều giao diện, MVC giúp tránh gắn quy tắc nghiệp vụ vào một màn hình cụ thể.

Chẳng hạn, thông tin đơn hàng có thể được trình bày trong:

- Trang chi tiết dành cho khách hàng.
- Bảng tổng hợp dành cho nhân viên vận hành.
- Trang quản trị có thêm thao tác hủy hoặc hoàn tiền.
- Báo cáo tóm tắt theo ngày hoặc theo trạng thái.

Các View có thể trình bày dữ liệu khác nhau, nhưng những quy tắc như kiểm tra trạng thái đơn hàng, tính phí hoặc xác định quyền thực hiện thao tác cần được xử lý ở phần nghiệp vụ dùng chung. Controller của từng luồng điều phối yêu cầu và chọn View phù hợp.

### 2.3. Biểu mẫu có xác thực và nhiều trạng thái

MVC đặc biệt hữu ích khi ứng dụng có biểu mẫu tạo, sửa hoặc gửi dữ liệu. Một biểu mẫu thường có nhiều nhánh xử lý:

1. Người dùng mở biểu mẫu.
2. Controller cung cấp dữ liệu cần thiết cho View.
3. Người dùng gửi biểu mẫu.
4. Ứng dụng kiểm tra dữ liệu đầu vào và quy tắc nghiệp vụ.
5. Nếu dữ liệu không hợp lệ, View hiển thị lỗi cùng các giá trị người dùng đã nhập.
6. Nếu thành công, ứng dụng chuyển đến trang xác nhận hoặc trang chi tiết.

Khi các bước này được phân tách, View tập trung vào cách hiển thị trường nhập và thông báo; Controller điều phối request; Model hoặc service đảm nhiệm quy tắc như giới hạn số lượng, kiểm tra trạng thái và lưu dữ liệu.

### 2.4. Nghiệp vụ có vòng đời và quy tắc thay đổi thường xuyên

Các quy trình như tạo đơn hàng, duyệt yêu cầu, xử lý hoàn tiền hoặc quản lý đăng ký thường có nhiều trạng thái và điều kiện chuyển trạng thái. MVC tạo ranh giới để phần giao diện không phải tự quyết định nghiệp vụ.

Ví dụ, nút “Phê duyệt” có thể chỉ xuất hiện khi người dùng có quyền và hồ sơ đang ở trạng thái chờ duyệt. Tuy nhiên, việc kiểm tra quyền và tính hợp lệ của chuyển trạng thái vẫn phải được thực hiện ở phía máy chủ trong lớp phù hợp. Ẩn nút trên View chỉ cải thiện trải nghiệm, không thay thế kiểm soát truy cập.

### 2.5. Nhiều người hoặc nhiều nhóm cùng phát triển

MVC có thể giúp chia công việc theo trách nhiệm: một nhóm xây dựng giao diện, một nhóm xử lý request và một nhóm phát triển dữ liệu hoặc nghiệp vụ. Điều này hữu ích khi hợp đồng giữa các phần được thống nhất rõ ràng.

Lợi ích chỉ xuất hiện khi ranh giới được giữ nhất quán. Nếu Controller chứa toàn bộ quy tắc nghiệp vụ hoặc View tự truy vấn cơ sở dữ liệu, cấu trúc MVC trên tên gọi sẽ không còn tạo ra sự phân tách thực chất.

## 3. Những trường hợp chưa cần MVC đầy đủ

### 3.1. Trang tĩnh hoặc nội dung ít tương tác

Một trang giới thiệu, trang tài liệu, trang thông báo hoặc landing page chỉ hiển thị nội dung cố định thường không cần đủ ba lớp MVC. Một bộ tạo trang tĩnh hoặc một template đơn giản có thể đáp ứng tốt hơn.

Nếu sau này trang có đăng nhập, biểu mẫu, nội dung cá nhân hóa hoặc dữ liệu động, có thể bổ sung cấu trúc xử lý cho đúng phần phát sinh tương tác.

### 3.2. Tiện ích nhỏ hoặc bản thử nghiệm có phạm vi hẹp

Một công cụ nội bộ chỉ có một biểu mẫu và một thao tác đơn giản có thể dùng một route handler hoặc một thành phần xử lý gọn. Việc tạo nhiều lớp, interface và thư mục chỉ để tuân theo hình thức MVC có thể làm tăng số bước đọc hiểu mà chưa đem lại lợi ích tương xứng.

Khi chức năng tăng lên, chẳng hạn xuất hiện nhiều loại biểu mẫu, quyền người dùng, lịch sử thay đổi hoặc quy tắc nghiệp vụ dùng chung, đó là thời điểm xem xét tách Controller, Model và View rõ hơn.

### 3.3. Chương trình chạy nền, batch hoặc xử lý dữ liệu

Một tác vụ đọc tệp, chuyển đổi dữ liệu, tổng hợp báo cáo theo lịch hoặc đồng bộ dữ liệu giữa hai hệ thống thường không có View tương tác với người dùng. Luồng xử lý của nó có thể được tổ chức theo pipeline, bước xử lý hoặc kiến trúc hướng sự kiện.

Vẫn cần phân tách dữ liệu, quy tắc và hạ tầng, nhưng không nhất thiết phải tạo Controller và View theo MVC. Ép một tác vụ batch vào MVC có thể tạo ra các thành phần không có trách nhiệm thực tế.

### 3.4. Hệ thống lấy sự kiện hoặc vòng lặp thời gian thực làm trung tâm

Trong trò chơi, hệ thống điều khiển thiết bị, xử lý luồng sự kiện hoặc ứng dụng thời gian thực, luồng chính có thể xoay quanh event loop, trạng thái liên tục và các bộ xử lý sự kiện. Mô hình này thường phù hợp hơn với cách tổ chức dựa trên sự kiện hoặc thành phần.

Một giao diện quản trị của hệ thống đó vẫn có thể dùng MVC. Cần chọn mẫu theo từng phần của ứng dụng thay vì buộc toàn bộ hệ thống dùng một mẫu duy nhất.

### 3.5. API thuần không dựng giao diện phía máy chủ

Một dịch vụ chỉ cung cấp API JSON cho ứng dụng di động hoặc frontend độc lập có thể không cần View HTML và cấu trúc MVC kiểu server-rendered. Handler hoặc Controller có thể nhận request, service xử lý nghiệp vụ, còn serializer tạo phản hồi JSON.

Có thể xem phần biểu diễn JSON là một dạng View trong cách áp dụng MVC rộng hơn. Điều quan trọng là không tạo thêm lớp View chỉ để đủ tên gọi; hãy giữ ranh giới giữa request, nghiệp vụ và định dạng phản hồi rõ ràng.

## 4. Bảng gợi ý lựa chọn theo tình huống

| Tình huống | Hướng tổ chức thường hợp lý | Lý do |
|---|---|---|
| Trang giới thiệu chỉ có nội dung tĩnh | Trang tĩnh hoặc template đơn giản | Hầu như không có luồng tương tác và trạng thái cần quản lý |
| Công cụ nội bộ có một biểu mẫu và một thao tác | Route handler hoặc cấu trúc tối giản | Ít nhánh xử lý, chưa có nhu cầu tách nhiều trách nhiệm |
| Ứng dụng quản lý đơn hàng có nhiều màn hình và trạng thái | MVC, thường kết hợp service layer | Có nhiều request, biểu mẫu, quy tắc và cách trình bày |
| Cổng nhân sự có phân quyền và quy trình phê duyệt | MVC | Luồng tương tác và trạng thái nghiệp vụ cần ranh giới rõ |
| API JSON cho frontend độc lập | Controller/handler + service + model; áp dụng MVC nếu phù hợp | Cần tách request và nghiệp vụ, nhưng không nhất thiết có View HTML |
| Tác vụ nhập và chuẩn hóa dữ liệu theo lịch | Pipeline hoặc batch processing | Luồng xử lý không xoay quanh tương tác và View |
| Giao diện quản trị cho một hệ thống thời gian thực | MVC ở phần giao diện quản trị; mẫu khác ở lõi xử lý | Mỗi phần có luồng và trách nhiệm riêng |

Bảng này là gợi ý ban đầu, không phải quy tắc cứng. Một ứng dụng có thể kết hợp nhiều cách tổ chức ở các khu vực khác nhau.

## 5. Ví dụ: ứng dụng quản lý công việc phát triển theo từng giai đoạn

Giả sử cần xây dựng một ứng dụng cho phép người dùng tạo và xem danh sách công việc.

### Giai đoạn đầu: chức năng rất nhỏ

Ứng dụng chỉ có một màn hình, một danh sách và một thao tác thêm công việc. Một route handler đơn giản có thể nhận dữ liệu, lưu công việc và trả về trang danh sách. Nếu logic còn ngắn và chỉ có một luồng sử dụng, chưa cần tạo nhiều tầng MVC.

### Giai đoạn tiếp theo: xuất hiện nhiều trách nhiệm

Sau một thời gian, ứng dụng có thêm:

- Đăng nhập và quyền xem công việc.
- Chỉnh sửa, hoàn thành và lưu trữ công việc.
- Tìm kiếm, lọc theo người phụ trách và thời hạn.
- Kiểm tra dữ liệu đầu vào và hiển thị lỗi.
- Màn hình quản trị và màn hình cá nhân.

Lúc này, tách MVC giúp kiểm soát độ phức tạp. Một luồng tạo công việc có thể được mô tả như sau:

```text
Người dùng gửi biểu mẫu
        |
        v
Controller nhận request
        |
        v
Kiểm tra đầu vào và gọi service
        |
        v
Model / service áp dụng quy tắc, lưu dữ liệu
        |
        v
Controller chọn kết quả phản hồi
        |
        v
View hiển thị lỗi hoặc trang công việc
```

Một đoạn mã giả minh họa trách nhiệm của Controller:

```text
handleCreateTask(request):
    input = readTaskInput(request)
    result = taskService.create(input, currentUser)

    if result.hasErrors:
        return render("tasks/new", {
            values: input,
            errors: result.errors
        })

    return redirect("/tasks/" + result.taskId)
```

Controller điều phối request và chọn phản hồi. Quy tắc như người dùng có được phép tạo công việc trong dự án hay không, thời hạn có hợp lệ không và trạng thái ban đầu là gì nên được xử lý trong service hoặc Model phù hợp. View chịu trách nhiệm trình bày biểu mẫu, lỗi và kết quả.

Ví dụ này cho thấy việc áp dụng MVC có thể diễn ra khi nhu cầu thực tế xuất hiện. Không cần thiết kế mọi lớp ngay từ bản thử nghiệm đầu tiên, nhưng cũng không nên giữ một handler duy nhất khi nhiều luồng bắt đầu dùng chung nghiệp vụ.

## 6. Dấu hiệu cho thấy ứng dụng đã cần tách MVC rõ hơn

Có thể xem xét chuyển từ cấu trúc đơn giản sang MVC khi thường xuyên gặp một hoặc nhiều dấu hiệu sau:

- Một hàm xử lý request vừa đọc dữ liệu, kiểm tra quyền, áp dụng quy tắc nghiệp vụ, truy vấn dữ liệu và tạo HTML.
- Nhiều màn hình lặp lại cùng một quy tắc hoặc tự triển khai cùng một thao tác.
- Thay đổi giao diện khiến phải sửa logic nghiệp vụ, hoặc thay đổi nghiệp vụ buộc phải sửa nhiều View.
- Khó kiểm thử quy tắc nghiệp vụ vì logic bị trộn với HTTP, template hoặc thành phần giao diện.
- Việc xử lý lỗi biểu mẫu, điều hướng và trạng thái ngày càng có nhiều nhánh.
- Các thành viên trong nhóm thường xuyên sửa cùng một khu vực vì trách nhiệm chưa rõ.

Khi gặp các dấu hiệu này, hãy tách theo trách nhiệm đang bị trộn lẫn. Có thể bắt đầu bằng việc đưa quy tắc nghiệp vụ dùng chung vào service, sau đó làm rõ Controller và View. Không cần tạo thêm lớp nếu chưa có trách nhiệm cụ thể để đặt vào đó.

## 7. Những điều MVC không tự giải quyết

MVC giúp tổ chức mã nguồn, nhưng bản thân mẫu này không bảo đảm ứng dụng có thiết kế tốt hoặc an toàn.

- **Không thay thế phân tầng nghiệp vụ:** Controller nên điều phối. Quy tắc nghiệp vụ phức tạp thường cần service hoặc domain model phù hợp.
- **Không tự bảo đảm bảo mật:** Máy chủ vẫn phải xác thực, phân quyền, kiểm tra dữ liệu và chống các kiểu tấn công phù hợp. Ẩn một nút trên View không phải là kiểm soát quyền.
- **Không tự bảo đảm hiệu năng:** Truy vấn dữ liệu, cache, phân trang và xử lý đồng thời vẫn cần được thiết kế riêng.
- **Không quy định một cấu trúc thư mục duy nhất:** Tên lớp và vị trí file phụ thuộc framework và quy ước dự án. Điều cốt lõi là trách nhiệm và hợp đồng giữa các thành phần.
- **Không có nghĩa mọi dữ liệu đều là một đối tượng Model duy nhất:** Model có thể gồm domain model, dữ liệu đầu vào, dữ liệu trình bày và các thành phần truy cập dữ liệu; cần chọn đúng loại cho từng mục đích.

## 8. Câu hỏi tự đánh giá trước khi chọn MVC

Trước khi áp dụng MVC đầy đủ, hãy tự trả lời:

1. Ứng dụng có nhiều tương tác hoặc nhiều luồng request cần điều phối không?
2. Dữ liệu và quy tắc nghiệp vụ có được dùng ở nhiều màn hình hoặc nhiều cách trình bày không?
3. Biểu mẫu có nhiều bước xác thực, trạng thái lỗi hoặc điều kiện nghiệp vụ không?
4. Giao diện và nghiệp vụ có khả năng thay đổi độc lập không?
5. Việc tách Controller, Model và View có giúp kiểm thử, bảo trì hoặc phối hợp nhóm dễ hơn không?

Nếu phần lớn câu trả lời là **có**, MVC thường là lựa chọn đáng cân nhắc. Nếu phần lớn là **không**, hãy bắt đầu bằng cấu trúc đơn giản nhất vẫn giữ được mã nguồn dễ đọc và dễ thay đổi. Khi yêu cầu phát triển, có thể tách dần theo trách nhiệm.

## Kết luận

MVC phù hợp nhất với ứng dụng có tương tác, dữ liệu và nghiệp vụ cần được trình bày qua nhiều luồng hoặc nhiều giao diện. Với trang tĩnh, tiện ích nhỏ, tác vụ batch hay hệ thống lấy sự kiện làm trung tâm, cấu trúc nhẹ hơn hoặc mẫu kiến trúc khác có thể phù hợp hơn. Hãy chọn MVC khi ranh giới Model, View và Controller giải quyết được vấn đề cụ thể về tổ chức, kiểm thử và bảo trì của ứng dụng.

