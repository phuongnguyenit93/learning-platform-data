# Cân bằng thiết kế đủ dùng với rủi ro phải làm lại

Một Scrum Team phát triển nền tảng học trực tuyến được giao tính năng **lưu khóa học yêu thích**. Một Developer đề xuất xây ngay một hệ thống gợi ý cá nhân hóa có thể mở rộng tới hàng triệu người dùng, vì “sau này chắc chắn cần”. Người khác cho rằng chỉ cần thêm nút hình trái tim và lưu trạng thái trong trình duyệt vì “Agile không thiết kế trước”. Hai phương án đều nghe có lý nếu chỉ nhìn vào một nửa vấn đề: phương án thứ nhất muốn tránh làm lại về sau, phương án thứ hai muốn giao nhanh và tránh đầu tư vô ích.

Nhưng giả sử người dùng cần xem lại danh sách sau khi đổi thiết bị, dữ liệu phải tách đúng giữa các tài khoản và hệ thống cần xử lý thao tác lưu lặp. Nếu chỉ đổi màu nút, tính năng chưa hoàn tất. Ngược lại, nếu dành ba Sprint xây cơ sở hạ tầng gợi ý quy mô lớn khi chưa có bằng chứng về nhu cầu, đội đã trì hoãn phản hồi người dùng để bảo vệ một tương lai tưởng tượng.

**Thiết kế tiến hóa (evolutionary design)** tìm cách giải quyết sự căng thẳng này: xây **thiết kế đơn giản nhất có thể đáp ứng các yêu cầu đã hiểu và rủi ro cần kiểm soát**, đồng thời duy trì khả năng thay đổi an toàn khi học thêm. “Đủ dùng” không phải “cứ viết tạm rồi sửa”; “tránh làm lại” không phải “thiết kế toàn bộ tương lai ngay từ đầu”.

Bài thuộc chương **Thiết kế tiến hóa** của module **AGILE_DEVELOPMENT**, gắn với mục tiêu hiểu nguyên tắc Agile, nhận phản hồi sớm, giao phần mềm tăng dần và cải tiến liên tục. Các ví dụ kết nối user story, Product Backlog, Scrum, Kanban, XP, kiểm thử, refactoring và đo lường dòng công việc để chọn mức đầu tư thiết kế phù hợp.

