# Ghi lại câu hỏi chưa rõ, quyết định cần xác nhận và tiêu chí chấp nhận

## Mục tiêu bài học

Sau bài này, bạn có thể biến những điểm chưa rõ trong yêu cầu nghiệp vụ thành câu hỏi có người chịu trách nhiệm và thời hạn xử lý; ghi lại quyết định thiết kế cùng lý do và hệ quả; đồng thời viết tiêu chí chấp nhận đủ cụ thể để kiểm tra mô hình dữ liệu có đáp ứng nhu cầu hay không.

Trong phân tích dữ liệu, việc ghi chép này giúp tránh biến giả định thành sự thật, tránh để những lựa chọn quan trọng chỉ tồn tại trong trao đổi miệng, và tạo đường liên kết từ yêu cầu đến mô hình, triển khai và kiểm thử.

## 1. Vì sao phải ghi lại điều chưa rõ?

Yêu cầu nghiệp vụ thường bắt đầu bằng những câu như:

- Khách hàng có thể đặt hàng.
- Một đơn hàng có nhiều sản phẩm.
- Hệ thống lưu lịch sử thanh toán.
- Người dùng có thể cập nhật thông tin liên hệ.

Các câu này gợi ý phạm vi nhưng chưa đủ để thiết kế dữ liệu. Chúng chưa nói rõ khách hàng có cần tài khoản không, một đơn hàng có thể giao thành nhiều đợt không, thanh toán thất bại được ghi nhận thế nào, hay lịch sử liên hệ phải được giữ trong bao lâu.

Nếu người phân tích tự điền câu trả lời còn thiếu, mô hình sẽ chứa những giả định không được xác nhận. Khi nghiệp vụ phát hiện khác biệt, nhóm có thể phải thay đổi quan hệ, khóa, vòng đời bản ghi, dữ liệu lịch sử hoặc cả API đã tích hợp.

Vì vậy, mỗi điểm chưa rõ cần được ghi nhận như một mục có thể theo dõi. Một mục tốt cho biết:

- điều gì chưa rõ;
- vì sao câu trả lời ảnh hưởng đến mô hình hoặc quy trình;
- ai có thẩm quyền xác nhận;
- cần câu trả lời vào lúc nào;
- tình trạng hiện tại và bằng chứng đã có;
- quyết định hoặc phần mô hình nào phụ thuộc vào câu trả lời.

Ghi lại câu hỏi không làm chậm việc phân tích. Nó giúp nhóm biết phần nào có thể tiếp tục và phần nào đang phụ thuộc vào xác nhận.

## 2. Phân biệt câu hỏi, giả định và quyết định

Ba loại thông tin này thường bị trộn lẫn, nhưng chúng có ý nghĩa khác nhau.

| Loại | Ý nghĩa | Cách xử lý |
|---|---|---|
| Câu hỏi chưa rõ (open question) | Chưa đủ thông tin để kết luận | Giao người xác nhận, thời hạn và ghi tác động |
| Giả định (assumption) | Tạm coi một điều là đúng để có thể phân tích tiếp | Ghi rõ căn cứ, rủi ro và điều kiện cần kiểm chứng |
| Quyết định (decision) | Lựa chọn đã được người có thẩm quyền chấp thuận | Ghi lựa chọn, lý do, người quyết định và hệ quả |

Ví dụ: yêu cầu nói “khách hàng có thể đặt hàng”. Nhóm chưa biết người mua có cần tài khoản hay không. Đây là **câu hỏi**. Để phác thảo mô hình, nhóm tạm giả định khách có thể mua không cần đăng nhập. Đây là **giả định**. Sau khi chủ sản phẩm xác nhận cho phép mua khách, nhóm ghi nhận việc liên kết đơn hàng với tài khoản là tùy chọn. Đây là **quyết định**.

Không được ghi một giả định thành quyết định đã được duyệt. Nếu chưa có người có thẩm quyền xác nhận, trạng thái phải thể hiện điều đó.

### 2.1. Khi nào một điểm là câu hỏi?

Hãy tạo câu hỏi khi có ít nhất một trong các dấu hiệu:

- Yêu cầu dùng từ mơ hồ như “nhanh”, “khách hàng”, “lịch sử”, “đã xử lý”.
- Hai bên liên quan diễn giải cùng một thuật ngữ khác nhau.
- Chưa rõ một quan hệ là bắt buộc hay tùy chọn.
- Chưa rõ một thuộc tính có thể thay đổi hay phải giữ nguyên theo thời gian.
- Chưa rõ nguồn nào có thẩm quyền khi dữ liệu xung đột.
- Có nhiều cách thiết kế dẫn đến chi phí, rủi ro hoặc hành vi khác nhau.
- Quy tắc ngoại lệ, hủy, hoàn tiền, xóa hoặc lưu trữ chưa được mô tả.

### 2.2. Khi nào nên ghi giả định?

Giả định hữu ích khi nhóm cần tiếp tục làm việc trước khi có câu trả lời. Mỗi giả định nên có:

- mã định danh;
- nội dung giả định;
- lý do tạm dùng;
- mức độ tin cậy;
- ảnh hưởng nếu giả định sai;
- người cần xác nhận;
- thời điểm phải kiểm tra lại.

Ví dụ: “Tạm giả định mã sản phẩm do hệ thống danh mục cấp và không được tái sử dụng sau khi sản phẩm ngừng kinh doanh.” Giả định này ảnh hưởng đến khóa, tham chiếu lịch sử và việc nhập dữ liệu từ đối tác.

Nếu giả định có rủi ro cao, không nên dùng nó để chốt thiết kế khó đảo ngược. Hãy giữ phần thiết kế đó ở trạng thái đề xuất hoặc tạo phương án có thể thay đổi sau.

### 2.3. Khi nào trở thành quyết định?

Một quyết định chỉ được ghi là đã xác nhận khi có người hoặc vai trò có thẩm quyền chấp thuận. Bản ghi cần cho biết quyết định áp dụng trong phạm vi nào và có hiệu lực từ khi nào.

Quyết định có thể được xem xét lại khi nghiệp vụ, quy mô, quy định pháp lý hoặc workload thay đổi. Việc thay đổi quyết định cần tạo phiên bản hoặc bản ghi mới và liên kết với quyết định cũ; không nên âm thầm sửa lịch sử khiến người đọc không biết vì sao mô hình đã đổi.

## 3. Cách viết một câu hỏi chưa rõ có thể xử lý được

Câu hỏi tốt phải cụ thể, trung lập và hướng đến một câu trả lời có thể tác động đến thiết kế.

Thay vì ghi “Cần làm rõ khách hàng”, hãy tách thành các câu hỏi nhỏ:

- Người mua có bắt buộc phải có tài khoản đăng nhập không?
- Một tổ chức có thể có nhiều người đặt hàng thay mặt tổ chức không?
- Một người có thể liên kết nhiều tài khoản không?
- Đơn hàng có cần giữ thông tin người nhận độc lập với hồ sơ khách hàng không?

Mỗi câu hỏi chỉ nên tập trung vào một vấn đề. Nếu một câu có nhiều ý và có thể nhận các câu trả lời khác nhau, hãy tách nó thành nhiều mục.

### 3.1. Các trường thông tin của question log

Một **question log** là danh sách câu hỏi chưa được giải quyết. Các trường thường hữu ích:

| Trường | Nội dung |
|---|---|
| ID | Mã ổn định như Q-001 |
| Câu hỏi | Vấn đề cần xác nhận, viết thành câu rõ nghĩa |
| Bối cảnh | Yêu cầu, cuộc trao đổi hoặc tình huống dẫn đến câu hỏi |
| Tác động | Thực thể, thuộc tính, quan hệ, quy tắc hoặc luồng bị ảnh hưởng |
| Mức ưu tiên | Mức ảnh hưởng nếu chưa có câu trả lời |
| Người xác nhận | Vai trò hoặc cá nhân có quyền quyết định |
| Hạn trả lời | Thời điểm cần có câu trả lời |
| Trạng thái | Open, In review, Answered, Deferred hoặc Rejected |
| Câu trả lời/bằng chứng | Nội dung được xác nhận và nguồn tham chiếu |
| Liên kết | Decision ID, requirement ID hoặc model element liên quan |

Không nhất thiết phải có một công cụ chuyên biệt. Một bảng trong tài liệu dự án cũng được, miễn là có người cập nhật, lịch sử thay đổi và đường liên kết đến quyết định.

### 3.2. Ví dụ question log cho hệ thống bán hàng

Các dòng sau là ví dụ minh họa; câu trả lời chưa được xác nhận không được xem là chính sách của một hệ thống thực tế.

