# Thu thập phản hồi từ sử dụng thực tế và thử nghiệm với người dùng

## 1. Vì sao phản hồi thực tế quyết định giá trị sản phẩm?

Trong phát triển phần mềm Agile, **giao được chức năng** là một bước quan trọng, nhưng chưa đủ để khẳng định **đã tạo ra giá trị**. Nhóm có thể hoàn thành đúng user story, vượt qua kiểm thử kỹ thuật và phát hành thành công, trong khi người dùng vẫn không tìm được điều họ cần hoặc gặp khó khăn khi thao tác.

Ví dụ, một nền tảng học trực tuyến có tính năng tìm khóa học theo chủ đề. Bảng công việc cho thấy tính năng đã hoàn tất và chạy ổn định. Tuy nhiên, sau khi đưa vào sử dụng, phần lớn người học chỉ xem kết quả tìm kiếm mà không mở khóa học nào. Tình huống này đặt ra nhiều giả thuyết: kết quả không phù hợp, tên khóa học khó hiểu, bộ lọc không hiệu quả, giao diện trên điện thoại gây khó dùng, hoặc người học chỉ đang tham khảo.

**Phản hồi từ sử dụng thực tế** giúp nhận ra điều gì đang xảy ra khi sản phẩm được dùng trong bối cảnh thật. **Thử nghiệm với người dùng** giúp quan sát và kiểm chứng cụ thể hơn vì sao họ gặp trở ngại, một ý tưởng có dễ hiểu không và một thay đổi có đáng triển khai không.

Hai nguồn thông tin hỗ trợ nhau nhưng không thay thế nhau:

- **Dữ liệu hành vi** thường trả lời tốt câu hỏi **“Điều gì xảy ra, ở đâu và với tần suất nào?”**.
- **Quan sát và trao đổi với người dùng** giúp khám phá **“Người dùng đang cố làm gì, hiểu giao diện ra sao và vì sao họ hành động như vậy?”**.
- **Thử nghiệm có thiết kế** có thể giúp trả lời **“Giải pháp đề xuất có tạo ra khác biệt đáng tin cậy hay không?”**, tùy chất lượng phương pháp và dữ liệu.

Chủ đề này thuộc nhóm kiến thức **Sản phẩm và giá trị** của module **AGILE_DEVELOPMENT**. Việc thu thập phản hồi sớm tạo đầu vào cho product backlog, user story, các phần tăng dần của sản phẩm và việc điều chỉnh cách phối hợp trong Scrum, Kanban hoặc XP.

## 2. Phân biệt các nguồn phản hồi

“Phản hồi người dùng” không chỉ là một biểu mẫu đánh giá sao hoặc một cuộc họp yêu cầu tính năng. Có nhiều cách quan sát khác nhau, mỗi cách có thế mạnh và giới hạn riêng.

| Nguồn / phương pháp | Thu thập điều gì? | Trả lời tốt câu hỏi | Giới hạn quan trọng |
| --- | --- | --- | --- |
| **Product analytics** (dữ liệu sử dụng) | Sự kiện xem trang, tìm kiếm, lỗi, hoàn tất tác vụ, quay lại sử dụng | Người dùng đang làm gì, hành trình bị rơi ở đâu? | Thường không cho biết chính xác *vì sao* |
| **Phản hồi tự nguyện** | Đánh giá, biểu mẫu góp ý, yêu cầu hỗ trợ | Vấn đề nào khiến người dùng chủ động lên tiếng? | Thiên lệch về nhóm có động lực gửi phản hồi |
| **Phỏng vấn người dùng** | Mục tiêu, bối cảnh, động cơ, khó khăn, ngôn ngữ họ dùng | Người dùng thật sự muốn giải quyết công việc gì? | Lời kể có thể khác hành vi thực tế |
| **Usability testing** (thử nghiệm khả dụng) | Người tham gia thực hiện tác vụ cụ thể trên giao diện hoặc bản mẫu | Tìm nút có dễ không, vướng ở bước nào, lỗi hiểu biết nào xuất hiện? | Mẫu nhỏ hỗ trợ phát hiện vấn đề, không tự đại diện cho tỷ lệ toàn bộ người dùng |
| **Thử nghiệm A/B có phân nhóm ngẫu nhiên** | Kết quả của hai hoặc nhiều biến thể trên nhóm phù hợp | Thay đổi có tác động nhân quả đến chỉ số được định nghĩa không? | Cần thiết kế, quy mô mẫu, thời gian, kiểm soát sai lệch phù hợp |
| **Beta / phát hành giới hạn** | Hành vi, sự cố và góp ý trong nhóm người dùng được chọn | Phần tăng dần có hoạt động trong bối cảnh gần thực tế? | Nhóm beta có thể khác quần thể người dùng rộng hơn |
| **Đánh giá của bộ phận vận hành / hỗ trợ** | Vướng mắc lặp lại, sự cố, trường hợp ngoại lệ | Vấn đề nào không hiện rõ qua giao diện chính? | Quan sát qua trung gian, cần kiểm chứng với người dùng khi có thể |

**Cần phân biệt “người dùng nói họ sẽ làm gì” và “họ thực sự làm gì”.** Ví dụ, 80% người trả lời khảo sát nói thích tính năng lưu khóa học nhưng chỉ một phần nhỏ thực sự dùng sau phát hành. Không nên kết luận một trong hai dữ liệu “sai”; chúng đo những điều khác nhau.

Một cách tiếp cận có giá trị là **đối chiếu nhiều nguồn bằng chứng** (*triangulation*). Dữ liệu chỉ ra vị trí có vấn đề; buổi thử nghiệm giúp quan sát nguyên nhân có thể xảy ra; một thay đổi nhỏ và số liệu sau triển khai giúp kiểm tra giả thuyết.

## 3. Bắt đầu từ câu hỏi học hỏi, không bắt đầu từ công cụ

Trước khi cài công cụ phân tích hoặc mời người dùng phỏng vấn, nhóm nên xác định điều chưa biết và quyết định cần đưa ra.

Giả sử nhóm thấy ít người đăng ký khóa học sau khi tìm kiếm:

1. **Quan sát:** Nhiều người xem kết quả tìm kiếm nhưng ít người tiếp tục đến trang chi tiết.
2. **Câu hỏi:** Họ không tìm được khóa phù hợp, không hiểu thông tin hiển thị hay không có ý định đăng ký?
3. **Giả thuyết:** Nhãn trình độ và mục tiêu học tập không đủ rõ khiến người học ngại mở khóa học.
4. **Tín hiệu cần quan sát:** Tỷ lệ mở trang chi tiết từ kết quả tìm kiếm; tỷ lệ chọn đúng khóa trong một bài thử; lời giải thích khi người học cân nhắc.
5. **Quyết định dự kiến:** Nếu thông tin khóa chưa rõ, ưu tiên cải thiện nội dung thẻ khóa; nếu vấn đề nằm ở độ phù hợp kết quả, cần xử lý tìm kiếm trước.

Câu hỏi tốt liên hệ trực tiếp tới **quyết định sản phẩm**. “Người dùng có thích giao diện không?” khá rộng và dễ dẫn đến ý kiến cảm tính. “Người mới học Java có nhận biết khóa nào phù hợp trình độ của họ trong danh sách kết quả không?” cụ thể hơn và dễ quan sát.

### Phân biệt đầu ra với kết quả

| Loại | Ví dụ | Có chứng minh giá trị chưa? |
| --- | --- | --- |
| **Đầu ra (output)** | Ra mắt bộ lọc theo trình độ | Chưa; chỉ chứng minh có chức năng |
| **Hành vi sử dụng** | Người học sử dụng bộ lọc và mở khóa phù hợp | Có tín hiệu bước đầu |
| **Kết quả cho người dùng (outcome)** | Người học chọn được khóa phù hợp nhanh hơn và ít bỏ cuộc | Gần mục tiêu giá trị hơn |
| **Tác động dài hạn (impact)** | Người học duy trì việc học và đạt mục tiêu kỹ năng tốt hơn | Cần thêm thời gian và cách đo phù hợp |

Tránh chọn một chỉ số thuận tiện nhưng xa giá trị cốt lõi. Số lượt nhấp tăng có thể chỉ vì giao diện buộc người dùng nhấp nhiều lần hơn. Thời gian ở lại trang lâu hơn có thể phản ánh sự hứng thú hoặc sự bối rối.

## 4. Vòng lặp thu thập phản hồi và cải thiện sản phẩm

Một nhóm Agile có thể tổ chức vòng học hỏi nhỏ, gắn với việc giao sản phẩm tăng dần:

~~~mermaid
flowchart TD
    A["Xác định nhu cầu và câu hỏi cần học"]
    B["Chọn tín hiệu, phương pháp và đối tượng"]
    C["Thu thập dữ liệu sử dụng / quan sát thử nghiệm"]
    D["Phân tích, đối chiếu và diễn giải"]
    E["Ra quyết định và điều chỉnh product backlog"]
    F["Giao thay đổi nhỏ, kiểm tra chất lượng"]
    A --> B --> C --> D --> E --> F --> C
    D -->|"Chưa đủ bằng chứng"| B
~~~

Đây là **vòng học hỏi**, không phải chuỗi bước chỉ thực hiện một lần. Có thể lặp từ việc làm rõ vấn đề trước khi viết mã, qua thử bản mẫu, đến đo kết quả sau khi phát hành.

Để mỗi vòng có ý nghĩa, hãy ghi lại:

- **Quyết định cần hỗ trợ:** Sửa trang tìm kiếm, thêm bộ lọc hay giữ nguyên?
- **Bằng chứng hiện có:** Sự kiện sử dụng, báo lỗi, thử nghiệm hoặc phỏng vấn nào?
- **Điều chưa chắc chắn:** Cỡ mẫu, nhóm người dùng, yếu tố gây nhiễu hay dữ liệu thiếu?
- **Hành động tiếp theo:** Thử bản mẫu, điều chỉnh một lát cắt chức năng, khảo sát nhóm khác hoặc dừng ý tưởng?
- **Mốc kiểm tra lại:** Khi nào và bằng tín hiệu gì đánh giá quyết định vừa đưa ra?

## 5. Đo hành vi sử dụng thực tế một cách có mục đích

### 5.1. Thiết kế sự kiện (event) theo hành trình người dùng

Trong nền tảng học trực tuyến, nhóm muốn hiểu hành trình từ tìm khóa đến đăng ký. Có thể thống nhất tập sự kiện tối thiểu:

| Sự kiện minh họa | Khi nào ghi nhận? | Thuộc tính phù hợp để phân tích |
| --- | --- | --- |
| **course_search_submitted** | Người học thực hiện tìm kiếm | Loại bộ lọc, có/không kết quả |
| **course_result_viewed** | Danh sách kết quả được hiển thị thành công | Số kết quả, loại thiết bị |
| **course_detail_opened** | Mở trang chi tiết một khóa | Vị trí kết quả, loại thiết bị |
| **enrollment_started** | Bắt đầu đăng ký khóa | Loại khóa, điểm bắt đầu |
| **enrollment_completed** | Hệ thống xác nhận đăng ký thành công | Loại khóa, phiên bản giao diện |
| **enrollment_failed** | Đăng ký không thành công | Mã lỗi đã chuẩn hóa, bước xảy ra lỗi |

Đặt tên sự kiện nhất quán và mô tả **điều kiện ghi nhận**. Ví dụ, *enrollment_completed* nên chỉ được ghi khi hệ thống thực sự xác nhận kết quả; một lượt nhấp nút “Đăng ký” chưa phải đăng ký thành công.

Nên xác định rõ “một người dùng”, “một phiên sử dụng” và “một lần thực hiện tác vụ” khác nhau thế nào. Nếu người dùng bấm nút ba lần, ba lượt nhấp không nhất thiết tương ứng ba người hay ba lần đăng ký.

Không cần gửi thông tin cá nhân nhạy cảm vào sự kiện chỉ để phân tích. Tránh ghi mật khẩu, nội dung tin nhắn riêng, thông tin thanh toán, dữ liệu học tập nhạy cảm hoặc định danh trực tiếp không cần thiết vào log phân tích. Dùng mã lỗi, nhóm thiết bị và các thuộc tính được phép thu thập; áp dụng quy định về quyền riêng tư, đồng ý sử dụng dữ liệu và lưu giữ tương ứng với hệ thống.

### 5.2. Kiểm tra chất lượng dữ liệu trước khi phân tích

Một dashboard đẹp không bảo đảm số liệu đúng. Nhóm cần kiểm tra:

1. Sự kiện có được gửi **đúng thời điểm** không, và có ghi hai lần do retry hay render lại không?
2. Luồng thất bại, mất mạng hoặc người dùng thoát giữa chừng có được phản ánh không?
3. Mã định danh có đủ để liên kết các bước theo cách hợp lệ, hay đang vô tình đếm trùng người?
4. Phiên bản ứng dụng web, mobile và các môi trường thử nghiệm có dùng cùng quy ước không?
5. Những người chặn tracking hoặc không cho phép thu thập có làm dữ liệu quan sát chỉ còn là một phần quần thể?
6. Tên sự kiện hoặc quy tắc ghi nhận có thay đổi giữa hai giai đoạn so sánh không?

Nếu thiếu thông tin này, nhóm có thể nhầm **lỗi đo lường** với **vấn đề sản phẩm**. Ví dụ, tỷ lệ đăng ký đột ngột giảm sau phát hành có thể do nút đăng ký hỏng, hoặc do sự kiện xác nhận không còn được gửi.

### 5.3. Đọc phễu chuyển đổi (conversion funnel)

Giả sử trong một nhóm người dùng được xác định và một khoảng thời gian thống nhất, dữ liệu minh họa cho thấy:

| Bước hành trình | Số người duy nhất đạt bước | Tỷ lệ so với bước trước | Tỷ lệ so với 1.000 người xem kết quả |
| --- | ---: | ---: | ---: |
| Xem kết quả tìm kiếm | 1.000 | — | 100% |
| Mở trang chi tiết khóa | 300 | 30% | 30% |
| Bắt đầu đăng ký | 210 | 70% | 21% |
| Đăng ký thành công | 180 | Khoảng 85,7% | 18% |

Các con số chỉ là **ví dụ giả định**. Bảng này mô tả phễu tuần tự theo người duy nhất: người đạt bước sau cũng đã đạt các bước trước trong phạm vi đo, mỗi người chỉ tính một lần ở mỗi bước.

Từ đó, tỷ lệ đi tiếp thấp nhất xuất hiện ở bước **xem kết quả → mở chi tiết**. Đây là **điểm cần điều tra**, chưa chứng minh nguyên nhân nằm ở thiết kế thẻ khóa học. Có thể người học đã tìm được thông tin cần thiết ngay trên danh sách, hoặc người dùng chỉ vào tham khảo.

Nên kiểm tra theo **phân khúc có ý nghĩa**: người dùng mới so với người dùng quay lại, điện thoại so với máy tính, người tìm khóa lập trình cơ bản so với nâng cao. Không chia nhóm quá nhỏ đến mức dữ liệu mất tính ổn định hoặc gây nguy cơ nhận dạng cá nhân.

### 5.4. Đọc số liệu cùng bối cảnh

Khi so sánh trước và sau một thay đổi, cần xem những yếu tố khác: chiến dịch thu hút người dùng, mùa thi, thay đổi giá, tính ổn định của hệ thống, phần trăm lưu lượng thiết bị di động hoặc cách phân phối nguồn truy cập. **Tăng chỉ số sau phát hành không tự chứng minh thay đổi là nguyên nhân**.

Nên gắn dữ liệu với thời gian, phiên bản tính năng, nhóm được tiếp xúc với thay đổi và định nghĩa chỉ số. Những trường hợp ít gặp nhưng gây hại lớn như mất dữ liệu, đặt hàng trùng, khóa truy cập hoặc lỗi thanh toán không nên bị bỏ qua chỉ vì phễu chuyển đổi vẫn tăng.

## 6. Thử nghiệm khả dụng với người dùng (usability testing)

Thử nghiệm khả dụng là quá trình **quan sát người tham gia thực hiện nhiệm vụ đại diện trên sản phẩm, bản mẫu hoặc phiên bản thử nghiệm** để nhận ra điều gì dễ hiểu, khó hiểu và cản trở họ hoàn thành mục tiêu.

Nó khác với việc hỏi “Bạn có thích thiết kế này không?”. Người tham gia có thể nói thích một giao diện nhưng không tìm được nút quan trọng. Quan sát thao tác thực tế giúp phát hiện khoảng cách này.

### 6.1. Chuẩn bị một buổi thử nghiệm

**Bước 1 — Xác định câu hỏi nghiên cứu.** Ví dụ: Người học mới có thể chọn khóa Java phù hợp với trình độ từ danh sách kết quả không?

**Bước 2 — Chọn người tham gia phù hợp.** Nếu sản phẩm dành cho người mới học lập trình, đừng chỉ thử với kỹ sư trong nhóm phát triển. Cần chú ý thiết bị, kinh nghiệm, nhu cầu hỗ trợ tiếp cận và bối cảnh sử dụng của người dùng mục tiêu.

**Bước 3 — Chuẩn bị môi trường.** Chọn bản mẫu hoặc phiên bản chạy ổn định, tài khoản thử, dữ liệu không nhạy cảm, đường kết nối và cách ghi chép. Thông báo rõ mục đích, cách sử dụng ghi âm/ghi hình nếu có, xin đồng ý phù hợp và cho phép dừng tham gia.

**Bước 4 — Soạn tác vụ trung lập.** Mô tả mục tiêu người dùng mà không chỉ vị trí nút hoặc tên giải pháp nhóm muốn kiểm chứng.

**Bước 5 — Thống nhất cách quan sát.** Ghi nhận hoàn thành tác vụ, thao tác sai, điểm dừng, câu hỏi người dùng đưa ra và nhận xét sau khi thao tác.

### 6.2. Viết tác vụ không gợi ý đáp án

**Tác vụ mang tính dẫn dắt:**

> “Hãy bấm vào bộ lọc ‘Cơ bản’ ở bên trái rồi chọn khóa Java phù hợp.”

**Tác vụ ít dẫn dắt hơn:**

> “Bạn mới bắt đầu học Java và muốn tìm một khóa phù hợp để đăng ký. Hãy tìm một khóa mà bạn cho là phù hợp với mình.”

Tác vụ thứ hai cho phép quan sát người học có tự phát hiện bộ lọc, hiểu thông tin trình độ và ra quyết định được không.

