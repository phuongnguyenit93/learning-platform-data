# Phân biệt thực hiện hoạt động Agile với thay đổi cách ra quyết định

Một nhóm có thể tổ chức Sprint Planning, Daily Scrum, Sprint Review và Retrospective đều đặn, duy trì bảng Kanban đẹp mắt, viết user story đúng mẫu, nhưng vẫn phát triển sản phẩm theo những quyết định đã được chốt cứng từ nhiều tháng trước. Khi người dùng phản hồi rằng một tính năng không giải quyết vấn đề, nhóm vẫn phải hoàn thành toàn bộ danh sách vì “đã cam kết trong kế hoạch”. Nhóm đó **đang thực hiện các hoạt động thường gắn với Agile**, nhưng chưa chắc đã **làm việc theo tư duy Agile**.

Sự khác biệt quan trọng nằm ở câu hỏi: **Thông tin mới có thực sự thay đổi lựa chọn tiếp theo của nhóm hay không?** Một buổi họp, bảng công việc hoặc bản phát hành ngắn chỉ tạo ra giá trị Agile khi nó giúp những người có trách nhiệm nhìn rõ thực tế, cân nhắc đánh đổi và điều chỉnh hành động kịp thời.

Trong nền tảng Agile, chủ đề này kết nối trực tiếp với các giá trị cộng tác, phần mềm hoạt động được, phản hồi sớm, giao sản phẩm tăng dần và cải tiến liên tục. Những thực hành như Scrum, Kanban và Extreme Programming (XP) là phương tiện hỗ trợ các giá trị ấy; bản thân việc áp dụng thực hành chưa chứng minh rằng cách ra quyết định đã thay đổi.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **hoạt động**, **đầu ra**, **quyết định** và **kết quả** trong một chu trình phát triển phần mềm.
2. Nhận ra dấu hiệu “Agile trên hình thức” và dấu hiệu một nhóm thực sự sử dụng phản hồi để điều chỉnh mục tiêu, ưu tiên, phạm vi và cách làm.
3. Giải thích mỗi thực hành phổ biến của Scrum, Kanban và XP nên giúp đưa ra hoặc cải thiện quyết định nào.
4. Thiết kế vòng phản hồi, quyền quyết định, tiêu chí đánh giá và cách ghi nhận thay đổi cho một tình huống thực tế.
5. Đánh giá sự tiến bộ bằng giá trị mang lại, chất lượng và khả năng thích ứng, thay vì chỉ đếm số nghi thức đã thực hiện.

## 1. Hai lớp khác nhau của việc “làm Agile”

**Hoạt động Agile** là hành vi quan sát được: họp ngắn mỗi ngày, chia công việc thành iteration, viết backlog, cập nhật trạng thái trên bảng, demo sản phẩm, tổ chức retrospective, viết kiểm thử tự động. Các hoạt động này tạo cơ hội phối hợp và học hỏi.

**Thay đổi cách ra quyết định** là thay đổi cơ chế lựa chọn công việc và hành động: ai có quyền quyết định, dựa trên bằng chứng nào, quyết định được kiểm tra khi nào, điều gì có thể thay đổi, và nhóm sẽ làm gì khi giả định ban đầu không còn đúng.

Hai lớp này liên quan chặt chẽ nhưng không đồng nhất:

| Khía cạnh | Chỉ thực hiện hoạt động | Thực sự thay đổi cách ra quyết định |
|---|---|---|
| Lập kế hoạch | Chia kế hoạch năm thành các Sprint và giữ nguyên toàn bộ danh sách | Xác định hướng đi, ưu tiên phần chưa chắc chắn, cập nhật kế hoạch khi có bằng chứng mới |
| Daily Scrum | Mỗi người lần lượt báo cáo đã làm gì cho người quản lý | Các thành viên cùng đánh giá tiến độ hướng tới Sprint Goal, phối hợp và điều chỉnh kế hoạch trong ngày |
| Sprint Review hoặc demo | Trình diễn những chức năng đã hoàn tất để “được ký duyệt” | Kiểm tra Increment với người liên quan; học điều gì có ích và điều chỉnh Product Backlog |
| Backlog | Danh sách yêu cầu bất biến được gắn nhãn user story | Danh sách được làm rõ, sắp xếp lại hoặc loại bỏ theo mục tiêu và điều học được |
| Kanban | Các thẻ di chuyển qua cột To do–Doing–Done | Dữ liệu về tồn đọng, tắc nghẽn và thời gian hoàn tất dẫn đến quyết định giới hạn việc đang làm, tháo gỡ vướng mắc |
| Retrospective | Mọi người kể điều tốt, điều chưa tốt; lần sau lặp lại như cũ | Nhóm chọn một thay đổi có thể thử, có người theo dõi và có thời điểm kiểm chứng |
| Đo lường | Báo cáo số story point, số ticket hoặc số buổi họp | Sử dụng chỉ số phù hợp để nhận biết giá trị, độ tin cậy, chất lượng và khả năng dự báo |

Một nhóm có thể **bắt đầu** bằng việc thiết lập hoạt động trước khi quen với lối tư duy mới. Điều đó bình thường. Vấn đề xuất hiện khi các hoạt động trở thành đích đến và nhóm không còn tự hỏi chúng giúp ra quyết định gì.

### 1.1. Hoạt động, đầu ra, quyết định, kết quả

Bốn khái niệm này rất dễ bị trộn lẫn:

- **Hoạt động (activity):** điều nhóm làm, chẳng hạn phỏng vấn năm người dùng hoặc tổ chức Sprint Review.
- **Đầu ra (output):** thứ nhóm tạo ra, chẳng hạn một bản Increment có thể sử dụng, năm user story hoặc mười ticket hoàn tất.
- **Quyết định (decision):** lựa chọn được đưa ra dựa trên điều đã biết, chẳng hạn dừng phát triển tính năng A và thử cách giải quyết B.
- **Kết quả (outcome):** thay đổi có ý nghĩa đối với người dùng, khách hàng hoặc hệ thống, chẳng hạn người dùng hoàn tất đăng ký nhanh hơn, ít lỗi nghiêm trọng hơn.

