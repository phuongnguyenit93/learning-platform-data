# Đối chiếu tiêu chí chất lượng và các ngoại lệ còn hiệu lực

## 1. Mục đích và phạm vi

Trong giai đoạn phát hành và vận hành của VALIDATION_TESTING_STRATEGY, nhóm cần xác định bằng chứng kiểm thử có đáp ứng các tiêu chí chất lượng đã được thống nhất hay không, đồng thời nhận diện những ngoại lệ được phê duyệt và vẫn còn hiệu lực. Việc đối chiếu này biến kết quả kiểm thử thành căn cứ có thể kiểm tra cho quyết định phát hành: phát hành, phát hành có điều kiện theo thẩm quyền, hoặc tạm dừng để xử lý.

Tiêu chí chất lượng mô tả điều kiện cần đạt. Ngoại lệ mô tả một trường hợp cụ thể được chấp thuận xử lý khác với tiêu chí hoặc quy trình thông thường trong một phạm vi và khoảng thời gian xác định. Hai loại thông tin phải được xem xét cùng nhau nhưng giữ nguyên ý nghĩa riêng: ngoại lệ không tự động làm thay đổi tiêu chí gốc, và việc có một ngoại lệ trong hồ sơ không đồng nghĩa ngoại lệ đó còn hiệu lực tại thời điểm phát hành.

Bài học này trình bày cách xác định tiêu chí áp dụng, đối chiếu kết quả với bằng chứng, đánh giá trạng thái ngoại lệ và ghi nhận kết luận. Các ngưỡng định lượng, vai trò phê duyệt và quy định bắt buộc phải lấy từ chuẩn, hợp đồng, chính sách hoặc kế hoạch phát hành đang có hiệu lực của sản phẩm. Không tự đặt một ngưỡng chung cho mọi hệ thống.

## 2. Xác định đúng bộ tiêu chí áp dụng

Trước khi đọc kết quả kiểm thử, cần xác định chính xác bộ tiêu chí dùng để đánh giá bản phát hành. Một tiêu chí chỉ có ý nghĩa khi biết nó áp dụng cho sản phẩm, phiên bản, môi trường và phạm vi thay đổi nào.

Thông tin tối thiểu cần xác định gồm:

- **Nguồn tiêu chí:** tiêu chuẩn chất lượng, yêu cầu sản phẩm, hợp đồng dịch vụ, chính sách an toàn hoặc bảo mật, kế hoạch kiểm thử và điều kiện phát hành đã được phê duyệt.
- **Phiên bản và thời điểm hiệu lực:** mã phiên bản, ngày áp dụng, lịch sử thay đổi và người hoặc nhóm chịu trách nhiệm duy trì.
- **Phạm vi áp dụng:** dịch vụ, thành phần, luồng nghiệp vụ, nền tảng, môi trường, nhóm người dùng và loại thay đổi liên quan.
- **Cách đo và điều kiện đạt:** phép đo, tập dữ liệu, tải thử, cấu hình, thời lượng quan sát, công cụ và ngưỡng chấp nhận.
- **Điều kiện bắt buộc:** các yêu cầu mà việc không đáp ứng sẽ chặn phát hành theo chính sách hoặc cam kết hiện hành.

Không nên lấy một con số từ báo cáo cũ rồi mặc định đó là ngưỡng hiện hành. Ví dụ, thời gian phản hồi trong một đợt thử nghiệm chỉ có thể so sánh với mục tiêu hiệu năng nếu tải, dữ liệu, môi trường, cách đo và phiên bản hệ thống đủ tương đồng. Nếu tiêu chí đã thay đổi, kết quả phải được đánh giá theo phiên bản tiêu chí phù hợp với quyết định phát hành; mọi chuyển đổi giữa các phiên bản cần có căn cứ và dấu vết.

## 3. Các nhóm tiêu chí thường được đối chiếu