Người điều phối nên hỏi trung lập: “Bạn đang tìm điều gì?”, “Điều gì khiến bạn chọn cách đó?”, “Bạn mong đợi điều gì xảy ra sau thao tác này?”. Tránh hỏi “Nút này rất dễ thấy đúng không?” hoặc tự động hướng dẫn ngay khi người tham gia do dự.

### 6.3. Ghi nhận kết quả theo tác vụ

| Quan sát | Cách ghi nhận | Diễn giải thận trọng |
| --- | --- | --- |
| **Hoàn thành** | Hoàn thành độc lập, hoàn thành khi được trợ giúp, không hoàn thành | Thể hiện mức thành công của tác vụ trong điều kiện thử |
| **Đường đi** | Các bước đã thực hiện và nơi quay lại | Chỉ ra giao diện khiến người dùng phải dò tìm |
| **Lỗi sử dụng** | Nhấn nhầm, hiểu sai nhãn, chọn khóa không phù hợp | Cần phân biệt lỗi giao diện và thiếu kiến thức lĩnh vực |
| **Thời gian** | Thời gian từ lúc bắt đầu đến khi hoàn thành hoặc dừng | Dài chưa chắc xấu nếu người dùng đang đánh giá thông tin cẩn thận |
| **Phát biểu** | Ghi nguyên văn câu nói liên quan đến hành vi | Không suy ra tỷ lệ toàn bộ người dùng chỉ từ một lời nói |
| **Cảm nhận sau tác vụ** | Mức khó/dễ, điều gây bối rối, đề xuất của người tham gia | Hữu ích để giải thích, cần đối chiếu với quan sát |

Một số phiên thử với ít người có thể giúp phát hiện **các vấn đề khả dụng nổi bật** trong một nhóm người dùng cụ thể. Tuy nhiên, không có một con số người tham gia cố định bảo đảm “phát hiện đủ mọi vấn đề”. Muốn ước lượng tỷ lệ lỗi, so sánh nhóm người dùng hoặc kiểm định khác biệt định lượng phải thiết kế mẫu và quy mô phù hợp với câu hỏi nghiên cứu.

### 6.4. Kết thúc buổi thử nghiệm

Sau thử nghiệm, hỏi thêm về mục tiêu thật và bối cảnh sử dụng, cảm ơn người tham gia, giải thích phần nào là bản mẫu nếu cần. Khi tổng hợp kết quả, tách riêng **những gì quan sát được**, **câu nói của người tham gia**, **diễn giải của nhóm** và **đề xuất giải pháp**.

Ví dụ:

| Loại thông tin | Ghi nhận |
| --- | --- |
| Quan sát | Người tham gia quay lại danh sách ba lần để kiểm tra khóa nào dành cho người mới |
| Phát biểu | “Mình không biết khóa này có yêu cầu biết Java trước không.” |
| Diễn giải cần kiểm chứng | Thông tin điều kiện đầu vào chưa đủ rõ ở kết quả tìm kiếm |
| Đề xuất có thể thử | Thêm nhãn trình độ và mô tả điều kiện tiên quyết ngay trên thẻ khóa |

Nếu người dùng đề xuất “hãy thêm nút màu đỏ”, hãy hiểu **vấn đề họ muốn giải quyết** trước khi coi màu đỏ là giải pháp bắt buộc. Ý kiến giải pháp là một giả thuyết hữu ích, không tự động là yêu cầu đã được xác nhận.

## 7. Phỏng vấn, khảo sát và phản hồi từ kênh hỗ trợ

### Phỏng vấn khám phá

Phỏng vấn nên khai thác hành vi đã xảy ra và mục tiêu cụ thể. Ví dụ, thay cho “Bạn có dùng tính năng gợi ý khóa học không?”, hãy hỏi “Lần gần nhất bạn chọn một khóa học trực tuyến, bạn tìm và so sánh các khóa như thế nào?”. Có thể đề nghị người dùng kể lại tình huống, tiêu chí lựa chọn và khó khăn họ gặp.

Các câu hỏi quá giả định như “Nếu có hệ thống AI đề xuất khóa học hoàn hảo, bạn có trả tiền không?” thường cho phản hồi ít chắc chắn về hành vi mua thực tế.

### Khảo sát

Khảo sát có thể cung cấp độ bao phủ rộng hơn cho các câu hỏi được thiết kế rõ, nhưng chịu ảnh hưởng của cách tuyển mẫu, tỷ lệ phản hồi, cách đặt câu và người không trả lời. Tránh câu kép như “Tìm kiếm và thanh toán có dễ không?” vì không biết người trả lời đang đánh giá phần nào.

Nếu dùng thang đánh giá, cần mô tả cùng một thang đo cho các nhóm và thời điểm so sánh. Không diễn giải một điểm trung bình đơn lẻ thành “người dùng hài lòng” nếu không biết phân bố câu trả lời hoặc người được hỏi là ai.

### Phản hồi từ hỗ trợ khách hàng

Yêu cầu hỗ trợ, đánh giá ứng dụng và báo lỗi giúp phát hiện trường hợp nghiêm trọng mà analytics có thể bỏ sót. Nên phân loại theo **vấn đề người dùng gặp** (ví dụ “không nhận xác nhận đăng ký”) thay vì chỉ theo bộ phận xử lý (“lỗi email”).

Phản hồi từ một vài người rất khó chịu đáng được xem xét, nhất là khi liên quan thanh toán, bảo mật hoặc tiếp cận; nhưng không thể suy ra mức phổ biến của vấn đề nếu chưa đối chiếu với dữ liệu khác.

## 8. Thử nghiệm thay đổi: bản mẫu, beta và A/B

Không phải giả thuyết nào cũng cần thử nghiệm A/B. Chọn cách kiểm chứng phù hợp với rủi ro, mức sẵn sàng của sản phẩm, số người dùng và loại câu hỏi.

| Cách thử | Ví dụ | Khi nào phù hợp |
| --- | --- | --- |
| **Bản mẫu trên giấy / tương tác** | Thử hai cách trình bày nhãn trình độ khóa học | Cần học về khả năng hiểu trước khi xây chức năng |
| **Thử nghiệm khả dụng** | Quan sát người học chọn khóa với giao diện mới | Cần tìm chỗ vướng, hiểu nguyên nhân thao tác |
| **Phát hành beta có giới hạn** | Mở bộ lọc mới cho nhóm người dùng tự nguyện | Cần xem tính ổn định, lỗi và phản hồi trong môi trường sử dụng |
| **A/B ngẫu nhiên** | So sánh cách hiển thị thông tin khóa giữa nhóm A và B | Cần ước lượng tác động của thay đổi lên chỉ số xác định |
| **Phát hành theo giai đoạn** | Tăng dần tỷ lệ người dùng tiếp cận chức năng | Cần theo dõi rủi ro vận hành và thu phản hồi khi mở rộng |

