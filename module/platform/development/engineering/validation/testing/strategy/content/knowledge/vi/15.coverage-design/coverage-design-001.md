# Liên kết yêu cầu, rủi ro, điều kiện kiểm thử và bằng chứng

## 1. Vì sao cần liên kết các thành phần của thiết kế bao phủ?

Một kế hoạch kiểm thử có thể chứa nhiều yêu cầu, rủi ro, điều kiện và ca kiểm thử. Nếu các phần này được quản lý rời rạc, nhóm khó trả lời những câu hỏi quan trọng: yêu cầu nào đã được xác nhận, rủi ro nào chưa có kiểm thử, vì sao một ca kiểm thử tồn tại, kết quả nào chứng minh tiêu chí chấp nhận đã đạt và thay đổi mới sẽ ảnh hưởng đến những kiểm thử nào.

**Thiết kế bao phủ (coverage design)** tổ chức mối liên hệ giữa cơ sở kiểm thử, rủi ro, điều kiện kiểm thử, ca kiểm thử, kết quả thực hiện và bằng chứng. Mục tiêu là bảo đảm các quyết định kiểm thử có thể giải thích, có thể truy vết và có thể đánh giá theo mức rủi ro.

Trong phạm vi **VALIDATION_TESTING_STRATEGY**, liên kết này tạo thành một chuỗi bằng chứng từ nhu cầu đến quyết định phát hành. Nhóm có thể chứng minh một yêu cầu quan trọng được kiểm tra bằng những điều kiện nào, rủi ro nào được giảm thiểu, kết quả có đạt không và giới hạn nào vẫn còn. Khi yêu cầu hoặc kiến trúc thay đổi, liên kết giúp tìm đúng phần cần xem xét lại.

Mô hình khái quát:

```text
Nhu cầu / yêu cầu / mục tiêu chất lượng
                 |
                 v
          Rủi ro liên quan
                 |
                 v
        Điều kiện kiểm thử
                 |
                 v
            Ca kiểm thử
                 |
                 v
       Lần chạy và kết quả
                 |
                 v
       Bằng chứng xác nhận
                 |
                 v
    Đánh giá bao phủ và quyết định
```

Đây là mô hình dễ hình dung, nhưng quan hệ thực tế không phải lúc nào cũng một-một. Một yêu cầu có thể liên quan đến nhiều rủi ro; một điều kiện kiểm thử có thể xác nhận nhiều yêu cầu; một ca kiểm thử có thể tạo bằng chứng cho nhiều điều kiện; và một rủi ro có thể cần nhiều loại kiểm chứng độc lập. Thiết kế bao phủ phải thể hiện được những quan hệ nhiều-nhiều đó.

## 2. Phân biệt các khái niệm cần liên kết

### 2.1. Cơ sở kiểm thử và yêu cầu

**Cơ sở kiểm thử (test basis)** là nguồn thông tin dùng để xác định điều gì cần kiểm thử. Nguồn có thể gồm yêu cầu nghiệp vụ, tiêu chí chấp nhận, câu chuyện người dùng, đặc tả API, hợp đồng, mô hình dữ liệu, thiết kế kiến trúc, quy định, mục tiêu chất lượng, phản hồi người dùng và hồ sơ sự cố.

Một yêu cầu có thể được mô tả ở nhiều mức:

- **Nhu cầu:** kết quả mà người dùng hoặc tổ chức muốn đạt.
- **Yêu cầu nghiệp vụ:** quy tắc hoặc khả năng sản phẩm cần hỗ trợ.
- **Yêu cầu chức năng:** hành vi cụ thể hệ thống phải thực hiện.
- **Yêu cầu phi chức năng:** mức hiệu năng, bảo mật, độ tin cậy, khả dụng, tương thích hoặc thuộc tính chất lượng khác.
- **Tiêu chí chấp nhận:** điều kiện để xác định một hạng mục hoặc hành trình đáp ứng mong đợi.

Mỗi mục được dùng làm cơ sở kiểm thử cần có định danh ổn định, phiên bản hoặc mốc hiệu lực, nguồn sở hữu và trạng thái. Nếu yêu cầu chỉ nằm trong một cuộc trao đổi không được ghi nhận, nhóm khó truy vết khi người tham gia thay đổi.

### 2.2. Rủi ro

Rủi ro mô tả sự kiện không mong muốn có thể xảy ra và hậu quả của nó. Có thể viết theo cấu trúc: “Do [nguyên nhân], [sự kiện] có thể xảy ra, dẫn đến [hậu quả]”.

Ví dụ: “Do yêu cầu thanh toán có thể được gửi lại sau timeout, hệ thống có thể tạo giao dịch trùng, dẫn đến người mua bị thu tiền hai lần.”

Rủi ro không giống yêu cầu. Yêu cầu nói hệ thống cần làm gì; rủi ro nói điều gì có thể sai và gây hậu quả gì. Một yêu cầu có thể được liên kết với nhiều rủi ro, và một rủi ro có thể ảnh hưởng đến nhiều yêu cầu hoặc hành trình.

### 2.3. Điều kiện kiểm thử

**Điều kiện kiểm thử (test condition)** là khía cạnh, quy tắc, tình huống hoặc đặc tính cần được xác nhận. Điều kiện kiểm thử chuyển cơ sở kiểm thử thành nội dung có thể thiết kế và đánh giá.

