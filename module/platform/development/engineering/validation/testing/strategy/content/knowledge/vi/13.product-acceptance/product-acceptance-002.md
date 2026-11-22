# Thống nhất tiêu chí chấp nhận trước khi phát triển

Tiêu chí chấp nhận (acceptance criteria) mô tả những điều kiện mà một tính năng, thay đổi hoặc sản phẩm công việc phải đáp ứng để được xem là phù hợp với nhu cầu đã thống nhất. Chúng giúp chủ sản phẩm, người dùng đại diện, lập trình viên, QA và các bên liên quan hiểu cùng một kết quả cần đạt trước khi nhóm đầu tư công sức xây dựng.

Trong chiến lược kiểm thử xác thực (validation testing strategy), tiêu chí chấp nhận nối nhu cầu sử dụng với bằng chứng kiểm thử. Chúng trả lời câu hỏi: **Điều gì phải đúng để bên có thẩm quyền chấp nhận kết quả?** Nếu chỉ thống nhất tên tính năng hoặc mô tả ý tưởng chung, mỗi người có thể hiểu khác nhau về hành vi, trường hợp ngoại lệ và mức chất lượng cần đạt. Sự khác biệt thường chỉ lộ ra khi tính năng đã được triển khai, khiến việc sửa đổi tốn thời gian và làm tăng rủi ro.

Thống nhất tiêu chí trước khi phát triển giúp nhóm phát hiện điểm chưa rõ sớm, giới hạn phạm vi, thiết kế kiểm thử có mục tiêu và tránh tranh luận về kỳ vọng sau khi sản phẩm đã hoàn thành. Tiêu chí có thể được điều chỉnh khi hiểu biết thay đổi, nhưng mọi thay đổi cần được trao đổi và đánh giá tác động.

## 1. Tiêu chí chấp nhận là gì?

Tiêu chí chấp nhận là tập hợp các điều kiện có thể quan sát hoặc xác minh để quyết định một yêu cầu, câu chuyện người dùng hay tính năng đáp ứng nhu cầu đã thống nhất hay chưa. Chúng tập trung vào kết quả và hành vi cần có trong bối cảnh sử dụng.

Ví dụ, câu “người dùng có thể đặt lại mật khẩu” chưa đủ rõ để phát triển và kiểm thử. Một nhóm cần thống nhất thêm:

- Người dùng bắt đầu yêu cầu đặt lại mật khẩu bằng thông tin nào?
- Hệ thống phản hồi thế nào khi tài khoản tồn tại hoặc không tồn tại?
- Liên kết đặt lại có thời hạn bao lâu và chỉ sử dụng được mấy lần?
- Điều gì xảy ra khi liên kết hết hạn hoặc đã được sử dụng?
- Sau khi đặt lại thành công, phiên đăng nhập cũ được xử lý ra sao?
- Người dùng nhận được xác nhận bằng cách nào?

Các câu trả lời tạo nên điều kiện chấp nhận cụ thể. Nhờ vậy, nhóm có thể xây dựng các tình huống kiểm thử tương ứng và đánh giá kết quả dựa trên kỳ vọng đã thống nhất.

Tiêu chí chấp nhận nên mô tả:

- **Kết quả người dùng cần đạt:** Tác vụ hoặc mục tiêu nghiệp vụ được hỗ trợ.
- **Điều kiện áp dụng:** Vai trò, trạng thái ban đầu, dữ liệu và điều kiện liên quan.
- **Hành vi mong đợi:** Hệ thống phải phản hồi hoặc thay đổi trạng thái như thế nào.
- **Trường hợp ngoại lệ quan trọng:** Dữ liệu không hợp lệ, quyền không đủ, phụ thuộc lỗi hoặc thao tác lặp.
- **Cách xác minh:** Bằng chứng hoặc quan sát đủ để kết luận đạt hay không đạt.

Tiêu chí không cần mô tả mọi chi tiết triển khai nội bộ. Chúng cần đủ cụ thể để các bên thống nhất hành vi, đồng thời giữ không gian cho nhóm kỹ thuật lựa chọn giải pháp phù hợp.

## 2. Vì sao phải thống nhất trước khi phát triển?

