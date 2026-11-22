# Ghi chép giả thuyết, thao tác, bằng chứng và phát hiện

## 1. Vì sao cần ghi chép trong kiểm thử thủ công và khám phá?

Kiểm thử thủ công và kiểm thử khám phá tạo ra nhiều thông tin trong lúc người kiểm thử tương tác với sản phẩm: giả thuyết về hành vi, câu hỏi cần tìm lời giải, dữ liệu đã dùng, thao tác đã thực hiện, trạng thái quan sát được, bằng chứng thu thập và những điều bất ngờ phát hiện. Nếu chỉ ghi kết luận “đã kiểm tra” hoặc “không thấy lỗi”, nhóm sẽ khó tái dựng điều đã làm, đánh giá phần đã bao phủ, điều tra phát hiện và quyết định bước tiếp theo.

Ghi chép tốt giúp biến hoạt động khám phá linh hoạt thành một quá trình có thể giải thích và học hỏi. Người khác có thể hiểu vì sao một hướng kiểm tra được chọn, điều kiện nào đã được thử, kết quả quan sát được là gì, bằng chứng nằm ở đâu và còn câu hỏi nào chưa được trả lời. Ghi chép cũng giúp tránh lặp lại công việc, hỗ trợ báo cáo lỗi và chuyển hiểu biết từ một cá nhân thành tri thức dùng chung.

Trong phạm vi **VALIDATION_TESTING_STRATEGY**, ghi chép cần giữ được mối liên hệ giữa giả thuyết, thao tác, bằng chứng và phát hiện. Nội dung cần đủ chi tiết để hỗ trợ quyết định chất lượng nhưng không biến mỗi phiên khám phá thành một kịch bản cứng nhắc. Mục tiêu là ghi lại diễn biến và suy luận quan trọng trong khi vẫn để người kiểm thử thích ứng với điều quan sát được.

Một ghi chép có giá trị thường trả lời được năm câu hỏi:

1. **Vì sao kiểm tra?** Giả thuyết, câu hỏi, rủi ro hoặc mục tiêu nào dẫn đến hoạt động này?
2. **Đã kiểm tra trong điều kiện nào?** Phiên bản, môi trường, dữ liệu, tài khoản và trạng thái ban đầu là gì?
3. **Đã làm gì?** Các thao tác hoặc thử nghiệm quan trọng được thực hiện theo thứ tự nào?
4. **Đã quan sát điều gì?** Kết quả thực tế, bằng chứng và điểm khác biệt so với mong đợi là gì?
5. **Tiếp theo cần làm gì?** Phát hiện nào cần báo lỗi, câu hỏi nào cần điều tra và rủi ro nào còn chưa được xác nhận?

## 2. Phân biệt giả thuyết, câu hỏi, thao tác, quan sát và phát hiện

Các khái niệm này có liên quan nhưng không nên gộp thành một ghi chú chung chung.

| Thành phần | Ý nghĩa | Ví dụ |
|---|---|---|
| Giả thuyết | Nhận định có thể kiểm tra về cách hệ thống hoạt động hoặc nơi có thể tồn tại lỗi | “Nếu phiên đăng nhập hết hạn trong lúc lưu biểu mẫu, ứng dụng có thể mất nội dung người dùng đã nhập.” |
| Câu hỏi khám phá | Điều người kiểm thử muốn tìm hiểu khi chưa đủ căn cứ để nêu giả thuyết cụ thể | “Ứng dụng xử lý thế nào khi mạng bị ngắt ngay sau khi người dùng nhấn Lưu?” |
| Thao tác | Hành động hoặc biến đổi điều kiện được thực hiện | Nhập dữ liệu, chờ phiên hết hạn, ngắt mạng, nhấn Lưu và kết nối lại |
| Quan sát | Điều thực tế nhìn thấy hoặc đo được, chưa nhất thiết là lỗi | Nút Lưu chuyển sang trạng thái đang xử lý nhưng không có thông báo trong 8 giây |
| Phát hiện | Kết luận hoặc vấn đề đáng chú ý được rút ra từ quan sát và bằng chứng | Nội dung biểu mẫu bị mất sau khi phiên hết hạn dù giao diện thông báo lưu thành công |
| Giả định | Điều đang được coi là đúng nhưng chưa được xác nhận | Người dùng có thể tiếp tục phiên làm việc trong vòng 15 phút sau khi mạng phục hồi |
| Bằng chứng | Tư liệu hỗ trợ quan sát hoặc kết luận | Video thao tác, ảnh chụp, log đã làm sạch, request ID và dữ liệu trước/sau |

Giả thuyết không phải là kết quả. Người kiểm thử cần ghi rõ giả thuyết được hỗ trợ, bị bác bỏ hay chưa thể kết luận. Một quan sát bất thường cũng chưa tự động là lỗi sản phẩm; nó có thể do môi trường, dữ liệu, cấu hình, thao tác hoặc kỳ vọng chưa rõ.