Danh mục cụ thể phụ thuộc vào sản phẩm và rủi ro của thay đổi. Những nhóm dưới đây là khung tham khảo để lập bảng đối chiếu, không phải bộ ngưỡng mặc định.

| Nhóm tiêu chí | Câu hỏi cần trả lời | Bằng chứng thường dùng |
|---|---|---|
| Chức năng và nghiệp vụ | Luồng chính, quy tắc nghiệp vụ và trường hợp biên có hoạt động đúng không? | Kết quả kiểm thử chức năng, kiểm thử tích hợp, biên bản nghiệm thu |
| Độ tin cậy và ổn định | Hệ thống có duy trì hoạt động trong điều kiện dự kiến và xử lý lỗi có kiểm soát không? | Kiểm thử độ bền, tỷ lệ lỗi, log, số liệu giám sát và kết quả phục hồi |
| Hiệu năng và khả năng mở rộng | Độ trễ, thông lượng và mức sử dụng tài nguyên có nằm trong giới hạn áp dụng không? | Báo cáo kiểm thử tải, cấu hình môi trường, dữ liệu đo và biểu đồ xu hướng |
| Bảo mật và quyền riêng tư | Các yêu cầu bảo vệ dữ liệu, xác thực, phân quyền và xử lý lỗ hổng có được đáp ứng không? | Kết quả quét, kiểm thử bảo mật, rà soát cấu hình và hồ sơ xử lý phát hiện |
| Tương thích và khả năng triển khai | Bản phát hành có hoạt động trên các nền tảng, phiên bản và cấu hình được hỗ trợ không? | Ma trận tương thích, kiểm thử cài đặt, nâng cấp và triển khai |
| Khả năng vận hành | Nhóm vận hành có thể quan sát, chẩn đoán, sao lưu và khôi phục dịch vụ không? | Kiểm tra cảnh báo, dashboard, runbook, diễn tập khôi phục và kế hoạch rollback |
| Hồi quy và phạm vi ảnh hưởng | Thay đổi có làm hỏng hành vi đã được xác nhận trước đó không? | Bộ kiểm thử hồi quy, phân tích tác động và liên kết yêu cầu với ca kiểm thử |

Mỗi tiêu chí cần có một cách xác định kết quả rõ ràng. Nếu tiêu chí định lượng, ghi lại giá trị đo, đơn vị, ngưỡng và điều kiện đo. Nếu tiêu chí định tính, mô tả dấu hiệu đạt, dấu hiệu không đạt và bằng chứng cần có. Tránh các kết luận không thể kiểm chứng như “đã kiểm tra”, “có vẻ ổn” hoặc “rủi ro thấp” mà không kèm căn cứ.

## 4. Quy trình đối chiếu kết quả với tiêu chí

### Bước 1: Chốt phạm vi đánh giá

Ghi rõ mã bản dựng hoặc phiên bản phát hành, thành phần thay đổi, môi trường, cấu hình, thời điểm chạy kiểm thử và các phần nằm ngoài phạm vi. Phạm vi này phải khớp với phạm vi của tiêu chí và ngoại lệ được viện dẫn. Kết quả từ một nhánh mã, môi trường hoặc bản dựng khác không được dùng thay thế nếu chưa chứng minh tính tương đương.

### Bước 2: Thu thập và kiểm tra bằng chứng

Với từng tiêu chí, tìm kết quả kiểm thử hoặc hồ sơ vận hành có liên quan. Kiểm tra nguồn tạo ra bằng chứng, thời điểm, phiên bản, cấu hình, tính đầy đủ và khả năng truy xuất. Một báo cáo không ghi phiên bản bản dựng hoặc môi trường thực thi có thể chưa đủ để chứng minh bản phát hành hiện tại đạt yêu cầu.