Ví dụ: “Đã demo chức năng tìm kiếm” là một hoạt động; “đã phát hành bộ lọc mới” là đầu ra; “ưu tiên sửa độ chính xác kết quả trước khi thêm bộ lọc” là quyết định; “người dùng tìm thấy tài liệu cần thiết thường xuyên hơn” là kết quả. Một đầu ra có thể hoạt động đúng kỹ thuật mà vẫn chưa tạo ra kết quả mong muốn.

### 1.2. Vòng phản hồi là trung tâm

Agile sử dụng cách tiếp cận thực nghiệm: **minh bạch thông tin, kiểm tra thực tế, rồi thích ứng**. Không phải mọi quyết định đều cần thử nghiệm phức tạp; điều cốt lõi là các giả định quan trọng được đem ra đối chiếu với bằng chứng trong thời gian đủ ngắn.

~~~mermaid
flowchart LR
    A["Mục tiêu và giả định"] --> B["Chọn bước nhỏ có thể kiểm chứng"]
    B --> C["Xây dựng và đưa ra sử dụng"]
    C --> D["Quan sát phản hồi, dữ liệu và rủi ro"]
    D --> E{"Giả định còn phù hợp?"}
    E -->|Có bằng chứng ủng hộ| F["Tiếp tục hoặc mở rộng"]
    E -->|Có bằng chứng trái chiều| G["Đổi ưu tiên, giải pháp hoặc kế hoạch"]
    E -->|Chưa đủ bằng chứng| H["Thiết kế bước kiểm chứng tiếp theo"]
    F --> A
    G --> A
    H --> B
~~~

Vòng phản hồi có thể kéo dài vài giờ đối với một lỗi đang ảnh hưởng người dùng, vài ngày đối với luồng thao tác nhỏ hoặc vài tuần đối với giả thuyết sản phẩm lớn. **Sprint ngắn chưa chắc tạo phản hồi nhanh** nếu công việc chỉ được tích hợp, kiểm thử hoặc đưa đến người dùng sau nhiều tháng.

Một câu hỏi kiểm tra hữu ích là: *“Nếu kết quả quan sát được trái với giả định, quyết định cụ thể nào sẽ khác đi?”* Nếu câu trả lời luôn là “không có gì thay đổi vì lộ trình đã khóa”, vòng phản hồi hiện tại có thể chỉ mang tính nghi thức.

## 2. Sáu thay đổi cốt lõi trong cơ chế quyết định

### 2.1. Từ bàn giao phạm vi cố định sang hướng đến mục tiêu

Trong cách quản lý chỉ xoay quanh đầu ra, thành công dễ bị hiểu là giao đủ các hạng mục ban đầu. Trong Agile, nhóm vẫn cần cam kết, nhưng cam kết nên gắn với **mục tiêu có ý nghĩa**, chất lượng và sự minh bạch về dự báo. Phạm vi chi tiết có thể là biến số điều chỉnh để phục vụ mục tiêu.

Ví dụ, mục tiêu “giúp khách hàng tự hoàn thành thiết lập tài khoản” tốt hơn một danh sách rời rạc gồm “làm màn hình chào mừng, thêm ba biểu mẫu và tạo video hướng dẫn”. Nhóm có thể phát hiện một thông báo lỗi rõ ràng mang lại cải thiện lớn hơn cả video mới. Khi đó, điều chỉnh phạm vi là phản ứng hợp lý đối với thông tin mới.

Điều này **không có nghĩa** mục tiêu, ngân sách, ngày ra mắt hay nghĩa vụ pháp lý có thể đổi tùy hứng. Agile yêu cầu làm rõ các ràng buộc không thể thương lượng và phần nào còn có thể lựa chọn.

### 2.2. Từ ý kiến cấp bậc sang bằng chứng và giả thuyết

Kinh nghiệm và nhận định của lãnh đạo vẫn có vai trò, nhưng cần được diễn đạt thành giả thuyết có thể kiểm tra:

> Chúng tôi tin rằng đơn giản hóa bước xác minh email sẽ giúp người dùng mới hoàn tất thiết lập nhiều hơn. Chúng tôi sẽ quan sát tỷ lệ hoàn tất trong bảy ngày sau đăng ký, đồng thời theo dõi lỗi bảo mật và tỷ lệ yêu cầu hỗ trợ.

Một giả thuyết tốt nói rõ **ai** gặp vấn đề, **thay đổi** nào được đề xuất, **tác động** mong đợi và **dấu hiệu** có thể xác nhận hoặc bác bỏ. Các chỉ số kiểm soát rủi ro (guardrail) giúp nhóm tránh cải thiện một con số bằng cách gây hại ở nơi khác.

Không chỉ dữ liệu định lượng mới là bằng chứng: quan sát người dùng, phỏng vấn, phản ánh từ hỗ trợ khách hàng, lỗi sản xuất, khả năng tiếp cận và kiến thức kỹ thuật đều có giá trị. Cần xem xét giới hạn mẫu và bối cảnh, tránh kết luận nguyên nhân chỉ từ một biến động ngẫu nhiên.

### 2.3. Từ quyết định lớn, muộn và khó đảo ngược sang quyết định nhỏ, sớm

Nhóm không cần đợi giải xong toàn bộ bài toán mới bắt đầu. Khi rủi ro cho phép, hãy chọn bước nhỏ tạo ra thông tin hữu ích: một bản prototype, một lát cắt chức năng chạy xuyên suốt, một thử nghiệm có phạm vi giới hạn hoặc một cải tiến quy trình trong một tuần.

Chi phí thay đổi càng thấp, nhóm càng có cơ hội học và điều chỉnh. Các thực hành kỹ thuật như kiểm thử tự động, tích hợp liên tục, chia thay đổi nhỏ và triển khai an toàn hỗ trợ điều này. Nhưng với quyết định khó đảo ngược — ví dụ di chuyển dữ liệu nhạy cảm hoặc thay đổi hợp đồng — vẫn cần thẩm định, kiểm soát và phê duyệt thích hợp.

### 2.4. Từ xin phép cho mọi bước sang quyền quyết định rõ ràng

