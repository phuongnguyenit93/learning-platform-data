# Discount precedence — Thứ tự ưu tiên áp dụng giảm giá

Trong chương **Discounts**, **discount precedence** là quy tắc quyết định ưu đãi nào được xét trước, ưu đãi nào được chọn khi có xung đột và giá trị nào làm cơ sở cho bước giảm tiếp theo. Nếu các quyết định này phụ thuộc vào thứ tự request, dữ liệu do client gửi hoặc một lần kiểm tra đã lỗi thời, người dùng có thể nhận mức giảm ngoài chính sách dù từng API đều hợp lệ về cú pháp.

Trong phạm vi bảo mật logic nghiệp vụ, mục tiêu là bảo vệ các bất biến về giá, quyền hưởng ưu đãi và số lần sử dụng xuyên suốt từ giỏ hàng đến thanh toán. Bài học sử dụng một chính sách cửa hàng giả định để làm rõ cách thiết kế; các mức ưu tiên, ngưỡng và cách làm tròn trong ví dụ là quyết định của chính sách đó, không phải quy tắc chung của mọi nền tảng.

Sau bài học, bạn cần có khả năng:

- Phân biệt điều kiện hưởng ưu đãi, khả năng cộng dồn, thứ tự áp dụng và cơ sở tính tiền.
- Mô tả chính sách giảm giá đủ rõ để các kênh bán hàng cho cùng một kết quả.
- Ngăn sửa thứ tự ưu tiên, tái sử dụng báo giá, áp dụng mã trùng và vượt hạn mức bằng request đồng thời.
- Thiết kế dấu vết tính giá và tình huống kiểm thử để chứng minh quyết định giảm giá.

## 1. Phân biệt những quyết định thường bị gộp thành “ưu tiên”

| Khái niệm | Câu hỏi cần trả lời | Ví dụ |
| --- | --- | --- |
| Eligibility — điều kiện hợp lệ | Ưu đãi có áp dụng được cho đối tượng và giao dịch này không? | Chỉ khách VIP trong đúng tenant, đơn đạt ngưỡng và chiến dịch đang hiệu lực |
| Compatibility — khả năng kết hợp | Hai ưu đãi hợp lệ có được dùng chung không? | Mã nhân viên không kết hợp với mã đối tác |
| Selection — cách chọn | Trong các lựa chọn cạnh tranh, chọn theo tiêu chí nào? | Chọn chiến dịch có thứ hạng cao nhất hoặc phương án cho số tiền phải trả thấp nhất |
| Precedence — thứ tự xử lý | Bước nào trước, ai thắng khi cùng cạnh tranh? | Giảm theo dòng hàng trước; trong nhóm giảm toàn đơn, priority nhỏ hơn thắng |
| Calculation basis — cơ sở tính | Tỷ lệ hoặc ngưỡng được tính trên số tiền nào? | Ngưỡng mã đơn hàng xét trên tiền hàng sau giảm theo dòng |
| Rounding và cap | Làm tròn lúc nào, giới hạn nào được áp dụng? | Làm tròn xuống từng khoản giảm đến một đồng; tổng giảm tiền hàng không quá 30% |
| Reservation và consumption | Khi nào giữ chỗ và khi nào tiêu thụ quyền dùng mã? | Giữ chỗ lúc chốt đơn, tiêu thụ sau khi xác nhận thanh toán |

Một giá trị priority không mô tả đủ toàn bộ chính sách. Ưu đãi đứng đầu vẫn phải qua kiểm tra quyền, hiệu lực, điều kiện và xung đột. Tương tự, hai ưu đãi đều hợp lệ riêng lẻ chưa có nghĩa chúng được phép kết hợp.

Cần phân biệt **mã được gửi**, **ứng viên hợp lệ**, **ưu đãi được chọn** và **ưu đãi đã được tiêu thụ**. Một mã xuất hiện trong request không đồng nghĩa hệ thống đã giảm giá hoặc trừ lượt sử dụng cho mã đó.

## 2. Vì sao đổi thứ tự có thể đổi số tiền?

Giả sử tiền hàng là 1.000.000 đồng. Hai ưu đãi được phép cộng dồn:

- A: giảm 10% trên số tiền còn lại.
- B: giảm cố định 100.000 đồng.

Nếu A được áp dụng trước:

~~~text
1.000.000 - 10% × 1.000.000 = 900.000
900.000 - 100.000           = 800.000 đồng
~~~

Nếu B được áp dụng trước:

~~~text
1.000.000 - 100.000       = 900.000
900.000 - 10% × 900.000  = 810.000 đồng
~~~

Chênh lệch là 10.000 đồng. Nếu chính sách quy định B trước A nhưng API lặp qua danh sách mã do client gửi, khách hàng có thể đổi thứ tự danh sách để được tính theo A trước B.

Có hệ thống quy định cả hai khoản giảm cùng lấy giá gốc làm cơ sở. Khi đó phép tính lại khác. Vì vậy, câu “giảm phần trăm trước” chỉ có ý nghĩa khi đồng thời xác định phần trăm tính trên giá nào, khoản giảm có được cộng dồn không và bước làm tròn diễn ra ở đâu.

Ưu tiên có thể làm thay đổi cả quyền hưởng ưu đãi. Chẳng hạn, mã yêu cầu tiền hàng còn lại ít nhất 900.000 đồng có thể hợp lệ trước một bước giảm, nhưng không còn hợp lệ sau bước đó. Cần chỉ định chính xác mốc xét ngưỡng thay vì kiểm tra ở bất kỳ thời điểm nào thuận tiện cho từng API.

## 3. Đặc tả một chính sách cụ thể

Xét một cửa hàng sử dụng VND. Ví dụ chỉ tính tiền hàng và phí giao hàng; phần thuế không thuộc mô hình tính toán này.

### 3.1. Chính sách được công bố cho bộ máy tính giá

| Hạng mục | Quy tắc trong ví dụ |
| --- | --- |
| Nguồn giá | Giá sản phẩm và quyền khách hàng lấy từ dữ liệu máy chủ |
| Giai đoạn | Giảm theo dòng hàng → giảm toàn đơn → ưu đãi giao hàng |
| Ưu tiên trong nhóm | Số priority nhỏ hơn được ưu tiên |
| Phá hòa | Thời điểm bắt đầu sớm hơn thắng; nếu vẫn bằng nhau, so ID ổn định do máy chủ cấp |
| Nhóm giảm toàn đơn | Chỉ được chọn một ưu đãi trong nhóm ORDER_MAIN |
| Chọn trong ORDER_MAIN | BUSINESS_PRIORITY: chọn ứng viên hợp lệ có thứ hạng cao nhất |
| Kết hợp | Giảm theo dòng được kết hợp với một mã ORDER_MAIN và ưu đãi giao hàng |
| Ngưỡng ORDER_MAIN | Xét tiền hàng sau giai đoạn giảm theo dòng, trước giai đoạn giảm toàn đơn |
| Ngưỡng miễn phí giao hàng | Xét tiền hàng sau tất cả khoản giảm tiền hàng |
| Làm tròn | Mỗi khoản giảm phần trăm làm tròn xuống đến một đồng |
| Trần giảm tiền hàng | Tối đa 30% tiền hàng gốc trong snapshot; không tính giảm phí giao hàng |
| Khi chạm trần | Khoản giảm tiếp theo bị giới hạn bởi phần trần còn lại, theo quy tắc đã phê duyệt |
| Khi sửa giỏ hoặc đổi chính sách | Báo giá chưa chốt phải được tính lại |

