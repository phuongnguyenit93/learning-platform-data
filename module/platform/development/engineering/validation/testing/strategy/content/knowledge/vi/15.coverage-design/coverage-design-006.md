# Lựa chọn tiêu chí cấu trúc mã phù hợp với mức độ quan trọng

## Mục tiêu học tập

Sau bài học này, người học có thể:

- Giải thích tiêu chí bao phủ cấu trúc mã và phân biệt chúng với độ bao phủ yêu cầu hoặc chức năng.
- So sánh statement, branch/decision, condition, condition/decision, MC/DC, path, loop và data-flow coverage.
- Lựa chọn mức bao phủ dựa trên mức độ quan trọng, rủi ro, độ phức tạp và hậu quả khi phần mềm hoạt động sai.
- Đọc báo cáo coverage đúng cách, nhận diện giới hạn của phần trăm bao phủ và xử lý mã không thể thực thi.
- Thiết kế trường hợp kiểm thử để đạt tiêu chí đã chọn mà vẫn giữ được tính rõ ràng và khả năng bảo trì.
- Kết hợp bao phủ cấu trúc với kiểm thử dựa trên yêu cầu, phân tích rủi ro, review và các kỹ thuật bổ trợ.
- Ghi nhận lý do lựa chọn tiêu chí, phần chưa đạt và rủi ro còn lại một cách có thể truy vết.

## 1. Vì sao phải chọn tiêu chí bao phủ theo mức độ quan trọng?

Trong phạm vi **VALIDATION_TESTING_STRATEGY**, bao phủ cấu trúc mã (structural code coverage) cho biết các phần cấu trúc của mã nguồn đã được thực thi trong quá trình kiểm thử đến mức nào. Đây là một góc nhìn giúp đánh giá bộ kiểm thử có đi qua các câu lệnh, nhánh quyết định hoặc điều kiện logic quan trọng hay chưa.

Không phải mọi đoạn mã đều có mức độ quan trọng như nhau. Một hàm định dạng thông báo có thể ảnh hưởng nhỏ nếu xử lý sai; một điều kiện quyết định quyền truy cập, giới hạn giao dịch hoặc trạng thái an toàn có thể gây hậu quả lớn. Vì vậy, áp dụng cùng một tiêu chí và ngưỡng coverage cho toàn bộ mã nguồn có thể không phản ánh đúng rủi ro.

Chọn tiêu chí theo mức độ quan trọng giúp nhóm tập trung bằng chứng sâu hơn vào phần mã có hậu quả lớn, đồng thời tránh đặt mục tiêu bao phủ tốn kém nhưng ít giá trị cho phần ít rủi ro. Quyết định này cần dựa trên yêu cầu, phân tích tác động, độ phức tạp và chính sách của tổ chức. Một tỷ lệ coverage cao không tự chứng minh phần mềm đúng; một tỷ lệ thấp cũng cần được diễn giải theo phần mã chưa được thực thi và lý do chưa bao phủ.

Các câu hỏi nền tảng gồm:

- Phần mã này hỗ trợ chức năng hoặc quy tắc nghiệp vụ nào?
- Nếu điều kiện hoặc nhánh sai, hậu quả đối với người dùng, dữ liệu, tiền, an toàn hay hoạt động là gì?
- Cấu trúc logic đơn giản hay có nhiều điều kiện kết hợp, vòng lặp và đường đi?
- Tiêu chí bao phủ nào phù hợp để phát hiện phần chưa được thực thi?
- Những điều kiện nào có thể độc lập làm thay đổi kết quả quyết định?
- Có đường đi nào không thể xảy ra hoặc không thể kiểm tra trong môi trường hiện tại không?
- Bằng chứng nào sẽ cho phép người đánh giá hiểu coverage đạt đến đâu và giới hạn còn lại là gì?

## 2. Bao phủ cấu trúc mã đo điều gì?

Bao phủ cấu trúc mã là một phép đo dựa trên cấu trúc triển khai. Công cụ thường ghi nhận câu lệnh, nhánh, điều kiện hoặc đường đi đã được thực thi khi bộ kiểm thử chạy. Kết quả có thể được biểu diễn dưới dạng số phần tử đã bao phủ trên tổng số phần tử được tính trong phạm vi.

Ví dụ, nếu trong 100 câu lệnh được công cụ tính vào phạm vi có 90 câu đã chạy, statement coverage là 90%. Con số này không cho biết 90 câu đó có được kiểm tra với dữ liệu đủ tốt hay assertion có xác minh đúng kết quả hay không.

### 2.1. Phân biệt coverage với các loại độ bao phủ khác

- **Độ bao phủ yêu cầu (requirements coverage)** cho biết yêu cầu hoặc tiêu chí chấp nhận nào đã có hoạt động kiểm chứng.
- **Độ bao phủ chức năng (functional coverage)** cho biết chức năng, hành trình, trạng thái hoặc tổ hợp nghiệp vụ nào đã được kiểm tra.
- **Độ bao phủ rủi ro (risk coverage)** cho biết rủi ro quan trọng nào đã có biện pháp kiểm tra và bằng chứng.
- **Bao phủ cấu trúc mã (structural coverage)** cho biết các phần tử cấu trúc trong mã đã được thực thi đến mức nào.

Các góc nhìn này bổ sung cho nhau. Một test có thể bao phủ câu lệnh nhưng không xác minh yêu cầu. Một yêu cầu có thể được kiểm tra bằng E2E nhưng không bao phủ mọi nhánh nội bộ. Một nhánh có thể được thực thi mà dữ liệu đầu ra sai vẫn không làm test thất bại nếu assertion quá yếu.

### 2.2. Bao phủ không đồng nghĩa với tính đúng đắn

