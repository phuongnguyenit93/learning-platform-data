# Xác định bất biến nghiệp vụ và hậu quả khi dữ liệu không nhất quán

Trong thiết kế cơ sở dữ liệu NoSQL, câu hỏi đầu tiên không phải là “nên dùng bao nhiêu node?” hay “chọn mức nhất quán nào?”, mà là: **điều gì tuyệt đối không được xảy ra với dữ liệu nghiệp vụ, kể cả khi có nhiều yêu cầu đồng thời, bản sao chậm cập nhật hoặc một nút gặp sự cố?**

Một hệ thống có thể chấp nhận việc số lượt thích trên màn hình chậm vài giây, nhưng khó có thể chấp nhận việc cùng một chỗ ngồi được bán cho hai khách. Hai tình huống đều liên quan đến dữ liệu không nhất quán, nhưng hậu quả và biện pháp thiết kế hoàn toàn khác nhau.

Bài học này tập trung vào cách chuyển yêu cầu nghiệp vụ thành **bất biến có thể kiểm chứng**, xác định **ranh giới nhất quán** và lượng hóa **hậu quả của việc vi phạm** trước khi lựa chọn mô hình dữ liệu, khóa, phân vùng, phương thức đọc/ghi và cơ chế xử lý lỗi trong NoSQL.

## 1. Bất biến nghiệp vụ là gì?

**Bất biến nghiệp vụ (business invariant)** là một điều kiện phải đúng đối với trạng thái nghiệp vụ hợp lệ tại những thời điểm hoặc ranh giới mà hệ thống cam kết. Ví dụ:

- Một ghế trong một suất chiếu **không thể có hơn một đặt chỗ đã xác nhận và còn hiệu lực**.
- Một yêu cầu thanh toán có cùng mã định danh nghiệp vụ **không được tạo hai khoản thu độc lập**.
- Khi chính sách không cho âm tiền, **số dư khả dụng của ví không được nhỏ hơn 0 sau giao dịch đã cam kết**.
- Đơn hàng đã hoàn tất **không được tự động quay về trạng thái đang xử lý chỉ vì một sự kiện cũ đến muộn**.
- Mã định danh khách hàng **phải tham chiếu đến khách hàng hợp lệ** theo chính sách tạo và xóa đã thống nhất.

Bất biến trả lời câu hỏi **“trạng thái nào được xem là đúng theo nghiệp vụ?”**; cơ chế nhất quán trả lời câu hỏi **“hệ thống làm thế nào để duy trì hoặc khôi phục trạng thái đó?”**.

Có thể mô hình hóa đơn giản:

~~~text
I(S) = true  nếu trạng thái nghiệp vụ S thỏa các quy tắc đã định nghĩa
I(S) = false nếu S vi phạm ít nhất một quy tắc

Một thao tác hợp lệ:
S_trước  --[thao tác + điều kiện kiểm tra]-->  S_sau
I(S_trước) = true                      I(S_sau) = true
~~~

Điều kiện “phải luôn đúng” cần ghi rõ **phạm vi**. Ví dụ, với mỗi ghế và suất chiếu, chỉ một đặt chỗ được xác nhận; **không phải** mỗi khách chỉ được mua một vé trên toàn hệ thống. Bất biến cũng cần ghi rõ **thời điểm**: trước và sau thao tác đã cam kết, sau một bước xử lý bất đồng bộ, hay sau khi hoàn tất toàn bộ quy trình?

### Phân biệt bốn loại yêu cầu thường bị trộn lẫn

| Loại yêu cầu | Câu hỏi cần trả lời | Ví dụ |
| --- | --- | --- |
| **Bất biến an toàn (safety invariant)** | Điều gì không được phép xảy ra trong trạng thái đã cam kết? | Một ghế có hai người sở hữu vé hợp lệ |
| **Quy tắc trạng thái/chuyển trạng thái** | Trạng thái nào được chuyển sang trạng thái nào? | Đơn đã hủy không được đổi thành đã giao chỉ vì sự kiện trễ |
| **Yêu cầu độ mới (freshness/staleness)** | Thông tin cho người đọc được trễ tối đa bao lâu? | Số lượng hàng hiển thị cập nhật trong 5 giây |
| **Yêu cầu hoàn tất/khôi phục (liveness/recovery)** | Sự kiện đã được chấp nhận phải được xử lý xong trong bao lâu? | Thanh toán thành công phải được đối soát với đơn hàng trong 2 phút |

Không phải mọi màn hình hiển thị dữ liệu cũ đều đồng nghĩa hệ thống đã phá vỡ bất biến. Một bản sao có thể trả về thông tin ghế “còn trống”, nhưng khi người dùng bấm xác nhận, nguồn dữ liệu có thẩm quyền vẫn từ chối giao dịch vì ghế đã bán. Ngược lại, nếu ứng dụng cho phép bán vé dựa trên lần đọc cũ mà không kiểm tra lại khi ghi, bất biến đã có nguy cơ bị phá vỡ.

**Điểm quyết định:** phân biệt **dữ liệu quan sát có thể cũ** với **quyết định nghiệp vụ đã cam kết sai**.

## 2. Tại sao NoSQL làm câu hỏi này trở nên quan trọng?

NoSQL bao gồm nhiều mô hình như key–value, document, wide-column và graph. Các hệ này có cơ chế khác nhau về tính nguyên tử, giao dịch, replication, phân vùng và mức nhất quán; không thể gán một chính sách chung cho tất cả NoSQL.

Ở hệ phân tán, một thay đổi có thể đi qua nhiều bước:

~~~text
Khách hàng xác nhận mua hàng
          |
          v
  Nút tiếp nhận ghi
          |
          +--> Dữ liệu có thẩm quyền được cập nhật
          |
          +--> Replica khác nhận thay đổi sau
          |
          +--> Chỉ mục / bản chiếu / cache được cập nhật sau
          |
          +--> Sự kiện gửi sang kho hàng, thanh toán, thông báo
~~~

Các bước trên có thể hoàn thành ở những thời điểm khác nhau. Vì vậy, hai thành phần có thể quan sát hai phiên bản hợp lệ theo cơ chế lưu trữ, dù nghiệp vụ chỉ có một kết quả cuối cùng mong muốn.

Nguồn gốc thường gặp của dữ liệu không nhất quán:

1. **Đọc dữ liệu cũ (stale read):** một replica, cache hoặc bản chiếu chưa nhận bản cập nhật mới.
2. **Ghi đồng thời:** hai yêu cầu cùng xem điều kiện hợp lệ rồi cùng cập nhật; một hoặc cả hai kết quả có thể sai nếu thiếu bảo vệ nguyên tử.
3. **Mất cập nhật (lost update):** hai thao tác tính từ cùng một phiên bản, lần ghi sau ghi đè lần ghi trước.
4. **Ghi nhiều đối tượng dang dở (partial update):** một đối tượng đã đổi, đối tượng liên quan chưa đổi vì lỗi giữa chừng.
5. **Sự kiện lặp hoặc đến sai thứ tự:** retry hoặc hàng đợi phát lại khiến thao tác được xử lý hai lần, hoặc trạng thái mới bị sự kiện cũ ghi đè.
6. **Phân vùng mạng hoặc chuyển vai trò nút:** các thành phần mất liên lạc, quyết định ghi/đọc và đồng bộ khác nhau tùy cơ chế hệ quản trị.