Ví dụ, “ứng dụng bị treo” là một mô tả chưa đủ chính xác. Ghi chép hữu ích hơn là: “Sau khi chọn Lưu với kết nối mạng bị ngắt, màn hình không phản hồi thao tác trong 8 giây; sau khi kết nối lại, nội dung biểu mẫu không còn. Video phiên 04:12–04:28 và mã tương quan `req-7f2a` được đính kèm.” Phần sau tách điều quan sát được khỏi kết luận nguyên nhân.

## 3. Chuẩn bị phiên kiểm thử và xác định mục tiêu

### 3.1. Xác định mục tiêu và phạm vi

Trước phiên kiểm thử, ghi rõ tính năng hoặc hành trình sẽ khám phá, người dùng mục tiêu, phiên bản, ranh giới trong phạm vi và phần chưa được kiểm tra. Mục tiêu nên hướng đến một câu hỏi có ý nghĩa, chẳng hạn xác nhận khả năng khôi phục dữ liệu khi mất kết nối hoặc tìm điểm người dùng có thể vượt qua kiểm tra phân quyền.

Tránh mục tiêu quá rộng như “kiểm tra toàn bộ ứng dụng”. Mục tiêu cụ thể giúp chọn dữ liệu, công cụ, thời lượng và mức độ chi tiết cần ghi. Nếu phát hiện hướng mới có rủi ro cao, người kiểm thử có thể điều chỉnh phạm vi nhưng cần ghi lại lý do và tác động đến mục tiêu ban đầu.

### 3.2. Viết giả thuyết có thể kiểm tra

Một giả thuyết hữu ích nêu điều kiện kích hoạt, hành vi dự kiến và dấu hiệu có thể quan sát. Có thể dùng mẫu:

> Khi **[điều kiện hoặc sự kiện]**, nếu **[tác nhân/thao tác]**, hệ thống có thể **[hành vi nghi ngờ]**, dẫn đến **[tác động]**. Tôi sẽ kiểm tra bằng **[thao tác/dữ liệu]** và quan sát **[dấu hiệu]**.

Ví dụ:

> Khi người dùng gửi biểu mẫu hai lần do phản hồi chậm, hệ thống có thể tạo hai hồ sơ giống nhau. Tôi sẽ gửi hai yêu cầu gần như đồng thời với cùng dữ liệu và quan sát số hồ sơ được lưu cùng mã phản hồi.

Không cần ép mọi phiên khám phá bắt đầu bằng một giả thuyết đã hoàn chỉnh. Với tính năng mới hoặc yêu cầu chưa rõ, có thể bắt đầu bằng câu hỏi mở, sau đó hình thành giả thuyết dựa trên quan sát.

### 3.3. Tạo charter cho phiên khám phá

Charter mô tả hướng khám phá mà không quy định trước mọi bước. Một charter ngắn có thể gồm:

- **Mục tiêu:** điều cần tìm hiểu hoặc rủi ro cần kiểm tra.
- **Phạm vi:** chức năng, luồng, vai trò hoặc thành phần liên quan.
- **Giả thuyết/câu hỏi:** nhận định hoặc câu hỏi dẫn dắt.
- **Điều kiện:** phiên bản, môi trường, dữ liệu, tài khoản và phụ thuộc.
- **Giới hạn:** hành động không được thực hiện, dữ liệu không được sử dụng hoặc thời gian cho phép.
- **Tiêu chí hoàn tất:** điều kiện kết thúc phiên hoặc điều kiện cần báo ngay.

Charter là điểm bắt đầu. Nếu bằng chứng dẫn đến một hướng mới hợp lý, người kiểm thử có thể chuyển hướng và ghi lại quyết định đó.

### 3.4. Ghi điều kiện ban đầu

Thông tin môi trường ảnh hưởng trực tiếp đến khả năng tái hiện. Nên ghi:

- Phiên bản ứng dụng, build/commit hoặc mã phát hành.
- Môi trường, URL hoặc định danh hệ thống theo quy định nội bộ.
- Hệ điều hành, trình duyệt, thiết bị, độ phân giải hoặc phiên bản client nếu có liên quan.
- Cấu hình, feature flag, ngôn ngữ, múi giờ và trạng thái mạng.
- Vai trò/tài khoản kiểm thử và quyền cần thiết; không ghi mật khẩu hoặc token.
- Dữ liệu đầu vào, trạng thái dữ liệu ban đầu và cách tạo dữ liệu.
- Dịch vụ phụ thuộc, sandbox, mock hoặc container đang sử dụng.
- Thời điểm bắt đầu và các điều kiện đặc biệt.

Không cần chép mọi thông tin môi trường vào từng ghi chú nếu có một mã phiên hoặc liên kết đến hồ sơ môi trường. Nhưng dữ liệu phải đủ để người khác biết phiên được chạy trong điều kiện nào.

## 4. Ghi lại thao tác trong lúc khám phá

### 4.1. Ghi các bước có ý nghĩa