### 8.1. Thiết kế một thử nghiệm A/B có kỷ luật

Giả sử nhóm muốn kiểm tra việc thêm nhãn trình độ trên thẻ khóa học có giúp người học mở khóa phù hợp hơn không.

1. **Giả thuyết:** Có nhãn trình độ giúp người mới tìm được khóa phù hợp, làm tăng tỷ lệ hoàn thành hành trình lựa chọn khóa.
2. **Biến thể:** A là thẻ hiện tại; B là thẻ có nhãn trình độ và điều kiện tiên quyết rõ ràng.
3. **Đối tượng và phân nhóm:** Phân bổ ngẫu nhiên các đối tượng đủ điều kiện theo một đơn vị nhất quán, thường là người dùng, và giữ biến thể ổn định trong phạm vi thử.
4. **Chỉ số chính:** Xác định trước một kết quả phản ánh mục tiêu, ví dụ tỷ lệ người mới chọn thành công khóa phù hợp theo tiêu chí đã kiểm chứng.
5. **Chỉ số bảo vệ (guardrails):** Theo dõi lỗi, thời gian tải, nhầm lẫn của người dùng, khiếu nại hoặc kết quả bất lợi ở nhóm liên quan.
6. **Kế hoạch phân tích:** Xác định trước điều kiện bắt đầu, thời gian dự kiến, quy mô mẫu cần thiết, cách xử lý trường hợp bỏ dở và điều kiện dừng sớm vì rủi ro.
7. **Kết luận:** Kiểm tra chất lượng phân nhóm và dữ liệu, độ lớn hiệu ứng cùng độ bất định trước khi quyết định triển khai rộng.

**Ngẫu nhiên hóa** giúp giảm nhiều sai lệch giữa các nhóm, nhưng không cứu được thử nghiệm có lỗi đo lường, phân nhóm không ổn định, can thiệp chéo hoặc mẫu không đại diện cho đối tượng cần áp dụng. Việc liên tục nhìn số liệu giữa chừng và tuyên bố thắng ngay khi thấy mức tăng có thể dẫn đến kết luận sai nếu không có quy tắc phân tích phù hợp.

### 8.2. Ví dụ diễn giải kết quả

Một thử nghiệm giả định cho thấy tỷ lệ hoàn thành tác vụ ở nhóm A là **40%** và ở nhóm B là **44%**:

- **Chênh lệch tuyệt đối:** 44% − 40% = **4 điểm phần trăm**.
- **Thay đổi tương đối so với A:** (44% − 40%) / 40% = **10%**.

Hai cách biểu diễn khác nhau; đừng gọi mức tăng “4%” nếu thực chất là tăng 4 **điểm phần trăm**. Quan trọng hơn, hai tỷ lệ đơn lẻ **không đủ để kết luận B tốt hơn một cách đáng tin cậy**. Cần biết số lượng người tham gia, cách phân nhóm, khoảng bất định, hành vi của phân khúc chính, chỉ số bảo vệ và chất lượng dữ liệu.

Nếu chức năng hiện tại gây hại rõ ràng hoặc vi phạm tiêu chuẩn an toàn, bảo mật, tiếp cận, nhóm cần xử lý theo trách nhiệm chất lượng; không dùng A/B để trì hoãn sửa lỗi nghiêm trọng chỉ nhằm đo mức độ tác động.

## 9. Từ phản hồi đến quyết định product backlog

Giá trị của phản hồi thể hiện khi nhóm có thể **ra quyết định tốt hơn**. Không phải mọi câu góp ý đều trở thành một user story. Nên phân loại phát hiện trước khi xếp ưu tiên.

### 9.1. Phân loại phát hiện

| Loại phát hiện | Ví dụ | Hướng xử lý có thể |
| --- | --- | --- |
| Lỗi chức năng hoặc chất lượng nghiêm trọng | Đăng ký thành công nhưng không tạo quyền học | Ưu tiên khắc phục, xác định tác động và kiểm thử hồi quy |
| Trở ngại khả dụng được quan sát | Người mới không phân biệt khóa cơ bản và nâng cao | Thử chỉnh thông tin, điều hướng, cách trình bày |
| Nhu cầu mới có bằng chứng | Người học thường muốn lưu khóa để học sau | Xem xét user story / increment mới theo giá trị |
| Ý kiến về giải pháp chưa rõ nhu cầu | “Cần chatbot ở mọi trang” | Khám phá tác vụ và vấn đề trước khi xây giải pháp |
| Dữ liệu mâu thuẫn hoặc chưa đủ | Một nhóm đánh giá cao, nhóm khác ít sử dụng | Tách phân khúc, kiểm tra tracking, nghiên cứu bổ sung |

### 9.2. Viết user story dựa trên vấn đề

**Phát hiện:** Trong buổi thử nghiệm, người mới thường quay lại danh sách để tìm điều kiện đầu vào của khóa học.

**User story đề xuất:**

> Là người mới học Java, tôi muốn nhìn thấy trình độ và điều kiện tiên quyết ngay trong kết quả tìm kiếm, để chọn khóa phù hợp mà không phải mở nhiều trang để đoán.

**Một số tiêu chí chấp nhận:**

- Thẻ kết quả hiển thị trình độ và điều kiện tiên quyết khi khóa có thông tin này.
- Với dữ liệu chưa xác định, giao diện không tự suy đoán trình độ; có cách hiển thị hoặc xử lý thống nhất.
- Nội dung có thể đọc và thao tác được trên các kích thước màn hình mục tiêu và bằng công nghệ hỗ trợ đã chọn để kiểm thử.
- Thông tin trên thẻ nhất quán với trang chi tiết; cập nhật dữ liệu không làm sai lệch kết quả tìm kiếm.

**Giả thuyết giá trị:** Người mới nhận biết khóa phù hợp nhanh hơn và ít chọn nhầm khóa. Sau khi giao increment, nhóm tiếp tục quan sát tỷ lệ hoàn thành tác vụ và các phản hồi liên quan.

