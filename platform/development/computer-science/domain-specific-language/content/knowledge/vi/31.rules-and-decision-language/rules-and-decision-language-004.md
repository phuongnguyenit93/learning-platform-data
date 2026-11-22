# Bảng quyết định

Trong ngôn ngữ chuyên biệt miền (Domain-Specific Language, DSL) dành cho luật và quyết định, **bảng quyết định (decision table)** là cách biểu diễn một tập quy tắc bằng các cột điều kiện và kết quả. Mỗi hàng mô tả một trường hợp: khi các điều kiện ở hàng đó thỏa mãn, hệ thống áp dụng hành động hoặc trả về kết quả tương ứng. Thay vì viết nhiều nhánh if/else lồng nhau, người thiết kế có thể nhìn toàn bộ các trường hợp trong một bảng, so sánh chúng và phát hiện những tình huống bị thiếu hoặc chồng lấn.

Ví dụ, một dịch vụ bán hàng cần quyết định mức phí giao hàng theo khu vực, giá trị đơn hàng và loại thành viên:

| Khu vực | Giá trị đơn hàng | Thành viên | Phí giao hàng |
|---|---:|---|---:|
| Nội thành | Từ 1.000.000 VND | Bất kỳ | 0 VND |
| Nội thành | Dưới 1.000.000 VND | VIP | 10.000 VND |
| Nội thành | Dưới 1.000.000 VND | Thường | 25.000 VND |
| Ngoại thành | Bất kỳ | Bất kỳ | 40.000 VND |

Khi nhận một đơn hàng, engine đánh giá dữ liệu đầu vào, tìm hàng phù hợp theo chính sách của bảng và trả về phí giao hàng. Bảng cho phép chuyên gia nghiệp vụ kiểm tra quy tắc mà không phải đọc chi tiết thuật toán điều khiển.

Trong một DSL, decision table có thể là cú pháp nguồn được parser chuyển thành decision model, được validator kiểm tra rồi được interpreter hoặc code generator thực thi. Để có semantics đáng tin cậy, DSL phải định nghĩa kiểu dữ liệu, cách so khớp điều kiện, chính sách khi nhiều hàng cùng khớp, cách xử lý trường hợp không có hàng nào khớp và quy tắc ưu tiên giữa các kết quả.

## 1. Bảng quyết định là gì?

Decision table là một biểu diễn dạng bảng cho logic quyết định. Các cột đầu vào mô tả điều kiện cần đánh giá; các cột đầu ra mô tả kết quả hoặc hành động; mỗi hàng là một rule hoặc một trường hợp có thể xảy ra.

Một bảng thường có:

- **Input columns:** Các giá trị hoặc biểu thức đầu vào của quyết định.
- **Condition entries:** Điều kiện hoặc miền giá trị được yêu cầu ở từng hàng.
- **Output columns:** Kết quả, trạng thái hoặc hành động cần trả về.
- **Rule rows:** Các hàng quy tắc độc lập.
- **Hit policy:** Chính sách quyết định cách xử lý khi không hàng nào, một hàng hoặc nhiều hàng cùng khớp.
- **Metadata:** Tên, phiên bản, mô tả, người sở hữu và phạm vi hiệu lực của bảng.

### 1.1. Một hàng là một quy tắc

Hàng quy tắc mô tả một tổ hợp điều kiện. Ví dụ, nếu total lớn hơn hoặc bằng 1.000.000 VND và customerType là VIP thì discountRate bằng 10%. Điều kiện có thể gồm so sánh, khoảng, tập giá trị, biểu thức hoặc wildcard.

### 1.2. Cột đầu vào và cột đầu ra

Input column lấy dữ liệu từ request, context hoặc kết quả quyết định trước đó. Output column xác định giá trị trả về hoặc hành động được chọn. Một bảng có thể có nhiều input và nhiều output.

### 1.3. Decision table không phải bảng dữ liệu thông thường

Bảng dữ liệu thường lưu các bản ghi; mỗi dòng là một thực thể hoặc quan sát. Decision table lưu logic; mỗi dòng là một rule được đánh giá. Vì vậy, thứ tự dòng, overlap và hit policy có thể ảnh hưởng trực tiếp đến kết quả thực thi.

### 1.4. Decision table không nhất thiết là truth table

Truth table thường liệt kê các tổ hợp Boolean của một số biến logic. Decision table có thể dùng số, chuỗi, enum, ngày giờ, khoảng giá trị, tập hợp và biểu thức miền. Nó cũng có thể trả về nhiều loại output thay vì chỉ true/false.

### 1.5. Decision table không thay thế mọi workflow

Decision table phù hợp để chọn kết quả từ dữ liệu và quy tắc. Workflow mô tả trình tự hành động theo thời gian, dependency và trạng thái. Một quyết định có thể được gọi từ workflow, còn workflow thường điều phối những gì xảy ra sau khi quyết định được đưa ra.

## 2. Khi nào nên dùng bảng quyết định?

Bảng quyết định đặc biệt hữu ích khi một nghiệp vụ có nhiều điều kiện kết hợp và cần được kiểm tra bởi cả người viết phần mềm lẫn chuyên gia miền.

### 2.1. Nhiều điều kiện đầu vào

Nếu quyết định phụ thuộc vào tuổi, khu vực, giá trị giao dịch, loại khách hàng và trạng thái hồ sơ, các nhánh if/else có thể nhanh chóng trở nên khó đọc. Bảng cho phép đặt các điều kiện cạnh nhau.

### 2.2. Quy tắc cần được chuyên gia nghiệp vụ xem xét

Nhân viên nghiệp vụ có thể kiểm tra các hàng, so sánh điều kiện và xác nhận kết quả mà không cần hiểu cú pháp điều khiển của ngôn ngữ lập trình.

### 2.3. Chính sách thay đổi thường xuyên

Bảng có thể được version hóa và cập nhật như một artifact luật. Một số hệ thống cho phép thay đổi decision table độc lập với phần code điều phối, sau khi xác thực và phát hành phiên bản mới.

### 2.4. Cần kiểm tra tính đầy đủ

Các khoảng giá trị hoặc tổ hợp điều kiện có thể để sót một vùng đầu vào. Decision table giúp nhìn ra những khoảng trống và cho phép công cụ phân tích coverage.

### 2.5. Cần phát hiện quy tắc trùng lặp

Hai hàng có thể mô tả cùng một điều kiện nhưng trả về kết quả khác nhau. Validator có thể phát hiện overlap và yêu cầu người thiết kế chọn hit policy hoặc sửa quy tắc.

### 2.6. Cần giải thích kết quả

Engine có thể trả về rule ID hoặc danh sách hàng đã khớp. Điều này giúp người vận hành giải thích vì sao một hồ sơ được chấp nhận, một giao dịch bị từ chối hoặc một mức giá được chọn.

## 3. Cấu trúc của một decision table

Một decision table thường được mô hình hóa bằng metadata, input definitions, output definitions và các rule row.

### 3.1. Metadata

Metadata nhận diện bảng và mô tả mục đích:

~~~text
decision-table shipping-fee {
    description = "Tính phí giao hàng cho đơn hàng"
    version = "1.0"
}
~~~