“Thời điểm bắt đầu sớm hơn” chỉ là cách phá hòa được chọn cho ví dụ. Một doanh nghiệp có thể chọn cách khác, nhưng cần một thứ tự đầy đủ và ổn định. Không sử dụng thứ tự trả về không có cam kết của cơ sở dữ liệu làm quy tắc ngầm.

Trần tổng 30% cũng phải có cơ sở rõ ràng: đó là 30% của tiền hàng gốc trong snapshot, không phải 30% của số tiền còn lại sau mỗi lần giảm. Quy tắc giới hạn khoản giảm khi chạm trần là một phần chính sách; không tự thêm thao tác cắt giảm âm thầm để che lỗi cấu hình.

### 3.2. Giỏ hàng và các ưu đãi

Giỏ hàng có hai dòng:

| Dòng | Số lượng | Đơn giá | Thành tiền |
| --- | ---: | ---: | ---: |
| P-1 | 2 | 300.000 | 600.000 |
| P-2 | 1 | 400.000 | 400.000 |
| **Tổng tiền hàng gốc** | | | **1.000.000** |

Các ứng viên:

- LINE10: giảm 10% dòng P-1, thuộc giai đoạn giảm theo dòng.
- SAVE100: giảm 100.000 đồng, yêu cầu cơ sở xét ngưỡng từ 900.000 đồng, thuộc ORDER_MAIN, priority = 10.
- VIP15: giảm 15%, dành cho khách VIP, thuộc ORDER_MAIN, priority = 20.
- SHIPFREE: miễn phí giao hàng nếu tiền hàng sau giảm đạt ít nhất 1.000.000 đồng.
- Phí giao hàng ban đầu là 30.000 đồng.

Giả sử người mua là VIP, các chiến dịch còn hiệu lực và các hạn mức cho phép giữ chỗ.

### 3.3. Tính theo chính sách

1. LINE10 giảm 10% × 600.000 = 60.000 đồng.
2. Tiền hàng sau giảm theo dòng là 940.000 đồng.
3. SAVE100 đạt ngưỡng 900.000; VIP15 cũng hợp lệ.
4. SAVE100 thắng trong ORDER_MAIN vì priority = 10 đứng trước 20.
5. Tiền hàng sau giảm toàn đơn là 840.000 đồng.
6. Tổng giảm tiền hàng là 160.000 đồng, thấp hơn trần 300.000 đồng.
7. SHIPFREE không đạt ngưỡng vì 840.000 < 1.000.000.
8. Tổng phải trả là 840.000 + 30.000 = **870.000 đồng**.

VIP15 nếu được chọn sẽ giảm 141.000 đồng trên cơ sở 940.000 đồng. Tổng phải trả khi đó là 799.000 + 30.000 = 829.000 đồng. Tuy nhiên, chính sách ví dụ chọn theo thứ hạng nghiệp vụ nên kết quả chính thức vẫn là 870.000 đồng.

Không được giải thích BUSINESS_PRIORITY là “luôn có lợi nhất cho khách hàng”. Hai chiến lược này giải quyết hai yêu cầu khác nhau.

## 4. Chọn theo ưu tiên và chọn phương án tốt nhất

### 4.1. BUSINESS_PRIORITY

Chiến lược này thể hiện quyết định của doanh nghiệp: chiến dịch nào được ưu tiên khi nhiều ưu đãi cạnh tranh. Với cùng dữ liệu đầu vào đã chuẩn hóa, thứ tự phải ổn định.

Trong một nhóm độc quyền đơn giản:

~~~text
Lấy các ứng viên thuộc đúng nhóm và đúng phạm vi
→ lọc điều kiện hợp lệ trên snapshot quy định
→ sắp xếp theo priority, startsAt, id
→ chọn ứng viên đầu tiên
→ tính khoản giảm theo cơ sở, cách làm tròn và trần đã định nghĩa
~~~

Một ứng viên có thứ hạng cao nhưng không hợp lệ phải bị loại trước bước chọn. Ngược lại, không được coi lỗi đọc quyền VIP hoặc lỗi tải chính sách là bằng chứng khách hàng đủ điều kiện.

### 4.2. BEST_PRICE

Nếu doanh nghiệp cam kết chọn phương án cho khách trả ít nhất, hệ thống cần so sánh các tổ hợp được phép sau khi áp dụng đầy đủ:

- Điều kiện và phạm vi từng ưu đãi.
- Xung đột giữa các ưu đãi.
- Cơ sở tính, thứ tự tính, làm tròn và trần.
- Ảnh hưởng tới phí giao hàng nếu mục tiêu là tổng phải trả.

Không thể luôn chọn khoản giảm riêng lẻ lớn nhất rồi tiếp tục tham lam. Một ưu đãi giảm nhiều có thể chặn hai ưu đãi khác mà tổng lợi ích cao hơn, hoặc làm mất điều kiện miễn phí giao hàng.

Cần giới hạn số ứng viên và độ phức tạp tính toán. Khi chạm giới hạn hoặc không tải được dữ liệu bắt buộc, trả kết quả kiểm soát được theo hợp đồng API; không tự chuyển sang một chiến lược khác khiến giá lệch khỏi chính sách đã công bố.

### 4.3. Độc quyền có phạm vi

Quy tắc “chỉ một ưu đãi trong nhóm” cần khóa phạm vi, ví dụ:

~~~text
(scopeType, scopeId, exclusiveGroup)
~~~

Độc quyền theo dòng P-1 không mặc nhiên loại ưu đãi dành riêng cho P-2. Ngược lại, hai mã khác tên nhưng cùng chiến dịch giảm toàn đơn có thể vẫn cạnh tranh trong cùng một nhóm.

Nếu tồn tại xung đột giữa nhiều nhóm, phải mô tả cách giải quyết ở cấp tổ hợp. Có thể dùng chiến lược duyệt theo thứ hạng ổn định và loại ứng viên xung đột với lựa chọn trước đó, nếu đó chính là chính sách đã phê duyệt; hoặc dùng chiến lược tối ưu toàn cục. Không giả định việc chọn độc lập một người thắng ở mỗi nhóm sẽ giải quyết mọi loại xung đột.

Cờ stopProcessing cũng cần xác định phạm vi: dừng phần còn lại của dòng hàng, của nhóm hay của toàn bộ giai đoạn. Một ưu đãi không hợp lệ không được kích hoạt cờ dừng. Việc dừng sau ưu đãi đã được chọn không được bỏ qua các kiểm tra bất biến cuối cùng.

## 5. Các bất biến phải được bảo vệ

Các bất biến dưới đây cần đúng ở API tính thử, khi chốt đơn và khi xử lý lại request.

### 5.1. Quyền và tính hợp lệ

- Chỉ áp dụng chiến dịch thuộc đúng tenant, đúng kênh và đúng đối tượng.
- Người gọi phải có quyền với giỏ hàng, báo giá và đơn hàng đang thao tác.
- Ưu đãi thủ công phải có phê duyệt hợp lệ nếu chính sách yêu cầu.
- Không thay việc kiểm tra quyền bằng sự hiện diện của campaignId, quoteId hoặc một mã khó đoán.

