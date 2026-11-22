# Đặt ngưỡng chấp nhận lỗi theo tác động và khả năng khắc phục

Không phải mọi lỗi đều có cùng mức độ nghiêm trọng, và không phải mọi lỗi đã biết đều buộc phải chặn phát hành. Một lỗi nhỏ về cách trình bày có thể gây khó chịu nhưng không ảnh hưởng đến giao dịch; một lỗi hiếm gặp trong quy trình hoàn tiền có thể gây thất thoát tiền hoặc làm sai lệch dữ liệu; một lỗi nghiêm trọng khác có thể được giảm thiểu tạm thời bằng cách quay lui phiên bản hoặc chuyển sang quy trình vận hành an toàn.

Đặt ngưỡng chấp nhận lỗi là việc xác định trước loại lỗi nào có thể được phát hành cùng sản phẩm, lỗi nào cần sửa trước, lỗi nào chỉ được chấp nhận khi có biện pháp giảm thiểu và người có thẩm quyền phê duyệt. Quyết định cần dựa trên tác động thực tế, phạm vi ảnh hưởng, khả năng phát hiện, khả năng khắc phục và rủi ro còn lại.

Một ngưỡng tốt giúp nhóm đưa ra quyết định nhất quán, giải thích được và có thể kiểm tra lại. Nó không chỉ dựa vào nhãn Critical, High, Medium hay Low; cần xét người dùng bị ảnh hưởng, hậu quả nghiệp vụ, dữ liệu, bảo mật, thời gian phục hồi, cách làm việc thay thế và khả năng đảo ngược thay đổi. Ngưỡng cũng phải phản ánh bối cảnh phát hành: một lỗi có thể chấp nhận trong bản thử nghiệm giới hạn nhưng không thể chấp nhận khi mở rộng cho toàn bộ khách hàng.

## 1. Phân biệt mức độ nghiêm trọng, mức ưu tiên và khả năng chấp nhận

Ba khái niệm này liên quan nhưng trả lời các câu hỏi khác nhau.

- **Mức độ nghiêm trọng (severity):** hậu quả của lỗi nếu nó xảy ra trong điều kiện đã xác định.
- **Mức ưu tiên xử lý (priority):** mức độ khẩn cấp và thứ tự nhóm cần xử lý lỗi so với các công việc khác.
- **Khả năng chấp nhận lỗi:** liệu rủi ro còn lại có thể được phép tồn tại trong phạm vi phát hành cụ thể hay không, với điều kiện và sự phê duyệt nào.

Ví dụ, một lỗi làm trang quản trị hiển thị sai màu có thể có severity thấp nhưng priority cao nếu nó xuất hiện trong buổi trình diễn quan trọng vào ngày mai. Một lỗi hiếm khi làm giao dịch bị ghi nhận hai lần có thể có severity rất cao dù priority điều tra ban đầu cần thời gian để tái hiện. Một lỗi severity cao có thể được phát hành trong một phạm vi thử nghiệm hạn chế nếu đã có biện pháp ngăn người dùng gặp phải và người có thẩm quyền chấp nhận rủi ro; điều đó không làm giảm severity của lỗi.

### Vì sao không nên dùng một nhãn duy nhất?

Nếu nhóm chỉ có một trường “mức độ lỗi”, các quyết định dễ bị lẫn lộn. Người sửa có thể ưu tiên theo thời hạn, trong khi người quyết định phát hành cần hiểu hậu quả. Báo cáo cũng khó phân biệt lỗi nghiêm trọng nhưng ít xảy ra với lỗi thường xuyên nhưng tác động nhỏ.

Nên ghi riêng ít nhất:

- Severity.
- Priority.
- Phạm vi và điều kiện tái hiện.
- Khả năng khắc phục hoặc workaround.
- Rủi ro còn lại.
- Trạng thái quyết định phát hành.
- Người chấp nhận ngoại lệ và thời hạn xem xét.

## 2. Đánh giá tác động của lỗi theo nhiều chiều

Tác động không chỉ là số người nhìn thấy lỗi. Cần xem xét hậu quả đối với người dùng, nghiệp vụ, dữ liệu, tiền, an toàn, bảo mật, tuân thủ và hoạt động vận hành.

### Tác động đến người dùng và hành trình cốt lõi

Hãy xác định:

- Người dùng nào bị ảnh hưởng: tất cả, một vai trò, một nhóm khách hàng hay một nền tảng.
- Bao nhiêu người hoặc giao dịch có thể gặp lỗi.
- Họ có thể hoàn thành mục tiêu chính hay không.
- Có cách thay thế dễ hiểu và khả thi không.
- Lỗi có gây mất niềm tin, nhầm lẫn hoặc thao tác sai tiếp theo không.
- Tình trạng kéo dài bao lâu và có thể tái diễn không.

Một lỗi chỉ xuất hiện ở một nhóm người dùng vẫn có thể nghiêm trọng nếu nhóm đó thực hiện nghiệp vụ quan trọng hoặc xử lý dữ liệu nhạy cảm.

### Tác động đến nghiệp vụ và tài chính

Cần đánh giá khả năng:

- Mất doanh thu hoặc phát sinh giao dịch sai.
- Tính sai giá, thuế, phí, chiết khấu hoặc số dư.
- Ghi nhận thanh toán, hoàn tiền hoặc đối soát không chính xác.
- Làm gián đoạn hoạt động của nhân viên hoặc đối tác.
- Tạo chi phí hỗ trợ, xử lý thủ công hoặc bồi hoàn.
- Làm trễ cam kết dịch vụ hoặc nghĩa vụ hợp đồng.

Tác động tài chính không chỉ là giá trị một giao dịch. Một lỗi nhỏ lặp lại trên hàng nghìn giao dịch có thể tạo ra hậu quả lớn.

### Tác động đến dữ liệu

Dữ liệu có thể bị:

- Mất hoặc không thể phục hồi.
- Ghi trùng hoặc ghi sai.
- Gắn nhầm chủ sở hữu.
- Cập nhật không nhất quán giữa các hệ thống.
- Lộ ra ngoài phạm vi quyền được phép.
- Không thể đối soát hoặc truy vết.
- Hỏng theo cách chỉ phát hiện sau một thời gian dài.

Lỗi dữ liệu cần được đánh giá cẩn thận vì người dùng có thể không nhìn thấy ngay. Một giao diện hiển thị đúng không chứng minh dữ liệu phía sau chính xác.

### Tác động đến bảo mật, quyền riêng tư và tuân thủ

Nếu lỗi có thể làm lộ thông tin, vượt quyền, bỏ qua xác thực, thay đổi dấu vết kiểm toán hoặc vi phạm nghĩa vụ pháp lý, không nên đánh giá nó như lỗi chức năng thông thường. Cần áp dụng quy trình chuyên môn tương ứng và xem xét nghĩa vụ thông báo, giới hạn xử lý hoặc dừng chức năng.

Một workaround vận hành không làm cho lỗ hổng bảo mật tự động trở nên chấp nhận được. Cần có đánh giá của người có thẩm quyền về bảo mật và tuân thủ.

### Tác động đến an toàn và hoạt động vận hành

Với sản phẩm ảnh hưởng đến thiết bị, sức khỏe, phương tiện, hạ tầng hoặc quy trình có rủi ro an toàn, hậu quả tiềm tàng cần được đánh giá theo tiêu chuẩn và quy trình chuyên ngành. Không được dùng mức độ phổ biến thấp để xem nhẹ hậu quả nghiêm trọng.

Trong hệ thống vận hành, lỗi có thể làm mất khả năng giám sát, cảnh báo hoặc phục hồi. Một lỗi ở chức năng hỗ trợ có thể trở nên nghiêm trọng nếu nó làm nhóm không phát hiện được một lỗi khác.

## 3. Đánh giá phạm vi và xác suất xảy ra

Tác động là một phần của rủi ro. Nhóm cũng cần hiểu điều kiện xảy ra và mức phơi nhiễm.

Các câu hỏi cần xem xét:

- Lỗi xảy ra với mọi lần thực hiện hay chỉ ở một điều kiện cụ thể?
- Điều kiện đó có phổ biến trong dữ liệu thực tế không?
- Lỗi xuất hiện trên mọi nền tảng hay chỉ một trình duyệt, thiết bị hoặc phiên bản?
- Có phụ thuộc vào thời điểm, tải, thứ tự sự kiện hoặc thao tác đồng thời không?
- Bao nhiêu người dùng, bản ghi hoặc giao dịch có thể bị ảnh hưởng?
- Có thể phát hiện lỗi ngay khi xảy ra không?
- Lỗi có thể lan sang các dịch vụ hoặc quy trình khác không?
- Có bằng chứng từ log, metric, sự cố cũ hoặc kiểm thử để ước lượng không?

Không nên gán xác suất chính xác khi dữ liệu không đủ. Có thể dùng các mức định tính như hiếm, không thường xuyên, có khả năng và thường xuyên, kèm cơ sở đánh giá.

### Tách xác suất xảy ra khỏi khả năng phát hiện

Một lỗi có thể hiếm nhưng khó phát hiện. Nếu không có log hoặc đối soát, lỗi có thể tồn tại lâu và tích lũy hậu quả. Vì vậy, cần xem khả năng phát hiện như một chiều riêng khi đánh giá rủi ro.

Ví dụ, một lỗi làm sai số dư chỉ trong trường hợp hoàn tiền một phần có thể không xuất hiện trong kiểm thử thông thường. Nếu không có đối soát tự động, lỗi có thể chỉ được phát hiện khi khách hàng khiếu nại.

## 4. Đánh giá khả năng khắc phục

Khả năng khắc phục cho biết nhóm có thể ngăn, giảm, đảo ngược hoặc sửa hậu quả của lỗi đến mức nào sau khi nó xảy ra. Đây là yếu tố quan trọng khi quyết định có thể chấp nhận rủi ro trong một phạm vi phát hành hay không.

Không nên đánh đồng “có workaround” với “có thể khắc phục”. Một hướng dẫn thủ công có thể giúp người dùng tiếp tục công việc nhưng không sửa dữ liệu đã sai. Một nút tắt chức năng có thể ngăn lỗi mới nhưng không phục hồi giao dịch đã bị ảnh hưởng.

### Những chiều cần đánh giá

**Khả năng ngăn tiếp tục phát sinh:** có thể tắt feature flag, dừng job, giới hạn vai trò, chặn loại giao dịch hoặc quay lui phiên bản không?

**Khả năng phục hồi dữ liệu:** có backup, log, event history hoặc quy trình đối soát để khôi phục dữ liệu không? Có biết chính xác bản ghi nào bị ảnh hưởng không?

**Khả năng đảo ngược:** thay đổi có thể rollback an toàn không? Dữ liệu có mất thông tin khi chuyển đổi không? Phiên bản cũ có tương thích với schema hiện tại không?

**Thời gian khắc phục:** nhóm có thể phục hồi trong vài phút, vài giờ hay nhiều ngày? Thời gian đó có nằm trong ngưỡng nghiệp vụ chấp nhận được không?

**Độ tin cậy của workaround:** người dùng có thể thực hiện cách thay thế đúng và nhất quán không? Workaround có tạo thêm rủi ro, chi phí hoặc thao tác thủ công dễ sai không?

**Khả năng xác minh sau khắc phục:** nhóm có thể chứng minh dữ liệu và hành vi đã trở lại đúng không? Có thể kiểm tra toàn bộ phạm vi ảnh hưởng hay chỉ một mẫu?

### Phân biệt các biện pháp