Tên và cú pháp chỉ minh họa. DSL cần xác định phạm vi tên, cách version hóa và metadata nào bắt buộc.

### 3.2. Input definitions

Input definition khai báo tên, kiểu và cách lấy giá trị:

~~~text
inputs {
    area: DeliveryArea
    total: Money<VND>
    memberType: MemberType
}
~~~

Định nghĩa đầu vào giúp kiểm tra điều kiện và tránh so sánh những kiểu không tương thích.

### 3.3. Output definitions

Output definition khai báo kiểu kết quả:

~~~text
outputs {
    shippingFee: Money<VND>
}
~~~

Output có thể là scalar, enum, record hoặc một tập giá trị tùy khả năng của DSL.

### 3.4. Rule rows

Mỗi row gán điều kiện cho các input và giá trị cho output. Tên rule hoặc ID ổn định giúp audit, kiểm thử và giải thích kết quả.

### 3.5. Hit policy

Hit policy quyết định điều gì xảy ra khi có nhiều hàng cùng khớp. Đây là một phần semantics của bảng, không chỉ là cách hiển thị.

## 4. Cách đọc điều kiện trong từng ô

Một ô điều kiện biểu diễn miền giá trị mà input phải thỏa mãn để hàng được xem là match.

### 4.1. Giá trị bằng nhau

Ô có giá trị VIP có thể mang nghĩa memberType phải bằng VIP.

### 4.2. Wildcard

Ký hiệu wildcard có nghĩa hàng không giới hạn input đó. Ví dụ, bất kỳ loại thành viên nào đều thỏa mãn điều kiện ở cột memberType.

### 4.3. So sánh

Một ô có thể biểu diễn:

~~~text
< 1000000 VND
>= 1000000 VND
!= SUSPENDED
~~~

Toán tử được hỗ trợ phải phù hợp với kiểu dữ liệu. Không phải kiểu nào cũng có thứ tự để so sánh lớn hơn hoặc nhỏ hơn.

### 4.4. Khoảng giá trị

Điều kiện có thể dùng khoảng đóng hoặc khoảng mở:

~~~text
[18, 65)
~~~

Khoảng này gồm 18 và không gồm 65. DSL cần quy định cách viết và semantics của endpoint.

### 4.5. Tập giá trị

Một ô có thể nhận một trong nhiều giá trị:

~~~text
in {HANOI, HCMC, DANANG}
~~~

Tập hợp nên có kiểu phần tử đồng nhất và quy tắc xử lý giá trị trùng.

### 4.6. Biểu thức

Một số DSL cho phép dùng biểu thức:

~~~text
total > minimumOrderValue
~~~

Biểu thức cần được kiểm tra kiểu, giới hạn side effect và đánh giá theo một context nhất quán. Nếu biểu thức phụ thuộc dữ liệu thay đổi trong lúc đánh giá, kết quả có thể khó tái lập.

### 4.7. Giá trị thiếu và null

Input không được cung cấp khác với input có giá trị null. DSL cần phân biệt missing, null và một giá trị mặc định. Wildcard có bao gồm null hay không cũng phải được định nghĩa.

## 5. Khai báo decision table bằng DSL

Một DSL dạng khai báo có thể biểu diễn bảng trực tiếp trong source file.

~~~text
decision-table shipping_fee {
    inputs {
        area: DeliveryArea
        total: Money<VND>
        member: MemberType
    }

    outputs {
        fee: Money<VND>
    }

    hit-policy = UNIQUE

    rules {
        when area == NOI_THANH
         and total >= 1000000 VND
        then fee = 0 VND

        when area == NOI_THANH
         and total < 1000000 VND
         and member == VIP
        then fee = 10000 VND

        when area == NOI_THANH
         and total < 1000000 VND
         and member == STANDARD
        then fee = 25000 VND

        when area == NGOAI_THANH
        then fee = 40000 VND
    }
}
~~~

Đây là ví dụ minh họa một bảng có chính sách UNIQUE. Engine phải bảo đảm không có hai hàng cùng match với một input hợp lệ; nếu có, đó là lỗi vi phạm hit policy.

### 5.1. Cú pháp dạng hàng và cột

DSL khác có thể dùng bảng tường minh:

~~~text
decision-table shipping_fee
    hit-policy UNIQUE

| area        | total          | member   | fee       |
| NOI_THANH   | >= 1000000 VND | -        | 0 VND     |
| NOI_THANH   | < 1000000 VND  | VIP      | 10000 VND |
| NOI_THANH   | < 1000000 VND  | STANDARD | 25000 VND |
| NGOAI_THANH | -              | -        | 40000 VND |
~~~

Ký hiệu dấu gạch ngang chỉ mang nghĩa wildcard trong ví dụ này. Một DSL thực tế cần chọn ký hiệu không xung đột với giá trị hợp lệ.

### 5.2. Rule ID

Mỗi hàng có thể có ID:

~~~text
rule R_SHIP_001:
    when area == NOI_THANH and total >= 1000000 VND
    then fee = 0 VND
~~~

Rule ID ổn định hữu ích cho audit và monitoring. Nếu ID tự sinh theo số dòng, việc chèn một hàng có thể làm thay đổi ID của mọi rule phía sau.

### 5.3. Mô tả rule

Rule có thể mang description giải thích ý nghĩa nghiệp vụ, nguồn chính sách hoặc ngày hiệu lực. Mô tả không thay thế điều kiện thực thi nhưng giúp review và vận hành.

## 6. Các hit policy phổ biến

Hit policy xác định cách engine xử lý số lượng hàng khớp. Nhiều chuẩn và sản phẩm dùng tên hoặc biến thể khác nhau; DSL cần công bố đúng semantics của dialect mình hỗ trợ.

| Hit policy | Ý nghĩa khái quát |
|---|---|
| UNIQUE | Tối đa một hàng được khớp |
| FIRST | Chọn hàng khớp đầu tiên theo thứ tự |
| ANY | Nhiều hàng có thể khớp nếu output tương đương |
| PRIORITY | Chọn kết quả có mức ưu tiên cao nhất |
| COLLECT | Thu thập kết quả từ tất cả hàng khớp |
| RULE ORDER | Trả các kết quả theo thứ tự hàng |
| OUTPUT ORDER | Trả các kết quả theo thứ tự ưu tiên output |

### 6.1. UNIQUE

UNIQUE yêu cầu không có nhiều hơn một hàng khớp cho một input. Nếu không có hàng nào khớp, kết quả phụ thuộc default/no-match policy. Nếu nhiều hàng khớp, engine báo lỗi quyết định không duy nhất.

UNIQUE phù hợp khi người thiết kế muốn mỗi trường hợp đầu vào có đúng một quy tắc cụ thể và overlap là lỗi mô hình.

### 6.2. FIRST

FIRST chọn hàng khớp đầu tiên theo thứ tự khai báo. Các hàng phía sau không được dùng cho kết quả của lần đánh giá đó.

Policy này hữu ích khi thứ tự là một phần có chủ đích của chính sách, chẳng hạn quy tắc ngoại lệ được đặt trước quy tắc chung. Tuy nhiên, thêm hoặc sắp xếp lại hàng có thể thay đổi kết quả, vì vậy thứ tự cần được review và kiểm thử.