Coverage trả lời câu hỏi “đã thực thi phần nào?” chứ không tự trả lời “kết quả có đúng không?”. Một test chỉ gọi hàm và không có assertion vẫn có thể làm tăng coverage. Một test có assertion sai hoặc chỉ kiểm tra rằng không phát sinh exception cũng có thể tạo tỷ lệ cao mà không bảo vệ hành vi mong đợi.

Do đó, coverage cần được đọc cùng:

- Yêu cầu và tiêu chí chấp nhận liên quan.
- Chất lượng dữ liệu và các trường hợp biên.
- Assertion và kết quả mong đợi.
- Rủi ro, độ phức tạp và lịch sử lỗi.
- Review mã nguồn và thiết kế.
- Các lỗi được phát hiện trong kiểm thử và sau phát hành.

## 3. Các tiêu chí bao phủ cấu trúc phổ biến

Mỗi tiêu chí xem xét một khía cạnh khác nhau của cấu trúc chương trình. Tên gọi và cách công cụ tính có thể khác nhau theo ngôn ngữ, framework hoặc công cụ đo; nhóm cần thống nhất định nghĩa và phạm vi trước khi đặt mục tiêu.

### 3.1. Statement coverage – bao phủ câu lệnh

Statement coverage đo tỷ lệ câu lệnh có thể thực thi đã được chạy ít nhất một lần.

Ví dụ:

```java
int calculateFee(int amount) {
    int fee = 0;
    if (amount > 100_000) {
        fee = 5_000;
    }
    return fee;
}
```

Một test với `amount = 150_000` thực thi câu lệnh gán `fee = 5_000`; một test với `amount = 50_000` làm điều kiện sai và chỉ thực thi phần còn lại của hàm. Nếu chỉ chạy test đầu tiên, mọi câu lệnh trong ví dụ vẫn có thể đã được thực thi (statement coverage 100%), nhưng kết quả false của điều kiện chưa được kiểm tra. Đây là lý do statement coverage không thay thế branch coverage.

Statement coverage hữu ích để phát hiện mã chưa từng chạy và thường là điểm khởi đầu dễ hiểu. Tuy nhiên, nó không bảo đảm mọi kết quả của điều kiện đều được kiểm tra. Một test chỉ đi vào nhánh `if` có thể đạt nhiều statement coverage nhưng chưa kiểm tra trường hợp điều kiện sai.

### 3.2. Branch hoặc decision coverage – bao phủ nhánh/quyết định

Branch coverage đo việc thực thi các kết quả của điểm rẽ nhánh, chẳng hạn nhánh đúng và sai của `if`, các nhánh của `switch` hoặc kết quả của một quyết định điều khiển. Decision coverage thường được dùng để nói đến việc mỗi quyết định nhận cả kết quả true và false; một số công cụ dùng thuật ngữ branch coverage với cách đếm chi tiết hơn.

Với ví dụ tính phí, cần ít nhất một test có `amount > 100_000` là true và một test làm điều kiện false. Điều này bảo đảm hai kết quả của quyết định đã được thực thi.

Branch coverage thường phát hiện khoảng trống mà statement coverage bỏ qua, nhưng chưa chắc từng điều kiện thành phần trong một biểu thức phức hợp đã được kiểm tra độc lập.

### 3.3. Condition coverage – bao phủ điều kiện

Condition coverage xem xét từng điều kiện Boolean thành phần trong một quyết định và yêu cầu mỗi điều kiện nhận cả giá trị true và false ít nhất một lần.

Ví dụ:

```java
if (isActive && hasPermission) {
    approveRequest();
}
```

Hai điều kiện là `isActive` và `hasPermission`. Bộ test cần làm cho mỗi điều kiện có lúc true và có lúc false. Tuy nhiên, condition coverage đơn thuần không nhất thiết bảo đảm toàn bộ quyết định có cả kết quả true và false trong các tổ hợp đã chạy.

### 3.4. Condition/decision coverage – bao phủ điều kiện và quyết định

Condition/decision coverage yêu cầu cả hai điều:

- Mỗi điều kiện thành phần nhận cả true và false.
- Mỗi quyết định tổng thể nhận cả true và false.

Tiêu chí này kết hợp góc nhìn của condition coverage và decision coverage. Nó mạnh hơn từng tiêu chí riêng lẻ trong nhiều tình huống, nhưng vẫn không nhất thiết chứng minh mỗi điều kiện có ảnh hưởng độc lập đến kết quả quyết định. Khi mức độ quan trọng yêu cầu bằng chứng sâu hơn, nhóm có thể xem xét MC/DC.

### 3.5. MC/DC – Modified Condition/Decision Coverage

MC/DC yêu cầu chứng minh mỗi điều kiện thành phần có thể độc lập làm thay đổi kết quả của quyết định, trong khi các điều kiện khác được giữ phù hợp để cô lập ảnh hưởng đó. Cách định nghĩa chi tiết có thể phụ thuộc tiêu chuẩn hoặc quy trình được áp dụng; nhóm cần thống nhất biến thể MC/DC và cách xử lý short-circuit, điều kiện không được đánh giá hoặc điều kiện phụ thuộc.

Xét quyết định:

```java
boolean allowed = isAuthenticated && (isOwner || isAdministrator);
```

Đặt:

- `A = isAuthenticated`
- `B = isOwner`
- `C = isAdministrator`
- `D = A && (B || C)`

Một tập giá trị minh họa cho unique-cause MC/DC:

| Test | A | B | C | D | Điều kiện được chứng minh |
|---|---|---|---|---|---|
| T1 | true | true | false | true | Mốc so sánh cho A và B. |
| T2 | false | true | false | false | So với T1, chỉ A đổi và D đổi. |
| T3 | true | false | false | false | So với T1, chỉ B đổi và D đổi. |
| T4 | true | false | true | true | So với T3, chỉ C đổi và D đổi. |

