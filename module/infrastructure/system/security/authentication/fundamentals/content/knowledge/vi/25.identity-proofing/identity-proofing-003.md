# Kiểm tra giấy tờ — Xác minh tài liệu định danh trong quy trình identity proofing

**Kiểm tra giấy tờ (document verification)** là quá trình đánh giá một tài liệu định danh có hợp lệ, còn giá trị và có dấu hiệu bị sửa đổi hoặc làm giả hay không, sau đó xác định tài liệu có đủ phù hợp để làm bằng chứng trong một quy trình **identity proofing** hay không. Tài liệu có thể là căn cước, hộ chiếu, giấy phép lái xe, thẻ cư trú hoặc giấy tờ khác được pháp luật và chính sách của dịch vụ chấp nhận.

Kiểm tra giấy tờ chỉ là một phần của identity proofing. Một hình ảnh giấy tờ trông thật không tự chứng minh người đang gửi hồ sơ là người được ghi trên giấy tờ; OCR đọc đúng họ tên cũng không chứng minh tài liệu là thật; chữ ký số của chip cũng không tự chứng minh giấy tờ chưa bị báo mất hoặc người trình diện là chủ thể hợp pháp. Quy trình tốt phải đánh giá riêng **tính xác thực của tài liệu**, **tính hợp lệ của dữ liệu**, **mối liên hệ giữa người trình diện và ảnh/chủ thể trên giấy tờ**, cùng **mức tin cậy cần thiết cho dịch vụ**.

Trong module SECURITY_AUTHENTICATION_FUNDAMENTALS, người học cần hiểu bằng chứng danh tính, ranh giới tin cậy và cách giảm gian lận trong các luồng đăng ký, khôi phục tài khoản hoặc cấp quyền truy cập. Bài này tập trung vào việc kiểm tra giấy tờ theo hướng có thể kiểm thử, bảo vệ dữ liệu cá nhân và không đánh đồng một kết quả kiểm tra tự động với kết luận chắc chắn về danh tính.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích vai trò và giới hạn của giấy tờ định danh trong identity proofing.
2. Phân biệt kiểm tra tính xác thực tài liệu, kiểm tra dữ liệu, kiểm tra hiệu lực và đối chiếu người trình diện.
3. Thiết kế quy trình thu nhận ảnh/chip, kiểm tra chất lượng, OCR, kiểm tra dấu hiệu giả mạo và xác minh nguồn phát hành.
4. Hiểu vai trò của MRZ, barcode, NFC chip, chữ ký số, ảnh chân dung và các đặc điểm bảo an.
5. Phân biệt face matching với face liveness/presentation attack detection (PAD).
6. Xây dựng quyết định pass/review/fail dựa trên bằng chứng, rủi ro và ngưỡng được kiểm định.
7. Bảo vệ ảnh giấy tờ, dữ liệu OCR, dữ liệu sinh trắc và audit trail theo nguyên tắc tối thiểu hóa.
8. Nhận diện các tấn công như giấy tờ giả, ảnh chụp màn hình, thay ảnh, replay, deepfake, document tampering và social engineering.
9. Viết tiêu chí kiểm thử cho cả luồng tự động, kiểm tra thủ công, ngoại lệ và khiếu nại.

## 2. Giấy tờ chứng minh điều gì?

Giấy tờ định danh là bằng chứng do một tổ chức phát hành, thường là cơ quan nhà nước hoặc tổ chức được ủy quyền. Tài liệu có thể chứa họ tên, ngày sinh, ảnh, số định danh, quốc tịch, ngày cấp, ngày hết hạn và các yếu tố bảo an.

Khi kiểm tra, cần tách ít nhất bốn câu hỏi:

| Câu hỏi | Điều cần xác minh | Ví dụ bằng chứng |
| --- | --- | --- |
| **Tài liệu có thật không?** | Tài liệu có được phát hành bởi nguồn được chấp nhận và có dấu hiệu giả/sửa không? | Đặc điểm bảo an, dữ liệu chip có chữ ký hợp lệ, kiểm tra với nguồn phát hành. |
| **Dữ liệu có nhất quán không?** | Các vùng thông tin có khớp nhau và đúng định dạng không? | OCR so với MRZ/barcode, ngày tháng, số tài liệu, checksum. |
| **Tài liệu còn hiệu lực không?** | Tài liệu còn trong thời hạn và chưa bị hủy/thu hồi theo nguồn có thẩm quyền không? | Ngày hết hạn, trạng thái từ issuer hoặc dịch vụ xác minh đáng tin. |
| **Người đang trình diện có liên hệ với tài liệu không?** | Người thực hiện quy trình có phải người trong ảnh hoặc chủ thể được ghi nhận không? | Face comparison, kiểm tra hiện diện/liveness, kiểm tra trực tiếp hoặc bằng chứng bổ sung. |

Không phải tài liệu nào cũng cung cấp được tất cả loại bằng chứng. Ví dụ, một giấy tờ không có chip NFC có thể vẫn là tài liệu hợp lệ nếu có phương thức kiểm tra khác. Chính sách phải nêu rõ loại giấy tờ nào được chấp nhận và bằng chứng nào được yêu cầu cho từng mức rủi ro.

### 2.1. Kiểm tra giấy tờ khác với xác minh danh tính toàn diện

Một kết quả document verification có thể kết luận rằng hình ảnh/tài liệu có vẻ hợp lệ theo những phép kiểm tra đã thực hiện. Identity proofing còn có thể cần xác minh người trình diện, đối chiếu thuộc tính với nguồn có thẩm quyền, kiểm tra tính duy nhất hoặc xác minh liên hệ với tài khoản/tổ chức.