### 6.3. ANY

ANY cho phép nhiều hàng cùng khớp nếu các output của chúng tương đương theo quy tắc equality đã định nghĩa. Nếu các hàng cùng match nhưng trả output khác nhau, engine báo conflict.

ANY hữu ích khi có nhiều cách mô tả cùng một kết quả và người thiết kế muốn cho phép overlap nhưng không chấp nhận kết quả mâu thuẫn.

### 6.4. PRIORITY

PRIORITY chọn output có thứ tự ưu tiên cao nhất trong các kết quả của hàng khớp. Ưu tiên thường được xác định bởi thứ tự trong miền output hoặc metadata riêng.

Ví dụ, một quyết định phân loại rủi ro có thể trả LOW, MEDIUM, HIGH hoặc CRITICAL. Nếu nhiều rule match, PRIORITY có thể chọn mức nghiêm trọng nhất theo thứ tự đã công bố.

### 6.5. COLLECT

COLLECT thu thập output của tất cả hàng khớp. Kết quả thường là danh sách hoặc tập hợp. Một số dialect cho phép collector như SUM, MIN, MAX hoặc COUNT trên các output số.

~~~text
hit-policy = COLLECT
aggregate = SUM
~~~

Ví dụ, nhiều quy tắc phụ phí có thể cùng match và mỗi hàng đóng góp một khoản phí. Engine cộng các khoản đó để tạo tổng phụ phí.

### 6.6. RULE ORDER

RULE ORDER trả về các output của tất cả hàng khớp theo thứ tự khai báo. Nó giữ lại thứ tự của rule, có thể hữu ích khi thứ tự là dữ liệu có ý nghĩa đối với consumer.

### 6.7. OUTPUT ORDER

OUTPUT ORDER trả về kết quả theo thứ tự ưu tiên của output thay vì thứ tự khai báo. Điều này cần một thứ tự so sánh hoặc priority rõ ràng.

### 6.8. Hit policy phải gắn với kiểu kết quả

COLLECT cần output có thể thu thập; SUM cần output số hoặc kiểu có phép cộng xác định; PRIORITY cần thứ tự output. Validator nên từ chối tổ hợp không có nghĩa thay vì để runtime thất bại muộn.

## 7. No-match policy và default result

Hit policy thường mô tả trường hợp có hàng match. DSL cũng phải quy định trường hợp không hàng nào match.

### 7.1. Không có hàng khớp

Nếu input nằm ngoài mọi điều kiện, engine có thể trả no-match result, giá trị mặc định, trạng thái không xác định hoặc diagnostic. Hành vi phụ thuộc miền nghiệp vụ.

### 7.2. Default output

Một bảng có thể khai báo default:

~~~text
default {
    decision = MANUAL_REVIEW
}
~~~

Default nên được phân biệt với một hàng wildcard. Hàng wildcard là rule có thể match cùng các rule khác; default thường chỉ áp dụng sau khi engine xác định không có rule nào phù hợp.

### 7.3. Reject hoặc fail closed

Với quyết định bảo mật, quyền truy cập hoặc phê duyệt giao dịch, no-match có thể cần từ chối hoặc chuyển review. Không nên mặc định cho phép khi thiếu quy tắc.

### 7.4. Optional result

Một số API có thể trả Optional hoặc DecisionResult với trạng thái NO_MATCH. Cách này cho caller tự quyết định hành động tiếp theo nhưng phải tránh caller bỏ qua trạng thái.

### 7.5. Phân biệt no-match với evaluation error

No-match nghĩa là đánh giá thành công nhưng không hàng nào thỏa điều kiện. Evaluation error nghĩa là không thể đánh giá, ví dụ thiếu input bắt buộc hoặc lỗi khi tính biểu thức. Hai trường hợp cần diagnostic khác nhau.

## 8. Tính đầy đủ của bảng

Một bảng đầy đủ khi mọi đầu vào thuộc miền hợp lệ đều được xử lý theo semantics mong muốn.

### 8.1. Input domain

Để kiểm tra completeness, cần biết miền giá trị hợp lệ của từng input. Nếu age là Integer không âm, domain có thể là 0 trở lên; nếu area là enum, domain là tập thành viên đã khai báo.

### 8.2. Coverage

Coverage cho biết phần miền đầu vào hoặc tổ hợp điều kiện đã được các rule bao phủ. Với miền hữu hạn nhỏ, có thể liệt kê mọi tổ hợp; với miền liên tục, cần phân tích khoảng và biên.

### 8.3. Gaps

Gap là một vùng đầu vào hợp lệ không match hàng nào. Ví dụ bảng phí chỉ có total dưới 100.000 và trên 500.000, bỏ sót khoảng từ 100.000 đến 500.000.

### 8.4. Wildcard và completeness

Wildcard có thể bao phủ một miền rộng nhưng cũng có thể làm rule cụ thể trở nên unreachable hoặc gây overlap. Công cụ cần hiển thị vùng được wildcard bao phủ.

### 8.5. Completeness có điều kiện

Một bảng có thể đầy đủ trong miền đầu vào đã được giới hạn bởi decision trước đó. Vì vậy, validator cần hiểu constraint và dependency thay vì chỉ xét mọi giá trị có thể về mặt kiểu.

### 8.6. Default không thay thế phân tích coverage

Default bảo đảm có kết quả cho no-match, nhưng có thể che một gap trong logic nghiệp vụ. Công cụ nên phân biệt coverage do rule cụ thể và fallback do default.

## 9. Overlap, conflict và tính duy nhất

Overlap xảy ra khi hai hay nhiều hàng cùng thỏa mãn một input. Overlap có thể là lỗi hoặc hành vi được cho phép bởi hit policy.

### 9.1. Overlap không mong muốn

Giả sử hai hàng cùng match khi total lớn hơn 1.000.000 VND, nhưng một hàng trả discount 10% và hàng kia trả discount 20%. Với UNIQUE, đây là lỗi; với FIRST, thứ tự quyết định kết quả.

### 9.2. Equivalent overlap

Hai hàng có thể cùng match và trả cùng output. ANY có thể cho phép tình huống này, nhưng vẫn nên xem xét có cần gộp rule để tránh bảo trì trùng lặp hay không.

### 9.3. Conflict detection

Validator có thể so sánh điều kiện của các hàng để xác định giao nhau. Với biểu thức phức tạp, công cụ có thể không chứng minh được đầy đủ; khi đó nên báo trạng thái unknown thay vì khẳng định không overlap.

### 9.4. Priority giải quyết conflict như thế nào?

PRIORITY chỉ giải quyết xung đột theo output priority đã khai báo. Nó không tự chứng minh các điều kiện đúng hoặc rằng ưu tiên nghiệp vụ là hợp lý.

### 9.5. Rule unreachable

Một hàng có thể không bao giờ được chọn vì hàng FIRST trước đó bao phủ toàn bộ miền của nó hoặc điều kiện của nó mâu thuẫn. Validator nên cảnh báo rule unreachable.

### 9.6. Dead rule

Rule dead là rule không thể match trong mọi đầu vào hợp lệ. Nó có thể là dấu hiệu của điều kiện sai, dữ liệu schema đã đổi hoặc rule cũ không còn cần thiết.