Các cặp T1/T2, T1/T3 và T3/T4 lần lượt cho thấy A, B và C có thể độc lập làm thay đổi D. Trong mã thực tế, cần xác nhận các điều kiện được đánh giá như dự kiến và các cặp test hợp lệ theo quy tắc MC/DC đã chọn.

MC/DC thường hữu ích với logic quyết định quan trọng, nơi cần bằng chứng rằng từng điều kiện có ảnh hưởng đến kết quả. Nó đòi hỏi thiết kế test và phân tích phức tạp hơn branch coverage. Không nên áp dụng máy móc cho mọi đoạn mã; cần dựa vào mức độ quan trọng và tiêu chuẩn dự án.

### 3.6. Path coverage – bao phủ đường đi

Path coverage xem xét các đường đi có thể có qua luồng điều khiển. Với chương trình không có vòng lặp và số nhánh nhỏ, có thể liệt kê một tập đường đi hữu hạn. Nhưng khi có vòng lặp, đệ quy hoặc nhiều quyết định kết hợp, số đường đi có thể tăng rất nhanh hoặc trở thành vô hạn.

Bao phủ mọi đường đi thường không khả thi đối với chương trình thực tế. Thay vào đó, nhóm có thể chọn các đường đi quan trọng, đường đi độc lập theo độ phức tạp chu trình hoặc đường đi đại diện cho trạng thái/rủi ro cụ thể. Cần nêu rõ phạm vi đường đi được yêu cầu, không tuyên bố “100% path coverage” nếu vòng lặp hoặc dữ liệu khiến không thể liệt kê toàn bộ.

### 3.7. Loop coverage – bao phủ vòng lặp

Loop coverage tập trung vào hành vi của vòng lặp, ví dụ:

- Không thực hiện vòng lặp (0 lần).
- Thực hiện đúng 1 lần.
- Thực hiện nhiều lần.
- Thực hiện tại giới hạn hoặc gần giới hạn.
- Dừng đúng điều kiện và xử lý khi dữ liệu rỗng hoặc lớn.

Với vòng lặp xử lý danh sách, các trường hợp danh sách rỗng, một phần tử, nhiều phần tử và kích thước sát giới hạn có thể phát hiện lỗi khởi tạo, chỉ số, điều kiện dừng và hiệu năng. Số lần lặp tối đa cần dựa trên quy tắc nghiệp vụ và giới hạn dữ liệu, không tự đặt tùy ý.

### 3.8. Data-flow coverage – bao phủ luồng dữ liệu

Data-flow coverage xem xét các điểm định nghĩa và sử dụng biến, nhằm phát hiện những đường đi mà giá trị được gán nhưng không được sử dụng đúng, bị sử dụng trước khi khởi tạo hoặc bị ghi đè bất ngờ. Một số tiêu chí dựa trên cặp definition-use (def-use) hoặc đường đi từ nơi gán đến nơi sử dụng.

Tiêu chí này hữu ích với logic biến đổi dữ liệu, trạng thái và tính toán phức tạp. Nó có thể bổ sung cho branch coverage khi rủi ro nằm ở cách giá trị đi qua nhiều nhánh. Khả năng đo tự động phụ thuộc ngôn ngữ và công cụ.

## 4. So sánh độ mạnh và giới hạn của tiêu chí

Các tiêu chí không tạo thành một thang đo đơn giản áp dụng cho mọi chương trình, nhưng có thể so sánh về loại bằng chứng mà chúng cung cấp.

| Tiêu chí | Điều được xem xét | Điểm mạnh | Giới hạn chính |
|---|---|---|---|
| Statement | Câu lệnh đã chạy | Dễ đo, phát hiện mã chưa thực thi | Không bảo đảm các kết quả nhánh đều được kiểm tra. |
| Branch/decision | Các kết quả của quyết định | Kiểm tra cả hướng đúng và sai của quyết định | Không bảo đảm từng điều kiện thành phần ảnh hưởng độc lập. |
| Condition | Mỗi điều kiện thành phần true/false | Phát hiện điều kiện chưa từng nhận một giá trị | Không nhất thiết bao phủ cả hai kết quả của quyết định tổng thể. |
| Condition/decision | Điều kiện thành phần và quyết định tổng thể | Kết hợp hai góc nhìn | Không luôn chứng minh tính độc lập của từng điều kiện. |
| MC/DC | Mỗi điều kiện độc lập làm đổi quyết định | Bằng chứng sâu cho logic quyết định phức hợp | Thiết kế, phân tích và duy trì test tốn công hơn. |
| Path | Đường đi qua luồng điều khiển | Có thể phát hiện tương tác giữa nhiều quyết định | Số đường đi tăng mạnh; vòng lặp có thể làm tập đường đi vô hạn. |
| Loop | Số lần và điều kiện lặp | Tập trung vào lỗi biên và điều kiện dừng | Không tự bao phủ mọi tương tác bên trong vòng lặp. |
| Data-flow | Đường đi từ định nghĩa đến sử dụng dữ liệu | Phát hiện vấn đề về vòng đời và sử dụng biến | Đo lường có thể phụ thuộc công cụ và phức tạp với luồng dữ liệu động. |

Branch coverage không luôn bao hàm condition coverage và ngược lại. MC/DC có yêu cầu chứng minh ảnh hưởng độc lập chặt chẽ hơn, nhưng một bộ test đạt MC/DC vẫn không tự chứng minh mọi đường đi, mọi giá trị dữ liệu hoặc mọi yêu cầu nghiệp vụ đều đúng.

