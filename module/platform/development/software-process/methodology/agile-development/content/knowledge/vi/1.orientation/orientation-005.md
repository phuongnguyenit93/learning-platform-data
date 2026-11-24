# Phân biệt phát triển lặp với phát triển tăng trưởng

Trong phát triển phần mềm Agile, nhóm không cần đợi đến khi hoàn thành toàn bộ hệ thống mới đưa kết quả cho người dùng. Thay vào đó, nhóm có thể kiểm tra giả định sớm, nhận phản hồi, cải thiện giải pháp và bổ sung những khả năng có giá trị theo từng đợt nhỏ. Hai khái niệm thường xuất hiện trong cách làm này là **phát triển lặp** (*iterative development*) và **phát triển tăng trưởng**, còn gọi chính xác hơn trong ngữ cảnh kỹ thuật là **phát triển tăng dần** (*incremental development*).

Hai khái niệm liên quan chặt chẽ nhưng trả lời hai câu hỏi khác nhau:

- **Lặp:** Ta học được gì từ phiên bản hiện có và sẽ chỉnh sửa nó thế nào trong vòng tiếp theo?
- **Tăng dần:** Sau đợt phát triển này, sản phẩm có thêm khả năng hoàn chỉnh, sử dụng được nào?

Một nhóm có thể làm việc theo các vòng lặp nhưng chưa bổ sung chức năng mới, hoặc bổ sung chức năng mới mà ít quay lại cải thiện phần cũ. Trong thực tế Agile, cách tiếp cận thường hiệu quả là **kết hợp cả lặp và tăng dần**.

## 1. Phát triển lặp là gì?

**Phát triển lặp** là cách xây dựng và hoàn thiện một giải pháp qua nhiều chu kỳ: tạo một phiên bản, quan sát hoặc đánh giá kết quả, tiếp nhận phản hồi rồi điều chỉnh phiên bản tiếp theo. Trọng tâm là **học hỏi và cải thiện**.

Ví dụ, một nhóm xây dựng chức năng tìm khung giờ khám bệnh:

1. **Vòng lặp 1:** Tạo bản đầu tiên cho phép xem danh sách khung giờ còn trống.
2. **Vòng lặp 2:** Sau khi thử với người dùng, thay danh sách dài bằng cách hiển thị theo ngày để việc chọn giờ dễ hơn.
3. **Vòng lặp 3:** Dựa trên dữ liệu sử dụng, cải thiện bộ lọc và cách hiển thị khung giờ phù hợp.

Cả ba vòng đều tập trung vào **cùng một khả năng tìm khung giờ**. Thứ thay đổi chủ yếu là chất lượng giải pháp: tính dễ sử dụng, độ chính xác, hiệu năng hoặc độ phù hợp với nhu cầu.

Một vòng lặp thường có các hoạt động: hình thành giả thuyết → xây dựng hoặc điều chỉnh → kiểm tra với tiêu chí rõ ràng → nhận phản hồi → quyết định bước tiếp theo. Vòng lặp không nhất thiết là một Sprint Scrum và cũng không bắt buộc phải tạo ra chức năng mới.

### Lặp đem lại lợi ích gì?

- **Giảm rủi ro hiểu sai nhu cầu:** Một bản thử nghiệm sớm giúp phát hiện rằng người dùng thực sự quan tâm đến điều gì.
- **Cải thiện chất lượng dần dần:** Nhóm có thể điều chỉnh thiết kế, tương tác, kiến trúc và hiệu năng dựa trên quan sát thực tế.
- **Thích ứng khi thông tin thay đổi:** Giải pháp ban đầu chỉ là giả thuyết có thể kiểm chứng, không phải cam kết bất biến.

Giới hạn cần nhớ: lặp đi lặp lại không tự động tạo ra giá trị. Nếu mỗi vòng chỉ chỉnh sửa giao diện theo sở thích chủ quan, không có tiêu chí đánh giá hoặc tín hiệu phản hồi, nhóm có thể tốn nhiều thời gian mà chưa cải thiện được kết quả.

## 2. Phát triển tăng trưởng (tăng dần) là gì?

**Phát triển tăng dần** chia phạm vi sản phẩm thành những **phần gia tăng** (*increment*) có thể tích hợp vào sản phẩm đã có. Sau mỗi phần gia tăng hoàn tất, sản phẩm cung cấp thêm một năng lực hoặc một mức giá trị sử dụng mới.