## 10. Thứ tự quy tắc và precedence

Thứ tự hàng có thể có hoặc không có ý nghĩa tùy hit policy.

### 10.1. Policy không phụ thuộc thứ tự

UNIQUE và ANY không nên dùng thứ tự dòng để giải quyết conflict. PRIORITY dùng thứ tự ưu tiên output được khai báo, không nhất thiết là vị trí hàng.

### 10.2. FIRST và RULE ORDER

Với FIRST, thứ tự hàng quyết định rule thắng. Với RULE ORDER, thứ tự hàng quyết định thứ tự kết quả được trả. Vì vậy, thay đổi vị trí hàng là thay đổi logic có thể ảnh hưởng production.

### 10.3. Specificity

Một số DSL cung cấp policy chọn rule cụ thể nhất, ví dụ điều kiện có nhiều ràng buộc hơn được ưu tiên. Specificity cần được định nghĩa bằng thuật toán rõ ràng; không nên để engine tự suy đoán rằng điều kiện dài hơn luôn quan trọng hơn.

### 10.4. Explicit priority

Có thể khai báo priority trên từng rule:

~~~text
rule urgent_case priority 100:
    when risk == CRITICAL
    then route = IMMEDIATE_REVIEW
~~~

Nếu dùng priority của rule, cần định nghĩa tie-break khi bằng nhau và cách kết hợp với hit policy.

### 10.5. Không trộn nhiều precedence ngầm

Kết hợp thứ tự dòng, rule priority, output priority và specificity mà không có quy tắc tổng thể khiến bảng khó dự đoán. Nên chọn một hit policy chính và chỉ thêm cơ chế phụ khi có nhu cầu rõ.

## 11. Kiểu dữ liệu và so khớp điều kiện

Decision table chỉ đáng tin cậy khi các input, condition và output được kiểm tra kiểu.

### 11.1. Numeric

Số nguyên, số thập phân và tiền tệ cần phép so sánh phù hợp. Với Money, cần quy định currency và cách xử lý rounding; không so sánh hai số tiền khác currency như thể cùng đơn vị.

### 11.2. String

So khớp chuỗi có thể phân biệt hoa thường hoặc không. Cần quy định Unicode normalization, trimming và collation nếu so sánh văn bản có ý nghĩa nghiệp vụ.

### 11.3. Enum

Enum giúp giới hạn miền đầu vào và output. Validator có thể phát hiện giá trị không tồn tại trước runtime.

### 11.4. Date và time

Điều kiện thời gian cần quy định timezone, instant, local date và biên khoảng. Ví dụ “trước 17:00” cần biết timezone nào và có bao gồm đúng 17:00 hay không.

### 11.5. Duration

Duration là khoảng thời gian, không phải ngày giờ tuyệt đối. So sánh Duration cần thống nhất đơn vị hoặc chuyển về biểu diễn chuẩn.

### 11.6. Collection

Condition có thể kiểm tra phần tử tồn tại, tập con hoặc số lượng phần tử. DSL cần quy định equality của collection là theo thứ tự, theo tập hợp hay theo multiset.

### 11.7. Record và object

Một điều kiện có thể truy cập field của object đầu vào. Semantic analyzer cần xác minh field tồn tại và quyền truy cập.

### 11.8. Coercion

Không nên âm thầm chuyển chuỗi "100" sang số trong mọi ngữ cảnh. Coercion cần được xác định rõ để tránh so sánh chuỗi với số theo cách không mong muốn.

## 12. Null, missing và unknown

Ba trạng thái này có thể tạo ra kết quả khác nhau trong logic quyết định.

### 12.1. Null

Null biểu diễn một giá trị được xác định là không có hoặc rỗng theo mô hình dữ liệu.

### 12.2. Missing

Missing nghĩa là trường đầu vào không được cung cấp. Nó có thể là lỗi schema hoặc là trường tùy chọn.

### 12.3. Unknown

Unknown có thể xuất hiện khi dữ liệu chưa được xác định hoặc biểu thức không thể đánh giá do thiếu thông tin. Một số DSL dùng logic ba giá trị true/false/unknown.

### 12.4. So sánh với null

Trong nhiều ngôn ngữ, phép so sánh thông thường với null không trả true hoặc false như người dùng mong đợi. DSL cần định nghĩa toán tử is null, is missing hoặc exists thay vì dựa vào hành vi ngầm.

### 12.5. Unknown trong condition

Nếu condition trả unknown, engine có thể coi hàng không match, báo lỗi hoặc truyền trạng thái unknown theo semantics riêng. Quy tắc phải nhất quán giữa các operator và hit policy.

### 12.6. Không biến lỗi dữ liệu thành no-match

Nếu input bắt buộc bị thiếu, coi mọi hàng là không match có thể dẫn đến fallback sai. Thường nên xác thực input trước khi đánh giá bảng.

## 13. Biểu thức và hàm trong decision table

Một decision table có thể dùng biểu thức để mô tả điều kiện phức tạp hơn phép so sánh trực tiếp.

### 13.1. Input expression

Input có thể được tính từ context:

~~~text
input customerAge = yearsBetween(customer.birthDate, today())
~~~

Biểu thức cần có kiểu trả về và quy tắc xử lý lỗi.

### 13.2. Condition expression

Condition có thể kết hợp nhiều thuộc tính:

~~~text
customer.active
and order.total >= policy.minimum
and order.country in policy.allowedCountries
~~~

### 13.3. Pure functions

Nên ưu tiên hàm thuần trong điều kiện: cùng đầu vào cho cùng kết quả và không tạo side effect. Gọi API hoặc sửa trạng thái trong lúc đánh giá làm kết quả khó tái lập và khó kiểm thử.

### 13.4. Snapshot đầu vào

Engine nên đánh giá tất cả hàng trên cùng một snapshot input. Nếu dữ liệu bị thay đổi giữa lúc kiểm tra các hàng, hai rule có thể được đánh giá trên những trạng thái khác nhau.

### 13.5. Timeout và giới hạn

Biểu thức phức tạp hoặc hàm miền cần giới hạn thời gian và tài nguyên. Một decision table không nên có khả năng gây vòng lặp vô hạn hoặc truy vấn không giới hạn.

### 13.6. Evaluation error

Nếu hàm ném lỗi, engine cần phân biệt lỗi tính toán với điều kiện false. Có thể dừng toàn bảng, đánh dấu rule lỗi hoặc dùng error policy, nhưng hành vi phải được định nghĩa.

## 14. Nhiều output và kiểu kết quả

Một decision table có thể trả nhiều trường thay vì một giá trị.

### 14.1. Nhiều output columns

Ví dụ quyết định khoản vay có thể trả:

- decision: APPROVE, REJECT hoặc REVIEW.
- interestRate: tỷ lệ lãi suất.
- creditLimit: hạn mức.
- reasonCode: mã lý do.

### 14.2. Output record

Có thể gói kết quả vào một record có kiểu:

~~~text
type LoanDecision = {
    decision: DecisionStatus
    interestRate: Percentage
    creditLimit: Money<VND>
    reasonCode: String
}
~~~

### 14.3. Output consistency