Trao quyền không đồng nghĩa “ai cũng có thể quyết định mọi thứ”. Nhóm cần biết:

- **Ai chịu trách nhiệm về giá trị và thứ tự ưu tiên?** Trong Scrum, Product Owner chịu trách nhiệm tối đa hóa giá trị sản phẩm và quản lý Product Backlog hiệu quả.
- **Ai chịu trách nhiệm tổ chức cách thực hiện công việc?** Trong Scrum, Developers tự quản lý kế hoạch và cách tạo Increment đạt Definition of Done.
- **Ai cung cấp bằng chứng và ràng buộc?** Người dùng, các bên liên quan, chuyên gia vận hành, bảo mật, pháp lý hoặc kiến trúc có thể đưa ra thông tin quan trọng.
- **Khi có xung đột, ai quyết định và theo tiêu chí nào?** Cần nói rõ trước khi xung đột xảy ra, thay vì để mọi quyết định phải chờ người có chức danh cao nhất.

Một nhóm phối hợp tốt không nhất thiết phải đồng thuận tuyệt đối. Quyền quyết định rõ và trách nhiệm giải trình rõ giúp giảm thời gian chờ, đồng thời giữ được các ranh giới an toàn.

### 2.5. Từ tối ưu mức bận rộn sang tối ưu dòng giá trị

“Mọi người đều có việc” không bảo đảm khách hàng nhận giá trị nhanh hơn. Khi nhóm bắt đầu quá nhiều việc cùng lúc, công việc nằm chờ, chuyển giao liên tục và khó hoàn tất. Cách nghĩ theo dòng giá trị khuyến khích nhóm nhìn toàn bộ quá trình từ nhu cầu đến kết quả, giới hạn công việc đang thực hiện (work in progress, WIP) khi phù hợp và chủ động tháo tắc nghẽn.

Quyết định có thể là: “Hôm nay hai thành viên cùng hoàn tất một ticket bị chặn kiểm thử; chưa bắt đầu thêm ticket mới”. Từ góc nhìn cá nhân, một người có thể đang “không bận hết công suất”; từ góc nhìn toàn hệ thống, lựa chọn đó giúp hoàn thành và nhận phản hồi sớm hơn.

### 2.6. Từ rút kinh nghiệm cho có sang học tập có trách nhiệm

Retrospective chỉ có tác dụng khi nó tạo ra một thử nghiệm cải tiến cụ thể. Ví dụ: “Trong hai tuần tới, các yêu cầu thay đổi API phải có ví dụ dữ liệu vào/ra trước khi bắt đầu; theo dõi số lần làm lại vì hiểu sai hợp đồng”. Nhóm kiểm tra xem thử nghiệm có giúp ích không, rồi giữ, sửa hoặc bỏ nó.

Một thay đổi tốt cần có **người theo dõi, thời hạn kiểm tra và dấu hiệu thành công**. Không nhất thiết phải tạo thêm quy trình; đôi khi quyết định quan trọng nhất là loại bỏ một bước không còn tạo giá trị.

## 3. Nhìn từng thực hành qua quyết định mà nó hỗ trợ

Scrum, Kanban và XP giải quyết những khía cạnh khác nhau của công việc. Không có quy tắc “phải áp dụng đủ cả ba mới là Agile”. Điều cần hiểu là **mỗi thực hành giúp quan sát, phối hợp hoặc quyết định điều gì**.

### 3.1. Scrum: các sự kiện phải tạo ra cơ hội kiểm tra và thích ứng

| Thực hành | Dấu hiệu làm vì nghi thức | Quyết định hoặc điều chỉnh nên được hỗ trợ |
|---|---|---|
| Product Goal và Product Backlog | Liệt kê tất cả yêu cầu đã được duyệt, không nêu mục đích | Làm rõ mục tiêu dài hạn của sản phẩm; sắp xếp lại các hạng mục dựa trên giá trị, rủi ro và điều mới học |
| Sprint Planning | Lấp đầy Sprint theo năng lực ước lượng, không ai giải thích được mục tiêu | Chọn Sprint Goal có ý nghĩa; Developers dự báo công việc có thể làm và lập kế hoạch thực hiện |
| Daily Scrum | Báo cáo từng cá nhân cho người giám sát, không xử lý vướng mắc | Developers kiểm tra tiến độ hướng tới Sprint Goal và thích ứng Sprint Backlog, thống nhất cách phối hợp ngay |
| Sprint Review | Demo một chiều, nhận lời khen rồi chuyển sang Sprint mới | Scrum Team và stakeholders kiểm tra kết quả Sprint, môi trường sử dụng và các lựa chọn tiếp theo; Product Backlog có thể được điều chỉnh |
| Sprint Retrospective | Lặp lại danh sách “cần giao tiếp tốt hơn” qua nhiều Sprint | Chọn cải tiến cụ thể để tăng chất lượng và hiệu quả, kiểm tra tác động ở Sprint sau |
| Definition of Done | Nhãn “Done” nghĩa là lập trình viên hoàn thành phần code của mình | Cùng hiểu thế nào là Increment đạt chất lượng; phát hiện sớm công việc chưa thật sự hoàn tất |

**Lưu ý quan trọng:** Trong Scrum, Sprint Goal tạo ra sự tập trung và linh hoạt về cách đạt mục tiêu. Nếu học được điều mới trong Sprint, phạm vi có thể được làm rõ hoặc thương lượng lại với Product Owner mà không làm mất Sprint Goal. Không được âm thầm hạ tiêu chuẩn Definition of Done để “đạt cam kết”. Sprint Review cũng không phải một cổng phê duyệt bắt buộc để phát hành sản phẩm.

**Một cuộc Daily Scrum chuyển đổi quyết định ra sao?**

Giả sử Sprint Goal là “người dùng có thể đặt lại mật khẩu thành công”. Sáng thứ Ba, API gửi email có nguy cơ trễ hai ngày.

