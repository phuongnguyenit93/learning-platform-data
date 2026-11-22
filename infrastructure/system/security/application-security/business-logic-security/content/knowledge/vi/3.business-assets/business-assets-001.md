# Tiền và số dư tiền tệ — Money and monetary balances

## 1. Tiền là tài sản nghiệp vụ, không chỉ là một trường số

Trong chương **Business Assets** của học phần **Business Logic Security**, tiền và số dư tiền tệ là nhóm tài sản cần được mô hình hóa rõ trước khi thiết kế API. Một lỗi không làm lộ dữ liệu vẫn có thể gây thiệt hại trực tiếp: cấp tiền hai lần, chi tiêu vượt số dư, hoàn tiền vượt quyền lợi hoặc chuyển tiền từ ví không thuộc quyền sử dụng.

Một trường như `balance = 1000000` chưa trả lời được:

- Đây là tiền tệ nào và đang dùng đơn vị nào?
- Số tiền đã được ghi sổ hay chỉ đang chờ xác nhận?
- Bao nhiêu đã bị giữ cho các giao dịch khác?
- Chủ thể nào có quyền sử dụng?
- Những giao dịch nào tạo nên số dư?
- Nếu hai yêu cầu cùng tiêu tiền, hệ thống bảo đảm giới hạn bằng cách nào?

**Bảo vệ tài sản tiền tệ** là bảo vệ quyền lợi và nghĩa vụ được biểu diễn bằng tiền, cùng các điều kiện làm tiền được ghi có, giữ, ghi nợ, chuyển, hoàn hoặc điều chỉnh. Bảo vệ một giá trị số không đủ nếu các đường thay đổi giá trị đó vẫn cho phép tạo quyền lợi trái chính sách.

Sau bài này, bạn cần có khả năng:

- Phân biệt số dư đã ghi sổ, khoản giữ, tiền khả dụng và khoản đang chờ.
- Biểu diễn tiền chính xác cùng đơn vị tiền tệ.
- Viết invariant cho chuyển tiền, giữ tiền, sử dụng khoản giữ và hoàn tiền.
- Nhận diện rủi ro cạnh tranh, ghi nhận trùng, sai quyền theo đối tượng và tin dữ liệu từ phía khách.
- Xác định bằng chứng cần lưu để kiểm thử, đối soát và giải thích số dư.

## 2. Xác định đúng loại tài sản đang bảo vệ

Một hệ thống thương mại có thể có nhiều đại lượng trông giống tiền nhưng mang ý nghĩa khác nhau.

| Đại lượng | Ý nghĩa trong nghiệp vụ | Không nên mặc nhiên hiểu là |
| --- | --- | --- |
| Số dư ví | Quyền lợi hoặc nghĩa vụ bằng tiền được hệ thống ghi nhận cho chủ ví | Tiền có thể chi ngay trong mọi trường hợp |
| Tiền khả dụng | Phần được phép sử dụng theo chính sách hiện tại | Toàn bộ số dư hiển thị |
| Khoản thanh toán được cấp phép | Bên thanh toán đã cấp quyền hoặc giữ hạn mức theo hợp đồng tích hợp | Tiền đã được thu và không thể đảo ngược |
| Khoản đã thu | Giao dịch đã được ghi nhận ở bước thu tiền theo hệ thống thanh toán | Khoản đã quyết toán cuối cùng hoặc không còn rủi ro hoàn, tranh chấp |
| Khoản chờ ghi có | Tiền nạp hoặc khoản phải nhận chưa đủ điều kiện ghi sổ | Nguồn tiền chắc chắn cho chi tiêu mới |
| Hạn mức khuyến mãi bằng tiền | Quyền sử dụng theo chiến dịch, có thể bị giới hạn mục đích | Tiền mặt có thể chuyển hoặc rút |
| Khoản có thể hoàn | Quyền hoàn phát sinh từ giao dịch và chính sách liên quan | Giá gốc hoặc toàn bộ số tiền từng thanh toán |

Tên trạng thái ở từng nhà cung cấp có thể khác nhau. Tích hợp cần xác định rõ sự kiện nào cho phép ghi sổ, sự kiện nào chỉ cập nhật trạng thái chờ và điều kiện nào còn có thể làm phát sinh điều chỉnh.

Ví dụ, một URL quay về trình duyệt có `status=success` không phải bằng chứng đủ để cộng tiền vào ví. Nguồn quyết định cần là phản hồi hoặc sự kiện đã xác minh theo hợp đồng tích hợp, hoặc kết quả truy vấn có thẩm quyền. Việc xác minh nguồn gửi vẫn phải đi kèm đối chiếu đúng giao dịch, tài khoản nhà cung cấp, người nhận, số tiền và tiền tệ.

### 2.1. Số dư trong ứng dụng không đồng nhất với tiền ở bên ngoài

Số dư ví là một bản ghi quyền lợi trong hệ thống. Tiền thực tế có thể nằm ở một hay nhiều tài khoản hoặc nhà cung cấp bên ngoài. Hai phía cần được đối soát, nhưng không nên gom thành một trường duy nhất.

Tương tự, tài khoản tiền khuyến mãi và tài khoản tiền có thể rút có thể cùng dùng đơn vị VND nhưng có quyền sử dụng khác nhau. Nếu chỉ cộng chúng rồi cho phép rút toàn bộ, hệ thống có thể biến ưu đãi có điều kiện thành tiền rút được.

