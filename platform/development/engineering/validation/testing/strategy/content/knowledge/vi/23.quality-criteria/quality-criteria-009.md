# Xác định quyền chấp nhận rủi ro và quyền quyết định phát hành

Một sản phẩm có thể hoàn thành phần lớn kiểm thử nhưng vẫn còn lỗi, khoảng trống bằng chứng hoặc giới hạn vận hành. Khi đó, câu hỏi không chỉ là “còn rủi ro nào?” mà còn là “ai có quyền quyết định rủi ro đó có thể được chấp nhận, trong phạm vi nào và ai được phép cho phát hành?”. Nếu quyền quyết định không rõ, nhóm có thể tiếp tục phát hành dựa trên đồng thuận miệng, trì hoãn vô thời hạn vì không ai dám quyết định, hoặc để người không chịu trách nhiệm về hậu quả tự chấp nhận rủi ro.

Quản trị chất lượng cần phân định rõ **chủ sở hữu rủi ro**, **người đánh giá và cung cấp bằng chứng**, **người phê duyệt chấp nhận rủi ro**, và **người có quyền quyết định phát hành**. Các vai trò này có thể thuộc cùng một người trong dự án nhỏ, nhưng trách nhiệm và giới hạn thẩm quyền vẫn phải được ghi nhận. Quyền quyết định phải phù hợp với mức độ tác động, chính sách, nghĩa vụ pháp lý/hợp đồng và phạm vi phát hành.

## 1. Phân biệt chấp nhận rủi ro với quyết định phát hành

**Chấp nhận rủi ro** là quyết định có chủ đích rằng một rủi ro còn lại được phép tồn tại trong những điều kiện xác định. Người chấp nhận phải hiểu khả năng xảy ra, tác động, nhóm bị ảnh hưởng, biện pháp kiểm soát và giới hạn của bằng chứng.

**Quyết định phát hành** là quyết định cho phép một phiên bản hoặc phạm vi sản phẩm được triển khai, mở cho người dùng hoặc chuyển sang giai đoạn vận hành. Quyết định này tổng hợp nhiều yếu tố: kết quả kiểm thử, rủi ro còn lại, mức sẵn sàng vận hành, bảo mật, tuân thủ, hỗ trợ, kế hoạch rollback và các phê duyệt bắt buộc.

Hai quyết định có liên quan nhưng không đồng nhất:

- Một người có thẩm quyền chấp nhận một rủi ro cụ thể chưa chắc có quyền cho phép phát hành toàn bộ sản phẩm.
- Người quyết định phát hành không được mặc nhiên chấp nhận thay mọi rủi ro thuộc quyền của chủ sở hữu dữ liệu, bảo mật, pháp lý hoặc vận hành.
- Một phiên bản có thể đáp ứng tiêu chí kỹ thuật nhưng vẫn chưa được phép phát hành vì thiếu phê duyệt bắt buộc hoặc chưa sẵn sàng hỗ trợ.
- Một rủi ro có thể được chấp nhận trong phạm vi thử nghiệm nội bộ nhưng không được chấp nhận khi mở rộng ra toàn bộ người dùng.

Ví dụ: chủ sản phẩm có thể chấp nhận việc một báo cáo ít dùng chưa hỗ trợ trình duyệt cũ trong đợt phát hành giới hạn. Nhưng chủ sản phẩm không thể tự miễn trừ yêu cầu bảo vệ dữ liệu hoặc phê duyệt bảo mật thuộc thẩm quyền của tổ chức.

## 2. Các khái niệm cần thống nhất

| Khái niệm | Ý nghĩa | Câu hỏi chính |
| --- | --- | --- |
| Rủi ro (risk) | Khả năng xảy ra sự kiện không mong muốn và hậu quả của nó | Điều gì có thể xảy ra và ảnh hưởng ra sao? |
| Rủi ro vốn có (inherent risk) | Rủi ro trước khi áp dụng biện pháp kiểm soát | Nếu chưa có kiểm soát, mức phơi lộ là gì? |
| Rủi ro còn lại (residual risk) | Rủi ro vẫn tồn tại sau kiểm soát | Sau các biện pháp hiện tại, điều gì vẫn có thể xảy ra? |
| Khẩu vị rủi ro (risk appetite) | Mức độ rủi ro tổ chức sẵn sàng theo đuổi hoặc chấp nhận để đạt mục tiêu | Tổ chức sẵn sàng chịu mức rủi ro nào? |
| Ngưỡng chấp nhận (risk tolerance) | Giới hạn cụ thể cho một loại rủi ro hoặc phạm vi | Khi nào phải giảm thiểu, chuyển cấp hoặc dừng? |
| Chủ sở hữu rủi ro (risk owner) | Người chịu trách nhiệm theo dõi và quản lý một rủi ro | Ai bảo đảm rủi ro được xử lý và rà soát? |
| Người chấp nhận rủi ro | Người có thẩm quyền phê duyệt việc giữ rủi ro còn lại | Ai có quyền nói rằng rủi ro này được phép tồn tại? |
| Người quyết định phát hành (release authority) | Người hoặc cơ quan có quyền cho phép phát hành theo quy trình | Ai có quyền cho phép phiên bản đi tiếp? |