Nếu kết quả bị thiếu, lỗi công cụ hoặc không thể tái lập, ghi nhận là chưa đủ bằng chứng. Không tự chuyển trạng thái đó thành đạt. Khi cần chạy lại, lưu cả kết quả trước và sau, lý do chạy lại, thay đổi môi trường hoặc dữ liệu đã thực hiện.

### Bước 3: So sánh kết quả thực tế với điều kiện đạt

Đối chiếu từng tiêu chí theo đúng phương pháp đo và ngưỡng đã được phê duyệt. Với tiêu chí định lượng, so sánh số đo cùng đơn vị và cùng điều kiện. Với tiêu chí định tính, so sánh từng điều kiện quan sát được với mô tả đạt. Ghi rõ sai lệch, mức độ ảnh hưởng, phạm vi bị tác động và liên kết tới bằng chứng gốc.

### Bước 4: Phân loại trạng thái

Có thể sử dụng các trạng thái thống nhất sau trong bảng đánh giá:

- **Đạt:** bằng chứng hợp lệ cho thấy tiêu chí được đáp ứng trong đúng phạm vi.
- **Không đạt:** bằng chứng cho thấy điều kiện đạt bị vi phạm.
- **Chưa đủ bằng chứng:** chưa có kết quả, kết quả không đáng tin cậy hoặc không đủ thông tin để kết luận.
- **Không áp dụng:** tiêu chí không thuộc phạm vi bản phát hành; phải ghi lý do và căn cứ xác định.
- **Được xử lý bằng ngoại lệ:** tiêu chí chưa được đáp ứng theo cách thông thường nhưng có ngoại lệ cụ thể được xác nhận còn hiệu lực và bao phủ đúng trường hợp.

Trạng thái “được xử lý bằng ngoại lệ” phải liên kết tới hồ sơ ngoại lệ. Không đổi kết quả kiểm thử không đạt thành đạt chỉ vì đã có người chấp thuận rủi ro. Kết quả gốc vẫn cần được giữ để người ra quyết định hiểu chính xác điều gì đang được chấp nhận.

### Bước 5: Tổng hợp ảnh hưởng tới quyết định phát hành

Xem xét các tiêu chí không đạt, chưa đủ bằng chứng và được xử lý bằng ngoại lệ cùng với mức độ nghiêm trọng, khả năng xảy ra, phạm vi ảnh hưởng và biện pháp kiểm soát. Một tiêu chí bắt buộc có thể là điều kiện chặn phát hành theo chính sách hiện hành, kể cả khi các tiêu chí khác đều đạt. Chỉ người hoặc vai trò có thẩm quyền theo quy trình mới được quyết định chấp nhận rủi ro hoặc cho phép phát hành có điều kiện.

## 5. Đánh giá một ngoại lệ còn hiệu lực

Ngoại lệ thường được sử dụng khi có sai lệch đã biết nhưng tổ chức cần một phương án xử lý tạm thời, có kiểm soát. Ngoại lệ có thể liên quan đến việc hoãn sửa lỗi, thay đổi tạm thời một bước kiểm thử, giới hạn phạm vi hỗ trợ hoặc chấp nhận một rủi ro đã được đánh giá. Hình thức và quyền phê duyệt phải tuân theo quy trình của tổ chức.

Một hồ sơ ngoại lệ có thể được xem là đủ thông tin để đánh giá khi thể hiện được các nội dung sau:

1. **Định danh:** mã ngoại lệ duy nhất, trạng thái và ngày tạo.
2. **Sai lệch được đề nghị:** tiêu chí hoặc yêu cầu nào chưa được đáp ứng, kết quả thực tế là gì và bằng chứng nào xác nhận sai lệch.
3. **Phạm vi:** dịch vụ, thành phần, phiên bản, môi trường, nhóm người dùng và tình huống cụ thể được bao phủ.
4. **Lý do:** nguyên nhân chưa thể khắc phục trước thời điểm phát hành và lý do đề nghị chấp nhận tạm thời.
5. **Đánh giá rủi ro:** tác động có thể xảy ra, mức độ nghiêm trọng, khả năng xảy ra và các phụ thuộc liên quan.
6. **Biện pháp kiểm soát bù:** giới hạn tính năng, giám sát tăng cường, cảnh báo, quy trình xử lý thủ công, kế hoạch quay lui hoặc biện pháp khác có thể kiểm chứng.
7. **Trách nhiệm:** người đề xuất, người chịu trách nhiệm xử lý, vai trò phê duyệt và bằng chứng phê duyệt.
8. **Thời hạn:** thời điểm bắt đầu hiệu lực, thời điểm hết hạn hoặc điều kiện kết thúc, cùng mốc rà soát.
9. **Kế hoạch đóng:** công việc khắc phục, người phụ trách, mốc hoàn thành và bằng chứng cần có để đóng ngoại lệ.

Khi kiểm tra hiệu lực, không chỉ nhìn vào nhãn trạng thái “đã duyệt”. Cần xác nhận đồng thời:

- Phê duyệt đến từ đúng vai trò có thẩm quyền và còn truy xuất được.
- Ngoại lệ chưa hết hạn, chưa bị thu hồi, thay thế hoặc đóng.
- Bản phát hành hiện tại nằm trong phạm vi phiên bản, thành phần, môi trường và tình huống đã được chấp thuận.
- Điều kiện kèm theo vẫn được đáp ứng, chẳng hạn giới hạn lưu lượng, tắt một chức năng, bật cảnh báo hoặc có người trực xử lý.
- Rủi ro chưa thay đổi theo cách làm mất cơ sở chấp nhận ban đầu.
- Kế hoạch khắc phục và các mốc rà soát vẫn có người chịu trách nhiệm.

Nếu thiếu bằng chứng phê duyệt, hết hạn, sai phạm vi hoặc điều kiện kiểm soát không còn được đáp ứng, không được coi ngoại lệ đó là căn cứ hợp lệ cho quyết định phát hành. Cần chuyển trạng thái đánh giá về chưa đủ bằng chứng hoặc không được bao phủ, thông báo người phụ trách và xử lý theo quy trình. Không tự gia hạn hoặc mở rộng phạm vi ngoại lệ.

Đối với yêu cầu pháp lý, an toàn, bảo mật hoặc nghĩa vụ hợp đồng, cần xác định trước liệu quy định tương ứng có cho phép ngoại lệ hay không và ai có thẩm quyền chấp thuận. Một phê duyệt nội bộ không thể tự động thay thế nghĩa vụ bắt buộc hoặc sự chấp thuận của bên có thẩm quyền bên ngoài.

## 6. Bảng đối chiếu tiêu chí và ngoại lệ

Nên duy trì một bảng tổng hợp có thể truy xuất đến bằng chứng chi tiết. Ví dụ dưới đây minh họa cấu trúc; các mã, ngưỡng và trạng thái là dữ liệu giả định để giải thích cách ghi nhận, không phải chính sách hoặc số liệu mặc định của sản phẩm.

| Mã | Tiêu chí và điều kiện đạt | Kết quả, bằng chứng | Ngoại lệ liên quan | Hiệu lực và kiểm soát | Kết luận |
|---|---|---|---|---|---|
| Q-01 | Luồng thanh toán chính hoàn tất đúng quy tắc nghiệp vụ | Bộ kiểm thử hồi quy đạt; liên kết tới báo cáo bản dựng đang phát hành | Không có | Không áp dụng | Đạt |
| Q-02 | Độ trễ p95 không vượt ngưỡng trong cấu hình tải đã chốt | Đo vượt ngưỡng; báo cáo tải ghi rõ môi trường và thời điểm | EX-014 | Phê duyệt còn hạn; giới hạn lưu lượng và cảnh báo đang hoạt động | Được xử lý bằng ngoại lệ, cần theo dõi điều kiện |
| Q-03 | Không còn phát hiện bảo mật thuộc mức chặn phát hành | Báo cáo quét còn một phát hiện chưa được phân loại đầy đủ | EX-019 được viện dẫn nhưng thiếu bằng chứng phê duyệt | Không xác minh được hiệu lực | Chưa đủ bằng chứng; chưa được ngoại lệ bao phủ |