| ID | Câu hỏi chưa rõ | Tác động đến dữ liệu | Ưu tiên | Người xác nhận | Trạng thái ví dụ |
|---|---|---|---|---|---|
| Q-001 | Người mua có thể đặt hàng khi chưa có tài khoản không? | Liên kết Order–Customer/Account, tính tùy chọn của account | Cao | Chủ sản phẩm | Open |
| Q-002 | Một đơn hàng có thể được giao thành nhiều đợt không? | Quan hệ Order–Shipment và vòng đời giao hàng | Cao | Vận hành kho | Open |
| Q-003 | Đơn giá được chốt khi tạo đơn hay khi xác nhận thanh toán? | Thuộc tính snapshot giá và thời điểm hiệu lực | Cao | Kinh doanh/Kế toán | In review |
| Q-004 | Một đơn hàng có cho phép thanh toán một phần hoặc nhiều lần thử không? | Quan hệ Order–Payment, số tiền và trạng thái | Cao | Kế toán | Open |
| Q-005 | Địa chỉ cũ có cần truy xuất sau khi khách cập nhật không? | Lưu lịch sử, valid time và retention | Trung bình | Chủ dữ liệu khách hàng | Open |

Mục “tác động” rất quan trọng. Nó giúp người xác nhận hiểu vì sao câu hỏi cần được trả lời và giúp kỹ sư biết phần nào đang chờ.

### 3.3. Ưu tiên câu hỏi theo rủi ro

Không phải câu hỏi nào cũng cần được giải quyết ngay. Có thể ưu tiên dựa trên:

- **Mức ảnh hưởng:** nếu trả lời khác đi, mô hình thay đổi nhiều đến đâu?
- **Khả năng xảy ra:** tình huống đó có thường gặp không?
- **Chi phí sửa muộn:** phải di chuyển dữ liệu, đổi API hay sửa tích hợp không?
- **Mức độ phụ thuộc:** có bao nhiêu quyết định khác đang chờ câu trả lời?
- **Thời hạn:** có chặn mốc thiết kế, phát triển hoặc nghiệm thu không?

Câu hỏi liên quan định danh, cardinality, lịch sử, quyền truy cập và vòng đời thường có chi phí sửa muộn cao. Câu hỏi về nhãn hiển thị có thể ít ảnh hưởng hơn, tùy hệ thống.

Hãy dùng mức ưu tiên nhất quán, chẳng hạn Critical/High/Medium/Low, và định nghĩa ý nghĩa của từng mức trong nhóm. Không dùng nhãn ưu tiên chỉ để tạo cảm giác khẩn cấp.

## 4. Ghi lại quyết định cần xác nhận

Khi câu hỏi đã có câu trả lời, nhóm cần ghi lại lựa chọn và hệ quả. Trong thiết kế dữ liệu, quyết định thường ảnh hưởng đến:

- ranh giới giữa các thực thể;
- định danh và khóa;
- cardinality và optionality;
- thuộc tính gốc, thuộc tính dẫn xuất và dữ liệu snapshot;
- cách lưu trạng thái và lịch sử;
- nguồn dữ liệu chuẩn;
- cách đồng bộ và xử lý xung đột;
- kiểu lưu trữ hoặc cách truy vấn.

### 4.1. Nội dung của decision record

Một **decision record** nên có các phần sau:

1. **ID và tiêu đề:** mã duy nhất, mô tả ngắn lựa chọn.
2. **Bối cảnh:** yêu cầu, vấn đề hoặc câu hỏi dẫn đến quyết định.
3. **Trạng thái:** Proposed, Approved, Rejected, Superseded hoặc Deferred.
4. **Các phương án:** lựa chọn đã xem xét, kể cả phương án giữ nguyên hiện trạng.
5. **Lựa chọn:** phương án được chọn hoặc đề xuất.
6. **Lý do:** quy tắc nghiệp vụ, dữ liệu, workload và bằng chứng hỗ trợ.
7. **Hệ quả:** ảnh hưởng đến mô hình, ứng dụng, vận hành, dữ liệu cũ và tích hợp.
8. **Người phê duyệt và ngày:** ai xác nhận, thời điểm nào.
9. **Điều kiện xem xét lại:** sự kiện hoặc ngưỡng khiến quyết định cần đánh giá lại.
10. **Liên kết:** các question ID, requirement ID, model element và acceptance criteria liên quan.

Ghi cả phương án bị loại và lý do giúp người đọc sau này không lặp lại cùng một cuộc tranh luận mà thiếu bối cảnh.