Ghi những thao tác làm thay đổi trạng thái hoặc giúp kiểm tra một giả thuyết. Mỗi bước nên có hành động, dữ liệu hoặc điều kiện được dùng và kết quả quan sát. Không cần ghi từng lần nhấp chuột không có ý nghĩa kiểm thử; cần ghi đủ để người khác tái hiện đường đi quan trọng.

Ví dụ:

| Thời điểm | Thao tác/điều kiện | Quan sát |
|---|---|---|
| 09:12:03 | Đăng nhập bằng tài khoản có quyền sửa hồ sơ | Đăng nhập thành công, trang hồ sơ hiển thị |
| 09:13:10 | Sửa trường địa chỉ và giữ biểu mẫu mở | Dữ liệu mới hiển thị trong biểu mẫu |
| 09:13:40 | Ngắt kết nối mạng trong công cụ mô phỏng mạng | Biểu tượng mạng chuyển sang ngoại tuyến |
| 09:13:44 | Nhấn Lưu | Nút chuyển sang trạng thái đang xử lý, không có thông báo lỗi |
| 09:13:52 | Kết nối mạng trở lại và tải lại hồ sơ | Địa chỉ cũ vẫn được lưu; nội dung mới bị mất |

Bảng này giúp tách thao tác khỏi kết quả. Người đọc có thể xác định bước nào dẫn đến trạng thái bất thường và điều kiện mạng nào cần tái tạo.

### 4.2. Ghi dữ liệu và trạng thái

Với dữ liệu có ảnh hưởng đến kết quả, ghi giá trị đại diện hoặc mã định danh an toàn. Nêu trạng thái trước và sau thao tác, chẳng hạn số lượng bản ghi, trạng thái đơn hàng, số dư giả lập hoặc quyền của tài khoản.

Không đưa dữ liệu cá nhân, bí mật hoặc thông tin xác thực vào ghi chép nếu không cần thiết. Có thể thay bằng dữ liệu tổng hợp, giá trị đã che hoặc mã tham chiếu được phép. Nếu cần chia sẻ bằng chứng, kiểm tra nội dung ảnh, video, log và URL để loại bỏ thông tin nhạy cảm.

### 4.3. Ghi thời gian và trình tự

Thời gian rất quan trọng với lỗi timeout, race condition, hết hạn phiên, retry và sự kiện bất đồng bộ. Ghi timestamp hoặc thứ tự tương đối khi cần; thống nhất múi giờ hoặc lưu thời gian theo UTC nếu nhiều hệ thống tham gia.

Nếu hai thao tác diễn ra gần đồng thời, ghi rõ cách tạo đồng thời, độ trễ giữa chúng và công cụ sử dụng. Không dùng mô tả “nhấn gần như cùng lúc” khi có thể cung cấp cách tái tạo chính xác hơn.

### 4.4. Ghi thay đổi hướng khám phá

Trong kiểm thử khám phá, quan sát mới có thể làm thay đổi hướng kiểm tra. Ghi lại:

- Quan sát nào dẫn đến câu hỏi mới.
- Giả thuyết ban đầu được điều chỉnh ra sao.
- Vì sao bỏ hoặc tạm dừng một nhánh kiểm tra.
- Rủi ro mới nào được phát hiện.
- Phần nào của charter ban đầu chưa được hoàn thành.

Điều này giúp người xem lại hiểu quá trình suy luận thay vì chỉ thấy một chuỗi thao tác rời rạc.

## 5. Thu thập và quản lý bằng chứng

### 5.1. Chọn loại bằng chứng phù hợp

Không phải phát hiện nào cũng cần cùng một loại artifact. Chọn bằng chứng trực tiếp hỗ trợ câu hỏi đang kiểm tra.

| Loại bằng chứng | Hữu ích khi | Lưu ý |
|---|---|---|
| Ảnh chụp màn hình | Trạng thái giao diện, thông báo, bố cục hoặc dữ liệu hiển thị | Giữ ngữ cảnh cần thiết; che thông tin nhạy cảm |
| Video/screen recording | Lỗi phụ thuộc trình tự, chuyển trạng thái hoặc thao tác khó mô tả | Ghi thời điểm trong video; tránh thu âm hoặc ghi màn hình ngoài phạm vi cần thiết |
| Log ứng dụng | Lỗi xử lý, exception, trạng thái nội bộ và thông tin chẩn đoán | Loại bỏ secret, token, dữ liệu cá nhân; giữ timestamp và correlation ID |
| Network trace/request-response | Lỗi API, header, payload, mã trạng thái và thời gian phản hồi | Làm sạch credential và dữ liệu nhạy cảm trước khi chia sẻ |
| Metric/trace | Hiệu năng, timeout, phụ thuộc và hành vi phân tán | Ghi khoảng thời gian, môi trường và định danh tương quan |
| Dữ liệu trước/sau | Sai lệch dữ liệu, mất dữ liệu, giao dịch trùng hoặc trạng thái không nhất quán | Dùng bản ghi thử nghiệm; mô tả cách đối chiếu |
| Nhật ký thao tác | Tái hiện luồng thủ công hoặc khám phá | Nêu điều kiện, dữ liệu, kết quả và nhánh đã thử |
| Biên bản trao đổi/rà soát | Làm rõ yêu cầu hoặc xác nhận kết luận với chuyên gia | Ghi người tham gia, ngày và quyết định; tránh diễn giải thành cam kết nếu chưa được xác nhận |