Ví dụ: attacker sử dụng hộ chiếu thật bị đánh cắp. Kiểm tra chip và chữ ký có thể thành công vì tài liệu là thật. Nhưng người cầm hộ chiếu có thể không phải chủ thể hợp pháp. Vì vậy, kiểm tra tài liệu và kiểm tra người trình diện là hai lớp riêng.

## 3. Phân loại tài liệu và chính sách chấp nhận

Không nên dùng một quy tắc chung cho mọi loại giấy tờ. Mỗi loại có cấu trúc, cơ quan phát hành, tính năng bảo an, cách đọc và khả năng kiểm tra khác nhau.

| Loại tài liệu | Dữ liệu thường có | Cách kiểm tra có thể áp dụng | Lưu ý |
| --- | --- | --- | --- |
| Căn cước/thẻ định danh | Họ tên, ngày sinh, số định danh, ảnh, ngày cấp/hết hạn | Kiểm tra layout/đặc điểm bảo an, OCR, mã 2D, nguồn xác minh nếu có | Mẫu tài liệu thay đổi theo quốc gia và phiên bản. |
| Hộ chiếu | Trang dữ liệu, ảnh, MRZ; một số loại có chip điện tử | Kiểm tra MRZ, vùng ảnh, dữ liệu chip và chữ ký số nếu có | Chip điện tử không có trên mọi hộ chiếu hoặc mọi thế hệ. |
| Giấy phép lái xe | Thông tin cá nhân, ảnh, hạng/điều kiện lái xe, ngày hết hạn | OCR, barcode, mẫu bảo an và nguồn cấp phép nếu được phép | Không phải lúc nào cũng được chấp nhận làm bằng chứng cho mọi dịch vụ. |
| Thẻ cư trú/visa | Thông tin định danh và trạng thái cư trú/nhập cảnh | Kiểm tra định dạng, thời hạn, mã/ chip và nguồn có thẩm quyền | Quyền cư trú và danh tính là hai thuộc tính khác nhau. |
| Thẻ nhân viên/sinh viên | Tên, ảnh, mã tổ chức, đơn vị | Đối chiếu hệ thống tổ chức hoặc người quản lý phát hành | Chỉ chứng minh quan hệ trong phạm vi tổ chức nếu nguồn đáng tin. |
| Giấy tờ điện tử có chữ ký | Thuộc tính danh tính, chữ ký/chứng thư số | Xác minh chữ ký, chuỗi tin cậy, trạng thái chứng thư và issuer | Chữ ký hợp lệ không tự chứng minh nội dung đúng ngoài phạm vi issuer xác nhận. |

### 3.1. Chính sách chấp nhận phải được công bố

Trước khi thu thập, dịch vụ cần xác định:
- Những loại tài liệu và quốc gia phát hành nào được chấp nhận.
- Phiên bản tài liệu tối thiểu hoặc ngày cấp có liên quan.
- Tài liệu hết hạn có được chấp nhận trong trường hợp đặc biệt không.
- Có yêu cầu chip/NFC, đối chiếu ảnh hoặc nguồn xác minh độc lập không.
- Có chấp nhận giấy tờ tạm thời, giấy tờ số hoặc bản sao có chứng thực không.
- Trường hợp nào cần review thủ công hoặc bằng chứng thay thế.
- Cách xử lý tài liệu hư hỏng, tên không dấu, khác thứ tự tên hoặc dữ liệu không khớp do quy tắc địa phương.

Không tự suy ra chính sách pháp lý từ hình thức tài liệu. Yêu cầu pháp lý khác nhau theo quốc gia, ngành, mục đích và loại giao dịch; cần xác nhận với bộ phận pháp chế/tuân thủ và cơ quan có thẩm quyền trước khi triển khai.

## 4. Quy trình kiểm tra giấy tờ từ đầu đến cuối

Một quy trình thường gồm nhiều bước. Không nên đưa ra kết luận chỉ từ OCR hoặc một điểm số của nhà cung cấp.

~~~mermaid
flowchart TD
    A["Thông báo mục đích và thu thập tối thiểu"] --> B["Chọn loại tài liệu được chấp nhận"]
    B --> C["Thu nhận ảnh hoặc đọc chip"]
    C --> D["Kiểm tra chất lượng và tính đầy đủ"]
    D --> E{"Ảnh đủ chất lượng?"}
    E -->|Không| F["Yêu cầu chụp lại / phương thức thay thế"]
    F --> C
    E -->|Có| G["OCR và trích xuất thuộc tính"]
    G --> H["Kiểm tra cấu trúc, MRZ/barcode/chip"]
    H --> I["Kiểm tra dấu hiệu giả mạo và hiệu lực"]
    I --> J["Đối chiếu ảnh người trình diện nếu policy yêu cầu"]
    J --> K["Đánh giá rủi ro và nguồn bằng chứng"]
    K --> L{"Kết quả"}
    L -->|Đủ bằng chứng| M["Chấp nhận theo assurance policy"]
    L -->|Chưa rõ| N["Review thủ công / yêu cầu bằng chứng bổ sung"]
    L -->|Có dấu hiệu gian lận| O["Từ chối hoặc chuyển quy trình fraud"]
    M --> P["Lưu kết quả tối thiểu và audit"]
    N --> P
    O --> P
~~~

### 4.1. Bước 1 — Thông báo và thu thập có mục đích

Trước khi yêu cầu người dùng chụp giấy tờ, hãy giải thích:
- Vì sao cần kiểm tra giấy tờ và dịch vụ sẽ dùng kết quả cho việc gì.
- Loại giấy tờ nào được chấp nhận.
- Những trường dữ liệu nào sẽ được đọc.
- Có dùng nhà cung cấp xử lý bên ngoài hoặc kiểm tra sinh trắc hay không.
- Dữ liệu nào được lưu, thời gian lưu và cách yêu cầu hỗ trợ/xóa theo chính sách.
- Người dùng có phương thức thay thế nào nếu không thể dùng camera, NFC hoặc sinh trắc.