Các cột output có thể có ràng buộc chéo. Ví dụ REJECT không được trả creditLimit dương; APPROVE cần có interestRate. Validator có thể kiểm tra schema hoặc constraint sau khi tính output.

### 14.4. Output nullability

Một output có thể không áp dụng trong một nhánh. Cần khai báo nullable hoặc kiểu union thay vì để trống ô với ý nghĩa không rõ.

### 14.5. Output aggregation

Với COLLECT, mỗi hàng có thể trả một record. Aggregator cần xác định kết quả là list, set hay phép tổng hợp và cách xử lý phần tử trùng.

## 15. Kết hợp nhiều decision table

Một quyết định lớn có thể được chia thành các bảng nhỏ để quản lý từng phần nghiệp vụ.

### 15.1. Decision chaining

~~~mermaid
flowchart TD
    A[Thông tin khách hàng] --> B[Bảng phân loại rủi ro]
    B --> C[Risk category]
    C --> D[Bảng xác định hạn mức]
    D --> E[Credit limit]
    E --> F[Bảng quyết định cuối]
    F --> G[Approve / Reject / Review]
~~~

### 15.2. Dependency

Decision graph cần có thứ tự rõ ràng. Bảng sau chỉ được đánh giá khi input phụ thuộc đã có giá trị.

### 15.3. Reuse

Một bảng phân loại khách hàng có thể được dùng bởi nhiều workflow. Nên version hóa và định danh bảng để caller biết chính xác policy nào đang được áp dụng.

### 15.4. Tránh dependency cycle

Nếu bảng A cần output của B và B lại cần output của A, không thể đánh giá theo mô hình tuần tự thông thường. Cần phát hiện cycle hoặc dùng một semantics giải quyết cố định được thiết kế riêng.

### 15.5. Composed decisions

Một decision service có thể gọi nhiều bảng và kết hợp kết quả. Cần ghi nhận decision ID, version từng bảng và input snapshot để giải thích kết quả tổng thể.

## 16. Decision table và các dạng luật khác

DSL luật có thể hỗ trợ nhiều cách biểu diễn logic. Mỗi cách phù hợp với một dạng vấn đề.

| Dạng biểu diễn | Phù hợp khi |
|---|---|
| Decision table | Nhiều tổ hợp điều kiện và kết quả cần so sánh |
| If/else | Luồng điều khiển ngắn, có thứ tự rõ |
| Decision tree | Muốn thể hiện các nhánh tuần tự và câu hỏi |
| Rule set | Nhiều luật độc lập có thể kích hoạt |
| Truth table | Logic Boolean hữu hạn |
| State machine | Hành vi phụ thuộc trạng thái và sự kiện theo thời gian |
| Workflow | Điều phối các bước, tác vụ và dependency |

### 16.1. Decision tree

Decision tree biểu diễn việc kiểm tra điều kiện theo từng nhánh. Nó có thể dễ đọc khi có ít câu hỏi tuần tự, nhưng nhiều tổ hợp điều kiện có thể tạo cây sâu và lặp lại nhánh.

### 16.2. Rule set

Rule set có thể cho phép nhiều rule độc lập cùng kích hoạt và tạo side effect. Decision table thường tập trung vào ánh xạ input sang output, dù DSL có thể hỗ trợ output mô tả action.

### 16.3. State machine

State machine mô tả trạng thái hiện tại, sự kiện và chuyển trạng thái. Decision table có thể được dùng để quyết định transition hoặc guard, nhưng không tự mô tả toàn bộ lifecycle.

### 16.4. If/else

If/else phù hợp cho logic điều khiển nhỏ. Khi số điều kiện và ngoại lệ tăng, decision table giúp tách dữ liệu quy tắc khỏi flow điều khiển.

## 17. Tích hợp với Decision Model and Notation

Decision Model and Notation (DMN) là một tiêu chuẩn của OMG dùng để mô hình hóa quyết định và decision requirements, trong đó decision table là một biểu diễn quan trọng.

### 17.1. Decision requirements graph

DMN có thể mô tả các quyết định, input data và dependency giữa chúng bằng Decision Requirements Graph (DRG). Điều này giúp người thiết kế thấy một quyết định phụ thuộc vào dữ liệu hoặc quyết định nào khác.

### 17.2. FEEL

DMN sử dụng Friendly Enough Expression Language (FEEL) cho biểu thức trong mô hình. FEEL có semantics riêng cho kiểu, range, list và biểu thức. Một DSL khác không nên tự nhận tương thích FEEL nếu không triển khai đúng đặc tả liên quan.

### 17.3. Hit policy

DMN định nghĩa các hit policy như Unique, First, Any, Priority, Collect, Rule Order và Output Order. Một DSL có thể chọn hỗ trợ một tập con hoặc có policy mở rộng, nhưng cần ghi rõ điểm khác biệt.

### 17.4. Import/export

Nếu DSL muốn trao đổi decision model với công cụ DMN, cần ánh xạ metadata, expression, type, hit policy và output. Không phải mọi cú pháp DSL đều có thể chuyển đổi lossless sang DMN.

### 17.5. Tiêu chuẩn và implementation

Một sản phẩm có thể hỗ trợ một phần tiêu chuẩn hoặc có extension riêng. Tài liệu cần nói rõ mức tương thích, phiên bản và giới hạn để người dùng không hiểu nhầm.

## 18. Validation và phân tích tĩnh

Validator kiểm tra decision table trước khi phát hành hoặc thực thi.

### 18.1. Structural validation

Kiểm tra bảng có input và output definitions, số cột hợp lệ, mỗi hàng có đủ ô và rule ID không trùng.

### 18.2. Type validation

Kiểm tra kiểu input, condition và output tương thích. Ví dụ không cho so sánh Money với Date hoặc gán String vào output Boolean nếu không có conversion được khai báo.

### 18.3. Hit policy validation

UNIQUE cần phân tích overlap; ANY cần kiểm tra output tương đương ở vùng giao; COLLECT cần output/aggregator tương thích.

### 18.4. Completeness analysis

Phân tích vùng đầu vào chưa được bao phủ và hiển thị ví dụ hoặc constraint gây gap.

### 18.5. Redundancy analysis

Hai rule có điều kiện tương đương và output giống nhau có thể là redundancy. Công cụ có thể cảnh báo để người sở hữu quyết định có gộp hay giữ lại vì lý do audit.

### 18.6. Unreachable rules

Phát hiện rule bị rule khác che phủ hoàn toàn theo FIRST hoặc không thể thỏa mãn do điều kiện mâu thuẫn.

### 18.7. Expression safety

Kiểm tra hàm được gọi có được phép trong decision context, có side effect hay không và có thể tiêu tốn tài nguyên quá mức không.

### 18.8. Static analysis limits

Với biểu thức tổng quát hoặc dữ liệu ngoài, công cụ có thể không chứng minh được overlap hay completeness. Kết quả nên có trạng thái proven, disproven hoặc unknown thay vì khẳng định quá mức.

## 19. Thực thi decision table trong runtime

Runtime nhận input, chuẩn hóa dữ liệu, đánh giá hàng và áp dụng hit policy để tạo result.

### 19.1. Input binding