- Nếu chỉ báo cáo trạng thái: từng người nói mình đã hoàn thành bao nhiêu phần trăm; nhóm tiếp tục làm việc riêng lẻ.
- Nếu quyết định theo Agile: Developers cùng đánh giá nguy cơ đối với Sprint Goal, hỗ trợ kiểm tra API, chuyển sang một phương án tích hợp khả thi hoặc điều chỉnh Sprint Backlog. Khi cần thay đổi phạm vi, trao đổi với Product Owner.

Sự khác biệt nằm ở **quyết định được đưa ra sau khi nhìn thấy vấn đề**, không nằm ở việc cuộc họp kéo dài 10 hay 15 phút.

### 3.2. Kanban: chính sách dòng công việc phải ảnh hưởng hành vi

Một bảng cột không tự động làm giảm thời gian giao hàng. Hệ thống Kanban hữu ích khi nhóm **hiển thị công việc, quản lý các hạng mục đang thực hiện và cải thiện dòng chảy một cách chủ động**, với các chính sách minh bạch.

Ví dụ một nhóm xử lý lỗi sản phẩm có chính sách:

1. Cột “Đang xử lý” tối đa ba mục.
2. Nếu đã chạm giới hạn WIP, ưu tiên giúp hoàn tất hoặc tháo chặn mục đang làm trước khi nhận việc mới.
3. Mục bị chặn phải thể hiện lý do và người hỗ trợ, không được che trong cột “Đang xử lý”.
4. Hằng tuần kiểm tra tuổi của công việc đang làm, thời gian hoàn tất và các nhóm nguyên nhân gây chờ.

Các chính sách này dẫn đến những quyết định cụ thể: **có kéo việc mới không, hỗ trợ mục nào trước, tháo chặn ở đâu, thay đổi giới hạn WIP hay cách phối hợp khi nào**. Không nên xem giới hạn WIP là con số thần kỳ; cần thử, quan sát và điều chỉnh theo hệ thống thực tế.

Một vài chỉ số dòng công việc thường gặp:

| Chỉ số | Cách hiểu thực dụng | Câu hỏi để ra quyết định |
|---|---|---|
| WIP | Số mục đã bắt đầu nhưng chưa hoàn thành | Nhóm có đang mở quá nhiều việc khiến hoàn tất chậm không? |
| Work item age | Thời gian một mục đang mở đã tồn tại tới thời điểm quan sát | Mục nào cần được giúp hoặc tháo chặn ngay? |
| Cycle time | Thời gian từ khi bắt đầu xử lý đến khi hoàn tất, theo ranh giới được thống nhất | Công việc mất bao lâu để đi qua hệ thống? Vì sao có nhóm mục quá chậm? |
| Throughput | Số mục hoàn thành trong một khoảng thời gian | Nhóm có thể dự báo khả năng hoàn tất ra sao với loại công việc tương tự? |
| Lead time | Thời gian từ mốc yêu cầu được ghi nhận/chấp nhận đến khi được giao, theo định nghĩa đã thống nhất | Khách hàng thực tế phải chờ bao lâu? Đoạn chờ nào cần cải thiện? |

Phải thống nhất rõ điểm bắt đầu/kết thúc của từng phép đo. Không dùng số ticket hoàn thành làm thước đo năng suất cá nhân khi ticket có độ lớn và độ phức tạp khác nhau. Nếu tối ưu chỉ số khiến mọi người chia ticket giả tạo hoặc giấu việc bị chặn, cách đo đang tạo hành vi sai.

### 3.3. XP: năng lực kỹ thuật làm quyết định thích ứng khả thi

Nhóm có thể đồng ý đổi ưu tiên sau phản hồi nhưng vẫn không thể thay đổi an toàn vì code khó kiểm thử, build lâu, tích hợp muộn hoặc triển khai rủi ro. Các thực hành XP như phát triển hướng kiểm thử (TDD), lập trình cặp khi phù hợp, refactoring, tích hợp liên tục, thiết kế đơn giản và phát hành nhỏ giúp giảm chi phí nhận phản hồi và chi phí sửa quyết định.

Ví dụ, trước kia một thay đổi quy tắc tính phí phải kiểm thử thủ công nhiều ngày nên nhóm tránh điều chỉnh. Sau khi bổ sung các kiểm thử hồi quy có ý nghĩa và pipeline ổn định, nhóm có thể thử một thay đổi phạm vi nhỏ, phát hiện lỗi sớm và đưa ra quyết định tiếp tục hoặc quay lại dựa trên kết quả. **Kỹ thuật tốt không tự chọn được điều có giá trị**, nhưng giúp nhóm thay đổi hướng đi mà vẫn kiểm soát chất lượng.

## 4. Khi phản hồi đến, quyết định nào thực sự đổi?

Để đánh giá một hoạt động Agile, hãy truy ngược từ hành động đến quyết định:

| Câu hỏi kiểm tra | Minh chứng có thể quan sát |
|---|---|
| Nhóm muốn học hoặc giải quyết điều gì? | Mục tiêu Sprint, vấn đề người dùng, rủi ro hoặc giả thuyết được diễn đạt rõ |
| Tín hiệu nào được thu thập? | Phản hồi người dùng, Increment chạy được, dữ liệu dòng công việc, lỗi hoặc quan sát có bối cảnh |
| Ai có quyền quyết định và ai cần được tham vấn? | Vai trò, trách nhiệm và ranh giới được làm rõ trước khi lựa chọn |
| Nhóm đã cân nhắc những lựa chọn nào? | Tiếp tục, dừng, ưu tiên lại, giảm phạm vi, thay giải pháp, hỗ trợ gỡ chặn hoặc thử nghiệm thêm |
| Điều gì thay đổi sau cuộc họp hoặc lần kiểm tra? | Backlog được điều chỉnh, kế hoạch làm việc đổi, một thử nghiệm mới được chọn, hay một giả định được xác nhận rõ |
| Khi nào nhóm biết quyết định đó hiệu quả? | Mốc kiểm tra tiếp theo và tín hiệu kết quả/chất lượng đã thống nhất |

Nếu không có thay đổi, cũng **không mặc nhiên là thất bại**: có thể bằng chứng mới cho thấy hướng hiện tại vẫn đúng. Quan trọng là nhóm đã kiểm tra lựa chọn một cách có chủ đích, hiểu mức độ chắc chắn và biết điều gì sẽ khiến mình đổi hướng.