Việc phân loại nguồn tiền, mục đích được phép và thứ tự sử dụng cần được quy định rõ nếu sản phẩm có các loại số dư này.

## 3. Mô hình tối thiểu: đã ghi sổ, đang giữ và khả dụng

Xét một ví không cho phép người dùng chi vượt tiền và chỉ có một tiền tệ trên mỗi tài khoản số dư.

Đặt:

- `B`: số dư đã ghi sổ, gồm các khoản ghi có và ghi nợ đã có hiệu lực trong sổ nội bộ.
- `H`: tổng các khoản giữ còn hiệu lực trong lưu trữ có thẩm quyền, chưa sử dụng và chưa giải phóng.
- `A`: số tiền khả dụng để tạo chi tiêu hoặc khoản giữ mới.
- `P`: khoản ghi có đang chờ, chưa được tính vào `B`.

Trong mô hình này:

~~~text
A = B - H
~~~

Khoản `P` không tự động được cộng vào `A`. Nếu sản phẩm cho ứng trước một phần khoản chờ, đó là một chính sách tín dụng riêng cần hạn mức và cách ghi nhận riêng.

Ví dụ:

| Trạng thái ví | Đã ghi sổ B | Đang giữ H | Khả dụng A | Chờ ghi có P |
| --- | ---: | ---: | ---: | ---: |
| Ban đầu | 1.000.000 | 0 | 1.000.000 | 0 |
| Giữ tiền cho đơn hàng | 1.000.000 | 300.000 | 700.000 | 0 |
| Có tiền nạp chưa xác nhận | 1.000.000 | 300.000 | 700.000 | 500.000 |
| Sử dụng khoản giữ 300.000 | 700.000 | 0 | 700.000 | 500.000 |
| Tiền nạp đủ điều kiện ghi có | 1.200.000 | 0 | 1.200.000 | 0 |

Tại bước sử dụng khoản giữ, số tiền đã ghi sổ giảm và khoản giữ cũng giảm. Tiền khả dụng không giảm lần thứ hai, vì phần đó đã bị loại khỏi khả dụng khi tạo khoản giữ.

### 3.1. Invariant của mô hình không cho chi vượt

Đối với các thao tác thông thường của mô hình đang xét:

~~~text
H >= 0
B >= H
A = B - H
khoản_chi_mới > 0
khoản_chi_mới <= A
~~~

Nếu lưu `A` thành một cột độc lập, phải giữ nó nhất quán với `B` và `H` trong cùng cơ chế cập nhật. Việc lưu cả ba đại lượng mà mỗi dịch vụ tự sửa một cột rất dễ tạo sai lệch.

Không áp dụng mệnh đề “mọi số dư luôn không âm” cho mọi sản phẩm. Hoàn trả bắt buộc từ bên ngoài, tranh chấp hoặc điều chỉnh có thể xuất hiện sau khi tiền đã được dùng. Một hệ thống thực tế cần biểu diễn trung thực khoản nợ hoặc trạng thái thiếu hụt theo thiết kế, đồng thời chặn quyền chi tiếp nếu chính sách yêu cầu. Từ chối ghi nhận một sự kiện tài chính đã thật sự xảy ra chỉ để giữ số dư đẹp sẽ làm mất tính đúng đắn của sổ.

Bài này dùng mô hình không chi vượt cho luồng chi tiêu thông thường. Ngoại lệ, tín dụng và xử lý nợ cần chính sách riêng.

## 4. Tiền phải đi cùng tiền tệ, đơn vị và cách làm tròn

### 4.1. Một số nguyên không tự mang ý nghĩa tiền

Giá trị `10000` có thể là 10.000 đồng hoặc 100 đơn vị tiền nếu hệ thống đang dùng phần trăm đơn vị. Nếu hai dịch vụ hiểu khác nhau, giao dịch có thể sai một hoặc nhiều bậc độ lớn.

Một đối tượng tiền nên chứa ít nhất:

~~~text
Money {
    currency
    minorUnits
}
~~~

`minorUnits` là số nguyên theo đơn vị nhỏ nhất mà sản phẩm và tích hợp đã thống nhất cho tiền tệ đó. Phải kiểm tra quy ước của từng giao diện tích hợp; không giả định mọi API đều dùng cùng quy ước.

Trong ví dụ của bài:

- VND được biểu diễn theo đồng.
- USD được biểu diễn theo cent.
- 1.200.000 VND có `minorUnits = 1200000`.
- 12,34 USD có `minorUnits = 1234`.

Đây là tập tiền tệ minh họa của ứng dụng, không phải một danh sách quy tắc đầy đủ cho mọi loại tiền hoặc nhà cung cấp.

### 4.2. Không dùng số dấu phẩy động để quyết định tiền

`float` và `double` không biểu diễn chính xác mọi phân số thập phân. Không nên dùng chúng để so sánh hạn mức, cộng tiền hoặc tính quyền hoàn.

Trong Java, có thể chọn:

- Số nguyên theo đơn vị nhỏ nhất, với kiểm tra tràn khi cộng, trừ và đổi dấu.
- `BigDecimal` với scale, độ chính xác và cách làm tròn được quy định.