Khẩu vị rủi ro thường được xác định ở cấp tổ chức hoặc lĩnh vực. Ngưỡng chấp nhận chuyển định hướng đó thành giới hạn có thể áp dụng cho loại rủi ro, sản phẩm hoặc quyết định cụ thể. Không nên tự tạo ngưỡng riêng cho một lần phát hành nếu ngưỡng đó mâu thuẫn với chính sách đã được phê duyệt.

## 3. Vì sao phải xác định quyền quyết định từ sớm?

Nếu chỉ xác định người phê duyệt khi đã đến ngày phát hành, nhóm có thể phát hiện quá muộn rằng người có mặt trong cuộc họp không đủ thẩm quyền. Điều này tạo áp lực thời hạn và khuyến khích chấp nhận ngoại lệ thiếu căn cứ.

Phân định quyền từ giai đoạn lập kế hoạch giúp:

- Biết ai cần tham gia đánh giá rủi ro và ai có quyền quyết định cuối cùng.
- Xác định tiêu chí bắt buộc phải đạt trước khi bắt đầu phát triển hoặc trước release.
- Dự kiến thời gian xin phê duyệt cho rủi ro cao hoặc phụ thuộc bên ngoài.
- Tránh việc nhóm kiểm thử bị yêu cầu tự “approve” rủi ro mà họ chỉ có trách nhiệm cung cấp bằng chứng.
- Bảo đảm người chịu tác động và người có trách nhiệm nghiệp vụ được tham gia.
- Tạo đường chuyển cấp khi các nhóm không thống nhất hoặc rủi ro vượt thẩm quyền.

Quyền quyết định nên được ghi trong kế hoạch chất lượng, quy trình release, ma trận thẩm quyền hoặc tài liệu quản trị dự án được tổ chức công nhận. Không nên chỉ dựa vào thói quen hoặc chức danh không gắn với phạm vi trách nhiệm.

## 4. Các vai trò trong quyết định rủi ro và phát hành

### Chủ sở hữu rủi ro

Chủ sở hữu rủi ro chịu trách nhiệm về việc hiểu, theo dõi và điều phối xử lý một rủi ro cụ thể. Họ thường:

- Mô tả rủi ro, nguyên nhân, tác động và phạm vi phơi lộ.
- Đề xuất biện pháp giảm thiểu và chỉ số theo dõi.
- Xác định hành động, người thực hiện và thời hạn.
- Theo dõi rủi ro còn lại và thông báo khi điều kiện thay đổi.
- Đề xuất chấp nhận, giảm thiểu, chuyển giao hoặc tránh rủi ro.

Chủ sở hữu rủi ro không tự động có quyền chấp nhận rủi ro. Ví dụ, trưởng nhóm phát triển có thể sở hữu rủi ro về lỗi hiệu năng của dịch vụ, nhưng mức độ rủi ro có thể vượt giới hạn mà vai trò đó được phép chấp nhận.

### Người đánh giá và cung cấp bằng chứng

Nhóm kiểm thử, kỹ thuật, bảo mật, vận hành và nghiệp vụ cung cấp bằng chứng trong phạm vi chuyên môn:

- Kiểm thử báo cáo kết quả, phạm vi, điều kiện, lỗi và khoảng trống bằng chứng.
- Phát triển giải thích thay đổi, nguyên nhân kỹ thuật, mức độ ảnh hưởng và khả năng sửa.
- Bảo mật đánh giá mối đe dọa, lỗ hổng và biện pháp kiểm soát.
- Vận hành đánh giá giám sát, backup, rollback, hỗ trợ và năng lực xử lý sự cố.
- Chủ sản phẩm hoặc nghiệp vụ đánh giá tác động tới người dùng và mục tiêu kinh doanh.

Người cung cấp bằng chứng phải trình bày cả kết quả không thuận lợi và giới hạn của phép đo. Họ không nên điều chỉnh hoặc bỏ qua kết quả để làm quyết định dễ được thông qua.

### Người chấp nhận rủi ro

Người chấp nhận rủi ro phải có thẩm quyền tương ứng với loại và mức độ rủi ro. Họ cần:

- Hiểu rủi ro còn lại và những giả định chưa được xác minh.
- Xác nhận rủi ro nằm trong giới hạn được phép chấp nhận.
- Phê duyệt phạm vi, thời hạn, biện pháp kiểm soát và điều kiện dừng.
- Bảo đảm có chủ sở hữu và nguồn lực cho các hành động còn lại.
- Xem xét lại quyết định khi có sự cố hoặc bằng chứng mới.

Không nên chấp nhận rủi ro chỉ vì thời hạn phát hành, chi phí đã đầu tư hoặc mong muốn giữ cam kết. Những yếu tố này có thể ảnh hưởng lựa chọn kinh doanh nhưng không thay thế đánh giá tác động và giới hạn thẩm quyền.

### Người quyết định phát hành

Release authority có quyền quyết định phiên bản có được triển khai theo phạm vi đề xuất hay không. Vai trò này thường xem xét:

