# Đánh giá chất lượng bộ kiểm thử bằng kiểm thử đột biến (mutation testing) khi phù hợp

Một bộ kiểm thử có thể chạy thành công, bao phủ nhiều dòng mã và vẫn bỏ sót những lỗi logic rất nhỏ nhưng có ảnh hưởng lớn. Ví dụ, điều kiện kiểm tra ngưỡng có thể dùng dấu lớn hơn thay vì lớn hơn hoặc bằng; phép cộng có thể bị đổi thành phép trừ; hoặc một nhánh từ chối quyền truy cập có thể bị bỏ qua. Nếu bộ kiểm thử vẫn đạt sau những thay đổi sai như vậy, có thể các kiểm thử chưa kiểm tra đủ chặt hành vi cần bảo vệ.

**Kiểm thử đột biến (mutation testing)** đánh giá khả năng phát hiện lỗi của bộ kiểm thử bằng cách cố ý tạo những thay đổi nhỏ, có kiểm soát trong mã nguồn rồi chạy lại các kiểm thử. Nếu một thay đổi làm kiểm thử thất bại, bộ kiểm thử đã phát hiện được đột biến đó. Nếu kiểm thử vẫn đạt, nhóm cần xem xét liệu đang thiếu trường hợp kiểm thử, thiếu khẳng định kết quả hay đột biến không làm thay đổi hành vi quan sát được.

Mutation testing là một kỹ thuật đánh giá chất lượng kiểm thử, không phải cách thay thế kiểm thử chức năng, review mã, phân tích rủi ro hay các loại kiểm thử khác. Nó đặc biệt hữu ích khi nhóm muốn biết một bộ unit test hoặc component test có thực sự phân biệt được hành vi đúng với những lỗi thường gặp hay không.

## 1. Mutation testing là gì?

Mutation testing tạo ra các phiên bản biến đổi của chương trình, mỗi phiên bản thường chứa một thay đổi nhỏ được gọi là **mutant** (bản đột biến). Các thay đổi được tạo theo những toán tử đột biến (mutation operators), chẳng hạn:

- Đổi toán tử so sánh >= thành >.
- Đổi phép cộng + thành phép trừ -.
- Đảo điều kiện đúng/sai.
- Bỏ một điều kiện trong biểu thức logic.
- Thay một hằng số hoặc giá trị trả về.
- Bỏ lời gọi một phương thức có tác động quan sát được.

Sau khi tạo mutant, công cụ chạy cùng bộ kiểm thử trên phiên bản đã biến đổi. Nếu một kiểm thử thất bại vì hành vi bị thay đổi, mutant được xem là **bị tiêu diệt (killed)**. Nếu tất cả kiểm thử liên quan vẫn đạt, mutant **sống sót (survived)**.

Ví dụ, mã gốc cho phép áp dụng ưu đãi khi tổng tiền đạt ngưỡng:

~~~java
boolean eligible(long total, long minimum) {
    return total >= minimum;
}
~~~

Một mutant có thể đổi >= thành >. Nếu bộ kiểm thử có trường hợp total bằng minimum và xác minh kết quả phải là true, mutant sẽ bị tiêu diệt. Nếu bộ kiểm thử chỉ kiểm tra một giá trị lớn hơn ngưỡng và một giá trị nhỏ hơn ngưỡng, mutant có thể sống sót vì các trường hợp đó vẫn cho cùng kết quả.

Điều này cho thấy mutation testing kiểm tra chất lượng của các khẳng định trong test suite: kiểm thử có phân biệt được hành vi đúng với một thay đổi sai cụ thể hay không?

## 2. Phân biệt mutation testing với các chỉ số bao phủ khác

Các chỉ số bao phủ truyền thống cho biết một phần mã hoặc cấu trúc đã được thực thi. Chúng không luôn cho biết kết quả có được kiểm tra chính xác hay không.