## 5. Xác định mức độ quan trọng của mã

Trước khi chọn tiêu chí, cần phân loại phần mã theo hậu quả nếu nó hoạt động sai. Mức độ quan trọng không chỉ dựa vào số dòng hoặc độ phức tạp kỹ thuật.

### 5.1. Các yếu tố đánh giá

- **Tác động nghiệp vụ**: sai sót có làm mất tiền, sai trạng thái giao dịch, gián đoạn quy trình cốt lõi hoặc ảnh hưởng nhiều khách hàng không?
- **Bảo mật và quyền riêng tư**: mã có quyết định xác thực, phân quyền, bảo vệ dữ liệu hoặc xử lý secret không?
- **An toàn và hậu quả nghiêm trọng**: lỗi có thể gây nguy hiểm, hư hỏng thiết bị hoặc ảnh hưởng đến hệ thống quan trọng không?
- **Tính toàn vẹn dữ liệu**: mã có ghi, xóa, chuyển đổi hoặc đồng bộ dữ liệu quan trọng không?
- **Độ phức tạp logic**: có nhiều điều kiện kết hợp, trạng thái, vòng lặp hoặc xử lý lỗi không?
- **Mức độ thay đổi và lịch sử lỗi**: mã thường xuyên thay đổi hoặc từng gây sự cố không?
- **Khả năng phát hiện sau triển khai**: lỗi có dễ nhận biết, khoanh vùng và khôi phục không?
- **Yêu cầu bên ngoài**: hợp đồng, tiêu chuẩn, quy định hoặc quy trình assurance có yêu cầu tiêu chí cụ thể không?

### 5.2. Phân loại minh họa

| Mức độ | Đặc điểm tham khảo | Hướng lựa chọn tiêu chí |
|---|---|---|
| Thấp | Mã trình bày, chuyển đổi đơn giản hoặc chức năng ít tác động; lỗi dễ phát hiện và khắc phục. | Statement hoặc branch coverage phù hợp với logic; vẫn cần test dựa trên yêu cầu và assertion có ý nghĩa. |
| Trung bình | Quy tắc nghiệp vụ thông thường, nhiều nhánh hoặc có tác động giới hạn đến dữ liệu. | Branch/decision coverage làm mục tiêu cơ bản; bổ sung condition hoặc loop coverage ở phần có logic phức tạp. |
| Cao | Mã ảnh hưởng đến giao dịch, quyền truy cập, tính toàn vẹn dữ liệu, thanh toán hoặc hoạt động cốt lõi. | Branch và condition/decision coverage; xem xét MC/DC cho quyết định phức hợp hoặc có hậu quả lớn. |
| Rất cao / trọng yếu | Mã có thể ảnh hưởng đến an toàn, chức năng trọng yếu hoặc chịu yêu cầu assurance/certification cụ thể. | Áp dụng tiêu chí theo tiêu chuẩn và quy trình có thẩm quyền; có thể yêu cầu MC/DC hoặc bằng chứng sâu hơn, cùng review độc lập và truy vết chặt chẽ. |

Đây là khung tham khảo để thảo luận, không phải quy định bắt buộc cho mọi ngành. Với hệ thống chịu tiêu chuẩn an toàn, hàng không, ô tô, y tế hoặc quy định chuyên ngành, tiêu chí cụ thể phải theo tiêu chuẩn áp dụng, phạm vi chứng nhận và quyết định của cơ quan hoặc tổ chức có thẩm quyền. Không tự suy ra mức coverage bắt buộc chỉ từ nhãn “critical”.

## 6. Chọn tiêu chí cho từng loại logic

Một hệ thống có thể cần nhiều tiêu chí ở các phần mã khác nhau. Không nhất thiết áp một mức cho toàn bộ repository.

### 6.1. Logic tuần tự đơn giản

Với hàm chỉ thực hiện một chuỗi phép biến đổi không có quyết định hoặc vòng lặp, statement coverage có thể giúp xác nhận các câu lệnh đã chạy. Tuy nhiên, vẫn cần kiểm tra dữ liệu biên, kết quả mong đợi và trường hợp lỗi nếu có.

### 6.2. Quyết định nhị phân

Với một `if/else` đơn giản, branch coverage thường là lựa chọn phù hợp hơn statement coverage vì yêu cầu cả hai kết quả của quyết định được thực thi. Nếu nhánh liên quan đến quyền, giao dịch hoặc hậu quả lớn, cần xem xét điều kiện dữ liệu, trạng thái và kiểm tra bổ sung.

### 6.3. Biểu thức Boolean phức hợp

Khi một quyết định gồm nhiều điều kiện, branch coverage có thể đạt dù một điều kiện thành phần chưa được kiểm tra độc lập. Condition/decision coverage hoặc MC/DC có thể phù hợp hơn, đặc biệt khi từng điều kiện có ý nghĩa nghiệp vụ hoặc an toàn riêng.

Ví dụ:

```java
boolean canWithdraw(Account account, Money amount) {
    return account.isActive()
        && account.hasWithdrawalPermission()
        && account.balance().compareTo(amount) >= 0;
}
```

Các điều kiện gồm tài khoản đang hoạt động, có quyền rút và số dư đủ. Một bộ test chỉ kiểm tra trường hợp tất cả đều true có thể thực thi đường trả về true nhưng không chứng minh từng điều kiện false được xử lý đúng. Cần có trường hợp làm từng điều kiện ảnh hưởng đến kết quả, đồng thời xác minh không có giao dịch bị ghi khi điều kiện không đạt.

### 6.4. Vòng lặp và xử lý tập dữ liệu