### 5.2. Bằng chứng phải có ngữ cảnh

Một ảnh chụp chỉ có thông báo lỗi có thể không đủ nếu thiếu phiên bản, thao tác trước đó hoặc trạng thái dữ liệu. Một log có stack trace nhưng không có thời điểm và correlation ID có thể khó ghép với request. Bằng chứng nên liên kết với mã phiên, giả thuyết, thao tác và phát hiện.

Có thể đặt tên artifact theo quy ước dễ tìm, ví dụ:

```text
EXP-2026-041/
  notes.md
  evidence/
    step-05-save-timeout.png
    step-05-network-trace.txt
    step-06-record-state.json
  findings/
    FIND-02-session-data-loss.md
```

Đây là cấu trúc minh họa. Dùng kho lưu trữ và quy ước đặt tên của tổ chức; không tạo bản sao không kiểm soát của dữ liệu nhạy cảm.

### 5.3. Bảo đảm tính toàn vẹn và khả năng truy xuất

Ghi nguồn tạo artifact, thời điểm, người thực hiện hoặc công cụ, phiên bản liên quan và liên kết đến phiên khám phá. Nếu artifact được cắt, làm mờ hoặc chuyển định dạng, ghi rõ việc xử lý để người xem hiểu giới hạn. Không chỉnh sửa nội dung theo cách làm thay đổi ý nghĩa bằng chứng.

Với bằng chứng quan trọng cho quyết định phát hành, lưu trong hệ thống có quyền truy cập và lịch sử phù hợp. Đặt thời hạn lưu theo chính sách, tránh giữ vô thời hạn dữ liệu cá nhân hoặc dữ liệu thử nghiệm có rủi ro.

### 5.4. Không thu thập quá mức

Chỉ thu thập những gì cần để tái hiện, xác nhận và điều tra. Video dài có thể chứa thông tin ngoài phạm vi; log đầy đủ có thể chứa token; file HAR có thể lưu cookie và header xác thực. Trước khi chia sẻ, rà soát và loại bỏ dữ liệu không cần thiết. Dùng tài khoản thử nghiệm và dữ liệu tổng hợp khi có thể.

## 6. Ghi nhận và phân loại phát hiện

### 6.1. Tách quan sát khỏi kết luận

Ghi điều quan sát được trước, sau đó mới nêu diễn giải. Ví dụ:

- **Quan sát:** sau khi bấm “Lưu”, giao diện hiển thị thông báo “Đã lưu”; khi tải lại trang, giá trị cũ xuất hiện.
- **Diễn giải cần xác minh:** có thể giao diện hiển thị thành công trước khi server xác nhận lưu dữ liệu.
- **Phát hiện:** trạng thái hiển thị không nhất quán với dữ liệu đã lưu; cần điều tra điều kiện gây ra và mức ảnh hưởng.

Phân biệt này giúp tránh báo cáo nguyên nhân chưa được chứng minh như sự thật. Nguyên nhân gốc thường cần developer hoặc chuyên gia phân tích thêm.

### 6.2. Phân loại phát hiện

Một phiên khám phá có thể tạo ra nhiều loại phát hiện:

- **Defect/bug:** hành vi quan sát được vi phạm yêu cầu, hợp đồng hoặc kỳ vọng đã thống nhất.
- **Anomaly:** hành vi bất thường cần điều tra thêm, chưa đủ căn cứ kết luận là defect.
- **Risk:** tình huống có thể gây hậu quả nhưng chưa quan sát thấy sự kiện lỗi.
- **Requirement question:** yêu cầu hoặc quy tắc nghiệp vụ chưa rõ, cần người có thẩm quyền xác nhận.
- **Usability observation:** khó khăn, nhầm lẫn hoặc trở ngại người dùng có thể gặp.
- **Improvement opportunity:** đề xuất cải thiện ngoài tiêu chí lỗi hiện tại.
- **Environment issue:** lỗi do môi trường, dữ liệu, cấu hình hoặc phụ thuộc kiểm thử.

Không gộp mọi quan sát vào danh sách bug. Phân loại đúng giúp giao đúng người xử lý và tránh làm sai lệch số liệu chất lượng.

### 6.3. Đánh giá mức độ nghiêm trọng và ưu tiên

Khi phát hiện có khả năng là lỗi, đánh giá tác động đến người dùng, dữ liệu, bảo mật, nghiệp vụ, tần suất, phạm vi ảnh hưởng và khả năng khôi phục. Phân biệt:

- **Severity (mức độ nghiêm trọng):** hậu quả của lỗi đối với hệ thống hoặc người dùng.
- **Priority (mức ưu tiên):** mức khẩn cấp và thứ tự xử lý theo bối cảnh phát hành, nguồn lực và mục tiêu.