| Biện pháp | Mục đích | Giới hạn cần xét |
|---|---|---|
| Workaround cho người dùng | Giúp hoàn thành công việc bằng cách khác | Có thể tăng chi phí và nguy cơ thao tác sai |
| Feature flag hoặc kill switch | Ngăn người dùng đi vào chức năng lỗi | Không sửa dữ liệu hoặc giao dịch đã phát sinh |
| Rollback ứng dụng | Quay lại mã phiên bản trước | Không nhất thiết đảo ngược schema hoặc dữ liệu |
| Roll-forward | Triển khai bản sửa tiếp theo | Cần kiểm thử và theo dõi tác động mới |
| Backup và restore | Phục hồi dữ liệu hoặc trạng thái | Có thể mất dữ liệu phát sinh sau thời điểm backup |
| Đối soát và sửa dữ liệu | Tìm và sửa bản ghi bị ảnh hưởng | Cần xác định phạm vi và quy tắc sửa chính xác |
| Chạy lại job hoặc event | Hoàn tất xử lý bị gián đoạn | Cần idempotency và tránh xử lý trùng |
| Hạn chế phạm vi phát hành | Giảm số người dùng hoặc giao dịch phơi nhiễm | Không loại bỏ lỗi và cần theo dõi chặt |

Một biện pháp chỉ được tính là khả năng khắc phục khi đã xác định người thực hiện, điều kiện kích hoạt, thời gian, quyền cần có và cách xác minh kết quả. Một kế hoạch chưa từng diễn tập hoặc chưa có bằng chứng chỉ nên được coi là giả định.

## 5. Phân biệt workaround, khắc phục và phục hồi

Ba khái niệm thường bị dùng thay thế cho nhau nhưng có ý nghĩa khác nhau.

- **Workaround:** cách tạm thời tránh hoặc giảm ảnh hưởng để người dùng hoặc hệ thống tiếp tục hoạt động.
- **Khắc phục (remediation):** hành động sửa nguyên nhân hoặc ngăn lỗi tiếp tục xảy ra.
- **Phục hồi (recovery):** đưa dịch vụ, dữ liệu và hoạt động trở lại trạng thái được chấp nhận sau sự cố.

Ví dụ, nếu thao tác hoàn tiền tạo giao dịch trùng:

- Workaround có thể là tạm dừng hoàn tiền tự động và chuyển các yêu cầu sang hàng đợi xử lý thủ công.
- Remediation là sửa cơ chế idempotency và kiểm tra điều kiện cập nhật trạng thái.
- Recovery là đối soát giao dịch đã phát sinh, xác định khoản hoàn trùng và xử lý theo quy trình tài chính.

Có workaround không có nghĩa lỗi đã được sửa. Có bản sửa cũng không có nghĩa dữ liệu bị ảnh hưởng đã được phục hồi. Quyết định chấp nhận cần xem xét cả ba.

## 6. Xây dựng thang severity có tiêu chí rõ

Tổ chức nên định nghĩa một thang severity nhất quán. Có thể dùng bốn hoặc năm mức. Ví dụ dưới đây dùng bốn mức để dễ áp dụng; tên và ngưỡng cụ thể cần điều chỉnh theo sản phẩm.

| Mức | Mô tả tác động | Ví dụ |
|---|---|---|
| S1 – Nghiêm trọng | Gây mất dữ liệu, sai giao dịch diện rộng, lộ dữ liệu nhạy cảm, vượt quyền nghiêm trọng hoặc làm ngừng chức năng cốt lõi không có cách phục hồi an toàn | Người dùng có thể xem dữ liệu của tài khoản khác; thanh toán bị ghi nợ lặp |
| S2 – Cao | Làm gián đoạn đáng kể quy trình quan trọng, ảnh hưởng nhiều người dùng hoặc gây sai dữ liệu có thể sửa nhưng cần xử lý đáng kể | Không thể tạo đơn cho một nhóm khách hàng lớn; đối soát sai nhưng có thể xác định và sửa |
| S3 – Trung bình | Ảnh hưởng giới hạn, một phần chức năng hoặc nhóm người dùng; có workaround khả thi với chi phí chấp nhận được | Bộ lọc báo cáo sai trong một điều kiện; người dùng có thể hoàn thành bằng cách khác |
| S4 – Thấp | Tác động nhỏ, chủ yếu về trình bày hoặc tiện ích, không ảnh hưởng dữ liệu hay quy trình cốt lõi | Khoảng cách giao diện chưa đồng nhất; thông báo phụ có lỗi chính tả |

### Quy tắc nâng mức severity

Không nên chỉ dựa vào số người bị ảnh hưởng. Một lỗi phạm vi hẹp vẫn có thể là S1 nếu nó gây lộ dữ liệu, mất dữ liệu không thể phục hồi hoặc ảnh hưởng đến an toàn.

Có thể nâng mức khi:

- Tác động liên quan đến tiền, quyền, dữ liệu nhạy cảm hoặc nghĩa vụ pháp lý.
- Không thể xác định đầy đủ phạm vi bản ghi bị ảnh hưởng.
- Lỗi có thể lan rộng hoặc tái diễn tự động.
- Không có cách dừng an toàn.
- Khả năng phát hiện thấp và hậu quả có thể tích lũy.
- Workaround có nguy cơ gây lỗi thứ cấp.

### Ghi rõ điều kiện áp dụng

Severity cần gắn với điều kiện xảy ra và bằng chứng. Ví dụ: “S2 khi người dùng có vai trò X thực hiện thao tác Y trên bản ghi đã ở trạng thái Z; chưa quan sát thấy ảnh hưởng ở vai trò khác.” Cách mô tả này giúp tránh đánh giá quá rộng hoặc quá hẹp.

## 7. Kết hợp tác động và khả năng khắc phục thành ngưỡng chấp nhận

Severity cho biết hậu quả; khả năng khắc phục cho biết nhóm có thể kiểm soát hậu quả đến mức nào. Hai chiều này nên được xem cùng nhau.

Một lỗi có tác động cao nhưng có thể ngăn hoàn toàn bằng kill switch đã được diễn tập có thể có phương án phát hành giới hạn trong một số bối cảnh. Tuy nhiên, nếu lỗi đã làm sai dữ liệu và không thể xác định bản ghi bị ảnh hưởng, khả năng khắc phục thấp làm rủi ro tăng mạnh.