### 4.2. Ví dụ decision record

**D-001 — Tách tài khoản đăng nhập khỏi hồ sơ người mua**

- **Bối cảnh:** Q-001 hỏi liệu khách có thể đặt hàng khi chưa đăng nhập.
- **Trạng thái ví dụ:** Proposed, chờ chủ sản phẩm phê duyệt.
- **Phương án A:** bắt buộc mọi người mua có một Account.
- **Phương án B:** Buyer/Customer là khái niệm nghiệp vụ; liên kết Account có thể tùy chọn.
- **Lựa chọn đề xuất:** Phương án B.
- **Lý do:** hỗ trợ mua khách; vai trò đăng nhập và vai trò mua hàng có vòng đời khác nhau.
- **Hệ quả:** đơn hàng có thể lưu thông tin liên hệ của người mua và tham chiếu Account khi có; không dùng account ID làm định danh duy nhất của mọi người mua.
- **Cần xác nhận:** chủ sản phẩm xác nhận chính sách mua khách và quy tắc hợp nhất hồ sơ khi người mua đăng ký sau.
- **Xem xét lại khi:** cửa hàng chuyển sang mô hình chỉ bán cho thành viên hoặc thay đổi yêu cầu nhận diện khách hàng.

Đây là quyết định đề xuất, chưa phải quyết định đã duyệt. Trong tài liệu dự án thật, cần thay phần trạng thái và lựa chọn bằng thông tin đã được người có thẩm quyền xác nhận.

### 4.3. Ghi hệ quả, không chỉ ghi phương án

Một quyết định chỉ ghi “dùng UUID” hoặc “chọn document database” không đủ để người khác hiểu.

Ví dụ quyết định dùng UUID cần làm rõ:

- UUID được cấp ở dịch vụ nào?
- Có yêu cầu sinh ID trước khi ghi database không?
- ID có xuất hiện trong API công khai không?
- Có cần giữ mã nghiệp vụ dễ đọc riêng không?
- Hệ thống cũ đang dùng ID dạng nào và sẽ chuyển đổi ra sao?

Tương tự, quyết định nhúng `items` trong document cần làm rõ giới hạn kích thước, tần suất cập nhật, nhu cầu truy vấn độc lập từng dòng hàng và cách xử lý khi một đơn hàng có rất nhiều dòng.

### 4.4. Quyết định có thể được thay thế

Khi bối cảnh thay đổi, một quyết định cũ có thể bị thay thế. Hãy ghi:

- quyết định mới thay thế quyết định nào;
- lý do thay đổi;
- dữ liệu và thành phần bị ảnh hưởng;
- kế hoạch chuyển đổi;
- thời điểm bắt đầu áp dụng;
- cách xử lý dữ liệu được tạo theo quy tắc cũ.

Không xóa quyết định cũ khỏi lịch sử. Lịch sử quyết định giúp giải thích vì sao dữ liệu trong hai giai đoạn có cấu trúc khác nhau.

## 5. Viết tiêu chí chấp nhận có thể kiểm chứng

**Tiêu chí chấp nhận (acceptance criteria)** mô tả điều kiện quan sát được để xác nhận một yêu cầu hoặc kết quả thiết kế đáp ứng nhu cầu nghiệp vụ.

Tiêu chí cần trả lời: “Cần quan sát điều gì để biết yêu cầu này đã được đáp ứng?” Nó không nên chỉ nói “hệ thống hoạt động tốt”, “dữ liệu hợp lệ” hoặc “truy vấn nhanh”.

Một tiêu chí tốt thường:

- cụ thể và đơn nghĩa;
- có thể quan sát hoặc đo lường;
- có thể kiểm thử bằng dữ liệu và tình huống xác định;
- gắn với một yêu cầu hoặc quyết định;
- mô tả kết quả mong đợi, không áp đặt chi tiết triển khai khi chưa cần;
- bao gồm tình huống bình thường, biên và lỗi quan trọng.

### 5.1. Phân biệt acceptance criteria và implementation detail

Yêu cầu: “Giữ đúng giá của đơn hàng cũ khi giá danh mục thay đổi.”

Tiêu chí chấp nhận có thể là:

> Khi đơn hàng đã được xác nhận ở mức giá 850.000 VND cho một sản phẩm, sau đó giá danh mục thay đổi thành 900.000 VND, việc xem lại đơn hàng cũ vẫn hiển thị đơn giá 850.000 VND và mã tiền tệ VND.