**Nhân bản dữ liệu không tự động bảo đảm tính đúng đắn nghiệp vụ.** Nhiều replica có thể giúp chịu lỗi, nhưng cũng đặt ra câu hỏi replica nào được quyền xác nhận thao tác, những bản nào phải xác nhận và một lần đọc có thể thấy dữ liệu mới đến mức nào.

## 3. Từ câu mô tả nghiệp vụ đến bất biến có thể kiểm chứng

Yêu cầu dạng “đừng bán quá số lượng tồn” còn mơ hồ. Trước khi chọn giải pháp kỹ thuật, cần làm rõ đối tượng, phạm vi, cách tính và các ngoại lệ.

### Bước 1: Xác định đối tượng và trạng thái nguồn

Ví dụ cửa hàng bán vé:
- **Đối tượng:** chỗ ngồi.
- **Khóa phân biệt:** cặp **(showId, seatId)**, không chỉ **seatId** vì ghế A12 tồn tại ở nhiều suất chiếu.
- **Trạng thái:** AVAILABLE, HELD, CONFIRMED, CANCELLED hoặc EXPIRED (mô hình minh họa).
- **Nguồn có thẩm quyền:** bản ghi đặt chỗ hoặc trạng thái ghế được hệ thống chọn làm điểm quyết định.
- **Quy tắc:** mỗi cặp **(showId, seatId)** có tối đa một quyền sở hữu đang CONFIRMED và hợp lệ.

Cách viết có thể kiểm tra:

~~~text
Với mọi (showId, seatId):
count(activeConfirmedBookings(showId, seatId)) <= 1
~~~

Nếu **HELD** cũng là quyền giữ ghế độc quyền tạm thời, cần thêm quy tắc: tại một thời điểm hệ thống chỉ chấp nhận tối đa một hold chưa hết hạn cho cùng ghế, và thao tác xác nhận chỉ được thực hiện bởi người giữ hold hợp lệ.

### Bước 2: Xác định ranh giới thời gian

“Không bao giờ có hai vé đã xác nhận” là cam kết tại thời điểm **xác nhận bán vé**. “Màn hình chọn chỗ phải đúng ngay” lại là cam kết tại thời điểm **đọc**.

Có thể đặt hai chính sách khác nhau:
- Màn hình hiển thị có thể chậm vài giây, phải ghi rõ rằng ghế được kiểm tra lại khi đặt.
- Thao tác ghi xác nhận phải từ chối nếu ghế đã có người khác xác nhận, bất kể màn hình trước đó thấy gì.

Chấp nhận độ trễ hiển thị **không có nghĩa** chấp nhận bán trùng vé.

### Bước 3: Xác định ngoại lệ và quy tắc chuyển trạng thái

Nếu người mua giữ ghế 5 phút rồi bỏ thanh toán, hold có hết hạn không? Nếu thanh toán thành công đúng lúc hold hết hạn, hệ thống ưu tiên kết quả nào? Nếu người dùng hoàn vé, khi nào ghế lại mở bán?

Những câu hỏi này quyết định chính xác bất biến. Một điều kiện đủ rõ cần mô tả cả **hủy, hoàn, hết hạn, retry và sự cố** chứ không chỉ đường đi “mua thành công” thông thường.

### Bước 4: Viết phản ví dụ tối thiểu

~~~text
T0: Ghế A12 chưa được bán.
T1: Khách X đọc replica, thấy A12 còn trống.
T2: Khách Y đọc replica, cũng thấy A12 còn trống.
T3: Khách X gửi xác nhận.
T4: Khách Y gửi xác nhận.
T5: Hai giao dịch đều được hệ thống trả về "thành công".
~~~

Tại **T5**, bất biến bị vi phạm nếu cả hai giao dịch tạo quyền sở hữu hợp lệ. Phản ví dụ cho thấy **kiểm tra khi đọc** không đủ; cần kiểm tra điều kiện cạnh tranh ở bước ghi có thẩm quyền.

### Bước 5: Gắn hậu quả và mức chấp nhận

Một bất biến hữu ích phải có chủ sở hữu nghiệp vụ trả lời được: nếu vi phạm, ai bị ảnh hưởng, mức thiệt hại bao nhiêu, có thể phục hồi không và phục hồi trong bao lâu?

| Bất biến | Hậu quả nếu vi phạm | Mức chấp nhận thường gặp |
| --- | --- | --- |
| Một ghế chỉ có một vé hợp lệ | Hai khách cùng đến, phải xử lý hoàn tiền/bồi thường, mất uy tín | Không chấp nhận bán trùng đã cam kết |
| Không trừ tiền hai lần cho cùng yêu cầu | Thiệt hại tài chính, khiếu nại và đối soát | Không chấp nhận khoản thu trùng không có căn cứ |
| Lượng phân bổ hàng không vượt ngân sách tồn cho phép | Bán thiếu hàng, hủy đơn, hoàn tiền | Tùy chính sách oversell được phép hay không |
| Trạng thái đơn đi theo chuyển trạng thái hợp lệ | Giao hàng sai, gửi thông báo sai, thao tác bị ghi đè | Không chấp nhận chuyển trạng thái bất hợp lệ ở nguồn |
| Tổng lượt xem gần thời gian thực | Báo cáo và màn hình chậm | Có thể chấp nhận độ trễ có giới hạn |

“Mức chấp nhận” phải do nghiệp vụ quyết định. Có cửa hàng **chủ động cho phép đặt vượt tồn** trong một giới hạn để quản lý hàng dự kiến về. Khi đó bất biến đúng không phải “không bao giờ âm tồn”, mà là “không vượt mức phân bổ vượt tồn đã được phê duyệt”. Không tự biến chính sách kinh doanh thành một quy tắc kỹ thuật cứng.

## 4. Nhận diện hậu quả theo từng kiểu không nhất quán

Những hiện tượng kỹ thuật giống nhau có thể mang rủi ro rất khác nhau tùy thao tác.