Vẫn với sản phẩm đặt lịch khám:

1. **Phần tăng dần 1:** Người dùng tìm được khung giờ còn trống.
2. **Phần tăng dần 2:** Người dùng có thể đặt một khung giờ và nhận xác nhận; chức năng tìm kiếm vẫn hoạt động.
3. **Phần tăng dần 3:** Người dùng có thể hủy lịch đã đặt theo quy tắc của phòng khám; các chức năng trước đó tiếp tục hoạt động.

Sản phẩm mở rộng từ **tìm giờ** sang **tìm và đặt giờ**, rồi thành **tìm, đặt và hủy lịch**. Trọng tâm là **tăng phạm vi khả năng có ích**.

Một phần gia tăng có giá trị cần được **tích hợp và kiểm chứng**. Chẳng hạn, hoàn thành riêng cơ sở dữ liệu đặt lịch nhưng chưa có cách nào để người dùng đặt lịch từ đầu đến cuối thường chỉ là tiến độ của một thành phần kỹ thuật, chưa phải một năng lực sản phẩm dùng được.

Trong Scrum, Increment phải đáp ứng **Definition of Done** (định nghĩa hoàn thành), có thể sử dụng và tạo ra tính minh bạch về tiến độ. **Có thể phát hành** không đồng nghĩa với **bắt buộc phát hành công khai ngay**: việc triển khai hoặc mở tính năng cho người dùng còn phụ thuộc quyết định sản phẩm, vận hành và điều kiện cần thiết.

### Tăng dần đem lại lợi ích gì?

- **Đưa giá trị vào sử dụng sớm:** Người dùng nhận được một phần hữu ích trước khi mọi ý tưởng của sản phẩm hoàn tất.
- **Giảm quy mô rủi ro của từng đợt:** Nhóm triển khai và kiểm tra một lát cắt nhỏ thay vì tích hợp tất cả ở cuối dự án.
- **Dễ thay đổi thứ tự ưu tiên:** Khi có thông tin mới, nhóm có thể bổ sung phần mang lại giá trị cao tiếp theo, hoãn phần kém cấp thiết.

Giới hạn cần nhớ: chỉ chia công việc thành nhiều phần nhỏ là chưa đủ. Nếu mỗi đợt chỉ bàn giao một lớp kỹ thuật rời rạc, các phần không kết nối và không tạo ra hành vi sử dụng được, nhóm vẫn phải đợi đến cuối mới nhận được phản hồi có ý nghĩa từ người dùng.

## 3. So sánh trực tiếp

| Khía cạnh | Phát triển lặp (*iterative*) | Phát triển tăng dần (*incremental*) |
| --- | --- | --- |
| Câu hỏi trung tâm | **Giải pháp hiện có cần được cải thiện như thế nào?** | **Sản phẩm có thể bổ sung khả năng nào tiếp theo?** |
| Trọng tâm thay đổi | Điều chỉnh, kiểm chứng và hoàn thiện một giải pháp | Mở rộng phạm vi khả năng sử dụng của sản phẩm |
| Kết quả điển hình | Phiên bản tốt hơn của chức năng hoặc thiết kế hiện có | Một năng lực mới được tích hợp vào sản phẩm hiện có |
| Nguồn phản hồi | Quan sát sử dụng, thử nghiệm, đánh giá chất lượng, dữ liệu thực tế | Việc đưa từng phần giá trị vào sử dụng và đo tác động |
| Rủi ro thường gặp | Lặp quá lâu mà không học được điều mới | Chia theo thành phần kỹ thuật, tạo nhiều mảnh chưa dùng được |
| Dấu hiệu tiến bộ | Giả định được kiểm chứng; chất lượng hoặc kết quả sử dụng cải thiện | Sản phẩm có thêm hành vi hoàn chỉnh, đáp ứng tiêu chí chấp nhận |

**Một vòng lặp** chỉ một chu kỳ học hỏi và điều chỉnh; **một phần tăng dần** chỉ kết quả sản phẩm được bổ sung. Chúng không phải hai tên gọi cho cùng một sự kiện. Một vòng lặp có thể tạo ra phần tăng dần; một phần tăng dần cũng có thể được tinh chỉnh qua nhiều vòng lặp.