### Ma trận tác động và khả năng khắc phục

| Tác động | Khắc phục tốt | Khắc phục có điều kiện | Khắc phục kém hoặc chưa rõ |
|---|---|---|---|
| Nghiêm trọng | Chỉ xem xét trong phạm vi hạn chế sau đánh giá chuyên môn và kiểm soát đã được chứng minh; nhiều trường hợp vẫn phải chặn | Thông thường chặn phát hành cho đến khi giảm rủi ro | Chặn phát hành |
| Cao | Có thể xem xét phát hành có điều kiện nếu workaround hiệu quả, được giám sát và có phê duyệt | Cần sửa trước hoặc giới hạn phạm vi với phê duyệt rõ | Chặn phát hành |
| Trung bình | Có thể chấp nhận có kế hoạch sửa và theo dõi | Cân nhắc theo tần suất, nhóm người dùng và chi phí workaround | Thường cần sửa hoặc giới hạn phát hành |
| Thấp | Có thể đưa vào backlog với thời hạn phù hợp | Ghi nhận và theo dõi | Đánh giá lại nếu thiếu khả năng phát hiện làm tác động tăng |

Ma trận là khung ra quyết định, không phải giấy phép tự động. Các lỗi bảo mật, quyền riêng tư, an toàn, mất dữ liệu hoặc nghĩa vụ pháp lý có thể chịu ngưỡng nghiêm ngặt hơn bất kể khả năng workaround.

### Ba kết quả quyết định

Sau khi đánh giá, lỗi thường thuộc một trong ba nhóm:

1. **Không chấp nhận:** phải sửa và xác minh trước khi phát hành hoặc trước khi mở phạm vi liên quan.
2. **Chấp nhận có điều kiện:** chỉ được phát hành khi biện pháp giảm thiểu, giám sát, giới hạn phạm vi, người phê duyệt và thời hạn xử lý đã rõ.
3. **Chấp nhận trong phạm vi hiện tại:** tác động thấp, rủi ro còn lại nằm trong ngưỡng đã thống nhất và có kế hoạch theo dõi hoặc đưa vào backlog.

Không nên dùng trạng thái “chấp nhận” để thay thế việc ghi nhận lỗi. Lỗi vẫn cần có chủ sở hữu và trạng thái xử lý.

## 8. Thiết lập ngưỡng theo loại rủi ro

Một ngưỡng chung có thể chưa đủ cho các loại lỗi có hậu quả rất khác nhau. Nên định nghĩa điều kiện riêng cho các nhóm quan trọng.

### Lỗi chức năng

Xem xét mức ảnh hưởng đến nhiệm vụ, số người dùng, khả năng hoàn thành và workaround. Lỗi ở chức năng cốt lõi thường có ngưỡng chặt hơn lỗi ở chức năng phụ.

### Lỗi dữ liệu và giao dịch

Sai số tiền, mất bản ghi, trùng giao dịch hoặc dữ liệu không nhất quán cần được đánh giá theo phạm vi, khả năng đối soát và khả năng phục hồi. Nếu không xác định được phạm vi dữ liệu, không nên coi đó là lỗi nhỏ chỉ vì chưa có khiếu nại.

### Lỗi bảo mật và quyền riêng tư

Cần đánh giá khả năng truy cập trái phép, loại dữ liệu, phạm vi phơi nhiễm, khả năng khai thác, thời gian tồn tại và nghĩa vụ xử lý. Không nên cho phép phát hành chỉ dựa trên workaround thủ công nếu lỗ hổng vẫn có thể bị khai thác.

### Lỗi hiệu năng và độ sẵn sàng

Xem xét thời gian phản hồi, tỷ lệ lỗi, số người dùng bị ảnh hưởng, thời gian gián đoạn, khả năng mở rộng và mức độ đáp ứng cam kết dịch vụ. Một lỗi hiệu năng chỉ xuất hiện dưới tải cao vẫn quan trọng nếu tải đó thường xảy ra trong mùa cao điểm.

### Lỗi tương thích và nền tảng

Xem xét nền tảng nào được hỗ trợ, tỷ lệ người dùng trên nền tảng đó, khả năng cung cấp giải pháp thay thế và ảnh hưởng đến dữ liệu. Không nên loại một nền tảng khỏi phạm vi chỉ để làm đẹp tỷ lệ test đạt.

### Lỗi trải nghiệm và khả năng tiếp cận

Xem xét liệu người dùng có thể hiểu, điều hướng và hoàn thành nhiệm vụ không. Một lỗi có thể chỉ ảnh hưởng một nhóm người dùng nhưng làm họ không thể sử dụng sản phẩm; khi đó tác động không thể coi là thấp chỉ vì số lượng người dùng nhỏ.

## 9. Xác định ngưỡng theo giai đoạn và phạm vi phát hành

Mức rủi ro có thể được chấp nhận khác nhau giữa các giai đoạn, nhưng không được thay đổi tùy tiện.

### Bản dựng nội bộ

Có thể chấp nhận nhiều lỗi đã biết để tiếp tục thử nghiệm nếu dữ liệu an toàn, người dùng được giới hạn và mục tiêu của bản dựng được thông báo rõ. Tuy nhiên, lỗi làm hỏng môi trường, mất dữ liệu thử nghiệm quan trọng hoặc che giấu kết quả kiểm thử vẫn cần được xử lý.

### Beta hoặc phát hành giới hạn

Có thể giới hạn người dùng, tính năng, khu vực hoặc tỷ lệ lưu lượng để giảm phạm vi phơi nhiễm. Cần có cách thu hồi quyền truy cập, theo dõi chỉ số và hỗ trợ người dùng bị ảnh hưởng.

### Phát hành rộng

Ngưỡng cần chặt hơn vì số người dùng, dữ liệu và giao dịch có thể tăng nhanh. Lỗi nghiêm trọng, lỗi bảo mật chưa xử lý, lỗi dữ liệu không thể đối soát hoặc lỗi ở quy trình cốt lõi không có phương án phục hồi thường là điều kiện chặn.