Ví dụ từ yêu cầu “một yêu cầu thanh toán được gửi lại không được tạo khoản thu trùng” có thể tách thành các điều kiện:

- Gửi lại cùng yêu cầu và cùng khóa idempotency.
- Gửi đồng thời hai yêu cầu có cùng khóa.
- Gửi cùng khóa nhưng payload khác.
- Client timeout sau khi provider đã xử lý nhưng chưa nhận được response.
- Webhook xác nhận đến trễ hoặc được gửi lặp.
- Khóa idempotency hết hạn và yêu cầu được gửi lại.

Điều kiện kiểm thử nói điều gì cần được kiểm tra, chưa nhất thiết mô tả từng bước, dữ liệu và kết quả mong đợi của một ca cụ thể.

### 2.4. Ca kiểm thử và thủ tục kiểm thử

**Ca kiểm thử (test case)** mô tả đầu vào, trạng thái ban đầu, thao tác hoặc sự kiện, điều kiện môi trường và kết quả mong đợi để xác nhận một hoặc nhiều điều kiện kiểm thử.

**Thủ tục kiểm thử (test procedure)** mô tả thứ tự thực hiện, cách chuẩn bị, cách chạy và cách thu thập kết quả. Một ca kiểm thử có thể được thực hiện qua thủ tục thủ công hoặc tự động.

Ví dụ, điều kiện “gửi lại cùng khóa idempotency không tạo giao dịch mới” có thể được kiểm tra bằng một ca tự động: tạo giao dịch với khóa `K-001`, gửi lại cùng payload và khóa, sau đó xác nhận chỉ có một giao dịch và hai phản hồi tham chiếu cùng kết quả theo hợp đồng.

### 2.5. Kết quả và bằng chứng

**Kết quả kiểm thử** ghi nhận lần thực hiện đạt, không đạt, bị chặn, không thể kết luận hoặc bị bỏ qua theo quy ước của nhóm.

**Bằng chứng kiểm thử (test evidence)** là dữ liệu hỗ trợ kết luận đó, ví dụ log, báo cáo tự động, ảnh chụp, request/response đã làm sạch, trace, kết quả đối chiếu dữ liệu, video thử nghiệm người dùng, biên bản rà soát hoặc kết quả diễn tập.

Kết quả “PASS” không tự nó là bằng chứng đầy đủ nếu không biết test nào chạy, trên phiên bản nào, ở môi trường nào và theo tiêu chí nào. Bằng chứng phải có nguồn gốc, thời điểm, phạm vi và khả năng liên kết tới lần chạy cụ thể.

## 3. Mô hình truy vết hai chiều

Truy vết hai chiều (bidirectional traceability) nghĩa là có thể đi từ yêu cầu đến bằng chứng và đi ngược từ một ca kiểm thử hoặc bằng chứng về yêu cầu, rủi ro hay điều kiện mà nó hỗ trợ.

### 3.1. Truy vết xuôi

Truy vết xuôi trả lời: “Yêu cầu hoặc rủi ro này được kiểm tra bằng cách nào?”

Với một yêu cầu, nhóm cần tìm được:

1. Rủi ro liên quan và mức ưu tiên.
2. Điều kiện kiểm thử cần xác nhận.
3. Ca kiểm thử hoặc hoạt động kiểm chứng tương ứng.
4. Lần chạy gần nhất và trạng thái kết quả.
5. Bằng chứng và quyết định xử lý khi không đạt.

Nếu một yêu cầu quan trọng không dẫn tới điều kiện hoặc bằng chứng nào, đó là dấu hiệu có khoảng trống bao phủ cần được đánh giá. Tuy nhiên, không phải mọi yêu cầu đều cần một ca kiểm thử riêng; có thể dùng phân tích, kiểm tra tài liệu, thử nghiệm khả dụng hoặc bằng chứng khác phù hợp với bản chất yêu cầu.

### 3.2. Truy vết ngược

Truy vết ngược trả lời: “Vì sao ca kiểm thử này tồn tại và kết quả của nó có ý nghĩa gì?”

Với một ca kiểm thử, cần biết nó xác nhận điều kiện nào, bảo vệ yêu cầu hoặc rủi ro nào, thuộc phiên bản nào và ai sở hữu. Ca kiểm thử không còn liên kết với nhu cầu hoặc rủi ro có thể đã lỗi thời, trùng lặp hoặc kiểm tra một giả định không còn đúng.

Truy vết ngược cũng giúp đánh giá ảnh hưởng khi một ca kiểm thử thất bại. Nếu một test bao phủ nhiều điều kiện, nhóm có thể xác định các yêu cầu và rủi ro cần được xem xét thay vì chỉ sửa test để pipeline xanh.

### 3.3. Quan hệ nhiều-nhiều

Không ép mọi quan hệ thành một chuỗi tuyến tính. Ví dụ:

- Một yêu cầu về thanh toán chính xác liên quan đến rủi ro tính sai tiền, giao dịch trùng và mất trạng thái.
- Rủi ro giao dịch trùng có thể liên quan đến API tạo thanh toán, webhook và quy trình đối soát.
- Một điều kiện kiểm thử webhook lặp có thể hỗ trợ cả yêu cầu về tính đúng đắn giao dịch và yêu cầu về khả năng phục hồi.
- Một ca kiểm thử tích hợp có thể tạo bằng chứng cho nhiều điều kiện, nhưng cần chỉ rõ từng assertion chứng minh điều gì.