Nếu kỳ vọng chỉ được làm rõ sau khi lập trình xong, nhóm có thể phát hiện rằng mình đã xây dựng đúng theo một cách hiểu nhưng sai với nhu cầu thực tế. Khi đó, thay đổi thường ảnh hưởng đến thiết kế, mã nguồn, dữ liệu, tài liệu, ca kiểm thử và lịch phát hành.

Thống nhất sớm đem lại các lợi ích sau:

1. **Tạo cách hiểu chung:** Chủ sản phẩm, người dùng đại diện, lập trình viên và QA có cùng định nghĩa về kết quả cần đạt.
2. **Làm lộ điểm mơ hồ:** Các câu hỏi về quy tắc, dữ liệu, quyền hạn và trường hợp biên được đặt ra trước khi trở thành lỗi.
3. **Hỗ trợ ước lượng và lập kế hoạch:** Nhóm hiểu rõ phạm vi và có thể nhận diện phụ thuộc hoặc công việc chưa được tính đến.
4. **Định hướng thiết kế và kiểm thử:** Lập trình viên biết hành vi cần xây dựng; QA có thể chuẩn bị tình huống và dữ liệu kiểm thử.
5. **Giảm thay đổi muộn:** Bất đồng về kỳ vọng được xử lý khi chi phí thay đổi còn thấp.
6. **Tạo căn cứ nghiệm thu:** Kết quả được đánh giá theo điều kiện đã thống nhất, thay vì cảm nhận chủ quan hoặc kỳ vọng xuất hiện vào phút cuối.

Ví dụ, nếu nhóm chỉ biết “áp dụng mã giảm giá”, họ có thể không tính đến việc mã đã hết hạn, không áp dụng cho một số sản phẩm, không được cộng dồn hoặc bị giới hạn theo khách hàng. Nếu các quy tắc này được thảo luận trước, nhóm có thể thiết kế dữ liệu, logic và kiểm thử ngay từ đầu.

## 3. Phân biệt tiêu chí chấp nhận với các khái niệm liên quan

Tiêu chí chấp nhận thường được dùng cùng yêu cầu, câu chuyện người dùng, ca kiểm thử và Definition of Done, nhưng mỗi khái niệm có mục đích riêng.

| Khái niệm | Câu hỏi trả lời | Ví dụ |
|---|---|---|
| Yêu cầu (requirement) | Sản phẩm hoặc hệ thống cần cung cấp điều gì? | Khách hàng có thể hủy đơn trước khi đơn được bàn giao cho đơn vị vận chuyển |
| Câu chuyện người dùng (user story) | Ai cần khả năng gì và vì sao? | Là khách hàng, tôi muốn hủy đơn đủ điều kiện để không phải nhận hàng không còn cần thiết |
| Tiêu chí chấp nhận | Điều kiện cụ thể nào chứng minh yêu cầu/câu chuyện đáp ứng nhu cầu? | Đơn ở trạng thái chờ xác nhận có thể hủy; hệ thống cập nhật trạng thái và hiển thị xác nhận |
| Ca kiểm thử (test case) | Thực hiện những bước nào với dữ liệu nào để kiểm tra tiêu chí? | Tạo đơn chờ xác nhận, chọn hủy, kiểm tra trạng thái và lịch sử đơn |
| Definition of Done (DoD) | Công việc cần đáp ứng những chuẩn hoàn thành chung nào? | Code được review, kiểm thử tự động đạt, tài liệu được cập nhật và không còn lỗi nghiêm trọng chưa xử lý |
| Tiêu chí kết thúc kiểm thử (test exit criteria) | Khi nào có đủ bằng chứng để kết thúc một giai đoạn kiểm thử? | Các kịch bản ưu tiên cao đã chạy và rủi ro còn lại được ghi nhận |

Tiêu chí chấp nhận thường gắn với một tính năng hoặc yêu cầu cụ thể. Definition of Done áp dụng chung cho nhiều hạng mục công việc trong nhóm. Ca kiểm thử chuyển tiêu chí thành cách thực hiện và bằng chứng cụ thể. Kết quả kiểm thử có thể hỗ trợ quyết định chấp nhận, nhưng quyết định cuối cùng vẫn thuộc về người có thẩm quyền theo quy trình.