Không tạo `BigDecimal` từ một giá trị `double` đã mất độ chính xác rồi coi đó là dữ liệu tiền gốc. Khi nhận dữ liệu thập phân, xử lý từ biểu diễn thập phân chính xác theo hợp đồng API.

### 4.3. Làm tròn là một phần của quy tắc nghiệp vụ

Giả sử cần phân bổ 10.000 đồng cho ba dòng hàng có tỷ lệ bằng nhau. Không thể cấp cho mỗi dòng 3.333,33 đồng trong mô hình VND nguyên đồng. Một cách phân bổ xác định có thể cho 3.333, 3.333 và 3.334 đồng.

Điều quan trọng là:

~~~text
tổng các phần đã phân bổ = tổng tiền cần phân bổ
~~~

Cần quy định dòng nào nhận phần dư và lưu kết quả đã chốt. Khi hoàn từng phần, dùng quyền lợi đã phân bổ và phần đã hoàn, thay vì mỗi lần tính lại độc lập rồi làm tròn theo hướng có lợi.

Tổng tiền hoàn của nhiều lần trả nhỏ không được vượt tổng quyền hoàn chỉ vì sai lệch làm tròn.

### 4.4. Không cộng trực tiếp khác tiền tệ

Chuyển đổi tiền tệ cần có báo giá hoặc tỷ giá, chiều quy đổi, phí, thời hạn và cách làm tròn. Kết quả cần lưu được căn cứ đã dùng.

Không kiểm tra tính cân bằng bằng phép cộng “100 USD + 2.000.000 VND”. Trong một mô hình sổ nhiều tiền tệ, cần đối chiếu các bút toán theo từng tiền tệ và các tài khoản chuyển đổi tương ứng. Giá trị kinh tế sau quy đổi là một bài toán khác với phép cộng số nguyên của cùng tiền tệ.

## 5. Sổ giao dịch giải thích số dư được hình thành như thế nào

Nếu chỉ lưu số dư hiện tại, khi phát hiện sai lệch sẽ khó biết tiền đến từ đâu hoặc mất ở bước nào. Cần một lịch sử giao dịch có cấu trúc, thường được gọi là **ledger** hoặc sổ ghi nhận.

Một mục ghi nhận nên liên kết được:

- Tenant, tài khoản và tiền tệ.
- Giao dịch nghiệp vụ và loại tác động.
- Số tiền, chiều tăng hoặc giảm.
- Thời điểm ghi nhận do máy chủ xác định.
- Nguồn phát sinh và tham chiếu bên ngoài nếu có.
- Quyết định, khoản giữ hoặc giao dịch gốc liên quan.
- Mã tương quan và thông tin chống ghi nhận trùng.

Số dư hiện tại có thể là giá trị tổng hợp được cập nhật cùng transaction với sổ, hoặc là một projection được xây từ sổ. Thiết kế phải xác định rõ đâu là dữ liệu có thẩm quyền và đâu chỉ là bản sao để đọc.

Một projection cập nhật bất đồng bộ có thể phù hợp để hiển thị, nhưng bản sao chậm không nên tự quyết định việc chi tiền. Nếu dùng một projection làm cơ sở chấp nhận chi, nó phải tham gia cơ chế nhất quán bảo đảm hạn mức tại nơi ghi.

### 5.1. Ví dụ sổ phụ cho chuyển tiền nội bộ

Trong mô hình minh họa, dùng số có dấu để biểu diễn thay đổi số dư của từng tài khoản trong sổ phụ. Đây là cách biểu diễn kỹ thuật, không phải hướng dẫn đầy đủ về hệ thống tài khoản kế toán.

Chuyển 120.000 đồng từ ví A sang ví B, phí 5.000 đồng do A trả:

| Tài khoản | Thay đổi số dư |
| --- | ---: |
| Ví A | -125.000 VND |
| Ví B | +120.000 VND |
| Tài khoản ghi nhận phí | +5.000 VND |
| Tổng trong phạm vi giao dịch nội bộ | 0 VND |

Các phần ghi nhận phải cùng tồn tại hoặc cùng không tồn tại. Không trừ A thành công rồi coi việc cộng B là một bước tùy chọn.

Với nạp và rút tiền, cần tài khoản đối ứng hoặc tham chiếu luồng bên ngoài phù hợp. Không thể kết luận mọi tổng số dư khách hàng luôn bất biến: nạp tiền, rút tiền, phí và điều chỉnh hợp lệ làm thay đổi tổng đó. Quy tắc bảo toàn cần áp dụng trong **phạm vi sổ và loại giao dịch đã xác định**, với các phía đối ứng được ghi đầy đủ.

### 5.2. Sửa sai bằng điều chỉnh có tham chiếu

Không nên cho nghiệp vụ thông thường sửa hoặc xóa mục đã ghi sổ để thay đổi lịch sử. Một sai sót cần được xử lý bằng giao dịch đảo hoặc điều chỉnh có thẩm quyền, tham chiếu đến giao dịch gốc.

Việc ghi một giao dịch đảo cũng phải có tính duy nhất và giới hạn. Nếu đảo cùng giao dịch hai lần, hệ thống vẫn có thể tạo hoặc làm mất tiền dù mọi mục lịch sử đều được giữ lại.