Caller cung cấp giá trị theo tên hoặc cấu trúc record. Engine kiểm tra trường bắt buộc, kiểu và constraint trước khi bắt đầu match.

### 19.2. Normalization

Nếu DSL cho phép normalization như trim chuỗi hoặc chuẩn hóa enum, việc này nên diễn ra ở một bước được định nghĩa. Không tự ý thay đổi dữ liệu gốc theo quy tắc không công bố.

### 19.3. Row evaluation

Engine đánh giá các condition của một hàng. Với điều kiện AND, có thể dừng khi một điều kiện false nếu biểu thức thuần và không có side effect. Nếu DSL có short-circuit semantics, cần đặc tả.

### 19.4. Match collection

Engine thu thập các hàng khớp hoặc dừng sớm với policy FIRST. Với policy khác, có thể cần đánh giá mọi hàng để xác định kết quả cuối.

### 19.5. Hit policy application

Sau khi xác định tập match, engine áp dụng UNIQUE, ANY, PRIORITY, COLLECT hoặc policy đã khai báo.

### 19.6. Result object

Result nên chứa output, decision/table ID, version, trạng thái match, rule IDs đã áp dụng và diagnostic nếu có. Caller có thể dùng metadata để audit mà không cần truy vấn lại source.

### 19.7. Determinism

Cùng version bảng và cùng input snapshot cần tạo cùng kết quả nếu biểu thức không dùng thời gian, randomness hoặc nguồn ngoài không được cố định.

## 20. Hiệu năng và tối ưu hóa

Decision table có thể có hàng trăm hoặc hàng nghìn rule. Engine cần tối ưu nhưng vẫn giữ nguyên semantics.

### 20.1. Precompile conditions

Parser và semantic analyzer có thể chuyển condition thành biểu diễn trung gian để tránh parse lại mỗi lần đánh giá.

### 20.2. Index theo input

Các điều kiện equality trên enum hoặc key có thể được lập index để giảm số hàng cần xét. Range condition có thể dùng interval index nếu có lợi.

### 20.3. Short-circuit

Với policy cho phép, engine có thể dừng khi đã biết kết quả. FIRST thường có thể dừng sau hàng đầu tiên match; UNIQUE phải tiếp tục đủ để phát hiện hàng match thứ hai.

### 20.4. Decision cache

Có thể cache kết quả theo input key nếu quyết định thuần, dữ liệu phụ thuộc có version và cache invalidation được xác định. Không cache quyết định phụ thuộc vào thời gian hoặc trạng thái ngoài mà không đưa chúng vào key.

### 20.5. Batch evaluation

Một số workload cần đánh giá nhiều input. Batch API có thể giảm overhead, nhưng phải xác định mỗi input có context và result riêng.

### 20.6. Profiling

Theo dõi số hàng được xét, thời gian đánh giá, rule match và chi phí biểu thức. Không ghi input nhạy cảm vào profiling log.

### 20.7. Không tối ưu làm đổi thứ tự

Reordering rule có thể thay đổi FIRST hoặc RULE ORDER. Optimizer chỉ được sắp xếp lại khi chứng minh được semantics không đổi.

## 21. Kiểm thử decision table

Kiểm thử nên bao phủ rule, biên điều kiện, overlap, no-match và hit policy.

### 21.1. Test từng hàng

Tạo ít nhất một input đại diện để xác nhận mỗi rule có thể match và trả output mong đợi.

### 21.2. Boundary tests

Với điều kiện total < 1.000.000 và total >= 1.000.000, kiểm thử giá trị ngay dưới, đúng bằng và ngay trên ngưỡng. Với date range, kiểm thử cả endpoint.

### 21.3. No-match tests

Tạo input không khớp hàng nào và xác minh default, reject hoặc NO_MATCH result.

### 21.4. Overlap tests

Tạo input cố ý làm nhiều hàng match. Kiểm tra UNIQUE báo lỗi, FIRST chọn hàng đúng thứ tự, ANY xác minh output tương đương và COLLECT trả đủ kết quả.

### 21.5. Type and missing input tests

Kiểm tra input sai kiểu, thiếu trường, null, unknown và giá trị ngoài miền.

### 21.6. Property-based testing

Sinh nhiều input trong domain để kiểm tra invariant như không có phí âm, hạn mức không vượt trần hoặc decision không có trạng thái mâu thuẫn.

### 21.7. Pairwise và combinatorial testing

Khi có nhiều input, toàn bộ tổ hợp có thể quá lớn. Pairwise hoặc combinatorial testing chọn tập trường hợp bao phủ tương tác giữa các cặp hoặc nhóm điều kiện quan trọng.

### 21.8. Regression tests

Mỗi thay đổi rule có thể làm thay đổi quyết định cũ. Lưu input/output của các trường hợp quan trọng để so sánh giữa version.

### 21.9. Golden decision tests

Có thể lưu fixture gồm input, expected output và expected rule IDs. Điều này giúp phát hiện thay đổi không chủ ý trong hit policy hoặc rule ordering.

### 21.10. Test giải thích

Ngoài output, kiểm tra rule IDs và reason codes để bảo đảm người dùng có thể truy vết vì sao kết quả được chọn.

## 22. Quản lý phiên bản và vòng đời luật

Decision table thường phản ánh chính sách nghiệp vụ có hiệu lực theo thời gian. Version và lifecycle cần được quản lý rõ.

### 22.1. Version bất biến

Một version đã phát hành nên được coi là immutable. Thay đổi rule tạo version mới để các quyết định cũ có thể được tái hiện.

### 22.2. Effective date

Bảng có thể có thời điểm bắt đầu và kết thúc hiệu lực. Cần xác định timezone, endpoint và hành vi khi hai version có khoảng hiệu lực chồng nhau.

### 22.3. Draft và published

Draft có thể được chỉnh sửa và thử nghiệm; published version được runtime sử dụng. Việc publish nên gắn với validation và approval theo quy trình quản trị.

### 22.4. Rollback

Có thể quay lại version trước nếu version mới gây lỗi. Rollback cần xác định có áp dụng cho quyết định mới, quyết định đang xử lý hay cả hai.

### 22.5. Audit history

Lưu ai tạo, ai sửa, ai phê duyệt, thay đổi gì và version nào được triển khai. Lịch sử không nên chỉ lưu nội dung cuối cùng.

### 22.6. Migration

Đổi tên input, kiểu output hoặc hit policy có thể phá caller. Cần version schema, migration note và kiểm tra tương thích trước khi phát hành.

## 23. Giải thích kết quả và khả năng audit

Một hệ thống luật tốt cần giải thích được quyết định đã đưa ra.

### 23.1. Matched rule IDs

Engine có thể trả ID của các rule đã match. Với FIRST, đó là rule được chọn; với COLLECT, là toàn bộ rule đóng góp vào kết quả.

### 23.2. Decision trace

Trace có thể ghi input đã chuẩn hóa, hàng được xét, kết quả từng condition, rule match và hit policy. Dữ liệu nhạy cảm cần được che hoặc giới hạn quyền truy cập.

### 23.3. Reason codes

Output có thể kèm mã lý do như HIGH_RISK, INSUFFICIENT_DATA hoặc VIP_DISCOUNT. Reason code ổn định giúp báo cáo và hỗ trợ khách hàng.