Khi một ca kiểm thử chỉ kiểm tra một phần của yêu cầu, hãy ghi phạm vi phần đó. Không đánh dấu toàn bộ yêu cầu đã bao phủ nếu còn các điều kiện quan trọng chưa được xác nhận.

## 4. Xây dựng liên kết từ yêu cầu đến bằng chứng

### Bước 1: Xác định nguồn và định danh yêu cầu

Thu thập cơ sở kiểm thử có liên quan và xác định nguồn chính thức. Gán hoặc giữ định danh ổn định như `REQ-PAY-012`, liên kết đến tài liệu gốc, phiên bản, chủ sở hữu và trạng thái. Tránh tạo một mã mới cho cùng một yêu cầu ở mỗi bảng khác nhau.

Nếu yêu cầu thay đổi, ghi lại phiên bản hoặc lịch sử thay đổi. Một ca kiểm thử chạy trên yêu cầu cũ không tự động chứng minh phiên bản yêu cầu mới đã được đáp ứng.

### Bước 2: Phân rã yêu cầu thành điều kiện kiểm thử

Tách yêu cầu thành các hành vi hoặc thuộc tính có thể xác nhận. Dùng ví dụ, bảng quyết định, sơ đồ trạng thái, phân vùng tương đương, giá trị biên hoặc kịch bản chất lượng để tìm điều kiện.

Một điều kiện nên đủ cụ thể để người thiết kế khác có thể hiểu phạm vi cần kiểm tra. Tránh điều kiện chung như “kiểm tra thanh toán” hoặc “kiểm tra bảo mật”. Có thể tách thành “từ chối thanh toán khi người dùng không có quyền”, “xử lý retry với cùng idempotency key” và “không ghi token vào log”.

### Bước 3: Nhận diện và liên kết rủi ro

Với từng điều kiện, xác định điều gì có thể sai, hậu quả và khả năng phát hiện. Liên kết đến hồ sơ rủi ro hiện có hoặc tạo mục mới theo quy trình. Ghi mức độ nghiêm trọng, khả năng xảy ra, phạm vi ảnh hưởng và mức rủi ro còn lại nếu có.

Không cần tạo một rủi ro riêng cho mọi điều kiện nhỏ. Có thể liên kết nhiều điều kiện với một rủi ro có ý nghĩa chung, miễn là mối quan hệ và phạm vi được giải thích.

### Bước 4: Thiết kế ca kiểm thử và hoạt động xác nhận

Chọn loại kiểm thử phù hợp: đơn vị, thành phần, API, hợp đồng, tích hợp, đầu cuối, hiệu năng, bảo mật, khả dụng, kiểm thử khám phá hoặc kiểm tra vận hành. Mỗi ca cần có dữ liệu, trạng thái ban đầu, điều kiện môi trường, thao tác và kết quả mong đợi.

Một điều kiện có thể cần nhiều ca để bao phủ đường thành công, dữ liệu biên, lỗi, quyền và tương tác đồng thời. Ngược lại, một ca có thể kiểm tra nhiều điều kiện nếu kết quả được phân biệt rõ và không làm cho việc chẩn đoán trở nên khó khăn.

### Bước 5: Xác định bằng chứng cần thu thập

Trước khi chạy, xác định bằng chứng nào đủ để kết luận. Ví dụ, kiểm thử phân quyền cần kết quả response, danh tính/role đã làm sạch, định danh tài nguyên và log kiểm toán; kiểm thử hiệu năng cần cấu hình tải, số mẫu, phân vị độ trễ, thông lượng, tỷ lệ lỗi và tài nguyên.

Không thu thập dữ liệu nhạy cảm vượt quá nhu cầu. Token, mật khẩu, khóa ký và dữ liệu cá nhân cần được loại bỏ hoặc che trước khi lưu/chia sẻ bằng chứng.

### Bước 6: Thực hiện và ghi nhận kết quả

Chạy kiểm thử trên phiên bản và môi trường xác định. Ghi lại kết quả cùng bằng chứng, lỗi liên quan, người thực hiện hoặc pipeline, thời điểm và các điều kiện đặc biệt. Nếu test bị chặn hoặc không chạy, giữ trạng thái đó thay vì đánh dấu đạt.

### Bước 7: Đánh giá khoảng trống và quyết định

Kiểm tra các yêu cầu/rủi ro chưa có điều kiện, điều kiện chưa có ca, ca chưa có kết quả và kết quả không có bằng chứng đủ tin cậy. Xác định phần nào cần bổ sung kiểm thử, phần nào có thể dùng phương pháp xác nhận khác, phần nào được chấp nhận có điều kiện và ai có thẩm quyền quyết định.

## 5. Thiết kế ma trận truy vết

Ma trận truy vết (traceability matrix) là một cách biểu diễn mối liên hệ giữa các đối tượng. Có thể dùng bảng, công cụ quản lý yêu cầu, hệ thống quản lý kiểm thử hoặc dữ liệu có cấu trúc. Công cụ không quan trọng bằng định danh ổn định, quan hệ rõ và khả năng truy xuất.

### 5.1. Các trường nên có