Với vòng lặp xử lý danh sách, hãy chọn trường hợp rỗng, một phần tử, nhiều phần tử và các biên kích thước. Nếu có điều kiện dừng phức tạp, kiểm tra cả việc dừng đúng và không lặp vô hạn. Nếu số lượng bản ghi có thể rất lớn, cần thêm kiểm thử hiệu năng hoặc giới hạn tài nguyên; loop coverage đơn thuần không chứng minh năng lực xử lý.

### 6.5. Máy trạng thái và logic chuyển tiếp

Với mã quản lý trạng thái, branch coverage có thể không đủ để thể hiện các chuyển tiếp hợp lệ và không hợp lệ. Hãy lập mô hình trạng thái, kiểm tra chuyển tiếp được phép, chuyển tiếp bị từ chối và các trạng thái cuối. Kết hợp state-transition testing với coverage cấu trúc để vừa kiểm tra yêu cầu vừa biết phần mã nào đã chạy.

## 7. Ví dụ thiết kế test theo nhiều tiêu chí

Xét hàm kiểm tra một yêu cầu được phép thực hiện khi người dùng đã xác thực và là chủ sở hữu hoặc quản trị viên:

```java
boolean canAccess(boolean authenticated,
                  boolean isOwner,
                  boolean isAdministrator) {
    return authenticated && (isOwner || isAdministrator);
}
```

Đặt `A = authenticated`, `B = isOwner`, `C = isAdministrator`.

### 7.1. Test theo statement và branch

Để bao phủ kết quả true và false của quyết định, cần ít nhất một test cho phép truy cập và một test từ chối. Ví dụ:

| Test | A | B | C | Kết quả mong đợi |
|---|---|---|---|---|
| T1 | true | true | false | true |
| T2 | false | true | false | false |

Hai test này có thể bao phủ cả hai kết quả của quyết định tổng thể, nhưng chưa kiểm tra vai trò quản trị viên là một điều kiện có ảnh hưởng độc lập. Cũng chưa kiểm tra riêng trường hợp đã xác thực nhưng không phải chủ sở hữu và không phải quản trị viên.

### 7.2. Bổ sung condition coverage

Để mỗi điều kiện có cả true và false, có thể bổ sung:

| Test | A | B | C | Kết quả mong đợi |
|---|---|---|---|---|
| T3 | true | false | true | true |
| T4 | true | false | false | false |

Lúc này A, B và C đều đã nhận cả hai giá trị trong tập test. Bộ test cũng thể hiện rõ người không phải chủ sở hữu và không phải quản trị viên bị từ chối.

### 7.3. Xem xét MC/DC

Các test T1, T2, T4 và T3 có thể được ghép thành các cặp để chứng minh mỗi điều kiện độc lập làm thay đổi kết quả:

- A: T1 (`true, true, false`) so với T2 (`false, true, false`).
- B: T1 (`true, true, false`) so với T4 (`true, false, false`).
- C: T4 (`true, false, false`) so với T3 (`true, false, true`).

Mỗi cặp chỉ thay đổi một điều kiện và kết quả quyết định thay đổi. Đây là tập test minh họa unique-cause MC/DC cho biểu thức đã cho. Với triển khai có short-circuit hoặc điều kiện có phụ thuộc, cần kiểm tra thêm cách công cụ và quy trình đánh giá việc điều kiện được đánh giá.

### 7.4. Assertion phải xác minh tác động nghiệp vụ

Nếu hàm này dùng để bảo vệ dữ liệu, test không nên chỉ gọi `canAccess` rồi kiểm tra boolean. Ở cấp tích hợp, cần xác minh người không có quyền thực sự không đọc hoặc thay đổi được dữ liệu. Coverage cấu trúc cho biết logic đã chạy; kiểm thử bảo mật và kiểm thử tích hợp xác minh ranh giới truy cập thực tế.

## 8. Xây dựng ma trận tiêu chí theo mức độ quan trọng

Một ma trận giúp thống nhất kỳ vọng giữa nhóm phát triển, kiểm thử, kiến trúc và người chịu trách nhiệm chất lượng.

| Thành phần | Mức độ quan trọng | Rủi ro chính | Tiêu chí cấu trúc đề xuất | Bằng chứng bổ sung |
|---|---|---|---|---|
| Bộ định dạng thông báo | Thấp | Hiển thị sai nội dung | Statement hoặc branch phù hợp | Test đầu ra với dữ liệu đại diện. |
| Bộ tính giá đơn hàng | Cao | Tính sai tiền, giảm giá hoặc thuế | Branch, condition/decision cho logic phức hợp | Test biên, đối chiếu quy tắc nghiệp vụ và property-based test khi phù hợp. |
| Kiểm tra quyền truy cập | Cao | Truy cập trái phép hoặc lộ dữ liệu | Branch và condition/decision; xem xét MC/DC nếu quyết định phức hợp quan trọng | Integration/security test với vai trò và tenant khác nhau. |
| Bộ điều khiển trạng thái giao dịch | Cao | Chuyển trạng thái sai hoặc giao dịch trùng | Branch, condition, loop hoặc data-flow tùy logic | State-transition test, kiểm tra idempotency và tính toàn vẹn dữ liệu. |
| Logic điều khiển có yêu cầu an toàn chuyên ngành | Rất cao / trọng yếu | Hành vi sai có hậu quả nghiêm trọng | Theo tiêu chuẩn và quy trình assurance áp dụng; có thể yêu cầu MC/DC | Review độc lập, truy vết yêu cầu, phân tích an toàn và bằng chứng xác minh theo quy định. |

Ma trận này không tự động đặt phần trăm coverage. Sau khi chọn tiêu chí, nhóm cần xác định phạm vi mã, cách đo, ngưỡng hoặc điều kiện hoàn thành, ngoại lệ được phép và người có thẩm quyền phê duyệt.