| Kỹ thuật/chỉ số | Câu hỏi trả lời | Giới hạn |
|---|---|---|
| Line coverage | Dòng mã nào đã được thực thi? | Một dòng được chạy nhưng không có assertion có thể vẫn đạt coverage |
| Statement coverage | Câu lệnh nào đã được thực thi? | Không cho biết mọi kết quả đều được xác minh |
| Branch coverage | Các nhánh quyết định nào đã được đi qua? | Không chứng minh assertion phân biệt được mọi lỗi trong nhánh |
| Condition coverage | Các điều kiện con đã nhận giá trị đúng và sai chưa? | Không nhất thiết phát hiện mọi tương tác hoặc lỗi kết quả |
| Mutation testing | Bộ kiểm thử có phát hiện những thay đổi sai được tạo ra không? | Phụ thuộc vào tập toán tử và mutant; không chứng minh không còn lỗi |

Ví dụ, một test gọi hàm tính phí và đi qua dòng fee = amount * rate, nhưng không kiểm tra giá trị fee. Line coverage có thể là 100% trong khi một mutant đổi * thành + vẫn sống sót.

Vì vậy, coverage và mutation testing cung cấp những góc nhìn bổ sung. Coverage giúp tìm vùng chưa được thực thi; mutation testing giúp tìm vùng đã được thực thi nhưng có thể chưa được kiểm tra đủ chặt.

## 3. Các loại kết quả khi chạy mutation testing

Không phải mọi mutant đều có thể được phân loại đơn giản là killed hoặc survived. Cần hiểu trạng thái của từng mutant để không diễn giải sai điểm số.

| Kết quả | Ý nghĩa | Cách xử lý |
|---|---|---|
| Killed | Ít nhất một kiểm thử thất bại vì mutant làm thay đổi hành vi được quan sát | Ghi nhận kiểm thử phát hiện mutant và xác minh lỗi thất bại đúng nguyên nhân |
| Survived | Tất cả kiểm thử liên quan vẫn đạt khi chạy mutant | Xem xét thiếu test case, thiếu assertion hoặc mutant không ảnh hưởng kết quả được quan sát |
| No coverage | Các kiểm thử được chạy không thực thi vị trí mã bị đột biến | Bổ sung đường đi hoặc dữ liệu để thực thi vùng đó nếu vùng có ý nghĩa |
| Equivalent | Mutant không tạo ra khác biệt hành vi có thể quan sát trong miền đầu vào hợp lệ | Loại khỏi mẫu số sau khi có căn cứ; ghi lý do |
| Invalid / compile error | Mutant không tạo được chương trình có thể chạy, ví dụ mã biến đổi không biên dịch | Phân loại riêng theo công cụ; không xem như bằng chứng bộ kiểm thử đã phát hiện lỗi |
| Timeout / inconclusive | Không thể kết luận do kiểm thử treo, môi trường lỗi hoặc thời gian chạy vượt giới hạn | Điều tra hạ tầng, tính ổn định và cấu hình trước khi chấm điểm |

### 3.1. Killed mutant

Mutant bị tiêu diệt khi một hoặc nhiều kiểm thử thất bại. Cần xác minh thất bại thực sự do khác biệt hành vi, chẳng hạn assertion về kết quả sai, trạng thái sai hoặc tác động phụ không đúng.

Một test thất bại vì môi trường không sẵn sàng, dữ liệu dùng chung hoặc lỗi khởi động không chứng minh mutant đã bị phát hiện. Công cụ mutation testing có thể đánh dấu mutant killed khi tiến trình kiểm thử thất bại, nhưng nhóm vẫn cần xem nguyên nhân.

### 3.2. Survived mutant

Mutant sống sót là tín hiệu cần điều tra. Có thể:

- Chưa có test case đi qua điều kiện bị thay đổi.
- Có test case đi qua nhưng không kiểm tra kết quả liên quan.
- Assertion quá rộng, chỉ kiểm tra khác null hoặc không có exception.
- Test chỉ kiểm tra một phía của ranh giới.
- Dữ liệu không tạo ra khác biệt giữa mã gốc và mutant.
- Hành vi bị thay đổi không nằm trong yêu cầu hoặc miền đầu vào hợp lệ.

Không nên lập tức thêm một test chỉ để làm mutant chết. Trước tiên hãy xác định hành vi nào cần được bảo vệ và nguồn nào xác nhận kết quả đúng.

### 3.3. No coverage

No coverage cho biết test suite chưa thực thi vị trí có mutant. Đây thường là khoảng trống về đường đi hoặc dữ liệu. Tuy nhiên, nếu mã thuộc phần không được dùng, mã sinh tự động hoặc nhánh không thể đạt đến, cần đánh giá trước khi bổ sung kiểm thử.