| Trường | Ý nghĩa |
|---|---|
| Requirement ID | Định danh yêu cầu hoặc tiêu chí chấp nhận |
| Requirement version/source | Phiên bản và nguồn chính thức của yêu cầu |
| Risk ID | Rủi ro được liên kết và mức ưu tiên |
| Test condition ID | Điều kiện cần xác nhận |
| Test case ID | Ca kiểm thử hoặc hoạt động kiểm chứng |
| Test level/type | Đơn vị, API, tích hợp, bảo mật, hiệu năng, khám phá... |
| Environment/build | Môi trường, cấu hình và phiên bản bản dựng |
| Expected result | Kết quả mong đợi hoặc ngưỡng đạt |
| Execution/run ID | Định danh lần chạy hoặc báo cáo |
| Actual result/status | Kết quả thực tế: đạt, không đạt, bị chặn, chưa chạy... |
| Evidence reference | Liên kết đến log, báo cáo, ảnh, trace hoặc hồ sơ |
| Owner | Người/nhóm chịu trách nhiệm duy trì hoặc xử lý |
| Exception/decision | Ngoại lệ, chấp thuận rủi ro và thời hạn nếu có |

Không nhất thiết phải đưa tất cả trường vào một bảng rộng. Có thể tách thành các bảng đối tượng và bảng liên kết để tránh lặp dữ liệu. Ví dụ, lưu yêu cầu một lần rồi liên kết đến nhiều risk ID và test condition ID.

### 5.2. Ví dụ ma trận truy vết

Giả sử sản phẩm có yêu cầu không tạo khoản thu trùng khi client gửi lại yêu cầu thanh toán.

| Requirement | Risk | Test condition | Test case | Evidence/result |
|---|---|---|---|---|
| REQ-PAY-012 | RISK-PAY-007: thu tiền trùng | Gửi lại cùng khóa và payload | TC-PAY-041: gửi hai lần tuần tự | Run-882, log giao dịch đã che dữ liệu; PASS |
| REQ-PAY-012 | RISK-PAY-007 | Hai yêu cầu cùng khóa đến đồng thời | TC-PAY-042: chạy song song hai request | Run-883, đối soát transaction; PASS |
| REQ-PAY-012 | RISK-PAY-007 | Response mất sau khi provider xử lý | TC-PAY-043: mô phỏng timeout rồi retry | Run-884, trace và kết quả đối chiếu; FAIL |
| REQ-PAY-012 | RISK-PAY-007 | Webhook xác nhận bị gửi lặp | TC-PAY-044: phát lại cùng event ID | Run-885, event log; PASS |

Trong ví dụ, yêu cầu có nhiều ca kiểm thử. Ba ca đạt không làm cho yêu cầu được coi là đạt nếu một tình huống trọng yếu vẫn thất bại. Kết quả `TC-PAY-043` cần tạo lỗi hoặc hành động xử lý, đánh giá rủi ro còn lại và chặn quyết định phát hành nếu tiêu chí đó là bắt buộc.

### 5.3. Mẫu dữ liệu có cấu trúc

Có thể lưu quan hệ bằng bảng hoặc YAML/JSON. Ví dụ rút gọn:

```yaml
requirement:
  id: REQ-PAY-012
  version: 3
  source: "Payment requirements"
  owner: "Payment product owner"

risks:
  - id: RISK-PAY-007
    statement: "Retry sau timeout có thể tạo khoản thu trùng."
    priority: high

conditions:
  - id: COND-PAY-021
    description: "Cùng idempotency key và payload được gửi lại."
    requirement_ids: [REQ-PAY-012]
    risk_ids: [RISK-PAY-007]

test_cases:
  - id: TC-PAY-041
    condition_ids: [COND-PAY-021]
    level: integration
    expected: "Chỉ có một giao dịch được ghi nhận."
    latest_run: RUN-882

evidence:
  - id: RUN-882
    build: "payment-service@a81f2d"
    environment: "integration-03"
    status: pass
    artifact: "test-report/payment/RUN-882"
```

Đây là ví dụ cấu trúc, không phải định dạng bắt buộc. Khi triển khai thực tế, cần bảo đảm các ID tham chiếu tồn tại, quan hệ không bị đứt và artifact có quyền truy cập phù hợp.

## 6. Đánh giá độ bao phủ đúng cách

### 6.1. Bao phủ yêu cầu

Bao phủ yêu cầu cho biết phần yêu cầu trong phạm vi đã được liên kết với hoạt động xác nhận hay chưa. Có thể tính tỷ lệ yêu cầu có ít nhất một hoạt động kiểm chứng phù hợp trên tổng số yêu cầu thuộc phạm vi.

Tuy nhiên, một yêu cầu có một test liên kết không có nghĩa là đã được bao phủ đầy đủ. Cần xem test có kiểm tra đúng điều kiện, rủi ro, dữ liệu và kết quả hay không. Có thể phân loại mức bao phủ chi tiết hơn: chưa có liên kết, đã thiết kế, đã thực hiện, đạt, không đạt hoặc được xác nhận bằng phương pháp khác.

### 6.2. Bao phủ rủi ro

Bao phủ rủi ro tập trung vào việc các rủi ro quan trọng có biện pháp kiểm soát và bằng chứng phù hợp hay chưa. Rủi ro nghiêm trọng có thể cần nhiều loại bằng chứng độc lập: kiểm thử bảo mật, rà soát thiết kế, kiểm thử phân quyền và giám sát vận hành.

Không nên tính mọi rủi ro ngang nhau. Có thể báo cáo theo mức ưu tiên, ví dụ tỷ lệ rủi ro cao có hoạt động kiểm chứng và kết quả còn hiệu lực. Đồng thời phải nêu rủi ro chưa được kiểm tra, kiểm thử thất bại và ngoại lệ đang mở.