Khi lập bảng thật, mỗi dòng cần liên kết tới tài liệu nguồn của tiêu chí, lần chạy kiểm thử, lỗi hoặc phát hiện, hồ sơ ngoại lệ và quyết định liên quan. Nếu một ngoại lệ bao phủ nhiều tiêu chí, ghi rõ từng quan hệ; nếu một tiêu chí có nhiều ngoại lệ theo các môi trường khác nhau, không gộp chúng thành một kết luận chung.

## 7. Ví dụ thực tế: ngoại lệ hiệu năng trong một đợt phát hành

Giả sử một phiên bản dịch vụ có một thay đổi ở luồng truy vấn. Kế hoạch phát hành quy định phải kiểm tra độ trễ ở một mức tải xác định. Kết quả đo cho thấy độ trễ p95 vượt ngưỡng đã phê duyệt, trong khi các kiểm thử chức năng và hồi quy liên quan đều đạt.

Nhóm phát triển đề xuất ngoại lệ vì việc tối ưu cần thêm thời gian. Hồ sơ nêu rõ bản dựng và môi trường áp dụng, số đo thực tế, nhóm người dùng chịu ảnh hưởng, nguyên nhân, giới hạn lưu lượng tạm thời, dashboard và cảnh báo cần bật, người trực xử lý, người phê duyệt, thời điểm hết hạn và kế hoạch sửa lỗi.

Trước khi quyết định, người phụ trách phát hành đối chiếu từng điều kiện. Nếu ngoại lệ đã được đúng thẩm quyền phê duyệt, chưa hết hạn, bao phủ chính xác bản dựng và môi trường hiện tại, đồng thời các giới hạn và cảnh báo đã được kiểm tra, hồ sơ có thể được trình để xem xét phát hành có điều kiện theo quy trình. Kết luận vẫn phải ghi rõ tiêu chí hiệu năng chưa đạt và rủi ro được chấp nhận.

Nếu bản dựng thay đổi sau khi phê duyệt, lưu lượng vượt giới hạn, cảnh báo không hoạt động hoặc ngoại lệ đã hết hạn, cơ sở chấp nhận trước đó có thể không còn phù hợp. Nhóm phải đánh giá lại theo quy trình; không sao chép phê duyệt cũ sang phạm vi mới. Ví dụ này cho thấy hiệu lực của ngoại lệ phụ thuộc vào điều kiện thực tế và phạm vi được phê duyệt, không chỉ phụ thuộc vào việc hồ sơ từng có trạng thái được duyệt.

## 8. Ghi nhận quyết định và duy trì dấu vết

Biên bản đánh giá trước phát hành nên ghi tối thiểu:

- Phiên bản hoặc mã bản dựng được đánh giá, môi trường và thời điểm chốt dữ liệu.
- Phiên bản bộ tiêu chí và nguồn phê duyệt của bộ tiêu chí.
- Kết quả từng tiêu chí, liên kết bằng chứng và các điểm chưa đạt hoặc chưa đủ bằng chứng.
- Danh sách ngoại lệ được viện dẫn, phạm vi, thời hạn, điều kiện kiểm soát và bằng chứng xác nhận hiệu lực.
- Rủi ro còn lại, biện pháp giảm thiểu, người chịu trách nhiệm và thời điểm rà soát tiếp theo.
- Quyết định phát hành, điều kiện kèm theo, người có thẩm quyền và thời điểm quyết định.