- Các cổng chất lượng bắt buộc đã đạt hay chưa.
- Những rủi ro còn lại đã được người đúng thẩm quyền chấp nhận hay chưa.
- Các điều kiện trước phát hành đã hoàn tất hay chưa.
- Kế hoạch triển khai, giám sát, hỗ trợ và rollback có khả thi không.
- Có sự cố, thay đổi hoặc thông tin mới làm mất hiệu lực phê duyệt trước đó không.

Release authority có thể là một cá nhân, hội đồng release hoặc vai trò được ủy quyền theo quy trình. Cần ghi rõ phạm vi ủy quyền và người thay thế khi người có thẩm quyền vắng mặt.

### Các vai trò kiểm soát độc lập

Trong những lĩnh vực như bảo mật, quyền riêng tư, pháp lý, an toàn hoặc quản lý dữ liệu, tổ chức có thể yêu cầu phê duyệt chuyên môn riêng. Các phê duyệt này có thể là điều kiện bắt buộc và không thể bị thay thế bằng quyết định kinh doanh thông thường.

## 5. Xây dựng ma trận quyền quyết định

Ma trận quyền quyết định nêu ai đề xuất, ai cung cấp ý kiến, ai phê duyệt và ai chịu trách nhiệm thực hiện. Có thể dùng RACI hoặc ma trận thẩm quyền riêng.

Trong RACI:

- **R (Responsible):** người trực tiếp thực hiện công việc.
- **A (Accountable):** người chịu trách nhiệm cuối cùng cho kết quả hoặc quyết định; nên có một A rõ ràng cho mỗi quyết định.
- **C (Consulted):** bên cần được tham vấn trước quyết định.
- **I (Informed):** bên cần được thông báo.

Ví dụ ma trận minh họa:

| Hoạt động | Chủ sản phẩm | QA/Test lead | Chủ sở hữu rủi ro kỹ thuật | Security/Privacy | Vận hành | Release authority |
| --- | --- | --- | --- | --- | --- | --- |
| Xác định tiêu chí chấp nhận | A/R | C | C | C | C | I |
| Thu thập kết quả kiểm thử | I | A/R | C | C | C | I |
| Đánh giá rủi ro kỹ thuật | C | C | A/R | C | C | I |
| Đánh giá rủi ro bảo mật | I | C | C | A/R | C | I |
| Đánh giá mức sẵn sàng vận hành | C | C | C | C | A/R | I |
| Chấp nhận rủi ro nghiệp vụ trong thẩm quyền | A/R hoặc người được ủy quyền | C | C | C | C | I |
| Chấp nhận rủi ro kỹ thuật trong thẩm quyền | C | C | A/R hoặc người được ủy quyền | C | C | I |
| Quyết định phát hành | C | C | C | C | C | A/R |

Ma trận này chỉ minh họa. Tổ chức phải điều chỉnh theo cấu trúc, chính sách và thẩm quyền thực tế. Không nên gán A cho nhiều vai trò trong cùng một quyết định nếu điều đó làm mờ trách nhiệm cuối cùng. Nếu cần nhiều phê duyệt bắt buộc, hãy biểu diễn chúng thành các điều kiện độc lập trước khi release authority ra quyết định.

## 6. Quyền quyết định phải gắn với mức độ rủi ro

Không phải mọi rủi ro đều cần cùng cấp phê duyệt. Có thể thiết lập các cấp thẩm quyền dựa trên mức độ tác động, khả năng xảy ra, phạm vi người dùng, tính nhạy cảm và nghĩa vụ bắt buộc.

Ví dụ mô hình phân cấp:

| Mức rủi ro | Ví dụ | Quyền quyết định có thể áp dụng |
| --- | --- | --- |
| Thấp | Sai lệch nhỏ về hiển thị, có cách khắc phục ngay và không ảnh hưởng dữ liệu hoặc giao dịch | Chủ sản phẩm hoặc quản lý được ủy quyền, theo chính sách |
| Trung bình | Một chức năng phụ có giới hạn, có workaround và giám sát rõ | Chủ sở hữu nghiệp vụ cùng chủ sở hữu kỹ thuật hoặc cấp quản lý được chỉ định |
| Cao | Ảnh hưởng nhiều người dùng, giao dịch, dữ liệu hoặc hoạt động vận hành trọng yếu | Cấp quản lý có thẩm quyền rủi ro; cần ý kiến chuyên môn bắt buộc liên quan |
| Rất cao/không được phép ngoại lệ | Nguy cơ vi phạm pháp luật, nghĩa vụ bắt buộc, mất an toàn nghiêm trọng hoặc vi phạm chính sách không thể miễn trừ | Không được chấp nhận bằng cơ chế ngoại lệ thông thường; phải xử lý theo quy trình chuyên biệt hoặc dừng phát hành |

Ngưỡng cụ thể phải được tổ chức xác định. Không nên dùng bảng này như một quy định phổ quát hoặc tự gán mức rủi ro chỉ bằng một điểm số.

### Xem xét tác động và quyền sở hữu