Không thu thập toàn bộ giấy tờ nếu chỉ cần xác minh một thuộc tính. Không yêu cầu chụp mặt sau nếu loại tài liệu và policy không cần. Nếu chỉ cần xác nhận tuổi hoặc quốc gia cư trú, cân nhắc giải pháp chỉ trả kết quả thuộc tính cần thiết thay vì lưu ảnh đầy đủ.

### 4.2. Bước 2 — Thu nhận ảnh hoặc dữ liệu chip

Khi chụp ảnh:
- Hướng dẫn đặt giấy tờ trên nền phù hợp, đủ sáng, tránh phản chiếu và không che góc.
- Chụp đủ bốn cạnh, không cắt mất vùng MRZ, barcode hoặc yếu tố bảo an.
- Tránh làm mờ, rung, méo phối cảnh và ảnh bị nén quá mức.
- Kiểm tra ảnh có phải ảnh trực tiếp từ luồng capture được yêu cầu hay là file không được phép.
- Nếu chấp nhận upload, xác định rõ loại file, kích thước, metadata và cách xử lý ảnh chỉnh sửa.

Capture SDK có thể giúp kiểm soát chất lượng và phát hiện một số bất thường, nhưng không phải bằng chứng độc lập rằng ảnh đến từ giấy tờ vật lý thật. Một ảnh chất lượng cao vẫn có thể là ảnh chụp lại màn hình hoặc tài liệu giả được in tinh vi.

Nếu đọc chip NFC:
- Yêu cầu người dùng đặt thiết bị đúng vị trí và giữ ổn định.
- Đọc dữ liệu theo quy trình và tiêu chuẩn phù hợp của tài liệu.
- Xác minh chữ ký/chứng thư của dữ liệu chip bằng trust anchor và danh sách issuer được chấp nhận.
- Kiểm tra dữ liệu chip có khớp với trang in và ảnh người trình diện hay không.
- Xử lý lỗi chip, thiết bị không hỗ trợ hoặc chứng thư không xác minh được theo nhánh riêng; không tự coi mọi lỗi đọc chip là gian lận.

## 5. Chất lượng ảnh và OCR

**OCR (Optical Character Recognition)** chuyển hình ảnh văn bản thành dữ liệu có cấu trúc, ví dụ họ tên, số tài liệu và ngày sinh. OCR giúp giảm nhập tay nhưng có thể nhầm ký tự, đặc biệt khi ảnh mờ, chữ nhỏ, font đặc thù, dấu tiếng Việt hoặc tài liệu nhiều ngôn ngữ.

Ví dụ các ký tự dễ nhầm: O/0, I/1, B/8, S/5. Một kết quả OCR có độ tin cậy cao chỉ có nghĩa hệ thống tự tin về việc đọc ký tự; nó không chứng minh tài liệu thật hoặc người dùng là chủ thể.

### 5.1. Kiểm tra chất lượng trước OCR

Các tín hiệu có thể đánh giá:
- Độ phân giải và kích thước vùng tài liệu.
- Độ nét, độ tương phản, ánh sáng và phản chiếu.
- Góc nghiêng, phối cảnh và méo hình.
- Bốn cạnh tài liệu có xuất hiện đầy đủ không.
- Vùng ảnh chân dung, chữ, MRZ và barcode có bị che/cắt không.
- Dấu hiệu ghép ảnh, viền bất thường hoặc nén không đồng đều.

Chất lượng kém nên dẫn tới yêu cầu chụp lại hoặc phương thức khác, thay vì tự động kết luận người dùng gian lận. Cần giới hạn số lần chụp lại hợp lý để tránh tạo vòng lặp gây khó khăn cho người dùng có thiết bị/camera kém.

### 5.2. Đối chiếu nhiều vùng dữ liệu

Nếu tài liệu có nhiều vùng biểu diễn cùng thuộc tính, so sánh chúng:
- Tên/ngày sinh trên vùng in với OCR.
- Dữ liệu MRZ với vùng thông tin in.
- Barcode/QR với các thuộc tính được in, nếu định dạng được hiểu và xác minh.
- Dữ liệu chip NFC với trang dữ liệu và ảnh in.
- Ngày cấp/hết hạn và số tài liệu với cấu trúc hợp lệ của loại giấy tờ.

Không tự sửa dữ liệu OCR để khớp một cách âm thầm. Nếu có sai lệch, ghi nhận trường nào không khớp, mức độ chắc chắn và quy trình review. Các quy tắc chuẩn hóa tên, dấu, khoảng trắng và thứ tự họ tên phải được định nghĩa theo quốc gia/tài liệu.

## 6. MRZ, barcode và chip điện tử

### 6.1. MRZ (Machine Readable Zone)

MRZ là vùng ký tự máy đọc được trên một số hộ chiếu và giấy tờ du lịch. Nó có định dạng, vị trí và các trường được quy định. Một số trường có **check digit** để phát hiện lỗi nhập/đọc.

Check digit giúp kiểm tra tính nhất quán của dữ liệu theo thuật toán định dạng. Nó **không phải chữ ký mật mã** và không chứng minh giấy tờ thật. Attacker có thể tạo dữ liệu giả với check digit đúng. Vì vậy MRZ phải được dùng như một nguồn dữ liệu để so sánh, không phải bằng chứng xác thực duy nhất.

### 6.2. Barcode và QR code

Barcode/QR có thể chứa dữ liệu được in trên giấy tờ hoặc mã tham chiếu tới nguồn xác minh. Cần:
- Giải mã theo chuẩn của loại tài liệu, không tự đoán format.
- Kiểm tra checksum/chữ ký nếu định dạng hỗ trợ.
- Đối chiếu dữ liệu giải mã với vùng in.
- Nếu mã chỉ là URL hoặc ID tra cứu, chỉ truy cập endpoint issuer đã xác minh; không mở URL tùy ý từ mã QR.
- Không coi việc mã đọc được là bằng chứng tài liệu thật.