### 6.3. Bao phủ điều kiện kiểm thử

Bao phủ điều kiện cho biết các điều kiện được nhận diện đã có ca kiểm thử hoặc hoạt động xác nhận tương ứng chưa. Đây là cách tìm khoảng trống giữa yêu cầu và thiết kế test.

Ví dụ, điều kiện “xử lý retry” có thể được chia thành retry tuần tự, retry đồng thời, timeout sau khi xử lý, retry với payload khác và retry sau khi khóa hết hạn. Nếu chỉ kiểm tra retry tuần tự, không nên đánh dấu toàn bộ điều kiện retry đã bao phủ.

### 6.4. Bao phủ ca kiểm thử và kết quả

Số lượng ca kiểm thử được viết hoặc tự động hóa là chỉ số về tài sản kiểm thử, không phải bằng chứng trực tiếp về chất lượng. Cần phân biệt:

- Ca đã thiết kế nhưng chưa chạy.
- Ca đã chạy và đạt.
- Ca đã chạy và thất bại.
- Ca bị chặn do môi trường hoặc dữ liệu.
- Ca bị bỏ qua hoặc không còn áp dụng.
- Ca chập chờn, kết quả không đáng tin.

Một ca test bị chặn không thể được tính như đã xác nhận. Một ca đạt trên phiên bản cũ không chứng minh bản dựng mới đã đạt nếu không có bằng chứng áp dụng được.

### 6.5. Không đồng nhất các loại coverage

Các chỉ số sau đo những khía cạnh khác nhau:

| Chỉ số | Đo điều gì | Không chứng minh điều gì |
|---|---|---|
| Requirement coverage | Yêu cầu có liên kết tới hoạt động xác nhận | Chất lượng hoặc độ sâu của hoạt động đó |
| Risk coverage | Rủi ro có kiểm soát/kiểm chứng tương ứng | Rủi ro đã được loại bỏ hoàn toàn |
| Test condition coverage | Điều kiện kiểm thử đã có test hoặc phương pháp xác nhận | Mọi tổ hợp dữ liệu/trạng thái đã được kiểm tra |
| Test execution coverage | Ca nào đã được thực hiện trong phạm vi | Kết quả đạt hoặc bằng chứng có đáng tin |
| Code coverage | Phần mã được thực thi bởi test theo công cụ | Logic nghiệp vụ được xác nhận đúng hoặc lỗi không tồn tại |
| Branch/condition coverage | Nhánh hoặc điều kiện mã được thực thi | Mọi yêu cầu và rủi ro đều được bao phủ |
| API/contract coverage | Giao diện hoặc tương tác hợp đồng được kiểm tra | Luồng đầu cuối, dữ liệu sản xuất hoặc mọi consumer đều đúng |

Không dùng một tỷ lệ tổng hợp duy nhất để thay thế phân tích theo yêu cầu và rủi ro. Một báo cáo bao phủ tốt cần chỉ ra cả phạm vi, mức độ, trạng thái và giới hạn.

## 7. Ưu tiên bao phủ dựa trên rủi ro

Không phải mọi yêu cầu đều cần cùng số lượng test hoặc cùng độ sâu. Phân bổ công sức theo hậu quả nếu lỗi xảy ra, khả năng xảy ra, phạm vi ảnh hưởng, khả năng phát hiện và khả năng khôi phục.

### 7.1. Xếp ưu tiên

Có thể dùng thang định tính như thấp, trung bình, cao và nghiêm trọng. Với mỗi rủi ro, ghi lý do xếp hạng và yếu tố bắt buộc. Các luồng liên quan đến tiền, quyền truy cập, dữ liệu cá nhân, tính toàn vẹn, an toàn và tuân thủ thường cần bằng chứng mạnh hơn.

### 7.2. Chọn độ sâu và loại kiểm thử

| Mức rủi ro | Định hướng bao phủ |
|---|---|
| Thấp | Kiểm thử chức năng cơ bản, kiểm tra hồi quy phù hợp và bằng chứng có thể truy vết |
| Trung bình | Bao phủ luồng chính, dữ liệu biên, lỗi thường gặp, tích hợp và các điều kiện quan trọng |
| Cao | Nhiều lớp kiểm thử, trường hợp lỗi/đồng thời, xác nhận dữ liệu, bảo mật hoặc hiệu năng theo bản chất rủi ro |
| Nghiêm trọng | Bằng chứng độc lập khi cần, kiểm thử âm tính và phục hồi, rà soát chuyên môn, cổng phát hành rõ và chấp thuận rủi ro đúng thẩm quyền |

Đây là định hướng chứ không phải quy tắc đếm số ca. Một rủi ro cao có thể cần một ca kiểm thử tập trung rất tốt cùng kiểm tra thiết kế và giám sát; một rủi ro khác cần hàng chục tổ hợp dữ liệu. Quan trọng là bằng chứng phải đủ sức hỗ trợ kết luận.

### 7.3. Xác định khoảng trống chấp nhận được

Nếu không thể kiểm tra một điều kiện, ghi rõ lý do, tác động, biện pháp thay thế, người chấp thuận và thời hạn xem xét lại. Phân biệt ngoài phạm vi, chưa kiểm thử, bị chặn và không áp dụng. Không biến một khoảng trống chưa giải quyết thành trạng thái đã bao phủ bằng cách thêm một liên kết hình thức.