Người có thẩm quyền cần đủ gần với hậu quả của quyết định và có khả năng cấp nguồn lực để quản lý nó. Rủi ro về dữ liệu khách hàng có thể cần chủ sở hữu dữ liệu và privacy officer; rủi ro về khả năng phục hồi dịch vụ có thể cần service owner và người chịu trách nhiệm vận hành; rủi ro về trải nghiệm hoặc phạm vi tính năng có thể thuộc chủ sản phẩm.

Việc một người có ngân sách hoặc quyền điều phối dự án không tự động trao cho họ thẩm quyền chấp nhận mọi loại rủi ro.

## 7. Phân biệt rủi ro có thể chấp nhận và điều kiện bắt buộc

Một số tiêu chí chất lượng là mục tiêu có thể cân nhắc theo mức rủi ro; một số khác là điều kiện bắt buộc theo luật, hợp đồng, chính sách hoặc kiến trúc kiểm soát. Nhóm cần phân biệt trước khi đề xuất ngoại lệ.

Ví dụ về điều kiện có thể cần phê duyệt theo khẩu vị rủi ro:

- Một báo cáo ít sử dụng chưa hỗ trợ một phiên bản trình duyệt cũ, trong khi nhóm người dùng đó có phương án thay thế.
- Một chỉ số hiệu năng ở chức năng phụ gần ngưỡng, với phạm vi triển khai giới hạn và giám sát.
- Một tài liệu vận hành chưa hoàn chỉnh nhưng có quy trình tạm thời được kiểm soát trong thời gian ngắn.

Ví dụ về điều kiện có thể không được miễn trừ theo quy trình thông thường:

- Nghĩa vụ bảo vệ dữ liệu hoặc hạn chế xử lý dữ liệu không có căn cứ.
- Lỗ hổng hoặc hành vi vi phạm chính sách bảo mật bắt buộc.
- Thiếu phê duyệt pháp lý, hợp đồng hoặc an toàn được yêu cầu.
- Mất khả năng bảo vệ dữ liệu quan trọng hoặc không có phương án phục hồi tối thiểu theo chính sách.

Chỉ bộ phận có thẩm quyền theo quy định mới có thể xác định một yêu cầu có được phép ngoại lệ hay không. Người quyết định phát hành không nên tự diễn giải rằng mọi tiêu chí đều có thể được chấp nhận có điều kiện.

## 8. Xác định khẩu vị rủi ro, ngưỡng và giới hạn ủy quyền

Để tránh quyết định tùy tiện, tổ chức cần xác định trước:

- Loại rủi ro được phép chấp nhận và loại rủi ro không được miễn trừ.
- Mức tác động hoặc phạm vi tối đa mà từng cấp vai trò được phép chấp nhận.
- Thời hạn tối đa cho ngoại lệ tạm thời.
- Các biện pháp kiểm soát tối thiểu phải có.
- Điều kiện bắt buộc phải chuyển cấp.
- Người thay thế hoặc quy trình khẩn cấp khi người phê duyệt chính vắng mặt.

Giới hạn ủy quyền có thể dựa trên nhiều chiều: mức độ nghiêm trọng, số người dùng, giá trị giao dịch, loại dữ liệu, khu vực triển khai, thời gian tồn tại và khả năng rollback.

Ví dụ: quản lý sản phẩm được phép chấp nhận một sai lệch hiển thị mức thấp cho nhóm nội bộ trong tối đa 14 ngày. Rủi ro về giao dịch tiền tệ hoặc dữ liệu cá nhân phải được chuyển tới vai trò cấp cao hơn và có phê duyệt chuyên môn liên quan. Các con số và loại rủi ro chỉ có hiệu lực nếu được tổ chức chính thức thông qua.

Không nên mở rộng ủy quyền bằng lời nói trong cuộc họp. Nếu cần thay đổi giới hạn, phải cập nhật quy định hoặc ghi nhận phê duyệt của cấp có thẩm quyền.

## 9. Quy trình quyết định chấp nhận rủi ro

Một hồ sơ rủi ro nên được xử lý theo các bước:

1. **Ghi nhận rủi ro:** mô tả sự kiện, nguyên nhân, hậu quả, phạm vi và điều kiện kích hoạt.
2. **Xác định chủ sở hữu:** chỉ định người chịu trách nhiệm theo dõi và xử lý.
3. **Thu thập bằng chứng:** kết quả kiểm thử, dữ liệu vận hành, phân tích bảo mật, giới hạn môi trường và lịch sử lỗi.
4. **Đánh giá rủi ro còn lại:** xem xét khả năng, tác động, mức bất định và biện pháp kiểm soát.
5. **Kiểm tra thẩm quyền:** xác định ai được phép chấp nhận loại rủi ro và mức độ đó.
6. **Đề xuất phương án:** giảm thiểu, tránh, chuyển giao hoặc chấp nhận có điều kiện.
7. **Tham vấn bên liên quan:** lấy ý kiến chuyên môn bắt buộc và người chịu tác động.
8. **Ra quyết định:** phê duyệt, từ chối, yêu cầu thêm bằng chứng hoặc chuyển cấp.
9. **Ghi điều kiện:** phạm vi, thời hạn, chủ sở hữu hành động, bằng chứng đóng và điều kiện dừng.
10. **Theo dõi và rà soát:** đánh giá lại khi có thay đổi, sự cố hoặc hết hạn.