### Phát hành theo feature flag hoặc canary

Có thể bật dần cho nhóm nhỏ nếu:

- Có tiêu chí chọn nhóm và giới hạn phơi nhiễm.
- Có metric và cảnh báo theo dõi.
- Có kill switch đã kiểm chứng.
- Có điều kiện dừng rollout rõ.
- Có người trực và quy trình xử lý.
- Có thể khôi phục dữ liệu hoặc giao dịch bị ảnh hưởng.

Feature flag chỉ giảm phạm vi ảnh hưởng nếu nó thật sự có thể tắt nhanh và không tạo trạng thái dữ liệu không nhất quán.

## 10. Đặt điều kiện chặn phát hành

Ngưỡng chấp nhận cần chuyển thành tiêu chí cụ thể trong quyết định phát hành. Có thể định nghĩa các điều kiện chặn mặc định như sau:

- Còn lỗi S1 chưa được xử lý hoặc chưa có kiểm soát được phê duyệt theo quy trình chuyên môn.
- Có lỗi bảo mật hoặc quyền riêng tư chưa được đánh giá và xử lý theo chính sách.
- Có nguy cơ mất, sai hoặc lộ dữ liệu mà chưa xác định được phạm vi.
- Chức năng cốt lõi không thể hoàn thành và không có workaround an toàn.
- Không có cách phát hiện hoặc ngăn lỗi tiếp tục gây hậu quả.
- Kiểm thử quan trọng chưa chạy do môi trường hoặc phụ thuộc bị blocked.
- Phương án rollback, khôi phục hoặc đối soát cần thiết chưa được xác minh.
- Rủi ro còn lại chưa có người có thẩm quyền chấp nhận.

Đây là các điều kiện tham khảo. Tổ chức cần điều chỉnh theo loại sản phẩm, nghĩa vụ và mức độ an toàn. Điều quan trọng là điều kiện chặn phải được thống nhất trước khi có áp lực phát hành.

### Điều kiện cho phép phát hành có điều kiện

Có thể xem xét khi tất cả điều kiện sau được đáp ứng:

1. Tác động và phạm vi lỗi đã được hiểu đủ để ra quyết định.
2. Có workaround hoặc biện pháp giảm thiểu khả thi.
3. Biện pháp đã được kiểm tra trong điều kiện đại diện.
4. Có metric, log hoặc cảnh báo để phát hiện tình trạng xấu đi.
5. Có kill switch, rollback hoặc quy trình phục hồi phù hợp.
6. Có người chịu trách nhiệm theo dõi và xử lý.
7. Có người có thẩm quyền chấp nhận rủi ro.
8. Có thời hạn, phạm vi và điều kiện kết thúc ngoại lệ.
9. Có kế hoạch sửa lỗi và xác minh sau phát hành.

Nếu thiếu một điều kiện trọng yếu, quyết định phát hành có điều kiện cần được xem xét lại.

## 11. Xây dựng mức khắc phục và thời gian phục hồi

Khả năng khắc phục cần được cụ thể hóa bằng mục tiêu thời gian và mức dữ liệu có thể mất hoặc phải sửa, khi phù hợp.

Một số khái niệm vận hành:

- **MTTR (Mean Time to Repair/Recover):** thời gian trung bình để sửa hoặc phục hồi sau lỗi; tổ chức cần thống nhất định nghĩa đang dùng.
- **RTO (Recovery Time Objective):** thời gian mục tiêu để khôi phục dịch vụ.
- **RPO (Recovery Point Objective):** mức mất dữ liệu tối đa có thể chấp nhận tính theo thời gian hoặc điểm phục hồi.

Không phải mọi lỗi sản phẩm đều có RTO/RPO, nhưng các khái niệm này hữu ích khi đánh giá khả năng phục hồi dữ liệu và dịch vụ.

Ví dụ, lỗi làm gián đoạn trang báo cáo có thể có RTO vài giờ nếu người dùng vẫn hoàn thành nghiệp vụ khác. Lỗi làm sai số dư tài khoản có thể cần ngăn giao dịch ngay và đối soát trước khi mở lại, bất kể số lượng người dùng bị ảnh hưởng.

### Đánh giá bằng bằng chứng, không chỉ bằng kế hoạch

Một tài liệu ghi “rollback trong 5 phút” chưa chứng minh khả năng đó. Cần có kết quả diễn tập, log, thời gian thực tế và phạm vi đã phục hồi. Tương tự, backup chỉ có giá trị khi đã kiểm tra khả năng restore và tính nhất quán sau phục hồi.

## 12. Quy trình đánh giá và chấp nhận lỗi

Một quy trình rõ giúp quyết định không phụ thuộc vào cảm tính hoặc áp lực từ một cá nhân.

### Bước 1: Ghi nhận lỗi

Ghi mô tả, bước tái hiện, kết quả mong đợi và thực tế, phiên bản, môi trường, dữ liệu, bằng chứng và điều kiện xuất hiện.

### Bước 2: Xác minh và phân loại

Xác định lỗi có thể tái hiện không, có phải lỗi sản phẩm không, phạm vi nào bị ảnh hưởng và có phụ thuộc môi trường hay dữ liệu không. Phân loại severity riêng với priority.

### Bước 3: Đánh giá tác động

Xem xét người dùng, nghiệp vụ, tiền, dữ liệu, bảo mật, tuân thủ, an toàn, vận hành và phạm vi lan truyền.

### Bước 4: Đánh giá khả năng khắc phục

Xác định workaround, kill switch, rollback, restore, đối soát, thời gian phục hồi và khả năng xác minh. Ghi rõ phần nào đã được thử nghiệm và phần nào chỉ là giả định.

### Bước 5: Xác định rủi ro còn lại

Đánh giá khả năng xảy ra, mức phơi nhiễm, khả năng phát hiện và hậu quả sau khi đã áp dụng biện pháp giảm thiểu.