### 4.1. Mẫu quyết định ngắn gọn

Nhóm có thể ghi lại quyết định quan trọng ngay trong backlog, tài liệu sản phẩm hoặc nhật ký quyết định:

~~~text
VẤN ĐỀ / MỤC TIÊU: Người dùng mới bỏ dở bước xác minh tài khoản.
GIẢ ĐỊNH: Thông báo lỗi quá khó hiểu là một nguyên nhân chính.
BẰNG CHỨNG HIỆN CÓ: Phản hồi hỗ trợ, quan sát 6 phiên dùng thử,
                      log lỗi và hành trình hoàn tất đăng ký.
LỰA CHỌN: (A) Viết lại thông báo và đường dẫn xử lý lỗi;
          (B) Làm lại toàn bộ luồng xác minh.
QUYẾT ĐỊNH: Thử A trước cho nhóm người dùng giới hạn.
NGƯỜI CHỊU TRÁCH NHIỆM: Product Owner quyết định ưu tiên;
                        Developers chọn phương án triển khai an toàn.
RÀNG BUỘC: Không giảm yêu cầu bảo mật hoặc lưu dữ liệu nhạy cảm trái phép.
TÍN HIỆU KIỂM CHỨNG: Tỷ lệ hoàn tất, lỗi xác minh,
                     số yêu cầu hỗ trợ liên quan.
THỜI ĐIỂM XEM LẠI: Sau khi đủ dữ liệu quan sát phù hợp.
NẾU KẾT QUẢ KHÔNG ĐẠT: Phỏng vấn sâu hơn và cân nhắc phương án B.
~~~

Với quyết định thường ngày, không cần biểu mẫu dài như trên; chỉ cần mục tiêu, lý do, người chịu trách nhiệm và thời điểm xem lại đủ rõ. Quyết định có ảnh hưởng lớn cần ghi chi tiết hơn để thuận tiện kiểm tra và giải trình.

## 5. Tình huống xuyên suốt: cải thiện quá trình kích hoạt tài khoản

> **Tình huống giả định để học tập.** Những con số dưới đây chỉ nhằm minh họa cách sử dụng bằng chứng, không phải kết quả nghiên cứu hay tiêu chuẩn chung cho sản phẩm.

Một nhóm phát triển nền tảng SaaS có 1.000 lượt đăng ký mới trong giai đoạn quan sát ban đầu; khoảng **38%** hoàn tất bước cấu hình đầu tiên trong vòng bảy ngày. Bộ phận kinh doanh yêu cầu xây dựng 12 tính năng onboarding trong quý. Kỹ sư đề xuất chia danh sách đó thành sáu Sprint và phát hành cuối quý.

### Cách A: có hoạt động Agile nhưng quyết định vẫn cố định

- Nhóm tạo đủ 12 user story lớn từ danh sách yêu cầu đã được chấp thuận.
- Mỗi hai tuần tổ chức planning, daily, review và retrospective.
- Review chủ yếu trình diễn số story đã xong; phản hồi “người dùng không hiểu hướng dẫn” được ghi thành việc để quý sau.
- Khi một biểu mẫu mới không đem lại chuyển biến, nhóm vẫn phát triển năm biểu mẫu còn lại vì kế hoạch quý đã cam kết.
- Báo cáo tập trung vào “đã hoàn thành 10/12 tính năng” và “velocity không giảm”.

Vấn đề không phải nhóm đã chọn Scrum, mà là **bằng chứng không ảnh hưởng đến thứ tự ưu tiên hoặc cách giải quyết vấn đề**. Hoàn thành kế hoạch có thể tạo nhiều đầu ra nhưng không cho biết tỷ lệ kích hoạt có cải thiện hay không.

### Cách B: dùng hoạt động để thay đổi quyết định

**Bước 1 — Xác định mục tiêu và vùng linh hoạt.** Product Owner và stakeholders thống nhất muốn tăng tỷ lệ hoàn tất cấu hình trong bảy ngày từ mức quan sát ban đầu 38% lên mức mục tiêu phù hợp; lấy **50%** làm mục tiêu minh họa cho giai đoạn này. Ngân sách, an toàn dữ liệu và thời điểm đánh giá vẫn là ràng buộc. Danh sách 12 ý tưởng được xem là các phương án có thể thay đổi, không phải 12 đầu ra bắt buộc bất kể hiệu quả.

**Bước 2 — Thu thập bằng chứng trước khi chọn giải pháp lớn.** Nhóm xem hành trình người dùng, kiểm tra các lỗi kỹ thuật, trao đổi với bộ phận hỗ trợ và quan sát một số phiên sử dụng. Nhóm phát hiện nhiều người không hiểu vì sao phải nhập thông tin cấu hình ở bước thứ hai. Đây là **giả thuyết cần kiểm tra**, chưa đủ để khẳng định nguyên nhân duy nhất.

**Bước 3 — Giao một lát cắt nhỏ.** Sprint Goal tập trung vào việc giúp người dùng hiểu và hoàn tất bước cấu hình. Nhóm chọn cách đơn giản hóa hướng dẫn và hiển thị lỗi ngay tại trường nhập. Developers chia công việc, bổ sung kiểm thử cần thiết và hoàn tất Increment theo Definition of Done.

**Bước 4 — Kiểm tra và ra quyết định.** Nhóm phát hành có kiểm soát, quan sát dữ liệu theo cùng định nghĩa chỉ số và xem phản hồi định tính. Giả sử giai đoạn sau cho thấy tỷ lệ hoàn tất tăng từ 38% lên **43%**, trong khi lỗi và yêu cầu hỗ trợ không tăng đáng kể. Nhóm ghi nhận tín hiệu tích cực, nhưng kiểm tra lượng mẫu, khác biệt nhóm người dùng và thay đổi bên ngoài trước khi kết luận đây là tác động nhân quả của tính năng.