Sơ đồ dưới đây cố ý tách hai góc nhìn:

~~~mermaid
flowchart TB
    subgraph L["Phát triển lặp: cải thiện cùng một khả năng"]
        A["Tìm giờ - phiên bản 1"] --> B["Tìm giờ - phiên bản 2: dễ chọn ngày hơn"]
        B --> C["Tìm giờ - phiên bản 3: lọc nhanh hơn"]
    end
    subgraph I["Phát triển tăng dần: bổ sung khả năng"]
        D["Tìm giờ"] --> E["Tìm giờ + đặt lịch"]
        E --> F["Tìm giờ + đặt lịch + hủy lịch"]
    end
~~~

## 4. Có thể kết hợp cả hai trong cùng một sản phẩm

Xét ba đợt làm việc của nhóm phát triển ứng dụng đặt lịch. Mỗi đợt vừa hoàn thiện điều đã có, vừa có thể bổ sung chức năng mới:

| Đợt | Lặp: điều chỉnh dựa trên phản hồi | Tăng dần: giá trị bổ sung |
| --- | --- | --- |
| 1 | Thử nghiệm cách trình bày danh sách khung giờ | Người dùng tìm được khung giờ |
| 2 | Đơn giản hóa cách chọn ngày sau khi quan sát người dùng | Người dùng đặt được lịch và nhận xác nhận |
| 3 | Cải thiện thông báo lỗi và khả năng kiểm tra lịch đã đặt | Người dùng tự hủy lịch hợp lệ |

Ở đợt 2, nhóm **lặp** trên trải nghiệm tìm giờ nhưng đồng thời tạo một **phần tăng dần** là đặt lịch. Hai loại tiến bộ cùng diễn ra trong một đợt, không cạnh tranh hay loại trừ nhau.

Ví dụ này cũng cho thấy lý do phải xét **sản phẩm đang chạy được** thay vì chỉ đếm số màn hình, số API hoặc số dòng mã. Nếu giao diện đặt lịch đã làm xong nhưng không lưu dữ liệu, không kiểm tra trùng giờ và không gửi xác nhận như yêu cầu, năng lực đặt lịch chưa hoàn tất theo góc nhìn người dùng.

### Vai trò của phản hồi sớm

Giả sử nhóm dự đoán người dùng muốn bộ lọc thật chi tiết, nên định dành hai tuần phát triển bộ lọc nâng cao. Khi cho người dùng sử dụng phiên bản đầu tiên, nhóm phát hiện họ quan tâm nhiều hơn đến **khung giờ sớm nhất có thể đặt**. Phản hồi này dẫn đến hai quyết định:

- **Theo hướng lặp:** Điều chỉnh chức năng tìm giờ để ưu tiên khung giờ gần nhất và kiểm tra xem thời gian tìm lịch có giảm không.
- **Theo hướng tăng dần:** Ưu tiên xây dựng khả năng đặt ngay khung giờ đó trước các tùy chọn nâng cao chưa được xác thực.

Đây là tinh thần thích ứng của Agile: làm đủ sớm để kiểm tra giả định, đo điều thực sự xảy ra rồi điều chỉnh cách tạo ra giá trị.

## 5. Biến sự khác biệt thành cách quản lý backlog

Một **product backlog** có thể chứa cả công việc bổ sung khả năng mới lẫn công việc cải thiện khả năng đã có. Để tránh nhầm lẫn, hãy mô tả công việc theo kết quả mong muốn thay vì tên bộ phận cần làm.

**User story cho phần tăng dần:**

> Là người cần khám bệnh, tôi muốn đặt một khung giờ đang trống để chắc chắn có lịch hẹn.

Một số tiêu chí chấp nhận có thể là: chọn được khung giờ hợp lệ; không thể đặt hai lịch trùng cùng một suất; sau khi đặt thành công có mã hoặc thông tin xác nhận; người dùng thấy thông báo rõ ràng khi khung giờ vừa hết chỗ.

**Hạng mục cải thiện qua vòng lặp:**

> Sau khi quan sát người dùng thử tính năng tìm giờ, điều chỉnh danh sách để người dùng nhận ra khung giờ sớm nhất dễ hơn và kiểm tra tác động bằng tác vụ sử dụng thực tế.