Sau khi phát hành, cần theo dõi các điều kiện gắn với ngoại lệ. Nếu chỉ số vượt giới hạn, biện pháp kiểm soát bị vô hiệu, xuất hiện tác động mới hoặc đến hạn khắc phục, nhóm vận hành phải kích hoạt hành động đã thống nhất: giảm tải, tắt chức năng, quay lui, xử lý sự cố hoặc đưa vấn đề trở lại hội đồng/quy trình phê duyệt. Khi ngoại lệ được khắc phục, lưu bằng chứng xác nhận, cập nhật trạng thái và đóng liên kết với bản phát hành liên quan.

Tiêu chí và ngoại lệ đều cần lịch sử thay đổi. Việc sửa ngưỡng, kéo dài thời hạn hoặc mở rộng phạm vi phải có lý do, người thực hiện, người phê duyệt và thời điểm. Lịch sử này giúp người đánh giá sau hiểu được quyết định được đưa ra dựa trên thông tin nào tại thời điểm đó.

## 9. Những sai sót cần tránh

- **Dùng sai phiên bản tiêu chí:** so sánh với tài liệu cũ hoặc ngưỡng chưa được phê duyệt. Cần xác nhận nguồn và phiên bản trước khi đánh giá.
- **Dùng bằng chứng không cùng phạm vi:** lấy kết quả từ bản dựng, môi trường hoặc cấu hình khác mà không chứng minh tương đương. Cần liên kết bằng chứng với đúng đối tượng phát hành.
- **Coi thiếu dữ liệu là đạt:** kết quả không có, lỗi hoặc không thể tái lập không chứng minh tiêu chí được đáp ứng. Phải ghi rõ chưa đủ bằng chứng.
- **Coi mọi ngoại lệ đã duyệt là còn hiệu lực:** bỏ qua thời hạn, phạm vi hoặc điều kiện đi kèm. Phải kiểm tra lại tại thời điểm ra quyết định.
- **Gộp ngoại lệ vào kết quả kiểm thử:** làm mất dấu vết về sai lệch thực tế. Giữ nguyên kết quả và liên kết ngoại lệ như một căn cứ xử lý riêng.
- **Gia hạn bằng trao đổi không truy xuất được:** không có hồ sơ và phê duyệt theo đúng thẩm quyền. Cần cập nhật qua quy trình chính thức.
- **Không theo dõi sau phát hành:** điều kiện kiểm soát có thể mất tác dụng sau khi triển khai. Phải gắn trách nhiệm, cảnh báo và mốc rà soát với ngoại lệ.

## 10. Danh sách kiểm tra trước khi chốt phát hành

1. Bộ tiêu chí đúng phiên bản, nguồn, phạm vi và thời điểm hiệu lực.
2. Mỗi tiêu chí có điều kiện đạt rõ ràng và phương pháp kiểm tra phù hợp.
3. Bằng chứng gắn với đúng bản dựng, môi trường, cấu hình và lần chạy.
4. Mọi kết quả được phân loại rõ: đạt, không đạt, chưa đủ bằng chứng, không áp dụng hoặc được xử lý bằng ngoại lệ.
5. Mỗi ngoại lệ được viện dẫn đã xác minh phê duyệt, phạm vi, thời hạn, điều kiện kiểm soát và kế hoạch khắc phục.
6. Rủi ro còn lại và điều kiện phát hành có người chịu trách nhiệm.
7. Quyết định cuối cùng có căn cứ, đúng thẩm quyền và lưu được dấu vết.
8. Các điều kiện cần theo dõi sau phát hành đã được chuyển giao cho nhóm vận hành.

Chỉ chốt kết luận khi người ra quyết định có thể đi từ từng tiêu chí đến bằng chứng, từ sai lệch đến ngoại lệ (nếu có), rồi đến phê duyệt và điều kiện vận hành. Chuỗi liên kết rõ ràng này giúp quyết định phát hành có thể được giải thích, rà soát và đánh giá lại khi hệ thống hoặc mức rủi ro thay đổi.