Đây là hành vi có thể kiểm chứng. Nó không bắt buộc phải lưu ở cột tên `unit_price`, trong bảng quan hệ hay trong một document. Những lựa chọn đó thuộc thiết kế mô hình và triển khai.

Một yêu cầu kỹ thuật cụ thể có thể cần thiết khi có ràng buộc kiến trúc hoặc vận hành, nhưng không nên biến lựa chọn triển khai thành tiêu chí nghiệp vụ nếu người dùng chỉ quan tâm đến kết quả.

### 5.2. Mẫu Given–When–Then

Có thể viết tiêu chí theo cấu trúc:

- **Given (Với điều kiện):** bối cảnh và dữ liệu ban đầu.
- **When (Khi):** hành động hoặc sự kiện xảy ra.
- **Then (Thì):** kết quả có thể quan sát và xác minh.

Ví dụ:

```gherkin
Feature: Lưu giá tại thời điểm đặt hàng

Scenario: Giá danh mục thay đổi sau khi đơn hàng được xác nhận
  Given sản phẩm P-20 có giá 850000 VND
  And khách hàng tạo đơn hàng với số lượng 2
  When đơn hàng được xác nhận
  And giá danh mục của P-20 đổi thành 900000 VND
  Then đơn hàng cũ vẫn hiển thị đơn giá 850000 VND
  And tổng tiền dòng hàng vẫn được tính theo giá đã chốt
  And đơn vị tiền tệ của dòng hàng vẫn là VND
```

Scenario này chỉ có ý nghĩa khi chính sách chốt giá đã được xác nhận. Nếu chưa biết giá được chốt ở thời điểm tạo đơn hay xác nhận thanh toán, hãy giữ câu hỏi mở thay vì viết tiêu chí như thể quyết định đã có.

## 6. Tiêu chí chấp nhận dành cho mô hình dữ liệu

Tiêu chí chấp nhận của mô hình dữ liệu cần bao quát ngữ nghĩa, cấu trúc, quan hệ, quy tắc và cách sử dụng dữ liệu. Không chỉ kiểm tra database có tạo bảng thành công.

### 6.1. Định danh và tính duy nhất

Xác định:

- mỗi đối tượng cần được nhận diện bằng gì;
- định danh duy nhất trong phạm vi nào;
- mã có thể thay đổi hoặc tái sử dụng không;
- có cần đối chiếu ID giữa nhiều hệ thống không;
- dữ liệu trùng được phát hiện và xử lý thế nào.

Ví dụ tiêu chí: “Khi hai yêu cầu tạo khách hàng có cùng mã định danh bên ngoài trong cùng một tenant, hệ thống không tạo hai hồ sơ tương ứng; kết quả phải tham chiếu cùng một hồ sơ hoặc trả lỗi xung đột theo quy tắc đã thống nhất.”

### 6.2. Quan hệ, cardinality và optionality

Với mỗi quan hệ, ghi rõ:

- một-một, một-nhiều hay nhiều-nhiều;
- đầu nào bắt buộc;
- có thể tồn tại bản ghi chưa liên kết không;
- khi xóa hoặc ngừng hoạt động một phía thì phía còn lại xử lý ra sao.

Ví dụ: “Mỗi Order đã được tiếp nhận phải có đúng một chủ thể mua hàng. Account có thể vắng mặt đối với đơn mua khách. Mỗi OrderItem phải thuộc về một Order đang được quản lý.”

### 6.3. Thuộc tính, miền giá trị và đơn vị

Xác định kiểu, miền giá trị, độ chính xác, đơn vị và tính tùy chọn. Tránh những tiêu chí chỉ nói “đúng kiểu dữ liệu”.

Ví dụ: “Số lượng trên mỗi dòng hàng là số nguyên dương; đơn giá là số thập phân không âm; số tiền luôn gắn với mã tiền tệ được hỗ trợ.”

### 6.4. Bất biến và vòng đời

Xác định quy tắc nào phải luôn đúng và chuyển trạng thái nào được phép. Ví dụ:

- dòng hàng không có số lượng bằng 0 hoặc âm;
- thanh toán thất bại không tự động biến thành thanh toán thành công;
- đơn đã hủy không được chuyển sang đã giao nếu chưa có quy trình khôi phục hợp lệ;
- một lần giao hàng phải tham chiếu đơn hàng tương ứng.