## 4. Ai tham gia thống nhất tiêu chí?

Tiêu chí cần được xây dựng với sự tham gia của những người hiểu nhu cầu, quy tắc và khả năng thực hiện. Không nên giao toàn bộ việc viết tiêu chí cho một vai trò rồi yêu cầu các bên khác chỉ xác nhận vào cuối.

| Vai trò | Đóng góp chính |
|---|---|
| Chủ sản phẩm hoặc đại diện nghiệp vụ | Giải thích mục tiêu, ưu tiên, quy tắc nghiệp vụ và quyết định chấp nhận |
| Người dùng đại diện hoặc chuyên gia miền nghiệp vụ | Mô tả quy trình thực tế, khó khăn, ngoại lệ và kỳ vọng sử dụng |
| QA/tester | Đặt câu hỏi về tính kiểm chứng, trường hợp biên, dữ liệu và rủi ro |
| Lập trình viên | Đánh giá tính khả thi, phụ thuộc kỹ thuật, trạng thái hệ thống và tác động kiến trúc |
| UX/UI hoặc chuyên gia khả năng truy cập | Làm rõ hành vi tương tác, nội dung hiển thị và nhu cầu tiếp cận |
| Vận hành, bảo mật hoặc chuyên gia khác | Bổ sung điều kiện về độ tin cậy, quyền, dữ liệu, giám sát và tuân thủ khi liên quan |

Chủ sản phẩm hoặc người được ủy quyền chịu trách nhiệm làm rõ và chấp nhận quy tắc nghiệp vụ. QA giúp bảo đảm tiêu chí có thể kiểm tra và bao phủ rủi ro. Lập trình viên xác nhận cách hiểu có thể triển khai và nêu phụ thuộc. Người dùng đại diện giúp nhóm tránh xây dựng tiêu chí chỉ phản ánh góc nhìn nội bộ.

Một nhóm nhỏ có thể để một người đảm nhiệm nhiều vai trò, nhưng cần ghi rõ ai có quyền quyết định khi có bất đồng. Nếu tiêu chí ảnh hưởng đến bảo mật, tài chính, an toàn hoặc tuân thủ, cần mời đúng chuyên gia và người có thẩm quyền tham gia.

## 5. Quy trình thống nhất tiêu chí trước khi phát triển

Một quy trình thực tế có thể được tổ chức thành các bước sau:

1. **Xác định mục tiêu và người dùng:** Nêu vấn đề cần giải quyết, nhóm người dùng và kết quả nghiệp vụ mong muốn.
2. **Rà soát yêu cầu và phạm vi:** Xác định tính năng liên quan, điều kiện áp dụng, phụ thuộc và phần chưa nằm trong phạm vi.
3. **Phân tích luồng chính:** Mô tả hành trình thông thường từ trạng thái ban đầu đến kết quả mong muốn.
4. **Khám phá ngoại lệ và rủi ro:** Xem xét dữ liệu sai, thiếu quyền, thao tác lặp, timeout, trạng thái bất thường và tương tác với hệ thống khác.
5. **Viết tiêu chí có thể xác minh:** Dùng ngôn ngữ rõ ràng, có điều kiện và kết quả quan sát được.
6. **Rà soát khả thi và tính đầy đủ:** QA, lập trình viên và chuyên gia liên quan kiểm tra xem tiêu chí có mâu thuẫn, thiếu thông tin hoặc không thể kiểm chứng không.
7. **Thống nhất và ghi nhận:** Chủ sở hữu yêu cầu cùng các bên liên quan xác nhận phiên bản tiêu chí, giả định và điểm còn mở.
8. **Liên kết với thiết kế và kiểm thử:** Chuyển từng tiêu chí thành tình huống kiểm thử, dữ liệu, bằng chứng và trách nhiệm.
9. **Quản lý thay đổi:** Khi yêu cầu thay đổi, đánh giá tác động đến thiết kế, kiểm thử, lịch trình và các bên liên quan trước khi cập nhật tiêu chí.