### 3.4. Equivalent mutant

Equivalent mutant là phiên bản mã khác về mặt văn bản nhưng có hành vi tương đương với mã gốc trong miền đầu vào và điều kiện đang xét. Ví dụ, một thay đổi biểu thức có thể được trình biên dịch tối ưu hoặc hai nhánh có cùng kết quả theo một bất biến đã được bảo đảm.

Việc chứng minh tương đương có thể khó và đôi khi không thể tự động hóa hoàn toàn. Không nên gắn nhãn equivalent chỉ vì chưa tìm được test làm mutant thất bại. Cần có lập luận dựa trên miền đầu vào, ràng buộc và ngữ nghĩa chương trình; ghi lại lý do loại trừ để điểm số có thể kiểm tra lại.

## 4. Mutation score và cách diễn giải

Một chỉ số phổ biến là mutation score:

\[
\text{Mutation Score} =
\frac{\text{Số mutant bị tiêu diệt}}
{\text{Mutant bị tiêu diệt} + \text{Mutant sống sót}}
\times 100\%
\]

Trong cách tính này, mẫu số gồm các mutant hợp lệ đã được đánh giá và có kết quả killed hoặc survived. Mutant equivalent, không biên dịch, no coverage và timeout chưa kết luận được báo cáo riêng, không tính như mutant đã bị tiêu diệt. Một số công cụ có quy ước khác; khi sử dụng báo cáo của công cụ, cần nêu rõ mẫu số và chính sách loại trừ để có thể so sánh đúng.

Ví dụ, công cụ tạo 120 mutant:

- 72 mutant bị tiêu diệt.
- 28 mutant sống sót.
- 10 mutant không được test thực thi (no coverage).
- 7 mutant tương đương đã được xác minh.
- 2 mutant không biên dịch.
- 1 mutant timeout chưa kết luận.

Mutation score trên 100 mutant đã được đánh giá (72 killed và 28 survived) là:

\[
\frac{72}{72 + 28}\times 100\% = 72\%
\]

Tuy nhiên, báo cáo vẫn phải nêu 2 mutant compile error và 1 mutant timeout, cùng 10 mutant no coverage và 7 mutant equivalent. Nếu không, người đọc có thể hiểu nhầm rằng toàn bộ 120 mutant đều đã được đánh giá.

Không nên coi một ngưỡng như 80% hoặc 90% là chuẩn chung cho mọi dự án. Mức phù hợp phụ thuộc ngôn ngữ, loại mã, toán tử được bật, chất lượng bộ kiểm thử, miền đầu vào và rủi ro nghiệp vụ. Một vùng tính tiền hoặc phân quyền có thể cần xem xét kỹ hơn vùng chuyển đổi hiển thị ít rủi ro.

## 5. Các toán tử đột biến thường gặp

Mutation testing sử dụng nhiều loại thay đổi để mô phỏng lỗi lập trình. Tập toán tử phụ thuộc công cụ, ngôn ngữ và cấu hình.

| Nhóm toán tử | Thay đổi minh họa | Lỗi có thể mô phỏng |
|---|---|---|
| Toán tử số học | + thành -, * thành / | Sai công thức hoặc tính toán |
| Toán tử quan hệ | >= thành >, == thành != | Sai ranh giới hoặc điều kiện so sánh |
| Toán tử logic | && thành ||, đảo ! | Sai kết hợp điều kiện |
| Hằng số | 10 thành 0, 1, hoặc giá trị lân cận | Sai ngưỡng, mặc định hoặc giới hạn |
| Giá trị trả về | true thành false, trả null thay vì đối tượng | Sai kết quả của hàm |
| Điều kiện nhánh | Bỏ hoặc đảo điều kiện if | Chọn nhánh sai |
| Lệnh gọi phương thức | Bỏ lời gọi hoặc thay đổi lời gọi | Thiếu tác động phụ hoặc xác minh |
| Giá trị biên | index < size thành index <= size | Lỗi ngoài phạm vi, off-by-one |
| Xử lý ngoại lệ | Bỏ bắt lỗi hoặc thay đổi kiểu lỗi | Sai hành vi khi có sự cố |
| Toán tử tăng/giảm | i++ thành i-- | Sai vòng lặp hoặc chỉ số |