Một lỗi có thể severity cao nhưng chỉ xuất hiện trong một điều kiện hiếm; vẫn cần được đánh giá theo chính sách rủi ro. Một lỗi giao diện nhỏ có thể priority cao nếu ảnh hưởng đến sự kiện hoặc khách hàng quan trọng. Không để người báo lỗi tự quyết định một mình mọi mức ưu tiên.

### 6.4. Khi nào cần tạo bug report?

Tạo bug report khi có đủ thông tin để người khác hiểu vấn đề và bắt đầu tái hiện hoặc điều tra. Nếu chưa đủ, ghi anomaly hoặc câu hỏi và chỉ rõ thông tin còn thiếu. Với vấn đề nghiêm trọng về bảo mật, dữ liệu hoặc an toàn, sử dụng quy trình báo cáo chuyên biệt và kênh được phê duyệt; không đưa chi tiết khai thác nhạy cảm vào nơi công khai.

## 7. Viết phát hiện có thể hành động

Một phát hiện tốt cần ngắn gọn nhưng đủ bối cảnh. Có thể dùng cấu trúc:

1. **Tiêu đề:** mô tả triệu chứng và điều kiện nổi bật.
2. **Môi trường:** phiên bản, build, thiết bị, trình duyệt và cấu hình liên quan.
3. **Điều kiện ban đầu:** tài khoản/vai trò, dữ liệu và trạng thái trước khi thao tác.
4. **Các bước tái hiện:** thứ tự thao tác rõ ràng, dữ liệu cần thiết và thời điểm nếu quan trọng.
5. **Kết quả mong đợi:** căn cứ từ yêu cầu, hợp đồng hoặc quy tắc đã xác nhận.
6. **Kết quả thực tế:** điều quan sát được, không suy diễn nguyên nhân.
7. **Tần suất:** luôn xảy ra, thỉnh thoảng, chỉ xảy ra một lần hoặc chưa xác định; nêu số lần thử.
8. **Tác động:** người dùng, dữ liệu, nghiệp vụ, bảo mật và khả năng khôi phục.
9. **Bằng chứng:** ảnh, video, log đã làm sạch, request ID hoặc liên kết phiên khám phá.
10. **Liên kết:** yêu cầu, rủi ro, test condition, phiên khám phá và lỗi liên quan.

Ví dụ tiêu đề chưa tốt: “Lỗi lưu hồ sơ”.

Ví dụ rõ hơn: “Hồ sơ hiển thị thông báo lưu thành công nhưng dữ liệu không được cập nhật khi mạng phục hồi sau timeout”. Tiêu đề cho biết hành vi và điều kiện có thể giúp nhóm định hướng điều tra.

Không cần đưa mọi suy luận vào phần kết quả thực tế. Có thể thêm mục “nhận định ban đầu” hoặc “câu hỏi cần điều tra” để phân biệt với bằng chứng.

## 8. Tổ chức phiên khám phá theo thời gian

### 8.1. Session-based test management

Session-based test management (SBTM) tổ chức kiểm thử khám phá thành các phiên có mục tiêu, thời lượng, ghi chép và debrief. Một phiên thường có:

- **Charter:** mục tiêu và phạm vi khám phá.
- **Timebox:** khoảng thời gian tập trung, ví dụ 60–90 phút tùy độ phức tạp.
- **Session notes:** giả thuyết, thao tác, quan sát, câu hỏi và nhánh đã thử.
- **Evidence:** artifact hỗ trợ phát hiện.
- **Findings:** lỗi, bất thường, rủi ro và câu hỏi được phát hiện.
- **Debrief:** trao đổi ngắn về kết quả, độ bao phủ và bước tiếp theo.

Timebox giúp giữ trọng tâm và dễ phân bổ công sức. Nó không phải giới hạn cứng buộc dừng ngay khi còn rủi ro nghiêm trọng; nếu cần tiếp tục, ghi lý do và thống nhất phiên tiếp theo.

### 8.2. Phân bổ thời gian và ghi nhận tiến độ

Trong một phiên, có thể dành phần lớn thời gian cho khám phá, một phần cho ghi bằng chứng và phân tích, phần cuối cho tổng hợp/debrief. Tỷ lệ tùy tình huống; không nên dành toàn bộ thời gian ghi chép đến mức không còn khám phá hoặc chỉ thao tác mà không lưu lại kết quả.

Ghi rõ charter nào đã hoàn thành, phần nào chưa thực hiện, hướng nào bị chặn và lý do. Nếu chuyển sang một hướng có rủi ro cao hơn, nêu điều gì khiến ưu tiên thay đổi.

### 8.3. Debrief sau phiên

Debrief là cuộc trao đổi ngắn giữa người kiểm thử và người liên quan để kiểm tra chất lượng ghi chép và thống nhất bước tiếp theo. Có thể hỏi:

- Mục tiêu ban đầu đã được kiểm tra đến đâu?
- Giả thuyết nào được hỗ trợ, bác bỏ hoặc còn bỏ ngỏ?
- Phát hiện nào cần bug report hoặc chuyển cấp ngay?
- Bằng chứng có đủ để người khác tái hiện không?
- Có giới hạn môi trường hoặc dữ liệu nào ảnh hưởng kết luận?
- Cần kiểm thử thêm, làm rõ yêu cầu hay phân tích kỹ thuật?
- Rủi ro nào cần cập nhật trong hồ sơ chất lượng?

Debrief không nhằm đánh giá cá nhân theo số lỗi tìm được. Mục đích là tăng chất lượng thông tin và học hỏi giữa các vai trò.

## 9. Ví dụ thực tế: khám phá quy trình lưu biểu mẫu khi mất kết nối

### 9.1. Charter và giả thuyết

**Mục tiêu:** tìm hiểu liệu người dùng có mất dữ liệu khi lưu biểu mẫu trong điều kiện mạng không ổn định.

**Giả thuyết:** nếu mạng bị ngắt sau khi client gửi yêu cầu nhưng trước khi nhận phản hồi, người dùng có thể không biết dữ liệu đã được lưu hay chưa; thao tác thử lại có thể tạo bản ghi trùng hoặc ghi đè dữ liệu mới.

**Điều kiện:** build `web-2.8.1`, môi trường staging, tài khoản thử nghiệm có quyền sửa, dữ liệu biểu mẫu tổng hợp và công cụ mô phỏng mạng.

### 9.2. Ghi chép thao tác và quan sát

| Bước | Thao tác | Quan sát |
|---|---|---|
| 1 | Mở hồ sơ thử nghiệm và ghi lại giá trị ban đầu | Hồ sơ có ID `FORM-TEST-17`, trạng thái `draft` |
| 2 | Thay đổi trường địa chỉ và nhấn Lưu | Nút chuyển sang `Saving`; request được gửi |
| 3 | Ngắt mạng ngay sau khi request được gửi | Trình duyệt báo mất kết nối; chưa nhận response |
| 4 | Chờ 5 giây rồi kết nối lại | Giao diện vẫn hiển thị giá trị mới trong bộ nhớ trang |
| 5 | Tải lại hồ sơ từ server | Giá trị cũ xuất hiện; trạng thái vẫn là `draft` |
| 6 | Nhập lại giá trị và nhấn Lưu khi mạng ổn định | Giao diện báo thành công; tải lại thấy giá trị mới |

### 9.3. Bằng chứng và phát hiện

- Video phiên ghi lại thời điểm ngắt mạng và thao tác tải lại.
- Network trace đã loại bỏ cookie và token, cho thấy request đầu tiên không nhận response.
- Log server theo correlation ID xác nhận request đầu tiên đã timeout trước khi hoàn tất ghi dữ liệu.
- Dữ liệu trước/sau cho thấy lần đầu không cập nhật, lần thứ hai cập nhật thành công.

**Phát hiện:** người dùng không có chỉ dẫn rõ ràng về trạng thái lưu khi mất phản hồi; dữ liệu mới có thể chỉ tồn tại trong bộ nhớ giao diện và mất sau khi tải lại. Cần điều tra thêm liệu các tình huống server đã ghi thành công nhưng response bị mất có tạo trạng thái không rõ hoặc giao dịch trùng hay không.

Phát hiện này nên được liên kết với yêu cầu lưu dữ liệu, rủi ro mất dữ liệu và điều kiện kiểm thử timeout/retry. Không kết luận nguyên nhân gốc chỉ từ video; log và đối chiếu dữ liệu cung cấp bằng chứng bổ sung.

## 10. Mẫu ghi chép phiên kiểm thử khám phá

Có thể dùng mẫu sau trong hệ thống quản lý kiểm thử hoặc tài liệu nhóm:

```markdown
# Session EXP-YYYY-NNN

## Thông tin phiên
- Người kiểm thử:
- Ngày/giờ và múi giờ:
- Sản phẩm/tính năng:
- Build/commit:
- Môi trường/thiết bị/trình duyệt:
- Tài khoản/vai trò thử nghiệm (không ghi credential):
- Charter:
- Timebox:

## Mục tiêu và giả thuyết
- Mục tiêu:
- Giả thuyết/câu hỏi:
- Rủi ro liên quan:
- Điều kiện hoàn tất:

## Điều kiện ban đầu
- Dữ liệu và trạng thái:
- Cấu hình/feature flag:
- Phụ thuộc và trạng thái mạng:
- Giới hạn hoặc giả định:

## Nhật ký thao tác
| Thời điểm | Thao tác/dữ liệu | Quan sát | Bằng chứng |
|---|---|---|---|
| | | | |

## Phát hiện
- ID/tiêu đề:
- Loại: defect / anomaly / risk / question / usability / environment
- Kết quả mong đợi:
- Kết quả thực tế:
- Tần suất và khả năng tái hiện:
- Tác động/severity đề xuất:
- Liên kết yêu cầu/rủi ro:
- Artifact:

## Kết quả phiên
- Giả thuyết được hỗ trợ/bác bỏ/chưa kết luận:
- Charter đã hoàn thành:
- Phần chưa kiểm tra và lý do:
- Câu hỏi còn mở:
- Hành động tiếp theo, owner và hạn:
```