| Hiện tượng | Ví dụ NoSQL | Hậu quả nghiệp vụ | Câu hỏi phân tích |
| --- | --- | --- | --- |
| **Đọc cũ** | Trang sản phẩm vẫn hiển thị “còn hàng” sau khi hàng vừa hết | Người mua thất vọng hoặc phải thay đổi giỏ; nếu bước chốt không kiểm tra lại có thể bán quá | Dữ liệu cũ chỉ ảnh hưởng hiển thị hay được dùng để cho phép ghi? |
| **Lost update** | Hai luồng cùng đọc stock = 1 và cùng ghi stock = 0 | Có thể hai đơn cùng được xác nhận dù chỉ còn một sản phẩm | Phép kiểm tra và cập nhật có nguyên tử không? |
| **Write skew** | Hai quản trị viên cùng thấy người còn lại đang trực rồi mỗi người tự tắt ca trực của mình | Không còn người trực dù từng thao tác riêng lẻ hợp lệ | Bất biến trải qua nhiều bản ghi không? |
| **Ghi thiếu một phần** | Tạo đơn đã thu tiền, nhưng chưa gắn trạng thái đơn | Khách mất tiền mà không nhận được xác nhận | Có cơ chế giao dịch, trạng thái trung gian và đối soát không? |
| **Xử lý trùng** | Hàng đợi phát lại sự kiện yêu cầu hoàn tiền | Hoàn tiền hoặc ghi sổ hai lần | Thao tác có idempotency key và kiểm tra kết quả trước đó không? |
| **Sai thứ tự** | Sự kiện “đã hủy” đến trước sự kiện “đã xác nhận” phát hành trước đó | Đơn bị đẩy ngược sang trạng thái sai | Có version, sequence, điều kiện chuyển trạng thái không? |
| **Phản chiếu chậm** | Chỉ mục tìm kiếm chưa có sản phẩm vừa tạo | Sản phẩm chưa hiện trên trang tìm kiếm dù lưu thành công | Có mục tiêu độ trễ và cơ chế cập nhật lại chỉ mục không? |
| **Replica chưa hội tụ** | Người dùng đọc ở vùng khác, không thấy thay đổi vừa lưu | Tạo yêu cầu lặp, nhầm thao tác, thiếu tin tưởng | Cần read-your-writes hay đọc từ nguồn có thẩm quyền? |

### Phân biệt đọc cũ và mất cập nhật

Đọc cũ là vấn đề **quan sát**: client thấy trạng thái chưa mới. Mất cập nhật là vấn đề **kết quả ghi**: một thay đổi đã thực hiện bị ghi đè hoặc bỏ qua. Một lần đọc cũ có thể dẫn đến quyết định sai, nhưng không nhất thiết gây mất cập nhật nếu thao tác ghi có điều kiện.

### Phân biệt bất biến một bản ghi và nhiều bản ghi

Một số điều kiện có thể kiểm tra trên **một đối tượng nguyên tử**; ví dụ giá trị **availableUnits** không giảm dưới 0 trong một bản ghi tồn kho.

Một số điều kiện khác liên quan **nhiều đối tượng**; ví dụ tổng số quyền giữ chỗ đang hiệu lực trong collection không vượt sức chứa, hoặc bút toán ghi nợ phải có bút toán ghi có tương ứng. Kiểm tra từng bản ghi riêng lẻ có thể chưa đủ bảo vệ điều kiện tổng.

**Điểm cần xác minh ở từng sản phẩm NoSQL:** phạm vi nào được cập nhật nguyên tử, có hỗ trợ conditional write, unique constraint, transaction nhiều bản ghi/partition, hay cần tổ chức lại dữ liệu hoặc dùng quy trình nhiều bước.

## 5. Mức độ nghiêm trọng: không chỉ hỏi “có nhất quán không?”

Hãy mô tả mỗi rủi ro qua năm chiều:

1. **Tác động:** gây sai lệch giao diện, thất thoát tiền, vi phạm cam kết, mất dữ liệu hay rủi ro an toàn?
2. **Khả năng xảy ra:** cần hai thao tác hiếm gặp đồng thời, hay thường xuyên vì một khóa cực nóng?
3. **Phạm vi ảnh hưởng:** một người dùng, một khách hàng doanh nghiệp, một sự kiện bán vé hay toàn bộ hệ?
4. **Khả năng phát hiện:** hệ có tự nhận biết sự sai lệch hoặc chỉ biết khi khách báo?
5. **Khả năng phục hồi:** có thể tự sửa, hoàn tác, đối soát hay có thiệt hại không thể bù?

Ma trận định hướng thảo luận:

| Mức | Dấu hiệu | Ví dụ | Hướng xử lý thiết kế |
| --- | --- | --- | --- |
| **Nghiêm trọng** | Tiền, quyền sở hữu, an toàn, cam kết pháp lý; khó bồi hoàn | Thu tiền hai lần, bán trùng ghế đã xác nhận | Bảo vệ điều kiện ở điểm commit; ghi vết, idempotency, đối soát và quy trình xử lý sự cố |
| **Cao** | Có thể bồi hoàn nhưng chi phí và trải nghiệm lớn | Xác nhận đơn khi không còn tồn thật | Giới hạn phân bổ, thao tác ghi có điều kiện, phát hiện nhanh và hoàn tác nghiệp vụ |
| **Trung bình** | Lệch trạng thái tạm thời gây thao tác lặp hoặc hỗ trợ thủ công | Đơn đã thanh toán nhưng trang đơn chưa cập nhật | Trạng thái trung gian rõ, khả năng thử lại, read-your-writes khi cần |
| **Thấp** | Chủ yếu ảnh hưởng quan sát, có thể tự hội tụ | Số lượt thích hoặc gợi ý chưa cập nhật | Eventual consistency với mục tiêu độ trễ và giám sát |

Bảng không phải công thức điểm rủi ro dùng cho mọi sản phẩm. Đội sản phẩm cần quy định thời hạn phục hồi và giới hạn thiệt hại dựa trên nghiệp vụ thực tế.

Ví dụ tài liệu yêu cầu tốt:

~~~text
Quy tắc INV-BOOKING-01
- Đối tượng: (showId, seatId).
- Bất biến: tối đa 1 booking CONFIRMED còn hiệu lực cho mỗi cặp.
- Thời điểm cam kết: trước khi API xác nhận vé trả thành công.
- Điểm quyết định: kho trạng thái chỗ ngồi có thẩm quyền.
- Thao tác liên quan: hold, confirm, expire, cancel, refund.
- Đồng thời: có thể có nhiều yêu cầu mua cùng ghế.
- Hậu quả vi phạm: bán trùng vé, hoàn tiền, mất uy tín.
- Mức chấp nhận: 0 booking xác nhận trùng.
- Khi lỗi: chỉ trả thành công khi đã có kết quả xác nhận hợp lệ;
  trạng thái chưa rõ được giữ PENDING để kiểm tra/đối soát.
- Dấu hiệu giám sát: count(active confirmed booking per seat) > 1.
~~~

Dạng yêu cầu này dẫn trực tiếp đến lựa chọn kỹ thuật và tình huống kiểm chứng, thay vì một câu chung chung như “dữ liệu phải luôn nhất quán”.

## 6. Thiết kế bảo vệ bất biến trong NoSQL

Sau khi xác định điều kiện cần giữ, mới chọn cơ chế. Trật tự tư duy thường hữu ích:

~~~text
Bất biến nghiệp vụ
       |
       v
Các bản ghi/đối tượng tham gia điều kiện
       |
       v