### 23.4. Explainability cho người nghiệp vụ

Một giao diện có thể hiển thị câu giải thích như “Đơn hàng thuộc nội thành và có giá trị từ 1.000.000 VND nên được miễn phí giao hàng”. Câu giải thích nên được tạo từ rule metadata và input thực tế.

### 23.5. Không lưu quá nhiều dữ liệu

Audit cần đủ để tái hiện quyết định nhưng không nên lưu toàn bộ thông tin cá nhân hoặc credential nếu không cần. Có thể dùng input snapshot đã được lọc hoặc reference đến bản ghi có kiểm soát quyền.

### 23.6. Correlation ID

Gắn decision ID với request, workflow và transaction giúp truy vết từ đầu vào đến hành động cuối.

## 24. Bảo mật và quản trị quyền

Decision table có thể quyết định quyền truy cập, phê duyệt, giá và giới hạn giao dịch. Vì vậy, thay đổi bảng có thể có tác động lớn.

### 24.1. Quyền chỉnh sửa

Chỉ người có quyền mới được tạo hoặc sửa decision table. Quyền xem, thử nghiệm và publish có thể tách biệt.

### 24.2. Approval workflow

Chính sách nhạy cảm có thể yêu cầu review hoặc phê duyệt hai người trước khi publish. Quy trình cần ghi nhận version được duyệt.

### 24.3. Separation of duties

Người viết rule và người phát hành có thể là hai vai trò khác nhau để giảm nguy cơ thay đổi không được kiểm soát.

### 24.4. Input trust

Không giả định input từ caller là đáng tin. Kiểm tra schema, domain, authorization và nguồn dữ liệu trước khi đánh giá.

### 24.5. Expression sandbox

Nếu DSL cho phép expression tùy ý, giới hạn hàm được gọi, side effect, thời gian và bộ nhớ. Không thực thi script không tin cậy trong quyền của runtime chính.

### 24.6. Version và integrity

Có thể ký hoặc checksum artifact luật đã phát hành để phát hiện thay đổi ngoài quy trình. Runtime chỉ nạp version từ nguồn được tin cậy.

### 24.7. Sensitive decision data

Input có thể chứa dữ liệu tài chính hoặc thông tin định danh. Trace và report cần phân quyền, retention và redaction phù hợp.

## 25. Tích hợp decision table với workflow và API

Decision table thường là một bước trong một quy trình rộng hơn.

### 25.1. Gọi từ workflow

~~~text
workflow approve_order {
    task load_order
    task decide after success(load_order) {
        use decision-table order_approval
    }
    task notify after success(decide)
}
~~~

Workflow chịu trách nhiệm lấy dữ liệu và điều phối; bảng quyết định trả kết quả nghiệp vụ.

### 25.2. API decision service

Một decision table có thể được cung cấp qua API nhận input record và trả output cùng metadata. API cần version endpoint hoặc version decision để caller kiểm soát thay đổi.

### 25.3. Error mapping

No-match, invalid input, evaluation error và conflict nên có mã lỗi riêng. Caller cần phân biệt lỗi nghiệp vụ với lỗi kỹ thuật.

### 25.4. Transaction boundary

Đánh giá decision thường nên là thao tác thuần. Nếu sau đó có side effect như ghi database hoặc gửi message, workflow hoặc service layer chịu trách nhiệm transaction và retry.

### 25.5. Idempotency

Nếu quyết định kích hoạt hành động, caller cần bảo đảm request retry không tạo side effect trùng. Decision table chỉ trả kết quả; cơ chế idempotency thường nằm ở tầng xử lý nghiệp vụ.

## 26. Ví dụ tổng hợp: quyết định phê duyệt đơn hàng

Giả sử hệ thống cần quyết định đơn hàng được tự động phê duyệt, từ chối hay chuyển nhân viên xem xét. Các input gồm tổng giá trị, trạng thái khách hàng và mức rủi ro.

### 26.1. Mô hình input và output

~~~text
enum CustomerStatus {
    ACTIVE
    NEW
    SUSPENDED
}

enum RiskLevel {
    LOW
    MEDIUM
    HIGH
    CRITICAL
}

enum ApprovalDecision {
    APPROVE
    REJECT
    MANUAL_REVIEW
}
~~~

Input record:

~~~text
type OrderContext = {
    total: Money<VND>
    customerStatus: CustomerStatus
    risk: RiskLevel
}
~~~

Output record:

~~~text
type ApprovalResult = {
    decision: ApprovalDecision
    reasonCode: String
}
~~~

### 26.2. Decision table

| Tổng giá trị | Khách hàng | Rủi ro | Quyết định | Lý do |
|---|---|---|---|---|
| Bất kỳ | SUSPENDED | Bất kỳ | REJECT | CUSTOMER_SUSPENDED |
| Bất kỳ | Bất kỳ | CRITICAL | REJECT | CRITICAL_RISK |
| Trên 50.000.000 VND | Bất kỳ | Bất kỳ | MANUAL_REVIEW | HIGH_VALUE |
| Bất kỳ | NEW | HIGH | MANUAL_REVIEW | NEW_CUSTOMER_HIGH_RISK |
| Đến 50.000.000 VND | ACTIVE | LOW | APPROVE | STANDARD_APPROVAL |

Bảng này minh họa nhiều rule có thể overlap. Ví dụ đơn hàng giá trị cao và rủi ro CRITICAL thỏa cả hai hàng đầu và hàng giá trị cao. Vì vậy, cần chọn hit policy phù hợp hoặc thiết kế lại điều kiện.

### 26.3. Dùng FIRST có chủ đích

Nếu chính sách quy định khách hàng bị khóa và rủi ro critical phải được xử lý trước, FIRST có thể được dùng với thứ tự:

1. Khách hàng SUSPENDED.
2. Rủi ro CRITICAL.
3. Giá trị cao.
4. Khách hàng mới có rủi ro cao.
5. Điều kiện tự động phê duyệt.

Khi đó, vị trí hàng là một phần logic và cần được kiểm thử.

### 26.4. Thiết kế UNIQUE bằng cách phân hoạch miền

Nếu muốn dùng UNIQUE, cần tách các miền sao cho không overlap. Có thể xác định rõ điều kiện risk trước, rồi phân hoạch giá trị và trạng thái khách hàng thành các tổ hợp rời nhau. Validator cần xác nhận không có giao giữa các hàng trong miền hợp lệ.

### 26.5. No-match

Nếu không hàng nào khớp, hệ thống có thể trả MANUAL_REVIEW với reason code NO_MATCH hoặc báo lỗi nếu bảng được kỳ vọng bao phủ mọi trường hợp. Lựa chọn phải phù hợp policy và không nên ngầm cho phép giao dịch.

### 26.6. Decision trace

Kết quả nên chứa decision table ID, version, matched rule ID, output và correlation ID. Người vận hành có thể xác định vì sao đơn được duyệt hoặc chuyển review.

## 27. Những sai lầm thường gặp

### 27.1. Không khai báo hit policy

Khi nhiều hàng cùng match, engine có thể không biết nên chọn một hay thu thập tất cả. Hit policy cần được ghi rõ và validate.