Mã 2D có thể bị sao chép từ tài liệu thật sang tài liệu giả. Tính xác thực phụ thuộc vào cơ chế chữ ký, trạng thái nguồn và cách gắn mã với tài liệu cụ thể.

### 6.3. Chip NFC và chữ ký số

Một số hộ chiếu/thẻ điện tử lưu dữ liệu trong chip có thể đọc không tiếp xúc. Quy trình kiểm tra có thể bao gồm:
- Đọc dữ liệu chip theo giao thức phù hợp.
- Xác minh chữ ký số trên các nhóm dữ liệu bằng chứng thư phát hành và trust anchor phù hợp.
- Kiểm tra dữ liệu chip nhất quán với trang dữ liệu in.
- Kiểm tra cơ chế chống sao chép/chứng minh chip nếu tài liệu và tiêu chuẩn hỗ trợ.

**Passive Authentication** xác minh chữ ký trên dữ liệu chip và giúp phát hiện dữ liệu bị thay đổi sau khi phát hành. Nó không tự chứng minh chip đang được đọc là chip gốc trong mọi trường hợp, không chứng minh người cầm hộ chiếu là chủ thể và không tự kiểm tra tài liệu đã bị báo mất/thu hồi. Các cơ chế như Active Authentication hoặc Chip Authentication có thể bổ sung bằng chứng sở hữu chip tùy loại tài liệu.

Không phải mọi tài liệu có chip đều triển khai cùng cơ chế. Chỉ chấp nhận kết quả theo tiêu chuẩn, trust store và quy trình được phê duyệt cho đúng loại tài liệu.

## 7. Kiểm tra tính xác thực và dấu hiệu giả mạo

Kiểm tra tài liệu có thể kết hợp đặc điểm vật lý, dữ liệu số và nguồn xác minh.

### 7.1. Đặc điểm vật lý

Tùy loại giấy tờ, có thể có:
- Hình chìm, nền in bảo an và hoa văn vi mô.
- Hình ảnh thay đổi theo góc nhìn, hologram hoặc OVD.
- Mực đổi màu, chi tiết phản quang hoặc UV.
- Chất liệu, độ dày, cấu trúc lớp và kỹ thuật in.
- Vị trí, font, khoảng cách và bố cục đặc trưng.
- Dấu, chữ ký hoặc đặc điểm phát hành theo mẫu.

Kiểm tra qua ảnh thường không thể đánh giá đầy đủ các đặc điểm vật lý cần ánh sáng/góc nhìn đặc biệt. Nếu policy đòi hỏi, có thể cần kiểm tra trực tiếp, thiết bị chuyên dụng hoặc nguồn xác minh độc lập. Không kết luận tài liệu giả chỉ vì camera không ghi lại được một hiệu ứng vật lý.

### 7.2. Dấu hiệu chỉnh sửa số

Hệ thống có thể tìm:
- Vùng ảnh hoặc văn bản có độ nét/nhiễu khác biệt bất thường.
- Font, baseline, khoảng cách hoặc màu nền không nhất quán.
- Viền ghép, bóng đổ và phối cảnh không khớp.
- Dấu hiệu ảnh bị cắt ghép, thay mặt hoặc chèn chữ.
- Metadata ảnh bất thường hoặc dấu hiệu tái mã hóa nhiều lần.
- Không khớp giữa trang in, MRZ, barcode và chip.

Các tín hiệu này có thể gây false positive do camera, ứng dụng nén ảnh, scan hoặc chất lượng bản gốc. Không dùng một heuristic đơn lẻ làm quyết định cuối cùng. Hệ thống phải lưu lý do và mức độ tin cậy để review.

### 7.3. Xác minh với nguồn phát hành

Nếu có nguồn chính thức hoặc dịch vụ xác minh đáng tin:
- Xác định endpoint/đối tác là nguồn được issuer hoặc cơ quan có thẩm quyền công nhận.
- Xác minh quyền truy cập, mục đích xử lý và căn cứ pháp lý.
- Gửi đúng thuộc tính tối thiểu cần tra cứu.
- Kiểm tra trạng thái hiệu lực/thu hồi theo khả năng nguồn cung cấp.
- Ghi thời điểm, nguồn và kết quả; xử lý khi dịch vụ ngoài không sẵn sàng.
- Không gửi dữ liệu giấy tờ tới website/đối tác bất kỳ chỉ vì họ quảng cáo có khả năng OCR hoặc verification.

Nguồn phát hành có thể không cung cấp API công khai hoặc dữ liệu trạng thái thời gian thực. Khi không thể kiểm tra trạng thái, kết quả phải ghi rõ giới hạn; không suy ra “chưa bị thu hồi” từ việc không có dữ liệu.

## 8. Đối chiếu ảnh và kiểm tra người trình diện

Sau khi đánh giá tài liệu, quy trình có thể cần xác định người đang thực hiện có tương ứng với ảnh chân dung trên giấy tờ hay không. Hai kỹ thuật thường gặp là **face matching** và **liveness/PAD**.

### 8.1. Face matching

Face matching so sánh hai ảnh khuôn mặt, thường là:
- Ảnh chân dung trên tài liệu (ảnh tham chiếu).
- Ảnh selfie/video được thu trong phiên hiện tại.

Hệ thống trả về điểm tương đồng. Điểm số không phải xác suất chắc chắn người đó là chủ thể; ngưỡng quyết định phụ thuộc mô hình, chất lượng ảnh, điều kiện chụp, tập dữ liệu kiểm định và mức rủi ro. Không tự đặt một ngưỡng chung cho mọi nhóm người dùng và mọi tài liệu.