Ranh giới cập nhật nguyên tử có thể có
       |
       +--> Một đối tượng nguyên tử?
       |       -> conditional update / CAS / điều kiện version
       |
       +--> Nhiều đối tượng nhưng hệ hỗ trợ giao dịch phù hợp?
       |       -> transaction + kiểm tra điều kiện tại commit
       |
       +--> Qua nhiều dịch vụ/nguồn dữ liệu độc lập?
               -> quy trình có trạng thái, idempotency,
                  bù trừ, đối soát và cam kết giới hạn rõ ràng
~~~

### 6.1. Đưa phép kiểm tra vào thao tác ghi nguyên tử

Một mẫu không an toàn:

~~~text
available = read("sku-01").availableUnits

if available >= 1:
    write("sku-01").availableUnits = available - 1
    confirmOrder()
~~~

Hai yêu cầu có thể đều đọc **available = 1**, đều vượt qua điều kiện rồi cùng xác nhận đơn. Kết quả kho có thể vẫn là **0** trong khi đã bán hai sản phẩm.

Một mẫu có điều kiện tốt hơn:

~~~text
result = atomicConditionalUpdate(
    key = "inventory:sku-01",
    condition = (availableUnits >= 1),
    change = (availableUnits = availableUnits - 1)
)

if result == APPLIED:
    proceedWithReservation()
else:
    rejectAsOutOfStock()
~~~

Đây là **giả mã**, không phải API chung cho mọi NoSQL. Cần chọn hệ cung cấp **kiểm tra điều kiện và cập nhật cùng một thao tác nguyên tử** với bảo đảm đọc/ghi/durability phù hợp. Nếu vẫn tạo đơn xác nhận ở nơi khác, phải xử lý thêm ranh giới giữa **trừ tồn** và **xác nhận đơn**.

Một biến thể là **optimistic concurrency control** với version:

~~~text
Đọc: { id: "item-01", availableUnits: 3, version: 7 }

Ghi có điều kiện:
  chỉ thành công nếu version hiện tại = 7
  đặt availableUnits = 2
  đặt version = 8

Nếu có người ghi trước:
  điều kiện thất bại -> đọc lại, tính lại, retry có giới hạn
~~~

Kiểm tra version ngăn việc ghi đè mù từ phiên bản cũ, nhưng bản thân nó không bảo đảm điều kiện trải qua **nhiều bản ghi** được bảo vệ nếu các bản ghi đó cập nhật độc lập.

### 6.2. Chọn ranh giới dữ liệu theo bất biến

Khi điều kiện cốt lõi nằm trong một nhóm dữ liệu nhỏ, đôi khi có thể mô hình hóa để quyết định trong cùng một đối tượng/aggregate nguyên tử.

Ví dụ thay vì tìm và đếm các booking ở nhiều tài liệu trước khi xác nhận ghế, có thể dùng một trạng thái có thẩm quyền theo khóa **(showId, seatId)** để chọn đúng một người giữ quyền tại một thời điểm. Bảng vé, lịch sử thanh toán và màn hình quản trị có thể là dữ liệu liên quan được cập nhật sau.

Tuy nhiên:
- Nhúng quá nhiều dữ liệu vào một tài liệu có thể tạo điểm nóng hoặc vượt giới hạn kích thước.
- Gom logic vào một khóa giúp bảo vệ điều kiện nhưng có thể làm giới hạn thông lượng của khóa đó.
- Không được giả định mọi NoSQL đều hỗ trợ thao tác nguyên tử với cùng ranh giới.

Thiết kế cần cân bằng **phạm vi bất biến**, **mẫu truy vấn** và **tải truy cập đồng thời**.

### 6.3. Dùng giao dịch khi bất biến trải trên nhiều đối tượng

Một giao dịch phù hợp có thể giúp đảm bảo nhiều thay đổi được chấp nhận hoặc từ chối theo các điều kiện đã định. Nhưng từ “transaction” chưa đủ: phải xem **isolation level**, phạm vi tài liệu/partition, xung đột, timeout và xử lý retry.

Ví dụ quy tắc “mỗi ca trực luôn có ít nhất một nhân sự đang hoạt động”:

~~~text
Ban đầu: A.active = true, B.active = true

Yêu cầu X: muốn tắt A; đọc B vẫn active.
Yêu cầu Y: muốn tắt B; đọc A vẫn active.

X tắt A và Y tắt B ở hai bản ghi riêng.
Kết quả: không còn ai trực.
~~~

Đây là dạng **write skew**: từng thao tác thay đổi bản ghi khác nhau nhưng cùng phá vỡ điều kiện tổng. Giao dịch có mức cô lập không đủ mạnh vẫn có thể gặp tình huống tương tự. Nếu bất biến yêu cầu bảo vệ ở thời điểm đồng thời, cần cơ chế tương đương **serializable** cho thao tác đó, hoặc một điểm điều phối/đối tượng có thẩm quyền chung với thao tác nguyên tử thích hợp.

### 6.4. Khi nghiệp vụ đi qua nhiều dịch vụ

Thanh toán, tồn kho, vận chuyển thường không cùng chung một giao dịch nguyên tử. Phải coi trạng thái **đang xử lý/chưa rõ kết quả** là một phần mô hình nghiệp vụ:

~~~text
ORDER_CREATED
     |
     v
INVENTORY_RESERVED
     |
     v
PAYMENT_PENDING
     |
     +--> PAYMENT_SUCCEEDED -> ORDER_CONFIRMED
     |
     +--> PAYMENT_FAILED    -> RELEASE_RESERVATION
     |
     +--> PAYMENT_UNKNOWN   -> RECONCILE -> tiếp tục hoặc hoàn tác
~~~

Đây chỉ là **ví dụ quy trình**, không ngụ ý thứ tự này luôn tối ưu. Cần quy định rõ khi nào đơn được xem là “đã xác nhận”, khi nào hoàn tiền, khi nào nhả giữ hàng và hành động nào được phép thử lại.

Các công cụ thường dùng:

- **Idempotency key:** yêu cầu lặp cùng ý nghĩa trả về kết quả đã xử lý, tránh tạo nhiều hiệu ứng độc lập. Khóa phải có phạm vi, thời hạn lưu và quy tắc xử lý cùng khóa nhưng payload khác nhau.
- **Outbox:** lưu thay đổi nghiệp vụ và thông điệp cần phát cùng ranh giới ghi hỗ trợ, rồi phát thông điệp bất đồng bộ để giảm nguy cơ “ghi xong nhưng quên gửi sự kiện”.
- **Inbox/deduplication:** ghi nhận định danh thông điệp đã xử lý để xử lý delivery lặp.
- **Saga và hành động bù trừ:** các bước có trạng thái, mỗi bước biết cách sửa hậu quả khi bước sau thất bại; bù trừ không nhất thiết là phép đảo hoàn hảo.
- **Đối soát (reconciliation):** so trạng thái giữa nguồn có thẩm quyền, cổng thanh toán và hệ vận hành để tìm các thao tác chưa rõ hoặc bỏ sót.