Quyết định cần thể hiện rõ trạng thái: Accepted, Accepted with conditions, Rejected, Deferred hoặc Escalated. Trạng thái Deferred không có nghĩa rủi ro đã được chấp nhận; nó cho biết quyết định đang chờ bằng chứng hoặc cấp phê duyệt.

## 10. Quy trình ra quyết định phát hành

Quyết định phát hành cần được đưa ra sau khi các bằng chứng và phê duyệt bắt buộc đã sẵn sàng. Một quy trình tham khảo:

1. **Xác định phạm vi release:** phiên bản, tính năng, môi trường, nhóm người dùng và tỷ lệ rollout.
2. **Tổng hợp bằng chứng chất lượng:** kết quả kiểm thử chức năng, hồi quy, phi chức năng, bảo mật, tương thích và các tiêu chí liên quan.
3. **Tổng hợp rủi ro còn lại:** lỗi mở, test bị chặn, giới hạn môi trường, phụ thuộc và ngoại lệ.
4. **Xác minh phê duyệt:** bảo đảm mỗi rủi ro được đúng người chấp nhận và các điều kiện bắt buộc đã được đáp ứng.
5. **Đánh giá sẵn sàng vận hành:** giám sát, cảnh báo, runbook, hỗ trợ, backup, rollback và năng lực ứng phó.
6. **Kiểm tra điều kiện release:** xác nhận không có cổng bắt buộc nào đang bị vi phạm hoặc bỏ qua trái phép.
7. **Quyết định:** release, release có giới hạn, trì hoãn hoặc từ chối.
8. **Thông báo và lưu hồ sơ:** ghi người quyết định, thời điểm, phạm vi, lý do và điều kiện.
9. **Theo dõi sau release:** giám sát chỉ số, điều kiện dừng và thời điểm đánh giá tiếp.

Release authority phải biết những rủi ro nào đã được chấp nhận, ai chấp nhận và trong giới hạn nào. Việc một ticket chuyển sang Done hoặc pipeline màu xanh không tự động tạo thành quyết định phát hành.

## 11. Các lựa chọn quyết định phát hành

Không phải lúc nào quyết định cũng chỉ có “phát hành” hoặc “không phát hành”. Có thể có các lựa chọn:

| Quyết định | Khi nào cân nhắc | Điều kiện cần ghi |
| --- | --- | --- |
| Release | Cổng bắt buộc đạt, rủi ro còn lại trong giới hạn và vận hành sẵn sàng | Phiên bản, phạm vi, thời điểm và người quyết định |
| Release có giới hạn | Có thể khoanh vùng người dùng, lưu lượng, tính năng hoặc khu vực | Giới hạn, giám sát, feature flag, điều kiện dừng và kế hoạch mở rộng |
| Defer / trì hoãn | Thiếu bằng chứng, phê duyệt hoặc điều kiện vận hành | Khoảng trống, người xử lý, hạn và điều kiện đánh giá lại |
| Reject / từ chối | Rủi ro vượt giới hạn hoặc điều kiện bắt buộc không đạt | Lý do, yêu cầu cần khắc phục và điều kiện xem xét lại |
| Rollback / dừng rollout | Sau phát hành xuất hiện tín hiệu vượt ngưỡng hoặc kiểm soát thất bại | Người kích hoạt, ngưỡng, quy trình và thông báo |

Release có giới hạn vẫn là một quyết định phát hành và cần đủ thẩm quyền. Không nên gọi một triển khai nội bộ là “không phải release” để né quy trình nếu nó có thể tác động đến dữ liệu, người dùng hoặc hệ thống thật.

## 12. Quyền phủ quyết và điều kiện dừng

Một số vai trò kiểm soát có thể được trao quyền yêu cầu dừng hoặc chặn phát hành khi phát hiện vi phạm thuộc phạm vi chuyên môn. Ví dụ:

- Security có thể yêu cầu dừng khi phát hiện lỗ hổng nghiêm trọng hoặc kiểm soát bảo mật bắt buộc không hoạt động.
- Privacy hoặc chủ sở hữu dữ liệu có thể chặn việc xử lý/chia sẻ dữ liệu không có căn cứ.
- Vận hành có thể yêu cầu trì hoãn khi không có khả năng giám sát, backup hoặc phục hồi theo yêu cầu.
- Release manager có thể dừng rollout khi chỉ số production vượt ngưỡng đã phê duyệt.

Quyền phủ quyết cần được định nghĩa chính thức: loại sự kiện nào kích hoạt, phạm vi chặn, ai có thể gỡ chặn và bằng chứng cần có. Nếu không có quyền phủ quyết chính thức, nhóm vẫn cần cơ chế escalation nhanh tới người có thẩm quyền.

Điều kiện dừng sau release nên đo được, ví dụ tỷ lệ lỗi giao dịch vượt ngưỡng trong cửa sổ thời gian, xuất hiện giao dịch trùng đã xác nhận, backlog vượt giới hạn hoặc phát hiện truy cập dữ liệu trái phép. Các giá trị phải được xác định theo SLO, mức chịu đựng và khả năng ứng phó của hệ thống.