Face matching là so sánh **một-một (1:1)** giữa người trình diện và ảnh trên tài liệu. Nó khác face identification 1:N, nơi hệ thống tìm một người trong kho ảnh. Không chuyển sang tìm kiếm 1:N nếu mục đích chỉ là đối chiếu tài liệu, vì rủi ro quyền riêng tư và tác động tới người dùng khác lớn hơn.

### 8.2. Liveness và Presentation Attack Detection (PAD)

Liveness/PAD đánh giá liệu đầu vào khuôn mặt có phải là một presentation attack như ảnh in, màn hình phát video, mặt nạ hoặc replay hay không. Phương pháp có thể gồm kiểm tra chuyển động, phản ứng theo challenge, phân tích ảnh/video hoặc cảm biến chuyên dụng.

Liveness không chứng minh danh tính. Một người thật có thể thực hiện liveness nhưng dùng giấy tờ của người khác. Ngược lại, một video deepfake có thể tìm cách đánh lừa hệ thống. Do đó phải đánh giá riêng:
- Tài liệu có thật và còn hiệu lực không?
- Khuôn mặt có khớp với ảnh tài liệu không?
- Đầu vào có dấu hiệu presentation attack không?
- Giao dịch có đúng ngữ cảnh và thiết bị không?

### 8.3. Ngưỡng và đánh giá sai số

Một hệ thống sinh trắc cần được đánh giá trên nhiều điều kiện và nhóm người dùng. Các chỉ số có thể gồm:
- False Match Rate (FMR): tỷ lệ hai người khác nhau bị hệ thống coi là khớp.
- False Non-Match Rate (FNMR): tỷ lệ cùng một người bị hệ thống coi là không khớp.
- PAD error rates: tỷ lệ presentation attack bị chấp nhận hoặc người thật bị từ chối, theo phương pháp đánh giá tương ứng.
- Tỷ lệ cần review thủ công và tỷ lệ người dùng hoàn thành quy trình.
- Chênh lệch hiệu năng theo thiết bị, ánh sáng, tuổi, màu da, khuyết tật và điều kiện sử dụng.

Không chỉ tối ưu một chỉ số trung bình. Ngưỡng phải dựa trên đánh giá rủi ro, kiểm định độc lập phù hợp, giám sát sau triển khai và quy trình khiếu nại/biện pháp thay thế. Người dùng không thể thực hiện selfie hoặc NFC cần có lối xử lý thay thế có mức bảo đảm tương ứng.

## 9. Quyết định: pass, review hay fail

Không nên buộc mọi trường hợp vào quyết định nhị phân khi bằng chứng có thể chưa đủ. Có thể thiết kế ba trạng thái:

| Trạng thái | Khi nào dùng | Hành động |
| --- | --- | --- |
| **PASS** | Tài liệu thuộc loại chấp nhận, kiểm tra bắt buộc đạt, dữ liệu nhất quán và mức tin cậy đạt policy | Tiếp tục bước proofing tiếp theo hoặc hoàn tất theo assurance policy. |
| **REVIEW** | Chất lượng chưa đủ, nguồn ngoài tạm lỗi, OCR không chắc chắn, có sai lệch cần giải thích hoặc điểm rủi ro ở vùng không chắc chắn | Chuyển người kiểm tra có đào tạo hoặc yêu cầu bằng chứng/phương thức khác. |
| **FAIL** | Có bằng chứng rõ tài liệu không hợp lệ, bị thu hồi, chữ ký sai, không thuộc loại chấp nhận hoặc có dấu hiệu gian lận được xác nhận | Từ chối theo policy, thông báo phù hợp và lưu audit tối thiểu. |

### 9.1. Không biến thiếu dữ liệu thành gian lận

Ví dụ:
- Camera không lấy nét: đây là lỗi chất lượng, không tự động là giấy tờ giả.
- NFC không đọc được: có thể do điện thoại/antenna hoặc chip hỏng; cần nhánh thay thế.
- OCR không đọc đúng tên có dấu: cần kiểm tra dữ liệu gốc và quy tắc ngôn ngữ.
- Dịch vụ issuer timeout: trạng thái là chưa xác minh được, không phải tự động hợp lệ hoặc gian lận.
- Face match dưới ngưỡng trong ánh sáng kém: có thể yêu cầu chụp lại hoặc review, tùy số lần và rủi ro.

### 9.2. Lý do quyết định phải có thể giải thích

Lưu mã lý do có cấu trúc, ví dụ:
- DOCUMENT_TYPE_UNSUPPORTED
- IMAGE_QUALITY_LOW
- OCR_FIELD_MISMATCH
- MRZ_CHECK_FAILED
- CHIP_SIGNATURE_INVALID
- DOCUMENT_EXPIRED
- ISSUER_STATUS_UNAVAILABLE
- FACE_MATCH_REVIEW
- PAD_SUSPECTED
- MANUAL_REVIEW_REQUIRED

Không nhất thiết hiển thị toàn bộ tín hiệu chống gian lận cho người dùng, vì có thể giúp attacker điều chỉnh giấy tờ giả. Nhưng thông báo cần đủ rõ để người dùng biết cách khắc phục lỗi chất lượng hoặc khiếu nại quyết định.

## 10. Kiểm tra thủ công và quản lý ngoại lệ

Review thủ công hữu ích khi tài liệu hiếm, mẫu mới, OCR bất thường hoặc có sai lệch cần chuyên gia xem xét. Tuy nhiên, người kiểm tra cũng có thể bị đánh lừa hoặc mắc thiên kiến.