Không nên viết tiêu chí chấp nhận kiểu “người dùng phải hài lòng 100%” hoặc khẳng định một chỉ số sản phẩm chắc chắn sẽ tăng. Tiêu chí chấp nhận mô tả **hành vi và chất lượng cần đúng**, còn giả thuyết outcome cần kiểm chứng sau khi người dùng trải nghiệm.

### 9.3. Ưu tiên với bối cảnh và độ tin cậy của bằng chứng

Khi sắp xếp backlog, Product Owner và các bên liên quan có thể cân nhắc **giá trị kỳ vọng, mức tác động đến người dùng, rủi ro, chi phí, sự cấp bách, khả năng kiểm chứng và mức bất định của thông tin**.

Ví dụ, lỗi khiến học viên đã thanh toán không truy cập được khóa học thường đáng xử lý trước một yêu cầu đổi màu nút, kể cả khi yêu cầu đổi màu được nhiều người bình chọn hơn. Một thay đổi nhỏ, chi phí thấp, có khả năng kiểm chứng rõ có thể được thử trước một sáng kiến lớn nhưng chưa biết có ai dùng hay không.

Phản hồi không thay thế trách nhiệm quyết định sản phẩm. Trong Scrum, Product Owner chịu trách nhiệm quản lý hiệu quả Product Backlog; nhà phát triển và các bên liên quan cùng cung cấp bằng chứng và kiến thức cần thiết.

## 10. Ví dụ xuyên suốt: cải thiện hành trình tìm và đăng ký khóa học

Giả sử nhóm xây dựng nền tảng học trực tuyến cho người đang chuyển nghề sang lập trình phần mềm.

### Tình huống ban đầu

Sau khi giao increment tìm khóa học, nhóm thấy từ dữ liệu sử dụng rằng nhiều người xem trang kết quả nhưng không mở khóa chi tiết. Bộ phận hỗ trợ cũng nhận các câu hỏi: “Khóa nào dành cho người chưa biết lập trình?” và “Học Java cơ bản có cần học thuật toán trước không?”.

Nhóm chưa biết nguyên nhân là **kết quả tìm kiếm thiếu phù hợp**, **thông tin khóa khó hiểu** hay **người học chỉ muốn khảo sát thị trường**.

### Kế hoạch học hỏi theo từng bước

| Bước | Hoạt động | Quyết định có thể rút ra |
| --- | --- | --- |
| 1. Xác thực tín hiệu | Kiểm tra định nghĩa sự kiện và phễu; phân nhóm người học mới và quay lại | Vấn đề thực sự xuất hiện ở nhóm nào? |
| 2. Khám phá | Phỏng vấn một số người học mới về lần gần nhất họ chọn khóa | Họ dựa vào điều kiện nào để chọn? |
| 3. Quan sát | Cho người học thực hiện tác vụ chọn khóa trên giao diện hiện tại | Họ hiểu nhãn khóa và bộ lọc ra sao? |
| 4. Thử trước khi xây lớn | Đưa nhãn trình độ/điều kiện tiên quyết vào bản mẫu | Phương án có giảm nhầm lẫn rõ rệt trong tác vụ thử không? |
| 5. Giao increment nhỏ | Thêm thông tin đã kiểm chứng vào thẻ khóa, tích hợp và kiểm thử | Người dùng có thể sử dụng phần bổ sung an toàn không? |
| 6. Theo dõi sau phát hành | Quan sát hành trình, phản hồi hỗ trợ và nhóm thiết bị | Kết quả có cải thiện, có hệ quả bất lợi nào? |

### Một kết quả nghiên cứu giả định

Sáu người học mới tham gia thử nghiệm khám phá trên bản mẫu. Bốn người trước đó nói không rõ “Java Foundation” và “Java Core” khác nhau như thế nào; sau khi xem nhãn trình độ và điều kiện đầu vào, họ giải thích chính xác hơn lý do chọn khóa.

Kết quả này cho thấy **một vấn đề khả dụng đáng điều tra và một phương án có triển vọng trong nhóm thử**, không chứng minh “67% toàn bộ người dùng gặp vấn đề” hoặc “thẻ mới chắc chắn làm doanh thu tăng”. Nhóm có thể dùng kết quả để quyết định triển khai giới hạn và tiếp tục quan sát thực tế.

### Khi bằng chứng trái chiều

Giả sử sau phát hành, người dùng tương tác với nhãn trình độ nhiều hơn nhưng tỷ lệ đăng ký không tăng. Đừng tự động coi thay đổi vô ích hoặc thành công:

- Có thể nhãn giúp **tránh đăng ký sai khóa**, nên tỷ lệ đăng ký không tăng nhưng tỷ lệ hoàn thành khóa về sau tốt hơn.
- Có thể người học hiểu khóa không phù hợp và quyết định không đăng ký; đây có thể là quyết định tốt cho họ.
- Có thể chất lượng danh mục khóa hoặc giá mới là yếu tố chính.
- Cũng có thể tracking không phản ánh chính xác ai đã tiếp xúc với nhãn.

Nhóm cần quay về **mục tiêu người dùng** và xác định kết quả dài hạn có ý nghĩa. Tránh tối ưu một lượt nhấp khiến người học đăng ký sai khóa chỉ để tăng con số chuyển đổi trước mắt.

## 11. Đưa phản hồi vào Scrum, Kanban và XP

### Scrum

Scrum tạo nhịp kiểm tra và thích ứng qua Sprint. Một Increment đáp ứng Definition of Done có thể là cơ sở để nhận phản hồi hữu ích, và Sprint Review tạo cơ hội cho Scrum Team cùng các bên liên quan kiểm tra kết quả, trao đổi thay đổi bối cảnh và điều chỉnh Product Backlog.

Nhóm có thể thử khả dụng trước khi triển khai, dùng bản mẫu trong quá trình làm rõ user story và thu thập tín hiệu khi Increment được người dùng tiếp cận. **Sprint Review không phải nơi duy nhất được phép nhận phản hồi** và hoàn tất Sprint không bắt buộc đồng nghĩa với phát hành công khai ngay lúc đó.

### Kanban