### Bước 6: Đưa ra quyết định

Chọn không chấp nhận, chấp nhận có điều kiện hoặc chấp nhận trong phạm vi hiện tại. Nêu rõ lý do, phạm vi, thời hạn và điều kiện xem xét lại.

### Bước 7: Phê duyệt đúng thẩm quyền

Người sở hữu nghiệp vụ hoặc người có quyền quyết định phát hành chấp nhận rủi ro nghiệp vụ. Các rủi ro chuyên môn như bảo mật, quyền riêng tư, an toàn hoặc tuân thủ cần có đánh giá của người phụ trách tương ứng.

### Bước 8: Theo dõi đến khi đóng

Giao người xử lý, thời hạn, biện pháp giám sát và bằng chứng cần có. Khi lỗi được sửa, chạy kiểm thử lại, hồi quy và xác minh dữ liệu nếu có ảnh hưởng.

## 13. Ai có quyền chấp nhận rủi ro?

Nhóm phát triển hoặc kiểm thử có thể đề xuất cách xử lý nhưng không nên tự chấp nhận mọi rủi ro.

Quyền quyết định cần gắn với loại hậu quả:

| Loại rủi ro | Người hoặc vai trò cần tham gia |
|---|---|
| Hành vi nghiệp vụ và trải nghiệm | Chủ sản phẩm hoặc chủ quy trình |
| Dữ liệu và giao dịch | Chủ sở hữu dữ liệu, nghiệp vụ tài chính hoặc vận hành liên quan |
| Bảo mật | Người phụ trách bảo mật theo chính sách |
| Quyền riêng tư | Người phụ trách quyền riêng tư hoặc tuân thủ |
| An toàn | Vai trò có thẩm quyền theo quy trình an toàn chuyên ngành |
| Độ sẵn sàng và phục hồi | Chủ sở hữu dịch vụ và vận hành |
| Phạm vi phát hành | Người có quyền phê duyệt phát hành |

Một quyết định có thể cần nhiều bên cùng ký nhận. Không nên dùng sự đồng ý của chủ sản phẩm để thay thế đánh giá bảo mật hoặc tuân thủ khi rủi ro thuộc lĩnh vực chuyên môn đó.

### Ghi nhận quyết định

Một ngoại lệ cần có:

- Mã lỗi và mô tả rủi ro.
- Severity và priority.
- Phạm vi và điều kiện xảy ra.
- Bằng chứng hiện có.
- Biện pháp giảm thiểu.
- Rủi ro còn lại.
- Người đề xuất và người phê duyệt.
- Phạm vi phát hành được phép.
- Ngày hết hạn hoặc ngày xem xét lại.
- Điều kiện tự động dừng hoặc thu hồi phát hành.

Không chấp nhận bằng lời nói không có dấu vết. Nếu quyết định được đưa ra trong cuộc họp, cần ghi lại và xác nhận trong hệ thống quản lý công việc.

## 14. Quản lý ngoại lệ có thời hạn

Ngoại lệ không nên trở thành cách trì hoãn vô thời hạn. Mỗi lỗi được chấp nhận cần có thời hạn và điều kiện kết thúc.

Có thể dùng các trạng thái:

- Chờ đánh giá.
- Chờ phê duyệt.
- Chấp nhận có điều kiện.
- Đang giảm thiểu.
- Chờ sửa.
- Chờ kiểm tra lại.
- Đã khắc phục.
- Hết hạn ngoại lệ.
- Đã đóng theo quyết định có ghi nhận.

Khi đến hạn, hệ thống hoặc người sở hữu cần yêu cầu xem xét lại. Nếu chưa xử lý, phải đánh giá lại tác động, bằng chứng và điều kiện phát hành. Không nên tự động gia hạn chỉ vì lỗi vẫn chưa được sửa.

### Điều kiện thu hồi ngoại lệ

Có thể thu hồi quyết định nếu:

- Lỗi xuất hiện với phạm vi rộng hơn dự kiến.
- Workaround không còn hoạt động.
- Có dấu hiệu dữ liệu bị ảnh hưởng.
- Metric vượt ngưỡng cảnh báo.
- Có lỗ hổng hoặc nghĩa vụ mới được phát hiện.
- Phiên bản hoặc cấu hình thay đổi làm biện pháp giảm thiểu mất hiệu lực.
- Thời hạn ngoại lệ đã hết.

## 15. Ví dụ: đánh giá lỗi hoàn tiền bị ghi nhận hai lần

Giả sử trong một điều kiện hiếm, webhook hoàn tiền được gửi lặp và dịch vụ ghi nhận hai giao dịch hoàn tiền. Nhóm cần quyết định có thể phát hành bản sửa khác trong khi chưa xử lý hoàn toàn lỗi này hay không.

### Đánh giá tác động

- Hậu quả: khách hàng có thể nhận tiền hoàn hai lần.
- Phạm vi: có thể ảnh hưởng các giao dịch có webhook lặp.
- Tài chính: phát sinh thất thoát và cần đối soát.
- Dữ liệu: lịch sử giao dịch có thể không phản ánh chính xác số tiền thực.
- Phát hiện: có thể nhận ra qua đối soát, nhưng không chắc phát hiện ngay.
- Lặp lại: phụ thuộc hành vi retry của nhà cung cấp.

Đây là lỗi có tác động cao, có thể nghiêm trọng tùy quy mô và khả năng phát hiện.

### Đánh giá khả năng khắc phục

Nhóm xem xét:

- Có thể tắt xử lý hoàn tiền tự động không?
- Có thể chuyển sang hàng đợi xử lý thủ công an toàn không?
- Có idempotency key hoặc mã giao dịch duy nhất không?
- Có thể xác định mọi giao dịch bị hoàn trùng không?
- Có thể đối soát với nhà cung cấp và sửa số liệu không?
- Có thể ngăn webhook lặp tiếp tục tạo giao dịch không?
- Quy trình khôi phục đã được diễn tập chưa?