Quyền điều chỉnh số dư cần được kiểm soát theo đối tượng, giá trị và quy trình phê duyệt; không biến thành một API “đặt số dư mới” cho người dùng hoặc nhân viên tùy ý.

## 6. Các đường tấn công logic vào tiền và số dư

| Điểm yếu | Kết quả có thể xảy ra | Quy tắc bị thiếu |
| --- | --- | --- |
| Tin tổng tiền hoặc giá do client gửi | Thu ít nhưng cấp đủ quyền lợi hoặc ghi có quá mức | Giá và quyền lợi phải do máy chủ xác định |
| Tin `walletId` mà không kiểm tra quyền | Chi hoặc chuyển tiền từ tài khoản khác | Quyền theo đối tượng và tenant |
| Cho ghi số tiền âm vào lệnh chi | Trừ số âm thành cộng tiền | Miền giá trị của từng loại lệnh |
| Kiểm tra rồi ghi tách rời | Hai request cùng tiêu một số dư | Giữ hoặc trừ tiền nguyên tử |
| Cộng tiền theo mỗi webhook | Một giao dịch bên ngoài được ghi có nhiều lần | Tính duy nhất của tác động nghiệp vụ |
| Giải phóng khoản giữ hai lần | Tăng tiền khả dụng vượt số thực có | Chuyển trạng thái khoản giữ đúng một lần |
| Vừa giải phóng vừa sử dụng cùng khoản giữ | Quyền lợi được cấp nhưng tiền vẫn khả dụng | Cạnh tranh trên cùng khoản giữ và ngân sách |
| Hoàn theo giá gốc, bỏ giảm giá | Hoàn nhiều hơn phần đã trả | Phân bổ và ngân sách hoàn đáng tin cậy |
| Dùng cache số dư để cấp phép chi | Cho chi dựa trên dữ liệu cũ | Nguồn quyết định có tính nhất quán phù hợp |
| Tin mọi sự kiện đến sau là mới hơn | Quay lùi trạng thái hoặc áp dụng lại tác động | Điều kiện chuyển trạng thái và chống trùng |

Số dư không âm chưa đủ chứng minh an toàn. Nếu một người dùng được ghi có 500.000 đồng không có căn cứ rồi chi số đó, mọi số dư có thể vẫn dương. Cần kiểm soát cả **nguồn tạo quyền lợi** lẫn **cách tiêu thụ quyền lợi**.

## 7. Giữ tiền: tách quyền chi khỏi việc ghi nợ cuối cùng

Khoản giữ hữu ích khi cần dành tiền cho một thao tác chưa thể hoàn tất ngay, như xác nhận đơn hoặc gửi lệnh ra hệ thống ngoài.

Một khoản giữ nên có:

~~~text
holdId
tenantId
accountId
currency
amountMinor
businessOperationId
state
expiresAt
~~~

Số tiền và tài khoản của khoản giữ không được tự thay đổi khi sử dụng. Nếu cần thay đổi, phải dùng quy trình tăng, giảm hoặc tạo lại khoản giữ có kiểm tra ngân sách.

### 7.1. Tạo khoản giữ

Với số tiền giữ mới là `h`:

~~~text
h > 0
h <= B - H

B' = B
H' = H + h
A' = A - h
~~~

Kiểm tra và tăng `H` phải nguyên tử. Ví dụ cập nhật có điều kiện trong PostgreSQL:

~~~sql
UPDATE wallet_balance
SET held_minor = held_minor + :amount_minor
WHERE tenant_id = :tenant_id
  AND account_id = :account_id
  AND currency = :currency
  AND state = 'ACTIVE'
  AND :amount_minor > 0
  AND :amount_minor <= posted_minor - held_minor;
~~~

Chỉ tiếp tục nếu số hàng cập nhật bằng 1. Các placeholder biểu diễn tham số bind, không phải ghép chuỗi SQL.

Bản ghi khoản giữ và thay đổi tổng `held_minor` phải nằm trong cùng transaction. Ràng buộc duy nhất theo ý định nghiệp vụ thích hợp ngăn retry tạo nhiều khoản giữ cho cùng một lệnh. Khóa số dư phải bao gồm đúng tenant, tài khoản và tiền tệ.

### 7.2. Sử dụng khoản giữ

Ví dụ sử dụng toàn bộ khoản giữ `h` để thanh toán:

~~~text
B' = B - h
H' = H - h
A' = A
~~~

Khoản giữ chuyển từ `ACTIVE` sang `CAPTURED` trong cùng transaction với ghi nợ và các mục sổ nội bộ liên quan.

Không lấy `h` từ request sử dụng khoản giữ. Phải lấy từ khoản giữ được lưu có thẩm quyền và kiểm tra đúng chủ thể, tài khoản, tiền tệ, giao dịch cùng trạng thái.

Nếu hỗ trợ sử dụng một phần, cần theo dõi phần còn giữ, tổng đã sử dụng và tổng đã giải phóng. Mô hình hai trạng thái đơn giản không đủ cho tình huống đó.

### 7.3. Giải phóng khoản giữ

Khi hủy theo điều kiện hợp lệ:

~~~text
B' = B
H' = H - h
A' = A + h
~~~