## 13. Xử lý bất đồng và chuyển cấp

Những bên liên quan có thể đánh giá rủi ro khác nhau. Chủ sản phẩm có thể ưu tiên thời điểm ra mắt; kỹ thuật lo ngại lỗi dữ liệu; bảo mật không chấp nhận một lỗ hổng; vận hành chưa sẵn sàng hỗ trợ.

Khi bất đồng:

1. Tách sự kiện đã xác minh khỏi giả định và ý kiến.
2. Ghi rõ rủi ro, tác động, xác suất, bất định và bằng chứng.
3. Xác định tiêu chí hoặc chính sách nào đang được áp dụng.
4. Kiểm tra cấp thẩm quyền và giới hạn ủy quyền.
5. Đề xuất các phương án có phạm vi, chi phí, biện pháp kiểm soát và hậu quả rõ.
6. Chuyển cấp tới vai trò hoặc hội đồng được chỉ định nếu vượt thẩm quyền hoặc chưa thống nhất.
7. Ghi quyết định cuối cùng, ý kiến khác biệt quan trọng và điều kiện xem xét lại.

Không nên giải quyết bất đồng bằng cách để người có chức danh cao nhất tự động bỏ qua ý kiến chuyên môn bắt buộc. Quy trình phải chỉ rõ các quyền kiểm soát độc lập và cách xử lý khi chúng không đồng thuận.

### Quy trình khẩn cấp

Trong sự cố khẩn cấp, tổ chức có thể có đường phê duyệt nhanh. Quy trình này vẫn cần:

- Người có quyền kích hoạt và phạm vi hành động được phép.
- Mục đích khẩn cấp và lý do không thể theo quy trình thông thường.
- Biện pháp giới hạn tác động và khả năng rollback.
- Ghi lại hành động, người thực hiện và thời điểm.
- Rà soát sau sự cố bởi các vai trò liên quan.

Khẩn cấp không phải lý do để bỏ qua các nghĩa vụ không thể miễn trừ. Nếu quy trình không cho phép ngoại lệ, cần dừng hoặc chọn phương án an toàn khác.

## 14. Ghi nhận quyết định và khả năng truy nguyên

Mỗi quyết định chấp nhận rủi ro hoặc phát hành cần có hồ sơ đủ để người khác hiểu vì sao quyết định được đưa ra và ai chịu trách nhiệm.

Các trường nên có:

| Trường | Nội dung |
| --- | --- |
| Decision ID | Mã định danh quyết định |
| Sản phẩm/phiên bản | Sản phẩm, build, commit hoặc release candidate |
| Phạm vi | Tính năng, môi trường, người dùng, khu vực và tỷ lệ rollout |
| Rủi ro liên quan | Mã rủi ro, mô tả, tác động và rủi ro còn lại |
| Bằng chứng | Báo cáo test, lỗi, đánh giá bảo mật, SLI/SLO và giới hạn |
| Phê duyệt bắt buộc | Vai trò, trạng thái và liên kết hồ sơ |
| Người chấp nhận rủi ro | Người, vai trò, phạm vi ủy quyền và thời điểm |
| Release authority | Người hoặc hội đồng ra quyết định phát hành |
| Quyết định | Release, limited release, defer, reject hoặc rollback |
| Điều kiện | Hành động, chủ sở hữu, hạn và bằng chứng đóng |
| Điều kiện dừng | Ngưỡng hoặc sự kiện kích hoạt dừng/rollback |
| Hiệu lực | Ngày bắt đầu, ngày hết hạn và thời điểm rà soát |
| Thông báo | Các nhóm nhận quyết định và thời điểm thông báo |

Hồ sơ nên liên kết tới nguồn bằng chứng thay vì sao chép toàn bộ log hoặc báo cáo. Cần lưu phiên bản của tài liệu và bảo đảm người kiểm tra có thể truy cập đúng nguồn.

### Mẫu quyết định

```text
DECISION-ID: REL-2027-042
PRODUCT / BUILD: Booking API / 5.6.0-rc3
SCOPE: Internal users, 10% traffic, one region
QUALITY EVIDENCE:
  - Functional regression: PASS
  - Payment integration: PASS
  - Full cross-region recovery: NOT RUN
OPEN RISK:
  - Recovery in secondary region has not been verified at target data volume
RISK OWNER: Service owner
RISK ASSESSMENT: Medium residual risk, limited to failover readiness
CONTROLS:
  - Primary region only for this rollout
  - Backup health and replication lag monitored
  - Rollback procedure rehearsed
RISK ACCEPTANCE:
  - Approved by: designated technology risk authority
  - Scope: limited rollout only
  - Expires: 2027-08-20
REQUIRED ACTION:
  - Owner: platform recovery team
  - Due: 2027-08-18
  - Evidence: full-volume recovery exercise
STOP CONDITION:
  - Replication lag exceeds approved limit or backup verification fails
RELEASE DECISION: LIMITED RELEASE
RELEASE AUTHORITY: Release board delegate
DECIDED AT: 2027-08-12 10:00 UTC
NEXT REVIEW: 2027-08-18
```