### 5.2. Tính tiền và lựa chọn

- Mỗi khoản giảm không âm và không vượt cơ sở còn lại mà nó được phép giảm.
- Tổng giảm theo phạm vi không vượt trần đã cấu hình.
- Tiền hàng, phí giao hàng và tổng phải trả không âm.
- Không có hai ưu đãi cùng được chọn trong cùng nhóm độc quyền và cùng phạm vi.
- Một quyền giảm giá không bị nhân lên chỉ vì được gửi bằng nhiều mã bí danh hoặc qua nhiều endpoint.
- Trường hợp tổng phải trả bằng 0 chỉ được xử lý nếu chính sách cho phép; không nhầm với trạng thái đã thanh toán qua cổng.

### 5.3. Tính xác định

Có thể mô tả phần tính giá thuần như sau:

~~~text
evaluate(
  cartSnapshot,
  policySnapshot,
  customerFactsSnapshot,
  normalizedPromotionIntent,
  evaluatedAt
) → pricingDecision
~~~

Giữ nguyên toàn bộ những đầu vào này thì kết quả phải giống nhau. Thời gian xét hiệu lực là một đầu vào được cố định cho lần tính, không gọi đồng hồ nhiều lần khiến các bước nhìn thấy các thời điểm khác nhau.

Báo giá không giữ chỗ chưa chứng minh ngân sách hoặc lượt dùng vẫn còn ở thời điểm chốt. Khả năng cam kết ưu đãi là điều kiện cần kiểm tra nguyên tử ở bước commit.

### 5.4. Hiệu ứng và vòng đời

- Gửi lại cùng một thao tác đã thành công không tạo thêm đơn hoặc thêm lượt sử dụng.
- Không có hai giao dịch cùng tiêu thụ một quyền dùng một lần.
- Dữ liệu quyết định giá đã chốt phải khớp dữ liệu yêu cầu thanh toán.
- Khi hoàn tiền, không trả lại nhiều hơn phần tiền thực trả được phân bổ cho hàng hoàn.

Chỉ kiểm tra tổng phải trả không âm là chưa đủ. Một đơn giảm 40% thay vì trần 30% vẫn có thể có tổng dương nhưng đã vi phạm chính sách.

## 6. Ranh giới tin cậy: client gửi ý định, máy chủ quyết định giá

Một request tính thử có thể có dạng:

~~~json
{
  "cartId": "cart-42",
  "expectedCartVersion": 7,
  "couponCodes": ["SAVE100", "VIP15"]
}
~~~

Đây là ý định sử dụng mã trên một phiên bản giỏ hàng. Nó không trao quyền để client chọn phần trăm giảm, quyền VIP hoặc thứ tự áp dụng.

Máy chủ cần tự xác định hoặc xác thực:

| Dữ liệu | Nguồn có thẩm quyền |
| --- | --- |
| Chủ sở hữu giỏ, tenant, quyền truy cập | Danh tính đã xác thực và dữ liệu quan hệ phía máy chủ |
| Sản phẩm, đơn giá, số lượng được phép | Giỏ hàng và bảng giá máy chủ |
| Hạng VIP, nhóm nhân viên, quyền mã riêng | Dữ liệu quyền khách hàng có phiên bản hoặc thời điểm xác định |
| Priority, nhóm độc quyền, phạm vi, cách làm tròn | Chính sách đã được kích hoạt |
| Giá trị giảm, giá sau giảm, ngưỡng đang áp dụng | Kết quả tính của máy chủ |
| Phê duyệt ngoại lệ | Bản ghi phê duyệt ràng buộc với đúng đối tượng và dữ liệu giao dịch |
| Ngân sách, lượt dùng | Trạng thái có thẩm quyền được kiểm tra khi giữ chỗ |

Các trường như unitPrice, discountAmount, priority, stackable, isVip hoặc approved trong payload không được dùng làm căn cứ tính giá hay cấp quyền. Nếu API không khai báo các trường đó, có thể từ chối chúng để phát hiện sớm client sai hợp đồng. Nếu cần nhận số tiền kỳ vọng từ giao diện, chỉ dùng nó để phát hiện chênh lệch, không thay thế kết quả tính máy chủ.

OWASP khuyến nghị thực thi kiểm soát ủy quyền giao dịch và tạo dữ liệu giao dịch quan trọng ở phía máy chủ. Áp dụng vào bài toán này, client không được tự quyết định giá cuối cùng hoặc đánh dấu một ngoại lệ đã được phê duyệt. [OWASP Transaction Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Transaction_Authorization_Cheat_Sheet.html).

### 6.1. Chuẩn hóa mã mà không tạo thêm quyền

Nếu chính sách mã là ASCII và không phân biệt hoa thường, có thể quy định:

~~~text
trim khoảng trắng được cho phép
→ chuyển hoa theo quy tắc không phụ thuộc locale
→ ánh xạ sang campaignId phía máy chủ
→ loại trùng theo quyền giảm giá thực tế
~~~

Không tự áp dụng quy tắc chuẩn hóa Unicode hoặc bỏ ký tự mà nhà phát hành chưa định nghĩa. Hai chuỗi trông giống nhau chưa chắc là cùng một mã.

Danh sách ["SAVE100", "save100", " SAVE100 "] chỉ tạo một yêu cầu hưởng SAVE100 theo chính sách ví dụ. Nếu hai mã khác nhau cùng ánh xạ tới một quyền giảm một lần, hệ thống cũng không được áp dụng quyền đó hai lần.

Chuẩn hóa giúp cùng một tập mã có cùng nghĩa. Nó không có nghĩa mọi tập mã khác nhau phải cho cùng một giá, vì tập mã được người dùng yêu cầu có thể chính là đầu vào hợp lệ của chính sách.

### 6.2. Quyền theo đối tượng phải được kiểm tra ở từng thao tác

Một người có thể có quyền đọc giỏ A nhưng không có quyền chốt báo giá của giỏ B. Nhân viên được phép gửi yêu cầu hỗ trợ giảm giá cũng chưa chắc được quyền:

- Sửa priority chiến dịch.
- Phê duyệt khoản giảm do chính mình đề xuất.
- Tạo ngoại lệ vượt trần.
- Áp dụng mã nội bộ cho khách hàng ở tenant khác.

Nếu thay đổi số tiền, phạm vi dòng hàng hoặc đối tượng sau phê duyệt, phê duyệt cũ phải hết giá trị theo chính sách đã định. Không cho phép tái sử dụng một cờ approved chung cho mọi lần sửa đơn.

## 7. Pipeline tính giá có thứ tự và có thể giải thích

~~~mermaid
flowchart TD
    A[Request giỏ hàng và mã yêu cầu] --> B[Kiểm tra danh tính và quyền đối tượng]
    B --> C[Nạp snapshot giá, giỏ, khách và chính sách]
    C --> D[Chuẩn hóa ý định và loại trùng quyền giảm]
    D --> E[Lọc ứng viên theo điều kiện giai đoạn]
    E --> F[Giải quyết xung đột theo chiến lược đã chọn]
    F --> G[Tính khoản giảm, làm tròn và áp trần]
    G --> H{Còn giai đoạn?}
    H -->|Có| E
    H -->|Không| I[Kiểm tra bất biến và lưu dấu vết]
    I --> J[Báo giá chưa giữ chỗ]
    J --> K[Commit: kiểm tra lại và giữ chỗ nguyên tử]