Hai hạng mục có thể được xếp ưu tiên theo cùng một mục tiêu sản phẩm: giúp người dùng tìm và đặt lịch thành công với ít thao tác, ít lỗi. Việc ưu tiên không nhất thiết là “chức năng mới trước, cải thiện sau”; một vấn đề nghiêm trọng ở chức năng hiện có có thể đáng xử lý hơn việc bổ sung khả năng mới.

**Chia phần tăng dần theo lát cắt dọc:** Một lát cắt nhỏ nên đi qua các phần cần thiết từ giao diện, quy tắc nghiệp vụ, dữ liệu đến kiểm tra để hoàn tất một hành vi có ý nghĩa. Tránh coi “làm xong toàn bộ database”, “làm xong tất cả API” hoặc “làm xong giao diện” là những increment độc lập nếu chúng chưa tạo ra kết quả sử dụng được.

**Đặt giới hạn cho vòng lặp:** Trước khi thử nghiệm, nêu rõ điều muốn học, cách quan sát và điều kiện quyết định tiếp tục hay thay đổi hướng. Ví dụ: cho năm người dùng thử chọn lịch trên bản mẫu, ghi nhận nơi họ gặp khó khăn rồi điều chỉnh và kiểm tra lại. Số người dùng này chỉ là ví dụ về một thử nghiệm nhỏ, không phải ngưỡng bảo đảm tính đại diện thống kê.

## 6. Mối liên hệ với Scrum, Kanban và XP

**Agile** nhấn mạnh giao sản phẩm có giá trị sớm, cộng tác với khách hàng, đón nhận thay đổi và cải tiến thường xuyên. Phát triển lặp và tăng dần là hai cơ chế hỗ trợ các mục tiêu đó; bản thân chúng không phải hai framework cạnh tranh.

- **Scrum:** Sprint là chu kỳ có thời hạn, tạo cơ hội kiểm tra và thích ứng. Nhóm hướng đến một Increment có giá trị, đáp ứng Definition of Done. Nhận phản hồi qua Sprint Review và điều chỉnh Product Backlog; xem lại cách làm việc qua Sprint Retrospective. Việc chỉnh một khả năng cũ và thêm khả năng mới có thể xảy ra trong cùng Sprint.
- **Kanban:** Tập trung trực quan hóa luồng công việc, quản lý công việc đang làm (WIP) và cải thiện dòng chảy. Các khả năng có thể được hoàn tất, giao và nhận phản hồi liên tục; không cần giả định mọi increment phải gắn với một Sprint cố định.
- **Extreme Programming (XP):** Các thực hành như kiểm thử tự động, tích hợp liên tục, lập trình cặp và tái cấu trúc mã giúp nhóm thay đổi phần đã có an toàn hơn, đồng thời duy trì khả năng phát hành những phần tăng dần nhỏ.

Không nên đánh đồng **lặp** với “cứ hết hai tuần là xong một tính năng” hay **tăng dần** với “phải phát hành mỗi ngày”. Nhịp làm việc, thời điểm sản phẩm đủ điều kiện sử dụng và thời điểm phát hành là các quyết định có liên quan nhưng khác nhau.

## 7. Đo tiến bộ bằng kết quả, không chỉ bằng số vòng và số phần

Đếm số iteration đã chạy hoặc số hạng mục backlog đã đóng không cho biết liệu sản phẩm có tốt hơn với người dùng hay không. Có thể dùng các nhóm tín hiệu sau:

| Điều cần hiểu | Ví dụ tín hiệu | Cách đọc đúng |
| --- | --- | --- |
| Vòng lặp có giúp học và cải thiện? | Tỷ lệ hoàn thành tác vụ, số lỗi sử dụng, thời gian người dùng tìm được khung giờ | So sánh trước và sau cùng loại tác vụ, chú ý bối cảnh |
| Phần tăng dần có tạo giá trị? | Tỷ lệ đặt lịch thành công, số lịch được xác nhận, mức sử dụng khả năng mới | Đánh giá kết quả người dùng nhận được thay vì chỉ đếm tính năng |
| Nhóm có giao được các phần nhỏ ổn định? | Lead time, cycle time, công việc đang làm (WIP), tần suất phát hành | Theo dõi xu hướng để nhận ra tắc nghẽn và cải thiện dòng chảy |
| Chất lượng có được duy trì? | Lỗi sau phát hành, kiểm thử tự động, sự cố tích hợp | Phần mới phải hoạt động cùng phần cũ, không làm hỏng hành vi hiện có |