Mẫu cần được điều chỉnh theo công cụ và chính sách của nhóm. Không cần điền trường không liên quan; nếu thiếu thông tin quan trọng, ghi rõ chưa có thay vì đoán.

## 11. Mẫu bug report từ phát hiện khám phá

```markdown
## Tiêu đề
[Triệu chứng] khi [điều kiện kích hoạt]

## Môi trường
- Build/commit:
- Môi trường:
- Thiết bị/trình duyệt:
- Tài khoản/vai trò thử nghiệm:

## Điều kiện ban đầu
- Trạng thái dữ liệu:
- Cấu hình/phụ thuộc:

## Các bước tái hiện
1.
2.
3.

## Kết quả mong đợi

## Kết quả thực tế

## Tần suất
- Số lần thử:
- Số lần gặp:
- Điều kiện ảnh hưởng:

## Tác động
- Người dùng/nghiệp vụ/dữ liệu:
- Severity đề xuất:
- Rủi ro liên quan:

## Bằng chứng
- Ảnh/video:
- Log/trace đã làm sạch:
- Correlation ID:
- Session ID:

## Câu hỏi hoặc nhận định cần điều tra
```

Bug report nên có đủ thông tin để người khác bắt đầu điều tra mà không phải hỏi lại những điều kiện cơ bản. Nếu lỗi không tái hiện ổn định, ghi rõ xác suất quan sát và các yếu tố có thể ảnh hưởng.

## 12. Chất lượng ghi chép và cách tránh sai lệch

### 12.1. Viết khách quan và cụ thể

Ưu tiên mô tả hành vi có thể quan sát thay cho phán xét. “API phản hồi sau 4,2 giây” hữu ích hơn “API rất chậm” nếu có công cụ đo. “Tài khoản role Viewer nhận mã 200 khi gọi endpoint sửa hồ sơ” cụ thể hơn “phân quyền bị lỗi”.

### 12.2. Ghi cả kết quả không tìm thấy lỗi

Không tìm thấy lỗi trong một phiên không chứng minh tính năng không có lỗi. Ghi phạm vi, điều kiện và giới hạn đã thử. Ví dụ: “Trong 45 phút, đã thử 12 trường hợp gồm timeout, retry tuần tự và mất kết nối trước khi gửi; chưa thử retry đồng thời hoặc tình huống server đã commit nhưng response bị mất.” Đây là thông tin hữu ích hơn “PASS”.

### 12.3. Tránh ghi chép sau quá lâu

Ghi những điểm quan trọng trong lúc thực hiện hoặc ngay sau mỗi nhánh khám phá. Trí nhớ dễ bỏ sót thứ tự, thời gian, dữ liệu và điều kiện ngẫu nhiên. Có thể dùng ghi chú ngắn trong lúc chạy rồi hoàn thiện sau phiên.

### 12.4. Phân biệt dữ kiện và suy luận

Đánh dấu rõ phần nào là log/quan sát, phần nào là giả thuyết và phần nào đã được xác nhận bởi nhóm phát triển hoặc chủ sở hữu yêu cầu. Không gán nguyên nhân gốc khi chưa có phân tích đủ căn cứ.

### 12.5. Giữ liên kết và lịch sử

Dùng ID phiên, finding ID, requirement ID, risk ID và test case ID ổn định. Khi phát hiện được chuyển thành bug, giữ liên kết giữa bug và phiên khám phá gốc. Khi bug được sửa, liên kết lần chạy xác nhận sau sửa thay vì ghi đè kết quả ban đầu.

### 12.6. Bảo vệ dữ liệu và người dùng

Không ghi mật khẩu, token, khóa bí mật hoặc dữ liệu cá nhân không cần thiết. Với lỗi bảo mật, dùng quy trình báo cáo được phê duyệt và giới hạn người nhận. Video, ảnh chụp, file HAR và log cần được kiểm tra trước khi tải lên công cụ quản lý công việc.

## 13. Sử dụng ghi chép để cải thiện chiến lược kiểm thử

Ghi chép không chỉ phục vụ báo cáo lỗi của phiên hiện tại. Khi tổng hợp qua nhiều phiên, nhóm có thể phát hiện:

- Khu vực có nhiều phát hiện lặp lại hoặc nhiều giả định chưa được làm rõ.
- Loại dữ liệu, vai trò hoặc trạng thái thường bị bỏ sót.
- Môi trường hoặc phụ thuộc làm giảm khả năng tái hiện.
- Kiểm thử tự động còn thiếu ở những luồng có quy tắc ổn định.
- Rủi ro mới cần bổ sung vào kế hoạch kiểm thử.
- Hướng dẫn sử dụng hoặc nội dung sản phẩm gây nhầm lẫn cho người dùng.
- Khoảng trống giữa tiêu chí chấp nhận và hành vi thực tế.