~~~

Một pipeline cụ thể nên thực hiện như sau:

1. **Kiểm tra quyền trước khi trả dữ liệu giá hoặc mã riêng.** Nạp giỏ bằng khóa bao gồm tenant và quan hệ quyền hợp lệ.
2. **Cố định snapshot.** Ghi cartVersion, phiên bản giá, policyVersion, dữ liệu quyền cần thiết và evaluatedAt.
3. **Xây tập ứng viên.** Bao gồm ưu đãi tự động và mã người dùng yêu cầu theo đúng hợp đồng; ngoại lệ thủ công chỉ vào tập sau kiểm tra phê duyệt.
4. **Xử lý giai đoạn giảm theo dòng.** Lọc điều kiện trên cơ sở được chỉ định, giải quyết nhóm độc quyền, tính giảm và cập nhật phần trần còn lại.
5. **Cố định cơ sở xét ngưỡng giảm toàn đơn.** Trong ví dụ đó là tiền hàng sau giảm theo dòng. Mọi ứng viên cùng giai đoạn nhìn thấy cùng cơ sở này.
6. **Chọn ưu đãi giảm toàn đơn.** Áp dụng chiến lược và quy tắc xung đột đã công bố; sau đó tính khoản giảm thực tế.
7. **Xử lý phí giao hàng.** Xét điều kiện trên tiền hàng sau giảm toàn đơn và chỉ giảm cơ sở phí giao hàng.
8. **Kiểm tra bất biến.** Không bỏ qua bước này dù có stopProcessing.
9. **Lưu quyết định.** Bao gồm lý do được chọn, bị loại, cơ sở tính và phiên bản đầu vào.

Việc đóng băng cơ sở xét ngưỡng ở bước 5 ngăn vòng lặp “mã giảm làm mất ngưỡng của chính nó, gỡ mã lại đủ ngưỡng”. Một chính sách khác có thể cố ý xét ngưỡng sau giảm, nhưng phải có quy tắc giải quyết rõ ràng thay vì lặp đến khi kết quả tình cờ ổn định.

Tương tự, không để cấu hình “A phải sau B” và “B phải sau A” cùng được kích hoạt. Phát hiện chu kỳ phụ thuộc khi kiểm tra cấu hình. Thứ tự các giai đoạn và thứ hạng trong một nhóm là hai loại quan hệ khác nhau.

## 8. Ví dụ Java cho thứ tự và phép tính tiền

Đoạn mã sau minh họa hai phần nhỏ: cách phá hòa ổn định và cách tính phần trăm theo đơn vị tiền nguyên. Nó không thay thế toàn bộ bộ máy kiểm tra quyền, điều kiện hoặc transaction.

### 8.1. Comparator chỉ nhận ứng viên đã kiểm tra

~~~java
import java.time.Instant;
import java.util.Comparator;
import java.util.List;
import java.util.Optional;

record EligibleDiscount(
        String id,
        int priority,
        Instant startsAt
) {}

final class DiscountSelection {
    private static final Comparator<EligibleDiscount> ORDER =
            Comparator.comparingInt(EligibleDiscount::priority)
                    .thenComparing(EligibleDiscount::startsAt)
                    .thenComparing(EligibleDiscount::id);

    static Optional<EligibleDiscount> chooseOne(
            List<EligibleDiscount> sameScopeAndExclusiveGroup
    ) {
        return sameScopeAndExclusiveGroup.stream().min(ORDER);
    }
}
~~~

Hợp đồng đầu vào của chooseOne:

- Mọi phần tử đã hợp lệ trên cùng snapshot và cùng cơ sở xét điều kiện.
- Mọi phần tử thuộc cùng nhóm độc quyền và cùng phạm vi.
- ID là duy nhất, ổn định và do máy chủ quản lý.
- Các trường bắt buộc đã được xác thực, không null.
- Chiến lược của nhóm là BUSINESS_PRIORITY.

Không truyền trực tiếp DTO của client vào hàm này. Comparator ổn định không thể sửa một tập ứng viên đã chứa ưu đãi mà khách hàng không có quyền nhận.

### 8.2. Tiền theo đơn vị nhỏ nhất và làm tròn rõ ràng

Trong ví dụ VND, một đơn vị nguyên là một đồng:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;

final class DiscountMoney {
    static long percentageFloor(long basisMinor, int rateBps) {
        if (basisMinor < 0 || rateBps < 0 || rateBps > 10_000) {
            throw new IllegalArgumentException("Invalid discount input");
        }

        return BigDecimal.valueOf(basisMinor)
                .multiply(BigDecimal.valueOf(rateBps))
                .divide(BigDecimal.valueOf(10_000), 0, RoundingMode.DOWN)
                .longValueExact();
    }
}
~~~

Một basis point bằng 0,01 điểm phần trăm; 1.000 bps tương ứng 10%. Vì cơ sở không âm, làm tròn xuống trong ví dụ có nghĩa bỏ phần lẻ nhỏ hơn một đồng.

Các điểm cần giữ trong thiết kế:

- Không dùng số thực nhị phân để biểu diễn chính sách tiền rồi làm tròn tùy nơi.
- Kiểm tra tràn số khi nhân số lượng, cộng tiền dòng và cộng phí; chọn kiểu số phù hợp phạm vi nghiệp vụ.
- Mọi phép so sánh tiền phải cùng loại tiền và cùng đơn vị.
- Mức giảm cố định và trần cũng phải được xác thực không âm.
- Tỷ lệ vượt phạm vi hợp lệ phải làm cấu hình không thể kích hoạt; không âm thầm sửa thành 100%.
- Chỉ giới hạn khoản giảm bằng cơ sở còn lại hoặc trần còn lại khi chính sách đã quy định cơ chế đó.

Ví dụ, giảm 15% trên 940.001 đồng cho giá trị trước làm tròn là 141.000,15 đồng; với quy tắc của bài, khoản giảm là 141.000 đồng. Nếu bộ máy tính thử làm tròn một lần ở cuối còn bộ máy chốt đơn làm tròn sau mỗi ưu đãi, hai kết quả có thể lệch nhau.

## 9. Báo giá là một trạng thái có phiên bản

Không nên lưu mỗi total = 870000 rồi coi đó là bằng chứng đủ điều kiện thanh toán. Báo giá cần gắn với những dữ liệu đã tạo ra nó.

Một snapshot báo giá có thể bao gồm:

~~~json
{
  "quoteId": "q-42",
  "tenantId": "shop-1",
  "customerId": "customer-7",
  "cartId": "cart-42",
  "cartVersion": 7,
  "priceVersion": 12,
  "policyVersion": 23,
  "customerFactsVersion": 4,
  "currency": "VND",
  "evaluatedAt": "2026-11-22T03:00:00Z",
  "expiresAt": "2026-11-22T03:05:00Z",
  "reservationMode": "NONE",
  "selectedPromotionIds": ["LINE10", "SAVE100"],
  "merchandiseBeforeDiscountMinor": 1000000,
  "merchandiseDiscountMinor": 160000,
  "shippingPayableMinor": 30000,
  "totalMinor": 870000
}
~~~