Không nên hứa **exactly-once end-to-end** chỉ vì broker hoặc database quảng bá cơ chế delivery mạnh. Khi có hệ thống ngoài và retry sau timeout, phải thiết kế để một thao tác nghiệp vụ **không tạo hiệu ứng trùng** và có thể đối soát kết quả không rõ ràng.

## 7. Tình huống xuyên suốt: bán một ghế trong hai yêu cầu đồng thời

Giả sử hệ thống bán vé lưu mỗi ghế thuộc một suất chiếu theo khóa logic:

~~~text
key = "show:show-42:seat:A12"

{
  "showId": "show-42",
  "seatId": "A12",
  "state": "AVAILABLE",
  "holderId": null,
  "holdToken": null,
  "holdExpiresAt": null,
  "version": 11
}
~~~

### Bất biến

**INV-01:** Một ghế của một suất chiếu không có hai booking đã xác nhận còn hiệu lực.

**INV-02:** Tại một thời điểm, một hold hợp lệ chỉ thuộc một người giữ ghế; việc xác nhận phải chứng minh quyền giữ còn hiệu lực.

**INV-03:** Một yêu cầu xác nhận cùng idempotency key không sinh nhiều booking hay nhiều lần thu tiền độc lập.

### Đường xử lý minh họa

~~~text
Khách X                    Trạng thái có thẩm quyền              Khách Y
  |                                 |                               |
  |--- HOLD A12 ------------------->|<---------------- HOLD A12 ----|
  |                                 |                               |
  |                 Conditional update: AVAILABLE -> HELD           |
  |                                 |                               |
  |<-- HOLD_SUCCESS(token-X) -------|--------- HOLD_REJECTED ------>|
  |                                 |                               |
  |--- CONFIRM(token-X) ----------->|                               |
  |                                 |                               |
  |           Kiểm tra holdToken, hạn giữ và điều kiện hiện tại      |
  |           chuyển HELD -> CONFIRMED bằng cập nhật nguyên tử       |
  |                                 |                               |
  |<-- CONFIRMED -------------------|                               |
~~~

Trong mô hình này, chỉ một lời gọi **conditional update** có thể chuyển ghế từ AVAILABLE sang HELD tại một thời điểm. Người thất bại nhận kết quả rõ ràng và có thể chọn ghế khác.

**Những chi tiết phải định nghĩa thêm để bất biến thật sự có hiệu lực:**

1. **Hết hạn giữ chỗ:** hệ dùng chính sách thời gian được tin cậy; một hold hết hạn chỉ được thay thế qua thao tác có điều kiện. Có thể cần token thế hệ (**fencing token**) để một tiến trình cũ không xác nhận sau khi quyền giữ đã chuyển sang người khác.
2. **Xác nhận và thu tiền:** trạng thái ghế và cổng thanh toán không tự động thuộc một transaction. Có thể cần trạng thái trung gian, bù trừ hoàn tiền và đối soát nếu thanh toán thành công nhưng ghế không còn xác nhận được.
3. **Retry do timeout:** người dùng không biết thao tác đã thành công hay chưa. Gửi lại cùng idempotency key phải đọc hoặc phục hồi kết quả cũ; không tạo một booking mới.
4. **Danh sách ghế trên giao diện:** có thể lấy từ cache hoặc replica chậm. API **HOLD/CONFIRM** vẫn phải kiểm tra tại nguồn có thẩm quyền.
5. **Nút lỗi/chuyển leader:** bảo đảm ghi và đọc cần được sản phẩm/cấu hình hỗ trợ; sơ đồ điều kiện nguyên tử chưa tự bảo đảm tính nhất quán sau sự cố mạng hoặc failover.

Nếu quy trình chỉ kiểm tra “A12 còn trống” trên replica rồi ghi xác nhận độc lập, bất biến rất dễ bị phá vỡ. Nếu ghi có điều kiện tại cùng ranh giới có thẩm quyền, hệ có thể từ chối một trong hai yêu cầu dù cả hai từng nhìn thấy ghế trống.

## 8. Khi nào có thể chấp nhận nhất quán cuối cùng?

**Eventual consistency** thường mô tả việc các bản sao sẽ hội tụ khi không còn thay đổi mới và các điều kiện vận hành cần thiết được đáp ứng. Nó **không xác định một thời gian trễ cố định**, cũng không cam kết mọi phép cập nhật nhiều đối tượng đều giữ bất biến. Cần thêm mục tiêu độ mới, điều kiện truy cập và quy trình phục hồi.

Một cách tách thiết kế hữu ích:

| Dữ liệu hoặc thao tác | Cam kết phù hợp có thể cân nhắc | Lý do |
| --- | --- | --- |
| Kết quả cuối cùng của giao dịch tiền | Kiểm tra có thẩm quyền, idempotency và đối soát chặt | Sai lệch gây thiệt hại trực tiếp |
| Bán một ghế không trùng | Quyền xác nhận duy nhất qua cập nhật có điều kiện/giao dịch phù hợp | Không thể chỉ bù bằng cập nhật giao diện |
| Màn hình xem ghế còn trống | Có thể hiển thị bản chiếu gần thời gian thực; kiểm tra lại khi giữ ghế | Người dùng có thể thấy ghế vừa được chọn đã hết |
| Trang “đơn hàng của tôi” | Có thể đồng bộ trễ, nhưng sau khi tạo đơn nên hỗ trợ đọc được kết quả của chính mình khi cần | Tránh người mua thử thanh toán lại vì tưởng chưa thành công |
| Lượt xem, đề xuất, số lượng tương tác | Có thể chấp nhận hội tụ về sau với độ trễ được đo | Lỗi thường là sai lệch quan sát có thể sửa |
| Bảng điều khiển quản trị tài chính | Có thể dùng bản tổng hợp trễ nếu được ghi nhãn thời điểm và có đường đối soát | Báo cáo không nên bị nhầm với số liệu quyết toán tức thời |

Cần phân biệt một số kỳ vọng quan sát:

- **Read-your-writes:** người dùng sau khi ghi sẽ đọc thấy thay đổi của chính mình theo phạm vi cam kết.
- **Monotonic reads:** sau khi đã nhìn thấy một phiên bản mới, người dùng không bị đưa về phiên bản cũ hơn trong cùng phạm vi bảo đảm.
- **Causal ordering:** các thay đổi có quan hệ nhân quả được quan sát theo thứ tự phù hợp.
- **Strong/linearizable operation:** một thao tác có thể được xem như có một điểm hiệu lực nguyên tử theo hợp đồng hệ cung cấp.

Các mức bảo đảm này khác nhau và còn phụ thuộc giao thức, cấu hình, vùng đọc/ghi hoặc giao dịch. **Đọc nhất quán hơn không tự khắc phục điều kiện cần transaction xuyên nhiều bản ghi**; ngược lại, một luồng cập nhật có thẩm quyền được bảo vệ tốt vẫn có thể cho phép bản chiếu bên ngoài trễ vài giây.