Không phải công cụ nào cũng hỗ trợ mọi toán tử. Một số công cụ tạo mutant ở mã nguồn; một số tạo đột biến ở bytecode hoặc ở mức biểu diễn trung gian. Hãy đọc cấu hình để biết loại lỗi nào đang được mô phỏng và vùng mã nào không được hỗ trợ.

## 6. Ví dụ thực tế: kiểm tra logic tính phí vận chuyển

Giả sử quy tắc quy định miễn phí vận chuyển khi giá trị hàng hóa từ 500.000 đồng trở lên. Mã Java đơn giản:

~~~java
public long shippingFee(long subtotal) {
    if (subtotal >= 500_000L) {
        return 0L;
    }
    return 30_000L;
}
~~~

Một bộ kiểm thử có thể gồm:

~~~java
@Test
void freeShippingAtMinimum() {
    assertEquals(0L, service.shippingFee(500_000L));
}

@Test
void freeShippingAboveMinimum() {
    assertEquals(0L, service.shippingFee(500_001L));
}

@Test
void chargeBelowMinimum() {
    assertEquals(30_000L, service.shippingFee(499_999L));
}
~~~

### 6.1. Đột biến điều kiện biên

Mutant thay:

~~~java
if (subtotal >= 500_000L) {
~~~

bằng:

~~~java
if (subtotal > 500_000L) {
~~~

Test freeShippingAtMinimum sẽ thất bại vì mutant tính phí 30.000 đồng ở đúng ngưỡng. Hai test còn lại có thể vẫn đạt. Trường hợp tại ngưỡng đã giúp bộ kiểm thử phân biệt hai cách hiểu.

### 6.2. Đột biến giá trị trả về

Một mutant có thể đổi return 30_000L thành return 0L. Test chargeBelowMinimum sẽ phát hiện thay đổi nếu assertion kiểm tra đúng số tiền.

### 6.3. Đột biến toán tử

Nếu công thức tính phí phụ thuộc khoảng cách hoặc trọng lượng, công cụ có thể thay + bằng -, * bằng / hoặc thay đổi hằng số. Test cần có dữ liệu làm cho các kết quả khác biệt và assertion đủ cụ thể.

Ví dụ này cho thấy mutation testing không tự tạo ra yêu cầu. Nhóm vẫn phải có chính sách vận chuyển đã được xác nhận và dữ liệu đại diện để biết kết quả nào đúng.

## 7. Quy trình áp dụng mutation testing

### Bước 1: Chọn phạm vi có ý nghĩa

Ưu tiên mã có logic quan trọng, nhiều điều kiện, công thức, xử lý quyền, trạng thái hoặc dữ liệu. Mutation testing thường có giá trị cao ở unit/component test nơi mutant có thể được đánh giá nhanh.

Không nhất thiết chạy trên toàn bộ repository ngay từ đầu. Có thể bắt đầu với một package, module hoặc vùng mã vừa thay đổi.

### Bước 2: Xác nhận bộ kiểm thử nền

Chạy bộ kiểm thử gốc và bảo đảm nó đạt ổn định trước khi tạo mutant. Nếu kiểm thử gốc đã thất bại hoặc không ổn định, kết quả mutation testing khó diễn giải.

Ghi lại commit, phiên bản compiler/runtime, cấu hình kiểm thử, dữ liệu và môi trường để có thể tái lập.

### Bước 3: Chọn công cụ và toán tử

Chọn công cụ phù hợp với ngôn ngữ, build system và cách chạy test. Cấu hình vùng mã, loại toán tử, timeout và cách xử lý mutant không hợp lệ. Bắt đầu với toán tử phổ biến và có khả năng mô phỏng lỗi thực tế.

### Bước 4: Sinh mutant và chạy kiểm thử

Công cụ tạo các phiên bản biến đổi, sau đó chạy test suite hoặc phần test liên quan trên từng mutant. Có thể chạy song song nếu tài nguyên đủ và môi trường không dùng chung trạng thái gây nhiễu.

### Bước 5: Phân loại kết quả

Tách killed, survived, no coverage, equivalent, compile error và timeout. Kiểm tra lý do thất bại, tránh tính các lỗi hạ tầng hoặc flaky test thành mutant killed.

### Bước 6: Điều tra mutant sống sót

Với từng mutant có ý nghĩa, xác định:

- Vị trí và toán tử bị thay đổi.
- Đường đi hoặc điều kiện cần để kích hoạt.
- Kết quả mong đợi theo yêu cầu hoặc oracle.
- Test hiện tại có thực thi vị trí đó không?
- Test có assertion kiểm tra kết quả bị ảnh hưởng không?
- Có cần thêm test, dữ liệu biên hoặc assertion không?
- Mutant có tương đương trong miền đầu vào hợp lệ không?

### Bước 7: Cải thiện bộ kiểm thử

Thêm hoặc điều chỉnh test để kiểm tra hành vi còn thiếu. Ưu tiên test có giá trị độc lập, dễ hiểu và ổn định. Không thêm assertion phụ thuộc vào chi tiết nội bộ chỉ để giết một mutant nếu chi tiết đó không phải hợp đồng cần bảo vệ.

### Bước 8: Chạy lại và báo cáo

Chạy lại test suite gốc, sau đó chạy lại mutation testing ở phạm vi đã chọn. Báo cáo mutation score cùng số lượng từng trạng thái, vùng mã, giới hạn công cụ và các rủi ro còn lại.

~~~mermaid
flowchart TD
    A["Chọn vùng mã theo rủi ro"]
    B["Chạy test suite gốc"]
    C{"Test gốc ổn định và đạt?"}
    D["Điều tra test hoặc môi trường nền"]
    E["Sinh mutant theo toán tử"]
    F["Chạy test suite trên từng mutant"]
    G["Phân loại killed, survived, no coverage, equivalent, lỗi"]
    H["Điều tra mutant sống sót có ý nghĩa"]
    I["Bổ sung test hoặc assertion phù hợp"]
    J["Chạy lại và báo cáo score cùng giới hạn"]
    A --> B --> C
    C -->|Không| D --> B
    C -->|Có| E --> F --> G --> H --> I --> J
~~~

## 8. Chọn phạm vi và tần suất theo rủi ro

Mutation testing có thể tốn nhiều thời gian vì một test suite phải được chạy nhiều lần trên các phiên bản mã biến đổi. Chi phí tăng theo số mutant, thời gian chạy test, số luồng phụ thuộc và mức độ song song.

Một cách áp dụng thực tế:

| Phạm vi | Cách sử dụng gợi ý | Lý do |
|---|---|---|
| Hàm tính toán, quy tắc nghiệp vụ quan trọng | Chạy thường xuyên hoặc theo thay đổi | Mutant dễ diễn giải, tác động trực tiếp đến kết quả |
| Phân quyền, xác thực, kiểm tra dữ liệu | Ưu tiên cao | Một điều kiện nhỏ có thể gây rủi ro lớn |
| Thành phần có nhiều nhánh và trạng thái | Chạy theo module hoặc lịch | Có nhiều cơ hội bỏ sót nhánh và điều kiện |
| Mã tích hợp với I/O hoặc dịch vụ bên ngoài | Chọn lọc | Test chậm và khó cô lập; cần cân bằng với contract/integration test |
| Mã sinh tự động, getter/setter đơn giản hoặc mã không thuộc quyền kiểm soát | Thường loại trừ có lý do | Mutant có thể ít giá trị hoặc tạo nhiễu |
| Toàn bộ repository | Chạy định kỳ hoặc trước mốc quan trọng khi khả thi | Chi phí lớn, cần tài nguyên và thời gian phù hợp |

Có thể chạy mutation testing trên pull request cho vùng mã thay đổi, theo lịch cho module quan trọng, hoặc trước phát hành cho một số thành phần rủi ro cao. Tần suất cần dựa trên thời gian chạy, chi phí và mức độ ảnh hưởng của lỗi.

## 9. Cải thiện test suite từ mutant sống sót

Mutant sống sót là đầu mối để đặt câu hỏi về chất lượng kiểm thử. Một số tình huống thường gặp:

| Nguyên nhân | Dấu hiệu | Hướng cải thiện |
|---|---|---|
| Thiếu dữ liệu biên | Mutant đổi >= thành > vẫn sống | Thêm trường hợp đúng tại ngưỡng |
| Thiếu nhánh | Mutant đảo điều kiện không bị phát hiện | Tạo dữ liệu đi qua cả hai nhánh và xác minh kết quả |
| Thiếu assertion | Test gọi hàm nhưng không kiểm tra giá trị trả về | Thêm assertion theo hợp đồng hành vi |
| Assertion quá rộng | Chỉ kiểm tra kết quả khác null hoặc không có exception | Kiểm tra giá trị, trạng thái và tác động quan trọng |
| Thiếu kiểm tra tác động phụ | Bỏ lời gọi ghi dữ liệu mà test vẫn đạt | Xác minh dữ liệu hoặc sự kiện theo yêu cầu |
| Oracle không rõ | Không biết mutant nào tạo kết quả đúng | Làm rõ quy tắc và người phê duyệt trước khi sửa test |
| Mutant tương đương | Thay đổi không tạo khác biệt trong miền hợp lệ | Chứng minh và ghi nhận lý do loại trừ |

Một test mới nên bảo vệ hành vi có ý nghĩa, không chỉ phụ thuộc vào cách triển khai hiện tại. Nếu thay đổi thiết kế mà test phải sửa dù hành vi không đổi, có thể test đang kiểm tra quá sâu chi tiết nội bộ.

## 10. Những giới hạn và rủi ro khi diễn giải mutation score

### 10.1. Equivalent mutant và chi phí phân tích

Một số mutant không thể bị tiêu diệt bởi test hợp lệ vì chúng tương đương với mã gốc trong miền đầu vào. Xác định equivalent thường cần phân tích thủ công. Nếu loại quá dễ, score bị thổi phồng; nếu không loại, score có thể thấp một cách sai lệch.

### 10.2. Mutant không đại diện cho mọi lỗi thực tế

Toán tử đột biến mô phỏng một lớp lỗi nhất định. Chúng không bao phủ mọi lỗi thiết kế, yêu cầu sai, lỗi cấu hình, lỗi tích hợp, vấn đề dữ liệu hoặc hành vi môi trường. Mutation score cao không có nghĩa phần mềm không còn lỗi.

### 10.3. Test flaky và môi trường không ổn định

Nếu test thất bại ngẫu nhiên, công cụ có thể đánh dấu mutant killed dù thay đổi mã không phải nguyên nhân. Cần có baseline ổn định, retry có kiểm soát và điều tra lỗi hạ tầng.

### 10.4. Test quá phụ thuộc chi tiết triển khai

Nếu test xác minh mọi lời gọi nội bộ hoặc cấu trúc private, nó có thể giết nhiều mutant nhưng trở nên mong manh khi refactor. Chỉ xác minh tương tác khi đó là hợp đồng hoặc tác động cần bảo vệ.

### 10.5. Điểm số có thể bị tối ưu sai mục tiêu

Khi nhóm đặt mục tiêu score cứng, người viết có thể thêm assertion hình thức, loại mutant khó hoặc điều chỉnh phạm vi để tăng điểm. Hãy dùng score làm tín hiệu điều tra, kết hợp đánh giá chất lượng test, rủi ro và lỗi thực tế.

## 11. Báo cáo kết quả mutation testing

Một báo cáo hữu ích cần cho biết phạm vi và cách tính, không chỉ đưa ra một phần trăm.

| Trường | Nội dung |
|---|---|
| Phiên bản mã | Commit hoặc build được kiểm tra |
| Phạm vi | Module, package, lớp hoặc file |
| Công cụ và cấu hình | Phiên bản công cụ, toán tử, timeout và exclusions |
| Test suite | Nhóm test và môi trường thực thi |
| Mutant được tạo | Tổng số mutant và phân bố theo toán tử |
| Killed | Số và tỷ lệ mutant bị tiêu diệt |
| Survived | Số mutant sống sót và vị trí |
| No coverage | Số mutant không được thực thi |
| Equivalent | Số mutant được loại cùng lý do |
| Invalid/timeout | Số mutant không thể đánh giá |
| Mutation score | Công thức và quy ước mẫu số |
| Hành động | Test bổ sung, rủi ro chấp nhận và người phụ trách |

Nên lưu báo cáo theo phiên bản để theo dõi xu hướng. Khi score thay đổi, kiểm tra xem nguyên nhân đến từ test suite, mã nguồn, tập toán tử, cấu hình hoặc exclusions.

## 12. Những sai lầm thường gặp

- **Xem mutation score là phần trăm lỗi đã loại bỏ:** score chỉ phản ánh khả năng phát hiện các mutant được tạo theo tập toán tử cụ thể.
- **Đồng nhất mutant killed với test tốt:** cần xác minh test thất bại vì đúng hành vi bị thay đổi.
- **Không phân biệt survived và no coverage:** một trường hợp thiếu đường đi khác với một trường hợp đã chạy nhưng thiếu assertion.
- **Loại mutant khó mà không có bằng chứng:** làm mẫu số nhỏ và score mất ý nghĩa.
- **Cố đạt 100% bằng mọi giá:** có thể tốn công cho mutant tương đương hoặc không liên quan rủi ro.
- **Chạy trên test suite không ổn định:** kết quả không thể diễn giải đáng tin.
- **Đưa mọi loại mã vào cùng phạm vi:** mã sinh tự động hoặc mã ít rủi ro có thể tạo nhiều nhiễu.
- **Chỉ nhìn score tổng:** score cao ở module này có thể che khuất vùng quan trọng khác có score thấp.
- **Không xem xét test oracle:** nếu kết quả mong đợi không rõ, nhóm không biết nên viết assertion nào.
- **Không quản lý chi phí chạy:** mutation testing có thể kéo dài pipeline và làm chậm phản hồi nếu không giới hạn phạm vi.

## 13. Checklist áp dụng mutation testing

- [ ] Bộ kiểm thử gốc đang đạt và ổn định.
- [ ] Phạm vi mã được chọn theo rủi ro và mục tiêu rõ ràng.
- [ ] Công cụ, phiên bản và toán tử đột biến đã được xác định.
- [ ] Có nguồn xác nhận hành vi mong đợi cho vùng mã quan trọng.
- [ ] Các mutant được phân loại rõ: killed, survived, no coverage, equivalent, invalid hoặc timeout.
- [ ] Thất bại của test được kiểm tra nguyên nhân, không chỉ dựa vào exit code.
- [ ] Mutant sống sót được điều tra theo hành vi và assertion còn thiếu.
- [ ] Mutant equivalent có lý do và bằng chứng để loại.
- [ ] Mutation score nêu rõ mẫu số và chính sách loại trừ.
- [ ] Kết quả được phân tích theo module và rủi ro, không chỉ score tổng.
- [ ] Test mới kiểm tra hành vi có ý nghĩa và không phụ thuộc quá mức vào chi tiết nội bộ.
- [ ] Chi phí thời gian chạy và độ ổn định môi trường được kiểm soát.
- [ ] Báo cáo có phiên bản mã, cấu hình và hành động tiếp theo.

## 14. Kết hợp mutation testing với chiến lược bao phủ

Mutation testing có giá trị nhất khi được dùng sau khi nhóm đã có một bộ kiểm thử nền và biết những rủi ro nào cần bảo vệ. Có thể kết hợp như sau:

~~~mermaid
flowchart TD
    A["Yêu cầu, rủi ro và oracle"]
    B["Thiết kế test case theo rủi ro"]
    C["Đo line/branch/condition coverage"]
    D["Chọn vùng mã quan trọng để mutation testing"]
    E["Sinh và chạy mutant"]
    F["Phân loại kết quả"]
    G["Bổ sung test/assertion hoặc chứng minh equivalent"]
    H["Đánh giá lại score và rủi ro còn lại"]
    A --> B --> C --> D --> E --> F --> G --> H
    H -. "Thay đổi yêu cầu hoặc mã" .-> A
~~~

Coverage cho biết vùng mã nào được thực thi; mutation testing giúp đánh giá test suite có phát hiện được những thay đổi sai trong vùng đó hay không; phân tích rủi ro giúp quyết định vùng nào cần đầu tư sâu. Kết hợp ba góc nhìn này giúp nhóm đánh giá bộ kiểm thử thực chất hơn và tập trung cải thiện những khẳng định có ảnh hưởng lớn.

Mutation testing nên được áp dụng có chọn lọc, với bộ kiểm thử nền ổn định, oracle rõ ràng và cách diễn giải kết quả minh bạch. Khi mutant sống sót được dùng như đầu mối để cải thiện test thay vì chỉ là mục tiêu điểm số, nhóm sẽ xây dựng được bộ kiểm thử có khả năng phân biệt hành vi đúng và sai tốt hơn.