**Bước 5 — Điều chỉnh kế hoạch.** Trong Sprint Review, nhóm thảo luận cùng stakeholders. Thay vì tiếp tục ngay mọi màn hình dự kiến, Product Owner ưu tiên giải quyết phần người dùng vẫn mắc ở bước xác minh. Một ý tưởng làm video dài được lùi lại; một thử nghiệm hướng dẫn ngắn được đưa lên trước. Sprint Retrospective đồng thời phát hiện chu kỳ chờ môi trường kiểm thử quá lâu và chọn cải tiến pipeline.

**Bước 6 — Tiếp tục học.** Nhóm theo dõi lại tỷ lệ kích hoạt, chất lượng và phản hồi sau mỗi thay đổi. Khi đạt mục tiêu hoặc phát hiện vấn đề có giá trị hơn, nhóm ra quyết định tiếp theo dựa trên bằng chứng và ưu tiên hiện tại, thay vì mặc định tiếp tục danh sách cũ.

| Thành phần | Cách A | Cách B |
|---|---|---|
| Thứ được bảo vệ | Danh sách 12 tính năng | Mục tiêu cải thiện trải nghiệm trong ràng buộc đã thống nhất |
| Phản hồi người dùng | Chỉ để ghi nhận | Để điều chỉnh giả thuyết, ưu tiên và phạm vi |
| Sprint Review | Báo cáo phần trăm hoàn tất | Kiểm tra Increment, kết quả và chọn bước tiếp theo |
| Thành công | Số tính năng đã giao | Kết quả sử dụng, chất lượng và điều nhóm đã học |
| Trách nhiệm | “Làm đúng những gì được giao” | Minh bạch về quyết định, dự báo, giá trị và rủi ro |

Đây không phải lời khuyên bỏ hết lập kế hoạch dài hạn. Nhóm vẫn cần định hướng, kinh phí, phối hợp liên phòng ban và quản lý phụ thuộc. Khác biệt là kế hoạch được xem như **dự báo có thể điều chỉnh khi thực tế thay đổi**, cùng với cơ chế công khai ai được điều chỉnh điều gì.

## 6. Bốn tình huống dễ nhầm lẫn

### Tình huống 1: “Chúng tôi có Sprint hai tuần, vậy đã thích ứng nhanh”

Không đủ. Nếu mỗi Sprint chỉ hoàn tất một phần code, còn kiểm thử tích hợp và phát hành dồn vào cuối quý, người dùng chưa thể phản hồi sớm. Nhóm có thể cần chia công việc thành lát cắt chạy xuyên suốt, tích hợp thường xuyên, cải thiện Definition of Done và tìm cách kiểm chứng giá trị sớm hơn.

**Câu hỏi quyết định:** Mỗi Sprint tạo ra được thông tin thực tế nào giúp chọn việc tiếp theo?

### Tình huống 2: “Stakeholder đổi ý liên tục nên nhóm phải nhận mọi yêu cầu”

Phản hồi mới đáng xem xét, nhưng Agile không có nghĩa thay đổi tùy tiện hoặc bỏ qua tập trung. Product Owner cần cân nhắc giá trị, chi phí, rủi ro và mục tiêu sản phẩm. Trong Sprint, Scrum Team giữ Sprint Goal làm điểm định hướng; nếu phát sinh yêu cầu, nhóm đánh giá ảnh hưởng và thương lượng phạm vi một cách minh bạch.

**Câu hỏi quyết định:** Thông tin mới có đủ quan trọng để đổi ưu tiên ngay, hay nên đưa vào vòng đánh giá kế tiếp?

### Tình huống 3: “Đã retrospective, ai cũng đồng ý cần giao tiếp tốt hơn”

Một mong muốn chung chưa phải thay đổi có thể kiểm chứng. Hãy thử quy tắc cụ thể, chẳng hạn trước khi bắt đầu thay đổi API phải có ví dụ request/response được hai bên thống nhất; sau hai tuần xem số lần sửa lại do hiểu nhầm có giảm không.

**Câu hỏi quyết định:** Nhóm sẽ làm điều gì khác từ ngày mai, ai kiểm tra và khi nào?

### Tình huống 4: “Velocity tăng, nghĩa là nhóm Agile hơn”

Velocity trong Scrum (nếu nhóm dùng) là một công cụ lập kế hoạch nội bộ dựa trên cách nhóm ước lượng, không phải thước đo giá trị tuyệt đối và càng không thích hợp để xếp hạng nhiều nhóm. Tăng điểm có thể chỉ phản ánh thay đổi cách ước lượng hoặc cách chia việc.

**Câu hỏi quyết định:** Người dùng nhận giá trị sớm và đều hơn không? Sự cố, thời gian chờ và khả năng dự báo có cải thiện không?

## 7. Đo lường sự thay đổi theo nhiều góc nhìn

Một nhóm có thể “qua mặt” bất kỳ chỉ số đơn lẻ nào nếu chỉ tối ưu con số đó. Cần chọn một tập nhỏ chỉ số gắn với mục tiêu, có định nghĩa rõ và được diễn giải trong bối cảnh.

| Góc nhìn | Ví dụ tín hiệu | Cách sử dụng hợp lý |
|---|---|---|
| Kết quả người dùng / kinh doanh | Tỷ lệ hoàn tất tác vụ, thời gian đạt giá trị đầu tiên, tỷ lệ lỗi thao tác, khả năng sử dụng | Kiểm tra giả thuyết về giá trị, ưu tiên vấn đề thực sự |
| Dòng công việc | Lead time, cycle time, WIP, work item age, throughput | Nhận diện chờ đợi, tắc nghẽn và cải thiện dự báo |
| Chất lượng và độ tin cậy | Lỗi lọt ra sản xuất, thời gian khôi phục, kết quả kiểm thử, sự cố sau thay đổi | Tránh giao nhanh bằng cách tích lũy lỗi hoặc rủi ro |
| Học tập và thích ứng | Số giả thuyết quan trọng được kiểm tra, thời gian từ phản hồi đến quyết định, cải tiến đã được kiểm chứng | Xem vòng phản hồi có vận hành hay chỉ lặp nghi thức |
| Sức bền của nhóm | Tình trạng làm thêm kéo dài, gánh nặng chuyển ngữ cảnh, phản hồi về khả năng phối hợp | Xem tốc độ hiện tại có bền vững hay gây kiệt sức |