Sau mỗi đợt, có thể nhóm phát hiện theo thành phần, nguyên nhân đã xác nhận, loại rủi ro, mức độ nghiêm trọng và giai đoạn phát hiện. Tránh chỉ đếm số bug; một phiên phát hiện nhiều lỗi nhỏ không nhất thiết có giá trị hơn một phiên xác nhận được một rủi ro nghiêm trọng đã được kiểm soát.

Kết quả tổng hợp có thể dẫn đến thay đổi trong charter, dữ liệu kiểm thử, môi trường, kiểm thử hồi quy, mục tiêu chất lượng hoặc quy trình refinement. Mỗi hành động cải tiến cần có chủ sở hữu và được đánh giá lại sau khi thực hiện.

## 14. Những sai lầm thường gặp

- **Chỉ ghi “đã kiểm tra” hoặc “không có lỗi”:** không cho biết phạm vi, điều kiện và bằng chứng.
- **Gộp giả thuyết với kết luận:** khiến người đọc hiểu suy đoán là sự thật đã xác nhận.
- **Ghi thao tác nhưng bỏ dữ liệu/trạng thái:** người khác không thể tái hiện cùng điều kiện.
- **Chỉ chụp ảnh lỗi mà không ghi bước trước đó:** thiếu trình tự và điều kiện kích hoạt.
- **Thu thập log/video không làm sạch:** có thể làm lộ token, cookie hoặc dữ liệu cá nhân.
- **Ghi mọi thao tác nhỏ:** tạo lượng ghi chú lớn nhưng khó tìm thông tin quan trọng.
- **Không ghi nhánh đã bỏ qua:** người đọc hiểu nhầm charter đã được hoàn thành toàn bộ.
- **Đánh dấu mọi bất thường là bug:** gây nhiễu backlog và che khuất câu hỏi yêu cầu hoặc lỗi môi trường.
- **Không ghi kết quả âm tính:** mất thông tin về giả thuyết đã được kiểm tra nhưng chưa được hỗ trợ.
- **Không giữ liên kết sau khi tạo bug:** mất bối cảnh khám phá và bằng chứng ban đầu.
- **Đánh giá người kiểm thử theo số bug:** khuyến khích ghi nhận số lượng thay vì chất lượng phát hiện và hiểu biết.
- **Không debrief:** các câu hỏi và hành động tiếp theo không được thống nhất hoặc giao chủ sở hữu.

## 15. Checklist ghi chép phiên khám phá

### Trước phiên

- [ ] Mục tiêu và phạm vi khám phá được xác định.
- [ ] Charter hoặc câu hỏi dẫn dắt đủ rõ.
- [ ] Giả thuyết có thể kiểm tra hoặc câu hỏi cần tìm hiểu được ghi lại.
- [ ] Phiên bản, môi trường, thiết bị và dữ liệu ban đầu được ghi nhận.
- [ ] Tài khoản và quyền thử nghiệm phù hợp; không dùng credential thật trong ghi chép.
- [ ] Giới hạn an toàn, dữ liệu và thời lượng được thống nhất.

### Trong phiên

- [ ] Thao tác quan trọng và dữ liệu được ghi theo trình tự.
- [ ] Quan sát được tách khỏi suy luận.
- [ ] Timestamp, trạng thái và điều kiện mạng được ghi khi có liên quan.
- [ ] Bằng chứng được liên kết với bước hoặc phát hiện tương ứng.
- [ ] Giả thuyết được đánh dấu hỗ trợ, bác bỏ hoặc chưa kết luận.
- [ ] Hướng khám phá thay đổi có lý do và được ghi lại.
- [ ] Thông tin nhạy cảm được tránh hoặc làm sạch.

### Sau phiên

- [ ] Phát hiện được phân loại đúng: bug, anomaly, risk, question, usability hoặc environment.
- [ ] Bug report có bước tái hiện, expected/actual result, môi trường và bằng chứng.
- [ ] Tác động và mức độ nghiêm trọng được mô tả có căn cứ.
- [ ] Yêu cầu, rủi ro và test condition liên quan được liên kết.
- [ ] Charter đã hoàn thành và phần chưa kiểm tra được nêu rõ.
- [ ] Debrief xác định hành động tiếp theo, owner và thời hạn.
- [ ] Artifact được lưu đúng nơi, có quyền truy cập và thời hạn lưu giữ phù hợp.

## Kết luận

Ghi chép giả thuyết, thao tác, bằng chứng và phát hiện giúp kiểm thử thủ công và khám phá tạo ra tri thức có thể tái dựng, kiểm chứng và sử dụng lại. Một phiên tốt nêu rõ mục tiêu, điều kiện, giả thuyết hoặc câu hỏi; ghi lại các thao tác quan trọng cùng quan sát khách quan; thu thập bằng chứng có ngữ cảnh; phân loại phát hiện và xác định hành động tiếp theo. Khi duy trì liên kết với yêu cầu, rủi ro và kiểm thử hồi quy, kết quả khám phá trở thành đầu vào có giá trị cho chiến lược kiểm thử và quyết định chất lượng.