Với Kanban, nhóm có thể tiếp nhận phản hồi liên tục và biểu diễn rõ các hạng mục như “cần nghiên cứu”, “đang xác thực”, “đang triển khai” hoặc “đang đánh giá kết quả”, tùy cách tổ chức dòng công việc. Việc quản lý WIP, theo dõi thời gian hoàn tất và điều chỉnh chính sách kéo việc giúp các phát hiện có giá trị không bị chôn trong hàng đợi kéo dài.

Không nên tạo quá nhiều đầu việc nghiên cứu cùng lúc. Nhóm cần ưu tiên câu hỏi quan trọng và hoàn tất vòng học hỏi trước khi mở thêm các nghiên cứu thiếu người theo dõi.

### Extreme Programming (XP)

XP nhấn mạnh phản hồi nhanh, thiết kế có thể thay đổi, kiểm thử tự động, tích hợp liên tục và phát hành nhỏ. Những thực hành này giúp nhóm nhanh chóng đưa ra một increment có chất lượng đủ tốt để kiểm chứng giả thuyết. Đại diện khách hàng sẵn sàng trao đổi và các ví dụ kiểm thử chấp nhận rõ ràng giúp kết nối phát hiện từ người dùng với hành vi phần mềm phải đáp ứng.

**Điểm chung:** Phản hồi về sản phẩm cho biết nên xây hoặc điều chỉnh điều gì; phản hồi về cách làm việc giúp nhóm cải thiện khả năng thu thập, hiểu và sử dụng thông tin đó.

## 12. Quyền riêng tư, tiếp cận và trách nhiệm với người tham gia

Thu thập dữ liệu tốt cần **chính đáng, minh bạch và tiết chế**. Mục đích học hỏi về sản phẩm không tự cho phép nhóm thu thập mọi hành vi hoặc dữ liệu cá nhân có thể lấy được.

- **Mục đích rõ ràng:** Chỉ ghi dữ liệu cần thiết cho câu hỏi sản phẩm và vận hành đã xác định.
- **Thông báo và cơ sở xử lý phù hợp:** Tuân thủ quy định pháp luật, chính sách tổ chức và cơ chế lựa chọn/đồng ý nơi cần thiết; không ngầm xem mọi dữ liệu có thể truy cập là được phép dùng cho phân tích.
- **Giảm dữ liệu nhạy cảm:** Tránh gửi nội dung học tập riêng, thông tin thanh toán hoặc dữ liệu trực tiếp nhận dạng vào công cụ phân tích nếu không cần; hạn chế quyền truy cập và thời hạn giữ dữ liệu.
- **Đối xử đúng với người tham gia thử nghiệm:** Thông báo mục tiêu, điều gì được ghi nhận, quyền dừng; không gây sức ép hoặc khiến họ cảm thấy bản thân bị kiểm tra năng lực.
- **Đại diện và tiếp cận:** Khi phù hợp, đưa vào nghiên cứu người sử dụng thiết bị khác nhau, có nhu cầu tiếp cận khác nhau, người mới và người có kinh nghiệm. Không chỉ thử với nhân viên nội bộ quen giao diện.
- **Không dùng thủ thuật gây hại:** Không tối ưu chỉ số chuyển đổi bằng cách đánh lừa người dùng, che giấu chi phí hoặc tạo ra thao tác khó hủy.
- **Ưu tiên khắc phục rủi ro:** Nếu phát hiện lỗi bảo mật, mất dữ liệu, cản trở tiếp cận nghiêm trọng hoặc tác động bất lợi rõ ràng, nhóm cần xử lý theo mức độ khẩn cấp, không chờ nghiên cứu tiếp chỉ để có một kết quả A/B.

Mã hóa định danh hoặc gộp dữ liệu giúp giảm rủi ro nhưng không tự bảo đảm thông tin đã hoàn toàn ẩn danh. Việc truy vấn nhiều thuộc tính kết hợp có thể làm tăng khả năng nhận dạng; cần quản lý quyền truy cập và cách báo cáo.

## 13. Những sai lầm thường gặp khi thu thập phản hồi

**1. Chỉ hỏi người dùng muốn tính năng gì.** Người dùng có thể mô tả giải pháp theo những công cụ họ đã biết, trong khi vấn đề gốc khác đi. Hãy hỏi mục tiêu, bối cảnh, lần sử dụng thực tế và quan sát tác vụ.

**2. Xem dữ liệu analytics là nguyên nhân.** Tỷ lệ bỏ dở cao ở bước thanh toán cho biết nơi cần điều tra, chưa chứng minh do màu nút hay quy tắc nghiệp vụ.

**3. Lấy ý kiến vài người rồi suy ra tỷ lệ toàn hệ thống.** Các buổi thử định tính giúp phát hiện vấn đề và giả thuyết; ước lượng tỷ lệ cần thiết kế mẫu thống kê phù hợp.

**4. Chỉ nghiên cứu người dùng hiện tại.** Những người không thể đăng ký, đã rời bỏ hoặc chưa từng thành công có thể có vấn đề mà dữ liệu người dùng hoạt động không phản ánh.

**5. Dẫn dắt tác vụ thử nghiệm.** Chỉ người tham gia vị trí nút sẽ che khuất vấn đề tìm kiếm và hiểu giao diện; hãy giao mục tiêu gần với đời thực.

**6. Chạy thử nghiệm A/B không có giả thuyết và quy tắc dừng.** Xem nhiều chỉ số rồi chọn chỉ số tăng đẹp nhất dễ tạo kết luận sai. Cần xác định trước câu hỏi, chỉ số chính, guardrails và kế hoạch phân tích.

**7. Chỉ theo dõi số lượt nhấp.** Chỉ số tương tác có thể tăng trong khi lỗi, thời gian hoàn thành tác vụ hoặc tỷ lệ học thành công xấu đi. Nên kết hợp chỉ số kết quả và chất lượng.

**8. Thu thập dữ liệu nhưng không dẫn tới quyết định.** Dashboard và biên bản phỏng vấn chỉ có giá trị khi nhóm đưa ra hành động cụ thể, người chịu trách nhiệm và thời điểm kiểm tra lại.

**9. Coi mọi yêu cầu phản hồi là có ưu tiên ngang nhau.** Cần xét mức độ nghiêm trọng, phạm vi ảnh hưởng, mục tiêu sản phẩm, chi phí, rủi ro và độ tin cậy của bằng chứng.