Mẫu trên chỉ minh họa cấu trúc. Tên vai trò, mức rủi ro, ngày và ngưỡng phải lấy từ quy trình và bằng chứng thực tế; không sao chép trực tiếp làm chính sách.

## 15. Theo dõi sau khi chấp nhận rủi ro hoặc phát hành

Chấp nhận rủi ro không kết thúc trách nhiệm quản lý. Sau quyết định, cần theo dõi xem giả định ban đầu có còn đúng và biện pháp kiểm soát có hoạt động hay không.

Các hoạt động thường cần:

- Theo dõi chỉ số vận hành, lỗi, cảnh báo và phản hồi người dùng liên quan.
- Kiểm tra các giới hạn rollout và feature flag.
- Theo dõi hành động còn mở, chủ sở hữu và thời hạn.
- Xác minh điều kiện dừng và khả năng rollback vẫn sẵn sàng.
- Đánh giá lại khi có thay đổi phiên bản, tải, dữ liệu, nhà cung cấp hoặc phạm vi người dùng.
- Ghi nhận sự cố, near miss và bằng chứng mới vào hồ sơ rủi ro.

Rủi ro cần được đánh giá lại khi:

- Xuất hiện sự cố hoặc lỗi mới làm tăng tác động/khả năng xảy ra.
- Biện pháp kiểm soát thất bại hoặc không còn được giám sát.
- Hành động giảm thiểu quá hạn.
- Phạm vi release mở rộng vượt giới hạn đã chấp nhận.
- Quyết định hết hạn hoặc người phê duyệt thay đổi.
- Có thay đổi pháp lý, hợp đồng, chính sách hoặc mối đe dọa.

Kết quả rà soát có thể là tiếp tục trong điều kiện cũ, đóng rủi ro, gia hạn có phê duyệt, thu hẹp phạm vi, dừng rollout hoặc thu hồi chấp nhận. Gia hạn phải dựa trên đánh giá mới, không nên tự động kéo dài ngày hết hạn.

## 16. Ví dụ thực tế: quyết định phát hành khi còn rủi ro hiệu năng

Giả sử một phiên bản mới của dịch vụ đặt lịch đã hoàn thành kiểm thử chức năng và hồi quy. Bài load test cho thấy p95 của API tìm kiếm đạt mục tiêu trong tải bình thường, nhưng ở giờ cao điểm mô phỏng, p95 cao hơn ngưỡng 15% trong vài phút. Không có mất dữ liệu hoặc đặt trùng, nhưng một số người dùng có thể phải chờ lâu.

Nhóm cần phân định:

- QA cung cấp kết quả, mô hình tải, phân vị, lỗi và giới hạn môi trường.
- Kỹ thuật phân tích nguyên nhân, ước lượng phạm vi ảnh hưởng và phương án tối ưu.
- Chủ sở hữu dịch vụ nhận trách nhiệm theo dõi rủi ro hiệu năng.
- Chủ sản phẩm đánh giá ảnh hưởng tới người dùng và lựa chọn phạm vi rollout.
- Vận hành xác nhận dashboard, cảnh báo, khả năng tăng tài nguyên và rollback.
- Người có thẩm quyền rủi ro quyết định liệu sai lệch này có thể được chấp nhận trong phạm vi giới hạn.
- Release authority quyết định có cho phép triển khai giới hạn hay không sau khi xác minh mọi cổng bắt buộc.

Một phương án có thể là mở cho 5% lưu lượng trong một khu vực, theo dõi p95 và tỷ lệ lỗi, tăng tài nguyên theo ngưỡng đã duyệt và dừng rollout nếu vượt điều kiện dừng. Điều kiện giảm thiểu cần có chủ sở hữu và hạn hoàn tất tối ưu.

Trước khi quyết định, nhóm phải xác minh sai lệch hiệu năng không vi phạm cam kết bắt buộc hoặc ảnh hưởng tới một nhóm người dùng cần bảo vệ. Nếu chưa có khả năng giám sát hoặc rollback, phương án giới hạn cũng có thể không đủ an toàn.

Trong hồ sơ, người chấp nhận rủi ro hiệu năng và release authority phải được ghi riêng nếu là hai vai trò khác nhau. Khi mở rộng từ 5% lên 100%, cần xem xét lại quyết định vì phạm vi và mức phơi lộ đã thay đổi.

## 17. Những lỗi quản trị thường gặp