Khoản giữ chuyển từ `ACTIVE` sang `RELEASED`. Job hết hạn và luồng sử dụng phải tranh chấp trên cùng trạng thái: chỉ một chuyển trạng thái được thắng.

Thời gian hết hạn không tự làm một khoản giữ biến mất khỏi tổng đã lưu. Nếu dùng bộ đếm `held_minor`, phải có thao tác giải phóng nhất quán. Xóa bản ghi bằng TTL mà không cập nhật tổng có thể làm ví bị giữ tiền vô thời hạn hoặc làm hai nguồn dữ liệu bất đồng.

Không giải phóng tự động chỉ vì hết thời gian chờ phản hồi khi tác động bên ngoài có thể đã xảy ra. Cần phân biệt khoản giữ chưa gửi lệnh và khoản giữ đang bảo đảm cho một lệnh chưa rõ kết quả.

## 8. Chuyển tiền nguyên tử và kiểm soát cạnh tranh

### 8.1. Ví dụ chi hai lần cùng một số dư

Ví A có 1.000.000 đồng khả dụng. Hai yêu cầu cùng chuyển 700.000 đồng:

~~~text
Request 1 đọc khả dụng: 1.000.000
Request 2 đọc khả dụng: 1.000.000
Request 1 kết luận đủ tiền
Request 2 kết luận đủ tiền
~~~

Nếu mỗi request ghi theo dữ liệu đã đọc, hệ thống có thể âm số dư hoặc mất một cập nhật ở phía nguồn trong khi cả hai phía nhận đều được cộng tiền.

Thêm annotation transaction chưa tự bảo đảm điều kiện nghiệp vụ. Cần cơ chế ngăn hoặc phát hiện cạnh tranh trên dữ liệu dùng chung, chẳng hạn khóa hàng, cập nhật có điều kiện, optimistic locking hoặc mức cô lập phù hợp kèm retry.

### 8.2. Ranh giới của chuyển tiền nội bộ

Nếu hai tài khoản và sổ nằm trong cùng cơ sở dữ liệu hỗ trợ transaction tương ứng, một luồng minh họa là:

1. Xác định actor từ ngữ cảnh xác thực, kiểm tra quyền chi ở tài khoản nguồn và điều kiện nhận ở tài khoản đích.
2. Xác định số tiền, tiền tệ và phí từ dữ liệu đã kiểm chứng; không cho sửa nguồn hoặc người nhận sau khi phê duyệt mà vẫn dùng quyết định cũ.
3. Giành quyền xử lý duy nhất cho ý định chuyển tiền.
4. Khóa hoặc cập nhật có điều kiện các bản ghi số dư theo thứ tự thống nhất.
5. Kiểm tra số tiền khả dụng, trạng thái tài khoản và hạn mức liên quan.
6. Ghi nợ nguồn, ghi có đích và ghi phí cùng các mục sổ.
7. Lưu kết quả chống gửi lại và sự kiện cần phát trong cùng transaction.
8. Commit rồi mới công bố kết quả thành công.

Nếu dùng khóa nhiều tài khoản, cần thứ tự khóa thống nhất để giảm deadlock. Nếu gặp deadlock hoặc xung đột phiên bản, retry có giới hạn phải giữ nguyên ý định và cơ chế chống trùng.

Không dùng `synchronized` trong một JVM làm bảo vệ duy nhất cho số dư nếu hệ thống có nhiều instance, job hoặc đường ghi trực tiếp khác.

### 8.3. Khi chuyển ra hệ thống bên ngoài

Transaction cục bộ không rollback được một lệnh đã thực hiện ở nhà cung cấp. Thường cần giữ tiền, tạo lệnh nội bộ, ghi outbox, xử lý kết quả và đối soát.

Nếu lệnh bên ngoài chưa rõ kết quả, giữ trạng thái chờ phù hợp và dùng mã giao dịch ổn định để truy vấn hoặc retry theo hợp đồng nhà cung cấp. Không coi timeout là bằng chứng chắc chắn thất bại rồi cho người dùng chi lại toàn bộ tiền.

## 9. Minh họa Java: biểu diễn tiền chính xác

Đoạn mã dưới đây minh họa một kiểu tiền tối thiểu cho ứng dụng chỉ hỗ trợ VND và USD. Đây không phải thư viện tiền tệ hoàn chỉnh hoặc một dịch vụ chuyển tiền chạy độc lập.

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.Objects;

enum CurrencyUnit {
    VND(0),
    USD(2);

    private final int scale;

    CurrencyUnit(int scale) {
        this.scale = scale;
    }

    int scale() {
        return scale;
    }
}

record Money(CurrencyUnit currency, long minorUnits) {
    Money {
        Objects.requireNonNull(currency, "currency");
    }

    static Money parseExact(CurrencyUnit currency, String decimalText) {
        Objects.requireNonNull(currency, "currency");
        Objects.requireNonNull(decimalText, "decimalText");

        long units = new BigDecimal(decimalText)
                .setScale(currency.scale(), RoundingMode.UNNECESSARY)
                .movePointRight(currency.scale())
                .longValueExact();

        return new Money(currency, units);
    }

    Money plus(Money other) {
        requireSameCurrency(other);
        return new Money(
                currency,
                Math.addExact(minorUnits, other.minorUnits));
    }