## 9. Xử lý mã chưa được bao phủ

Mã chưa được thực thi cần được phân tích, không nên tự động xem là lỗi hoặc tự động loại khỏi phép đo.

### 9.1. Các nguyên nhân thường gặp

- Thiếu test cho hành vi hoặc nhánh hợp lệ.
- Test chưa tạo được điều kiện để đi vào nhánh.
- Mã xử lý lỗi hoặc fallback chưa được kiểm tra.
- Mã chết (dead code) hoặc nhánh không thể đạt tới.
- Mã sinh tự động, mã framework hoặc mã ngoài phạm vi bị tính vào báo cáo.
- Điều kiện phụ thuộc môi trường hoặc phần cứng chưa có cách mô phỏng phù hợp.
- Test bị bỏ qua, không chạy trong pipeline hoặc bị loại khỏi cấu hình đo.

### 9.2. Cách xử lý

1. Xác định chính xác câu lệnh, nhánh hoặc điều kiện chưa được bao phủ.
2. Truy ngược đến yêu cầu, thiết kế và mức độ quan trọng của mã.
3. Kiểm tra xem phần mã đó có thể được thực thi trong cấu hình hợp lệ không.
4. Nếu có thể thực thi và thuộc phạm vi, thiết kế test để bao phủ và xác minh kết quả.
5. Nếu là mã chết hoặc không còn cần thiết, đánh giá việc loại bỏ qua quy trình thay đổi mã.
6. Nếu là mã sinh tự động hoặc ngoài phạm vi, xác định quy tắc loại trừ nhất quán và ghi rõ lý do.
7. Nếu không thể kiểm tra do giới hạn môi trường, ghi nhận rủi ro và phương án thay thế hoặc xác minh khác.

Không nên loại trừ mã chỉ để tăng tỷ lệ coverage. Mọi exclusion cần có lý do, phạm vi, người xem xét và khả năng truy nguyên.

## 10. Giới hạn của công cụ và phần trăm coverage

Các công cụ coverage thường dùng instrumentation hoặc phân tích bytecode/binary để ghi nhận phần mã được thực thi. Cách tính có thể khác nhau theo ngôn ngữ, compiler, framework, cấu hình và loại báo cáo.

Những điểm cần kiểm tra:

- Phạm vi source file và module nào được đưa vào báo cáo?
- Mã sinh tự động, thư viện bên thứ ba và mã framework có được tính không?
- Điều kiện Boolean được đo ở mức source hay bytecode?
- Các nhánh exception, switch, lambda, coroutine hoặc async có được tính như mong đợi không?
- Test nào được chạy để tạo báo cáo và test nào bị bỏ qua?
- Báo cáo có được gắn với đúng commit, build và phiên bản test không?
- Kết quả có thể được tái tạo trên CI không?

Một phần trăm duy nhất có thể che khuất vùng quan trọng chưa được bao phủ. Nên xem báo cáo theo package, module, file, hàm và nhánh, sau đó đối chiếu với danh sách thành phần có rủi ro cao.

### 10.1. Coverage có thể cao nhưng test yếu

Ví dụ, test gọi mọi hàm và đi qua mọi nhánh nhưng không kiểm tra giá trị trả về hoặc trạng thái dữ liệu. Coverage cao trong trường hợp này chỉ cho biết mã đã chạy. Cần review assertion và đối chiếu tiêu chí chấp nhận.

### 10.2. Coverage thấp không luôn có nghĩa bộ test kém

Một phần mã có thể là adapter phụ thuộc nền tảng, mã sinh tự động hoặc nhánh không thể kích hoạt trong môi trường test thông thường. Tuy nhiên, cần phân tích và ghi nhận rõ. Không được dùng lý do “khó test” để bỏ qua logic quan trọng.

### 10.3. Đừng tối ưu chỉ số bằng cách thay đổi mẫu số

Loại bỏ file khỏi báo cáo, đánh dấu mã là generated hoặc thêm exclusion có thể làm tỷ lệ tăng mà không bổ sung test. Cấu hình phạm vi cần được quản lý như một phần của chiến lược coverage và mọi thay đổi cần có lý do được review.

## 11. Kết hợp coverage với kỹ thuật kiểm thử khác

Bao phủ cấu trúc là một tín hiệu, không phải phương pháp kiểm thử hoàn chỉnh. Để tăng khả năng phát hiện lỗi, hãy kết hợp:

- **Requirements-based testing**: bảo đảm mỗi yêu cầu quan trọng có test và kết quả mong đợi.
- **Boundary value analysis**: kiểm tra giá trị ở ranh giới và ngay hai phía của giới hạn.
- **Equivalence partitioning**: chọn đại diện từ các nhóm dữ liệu có hành vi tương đương.
- **State-transition testing**: kiểm tra trạng thái và chuyển tiếp hợp lệ/không hợp lệ.
- **Decision table testing**: bao phủ tổ hợp điều kiện và hành động theo quy tắc nghiệp vụ.
- **Mutation testing**: cố ý tạo thay đổi nhỏ trong mã để xem test có phát hiện được không; đây là kỹ thuật đánh giá sức mạnh test bổ trợ, không phải một tiêu chí structural coverage.
- **Code review và static analysis**: phát hiện vấn đề về logic, cấu trúc, bảo mật hoặc quy ước mà coverage không đo được.
- **Integration và system testing**: xác minh hành vi tại ranh giới và trong môi trường thực thi.

Ví dụ, branch coverage có thể đạt 100% cho hàm tính giá nhưng test vẫn bỏ sót lỗi làm tròn ở giá trị sát ngưỡng. Boundary value analysis và assertion kiểm tra số tiền chính xác sẽ bổ sung bằng chứng cần thiết.