## 8. Bằng chứng kiểm thử đáng tin cậy

### 8.1. Thuộc tính của bằng chứng tốt

Bằng chứng cần:

- **Có nguồn gốc:** biết được tạo bởi test, người thực hiện hoặc hệ thống nào.
- **Có định danh:** liên kết đến test case, execution/run ID, yêu cầu và rủi ro liên quan.
- **Có bối cảnh:** phiên bản bản dựng, môi trường, cấu hình, dữ liệu và thời điểm.
- **Có tiêu chí:** biết kết quả mong đợi hoặc ngưỡng nào được dùng để kết luận.
- **Có thể kiểm tra lại:** artifact còn truy cập được và đủ thông tin để điều tra.
- **Toàn vẹn:** không bị sửa đổi không kiểm soát; nếu cần có thể lưu checksum hoặc cơ chế quản lý phiên bản.
- **An toàn:** không làm lộ secret, thông tin cá nhân hoặc dữ liệu nhạy cảm ngoài phạm vi được phép.

### 8.2. Ví dụ theo loại kiểm thử

| Hoạt động | Bằng chứng nên lưu |
|---|---|
| Kiểm thử chức năng | Test ID, dữ liệu, bước thực hiện, expected/actual result và trạng thái |
| Kiểm thử API | Request/response đã làm sạch, mã trạng thái, correlation ID, schema và log liên quan |
| Kiểm thử hợp đồng | Phiên bản hợp đồng, consumer/provider version, kết quả xác minh và tương tác thất bại |
| Kiểm thử hiệu năng | Mô hình tải, cấu hình, dữ liệu, thời lượng, p50/p95/p99, thông lượng, lỗi và tài nguyên |
| Kiểm thử bảo mật | Phạm vi, phương pháp, phát hiện, mức nghiêm trọng, bằng chứng đã che dữ liệu và trạng thái khắc phục |
| Kiểm thử khả dụng | Kịch bản, nhóm người dùng, nhiệm vụ, quan sát, số liệu và phản hồi đã được phép lưu |
| Di trú dữ liệu | Phiên bản schema, số lượng bản ghi, quy tắc chuyển đổi, đối soát, sai lệch và biên bản phê duyệt |
| Kiểm thử phục hồi | Kịch bản sự cố, thời điểm, RTO/RPO mục tiêu, thời gian thực tế và kết quả đối chiếu |

### 8.3. Quản lý vòng đời bằng chứng

Xác định nơi lưu, quyền truy cập, thời hạn lưu giữ và cách liên kết artifact. Bằng chứng cần còn sẵn trong thời gian kiểm toán, hỗ trợ hoặc điều tra yêu cầu. Không giữ vô thời hạn dữ liệu nhạy cảm chỉ vì có thể hữu ích trong tương lai.

Khi test được chạy lại, không ghi đè kết quả cũ nếu việc giữ lịch sử cần thiết để giải thích lỗi hoặc quyết định. Mỗi lần chạy nên có định danh riêng và chỉ rõ lần nào được dùng làm bằng chứng cho quyết định hiện tại.

## 9. Quản lý thay đổi và phân tích ảnh hưởng

Truy vết có giá trị đặc biệt khi yêu cầu, thiết kế hoặc implementation thay đổi. Khi một đối tượng đổi, nhóm cần xác định các liên kết bị ảnh hưởng và quyết định phần nào cần xem xét lại.

### 9.1. Khi yêu cầu thay đổi

Từ requirement ID, tìm các rủi ro, điều kiện, test case và bằng chứng liên quan. Kiểm tra:

- Nội dung hoặc tiêu chí chấp nhận nào đã thay đổi?
- Điều kiện kiểm thử cũ còn phù hợp không?
- Có rủi ro mới hoặc mức ưu tiên thay đổi không?
- Test case cần sửa, thêm, bỏ hay chạy lại?
- Bằng chứng cũ còn áp dụng cho phiên bản yêu cầu mới không?

Không xóa lịch sử liên kết cũ. Ghi phiên bản yêu cầu mà lần chạy đã xác nhận để tránh dùng bằng chứng lỗi thời.

### 9.2. Khi rủi ro thay đổi

Nếu có sự cố mới, lỗ hổng mới hoặc tác động được đánh giá lại, tìm các yêu cầu và test condition liên quan. Có thể cần tăng độ sâu kiểm thử, bổ sung test âm tính, mở rộng dữ liệu hoặc tạo giám sát sau phát hành.

### 9.3. Khi test case thay đổi hoặc bị loại bỏ

Tìm các yêu cầu và rủi ro chỉ được ca đó bao phủ. Nếu bỏ test vì trùng lặp, cần chứng minh ca khác cung cấp bằng chứng tương đương hoặc tốt hơn. Nếu bỏ vì không ổn định, ghi rõ khoảng trống và kế hoạch khôi phục.

### 9.4. Khi phiên bản hoặc môi trường thay đổi

Đánh giá liệu bằng chứng cũ có thể áp dụng cho bản dựng mới, cấu hình mới hoặc môi trường khác không. Một thay đổi nhỏ trong dependency, schema, quyền hoặc topology có thể làm mất hiệu lực của một số kết quả. Ghi rõ quy tắc tái sử dụng bằng chứng thay vì mặc định mọi kết quả trước đó vẫn còn hiệu lực.

## 10. Quản trị và duy trì truy vết

### 10.1. Định danh ổn định và quy tắc liên kết