Không nhất thiết cần một cuộc họp dài cho mỗi yêu cầu. Nhóm có thể trao đổi trong buổi refinement, phiên làm việc liên chức năng hoặc review tài liệu. Điều quan trọng là những người cần quyết định đều có cơ hội nêu câu hỏi và kết quả thống nhất được ghi lại.

## 6. Viết tiêu chí rõ ràng và có thể kiểm chứng

Một tiêu chí tốt cho phép hai người độc lập đọc và hiểu gần như cùng một điều kiện đạt. Hãy tránh những từ mơ hồ như “nhanh”, “thân thiện”, “hợp lý”, “đầy đủ”, “dễ dùng” hoặc “hoạt động tốt” nếu không có cách đánh giá cụ thể.

Ví dụ:

| Diễn đạt mơ hồ | Diễn đạt có thể kiểm chứng |
|---|---|
| Trang phải tải nhanh | Với điều kiện tải và môi trường đã thống nhất, thời gian phản hồi ở phân vị 95 không vượt quá ngưỡng được yêu cầu |
| Người dùng nhận thông báo phù hợp | Sau khi hủy đơn thành công, giao diện hiển thị xác nhận và đơn xuất hiện với trạng thái “Đã hủy” |
| Mã giảm giá phải hoạt động đúng | Mã còn hiệu lực, đủ điều kiện đơn hàng và chưa vượt giới hạn sử dụng được áp dụng đúng mức giảm đã công bố |
| Hệ thống phải an toàn | Người dùng không có quyền sở hữu đơn hàng không thể xem hoặc thay đổi đơn đó qua giao diện hoặc API |
| Báo lỗi dễ hiểu | Khi email không đúng định dạng, biểu mẫu nêu trường cần sửa và giữ lại các dữ liệu hợp lệ đã nhập |

Đối với chỉ số định lượng, phải nêu đơn vị, điều kiện đo, dữ liệu và cách tính. “Thời gian phản hồi dưới hai giây” cần làm rõ đo từ đâu đến đâu, ở tải nào, trên môi trường nào và áp dụng cho bao nhiêu phần trăm request. Nếu thiếu bối cảnh, một con số có vẻ cụ thể vẫn có thể dẫn đến cách hiểu khác nhau.

### 6.1. Dùng cấu trúc Given–When–Then

Với hành vi có điều kiện, cấu trúc Given–When–Then (Cho trước – Khi – Thì) giúp diễn đạt rõ trạng thái ban đầu, hành động và kết quả mong đợi.

```text
Given: Đơn hàng đang ở trạng thái "Chờ xác nhận"
       và khách hàng là chủ sở hữu đơn.
When:  Khách hàng yêu cầu hủy đơn.
Then:  Hệ thống chuyển đơn sang "Đã hủy",
       ghi nhận thời điểm hủy và hiển thị xác nhận.
```

Mỗi phần có vai trò:

- **Given:** Điều kiện, dữ liệu và trạng thái cần thiết trước hành động.
- **When:** Hành động hoặc sự kiện kích hoạt.
- **Then:** Kết quả có thể quan sát, bao gồm trạng thái, dữ liệu, phản hồi hoặc tác dụng phụ được phép.

Cấu trúc này đặc biệt hữu ích với quy tắc nghiệp vụ có nhiều trạng thái. Không nên nhồi nhiều hành vi độc lập vào một tiêu chí; hãy tách thành các kịch bản riêng để dễ hiểu và kiểm thử.

### 6.2. Viết theo kết quả, tránh áp đặt cách triển khai

Tiêu chí nên mô tả điều người dùng hoặc hệ thống cần quan sát được. Ví dụ, “khách hàng nhận được email xác nhận trong vòng một phút sau khi thanh toán thành công” mô tả kết quả. “Phải dùng thư viện X và lưu thông báo vào bảng Y” thường là quyết định triển khai, trừ khi có ràng buộc kỹ thuật đã được phê duyệt.

Tách kết quả mong muốn khỏi giải pháp giúp nhóm có thể lựa chọn thiết kế tốt hơn mà vẫn giữ nguyên kỳ vọng chất lượng. Nếu một công nghệ, giao thức hoặc cơ chế cụ thể là yêu cầu bắt buộc, hãy ghi nó thành ràng buộc kỹ thuật có căn cứ và liên kết với tiêu chí liên quan.