Nếu kill switch đã được thử nghiệm, giao dịch mới có thể được chặn an toàn và mọi bản ghi bị ảnh hưởng có thể được xác định, nhóm có thể xem xét phát hành giới hạn một phần chức năng không liên quan, với phê duyệt phù hợp. Nếu không thể xác định giao dịch bị ảnh hưởng hoặc không có cách ngăn hoàn tiền trùng, cần chặn phát hành có liên quan.

### Tiêu chí mở lại

Chỉ mở lại xử lý tự động sau khi:

1. Sửa logic idempotency.
2. Có kiểm thử webhook lặp và sai thứ tự.
3. Đối soát dữ liệu bị ảnh hưởng.
4. Xác minh không tạo giao dịch trùng trong môi trường đại diện.
5. Có metric và cảnh báo theo dõi.
6. Người sở hữu nghiệp vụ và vận hành chấp thuận.

## 16. Ví dụ: lỗi giao diện có workaround rõ ràng

Giả sử một nút lọc trong màn hình báo cáo không phản hồi trên một phiên bản trình duyệt cũ, nhưng người dùng vẫn có thể chọn cùng điều kiện bằng biểu mẫu tìm kiếm nâng cao.

Tác động có thể ở mức trung bình hoặc thấp tùy tỷ lệ người dùng và tầm quan trọng của báo cáo. Workaround đã được xác minh, không làm thay đổi dữ liệu và có thể hướng dẫn dễ dàng. Nhóm có thể chấp nhận có điều kiện cho một bản phát hành giới hạn, ghi rõ trình duyệt bị ảnh hưởng, cung cấp hướng dẫn, theo dõi phản hồi và đặt thời hạn sửa.

Nếu báo cáo đó là cơ sở cho quyết định tài chính hoặc tuân thủ, mức tác động có thể cao hơn. Cùng một lỗi giao diện nhưng bối cảnh nghiệp vụ làm thay đổi ngưỡng chấp nhận.

## 17. Ví dụ: lỗi nghiêm trọng nhưng có thể giới hạn phạm vi

Giả sử một tính năng mới có lỗi phân quyền nhưng đang tắt mặc định bằng feature flag. Tính năng chưa được mở cho người dùng và flag có thể được xác minh ở trạng thái tắt trên mọi môi trường.

Có thể tiếp tục phát hành phần sản phẩm không liên quan nếu:

- Tính năng vẫn bị vô hiệu hóa ở mọi đường truy cập.
- Không có API hoặc worker nào bỏ qua flag.
- Không có dữ liệu nhạy cảm bị ghi hoặc lộ trong nền.
- Có kiểm thử chứng minh trạng thái tắt.
- Có giám sát để phát hiện truy cập ngoài dự kiến.
- Người có thẩm quyền bảo mật đánh giá và chấp thuận phạm vi phát hành.

Lỗi phân quyền vẫn là lỗi nghiêm trọng và tính năng phải tiếp tục bị chặn. Việc phát hành phần khác không có nghĩa đã chấp nhận mở tính năng lỗi.

## 18. Theo dõi ngưỡng lỗi trong quyết định phát hành

Báo cáo phát hành cần cho biết lỗi đang mở theo severity, phạm vi, khả năng khắc phục và quyết định. Không nên chỉ báo cáo tổng số lỗi.

Một bảng tổng hợp có thể gồm:

| Mức | Đang mở | Đã sửa, chờ xác minh | Chấp nhận có điều kiện | Chặn phát hành |
|---|---:|---:|---:|---:|
| S1 | 1 | 0 | 0 | 1 |
| S2 | 2 | 1 | 1 | 1 |
| S3 | 5 | 2 | 2 | 0 |
| S4 | 8 | 1 | 3 | 0 |

Số liệu trên chỉ minh họa. Cần tránh cộng các trạng thái chồng lấn hoặc dùng bảng để che giấu lỗi quan trọng. Mỗi lỗi chấp nhận có điều kiện cần liên kết tới quyết định, biện pháp giảm thiểu và ngày hết hạn.

### Báo cáo rủi ro còn lại

Bên cạnh số lượng, cần tóm tắt:

- Lỗi nghiêm trọng nhất còn mở.
- Người dùng hoặc luồng bị ảnh hưởng.
- Workaround đang áp dụng.
- Bằng chứng về khả năng khắc phục.
- Kiểm thử hoặc điều kiện chưa được xác minh.
- Người chấp nhận rủi ro.
- Thời hạn và điều kiện thu hồi.

Tỷ lệ lỗi đã sửa không đủ để quyết định phát hành. Một lỗi S1 chưa xử lý có thể quan trọng hơn hàng chục lỗi S4 đã đóng.

## 19. Xem xét ngưỡng sau sự cố và thay đổi sản phẩm

Ngưỡng chấp nhận cần được xem lại khi có bằng chứng mới. Một lỗi từng được đánh giá thấp có thể trở nên nghiêm trọng sau khi số người dùng tăng hoặc một workaround không còn khả thi.

Cần xem xét lại khi:

- Lỗi xuất hiện ngoài phạm vi dự kiến.
- Tần suất hoặc tác động tăng.
- Có sự cố thực tế tương tự.
- Dữ liệu cho thấy khả năng phục hồi thấp hơn giả định.
- Thay đổi kiến trúc hoặc nhà cung cấp.
- Thay đổi quy định, hợp đồng hoặc nghĩa vụ.
- Mở rộng thị trường, nền tảng hoặc nhóm người dùng.
- Workaround gây chi phí vận hành quá lớn.
- Ngoại lệ lặp lại qua nhiều phiên bản.

Sau sự cố, hãy so sánh severity dự đoán với hậu quả thực tế. Nếu nhóm đánh giá thấp vì không có metric hoặc không biết cách đối soát, cần cải thiện khả năng quan sát và phục hồi, không chỉ thay đổi nhãn.

## 20. Các sai lầm thường gặp