Trong ví dụ, báo giá được lưu phía máy chủ và chưa giữ ngân sách hoặc lượt dùng. Các ID và phiên bản chỉ minh họa cấu trúc dữ liệu. quoteId không phải vật thay thế cho kiểm tra quyền.

Chính sách của bài yêu cầu trước commit:

- Báo giá thuộc đúng giỏ, đúng khách và đúng tenant.
- Báo giá chưa hết hạn và chưa được chốt thành một đơn khác.
- Phiên bản giỏ, giá, chính sách và dữ liệu quyền vẫn phù hợp với quy tắc hiệu lực.
- Mọi điều kiện nhạy với thời gian hoặc trạng thái đã được xác nhận lại.
- Ngân sách và lượt dùng được giữ chỗ nguyên tử.

Nếu có thay đổi, trả yêu cầu lấy báo giá mới trước khi tạo thanh toán. Không tự tính số tiền khác rồi thu tiền theo một báo giá mà người dùng chưa xác nhận.

Một hệ thống có thể chủ động cam kết giữ giá trong thời gian ngắn. Khi đó phải thiết kế cơ chế giữ giá, ngân sách và các trường hợp thu hồi riêng. Chữ ký hợp lệ hoặc thời hạn chưa hết của token báo giá tự nó không giữ được lượt dùng và không chứng minh quyền hiện tại.

### 9.1. State machine đề xuất

~~~mermaid
stateDiagram-v2
    [*] --> DRAFT
    DRAFT --> QUOTED: Tạo báo giá
    QUOTED --> DRAFT: Sửa giỏ hoặc đầu vào mất hiệu lực
    QUOTED --> COMMITTED: Xác minh và giữ chỗ thành công
    COMMITTED --> PAID: Xác nhận thanh toán hợp lệ
    COMMITTED --> CANCELLED: Xác nhận hủy hoặc thất bại cuối cùng
    PAID --> PARTIALLY_REFUNDED: Hoàn một phần
    PAID --> REFUNDED: Hoàn toàn bộ
    PARTIALLY_REFUNDED --> PARTIALLY_REFUNDED: Hoàn thêm phần còn lại
    PARTIALLY_REFUNDED --> REFUNDED: Hoàn hết phần còn lại
~~~

Sau COMMITTED, các khoản tiền của đơn được cố định theo snapshot đã chốt. Sửa giỏ cũ không được làm thay đổi yêu cầu thanh toán đang tồn tại.

Không giải phóng giữ chỗ chỉ vì một request đến cổng thanh toán bị timeout: giao dịch bên ngoài có thể đã thành công. Cần đối soát hoặc nhận kết quả có thẩm quyền, rồi chuyển trạng thái bằng quy tắc có kiểm soát. Callback đến muộn phải được xử lý theo cùng state machine, không được tự làm sống lại một đơn đã hủy.

## 10. Transaction, hạn mức và idempotency

### 10.1. Lỗi kiểm tra rồi mới cập nhật

Giả sử mã còn đúng một lượt. Hai request có thể cùng đọc remainingUses = 1, cùng vượt qua kiểm tra rồi cùng tạo đơn. Sắp xếp ưu đãi chính xác không ngăn được lỗi đồng thời này.

Cần bảo vệ cả **quyết định chọn ưu đãi** và **khả năng cam kết quyết định đó**.

Một luồng commit trong cùng cơ sở dữ liệu có thể có dạng:

~~~text
BEGIN

1. Xác thực và kiểm tra quyền trên giỏ/báo giá.
2. Nhận hoặc khóa bản ghi idempotency theo tenant, actor, operation, key.
   - Cùng key, cùng payload đã hoàn tất: trả kết quả đã lưu.
   - Cùng key, payload khác: từ chối xung đột.
   - Đang xử lý: xử lý theo hợp đồng retry, không tạo nhánh commit thứ hai.
3. Khóa giỏ hoặc dùng cập nhật có điều kiện theo version và trạng thái.
4. Kiểm tra quote, snapshot và hiệu lực; tính lại quyết định nếu cần xác minh.
5. Giữ chỗ các tài nguyên chiến dịch theo thứ tự khóa ổn định.
   - Kiểm tra quyền dùng một lần hoặc giới hạn theo khách.
   - Kiểm tra ngân sách theo khoản giảm thực tế.
6. Tạo order snapshot, các dòng phân bổ và discount reservations.
7. Chuyển giỏ/báo giá sang trạng thái đã commit.
8. Ghi kết quả idempotency và sự kiện outbox.

COMMIT

Worker outbox yêu cầu thanh toán bằng ID ổn định của đơn.
~~~

Đây là giả mã thiết kế, không phải script giao dịch có thể chạy nguyên xi. Cơ chế khóa hoặc cập nhật có điều kiện phải được hiện thực phù hợp với cơ sở dữ liệu và mức cô lập được sử dụng. Chỉ thêm annotation transaction chưa chứng minh bất biến đồng thời đã được bảo vệ.

Không giữ khóa cơ sở dữ liệu trong lúc gọi dịch vụ thanh toán từ xa. Outbox giúp gắn việc lưu đơn và ý định gửi sự kiện trong một transaction; bên nhận vẫn cần xử lý lặp an toàn.

### 10.2. Bảo vệ ngân sách và quyền dùng một lần

Nếu một chiến dịch có ngân sách bằng tiền, bất biến giữ chỗ là:

~~~text
reservedAmount + consumedAmount <= budgetLimit
~~~

Khoản giữ chỗ bằng phần giảm thực tế được gán cho chiến dịch sau làm tròn và trần. Nó không bằng một con số client đề xuất.

Việc tăng reservedAmount phải là cập nhật có điều kiện nguyên tử hoặc diễn ra khi đã khóa bản ghi ngân sách phù hợp. Kiểm tra số bản ghi cập nhật để biết đã giữ chỗ thành công; không chỉ tin kết quả đọc trước đó.

Với quyền dùng một lần cho mỗi khách, có thể dùng một bản ghi slot duy nhất theo:

~~~text
(tenantId, campaignId, customerId)
~~~

Giữ chỗ slot bằng chuyển trạng thái có điều kiện. Khi hủy, slot chỉ trở lại khả dụng nếu chính sách cho phép. Khi đã tiêu thụ, việc mở lại quyền sau hoàn tiền cũng phải là một quyết định chính sách riêng.

Khóa duy nhất trên ledger theo orderId và campaignId chỉ ngăn ghi hai lần cho cùng đơn; nó không tự ngăn cùng khách dùng mã ở hai đơn khác nhau. Cần ràng buộc đúng đối tượng mà hạn mức áp dụng.

Nếu nhiều ngân sách phải giữ chỗ cùng lúc, cố định thứ tự khóa và rollback toàn bộ khi một tài nguyên không đủ. Không để ưu đãi đã được chọn thành công một nửa.

### 10.3. Retry cùng key và cùng nghiệp vụ

Khóa idempotency cần gắn với tenant, người gọi và loại thao tác. Payload hash cần bao gồm các trường có ý nghĩa, chẳng hạn cartId, expectedCartVersion, quoteId và tập mã sau chuẩn hóa.

Có hai lớp chống trùng khác nhau:

| Lớp | Ngăn điều gì? |
| --- | --- |
| Idempotency theo key và payload | Retry cùng một request không tạo hiệu ứng lặp |
| Ràng buộc nghiệp vụ trên giỏ, quote và order | Hai key khác nhau vẫn không chốt cùng một giỏ/phiên bản thành hai đơn |