    Money minus(Money other) {
        requireSameCurrency(other);
        return new Money(
                currency,
                Math.subtractExact(minorUnits, other.minorUnits));
    }

    void requirePositive() {
        if (minorUnits <= 0) {
            throw new IllegalArgumentException("Amount must be positive");
        }
    }

    private void requireSameCurrency(Money other) {
        Objects.requireNonNull(other, "other");
        if (currency != other.currency) {
            throw new IllegalArgumentException("Currency mismatch");
        }
    }
}
~~~

Ý nghĩa các lựa chọn:

- `parseExact` không tự làm tròn số tiền vượt độ chính xác được hỗ trợ. Dữ liệu không biểu diễn chính xác hoặc vượt phạm vi `long` bị từ chối.
- `Math.addExact` và `Math.subtractExact` phát hiện tràn thay vì âm thầm quay vòng giá trị.
- Một `Money` có thể mang giá trị âm để biểu diễn chênh lệch trong mô hình này; lệnh chi, giữ hoặc hoàn mới phải gọi kiểm tra số dương ở ranh giới nghiệp vụ.
- Cộng hoặc trừ khác tiền tệ bị từ chối.
- Scale được khai báo cho tập tiền tệ hỗ trợ; quy ước của nhà cung cấp vẫn phải được kiểm tra khi tích hợp.

Lớp API còn cần giới hạn độ dài và định dạng đầu vào theo hợp đồng, ánh xạ lỗi thành phản hồi phù hợp và kiểm tra hạn mức nghiệp vụ. Một chuỗi số hợp lệ không chứng minh người gọi có quyền tiêu số tiền đó.

Đoạn mã chỉ giải quyết biểu diễn và phép tính. Nó không cung cấp transaction, phân quyền, sổ giao dịch, khóa số dư hoặc idempotency. Không được đọc số dư vào Java, kiểm tra bằng đối tượng `Money`, rồi ghi lại mà bỏ cơ chế cạnh tranh tại nơi lưu trữ.

## 10. Chống ghi nhận trùng ở đúng cấp nghiệp vụ

### 10.1. Request trùng và giao dịch trùng không hoàn toàn giống nhau

Idempotency key giúp xử lý việc gửi lại cùng yêu cầu. Phạm vi khóa nên gắn với tenant, chủ thể hoặc bên gọi có thẩm quyền, loại thao tác và fingerprint nội dung.

Cùng khóa nhưng khác số tiền, nguồn, đích hoặc tiền tệ phải được xử lý như xung đột. Cùng khóa và cùng nội dung phải trả kết quả đã lưu hoặc trạng thái đang xử lý theo hợp đồng API.

Tuy nhiên, người gọi có thể tạo khóa mới. Vì vậy, cần thêm ràng buộc nghiệp vụ, ví dụ:

- Một lệnh chuyển chỉ tạo một nhóm ghi nhận tài chính.
- Một khoản giữ không được sử dụng hoặc giải phóng vượt số tiền của nó.
- Một giao dịch nạp bên ngoài chỉ được ghi có theo đúng tác động hợp lệ của giao dịch đó.
- Tổng hoàn cho giao dịch gốc không vượt quyền hoàn còn lại.

### 10.2. Event ID không phải lúc nào cũng là khóa chống cộng tiền đầy đủ

Cùng một giao dịch bên ngoài có thể phát sinh nhiều sự kiện với các ID khác nhau. Chống trùng chỉ theo event ID vẫn có thể cộng tiền nhiều lần nếu mỗi sự kiện đều bị hiểu là một lần ghi có.

Cần hiểu loại sự kiện và ràng buộc tác động theo định danh giao dịch nghiệp vụ của nhà cung cấp, loại tác động, tài khoản tích hợp và phạm vi liên quan. Một giao dịch cũng có thể có các tác động khác nhau hợp lệ như thu tiền, hoàn tiền và điều chỉnh; không được gộp chúng thành một sự kiện duy nhất rồi bỏ qua mọi thay đổi sau.

Kiểm tra chữ ký hoặc nguồn gửi, đối chiếu dữ liệu và quyết định chuyển trạng thái phải đi cùng nhau. Webhook xác thực đúng nhưng tham chiếu sai số tiền hoặc sai người nhận không được tự động tạo số dư.

### 10.3. Lưu dấu chống trùng phải cùng ranh giới với tác động

Nếu đánh dấu đã xử lý trước rồi tiến trình dừng trước khi cộng tiền, hệ thống có thể bỏ sót khoản ghi có. Nếu cộng tiền trước rồi dừng trước khi đánh dấu, lần retry có thể cộng lại.

Trong transaction cục bộ, dấu chống trùng, thay đổi số dư và mục sổ phải được commit cùng nhau. Nếu tác động nằm bên ngoài, cần hợp đồng idempotency hoặc đối soát tương ứng; không thể chỉ dựa vào một cờ trong cơ sở dữ liệu cục bộ.

## 11. Hoàn tiền và điều chỉnh cũng là đường làm thay đổi tài sản

Hoàn tiền thường được xem như luồng hỗ trợ, nhưng nó có thể làm tiền rời hệ thống hoặc làm tăng quyền chi trong ví. Vì vậy, cần cùng mức kiểm soát như luồng thanh toán.

Với một giao dịch gốc và cùng tiền tệ, đặt:

- `C`: ngân sách hoàn được xác định từ giao dịch và chính sách.
- `R`: tổng hoàn đã thành công.
- `P`: tổng đang giữ cho các lệnh hoàn chưa có kết quả cuối.
- `x`: khoản hoàn mới.

Điều kiện cơ bản:

~~~text
x > 0
R + P + x <= C
~~~

Đây chưa phải toàn bộ điều kiện. Cần kiểm tra dòng hàng, số lượng, giảm giá đã phân bổ, người nhận, trạng thái trả hàng và thẩm quyền phê duyệt. Ngân sách thanh toán còn dư không cho phép hoàn thêm cho một dòng hàng đã được hoàn đủ.

Không lấy giá bán hiện tại để tính lại quyền hoàn của giao dịch cũ. Không tin trường `refundableAmount` do client gửi. Quyết định duyệt phải gắn với đúng nội dung, số tiền và phiên bản hồ sơ.

Với điều chỉnh số dư thủ công, cần lưu căn cứ, người đề nghị, người duyệt nếu có và giao dịch đối ứng. Hạn mức theo nhân viên hoặc tổng trong một khoảng thời gian cũng cần được giữ nhất quán nếu đó là điều kiện bắt buộc, thay vì chỉ kiểm tra riêng từng yêu cầu.

## 12. Kiểm thử theo invariant tiền tệ

Mỗi tình huống cần kiểm tra cả kết quả API và trạng thái tài sản sau commit.

| Tình huống | Thiết lập và thao tác kiểm thử | Điều cần chứng minh |
| --- | --- | --- |
| Số tiền âm hoặc bằng không | Gửi lệnh chi, giữ hoặc hoàn với giá trị không dương | Không phát sinh tác động tài chính |
| Sai tiền tệ hoặc đơn vị | Dùng USD cho tài khoản VND; đổi quy ước cent và đơn vị chính | Bị từ chối hoặc chuyển đổi đúng quy trình đã quy định |
| Tràn số | Dùng giá trị gần giới hạn kiểu số | Không quay vòng thành số âm hoặc số nhỏ |
| Hai lần chi đồng thời | Ví có 1.000.000 đồng, hai lệnh 700.000 đồng tranh chấp | Không có tổng quyền chi được chấp nhận vượt khả dụng |
| Lỗi giữa chuyển tiền | Gây lỗi sau ghi nợ nhưng trước ghi có trong transaction cục bộ | Không commit một phía |
| Sử dụng khoản giữ hai lần | Retry hoặc hai worker cùng xử lý một hold | Chỉ một lần ghi nợ theo quyền giữ |
| Giải phóng và sử dụng cạnh tranh | Job hết hạn chạy cùng worker thanh toán | Không vừa trả tiền khả dụng vừa cấp quyền lợi thanh toán |
| Callback trùng | Phát lại cùng event và các event khác của cùng giao dịch | Chỉ ghi nhận các tác động nghiệp vụ hợp lệ |
| Sai đối tượng | Dùng ví, hold hoặc payment thuộc người khác hoặc tenant khác | Không phát sinh thay đổi hoặc tiết lộ dữ liệu trái quyền |
| Khoản chờ chưa xác nhận | Tạo tiền nạp ở trạng thái chờ rồi thử chi | Không dùng nguồn chưa đủ điều kiện |
| Chia nhỏ hoàn tiền | Hoàn nhiều phần, gồm trường hợp có phân bổ làm tròn | Tổng hoàn không vượt quyền lợi đã chốt |
| Timeout bên ngoài | Bên ngoài đã thực hiện nhưng phản hồi bị mất | Không ghi có, ghi nợ hoặc hoàn thêm lần nữa |
| Projection chậm | Cố ý làm chậm bản sao hiển thị | Nơi quyết định chi vẫn giữ đúng hạn mức |
| Điều chỉnh từ bên ngoài | Ghi nhận đảo giao dịch sau khi tiền đã được dùng | Sổ phản ánh trung thực và quyền chi xử lý đúng chính sách |

Kiểm thử đồng thời cần buộc các luồng thực sự tranh chấp, chẳng hạn dùng điểm đồng bộ trước thao tác giữ tiền. Hai request tuần tự không chứng minh được cơ chế chống chi hai lần.

Nên chạy kiểm thử transaction với cơ sở dữ liệu thật hoặc môi trường có ngữ nghĩa tương ứng. Mock repository không chứng minh được hành vi khóa, ràng buộc duy nhất hoặc rollback.

Có thể dùng kiểm thử sinh chuỗi thao tác: ghi có hợp lệ, giữ, sử dụng, giải phóng, hoàn, retry và nhận callback. Sau mỗi transaction đã commit, kiểm tra:

~~~text
số dư tổng hợp khớp các mục sổ đã có hiệu lực
tổng khoản giữ khớp các hold còn hiệu lực theo mô hình
khả dụng khớp công thức đã chọn
mỗi tác động nghiệp vụ có đúng số lần cho phép
các phép cân bằng được giữ theo từng tiền tệ và phạm vi sổ
~~~

Nếu có nợ hoặc điều chỉnh ngoại lệ, bộ kiểm tra phải dùng invariant tương ứng với trạng thái đó, thay vì áp đặt điều kiện không âm cho mọi trường hợp.