Quy trình review cần:
- Người review được đào tạo về loại tài liệu và giới hạn công cụ.
- Hiển thị nguồn bằng chứng, kết quả tự động, vùng không chắc chắn và lý do chuyển review.
- Có checklist theo loại tài liệu, không dựa vào cảm giác “trông có vẻ thật”.
- Phân tách người xử lý và người phê duyệt đối với tài khoản/hành động rủi ro cao.
- Audit ai xem dữ liệu, thay đổi kết quả và lý do.
- Có quy trình khiếu nại và review lần hai.
- Không cho nhân viên yêu cầu người dùng gửi mật khẩu, OTP, private key hoặc recovery code.
- Hạn chế tải ảnh về máy cá nhân hoặc chia sẻ qua kênh không được quản lý.

Nếu reviewer không đủ bằng chứng, kết quả phải là pending/review hoặc yêu cầu phương thức khác, không ép kết luận pass/fail tùy tiện.

## 11. Các tấn công phổ biến và biện pháp phòng vệ

| Tấn công | Cách xảy ra | Kiểm soát |
| --- | --- | --- |
| **Giấy tờ giả hoàn toàn** | Tạo tài liệu với layout và dữ liệu giả | Kiểm tra mẫu/đặc điểm bảo an, chip/chữ ký hoặc nguồn issuer khi có; review rủi ro. |
| **Document tampering** | Thay tên, ngày sinh, ảnh hoặc số tài liệu trên giấy tờ thật | Đối chiếu nhiều vùng, dữ liệu chip, đặc điểm vật lý và nguồn phát hành. |
| **Ảnh chụp màn hình/in lại** | Trình diện ảnh hoặc bản sao trên màn hình | Capture guidance, kiểm tra phản chiếu/viền, PAD cho khuôn mặt, chip/NFC khi có. |
| **Replay capture** | Phát lại ảnh/video đã dùng trong phiên khác | Challenge phiên, nonce/timestamp, ràng buộc transaction, phát hiện trùng lặp và PAD. |
| **Stolen genuine document** | Dùng giấy tờ thật của người khác | Face matching, liveness/PAD, kiểm tra bổ sung và risk-based review. |
| **Deepfake/face swap** | Thay khuôn mặt trong selfie/video | PAD được kiểm định, capture integrity, kiểm tra thiết bị và phương thức khác khi rủi ro cao. |
| **MRZ/barcode copying** | Sao chép vùng mã từ giấy tờ thật | Không coi checksum/mã đọc được là bằng chứng duy nhất; xác minh chữ ký/chip/issuer. |
| **OCR manipulation** | Lợi dụng lỗi đọc ký tự hoặc thay dữ liệu đầu vào | Đối chiếu nhiều nguồn, kiểm tra thủ công khi bất nhất, không auto-correct âm thầm. |
| **Synthetic identity** | Kết hợp thuộc tính thật/giả để tạo hồ sơ khó phát hiện | Đối chiếu nguồn độc lập, kiểm tra tính nhất quán và uniqueness theo policy. |
| **Insider abuse** | Nhân viên xem, tải hoặc sửa kết quả trái phép | Least privilege, audit, phân tách nhiệm vụ, giám sát truy cập và hạn chế export. |
| **Vendor/API substitution** | Gửi ảnh tới dịch vụ giả hoặc endpoint không được phê duyệt | Ghim nhà cung cấp/endpoint, xác thực kết nối, đánh giá hợp đồng và xử lý dữ liệu. |

### 11.1. Ràng buộc capture với giao dịch

Nếu quy trình yêu cầu capture trực tiếp, server nên tạo transaction ID/challenge ngẫu nhiên, thời hạn ngắn và ràng buộc kết quả capture với đúng tài khoản/phiên. Không tin timestamp hoặc account ID do client tự khai. Khi nhận ảnh/video, kiểm tra transaction còn hiệu lực và chưa được sử dụng.

Challenge chống replay không tự chứng minh nguồn ảnh là camera vật lý thật. Attacker có thể điều khiển thiết bị hoặc phần mềm capture. Cần kết hợp kiểm soát thiết bị, PAD, kiểm tra dữ liệu và nguồn tin cậy theo mức rủi ro.

## 12. Bảo vệ dữ liệu giấy tờ và sinh trắc

Ảnh giấy tờ và selfie thường chứa dữ liệu cá nhân nhạy cảm. Việc thu thập/lưu trữ cần được thiết kế ngay từ đầu, không chờ tới khi sản phẩm vận hành.

Nguyên tắc:
- **Purpose limitation:** chỉ dùng dữ liệu cho mục đích đã thông báo và được phép.
- **Data minimization:** chỉ thu trường và ảnh cần thiết; không giữ toàn bộ bản sao nếu kết quả/thuộc tính là đủ.
- **Access control:** giới hạn người và service được đọc ảnh gốc; phân quyền riêng cho review.
- **Encryption:** mã hóa khi truyền và lưu, quản lý khóa độc lập.
- **Retention:** đặt thời hạn lưu cho ảnh gốc, crop, OCR, sinh trắc, log và bản sao lưu; xóa theo lịch và kiểm chứng.
- **Audit:** ghi ai truy cập, xuất, sửa trạng thái và vì sao; không đưa dữ liệu nhạy cảm vào log chung.
- **Vendor governance:** đánh giá nơi xử lý, subprocessor, lưu trữ xuyên biên giới, thời hạn xóa và quyền sử dụng dữ liệu để huấn luyện.
- **User rights:** cung cấp kênh yêu cầu truy cập, chỉnh sửa, khiếu nại hoặc xóa theo pháp luật/chính sách áp dụng.

Không coi mã hóa là thay thế kiểm soát truy cập. Người có quyền giải mã vẫn có thể lạm dụng. Cần tách quyền vận hành hệ thống khỏi quyền xem ảnh và dữ liệu sinh trắc.

### 12.1. Lưu kết quả thay vì bản sao khi có thể

