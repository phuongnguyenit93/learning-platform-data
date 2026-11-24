# Localized legal notices — Bản địa hóa thông báo pháp lý trong khôi phục tài khoản

## 1. Thông báo pháp lý cần giúp người dùng hiểu điều gì?

Localized legal notices là các thông báo có nội dung pháp lý được trình bày bằng ngôn ngữ và cách diễn đạt phù hợp với người nhận, đồng thời giữ đúng phạm vi áp dụng, quyền, nghĩa vụ và thông tin thực tế của dịch vụ.

Trong khôi phục tài khoản, người dùng có thể đang mất mật khẩu, điện thoại, MFA hoặc passkey. Họ phải quyết định có gửi giấy tờ xác minh, cung cấp thông tin liên hệ khác hoặc tiếp tục một quy trình hỗ trợ hay không. Một thông báo khó hiểu có thể khiến họ cung cấp dữ liệu không cần thiết, hiểu sai thời hạn hoặc tưởng rằng phải từ bỏ quyền riêng tư để lấy lại tài khoản.

Bản địa hóa tốt cần giải quyết đồng thời ba việc:

1. **Đúng nội dung:** mô tả đúng hoạt động xử lý dữ liệu và điều kiện của quy trình.
2. **Đúng người nhận:** chọn ngôn ngữ có thể hiểu được và hồ sơ pháp lý phù hợp.
3. **Đúng thời điểm:** cho người dùng xem trước khi thực hiện hành động mà thông báo liên quan.

Việc dịch đủ từng câu chưa chứng minh rằng cả ba việc đã được đáp ứng. Một bản dịch trôi chảy vẫn có thể sai nếu nó nói về pháp nhân khác, dùng điều khoản hết hiệu lực hoặc biến việc cung cấp thông tin thành sự đồng ý.

**Ví dụ:** Màn hình xác minh danh tính ghi bằng tiếng Việt nhưng liên kết tới chính sách của một pháp nhân không cung cấp dịch vụ cho tài khoản đó. Đây là lỗi chọn nội dung pháp lý, dù bản dịch tiếng Việt không sai ngữ pháp.

## 2. Phân biệt các loại nội dung trong recovery

Không nên gom mọi đoạn chữ dưới tên “điều khoản”. Mỗi loại thông báo có mục đích và cách xử lý khác nhau.

| Loại nội dung | Ví dụ trong khôi phục tài khoản | Điều không được suy diễn |
| --- | --- | --- |
| Hướng dẫn thao tác | “Nhập mã đã được gửi tới kênh đã đăng ký.” | Đây không phải thông báo đầy đủ về xử lý dữ liệu |
| Cảnh báo bảo mật | “Một phương thức xác thực đã được thay đổi.” | Không mặc nhiên là thông báo vi phạm dữ liệu theo luật |
| Thông báo quyền riêng tư | Mục đích xử lý tài liệu xác minh, bên xử lý, thời hạn lưu, cách liên hệ | Việc hiển thị không tự tạo căn cứ pháp lý cho mọi hoạt động |
| Điều kiện của quy trình | Điều kiện dùng hỗ trợ thủ công, giới hạn phương thức được chấp nhận | Không được dịch thành việc người dùng từ bỏ quyền |
| Yêu cầu đồng ý, nếu có áp dụng | Một hoạt động cần sự đồng ý riêng theo hồ sơ pháp lý đã xác định | Không được gộp thành một nút chung với mọi bước recovery |
| Thông báo pháp lý về sự cố | Nội dung được lựa chọn sau khi xác định nghĩa vụ thông báo | Không thay bằng email bảo mật thông thường một cách tự động |

Tên gọi “thông báo” không quyết định hiệu lực pháp lý. Nội dung, hoàn cảnh cung cấp, loại dữ liệu và quy định áp dụng mới là những yếu tố cần được xác định.