## 7. Bao phủ luồng chính, ngoại lệ và ranh giới

Tiêu chí chỉ mô tả luồng thành công thường chưa đủ. Nhóm cần xem xét cách hệ thống xử lý khi điều kiện thay đổi hoặc một bước không thể hoàn thành.

Với mỗi tính năng, hãy cân nhắc:

- **Luồng chính:** Người dùng thực hiện tác vụ trong điều kiện bình thường.
- **Dữ liệu không hợp lệ:** Thiếu trường, sai định dạng, vượt giới hạn hoặc không thuộc miền giá trị cho phép.
- **Giá trị biên:** Giá trị ngay dưới, tại và ngay trên giới hạn nghiệp vụ.
- **Quyền hạn:** Người dùng có vai trò khác nhau hoặc không có quyền thực hiện thao tác.
- **Trạng thái:** Hành động được thực hiện ở trạng thái hợp lệ và không hợp lệ.
- **Thao tác lặp hoặc đồng thời:** Nhấn nhiều lần, gửi lại request hoặc nhiều người cập nhật cùng dữ liệu.
- **Lỗi phụ thuộc:** Dịch vụ bên ngoài chậm, không sẵn sàng hoặc trả dữ liệu không mong đợi.
- **Khả năng phục hồi:** Hệ thống giữ dữ liệu, hoàn tác hoặc cho phép thử lại như thế nào.
- **Khả năng tiếp cận:** Người dùng có thể hoàn thành tác vụ bằng bàn phím, trình đọc màn hình hoặc phương thức tương tác được hỗ trợ không.

Không phải mọi tính năng đều cần tiêu chí riêng cho mọi trường hợp. Hãy chọn theo rủi ro và hậu quả nếu hành vi sai. Các tình huống có tác động tài chính, dữ liệu hoặc quyền truy cập cao cần được làm rõ trước khi phát triển.

## 8. Ví dụ: thống nhất tiêu chí cho chức năng hủy đơn

Giả sử câu chuyện người dùng là:

> Là khách hàng, tôi muốn hủy đơn hàng trước khi đơn được bàn giao cho đơn vị vận chuyển để không phải nhận hàng tôi không còn cần.

Sau khi thảo luận với chủ sản phẩm, QA và lập trình viên, nhóm có thể thống nhất các tiêu chí sau:

**AC-01 – Hủy đơn đủ điều kiện**

```text
Given: Đơn hàng thuộc về khách hàng hiện tại và đang ở trạng thái
       "Chờ xác nhận".
When:  Khách hàng chọn hủy đơn và xác nhận thao tác.
Then:  Đơn chuyển sang trạng thái "Đã hủy" và giao diện hiển thị
       kết quả hủy thành công.
```

**AC-02 – Không cho hủy đơn đã bàn giao**

```text
Given: Đơn hàng đã được bàn giao cho đơn vị vận chuyển.
When:  Khách hàng gửi yêu cầu hủy.
Then:  Hệ thống không thay đổi trạng thái đơn và thông báo
       rằng đơn không còn đủ điều kiện hủy theo chính sách.
```

**AC-03 – Không cho người khác hủy đơn**

```text
Given: Người dùng đã đăng nhập nhưng không sở hữu đơn hàng.
When:  Người dùng gửi yêu cầu hủy đơn đó qua giao diện hoặc API.
Then:  Hệ thống từ chối yêu cầu, không thay đổi đơn hàng
       và không tiết lộ thông tin nhạy cảm của chủ sở hữu.
```

**AC-04 – Ghi nhận lịch sử hủy**

```text
Given: Đơn hàng được hủy thành công.
When:  Hệ thống hoàn tất xử lý yêu cầu hủy.
Then:  Lịch sử đơn ghi nhận thời điểm, nguồn yêu cầu
       và trạng thái mới theo chính sách lưu vết.
```