## 9. Gắn bất biến với đặc điểm tải dữ liệu

Trong chương “Yêu cầu và tải dữ liệu”, bất biến không thể đứng một mình: mức tranh chấp và cách phân bố truy cập ảnh hưởng trực tiếp đến chi phí giữ bất biến.

Giả sử cửa hàng bán 20.000 vé cho cùng một buổi hòa nhạc. Hầu hết yêu cầu cùng nhắm vào một tập ghế rất nhỏ. Một thiết kế ghi có điều kiện có thể đúng về nghiệp vụ nhưng các khóa nóng có thể bị tranh chấp cao.

Khi khảo sát workload, nên ghi:

| Thuộc tính tải | Câu hỏi | Ý nghĩa đối với bất biến |
| --- | --- | --- |
| **Tỷ lệ đọc/ghi** | Bao nhiêu lần xem so với đặt vé? | Có thể tách bản chiếu đọc nhanh khỏi đường chốt quyền sở hữu |
| **Độ tập trung khóa** | Nhiều yêu cầu cùng tranh một ghế/SKU không? | Xác định hot key và chi phí điều kiện nguyên tử |
| **Mức đồng thời cao nhất** | Giờ mở bán có bao nhiêu ghi tranh chấp? | Cần dự toán retry, giới hạn tải và thất bại hợp lệ |
| **Phân bố vùng địa lý** | Người mua/nguồn ghi ở nhiều region? | Độ trễ và cơ chế failover ảnh hưởng đường xác nhận |
| **Yêu cầu độ trễ** | API xác nhận phải trả trong bao lâu? | Có thể phải trả PENDING thay vì “thành công” khi chưa đủ chắc chắn |
| **Số đối tượng liên quan** | Một giao dịch động tới một bản ghi hay nhiều partition? | Quyết định có cần transaction hoặc mô hình bù trừ |
| **Mức chấp nhận phục hồi** | Có thể đối soát trong 30 giây hay phải chắc chắn ngay? | Phân biệt kiểm tra đồng bộ với xử lý bất đồng bộ |

### Ví dụ: chọn sai điểm kiểm tra vì ưu tiên độ trễ

~~~text
Thiết kế A:
  Đọc tồn từ cache -> thấy 1 -> lập tức báo "đặt hàng thành công"
  Sau đó mới thử trừ tồn trong database.

Thiết kế B:
  Đọc tồn từ cache -> hiển thị khả dụng tham khảo.
  Khi người dùng đặt:
    kiểm tra và giữ tồn bằng ghi có điều kiện tại nguồn có thẩm quyền
    -> chỉ báo "đã giữ hàng" nếu thao tác thành công.
  Thanh toán và xác nhận cuối cùng theo quy trình có trạng thái.
~~~

Thiết kế A có thể trả lời nhanh nhưng lời hứa “đã mua thành công” được phát trước khi bất biến được bảo vệ. Thiết kế B xác định ranh giới nghiệp vụ rõ hơn: UI được phép nhanh và hơi cũ, còn bước cấp quyền giữ hàng buộc phải qua thao tác đủ mạnh.

Nếu nguồn dữ liệu có thẩm quyền tạm thời không thể xác nhận, hệ cần chính sách: **từ chối**, **cho đặt chờ**, hay **chấp nhận rủi ro trong một hạn mức**. Mỗi lựa chọn là quyết định kinh doanh, không nên ngầm chuyển thành “thành công”.

## 10. Những biện pháp thường dùng và điều chúng không tự giải quyết

| Biện pháp | Giúp ích gì? | Không nên suy ra điều gì? |
| --- | --- | --- |
| **Conditional write / compare-and-set** | Bảo vệ điều kiện trên một phạm vi cập nhật nguyên tử có hỗ trợ | Không tự bảo vệ mọi điều kiện ở bản ghi khác |
| **Unique constraint / khóa duy nhất** | Ngăn trùng định danh trong phạm vi ràng buộc hỗ trợ | Không tự đảm bảo toàn bộ quy trình liên dịch vụ hoàn tất |
| **Transaction với cô lập phù hợp** | Phối hợp nhiều đọc/ghi theo hợp đồng của hệ quản trị | Không mặc nhiên bao trùm cổng thanh toán hay hàng đợi bên ngoài |
| **Replication** | Tăng khả năng chịu lỗi, đôi khi tăng khả năng phục vụ đọc | Không thay thế backup hoặc tự đảm bảo đọc mới nhất |
| **Quorum/read-write concern** | Điều chỉnh mức xác nhận và đọc theo sản phẩm | Không phải công thức bảo đảm mọi bất biến; còn phụ thuộc xung đột, failover và semantics |
| **Idempotency** | Hạn chế tạo tác dụng phụ trùng do retry | Không sửa được tranh chấp giữa hai yêu cầu nghiệp vụ khác nhau |
| **Saga/compensation** | Quản lý tiến trình nhiều bước và hậu quả khi thất bại | Không biến nhiều dịch vụ thành một transaction nguyên tử |
| **Eventual consistency** | Cho phép lan truyền/chiếu dữ liệu bất đồng bộ, tối ưu một số đường đọc | Không nói sai lệch được phép kéo dài bao lâu nếu không định nghĩa SLO |
| **Reconciliation** | Phát hiện và sửa trạng thái lệch sau khi xảy ra | Không làm biến mất chi phí/hậu quả đã gây ra trước lúc sửa |

Một kỹ thuật có thể cần phối hợp với kỹ thuật khác. Ví dụ **một khóa idempotency** ngăn hai lần gửi lại cùng yêu cầu thanh toán, nhưng **hai yêu cầu khác khóa** vẫn có thể cùng tranh quyền mua ghế; lúc này cần thêm điều kiện sở hữu ghế tại commit.

## 11. Cách viết tài liệu yêu cầu và hậu quả nhất quán dữ liệu

Trước khi triển khai NoSQL, có thể dùng một phiếu yêu cầu ngắn cho mỗi bất biến quan trọng:

~~~text
ID:
Tên bất biến:
Chủ sở hữu nghiệp vụ:
Đối tượng và phạm vi khóa:
Biểu thức/trạng thái nào được phép:
Các thao tác có thể thay đổi trạng thái:
Thời điểm bất biến phải được giữ:
Nguồn dữ liệu có thẩm quyền:
Có bao nhiêu đối tượng/partition liên quan:
Những luồng ghi đồng thời hoặc retry có thể xảy ra:
Phần nào được phép đọc trễ? Mức trễ tối đa:
Khi không xác nhận được trạng thái: FAIL / PENDING / QUOTA?
Hậu quả nếu vi phạm:
Biện pháp phát hiện:
Cách khắc phục/đối soát:
Ngưỡng cảnh báo và người xử lý:
Dấu hiệu cần kiểm chứng khi triển khai:
~~~