## 12. Đặt mục tiêu coverage và quản lý ngoại lệ

Sau khi chọn tiêu chí, nhóm cần định nghĩa mục tiêu có thể kiểm chứng và phạm vi áp dụng. Tránh đặt một tỷ lệ chung mà không xác định phần mã nào và tiêu chí nào được đo.

Một mục tiêu nên nêu:

1. **Phạm vi mã**: module, package, file hoặc nhóm chức năng.
2. **Tiêu chí**: statement, branch, condition, MC/DC hoặc tiêu chí khác.
3. **Ngưỡng hoặc điều kiện hoàn thành**: tỷ lệ, các nhánh bắt buộc hoặc yêu cầu không còn phần quan trọng chưa bao phủ.
4. **Cách đo**: công cụ, phiên bản, cấu hình và nhóm test tạo dữ liệu.
5. **Ngoại lệ**: mã sinh tự động, mã không thể thực thi hoặc phần ngoài phạm vi, kèm lý do.
6. **Trách nhiệm**: người đánh giá, người phê duyệt ngoại lệ và người xử lý khoảng trống.
7. **Bằng chứng**: báo cáo gắn với commit/build, test run và liên kết đến yêu cầu/rủi ro.

### 12.1. Không đặt mục tiêu chỉ bằng một tỷ lệ toàn dự án

Một tỷ lệ tổng thể có thể bị các module lớn nhưng ít quan trọng chi phối, trong khi một module nhỏ nhưng trọng yếu chưa được kiểm tra. Nên xem xét mục tiêu theo vùng rủi ro hoặc thành phần, đặc biệt đối với logic có hậu quả cao.

### 12.2. Quản lý phần chưa đạt

Khi mục tiêu chưa đạt, báo cáo cần nêu phần mã còn thiếu, nguyên nhân, mức độ quan trọng, kế hoạch bổ sung test hoặc lý do đề xuất ngoại lệ. Nếu cần chấp nhận rủi ro, phải theo quy trình và thẩm quyền của tổ chức; người viết báo cáo coverage không tự quyết định ngoại lệ.

### 12.3. Theo dõi thay đổi theo thời gian

Coverage nên được theo dõi qua các phiên bản. Khi mã mới được thêm, nhóm cần kiểm tra liệu nó có làm tăng rủi ro hoặc tạo khoảng trống mới. Khi một module được tái cấu trúc, tỷ lệ có thể thay đổi do cấu trúc mã thay đổi; cần xem xét cả nội dung test và phạm vi đo thay vì so sánh phần trăm một cách máy móc.

## 13. Ví dụ thực tế: chọn tiêu chí cho hệ thống thanh toán

Giả sử một hệ thống có các thành phần tính tổng tiền, kiểm tra quyền thanh toán, gửi yêu cầu đến nhà cung cấp và cập nhật trạng thái giao dịch.

### 13.1. Phân loại mức độ quan trọng

- Hàm định dạng mô tả giao dịch: mức thấp nếu không ảnh hưởng dữ liệu hoặc quyết định.
- Logic tính tổng tiền và phí: mức cao vì có thể gây sai lệch tài chính.
- Logic kiểm tra quyền và giới hạn giao dịch: mức cao vì có thể cho phép thao tác trái phép.
- Logic chuyển trạng thái thanh toán sau callback: mức cao vì có thể ghi nhận sai hoặc trùng giao dịch.
- Phần mã điều khiển có yêu cầu an toàn/chứng nhận đặc thù (nếu có): áp dụng tiêu chí theo tiêu chuẩn và quy trình tương ứng.

### 13.2. Chọn tiêu chí và phép kiểm chứng

| Thành phần | Tiêu chí cấu trúc | Test bổ sung |
|---|---|---|
| Định dạng mô tả | Statement hoặc branch tùy logic | Kiểm tra đầu ra với chuỗi rỗng, dài và ký tự đặc biệt. |
| Tính tổng tiền | Branch và condition/decision cho điều kiện khuyến mại, thuế, phí | Boundary tests, bảng quyết định và đối chiếu kết quả tiền tệ. |
| Kiểm tra quyền | Branch, condition/decision; cân nhắc MC/DC nếu logic phức hợp | Kiểm tra vai trò, tenant, quyền thiếu và truy cập trực tiếp qua API. |
| Xử lý callback | Branch, condition và loop/data-flow nếu có retry hoặc danh sách sự kiện | Callback trùng, đến trễ, sai chữ ký, thứ tự khác nhau và idempotency. |
| Tích hợp nhà cung cấp | Coverage cấu trúc trong adapter cộng với contract/integration test | Schema, timeout, lỗi 4xx/5xx, retry và trạng thái cuối. |

### 13.3. Đánh giá kết quả

Giả sử báo cáo cho thấy module thanh toán đạt 95% statement coverage nhưng branch coverage chỉ 72%. Nhóm không nên kết luận module đã đủ an toàn. Cần xác định các nhánh chưa chạy nằm ở đâu: xử lý lỗi nhà cung cấp, từ chối quyền, callback trùng hay nhánh ít quan trọng. Nếu nhánh chưa bao phủ liên quan đến trạng thái giao dịch, cần bổ sung test và xác minh hậu điều kiện. Nếu là mã không thể thực thi hoặc generated code, cần đánh giá exclusion theo quy trình và ghi rõ giới hạn.

Ngược lại, ngay cả khi branch hoặc MC/DC đạt mục tiêu, nhóm vẫn cần kiểm tra rằng assertion xác minh số tiền, trạng thái, quyền và dữ liệu thực tế. Coverage là một phần của bằng chứng, không thay thế kiểm thử chức năng hoặc tích hợp.