Nhóm cũng cần làm rõ các câu hỏi trước khi bắt đầu: đơn đã thanh toán thì hoàn tiền tự động hay cần quy trình riêng? Nếu kho đã giữ hàng thì khi nào giải phóng tồn kho? Nếu hai yêu cầu hủy đến gần như đồng thời thì kết quả nào được coi là hợp lệ? Thông báo được gửi qua kênh nào? Các câu hỏi này có thể trở thành tiêu chí bổ sung nếu nằm trong phạm vi tính năng.

Từ tiêu chí trên, QA có thể tạo ca kiểm thử cho khách hàng đúng chủ sở hữu, người dùng khác, các trạng thái đơn, thao tác lặp và kết quả lưu vết. Lập trình viên có thể thiết kế chuyển trạng thái và kiểm soát quyền. Chủ sản phẩm có căn cứ để xác nhận tính năng đáp ứng chính sách.

## 9. Bao gồm yêu cầu phi chức năng trong tiêu chí chấp nhận

Tiêu chí chấp nhận không chỉ dành cho chức năng. Khi phù hợp, cần đưa các thuộc tính chất lượng quan trọng vào điều kiện nghiệm thu hoặc liên kết đến tiêu chuẩn chất lượng áp dụng chung.

Các nhóm thường cần xem xét:

| Thuộc tính | Ví dụ tiêu chí có thể xác minh |
|---|---|
| Hiệu năng | Với tải và cấu hình đã thống nhất, phân vị 95 của thời gian phản hồi không vượt ngưỡng yêu cầu |
| Bảo mật | Người dùng không có quyền không thể truy cập dữ liệu ngoài phạm vi được cấp; các thao tác nhạy cảm được ghi nhận theo chính sách |
| Khả năng truy cập | Các thao tác cốt lõi có thể thực hiện bằng bàn phím và thành phần giao diện có tên/nhãn phù hợp cho công nghệ hỗ trợ |
| Tương thích | Luồng quan trọng hoạt động trên các trình duyệt và thiết bị thuộc danh sách hỗ trợ |
| Độ tin cậy | Khi một phụ thuộc tạm thời không sẵn sàng, hệ thống phản hồi theo quy tắc lỗi và có thể phục hồi mà không tạo tác dụng phụ trùng lặp |
| Khả năng quan sát | Lỗi của luồng nghiệp vụ có thể được truy vết bằng mã tương quan và metric cần thiết |
| Quyền riêng tư | Dữ liệu cá nhân được xử lý, hiển thị và lưu trữ theo mục đích và chính sách đã thống nhất |

Với yêu cầu áp dụng chung cho nhiều tính năng, có thể tham chiếu một chuẩn chất lượng hoặc Definition of Done thay vì sao chép cùng một tiêu chí vào từng câu chuyện. Tuy nhiên, các rủi ro đặc thù của tính năng vẫn cần tiêu chí riêng.

## 10. Kiểm tra chất lượng của tiêu chí chấp nhận

Trước khi thống nhất, nhóm nên tự kiểm tra tiêu chí bằng các câu hỏi:

- **Rõ ràng:** Người đọc có hiểu cùng một điều kiện và kết quả không?
- **Có thể kiểm chứng:** Có thể xác định đạt hoặc không đạt bằng quan sát, dữ liệu hay bằng chứng không?
- **Đầy đủ theo rủi ro:** Luồng chính và các ngoại lệ quan trọng đã được xem xét chưa?
- **Nhất quán:** Các tiêu chí có mâu thuẫn với nhau, với yêu cầu khác hoặc với chính sách nghiệp vụ không?
- **Khả thi:** Nhóm có thể xây dựng và kiểm tra trong phạm vi nguồn lực, môi trường và phụ thuộc hiện có không?
- **Độc lập vừa đủ:** Mỗi tiêu chí có mô tả một kết quả có thể đánh giá riêng, không trộn nhiều hành vi không liên quan không?
- **Có thể truy vết:** Tiêu chí liên kết được với nhu cầu, câu chuyện, rủi ro và ca kiểm thử tương ứng không?
- **Có chủ sở hữu:** Ai giải thích và quyết định khi có cách hiểu khác nhau?

Một tiêu chí không thể kiểm chứng cần được làm rõ trước khi phát triển hoặc được ghi nhận như một giả định/rủi ro có người chịu trách nhiệm. Không nên giữ lại câu mơ hồ chỉ để đánh dấu yêu cầu đã hoàn thành.