Nếu mục tiêu chỉ là xác minh một thuộc tính, hệ thống có thể lưu:
- Trạng thái proofing và thời điểm.
- Loại tài liệu và issuer ở mức cần thiết.
- Các thuộc tính tối thiểu đã xác minh.
- Phương pháp/nguồn và phiên bản policy.
- Mã lý do, reviewer ID và audit reference.
- Hash hoặc reference bảo vệ tới bằng chứng nếu cần điều tra và policy cho phép.

Hash của ảnh không thay thế bản gốc khi cần xem lại, nhưng có thể giúp kiểm tra tính toàn vẹn của một artifact được lưu riêng. Không lưu hash/metadata có thể liên kết người dùng nếu không có mục đích rõ ràng.

### 12.2. Dữ liệu sinh trắc có rủi ro riêng

Khuôn mặt là thuộc tính khó thay đổi nếu bị lộ. Nếu dùng face matching hoặc PAD, cần đánh giá căn cứ xử lý, sự cần thiết, tính tương xứng, độ chính xác, khả năng thay thế và tác động tới nhóm người dùng. Không lưu template sinh trắc lâu hơn nhu cầu. Không dùng ảnh thu cho identity proofing sang mục đích quảng cáo, theo dõi hoặc nhận diện 1:N nếu không có căn cứ và quy trình riêng.

## 13. Tích hợp nhà cung cấp document verification

Nhiều sản phẩm dùng dịch vụ bên ngoài để OCR, phân tích giả mạo, face matching hoặc đọc chip. Nhà cung cấp giúp giảm công sức triển khai nhưng tạo thêm trust boundary.

Trước khi tích hợp, cần đánh giá:
- Nguồn dữ liệu/mẫu tài liệu được hỗ trợ và độ mới của thư viện mẫu.
- Kết quả trả về có giải thích được hay chỉ là một điểm số tổng hợp.
- Độ chính xác theo quốc gia, loại giấy tờ, thiết bị và nhóm người dùng.
- Quy trình cập nhật mẫu khi giấy tờ đổi thiết kế.
- Cơ chế bảo vệ ảnh, token API, webhook và dữ liệu trả về.
- Nơi xử lý/lưu trữ, subprocessor, retention, xóa và sử dụng dữ liệu.
- Cách xử lý lỗi timeout, outage, kết quả không xác định và retry.
- Khả năng audit, xuất bằng chứng và khiếu nại.
- Quyền kiểm tra độc lập và yêu cầu thông báo khi có thay đổi mô hình.

Không coi một nhãn PASS của vendor là quyết định cuối cùng. Ứng dụng phải áp policy riêng, lưu nguồn/version, kết hợp tín hiệu và có cơ chế review. Webhook cần xác thực chữ ký hoặc cơ chế xác thực phù hợp, chống replay và gắn với transaction đã tạo.

## 14. Bài thực hành: thiết kế kiểm tra giấy tờ cho StudyHub

**Bối cảnh:** StudyHub cần proofing cho tài khoản giảng viên có quyền sửa điểm. Người dùng có thể dùng căn cước hoặc hộ chiếu. Hệ thống hỗ trợ chụp ảnh tài liệu, OCR và selfie; một số hộ chiếu có chip NFC. Kết quả PASS sẽ cho phép tiếp tục quy trình xác minh danh tính và cấp role theo chính sách tổ chức.

### 14.1. Thiết kế quy trình

Hãy xác định:
1. Loại tài liệu/quốc gia nào được chấp nhận và lý do.
2. Trường dữ liệu tối thiểu cần thu, mục đích và thời hạn lưu.
3. Quy tắc chất lượng ảnh và số lần chụp lại.
4. Thuộc tính nào được đọc bằng OCR, MRZ, barcode hoặc chip.
5. Cách xác minh chữ ký/chứng thư chip và nguồn issuer.
6. Có cần face matching, PAD hoặc kiểm tra thủ công không; vì sao.
7. Ngưỡng PASS/REVIEW/FAIL được kiểm định và giám sát thế nào.
8. Ai có quyền xem ảnh, thay đổi kết quả và phê duyệt ngoại lệ.
9. Cách xử lý vendor timeout, NFC không hỗ trợ, giấy tờ hết hạn và người dùng khiếu nại.
10. Hành động nào được phép sau proofing và có cần step-up cho thao tác sửa điểm không.

### 14.2. Bộ ca kiểm thử chấp nhận

| Tình huống | Kết quả mong đợi |
| --- | --- |
| Tài liệu đúng loại, ảnh rõ và dữ liệu nhất quán | Tiếp tục kiểm tra các bước bắt buộc; chỉ PASS khi toàn bộ policy đạt. |
| Ảnh mờ hoặc mất góc tài liệu | Yêu cầu chụp lại hoặc phương thức thay thế; không tự kết luận gian lận. |
| OCR đọc sai một ký tự | Đối chiếu vùng khác/nguồn khác hoặc review; không tự sửa âm thầm. |
| MRZ check digit sai | Ghi nhận bất nhất và chuyển review/fail theo policy; không chỉ dựa vào một tín hiệu. |
| Barcode đọc được nhưng dữ liệu không khớp vùng in | Không PASS tự động; review hoặc fail theo bằng chứng. |
| Chip có chữ ký không hợp lệ | Từ chối nhánh xác minh chip; đánh giá theo policy và loại tài liệu. |
| Chip không đọc được do thiết bị không hỗ trợ | Cho phép phương thức thay thế nếu policy có; không mặc định tài liệu giả. |
| Tài liệu hết hạn | Từ chối hoặc xử lý ngoại lệ được phê duyệt theo mục đích/pháp luật. |
| Tài liệu thật bị báo mất/thu hồi theo nguồn đáng tin | Không chấp nhận; chuyển quy trình xử lý gian lận/hỗ trợ. |
| Ảnh tài liệu là bản chụp màn hình | Capture/PAD/risk controls phát hiện hoặc chuyển review; không chỉ dựa OCR. |
| Selfie khớp nhưng PAD nghi ngờ | Không PASS; yêu cầu phương thức khác hoặc review. |
| Face match dưới ngưỡng trong điều kiện ánh sáng kém | Yêu cầu capture lại hoặc review theo policy; không tự động kết luận giả mạo. |
| Issuer verification timeout | Trạng thái chưa xác minh; retry có giới hạn hoặc review, không tự PASS. |
| Capture transaction hết hạn hoặc đã dùng | Từ chối response replay. |
| Webhook vendor có chữ ký sai hoặc transaction không khớp | Từ chối kết quả, ghi audit và cảnh báo. |
| Reviewer thay đổi kết quả | Yêu cầu quyền phù hợp, lý do, audit và phê duyệt bổ sung nếu policy yêu cầu. |
| Người dùng yêu cầu xóa ảnh sau khi hoàn tất | Xử lý theo retention/legal hold; xóa các bản sao thuộc phạm vi và giữ metadata tối thiểu được phép. |
| Người dùng không thể dùng camera/sinh trắc | Cung cấp phương thức thay thế có mức bảo đảm phù hợp và khả năng tiếp cận. |