## 14. Những sai lầm thường gặp

- **Dùng cùng một tiêu chí cho mọi mã**: không phản ánh mức độ quan trọng. Hãy phân loại theo tác động và rủi ro.
- **Theo đuổi phần trăm coverage tổng thể**: module trọng yếu có thể vẫn thiếu test. Hãy xem theo thành phần và rủi ro.
- **Cho rằng statement coverage chứng minh mọi nhánh**: câu lệnh có thể chạy nhưng một kết quả quyết định chưa được kiểm tra. Hãy chọn branch/decision khi cần.
- **Cho rằng condition coverage tự chứng minh quyết định**: từng điều kiện nhận true/false nhưng kết quả tổng thể có thể chưa đủ. Hãy xem xét condition/decision hoặc MC/DC.
- **Nhầm branch coverage với MC/DC**: bao phủ hai kết quả của quyết định không chứng minh mỗi điều kiện ảnh hưởng độc lập. Hãy dùng tiêu chí phù hợp với logic và mức độ quan trọng.
- **Yêu cầu 100% path coverage cho chương trình có vòng lặp**: số đường đi có thể vô hạn hoặc không khả thi. Hãy xác định đường đi quan trọng và tiêu chí hữu hạn phù hợp.
- **Tạo test chỉ để chạy mã**: coverage tăng nhưng không xác minh kết quả. Hãy yêu cầu assertion gắn với hành vi.
- **Loại trừ mã để làm đẹp báo cáo**: tỷ lệ tăng mà rủi ro không giảm. Hãy quản lý exclusion có lý do và phê duyệt.
- **Bỏ qua nhánh lỗi**: luồng thành công được kiểm tra nhưng xử lý lỗi chưa có bằng chứng. Hãy ưu tiên nhánh lỗi theo hậu quả.
- **Coi coverage là bằng chứng duy nhất**: yêu cầu, dữ liệu, tích hợp và bảo mật vẫn có thể sai. Hãy kết hợp nhiều kỹ thuật.
- **Không cập nhật mục tiêu khi kiến trúc thay đổi**: phạm vi đo và mức quan trọng có thể thay đổi. Hãy rà soát tiêu chí theo phiên bản và rủi ro mới.

## 15. Quy trình lựa chọn và đánh giá tiêu chí bao phủ

Nhóm có thể áp dụng trình tự sau:

1. **Xác định thành phần và chức năng**: lập danh sách module, hàm hoặc vùng mã cần đánh giá.
2. **Đánh giá mức độ quan trọng**: phân tích tác động, khả năng xảy ra, độ phức tạp, bảo mật, dữ liệu và yêu cầu chuyên ngành.
3. **Chọn tiêu chí phù hợp**: statement, branch, condition/decision, MC/DC, loop, path hoặc data-flow theo loại logic và mức rủi ro.
4. **Thiết kế test có assertion**: tạo dữ liệu để thực thi phần tử cần bao phủ và xác minh kết quả mong đợi.
5. **Chạy công cụ và kiểm tra phạm vi**: xác nhận source, module, generated code, cấu hình và phiên bản công cụ.
6. **Phân tích phần chưa bao phủ**: xác định nhánh/điều kiện thiếu, mã chết, mã ngoài phạm vi hoặc giới hạn môi trường.
7. **Bổ sung hoặc xử lý ngoại lệ**: viết test, sửa mã không cần thiết hoặc ghi nhận ngoại lệ theo thẩm quyền.
8. **Đối chiếu với yêu cầu và rủi ro**: bảo đảm coverage đi cùng bằng chứng chức năng, tích hợp và bảo mật.
9. **Lưu báo cáo và rà soát định kỳ**: gắn kết quả với commit/build, theo dõi xu hướng và cập nhật khi mã thay đổi.

## 16. Tự kiểm tra

Trước khi phê duyệt mục tiêu bao phủ cấu trúc mã, hãy tự hỏi:

- Phạm vi mã và mức độ quan trọng của từng thành phần đã rõ chưa?
- Tiêu chí được chọn có phù hợp với loại logic và hậu quả khi lỗi không?
- Đã phân biệt statement, branch, condition, condition/decision và MC/DC chưa?
- Các quyết định phức hợp có cần chứng minh ảnh hưởng độc lập của từng điều kiện không?
- Vòng lặp, trạng thái và luồng dữ liệu có rủi ro riêng cần kiểm tra không?
- Test có assertion xác minh kết quả hay chỉ thực thi mã?
- Phần chưa bao phủ đã được phân tích theo yêu cầu và rủi ro chưa?
- Mọi exclusion có lý do, phạm vi và người xem xét không?
- Báo cáo có gắn với đúng commit, build, công cụ và cấu hình không?
- Coverage đã được kết hợp với kiểm thử yêu cầu, dữ liệu, tích hợp và bảo mật chưa?

## Kết luận

Tiêu chí bao phủ cấu trúc mã cần được lựa chọn theo mức độ quan trọng và loại logic mà phần mềm thực hiện. Statement và branch coverage có thể phù hợp với nhiều phần mã thông thường; condition/decision và MC/DC cung cấp bằng chứng sâu hơn cho logic quyết định phức hợp hoặc trọng yếu; loop, path và data-flow coverage hỗ trợ những rủi ro đặc thù. Không có tỷ lệ coverage đơn lẻ nào chứng minh phần mềm đúng. Khi mục tiêu được gắn với rủi ro, test có assertion rõ ràng, ngoại lệ được giải thích và báo cáo được đối chiếu với yêu cầu, coverage trở thành bằng chứng hữu ích trong chiến lược kiểm thử.