## 11. Liên kết tiêu chí với yêu cầu, rủi ro và kiểm thử

Tiêu chí chấp nhận tạo ra một điểm nối giữa mục tiêu sản phẩm và hoạt động xác minh. Nhóm có thể duy trì liên kết đơn giản như sau:

| Nhu cầu hoặc rủi ro | Tiêu chí | Bằng chứng/kiểm thử | Người xác nhận |
|---|---|---|---|
| Khách hàng hủy được đơn còn đủ điều kiện | AC-01 | Kiểm thử trạng thái hợp lệ và giao diện xác nhận | Chủ sản phẩm, QA |
| Đơn đã bàn giao không bị hủy sai | AC-02 | Kiểm thử trạng thái biên và kiểm tra dữ liệu đơn | Chủ sản phẩm, QA |
| Không thể hủy đơn của người khác | AC-03 | Kiểm thử phân quyền ở giao diện và API | QA, chuyên gia bảo mật |
| Có thể truy vết việc hủy | AC-04 | Kiểm tra lịch sử và log theo chính sách | QA, vận hành/nghiệp vụ |

Liên kết giúp nhóm biết mỗi tiêu chí đã có bằng chứng hay chưa và tác động khi tiêu chí thay đổi. Nếu một yêu cầu có nhiều tiêu chí, cần bảo đảm mọi tiêu chí quan trọng được kiểm tra. Nếu một ca kiểm thử xác nhận nhiều tiêu chí, báo cáo cần thể hiện rõ kết quả cho từng điều kiện.

Không nên dùng số lượng ca kiểm thử làm đại diện duy nhất cho mức độ bao phủ. Điều quan trọng là mỗi tiêu chí và rủi ro quan trọng có bằng chứng phù hợp, trong điều kiện có thể giải thích và tái hiện.

## 12. Quản lý thay đổi tiêu chí sau khi đã thống nhất

Yêu cầu có thể thay đổi do phản hồi người dùng, điều chỉnh chính sách, phát hiện rủi ro hoặc giới hạn kỹ thuật mới. Khi đó, tiêu chí chấp nhận cần được cập nhật có kiểm soát.

Quy trình thay đổi nên gồm:

1. Ghi nhận lý do và người đề xuất thay đổi.
2. Xác định tiêu chí, yêu cầu và nhóm người dùng bị ảnh hưởng.
3. Đánh giá tác động đến thiết kế, mã nguồn, dữ liệu, ca kiểm thử, ước lượng và lịch phát hành.
4. Trao đổi với chủ sở hữu nghiệp vụ, QA, lập trình viên và các chuyên gia liên quan.
5. Cập nhật phiên bản tiêu chí và thông báo cho những người đang thực hiện công việc.
6. Xác nhận lại bằng chứng hoặc kế hoạch kiểm thử nếu phạm vi thay đổi.

Không nên âm thầm thay đổi điều kiện nghiệm thu sau khi nhóm đã bắt đầu phát triển. Nếu tiêu chí mới làm tăng phạm vi hoặc thay đổi hành vi, nhóm cần điều chỉnh kế hoạch và thống nhất lại thứ tự ưu tiên.

Khi một tiêu chí được nới lỏng vì giới hạn thời gian, hãy ghi rõ phần rủi ro được chấp nhận, người chấp nhận và kế hoạch xử lý sau đó. Việc giảm tiêu chuẩn không được che giấu dưới dạng “đã đạt” nếu bằng chứng không còn đáp ứng kỳ vọng ban đầu.

## 13. Điều kiện sẵn sàng để bắt đầu phát triển

Một nhóm có thể dùng tiêu chí chấp nhận như một phần của Definition of Ready hoặc checklist refinement. Trước khi đưa hạng mục vào phát triển, nên xác nhận:

- Mục tiêu và người dùng liên quan đã rõ.
- Phạm vi và các phụ thuộc quan trọng đã được nhận diện.
- Tiêu chí chấp nhận đã được viết và thống nhất với chủ sở hữu.
- Các câu hỏi nghiệp vụ quan trọng đã được giải đáp hoặc có người chịu trách nhiệm và thời hạn.
- Rủi ro chính và yêu cầu phi chức năng liên quan đã được xem xét.
- Nhóm hiểu cách xác minh kết quả và có thể chuẩn bị dữ liệu/môi trường cần thiết.
- Kích thước công việc đủ rõ để ước lượng và đưa vào kế hoạch.