Chẳng hạn, nhóm hoàn tất ba increment trong ba đợt nhưng tỷ lệ đặt lịch thành công thấp vì giao diện khó hiểu. Khi đó, một vòng lặp cải thiện trải nghiệm có thể tạo ra nhiều giá trị hơn một increment bổ sung chức năng nữa. Ngược lại, nếu chức năng tìm lịch đã đủ tốt nhưng người dùng vẫn không thể đặt lịch, chỉ tiếp tục tinh chỉnh bộ lọc sẽ không giải quyết nhu cầu chính.

## 8. Các nhầm lẫn thường gặp

**“Iteration nào cũng phải có tính năng mới.”** Không nhất thiết. Một vòng lặp có thể tập trung kiểm chứng giả thuyết, cải thiện trải nghiệm hoặc xử lý rủi ro của giải pháp hiện tại. Trong Scrum, mục tiêu và cam kết với Increment vẫn phải được hiểu theo hướng dẫn của Scrum, nhưng không nên dùng từ *iteration* như từ đồng nghĩa với *feature*.

**“Cứ chia việc theo tầng kỹ thuật là đang phát triển tăng dần.”** Chia nhỏ công việc giúp lập kế hoạch, nhưng chỉ khi các thành phần được tích hợp thành khả năng sử dụng được thì mới thấy giá trị sản phẩm tăng lên. Lát cắt dọc thường cho phép kiểm tra kết quả sớm hơn.

**“Increment phải hoàn hảo ngay từ đầu.”** Increment phải đạt mức chất lượng và tiêu chí hoàn thành đã thống nhất, nhưng một chức năng có thể tiếp tục được cải thiện sau khi người dùng sử dụng và phản hồi. “Chưa cần hoàn hảo” không có nghĩa là chấp nhận chức năng sai, thiếu bảo mật hoặc chưa kiểm thử theo tiêu chuẩn của nhóm.

**“Phải chờ nhiều increment mới xin phản hồi.”** Phản hồi có thể đến từ bản mẫu, thử nghiệm, quan sát sử dụng hoặc một phần sản phẩm đã hoàn tất. Chính thông tin sớm giúp điều chỉnh backlog trước khi đầu tư lớn hơn.

**“Lặp và tăng dần là hai giai đoạn nối tiếp bắt buộc.”** Không. Đây là hai chiều tổ chức việc phát triển có thể xảy ra song song, với cường độ khác nhau tùy rủi ro, nhu cầu và trạng thái sản phẩm.

## 9. Bài tập tình huống

Một nhóm phát triển nền tảng học trực tuyến đã có trang tìm khóa học. Người học phản ánh rằng kết quả tìm kiếm khó chọn. Nhóm đồng thời nhận yêu cầu xây dựng chức năng lưu khóa học yêu thích.

Hãy phân loại ba đề xuất:

1. Thử hai cách sắp xếp kết quả tìm kiếm, quan sát người học chọn khóa nhanh hơn ở cách nào.
2. Hoàn thiện chức năng lưu khóa học yêu thích, bao gồm giao diện, lưu dữ liệu và truy xuất danh sách đã lưu.
3. Trong cùng đợt làm việc, cải thiện cách sắp xếp kết quả tìm kiếm và bàn giao chức năng lưu yêu thích.

**Gợi ý đối chiếu:**

- **Đề xuất 1:** Chủ yếu là **lặp**, vì nhóm học và chỉnh một khả năng sẵn có.
- **Đề xuất 2:** Chủ yếu là **tăng dần**, vì sản phẩm có thêm một khả năng hoàn chỉnh.
- **Đề xuất 3:** **Kết hợp lặp và tăng dần**, vì vừa cải thiện phần cũ vừa bổ sung giá trị mới.

Khi lên kế hoạch, hãy tự hỏi: “Chúng ta cần học thêm điều gì về giải pháp đang có?” và “Phần năng lực nhỏ nhất nào có thể đưa vào sử dụng một cách an toàn?” Hai câu hỏi này giúp nhóm lựa chọn công việc phù hợp, nhận phản hồi sớm và cải tiến liên tục mà không đánh đồng chuyển động của quy trình với tiến bộ của sản phẩm.