Các quy tắc chuyển trạng thái cần có tình huống trước, hành động và kết quả sau để kiểm thử.

### 6.5. Lịch sử và thời gian

Xác định dữ liệu nào là snapshot, dữ liệu nào là trạng thái hiện tại, dữ liệu nào cần lịch sử.

Ví dụ tiêu chí:

- Thay đổi địa chỉ khách hàng không làm thay đổi địa chỉ giao hàng đã chốt của đơn cũ.
- Khi nhận sự kiện từ đối tác trễ, hệ thống vẫn giữ thời điểm sự kiện xảy ra và thời điểm nhận.
- Người có quyền có thể truy xuất lịch sử thay đổi trạng thái trong khoảng thời gian được phép.

### 6.6. Truy vấn và workload

Tiêu chí có thể mô tả truy vấn quan trọng bằng tập dữ liệu mẫu và điều kiện đo:

- Tra cứu đơn hàng theo mã trả về đúng một đơn nếu mã duy nhất.
- Danh sách đơn của khách hàng trong khoảng thời gian không bỏ sót hoặc lặp đơn.
- Báo cáo doanh thu theo ngày không đếm lặp số tiền ở mức đơn hàng khi join với nhiều dòng hàng.
- Truy vấn quan trọng đáp ứng ngưỡng thời gian dưới tải và quy mô dữ liệu đã thống nhất.

Nếu có tiêu chí hiệu năng, phải ghi môi trường, quy mô dữ liệu, concurrency, percentile và cách đo. Không ghi “nhanh” nếu không có ngưỡng kiểm chứng.

## 7. Ví dụ hoàn chỉnh: từ câu hỏi đến tiêu chí chấp nhận

Giả sử yêu cầu ban đầu là:

> Khách hàng đặt hàng, thanh toán và nhận hàng. Hệ thống cần lưu lịch sử để hỗ trợ chăm sóc khách hàng và báo cáo.

### 7.1. Tách câu hỏi

| ID | Câu hỏi | Tác động |
|---|---|---|
| Q-101 | Khách mua có cần đăng nhập không? | Định danh người mua và quan hệ với Account |
| Q-102 | Đơn hàng có thể được thanh toán nhiều lần không? | Mô hình Order–Payment và lịch sử giao dịch |
| Q-103 | Một đơn có thể giao nhiều đợt không? | Mô hình Order–Shipment |
| Q-104 | Lịch sử trạng thái cần lưu bao lâu và ai được xem? | Lưu trữ, audit và quyền truy cập |
| Q-105 | Báo cáo doanh thu căn cứ thời điểm đặt hàng hay thanh toán? | Định nghĩa measure và thời gian trong mô hình phân tích |

Các câu hỏi Q-101 đến Q-105 cần người phụ trách nghiệp vụ xác nhận. Việc ghi chúng vào log không đồng nghĩa đã có câu trả lời.

### 7.2. Ghi quyết định sau khi xác nhận

Giả sử chủ sản phẩm và các bộ phận liên quan đã xác nhận các chính sách sau trong một dự án minh họa:

| ID | Quyết định đã xác nhận | Hệ quả với mô hình |
|---|---|---|
| D-101 | Cho phép mua khách; tài khoản đăng nhập là tùy chọn | Account không phải định danh bắt buộc của mọi người mua |
| D-102 | Mỗi lần thử thu tiền được ghi nhận riêng | Một Order có thể liên kết nhiều Payment |
| D-103 | Một Order có thể chia thành nhiều Shipment | Shipment có vòng đời riêng |
| D-104 | Lưu lịch sử trạng thái phục vụ hỗ trợ và kiểm toán theo chính sách lưu trữ | Cần nguồn sự kiện/lịch sử và quyền truy cập |
| D-105 | Báo cáo tách doanh thu theo thời điểm ghi nhận đơn và thời điểm thanh toán | Cần định nghĩa riêng các chỉ số và timestamp |

Trong dự án thực tế, mỗi dòng phải liên kết tới decision record chứa bối cảnh, phương án, lý do, người phê duyệt, ngày hiệu lực và các hệ quả chi tiết. Bảng trên chỉ là bản tóm tắt minh họa.

### 7.3. Viết tiêu chí chấp nhận