### 27.2. Dùng FIRST nhưng không quản lý thứ tự

Thêm một hàng lên đầu có thể thay đổi kết quả. Cần coi việc sắp xếp hàng là thay đổi logic, review và regression test.

### 27.3. Dùng wildcard quá rộng

Wildcard có thể làm một rule bao phủ nhiều trường hợp và che các rule cụ thể phía sau. Cần phân tích overlap và unreachable.

### 27.4. Bỏ qua no-match

Nếu không có hàng nào khớp, runtime có thể trả trạng thái không rõ hoặc caller xử lý sai. Cần khai báo default hoặc no-match policy.

### 27.5. Trộn null với missing

Dữ liệu không được gửi và dữ liệu có giá trị null có thể mang ý nghĩa nghiệp vụ khác nhau. Schema phải phân biệt.

### 27.6. So sánh không cùng kiểu

So sánh tiền tệ khác currency hoặc ngày giờ khác timezone có thể tạo kết quả sai. Dùng kiểu miền và conversion tường minh.

### 27.7. Đưa side effect vào condition

Gọi API hoặc cập nhật trạng thái trong lúc match khiến kết quả phụ thuộc thứ tự và có thể thực hiện nhiều lần. Condition nên thuần và có thể tái lập.

### 27.8. Không kiểm tra coverage

Bảng có thể thiếu khoảng giá trị hoặc tổ hợp trạng thái. Cần phân tích completeness và kiểm thử biên.

### 27.9. Không version hóa policy

Sửa trực tiếp bảng đang dùng khiến không thể giải thích quyết định lịch sử. Phát hành version bất biến và lưu version trong trace.

### 27.10. Không giải thích kết quả

Chỉ trả APPROVE hoặc REJECT có thể không đủ để audit. Nên có rule ID, reason code và trace phù hợp.

### 27.11. Coi mọi overlap đều là lỗi

Một số policy như COLLECT hoặc PRIORITY được thiết kế để xử lý nhiều hàng match. Cần phân tích overlap theo hit policy thay vì cấm tất cả.

### 27.12. Coi mọi overlap đều an toàn

FIRST hoặc PRIORITY có thể che xung đột nghiệp vụ. Dù policy cho phép overlap, vẫn cần kiểm tra và giải thích thứ tự hoặc mức ưu tiên.

## 28. Nguyên tắc thiết kế decision table trong DSL

Một DSL luật và quyết định tốt cần giúp người viết biểu diễn logic rõ, kiểm tra được và giải thích được.

### 28.1. Định nghĩa input/output có kiểu

Mỗi cột cần tên, kiểu, nguồn và constraint. Tránh để engine suy đoán kiểu từ giá trị trong từng hàng.

### 28.2. Hit policy tường minh

Khai báo UNIQUE, FIRST, ANY, PRIORITY, COLLECT hoặc policy được hỗ trợ. Kiểm tra output schema có tương thích với policy.

### 28.3. Xử lý no-match rõ ràng

Định nghĩa default, reject, optional result hoặc lỗi. Không để caller tự suy đoán trạng thái khi bảng không match.

### 28.4. Phân tích completeness và overlap

Công cụ nên phát hiện gap, overlap, rule unreachable và redundancy trong giới hạn có thể chứng minh.

### 28.5. Điều kiện thuần

Giới hạn expression side effect và dùng snapshot input nhất quán để kết quả có thể tái lập.

### 28.6. Output có thể giải thích

Giữ rule ID, reason code, decision version và trace metadata để audit và hỗ trợ vận hành.

### 28.7. Version hóa bất biến

Thay đổi policy tạo version mới; quản lý effective date, approval và rollback rõ ràng.

### 28.8. Kiểm thử biên và conflict

Kiểm thử từng hàng, boundary, no-match, overlap và hit policy. Lưu regression cases cho các quyết định quan trọng.

### 28.9. Tách quyết định khỏi điều phối

Decision table trả kết quả; workflow hoặc service điều phối side effect. Cách tách này giúp bảng dễ kiểm thử và tái sử dụng.

### 28.10. Công bố semantics của DSL

Tài liệu cần định nghĩa cú pháp cell, wildcard, range, null, equality, ordering, priority, aggregation và lỗi đánh giá. Tránh để hành vi phụ thuộc ngầm vào implementation.

## 29. Thuật ngữ cần nhớ

| Thuật ngữ | Ý nghĩa |
|---|---|
| Decision Table | Bảng biểu diễn các quy tắc bằng điều kiện và kết quả |
| Input Column | Cột khai báo dữ liệu đầu vào của quyết định |
| Output Column | Cột khai báo kết quả của quyết định |
| Rule Row | Một hàng quy tắc với điều kiện và output |
| Hit Policy | Chính sách xử lý khi không, một hoặc nhiều hàng khớp |
| UNIQUE | Yêu cầu tối đa một hàng match |
| FIRST | Chọn hàng match đầu tiên theo thứ tự |
| ANY | Cho phép nhiều hàng match nếu output tương đương |
| PRIORITY | Chọn output có mức ưu tiên cao nhất |
| COLLECT | Thu thập kết quả từ tất cả hàng match |
| RULE ORDER | Trả kết quả theo thứ tự khai báo hàng |
| OUTPUT ORDER | Trả kết quả theo thứ tự ưu tiên output |
| Wildcard | Điều kiện không giới hạn một input |
| No-match | Không có hàng nào thỏa điều kiện |
| Completeness | Mức độ bao phủ miền đầu vào hợp lệ |
| Coverage Gap | Vùng đầu vào không được rule nào bao phủ |
| Overlap | Vùng đầu vào làm nhiều hàng cùng match |
| Conflict | Nhiều rule tạo ra kết quả không tương thích |
| Unreachable Rule | Rule không thể được chọn với đầu vào hợp lệ |
| Decision Requirements Graph | Đồ thị mô tả dependency giữa các quyết định |
| DMN | Tiêu chuẩn mô hình hóa quyết định của OMG |
| FEEL | Ngôn ngữ biểu thức được dùng trong DMN |
| Decision Trace | Dấu vết đánh giá và rule đã được áp dụng |
| Reason Code | Mã giải thích kết quả quyết định |
| Effective Date | Thời điểm một phiên bản policy bắt đầu có hiệu lực |
| Regression Test | Kiểm thử để phát hiện kết quả cũ bị thay đổi ngoài ý muốn |

Bảng quyết định giúp biểu diễn logic nghiệp vụ dưới dạng các điều kiện và kết quả có thể đọc, so sánh và kiểm tra. Trong DSL, decision table cần có input/output được định kiểu, cú pháp condition rõ ràng, hit policy tường minh và no-match behavior được công bố. Các phân tích completeness, overlap, conflict và unreachable rule giúp phát hiện lỗ hổng trước khi phát hành; runtime trace, version và reason code giúp giải thích quyết định sau khi vận hành. Khi điều kiện được giữ thuần, policy được version hóa và các trường hợp biên được kiểm thử, decision table trở thành một cách tổ chức luật dễ bảo trì và phù hợp cho sự phối hợp giữa chuyên gia nghiệp vụ với nhóm phát triển.