Một phép đo không chỉ cần **đếm**, mà còn phải dẫn đến **hành động**. Chẳng hạn cycle time tăng có thể do loại việc khó hơn chứ không nhất thiết do hiệu suất đi xuống. Nhóm nên phân nhóm công việc, xem dữ liệu phân bố và tìm nguyên nhân trước khi áp chính sách mới.

Tránh các cách sử dụng sai: so năng suất cá nhân bằng story point, thưởng theo số ticket đóng, yêu cầu mọi Sprint phải tăng velocity, hoặc chỉ lấy dữ liệu thuận lợi để chứng minh một quyết định đã đúng. Khi chỉ số trở thành mục tiêu đối phó, nó mất giá trị làm tín hiệu học hỏi.

## 8. Tạo điều kiện để quyết định tốt được thực thi

Ngay cả khi đồng ý dùng phản hồi, nhóm vẫn có thể mắc kẹt nếu không có cơ chế thực hiện. Cần giải quyết đồng thời một số yếu tố:

**Mục tiêu rõ và phạm vi được phép thay đổi.** Nhóm hiểu vì sao làm sản phẩm, điều gì là ràng buộc bắt buộc, điều gì có thể thương lượng. Product Goal hoặc mục tiêu dịch vụ giúp nối quyết định ngắn hạn với hướng đi dài hạn.

**Quyền quyết định đúng nơi có thông tin.** Người chịu trách nhiệm về giá trị phải có quyền sắp xếp ưu tiên; người trực tiếp phát triển cần có quyền quyết định kỹ thuật trong ranh giới đã thống nhất. Các quyết định liên quan bảo mật, dữ liệu, pháp lý hoặc chi phí lớn vẫn tuân thủ cơ chế kiểm soát thích hợp.

**Khả năng tạo ra Increment có thể kiểm tra.** Chia việc theo lát cắt tạo giá trị, tự động hóa kiểm thử ở nơi hiệu quả, tích hợp thường xuyên và giữ Definition of Done đáng tin cậy. Nếu mọi thay đổi đều cần sáu tuần để triển khai, “được phép thích ứng” vẫn rất khó biến thành hành động.

**Tiếp cận được phản hồi thật.** Phối hợp với người dùng, khách hàng và bộ phận hỗ trợ; quan sát hành vi sử dụng với quyền riêng tư phù hợp. Đảm bảo có kênh để phản hồi tác động đến backlog, thay vì bị lưu ở một báo cáo không ai dùng.

**An toàn để nêu rủi ro và sai lầm.** Nếu nhóm bị phạt khi phát hiện giả thuyết sai, mọi người có xu hướng trình bày kết quả đẹp và tránh thử nghiệm. Cần khuyến khích minh bạch, học từ sai sót và giải quyết vấn đề theo hệ thống, đồng thời vẫn giữ trách nhiệm đối với chất lượng và hành động.

**Thời điểm xem lại phù hợp.** Không phải mọi quyết định đều cần một cuộc họp. Sự cố sản xuất có thể yêu cầu phản ứng tức thời; kế hoạch Sprint được kiểm tra hằng ngày; lựa chọn sản phẩm thường được xem lại sau khi có Increment và tín hiệu đủ tin cậy. Cadence là công cụ tổ chức học tập, không phải lý do trì hoãn phản hồi quan trọng.

### 8.1. Thực hành chuyển đổi trong bốn tuần

Đây là lịch thử nghiệm minh họa cho một nhóm đã có hoạt động Agile nhưng cảm thấy quyết định không thay đổi. Có thể rút ngắn hoặc kéo dài theo bối cảnh.

| Thời điểm | Việc cần làm | Bằng chứng kết thúc bước |
|---|---|---|
| Tuần 1: Quan sát | Chọn ba quyết định gần đây, ghi lại ai quyết, dùng dữ liệu gì, mất bao lâu, có được xem lại không | Nhìn rõ một điểm nghẽn trong quyền quyết định hoặc phản hồi |
| Tuần 2: Chọn thử nghiệm | Viết một mục tiêu có ý nghĩa, một giả thuyết kiểm chứng được và một thay đổi nhỏ trong backlog hoặc chính sách WIP | Có người chịu trách nhiệm, tiêu chí chấp nhận và mốc xem lại |
| Tuần 3: Thực hiện | Giao lát cắt nhỏ hoặc áp dụng chính sách mới; lấy phản hồi thật và theo dõi rủi ro | Có dữ liệu thực tế và những điều còn chưa chắc |
| Tuần 4: Kiểm tra và thích ứng | Đối chiếu giả thuyết, trao đổi với người liên quan, chọn tiếp tục/chỉnh sửa/dừng | Có quyết định cụ thể và bài học được phản ánh vào cách làm tiếp theo |

Hãy bắt đầu với một quyết định có ảnh hưởng vừa đủ để thấy kết quả nhưng không quá rủi ro. Không cần cải tổ toàn bộ quy trình trước khi có bằng chứng rằng thay đổi đầu tiên hữu ích.

## 9. Bộ câu hỏi tự đánh giá nhóm

Với từng câu, hãy tìm **một ví dụ thực tế trong các tuần gần đây**. “Có họp” hoặc “có tài liệu” chưa phải minh chứng.

1. Nhóm có diễn đạt được kết quả mà sản phẩm hoặc Sprint muốn tạo ra, vượt ra ngoài danh sách tính năng không?
2. Lần gần nhất phản hồi người dùng khiến backlog được đổi ưu tiên hoặc một ý tưởng bị loại bỏ là khi nào?
3. Khi một kế hoạch có nguy cơ không đạt, nhóm có thể chủ động điều chỉnh hành động trong giới hạn trách nhiệm không?
4. Stakeholders có được tham gia kiểm tra Increment và thảo luận lựa chọn tương lai, hay chỉ xem demo một chiều?
5. Các vấn đề lặp lại trong retrospective có dẫn đến thử nghiệm cải tiến được kiểm chứng hay không?
6. Nhóm biết công việc đang bị chặn ở đâu và có quyết định hỗ trợ hoàn tất trước khi mở quá nhiều việc mới không?
7. Các chỉ số dùng trong họp có giúp chọn hành động hay chỉ để đánh giá và so sánh người làm?
8. Nhóm có đủ kiểm thử, tích hợp và cơ chế triển khai để thay đổi một phần sản phẩm an toàn không?
9. Những gì bắt buộc phải giữ nguyên (bảo mật, pháp lý, ngân sách, mục tiêu Sprint...) có được nói rõ với các bên liên quan không?
10. Khi bằng chứng chưa đủ, nhóm có biết thử nghiệm/quan sát nào cần làm tiếp không?