**10. Thay đổi quá nhiều yếu tố cùng lúc.** Khi vừa thay thuật toán tìm kiếm, giá khóa học, nhãn trình độ và luồng đăng ký, rất khó biết yếu tố nào gây ra kết quả mới. Nếu phải thay đồng thời, cần ghi nhận giới hạn suy luận.

## 14. Bài tập tình huống: phản hồi sau khi phát hành tính năng đăng ký

Một nhóm xây dựng nền tảng học trực tuyến vừa phát hành chức năng đăng ký khóa học. Trong tuần đầu, nhóm thấy:

- 1.200 người duy nhất truy cập trang chi tiết khóa.
- 480 người bắt đầu đăng ký.
- 300 người hoàn thành đăng ký.
- Bộ phận hỗ trợ nhận nhiều câu hỏi “Tôi đã đăng ký thành công chưa?”.
- Một số người dùng điện thoại nói họ không nhìn thấy thông báo xác nhận sau khi bấm nút.

Đây là **dữ liệu giả định cho bài tập**. Giả sử các sự kiện được ghi chính xác và các nhóm ở bước sau đều thuộc tập người của bước trước.

### Câu hỏi

1. Tính tỷ lệ **bắt đầu đăng ký trên lượt xem chi tiết**, tỷ lệ **hoàn thành trên số bắt đầu** và tỷ lệ **hoàn thành trên lượt xem chi tiết**.
2. Nêu ít nhất ba giả thuyết giải thích vì sao nhiều người bắt đầu nhưng chưa hoàn thành.
3. Chọn một phương pháp nghiên cứu định tính và mô tả tác vụ thử nghiệm không dẫn dắt.
4. Đề xuất một thay đổi nhỏ có thể thử, kèm tiêu chí chấp nhận và tín hiệu cần theo dõi sau khi giao.
5. Tại sao không nên kết luận ngay rằng “chỉ cần làm nút Đăng ký lớn hơn”?

### Gợi ý đối chiếu

**Câu 1:** Tỷ lệ bắt đầu trên lượt xem chi tiết là **480 / 1.200 = 40%**; tỷ lệ hoàn thành trên số bắt đầu là **300 / 480 = 62,5%**; tỷ lệ hoàn thành trên lượt xem chi tiết là **300 / 1.200 = 25%**.

**Câu 2:** Những giả thuyết hợp lý gồm lỗi khi gửi yêu cầu, thông báo xác nhận khó nhận biết trên điện thoại, người dùng chưa hiểu điều kiện đăng ký, thời gian xử lý dài hoặc người dùng đổi ý. Không thể chọn nguyên nhân chỉ từ ba con số.

**Câu 3:** Có thể tổ chức usability testing với người dùng di động mục tiêu. Giao nhiệm vụ: “Bạn muốn đăng ký khóa này để bắt đầu học tối nay. Hãy thực hiện đến lúc bạn tin rằng mình đã đăng ký xong.” Quan sát người dùng có nhận ra trạng thái xác nhận, có bấm lại hay thoát giữa chừng không.

**Câu 4:** Nếu quan sát cho thấy thông báo xác nhận khó thấy, nhóm có thể thử màn hình xác nhận rõ ràng và trạng thái nút phù hợp khi đang xử lý. Tiêu chí chấp nhận gồm: chỉ báo thành công đúng khi đăng ký thực sự thành công, lỗi được thông báo rõ, thao tác lặp không tạo đăng ký trùng và giao diện hoạt động trên thiết bị mục tiêu. Theo dõi tỷ lệ hoàn thành, lỗi gửi yêu cầu, số lượt bấm lặp và câu hỏi hỗ trợ sau phát hành.

**Câu 5:** Dữ liệu hiện tại chưa biết có phải nút khó nhìn hay không; một số người đã bấm bắt đầu nhưng không hoàn tất, nên vấn đề có thể nằm ở bước xử lý hoặc xác nhận sau đó. Cần kiểm chứng nguyên nhân trước khi đầu tư vào một giải pháp cụ thể.

### Bài tập mở rộng

Hãy lập một bảng nhỏ cho hai nhóm **người dùng điện thoại** và **người dùng máy tính** gồm: số người bắt đầu, số người hoàn thành, tỷ lệ hoàn thành và số lỗi đăng ký. Nếu hai nhóm khác biệt lớn, bạn sẽ kiểm tra điều gì về tracking, quy trình, tốc độ mạng và đặc điểm người dùng trước khi kết luận nguyên nhân?

## 15. Danh sách kiểm tra trước khi thu thập và sử dụng phản hồi

Trước khi mở một nghiên cứu hoặc công cụ đo lường, nhóm có thể tự hỏi:

1. **Mục tiêu:** Quyết định sản phẩm nào cần bằng chứng? Giá trị nào cho người dùng đang được xem xét?
2. **Đối tượng:** Ai là người dùng mục tiêu? Có nhóm nào quan trọng nhưng đang bị thiếu trong dữ liệu?
3. **Phương pháp:** Cần quan sát hành vi, hỏi bối cảnh, thử khả dụng hay kiểm chứng tác động có kiểm soát?
4. **Đo lường:** Sự kiện, mẫu nghiên cứu, thời gian, cách tính chỉ số và dấu hiệu chất lượng đã được định nghĩa chưa?
5. **Tin cậy và đạo đức:** Dữ liệu có chính xác và được thu thập hợp lệ không? Người tham gia có được đối xử phù hợp không?
6. **Diễn giải:** Đâu là sự thật quan sát được, đâu là giả thuyết, đâu là giới hạn suy luận?
7. **Quyết định:** Nhóm sẽ xây, sửa, hoãn, dừng hay nghiên cứu tiếp điều gì? Ai có quyền ưu tiên và xác nhận?
8. **Học tiếp:** Sau khi giao phần tăng dần, khi nào nhóm kiểm tra tác động và tác dụng phụ?

**Ghi nhớ:** Agile khuyến khích giao sản phẩm có giá trị sớm để học hỏi từ thực tế. **Dữ liệu sử dụng cho thấy hành vi; thử nghiệm và phỏng vấn giúp hiểu bối cảnh; thử nghiệm có kiểm soát có thể kiểm tra tác động; product backlog biến việc học thành quyết định.** Giá trị không nằm ở việc thu thập thật nhiều phản hồi, mà ở khả năng dùng bằng chứng đủ tin cậy để giúp người dùng đạt mục tiêu tốt hơn sau mỗi vòng phát triển.