### 14.3. Câu hỏi tự đánh giá

1. Vì sao giấy tờ thật bị đánh cắp vẫn có thể được dùng trong một vụ giả mạo danh tính?
2. OCR và document authenticity khác nhau ở đâu?
3. MRZ check digit chứng minh được gì và không chứng minh được gì?
4. Passive Authentication của chip hộ chiếu xác minh điều gì?
5. Vì sao chữ ký chip hợp lệ không chứng minh người cầm tài liệu là chủ thể?
6. Face matching khác liveness/PAD như thế nào?
7. Vì sao cần trạng thái REVIEW thay vì chỉ PASS/FAIL?
8. Khi nào nên kiểm tra với nguồn phát hành?
9. Làm thế nào để reviewer không dựa vào cảm tính khi đánh giá giấy tờ?
10. Dữ liệu giấy tờ và sinh trắc cần được tối thiểu hóa, mã hóa, audit và xóa như thế nào?

**Tiêu chí hoàn thành:** Người học có thể mô tả rõ từng loại bằng chứng, phân biệt tính xác thực tài liệu với việc xác minh người trình diện, thiết kế luồng PASS/REVIEW/FAIL, nêu giới hạn OCR/MRZ/chip/face matching và viết test cho replay, giả mạo, lỗi nguồn và quyền riêng tư.

## 15. Vận hành, giám sát và cải tiến

Các chỉ số nên theo dõi:
- Tỷ lệ hoàn tất proofing theo loại tài liệu, quốc gia và thiết bị.
- Tỷ lệ capture lỗi do chất lượng, số lần chụp lại và tỷ lệ bỏ cuộc.
- Tỷ lệ OCR mismatch, MRZ/barcode/chip validation failure.
- Tỷ lệ PASS/REVIEW/FAIL và lý do theo policy version.
- Tỷ lệ false rejection/appeal và kết quả review lại.
- Hiệu năng face matching/PAD theo nhóm và điều kiện đã được phép đánh giá.
- Thời gian xử lý manual review và tỷ lệ reviewer override.
- Vendor availability, latency, webhook failure và dữ liệu thiếu.
- Thời gian lưu ảnh, số lần truy cập/export và kết quả xóa.

Cần giám sát drift khi mẫu giấy tờ thay đổi, camera/browser thay đổi hoặc vendor cập nhật mô hình. Mọi thay đổi threshold, model, issuer trust list hoặc policy phải được kiểm thử, phê duyệt và version hóa. Không âm thầm thay đổi ngưỡng khi tỷ lệ fraud tăng; cần đánh giá false positive và tác động tới người dùng hợp lệ.

Khi phát hiện sự cố, cần xác định tài liệu, transaction, policy version, nguồn xác minh và người/ hệ thống đã ra quyết định. Hạn chế quyền xem ảnh gốc; điều tra bằng metadata/audit trước nếu đủ. Nếu dữ liệu bị lộ, kích hoạt incident response và đánh giá nghĩa vụ thông báo theo pháp luật áp dụng.

## 16. Tài liệu nên đọc tiếp

- **NIST SP 800-63A — Identity Proofing and Enrollment**: mô hình proofing, bằng chứng và các yêu cầu xác minh danh tính; kiểm tra phiên bản hiện hành.
- **ICAO Doc 9303 — Machine Readable Travel Documents**: cấu trúc hộ chiếu/tài liệu du lịch, MRZ và dữ liệu chip.
- **W3C Verifiable Credentials Data Model**: mô hình credential có thể xác minh trong các hệ sinh thái danh tính số.
- **NIST Face Recognition Vendor Test (FRVT)** và tài liệu đánh giá PAD liên quan: hiểu cách đo hiệu năng sinh trắc và giới hạn của chỉ số.
- **ISO/IEC 30107**: khung đánh giá presentation attack detection cho sinh trắc.
- **OWASP Application Security Verification Standard (ASVS)** và hướng dẫn privacy/security: chuyển kiểm soát dữ liệu, API và authentication thành tiêu chí xác minh.
- **Tài liệu của cơ quan phát hành giấy tờ tại quốc gia liên quan**: mẫu tài liệu, đặc điểm bảo an, chip và cơ chế xác minh chính thức.

Khi áp dụng thực tế, hãy xác định loại tài liệu, mục đích proofing, mức assurance cần đạt, nguồn tin cậy, khả năng tiếp cận và nghĩa vụ bảo vệ dữ liệu. **Kiểm tra giấy tờ là đánh giá bằng chứng có giới hạn; kết luận danh tính chỉ đáng tin khi các lớp xác minh được kết hợp đúng, các giới hạn được công bố và mọi quyết định có thể kiểm tra lại.**