## 13. Đối soát và dấu vết để giải thích tiền

Có ít nhất ba lớp cần kiểm tra quan hệ:

1. **Trong nội bộ:** số dư tổng hợp so với các mục sổ.
2. **Khoản giữ:** tổng đã giữ so với các bản ghi giữ và trạng thái giao dịch.
3. **Với bên ngoài:** lệnh, kết quả nhà cung cấp và giao dịch quyết toán hoặc báo cáo liên quan.

Đối soát không phải chỉ so tổng tiền cuối ngày. Hai sai sót ngược chiều có thể bù nhau về tổng nhưng vẫn phân bổ sai cho từng người dùng. Cần đối chiếu ở mức giao dịch, tài khoản, tiền tệ và trạng thái phù hợp.

Dấu vết nên cho phép nối chuỗi:

~~~text
businessOperationId
  -> holdId hoặc decisionId
  -> ledgerTransactionId
  -> externalTransactionId
  -> reconciliationResult
~~~

Ghi số tiền, tiền tệ, tenant, tài khoản, chủ thể thực hiện và thời gian cần thiết để truy nguyên. Tránh đưa bí mật thanh toán hoặc token đầy đủ vào log.

Các tín hiệu cần điều tra gồm số dư không khớp sổ, khoản giữ treo lâu, giao dịch ngoài thành công nhưng chưa ghi nhận, nhiều lần thử với các khóa khác nhau trên cùng quyền lợi và điều chỉnh thủ công bất thường.

Không tự đặt lại số dư chỉ để làm hết cảnh báo. Phải xác định nguồn sai lệch và thực hiện điều chỉnh có căn cứ, có quyền và có lịch sử. Đối soát giúp phát hiện, phục hồi; nó không thay thế kiểm soát nguyên tử tại lúc cấp quyền chi.

## 14. Bài tập tự kiểm tra

### Bài 1: sử dụng khoản giữ có làm giảm khả dụng thêm không?

Ví có `B = 900.000`, `H = 250.000`. Hệ thống sử dụng toàn bộ khoản giữ 250.000 đồng để thanh toán.

**Gợi ý trả lời:** trước thao tác, khả dụng là 650.000 đồng. Sau thao tác, `B = 650.000`, `H = 0`, khả dụng vẫn 650.000 đồng. Trừ khả dụng thêm một lần nữa sẽ giữ hoặc trừ tiền hai lần về mặt quyền chi.

### Bài 2: số dư luôn dương có chứng minh không mất tiền không?

Một callback nạp 400.000 đồng bị xử lý hai lần. Người dùng được cộng 800.000 đồng rồi chi 600.000 đồng. Số dư cuối vẫn dương.

**Gợi ý trả lời:** không. Nguồn ghi có đã tạo quyền lợi vượt giao dịch thực tế. Cần kiểm soát tính duy nhất của tác động nạp, xác minh dữ kiện và ghi nhận cùng transaction với dấu chống trùng.

### Bài 3: chuyển tiền hai cơ sở dữ liệu

Ví nguồn và ví đích nằm ở hai dịch vụ, mỗi bên có cơ sở dữ liệu riêng. Lập trình viên bọc hai lời gọi HTTP trong transaction của dịch vụ nguồn.

**Gợi ý trả lời:** transaction cục bộ không làm hai lời gọi thành một giao dịch nguyên tử xuyên dịch vụ. Cần một quy trình có trạng thái, giữ tiền, mã giao dịch ổn định, xử lý message trùng, kết quả chưa rõ và đối soát; lựa chọn cơ chế cụ thể phụ thuộc kiến trúc và hợp đồng.

### Bài 4: tiền khuyến mãi có thể rút không?

Ví hiển thị tổng 700.000 đồng, gồm 500.000 đồng tiền nạp và 200.000 đồng ưu đãi chỉ được mua hàng. Endpoint rút tiền chỉ kiểm tra tổng số dư.

**Gợi ý trả lời:** cách kiểm tra đó có thể đổi quyền lợi khuyến mãi thành tiền rút được. Cần phân loại nguồn và điều kiện sử dụng, tính số dư đủ tư cách cho thao tác rút và bảo vệ việc trừ đúng nhóm số dư một cách nguyên tử.

## 15. Các điểm cần ghi nhớ

Tiền và số dư là quyền lợi nghiệp vụ có nguồn gốc, chủ thể, tiền tệ và điều kiện sử dụng. Số dư đã ghi sổ, khoản giữ, khoản chờ và tiền khả dụng cần được phân biệt rõ.

Một thiết kế an toàn phải kiểm soát cả nơi tiền được tạo quyền lợi và nơi tiền được tiêu thụ. Biểu diễn chính xác ngăn sai số; sổ giải thích nguồn gốc; quyền theo đối tượng bảo vệ chủ thể; transaction và kiểm soát cạnh tranh giữ ngân sách; idempotency cùng tính duy nhất ngăn tác động trùng; đối soát xử lý chênh lệch với thực tế bên ngoài.

Câu hỏi cốt lõi là: **Mỗi đơn vị tiền được phép sử dụng đến từ căn cứ nào, đang thuộc quyền ai và cơ chế nào bảo đảm nó chỉ được tiêu dùng trong giới hạn đã quy định?**