Không chỉ dựa vào key do client chọn. Người gọi có thể gửi hai key khác nhau. Trạng thái giỏ, cập nhật version có điều kiện và ràng buộc tạo đơn phải chặn nhánh commit thứ hai.

Khi trả lại kết quả đã lưu, tiếp tục bảo đảm người gọi có quyền nhận kết quả đó. Không để việc đoán được idempotency key làm lộ báo giá hoặc đơn của tài khoản khác.

### 10.4. Thanh toán chỉ tiêu thụ một lần

Với reservation đang ở RESERVED:

~~~text
RESERVED → CONSUMED: thanh toán được xác nhận hợp lệ
RESERVED → RELEASED: hủy được xác nhận theo chính sách
~~~

Hai chuyển trạng thái cạnh tranh phải được bảo vệ bằng khóa hoặc cập nhật có điều kiện. Callback lặp không được tăng consumedAmount lần nữa; việc giải phóng cũng không được trừ reservedAmount hai lần.

Đồng thời kiểm tra sự kiện thanh toán thuộc đúng đơn, đúng loại tiền, đúng số tiền dự kiến và có nguồn xác thực. Một cờ success hoặc total do client gửi không đủ để đánh dấu PAID.

Nếu chính sách cho phép đơn 0 đồng, thiết kế luồng xác nhận riêng có cùng kiểm tra quyền và tiêu thụ ưu đãi, không giả lập callback của một giao dịch cổng thanh toán không tồn tại.

## 11. Phân bổ giảm toàn đơn và hoàn tiền

Giảm toàn đơn cần được phân bổ về các dòng hàng để kiểm soát hoàn tiền. Không tính lại ưu đãi bằng chính sách đang chạy ở thời điểm hoàn, vì chiến dịch hoặc thứ tự ưu tiên có thể đã thay đổi.

Trong ví dụ, cơ sở sau giảm theo dòng là:

- P-1: 540.000 đồng.
- P-2: 400.000 đồng.
- Tổng: 940.000 đồng.

Phân bổ SAVE100 theo tỷ lệ cơ sở của các dòng:

~~~text
P-1: 100.000 × 540.000 / 940.000 = 57.446,8085... đồng
P-2: 100.000 × 400.000 / 940.000 = 42.553,1914... đồng
~~~

Với phương pháp phần dư lớn nhất:

1. Lấy phần nguyên mỗi khoản phân bổ: 57.446 và 42.553 đồng.
2. Tổng hiện là 99.999 đồng, còn thiếu một đồng.
3. Gán đồng còn lại cho dòng có phần dư lớn nhất, ở đây là P-1.
4. Nếu phần dư bằng nhau, dùng khóa dòng ổn định để phá hòa.

Kết quả:

| Dòng | Tiền sau giảm theo dòng | Phần SAVE100 | Tiền hàng thực trả |
| --- | ---: | ---: | ---: |
| P-1 | 540.000 | 57.447 | 482.553 |
| P-2 | 400.000 | 42.553 | 357.447 |
| **Tổng** | **940.000** | **100.000** | **840.000** |

Cần bảo đảm tổng các khoản phân bổ bằng đúng khoản giảm toàn đơn, mỗi khoản phân bổ không âm và không vượt cơ sở dòng. Khi ưu đãi chỉ áp dụng cho một tập sản phẩm, mẫu số chỉ gồm các dòng đủ điều kiện.

Nếu hoàn toàn bộ dòng P-1, số tiền hàng có thể hoàn theo phân bổ là 482.553 đồng, không phải 600.000 đồng giá gốc. Phần phí giao hàng được xử lý theo chính sách hoàn phí riêng.

P-1 có hai đơn vị hàng. Nếu cho hoàn từng đơn vị, cần phân bổ tiếp 482.553 đồng bằng quy tắc ổn định, ví dụ một đơn vị 241.277 đồng và một đơn vị 241.276 đồng. Phải lưu hoặc tái dựng được đúng phân bổ đó; không làm tròn cả hai đơn vị lên 241.277 rồi cho hoàn vượt một đồng.

Các bất biến hoàn tiền cần thêm:

- Tổng tiền đã hoàn và đang được giữ cho các yêu cầu hoàn đồng thời không vượt phần có thể hoàn.
- Callback hoặc request hoàn lặp không phát sinh lần hoàn thứ hai.
- Việc hoàn tiền không tự động khôi phục lượt dùng mã, trừ khi chính sách cho phép.
- Nếu hoàn hàng làm mất điều kiện khuyến mãi ban đầu, cách thu hồi lợi ích phải được định nghĩa riêng; không tự lấy công thức báo giá hiện tại để thay thế lịch sử.

## 12. Những đường lạm dụng cần chủ động chặn