Bản ghi mẫu cho hệ quản lý kho:

~~~text
ID: INV-STOCK-01
Tên: Không cấp phát quá ngân sách tồn cho SKU

Phạm vi:
  (warehouseId, sku), trên lượng hàng thực sự sẵn sàng để cấp phát.

Bất biến:
  confirmedAllocatedQty <= allowedAllocationBudget
  tại mỗi lần xác nhận cấp phát.
  Nếu kinh doanh cho phép oversell, budget phải bao gồm hạn mức được phê duyệt.

Hành động:
  reserve, confirm, cancel, release, stock adjustment, stock reconciliation.

Tải:
  Nhiều yêu cầu đồng thời cho SKU flash sale;
  cập nhật tồn từ kho vận có thể đến muộn hoặc lặp.

Điểm quyết định:
  Một cơ chế có thẩm quyền áp dụng phép cập nhật có điều kiện
  hoặc giao dịch phù hợp trên cùng phạm vi cấp phát.

Đọc được phép trễ:
  Product listing được trễ trong giới hạn do sản phẩm quy định.
  Quyết định cấp phát không dựa duy nhất vào listing.

Hậu quả:
  Thiếu hàng đã cam kết, phải hủy đơn/hoàn tiền,
  tăng số yêu cầu hỗ trợ và chi phí vận hành.

Lỗi và hồi phục:
  Khi không thể giữ hàng, không báo "đã cấp phát".
  Sự kiện stock adjustment được deduplicate, kiểm tra version/sequence;
  đối soát số lượng cấp phát với chứng từ kho.
~~~

Không được mặc định rằng trường **stock** chỉ có một nghĩa. Phải phân biệt số thực tế trong kho, số sẵn sàng bán, số đã giữ, số đã xuất, số đang chuyển kho, hàng hoàn và hạn mức oversell; nếu định nghĩa các số này không rõ, một hệ thống “nhất quán” về mặt kỹ thuật vẫn có thể ra quyết định nghiệp vụ sai.

### Bốn câu hỏi cần hỏi nhóm sản phẩm

- “Nếu hai khách cùng thao tác trong một mili giây, **ai được thắng**, và kết quả nào được công bố cho người thua?”
- “Khi một nơi đã ghi thành công nhưng nơi khác chưa nhìn thấy, **người dùng được phép làm gì tiếp**?”
- “Nếu API timeout sau khi phía server xử lý xong, lần retry **được hiểu là yêu cầu cũ hay yêu cầu mới**?”
- “Khi kết quả chưa xác định, hệ thống **chờ xác minh, từ chối hay tạm chấp nhận rủi ro**?”

Đây là câu hỏi nghiệp vụ trước khi là câu hỏi về API của database.

## 12. Các tình huống thực hành

### Tình huống A: Số lượt thích của bài viết

Người A thích bài viết, replica ở vùng khác vẫn hiển thị 99 thay vì 100 trong vài giây.

- **Bất biến có thể quan trọng:** một tài khoản không được tính hai lượt thích cho cùng bài viết theo quy tắc sản phẩm.
- **Dữ liệu có thể chấp nhận trễ:** tổng số likes hiển thị.
- **Hậu quả:** số hiển thị chậm thường nhẹ hơn việc đếm trùng, nhưng mức cho phép còn phụ thuộc sản phẩm.
- **Hướng thiết kế:** đảm bảo tính duy nhất theo cặp **(userId, postId)** tại nguồn xử lý thao tác; tổng hợp số đếm có thể là projection bất đồng bộ.

### Tình huống B: Chuyển tiền giữa hai ví

Ví A chuyển 100.000 đồng sang ví B. Hệ đã trừ A nhưng lỗi mạng trước bước cộng B.

- **Bất biến cần làm rõ:** tổng nghĩa vụ tài chính phải được hạch toán đúng; mỗi giao dịch có một kết quả định danh, không ghi nhận hai lần từ retry.
- **Hậu quả:** mất cân đối giữa người gửi, người nhận và sổ cái; thiệt hại tiền và khó đối soát.
- **Hướng thiết kế:** một sổ cái có thẩm quyền với mô hình bút toán và cơ chế ghi nguyên tử phù hợp cho phạm vi kế toán; quy trình chuyển trạng thái và đối soát khi các dịch vụ ngoài không cùng transaction. Không nên chỉ gửi hai lệnh cập nhật ví độc lập rồi coi là hoàn tất.

### Tình huống C: Flash sale có 1 đơn vị hàng

Hai người cùng đọc số tồn là 1 rồi cùng nhấn mua.

- **Bất biến:** số lượng cấp phát xác nhận không được vượt ngân sách tồn theo chính sách đã định.
- **Hậu quả:** ít nhất một khách phải chờ hoặc hủy nếu không có hàng thay thế.
- **Hướng thiết kế:** giữ quyền cấp phát bằng phép ghi có điều kiện; kết quả giỏ hàng chỉ là dự kiến cho tới khi đã giữ được hàng. Có thể quy định timeout, hàng đợi và cơ chế giải phóng quyền giữ.

### Tình huống D: Đơn đã hủy nhưng sự kiện “đã đóng gói” đến muộn

Sự kiện đến muộn cố đưa đơn từ CANCELLED về PACKED.

- **Bất biến:** trạng thái đơn chỉ được đi qua các chuyển trạng thái hợp lệ, có quy tắc riêng khi sự kiện muộn.
- **Hậu quả:** giao đơn đáng lẽ không được giao, khởi tạo thu tiền hoặc hoàn sai.
- **Hướng thiết kế:** kiểm tra version/sequence hoặc điều kiện chuyển trạng thái tại cập nhật nguồn; xử lý sự kiện lặp hoặc ngoài thứ tự theo chính sách xác định, không ghi đè trạng thái mù.

### Tình huống E: Trang quản trị cần báo cáo “thời gian thực”

Bảng điều khiển tính doanh thu từ luồng sự kiện, trễ vài chục giây so với sổ cái.

- **Bất biến:** tổng hạch toán chính thức phải tuân thủ nguồn sổ cái và quy tắc ghi nhận.
- **Dữ liệu có thể trễ:** bảng điều khiển nếu ghi rõ mốc cập nhật và không dùng làm căn cứ quyết toán tức thời.
- **Hậu quả:** người điều hành có thể quyết định sai nếu tưởng bảng hiển thị đã phản ánh toàn bộ giao dịch.
- **Hướng thiết kế:** phân biệt báo cáo ước tính và số quyết toán; theo dõi độ trễ sự kiện, mất sự kiện và đối soát nguồn.

## 13. Bài tập áp dụng trước khi chọn NoSQL

Một nền tảng đặt lịch có các yêu cầu sau:

~~~text
R1. Một bác sĩ không thể nhận hai cuộc hẹn đã xác nhận có giờ chồng lấp.
R2. Danh sách khung giờ trên trang tìm kiếm được phép cập nhật chậm.
R3. Nếu khách nhấn đặt lịch hai lần do mất mạng, không tạo hai cuộc hẹn.
R4. Khi lịch hẹn bị hủy, email hủy được gửi trong vòng 2 phút.
R5. Trung bình 500 lượt xem cho mỗi lượt đặt;
    vào giờ cao điểm có nhiều khách tranh cùng giờ đẹp.
~~~

Hãy thử điền phiếu bất biến bằng các câu hỏi: dữ liệu nào phải kiểm tra tại lúc xác nhận, khóa nào dùng để phát hiện xung đột, phần nào có thể trả lời từ cache, có giao dịch nào vượt quá một đối tượng hay không, và nếu kết quả gửi email chậm thì có phải cuộc hẹn đã bị đặt trùng?

**Gợi ý phân tích:**

| Yêu cầu | Bất biến hay cam kết nào? | Điểm cần xử lý |
| --- | --- | --- |
| **R1** | Bất biến an toàn trên các khoảng thời gian đã xác nhận của một bác sĩ | Chống tranh chấp và kiểm tra **chồng lấp khoảng**, không chỉ trùng chính xác một timestamp |
| **R2** | Độ mới dữ liệu đọc | Có thể cache danh sách giờ, nhưng xác nhận phải kiểm tra tại nguồn |
| **R3** | Idempotency cho một ý định đặt lịch | Dùng mã yêu cầu ổn định và tra cứu kết quả khi retry |
| **R4** | SLO hoàn tất tác vụ phụ | Outbox/queue, retry, giám sát trễ; email chậm không làm thay đổi quyền sở hữu lịch hẹn |
| **R5** | Đặc điểm tải và tranh chấp | Tối ưu đường đọc riêng; đo hot key, thất bại do tranh chấp, độ trễ xác nhận |

**Lưu ý với R1:** nếu ca khám có thời lượng khác nhau, ràng buộc “unique theo bác sĩ + thời điểm bắt đầu” không đủ. Hai cuộc hẹn bắt đầu lúc 09:00 và 09:15, kéo dài 30 phút, vẫn chồng lấp. Bất biến phải được phát biểu trên **khoảng thời gian** và bảo vệ bằng mô hình dữ liệu/giao dịch đủ mạnh cho kiểm tra đó.

## 14. Các dấu hiệu quan sát trong vận hành

Bất biến có ý nghĩa thực tiễn khi hệ thống có cách phát hiện vi phạm hoặc dấu hiệu sắp vi phạm. Một số chỉ số cần cân nhắc:

- **Số trường hợp xác nhận trùng quyền sở hữu:** chẳng hạn hai booking còn hiệu lực cho cùng ghế và suất.
- **Tỷ lệ ghi có điều kiện thất bại do tranh chấp:** tăng bất thường có thể cho thấy tải dồn vào một khóa; thất bại vì điều kiện không hợp lệ cũng có thể là hoạt động bình thường trong flash sale.
- **Số giao dịch ở trạng thái chưa rõ:** đơn chờ xác minh thanh toán, giữ hàng hết hạn nhưng chưa được xử lý, bước saga chưa hoàn thành.
- **Số tác vụ phải đối soát hoặc bù trừ:** cho biết mức độ gián đoạn và chi phí phục hồi nghiệp vụ.
- **Độ trễ bản chiếu và replica:** đo thời điểm nguồn có thay đổi so với thời điểm dữ liệu trở nên quan sát được ở nơi khác, khi hệ có khả năng đo.
- **Sự kiện trùng hoặc sai thứ tự:** tỷ lệ bị deduplicate, bị từ chối do version cũ hoặc phải xử lý lại.
- **Mức chênh lệch với nguồn có thẩm quyền:** ví dụ số liệu tổng hợp so với sổ cái, tồn kho cấp phát so với chứng từ đã xác nhận.

Chỉ số vận hành cần gắn với chính sách. Chẳng hạn nhiều lần **conditional write bị từ chối** chưa chắc là sự cố; đó có thể là bằng chứng cơ chế bảo vệ bất biến đang hoạt động đúng. Ngược lại, tỷ lệ tranh chấp tăng có thể dẫn tới độ trễ hoặc trải nghiệm không chấp nhận được và cần điều chỉnh cách phân phối tải.

## 15. Tự kiểm tra

**Câu 1.** Sàn thương mại điện tử hiển thị “còn hàng” từ cache chậm 3 giây, nhưng khi bấm mua, hệ kiểm tra và giữ hàng thành công tại nguồn có thẩm quyền trước khi xác nhận. Có phải chắc chắn đã vi phạm bất biến tồn kho không?

**Trả lời:** Không. Đây có thể là **độ trễ hiển thị** được phép. Bất biến cấp phát phụ thuộc bước giữ hàng và xác nhận có thẩm quyền. Cần xem SLO màn hình và cam kết người mua.

**Câu 2.** Hai thao tác khác nhau cùng có idempotency key hay không thì có bảo vệ được việc bán trùng ghế không?

**Trả lời:** Không đủ. Idempotency bảo vệ **lặp cùng một ý định** theo phạm vi khóa; để ngăn hai khách khác nhau mua cùng ghế cần thêm ràng buộc cạnh tranh tại điểm cấp quyền sở hữu.

**Câu 3.** Một hệ có ba replica. Có thể tự kết luận rằng sau khi ghi thành công, đọc từ replica bất kỳ sẽ thấy dữ liệu mới nhất không?

**Trả lời:** Không. Phải xem mô hình replication, mức xác nhận ghi, cách chọn replica đọc, cơ chế failover và hợp đồng nhất quán thực tế.

**Câu 4.** Nếu mọi thao tác cập nhật riêng lẻ đều nguyên tử, liệu bất biến “luôn có ít nhất một nhân viên trực” trải qua nhiều bản ghi đã được bảo vệ?

**Trả lời:** Chưa chắc. Hai thao tác riêng biệt có thể tạo **write skew** khi mỗi người tắt ca trực dựa trên bản chụp chưa phản ánh thao tác còn lại. Cần ranh giới đồng bộ/giao dịch phù hợp cho toàn điều kiện.

**Câu 5.** Số lượt thích được phép trễ cập nhật 10 giây. Có đồng nghĩa người dùng được phép nhấn một lần và bị tính mười lượt không?

**Trả lời:** Không. **Độ mới của số tổng hợp** và **tính duy nhất của lượt thích** là hai yêu cầu khác nhau, có thể cần hai cơ chế xử lý khác nhau.

---

Khi mô tả một yêu cầu NoSQL, hãy luôn viết thành ba phần nối tiếp: **trạng thái nào không được sai**, **sai sẽ gây hậu quả gì**, và **hệ thống phải bảo vệ hoặc khôi phục trạng thái đó tại ranh giới nào**. Từ câu trả lời đó, mới quyết định chỗ nào cần thao tác nguyên tử hoặc giao dịch, chỗ nào có thể cập nhật bất đồng bộ, và hiệu năng cần đo ở đường đọc hay đường ghi.