> **Câu hỏi trung tâm:** Với thông tin có hôm nay, điều gì phải thiết kế chắc ngay để bảo vệ tính đúng đắn và khả năng thay đổi, còn điều gì có thể hoãn đến khi có bằng chứng mà không tạo rủi ro làm lại quá lớn?

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích thiết kế tiến hóa, thiết kế vừa đủ, **YAGNI** (*You Aren't Gonna Need It*) và **refactoring**, đồng thời phân biệt chúng với lập trình thiếu kế hoạch hoặc hạ chất lượng.
2. Nhận diện hai loại chi phí đối nghịch: **xây quá sớm một khả năng không cần** và **làm lại quá đắt vì không chuẩn bị những quyết định khó đảo ngược**.
3. Đánh giá quyết định thiết kế theo **mức bất định, khả năng đảo ngược, mức độ ảnh hưởng, chi phí chuyển đổi và thời điểm có thông tin mới**.
4. Chọn những ràng buộc cần làm rõ sớm: quyền truy cập, dữ liệu, tính đúng đắn giao dịch, tính tương thích, hiệu năng, vận hành và nghĩa vụ tuân thủ.
5. Dùng các kỹ thuật như lát cắt dọc, thiết kế mô-đun, refactoring, automated tests, CI, thử nghiệm có thời hạn và migration kiểu **expand–migrate–contract** để hỗ trợ thay đổi.
6. Giải thích cách Scrum, Kanban và XP có thể hỗ trợ các quyết định thiết kế mà không biến story point, số ticket hoặc bộ kiểm thử thành mục tiêu tự thân.
7. Áp dụng mô hình quyết định có giả định, bằng chứng, guardrails và mốc xem lại trong tình huống phát triển nền tảng học trực tuyến.

## 1. Thiết kế tiến hóa là gì — và không phải gì?

**Thiết kế tiến hóa** là cách phát triển cấu trúc phần mềm qua những bước nhỏ, liên tục điều chỉnh dựa trên yêu cầu hiện tại và điều học được từ kiểm thử, vận hành, người dùng và bối cảnh kỹ thuật. Thiết kế không chỉ diễn ra trong một giai đoạn trước khi lập trình; nó được rà soát khi hiểu biết thay đổi.

Theo nguyên tắc Agile, việc chú trọng **technical excellence** và **good design** có thể nâng cao sự linh hoạt. Vì vậy thiết kế tiến hóa không chống lại thiết kế; nó chống lại sự giả định rằng có thể biết đủ mọi yêu cầu tương lai để khóa toàn bộ cấu trúc từ đầu.

### 1.1. Ba lập trường dễ nhầm

| Lập trường | Điều được ưu tiên | Rủi ro nếu áp dụng cực đoan |
|---|---|---|
| **Big Design Up Front** cho mọi chi tiết | Cố dự đoán toàn bộ tương lai trước khi giao chức năng | Chi phí thiết kế/speculative infrastructure cao, phản hồi người dùng muộn, nhiều giả định lỗi thời |
| **Không thiết kế, chỉ code** | Hoàn tất một phần trước mắt với ít suy nghĩ về cấu trúc | Dữ liệu sai, phụ thuộc chặt, hồi quy, khó tích hợp, chi phí thay đổi tăng |
| **Thiết kế tiến hóa có kỷ luật** | Thiết kế đủ cho giá trị gần và rủi ro có thật, giữ khả năng đổi | Cần đầu tư kiểm thử, tích hợp, hiểu biết hệ thống và ra quyết định thường xuyên |

Không nên biến bảng thành tuyên bố rằng **mọi thiết kế ban đầu đều xấu**. Một quyết định về ranh giới dữ liệu nhạy cảm hoặc định dạng tích hợp với đối tác có thể cần phân tích sớm vì thay đổi sau này rất đắt. Ngược lại, chọn trước ba mươi biến thể giao diện chưa có người dùng thường ít căn cứ.

### 1.2. “Đủ dùng” phải đủ theo **toàn bộ chất lượng cần thiết**

Một thiết kế chỉ đủ dùng khi đáp ứng đồng thời:

- **Hành vi cần thiết:** người dùng thực hiện được tác vụ trong phạm vi đã công bố.
- **Tính đúng đắn và an toàn:** dữ liệu, quyền truy cập, giao dịch và trạng thái tuân theo ràng buộc áp dụng.
- **Mức chất lượng thích hợp:** kiểm thử, độ tin cậy, khả năng truy cập, vận hành và hiệu năng liên quan đủ cho bối cảnh sử dụng.
- **Khả năng sửa đổi hợp lý:** cấu trúc hiện tại không buộc mọi thay đổi nhỏ đều trở thành sửa chữa lớn không cần thiết.
- **Bằng chứng kiểm chứng:** có cách xác minh những khẳng định quan trọng, không chỉ dựa vào cảm giác “chạy được trên máy tôi”.

Ví dụ, với yêu thích khóa học, lưu một bản ghi liên kết **user_id–course_id** và kiểm soát quyền truy cập có thể đủ cho phiên bản đầu. Việc xây ngay bộ máy gợi ý AI có thể chưa cần. Nhưng lưu mọi yêu thích trong bộ nhớ tạm, mất hết sau khi đăng xuất, **không đủ** nếu mục tiêu người dùng là lưu để xem sau.

### 1.3. Thiết kế tiến hóa không bảo đảm chi phí thay đổi luôn thấp

Một số thay đổi rẻ: đổi nhãn nút, thêm loại hiển thị khi dữ liệu đã tách lớp rõ. Một số thay đổi có thể rất đắt: đổi khóa định danh đã phát tán sang hệ thống đối tác, tách cơ sở dữ liệu có hàng triệu bản ghi, thay cơ chế phân quyền hoặc sửa mô hình nhất quán của giao dịch tiền.

Chi phí thay đổi phụ thuộc **kiến trúc, dữ liệu, kiểm thử, phụ thuộc, tải thực, nghĩa vụ hợp đồng và kỹ năng đội**. Thiết kế tiến hóa giảm rủi ro bằng cách nhận diện khác biệt đó sớm; nó không biến mọi lựa chọn thành đảo ngược dễ dàng.

## 2. Hai thái cực gây lãng phí: xây quá mức và làm lại quá lớn

Một thiết kế có thể thất bại theo hai hướng:

1. **Overengineering:** đầu tư vào cấu trúc, tính tổng quát hoặc hạ tầng cho một khả năng chưa đủ xác suất xuất hiện hay chưa đáng ưu tiên.
2. **Underdesign:** bỏ qua những đặc tính kỹ thuật đã có bằng chứng cần thiết, khiến việc hoàn tất hiện tại hoặc thay đổi gần phải trả giá lớn.

### 2.1. Bảng so sánh bằng ví dụ

| Quyết định | Overengineering | Underdesign | Thiết kế đủ dùng |
|---|---|---|---|
| **Lưu khóa yêu thích** | Xây recommendation engine, event bus và phân cụm cho nhu cầu chưa xác nhận | Chỉ đổi biểu tượng UI, mất dữ liệu sau đăng nhập lại | Lưu bền vững theo tài khoản, xử lý lưu lặp, phân quyền đúng |
| **Thanh toán một phương thức** | Xây bộ điều phối cho mọi nhà cung cấp chưa được chọn | Cấp quyền học ngay khi bấm Pay | Xác thực kết quả đáng tin, xử lý callback lặp và trạng thái lỗi; cô lập chỗ tích hợp khó đổi |
| **Tìm kiếm khóa học** | Triển khai search cluster phân tán trước khi có dữ liệu về truy vấn và tải | Tạo truy vấn thiếu chỉ mục dù tải thực đã khiến trang không dùng được | Truy vấn/chỉ mục phù hợp tải hiện tại, đo latency và xác định ngưỡng xem lại |
| **Thông báo email** | Tự xây nền tảng workflow và template động phức tạp cho một thông báo | Gửi đồng bộ trong request khiến API treo hoặc báo thành công giả | Tách xử lý theo nhu cầu đáng tin, ghi nhận trạng thái và retry phù hợp |
| **Báo cáo quản trị** | Xây data lake toàn tổ chức trước một báo cáo đơn giản | Cho truy vấn mọi dữ liệu không kiểm soát quyền | Tạo lát cắt báo cáo đúng đối tượng và chính sách dữ liệu, mở rộng theo nhu cầu |

Không có cột “thiết kế đủ dùng” áp dụng y nguyên cho mọi tổ chức. Nếu một hệ thống thanh toán phải tích hợp nhiều đối tác theo hợp đồng đã ký, thiết kế giao diện thay thế đối tác sớm có thể là cần thiết. Nếu sản phẩm chỉ phục vụ mười người dùng thử và không lưu dữ liệu nhạy cảm, một số lựa chọn có thể đơn giản hơn.

### 2.2. YAGNI đúng nghĩa

**YAGNI — You Aren't Gonna Need It** là một heuristic quen thuộc trong XP: **đừng xây chức năng hoặc độ tổng quát chỉ vì tưởng tượng có thể cần trong tương lai**. Nó giúp tránh:

- Thêm nhiều chế độ cấu hình chưa có trường hợp sử dụng.
- Thiết kế lớp kế thừa cho các loại đối tượng chưa xuất hiện.
- Tạo API công khai phức tạp trước khi biết nhu cầu tích hợp.
- Chuẩn bị một cụm hạ tầng lớn khi dữ liệu tải thực còn nhỏ.
- Viết trước tính năng dành cho “khách hàng tương lai” chưa có bằng chứng.

YAGNI **không phải** lời khuyên bỏ:

- Kiểm thử cần để bảo vệ tính đúng đắn.
- Phân quyền, bảo mật, tính toàn vẹn dữ liệu.
- Kết quả thiết kế cần để bảo đảm Increment hoạt động được.
- Migrations hoặc khả năng nâng cấp khi dữ liệu thật đã tồn tại.
- Những ràng buộc pháp lý, kỹ thuật hoặc hợp đồng đã được xác nhận.

Phân biệt **“chưa cần tính năng”** với **“cần năng lực để thay đổi an toàn”**. Một test và một ranh giới mô-đun đơn giản có thể chưa trực tiếp tạo nút mới, nhưng giúp đội đáp ứng nhu cầu đã biết và tránh làm lại ở những Sprint sau.

### 2.3. Chi phí không chỉ là số giờ viết mã ban đầu

Một thay đổi có thể tiêu tốn:

\[
C_{\text{toàn phần}} =
C_{\text{thiết kế/xây}}+
C_{\text{kiểm thử/tích hợp}}+
C_{\text{triển khai/di trú}}+
C_{\text{vận hành}}+
C_{\text{làm lại/rủi ro}}
\]

Đây là **mô hình tư duy**, không phải công thức định giá có thể tính chính xác bằng một vài giờ ước lượng. Những thành phần có thể trùng lặp hoặc phụ thuộc nhau; khi so sánh cần nhất quán cách tính và dùng khoảng ước lượng phù hợp.

Ví dụ một giải pháp tạm có chi phí code thấp nhưng đòi hỏi thao tác sửa dữ liệu bằng tay mỗi tuần; sau vài tháng, tổng chi phí có thể cao hơn giải pháp đơn giản nhưng có kiểm chứng và tự động hóa từ đầu.

## 3. Đánh giá mức độ cần thiết của thiết kế bằng rủi ro và khả năng đảo ngược

Không phải quyết định nào cũng xứng đáng có cùng mức phân tích. Một cách phân loại hữu ích là **mức bất định** và **chi phí đảo ngược**.

### 3.1. Ma trận bốn trường hợp

| | **Dễ đảo ngược / thay đổi rẻ** | **Khó đảo ngược / thay đổi đắt** |
|---|---|---|
| **Thông tin tương đối chắc** | Chọn phương án đơn giản, làm và kiểm tra nhanh | Thiết kế đủ sâu cho ràng buộc đã biết, ghi quyết định và phương án chuyển đổi |
| **Thông tin còn bất định** | Giữ lựa chọn mở, giao lát cắt nhỏ, học từ thực tế | Giảm bất định sớm bằng spike/prototype/đo; trì hoãn cam kết không cần thiết, thiết kế đường thoát hoặc phối hợp cấp có thẩm quyền |

**Ví dụ dễ đảo ngược, bất định cao:** vị trí nút “Lưu khóa” trên giao diện. Có thể thử phương án đơn giản và quan sát học viên.

**Ví dụ khó đảo ngược, tương đối chắc:** hệ thống có dữ liệu cá nhân và quyền truy cập theo tài khoản. Cần thiết kế phân quyền và cách lưu dữ liệu ngay từ lát cắt đầu.

**Ví dụ khó đảo ngược, bất định cao:** có nên đưa dữ liệu đăng ký sang một hệ thống đối tác chưa chốt hợp đồng, dùng khóa định danh của bên đó làm khóa chính mọi nơi? Nên xác minh ràng buộc, thử tích hợp nhỏ và tránh làm cấu trúc lõi phụ thuộc sâu khi chưa biết đối tác cuối.

### 3.2. Năm câu hỏi trước một quyết định kỹ thuật

1. **Điều gì đã có bằng chứng?** Yêu cầu hiện tại, dữ liệu tải, hành vi người dùng, nghĩa vụ và tình trạng hệ thống nào là thật?
2. **Điều gì mới chỉ là giả thuyết?** Có phải ta đang xây cho một tương lai “có lẽ sẽ xảy ra”?
3. **Nếu quyết định sai, đổi lại khó đến đâu?** Ảnh hưởng bao nhiêu module, dữ liệu, API công khai, hệ thống ngoài và người dùng?
4. **Khi nào chúng ta có thông tin tốt hơn?** Sau một thử nghiệm, vài bản phát hành, dữ liệu traffic hay quyết định hợp đồng?
5. **Có cách nào giữ đường thay đổi rẻ hơn?** Một ranh giới mô-đun, test, contract, migration theo bước hoặc option được ghi rõ?

Không cần lập bảng điểm cho mọi phương thức Java. Nhưng với quyết định cấu trúc dữ liệu, xác thực giao dịch hoặc tích hợp lâu dài, những câu hỏi này có thể tránh chi phí lớn.

### 3.3. Expected rework: một mô hình ra quyết định đơn giản

Giả sử có hai lựa chọn:

- **A:** thiết kế gọn cho một nhà cung cấp hiện tại; có thể cần làm lại nếu thêm nhà cung cấp B.
- **B:** đầu tư ngay lớp tích hợp linh hoạt để hỗ trợ nhiều nhà cung cấp.

Ước lượng giả định:

| Thành phần | A — Gọn | B — Tổng quát sớm |
|---|---:|---:|
| Chi phí xây hôm nay (đơn vị công sức minh họa) | 4 | 9 |
| Chi phí mở rộng nếu thật sự cần B | 8 | 2 |
| Xác suất cần B trong khoảng thời gian đang xét | 25% | 25% |

Nếu **chỉ** xét chi phí kỳ vọng đơn giản:

\[
E[C_A]=4 + 0{,}25\times 8=6
\]

\[
E[C_B]=9 + 0{,}25\times 2=9{,}5
\]

Với giả định này, **A có chi phí kỳ vọng thấp hơn**. Nhưng **không** nên kết luận A luôn tốt hơn: nếu việc thay sau này làm mất dữ liệu, ngừng hệ thống hai tháng hoặc vi phạm hợp đồng, tác động không thể chỉ phản ánh bằng “8 đơn vị công sức”; nếu nhu cầu thêm B đã được ký, xác suất không còn 25%.

Phép tính có ích để **bộc lộ các giả định** chứ không tự tạo độ chính xác. Hãy nhạy cảm với thay đổi xác suất và mức thiệt hại; với rủi ro an toàn hoặc không chấp nhận được, **guardrails** quan trọng hơn tối ưu kỳ vọng trung bình.

### 3.4. Giá trị của việc trì hoãn quyết định

Trong tư duy quản lý lựa chọn (*real options* như một phép ẩn dụ), khi quyết định **khó đảo ngược** và thông tin mới có khả năng xuất hiện sớm, có thể có giá trị khi **giữ nhiều phương án mở thêm một thời gian hợp lý**.

Ví dụ, thay vì mua hạ tầng xử lý video ở quy mô lớn ngay, nhóm thử một đường xử lý nhỏ và đo:

- Số lượng video tải lên, kích cỡ và yêu cầu mã hóa thực.
- Thời gian xử lý và mức chi phí tại lưu lượng hiện tại.
- Nghĩa vụ lưu trữ, riêng tư và quyền truy cập.
- Ranh giới tích hợp nếu phải đổi dịch vụ.

Trì hoãn quyết định **không đồng nghĩa trì hoãn mọi hành động**. Nhóm có thể xây lát cắt và thu dữ liệu để giảm bất định. Hoãn quá lâu một quyết định đã ảnh hưởng bản ghi dữ liệu hoặc API công khai lại có thể làm tăng chi phí thay đổi.

### 3.5. Tín hiệu cho biết cần quyết định sớm

Hãy tăng đầu tư thiết kế khi:

- Mô hình dữ liệu sẽ được nhiều bên ngoài phụ thuộc và rất khó di trú.
- Có ràng buộc bảo mật, pháp lý, an toàn hoặc tiền tệ.
- Lựa chọn không thể đảo ngược sau khi phát hành hoặc khi người dùng đã lưu dữ liệu.
- Một điểm nghẽn kiến trúc được quan sát lặp lại và ảnh hưởng nhiều tính năng.
- Kết quả spike cho thấy giả định thiết kế cũ không đáp ứng yêu cầu.
- Hợp đồng, tích hợp hoặc giới hạn tài nguyên đã đủ xác nhận để ảnh hưởng cách làm.

Hãy cân nhắc **chưa thiết kế tổng quát** khi:

- Chưa có người dùng hoặc cam kết cho biến thể tương lai.
- Chi phí đổi sau này nhỏ và đã có test bảo vệ.
- Chỉ cần chỉnh một vùng code rõ ràng, không lan sang nhiều module.
- Bằng chứng mới sẽ có sớm qua một lát cắt nhỏ.
- Cấu trúc tổng quát sẽ tạo nhiều lớp cấu hình, bảo trì và vận hành không cần thiết.

## 4. “Thiết kế đủ dùng” không phải “bỏ kiến trúc trước Sprint”

Thiết kế tiến hóa vẫn cần nhìn **kiến trúc**: những quyết định về ranh giới thành phần, mô hình dữ liệu, giao tiếp, trách nhiệm và thuộc tính chất lượng. Điều khác biệt là chọn **mức chi tiết vừa đủ để giảm rủi ro quan trọng**, không khóa mọi đường phát triển tương lai.

### 4.1. Những câu hỏi nên làm rõ trước lát cắt đầu

| Chủ đề | Câu hỏi cần trả lời sớm | Vì sao có thể khó sửa muộn? |
|---|---|---|
| **Danh tính và phân quyền** | Dữ liệu gắn với ai, ai được đọc/sửa, xác thực bằng cách nào? | Rò rỉ dữ liệu, thay đổi toàn hệ thống, ảnh hưởng người dùng |
| **Tính toàn vẹn dữ liệu** | Có ràng buộc duy nhất, nhất quán và nguồn sự thật nào? | Dữ liệu trùng hoặc sai, phải làm sạch/di trú |
| **Giao dịch và idempotency** | Gửi yêu cầu/callback lặp thì sao? | Thanh toán, cấp quyền hoặc ghi nhận trùng |
| **Tích hợp ngoài** | Hợp đồng API, định dạng sự kiện, thời gian phản hồi, thất bại? | Bên thứ ba/đội khác phụ thuộc vào giao diện đã công bố |
| **Khả năng quan sát** | Làm sao phát hiện lỗi, xác định nơi sai và điều tra sự cố? | Lỗi production khó tái hiện nếu thiếu dữ liệu cần thiết |
| **Quản lý thay đổi** | Có thể deploy/rollback/migrate theo bước không? | Thay đổi dữ liệu hoặc dịch vụ có thể gây gián đoạn |
| **Hiệu năng/thông lượng** | Có SLO hay tải tối thiểu đã biết nào? | Thiết kế đồng bộ/chờ lâu có thể không chịu tải thực |
| **Khả năng truy cập** | Nhóm người dùng và tiêu chuẩn áp dụng là gì? | UI có thể phải thiết kế lại nếu bỏ qua từ đầu |
| **Nghĩa vụ tuân thủ** | Cần ghi dấu vết và phê duyệt nào? | Không thể bổ sung bằng chứng lịch sử đã bỏ qua |

Mức độ nghiên cứu tùy rủi ro. Ví dụ, với một biểu mẫu không lưu dữ liệu nhạy cảm, không cần thiết kế kiến trúc phân tán. Với hệ thống thanh toán, làm rõ trạng thái, quyền và dữ liệu là công việc cần thiết ngay từ đầu.

### 4.2. Đường tiến hóa kiến trúc — không cần biết trước mọi nhánh

~~~mermaid
flowchart TD
    A["Ràng buộc đã xác nhận và mục tiêu người dùng"] --> B["Thiết kế lát cắt nhỏ có chất lượng"]
    B --> C["Kiểm thử / tích hợp / triển khai an toàn"]
    C --> D["Dữ liệu thật và phản hồi người dùng"]
    D --> E{"Thiết kế hiện tại còn đáp ứng?"}
    E -->|"Có"| F["Giữ đơn giản; giao lát cắt kế"]
    E -->|"Không"| G["Chỉ ra nguyên nhân, rủi ro và lựa chọn sửa"]
    G --> H["Refactor / migrate / đổi ranh giới theo bước"]
    H --> C
    F --> B
~~~

Sơ đồ là chu trình học tập, **không phải bảo đảm mọi vấn đề đều sửa được bằng refactoring nhỏ**. Khi hệ thống cần di trú dữ liệu lớn hoặc đổi giao thức công khai, có thể cần chương trình thay đổi theo nhiều bản phát hành và kế hoạch khôi phục.

### 4.3. Ranh giới mô-đun đơn giản thường có giá trị

Một dấu hiệu thiết kế tốt là **thay đổi một quy tắc không buộc sửa những phần không liên quan**. Trong nền tảng học, ví dụ:

- Quy tắc ghi danh nên được thực thi ở thành phần nghiệp vụ thích hợp, không chỉ ở UI.
- Mã định danh tài khoản phải được xác thực trước khi truy xuất dữ liệu riêng tư.
- Giao tiếp với nhà cung cấp email hoặc thanh toán nên có ranh giới rõ khi nguy cơ thay đối tác là thật.
- Những trường hợp lỗi quan trọng phải có cách biểu diễn nhất quán.

Nhưng ranh giới không đòi hỏi xây ngay một **microservice cho mỗi user story**. Một **modular monolith** có ranh giới trách nhiệm rõ có thể là lựa chọn đủ dùng tốt hơn mạng lưới dịch vụ phân tán, nhất là khi đội còn nhỏ và yêu cầu tải chưa buộc tách dịch vụ.

### 4.4. Tránh trừu tượng hóa dựa trên một ví dụ

Giả sử hiện chỉ có một loại thông báo email. Một Developer muốn tạo:

~~~text
MessageProviderFactory
  -> AbstractMessageStrategy
      -> EmailAdapter
      -> SmsAdapter (chưa dùng)
      -> PushAdapter (chưa dùng)
  -> GenericWorkflowRuleEngine
  -> MultiTenantRoutingConfiguration
~~~

Cấu trúc này có thể cần trong một sản phẩm thật với nhiều kênh đã được xác nhận, nhưng nếu hiện chỉ có một thông báo email, nó có thể tạo chi phí cấu hình, test và hiểu biết cao hơn ích lợi.

Thiết kế đủ dùng có thể là:

~~~text
EnrollmentService
  -> NotificationSender.sendEnrollmentStatus(...)
       -> EmailNotificationSender
~~~

Một giao diện nhỏ chỉ có ích khi có **ranh giới trách nhiệm hoặc nhu cầu thay đổi thực**, không phải vì “mọi lớp đều phải có interface”. Khi thêm kênh thứ hai và thấy phần khác biệt, nhóm có thể rút ra abstraction dựa trên **hai ví dụ thật** thay vì dự đoán sẵn mọi biến thể.

### 4.5. Architectural Decision Record (ADR)

Một **ADR** ngắn có thể giúp ghi lại những quyết định khó hiểu hoặc khó đảo ngược:

~~~text
ADR-007 — Luu yeu thich theo tai khoan trong cung CSDL

BOI CANH:
  Nhu cau hien tai: hoc vien luu khoa va xem lai sau dang nhap.
  Chua co bang chung can he thong goi y phan tan.

QUYET DINH:
  Luu (user_id, course_id) trong mot bang co rang buoc duy nhat.
  Truy cap phai kiem tra danh tinh tai khoan.

LUA CHON DA XEM:
  A. Local storage trong trinh duyet.
  B. Co so du lieu hien tai.
  C. Dich vu yeu thich rieng.

LY DO:
  B dap ung nhu cau dong bo va quyen voi chi phi hien tai hop ly.

RUI RO / DOI DOI:
  Can quan sat so luong yeu thich, tai va cache neu lon.

TRIGGER XEM LAI:
  Khi co yeu cau tich hop/luu luong duoc kiem chung,
  hoac do tre truy van vuot muc muc tieu da thong nhat.
~~~

ADR là **thực hành tùy chọn**, không phải artifact chính thức của Scrum. Một quyết định đơn giản có thể không cần ADR; những quyết định ảnh hưởng nhiều đội, dữ liệu hoặc giao thức thường có lợi khi ghi bối cảnh, lý do và điều kiện xem lại.

## 5. Refactoring là công cụ giữ chi phí thay đổi thấp

**Refactoring** là điều chỉnh cấu trúc nội bộ của phần mềm mà không chủ đích thay đổi hành vi quan sát được. Trong thiết kế tiến hóa, refactoring giúp làm thiết kế hiện tại rõ hơn khi hiểu biết tăng.

Ví dụ:

- Tách quy tắc cấp quyền khỏi controller.
- Đặt tên lại các khái niệm nghiệp vụ bị hiểu sai.
- Loại bỏ nhánh điều kiện trùng lặp.
- Chia một hàm quá lớn thành các thành phần có trách nhiệm rõ.
- Đổi nơi quản lý kết nối tới hệ thống ngoài mà giữ hợp đồng hành vi.

### 5.1. Refactoring khác thêm tính năng và sửa lỗi

| Hoạt động | Mục đích | Thay đổi hành vi ngoài? | Bằng chứng thường cần |
|---|---|---|---|
| **Refactoring** | Cải thiện cấu trúc/code | Không chủ đích thay đổi | Regression tests, review, so sánh hợp đồng |
| **Thêm tính năng** | Bổ sung hành vi người dùng cần | Có | AC, test mới, kiểm tra tác động |
| **Sửa lỗi** | Khắc phục hành vi sai | Có, để đưa về đúng | Test tái hiện lỗi, regression |
| **Thay kiến trúc/di trú** | Thay ranh giới hoặc hạ tầng đáng kể | Có thể giữ hành vi, nhưng có rủi ro dữ liệu/vận hành | Migration test, kiểm tra tương thích, triển khai từng phần |

Không nên gọi một lần viết lại 50% hệ thống là “refactor nhỏ” chỉ để giảm cảm nhận rủi ro. Các thay đổi lớn có thể đòi hỏi kế hoạch chuyển đổi, khả năng chạy song song và xử lý dữ liệu.

### 5.2. Refactoring thường xuyên thay vì “dọn nợ một lần”

Nếu đội luôn hứa sẽ “làm sạch code vào cuối quý”, độ phụ thuộc và khó hiểu có thể tích lũy, khiến mỗi PBI sau đắt hơn. Cách tiếp cận thực dụng:

1. Khi sửa một vùng code cho nhu cầu thật, xem xét cấu trúc nào đang cản thay đổi.
2. Bổ sung kiểm thử cần thiết để biết hành vi không đổi.
3. Refactor từng bước nhỏ, chạy lại kiểm thử và tích hợp thường xuyên.
4. Không tự ý mở rộng thành một cuộc viết lại không liên quan đến mục tiêu.
5. Với khoản đầu tư kỹ thuật lớn, đưa nó vào lựa chọn sản phẩm/kỹ thuật với lý do rủi ro và kết quả mong đợi.

**Không nên hiểu “luôn refactor” là cải tiến thẩm mỹ vô hạn.** Một refactoring tốt giải quyết chi phí hoặc rủi ro có thật, không đổi tên lớp chỉ để thống nhất sở thích cá nhân khi việc đó không giúp hệ thống.

### 5.3. Một ví dụ Java: tách quy tắc nghiệp vụ mà không phức tạp hóa

Ban đầu, quy tắc “đã xác nhận giao dịch hợp lệ mới cấp quyền” được nhúng trong controller:

~~~java
public void handlePaymentCallback(PaymentEvent event) {
    // Sai nếu chỉ tin trạng thái do request bên ngoài tự khai báo.
    if ("SUCCESS".equals(event.status())) {
        grantCourseAccess(event.orderId());
    }
}
~~~

Trong triển khai thật, cần xác thực nguồn sự kiện, kiểm tra liên hệ giữa giao dịch/đơn, trạng thái và việc xử lý lặp. Một thiết kế được làm rõ hơn có thể tách ranh giới:

~~~java
public final class EnrollmentPaymentHandler {
    private final PaymentVerifier verifier;
    private final EnrollmentRepository enrollments;

    public EnrollmentPaymentHandler(PaymentVerifier verifier,
                                    EnrollmentRepository enrollments) {
        this.verifier = verifier;
        this.enrollments = enrollments;
    }

    public void onPaymentEvent(PaymentEvent event) {
        VerifiedPayment payment = verifier.verify(event);
        if (!payment.isConfirmed()) {
            return;
        }
        // Repository phải xử lý idempotency và tính nguyên tử phù hợp;
        // method này là minh họa ranh giới, chưa phải hệ thống thanh toán đầy đủ.
        enrollments.grantAccessOnce(payment.orderId(),
                                    payment.courseId(),
                                    payment.userId());
    }
}
~~~

Ví dụ thứ hai **không tự tạo bảo mật chỉ vì thêm interface**. Tính đúng đắn phụ thuộc vào implementation của \`PaymentVerifier\`, ràng buộc dữ liệu, xử lý giao dịch/đua tranh, audit và kiểm thử thực tế. Tuy nhiên, ranh giới này giúp tách **xác thực nhà cung cấp** khỏi **quy tắc cấp quyền**, có thể thuận lợi khi cần thay đổi tích hợp hoặc kiểm thử.

Đừng tạo thêm \`PaymentStrategyRegistryFactory\` nếu chỉ có một tích hợp và chưa thấy lý do thực. Sự đơn giản nằm ở **trách nhiệm rõ và ít giả định thừa**, không ở số lớp tối thiểu hay tối đa.

## 6. TDD, kiểm thử và CI tạo điều kiện cho thiết kế tiến hóa

Đội chỉ có thể thay đổi thiết kế thường xuyên khi có cách **phát hiện hồi quy đáng tin**. Nếu refactor xong phải kiểm tra thủ công toàn bộ sản phẩm trong nhiều tuần, chi phí thay đổi rất cao và nhóm sẽ ngại cải thiện cấu trúc.

### 6.1. TDD trong XP

**Test-Driven Development** thường dùng vòng:

1. **Red:** viết một test nhỏ thất bại cho hành vi cần có.
2. **Green:** bổ sung mức mã cần thiết để test đạt.
3. **Refactor:** cải thiện cấu trúc khi test vẫn bảo vệ hành vi.

Ví dụ quy tắc **lưu cùng khóa yêu thích hai lần không tạo bản ghi trùng**:

~~~java
@Test
void savingTheSameCourseTwiceDoesNotCreateDuplicates() {
    favorites.save("learner-A", "course-X");
    favorites.save("learner-A", "course-X");

    assertEquals(1, favorites.count("learner-A", "course-X"));
}
~~~

Test trên chỉ minh họa điều kiện nghiệp vụ; \`favorites\` là fixture hoặc đối tượng kiểm thử do đội định nghĩa. Với hệ thống thật, vẫn cần test về **truy cập trái quyền, lưu trữ bền vững, cạnh tranh đồng thời và lỗi dịch vụ** ở lớp thích hợp.

### 6.2. BDD/Acceptance tests giúp tránh refactor “đúng code nhưng sai nhu cầu”

Khi một lát cắt cần hành vi rõ ràng, Product Owner/đại diện nghiệp vụ, Developers và testers có thể trao đổi các ví dụ:

~~~gherkin
Feature: Luu khoa hoc yeu thich

  Scenario: Hoc vien xem lai khoa da luu
    Given hoc vien A da dang nhap
    And khoa X ton tai va duoc phep hien thi
    When A luu khoa X vao danh sach yeu thich
    And A dang xuat va dang nhap lai
    Then danh sach yeu thich cua A co khoa X

  Scenario: Khong tao yeu thich trung
    Given A da luu khoa X
    When A gui lai yeu cau luu khoa X
    Then he thong khong tao ban ghi yeu thich trung

  Scenario: Tai khoan khac khong duoc doc du lieu cua A
    Given hoc vien B da dang nhap
    And A co danh sach yeu thich rieng
    When B yeu cau doc danh sach cua A
    Then he thong tu choi theo chinh sach phan quyen
~~~

**File Gherkin không phải bằng chứng test đã chạy.** Cần bước kiểm thử thực thi, dữ liệu, phiên bản build và điều kiện môi trường phù hợp. BDD giúp làm rõ **đúng điều cần xây**, còn TDD và chiến lược kiểm thử khác hỗ trợ **xây đúng và thay đổi an toàn**.

### 6.3. Nhiều lớp kiểm chứng bảo vệ những rủi ro khác nhau

| Kỹ thuật | Rủi ro được phát hiện tốt | Giới hạn |
|---|---|---|
| **Unit tests** | Logic, trường hợp biên và contract nội bộ | Không tự chứng minh tích hợp dữ liệu, phân quyền toàn hệ thống |
| **API/contract tests** | Hợp đồng giao tiếp và quy tắc dịch vụ | Không thay thế luồng UI và quyền xuyên suốt |
| **Integration tests** | Tương tác database, message broker, đối tác/mock có kiểm soát | Môi trường thử phải phản ánh rủi ro và giới hạn thực |
| **End-to-end tests** | Hành trình người dùng qua nhiều thành phần | Thường chậm/khó duy trì nếu dùng thay mọi lớp khác |
| **Kiểm thử khám phá** | Các cách dùng, lỗi UX và giả định ít được nghĩ tới | Phụ thuộc kỹ năng, bối cảnh, ghi nhận và thời gian |
| **Kiểm tra bảo mật, hiệu năng, accessibility** | Thuộc tính chất lượng quan trọng | Cần tiêu chuẩn và điều kiện kiểm chứng theo sản phẩm |

Không có tỷ lệ unit/integration/E2E chuẩn do Scrum hay XP bắt buộc cho mọi đội. **Chọn test theo rủi ro thực** và duy trì chúng sao cho kết quả tin cậy.

### 6.4. Continuous Integration hỗ trợ thay đổi từng bước

**CI** giúp phát hiện sớm lỗi khi những thay đổi nhỏ được tích hợp thường xuyên vào phiên bản chung. Một năng lực CI hữu ích thường cần:

- Build có thể lặp lại.
- Kiểm thử phù hợp chạy trên thay đổi tích hợp, không chỉ máy cá nhân.
- Lỗi hoặc test bị skip được nhìn thấy và xử lý.
- Thay đổi nhỏ, dễ truy vết; giảm nhánh tồn tại quá lâu.
- Có cách khôi phục build ổn định khi cần.

**CI không tự bảo đảm code đúng hoặc sản phẩm tạo giá trị.** Pipeline “xanh” với test không đại diện có thể cho cảm giác an toàn giả. Tuy nhiên, nếu thiếu tích hợp thường xuyên và test hồi quy, việc refactor và giao Increment nhỏ sẽ khó giữ chất lượng.

### 6.5. Definition of Done là ranh giới, không phải thứ để hạ cho vừa Sprint

Nếu dùng Scrum, **Definition of Done (DoD)** mô tả chính thức trạng thái Increment khi các tiêu chuẩn chất lượng áp dụng cho sản phẩm đã được đáp ứng. Một PBI chưa đáp ứng DoD không thể được tính là phần của Increment.

Trong thiết kế tiến hóa, có thể **giảm phạm vi tính năng chưa cần**, nhưng không nên **giảm chất lượng của phạm vi đã chọn**. Ví dụ:

- Có thể chưa xây bộ lọc gợi ý nâng cao.
- Không thể bỏ kiểm tra A/B tách dữ liệu tài khoản chỉ để tính tính năng yêu thích là Done.
- Có thể chọn một nhà cung cấp thanh toán cho lát cắt đầu.
- Không thể cấp quyền học khi giao dịch chưa được xác nhận đáng tin rồi hứa “sẽ thêm an toàn Sprint sau”.

Kết hợp test, CI, DoD và review giúp nhóm cải thiện thiết kế mà vẫn giao phần mềm có thể sử dụng.

## 7. Quản lý “nợ kỹ thuật” mà không dùng nó làm nhãn cho mọi thiết kế đơn giản

**Technical debt** thường được dùng như ẩn dụ về việc lựa chọn giải pháp kỹ thuật làm tăng chi phí thay đổi hoặc rủi ro về sau. Nó không đồng nghĩa **mọi code chưa hoàn hảo** hoặc **mọi giải pháp đơn giản** đều là nợ xấu.

### 7.1. Ba loại tình huống cần phân biệt

| Tình huống | Ví dụ | Cách ứng xử |
|---|---|---|
| **Thiết kế đơn giản có chủ đích** | Dùng một database và service mô-đun rõ cho quy mô hiện tại | Giữ khi đáp ứng yêu cầu, theo dõi trigger mở rộng |
| **Đánh đổi tạm thời được công bố** | Dùng luồng xử lý nhỏ để kiểm chứng giá trị, biết sẽ cần sửa khi traffic tăng | Ghi giả định, thời hạn/trigger, rủi ro và đường di trú |
| **Chất lượng thiếu khiến rủi ro không chấp nhận được** | Bỏ phân quyền hoặc tính toàn vẹn giao dịch để đóng ticket | Không xem đây là cách “vay nợ” hợp lệ nếu vi phạm yêu cầu bắt buộc; phải sửa trước khi gọi Done/phát hành theo quy định |

Một prototype có giới hạn dùng nội bộ **không phải production feature**. Nếu nhóm thử một giải pháp tạm trong sandbox, cần nói rõ nơi có thể sử dụng và điều gì chưa được kiểm chứng.

### 7.2. Theo dõi nợ bằng tác động, không chỉ bằng điểm “code smell”

Một bản ghi nợ kỹ thuật hữu ích:

~~~text
MUC:
  Phan logic tinh quyen hoc dang trung lap o 3 vi tri.

TAC DONG:
  Moi thay doi chinh sach phai sua nhieu noi, da co mot loi hoi quy.

BANG CHUNG:
  Duong code lien quan, su co, test thieu, thong tin cycle time.

PHUONG AN:
  Dua quy tac vao thanh phan chung co test bao ve.

RUI RO NEU TRI HOAN:
  Sai quyen hoc, tang thoi gian sua cac story lien quan.

CHI PHI / PHU THUOC:
  Uoc luong, test, pham vi migration va anh huong.

TRIGGER / MOC:
  Truoc khi mo rong quy tac, hoac khi thay doi tiet lo rui ro cao.
~~~

Không nên biến danh sách “nợ kỹ thuật” thành mọi sở thích refactoring chưa có hậu quả rõ. Cũng không nên bỏ công việc kỹ thuật quan trọng chỉ vì nó không tạo màn hình mới: khả năng giao giá trị trong tương lai phụ thuộc chất lượng của hệ thống hôm nay.

### 7.3. Nợ kỹ thuật và Product Backlog

Trong Scrum, Product Owner chịu trách nhiệm tối đa hóa giá trị và quản lý Product Backlog hiệu quả, Developers chịu trách nhiệm chất lượng và tạo Increment. Các khoản đầu tư kỹ thuật ảnh hưởng sản phẩm cần được thảo luận bằng **rủi ro, chi phí trì hoãn và năng lực cần tạo**.

Không phải mỗi refactor một dòng đều phải thành một Product Backlog Item riêng; cải thiện cấu trúc nhỏ trong khi triển khai có thể là phần của công việc đạt DoD. Nhưng một đợt thay thế kiến trúc có tác động lớn, cần năng lực nhiều Sprint hoặc ảnh hưởng roadmap nên được làm minh bạch ở mức kế hoạch phù hợp.

## 8. Thay đổi schema và dữ liệu: nơi thiết kế quá muộn có thể rất đắt

Dữ liệu đã lưu thật, nhất là dữ liệu có nhiều consumer và nghĩa vụ lưu trữ, thường **khó đảo ngược hơn code giao diện**. Không nên dùng khẩu hiệu “cứ đổi database khi cần” mà không tính tới tương thích, migration, tính nhất quán và khả năng khôi phục.

### 8.1. Ví dụ đổi mô hình yêu thích khóa học

Phiên bản đầu có bảng:

~~~sql
CREATE TABLE favorite_course (
    user_id   BIGINT NOT NULL,
    course_id BIGINT NOT NULL,
    created_at TIMESTAMP NOT NULL,
    PRIMARY KEY (user_id, course_id)
);
~~~

Ví dụ này phù hợp với nhu cầu **mỗi tài khoản lưu một khóa tối đa một lần** trong một hệ thống có kiểu định danh nêu trên. Trong sản phẩm thực, phải thiết kế thêm khóa ngoại, chính sách xóa, truy vấn/chỉ mục, bảo vệ dữ liệu và chuẩn thời gian tương ứng với cơ sở dữ liệu được chọn.

Sau đó Product Owner xác nhận nhu cầu **nhiều danh sách riêng** (ví dụ “Muốn học”, “Đang xem”, “Gửi bạn bè”), với quy tắc một khóa có thể thuộc nhiều danh sách. Việc thêm \`list_id\` có thể tác động API, UI, bảng dữ liệu và consumer. Đây là yêu cầu mới có bằng chứng; không có nghĩa nhóm đã sai khi chưa xây mọi loại danh sách từ đầu.

### 8.2. Expand–migrate–contract thay vì đổi schema phá vỡ ngay

Một kế hoạch tiến hóa thường gồm:

1. **Expand:** thêm cấu trúc mới tương thích (bảng/column/API) mà consumer cũ vẫn hoạt động.
2. **Migrate:** di trú dữ liệu hiện có, cập nhật writers/readers theo từng bước, kiểm chứng tính toàn vẹn và quan sát.
3. **Contract:** chỉ loại bỏ cấu trúc cũ sau khi consumer đã chuyển, dữ liệu được đối chiếu và có điều kiện an toàn.

~~~mermaid
flowchart LR
    A["Dữ liệu/schema cũ đang dùng"] --> B["Expand: thêm cấu trúc tương thích"]
    B --> C["Migrate: backfill, dual-read/write nếu cần"]
    C --> D["Kiểm chứng, theo dõi, chuyển consumer"]
    D --> E{"Đủ bằng chứng và rollback plan?"}
    E -->|"Chưa"| C
    E -->|"Có"| F["Contract: loại bỏ phần cũ có kiểm soát"]
~~~

**Dual-write không tự an toàn**: viết hai nơi có thể lệch dữ liệu nếu lỗi giữa chừng. Cần lựa chọn cách đồng bộ, idempotency, transaction/outbox hoặc reconciliation theo kiến trúc thực. **Rollback schema** có thể không đủ khi dữ liệu đã di trú bất khả nghịch; đôi khi cần kế hoạch roll-forward hoặc phục hồi từ bản sao đã kiểm chứng.

### 8.3. Một kế hoạch migration cần trả lời

| Vấn đề | Câu hỏi |
|---|---|
| **Compatibility** | Những phiên bản app/client/đối tác nào vẫn dùng cấu trúc cũ? |
| **Data correctness** | Làm sao bảo đảm không mất hoặc tạo trùng quan hệ yêu thích? |
| **Cutover** | Khi nào readers/writers chuyển; có thể chuyển từng nhóm không? |
| **Observability** | Đo số bản ghi, lỗi đọc/ghi, độ trễ, dữ liệu không khớp bằng gì? |
| **Rollback/recovery** | Khi gặp lỗi, đường khôi phục phù hợp cho code và dữ liệu là gì? |
| **Privacy/retention** | Dữ liệu cũ có chứa thông tin phải được xóa hoặc hạn chế truy cập không? |
| **Scale** | Backfill có thể gây khóa bảng, tải hoặc thời gian gián đoạn không? |

Không phải một migration nhỏ cần chương trình phê duyệt lớn, nhưng **mức độ thận trọng cần theo tính khó đảo và tác động**.

## 9. Hiệu năng và khả năng mở rộng: thiết kế theo ngưỡng đã hiểu

Một lỗi overengineering phổ biến là chọn kiến trúc phân tán “cho quy mô tương lai” trước khi có dữ liệu tải. Lỗi underdesign tương ứng là **không đo hiệu năng và mặc kệ bottleneck đã có bằng chứng**.

### 9.1. Trả lời câu hỏi về tải trước khi chọn hạ tầng

- Số người dùng đồng thời và dạng phân phối tải hiện tại là bao nhiêu?
- Tác vụ nào cần độ trễ thấp và ngưỡng nào là nghĩa vụ thật?
- Tỷ lệ đọc/ghi và sự tăng trưởng được dự báo dựa trên nguồn nào?
- Có thời điểm cao điểm theo kỳ khai giảng hoặc chiến dịch không?
- Những truy vấn nào chậm, vì sao: thiếu chỉ mục, khóa, mạng, xử lý đồng bộ?
- Thất bại của một thành phần ảnh hưởng gì tới trải nghiệm?
- Có thể mở rộng theo bước và kiểm tra trước khi phải thay kiến trúc lớn không?

### 9.2. Một ví dụ quyết định theo bằng chứng

**Giả định để minh họa:** ở hiện tại, truy vấn danh sách yêu thích đạt độ trễ tốt theo yêu cầu được thống nhất. Chỉ số sử dụng tăng và nhóm đo thấy truy vấn bắt đầu chậm do thiếu chỉ mục theo \`user_id\`. Thay vì lập tức xây cache phân tán, nhóm có thể:

1. Xác minh truy vấn và kế hoạch thực thi của database.
2. Bổ sung/chỉnh chỉ mục phù hợp và kiểm tra tác động lên ghi dữ liệu.
3. Đo latency, tài nguyên và lỗi sau thay đổi trên tải đại diện.
4. Xem việc phân trang hoặc giới hạn kích thước kết quả.
5. Chỉ xem cache/đọc phân tán khi có bằng chứng cần và kế hoạch nhất quán dữ liệu.

Đây là thiết kế tiến hóa: **giải quyết bottleneck được đo**, không chọn công nghệ theo độ nổi tiếng. Nếu hợp đồng đã yêu cầu khối lượng lớn ngay ngày đầu, cần kiểm chứng hiệu năng tương ứng **trước** khi phát hành, không đợi production hỏng.

### 9.3. Feature flags và triển khai từng phần

Feature flag có thể giảm rủi ro khi thử một thiết kế mới:

- Bật cho nhóm nhỏ phù hợp.
- So sánh lỗi/latency hoặc kết quả tác vụ.
- Tắt nhanh một khả năng nếu an toàn để tắt.
- Chuyển dần người dùng sau khi có dữ liệu.

Nhưng feature flag **không giải quyết mọi thay đổi dữ liệu**, không đảm bảo rollback và có thể tạo nhánh logic phức tạp nếu không được dọn. Cần người phụ trách, thời hạn/điều kiện loại flag và kiểm tra cả trạng thái bật/tắt theo rủi ro.

### 9.4. Kiến trúc có thể quan sát được là khoản đầu tư “đủ dùng”

Nếu nhóm không biết phần mềm lỗi ở đâu, mỗi thay đổi đều khó xác minh. Logging phù hợp, metrics, tracing, correlation ID và cảnh báo có thể tạo **đường kiểm tra thiết kế sau phát hành**. Mức độ đầu tư theo rủi ro; ghi log phải tránh lộ dữ liệu cá nhân hoặc bí mật.

## 10. Tạo thông tin mới trước một quyết định đắt: spikes, prototypes và experiments

Khi thiếu dữ liệu, một phương án thiết kế tốt là **chủ động giảm bất định** thay vì đoán chắc hoặc trì hoãn vô thời hạn.

### 10.1. Phân biệt ba loại hoạt động

| Hoạt động | Câu hỏi thường trả lời | Kết quả cần có | Cảnh báo |
|---|---|---|---|
| **Technical spike** | Có tích hợp API, đạt latency hoặc migrate dữ liệu được không? | Bằng chứng khả thi, giới hạn, rủi ro và lựa chọn tiếp theo | Spike code có thể bỏ, không tự là Increment production |
| **Prototype** | Giao diện/luồng giải pháp có dễ hiểu không? | Phản hồi người dùng hoặc kiểm tra thiết kế | Prototype chưa đạt an toàn/DoD không được ngụy trang thành sản phẩm |
| **Product experiment** | Tính năng có cải thiện outcome không? | Dữ liệu hành vi và quyết định đầu tư hay đổi hướng | Kết quả cần phương pháp đo và giới hạn suy luận phù hợp |

Một spike tốt có **câu hỏi cụ thể, thời hạn hoặc giới hạn công sức, điều kiện kết thúc và cách báo kết quả**.

### 10.2. Ví dụ spike thanh toán

~~~text
SPK-PAY-01 — Kiem chung callback lap va den muon

CAU HOI:
  Doi tac co the gui callback trung, sai thu tu hoac cham khong?
  Co cach xac thuc su kien va truy van trang thai dang tin khong?

PHAM VI:
  Chi lam ket noi sandbox, xu ly mot bo tinh huong doi tac cong bo.

BANG CHUNG:
  Log/trace da an thong tin nhay cam, ket qua test, gioi han sandbox,
  tai lieu contract va cac truong hop chua kiem chung.

THOI HAN:
  Ngan, duoc nhom thoa thuan theo gia tri cua thong tin can thu.

QUYET DINH SAU SPIKE:
  Giao dien tich hop, quy tac idempotency, duong loi va pham vi dau tien.

KHONG TUYEN BO:
  Chua coi giao dich production da an toan hoac dat DoD.
~~~

Spike có thể tạo thông tin quan trọng giúp tránh thiết kế sai mô hình giao dịch. Nhưng nếu thời gian điều tra kéo dài không giới hạn hoặc không dẫn tới quyết định, hoạt động ấy không còn giúp học sớm.

### 10.3. Quy tắc chọn lúc thực nghiệm

Hỏi:

1. **Bất định nào có tác động lớn nhất đến thiết kế?**
2. **Thí nghiệm nhỏ nhất** có thể phân biệt các lựa chọn là gì?
3. Dữ liệu nào đủ tin cậy để ra quyết định?
4. Nếu kết quả không rõ, có thể giữ đường thay đổi mở thêm không?
5. Có rủi ro an toàn/hợp đồng khiến thử trên production không phù hợp không?

Với dữ liệu nhạy cảm, nên dùng dữ liệu giả hoặc đã xử lý theo chính sách; không đưa người dùng thật vào một thử nghiệm có rủi ro chưa được phê duyệt.

## 11. Tình huống xuyên suốt: phát triển tính năng lưu khóa học yêu thích

> **Tình huống hoàn toàn giả định để học tập.** Tất cả thời gian, tỷ lệ, mức chi phí và quyết định ở phần này chỉ minh họa cách lập luận; không phải số liệu thực nghiệm hoặc chuẩn kỹ thuật áp dụng chung.

Một Scrum Team xây nền tảng học trực tuyến với Product Goal: **“Học viên tìm và bắt đầu những khóa phù hợp mà không mất thời gian tìm lại.”** Dữ liệu nghiên cứu ban đầu cho thấy học viên hay mở nhiều khóa để so sánh, nhưng chưa có bằng chứng họ cần một hệ thống gợi ý thông minh hay chia sẻ danh sách cho bạn bè.

Product Owner đề xuất PBI:

> Là học viên đã đăng nhập, tôi muốn lưu khóa học đang quan tâm và xem lại danh sách của mình để tiếp tục so sánh hoặc đăng ký sau.

Developers nhận thấy có ba nhóm quyết định:

1. **Hành vi phải đúng ngay:** lưu bền vững, xem lại sau đăng nhập, phân quyền theo tài khoản, không tạo bản ghi trùng, xử lý lỗi trung thực.
2. **Cấu trúc cần đủ tốt:** trách nhiệm UI/API/storage rõ, dữ liệu có khóa duy nhất, có kiểm thử để sửa an toàn.
3. **Khả năng còn là giả thuyết:** nhiều danh sách, đồng bộ qua bên thứ ba, social sharing, AI ranking, xử lý tải lớn.

### 11.1. Hai phương án cực đoan

**Phương án A — xây trước tương lai chưa có bằng chứng:**

~~~text
Favorites Microservice
-> Event Broker
-> Recommendation Engine
-> Multi-List Domain Layer
-> Social Sharing Gateway
-> Distributed Cache Cluster
-> Reporting Data Pipeline
~~~

Rủi ro: đội mất nhiều thời gian trước khi học viên dùng được một hành vi đơn giản; độ phức tạp vận hành, tích hợp và kiểm thử tăng. Nếu người dùng chỉ cần lưu và xem lại, phần lớn hạ tầng có thể không đem lại giá trị.

**Phương án B — làm tạm đến mức sai nhu cầu:**

~~~text
UI heart.toggleColor()
-> localStorage["favorites"] = courseId
-> Không xác thực user_id khi đọc API
-> Không có dữ liệu bền vững giữa thiết bị
~~~

Rủi ro: user story chưa được đáp ứng, quyền truy cập có thể sai, dữ liệu mất và buộc làm lại luồng đã công bố là hoàn tất.

### 11.2. Phương án C — một lát cắt đúng và có đường phát triển

Nhóm thiết kế:

~~~mermaid
flowchart LR
    UI["Course UI / Favorites list"] --> API["Favorites API"]
    API --> AUTH["Xác thực và phân quyền"]
    API --> SVC["Favorites application logic"]
    SVC --> DB[("favorite_course<br/>unique(user_id, course_id)")]
    API -. "Mã lỗi và phản hồi" .-> UI
    TEST["Test API + DB + hai tài khoản"] -. "Kiểm chứng" .-> API
~~~

Điều cần giữ:

- UI không là nơi duy nhất quyết định ai sở hữu bản ghi.
- API kiểm tra danh tính và quyền truy cập tương ứng.
- Dữ liệu lưu bền vững với ràng buộc duy nhất thích hợp.
- Yêu cầu lặp được xử lý theo ngữ nghĩa đã thống nhất.
- Khi lưu thất bại, UI không báo thành công giả.
- Mã được tích hợp, kiểm thử và đạt DoD áp dụng.

Điều **chưa** cần nếu chưa có bằng chứng:

- Nhiều loại danh sách công khai.
- Thuật toán gợi ý dựa trên hành vi.
- Tích hợp mạng xã hội và API bên ngoài.
- Hạ tầng phân tán chuyên dụng.

Một điểm quan trọng: **thiết kế đơn giản không loại trừ ranh giới rõ**. Mô hình sử dụng một database và vài thành phần rõ trách nhiệm có thể dễ bảo trì hơn hệ thống nhiều dịch vụ cho quy mô hiện tại.

### 11.3. Làm rõ acceptance criteria với Product Owner

| ID | Tiêu chí chấp nhận minh họa | Lý do kỹ thuật |
|---|---|---|
| **AC-01** | Học viên A lưu khóa X và thấy trong danh sách sau đăng xuất/đăng nhập lại | Cần lưu bền vững theo tài khoản |
| **AC-02** | A lưu X nhiều lần không tạo bản ghi trùng hoặc trạng thái sai | Cần ngữ nghĩa lặp và tính toàn vẹn |
| **AC-03** | Học viên B không được đọc/sửa danh sách của A | Cần phân quyền server-side, không chỉ ẩn UI |
| **AC-04** | Khi lưu thất bại, hệ thống không khẳng định thành công và có hướng xử lý phù hợp | Cần xử lý lỗi và phản hồi trung thực |
| **AC-05** | Khi khóa bị ẩn/xóa theo quy tắc, danh sách không tiết lộ thông tin trái quyền | Cần làm rõ dữ liệu liên kết và chính sách hiển thị |
| **AC-06** | Giao diện lưu và danh sách có thể sử dụng theo yêu cầu truy cập áp dụng | Tránh thiết kế chỉ chạy với chuột hoặc một trạng thái UI |

AC là ví dụ **cần được điều chỉnh theo sản phẩm thật**. Với một ứng dụng chỉ cho phép khách vãng lai lưu tạm mà mục tiêu là xem trong cùng thiết bị, chính sách lưu bền vững có thể khác; lúc đó user story phải mô tả đúng mong đợi.

### 11.4. Giai đoạn 1 — chọn cấu trúc ít cam kết không cần thiết

Developers cân nhắc ba lựa chọn:

| Lựa chọn | Ưu điểm | Rủi ro |
|---|---|---|
| Local storage | Triển khai rất nhanh, không cần backend | Không đáp ứng đồng bộ theo tài khoản; nguy cơ dùng sai quyền nếu kết hợp API thiếu kiểm tra |
| DB trong ứng dụng hiện tại | Dễ tích hợp và vận hành, phù hợp dữ liệu bền vững theo tài khoản | Cần đặt ranh giới và kiểm soát schema tốt khi mở rộng |
| Microservice riêng | Có thể cô lập vòng đời triển khai | Thêm mạng, auth, theo dõi sự cố, CI/CD, dữ liệu và vận hành; lợi ích chưa chắc bù chi phí |

Đội chọn **DB trong ứng dụng hiện tại** vì đáp ứng AC và rủi ro với mức phức tạp hợp lý. Đây không phải khẳng định “monolith luôn tốt hơn microservice”; nếu một hệ thống đã có kiến trúc dịch vụ và yêu cầu khác, lựa chọn có thể thay đổi.

### 11.5. Giai đoạn 2 — xây Increment có thể kiểm chứng

Nhóm thực hiện:

1. Tạo ràng buộc dữ liệu, API và kiểm tra server-side.
2. Bổ sung unit/API/integration tests theo trường hợp quan trọng.
3. Thử với hai tài khoản tách biệt và qua hai phiên đăng nhập.
4. Tích hợp thường xuyên với build chung.
5. Kiểm tra UI trong các trạng thái loading, lỗi, đã lưu/chưa lưu và khả năng truy cập.
6. Hoàn tất DoD trước khi coi story Done.
7. Cung cấp cho người dùng phù hợp để nhận phản hồi sau khi đủ điều kiện phát hành.

Tại Sprint Review, Product Owner và stakeholders kiểm tra Increment thật thay vì chỉ xem mockup. Nếu vẫn chưa có tính năng production, nhóm nói rõ đó là prototype hay kết quả spike; không đánh tráo mức hoàn tất.

### 11.6. Giai đoạn 3 — phản hồi giúp quyết định có mở rộng không

Giả sử sau bản phát hành nhỏ, dữ liệu và phỏng vấn cho thấy:

- Nhiều người dùng quay lại danh sách đã lưu.
- Một số học viên muốn phân nhóm khóa theo dự định học.
- Nhiều người không quan tâm việc chia sẻ ra ngoài.
- Độ trễ truy vấn vẫn trong ngưỡng chất lượng đang áp dụng.

Product Owner cân nhắc ưu tiên **nhiều danh sách** trước **social sharing**. Developers nhận thấy schema hiện tại cần mở rộng; nhóm thiết kế migration theo bước thay vì bỏ bảng cũ ngay.

Đây là **chi phí tiến hóa có căn cứ từ nhu cầu mới**. Không nên gọi mọi thay đổi schema là “nợ do thiết kế kém” nếu lựa chọn ban đầu đã phù hợp với dữ liệu và rủi ro lúc đó.

### 11.7. Giai đoạn 4 — khi tải lớn lên

Giả sử lượng yêu thích tăng mạnh theo kỳ khai giảng, nhóm đo thấy:

- Một truy vấn danh sách chậm khi trả về quá nhiều khóa.
- Một số request không được phân trang.
- CPU database tăng trong đợt marketing.

Nhóm không lập tức tách microservice. Trước tiên:

1. Đối chiếu SLO hoặc ngưỡng thực đã thỏa thuận.
2. Tối ưu truy vấn/indexing và thêm phân trang phù hợp.
3. Kiểm tra tải đại diện, nhất là trường hợp đọc đồng thời.
4. Cân nhắc cache hoặc replica nếu số liệu vẫn cho thấy cần.
5. Đặt điều kiện và đường chuyển nếu cần tách thành dịch vụ sau này.

Một kiến trúc phân tán có thể hợp lý ở tương lai, nhưng **mốc đầu tư xuất hiện khi lợi ích vượt chi phí và rủi ro** chứ không vì một tỷ lệ traffic bất kỳ được chép từ bài hướng dẫn khác.

### 11.8. Những điều cần học từ tình huống

**Làm tốt:** hoàn tất tính năng hiện tại với dữ liệu, quyền và chất lượng đúng; có test, ranh giới và cách đo để thay đổi sau.

**Không cần làm ngay:** mô hình gợi ý hoặc nền tảng phân tán chưa có nhu cầu được chứng minh.

**Không được bỏ:** tính đúng đắn, DoD, bảo mật, khả năng khôi phục dữ liệu và bằng chứng kiểm thử liên quan.

**Khi thay đổi:** mở rộng khi có dữ liệu, đánh giá chi phí di trú và dùng từng bước tương thích để tránh rủi ro “big bang”.

## 12. Khi nào nên đầu tư thêm thiết kế trước khi thêm tính năng?

Độ sâu thiết kế phải tỷ lệ với **nguy cơ nếu sai**, không phải với độ hấp dẫn công nghệ.

### 12.1. Một bảng gợi ý quyết định

| Tình huống | Dấu hiệu | Can thiệp phù hợp |
|---|---|---|
| **Thêm trường UI ít rủi ro** | Đã hiểu hành vi, thay đổi cục bộ, có test | Thiết kế đơn giản và thử nhanh |
| **Thêm đối tác thanh toán** | API chưa rõ, callback lặp, dữ liệu có tiền | Spike/contract tests, ranh giới tích hợp, idempotency, kiểm tra bảo mật |
| **Thêm loại khóa học mới** | Quy tắc đang lặp qua nhiều module | Refactor phần chung đã hiểu; tránh tạo framework tổng quát trước khi thấy biến thể thực |
| **Tách database** | Nhiều consumer, dữ liệu lịch sử lớn | ADR, kế hoạch tương thích/migration, đo và rollback/roll-forward |
| **Tăng tải rõ rệt** | Latency vượt mục tiêu, truy vấn nóng | Đo bottleneck, tối ưu theo bằng chứng, cân nhắc kiến trúc mới theo ngưỡng |
| **Một tính năng chưa rõ nhu cầu** | Có giả thuyết nhưng ít bằng chứng người dùng | Prototype hoặc experiment giới hạn; trì hoãn đầu tư kiến trúc lớn |
| **Báo lỗi hồi quy lặp đi lặp lại** | Mỗi thay đổi nhỏ gây hỏng nơi khác | Tăng test, cải thiện CI, refactor vùng phụ thuộc cao |
| **Khung/phương pháp tổ chức không hiệu quả** | Họp đủ nhưng nhiều item chưa Done | Nhìn DoD, phụ thuộc, WIP và quyền quyết định; không giải quyết bằng thêm ceremony đơn thuần |

Đây là **heuristic để thảo luận**, không phải máy tự quyết kiến trúc. Hai đội có hệ thống và mức rủi ro khác nhau có thể chọn đầu tư khác nhau.

### 12.2. Cách nhìn theo “chi phí làm lại” và “chi phí chuẩn bị”

Giả sử hai phương án cho cùng một chức năng:

| Thành phần cân nhắc | Chuẩn bị thêm hôm nay | Không chuẩn bị, sửa sau |
|---|---|---|
| Phí thiết kế/kiểm chứng ban đầu | Cao hơn | Thấp hơn |
| Khả năng cần phần bổ sung | Có thể thấp hoặc chưa biết | Có thể thấp hoặc chưa biết |
| Rủi ro di trú dữ liệu | Có thể giảm nếu thiết kế đúng | Có thể tăng nếu quyết định đầu phụ thuộc nhiều |
| Chi phí vận hành duy trì | Có thể tăng nếu thêm hạ tầng | Có thể thấp hơn ở giai đoạn đầu |
| Thời gian đến phản hồi người dùng | Có thể lâu hơn | Có thể sớm hơn |
| Độ linh hoạt khi thay đổi | Phụ thuộc thiết kế thật, không chỉ số lớp | Phụ thuộc ranh giới, tests và dữ liệu đã công bố |

Đội cần **đặt thời gian đến phản hồi và giá trị học tập vào phép so sánh**, không chỉ số giờ code hôm nay và số giờ refactor trong tương lai.

### 12.3. “Thiết kế trước ít” không có nghĩa “để trống những ràng buộc”

Ví dụ sản phẩm phải xử lý dữ liệu tài chính hoặc đáp ứng khả năng truy cập theo chuẩn đã áp dụng. Một thiết kế đủ dùng có thể rất nhỏ về phạm vi, nhưng phải **đủ kỹ để thỏa điều kiện đó**.

Nếu người ra quyết định yêu cầu “cắt toàn bộ logging và test để giảm tiến độ”, Developers cần giải thích:

- Những rủi ro nào tăng và không thể chấp nhận?
- Có thể **giảm phạm vi** mà vẫn giữ điều kiện chất lượng không?
- Có thể **tự động hóa** hoặc **dùng lại hạ tầng** để giảm chi phí kiểm chứng không?
- Ai có quyền quyết định rủi ro ngoài phạm vi nhóm?

Không tự chọn bỏ kiểm soát có nghĩa vụ pháp lý; cũng không gọi mọi bước giấy tờ là “bắt buộc” nếu chưa kiểm tra căn cứ thật.

## 13. Scrum, Kanban và XP giúp thiết kế tiến hóa như thế nào?

Thiết kế tiến hóa không phải sự kiện Scrum mới hoặc kỹ thuật được Kanban bắt buộc. Nó là cách ra quyết định kỹ thuật được hỗ trợ bởi **phản hồi, chất lượng và quản lý dòng công việc**.

### 13.1. Scrum: mục tiêu và Increment tạo nhịp học

Trong Scrum:

- **Product Goal** giúp đánh giá vì sao một khoản đầu tư thiết kế đáng làm.
- **Product Backlog** phản ánh cả giá trị, rủi ro và khả năng sản phẩm cần được cải thiện.
- **Sprint Goal** tạo trọng tâm để Developers chọn lát cắt và cân nhắc những công việc kỹ thuật hỗ trợ.
- **Definition of Done** bảo vệ Increment khỏi trạng thái “code xong nhưng chưa tích hợp”.
- **Sprint Review** giúp kiểm tra phần mềm và bối cảnh người dùng, điều chỉnh thứ tự.
- **Sprint Retrospective** giúp đội cải tiến cách thiết kế, kiểm thử, cộng tác và xử lý phụ thuộc.

Scrum Guide không quy định một công thức kiến trúc hay bắt buộc TDD, ADR, microservice, story point hoặc CI tool cụ thể. Nhóm phải chọn thực hành kỹ thuật phù hợp để **thực sự tạo Increment đáp ứng DoD**.

**Quan trọng:** Không thể gọi một PBI chưa đạt DoD là Done với lý do “chúng ta theo thiết kế tiến hóa, sẽ sửa sau”. Thiết kế tiến hóa điều chỉnh cấu trúc sau khi học, không hợp thức hóa phần mềm thiếu chất lượng.

### 13.2. Kanban: kiểm soát số thay đổi dở dang

Khi nhiều tính năng được bắt đầu trước khi cái cũ tích hợp xong, việc cải thiện thiết kế sẽ khó: có nhiều nhánh code, nhiều migration song song, nhiều phụ thuộc và khó biết thay đổi nào gây lỗi.

Kanban có thể giúp:

- Trực quan hóa workflow phát triển–review–kiểm thử–triển khai.
- Giới hạn **WIP** để giảm số thay đổi cùng dở.
- Kéo công việc theo năng lực của bước sau.
- Dùng **work item age** để thấy item đang bị chặn.
- Dùng **cycle time** và **throughput** để nhìn khả năng hoàn tất.
- Tạo chính sách rõ cho bug, nợ kỹ thuật, migration và việc khẩn.

Không nhất thiết mọi item refactor phải đứng thành cột riêng. Nhưng nếu một thay đổi kiến trúc lớn nhiều Sprint không được nhìn thấy trong dòng công việc và dự báo, nhóm dễ tự che chi phí của nó.

### 13.3. XP: kỹ thuật để chi phí thay đổi không tăng mất kiểm soát

XP đóng góp những thực hành thường phù hợp với thiết kế tiến hóa:

- **TDD** để phát hiện lỗi logic và hỗ trợ refactoring.
- **Refactoring** liên tục để cải thiện cấu trúc có căn cứ.
- **Simple design** để tránh tính tổng quát không cần.
- **Continuous Integration** và phát hành nhỏ để kiểm tra thay đổi sớm.
- **Pair programming/collective ownership** khi phù hợp để chia sẻ hiểu biết.
- **On-site customer/Whole Team** để làm rõ ưu tiên và hành vi thường xuyên.
- **Sustainable pace** giúp nhóm cải tiến bền vững qua nhiều vòng, không phải trả giá bằng kiệt sức.

**Không phải cứ dùng XP thì mọi thay đổi sẽ rẻ.** Migration dữ liệu lớn, tích hợp đối tác hoặc thay giao thức công khai vẫn cần phân tích rủi ro, kế hoạch triển khai và bằng chứng.

### 13.4. Một bảng tổng hợp

| Cách tiếp cận | Phần hỗ trợ thiết kế tiến hóa | Giới hạn cần nhớ |
|---|---|---|
| **Scrum** | Mục tiêu, cơ hội kiểm tra Increment và cải tiến định kỳ | Không chỉ định toàn bộ kiến trúc/kiểm thử |
| **Kanban** | Giới hạn việc dở, nhìn điểm chặn và thời gian dòng công việc | Không tự làm code dễ thay hay chứng minh giá trị |
| **XP** | Simple design, tests, CI, refactoring, phản hồi khách hàng | Không xóa rủi ro dữ liệu, hệ thống ngoài và tổ chức |
| **DevOps** | Triển khai theo bước, quan sát production, kiểm soát thay đổi | Tăng deploy không có nghĩa tự động an toàn |
| **Product discovery** | Giảm đầu tư vào giải pháp sai nhu cầu | Prototype/khảo sát không tự là tính năng đạt DoD |
| **Lean** | Nhìn toàn dòng giá trị và tránh làm quá sớm | “Giảm lãng phí” không đồng nghĩa cắt kiểm thử/tuân thủ |

Các thực hành có thể kết hợp có chủ đích theo trở ngại được quan sát. Không cần áp mọi kỹ thuật như một danh sách chứng nhận “Agile đủ bộ”.

## 14. Kiểm tra mức độ linh hoạt của kiến trúc bằng bằng chứng

Một câu dễ gây hiểu lầm là: **“Chúng ta phải thiết kế cho dễ thay đổi.”** Dễ thay đổi ở đâu, cho nhu cầu nào, bằng chứng gì?

### 14.1. Một số tín hiệu định tính

- Developers có thể xác định tương đối nhanh phần code chịu trách nhiệm cho một quy tắc.
- Thay đổi nghiệp vụ nhỏ ít khi buộc sửa nhiều module không liên quan.
- Các quyết định quan trọng có lý do và đường xem lại.
- Phần phụ thuộc đối tác được cô lập đủ để kiểm thử và thay đổi.
- Phân quyền, dữ liệu, validation và error handling không bị rải rác khó kiểm soát.
- Hệ thống có thể sửa, tích hợp và triển khai với rủi ro hợp lý.

### 14.2. Một số phép đo có thể dùng

| Tín hiệu | Câu hỏi được hỗ trợ | Cảnh báo diễn giải |
|---|---|---|
| **Change lead/cycle time** | Thay đổi thông thường mất bao lâu tới khi đạt Done? | Phụ thuộc kích thước, loại việc, môi trường, đội |
| **Lỗi hồi quy sau thay đổi** | Kiến trúc và kiểm thử có bảo vệ hành vi cũ không? | Cần xem mức nghiêm trọng, số thay đổi và cách phát hiện |
| **Số vùng mã bị ảnh hưởng khi thay đổi một quy tắc** | Có phụ thuộc lan rộng bất hợp lý không? | Một thay đổi lớn hợp lệ vẫn có thể đụng nhiều module |
| **Thời gian phát hiện/sửa lỗi tích hợp** | CI và ranh giới có cho phản hồi sớm không? | Không chỉ đo số lỗi, vì phát hiện sớm có thể tăng số lỗi được ghi nhận |
| **Thời gian và sự cố khi migration** | Dữ liệu có thể thay đổi an toàn không? | Gắn với độ lớn và tính bất khả nghịch của dữ liệu |
| **Latency/error rate của luồng trọng yếu** | Thiết kế có đáp ứng chất lượng sử dụng không? | Cần ngưỡng theo nhu cầu thực, không dùng chuẩn tưởng tượng |
| **Work item age/WIP** | Công việc thiết kế hoặc refactor có bị kẹt không? | Không tự chứng minh cấu trúc tốt hay xấu |

Không có chỉ số đơn lẻ nào đo được “độ tốt của kiến trúc”. Các chỉ số chỉ có giá trị khi nối với **thay đổi cụ thể và quyết định cụ thể**.

### 14.3. Architecture fitness functions

Trong thực hành kiến trúc tiến hóa, **architecture fitness functions** là những phép kiểm chứng hoặc đánh giá giúp xem hệ thống còn đáp ứng đặc tính kiến trúc mong muốn không. Chúng có thể:

- **Tự động:** test bảo vệ ranh giới package/module; kiểm tra dependency rules; test contract; kiểm tra hiệu năng dưới tải đại diện.
- **Bán tự động:** kiểm tra migration, phục hồi hoặc cấu hình triển khai.
- **Thủ công theo chu kỳ:** rà soát rủi ro kiến trúc, khả năng bảo trì hoặc nghĩa vụ pháp lý chưa tự động hóa được.

Ví dụ:

~~~text
Thuoc tinh can bao ve:
  Logic cap quyen khong phu thuoc truc tiep UI controller.

Phep kiem chung:
  Test kien truc/kiem tra dependency + code review tai module lien quan.

Trigger xem lai:
  Khi them mot kenh moi hay thay doi mo hinh phan quyen.
~~~

Không phải dự án nhỏ phải xây một nền tảng đo fitness phức tạp. Chỉ thêm kiểm tra khi chúng **bảo vệ một quyết định đáng giá và có nguy cơ bị phá vỡ**.

### 14.4. Dùng thang thay đổi thay vì thang công nghệ

Không hỏi chỉ:

> “Chúng ta dùng microservice hay monolith, PostgreSQL hay NoSQL, synchronous hay event-driven?”

Hãy hỏi:

- Khi quy tắc nghiệp vụ đổi, **phạm vi ảnh hưởng** là gì?
- Khi lỗi xuất hiện, **phát hiện và khôi phục** mất bao lâu?
- Khi dữ liệu cần di trú, **có thể chuyển từng bước** không?
- Khi người dùng yêu cầu tính năng chưa dự đoán, **chi phí thêm** có hợp lý không?
- Từ lúc một giả thuyết xuất hiện tới lúc **nhận phản hồi người dùng** mất bao lâu?

Sự linh hoạt không nằm ở tên công nghệ; nó thể hiện qua **khả năng thay đổi sản phẩm đúng và an toàn trong bối cảnh thật**.

## 15. Những ranh giới của thiết kế tiến hóa

### 15.1. Phần cứng, chứng nhận và an toàn nghiêm ngặt

Trong thiết bị y tế, điều khiển công nghiệp hoặc các hệ thống có điều kiện chứng nhận đặc biệt, không thể dùng cách “phát hành rồi xem người dùng phản hồi” cho các nguy cơ an toàn chưa được xử lý.

Có thể vẫn phát triển tăng dần bằng mô phỏng, nguyên mẫu, thử nghiệm có kiểm soát và bằng chứng từng giai đoạn, nhưng phải **đáp ứng điều kiện kiểm định** trước khi sử dụng trong bối cảnh tương ứng. Thiết kế trước có thể cần sâu hơn ở những phần khó đảo ngược hoặc có rủi ro lớn.

### 15.2. Hệ thống legacy khó thay đổi

Một hệ thống cũ không có test, dữ liệu ràng buộc chặt và deploy thủ công có chi phí refactor cao. “Cứ thay đổi nhỏ” là lời khuyên chưa đủ.

Cách tiếp cận có thể gồm:

1. Xây **characterization tests** hoặc kiểm chứng hành vi hiện có ở vùng cần sửa.
2. Tạo seam hoặc ranh giới để thay đổi từng phần mà không viết lại toàn bộ.
3. Đặt điểm quan sát lỗi/dữ liệu để biết thay đổi có gây hồi quy không.
4. Chọn lát cắt có giá trị để tập trung cải tiến.
5. Di trú theo giai đoạn khi có phụ thuộc nhiều consumer.

Không nhất thiết phải hiểu hoặc viết lại mọi góc của hệ thống trước khi tạo giá trị, nhưng **không thể bỏ qua những chỗ không an toàn chỉ bằng cách gọi đó là legacy**.

### 15.3. API công khai và hợp đồng đối tác

Một API đã có khách hàng bên ngoài sử dụng khó thay đổi tự do như hàm private. Cần nghĩ sớm về:

- Versioning và tương thích ngược.
- Ngữ nghĩa trường dữ liệu, mã lỗi và định danh.
- Quy tắc xác thực, phân quyền và giới hạn sử dụng.
- Kế hoạch thông báo, chuyển consumer và loại phiên bản cũ.

Thiết kế API “đủ dùng” không có nghĩa thêm mọi tham số dự đoán trước; nó có nghĩa **hợp đồng hiện tại rõ, có kiểm chứng và có đường tiến hóa được quản lý**.

### 15.4. Hệ thống phân tán và nhất quán dữ liệu

Thêm message queue hoặc tách service có thể giải quyết một số yêu cầu, nhưng cũng tạo:

- Xử lý sự kiện lặp, sai thứ tự hoặc thất lạc.
- Retry và idempotency.
- Quan sát xuyên service.
- Quản lý bí mật, quyền và mạng.
- Migration đồng bộ dữ liệu.
- Khả năng rollback khi dữ liệu đã thay đổi.

Không nên chọn phân tán “để dễ mở rộng sau này” nếu chưa có lý do và năng lực vận hành. Ngược lại, nếu một sản phẩm đã có ràng buộc phân tán xác nhận, cần thiết kế các trường hợp lỗi đó ngay; không thể trì hoãn bằng YAGNI.

### 15.5. Deadline cố định, dữ liệu chưa đủ

Khi có mốc giao không thể dời, đội cần xác định **phạm vi tối thiểu đáp ứng nghĩa vụ và chất lượng**, chọn quyết định kiến trúc theo rủi ro đã xác nhận, thử sớm phụ thuộc và công khai những điều chưa chắc.

Không một nguyên tắc “thiết kế tối giản” nào cho phép hứa cả phạm vi lớn, thời gian ngắn và chất lượng không thay đổi khi dữ liệu cho thấy không khả thi. Quyết định đánh đổi cần đúng thẩm quyền sản phẩm, hợp đồng và an toàn.

### 15.6. Đội thiếu năng lực kiểm thử hoặc CI

Nếu không có regression tests đáng tin, mỗi refactor có nguy cơ lớn và làm chậm toàn hệ thống. Việc nâng năng lực kiểm thử/CI có thể trở thành **khoản đầu tư mở đường cho thiết kế tiến hóa**, chứ không phải chờ “đủ thời gian” mới làm.

Nhưng không nên theo đuổi 100% coverage hay một stack test đắt chỉ để đạt mục tiêu bề mặt; hãy ưu tiên **luồng giá trị và rủi ro quan trọng**.

## 16. Quy trình tám bước chọn thiết kế đủ dùng

Một quy trình thực dụng cho PBI hoặc quyết định kiến trúc quan trọng:

### Bước 1 — Gắn quyết định với mục tiêu người dùng

Viết một câu:

> “Học viên muốn lưu khóa X để quay lại sau khi đăng nhập.”

Hỏi bằng chứng nào cho thấy đó là nhu cầu, độ ưu tiên so với các vấn đề khác và cách sẽ kiểm tra outcome.

### Bước 2 — Liệt kê các điều kiện phải đúng

Xác định hành vi, AC, điều kiện DoD, bảo mật, dữ liệu, hiệu năng, khả năng truy cập, vận hành và quy định áp dụng. Phân biệt những điều **bắt buộc bây giờ** với biến thể tương lai chưa xác nhận.

### Bước 3 — Phân loại bất định và chi phí đảo ngược

Cho mỗi quyết định chính, hỏi:

| Câu hỏi | Ghi ngắn |
|---|---|
| Chúng ta biết chắc gì? | Yêu cầu, dữ liệu tải, hợp đồng, ràng buộc |
| Chưa biết gì? | Nhu cầu nhiều danh sách, đối tác mới, quy mô |
| Nếu sai thì sao? | Thay code nhỏ, migrate dữ liệu, ngừng dịch vụ, rủi ro an toàn |
| Khi nào sẽ biết hơn? | Sau prototype, test tích hợp, phát hành thử, quyết định hợp đồng |
| Có đường thoát nào? | Interface/seam cần thiết, tests, expand–contract, feature flag |

### Bước 4 — So sánh hai hoặc ba phương án thực tế

Không so một giải pháp đơn giản với một kiến trúc lý tưởng không giới hạn thời gian. Hãy so những phương án đội **có thể xây và vận hành**:

- Mức công sức hiện tại.
- Chi phí vận hành, kiểm thử và triển khai.
- Rủi ro đúng/sai và tác động dữ liệu.
- Chi phí thay đổi khi có nhu cầu mới.
- Thời gian đến phản hồi người dùng.
- Khả năng quan sát và khôi phục.

### Bước 5 — Giảm bất định đắt trước khi cam kết

Nếu quyết định khó đảo ngược và chưa chắc, thử spike, test contract, prototype hoặc đo tải. Chỉ dùng sản phẩm thật hoặc dữ liệu thật trong điều kiện an toàn/được cho phép.

### Bước 6 — Chọn lát cắt nhỏ và giữ đường kiểm chứng

Thiết kế phần nhỏ nhất có ý nghĩa **đạt chất lượng áp dụng**, tạo test bảo vệ, tích hợp liên tục và phân chia trách nhiệm rõ. Nếu một lớp abstraction không giúp giải quyết ranh giới hoặc rủi ro hiện có, cân nhắc bỏ nó.

### Bước 7 — Ghi quyết định và trigger xem lại

Với thay đổi đáng kể, ghi ngắn:

- Vì sao chọn.
- Giả định nào còn có thể sai.
- Phương án đã cân nhắc.
- Ngưỡng hoặc sự kiện khiến quyết định cần xem lại.
- Điều kiện vận hành/di trú nếu thay sau.

### Bước 8 — Kiểm tra qua Increment và dữ liệu thực

Sau khi triển khai và có phản hồi:

- Hành vi/AC đạt chưa?
- DoD và chất lượng được giữ chưa?
- Người dùng có đạt kết quả mong muốn không?
- Cycle time và lỗi liên quan thay đổi có ra sao?
- Cần refactor hay mở rộng ranh giới nào dựa trên bằng chứng?

Nếu câu trả lời khác giả định, **thay đổi có chủ đích**. Không bảo vệ thiết kế cũ chỉ vì đã đầu tư nhiều công sức; cũng không viết lại mọi thứ mỗi khi có một ý kiến mới.

### 16.1. Sơ đồ quyết định nhanh

~~~mermaid
flowchart TD
    A["Yêu cầu hay rủi ro vừa xuất hiện"] --> B{"Có ràng buộc bắt buộc?"}
    B -->|"Có"| C["Thiết kế + kiểm chứng ràng buộc trước khi dùng"]
    B -->|"Không"| D{"Quyết định khó đảo ngược?"}
    D -->|"Không"| E["Chọn đơn giản, kiểm thử và học"]
    D -->|"Có"| F{"Thông tin đã đủ chắc?"}
    F -->|"Có"| G["Thiết kế vừa sâu theo rủi ro, ghi ADR"]
    F -->|"Chưa"| H["Spike/đo/prototype, giữ phương án mở"]
    C --> I["Lát cắt có chất lượng + bằng chứng"]
    E --> I
    G --> I
    H --> I
    I --> J["Theo dõi và xem lại khi có dữ liệu mới"]
~~~

Không thể ép mọi quyết định kỹ thuật vào một sơ đồ nhị phân. Sơ đồ chỉ nhắc **phải có lý do trước khi thiết kế quá sâu hoặc quá ít**.

## 17. Những ngộ nhận và phản mẫu

### Ngộ nhận 1: “Agile không cần thiết kế trước”

**Vấn đề:** bỏ nghiên cứu ranh giới dữ liệu, quyền và phụ thuộc trước khi viết code.

**Điều chỉnh:** thiết kế trước **đủ cho rủi ro và nghĩa vụ đã biết**, rồi tiến hóa khi có dữ liệu mới.

### Ngộ nhận 2: “YAGNI nghĩa là không viết test hoặc không cần clean code”

**Vấn đề:** nhầm tính năng chưa chắc cần với điều kiện để sửa và phát hành an toàn.

**Điều chỉnh:** không xây chức năng phỏng đoán; vẫn giữ chất lượng, test và thiết kế rõ cho yêu cầu thật.

### Ngộ nhận 3: “Thiết kế đơn giản nhất là ít dòng code nhất”

**Vấn đề:** dồn nhiều quy tắc vào một controller, bỏ xử lý lỗi hoặc phân quyền.

**Điều chỉnh:** đánh giá mức đơn giản bằng **khả năng hiểu, tính đúng đắn, sự phù hợp và chi phí thay đổi**, không chỉ số lớp/hàm.

### Ngộ nhận 4: “Để tránh làm lại, phải xây khả năng mở rộng toàn diện ngay”

**Vấn đề:** xây mọi abstraction, microservice, queue, cache khi chưa có nhu cầu xác thực.

**Điều chỉnh:** phân loại rủi ro theo tác động và khả năng đảo ngược; đầu tư ở nơi đổi sau thật sự đắt.

### Ngộ nhận 5: “Nếu yêu cầu thay đổi, thiết kế ban đầu chắc chắn sai”

**Vấn đề:** đánh đồng học từ người dùng với thất bại của thiết kế.

**Điều chỉnh:** so sánh quyết định với thông tin đã có khi ra quyết định; kiểm tra đường tiến hóa và hậu quả thực, không phán xét bằng hiểu biết có được sau này.

### Ngộ nhận 6: “Mọi thay đổi đều có thể giải quyết bằng refactoring nhỏ”

**Vấn đề:** xem nhẹ migration dữ liệu, API công khai, bên thứ ba và sự cố vận hành.

**Điều chỉnh:** phân biệt refactor nội bộ với thay đổi kiến trúc/di trú; lập kế hoạch tương thích, theo dõi và khôi phục khi cần.

### Ngộ nhận 7: “Có nhiều interface thì hệ thống càng linh hoạt”

**Vấn đề:** tạo nhiều tầng abstraction khi chưa có biến thể thật và không có ranh giới cần bảo vệ.

**Điều chỉnh:** đặt abstraction khi có chức năng, phụ thuộc hoặc thay đổi được quan sát; giữ cấu trúc dễ hiểu.

### Ngộ nhận 8: “Khi performance kém, phải tách microservice”

**Vấn đề:** chọn kiến trúc phân tán trước khi tìm bottleneck.

**Điều chỉnh:** đo tải/latency, xem truy vấn, chỉ mục, xử lý đồng bộ và tài nguyên trước; mở rộng theo bằng chứng.

### Ngộ nhận 9: “Spike chứng minh production đã sẵn sàng”

**Vấn đề:** demo sandbox hoặc mock được dùng thay bằng chứng tích hợp, bảo mật và vận hành.

**Điều chỉnh:** công bố phạm vi và điều chưa được kiểm chứng; chỉ gọi Done khi đạt DoD tương ứng.

### Ngộ nhận 10: “Nợ kỹ thuật là mọi code không theo phong cách mình thích”

**Vấn đề:** biến sở thích kỹ thuật thành lý do chiếm ưu tiên backlog.

**Điều chỉnh:** nêu ảnh hưởng thực tới khả năng thay đổi, rủi ro, chất lượng hoặc vận hành; giải thích lựa chọn bằng chi phí và giá trị.

### Ngộ nhận 11: “Nếu còn deadline, cứ cắt quality”

**Vấn đề:** giảm kiểm thử, bảo mật hoặc điều kiện dữ liệu để giữ ngày.

**Điều chỉnh:** thương lượng phạm vi, chia lát cắt, làm rõ ràng buộc và mốc; không gọi chưa đạt chuẩn là Done.

### Ngộ nhận 12: “Số story point tăng chứng minh kiến trúc tốt hơn”

**Vấn đề:** story point phụ thuộc cách ước lượng; có thể đổi mà không tăng giá trị.

**Điều chỉnh:** xem thời gian đến Increment đạt DoD, lỗi hồi quy, chi phí sửa, phản hồi và outcome.

### Ngộ nhận 13: “Schema có thể đổi một lần là xong”

**Vấn đề:** bỏ qua consumer cũ, dữ liệu tồn tại, migration/backfill và rollback.

**Điều chỉnh:** dùng expand–migrate–contract khi phù hợp, kiểm tra tương thích và dữ liệu trước khi loại bỏ phần cũ.

### Ngộ nhận 14: “Khi design chưa đủ hoàn hảo, chưa thể giao gì”

**Vấn đề:** trì hoãn mọi phản hồi vì đợi kiến trúc tương lai hoàn chỉnh.

**Điều chỉnh:** tìm lát cắt nhỏ đúng, an toàn và có thể kiểm chứng để giao sớm; dùng thực tế điều hướng mở rộng.

### Ngộ nhận 15: “Refactoring là một dự án dọn dẹp tách khỏi giá trị”

**Vấn đề:** chỉ refactor cuối năm hoặc ngược lại tổ chức các đợt viết lại khổng lồ không rõ tác dụng.

**Điều chỉnh:** cải thiện cấu trúc khi có thay đổi liên quan và test bảo vệ; với khoản đầu tư lớn, giải thích rủi ro/giá trị và đo kết quả.

### Ngộ nhận 16: “Đã có test nên mọi thay đổi đều an toàn”

**Vấn đề:** test chỉ bao phủ một số điều kiện, mock quá nhiều, bỏ qua dữ liệu/đua tranh/production.

**Điều chỉnh:** chọn test theo rủi ro, kiểm tra môi trường và các điều kiện vận hành; theo dõi sau triển khai.

### Ngộ nhận 17: “Thiết kế tiến hóa là đổi kiến trúc liên tục theo xu hướng”

**Vấn đề:** chạy theo công nghệ, gây migration tốn kém mà không có bằng chứng nhu cầu.

**Điều chỉnh:** chỉ thay khi một trở ngại hoặc cơ hội đã được xác nhận, nêu giả thuyết và mốc xem lại.

### Ngộ nhận 18: “Một lựa chọn được ưa chuộng trong công ty phải phù hợp mọi nhóm”

**Vấn đề:** sao chép microservice, event-driven hoặc framework của sản phẩm khác mà bỏ qua đội ngũ, tải và nghĩa vụ.

**Điều chỉnh:** so sánh theo bối cảnh thực và khả năng vận hành của nhóm; dùng chuẩn tổ chức khi có lý do/chính sách rõ, không vì phong trào.

## 18. Workshop: chọn thiết kế cho một yêu cầu có tương lai chưa chắc

Một workshop 75–90 phút có thể giúp Product Owner, Developers, tester và người phụ trách vận hành phân biệt **nhu cầu đã có bằng chứng** với **dự đoán kỹ thuật tương lai**. Đây là bài thực hành gợi ý, không phải sự kiện chính thức của Scrum hay XP.

### 18.1. Đề bài nhóm

Một nền tảng học trực tuyến chuẩn bị cho phép **học viên lưu nhiều khóa học muốn xem lại**. Đội có bốn Developers và một người thường phụ trách kiểm thử. Product Owner kỳ vọng sẽ mở rộng sang gợi ý AI, danh sách học nhóm và tích hợp ứng dụng di động trong năm sau, nhưng chưa có quyết định ngân sách hoặc dữ liệu xác nhận. Hiện tại nền tảng có một database quan hệ, hệ thống tài khoản và pipeline tích hợp cơ bản.

Một thành viên đề xuất **xây microservice riêng với event broker**. Một người khác đề xuất **dùng local storage rồi đổi sau**.

**Nhiệm vụ:** đưa ra lựa chọn cho lát cắt đầu, những điều cần kiểm chứng ngay, giả định được phép hoãn, cách đo và trigger để xem lại.

### 18.2. Vai trò và thời gian minh họa

| Phần | Thời lượng | Hoạt động | Kết quả |
|---|---:|---|---|
| **Mở vấn đề** | 10 phút | Product Owner mô tả người dùng, giá trị và điều chưa chắc | Một phát biểu mục tiêu, tách sự thật/giả thuyết |
| **Nhìn rủi ro** | 15 phút | Developers/tester nêu rủi ro quyền, dữ liệu, tính lặp, tích hợp và tương lai | Danh sách ràng buộc và mức đảo ngược |
| **So sánh phương án** | 20 phút | Thảo luận local storage, modular monolith/DB và service riêng | Bảng ưu/nhược và quyết định có lý do |
| **Chọn lát cắt** | 15 phút | Viết AC, DoD, cách kiểm tra và triển khai | Một Increment ứng viên có thể xác minh |
| **Kiểm tra kịch bản mới** | 10 phút | Người hướng dẫn đưa thông tin “cần thêm nhiều danh sách” | Phương án di trú, mức làm lại chấp nhận |
| **Kết luận** | 10–20 phút | Ghi ADR/decision note, đo lường và trigger | Quyết định và bằng chứng cần theo dõi |

### 18.3. Thẻ tình huống bất ngờ

**Thẻ A — Người dùng không quan tâm AI:** thử nghiệm cho thấy chức năng lưu và xem lại hữu ích, nhưng khả năng gợi ý AI không cải thiện hành trình. Nhóm nên thay đổi kế hoạch đầu tư hạ tầng thế nào?

**Thẻ B — Quy tắc phân quyền mới:** một người dùng báo có thể gọi API để lấy danh sách của tài khoản khác. Điều gì cần sửa trước khi release, và việc nào không được viện dẫn YAGNI để hoãn?

**Thẻ C — Cần nhiều danh sách:** dữ liệu cho thấy học viên muốn phân nhóm “Muốn học” và “Học sau”. Schema cũ có hàng trăm nghìn bản ghi, đang được API cũ sử dụng. Nhóm sẽ chuyển theo bước thế nào?

**Thẻ D — Tải cao đột ngột:** sau một chiến dịch, tỷ lệ lỗi và độ trễ tăng. Nhóm nên đo gì trước khi quyết định tách service?

**Thẻ E — Nhà cung cấp thay đổi:** một bên thứ ba đề xuất tích hợp danh sách yêu thích nhưng hợp đồng chưa ký. Quyết định kiến trúc nào nên hoãn và đâu là ranh giới có thể chuẩn bị với chi phí hợp lý?

### 18.4. Tiêu chí đánh giá bài làm

- Lựa chọn có **phục vụ user story và Product Goal** không?
- Có phân biệt **điều bắt buộc** với **tính năng dự đoán** không?
- Có nhận diện quyết định **khó đảo ngược** và đường migration không?
- Có thể **test và đạt DoD** cho lát cắt đầu không?
- Có bằng chứng, giới hạn, owner và trigger xem lại không?
- Khi đưa thông tin mới, nhóm có **thay đổi lập luận theo bằng chứng**, không bảo vệ phương án cũ bằng cảm tính không?

## 19. Mẫu ghi nhận quyết định thiết kế và rủi ro làm lại

### 19.1. Mẫu quyết định cho một PBI

~~~text
PBI / MUC TIEU:
  [Nguoi dung can lam duoc gi? Product Goal lien quan?]

BANG CHUNG HIEN TAI:
  [Du lieu su dung, nghia vu, test, dieu kien van hanh]

GIA THUYET CHUA CHUNG MINH:
  [Nhu cau tuong lai, tai, doi tac, kenh mo rong]

BAT BUOC TU NGAY DAU:
  [AC, DoD, an toan, du lieu, performance can thiet]

QUYET DINH KIEN TRUC:
  [Luu tru, ranh gioi, contract, phuong an tich hop]

PHUONG AN KHAC DA XEM:
  A:
  B:
  C:

CHI PHI HOM NAY:
  [Cong suc, test, ha tang, van hanh, thoi gian den phan hoi]

RUI RO LAM LAI SAU:
  [Dieu gi thay doi? Muc do tac dong? Kho dao nguoc?]

DUONG THAY DOI:
  [Test, seam/interface, feature flag, migrate, rollback/roll-forward]

BANG CHUNG KIEM CHUNG:
  [Test can chay, build/moi truong, phep do, ket qua nguoi dung]

GUARDRAILS:
  [Nhung dieu khong duoc danh doi]

TRIGGER XEM LAI:
  [Su kien, nguong, du lieu, nghia vu moi]

QUYEN QUYET DINH / NGUOI THAM GIA:
  [Ai phu trach ky thuat, uu tien va rui ro]

KET LUAN:
  [Chon phuong an, ly do va dieu kien con mo]
~~~

Mẫu không phải biểu mẫu chính thức trong Scrum, Kanban hay XP. Với một thay đổi nhỏ ít rủi ro, vài câu trao đổi có thể đủ; với schema, giao thức công khai hoặc bảo mật, cần ghi rõ để các bên không quên giả định.

### 19.2. Mẫu review định kỳ quyết định cũ

| Quyết định | Giả định lúc chọn | Tín hiệu hiện tại | Tiếp tục hay đổi? | Bước tiếp |
|---|---|---|---|---|
| Lưu yêu thích trong DB hiện tại | Chưa có nhu cầu nhiều danh sách, tải thấp | Người dùng yêu cầu nhóm danh sách, truy vấn vẫn ổn | Mở rộng schema có kiểm soát, chưa cần service riêng | Thiết kế expand–migrate–contract |
| Chưa dùng cache phân tán | Latency đáp ứng SLO hiện tại | Tải cao có lỗi truy vấn | Điều tra trước khi đổi kiến trúc | Đo plan truy vấn và tối ưu |
| Tách xác thực thanh toán khỏi cấp quyền | Có rủi ro callback lặp và đối tác ngoài | Integration tests phát hiện sai trạng thái | Giữ và hoàn thiện | Sửa tính nguyên tử, kiểm tra an toàn |
| Chưa xây AI recommendation | Chưa có bằng chứng giá trị | Thử nghiệm không cải thiện outcome | Tiếp tục hoãn | Ưu tiên luồng giúp người học vào bài |

### 19.3. Mẫu thuyết phục Product Owner bằng ngôn ngữ giá trị

Thay vì:

> “Chúng tôi cần refactor PaymentManager vì code không SOLID.”

Hãy nêu:

> “Mỗi lần thêm phương thức thanh toán, nhóm hiện phải sửa quy tắc cấp quyền tại ba nơi. Trong hai lần thay đổi gần nhất đã phát sinh lỗi hồi quy. Chúng tôi đề xuất gom quy tắc về một ranh giới có test bảo vệ trước khi thêm phương thức B, nhằm giảm nguy cơ cấp quyền sai và giúp giao những thay đổi tiếp theo an toàn hơn. Chúng tôi sẽ đo lỗi tích hợp, thời gian hoàn tất các PBI liên quan và tác động lên kế hoạch gần.”

Thông điệp cho thấy **đầu tư thiết kế nhằm giảm rủi ro và tăng khả năng giao giá trị**, không chỉ nhằm đạt một chuẩn phong cách mã.

## 20. Bài tập vận dụng

### Bài tập A — Nhận diện overengineering và underdesign

Đội cần tính năng lưu khóa học để học viên xem lại sau đăng nhập. Một kỹ sư đề xuất microservice độc lập cùng event broker; người khác đề xuất chỉ dùng local storage trong trình duyệt.

**Yêu cầu:** Nêu rủi ro của từng phương án và đề xuất thiết kế đủ dùng.

<details>
<summary>Gợi ý đáp án</summary>

Microservice và event broker có thể làm tăng hạ tầng, kiểm thử, vận hành khi chưa có nhu cầu về phân tán hoặc tích hợp ngoài. Local storage không đáp ứng mục tiêu xem lại theo tài khoản/thiết bị nếu đó là AC và có thể tạo hiểu nhầm hoặc rủi ro dữ liệu. Phương án đủ dùng có thể dùng DB hiện tại, khóa duy nhất theo user–course, API kiểm tra phân quyền, xử lý yêu cầu lặp và test đăng nhập lại/hai tài khoản. Vẫn có thể thay đổi nếu có bằng chứng mới về tải hoặc nhiều loại danh sách.

</details>

### Bài tập B — Áp dụng ma trận khả năng đảo ngược

Hãy phân loại bốn quyết định:

1. Vị trí nút “Lưu khóa” trên trang chi tiết.
2. Chọn ID dùng trong API công khai đã có ba đối tác.
3. Có dùng cache cho danh sách yêu thích khi tải hiện rất thấp.
4. Quy tắc cấp quyền học sau thanh toán đã được xác nhận.

**Yêu cầu:** Điều gì nên thử nhanh, điều gì cần thiết kế/kiểm chứng sâu hơn?

<details>
<summary>Gợi ý đáp án</summary>

(1) thường dễ đổi, có thể thử nhanh với người dùng. (2) khó đổi vì nhiều consumer nên cần contract, tương thích và migration ngay trong quyết định. (3) có thể hoãn cache cho tới khi có bằng chứng về độ trễ hoặc tải, nhưng giữ phép đo/ranh giới phù hợp. (4) là điều kiện nghiệp vụ và an toàn đã biết, cần thiết kế và test ngay; không dùng YAGNI để bỏ kiểm soát giao dịch.

</details>

### Bài tập C — Tính chi phí kỳ vọng một cách thận trọng

Hai lựa chọn cho khả năng hỗ trợ nhà cung cấp thứ hai:

| Phương án | Xây hôm nay | Mở rộng khi cần | Xác suất cần trong năm tới |
|---|---:|---:|---:|
| A — Làm gọn | 5 đơn vị | 9 đơn vị | 20% |
| B — Tổng quát sớm | 11 đơn vị | 2 đơn vị | 20% |

**Yêu cầu:** Tính chi phí kỳ vọng thô và nêu ba lý do khiến kết quả không phải đáp án cuối.

<details>
<summary>Gợi ý đáp án</summary>

E[A] = 5 + 0,2 × 9 = 6,8. E[B] = 11 + 0,2 × 2 = 11,4. Trong mô hình đơn giản, A thấp hơn. Nhưng xác suất có thể sai, chi phí có thể không bao gồm gián đoạn dữ liệu/hợp đồng, việc thêm đối tác có thể có mức độ khẩn khác và thời gian đến phản hồi người dùng cũng là chi phí cơ hội. Cần xem khả năng đảo ngược, guardrails và thông tin có thể thu sớm.

</details>

### Bài tập D — Refactoring hay thêm tính năng?

Một controller có bốn khối điều kiện giống nhau để kiểm tra quyền xem khóa học. Nhóm cần thêm một quy tắc quyền mới, nhưng mỗi lần sửa controller đều dễ tạo hồi quy.

**Yêu cầu:** Phân biệt phần refactoring và phần thay đổi hành vi; đề xuất cách kiểm chứng.

<details>
<summary>Gợi ý đáp án</summary>

Đưa các quy tắc đang lặp vào thành phần có trách nhiệm rõ, giữ hành vi cũ, là refactoring. Bổ sung quy tắc quyền mới là thay đổi hành vi. Nên bổ sung characterization/regression tests cho quy tắc hiện có, refactor từng bước và chạy CI; sau đó viết test cho quy tắc mới, integration tests phân quyền UI/API và kiểm tra tài khoản khác. Không đánh đồng code ít lặp hơn với bằng chứng đã an toàn.

</details>

### Bài tập E — Di trú schema theo bước

Ban đầu một học viên chỉ có một danh sách yêu thích. Giờ khách hàng muốn nhiều danh sách. Có ứng dụng di động phiên bản cũ vẫn đọc API hiện tại.

**Yêu cầu:** Phác thảo các bước expand–migrate–contract và rủi ro cần quản lý.

<details>
<summary>Gợi ý đáp án</summary>

Expand: thêm schema/API có thể hỗ trợ nhiều danh sách mà consumer cũ vẫn hoạt động. Migrate: backfill dữ liệu hiện tại vào danh sách mặc định, thay readers/writers từng bước, đối chiếu số liệu và quan sát lỗi. Contract: chỉ bỏ schema/API cũ khi client được chuyển hoặc có chính sách phiên bản/hết hỗ trợ rõ. Cần đánh giá dual-write, idempotency, tính nguyên tử, rollback/roll-forward, backup, thời gian backfill, quyền truy cập và người dùng đang chạy bản di động cũ.

</details>

### Bài tập F — Trình bày đầu tư kỹ thuật cho Product Owner

Developers muốn bổ sung integration tests và sửa module thanh toán trước khi thêm một phương thức mới. Product Owner nói: “Điều đó không tạo nút mới cho người dùng”.

**Yêu cầu:** Viết một giải thích ngắn gắn với giá trị, rủi ro và phép đo.

<details>
<summary>Gợi ý đáp án</summary>

Có thể giải thích: “Module hiện có nhiều nơi cấp quyền sau thanh toán; việc thêm phương thức có nguy cơ tạo giao dịch trùng hoặc cấp quyền sai. Chúng tôi muốn xây test tích hợp và gom quy tắc vào một thành phần để phát hiện lỗi trước khi phát hành, giảm sự cố và tốc độ sửa những biến thể kế tiếp. Chúng tôi sẽ theo dõi lỗi sau thay đổi, số item đạt DoD và thời gian kiểm chứng của PBI liên quan.” Product Owner cùng đội cân nhắc thứ tự và năng lực, không hạ bảo mật bắt buộc.

</details>

### Bài tập G — Chọn khi nào cần spike

Hệ thống phải tích hợp một API thanh toán chưa từng dùng, tài liệu không nói rõ callback đến muộn hoặc gửi lặp. Nhà cung cấp hứa rằng “mọi sự kiện luôn đúng thứ tự”.

**Yêu cầu:** Bạn có xây toàn bộ luồng ngay không? Thiết kế một spike và tiêu chí kết thúc.

<details>
<summary>Gợi ý đáp án</summary>

Không nên xây toàn bộ trên giả định chưa kiểm chứng nếu dữ liệu/giao dịch có rủi ro cao. Spike có thể thử sandbox với sự kiện thành công, thất bại, lặp, đến muộn, hết hạn và lỗi kết nối; kiểm tra cơ chế xác thực sự kiện, query trạng thái đáng tin và quyền truy cập. Kết quả là chứng cứ, các giới hạn chưa kiểm tra, lựa chọn idempotency và phạm vi triển khai kế tiếp. Mock/sandbox pass không đồng nghĩa production an toàn.

</details>

### Bài tập H — Không nhầm performance với kiến trúc thời thượng

Đội nhận phản ánh trang danh sách khóa yêu thích chậm khi có nhiều khóa. Một thành viên đề nghị chuyển sang microservices và dùng message queue.

**Yêu cầu:** Viết năm câu hỏi cần điều tra và hai cải tiến nhỏ có thể thử trước.

<details>
<summary>Gợi ý đáp án</summary>

Hỏi: ngưỡng latency đã thống nhất là gì, request nào chậm, kích thước tập kết quả, execution plan và chỉ mục ra sao, tỷ lệ đọc/ghi và mức lỗi thế nào, giới hạn môi trường/tải cao điểm nào có thật. Có thể thử phân trang, tối ưu truy vấn/indexing và đo tác dụng; kiểm tra cache sau khi hiểu nhu cầu nhất quán. Microservices chỉ nên cân nhắc khi có bằng chứng lợi ích vượt chi phí phân tán.

</details>

### Bài tập I — Kết hợp thiết kế tiến hóa với Scrum/Kanban/XP

Scrum Team chọn sáu PBI trong Sprint, Development WIP limit = 2, sử dụng TDD và CI. Giữa Sprint, phát hiện kiến trúc hiện tại khiến xử lý phân quyền rất khó và một PBI không thể đạt DoD như dự kiến.

**Yêu cầu:** Những hành động nào phù hợp Scrum, Kanban và XP? Có thể chuyển item Done rồi sửa sau không?

<details>
<summary>Gợi ý đáp án</summary>

Developers kiểm tra ảnh hưởng tới Sprint Goal, điều chỉnh Sprint Backlog và trao đổi với Product Owner về phạm vi trong giới hạn Scrum; không hạ DoD. Dùng giới hạn WIP để tránh mở thêm việc trong lúc sửa điểm nghẽn, theo dõi item bị blocked. Dùng test, refactoring/CI theo XP để cô lập và sửa quy tắc quyền. Nếu PBI chưa đạt DoD thì chưa là phần của Increment Done; các bên cần cập nhật dự báo trung thực.

</details>

### Bài tập J — Phân tích một quyết định đáng tiếc mà không dùng “biết trước”

Sáu tháng trước nhóm chọn một database vì người dùng ít, không có yêu cầu dữ liệu phân tán và có test tốt. Hiện nay tải tăng mạnh, đội phải đầu tư cache hoặc tách phần đọc dữ liệu. Một người kết luận “Thiết kế ban đầu sai vì không dự đoán được”.

**Yêu cầu:** Bạn đánh giá quyết định ban đầu thế nào cho công bằng và hữu ích?

<details>
<summary>Gợi ý đáp án</summary>

Hãy đánh giá với thông tin **đã có khi quyết định được đưa ra**: nhu cầu, tải, ràng buộc, chi phí phân tán, khả năng di trú và bằng chứng. Nếu phương án ban đầu đáp ứng đầy đủ chất lượng và có đường mở rộng hợp lý, việc phải cải tiến khi tăng trưởng có thể là thiết kế tiến hóa thành công, không phải sai. Nếu nhóm bỏ qua các rủi ro đã biết, làm mất dữ liệu hoặc tạo phụ thuộc khó đảo không cần thiết, có lý do cải tiến cách ra quyết định. Cần dùng dữ liệu hiện tại để chọn bước tiếp thay vì trách móc bằng hindsight.

</details>

### Bài tập K — YAGNI trước nghĩa vụ an toàn

Một nhóm phát triển tính năng cấp quyền học sau thanh toán. Người quản lý đề nghị “để idempotency và kiểm tra phân quyền Sprint sau vì chưa có khách hàng lớn”.

**Yêu cầu:** Tại sao đây không phải áp dụng YAGNI đúng? Có thể giảm phạm vi bằng cách nào?

<details>
<summary>Gợi ý đáp án</summary>

Idempotency và phân quyền có thể là điều kiện tính đúng đắn/an toàn của luồng thanh toán hiện tại, không phải tính năng chưa cần. Bỏ chúng tạo rủi ro trùng giao dịch/cấp quyền hoặc lộ dữ liệu và có thể vi phạm DoD. Đội có thể chỉ triển khai một phương thức được hỗ trợ, phạm vi release nhỏ và hoãn khuyến mãi/báo cáo, nhưng vẫn kiểm tra các trạng thái lỗi bắt buộc và điều kiện an toàn cho lát cắt đã chọn.

</details>

## 21. Checklist tự đánh giá thiết kế đủ dùng và nguy cơ làm lại

Hãy trả lời bằng **một quyết định thiết kế gần đây**, không chỉ bằng khẩu hiệu:

1. Người dùng đang cần đạt điều gì và có bằng chứng nào cho nhu cầu đó?
2. Hạng mục có phạm vi đủ nhỏ để tạo Increment có thể kiểm chứng không?
3. Những ràng buộc về bảo mật, dữ liệu, an toàn, accessibility và vận hành đã rõ chưa?
4. Có đang xây một khả năng tương lai chỉ vì “sẽ có lúc cần” mà chưa có dữ liệu không?
5. Có bỏ một điều kiện cần cho nhu cầu hiện tại để hoàn tất nhanh không?
6. Các quyết định chính có được phân loại theo **độ bất định** và **chi phí đảo ngược** không?
7. Nếu quyết định sai, phải sửa bao nhiêu module, dữ liệu, API, đối tác và người dùng?
8. Có thể thu thông tin mới bằng spike, prototype hoặc thử nghiệm nhỏ trước khi cam kết lớn không?
9. Có đường thay đổi rõ nếu một giả định quan trọng bị bác bỏ không?
10. Ranh giới thành phần có phản ánh trách nhiệm thật hay chỉ là thêm lớp cho đủ “kiến trúc”?
11. Các abstraction đã có ít nhất một lý do kỹ thuật hoặc biến thể thực đáng giá không?
12. Có kiểm thử hồi quy đủ tin để refactor mà không phá hành vi cũ không?
13. CI có giúp phát hiện lỗi tích hợp sớm, hay nhiều nhánh/chưa chạy test bị dồn cuối?
14. Acceptance criteria có kiểm chứng các trường hợp thành công, lỗi, lặp và phân quyền khi áp dụng không?
15. Increment có đáp ứng Definition of Done và nghĩa vụ chất lượng trước khi tính Done không?
16. Các quyết định dữ liệu có tính tới phiên bản cũ, migration, backup, rollback hoặc roll-forward không?
17. Những quyết định khó đảo ngược có ADR hoặc ghi nhận lý do/điều kiện xem lại không?
18. Những khoản nợ kỹ thuật lớn có tác động/rủi ro cụ thể thay vì chỉ là sở thích mã không?
19. Thời gian sửa, lỗi hồi quy, cycle time và work item age có được quan sát theo bối cảnh không?
20. Thiết kế hiện tại có đáp ứng mục tiêu hiệu năng thật, hay đang tối ưu tải tưởng tượng?
21. Khi tải vượt ngưỡng, nhóm có kế hoạch đo bottleneck trước khi đổi kiến trúc không?
22. Feature flags và các thay đổi tạm có owner, trigger dọn và cách kiểm chứng không?
23. Có cơ chế để Product Owner và Developers cân nhắc đầu tư kỹ thuật theo giá trị/rủi ro không?
24. Các lựa chọn có xem **thời gian đến phản hồi người dùng** như một chi phí cơ hội không?
25. Đội có phân biệt prototype/spike với tính năng production đạt chất lượng không?
26. Khi thiết kế cũ không còn phù hợp, nhóm có sẵn sàng đổi theo bằng chứng mà không chỉ trích bằng hindsight không?
27. Có người có thẩm quyền hỗ trợ khi quyết định liên quan hợp đồng, hạ tầng hoặc dữ liệu ngoài đội không?
28. Đầu tư vào thiết kế có tạo **năng lực thay đổi thật** hay chỉ thêm tài liệu và tầng trừu tượng?

Nếu nhiều câu trả lời chưa rõ, đừng lập tức chọn giữa “viết lại toàn bộ” và “không làm gì”. Hãy chọn **một luồng thay đổi gây tốn kém hoặc rủi ro nhất**, làm rõ nguyên nhân, bổ sung test/bằng chứng và thử một thay đổi nhỏ có thể đánh giá được.

## 22. Ghi nhớ

- **Thiết kế tiến hóa không có nghĩa bỏ thiết kế trước.** Nó có nghĩa thiết kế theo nhu cầu và rủi ro được hiểu hiện tại, học thêm từ Increment và thay đổi cấu trúc có chủ đích.
- **Thiết kế đủ dùng** phải đáp ứng hành vi, tính đúng đắn, chất lượng, khả năng truy cập, bảo mật và nghĩa vụ áp dụng. Nó không chỉ là giải pháp ít dòng code hoặc giao diện demo nhanh.
- **Overengineering** gây chi phí cho tương lai chưa chắc; **underdesign** khiến khả năng thay đổi và tính đúng đắn bị tổn hại. Sự cân bằng phụ thuộc xác suất, tác động và khả năng đảo ngược.
- **YAGNI** giúp hoãn chức năng không có bằng chứng cần thiết, **không** cho phép hoãn kiểm thử hoặc yêu cầu an toàn vốn đã có.
- **Những quyết định khó đảo ngược** — dữ liệu, giao thức, phân quyền, hợp đồng, nghĩa vụ — đáng được làm rõ sớm hơn những quyết định dễ sửa như vị trí UI.
- **Refactoring, TDD, BDD, kiểm thử tự động và CI** giúp xây bằng chứng để sửa cấu trúc an toàn. Không kỹ thuật nào tự biến migration lớn hoặc yêu cầu sai thành đơn giản.
- **Thử nghiệm có thời hạn** và quan sát sản phẩm giúp giảm bất định trước khi đầu tư một kiến trúc lớn. Prototype và spike phải được công bố đúng giới hạn.
- **Dữ liệu thật cần đường tiến hóa:** những thay đổi lớn có thể cần expand–migrate–contract, kiểm tra tương thích, tính nhất quán và phương án khôi phục.
- **Scrum, Kanban và XP bổ sung những cơ chế khác nhau:** mục tiêu/phản hồi/DoD, quản lý dòng công việc và kỹ thuật duy trì khả năng thay đổi.
- **Đánh giá quyết định theo bối cảnh lúc ra quyết định**, không dùng thông tin xuất hiện sáu tháng sau để kết luận mọi lựa chọn đơn giản trước đây đều sai.
- **Mục tiêu cuối không phải kiến trúc hiện đại nhất.** Mục tiêu là phần mềm có giá trị, đáng tin và có thể tiếp tục được cải tiến với chi phí/rủi ro hợp lý.

Khi chuẩn bị thiết kế một khả năng mới, hãy hỏi:

> **“Với bằng chứng hiện tại, điều đơn giản nhất vẫn đáp ứng đầy đủ chất lượng là gì? Nếu nhu cầu đổi, phần nào sẽ khó sửa và chúng ta có thể tạo đường thay đổi rẻ hơn ngay bây giờ không? Đâu là dấu hiệu thực khiến ta nên đầu tư sâu thêm?”**

Trả lời ba câu hỏi ấy một cách trung thực là bước quan trọng để **cân bằng thiết kế đủ dùng với rủi ro phải làm lại** trong phát triển phần mềm thích ứng.

## Tài liệu tham khảo định hướng

- [Manifesto for Agile Software Development](https://agilemanifesto.org/): giá trị về phần mềm hoạt động, hợp tác với khách hàng và phản hồi thay đổi.
- [Principles behind the Agile Manifesto](https://agilemanifesto.org/principles.html): chất lượng kỹ thuật và thiết kế tốt tăng sự linh hoạt; phát triển bền vững, giao sản phẩm và cải tiến thường xuyên.
- **Martin Fowler — _Refactoring: Improving the Design of Existing Code_ (ấn bản thứ hai)**: khái niệm refactoring, kỹ thuật cải thiện thiết kế mà giữ hành vi.
- [Martin Fowler — Refactoring](https://refactoring.com/): tài liệu về refactoring và thực hành cải thiện cấu trúc mã.
- **Kent Beck & Cynthia Andres — _Extreme Programming Explained: Embrace Change_ (ấn bản thứ hai)**: YAGNI, simple design, TDD, refactoring, small releases và phản hồi kỹ thuật/nghiệp vụ.
- **Pramod Sadalage & Martin Fowler — _Refactoring Databases: Evolutionary Database Design_**: khái niệm tiến hóa schema, migration từng bước và quản lý tính tương thích.
- [The Scrum Guide (2020)](https://scrumguides.org/scrum-guide.html): Product Goal, Sprint Goal, Increment, Definition of Done và vòng kiểm tra/thích ứng trong Scrum.
- [The Kanban Guide](https://kanbanguides.org/the-kanban-guide/): Definition of Workflow, WIP, throughput, cycle time và work item age cho năng lực dòng công việc.
- [Cucumber — Gherkin Reference](https://cucumber.io/docs/gherkin/reference/): ví dụ hành vi Given–When–Then để làm rõ điều kiện chấp nhận.
- [DORA](https://dora.dev/): nghiên cứu và thực hành về khả năng giao phần mềm và vận hành, hữu ích khi đánh giá vòng phản hồi và độ tin cậy.
- **Neal Ford, Rebecca Parsons & Patrick Kua — _Building Evolutionary Architectures_**: khái niệm kiến trúc tiến hóa và fitness functions.