- **Không xác định chủ sở hữu rủi ro:** mọi người đều biết vấn đề nhưng không ai theo dõi đến khi đóng.
- **Nhầm người cung cấp bằng chứng với người chấp nhận:** QA bị yêu cầu tự approve rủi ro chỉ vì họ là người báo cáo kết quả.
- **Một người tự phê duyệt mọi thứ:** bỏ qua quyền chuyên môn và kiểm soát độc lập.
- **Dựa vào chức danh thay cho ủy quyền:** không rõ người đó có quyền với loại rủi ro hoặc phạm vi này không.
- **Chấp nhận rủi ro không giới hạn:** không có phạm vi, thời hạn, điều kiện dừng hoặc biện pháp kiểm soát.
- **Đồng nhất chấp nhận rủi ro với release approval:** rủi ro đã được chấp nhận nhưng cổng phát hành khác vẫn chưa đạt.
- **Bỏ qua điều kiện bắt buộc:** dùng ngoại lệ kinh doanh để thay thế nghĩa vụ pháp lý, hợp đồng hoặc chính sách.
- **Quyết định bằng lời nói:** không có hồ sơ, người phê duyệt hoặc thời điểm.
- **Không chuyển cấp khi vượt thẩm quyền:** người quản lý cấp thấp tự chấp nhận rủi ro vượt giới hạn.
- **Không đánh giá lại khi mở rộng rollout:** áp dụng quyết định cho phạm vi lớn hơn phạm vi đã duyệt.
- **Không theo dõi sau release:** điều kiện kiểm soát không còn hiệu lực nhưng quyết định vẫn được xem là hợp lệ.

## 18. Checklist xác định quyền chấp nhận rủi ro và quyền phát hành

- [ ] Đã xác định các loại rủi ro và tiêu chí chất lượng liên quan.
- [ ] Đã phân biệt điều kiện bắt buộc với mục tiêu có thể cân nhắc theo rủi ro.
- [ ] Mỗi rủi ro có chủ sở hữu và người theo dõi.
- [ ] Vai trò cung cấp bằng chứng, người chấp nhận rủi ro và release authority được phân định.
- [ ] Ma trận thẩm quyền nêu rõ cấp phê duyệt theo loại và mức độ rủi ro.
- [ ] Giới hạn ủy quyền, điều kiện chuyển cấp và quyền phủ quyết được xác định.
- [ ] Rủi ro còn lại có bằng chứng, biện pháp kiểm soát và phạm vi cụ thể.
- [ ] Mọi phê duyệt chuyên môn bắt buộc đã được xác nhận.
- [ ] Quyết định release có xem xét chất lượng, vận hành, hỗ trợ, giám sát và rollback.
- [ ] Điều kiện trước phát hành và hành động sau phát hành được phân biệt.
- [ ] Quyết định có người phê duyệt, thời điểm, hiệu lực, hạn và điều kiện dừng.
- [ ] Phạm vi rollout không vượt quá phạm vi rủi ro đã được chấp nhận.
- [ ] Có kế hoạch rà soát, thu hồi hoặc cập nhật quyết định khi điều kiện thay đổi.

## 19. Những điểm cần ghi nhớ

- Chấp nhận rủi ro và quyết định phát hành là hai quyết định liên quan nhưng khác nhau.
- Chủ sở hữu rủi ro theo dõi và quản lý rủi ro; người chấp nhận phải có thẩm quyền phù hợp với loại và mức độ rủi ro.
- Nhóm kiểm thử và chuyên gia cung cấp bằng chứng, phân tích và khuyến nghị; kết quả kiểm thử không tự tạo ra quyền phát hành.
- Release authority tổng hợp các cổng chất lượng, phê duyệt bắt buộc, rủi ro còn lại và mức sẵn sàng vận hành.
- Quyền quyết định cần gắn với khẩu vị rủi ro, ngưỡng, giới hạn ủy quyền và cơ chế chuyển cấp.
- Điều kiện bắt buộc theo luật, hợp đồng hoặc chính sách không thể được bỏ qua bằng quyết định kinh doanh thông thường.
- Mọi quyết định cần có phạm vi, bằng chứng, người phê duyệt, thời hạn, biện pháp kiểm soát và điều kiện dừng.
- Release có giới hạn vẫn cần phê duyệt và phải được đánh giá lại khi mở rộng phạm vi.
- Theo dõi sau release và đánh giá lại khi có sự cố, thay đổi hoặc hành động quá hạn.

## Câu hỏi tự kiểm tra

1. Phân biệt chủ sở hữu rủi ro, người chấp nhận rủi ro và release authority.
2. Vì sao kết quả kiểm thử đạt không tự động có nghĩa sản phẩm được phép phát hành?
3. Hãy mô tả một tình huống mà chủ sản phẩm có thể chấp nhận rủi ro nghiệp vụ nhưng không có quyền chấp nhận rủi ro bảo mật.
4. Ma trận RACI giúp làm rõ quyền quyết định như thế nào? Vì sao mỗi quyết định cần một người chịu trách nhiệm cuối cùng rõ ràng?
5. Khẩu vị rủi ro, ngưỡng chấp nhận và giới hạn ủy quyền khác nhau ra sao?
6. Những loại điều kiện nào có thể không được miễn trừ bằng quy trình chấp nhận rủi ro thông thường?
7. Nếu các nhóm không thống nhất về việc phát hành, cần thu thập thông tin và chuyển cấp như thế nào?
8. Một bản release được chấp nhận cho 5% lưu lượng. Vì sao cần đánh giá lại trước khi mở rộng lên 100%?
9. Hãy lập ma trận quyền quyết định cho một sản phẩm có rủi ro về dữ liệu, hiệu năng và vận hành.
10. Viết một quyết định phát hành có điều kiện, nêu rõ người chấp nhận rủi ro, release authority, phạm vi, bằng chứng, điều kiện dừng và thời hạn.