Nếu nhiều câu chưa có ví dụ cụ thể, hãy chọn **một vòng quyết định** để cải thiện. Thay đổi có tác dụng thường bắt đầu từ một vấn đề được theo dõi đến cùng, thay vì đồng loạt thêm nhiều cuộc họp và biểu mẫu.

## 10. Bài tập vận dụng

### Bài tập A — Phân loại bốn phát biểu

Cho các phát biểu:

1. “Đội đã tổ chức đủ bốn sự kiện Scrum trong Sprint này.”
2. “Đội hoàn thành tám user story.”
3. “Sau khi khách hàng thử Increment, Product Owner đưa khả năng truy cập bằng bàn phím lên ưu tiên cao hơn tính năng giao diện mới.”
4. “Tỷ lệ người dùng hoàn tất tác vụ bằng bàn phím đã tăng trong nhóm được kiểm tra.”

Hãy xác định câu nào chủ yếu nói về **hoạt động**, **đầu ra**, **quyết định**, **kết quả**; sau đó cho biết vì sao cả bốn thông tin đều có thể hữu ích nhưng không thể thay thế nhau.

<details>
<summary>Gợi ý đáp án</summary>

1 là hoạt động; 2 là đầu ra; 3 là quyết định; 4 là kết quả được quan sát. Một hoạt động giúp tạo cơ hội phối hợp, đầu ra tạo điều kiện nhận phản hồi, quyết định chọn hướng hành động và kết quả cho biết mức độ đạt mục tiêu. Cần kiểm tra thêm cách đo kết quả trước khi quy kết nguyên nhân.

</details>

### Bài tập B — Sửa một Sprint Review hình thức

Nhóm vừa trình diễn màn hình tìm kiếm mới. Một khách hàng cho biết tìm thấy ít kết quả liên quan dù màn hình tải nhanh. Cuộc họp kết thúc bằng câu “Ghi nhận ý kiến, chúng ta tiếp tục kế hoạch quý”.

Hãy đề xuất ít nhất ba câu hỏi hoặc hành động giúp biến phản hồi thành quyết định có trách nhiệm. Có thể xem xét mục tiêu tìm kiếm, phân loại người dùng bị ảnh hưởng, bằng chứng cần thu thập, đánh đổi với tính năng mới và ai có quyền đổi ưu tiên.

<details>
<summary>Gợi ý đáp án</summary>

Hỏi người dùng đang cố tìm loại nội dung nào và định nghĩa thế nào là “liên quan”; kiểm tra log truy vấn hoặc quan sát phiên sử dụng phù hợp; xác định liệu lỗi xếp hạng kết quả có làm hỏng mục tiêu hiện tại không; để Product Owner cân nhắc điều chỉnh Product Backlog cùng stakeholders; chọn một thay đổi nhỏ, có chỉ số chất lượng tìm kiếm và mốc xem lại. Không cần hứa đổi ưu tiên ngay nếu chưa đủ bằng chứng.

</details>

### Bài tập C — Quyết định của nhóm Kanban

Một nhóm hỗ trợ có bốn việc đang thực hiện, hai việc bị chặn chờ kiểm thử, trong khi ba yêu cầu mới vừa đến. Người quản lý nói: “Nhận cả ba để ai cũng bận”.

Thiết kế một chính sách đơn giản để xử lý tình huống. Nêu ít nhất một chỉ số sẽ xem lại sau hai tuần và một điều kiện ngoại lệ cho yêu cầu khẩn cấp thực sự.

<details>
<summary>Gợi ý đáp án</summary>

Nhóm có thể đặt giới hạn WIP phù hợp, ưu tiên cùng nhau gỡ hai việc đang chặn trước khi kéo việc mới, hiển thị rõ lý do chặn và dùng chính sách xử lý khẩn cấp đã thống nhất. Sau hai tuần xem work item age, cycle time và số mục bị chặn kéo dài. Với sự cố nghiêm trọng đang gây tác động sản xuất, có thể áp dụng luồng khẩn cấp riêng và đánh giá ảnh hưởng lên công việc hiện tại.

</details>

## 11. Những nguyên tắc cần nhớ

- **Nghi thức tạo cơ hội; quyết định mới tạo ra sự thích ứng.** Họp, bảng và công cụ cần phục vụ việc kiểm tra thực tế và lựa chọn hành động.
- **Giá trị không đồng nhất với số lượng tính năng.** Hãy nối đầu ra với vấn đề của người dùng, chất lượng và kết quả mong đợi.
- **Phản hồi chỉ hữu ích khi có người chịu trách nhiệm xem xét nó.** Quyền quyết định, tiêu chí và thời điểm kiểm tra phải đủ rõ.
- **Linh hoạt luôn đi cùng kỷ luật.** Có mục tiêu, ràng buộc, Definition of Done, cơ chế quản lý rủi ro và sự minh bạch khi điều chỉnh.
- **Cải tiến liên tục là thử một thay đổi rồi kiểm chứng.** Một retrospective tốt, một chính sách WIP hữu ích hoặc một Increment nhỏ phải giúp nhóm đưa ra quyết định tốt hơn ở vòng tiếp theo.

Hãy kết thúc mỗi hoạt động Agile bằng câu hỏi: **“Chúng ta vừa học được điều gì, điều đó ảnh hưởng tới quyết định nào và khi nào sẽ kiểm tra lại?”** Khi nhóm trả lời được bằng ví dụ cụ thể, Agile đang trở thành cách vận hành chứ không chỉ là tên gọi cho lịch họp.