Ví dụ về một khung pháp luật cụ thể: Điều 12 GDPR yêu cầu một số thông tin và trao đổi thuộc phạm vi điều này được cung cấp ngắn gọn, minh bạch, dễ hiểu, dễ tiếp cận, bằng ngôn ngữ rõ ràng. Điều 34 quy định việc thông báo cho cá nhân trong những trường hợp vi phạm dữ liệu có khả năng dẫn tới rủi ro cao, cùng các điều kiện và ngoại lệ. Không thể suy từ một yêu cầu recovery thành nghĩa vụ thông báo theo Điều 34. Xem [GDPR, Điều 12 và Điều 34 trên EUR-Lex](https://eur-lex.europa.eu/eli/reg/2016/679/).

Các cấu trúc và ví dụ tiếp theo là phương án thiết kế hệ thống. Chúng không phải bộ điều khoản dùng chung cho mọi quốc gia hoặc mọi loại tài khoản.

## 3. Ngôn ngữ giao diện không phải phạm vi pháp luật áp dụng

Một hệ thống cần tách ít nhất bốn khái niệm:

| Khái niệm | Câu hỏi được giải quyết | Ví dụ |
| --- | --- | --- |
| Ngôn ngữ người dùng lựa chọn | Người dùng muốn đọc bằng ngôn ngữ nào? | Tiếng Việt |
| Locale hiển thị | Cách trình bày ngày, giờ, số và nội dung theo vùng nào? | vi-VN |
| Múi giờ hiển thị | Thời điểm được biểu diễn theo múi giờ nào? | Asia/Ho_Chi_Minh |
| Hồ sơ pháp lý | Bộ nội dung nào phù hợp với dịch vụ và trường hợp này? | Một hồ sơ đã được xác định từ dữ liệu phía máy chủ |

Một người đọc tiếng Việt có thể sử dụng dịch vụ do một pháp nhân ở khu vực khác cung cấp. Ngược lại, dùng trình duyệt tiếng Anh không làm tài khoản tự chuyển sang một bộ điều khoản khác.

Địa chỉ IP hiện tại, quốc gia của SIM hoặc ngôn ngữ trình duyệt có thể thiếu chính xác hoặc thay đổi khi đi du lịch. Không dùng riêng một tín hiệu đó để quyết định bộ quyền, nghĩa vụ hay điều khoản.

W3C lưu ý rằng Accept-Language biểu thị sở thích ngôn ngữ và không đủ để xác định mọi thuộc tính locale; người dùng cũng cần có cách thay đổi lựa chọn. Trong thiết kế recovery, header này chỉ nên là một gợi ý hiển thị, không phải chứng cứ về nơi cư trú hoặc phạm vi luật áp dụng. Xem [Accept-Language used for locale setting](https://www.w3.org/International/questions/qa-accept-lang-locales).

Một cách tổ chức phù hợp là:

- Bộ phận phụ trách chính sách xác định các hồ sơ pháp lý và điều kiện lựa chọn.
- Máy chủ chọn hồ sơ từ dữ liệu được phép sử dụng, có nguồn gốc và độ tin cậy phù hợp.
- Bộ bản địa hóa chọn bản dịch tương ứng với hồ sơ đó.
- Người dùng đổi ngôn ngữ mà không làm thay đổi quyền recovery hoặc chính sách xác minh.

Tham số ngôn ngữ trên URL không được phép chọn một hồ sơ pháp lý dễ dãi hơn hoặc bỏ qua thông báo bắt buộc.

## 4. Xác định nội dung gốc theo hành động thực tế

Thông báo phải được viết từ hoạt động xử lý dữ liệu thật, không từ một mẫu chung được gắn vào cuối trang.

Trước bước tải tài liệu xác minh, nội dung cần làm rõ các thông tin có liên quan theo hồ sơ pháp lý, chẳng hạn:

- Đơn vị chịu trách nhiệm và cách liên hệ.
- Mục đích sử dụng thông tin được yêu cầu.
- Loại thông tin cần cung cấp và phần nào thực sự bắt buộc.
- Hệ quả thực tế nếu người dùng không cung cấp thông tin bắt buộc.
- Những bên tham gia xử lý hoặc tiếp nhận dữ liệu, nếu cần nêu.
- Thời hạn lưu hoặc cách xác định thời hạn theo chính sách áp dụng.
- Cách tìm hiểu và thực hiện các quyền liên quan.
- Liên kết tới nội dung đầy đủ có đúng phạm vi áp dụng.

Danh sách này là khung soạn nội dung, không phải danh sách nghĩa vụ pháp lý đầy đủ cho mọi trường hợp. Những nội dung như dữ liệu sinh trắc học, trẻ em hoặc chuyển dữ liệu qua biên giới cần được xác định riêng khi có liên quan.

Nếu dịch vụ không sử dụng nhận diện khuôn mặt, bản dịch không được tự thêm “chúng tôi phân tích sinh trắc học”. Nếu một nhà cung cấp thực tế có tham gia xác minh, cũng không được xóa thông tin cần thiết về bên đó chỉ để đoạn thông báo ngắn hơn.

Không công bố một thời hạn lưu cố định chỉ vì nó thường xuất hiện trong mẫu. Ví dụ, “xóa ngay sau xác minh” là lời khẳng định sai nếu tài liệu còn được giữ trong thời gian xử lý khiếu nại theo chính sách thực tế.

Nên tách nội dung thành lớp ngắn tại điểm cần đọc và lớp đầy đủ có thể mở ngay. Lớp ngắn giúp hiểu hành động sắp làm; nó không được dùng để giấu thông tin quan trọng phía sau một liên kết khó thấy.

## 5. Giữ nguyên ý nghĩa pháp lý khi chuyển ngữ

Bản dịch cần bảo toàn chủ thể, phạm vi, điều kiện, quyền lựa chọn, thời hạn và mức độ cam kết. Không chỉ bảo toàn từ vựng.

| Ý nghĩa cần bảo toàn | Sai lệch có thể xảy ra | Hệ quả |
| --- | --- | --- |
| Có thể yêu cầu thêm thông tin trong trường hợp cụ thể | Dịch thành luôn phải gửi giấy tờ | Thu thập quá mức hoặc cản trở người dùng |
| Dữ liệu dùng cho xác minh recovery | Dịch thành có thể dùng cho mọi mục đích | Mở rộng sai phạm vi xử lý |
| Có những phương thức thay thế nếu đủ điều kiện | Dịch thành luôn có phương thức thay thế | Hứa một lựa chọn hệ thống không cung cấp |
| Thời hạn tính từ khi đóng hồ sơ | Dịch thành tính từ lúc tải tài liệu | Hiểu sai thời gian lưu |
| Thông tin chỉ được chia sẻ với bên được nêu theo phạm vi xác định | Dịch thành không bao giờ chia sẻ | Mâu thuẫn với hoạt động thực tế |
| Người dùng được hướng dẫn cách gửi yêu cầu về dữ liệu | Dịch thành mọi yêu cầu đều được chấp thuận ngay | Biến quyền yêu cầu thành một kết quả được bảo đảm |

Cần thống nhất thuật ngữ trong cả hành trình. Ví dụ, “mã khôi phục” không nên ở trang sau trở thành “mã hỗ trợ” nếu hai thuật ngữ đang chỉ cùng một bí mật dùng để xác minh.

Tên pháp nhân, địa chỉ liên hệ và tên tài liệu nên có quy tắc riêng: phần nào giữ nguyên tên đăng ký, phần nào có bản dịch chính thức, phần nào chỉ là nhãn giao diện. Người dịch không tự đổi tên đơn vị chịu trách nhiệm.

Tránh ghép một câu pháp lý từ nhiều mảnh chuỗi. Trật tự từ, cách phủ định và số nhiều có thể khác giữa các ngôn ngữ. Nên dịch cả đơn vị ý nghĩa với các tham số có kiểu rõ ràng.

Đối với tên người hoặc dữ liệu do người dùng cung cấp, hãy xử lý như dữ liệu không đáng tin. Việc chèn tên vào thông báo không được tạo thêm HTML, liên kết hoặc câu có vẻ là một điều khoản mới.

## 6. Chọn ngôn ngữ khi người dùng đã mất quyền đăng nhập

Recovery thường diễn ra trước khi có session đầy đủ. Người dùng vẫn cần chọn được ngôn ngữ của thông báo ngay tại màn hình khôi phục.

Một thứ tự lựa chọn minh họa:

1. Lựa chọn trực tiếp của người dùng trong phiên recovery hiện tại.
2. Sở thích thông báo đã được lưu, nếu hệ thống đã xác định tài khoản và được phép dùng dữ liệu đó.
3. Ngôn ngữ trình duyệt làm gợi ý khi chưa có lựa chọn rõ ràng.
4. Một phương án thay thế đã được quy định cho loại thông báo và hồ sơ tương ứng.

Không dùng việc chọn ngôn ngữ để trả thêm dữ liệu về tài khoản trên màn hình chưa xác thực. Ví dụ, thay email nhập vào rồi thấy giao diện đổi sang “ngôn ngữ ưu tiên của tài khoản” có thể làm lộ rằng tài khoản đó tồn tại. Lựa chọn của chủ tài khoản cho thư gửi ra và lựa chọn trên trang công khai có thể cần được xử lý riêng.

Đổi ngôn ngữ là thay đổi cách hiển thị. Thao tác đó không được tiêu thụ mã dùng một lần, gia hạn token, thay đổi phương thức xác minh hoặc đánh dấu người dùng đã chấp thuận điều khoản.

Với email và SMS, cần có quy tắc rõ về ngôn ngữ tại lúc tạo thông báo và lúc gửi lại. Không tự đổi ngôn ngữ của thư gửi tới chủ tài khoản chỉ vì người yêu cầu recovery đặt một header khác.

## 7. Fallback cho thông báo pháp lý phải có chính sách riêng

Fallback là chọn nội dung thay thế khi không có đúng bản dịch được yêu cầu. Với thông báo pháp lý, không nên áp dụng máy móc cùng chuỗi fallback của mọi nhãn giao diện.

Ví dụ, việc không có vi-VN có thể dẫn tới bản vi nếu bản đó đã được xác định phù hợp. Nhưng việc không có bản tiếng Việt của hồ sơ A không cho phép dùng bản tiếng Việt thuộc hồ sơ B chỉ vì chúng cùng ngôn ngữ.

| Tình huống | Hướng xử lý minh họa |
| --- | --- |
| Có đúng bản dịch, đúng hồ sơ và đúng phiên bản áp dụng | Hiển thị bản đó |
| Thiếu biến thể vùng nhưng có bản ngôn ngữ chung tương thích | Chỉ chọn nếu chính sách của thông báo cho phép |
| Chỉ có bản dịch cho hồ sơ pháp lý khác | Không dùng thay |
| Bản dịch còn tham chiếu tới nội dung gốc đã hết hiệu lực | Xử lý như thiếu bản phù hợp |
| Có bản thay thế đã được quy định | Nêu rõ ngôn ngữ và cung cấp lựa chọn phù hợp |
| Không có phương án thay thế được phép | Đi theo nhánh xử lý đã định nghĩa cho hành động đó |

Nhánh xử lý cuối cùng có thể là tạm dừng việc thu thập thêm tài liệu và cung cấp kênh hỗ trợ. Không được tự động bỏ bước cung cấp thông tin rồi vẫn tiếp tục thu thập như bình thường.

Cũng không nên khóa toàn bộ khả năng báo mất tài khoản chỉ vì một bản dịch của thông báo tải tài liệu đang thiếu. Cần phân biệt bước tiếp nhận báo cáo tối thiểu, hành động bảo vệ khẩn cấp và bước xử lý dữ liệu cần thông báo cụ thể. Quyết định cho phép từng bước phải đến từ chính sách đã xác định, không từ một giá trị mặc định “cho qua” hoặc “chặn hết”.

Đối với sự cố có nghĩa vụ thông báo theo thời hạn áp dụng, thiếu bản dịch cần được xử lý bằng phương án dự phòng được quy định trước. Hàng đợi dịch không được trở thành lý do để hệ thống tự trì hoãn vô hạn. Cách dùng ngôn ngữ thay thế, hỗ trợ bổ sung hay gửi cập nhật phải được quyết định cho trường hợp đó.

Không dùng dịch máy trực tiếp tại thời điểm hiển thị làm phương án mặc định cho nội dung có hiệu lực pháp lý. Nếu dịch máy tham gia quy trình tạo bản dịch, kết quả vẫn cần đi qua cơ chế quản lý nội dung tương ứng trước khi trở thành một bản được phép sử dụng.

## 8. Hiển thị, ghi nhận đã đọc và đồng ý là ba việc khác nhau

Một thông báo quyền riêng tư có thể cần được cung cấp mà không phải là một yêu cầu đồng ý. Một nút “Tiếp tục” cũng không tự chứng minh người dùng đã đồng ý với mọi hoạt động xử lý.

Cần phân biệt:

- **Đã cung cấp:** hệ thống đã hiển thị hoặc gửi một phiên bản thông báo qua kênh cụ thể.
- **Đã xác nhận:** người dùng thực hiện hành động xác nhận được thiết kế cho mục đích đã nêu.
- **Đã đồng ý:** có một hành động và ngữ cảnh đáp ứng yêu cầu của cơ chế đồng ý đang áp dụng.

Không tạo checkbox chung kiểu “Tôi đồng ý với mọi việc xử lý dữ liệu và nhận quảng cáo để lấy lại tài khoản”. Mục đích khôi phục và mục đích tiếp thị cần được xử lý riêng; nội dung hiển thị không có quyền mở rộng phạm vi xử lý.

Nếu có bước yêu cầu đồng ý, cấu trúc phải gắn với hoạt động cụ thể, phiên bản nội dung và lựa chọn thật của người dùng. Việc người dùng từ chối cần dẫn tới hành vi đã được xác định cho hoạt động đó, thay vì một thông báo lỗi kỹ thuật không giải thích được.

Những câu như “bản tiếng Anh luôn có giá trị ưu tiên” không phải một thuộc tính kỹ thuật của hệ thống dịch. Không tự thêm chúng vào mọi bản dịch; nếu có quy tắc ưu tiên ngôn ngữ trong một tài liệu, quy tắc đó phải được xác định cho chính tài liệu và trường hợp áp dụng.

## 9. Trình bày dễ đọc mà vẫn giữ nguyên định danh

Đọc được ngôn ngữ chưa đủ nếu nội dung bị cắt, đường liên kết không sử dụng được hoặc thời gian bị hiểu sai.

Các lựa chọn trình bày hữu ích gồm:

- Có tên ngôn ngữ dễ nhận biết trong bộ chọn, không chỉ dùng cờ quốc gia.
- Cho phép mở toàn bộ nội dung bằng bàn phím và công nghệ hỗ trợ.
- Dùng nhãn liên kết có nghĩa, chẳng hạn “Thông báo quyền riêng tư về khôi phục tài khoản”.
- Hiển thị ngày và thời điểm hết hạn không mơ hồ, với múi giờ khi cần.
- Đảm bảo nội dung dài không bị che bởi nút cố định hoặc bị cắt trên màn hình nhỏ.
- Giữ đường báo sự cố và cách liên hệ truy cập được khi chưa đăng nhập.

W3C phân biệt thuộc tính lang dùng khai báo ngôn ngữ với dir dùng khai báo hướng văn bản. Với ngôn ngữ viết từ phải sang trái, cần xử lý cả hướng trang và các đoạn dữ liệu chèn vào. Xem [Structural markup and right-to-left text in HTML](https://www.w3.org/International/questions/qa-html-dir).

Tên miền, địa chỉ email và mã hồ sơ cần hiển thị rõ trong văn bản có nhiều hệ chữ. Không dịch hoặc thay ký tự trong token, địa chỉ liên hệ, hostname hay định danh được dùng để tra cứu. Ngày giờ có thể được bản địa hóa về cách trình bày nhưng không được thay đổi thời điểm thực tế.

Nội dung đầy đủ phải tồn tại tại URL do hệ thống kiểm soát, với liên kết được chọn từ cấu hình tin cậy. Tham số locale không được trở thành một URL tùy ý, đường dẫn tệp hoặc open redirect. Nếu liên kết tới một trang bên ngoài, cần xác định rõ đó có phải nơi người dùng sẽ được yêu cầu nhập dữ liệu hay không.

Không đưa email người dùng, token recovery hoặc chi tiết tài liệu xác minh vào query string của liên kết chính sách hay hệ thống phân tích lượt xem. Người dùng cần đọc thông báo mà không làm lộ thêm dữ liệu recovery.

## 10. Ví dụ lớp thông báo ngắn bằng hai ngôn ngữ

Giả sử dịch vụ có một bước hỗ trợ xác minh danh tính và đã có tài liệu đầy đủ phù hợp. Hai bản dưới đây chỉ minh họa lớp giải thích ngắn trước bước gửi thông tin; chúng không thay cho toàn bộ thông báo bắt buộc của dịch vụ.

### Bản tiếng Việt

~~~text
Xác minh danh tính để khôi phục tài khoản

Chúng tôi sử dụng thông tin bạn gửi ở bước này để xác minh yêu cầu
khôi phục tài khoản. Chỉ cung cấp những thông tin được yêu cầu.

Trước khi gửi, hãy đọc Thông báo quyền riêng tư về khôi phục tài khoản
để biết đơn vị chịu trách nhiệm, cách thông tin được sử dụng và lưu giữ,
cùng cách liên hệ về quyền đối với dữ liệu.

Nếu không thể sử dụng phương thức này, hãy chọn Trợ giúp khôi phục
để xem các lựa chọn phù hợp với tài khoản.

[Nhãn liên kết] Thông báo quyền riêng tư về khôi phục tài khoản
[Nút] Tiếp tục xác minh
~~~

### Bản tiếng Anh

~~~text
Verify your identity to recover your account

We use the information you submit at this step to verify your account
recovery request. Provide only the information requested.

Before submitting, read the Account Recovery Privacy Notice to learn
who is responsible, how your information is used and retained, and
how to contact us about your data rights.

If you cannot use this method, choose Recovery Help to see the options
available for your account.

[Link label] Account Recovery Privacy Notice
[Button] Continue verification
~~~

Hai bản giữ cùng mục đích, không biến nút tiếp tục thành một lời đồng ý bao quát và không hứa luôn có phương thức thay thế. Đường Trợ giúp cũng cần phản ánh các lựa chọn thật, không dẫn vòng về chính bước mà người dùng không thể hoàn thành.

Nếu lớp thông báo đầy đủ đang nói tới một bên xác minh cụ thể, dữ liệu được thu thập và thời hạn lưu cụ thể, các bản dịch của lớp đầy đủ cần giữ những thông tin đó. Một đoạn ngắn như ví dụ không được dùng để thay thế chúng.

## 11. Quản lý phiên bản và bản ghi cung cấp thông báo

Cần biết người dùng đã được cung cấp **nội dung nào**, không chỉ **ngôn ngữ nào**. Một khóa “privacy.vi” có thể trỏ tới nội dung khác nhau ở hai thời điểm.

Một mô hình metadata minh họa cho kho nội dung:

~~~yaml
noticeKey: RECOVERY_IDENTITY_NOTICE
legalProfileId: PROFILE_A
sourceVersion: "3"
locale: vi-VN
translationRevision: "2"
effectiveFrom: "2026-11-23T00:00:00Z"
status: APPROVED
contentDigest: "<digest-of-immutable-content>"
fallbackPolicyId: PROFILE_A_IDENTITY_NOTICE
~~~

Các tên trường và giá trị trên chỉ để minh họa. Chúng không phải YAML bài học hay cấu hình đang được ghi vào module.

Những thuộc tính có vai trò khác nhau:

| Thuộc tính | Vai trò |
| --- | --- |
| noticeKey | Xác định loại thông báo |
| legalProfileId | Xác định phạm vi nội dung áp dụng |
| sourceVersion | Xác định phiên bản ý nghĩa của nội dung gốc |
| translationRevision | Xác định lần sửa bản dịch của cùng phiên bản gốc |
| effectiveFrom | Thời điểm được phép áp dụng theo chính sách |
| contentDigest | Hỗ trợ đối chiếu nội dung bất biến |
| fallbackPolicyId | Xác định cách xử lý khi thiếu ngôn ngữ phù hợp |

Sửa lỗi dấu câu có thể chỉ tạo revision bản dịch mới. Thay mục đích xử lý dữ liệu hoặc thời hạn lưu là thay đổi nội dung có ý nghĩa, không được che dưới nhãn “chỉ cập nhật ngôn ngữ”.

Bản ghi cung cấp thông báo có thể liên kết mã giao dịch recovery nội bộ, mã thông báo, hồ sơ pháp lý, phiên bản nội dung, ngôn ngữ thực tế, kênh và thời điểm. Nếu đã dùng fallback, ghi cả ngôn ngữ được yêu cầu và ngôn ngữ đã cung cấp.

Cần phân biệt các mức bằng chứng. Render thành công chứng minh hệ thống tạo được nội dung; nhà cung cấp thư chấp nhận không chứng minh chủ tài khoản đã đọc; một mã băm không tự chứng minh người dùng đã đồng ý.

Nội dung gốc, bản dịch và các giá trị tham số có ý nghĩa cần có cách đối chiếu theo chính sách lưu bằng chứng. Chỉ lưu mã băm mà mất toàn bộ bản nội dung liên quan có thể không đủ để tái dựng điều đã cung cấp.

Bản ghi này cũng là dữ liệu cần bảo vệ. Không nhân bản tài liệu định danh, OTP hoặc token vào log chỉ để làm bằng chứng về thông báo. Giới hạn quyền truy cập và thời hạn lưu theo mục đích thực tế; không mặc định giữ mãi mọi chi tiết.

## 12. Luồng lựa chọn và render minh họa

~~~text
handleRecoveryNotice(context):
    action = resolveRecoveryActionOnServer(context)
    profile = resolveApplicableLegalProfile(context, action)
    requestedLanguage = resolveDisplayLanguage(context)

    notice = selectApprovedNotice(
        action,
        profile,
        requestedLanguage,
        currentTime
    )

    if notice is unavailable:
        return handleMissingNoticeUsingPolicy(action, profile)

    parameters = buildAllowedNoticeParameters(action, context)
    rendered = renderWithEscaping(notice, parameters)

    recordNoticeProvision(
        context.recoveryTransactionId,
        notice.identity,
        requestedLanguage,
        notice.actualLanguage,
        currentTime
    )

    return rendered
~~~

Giả mã này không cấp quyền khôi phục. Máy chủ vẫn phải xác minh token, kiểm tra giới hạn sử dụng và quyết định quyền thực hiện hành động bằng cơ chế riêng. Việc render một thông báo thành công không làm yêu cầu recovery trở nên hợp lệ.

Nếu ứng dụng có cache, khóa cache phải phân biệt đủ hồ sơ pháp lý, ngôn ngữ, phiên bản và thời điểm hiệu lực liên quan. Tránh để tài khoản thuộc hồ sơ A nhận nội dung của hồ sơ B chỉ vì dùng chung đường dẫn trang.

Thông báo có dữ liệu cá nhân chèn vào cũng không được đưa vào cache dùng chung cho người khác. Trong nhiều trường hợp, có thể cache phần nội dung bất biến và render các dữ liệu được phép dùng riêng cho từng giao dịch.

## 13. Ví dụ xuyên suốt và các lỗi cần tránh

Lan dùng giao diện tiếng Việt nhưng đang mượn một máy tính có trình duyệt đặt tiếng Anh. Cô mất thiết bị MFA và mở quy trình hỗ trợ recovery.

**Đầu hành trình:** Trang công khai cho Lan chọn tiếng Việt mà không tiết lộ tài khoản đã được tìm thấy hay chưa. Header của máy tính không ghi đè lựa chọn trực tiếp đó.

**Trước bước gửi tài liệu:** Máy chủ đã xác định hồ sơ pháp lý của giao dịch từ nguồn phù hợp. Nó chọn bản tiếng Việt thuộc đúng hồ sơ và phiên bản đang áp dụng. Nếu thiếu biến thể vi-VN, nó chỉ chọn bản vi khi chính sách cho phép.

**Khi chuyển ngôn ngữ:** Lan có thể xem bản tiếng Anh tương ứng. Việc này không thay hồ sơ pháp lý, không làm token hết hạn muộn hơn và không bỏ qua bước xác minh.

**Khi bản dịch chưa sẵn sàng:** Nếu không có phương án thay thế phù hợp, hệ thống xử lý theo nhánh đã quy định, chẳng hạn dừng việc tải thêm tài liệu và cung cấp trợ giúp. Nó vẫn xử lý các bước bảo vệ hoặc tiếp nhận tối thiểu theo chính sách riêng.

**Sau khi cung cấp thông báo:** Hệ thống ghi nhận đúng bản đã hiển thị. Nó không ghi “Lan đã đồng ý” chỉ vì trang được mở hoặc nút tiếp tục được dùng.

| Lỗi thiết kế | Điều nên thực hiện |
| --- | --- |
| Suy phạm vi pháp lý từ ngôn ngữ hoặc IP hiện tại | Tách lựa chọn hồ sơ pháp lý khỏi lựa chọn ngôn ngữ |
| Có bản dịch cùng ngôn ngữ thì dùng, bất kể hồ sơ | Chọn đúng loại thông báo, hồ sơ và phiên bản |
| Thiếu bản dịch thì âm thầm bỏ thông báo | Thực hiện chính sách fallback hoặc nhánh hỗ trợ cụ thể |
| Dịch “có thể” thành “bắt buộc” để câu ngắn | Giữ điều kiện và mức độ nghĩa vụ của nội dung gốc |
| Gộp quyền riêng tư, đồng ý và quảng cáo vào một nút | Xác định rõ mục đích và hành động của từng thành phần |
| Ghi mọi lần mở trang là bằng chứng đồng ý | Ghi đúng loại sự kiện và giới hạn của bằng chứng |
| Dùng đường dẫn chính sách nhận từ tham số tùy ý | Chọn tài nguyên từ danh mục do hệ thống kiểm soát |

Một thông báo được bản địa hóa đúng cần đi cùng đúng nội dung pháp lý, đúng hành động thực tế và một đường hỗ trợ sử dụng được. Người dùng phải hiểu thông tin trước khi quyết định, kể cả khi họ đang mất quyền truy cập tài khoản.