Sử dụng ID duy nhất, dễ tham chiếu và không phụ thuộc vào tên hiển thị có thể thay đổi. Nếu đổi tên yêu cầu, giữ nguyên ID khi ý nghĩa không đổi; nếu ý nghĩa thay đổi đáng kể, quản lý phiên bản hoặc tạo yêu cầu mới theo quy trình.

Quy định loại quan hệ, ví dụ:

- `satisfies`: test condition xác nhận yêu cầu.
- `mitigates`: hoạt động kiểm chứng hoặc kiểm soát giảm thiểu rủi ro.
- `verified_by`: ca kiểm thử xác nhận điều kiện.
- `produces`: lần chạy tạo bằng chứng.
- `supersedes`: yêu cầu hoặc quyết định mới thay thế bản cũ.
- `depends_on`: điều kiện kiểm thử phụ thuộc vào thành phần hoặc môi trường khác.

Tên quan hệ có thể tùy công cụ; điều quan trọng là nhóm hiểu và sử dụng nhất quán.

### 10.2. Chủ sở hữu dữ liệu truy vết

Xác định ai duy trì yêu cầu, ai sở hữu hồ sơ rủi ro, ai tạo test condition và ai bảo đảm kết quả/bằng chứng được cập nhật. Có thể phân chia:

| Đối tượng | Chủ sở hữu thường gặp | Trách nhiệm |
|---|---|---|
| Yêu cầu | Product owner/Business analyst | Định danh, phiên bản, tiêu chí và trạng thái |
| Rủi ro | Risk owner/Service owner | Mô tả, đánh giá, biện pháp và quyết định chấp nhận |
| Điều kiện kiểm thử | Test lead/Tester cùng chuyên gia nghiệp vụ | Phân rã, liên kết và xác định mức bao phủ cần thiết |
| Ca kiểm thử | Người viết hoặc nhóm sở hữu bộ kiểm thử | Duy trì dữ liệu, bước chạy, expected result và trạng thái |
| Lần chạy/bằng chứng | CI owner/Tester/Operations theo hoạt động | Lưu kết quả, metadata, artifact và khả năng truy xuất |
| Báo cáo bao phủ | Test lead/Quality owner | Kiểm tra khoảng trống, độ tin cậy và trình bày giới hạn |

Một cá nhân có thể đảm nhiệm nhiều vai trò, nhưng không nên để trách nhiệm cập nhật liên kết phụ thuộc vào trí nhớ hoặc một bảng cá nhân không được chia sẻ.

### 10.3. Rà soát định kỳ

Rà soát truy vết khi:

- Chuẩn bị cổng phát hành hoặc đánh giá chất lượng.
- Yêu cầu, hợp đồng, kiến trúc hoặc dữ liệu thay đổi.
- Có lỗi nghiêm trọng hoặc sự cố sau phát hành.
- Thêm consumer, nền tảng, nhóm người dùng hoặc tích hợp.
- Loại bỏ hoặc thay thế bộ kiểm thử.
- Đến kỳ đánh giá rủi ro và mục tiêu chất lượng.

Rà soát không chỉ tìm liên kết bị thiếu. Cần kiểm tra liên kết có còn đúng, test có chạy trên phiên bản hiện tại, bằng chứng có còn truy cập được và rủi ro có được xử lý sau kết quả thất bại không.

## 11. Ví dụ xuyên suốt: xác nhận chức năng đăng nhập

Giả sử nhu cầu là người dùng có thể đăng nhập an toàn và chỉ truy cập dữ liệu thuộc tài khoản của mình.

### 11.1. Từ yêu cầu đến rủi ro

| ID | Nội dung |
|---|---|
| REQ-AUTH-001 | Người dùng hợp lệ có thể đăng nhập bằng thông tin xác thực đúng |
| REQ-AUTH-002 | Người dùng không thể truy cập dữ liệu thuộc tài khoản khác |
| REQ-AUTH-003 | Phiên đăng nhập hết hạn phải yêu cầu xác thực lại |
| RISK-AUTH-011 | Kiểm tra phân quyền không đầy đủ có thể làm lộ dữ liệu giữa các tài khoản |
| RISK-AUTH-012 | Xử lý phiên hết hạn sai có thể cho phép truy cập trái phép hoặc làm gián đoạn người dùng |

### 11.2. Từ rủi ro đến điều kiện kiểm thử

| Condition ID | Điều kiện |
|---|---|
| COND-AUTH-001 | Credential hợp lệ tạo phiên đăng nhập đúng |
| COND-AUTH-002 | Credential sai hoặc bị khóa không tạo phiên hợp lệ |
| COND-AUTH-003 | Người dùng A không đọc hoặc sửa được dữ liệu của người dùng B |
| COND-AUTH-004 | Token hết hạn bị từ chối theo chính sách |
| COND-AUTH-005 | Token bị thu hồi không tiếp tục cấp quyền |

### 11.3. Từ điều kiện đến ca và bằng chứng

| Test case | Điều kiện | Loại kiểm thử | Bằng chứng |
|---|---|---|---|
| TC-AUTH-101 | COND-AUTH-001 | API/integration | Response đã làm sạch, session record và run ID |
| TC-AUTH-102 | COND-AUTH-002 | API/security | Mã lỗi, xác nhận không tạo session và log liên quan |
| TC-AUTH-103 | COND-AUTH-003 | Security/integration | Ma trận vai trò, request của A truy cập tài nguyên B và kết quả từ chối |
| TC-AUTH-104 | COND-AUTH-004 | API | Thời điểm hết hạn, response và trạng thái phiên |
| TC-AUTH-105 | COND-AUTH-005 | API/security | Kết quả sau thu hồi token và log kiểm toán |