Definition of Ready là thực hành của nhóm, không phải quy tắc bắt buộc áp dụng giống nhau cho mọi phương pháp. Với công việc khám phá hoặc thử nghiệm ý tưởng, nhóm có thể chấp nhận một số điểm chưa rõ, miễn là mục tiêu học hỏi, giới hạn và điều kiện quyết định được ghi nhận.

## 14. Những sai lầm thường gặp

- **Viết tiêu chí sau khi phát triển:** Nhóm mất cơ hội phát hiện khác biệt về kỳ vọng trước khi chi phí thay đổi tăng lên.
- **Dùng câu chung chung:** “Hoạt động tốt” hoặc “dễ sử dụng” không cho biết bằng chứng nào là đủ.
- **Chỉ mô tả luồng thành công:** Bỏ qua dữ liệu sai, quyền hạn, trạng thái bất thường và lỗi phụ thuộc.
- **Để một vai trò tự quyết định:** Thiếu góc nhìn QA, kỹ thuật hoặc người dùng có thể tạo ra tiêu chí không đầy đủ.
- **Mô tả giải pháp thay cho kết quả:** Ràng buộc triển khai quá sớm có thể làm giảm lựa chọn kỹ thuật mà không tăng giá trị nghiệm thu.
- **Bỏ qua phi chức năng:** Tính đúng chức năng không bảo đảm sản phẩm đáp ứng hiệu năng, bảo mật, khả năng truy cập hoặc độ tin cậy.
- **Trộn nhiều hành vi vào một tiêu chí:** Khó xác định phần nào đạt và phần nào không đạt.
- **Không ghi chủ sở hữu và giả định:** Khi có bất đồng, nhóm không biết ai quyết định hoặc điều kiện nào cần xác minh.
- **Thay đổi tiêu chí không thông báo:** QA và lập trình viên có thể tiếp tục làm theo phiên bản cũ.
- **Coi tiêu chí đạt là bằng chứng chất lượng toàn diện:** Tiêu chí chỉ bao phủ những điều đã thống nhất; nhóm vẫn cần đánh giá rủi ro và phần chưa được kiểm thử.

## 15. Checklist thống nhất tiêu chí trước khi phát triển

Trước khi chuyển một hạng mục sang phát triển, nhóm có thể sử dụng checklist sau:

- [ ] Mục tiêu người dùng và kết quả nghiệp vụ được mô tả rõ.
- [ ] Phạm vi, vai trò và điều kiện ban đầu đã được xác định.
- [ ] Luồng chính và các trường hợp ngoại lệ quan trọng đã được xem xét.
- [ ] Mỗi tiêu chí có kết quả quan sát được và cách xác minh.
- [ ] Các ngưỡng định lượng có đơn vị, điều kiện đo và phạm vi áp dụng.
- [ ] Yêu cầu phi chức năng và rủi ro đặc thù đã được xem xét.
- [ ] QA và lập trình viên đã rà soát tính kiểm chứng và tính khả thi.
- [ ] Chủ sản phẩm hoặc người có thẩm quyền đã xác nhận quy tắc nghiệp vụ.
- [ ] Các giả định, phụ thuộc và câu hỏi còn mở có người phụ trách.
- [ ] Tiêu chí được liên kết với yêu cầu, rủi ro và kế hoạch kiểm thử.
- [ ] Quy trình cập nhật tiêu chí khi có thay đổi đã rõ.

Thống nhất tiêu chí chấp nhận trước khi phát triển giúp nhóm chuyển kỳ vọng thành điều kiện có thể kiểm chứng. Khi người dùng, chủ sản phẩm, QA và lập trình viên cùng làm rõ kết quả, ngoại lệ và bằng chứng cần có, nhóm giảm hiểu nhầm, thiết kế kiểm thử sớm và đưa ra quyết định chấp nhận dựa trên những điều đã được thống nhất.