| ID | Tiêu chí | Cách xác minh |
|---|---|---|
| AC-101 | Đơn mua khách vẫn được tạo khi không có Account; thông tin liên hệ cần thiết được lưu theo chính sách | Tạo đơn không đăng nhập và đọc lại thông tin người mua |
| AC-102 | Mỗi lần thử thanh toán có mã giao dịch, số tiền, mã tiền tệ, thời điểm và kết quả riêng | Gửi một lần thất bại và một lần thành công; xác minh có hai bản ghi |
| AC-103 | Một Order có thể liên kết nhiều Shipment; trạng thái mỗi Shipment được theo dõi độc lập | Tạo hai lô giao cho cùng một đơn và cập nhật trạng thái khác nhau |
| AC-104 | Lịch sử trạng thái có thể truy xuất theo quyền và khoảng thời gian được phép | Kiểm thử truy vấn lịch sử với tài khoản có và không có quyền |
| AC-105 | Báo cáo tách chỉ số theo thời điểm ghi nhận đơn và thời điểm thanh toán | Dùng tập dữ liệu có thời điểm đặt và thanh toán ở hai ngày khác nhau |

Ví dụ này cho thấy quyết định cần được chuyển thành kết quả có thể kiểm tra. Nếu quyết định không dẫn đến tiêu chí nào, có thể chưa hiểu rõ hệ quả của nó hoặc chưa xác định cách chứng minh quyết định được thực hiện đúng.

## 8. Liên kết yêu cầu, câu hỏi, quyết định và mô hình

Các tài liệu riêng lẻ chỉ hữu ích khi có thể lần theo mối liên hệ giữa chúng. **Traceability (truy xuất nguồn gốc yêu cầu)** giúp trả lời:

- Vì sao thực thể hoặc thuộc tính này tồn tại?
- Ai đã yêu cầu quy tắc này?
- Quyết định nào khiến quan hệ trở thành tùy chọn?
- Tiêu chí nào chứng minh mô hình đáp ứng yêu cầu?
- Nếu yêu cầu đổi, những phần nào cần xem lại?

Một ma trận truy xuất đơn giản có thể như sau:

| Requirement | Question | Decision | Acceptance criteria | Thành phần mô hình |
|---|---|---|---|---|
| R-01: Cho phép đặt hàng | Q-101 | D-101 | AC-101 | Buyer, Account, Order |
| R-02: Lưu lần thử thanh toán | Q-102 | D-102 | AC-102 | Order, Payment |
| R-03: Hỗ trợ giao nhiều đợt | Q-103 | D-103 | AC-103 | Order, Shipment |
| R-04: Truy xuất lịch sử | Q-104 | D-104 | AC-104 | OrderStatusHistory/Event |
| R-05: Báo cáo theo thời gian | Q-105 | D-105 | AC-105 | FactOrder, FactPayment hoặc các measure tương ứng |

Ma trận không nhất thiết phải là một công cụ riêng. Có thể dùng ID trong tài liệu, issue tracker hoặc hệ thống quản lý yêu cầu. Điều quan trọng là ID ổn định và liên kết được cập nhật khi có thay đổi.

### 8.1. Kiểm tra độ bao phủ

Trước khi xem phân tích là hoàn tất, hãy kiểm tra:

- Mỗi yêu cầu quan trọng có tiêu chí chấp nhận không?
- Mỗi câu hỏi có trạng thái, người xác nhận và bước tiếp theo không?
- Mỗi quyết định quan trọng có bối cảnh và hệ quả không?
- Mỗi quyết định đã duyệt có được phản ánh trong mô hình không?
- Mỗi thành phần mô hình quan trọng có thể truy ngược về yêu cầu hoặc quy tắc không?
- Mỗi tiêu chí chấp nhận có cách kiểm chứng và dữ liệu kiểm thử không?

Nếu có thành phần mô hình không truy ngược được về yêu cầu, hãy xác định đó là quy tắc kỹ thuật, yêu cầu vận hành hay thiết kế thừa. Nếu có yêu cầu không dẫn đến thành phần mô hình hoặc hành vi nào, cần xác nhận xem nó đã bị bỏ sót hay chỉ là thông tin tham khảo.

## 9. Quản lý thay đổi và trạng thái

Yêu cầu và quyết định có thể thay đổi khi nhóm phát hiện thêm tình huống hoặc khi chính sách nghiệp vụ được cập nhật.

Một quy trình quản lý đơn giản:

1. Ghi nhận yêu cầu hoặc thay đổi mới với ID và nguồn.
2. Phân tích thành câu hỏi, giả định và tác động.
3. Giao câu hỏi cho người có thẩm quyền và thống nhất hạn trả lời.
4. Ghi decision record sau khi có xác nhận.
5. Cập nhật mô hình và các tiêu chí chấp nhận liên quan.
6. Đánh giá ảnh hưởng đến dữ liệu hiện có, API, tích hợp và báo cáo.
7. Kiểm thử lại các tiêu chí bị ảnh hưởng và ghi nhận kết quả.

Nên thống nhất tập trạng thái có ý nghĩa rõ ràng. Ví dụ:

- **Open:** chưa có câu trả lời.
- **In review:** đang chờ người có thẩm quyền xem xét.
- **Answered:** đã có câu trả lời nhưng chưa nhất thiết được phê duyệt thành quyết định.
- **Approved:** đã được chấp thuận.
- **Deferred:** hoãn đến mốc hoặc điều kiện xác định.
- **Rejected:** không chấp nhận phương án hoặc yêu cầu.
- **Superseded:** đã được thay thế bởi bản ghi mới.

Trạng thái phải phản ánh đúng quy trình thực tế. Không đánh dấu câu hỏi là Answered chỉ vì nhóm kỹ thuật đã tự chọn một cách triển khai.

## 10. Những sai lầm thường gặp

- **Để câu hỏi trong biên bản họp:** sau vài tuần không ai biết ai cần trả lời hoặc quyết định đã được chốt chưa. Hãy tạo ID và người phụ trách.
- **Viết câu hỏi quá rộng:** “Khách hàng hoạt động thế nào?” khó trả lời và khó liên kết đến mô hình. Hãy tách thành các câu hỏi cụ thể.
- **Biến giả định thành quyết định:** làm người đọc tưởng chính sách đã được phê duyệt. Hãy ghi trạng thái và người xác nhận.
- **Chỉ ghi lựa chọn mà không ghi lý do:** người sau không thể đánh giá liệu quyết định còn phù hợp khi bối cảnh đổi.
- **Viết tiêu chí mơ hồ:** “dữ liệu phải chính xác” không cho biết dữ liệu nào, chính xác theo nguồn nào và kiểm tra ra sao.
- **Gắn tiêu chí với tên bảng hoặc cột quá sớm:** có thể khóa chặt thiết kế trước khi hiểu hành vi cần đạt. Hãy mô tả kết quả nghiệp vụ trước.
- **Bỏ qua trường hợp biên:** chỉ kiểm thử luồng thành công sẽ bỏ sót thanh toán thất bại, dữ liệu thiếu, sự kiện trễ và cập nhật đồng thời.
- **Không cập nhật liên kết khi thay đổi:** mô hình, quyết định và tiêu chí có thể mâu thuẫn nếu chỉ sửa một tài liệu.
- **Không lưu lịch sử quyết định:** người đọc không hiểu vì sao dữ liệu cũ khác với quy tắc hiện tại.

## 11. Kết luận

Câu hỏi chưa rõ giúp nhóm nhận diện điều cần xác nhận; giả định cho phép phân tích tiếp nhưng phải được đánh dấu là tạm thời; quyết định ghi lại lựa chọn đã được chấp thuận cùng lý do và hệ quả. Tiêu chí chấp nhận chuyển yêu cầu thành điều kiện có thể quan sát và kiểm chứng.

Trong mô hình hóa dữ liệu, hãy liên kết các bản ghi này với thực thể, thuộc tính, quan hệ, bất biến, lịch sử và truy vấn liên quan. Khi yêu cầu thay đổi, đường liên kết đó cho biết mô hình và dữ liệu nào cần được xem xét lại.

## Tự kiểm tra

1. Phân biệt câu hỏi chưa rõ, giả định và quyết định bằng một ví dụ về dữ liệu khách hàng.
2. Một câu hỏi về việc một đơn hàng có thể giao nhiều đợt ảnh hưởng đến những thành phần nào của mô hình?
3. Vì sao decision record cần ghi cả phương án bị loại và hệ quả của phương án được chọn?
4. Viết một tiêu chí Given–When–Then cho trường hợp thanh toán thất bại rồi thử lại.
5. Tiêu chí “truy vấn phải nhanh” cần bổ sung thông tin gì để có thể kiểm chứng?
6. Làm thế nào để truy ngược từ một thuộc tính trong mô hình đến yêu cầu và người đã xác nhận?
7. Khi một quyết định bị thay thế, cần giữ lại những thông tin nào để giải thích dữ liệu được tạo theo quy tắc cũ?