OWASP WSTG gợi ý kiểm thử khả năng dùng nhiều mã, áp dụng mã nhiều lần, sửa giỏ sau khi áp dụng giảm giá và đi sai trình tự checkout. Các hướng kiểm thử đó giúp tìm chỗ hệ thống tin vào một bước đã hoàn thành nhưng không còn đúng. [OWASP WSTG — Payment Functionality](https://wstg.owasp.org/latest/4-Web_Application_Security_Testing/10-Business_Logic/10-Payment_Functionality/).

### 12.1. Lấy thứ tự request làm thứ tự nghiệp vụ

**Thiết kế dễ lỗi:** duyệt couponCodes theo thứ tự nhận được và cập nhật giá ngay sau mỗi mã.

**Lạm dụng:** đảo vị trí mã hoặc thay đổi thứ tự gọi các endpoint để thay đổi cơ sở tính.

**Kiểm soát:** chuẩn hóa thành ý định dùng mã, xây tập ứng viên máy chủ và thực thi pipeline có thứ tự đã định.

### 12.2. Áp lại cùng quyền bằng tên khác

**Thiết kế dễ lỗi:** kiểm tra trùng theo chuỗi mã, trong khi nhiều chuỗi cùng ánh xạ một chiến dịch hoặc cùng một quyền nhận giảm.

**Lạm dụng:** gửi mã khác hoa thường, lặp trường trong danh sách hoặc sử dụng các bí danh khác nhau.

**Kiểm soát:** chuẩn hóa theo hợp đồng, ánh xạ ID có thẩm quyền và áp hạn mức theo quyền nghiệp vụ thực tế.

### 12.3. Giữ điều kiện cũ sau khi sửa giỏ

**Thiết kế dễ lỗi:** bật couponApplied sau khi đủ ngưỡng rồi không xét lại khi xóa hàng.

**Lạm dụng:** thêm hàng để đạt ngưỡng, nhận báo giá rồi bớt hàng trước khi thanh toán.

**Kiểm soát:** mọi thay đổi ảnh hưởng điều kiện làm thay đổi cartVersion và vô hiệu báo giá chưa chốt. Tổng tiền khi thanh toán phải lấy từ order snapshot đã commit.

### 12.4. Đi vòng qua kênh có kiểm tra yếu hơn

**Thiết kế dễ lỗi:** web dùng engine mới nhưng mobile, API nội bộ hoặc chức năng hỗ trợ khách hàng vẫn có công thức cũ.

**Lạm dụng:** gửi thao tác hợp lệ qua kênh kiểm tra ít điều kiện hơn để giữ khoản giảm bị kênh chính từ chối.

**Kiểm soát:** các kênh gọi cùng điểm thực thi chính sách có thẩm quyền; kiểm tra quyền và điều kiện ở đường ghi cuối cùng. Chính sách có thể khác theo kênh nếu được định nghĩa rõ, nhưng client không được tự chọn một kênh đặc quyền bằng cách sửa trường channel.

### 12.5. Tái sử dụng quyền phê duyệt hoặc báo giá

**Thiết kế dễ lỗi:** phê duyệt chỉ gắn với customerId, hoặc quoteId được chấp nhận cho mọi giỏ.

**Lạm dụng:** chuyển ưu đãi đã phê duyệt sang đơn lớn hơn, người khác hoặc giỏ khác.

**Kiểm soát:** ràng buộc phê duyệt với nội dung có ý nghĩa như tenant, đối tượng, phạm vi, số tiền và phiên bản; kiểm tra lại khi nội dung thay đổi.

### 12.6. Dùng lỗi đồng thời để vượt chính sách

**Thiết kế dễ lỗi:** đọc số lượt còn lại trước transaction rồi chỉ ghi nhận sử dụng sau khi tạo thanh toán.

**Lạm dụng:** gửi đồng thời nhiều yêu cầu chốt đơn để cùng vượt qua lần đọc.

**Kiểm soát:** giữ chỗ nguyên tử, ràng buộc duy nhất đúng phạm vi và kiểm tra trạng thái khi chuyển ledger. Rate limit có thể giảm tải nhưng không thay thế bất biến đồng thời.

Nếu ưu đãi được chọn không thể giữ chỗ, hủy transaction chốt đó và trả trạng thái yêu cầu báo giá hoặc xác nhận mới. Không âm thầm chọn ưu đãi khác rồi thu số tiền thay đổi mà khách chưa xác nhận.

## 13. Thiết kế tình huống kiểm thử

Bảng dưới là đặc tả kiểm thử cho chính sách ví dụ, không phải kết quả của một bộ test đã chạy. Các trường hợp thanh toán và đồng thời cần thực hiện trong môi trường kiểm thử được phép.

| Tình huống | Hành động | Kết quả cần chứng minh |
| --- | --- | --- |
| Luồng chuẩn | Dùng giỏ ví dụ với khách VIP và các mã hợp lệ | Chọn LINE10, SAVE100; tổng 870.000 đồng |
| Hoán vị đầu vào | Đổi ["SAVE100", "VIP15"] thành ["VIP15", "SAVE100"] | Cùng lựa chọn và tổng tiền khi các đầu vào còn lại giữ nguyên |
| Ưu tiên cao nhưng hết hiệu lực | Làm SAVE100 hết hiệu lực, VIP15 còn hiệu lực | SAVE100 bị loại; nếu mọi điều kiện khác giữ nguyên, tổng là 829.000 đồng |
| Mã lặp | Gửi SAVE100 nhiều lần và bằng biến thể được chuẩn hóa tương đương | Chỉ một quyền giảm SAVE100 được xét và ghi nhận |
| Sửa priority | Thêm hoặc đổi priority trong payload | Không thay đổi thứ hạng từ chính sách máy chủ |
| Cộng dồn sai nhóm | Cố áp cả SAVE100 và VIP15 | Chỉ một ưu đãi ORDER_MAIN được chọn |
| Biên ngưỡng | Thử cơ sở ORDER_MAIN bằng 899.999, 900.000 và 900.001 đồng | SAVE100 chỉ đạt ngưỡng ở hai giá trị sau |
| Sai cơ sở xét ngưỡng | Dùng giỏ ví dụ có tiền gốc 1.000.000 nhưng tiền sau giảm 840.000 | Không nhận miễn phí giao hàng |
| Sửa giỏ sau báo giá | Xóa bớt hàng rồi dùng quote cũ | Commit bị từ chối do phiên bản hoặc điều kiện đã thay đổi |
| Quyền đối tượng | Dùng quote hợp lệ của khách hoặc tenant khác | Từ chối, không tiết lộ chi tiết ưu đãi riêng |
| Chính sách đổi trước commit | Kích hoạt phiên bản khác sau khi tạo quote | Theo chính sách bài, phải có báo giá mới |
| Retry cùng request | Gửi lại cùng key và payload đã thành công | Trả cùng kết quả, không tạo thêm đơn hay reservation |
| Key dùng sai | Dùng lại key với quoteId hoặc tập mã khác | Trả xung đột, không dùng kết quả cũ cho yêu cầu mới |
| Hai key, cùng giỏ | Chốt cùng giỏ/phiên bản bằng hai key khác nhau | Tối đa một đơn được commit |
| Lượt dùng cuối | Hai đơn đồng thời tranh một quyền dùng cuối | Tối đa một reservation hợp lệ; request còn lại không nhận khoản giảm chưa được giữ |
| Ngân sách sát giới hạn | Hai commit mà tổng khoản giữ sẽ vượt ngân sách | Tổng reserved và consumed không vượt giới hạn |
| Callback lặp | Gửi lặp sự kiện thanh toán hợp lệ | Chỉ một chuyển RESERVED → CONSUMED và một hiệu ứng hoàn tất |
| Hoàn tiền lặp | Lặp yêu cầu hoàn toàn bộ dòng P-1 | Không hoàn tiền hàng vượt 482.553 đồng |
| Làm tròn | Giảm 15% trên cơ sở 940.001 đồng | Khoản giảm 141.000 đồng theo quy tắc của bài |
| Chạm trần | Tạo các khoản giảm có tổng danh nghĩa trên 300.000 đồng cho giỏ gốc 1.000.000 | Tổng giảm tiền hàng không vượt 300.000 và trace ghi rõ phần bị giới hạn |

Ở biên ngưỡng, cần phân biệt **đạt điều kiện của một mã** với **mã đó được chọn**. SAVE100 đạt ngưỡng vẫn có thể bị một ứng viên khác ưu tiên hơn thay thế nếu cấu hình nhóm đã thay đổi.

### 13.1. Kiểm thử thuộc tính

Ngoài ví dụ cụ thể, có thể sinh nhiều giỏ và tập ưu đãi để kiểm tra:

- Với cùng snapshot, chính sách và thời điểm xét, hoán vị cùng một tập mã không đổi kết quả.
- Thêm bản sao của cùng một quyền giảm không làm tăng lợi ích hoặc số lần tiêu thụ.
- Trong mỗi nhóm độc quyền và phạm vi, có tối đa một ưu đãi được chọn.
- Tổng phân bổ trên các dòng bằng đúng khoản giảm được phân bổ.
- Tổng phải trả bằng tiền hàng sau giảm cộng phí phải trả trong mô hình này.
- Chạy lại evaluator thuần trên cùng đầu vào không làm thay đổi ledger sử dụng.
- Hai transaction cạnh tranh không phá trần ngân sách hoặc giới hạn theo khách.

Không mặc định thuộc tính “thêm một ưu đãi luôn làm khách trả ít hơn”. Với BUSINESS_PRIORITY, một ưu đãi mới có thứ hạng cao hơn có thể thay thế ưu đãi có lợi hơn. Chỉ kiểm tra tính đơn điệu nếu chính sách thực sự cam kết điều đó.

Cũng không mặc định tách một dòng thành hai dòng luôn giữ nguyên giá. Làm tròn theo dòng có thể thay đổi kết quả. Nếu nghiệp vụ yêu cầu không thể kiếm lợi bằng cách tách dòng, phải chuẩn hóa các dòng tương đương hoặc tính trên phạm vi tổng phù hợp, rồi kiểm thử chính yêu cầu đó.

## 14. Dấu vết quyết định và vận hành

Một tổng tiền đúng nhưng không giải thích được sẽ khó điều tra khi có khiếu nại hoặc dấu hiệu lạm dụng. Nên lưu dấu vết có cấu trúc theo từng lần tính và từng order snapshot:

| Trường | Mục đích |
| --- | --- |
| decisionId, quoteId, orderId | Liên kết quá trình tính thử, chốt và thanh toán |
| tenantId, cartVersion, policyVersion, priceVersion | Tái dựng đúng ngữ cảnh |
| evaluatedAt, customerFactsVersion | Giải thích hiệu lực và quyền tại lúc tính |
| candidateId, scope, exclusiveGroup | Giải thích tập ứng viên và phạm vi cạnh tranh |
| basisMinor, thresholdBasisMinor, rate hoặc fixedAmount | Giải thích cơ sở tính và xét ngưỡng |
| priority và khóa phá hòa | Giải thích thứ tự lựa chọn |
| selected hoặc rejectedReason | Giải thích quyết định |
| discountMinor, capRemainingMinor, allocations | Đối chiếu tiền và hoàn tiền |
| reservationId và trạng thái | Đối chiếu hiệu ứng ngân sách, lượt dùng |

Ví dụ lý do nội bộ:

~~~text
LINE10   SELECTED              basis=600000 discount=60000
SAVE100  SELECTED              thresholdBasis=940000 discount=100000
VIP15    EXCLUSIVE_GROUP_LOST  winner=SAVE100 group=ORDER_MAIN
SHIPFREE MIN_SPEND_NOT_MET     thresholdBasis=840000 required=1000000
~~~

Đây là trace nội bộ. Giao diện công khai có thể chỉ nói “mã không áp dụng cho đơn này” nếu lý do chi tiết làm lộ nhóm khách hàng hoặc chiến dịch riêng. Không ghi token xác thực hoặc mã bí mật nguyên văn vào log chỉ để phục vụ đối soát.

Các tín hiệu vận hành hữu ích gồm:

- Tỷ lệ báo giá hết hiệu lực vì sửa giỏ hoặc thay phiên bản chính sách.
- Chênh lệch giữa tổng hiển thị, tổng đã commit và số tiền cổng thanh toán xác nhận.
- Nhiều request dùng lại key với payload khác.
- Nhiều lần tranh lượt dùng cuối hoặc nhiều tài khoản có mẫu thao tác giống nhau.
- Bất biến bị vi phạm, khoản giảm vượt trần hoặc ledger không cân đối.

Không coi mọi lần retry hoặc quote hết hạn là tấn công. Mất mạng và chỉnh sửa giỏ là hành vi bình thường; cần đối chiếu trạng thái và mẫu lặp trước khi kết luận.

### 14.1. Bảo vệ cả đường quản trị chính sách

Người dùng có thể không sửa được priority qua checkout, nhưng cấu hình sai hoặc quyền quản trị quá rộng vẫn làm mất bất biến. Đường quản trị cần:

- Phân quyền riêng cho tạo chiến dịch, sửa chính sách và phê duyệt ngoại lệ.
- Xác thực phạm vi tỷ lệ, loại tiền, thời gian hiệu lực, nhóm độc quyền và chu kỳ phụ thuộc trước khi kích hoạt.
- Lưu phiên bản chính sách bất biến để đơn đã chốt tham chiếu được.
- Kích hoạt toàn bộ một snapshot cấu hình, tránh trộn priority của phiên bản này với điều kiện của phiên bản khác.
- Lưu người thay đổi và lý do; áp dụng quy trình phê duyệt nếu nghiệp vụ yêu cầu.
- Quy định rõ báo giá đang mở được giữ hiệu lực hay phải lấy lại khi đổi chính sách.

Cache không được làm các bước của cùng một lần tính nhìn thấy các phiên bản chính sách khác nhau. Với ngân sách và quyền dùng một lần, cache đọc để hiển thị không thay thế cập nhật có điều kiện trên nguồn có thẩm quyền khi commit.

## 15. Bài tập vận dụng

### Bài tập 1: Làm rõ yêu cầu còn mơ hồ

Một yêu cầu ghi: “Khách VIP được giảm 15%, có thể nhập mã 100.000 đồng; ưu tiên mã tốt hơn”.

Hãy viết lại thành đặc tả có thể triển khai, trả lời ít nhất:

1. Hai ưu đãi có được cộng dồn không?
2. “Tốt hơn” là giảm tiền hàng nhiều hơn hay tổng phải trả thấp hơn sau phí giao hàng?
3. Mức giảm phần trăm tính trước hay sau khoản cố định?
4. Ngưỡng tối thiểu xét trên giá nào?
5. Khi bằng nhau, ưu đãi nào thắng?
6. Khi hết ngân sách giữa báo giá và commit, API trả kết quả gì và khách xác nhận lại thế nào?

Không bắt đầu bằng việc chọn giá trị priority trước khi xác định được những điều này.

### Bài tập 2: Tìm vị trí mất bất biến

Một hệ thống có ba endpoint:

~~~text
POST /cart/apply-coupon
PATCH /cart/items
POST /checkout
~~~

Endpoint đầu kiểm tra đủ ngưỡng và lưu couponApplied = true. Endpoint thứ hai chỉ sửa số lượng. Endpoint checkout tin cờ couponApplied rồi trừ khoản giảm.

Hãy chỉ ra điều kiện đã cũ sau khi sửa giỏ, đề xuất version nào cần tăng và thiết kế cách checkout kiểm tra lại. Sau đó thêm tình huống hai checkout cùng chạy để chứng minh việc tính lại giá vẫn cần đi kèm bảo vệ đồng thời.

### Bài tập 3: Thiết kế quyết định có thể tái dựng

Từ giỏ ví dụ, hãy tạo một decision record đủ để chứng minh:

- Vì sao SAVE100 thắng VIP15.
- Vì sao không có miễn phí giao hàng.
- Vì sao phần tiền hàng hoàn cho P-1 là 482.553 đồng.
- Vì sao callback thanh toán thứ hai không tiêu thụ thêm lượt mã.

## 16. Những điểm cần ghi nhớ

Discount precedence phải là chính sách rõ ràng về giai đoạn, điều kiện, xung đột, thứ hạng, cơ sở tính, làm tròn và trần. Kết quả không được phụ thuộc vào thứ tự dữ liệu mà người gọi có thể điều khiển.

Máy chủ phải kiểm tra quyền theo đối tượng và tính giá từ dữ liệu có thẩm quyền. Báo giá phải gắn với snapshot; commit phải bảo vệ phiên bản, ngân sách và lượt dùng bằng cơ chế nguyên tử.

Giá đúng ở một lần tính thử chưa đủ. Cần giữ đúng quyết định qua retry, xử lý đồng thời, thanh toán và hoàn tiền, đồng thời lưu dấu vết để giải thích từng khoản giảm.