Nếu `TC-AUTH-103` thất bại, liên kết truy vết cho biết `REQ-AUTH-002` và `RISK-AUTH-011` bị ảnh hưởng. Nhóm có thể chặn phát hành theo chính sách bảo mật, điều tra nguyên nhân, sửa lỗi và chạy lại các ca liên quan. Không chỉ cập nhật test case thành đạt sau khi sửa; cần lưu cả lần chạy thất bại và lần chạy xác nhận sau sửa.

## 12. Những sai lầm thường gặp

- **Tạo ma trận chỉ để có đủ liên kết:** liên kết hình thức không chứng minh test xác nhận đúng nội dung.
- **Không phân biệt yêu cầu, rủi ro và điều kiện:** một yêu cầu không phải là một rủi ro, và điều kiện kiểm thử không phải lúc nào cũng là một ca kiểm thử.
- **Chỉ truy vết một chiều:** không tìm được lý do tồn tại của test hoặc không biết yêu cầu nào chưa có bằng chứng.
- **Ép quan hệ một-một:** bỏ sót trường hợp một yêu cầu cần nhiều điều kiện hoặc một ca hỗ trợ nhiều rủi ro.
- **Đánh dấu bao phủ khi test chưa chạy:** thiết kế test không đồng nghĩa đã có kết quả xác nhận.
- **Tính mọi test pass ngang nhau:** một test rủi ro thấp không bù được một điều kiện bảo mật trọng yếu thất bại.
- **Dùng code coverage thay cho requirement coverage:** mã được thực thi không đồng nghĩa yêu cầu đã được kiểm chứng.
- **Không lưu phiên bản và môi trường:** bằng chứng cũ có thể bị áp dụng sai cho bản dựng mới.
- **Không giữ lịch sử kết quả:** mất thông tin về lỗi đã gặp và cơ sở quyết định phát hành.
- **Bỏ qua bằng chứng ngoài tự động hóa:** rà soát, thử nghiệm người dùng, phân tích và diễn tập cũng có thể tạo bằng chứng phù hợp.
- **Không cập nhật sau thay đổi:** liên kết bị lỗi thời và báo cáo bao phủ trở nên thiếu tin cậy.
- **Thu thập quá nhiều dữ liệu nhạy cảm:** artifact kiểm thử trở thành rủi ro bảo mật và quyền riêng tư.

## 13. Checklist thiết kế và rà soát bao phủ

### Khi thiết kế

- [ ] Cơ sở kiểm thử có nguồn chính thức, ID và phiên bản.
- [ ] Yêu cầu chức năng và phi chức năng được phân rã đủ rõ.
- [ ] Rủi ro liên quan được mô tả và ưu tiên theo tác động.
- [ ] Điều kiện kiểm thử bao phủ đường chính, biên và tình huống lỗi quan trọng.
- [ ] Mỗi điều kiện có ca kiểm thử hoặc phương pháp xác nhận phù hợp.
- [ ] Quan hệ nhiều-nhiều giữa yêu cầu, rủi ro, điều kiện và ca được thể hiện rõ.
- [ ] Expected result, dữ liệu, môi trường và tiêu chí đạt được xác định.
- [ ] Bằng chứng cần thu thập và nơi lưu đã được thống nhất.

### Khi thực hiện

- [ ] Lần chạy gắn với đúng phiên bản, build, môi trường và cấu hình.
- [ ] Trạng thái đạt, không đạt, bị chặn, chưa chạy và không áp dụng được phân biệt.
- [ ] Artifact có nguồn gốc, định danh và khả năng truy xuất.
- [ ] Dữ liệu nhạy cảm và secret được bảo vệ.
- [ ] Lỗi và ngoại lệ được liên kết với yêu cầu/rủi ro bị ảnh hưởng.

### Trước quyết định phát hành

- [ ] Yêu cầu quan trọng có hoạt động xác nhận và bằng chứng còn hiệu lực.
- [ ] Rủi ro cao có kiểm soát và kết quả kiểm chứng phù hợp.
- [ ] Điều kiện chưa bao phủ hoặc chưa đạt được nêu rõ.
- [ ] Bằng chứng có đủ bối cảnh để người khác đánh giá lại.
- [ ] Ngoại lệ có lý do, tác động, người chấp thuận và thời hạn.
- [ ] Các thay đổi gần nhất đã được phân tích ảnh hưởng đến liên kết và test.
- [ ] Báo cáo bao phủ nêu rõ cách tính, phạm vi và giới hạn.

## Kết luận

Liên kết yêu cầu, rủi ro, điều kiện kiểm thử và bằng chứng giúp thiết kế bao phủ trở thành một hệ thống truy vết có thể giải thích. Nhóm cần xác định nguồn và phiên bản yêu cầu, phân rã thành điều kiện, liên kết rủi ro, thiết kế ca phù hợp và lưu bằng chứng gắn với lần chạy cụ thể. Truy vết hai chiều cùng cách đánh giá bao phủ theo rủi ro giúp phát hiện khoảng trống, phân tích ảnh hưởng khi có thay đổi và đưa ra quyết định phát hành dựa trên bằng chứng thực tế.