- **Dùng priority thay cho severity:** lỗi được ưu tiên thấp có thể vẫn có hậu quả nghiêm trọng.
- **Chỉ đếm số người dùng:** một nhóm nhỏ có thể xử lý dữ liệu hoặc giao dịch đặc biệt quan trọng.
- **Xem workaround là sửa lỗi:** cách tránh lỗi không loại bỏ nguyên nhân hoặc phục hồi dữ liệu.
- **Giả định rollback luôn an toàn:** schema và dữ liệu có thể không thể quay ngược.
- **Không đánh giá khả năng phát hiện:** lỗi âm thầm có thể tích lũy hậu quả.
- **Chấp nhận ngoại lệ không thời hạn:** rủi ro tạm thời trở thành nợ không có chủ sở hữu.
- **Dùng một ngưỡng cho mọi loại sản phẩm:** bảo mật, an toàn và dữ liệu cần tiêu chí riêng.
- **Để nhóm kiểm thử tự chấp nhận rủi ro:** quyết định vượt quá thẩm quyền và trách nhiệm.
- **Không kiểm tra biện pháp giảm thiểu:** kế hoạch trên giấy bị coi như bằng chứng.
- **Chỉ báo cáo tổng số lỗi:** các lỗi nghiêm trọng bị che khuất bởi số lượng lỗi nhỏ.
- **Không xem xét lại sau phát hành:** điều kiện và phạm vi ảnh hưởng có thể đã thay đổi.
- **Dùng tỷ lệ pass làm điều kiện duy nhất:** các rủi ro quan trọng có thể chưa được kiểm tra.

## 21. Mẫu đánh giá và quyết định chấp nhận lỗi

Có thể dùng mẫu sau cho mỗi lỗi cần xem xét trong quyết định phát hành:

~~~text
MÃ LỖI:
MÔ TẢ:
PHIÊN BẢN / MÔI TRƯỜNG:
ĐIỀU KIỆN TÁI HIỆN:
BẰNG CHỨNG:

SEVERITY:
PRIORITY:
PHẠM VI ẢNH HƯỞNG:
- Người dùng / vai trò:
- Chức năng / luồng:
- Dữ liệu / giao dịch:
- Bảo mật / tuân thủ / an toàn:
- Tần suất và khả năng xảy ra:

KHẢ NĂNG KHẮC PHỤC:
- Workaround:
- Kill switch / giới hạn phạm vi:
- Rollback / roll-forward:
- Backup / restore / đối soát:
- Thời gian phục hồi:
- Bằng chứng đã diễn tập:
- Giới hạn còn lại:

RỦI RO SAU GIẢM THIỂU:
QUYẾT ĐỊNH:
- Không chấp nhận
- Chấp nhận có điều kiện
- Chấp nhận trong phạm vi hiện tại

PHẠM VI PHÁT HÀNH ĐƯỢC PHÉP:
BIỆN PHÁP GIÁM SÁT:
ĐIỀU KIỆN DỪNG / THU HỒI:
NGƯỜI ĐỀ XUẤT:
NGƯỜI PHÊ DUYỆT:
THỜI HẠN NGOẠI LỆ:
KẾ HOẠCH SỬA VÀ KIỂM TRA LẠI:
TRẠNG THÁI CUỐI:
~~~

Mẫu cần được rút gọn hoặc mở rộng theo mức rủi ro. Với lỗi nghiêm trọng hoặc liên quan dữ liệu, bảo mật và an toàn, không nên bỏ các trường về phạm vi, khả năng phục hồi, phê duyệt và điều kiện dừng.

## 22. Mẫu ngưỡng chấp nhận lỗi cho một bản phát hành

~~~text
BẢN PHÁT HÀNH:
PHẠM VI:
NGÀY QUYẾT ĐỊNH:
NGƯỜI PHÊ DUYỆT:

ĐIỀU KIỆN CHẶN:
- Lỗi nghiêm trọng chưa xử lý:
- Lỗi bảo mật / quyền riêng tư / an toàn:
- Lỗi dữ liệu hoặc giao dịch:
- Luồng cốt lõi không có workaround:
- Kiểm thử quan trọng bị blocked:
- Khả năng rollback / phục hồi chưa xác minh:

ĐIỀU KIỆN CHẤP NHẬN CÓ ĐIỀU KIỆN:
- Severity tối đa được xem xét:
- Phạm vi người dùng:
- Workaround đã xác minh:
- Giám sát và cảnh báo:
- Kill switch / rollback:
- Người sở hữu:
- Thời hạn xử lý:

LỖI CÒN MỞ:
- Mã lỗi:
- Severity:
- Tác động:
- Khả năng khắc phục:
- Quyết định:
- Người phê duyệt:
- Ngày xem xét lại:

RỦI RO CÒN LẠI:
KẾT LUẬN PHÁT HÀNH:
ĐIỀU KIỆN DỪNG ROLLOUT:
KẾ HOẠCH SAU PHÁT HÀNH:
~~~

## Kết luận

Ngưỡng chấp nhận lỗi cần được xác định dựa trên hậu quả nếu lỗi xảy ra và khả năng ngăn chặn, khắc phục hoặc phục hồi sau đó. Nhóm cần đánh giá riêng severity, priority và khả năng chấp nhận; xem xét phạm vi người dùng, nghiệp vụ, dữ liệu, bảo mật, an toàn, khả năng phát hiện và độ tin cậy của workaround.

Một lỗi chỉ nên được chấp nhận khi rủi ro còn lại đã được hiểu, biện pháp giảm thiểu có bằng chứng, phạm vi và thời hạn rõ, có người sở hữu và được phê duyệt đúng thẩm quyền. Các lỗi nghiêm trọng về bảo mật, dữ liệu, an toàn hoặc chức năng cốt lõi cần ngưỡng chặt chẽ và điều kiện chặn cụ thể. Khi quyết định được ghi nhận, theo dõi và xem xét lại theo bằng chứng mới, nhóm có thể cân bằng tiến độ phát hành với mức rủi ro mà sản phẩm và người dùng thực sự có thể chấp nhận.
